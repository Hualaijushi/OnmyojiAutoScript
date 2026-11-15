"""每账号独立战斗进度；不复用组队觉醒与每日任务的完成状态。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from datetime import date, datetime
from pathlib import Path

from module.multi_account.file_lock import atomic_replace_with_retry, interprocess_file_lock


class RotationProgressError(RuntimeError):
    """进度不可信时停止该账号，保留记录。"""


def account_identity(instance: str, position: int, login: str, server: str, character: str) -> str:
    """用摘要绑定账号身份，避免记录明文登录凭据。"""
    values = [instance.lower(), int(position), login.strip().casefold(), server.strip(), character.strip()]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode('utf-8')).hexdigest()


class RotationProgress:
    """按实例跨天保存进度，写入前使用进程锁与原子替换。"""

    def __init__(self, directory: Path, instance: str, *, day: str | None = None, reset_generation: int = 0):
        instance = instance.lower()
        if instance not in {'oas3', 'oas4', 'oas5'}:
            raise RotationProgressError('仅支持已配置的 oas3、oas4、oas5 实例')
        self.day = date.fromisoformat(day).isoformat() if day else date.today().isoformat()
        self.directory = Path(directory)
        if type(reset_generation) is not int or reset_generation < 0:
            raise RotationProgressError('进度重置批次无效')
        self.reset_generation = reset_generation
        self.path = self.directory / f'.meta_demon_rotation_{instance}_continuing.json'
        self.lock_path = self.directory / f'.meta_demon_rotation_{instance}.lock'
        self.instance = instance

    def _load(self) -> dict:
        if not self.path.exists():
            return {'instance': self.instance, 'generation': self.reset_generation,
                    'legacy_import': self.reset_generation == 0, 'accounts': {}}
        try:
            state = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RotationProgressError('账号轮换进度无法读取，保留原文件') from exc
        if (not isinstance(state, dict) or state.get('instance') != self.instance
                or type(state.get('generation')) is not int or state['generation'] < 0
                or type(state.get('legacy_import')) is not bool or not isinstance(state.get('accounts'), dict)):
            raise RotationProgressError('账号轮换进度格式不匹配，保留原文件')
        if self.reset_generation < state['generation']:
            raise RotationProgressError('进度重置批次小于已有批次，请检查实例配置')
        if state['generation'] != self.reset_generation:
            backup = self.path.with_name(f'{self.path.name}.backup-{uuid.uuid4().hex}')
            with self.path.open('rb') as source, backup.open('xb') as destination:
                shutil.copyfileobj(source, destination)
                destination.flush()
                os.fsync(destination.fileno())
            state = {'instance': self.instance, 'generation': self.reset_generation,
                     'legacy_import': False, 'accounts': {}}
            self._save(state)
        return state

    def _legacy_account(self, account_id: str, identity: str):
        """按日期倒序找身份匹配的最近旧记录，不合并不同日期。"""
        pattern = re.compile(rf'^\.meta_demon_rotation_{re.escape(self.instance)}_(\d{{4}}-\d{{2}}-\d{{2}})\.json$')
        paths = sorted((p for p in self.directory.iterdir() if pattern.fullmatch(p.name)),
                       key=lambda p: p.name, reverse=True)
        for path in paths:
            match = pattern.fullmatch(path.name)
            try:
                old = json.loads(path.read_text(encoding='utf-8'))
                date.fromisoformat(match.group(1))
            except (ValueError, OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise RotationProgressError('旧轮换进度无法读取，保留原文件') from exc
            if (not isinstance(old, dict) or old.get('date') != match.group(1)
                    or old.get('instance') != self.instance or not isinstance(old.get('accounts'), dict)):
                raise RotationProgressError('旧轮换进度格式不匹配，保留原文件')
            item = old['accounts'].get(account_id)
            if item is not None and not isinstance(item, dict):
                raise RotationProgressError('旧账号进度格式无效，保留原文件')
            if item and item.get('identity') == identity:
                return dict(item)
        return None

    def _save(self, state: dict) -> None:
        temporary = self.directory / f'.{self.path.name}.{uuid.uuid4().hex}.tmp'
        with temporary.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(state, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        atomic_replace_with_retry(temporary, self.path, timeout=5)

    def update(self, account_id: str, identity: str, action: str, *, target: int, reason: str = '',
               expected_state: dict | None = None) -> dict:
        if not account_id or not identity or type(target) is not int or target < 1:
            raise RotationProgressError('账号身份或目标次数无效')
        with interprocess_file_lock(self.lock_path, timeout=10):
            state = self._load()
            accounts = state['accounts']
            item = accounts.get(account_id)
            if action == 'resume_from_courtyard' and (item is None or item != expected_state):
                raise RotationProgressError('庭院核对期间进度已变化，保留记录并停止')
            is_new = item is None
            if item is None:
                item = self._legacy_account(account_id, identity) if state['legacy_import'] else None
                item = item or {'identity': identity, 'entered': 0, 'phase': 'idle', 'status': 'pending', 'reason': ''}
                accounts[account_id] = item
            if item.get('identity') != identity:
                raise RotationProgressError('账号身份与既有进度不一致，停止该账号')
            count = item.get('entered')
            phase = item.get('phase')
            if type(count) is not int or count < 0 or phase not in {'idle', 'pending', 'entered'}:
                raise RotationProgressError('账号战斗进度格式无效，保留原文件')
            if is_new:
                self._save(state)
            if action == 'read':
                return dict(item)
            if action == 'begin':
                if phase != 'idle' or count >= target:
                    raise RotationProgressError('战斗进度未结束或已达目标')
                item.update(phase='pending', status='running', reason='')
            elif action == 'entered':
                if phase != 'pending':
                    raise RotationProgressError('缺少对应的战斗开始记录')
                item.update(entered=count + 1, phase='entered', status='running')
            elif action == 'finished':
                if phase != 'entered':
                    raise RotationProgressError('战斗是否已开始无法确认')
                item.update(phase='idle', status='completed' if count >= target else 'pending')
            elif action == 'not_entered':
                if phase != 'pending':
                    raise RotationProgressError('不存在待确认的战斗')
                item.update(phase='idle', status='pending')
            elif action == 'resume_from_courtyard':
                if phase not in {'pending', 'entered'}:
                    raise RotationProgressError('不存在需要恢复的旧战斗标记')
                # 仅核对庭院后解除标记，入场次数既不补计也不回退。
                item.update(phase='idle', status='completed' if count >= target else 'pending', reason='')
            elif action == 'score_result':
                if phase != 'idle' or count < target or reason not in {'积分已领取', '无可领取积分'}:
                    raise RotationProgressError('积分结果与已完成场次不匹配')
                item.update(status='completed', reason=reason, score_pending=False)
            elif action == 'stop':
                if phase != 'idle':
                    raise RotationProgressError('存在未结束战斗，需先核实')
                item.update(status='incomplete', reason=reason)
            else:
                raise RotationProgressError('未知的进度操作')
            item.update(target=target, updated_at=datetime.now().isoformat(timespec='seconds'))
            self._save(state)
            return dict(item)
