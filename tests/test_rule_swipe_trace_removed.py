"""RuleSwipe 死代码（trace / is_default_mode / is_vector_mode）清理后的回归护栏。

`RuleSwipe.trace()` 及 `is_default_mode` / `is_vector_mode` 全仓零生产调用方，且
生产滑动一律走 `Control.swipe` → 各后端自身实现（minitouch 走 `insert_swipe`），
不经过 `RuleSwipe.trace()`。清理后 `RuleSwipe` 只保留 `__init__` 与 `coord()`。
"""

import inspect
from unittest import TestCase

from module.atom import swipe as swipe_module
from module.atom.swipe import RuleSwipe


class RuleSwipeTraceRemovedTest(TestCase):
    def test_module_imports_and_public_api_intact(self):
        # 模块可正常导入；生产 API coord() 仍工作且返回 4 元组
        rule = RuleSwipe(roi_front=(100, 200, 20, 30), roi_back=(400, 500, 40, 50), mode="default")
        coord = rule.coord()
        self.assertEqual(len(coord), 4)
        x1, y1, x2, y2 = coord
        self.assertTrue(100 <= x1 < 120 and 200 <= y1 < 230)
        self.assertTrue(400 <= x2 < 440 and 500 <= y2 < 550)
        self.assertEqual(rule.name, "swipe")
        self.assertEqual(rule.interval, 8)

    def test_dead_symbols_are_gone(self):
        for name in ("trace", "is_default_mode", "is_vector_mode"):
            self.assertFalse(
                hasattr(RuleSwipe, name),
                f"RuleSwipe.{name} 应已删除",
            )

    def test_dead_imports_are_gone(self):
        lines = {ln.strip() for ln in inspect.getsource(swipe_module).splitlines()}
        for stmt in (
            "import random",
            "from math import dist",
            "from module.base.decorator import cached_property",
            "from module.atom.cBezier import BezierTrajectory",
        ):
            self.assertNotIn(stmt, lines, f"swipe.py 不应再出现 {stmt!r}")
        # coord() 仍依赖的公共随机 import 必须保留
        self.assertIn(
            "from module.base.utils.random import random_center_point_in_roi", lines
        )

    def test_no_production_caller_of_trace(self):
        # 静态确认：项目源码里没有 `.trace(` 调用（RuleSwipe 相关）。
        # 这里只校验 RuleSwipe 自身不再暴露该能力；全仓 grep 见开发日志。
        self.assertNotIn("trace", dir(RuleSwipe))
