"""读取轮换购买状态，生成入口页的每周汇总。"""

from datetime import datetime, timedelta
from pathlib import Path

from module.config.utils import read_file
from module.multi_account.account_manager import AccountManager
from tasks.MultiAccountEvo.config import MultiAccountEvo
from tasks.StoryRotation.state import StoryState


def weekly_purchase_summary(config_dir: Path, now: datetime) -> str:
    monday = (now - timedelta(days=now.weekday())).replace(hour=9, minute=0, second=0, microsecond=0)
    start = monday if now >= monday else monday - timedelta(days=7)
    week_key = start.isoformat(timespec="seconds")
    parts = []
    completed_total = total = 0
    unknown = False
    for config_path in sorted(config_dir.glob("oas*.json")):
        instance = config_path.stem.lower()
        try:
            data = read_file(str(config_path))
            rotation = data.get("weekly_purchase_rotation", {})
            if not rotation.get("scheduler", {}).get("enable", False):
                continue
            settings = data.get("account_rotation", {}).get("account_rotation_config", {})
            manager = AccountManager(
                instance, MultiAccountEvo.model_validate(data.get("multi_account_evo", {})),
                order=settings.get("account_order", "1-18"),
                enabled=settings.get("enabled_accounts", "1-18"),
            )
            accounts = manager.get_enabled_accounts()
            state_path = config_dir / f".weekly_purchase_rotation_{instance}.json"
            if state_path.exists():
                state = read_file(str(state_path))
                if not isinstance(state, dict) or state.get("version") != 1 or not isinstance(state.get("weeks"), dict):
                    raise ValueError("每周购买进度格式无效")
                week = state["weeks"].get(week_key, {})
                if not isinstance(week, dict):
                    raise ValueError("每周购买周期格式无效")
            else:
                week = {}
            done = sum(week.get(StoryState.identity(account)) == "completed" for account in accounts)
            parts.append(f"{instance.upper()} {done}/{len(accounts)}")
            completed_total += done
            total += len(accounts)
        except Exception:
            parts.append(f"{instance.upper()} 未知")
            unknown = True
    if not parts:
        return f"本周购买完成情况（{start:%m-%d} 09:00 起）：暂无启用实例"
    overall = "未知" if unknown else f"{completed_total}/{total}"
    return f"本周购买完成情况（{start:%m-%d} 09:00 起）：{' · '.join(parts)} · 合计 {overall}"
