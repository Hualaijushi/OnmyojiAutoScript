# This Python file uses the following encoding: utf-8
"""式神活动统一任务入口。"""

from datetime import datetime

from module.config.config_model import ConfigModel
from module.exception import (
    GameBugError,
    GameNotRunningError,
    GamePageUnknownError,
    GameStuckError,
    GameTooManyClickError,
    RequestHumanTakeover,
    TaskEnd,
)
from module.logger import logger
from tasks.ActivityShikigami.activities.fake_god import FakeGodAct
from tasks.ActivityShikigami.activities.normal import NormalClimbAct
from tasks.ActivityShikigami.activities.rich_man import RichManAct
from tasks.ActivityShikigami.base_act import BaseAct


ACTIVITY_METHOD_FIELDS = {
    '大富翁': 'run_rich_man',
    '爬塔': 'run_climb',
    '伪神降临': 'run_fakegod',
}


# 调度器会自动 Restart 并重新拉起任务的异常（见 Script._handle_task_exception）。
# 其余异常要么 exit(1) 要么是 TaskEnd，不会被自动重跑，不需要这里处理
AUTO_RECOVERED_ERRORS = (
    GameStuckError, GameTooManyClickError, GameBugError, GamePageUnknownError, GameNotRunningError,
)


class ScriptTask(RichManAct, NormalClimbAct, FakeGodAct, BaseAct):

    def run(self):
        # 区间非法必须在任何游戏操作之前拒绝，不截断、不交换、不回退默认值
        range_error = self.conf.general_config.ap_range_error()
        if range_error:
            raise RequestHumanTakeover(range_error)
        self.before_run()
        sequence = self.conf.general_config.task_sequence_v
        logger.info(f'ActivityShikigami enabled sequence: {sequence}')
        # 本次目标在任务开始时确定：即使体力爬塔排在大富翁之后，也沿用同一个值
        if '爬塔' in sequence and 'ap' in self.conf.general_config.climb_sequence_v:
            self.climb_ap_target()
        guarded = self._ap_random_range_active(sequence)
        started = False
        try:
            for activity_name in sequence:
                if self.time_limit_reached():
                    break
                method_name = ACTIVITY_METHOD_FIELDS[activity_name]
                started = True
                getattr(self, method_name)()
            self.finish_activity_task()
        except TaskEnd:
            raise
        except AUTO_RECOVERED_ERRORS as error:
            if guarded and started:
                self._end_interrupted_execution(error)
            raise

    def _ap_random_range_active(self, sequence) -> bool:
        """本次执行是否包含「区间随机」的体力爬塔。固定次数（含旧配置 N～N）没有随机目标，
        异常后重跑的行为保持原样。"""
        general = self.conf.general_config
        return (
            '爬塔' in sequence
            and 'ap' in general.climb_sequence_v
            and general.ap_limit < general.ap_limit_max
        )

    def _end_interrupted_execution(self, error: Exception) -> None:
        """区间随机的活动执行被卡死 / 页面未知等异常打断：终止本次活动执行，延后到下一次正常排期。

        调度器随后会 Restart 并重新创建 ScriptTask，目标与计数都留不下来，而中断瞬间的战斗
        结果也不可信，所以不重新抽取、不从零续跑、不猜剩余场次、也不重跑已做过的玩法。

        保护靠「活动自己的 next_run 落在未来」成立，因此：① 以**中断时刻**为基准计算失败延后
        （任务开始时刻会让长时间运行后的延后已经过期）；② 写入后从磁盘读回确认确实在未来；
        ③ 写不进去或读回仍不在未来（如失败间隔为 0 且 server_update 为默认 09:00）时，公共异常
        处理的自动 Restart 会让活动立刻重跑，所以改抛 RequestHumanTakeover 走现有人工处理路径
        （推送并退出），原始游戏异常作为异常链保留。不新增冷却配置，不自行发明延后时长。
        """
        counts = {name: count for name, count in self.action_count.items() if count}
        logger.warning(
            f'式神活动被异常打断（体力爬塔本次目标 {self.ap_target} 次，已进入战斗 {counts or "无"}）。'
            '无法可靠确认中断时的进度，不重新随机、不从零继续：本次活动执行终止，'
            '延后到下一次正常排期（失败间隔之后）重新开始。'
        )
        reason = None
        cause: Exception = error
        try:
            self.config.task_delay(
                task=self.scheduled_task_name,
                start_time=datetime.now().replace(microsecond=0),
                success=False,
            )
            next_run = ConfigModel(self.config.config_name).activity_shikigami.scheduler.next_run
            if next_run <= datetime.now():
                reason = f'延后后的下次运行时间 {next_run} 不在未来（失败间隔可能为 0 或过短）'
        except Exception as save_error:
            reason = f'延后排期写入失败：{save_error!r}'
            cause = save_error
            logger.exception(reason)
        if reason is None:
            return
        message = (
            f'式神活动被 {error!r} 打断，本次体力目标和进度无法可靠恢复，且{reason}。'
            '为避免自动 Restart 后重新随机、从零开始，已停止自动运行，需要人工处理：'
            '请检查配置文件是否可写、活动的失败间隔是否大于 0，修复后再手动启动。'
        )
        logger.critical(message)
        raise RequestHumanTakeover(message) from cause
