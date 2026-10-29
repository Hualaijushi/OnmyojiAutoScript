"""`module/instance_sync/ledger.py` + `journal.py` 的文件级测试（临时目录，不碰真实 log/）。

锁住：事务只在变更时写盘；违反不变式的变更不落盘；账本损坏 / 未知版本 / 键不符 → 原文件不动、只备份、报错；
账本缺失与「journal 记录过却不在账本里」→ 报 Lost、不重建；拿锁超时；原子写失败时文件保持写前内容；
PermissionError 有界重试；journal 容忍半行。
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from filelock import FileLock

from module.instance_sync import state_machine as sm
from module.instance_sync.errors import (
    InvariantViolation, LedgerCorruptError, LedgerLockTimeout, LedgerLostError, LedgerWriteError,
)
from module.instance_sync.journal import Journal
from module.instance_sync.ledger import Ledger

PARAMS = {'retry_wait': 30, 'budget': 180, 'min_attempt_cost': 10, 'max_rounds': 4}
MEMBERS = sm.canonical_members([('oas1', 'A01'), ('oas2', 'A02')])
PROTOCOL = sm.make_protocol(PARAMS)
KEY = sm.make_key('2026-10-21', 'xinlan', MEMBERS)
ACTOR = sm.Actor('oas1', 'sess-a')
T0 = 1_000_000.0


def _enter(round_id='r1'):
    def fn(doc, now):
        return sm.op_enter(doc, now, ACTOR, members=MEMBERS, protocol=PROTOCOL, rendezvous_timeout=600,
                           new_round_id=round_id)
    return fn


class LedgerTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.journal = Journal(self.root / 'oas1.journal.jsonl')
        self.ledger = self.make_ledger()

    def make_ledger(self, **kwargs):
        kwargs.setdefault('clock', lambda: T0)
        kwargs.setdefault('sleep', lambda s: None)
        return Ledger(self.root, KEY, self.journal, **kwargs)

    def create(self):
        result, changed = self.ledger.transact(_enter(), create_if_missing=True)
        self.assertTrue(changed)
        return result


class TransactionTest(LedgerTestCase):
    def test_first_enter_creates_the_ledger_file(self):
        result = self.create()
        self.assertEqual(result.value['outcome'], sm.OUT_CREATED)
        doc = json.loads(self.ledger.path.read_text(encoding='utf-8'))
        self.assertEqual(doc['key'], KEY)
        self.assertEqual(len(doc['rounds']), 1)

    def test_unchanged_transaction_does_not_write(self):
        self.create()
        before = (self.ledger.path.read_bytes(), self.ledger.path.stat().st_mtime_ns)
        value, changed = self.ledger.transact(lambda doc, now: 'seen')
        self.assertEqual((value, changed), ('seen', False))
        self.assertEqual((self.ledger.path.read_bytes(), self.ledger.path.stat().st_mtime_ns), before)

    def test_nothing_is_created_when_the_transaction_changes_nothing(self):
        value, changed = self.ledger.transact(lambda doc, now: 1, create_if_missing=True)
        self.assertEqual((value, changed), (1, False))
        self.assertFalse(self.ledger.path.exists())

    def test_invariant_violation_is_not_written(self):
        self.create()
        before = self.ledger.path.read_bytes()

        def corrupting(doc, now):
            doc['rounds'][-1]['global'].update(state=sm.G_COMPLETED, reason='completed', at=now)

        with self.assertRaises(InvariantViolation):
            self.ledger.transact(corrupting)
        self.assertEqual(self.ledger.path.read_bytes(), before)

    def test_exception_in_the_mutator_leaves_the_file_alone_and_releases_the_lock(self):
        self.create()
        before = self.ledger.path.read_bytes()
        with self.assertRaises(RuntimeError):
            self.ledger.transact(lambda doc, now: (_ for _ in ()).throw(RuntimeError('boom')))
        self.assertEqual(self.ledger.path.read_bytes(), before)
        value, _ = self.ledger.transact(lambda doc, now: 'again')  # 锁已释放
        self.assertEqual(value, 'again')

    def test_transaction_time_is_taken_inside_the_lock(self):
        clock_values = iter([T0 + 5])
        ledger = self.make_ledger(clock=lambda: next(clock_values))
        seen = []
        ledger.transact(lambda doc, now: seen.append(now), create_if_missing=True)
        self.assertEqual(seen, [T0 + 5])


class CorruptionTest(LedgerTestCase):
    def _assert_stopped_and_untouched(self, raw: bytes, *, backup_expected=True):
        self.ledger.path.write_bytes(raw)
        for create in (False, True):  # create_if_missing 不能成为「覆盖损坏文件」的后门
            with self.assertRaises(LedgerCorruptError) as ctx:
                self.ledger.transact(_enter('r9'), create_if_missing=create)
            self.assertEqual(self.ledger.path.read_bytes(), raw)
        backups = list(self.root.glob('*.corrupt-*'))
        if backup_expected:
            self.assertEqual(len(backups), 1, backups)  # 同一份内容只备份一次
            self.assertEqual(backups[0].read_bytes(), raw)
            self.assertEqual(ctx.exception.backup, str(backups[0]))

    def test_truncated_json(self):
        self.create()
        self._assert_stopped_and_untouched(self.ledger.path.read_bytes()[:-20])

    def test_binary_garbage(self):
        self._assert_stopped_and_untouched(b'\xff\xfe\x00garbage')

    def test_unknown_schema_version(self):
        self._assert_stopped_and_untouched(json.dumps({'schema_version': 99, 'key': KEY, 'rounds': []}).encode())

    def test_structurally_broken_round(self):
        self.create()
        doc = json.loads(self.ledger.path.read_text(encoding='utf-8'))
        del doc['rounds'][0]['global']
        self._assert_stopped_and_untouched(json.dumps(doc).encode())

    def test_ledger_for_another_key_is_rejected(self):
        other = sm.make_key('2026-10-22', 'xinlan', MEMBERS)
        self._assert_stopped_and_untouched(json.dumps(sm.new_document(other)).encode())

    def test_unreadable_file_is_reported_without_a_backup(self):
        self.create()
        with patch.object(Path, 'read_bytes', side_effect=PermissionError('locked')):
            with self.assertRaises(LedgerCorruptError):
                self.ledger.transact(lambda doc, now: None)


class LostLedgerTest(LedgerTestCase):
    def test_missing_ledger_without_create_is_lost(self):
        with self.assertRaises(LedgerLostError):
            self.ledger.transact(lambda doc, now: None)

    def test_missing_ledger_that_the_journal_knows_is_lost_even_with_create(self):
        self.create()
        self.journal.append(self.ledger.name, 'r1', 'enter:created')
        self.ledger.path.unlink()
        with self.assertRaises(LedgerLostError):
            self.ledger.transact(_enter('r2'), create_if_missing=True)
        self.assertFalse(self.ledger.path.exists())  # 没有被悄悄重建

    def test_replaced_ledger_without_the_journaled_round_is_lost(self):
        self.create()
        self.journal.append(self.ledger.name, 'r1', 'enter:created')
        self.ledger.path.write_text(json.dumps(sm.new_document(KEY)), encoding='utf-8')
        with self.assertRaises(LedgerLostError):
            self.ledger.transact(lambda doc, now: None)

    def test_fresh_day_with_no_journal_history_creates_normally(self):
        result = self.create()
        self.assertEqual(result.value['outcome'], sm.OUT_CREATED)


class LockAndWriteTest(LedgerTestCase):
    def test_lock_timeout(self):
        self.create()
        ledger = self.make_ledger(lock_timeout=0.2)
        holder = FileLock(str(ledger.lock_path))
        holder.acquire()
        try:
            with self.assertRaises(LedgerLockTimeout):
                ledger.transact(lambda doc, now: None)
        finally:
            holder.release()
        ledger.transact(lambda doc, now: None)  # 释放后恢复可用

    def test_write_failure_keeps_the_previous_content(self):
        self.create()
        before = self.ledger.path.read_bytes()

        def change(doc, now):
            return sm.op_fail(doc, now, ACTOR, round_id='r1', reason='boom')

        with patch('module.instance_sync.ledger.atomic_write', side_effect=OSError('disk full')):
            with self.assertRaises(LedgerWriteError):
                self.ledger.transact(change)
        self.assertEqual(self.ledger.path.read_bytes(), before)
        value, changed = self.ledger.transact(change)  # 状态没有前进，重做仍然成立
        self.assertTrue(value.ok and changed)

    def test_permission_error_is_retried_with_backoff_then_succeeds(self):
        self.create()
        sleeps = []
        ledger = self.make_ledger(sleep=sleeps.append)
        real = __import__('module.instance_sync.ledger', fromlist=['atomic_write']).atomic_write
        calls = {'n': 0}

        def flaky(*args, **kwargs):
            calls['n'] += 1
            if calls['n'] <= 2:
                raise PermissionError('antivirus')
            return real(*args, **kwargs)

        with patch('module.instance_sync.ledger.atomic_write', side_effect=flaky):
            _, changed = ledger.transact(lambda doc, now: sm.op_fail(doc, now, ACTOR, round_id='r1', reason='boom'))
        self.assertTrue(changed)
        self.assertEqual(sleeps, [0.05, 0.1])
        self.assertEqual(json.loads(ledger.path.read_text(encoding='utf-8'))['rounds'][0]['global']['state'], 'failed')

    def test_permission_error_forever_is_a_bounded_write_failure(self):
        self.create()
        sleeps = []
        ledger = self.make_ledger(sleep=sleeps.append)
        before = ledger.path.read_bytes()
        with patch('module.instance_sync.ledger.atomic_write', side_effect=PermissionError('locked')):
            with self.assertRaises(LedgerWriteError):
                ledger.transact(lambda doc, now: sm.op_fail(doc, now, ACTOR, round_id='r1', reason='boom'))
        self.assertEqual(len(sleeps), 3)
        self.assertEqual(ledger.path.read_bytes(), before)


class JournalTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / 'sub' / 'oas1.journal.jsonl'

    def test_append_and_reload(self):
        journal = Journal(self.path)
        self.assertFalse(journal.knows_ledger('L'))
        self.assertTrue(journal.append('L', 'r1', 'enter:created', extra=1))
        self.assertTrue(journal.knows_ledger('L'))
        self.assertEqual(Journal(self.path).known_rounds('L'), {'r1'})
        self.assertEqual(Journal(self.path).known_rounds('other'), set())

    def test_torn_last_line_and_garbage_lines_are_skipped(self):
        journal = Journal(self.path)
        journal.append('L', 'r1', 'enter:created')
        with open(self.path, 'a', encoding='utf-8') as f:
            f.write('not json\n{"ledger": "L"}\n{"ledger": "L", "round_id": "r2", "event"')
        self.assertEqual(Journal(self.path).known_rounds('L'), {'r1'})

    def test_append_failure_is_swallowed(self):
        journal = Journal(self.path)
        with patch('builtins.open', side_effect=OSError('read-only')):
            self.assertFalse(journal.append('L', 'r1', 'enter:created'))
        self.assertFalse(journal.knows_ledger('L'))


if __name__ == '__main__':
    unittest.main()
