"""验证表格报告、旧勾选迁移及展示层异常隔离。"""

import copy
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from module.multi_account import daily_task_report as report
from module.multi_account.daily_task_html import read_html_checks
from module.multi_account.daily_task_images import CooperationImage, read_cooperation_galleries


class DailyTaskReportChecklistTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config_dir = self.root / "config"
        self.config_dir.mkdir()
        self.config = {
            "account_rotation": {"daily_task_config": {
                "daily_cooperation_morning": True, "daily_cooperation_evening": True,
            }},
            "multi_account_evo": {
                "account_list_1": {"account": "shared@example.test", "apple_or_android": False},
                "account_list_2": {"account": "shared@example.test", "apple_or_android": True},
            },
        }
        self._save_config()
        self.snapshot = {"instances": {"oas3": {"accounts": {
            "A01": {"tasks": {
                "cooperation_morning": {"status": "completed", "result": "normal+jade+realworld+sushi"},
                "cooperation_evening": {"status": "completed", "result": "normal+jade"},
            }},
            "A02": {"tasks": {
                "cooperation_morning": {"status": "completed", "result": "normal+jade"},
                "cooperation_evening": {"status": "completed", "result": "none"},
            }},
            "A03": {"tasks": {
                "cooperation_morning": {"status": "pending", "result": "normal+jade"},
            }},
        }}}}
        self.state = SimpleNamespace(load_today=lambda: self.snapshot)
        file_patch = patch.object(report, "__file__", str(self.root / "module/multi_account/daily_task_report.py"))
        file_patch.start()
        self.addCleanup(file_patch.stop)
        clock_patch = patch.object(report, "datetime", wraps=datetime)
        self.clock = clock_patch.start()
        self.addCleanup(clock_patch.stop)
        self.clock.now.return_value = datetime(2026, 10, 23, 19, 0)

    def _save_config(self):
        (self.config_dir / "oas3.json").write_text(json.dumps(self.config), encoding="utf-8")

    def _write(self):
        path = report.write_html(self.state, self.config_dir)
        return path, path.read_text(encoding="utf-8")

    @staticmethod
    def _checked_key():
        return ("cooperation_morning", "shared@example.test", "oas3", "iOS", "普通勾协+现世体协")

    def _migrate_native_check(self):
        path, _content = self._write()
        path.with_suffix(".md").write_text(
            "## 早间协作统计\n\n- [x] 普通勾协+现世体协 — shared@example.test（oas3，iOS）\n",
            encoding="utf-8-sig",
        )
        return self._write()[0]

    def test_only_html_is_generated_with_real_checkboxes_and_history_entry(self):
        path, content = self._write()
        self.assertEqual(path.suffix, ".html")
        self.assertFalse(path.with_suffix(".md").exists())
        self.assertIn("<td>普通勾协+现世体协</td>", content)
        self.assertIn('href="index.html">近7天日志</a>', content)
        self.assertTrue((path.parent / "index.html").exists())
        self.assertNotIn("<!--", content)
        self.assertEqual(content.count('type="checkbox"'), 3)
        self.assertNotIn('type="checkbox" disabled', content)

    def test_native_checks_migrate_to_html_and_survive_regeneration_before_opening(self):
        original = copy.deepcopy(self.snapshot)
        path = self._migrate_native_check()
        self.assertEqual(read_html_checks(path.with_suffix(".html")), {self._checked_key()})
        self._write()
        self.assertEqual(read_html_checks(path.with_suffix(".html")), {self._checked_key()})
        self.assertEqual(self.snapshot, original)

    def test_account_platform_and_result_changes_do_not_inherit_initial_check(self):
        for field in ("account", "platform", "result"):
            with self.subTest(field=field):
                path = self._migrate_native_check()
                if field == "account":
                    self.config["multi_account_evo"]["account_list_1"]["account"] = "renamed@example.test"
                elif field == "platform":
                    self.config["multi_account_evo"]["account_list_1"]["apple_or_android"] = True
                else:
                    self.snapshot["instances"]["oas3"]["accounts"]["A01"]["tasks"]["cooperation_morning"]["result"] = "normal+jade"
                self._save_config()
                self._write()
                self.assertEqual(read_html_checks(path.with_suffix(".html")), set())
                self.config["multi_account_evo"]["account_list_1"].update(account="shared@example.test", apple_or_android=False)
                self.snapshot["instances"]["oas3"]["accounts"]["A01"]["tasks"]["cooperation_morning"]["result"] = "normal+jade+realworld+sushi"
                self._save_config()

    def test_new_day_does_not_copy_previous_day_initial_checks(self):
        path = self._migrate_native_check()
        previous = path.with_suffix(".html").read_bytes()
        self.clock.now.return_value = datetime(2026, 10, 24, 19, 0)
        next_path, _content = self._write()
        self.assertNotEqual(path, next_path)
        self.assertEqual(read_html_checks(next_path.with_suffix(".html")), set())
        self.assertEqual(path.with_suffix(".html").read_bytes(), previous)

    def test_disabled_and_empty_cooperation_has_no_clickable_rows(self):
        self.config["account_rotation"]["daily_task_config"]["daily_cooperation_morning"] = False
        self._save_config()
        self.snapshot["instances"]["oas3"]["accounts"]["A01"]["tasks"]["cooperation_evening"]["result"] = "none"
        path, content = self._write()
        self.assertEqual(content.count('class="card cooperation"'), 2)
        self.assertNotIn('type="checkbox"', content)

    def test_legacy_table_checks_migrate_without_leaking_markers(self):
        path, _content = self._write()
        key = "cooperation:cooperation_morning:oas3:A01:iOS:普通勾协+现世体协"
        path.with_suffix(".md").write_text(
            f"## 早间协作统计\n\n|☑|shared@example.test|oas3|iOS|普通勾协+现世体协 <!-- {key} -->|\n",
            encoding="utf-8",
        )
        _path, cleaned = self._write()
        self.assertEqual(read_html_checks(path.with_suffix(".html")), {self._checked_key()})
        self.assertNotIn("<!--", cleaned)
        self.assertNotIn(f"<!-- {key} -->", cleaned)

    def test_legacy_per_type_list_requires_the_whole_record_to_be_checked(self):
        path, _content = self._write()
        prefix = "cooperation:cooperation_morning:oas3:A01:iOS:"
        legacy = "\n".join(f"- [x] account <!-- {prefix}{label} -->" for label in ("普通勾协", "现世体协"))
        path.with_suffix(".md").write_text(legacy, encoding="utf-8")
        self._write()
        self.assertEqual(read_html_checks(path.with_suffix(".html")), {self._checked_key()})
        path.with_suffix(".html").unlink()
        path.with_suffix(".md").write_text(legacy.splitlines()[0], encoding="utf-8")
        self._write()
        self.assertEqual(read_html_checks(path.with_suffix(".html")), set())

    def test_html_failure_preserves_existing_report_and_task_state(self):
        original = copy.deepcopy(self.snapshot)
        path, _content = self._write()
        previous = path.read_bytes()
        with patch.object(report, "render_interactive_report", side_effect=RuntimeError("渲染失败")):
            with patch.object(report.logger, "exception") as logged:
                returned = report.write_html(self.state, self.config_dir)
        self.assertEqual(returned, path)
        self.assertEqual(path.read_bytes(), previous)
        self.assertFalse(path.with_suffix(".md").exists())
        self.assertEqual(self.snapshot, original)
        logged.assert_called_once()

    def test_legacy_writer_name_also_only_outputs_html(self):
        path = report.write_markdown(self.state, self.config_dir)
        self.assertEqual(path.suffix, ".html")
        self.assertTrue(path.exists())
        self.assertFalse(path.with_suffix(".md").exists())

    def test_refresh_automatically_removes_only_expired_known_reports(self):
        path, _content = self._write()
        expired = path.parent / "OAS每日任务结果_2026-10-16.md"
        boundary = path.parent / "OAS每日任务结果_2026-10-17.html"
        unrelated = path.parent / "个人备注.md"
        for item in (expired, boundary, unrelated):
            item.write_text("保留内容", encoding="utf-8")
        self._write()
        self.assertFalse(expired.exists())
        self.assertTrue(boundary.exists())
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "保留内容")

    def test_multiple_images_survive_other_account_refreshes_without_extra_files_or_state_changes(self):
        original = copy.deepcopy(self.snapshot)
        pictures = tuple(CooperationImage(slot, "普通勾协", "data:image/jpeg;base64,YQ==") for slot in (1, 2))
        path = report.write_html(self.state, self.config_dir, image_updates={
            ("cooperation_morning", "oas3", "A01"): pictures,
        })
        report.write_html(self.state, self.config_dir, image_updates={
            ("cooperation_evening", "oas3", "A01"): pictures[:1],
            ("cooperation_morning", "oas3", "A02"): pictures[1:],
        })
        self._write()
        galleries = read_cooperation_galleries(path)
        self.assertEqual(galleries[("cooperation_morning", "oas3", "A01", "普通勾协+现世体协")].images, pictures)
        self.assertEqual(galleries[("cooperation_evening", "oas3", "A01", "普通勾协")].images, pictures[:1])
        self.assertEqual(galleries[("cooperation_morning", "oas3", "A02", "普通勾协")].images, pictures[1:])
        self.assertEqual(self.snapshot, original)
        self.assertEqual({item.suffix for item in path.parent.iterdir()}, {".html", ".lock"})
        self.assertIn("<th>协作详情</th>", path.read_text(encoding="utf-8"))

    def test_previous_images_do_not_attach_to_changed_result_or_next_day(self):
        pictures = (CooperationImage(1, "普通勾协", "data:image/jpeg;base64,YQ=="),)
        path = report.write_html(self.state, self.config_dir, image_updates={
            ("cooperation_morning", "oas3", "A01"): pictures,
        })
        self.snapshot["instances"]["oas3"]["accounts"]["A01"]["tasks"]["cooperation_morning"]["result"] = "realworld+jade"
        self._write()
        self.assertEqual(read_cooperation_galleries(path), {})
        report.write_html(self.state, self.config_dir, image_updates={
            ("cooperation_morning", "oas3", "A01"): pictures,
        })
        self.assertTrue(read_cooperation_galleries(path))
        previous = path.read_bytes()
        self.clock.now.return_value = datetime(2026, 10, 24, 19, 0)
        next_path, _ = self._write()
        self.assertEqual(read_cooperation_galleries(next_path), {})
        self.assertEqual(path.read_bytes(), previous)


if __name__ == "__main__":
    unittest.main()
