from __future__ import annotations

from collections.abc import Callable
import time

from module.exception import ScriptError, OcrUnavailableError
from tasks.Component.Login.service import LoginService
from tasks.Restart.script_task import ScriptTask as RestartTask


def wait_for_ocr_recovery(*, deadline, check):
    """只等待后端托管的 OCR 恢复，不在账号内启动服务或独自重放业务。"""
    import zerorpc
    from zerorpc.exceptions import LostRemote, RemoteError, TimeoutExpired
    from module.server.setting import State
    from module.ocr.rpc import get_ocr_client
    from inspect import Parameter, signature

    address = State.deploy_config.OcrClientAddress or '127.0.0.1:22268'
    if not address.startswith('tcp://'):
        address = 'tcp://' + address
    last_error = None
    parameters = signature(get_ocr_client).parameters
    bounded_proxy = 'deadline' in parameters or any(
        item.kind == Parameter.VAR_KEYWORD for item in parameters.values()
    )
    proxy = None
    while time.monotonic() < deadline:
        check()
        client = None
        try:
            if bounded_proxy:
                # 新代理复用同一连接，保持原有整轮期限和断线按需重连语义。
                if proxy is None:
                    proxy = get_ocr_client(refresh=True, deadline=min(deadline, time.monotonic()+2))
                info = proxy._request('get_server_info', _deadline=min(deadline, time.monotonic()+2))
            else:
                # 旧代理不支持整轮期限，用独立短健康请求避免依赖未提交接口。
                client = zerorpc.Client(timeout=min(2, max(.001, deadline-time.monotonic())))
                client.connect(address)
                info = client.get_server_info()
            check()
            ready = isinstance(info, dict) and (
                info.get('warmup_complete') is True if 'warmup_complete' in info
                else info.get('loaded_worker_count', 0) > 0
            )
            if ready and time.monotonic() < deadline:
                return
        except (OcrUnavailableError, LostRemote, RemoteError, TimeoutExpired) as exc:
            last_error = exc
        finally:
            if client is not None:
                client.close()
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(.25, remaining))
    raise OcrUnavailableError('整组恢复等待 OCR 就绪超时，停止本组') from last_error



class TeamStallError(ScriptError):
    """可交给当前觉醒组自动恢复的房间或战后等待故障。"""


class GroupGameRestart(RestartTask):
    """复用强制游戏重启，不运行每日任务或修改 Restart 调度。"""

    def __init__(self, config, device, check: Callable[[], None]):
        self._recovery_check = check
        super().__init__(config, device)

    def app_restart(self):
        self._recovery_check()
        super().app_restart()
        self._recovery_check()

    def app_start(self):
        self._recovery_check()
        self.device.app_start()
        self.device.wait_app_start_ready()
        self._recovery_check()
        login = LoginService(config=self.config, device=self.device)
        screenshot = login.screenshot

        def checked_screenshot():
            self._recovery_check()
            result = screenshot()
            self._recovery_check()
            return result

        # 登录循环也响应队友失败，避免恢复阶段又形成不受控的内层等待。
        login.screenshot = checked_screenshot
        login.app_handle_login()
        self._recovery_check()
