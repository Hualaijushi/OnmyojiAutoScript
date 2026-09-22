# 项目架构地图

> 本文档给新接手的 AI 快速建立「项目怎么组成、调用链怎么走」的真实架构认知。
> **不是源码 API 百科**，只记录稳定的分层关系、核心入口与经常被修改的调用链。
> 与源码冲突时以源码为准，并在同一轮修正本文档。
> 更新触发条件见 `docs/AI_CONTEXT.md` §0 表与 §10.1；普通 Bug 修复不需要动本文档。

核对时间：2026-09-01。仓库根：`OnmyojiAutoScript-easy-install`。

---

## 1. 总体分层

```
Script Runtime  (script.py: Script.loop / Script.run)
        │  调度循环、任务加载、异常恢复、疲劳/行为观测生命周期
        ▼
Scheduler / Config  (module/config/*, tasks/*/config*.py)
        │  按 next_run 选下一个任务；pydantic 配置模型；每 config 一个 spawn 进程
        ▼
Task / ScriptTask  (tasks/<TaskName>/script_task.py 的 ScriptTask.run)
        │  单个业务任务的完整流程；以 raise TaskEnd 结束
        ▼
BaseTask / GeneralBattle / GameUi(Navigator)  (tasks/base_task.py, tasks/Component/GeneralBattle/, tasks/GameUi/)
        │  公共识别/点击/等待循环、通用战斗 FSM、页面导航
        ▼
Rule* 原子  (module/atom/: RuleImage / RuleClick / RuleSwipe / RuleOcr / RuleList / ...)
        │  单条识别规则 + coord() 落点生成（RuleSwipe：coord() 旧端点 / sample_endpoints() v2 端点）
        ▼
ClickSampler  (module/click_sampler.py, module/click_profile.py, module/click_preference.py)
        │  ROI → 最终整数点击坐标的唯一公共入口。
        │  滑动端点是**平行的另一层**：SwipeEndpointSampler（module/atom/swipe_endpoint.py，
        │  D022）—— RuleSwipe(roi_front, roi_back) → sample_swipe_endpoints() → 具体整数
        │  起终点（起终点各自独立、主集中高斯 + 少量宽尾、夹到安全范围、联合保方向 / 有效
        │  距离；轴向 ROI >= wide_axis_px 的轴 + 两端两轴都大时逐字保持旧 _center_biased_int）。
        │  BaseTask.swipe 走它；不进 Control / TouchSwipeModel。
        │  **T7-5（2026-09-04，D014 T7-5 段）**：Rule*.coord() 默认 = sample_target(roi,
        │  rule.name) —— resolve_target_preference（click_preference.py 的静态 registry，
        │  按 rule.name 索引；EMPIRICAL 优先，未标定 →
        │  RULE_FALLBACK=(0.58,0.59)+default_point）→ adapt_point_profile（内部复用
        │  adapt_preferred_by_size；point_size_factor smoothstep 连续调 preferred + core/medium
        │  sigma + tail，T7-2/T7-4）→ sample(strategy=HABIT)。一次点击一次空间采样。
        │  LEGACY_UNIFORM（逐字等价 random_point_in_roi）保留但不再是 Point 默认：兼容测试 /
        │  characterization / 显式调用 / fallback。STRICT/UNIFORM + ClickProfile + Safe ROI
        │  已实现。sample_point(roi, base_profile)（逐调用点显式传语义 profile 的薄入口）
        │  与 sample_target 并存，都走 adapt_point_profile + HABIT。
        │  **D019（2026-09-08）**：sample_region(roi, name)（Region Target：业务已选定
        │  region 后，region 内取点；未标定 = RULE_FALLBACK=(0.58,0.59)；只经
        │  adapt_preferred_by_size 做 24/96 preferred 适配，default_region 的 sigma/weights/tail
        │  不做 Point shape 适配）。GeneralBattle 结算 V3（D016）不经 coord()：
        │  _sample_settlement_click 走 sample_region（region 选择 marker/80-20 不变）。
        │  生产 bare sample(roi)=LEGACY_UNIFORM 消费者 = 0。inventory：docs/T7_TARGET_PREFERENCE_MAP.md。
        ▼
Control  (module/device/control.py)
        │  统一 click / long_click / swipe / drag，按 control_method 分发到后端
        ▼
Device Backend  (module/device/method/)
        ├─ minitouch      (minitouch.py)      当前默认控制后端
        ├─ adb            (adb.py)
        ├─ uiautomator2   (uiautomator_2.py)
        ├─ scrcpy         (scrcpy/scrcpy.py)
        └─ window_message (windows_impl.py)
```

旁挂的横切能力（不在主调用链上，被多层调用）：

- **Device / Screenshot**（`module/device/device.py`, `module/device/screenshot.py`）：截图、卡死检测、点击计数保护。
- **Image / OCR 服务**（`module/image/`, `module/ocr/`）：`RuleImage.match` / `RuleOcr.ocr` 走 RPC 客户端。
- **FatigueManager**（`module/fatigue.py`）：疲劳 / 发呆 / 休息，默认关闭，接入 = `RyouToppa` + `Orochi` / `EvoZone` 单人（`run_alone`）+ `RealmRaid` 主循环（§4.56，`_realm_raid_cycle_safe_break`，`deadline=None`）+ `Exploration` solo（§4.58 / D021）+ `ActivityShikigami` 普通爬塔线（§4.62，`NormalClimbAct._activity_challenge_safe_break`：「稳定挑战页 + Challenge Ready」，`deadline=start_time+limit_time_v`，爬塔线 `random_sleep` 由 `_fatigue_owns_macro_idle` 关掉）。
- **BehaviorTrace**（`module/behavior_trace.py`）：只读行为观测日志，默认关闭。`Control.click/long_click` 的 ACTION 带 `extra.x/y`；`swipe` 的 ACTION 带端点，`swipe_trajectory` 再带完整 `extra.trajectory`（一次 swipe = 一个 ACTION）。事件模型仍只有 `TASK` / `ACTION`。
- **点击 / 滑动统计后端**（`module/server/behavior_stats.py` + `stats_router.py` 的 `GET /stats/{script_name}/behavior/clicks`）：按需读 BehaviorTrace JSONL 返回点击散点 + swipe 轨迹，支持 `task` / `interaction_type`（all/click/swipe）/ `target` 过滤，无后台聚合。OASX 前端消费为下一轮独立任务。
- **FrameState Wait Layer**（`module/base/frame_wait.py`）：在 `FrameStateDetector` 上加「注入式取帧 + 轮询 + 有限 timeout」的有限等待，设备无关、可单测，超时返回结构化结果不抛。**生产消费者（2 个，2026-09-08）**：① `KekkaiUtilize._perform_search_swipe`（K3，标准 PASS + minitouch 的 swipe settle）——baseline 取 swipe 前一帧、ROI 限 card-column、阈值 provisional 由业务层显式传、`success=False → PassResult.ABORT`（不当作到底，**结果参与控制流**）；② `BaseTask.list_find` 翻页 settle（T5-2，`docs/DECISIONS.md` D013 补记）——`settle_baseline` 取 swipe 前的 `self.device.image`、ROI = `RuleList.roi_back` 换算、阈值 provisional（模块级 `_LIST_FIND_SETTLE_*`）、**结果丢弃不参与控制流**（W1 结构性 settle，取代固定 `sleep(0.8~1.3)`，`max_swipe` 仍是唯一收敛边界、不新增 BOTTOM / ABORT）。**不因为全仓 swipe 已迁 TouchSwipeModel 就给每个 swipe 自动套 FrameWait。**
- **ManualClickRecorder**（`dev_tools/manual_click_recorder.py`，开发 / 校准工具）：BehaviorTrace 的人工对照——被动监听目标 MuMu 游戏画面内的**人工物理鼠标**左键，换算成 1280×720 逻辑坐标写 `log/manual_click/<config>_<日期>.jsonl`。**只观察、不发送任何输入**，不进生产链；与 `log/behavior/` 数据分离（见 `docs/DECISIONS.md` D014）。配套离线分析器 `dev_tools/manual_click_analyze.py`：对该日志做连续点击 burst-collapse + 重新统计（preferred center / spread / 阈值敏感性 / k-means 三簇），派生结果写 `log/manual_click_analysis/`，原始日志只读不改。再配 `dev_tools/runtime_roi_probe.py`：只读探测某资产（默认 `I_FIRE`）在当前游戏画面 `match()` 后的运行时 `roi_front`，复用生产截屏 + `RuleImage.match()`，不改公共 API、不启动设备。三者都只观察不发送输入（见 `docs/DECISIONS.md` D014）。
- **Reaction Timing profile**（`module/reaction_profile.py`，2026-09-08 新增）：识别到稳定 Point Target 后、点击前的「人为反应延迟」语义 profile —— 只含具名 `(min,max)` 秒区间常量（`REACTION_FAST/NORMAL/NORMAL_HIGH/CONFIRM/NAVIGATION/DELIBERATE`，全部 PROVISIONAL），无函数 / 无 `sleep` / 不依赖 task·device。业务 consumer 在调用点显式传给 `BaseTask.appear_then_click(..., confirm_delay=)`；不在 `RuleImage` / asset 层设默认。与 `click_profile.py`（点击「点哪」）正交：这里管「多久去点」。首批 27 个生产 opt-in 见 §4.51 / `docs/DECISIONS.md` D001 补记。
- **Logger**（`module/logger.py`）：按 `config_name` + 日期分文件的人读日志。

---

## 2. 每层职责

### Script Runtime — `script.py`

- **职责**：`Script.loop` 主调度循环；`Script.run(command)` 用 `load_module` 从 `tasks/<command>/script_task.py` 动态载入 `ScriptTask` 并 `.run()`；`_handle_task_exception` 统一异常恢复（`TaskEnd` / `GameStuckError` / `GamePageUnknownError` / `ScriptError` / `exit(1)`）；进程启动时一次性配置 `FatigueManager` 与 `BehaviorTrace`。
- **不负责**：任务内部页面流程、识别、点击。
- **核心文件**：`script.py`。
- **调用方向**：`loop → get_next_task → run → ScriptTask.run`。

### Scheduler / Config — `module/config/`, `tasks/*/config*.py`

- **职责**：`Config(config_name)` 加载 `config/<name>.json`（pydantic 模型，`ConfigModel`）；`get_next()` 按各任务 `scheduler.next_run` 排序选下一个任务；`task_delay` / `set_next_run` 写回下次运行时间。任务配置模型分散在 `tasks/<Task>/config*.py` 与 `tasks/Script/config_*.py`（`Script.device` / `Script.optimization` / `Script.error` / `Script.anti_ban`）、`tasks/GlobalGame/config.py`（`global_game.fatigue` 等）。
- **不负责**：任务执行、设备控制。
- **核心文件**：`module/config/config.py`, `module/config/config_model.py`, `tasks/Script/config*.py`, `tasks/GlobalGame/config.py`。
- **多实例**：`module/server/script_process.py` 用 `multiprocessing.get_context("spawn")`，**每个 `config_name` 一个独立进程**。

### Task / ScriptTask — `tasks/<TaskName>/script_task.py`

- **职责**：单个业务任务的完整流程（进页面 → 循环识别 → 点击 / 战斗 → 领奖 → `set_next_run` → `raise TaskEnd`）。
- **不负责**：跨任务调度、后端分发。
- **核心文件**：每个任务目录下的 `script_task.py`、`assets.py`（`Rule*` 实例定义）、`config.py`。

### BaseTask — `tasks/base_task.py`

- **职责**：所有任务的公共基类。提供 `screenshot` / `appear` / `appear_then_click` / `click` / `swipe` / `wait_until_appear[_then_click]` / `wait_until_disappear` / `wait_until_stable` / `list_find` / `list_appear_click` / `ocr_appear[_click]` / `ui_click*` 系列循环、`set_next_run` / `custom_next_run`、勾协突发处理（`_burst`）、疲劳安全节点（`begin_fatigue_task` / `try_fatigue_break`）。
- **不负责**：控制后端分发、业务页面语义。
- **核心文件**：`tasks/base_task.py`。
- **约定**：`interval=` 参数是「两次动作最小间隔」的 `Timer` 门控，**不 sleep**；命中即点当帧 `coord()`。`appear_then_click(confirm_delay=...)` 是唯一「等待后重新截图 + 重新生成坐标」的路径，默认 `None`（不启用）。

- **时序职责分层（2026-09-02 `appear_then_click` / `confirm_delay` 专项审查确立，见 `docs/Action点击前反应时序静态审查.md` + `docs/DECISIONS.md` D001）**：
  - **Micro（单个 Action 内）**：`confirm_delay`——可识别 Point Target 单击的 reaction pause + 二次确认 + 重定位（`appear` → `sleep(random_delay)` → `screenshot` → 二次 `appear`（没了不点、返回 False）→ 重新 `coord()` → `device.click`）。owner = `appear_then_click`（primitive 未改，`confirm_delay=None` 默认不变）。语义 profile = **`module/reaction_profile.py`**（新增，与 `click_profile.py` 同层）：具名 `(min,max)` 秒区间常量 `REACTION_FAST/NORMAL/NORMAL_HIGH/CONFIRM/NAVIGATION/DELIBERATE`，全部 PROVISIONAL，由业务 consumer 在调用点显式传 `confirm_delay=`，不在 asset 层设默认。**首批生产 opt-in（2026-09-08，§4.51）= 27 调用点 / RealmRaid·Orochi·EvoZone·RyouToppa·Exploration**（稳定锁定 / 刷新确认 / 组队 / 材料类型 / 导航返回 / 章节确认）；Settlement V3 / `I_PREPARE_HIGHLIGHT` / 瞬态 / 动态 / polling 永不加。**`I_FIRE` 用专属 `REACTION_FIRE=(0.4,0.8)`**（不是 `confirm_delay`）——2026-09-08（§4.52）RealmRaid `fire()` R-R1 收口 + RyouToppa `attack_area` 统一使用，见下方「FIRE Action」链；Orochi / EvoZone 的 `I_*_FIRE` 待下一轮。
  - **Throttle（跨循环轮次）**：`interval` 的 `Timer` 门控 / poll 循环 `interval`。owner = 循环。**不用 `confirm_delay` 实现节流。**（`list_find` 翻页等待 2026-09-08 起是 State Wait / 视觉结构等待，见下。）
  - **State Wait**：`wait_until_appear(wait_time=)` / `wait_until_disappear`（语义）、`wait_for_changed_and_stable`（视觉结构，D012；生产消费者 = K3 + `list_find` 翻页 settle + Exploration 章节 swipe settle）。**不用 `confirm_delay` 替代语义等待。**
  - **Macro（task-cycle 安全节点）**：`FatigueManager` idle / rest，只在调用方显式 `safe=True` 的安全节点（当前 `RyouToppa` + `Orochi` / `EvoZone` 单人 + RealmRaid + Exploration solo + ActivityShikigami 爬塔线）触发；`try_break` 自身不截图 / 不重识别 state（调用方负责）。**不得进入 Action transaction 中途。** 同一 task cycle 只允许一个 macro-idle owner——ActivityShikigami 爬塔线接入后，`prepare_next_action` 的旧 `random_sleep` 由 `_fatigue_owns_macro_idle` gate 关掉（§4.62）。
  - **Action Transaction 原子性**：`State recognized → reaction timing → fresh relocation → Action → Verify` 是一个原子单元；Fatigue 不在其中途插入（当前由构造保证）；每个 Retry attempt 是一个新的 Action Transaction（Exploration `fire()` 已是此形态——每轮重新 `screenshot` + `appear_then_click`）。
  - **GeneralBattle 自有时序契约**（`PREPARE_CLICK_DELAY_RANGE` / `SETTLEMENT_CLICK_INTERVAL_RANGE`，见下）**永不叠加 `confirm_delay`**。
  - 输入执行细节（截图 `Timer(0.1)`、minitouch dwell / `insert_swipe` 尾部 `wait`）不归业务 reaction timing 讨论（D002）。

### GeneralBattle — `tasks/Component/GeneralBattle/general_battle.py`

- **职责**：基于 Page FSM 的通用战斗（`run_general_battle`）。`gb_page_handle_dict` 把 `page_battle_prepare / page_battle / page_battle_result / page_reward` 映射到 handler；每轮 `screenshot` + `detect_page_in` 重新判定当前页。准备点击延迟 / 结算点击间隔通过 `PREPARE_CLICK_DELAY_RANGE` / `SETTLEMENT_CLICK_INTERVAL_RANGE` 类属性控制（子类可覆写，`RealmRaid` 覆写为真实区间）。
- **通用结算推进（Settlement Micro-Burst v1.2，2026-09-14；D016 + D025）**：三个 Large Safe Region `C_RANDOM_DEFAULT` / `C_RANDOM_SAVE_RIGHT` / `C_RANDOM_SAVE_BOTTOM` 与 D019 `ClickSampler.sample_region` 落点策略不变；Reward 仍由 `_select_reward_region()` 按 marker → DEFAULT、否则 80% SAVE_RIGHT / 20% SAVE_BOTTOM 选择 region。Generic Result 与普通 Reward 统一进入同一个 Settlement lifecycle，但每个 semantic state 使用独立的 2~4 click segment（50%/30%/20%）；segment exhaustion 不是 terminal，fresh classify 仍为 result/reward 时才能续段。
  - **`_handle_result` / `_handle_reward`**：通用结果页与无特殊弹窗的普通奖励页调用 `_settlement_burst_step(...)`；更宽的 `I_BATTLE_STATE_INFO`-only 结果页仍走原 `_settlement_click` 单次节流路径。`I_OVER_GHOST` / `I_GB_SKIN_CONFIRM` 点击后立即 `CONTINUE`，保持 Action → Fresh State 边界。
  - **`_settlement_burst_step`**：首次进入建立 lifecycle、anchor 与首段；Result → Reward 采用方案 B，先按新 region 做 anchor keep/resample，再为 Reward 建独立 segment；同一 state 只有在上一段耗尽且本帧 fresh semantic page 仍明确可点击时才 renew。Unknown 不续段，known non-settlement 由主循环或 mid-burst observation 调 `_teardown_settlement_session()`。
  - **`_fire_settlement_burst`**：timer 到点后点第一下；若本次目标为两下，则等待 `0.10~0.30s` → fresh screenshot → 复用 `GameUi.detect_page_in` 语义分类。只有 observed page 与 current page 相同才用同 anchor 点第二下；state advance / Unknown / terminal 分别取消第二下、交回既有 recovery、立即 teardown。第二下之后一律交回外层主循环重新截图分类，保持 Click → Observe → Decide。
  - **anchor 与 segment 解耦**：同 state 续段不换 anchor；state advance 时旧 anchor 不在新 safe ROI 则强制重采样，在新 ROI 内则按 50% keep/resample，且 lifecycle 最多一次主动换点。重新生成 segment 不等于重新生成 anchor。
  - **有界性与作用域**：随机 2~4 只负责局部节奏；`settlement_total_clicks` 达到固定 `SETTLEMENT_MAX_TOTAL_CLICKS=9` 后不再续段或点击，底层 Device click/stuck guard 仍是第二层保护。安全帽耗尽不伪称 semantic terminal；只有 fresh known non-settlement 才销毁 lifecycle。Micro-Burst 多击只属于 GeneralBattle 结算，不是公共 multi-click API，不替代普通按钮的 `appear_then_click` 单击契约。synevo 的 MultiAccount/GeneralInvite/EvoZone 架构均未改。
  - 子类 `_handle_result` / `_handle_reward` 只要最终 `super()` 到基类，就经 guard 后走新策略（RealmRaid 非 quick_exit / HeroTest 非 skill-add / Orochi / EvoZone / EternitySea / ActivityShikigami / BondlingFairyland._handle_reward）；`BondlingFairyland._handle_result` 与 SixRealms `moon_sea` / `peacock_kingdom` 的 `_handle_result` / `_handle_reward` 全私有、不 `super()`、**不被公共双击穿透**（自带 `random_click()`）。`random_click()`（navigation）与 Settlement Policy 分离——SAVE 区域不接入 `random_click`。
- **不负责**：具体任务的进入 / 退出页面（由子类 `_exit_matcher` 或调用方传 `exit_matcher`）。
- **核心文件**：`tasks/Component/GeneralBattle/general_battle.py`, `config_general_battle.py`, `assets.py`。

### GameUi / Navigator — `tasks/GameUi/`

- **职责**：页面图（`page*.py` / `page_definition.py`）+ 导航（`navigator.py` `goto_page`）+ 页面识别（`game_ui.py` `detect_page_in` / `get_current_page` / `match_page_once`）+ 页面 hook（登录、活动栏、战斗接管）。
- **不负责**：单条识别规则、控制后端。
- **核心文件**：`tasks/GameUi/navigator.py`, `game_ui.py`, `page.py`, `default_pages.py`, `matcher.py`。

### Rule\* 原子 — `module/atom/`

- **职责**：单条识别 / 操作规则的封装。
  - `RuleImage`（`image.py`）：模板 / 多尺度 / SIFT 匹配（走 `module/image/rpc.py` 客户端），`coord()` = 匹配命中后在 `roi_front` 内取点（**T7-5：经 `ClickSampler.sample_target(roi, name)`，name = 文件名 stem 大写**）。
  - `RuleClick`（`click.py`）：`coord()` = `roi_front` 内取点（**T7-5：`ClickSampler.sample_target(roi, name)`**，`RuleLongClick` 继承）。
  - `RuleOcr`（`ocr.py`）：OCR（走 `module/ocr/rpc.py`），`coord()` = `ClickSampler.sample_target(_normalize_ocr_click_area(area), name)`。FULL 模式的 `area` = `Full.ocr_full()` 用 OpenCV 检测框写入的浮点 `(x,y,w,h)`，`_normalize_ocr_click_area()`（左/上 `floor`、右/下 `ceil`、贴边裁 1280/720、宽高兜底 ≥1）整数化，`random_point_in_roi` 的整数 ROI 契约不放宽（`docs/AI_CONTEXT.md` §4.43）。**D019（§4.50）**：`sample_target` = 按 `rule.name` 查 `TargetPreference`（EMPIRICAL 优先；未标定 → `RULE_FALLBACK=(0.58,0.59)`+`default_point`）→ `adapt_point_profile` → `HABIT`；普通 Point 点击默认不再整 ROI 均匀。`RuleGif` 同（name 取首个 target 的）。
  - `RuleSwipe`（`swipe.py`）：`__init__(roi_front, roi_back, mode, name)` + 两个端点访问器。`coord()`（旧）= 起点 `roi_front` / 终点 `roi_back` 各用 `random_center_point_in_roi`（**中心偏置**，3 次采样均值，严格 ROI 内）——保留给兼容 / 测试。**`sample_endpoints()`（v2，`BaseTask.swipe` 用）**= `module/atom/swipe_endpoint.py` 的 `sample_swipe_endpoints`：起终点各自独立采、主集中高斯 + 少量宽尾、夹到安全范围、联合保方向 / 有效距离；轴向 ROI `>= wide_axis_px`（48）的轴 + 两端两轴都大时逐字保持旧 `_center_biased_int`（见 `docs/DECISIONS.md` D022）。`trace()` / `is_default_mode` / `is_vector_mode` 早已作死代码删除（D006）。
  - `RuleList`（`list.py`）：列表滚动查找，`swipe_pos()` 生成翻页端点。
  - `RuleAnimate`（`animate.py`）：判断连续两帧目标区域是否稳定（走 image RPC，返回 bool）。
  - `frame_state.py`：**纯 numpy** 的连续帧视觉状态判定——`frame_difference(a, b, roi)` 返回 `[0,1]` 差异分，`FrameStateDetector` 维护 `changed`（相对基线、锁存）/ `stable`（相邻帧连续安静）。不走 RPC、不截图、不 sleep，只处理传入的帧。当前零生产消费者，为「列表状态驱动」改造预留（见 `docs/ROADMAP.md` T4-1、`docs/DECISIONS.md` D010）。设备截图轮询与超时**不在本组件**，由 `module/base/frame_wait.py`（§2 Wait Layer）承担。
- **不负责**：调用时序、后端、设备轮询 / 超时。
- **核心文件**：`module/atom/*.py`, `module/base/utils/random.py`（公共随机：`random_delay` / `random_int` / `random_triangular` / `random_point_in_roi` / `random_center_point_in_roi`，均用一个模块级 `SystemRandom`）。

### Control — `module/device/control.py`

- **职责**：统一 `click(x, y, control_name)` / `long_click` / `swipe(p1, p2, duration, control_name)` / `swipe_trajectory(trajectory, control_name)` / `drag`，读 `config.script.device.control_method` 分发到具体后端。测量 `perf_counter` 耗时并 `logger.info`，随后调 `BehaviorTrace.record('ACTION', ...)`。
- **不负责**：业务页面状态、OCR、任务 retry、坐标生成（坐标由 `Rule*.coord()` 传入）、滑动轨迹形状（`swipe` 的轨迹由后端 `insert_swipe` 生成；`swipe_trajectory` 的轨迹由调用方 `TouchSwipeModel` 传入）。
- **核心文件**：`module/device/control.py`。
- **契约**：见 §4；`swipe_trajectory` 见 `docs/DECISIONS.md` D018（独立 opt-in 入口，不改 `swipe`；非 minitouch 后端 `NotImplementedError`；BehaviorTrace 仍端点级）。

### Device Backend — `module/device/method/`

- **职责**：把一次抽象操作翻译成具体设备协议。
  - `minitouch.py`：`click_minitouch`（DOWN → `wait(_humanized_dwell())` → UP）、`swipe_minitouch(p1, p2)`（`insert_swipe` 生成贝塞尔轨迹，每 MOVE `random_int(6, 15)` ms）、`swipe_minitouch_trajectory(trajectory)`（**执行调用方给的 `[(x,y,dt_ms)]`**——`_ensure_trajectory` 在 `@retry` 外校验 + `@retry _swipe_minitouch_trajectory_run` 逐点 `move.commit.wait(dt)`；不套 `insert_swipe`、不叠加 `random_int(6,15)`，D018）。当前默认后端。
  - `adb.py`：`click_adb` / `swipe_adb(p1, p2, duration)`（系统 `input tap` / `input swipe`，直线）。
  - `uiautomator_2.py`：`swipe_uiautomator2(p1, p2, duration)`。
  - `scrcpy/scrcpy.py`：`swipe_scrcpy(p1, p2)`。
  - `windows_impl.py`：`swipe_window_message(startPos, endPos)`（内联贝塞尔，用 `module/base/cBezier.py`）。
- **不负责**：坐标生成、时序策略（`swipe_minitouch_trajectory` 的路径与逐段 dt 由 `TouchSwipeModel` 决定，不在此层生成）。

### TouchSwipeModel — `module/device/touch_swipe_model.py`

- **职责**：自定义滑动轨迹的「怎么移动」——纯数学生成器 `generate(start, end) -> list[(x, y, dt_ms)]`。minimum-jerk 位置进度 `s(t)=10t³-15t⁴+6t⁵` + 整体曲率 `curve_amp·sin(πt)`（可正可负、幅度有上限、无逐点抖动）+ 时间模型 `base_dt(s) 趋势 + smooth_noise`（第二阶段：逐段 dt 扰动改为一阶低通 / EMA，连续有界零漂移；尾段按已走距离占比加密 MOVE 点 + `smoothstep` 平滑放慢，终点精确、无固定 pre-UP 停顿、无过冲）。`TouchSwipeParams`（frozen）持有可调项，`rng=` 可注入确定性实现（默认走公共 `random_int`）。
- **不负责**：截图 / FrameWait / OCR / ROI / 业务状态 / minitouch socket / BehaviorTrace / 旋转分辨率换算 / pressure。**不 import** `device` / `Config` / `BaseTask`，可脱离设备单测。
- **状态**：**首个生产消费者 = `KekkaiUtilize` 标准 PASS 搜索的列表下划（K1，2026-09-04）** —— `KekkaiUtilize._perform_search_swipe` 在 minitouch 配置下 `TouchSwipeModel().generate(...)` → `Control.swipe_trajectory(..., control_name='KEKKAI_UTILIZE_SWIPE')`；非 minitouch 回退旧 `swipe_adb`；怠惰模式仍走旧 `perform_swipe_action`。**K2（2026-09-07）起 minitouch 路径：commanded 位移改 `random_int(*SWIPE_DISTANCE_RANGE)`（取代固定 416px；Level C 分档 provisional，首档 `(212,265)` 首次实测滚 >4 格 → 已回调 `(140,180)`）+ 轻微整体斜度 `end_x = clamp(start_x + random_int(*SWIPE_LATERAL_OFFSET_RANGE(-12,12)), *SWIPE_START_X_RANGE)`（只作用于最终 `end_x`、不给 MOVE 加噪声、不扩大 `start_x` 范围）——Kekkai 业务层决定「滑多远 / 往哪斜」，`TouchSwipeModel` 未改（仍只调一次、仍只收 start/end）；怠惰 / 非 minitouch 回退仍 416 纯竖直**。D017 契约不动，K1 真机验收 = Level C，K2 需二次 Level C。逐调用点显式 opt-in（不全局替换 `BaseTask.swipe`）。
- **契约**：`docs/DECISIONS.md` D018；可行性审查 `docs/Minitouch自定义轨迹能力审查.md`。

### Device / Screenshot — `module/device/`

- **职责**：`Device` 组合 `Platform / Screenshot / Control / AppControl`。`Screenshot.screenshot` 有固定 `_screenshot_interval = Timer(0.1)` 节流（`limit_in` 限幅），卡死检测（`stuck_timer` 60s / `stuck_timer_long` 300s），点击计数保护（`click_record_check`，同按钮 10 次 / 两按钮各 6 次抛 `GameTooManyClickError`）。
- **核心文件**：`module/device/device.py`, `module/device/screenshot.py`。

### FatigueManager — `module/fatigue.py`

- **职责**：疲劳 / 发呆(idle) / 休息(rest) / 调度空档(scheduler_idle) 模型。按 `config_name` 单例（`get_fatigue_manager`）。`try_break` 在安全节点按 hazard 概率决定是否 `sleep`。
- **状态**：`FatigueConfig.enable` 默认 `False`；当前接入 `BaseTask.begin_fatigue_task` / `try_fatigue_break` 的任务 = `RyouToppa`（每完成一个区域）+ `Orochi` / `EvoZone` 的 `run_alone`（一场战斗完整结束、回到稳定挑战页之后）+ `RealmRaid` 主循环（§4.56 / D020，`_realm_raid_cycle_safe_break`：普通目标 / 退四「一个完整目标业务循环结束、回到个人突破可操作页」处，`deadline=None`——RealmRaid 无墙钟时限，挑战次数由 `number_attack` 限）+ `Exploration` 的 `ALONE` 路径（§4.58 / D021，Boss win → map ready → direct exit → `page_exp_entrance` positive，`deadline=start_time+limit_time`，fatigue 后 fresh revalidate）+ `ActivityShikigami` 普通爬塔线（§4.62，`NormalClimbAct._activity_challenge_safe_break`：稳定挑战页 + Challenge Ready positive → `try_fatigue_break` → 休息后 fresh revalidate 页 / 挑战键 / 资源 OCR；`deadline=start_time+limit_time_v`；旧 `random_sleep` 让位；大富翁 / 伪神降临线不接）。leader / member / wild 路径不接（见 `docs/DECISIONS.md` D001「Fatigue Safe Point 铺开补记」）。
- **不负责**：输入协议时序（截图 interval / minitouch dwell 不归它管）。

### BehaviorTrace — `module/behavior_trace.py`

- **职责**：只读记录 `ACTION`（click/swipe/long_click 完成）与 `TASK`（Script.run episode）到 `log/behavior/<config>_<日期>.jsonl`。按 `config_name` 单例。`Control.click` / `Control.long_click` 的 ACTION 带 `extra={'x','y'}`（`ensure_int` 后的最终执行坐标）；**`swipe` 的 ACTION（2026-09-07）带端点 + `point_count`，`Control.swipe_trajectory` 再带完整 `trajectory=[[x,y,dt],...]`**（一次 swipe = 一个 ACTION，轨迹整体嵌 `extra`，不逐 MOVE 落事件）。`is_recording()` 读访问器供调用方在关闭态跳过大 `extra` 组装。
- **状态**：`config.script.optimization.behavior_trace_enable` 默认 `False`；关闭时 `record()` 首行返回，无 IO。
- **不负责**：改变任何业务行为；不记录 screenshot / OCR / Timer / minitouch 每个 MOVE / retry；swipe 不记 FrameWait 的 `changed/stable`（K3）、不记 actual scroll dy / scroll_gain（K4）。
- **契约**：见 `docs/DECISIONS.md` D004（事件模型 + swipe trajectory 补记）、D011（统计后端）。

### 点击 / 滑动统计后端 — `module/server/behavior_stats.py` + `module/server/stats_router.py`

- **职责**：按需读取某 config 某日期的 BehaviorTrace JSONL，返回 click / long_click 坐标散点 **与 swipe 轨迹** 给 OASX。`read_behavior_clicks(config, date, *, task=None, interaction_type="all", target=None)` 逐行读单文件一次；HTTP `GET /stats/{script_name}/behavior/clicks?date=YYYY-MM-DD[&task=&interaction_type=all|click|swipe&target=]`（FastAPI，挂在既有 `stats_app` 上）。`{script_name}` 是**完整 config_name**（`ConfigManager.validate_config_name` 校验后原样用，不按 `_` 截断——config 名允许含 `_`）。
- **过滤**：`date AND task AND interaction_type AND target` 四层等值 AND，缺省 = 不限；`target` 对 click / swipe 同一语义。响应 additive：旧键（`points` / `tasks` / `summary` 旧计数）不变，新增 `swipes` / `summary.swipe_count` / `available_tasks` / `available_targets` / `filter`。
- **不负责**：后台聚合 / 定时扫描 / 数据库 / SSE / 热力图 / 轨迹平滑 / 轨迹抽稀 / 坐标变换 / OASX 前端。接口未被请求时零后台开销。一条坏 `trajectory` 只降级该条（`summary.malformed_trajectories`），不 500。
- **契约**：见 `docs/DECISIONS.md` D011（+ Swipe Trajectory Backend 补记）、D004 补记。**OASX 前端消费本 schema 是下一轮独立任务（本轮未动前端）。**

### FrameState Wait Layer — `module/base/frame_wait.py`

- **职责**：`wait_for_changed_and_stable(baseline, frame_provider, *, changed_threshold, stable_threshold, stable_frames, timeout, roi=None, pixel_threshold=…, poll_interval=0.0, clock=time.monotonic, sleeper=time.sleep) -> FrameWaitResult`。内部建一个 `FrameStateDetector`，反复调 `frame_provider()` 取帧喂给它，直到「`changed and stable`」成功或 `clock()` 到达 `timeout`。返回 `FrameWaitResult`（`frozen` dataclass：`changed` / `stable` / `timed_out` / `last_difference` / `stable_count` / `frames_checked` / `elapsed` / `success` property）。
- **三层分工**：`FrameStateDetector`（`module/atom/frame_state.py`）只做帧差与状态；本层做取帧 / 轮询 / 计时 / 超时；调用方（未来的 Task）决定 baseline / ROI / 阈值 / `stable_frames` / `timeout` / retry / recovery。
- **不负责**：retry、recovery、失败换动作（那是 T4-3 WaitPolicy / RetryPolicy）；自截 baseline（调用方按 `screenshot()→action()→wait(baseline=)` 传入）；BehaviorTrace 事件。
- **依赖**：仅 `numpy` + `module.atom.frame_state`。`frame_provider` / `clock` / `sleeper` 全部可注入——生产传 `self.device.screenshot`，测试传 fake，无 Device / Timer 硬依赖。放 `module/base/` 与 `retry.py` 同层（控制流基础设施），`base → atom` 单向 import 无环。
- **契约**：超时返回结果不抛异常；成功严格 `changed and stable and not timed_out`；`frame_provider` / detector 抛的异常原样透传（不伪装成 timeout）；`timeout` 必须有限正数，无 `while True` 无界循环（`_MAX_POLLS` 兜底）。详见 `docs/DECISIONS.md` D012。
- **状态**：**生产消费者 2 个（2026-09-08）**：
  - **① `KekkaiUtilize._perform_search_swipe`（2026-09-07 K3，标准 PASS + minitouch 的 swipe settle，取代固定 `time.sleep(2)`）**——业务层传 `SWIPE_WAIT_ROI` + 4 个 provisional 判定阈值（`changed 0.10` / `stable 0.02` / `stable_frames 3` / `timeout 3.0s`）+ 显式 `poll_interval=SWIPE_WAIT_POLL_INTERVAL=0.15`（覆盖全局默认 0.0，检测采样 pacing，避免惯性微滚被误判 stable；非恢复 `sleep(2)`），均注释标「需 Level C 调整」；`wait.success is False → PassResult.ABORT`（**结果参与控制流**，不当作到底）。
  - **② `BaseTask.list_find` 翻页 settle（2026-09-08 T5-2，`docs/DECISIONS.md` D013 补记 / `docs/AI_CONTEXT.md` §4.49）**——取代固定 `sleep(random.uniform(0.8, 1.3))`。`settle_baseline = self.device.image`（`list_find` 循环里 swipe 前未再截图、干净）→ `self.device.swipe` → `wait_for_changed_and_stable(settle_baseline, self.device.screenshot, roi=_list_roi_back_to_box(target.roi_back), *模块级 `_LIST_FIND_SETTLE_*` provisional 阈值*)`。**返回值丢弃、不参与控制流**：settle 成功或 timeout 都回循环顶重新识别，`max_swipe` 仍是唯一收敛边界，**不新增 BOTTOM / ABORT**。ROI 用每个 RuleList 自己的 `roi_back`（无全局 ROI）。
  - 真机标定仍为 Level C；**不因为全仓 swipe 已迁 TouchSwipeModel 就给每个 swipe 自动套 FrameWait**（FrameWait 由业务 consumer 按 W1 语义显式决定）。

---

## 3. 关键调用链（经常被修改）

### 出现即点击

```
ScriptTask.run
 → BaseTask.appear_then_click(target, interval=, threshold=, confirm_delay=)
    → BaseTask.appear(target)                     # RuleImage.match / RuleOcr.ocr（走 RPC）
    → target.coord() / action.coord()             # module/atom/*.py → ClickSampler.sample_target(roi, name)（D019：EMPIRICAL 优先；未标定 = RULE_FALLBACK anchor 经 ROI 尺寸适配；HABIT，非整 ROI 均匀）
    → Device.click(x, y, control_name)            # = Control.click（只执行最终坐标，不再空间抖动）
       → Control.click → click_methods[control_method](x, y)
          → minitouch.click_minitouch  (默认)
          → BehaviorTrace.record('ACTION', action='click', target=control_name, elapsed_ms=...)
```

`confirm_delay=(lo, hi)` 时额外：识别 → `random_delay(lo, hi)` sleep → 重新 `screenshot` → 二次 `appear` → 重新 `coord()` → 点击。

### 滑动（普通页面滑动 / 列表滚动 —— 2026-09-07 起统一经 `BaseTask.swipe_trajectory` helper）

```
BaseTask.swipe(RuleSwipe)  —— ~50 个 self.swipe(S_*) consumer
 → RuleSwipe.sample_endpoints()  = sample_swipe_endpoints(roi_front, roi_back)   # v2 端点采样器（D022）
     # 起终点各自独立采、主集中高斯 + 少量宽尾、夹到安全范围、联合保方向 / 有效距离；
     # 轴向 ROI >= 48px 的轴 + 两端两轴都大时逐字保持旧 _center_biased_int（== 旧 coord()）
     # 旧 RuleSwipe.coord()（严格 ROI 内中心偏置）保留给兼容 / 测试，不再在生产链上
 → BaseTask.swipe_trajectory((x1,y1), (x2,y2), control_name=swipe.name, fallback=True)   # 公共薄 helper
    → control_method == 'minitouch' 且 位移 >= 10px
         → TouchSwipeModel().generate((x1,y1),(x2,y2))  → Device.swipe_trajectory(...)   # 见下方「自定义轨迹滑动」链
    → 其它后端 / 位移 < 10px（fallback=True）
         → Device.swipe(p1, p2, control_name=)  = Control.swipe                          # 端点滑动，保留 distance_check / duration
              → minitouch→swipe_minitouch / uiautomator2→swipe_uiautomator2(duration=) / adb→swipe_adb(duration*2.5) / scrcpy / window_message
    → fallback=False 且非 minitouch  → raise NotImplementedError
 # helper 只负责「怎么滑一次」：不 screenshot / 不 FrameWait / 不 sleep / 不 retry / 不加随机延迟
 # GeneralBuff.exp_50/exp_100 直接调 self.swipe_trajectory((580,320),(530,240), control_name='GENERAL_BUFF_LIST')
```

**注意**：
- `BaseTask.list_find` 翻页 swipe 仍直接 `self.device.swipe(p1,p2)`（未迁 `swipe_trajectory` helper——RuleList 翻页几何 D013 明令不动）。**但翻页后的 settle 已于 2026-09-08 从固定 `sleep(0.8~1.3)` 迁到 `wait_for_changed_and_stable`**（上方「FrameState Wait Layer」消费者 ②，结果不参与控制流）。
- `KekkaiActivation.check_card_num`、`KekkaiUtilize` **怠惰模式** / **非 minitouch 回退**、`RyouToppa.flush_area_cache` 仍直接 `swipe_adb` / `device.swipe`（各有原因，见 `docs/ROADMAP.md` / D018 全仓迁移补记）；`swipe_adb` 直连不被 BehaviorTrace 记录（已知缺口）。
- **drag / press-and-drag / 摇杆手势永不按普通 swipe 迁移**：`Control.drag`、`tasks/Chess/runtime/press_and_drag.py`、`AbyssShadows.move_a_little`。

### 自定义轨迹滑动（`swipe_trajectory`，D018；`BaseTask.swipe_trajectory` helper + KekkaiUtilize K1~K4）

```
调用方：KekkaiUtilize._perform_search_swipe（标准 PASS 搜索，minitouch 配置；首个逐调用点 opt-in）
 → TouchSwipeModel(params, rng).generate(start, end)  = [(x, y, dt_ms), ...]   # 纯逻辑，minimum-jerk + 有界曲率
 → Device.swipe_trajectory(trajectory, control_name=)  = Control.swipe_trajectory
    → control_method == 'minitouch'  → swipe_minitouch_trajectory(trajectory)
         → _ensure_trajectory(trajectory)                     # @retry 之外校验，非法 → ValueError
         → @retry _swipe_minitouch_trajectory_run(points)
              → down(p0) / [move(pi).commit().wait(dt_i)] / up  # 不套 insert_swipe、不叠加 random_int(6,15)
    → 其它后端  → raise NotImplementedError                    # 不静默退化成端点滑动
 → BehaviorTrace.record('ACTION', action='swipe', target=control_name, elapsed_ms=...,
        extra={start_x,start_y,end_x,end_y,point_count,trajectory:[[x,y,dt],...]})  # 一次 swipe = 一个 ACTION
        # 完整 commanded 轨迹整体嵌 extra（≤80 点，直接来自传入的这一份、不重 generate）；绝不逐 MOVE 落事件
        # extra 仅在 trace.is_recording() 为真时才组装（关闭态不白拷贝点列）
 → click_record_clear()
 → wait_for_changed_and_stable(baseline, device.screenshot, roi=SWIPE_WAIT_ROI, ...)      # K3：取代固定 sleep(2)
      # baseline = swipe 前明确重截的一帧；success → True（扫下一屏），否则 → False
 → _run_search_pass：_perform_search_swipe() 返回 False → return PassResult.ABORT（no change ≠ BOTTOM）
```

**K4（2026-09-07，`_run_search_pass` 循环内，D017 K4 补记 / §4.47）—— K4-1 selected anchor 实际滚动位移 + K4-2 一帧对一帧投影去重（均 Level A/B 已实施；Level C pending）**：
```
_run_search_pass 每屏（screen N，K3 判 changed&stable 后的稳定屏）：
  screenshot → detect_selected_anchor(frame, I_IS_SELECTED)  = SelectedAnchorResult   # tasks/KekkaiUtilize/selected_anchor.py
       # I_IS_SELECTED.roi_back=(602,168,30,442) 动态搜索条 → match_all_any（cv2.matchTemplate 全量 + NMS）
       #   NMS 后恰 1 → available(center_y=y+h/2)；0 / >1 → unavailable
  actual_scroll_dy_px(anchor_before(屏 N-1 swipe 前), anchor_after(屏 N))  = dy | None  # tasks/KekkaiUtilize/frame_projection.py
       # dy = before.center_y − after.center_y；dy<=0 / dy>=roi_back 高度 / 任一 unavailable → None
       # 禁止用 commanded 位移（SWIPE_DISTANCE_RANGE）；row_pitch 只做「约几格」日志、不参与、不取整
  cards = find_everyone(frame)                                # (image, score, (x,y,w,h)) 按 y 排序
  scan_cards = cards
  if cards and prev_detections and dy is not None:
      dedup_by_projection(prev_detections, cards, dy, visible_y=K4_LIST_VISIBLE_Y):
          project 上一屏每个 bbox → (x, y−dy, w, h)；投影中心出 visible_y → 忽略（已滚出屏）
          同 image.name + bbox IoU>0 → max-IoU 贪心一对一 → duplicate_indices
      scan_cards = new_detections（cards − duplicates，保序）
  for det in scan_cards: 点开 → check_card_num → threshold（D017 原样，仅遍历 new）
  ... appear(I_U_EMPTY_CARD)（BOTTOM 判定，不变）...
  loop 底 swipe 前：prev_detections = cards；screenshot；anchor_before = detect_selected_anchor(frame)
```
**测量不可靠（unavailable / dy 非法 / >1 匹配）→ scan_cards = cards（完整 D017 扫描，不漏卡）。** `measurement unavailable ≠ ABORT ≠ BOTTOM ≠ PASS_MISS`；K3 失败仍 `return ABORT`（且不进 K4 after anchor）；BOTTOM 仍只认 `I_U_EMPTY_CARD`。**无持久历史**（只留上一屏）。两个 task-local 纯组件（`selected_anchor.py` = K4-1、`frame_projection.py` = K4-2）不 swipe / 不调 FrameWait / 不改 PASS。`K4_ENABLED` kill switch。K4-2 是**业务层去重**（跑完整 `find_everyone` 后过滤 `new_detections`）；`new-region-only optimization`（按 dy 只裁新进入区域跑识别）⏸ **未实现 / optional**。

`Control.swipe` / `Control.swipe_trajectory` / `RuleSwipe` 本体不变；`swipe_trajectory` 不做 `distance_check` / `duration` / vector 合成。**`BaseTask.swipe` 自 2026-09-07（全仓 Swipe Consumer 迁移，D018 全仓迁移补记）起改为委托新公共 helper `BaseTask.swipe_trajectory`**——minitouch → `TouchSwipeModel` 轨迹、其它后端 → `Control.swipe` 端点回退；起终点 / 方向 / 距离 / `interval` / `control_name` 不变。K3（2026-09-07）在 KekkaiUtilize 链尾把「固定 2 秒等待猜停稳」换成 FrameWait（见上方「FrameState Wait Layer」）——只是 KekkaiUtilize 这一个 consumer 的 settle 方式变化，`swipe_trajectory` / `TouchSwipeModel` / FrameWait 本体契约不变；`BaseTask.swipe_trajectory` helper **不含 K3 FrameWait**。

### FIRE Action（进攻入口 → 进入战斗，R-R1 收口 2026-09-08 + 第二批 Orochi/EvoZone + RealmRaid `_fire_again` §4.56）

`RealmRaid.fire()` / `RyouToppa.attack_area()` / `Orochi._fire_orochi_alone()` /
`EvoZone._fire_evozone_alone()` 的「点进攻按钮 → 进入 `run_general_battle`」是**进入
GeneralBattle 之前的业务入口状态机**，与 GeneralBattle FSM 无关。R-R1 收口后标准形状：

```
State Ready        识别到目标详情 / I_FIRE 就绪（appear(I_FIRE)）
   ↓
FIRE Reaction      每次 attempt 独立 random_delay(*REACTION_FIRE)  (0.4~0.8s，PROVISIONAL)
   ↓
Fresh Confirm      sleep → screenshot（新帧）→ 再判 is_in_battle() → 二次 appear(I_FIRE)
   ↓               ├─ reaction 期间 I_FIRE 消失 → 不点旧坐标，回循环顶按当前页面重判
   ↓               └─ I_FIRE 仍在
Click              appear_then_click(I_FIRE, interval=0, threshold=0.8)
   ↓
FIRE post-click 三态（RealmRaid `_wait_fire_entered_battle()`，有界 Timer(RR_FIRE_POST_CLICK_TIMEOUT=3)，期间不点任何坐标）：
   ├─ BATTLE            is_in_battle()（准备 / 战斗 / 结算 / 奖励页；复用 GeneralBattle.is_in_battle）→ return True → caller run_general_battle
   ├─ RETRYABLE_REALM_RAID  _is_realm_raid_retryable_state() = appear(I_RR_PERSON) | appear(I_FIRE) | appear(I_BACK_RED)
   │                    → 明确仍在个人突破可操作页面 → 下一 bounded attempt / 允许重开目标详情
   └─ TRANSITION_UNKNOWN  旧 marker 消失、battle 未出现的过渡 / 加载 blank 帧
                        → **既不当 success，也不当 immediate failure** → 在 Timer 内持续等 BATTLE / RETRYABLE
   ↓
attempt / timeout 用尽（RealmRaid: RR_FIRE_MAX_TRIES=4 + Timer(RR_FIRE_TIMEOUT=10)；RyouToppa: RYOU_TOPPA_ACTION_RETRIES=2 + _wait_for_attack_state）
   → return False（可达）→ caller `if not self.fire(index): continue`（不误交接 GeneralBattle）
```

**关键约束**：
- **旧页面标识消失（RealmRaid `I_RR_PERSON` / RyouToppa 目标列表）既 ≠ 已进入战斗，也 ≠ immediate
  failure / retry**——只作辅助信号；success 必须由正向战斗状态确认（`is_in_battle()`），过渡 / 未知帧
  必须在有界 timer 内继续等。
- **`C_PARTITION_n`（RealmRaid 九宫格）点击必须有明确 retryable-state 守卫**（`_is_realm_raid_retryable_state()`），
  `not appear(I_FIRE)` **不再是**点 partition 的充分条件（可能是详情未开 / 页面切换 / FIRE 加载中 /
  弹窗遮挡 / 已离开个人突破页）。
- `I_FIRE` 的 reaction owner 只有 `REACTION_FIRE`（`module/reaction_profile.py`，engineering baseline），
  **不叠** `confirm_delay` / 第二套 repeat/retry delay（下一次 attempt 的 `REACTION_FIRE` + 状态检查即
  构成合理 retry 间隔）。RyouToppa 区域进攻前的 `random_delay(1.0, 3.0)` 是**区域级业务 pacing**
  （不同 owner），与 FIRE reaction 并存、不合并。
`Exploration.fire()`（`get_current_page() in (page_battle_prepare, page_battle)` + `max_tries=4` +
`Timer(10)`）是本形状的参照实现，本轮未改。

**第二批（2026-09-08，§4.53）**：Orochi `run_alone` / EvoZone `run_alone` 的 `I_*_FIRE` 收口为同一
三态形状——`_fire_{orochi,evozone}_alone()`（正向 `is_in_battle()` + 每 attempt 独立
`REACTION_FIRE` + fresh reconfirm + `{OROCHI,EVOZONE}_FIRE_MAX_TRIES=4` + `Timer(*_FIRE_TIMEOUT=10)`
+ 可达 `return False`）/ `_wait_{orochi,evozone}_fire_state() -> 'battle'|'retryable'|'timeout'`（不点坐标）
/ `_is_{orochi,evozone}_challenge_retryable()`（纯只读 = `appear(I_*_FIRE)`）。caller
`if self._fire_*_alone(): run_general_battle(...)`。**未迁**：契灵 `I_BALL_FIRE`（连点 + `BondlingNumberMax`
资源耗尽耦合，结构特殊 → PARTIAL / ROADMAP）、Orochi `run_wild` 的 `I_OROCHI_WILD_FIRE`（全仓无
`RuleImage` 定义、既有断链 → ROADMAP）、Orochi / EvoZone 的 `run_leader` / `run_member`（不点 FIRE）。

**RealmRaid `_fire_again()` —— 退四内部「再次挑战」（2026-09-08，§4.56 / D001 补记 / D020 + Level C hotfix）**：
退四路径失败结算页点「再次挑战」重新进战斗，同一 FIRE Contract。`fire_again()` → `_fire_again() -> bool`
（`wait_until_appear(I_FIRE_AGAIN, wait_time=RR_AGAIN_TIMEOUT)` + `Timer(RR_AGAIN_TIMEOUT)` +
`for attempt in range(1, RR_AGAIN_MAX_TRIES + 1)`；正向 **`_is_active_battle_entry()`** → True；
`I_SHOW_AGAIN` 是「不再提示」复选项，保持流程点击、无 reaction；`I_FRESH_ENSURE` 是刷新确认与再战确认共用的确认按钮。在 `_fire_again()` 内它独立使用
`confirm_delay=RR_AGAIN_CONFIRM_DELAY=(0.3,0.6)`：识别 → 随机等待 → fresh screenshot → 二次确认（消失不点旧坐标）→ 重新取坐标点击；不复用 `REACTION_FIRE`。就绪 → 每 attempt 独立
`random_delay(*REACTION_FIRE)` → `sleep` → fresh screenshot → 二次 `appear(I_FIRE_AGAIN)`（消失不点
旧坐标）→ click → `_wait_again_entered_battle()`；用尽 → **可达 `return False`** → `run()` 退四路径改走
`check_refresh()`）。`_wait_again_entered_battle(timeout=RR_AGAIN_POST_CLICK_TIMEOUT) -> str`
（`'battle'` = `_is_active_battle_entry()` / `'failure_page'` = `appear(I_FIRE_AGAIN) or
appear(I_FRESH_ENSURE)` / `'timeout'`，**不点任何坐标**）。常量 `RR_AGAIN_MAX_TRIES=4` /
`RR_AGAIN_TIMEOUT=10` / `RR_AGAIN_POST_CLICK_TIMEOUT=3`（对齐 `RR_FIRE_*`）。**只在退四分支被调**，
普通失败绝不调用。

**Battle Lifecycle Detector ≠ New Battle Entry Detector（Level C hotfix，2026-09-08，D001 补记）**：
`_fire_again()` / `_wait_again_entered_battle()` 原用 `GeneralBattle.is_in_battle(False)` 作 positive
——真机实测发现退四首战主动退出、`Battle result: Lose` 之后，`is_in_battle()` 因失败横幅 `I_FALSE`
命中恒 True（`is_in_battle` = `I_BATTLE_INFO | I_PREPARE_HIGHLIGHT | I_FRIENDS | I_WIN | I_DE_WIN |
I_FALSE | I_REWARD | I_REWARD_GOLD`，含 result / reward marker），把「仍停在失败结果页」误判成
「已进入下一场战斗」→ caller 又 `run_general_battle()` → 假退四循环。修复：新增 RealmRaid-local 只读
helper **`_is_active_battle_entry()`** = `self.is_in_prepare(False) or self.is_in_real_battle(False)`
——复用 GeneralBattle 已有的两个**窄** detector（`is_in_prepare` = `I_BUFF | I_PREPARE_HIGHLIGHT |
I_PREPARE_DARK | I_PRESET | I_PRESET_WIT_NUMBER`，`is_in_real_battle` = `I_BATTLE_INFO`），都不含
result / reward marker。`GeneralBattle.is_in_battle()` / `is_in_prepare()` / `is_in_real_battle()`
**本体及其它 consumer 不动**。**长期规则**：challenge / `fire_again` / retry 这类「点按钮后判断是否
进入了一场*新*战斗」的 positive 确认，不得用含 result / reward marker 的宽生命周期 detector，应用
只含 active prepare / battle marker 的窄 positive。`fire()` R-R1 的 `is_in_battle()` 用法本轮不动
（目标详情页点第一次 FIRE，其前无结果页，安全-by-context）。

**RealmRaid 目标选择 = 九宫格固定 1→9（§4.56 / D020）**——与 FIRE Action 同层但不是 FIRE 契约：
`_grid_targets()`（`order_medal.find_everyone()` 一次扫全 9 格当过滤器，每 match 中心映射回
`C_PARTITION_n.roi_front`，减 `_broken_orders()`）→ `run()` 取 `index = min(targets)`（从左到右、
从上到下第一个）。**不再按勋章数 / `order_attack` 优先级排序**（勋章值只留给呱太判定）。**目标级业务
pacing `RR_TARGET_PACING = (1.0, 2.5)`**（`_enter_target()` 里唯一一次 `random_delay(*RR_TARGET_PACING)`
→ `sleep` → fresh 二次确认 → `click(C_PARTITION[order-1])`）是**独立 timing owner**，与 `fire()` 的
`REACTION_FIRE` 并存、不合并——定位同 RyouToppa 区域进攻前的 `random_delay(1.0, 3.0)`。

**RealmRaid `run()` 主循环（§4.56 + 2026-09-08 correctness follow-up / D020）**：

```
begin_fatigue_task('RealmRaid')  ；lock_default = con.general_battle_config.lock_team_enable
failed_orders = set()            ← CONTINUE 本轮 skip 的失败 order（纯局部，不涂帧 / 不当 broken）
while 1:
  screenshot ; lock 复位 lock_default ; check_ticket → False 则 break
  targets   = _grid_targets()                              ← raw UI 可攻打（已减 broken）
  available = {o:m for o,m in targets if o not in failed_orders}   ← 普通选目标用
  not available → CONTINUE: check_refresh → clear + fatigue + continue ；否则 success=False; break
  index = min(available) ; only_last = len(targets) == 1   ← 退四判据用 raw，不用 available
  ┌ only_last and exit_four（退四）:
  │   screenshot → _is_only_remaining_target(index) 否 → continue（不解锁）
  │   ensure_lock(False)
  │   try:  _enter_target(index, require_only_remaining=True) → fire → 首战投降
  │         for i in range(RR_EXIT_FOUR_SURRENDERS=4): _fire_again → run_general_battle（第4次真打）
  │   finally: ensure_lock(lock_default)          ← continue/break/异常都恢复；不吞异常
  │   aborted or not last_battle → check_refresh → clear + fatigue + continue ；否则 success=False; break
  └ else（普通目标）:
      check_medal_is_frog → 临时 lock_team_enable=False
      _enter_target(index) → fire(index) → last_battle = run_general_battle(...)   ← 此处不再 fatigue
  ── 共享尾部 ──
  reward_detect_click → continue（同 cycle 收尾，不 fatigue）
  three_refresh 命中 → check_refresh → clear + fatigue + continue ；否则 break
  not last_battle:
     REFRESH  → check_refresh → clear + fatigue + continue ；否则 break
     EXIT     → break（不 skip / 不 refresh / 不 fatigue）
     CONTINUE → failed_orders.add(index) → fatigue + continue
  （普通/退四胜利）→ _realm_raid_cycle_safe_break()   ← fatigue 在此
```

**Fatigue Safe Point = failure recovery 完成之后**（不是 battle 之后）：`_realm_raid_cycle_safe_break()`
先 `wait_until_appear(I_BACK_RED, wait_time=RR_CYCLE_STABLE_TIMEOUT=10)`（复用个人突破页返回键作
recovery-complete 判据，非固定 sleep）→ `screenshot` → `_is_realm_raid_retryable_state()` 守卫 →
`try_fatigue_break(safe=True, repeat_completed=True, deadline=None)`。禁止 `battle failure → fatigue
→ refresh` 顺序。退四内 4 次 `_fire_again()`（`RR_EXIT_FOUR_SURRENDERS = 4`，旧 `run()` 硬编码、
源码可证）。**Failure Policy**（`when_attack_fail`）：REFRESH = 刷新 + `failed_orders.clear()`；
CONTINUE = `failed_orders.add(order)` 本轮跳过、`available` 空才刷新；EXIT = 直接退出。`failed_orders`
!= broken——两套状态不混用（D020 补充）。

### Stable Battle Entry Action —— Action Owner vs Passive Waiter（2026-09-08，§4.54 reaction + §4.55 FSM）

进入战斗的「点稳定挑战 / 开始战斗按钮」不按「单人 / 组队」区分 reaction，而按**谁真正点击**：

| 角色 | 判据 | reaction |
|---|---|---|
| **Action Owner** | 本机真实识别并点击「挑战 / 开始战斗」按钮 | `REACTION_FIRE`（每 attempt 独立采样）+ fresh reconfirm + no stale click + bounded FSM |
| **Passive Waiter** | 只等别人开战（`wait_battle` / `check_then_accept` / member / invitee） | 无 reaction click |

**公共组队 challenge owner = `GeneralInvite.click_fire()`**（`tasks/Component/GeneralInvite/general_invite.py`）：
`run_invite` 里 `room_check_can_fire(config)` 为真时调用，或 ExperienceYoukai / GoldYoukai / Hunt /
Tako 直接调用。**§4.55 起是 bounded 四态 transaction，返回 `str`**：

```
overall = Timer(GI_FIRE_TIMEOUT=15)   # soft new-attempt admission budget（非 strict 15s wall-clock）
for attempt in 1..GI_FIRE_MAX_TRIES=4:
  if overall.reached(): break          # ← 只在 attempt 顶 gate「是否允许启动新 attempt」
  screenshot → _classify_room_entry_state()（只读，优先级 battle > room_failed > retryable > unknown）：
   ├─ BATTLE            _battle_entry_positive() = is_in_battle(False)（11 consumer MRO 都有；
   │                    否则兜底 appear(GeneralBattleAssets.I_BATTLE_INFO) | I_PREPARE_HIGHLIGHT
   │                    —— is_in_battle 的 2 个 battle-entry marker 严格子集）
   │                    → return 'battle'（唯一 success）
   ├─ ROOM_FAILED       _room_entry_failed() = appear(I_MATCHING) | I_CHECK_MAIN | I_CHECK_EXPLORATION
   │                    （复用 ensure_enter / wait_battle 已有 marker）→ return 'room_failed'（不点）
   ├─ TRANSITION_UNKNOWN 三者都不是（loading / blank / 转换）→ _wait_room_entry_state（有界 Timer，不点）
   │                    → battle / room_failed 返回；retryable / timeout → 下一 attempt
   └─ RETRYABLE_ROOM    is_in_room(False) → 识别 I_FIRE(优先)/I_FIRE_SEA
        → random_delay(*REACTION_FIRE) → sleep → fresh screenshot → 重新 classify
           （battle/room_failed 立即返回；离开 retryable / 按钮消失 → 不点旧坐标、下一 attempt）
        → appear_then_click(target, interval=1, threshold=0.7)
        → _wait_room_entry_state（有界 Timer(GI_FIRE_POST_CLICK_TIMEOUT=4)）
           → battle / room_failed 返回；retryable / timeout → 下一 attempt
attempts / overall 用尽 → return 'timeout'                # 无 while 1
```

**关键约束**：
- **「旧 room 状态消失（`not is_in_room(False)`）」单独发生既 ≠ success 也 ≠ immediate failure** ——
  无 battle / 无 failure marker 时归 TRANSITION_UNKNOWN，有界 polling 等决定性状态，不点任何坐标。
- **`click_fire()` 无界（`while 1`）已消除**：`Timer(GI_FIRE_TIMEOUT)` + `for attempt in range(4)` +
  `_wait_room_entry_state` 各自 `Timer` —— bounded / finite（一定会终止）。**但 `GI_FIRE_TIMEOUT` 是
  soft new-attempt admission budget，不是 strict 15s hard deadline**：`overall_timer.reached()` 只在
  `for attempt` 循环顶检查；已启动的 attempt 的 `random_delay(*REACTION_FIRE)` + `_wait_room_entry_state`
  （自带独立 `Timer(GI_FIRE_POST_CLICK_TIMEOUT)`、不接收 remaining budget、`Timer.reached()` 纯轮询
  不打断）会跑完。最后一个在途 attempt 显式 overrun 约 `0.8 + 4 ≈ 4.8s` → 显式返回上界 ≈ `19.8s`
  （另加 device 开销）。**保留 soft**（与 RealmRaid `fire()` / Orochi·EvoZone `_fire_*_alone` 同结构；
  不在接近 battle 正向确认时硬切断）。
- **caller guard**：`run_invite` 只在 `click_fire() == 'battle'` 才 `return True`，否则 `return False`
  （各 caller 已有的「邀请失败退出」/ `raise InviteFailedException` 承接，不误交接 `run_general_battle`）；
  4 个直接 caller（ExperienceYoukai / GoldYoukai / Hunt / Tako）加 `if self.click_fire() == 'battle':` guard。
- `is_in_room` 循环判据 + 上层 `run_invite` 的 `Timer(20/30)` / `timer_wait` + `interval=1` throttle
  + minitouch dwell 不变；**不叠 `confirm_delay` / 第二套 reaction**；**不接 Fatigue**（组队 critical path）。
- `_battle_entry_positive` / `_room_entry_failed` / `_classify_room_entry_state` / `_wait_room_entry_state`
  **纯只读**（无 screenshot / click / sleep / random_delay，`_wait_*` 只有一个自己的 `Timer`）。

**自动继承**（`click_fire` 唯一公共实现、无 task 覆写）：经 `run_invite` = BondlingFairyland /
EternitySea / EvoZone / Exploration / FallenSun / Orochi / OtherWorldTwilight；直接调 = ExperienceYoukai
/ GoldYoukai / Hunt / Tako。**11 个 consumer MRO 里全部带 `GeneralBattle`**（Exploration 经
`BaseExploration`）；唯一 `GeneralInvite`-without-`GeneralBattle` 的 `MysteryShop` 不调 `click_fire`。

Orochi / EvoZone 的 `run_leader` / `run_wild` 是 Action Owner（leader 经 `run_invite` → `click_fire`；
Orochi wild 自己点断链的 `I_OROCHI_WILD_FIRE`）；`run_member` 是 Passive Waiter。`run_alone` 的
`_fire_*_alone`（§4.53）是各自 task-local 的 Action Owner，**不经 `click_fire`**、不叠加。

### 通用战斗

```
ScriptTask.run → run_general_battle(config, exit_matcher=)
 → while True:
     screenshot
     _tick_long_battle / _tick_timeout
     page = GameUi.detect_page_in(prepare, battle, result, reward)
     handler = gb_page_handle_dict[page]  (或 _handle_missing_battle_page)
     action = handler(context, config)
     resolved = _resolve_action(action)   → 命中则返回 True/False
```

### 任务 episode（Script.run）

```
Script.loop → get_next_task → run(command)
 → begin_global_activity()
 → trace.set_task(command); trace_started_at = perf_counter()
 → try: ScriptTask(config, device).run()          # 通常 raise TaskEnd
   except Exception: outcome = _handle_task_exception(e, command); return outcome
   finally: trace.record('TASK', target=command, result=ok|fail, elapsed_ms=...)
            trace.set_task('')
            end_global_activity()
```

所有出口（正常 / fail / Exception→return / `exit(1)` 引发的 SystemExit）都经过 `finally`，`set_task('')` 一定执行（见 `docs/DECISIONS.md` D005）。

每次任务执行都会 `ScriptTask(config, device)` **重新实例化**，因此任务实例上的可变状态
（`BattleContext`、`utilize_*` 计数、`_fatigue_owns_macro_idle` 等）不跨任务、也不跨账号继承；
账号轮换在任务之间切号时同样落在这个边界内（见 §4.70 的账号切换状态检查）。

### 多账号 / 多实例层（仅 `zoombies-account-rotation-dailytask/synevo` 分支，2026-09-14 整合）

```
tasks/AccountRotation/script_task.py      # 账号轮换主流程（登录 → 庭院确认 → 每日任务 → 切号）
tasks/MultiAccountEvo/script_task.py      # 多实例组队觉醒（队长/队员角色 + 三实例同步）
  ├─ EvoZoneScriptTask.run_embedded(...)  # 复用 EvoZone 业务，配置走 active_evo_zone 注入
  └─ ClickSampler.sample_target(...)      # 好友名点击（2026-09-14 起与 GeneralInvite 同一 contract）
module/multi_account/                     # account / switcher / coordinator / daily_state /
                                          # daily_task_report / file_lock / ocr_service / rotation_runner
tasks/DailyTrifles/{cooperation,hunt}_adapter.py
```

`EvoZone.active_evo_zone` 是这一层的配置入口：无嵌入配置时回落 `self.config.evo_zone`，
被 `MultiAccountEvo` 注入 `_embedded_evo_zone` 时按当前账号/角色生效。**EvoZone 的 FIRE 与结算
仍走公共 contract**（`_fire_evozone_alone()` 三态 FIRE + `run_general_battle`），多账号层只负责
选配置、切号与实例间同步，不自建第二套战斗/FIRE 实现。

### 疲劳安全节点

```
RyouToppa.run → begin_fatigue_task('RyouToppa')
 → 每完成一个区域（SUCCESS / FAILED_MARKED）:
     BaseTask.try_fatigue_break(safe=True, repeat_completed=True, deadline=)
      → FatigueManager.try_break(...)   # 按 rest/idle hazard 概率决定是否 sleep

Orochi.run_alone / EvoZone.run_alone → begin_fatigue_task('Orochi' / 'EvoZone')   # 第二批，2026-09-08 §4.53
 → 一场完整战斗结束、run_general_battle 已回到稳定挑战页:
     BaseTask.try_fatigue_break(safe=True, repeat_completed=True, deadline=)
 → 休息结束回外层 while 顶 screenshot + is_in_orochi / is_in_evozone 重新确认（fresh revalidate）

RealmRaid.run → begin_fatigue_task('RealmRaid')   # §4.56 / D020 + 2026-09-08 correctness follow-up
 → 普通目标 / 退四「战斗 + 结果 + failure recovery（REFRESH 的刷新 / CONTINUE 的 skip 记录）
    都完成、回到个人突破稳定九宫格」——**不是 battle 之后**（禁止 battle failure → fatigue → refresh）:
     _realm_raid_cycle_safe_break():
       wait_until_appear(I_BACK_RED, wait_time=RR_CYCLE_STABLE_TIMEOUT=10)   # recovery-complete，非固定 sleep
       → screenshot → _is_realm_raid_retryable_state() 守卫 才
       try_fatigue_break(safe=True, repeat_completed=True, deadline=None)   # 无墙钟时限，number_attack 限次
 → 休息结束回 while 顶 screenshot + check_ticket(wait_until_appear(I_BACK_RED)) + _grid_targets 重扫
   （fresh revalidate + reselect target）

Exploration.run（仅 ALONE）→ begin_fatigue_task('Exploration')   # §4.60 / D021 corrected 补记
 → Boss FIRE → run_general_battle(exit_matcher=page_exp_main) → _match_end.refresh()   # 原生，返回值不捕获
 → page-dispatch：page_exp_main → run_on_exp_main → collect_reward()
      = collect_treasure_box()（有小 / 大宝箱 → 领取；无 → return False）
        or collect_paper_man_reward()（fire_monster_type=='boss' and not collect_paper_reward
                                       → "Not collect paper doll reward" + 原生 quit_exp_main()）
 → quit_exp_main → page_exp_exit → run_on_exp_exit(I_E_EXIT_CONFIRM)   # confirm_delay 二次确认，天然 stale-safe
 → 游戏退出 → get_current_page() 命中 page_exp_entrance / page_exploration
 → run_on_exp_entrance / run_on_exp 顶部 _maybe_boss_cycle_fatigue()：
      ALONE 且 fire_monster_type=='boss' → try_fatigue_break(safe=True, repeat_completed=True,
                                                             deadline=start_time+limit_time)
      + 消费 Boss 标记 + 调用方 return → exec_exp_page 下一轮 fresh screenshot + 重新分发（fresh revalidate）
```
（§4.58 曾新增 `_run_boss_exit_transaction` / `EXIT_READY..EXIT_SUCCESS` / `_is_boss_exit_success_state`
/ `_complete_boss_business_cycle` / `_skip_treasure_once_at_entrance` 等 Boss 专用退出结构，服务于「Boss
后完全不领地图宝箱直接退出」的**错误业务需求**，§4.60 已撤销、恢复上面的原生链。）

**Rotation Contract（§4.59 / D021 补记，§4.60 保留不动）**：游戏内「自动轮换」开关归**用户**所有。`switch_rotate()` 的
`AutoRotate.no`（默认）分支 = `pass`——脚本**绝不**点 `I_E_AUTO_ROTATE_ON` / `I_E_AUTO_ROTATE_OFF` 去
取消 / 恢复用户手工设置的轮换。`page_exp_main` 识别本就用
`any_of(I_E_SETTINGS_BUTTON, I_E_AUTO_ROTATE_ON, I_E_AUTO_ROTATE_OFF)` 覆盖轮换开 / 关两种布局。
例外：`auto_rotate=yes` 是用户 opt-in「脚本管理候补 / 轮换」，仍走 `C_CLICK_SETTINGS → fill_shikigami
+ 开轮换`，只做「开」方向。

**长期契约**（`docs/DECISIONS.md` D001「Fatigue Safe Point 铺开补记」+ D020 / D021 补充）：只在 Business
Cycle Complete + **Recovery Complete** + Stable Return State 触发；fatigue 后必须 fresh screenshot +
revalidate；leader / member / wild 等有邀请 / 房间 / 队友同步的路径**不接**；`GeneralBattle` 永不是
Fatigue owner。当前 consumer = RyouToppa + Orochi / EvoZone 单人 + RealmRaid 主循环 + Exploration solo
+ ActivityShikigami 普通爬塔线（§4.62：`_activity_challenge_safe_break`，稳定挑战页 + Challenge Ready
positive → `try_fatigue_break`；`_fatigue_owns_macro_idle` 关掉爬塔线旧 `random_sleep`，同一 cycle 只有
Fatigue 一个 macro-idle owner；大富翁 / 伪神降临线不接）。其它活动副本待各自业务链收口后再接。
**ActivityShikigami 爬塔线禁止放在**：`prepare_next_action` 内 / FIRE 点击前 / `_enter_climb_battle` reaction·retry·transition-unknown 内 / battle 中 / `run_general_battle` result·settlement 内 / `_drain_activity_settlement` 未回到挑战页时 / 资源 OCR 判定之前。**RealmRaid 侧禁止放在**：target pacing / FIRE / FIRE retry /
transition-unknown / battle / settlement / reward popup 未处理完 / 退四内部 / `_fire_again` 之间 /
refresh 点击后但尚未确认完成 / 临时解锁尚未恢复时。

---

## 4. 多后端差异（当前已确认）

`Control.swipe(p1, p2, duration=...)` 的 `duration` 只对部分后端有效：

| 后端 | 底层方法 | 是否消费 `duration` |
|---|---|---|
| minitouch | `swipe_minitouch(self, p1, p2)` | **否** |
| adb | `swipe_adb(self, p1, p2, duration=0.1)` | **是**（`Control.swipe` else 分支先 `duration *= 2.5`） |
| uiautomator2 | `swipe_uiautomator2(self, p1, p2, duration=0.1)` | **是** |
| scrcpy | `swipe_scrcpy(self, p1, p2)` | **否** |
| window_message | `swipe_window_message(self, startPos, endPos)` | **否** |

`Control.swipe` 保留 `duration` 形参（adb / uiautomator2 依赖），docstring 已注明该边界。调用方（如 `RyouToppa.flush_area_cache`）传随机 `duration` 在 minitouch 环境下不影响真实滑动时序。详见 `docs/DECISIONS.md` D003。

其他后端差异：
- **点击**：`click_adb` 有 `<0.05s 补 sleep(0.05)`；`click_minitouch` 有 `_humanized_dwell()` = `round(random_triangular(45, 130, 65))` ms + `minitouch_send` 固定尾部 50ms。
- **minitouch pressure**：`_humanized_pressure()` 在 MuMu 环境（握手 `max_pressure` 回退为 1）恒为 1。
- **真实滑动轨迹**：minitouch 由 `insert_swipe`（`module/device/method/minitouch.py`）生成；window_message 由 `windows_impl.py` 内联的 `BezierTrajectory.trackArray`（`module/base/cBezier.py`）生成；adb / uiautomator2 由系统命令直线插值。`module/atom/swipe.py` 的 `RuleSwipe` **不参与**任何后端的轨迹生成，只提供端点。

---

## 5. 当前扩展点（后续公共能力放哪）

| 能力 | 建议位置 | 依据 |
|---|---|---|
| 行为观测 | `module/behavior_trace.py`（已建） | 已有 `ACTION` / `TASK`，后续 `WAIT` / `ERROR` / `TRANSITION` / `RETRY` 复用同一行结构，由对应 Policy / 状态机那一层各自 `record(...)`，不改 BehaviorTrace 本身 |
| 图像状态检测（列表 changed / stable） | **已落地**：`module/atom/frame_state.py`（纯 numpy，`frame_difference` + `FrameStateDetector`）。设备轮询 / 超时留给上层，尚无生产接入 | `docs/ROADMAP.md` T4-1；`docs/DECISIONS.md` D010 |
| 视觉变化 + 稳定的有限等待（取帧 + 轮询 + timeout） | **已落地 + 3 个生产消费者（2026-09-08）**：`module/base/frame_wait.py` 的 `wait_for_changed_and_stable`（`frame_provider` / `clock` 注入、超时返回不抛、成功严格 `changed and stable`）。只做等待外壳，不做 retry / recovery。① `KekkaiUtilize._perform_search_swipe`（K3，结果 → `PassResult.ABORT`）；② `BaseTask.list_find` 翻页 settle（结果丢弃）；③ `Exploration._wait_chapter_list_settle`（章节实际 swipe 后结构 settle，结果不作 semantic success）。参数均 task-local provisional、Level C 待标定；各 consumer 用自己的 asset/list ROI，无全局 ROI | `docs/ROADMAP.md` T4-2 / T5-2 / Exploration 主流程；`docs/DECISIONS.md` D012 / D013 / D021 |
| Wait / Retry / Recovery 职责分层 | **职责边界已由三案例归纳确认（D015）**：① **Verify**（Action 后确认业务结果）= `Task` 组合既有 `appear` / `wait_until_appear` / `wait_until_disappear` / `detect_page_in`，**不新增 Verifier 类**；② **语义 Wait** = `wait_until_appear(wait_time=)` / `wait_until_disappear`（后者缺 `wait_time`，未来补 1 行签名）；③ **视觉结构 Wait** = `module/base/frame_wait.py`（已落地）；④ **Retry**（bounded，verify 触发式）= 未来极小 primitive，仅「计 attempts + 独立 timeout + frozen RetryResult」，不 screenshot / 不缓存坐标 / 不理解 target 类型 / 不做 recovery / 异常透传——**当前不抽，等第一个真实 Level C 迁移**；⑤ **Recovery** = **永远在 `Task`**（refresh / switch group / set_next_run / TaskEnd）。`module/base/retry.py` 的 `@retry` 是异常触发式、基础设施层专用，不适配 task 层。`max_attempts`（动作次数）与 `timeout`（迁移墙钟时间）正交，数值永远调用方给，无项目级默认 | `docs/ROADMAP.md` T4-3；`docs/DECISIONS.md` D012 / D013 / D015；`docs/状态验证与重试模式归纳.md` |
| Task 状态机（State → Action → Verify） | 每个任务自己的 `script_task.py` 内先局部落地，成熟后再抽公共 Engine。四案例的迁移前 characterization 仍作为历史基线；其中 RealmRaid 已完成 FIRE / 主循环收口。Exploration 仍是 page-dispatch FSM，dynamic `fire()` 保持正向 battle page + `max_tries=4` + `Timer(10)`；Boss 战后走**原项目原生 reward / exit 链**（`page_exp_main → collect_reward` = 地图宝箱 or 小纸人 policy →「Boss + 不领小纸人」原生 `quit_exp_main` → page-dispatch 接管外层页），solo Fatigue 挂在 `_maybe_boss_cycle_fatigue()`（外层稳定页）——§4.58 / §4.59 曾按错误需求新增的 Boss 专用 Exit Contract（`_run_boss_exit_transaction` / `EXIT_*` 状态机）已由 §4.60 撤销。Settlement 仍 100% 走 GeneralBattle V3。没有抽第二套全局 FSM / Wait API | `docs/AI_CONTEXT.md` §4.37 / §4.60；`docs/DECISIONS.md` D015 / D021 |
| 疲劳 / 作息 | `module/fatigue.py`（已建），`FatigueConfig` 在 `tasks/GlobalGame/config.py` | 默认关闭，扩接入任务需谨慎 |
| 普通滑动端点空间分布（「起终点在哪」） | **已落地（D022，2026-09-08，Level A/B）**：`module/atom/swipe_endpoint.py` 的 `sample_swipe_endpoints(roi_front, roi_back)`（`SwipeEndpointParams` frozen + provisional）。起终点各自独立采（不共享平移）、主集中高斯（~85%）+ 少量宽尾（~15%）、夹到 `[preferred±hard_half]∩屏幕安全边界`、有限 rejection → 回退轴中心；联合校验夹角 `<= ~25°` + 距离 `[0.55, 1.45]×基准` + 主轴符号 + `>=10px`，`joint_max_attempts` 用尽 → 回退 `(preferred_start, preferred_end)`（有界，无 `while True`）。**轴向 ROI `>= wide_axis_px`（48）的轴 + 两端两轴都大 → 逐字保持旧 `_center_biased_int`**（`S_BATTLE_RANDOM_*` / Summon `S_RANDOM_SWIPE_*` 分布不变）。`RuleSwipe.sample_endpoints()` 委托它；`BaseTask.swipe` 的 `coord()` → `sample_endpoints()`（~50 consumer 透明迁移）。`RuleSwipe.coord()` / `TouchSwipeModel` / `Control` / BehaviorTrace 未改。**Level C PASS（2026-09-08，多轮 MuMu 真机 + OASX trajectory 统计）—— `SwipeEndpointParams` 当前默认值在无新反例前冻结**（reopen 条件见 D022 Level C 补记） | `docs/ROADMAP.md`「已完成」表 + D022 Level C 补记；`docs/DECISIONS.md` D022；`docs/AI_CONTEXT.md` §4.61 |
| 自定义滑动轨迹（「怎么移动」） | **基础设施已落地（D018）**：`module/device/touch_swipe_model.py` 的 `TouchSwipeModel.generate(start, end)`（纯 minimum-jerk + 有界曲率 + 逐段 dt，不 import device）→ `Minitouch.swipe_minitouch_trajectory` → `Control.swipe_trajectory`（显式 opt-in，非 minitouch `NotImplementedError`）。协议层 / `CommandBuilder` / `Control.swipe` / `insert_swipe` 均未改；`RuleSwipe` 端点分布另见 D022（本行不覆盖「怎么走」）。**首个生产消费者 = `KekkaiUtilize` 标准 PASS 搜索（K1~K4，2026-09-04~09-07，已真机连测）**。**2026-09-07 全仓 Swipe Consumer 迁移（D018 全仓迁移补记 / §4.48）**：新增薄公共 helper **`BaseTask.swipe_trajectory(start, end, *, control_name, fallback=True)`**（minitouch→轨迹 / 非 minitouch→`Control.swipe` 端点回退 / <10px→回退 / 不含 K3 FrameWait），`BaseTask.swipe(RuleSwipe)` 改为委托它——42 个 `self.swipe(S_*)` ordinary-scroll consumer + GeneralBuff `exp_50/100` 透明迁移。未迁：`list_find`（绑 T5-2）/ KekkaiActivation `swipe_adb` / RyouToppa（依赖 `duration=`）/ KekkaiUtilize 回退。drag / press-and-drag / 摇杆手势保留 legacy。迁移 consumer 真机效果（除 KekkaiUtilize 外）Level C 待验 | `docs/ROADMAP.md`「TouchSwipeModel 接入」；`docs/DECISIONS.md` D018；`docs/AI_CONTEXT.md` §4.41 / §4.42 / §4.48 |
| 点击落点分布 / preferred center（当前） | **D019（2026-09-08）**：热点解析优先级 `EMPIRICAL > RULE_FALLBACK`；未采样 target 的规则锚点是 `(0.58,0.59)`，两者即使数值相同也以 provenance 区分。Point：`sample_target → adapt_point_profile`，其中 preferred 复用 `adapt_preferred_by_size`，sigma/tail 继续 Point 收缩；Region：`sample_region → adapt_preferred_by_size → 只替换 preferred`，不调用 `adapt_point_profile`，`default_region` shape 不变。两者都按 short side 24/96 smoothstep 释放热点。`area_1` / `wide_card` 保持 EMPIRICAL；GeneralBattle 三个 Settlement Region 是 RULE_FALLBACK。下一行保留的是 T7-5 历史演进记录，其中 `CENTER_FALLBACK` 与 Region「不做 short_side 适配」已被本行 / D019 Supersede | `docs/DECISIONS.md` D019；`docs/AI_CONTEXT.md` §4.50；`docs/T7_TARGET_PREFERENCE_MAP.md` |
| 点击落点分布 / preferred center | **T7-5（2026-09-04，D014 T7-5 段）：普通 Point 生产默认已从整 ROI 均匀改成 preferred 热点 + 偏移模型**。`RuleImage`/`RuleClick`/`RuleOcr`/`RuleGif`/`RuleLongClick` 的 `coord()` = `ClickSampler.sample_target(roi, rule.name)` → `module/click_preference.py` 的 `resolve_target_preference`（静态 registry；未标定 → `CENTER_FALLBACK=(0.5,0.5)`+`default_point`）→ `adapt_point_profile` → `sample(strategy=HABIT)`。registry：`area_1`（EMPIRICAL）+ 3 条 Region 兜底（`random_default`/`random_save_right`/`random_save_bottom` → `CENTER_FALLBACK`+`default_region`）。**T7-5 Stage 2（2026-09-06）新增 `ClickSampler.sample_region(roi, name)`**（Region Target：业务已选定 region 后区内取点，`default_region` profile 比 Point 宽、不做 short_side 适配）。`LEGACY_UNIFORM` 保留但**生产链上 bare `sample(roi)` 消费者 = 0**。inventory：`docs/T7_TARGET_PREFERENCE_MAP.md`。以下能力早已落地：`HABIT`（三成分 mixture + Safe ROI rejection，非 clamp fallback）/ `STRICT`（窄 profile 无 tail）/ `UNIFORM`（Safe ROI 内均匀）+ `module/click_profile.py` 的 `ClickProfile`（frozen，ROI 相对）/ `ClickProfileManager` / `DEFAULT_PROFILES` 已实现。`module/click_profile.py` 的 **`adapt_point_profile(base, roi)` + `point_size_factor`**（T7-2 / T7-4）：Point Target 的语义基础 profile 按运行时 `short_side=min(w,h)` 用**同一个** smoothstep `size_factor`（锚点 24/96）连续适配三件事——`preferred`（→ 中心）、`core/medium sigma`（→ `tiny` 的 σ 锚点 `POINT_MIN_*_SIGMA_*`）、`tail_weight`（→ 0，削掉的回补 `core_weight`）；`safe_margin` / `max_attempts` / `provisional` / `name` 原样透传（`safe_margin` 不随尺寸变——Safe ROI 是硬边界，职责独立），`f=1` 逐字段恢复 base。取代离散尺寸分类——纯计算。**`ClickSampler.sample_point(roi, base_profile)`**（T7-3.2）= `adapt_point_profile` + `sample(strategy=HABIT)` 的薄组合入口（放 `ClickSampler`，**不进 `BaseTask`**——god class 约束）。**非 LEGACY 生产 opt-in（都是逐调用点显式）**：**唯一一个** = `RyouToppa.C_AREA_1`（`HABIT` + `wide_card`，经 `ClickSampler.sample_point` + `RyouToppa.ScriptTask._click_toppa_area` 的 `rule is self.C_AREA_1` 身份守卫，T7-3.2）。GeneralBattle 结算曾是 opt-in ②（Contract v2 `HABIT` + `_SETTLEMENT_PRIMARY_PROFILE`），Contract V3（D016）三个 Large Safe Region 经 `_sample_settlement_click`（**不经 `coord()`**）；**T7-5 Stage 2 起走 `ClickSampler.sample_region`**（中心偏置、非整区均匀；region 选择 marker/80-20 + Generic Result 两次点击 policy 不变）。**T7-5 起 `C_AREA_2..8` 与其它所有 `Rule*.coord()` 默认路径 = `sample_target` = `HABIT` + `CENTER_FALLBACK`**（不再 `LEGACY_UNIFORM`）；`RyouToppa._click_toppa_area` 对 `C_AREA_1` 的显式 `sample_point(wide_card)` 与 registry `area_1` 等价、保留未改。**不放** `RuleClick` / `Control` / minitouch。人工样本由 `dev_tools/manual_click_recorder.py` 采集、`manual_click_analyze.py` 分析、`runtime_roi_probe.py` 采资产运行时 ROI | `docs/ROADMAP.md` T7-1；`docs/DECISIONS.md` D014 / D002；`docs/AI_CONTEXT.md` §4.24 / §4.25 / §4.28 / §4.29 / §4.31 / §4.32 |

**不要**把上述能力塞进 `Control` / `screenshot.py` / `Timer` / `minitouch`——这些是稳定性基础层，见 `docs/DECISIONS.md` D002。（`Minitouch.swipe_minitouch_trajectory` 是例外中的合规做法：它只是「把点列表发给 minitouch」的薄执行层，轨迹**形状与时间**全在 `TouchSwipeModel`，minitouch 侧不含任何策略 / 拟人逻辑，见 D018。）

## L1 / L2 交互分层（2026-09-22 由 master 整合进本分支，集成分支 `zoombies-account-rotation-dailytask/synevo-l1l2-integration`）

本分支在整合前没有 L1 执行器与 L2 反应层（`module/click_pipeline.py`、`module/interaction_policy.py` 都不存在），
`ClickSampler` / `ClickProfile` / `reaction_profile` / `TouchSwipeModel` / `FrameWait` / `BehaviorTrace` / minitouch 拟人化按压则早已与 master 逐字节相同。整合后的合法调用图：

```
单击：任务 / BaseTask / 业务组件 → execute_single_click → Control.click / click_with_backend → 设备后端
长按：任务 / BaseTask / 业务组件 → execute_long_click   → Control.long_click                → 设备后端
L2 ：目标已识别 → InteractionPolicy → reaction 采样一次 → sleep → fresh screenshot → 同目标二次确认 → 新帧坐标 → L1
FIRE：battle-entry 状态机自己拥有 reaction（fire_reaction_range + 任务级 fire_reaction 配置），不走通用 policy
```

- 坐标语义由 `FinalPoint` / `ClickBounds` / `ClickRegion` / `Rule*` 显式声明，一次动作只采样一次最终落点；`Control` 层不做空间抖动。
- 滑动 / 拖动 / 连续触摸手势不属于 L1 单击 / 长按范围（Chess `press_and_drag`、`TouchSwipeModel` 保持原状）。
- 静态守卫 `dev_tools/click_entry_guard.py` 默认禁止生产直接点击 / 长按，白名单分两张表：`_INTERNAL_EXITS` 是架构内部出口（执行器 3 / Control 后端注册表 13 / 后端实现 3 / 演示 2 / 死代码 1），
  `BUSINESS_EXEMPTIONS` 是用户明确决定保留原实现的业务点击豁免（层名 `exempt`）。两张表同样精确到（文件, 函数, 调用形式, 次数），并同样做过期检测。
  **本分支现状（2026-09-22 收尾后）**：守卫 `ok = True`；MultiAccountEvo 的 `_detect_select` / `check_then_accept` 已接入 L1，生产侧只剩 SwitchAccount `_click_bounds` 一条精确豁免——
  它是 synevo 原有账号切换的原生控件点击，按用户决定保留原实现，不接 L1 / L2。
- synevo 独有业务的时序所有权不变：Settlement v1.2 归 GeneralBattle 自己的 session 状态机；账号轮换 / 多账号觉醒的节奏归 `module/multi_account/*` 与 `run_embedded`；两者都不接普通 policy。
