# This Python file uses the following encoding: utf-8
"""组队会合（D030）：`module/instance_sync/team.py` + `module/script/team_sync.py` + `Script.loop` 接入。

- 判断：`decide()` 是纯函数，逐行覆盖「对方状态 → 开始 / 等 / 推迟」的表，以及两个组队任务卡住时只有一边让。
- 在场文件：读写往返、坏文件 / 缺文件当不在线、心跳只刷新时间。
- 会合：两个真实 PresenceBoard 共用临时目录，在两个线程里各自等，验证同时到、一先一后、对方不在线、配置变了中断。
- 胶水：用真实配置模型判断身份；没开同步时不写任何文件；出错放行。
- 调度器：真实 `Script.loop` + 真实 `Config.task_delay`（临时目录），组队任务推迟后不执行、非组队任务照常执行。
"""

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.config.config_model import ConfigModel
from module.instance_sync import team
from module.instance_sync.team import (
    ABORT, GO, IDLE, POSTPONE, RUNNING, UNREADABLE, WAIT, WAITING, PresenceBoard, Progress, TeamSession,
    clear_session, decide, get_session, rendezvous, set_session,
)
from module.script.team_sync import TeamSync, task_role, team_tasks

NOW = datetime(2026, 10, 22, 14, 0, 0)
_REPO = Path(__file__).resolve().parents[1]


def entry(role, next_run=NOW - timedelta(minutes=5), enable=True):
    return {'role': role, 'enable': enable, 'next_run': next_run}


def me(task='Orochi', role='leader', since=NOW, tasks=None, instance='oas2', token='tok-me', started_at=None):
    return {'instance': instance, 'task': task, 'role': role, 'token': token, 'since': since,
            'team_tasks': tasks if tasks is not None else {'Orochi': entry('leader')}, 'started_at': started_at}


def peer(state=RUNNING, task='DailyTrifles', tasks=None, updated_at=NOW, instance='oas1', paired='oas2', **extra):
    doc = {'version': 1, 'instance': instance, 'peer': paired, 'state': state, 'task': task, 'role': None,
           'token': None, 'since': None, 'until': None, 'partner_token': None, 'updated_at': updated_at,
           'team_tasks': tasks if tasks is not None else {'Orochi': entry('member')}}
    doc.update(extra)
    return doc


class DecideTest(unittest.TestCase):
    def check(self, p, action, reason, until=None, mine=None):
        d = decide(mine or me(), p, NOW)
        self.assertEqual((d.action, d.reason), (action, reason))
        if until is not None:
            self.assertEqual(d.until, until)
        return d

    def test_peer_offline_or_not_paired_postpones_ten_minutes(self):
        self.check(None, POSTPONE, 'peer_offline', NOW + timedelta(minutes=10))
        self.check(peer(updated_at=NOW - timedelta(minutes=6)), POSTPONE, 'peer_offline')
        self.check(peer(updated_at=NOW - timedelta(seconds=59)), WAIT, 'peer_busy')
        self.check(peer(paired='oas3'), POSTPONE, 'peer_not_paired', NOW + timedelta(minutes=10))

    def test_just_expired_peer_is_probably_restarting_so_wait_instead_of_postponing(self):
        # 10-23 10:40：两边一起重启，先起来的一边读到对方旧进程留下的文件（2.5 分钟前），不能推迟 + 推送「不在线」
        self.check(peer(updated_at=NOW - timedelta(seconds=61)), WAIT, 'peer_reconnecting')
        self.check(peer(updated_at=NOW - timedelta(seconds=150)), WAIT, 'peer_reconnecting')
        self.check(peer(updated_at=NOW - timedelta(seconds=299)), WAIT, 'peer_reconnecting')
        self.check(peer(updated_at=NOW - timedelta(seconds=301)), POSTPONE, 'peer_offline')

    def test_stale_peer_file_is_never_trusted_as_a_meeting(self):
        # 旧文件里即使写着「在同一个门口等」或「已带着我开始」，也只等它重新写，不能当成会合
        old = NOW - timedelta(seconds=150)
        self.check(peer(state=WAITING, task='Orochi', role='member', token='tok-peer', updated_at=old),
                   WAIT, 'peer_reconnecting')
        self.check(peer(task='Orochi', partner_token='tok-me', updated_at=old), WAIT, 'peer_reconnecting')

    def test_unreadable_peer_waits_one_more_poll(self):
        self.check(UNREADABLE, WAIT, 'peer_unreadable')

    def test_meeting_at_the_same_door_starts_only_with_complementary_roles(self):
        self.check(peer(state=WAITING, task='Orochi', role='member', token='tok-peer'), GO, 'met')
        self.check(peer(state=WAITING, task='Orochi', role='leader'), POSTPONE, 'role_conflict',
                   NOW + timedelta(minutes=30))

    def test_freshly_started_process_waits_for_a_peer_that_is_not_there_yet(self):
        # 10-23 11:23：两边停了 43 分钟后一起启动，先起来的一边读到对方 43 分钟前的旧文件，不能推迟 + 推送
        long_gone = peer(updated_at=NOW - timedelta(minutes=43))
        for age in (0, 10, 179):
            with self.subTest(started_seconds_ago=age):
                mine = me(started_at=NOW - timedelta(seconds=age))
                self.check(None, WAIT, 'peer_starting', mine=mine)
                self.check(long_gone, WAIT, 'peer_starting', mine=mine)
        # 宽限过了对方还没来：照旧推迟
        late = me(started_at=NOW - timedelta(seconds=181))
        self.check(None, POSTPONE, 'peer_offline', NOW + timedelta(minutes=10), mine=late)
        self.check(long_gone, POSTPONE, 'peer_offline', mine=late)
        # 没有启动时刻（不是脚本进程的调用方）不受影响
        self.check(long_gone, POSTPONE, 'peer_offline', mine=me(started_at=None))

    def test_startup_grace_only_covers_the_offline_tier(self):
        mine = me(started_at=NOW - timedelta(seconds=10))
        # 只过期 2 分钟仍是「重启中」那一档，分档不乱
        self.check(peer(updated_at=NOW - timedelta(seconds=120)), WAIT, 'peer_reconnecting', mine=mine)
        # 对方在线但没把我填成对方：不是时间问题，刚启动也照旧推迟
        self.check(peer(paired='oas3'), POSTPONE, 'peer_not_paired', mine=mine)

    def test_peer_already_running_the_task(self):
        self.check(peer(task='Orochi', partner_token='tok-me'), GO, 'peer_started_with_me')
        # 10-23 11:25：我刚重启，对方文件还写着和我旧进程那一次组队。不推迟，进门等它重新进门 / 看到我在等
        self.check(peer(task='Orochi', partner_token='someone-else'), WAIT, 'peer_running_alone')

    def test_peer_busy_with_another_task_and_ours_is_due_keeps_waiting(self):
        # 用户要的场景：对方还在做上一个任务，这个组队任务在它那边已经到点
        self.check(peer(), WAIT, 'peer_busy')
        # 两边 next_run 差几秒很常见，一分钟内都算到点
        self.check(peer(tasks={'Orochi': entry('member', NOW + timedelta(seconds=50))}), WAIT, 'peer_busy')

    def test_peer_not_due_waits_and_will_be_pulled(self):
        # 10-23 两边 Orochi 互推：以前按对方的计划时间推迟自己，两边被推到同一个较晚时间后谁也提前不了
        later = NOW + timedelta(hours=20)
        self.check(peer(tasks={'Orochi': entry('member', later)}), WAIT, 'peer_busy')        # 对方跑完别的再来
        idle = peer(state=IDLE, task='Orochi', until=later, tasks={'Orochi': entry('member', later)})
        self.check(idle, WAIT, 'pull_peer')                                                  # 对方空闲：拉过来

    def test_task_off_or_not_a_team_task_on_peer(self):
        self.check(peer(tasks={}), POSTPONE, 'peer_task_off', NOW + timedelta(minutes=30))
        self.check(peer(tasks={'Orochi': entry('member', enable=False)}), POSTPONE, 'peer_task_off')

    def test_same_role_in_snapshot_is_a_config_error(self):
        self.check(peer(tasks={'Orochi': entry('leader')}), POSTPONE, 'role_conflict')

    def test_idle_peer(self):
        far = NOW + timedelta(hours=2)
        # 空闲的对方下一个任务排在以后：照样等，对方会被拉过来
        self.check(peer(state=IDLE, task='Duel', until=far), WAIT, 'pull_peer')
        self.check(peer(state=IDLE, task='Duel', until=NOW + timedelta(seconds=30)), WAIT, 'pull_peer')
        self.check(peer(state=IDLE, task='Orochi', until=NOW - timedelta(seconds=5)), WAIT, 'pull_peer')

    def test_resting_peer_postpones_to_the_end_of_its_rest(self):
        far = NOW + timedelta(hours=2)
        self.check(peer(state=IDLE, task='Orochi', until=far, rest_until=far), POSTPONE, 'peer_resting', far)
        # 一分钟内就醒：当作马上来，照样等
        self.check(peer(state=IDLE, task='Orochi', rest_until=NOW + timedelta(seconds=30)), WAIT, 'pull_peer')
        # 已经在门口等我的对方不算休息
        self.check(peer(state=WAITING, task='Orochi', role='member', rest_until=far), GO, 'met')
        # 旧版本写的在场文件没有这个字段：当作不在休息
        old = peer(state=IDLE, task='Duel', until=far)
        old.pop('rest_until', None)
        self.check(old, WAIT, 'pull_peer')

    def test_two_team_tasks_deadlock_exactly_one_side_yields(self):
        both_due = {'Orochi': entry('leader'), 'BondlingFairyland': entry('member')}
        peer_due = {'Orochi': entry('member'), 'BondlingFairyland': entry('leader')}
        cases = [
            (NOW, NOW + timedelta(seconds=3), WAIT),       # 我先到，对方让
            (NOW + timedelta(seconds=3), NOW, POSTPONE),   # 对方先到，我让
            (NOW, NOW, POSTPONE),                          # 同时到，实例名大的（我 oas2）让
        ]
        for mine_since, peer_since, expected in cases:
            with self.subTest(mine=mine_since, peer=peer_since):
                a = me(task='Orochi', since=mine_since, tasks=both_due)
                b = peer(state=WAITING, task='BondlingFairyland', role='leader', since=peer_since, tasks=peer_due)
                da = decide(a, b, NOW)
                # 对方视角：把两边对调
                a_doc = peer(state=WAITING, task='Orochi', role='leader', since=mine_since, tasks=both_due,
                             instance='oas2', paired='oas1')
                b_me = me(task='BondlingFairyland', role='leader', since=peer_since, tasks=peer_due,
                          instance='oas1')
                db = decide(b_me, a_doc, NOW)
                self.assertEqual(da.action, expected, da)
                self.assertEqual(sorted([da.action, db.action]), [POSTPONE, WAIT], (da, db))
                for d in (da, db):
                    if d.action == POSTPONE:
                        self.assertEqual((d.reason, d.until), ('yield_to_peer', NOW + timedelta(minutes=3)))

    def test_peer_in_a_paired_task_that_is_due_on_me_makes_me_yield(self):
        # 对方在同心之兰里等我进场，我却在御魂门口等它：我得先让开
        xinlan_due = me(tasks={'Orochi': entry('leader'), 'XinLan': entry('pair')})
        self.check(peer(task='XinLan'), POSTPONE, 'yield_to_paired_task', NOW + timedelta(minutes=3), mine=xinlan_due)
        self.check(peer(state=IDLE, task='XinLan', until=NOW), POSTPONE, 'yield_to_paired_task', mine=xinlan_due)
        # 同心之兰在我这边还要好几分钟才到点：先照常等；到点之后（每轮按当前时间重判）改成让路
        later = me(tasks={'Orochi': entry('leader'), 'XinLan': entry('pair', NOW + timedelta(minutes=5))})
        self.check(peer(task='XinLan'), WAIT, 'peer_busy', mine=later)
        then = NOW + timedelta(minutes=5)
        self.assertEqual(decide(later, peer(task='XinLan', updated_at=then), then).reason, 'yield_to_paired_task')
        # 对方在跑的是普通任务，或同心之兰在我这边没开：不受影响
        self.check(peer(task='Duel'), WAIT, 'peer_busy', mine=xinlan_due)
        off = me(tasks={'Orochi': entry('leader'), 'XinLan': entry('pair', enable=False)})
        self.check(peer(task='XinLan'), WAIT, 'peer_busy', mine=off)

    def test_bondling_handoff_roles_pair_with_each_other_only(self):
        mine = me(task='BondlingFairyland', role='handoff1', tasks={'BondlingFairyland': entry('handoff1')})
        snap = {'BondlingFairyland': entry('handoff2')}
        self.check(peer(state=WAITING, task='BondlingFairyland', role='handoff2', tasks=snap), GO, 'met', mine=mine)
        self.check(peer(state=WAITING, task='BondlingFairyland', role='handoff1', tasks=snap), POSTPONE,
                   'role_conflict', mine=mine)
        self.check(peer(state=WAITING, task='BondlingFairyland', role='member', tasks=snap), POSTPONE,
                   'role_conflict', mine=mine)
        self.check(peer(tasks=snap), WAIT, 'peer_busy', mine=mine)
        self.check(peer(tasks={'BondlingFairyland': entry('leader')}), POSTPONE, 'role_conflict', mine=mine)

    def test_paired_task_is_never_a_door_on_the_peer_side(self):
        self.check(peer(tasks={'Orochi': entry('pair')}), POSTPONE, 'peer_task_off')

    def test_two_team_tasks_where_only_one_is_due_on_the_other_side(self):
        # 对方等的那个任务在我这边没到点：不再看到没到点（没有人会因为没到点推迟了），照样后到的让，
        # 让的一方回到调度器会被对方拉进它等的任务
        mine = me(tasks={'Orochi': entry('leader'),
                         'BondlingFairyland': entry('member', NOW + timedelta(hours=3))})
        earlier = peer(state=WAITING, task='BondlingFairyland', role='leader', since=NOW - timedelta(minutes=5))
        self.check(earlier, POSTPONE, 'yield_to_peer', NOW + timedelta(minutes=3), mine=mine)
        later = peer(state=WAITING, task='BondlingFairyland', role='leader', since=NOW + timedelta(seconds=5))
        self.check(later, WAIT, 'peer_will_yield', mine=mine)


class BoardTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='oas_team_'))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.a = PresenceBoard(self.root, 'oas1', 'oas2')
        self.b = PresenceBoard(self.root, 'oas2', 'oas1')

    def test_round_trip(self):
        tasks = {'Orochi': entry('member', datetime(2026, 10, 23, 13, 39, 57))}
        self.assertTrue(self.a.publish(IDLE, tasks, task='Orochi', until=datetime(2026, 10, 23, 13, 39, 57)))
        got = self.b.read_peer()
        self.assertEqual((got['instance'], got['peer'], got['state'], got['task']), ('oas1', 'oas2', IDLE, 'Orochi'))
        self.assertEqual(got['team_tasks'], tasks)
        self.assertEqual(got['until'], datetime(2026, 10, 23, 13, 39, 57))
        self.assertIsNone(got['rest_until'])
        self.assertIsInstance(got['updated_at'], datetime)
        self.a.publish(IDLE, tasks, task='Orochi', rest_until=datetime(2026, 10, 23, 23, 0, 0))
        self.assertEqual(self.b.read_peer()['rest_until'], datetime(2026, 10, 23, 23, 0, 0))

    def test_progress_round_trip_survives_heartbeat_and_is_cleared_by_a_new_state(self):
        self.assertFalse(self.a.report_progress(1))                 # 还没发布过就不写
        self.a.publish(RUNNING, {}, task='Orochi')
        self.assertIsNone(self.b.read_peer()['progress'])
        self.assertTrue(self.a.report_progress(3))
        self.assertEqual(self.b.read_peer()['progress'], {'count': 3, 'done': False})
        self.a.heartbeat()
        self.assertEqual(self.b.read_peer()['progress'], {'count': 3, 'done': False})
        self.a.report_progress(5, True)
        self.assertEqual(self.b.read_peer()['progress'], {'count': 5, 'done': True})
        self.a.publish(IDLE, {}, task='Orochi')                       # 换状态：上一次的进度不能留给下一次
        self.assertIsNone(self.b.read_peer()['progress'])

    def test_malformed_progress_is_ignored_not_fatal(self):
        self.a.publish(RUNNING, {}, task='Orochi')
        for bad in ('x', {'count': 'many'}, {'count': True}, {'done': True}, [1]):
            with self.subTest(bad=bad):
                raw = json.loads(self.a.path.read_text(encoding='utf-8'))
                raw['progress'] = bad
                self.a.path.write_text(json.dumps(raw), encoding='utf-8')
                got = self.b.read_peer()
                self.assertIsNotNone(got)
                self.assertIsNone(got['progress'])

    def test_missing_or_corrupt_peer_file_counts_as_offline(self):
        self.assertIsNone(self.b.read_peer())
        (self.root / 'team').mkdir(parents=True, exist_ok=True)
        (self.root / 'team' / 'oas1.json').write_text('{not json', encoding='utf-8')
        self.assertIsNone(self.b.read_peer())
        (self.root / 'team' / 'oas1.json').write_text(json.dumps({'version': 9}), encoding='utf-8')
        self.assertIsNone(self.b.read_peer())

    def test_heartbeat_only_refreshes_the_time(self):
        self.assertFalse(self.a.heartbeat())      # 还没发布过就不写
        self.assertFalse(self.a.path.exists())
        times = iter([NOW, NOW + timedelta(seconds=10)])
        self.a.clock = lambda: next(times)
        self.a.publish(RUNNING, {}, task='Duel')
        self.a.heartbeat()
        got = self.b.read_peer()
        self.assertEqual((got['state'], got['task'], got['updated_at']), (RUNNING, 'Duel', NOW + timedelta(seconds=10)))

    def test_step_writes_the_matching_state(self):
        tasks = {'Orochi': entry('leader')}
        m = me(instance='oas2', tasks=tasks)
        b = PresenceBoard(self.root, 'oas2', 'oas1')
        self.assertEqual(b.step(m).action, POSTPONE)              # 对方不在线
        self.assertEqual(self.a.read_peer()['state'], IDLE)
        self.a.publish(RUNNING, {'Orochi': entry('member')}, task='Duel')
        self.assertEqual(b.step(m).action, WAIT)
        self.assertEqual(self.a.read_peer()['state'], WAITING)
        self.assertEqual(b.step(m, abort=True).action, ABORT)
        self.assertEqual(self.a.read_peer()['state'], IDLE)


class RendezvousTest(unittest.TestCase):
    """两个真实 PresenceBoard 共用临时目录，各在一个线程里等；所有等待都有硬超时。"""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='oas_team_rv_'))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.a = PresenceBoard(self.root, 'oas1', 'oas2')
        self.b = PresenceBoard(self.root, 'oas2', 'oas1')
        self.tasks_a = {'Orochi': entry('member')}
        self.tasks_b = {'Orochi': entry('leader')}

    def run_side(self, board, role, tasks, results, key, delay=0.0, should_abort=lambda: False):
        def go():
            time.sleep(delay)
            results[key] = rendezvous(board, 'Orochi', role, tasks, should_abort=should_abort, poll=0.01)
        t = threading.Thread(target=go, daemon=True)
        t.start()
        return t

    def join(self, *threads):
        for t in threads:
            t.join(10)
            self.assertFalse(t.is_alive(), 'rendezvous did not finish')

    def test_arrive_together_or_one_after_another(self):
        for delay_a, delay_b in ((0, 0), (0, 0.2), (0.2, 0), (0.05, 0.06)):
            with self.subTest(a=delay_a, b=delay_b):
                # 后到的一方之前在跑别的任务：先发布 running，对方会一直等
                self.a.publish(RUNNING, self.tasks_a, task='Duel')
                self.b.publish(RUNNING, self.tasks_b, task='Duel')
                results = {}
                self.join(self.run_side(self.a, 'member', self.tasks_a, results, 'a', delay_a),
                          self.run_side(self.b, 'leader', self.tasks_b, results, 'b', delay_b))
                self.assertEqual((results['a'].action, results['b'].action), (GO, GO), results)
                pa, pb = self.b.read_peer(), self.a.read_peer()
                self.assertEqual((pa['state'], pb['state']), (RUNNING, RUNNING))
                # 两边记下的搭档就是对方这一次的 token
                self.assertEqual(pa['partner_token'], pb['token'])
                self.assertEqual(pb['partner_token'], pa['token'])

    def test_waits_while_peer_is_busy_with_its_previous_task(self):
        self.b.publish(RUNNING, self.tasks_b, task='RealmRaid')
        stop_beat = threading.Event()

        def beat():   # 对方任务执行中，心跳线程一直在刷
            while not stop_beat.wait(0.02):
                self.b.heartbeat()
        threading.Thread(target=beat, daemon=True).start()
        self.addCleanup(stop_beat.set)
        results = {}
        ta = self.run_side(self.a, 'member', self.tasks_a, results, 'a')
        time.sleep(0.3)
        self.assertNotIn('a', results)           # 对方没做完就一直等
        self.join(self.run_side(self.b, 'leader', self.tasks_b, results, 'b'), ta)
        self.assertEqual((results['a'].action, results['b'].action), (GO, GO))

    def test_yields_once_its_own_paired_task_comes_due_while_waiting(self):
        # B 在同心之兰里等 A；A 在御魂门口，A 的同心之兰 0.3 秒后才进入「到点」范围
        self.b.publish(RUNNING, self.tasks_b, task='XinLan')
        soon = datetime.now() + team.DUE_GRACE + timedelta(seconds=0.3)
        tasks_a = {'Orochi': entry('member'), 'XinLan': entry('pair', soon)}
        results = {}
        t = self.run_side(self.a, 'member', tasks_a, results, 'a')
        self.join(t)
        self.assertEqual((results['a'].action, results['a'].reason), (POSTPONE, 'yield_to_paired_task'))
        # 确实先等过，直到进入「到点」范围才让路
        self.assertGreaterEqual(datetime.now(), soon - team.DUE_GRACE - timedelta(seconds=0.05))

    def test_peer_offline_postpones_immediately(self):
        d = rendezvous(self.a, 'Orochi', 'member', self.tasks_a, poll=0.01)
        self.assertEqual((d.action, d.reason), (POSTPONE, 'peer_offline'))

    def _stale_old_process_file(self, clock, age=150):
        """旧进程留下的在场文件：age 秒前最后一次写，还写着在 Orochi 门口等。"""
        self.b.clock = lambda: NOW - timedelta(seconds=age)
        self.b.publish(WAITING, self.tasks_b, task='Orochi', role='leader', token='old',
                       since=NOW - timedelta(seconds=age))
        for board in (self.a, self.b):
            board.clock = lambda: clock[0]

    def test_restart_race_waits_for_the_peer_instead_of_postponing(self):
        """10-23 10:40：oas1 先起来，读到 oas2 旧进程的文件（2.5 分钟前）。以前推迟 10 分钟 + 推送「不在线」。"""
        clock, sleeps, sent = [NOW], [], []
        self._stale_old_process_file(clock)
        mine_b = me(instance='oas2', role='leader', token='tok-new-b', tasks=self.tasks_b)

        def sleep(_):
            sleeps.append(1)
            self.assertLess(len(sleeps), 10, 'never met')
            clock[0] += timedelta(seconds=2)
            if len(sleeps) == 2:                                      # oas2 新进程起来了，进门
                mine_b['since'] = clock[0]
                self.assertEqual(self.b.step(mine_b).action, GO)

        d = rendezvous(self.a, 'Orochi', 'member', self.tasks_a, sleep=sleep, notify=sent.append)
        self.assertEqual((d.action, d.reason), (GO, 'peer_started_with_me'))
        self.assertGreaterEqual(len(sleeps), 2)                       # 确实等过，没有一上来就推迟
        self.assertEqual(sent, [])                                    # 没有「等了很久」的推送

    def test_peer_that_never_comes_back_is_postponed_after_the_grace(self):
        clock, sleeps = [NOW], []
        self._stale_old_process_file(clock)

        def sleep(_):
            sleeps.append(1)
            self.assertLess(len(sleeps), 20, 'never gave up')
            clock[0] += timedelta(minutes=2)

        d = rendezvous(self.a, 'Orochi', 'member', self.tasks_a, sleep=sleep)
        self.assertEqual((d.action, d.reason), (POSTPONE, 'peer_offline'))
        self.assertEqual(len(sleeps), 2)                              # 2.5 → 4.5 → 6.5 分钟，过了 5 分钟才放弃

    def test_both_started_together_after_a_long_stop_meet_without_postponing(self):
        """10-23 11:23:54：停了 43 分钟后两边一起启动，oas1 早 0.7 秒。以前推迟 10 分钟 + 推送，8 秒后才被拉回。"""
        clock, sleeps, sent = [NOW], [], []
        self._stale_old_process_file(clock, age=43 * 60)
        mine_b = me(instance='oas2', role='leader', token='tok-new-b', tasks=self.tasks_b)

        def sleep(_):
            sleeps.append(1)
            self.assertLess(len(sleeps), 10, 'never met')
            clock[0] += timedelta(seconds=2)
            if len(sleeps) == 1:                                      # oas2 也起来了，进门
                mine_b['since'] = clock[0]
                self.assertEqual(self.b.step(mine_b).action, GO)

        d = rendezvous(self.a, 'Orochi', 'member', self.tasks_a, sleep=sleep, notify=sent.append, started_at=NOW)
        self.assertEqual((d.action, d.reason), (GO, 'peer_started_with_me'))
        self.assertEqual(len(sleeps), 1)                              # 确实先等了一轮，没有一上来就推迟
        self.assertEqual(sent, [])

    def test_peer_that_never_starts_is_postponed_once_the_startup_grace_is_over(self):
        clock, sleeps = [NOW], []
        self._stale_old_process_file(clock, age=43 * 60)

        def sleep(_):
            sleeps.append(1)
            self.assertLess(len(sleeps), 20, 'never gave up')
            clock[0] += timedelta(minutes=1)

        d = rendezvous(self.a, 'Orochi', 'member', self.tasks_a, sleep=sleep, started_at=NOW)
        self.assertEqual((d.action, d.reason), (POSTPONE, 'peer_offline'))
        self.assertEqual(len(sleeps), 3)                              # 第 0、1、2 分钟在等，第 3 分钟宽限用完

    def _old_session_file(self, clock, age=20):
        """对方旧进程 age 秒前写的文件：还在和我的旧进程组队（partner_token 是旧的）。"""
        self.b.clock = lambda: NOW - timedelta(seconds=age)
        self.b.publish(RUNNING, self.tasks_b, task='Orochi', role='leader', token='old-b',
                       since=NOW - timedelta(seconds=age), partner_token='old-a')
        for board in (self.a, self.b):
            board.clock = lambda: clock[0]

    def test_peer_in_my_old_session_is_waited_for_not_postponed(self):
        """10-23 11:25:08：两边一起重启，oas1 读到 oas2 旧进程没过期的文件（还在和 oas1 的旧进程组队）。
        以前推迟 10 分钟，7 秒后才被拉回；现在进门等，oas2 新进程进门后会合。"""
        clock, reasons = [NOW], []
        self._old_session_file(clock)
        mine_b = me(instance='oas2', role='leader', token='tok-new-b', tasks=self.tasks_b)
        step = self.a.step

        def traced(mine, abort=False):
            decision = step(mine, abort)
            reasons.append(decision.reason)
            return decision
        self.a.step = traced

        def sleep(_):
            self.assertLess(len(reasons), 10, 'never met')
            clock[0] += timedelta(seconds=2)
            mine_b['since'] = clock[0]
            self.assertEqual(self.b.step(mine_b).action, GO)          # oas2 新进程进门

        d = rendezvous(self.a, 'Orochi', 'member', self.tasks_a, sleep=sleep)
        self.assertEqual((d.action, d.reason), (GO, 'peer_started_with_me'))
        self.assertEqual(reasons, ['peer_running_alone', 'peer_started_with_me'])

    def test_peer_really_still_in_the_old_session_pulls_me_in_when_it_is_done(self):
        # 对方没重启、确实还在旧的那一次里：它结束回到空闲后，看到我在门口等，再进门会合
        clock, reasons = [NOW], []
        self._old_session_file(clock)
        mine_b = me(instance='oas2', role='leader', token='tok-new-b', tasks=self.tasks_b)
        step = self.a.step

        def traced(mine, abort=False):
            decision = step(mine, abort)
            reasons.append(decision.reason)
            return decision
        self.a.step = traced
        sleeps = []

        def sleep(_):
            sleeps.append(1)
            self.assertLess(len(sleeps), 10, 'never met')
            clock[0] += timedelta(seconds=2)
            if len(sleeps) == 1:                                      # 旧的那一次结束，回到空闲
                self.b.publish(IDLE, self.tasks_b, task='Orochi', until=clock[0])
            else:                                                     # 对方 answer() 拉起同一任务后进门
                mine_b['since'] = clock[0]
                self.assertEqual(self.b.step(mine_b).action, GO)

        d = rendezvous(self.a, 'Orochi', 'member', self.tasks_a, sleep=sleep)
        self.assertEqual((d.action, d.reason), (GO, 'peer_started_with_me'))
        self.assertEqual(reasons, ['peer_running_alone', 'pull_peer', 'peer_started_with_me'])

    def test_config_change_aborts_the_wait(self):
        self.b.publish(RUNNING, self.tasks_b, task='RealmRaid')
        calls = []
        d = rendezvous(self.a, 'Orochi', 'member', self.tasks_a, poll=0.01,
                       should_abort=lambda: calls.append(1) or len(calls) >= 3)
        self.assertEqual(d.action, ABORT)
        self.assertEqual(self.b.read_peer()['state'], IDLE)

    def test_long_wait_notifies_once_and_keeps_waiting(self):
        # 假时钟：每轮过 10 分钟，对方一直在跑别的任务（心跳跟着刷新），第 10 轮配置变了结束等待
        clock = [NOW]
        for board in (self.a, self.b):
            board.clock = lambda: clock[0]
        self.b.publish(RUNNING, self.tasks_b, task='RealmRaid')

        def sleep(_):
            clock[0] += timedelta(minutes=10)
            self.b.heartbeat()

        polls, sent = [], []
        d = rendezvous(self.a, 'Orochi', 'member', self.tasks_a, sleep=sleep, notify=sent.append,
                       should_abort=lambda: polls.append(1) or len(polls) >= 10)
        self.assertEqual(d.action, ABORT)
        self.assertEqual(len(sent), 1)                           # 等满 30 分钟推一次，之后不再推
        self.assertIn('30 分钟', sent[0])
        self.assertIn('oas2', sent[0])

    def test_failing_notice_does_not_break_the_wait(self):
        clock = [NOW]
        for board in (self.a, self.b):
            board.clock = lambda: clock[0]
        self.b.publish(RUNNING, self.tasks_b, task='RealmRaid')

        def sleep(_):
            clock[0] += timedelta(minutes=40)
            self.b.heartbeat()

        polls = []
        d = rendezvous(self.a, 'Orochi', 'member', self.tasks_a, sleep=sleep,
                       notify=Mock(side_effect=RuntimeError('push down')),
                       should_abort=lambda: polls.append(1) or len(polls) >= 3)
        self.assertEqual(d.action, ABORT)

    def test_config_change_after_peer_started_with_me_still_goes(self):
        # 对方已经看到我在等并开始了：这时即使我这边配置变了也要开始，否则对方一个人跑
        mine_a = me(instance='oas1', role='member', token='tok-a', tasks=self.tasks_a)
        mine_b = me(instance='oas2', role='leader', token='tok-b', tasks=self.tasks_b)
        self.b.publish(RUNNING, self.tasks_b, task='RealmRaid')
        self.assertEqual(self.a.step(mine_a).action, WAIT)
        self.assertEqual(self.b.step(mine_b).action, GO)
        self.assertEqual(self.a.step(mine_a, abort=True).action, GO)


class SessionTest(unittest.TestCase):
    """会合后的这一次组队：队长上报进度，队员读；对方离开这一次就算结束。"""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='oas_team_sess_'))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(clear_session, 'oas1')
        self.addCleanup(clear_session, 'oas2')
        self.leader = PresenceBoard(self.root, 'oas1', 'oas2')
        self.member = PresenceBoard(self.root, 'oas2', 'oas1')
        self.tasks = {'Orochi': entry('leader')}
        self.leader.publish(RUNNING, self.tasks, task='Orochi', role='leader', token='tok-L', since=NOW,
                            partner_token='tok-M')
        self.session = TeamSession(self.member, 'Orochi', 'member', 'tok-M', 'tok-L')

    def test_member_follows_the_leader_until_it_says_done(self):
        self.assertEqual(self.session.peer_progress(), Progress(None, False))      # 队长还没打完第一场
        TeamSession(self.leader, 'Orochi', 'leader', 'tok-L', 'tok-M').report(3)
        self.assertEqual(self.session.peer_progress(), Progress(3, False))
        self.leader.report_progress(4, True)
        self.assertEqual(self.session.peer_progress(), Progress(4, True))

    def test_leader_leaving_the_meeting_finishes_it_and_keeps_the_last_count(self):
        self.leader.report_progress(7)
        self.assertEqual(self.session.peer_progress(), Progress(7, False))
        self.leader.publish(IDLE, self.tasks, task='Duel')                          # 队长任务结束回到调度器
        self.assertEqual(self.session.peer_progress(), Progress(7, True))

    def test_other_meetings_and_tasks_count_as_left(self):
        cases = {
            'other task': dict(task='RealmRaid', token='tok-L', partner_token='tok-M'),
            'other token': dict(task='Orochi', token='tok-L2', partner_token='tok-M'),
            'not my partner': dict(task='Orochi', token='tok-L', partner_token='someone-else'),
        }
        for name, kw in cases.items():
            with self.subTest(name):
                self.leader.publish(RUNNING, self.tasks, role='leader', since=NOW, **kw)
                self.assertEqual(self.session.peer_progress(), Progress(None, True))

    def test_leader_still_handing_over_is_not_finished(self):
        # 队员先开始、队长下一轮才把 waiting 写成 running
        self.leader.publish(WAITING, self.tasks, task='Orochi', role='leader', token='tok-L', since=NOW)
        self.assertEqual(self.session.peer_progress(), Progress(None, False))

    def test_stale_or_missing_leader_file_is_finished(self):
        self.leader.clock = lambda: datetime.now() - timedelta(minutes=2)
        self.leader.heartbeat()
        self.assertEqual(self.session.peer_progress(), Progress(None, True))
        self.leader.path.unlink()
        self.assertEqual(self.session.peer_progress(), Progress(None, True))

    def test_unreadable_file_is_not_finished_and_errors_never_raise(self):
        self.leader.report_progress(2)
        self.session.peer_progress()
        with patch.object(self.member, 'read_peer', return_value=UNREADABLE):
            self.assertEqual(self.session.peer_progress(), Progress(2, False))
        with patch.object(self.member, 'read_peer', side_effect=RuntimeError('boom')):
            self.assertEqual(self.session.peer_progress(), Progress(2, False))
        with patch.object(self.leader, 'report_progress', side_effect=RuntimeError('boom')):
            TeamSession(self.leader, 'Orochi', 'leader', 'tok-L', 'tok-M').report(1)       # 只记日志

    def test_registry_is_per_instance_and_per_task(self):
        self.assertIsNone(get_session('oas2', 'Orochi'))
        set_session('oas2', self.session)
        self.assertIs(get_session('oas2', 'Orochi'), self.session)
        self.assertIsNone(get_session('oas2', 'BondlingFairyland'))       # 别的任务不能读到这一次
        self.assertIsNone(get_session('oas1', 'Orochi'))
        clear_session('oas2')
        self.assertIsNone(get_session('oas2', 'Orochi'))


def _model(enable=True, peer_name='oas2', **tasks):
    data = {'running_task': '', 'script': {'team_sync': {'enable': enable, 'peer_instance': peer_name}}}
    data.update(tasks)
    return ConfigModel.model_validate(data)


class GlueTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='oas_team_glue_'))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_roles_come_from_user_status(self):
        model = _model(orochi={'orochi_config': {'user_status': 'member'}},
                       bondling_fairyland={'bondling_config': {'user_status': 'leader'}},
                       exploration={'exploration_config': {'user_status': 'alone'}})
        tasks = team_tasks(model)
        self.assertEqual(tasks['Orochi']['role'], 'member')
        self.assertEqual(tasks['BondlingFairyland']['role'], 'leader')
        self.assertNotIn('Exploration', tasks)          # 单人不会合
        self.assertNotIn('Duel', tasks)                 # 没有 user_status 的任务
        self.assertEqual(tasks['XinLan']['role'], 'pair')   # 自己要两边同时到场的任务进快照，但不是门口
        handoff = team_tasks(_model(bondling_fairyland={'bondling_config': {'user_status': 'handoff1'}}))
        self.assertEqual(handoff['BondlingFairyland']['role'], 'handoff1')
        self.assertIsInstance(tasks['Orochi']['next_run'], datetime)
        self.assertIsNone(task_role({'scheduler': {}, 'x': {'user_status': 'wild'}}))

    def test_disabled_writes_nothing_and_lets_everything_run(self):
        sync = TeamSync('oas1', self.root)
        config = SimpleNamespace(model=_model(enable=False))
        sync.on_schedule(config, 'Orochi', NOW)
        self.assertEqual(sync.gate(config, 'Orochi').action, GO)
        self.assertFalse((self.root / 'team').exists())

    def test_invalid_peer_is_ignored(self):
        for name in ('', 'oas1', '  '):
            with self.subTest(peer=name):
                sync = TeamSync('oas1', self.root)
                config = SimpleNamespace(model=_model(peer_name=name))
                self.assertEqual(sync.gate(config, 'Orochi'), (GO, 'disabled', None))
        self.assertFalse((self.root / 'team').exists())

    def test_non_team_task_publishes_running_and_goes(self):
        sync = TeamSync('oas1', self.root)
        config = SimpleNamespace(model=_model())
        sync.on_schedule(config, 'Duel', NOW)
        reader = PresenceBoard(self.root, 'oas2', 'oas1')
        self.assertEqual(reader.read_peer()['state'], IDLE)
        self.assertEqual(sync.gate(config, 'Duel').action, GO)
        self.assertEqual((reader.read_peer()['state'], reader.read_peer()['task']), (RUNNING, 'Duel'))

    def test_team_task_without_peer_postpones(self):
        sync = TeamSync('oas1', self.root, sleep=lambda s: None)
        config = SimpleNamespace(model=_model(orochi={'orochi_config': {'user_status': 'member'}}))
        d = sync.gate(config, 'Orochi')
        self.assertEqual((d.action, d.reason), (POSTPONE, 'peer_offline'))

    def test_paired_task_is_not_a_door(self):
        sync = TeamSync('oas1', self.root)
        self.assertEqual(sync.gate(SimpleNamespace(model=_model()), 'XinLan').action, GO)
        self.assertIsNone(sync.precheck(SimpleNamespace(model=_model()), 'XinLan'))

    def test_precheck_only_postpones_when_the_peer_will_not_come(self):
        orochi = {'orochi_config': {'user_status': 'member'}}
        sync = TeamSync('oas1', self.root)
        config = SimpleNamespace(model=_model(orochi=orochi))
        d = sync.precheck(config, 'Orochi')
        self.assertEqual((d.action, d.reason), (POSTPONE, 'peer_offline'))
        self.assertFalse((self.root / 'team' / 'oas1.json').exists())     # 只读，不写自己的状态
        peer_board = PresenceBoard(self.root, 'oas2', 'oas1')
        peer_board.publish(RUNNING, {'Orochi': entry('leader', datetime.now())}, task='Duel')
        self.assertIsNone(sync.precheck(config, 'Orochi'))                 # 对方在忙：照常准备再进门口
        self.assertIsNone(sync.precheck(config, 'Duel'))                   # 非组队任务
        self.assertIsNone(sync.precheck(SimpleNamespace(model=_model(enable=False, orochi=orochi)), 'Orochi'))

    def test_precheck_does_not_postpone_for_a_just_expired_peer_but_does_for_a_long_gone_one(self):
        orochi = {'orochi_config': {'user_status': 'member'}}
        sync = TeamSync('oas1', self.root)
        config = SimpleNamespace(model=_model(orochi=orochi))
        peer_board = PresenceBoard(self.root, 'oas2', 'oas1')
        peer_board.clock = lambda: datetime.now() - timedelta(seconds=150)           # 重启中：旧进程 2.5 分钟前写的
        peer_board.publish(IDLE, {'Orochi': entry('leader', datetime.now())}, task='Orochi')
        self.assertIsNone(sync.precheck(config, 'Orochi'))                           # 不推迟、不推送，照常准备进门
        peer_board.clock = lambda: datetime.now() - timedelta(minutes=6)
        peer_board.publish(IDLE, {'Orochi': entry('leader', datetime.now())}, task='Orochi')
        d = sync.precheck(config, 'Orochi')
        self.assertEqual((d.action, d.reason), (POSTPONE, 'peer_offline'))

    def test_new_process_waits_for_a_long_gone_peer_in_precheck_and_gate(self):
        orochi = {'orochi_config': {'user_status': 'member'}}
        config = SimpleNamespace(model=_model(orochi=orochi))
        peer_board = PresenceBoard(self.root, 'oas2', 'oas1')
        peer_board.clock = lambda: datetime.now() - timedelta(minutes=43)           # 上次两边都关掉时留下的文件
        peer_board.publish(IDLE, {'Orochi': entry('leader', datetime.now())}, task='Orochi')

        fresh = TeamSync('oas1', self.root, started_at=datetime.now(), sleep=Mock(side_effect=_StopLoop))
        self.assertIsNone(fresh.precheck(config, 'Orochi'))                          # 不推迟、不推送，照常准备
        with self.assertRaises(_StopLoop):                                           # 进门等，第一次睡眠处被截断
            fresh.gate(config, 'Orochi')
        mine = PresenceBoard(self.root, 'oas2', 'oas1').read_peer()                  # 对方视角读到的 oas1
        self.assertEqual((mine['state'], mine['task']), (WAITING, 'Orochi'))

        old = TeamSync('oas1', self.root, started_at=datetime.now() - timedelta(minutes=4))
        d = old.precheck(config, 'Orochi')
        self.assertEqual((d.action, d.reason), (POSTPONE, 'peer_offline'))           # 宽限用完，照旧推迟
        d = TeamSync('oas1', self.root, started_at=datetime.now() - timedelta(minutes=4),
                     sleep=Mock(side_effect=_StopLoop)).gate(config, 'Orochi')
        self.assertEqual((d.action, d.reason), (POSTPONE, 'peer_offline'))

    def test_notice_once_per_day_per_reason(self):
        day = [NOW]
        sync = TeamSync('oas1', self.root, clock=lambda: day[0])
        sync._board(SimpleNamespace(model=_model()))
        offline = team.Decision(POSTPONE, 'peer_offline', NOW)
        self.assertIn('oas2', sync.notice('Orochi', offline))
        self.assertIsNone(sync.notice('BondlingFairyland', offline))
        self.assertIn('身份不互补', sync.notice('Orochi', team.Decision(POSTPONE, 'role_conflict', NOW)))
        self.assertIsNone(sync.notice('Orochi', team.Decision(POSTPONE, 'peer_resting', NOW)))   # 正常对齐不提醒
        day[0] = NOW + timedelta(days=1)
        self.assertIsNotNone(sync.notice('Orochi', offline))

    def test_errors_never_block_the_scheduler(self):
        sync = TeamSync('oas1', self.root)
        broken = SimpleNamespace(model=SimpleNamespace(script=None))
        sync.on_schedule(broken, 'Orochi', NOW)            # 只记日志
        self.assertIsNone(sync.precheck(broken, 'Orochi'))
        self.assertEqual(sync.gate(broken, 'Orochi'), (GO, 'team_sync_error', None))

    def test_config_registration_and_i18n(self):
        self.assertFalse(ConfigModel.model_validate({'running_task': ''}).script.team_sync.enable)
        i18n = json.loads((_REPO / 'assets' / 'i18n' / 'zh-CN.json').read_text(encoding='utf-8'))
        from tasks.Script.config_team_sync import TeamSync as TeamSyncConfig
        self.assertIn('team_sync', i18n)
        for name, field in TeamSyncConfig.model_fields.items():
            if name != 'enable':
                self.assertIn(name, i18n)
            self.assertIn(field.description, i18n)


def _orochi(status, next_run, enable=True):
    return {'orochi_config': {'user_status': status}, 'scheduler': {'enable': enable, 'next_run': next_run}}


class PullTest(unittest.TestCase):
    """对方在门口等我时，把我这边的同一任务拉到现在（`peer_request` / `answer`）。"""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='oas_team_pull_'))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.later = (datetime.now() + timedelta(hours=4)).replace(microsecond=0)
        self.peer_board = PresenceBoard(self.root, 'oas2', 'oas1')
        self.addCleanup(clear_session, 'oas1')
        self.addCleanup(clear_session, 'oas2')

    def config(self, status='member', next_run=None, enable=True, sync=True):
        model = _model(enable=sync, orochi=_orochi(status, next_run or self.later, enable))

        def task_call(task, force_call=True):
            # 和真实 Config.task_call 一样把运行时间改成现在
            model.orochi.scheduler.next_run = datetime.now().replace(microsecond=0)
        return SimpleNamespace(model=model, task_call=Mock(side_effect=task_call), notifier=Mock())

    def peer_waits(self, token='tok-1', role='leader', task='Orochi', state=WAITING):
        self.peer_board.publish(state, {'Orochi': entry(role)}, task=task, role=role, token=token,
                                since=datetime.now())

    def test_peer_waiting_for_a_task_that_is_not_due_here_is_answered_once(self):
        sync = TeamSync('oas1', self.root)
        config = self.config()
        self.peer_waits()
        self.assertEqual(sync.peer_request(config), 'Orochi')
        self.assertEqual(sync.peer_request(config), 'Orochi')          # 只读，不算回应
        self.assertEqual(sync.answer(config), 'Orochi')
        config.task_call.assert_called_once_with('Orochi', force_call=False)
        self.assertIsNone(sync.peer_request(config))                   # 回应过了：不再打断空闲等待

    def test_same_token_is_answered_only_once_even_if_the_task_is_still_not_due(self):
        sync = TeamSync('oas1', self.root)
        config = self.config()
        config.task_call = Mock()                                        # 运行时间没改成功
        self.peer_waits('tok-1')
        sync.answer(config)
        self.assertIsNone(sync.answer(config))
        self.assertIsNone(sync.peer_request(config))
        self.assertEqual(config.task_call.call_count, 1)
        self.peer_waits('tok-2')                                         # 对方重新进门：再回应一次
        self.assertEqual(sync.answer(config), 'Orochi')
        self.assertEqual(config.task_call.call_count, 2)

    def test_requests_that_are_not_for_me_are_ignored(self):
        cases = {
            'task off here': dict(config=dict(enable=False)),
            'same role': dict(config=dict(status='leader')),
            'already due here': dict(config=dict(next_run=datetime.now() - timedelta(minutes=1))),
            'peer running, not waiting': dict(peer=dict(state=RUNNING)),
            'peer idle': dict(peer=dict(state=IDLE)),
            'single player here': dict(config=dict(status='alone')),
            'sync off': dict(config=dict(sync=False)),
        }
        for name, case in cases.items():
            with self.subTest(name):
                sync = TeamSync('oas1', self.root)
                config = self.config(**case.get('config', {}))
                self.peer_waits(**case.get('peer', {}))
                self.assertIsNone(sync.peer_request(config))
                self.assertIsNone(sync.answer(config))
                config.task_call.assert_not_called()

    def test_offline_or_unpaired_peer_is_ignored(self):
        sync = TeamSync('oas1', self.root)
        config = self.config()
        self.assertIsNone(sync.peer_request(config))                   # 没有对方文件
        self.peer_board.clock = lambda: datetime.now() - timedelta(minutes=5)
        self.peer_waits()
        self.assertIsNone(sync.peer_request(config))                   # 对方不在线
        PresenceBoard(self.root, 'oas2', 'oas3').publish(WAITING, {}, task='Orochi', role='leader', token='t')
        self.assertIsNone(sync.peer_request(config))                   # 对方配的不是我

    def test_errors_return_none(self):
        sync = TeamSync('oas1', self.root)
        broken = SimpleNamespace(model=SimpleNamespace(script=None))
        self.assertIsNone(sync.peer_request(broken))
        self.assertIsNone(sync.answer(broken))

    def test_on_schedule_publishes_rest_until(self):
        sync = TeamSync('oas1', self.root)
        wake = self.later
        sync.on_schedule(self.config(), 'Orochi', wake, rest_until=wake)
        self.assertEqual(PresenceBoard(self.root, 'oas2', 'oas1').read_peer()['rest_until'], wake)

    def test_precheck_waits_for_an_idle_peer_but_not_for_a_resting_one(self):
        sync = TeamSync('oas1', self.root)
        config = self.config(next_run=datetime.now() - timedelta(minutes=1))
        later = self.later
        self.peer_board.publish(IDLE, {'Orochi': entry('leader', later)}, task='Orochi', until=later)
        self.assertIsNone(sync.precheck(config, 'Orochi'))             # 以前这里判 peer_not_due 推迟
        self.peer_board.publish(IDLE, {'Orochi': entry('leader', later)}, task='Orochi', until=later,
                                rest_until=later)
        d = sync.precheck(config, 'Orochi')
        self.assertEqual((d.action, d.reason, d.until), (POSTPONE, 'peer_resting', later))

    def test_reproduce_both_idle_and_peer_scheduled_later(self):
        """10-23 日志：A 的 Orochi 到点，B 的 Orochi 排在几小时后、B 空闲。

        以前 A 判 peer_not_due 推迟到 B 的时间；现在 A 在门口等，B 被拉过来，两边一起开始。
        """
        sync_a = TeamSync('oas1', self.root, sleep=lambda s: time.sleep(0.01))
        sync_b = TeamSync('oas2', self.root, sleep=lambda s: time.sleep(0.01))
        config_a = self.config('member', next_run=datetime.now() - timedelta(minutes=1))
        config_a.model.script.team_sync.peer_instance = 'oas2'
        config_b = self.config('leader')
        config_b.model.script.team_sync.peer_instance = 'oas1'
        sync_b.on_schedule(config_b, 'Orochi', self.later)              # B 空闲，Orochi 排在以后
        self.assertIsNone(sync_a.precheck(config_a, 'Orochi'))

        results = {}
        thread = threading.Thread(target=lambda: results.setdefault('a', sync_a.gate(config_a, 'Orochi')),
                                  daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while sync_b.peer_request(config_b) is None:                     # B 的空闲等待每轮看一眼
            self.assertLess(time.monotonic(), deadline, 'A never showed up at the door')
            time.sleep(0.01)
        self.assertEqual(sync_b.answer(config_b), 'Orochi')
        self.assertLessEqual(config_b.model.orochi.scheduler.next_run, datetime.now())
        self.assertIsNone(sync_b.precheck(config_b, 'Orochi'))
        self.assertEqual(sync_b.gate(config_b, 'Orochi').action, GO)
        thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual((results['a'].action, results['a'].reason), (GO, 'peer_started_with_me'))
        config_a.task_call.assert_not_called()

        # 会合成功后两边各拿到这一次组队的会话，token 互相对得上；任务结束清掉
        session_a, session_b = get_session('oas1', 'Orochi'), get_session('oas2', 'Orochi')
        self.assertIsNotNone(session_a)
        self.assertIsNotNone(session_b)
        self.assertEqual((session_a.token, session_a.peer_token), (session_b.peer_token, session_b.token))
        self.assertEqual((session_a.role, session_b.role), ('member', 'leader'))
        session_b.report(3)                                              # 队长上报，队员读到
        self.assertEqual(session_a.peer_progress(), Progress(3, False))
        sync_a.end_task()
        self.assertIsNone(get_session('oas1', 'Orochi'))
        self.assertIsNotNone(get_session('oas2', 'Orochi'))              # 只清自己这个实例的

    def test_no_session_without_a_meeting(self):
        set_session('oas1', TeamSession(self.peer_board, 'Orochi', 'member', 'a', 'b'))
        sync = TeamSync('oas1', self.root)
        sync.gate(self.config(sync=False), 'Orochi')                     # 没开同步：放行，也不留上一次的会话
        self.assertIsNone(get_session('oas1', 'Orochi'))
        set_session('oas1', TeamSession(self.peer_board, 'Orochi', 'member', 'a', 'b'))
        sync.gate(self.config(), 'Duel')                                 # 非组队任务
        self.assertIsNone(get_session('oas1', 'Orochi'))
        set_session('oas1', TeamSession(self.peer_board, 'Orochi', 'member', 'a', 'b'))
        broken = SimpleNamespace(model=SimpleNamespace(script=None))
        self.assertEqual(sync.gate(broken, 'Orochi').reason, 'team_sync_error')
        self.assertIsNone(get_session('oas1', 'Orochi'))
        sync = TeamSync('oas1', self.root, sleep=lambda s: None)
        d = sync.gate(self.config(), 'Orochi')                           # 对方不在线：推迟，没有会合
        self.assertEqual(d.action, POSTPONE)
        self.assertIsNone(get_session('oas1', 'Orochi'))


class WaitUntilTest(unittest.TestCase):
    """`Script.wait_until`：对方在门口等我时打断空闲等待。"""

    def test_peer_request_interrupts_idle_wait(self):
        import script as script_mod
        script = script_mod.Script.__new__(script_mod.Script)
        script.config = SimpleNamespace(start_watching=Mock(), should_reload=Mock(return_value=False))
        requests = iter([None, None, 'Orochi'])
        script.__dict__['team_sync'] = SimpleNamespace(peer_request=Mock(side_effect=lambda c: next(requests)))
        sleeps = []

        def sleep(_):
            # 硬上限：不看对方请求时会一直等到 1 小时后，这里直接失败而不是挂住
            sleeps.append(1)
            self.assertLess(len(sleeps), 50, 'idle wait was not interrupted by the peer request')

        with patch.object(script_mod.time, 'sleep', side_effect=sleep):
            self.assertFalse(script.wait_until(datetime.now() + timedelta(hours=1)))
        self.assertEqual(script.team_sync.peer_request.call_count, 3)

    def test_wait_still_finishes_without_requests(self):
        import script as script_mod
        script = script_mod.Script.__new__(script_mod.Script)
        script.config = SimpleNamespace(start_watching=Mock(), should_reload=Mock(return_value=False))
        script.__dict__['team_sync'] = SimpleNamespace(peer_request=Mock(return_value=None))
        real_sleep = time.sleep
        with patch.object(script_mod.time, 'sleep', side_effect=lambda s: real_sleep(0.01)):
            self.assertTrue(script.wait_until(datetime.now() - timedelta(seconds=0.9)))


class _StopLoop(BaseException):
    """穿过 `Script.loop` 的 `except Exception`，用来结束调度循环。"""


class ScriptLoopTest(unittest.TestCase):
    """真实 Script.loop + 真实 Config（临时目录里的临时配置）。"""

    def setUp(self):
        import script as script_mod
        from module.config.config import Config
        from module.script import ScriptRuntimeDecision
        self.script_mod = script_mod
        self._cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp(prefix='oas_team_loop_')
        os.chdir(self.tmp)
        os.makedirs('config')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(os.chdir, self._cwd)
        patch.object(script_mod.logger, 'set_file_logger').start()
        patch.object(script_mod, 'IS_WINDOWS', False).start()
        self.notifier = Mock(name='notifier')
        patch.object(Config, 'notifier', self.notifier).start()
        self.addCleanup(patch.stopall)
        self.ran = []
        self.session_seen = None
        self.addCleanup(clear_session, 'simA')
        patch.object(script_mod, 'load_module', side_effect=self._module).start()
        self.decision_ready = ScriptRuntimeDecision.READY

    def _module(self, name, path):
        command = Path(path).parent.name

        def run():
            self.ran.append(command)
            self.session_seen = get_session('simA', command)       # 任务运行时能取到会合后的这一次组队
            raise _StopLoop
        return SimpleNamespace(ScriptTask=lambda config, device: SimpleNamespace(run=run))

    def _write_config(self, *, sync, orochi_status='leader', enable=('orochi',), orochi_next_run=None):
        data = ConfigModel().model_dump()
        data.pop('config_name', None)
        for value in data.values():
            if isinstance(value, dict) and isinstance(value.get('scheduler'), dict):
                value['scheduler']['enable'] = False
        for key in enable:
            data[key]['scheduler'].update(enable=True, next_run=datetime.now() - timedelta(minutes=1))
        data['orochi']['orochi_config']['user_status'] = orochi_status
        if orochi_next_run is not None:
            data['orochi']['scheduler']['next_run'] = orochi_next_run
        # 服务器刷新时间不是 9 点时，task_delay(server=True) 会把 next_run 改成明天这个点，用来确认推迟时没走那条分支
        data['orochi']['scheduler']['server_update'] = dt_time(5, 0)
        data['script']['team_sync'] = {'enable': sync, 'peer_instance': 'peerX'}
        ConfigModel.write_json('simA', data)

    def _script(self, *, long_running=True):
        script = self.script_mod.Script.__new__(self.script_mod.Script)
        if long_running:
            # 脚本已经运行很久：没有启动宽限，对方不在线就直接推迟（否则门口会真等 3 分钟）
            script.team_sync = TeamSync('simA', started_at=datetime.now() - timedelta(minutes=10))
        script.server = script.state_queue = script.command_queue = script.gui_update_task = None
        script._emulator_down = False
        script.is_first_task = False
        script.config_name = 'simA'
        script.failure_record = {}
        script.last_task_runtime_outcome = None
        script.loop_thread = None
        script.device = Mock(name='device')
        script.runtime = Mock(name='runtime')
        script.runtime.prepare_task_execution.return_value = self.decision_ready
        script.runtime.handle_wait_during_idle.side_effect = _StopLoop
        return script

    def _saved_next_run(self, task='orochi'):
        raw = json.loads(Path('config', 'simA.json').read_text(encoding='utf-8'))
        return datetime.fromisoformat(raw[task]['scheduler']['next_run'])

    def test_sync_off_runs_team_task_as_before(self):
        self._write_config(sync=False)
        with self.assertRaises(_StopLoop):
            self._script().loop()
        self.assertEqual(self.ran, ['Orochi'])
        self.assertFalse(Path('log', 'instance_sync', 'team').exists())

    def test_team_task_without_peer_is_postponed_not_run(self):
        self._write_config(sync=True)
        before = datetime.now()
        script = self._script()
        with self.assertRaises(_StopLoop):
            script.loop()
        self.assertEqual(self.ran, [])
        # 确定对方不会来：在唤醒模拟器 / 游戏之前就推迟，并推送一次提醒
        script.runtime.prepare_task_execution.assert_not_called()
        self.notifier.push.assert_called_once()
        self.assertIn('peerX', self.notifier.push.call_args.kwargs['content'])
        delay = self._saved_next_run() - before
        # 推迟 10 分钟，没有被任务自己的服务器刷新时间（server=True 的分支）覆盖
        self.assertTrue(timedelta(minutes=9) < delay < timedelta(minutes=11), delay)
        presence = json.loads(Path('log', 'instance_sync', 'team', 'simA.json').read_text(encoding='utf-8'))
        self.assertEqual(presence['state'], IDLE)

    def test_freshly_started_script_waits_at_the_door_instead_of_postponing(self):
        """10-23 11:23：两边一起启动，对方文件还是上次留下的。不能先推迟、推送，几秒后又被拉回。"""
        self._write_config(sync=True)
        script = self._script(long_running=False)

        def stop_in_main_thread(seconds):          # 心跳线程里的睡眠照常，门口等待的睡眠在主线程，在这里截断
            if threading.current_thread() is threading.main_thread():
                raise _StopLoop
            time.sleep(seconds)
        script.team_sync.sleep = stop_in_main_thread
        with self.assertRaises(_StopLoop):
            script.loop()
        self.assertEqual(self.ran, [])
        script.runtime.prepare_task_execution.assert_called_once_with('Orochi')    # 照常准备，再进门等
        self.notifier.push.assert_not_called()
        self.assertLessEqual(self._saved_next_run(), datetime.now())               # 没被推迟
        presence = json.loads(Path('log', 'instance_sync', 'team', 'simA.json').read_text(encoding='utf-8'))
        self.assertEqual((presence['state'], presence['task']), (WAITING, 'Orochi'))

    def test_script_team_sync_carries_the_process_start_time(self):
        before = datetime.now()
        sync = self._script(long_running=False).team_sync
        self.assertIsNotNone(sync.started_at)
        self.assertTrue(before <= sync.started_at <= datetime.now())

    def test_peer_waiting_at_the_door_prepares_then_runs_together(self):
        self._write_config(sync=True)
        PresenceBoard(Path('log', 'instance_sync'), 'peerX', 'simA').publish(
            WAITING, {'Orochi': entry('member', datetime.now())}, task='Orochi', role='member', token='tok-peer',
            since=datetime.now())
        script = self._script()
        with self.assertRaises(_StopLoop):
            script.loop()
        self.assertEqual(self.ran, ['Orochi'])
        script.runtime.prepare_task_execution.assert_called_once_with('Orochi')
        presence = json.loads(Path('log', 'instance_sync', 'team', 'simA.json').read_text(encoding='utf-8'))
        self.assertEqual((presence['state'], presence['partner_token']), (RUNNING, 'tok-peer'))
        self.notifier.push.assert_not_called()
        # 任务运行时有会话（对方的 token 就是 tok-peer），任务结束（这里是异常穿出）后清掉，不留给下一个任务
        self.assertIsNotNone(self.session_seen)
        self.assertEqual(self.session_seen.peer_token, 'tok-peer')
        self.assertIsNone(get_session('simA', 'Orochi'))

    def test_idle_side_is_pulled_into_the_task_the_peer_waits_for(self):
        # 本实例的 Orochi 排在 4 小时后；对方已经在 Orochi 门口等：调度器把它拉到现在并一起开始，不进空闲等待
        self._write_config(sync=True, orochi_next_run=datetime.now() + timedelta(hours=4))
        PresenceBoard(Path('log', 'instance_sync'), 'peerX', 'simA').publish(
            WAITING, {'Orochi': entry('member', datetime.now())}, task='Orochi', role='member', token='tok-peer',
            since=datetime.now())
        script = self._script()
        with self.assertRaises(_StopLoop):
            script.loop()
        self.assertEqual(self.ran, ['Orochi'])
        script.runtime.handle_wait_during_idle.assert_not_called()
        self.assertLessEqual(self._saved_next_run(), datetime.now())
        presence = json.loads(Path('log', 'instance_sync', 'team', 'simA.json').read_text(encoding='utf-8'))
        self.assertEqual((presence['state'], presence['partner_token']), (RUNNING, 'tok-peer'))

    def test_non_team_task_runs_with_sync_on(self):
        self._write_config(sync=True, orochi_status='alone')
        with self.assertRaises(_StopLoop):
            self._script().loop()
        self.assertEqual(self.ran, ['Orochi'])
        presence = json.loads(Path('log', 'instance_sync', 'team', 'simA.json').read_text(encoding='utf-8'))
        self.assertEqual((presence['state'], presence['task']), (RUNNING, 'Orochi'))


if __name__ == '__main__':
    unittest.main()
