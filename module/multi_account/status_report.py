from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from module.multi_account.file_lock import atomic_replace_with_retry


class MultiAccountEvoStatusReport:
    """Human-readable desktop mirror of the durable team task state."""

    STATUS_TEXT = {
        "pending": "未开始",
        "running": "进行中",
        "completed": "已完成",
        "failed": "失败",
        "skipped": "已跳过",
    }

    def __init__(
        self,
        config_directory: str | Path,
        output_path: str | Path | None = None,
    ) -> None:
        self.config_directory = Path(config_directory)
        self.output_path = Path(output_path) if output_path else Path.home() / "Desktop" / "小号觉醒状态.txt"

    @staticmethod
    def _channel(account: dict) -> str:
        return "安卓" if bool(account.get("apple_or_android", True)) else "iOS"

    def _groups(self) -> list[dict]:
        configs: dict[str, dict] = {}
        for instance in ("oas3", "oas4", "oas5"):
            path = self.config_directory / f"{instance}.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            configs[instance] = data.get("multi_account_evo", {})
        group_count = int(
            configs["oas3"].get("multi_account_evo_config", {}).get("group_count", 18)
        )
        groups = []
        for group in range(1, group_count + 1):
            accounts = [configs[instance].get(f"account_list_{group}", {}) for instance in ("oas3", "oas4", "oas5")]
            channels = []
            for account in accounts:
                channel = self._channel(account)
                if channel not in channels:
                    channels.append(channel)
            groups.append(
                {
                    "group": group,
                    "accounts": [str(account.get("account") or "未配置") for account in accounts],
                    "channel": "、".join(channels) if channels else "未配置",
                }
            )
        return groups

    def render(self, daily_state: dict) -> str:
        lines = ["小号觉醒状态", f"日期：{daily_state.get('date') or '-'}", ""]
        teams = daily_state.get("teams", {})
        for group in self._groups():
            team_id = f"group_{group['group']:02d}"
            task = teams.get(team_id, {}).get("tasks", {}).get("multi_account_evo", {})
            status = self.STATUS_TEXT.get(str(task.get("status") or "pending"), "未开始")
            updated_at = str(task.get("updated_at") or "-")
            lines.extend(
                [
                    f"账号组{group['group']}",
                    f"账号：{'、'.join(group['accounts'])}",
                    f"渠道：{group['channel']}",
                    f"刷取状态：{status}",
                    f"更新时间：{updated_at}",
                    "",
                ]
            )
        return "\n".join(lines).rstrip() + "\n"

    def refresh(self, daily_state: dict) -> Path:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        content = self.render(daily_state)
        temp = self.output_path.with_name(
            f".{self.output_path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        with temp.open("w", encoding="utf-8-sig", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        atomic_replace_with_retry(temp, self.output_path)
        return self.output_path
