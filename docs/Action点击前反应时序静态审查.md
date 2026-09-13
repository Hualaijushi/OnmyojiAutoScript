# Action 点击前反应时序（`appear_then_click` / `confirm_delay`）静态审查

> 2026-09-02。只读专项审查——**未改任何生产代码、未新增测试**（`confirm_delay` 已有
> `tests/test_base_task_confirm_click.py` 5 用例充分覆盖）。方法论与四案例静态收口一致：
> 全仓审查 → 还原真实调用链 → 盘点消费者 → Action 分类 → 建立 timing ownership →
> 决定 `confirm_delay` 的长期职责。**production diff = 0**。
> 源码基准：HEAD `2cdf3a05` + 当前工作树（`tasks/base_task.py` 的工作树改动只涉及
> FatigueManager 接入与 `wait_until_appear_then_click` 关键字修复，**未触碰
> `appear_then_click` / `confirm_delay` 本体**，与 commit `880cd21f` 逐字一致）。

---

## 1. 核心结论

**问题**：对「可识别 Point Target 点击」，现有 `confirm_delay` 是否已经可以承担统一的
reaction timing 职责？

**回答：PARTIAL。**

- **能力本身正确且完整**：`confirm_delay` 路径已经是「首次识别 → 随机等待 → 重新截图 →
  二次 `appear`（目标消失则不点）→ 在新帧上重新 `coord()` → 点击」，对 `target` 为
  `RuleImage` 且未传 `action=` 的调用形态，它满足 **Fresh Frame Contract（模式 A）** 与
  **Target Relocation Contract**，且 T7 空间采样发生在 fresh 之后（无 stale-coord 风险）。
- **但不应「统一」**：① 当前**零生产消费者**（全仓 486 处 `appear_then_click` 调用，无一
  传 `confirm_delay`）；② 覆盖面有边界——`action=` 分支点的是 `action.coord()`（静态
  `RuleClick`，不重定位）、`RuleOcr` target 的重定位取决于 `ocr_appear`；③ D001 已定「按
  调用点风险显式 opt-in，不全局启用」，本轮无新证据推翻。
- **不需要新增 `reaction_delay` API**：`confirm_delay` 就是该 primitive；再起一个同义名字
  正是 D008「不重新加入 `reaction_delay` / `CLICK_REACTION_DELAY` / BaseTask 全局自动等待」
  要防的事。历史上 `RealmRaid.CLICK_REACTION_DELAY` 已作为失效项删除。
- **长期职责定义**：`confirm_delay` = 「可识别 Point Target 单次点击的 reaction timing +
  二次确认 + 重定位」。它是 micro timing；Fatigue idle/rest 是 macro timing；
  `wait_until_appear` / `frame_wait` 是 state wait；`interval` 是 retry throttle——四者
  owner 不同，不能互相替代，也不应在同一个 Action 上叠加实现同一个等待目的。

---

## 2. `appear_then_click` 当前真实调用链

源码 `tasks/base_task.py:319-388`。签名：

```python
def appear_then_click(self, target: RuleImage | RuleGif | RuleOcr,
                      action: Union[RuleClick, RuleLongClick] = None,
                      interval: float = None, threshold: float = None,
                      duration: float = None,
                      confirm_delay: tuple[float, float] = None):
```

### 2.A 默认路径（`confirm_delay is None`）——命中即点当帧

```
appear = self.appear(target, interval=interval, threshold=threshold)
         └─ 不截图！读 self.device.image（调用方 while 循环里最近一次 self.screenshot() 的帧）
         └─ RuleImage → target.match(image, ...) → _apply_match_result → 命中即写 target.roi_front
         └─ interval 给定时：Timer 未到 → 直接 return False（throttle gate，不 sleep）
if appear and not action:
    x, y = target.coord()          # ClickSampler.sample(target.roi_front)（当帧刚更新的 roi_front）
    self.device.click(x, y, control_name=target.name)
elif appear and action:
    x, y = action.coord()          # action 的静态 roi_front
    self.device.long_click / click
return appear                       # 返回「是否命中」
```

- **没有任何 delay / sleep**。唯一时间机制是 `interval`（`Timer` 门控，命中后 `reset`）。
- 截图由**调用方**负责（典型 `while 1: self.screenshot(); self.appear_then_click(...)`）。
- 坐标在**当前帧**上算：`target` 是 `RuleImage` 时 `roi_front` 就是本帧匹配位置，不 stale；
  但整段没有「识别后等一下再点」的语义。

### 2.B `confirm_delay=(lo, hi)` 路径——识别后二次确认再点

```
timer_key = target.name
if interval:
    # 维护 self.interval_timer[timer_key] = Timer(interval)
    if not self.interval_timer[timer_key].reached():
        return False                                  # ① throttle gate
if not self.appear(target, threshold=threshold):      # ② 首次识别（当帧，不截图）
    return False
delay = random_delay(*confirm_delay)                  # ③ SystemRandom.uniform(lo, hi)
sleep(delay)                                          # ④ 阻塞等待（reaction pause）
self.screenshot()                                     # ⑤ FRESH 截图
if not self.appear(target, threshold=threshold):      # ⑥ 二次确认（新帧）——目标没了就 return False，不点
    return False
if not action:
    x, y = target.coord()                             # ⑦ 在 fresh + re-appear 后的 roi_front 上采样
    self.device.click(x, y, control_name=target.name)
else:
    x, y = action.coord()                             # action=RuleClick 时用其静态 roi_front（不重定位）
    ... long_click / click
if interval:
    self.interval_timer[timer_key].reset()            # ⑧ throttle 复位
return True
```

调用链示意（照实）：

```
[interval gate]
   ↓ 通过
appear(target)   ← 首次识别（调用方帧）
   ↓ 命中
random_delay(lo,hi) → sleep
   ↓
screenshot       ← 新帧
   ↓
appear(target)   ← 二次确认；不命中 → return False（不点击）
   ↓ 命中（此时 target.roi_front 已按新帧更新）
target.coord() / action.coord()
   ↓
device.click
```

`tests/test_base_task_confirm_click.py::test_confirm_path_rechecks_and_clicks_latest_position`
已锁死这个事件序列：`['appear-A', 'sleep-0.15', 'screenshot', 'appear-B', 'coord-B',
'click-30-40-target']`——`coord` 用的是二次 `appear` 之后的位置（B），不是首次（A）。

---

## 3. `confirm_delay` 当前语义（逐项）

| 维度 | 事实 |
|---|---|
| **随机源** | `module/base/utils/random.random_delay(*confirm_delay)` → 模块级 `_rng = SystemRandom()` 的 `_rng.uniform(lo, hi)`。**不是** `protect.py` 里那个同名普通 `random` 版本（`base_task.py` 明确 `from module.base.utils.random import random_delay`）。 |
| **范围语义** | `tuple(min, max)`，连续均匀。`random_delay` 内有 validation：拒 `bool` / 非 `Real` / 非有限 / `<0` / `min>max`；`min==max` 短路返回该常量（此时 `sleep(常量)` 仍睡固定值）。`appear_then_click` 本身**不校验 tuple 形状**——`random_delay(*confirm_delay)` 对非 2 元组会 `TypeError`。 |
| **`None` / `0`** | `confirm_delay is None` → 完全不进该分支（默认）。`confirm_delay=(0, 0)` → `delay=0.0` → `sleep(0.0)` + 仍然重新截图 + 二次 `appear`。 |
| **delay 发生位置** | **首次识别成功之后、重新截图之前**（上节 ③④⑤ 之间）。不是识别前、不是 click 后。 |
| **"confirm" 的含义** | **真·二次确认**：sleep 后 `self.screenshot()` 取新帧，再 `self.appear(target)`；目标不在新帧里 → `return False` **不点击**。不是「延迟后无条件点」。 |
| **delay 后是否重新截图** | **是**（⑤ `self.screenshot()`）。 |
| **delay 后是否重新 `appear()`** | **是**（⑥）。 |
| **delay 后是否重新取坐标** | **是**（⑦ `target.coord()` 在 ⑥ 之后）。`RuleImage` 的 `appear` 会把 `roi_front` 更新到新帧匹配位置（`_apply_match_result` / `_update_roi_front` / `sift_match` 都写 `roi_front`），所以 `coord()` 采的是新位置。 |
| **最终 `coord()` 在 delay 前还是后** | **后**（关键结论——不存在「先算坐标→等 1 秒→点旧坐标」）。 |
| **stale frame / stale coord 风险** | 该路径**无**。默认路径也无（当帧算当帧点），只是默认路径没有 reaction pause 语义。 |
| **返回值** | confirm 路径：命中并点击 → `True`；interval 未到 / 首次或二次 `appear` 失败 → `False`。默认路径：返回 `appear`（是否命中），命中即已点。 |
| **异常** | 无 `try/except`。`screenshot` / `appear` / `coord` / `device.click` 抛出的异常原样透传（与项目其它 Action 一致）。 |
| **`Timer`** | confirm 路径只用 `interval` 的 `Timer`（throttle），**没有** reaction 专用 Timer——reaction 用一次性 `sleep`。 |

---

## 4. Fresh Frame Contract 检查

D015 硬约束 #3 / `docs/状态验证与重试模式归纳.md` §10：Action 前发生非零等待后，不能继续
无条件消费旧 screenshot / 旧 target 坐标。

`confirm_delay` 路径分类：**A —— 重新 screenshot + 重新 `appear` + 重新 `coord()`。**

- ⑤ `self.screenshot()`
- ⑥ `self.appear(target)`（新帧）
- ⑦ `target.coord()`（新帧的 `roi_front`）

**结论：`confirm_delay` 路径满足 Fresh Frame Contract（模式 A），无 Gap。**
默认路径（无 `confirm_delay`）不涉及非零等待，不在该契约范围内。

唯一边角：`action=` 分支点的是 `action.coord()`——`action` 是静态 `RuleClick`，其
`roi_front` 不随识别更新（这是 `RuleClick` 的定义，不是缺陷）；此时「二次确认」确认的是
`target`（图像 gate）仍在，点的是固定安全区。语义正确。

---

## 5. Target Relocation Contract 检查

| target 类型 | `appear()` 是否更新位置 | `confirm_delay` 后 `coord()` 用新位置？ |
|---|---|---|
| `RuleImage`（Template / Multi-scale / Sift Flann） | **是**——`match` → `_apply_match_result` 写 `self.roi_front`；本地 `template_match` / `multi_scale_template_match` / `sift_match` 也都 `_update_roi_front` / 改 `roi_front` | **是**（无 `action=` 时） |
| `RuleImage` + `action=RuleClick` | target 的 `roi_front` 更新，但点的是 `action.coord()`（静态） | 点静态区，不重定位（设计如此） |
| `RuleOcr` target | `appear` → `ocr_appear`；命中/坐标取决于 `RuleOcr` 实现与 mode | 需按 `RuleOcr` 单独确认（当前 `appear_then_click` 的 `target` 极少用 `RuleOcr`） |
| `RuleGif` target | `appear` → `match`（gif 逐帧） | 随 `match` 更新 |
| `action=RuleLongClick` | 同 `RuleClick`，静态 | 静态 |

**结论：对最主流的「`RuleImage` target、无 `action=`」形态，`confirm_delay` 的重定位是完整
的**。`RuleImage` 的 `roi_front` 是「运行时会被 match 覆写」的可变字段（参见
`docs/Exploration状态机静态收口.md` E-1 记录的 `search_up_fight` 原地改写），
`confirm_delay` 路径的二次 `appear` 天然吃到这次覆写。

---

## 6. 全仓 `appear_then_click` 调用方盘点

`grep -rn "appear_then_click(" tasks/ module/ script.py`（排除定义行）：**486 处调用，分布在
约 85 个文件**。调用最多的：`GeneralInvite`(24)、`DailyTrifles`(23)、`GeneralBattle`(16)、
`BondlingFairyland`(16)、`DemonRetreat`(13)、`RealmRaid`(12)、`MartialArts`(12)、
`HeroTest`(12)、`Login/service`(12)……

**`confirm_delay=` 传入次数：0。**（`grep -rn "confirm_delay" tasks/ module/ script.py` 只
命中 `base_task.py` 定义处 + 测试 + 文档 + `test_general_battle_timing.py:256` 的
`assertNotIn` 守卫。）

绝大多数调用形态是以下几类（按语义，非逐行）：

| 形态 | 典型 | 占比（估） | 说明 |
|---|---|---|---|
| `appear_then_click(I_X)` 无参 | `harvest_card` 的 8 连点、各 `run` 里「见到就关」的弹窗 | 高 | 当帧命中即点，无 throttle |
| `appear_then_click(I_X, interval=N)` | 轮询循环里 `while ...: appear_then_click(I_X, interval=1)` | 高 | throttle gate；RealmRaid `I_FIRE(interval=1)` 属此类 |
| `if appear_then_click(I_X, interval=N): continue/return` | FSM handler / `run` 主循环分派 | 中 | 命中即推进状态 |
| `appear_then_click(I_X, action=C_Y)` | 图像 gate + 固定区域点击 | 低 | 点 `C_Y` 静态区 |
| `appear_then_click(O_X, ...)` | OCR target | 很低 | |

---

## 7. Action Taxonomy（本轮核心产物之一）

| Action 类型 | 示例 | 适合 `appear_then_click` | 适合 `confirm_delay` | reaction timing owner |
|---|---|---|---|---|
| **Image Point Target** | `I_BOSS_BATTLE_BUTTON`、`I_UI_CONFIRM`、探索 `I_NORMAL_BATTLE_BUTTON` | 是（本来就是） | **是（Tier 1 候选）** | `confirm_delay`（显式 opt-in） |
| **Small / Strict Point Target** | 小图标类按钮（`short_side < 40`） | 是 | 可以，但空间用 T7 `strict`/`small` profile、时间更保守 | `confirm_delay` + T7 profile |
| **Transitional Button**（短生命周期） | 结算飘字、`I_EXIT`(interval=6)、快速切页按钮 | 是 | **否**——delay 期间按钮可能消失，二次确认必然 `False`，反而降低命中率 | 不加，靠 `interval` |
| **Repeated Poll Click** | `while: appear_then_click(I_X, interval=1)` / `ui_click_until_*` | 是 | **否**——循环本身已是节流+重试，再加 per-attempt sleep 是重复 timing | `interval`（已有） |
| **Static RuleClick Region** | `self.click(C_AREA_n)`、九宫格 `C_PARTITION_*` | **否**——无可 `appear()` 的图像目标 | 否 | 无（Page 已确认前提下点固定区） |
| **Settlement / Large Safe Region** | GeneralBattle `C_RANDOM_RD`（`_sample_settlement_click`） | 否——不是按钮识别 | 否——GeneralBattle 自有 `SETTLEMENT_CLICK_INTERVAL_RANGE` timer | GeneralBattle 契约 v2 |
| **Dynamic Search Result** | `order_medal.find_anyone` / `search_up_fight` 的 `match_all` / OCR 结果 | 部分——定位逻辑在 Task 里，不套 `appear_then_click` | 需「delay 后重新 search」，不是重新 `appear(单 target)` | Task（`fire()` 式 bounded retry） |
| **Swipe / Drag** | `RuleSwipe`、`press_and_drag` | **否**（不属该 API） | 否 | `frame_wait` / 固定 sleep（D013） |
| **Navigation Action** | `goto_page` / Navigator FSM | 否——已有 `Timer(30)` + 两帧稳定 | 否 | Navigator |
| **Retry Action** | Exploration `fire()` / 未来 bounded-retry primitive | 内部可用 `appear_then_click` | 每个 attempt 是独立 Action Transaction，reaction timing 应在 attempt **内** | Task / 未来 primitive |

---

## 8. 哪些 `self.click` / `device.click` 属于「可识别 Point Target」、可迁入

`grep`：`self.click(` 在 `tasks/` 共 **222 处**；`self.device.click(` / `self.device.long_click(`
在 `tasks/`（非 base）共 **34 处**。

`self.click(rule, interval=)` 的真实语义（`base_task.py:591-623`）：**不截图、不 `appear()`**，
直接 `rule.coord()` → `device.click`；`interval` 为 `Timer` 门控；**`interval` 为 None 时永远
返回 `False`（即使点了）**。

| 位置类别 | 当前调用 | target 来源 | 可 re-identify | 是否适合迁入 `appear_then_click` |
|---|---|---|---|---|
| `self.click(C_STATIC_REGION)` | 固定 `RuleClick` | 静态 ROI | 否 | **否**（无图像目标） |
| `self.click(I_IMAGE, interval=N)` 在 `while` 里 | `RuleImage`，但**依赖上一次 `appear` 设的 `roi_front`** | 上一帧匹配 | 是（但循环里通常上一步就有 `appear`） | 语义上等价于 `appear_then_click(I_IMAGE, interval=N)`——可迁，属 Tier 2（收益是「点前必再确认」，代价是多一次 match） |
| `self.click(rule)` 无 interval | 各类 | | | 迁入需评估：无 interval 的 `self.click` 返回 `False` 是被调用方依赖的语义之一 |
| `self.device.click(x, y)` 直坐标 | Task 自己算的动态坐标（如 `front_center()` 偏移、OCR 结果） | 动态 | 需重新 search | **否**——不是单 target `appear` 模型 |

> 结论：`self.click` 里真正「本可以是 `appear_then_click`」的是「循环内 `self.click(RuleImage,
> interval=)` 且点击前那一步就是对同一 `RuleImage` 的 `appear`」这一小类——但它们已经在
> throttle 循环里，迁移**不是** reaction timing 问题，属可读性/一致性，**本轮不动**。

---

## 9. 明确不能迁入 `appear_then_click` / 不能加 `confirm_delay` 的 Action

| 类别 | 原因 |
|---|---|
| **Static Region**（`C_AREA_*` / 九宫格 `C_PARTITION_*` / `C_CLICK_STANDBY_TEAM`） | 没有可 `appear()` 的图像目标；点的是「Page 已确认 → 在已知固定区点」。硬套 `appear_then_click(C_AREA)` 无意义（`RuleClick` 无模板）。 |
| **Settlement Region**（`C_RANDOM_RD` / `C_RANDOM_LEFT/RIGHT`） | 区域点击，不是按钮识别。GeneralBattle 已有 `SETTLEMENT_CLICK_INTERVAL_RANGE` timer 驱动的重复点击节奏（契约 v2）。 |
| **Dynamic Search Result**（`find_anyone` / `find_everyone` / `search_up_fight` 的 `match_all` / OCR result） | 需要「delay 后**重新 search**」而不是「重新 `appear(固定 target)`」；定位逻辑是 Task 私有的（含最近距离排序、`roi_front` 动态改写）。 |
| **Swipe / Drag** | 不属该 API。等待用 `frame_wait`（D012/D013）或固定 sleep。 |
| **Navigation / 现有 FSM handler**（`goto_page` / Navigator / GeneralBattle `gb_page_handle_dict` / Exploration `exec_exp_page`） | 已有可靠 `Timer` + 每轮 `screenshot` + `detect_page_in` 重判。为「统一」强行迁移会破坏成熟时序（D008）。 |
| **短生命周期 Transitional Button** | `confirm_delay` 的 sleep 期间目标消失 → 二次 `appear` 必 `False` → 不点 → 漏点。 |
| **Repeated Poll Click**（`ui_click_until_*` / `while: appear_then_click(interval=)`） | 循环本身是节流 + 重试；加 `confirm_delay` = 在每次 attempt 里再塞一个 sleep + 截图，与循环的 `interval` 职责重叠。 |

---

## 10. `interval` / `confirm_delay` / `random_delay` 职责区别

| 机制 | 是什么 | 是否 sleep | 目的 | Scale |
|---|---|---|---|---|
| **`interval`**（`appear_then_click` / `appear` / `click` 的参数） | `self.interval_timer[name] = Timer(interval)`，未到 `reached()` 直接 `return False`；命中后 `reset()` | **否**（纯 `Timer` 门控） | 同一目标两次动作的**最小间隔**（retry / click throttle），防同轮循环过密点击 | micro，跨循环轮次 |
| **`confirm_delay`**（`appear_then_click` 专属） | `sleep(random_delay(lo, hi))` + 重新截图 + 二次 `appear` + 重新 `coord` | **是** | 单次可识别 Point 点击的 **reaction pause + 二次确认 + 重定位** | micro，单个 Action 内 |
| **`random_delay(a, b)`**（`module/base/utils/random`） | `SystemRandom.uniform(a, b)`，纯返回一个 float | 否（自身不 sleep；调用方决定是否 `sleep` 它） | 通用「取一个随机时长/随机浮点」，被多种上层复用 | 取决于调用方 |

**同一调用点同时 `interval=N` + `confirm_delay=(lo,hi)` 时的真实链**：

```
interval Timer 未到 → return False（本轮不动）
      ↓ Timer 到
appear(target) 命中
      ↓
sleep(random_delay(lo,hi))        ← confirm_delay 的等待
      ↓
screenshot → appear → coord → click
      ↓
interval Timer.reset()
```

两者**顺序叠加、目的不同**：`interval` 决定「这一轮要不要尝试」，`confirm_delay` 是「决定
尝试之后、点下去之前的反应停顿」。不是对同一个等待目的的两套实现，但**都会增加该点击的
墙钟延迟**（若两者都设）。当前无任何调用点同时设置这两者（`confirm_delay` 零消费者）。

---

## 11. `confirm_delay` 与 `random_delay` 各调用场景的区分（防命名误判）

`grep -rn "random_delay(" tasks/ module/`（点击/等待相关，去重归类）：

| 用途类别 | 例 | 是不是 reaction timing |
|---|---|---|
| **Reaction timing** | `appear_then_click(confirm_delay=)` 内的 `sleep(random_delay(*confirm_delay))` | **是**（唯一一处） |
| **General task pacing** | `RyouToppa` 多处 `time.sleep(random_delay(...))`（业务步骤之间）、`flush_area_cache` 的 swipe `duration` 用 `random_delay(0.342, 0.362)` | 否——两个业务步骤之间的节奏 |
| **Retry throttle** | 各 `interval=` 不走 `random_delay`（是 `Timer`）；`list_find` 翻页后 `sleep(random.uniform(0.8,1.3))` 是普通 `random` 不是 `random_delay` | 否 |
| **Animation wait** | `open_expect_level` 的 `time.sleep(1)`、`fill_shikigami` 的 `time.sleep(0.5)`（固定值，非 `random_delay`） | 否 |
| **Frequency gate（战斗）** | GeneralBattle `_sample_interval` → `random_delay(low, high)` 作 `Timer.limit`（`PREPARE_CLICK_DELAY_RANGE` / `SETTLEMENT_CLICK_INTERVAL_RANGE`） | 否——GeneralBattle 自有的点击间隔契约 |
| **Cooldown jitter** | `fatigue._start_rest_cooldown` 的 `random_delay(jitter_min, jitter_max)` 乘在 cooldown 上 | 否——macro 恢复冷却 |
| **Probability sampling（名字误导）** | `fatigue.try_break` 里 `random_delay(0.0, 1.0) < probability`（当 `[0,1)` 概率用，不是等待）；`KekkaiUtilize.run` 的 `lazy_roll`（§16 cleanup queue #5） | **否**——只是取随机浮点，函数名 "delay" 误导 |

---

## 12. `confirm_delay` 与 FatigueManager 的关系（Macro vs Micro）

### FatigueManager 真实生产接入

- `BaseTask.__init__` 建 `self.fatigue_manager = get_fatigue_manager(identity, config.global_game.fatigue)`。
- Helper：`BaseTask.begin_fatigue_task(task_identity)` / `BaseTask.try_fatigue_break(*, safe, repeat_completed=, deadline=)`。
- **实际调用者只有 `tasks/RyouToppa/script_task.py`**：`begin_fatigue_task('RyouToppa')`
  （主循环前，`script_task.py:331`）；`try_fatigue_break(safe=True, repeat_completed=True,
  deadline=deadline)`（主 `while 1` 里 `attack_area()` 返回 `SUCCESS` / `FAILED_MARKED`
  之后、`continue` 之前，`script_task.py:357` / `:406`）。
- `script.py` 层：`begin_task` / `begin_global_activity` / `end_global_activity` + UI 快照。

### `FatigueManager.try_break` 做什么

`module/fatigue.py:441-540`：`if not enabled or not safe or task_identity is None: return None`
→ 按概率决定 `rest` / `idle` → `self._sleep(duration)`（idle 15~120s，rest 更长）→ 记账
（`_apply_idle_recovery` / `_apply_rest_recovery` / cooldown）。

**关键：`try_break` 全程不碰 `self.device`——不截图、不 `appear`、不重新识别 state。**
break 结束后由**调用方**负责重新截图 / 重判（RyouToppa 在 `continue` 后回到 `while` 顶重新
`has_ticket()` / `attack_area()`，SUCCESS 分支还显式 `self.screenshot()`）。

### 边界

| | Macro timing | Micro timing |
|---|---|---|
| 机制 | `FatigueManager` idle / rest | `confirm_delay` reaction pause |
| 触发点 | 调用方**显式**在安全节点传 `safe=True`（当前只有 RyouToppa 的 task-cycle 边界） | `appear_then_click` 内部，识别成功后 |
| 时长 | 15s ~ 数分钟 | 亚秒 ~ 数秒（调用方给） |
| 是否重新识别 state | 否（调用方负责） | **是**（内建二次 `appear`） |
| 能否发生在单次 Action transaction 中途 | **不能**——只在 task-cycle 安全节点 | 它**就是** transaction 的一步 |

**两者是否会在同一个点击 Action 上直接累加？——当前不会。** FatigueManager 的 break 发生在
`attack_area()` 这类「一整轮」结束后，不在任何 `appear_then_click` / `self.click` 内部。
`confirm_delay` 零消费者，即使未来启用，也在 `appear_then_click` 内部，与 FatigueManager 的
安全节点在时间线上前后分离。**理想长期模型**（本轮只记录差距，不实现）：

```
Safe Task Node
  → FatigueManager.try_break(safe=True)
      ├─ no break
      └─ break → idle/rest（sleep）→ 调用方 invalidate state → 重新 screenshot + 重新识别 state
  → Action selected（State recognized）
  → confirm_delay（reaction pause）
  → fresh screenshot + 二次 appear + 重新 coord
  → click
  → semantic verify（wait_until_appear / detect_page_in）
```

当前差距：break 后「必须完整重新识别 state」是**约定俗成靠调用方**，没有强制机制（RyouToppa
恰好做对了）。这不是本轮要修的（无 Level C、且只影响 fatigue 已接入的 RyouToppa）。

---

## 13. Action Transaction 边界（是否值得成为架构规则）

**候选定义**：

```
State recognized → reaction timing → fresh relocation → Action → Verify
```

作为一个**原子单元**：

- **Fatigue 不得在 transaction 中途插入**：当前**由构造保证**（FatigueManager 只在
  task-cycle 安全节点、不在 Action 内）。值得写成明文架构约束，防止未来有人把
  `try_fatigue_break` 塞进 `appear_then_click` / 循环体内部。
- **每个 Retry attempt 是一个新的 Action Transaction**：Exploration `fire()` 已经是这个形态
  ——`while` 每轮开头 `self.screenshot()` → `get_current_page()` → `appear_then_click` →
  下一轮再来。即「每 attempt 重新 fresh + 重新 locate」。未来 bounded-retry primitive
  （D015）应把这条写进契约（硬约束 #3 已隐含）。

**结论**：`Action Transaction` 值得作为**架构描述性概念**写进 `ARCHITECTURE.md` 的 timing
分层里（Macro / Micro / State Wait 三层 + transaction 原子性），**不需要**新建类或运行时
强制。

---

## 14. Timing Ownership Inventory（本轮核心产物）

| Timing 机制 | Owner | 目的 | Scale | 是否 sleep | 能否与 `confirm_delay` 同时作用 |
|---|---|---|---|---|---|
| `time.sleep(常量)` | Task | 固定动画等待 / 步骤节奏（`open_expect_level` `sleep(1)`、`fill_shikigami` `sleep(0.5)`） | micro~macro | 是 | 能（不同调用点），职责不同 |
| `random_delay(a,b)` + `sleep` | Task | 业务步骤间随机节奏（RyouToppa 多处） | micro~macro | 是（调用方 sleep） | 能，职责不同 |
| **`confirm_delay`** | `appear_then_click` | **可识别 Point 单击的 reaction pause + 二次确认 + 重定位** | micro（单 Action 内） | 是 | —— |
| `interval`（`Timer` 门控） | `appear` / `appear_then_click` / `click` / `swipe` | 同目标两次动作最小间隔（click / retry throttle） | micro（跨轮次） | 否 | 能（顺序叠加，见 §10） |
| `Timer(n)`（显式） | Task / Navigator / GeneralBattle | 业务操作总超时 / 循环上界（`goto_page` `Timer(30)`、Kekkai `Timer(120)`、Exploration `fire()` `Timer(10)`） | macro（一整段迁移） | 否 | 能，正交 |
| `wait_until_appear(wait_time=)` | BaseTask | 语义等待「某标识出现」，可选 timeout | micro~macro | 每轮 `screenshot` 循环 | 互斥用途——见 §19 |
| `wait_until_disappear` | BaseTask | 语义等待「某标识消失」（无 timeout） | 同上 | 同上 | 同上 |
| `wait_for_changed_and_stable`（`frame_wait`） | `module/base/frame_wait.py` | 视觉结构等待「画面变了并稳定」 | micro（swipe 后） | 注入 sleeper | 不同用途（D012/D013） |
| Retry throttle（`interval` in poll loop / `list_find` 翻页 `sleep`） | Task | 重试之间的间隔 | micro | 部分 | 见 §20 |
| `PREPARE_CLICK_DELAY_RANGE` | GeneralBattle | 准备页点击前延迟（`Timer.limit`） | micro | 否（`Timer`） | GeneralBattle 内不叠 `confirm_delay`（§18） |
| `SETTLEMENT_CLICK_INTERVAL_RANGE` | GeneralBattle | 结算 RD 重复点击间隔（`Timer.limit`，每次重采） | micro | 否 | 同上 |
| Fatigue idle | `FatigueManager` | 拟人短暂走神（15~120s） | **macro**（task-cycle 安全节点） | 是 | 时间线分离，不叠（§12） |
| Fatigue rest | `FatigueManager` | 拟人长休息 + cooldown | **macro** | 是 | 同上 |
| minitouch dwell / `insert_swipe` 尾部 `wait(140)` | 输入后端 | 触摸协议时序 | 输入执行细节 | 是 | **不是业务 reaction timing**，不在本盘点的 owner 讨论范围（D002） |
| 截图间隔 `Timer(0.1)` | `module/device/screenshot.py` | 截图频率下限 | 输入执行细节 | 否 | D002 稳定性基础，不动 |

---

## 15. Timing 冲突 Register

| 位置 | Timing A | Timing B | 是否同一职责 | 风险 / 结论 |
|---|---|---|---|---|
| 任意 `appear_then_click(I_X, interval=N, confirm_delay=(lo,hi))`（**当前无此调用**） | `interval`（throttle） | `confirm_delay`（reaction） | 否 | 顺序叠加，都增加延迟；语义不冲突。**当前零发生。** |
| GeneralBattle `_handle_reward` | `appear_then_click(I_OVER_GHOST, interval=0.8)` | 之后 `_settlement_click` 的 `SETTLEMENT_CLICK_INTERVAL_RANGE` timer | 否（一个是关弹窗节流，一个是结算 RD 节奏） | 无冲突；**若未来给这里加 `confirm_delay` 会与 0.8s interval 叠**——不要加（§18） |
| RyouToppa 主循环 | `try_fatigue_break`（macro idle/rest） | `attack_area` 内部的 `time.sleep` / `random_delay` 业务节奏 | 否 | 时间线分离（break 在 cycle 边界）；无冲突 |
| Exploration `fire()` | `Timer(10)` 总超时 + `max_tries=4` | 每轮 `appear_then_click(button, interval=0.8)` 的 `interval` | 否（一个总预算，一个单次 throttle） | 无冲突；**若给 `button` 加 `confirm_delay`，per-attempt 会多 sleep，吃 `Timer(10)` 预算**（§23） |
| `list_find` 翻页 | `sleep(random.uniform(0.8,1.3))`（普通 `random`，非 `random_delay`） | 无 | —— | 已知瑕疵（D013，翻页等待重构时一起处理），与本轮无关 |

**没有发现「同一业务等待目的被两套机制重复实现」的现存实例**——因为 `confirm_delay` 零
消费者，reaction timing 这一层目前是空的。风险全部是「未来若草率启用」的假设性冲突。

---

## 16. Kekkai `harvest_card` 专项

`tasks/KekkaiActivation/script_task.py`（源码逐字）：

```python
def harvest_card(self):
    self.appear_then_click(self.I_A_HARVEST_EXP)
    self.appear_then_click(self.I_A_HARVEST_FISH4)
    self.appear_then_click(self.I_A_HARVEST_KAIKO_4)
    self.appear_then_click(self.I_A_HARVEST_KAIKO_3)
    self.appear_then_click(self.I_A_HARVEST_KAIKO_6)
    self.appear_then_click(self.I_A_HARVEST_FISH_6)
    self.appear_then_click(self.I_A_HARVEST_MOON_3)
    self.appear_then_click(self.I_A_HARVEST_FISH_3)
```

- **8 处全部没传 `confirm_delay`**（也没 `interval`）。
- **当前一帧连续判断**：`harvest_card` 内部没有 `self.screenshot()`——8 次 `appear_then_click`
  全部跑在**同一帧**（`self.device.image` = 调用 `harvest_card` 前那次截图）。已由
  `tests/test_kekkai_activation_state.py` 锁定（`screenshot` 从不调用、8 步纯线性）。
- **如果以后给每个 `appear_then_click` 加 `confirm_delay`**：
  - 每处会各自 `sleep` + `self.screenshot()` + 二次 `appear` → **自然获得 fresh frame**
    （§2.B 的 ⑤⑥）。即 `confirm_delay` 顺带解决了「8 连点共用一帧」的问题。
  - 但会串行叠加 8 段 sleep。
- **是否应该先解决 semantic verify 再考虑 reaction timing？——是。** `harvest_card` 的真正
  缺口是「8 连点无截图 / 无验证 / 无 reward 闭环」（`docs/Kekkai状态机静态收口.md` §5，
  Level C / T4-4）。reaction timing 只是副作用式地引入 fresh frame，不解决「点完到底收没
  收到」。正确顺序：先做 State→Action→Verify 局部落地（每步之间 `screenshot` + 确认卡片
  消失 / reward 出现），reaction timing 是那之后的可选增强。

**本轮不修。**

---

## 17. RealmRaid 专项

### `partition` 点击（`self.click(click, interval=2)`，`click = self.partition[order-1]`）

- `partition` = `C_PARTITION_1..9`，**静态 `RuleClick`**（固定 ROI）。
- 目标序号来自 `find_one` → `order_medal.find_anyone` 的**外部识别结果**，但点的是**九宫格
  固定区中心**，不是识别到的勋章位置（`docs/RealmRaid状态机静态收口.md` R-R12）。
- **不适合机械迁移到 `appear_then_click`**：没有可 `appear()` 的图像 target；
  `appear_then_click(C_PARTITION_n)` 无意义（`RuleClick` 无模板）。若要「点前确认」，正确
  形态是「`confirm_delay` 后重新 `find_one` / `find_anyone`」——即 Dynamic Search Result 类
  （§9），属 Task 私有 bounded retry，不是本 API。

### `I_FIRE`（`self.appear_then_click(self.I_FIRE, interval=1)`）

- **是最典型的 Image Point Target**：`RuleImage` 按钮、可重新识别、进攻按钮语义清晰。
- 当前真实参数：`interval=1`，**无 `confirm_delay`**（`test_realm_raid_state` +
  `test_general_battle_timing.py::test_realm_raid_fire_keeps_original_timing_arguments`
  双重锁定 `self.appear_then_click(self.I_FIRE, interval=1)` + `self.click(click,
  interval=2)` + `assertNotIn('confirm_delay')` + `assertNotIn('reaction_delay')`）。
- **未来若给 `I_FIRE` 加 `confirm_delay`**，与 RealmRaid Level C 迁移的交互：
  - RealmRaid `fire()` 是 `while True` 无 `max_attempts`、无 total timeout（R-R1/R-R2）。
    `confirm_delay` 在这个无界循环里 = 每轮多一次 `sleep` + `screenshot`——**在 R-R1 判定
    改造（加正向战斗页确认 + timeout）之前加 `confirm_delay` 没有意义**：循环本身还没有
    收敛保证。
  - 正确顺序：先按 Exploration `fire()` 形状给 RealmRaid `fire()` 做 bounded retry（正向
    确认 + `max_tries` + `Timer`），`confirm_delay` 作为「每个 attempt 内、点 `I_FIRE`
    之前的 reaction pause」是那之后的细化。
  - `max_attempts` / `total timeout` 与 `confirm_delay` 正交：前两者约束「点几次 / 多久」，
    `confirm_delay` 约束「每次点之前停多久 + 是否重新确认」。

**本轮不修。**

---

## 18. GeneralBattle 专项（只读）

`grep` `general_battle.py`：

| 环节 | 走什么 | 时序机制 |
|---|---|---|
| 准备页 `I_PREPARE_HIGHLIGHT` | `appear_then_click(self.I_PREPARE_HIGHLIGHT, interval=0.8)` | `interval=0.8` + `prepare_click_timer = Timer(_next_prepare_click_delay())`（`PREPARE_CLICK_DELAY_RANGE`） |
| 关「7 天禁用御魂」等弹窗 | `appear_then_click(I_DISABLE_7DAYS_DIFF_SOUL, interval=0.6)` 等 | `interval` |
| result 结算 `_handle_result` | `self._settlement_click(context)` | **不走 `appear_then_click`**——`_sample_settlement_click(C_RANDOM_RD, _SETTLEMENT_PRIMARY_PROFILE)` 直接 `device.click`，`SETTLEMENT_CLICK_INTERVAL_RANGE` timer 驱动重复 |
| reward `_handle_reward` | `appear_then_click(I_OVER_GHOST, interval=0.8)` + `appear_then_click(I_GB_SKIN_CONFIRM, interval=0.8)` 然后 `_settlement_click` | `interval=0.8` + settlement timer |
| 退出 `I_EXIT` / `I_EXIT_ENSURE` | `appear_then_click(I_EXIT, interval=6)` / `appear_then_click(I_EXIT_ENSURE, interval=0.8)` | `interval` |

- **GeneralBattle 已有独立、成熟、契约化的点击时序**（`PREPARE_CLICK_DELAY_RANGE` /
  `SETTLEMENT_CLICK_INTERVAL_RANGE`，每次 `random_delay` 重采，契约 v2）。
- `test_general_battle_timing.py:256` 断言 `RealmRaid.fire` 源码 `assertNotIn('confirm_delay')`；
  `test_general_battle_settlement` 断言 `_settlement_click` 源码不含 v1 token。
- **未来禁止**在 GeneralBattle 任何 handler 上加 `confirm_delay`——会与 `interval=0.8` /
  `PREPARE_CLICK_DELAY_RANGE` / 结算 timer 形成双层延迟。GeneralBattle 的「点前节奏」owner
  是它自己的契约，不是 `confirm_delay`。

**不修改 GeneralBattle。**

---

## 19. Exploration `fire()` 专项

`tasks/Exploration/base.py:300`：

```python
def fire(self, button) -> bool:
    max_tries = 4
    timeout_timer = Timer(10).start()
    while max_tries > 0 and not timeout_timer.reached():
        self.screenshot()
        cur_page = self.get_current_page()
        if cur_page == pages.page_exp_exit: self.need_exit = False; return True
        if cur_page in (pages.page_battle_prepare, pages.page_battle): return True
        if self.appear_then_click(button, interval=0.8):
            max_tries -= 1
            continue
    return False
```

- **确实用 `appear_then_click`**（`button` = `I_BOSS_BATTLE_BUTTON` 或
  `search_up_fight()` 重定位后的 `I_NORMAL_BATTLE_BUTTON`），`interval=0.8`，**无
  `confirm_delay`**。
- 为什么不用 `confirm_delay`：`fire()` 自己就是一个 **bounded semantic retry**——
  - 每轮 `self.screenshot()` = fresh frame（Action Transaction 的 fresh 步）；
  - `get_current_page()` 正向确认战斗页 = semantic verify（比 `confirm_delay` 的「二次
    `appear(同一按钮)`」强——它确认的是**状态迁移完成**，不只是「按钮还在」）；
  - `max_tries=4` + `Timer(10)` = retry bound。
  - `confirm_delay` 能提供的「点前重新截图 + 二次确认按钮」，`fire()` 的循环结构已经覆盖
    （下一轮 `screenshot` + `appear_then_click` 内部的 `appear`）。
- `get_fire_button` / `search_up_fight` / runtime `roi_front` 改写：这是 **Dynamic Search
  Result** 类定位——`search_up_fight` 用 `match_all(threshold=0.9)` + 最近距离排序 + 原地
  改写 `I_NORMAL_BATTLE_BUTTON.roi_front`。这类逻辑**不套 `appear_then_click`**，因为
  「delay 后要做的是重新 search（重新 `match_all` + 重新排序），不是重新 `appear(单个固定
  target)`」。

**Exploration `fire()` 证明：不是所有强 Semantic Action 都应该改成 `appear_then_click` +
`confirm_delay`。** 当 Action 需要「正向状态确认」而非「同一按钮二次确认」，或需要「重新
搜索」而非「重新识别单目标」时，正确形态是 Task 层 bounded retry（`fire()` 式），
`confirm_delay` 只适合「目标就是那一个可 `appear()` 的按钮、迁移就是从旧位置到新位置」的
简单情形。

**本轮不修。**

---

## 20. `confirm_delay` 与 Retry throttle 不能混为一谈

- **Retry throttle**（attempt 失败 → 等下一次 retry）：owner 是循环 / 未来 bounded-retry
  primitive；例 `while: appear_then_click(I_X, interval=1)` 的 `interval`、`fire()` 每轮
  `interval=0.8`、`list_find` 翻页 `sleep`。
- **`confirm_delay`**（单次 Action：识别 → 停顿 → 确认 → 点）：owner 是 `appear_then_click`
  自己，作用在「决定要点了之后、点下去之前」。
- 不能把 retry 间隔实现成「给循环体里的 `appear_then_click` 加 `confirm_delay`」——那样
  `confirm_delay` 的语义（reaction + 二次确认）被挪用为循环节流，且每轮多一次 `screenshot`。

---

## 21. T7 ClickSampler 关系

- `confirm_delay` 只影响 **when**（何时点）；`ClickSampler` / `ClickProfile` 只负责
  **where**（点 ROI 内哪个像素）。二者已解耦。
- **当前顺序（正确）**：`confirm_delay` 路径 ⑤ `screenshot` → ⑥ `appear`（更新
  `roi_front`）→ ⑦ `target.coord()` = `ClickSampler.sample(roi_front)`。
  **采样发生在 fresh + relocate 之后**，用的是新 `roi_front`。
- **不存在**「`ClickSampler` 先生成坐标 → 等 1 秒 → 用旧坐标」的反模式——`appear_then_click`
  两条路径都是「先定位再采样再点」，`coord()` 从不提前于 `sleep` 调用。
- 未来正确顺序契约（已满足）：`initial detect → confirm_delay → fresh locate →
  ClickSampler.sample → click`。

---

## 22. D001 是否继续成立

**继续成立（YES）。**

- D001：`confirm_delay` 默认 `None`、按调用点显式 opt-in、不给 `RealmRaid.fire` /
  `GeneralBattle` / `RyouToppa` FIRE 自动套用。
- **无任何新证据支持全局默认**：
  - 短生命周期 Transitional Button：`confirm_delay` 的 sleep 会让二次 `appear` 落空 → 漏点。
  - Repeated Poll Click：循环已是节流 + 重试，加 `confirm_delay` = 重复 timing。
  - Static Region（`C_AREA_*` / 九宫格）：无图像 target，硬套无意义。
  - GeneralBattle：已有 `PREPARE_CLICK_DELAY_RANGE` / `SETTLEMENT_CLICK_INTERVAL_RANGE`。
  - 现有 FSM handler / Navigator：已有可靠 `Timer` + 每轮重判。
- **新增一条支持 D001 的观察**：能力上线约一周（commit `880cd21f`，2026-08-28），
  **至今零生产 opt-in**——说明没有「必须全局」的实际压力，逐点评估是对的。
- D002（稳定性基础层不因随机化修改）、D008（不重新加入 `reaction_delay` /
  `CLICK_REACTION_DELAY` / BaseTask 全局自动等待）与 D001 相互印证。

**建议把 D001 从「默认不启用」扩写为「`confirm_delay` = 可识别 Point Action 的官方
reaction-timing 机制，逐调用点显式 opt-in，参数由调用方给，不新增第二个同义 API」**——
见 §26。

---

## 23. D015 是否继续成立

**继续成立（YES），且 `confirm_delay` 与 D015 一致。**

- D015 四类职责（Verify / Wait / Retry / Recovery）owner 分离。`confirm_delay` 落在
  「单次 Action 内的 micro reaction + 就地二次 Verify」，不越界到 Retry（循环）/ Recovery
  （Task）/ semantic Wait（`wait_until_*`）。
- D015 未来 bounded-retry primitive 硬约束：`confirm_delay` 恰好是「单个 attempt」维度的
  一个合规缩影——
  - #3「不 screenshot——verify/action callback 自己截图」：`confirm_delay` 路径**自己**
    `self.screenshot()` 再 `appear`，符合「防 Action 后 Verify 读旧帧」。
  - #2「不缓存业务 target 坐标，每次 attempt 重新定位」：`confirm_delay` 的 `coord()` 在
    二次 `appear` 之后算，符合。
  - #4「不做 recovery」：`confirm_delay` 目标消失只 `return False`，recovery 交调用方。
- 因此未来若抽 bounded-retry primitive，`confirm_delay` 可以作为「attempt 内 reaction +
  fresh revalidate」那一小步的现成实现参考，不冲突。

---

## 24. Point Action Candidate Tiers（本轮只给候选，不改生产）

| Tier | 判据 | Caller 举例 | Current timing | 备注 |
|---|---|---|---|---|
| **Tier 1**（非常适合未来显式 `confirm_delay`） | `RuleImage` 按钮 / 明确可重新识别 / 点击安全区清楚 / 非短生命周期 / 非 poll 循环 | `RealmRaid.I_FIRE`（需先做 R-R1 bounded 改造）、探索 `I_BOSS_BATTLE_BUTTON`、各任务「进入某页」的确认按钮（`I_UI_CONFIRM` 类，非弹窗关闭） | `interval` only | 参数待 Level C / manual data 标定 |
| **Tier 2**（Level C 后再启用） | 目标较小（`short_side < 40`）/ 位置有动画漂移 / 需与 T7 `strict`·`small` profile 配套 | 小图标类确认按钮、`RyouToppa.C_AREA_1`（已是 T7 Point opt-in，reaction timing 是下一层） | `LEGACY` / T7 HABIT | 时间 + 空间都要更保守 |
| **Tier 3**（不适合） | Static Region / Settlement Region / Dynamic Search Result / Transitional Button / Poll Click / Navigation / Swipe·Drag | `C_PARTITION_*`、`C_RANDOM_RD`、`find_anyone` 结果、`I_EXIT(interval=6)`、`ui_click_until_*`、`goto_page`、所有 `RuleSwipe` | 各自既有 | §9 已逐条说明原因 |

---

## 25. BehaviorTrace 是否需要记录 reaction timing

当前 `ACTION` extra 已有最终 `x/y` / `elapsed_ms`（D004：克制，不记录 `appear()`）。

- **不建议**为 `confirm_delay` 单独加 `REACTION` 事件（零消费者，且每次点一条太吵，违背
  D004）。
- **可选**（未来、非本轮）：`confirm_delay` 实际启用后，在 `ACTION` extra 里加一个
  `reaction_ms` 字段（只在走了 confirm 路径时有值），供分析「reaction 分布是否像人」。
  这与 D015「BehaviorTrace 下一个事件是 `RETRY`」不冲突（`reaction_ms` 是 `ACTION` 的
  附加字段，不是新事件）。
- **本轮不改 BehaviorTrace。**

---

## 26. 是否需要新的 `reaction_delay` API

**否（NO）。**

- `confirm_delay` **已经是** reaction timing primitive，且实现正确（fresh screenshot + 二次
  `appear` + 重新 `coord`）。
- 再起 `reaction_delay` = 「两个名字不同但做同一件事」，正是 §26 要避免、也是 D008 明令
  禁止的（`reaction_delay` / `CLICK_REACTION_DELAY` 已有前科被删）。
- **推荐 Option A**：正式定义
  > `confirm_delay` = identifiable Point Action 的 reaction timing（识别后停顿 + 二次确认 +
  > 重定位），逐调用点显式 opt-in。
  不新增 `reaction_delay`；不改默认值；参数由调用方给。

---

## 27. 是否需要修改 `appear_then_click`

**本轮不改；且评估结论是「基本无需改」。**

| 候选 | 评估 |
|---|---|
| **Candidate 1：保持现状** | **推荐。** confirm 路径已满足 Fresh Frame + Relocation；默认路径零消费者影响、保持向后兼容。 |
| Candidate 2：`confirm_delay` 后强制 fresh screenshot + re-appear + re-coord | **已经是这样**（§2.B ⑤⑥⑦）——无需改。 |
| Candidate 3：加 `confirm=True` / `relocate=True` 开关 | 不必——`confirm_delay is not None` 就是那个开关；再加布尔参数是配置矩阵膨胀。 |
| Candidate 4：其它最小方案 | 唯一可考虑的极小项（**非本轮**）：给 `confirm_delay` 加 tuple 形状校验（当前非 2 元组会在 `random_delay(*confirm_delay)` 处 `TypeError`，报错位置略隐晦）。零消费者时收益极低，留待首个 opt-in 时随手做。 |

---

## 28. 全局默认 vs 显式 opt-in

**维持显式 opt-in（D001）。** 见 §22。四案例 + 本轮盘点均无反例。

**D001 经本轮继续成立**，并建议扩写其「决定」条目（§26 的正式定义）。

---

## 29. Production Impact

**0。** 本轮纯静态审查。未改 `appear_then_click` / `confirm_delay` / `random_delay` /
FatigueManager / `frame_wait` / retry / `ClickSampler` / RealmRaid / Exploration / Kekkai /
GeneralBattle / 任何默认 timing。未新增测试（`tests/test_base_task_confirm_click.py` 5 用例
已充分）。完整回归 `741/741 OK`（未变）。

---

## 30. 下一步推荐（唯一）

**把 `confirm_delay` 的长期职责写进 D001（扩写，不新增 ADR）+ 在 `ARCHITECTURE.md` 建立
Macro / Micro / State Wait 三层 timing ownership 边界 + Action Transaction 原子性描述**，
然后**停在这里**——不加任何 opt-in。首个真实 opt-in 等 Level C：拿 RealmRaid `fire()` 的
bounded 改造（R-R1，按 Exploration `fire()` 形状）做载体，那时 `I_FIRE` 的
`confirm_delay` 参数用 manual click / BehaviorTrace 数据标定，作为「attempt 内 reaction
pause」接入。

---

## 31. 成功标准对照（§37 十六问）

1. **`appear_then_click` 是否真的执行「二次确认」？** 传 `confirm_delay` 时**是**（sleep 后
   重新 `screenshot` + 再 `appear`，目标没了不点）；不传时**否**（当帧命中即点）。
2. **`confirm_delay` 后有没有 fresh frame？** 有（`self.screenshot()`）。
3. **delay 后有没有重新定位 target？** 有——二次 `appear` 更新 `RuleImage.roi_front`，
   `coord()` 用新值（`action=` 分支点静态 `RuleClick` 除外，设计如此）。
4. **哪些 Point Action 可以统一使用它？** Tier 1（Image Point Target，非短命/非 poll/非
   static），逐点 opt-in；见 §24。
5. **哪些 Action 永远不应该走它？** Static Region / Settlement Region / Dynamic Search
   Result / Swipe·Drag / Navigation / 现有 FSM handler / 短生命周期按钮 / poll 循环；见 §9。
6. **是否还需要新增 `reaction_delay`？** 否（§26）。
7. **`confirm_delay` 和 `interval` 是否会重复？** 不同职责（reaction vs throttle），顺序
   叠加、都增加延迟；当前无调用点同时使用。
8. **`confirm_delay` 和已有 `random_delay` 是否会重复？** `confirm_delay` 内部就是
   `sleep(random_delay(*confirm_delay))`；与其它 `random_delay` 用途（task pacing / cooldown
   jitter / 概率采样）职责不同，不重复。
9. **Fatigue 是否可能插入 Action transaction？** 当前**不会**——`try_break` 只在调用方
   显式 `safe=True` 的 task-cycle 安全节点（仅 RyouToppa），不在任何 Action 内。
10. **Fatigue break 后是否必须完整重新识别 State？** 当前**由调用方约定保证**（RyouToppa
    `continue` 回循环顶重判；`try_break` 自己不 screenshot）。建议写成明文架构约束。
11. **Retry 的每个 attempt 是否应该重新经历 reaction timing？** 是——每个 attempt 是独立
    Action Transaction（Exploration `fire()` 已是此形态：每轮重新 `screenshot` +
    `appear_then_click`）。
12. **T7 ClickSampler 应在 delay 前还是后采样坐标？** **后**——当前实现已是「fresh →
    appear → coord/ClickSampler.sample」，无 stale-coord 风险。
13. **GeneralBattle 是否已有独立 timing，不能再叠 `confirm_delay`？** 是——
    `PREPARE_CLICK_DELAY_RANGE` / `SETTLEMENT_CLICK_INTERVAL_RANGE`，禁止叠加。
14. **D001 是否继续成立？** 是（§22），并建议扩写其决定条目。
15. **D015 是否继续成立？** 是（§23），`confirm_delay` 与其硬约束一致。
16. **下一阶段应改 API 还是只做调用点 opt-in？** 都不做——先固化职责文档（§30），opt-in
    等 Level C 随 RealmRaid `fire()` 改造一起。
