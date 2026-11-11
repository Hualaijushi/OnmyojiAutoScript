import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from module.exception import TaskEnd
from module.multi_account.account import Account
from module.multi_account.daily_state import DailyStateManager
from module.multi_account.status_report import MultiAccountEvoStatusReport
from tasks.Component.GeneralInvite.general_invite import GeneralInvite
from tasks.EvoZone.config import EvoZone, KirinType, Layer, UserStatus
from tasks.EvoZone.script_task import ScriptTask as EvoZoneScriptTask
from tasks.GameUi.assets import GameUiAssets
from tasks.GameUi.default_pages import page_team
from tasks.GameUi.matcher import AnyMatcher, collect_rule_images
from tasks.GameUi.page import page_main
from tasks.MultiAccountEvo.config import MultiAccountEvo
from tasks.MultiAccountEvo.sync import (
    MultiAccountEvoSync,
    PeerFailedError,
    RunChangedError,
    SyncStateError,
    SyncTimeoutError,
)
from tasks.MultiAccountEvo.script_task import ScriptTask as MultiAccountEvoScriptTask
from module.config.config_model import ConfigModel
from module.server.config_manager import ConfigManager


class MultiAccountEvoConfigTest(unittest.TestCase):
    def test_dynamic_account_fields_round_trip(self):
        source = MultiAccountEvo().model_dump()
        self.assertEqual("雷麒麟", source["multi_account_evo_config"]["kirin_type"])
        self.assertEqual("拾层", source["multi_account_evo_config"]["layer"])
        self.assertEqual(18, len([key for key in source if key.startswith("account_list_")]))
        self.assertNotIn("account_list", source)
        self.assertFalse(source["account_list_1"]["apple_or_android"])
        self.assertTrue(source["account_list_10"]["apple_or_android"])
        self.assertIn("related_account", source["account_list_1"])
        restored = MultiAccountEvo(**json.loads(json.dumps(source, default=str)))
        self.assertEqual(source, restored.model_dump())

    def test_dynamic_account_fields_keep_values_for_config_api(self):
        config = MultiAccountEvo()
        config.account_list[0].character = "character-secret"
        config.account_list[0].svr = "server-secret"
        config.account_list[0].account = "login-secret"
        config.account_list[0].account_alias = "alias-secret"
        config.account_list[0].related_account = "oas3:a#oas4:b#oas5:c"
        visible = config.model_dump(context={"hide": True})["account_list_1"]
        self.assertEqual(
            {
                "character": "character-secret",
                "svr": "server-secret",
                "account": "login-secret",
                "account_alias": "alias-secret",
            },
            {key: visible[key] for key in ("character", "svr", "account", "account_alias")},
        )
        self.assertEqual("oas3:a#oas4:b#oas5:c", visible["related_account"])

    def test_config_model_save_reload_preserves_dynamic_accounts(self):
        repository_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "config").mkdir()
            shutil.copy2(repository_root / "config" / "template.json", temp_path / "config" / "test.json")
            previous_cwd = Path.cwd()
            try:
                os.chdir(temp_path)
                model = ConfigModel("test")
                model.save()
                restored = ConfigModel("test")
            finally:
                os.chdir(previous_cwd)
            dumped = restored.model_dump()["multi_account_evo"]
            self.assertEqual(18, len([key for key in dumped if key.startswith("account_list_")]))
            self.assertNotIn("account_list", dumped)

    def test_config_api_recognizes_task_and_exposes_accounts(self):
        model = ConfigModel("template")
        model.multi_account_evo.account_list[0].character = "visible-character"
        model.multi_account_evo.account_list[0].svr = "visible-server"
        model.multi_account_evo.account_list[0].account = "visible-account"
        model.multi_account_evo.account_list[0].account_alias = "visible-alias"
        model.multi_account_evo.account_list[0].related_account = "oas3:a#oas4:b#oas5:c"
        data = model.script_task("MultiAccountEvo")
        self.assertIn("multi_account_evo_config", data)
        self.assertEqual(18, len([key for key in data if key.startswith("account_list_")]))
        sensitive_values = {
            item["name"]: item["value"]
            for item in data["account_list_1"]
            if item["name"] in {"character", "svr", "account", "account_alias"}
        }
        self.assertEqual(
            {
                "character": "visible-character",
                "svr": "visible-server",
                "account": "visible-account",
                "account_alias": "visible-alias",
            },
            sensitive_values,
        )
        related_value = next(
            item["value"] for item in data["account_list_1"] if item["name"] == "related_account"
        )
        self.assertEqual("oas3:a#oas4:b#oas5:c", related_value)


class MultiAccountEvoTwentyGroupsTest(unittest.TestCase):
    @staticmethod
    def _source():
        return {
            "multi_account_evo_config": {"group_count": 20, "ios_count": 10},
            **{
                f"account_list_{index}": {
                    "character": f"角色{index}", "svr": "测试区",
                    "account": f"test{index}@example.com",
                    "apple_or_android": index > 10,
                    "related_account": "oas3:a#oas4:b#oas5:c",
                }
                for index in range(1, 21)
            },
        }

    def test_twenty_accounts_round_trip_and_validate(self):
        source = self._source()
        config = MultiAccountEvo(**source)
        config.validate_runtime_accounts()
        restored = MultiAccountEvo(**json.loads(json.dumps(config.model_dump(), default=str)))
        self.assertEqual(20, len(restored.account_list))
        self.assertEqual("角色20", restored.account_list[19].character)
        self.assertEqual(config.model_dump(), restored.model_dump())

    def test_last_group_missing_fields_are_rejected(self):
        source = self._source()
        source["account_list_20"]["character"] = ""
        with self.assertRaisesRegex(ValueError, "account_list_20 is missing"):
            MultiAccountEvo(**source).validate_runtime_accounts()

    def test_nineteenth_group_platform_is_checked(self):
        source = self._source()
        source["account_list_19"]["apple_or_android"] = False
        with self.assertRaisesRegex(ValueError, "account_list_19 must be Android"):
            MultiAccountEvo(**source).validate_runtime_accounts()

    def test_twenty_groups_require_twenty_slots(self):
        source = self._source()
        del source["account_list_20"]
        with self.assertRaisesRegex(ValueError, "at least 20 accounts"):
            MultiAccountEvo(**source).validate_runtime_accounts()

    def test_out_of_range_keeps_existing_default_fallback(self):
        source = self._source()
        source["multi_account_evo_config"]["group_count"] = 21
        config = MultiAccountEvo(**source)
        self.assertEqual(18, config.group_count)
        from tasks.MultiAccountEvo.config import MultiAccountEvoConfig
        self.assertEqual(20, MultiAccountEvoConfig.model_json_schema()["properties"]["group_count"]["maximum"])

    def test_all_three_rotation_managers_include_new_accounts(self):
        from module.multi_account.account_manager import AccountManager
        config = MultiAccountEvo(**self._source())
        for instance, prefix in (("oas3", "A"), ("oas4", "B"), ("oas5", "C")):
            with self.subTest(instance=instance):
                accounts = AccountManager(instance, config, order="1-20", enabled="1-20").get_enabled_accounts()
                self.assertEqual(20, len(accounts))
                self.assertEqual(f"{prefix}10", accounts[9].account_id)
                self.assertFalse(accounts[9].apple_or_android)
                self.assertEqual(f"{prefix}20", accounts[-1].account_id)
                self.assertTrue(accounts[-1].apple_or_android)

    def test_config_api_and_saved_reload_keep_twenty_accounts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            model = ConfigModel(config_name="twenty", multi_account_evo=self._source())
            previous = Path.cwd()
            try:
                os.chdir(root)
                model.save()
                restored = ConfigModel("twenty")
                api = restored.script_task("MultiAccountEvo")
                self.assertIn("account_list_20", api)
                self.assertEqual(20, restored.multi_account_evo.group_count)
                restored.multi_account_evo.validate_runtime_accounts()
                self.assertEqual(model.multi_account_evo.model_dump(), restored.multi_account_evo.model_dump())
            finally:
                os.chdir(previous)

    def test_twenty_groups_sync_reaches_final_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            sync = MultiAccountEvoSync(directory, timeout=0.2, poll_interval=0.001)
            state = sync.start_or_resume(20, 20, run_date="2026-10-26")
            for group in range(1, 21):
                self.assertEqual(group, state["current_group"])
                for role in ("leader", "member_1", "member_2"):
                    sync.update_role(state["run_id"], group, role, "done", character=role)
                state = sync.advance(state["run_id"], group, "leader")
                self.assertEqual(group == 20, state["complete"])
            self.assertEqual(21, sync.read()["current_group"])

    def test_peer_validation_covers_the_twentieth_related_group(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configs = root / "config"
            configs.mkdir()
            helper = MultiAccountEvoPeerConfigTest()
            for index, role in enumerate(("leader", "member_1", "member_2"), 3):
                helper._write_peer(configs, f"oas{index}", role, group_count=20)
            previous = Path.cwd()
            try:
                os.chdir(root)
                task = object.__new__(MultiAccountEvoScriptTask)
                self.assertEqual(3, len(task._validate_peer_configs()))
                path = configs / "oas5.json"
                data = json.loads(path.read_text(encoding="utf-8"))
                data["multi_account_evo"]["account_list_20"]["related_account"] = "oas3:wrong#oas4:wrong#oas5:wrong"
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "account group 20 related_account mismatch"):
                    task._validate_peer_configs()
            finally:
                os.chdir(previous)


class EvoZoneEmbeddedTest(unittest.TestCase):
    def test_embedded_return_to_main_uses_direct_click_with_four_second_interval(self):
        task = object.__new__(EvoZoneScriptTask)
        task._embedded_evo_zone = EvoZone()
        calls = []
        task.ui_click = lambda click, stop, interval=1: calls.append((click, stop, interval))
        task.goto_page = lambda page: self.fail("embedded return must not use navigator")

        task._return_to_main_after_run()

        self.assertEqual(1, len(calls))
        self.assertEqual(4, calls[0][2])

    def test_direct_evozone_return_keeps_existing_navigation(self):
        task = object.__new__(EvoZoneScriptTask)
        task._embedded_evo_zone = None
        calls = []
        task.goto_page = lambda page: calls.append(page)
        task.ui_click = lambda *args, **kwargs: self.fail("direct task must keep navigator")

        task._return_to_main_after_run()

        self.assertEqual(1, len(calls))

    def test_direct_run_still_updates_evozone_scheduler(self):
        task = object.__new__(EvoZoneScriptTask)
        task._run_core = lambda: True
        calls = []
        task.set_next_run = lambda *args, **kwargs: calls.append((args, kwargs))
        with self.assertRaises(TaskEnd):
            task.run()
        self.assertEqual("EvoZone", calls[0][0][0])
        self.assertTrue(calls[0][1]["success"])

    def test_embedded_overrides_do_not_change_persisted_config(self):
        original = EvoZone()
        original.evo_zone_config.user_status = UserStatus.ALONE
        original.evo_zone_config.limit_count = 7
        original.evo_zone_config.kirin_type = KirinType.FIREKIRIN
        original.evo_zone_config.layer = Layer.ONE
        original.invite_config.friend_list = "original"

        task = object.__new__(EvoZoneScriptTask)
        task.config = type("Config", (), {"evo_zone": original})()
        observed = {}

        def fake_run_core():
            observed["status"] = task.active_evo_zone.evo_zone_config.user_status
            observed["count"] = task.active_evo_zone.evo_zone_config.limit_count
            observed["kirin_type"] = task.active_evo_zone.evo_zone_config.kirin_type
            observed["layer"] = task.active_evo_zone.evo_zone_config.layer
            observed["friends"] = task.active_evo_zone.invite_config.friend_list
            task.current_count = 20
            return True

        task._run_core = fake_run_core
        self.assertTrue(
            task.run_embedded(
                user_status=UserStatus.LEADER,
                limit_count=20,
                kirin_type=KirinType.WATERKIRIN,
                layer=Layer.TEN,
                friend_list=["member-a", "member-b"],
            )
        )
        self.assertEqual(UserStatus.LEADER, observed["status"])
        self.assertEqual(20, observed["count"])
        self.assertEqual(KirinType.WATERKIRIN, observed["kirin_type"])
        self.assertEqual(Layer.TEN, observed["layer"])
        self.assertEqual("member-a\nmember-b", observed["friends"])
        self.assertEqual(UserStatus.ALONE, original.evo_zone_config.user_status)
        self.assertEqual(7, original.evo_zone_config.limit_count)
        self.assertEqual(KirinType.FIREKIRIN, original.evo_zone_config.kirin_type)
        self.assertEqual(Layer.ONE, original.evo_zone_config.layer)
        self.assertEqual("original", original.invite_config.friend_list)


class MultiAccountEvoSyncTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.sync = MultiAccountEvoSync(self.temp.name, timeout=0.08, poll_interval=0.005)

    def tearDown(self):
        self.temp.cleanup()

    def test_ready_done_advance_and_complete(self):
        state = self.sync.start_or_resume(2, 20, run_date="2026-08-16")
        run_id = state["run_id"]
        for role in ("leader", "member_1", "member_2"):
            self.sync.update_role(run_id, 1, role, "ready", character=f"{role}-character")
        ready = self.sync.wait_all_ready(run_id, 1)
        self.assertEqual("member_1-character", ready["roles"]["member_1"]["character"])
        for role in ("leader", "member_1", "member_2"):
            self.sync.update_role(run_id, 1, role, "done", character=f"{role}-character")
        with self.assertRaises(SyncStateError):
            self.sync.advance(run_id, 1, "member_1")
        state = self.sync.advance(run_id, 1, "leader")
        self.assertEqual(2, state["current_group"])
        for role in ("leader", "member_1", "member_2"):
            self.sync.update_role(run_id, 2, role, "done", character=f"{role}-character")
        state = self.sync.advance(run_id, 2, "leader")
        self.assertTrue(state["complete"])
        self.assertEqual(3, state["current_group"])

        persisted = json.loads(Path(self.sync.state_path).read_text(encoding="utf-8"))
        serialized = json.dumps(persisted, ensure_ascii=False).lower()
        for forbidden in ("password", "token", "cookie", "account_alias"):
            self.assertNotIn(forbidden, serialized)

    def test_leader_can_skip_group_completed_in_daily_state(self):
        state = self.sync.start_or_resume(2, 20, run_date="2026-08-16")
        state = self.sync.skip_completed_group(state["run_id"], 1, "leader")
        self.assertEqual(2, state["current_group"])
        self.assertFalse(state["complete"])
        self.assertTrue(all(item["status"] == "pending" for item in state["roles"].values()))
        state = self.sync.skip_completed_group(state["run_id"], 2, "leader")
        self.assertEqual(3, state["current_group"])
        self.assertTrue(state["complete"])

    def test_member_cannot_skip_completed_group(self):
        state = self.sync.start_or_resume(2, 20, run_date="2026-08-16")
        with self.assertRaisesRegex(SyncStateError, "only leader"):
            self.sync.skip_completed_group(state["run_id"], 1, "member_1")

    def test_wait_roles_ready_supports_ordered_account_switching(self):
        state = self.sync.start_or_resume(2, 20, run_date="2026-08-16")
        run_id = state["run_id"]
        self.sync.update_role(run_id, 1, "leader", "ocr_done", character="leader-character")
        ready = self.sync.wait_roles_ready(run_id, 1, ("leader",))
        self.assertEqual("ocr_done", ready["roles"]["leader"]["status"])
        with self.assertRaises(SyncTimeoutError):
            self.sync.wait_roles_ready(run_id, 1, ("leader", "member_1"))

    def test_peer_failure_is_reported(self):
        state = self.sync.start_or_resume(18, 20, run_date="2026-08-16")
        self.sync.fail(state["run_id"], 1, "member_1", "simulated failure")
        with self.assertRaisesRegex(PeerFailedError, "member_1: simulated failure"):
            self.sync.wait_all_ready(state["run_id"], 1)

    def test_wait_has_timeout(self):
        state = self.sync.start_or_resume(18, 20, run_date="2026-08-16")
        with self.assertRaises(SyncTimeoutError):
            self.sync.wait_all_ready(state["run_id"], 1)

    def test_old_run_id_is_rejected_after_leader_restart(self):
        old_state = self.sync.start_or_resume(18, 20, run_date="2026-08-16")
        new_state = self.sync.start_or_resume(18, 20, run_date="2026-08-16")
        self.assertNotEqual(old_state["run_id"], new_state["run_id"])
        with self.assertRaises(RunChangedError):
            self.sync.update_role(old_state["run_id"], 1, "member_1", "ready", character="member")

    def test_member_ignores_failed_session_until_leader_restarts(self):
        old_state = self.sync.start_or_resume(18, 20, run_date="2026-08-16")
        self.sync.fail(old_state["run_id"], 1, "leader", "old failure")
        observed = {}

        waiter = threading.Thread(
            target=lambda: observed.setdefault(
                "state", self.sync.wait_for_session(run_date="2026-08-16")
            )
        )
        waiter.start()
        time.sleep(0.02)
        new_state = self.sync.start_or_resume(18, 20, run_date="2026-08-16")
        waiter.join(timeout=0.2)

        self.assertFalse(waiter.is_alive())
        self.assertEqual(new_state["run_id"], observed["state"]["run_id"])

    def test_external_reads_wait_for_shared_state_lock(self):
        state = self.sync.start_or_resume(18, 20, run_date="2026-08-16")
        run_id = state["run_id"]
        for role in ("leader", "member_1", "member_2"):
            self.sync.update_role(run_id, 1, role, "ready", character=role)

        operations = (
            ("read", lambda: self.sync.read()),
            ("assert_active", lambda: self.sync.assert_active(run_id, 1)),
            ("wait_all_ready", lambda: self.sync.wait_all_ready(run_id, 1)),
        )
        for name, operation in operations:
            with self.subTest(operation=name):
                started = threading.Event()
                finished = threading.Event()
                errors = []

                def run_read():
                    started.set()
                    try:
                        operation()
                    except Exception as exc:
                        errors.append(exc)
                    finally:
                        finished.set()

                with self.sync._lock():
                    reader = threading.Thread(target=run_read)
                    reader.start()
                    self.assertTrue(started.wait(timeout=0.1))
                    self.assertFalse(finished.wait(timeout=0.02))

                reader.join(timeout=0.2)
                self.assertFalse(reader.is_alive())
                self.assertFalse(errors)
                self.assertTrue(finished.is_set())


class MultiAccountEvoPeerConfigTest(unittest.TestCase):
    def _write_peer(self, directory: Path, name: str, role: str, *, group_count: int = 18, battle_count: int = 20):
        instances = ("oas3", "oas4", "oas5")
        data = {
            "multi_account_evo": {
                "scheduler": {"enable": True},
                "multi_account_evo_config": {
                    "role": role,
                    "group_count": group_count,
                    "battle_count": battle_count,
                },
                **{
                    f"account_list_{index}": {
                        "account": f"{name}-account-{index}",
                        "related_account": "#".join(
                            f"{instance}:{instance}-account-{index}" for instance in instances
                        ),
                    }
                    for index in range(1, group_count + 1)
                },
            },
            "evo_zone": {"scheduler": {"enable": False}},
        }
        (directory / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")

    def test_three_unique_matching_peers_are_accepted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            for index, role in enumerate(("leader", "member_1", "member_2"), start=3):
                self._write_peer(root / "config", f"oas{index}", role)
            previous_cwd = Path.cwd()
            try:
                os.chdir(root)
                MultiAccountEvoScriptTask._validate_peer_configs(object.__new__(MultiAccountEvoScriptTask))
            finally:
                os.chdir(previous_cwd)

    def test_related_account_mismatch_is_rejected_before_switching(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / "config"
            config_dir.mkdir()
            for index, role in enumerate(("leader", "member_1", "member_2"), start=3):
                self._write_peer(config_dir, f"oas{index}", role)
            oas4_path = config_dir / "oas4.json"
            data = json.loads(oas4_path.read_text(encoding="utf-8"))
            data["multi_account_evo"]["account_list_1"]["related_account"] = (
                "oas3:oas3-account-1#oas4:oas4-account-2#oas5:oas5-account-1"
            )
            oas4_path.write_text(json.dumps(data), encoding="utf-8")
            previous_cwd = Path.cwd()
            try:
                os.chdir(root)
                with self.assertRaisesRegex(ValueError, "account group 1 related_account mismatch in oas4"):
                    MultiAccountEvoScriptTask._validate_peer_configs(
                        object.__new__(MultiAccountEvoScriptTask)
                    )
            finally:
                os.chdir(previous_cwd)

    def test_duplicate_roles_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            for index, role in enumerate(("leader", "member_1", "member_1"), start=3):
                self._write_peer(root / "config", f"oas{index}", role)
            previous_cwd = Path.cwd()
            try:
                os.chdir(root)
                with self.assertRaisesRegex(ValueError, "roles must be unique"):
                    MultiAccountEvoScriptTask._validate_peer_configs(object.__new__(MultiAccountEvoScriptTask))
            finally:
                os.chdir(previous_cwd)

    def test_sync_state_file_is_hidden_from_config_lists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / "config"
            config_dir.mkdir()
            for name in ("template", "oas3", ".multi_account_evo_sync"):
                (config_dir / f"{name}.json").write_text("{}", encoding="utf-8")
            previous_cwd = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(["oas3"], ConfigManager.all_script_files())
                self.assertEqual(["template", "oas3"], ConfigManager.all_json_file())
            finally:
                os.chdir(previous_cwd)


class MultiAccountEvoCharacterVerificationTest(unittest.TestCase):
    def _task(self, detected_values: list[str], *, on_main: bool = True):
        task = object.__new__(MultiAccountEvoScriptTask)
        task.character_verify_interval = 0
        task.goto_page = lambda destination: on_main
        task.get_current_page = lambda: __import__(
            "tasks.GameUi.page", fromlist=["page_main"]
        ).page_main if on_main else object()
        task.screenshot = lambda: None
        task.device = type("Device", (), {"image": object()})()
        values = iter(detected_values)
        task.courtyard_character_ocr = type(
            "Ocr", (), {"ocr": lambda self, image: next(values)}
        )()
        return task

    @staticmethod
    def _account(character: str = "普信男孩146") -> Account:
        return Account(
            account_id="A03",
            instance="oas3",
            position=3,
            character=character,
            server="server",
            login_account="login",
        )

    def test_exact_courtyard_character_is_accepted(self):
        task = self._task([" 普信男孩146 "])
        self.assertTrue(task._verify_courtyard_character(self._account()))

    def test_first_ocr_frame_failure_then_success(self):
        account = self._account()
        task = self._task([None, account.character])
        self.assertTrue(task._verify_courtyard_character(account))

    def test_wrong_courtyard_character_is_rejected_after_bounded_retries(self):
        task = self._task(["普信男孩145"] * 3)
        self.assertFalse(task._verify_courtyard_character(self._account()))


    def test_navigation_recovers_to_courtyard_before_character_ocr(self):
        task = self._task([self._account().character])
        calls = []
        task.goto_page = lambda destination: calls.append(destination) or True

        self.assertTrue(task._verify_courtyard_character(self._account()))
        self.assertEqual([page_main], calls)

    def test_navigation_failure_skips_character_ocr(self):
        task = self._task([self._account().character], on_main=False)
        task.goto_page = lambda destination: False
        ocr_calls = []
        task.courtyard_character_ocr = type(
            "Ocr", (), {"ocr": lambda self, image: ocr_calls.append(image)}
        )()

        self.assertFalse(task._verify_courtyard_character(self._account()))
        self.assertEqual([], ocr_calls)


class MultiAccountEvoInviteRetryConfigTest(unittest.TestCase):
    def test_generic_invite_retry_intervals_are_unchanged(self):
        self.assertEqual(GeneralInvite.invite_retry_seconds_first, 20.0)
        self.assertEqual(GeneralInvite.invite_retry_seconds, 30.0)

    def test_multi_account_evo_uses_slower_reinvite_interval(self):
        self.assertEqual(MultiAccountEvoScriptTask.invite_retry_seconds_first, 40.0)
        self.assertEqual(MultiAccountEvoScriptTask.invite_retry_seconds, 40.0)

    def test_multi_account_evo_starts_retry_timer_after_initial_invite(self):
        task = object.__new__(MultiAccountEvoScriptTask)
        self.assertTrue(task.invite_retry_starts_after_initial_invite())
        self.assertFalse(GeneralInvite.invite_retry_starts_after_initial_invite(object()))


class MultiAccountEvoInviteOcrTest(unittest.TestCase):
    def test_batched_friend_class_ocr_reads_the_four_regions_in_screen_order(self):
        task = object.__new__(MultiAccountEvoScriptTask)
        image = object()
        task.device = SimpleNamespace(image=image)
        calls = []
        task.O_MAE_FRIEND_CLASS_BAR = SimpleNamespace(
            detect_and_ocr=lambda actual_image: calls.append(actual_image) or [
                SimpleNamespace(ocr_text="跨区", box=((310, 1), (330, 1), (330, 20), (310, 20))),
                SimpleNamespace(ocr_text="好友", box=((5, 1), (25, 1), (25, 20), (5, 20))),
                SimpleNamespace(ocr_text="寮友", box=((220, 1), (240, 1), (240, 20), (220, 20))),
                SimpleNamespace(ocr_text="最近", box=((120, 1), (140, 1), (140, 20), (120, 20))),
            ]
        )

        self.assertEqual(task._read_friend_classes(), ["好友", "最近", "寮友", "跨区"])
        self.assertEqual(calls, [image])


class TeamPageAnyRecognitionTest(unittest.TestCase):
    def test_team_page_has_second_marker_asset(self):
        self.assertEqual(
            GameUiAssets.I_CHECK_TEAM_2.file,
            "./tasks/GameUi/page/page_check_team_2.png",
        )

    def test_team_page_recognizer_accepts_either_marker(self):
        self.assertIsInstance(page_team.recognizer, AnyMatcher)
        images = collect_rule_images(page_team.recognizer)
        ids = {id(image) for image in images}
        self.assertIn(id(GameUiAssets.I_CHECK_TEAM), ids)
        self.assertIn(id(GameUiAssets.I_CHECK_TEAM_2), ids)


class MultiAccountEvoEmbeddedAbortTest(unittest.TestCase):
    def _task(self):
        records = []
        task = object.__new__(MultiAccountEvoScriptTask)
        task.device = type(
            "Device", (), {"stuck_record_add": lambda self, name: records.append(name)}
        )()
        return task, records

    def test_abort_check_arms_team_wait_long_wait_exemption(self):
        task, records = self._task()
        calls = []

        task._check_embedded_abort_with_team_wait(lambda: calls.append("checked"))

        self.assertEqual(["checked"], calls)
        self.assertEqual(["PREPARE_BEFORE_BATTLE"], records)

    def test_abort_check_propagates_sync_failure_without_arming(self):
        task, records = self._task()

        def fail():
            raise RuntimeError("abort")

        with self.assertRaisesRegex(RuntimeError, "abort"):
            task._check_embedded_abort_with_team_wait(fail)

        self.assertEqual([], records)

    def test_abort_check_wiring_survives_run_embedded_attribute_shadowing(self):
        task = object.__new__(MultiAccountEvoScriptTask)
        records = []
        sync_calls = []

        class FakeSync:
            control_check_interval = 1.0

            def assert_active(self, run_id, group, **kwargs):
                sync_calls.append((run_id, group))

        task.device = type(
            "Device",
            (),
            {"stuck_record_add": lambda self, name: records.append(name)},
        )()
        task.config = type("Config", (), {"evo_zone": EvoZone()})()

        def fake_run_core():
            task._check_embedded_abort()
            task.current_count = 20
            return True

        task._run_core = fake_run_core
        task.run_embedded(
            user_status=UserStatus.LEADER,
            limit_count=20,
            abort_check=lambda: task._run_embedded_abort_check(
                "run-1", 2, FakeSync()
            ),
        )
        self.assertEqual(sync_calls, [("run-1", 2)])
        self.assertEqual(["PREPARE_BEFORE_BATTLE"], records)


class MultiAccountEvoFailureNotificationTest(unittest.TestCase):
    def _task(self, enabled: bool):
        task = object.__new__(MultiAccountEvoScriptTask)
        config = MultiAccountEvo().multi_account_evo_config
        config.failure_notify_enable = enabled
        config.failure_pushplus_token = "test-token"
        task.config = SimpleNamespace(
            config_name="oas3",
            multi_account_evo=SimpleNamespace(multi_account_evo_config=config),
        )
        return task

    def test_disabled_notification_does_not_send(self):
        with patch("tasks.MultiAccountEvo.script_task.requests.post") as post:
            self._task(False)._notify_failure(16, "leader", "battle failed")
        post.assert_not_called()

    def test_failure_sends_group_and_reason_with_network_timeout(self):
        response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"code": 200})
        with patch("tasks.MultiAccountEvo.script_task.requests.post", return_value=response) as post:
            self._task(True)._notify_failure(16, "leader", "battle failed")
        args, kwargs = post.call_args
        self.assertEqual("https://www.pushplus.plus/send", args[0])
        self.assertEqual((3, 8), kwargs["timeout"])
        self.assertEqual("test-token", kwargs["json"]["token"])
        self.assertIn("oas3".upper(), kwargs["json"]["title"])
        self.assertIn("16", kwargs["json"]["content"])
        self.assertIn("battle failed", kwargs["json"]["content"])

    def test_push_failure_does_not_replace_task_error(self):
        with patch("tasks.MultiAccountEvo.script_task.requests.post", side_effect=TimeoutError):
            self._task(True)._notify_failure(16, "leader", "battle failed")


class MultiAccountEvoDailyStateTest(unittest.TestCase):
    def test_completed_team_task_records_progress_status_and_today_timestamp(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state = DailyStateManager(temp_dir)
            self.assertFalse(
                state.is_team_task_completed_today("group_01", "multi_account_evo")
            )
            state.update_team_progress(
                "group_01",
                "multi_account_evo",
                20,
                target=20,
            )
            task = state.get_team_task_state("group_01", "multi_account_evo")
            self.assertEqual("completed", task["status"])
            self.assertEqual(20, task["progress"])
            self.assertEqual(20, task["target"])
            self.assertEqual(date.today().isoformat(), task["updated_at"][:10])
            self.assertTrue(
                state.is_team_task_completed_today("group_01", "multi_account_evo")
            )

    def test_desktop_text_report_contains_three_accounts_channel_status_and_time(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / "config"
            config_dir.mkdir()
            relation = "oas3:a@example.com#oas4:b@example.com#oas5:c@example.com"
            for instance, account in (
                ("oas3", "a@example.com"),
                ("oas4", "b@example.com"),
                ("oas5", "c@example.com"),
            ):
                data = {
                    "multi_account_evo": {
                        "multi_account_evo_config": {"group_count": 1},
                        "account_list_1": {
                            "account": account,
                            "apple_or_android": False,
                            "related_account": relation,
                        },
                    }
                }
                (config_dir / f"{instance}.json").write_text(
                    json.dumps(data, ensure_ascii=False), encoding="utf-8"
                )
            output = root / "小号觉醒状态.txt"
            report = MultiAccountEvoStatusReport(config_dir, output)
            report.refresh(
                {
                    "date": "2026-08-17",
                    "teams": {
                        "group_01": {
                            "tasks": {
                                "multi_account_evo": {
                                    "status": "completed",
                                    "updated_at": "2026-08-17T12:30:00",
                                }
                            }
                        }
                    },
                }
            )
            text = output.read_text(encoding="utf-8-sig")
            self.assertIn("账号：a@example.com、b@example.com、c@example.com", text)
            self.assertIn("渠道：iOS", text)
            self.assertIn("刷取状态：已完成", text)
            self.assertIn("更新时间：2026-08-17T12:30:00", text)

    def test_completed_status_with_old_timestamp_is_not_skipped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state = DailyStateManager(temp_dir)
            state.update_team_progress(
                "group_01",
                "multi_account_evo",
                20,
                target=20,
            )
            data = state.load()
            data["teams"]["group_01"]["tasks"]["multi_account_evo"]["updated_at"] = (
                "2026-08-16T23:59:59"
            )
            state.save(data)
            self.assertFalse(
                state.is_team_task_completed_today("group_01", "multi_account_evo")
            )


if __name__ == "__main__":
    unittest.main()
