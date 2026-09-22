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
| `tasks/WeeklyPurchase/mall/navbar.py:76` | `pos[0], pos[1]` | 同上（**master 集成：WeeklyPurchase 按项目决定排除，保持直点，不迁移**） |
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

> **master 基线移植说明（2026-09-15，L2-1 前置）**：§9 / §10 原在 synevo 分支 L1 worktree 形成，未提交。L2-1 以 master `a5e2d7e6`（+ 工作区 Settlement v1.2）为基线，把 L1 / L1.2 **公共层**原样移植进来：`module/click_pipeline.py`、`RuleList.last_ocr_hit`、`Control.click_with_backend` / `_dispatch_click` 与全部公共 task 点位；synevo 专属点位（网易原生控件 `netease_account_ui`、MultiAccountEvo）在 master 不存在，小号轮换业务（Login `_app_handle_login` 固定退出点、DailyTrifles `summon_recall`）**刻意不迁**，作为 master 静态白名单里的显式排除项保留直接 `device.click`。下文提到这些点位的地方以此说明为准。

## 9. L1 全局单击管线（2026-09-15，D026）点位变化

L1 新增 `module/click_pipeline.py`，业务用显式语义（Rule 目标 / `ClickBounds` / `ClickRegion` /
`FinalPoint`）经 `execute_single_click` 落到 `Control.click`。**本节不改写 §3 的历史分类**，只记录
本轮哪些点位的「执行方式」变了、坐标分布是否变了。行号为本轮时 synevo 分支位置。

### 9.1 坐标分布改变（1）

| file:line | 之前 | L1 之后 | 说明 |
| --- | --- | --- | --- |
| `tasks/Component/SwitchAccount/netease_account_ui.py:105`（`_click_bounds`） | uiautomator2 原生控件 `(l,t,r,b)` 精确中心 | `ClickBounds((l,t,r-l,b-t), name, native=True)` → `sample_region(roi, None)` | 原生控件 bounds 是真实可点击矩形（`_bounds` 已拒绝空框），改为框内 RULE_FALLBACK 区域采样，**不查任何图片热点**。覆盖账号列表展开 / 选择账号 / 已保存账号登录三处。Level C |

### 9.2 执行方式收口、坐标逐像素不变（显式 `FinalPoint`，原 §3.4 `EXACT_COORDINATE_BLOCKED` 语义保留）

| file:line | 坐标语义 | control_name |
| --- | --- | --- |
| `tasks/Component/Login/service.py:267`（`_app_handle_login`） | 「误入区服设置」固定退出点 `(106, 535)`，无 asset / ROI | `LOGIN_ESCAPE_SERVER_SETTINGS`（原无名） |
| `tasks/ActivityShikigami/activities/rich_man.py:331`（`_enter_boss_fight_by_anchor`） | anchor 中心上移 70px（框外） | `rm_boss_fight_dynamic_enter` |
| `tasks/Component/GeneralBattle/general_battle.py:1384`（`green_mark_name`） | OCR 名字框左上角 +(5, 30)，框外 | OCR 文本 |
| `tasks/GameUi/navigator.py:539`（`_execute_transition` TOWN_FALLBACK） | 模板未识别时的 `roi_front` 中心；旧资源框不是当前帧真实边界，刻意取中心 | `TOWN_FALLBACK_*` |
| `tasks/MultiAccountEvo/script_task.py:139`（`check_then_accept`） | 作者注明的接受按钮「安全控件中心」（synevo 独有） | `I_I_ACCEPT.name`（原无名） |
| `tasks/base_task.py:825`（`list_appear_click`） | `list_find` 结果（图片列表 = 已采样点；文字列表 = OCR 框中心），原 §3.1 `ALREADY_SAMPLED` | 列表名（原无名） |
| `tasks/EvoZone/script_task.py:185`（`check_layer`） | 文字列表 OCR 框中心（`RuleList` 不暴露框体尺寸） | `EVOZONE_LAYER_<层>`（原无名） |

### 9.3 执行方式收口、仍只采样一次（原 §3.1 `ALREADY_SAMPLED`）

| file:line | 变化 |
| --- | --- |
| `tasks/Component/GeneralBattle/general_battle.py:1361`（`green_mark_choose`） | 先选 `C_GREEN_*` 规则，点击时再经管线 `coord()` 一次（固定 RuleClick，采样时刻后移不改分布）；补 control_name |
| `tasks/DailyTrifles/script_task.py:265`（`summon_recall`） | `list[i].coord()` + 无名 `device.click` → `execute_single_click(device, list[i])`；补 control_name |

### 9.4 本轮刻意不动（已等价于 L1 语义，且有源码契约测试 / D017 保护）

GeneralBattle `_sample_settlement_click`（= `ClickRegion`）/ `_click_settlement_point`（= `FinalPoint`）、
`GeneralInvite._detect_select` 与 `MultiAccountEvo._detect_select` 的好友名框 `sample_target`（= `ClickBounds`）、
`RyouToppa._click_toppa_area` `C_AREA_1` 的 `sample_point`、`navigator.py` RuleClick `coord()`、
`KekkaiUtilize.switch_friend_list` `check_image.coord()`（D017）、`BaseTask` 内部 `appear_then_click` /
`click` / `ocr_appear_click` / `wait_until_*` 的 `coord()` 路径。

### 9.5 仍绕过 L1 的已知点位（L1.2 起已全部收口，见 §10；本节保留为当时快照）

- **绕过 `Control`（无 BehaviorTrace）**：`tasks/Hyakkiyakou/slave/hya_device.py:99` 直调 `click_minitouch`、
  `:105` 直调 `click_window_message(fast=True)`（百鬼夜行高速小游戏）。
- **自带随机偏移**：`tasks/Component/GeneralRoom/general_room.py:161`（`check_zones`）在 `L_TEAM_LIST`（OCR 列表）
  中心上 `randint(±5)`——当前是单次随机；若该列表改为图片模式会叠加 `coord()` 变成 double randomization。
- **其余直接 `device.click`**（§3.4 语义不变，未进管线）：Chess、QuickLoadout ×4、WeeklyTrifles ×2、
  WantedQuests、SixRealms、Secret、Dokan ×2、EternitySea、FallenSun、Orochi、WeeklyPurchase、SwitchSoul。

## 10. L1.2 Global Click Migration（2026-09-15，D026 补记）重新审计与收口

> **2026-09-21 Stage 3B 更新**：下文「项目排除」的 WeeklyPurchase navbar（L1M-038）、Login、DailyTrifles 三处直接单击已以 `FinalPoint` 迁入 `execute_single_click`（只统一执行入口，不改落点；Login 固定坐标 (106, 535) 仍无 ROI 证据，不随机化），并由全局静态守卫锁定（见 `docs/AI_CONTEXT.md` §4.86）。

> **2026-09-21 Stage 2 更新**：下文所述「仍直接 `device.click` 的 canonical 路径」已全部迁入 `execute_single_click`（采样原位保留），白名单现只剩执行器自身与项目排除项（见 `docs/AI_CONTEXT.md` §4.84）。

本轮开始时重新全仓 AST 扫描（`module/` + `tasks/`，不含测试 / dev_tools）：业务层直接单击入口
**40** 处 = 直接 `device.click` 38 + 直调后端 2（Hyakkiyakou）。收口后：业务绕过 **0**；仍直接调
`device.click` 的 18 处全部是已合规 canonical 路径（测试白名单锁定）；`click_minitouch` /
`click_window_message` 只在 `module/device/` 内出现。分类：A = 已由 Rule / 采样器得到的点；B = 业务算好
的精确点；C = 图片目标却直点坐标；D = 动态 / OCR / 原生 bounds；E = 本地随机；F = 直调后端。
「分布」列：**变** = 需 Level C 看落点，**同** = 逐像素不变。行号为本轮收口后位置。

### 10.1 迁移点位（22）

| ID | file:line（函数） | 类 | 旧语义 | 新语义 | 分布 |
| --- | --- | --- | --- | --- | --- |
| L1M-010 | `tasks/Chess/runtime/hand_operations.py:1058`（`discover_souls_from_hand`） | D | 卡名 OCR 框中心直点 | `ClickBounds(卡名 OCR 框, CHESS_DISCOVER_CARD)` | 变 |
| L1M-014 | `tasks/Component/GeneralRoom/general_room.py:165`（`check_zones`） | E | OCR 中心 + `randint(±5)`，无名 | `list_click_target` → `ClickBounds(OCR 框, GR_ZONE_<名>)`；图片列表 → `FinalPoint` | 变 |
| L1M-015~018 | `tasks/Component/QuickLoadout/quick_loadout.py:331 / 344 / 388 / 402` | B | 面板锚点 + 布局常量交点 | `FinalPoint`（无识别到的按钮框，不随机） | 同 |
| L1M-019 | `tasks/Component/SwitchSoul/switch_soul.py:284`（`ocr_appear_click_by_rule`） | A | 按钮列 `action.coord()` x × 队名 OCR `coord()` y | `FinalPoint(x, y1)`（两轴各已采样一次） | 同 |
| L1M-020 | `tasks/Dokan/page.py:26`（`map_enter_dokan`） | B | OCR 框中心 x、框上方 20px | `FinalPoint`（框外业务偏移） | 同 |
| L1M-021 | `tasks/Dokan/script_task.py:379`（`find_challengeable`） | C | 赏金图标匹配框**左上角**，无名 | `ClickBounds(匹配框, I_RIGHTPAD_POINT_BOUNTY.name)`，与正常路径同身份 | 变 |
| L1M-022 | `tasks/EternitySea/script_task.py:247`（`check_layer`） | D | 文字列表 OCR 中心，无名 | `list_click_target` → `ClickBounds`，`ETERNITY_SEA_LAYER_<层>` | 变 |
| L1M-023 | `tasks/FallenSun/script_task.py:87`（`check_layer`） | D | 同上，无名 | 同上，`FALLEN_SUN_LAYER_<层>` | 变 |
| L1M-025~027 | `tasks/Hyakkiyakou/slave/hya_device.py:96 / 105`（`fast_click` 兜底） | F | 无 root_node / 后端 AttributeError 时 `device.click(x, y)` | `FinalPoint` → 标准 `Control.click`，`HYA_BEAN_THROW` | 同 |
| L1M-028 | `tasks/Hyakkiyakou/slave/hya_device.py:102`（minitouch 分支） | F | 直调 `click_minitouch`，无 trace | `backend='minitouch'` → `Control.click_with_backend` | 同 |
| L1M-029 | `tasks/Hyakkiyakou/slave/hya_device.py:102`（window_message 分支） | F | 直调 `click_window_message(fast=True)`，无 trace | `backend='window_message'` → `fast=True` 保留 | 同 |
| L1M-032 | `tasks/Orochi/script_task.py:158`（`check_layer`） | D | 文字列表 OCR 中心 | `list_click_target` → `ClickBounds`，`LAYER_<层>` | 变 |
| L1M-035 | `tasks/SixRealms/common.py:159`（`buy_skill`） | E | 图标中心左移 `randint(35,60)`、上下 `randint(±h/2)` 均匀 | `ClickRegion((cx-60, cy+(-h)//2, 26, h+1), <rule>_buy_left)`，范围 = 旧支撑集 | 变 |
| L1M-037 | `tasks/WantedQuests/script_task.py:251`（`trace_one`） | B | 邀请按钮左上角上方 40px | `FinalPoint`（框外业务偏移） | 同 |
| L1M-038 | `tasks/WeeklyPurchase/mall/navbar.py:78`（`click_and_check`） | A | 图片列表 `list_find` 已采样点 | worktree 里为 `FinalPoint`；**master 集成：项目排除，保持直点**（语义无歧义、不是 double randomization） | 同 |
| L1M-039~040 | `tasks/WeeklyTrifles/script_task.py:231 / 237`（`_broken_amulet`） | B | 文字左边界减勾选框宽度推算的中心 | `FinalPoint`（推算几何，不在推算框内随机） | 同 |

同步升级（上一轮已进管线）：`tasks/base_task.py:823`（`list_appear_click`）与
`tasks/EvoZone/script_task.py:185`（`check_layer`）由「OCR 中心 `FinalPoint`」改为 `list_click_target`
——图片列表仍逐像素不变，**文字列表变为 OCR 框内采样**（Level C）。Hyakkiyakou 行为差异仅为：点击后由
`Control` 统一打日志（原先点击前自打一行）、失效图片批缓存、写 BehaviorTrace；后端与按压时长不变。

### 10.2 保留的直接 `device.click`（18，已合规，`StaticMigrationGuardTest.CANONICAL_DIRECT_CLICKS`）

| ID | file:line（函数） | 类 | 为什么不改 |
| --- | --- | --- | --- |
| L1M-001~004 | `tasks/base_task.py:384 / 393 / 402 / 412`（`appear_then_click`） | A | `target.coord()` / `action.coord()` 紧邻具名单击，就是 canonical 执行器 |
| L1M-005~006 | `tasks/base_task.py:461 / 465`（`wait_until_appear_then_click`） | A | 同上 |
| L1M-007 | `tasks/base_task.py:676`（`click`） | A | `BaseTask.click` 本身 |
| L1M-008 | `tasks/base_task.py:752`（`ocr_appear_click`） | A | `target.coord()`（RuleOcr → sample_target） |
| L1M-009 | `tasks/Chess/runtime/round_state.py:176`（`_refresh_grigri_option`） | A | 每次点击独立 `refresh_rule.coord()` + 具名 |
| L1M-011 | `tasks/Component/GeneralBattle/general_battle.py:646`（`_sample_settlement_click`） | Region | = `ClickRegion`，Settlement v1.2 原语不动 |
| L1M-012 | `tasks/Component/GeneralBattle/general_battle.py:709`（`_click_settlement_point`） | B | = `FinalPoint`（anchor 复用），Settlement 原语不动 |
| L1M-013 | `tasks/Component/GeneralInvite/general_invite.py:592`（`_detect_select`） | D | 好友名 OCR 框 `sample_target` = `ClickBounds`，有源码契约测试 |
| L1M-024 | `tasks/GameUi/navigator.py:351`（`_execute_action`） | A | `RuleClick.coord()` 紧邻具名 |
| L1M-030 | `tasks/KekkaiUtilize/script_task.py:584`（`switch_friend_list`） | A | `check_image.coord()`，D017 保护 |
| L1M-031 | `tasks/MultiAccountEvo/script_task.py:108`（`_detect_select`） | D | 与 GeneralInvite 同一 `sample_target` 写法 |
| L1M-033 | `tasks/RyouToppa/script_task.py:264`（`_click_toppa_area`） | A | `C_AREA_1` 显式 `sample_point` opt-in |
| L1M-034 | `tasks/Secret/script_task.py:275`（`find_battle`） | A | 构造的安全 `RuleClick.coord()` ×2 各一次，有源码契约测试 |
| L1M-036 | `tasks/SixRealms/peacock_kingdom/base_peacock_kingdom.py:77`（`_mark_peacock_boss`） | A | `C_PK_GREEN_MAIN.coord()` 紧邻具名 |

### 10.3 不在 L1 单击范围

长按（`RuleLongClick`）：**Stage 3A（2026-09-21）起统一走独立的 `execute_long_click` → `Control.long_click`**（单击管线仍拒绝长按；落点仍是 `RuleClick.coord()` 一次采样，时长由 `RuleLongClick.duration` 毫秒 / 1000 透传，
不属于本表的空间采样迁移）；Chess `press_and_drag` 直接用 minitouch builder
做按住拖拽（手势，归 Swipe 家族）；`module/device/` 内部后端互调（如 `scroll_window_message`）。
