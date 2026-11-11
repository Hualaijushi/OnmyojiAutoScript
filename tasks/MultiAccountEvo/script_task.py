from __future__ import annotations

import json
import hashlib
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from zerorpc.exceptions import LostRemote, TimeoutExpired

from module.click_pipeline import FinalPoint, execute_single_click
from module.click_sampler import ClickSampler
from module.exception import (
    GameBugError, GameNotRunningError, GamePageUnknownError, GameStuckError,
    GameTooManyClickError, RequestHumanTakeover, ScriptError, TaskEnd,
    OcrUnavailableError, ImageFrameExpiredError,
)
from module.logger import logger
from module.multi_account.account import Account
from module.multi_account.account_switcher import AccountSwitcher
from module.multi_account.courtyard_verifier import CourtyardCharacterVerifierMixin
from module.multi_account.daily_state import DailyStateManager
from module.multi_account.status_report import MultiAccountEvoStatusReport
from module.atom.ocr import RuleOcr
from module.ocr.rpc import set_ocr_logging_enabled
from tasks.Component.GeneralBattle.assets import GeneralBattleAssets
from tasks.Component.GeneralBattle.general_battle import BattleAction
from tasks.Component.GeneralInvite.config_invite import FindMode
from tasks.EvoZone.config import UserStatus
from tasks.EvoZone.script_task import ScriptTask as EvoZoneScriptTask
from tasks.GameUi.default_pages import page_battle, page_battle_prepare, page_battle_result, page_reward, random_click
from tasks.GameUi.game_ui import GameUi
from tasks.MultiAccountEvo.config import MultiAccountEvoRole
from tasks.MultiAccountEvo.event import EventGoalError, event_complete, parse_ticket_value
from tasks.MultiAccountEvo.recovery import (
    GroupGameRestart, ImageServiceUnavailable, TeamStallError,
    wait_for_image_recovery, wait_for_ocr_recovery,
)
from tasks.MultiAccountEvo.sync import (
    ROLES, MultiAccountEvoSync, MultiAccountEvoSyncError, RecoveryRequested, SyncTimeoutError,
    SessionReplacedError, SyncStateError,
)


class ScriptTask(EvoZoneScriptTask, CourtyardCharacterVerifierMixin):
    task_name = "MultiAccountEvo"
    daily_team_task_name = "multi_account_evo"
    switch_instance_order = ("oas3", "oas4", "oas5")
    # The friend-list OCR is slow (~20s for two friends), so give the re-invite
    # timer enough headroom to avoid re-opening the invite panel right after a
    # completed invite.
    invite_retry_seconds_first: float = 40.0
    invite_retry_seconds: float = 40.0
    # 结算后的等待上限是工程初值，仍需三实例真机校准。
    post_battle_timeout: float = 15.0
    post_battle_poll_interval: float = 0.3
    # 同日每组只自动重跑一次，预算保存到共享状态，任务重启也不清零。
    auto_recovery_attempts: int = 1

    def _read_only_image_retry(self, operation):
        """只重试当前识别，使用新截图，不重放调用方已经执行的点击。"""
        try:
            return operation()
        except (TimeoutExpired, LostRemote) as exc:
            used = getattr(self, "_image_read_retries", 0)
            if used >= 2:
                raise ImageServiceUnavailable("批量图像识别持续超时") from exc
            self._image_read_retries = used + 1
            logger.warning("组队觉醒图像识别暂时超时，新截图后只读重试，本组已用=%s/2", used + 1)
            self.screenshot()
            # 每次调用只补试一次；第二次失败透传，避免服务持续繁忙时不断叠加请求。
            try:
                return operation()
            except (TimeoutExpired, LostRemote) as retry_exc:
                raise ImageServiceUnavailable("批量图像识别新帧重试仍失败") from retry_exc

    def prepare_appear_cache(self, targets):
        targets = list(targets)
        parent = super().prepare_appear_cache
        return self._read_only_image_retry(lambda: parent(targets))

    # 四个好友分类标签位于顶部同一条区域，一次 FULL OCR 比依次四次 SINGLE 便宜得多。
    O_MAE_FRIEND_CLASS_BAR = RuleOcr(
        roi=(346, 87, 416, 51),
        area=(346, 87, 416, 51),
        mode="Full",
        method="Default",
        keyword="",
        name="mae_friend_class_bar",
    )
    O_EVENT_PROGRESS_50 = RuleOcr(
        roi=(1128, 10, 104, 24), area=(1128, 10, 104, 24),
        mode="Single", method="Default", keyword="", name="o_event_progress_50",
    )

    def _evo_count_limit_reached(self) -> bool:
        if getattr(self, "_event_segment", None) is not None:
            return self._event_stop
        return super()._evo_count_limit_reached()

    def _evo_time_limit_reached(self) -> bool:
        if getattr(self, "_event_segment", None) is not None:
            return False
        return super()._evo_time_limit_reached()

    def _embedded_count_complete(self, limit_count: int) -> bool:
        if getattr(self, "_event_segment", None) is not None:
            return self._event_stop
        return super()._embedded_count_complete(limit_count)

    def _event_sample_due(self) -> bool:
        context = getattr(self, "_event_segment", None)
        if context is None:
            return False
        next_round = context["completed"] + 1
        point = context["floor"] + next_round
        return (next_round == context["remaining"] or context["pending"]
                or point >= context["start"] and (point - context["start"]) % context["interval"] == 0)

    def _read_event_sample(self) -> bool:
        context = self._event_segment
        if self._event_sample_token is not None or not self._event_sample_due():
            return True
        now = time.monotonic()
        started = getattr(self, "_event_reward_wait_started", None)
        if started is None:
            started = self._event_reward_wait_started = now
        if now - started >= 30:
            self._save_event_ocr_evidence("奖励画面等待稳定超时", [])
            raise EventGoalError("奖励画面等待稳定超时，停止门票识别；已保存截图")
        if not self._event_reward_visible():
            self._event_reward_visible_since = None
            return False
        visible_since = getattr(self, "_event_reward_visible_since", None)
        if visible_since is None:
            self._event_reward_visible_since = now
            return False
        if now - visible_since < 1:
            return False
        self._event_reward_wait_started = None
        self._event_reward_visible_since = None
        started = time.monotonic()
        value, raw, confirmed = None, "", False
        readings = []
        if context["reached"]:
            value, raw, confirmed = 50, "50/50（复用已确认达标）", True
        else:
            consecutive = 0
            for attempt in range(3):
                if attempt:
                    self.screenshot()
                    if not self._event_reward_visible():
                        self._save_event_ocr_evidence("复核时奖励袋消失", readings)
                        raise EventGoalError("门票复核时奖励页已离开，未确认达标")
                raw = str(self.O_EVENT_PROGRESS_50.ocr(self.device.image))
                readings.append(raw)
                value = parse_ticket_value(raw)
                if value is not None and value < 50:
                    break
                if value == 50:
                    consecutive += 1
                    if consecutive >= 2:
                        confirmed = True
                        break
                else:
                    consecutive = 0
            if value is None or value == 50 and not confirmed:
                self._save_event_ocr_evidence("门票读值无效或50未经复核", readings)
                raise EventGoalError(f"门票OCR未能可靠确认，最后读值：{raw[:80]}")
        self._event_sample_token = context["sync"].record_event_sample(
            context["run_id"], context["group"], context["epoch"], context["role"],
            context["completed"] + 1, value, raw, confirmed, time.monotonic() - started,
        )
        context["reached"] = confirmed
        logger.info("超鬼王门票：组=%s 角色=%s 采样场=%s 读值=%s/50 达标=%s",
                    context["group"], context["role"], context["floor"] + context["completed"] + 1,
                    value, confirmed)
        return True

    def _event_reward_visible(self) -> bool:
        """门票截图中的奖励袋是采样锚点，通用结算/皮肤确认标志不足以放行。"""
        return (self.appear(self.I_GET_BATTLE_REWARD)
                or self.appear(self.I_GET_BATTLE_REWARD_2))

    def _save_event_ocr_evidence(self, reason, readings):
        """保存失败现场原帧与实际ROI，不再用事后的庭院截图猜测识别原因。"""
        try:
            import cv2
            context = self._event_segment
            name = str(getattr(self.config, "config_name", "unknown"))
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            folder = Path.cwd()/"log/dailytask/ticket_ocr_debug"/f"{name}_g{context['group']:02d}_{stamp}"
            folder.mkdir(parents=True)
            frame = self.device.image.copy()
            x, y, width, height = self.O_EVENT_PROGRESS_50.roi
            for filename, pixels in (("frame.png", frame), ("roi.png", frame[y:y+height, x:x+width])):
                ok, encoded = cv2.imencode(".png", pixels)
                if not ok:
                    raise OSError("截图编码失败")
                (folder/filename).write_bytes(encoded.tobytes())
            (folder/"sample.json").write_text(json.dumps({
                "reason": reason, "readings": readings, "roi": [x,y,width,height],
                "group": context["group"], "point": context["floor"]+context["completed"]+1,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.warning("门票OCR失败现场已保存：%s", folder)
        except Exception:
            logger.exception("门票OCR失败截图未能保存，原识别错误仍会透传")

    def _refresh_event_report(self) -> None:
        report = getattr(self, "_event_report", None)
        if report is not None:
            try:
                report.refresh()
            except Exception:
                logger.exception("门票HTML更新失败，保留真实任务状态")

    def invite_retry_starts_after_initial_invite(self) -> bool:
        """好友列表 OCR 耗时不计入本任务的重邀间隔。"""
        return True

    def _read_friend_classes(self) -> list[str]:
        """用一次 FULL OCR 读取前四个好友分类区域。

        合并识别结果不完整时回退到原有的四区域读取，不猜测标签顺序。
        """
        results = self.O_MAE_FRIEND_CLASS_BAR.detect_and_ocr(self.device.image)
        ordered = sorted(
            results,
            key=lambda result: min(float(point[0]) for point in result.box),
        )
        friend_class: list[str] = []
        for result in ordered:
            text = str(result.ocr_text or '').replace(' ', '').replace('、', '')
            if text not in self.friend_class:
                continue
            normalized = self._normalize_friend_class_name(text)
            if normalized not in friend_class:
                friend_class.append(normalized)

        if len(friend_class) == 4:
            logger.info('Friend class (batched OCR): %s', friend_class)
            return friend_class

        logger.warning(
            'Friend class batched OCR returned %s/4 valid tabs; use legacy reader',
            len(friend_class),
        )
        return super()._read_friend_classes()

    def appear_then_click(self, target, *args, **kwargs):
        """Disable the obsolete lower room keepalive slot for this task only."""
        if target is self.I_GI_EMOJI_2:
            logger.info('Skip legacy lower room keepalive in MultiAccountEvo')
            return False
        return super().appear_then_click(target, *args, **kwargs)

    def screenshot(self):
        # 共享组件内层循环也经由此入口，恢复请求不能只在觉醒外层检查。
        check = getattr(self, "_team_control_check", None)
        if check is not None:
            check()
        result = super().screenshot()
        if check is not None:
            check()
        return result

    def is_in_room(self, is_screenshot: bool = True) -> bool:
        """本任务复用房间标题和上方表情，避开已失效的下方表情位置。"""
        if is_screenshot:
            self.screenshot()
        return any(self.appear(marker) for marker in (
            self.I_GI_IN_ROOM, self.I_GI_EMOJI_1,
        ))

    def _room_snapshot_after_screenshot(self) -> bool:
        """队长及邀请循环已截图；只读当前帧，不跨轮缓存房间状态。"""
        return self.is_in_room(False)

    def _post_battle_invite_step(self) -> bool:
        """每帧最多执行一个已识别的邀请动作，动作后交回新截图。"""
        leader = self.active_evo_zone.evo_zone_config.user_status == UserStatus.LEADER
        if self.appear(self.I_GI_SURE):
            if leader and self.active_evo_zone.invite_config.default_invite:
                if self.appear_then_click(self.I_I_NO_DEFAULT, interval=0.8):
                    return True
            return self.appear_then_click(self.I_GI_SURE, interval=0.8)
        if not leader and self.appear_accept():
            return self.check_then_accept(single_step=True)
        return False

    def _wait_post_battle_state(self) -> str:
        """确认结算后的去向；未知帧不点击，不把一次页面命中当作终态。"""
        started = time.monotonic()
        previous = None
        consecutive = 0
        member = self.active_evo_zone.evo_zone_config.user_status == UserStatus.MEMBER
        while time.monotonic() - started < self.post_battle_timeout:
            self._check_embedded_abort()
            self.screenshot()
            if time.monotonic() - started >= self.post_battle_timeout:
                break
            # 邀请与结算覆盖层优先于其下方的房间或探索背景。
            if self.appear(self.I_GI_SURE) or (member and self.appear_accept()):
                state = 'invite'
                self._post_battle_invite_step()
            else:
                page = GameUi.detect_page_in(
                    self, page_battle_prepare, page_battle, page_battle_result,
                    page_reward, include_global=False,
                )
                if page in (page_battle_prepare, page_battle):
                    state = 'battle'
                elif page in (page_battle_result, page_reward):
                    state = 'reward'
                    self.click(self._multi_account_settlement_click(), interval=0.8)
                elif self.is_in_room(False):
                    state = 'room'
                elif self.appear(self.I_MATCHING):
                    state = 'matching'
                elif self.appear(self.I_CHECK_EXPLORATION):
                    state = 'exploration'
                elif self.appear(self.I_CHECK_MAIN):
                    state = 'main'
                else:
                    state = 'unknown'
            consecutive = consecutive + 1 if state == previous else 1
            if state != previous:
                logger.info('Post-battle confirmation: %s', state)
            previous = state
            if consecutive >= 2:
                if state == 'room':
                    return state
                # 队员可能已被秒开，交回原有战斗接管入口；达标后不把新战斗当作收尾。
                if state == 'battle' and member and self.current_count < self.limit_count:
                    return state
                if state in ('matching', 'exploration', 'main'):
                    # 队员结算后可先回庭院等待再次邀请；房主仍在房间，不能据此判整组失效。
                    # 是否达标继续由外层计数判断，未达标时交回原有接受邀请循环。
                    if member:
                        return state
                    raise TeamStallError(f'Post-battle room lost: {state}')
            time.sleep(self.post_battle_poll_interval)
        raise TeamStallError(f'Post-battle confirmation timeout: last_state={previous or "unknown"}')

    def run_general_battle(self, *args, **kwargs) -> bool:
        """战斗结果返回后确认房间，避免结算过渡帧直接触发觉醒外层失败分支。"""
        self._team_battle_settled = False
        self._event_sample_token = None
        self._event_reward_wait_started = None
        self._event_reward_visible_since = None
        sample_due = self._event_sample_due()
        result = super().run_general_battle(*args, **kwargs)
        checkpoint = getattr(self, "_team_battle_checkpoint", None)
        if checkpoint is not None:
            if not self._team_battle_settled:
                raise TeamStallError("Battle returned without confirmed settlement")
            # 先保存已结束的战斗，再确认回房；战后丢房不能抹掉本场结果。
            checkpoint()
        self._wait_post_battle_state()
        context = getattr(self, "_event_segment", None)
        if context is not None and sample_due:
            if self._event_sample_token is None:
                raise EventGoalError("采样场已结束但没有取得奖励页门票读值")
            state = context["sync"].finish_event_sample(
                context["run_id"], context["group"], context["epoch"], context["role"], self._event_sample_token,
            )
            context["pending"] = False
            self._event_stop = event_complete(state, context["group"])
            self._refresh_event_report()
            if not self._event_stop and max(state["battle_progress"][str(context["group"])].values()) >= state["battle_count"]:
                raise EventGoalError(f"已到{state['battle_count']}把保护上限，三端门票仍未全部确认50/50")
        return result

    def invite_friends(self, config, open_invite: bool = True, confirm_rule=None) -> bool:
        """Invite friends with sensitive names redacted for this task only."""
        logger.hr('Invite friends', 2)
        if not config.friend_list_v:
            logger.warning('No friend to invite')
            return False
        logger.info('Need invite friend count: %s', len(config.friend_list_v))
        if not self._open_invite_panel_if_needed(open_invite):
            return True
        friend_class = self._read_friend_classes()
        selected_set: set[str] = set()
        match config.find_mode:
            case FindMode.RECENT_FRIEND:
                self._select_recent_mode_friends(friend_class, config.friend_list_v, selected_set)
            case FindMode.AUTO_FIND:
                self._select_auto_mode_friends(friend_class, config.friend_list_v, selected_set)
        return self._confirm_invite_and_validate(selected_set, config.friend_list_v, confirm_rule)

    def _find_exact_friend_area(self, rule, name: str) -> tuple[int, int, int, int] | None:
        """Find a friend while keeping its name out of this task's logs."""
        target_name = self._normalize_friend_name_text(name)
        if not target_name:
            return None
        boxed_results = rule.detect_and_ocr(self.device.image)
        if not boxed_results:
            return None
        for result in boxed_results:
            if self._normalize_friend_name_text(result.ocr_text) != target_name:
                continue
            box = result.box
            area = (
                int(box[0, 0] + rule.roi[0]),
                int(box[0, 1] + rule.roi[1]),
                int(box[1, 0] - box[0, 0]),
                int(box[2, 1] - box[0, 1]),
            )
            logger.info('Exact match friend [redacted] in %s at %s', rule.name, area)
            return area
        return None

    def _detect_select(self, name: str = None) -> bool:
        """Select a friend without exposing its name in failure logs."""
        if not name:
            return False
        self.screenshot()
        pre_cnt = len(self.I_SELECTED.match_all_any(self.device.image, frame_id=self.device.image_frame_id))
        for _ in range(3):
            self.screenshot()
            if len(self.I_SELECTED.match_all_any(
                    self.device.image, frame_id=self.device.image_frame_id)) >= pre_cnt + 1:
                return True
            rule = self.O_FRIEND_NAME_1
            select_area = self._find_exact_friend_area(rule, name)
            if select_area is None:
                rule = self.O_FRIEND_NAME_2
                select_area = self._find_exact_friend_area(rule, name)
            if select_area is None:
                logger.info('Current page no exact friend')
                return False
            # T7-5 Stage 2：好友名 OCR bbox 即安全点击 ROI；随 GeneralInvite 一起从任务私有
            # 整框均匀 `_random_point_in_area` 迁到统一 preferred 热点模型（未登记 →
            # RULE_FALLBACK），不再保留两套点位实现。
            click_x, click_y = ClickSampler.sample_target(select_area, rule.name)
            # 落点已由 ClickSampler 采样完毕，交给 L1 时必须包成 FinalPoint（零二次采样）。
            execute_single_click(self.device, FinalPoint(click_x, click_y), control_name=rule.name)
            if self._wait_selected_appear(pre_cnt):
                return True
        logger.warning('Find friend [redacted] but failed to select')
        return False

    def appear_accept(self) -> bool:
        """Accept only the normal team invitation in this task."""
        return self.appear(self.I_I_ACCEPT)

    def check_then_accept(self, *, single_step: bool = False) -> bool:
        """复用接受邀请的安全中心点；结算确认只执行当前帧的一步。"""
        if not self.appear_accept():
            return False
        logger.info('Click accept')
        while True:
            if not single_step:
                self.screenshot()
                if self.is_in_room():
                    return True
            if self.appear(GeneralBattleAssets.I_EXIT):
                return False
            if self.appear_then_click(self.I_I_NO_DEFAULT, interval=1):
                if single_step:
                    return True
                continue
            if self.appear_then_click(self.I_GI_SURE, interval=1):
                if single_step:
                    return True
                continue
            if self.appear_then_click(self.I_I_ACCEPT_DEFAULT, interval=1):
                if single_step:
                    return True
                continue
            if self.appear(self.I_I_ACCEPT):
                x, y, width, height = self.I_I_ACCEPT.roi_front
                # 本任务接受邀请事务暂缓 L2 改造（与 GeneralInvite 五个点位同一决定），
                # 这里只把执行入口收口到 L1：固定中心点仍是最终落点，不加 policy / reaction。
                execute_single_click(self.device, FinalPoint(x + width // 2, y + height // 2))
                if single_step:
                    return True
                time.sleep(1)
            if single_step:
                return False

    @staticmethod
    def _multi_account_settlement_click():
        """Keep this task's settlement clicks away from the new left sidebar."""
        return random_click(ltrb=(False, False, True, False))

    def _handle_result(self, context, config) -> BattleAction:
        """Handle this task's settlement without using the common left area."""
        self._event_reward_visible_since = None
        self._team_battle_settled = True
        context.reward_no_battle_ts = None
        context.is_win = not self.appear(self.I_FALSE, threshold=0.8)
        if context.last_page != page_battle_result:
            self.device.click_record_clear()
        self.click(self._multi_account_settlement_click(), interval=0.8)
        return BattleAction.CONTINUE

    def _handle_reward(self, context, config) -> BattleAction:
        """Handle this task's reward page without using the common left area."""
        if self.active_evo_zone.evo_zone_config.user_status == UserStatus.LEADER and \
                self.appear(self.I_GI_SURE):
            self._post_battle_invite_step()
            return BattleAction.CONTINUE
        event_mode = getattr(self, "_event_segment", None) is not None
        skin_closed = self.appear_then_click(self.I_GB_SKIN_CONFIRM, interval=0.8)
        if event_mode and skin_closed:
            self._event_reward_visible_since = None
            return BattleAction.CONTINUE
        self._team_battle_settled = True
        context.reward_no_battle_ts = None
        context.is_win = True
        if event_mode:
            if not self._read_event_sample():
                return BattleAction.CONTINUE
        if context.last_page != page_reward:
            self.device.click_record_clear()
        self.click(self._multi_account_settlement_click(), interval=0.8)
        return BattleAction.CONTINUE

    @staticmethod
    def _normalize_account(value: object) -> str:
        return str(value or "").strip().casefold()

    @classmethod
    def _parse_related_accounts(cls, value: object) -> dict[str, str]:
        result: dict[str, str] = {}
        for part in str(value or "").split("#"):
            instance, separator, account = part.partition(":")
            if not separator:
                continue
            instance = instance.strip().casefold()
            account = cls._normalize_account(account)
            if instance:
                result[instance] = account
        return result

    def _enabled_peer_configs(self) -> list[dict]:
        peers = []
        for path in sorted((Path.cwd() / "config").glob("*.json")):
            if path.name == "template.json" or path.name.startswith("."):
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"cannot read peer config {path.name}: {exc}") from exc
            task = data.get("multi_account_evo")
            if not isinstance(task, dict) or not task.get("scheduler", {}).get("enable", False):
                continue
            peers.append(
                {
                    "name": path.stem,
                    "role": task.get("multi_account_evo_config", {}).get("role"),
                    "kirin_type": task.get("multi_account_evo_config", {}).get("kirin_type", "雷麒麟"),
                    "layer": task.get("multi_account_evo_config", {}).get("layer", "拾层"),
                    "group_count": task.get("multi_account_evo_config", {}).get("group_count", 18),
                    "group_start": task.get("multi_account_evo_config", {}).get("group_start", 1),
                    "group_end": task.get("multi_account_evo_config", {}).get("group_end", 0)
                    or task.get("multi_account_evo_config", {}).get("group_count", 18),
                    "battle_count": task.get("multi_account_evo_config", {}).get("battle_count", 20),
                    "event_progress_enable": task.get("multi_account_evo_config", {}).get("event_progress_enable", False),
                    "event_ocr_start": task.get("multi_account_evo_config", {}).get("event_ocr_start", 200),
                    "event_ocr_interval": task.get("multi_account_evo_config", {}).get("event_ocr_interval", 10),
                    "evo_zone_enabled": data.get("evo_zone", {}).get("scheduler", {}).get("enable", False),
                    "accounts": [
                        {
                            "account": (task.get(f"account_list_{index}") or {}).get("account", ""),
                            "related_account": (task.get(f"account_list_{index}") or {}).get("related_account", ""),
                            "character": (task.get(f"account_list_{index}") or {}).get("character", ""),
                            "svr": (task.get(f"account_list_{index}") or {}).get("svr", ""),
                            "apple_or_android": (task.get(f"account_list_{index}") or {}).get("apple_or_android", False),
                        }
                        for index in range(
                            1,
                            int(task.get("multi_account_evo_config", {}).get("group_count", 18)) + 1,
                        )
                    ],
                }
            )
        return peers

    def _validate_related_account_groups(self, peers: list[dict]) -> None:
        peer_by_name = {peer["name"].lower(): peer for peer in peers}
        expected_instances = set(self.switch_instance_order)
        group_count = int(peers[0]["group_count"])
        for group in range(1, group_count + 1):
            expected = {
                instance: self._normalize_account(peer_by_name[instance]["accounts"][group - 1]["account"])
                for instance in self.switch_instance_order
            }
            missing = [instance for instance, account in expected.items() if not account]
            if missing:
                raise ValueError(
                    f"account group {group} is missing login account for {', '.join(missing)}"
                )
            for instance in self.switch_instance_order:
                related = self._parse_related_accounts(
                    peer_by_name[instance]["accounts"][group - 1]["related_account"]
                )
                if set(related) != expected_instances or related != expected:
                    raise ValueError(
                        f"account group {group} related_account mismatch in {instance}"
                    )

    def _validate_peer_configs(self) -> list[dict]:
        peers = self._enabled_peer_configs()
        if len(peers) != 3:
            raise ValueError(f"exactly 3 enabled MultiAccountEvo configs are required, found {len(peers)}")
        roles = [peer["role"] for peer in peers]
        expected_roles = {role.value for role in MultiAccountEvoRole}
        if set(roles) != expected_roles or len(set(roles)) != 3:
            raise ValueError("the three MultiAccountEvo roles must be unique: leader, member_1, member_2")
        if len({peer["group_count"] for peer in peers}) != 1:
            raise ValueError("the three MultiAccountEvo group_count values must match")
        if len({peer["battle_count"] for peer in peers}) != 1:
            raise ValueError("the three MultiAccountEvo battle_count values must match")
        if len({peer["kirin_type"] for peer in peers}) != 1:
            raise ValueError("the three MultiAccountEvo kirin_type values must match")
        if len({peer["layer"] for peer in peers}) != 1:
            raise ValueError("the three MultiAccountEvo layer values must match")
        for field in ("event_progress_enable", "event_ocr_start", "event_ocr_interval"):
            if len({peer[field] for peer in peers}) != 1:
                raise ValueError(f"the three MultiAccountEvo {field} values must match")
        for field, default in (("group_start", 1), ("group_end", peers[0]["group_count"])):
            if len({peer.get(field, default) for peer in peers}) != 1:
                raise ValueError(f"the three MultiAccountEvo {field} values must match")
        if not 1 <= peers[0].get("group_start", 1) <= peers[0].get("group_end", peers[0]["group_count"]) <= peers[0]["group_count"]:
            raise ValueError("invalid local account group range")
        conflicting = [peer["name"] for peer in peers if peer["evo_zone_enabled"]]
        if conflicting:
            raise ValueError("EvoZone and MultiAccountEvo cannot both be enabled in the same config")
        actual_names = {peer["name"].lower() for peer in peers}
        if actual_names != set(self.switch_instance_order):
            raise ValueError("enabled MultiAccountEvo configs must be oas3, oas4 and oas5")
        self._validate_related_account_groups(peers)
        return peers

    @staticmethod
    def _battle_checkpoint_key(peers: list[dict]) -> str:
        """绑定三端角色、账号顺序及副本目标，只持久化摘要，不写明文账号。"""
        payload = [
            {key: peer[key] for key in (
                "name", "role", "kirin_type", "layer", "group_count", "battle_count", "accounts",
            )}
            for peer in sorted(peers, key=lambda item: item["name"])
        ]
        for source, item in zip(sorted(peers, key=lambda item: item["name"]), payload):
            if source.get("event_progress_enable"):
                item.update(event_progress_enable=True, event_ocr_start=source.get("event_ocr_start", 200),
                            event_ocr_interval=source.get("event_ocr_interval", 10))
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def _validate_checkpoint_runtime_config(self, peers: list[dict]) -> None:
        """旧进程内存配置不能借用磁盘上新账号的断点身份。"""
        config = self.config.multi_account_evo
        peer = next(item for item in peers if item["name"].lower() == self.config.config_name.lower())
        expected = {
            "role": config.role.value, "kirin_type": config.kirin_type, "layer": config.layer,
            "group_count": config.group_count, "battle_count": config.battle_count,
            "accounts": [
                {key: getattr(account, key) for key in (
                    "account", "related_account", "character", "svr", "apple_or_android",
                )}
                for account in config.account_list[:config.group_count]
            ],
        }
        if any(peer[key] != value for key, value in expected.items()):
            raise ValueError("loaded checkpoint configuration differs from disk; reload this task")
        for field, default in (("event_progress_enable", False), ("event_ocr_start", 200), ("event_ocr_interval", 10)):
            if peer.get(field, default) != getattr(config.multi_account_evo_config, field):
                raise ValueError("loaded event configuration differs from disk; reload this task")
        for field, default in (("group_start", 1), ("group_end", config.group_count)):
            if peer.get(field, default) != getattr(config, field):
                raise ValueError("loaded group range differs from disk; reload all three tasks")

    @staticmethod
    def _can_write_daily_status(sync, run_id, group) -> bool:
        """旧日期或已换组、换代的任务不能覆盖当前每日状态。"""
        state = sync.read()
        return (state["date"] == date.today().isoformat()
                and state["run_id"] == run_id and state["current_group"] == group)

    def _finish_successfully(self) -> None:
        self.set_next_run(self.task_name, finish=True, success=True)
        raise TaskEnd(self.task_name)

    @staticmethod
    def _daily_team_id(group: int) -> str:
        return f"group_{int(group):02d}"

    @staticmethod
    def _refresh_status_report(
        status_report: MultiAccountEvoStatusReport,
        daily_state: DailyStateManager,
    ) -> None:
        try:
            status_report.refresh(daily_state.load_today())
        except Exception as exc:
            logger.warning(
                "Cannot update MultiAccountEvo desktop status report: %s",
                exc.__class__.__name__,
            )

    def _check_embedded_abort_with_team_wait(self, check) -> None:
        """Run the sync abort check while keeping the team-wait exemption armed.

        EvoZone's room/team wait has no dedicated stuck record, so a slow
        member can push the leader past the 60s device guard and abort a
        healthy group.  Re-arming the existing PREPARE_BEFORE_BATTLE
        long-wait exemption on every embedded loop iteration raises that
        bound to the battle standard (300s) while still failing on a
        genuinely frozen game.
        """
        check()
        self.device.stuck_record_add("PREPARE_BEFORE_BATTLE")

    def _run_embedded_abort_check(self, run_id, group, sync) -> None:
        """Wire the embedded abort check without shadowing the callback slot.

        EvoZone's ``run_embedded`` stores the callback on
        ``self._embedded_abort_check`` while the embedded run is active.  The
        method must therefore keep a different name, otherwise the callback
        would call itself with one argument and raise a TypeError.
        """
        self._check_embedded_abort_with_team_wait(
            lambda: sync.assert_active(run_id, group, max_age=sync.control_check_interval)
        )

    def run(self) -> bool:
        ocr_logging_enabled = bool(self.config.global_game.ocr.save_ocr_log)
        set_ocr_logging_enabled(False)
        try:
            return self._run_multi_account_evo()
        finally:
            set_ocr_logging_enabled(ocr_logging_enabled)

    def _notify_failure(self, group: int | None, role: str, message: str) -> None:
        config = self.config.multi_account_evo.multi_account_evo_config
        if not config.failure_notify_enable:
            return
        if not config.failure_pushplus_token:
            logger.warning("MultiAccountEvo failure notification skipped: PushPlus token is empty")
            return
        try:
            response = requests.post(
                "https://www.pushplus.plus/send",
                json={
                    "token": config.failure_pushplus_token,
                    "title": f"{str(self.config.config_name).upper()} 多账号组队觉醒失败",
                    "content": (
                        f"组别：{group if group is not None else '未开始'}\n"
                        f"角色：{role}\n原因：{message}"
                    ),
                    "template": "markdown",
                },
                timeout=(3, 8),
            )
            response.raise_for_status()
            if response.json().get("code") != 200:
                logger.warning("MultiAccountEvo PushPlus notification was rejected")
        except Exception as notify_exc:
            logger.warning("MultiAccountEvo failure notification failed: %s", notify_exc.__class__.__name__)

    def _run_multi_account_evo(self) -> bool:
        config = self.config.multi_account_evo
        role = config.role.value
        sync = MultiAccountEvoSync(
            Path.cwd() / "config",
            timeout=config.sync_timeout_seconds,
            event_mode=config.multi_account_evo_config.event_progress_enable,
        )
        if config.multi_account_evo_config.event_progress_enable:
            from module.multi_account.event_ticket_report import EventTicketReport
            self.daily_team_task_name = "multi_account_evo_event_50"
            self._event_report = EventTicketReport(
                sync, group_count=config.group_count, group_start=config.group_start, group_end=config.group_end,
                event_ocr_start=config.multi_account_evo_config.event_ocr_start,
                event_ocr_interval=config.multi_account_evo_config.event_ocr_interval,
                battle_count=config.battle_count,
            )
        daily_state = DailyStateManager(
            Path.cwd() / "config",
            recover_instances=set(),
        )
        status_report = getattr(self, "_event_report", None) or MultiAccountEvoStatusReport(Path.cwd() / "config")
        self._refresh_status_report(status_report, daily_state)
        run_id = None
        group = None
        self._team_bound_session = None

        try:
            config.validate_runtime_accounts()
            peers = self._validate_peer_configs()
            self._validate_checkpoint_runtime_config(peers)
            checkpoint_key = self._battle_checkpoint_key(peers)

            def checkpoint_key_for_count(count):
                # 还原旧上限核对摘要，其他账号和任务设置必须完全一致。
                previous_peers = [dict(peer, battle_count=count) for peer in peers]
                return self._battle_checkpoint_key(previous_peers)

            if config.role == MultiAccountEvoRole.LEADER:
                state = sync.start_or_resume(
                    config.group_count, config.battle_count, checkpoint_key=checkpoint_key,
                    group_start=config.group_start, group_end=config.group_end,
                    event_ocr_start=config.multi_account_evo_config.event_ocr_start,
                    event_ocr_interval=config.multi_account_evo_config.event_ocr_interval,
                    checkpoint_key_for_count=checkpoint_key_for_count,
                )
            else:
                state = sync.wait_for_session(date.today().isoformat())

            if state.get("checkpoint_key") != checkpoint_key:
                raise ValueError("shared battle checkpoint configuration does not match; reload all three tasks")
            if state["group_count"] != config.group_count:
                raise ValueError("shared group_count does not match local config")
            if state["battle_count"] != config.battle_count:
                raise ValueError("shared battle_count does not match local config")
            if (state.get("group_start", 1), state.get("group_end", config.group_count)) != (config.group_start, config.group_end):
                raise ValueError("shared group range does not match local config")
            if state["complete"]:
                logger.info("MultiAccountEvo is already complete for today")
                self._finish_successfully()

            run_id = state["run_id"]
            group = int(state["current_group"])
            while group <= config.group_end:
                logger.info("MultiAccountEvo group %s/%s", group, config.group_count)
                team_id = self._daily_team_id(group)
                if daily_state.is_team_task_completed_today(
                    team_id,
                    self.daily_team_task_name,
                ):
                    logger.info(
                        "Skip completed MultiAccountEvo group %s: durable state was updated today",
                        group,
                    )
                    if config.role == MultiAccountEvoRole.LEADER:
                        state = sync.skip_completed_group(run_id, group, role)
                    else:
                        state = sync.wait_for_advance(run_id, group)
                    if state["complete"]:
                        break
                    group = int(state["current_group"])
                    continue
                if config.role == MultiAccountEvoRole.LEADER:
                    if not self._can_write_daily_status(sync, run_id, group):
                        raise RuntimeError("stale task cannot update today's daily status")
                    daily_state.mark_team_task_status(
                        team_id,
                        self.daily_team_task_name,
                        "running",
                        target=50 if sync.event_mode else config.battle_count,
                    )
                    self._refresh_status_report(status_report, daily_state)
                account = config.account_list[group - 1]
                logger.info(
                    "Parallel account switch: instance=%s shared_group=%s",
                    self.config.config_name,
                    group,
                )
                account_id_prefix = {"oas3": "A", "oas4": "B", "oas5": "C"}[str(self.config.config_name).lower()]
                managed_account = Account(
                    account_id=f"{account_id_prefix}{group:02d}",
                    instance=str(self.config.config_name).lower(),
                    position=group,
                    character=account.character,
                    server=account.svr,
                    login_account=account.account,
                    account_alias=account.account_alias,
                    apple_or_android=account.apple_or_android,
                    related_account=account.related_account,
                )
                run_id, group_state = self._run_prebattle_session(
                    config, sync, run_id, group, role, managed_account, checkpoint_key,
                )
                if config.role == MultiAccountEvoRole.LEADER:
                    # Persist completion before advancing. If the process exits
                    # after this write, today's next run will safely skip the
                    # already completed account group.
                    if not self._can_write_daily_status(sync, run_id, group):
                        raise RuntimeError("stale task cannot update today's daily status")
                    if sync.event_mode:
                        daily_state.mark_team_task_status(team_id, self.daily_team_task_name, "completed", target=50)
                    else:
                        daily_state.update_team_progress(
                            team_id, self.daily_team_task_name, config.battle_count, target=config.battle_count,
                        )
                    self._refresh_status_report(status_report, daily_state)
                    state = sync.advance(run_id, group, role)
                    self._refresh_event_report()
                else:
                    state = group_state
                if state["complete"]:
                    break
                group = int(state["current_group"])

            self._finish_successfully()
        except TaskEnd:
            raise
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            logger.error("MultiAccountEvo failed: %s", message)
            bound = getattr(self, "_team_bound_session", None)
            if bound is not None and bound[0] == group:
                run_id = bound[1]
            if run_id is not None and group is not None:
                try:
                    sync.fail(run_id, group, role, message)
                except Exception as sync_exc:
                    logger.warning(
                        "Cannot update MultiAccountEvo failure state: %s",
                        sync_exc.__class__.__name__,
                    )
                try:
                    if self._can_write_daily_status(sync, run_id, group):
                        daily_state.mark_team_task_status(
                            self._daily_team_id(group),
                            self.daily_team_task_name,
                            "failed",
                            error=message,
                            target=50 if sync.event_mode else config.battle_count,
                        )
                    self._refresh_status_report(status_report, daily_state)
                except Exception as report_exc:
                    logger.warning(
                        "Cannot update MultiAccountEvo desktop status report: %s",
                        report_exc.__class__.__name__,
                    )
            self._notify_failure(group, role, message)
            self.set_next_run(
                self.task_name,
                target=datetime.now() + timedelta(minutes=10),
                server=False,
            )
            if isinstance(exc, MultiAccountEvoSyncError):
                raise RequestHumanTakeover(message) from exc
            raise RequestHumanTakeover(f"MultiAccountEvo: {message}") from exc

    @staticmethod
    def _is_recoverable_stall(exc: Exception) -> bool:
        return isinstance(exc, (
            TeamStallError, GameStuckError, GameTooManyClickError,
            GameNotRunningError, GamePageUnknownError, GameBugError,
            OcrUnavailableError, ImageFrameExpiredError,
        ))

    def _run_prebattle_session(self, config, sync, run_id, group, role, account, checkpoint_key):
        """切号和等待就绪时允许有限换代；进入嵌入式战斗流程后保留旧执行段隔离。"""
        deadline = time.monotonic() + config.sync_timeout_seconds
        run_date = date.today().isoformat()
        verified = False
        rejoined = 0
        self._team_group_entered = False
        self._team_bound_session = (group, run_id)
        while True:
            if time.monotonic() >= deadline:
                raise SyncTimeoutError("等待本组启动就绪超时")
            try:
                if verified:
                    if not self._verify_courtyard_character(account):
                        raise SyncStateError("重新接入前未确认当前账号庭院，停止本组")
                else:
                    result = AccountSwitcher(
                        self.config, self.device, max_attempts=3, retry_delay=2,
                        timeout=max(.01, deadline-time.monotonic()),
                        home_verifier=self._verify_courtyard_character, fast=True,
                    ).ensure_account(account)
                    if not result.success:
                        raise RuntimeError(f"account switch failed for group {group}: {result.error_code.value}")
                    verified = True
                sync.update_role(run_id, group, role, "ocr_done", character=account.character)
                sync.update_role(run_id, group, role, "ready", character=account.character)
                sync.wait_all_ready(run_id, group, deadline=deadline)
                state = self._run_group_with_recovery(config, sync, run_id, group, role, account)
                return run_id, state
            except SessionReplacedError:
                if role == "leader" or self._team_group_entered or rejoined >= 2:
                    raise
                logger.warning("队长会话已更换，当前组尚未开战，等待队长就绪后重新核验接入")
                state = sync.wait_for_session(run_date, exclude_run_id=run_id, deadline=deadline)
                if (date.today().isoformat() != run_date or state["complete"]
                        or state["current_group"] != group or state.get("checkpoint_key") != checkpoint_key
                        or state["group_count"] != config.group_count or state["battle_count"] != config.battle_count
                        or (state.get("group_start", 1), state.get("group_end", config.group_count))
                        != (config.group_start, config.group_end)):
                    raise SyncStateError("新会话的日期、账号身份、组号或范围不同，禁止重新接入")
                run_id = state["run_id"]
                self._team_bound_session = (group, run_id)
                rejoined += 1

    def _run_group_with_recovery(self, config, sync, run_id, group, role, account) -> dict:
        """只重入当前组；真正成功前不写每日完成状态或推进账号组。"""
        identity = (run_id, group)
        if getattr(self, "_image_retry_group", None) != identity:
            self._image_retry_group = identity
            self._image_read_retries = 0
        while True:
            try:
                ready = sync.wait_all_ready(run_id, group)
                epoch = sync.recovery_epoch(ready)
                friends = []
                evo_role = UserStatus.MEMBER
                if role == "leader":
                    friends = [ready["roles"][key]["character"] for key in ROLES[1:]]
                    if not all(friends):
                        raise ValueError("member character name is missing from READY state")
                    evo_role = UserStatus.LEADER
                self._team_control_check = lambda: sync.assert_active(
                    run_id, group, epoch=epoch, max_age=sync.control_check_interval,
                )
                try:
                    segment = (sync.begin_battle_segment(run_id, group, epoch)
                               if ready.get("checkpoint_key") else None)
                    remaining = segment["remaining"] if segment is not None else config.battle_count
                    completed = 0
                    if ready.get("event_mode"):
                        node = ready.get("event_groups", {}).get(str(group), {})
                        self._event_segment = {
                            "sync": sync, "run_id": run_id, "group": group, "epoch": epoch, "role": role,
                            "floor": min(segment["bases"].values()), "remaining": remaining, "completed": 0,
                            "start": config.multi_account_evo_config.event_ocr_start,
                            "interval": config.multi_account_evo_config.event_ocr_interval,
                            "reached": node.get("roles", {}).get(role, {}).get("reached", False),
                            "pending": any((item.get("run_id") != run_id or item.get("epoch") != epoch)
                                           and not item.get("superseded")
                                           and set(item.get("ready", [])) != set(ROLES)
                                           for item in node.get("samples", {}).values()),
                        }
                        self._event_stop = event_complete(ready, group)
                        if not remaining and not self._event_stop:
                            raise EventGoalError("刷场保护上限已到，门票尚未全部确认")
                        self._refresh_event_report()

                    def checkpoint():
                        nonlocal completed
                        state = sync.record_battle_progress(run_id, group, epoch, role, completed + 1)
                        completed += 1
                        if getattr(self, "_event_segment", None) is not None:
                            self._event_segment["completed"] = completed
                            if completed % 10 == 0 and role == "leader":
                                self._refresh_event_report()
                        logger.info("Battle checkpoint: group=%s role=%s completed=%s/%s segment=%s/%s",
                                    group, role, state["battle_progress"][str(group)][role],
                                    config.battle_count, completed, remaining)

                    self._team_battle_checkpoint = checkpoint if segment is not None else None
                    sync.update_role(run_id, group, role, "running", character=account.character, epoch=epoch)
                    if segment is not None:
                        logger.info("Resume battles: group=%s role=%s confirmed=%s remaining=%s",
                                    group, role, segment["bases"][role], remaining)
                    success = True
                    if remaining and not (ready.get("event_mode") and self._event_stop):
                        self._team_group_entered = True
                        success = self.run_embedded(
                            user_status=evo_role, limit_count=remaining,
                            kirin_type=config.kirin_type, layer=config.layer,
                            friend_list=friends, redact_sensitive_logs=True,
                            abort_check=lambda: self._run_embedded_abort_check(run_id, group, sync),
                        )
                    if not success or (ready.get("event_mode") and not self._event_stop) or (
                        not ready.get("event_mode") and segment is not None and completed != remaining
                    ):
                        raise TeamStallError(f"embedded EvoZone failed for group {group}")
                    sync.update_role(run_id, group, role, "done", character=account.character, epoch=epoch)
                    # 已提前完成的成员也留在此处响应恢复，不能独自退出下一轮协作。
                    if role == "leader":
                        return sync.wait_all_done(run_id, group, epoch=epoch)
                    return sync.wait_for_advance(run_id, group)
                finally:
                    self._event_segment = None
                    self._team_battle_checkpoint = None
                    self._team_control_check = None
            except RecoveryRequested as exc:
                self._recover_current_group(sync, run_id, group, role, account, exc.epoch)
            except Exception as exc:
                if not self._is_recoverable_stall(exc):
                    raise
                if isinstance(exc, OcrUnavailableError):
                    reason = f'OCR_UNAVAILABLE: {exc}'
                elif isinstance(exc, ImageServiceUnavailable):
                    reason = f'IMAGE_UNAVAILABLE: {exc}'
                else:
                    reason = str(exc)
                state = sync.request_recovery(
                    run_id, group, role, reason, max_attempts=self.auto_recovery_attempts,
                )
                self._recover_current_group(
                    sync, run_id, group, role, account, sync.recovery_epoch(state),
                )

    def _recover_current_group(self, sync, run_id, group, role, account, epoch) -> None:
        started = time.monotonic()
        deadline = started + sync.timeout

        def check():
            if time.monotonic() - started >= sync.timeout:
                raise SyncTimeoutError(f"game recovery timeout for group {group}")
            sync.assert_recovering(run_id, group, epoch, deadline=deadline,
                                   max_age=sync.control_check_interval)

        self._team_control_check = check
        try:
            logger.warning("MultiAccountEvo recovery: group=%s epoch=%s role=%s pause", group, epoch, role)
            sync.acknowledge_recovery(run_id, group, epoch, role, "paused")
            sync.wait_recovery_stage(run_id, group, epoch, "paused", deadline=deadline)
            recovery = sync.assert_recovering(run_id, group, epoch, deadline=deadline)
            if recovery['recovery'].get('reason', '').startswith('OCR_UNAVAILABLE:'):
                # 先等共享 OCR 就绪，再允许原有整组游戏恢复；服务不恢复则不重启游戏。
                wait_for_ocr_recovery(deadline=deadline, check=check)
            if recovery['recovery'].get('reason', '').startswith('IMAGE_UNAVAILABLE:'):
                # 图像服务仍不可用时重启游戏无法解决问题，先等待健康响应。
                wait_for_image_recovery(deadline=deadline, check=check)
            # 按队长、队员一、队员二顺序重启，避免同时登录占用识别服务。
            sync.wait_recovery_stage(
                run_id, group, epoch, "restarted", ROLES[:ROLES.index(role)], deadline=deadline,
            )
            check()
            logger.warning("MultiAccountEvo recovery: group=%s epoch=%s role=%s restart game", group, epoch, role)
            GroupGameRestart(self.config, self.device, check).app_restart()
            check()
            if not self._verify_courtyard_character(account):
                raise ScriptError("character verification failed after automatic game restart")
            check()
            sync.acknowledge_recovery(run_id, group, epoch, role, "restarted")
            sync.wait_recovery_stage(run_id, group, epoch, "restarted", deadline=deadline)
            if role == "leader":
                check()
                sync.finish_recovery(run_id, group, epoch, role)
            else:
                sync.wait_recovery_finished(run_id, group, epoch, deadline=deadline)
            logger.warning("MultiAccountEvo recovery: group=%s epoch=%s restart current group", group, epoch)
        finally:
            self._team_control_check = None
