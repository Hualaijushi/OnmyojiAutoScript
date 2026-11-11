"""验证七天保留边界、入口顺序及删除失败隔离。"""

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

from module.multi_account import daily_task_archive as archive


class DailyTaskArchiveTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.today = date(2026, 10, 23)

    def _file(self, name):
        path = self.root / name
        path.write_text("原有内容", encoding="utf-8")
        return path

    def test_calendar_date_boundary_ignores_mtime_and_preserves_unrelated_files(self):
        expired = [self._file(f"OAS每日任务结果_2026-10-16.{suffix}") for suffix in ("html", "md", "txt")]
        retained = [self._file(f"OAS每日任务结果_{day}.html") for day in ("2026-10-17", "2026-10-23", "2026-10-24")]
        unrelated = [self._file(name) for name in ("个人备注.md", ".daily_task_report.lock", "OAS每日任务结果_2026-02-30.html")]
        directory = self.root / "OAS每日任务结果_2026-10-15.html"
        directory.mkdir()
        (directory / "不递归删除.txt").write_text("保留", encoding="utf-8")
        removed = archive.refresh_report_archive(self.root, self.today)
        self.assertEqual(set(removed), set(expired))
        self.assertTrue(all(path.exists() for path in retained + unrelated))
        self.assertTrue((directory / "不递归删除.txt").exists())
        index = (self.root / "index.html").read_text(encoding="utf-8")
        self.assertNotIn(quote("OAS每日任务结果_2026-10-24.html"), index)

    def test_index_latest_and_history_are_ordered_by_report_date(self):
        self._file("OAS每日任务结果_2026-10-22.html")
        self._file("OAS每日任务结果_2026-10-23.html")
        self._file("OAS每日任务结果_2026-10-21.md")
        archive.refresh_report_archive(self.root, self.today)
        index = (self.root / "index.html").read_text(encoding="utf-8")
        latest = quote("OAS每日任务结果_2026-10-23.html")
        older = quote("OAS每日任务结果_2026-10-22.html")
        self.assertIn(f'id="latest" class="primary" href="{latest}"', index)
        self.assertLess(index.index(latest), index.index(older))
        self.assertNotIn(quote("OAS每日任务结果_2026-10-21.md"), index)
        self.assertIn("location.replace(link.href)", index)

    def test_index_write_failure_keeps_old_reports_and_removes_temporary_file(self):
        expired = self._file("OAS每日任务结果_2026-10-16.html")
        with patch.object(archive, "atomic_replace_with_retry", side_effect=OSError("写入失败")):
            with self.assertRaises(OSError):
                archive.refresh_report_archive(self.root, self.today)
        self.assertTrue(expired.exists())
        self.assertFalse(list(self.root.glob("*.tmp")))

    def test_one_locked_expired_file_does_not_prevent_other_cleanup(self):
        locked = self._file("OAS每日任务结果_2026-10-15.html")
        removable = self._file("OAS每日任务结果_2026-10-16.html")
        unlink = Path.unlink

        def unlink_with_lock(path, *args, **kwargs):
            if path == locked:
                raise PermissionError("文件被占用")
            return unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", unlink_with_lock), patch.object(archive.logger, "warning") as logged:
            removed = archive.refresh_report_archive(self.root, self.today)
        self.assertEqual(removed, [removable])
        self.assertTrue(locked.exists())
        self.assertFalse(removable.exists())
        logged.assert_called_once()


if __name__ == "__main__":
    unittest.main()
