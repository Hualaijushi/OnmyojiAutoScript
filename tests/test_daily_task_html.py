"""验证可点击报告的勾选初值及账号文本转义。"""

import json
import unittest
from html.parser import HTMLParser

from module.multi_account.daily_task_html import render_interactive_report
from module.multi_account.daily_task_images import CooperationGallery, CooperationImage


class _ReportParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inputs = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag == "input":
            self.inputs.append(dict(attrs))
        if tag == "script":
            self.scripts.append(dict(attrs))


class DailyTaskHtmlTest(unittest.TestCase):
    @staticmethod
    def _markdown(account="sample@example.test"):
        header = "|账号|模拟器编号|平台|协作|\n|-|-|-|-|\n"
        return (
            "|账号|状态|\n|-|-|\n|sample|✅完成|\n\n"
            + "## 早间协作统计\n\n" + header + f"|{account}|oas3|iOS|普通勾协|\n\n"
            + "## 晚间协作统计\n\n" + header + f"|{account}|oas3|iOS|普通勾协|\n"
        )

    def test_real_checkboxes_seed_existing_progress_and_separate_periods(self):
        key = ("cooperation_morning", "sample@example.test", "oas3", "iOS", "普通勾协")
        html = render_interactive_report(self._markdown(), title="测试报告", report_date="2026-10-23", checked_keys={key})
        parser = _ReportParser()
        parser.feed(html)
        self.assertEqual(len(parser.inputs), 2)
        morning, evening = parser.inputs
        self.assertEqual(morning["type"], "checkbox")
        self.assertIn("checked", morning)
        self.assertNotIn("checked", evening)
        self.assertNotIn("disabled", morning)
        self.assertNotEqual(morning["data-key"], evening["data-key"])
        self.assertEqual(tuple(json.loads(morning["data-key"])), key)

    def test_account_text_cannot_create_script_or_extra_input_attributes(self):
        account = '<script>alert("account")</script><img src=x onerror="alert(1)">'
        html = render_interactive_report(self._markdown(account), title="测试报告", report_date="2026-10-23", checked_keys=set())
        parser = _ReportParser()
        parser.feed(html)
        self.assertEqual(parser.scripts, [{}])
        self.assertEqual(len(parser.inputs), 2)
        self.assertEqual(json.loads(parser.inputs[0]["data-key"])[1], account)
        self.assertNotIn(account, html)
        self.assertNotIn("onerror", parser.inputs[0])

    def test_images_are_inline_and_invalid_sources_are_not_rendered(self):
        label = '<img src=x onerror="alert(1)">'
        gallery = CooperationGallery(("cooperation_morning", "oas3", "A01", "普通勾协"), (
            CooperationImage(1, label, "data:image/png;base64,YQ=="),
            CooperationImage(2, "错误图片", 'x" onerror="alert(1)'),
        ))
        html = render_interactive_report(
            self._markdown(), title="测试报告", report_date="2026-10-23", checked_keys=set(),
            row_galleries={("cooperation_morning", 0): gallery},
        )
        self.assertEqual(html.count('class="cooperation-image"'), 1)
        self.assertIn('src="data:image/png;base64,YQ=="', html)
        self.assertNotIn(label, html)
        self.assertNotIn('src="x', html)
        self.assertNotIn("<dialog", html)


if __name__ == "__main__":
    unittest.main()
