"""账号轮换每日子任务的时间规则。"""

from __future__ import annotations

from datetime import datetime, time


def is_daily_task_due(task_name: str, now: datetime) -> bool:
    """判断子任务在当前时间是否允许执行。"""
    current = now.time()
    if task_name in {"courtyard_morning", "cooperation_morning"}:
        return time(5, 0) <= current < time(18, 0)
    if task_name in {"courtyard_evening", "cooperation_evening"}:
        return current >= time(18, 0)
    if task_name == "hunt_kirin":
        return now.weekday() <= 3 and time(6, 0) <= current <= time(23, 0)
    if task_name == "hunt_netherworld":
        return now.weekday() >= 4 and time(18, 0) <= current <= time(23, 0)
    return True


def is_daily_task_not_time_yet(task_name: str, now: datetime) -> bool:
    """判断子任务今天仍未到开始时间。"""
    current = now.time()
    if task_name in {"courtyard_morning", "cooperation_morning"}:
        return current < time(5, 0)
    if task_name in {"courtyard_evening", "cooperation_evening"}:
        return current < time(18, 0)
    if task_name == "hunt_kirin":
        return now.weekday() <= 3 and current < time(6, 0)
    if task_name == "hunt_netherworld":
        return now.weekday() >= 4 and current < time(18, 0)
    return False


def is_daily_task_applicable(task_name: str, now: datetime) -> bool:
    """判断子任务在当前星期是否适用。"""
    if task_name == "hunt_kirin":
        return now.weekday() <= 3
    if task_name == "hunt_netherworld":
        return now.weekday() >= 4
    return True
