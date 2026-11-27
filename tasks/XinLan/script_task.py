# This Python file uses the following encoding: utf-8
from datetime import datetime
from typing import Optional

from module.instance_sync import NEXT_DONE, NEXT_RETRY, SyncAdapter, SyncCoordinator, SyncResult
from module.logger import logger
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.assets import GameUiAssets
from tasks.DailyTrifles.assets import DailyTriflesAssets
from tasks.GlobalGame.assets import GlobalGameAssets
from module.interaction_policy import InteractionPolicy
from tasks.Exploration.assets import ExplorationAssets
from tasks.XinLan.adapter import make_adapter
from tasks.XinLan.business import next_business_day_start
from tasks.XinLan.config import SyncConfig, XinLan


def check_pair(sync: SyncConfig, config_name: str) -> Optional[str]:
    """配对配置合法性。返回 None = 合法，否则返回原因。不写 pydantic validator：非范围类校验错误会让整份配置加载不了。"""
    members = [(sync.instance_a.strip(), sync.alias_a.strip()), (sync.instance_b.strip(), sync.alias_b.strip())]
    if not all(name and alias for name, alias in members):
        return 'instance_a / alias_a / instance_b / alias_b must all be filled in'
    (instance_a, alias_a), (instance_b, alias_b) = members
    if instance_a == instance_b:
        return 'instance_a and instance_b must differ'
    if alias_a == alias_b:
        return 'alias_a and alias_b must differ'
    if config_name not in (instance_a, instance_b):
        return f'this instance {config_name!r} is neither instance_a nor instance_b'
    return None


class ScriptTask(GameUi):
    """同心之兰任务编排及导航恢复桥接；互赠时序在适配器里。"""

    # 复用公共关闭机制，但互赠期间不使用可能提交业务的通用确认按钮。
    DEFAULT_UNKNOWN_CLOSERS = [DailyTriflesAssets.I_FRIENDSHIP_UP] + [
        action for action in GameUi.DEFAULT_UNKNOWN_CLOSERS
        if action not in (GlobalGameAssets.I_UI_CONFIRM_SAMLL,
                          GlobalGameAssets.I_UI_CONFIRM,
                          ExplorationAssets.I_E_EXIT_CONFIRM)
    ]

    def _execute_action(self, action, *, interval=None, skip_first_screenshot=True):
        # 每个导航动作重新看邀请，避免关闭前后换帧时误操作绑定邀请。
        self.screenshot()
        if self.appear(GameUiAssets.I_ACC_TONGXIN):
            return False
        return super()._execute_action(action, interval=interval, skip_first_screenshot=True)

    def close_unknown_pages(self, skip_first_screenshot=True):
        self.maybe_screenshot(skip_first_screenshot)
        if self.appear(GameUiAssets.I_ACC_TONGXIN):
            return False
        # 福袋是业务页，交给适配器按原流程关闭，不能被通用返回动作打断。
        if self.appear(GameUiAssets.I_INVITE_TONGXIN):
            return False
        return super().close_unknown_pages(skip_first_screenshot=True)

    def recover_xin_lan_navigation(self, unknown=False):
        """处理一个遮挡；由适配器重新截图并在总时限内连续处理。"""
        self.screenshot()
        if self.appear(GameUiAssets.I_ACC_TONGXIN):
            return False
        if self.appear_then_click(DailyTriflesAssets.I_FRIENDSHIP_UP, interval=1.5,
                                  policy=InteractionPolicy.NAVIGATION):
            return True
        return bool(unknown and self.close_unknown_pages(skip_first_screenshot=True))

    def run(self):
        conf: XinLan = self.config.xin_lan
        # 先关开关再做别的：配置不合法 / 确认被拒 / 抛异常，开关都已经消费掉，不会残留到之后新的 unsafe 上
        reset_requested = self._consume_reset_flag(conf)

        error = check_pair(conf.sync, self.config.config_name)
        if error:
            logger.error(f'XinLan config invalid: {error}')
            self.set_next_run(task='XinLan', success=False)
            return

        adapter = self._build_adapter()
        coordinator = self._build_coordinator(adapter, conf)
        if reset_requested:
            ack = coordinator.acknowledge_unsafe(reason=f'reset_unsafe switch on {self.config.config_name}')
            if ack.acknowledged:
                logger.warning(f'XinLan unsafe round {ack.seq} acknowledged by the reset_unsafe switch')
            else:
                logger.info(f'XinLan reset_unsafe: nothing acknowledged ({ack.reason})')

        # 适配器 / 设备异常由核心原样上抛，交给调度器的异常处理
        self._schedule(coordinator.run())

    def _consume_reset_flag(self, conf: XinLan) -> bool:
        """一次性开关：读到就关回去并立刻落盘，落盘成功之后才允许确认（落盘失败则异常上抛、确认不会发生）。"""
        if not conf.reset.reset_unsafe:
            return False
        conf.reset.reset_unsafe = False
        self.config.save()
        logger.warning('XinLan reset_unsafe switch consumed and turned off')
        return True

    def _build_adapter(self) -> SyncAdapter:
        return make_adapter(self, self.config.xin_lan.sync, self.config.config_name)

    def _build_coordinator(self, adapter: SyncAdapter, conf: XinLan) -> SyncCoordinator:
        sync = conf.sync
        return SyncCoordinator(
            adapter,
            instance=self.config.config_name,
            members=[(sync.instance_a.strip(), sync.alias_a.strip()), (sync.instance_b.strip(), sync.alias_b.strip())],
            rendezvous_timeout=sync.rendezvous_timeout,
        )

    def _schedule(self, result: SyncResult) -> None:
        if result.ok:
            logger.info(f'XinLan sync finished: {result.status}')
        else:
            logger.warning(f'XinLan sync failed: {result.reason} -> {result.next_action} {result.detail}')
            if result.reason == 'unsafe_prior_round':
                logger.warning('Check the game first, then turn on reset_unsafe and run again')

        if result.next_action == NEXT_DONE:
            self.set_next_run(task='XinLan', success=True)
        elif result.next_action == NEXT_RETRY:
            # failure_interval 由用户配置，任务不替用户设置
            self.set_next_run(task='XinLan', success=False)
        else:
            self.set_next_run(task='XinLan', server=False, target=next_business_day_start(datetime.now()))
