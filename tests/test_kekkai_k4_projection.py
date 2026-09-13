# This Python file uses the following encoding: utf-8
"""K4-B：`actual_scroll_dy_px` / `project_bbox` / `bbox_iou` / `dedup_by_projection` 单元测试。

锁定：
- `actual_scroll_dy_px`：before/after center_y 之差、保留连续像素（不四舍五入成整格）；
  非法（after >= before / dy >= roi_back 高度 / 任一 unavailable）→ None；
- 投影 = `y - dy`，dy 是真实 float/int 像素、不转 row count；
- dedup：同模板类型 + bbox 真实几何交集（IoU>0）→ 一对一贪心匹配 → duplicate；
- 类型不一致即使 bbox 重叠也不去重；
- 一个 projected 与多个同类 current 相交 → 只配 max IoU 的一个；
- 投影出可见范围 → 忽略该 previous；
- 全 duplicate → new_detections=[]。
"""

import unittest
from types import SimpleNamespace

from tasks.KekkaiUtilize.selected_anchor import SelectedAnchorResult
from tasks.KekkaiUtilize.frame_projection import (
    actual_scroll_dy_px,
    project_bbox,
    bbox_iou,
    dedup_by_projection,
)

_MAX_DY = 442  # I_IS_SELECTED.roi_back[3]
_VISIBLE_Y = (156, 606)


def _av(center_y):
    return SelectedAnchorResult(available=True, center_y=float(center_y),
                                bbox=(610, int(center_y - 29.5), 21, 59), score=0.96, match_count=1)


_UN = SelectedAnchorResult(available=False)


def _det(name, y, *, x=540, w=70, h=54):
    """模拟 find_everyone 的一项：(image, score, (x,y,w,h))。image 只需 .name。"""
    return (SimpleNamespace(name=name), 0.9, (x, y, w, h))


class ActualScrollDyTest(unittest.TestCase):
    def test_basic_positive(self):
        self.assertEqual(actual_scroll_dy_px(_av(500), _av(288), max_dy=_MAX_DY), 212.0)

    def test_sub_row_displacement_preserved(self):
        self.assertEqual(actual_scroll_dy_px(_av(400), _av(360), max_dy=_MAX_DY), 40.0)

    def test_arbitrary_pixel_values_not_rounded_to_rows(self):
        for before_y, after_y, expect in ((500, 327, 173.0), (500, 279, 221.0), (500, 213, 287.0)):
            dy = actual_scroll_dy_px(_av(before_y), _av(after_y), max_dy=_MAX_DY)
            self.assertEqual(dy, expect)
            self.assertNotEqual(dy % 106, 0)              # 不是整数 row_pitch

    def test_after_not_above_before_is_none(self):
        self.assertIsNone(actual_scroll_dy_px(_av(300), _av(300), max_dy=_MAX_DY))   # dy == 0
        self.assertIsNone(actual_scroll_dy_px(_av(300), _av(360), max_dy=_MAX_DY))   # dy < 0

    def test_dy_exceeds_roi_back_height_is_none(self):
        self.assertIsNone(actual_scroll_dy_px(_av(600), _av(600 - 442), max_dy=_MAX_DY))
        self.assertIsNone(actual_scroll_dy_px(_av(600), _av(100), max_dy=_MAX_DY))

    def test_unavailable_anchor_is_none(self):
        self.assertIsNone(actual_scroll_dy_px(_UN, _av(300), max_dy=_MAX_DY))
        self.assertIsNone(actual_scroll_dy_px(_av(500), _UN, max_dy=_MAX_DY))
        self.assertIsNone(actual_scroll_dy_px(_UN, _UN, max_dy=_MAX_DY))


class ProjectBboxTest(unittest.TestCase):
    def test_projects_y_up_by_dy(self):
        self.assertEqual(project_bbox((540, 432, 70, 54), 212), (540, 220, 70, 54))

    def test_float_dy(self):
        self.assertEqual(project_bbox((540, 400, 70, 54), 173.5), (540, 226.5, 70, 54))

    def test_x_w_h_unchanged(self):
        x, y, w, h = project_bbox((100, 500, 30, 40), 250)
        self.assertEqual((x, w, h), (100, 30, 40))


class BboxIouTest(unittest.TestCase):
    def test_identical(self):
        self.assertEqual(bbox_iou((0, 0, 10, 10), (0, 0, 10, 10)), 1.0)

    def test_disjoint(self):
        self.assertEqual(bbox_iou((0, 0, 10, 10), (100, 100, 10, 10)), 0.0)

    def test_partial_overlap(self):
        v = bbox_iou((0, 0, 10, 10), (5, 0, 10, 10))       # 交集 5x10=50, 并集 150
        self.assertAlmostEqual(v, 50 / 150)

    def test_touching_edge_is_zero(self):
        self.assertEqual(bbox_iou((0, 0, 10, 10), (10, 0, 10, 10)), 0.0)


class DedupByProjectionTest(unittest.TestCase):
    def test_two_overlap_two_new(self):
        # §32：上一屏 A B C D，actual_dy=212 → 投影 y 220/114/8/... ；当前 C' D' E F
        prev = [_det('T1', 220), _det('T2', 326), _det('T1', 432), _det('T2', 538)]
        cur = [_det('T1', 220), _det('T2', 326), _det('T1', 432), _det('T2', 538)]
        res = dedup_by_projection(prev, cur, 212, visible_y=_VISIBLE_Y)
        # prev[2] (T1,432) → proj y 220 == cur[0]; prev[3] (T2,538) → proj y 326 == cur[1]
        self.assertEqual(res.duplicate_indices, frozenset({0, 1}))
        self.assertEqual([d[2][1] for d in res.new_detections], [432, 538])   # E, F
        self.assertEqual([d[0].name for d in res.new_detections], ['T1', 'T2'])

    def test_type_mismatch_not_deduped_even_if_overlap(self):
        prev = [_det('TAIKO_6', 220)]
        cur = [_det('FISH_6', 220)]                        # 完全重叠但类型不同
        res = dedup_by_projection(prev, cur, 0, visible_y=_VISIBLE_Y)
        self.assertEqual(res.duplicate_indices, frozenset())
        self.assertEqual(len(res.new_detections), 1)
        self.assertEqual(res.new_detections[0][0].name, 'FISH_6')

    def test_one_projected_two_same_type_current_only_max_iou(self):
        prev = [_det('T1', 300, x=540, w=70, h=54)]        # proj (dy=0) = (540,300,70,54)
        # cur[0] 完全重合（IoU=1）；cur[1] 部分重合（IoU<1）
        cur = [_det('T1', 300, x=540, w=70, h=54),
               _det('T1', 330, x=540, w=70, h=54)]
        res = dedup_by_projection(prev, cur, 0, visible_y=_VISIBLE_Y)
        self.assertEqual(res.duplicate_indices, frozenset({0}))   # 只配 max IoU
        self.assertEqual(len(res.new_detections), 1)
        self.assertEqual(res.new_detections[0][2][1], 330)        # cur[1] 仍是 new

    def test_projected_off_screen_previous_ignored(self):
        # §15：previous center_y=220，dy=250 → projected center ≈ -30 < visible top → 忽略
        prev = [_det('T1', 220 - 27, h=54)]               # center ≈ 220
        cur = [_det('T1', 220, h=54)]
        res = dedup_by_projection(prev, cur, 250, visible_y=_VISIBLE_Y)
        self.assertEqual(res.duplicate_indices, frozenset())      # 上一屏候选已滚出屏，不去重
        self.assertEqual(len(res.new_detections), 1)

    def test_all_duplicate_yields_empty_new(self):
        prev = [_det('T1', 220), _det('T2', 326), _det('T1', 432)]
        cur = [_det('T1', 220), _det('T2', 326), _det('T1', 432)]
        res = dedup_by_projection(prev, cur, 0, visible_y=_VISIBLE_Y)
        self.assertEqual(res.new_detections, [])
        self.assertEqual(res.duplicate_indices, frozenset({0, 1, 2}))

    def test_no_previous_all_new(self):
        cur = [_det('T1', 220), _det('T2', 326)]
        res = dedup_by_projection([], cur, 200, visible_y=_VISIBLE_Y)
        self.assertEqual(res.new_detections, cur)
        self.assertEqual(res.duplicate_indices, frozenset())

    def test_new_detections_preserve_order(self):
        prev = [_det('T1', 300)]
        cur = [_det('T2', 200), _det('T1', 300), _det('T2', 400), _det('T1', 500)]
        res = dedup_by_projection(prev, cur, 0, visible_y=_VISIBLE_Y)
        self.assertEqual([d[2][1] for d in res.new_detections], [200, 400, 500])

    def test_one_current_not_double_consumed_by_two_previous(self):
        # 两个同类 projected 都与同一个 current 相交 → 只有一个配对成功，另一个 previous 无配对
        prev = [_det('T1', 300, x=540, w=70, h=54), _det('T1', 320, x=540, w=70, h=54)]
        cur = [_det('T1', 300, x=540, w=70, h=54)]
        res = dedup_by_projection(prev, cur, 0, visible_y=_VISIBLE_Y)
        self.assertEqual(res.duplicate_indices, frozenset({0}))
        self.assertEqual(len(res.matched_pairs), 1)


if __name__ == '__main__':
    unittest.main()
