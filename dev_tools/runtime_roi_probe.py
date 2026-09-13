# This Python file uses the following encoding: utf-8
"""只读 Runtime ROI Probe：截一帧目标 MuMu 游戏画面，用现有 `RuleImage.match()` 去匹配
指定资产（默认 `RealmRaidAssets.I_FIRE`，寮突破的进攻按钮），读出匹配成功后被
`_update_roi_front` 动态改写的 `roi_front`，为人工点击分析提供准确的运行时 ROI。

硬约束：
- **只截图、只识别、只打印 / 记录，绝不点击、绝不发送任何输入。**
- **不主动启动 MuMu / 游戏 / OAS 任务**：目标窗口必须已经在运行；本工具不实例化
  `Device`（其 `__init__` 在模拟器未运行时会主动 `emulator_start()`，是明确要
  避免的副作用）、不实例化 `BaseTask`（业务副作用过多）。截屏复用
  `module/device/method/windows_impl.py:Window.screenshot_window_background`
  （production 已在用的 BitBlt 截屏协议，无需新造第二套）；窗口定位复用
  `dev_tools/manual_click_recorder.py` 里已实现并测过的
  `resolve_viewport_hwnd` / `viewport_sanity`（同一套 Handle / 标题扫描逻辑，
  不建第二套 HWND 查找）。
- 图像匹配走生产用的 Image RPC 服务（`RuleImage.match()` 内部调用
  `get_image_client()`），**不修改 `RuleImage` 公共 API**；该服务未启动时视为
  "设备/服务不可用"，清晰报错退出，不崩溃、不重试到死。

运行：``toolkit/python.exe dev_tools/runtime_roi_probe.py --config yys1 --target I_FIRE``
（默认 `--count 1`，即"一次性模式"；重复采样见下方 CLI 帮助）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

LOGICAL_WIDTH = 1280
LOGICAL_HEIGHT = 720

# probe 记录输出根目录：log/manual_click_analysis/runtime_roi/<target>_<日期>.jsonl
RUNTIME_ROI_LOG_ROOT = Path(_PROJECT_ROOT) / "log" / "manual_click_analysis" / "runtime_roi"

# 目前支持的探测目标。key 是 CLI 传入的 --target 名；value 是 (module_path, class_name,
# attr_name)，惰性 import，避免探测其它 target 时也拖入用不到的资产模块。
_TARGET_REGISTRY: dict[str, tuple[str, str, str]] = {
    "I_FIRE": ("tasks.RealmRaid.assets", "RealmRaidAssets", "I_FIRE"),
}


# --------------------------------------------------------------------------------------
# 纯函数部分（无 Win32 / RPC 依赖，单元测试直接覆盖）
# --------------------------------------------------------------------------------------

def resolve_target(name: str):
    """按名字取一个已注册的 `RuleImage` 资产实例（惰性 import，找不到就明确报错）。"""
    entry = _TARGET_REGISTRY.get(name)
    if entry is None:
        raise ValueError(
            f"未知 target：{name!r}；当前只支持 {sorted(_TARGET_REGISTRY)}"
        )
    module_path, class_name, attr_name = entry
    import importlib

    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return getattr(cls, attr_name)


def build_probe_record(
    *, now, config_name: str, target_name: str, matched: bool,
    roi_front: tuple[int, int, int, int] | None, viewport_hwnd: int | None,
    error: str | None = None,
) -> dict:
    """组装一条 runtime ROI 探测记录。`matched=False` 时也记录（不静默丢弃）。"""
    rec: dict = {
        "ts": now().astimezone().isoformat(timespec="milliseconds"),
        "config": config_name,
        "target": target_name,
        "matched": bool(matched),
        "viewport_hwnd": int(viewport_hwnd) if viewport_hwnd is not None else None,
    }
    if matched and roi_front is not None:
        x, y, w, h = (int(v) for v in roi_front)
        rec.update(
            roi_front=[x, y, w, h],
            center=[round(x + w / 2, 1), round(y + h / 2, 1)],
            template_width=w,
            template_height=h,
        )
    if error:
        rec["error"] = error
    return rec


def probe_record_path(target_name: str, day: date, root: Path | None = None) -> Path:
    """计算某 target 某天的 probe 记录文件路径（不做 IO）。"""
    root = Path(root) if root is not None else RUNTIME_ROI_LOG_ROOT
    return root / f"{target_name}_{day.isoformat()}.jsonl"


def append_probe_record(path: Path, record: dict) -> None:
    """追加一条 JSON 行；自动建目录；不做跨天轮转判断（探测会话通常很短）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def summarize_roi_samples(records: list[dict]) -> dict:
    """汇总多次 probe 的结果：matched/unmatched 计数、去重后的 ROI 集合与坐标范围。

    只有当 ``unique_roi_count <= 1`` 才说明这批样本里运行时 ROI 完全稳定；
    出现多个不同 ROI 时只报告范围，**不代表** ROI 会一直漂移，也不建议据此
    强行归一化——按规格要求，多值时把范围报出来，时间匹配留给下一轮设计。
    """
    matched = [r for r in records if r.get("matched")]
    rois = [tuple(r["roi_front"]) for r in matched if r.get("roi_front")]
    unique = sorted(set(rois))
    out: dict = {
        "total": len(records),
        "matched_count": len(matched),
        "unmatched_count": len(records) - len(matched),
        "unique_roi_count": len(unique),
        "unique_rois": [list(u) for u in unique],
        # 至少要有过一次成功匹配才谈得上“ROI 稳定”；0 次匹配不算稳定，只是没有数据。
        "stable": len(matched) > 0 and len(unique) <= 1,
    }
    if rois:
        xs = [r[0] for r in rois]
        ys = [r[1] for r in rois]
        ws = [r[2] for r in rois]
        hs = [r[3] for r in rois]
        out.update(
            x_min=min(xs), x_max=max(xs), y_min=min(ys), y_max=max(ys),
            w_min=min(ws), w_max=max(ws), h_min=min(hs), h_max=max(hs),
        )
    return out


# --------------------------------------------------------------------------------------
# Win32 / RPC 胶水（不做单元测试，全部 lazy import；异常向上抛给 main 处理）
# --------------------------------------------------------------------------------------

def capture_frame(hwnd: int, size: tuple[int, int]):
    """复用生产截屏协议 `Window.screenshot_window_background`，不新造第二套。

    该方法只依赖 `self.screenshot_handle_num` / `self.screenshot_size` 两个属性，
    用一个最小 `SimpleNamespace` 顶替 `self` 即可直接调用，不需要构造完整的
    `Window`/`Handle` 实例（避免其 `__init__` 里的任何额外副作用）。
    """
    from types import SimpleNamespace

    from module.device.method.windows_impl import Window

    ns = SimpleNamespace(screenshot_handle_num=hwnd, screenshot_size=size)
    return Window.screenshot_window_background(ns)


def resolve_probe_viewport(config_name: str, *, hwnd_override=None):
    """定位并校验 probe 用的视口窗口，返回 `(hwnd, capture_size, info)`。

    复用 `dev_tools/manual_click_recorder.py` 已实现并测过的 Handle / 标题扫描
    定位逻辑与 1280x720 视口校验，不建第二套 HWND 查找。
    """
    from dev_tools.manual_click_recorder import (
        _read_handle_field,
        get_window_rect,
        resolve_viewport_hwnd,
        viewport_sanity,
    )
    from module.device.handle import window_scale_rate

    handle_field = "" if hwnd_override is not None else _read_handle_field(config_name)
    hwnd, info = resolve_viewport_hwnd(config_name, hwnd_override=hwnd_override, handle_field=handle_field)
    scale = float(window_scale_rate())
    rect = get_window_rect(hwnd)
    ok, why = viewport_sanity(rect, scale)
    if not ok:
        raise RuntimeError(f"视口校验失败：{why}")
    w = rect[2] - rect[0]
    h = rect[3] - rect[1]
    # 对齐 module/device/handle.py Handle.screenshot_size 的 snap 判定思路：
    # 窗口物理尺寸（虚拟化尺寸 × DPI scale）接近 1280x720 时按 1280x720 截取。
    size = (
        LOGICAL_WIDTH if abs(w * scale - LOGICAL_WIDTH) < 5 else w,
        LOGICAL_HEIGHT if abs(h * scale - LOGICAL_HEIGHT) < 5 else h,
    )
    info["scale"] = scale
    return hwnd, size, info


def probe_once(config_name: str, target_name: str, *, hwnd_override=None):
    """截一帧 + 用 `target.match(frame)` 识别一次，返回 `(hwnd, matched, roi_front)`。

    `target.match()` 是 `RuleImage` 现成的公共方法，内部经 `get_image_client()`
    连生产用的 Image RPC 服务；服务未启动时这里会抛异常，交给调用方按
    "设备/服务不可用" 处理，不在本函数内静默吞掉或重试。
    """
    hwnd, size, _info = resolve_probe_viewport(config_name, hwnd_override=hwnd_override)
    frame = capture_frame(hwnd, size)
    target = resolve_target(target_name)
    matched = target.match(frame)
    roi_front = tuple(target.roi_front) if matched else None
    return hwnd, matched, roi_front


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------

def _parse_args(argv):
    p = argparse.ArgumentParser(
        prog="runtime_roi_probe",
        description="只读探测目标资产（默认 I_FIRE 进攻按钮）在当前游戏画面里匹配后的真实运行时 roi_front。",
    )
    p.add_argument("--config", required=True, help="完整 config 名（如 yys1）")
    p.add_argument("--target", default="I_FIRE", help=f"探测目标，当前支持 {sorted(_TARGET_REGISTRY)}（默认 I_FIRE）")
    p.add_argument("--hwnd", default=None, help="直接指定游戏画面窗口句柄，跳过自动定位")
    p.add_argument("--once", action="store_true", help="只探测一次（等价于 --count 1，也是默认行为）")
    p.add_argument("--count", type=int, default=1, help="探测次数（默认 1）")
    p.add_argument("--interval", type=float, default=2.0, help="多次探测之间的间隔秒数（默认 2.0，仅 --count>1 时生效）")
    p.add_argument("--out-dir", default=None, help=f"记录输出目录（默认 {RUNTIME_ROI_LOG_ROOT}）")
    return p.parse_args(argv)


def main(argv=None) -> int:
    if sys.platform != "win32":
        print("runtime_roi_probe 仅支持 Windows。", file=sys.stderr)
        return 2

    args = _parse_args(argv)
    try:
        from dev_tools.manual_click_recorder import resolve_config_name

        config_name = resolve_config_name(args.config)
    except Exception as exc:
        print(f"config 名非法：{exc}", file=sys.stderr)
        return 2

    if args.target not in _TARGET_REGISTRY:
        print(f"未知 --target {args.target!r}；当前只支持 {sorted(_TARGET_REGISTRY)}", file=sys.stderr)
        return 2

    count = 1 if args.once else max(1, args.count)
    out_root = Path(args.out_dir) if args.out_dir else RUNTIME_ROI_LOG_ROOT
    out_path = probe_record_path(args.target, datetime.now().date(), root=out_root)

    print("Runtime ROI Probe")
    print()
    print(f"  config: {config_name}")
    print(f"  target: {args.target}")
    print(f"  count: {count}" + (f"  interval: {args.interval}s" if count > 1 else ""))
    print(f"  输出: {out_path}")
    print()
    print("  只截图 + 只识别 + 只记录，不点击、不发送任何输入。")
    print()

    records: list[dict] = []
    for i in range(count):
        try:
            hwnd, matched, roi_front = probe_once(config_name, args.target, hwnd_override=args.hwnd)
        except Exception as exc:
            # 第一次就失败：多半是目标窗口不存在 / 图像识别服务未启动，重试没有意义。
            print(
                f"[!] 设备 / 窗口 / 图像识别服务不可用：{type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            print(
                "    请确认目标 MuMu 已启动、config 对应实例正确、"
                "以及 OAS 主进程（图像识别服务）已在运行——本工具不会自动启动它们。",
                file=sys.stderr,
            )
            if i == 0:
                return 3
            # 已有过成功探测，中途失败就停止但保留已采集的记录。
            break

        rec = build_probe_record(
            now=datetime.now, config_name=config_name, target_name=args.target,
            matched=matched, roi_front=roi_front, viewport_hwnd=hwnd,
        )
        try:
            append_probe_record(out_path, rec)
        except Exception as exc:
            print(f"[写入失败] {type(exc).__name__}: {exc}", file=sys.stderr)
            return 4
        records.append(rec)

        if matched:
            rf = rec["roi_front"]
            print(f"#{i + 1:<3} matched=True   roi_front=({rf[0]},{rf[1]},{rf[2]},{rf[3]})  center={rec['center']}")
        else:
            print(f"#{i + 1:<3} matched=False  （本次截图里没识别到 {args.target}）")

        if count > 1 and i < count - 1:
            time.sleep(args.interval)

    print()
    summary = summarize_roi_samples(records)
    print("探测完成")
    print(f"  总次数：{summary['total']}   matched：{summary['matched_count']}   "
          f"unmatched：{summary['unmatched_count']}")
    print(f"  unique roi 数：{summary['unique_roi_count']}  "
          f"（{'稳定' if summary['stable'] else '存在变化，不要直接归一化，见 unique_rois'}）")
    if summary["matched_count"]:
        print(f"  x: {summary['x_min']}~{summary['x_max']}   y: {summary['y_min']}~{summary['y_max']}")
        print(f"  w: {summary['w_min']}~{summary['w_max']}   h: {summary['h_min']}~{summary['h_max']}")
        print(f"  unique_rois: {summary['unique_rois']}")
    print(f"  记录文件：{out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
