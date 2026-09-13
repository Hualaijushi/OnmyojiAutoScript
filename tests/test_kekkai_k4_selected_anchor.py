# This Python file uses the following encoding: utf-8
"""K4-A：`detect_selected_anchor` / `SelectedAnchorResult` 单元测试。

锁定：
- `match_all_any` 命中 1 个 → available，`center_y = y + h/2`，score/bbox 原样保留；
- 0 个 → unavailable；>1 个（NMS 后）→ unavailable（宁可测不到也不选错 glow）；
- `roi_back` 内任意 Y（顶 / 中 / 底 / 连续）命中都能算出正确 center_y；
- 边界只剩部分模板 → matcher 返回 0 → detector unavailable；
- **不调用** `RuleImage.coord()`；**不依赖** `SWIPE_DISTANCE_RANGE` / commanded 位移；
- `threshold=None` 时透传（用资产自带阈值，不在这里改）。
"""

import inspect
import unittest
from unittest.mock import Mock

from tasks.KekkaiUtilize.selected_anchor import detect_selected_anchor, SelectedAnchorResult
from tasks.KekkaiUtilize import selected_anchor as sa_mod


def _rule(matches):
    """构造一个只暴露 match_all_any / roi_back / coord 的假 RuleImage。"""
    r = Mock(name='I_IS_SELECTED')
    r.roi_back = (602, 168, 30, 442)
    r.match_all_any = Mock(return_value=list(matches))
    r.coord = Mock(name='coord', side_effect=AssertionError('detect_selected_anchor 不得调用 coord()'))
    return r


class DetectSelectedAnchorTest(unittest.TestCase):
    FRAME = object()  # detector 不解析帧内容，只透传给 match_all_any

    def test_zero_match_is_unavailable(self):
        res = detect_selected_anchor(self.FRAME, _rule([]))
        self.assertFalse(res.available)
        self.assertEqual(res.match_count, 0)
        self.assertIsNone(res.center_y)
        self.assertIsNone(res.bbox)
        self.assertIsNone(res.score)

    def test_exactly_one_match_is_available_with_center_y(self):
        r = _rule([(0.97, 610, 300, 21, 59)])
        res = detect_selected_anchor(self.FRAME, r)
        self.assertTrue(res.available)
        self.assertEqual(res.match_count, 1)
        self.assertEqual(res.center_y, 300 + 59 / 2.0)     # 329.5
        self.assertEqual(res.bbox, (610, 300, 21, 59))
        self.assertEqual(res.score, 0.97)
        self.assertIsInstance(res.center_y, float)
        self.assertIsInstance(res.score, float)
        for v in res.bbox:
            self.assertIsInstance(v, int)

    def test_multiple_match_after_nms_is_unavailable(self):
        for n in (2, 3, 5):
            with self.subTest(n=n):
                r = _rule([(0.9, 610, 200 + 60 * i, 21, 59) for i in range(n)])
                res = detect_selected_anchor(self.FRAME, r)
                self.assertFalse(res.available)
                self.assertEqual(res.match_count, n)
                self.assertIsNone(res.center_y)

    def test_dynamic_y_top_mid_bottom(self):
        # roi_back y 168..610；模板 59 高 → 命中顶部 y≈170 / 中部 y≈390 / 底部 y≈545
        for y in (170, 390, 545):
            with self.subTest(y=y):
                res = detect_selected_anchor(self.FRAME, _rule([(0.96, 611, y, 21, 59)]))
                self.assertTrue(res.available)
                self.assertEqual(res.center_y, y + 29.5)
                self.assertEqual(res.bbox[1], y)

    def test_dynamic_y_continuous(self):
        # 任意连续 Y 都线性跟随，不吸附到固定 slot
        seen = set()
        for y in range(180, 561, 20):
            res = detect_selected_anchor(self.FRAME, _rule([(0.95, 610, y, 21, 59)]))
            self.assertTrue(res.available)
            self.assertEqual(res.center_y, y + 29.5)
            seen.add(res.center_y)
        self.assertGreater(len(seen), 15)                 # 连续、非离散 4 格

    def test_score_preserved_various_values(self):
        for s in (0.81, 0.90, 0.955, 0.999):
            res = detect_selected_anchor(self.FRAME, _rule([(s, 610, 300, 21, 59)]))
            self.assertEqual(res.score, s)

    def test_boundary_partial_template_is_unavailable(self):
        # selected row 滑到列表上/下边界，只剩半个 glow → matcher 无完整命中 → 0 个 → unavailable
        res = detect_selected_anchor(self.FRAME, _rule([]))
        self.assertFalse(res.available)

    def test_does_not_call_coord_or_front_center(self):
        r = _rule([(0.97, 610, 300, 21, 59)])
        r.front_center = Mock(side_effect=AssertionError('不得调用 front_center()'))
        detect_selected_anchor(self.FRAME, r)
        r.coord.assert_not_called()
        r.front_center.assert_not_called()
        r.match_all_any.assert_called_once()              # 走的是全量匹配 + NMS，坐标来自返回元组

    def test_body_does_not_reference_coord_or_commanded_distance(self):
        # 只看函数体（去掉解释性 docstring），锚点测量不碰点击采样 / 不引用指令位移
        src = inspect.getsource(detect_selected_anchor)
        body = src.split('"""', 2)[-1]
        for token in ('.coord(', 'coord()', 'front_center', 'SWIPE_DISTANCE',
                      'KEKKAI_ROW_PITCH', 'commanded'):
            self.assertNotIn(token, body, token)

    def test_threshold_none_is_passed_through(self):
        r = _rule([(0.97, 610, 300, 21, 59)])
        detect_selected_anchor(self.FRAME, r, threshold=None, nms_threshold=0.3, frame_id='F1')
        _args, kwargs = r.match_all_any.call_args
        self.assertIsNone(kwargs.get('threshold'))        # 用资产自带阈值
        self.assertEqual(kwargs.get('nms_threshold'), 0.3)
        self.assertEqual(kwargs.get('frame_id'), 'F1')

    def test_result_dataclass_is_frozen(self):
        res = SelectedAnchorResult(available=False)
        with self.assertRaises(Exception):
            res.available = True                          # frozen


if __name__ == '__main__':
    unittest.main()
