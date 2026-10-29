# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey

import zerorpc
import zmq
import re
import cv2
import time
import os
import inflection
import json
from queue import Empty

from datetime import date
import threading
from module.device.device import Device
from typing import Any, Callable
from datetime import datetime, timedelta
from pathlib import Path
from cached_property import cached_property
from pydantic import BaseModel, ValidationError
from threading import Thread
from multiprocessing.queues import Queue
from module.config.utils import convert_to_underscore, DEFAULT_TIME
from module.config.config import Config
from module.device.env import IS_WINDOWS
from module.base.utils import load_module
from module.base.decorator import del_cached_property
from module.logger import logger
from module.exception import *
from module.fatigue import get_fatigue_manager
from module.behavior_trace import configure_behavior_trace, get_behavior_trace
from module.server.i18n import I18n
from module.image.rpc import ensure_image_server_ready, set_image_low_spec_mode
from module.ocr.rpc import (
    ensure_ocr_server_ready,
    set_ocr_logging_enabled,
    set_ocr_model_size,
)
from module.script import ScriptRuntimeController, ScriptRuntimeDecision
from module.script.team_sync import TeamSync
from module.script.loop_controller import LoopController, LoopParams, set_controller
from module.instance_sync.team import (
    GO as TEAM_GO, POSTPONE as TEAM_POSTPONE, WAIT_NOTIFY as TEAM_WAIT_NOTIFY, YIELD_DELAY as TEAM_YIELD_DELAY,
)
from tasks.Restart.server_update import delay_pending_tasks_for_server_update, is_server_update_window
from module.server.log_service import build_error_log_dir_name

_log_switch_lock = threading.Lock()#线程锁

# 循环等待对方 / 等待完成时的检查间隔（秒）
LOOP_POLL_INTERVAL = 2.0
# 循环步骤在门口被判推迟时，这些原因说明配置不对，再等也等不到，直接停止循环；其余原因稍后再试
LOOP_CONFIG_REASONS = ('role_conflict', 'peer_task_off', 'peer_not_paired')


class Script:
    # 类级默认值：不经 __init__ 构造的 Script（测试里常见）也能直接 run
    _fatigue_prepared_for: str | None = None
    _run_ended = False

    def __init__(self, config_name: str ='oas') -> None:
        logger.hr('Start', level=0)
        self.server = None
        self.state_queue: Queue = None
        self.command_queue: Queue = None
        self._emulator_down = False
        self.runtime = ScriptRuntimeController(self)
        self.gui_update_task: Callable = None  # 回调函数, gui进程注册当每次config更新任务的时候更新gui的信息
        self.config_name = config_name
        # Skip first restart
        self.is_first_task = True
        # 步骤开始前已经按这个任务建立过疲劳上下文：Script.run 不重复初始化
        self._fatigue_prepared_for: str | None = None
        # 本次 Script.run 是否正常走到了任务自己的结束出口（TaskEnd）
        self._run_ended = False
        # Failure count of tasks
        # Key: str, task name, value: int, failure count
        self.failure_record = {}
        self.last_task_runtime_outcome: dict[str, Any] | None = None
        # 运行loop的线程
        self.loop_thread: Thread = None
        # 低配模式属于进程级运行参数，只在脚本进程创建时读取一次。
        # OASX 中途修改配置不会影响正在运行的脚本。
        self.low_spec_mode = bool(self.config.script.device.low_spec_mode)
        set_image_low_spec_mode(self.low_spec_mode)
        set_ocr_model_size('small' if self.low_spec_mode else 'medium')
        if self.low_spec_mode:
            logger.info(
                'Low spec mode enabled: frame cache=10s, '
                'OCR model=small, image threshold offset=-0.1'
            )
        self.fatigue_manager = get_fatigue_manager(
            self.config_name, self.config.global_game.fatigue
        )
        self.fatigue_manager.end_global_activity()
        # 行为观测开关属进程级运行参数，只在脚本进程创建时读取一次，运行中不动态重载。
        configure_behavior_trace(
            self.config_name,
            enabled=bool(self.config.script.optimization.behavior_trace_enable),
        )

    def attach_runtime_channels(self, state_queue: Queue, command_queue: Queue) -> None:
        self.state_queue = state_queue
        self.command_queue = command_queue
        Thread(target=self._publish_fatigue_state, daemon=True).start()
        Thread(target=self._listen_runtime_commands, daemon=True).start()

    def _publish_fatigue_state(self) -> None:
        while True:
            if self.state_queue:
                self.state_queue.put({'fatigue': self.fatigue_manager.ui_snapshot()})
            time.sleep(2)

    def _listen_runtime_commands(self) -> None:
        while True:
            try:
                command = self.command_queue.get(timeout=1)
            except Empty:
                continue
            if not isinstance(command, dict):
                continue
            if command.get('command') == 'loop_cancel':
                # 界面停止前，父进程让本进程自己把循环写成已取消；boot_id / loop_id 对不上的旧命令会被忽略
                self.loop_controller.cancel_by_command(command)
                continue
            if command.get('command') == 'set_fatigue_load_factor':
                self.fatigue_manager.set_load_factor(command.get('value', 1.1))
                if self.state_queue:
                    self.state_queue.put({'fatigue': self.fatigue_manager.ui_snapshot()})

    @cached_property
    def team_sync(self) -> TeamSync:
        # 每个配置一个进程，loop() 开头就会访问，这个时刻就是脚本启动时刻
        return TeamSync(self.config_name, started_at=datetime.now())

    @cached_property
    def loop_controller(self) -> LoopController:
        # 属于脚本进程：配置对象会反复重载，循环状态不能放在配置里
        controller = LoopController(self.config_name, notify=self._loop_notify)
        set_controller(self.config_name, controller)
        return controller

    def _loop_notify(self, text: str) -> None:
        self.config.notifier.push(title='御魂循环', content=f'<{self.config_name}> {text}')

    @cached_property
    def config(self) -> "Config":
        try:
            from module.config.config import Config
            config = Config(config_name=self.config_name)
            return config
        except RequestHumanTakeover:
            logger.critical('Request human takeover')
            exit(1)
        except Exception as e:
            logger.exception(e)
            exit(1)

    @cached_property
    def device(self) -> Device | None:
        try:
            from module.device.device import Device
            device = Device(config=self.config)
            return device
        except RequestHumanTakeover:
            logger.critical('Request human takeover')
            exit(1)
        except Exception as e:
            logger.exception(e)
            exit(1)

    @cached_property
    def checker(self):
        """
        占位函数，在alas中是检查服务器是否正常的
        :return:
        """
        return None

    def save_error_log(self):
        """
        保存错误现场到 ./log/error/<script_name>_<timestamp_ms>。

        保存内容包括:
        - 最近一段截图, 文件名为时间戳 PNG。
        - 当前脚本日志的截取内容, 文件名为 log.txt。

        说明:
        - 新错误目录名会带上脚本名, 便于前端区分不同脚本产生的错误。
        - 目录名和脚本名都会经过统一净化, 避免路径注入。
        """
        from module.base.utils import save_image
        from module.handler.sensitive_info import (handle_sensitive_image,
                                                   handle_sensitive_logs)
        if self.config.script.error.save_error:
            if not os.path.exists('./log/error'):
                os.mkdir('./log/error')
            # 用统一规则生成错误目录名, 目录格式为 <script_name>_<timestamp_ms>。
            folder_name = build_error_log_dir_name(self.config_name, int(time.time() * 1000))
            folder = f'./log/error/{folder_name}'
            logger.warning(f'Saving error: {folder}')
            os.mkdir(folder)
            for data in self.device.screenshot_deque:
                image_time = datetime.strftime(data['time'], '%Y-%m-%d_%H-%M-%S-%f')
                image = handle_sensitive_image(data['image'])
                save_image(image, f'{folder}/{image_time}.png')
            with open(logger.log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                start = 0
                for index, line in enumerate(lines):
                    line = line.strip(' \r\t\n')
                    if re.match('^═{15,}$', line):
                        start = index
                lines = lines[start - 2:]
                lines = handle_sensitive_logs(lines)
            with open(f'{folder}/log.txt', 'w', encoding='utf-8') as f:
                f.writelines(lines)

    def init_server(self, port: int) -> int:
        """
        初始化zerorpc服务，返回端口号
        :return:
        """
        self.server = zerorpc.Server(self)
        try:
            self.server.bind(f'tcp://127.0.0.1:{port}')
            return port
        except zmq.error.ZMQError:
            logger.error(f"Ocr server cannot bind on port {port}")
            return None

    def run_server(self) -> None:
        """
        启动zerorpc服务
        :return:
        """
        self.server.run()

    def gui_args(self, task: str) -> str:
        """
        获取给gui显示的参数
        :return:
        """
        return self.config.gui_args(task=task)

    def gui_menu(self) -> str:
        """
        获取给gui显示的菜单
        :return:
        """
        return self.config.gui_menu

    def gui_task(self, task: str) -> str:
        """
        获取给gui显示的任务 的参数的具体值
        :return:
        """
        return self.config.model.gui_task(task=task)

    def gui_set_task(self, task: str, group: str, argument: str, value) -> bool:
        """
        设置给gui显示的任务 的参数的具体值
        :return:
        """
        # 验证参数
        task = convert_to_underscore(task)
        group = convert_to_underscore(group)
        argument = convert_to_underscore(argument)
        # pandtic验证
        if isinstance(value, str):
            if len(value) == 8:
                try:
                    value = datetime.strptime(value, '%H:%M:%S').time()
                except ValueError:
                    pass


        path = f'{task}.{group}.{argument}'
        task_object = getattr(self.config.model, task, None)
        group_object = getattr(task_object, group, None)
        argument_object = getattr(group_object, argument, None)

        if argument_object is None:
            logger.error(f'Set arg {task}.{group}.{argument}.{value} failed')
            return False

        try:
            setattr(group_object, argument, value)
            argument_object = getattr(group_object, argument, None)
            logger.info(f'Set arg {task}.{group}.{argument}.{argument_object}')
            self.config.save()  # 我是没有想到什么方法可以使得属性改变自动保存的
            return True
        except ValidationError as e:
            logger.error(e)
            return False

    @zerorpc.stream
    def gui_mirror_image(self):
        """
        获取给gui显示的镜像
        :return: cv2的对象将 numpy 数组转换为字节串。接下来MsgPack 进行序列化发送方将图像数据转换为字节串
        """
        # return msgpack.packb(cv2.imencode('.jpg', self.device.screenshot())[1].tobytes())
        img = cv2.cvtColor(self.device.screenshot(), cv2.COLOR_RGB2BGR)
        self.device.stuck_record_clear()
        ret, buffer = cv2.imencode('.jpg', img)
        yield buffer.tobytes()

    def _gui_update_tasks(self) -> None:
        """
        获取更新任务后 pending waiting 的任务 和 当前的任务的数据。打包给gui显示
        :return:
        """
        data = {}
        pending = []
        waiting = []
        task = {}
        if self.config.task is not None and self.config.task.next_run < datetime.now():
            task["name"] = self.config.task.command
            task["next_run"] = str(self.config.task.next_run)
        data["task"] = task

        for p in self.config.pending_task[1:]:
            item = {"name": p.command, "next_run": str(p.next_run)}
            pending.append(item)

        for w in self.config.waiting_task:
            item = {"name": w.command, "next_run": str(w.next_run)}
            waiting.append(item)


        data["pending"] = pending
        data["waiting"] = waiting

        if self.gui_update_task is not None:
            self.gui_update_task(data)

    def _gui_set_status(self, status: str) -> None:
        """
        设置给gui显示的状态
        :param status: 可以在gui中显示的状态 有 "Init", "Empty"(不显示), "Run"(运行中), "Error", "Free"(空闲)
        :return:
        """
        data = {"status": status}
        if self.gui_update_task is not None:
            self.gui_update_task(data)

    def gui_task_list(self) -> str:
        """
        获取给gui显示的任务列表
        :return:
        """
        result = {}
        for key, value in self.config.model.dict().items():
            if isinstance(value, str):
                continue
            if key == "restart":
                continue
            if "scheduler" not in value:
                continue

            scheduler = value["scheduler"]
            item = {"enable": scheduler["enable"],
                    "next_run": str(scheduler["next_run"])}
            key = self.config.model.type(key)
            result[key] = item
        return json.dumps(result)

    def wait_until(self, future):
        """
        Wait until a specific time.

        Args:
            future (datetime):

        Returns:
            bool: True if wait finished, False if config changed or the team peer is waiting for me.
        """
        future = future + timedelta(seconds=1)
        self.config.start_watching()
        while 1:
            if datetime.now() > future:
                return True
            # if self.stop_event is not None:
            #     if self.stop_event.is_set():
            #         logger.info("Update event detected")
            #         logger.info(f"[{self.config_name}] exited. Reason: Update")
            #         exit(0)

            time.sleep(5)

            if self.config.should_reload():
                return False
            # 对方在组队任务门口等我：打断空闲等待，回到调度器把那个任务拉到现在（同一次等待只打断一次）
            peer_task = self.team_sync.peer_request(self.config)
            if peer_task is not None:
                logger.info(f'Team sync: peer is waiting at {peer_task}, stop idle wait')
                return False

    @staticmethod
    def _in_sleep_window(t, start, end) -> bool:
        if start == end:
            return False
        if start < end:
            return start <= t < end
        return t >= start or t < end

    @staticmethod
    def _next_time_point(now: datetime, end) -> datetime:
        candidate = now.replace(hour=end.hour, minute=end.minute, second=end.second, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    def _antiban_wake_time(self, now: datetime):
        ab = self.config.script.anti_ban
        if not ab.enable:
            return None
        wake = None
        if self._in_sleep_window(now.time(), ab.sleep_start, ab.sleep_end):
            wake = self._next_time_point(now, ab.sleep_end)
        limit = ab.daily_active_limit.total_seconds()
        if limit > 0:
            if getattr(self, '_active_date', None) != now.date():
                self._active_date = now.date()
                self._active_seconds_today = 0
            rest_until = getattr(self, '_rest_until', None)
            if rest_until and now < rest_until:
                wake = max(wake, rest_until) if wake else rest_until
            elif getattr(self, '_active_seconds_today', 0) >= limit:
                self._rest_until = now + ab.long_rest_duration
                self._active_seconds_today = 0
                wake = max(wake, self._rest_until) if wake else self._rest_until
        return wake

    def get_next_task(self) -> str:
        """
        获取下一个任务的名字, 大驼峰。
        :return:
        """
        while True:
            # 对方在某个组队任务门口等我：把我这边的同一任务改成现在运行，按原来的调度顺序排
            self.team_sync.answer(self.config)
            self._loop_prepare_schedule()
            task = self.config.get_next()
            if self._loop_postpone_deferred():
                del_cached_property(self, "config")
                continue
            self.config.task = task
            if self.state_queue:
                self.state_queue.put({"schedule": self.config.get_schedule_data()})
            now = datetime.now()
            antiban_wake = self._antiban_wake_time(now)
            if antiban_wake is not None:
                task.next_run = max(task.next_run, antiban_wake)
            rest_until = antiban_wake if antiban_wake is not None and antiban_wake > now else None
            self.team_sync.on_schedule(self.config, task.command, task.next_run, rest_until=rest_until)
            # 任务时间到了返回任务名称
            if task.next_run <= now:
                return task.command
            if self.loop_controller.live:
                # 循环进行中没有可跑的任务（等对方完成 / 等未恢复的任务）：短间隔检查，不睡到下一个任务
                self._loop_idle_poll()
                continue
            # 根据策略执行等待逻辑
            decision = self.runtime.handle_wait_during_idle(task.next_run)
            if decision == ScriptRuntimeDecision.RESCHEDULE:
                logger.info('Idle wait requested scheduler refresh, reload config and reschedule')
                del_cached_property(self, "config")
            elif decision == ScriptRuntimeDecision.FAILED:
                logger.warning('Idle wait preparation failed, reload config and retry scheduling')
                del_cached_property(self, "config")

    def _loop_prepare_schedule(self) -> None:
        """每次取任务前：消费一次性开关、把循环钩子挂到当前的配置对象上。"""
        try:
            self._loop_consume_request()
            controller = self.loop_controller
            controller.bind_board(self.team_sync.board)
            self.config.scheduler_hook = controller.schedule_hook
            if controller.live:
                self.team_sync.loop_allows = lambda name: controller.outranks_current_step(self.config, name)
                self.team_sync.loop_step_task = controller.current_step()
                rank_of = controller.rank_of(self.config)
                self.team_sync.rank_of = rank_of
                controller.publish_step_rank(rank_of(controller.current_step() or ''))
                controller.tick()
            else:
                self.team_sync.loop_step_task = None
                self.team_sync.rank_of = None
                self.team_sync.loop_allows = None
        except Exception as e:
            logger.exception(f'Loop schedule preparation failed: {e}')

    def _loop_consume_request(self) -> None:
        """一次性「开始循环」开关：读到就立刻关回并保存，只提交这一次请求。"""
        orochi = getattr(self.config.model, 'orochi', None)
        conf = getattr(orochi, 'loop_config', None)
        if conf is None or not conf.start_loop:
            return
        conf.start_loop = False
        self.config.save()
        status = orochi.orochi_config.user_status
        params = LoopParams(getattr(status, 'value', status), conf.rounds, conf.target_min, conf.target_max)
        board = self.team_sync._board(self.config)
        result = self.loop_controller.request_start(params, board)
        logger.info(f'Loop start request: {result}')

    def _loop_postpone_deferred(self) -> bool:
        """组队任务只有两边都认为它严格更高才插入；对方不这么认为的，推迟一小段时间。"""
        names = self.loop_controller.pop_deferred()
        for name in names:
            logger.info(f'Loop: peer does not rank {name} above its step, postpone it')
            self.config.task_delay(task=name, target=datetime.now() + TEAM_YIELD_DELAY, server=False)
        return bool(names)

    def _loop_idle_poll(self) -> None:
        if self.config.start_mtime == DEFAULT_TIME:
            self.config.start_watching()
        self.loop_controller.tick()
        time.sleep(LOOP_POLL_INTERVAL)
        if self.config.should_reload():
            del_cached_property(self, 'config')

    def _loop_note_recovery(self) -> None:
        """异常处理里要安排 Restart 之前登记：恢复结束前循环不推进、不解除阻塞。"""
        try:
            if self.loop_controller.note_recovery(bool(self.config.model.restart.scheduler.enable)):
                # 这是异常请求的恢复，不是脚本刚启动时那个可以跳过的 Restart；否则首个任务的准备阶段
                # 出异常时 Restart 会被跳过，恢复永远结束不了
                self.is_first_task = False
        except Exception as e:
            logger.exception(f'Loop recovery note failed: {e}')

    def _request_restart_recovery(self) -> bool:
        """异常处理里请求 Restart 恢复：先登记循环恢复，再 `task_call('Restart')`，登记成功之后才改调度状态。

        「脚本启动时跳过首次 Restart」只针对启动时已经到点的例行 / 陈旧 Restart；本进程内由任务运行或准备阶段异常
        请求的恢复不是它。任务运行中的异常之后 `is_first_task` 本来就会在任务结束处被置 False；准备阶段（首个任务
        还没真正运行）出异常时没有这一步，请求登记后的下一轮调度会把它当成启动时的 Restart 跳过，这里补上。
        `task_call` 抛异常或没有登记（返回 False）时不改 `is_first_task`，不假装恢复已经安排。
        """
        self._loop_note_recovery()
        registered = self.config.task_call('Restart')
        if registered:
            self.is_first_task = False
        return bool(registered)

    def _loop_fail_before_exit(self, reason: str) -> None:
        """进程马上要退出：先把循环写成失败，对方不用等 60 秒才发现。"""
        try:
            self.loop_controller.fail(reason)
        except Exception as e:
            logger.warning(f'Loop fail note failed: {e}')

    def _prepare_step_fatigue(self, command: str) -> None:
        """循环步骤的疲劳检查要在会合之前做：先建立任务的疲劳上下文，再检查是否需要休息。"""
        self.fatigue_manager = get_fatigue_manager(self.config_name, self.config.global_game.fatigue)
        manager = self.fatigue_manager
        manager.begin_task(command, load_factor=manager.load_factor, restart=True)
        manager.begin_global_activity()
        try:
            manager.try_break(safe=True)
        finally:
            manager.end_global_activity()
        self._fatigue_prepared_for = command

    def _loop_should_yield(self, task: str) -> bool:
        """等对方期间，有严格更高优先级的任务到点了就让出：它会排在步骤前面。"""
        # 对方已经在某个组队任务门口等我、且这个任务按我的位次也严格高于步骤：把它改成现在，下面就会让出
        self.team_sync.answer(self.config)
        self.config.update_scheduler()
        pending = self.config.pending_task
        return bool(pending) and pending[0].command != task

    def _loop_step_prelude(self, task: str) -> str:
        """循环步骤的前置：疲劳检查 → 循环会合。返回 'go' 才继续进门口并运行；其余都回调度器。"""
        controller = self.loop_controller
        self._prepare_step_fatigue(task)
        if not controller.check(force=True):
            return 'stop'
        self.config.start_watching()
        waited_since, notified = time.monotonic(), False
        while True:
            verdict = controller.barrier()
            if verdict == 'go':
                return 'go' if controller.begin_run() else 'stop'
            if verdict == 'skip':
                controller.accept_skip()
                return 'skip'
            if verdict in ('failed', 'cancelled', 'idle'):
                return 'stop'
            time.sleep(LOOP_POLL_INTERVAL)
            # 等对方不设固定超时；等满一段时间推送一次提醒，但不放弃等待
            if not notified and time.monotonic() - waited_since >= TEAM_WAIT_NOTIFY.total_seconds():
                notified = True
                self._loop_notify(f'循环步骤 {task} 已等待对方 {int(TEAM_WAIT_NOTIFY.total_seconds() // 60)} 分钟，仍在继续等待')
            if self.config.should_reload():
                return 'reload'
            if self._loop_should_yield(task):
                logger.info(f'Loop step `{task}` yields to a higher priority task')
                return 'yield'

    def exception_handler(self, e: Exception, command: str) -> None:
        # 处理御魂溢出
        from tasks.Utils.post_diagnotor import PostDiagnotor, AnalyzeType
        image = getattr(self.device, 'image', None)
        # image为None则不做处理
        if image is None:
            return
        analyse_type = PostDiagnotor().handle(e=e, command=command, image=image)
        if analyse_type == AnalyzeType.SoulOverflow:
            self.config.task_call('SoulsTidy')
            time.sleep(1)

    def _reset_task_runtime_outcome(self) -> None:
        self.last_task_runtime_outcome = None
        if 'config' in self.__dict__:
            self.config.task_runtime_outcome = None

    def _set_task_runtime_outcome(self, task: str, status: str, wait_until: datetime | None = None) -> None:
        outcome = {
            'task': task,
            'status': status,
        }
        if wait_until is not None:
            outcome['wait_until'] = wait_until
        self.last_task_runtime_outcome = outcome
        if 'config' in self.__dict__:
            self.config.task_runtime_outcome = outcome

    def _capture_task_runtime_outcome(self, command: str) -> None:
        outcome = getattr(self.config, 'task_runtime_outcome', None)
        self.last_task_runtime_outcome = outcome if isinstance(outcome, dict) else None
        if self.last_task_runtime_outcome is None:
            return
        status = self.last_task_runtime_outcome.get('status')
        if status == 'server_update_delayed':
            wait_until = self.last_task_runtime_outcome.get('wait_until')
            logger.info(f'{command} runtime outcome: server_update_delayed (wait_until={wait_until})')
            if isinstance(wait_until, datetime):
                self.runtime.server_update_wait_until = wait_until
                self.runtime.server_update_wait_log_until = None
            return
        if command != 'Restart':
            return
        if status == 'recovered':
            logger.info('Restart runtime outcome: recovered')
            return
        logger.info(f'Restart runtime outcome: {status}')

    def _delay_tasks_for_server_update(self, task: str, reason: str) -> bool:
        if not is_server_update_window():
            return False

        delay_target = delay_pending_tasks_for_server_update(self.config, reason=reason)
        self._set_task_runtime_outcome(task=task, status='server_update_delayed', wait_until=delay_target)
        return True

    def run(self, command: str) -> bool:
        """
        :param command:  大写驼峰命名的任务名字
        :return:
        """
        if command == 'start' or command == 'goto_main':
            logger.error(f'Invalid command `{command}`')

        self._reset_task_runtime_outcome()
        set_ocr_logging_enabled(self.config.global_game.ocr.save_ocr_log)
        self.fatigue_manager = get_fatigue_manager(
            self.config_name, self.config.global_game.fatigue
        )
        self._run_ended = False
        self.config.__dict__['last_task_delay'] = {}
        # 任务内的业务等待（福利道馆主动离线）从防沉迷活跃时长里扣除，见 `_active_seconds_today`
        self.config.__dict__['excluded_active_seconds'] = 0.0
        # 循环步骤已经在会合前按这个任务建立过疲劳上下文并检查过，不重复初始化
        prepared = self._fatigue_prepared_for == command
        self._fatigue_prepared_for = None
        if not prepared:
            previous_fatigue_task = self.fatigue_manager.task_identity
            switched = self.fatigue_manager.begin_task(
                command,
                load_factor=self.fatigue_manager.load_factor,
                restart=True,
            )
            if switched and self.fatigue_manager.enabled:
                snapshot = self.fatigue_manager.snapshot()
                logger.info(
                    f'疲劳任务切换：{previous_fatigue_task or "无"} -> {command}，'
                    f'当前任务疲劳：{snapshot.task:.1f}，总疲劳：{snapshot.global_:.1f}'
                )
        self.fatigue_manager.begin_global_activity()
        # 观测：记录一次任务 episode 的耗时与结果，不改变任何异常传播路径
        trace = get_behavior_trace(self.config_name)
        trace.set_task(command)
        trace_started_at = time.perf_counter()
        trace_result = 'fail'
        try:
            self.device.screenshot()
            module_name = 'script_task'
            module_path = str(Path.cwd() / 'tasks' / command / (module_name + '.py'))
            logger.info(f'module_path: {module_path}, module_name: {module_name}')
            task_module = load_module(module_name, module_path)
            task_module.ScriptTask(config=self.config, device=self.device).run()
            trace_result = 'ok'
        except Exception as e:
            outcome = self._handle_task_exception(e, command)
            trace_result = 'ok' if outcome else 'fail'
            return outcome
        finally:
            trace.record(
                'TASK', action='run', target=command, result=trace_result,
                elapsed_ms=round((time.perf_counter() - trace_started_at) * 1000),
            )
            trace.set_task('')
            self.fatigue_manager.end_global_activity()
        return False

    def loop(self):
        """
        Main loop of scheduler.
        :return:
        """
        with _log_switch_lock:
            logger.set_file_logger(self.config_name, do_cleanup=True)
        start_day = date.today()
        logger.info(f'Start scheduler loop: {self.config_name}')
        self.config.model.running_task = ''
        self._active_seconds_today = 0
        self._active_date = date.today()
        self._rest_until = None
        self.team_sync.start_heartbeat()

        # Update GUI 防呆, 读取设置并立刻显示后台模拟器到前台
        if not self.config.script.device.run_background_only and IS_WINDOWS:
            from module.device.platform2.platform_windows import minimize_by_name, show_window_by_name
            target_window_name = self.config.script.device.handle  # 在这里输入你的具体窗口名称
            if self.config.script.device.emulator_window_minimize:
                minimize_by_name(target_window_name)
                logger.info(f'重新显示: {target_window_name}')
            else:
                show_window_by_name(target_window_name)
                
        while 1:
            if date.today() > start_day:
                with _log_switch_lock:
                    logger.set_file_logger(self.config_name, do_cleanup=True)
                start_day = date.today()

            task = ""
            loop_step = False
            self._fatigue_prepared_for = None
            try:
                # Get task
                task = self.get_next_task()
                # Skip first restart
                if self.is_first_task and task == 'Restart':
                    logger.info('Skip task `Restart` at scheduler start')
                    self.config.task_delay(task='Restart', success=True, server=True)
                    del_cached_property(self, 'config')
                    continue
                loop_step = self.loop_controller.is_step(task)
                # 组队任务的对方确定不会来时，在唤醒模拟器 / 游戏之前就推迟（循环步骤的等待由循环会合负责）
                team = None if loop_step else self.team_sync.precheck(self.config, task)
                if team is not None:
                    self._postpone_team_task(task, team)
                    continue
                decision = self.runtime.prepare_task_execution(task)
            except Exception as e:
                self._handle_task_exception(e, task)
                # 本轮 prepare 失败,重新调度
                del_cached_property(self, 'config')
                continue

            if decision == ScriptRuntimeDecision.RESCHEDULE:
                logger.info(f'Runtime preparation for `{task}` requested reschedule, reload config and retry scheduling')
                del_cached_property(self, 'config')
                continue
            if decision == ScriptRuntimeDecision.FAILED:
                logger.warning(f'Runtime preparation for `{task}` failed, reload config and retry scheduling')
                del_cached_property(self, 'config')
                continue

            if loop_step:
                verdict = self._loop_step_prelude(task)
                if verdict != 'go':
                    # 让出 / 重载 / 停止：撤回已发布的就绪，对端不能再凭旧的 ready 放行
                    self.loop_controller.withdraw_ready()
                    self._fatigue_prepared_for = None
                    del_cached_property(self, 'config')
                    continue

            # 组队任务先和对方实例会合；推迟或配置变了就回去重新调度
            self.config.start_watching()
            team = self.team_sync.gate(self.config, task, should_abort=self.config.should_reload,
                                       loop=self.loop_controller.loop_door() if loop_step else None)
            if team.action == TEAM_POSTPONE:
                if loop_step:
                    self._loop_gate_postponed(team)
                    continue
                self._postpone_team_task(task, team)
                continue
            if team.action != TEAM_GO:
                if loop_step:
                    self.loop_controller.abandon_run()
                self._fatigue_prepared_for = None
                del_cached_property(self, 'config')
                continue

            # Run
            logger.info(f'Scheduler: Start task `{task}`')
            self.device.stuck_record_clear()
            self.device.click_record_clear()
            logger.hr(task, level=0)
            self.config.model.running_task = task
            _task_start = datetime.now()
            try:
                success = self.run(inflection.camelize(task))
            finally:
                self.team_sync.end_task()
            self.config.model.running_task = ''
            self._loop_after_run(task)
            logger.info(f'Scheduler: End task `{task}`')
            self.is_first_task = False
            self._add_active_seconds(_task_start)

            # Check failures
            # failed = deep_get(self.failure_record, keys=task, default=0)
            failed = self.failure_record[task] if task in self.failure_record else 0
            failed = 0 if success else failed + 1
            # deep_set(self.failure_record, keys=task, value=failed)
            self.failure_record[task] = failed
            if failed >= 3:
                logger.critical(f"Task `{task}` failed 3 or more times.")
                logger.critical("Possible reason #1: You haven't used it correctly. "
                                "Please read the help text of the options.")
                logger.critical("Possible reason #2: There is a problem with this task. "
                                "Please contact developers or try to fix it yourself.")
                logger.critical('Request human takeover')
                # 添加失败三次的推送通知
                self._loop_fail_before_exit('process_exit')
                self.config.notifier.push(
                    title=f'{I18n.trans_zh_cn(task)}{task}',
                    content=f"<{self.config_name}> 任务连续失败三次，请上线查看"
                )
                # 关闭模拟器
                if self.config.script.error.error_repeated:
                    self.device.emulator_stop()
                exit(1)

            if success:
                del_cached_property(self, 'config')
                continue
            elif self.config.script.error.handle_error:
                # self.config.task_delay(success=False)
                del_cached_property(self, 'config')
                # self.checker.check_now()
                continue
            else:
                break

    def _add_active_seconds(self, task_start: datetime) -> None:
        """把本次任务的墙钟时长累计进防沉迷的当日活跃时长；任务内的业务等待（福利道馆主动离线）扣除。"""
        if self._active_date != date.today():
            self._active_date = date.today()
            self._active_seconds_today = 0
        excluded = float(self.config.__dict__.pop('excluded_active_seconds', 0.0) or 0.0)
        self._active_seconds_today += max(0.0, (datetime.now() - task_start).total_seconds() - excluded)

    def _loop_gate_postponed(self, team) -> None:
        """循环步骤在门口被判推迟：配置类原因停止循环，其余是暂时的，稍后重新走会合。"""
        controller = self.loop_controller
        controller.abandon_run()
        self._fatigue_prepared_for = None
        if team.reason in LOOP_CONFIG_REASONS:
            controller.fail(f'config_mismatch:{team.reason}')
        else:
            time.sleep(LOOP_POLL_INTERVAL * 5)
        del_cached_property(self, 'config')

    def _loop_after_run(self, task: str) -> None:
        """任务跑完：把「是否正常走到结束出口」「任务自己报告的成功」「Restart 恢复结果」交给循环控制器。"""
        try:
            outcome = self.last_task_runtime_outcome or {}
            delay = self.config.__dict__.get('last_task_delay', {})
            self.loop_controller.after_run(
                task, ended=self._run_ended,
                delay_success=delay.get(convert_to_underscore(task)),
                restart_status=outcome.get('status'),
            )
        except Exception as e:
            logger.exception(f'Loop after-run settle failed: {e}')
            self._loop_fail_before_exit('settle_error')

    def _postpone_team_task(self, task: str, team) -> None:
        # server=False：否则服务器刷新时间不是 9 点的任务会被改到明天那个点，覆盖推迟目标
        self.config.task_delay(task=task, target=team.until, server=False)
        message = self.team_sync.notice(task, team)
        if message:
            self.config.notifier.push(title=f'{I18n.trans_zh_cn(task)}{task}',
                                      content=f'<{self.config_name}> {message}')
        del_cached_property(self, 'config')

    def _handle_task_exception(self, e: Exception, command: str) -> bool:
        """
        统一处理任务执行 / 准备阶段抛出的异常。
        Returns:
            True  -> 视为正常结束或已自动恢复 (例如已 task_call('Restart')),
                     调度器继续推进
            False -> 视为失败,脚本继续运行
        对致命异常 (ScriptError / RequestHumanTakeover / 未识别 Exception)
        在内部直接 exit(1)。
        """
        if isinstance(e, TaskEnd):
            self._run_ended = True
            self._capture_task_runtime_outcome(command)
            return True

        if isinstance(e, GameNotRunningError):
            logger.warning(e)
            self.exception_handler(e=e, command=command)
            self._request_restart_recovery()
            return True

        if isinstance(e, (GameStuckError, GameTooManyClickError)):
            logger.error(e)
            self.save_error_log()
            self.exception_handler(e=e, command=command)
            logger.warning(f'Game stuck, {self.device.package} will be restarted in 10 seconds')
            logger.warning('If you are playing by hand, please stop Alas')
            self.config.notifier.push(title=f'{I18n.trans_zh_cn(command)}{command}',
                                      content=f"<{self.config_name}> GameStuckError or GameTooManyClickError")
            self._request_restart_recovery()
            self.device.sleep(10)
            return False

        if isinstance(e, GameBugError):
            logger.warning(e)
            self.save_error_log()
            self.exception_handler(e=e, command=command)
            logger.warning('An error has occurred in Azur Lane game client, Alas is unable to handle')
            logger.warning(f'Restarting {self.device.package} to fix it')
            self._request_restart_recovery()
            self.device.sleep(10)
            return False

        if isinstance(e, GamePageUnknownError):
            logger.info('Game server may be under maintenance or network may be broken, check server status now')
            if command == 'GotoMain' and self._delay_tasks_for_server_update(
                    task=command,
                    reason='failed to goto main during morning server update window',
            ):
                logger.info('GotoMain failed during server update window, delayed pending tasks and reschedule')
                return False
            logger.critical('Game page unknown')
            self.save_error_log()
            self.exception_handler(e=e, command=command)
            self.config.notifier.push(
                title=f'{I18n.trans_zh_cn(command)}{command}',
                content=f"<{self.config_name}> GamePageUnknownError",
            )
            self._request_restart_recovery()
            self.device.sleep(10)
            return False

        if isinstance(e, ScriptError):
            logger.critical(e)
            self.exception_handler(e=e, command=command)
            logger.critical('This is likely to be a mistake of developers, but sometimes just random issues')
            self._loop_fail_before_exit('process_exit')
            self.config.notifier.push(
                title=f'{I18n.trans_zh_cn(command)}{command}',
                content=f"<{self.config_name}> ScriptError",
            )
            exit(1)

        if isinstance(e, RequestHumanTakeover):
            logger.critical(e)
            self.exception_handler(e=e, command=command)
            logger.critical('Request human takeover')
            self._loop_fail_before_exit('process_exit')
            self.config.notifier.push(
                title=f'{I18n.trans_zh_cn(command)}{command}',
                content=f"<{self.config_name}> RequestHumanTakeover",
            )
            exit(1)

        # generic
        logger.exception(e)
        self._loop_fail_before_exit('process_exit')
        self.exception_handler(e=e, command=command)
        self.save_error_log()
        self.config.notifier.push(
            title=f'{I18n.trans_zh_cn(command)}{command}',
            content=f"<{self.config_name}> Exception occured",
        )
        exit(1)
        return False

    def start_loop(self) -> None:
        """
        创建一个线程，运行loop
        :return:
        """
        if self.loop_thread is None:
            self.loop_thread = Thread(target=self.loop, name='Script_loop')
            self.loop_thread.start()


if __name__ == "__main__":
    ensure_image_server_ready()
    ensure_ocr_server_ready()
    script = Script("oas1")
    script.loop()
