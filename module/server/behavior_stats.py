# This Python file uses the following encoding: utf-8
"""按需读取 BehaviorTrace JSONL 里的 click / long_click 坐标点与 swipe 轨迹，
供 OASX「统计 → 点击分布 / 滑动轨迹」页面绘制。

设计原则（记录轻量化 / 统计按需化 / 前端渲染化）：

- OAS 正常运行时只由 `Control.click` / `Control.long_click` 在 `extra` 里多写 `x` / `y`，
  由 `Control.swipe` / `Control.swipe_trajectory` 在 `extra` 里写端点（后者再带完整 `trajectory`）。
  没有后台统计线程、没有定时扫描、没有数据库、没有实时聚合。
- 只有接口被请求时才打开当天单个 JSONL、逐行读取一次、返回结果、关闭文件。
- 任务筛选、连线、tooltip、热力图等渲染全部由前端本地完成；后端只做 date / task /
  interaction_type / target 四层等值过滤，返回原始点击点与原始 swipe 轨迹（原始屏幕坐标，
  不做任何坐标变换 / Y 翻转 / 缩放）。
- 一条 swipe 记录 = 一个 ACTION，无论 `trajectory` 有多少个点，`swipe_count` 只 +1。
- 旧 JSONL（只有 click、swipe 无 `trajectory`、坏行）必须能正常读；单条坏 `trajectory`
  只降级该条，绝不让整个接口 500。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from module.server.config_manager import ConfigManager, ConfigNameError

# BehaviorTrace 固定输出目录（见 module/behavior_trace.py 的 _LOG_DIR）。
PROJECT_ROOT = Path.cwd().resolve()
BEHAVIOR_LOG_ROOT = (PROJECT_ROOT / "log" / "behavior").resolve()

# OAS 逻辑分辨率：module/device/screenshot.py 的 check_screen_size 强制截图为该尺寸，
# 所有 asset ROI 与 Control.click 收到的坐标都在此坐标空间；minitouch 的设备分辨率
# 缩放发生在 Control 之后，不影响这里记录的 x / y。所有事件同一坐标空间，故只在
# 响应顶层返回一次，JSONL 每条记录不重复保存宽高。
CANONICAL_SCREEN_WIDTH = 1280
CANONICAL_SCREEN_HEIGHT = 720

_CLICK_ACTIONS = ("click", "long_click")
_SWIPE_ACTION = "swipe"

# interaction_type 取值：ALL = 点击 + 滑动；CLICK = click / long_click；SWIPE = swipe。
INTERACTION_TYPES = ("all", "click", "swipe")


class BehaviorStatsError(Exception):
    """点击统计读取的业务异常，携带建议的 HTTP 状态码。"""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _validated_config_name(script_name: str) -> str:
    """API 的 ``{script_name}`` 就是完整 config_name，用项目统一的
    ``ConfigManager.validate_config_name`` 校验并原样返回。

    不做 ``log_service`` / ``log_stats`` 那种「按 ``_`` 截首段去运行时后缀」——那是为
    ``<date>_<script>.txt`` 人读日志名解析设计的；config_name 本身允许含 ``_``
    （校验只禁 ``. / \\ : * ? " < > |`` 与控制字符），截断会读错 BehaviorTrace 文件。
    """
    try:
        return ConfigManager.validate_config_name(script_name, allow_template=False)
    except ConfigNameError as exc:
        raise BehaviorStatsError(400, f"Invalid config name: {exc}") from exc


def _normalize_interaction_type(value) -> str:
    """把 interaction_type 归一到 ``all`` / ``click`` / ``swipe``；非法值 400。"""
    text = str(value or "all").strip().lower()
    if text not in INTERACTION_TYPES:
        raise BehaviorStatsError(
            400, f"Invalid interaction_type: {value!r} (expected one of {INTERACTION_TYPES})")
    return text


def _behavior_file_path(script_name: str, target_day: date) -> Path:
    """把 (config, date) 定位到 log/behavior/<config>_<date>.jsonl，只允许该固定目录内的文件。"""
    file_name = f"{script_name}_{target_day.isoformat()}.jsonl"
    path = (BEHAVIOR_LOG_ROOT / file_name).resolve()
    try:
        # 机械兜底：即便 config 名校验被绕过，也不允许目标逃出 behavior 目录。
        path.relative_to(BEHAVIOR_LOG_ROOT)
    except ValueError as exc:
        raise BehaviorStatsError(400, "Path escapes behavior log directory") from exc
    if path.name != file_name:
        raise BehaviorStatsError(400, "Invalid config name for behavior log")
    return path


def _coerce_coord(value) -> int | None:
    """把坐标字段安全转成 int；非法 / 缺失返回 None（跳过该点）。"""
    if isinstance(value, bool):  # bool 是 int 子类，明确排除
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return int(round(value))
    return None


def _coerce_traj_point(pt) -> list[int] | None:
    """把 trajectory 里的一个点安全转成 ``[x, y, dt]``；结构 / 数值非法返回 None。"""
    if isinstance(pt, (list, tuple)) and len(pt) == 3:
        x = _coerce_coord(pt[0])
        y = _coerce_coord(pt[1])
        dt = _coerce_coord(pt[2])
        if x is not None and y is not None and dt is not None:
            return [x, y, dt]
    return None


def _parse_point(obj: dict) -> dict | None:
    """把一条已解析的 JSONL 记录转成前端需要的点击点；不符合条件返回 None。"""
    if obj.get("event") != "ACTION":
        return None
    action = obj.get("action")
    if action not in _CLICK_ACTIONS:
        return None
    extra = obj.get("extra")
    if not isinstance(extra, dict):
        return None
    x = _coerce_coord(extra.get("x"))
    y = _coerce_coord(extra.get("y"))
    if x is None or y is None:
        return None

    point: dict = {
        "x": x,
        "y": y,
        "task": str(obj.get("task") or ""),
        "action": action,
        "target": str(obj.get("target") or ""),
        "ts": str(obj.get("ts") or ""),
    }
    elapsed = obj.get("elapsed_ms")
    if isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool):
        point["elapsed_ms"] = int(round(elapsed))
    return point


def _parse_swipe(obj: dict) -> tuple[dict, bool]:
    """把一条 ``action='swipe'`` 的 ACTION 记录转成一条 swipe 轨迹条目。

    返回 ``(swipe_dict, degraded)``。始终返回一条（swipe 就是一条 swipe，哪怕没有轨迹）：
    - ``trajectory`` 缺失 / 空 → ``[]``（旧 JSONL 或 legacy 端点滑动，section 十五）。
    - ``trajectory`` 存在但不是列表、或含 ≥1 个坏点 → 只保留可解析的点，``degraded=True``
      （section 十五：单条降级，不影响其余）。
    - ``start`` / ``end`` 优先取 ``extra`` 里的显式端点；缺失时用轨迹首 / 尾点兜底。
    """
    extra = obj.get("extra")
    extra = extra if isinstance(extra, dict) else {}

    raw_traj = extra.get("trajectory")
    trajectory: list[list[int]] = []
    degraded = False
    if raw_traj is not None:
        if isinstance(raw_traj, list):
            for pt in raw_traj:
                cp = _coerce_traj_point(pt)
                if cp is None:
                    degraded = True
                else:
                    trajectory.append(cp)
        else:
            degraded = True  # trajectory 字段存在但结构完全不对

    sx = _coerce_coord(extra.get("start_x"))
    sy = _coerce_coord(extra.get("start_y"))
    ex = _coerce_coord(extra.get("end_x"))
    ey = _coerce_coord(extra.get("end_y"))
    if (sx is None or sy is None) and trajectory:
        sx, sy = trajectory[0][0], trajectory[0][1]
    if (ex is None or ey is None) and trajectory:
        ex, ey = trajectory[-1][0], trajectory[-1][1]

    point_count = extra.get("point_count")
    if not (isinstance(point_count, int) and not isinstance(point_count, bool) and point_count >= 0):
        point_count = len(trajectory)

    swipe: dict = {
        "task": str(obj.get("task") or ""),
        "action": _SWIPE_ACTION,
        "target": str(obj.get("target") or ""),
        "ts": str(obj.get("ts") or ""),
        "start": [sx, sy] if (sx is not None and sy is not None) else None,
        "end": [ex, ey] if (ex is not None and ey is not None) else None,
        "point_count": point_count,
        "trajectory": trajectory,
    }
    elapsed = obj.get("elapsed_ms")
    if isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool):
        swipe["elapsed_ms"] = int(round(elapsed))
    return swipe, degraded


def read_behavior_clicks(
    script_name: str,
    target_day: date,
    *,
    task: str | None = None,
    interaction_type: str = "all",
    target: str | None = None,
) -> dict:
    """读取某 config 某日期 BehaviorTrace JSONL 中的 click / long_click 点与 swipe 轨迹。

    只读、逐行解析、单次打开单个文件，不缓存、不后台扫描。
    文件不存在 / 空 / 全是坏行 → 返回空结果（不报错）。
    单行坏 JSON / 非 dict → 跳过并计入 ``summary.skipped_lines``。
    单条 swipe 的 ``trajectory`` 坏 → 只降级该条并计入 ``summary.malformed_trajectories``，
    不影响其余行、不让接口 500。

    过滤（四层等值 AND，缺省表示不限）：
    - ``target_day``：文件粒度。
    - ``task``：精确匹配记录的 ``task``。
    - ``interaction_type``：``all`` / ``click`` / ``swipe``（大小写不敏感）。
    - ``target``：精确匹配记录的 ``target``，对 click / swipe 使用同一语义。

    返回（相对旧版为 **additive**，旧字段语义不变）：
    - ``points``：命中过滤的 click / long_click 点，保持 JSONL 事件顺序。
    - ``swipes``：命中过滤的 swipe 轨迹条目（新增）。
    - ``tasks``：命中过滤的 **click** 点里出现过的任务，按首次出现顺序（旧语义：无过滤时
      即当天所有 click 任务）。
    - ``available_tasks`` / ``available_targets``：在「排除自己那一维」的过滤下，click+swipe
      两类记录里 distinct 的 task / target（供前端下拉动态刷新，section 二十三）。
    - ``summary``：``total`` / ``click_count`` / ``long_click_count`` / ``task_count`` /
      ``skipped_lines`` 语义不变；新增 ``swipe_count`` / ``filtered_count`` /
      ``malformed_trajectories``。
    - ``filter``：回显本次生效的 ``task`` / ``interaction_type`` / ``target``。
    """
    config_name = _validated_config_name(script_name)
    itype = _normalize_interaction_type(interaction_type)
    task_filter = str(task).strip() if task not in (None, "") else None
    target_filter = str(target).strip() if target not in (None, "") else None
    path = _behavior_file_path(config_name, target_day)

    points: list[dict] = []
    swipes: list[dict] = []
    click_count = 0
    long_click_count = 0
    skipped_lines = 0
    malformed_trajectories = 0

    task_order: list[str] = []          # 旧 `tasks`：命中过滤的 click 点里出现的任务
    task_seen: set[str] = set()
    avail_tasks: list[str] = []         # 排除 task 维之后，click+swipe 里的 distinct task
    avail_tasks_seen: set[str] = set()
    avail_targets: list[str] = []       # 排除 target 维之后，click+swipe 里的 distinct target
    avail_targets_seen: set[str] = set()

    if path.is_file():
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (ValueError, TypeError):
                    skipped_lines += 1
                    continue
                if not isinstance(obj, dict):
                    skipped_lines += 1
                    continue
                if obj.get("event") != "ACTION":
                    continue
                action = obj.get("action")
                if action in _CLICK_ACTIONS:
                    kind = "click"
                elif action == _SWIPE_ACTION:
                    kind = "swipe"
                else:
                    continue

                rec_task = str(obj.get("task") or "")
                rec_target = str(obj.get("target") or "")
                type_ok = itype == "all" or itype == kind
                task_ok = task_filter is None or rec_task == task_filter
                target_ok = target_filter is None or rec_target == target_filter

                # 下拉候选：各自排除自己那一维，避免选定后只剩自己。
                if type_ok and target_ok and rec_task and rec_task not in avail_tasks_seen:
                    avail_tasks_seen.add(rec_task)
                    avail_tasks.append(rec_task)
                if type_ok and task_ok and rec_target and rec_target not in avail_targets_seen:
                    avail_targets_seen.add(rec_target)
                    avail_targets.append(rec_target)

                if not (type_ok and task_ok and target_ok):
                    continue

                if kind == "click":
                    point = _parse_point(obj)
                    if point is None:
                        continue
                    points.append(point)
                    if point["action"] == "click":
                        click_count += 1
                    else:
                        long_click_count += 1
                    ptask = point["task"]
                    if ptask and ptask not in task_seen:
                        task_seen.add(ptask)
                        task_order.append(ptask)
                else:
                    swipe, degraded = _parse_swipe(obj)
                    if degraded:
                        malformed_trajectories += 1
                    swipes.append(swipe)

    if malformed_trajectories:
        try:  # 惰性 import，告警失败也不影响返回（与 BehaviorTrace 同风格）
            from module.logger import logger

            logger.warning(
                f"behavior stats: {malformed_trajectories} swipe record(s) had a malformed "
                f"trajectory for {config_name} {target_day.isoformat()} (degraded, not dropped)"
            )
        except BaseException:
            pass

    return {
        "config": config_name,
        "date": target_day.isoformat(),
        "screen": {"width": CANONICAL_SCREEN_WIDTH, "height": CANONICAL_SCREEN_HEIGHT},
        "filter": {
            "task": task_filter or "",
            "interaction_type": itype,
            "target": target_filter or "",
        },
        "summary": {
            "total": len(points),
            "click_count": click_count,
            "long_click_count": long_click_count,
            "swipe_count": len(swipes),
            "filtered_count": len(points) + len(swipes),
            "task_count": len(task_order),
            "skipped_lines": skipped_lines,
            "malformed_trajectories": malformed_trajectories,
        },
        "tasks": task_order,
        "available_tasks": avail_tasks,
        "available_targets": avail_targets,
        "points": points,
        "swipes": swipes,
    }
