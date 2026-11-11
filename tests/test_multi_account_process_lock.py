from __future__ import annotations

import multiprocessing
import tempfile
import time
import unittest
from pathlib import Path


def _daily_state_worker(directory: str, instance: str, prefix: str, start, result) -> None:
    try:
        from module.multi_account.daily_state import DailyStateManager

        manager = DailyStateManager(directory, lock_timeout=10, recover_instances={instance})
        start.wait(10)
        for index in range(1, 21):
            account_id = f"{prefix}{index:02d}"
            manager.mark_login(instance, account_id, "running")
            manager.mark_login(instance, account_id, "completed")
            manager.load()
        result.put((instance, "ok", ""))
    except BaseException as exc:
        result.put((instance, "error", repr(exc)))


def _ocr_coordinator_worker(directory: str, instance: str, start, result) -> None:
    try:
        from module.multi_account.coordinator import SharedOcrCoordinator

        coordinator = SharedOcrCoordinator(
            directory,
            instance,
            acquire_timeout=10,
            lease_timeout=2,
            turn_grace=0.02,
        )
        start.wait(10)
        for index in range(15):
            with coordinator.lease(f"stress-{index}"):
                time.sleep(0.002)
        result.put((instance, "ok", ""))
    except BaseException as exc:
        result.put((instance, "error", repr(exc)))


class ThreeProcessFileLockTests(unittest.TestCase):
    @staticmethod
    def _run_three_processes(target, directory: str) -> list[tuple[str, str, str]]:
        context = multiprocessing.get_context("spawn")
        start = context.Event()
        result = context.Queue()
        processes = [
            context.Process(target=target, args=(directory, instance, start, result))
            if target is _ocr_coordinator_worker
            else context.Process(target=target, args=(directory, instance, prefix, start, result))
            for instance, prefix in (("oas3", "A"), ("oas4", "B"), ("oas5", "C"))
        ]
        for process in processes:
            process.start()
        start.set()
        outcomes = [result.get(timeout=30) for _ in processes]
        for process in processes:
            process.join(10)
            if process.is_alive():
                process.terminate()
                process.join(5)
            if process.exitcode != 0:
                outcomes.append((str(process.pid), "exit", str(process.exitcode)))
        return sorted(outcomes)

    def test_daily_state_three_process_write_stress(self):
        with tempfile.TemporaryDirectory() as directory:
            outcomes = self._run_three_processes(_daily_state_worker, directory)
            self.assertEqual(outcomes, [("oas3", "ok", ""), ("oas4", "ok", ""), ("oas5", "ok", "")])

            from module.multi_account.daily_state import DailyStateManager

            manager = DailyStateManager(directory)
            for instance, prefix in (("oas3", "A"), ("oas4", "B"), ("oas5", "C")):
                for index in range(1, 21):
                    self.assertEqual(manager.login_status(instance, f"{prefix}{index:02d}"), "completed")
            self.assertFalse(list(Path(directory).glob("*.tmp")))

    def test_ocr_coordinator_three_process_lock_stress(self):
        with tempfile.TemporaryDirectory() as directory:
            outcomes = self._run_three_processes(_ocr_coordinator_worker, directory)
            self.assertEqual(outcomes, [("oas3", "ok", ""), ("oas4", "ok", ""), ("oas5", "ok", "")])
            self.assertFalse(list(Path(directory).glob("*.tmp")))


if __name__ == "__main__":
    multiprocessing.freeze_support()
    unittest.main()
