from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from module.config.utils import read_file, write_file
from module.multi_account.account import Account


class StoryState:
    """每实例独立保存剧情完成记录，不随日期或账号槽位变化而重置。"""

    def __init__(self, directory: Path, instance: str, revision: str):
        if not instance or any(char in instance for char in '/\\.:'):
            raise ValueError("剧情状态的实例名无效")
        self.path = directory / f".story_rotation_{instance}.json"
        self.revision = revision
        self.data = read_file(str(self.path)) if self.path.exists() else {"version": 1, "accounts": {}}
        if (not isinstance(self.data, dict) or self.data.get("version") != 1
                or not isinstance(self.data.get("accounts"), dict)
                or any(not isinstance(node, dict) for node in self.data["accounts"].values())):
            raise ValueError("剧情状态格式无效，保留原文件等待检查")

    @staticmethod
    def identity(account: Account) -> str:
        # 同一个登录账号的双平台角色分别记录，插入账号不继承旧槽位的完成状态。
        raw = [account.instance, account.login_account.strip().casefold(), account.server,
               account.character, account.apple_or_android]
        return hashlib.sha256(json.dumps(raw, ensure_ascii=False).encode("utf-8")).hexdigest()

    def is_completed(self, account: Account) -> bool:
        node = self.data["accounts"].get(self.identity(account), {})
        # 已确认无入口是角色的持久事实，重标注或调阈值不应重复登录该角色。
        return node.get("status") == "completed"

    def mark(self, account: Account, status: str, error: str = "") -> None:
        if status not in {"running", "completed", "failed"}:
            raise ValueError("剧情状态无效")
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        self.data["accounts"][self.identity(account)] = {
            "account_id": account.account_id,
            "character": account.character,
            "server": account.server,
            "platform": "android" if account.apple_or_android else "ios",
            "status": status,
            "revision": self.revision,
            "updated_at": now,
            "completed_at": now if status == "completed" else "",
            "completion_reason": "courtyard_no_story_entry" if status == "completed" else "",
            "error": error,
        }
        write_file(str(self.path), self.data)


def asset_revision(directory: Path) -> str:
    """记录识别资源版本供诊断，不使已完成角色的记录失效。"""
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".json", ".png"}:
            digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()
