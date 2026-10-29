# This Python file uses the following encoding: utf-8
"""悬赏封印新详情界面适配：详情判定 / 整行 OCR / 取消追踪出口 / 异常收尾的回归护栏。

测试用**真实 `ScriptTask` 方法 + 真实 `BaseTask.appear` / `appear_then_click` / `click`**，只替换外部边界：
`RuleImage.match`（按帧给出可见的规则名）、`RuleOcr.ocr` / `detect_text`（按规则名给文本）、设备点击、截图、
`sleep` 与 `Timer`（虚拟时钟）。`frames[n]` = 第 n 次截图之后可见的规则名集合，`frames[0]` = 进入前的当前帧。

离线图片匹配（状态区分）只在本机留有标注器抓图时运行，否则明确 skip，不假装测过。
"""

from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, skipUnless
from unittest.mock import Mock, patch

import cv2

from module.atom.image import RuleImage
from module.atom.ocr import RuleOcr
from module.exception import GameStuckError, TaskEnd
from tasks.WantedQuests import script_task as wq
from tasks.WantedQuests.config import WQType, WantedQuestsConfig
from tasks.WantedQuests.script_task import ScriptTask

A = ScriptTask  # 资源规则都是类属性
SHOT = 0.3

TRUE_, FALSE_ = A.I_TRACE_TRUE.name, A.I_TRACE_FALSE.name
BACK_RED = A.I_UI_BACK_RED.name
LIST_PAGE = A.I_CHECK_EXPLORATION.name
GOTO = [A.I_GOTO_1.name, A.I_GOTO_2.name, A.I_GOTO_3.name, A.I_GOTO_4.name]
ALL_GOTO = frozenset(GOTO)
INFO = [A.O_WQ_INFO_1.name, A.O_WQ_INFO_2.name, A.O_WQ_INFO_3.name, A.O_WQ_INFO_4.name]
TEXT_ALL = A.O_WQ_TEXT_ALL.name


class _VTimer:
    clock = None

    def __init__(self, limit, count=0):
        self.limit = limit
        self.count = count
        self._t0 = None

    def start(self):
        self._t0 = _VTimer.clock()
        return self

    def reached(self):
        return self._t0 is None or _VTimer.clock() - self._t0 > self.limit

    def reset(self):
        self._t0 = _VTimer.clock()
        return self


def names(*items):
    return frozenset(items)


class Sandbox(TestCase):
    PRIORITY = '挑战 > 秘闻 > 探索'

    def setUp(self):
        self.events = []
        self.now = 0.0
        self.n = 0
        _VTimer.clock = lambda: self.now
        self.frames = [frozenset()]
        self.ocr_texts = {}
        self.monster = ''
        self.tickets = 30
        self._old_executed = set(ScriptTask.wq_executed_set)
        ScriptTask.wq_executed_set = set()
        self._old_unwanted = ScriptTask.unwanted_boss_name_list
        ScriptTask.unwanted_boss_name_list = []
        self._old_area = list(A.O_WQ_TEXT_ALL.area)

    def tearDown(self):
        ScriptTask.wq_executed_set = self._old_executed
        ScriptTask.unwanted_boss_name_list = self._old_unwanted
        A.O_WQ_TEXT_ALL.area = self._old_area

    def make(self, frames=None, priority=None):
        if frames is not None:
            self.frames = frames
        events = self.events

        def screenshot():
            self.n += 1
            self.now += SHOT
            if self.n > 400:
                raise AssertionError('截图次数失控：可能出现了无界循环')
            events.append(('screenshot', self.n))

        def click(x, y, control_name):
            events.append(('click', control_name, round(self.now, 3)))

        task = ScriptTask.__new__(ScriptTask)
        task.interval_timer = {}
        task.screenshot = screenshot
        task.device = SimpleNamespace(
            image='F', image_frame_id=None, get_image_batch_cache=lambda *a, **k: None,
            click=Mock(side_effect=click),
        )
        wq_config = WantedQuestsConfig(battle_priority=priority or self.PRIORITY)
        task.config = SimpleNamespace(
            wanted_quests=SimpleNamespace(wanted_quests_config=wq_config),
            model=SimpleNamespace(wanted_quests=SimpleNamespace(wanted_quests_config=wq_config)),
        )
        task.swipe = Mock(side_effect=lambda s, interval=None: events.append(('swipe', s.name)))
        task.wq_skip_count = 0
        return task

    def current(self):
        return self.frames[min(self.n, len(self.frames) - 1)]

    def drive(self, fn):
        def fake_match(rule, image, threshold=None, frame_id=None):
            return rule.name in self.current()

        def fake_ocr(rule, image, keyword=None):
            value = self.ocr_texts.get(rule.name, '')
            return value(self) if callable(value) else value

        def sleep(seconds):
            self.events.append(('sleep', seconds))
            self.now += seconds

        with patch.object(RuleImage, 'match', fake_match), \
                patch.object(RuleOcr, 'ocr', fake_ocr), \
                patch.object(RuleOcr, 'detect_text', lambda rule, image: self.monster), \
                patch.object(wq, 'sleep', side_effect=sleep), patch('tasks.base_task.sleep', side_effect=sleep), \
                patch.object(wq, 'Timer', _VTimer), patch('tasks.base_task.Timer', _VTimer), \
                patch.object(wq, 'logger'):
            return fn()

    def of(self, kind):
        return [e for e in self.events if e[0] == kind]

    def clicked(self, name):
        return [e for e in self.of('click') if e[1] == name]


ROWS_OK = {
    INFO[0]: '式神碎片第十二章(数量:14)',
    INFO[1]: '探索 第十二章(数量:5)',
    INFO[2]: '秘闻 夜雪无声·壹(数量:3)',
    INFO[3]: '探索 第三章(数量:6)',
}


class ParseRowTextTest(TestCase):
    def parse(self, text):
        return ScriptTask.parse_wq_row_text(text)

    def test_type_labels_map_to_internal_types(self):
        cases = [
            ('式神碎片 第十二章(数量:14)', (WQType.CHALLENGE, '第十二章', 14)),
            ('式神第十二章(数量:14)', (WQType.CHALLENGE, '第十二章', 14)),   # 旧「式神」
            ('挑战第十二章(数量:14)', (WQType.CHALLENGE, '第十二章', 14)),
            ('探索 第三章(数量:6)', (WQType.EXPLORE, '第三章', 6)),
            ('秘闻 夜雪无声·壹(数量:3)', (WQType.SECRET, '夜雪无声·壹', 3)),
            ('秘闻河畔童谣·壹(数量:3)', (WQType.SECRET, '河畔童谣·壹', 3)),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(self.parse(text), expected)

    def test_tolerates_spaces_fullwidth_punctuation_and_trailing_quote(self):
        for text in ['探索 第 三 章 ( 数量 : 6 )', '探索第三章（数量：6）', '探索第三章(数量:6)"', '探索第三章数量:6']:
            with self.subTest(text=text):
                self.assertEqual(self.parse(text), (WQType.EXPLORE, '第三章', 6))

    def test_type_word_is_not_leaked_into_dest(self):
        _, dest, _ = self.parse('式神碎片第十二章(数量:14)')
        self.assertEqual(dest, '第十二章')

    def test_incomplete_or_wrong_text_is_not_guessed(self):
        for text in ['', '第十二章(数量:5)', '探素第三章(数量:6)', '探索(数量:5)', '探索第三章',
                     '探索第三章(数量:)', '探索第三章(数量:0)', '探索第三章(数量:1O)', '探索第三章(数量:6)前往',
                     '推荐探索第三章(数量:6)']:
            with self.subTest(text=text):
                self.assertIsNone(self.parse(text))


class RowReadingTest(Sandbox):
    def read(self, task, num_want=8):
        return self.drive(lambda: task.read_wq_rows(num_want))

    def test_row_binds_its_own_goto_button_when_other_row_fails(self):
        self.ocr_texts = {**ROWS_OK, INFO[1]: '乱码'}
        task = self.make([ALL_GOTO])
        readings = self.read(task)
        self.assertEqual([r.status for r in readings], ['ok', 'failed', 'ok', 'ok'])
        self.assertIs(readings[2].info.goto_btn, A.I_GOTO_3)
        self.assertIs(readings[3].info.goto_btn, A.I_GOTO_4)
        self.assertEqual(readings[2].info.type, WQType.SECRET)

    def test_do_num_keeps_ceil_semantics_and_never_divides_by_zero(self):
        self.ocr_texts = {**ROWS_OK, INFO[3]: '探索第三章(数量:0)'}
        task = self.make([ALL_GOTO])
        readings = self.read(task, num_want=8)
        self.assertEqual(readings[0].info.do_num, 1)   # ceil(8/14)
        self.assertEqual(readings[1].info.do_num, 2)   # ceil(8/5)
        self.assertEqual(readings[2].info.do_num, 3)   # ceil(8/3)
        self.assertEqual(readings[3].status, 'failed')  # 数量 0 不能算有效数据

    def test_missing_row_without_goto_button_is_absent_not_failed(self):
        self.ocr_texts = {INFO[0]: ROWS_OK[INFO[0]]}
        task = self.make([names(GOTO[0])])
        statuses = [r.status for r in self.read(task)]
        self.assertEqual(statuses, ['ok', 'absent', 'absent', 'absent'])

    def test_text_without_goto_button_is_a_failure(self):
        self.ocr_texts = dict(ROWS_OK)
        task = self.make([names(GOTO[0], GOTO[1], GOTO[3])])   # 第 3 行有字但没有前往按钮
        statuses = [r.status for r in self.read(task)]
        self.assertEqual(statuses, ['ok', 'ok', 'failed', 'ok'])

    def test_rule_filters_are_reported_as_filtered_not_failed(self):
        self.ocr_texts = {
            INFO[0]: '秘闻 夜雪无声·捌(数量:3)',      # 高层秘闻
            INFO[1]: '探索 第三章(数量:6)',          # 不在优先级里（见下方 priority）
            INFO[2]: '妖气 某处(数量:2)',             # 类型存在但不在优先级里
            INFO[3]: '探索 第三章(数量:6)',
        }
        task = self.make([ALL_GOTO], priority='挑战 > 秘闻')
        readings = self.read(task)
        self.assertEqual([r.status for r in readings], ['filtered'] * 4)
        self.assertEqual(readings[0].reason, 'high secret layer')

    def test_executed_target_is_filtered(self):
        self.ocr_texts = dict(ROWS_OK)
        task = self.make([ALL_GOTO])
        first = self.read(task)[1].info
        ScriptTask.wq_executed_set.add(first)
        again = self.read(task)
        self.assertEqual(again[1].status, 'filtered')
        self.assertEqual(again[1].reason, 'already executed')

    def test_priority_order_challenge_then_secret_then_explore(self):
        self.ocr_texts = dict(ROWS_OK)
        task = self.make([ALL_GOTO])
        infos = self.drive(lambda: task.get_ordered_wq_infos(8))
        self.assertEqual([i.type for i in infos],
                         [WQType.CHALLENGE, WQType.SECRET, WQType.EXPLORE, WQType.EXPLORE])


class OpenDetailTest(Sandbox):
    def open(self, task):
        return self.drive(task.open_wq_info)

    def test_new_trace_true_confirms_detail_and_stops_clicking_the_list(self):
        # frames[0] = 进入前；frames[1] / [2] 还是列表，frames[3] 起详情出现
        task = self.make([names(), names(), names(), names(TRUE_), names(TRUE_)])
        self.assertTrue(self.open(task))
        self.assertEqual(len(self.clicked(TEXT_ALL)), 1)
        # 详情出现（第 3 次截图）之后不再有任何点击
        after = self.events[self.events.index(('screenshot', 3)):]
        self.assertEqual([e for e in after if e[0] == 'click'], [])
        self.assertEqual(self.n, 3)

    def test_untracked_detail_is_also_recognized_as_opened(self):
        task = self.make([names(), names(FALSE_)])
        self.assertTrue(self.open(task))

    def test_detail_appearing_after_the_last_click_is_still_confirmed(self):
        # 5 秒窗口内（17 次截图）一直没有详情，窗口结束后补的那一次新截图才出现 → 仍然确认
        task = self.make([names()] * 18 + [names(TRUE_)])
        self.assertTrue(self.open(task))
        self.assertEqual(self.n, 18)

    def test_never_opened_returns_false_with_bounded_clicks(self):
        task = self.make([names()])
        self.assertFalse(self.open(task))
        self.assertLessEqual(len(self.clicked(TEXT_ALL)), 6)
        self.assertLessEqual(self.n, 40)
        self.assertEqual(self.of('swipe'), [])


class CancelTraceTest(Sandbox):
    def cancel(self, task):
        return self.drive(task.cancel_wq_trace)

    def test_cancel_then_untracked_detail_is_closed_back_to_list(self):
        frames = [names(), names(TRUE_), names(FALSE_), names(FALSE_, BACK_RED), names(LIST_PAGE), names(LIST_PAGE)]
        task = self.make(frames)
        self.assertTrue(self.cancel(task))
        self.assertEqual(len(self.clicked(TRUE_)), 1)
        self.assertGreaterEqual(len(self.clicked(BACK_RED)), 1)

    def test_cancel_that_closes_detail_needs_list_confirmed_on_consecutive_frames(self):
        task = self.make([names(), names(TRUE_), names(LIST_PAGE), names(LIST_PAGE)])
        self.assertTrue(self.cancel(task))
        self.assertEqual(len(self.clicked(TRUE_)), 1)

    def test_trace_true_vanishing_for_one_frame_is_not_a_success(self):
        # TRUE 点击后只消失一帧（过渡画面），随后又回来：不能算取消成功，也不能无限点击
        frames = [names(), names(TRUE_), names(), names(TRUE_), names(), names(TRUE_), names(), names(TRUE_), names()]
        task = self.make(frames)
        self.assertFalse(self.cancel(task))
        self.assertLessEqual(len(self.clicked(TRUE_)), A.WQ_CANCEL_MAX_CLICKS)

    def test_cancel_not_taking_effect_gives_up_after_bounded_clicks(self):
        task = self.make([names(TRUE_)])
        self.assertFalse(self.cancel(task))
        self.assertEqual(len(self.clicked(TRUE_)), A.WQ_CANCEL_MAX_CLICKS)
        self.assertLessEqual(self.n, 60)

    def test_stuck_on_untracked_detail_without_close_button_fails_boundedly(self):
        task = self.make([names(FALSE_)])
        self.assertFalse(self.cancel(task))
        self.assertEqual(self.clicked(BACK_RED), [])   # 红叉没出现就不盲点
        self.assertLessEqual(self.n, 60)

    def test_list_visible_without_any_cancel_evidence_is_not_success(self):
        task = self.make([names(LIST_PAGE)])
        self.assertFalse(self.cancel(task))

    def test_unknown_page_is_not_success(self):
        task = self.make([names()])
        self.assertFalse(self.cancel(task))
        self.assertEqual(self.of('click'), [])


class ExecuteMissionTest(Sandbox):
    def setUp(self):
        super().setUp()
        self.ocr_texts = dict(ROWS_OK)
        self.ocr_texts[A.O_WQ_NUMBER.name] = lambda sb: sb.tickets

    def mission(self, frames=None, priority=None, num_want=8):
        task = self.make(frames or [ALL_GOTO], priority=priority)
        task.challenge = Mock()
        task.explore = Mock()
        task.secret = Mock()
        task.goto_page = Mock()
        task.cancel_wq_trace = Mock(return_value=True)
        self.drive(lambda: task.execute_mission(num_want))
        return task

    def test_executes_highest_priority_candidate_with_its_own_button(self):
        task = self.mission()
        task.challenge.assert_called_once()
        self.assertIs(task.challenge.call_args.args[0], A.I_GOTO_1)
        self.assertEqual(task.challenge.call_args.args[1], 1)
        task.cancel_wq_trace.assert_not_called()

    def test_failed_second_row_does_not_shift_third_row_button(self):
        self.ocr_texts.update({INFO[0]: '乱码', INFO[1]: '乱码'})
        task = self.mission()
        task.secret.assert_called_once()
        self.assertIs(task.secret.call_args.args[0], A.I_GOTO_3)

    def test_challenge_ticket_condition_falls_back_to_next_candidate(self):
        self.tickets = 4
        task = self.mission()
        task.challenge.assert_not_called()
        self.assertIs(task.secret.call_args.args[0], A.I_GOTO_3)

    def test_unwanted_monster_is_an_explicit_skip(self):
        ScriptTask.unwanted_boss_name_list = ['酒吞童子']
        self.monster = '酒吞童子'
        task = self.mission()
        task.cancel_wq_trace.assert_called_once()
        task.challenge.assert_not_called()

    def test_missing_goto_button_is_secret_not_unlocked_skip(self):
        task = self.mission(frames=[names()])
        task.cancel_wq_trace.assert_called_once()
        task.explore.assert_not_called()

    def test_all_rows_filtered_by_rules_is_a_skip_not_an_error(self):
        self.ocr_texts.update({
            INFO[0]: '秘闻 夜雪无声·玖(数量:3)', INFO[1]: '秘闻 夜雪无声·拾(数量:3)',
            INFO[2]: '秘闻 夜雪无声·捌(数量:3)', INFO[3]: '秘闻 夜雪无声·番外(数量:3)',
        })
        task = self.mission()
        task.cancel_wq_trace.assert_called_once()
        task.secret.assert_not_called()

    def test_all_rows_unreadable_is_an_error_and_never_cancels_the_quest(self):
        self.ocr_texts.update({k: '' for k in INFO})
        task = self.make([ALL_GOTO])
        task.cancel_wq_trace = Mock(return_value=True)
        with self.assertRaises(GameStuckError):
            self.drive(lambda: task.execute_mission(8))
        task.cancel_wq_trace.assert_not_called()
        self.assertEqual(self.of('click'), [])

    def test_unreadable_vs_filtered_have_different_outcomes(self):
        # 同样是「没有可执行候选」：识别失败抛异常、规则过滤取消追踪
        unreadable = self.make([ALL_GOTO])
        unreadable.cancel_wq_trace = Mock(return_value=True)
        self.ocr_texts.update({k: '乱码' for k in INFO})
        with self.assertRaises(GameStuckError):
            self.drive(lambda: unreadable.execute_mission(8))
        self.ocr_texts.update({k: '探索 第三章(数量:6)' for k in INFO})
        filtered = self.make([ALL_GOTO], priority='挑战 > 秘闻')
        filtered.cancel_wq_trace = Mock(return_value=True)
        filtered.goto_page = Mock()
        self.drive(lambda: filtered.execute_mission(8))
        filtered.cancel_wq_trace.assert_called_once()

    def test_cancel_failure_raises_instead_of_pretending_skip(self):
        ScriptTask.unwanted_boss_name_list = ['酒吞童子']
        self.monster = '酒吞童子'
        task = self.make([ALL_GOTO])
        task.cancel_wq_trace = Mock(return_value=False)
        with self.assertRaises(GameStuckError):
            self.drive(lambda: task.execute_mission(8))

    def test_skip_cap_prevents_endless_reopen_of_same_quest(self):
        ScriptTask.unwanted_boss_name_list = ['酒吞童子']
        self.monster = '酒吞童子'
        task = self.make([ALL_GOTO])
        task.cancel_wq_trace = Mock(return_value=True)
        task.wq_skip_count = A.WQ_MAX_SKIPS
        with self.assertRaises(GameStuckError):
            self.drive(lambda: task.execute_mission(8))


class RunLoopTest(Sandbox):
    """`run()` 主循环的收尾语义：详情打不开 / 正常完成 / 跳过后继续。"""

    def loop_task(self, remained, found, frames, execute=None):
        task = self.make(frames)
        task.switch_mission_souls = Mock()
        task.pre_work = Mock(return_value=True)
        task.is_wq_remained = Mock(side_effect=remained)
        task.find_wq = Mock(side_effect=found)
        task.next_run = Mock()
        task.execute_mission = Mock(side_effect=execute)
        task.O_WQ_TEXT_ALL = SimpleNamespace(name=TEXT_ALL, area=[0, 0, 0, 0], coord=A.O_WQ_TEXT_ALL.coord)
        return task

    def run_loop(self, task):
        return self.drive(task.run)

    def test_unfinished_progress_but_detail_never_opens_raises_and_is_not_scheduled_tomorrow(self):
        task = self.loop_task(lambda *a: True, lambda *a, **k: (0, 1, 8, [38, 179, 36, 21]), [names()])
        task.O_WQ_TEXT_ALL = A.O_WQ_TEXT_ALL
        with self.assertRaises(GameStuckError):
            self.run_loop(task)
        task.next_run.assert_not_called()
        task.execute_mission.assert_not_called()
        self.assertEqual(self.of('swipe'), [])          # 不靠滑动列表掩盖
        self.assertLessEqual(self.n, 300)

    def test_confirmed_no_remaining_quest_still_schedules_normally(self):
        task = self.loop_task(lambda *a: False, lambda *a, **k: (-1, -1, -1, [0, 0, 0, 0]), [names()])
        with self.assertRaises(TaskEnd):
            self.run_loop(task)
        task.next_run.assert_called_once()

    def test_no_unfinished_after_scrolling_is_still_a_normal_finish(self):
        task = self.loop_task(lambda *a: True, lambda *a, **k: (-1, -1, -1, [0, 0, 0, 0]), [names()])
        with self.assertRaises(TaskEnd):
            self.run_loop(task)
        task.next_run.assert_called_once()
        self.assertEqual(len(self.of('swipe')), A.WQ_LIST_MAX_SCROLLS)

    def test_after_skip_the_loop_continues_with_next_quest_without_swiping(self):
        remained = iter([True, True, False])
        founds = iter([(0, 1, 8, [38, 179, 36, 21]), (0, 1, 10, [38, 250, 36, 21])])
        task = self.loop_task(lambda *a: next(remained), lambda *a, **k: next(founds),
                              [names(TRUE_)])
        task.O_WQ_TEXT_ALL = A.O_WQ_TEXT_ALL
        with self.assertRaises(TaskEnd):
            self.run_loop(task)
        self.assertEqual(task.execute_mission.call_count, 2)
        self.assertEqual(task.execute_mission.call_args_list[0].args, (8,))
        self.assertEqual(task.execute_mission.call_args_list[1].args, (10,))
        task.next_run.assert_called_once()
        self.assertEqual(self.of('swipe'), [])


_CAPTURES = Path(__file__).resolve().parents[1] / 'log' / 'annotator' / '8082d16afe8f4091bb2be3f10c71faa9' / 'captures'
_TRACKED = _CAPTURES / 'capture_1793175113186.png'
_UNTRACKED = _CAPTURES / 'capture_1793177328690.png'
_LIST = _CAPTURES / 'capture_1793174242637.png'


def _score(rule, image):
    return float(cv2.matchTemplate(rule.corp(image), rule.image, cv2.TM_CCOEFF_NORMED).max())


@skipUnless(_TRACKED.exists() and _UNTRACKED.exists() and _LIST.exists(), '本机没有标注器抓图，状态区分未验证')
class OfflineTemplateStateTest(TestCase):
    """用用户标注时抓的真实截图验证两个状态的模板互不命中（纯 cv2，不走任何服务）。"""

    def test_tracked_and_untracked_detail_do_not_cross_match(self):
        tracked = cv2.imread(str(_TRACKED))
        untracked = cv2.imread(str(_UNTRACKED))
        self.assertGreater(_score(A.I_TRACE_TRUE, tracked), A.I_TRACE_TRUE.threshold)
        self.assertLess(_score(A.I_TRACE_FALSE, tracked), 0.5)
        self.assertGreater(_score(A.I_TRACE_FALSE, untracked), A.I_TRACE_FALSE.threshold)
        self.assertLess(_score(A.I_TRACE_TRUE, untracked), 0.5)

    def test_detail_markers_do_not_hit_the_list_page_and_close_button_hits_detail(self):
        listing = cv2.imread(str(_LIST))
        detail = cv2.imread(str(_TRACKED))
        self.assertLess(_score(A.I_TRACE_TRUE, listing), A.I_TRACE_TRUE.threshold)
        self.assertLess(_score(A.I_TRACE_FALSE, listing), A.I_TRACE_FALSE.threshold)
        self.assertGreater(_score(A.I_UI_BACK_RED, detail), A.I_UI_BACK_RED.threshold)
        self.assertGreater(_score(A.I_CHECK_EXPLORATION, listing), A.I_CHECK_EXPLORATION.threshold)
        self.assertLess(_score(A.I_CHECK_EXPLORATION, detail), 0.5)   # 详情盖住列表页标识
