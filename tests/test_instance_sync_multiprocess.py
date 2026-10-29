"""`module/instance_sync` 的双进程集成测试：两个真实 spawn 进程共用同一个账本目录（临时目录）。

这是 master 测试里少有的多进程用例，所以：只测单进程测不了的东西（FileLock 跨进程互斥、真实时钟下的并发提交），
每个场景一对进程、跑多个「业务日」（每个业务日一个独立账本），所有等待都有硬超时，卡住就 terminate。
不碰设备 / 游戏 / OCR：适配器是纯内存的假实现。

锁住：
- normal：两个进程同时提交最后一次 verify（Barrier 对齐），每个账本恰好一次 completed，两边都拿到 COMPLETED。
- verify_race：一方核验通过、另一方同一时刻核验失败 → 整轮 failed，两边都 FAILED，账本里绝不出现 completed。
- unknown：一方结果未知 → 另一方在一个轮询周期（20ms）量级内退出，不是等到预算超时。
"""

import json
import multiprocessing
import queue
import tempfile
import time
import unittest
from pathlib import Path

from module.instance_sync import state_machine as sm
from module.instance_sync.adapter import Evidence, PrepareResult, SyncAdapter
from module.instance_sync.coordinator import S_COMPLETED, S_FAILED, SyncCoordinator
from module.instance_sync.invariants import validate_document

MEMBERS = [('oas1', 'A01'), ('oas2', 'A02')]
PARAMS = {'retry_wait': 0.2, 'budget': 20, 'min_attempt_cost': 0.05, 'max_rounds': 4}
BARRIER_TIMEOUT = 20
POLL = 0.02


class _MpAdapter(SyncAdapter):
    business_id = 'xinlan'

    def __init__(self, day, role, scenario, verify_barrier):
        self.day = day
        self.role = role
        self.scenario = scenario
        self.verify_barrier = verify_barrier
        self.failed_at = None

    def protocol_params(self):
        return PARAMS

    def business_day(self, now):
        return self.day

    def prepare(self, ctx):
        return PrepareResult(True)

    def dispatch(self, ctx, attempt):
        pass

    def judge(self, ctx, attempt):
        if self.scenario == 'unknown' and self.role == 'oas2':
            self.failed_at = time.time()
            return Evidence.unknown('no toast')
        return Evidence.done()

    def verify(self, ctx):
        if self.scenario in ('normal', 'verify_race'):
            self.verify_barrier.wait(BARRIER_TIMEOUT)  # 两边同时去提交最后一次核验
        if self.scenario == 'verify_race' and self.role == 'oas2':
            return False
        return True

    def inspect_attempt(self, ctx, attempt):
        return Evidence.unknown()


def _worker(role, root, days, scenario, start_barrier, verify_barrier, out):
    """子进程入口（spawn 要求在模块顶层）。"""
    try:
        for day in days:
            adapter = _MpAdapter(day, role, scenario, verify_barrier)
            coordinator = SyncCoordinator(adapter, instance=role, members=MEMBERS, rendezvous_timeout=30, root=root,
                                          poll_interval=POLL, lock_timeout=10)
            start_barrier.wait(BARRIER_TIMEOUT)
            result = coordinator.run()
            out.put({'role': role, 'day': day, 'status': result.status, 'reason': result.reason,
                     'next': result.next_action, 'end': time.time(), 'failed_at': adapter.failed_at})
    except BaseException as exc:  # 把任何异常带回父进程，而不是让父进程干等
        out.put({'role': role, 'error': repr(exc)})


class TwoProcessTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _run(self, scenario, days):
        ctx = multiprocessing.get_context('spawn')
        out = ctx.Queue()
        start_barrier, verify_barrier = ctx.Barrier(2), ctx.Barrier(2)
        procs = [ctx.Process(target=_worker, daemon=True,
                             args=(role, str(self.root), days, scenario, start_barrier, verify_barrier, out))
                 for role in ('oas1', 'oas2')]
        for p in procs:
            p.start()
        results, expected, give_up = [], 2 * len(days), time.time() + 90
        try:
            while len(results) < expected and time.time() < give_up:
                try:
                    results.append(out.get(timeout=1))
                except queue.Empty:
                    if not any(p.is_alive() for p in procs):
                        break
        finally:
            for p in procs:
                p.join(5)
                if p.is_alive():
                    p.terminate()
                    p.join(5)
        self.assertEqual([r for r in results if 'error' in r], [])
        self.assertEqual(len(results), expected, results)
        return results

    def _ledger(self, day) -> dict:
        key = sm.make_key(day, 'xinlan', sm.canonical_members(MEMBERS))
        doc = json.loads((self.root / sm.ledger_filename(key)).read_text(encoding='utf-8'))
        self.assertEqual(validate_document(doc, key), [])
        return doc

    def test_simultaneous_final_verification_completes_exactly_once(self):
        days = [f'2026-10-{d:02d}' for d in range(1, 6)]
        results = self._run('normal', days)
        for r in results:
            self.assertEqual((r['status'], r['next']), (S_COMPLETED, 'done'), r)
        for day in days:
            doc = self._ledger(day)
            self.assertEqual(len(doc['rounds']), 1)
            rnd = doc['rounds'][0]
            self.assertEqual(rnd['global']['state'], sm.G_COMPLETED)
            self.assertEqual({p['state'] for p in rnd['participants'].values()}, {sm.P_VERIFIED})
            self.assertEqual([a['status'] for a in rnd['attempts']], [sm.A_DONE, sm.A_DONE])
            self.assertEqual(rnd['late_events'], [])

    def test_one_side_failing_verification_never_yields_completed(self):
        days = [f'2026-10-{d:02d}' for d in range(1, 6)]
        results = self._run('verify_race', days)
        for r in results:
            self.assertEqual((r['status'], r['reason']), (S_FAILED, sm.R_VERIFY_FAILED), r)
        for day in days:
            rnd = self._ledger(day)['rounds'][0]
            self.assertEqual((rnd['global']['state'], rnd['global']['reason']), (sm.G_FAILED, sm.R_VERIFY_FAILED))

    def test_peer_notices_an_unknown_result_within_a_poll_period(self):
        days = [f'2026-10-{d:02d}' for d in range(1, 4)]
        results = self._run('unknown', days)
        for r in results:
            self.assertEqual((r['status'], r['reason'], r['next']), (S_FAILED, sm.R_ATTEMPT_UNKNOWN, 'defer_next_day'), r)
        for day in days:
            failed_at = next(r['failed_at'] for r in results if r['day'] == day and r['role'] == 'oas2')
            seen_at = next(r['end'] for r in results if r['day'] == day and r['role'] == 'oas1')
            self.assertGreaterEqual(seen_at - failed_at, 0)
            self.assertLess(seen_at - failed_at, 2.0)  # 轮询间隔 20ms；远小于 20 秒预算
            rnd = self._ledger(day)['rounds'][0]
            self.assertEqual(rnd['global']['reason'], sm.R_ATTEMPT_UNKNOWN)


if __name__ == '__main__':
    unittest.main()
