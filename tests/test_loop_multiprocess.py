# This Python file uses the following encoding: utf-8
"""御魂 → 个人突破 循环的双进程集成测试：两个真实 spawn 进程共用同一个在场文件目录（临时目录）。

只测单进程测不了的东西：跨进程文件读写、对方进程被终止后的失联判定、界面停止的命令 + 只读确认。
不碰设备 / 游戏 / OCR / 模拟器：每个步骤都是睡眠 + 调控制器接口的假实现。
为了让 60 秒的失联判定在测试里只需 1 秒左右，进程内的时钟按 SCALE 倍速走（两个进程都用同一个墙钟基准）。
所有等待都有硬超时，卡住就 terminate。离线通过不等于真机通过。
"""

import asyncio
import json
import multiprocessing
import queue
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

from module.script import loop_controller as lc

SCALE = 60.0
HARD_TIMEOUT = 40
CTX = multiprocessing.get_context('spawn')


def _worker(name, peer, role, root, base_ts, delay, rounds, scenario, result_q, cmd_q):
    """一个实例：请求循环 → 按控制器指示跑假步骤 → 把结果放进队列。"""
    from datetime import datetime, timedelta
    from random import Random

    from module.instance_sync.team import PresenceBoard
    from module.script.loop_controller import LoopController, LoopParams

    def clock():
        return datetime.fromtimestamp(base_ts + (time.time() - base_ts) * SCALE)

    time.sleep(delay)
    board = PresenceBoard(root, name, peer, clock=clock)
    ctrl = LoopController(name, rng=Random(hash(name) & 0xFFFF))
    ctrl.bind_board(board)
    stop = threading.Event()

    def heartbeat():
        board.heartbeat()
        while not stop.wait(0.15):
            board.heartbeat()

    def commands():
        while not stop.is_set():
            try:
                command = cmd_q.get(timeout=0.1)
            except queue.Empty:
                continue
            ctrl.cancel_by_command(command)

    threading.Thread(target=commands, daemon=True).start()
    ctrl.request_start(LoopParams(role, rounds, 2, 4), board)
    threading.Thread(target=heartbeat, daemon=True).start()
    slow = scenario in ('cancel',)
    ran = []
    begins = []
    yielded = False
    away_end = None
    deadline = time.time() + HARD_TIMEOUT
    while time.time() < deadline:
        step = ctrl.current_step()
        if not ctrl.live:
            break
        if step is None:
            ctrl.tick()
            time.sleep(0.05)
            continue
        verdict = ctrl.barrier()
        if scenario == 'yield' and role == 'leader' and not yielded and ctrl.loop['ready']:
            # 已经发布了就绪，又让出去做别的事：必须撤回就绪，对方不能凭旧的 ready 开始
            yielded = True
            ctrl.abandon_run()
            time.sleep(1.5)
            away_end = time.time()
            continue
        if verdict == 'wait':
            time.sleep(0.05)
            continue
        if verdict == 'skip':
            ctrl.accept_skip()
            continue
        if verdict != 'go':
            break
        if not ctrl.begin_run():
            break
        ran.append((ctrl.idx, step))
        begins.append(time.time())
        if step == 'Orochi':
            if role == 'leader':
                while ctrl.remaining() > 0 and ctrl.check(force=True):
                    ctrl.attempt_begin()
                    time.sleep(0.4 if slow else 0.02)
                    ctrl.battle_settled(True)
                ctrl.report_batch(True)
            else:
                while ctrl.member_batch_state() == 'running':
                    time.sleep(0.05)
            ctrl.after_run('Orochi', ended=True, delay_success=True)
        else:
            time.sleep(0.02 if role == 'leader' else 0.25)       # 队长的个人突破先完成，要等队员
            ctrl.after_run('RealmRaid', ended=True, delay_success=None)
    snap = ctrl.snapshot()
    result_q.put({'name': name, 'state': ctrl.state, 'reason': snap and snap['reason'],
                  'done_idx': snap and snap['done_idx'], 'id': snap and snap['id'], 'ran': ran,
                  'targets': ctrl.targets, 'counts': ctrl.counts, 'begins': begins, 'away_end': away_end})
    time.sleep(0.3 if scenario != 'late_read' else 0)
    stop.set()


class LoopMultiprocessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='oas_loop_mp_')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.results = CTX.Queue()
        self.cmd = {'A': CTX.Queue(), 'B': CTX.Queue()}
        self.procs = {}
        self.base = time.time()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for proc in self.procs.values():
            if proc.is_alive():
                proc.terminate()
            proc.join(timeout=5)

    def spawn(self, name, peer, role, delay=0.0, rounds=2, scenario='normal'):
        proc = CTX.Process(target=_worker, name=name, daemon=True,
                           args=(name, peer, role, self.tmp, self.base, delay, rounds, scenario,
                                 self.results, self.cmd[name]))
        proc.start()
        self.procs[name] = proc
        return proc

    def collect(self, names, timeout=HARD_TIMEOUT):
        got = {}
        deadline = time.time() + timeout
        # 只等指定的几个；队列里可能还有别的 worker 先放进来的结果，收下但不算数
        while not all(name in got for name in names) and time.time() < deadline:
            try:
                item = self.results.get(timeout=0.5)
            except queue.Empty:
                continue
            got[item['name']] = item
        self.assertTrue(all(name in got for name in names), f'workers did not finish: {got}')
        return got

    def presence(self, name):
        return json.loads(Path(self.tmp, 'team', f'{name}.json').read_text(encoding='utf-8'))

    def test_leader_opens_first_member_much_later_then_two_rounds_complete(self):
        self.spawn('A', 'B', 'leader', delay=0.0)
        self.spawn('B', 'A', 'member', delay=1.5)               # 队员很久之后才手动加入
        got = self.collect(['A', 'B'])
        for name in ('A', 'B'):
            self.assertEqual(got[name]['state'], 'COMPLETED', got[name])
            self.assertEqual(got[name]['done_idx'], 3)
            self.assertEqual([step for _, step in got[name]['ran']],
                             ['Orochi', 'RealmRaid', 'Orochi', 'RealmRaid'])
        self.assertEqual(got['A']['id'], got['B']['id'])
        self.assertEqual(got['A']['targets'], got['B']['targets'])       # 队员使用队长随机出的同一个目标
        self.assertTrue(all(2 <= n <= 4 for n in got['A']['targets'].values()))
        for idx, target in got['A']['targets'].items():
            self.assertEqual(got['A']['counts'][idx], target)
        # 两个进程都退出之后，终态仍保留在各自的在场文件里
        for proc in self.procs.values():
            proc.join(timeout=10)
        self.assertEqual(self.presence('A')['loop']['state'], 'COMPLETED')
        self.assertEqual(self.presence('B')['loop']['state'], 'COMPLETED')

    def test_yielding_after_publishing_ready_withdraws_it_so_the_peer_cannot_start(self):
        self.spawn('A', 'B', 'leader', delay=0.0, rounds=1, scenario='yield')
        self.spawn('B', 'A', 'member', delay=0.3, rounds=1, scenario='yield')
        got = self.collect(['A', 'B'])
        self.assertEqual({got['A']['state'], got['B']['state']}, {'COMPLETED'})
        self.assertIsNotNone(got['A']['away_end'])
        # 队员的第一步在队长回来重新就绪之后才开始（留 0.2 秒的时钟 / 轮询余量）
        self.assertGreaterEqual(got['B']['begins'][0], got['A']['away_end'] - 0.2)

    def test_member_first_leader_later(self):
        self.spawn('B', 'A', 'member', delay=0.0, rounds=1)
        self.spawn('A', 'B', 'leader', delay=1.5, rounds=1)
        got = self.collect(['A', 'B'])
        self.assertEqual({got['A']['state'], got['B']['state']}, {'COMPLETED'})
        self.assertEqual(got['A']['done_idx'], 1)

    def test_config_mismatch_is_rejected_before_any_step(self):
        self.spawn('A', 'B', 'leader', rounds=2)
        self.spawn('B', 'A', 'member', delay=0.3, rounds=3)
        got = self.collect(['A', 'B'])
        self.assertEqual({got['A']['state'], got['B']['state']}, {'FAILED'})
        self.assertEqual(got['A']['ran'], [])
        self.assertEqual(got['B']['ran'], [])

    def test_killing_one_process_makes_the_other_stop_by_loss_detection(self):
        self.spawn('A', 'B', 'leader', rounds=3)
        victim = self.spawn('B', 'A', 'member', delay=0.3, rounds=3)
        deadline = time.time() + HARD_TIMEOUT
        while time.time() < deadline:                            # 等循环进入 ACTIVE 之后再杀
            try:
                if self.presence('B')['loop']['state'] == 'ACTIVE':
                    break
            except (OSError, KeyError, ValueError):
                pass
            time.sleep(0.05)
        victim.terminate()
        victim.join(timeout=5)
        got = self.collect(['A'])
        self.assertEqual(got['A']['state'], 'FAILED')
        self.assertIn(got['A']['reason'], ('peer_lost', 'peer_left'))

    def test_ui_stop_notice_is_acked_and_the_peer_stops_without_waiting_for_loss(self):
        proc_a = self.spawn('A', 'B', 'leader', rounds=3, scenario='cancel')
        self.spawn('B', 'A', 'member', delay=0.3, rounds=3, scenario='cancel')
        deadline = time.time() + HARD_TIMEOUT
        while time.time() < deadline:
            try:
                if self.presence('A')['loop']['state'] == 'ACTIVE' and self.presence('A')['loop']['ready']:
                    break
            except (OSError, KeyError, ValueError):
                pass
            time.sleep(0.05)
        started = time.time()
        result = asyncio.run(lc.notify_cancel(self.tmp, 'A', proc_a.pid, self.cmd['A'], sleep=asyncio.sleep,
                                              timeout=5.0, poll=0.05))
        self.assertEqual(result, 'acked')
        self.assertLess(time.time() - started, 5.0)
        proc_a.terminate()                                       # 父进程确认后照常终止（A 的结果可能来不及放进队列，不收）
        got = self.collect(['B'])
        self.assertEqual(got['B']['state'], 'CANCELLED')
        self.assertEqual(got['B']['reason'], 'peer_cancelled')
        self.assertEqual(self.presence('A')['loop']['state'], 'CANCELLED')

    def test_stop_notice_of_an_old_process_does_not_hit_a_new_loop(self):
        """残留的取消命令带着旧进程的 boot_id，新进程里的新循环不受影响。"""
        stale = {'command': 'loop_cancel', 'boot_id': 'dead-process', 'loop_id': 'dead-loop', 'pid': 1,
                 'reason': 'ui_stop'}
        self.cmd['A'].put(stale)
        self.spawn('A', 'B', 'leader', rounds=1)
        self.spawn('B', 'A', 'member', delay=0.3, rounds=1)
        got = self.collect(['A', 'B'])
        self.assertEqual({got['A']['state'], got['B']['state']}, {'COMPLETED'})


if __name__ == '__main__':
    unittest.main()
