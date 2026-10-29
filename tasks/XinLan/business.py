# This Python file uses the following encoding: utf-8
"""同心之兰的业务常量与业务日换算（P4 适配器复用）。

下面带「未核实」的取值都是占位，要等 P3 真机采样后才能定；改它们之前先看 docs/ROADMAP.md P3。
"""
from datetime import datetime, time, timedelta

BUSINESS_ID = 'xinlan'

# 两端必须一致（加入时逐项比对）。max_rounds=4 = 第一轮 + 最多 3 次自动重来（用户 2026-10-21 确认）；
# retry_wait / budget 沿用核心约定；min_attempt_cost 未核实，P3 测完单次尝试耗时再定
PROTOCOL_PARAMS = {'retry_wait': 30, 'budget': 180, 'min_attempt_cost': 10, 'max_rounds': 4}

# 游戏每日重置时刻（用户 2026-10-22 确认是 0 点），决定账本的业务日
DAILY_RESET = time(0, 0)


def business_day(now: float) -> str:
    """epoch 秒 → 业务日 'YYYY-MM-DD'：重置时刻之前仍算前一天。"""
    moment = datetime.fromtimestamp(now) - timedelta(hours=DAILY_RESET.hour, minutes=DAILY_RESET.minute,
                                                     seconds=DAILY_RESET.second)
    return moment.strftime('%Y-%m-%d')


def next_business_day_start(now: datetime) -> datetime:
    """下一个业务日开始的时刻（严格晚于 now）。"""
    start = datetime.combine(now.date(), DAILY_RESET)
    return start if start > now else start + timedelta(days=1)
