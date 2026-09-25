import time
from functools import partial

# from module.base.button import Button
from module.base.decorator import cached_property
from module.base.timer import Timer
from module.base.utils import *
from module.device.env import IS_WINDOWS
# from module.device.method.hermit import Hermit
# from module.device.method.maatouch import MaaTouch
from module.device.method.minitouch import Minitouch
from module.device.method.adb import Adb
from module.device.method.scrcpy import Scrcpy
from module.device.method.windows import Window
from module.behavior_trace import get_behavior_trace
from module.logger import logger


def _swipe_trajectory_extra(trajectory) -> dict:
    """把本次交给 executor 的 commanded 轨迹整理进 BehaviorTrace ACTION 的 extra。

    数据源就是传给 `Control.swipe_trajectory` 的这一份点列（executor 的真实输入）——
    不按 start/end 重新生成、不还原曲线。每个点保留 ``[x, y, dt_ms]``（dt 语义见 D018，
    本层不重新解释）。一次 swipe 仍只对应一个 ACTION，轨迹点整体塞进 extra，绝不逐点写事件。
    """
    pts = [[int(round(p[0])), int(round(p[1])), int(round(p[2]))] for p in trajectory]
    first = pts[0] if pts else [None, None, None]
    last = pts[-1] if pts else [None, None, None]
    return {
        'start_x': first[0], 'start_y': first[1],
        'end_x': last[0], 'end_y': last[1],
        'point_count': len(pts),
        'trajectory': pts,
    }


class Control(Minitouch, Adb, Scrcpy, Window):
    def handle_control_check(self, button):
        # Will be overridden in Device
        pass

    @staticmethod
    def _format_action_duration(duration_seconds: float) -> str:
        return f'[{duration_seconds:.2f}s] '

    def _invalidate_image_batch_cache(self) -> None:
        invalidate = getattr(self, 'invalidate_image_batch_cache', None)
        if callable(invalidate):
            invalidate()

    @cached_property
    def click_methods(self):
        methods = {
            'ADB': self.click_adb,
            'uiautomator2': self.click_uiautomator2,
            'minitouch': self.click_minitouch,
            # 'Hermit': self.click_hermit,
            # 'MaaTouch': self.click_maatouch,
        }
        if IS_WINDOWS:
            methods['window_message'] = self.click_window_message
        return methods

    @cached_property
    def long_click_methods(self):
        methods = {
            'ADB': self.long_click_adb,
            'uiautomator2': self.long_click_uiautomator2,
            'minitouch': self.long_click_minitouch,
            'scrcpy': self.long_click_scrcpy
            # 'Hermit': self.click_hermit,
            # 'MaaTouch': self.click_maatouch,
        }
        if IS_WINDOWS:
            methods['window_message'] = self.long_click_window_message
        return methods

    @cached_property
    def click_backend_methods(self):
        """`click_with_backend` 可显式指定的单击后端（百鬼夜行撒豆这类高频小游戏）。

        window_message 保留原高速路径的 `fast=True`（10~40ms 按压），minitouch 与普通点击同一实现；
        不按 IS_WINDOWS 裁剪，与原业务直调时一致。
        """
        return {
            'minitouch': self.click_minitouch,
            'window_message': partial(self.click_window_message, fast=True),
        }

    def click(self, x: int, y: int, control_check=True, control_name='Click') -> None:
        """

        :param control_name:
        :param x:
        :param y:
        :param control_check:
        :return:
        """
        if control_check:
            self.handle_control_check(control_name)
        method = self.click_methods.get(
            self.config.script.device.control_method,
            self.click_adb
        )
        self._dispatch_click(method, x, y, control_name)

    def click_with_backend(self, x: int, y: int, backend, control_name='Click') -> None:
        """用显式指定的后端执行一次单击，不读 control_method 配置。

        不做 control_check：原高速路径从不进 click_record，高频撒豆若计数会误触发
        GameTooManyClickError。坐标取整 / 日志 / BehaviorTrace 与 `click` 共用同一段实现。
        """
        key = getattr(backend, 'value', backend)
        method = self.click_backend_methods.get(key)
        if method is None:
            raise ValueError(f'未知的单击后端：{backend!r}')
        self._dispatch_click(method, x, y, control_name)

    def _dispatch_click(self, method, x, y, control_name) -> None:
        x, y = ensure_int(x, y)
        self._invalidate_image_batch_cache()
        start = time.perf_counter()
        method(x, y)
        elapsed = time.perf_counter() - start
        logger.info(f'{self._format_action_duration(elapsed)}Click {point2str(x, y)} @ {control_name}')
        # 观测：动作已正常返回后记录，复用现成 elapsed，不新增计时、不改控制流。
        # x / y 为实际提交给控制后端执行的最终坐标（已 ensure_int），供点击分布统计使用。
        get_behavior_trace(self.config.config_name).record(
            'ACTION', action='click', target=control_name,
            elapsed_ms=round(elapsed * 1000), extra={'x': x, 'y': y})


    def multi_click(self, button, n, interval=(0.1, 0.2)):
        """
        也是不能用button的逻辑
        :param button:
        :param n:
        :param interval:
        :return:
        """
        self.handle_control_check(button)
        click_timer = Timer(0.1)
        for _ in range(n):
            remain = ensure_time(interval) - click_timer.current()
            if remain > 0:
                self.sleep(remain)
            click_timer.reset()

            self.click(button, control_check=False)

    def long_click(self, x: int, y: int, duration=(0.5, 2), control_name='LongClick') -> None:
        """

        :param control_name:
        :param x:
        :param y:
        :param duration: 单位是s
        :return:
        """
        self.handle_control_check(control_name)
        x, y = ensure_int(x, y)
        if duration is None:
            duration = 0.8
        duration = ensure_time(duration)
        self._invalidate_image_batch_cache()
        method = self.long_click_methods.get(
            self.config.script.device.control_method,
            self.long_click_adb)
        start = time.perf_counter()
        method(x, y, duration)
        elapsed = time.perf_counter() - start
        logger.info(f'{self._format_action_duration(elapsed)}Click {point2str(x, y)} @ {control_name} {duration}')
        # 观测：动作已正常返回后记录，复用现成 elapsed；x / y 为最终执行坐标。
        get_behavior_trace(self.config.config_name).record(
            'ACTION', action='long_click', target=control_name,
            elapsed_ms=round(elapsed * 1000), extra={'x': x, 'y': y})

    def swipe(self, p1, p2, duration=(0.1, 0.2), control_name='SWIPE', distance_check=True):
        """执行一次滑动。

        duration 只对会消费该参数的控制后端生效：当前仅 uiautomator2 与 adb 使用它，
        minitouch / scrcpy / window_message 均忽略 duration（滑动时序由各自实现内部决定）。
        因此在 minitouch 环境下给 duration 传随机值不会改变实际滑动速度。
        """
        self.handle_control_check(control_name)
        p1, p2 = ensure_int(p1, p2)
        duration = ensure_time(duration)
        method = self.config.script.device.control_method
        swipe_log = None
        if method == 'minitouch':
            swipe_log = 'Swipe %s -> %s' % (point2str(*p1), point2str(*p2))
        elif method == 'window_message':
            swipe_log = 'Swipe %s -> %s' % (point2str(*p1), point2str(*p2))
        elif method == 'uiautomator2':
            swipe_log = 'Swipe %s -> %s, %s' % (point2str(*p1), point2str(*p2), duration)
        elif method == 'scrcpy':
            swipe_log = 'Swipe %s -> %s' % (point2str(*p1), point2str(*p2))
        # elif method == 'MaaTouch':
        #     logger.info('Swipe %s -> %s' % (point2str(*p1), point2str(*p2)))
        else:
            # ADB needs to be slow, or swipe doesn't work
            duration *= 2.5
            swipe_log = 'Swipe %s -> %s, %s ' % (point2str(*p1), point2str(*p2), duration)

        if distance_check:
            if p1[0] == p2[0]:
                logger.info('Swipe x distance is 0')
                p1[0] += 1
            if p1[1] == p2[1]:
                logger.info('Swipe y distance is 0')
                p1[1] += 1

            if np.linalg.norm(np.subtract(p1, p2)) < 10:
                # Should swipe a certain distance, otherwise AL will treat it as click.
                # uiautomator2 should >= 6px, minitouch should >= 5px
                logger.info('Swipe distance < 10px, dropped')
                return

        self._invalidate_image_batch_cache()
        start = time.perf_counter()
        if method == 'minitouch':
            self.swipe_minitouch(p1, p2)
        elif method == 'window_message':
            self.swipe_window_message(p1, p2)
        elif method == 'uiautomator2':
            self.swipe_uiautomator2(p1, p2, duration=duration)
        elif method == 'scrcpy':
            self.swipe_scrcpy(p1, p2)
        # elif method == 'MaaTouch':
        #     self.swipe_maatouch(p1, p2)
        else:
            self.swipe_adb(p1, p2, duration=duration)
        elapsed = time.perf_counter() - start
        logger.info(f'{self._format_action_duration(elapsed)}{swipe_log}')
        # 观测：动作已正常返回后记录，复用现成 elapsed。注意直接调用 swipe_adb 的路径
        # （KekkaiUtilize / KekkaiActivation 好友列表滑动）绕过本方法，v1 不覆盖。
        # legacy 端点滑动只知道 p1/p2 —— extra 只带端点，**不带 trajectory 键**（避免下游
        # 误以为执行过某条曲线）。完整轨迹见 swipe_trajectory。
        get_behavior_trace(self.config.config_name).record(
            'ACTION', action='swipe', target=control_name, elapsed_ms=round(elapsed * 1000),
            extra={'start_x': p1[0], 'start_y': p1[1], 'end_x': p2[0], 'end_y': p2[1],
                   'point_count': 2})

    def swipe_trajectory(self, trajectory, control_name='SWIPE'):
        """按调用方提供的自定义轨迹执行一次滑动（显式 opt-in，当前仅 minitouch 后端）。

        与 `Control.swipe` 的区别：路径点与逐段时间（``[(x, y, dt_ms), ...]``）由调用方
        （`module/device/touch_swipe_model.TouchSwipeModel`）给定，本方法不做 duration /
        distance_check / vector 合成，也不改 `Control.swipe` 的任何行为。

        非 minitouch 后端本方法不支持，直接 `raise NotImplementedError`——不静默用首尾点
        退化成普通端点滑动，以免自定义轨迹语义被悄悄丢掉。轨迹结构校验由
        `Minitouch.swipe_minitouch_trajectory` → `_ensure_trajectory` 负责（非法输入抛
        `ValueError`）。
        """
        self.handle_control_check(control_name)
        method = self.config.script.device.control_method
        if method != 'minitouch':
            raise NotImplementedError(
                f'swipe_trajectory 当前仅支持 minitouch 后端，当前控制后端：{method}')

        try:
            trajectory = list(trajectory)
        except TypeError:
            raise ValueError(f'轨迹必须是可迭代的点序列：{trajectory!r}')

        self._invalidate_image_batch_cache()
        start = time.perf_counter()
        self.swipe_minitouch_trajectory(trajectory)
        elapsed = time.perf_counter() - start
        logger.info(
            f'{self._format_action_duration(elapsed)}'
            f'SwipeTrajectory {len(trajectory)} pts @ {control_name}')
        # 观测：一次 swipe = 一个 ACTION（action='swipe'），完整 commanded 轨迹整体进 extra，
        # 绝不逐 MOVE 写事件。extra 仅在真的会落盘时组装，关闭态不白拷贝几十个点。
        trace = get_behavior_trace(self.config.config_name)
        extra = _swipe_trajectory_extra(trajectory) if trace.is_recording() else None
        trace.record(
            'ACTION', action='swipe', target=control_name,
            elapsed_ms=round(elapsed * 1000), extra=extra)

    def swipe_vector(self, vector, box=(123, 159, 1175, 628), random_range=(0, 0, 0, 0), padding=15,
                     duration=(0.1, 0.2), whitelist_area=None, blacklist_area=None, name='SWIPE', distance_check=True):
        """Method to swipe.

        Args:
            box (tuple): Swipe in box (upper_left_x, upper_left_y, bottom_right_x, bottom_right_y).
            vector (tuple): (x, y).
            random_range (tuple): (x_min, y_min, x_max, y_max).
            padding (int):
            duration (int, float, tuple):
            whitelist_area: (list[tuple[int]]):
                A list of area that safe to click. Swipe path will end there.
            blacklist_area: (list[tuple[int]]):
                If none of the whitelist_area satisfies current vector, blacklist_area will be used.
                Delete random path that ends in any blacklist_area.
            name (str): Swipe name
            distance_check: (bool):
        """
        p1, p2 = random_rectangle_vector_opted(
            vector,
            box=box,
            random_range=random_range,
            padding=padding,
            whitelist_area=whitelist_area,
            blacklist_area=blacklist_area
        )
        self.swipe(p1, p2, duration=duration, control_name=name, distance_check=distance_check)

    def drag(self, p1, p2, segments=1, shake=(0, 15), point_random=(-10, -10, 10, 10), shake_random=(-5, -5, 5, 5),
             swipe_duration=0.25, shake_duration=0.1, name='DRAG'):
        self.handle_control_check(name)
        p1, p2 = ensure_int(p1, p2)
        drag_log = 'Drag %s -> %s' % (point2str(*p1), point2str(*p2))
        method = self.config.script.emulator.control_method
        start = time.perf_counter()
        if method == 'minitouch':
            self.drag_minitouch(p1, p2, point_random=point_random)
        elif method == 'uiautomator2':
            self.drag_uiautomator2(
                p1, p2, segments=segments, shake=shake, point_random=point_random, shake_random=shake_random,
                swipe_duration=swipe_duration, shake_duration=shake_duration)
        elif method == 'scrcpy':
            self.drag_scrcpy(p1, p2, point_random=point_random)
        # elif method == 'MaaTouch':
        #     self.drag_maatouch(p1, p2, point_random=point_random)
        else:
            logger.warning(f'Control method {method} does not support drag well, '
                           f'falling back to ADB swipe may cause unexpected behaviour')
            self.swipe_adb(p1, p2, duration=ensure_time(swipe_duration * 2))
            # self.click(Button(area=(), color=(), button=area_offset(point_random, p2), name=name))
        elapsed = time.perf_counter() - start
        logger.info(f'{self._format_action_duration(elapsed)}{drag_log}')
