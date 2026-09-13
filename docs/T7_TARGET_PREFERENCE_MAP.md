# T7-5 全项目点击空间模型覆盖 Inventory

> 生成：2026-09-06（Stage 2 收口）。Stage 1 = 2026-09-04（普通 Point Rule 默认切 preferred）。
> 静态数据源：`grep` + `dev_tools/click_roi_inventory.py`（只读，不启动设备）。
> 本文件是**清单 + 方法 + 状态**。每个入口都有归类；偏离默认路径且**有安全 ROI** 的已迁移，
> **无安全 ROI** 的进 `EXACT_COORDINATE_BLOCKED` 并写明原因。

---

## 1. 最终三类点击

| 类 | 链路 | 入口 |
| --- | --- | --- |
| **A. Point Target** | `target → TargetPreference（EMPIRICAL 优先；未标定 → RULE_FALLBACK=(0.58,0.59)+default_point）→ resolve_profile → 写 anchor → adapt_point_profile(runtime ROI, 24/96 smoothstep；内部复用 adapt_preferred_by_size，并继续收缩 sigma/tail) → ClickSampler.sample(HABIT) → Core/Medium 高斯 + Uniform Tail → Safe ROI → (x,y)` | `ClickSampler.sample_target(roi, name)`（`Rule*.coord()` 默认）/ `ClickSampler.sample_point(roi, profile)`（逐调用点显式 opt-in，仅 `RyouToppa.C_AREA_1`） |
| **B. Region Target** | 业务先选 region（`GeneralBattle._select_reward_region`：marker→DEFAULT，否则 80% SAVE_RIGHT / 20% SAVE_BOTTOM）→ `选定 region → TargetPreference（EMPIRICAL 优先；未标定 → RULE_FALLBACK=(0.58,0.59)+default_region）→ adapt_preferred_by_size(runtime ROI, 24/96 smoothstep) → 只替换 preferred，不改 Region sigma/weights/tail → ClickSampler.sample(HABIT) → Safe ROI → (x,y)` | `ClickSampler.sample_region(roi, name)` |
| **C. Exact Coordinate** | 无安全 ROI，坐标语义就是「必须点这个精确像素 / 检测中心 / 有意固定 fallback 点」→ 直接 `device.click(x, y)` | 见 §4 `EXACT_COORDINATE_BLOCKED` |

**一次点击只做一次空间采样**：`sample_target` / `sample_region` / `sample_point` 内部各恰调
`ClickSampler.sample` 一次；`Control` / 后端不再偏移。double-sampling 审计 = **0**（§5）。

---

## 2. Point Rule（Stage 1，未变）

`RuleClick` / `RuleImage` / `RuleGif` / `RuleOcr` / `RuleLongClick` 的 `coord()`（+ `coord_more()`）
= `ClickSampler.sample_target(roi, rule.name)`。`RuleLongClick` **无 `coord` override**，经
`RuleClick.coord` 继承（Stage 2 确认，测试锁 `RuleLongClickTest`）；长按时长属时间模型，
与空间模型分离。静态可点击 ROI 定义 **~2684**（RuleImage 2077 / RuleClick 300 / RuleOcr 297 /
RuleLongClick 10），全部 = `PREFERRED_POINT`；registry 命中 1 项（`area_1` EMPIRICAL），其余
运行时 `RULE_FALLBACK`。`RuleOcr` FULL 模式浮点 bbox 仍先经 `_normalize_ocr_click_area`
floor/ceil 整数化（`docs/AI_CONTEXT.md` §4.43），再 `sample_target`。

---

## 3. Direct `device.click(...)` Inventory（生产，44 处 + 全部 `.center` / `.front_center()` / 就地 `RuleClick` 消费点重新核对）

### 3.1 `ALREADY_SAMPLED`（18）—— 坐标已由某 `Rule.coord()` / `list_find` 在上游采样，**不改**

| file:line | 上游 |
| --- | --- |
| `tasks/base_task.py:358 / 367 / 376 / 386` | `ocr_appear_click`(confirm_delay 路径) `target.coord()` / `action.coord()` |
| `tasks/base_task.py:435 / 439` | `wait_until_appear_then_click` `target.coord()` |
| `tasks/base_task.py:617` | `BaseTask.click` `x, y = click.coord()`（`RuleClick`/`RuleImage`/`RuleOcr`；`RuleLongClick` 走 `long_click`） |
| `tasks/base_task.py:693` | `ocr_appear_click`(默认路径) `target.coord()` |
| `tasks/base_task.py:750` | `wait_until_*` `x, y = appear`（`list_find` 结果） |
| `tasks/GameUi/navigator.py:350` | `action.coord()` |
| `tasks/Chess/runtime/round_state.py:176` | `refresh_rule.coord()`（`for click_index in 1..2` 两次独立采样） |
| `tasks/Component/SwitchSoul/switch_soul.py:281` | `x` 来自 `action.coord()`、`y1` 来自 `target.coord()`（历史 mix，两者都已采样） |
| `tasks/SixRealms/peacock_kingdom/base_peacock_kingdom.py:77` | `C_PK_GREEN_MAIN.coord()` |
| `tasks/Component/GeneralBattle/general_battle.py:1058` | `C_GREEN_LEFT_N.coord()` / `C_GREEN_MAIN.coord()` |
| `tasks/DailyTrifles/script_task.py:99` | `list[i].coord()` |
| `tasks/RyouToppa/script_task.py:259` | `_click_toppa_area` C_AREA_1：`ClickSampler.sample_point(...)` |
| `tasks/KekkaiUtilize/script_task.py:417` | `check_image.coord()`（`switch_friend_list`；**受 D017 简化保护，只分类不改**） |

### 3.2 `PREFERRED_POINT` —— 本轮迁移（1）

| file:line | 旧 | 新 |
| --- | --- | --- |
| `tasks/Component/GeneralInvite/general_invite.py:426` | `self._random_point_in_area(select_area)`（任务私有整框 `random_point_in_roi`） | `ClickSampler.sample_target(select_area, rule.name)`。`select_area` = `_find_exact_friend_area` 返回的好友名 OCR bbox（整数、真实安全点击 ROI）；`rule.name` = `O_FRIEND_NAME_1/2`（未登记 → RULE_FALLBACK + `default_point`，anchor 再按 bbox short side 适配）。删私有 `_random_point_in_area` staticmethod + `random_point_in_roi` import。 |

### 3.3 `PREFERRED_REGION` —— 本轮迁移（1 个采样点，服务 3 个 region 身份）

| file:line | 旧 | 新 |
| --- | --- | --- |
| `tasks/Component/GeneralBattle/general_battle.py:577`（`_sample_settlement_click`） | `x, y = ClickSampler.sample(rule.roi_front)`（整 ROI `LEGACY_UNIFORM`） | `x, y = ClickSampler.sample_region(rule.roi_front, rule.name)`。`rule` ∈ `{C_RANDOM_DEFAULT / C_RANDOM_SAVE_RIGHT / C_RANDOM_SAVE_BOTTOM}`，`rule.name` ∈ `{random_default / random_save_right / random_save_bottom}` —— registry 显式登记为 `RULE_FALLBACK=(0.58,0.59)` + `default_region`；anchor 按各自 ROI short side 适配，只替换 preferred，不收缩 Region shape。调用方 `_settlement_click`（节流单次）、`_advance_generic_result`（连调两次 = **两次独立采样**）**均未改**。region **选择**（`_select_reward_region` marker→DEFAULT / 80-20）**一字未改**。 |

### 3.4 `EXACT_COORDINATE_BLOCKED` / `DEFER_LEVEL_C`（23）—— 无静态可证安全 ROI，属后续任务 B

| file:line | 点击目标 | 为什么无法安全迁移 |
| --- | --- | --- |
| `tasks/Component/Login/service.py:133` | `x=106, y=535` 硬编码 | 「误入区服设置」的固定返回点，无 asset / ROI；精确像素语义。Level C |
| `tasks/Dokan/page.py:25` | `pos[0]+pos[2]/2, pos[1]-20`（`O_DOKAN_MAP.ocr_full`） | 点在 OCR bbox **上方 20px**（框外），该点无安全 ROI |
| `tasks/Dokan/script_task.py:376` | `x, y = bounty_list[idx]`（bbox 左上角） | 点 bbox 左上角、非中心；语义「点左上显示挑战按钮」。Level C |
| `tasks/WantedQuests/script_task.py:248` | `btn.roi_front[0], btn.roi_front[1]-40` | 点在 rule ROI **上方 40px**（框外） |
| `tasks/ActivityShikigami/activities/rich_man.py:325` | `anchor center, y-70` | 点在 anchor ROI 中心**上移 70px**（框外）dynamic enter |
| `tasks/SixRealms/common.py:156` | `skill_rule.front_center() - randint(35,60)` | 点在 skill icon **左侧 35~60px**（框外）；stdlib `random`（D007「已存在保留」先例） |
| `tasks/Component/QuickLoadout/quick_loadout.py:328 / 341 / 385 / 399` | `panel_x + GROUP_CLICK_X` 等 | 相对动态 panel 的常量偏移点，无独立 ROI，需 panel 几何。Level C |
| `tasks/EternitySea/script_task.py:245` | `pos[0], pos[1]` | 直点检测坐标，无 jitter、无 ROI 证据 |
| `tasks/EvoZone/script_task.py:114` | `pos[0], pos[1]` | 同上 |
| `tasks/FallenSun/script_task.py:85` | `pos[0], pos[1]` | 同上 |
| `tasks/Orochi/script_task.py:146` | `pos[0], pos[1]`（`LAYER_n`） | 同上 |
| `tasks/WeeklyPurchase/mall/navbar.py:76` | `pos[0], pos[1]` | 同上 |
| `tasks/WeeklyTrifles/script_task.py:227 / 232` | `x_50 - width//2, y_check + height//2` 计算中心 | 从 check 区推算的点，无该点安全 ROI |
| `tasks/Chess/runtime/hand_operations.py:1054` | `card['position']` | 卡牌检测坐标直点 |
| `tasks/Component/GeneralBattle/general_battle.py:1079`（`green_mark_name`） | `O_GREEN_MARK_AREA.roi[0] + ret.box[0,0] + 5`, `+30` | 手搓 OCR 角点 + 固定偏移；可迁但 `+5/+30` vs preferred-center 语义需 Level C |
| `tasks/GameUi/navigator.py:536`（`TOWN_FALLBACK`） | `transition.action.roi_front` 中心 | 识别失败后的兜底点；`roi_front` 是失败匹配后的 stale / static 值，**不是被确认过的安全区**，是「按钮大概在这」的猜测 |
| `tasks/Hyakkiyakou/slave/hya_device.py:95 / 102 / 108` | slave 设备 `device.click(x, y)` | Hyakkiyakou 多开从设备特殊输入路径，非主 click 模型 |

### 3.5 `PREFERRED_POINT`（direct，本轮末迁移完成）（1）

| file:line | 旧链 | 新链（2026-09-07 已迁移） |
| --- | --- | --- |
| `tasks/Secret/script_task.py`（`find_battle` 关卡卡片点击，×2） | 就地构造 `click_roi = (card_x+12, card_y+8, 216, LAYER_CARD_HEIGHT-16)` + `RuleClick(...)` → `click_x, click_y = click_rule.center`（几何中心，绕过 `.coord()`）→ `for click_index in 1..2: device.click(同一坐标)` | `click_rule = RuleClick(roi_front=click_roi, ...)` → `for click_index in 1..2: click_x, click_y = click_rule.coord() → ClickSampler.sample_target(click_roi, 'secret_layer_{n}_card')`（未标定 → RULE_FALLBACK `(0.58,0.59)` + `default_point` + `adapt_point_profile` + HABIT）→ `device.click`。**两次点击 = 两次独立 `coord()` / `sample_target` 采样。** `click_roi` 几何、右侧状态文字避让、循环次数、点击间隔、`control_name`（`SECRET_LAYER_{n}_SELECT_{i}`）**一字未改**；仅「坐标从哪里来」变了：`.center` → `.coord()`。测试 `SecretLayerCardMigrationTest`（源码契约 scoped 到 `find_battle` / 构造 RuleClick 路由 `sample_target` / 驱动真实 `find_battle` 验 `coord()` ×2 + `device.click` ×2 + `call_args_list` 逐一对应两次采样 / ROI 几何常量不变）。 |

---

## 4. 生产 `LEGACY_UNIFORM` 剩余（Stage 2 后）

| 位置 | 状态 |
| --- | --- |
| `ClickSampler.sample(roi)` 默认 `strategy=LEGACY_UNIFORM` | **保留**：兼容 / characterization / 显式调用 / `HABIT` fallback（rejection 用尽时的投影不算）。策略常量与 `sample` 方法不删。 |
| `ClickSampler.sample` 内 `random_point_in_roi(roi)`（LEGACY_UNIFORM 分支）/ `random_point_in_roi(_safe_roi(...))`（`UNIFORM` 分支）/ `_sample_mixture` 的 tail `random_point_in_roi(safe)` | **实现细节**，不是消费者。tail 在 Safe ROI 内均匀是 D014 允许的 mixture 成分（§19）。 |
| **生产链上 bare `ClickSampler.sample(roi)` 消费者** | **0**。Stage 1 后所有 `Rule*.coord()` 走 `sample_target`；Stage 2 后 GeneralBattle 结算走 `sample_region`。`grep "ClickSampler.sample(" tasks/` = 0（除 `sample_target`/`sample_point`/`sample_region`）。 |
| `tasks/RyouToppa/script_task.py:254` 注释「区域 2~8 = LEGACY_UNIFORM」 | **已改**：更正为「Stage 1 起 = `sample_target`；D019 起未标定目标 = RULE_FALLBACK」。 |
| `tasks/Component/GeneralBattle/general_battle.py:45` 注释「采样一律整 ROI 均匀 LEGACY_UNIFORM」 | **已改**：更正为「Stage 2 起 = `sample_region`」。 |

**结论**：普通生产 Point / Region 点击**不存在未解释的 whole-ROI Uniform**。

---

## 5. Double-Sampling 审计

| 入口 | `ClickSampler.sample` 调用次数 / 点击 | 结论 |
| --- | --- | --- |
| `sample_target` | 恰 1（`strategy=HABIT`） | OK |
| `sample_region` | 恰 1（`strategy=HABIT`） | OK |
| `sample_point`（RyouToppa C_AREA_1） | 恰 1 | OK |
| `_sample_settlement_click` | 恰 1 `sample_region`（无 `random_int` / `+ random`） | OK |
| `_advance_generic_result` | 两次点击 = 两次独立 `_sample_settlement_click` = 两次独立 `sample_region` | OK（不是「sample once click twice」） |
| GeneralInvite friend select | `sample_target` 一次 → `device.click`，中间无 `randint` / `random.` / `+ random` | OK |
| `ALREADY_SAMPLED` 18 处 | `Rule.coord()` 采样一次 → `device.click(x, y)`，`Control` / 后端不再 jitter（D002/D014） | OK |

**double-sampling consumer = 0。**

---

## 6. TargetPreference Registry 现状

| provenance | 数量 | 条目 |
| --- | --- | --- |
| `EMPIRICAL` | 1 | `area_1`（`RyouToppa.C_AREA_1`，`(0.58,0.59)` + `wide_card`，来源 `manual_click yys1_2026-09-01` cluster_A vs 真实 RuleClick ROI） |
| `SEMANTIC_TRANSFER` | 0 | —— |
| `PROVISIONAL` | 0 | `normal_button` / `large_area` profile 仍在目录里、`provisional=True`、**零 registry 引用、零生产消费者**（`I_FIRE` 3 个不同 asset，无 `runtime_roi_probe` 输出 → 见 §7） |
| `RULE_FALLBACK`（显式登记） | 3 | `random_default` / `random_save_right` / `random_save_bottom` → anchor `(0.58,0.59)` + `default_region`；effective preferred 再按各自 ROI short side 适配 |
| `RULE_FALLBACK`（隐式，resolver 兜底） | 其余全部运行时 target | anchor `(0.58,0.59)` + `default_point`；registry 不为 ~2000 个 target 各写一行规则兜底 |

---

## 7. `normal_button` / `I_FIRE`

- `log/runtime_roi_analysis/` **不存在** —— 无 `runtime_roi_probe` 输出。
- `I_FIRE` 是 3 个不同 asset（`RealmRaid` `(982,494,136,63)` / `AreaBoss` `(1109,490,100,73)` /
  `GeneralInvite` `(1179,602,81,74)`），ROI 各不相同，无单一 runtime bbox。
- manual click `cluster_B`（screen centroid ≈ `(674.9, 392.3)` / 归一化 `(0.527,0.545)`）**没有**
  可靠的 runtime ROI-relative 基准可归一化。
- **结论**：空间模型已统一 —— `I_FIRE` 等战斗按钮走默认 `sample_target` → `RULE_FALLBACK`
  anchor `(0.58,0.59)` + `default_point`，再按运行时 ROI short side 计算 effective preferred。**该 target 的个人 hotspot
  尚未完成 empirical calibration**（缺真实 runtime ROI）。这**不算 Stage 2 代码迁移未完成** ——
  是 Level C calibration 待办（`docs/ROADMAP.md`）。不伪造 empirical 值。

---

## 8. 状态统计

| status | 数量 | 说明 |
| --- | --- | --- |
| `PREFERRED_POINT`（Rule 默认路径） | ~2684 静态 ROI 定义 + 全部动态 / 无字面量 target | Stage 1 |
| `PREFERRED_POINT`（direct 迁移） | 2 | `GeneralInvite` friend-name（§3.3）+ `Secret` 关卡卡片（§3.5，2026-09-07） |
| `PREFERRED_REGION`（direct 迁移） | 1 采样点 / 3 region 身份 | GeneralBattle Settlement V3 selected-region 内采样 |
| `ALREADY_SAMPLED`（direct，不改） | 18 | 坐标上游已采样（含 `Chess`/`SwitchAccount`/`KekkaiActivation` 就地构造的 `RuleClick` 经 `self.click(...)` → `.coord()`） |
| **`PENDING_MIGRATION`（有安全 ROI，未迁移）** | **0** | —— |
| `EXACT_COORDINATE_BLOCKED` / `DEFER_LEVEL_C` | 23 | 无静态可证安全 ROI（检测中心 / 框外偏移点 / 硬编码 / 识别失败兜底猜测点 / slave 设备）→ 后续任务 B |
| `LEGACY_LAZY` | `KekkaiUtilize._reset_utilize_friend_list`（`S_U_END` + 切区双切） | 仅怠惰路径；标准 D017 已简化为 `switch_friend_list` |
| `TEST_ONLY` | `tests/` 内所有 `ClickSampler.sample(` / `random_point_in_roi(` | 特征化 / 兼容测试 |
| `NON_CLICK` | `RuleSwipe.coord`（`random_center_point_in_roi`）/ `TouchSwipeModel` / minitouch trajectory / `Press_and_Drag` 端点（Chess `_rule_center(RuleClick(HAND_AREA))` 是 drag `p2`，不是点击） | 滑动 / 拖拽 / 长按时长，不属点击空间模型（§24） |

**Stage 2 覆盖现状（2026-09-07，收口完成）= IMPLEMENTED**：`sample_region` / `default_region` /
GeneralBattle selected-region 迁移 / `GeneralInvite` 私有 random 迁移 / `Secret` 关卡卡片
`.center → .coord()` 迁移 / `RuleLongClick` / 生产 bare `ClickSampler.sample()` 消费者 **0** /
whole-ROI Uniform production Point·Region **0** / double-sampling **0** —— 全部落地。
重新核对全部 `.center` / `.front_center()` / 就地 `RuleClick(...)` / `device.click(` 消费点：
**`PENDING_MIGRATION`（有可证明安全 ROI 但未迁移）= 0**。剩余 23 处 `EXACT_COORDINATE_BLOCKED`
无静态可证安全 ROI —— 逐条列文件 / 行号 / 原因，属**后续独立任务 B**，不是 Stage 2 blocker。

**后续两个独立持续任务（不阻塞 Stage 2 架构结论）**：
- **A. Empirical Hotspot Calibration**：`I_FIRE` / `normal_button`（无 `runtime_roi_probe` 输出）、
  GeneralBattle 三个 Region（`random_default` / `random_save_right` / `random_save_bottom`）、
  以及其它 target 的 `RULE_FALLBACK → EMPIRICAL` 升级 —— 属 Level C calibration，**不等于代码 /
  架构迁移**；`RULE_FALLBACK` 已进统一 Preferred 模型即视为「空间模型已统一」。
- **B. Exact Coordinate ROI Discovery**：§3.4 的 23 处，只有 Level C / 新证据确认存在安全 ROI
  且改分布不打断业务后才迁移；其中个别「有运行时 bbox 但点角点 / 偏移」的（`Dokan:376` bbox 左上角、
  `green_mark_name` OCR 角点 +5/+30、`QuickLoadout` panel 相对）需真机确认语义。
