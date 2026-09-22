# This Python file uses the following encoding: utf-8
"""L1 全局单击管线：把「已经决定要点」的目标变成一次物理单击。

    Target → resolve_click_point → FinalPoint → execute_single_click
           → Control.click → 后端（minitouch：DOWN → dwell → UP）→ BehaviorTrace

本层只回答两件事：**最终点在哪**、**这一击怎么落下去**。一次调用 = 一次物理点击。
不做 reaction 等待 / fresh 截图 / 二次确认 / 重试 / 连点 / 业务节奏——这些属于 L2 / L3，
由各业务状态机自己拥有（见 `docs/DECISIONS.md` D026）。点击时序（dwell / pressure）仍由
`Control.click` → 后端负责，本层不增加任何 sleep。

坐标语义必须显式声明，**禁止裸 `(x, y)`**——裸坐标看不出「是目标中心」还是「已经是最终落点」，
正是 double randomization（上层随机一次、下层再随机一次）的来源：

- `Rule*`（`RuleImage` / `RuleClick` / `RuleOcr` / `RuleGif`）：图片 / 规则目标，走
  `rule.coord()`（EMPIRICAL 热点优先，否则 RULE_FALLBACK；HABIT 采样一次）。
- `ClickBounds`：运行时得到的动态矩形。`native=False`（游戏内 OCR 框 / 列表项等）按目标身份
  走 Point 模型；`native=True`（原生 Android 控件 bounds）只用 RULE_FALLBACK 区域模型，
  **绝不**查游戏图片的 empirical 热点。
- `ClickRegion`：业务已经选定的安全区域（如 Settlement 的 SAVE_RIGHT / SAVE_BOTTOM /
  DEFAULT），本层只在区域内取一次点，不改业务的区域选择策略。
- `FinalPoint`：业务已经算好的最终落点，原样执行，**绝不再做任何空间采样**。

后端默认由 `Control.click` 按 `control_method` 配置分发；只有百鬼夜行这类高频小游戏可以用
`backend=` 显式指定 `Control.click_with_backend` 的专用后端（保留原 window_message fast 按压），
坐标语义 / 一击一次 / BehaviorTrace 与默认路径完全相同。业务模块不得自己直调
`click_minitouch` / `click_window_message`。

长按是另一种物理动作，走独立的 `execute_long_click`（Control.long_click → 各后端的长按实现），
与单击执行器互不替代：单击执行器拒绝 `RuleLongClick`，长按执行器不降级成单击、不叠加单击 dwell。
"""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real

from module.atom.click import RuleClick
from module.atom.gif import RuleGif
from module.atom.image import RuleImage
from module.atom.long_click import RuleLongClick
from module.atom.ocr import RuleOcr
from module.click_sampler import ClickSampler

# 这些规则的 coord() 返回单点 (x, y)；RuleSwipe / RuleList 的 coord 语义不是单击落点，不接受。
_RULE_TARGET_TYPES = (RuleImage, RuleClick, RuleOcr, RuleGif)


def _to_int(value, field: str) -> int:
    """与 `Control.click` 里的 `ensure_int`（`int(value)`）口径一致：numpy 浮点 OCR 坐标
    也按截断取整，保证把原来的裸坐标改成 FinalPoint 后落点逐像素不变。bool 一律拒绝。"""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f'{field} 必须是数值：{value!r}')
    return int(value)


def _as_roi(roi, owner: str) -> tuple[int, int, int, int]:
    if len(roi) != 4:
        raise ValueError(f'{owner} 的 roi 必须是 (x, y, w, h)：{roi!r}')
    return tuple(_to_int(v, f'{owner}.roi') for v in roi)


@dataclass(frozen=True)
class FinalPoint:
    """业务已经算好的最终落点（例如锚点上方固定偏移、Settlement 复用的 anchor）。原样执行。"""
    x: int
    y: int

    def __post_init__(self) -> None:
        object.__setattr__(self, 'x', _to_int(self.x, 'FinalPoint.x'))
        object.__setattr__(self, 'y', _to_int(self.y, 'FinalPoint.y'))


@dataclass(frozen=True)
class ClickRegion:
    """业务已选定的安全区域：只在区域内按 Region 模型取一次点。"""
    roi: tuple[int, int, int, int]
    name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, 'roi', _as_roi(self.roi, 'ClickRegion'))


@dataclass(frozen=True)
class ClickBounds:
    """运行时得到的动态矩形 `(x, y, w, h)`。

    `native=True` 表示原生 Android 控件 bounds：不按名字查任何图片热点，只用 RULE_FALLBACK
    区域模型。宽或高为 0 的退化 bounds（原生控件 / OCR 细框都可能出现）退回中心点，不能因为
    采样器拒绝退化 ROI 而让业务崩掉。
    """
    roi: tuple[int, int, int, int]
    name: str
    native: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, 'roi', _as_roi(self.roi, 'ClickBounds'))


def resolve_click_point(target) -> tuple[int, int]:
    """把点击目标解析成最终整数落点。每次调用至多做一次空间采样，FinalPoint 零采样。"""
    if isinstance(target, FinalPoint):
        return target.x, target.y
    if isinstance(target, ClickRegion):
        return ClickSampler.sample_region(target.roi, target.name)
    if isinstance(target, ClickBounds):
        x, y, w, h = target.roi
        if w <= 0 or h <= 0:
            return x + w // 2, y + h // 2
        if target.native:
            # target_name=None → RULE_FALLBACK + default_region，不做任何名字热点查找。
            return ClickSampler.sample_region(target.roi, None)
        return ClickSampler.sample_target(target.roi, target.name)
    if isinstance(target, _RULE_TARGET_TYPES):
        x, y = target.coord()
        return _to_int(x, 'coord.x'), _to_int(y, 'coord.y')
    raise TypeError(
        f'无法解析的点击目标：{target!r}。裸坐标必须显式包成 FinalPoint，'
        f'动态矩形用 ClickBounds，业务安全区域用 ClickRegion。'
    )


def list_click_target(rule_list, pos, name: str):
    """把 `BaseTask.list_find` 的命中结果变成显式点击目标。

    - 文字列表：`RuleList.ocr_appear` 命中时记录了该文字的 OCR 框，且返回的中心点与本次 `pos`
      一致 → `ClickBounds(OCR 框)`，由统一模型在框内取一次点（替代「OCR 中心直点」与各业务
      自带的 `randint` 抖动）。
    - 图片列表：`image_appear` 返回的已是 `coord()` 采样过的点；以及拿不到匹配 OCR 框的任何
      情况（含 `ocr_appear` 无结果时的 `(0, 0)` 旧行为）→ `FinalPoint` 原样执行，绝不二次采样。
    """
    hit = getattr(rule_list, 'last_ocr_hit', None)
    if getattr(rule_list, 'is_ocr', False) is True and isinstance(hit, tuple):
        hit_point, hit_bounds = hit
        if hit_point == (_to_int(pos[0], 'pos.x'), _to_int(pos[1], 'pos.y')):
            return ClickBounds(hit_bounds, name)
    return FinalPoint(pos[0], pos[1])


def _control_name(target, control_name: str | None) -> str:
    if control_name:
        return control_name
    name = getattr(target, 'name', None)
    return name if name else 'Click'


def execute_single_click(device, target, control_name: str | None = None, backend: str | None = None) -> tuple[int, int]:
    """解析一次落点并执行**一次**物理单击，返回实际执行的坐标。

    长按不是单击：`RuleLongClick` 必须继续走 `device.long_click`，这里直接拒绝，避免把长按
    悄悄降级成轻点。`backend` 为空时走 `device.click`（按配置的 control_method）；非空时走
    `device.click_with_backend`，只换后端，不换坐标语义。
    """
    if isinstance(target, RuleLongClick):
        raise TypeError(f'{target!r} 是长按目标，不能走单击管线')
    x, y = resolve_click_point(target)
    name = _control_name(target, control_name)
    if backend is None:
        device.click(x=x, y=y, control_name=name)
    else:
        device.click_with_backend(x=x, y=y, backend=backend, control_name=name)
    return x, y


_DEFAULT_NAME = object()


def execute_long_click(device, target, duration, control_name=_DEFAULT_NAME) -> tuple[int, int]:
    """解析一次落点并执行**一次**物理长按，返回实际执行的坐标。

    - `duration` 是**秒**（或 `Control.long_click` 认识的秒区间 / `None`），原样交给
      `device.long_click`，本层不换算、不随机、不叠加单击的 dwell。`RuleLongClick.duration`
      是毫秒，由调用方在业务里除以 1000 后传入，与迁移前的原写法一致。
    - 落点走 `resolve_click_point`：业务已经 `coord()` 采样过的点必须包成 `FinalPoint`（零采样），
      直接传 Rule 才会在这里采样一次；绝不能在业务里先 `coord()` 再把 Rule 交进来。
    - `control_name` 不显式传入时才回退为 target.name / 'LongClick'；显式传入（含 None / 空串）
      一律原样透传，保证迁移点与原 `device.long_click(control_name=...)` 逐字段一致。
    - 不做 reaction 等待 / 截图 / 重试 / 连按；后端选择、control_check、BehaviorTrace 仍全部由
      `Control.long_click` 负责，异常原样向上传播。
    """
    x, y = resolve_click_point(target)
    if control_name is _DEFAULT_NAME:
        control_name = getattr(target, 'name', None) or 'LongClick'
    device.long_click(x=x, y=y, duration=duration, control_name=control_name)
    return x, y
