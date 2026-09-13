# This Python file uses the following encoding: utf-8
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from module.server.api_logger import ApiLoggingRoute
from module.server.behavior_stats import BehaviorStatsError, read_behavior_clicks
from module.server.config_manager import ConfigManager, ConfigNameError
from module.server.log_stats import log_stats_service

stats_app = APIRouter(
    prefix="/stats",
    tags=["stats"],
    route_class=ApiLoggingRoute,
)


class BattleStatsResponse(BaseModel):
    count: int
    avg_duration_seconds: float


class TaskRunStatsResponse(BaseModel):
    start_time: str
    end_time: str
    duration_seconds: float
    battle: BattleStatsResponse | None = None


class TaskStatsResponse(BaseModel):
    run_count: int
    total_duration_seconds: float
    battle: BattleStatsResponse | None = None
    runs: list[TaskRunStatsResponse] = Field(default_factory=list)


class StatsResponse(BaseModel):
    script_name: str
    total_runtime_seconds: float
    total_task_run_count: int
    total_battle_count: int
    tasks: dict[str, TaskStatsResponse] = Field(default_factory=dict)


class StatsAvailableDatesResponse(BaseModel):
    script_name: str
    dates: list[str] = Field(default_factory=list)


class BehaviorScreen(BaseModel):
    width: int
    height: int


class BehaviorClickPoint(BaseModel):
    x: int
    y: int
    task: str
    action: str
    target: str
    ts: str
    elapsed_ms: int | None = None


class BehaviorSwipeEntry(BaseModel):
    task: str
    action: str
    target: str
    ts: str
    start: list[int] | None = None
    end: list[int] | None = None
    point_count: int
    trajectory: list[list[int]] = Field(default_factory=list)
    elapsed_ms: int | None = None


class BehaviorClickSummary(BaseModel):
    total: int
    click_count: int
    long_click_count: int
    swipe_count: int = 0
    filtered_count: int = 0
    task_count: int
    skipped_lines: int
    malformed_trajectories: int = 0


class BehaviorClickFilter(BaseModel):
    task: str = ""
    interaction_type: str = "all"
    target: str = ""


class BehaviorClicksResponse(BaseModel):
    config: str
    date: str
    screen: BehaviorScreen
    filter: BehaviorClickFilter
    summary: BehaviorClickSummary
    tasks: list[str] = Field(default_factory=list)
    available_tasks: list[str] = Field(default_factory=list)
    available_targets: list[str] = Field(default_factory=list)
    points: list[BehaviorClickPoint] = Field(default_factory=list)
    swipes: list[BehaviorSwipeEntry] = Field(default_factory=list)


class StatsUpdateResponse(BaseModel):
    script_name: str
    total_runtime_seconds: float
    total_task_run_count: int
    total_battle_count: int
    changed_tasks: dict[str, TaskStatsResponse] = Field(default_factory=dict)
    removed_tasks: list[str] = Field(default_factory=list)


def _parse_target_date(date_text: str) -> date:
    try:
        return datetime.strptime(date_text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid date format, expected YYYY-MM-DD") from exc


@stats_app.get("/{script_name}/dates", response_model=StatsAvailableDatesResponse)
async def stats_available_dates(script_name: str):
    return log_stats_service.list_available_dates(script_name)


@stats_app.get("/{script_name}/behavior/clicks", response_model=BehaviorClicksResponse)
async def behavior_clicks(
    script_name: str,
    date_text: str = Query(..., alias="date", description="YYYY-MM-DD"),
    task: str | None = Query(None, description="按任务名精确筛选；缺省=全部"),
    interaction_type: str = Query(
        "all", description="交互类型：all（点击+滑动） | click（click/long_click） | swipe"),
    target: str | None = Query(None, description="按 target 精确筛选（click / swipe 同一语义）；缺省=全部"),
):
    """按需读取当天 BehaviorTrace JSONL 中的 click / long_click 坐标点与 swipe 轨迹。

    只读取 `log/behavior/<config>_<date>.jsonl` 单个文件、逐行解析一次；
    文件不存在 / 空 / 全是坏行时返回空 `points` / `swipes`，不视为服务器错误。

    过滤为 `date AND task AND interaction_type AND target` 四层等值 AND；缺省 = 不限。
    响应相对旧版为 additive：旧字段（`points` / `tasks` / `summary` 的旧计数）语义不变，
    新增 `swipes` / `summary.swipe_count` / `available_tasks` / `available_targets` / `filter`。
    """
    try:
        config_name = ConfigManager.validate_config_name(script_name, allow_template=False)
    except ConfigNameError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    target_day = _parse_target_date(date_text)
    itype = (interaction_type or "all").strip().lower()
    if itype not in ("all", "click", "swipe"):
        raise HTTPException(
            status_code=422,
            detail="interaction_type must be one of: all, click, swipe")
    try:
        return read_behavior_clicks(
            config_name, target_day,
            task=task, interaction_type=itype, target=target)
    except BehaviorStatsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@stats_app.get("/{script_name}", response_model=StatsResponse)
async def stats_snapshot(
    script_name: str,
    date_text: str = Query(..., alias="date", description="YYYY-MM-DD"),
):
    target_day = _parse_target_date(date_text)
    return log_stats_service.build_stats(script_name, target_day)


@stats_app.get("/{script_name}/stream")
async def stats_stream(
    script_name: str,
    date_text: str = Query(..., alias="date", description="YYYY-MM-DD"),
):
    target_day = _parse_target_date(date_text)
    if target_day != date.today():
        raise HTTPException(status_code=400, detail="Only today's date supports SSE stream")

    response = StreamingResponse(
        log_stats_service.stream_events(script_name, target_day),
        media_type="text/event-stream",
    )
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Connection"] = "keep-alive"
    response.headers["X-Accel-Buffering"] = "no"
    return response
