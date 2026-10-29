# This Python file uses the following encoding: utf-8
"""同心之兰的真实适配器（P4）：A 先送、B 接受后看回赠按钮作证据，设计见 docs/DECISIONS.md D029 补记（P3）。

所有碰设备的操作都收在 `_shot / _seen / _tap / _ocr / _goto_friends / _keepalive / _pause` 这几个薄方法里，
测试覆盖它们就能在没有设备的情况下跑完整流程；业务时序（谁等谁、哪一步点一次）写在上面的方法里。
"""
import time
from typing import Mapping, Optional

from module.instance_sync import Evidence, PrepareResult, SyncAdapter
from module.instance_sync import state_machine as sm
from module.logger import logger
from tasks.Component.GeneralInvite.assets import GeneralInviteAssets
from tasks.GameUi.assets import GameUiAssets as A
from tasks.XinLan import business
from tasks.XinLan.config import SyncConfig


def _squash(text) -> str:
    return ''.join(str(text).split())


class XinLanAdapter(SyncAdapter):
    """两端共用的导航与读数；发送 / 回赠的时序在 `SenderAdapter` / `ReceiverAdapter`。"""
    business_id = business.BUSINESS_ID

    # 下面的时间都是占位，P5 真机量过再调（秒）
    POLL = 0.5          # 截图 / 账本轮询间隔
    CLICK_GAP = 1.0     # 导航里重复点击同一处的间隔，要大于界面动画
    NAV_TIMEOUT = 30    # 单个导航步骤的上限
    SAME_TOGGLES = 3    # 展开同区好友：最多点几次标题行（它是开关，点太多会来回收起）
    OPEN_TRIES = 3     # 进置顶好友详情：复位 + 点置顶好友 + 核对名字，最多重做几次（远小于单按钮 10 次点击上限）
    ACCEPT_WAIT = 30    # B 等 A 的绑定邀请弹窗出现
    REPUR_WAIT = 15     # B 接受之后等回赠按钮
    NUM_WAIT = 10       # 读次数图标
    JUDGE_WAIT = 90     # 判定一次尝试结果最多等多久
    TOAST_WINDOW = 6    # A 点购买之后，只在前几秒 OCR 小字提示（一闪而过，之后再读也读不到）
    TOAST_KEYWORD = '邀请已发送'

    def __init__(self, task, peer_alias: str):
        self.task = task
        self.peer_alias = peer_alias

    # ------------------------------------------------------------------------------------------------------------------
    # 协议约定
    # ------------------------------------------------------------------------------------------------------------------
    def protocol_params(self) -> Mapping[str, float]:
        return business.PROTOCOL_PARAMS

    def business_day(self, now: float) -> str:
        return business.business_day(now)

    def after_wait(self, seconds: float) -> None:
        # 账本里的纯等待不截图，核心做完较长的等待后在这里重置卡死计时
        self._keepalive()

    # ------------------------------------------------------------------------------------------------------------------
    # 设备缝隙
    # ------------------------------------------------------------------------------------------------------------------
    def _shot(self):
        # 本适配器的循环都有明确的超时；这里清掉卡死计时，不然「只截图不点击」的等待会被当成卡死
        self._keepalive()
        self.task.screenshot()

    def _seen(self, rule) -> bool:
        return bool(self.task.appear(rule))

    def _tap(self, rule) -> None:
        self.task.click(rule)

    def _ocr(self, rule):
        return rule.ocr(self.task.device.image)

    def _goto_friends(self) -> bool:
        from tasks.GameUi.page import page_friends
        return bool(self.task.goto_page(page_friends))

    def _keepalive(self) -> None:
        self.task.device.stuck_record_clear()

    def _pause(self, seconds: float) -> None:
        time.sleep(seconds)

    # ------------------------------------------------------------------------------------------------------------------
    # 公共步骤
    # ------------------------------------------------------------------------------------------------------------------
    def _click_until(self, click, stop, timeout: float, gone: bool = False) -> bool:
        """点 `click` 直到看到 `stop`（`gone=True` 则直到 `stop` 消失）；一进来就满足就一次也不点。

        只用于导航和接受邀请，不用于扣勾玉的点击。
        """
        deadline = time.monotonic() + timeout
        while True:
            self._shot()
            if self._seen(stop) != gone:
                return True
            if time.monotonic() >= deadline:
                logger.warning(f'XinLan: {getattr(stop, "name", stop)} did not appear in {timeout}s')
                return False
            self._tap(click)
            self._pause(self.CLICK_GAP)

    def _expand_same_list(self) -> bool:
        """只认同区好友的 ▶（已收起）：看到才点标题行展开，看不到就当作已展开，往下点置顶好友，名字 OCR 兜底。

        标题行是开关（展开时点会收起，用户 2026-10-24 确认），所以绝不在没看到 ▶ 时点；▶ 与 ▼ 形状差别大
        （实测 ▼ 画面上 `I_FRIEND_SAME_CLOSE` 0.70，▶ 为 1.0，阈值 0.8）。
        次数有限（`SAME_TOGGLES`）：不用 `_click_until` 的 30 秒循环，免得同一按钮来回触发单按钮 10 次点击上限。
        """
        for _ in range(self.SAME_TOGGLES):
            self._shot()
            if not self._seen(A.I_FRIEND_SAME_CLOSE):
                return True
            self._tap(A.C_FRIEND_SAME)
            self._pause(self.CLICK_GAP)
        self._shot()
        if not self._seen(A.I_FRIEND_SAME_CLOSE):
            return True
        logger.warning('XinLan: same-server friend list did not expand')
        return False

    def _on_peer_detail(self) -> bool:
        return _squash(self.peer_alias) in _squash(self._ocr(A.O_NAME_TONGXIN_FRIEND) or '')

    def _open_peer_detail(self) -> bool:
        """好友页 → 置顶好友的详情，并核对头部名字就是对端。

        有通知时好友列表不会停在最顶端，要先点「最近」再点「好友」才回到顶部（用户 2026-10-22 补充），
        所以每次都无条件复位，再点固定坐标；名字对不上就整套重做，用尽仍不对才失败（不会进福袋页）。
        """
        if not self._goto_friends():
            return False
        for attempt in range(1, self.OPEN_TRIES + 1):
            # 两个标签的选中 / 未选中模板互相得分都在 0.94 以上（阈值 0.8 分不开），不能靠「看到已选中就跳过」：
            # 2026-10-24 oas1 因此跳过了复位，一直点在别人身上。这里无条件各点一次，结果交给下面的名字 OCR 核对
            self._tap(A.I_FRIEND_CUR_UNSEL)
            self._pause(self.CLICK_GAP)
            self._tap(A.I_FRIEND_LIST_UNSEL)
            self._pause(self.CLICK_GAP)
            if not self._expand_same_list():
                return False
            self._tap(A.C_THE_TOP_FRIEND)
            self._pause(self.CLICK_GAP)
            self._shot()
            if self._on_peer_detail():
                return True
            logger.warning(f'XinLan: top friend is not {self.peer_alias!r} (attempt {attempt}/{self.OPEN_TRIES})')
        return False

    def _on_gift_page(self) -> bool:
        self._shot()
        return self._seen(A.I_INVITE_TONGXIN)

    def _open_gift_page(self) -> bool:
        """在好友详情点右上角图标进福袋页（初始 / x/10 / x/20 三态外观不同，所以用固定区域点击）。"""
        return self._click_until(A.C_TONGXIN_ICON, A.I_INVITE_TONGXIN, self.NAV_TIMEOUT)

    def _close_gift_page(self) -> bool:
        deadline = time.monotonic() + self.NAV_TIMEOUT
        while True:
            self._shot()
            if not self._seen(A.I_INVITE_TONGXIN):
                return True
            if time.monotonic() >= deadline:
                return False
            self._tap(A.C_RANDOM_LEFT)
            self._pause(self.CLICK_GAP)

    def _accept_invite(self, ctx, inviter_alias: str, timeout: float) -> bool:
        """等绑定邀请弹窗，邀请人对得上才点 ✓ 并等弹窗消失。

        不用 `GeneralInvite.check_then_accept()`：它不区分邀请类型，还会一直循环到进入房间为止。
        名字对不上就不接受（别的邀请不是本任务的），继续等。
        """
        deadline = time.monotonic() + timeout
        ignored = None
        while True:
            ctx.check_alive()
            self._shot()
            if self._seen(A.I_ACC_TONGXIN):
                name = _squash(self._ocr(A.O_NAME_TONGXIN_INVITER) or '')
                if _squash(inviter_alias) in name:
                    return self._click_until(GeneralInviteAssets.I_I_ACCEPT, A.I_ACC_TONGXIN, self.NAV_TIMEOUT,
                                             gone=True)
                if name != ignored:
                    ignored = name
                    logger.warning(f'XinLan: ignore bind invite from {name!r}')
            if time.monotonic() >= deadline:
                return False
            self._pause(self.POLL)

    def _wait_total(self, total: int) -> bool:
        """次数图标 `x/y` 的分母读到 `total`（用户 2026-10-21 确认：成功判据只看分母是 20，不看分子）。"""
        deadline = time.monotonic() + self.NUM_WAIT
        while True:
            self._shot()
            result = self._ocr(A.O_NUM_TONGXIN)
            if result and result[2] == total:
                return True
            if time.monotonic() >= deadline:
                logger.warning(f'XinLan: counter reads {result!r}, expect denominator {total}')
                return False
            self._pause(self.POLL)

    def _verify_total(self) -> bool:
        return self._open_peer_detail() and self._wait_total(20)

    @staticmethod
    def _budget(ctx, cap: float) -> float:
        remaining = ctx.remaining()
        return cap if remaining is None else max(0.0, min(cap, remaining))


class SenderAdapter(XinLanAdapter):
    """instance_a：先送。"""

    def prepare(self, ctx) -> PrepareResult:
        return self._enter_gift_page()

    def _enter_gift_page(self) -> PrepareResult:
        if not self._open_peer_detail():
            return PrepareResult(False, 'peer friend detail not reachable')
        if not self._open_gift_page():
            return PrepareResult(False, 'gift page not reachable')
        self._shot()
        if not self._seen(A.I_PURCHASE_TONGXIN):
            return PrepareResult(False, 'purchase button missing')
        return PrepareResult(True)

    def await_turn(self, ctx) -> bool:
        # 先手没有要等的人；重试时只确认一下购买按钮还在
        self._shot()
        if self._seen(A.I_PURCHASE_TONGXIN):
            return True
        return self._enter_gift_page().ok

    def dispatch(self, ctx, attempt) -> None:
        ctx.check_alive()
        self._tap(A.I_PURCHASE_TONGXIN)

    def judge(self, ctx, attempt) -> Evidence:
        """主证据是 B 的尝试出现（B 只有亲眼看到回赠按钮才写 prepared）；小字提示一闪而过，只是快速通道。"""
        started = time.monotonic()
        wait = self._budget(ctx, self.JUDGE_WAIT)
        while True:
            view = ctx.check_alive()
            if view.peer_attempts:
                return Evidence.done('peer saw the return-gift button')
            elapsed = time.monotonic() - started
            if elapsed < self.TOAST_WINDOW:
                self._shot()
                if self.TOAST_KEYWORD in _squash(self._ocr(A.O_TOAST_TONGXIN) or ''):
                    return Evidence.done('sent toast')
            if elapsed >= wait:
                return Evidence.unknown('neither toast nor peer attempt within the wait')
            self._pause(self.POLL)

    def verify(self, ctx) -> bool:
        # B 回赠后 A 这边会弹出同样的绑定邀请，接受后双方图标都变成 x/20
        if not self._accept_invite(ctx, self.peer_alias, self._budget(ctx, self.JUDGE_WAIT)):
            return False
        return self._close_gift_page() and self._verify_total()

    def inspect_attempt(self, ctx, attempt) -> Evidence:
        # 对端尝试存在 = B 看到过回赠按钮 = 这次一定送到了
        if ctx.view().peer_attempts:
            return Evidence.done('peer has an attempt')
        return Evidence.unknown('no peer attempt, cannot tell')


class ReceiverAdapter(XinLanAdapter):
    """instance_b：接受邀请后回赠。"""

    def prepare(self, ctx) -> PrepareResult:
        if not self._open_peer_detail():
            return PrepareResult(False, 'peer friend detail not reachable')
        return PrepareResult(True)

    def await_turn(self, ctx) -> bool:
        """等 A 点了购买 → 接受绑定邀请 → 打开福袋页，亲眼看到回赠按钮才放行。

        绑定邀请在任何页面都会弹，所以停在好友详情就能接。重试时弹窗早已接受，`_accept_invite` 会等到超时，
        它的结果因此不作判据，以最后「回赠按钮在不在」为准。
        """
        if not ctx.wait_until(lambda view: bool(view.peer_attempts), timeout=self._budget(ctx, self.JUDGE_WAIT)):
            logger.warning('XinLan: peer has not started sending')
            return False
        self._accept_invite(ctx, self.peer_alias, self.ACCEPT_WAIT)
        ctx.check_alive()
        if not self._on_gift_page():
            if not self._open_peer_detail() or not self._open_gift_page():
                return False
        deadline = time.monotonic() + self.REPUR_WAIT
        while True:
            ctx.check_alive()
            self._shot()
            if self._seen(A.I_REPUR_TONGXIN):
                return True
            if time.monotonic() >= deadline:
                logger.warning('XinLan: return-gift button not seen')
                return False
            self._pause(self.POLL)

    def dispatch(self, ctx, attempt) -> None:
        ctx.check_alive()
        self._tap(A.I_REPUR_TONGXIN)

    def judge(self, ctx, attempt) -> Evidence:
        # A 能 verify 说明 B 的回赠送到了而且 A 接受了
        if ctx.wait_until(lambda view: view.peer_state == sm.P_VERIFIED, timeout=self._budget(ctx, self.JUDGE_WAIT)):
            return Evidence.done('peer verified')
        return Evidence.unknown('peer did not verify within the wait')

    def verify(self, ctx) -> bool:
        return self._close_gift_page() and self._verify_total()

    def inspect_attempt(self, ctx, attempt) -> Evidence:
        if ctx.view().peer_state == sm.P_VERIFIED:
            return Evidence.done('peer verified')
        return Evidence.unknown('peer not verified, cannot tell')


def make_adapter(task, sync: SyncConfig, config_name: str) -> XinLanAdapter:
    """instance_a 永远先送，instance_b 永远回赠（用户选定的固定角色）。"""
    if config_name == sync.instance_a.strip():
        return SenderAdapter(task, sync.alias_b.strip())
    return ReceiverAdapter(task, sync.alias_a.strip())
