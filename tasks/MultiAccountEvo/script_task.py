from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from module.exception import RequestHumanTakeover, TaskEnd
from module.logger import logger
from module.multi_account.account import Account
from module.multi_account.account_switcher import AccountSwitcher
from module.multi_account.courtyard_verifier import CourtyardCharacterVerifierMixin
from module.multi_account.daily_state import DailyStateManager
from module.multi_account.status_report import MultiAccountEvoStatusReport
from module.ocr.rpc import set_ocr_logging_enabled
from tasks.Component.GeneralBattle.assets import GeneralBattleAssets
from tasks.Component.GeneralBattle.general_battle import BattleAction
from tasks.Component.GeneralInvite.config_invite import FindMode
from tasks.EvoZone.config import UserStatus
from tasks.EvoZone.script_task import ScriptTask as EvoZoneScriptTask
from tasks.GameUi.default_pages import page_battle_result, page_reward, random_click
from tasks.MultiAccountEvo.config import MultiAccountEvoRole
from tasks.MultiAccountEvo.sync import MultiAccountEvoSync, MultiAccountEvoSyncError


class ScriptTask(EvoZoneScriptTask, CourtyardCharacterVerifierMixin):
    task_name = "MultiAccountEvo"
    daily_team_task_name = "multi_account_evo"
    switch_instance_order = ("oas3", "oas4", "oas5")
    # The friend-list OCR is slow (~20s for two friends), so give the re-invite
    # timer enough headroom to avoid re-opening the invite panel right after a
    # completed invite.
    invite_retry_seconds_first: float = 40.0
    invite_retry_seconds: float = 40.0

    def appear_then_click(self, target, *args, **kwargs):
        """Disable the obsolete lower room keepalive slot for this task only."""
        if target is self.I_GI_EMOJI_2:
            logger.info('Skip legacy lower room keepalive in MultiAccountEvo')
            return False
        return super().appear_then_click(target, *args, **kwargs)

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
            click_x, click_y = self._random_point_in_area(select_area)
            self.device.click(x=click_x, y=click_y, control_name=rule.name)
            if self._wait_selected_appear(pre_cnt):
                return True
        logger.warning('Find friend [redacted] but failed to select')
        return False

    def appear_accept(self) -> bool:
        """Accept only the normal team invitation in this task."""
        return self.appear(self.I_I_ACCEPT)

    def check_then_accept(self) -> bool:
        """Accept this task's invitation using the safe control centre."""
        if not self.appear_accept():
            return False
        logger.info('Click accept')
        while True:
            self.screenshot()
            if self.is_in_room():
                return True
            if self.appear(GeneralBattleAssets.I_EXIT):
                return False
            if self.appear_then_click(self.I_I_NO_DEFAULT, interval=1):
                continue
            if self.appear_then_click(self.I_GI_SURE, interval=1):
                continue
            if self.appear_then_click(self.I_I_ACCEPT_DEFAULT, interval=1):
                continue
            if self.appear(self.I_I_ACCEPT):
                x, y, width, height = self.I_I_ACCEPT.roi_front
                self.device.click(x=x + width // 2, y=y + height // 2)
                time.sleep(1)

    @staticmethod
    def _multi_account_settlement_click():
        """Keep this task's settlement clicks away from the new left sidebar."""
        return random_click(ltrb=(False, False, True, False))

    def _handle_result(self, context, config) -> BattleAction:
        """Handle this task's settlement without using the common left area."""
        context.reward_no_battle_ts = None
        context.is_win = not self.appear(self.I_FALSE, threshold=0.8)
        if context.last_page != page_battle_result:
            self.device.click_record_clear()
        self.click(self._multi_account_settlement_click(), interval=0.8)
        return BattleAction.CONTINUE

    def _handle_reward(self, context, config) -> BattleAction:
        """Handle this task's reward page without using the common left area."""
        if self.active_evo_zone.evo_zone_config.user_status == UserStatus.LEADER and \
                self.check_and_invite(self.active_evo_zone.invite_config.default_invite):
            return BattleAction.CONTINUE
        context.reward_no_battle_ts = None
        context.is_win = True
        self.appear_then_click(self.I_GB_SKIN_CONFIRM, interval=0.8)
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
                    "battle_count": task.get("multi_account_evo_config", {}).get("battle_count", 20),
                    "evo_zone_enabled": data.get("evo_zone", {}).get("scheduler", {}).get("enable", False),
                    "accounts": [
                        {
                            "account": (task.get(f"account_list_{index}") or {}).get("account", ""),
                            "related_account": (task.get(f"account_list_{index}") or {}).get("related_account", ""),
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
        conflicting = [peer["name"] for peer in peers if peer["evo_zone_enabled"]]
        if conflicting:
            raise ValueError("EvoZone and MultiAccountEvo cannot both be enabled in the same config")
        actual_names = {peer["name"].lower() for peer in peers}
        if actual_names != set(self.switch_instance_order):
            raise ValueError("enabled MultiAccountEvo configs must be oas3, oas4 and oas5")
        self._validate_related_account_groups(peers)
        return peers

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
            lambda: sync.assert_active(run_id, group)
        )

    def run(self) -> bool:
        ocr_logging_enabled = bool(self.config.global_game.ocr.save_ocr_log)
        set_ocr_logging_enabled(False)
        try:
            return self._run_multi_account_evo()
        finally:
            set_ocr_logging_enabled(ocr_logging_enabled)

    def _run_multi_account_evo(self) -> bool:
        config = self.config.multi_account_evo
        role = config.role.value
        sync = MultiAccountEvoSync(
            Path.cwd() / "config",
            timeout=config.sync_timeout_seconds,
        )
        daily_state = DailyStateManager(
            Path.cwd() / "config",
            recover_instances=set(),
        )
        status_report = MultiAccountEvoStatusReport(Path.cwd() / "config")
        self._refresh_status_report(status_report, daily_state)
        run_id = None
        group = None

        try:
            config.validate_runtime_accounts()
            self._validate_peer_configs()

            if config.role == MultiAccountEvoRole.LEADER:
                state = sync.start_or_resume(config.group_count, config.battle_count)
            else:
                state = sync.wait_for_session(date.today().isoformat())

            if state["complete"]:
                logger.info("MultiAccountEvo is already complete for today")
                self._finish_successfully()
            if state["group_count"] != config.group_count:
                raise ValueError("shared group_count does not match local config")
            if state["battle_count"] != config.battle_count:
                raise ValueError("shared battle_count does not match local config")

            run_id = state["run_id"]
            group = int(state["current_group"])
            while group <= config.group_count:
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
                    daily_state.mark_team_task_status(
                        team_id,
                        self.daily_team_task_name,
                        "running",
                        target=config.battle_count,
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
                switch_result = AccountSwitcher(
                    self.config,
                    self.device,
                    max_attempts=3,
                    retry_delay=2,
                    timeout=config.sync_timeout_seconds,
                    home_verifier=self._verify_courtyard_character,
                    fast=True,
                ).ensure_account(
                    managed_account,
                )
                if not switch_result.success:
                    raise RuntimeError(
                        f"account switch failed for group {group}: {switch_result.error_code.value}"
                    )

                # Release the next instance only after the courtyard character
                # has been verified, not merely after selecting a saved login.
                sync.update_role(
                    run_id,
                    group,
                    role,
                    "ocr_done",
                    character=account.character,
                )

                sync.update_role(
                    run_id,
                    group,
                    role,
                    "ready",
                    character=account.character,
                )
                ready_state = sync.wait_all_ready(run_id, group)
                friend_names = []
                evo_role = UserStatus.MEMBER
                if config.role == MultiAccountEvoRole.LEADER:
                    friend_names = [
                        ready_state["roles"]["member_1"]["character"],
                        ready_state["roles"]["member_2"]["character"],
                    ]
                    if not all(friend_names):
                        raise RuntimeError("member character name is missing from READY state")
                    evo_role = UserStatus.LEADER

                sync.update_role(
                    run_id,
                    group,
                    role,
                    "running",
                    character=account.character,
                )
                success = self.run_embedded(
                    user_status=evo_role,
                    limit_count=config.battle_count,
                    kirin_type=config.kirin_type,
                    layer=config.layer,
                    friend_list=friend_names,
                    redact_sensitive_logs=True,
                    abort_check=lambda: self._run_embedded_abort_check(
                        run_id, group, sync
                    ),
                )
                if not success:
                    raise RuntimeError(f"embedded EvoZone failed for group {group}")

                sync.update_role(
                    run_id,
                    group,
                    role,
                    "done",
                    character=account.character,
                )
                if config.role == MultiAccountEvoRole.LEADER:
                    sync.wait_all_done(run_id, group)
                    # Persist completion before advancing. If the process exits
                    # after this write, today's next run will safely skip the
                    # already completed account group.
                    daily_state.update_team_progress(
                        team_id,
                        self.daily_team_task_name,
                        config.battle_count,
                        target=config.battle_count,
                    )
                    self._refresh_status_report(status_report, daily_state)
                    state = sync.advance(run_id, group, role)
                else:
                    state = sync.wait_for_advance(run_id, group)
                if state["complete"]:
                    break
                group = int(state["current_group"])

            self._finish_successfully()
        except TaskEnd:
            raise
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            logger.error("MultiAccountEvo failed: %s", message)
            if run_id is not None and group is not None:
                sync.fail(run_id, group, role, message)
                try:
                    daily_state.mark_team_task_status(
                        self._daily_team_id(group),
                        self.daily_team_task_name,
                        "failed",
                        error=message,
                        target=config.battle_count,
                    )
                    self._refresh_status_report(status_report, daily_state)
                except Exception as report_exc:
                    logger.warning(
                        "Cannot update MultiAccountEvo desktop status report: %s",
                        report_exc.__class__.__name__,
                    )
            self.set_next_run(
                self.task_name,
                target=datetime.now() + timedelta(minutes=10),
                server=False,
            )
            if isinstance(exc, MultiAccountEvoSyncError):
                raise RequestHumanTakeover(message) from exc
            raise RequestHumanTakeover(f"MultiAccountEvo: {message}") from exc
