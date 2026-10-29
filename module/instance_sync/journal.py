# This Python file uses the following encoding: utf-8
"""每实例一份只追加的本地 journal：只用来发现「账本丢了」和做审计。

journal 不是执行依据：不能靠它恢复账本、也不能靠它重发请求。
它只回答一个问题：我这个实例以前在账本里留下过哪些轮次？账本里缺了其中任何一个，就说明账本被删 / 被替换了。

写入顺序是「先写账本，再写 journal」：崩溃在两者之间只会少记一条（检测变弱一点），
不会出现「journal 引用了账本里从没存在过的轮次」造成的误报。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable

from module.logger import logger


class Journal:
    def __init__(self, path, clock: Callable[[], float] = time.time):
        self.path = Path(path)
        self.clock = clock
        self._rounds: dict[str, set[str]] = {}
        self._load()

    def _load(self) -> None:
        try:
            lines = self.path.read_text(encoding='utf-8').splitlines()
        except FileNotFoundError:
            return
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning(f'Instance sync journal unreadable, lost-ledger detection is weaker: {exc}')
            return
        for line in lines:
            try:
                event = json.loads(line)
                self._rounds.setdefault(event['ledger'], set()).add(event['round_id'])
            except (ValueError, KeyError, TypeError):
                continue  # 崩溃可能留下半行，直接跳过

    def knows_ledger(self, ledger: str) -> bool:
        return bool(self._rounds.get(ledger))

    def known_rounds(self, ledger: str) -> set[str]:
        return set(self._rounds.get(ledger, ()))

    def append(self, ledger: str, round_id: str, event: str, **detail) -> bool:
        """追加一条事件。写失败只告警：journal 不能反过来影响业务。"""
        record = {'ts': self.clock(), 'ledger': ledger, 'round_id': round_id, 'event': event, **detail}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
        except OSError as exc:
            logger.warning(f'Instance sync journal append failed: {exc}')
            return False
        self._rounds.setdefault(ledger, set()).add(round_id)
        return True
