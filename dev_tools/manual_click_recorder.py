# This Python file uses the following encoding: utf-8
"""人工点击采样器 v1（ManualClickRecorder）。

用途：OAS + 某个 MuMu 实例已经启动后，用户用**物理鼠标**操作该 MuMu，本工具被动
监听目标 MuMu 游戏画面内的人工左键点击，把 Windows 屏幕坐标换算成 OAS 的 1280×720
逻辑坐标，写入独立 JSONL（``log/manual_click/<config>_<日期>.jsonl``），供后续统计
用户真实的 preferred center / spread。

硬约束：
- **只监听、绝不发送任何输入**：不点击、不移动鼠标、不发键盘，不碰 Control / minitouch /
  adb / uiautomator2。鼠标钩子回调只读取事件并始终 ``CallNextHookEx`` 放行。
- 人工样本与自动 BehaviorTrace（``log/behavior/``）**分开存**，两类原始事件不混。
- 不启动 MuMu / 游戏 / OAS / OCR，不抢焦点，不移动 / 缩放目标窗口。
- Windows only。

坐标体系：本进程不设置任何 DPI awareness（与 OAS 一致，默认 DPI-unaware）。鼠标钩子
的 ``MSLLHOOKSTRUCT.pt`` 与 ``GetWindowRect`` 处于同一套（虚拟化）坐标空间，换算是纯
比例（``client / window * 1280``），因此**不需要也不应该**再乘 ``window_scale_rate``；
该值只作诊断展示 / 存档。视口窗口取 OAS 自己截图用的那个句柄（MuMu 的游戏画面 child
窗口，见 ``module/device/handle.py`` 的 ``screenshot_handle_num``）。

运行：``toolkit/python.exe dev_tools/manual_click_recorder.py --config oas1``
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from datetime import date, datetime
from pathlib import Path

# 允许 `toolkit/python.exe dev_tools/manual_click_recorder.py` 直接运行时也能 import 项目包。
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# OAS 逻辑分辨率（module/device/screenshot.py check_screen_size 强制）。
LOGICAL_WIDTH = 1280
LOGICAL_HEIGHT = 720

# 低级鼠标钩子事件标志位。
LLMHF_INJECTED = 0x00000001
LLMHF_LOWER_IL_INJECTED = 0x00000002

# 人工样本输出根目录，按 <项目根>/log/manual_click 定位（不依赖 cwd）。测试会替换此值。
MANUAL_CLICK_LOG_ROOT = Path(__file__).resolve().parents[1] / "log" / "manual_click"

# MuMu 顶层窗口标题关键字 / 游戏画面 child 窗口名——对齐 module/device/handle.py：
# 顶层用 Handle.emulator_list 里的 MuMu 项；游戏 child 用 Handle.emulator_family /
# screenshot_handle_num 判定的 'MuMuPlayer'(MuMu12) / 'NemuPlayer'(MuMu6) / 'MuMuNxDevice'(MuMu5.0)。
_MUMU_TITLE_KEYS = ("MuMu", "NemuPlayer")
_MUMU_GAME_CHILD_NAMES = ("MuMuPlayer", "NemuPlayer", "MuMuNxDevice")


# --------------------------------------------------------------------------------------
# 纯函数部分（无 Win32 依赖，单元测试直接覆盖）
# --------------------------------------------------------------------------------------

def resolve_config_name(name: str) -> str:
    """用项目统一的 ``ConfigManager.validate_config_name`` 校验并**原样返回**完整
    config_name（保留 ``_``，不按 ``_`` 截断，避免 ``account_group_1`` 被截成 ``account``）。
    """
    from module.server.config_manager import ConfigManager

    return ConfigManager.validate_config_name(name, allow_template=False)


def parse_roi(text: str) -> tuple[int, int, int, int]:
    """解析 CLI 传入的 ``x,y,w,h``（与项目 Rule ROI 一致，**不是** x1,y1,x2,y2）。"""
    parts = [p.strip() for p in str(text).split(",")]
    if len(parts) != 4:
        raise ValueError(f"ROI 需要 4 个逗号分隔的整数 x,y,w,h：{text!r}")
    try:
        x, y, w, h = (int(p) for p in parts)
    except ValueError:
        raise ValueError(f"ROI 必须是整数 x,y,w,h：{text!r}")
    if w <= 0 or h <= 0:
        raise ValueError(f"ROI 宽高必须为正：w={w}, h={h}")
    if x < 0 or y < 0:
        raise ValueError(f"ROI 左上角不能为负：x={x}, y={y}")
    if x + w > LOGICAL_WIDTH or y + h > LOGICAL_HEIGHT:
        raise ValueError(
            f"ROI 超出 {LOGICAL_WIDTH}x{LOGICAL_HEIGHT} 逻辑空间：(x={x}, y={y}, w={w}, h={h})"
        )
    return (x, y, w, h)


def screen_to_logical(
    screen_x: float,
    screen_y: float,
    win_rect: tuple[int, int, int, int],
    logical_w: int = LOGICAL_WIDTH,
    logical_h: int = LOGICAL_HEIGHT,
) -> tuple[int, int, float, float, bool]:
    """屏幕坐标 → 视口客户坐标 → OAS 逻辑坐标。

    Args:
        screen_x / screen_y: 鼠标屏幕坐标（与 ``win_rect`` 同一虚拟化空间）。
        win_rect: 视口窗口 ``GetWindowRect`` 结果 ``(left, top, right, bottom)``。
    Returns:
        ``(client_x, client_y, logical_x, logical_y, inside_viewport)``。
        逻辑坐标为 ``float``（调用方按需 round）；不做任何 clamp。
    """
    left, top, right, bottom = win_rect
    win_w = right - left
    win_h = bottom - top
    if win_w <= 0 or win_h <= 0:
        raise ValueError(f"视口窗口尺寸非法：{win_rect}")
    client_x = screen_x - left
    client_y = screen_y - top
    inside = (0 <= client_x < win_w) and (0 <= client_y < win_h)
    logical_x = client_x / win_w * logical_w
    logical_y = client_y / win_h * logical_h
    return client_x, client_y, logical_x, logical_y, inside


def relative_uv(
    logical_x: float, logical_y: float, roi: tuple[int, int, int, int]
) -> tuple[float, float, bool]:
    """逻辑坐标相对 ROI 的归一化位置 ``u = (x - roi_x) / roi_w``、``v`` 同理。

    不做 clamp：点在 ROI 外时 u / v 会 < 0 或 > 1，``inside_roi`` 为 False。
    """
    rx, ry, rw, rh = roi
    u = (logical_x - rx) / rw
    v = (logical_y - ry) / rh
    inside_roi = (0.0 <= u <= 1.0) and (0.0 <= v <= 1.0)
    return u, v, inside_roi


def is_injected_event(flags: int) -> bool:
    """低级鼠标钩子事件是否被标记为注入（其它自动化工具产生），默认跳过这类事件。"""
    return bool(int(flags) & LLMHF_INJECTED)


def match_mumu_toplevel_title(title: str) -> bool:
    """顶层窗口标题是否像 MuMu（对齐 handle.py 的标题关键字）。"""
    if not title:
        return False
    return any(key in title for key in _MUMU_TITLE_KEYS)


def viewport_sanity(
    win_rect: tuple[int, int, int, int], scale_rate: float, tol: int = 8
) -> tuple[bool, str]:
    """校验视口窗口的物理尺寸是否≈1280×720（复用 handle.py ``screenshot_size`` 的判定思路）。

    这是选错窗口 / 坐标空间不一致时的兜底闸门：不通过就拒绝启动，让用户改用 ``--hwnd``。
    """
    left, top, right, bottom = win_rect
    w = right - left
    h = bottom - top
    if w <= 0 or h <= 0:
        return False, f"窗口尺寸非法 {w}x{h}（rect={win_rect}）"
    phys_w = w * scale_rate
    phys_h = h * scale_rate
    if abs(phys_w - LOGICAL_WIDTH) > tol or abs(phys_h - LOGICAL_HEIGHT) > tol:
        return False, (
            f"视口窗口物理尺寸≈{phys_w:.0f}x{phys_h:.0f}，不接近 {LOGICAL_WIDTH}x{LOGICAL_HEIGHT}"
            f"（原始 rect={win_rect}，scale={scale_rate}）。可能选错了窗口——"
            f"请用 --hwnd 指定 OAS 日志里的 “Screenshot handle num”，或确认 MuMu 分辨率为 1280x720"
        )
    return True, "ok"


def build_sample(
    *,
    now,
    config_name: str,
    screen_x: float,
    screen_y: float,
    win_rect: tuple[int, int, int, int],
    injected: bool,
    scale_rate: float | None = None,
    viewport_hwnd: int | None = None,
    scene: str | None = None,
    target: str | None = None,
    roi: tuple[int, int, int, int] | None = None,
) -> dict:
    """组装一条人工点击样本。``x`` / ``y`` 永远是 OAS 1280×720 逻辑坐标（四舍五入到 int）。"""
    left, top, right, bottom = win_rect
    win_w = right - left
    win_h = bottom - top
    client_x, client_y, lx_f, ly_f, inside = screen_to_logical(screen_x, screen_y, win_rect)
    logical_x = int(round(lx_f))
    logical_y = int(round(ly_f))
    sample: dict = {
        "ts": now().astimezone().isoformat(timespec="milliseconds"),
        "source": "manual",
        "config": config_name,
        "screen_x": int(round(screen_x)),
        "screen_y": int(round(screen_y)),
        "client_x": int(round(client_x)),
        "client_y": int(round(client_y)),
        "x": logical_x,
        "y": logical_y,
        "window_width": int(win_w),
        "window_height": int(win_h),
        "logical_width": LOGICAL_WIDTH,
        "logical_height": LOGICAL_HEIGHT,
        "inside_viewport": bool(inside),
        "injected": bool(injected),
    }
    if scale_rate is not None:
        sample["window_scale_rate"] = scale_rate
    if viewport_hwnd is not None:
        sample["viewport_hwnd"] = int(viewport_hwnd)
    if scene:
        sample["scene"] = scene
    if target:
        sample["target"] = target
    if roi is not None:
        u, v, inside_roi = relative_uv(logical_x, logical_y, roi)
        sample["roi"] = [int(v) for v in roi]
        sample["u"] = round(u, 4)
        sample["v"] = round(v, 4)
        sample["inside_roi"] = bool(inside_roi)
    return sample


class ManualClickStats:
    """在线（Welford）统计。u / v 只累计 ROI 内样本，避免外围点拉偏 preferred center。

    仅用于终端展示；权威数据是 JSONL 原始记录。
    """

    def __init__(self) -> None:
        self.total = 0
        self.roi_inside = 0
        self.roi_outside = 0
        self._n = 0
        self._mu_u = 0.0
        self._m2_u = 0.0
        self._mu_v = 0.0
        self._m2_v = 0.0

    def add(self, u, v, inside_roi) -> None:
        self.total += 1
        if inside_roi is None:  # 未指定 ROI
            return
        if inside_roi:
            self.roi_inside += 1
        else:
            self.roi_outside += 1
            return
        self._n += 1
        du = u - self._mu_u
        self._mu_u += du / self._n
        self._m2_u += du * (u - self._mu_u)
        dv = v - self._mu_v
        self._mu_v += dv / self._n
        self._m2_v += dv * (v - self._mu_v)

    @property
    def has_uv(self) -> bool:
        return self._n > 0

    @property
    def mean_u(self):
        return self._mu_u if self._n else None

    @property
    def mean_v(self):
        return self._mu_v if self._n else None

    @property
    def std_u(self):
        return (self._m2_u / self._n) ** 0.5 if self._n else None

    @property
    def std_v(self):
        return (self._m2_v / self._n) ** 0.5 if self._n else None


class ManualClickWriter:
    """按 ``<config>_<日期>.jsonl`` 写人工样本，跨天自动轮转，行缓冲。

    与 BehaviorTrace 不同：这是前台工具，写失败**向上抛**，由 ``main`` 打印错误、停止
    采样并在 ``finally`` 里 unhook + close，不吞异常。
    """

    def __init__(self, config_name: str, root: Path | None = None, now=None) -> None:
        self._config = config_name
        self._root = Path(root) if root is not None else MANUAL_CLICK_LOG_ROOT
        self._now = now or datetime.now
        self._fh = None
        self._fh_date: date | None = None
        self._path: Path | None = None

    def _target_path(self, day: date) -> Path:
        file_name = f"{self._config}_{day.isoformat()}.jsonl"
        root = self._root.resolve()
        path = (root / file_name).resolve()
        try:
            path.relative_to(root)  # 机械兜底：不允许逃出 manual_click 目录
        except ValueError as exc:
            raise ValueError(f"输出路径逃逸 manual_click 目录：{path}") from exc
        if path.name != file_name:
            raise ValueError(f"非法 config 名导致文件名异常：{file_name!r}")
        return path

    def _ensure_handle(self) -> None:
        day = self._now().date()
        if self._fh is not None and self._fh_date == day:
            return
        if self._fh is not None:
            try:
                self._fh.close()
            except Exception:
                pass
            self._fh = None
        path = self._target_path(day)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(path, "a", encoding="utf-8", buffering=1)
        self._fh_date = day
        self._path = path

    def write(self, sample: dict) -> None:
        self._ensure_handle()
        line = json.dumps(sample, ensure_ascii=False, default=str)
        self._fh.write(line + "\n")

    @property
    def path(self) -> Path:
        return self._path if self._path is not None else self._target_path(self._now().date())

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            finally:
                self._fh = None


# --------------------------------------------------------------------------------------
# Win32 胶水（不做单元测试，均 lazy import；异常向上抛给 main 处理）
# --------------------------------------------------------------------------------------

def is_window(hwnd) -> bool:
    import win32gui

    try:
        return bool(hwnd) and bool(win32gui.IsWindow(int(hwnd)))
    except Exception:
        return False


def get_window_rect(hwnd) -> tuple[int, int, int, int]:
    import win32gui

    return tuple(win32gui.GetWindowRect(int(hwnd)))  # (left, top, right, bottom)


def _enum_toplevel_mumu() -> list[tuple[int, str]]:
    import win32gui

    found: list[tuple[int, str]] = []

    def _cb(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd)
            if match_mumu_toplevel_title(title):
                found.append((hwnd, title))
        except Exception:
            pass
        return True

    win32gui.EnumWindows(_cb, None)
    return found


def _find_game_child(top_hwnd: int) -> int | None:
    import win32gui

    hit: list[int] = []

    def _cb(child, _):
        try:
            if win32gui.GetParent(child) == top_hwnd:
                text = win32gui.GetWindowText(child)
                cls = win32gui.GetClassName(child)
                if text in _MUMU_GAME_CHILD_NAMES or cls in _MUMU_GAME_CHILD_NAMES:
                    hit.append(child)
        except Exception:
            pass
        return True

    win32gui.EnumChildWindows(top_hwnd, _cb, None)
    return hit[0] if hit else None


def resolve_viewport_hwnd(config_name: str, *, hwnd_override=None, handle_field: str = ""):
    """定位 MuMu 游戏画面窗口（OAS 逻辑 1280×720 的实际承载窗口）。

    优先级：
      1. ``--hwnd``：直接当作游戏画面窗口使用（对应 OAS 日志的 “Screenshot handle num”）。
      2. 复用 ``module.device.handle.Handle``：当 config 配了 ``script.device.handle`` 时，
         取 ``Handle.screenshot_handle_num``（与 OAS 截图 / window_message 点击同一个窗口）。
      3. 兜底：按窗口标题枚举 MuMu 顶层，再找 ``MuMuPlayer`` / ``NemuPlayer`` / ``MuMuNxDevice``
         游戏 child。多开且未配 handle 时可能不准，会提示改用 ``--hwnd``。

    Returns:
        ``(viewport_hwnd, info)``，``info`` 含定位方式 / 顶层窗口等诊断信息。
    """
    info: dict = {"method": None, "toplevel": None, "toplevel_title": None}

    if hwnd_override is not None:
        h = int(hwnd_override, 0) if isinstance(hwnd_override, str) else int(hwnd_override)
        if not is_window(h):
            raise RuntimeError(f"--hwnd {h} 不是有效窗口句柄")
        info["method"] = "hwnd-override"
        return h, info

    handle_field = (handle_field or "").strip()
    if handle_field:
        try:
            from module.device.handle import Handle

            handle = Handle(config=config_name)
            num = getattr(handle, "screenshot_handle_num", 0)
            if num and is_window(num):
                info["method"] = "Handle.screenshot_handle_num"
                info["toplevel"] = getattr(handle, "root_handle_num", None)
                info["toplevel_title"] = getattr(handle, "root_handle_title", None)
                return int(num), info
            info["handle_error"] = f"screenshot_handle_num 无效：{num!r}"
        except Exception as exc:  # Handle 构造较重，失败就退回标题扫描
            info["handle_error"] = f"{type(exc).__name__}: {exc}"

    tops = _enum_toplevel_mumu()
    if not tops:
        raise RuntimeError(
            "找不到 MuMu 窗口。请确认目标 MuMu 已启动；"
            "或在 config 的 script.device.handle 填写句柄，或用 --hwnd 直接指定游戏窗口句柄"
        )
    if len(tops) > 1:
        listed = ", ".join(f"{h}:{t!r}" for h, t in tops)
        print(
            f"[警告] 发现多个 MuMu 顶层窗口（{listed}），默认用第一个。"
            f"多开场景请用 --hwnd 明确指定游戏窗口句柄。",
            file=sys.stderr,
        )
    top_hwnd, top_title = tops[0]
    child = _find_game_child(top_hwnd)
    if not child:
        raise RuntimeError(
            f"MuMu 顶层窗口 {top_hwnd}({top_title!r}) 下找不到游戏画面 child "
            f"（期望名 {_MUMU_GAME_CHILD_NAMES}）。请用 --hwnd 指定"
        )
    info["method"] = "title-scan"
    info["toplevel"] = top_hwnd
    info["toplevel_title"] = top_title
    return int(child), info


def _read_handle_field(config_name: str) -> str:
    """读取 config 的 ``script.device.handle``（用于判断走 Handle 复用还是标题扫描）。"""
    try:
        from module.config.config import Config

        cfg = Config(config_name, task=None)
        return str(getattr(cfg.script.device, "handle", "") or "").strip()
    except Exception as exc:
        print(f"[提示] 读取 config 的 device.handle 失败（{exc}），改用窗口标题扫描。", file=sys.stderr)
        return ""


class MouseHook:
    """WH_MOUSE_LL 低级鼠标钩子。只读事件、始终放行，绝不发送 / 修改输入。"""

    WH_MOUSE_LL = 14
    WM_LBUTTONDOWN = 0x0201

    def __init__(self, on_left_down) -> None:
        self._on_left_down = on_left_down  # callable(pt: (x, y), flags: int)
        self._hook = None
        self._proc_ref = None  # 必须持有回调引用，否则被 GC
        self._user32 = None

    def start(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        LRESULT = ctypes.c_ssize_t
        ULONG_PTR = ctypes.c_size_t

        class MSLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [
                ("pt", wintypes.POINT),
                ("mouseData", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR),
            ]

        HOOKPROC = ctypes.CFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
        user32.CallNextHookEx.restype = LRESULT
        user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

        def _proc(nCode, wParam, lParam):
            # 无论如何都要放行事件，任何异常都不能影响用户鼠标操作。
            try:
                if nCode == 0 and wParam == self.WM_LBUTTONDOWN:
                    ms = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                    self._on_left_down((int(ms.pt.x), int(ms.pt.y)), int(ms.flags))
            except Exception:
                pass
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        self._proc_ref = HOOKPROC(_proc)
        self._user32 = user32
        self._hook = user32.SetWindowsHookExW(
            self.WH_MOUSE_LL, self._proc_ref, kernel32.GetModuleHandleW(None), 0
        )
        if not self._hook:
            raise OSError(ctypes.get_last_error(), "SetWindowsHookExW(WH_MOUSE_LL) 失败")

    def pump(self, should_stop) -> None:
        """在**当前线程**跑消息循环，直到 ``should_stop()`` 为真或收到 KeyboardInterrupt。"""
        import ctypes
        from ctypes import wintypes

        user32 = self._user32
        msg = wintypes.MSG()
        PM_REMOVE = 0x0001
        while not should_stop():
            got = user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE)
            if got:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            else:
                time.sleep(0.008)  # 让出 CPU 且可被 Ctrl+C 打断

    def stop(self) -> None:
        if self._hook and self._user32 is not None:
            try:
                self._user32.UnhookWindowsHookEx(self._hook)
            except Exception:
                pass
            finally:
                self._hook = None


# --------------------------------------------------------------------------------------
# CLI / 主流程
# --------------------------------------------------------------------------------------

def _parse_args(argv):
    p = argparse.ArgumentParser(
        prog="manual_click_recorder",
        description="被动采集目标 MuMu 游戏画面内的人工左键点击，换算成 OAS 1280x720 逻辑坐标。",
    )
    p.add_argument("--config", required=True, help="完整 config 名（如 oas1 / account_group_1）")
    p.add_argument("--hwnd", default=None, help="直接指定游戏画面窗口句柄（十进制或 0x 十六进制）；跳过自动定位")
    p.add_argument("--scene", default=None, help="可选人工标签：场景 / 任务名（如 RealmRaid）")
    p.add_argument("--target", default=None, help="可选人工标签：目标控件名（如 I_FIRE）")
    p.add_argument("--roi", default=None, help="可选 ROI，格式 x,y,w,h（1280x720 逻辑空间）；给了则每条记录带 u/v")
    p.add_argument("--include-injected", action="store_true", help="也记录被标记为 injected 的鼠标事件（默认跳过）")
    p.add_argument("--every", type=int, default=1, help="每 N 次点击打印一行实时输出（默认 1）")
    p.add_argument("--force", action="store_true", help="跳过视口 1280x720 尺寸校验（确认窗口无误时用）")
    return p.parse_args(argv)


def _print_summary(stats: ManualClickStats, roi, out_path) -> None:
    print()
    print("人工点击采样完成")
    print(f"  输出文件：{out_path}")
    print(f"  样本数：{stats.total}")
    if roi is not None:
        print(f"  ROI 内：{stats.roi_inside}")
        print(f"  ROI 外：{stats.roi_outside}")
        if stats.has_uv:
            print("  preferred center:")
            print(f"    u = {stats.mean_u:.4f}")
            print(f"    v = {stats.mean_v:.4f}")
            print("  spread:")
            print(f"    σu = {stats.std_u:.4f}")
            print(f"    σv = {stats.std_v:.4f}")
        else:
            print("  （ROI 内样本不足，无法给出 preferred center）")


def main(argv=None) -> int:
    if sys.platform != "win32":
        print("ManualClickRecorder 仅支持 Windows。", file=sys.stderr)
        return 2

    args = _parse_args(argv)

    try:
        config_name = resolve_config_name(args.config)
    except Exception as exc:
        print(f"config 名非法：{exc}", file=sys.stderr)
        return 2

    roi = None
    if args.roi:
        try:
            roi = parse_roi(args.roi)
        except ValueError as exc:
            print(f"--roi 非法：{exc}", file=sys.stderr)
            return 2

    handle_field = "" if args.hwnd is not None else _read_handle_field(config_name)
    try:
        viewport_hwnd, info = resolve_viewport_hwnd(
            config_name, hwnd_override=args.hwnd, handle_field=handle_field
        )
    except Exception as exc:
        print(f"定位游戏窗口失败：{exc}", file=sys.stderr)
        return 3

    from module.device.handle import window_scale_rate

    try:
        scale_rate = float(window_scale_rate())
    except Exception:
        scale_rate = 1.0
    rect = get_window_rect(viewport_hwnd)
    ok, why = viewport_sanity(rect, scale_rate)
    if not ok and not args.force:
        print(f"[视口校验失败] {why}", file=sys.stderr)
        print("确认窗口无误可加 --force 跳过该校验。", file=sys.stderr)
        return 3

    writer = ManualClickWriter(config_name)
    stats = ManualClickStats()
    lock = threading.Lock()
    state = {"stop": False, "n": 0}

    win_w = rect[2] - rect[0]
    win_h = rect[3] - rect[1]
    print("人工点击采样器")
    print()
    print(f"  config: {config_name}")
    print(f"  窗口: {info.get('toplevel_title')!r}  定位方式: {info.get('method')}")
    if info.get("handle_error"):
        print(f"  （Handle 复用未成功：{info['handle_error']}）")
    print(f"  viewport hwnd: {viewport_hwnd}")
    print(f"  viewport: {win_w} x {win_h}  (scale={scale_rate}, 物理≈{win_w * scale_rate:.0f}x{win_h * scale_rate:.0f})")
    print(f"  logical: {LOGICAL_WIDTH} x {LOGICAL_HEIGHT}")
    if args.scene:
        print(f"  scene: {args.scene}")
    if args.target:
        print(f"  target: {args.target}")
    if roi is not None:
        print(f"  roi: {roi}")
    print()
    print(f"  输出: {writer.path}")
    print()
    if not ok:
        print("  [注意] 已用 --force 跳过视口尺寸校验。")
    print("  只记录目标游戏画面内的真实人工左键。按 Ctrl+C 停止。")
    print()

    every = max(1, int(args.every))

    def on_left_down(pt, flags):
        injected = is_injected_event(flags)
        if injected and not args.include_injected:
            return
        if not is_window(viewport_hwnd):
            print("目标窗口已关闭，停止采样。")
            state["stop"] = True
            return
        try:
            cur_rect = get_window_rect(viewport_hwnd)
        except Exception:
            print("读取目标窗口位置失败，停止采样。")
            state["stop"] = True
            return
        sample = build_sample(
            now=datetime.now,
            config_name=config_name,
            screen_x=pt[0],
            screen_y=pt[1],
            win_rect=cur_rect,
            injected=injected,
            scale_rate=scale_rate,
            viewport_hwnd=viewport_hwnd,
            scene=args.scene,
            target=args.target,
            roi=roi,
        )
        if not sample["inside_viewport"]:
            return  # 点在游戏画面外（标题栏 / 边框 / 别的窗口）→ 忽略
        with lock:
            try:
                writer.write(sample)
            except Exception as exc:
                print(f"[写入失败] {type(exc).__name__}: {exc}，停止采样。")
                state["stop"] = True
                return
            state["n"] += 1
            n = state["n"]
            stats.add(sample.get("u"), sample.get("v"), sample.get("inside_roi"))
        if n % every == 0:
            if roi is not None:
                tag = "" if sample["inside_roi"] else "  [ROI外]"
                print(
                    f"#{n:<4} logical=({sample['x']:>4},{sample['y']:>4})  "
                    f"uv=({sample['u']:.3f},{sample['v']:.3f}){tag}"
                )
            else:
                print(f"#{n:<4} logical=({sample['x']:>4},{sample['y']:>4})")

    hook = MouseHook(on_left_down)
    try:
        hook.start()
        hook.pump(lambda: state["stop"])
    except KeyboardInterrupt:
        print("\n收到 Ctrl+C，停止采样…")
    except Exception as exc:
        print(f"\n采样异常：{type(exc).__name__}: {exc}", file=sys.stderr)
    finally:
        hook.stop()
        writer.close()
        _print_summary(stats, roi, writer.path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
