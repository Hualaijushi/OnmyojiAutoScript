from dataclasses import dataclass
from math import exp
from threading import Lock
from time import monotonic, sleep
from typing import Callable

from module.base.utils.random import random_delay, random_triangular


@dataclass(frozen=True)
class FatigueSnapshot:
    task: float
    global_: float
    task_active_seconds: float = 0.0
    global_active_seconds: float = 0.0


@dataclass(frozen=True)
class FatigueBreakResult:
    kind: str
    duration: float
    probability: float
    before: FatigueSnapshot
    after: FatigueSnapshot
    cooldown: float = 0.0
    # idle 事件率（次 / 小时），rest 结果保持默认 0.0
    idle_rate: float = 0.0


class FatigueManager:
    def __init__(
        self,
        config,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self.config = config
        self._clock = clock
        self._sleep = sleeper
        now = self._clock()
        self._global_active_started_at = now
        self._global_elapsed = 0.0
        self._global_activity_depth = 1
        self._task_active_started_at: float | None = None
        self._task_elapsed = 0.0
        self._task_identity: str | None = None
        self._task_load_factor = float(config.load_factor)
        self._task_repetitions = 0
        self._task_recovery = 0.0
        self._global_recovery = 0.0
        self._rest_cooldown_until = 0.0
        self._active_break_kind: str | None = None
        # 上一次 idle 判断时记录的任务 active 时间，用于按真实时间间隔换算单节点概率。
        self._last_idle_check_task_elapsed = 0.0
        # scheduler_idle（无任务可执行的调度空档）自然恢复用的入口快照。
        # 起点时间用 monotonic 墙钟，与 active elapsed 无关；未处于 scheduler_idle 时为 None。
        self._scheduler_idle_started_at: float | None = None
        self._scheduler_idle_global_start = 0.0
        self._scheduler_idle_recovery_applied = 0.0

    def update_config(self, config) -> None:
        self.config = config
        if self._task_identity is not None:
            self._task_load_factor = float(config.load_factor)
            self._normalize_task_recovery()

    @property
    def enabled(self) -> bool:
        return bool(self.config.enable)

    @property
    def task_identity(self) -> str | None:
        return self._task_identity

    @property
    def task_repetitions(self) -> int:
        return self._task_repetitions

    @property
    def load_factor(self) -> float:
        return self._task_load_factor

    def set_load_factor(self, value: float) -> None:
        value = max(0.8, min(1.3, float(value)))
        self.config.load_factor = value
        self._task_load_factor = value
        self._normalize_task_recovery()

    @property
    def state(self) -> str:
        if not self.enabled:
            return 'disabled'
        if self._active_break_kind is not None:
            return self._active_break_kind
        if self.rest_cooldown_remaining() > 0:
            return 'cooldown'
        return 'normal'

    @property
    def activity_state(self) -> str:
        if self._active_break_kind is not None:
            return self._active_break_kind
        if self._global_activity_depth <= 0:
            return 'scheduler_idle'
        return 'active'

    def begin_task(
        self,
        identity: str,
        load_factor: float = 1.0,
        restart: bool = False,
    ) -> bool:
        if identity == self._task_identity and not restart:
            self._task_load_factor = load_factor
            self._normalize_task_recovery()
            return False
        now = self._clock()
        self._task_identity = identity
        self._task_elapsed = 0.0
        self._task_active_started_at = (
            now
            if self._global_activity_depth > 0 and self._active_break_kind is None
            else None
        )
        self._task_load_factor = load_factor
        self._task_repetitions = 0
        self._task_recovery = 0.0
        # 新任务 / restart：idle 检查基准与 TaskFatigue 生命周期一致，一并归零。
        self._last_idle_check_task_elapsed = 0.0
        return True

    def begin_global_activity(self) -> None:
        if self._global_activity_depth == 0:
            self._end_scheduler_idle_session()
            self._start_active_segments(self._clock())
        self._global_activity_depth += 1

    def end_global_activity(self) -> None:
        if self._global_activity_depth <= 0:
            return
        self._global_activity_depth -= 1
        if self._global_activity_depth == 0:
            self._finish_active_segments(self._clock())
            self._begin_scheduler_idle_session()

    def _begin_scheduler_idle_session(self) -> None:
        # 进入 scheduler_idle：记录入口 G0 与起点时间，之后始终基于这个快照计算
        # “截至当前应恢复多少”，只追加增量，读取多少次都不会重复恢复。
        g0 = self.global_fatigue()
        self._scheduler_idle_started_at = self._clock()
        self._scheduler_idle_global_start = g0
        self._scheduler_idle_recovery_applied = 0.0

    def _end_scheduler_idle_session(self) -> None:
        # 退出 scheduler_idle：先把本轮已产生的自然恢复落定，再清理快照。
        # 下一次进入 scheduler_idle 会建立全新的独立 baseline。
        if self._scheduler_idle_started_at is None:
            return
        self._apply_scheduler_idle_recovery()
        self._scheduler_idle_started_at = None
        self._scheduler_idle_global_start = 0.0
        self._scheduler_idle_recovery_applied = 0.0

    def _apply_scheduler_idle_recovery(self) -> None:
        # scheduler_idle 超过等待期后，GlobalFatigue 按指数曲线自然恢复。
        # 前 recovery_delay_minutes 分钟只冻结，不恢复。
        if self._scheduler_idle_started_at is None:
            return
        cfg = self.config.scheduler_idle
        idle_minutes = max(0.0, self._clock() - self._scheduler_idle_started_at) / 60.0
        if idle_minutes <= cfg.recovery_delay_minutes:
            return
        ratio = 1.0 - exp(
            -(idle_minutes - cfg.recovery_delay_minutes) / cfg.recovery_tau_minutes
        )
        target = self._scheduler_idle_global_start * ratio
        delta = target - self._scheduler_idle_recovery_applied
        if delta <= 0.0:
            return
        # 追加到现有 GlobalRecovery，且不得超过当前 RawGlobal，避免形成“未来恢复额度”。
        room = max(0.0, self._raw_global_fatigue() - self._global_recovery)
        applied = min(delta, room)
        if applied <= 0.0:
            return
        self._global_recovery += applied
        self._scheduler_idle_recovery_applied += applied

    def _start_active_segments(self, now: float) -> None:
        if self._global_activity_depth > 0 or self._active_break_kind is not None:
            return
        self._global_active_started_at = now
        if self._task_identity is not None:
            self._task_active_started_at = now

    def _finish_active_segments(self, now: float) -> None:
        if self._global_active_started_at is not None:
            self._global_elapsed += max(0.0, now - self._global_active_started_at)
            self._global_active_started_at = None
        if self._task_active_started_at is not None:
            self._task_elapsed += max(0.0, now - self._task_active_started_at)
            self._task_active_started_at = None

    def _pause_for_break(self) -> None:
        self._finish_active_segments(self._clock())

    def _resume_after_break(self) -> None:
        if self._global_activity_depth <= 0:
            return
        now = self._clock()
        self._global_active_started_at = now
        if self._task_identity is not None:
            self._task_active_started_at = now

    def task_active_elapsed(self) -> float:
        elapsed = self._task_elapsed
        if self._task_active_started_at is not None:
            elapsed += max(0.0, self._clock() - self._task_active_started_at)
        return elapsed

    def global_active_elapsed(self) -> float:
        elapsed = self._global_elapsed
        if self._global_active_started_at is not None:
            elapsed += max(0.0, self._clock() - self._global_active_started_at)
        return elapsed

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(100.0, value))

    @staticmethod
    def logistic_probability(score: float, maximum: float, steepness: float, midpoint: float) -> float:
        return maximum / (1.0 + exp(-steepness * (score - midpoint)))

    def _raw_task_fatigue(self) -> float:
        if self._task_identity is None:
            return 0.0
        return self._calculate_raw_task_fatigue(
            active_seconds=self.task_active_elapsed(),
            repetitions=self._task_repetitions,
            load_factor=self._task_load_factor,
        )

    def _calculate_raw_task_fatigue(
        self,
        *,
        active_seconds: float,
        repetitions: int,
        load_factor: float,
    ) -> float:
        minutes = max(0.0, active_seconds) / 60.0
        task = self.config.task
        # 时间项描述持续操作，重复项描述单调行为，两项共同受任务注意负荷系数影响。
        return (
            task.time_weight * (1.0 - exp(-((minutes / task.time_scale_minutes) ** 2)))
            + task.repeat_weight * (1.0 - exp(-max(0, repetitions) / task.repeat_scale))
        ) * load_factor

    def task_fatigue(self) -> float:
        return self._clamp(self._raw_task_fatigue() - self._task_recovery)

    def _raw_global_fatigue(self) -> float:
        minutes = self.global_active_elapsed() / 60.0
        global_config = self.config.global_fatigue
        # 饱和曲线以前期缓慢、后期明显的方式描述本次 OAS 连续运行造成的整体疲劳。
        return 100.0 * (
            1.0 - exp(-((minutes / global_config.time_scale_minutes) ** global_config.exponent))
        )

    def global_fatigue(self) -> float:
        # 读取即惰性结算 scheduler_idle 自然恢复；结果只由起点与真实经过时间决定，
        # 与本函数被调用的次数无关。
        self._apply_scheduler_idle_recovery()
        return self._clamp(self._raw_global_fatigue() - self._global_recovery)

    def snapshot(self) -> FatigueSnapshot:
        return FatigueSnapshot(
            task=self.task_fatigue(),
            global_=self.global_fatigue(),
            task_active_seconds=self.task_active_elapsed(),
            global_active_seconds=self.global_active_elapsed(),
        )

    def ui_snapshot(self) -> dict[str, object]:
        snapshot = self.snapshot()
        return {
            'fatigue_enabled': self.enabled,
            'task_fatigue': round(snapshot.task, 2),
            'global_fatigue': round(snapshot.global_, 2),
            'fatigue_load_factor': round(self.load_factor, 2),
            'fatigue_state': self.state,
            'fatigue_cooldown_remaining': round(self.rest_cooldown_remaining(), 1),
            'fatigue_load_factor_preview': self.load_factor_preview(),
        }

    def idle_score(self, snapshot: FatigueSnapshot | None = None) -> float:
        snapshot = snapshot or self.snapshot()
        weights = self.config.weights
        return weights.idle_task * snapshot.task + weights.idle_global * snapshot.global_

    def rest_score(self, snapshot: FatigueSnapshot | None = None) -> float:
        snapshot = snapshot or self.snapshot()
        weights = self.config.weights
        return weights.rest_task * snapshot.task + weights.rest_global * snapshot.global_

    def idle_intensity(self, score: float) -> float:
        # 疲劳强度：标准 logistic，范围 (0, 1)。低疲劳趋近 0，高疲劳趋近 1，
        # 永远不等于 1。它本身不表示单个安全节点的触发概率。
        idle = self.config.idle
        return 1.0 / (1.0 + exp(-idle.steepness * (score - idle.midpoint)))

    def idle_rate_per_hour(self, snapshot: FatigueSnapshot | None = None) -> float:
        # 每小时 idle 事件率：低疲劳保留基础值 rate_base（自然走神），随疲劳强度
        # 线性升到上限 rate_max。高疲劳趋近 rate_max，但每次 idle 后 TaskFatigue
        # 会恢复，长期均值通常明显低于上限。
        snapshot = snapshot or self.snapshot()
        idle = self.config.idle
        intensity = self.idle_intensity(self.idle_score(snapshot))
        return idle.rate_base + (idle.rate_max - idle.rate_base) * intensity

    @staticmethod
    def _node_probability_from_rate(rate_per_hour: float, delta_seconds: float) -> float:
        # 按距上一次 idle 判断经过的真实 active 时间间隔，把事件率换算成本节点概率。
        # 节点越密集 Δt 越小、单节点概率越低；总体事件率由时间而非节点数量决定。
        return 1.0 - exp(
            -max(0.0, rate_per_hour) * max(0.0, delta_seconds) / 3600.0
        )

    def rest_probability(self, snapshot: FatigueSnapshot | None = None) -> float:
        if self.rest_cooldown_remaining() > 0:
            return 0.0
        probability = self.config.rest.probability
        return self.logistic_probability(
            self.rest_score(snapshot),
            probability.maximum,
            probability.steepness,
            probability.midpoint,
        )

    def rest_cooldown_remaining(self) -> float:
        return max(0.0, self._rest_cooldown_until - self._clock())

    @staticmethod
    def _duration_range(config, fatigue: float) -> tuple[float, float, float]:
        # 三角分布 (最短, 最长, 众数)。疲劳越高：上限按 span 抬升，众数从
        # mode_minimum_seconds 线性移到 mode_maximum_seconds。
        ratio = max(0.0, min(1.0, fatigue / 100.0))
        span_ratio = config.range_floor_ratio + (1.0 - config.range_floor_ratio) * ratio
        high = config.minimum_seconds + (config.maximum_seconds - config.minimum_seconds) * span_ratio
        mode = config.mode_minimum_seconds + (config.mode_maximum_seconds - config.mode_minimum_seconds) * ratio
        return config.minimum_seconds, high, min(high, mode)

    def _idle_duration(self, task_fatigue: float) -> float:
        return random_triangular(*self._duration_range(self.config.idle, task_fatigue))

    def _rest_duration(self, global_fatigue: float) -> float:
        return random_triangular(*self._duration_range(self.config.rest, global_fatigue))

    @staticmethod
    def _limit_duration(
        duration: float,
        max_break_seconds: float | None,
        minimum_seconds: float,
    ) -> float:
        if max_break_seconds is None:
            return duration
        if max_break_seconds < minimum_seconds:
            return 0.0
        return max(0.0, min(duration, max_break_seconds))

    def _apply_idle_recovery(self, duration: float) -> None:
        minutes = duration / 60.0
        self._accumulate_recovery(
            self.config.idle.task_recovery_per_minute * minutes,
            self.config.idle.global_recovery_per_minute * minutes,
        )

    @staticmethod
    def _nonlinear_recovery(duration: float, maximum: float, tau_minutes: float) -> float:
        return maximum * (1.0 - exp(-(duration / 60.0) / tau_minutes))

    def _apply_rest_recovery(self, duration: float) -> None:
        rest = self.config.rest
        self._accumulate_recovery(
            self._nonlinear_recovery(
                duration, rest.task_recovery_maximum, rest.task_recovery_tau_minutes
            ),
            self._nonlinear_recovery(
                duration, rest.global_recovery_maximum, rest.global_recovery_tau_minutes
            ),
        )

    def _accumulate_recovery(self, task_amount: float, global_amount: float) -> None:
        self._task_recovery = min(
            self._raw_task_fatigue(), self._task_recovery + max(0.0, task_amount)
        )
        self._global_recovery = min(
            self._raw_global_fatigue(), self._global_recovery + max(0.0, global_amount)
        )

    def _normalize_task_recovery(self) -> None:
        self._task_recovery = min(self._task_recovery, self._raw_task_fatigue())

    def load_factor_preview(self) -> list[dict[str, float]]:
        # Tooltip 参考场景：贴近当前高频副本（约 20~30 秒一轮，一小时 120~180 次），
        # 取 n=170 作为统一参考中值。真实运行仍使用真实 repetitions。
        reference_active_seconds = 60.0 * 60.0
        reference_repetitions = 170
        reference_global_fatigue = 10.0
        reference_node_seconds = 25.0
        preview = []
        for step in range(11):
            factor = 0.8 + step * 0.05
            task_fatigue = self._clamp(
                self._calculate_raw_task_fatigue(
                    active_seconds=reference_active_seconds,
                    repetitions=reference_repetitions,
                    load_factor=factor,
                )
            )
            snapshot = FatigueSnapshot(task=task_fatigue, global_=reference_global_fatigue)
            score = self.idle_score(snapshot)
            intensity = self.idle_intensity(score)
            rate = self.idle_rate_per_hour(snapshot)
            preview.append(
                {
                    'factor': round(factor, 2),
                    'task_fatigue': round(task_fatigue, 2),
                    'idle_score': round(score, 2),
                    'idle_intensity': round(intensity, 4),
                    'idle_rate_per_hour': round(rate, 4),
                    'idle_probability_at_25s': round(
                        self._node_probability_from_rate(rate, reference_node_seconds), 6
                    ),
                }
            )
        return preview

    def _start_rest_cooldown(self, duration: float) -> float:
        cooldown = self.config.cooldown
        base = cooldown.base_minutes * 60.0 + duration * cooldown.rest_duration_multiplier
        jitter = random_delay(cooldown.jitter_minimum, cooldown.jitter_maximum)
        seconds = base * jitter
        self._rest_cooldown_until = self._clock() + seconds
        return seconds

    def try_break(
        self,
        *,
        safe: bool,
        repeat_completed: bool = False,
        max_break_seconds: float | None = None,
        should_resume: Callable[[], bool] | None = None,
        on_check: Callable[[FatigueSnapshot], None] | None = None,
        on_break: Callable[[str, float, FatigueSnapshot], None] | None = None,
    ) -> FatigueBreakResult | None:
        if not self.enabled or not safe or self._task_identity is None:
            return None
        if repeat_completed:
            self._task_repetitions += 1

        before = self.snapshot()
        if on_check is not None:
            on_check(before)
        # 本节点对应的任务 active 时间，用于计算距上一次 idle 判断的真实间隔。
        node_active_elapsed = self.task_active_elapsed()
        rest_probability = self.rest_probability(before)
        if rest_probability > 0 and random_delay(0.0, 1.0) < rest_probability:
            duration = self._limit_duration(
                self._rest_duration(before.global_),
                max_break_seconds,
                self.config.rest.minimum_seconds,
            )
            if duration <= 0:
                return None
            self._active_break_kind = 'rest'
            self._pause_for_break()
            completed = False
            try:
                if on_break is not None:
                    on_break('rest', duration, before)
                self._sleep(duration)
                completed = True
            finally:
                self._active_break_kind = None
                if completed and (should_resume is None or should_resume()):
                    self._resume_after_break()
                else:
                    self.end_global_activity()
            self._apply_rest_recovery(duration)
            cooldown = self._start_rest_cooldown(duration)
            # rest 触发后本轮不再判断 idle。把 idle 基准推进到当前 active，
            # rest 不计入 active，因此后续 Δt 天然不含 rest 时间，也不会保留 rest 前的旧 Δt。
            self._last_idle_check_task_elapsed = node_active_elapsed
            return FatigueBreakResult(
                kind='rest',
                duration=duration,
                probability=rest_probability,
                before=before,
                after=self.snapshot(),
                cooldown=cooldown,
            )

        idle_rate = self.idle_rate_per_hour(before)
        idle_delta_seconds = max(0.0, node_active_elapsed - self._last_idle_check_task_elapsed)
        idle_probability = self._node_probability_from_rate(idle_rate, idle_delta_seconds)
        # 无论本节点是否触发 idle，都推进检查基准，避免未触发的时间被下一个节点重复计入。
        self._last_idle_check_task_elapsed = node_active_elapsed
        if random_delay(0.0, 1.0) >= idle_probability:
            return None
        duration = self._limit_duration(
            self._idle_duration(before.task),
            max_break_seconds,
            self.config.idle.minimum_seconds,
        )
        if duration <= 0:
            return None
        self._active_break_kind = 'idle'
        self._pause_for_break()
        completed = False
        try:
            if on_break is not None:
                on_break('idle', duration, before)
            self._sleep(duration)
            completed = True
        finally:
            self._active_break_kind = None
            if completed and (should_resume is None or should_resume()):
                self._resume_after_break()
            else:
                self.end_global_activity()
        self._apply_idle_recovery(duration)
        return FatigueBreakResult(
            kind='idle',
            duration=duration,
            probability=idle_probability,
            before=before,
            after=self.snapshot(),
            idle_rate=idle_rate,
        )


_manager_lock = Lock()
_managers: dict[str, FatigueManager] = {}


def get_fatigue_manager(identity: str, config) -> FatigueManager:
    with _manager_lock:
        manager = _managers.get(identity)
        if manager is None:
            manager = FatigueManager(config)
            _managers[identity] = manager
        else:
            manager.update_config(config)
        return manager


def reset_fatigue_managers() -> None:
    with _manager_lock:
        _managers.clear()
