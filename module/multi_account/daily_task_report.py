"""每日任务状态转换和 Markdown 汇总输出。"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path

from module.logger import logger
from module.multi_account.daily_state import DailyStateManager
from module.multi_account.file_lock import atomic_replace_with_retry, interprocess_file_lock
from module.multi_account.daily_task_schedule import (
    is_daily_task_applicable,
    is_daily_task_due,
    is_daily_task_not_time_yet,
)


_MAX_RETRY = 3


# 表格列顺序同时作为每日任务失败时的判断顺序。
TASK_DEFINITIONS = (
    ("courtyard_morning", "庭院05点", "daily_courtyard_morning", "courtyard_morning_dt"),
    ("courtyard_evening", "庭院18点", "daily_courtyard_evening", "courtyard_evening_dt"),
    ("pickup_email", "邮件", "daily_pickup_email", "pickup_email_dt"),
    ("guild_donate", "寮祈愿", "daily_guild_donate_enable", "guild_donate_dt"),
    ("guild_medal_donate", "捐寮勋章", "daily_guild_medal_donate", "guild_medal_donate_dt"),
    ("luck_msg", "每日吉闻", "daily_luck_msg", "luck_msg_dt"),
    ("store_sign", "商店签到", "daily_store_sign", "store_sign_dt"),
    ("buy_sushi", "购买体力", "daily_buy_sushi_count", "sushi_dt"),
    ("summon", "召唤", "daily_one_summon", "summon_dt"),
    ("hunt_kirin", "麒麟", "daily_hunt_kirin", None),
    ("hunt_netherworld", "阴界之门", "daily_hunt_netherworld", None),
    ("cooperation_morning", "协作05点", "daily_cooperation_morning", None),
    ("cooperation_evening", "协作18点", "daily_cooperation_evening", None),
)

_ROTATION_RESULT_TASKS = {"hunt_kirin", "hunt_netherworld", "cooperation_morning", "cooperation_evening"}


def _today(value: object) -> bool:
    try:
        return datetime.fromisoformat(str(value)).date() == datetime.now().date()
    except (TypeError, ValueError):
        return False


def _read_config(config_dir: Path, instance: str) -> dict:
    path = config_dir / f"{str(instance).lower()}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}


def _daily_settings(data: dict) -> dict:
    return data.get("account_rotation", {}).get("daily_task_config", {}) or {}


def _done_record(data: dict) -> dict:
    return data.get("daily_trifles", {}).get("done_record", {}) or {}


def _is_enabled(settings: dict, key: str) -> bool:
    if key == "daily_buy_sushi_count":
        try:
            return int(settings.get(key, -1)) > 0
        except (TypeError, ValueError):
            return False
    return bool(settings.get(key, False))


def _enabled_task_definitions(config_map: dict[str, dict]) -> tuple[tuple[str, str, str, str | None], ...]:
    """按当前实例启用配置，返回稳定顺序的日志任务定义。"""
    enabled_task_names: set[str] = set()
    for data in config_map.values():
        settings = _daily_settings(data)
        enabled_task_names.update(
            task_name
            for task_name, _title, setting_key, _done_key in TASK_DEFINITIONS
            if _is_enabled(settings, setting_key)
        )
    return tuple(
        definition
        for definition in TASK_DEFINITIONS
        if definition[0] in enabled_task_names
    )


def _task_display_name(task_name: str, title: str | None) -> str:
    """缺少人工标题时回退为任务内部名称，避免日志生成失败。"""
    display_name = str(title or "").strip()
    return display_name or task_name


def _is_due(task_name: str, now: datetime) -> bool:
    return is_daily_task_due(task_name, now)


def _not_time_yet(task_name: str, now: datetime) -> bool:
    return is_daily_task_not_time_yet(task_name, now)


def _not_applicable(task_name: str, now: datetime) -> bool:
    """判断 Hunt 子任务是否因星期不对应而不适用。"""
    return not is_daily_task_applicable(task_name, now)


def _format_cooperation_result(result: object) -> str:
    """将协作结果按入口和奖励标签动态转换为 Markdown 文本。"""
    raw = str(result or "none").strip()
    if not raw or raw == "none":
        return "无"

    label_map = {
        ("normal", "jade"): "普通勾协",
        ("normal", "sushi"): "普通体协",
        ("realworld", "jade"): "现世勾协",
        ("realworld", "sushi"): "现世体协",
        "jade": "勾协",
        "sushi": "体协",
        "普通勾协": "普通勾协",
        "普通体协": "普通体协",
        "现世勾协": "现世勾协",
        "现世体协": "现世体协",
    }
    parts = [part.strip() for part in raw.split("+") if part.strip()]
    labels: list[str] = []
    index = 0
    while index < len(parts):
        part = parts[index]
        if part in {"normal", "realworld"} and index + 1 < len(parts):
            label = label_map.get((part, parts[index + 1]))
            if label is None:
                return "无"
            index += 2
        else:
            label = label_map.get(part)
            if label is None:
                return "无"
            index += 1
        if label not in labels:
            labels.append(label)
    return "+".join(labels) if labels else "无"


def _status_text(task: dict | None, *, task_name: str = "", not_time_yet: bool = False) -> str:
    if not task:
        return "未到时间" if not_time_yet else "⏳未执行"
    status = str(task.get("status", "pending"))
    if status == "completed":
        if task_name in {"cooperation_morning", "cooperation_evening"}:
            return _format_cooperation_result(task.get("result", "none"))
        return "✅完成"
    if status == "failed":
        attempts = int(task.get("attempts", 0) or 0)
        return f"❌失败({attempts}/{_MAX_RETRY})"
    if status == "running":
        return "🔄执行中"
    return "未到时间" if not_time_yet else "⏳未执行"


def _account_display_maps(config_dir: Path, instances: list[str]) -> tuple[dict, dict, dict]:
    """一次读取各实例配置，建立显示账号、平台和每日任务配置映射。"""
    display_map: dict[tuple[str, str], str] = {}
    platform_map: dict[tuple[str, str], str] = {}
    config_map: dict[str, dict] = {}
    prefixes = {"oas1": "", "oas2": "", "oas3": "A", "oas4": "B", "oas5": "C"}
    for instance in instances:
        normalized = str(instance).lower()
        data = _read_config(config_dir, normalized)
        config_map[normalized] = data
        accounts = data.get("multi_account_evo", {}) or {}
        prefix = prefixes.get(normalized, "")
        for key, raw in accounts.items():
            if not str(key).startswith("account_list_"):
                continue
            try:
                position = int(str(key).rsplit("_", 1)[1])
            except (TypeError, ValueError):
                continue
            account_id = f"{prefix}{position:02d}" if prefix else f"{normalized}-{position:02d}"
            raw = raw if isinstance(raw, dict) else {}
            email = str(raw.get("account", "") or "").strip()
            identity = (normalized, account_id)
            # 邮箱只用于 Markdown 展示，空值时回退为内部账号标识。
            display_map[identity] = email or account_id
            platform_map[identity] = "安卓" if bool(raw.get("apple_or_android", True)) else "iOS"
    return display_map, platform_map, config_map


def _task_node(state: dict, instance: str, account_id: str, task_name: str) -> dict | None:
    return (
        state.get("instances", {})
        .get(str(instance).lower(), {})
        .get("accounts", {})
        .get(account_id, {})
        .get("tasks", {})
        .get(task_name)
    )


def _mark_running(state: DailyStateManager, instance: str, account_id: str, task_name: str) -> None:
    state.mark_task(instance, account_id, task_name, "running")


def sync_account_result(
    state: DailyStateManager,
    config_dir: str | Path,
    instance: str,
    account_id: str,
    success: bool,
    *,
    error: str = "每日任务执行失败",
    failed_task: str = "",
) -> None:
    """把本次执行结果转换为各子任务状态，再刷新 Markdown 展示文件。"""
    config_dir = Path(config_dir)
    data = _read_config(config_dir, instance)
    settings = _daily_settings(data)
    done = _done_record(data)
    now = datetime.now()
    for task_name, _title, setting_key, done_key in TASK_DEFINITIONS:
        if not _is_enabled(settings, setting_key):
            continue
        existing = _task_node(state.load_today(), instance, account_id, task_name)
        if existing and existing.get("status") == "completed":
            continue
        if task_name in _ROTATION_RESULT_TASKS:
            # Hunt 状态由轮换运行器直接写入，展示刷新不能用旧 DoneRecord 覆盖。
            if existing and existing.get("status") in {"failed", "running", "skipped"}:
                continue
            if not _is_due(task_name, now):
                state.mark_task(instance, account_id, task_name, "pending")
            continue
        if task_name == "guild_donate":
            completed = bool(done.get("guild_donate_finish", False))
        else:
            completed = _today(done.get(done_key, ""))
        if completed:
            _mark_running(state, instance, account_id, task_name)
            state.mark_task(instance, account_id, task_name, "completed")
            continue
        if task_name == failed_task:
            _mark_running(state, instance, account_id, task_name)
            state.mark_task(instance, account_id, task_name, "failed", error=error)
            continue
        if not _is_due(task_name, now):
            if existing is None:
                state.mark_task(instance, account_id, task_name, "pending")
            continue
        if success:
            # 总任务成功但缺少该子任务完成记录时保留未执行，避免虚假标记完成。
            if existing is None:
                state.mark_task(instance, account_id, task_name, "pending")
            continue
        # 没有明确子任务标识时不再猜测失败归属，保留原有子任务状态。
        if existing is None:
            state.mark_task(instance, account_id, task_name, "pending")

    write_markdown(state, config_dir)


def write_markdown(state: DailyStateManager, config_dir: str | Path) -> Path:
    """读取每日状态并生成当天的 Markdown 汇总，不把 Markdown 当作状态源。"""
    config_dir = Path(config_dir)
    project_root = Path(__file__).resolve().parents[2]
    output_dir = project_root / "log" / "dailytask"
    path = output_dir / f"OAS每日任务结果_{datetime.now():%Y-%m-%d}.md"
    temp = None
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        lock_path = output_dir / ".daily_task_report.lock"
        with interprocess_file_lock(lock_path, timeout=10.0, poll_interval=0.02):
            # 获取锁后重新读取最新状态，避免旧快照覆盖其他实例刚写入的结果。
            current = state.load_today()
            instances = [str(instance).lower() for instance in current.get("instances", {})]
            display_map, platform_map, config_map = _account_display_maps(config_dir, instances)
            report_task_definitions = _enabled_task_definitions(config_map)
            now = datetime.now()
            rows: list[str] = []
            cooperation_rows: dict[str, list[str]] = {
                "cooperation_morning": [],
                "cooperation_evening": [],
            }
            task_statistics = {
                task_name: {"completed": 0, "total": 0}
                for task_name, _title, _setting_key, _done_key in report_task_definitions
            }
            for instance, instance_node in sorted(current.get("instances", {}).items()):
                normalized_instance = str(instance).lower()
                data = config_map.get(normalized_instance, {})
                for account_id in sorted((instance_node.get("accounts", {}) or {}).keys()):
                    settings = _daily_settings(data)
                    task_nodes = instance_node.get("accounts", {}).get(account_id, {}).get("tasks", {}) or {}
                    values = []
                    for task_name, _title, setting_key, _done_key in report_task_definitions:
                        if not _is_enabled(settings, setting_key):
                            values.append("⏳未执行")
                            continue
                        if _not_applicable(task_name, now):
                            values.append("-")
                            continue
                        task_node = task_nodes.get(task_name)
                        task_statistics[task_name]["total"] += 1
                        if task_node and task_node.get("status") == "completed":
                            task_statistics[task_name]["completed"] += 1
                        values.append(
                            _status_text(
                                task_node,
                                task_name=task_name,
                                not_time_yet=_not_time_yet(task_name, now),
                            )
                        )
                    identity = (normalized_instance, account_id)
                    display_account = display_map.get(identity, account_id)
                    platform = platform_map.get(identity, "未知")
                    rows.append(
                        "|" + "|".join([display_account, normalized_instance, platform, *values]) + "|"
                    )
                    for task_name, setting_key in (
                        ("cooperation_morning", "daily_cooperation_morning"),
                        ("cooperation_evening", "daily_cooperation_evening"),
                    ):
                        if not _is_enabled(settings, setting_key):
                            continue
                        task_node = task_nodes.get(task_name) or {}
                        if task_node.get("status") != "completed":
                            continue
                        result = _format_cooperation_result(task_node.get("result", "none"))
                        if result == "无":
                            continue
                        cooperation_rows[task_name].append(
                            "|"
                            + "|".join([display_account, normalized_instance, platform, result])
                            + "|"
                        )
            statistic_values = []
            for task_name, _title, _setting_key, _done_key in report_task_definitions:
                statistic = task_statistics[task_name]
                total = statistic["total"]
                statistic_values.append(f'{statistic["completed"]}/{total}' if total else "-")
            rows.append("|" + "|".join(["完成情况统计", "-", "-", *statistic_values]) + "|")
            headers = [
                "账号",
                "模拟器编号",
                "平台",
                *(
                    _task_display_name(task_name, title)
                    for task_name, title, _setting_key, _done_key in report_task_definitions
                ),
            ]
            separator = ["-"] * len(headers)
            content = (
                "|" + "|".join(headers) + "|\n"
                + "|" + "|".join(separator) + "|\n"
                + ("\n".join(rows) + "\n" if rows else "")
                + "\n## 早间协作统计\n\n"
                + "|账号|模拟器编号|平台|协作|\n"
                + "|-|-|-|-|\n"
                + (
                    "\n".join(cooperation_rows["cooperation_morning"]) + "\n"
                    if cooperation_rows["cooperation_morning"]
                    else "|无|-|-|无|\n"
                )
                + "\n## 晚间协作统计\n\n"
                + "|账号|模拟器编号|平台|协作|\n"
                + "|-|-|-|-|\n"
                + (
                    "\n".join(cooperation_rows["cooperation_evening"]) + "\n"
                    if cooperation_rows["cooperation_evening"]
                    else "|无|-|-|无|\n"
                )
            )
            temp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
            with temp.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            atomic_replace_with_retry(temp, path)
            temp = None
    except Exception:
        logger.exception("每日任务 Markdown 更新失败，已忽略展示层异常: %s", path)
    finally:
        if temp is not None:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
    return path
