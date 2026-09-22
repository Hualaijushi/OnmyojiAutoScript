"""`BaseTask.list_find` / `list_appear_click` 的 characterization + T5-2 FrameWait 迁移护栏。

2026-09-08：翻页后的固定 `sleep(random.uniform(0.8, 1.3))` 已迁到 FrameState 等待层
（`module/base/frame_wait.wait_for_changed_and_stable`，见 `docs/DECISIONS.md` D013 补记）。
迁移语义 = **W1 结构性 settle**：只把「等这次翻页滚动完再重新识别」换成更聪明的等待，
**FrameWait 的结果不参与控制流**——settle 成功或 timeout 都一样回到循环顶重新截图 +
重新 `image_appear` / `ocr_appear`，`max_swipe` 仍是唯一收敛边界，不新增 BOTTOM / ABORT。

这些测试锁：识别 / swipe / settle 的调用顺序与次数、退出语义、返回值形态、异常传播，
以及「FrameWait timeout 不改变 list_find 的收敛 / 返回」。也照实锁定几处已知瑕疵
（最后一次未命中仍 swipe + settle；OCR 无结果的哨兵 `(0, 0)` 被当命中坐标），留注释。

源码：`tasks/base_task.py` `list_find`（约 774-812 行）、`list_appear_click`、
模块级 `_LIST_FIND_SETTLE_*` / `_list_roi_back_to_box`。
"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from tasks.base_task import BaseTask, _list_roi_back_to_box


class _FakeList:
    """替身 RuleList：只实现 `list_find` 用到的成员。

    `is_image` / `is_ocr` 决定走哪条识别分支；`results` 是每次识别调用按顺序返回的值
    （元组=命中坐标，其余=未命中信号）。`roi_back` 供 FrameWait ROI 推导用。
    """

    def __init__(self, mode: str, results, roi_back=(100, 150, 300, 400)):
        self.is_image = mode == 'image'
        self.is_ocr = mode == 'ocr'
        self._results = list(results)
        self.roi_back = list(roi_back)
        self.image_calls = []
        self.ocr_calls = []
        self.swipe_pos_calls = []

    def image_appear(self, image, name, frame_id=None):
        self.image_calls.append((name, frame_id))
        return self._results.pop(0)

    def ocr_appear(self, image, name):
        self.ocr_calls.append(name)
        return self._results.pop(0)

    def swipe_pos(self, number: int = 2, after: bool = True):
        self.swipe_pos_calls.append((number, after))
        return (11, 22, 33, 44)


class ListFindCharacterizationTest(TestCase):
    def setUp(self):
        self.task = BaseTask.__new__(BaseTask)
        self.events = []
        self.device = SimpleNamespace(
            image='FRAME',
            image_frame_id='FID',
            screenshot=Mock(side_effect=lambda: self.events.append('device.screenshot') or 'POLLFRAME'),
            swipe=Mock(side_effect=lambda **kw: self.events.append(('swipe', kw['p1'], kw['p2']))),
        )
        self.task.device = self.device
        self.task.screenshot = Mock(side_effect=lambda: self.events.append('screenshot'))

        # 翻页 settle 现在走 wait_for_changed_and_stable（tasks.base_task 模块级引用）。
        # 默认返回 success（changed & stable），个别用例覆写成 timeout 以验证「结果不参与控制流」。
        self._ok = SimpleNamespace(success=True, changed=True, stable=True, timed_out=False)
        self._wait = patch(
            'tasks.base_task.wait_for_changed_and_stable',
            side_effect=lambda *a, **kw: self.events.append(('wait', kw.get('roi'))) or self._ok,
        ).start()
        self.addCleanup(patch.stopall)

    def _run(self, mode, results, *, name='layer', max_swipe=10, roi_back=(100, 150, 300, 400)):
        target = _FakeList(mode, results, roi_back=roi_back)
        ret = self.task.list_find(target, name, max_swipe=max_swipe)
        return target, ret

    # ---- 第一屏命中 ------------------------------------------------------

    def test_found_on_first_screen_image_no_swipe_no_wait(self):
        target, ret = self._run('image', [(100, 200)])
        self.assertEqual(ret, (100, 200))
        self.assertEqual(self.events, ['screenshot'])
        self.assertEqual(target.image_calls, [('layer', 'FID')])
        self.device.swipe.assert_not_called()
        self._wait.assert_not_called()
        self.assertEqual(target.swipe_pos_calls, [])

    def test_found_on_first_screen_ocr_no_swipe_no_wait(self):
        target, ret = self._run('ocr', [(50, 60)])
        self.assertEqual(ret, (50, 60))
        self.assertEqual(self.events, ['screenshot'])
        self.assertEqual(target.ocr_calls, ['layer'])
        self.device.swipe.assert_not_called()
        self._wait.assert_not_called()

    def test_return_value_is_the_raw_finder_result(self):
        _, ret = self._run('image', [(123, 456)])
        self.assertEqual(ret, (123, 456))

    # ---- 翻页后命中 ----------------------------------------------------

    def test_found_after_one_swipe_image(self):
        target, ret = self._run('image', [False, (7, 8)])
        self.assertEqual(ret, (7, 8))
        self.assertEqual(self.events, [
            'screenshot',
            ('swipe', (11, 22), (33, 44)),
            ('wait', (100, 150, 400, 550)),
            'screenshot',
        ])
        self.assertEqual(self.task.screenshot.call_count, 2)
        self.device.swipe.assert_called_once_with(p1=(11, 22), p2=(33, 44))
        self._wait.assert_called_once()
        # image 模式：swipe_down 恒为 True，swipe_pos 用默认 number=2 + after=True
        self.assertEqual(target.swipe_pos_calls, [(2, True)])

    def test_settle_wait_uses_frame_wait_with_list_roi_and_device_screenshot(self):
        target, _ = self._run('image', [False, (1, 1)], roi_back=(10, 20, 30, 40))
        args, kwargs = self._wait.call_args
        # baseline（位置参数 0）= 翻页前那一帧
        self.assertEqual(args[0], 'FRAME')
        # frame_provider（位置参数 1）= device.screenshot（K3 同款：不经 BaseTask.screenshot 的 _burst）
        self.assertIs(args[1], self.device.screenshot)
        # ROI = RuleList.roi_back 换算成 (x1,y1,x2,y2)，不是全局 ROI
        self.assertEqual(kwargs['roi'], (10, 20, 40, 60))
        # 有限 timeout + 显式 poll_interval + 三个阈值都显式传（无全局默认）
        for key in ('changed_threshold', 'stable_threshold', 'stable_frames', 'timeout', 'poll_interval'):
            self.assertIn(key, kwargs)
        self.assertGreater(kwargs['timeout'], 0)
        self.assertLessEqual(kwargs['timeout'], 3)

    def test_found_after_two_swipes_image_full_ordering(self):
        _, ret = self._run('image', [False, False, (1, 2)])
        self.assertEqual(ret, (1, 2))
        self.assertEqual(self.events, [
            'screenshot',
            ('swipe', (11, 22), (33, 44)),
            ('wait', (100, 150, 400, 550)),
            'screenshot',
            ('swipe', (11, 22), (33, 44)),
            ('wait', (100, 150, 400, 550)),
            'screenshot',
        ])
        self.assertEqual(self.task.screenshot.call_count, 3)
        self.assertEqual(self.device.swipe.call_count, 2)
        self.assertEqual(self._wait.call_count, 2)

    def test_no_extra_screenshot_between_miss_and_swipe(self):
        # 未命中 -> swipe，中间不额外走 BaseTask.screenshot：每轮恰好 1 次 BaseTask.screenshot。
        self._run('image', [False, (1, 1)])
        self.assertEqual(self.task.screenshot.call_count, 2)

    def test_order_is_screenshot_find_swipe_wait_never_swipe_first(self):
        # 锁死关键顺序：find 在 swipe 前，settle-wait 在 swipe 后，下一轮 screenshot 在 wait 后。
        self._run('image', [False, (9, 9)])
        idx_screenshot_1 = 0
        idx_swipe = self.events.index(('swipe', (11, 22), (33, 44)))
        idx_wait = self.events.index(('wait', (100, 150, 400, 550)))
        idx_screenshot_2 = len(self.events) - 1
        self.assertEqual(self.events[idx_screenshot_1], 'screenshot')
        self.assertEqual(self.events[idx_screenshot_2], 'screenshot')
        self.assertLess(idx_screenshot_1, idx_swipe)
        self.assertLess(idx_swipe, idx_wait)
        self.assertLess(idx_wait, idx_screenshot_2)

    # ---- FrameWait 结果不参与控制流（W1 结构性 settle） -----------------

    def test_settle_timeout_does_not_change_convergence_or_return(self):
        # FrameWait 返回 timeout（changed 但没 stable）——list_find 照旧回循环顶重新识别，
        # 收敛仍只由 max_swipe 决定，绝不因 settle 失败变成 BOTTOM / ABORT / 提前返回。
        self._ok.success = False
        self._ok.timed_out = True
        self._ok.stable = False
        target, ret = self._run('image', [False, False, (5, 5)])
        self.assertEqual(ret, (5, 5))
        self.assertEqual(self.device.swipe.call_count, 2)
        self.assertEqual(self._wait.call_count, 2)

    def test_settle_timeout_never_found_still_returns_false_by_max_swipe(self):
        self._ok.success = False
        self._ok.timed_out = True
        target, ret = self._run('image', [False, False, False], max_swipe=3)
        self.assertIs(ret, False)
        self.assertEqual(self.device.swipe.call_count, 3)
        self.assertEqual(self._wait.call_count, 3)

    # ---- OCR 方向 -----------------------------------------------------

    def test_ocr_negative_result_swipes_toward_front(self):
        # result 为负 int -> swipe_down False -> swipe_pos(number=1, after=False)
        target, ret = self._run('ocr', [-3, (9, 9)])
        self.assertEqual(ret, (9, 9))
        self.assertEqual(target.swipe_pos_calls, [(1, False)])

    def test_ocr_positive_result_swipes_toward_back(self):
        # result 为正 int -> swipe_down True -> swipe_pos(number=1, after=True)
        target, ret = self._run('ocr', [5, (9, 9)])
        self.assertEqual(ret, (9, 9))
        self.assertEqual(target.swipe_pos_calls, [(1, True)])

    def test_ocr_zero_result_swipes_with_after_false(self):
        # result == 0（既非 tuple 也非 >0）-> swipe_down False
        target, ret = self._run('ocr', [0, (2, 2)])
        self.assertEqual(ret, (2, 2))
        self.assertEqual(target.swipe_pos_calls, [(1, False)])

    def test_ocr_empty_result_sentinel_tuple_is_treated_as_hit(self):
        # 已知瑕疵（本轮不修）：RuleList.ocr_appear 在「无 OCR 结果」时返回 (0, 0)，
        # 是个 tuple，被 list_find 当成命中坐标直接返回。
        target, ret = self._run('ocr', [(0, 0)])
        self.assertEqual(ret, (0, 0))
        self.device.swipe.assert_not_called()

    # ---- 未命中 / 边界 -----------------------------------------------

    def test_never_found_exhausts_max_swipe_and_returns_false(self):
        target, ret = self._run('image', [False, False, False], max_swipe=3)
        self.assertIs(ret, False)
        # 已知瑕疵（本轮不修）：最后一次未命中仍然 swipe + settle-wait，没有「末轮跳过」优化。
        self.assertEqual(self.task.screenshot.call_count, 3)
        self.assertEqual(self.device.swipe.call_count, 3)
        self.assertEqual(self._wait.call_count, 3)
        self.assertEqual(target.image_calls, [('layer', 'FID')] * 3)

    def test_max_swipe_zero_returns_false_without_touching_device(self):
        target, ret = self._run('image', [], max_swipe=0)
        self.assertIs(ret, False)
        self.task.screenshot.assert_not_called()
        self.device.swipe.assert_not_called()
        self._wait.assert_not_called()
        self.assertEqual(target.image_calls, [])

    def test_falsy_target_returns_false_immediately(self):
        ret = self.task.list_find(None, 'layer')
        self.assertIs(ret, False)
        self.task.screenshot.assert_not_called()
        self.device.swipe.assert_not_called()

    def test_list_find_has_no_bottom_detection_only_max_swipe_bounds_it(self):
        # list_find 从不读 RuleList.is_bottom / swipe_pos 的边界信息，纯靠 max_swipe 收敛。
        target, ret = self._run('image', [False] * 5, max_swipe=5)
        self.assertIs(ret, False)
        self.assertEqual(self.device.swipe.call_count, 5)

    # ---- 异常透传（本轮不新增 try/except / retry / recovery）--------

    def test_screenshot_exception_propagates(self):
        self.task.screenshot.side_effect = RuntimeError('boom')
        target = _FakeList('image', [(1, 1)])
        with self.assertRaises(RuntimeError):
            self.task.list_find(target, 'layer')
        self.device.swipe.assert_not_called()
        self._wait.assert_not_called()

    def test_finder_exception_propagates(self):
        target = _FakeList('image', [])
        target.image_appear = Mock(side_effect=ValueError('bad frame'))
        with self.assertRaises(ValueError):
            self.task.list_find(target, 'layer')
        self.device.swipe.assert_not_called()

    def test_swipe_exception_propagates_before_settle_wait(self):
        self.device.swipe.side_effect = RuntimeError('swipe failed')
        target = _FakeList('image', [False, (1, 1)])
        with self.assertRaises(RuntimeError):
            self.task.list_find(target, 'layer')
        # swipe 在 settle-wait 之前，异常时等待未发生
        self._wait.assert_not_called()

    def test_settle_wait_exception_propagates(self):
        self._wait.side_effect = RuntimeError('frame wait blew up')
        target = _FakeList('image', [False, (1, 1)])
        with self.assertRaises(RuntimeError):
            self.task.list_find(target, 'layer')


class ListRoiBackToBoxTest(TestCase):
    def test_xywh_to_x1y1x2y2(self):
        self.assertEqual(_list_roi_back_to_box((100, 150, 300, 400)), (100, 150, 400, 550))

    def test_accepts_list_and_floats(self):
        self.assertEqual(_list_roi_back_to_box([10.0, 20.0, 5.0, 6.0]), (10, 20, 15, 26))


class ListAppearClickCharacterizationTest(TestCase):
    """`list_appear_click` 是 `list_find` 的直接生产包装（navigator / Dokan 用）。"""

    def setUp(self):
        self.task = BaseTask.__new__(BaseTask)
        self.task.interval_timer = {}
        self.task.device = SimpleNamespace(click=Mock())
        self.target = SimpleNamespace(name='L_X', array=['first'])

    def test_hit_with_interval_clicks_and_returns_true(self):
        self.task.list_find = Mock(return_value=(5, 6))
        ret = self.task.list_appear_click(self.target, interval=1, max_swipe=3)
        self.assertIs(ret, True)
        self.task.list_find.assert_called_once_with(self.target, name='first', max_swipe=3)
        # L1：list_find 的返回值已是最终落点，原样执行一次、不再采样；同时带上列表名供
        # BehaviorTrace 区分（旧实现是无名的 `device.click(5, 6)`，坐标本身不变）。
        self.task.device.click.assert_called_once_with(x=5, y=6, control_name='L_X')

    def test_hit_without_interval_returns_false_and_does_not_click(self):
        # 已知瑕疵（本轮不修）：`isinstance(appear, tuple) and interval` —— interval 为空时
        # 即使 list_find 命中也返回 False 且不点击。真实调用方都传了 interval，未受影响。
        self.task.list_find = Mock(return_value=(5, 6))
        ret = self.task.list_appear_click(self.target, interval=None)
        self.assertIs(ret, False)
        self.task.device.click.assert_not_called()

    def test_miss_returns_false(self):
        self.task.list_find = Mock(return_value=False)
        ret = self.task.list_appear_click(self.target, interval=1)
        self.assertIs(ret, False)
        self.task.device.click.assert_not_called()
