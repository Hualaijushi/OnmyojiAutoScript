# AI 项目上下文

本文档是当前项目状态快照，供后续接手项目的 AI 快速了解有效基线、技术决策和修改边界。它不是开发流水账；历史过程记录在 `DEVELOP_LOG.md`。

## 0. 文档体系与阅读顺序

项目交接文档共 6 份，职责分离：

**判断是否更新某份文档，以「本轮是否改变了该文档负责的项目事实」为准，不以「是否修改了代码」为唯一标准。** 纯设计 / 项目管理工作（确定新架构方案、改 ROADMAP、新增或废弃长期设计决策、改测试规范或真机验证要求、改任务优先级或依赖、改 AI 开发规则）即使没有源码变化，也要更新对应文档。

| 文件 | 职责（负责的项目事实） | 何时更新 |
|---|---|---|
| `docs/AI_CONTEXT.md`（本文件） | 当前状态快照：当前开发阶段、当前 Git 状态、当前测试基线、核心能力状态、已知问题、当前限制、下一步 | 上述任一当前事实变化时 |
| `docs/ROADMAP.md` | 下一步做什么、优先级、前置依赖、什么能做 / 什么等真机 | 任务完成 / 新增 / 优先级变化 / 依赖变化 / 暂停 / 解锁 / 验收标准变化 / 开发阶段变化 |
| `docs/DECISIONS.md` | 长期设计决策（ADR），防止被改回去 | 产生新的长期设计决定 / 旧决定被正式推翻或 `Superseded` / 长期公共契约确定；普通实现细节不写 |
| `docs/ARCHITECTURE.md` | 真实分层与调用链地图 | 真实模块职责变化 / 新增或删除公共层 / 核心调用链变化 / 架构级公共 API 契约变化；普通 Bug 修复或纯计划变化不动 |
| `docs/TESTING.md` | 长期验证规则、测试分级、真机限制 | 长期测试命令 / 验证级别规则 / 真机要求 / Git·CI·lint·formatter 验证规则 / 长期测试原则变化；一次性测试数字放 `AI_CONTEXT` 不堆进这里 |
| `docs/DEVELOP_LOG.md` | 按时间追加的开发历史流水 | 本轮形成了真实项目变更就追加（源码 / 测试 / 配置 / 架构调整 / 正式项目规则变化 / 长期设计决策落地）；纯阅读、纯分析且没有形成项目变更时不追加 |

**新任务阅读顺序**：`AI_CONTEXT`（本文件）→ `ROADMAP` → `DECISIONS` → `ARCHITECTURE` → `TESTING` → 需要历史原因时再读 `DEVELOP_LOG` 最近相关记录（不必通读）。

**入口规则**：仓库根 `CLAUDE.md` / `AGENTS.md` 是所有 AI 会话的启动入口（内容一致的核心规则）。它们已通过 `.gitignore` 的 `!CLAUDE.md` / `!AGENTS.md` 例外**纳入版本控制**，重新 clone / 换机器后仍存在。它们只承担「启动入口」，保持轻量：阅读顺序 + 核心开发规则，不复制当前 HEAD / 测试数字 / 任务详情（那些由 `AI_CONTEXT` / `ROADMAP` 维护）。

若本文档与源码或最新 Git 状态冲突，以源码和最新 Git 状态为准，并及时更新本文档。

## 1. 项目简介

- 项目：`OnmyojiAutoScript-easy-install-self`
- 主要环境：Windows、PowerShell、MuMu 模拟器、Python 工具包。
- 当前仓库：用户自己的 `origin` 为 `https://github.com/Hualaijushi/OnmyojiAutoScript.git`。
- 原作者仓库：`upstream` 为 `https://github.com/xylolit-mu/OnmyojiAutoScript.git`。
- 当前主要控制后端：`minitouch`。
- 本项目包含游戏任务、页面识别、OCR、输入控制、调度、诊断导出和网页管理等模块。

## 2. 当前 Git 状态

以下状态核对时间为 2026-09-14。

- 当前分支：`master`
- 当前 HEAD / `origin/master`：`a5e2d7e6b84f3545994d9bd15ca6d0ff0bcb755b`。
- 工作区当前非干净：仅有 GeneralBattle Settlement Micro-Burst v1.2 本轮 9 个授权文件的未提交修改；无 staged 文件，未 commit / push。

### 2.1 已失效的 2026-09-02 工作区清单（历史记录）

以下清单中的“当前”均指 2026-09-02 当时状态，只保留用于追溯，不覆盖上方 2026-09-14 当前事实。
  - 当前**无任何 staged 文件**（用户已把此前 staged 的 `docs/AI_CONTEXT.md` / `docs/DEVELOP_LOG.md` 取消暂存；两者现与其余 `docs/*.md` 一样是未跟踪新文件，见下方「未跟踪」）。
  - 未 staged：`script.py`、`tasks/base_task.py`、`tasks/GlobalGame/config.py`、`tasks/RyouToppa/config.py`、`tasks/RyouToppa/script_task.py`、`tasks/KekkaiUtilize/config.py`、`tasks/KekkaiUtilize/script_task.py`、`tasks/Chess/runtime/press_and_drag.py`、`tasks/Script/config_optimization.py`、`module/atom/swipe.py`、`module/atom/click.py`、`module/atom/image.py`、`module/atom/ocr.py`、`module/atom/gif.py`、`module/base/protect.py`、`module/base/utils/random.py`、`module/device/control.py`、`module/server/script_process.py`、`module/server/script_router.py`、`module/server/stats_router.py`、`tasks/Component/GeneralBattle/general_battle.py`、`tasks/Component/GeneralBattle/assets.py`（+ `gb/click.json`、`gb/gb_reward.png`、`gb/image.json`）、`tasks/RyouToppa/assets.py`（+ `dev/click.json`）、`tests/test_general_battle_timing.py`、`tasks/RealmRaid/script_task.py`、`tasks/KekkaiActivation/script_task.py`（后两个 2026-09-02 cleanup 批次 1 起，纯死代码删除，见 §4.36）。（`assets.py` / `gb/*` / `RyouToppa/*` 是**用户 2026-09-02 手动重新框选**：`C_RANDOM_LEFT` 55×370→192×506、`C_RANDOM_RIGHT` 79×388→191×518，新增 `C_RANDOM_RD` 574×314 与 `C_RANDOM_RD2` 198×425，`I_REWARD` 重新框 `(558,508,166,106)` + 重截 `gb_reward.png`，另加两条 `S_BATTLE_RANDOM_*` swipe。**2026-09-03 用户又把 `assets.py` 里的 RD/RD2 换成三个新安全区 `C_RANDOM_DEFAULT` / `C_RANDOM_SAVE_RIGHT` / `C_RANDOM_SAVE_BOTTOM` + 两个奖励布局判别标志 `I_GET_BATTLE_REWARD` / `_2`（+ 两个新 PNG），`C_RANDOM_RIGHT`/`C_RANDOM_BOTTOM` 也重框**。`general_battle.py` / `test_general_battle_timing.py` 当前状态是 **SETTLEMENT CONTRACT V3（§4.3.1 / §4.39，2026-09-03）**——强制两次推进点击 + 奖励布局感知区域策略，RD/RD2 与 HABIT profile 已从生产移除（V2 §4.28 已 Superseded）。`module/atom/{click,image,ocr,gif}.py` 的 `coord()` / `coord_more()` 现在走 `ClickSampler.sample_target(roi, name)`（T7-5，§4.44：按目标 preferred 热点 + 偏移模型，未标定 → CENTER_FALLBACK；`ocr.py` 仍先经 `_normalize_ocr_click_area()` 把 FULL 模式浮点 bbox 整数化，见 §4.43）；新增 `module/click_preference.py`（`??`）；`module/base/utils/random.py` 2026-09-02 只新增了一个 `random_normal(mu, sigma)` helper——见 §4.25。）
  - 未跟踪（`git status` 的 `??`，即新增、尚未 `git add` 的文件）：`module/fatigue.py`、`module/behavior_trace.py`、`module/atom/frame_state.py`、`module/base/frame_wait.py`、`module/server/behavior_stats.py`、`tests/test_fatigue.py`、`tests/test_kekkai_utilize_threshold.py`、`tests/test_base_task_wait_until_appear.py`、`tests/test_behavior_trace.py`、`tests/test_swipe_duration_cleanup.py`、`tests/test_rule_swipe_trace_removed.py`、`tests/test_frame_state.py`、`tests/test_frame_wait.py`、`tests/test_list_find.py`、`tests/test_manual_click_recorder.py`、`tests/test_manual_click_analyze.py`、`tests/test_runtime_roi_probe.py`、`tests/test_click_sampler.py`、`tests/test_click_profile.py`、`tests/test_click_roi_inventory.py`、`tests/test_large_click_roi_review.py`、`tests/test_general_battle_settlement.py`、`tests/test_settlement_trace_check.py`、`tests/test_ryoutoppa_c_area_1_point_opt_in.py`、`tests/test_kekkai_activation_state.py`、`tests/test_kekkai_utilize_state.py`、`tests/test_realm_raid_state.py`、`tests/test_exploration_state.py`、`tests/test_behavior_click_stats.py`、`module/click_sampler.py`、`module/click_profile.py`、`dev_tools/manual_click_recorder.py`、`dev_tools/manual_click_analyze.py`、`dev_tools/runtime_roi_probe.py`、`dev_tools/click_roi_inventory.py`、`dev_tools/large_click_roi_review.py`、`dev_tools/settlement_trace_check.py`、`docs/AI_CONTEXT.md`、`docs/DEVELOP_LOG.md`、`docs/机械性审查报告.md`、`docs/机械性修改清单.md`、`docs/Kekkai状态机静态收口.md`、`docs/RealmRaid状态机静态收口.md`、`docs/Exploration状态机静态收口.md`、`docs/状态验证与重试模式归纳.md`、`docs/ROADMAP.md`、`docs/ARCHITECTURE.md`、`docs/DECISIONS.md`、`docs/TESTING.md`、`CLAUDE.md`、`AGENTS.md`。以上均为**未跟踪的新文件**，不是「已跟踪」。
  - `.gitignore` 本轮加了 `!CLAUDE.md` / `!AGENTS.md` 例外（`# ai` 段），此前这两个文件被 `.gitignore` 忽略、`git status` 不显示；现已作为普通未跟踪文件显示，待随其余改动一起 `git add` / commit（由用户决定时机）。
  - 注：`tasks/RyouToppa/script_task.py` 的当前 diff = 更早轮次的用户 WIP（`secrets` 移除、`random_delay` 改为 import 公共版、`begin_fatigue_task` / `try_fatigue_break`）**＋ T7-3.2 改动**（加 `import ClickSampler` / `DEFAULT_PROFILES`、私有 `_click_toppa_area(index)`、`attack_area` 与 `_reopen_area_after_fire_disappear` 两处点击改走它——见 §4.31）；`flush_area_cache` 仍与 HEAD 逐字一致。
  - 注：`tasks/RealmRaid/script_task.py` 与 `tasks/KekkaiActivation/script_task.py` 此前对 HEAD 干净，2026-09-02 cleanup 批次 1（§4.36）起为 `M`——**全部是零引用死代码 / 死 import 删除**（RealmRaid：`import time` / `RealmRaid`·`AttackNumber` dead import / `medal_grid` / `is_ticket` / `medal_fire`；KekkaiActivation：`parse_rule` dead import）。`tasks/KekkaiUtilize/script_task.py` 的 `M` 里本批只多删了 1 行 `last_best_index = 99`，其余是更早轮次阈值 WIP。
  - 注（2026-09-04，TouchSwipeModel 第一阶段，§4.42 / D018）：`module/device/method/minitouch.py` 此前对 HEAD 干净，本轮起为 `M`——**纯新增**（`import math` + `_ensure_trajectory` + `swipe_minitouch_trajectory` / `_swipe_minitouch_trajectory_run`），未改任何既有函数。`module/device/control.py` 的 `M` 里本轮只多加一个 `swipe_trajectory` 方法（`Control.swipe` 等一律未动）。新增未跟踪文件：`module/device/touch_swipe_model.py`、`tests/test_touch_swipe_model.py`、`tests/test_minitouch_trajectory_executor.py`、`tests/test_control_swipe_trajectory.py`、`docs/Minitouch自定义轨迹能力审查.md`（后者是 2026-09-03 审查产物）。
  - 被 `.gitignore` 忽略但确实改动：`config/oas1.json`、`config/oas2.json`（`fatigue` 配置块）、`module/config/i18n/zh-CN.json`（疲劳文案键）。
- 整合来源：`upstream/self`
- 整合期间使用的分支：`integration/upstream-self`
- merge commit：`2cdf3a0571b0449748aabef259da5cbd2378536c`
- merge message：`merge: integrate upstream/self`
- parent 1：`880cd21fde5a5146cd923c0109b207d9ed234e3d`
- parent 2：`ce476e8943bb981c2cd91865cd734865c957c91d`
- 推送状态：已通过正常 fast-forward 推送到 `origin/master`，未使用强制推送。
- 账号轮换远程分支：`origin/zoombies-account-rotation-dailytask/synevo`
- 账号轮换分支当前提交：`267a6fe6d0fbefac2da4ded3a4d1a0f066ec1fff`
- 该提交从目标分支原提交 `921e9649b233bb65745b595f692384633a3cc9ae` 正常快进，只选择性同步通用偏移点击与安全加固，没有合入完整 `master` 历史。

## 3. 核心技术约束

### 3.1 公共随机模块

公共随机能力位于 `module/base/utils/random.py`，使用一个模块级 `SystemRandom()`。重要方法包括：

- `random_delay()`
- `random_point_in_roi()`
- `random_center_point_in_roi()`
- `random_int()`
- `random_triangular()`

新增业务随机逻辑优先复用公共随机模块，不要随意创建新的 `SystemRandom` 实例，不要无理由重新引入普通 `random` 或 `np.random`。历史轨迹算法中已经存在的 `np.random` 不要为了形式统一而进行无关重构。

### 3.2 点击确认等待

`BaseTask.appear_then_click()` 当前支持：

```python
appear_then_click(..., confirm_delay=None)
```

默认 `confirm_delay=None`，完全保持旧行为。启用后的流程为：

```text
首次识别
→ 随机等待
→ 重新截图
→ 二次确认
→ 重新生成最新坐标
→ 点击
```

不要默认给所有任务启用 `confirm_delay`。`RealmRaid`、`GeneralBattle` 等当前没有自动套用该能力。

**2026-09-02 `appear_then_click` / `confirm_delay` / reaction timing 全仓专项审查结论**（完整见 `docs/Action点击前反应时序静态审查.md`，长期契约固化到 `docs/DECISIONS.md` D001 扩写）：

- **`confirm_delay` 能否作为可识别 Point Action 的统一 reaction timing？→ PARTIAL。** 能力实现正确（fresh screenshot + 二次 `appear` + 在新帧 `roi_front` 上重新 `coord()`，`ClickSampler` 采样在 fresh + relocate 之后，无 stale-coord 风险），但**不应「统一」**：① 全仓 486 处 `appear_then_click` 调用**零处**传 `confirm_delay`（能力上线约一周零 opt-in）；② 覆盖面有边界（`action=` 分支点静态 `RuleClick` 不重定位）；③ D001「逐点显式 opt-in」无新证据推翻。
- **fresh frame 状态**：`confirm_delay` 路径满足 Fresh Frame Contract（模式 A）；默认路径（`confirm_delay is None`）不涉及非零等待、命中即点当帧，也无 stale。
- **是否新增 `reaction_delay` API？→ 否。** `confirm_delay` 就是该 primitive；再起同义名字正是 D008 禁止的（`reaction_delay` / `CLICK_REACTION_DELAY` 已有前科被删）。
- **timing 分层**：`confirm_delay`（micro，单 Action 内）/ `interval`（throttle，跨轮次）/ `wait_until_*` · `frame_wait`（state wait）/ `FatigueManager` idle·rest（macro，仅 task-cycle 安全节点、RyouToppa + Orochi/EvoZone 单人 + RealmRaid + Exploration solo + ActivityShikigami 爬塔线）—— owner 不同，不互相替代、不在同一 Action 上叠加。FatigueManager `try_break` 不进入 Action transaction（当前由构造保证）。**ActivityShikigami 爬塔线接入后，`prepare_next_action` 的旧 `random_sleep` 由 `_fatigue_owns_macro_idle` gate 关掉——同一 cycle 只有 Fatigue 一个 macro-idle owner（§4.62）。**
- **不适合 `confirm_delay` 的 Action**：Static Region（`C_AREA_*` / 九宫格 `C_PARTITION_*`）、Settlement Region（`C_RANDOM_DEFAULT` / `C_RANDOM_SAVE_RIGHT` / `C_RANDOM_SAVE_BOTTOM`，GeneralBattle 自有跨 burst 节流 + Micro-Burst fresh semantic gate）、Dynamic Search Result（`find_anyone` / `search_up_fight` `match_all`）、短生命周期按钮、poll 循环、Navigation / FSM handler、Swipe / Drag。
- **下一步**：只固化职责文档（D001 扩写 + ARCHITECTURE timing 分层，已完成），**不加任何 opt-in**；首个真实 opt-in 待 Level C，随 RealmRaid `fire()` 的 bounded 改造（R-R1）一起，`I_FIRE` 的 `confirm_delay` 参数用 manual click / BehaviorTrace 数据标定。
- **生产影响 0**，未新增测试（`tests/test_base_task_confirm_click.py` 5 用例已充分），完整回归 741/741 未变。

### 3.3 修改边界

- 不进行与当前任务无关的重构或格式化。
- 不修改用户未授权的模块。
- 不自动提交或推送，除非用户明确要求。
- 新增注释和项目文档使用中文。
- 遵循现有项目代码风格。
- 静态编译和单元测试不能替代用户明确授权的设备或游戏内测试。

## 4. 已完成的重要修改

### 4.1 RuleClick、RuleImage 与 RuleOcr

`RuleClick` 和 `RuleImage` 保留本地实现：

```text
公共模块级 SystemRandom
+
完整 ROI 内均匀随机点
```

没有采用 upstream 的中心偏置点击。

`RuleOcr` 的关键区域选择逻辑为：

```python
if self.mode == OcrMode.FULL:
    area = self.area
else:
    area = self.roi
```

坐标随机继续使用公共 `SystemRandom`。

**2026-09-04 起**：`coord()` = `ClickSampler.sample_target(_normalize_ocr_click_area(area), self.name)`。
- `_normalize_ocr_click_area()`（模块级）：FULL 模式下 `self.area` 由 `Full.ocr_full()`（`module/ocr/sub_ocr.py`）用 OpenCV 检测框写入，格式 `(x, y, w, h)` 且**通常是 numpy 浮点**；按「左 / 上 `floor`、右 / 下 `ceil`」变成**完整包住原浮点框、不因取整而缩小**的整数 ROI（贴屏幕右下边缘再裁到 1280 / 720，兜底宽高 ≥ 1）。已是整数的 ROI（非 FULL 的 `self.roi`、`RuleClick` / `RuleImage`）经此变换结果不变。`ClickSampler` / `random_point_in_roi` 的整数 ROI 契约**不放宽**（见 §4.43）。
- `sample_target()`（T7-5，§4.44；D019 / §4.50 已更新热点解析）：把整数化后的 ROI 按该 OCR 目标的 preferred 热点 + 偏移模型取点。已有人工标定则使用 `EMPIRICAL`；没有专属 preference 的 OCR 文本 = `RULE_FALLBACK` anchor `(0.58,0.59)` + `default_point`，再按 ROI short side 24/96 smoothstep 得到 effective preferred，**不恢复整 ROI Uniform**。

### 4.2 RuleSwipe

`RuleSwipe` 已完成人工融合：滑动起点和终点使用 `random_center_point_in_roi()` 进行中心偏置随机，随机源为公共模块级 `SystemRandom`。

不要把 RuleSwipe 端点退回到 `np.random` 或 `random_normal_distribution_int`。

### 4.3 GeneralBattle

`GeneralBattle` 已人工融合：

- 保留 `PREPARE_CLICK_DELAY_RANGE`。
- 保留 `SETTLEMENT_CLICK_INTERVAL_RANGE`。
- 时间随机统一使用公共 `random_delay()`。
- 每个 `BattleContext` 独立维护 settlement timer。
- 第一次 settlement click 立即执行。
- 后续点击按 timer interval 执行。
- result 与 reward 共用同一 settlement timer。

不要重新加入 `reaction_delay`、`CLICK_REACTION_DELAY` 或 BaseTask 全局自动等待。

#### 4.3.1 通用结算点击 SETTLEMENT CONTRACT V3（2026-09-03，正式生产迁移）

> **历史基线**：本节记录 V3 初始迁移；其中 Generic Result 固定双击实现已先后被 §4.66 v1、
> §4.67 v1.1 与 §4.70 v1.2 取代。当前有效结算控制流以 §4.70 / D025 v1.2 修订为准；三区域与
> Reward layout-aware policy 继续有效。

旧 `C_RANDOM_RD` / `C_RANDOM_RD2` 区域、`_SETTLEMENT_PRIMARY_PROFILE` /
`_SETTLEMENT_FALLBACK_PROFILE`（HABIT profile）**已彻底移除，不再恢复、不做兼容 alias**。
迁到 `assets` 里三个 **Large Safe Region**（不是 Point Target，不走 `appear_then_click` /
`confirm_delay`）：

- `C_RANDOM_DEFAULT` `(742,430,362,230)` —— 普通 Result / Reward 布局的默认安全推进区。
- `C_RANDOM_SAVE_RIGHT` `(1185,209,87,441)` —— Reward 未命中奖励宝袋布局标志时的右侧 fallback。
- `C_RANDOM_SAVE_BOTTOM` `(819,639,425,69)` —— 同上，底部 fallback。

采样一律整 ROI 均匀（`ClickSampler.sample(roi)` 默认 `LEGACY_UNIFORM`），本轮**不做 HABIT
偏置**（缺人工点击数据，Level C 再标定）。

**Battle Result 强制两次推进点击（用户实测业务事实，不是代码推断）**：结果页 → 第一次点击
进入奖励蹦出动画 → 第二次点击推进动画 → 页面才稳定进入奖励结算。因此
`_handle_result` 在**通用结果上下文首帧**执行不可拆的
`_advance_generic_result(context)`：采样 `C_RANDOM_DEFAULT` 点 #1 → `time.sleep` 一个结算
随机间隔（`SETTLEMENT_CLICK_INTERVAL_RANGE`，唯一允许的 handler 内阻塞 sleep）→ **重新
采样** `C_RANDOM_DEFAULT` 点 #2 → 用同一区间武装 `settlement_click_timer` → `CONTINUE`。
两次点击都是必须动作（不是 retry、不是「最多两次」），两次坐标分别独立采样。

- **通用结果 guard**（`_is_generic_result_context`）：只认 `I_WIN` / `I_DE_WIN` / `I_FALSE`
  正向命中。更宽的 `I_BATTLE_STATE_INFO` 与任务追加的特殊 marker **不纳入**——这类帧退回
  旧的单次 `settlement_click` 节流点击，保持现状。`settlement_click_timer` 已启动（本轮已
  点过 / reward 页先到）也退回单次节流。private override（`BondlingFairyland._handle_result`、
  SixRealms `moon_sea` / `peacock_kingdom`）不 `super()`，不被公共双击穿透；`super()` 调用方
  （RealmRaid 非 quick_exit / ActivityShikigami / HeroTest 非 skill-add / Orochi）经 guard
  后才走双击。
- **Reward layout-aware policy**：`_handle_reward` 命中特殊弹窗 `I_OVER_GHOST` /
  `I_GB_SKIN_CONFIRM` 即本帧 `CONTINUE`（Action → Fresh State 边界，不再同帧 region click）；
  否则 `_select_reward_region()`：`I_GET_BATTLE_REWARD` / `I_GET_BATTLE_REWARD_2`（两个
  **Reward Layout Discriminator**，不进 `page_reward.recognizer`、不是点击目标）命中任一 →
  `C_RANDOM_DEFAULT`；都没命中 → `random_int(1,100) <= 80` 走 `C_RANDOM_SAVE_RIGHT`，否则
  `C_RANDOM_SAVE_BOTTOM`。然后 `_settlement_click(context, region=...)` 节流点一次。
- `is_win`（`I_FALSE` → loss，其它 → win）、`_exit_matcher`、结算消失后 2.5s missing
  fallback、`run_general_battle` FSM 结构 **均未改**。`random_click()`（navigation）与
  Settlement Policy **分离**，SAVE 区域不接入 `random_click`。Fatigue / FrameWait / retry
  primitive / `confirm_delay` **不参与**。
- Level C 待验：0.7~1.0 是否是最合适两击间隔、`C_RANDOM_DEFAULT` 新 ROI 实际安全性、两种
  奖励布局 marker 识别稳定性、marker miss 的 RIGHT/BOTTOM fallback 是否覆盖绝大多数剩余
  布局、特殊任务真实战后 UI 有无遗漏、`I_BATTLE_STATE_INFO`-only 结果帧是否需要也纳入
  强制双击。新契约的 BehaviorTrace Level C 分析器（`dev_tools/settlement_trace_check.py` 已
  按 3 区域名 + 整 ROI 做最小更新，但不校验双击时序结构与 80/20 分流）另行设计。

### 4.4 RealmRaid

`RealmRaid` 已删除失效的 `CLICK_REACTION_DELAY`，保留：

```python
PREPARE_CLICK_DELAY_RANGE = (2.5, 3.5)
SETTLEMENT_CLICK_INTERVAL_RANGE = (0.65, 0.95)
```

不要给 FIRE 自动增加 `confirm_delay`。

### 4.5 RyouToppa

`RyouToppa` 当前保留本地完整实现。不要覆盖其 FIRE 状态机、有限重试、异常恢复和任务级等待逻辑。

### 4.6 minitouch

`minitouch` 已完成人工融合并做过设备验证。

普通点击流程：

```text
DOWN
→ WAIT 45～130ms
→ UP
```

普通点击不包含正负 2 像素的 MOVE。

压力规则：

```python
top = max_pressure
lower = max(1, top // 2)
pressure = random_int(lower, top)
```

异常握手 `max_pressure <= 0` 时回退为 1。MuMu 曾返回：

```text
^ 10 540 960 0
```

因此该环境实际压力为 1。压力、按压时长、swipe interval 和 drag interval 均使用公共模块级 `SystemRandom`，swipe/drag MOVE interval 为 6～15ms。

### 4.7 诊断导出

`module/server/diagnostic.py` 与 `module/server/home_router.py` 已人工融合。

- 所有日志写入 ZIP 前必须经过 `_scrub()`。
- 脱敏覆盖密码、令牌、授权头、Cookie、API Key、账号、用户名、网易账号字段、代理认证、邮箱、Windows 用户目录、URL 查询参数和 URL 编码敏感值。
- summary 继续按白名单输出。
- ZIP 最多保留最近 5 个。
- 接口为 `POST /home/export_diagnostic`。
- 诊断包只生成本地文件，不主动上传。

已知架构问题：当前 endpoint 尚未确认存在统一有效鉴权。不要在不相关任务中顺手重构整个鉴权系统。

### 4.8 账号轮换分支安全加固同步

`origin/zoombies-account-rotation-dailytask/synevo` 已选择性同步以下通用能力：

- 公共随机、RuleOcr、RuleSwipe 和 minitouch。
- BaseTask 二次确认点击。
- GeneralBattle 与 RealmRaid 点击时序。
- AntiBan 作息约束与 KekkaiUtilize 最小运行间隔。
- diagnostic 本地 ZIP 脱敏导出。
- 对应 43 项回归测试。

该分支自己的账号轮换、MultiAccountEvo、GeneralInvite 和 i18n 内容均保留。没有同步 low-spec、NemuIPC、scrcpy、Image/OCR RPC、Chess、Costume 或 RyouToppa 业务链。

### 4.9 疲劳 / 发呆 / 休息系统

核心在 `module/fatigue.py` 的 `FatigueManager`，按 `config_name` 单例（`get_fatigue_manager` 注册表），多实例互相隔离。配置在 `tasks/GlobalGame/config.py` 的 `FatigueConfig`，默认 `enable=False`，关闭时 `try_break` 立即返回 `None`、不抽随机、不睡眠，完全保持旧行为。当前接入 `BaseTask.begin_fatigue_task` / `try_fatigue_break` 的任务 = `RyouToppa` + `Orochi` / `EvoZone` 的**单人（run_alone）**路径 + `RealmRaid` 主循环 + `Exploration` 的**单人（ALONE）**路径（§4.60：Safe Point = `_maybe_boss_cycle_fatigue()`，在 `run_on_exp_entrance` / `run_on_exp` 顶部、刚完成 Boss 循环回到外层稳定页时）；均只在各自完整业务循环结束、回到稳定可继续页面之后触发，组队 / member / wild 路径不接（见 §4.53 / §4.56 / §4.60 与 `docs/DECISIONS.md` D001）。

已确认并应保持的语义：

- **active time 与 wall clock 分离**：任务墙钟（`start_time + limit_time`）只决定 deadline，idle/rest 计入墙钟；`task_active_elapsed()` / `global_active_elapsed()` 只累计真正 active 的时间，idle/rest/调度空闲/隔夜等待都不计入，用于疲劳计算。三者互不等价。
- **`activity_state` 四态与 fatigue 关系**：`active`（TaskFatigue / GlobalFatigue 增长）、`idle`（明显恢复 TaskFatigue、轻微恢复 GlobalFatigue）、`rest`（明显恢复 Task + Global）、`scheduler_idle`（`_global_activity_depth <= 0`，两个 active elapsed 都冻结、不增疲劳；短空档只冻结，长空档让 GlobalFatigue 自然恢复）。
- **scheduler_idle 自然恢复**：`OAS 进程运行 ≠ 一直 active`；任务之间可能空闲数小时。`end_global_activity()` 把 depth 降到 0 时进入 scheduler_idle，记录入口 `_scheduler_idle_started_at`（monotonic 墙钟，与 active elapsed 无关）、`_scheduler_idle_global_start`（G0）、`_scheduler_idle_recovery_applied`。前 `scheduler_idle.recovery_delay_minutes`（默认 5）分钟只冻结；超过后 `ratio = 1 - exp(-(t - 5) / scheduler_idle.recovery_tau_minutes)`（默认 tau=34），`target = G0·ratio`，只把 `target - 已应用` 的增量追加进 `_global_recovery`（并 `min` 到当前 `RawGlobal`，不产生未来额度）。惰性结算：`global_fatigue()` 每次读取都调 `_apply_scheduler_idle_recovery()`，结果只由起点与真实经过时间决定，读多少次都不会重复恢复。`begin_global_activity()`（depth 0→1）先落定本轮恢复再清空快照并结束 session，下一次进入建立全新独立 baseline；不连续的多段 scheduler_idle 不拼接、各自重新计 5 分钟等待期。scheduler_idle 不动 TaskFatigue，不改 active elapsed 定义。本轮不做 fatigue 持久化——人为关闭 OAS 实例即 FatigueManager 生命周期结束，重启从 `GlobalFatigue = TaskFatigue = 0` 重新初始化。
- **recovery clamp**：`_accumulate_recovery` 每次累计后都 `min(当前 RawFatigue, 旧 recovery + 本次)`，不产生“未来恢复额度”。
- **运行时 L 归一化**：`_normalize_task_recovery()`（`_task_recovery = min(_task_recovery, _raw_task_fatigue())`）在 `set_load_factor()`、`update_config()`、`begin_task()` 同名任务分支中调用。降低 `L` 会立即把 `_task_recovery` 重新钳制到当前 `RawTask`，消除“恢复死区”；提高 `L` 不会凭空增大 recovery；只影响任务 recovery，不动 `_global_recovery`。不修改疲劳公式和概率参数。
- **`try_break` 的 `completed` + `should_resume`**：中断保护。`completed` 仅在 `self._sleep(duration)` 正常返回后置 `True`。`finally` 中当 `completed and (should_resume is None or should_resume())` 才 `_resume_after_break()`，否则调用 `end_global_activity()` 收口。`BaseTask.try_fatigue_break` 传入的 `should_resume` 在“睡过任务 deadline”时返回 `False`。
- **idle 触发采用事件率 / hazard 模型（不是每节点固定概率）**：
  - `IdleScore = 0.8·TaskFatigue + 0.2·GlobalFatigue`（权重未改）。
  - `idle_intensity(score) = 1 / (1 + exp(-k·(score - F0)))`，范围 (0,1)，`k` / `F0` 沿用原值 `0.11` / `52.0`（配置字段从 `idle.probability.steepness/midpoint` 平铺为 `idle.steepness/midpoint`，数值不变）。
  - `idle_rate_per_hour = rate_base + (rate_max - rate_base)·idle_intensity`，`rate_base` 默认 `1.5`、`rate_max` 默认 `4.0` 次/小时。低疲劳保留 `rate_base` 的自然走神，高疲劳趋近 `rate_max`（理论上限，非实际频次）。
  - 单安全节点概率 `P_node = 1 - exp(-idle_rate · Δt / 3600)`，`Δt` = 本节点 `task_active_elapsed()` 减去 `_last_idle_check_task_elapsed`（秒）。节点越密 `Δt` 越小、`P_node` 越低，整体 idle 频率由时间而非节点数决定。
  - `_last_idle_check_task_elapsed`：`__init__` 与 `begin_task` 切换 / restart 时归零（与 `TaskFatigue` 生命周期一致，页面切换不重置）；每个 idle 判断后推进到当前 `task_active_elapsed()`；rest 触发后也推进（rest 不计入 active，故后续 `Δt` 天然不含 rest 时间，也不保留 rest 前的旧 `Δt`）。
  - idle 时长三角分布 `_duration_range`：`(minimum_seconds, high, mode)`。idle 默认 `minimum_seconds=15`、`mode_minimum_seconds=25`、`mode_maximum_seconds=70`、`maximum_seconds=120`、`range_floor_ratio=0.12`；`high` 按 span 随疲劳升到 `maximum_seconds`，`mode` 从 `mode_minimum_seconds` 线性移到 `mode_maximum_seconds`。低疲劳均值约 23 秒、TaskFatigue≈50 约 45 秒、满疲劳约 68 秒（`high`=120），多数落在 20~60 秒，高疲劳主要集中在 45~90 秒，硬上限 120 秒不再被突破。idle 上限历史为 180 → 150 → 120，`maximum_seconds` 仍可配置。`RestFatigueConfig` 同步加了 `mode_minimum_seconds`，默认等于其 `minimum_seconds`，rest 时长行为不变。
  - 旧的 `idle.probability.maximum`（Pmax=0.18）不再参与 idle 生产计算，已从 idle 配置移除；`FatigueProbability` 类保留，仍由 `rest.probability` 使用。
  - `L` 仍只经 `TaskFatigue → IdleScore → idle_intensity → idle_rate` 间接影响 idle，未直接乘 rate 或 `P_node`，前端 Slider 语义不变。
  - rest 触发逻辑、`RestScore`、rest probability、rest 时长、cooldown 本轮未改。
  - 参考验证：L=1.30、连续 active 60 分钟、n 增至 ~170、GlobalFatigue 按公式增长时，第一小时 idle 理论期望约 `2.1` 次（未计 recovery，计入后略低）。
- **终止语义**：
  - 正常结束且任务仍有效 → 恢复 `active`，两个 active segment 重新置位。
  - stop / cancel / deadline（`should_resume()` 返回 `False`）→ `end_global_activity()`，终态 `scheduler_idle`。
  - 睡眠期抛异常（`completed` 仍为 `False`）→ 同样 `end_global_activity()`，异常正常向上传播；被中断的 break 不施加 recovery、不启动 cooldown。
  - 所有终止路径都不会错误重新开启 task/global active segment，终止后推进时钟不再增长 active elapsed。
- **`load_factor_preview()`（P0-D 后端）**：`FatigueManager.load_factor_preview()` 固定按 `L=0.80~1.30`、步进 `0.05` 输出 11 档。参考场景为 active 60 分钟、`n=170`、`GlobalFatigue=10`、`TaskRecovery=0`（贴近高频副本约 20~30 秒一轮）。每档字段：`factor` / `task_fatigue` / `idle_score` / `idle_intensity` / `idle_rate_per_hour` / `idle_probability_at_25s`（`25` 秒参考节点）。均复用生产 `idle_score()` / `idle_intensity()` / `idle_rate_per_hour()` / `_node_probability_from_rate()`，无独立公式。旧字段 `idle_probability` 已移除（不再复用旧名表达新含义）。`ui_snapshot()` 和 `ScriptProcess._default_fatigue_state()` 都带 `fatigue_load_factor_preview`，随每个 `{'fatigue': ...}` 负载下发；preview 与当前 `L` 无关，`set_fatigue_load_factor` 不重算（无害）。前端需从 `idle_probability` 迁移到 `idle_rate_per_hour`（+ 可选 `idle_probability_at_25s`）。
- **运行时下发链路**：`Script._publish_fatigue_state` 每 2 秒推 `ui_snapshot()` 到 `state_queue`；`Script._listen_runtime_commands` 处理 `set_fatigue_load_factor` 命令并回推快照；`ScriptProcess.coroutine_broadcast_state` 缓存 `fatigue_state` 并广播；WS 连接、`stop`、`refresh_fatigue_state` 各自补发一次。REST `PUT /{script}/global_game/fatigue/load_factor` 在进程存活时下发命令，进程 INACTIVE 时刷新默认状态。

不要在本轮之外继续调整疲劳核心算法、公式或概率参数。OASX Flutter 前端不在本工作区，属独立仓库。

### 4.10 随机源一致性修复

2026-08-30 收敛了三处同名冲突与重复实现，均为等价替换，无行为变化：

- `module/base/protect.py`：原 `random_delay` 与公共 `module/base/utils/random.py` 的 `random_delay` **同名但语义相反**（前者 `sleep()` 返回 `None`，后者返回 `float` 不 sleep），是静默误用风险。已重命名为 `sleep_random_delay`，内部改为复用公共 `random_delay` 取值后再 `sleep`；`random_sleep` 的概率抽样也改用 `random_delay(0.0, 1.0)`，`import random` 已移除。外部原本零 import 该函数，唯一链路是 `random_sleep` ← `tasks/ActivityShikigami/base_act.py`，未受影响。
- `tasks/RyouToppa/script_task.py`：删除本地 `_random = secrets.SystemRandom()` 与重复的 `random_delay`（语义与公共版相同），改为 import 公共实现；`import secrets` 一并移除。4 个调用点均显式传参、签名兼容，未改动。滑动坐标的 `random.randint` 按既有行为保留，`import random` 保留。
- `tasks/Chess/runtime/press_and_drag.py`：`random.randint(6, 15)` → 公共 `random_int`，`random.uniform(0.001, 0.004)` → 公共 `random_delay`，`import random` 已移除。

`_press_and_drag_minitouch` 终点两次固定 `wait(140)` **有意保留**并补了中文注释：它是拖拽落点的 settle 等待，游戏需要稳定停留才确认放置，属可靠性时序而非拟人化延迟。修改它会影响 Chess 真机拖拽落点，仅凭静态测试无法验证，不得在未授权真机测试的情况下变更。

### 4.11 KekkaiUtilize 结界蹭卡选卡与可靠性修复

> **选卡策略部分已被 §4.41「单向分区 PASS 搜索」取代（2026-09-03，`docs/DECISIONS.md` D017）**：
> `_select_optimal_resource_card` / `_current_select_best` / `_reselect_best_card`（global-best +
> 回选）/ `_card_rank` / `order_cards` / `order_targets`（KU 版）/ `_reward_threshold` /
> `_reaches_reward_threshold` 及 `utilize_best_*` / `utilize_last_*` / `ap_max_num` / `jade_max_num`
> 已删除。下文只保留可靠性修复部分（剩余时间兜底 / `switch_friend_list` 超时 / `receive_guild_assets`
> 提前 break / 随机源统一 / `swipe_adb` 有意保留）仍然有效。

2026-08-30 修复了一处功能缺陷和四处可靠性 / 一致性问题。

**选卡缺陷（原 P0）**：点开一张结界卡同时就是选中它，而 `ImageGrid.find_everyone` 按 y 坐标升序返回（位置序，非收益序），遍历结束时选中的是最后点开的那张而不是最优的。原 `_select_optimal_resource_card` 只要 `jade_max_num > 0` 就返回 True，于是会带着次优卡进入结界。典型失败：确认 5 星斗鱼 134 后仍去点 4 星太鼓 59，最终寄养到 59 那张。

现行方案（用户确认的 C 方案，与交接文档 §7.4「收益达到阈值即寄养」一致）：

- `UtilizeConfig` 新增 `taiko_reward_threshold` / `fish_reward_threshold`，**默认 76 / 151 等于六星满值，默认行为与改动前完全一致**。调低（如 67 / 134）可提前停止并减少翻页。
- 原类常量 `STRATEGY_MAX_REWARDS` 与 `_is_strategy_maximum_reward` 已移除，改为 `_reward_threshold()` + `_reaches_reward_threshold()` 读配置。浏览中命中阈值立即 `return True`，此时当前选中即目标，点击=选中不再是问题。
- 新增 `_card_rank()`：斗鱼给体力、太鼓给勾玉，**收益数值不可跨类型比较**，跨类型优劣一律按 `order_cards` 的既有偏好顺序排名。
- 扫描过程同时记录 `utilize_best_*`（最优）与 `utilize_last_*`（最后点开）。两者一致则无需回选。
- 新增 `_reselect_best_card(friend)` 兜底回选：回到列表顶部重扫，**按收益值匹配而非位置匹配**（好友列表排序不稳定，位置不可靠），用 `CARD_TIER_INFO` 档位上限剪枝跳过不可能达标的卡，OCR 校验后才算成功，120 秒超时 + 21 屏上限。
- 怠惰模式路径不变，不做回选。

**可靠性修复**：

- `check_utilize_add` 的寄养剩余时间：`ocr_duration` 解析失败返回 `timedelta(0)`，与真的剩余 0 无法区分，原代码直接用它算 `next_run` 会设成当前时刻，导致任务被立即重复调度形成热循环；而 `min_run_interval` 默认 0 不兜底。现按 `UTILIZE_RES_TIME_FALLBACK = 5 分钟` 兜底，并加 `UTILIZE_RES_TIME_MAX = 12 小时` 上界防止 OCR 误读把任务推迟数天。原 `isinstance` 分支是死代码（`ocr_duration` 恒返回 timedelta），现已成为有效的防御判断。
- `switch_friend_list` 原 `while 1` 无总超时，目标分组图标识别不到就无限点击。现加 `SWITCH_FRIEND_LIST_TIMEOUT = 20` 秒并抛 `GamePageUnknownError`。**该异常在两个调用点分别接住**（`run_utilize` → `_record_utilize_failure`，`_reselect_best_card` → `return False`），避免升级为重启游戏。签名从谎报的 `-> bool` 改为 `-> None`。
- `receive_guild_assets` 原忽略 `check_and_get_guild_rewards` 返回值固定往返 `max_tries` 次，现一个都没收到即 `break`。
- `perform_swipe_action` 的随机源改用公共 `random_int`，魔法数字提取为 `SWIPE_START_X_RANGE` / `SWIPE_START_Y_RANGE` / `SWIPE_DISTANCE`；`run` 的怠惰骰子与经验壶重试次数也改用公共随机。该文件已无普通 `random`。

**`swipe_adb` 有意保留**：`perform_swipe_action` 使用 `self.device.swipe_adb` 而非公共 `self.swipe`。查 `26715a72` 确认引入该方法时就选定 adb swipe，公共实现从创建起即为注释状态，属有意选择而非回退遗留。好友列表对滚动距离敏感，改回公共滑动会改变实际位移，必须先真机验证，已在方法 docstring 中写明。

**未验证**：回选路径与两处超时分支均无真机验证。默认阈值 76 / 151 下回选会被经常走到（满值卡少见），首次实跑应关注日志中的 `回选最优结界卡` 段；若不稳可把阈值调低到 67 / 134，绝大多数情况会在第一趟命中阈值而走不到回选。

### 4.12 `wait_until_appear_then_click` 参数绑定缺陷修复

2026-09-01 修复 `tasks/base_task.py` 的 `wait_until_appear_then_click` 参数绑定缺陷。

原实现按位置调用 `self.wait_until_appear(target, wait_time)`，而 `wait_until_appear` 的签名是 `(target, skip_first_screenshot=False, wait_time=None)`，第二个位置参数是 `skip_first_screenshot`。两个后果：

- **超时计时器从不建立**：`wait_time` 在被调方恒为 `None`，`wait_timer = None`，超时分支永远短路。调用方要求的「最多等 N 秒、超时返回 `False`」退化为「一直等到 `stuck_record_check` 抛 `GameStuckError`」（60s / 300s）。契约从「返回 False」变成「抛异常」。
- **首轮使用旧帧**：任何非零 `wait_time` 使 `skip_first_screenshot` 为真值，第一次循环跳过截图，直接拿调用前遗留的帧做识别。

现改为关键字传参 `self.wait_until_appear(target, wait_time=wait_time)`，并在调用处补中文注释说明位置传参的陷阱。

该方法当前**全仓零调用方**，属潜伏缺陷而非线上故障，改动不在任何现有任务执行路径上，风险接近零。测试见 `tests/test_base_task_wait_until_appear.py`（5 用例）。测试内置 `_LoopNotBounded` 哨兵异常并限制截图次数——缺陷复现时循环不退出，不设界会让测试挂死而非失败。已做双向验证：临时回退修复后为 3 failures + 1 error（error 即哨兵触发，实证死循环），恢复修复后 5/5 通过。

不要把 `wait_until_appear` 的参数顺序改成 `(target, wait_time, skip_first_screenshot)`——它有其他调用方依赖现有顺序，正确做法是调用侧显式关键字传参。

### 4.13 BehaviorTrace v1（行为观测日志）

2026-09-01 新增只读、可关闭、低侵入的运行观测层，为后续 State→Action→Verify、列表 changed/stable、WaitPolicy、RetryPolicy、Recovery、任务状态机重构建立数据基础。**只记录，不干预。**

**模块**：`module/behavior_trace.py`，单文件，仅依赖标准库（`json` / `threading` / `datetime` / `pathlib`）。不 import Config / Device / Timer / BaseTask，避免循环依赖；仅在自禁用告警时惰性 import `module.logger`（该 import 无环且再套一层 try/except）。形态仿 `module/fatigue.py`：按 `config_name` 的进程内单例注册表。

**API（保持极小）**：
- `configure_behavior_trace(config_name, enabled)`：进程启动阶段一次性注入开关，幂等，只更新 `enabled`，不重建实例、不重读磁盘。
- `get_behavior_trace(config_name)`：取进程内单例；未经 configure 的场景（standalone / 测试）返回默认关闭实例。
- `BehaviorTrace.record(event, *, task='', action='', target='', result='ok', elapsed_ms=None, extra=None)`：`ts` 内部生成，`config` 实例持有，`task` 缺省用 `set_task()` 设的当前任务名。
- `BehaviorTrace.set_task(name)` / `reset_behavior_traces()`（后者仅测试用）。
- **v1 不实现** `timed()` context manager / 装饰器 / `TraceHandle`。Control 已有现成 `elapsed`，Script.run 直接 `perf_counter` 首尾差。

**配置**：`tasks/Script/config_optimization.py` 的 `Optimization.behavior_trace_enable: bool = False`，读取路径 `config.script.optimization.behavior_trace_enable`。用 Chinese `description` 直写（仿 `FatigueConfig.enable` / `emulator_window_minimize`），**不新增 i18n 键**。缺字段自动取默认 False，无迁移。**进程级参数，只在 `Script.__init__` 读一次，运行中不动态重载**。

**接入点（4 个，全部在批准范围内）**：
- `module/device/control.py` `Control.click` / `long_click` / `swipe`：各在现成 `elapsed` 计算 + `logger.info` 之后加一行 `record('ACTION', ...)`。**不新增 try/except、不改异常传播、不改 retry、不改 logger 行为**。
- `script.py` `Script.run`：`finally` 里写一条 `TASK` 事件（task / result ok|fail / 整段 episode 耗时）。仅新增局部 `trace_result` 记账，异常传播、`_handle_task_exception` 入参与返回值均不变；`ScriptError` / `RequestHumanTakeover` / generic 走 `exit(1)`（SystemExit）时 `finally` 仍会写一条 `result='fail'` 的 TASK 事件。

**事件类型**：v1 只有 `ACTION`（click/swipe/long_click，**仅底层动作正常返回后记录，`result` 恒为 `ok`**）和 `TASK`。**不实现** `WAIT` / `ERROR` / `RETRY` / `TIMEOUT` / `RECOVERY` / `TRANSITION` / `ACTION_START/END`，也不实现 `ACTION result=error`（底层动作抛异常时 `record` 根本不会执行，这是刻意的——异常仍由现有 logger / retry / exception handler 处理）。

**字段**：`ts` / `config` / `task` / `event` / `action` / `target` / `result` 必有；`elapsed_ms` / `extra` 可选。**不记** `state_before` / `state_after` / `retry_count`（当前无统一 State / Retry 模型，不为填字段反向改任务架构）。

**输出**：`log/behavior/<config_name>_YYYY-MM-DD.jsonl`，每行一条 JSON，`ensure_ascii=False`，`extra` 用 `json.dumps(default=str)` 兜底。文件 `buffering=1` 行缓冲（每条写完即刷到 OS，非 fsync，进程被杀不丢尾部）。按日期跨天轮转。每个 config 独立文件——OASX 是 `multiprocessing spawn` 每 config 一进程，文件名带 `config_name` 即无跨进程竞争；进程内仍有一把 `threading.Lock`。**已知：`module/logger.py:cleanup_logs` 只清理 `log/` 根文件和 `log/error/`，`log/behavior/` 子目录不会被自动清理**，v1 可接受（JSONL 很小），后续可给 `cleanup_logs` 加分支。

**异常隔离（强制）**：`record()` 全程 `try/except BaseException`。任何内部失败（建目录 / open / write / 磁盘满 / 序列化 / 编码 / 轮转）→ `_broken=True` 自禁用 → 之后所有 `record()` 首行返回 → 尽力 `logger.warning` 一次（再套 try/except）。`_broken` + `_in_record` 双重防 `record → logger → record` 递归。**Trace 失败不抛给 Control、不导致 Task fail、不改 click/swipe/long_click 返回值**。

**v1 已知覆盖缺口**（刻意保留，写在 `Control.swipe` 注释里）：
- `KekkaiUtilize.perform_swipe_action` / `KekkaiActivation.check_card_num` 直接调 `self.device.swipe_adb(...)`，绕过 `Control.swipe`，v1 不记录这两类好友列表滑动。后续做 Kekkai 状态驱动重构时再决定是否在 `Adb.swipe_adb` 接入。
- `Control.drag` 属已确认无主要生产消费者的死路径，不接。
- 底层动作异常不产生 `ACTION` 事件（见上）。

**行为影响**：
- `behavior_trace_enable=False`（默认）：`record()` 首行布尔判断即返回，不建目录、不开文件、不构造事件。实测约 0.13 µs/次（本机，仅供数量级参考）。
- `enable=True`：动作执行完成、`logger.info` 之后同步 `json.dumps` + 行缓冲 `write`，实测约 17 µs/次（本机，仅供数量级参考）。**不改控制流、不加 sleep、不改点击/滑动顺序、不改截图/OCR 次数**；开销在动作关键时序路径之外。**不宣称「完全零时序影响」**——开启时有很小的同步结构化日志开销。

**下一步（不在 v1）**：`WAIT` / `ERROR` / `TRANSITION` / `RETRY` 事件复用同一行结构，由对应 Policy / 状态机改造那一层各自加 `record(...)`，不需要改 BehaviorTrace 本身。

### 4.14 `Control.swipe` duration 跨后端契约澄清（RyouToppa 原行为保留）

2026-09-01。**先完成了 BehaviorTrace `set_task()` 生命周期只读复核，结论为无需修改**（`Script.run` 的 `finally` 在所有出口——正常完成、`_handle_task_exception` 返回 True/False、`exit(1)` 引发的 `SystemExit`——都会执行 `trace.set_task('')`，且顺序是先 `record('TASK', ...)` 再 `set_task('')`，TASK 事件保留正确任务名；任务之间的 Control 动作正确得到 `task: ""`，不会继承上一个任务名）。

随后处理 `Control.swipe` 的 `duration` 参数。经过一次「删除 RyouToppa duration 采样」的尝试并**已收回**——那次删除对 minitouch 是 no-op，但对 adb / uiautomator2 会把 RyouToppa 列表滑动时长从传入值改成后端默认，属真实行为变化。当前无法真机验证，**故最终选择「只澄清契约、不改任何调用方行为」**：

- **`Control.swipe` 的 `duration` 后端消费边界**（全仓源码核实）：
  - `swipe_uiautomator2(self, p1, p2, duration=0.1)` — **消费**
  - `swipe_adb(self, p1, p2, duration=0.1)` — **消费**（`Control.swipe` else 分支先 `duration *= 2.5`）
  - `swipe_minitouch(self, p1, p2)` — **忽略**（无形参）
  - `swipe_scrcpy(self, p1, p2)` — **忽略**
  - `swipe_window_message(self, startPos, endPos)` — **忽略**
- **`Control.swipe` 保留 `duration` 形参**（adb / uiautomator2 依赖），新增一段中文 docstring 说明上述边界。**未改任何后端实现**，未实现 minitouch 的 duration 支持。
- **`tasks/RyouToppa/script_task.py:flush_area_cache` 保持原样**：`attempt == 1` 用 `random_delay(0.342, 0.362)`、其他 `attempt` 用 `random_delay(0.349, 0.355)`，`self.device.swipe(..., duration=duration, ...)` 原样传参。起点 / 终点 / `distance` / `control_name` / retry / `_wait_for_ryou_toppa_page` 状态等待全部未动。
- **最终状态**：所有控制后端下 RyouToppa 列表滑动行为与本轮之前完全一致；仅新增了 `Control.swipe` 的接口 docstring 与 `tests/test_swipe_duration_cleanup.py` 契约测试。
- **默认 minitouch 环境下**：`Control.swipe(..., duration=X)` 的 `duration` 不影响真实 minitouch 滑动时序（`swipe_minitouch` 不接收它，`insert_swipe` 的 MOVE 间隔仍是 `random_int(6, 15)`）。RyouToppa 传的随机 duration 只在 adb / uiautomator2 后端才有实际语义。

### 4.15 `RuleSwipe` 死代码清理

2026-09-01。删除 `module/atom/swipe.py` 中全仓零生产调用方的死代码：

- **`RuleSwipe.trace()`**：全仓（`module/` `tasks/` `script.py` `dev_tools/` `tests/`）grep `.trace(` 无任何调用；且该方法本身已损坏（`start_pos, end_pos = self.coord()` 解 4 元组会 `ValueError`）。生产滑动一律 `RuleSwipe.coord()` → `Control.swipe` → 各后端自身实现（minitouch 走 `insert_swipe`），不经过 `trace()`。
- **`is_default_mode` / `is_vector_mode`**：两个 `cached_property` 仅被 `trace()` 内部使用，无外部消费者，一并删除。
- **删除的 import**：`import random`、`from math import dist`、`from module.base.decorator import cached_property`、`from module.atom.cBezier import BezierTrajectory`（均只服务 `trace()`）。
- **保留**：`from module.base.utils.random import random_center_point_in_roi`（`coord()` 依赖）、`from module.logger import logger`（本文件既有的未使用 import，非本次死路径造成，按范围不动）。
- **`module/atom/cBezier.py` 未删**：删除 `trace()` 后该文件变为全仓无消费者的孤儿（`module/base/cBezier.py` 是**另一个文件**，仍被 `module/device/method/windows_impl.py:swipe_window_message` 使用，不能动）。是否删除 `module/atom/cBezier.py` 留作独立决定，本轮只移除对它的无效 import。
- **`windows_impl.py:swipe_window_message` 未动**：它内联实现了同型贝塞尔轨迹逻辑（用 `module.base.cBezier.BezierTrajectory` + 自己的 `random`），是 window_message 后端的真实生产路径，与 `RuleSwipe.trace()` 无关。
- **行为影响**：无。删除的都是零调用方死代码，`RuleSwipe` 的生产 API（`__init__` / `coord()`）与 `RuleSwipe` 的全部消费者（各任务 `assets.py` 的 `RuleSwipe(...)` 构造 + `BaseTask.swipe`）不受影响。

### 4.16 List Changed / Stable 独立视觉状态组件（T4-1）

2026-09-01。新增 `module/atom/frame_state.py`，为后续「列表状态驱动」改造建立可复用的 `changed` / `stable` 基础语义。**当前零生产消费者**，未接入任何任务。

- **纯图像组件**：只处理调用方传入的帧，不截图 / 不 sleep / 不做超时轮询；只依赖 `numpy` 与 `module.base.utils` 的 `area_limit` / `image_size`。不依赖 Device / BaseTask / Timer / OCR / BehaviorTrace。
- **`frame_difference(a, b, roi=None, pixel_threshold=15) -> float`**：ROI 内逐像素取各通道绝对差的最大值，`> pixel_threshold` 记为变化像素，返回变化像素占比 `[0.0, 1.0]`。`DEFAULT_PIXEL_THRESHOLD = 15` 是通用保守值，**不代表任何游戏页面最佳参数**。
- **`FrameStateDetector(changed_threshold, stable_threshold, stable_frames, roi=None, pixel_threshold=15)`**：三个判定阈值**必须显式传入**（无游戏默认值）。`reset(baseline)` / `update(frame) -> FrameStateResult(changed, stable, difference, stable_count)`；不显式 `reset` 时首个 `update` 帧作为基线。
- **语义**（详见 DECISIONS D010）：`changed` 相对基线，一旦成立就**锁存**、`reset` 前不回退（即使画面回到基线）；`stable` 基于**相邻帧**差异，连续 `stable_frames` 帧安静才成立，任一次相邻明显变化清零 `stable_count`；两者相互独立。
- **ROI**：`None`=全图，或 `(x1, y1, x2, y2)`（与 `module.base.utils.crop` / `area_*` 一致）。宽高必须为正，越界部分按 `area_limit` clamp，完全无重叠报 `ValueError`。禁止硬编码任何任务 ROI。
- **异常**：帧为 None / 非 ndarray / 维度非 2·3 / 两帧形状不一致 / 非法 ROI → `ValueError`（不 silent resize）。
- 测试 `tests/test_frame_state.py`（25 用例）：差异算法、ROI 隔离、噪声、score 恒 `[0,1]`、灰度、异常输入、以及 detector 的一直静止 / 变化后稳定 / 持续变化 / 变化后回基线 / stable_count 重置 / reset / 首帧基线等状态转换。

### 4.17 BehaviorTrace 点击位置统计后端 v1

2026-09-01。为 OASX「配置详情 → 统计 → 点击分布」页面提供后端数据，只做后端、不改 Flutter 前端。

- **BehaviorTrace ACTION 加坐标**：`module/device/control.py` 的 `Control.click` / `Control.long_click` 在现有 `record('ACTION', ...)` 调用里多传 `extra={'x': x, 'y': y}`。`x` / `y` 是 `ensure_int` 之后、**实际提交给控制后端执行的最终坐标**（不是 ROI 中心 / 模板原坐标）。**未改 `module/behavior_trace.py`**——`record` 早已有 `extra` 字段；事件类型仍只有 `ACTION` / `TASK`（D004 不变）。不新增 coord() 调用、不新增随机、不新增 screenshot、不改点击顺序 / 异常传播。旧 JSONL（无 `extra.x/y`）保持兼容。本轮**不记录 swipe / drag 轨迹**。
- **只读 Reader**：`module/server/behavior_stats.py` 的 `read_behavior_clicks(script_name, target_day) -> dict`。逐行读取 `log/behavior/<config>_<date>.jsonl` 单个文件一次，只保留 `event=='ACTION'` 且 `action in {click, long_click}` 且 `extra.x/y` 为有效数值的记录。文件不存在 / 空 / 全坏行 → 返回空结果（不报错）；单行坏 JSON / 缺字段 / 类型错误 → 跳过并计入 `skipped_lines`。**无缓存、无后台线程、无定时扫描、无数据库、无 SSE**——接口未被请求时零额外开销。
- **`{script_name}` 即完整 config_name**：Reader 用 `ConfigManager.validate_config_name(allow_template=False)` 校验并**原样使用**，**不做** `log_service` / `log_stats` 那种「按 `_` 截首段去运行时后缀」——config_name 允许含 `_`（如 `test_01` / `account_group_1`），截断会读错文件（2026-09-01 收口，见 DECISIONS D011 与 DEVELOP_LOG）。`log_stats._normalize_script_name` / `log_service.normalize_script_name` 未动（它们服务 `<date>_<script>.txt` 人读日志名解析）。
- **HTTP 接口**：`GET /stats/{script_name}/behavior/clicks?date=YYYY-MM-DD`（FastAPI，加在既有 `stats_router.py` 的 `stats_app` 里，风格对齐 `/stats/{script_name}/dates`）。`script_name` 经 `ConfigManager.validate_config_name(allow_template=False)` 校验（router 层非法 → 422；Reader 层非法 → `BehaviorStatsError(400)`）；`date` 经既有 `_parse_target_date`（非法 → 422）；`_behavior_file_path` 再用 `resolve().relative_to(BEHAVIOR_LOG_ROOT)` + `path.name == 期望文件名` 机械兜底防路径穿越。`validate_config_name` 已拒 `.` / `/` / `\` / 控制字符，路径穿越用例全部在读文件前被拒。
- **响应**（顶层一次返回 `screen`，JSONL 每条不重复存宽高）：
  ```json
  {"config":"oas1","date":"2026-09-01",
   "screen":{"width":1280,"height":720},
   "summary":{"total":N,"click_count":..,"long_click_count":..,"task_count":..,"skipped_lines":..},
   "tasks":["RealmRaid",".."],
   "points":[{"x":842,"y":512,"task":"RealmRaid","action":"click","target":"I_FIRE","ts":"..","elapsed_ms":112}]}
  ```
  `screen` 用 `CANONICAL_SCREEN_WIDTH/HEIGHT = 1280/720`（`module/device/screenshot.py` `check_screen_size` 强制的逻辑分辨率，asset ROI 与 Control 坐标都在此空间，minitouch 设备缩放在 Control 之后）。`points` 保持 JSONL append 顺序（即动作时间顺序）；`tasks` 按首次出现顺序。任务筛选 / 连线 / tooltip / 热力图全部由前端本地完成，后端只返回原始点击点。
- 设计契约见 `docs/DECISIONS.md` D011。测试 `tests/test_behavior_click_stats.py`（24 用例）：`Control.click/long_click` 记录最终坐标（含 caller 传 float 时取 int）、底层动作抛异常不生成 ACTION、disabled 零 IO；Reader 的正常文件 / 旧格式无坐标 / 多任务顺序 / 空文件 / 缺文件 / 坏 JSON 行 / 缺字段 / 非法 config / 非法 date / 路径穿越 / point 顺序 / summary / 响应结构 / elapsed_ms 取 int / **含 `_` 的 config（`test_01`、`account_group_1`）读自己的文件且不被截断误读到别的 config**。
- **前置：`behavior_trace_enable` 必须开**（2026-09-04 排障）。OASX「统计 → 点击分布」页显示 0 的常见原因不是链路 bug，而是 `config/<config>.json` 的 `script.optimization.behavior_trace_enable = false`（D004 默认关）—— `BehaviorTrace.record()` 空操作、`log/behavior/*.jsonl` 从不写、reader 返回 `total:0`、页面如实显示 0。整条链（reader / API / OASX controller·models·panel）已逐层核验正确（`read_behavior_clicks` 用真实 schema JSONL 实测 `total=4`）。**已把 `config/oas1.json` / `config/oas2.json` 的该项翻 `true`**（gitignored）；该开关只在脚本进程创建时读一次（`script.py:80`），改后需**重启对应 config 的运行**才生效，且开关打开前的旧点击无法补录。详见 `docs/DEVELOP_LOG.md` 2026-09-04「OASX 点击分布显示 0」条。

### 4.18 FrameState Wait Layer（`module/base/frame_wait.py`）

2026-09-01（会话内称 T4-2）。在 `FrameStateDetector`（§4.16，纯帧差算法）之上加一层「连续取帧 + 有限 timeout」的有限等待，为后续 `list_find` / Kekkai 列表状态驱动迁移提供设备无关、可单测的基础设施。**生产消费者（2 个，2026-09-08）**：① `KekkaiUtilize._perform_search_swipe`（K3，§4.41，标准 PASS + minitouch 的 swipe settle，结果参与控制流——失败 → `PassResult.ABORT`）；② `BaseTask.list_find` 翻页 settle（§4.49，T5-2，结果**不参与控制流**——纯 W1 结构性 settle，取代固定 `sleep(0.8~1.3)`）。其余任务仍零消费者，且**不因为全仓 swipe 已迁 TouchSwipeModel 就给每个 swipe 自动套 FrameWait**（见 §4.49）。

- **模块位置**：`module/base/frame_wait.py`。放 `module/base/` 而非 `module/atom/`——`atom` 层「不负责设备轮询 / 超时」（见 ARCHITECTURE §2、DECISIONS D010），`module/base/` 已是控制流基础设施所在（`retry.py`）。`base → atom` 单向 import，`module/base/__init__.py` 只 import `.utils` / `.grids`，`frame_wait` 不被它加载，无环。
- **`wait_for_changed_and_stable(baseline, frame_provider, *, changed_threshold, stable_threshold, stable_frames, timeout, roi=None, pixel_threshold=DEFAULT_PIXEL_THRESHOLD, poll_interval=0.0, clock=time.monotonic, sleeper=time.sleep) -> FrameWaitResult`**。
- **职责分层**：detector 只做帧差与 `changed`/`stable`（本层复用它、不另维护第二套状态）；本层做取帧 / 轮询 / 计时 / 超时；调用方（未来的 Task）决定 baseline / ROI / 阈值 / `stable_frames` / `timeout` / retry / recovery；`Control` 只做输入。
- **`baseline` 由调用方传入**，本层不自截——正确链路是 `baseline = screenshot() → action() → wait(baseline=baseline)`。
- **`frame_provider: Callable[[], np.ndarray]` 注入**，无 Device 硬依赖；生产层以后传 `self.device.screenshot`（自带 `_screenshot_interval` 节流），测试传 fake。
- **`clock` / `sleeper` 可注入**：项目 `Timer` 内部用 `time.time()` 不可 mock，故本层取时 / sleep 都走注入 callable，做确定性 timeout 测试。
- **`poll_interval` 默认 `0.0`**：生产 `frame_provider`（`device.screenshot`）已节流，不叠第二次固定 sleep；仅 `> 0` 时才调 `sleeper`。
- **阈值必须显式传**：`changed_threshold` / `stable_threshold` / `stable_frames` 无业务默认，数值校验交给 `FrameStateDetector`（不重复两套）。`pixel_threshold` 沿用 `frame_state.DEFAULT_PIXEL_THRESHOLD`。
- **`timeout` 必须为有限正数**：非正数 / bool / 非数值 → `ValueError`；`poll_interval` 为负 → `ValueError`。无 `while True` 无界循环；另有 `_MAX_POLLS = 1_000_000` 兜底，注入的 clock 不推进时抛 `RuntimeError` 而非死循环。
- **超时返回结果、不抛异常**：到 `timeout` 时返回 `timed_out=True` 的 `FrameWaitResult`。
- **成功严格等于 `changed and stable and not timed_out`**（见 D010：`stable=True` 单独不算成功）。`FrameWaitResult`（`@dataclass(frozen=True)`）字段：`changed` / `stable` / `timed_out` / `last_difference` / `stable_count` / `frames_checked`（调用 `frame_provider` 的次数，不含 baseline）/ `elapsed`（按注入 clock）/ `success`（property）。
- **三种结局可区分**：成功（`changed=T, stable=T, timed_out=F`）；失败 A「从未变化」（`changed=F, timed_out=T`，即使 detector 内部 `stable=T`）；失败 B「变化但未稳定」（`changed=T, stable=F, timed_out=T`）。
- **异常透传**：`frame_provider` 抛出的异常、帧 shape 不一致 / 非法 ROI / 非法阈值（`FrameStateDetector` 抛的 `ValueError`）都原样向上传播，**不伪装成 timeout**。
- **不碰 BehaviorTrace**：不产生 `WAIT` / `TIMEOUT` / `TRANSITION` 事件，不扩 D004。
- 契约见 `docs/DECISIONS.md` D012。测试 `tests/test_frame_wait.py`（20 用例）：变化后稳定→成功、从未变化→超时且 `changed=F`、持续变化→超时且 `stable=F`、变化后回基线→`changed` 锁存仍成功、`stable_count` 中途重置后重新累计、timeout 边界（注入推进 clock，无真实 sleep）、`frame_provider` 第 N 次抛异常透传、帧 shape 不一致 / 非法 ROI / 非法阈值 / 非法 `timeout`·`poll_interval` 校验分工、`frames_checked` 不含 baseline、`poll_interval>0` 用注入 sleeper 且默认 0 不 sleep、ROI 只圈定等待范围、不推进 clock 触发 `_MAX_POLLS`、结果 dataclass 冻结。

### 4.19 `BaseTask.list_find` 迁移前静态收口（characterization，会话内称 T4-3 / 对应 ROADMAP T5-2 前半）

2026-09-01。为把 `list_find` 翻页后的固定等待迁移到 FrameState 等待层做准备，本轮**完全不改 `list_find` 生产行为**，只审查其真实语义 + 全部生产调用方 + 补 characterization 测试 + 判断是否抽 seam。

- **`list_find` 当前真实控制流**（`tasks/base_task.py` 696-733，本轮逐行核实）：`for _ in range(max_swipe)` 有界循环 → 每轮先 `self.screenshot()`（首轮不跳过）→ 按 `target.is_image` / `target.is_ocr` 调 `target.image_appear(...)` / `target.ocr_appear(...)` → 结果是 `tuple` 即命中 `break` → 否则 `target.swipe_pos(...)` 算端点 → `self.device.swipe(p1=, p2=)` → `sleep(random.uniform(0.8, 1.3))` → 下一轮。命中 `return result`（原样返回识别结果元组），未命中耗尽 `max_swipe` 后 `return False`。`if not target: return False`（0 截图）。
- **等待方式**：翻页后唯一的等待就是 `sleep(random.uniform(0.8, 1.3))`（`from time import sleep` + 模块级 `import random`，普通 `random` 非公共 `random_delay`）。下一轮 `self.screenshot()` 里 `device.screenshot` 自带 `_screenshot_interval = Timer(0.1)` 节流，但被 0.8~1.3s 的固定 sleep 完全覆盖。注释自带「待优化」。
- **无界循环审查**：`list_find` 自身**不可能**无界——`for _ in range(max_swipe)` 硬上限（默认 10，`navbar` / `Dokan` 传 3）。**不读 `RuleList.is_bottom`**，没有到底部检测，纯靠 `max_swipe` 收敛；末轮未命中仍会 swipe + sleep（无「末轮跳过」优化）。本轮未加 retry count / bottom detection。
- **已知瑕疵（本轮不修，characterization 照实锁定）**：① 末轮未命中仍 swipe + sleep；② `RuleList.ocr_appear` 在「无 OCR 结果」时 `return 0, 0`，是 tuple，被 `list_find` 当成命中坐标 `(0,0)` 直接返回；③ `list_appear_click` 的 `isinstance(appear, tuple) and interval`——`interval` 为空时即使命中也返回 False 不点击（真实调用方 `navigator` / `Dokan` 都传了 interval，未触发）。
- **生产调用方（全仓确认，共 8 处 + 2 个包装入口）**：`list_find` 直接调用方 8 处——`Orochi` / `FallenSun` / `EvoZone` / `EternitySea` 的 `check_layer`（OCR 层列表，`L_LAYER_LIST`）、`GeneralRoom.check_zones`（队伍/副本列表 `L_TEAM_LIST`）、`WeeklyPurchase/mall/navbar` 5 处 `_enter_*`（图片导航条 `L_RM_NAVBAR`，`max_swipe=3`，其中 `_enter_honor` 传 `name=['honor','duel']` 走图片列表 list-name 分支）。包装：`list_appear_click`（内部调 `list_find`）被 `GameUi/navigator.py:341`（`interval=interval or 0.8`）与 `Dokan:521`（`interval=3`, `max_swipe=3`）使用。全部靠返回值 `tuple`（命中坐标）/ `False`（未命中）判断，无一依赖固定 swipe 次数或副作用。
- **KekkaiActivation / KekkaiUtilize 不是 `list_find` 消费者**：它们各自有 `check_card_num` + `perform_swipe_action`，直接 `self.device.swipe_adb(p1, p2, duration=...)`（自采样 duration），是「列表内 swipe + 等待」的**平行实现**，绕过 `list_find` 与 `Control.swipe`。迁移 `list_find` 不自动覆盖它们。
- **等待分类**：`list_find` 翻页后的 sleep 属**视觉结构等待**（等列表滚动停稳）→ 未来 `frame changed + stable` 接入点。`check_layer` / `check_zones` / `click_and_check` 等**外层**用 `while 1: screenshot; if appear(...)` 等按钮 / 页面出现的循环属**语义等待**，继续用 `appear` / `wait_until_appear` / `wait_until_disappear`，**不**规划成 FrameState。
- **是否抽 seam：否**（当时结论；2026-09-08 已按 §4.49 直接迁移，不抽独立 seam）。原理由见 DECISIONS D013——未来正确链路要求「动作前 baseline 显式传入」（D012），而 `list_find` 中可用的动作前帧是 `self.device.image`（为识别而截，非为等待基线而截）。**2026-09-08 复核确认该顾虑可解**：`list_find` 循环里 `self.screenshot()` → `image_appear`/`ocr_appear` → `swipe_pos` → `self.device.swipe` 之间**没有再截图**，`self.device.image` 在 swipe 时仍是那一帧、未被污染，`settle_baseline = self.device.image` 是干净的动作前帧（无需像 K3 那样重截）。真实 ROI 用 `RuleList.roi_back`，阈值 provisional（Level C 标定），因为 FrameWait 结果不参与控制流，阈值取错只影响多等 / 少等、不影响正确性。
- **迁移状态（2026-09-08，§4.49）**：翻页 `sleep(random.uniform(0.8, 1.3))` → `wait_for_changed_and_stable(settle_baseline, self.device.screenshot, roi=RuleList.roi_back 换算, changed/stable/frames/timeout/poll_interval=provisional)`，**结果丢弃**（settle / timeout 都回循环顶重新识别，`max_swipe` 仍是唯一收敛边界，无 BOTTOM / ABORT）。`list_find` 是 FrameWait 第 2 个生产消费者。
- 测试 `tests/test_list_find.py`（27 用例，`22 → 27`）：见 §7 / §4.49。

### 4.20 点击空间随机 / 偏移机制全仓审查（结论）

2026-09-01。对「目标原始坐标 → 最终提交给 `Control.click` / `long_click` 的坐标」之间所有位置变化实现做了一次静态全仓审查（未改任何代码）。核心结论（作为未来 preferred-center 模型的基线事实，长期边界见 DECISIONS D014）：

- **点击落点 = Rule 对象 ROI `(x, y, w, h)` 内一次独立均匀随机**（`random_point_in_roi`），`x` / `y` 各自 `SystemRandom.randrange` 独立采样。`RuleImage.coord` / `RuleClick.coord` / `RuleOcr.coord` / `RuleGif.coord` / `RuleLongClick`（继承 RuleClick）全部走这一套。`long_click` 与 `click` 用**同一套坐标生成**，只按压时长不同。
- **空间随机在整条链路上只发生一层**（`Rule.coord()`）。`BaseTask.click` / `appear_then_click` 只透传；`Control.click` / `long_click` 仅 `ensure_int`（int 截断），**不做任何空间偏移**；默认 `click_minitouch` 只随机压力 / dwell（时间），无 `.move()`、无 ±px；`CommandBuilder.convert` 是旋转 + 分辨率缩放（坐标转换，非随机）。**全仓 0 处默认「双重随机 / double jitter」。**
- **中心偏置（`random_center_point_in_roi`，3 次采样均值的 Bates 分布）只用于 `RuleSwipe` 滑动端点，点击路径 0 处使用。** 它是「每次采样更靠近 ROI 几何中心」的分布形状（A 类），**不是**「某目标长期维持一个偏好热点」（B 类）。
- **全程无状态**：无 preferred center / per-target / per-session 热点、无 EMA / AR(1) / rolling mean / click history / persisted center。同一按钮连点 N 次 = N 次 i.i.d. 均匀采样。
- **固定坐标 / 固定几何中心点击**大量存在（`random_click()` 安全大区、登录固定点、Chess / Secret / QuickLoadout / WeeklyTrifles / navigator fallback / GeneralBattle 绿名 / `list_find` 命中 等，几十处），多为「识别框中心 / 锚点 + 常量偏移」的确定性几何。
- **任务私有的随机空间偏移只有 1 处**：`tasks/SixRealms/common.py`（购买技能：`front_center()` 基础上 `random.randint` 左移 + 纵向抖动，普通 `random`）。
- **一改影响面最大的公共函数**：`random_point_in_roi`、`RuleImage.coord` / `RuleClick.coord`（≈2064 个 `RuleImage` + 291 个 `RuleClick` + 292 个 `RuleOcr` asset，491 处 `appear_then_click` + 223 处 `self.click`）。
- **ROI 体系**：项目只有事实上的 Detection ROI（`roi_back`）和 Click ROI（`roi_front` ≈ 模板框 / asset 框），**没有系统化的 Safe Click ROI**（内收 padding）机制。
- **未来学习 preferred center 的数据缺口**：BehaviorTrace 每条 click 有 `ts/config/task/target/x/y`，但**缺 page 身份与 ROI 几何**，且 `target` 大量混叠（`'Click'` / 跨页同名）；`list_appear_click` 等裸 `device.click` 无 `control_name`。最稳身份键是 `task + page + target + 记录时 ROI`，存量 JSONL 无法回填。
- 审查中发现 5 个 latent bug（`Control.multi_click` 传参错误、`control_method=='scrcpy'` 时 click 静默回退 adb、`click_nemu_ipc` 相对 `Control` 不可达、`RuleClick.move()` 翻倍 bug、`RuleList.ocr_appear` 无结果返回 `(0,0)` 被当命中）——**仅记录，未修**，待确认后另开任务。

### 4.21 人工点击采样器 ManualClickRecorder v1（`dev_tools/manual_click_recorder.py`）

2026-09-01。为「统计用户真实 preferred center / spread」提供**人工物理鼠标点击**的采集工具。**只观察、不发送任何输入**，与自动 BehaviorTrace 完全分离（长期边界见 DECISIONS D014）。

- **位置**：`dev_tools/manual_click_recorder.py`（校准工具，不进 `BaseTask` / 生产链）。运行：`toolkit/python.exe dev_tools/manual_click_recorder.py --config oas1 [--scene RealmRaid --target I_FIRE --roi 790,470,130,90] [--hwnd <句柄>]`。
- **窗口定位**：优先 `--hwnd`（直接当游戏画面窗口）；否则当 config 配了 `script.device.handle` 时复用 `module/device/handle.py` 的 `Handle.screenshot_handle_num`（与 OAS 截图 / `window_message` 点击同一窗口）；再兜底按窗口标题扫描 MuMu 顶层 + 找 `MuMuPlayer` / `NemuPlayer` / `MuMuNxDevice` 游戏 child（多开且未配 handle 时会警告改用 `--hwnd`）。启动时用 `viewport_sanity`（复用 `Handle.screenshot_size` 的判定思路：窗口物理尺寸 ≈ 1280×720）做闸门，选错窗口直接拒绝启动（可 `--force` 跳过）。
- **坐标转换**：本进程不设 DPI awareness（与 OAS 一致，DPI-unaware）。鼠标钩子 `MSLLHOOKSTRUCT.pt` 与 `GetWindowRect` 同一虚拟化空间，换算是**纯比例** `client_x / win_w * 1280`、`client_y / win_h * 720`，**不乘 `window_scale_rate`**（该值只作诊断展示 / 存档）。每次点击前重新 `GetWindowRect`，因此窗口移动 / resize 后仍正确。
- **只采目标视口内的真实左键**：`WH_MOUSE_LL` 全局钩子，`WM_LBUTTONDOWN` 时取 `pt` + `flags`；`flags & LLMHF_INJECTED` 的注入事件默认跳过（`--include-injected` 可留，记 `injected: true`）；点在视口外（`inside_viewport=False`）不写；回调只读、始终 `CallNextHookEx` 放行，异常也吞在回调里，不影响用户鼠标。
- **输出**：`log/manual_click/<config>_<日期>.jsonl`（与 `log/behavior/` 分开），行缓冲，跨天轮转。每条含 `ts / source="manual" / config / screen_x,y / client_x,y / x,y（1280×720 逻辑）/ window_width,height / logical_width,height / inside_viewport / injected`，可选 `scene / target / roi / u / v / inside_roi`（传 `--roi` 时；`u=(x-roix)/roiw`、`v` 同理，不 clamp）。config 名用 `ConfigManager.validate_config_name(allow_template=False)` 校验并原样保留（不按 `_` 截断），输出路径 `relative_to` 兜底防穿越。
- **v1 明确不做**：不每次截图 / 不 OCR / 不模板匹配 / 不自动猜 page / target、不热力图、不 ClickProfileManager、不学习、不改任何自动点击参数。`scene / target / roi` 全靠人工传入。
- **生命周期**：Ctrl+C / 异常 / 目标窗口消失 → `finally` 一定 `UnhookWindowsHookEx` + 关文件 + 打印摘要（样本数、ROI 内 / 外、`mean_u/v`、`std_u/v` Welford）。写文件失败会打印错误并停止采样（前台工具，不像 BehaviorTrace 那样静默吞）。
- 测试 `tests/test_manual_click_recorder.py`（31 用例，纯函数，不装真实钩子）：见 §7。

### 4.22 人工点击日志离线分析器 `dev_tools/manual_click_analyze.py`（burst collapse + 重新统计）

2026-09-01。把 `ManualClickRecorder` 采到的原始日志清洗成更接近「独立鼠标落点」的数据再统计。**纯离线只读**，不启动任何设备 / 服务，不改生产代码，**不修改原始 JSONL**（派生结果写 `log/manual_click_analysis/`）。

- **burst 合并（链式）**：时间顺序里相邻两点满足 `dt ≤ time_threshold_ms` 且 `distance ≤ distance_threshold_px` 且标签（`scene`/`target`/`roi`，都存在且不同才算冲突）兼容 → 归同一 burst。判据是 **current vs previous**，不是 vs burst 首点——一串每步都在阈值内的小幅漂移整体算一个 burst，即使首尾距离已超阈值。
- **代表坐标默认取 burst 第一个点**（用户移动到位后的首次按下，后续连点通常没重新瞄准）；同时算 `centroid_x/y` 供对照。
- **敏感性分析固定跑 4 组**（`300/3`、`500/5`、`800/5`、`500/8` ms/px）+ 用户传入的组，输出每组 `raw_click_count` / `burst_count` / `collapse_ratio` / 归一化中心 / std。参考分析参数取 **`500ms / 5px`**——**仅本轮参考，不是项目长期标准**。
- **统计**（对独立落点）：count、mean/std(pstdev)/median、`p05/p25/p75/p95`（x、y 各一套）、`normalized_mean_x/y`（÷1280 / 720）、径向分位 `r50/r75/r90/r95`。
- **ROI-relative 统计只用 ROI 内落点**（2026-09-02 修正）：`landing_stats(points, roi=...)` 传 `roi` 时，**默认只用 `inside_roi` 子集**算全部字段（含 mean/std/median/percentile/径向 + `mean_u/v`、`std_u/v`、`median_u/v`、`p05/p25/p75/p95 u/v`）；ROI 外样本不删除、不 clamp，通过 `outside_count`/`outside_ratio`/`outside_points`（原始坐标）单独报告。`count` = inside 数，`total_count` = 全部数。此前是对全部点一起换算（少数外点会污染 preferred center / spread）。
- **calibration 前缀识别是启发式、可覆盖**：`detect_calibration_prefix`（首次相邻间隔 `>=8s` 且前缀含屏幕边缘点）**只在 `yys1_2026-09-01` 上验证过，不是通用协议**；`--calibration-count N` / `analyze(calibration_count=)` 可显式覆盖跳过启发式；`summary["calibration"]` 报 `detected_by`（auto_heuristic/override/disabled）与 `excluded_range_ts`，用前人工核对。
- **burst 行为**：`click_count` 直方图（1 / 2 / 3 / 4-5 / 6+）、多连点 burst 数、其中的 raw click 总数、多连点 burst 的 duration 与最大鼠标移动距离统计。
- **粗分区**（`--y-split`，默认关闭）：按水平线粗分上 / 下两区，**纯几何切分，不代表任何游戏页面语义**——2026-09-01 曾用固定 `y_split=330` 直接把「上区」标成「进攻按钮」、「下区」标成「Large Area」，核对真实资产源码后确认是错误标签（上区其实是 `C_AREA_1` 目标卡片，真进攻按钮落在下区、和 Large Area 混在一起了），已改正：`region_split` 的输出不再附加页面语义。
- **三簇分析**（`--three-cluster` + `--seed-a/b/c`，`kmeans_clusters` + `detect_calibration_prefix` + `transition_counts`）：先用确定性 k-means(3) 验证空间簇数与簇间时间转移关系，再决定页面归属，取代「固定分割线直接贴页面标签」的错误做法。对 `yys1_2026-09-01`（剔除开头 6 条窗口校准点击后）三簇 = `C_AREA_1` 目标卡片 `(0.501,0.289)`（对 `C_AREA_1.roi_front` 的 inside-only ROI-relative `mean_uv≈(0.63,0.62)`、inside 101 / outside 6）、真进攻按钮 `(0.527,0.545)`（无可靠 ROI，只给 screen 统计）、Large Area `(0.742,0.672)`，转移序列验证「返回列表→点卡片→进攻→战斗结算连点→…」循环成立。拿到真进攻按钮运行时 ROI 后，用 `--three-cluster --roi x,y,w,h` 即可重算 cluster_B 的 ROI-relative preferred center（调用链已就绪）。
- **输出**：`log/manual_click_analysis/<stem>_dedup.jsonl`（参考阈值下每 burst 一条派生记录，含 `burst_id/start_ts/end_ts/click_count/duration_ms/x/y/centroid_x/y/max_step_distance/source` + 继承的 `config/scene/target/roi/u/v`）与 `<stem>_summary.json`（全部统计）。
- **本轮不做**：不拟合 Gaussian / Student-t / AR(1) / EMA，不建 ClickSampler / ClickProfileManager，不改任何自动点击参数。无新增第三方依赖（无 matplotlib → 只出统计不出散点图）。
- 对当前用户样本 `log/manual_click/yys1_2026-09-01.jsonl` 的分析结论（**实验结果 / 当前样本，不是长期 ADR**）见 `docs/DEVELOP_LOG.md` 2026-09-01 / 2026-09-02 对应条目。
- 测试 `tests/test_manual_click_analyze.py`（39 用例）：见 §7。

### 4.23 只读 Runtime ROI Probe `dev_tools/runtime_roi_probe.py`

2026-09-02。为拿到真进攻按钮 `RealmRaidAssets.I_FIRE` 在寮突破弹窗里被 `match()` 动态改写后的**运行时 `roi_front`**，给下一轮 Button preferred center 计算提供准确 ROI。**只截图 + 只识别 + 只打印/记录，绝不点击、不发送任何输入、不主动启动 MuMu / 游戏 / OAS。**

- **窗口定位**复用 `dev_tools/manual_click_recorder.py` 的 `resolve_viewport_hwnd` / `viewport_sanity` / `_read_handle_field`；**截屏**复用生产 `module/device/method/windows_impl.py:Window.screenshot_window_background`（用 `SimpleNamespace` 顶替 `self`，不构造 `Window`/`Handle`/`Device` 实例——`Device.__init__` 在模拟器未运行时会主动 `emulator_start()`，明确避免）；**识别**用 `RealmRaidAssets.I_FIRE.match(frame)`（未改 `RuleImage` 任何公共 API），匹配后直接读 `roi_front`。
- **失败即清晰报错退出**（退出码 3），不重试、不崩溃；图像识别服务（`get_image_client()` 的 Image RPC）连不上也视为「设备/服务不可用」，提示用户确认 OAS 主进程已运行，不自己启动。**未输出 score/similarity**（拿它要绕开 `match()` 掏 RPC 内部 result，为守「不改公共 API」本轮放弃）。
- **CLI**：`--config <name> --target I_FIRE [--hwnd N] [--count 1|N --interval 2]`；默认 `--count 1`（等价 `--once`）。输出 `log/manual_click_analysis/runtime_roi/<target>_<日期>.jsonl`（字段 `ts/config/target/matched/viewport_hwnd` + 命中时 `roi_front/center/template_width/template_height`；未命中也记一条）。`summarize_roi_samples()` 汇总 `matched/unmatched` 计数、`unique_roi_count`、`unique_rois`、`x_min..h_max`、`stable`（要求 ≥1 次命中且 unique ≤ 1）。
- **建议连采 5~10 次弹窗**判断运行时 ROI 是否稳定；多值时只报范围，不据此强行归一化（时间匹配留后续）。
- **未接入真机**：本轮只做了失败路径冒烟，未连真实图像识别服务、未拿到真实 ROI。
- 测试 `tests/test_runtime_roi_probe.py`（11 用例，纯函数不装真实设备/RPC）：见 §7。

### 4.24 ClickSampler v1（点击坐标空间采样的唯一公共入口）—— T7-1 第 1 阶段

2026-09-02。新增 `module/click_sampler.py`，把「ROI → 最终整数点击坐标」的空间随机收敛到一个公共层。**本轮只做等价抽象层，不改变任何生产点击分布**（回归 363→381，`git diff` 见下）。

- **API**：`ClickSampler.sample(roi, *, strategy=LEGACY_UNIFORM) -> (int, int)`。`roi` 沿用项目既有 `(x, y, w, h)` 整数格式；每次传当前 ROI（如 `RuleImage.roi_front` 在 `match()` 后被 `_update_roi_front` 改写的值），**不缓存**。轻量：无 IO / 无日志 / 无历史 / 无锁 / 无 numpy / 无新建对象。
- **唯一正式策略 `LEGACY_UNIFORM`**：直接转调 `module.base.utils.random.random_point_in_roi(roi)`——**同一个函数、同一个模块级 `SystemRandom`、逐字等价**（x/y 在 ROI 半开区间各自独立均匀）。`random_point_in_roi` 的 `TypeError`（非整数 ROI）/ `ValueError`（w·h ≤ 0）原样透传。这条整数 ROI 契约是 D007 起就有的硬约束，本层不放宽；`RuleOcr` FULL 模式的浮点 OCR bbox 在 `RuleOcr.coord()` 自己的边界规范化后才进来（§4.43）。
- **预留但未实现**：`STRATEGY_HABIT` / `STRATEGY_STRICT` / `STRATEGY_UNIFORM` 三个语义名占位，调用即抛 `NotImplementedError`；未知策略抛 `ValueError`。preferred center / Gaussian / mixture / Safe ROI / padding / tail / 历史状态 / target profile / 人工热点默认值 **全部留给下一轮 Click Profile / Strategy**，本轮 0 实现。
- **接入点（最小改动）**：`module/atom/click.py`（`RuleClick.coord` + `coord_more`）、`image.py`（`RuleImage.coord` + `coord_more`）、`ocr.py`（`RuleOcr.coord`）、`gif.py`（`RuleGif.coord`）——把 `random_point_in_roi(...)` 换成 `ClickSampler.sample(...)`，其余不动。`RuleLongClick` 继承 `RuleClick.coord`，无需改。业务层调用不变（仍是 `target.coord()`）。`coord_more`（roi_back）全仓无调用方，顺带一起路由使入口收敛干净。
- **未接入 / 保留**：`tasks/Component/GeneralInvite/general_invite.py:_random_point_in_area`（task 私有、非 `Rule.coord` 主路径，§4.20 已记录）；`SixRealms` 私有 `front_center` ± 偏移（非主路径，明确不动）；`RuleClick.move()`（历史死代码，明确不动）；`random_center_point_in_roi`（只服务 `RuleSwipe` 滑动端点，非点击）。
- **边界**：`Control` / minitouch / scrcpy / window_message / BaseTask / BehaviorTrace **完全未改**——最终点击 x/y 的空间随机只在 ClickSampler 一层发生，后端只执行坐标（见 `docs/DECISIONS.md` D014）。BehaviorTrace 仍记录 Control 收到的最终坐标，schema 不变。
- **人工热点数据未写入生产**：卡片 / 普通按钮 `≈(0.62,0.70)` / Large Area `≈(0.74,0.67)` / Tiny 居中略右——仍只在 `docs/DEVELOP_LOG.md` 实验结论里，**没有**变成 `RuleClick` / `RuleImage` / `ClickSampler` 的默认值。（卡片热点 T7-3.1 已按真实 `RyouToppa.C_AREA_1` RuleClick ROI 基准收口为 `wide_card ≈ (0.58,0.59)`，旧记的 `(0.68,0.53)` 是对更大的手工估卡片区算的，坐标基准不同——见 §4.30。）
- 测试 `tests/test_click_sampler.py`（19 用例）：见 §7。
- **T7-5（2026-09-04，§4.44）起**：`Rule*.coord()` 的默认不再是 `ClickSampler.sample(roi)` = `LEGACY_UNIFORM`，而是 `ClickSampler.sample_target(roi, rule.name)` = `HABIT` + `TargetPreference`。**D019（2026-09-08，§4.50）起**热点优先级为 `EMPIRICAL > RULE_FALLBACK`，未标定 target 使用规则锚点 `(0.58,0.59)` 并按 ROI 尺寸适配；`LEGACY_UNIFORM` 保留给兼容 / characterization / fallback，但**不再是普通 Point 生产默认**。

### 4.25 ClickProfile + HABIT / STRICT / UNIFORM + Safe ROI —— T7-1 第 2 阶段

2026-09-02。给 ClickSampler 加上「参数是什么（ClickProfile）+ 怎么采样（Strategy）+ 安全边界（Safe ROI）」三块能力。**默认生产点击仍完全是 `LEGACY_UNIFORM`**——`Rule*.coord()` 源码未再改、只传 `roi`（默认策略）。非 LEGACY 策略只有逐调用点显式 opt-in 才走到：`HABIT` 现有 GeneralBattle Settlement RD（§4.28）与 `RyouToppa.C_AREA_1`（§4.31）两个生产消费者；`STRICT` / `UNIFORM` 仍零消费者。

- **职责分离**：`module/click_profile.py` 的 `ClickProfile`（`@dataclass(frozen=True)`）只描述参数、**不产生坐标**；`module/click_sampler.py` 读 profile、算 Safe ROI、按策略采样。ClickProfile 字段全部 ROI 相对（`preferred_u/v`、`core_sigma_u/v`、`medium_sigma_u/v`、`core/medium/tail_weight`、`safe_margin_u/v`、`max_attempts`、`provisional` 标记），不存绝对屏幕坐标。构造即校验（`preferred∈[0,1]`、`sigma≥0`、`weight≥0` 且和为正、`margin∈[0,0.5)`、`max_attempts≥1`），非法抛 `ValueError`（不静默 clamp）。
- **随机源**：`module/base/utils/random.py` 新增 `random_normal(mu, sigma)`（复用同一模块级 `SystemRandom` 的 `_rng.gauss`，`sigma<0`→`ValueError`，`sigma=0`→返回 `mu`）。无 numpy、不新建 RNG。
- **Safe ROI**：`_safe_roi(roi, profile)` = 原 ROI 按相对 margin 左右上下各内收，收成宽或高 < 1px 抛 `ValueError`。只有「原 ROI + 相对 margin」这一基础能力，**没有**相邻控件识别 / 视觉语义 / 风险地图。
- **HABIT**：三成分 mixture——`_choose_component`（按归一化累计权重）先选 `core`/`medium`/`tail` 其一，再采样一次（不是三个 offset 叠加）。`core`/`medium` = ROI 相对独立二维正态（`random_normal(preferred_u, sigma_u)` × `random_normal(preferred_v, sigma_v)`，映射回原 ROI 像素），候选点必须落在 Safe ROI 内，否则有限次 rejection 重采（`max_attempts`），用尽则 fallback 到「热点 u/v 夹进 `[margin, 1-margin]` 再投影进 Safe ROI」的**单个确定点**——不是对越界样本做边界 clamp，避免四边堆积。`tail` = Safe ROI 内均匀（仍在安全区，不产生真正误点），权重很小。
- **STRICT**：给 tiny/small/高风险目标，可靠性优先。用 HABIT 的机制但强制 `without_tail()`（tail 权重清零）；resolve 出的 profile 若 `core_sigma_u/v > STRICT_MAX_CORE_SIGMA(0.12)` 直接 `ValueError`（拒绝 `wide_card`/`large_area` 这类宽 profile）。`profile=None` 时用内置 `strict` profile（居中、core σ=0.05、无 tail）。
- **UNIFORM**：Safe ROI 内均匀。与 `LEGACY_UNIFORM` 数学同族但语义不同——`LEGACY_UNIFORM` 是「兼容旧行为」的默认 fallback（不收边、整 ROI），`UNIFORM` 是「该目标业务语义就是全区域均匀」的显式声明（经 Safe ROI，默认 profile margin 0.06）。
- **v1 默认 profile**（`DEFAULT_PROFILES`，结构化默认，**不自动作用于任何任务**）：`wide_card ≈ (0.58,0.59)`（T7-3.1 起，见 §4.30）、`normal_button ≈ (0.62,0.70)`、`large_area ≈ (0.74,0.67)`、`small ≈ (0.54,0.50)`、`tiny ≈ (0.52,0.50)`、`strict`、`default`——**T7-3.1 起 8 个条目全部标 `provisional=True`**（个人实验样本 / 保守工程默认，均未经通用验证）。sigma 有序：tiny 最窄 → small → normal_button → wide_card → large_area 最宽。这些是「第一版个人先验」，不是所有用户通用真值。
- **ClickProfileManager**：内存注册表（`get(name)` 找不到回退 `default`），无配置加载 / 无用户 override / 无 identity 树。`resolve_profile(None|名字|ClickProfile实例)` 统一入口。LEGACY_UNIFORM 路径**完全不经过** profile 解析（`test_legacy_uniform_still_delegates_directly_no_profile` 锁）。
- **接入边界**：`module/atom/{click,image,ocr,gif}.py` 本轮**未再改**，仍 `ClickSampler.sample(roi)` 默认 `LEGACY_UNIFORM`。启用某个具体目标（`--` opt-in）是 T7-1 第 3 阶段 + 真机验收。`Control` / minitouch / 后端 / `BehaviorTrace` 未改。
- 测试 `tests/test_click_profile.py`（44 用例）：见 §7。

### 4.26 点击 ROI 尺寸静态普查 `dev_tools/click_roi_inventory.py`

2026-09-02。用只读 AST 工具普查全仓「可能最终用于点击的 ROI」的真实尺寸分布，为 Tiny / Small / Normal / Large 的尺寸边界提供数据依据。**未改任何 Asset / 生产代码 / ClickSampler / ClickProfile；阈值仍是候选，未落地任何默认行为。**

- **工具**：`dev_tools/click_roi_inventory.py`——`ast.parse` 扫 `tasks/` + `module/atom/`，抽出 `RuleClick` / `RuleImage` / `RuleLongClick` / `RuleOcr` / `RuleGif` 会进 `.coord()` 的那个矩形（Click/LongClick/Image/Gif 取 `roi_front`；Ocr 取 `roi`，`mode=Full` 且有字面量 `area` 时取 `area`）。只认字面量四元组，表达式 / 变量标 `unknown` 不猜。`RuleSwipe` / `RuleList` 不计入。附一个按符号名的全仓 consumer 粗扫（`appear_then_click` / `ui_click*` / `.click(SYM)` vs `appear(SYM)`），方向偏保守（宁可多算「可能被点」）。输出 `log/click_roi_analysis/click_roi_inventory.json` + `click_roi_summary.md`。
- **规模**：unique 可点击 ROI 定义 **2678**（RuleImage 2074 / RuleClick 297 / RuleOcr 297 / RuleLongClick 10 / RuleGif 0）。非字面量 ROI 20；`C_*RANDOM*` 大安全区 25，单独分组。
- **主分布**（RuleClick + RuleImage + RuleLongClick，排除大安全区，n=2339）**short_side**：min 1、p05 21、p10 23、p25 32、median 46、p75 68、p90 100、p95 120、max 720。**area** median 3569、p75 8648、p90 14584。aspect_ratio：AR<1.5 占 1317、1.5~2 占 280、2~3 占 462、3~5 占 219、>5 占 61。
- **confirmed_clickable 子集**（RuleClick/LongClick + 有点击 consumer 的 RuleImage，n=763）**short_side**：min 12、p05 21、p25 40、median 55、p75 81、p90 110、p95 143、max 720。比主分布整体偏大——大量 tiny 值来自纯检测用 `I_*_CHECK` / `I_*_ON` / `I_*_LOCK`，不在点击链上。
- **按类型 short_side median**：RuleClick 67（p25 47 / p75 100）、RuleImage 44（p25 32 / p75 63）、RuleOcr 37（读取为主，另计）、RuleLongClick 63.5。
- **候选尺寸边界（数据推导，未采纳）**：以 confirmed_clickable 的 short_side 分位为界——Tiny `< 24`（≈p05，仅 11/763，且多为语义特殊的确认键 / 退出条）、Small `24–40`（p05~p25）、Normal `40–96`（p25~p90 主体）、Large `≥ 96`。与此前人为的 `24 / 48 / 96` 相比，**下沿 24 得到数据支持，中间分界更接近 40 而非 48**。几何尺寸 ≠ 语义类别：`C_QUIT_AREA`(30×14) / `C_ANSWER_ENSURE_*`(≈13×26) / `C_BUY_MORE`(174×17) 等窄条按钮需要按语义单独指定 profile，不能只按 short_side 归类。
- **连续 vs 离散**：数据未呈现明显多峰（single-mode 右偏），`size_factor = f(short_side)` 连续映射比四档硬分类更贴合；真正需要离散的是「语义 override 名单」（大安全区、窄条、登录固定点），不是尺寸本身。
- **异常项**：`O_STORE_SUSHI_PRICE` / `O_DOKAN_RIGHTPAD_BOUNTY` / `C_SELECT_CARD` 等静态 `(0,0,0,0)` 占位（运行时填）；`tasks/Chess/runtime/recognition.py` 内一处 `<inline>` `RuleImage` 1×1（degenerate）。均照实标 `degenerate`，不参与数值统计。
- 测试 `tests/test_click_roi_inventory.py`（29 用例）：见 §7。

### 4.27 大尺寸点击 ROI 人工审查目录 `dev_tools/large_click_roi_review.py`

2026-09-02。在 §4.26 普查之上，把「大尺寸、真实可能用于点击」的 ROI 整理成可按编号逐项人工确认的目录。**未改任何生产代码 / Asset / ClickSampler / ClickProfile；`short_side>=96` 只是本轮取样线，未写进任何生产分类逻辑。**

- **工具**：`dev_tools/large_click_roi_review.py`（只读）。复用 `click_roi_inventory.scan_repo`，另建一套 **AST 消费者索引**（比 inventory 的正则粗扫准：能跨行、能记录所在函数、能区分 kind）。verb 分类：`click`（`click`/`appear_then_click`/`ui_click*`/`list_appear_click`/`ocr_appear_click` 等）、`coord`（`SYM.coord()`）、`indirect_click`（`random.choice([C_A, C_B, ...])` 再 click——`GameUi/default_pages.py` 与 `MartialArts/page.py` 的真实形状）、`detect`（`appear`/`wait_until_*`/`ocr` 等）。
- **同名符号消歧**：`C_RANDOM_LEFT` 在 `Component`/`GameUi`/`MartialArts` 各有一份。`build_assets_class_map()` 建「Assets 类名 → assets.py 路径」映射，消费者写 `GeneralBattleAssets.C_RANDOM_LEFT` 时可**精确归属**（`consumer_attribution=exact_by_qualifier`）；写 `self.C_X`（mixin 继承）无法区分，标 `ambiguous` 提醒人工核对。
- **筛选**：`RuleOcr` 一律不进主清单；`RuleImage` 必须**确认有点击消费者**才进（纯检测 `I_*_CHECK` 类进「排除项」）；`RuleClick`/`RuleLongClick` 天生是点击用，即使零消费者也进清单并标 `UNUSED / NO PRODUCTION CONSUMER`。
- **标注**：语义初判 A~I（`large_button` / `wide_card` / `large_safe_region` / `settlement_region` / `random_region` / `fullscreen_dismiss` / `fixed_business_area` / `dynamic_template` / `unknown`）、Point vs Region 目标类型、P0/P1/P2、每条的「人工检查重点」清单、`RuleImage` 的模板 PNG 路径（+ 是否存在）。**全部 `review_status = pending`**，不替用户做视觉判断。
- **本轮快照结果**：`short_side>=96` 的 ROI 定义 400 → 主审查清单 **198**（RuleClick 117 / 有点击消费者的 RuleImage 77 / RuleLongClick 4），排除 202（纯检测 + RuleOcr）。P0 35 / P1 109 / P2 54；settlement·reward·random 组 27；`C_*RANDOM*` 全量 27（不限尺寸）；超大区域表 36；**零消费者 40**（含 `C_GREEN_MARK_AREA` 1280×720、`C_RANDOM_ALL` 1207×543、`C_FG_RANDOM_*` 全套）。Region target 46 / Point target 152。
- **输出**：`log/click_roi_analysis/large_click_roi_review.md`（按编号 001~198 + 前 20 优先顺序）+ `.json`（含 `suggested_first_20` / `all_random` / `very_large` / `excluded`，供后续自动更新审查状态）。
- 测试 `tests/test_large_click_roi_review.py`（50 用例）：见 §7。

### 4.28 T7-1 Phase A —— GeneralBattle 通用结算迁到 C_RANDOM_RD（GENERALBATTLE SETTLEMENT CONTRACT V2）

> **已被 SETTLEMENT CONTRACT V3（§4.3.1 / §4.39，2026-09-03）取代**：`C_RANDOM_RD` /
> `C_RANDOM_RD2` 区域与 `_SETTLEMENT_PRIMARY_PROFILE` / `_SETTLEMENT_FALLBACK_PROFILE`
> 已从生产代码移除。下文只保留 V2 历史。

2026-09-02。`GeneralBattle` 的普通 result / reward 推进**从 `random_click()`（LEFT/RIGHT 随机）换成 `C_RANDOM_RD`（HABIT + 结算 profile）**，是 `LEGACY_UNIFORM` 之外第一个真进生产链的 ClickSampler 策略。**仍需 Level C MuMu 真机验收**。

> **历史**：Contract v1（RD 只点一次 + 2 秒观察窗口 + same-page 超时 = 推进失败 + sticky RD2 + Reward marker 决定点击区域）在结合真实结算 UI 后被推翻——一次完整结算通常本来就需要多次点击推进（点掉胜利层 → 推进御魂/奖励 → 关闭奖励展示），同一语义 Page 连续多帧是**正常内部推进**，不是「点击失败」。Contract v1 的 one-primary / 2s observe / sticky RD2 全部 Superseded（见 `docs/DECISIONS.md` D014）。

- **改动文件**：`tasks/Component/GeneralBattle/general_battle.py`（唯一生产文件）、`tests/test_general_battle_timing.py`（改）、`tests/test_general_battle_settlement.py`（重写）、`dev_tools/settlement_trace_check.py`（简化）、`tests/test_settlement_trace_check.py`（重写）。**未改** `random_click()` / `module/click_sampler.py` / `module/click_profile.py` / `module/atom/*` / Control / 后端 / 任何 Asset / 任何其它 task。`C_RANDOM_RD` `(699,397,574,314)` / `C_RANDOM_RD2` `(1056,237,198,425)` 是用户 WIP 已框好的资产。
- **Contract v2 行为**（`_handle_result` / `_handle_reward` → `_settlement_click(context)`）：
  - `page_battle_result` 与 `page_reward` **同一条路径**：`settlement_click_timer` 到点 → 点一次 `C_RANDOM_RD`（HABIT + `_SETTLEMENT_PRIMARY_PROFILE`）→ 重采下一次 `0.7~1.0s` 随机间隔 → `timer.reset()` → `return CONTINUE`。页面是否推进由外层 FSM 下一帧 `detect_page_in` 判断。
  - 仍是同一个 Page → 下一次 timer 到点后**继续点 RD**（每个 timer 周期都可以，不判失败）。合法序列 `reward → RD → reward → RD → reward → RD → exit`。
  - Page 变化 → 立即由新 Page handler 接管（`result → reward` 下一轮直接进 `_handle_reward`，不等 result 的 timer）。
  - `page_reward` 里 `appear_then_click(I_OVER_GHOST, interval=0.8)` / `appear_then_click(I_GB_SKIN_CONFIRM, interval=0.8)` **保持 Phase A 前调用时序：无条件尝试，点中也不早退**，然后照常 `_settlement_click`。
  - **不再有** `_reward_marker_present` / `REWARD_MARKERS` / `_advance_settlement` / `_reset_settlement_stage` / `_sync_settlement_stage` / `settlement_stage` / `settlement_primary_ts` / `settlement_fallback` / `_SETTLEMENT_PRIMARY_OBSERVE_SECONDS`——全部删除。`BattleContext` 只保留 `settlement_click_timer`（`_build_context` `Timer(0)` / `_reset_round_context` 重建）。`result → reward → exit` 由 `context.last_page` + 外层 `detect_page_in` 自然处理。
- **点击间隔**：`SETTLEMENT_CLICK_INTERVAL_RANGE` 从固定 `(0.8, 0.8)` 改为 `(0.7, 1.0)`。`_next_settlement_click_interval()` → `_sample_interval` → `random_delay(0.7, 1.0)`（项目统一随机源），**每次成功点击后独立重采**，不是任务开始时随机一次后复用。子类 override：只有 `RealmRaid` 有意覆写 `(0.65, 0.95)`（`PREPARE_CLICK_DELAY_RANGE (2.5, 3.5)`），本轮不动；其它 subclass 无 override。
- **每次点击重新采样坐标**：`_settlement_click` 每次到点都重新 `ClickSampler.sample(C_RANDOM_RD.roi_front, strategy=HABIT, profile=_SETTLEMENT_PRIMARY_PROFILE)`（2000 次实测 distinct 1926/2000，全在 Safe ROI 内，均值 ≈ `(1007, 565)`），不复用上一次 x/y。
- **结算 profile**（`general_battle.py` 模块常量，**不进 `DEFAULT_PROFILES`**，`provisional=True`，本轮参数**完全未改**）：
  - `_SETTLEMENT_PRIMARY_PROFILE`（RD）：`preferred_uv=(0.54, 0.53)` → 屏幕热点 ≈ `(1009, 563)`；`core σ=(0.10, 0.10)`、`medium σ=(0.16, 0.16)`、权重 `0.80 / 0.17 / 0.03`、`safe_margin=(0.06, 0.06)`、`max_attempts=12`。
  - `_SETTLEMENT_FALLBACK_PROFILE`（RD2）：`preferred_uv=(0.56, 0.58)` → 屏幕热点 ≈ `(1167, 484)`；`core σ=(0.12, 0.09)`、`medium σ=(0.18, 0.15)`、权重 `0.86 / 0.14 / 0.0`（tail=0）、`safe_margin=(0.10, 0.06)`。**Contract v2 下当前无生产消费者**——`C_RANDOM_RD2` Asset 与 profile 都保留，等 Level C / FrameChanged 提供「点击后页面确实没推进」的证据后再定义触发条件（不再以「同一语义 Page 持续 2 秒」为自动触发）。**本轮不接 FrameState/FrameWait 进 GeneralBattle**——只保留 semantic page polling，FrameChanged 是后续候选。
- **点击执行 `_sample_settlement_click(rule, profile)`**：`ClickSampler.sample(...)` → `self.device.click(x, y, control_name=rule.name)`。**保留 rule 身份**——BehaviorTrace 的 `target` 是 `random_rd`。采样抛 `ValueError`/`TypeError` → `logger.error` 后退回整 ROI 均匀一次（不静默、不卡死主循环）。
- **总边界**：RD 重复点击受 `settlement_click_timer` + 战斗硬 `battle_timer` / `_tick_timeout` / `QUICK_EXIT` 约束，**无独立 `while True`**、handler 内**无 `sleep`**。
- **Phase A 自动覆盖的 subclass**（最终 `super()` 到基类）：`RealmRaid`（非 quick_exit 分支）/ `HeroTest` / `Orochi` / `EvoZone` / `EternitySea` / `ActivityShikigami.base_act` / `BondlingFairyland._handle_reward`；各自 special 分支仍最先执行。**未迁**（Phase B）：`BondlingFairyland._handle_result`、`SixRealms/{moon_sea,peacock_kingdom}._handle_reward`（自带 `random_click()`）。**完全未动**：Duel ×4（`ltrb` 排除 RIGHT）、Dokan / fake_god / normal（仅 RIGHT）、moon_sea / peacock 退出页（仅 LEFT）、Exploration / MetaDemon task-private、`default_pages` 两个 page hook、SixRealms `page.py` 的 import-time `connect`、其它 NOT_SETTLEMENT `random_click`。
- 测试 `tests/test_general_battle_settlement.py`（37 用例，重写为 Contract v2）+ `tests/test_general_battle_timing.py`（17 用例）+ `tests/test_settlement_trace_check.py`（16 用例，简化）：见 §7。回归 504→537（Phase A 落地）→ 560（Contract v1 修正）→ **559**（Contract v2）。
- **Level C 真机验收：待用户手动跑一次**（本条更新时尚未执行）。分析器 `dev_tools/settlement_trace_check.py`（只读，不接设备）读 `log/behavior/<config>_<date>.jsonl`：RD/RD2 count / target / x·y / ROI-relative `(u,v)` / Safe ROI 内外 / `distinct_xy`；连续结算点击间隔分布（默认 `0.7~1.0s`，因 polling/调度/截图 实际略大于配置值——只标明显 `< 0.35s` 的高速重复，不检查上限）。**不再检查** RD-only-once / 2 秒观察 / same-page 超时 / sticky。前置：用户把待跑 config 的 `script.optimization.behavior_trace_enable` 改成 `true`（`config/*.json` 里默认 `false`，进程启动时读一次）。核心验收：result→RD、reward→RD、same-page 连续 RD、page change 立即换 handler、间隔在合理范围、坐标每次重采；`I_OVER_GHOST` / `I_GB_SKIN_CONFIRM` 用户当前无法稳定复现，未自然出现则标 PASS_WITH_PENDING，不为此改特殊逻辑。
- ~~**Settlement 问题当前冻结**（2026-09-02，用户决定）~~ → **已解冻并落地为 SETTLEMENT CONTRACT V3**（2026-09-03，§4.3.1 / §4.39）：用户给出「结果页必须两次推进点击」的真实业务事实 + 三个新安全区 + 两个奖励布局判别标志，据此正式迁移。`C_RANDOM_RD2` 的「同 page + frame 未变 → fallback」思路被「奖励宝袋 marker 命中与否决定 DEFAULT / RIGHT·BOTTOM」取代，不再需要 FrameChanged。

### 4.29 T7-2 —— Point Target 连续尺寸适配（`adapt_point_profile`）

2026-09-02。`module/click_profile.py` 新增「语义基础 Profile + 当前运行时 ROI → EffectiveProfile」的**纯计算**能力，解决「小图标趋近中心、大按钮逐渐释放个人热点」，取代 `if tiny / elif small / elif normal / elif large` 离散尺寸分类。T7-2 落地时**零生产消费者**；**T7-3.2（§4.31）起唯一消费者是 `RyouToppa.C_AREA_1`**（经 `ClickSampler.sample_point`，不经 `Rule*.coord()`）。

- **改动文件**：`module/click_profile.py`（唯一生产文件）、`tests/test_click_profile.py`（+21 用例）。**未改** `module/click_sampler.py` / `module/atom/*` / `RuleClick.coord` / Control / 后端 / `DEFAULT_PROFILES` 内容 / `resolve_profile` / strategy API / **任何 GeneralBattle / Settlement 代码**。
- **为什么在 ClickProfile 层而非 ClickSampler**：`ClickProfile` = 「参数是什么」，`ClickSampler` = 「怎么采样」。`adapt_point_profile(base, roi) -> ClickProfile` 是纯参数变换（base profile + ROI 几何 → 新 profile），不产生坐标、不调 RNG / 设备 / screenshot。放 `click_profile.py`；`click_sampler` 已 `import` 自 `click_profile`，反向 import 会成环，所以 `_roi_short_side` 在 `click_profile.py` 里独立实现（错误处理沿用 `ClickSampler._as_int_roi` 风格：非四元组 / 非数值 → `ValueError`/`TypeError`，`w<=0 或 h<=0` → `ValueError`）。
- **尺寸锚点**（provisional architecture constant，**不是用户配置**）：`POINT_SIZE_MIN_PX = 24`、`POINT_SIZE_FULL_PX = 96`。来自全仓 ROI 尺寸普查（§4.26）的描述性统计。
- **`point_size_factor(short_side)`**：`t = clamp((short_side - 24) / (96 - 24), 0, 1)`；`factor = 3·t² - 2·t³`（smoothstep）。`short_side <= 24` → `0`；`>= 96` → `1`；`60` → `0.5`。单调不减、两端一阶导为 0（无线性折点）。
- **`adapt_point_profile(profile, roi)`**（T7-2 第一步只调 `preferred`；**T7-4（§4.32）起同一个 `f` 也调 `core/medium sigma` 与 `tail`**）：`f = point_size_factor(min(w, h))`；`effective_u = 0.5 + (base.preferred_u - 0.5) * f`；`effective_v = 0.5 + (base.preferred_v - 0.5) * f`。返回新 frozen `ClickProfile`（`dataclasses.replace`），`profile` 不被修改。公式对称——`base_u < 0.5` 时同样向左平滑释放，不假设个人热点只能右偏。
- **T7-2 阶段：`core_sigma` / `medium_sigma` / `weights` / `safe_margin` / `max_attempts` / `provisional` / `name` 全部原样保留**（spread 与 preferred 当时按两个独立维度处理）。**T7-4（§4.32）改为 spread 也随 `f` 收敛**（`sigma` 向保守小目标锚点插值、`tail` 向 0 收），只有 `safe_margin` / `max_attempts` / `provisional` / `name` 仍原样透传。AR（宽高比）不进算法——`short_side = min(w, h)` 直接代表点击容错最窄方向（`320×60` 长条不能按大面积释放），AR 只作未来候选。
- **代表尺寸实测**（`normal_button` base `(0.62, 0.70)` / `wide_card` base `(0.58, 0.59)`——`wide_card` base 值 T7-3.1 修正，见 §4.30）：

  | short_side | factor | normal_button `(u,v)` | wide_card `(u,v)` |
  |---|---|---|---|
  | ≤24 | 0.0000 | `(0.5000, 0.5000)` | `(0.5000, 0.5000)` |
  | 40 | 0.1262 | `(0.5151, 0.5252)` | `(0.5101, 0.5114)` |
  | 48 | 0.2593 | `(0.5311, 0.5519)` | `(0.5207, 0.5233)` |
  | 60 | 0.5000 | `(0.5600, 0.6000)` | `(0.5400, 0.5450)` |
  | 72 | 0.7407 | `(0.5889, 0.6481)` | `(0.5593, 0.5667)` |
  | 80 | 0.8738 | `(0.6049, 0.6748)` | `(0.5699, 0.5786)` |
  | ≥96 | 1.0000 | `(0.6200, 0.7000)` | `(0.5800, 0.5900)` |

- **`tiny` / `small` profile 仍在 `DEFAULT_PROFILES`**（本轮不删，仍用于测试 / 历史兼容 / 显式 profile），但**新的 Point Target 动态算法不再用它们**——`adapt_point_profile` 源码里无 `tiny` / `small` / `DEFAULT_PROFILES` / `if short` / `elif` 字样（测试锁）。
- 测试 `tests/test_click_profile.py`（44→65，+21）：见 §7。回归 559→581。

### 4.30 T7-3.1 —— Point Semantic Profile 数据基线收口

2026-09-02。T7-3 只读审计发现 `wide_card (0.68,0.53)` / `normal_button (0.62,0.70)` 无法对真实 ROI-relative 数据复现。本轮**只改 profile 数值 / 元数据 + 对应测试**，**不改任何采样 / 适配算法、不接生产消费者、不碰 GeneralBattle Settlement（已冻结）**。

- **改动文件**：`module/click_profile.py`（`wide_card` preferred + 3 个 profile 的 `provisional` + 模块 docstring）、`tests/test_click_profile.py`（+3 用例、改 2 处断言）、`tests/test_general_battle_settlement.py`（1 个护栏测试改名 + 断言跟随工作树，见 §7）。**未改** `adapt_point_profile` / `point_size_factor` / `ClickSampler` / `resolve_profile` / sigma·weights·margin / `module/atom/*` / Control / 后端 / 任何 `Rule*.coord()` / GeneralBattle。
- **`wide_card` preferred `(0.68,0.53)` → `(0.58,0.59)`**：用现有 manual click 原始数据 `log/manual_click/yys1_2026-09-01.jsonl` 的 cluster_A（寮突破目标卡片，burst-collapse 后 **107** 个独立落点，剔除开头 6 条窗口校准点击）对**当前 `RyouToppa.C_AREA_1` WIP RuleClick ROI** `(514,141,223,116)` 重算 inside-only ROI-relative：inside **105 / 107**（outside 2 = 屏幕左上角残留点），`mean_uv=(0.582,0.586)`、`median_uv=(0.579,0.586)`、`std_uv=(0.128,0.140)`。取 `mean≈median` → `(0.58,0.59)`。旧值 `(0.68,0.53)` 已查明 = cluster_A 屏幕热点 `(641,205)` 对**手工估的更大「完整可点卡片区」`(423,142,319,118)`** 归一化（`u=(641-423)/319=0.683`、`v=(205-142)/118=0.536`），坐标基准与真实消费的 `C_AREA_1` RuleClick ROI 不一致，不能直接喂 `adapt_point_profile(base, C_AREA_1.roi_front)`。对照：同一批点对 **HEAD 版 `C_AREA_1` `(533,162,177,74)`** 算是 inside 101/107、`mean_uv=(0.627,0.622)`、`std_uv=(0.155,0.207)`（ROI 更小 → 相对散布更大、更多点被判 outside）——所以「preferred 数值依赖具体 ROI 定义版本」，必须记录坐标基准。
- **`normal_button (0.62,0.70)` 不重估**：cluster_B（真进攻按钮）只有屏幕归一化 `mean (0.527,0.545)`，`I_FIRE` 是 `RuleImage`（`match()` 后 `roi_front` 是模板尺寸框），**没有可靠 runtime ROI-relative 数据**。禁止拿 screen-space / static ROI 猜 runtime relative——保留旧值、标 `provisional`，等 Level C `runtime_roi_probe --target I_FIRE` + manual click 一起标定。
- **`large_area (0.74,0.67)` 不作 Point profile**：cluster_C 是多个战后页面混合的**屏幕空间**连点中心，无单一 ROI 基准，属 Region 语义。标 `provisional`，注释写明**禁止**用于 `adapt_point_profile` 的 Point Target opt-in；与 GeneralBattle `_SETTLEMENT_PRIMARY_PROFILE` 是不同东西，不合并。
- **`provisional` 补齐**：`DEFAULT_PROFILES` 8 个条目现**全部** `provisional=True`（`wide_card` / `normal_button` / `large_area` 补上，之前漏标）。`provisional` 是**纯文档标记**——`__post_init__` 不校验它、`ClickSampler` 各策略不读它、`adapt_point_profile` 用 `dataclasses.replace` 原样透传，**设置它不改变任何采样行为**（测试 `test_spread_and_metadata_unchanged` 锁）。
- **回归 581→584**（`tests/test_click_profile.py` 65→68：`wide_card` 代表尺寸新基线 `(0.58,0.59)` + `C_AREA_1` WIP ROI short_side 116→factor 1→effective==base 回归锁、3 类 `provisional=True` 断言、`DEFAULT_PROFILES` 全 `provisional` 断言）。
- **T7-4（spread / sigma 尺寸适配）**：T7-3 审计确认「小 ROI 只把 `preferred` 拉回中心、`sigma` 不变」在生产 opt-in 前需要解决。**2026-09-02 已实现，见 §4.32**（复用同一个 `size_factor`，`sigma` 向保守锚点插值、`tail` 向 0 收，未新增第二条尺寸曲线）。

### 4.31 T7-3.2 —— 首个普通 Point Target 生产 opt-in（`RyouToppa.C_AREA_1`）

2026-09-02。`RyouToppa` 的目标区域 1（`C_AREA_1`）从 `LEGACY_UNIFORM` 显式改为
`wide_card` → `adapt_point_profile` → `ClickSampler` HABIT。这是 `LEGACY_UNIFORM` /
GeneralBattle Settlement RD 之外**第一个普通 Point Target 的真实生产 opt-in**。
**Point Target 生产消费者：0 → 1。仍需 Level C MuMu 真机验收。**

- **改动文件**：`module/click_sampler.py`（加薄组合入口 `ClickSampler.sample_point`）、`tasks/RyouToppa/script_task.py`（加私有 `_click_toppa_area(index)` + 两处调用点改走它）、`tests/test_ryoutoppa_c_area_1_point_opt_in.py`（新增 25 用例）、`tests/test_general_battle_settlement.py`（`random_click` 护栏测试改名，见 §7）。**未改** `RuleClick/RuleImage/RuleOcr/RuleGif.coord` / `ClickSampler` 默认策略 / `adapt_point_profile` / `DEFAULT_PROFILES` 内容 / `BaseTask.click` / Control / 后端 / `normal_button` / `I_FIRE` / **任何 GeneralBattle Settlement 代码**。
- **新调用链**：`attack_area` / `_reopen_area_after_fire_disappear` → `_click_toppa_area(index)` → `if area_map[index]['rule_click'] is self.C_AREA_1`：`ClickSampler.sample_point(C_AREA_1.roi_front, DEFAULT_PROFILES['wide_card'])` → `adapt_point_profile`（按当前 `roi_front` 尺寸）→ `ClickSampler.sample(roi, strategy=HABIT, profile=effective)` → `self.device.click(x, y, control_name=rule.name)`。`else` 分支（`C_AREA_2..8`）走原 `self.click(rule)` = `RuleClick.coord()` = `LEGACY_UNIFORM`，**逐调用点身份守卫**，不按 ROI 尺寸批量迁移。
- **`ClickSampler.sample_point(roi, base_profile=None)`**：3 行薄组合——`adapt_point_profile(resolve_profile(base_profile), roi)` 再 `ClickSampler.sample(roi, strategy=HABIT, profile=effective)`。放 `ClickSampler`（「坐标如何产生」的统一入口），**不塞进 `BaseTask`**（god class 长期约束，见 `docs/DECISIONS.md` D014）。`Rule*.coord()` 默认路径不经过它。
- **`C_AREA_1` 尺寸适配当前不收缩**：`roi_front=(514,141,223,116)` → `short_side = min(223,116) = 116 ≥ POINT_SIZE_FULL_PX(96)` → `size_factor = 1.0` → effective `preferred == wide_card` base `(0.58,0.59)`（不向中心 `(0.5,0.5)` 收缩）。接了 `adapt_point_profile` 但当前区域够大、这是预期行为；将来 ROI 变小才会收缩。
- **spread 不变**：effective profile 的 `core_sigma (0.16,0.16)` / `medium_sigma (0.26,0.24)` / `weights (0.75/0.20/0.05)` / `safe_margin (0.05,0.05)` / `max_attempts 12` / `provisional` / `name` 全部 == base。本轮不做 T7-4。实测 `C_AREA_1` ROI + `wide_card` 下 20000 次采样 fallback 命中 **0 次**（rejection 不是问题），mean ≈ 屏幕 `(640,208)` ≈ 热点 `(643,209)`，Safe ROI `(525,147,201,104)`，每次点击重新采样（distinct ≈ 3973/5000）。
- **BehaviorTrace 身份不被污染**：`control_name` 仍是 `rule.name`（`"area_1"`），`Control.click` 记录 `target="area_1"`——不是 `"wide_card"` / `"point_click"` / `"habit"`。坐标产生方式变了、点击发送方式（`self.device.click`）没变。
- **回归 584→609**（`tests/test_ryoutoppa_c_area_1_point_opt_in.py` +25：调用链 / 尺寸适配 factor=1 / effective==base / spread 不变 / `sample_point` 喂 HABIT + effective profile / `C_AREA_2` 仍 `self.click`+LEGACY / `C_AREA_2..8` 不走 Point 路径 / 全仓 `.sample_point(` 只在 `RyouToppa/script_task.py` 出现 1 次 / `RuleClick.coord` 未改 / `ClickSampler` 默认仍 LEGACY / `normal_button` 生产零消费者且 `provisional` / `I_FIRE` 未接 / Settlement Contract v2 常量完好）。
- **回滚点**：删 `_click_toppa_area`、两处调用点还原成 `self.click(area_map[index].get('rule_click'))` / `self.click(rcl)`、删 `ClickSampler.sample_point` 即可完全恢复到 T7-3.1 状态（`sample_point` 无其它消费者）。
- **Level C 真机验收**：`C_AREA_1` 点击后开 `behavior_trace_enable=true` 跑 `RyouToppa`，看 `log/behavior/*.jsonl` 里 `target="area_1"` 的落点分布是否集中在 ROI 相对 `(0.58,0.59)` 附近、全在 Safe ROI 内、每次不同；对照 `C_AREA_2..8`（`target="area_2".."area_8"`）应仍是全 ROI 均匀。

### 4.32 T7-4 —— Point Target spread 连续尺寸适配

2026-09-02。`adapt_point_profile` 从「只调 `preferred`」扩展为「用**同一个** `size_factor` 同时调 `preferred` + `core/medium sigma` + `tail`」。**纯 `ClickProfile` 数学**：不新增生产消费者、不改 `C_AREA_1` 调用链、不改 `sample_point` API、不改任何 `Rule*.coord()` / GeneralBattle Settlement。

- **改动文件**：`module/click_profile.py`（`adapt_point_profile` 扩展 + 新常量 `POINT_MIN_*_SIGMA_*` + `_lerp` + 模块 docstring）、`tests/test_click_profile.py`（`AdaptPointProfileTest` 拆 1 个旧断言为 2 个 + 新增 `PointSpreadAnchorTest` 2 + `PointSpreadAdaptationTest` 16）、`tests/test_ryoutoppa_c_area_1_point_opt_in.py`（1 个断言收紧成「逐字段等于 base」+ docstring）。**未改** `point_size_factor` / `POINT_SIZE_MIN_PX` / `POINT_SIZE_FULL_PX` / `preferred` 公式 / `ClickSampler` / `sample_point` / strategy API / `DEFAULT_PROFILES` 数值 / `tasks/RyouToppa/script_task.py` / GeneralBattle。
- **不新增第二条尺寸曲线**：继续只有一个 `f = point_size_factor(min(w, h))`，没有 `spread_size_factor` / `tail_size_factor` / `sigma_size_factor`。
- **spread 锚点（`f=0` 时的最保守小目标分布宽度）= `tiny` profile 的 σ**：审计现成保守 profile（`default` coreσ 0.10 / `small` 0.09-0.08 / `tiny` 0.06 / `strict` 0.05）后取 `tiny`——它是 `DEFAULT_PROFILES` 里语义正好对应「Point Target 最小尺寸」的一档，`core σ 0.06` 保守但不退化（不趋近 0，最终安全仍靠 Safe ROI），本身已 `tail=0`。`strict` 更窄但语义绑定 STRICT 策略，不选。落成模块常量 `POINT_MIN_CORE_SIGMA_U/V = 0.06`、`POINT_MIN_MEDIUM_SIGMA_U/V = 0.10`，`test_point_min_spread_anchor_matches_tiny_profile` 锁「常量 == `tiny` 的 σ」。
- **sigma 公式**：`effective_sigma = anchor * (1 - f) + base_sigma * f`（`_lerp`，端点精确写法——`f=0`→恰好 anchor，`f=1`→恰好 base）。对 `core_sigma_u/v` 与 `medium_sigma_u/v` 各自独立插值。
- **tail 公式**：`effective_tail_weight = base.tail_weight * f`（`f=0`→`0.0`、`f=1`→`base.tail_weight`，都精确）。被削掉的 `base.tail_weight * (1 - f)` **整体回补到 `core_weight`**（`core += base.tail_weight * (1 - f)`）；`medium_weight` 不动。三成分之和恒等于 base 之和（base 都是 1.0），不新增第四个成分，无负数。
- **`safe_margin_u/v` 本轮不变**：Safe ROI 是 `ClickSampler` 的硬安全边界（职责与分布形状独立），不随尺寸缩放。`max_attempts` / `provisional` / `name` 也原样透传。
- **`f=1` 逐字段恢复 base**：`short_side >= 96` 时 EffectiveProfile 的**每个字段都逐字等于 base**（仅对象 identity 是新实例）。`f=0` 时 `preferred=(0.5,0.5)`、`sigma`=锚点、`tail=0`。中间 smoothstep 连续、单调、无 24→25 / 40→41 折点。
- **代表尺寸实测**（`_lerp`/公式脚本算，非估计）：

  `normal_button`（base coreσ 0.13 / medσ 0.22 / w 0.78·0.18·0.04）：

  | ss | factor | preferred | coreσ | medσ | (core_w, med_w, tail_w) |
  |---|---|---|---|---|---|
  | ≤24 | 0.0000 | (0.5000, 0.5000) | 0.0600 | 0.1000 | (0.8200, 0.1800, 0.0000) |
  | 40 | 0.1262 | (0.5151, 0.5252) | 0.0688 | 0.1151 | (0.8150, 0.1800, 0.0050) |
  | 48 | 0.2593 | (0.5311, 0.5519) | 0.0781 | 0.1311 | (0.8096, 0.1800, 0.0104) |
  | 60 | 0.5000 | (0.5600, 0.6000) | 0.0950 | 0.1600 | (0.8000, 0.1800, 0.0200) |
  | 72 | 0.7407 | (0.5889, 0.6481) | 0.1119 | 0.1889 | (0.7904, 0.1800, 0.0296) |
  | 80 | 0.8738 | (0.6049, 0.6748) | 0.1212 | 0.2049 | (0.7850, 0.1800, 0.0350) |
  | ≥96 | 1.0000 | (0.6200, 0.7000) | 0.1300 | 0.2200 | (0.7800, 0.1800, 0.0400) |

  `wide_card`（base coreσ 0.16 / medσ (0.26,0.24) / w 0.75·0.20·0.05）`f≥1` → 逐字段 base；`f=0` → preferred (0.5,0.5)、coreσ 0.06、medσ 0.10、tail 0、core_w 0.80。`ss=60`（f=0.5）：preferred (0.54,0.545)、coreσ 0.11、medσ (0.18,0.17)、tail 0.025。

- **极小按钮示例**（40×30，`short_side=30`，如 `C_DOKAN_REFRESH` 形状，**不接生产**，仅数学示例）：以 `normal_button` 为 base，`f≈0.0197` → `core_sigma_u ≈ 0.0614`（**≈ base 0.13 的 47%，收窄约 53%**）、`tail ≈ 0.0008`（≈0）、`preferred ≈ (0.502, 0.504)`（贴近中心）。
- **`RyouToppa.C_AREA_1` 生产行为不变（核心护栏）**：`roi_front (514,141,223,116)` → `short_side 116 ≥ 96` → `size_factor` 恰为 `1.0` → EffectiveProfile 逐字段等于 `wide_card` base（`preferred (0.58,0.59)` / coreσ (0.16,0.16) / medσ (0.26,0.24) / w (0.75,0.20,0.05) / margin (0.05,0.05) / `max_attempts 12` / `provisional` / `name`）。T7-4 前后 `C_AREA_1` 落点分布完全一致。
- **回归 609→628**（`tests/test_click_profile.py` 68→87；`tests/test_ryoutoppa_c_area_1_point_opt_in.py` 25 用例不变，1 个断言收紧）。生产点击分布：`C_AREA_1` 零变化（factor=1），其余 Point Target 仍零生产消费者。

### 4.33 Kekkai 状态机静态收口（`KekkaiActivation` / `KekkaiUtilize`，characterization）

2026-09-02。回到 OAS 状态驱动主线，对 `KekkaiActivation` + `KekkaiUtilize` 做迁移前静态收口——**只读审查 + 建模 + characterization，未改任何 Kekkai 生产行为**（本轮生产 diff = 0）。等价于 §4.19 为 `list_find` 做过的事，对应 ROADMAP T4-4（`harvest_card` 状态化）/ T5-1（`swipe_adb` trace）/ T5-2 后半 的迁移前准备。完整状态图 / State Matrix / 缺口清单 / Issue Register / 迁移候选见 `docs/Kekkai状态机静态收口.md`。

- **改动**：新增 `tests/test_kekkai_activation_state.py`（18 用例）+ `tests/test_kekkai_utilize_state.py`（23 用例）+ `docs/Kekkai状态机静态收口.md`。**未改** `tasks/KekkaiActivation/*`（本轮零改动）/ `tasks/KekkaiUtilize/*`（`M` 是更早轮次阈值 WIP，未触碰）/ `base_task.py` / 任何生产代码。
- **整体运行模型**：两个任务都是「截图 → `appear`/OCR 判局面 → `click`/`swipe_adb` → 多数步骤靠固定 `sleep` 或『下一轮 `while` 重判』推进」的黑盒轮询，无显式 State/Action/ExpectedState 结构，「验证」大多是隐式的（下一轮识别不到期望局面就继续点 / 继续滑）。
- **`harvest_card`**（`KekkaiActivation`）：线性 8 次无参 `appear_then_click(I_A_HARVEST_*)`，**8 步之间无 `screenshot` / `sleep` / 循环 / `if` / `return`**——`appear_then_click` 无 `interval` 时不截图，故 8 次全匹配同一帧（上一步 `goto_page` 留下的）。无验证、无 reward popup 闭环，返回 `None`。ROADMAP T4-4 pilot 的对象，落地需 Level C（点击后的「期望状态」是弹奖励 / 按钮消失 / 跳页 当前未知）。
- **列表 swipe（两处平行实现，均绕过 `list_find` 与 `Control.swipe`）**：`KekkaiActivation.check_card_num` 用 **stdlib `random.randint`** + `swipe_adb(duration=2)`，`p2 = (p1.x, p1.y-410)`，`while 1` + `ocr_count>3` **有界**，swipe 后 `sleep(1)`；`KekkaiUtilize.perform_swipe_action` 用公共 `random_int` + `swipe_adb(duration=2)`，`p2 = (p1.x, p1.y-SWIPE_DISTANCE=416)`，`swipe_adb → click_record_clear → sleep(2)`，调用方 `range(20|21)` + `Timer(120)` 双界。`KekkaiActivation` 仍全走 `swipe_adb`（不进 BehaviorTrace）。**KekkaiUtilize 2026-09-04 K1 起**：**标准 PASS 搜索**（`_run_search_pass`）的下划改走 `_perform_search_swipe` —— minitouch 配置 → `TouchSwipeModel` + `Control.swipe_trajectory`（**进 BehaviorTrace** `ACTION`/`swipe`/`target=KEKKAI_UTILIZE_SWIPE`），非 minitouch 回退 `perform_swipe_action`；**怠惰模式**（`_select_lazy_resource_card`）仍走 `perform_swipe_action`（`swipe_adb` 直连、不进 BehaviorTrace）。
- **循环边界**：多数是 bounded（`goto_page` `Timer(30)`、`switch_friend_list` `Timer(20)`+raise、`_current_select_best`/`_select_lazy_*`/`_reselect_*` `range`+`Timer(120)`、`check_utilize_add` `count>=5`、`check_card_num`(KA) `ocr_count>3`）；`KekkaiActivation.run_activation` 与 `screening_card` 的 4 个 `while 1` 是 **potentially unbounded**（无迭代上限 / 总超时，仅靠上游 stuck 检测兜底）。
- **Issue Register**（本轮只记录、不修）：`check_card_num` 子类覆写改返回类型（`RuleClick` vs `(str,int)`，latent）；`harvest_card` 无验证闭环；`check_card_num`(KA) 随机源不统一（stdlib）；`swipe_adb` 直连无 trace；`run_activation`/`screening_card` `while 1` 无超时；`ocr_time` 失败 `None + datetime` 会崩；`check_utilize_add` 「5 轮」return `True` 与失败路径 return `False` 语义相反（§8 已记）；`last_best_index=99` 死属性；lazy_roll 把 `random_delay(0.0,1.0)` 当随机浮点用；`KekkaiActivation` 死 import `parse_rule`；`run_utilize` U3 `goto_page` 失败不 return。详见专题文档 §9。
- **FrameWait**：`wait_for_changed_and_stable` 在 Kekkai **仍 0 consumer**；本轮未写入任何 `changed_threshold` / `stable_threshold` / `stable_frames` / ROI / timeout 猜测值。
- **与 `list_find` 关系**：三处「swipe 后等列表停稳」（`list_find` 翻页 sleep、KA `check_card_num` sleep(1)、KU `perform_swipe_action` sleep(2)）都属 D013 的视觉结构等待，未来可共用同一个 `wait_for_changed_and_stable` primitive（前提：调用点自己在 swipe 前显式传 baseline 帧）；命中判定 / 到底部判定 / 选卡回选跨区 是 Kekkai 特有 business wrapper，不进公共层。
- 测试 `tests/test_kekkai_activation_state.py`（18）+ `tests/test_kekkai_utilize_state.py`（23）：见 §7。回归 628→669。

### 4.34 RealmRaid 状态机静态收口（characterization）

2026-09-02。状态驱动主线第三个静态收口对象（前两个：`list_find` §4.19、Kekkai §4.33）。**只读审查 + 建模 + characterization，未改任何 RealmRaid 生产行为**——`tasks/RealmRaid/` 对 HEAD **零 diff**。完整状态图 / State Matrix（S1~S15）/ 目标选择与进攻逐条回答 / Action→Verify Gap / Wait & Loop Inventory / Stale 分析 / Issue Register（13 条）/ 与 Kekkai 对比 见 `docs/RealmRaid状态机静态收口.md`。

- **改动**：新增 `tests/test_realm_raid_state.py`（41 用例）+ `docs/RealmRaid状态机静态收口.md`。**未改** `tasks/RealmRaid/*` / `GeneralBattle` / `base_task.py` / 任何生产代码。
- **运行模型**：`run()` 一个 `while 1` 主循环——「查票 → `find_one` 九宫格选目标 → `fire(index)` 点目标+点进攻 → `run_general_battle()` → 三胜奖励 / 刷新 / 失败分支 → 下一轮」，6 个 `break` 退出点，收尾 `goto_page(page_exploration)` + `set_next_run` + `raise TaskEnd`。战斗完全委托 `GeneralBattle` Page FSM。
- **最关键现状——「旧标识消失 = 已进入战斗」**：`fire()` 判定进入战斗的**唯一**依据是 `if not self.appear(self.I_RR_PERSON): return True`，**没有**任何战斗页正向标识（源码无 `page_battle` / `detect_page_in` / `I_EXIT` / `get_current_page`）、**没有** timeout、**没有** retry 上限。弹窗遮挡 / 切页动画中间帧 / `threshold=0.8` 附近匹配抖动都可能让单帧误判 → 在非战斗页调 `run_general_battle`（有 `_handle_missing_battle_page` + `_tick_timeout` 兜底，不会立即崩，但浪费一段 battle timeout）。`fire_again()` 同构（`I_FIRE_AGAIN` 消失即成功）。
- **`fire()` 恒返回 True**：`while True` 内无 `break`，尾部 `logger.info` + `return False` **不可达**（AST 测试锁定）→ `run()` 里两处 `if not self.fire(index): continue` 是**当前死分支**，「没成功进入战斗就重来」这条设计意图实际从未生效。
- **循环边界**：主循环 state-bounded；**6 处自有 `while` 全部 potentially unbounded**（`fire` / `fire_again` / `ensure_lock` / `check_refresh`×2 / `reward_detect_click` / 呱太弹窗），且 AST 确认 RealmRaid 全部 `wait_until_appear(X)` **都不传 `wait_time`** → `BaseTask` 内不建计时器。兜底只有上游 `stuck_record`。
- **等待特征与 Kekkai 相反**：活跃路径**没有任何固定 `sleep`**（唯一 `sleep(0.2)` 在死代码 `medal_fire` 里），节流全靠 `interval`；**没有滑动、没有「等画面停稳」的等待** → **FrameState 候选面很小**，`fire()` 的改造方向是 semantic（正向页面标识）而非 FrameState。
- **GeneralBattle 交接**：`run_general_battle(config)`（`exit_four` 路径 4×quick_exit + 4×`fire_again` + 第 5 次常规），返回 `bool` 接进 `last_battle`。RealmRaid 覆写 `_exit_matcher()→I_BACK_RED`、`_handle_result`（quick_exit 时按 `appear(I_FALSE)` 直接 EXIT_WIN/LOSE 且**不点结算**，否则 `super()`）、`PREPARE_CLICK_DELAY_RANGE=(2.5,3.5)`（基类 `(3.0,3.0)`）、`SETTLEMENT_CLICK_INTERVAL_RANGE=(0.65,0.95)`（基类 `(0.7,1.0)`）——即 **RealmRaid 非 quick_exit 分支间接消费通用结算 V3**（`_advance_generic_result` 的强制双击 + `C_RANDOM_DEFAULT`，用自己的 `(0.65,0.95)` 间隔），quick_exit 分支仍在 `super()` 前直接 EXIT 不点结算，本轮 RealmRaid 代码未动。
- **输入全走 `Control`**：RealmRaid 模块内无 `swipe_adb` / `click_adb` / `adb_shell` / `*_minitouch` / `device.swipe(` 直连（测试锁定）→ 所有点击**都进 BehaviorTrace**，与 Kekkai 的两处 `swipe_adb` 绕过形成对比。目标点击用静态 `C_PARTITION_1..9` 的 `RuleClick.coord()` = `LEGACY_UNIFORM`（未做 T7 Point opt-in）。
- **Issue Register**（本轮只记录、不修，13 条见专题文档 §14）：R-R1「消失=进战斗」无正向确认无超时；R-R2/R-R3/R-R6 三处尾部 `return False` 不可达（`fire` 恒 True 导致 run 死分支）；R-R4/R-R5 六处 `while` 与全部 `wait_until_appear` 无超时；R-R7 `medal_fire()` / `is_ticket()` **全仓零调用方**且 `medal_grid=None`（一旦调用即 `AttributeError`）、`medal_fire` 声明 `-> bool` 却无 `return`；R-R8 `AttackNumber` 死 import；R-R9 `find_one` 在 `device.image` 上**原地涂黑**失败格（共享帧副作用，当前恰好未被消费）；R-R10 `false_image` 复用 RyouToppa 的 `loser_sign_1.png`（跨任务资产耦合）；R-R12 点的是静态九宫格 ROI 而非识别到的勋章位置。
- **FrameWait**：RealmRaid production consumers = **0**；本轮未写入任何 threshold / ROI / timeout 猜测值。
- **是否抽公共 Retry / State 层：否**。RealmRaid 与 Kekkai 确实共有「点击→旧标识消失即成功」「`while`+`interval` 无超时反复点」两种模式，但超时值全是 Level C 未知；且 `list_find`/Kekkai 的公共点是**视觉结构等待**而 RealmRaid 根本没有这类等待——**三者的公共层不是同一个**，不能一次抽完。延续 D013 纪律，等真机数据后再评估。
- 测试 `tests/test_realm_raid_state.py`（41）：见 §7。回归 669→710。

### 4.35 三案例 Verify / Wait / Retry / Recovery 架构归纳（决策节点）

2026-09-02。基于三个已完成迁移前静态收口的真实案例（`list_find` §4.19、Kekkai §4.33、RealmRaid §4.34）横向归纳四类职责的边界与公共化程度。**纯设计归纳——不修改任何业务生产行为、不新增任何 Python 代码**。完整分析（三案例总矩阵 / 四类定义 / Semantic S1~S4 / Structural / Retry 全量表 / Timeout·Attempts / Recovery Boundary / Fresh Screenshot / Target Relocation / Result·Exception Contract / Pattern Catalog A~E / Owner Matrix / BehaviorTrace 事件优先级 / Level A Cleanup Queue / API proposal）见 `docs/状态验证与重试模式归纳.md`，长期契约落到 `docs/DECISIONS.md` D015。

- **改动**：新增 `docs/状态验证与重试模式归纳.md` + `docs/DECISIONS.md` D015。**无 Python 改动**。
- **核心结论——是否抽公共 Retry / Verify 层：PARTIAL，且不是现在。**
  - **structural wait**：`module/base/frame_wait.py::wait_for_changed_and_stable` 已就位、无缺口，缺的 100% 是 Level C 参数（ROI / 阈值 / `stable_frames` / timeout）+ 调用点 baseline 捕获。**不新增第二套 structural wait 抽象。**
  - **semantic verify**：`wait_until_appear` / `wait_until_disappear` / `appear` 组合已足够；`wait_until_disappear` 补 `wait_time` 是 1 行签名扩展（不是新类，改动本身 Level C）。**不需要 `Verifier` / `ActionVerifier` 类。**
  - **bounded retry**：三案例的 action-retry 循环（RealmRaid `fire`/`fire_again`/`ensure_lock`/`check_refresh`、Kekkai `screening_card`）有共同骨架，但 action 多 target 交替、**当前全部无 bound**（加 bound 就改时序 → 每个消费者接入都是 Level C）、recovery 差异极大。**唯一真正共同的内核只有「计 attempts + 独立 total timeout + 返回 frozen result」约 15 行**——值得未来抽，不值得现在在零消费者下抽（会变成又一个像 `frame_wait` 一样长期悬空、且无真实 adoption 校准形状的组件）。
  - **recovery**：`return False` / `refresh` / `switch group` / `set_next_run(+N min)` / 改 config / `raise TaskEnd` / `find_one` 涂黑——高度业务特化，**永远留在 Task**。
- **下一阶段唯一推荐：Option 2 —— 先做一轮纯 Level A correctness / dead-code cleanup**（§9 待办新增队列）。理由：项目优先级 `correctness > reliability > observability > abstraction`；§16 队列全部零真机、低风险、有 characterization 回归护栏；retry 内核等第一个真实 Level C 迁移时对着真实消费者抽更准。不选 Option 1（零 adoption 校准）/ Option 3（三案例形态已够）/ Option 4（还有一队 Level A 活）。
- **BehaviorTrace 下一步观测能力**：`RETRY` 事件（一次 bounded retry 循环结束记一条，带 attempts + outcome，天然含 timeout 信号），优先级高于 `VERIFY`（太吵、违背 D004 克制）/ `TIMEOUT`（是 RETRY 子集）；排在 retry 抽象之后，本轮不动 BehaviorTrace。
- **FrameWait**：三案例 production consumers 仍 = **0**；本轮未写入任何未标定参数。
- 无测试改动，完整回归维持 `710/710`（见 §7）。

### 4.36 Level A cleanup —— 第一批（只删可证明零引用的死代码）

2026-09-02。执行 §4.35 推荐的 Option 2 的**第一批**：只处理「可从源码证明所有生产路径输出完全相同」的 A 类项（dead import / 零引用 dead attr / 零调用 dead method）。B 类（会改变运行结果的 correctness 修复）本批**只在正确语义唯一时**处理——本批无一符合，全部 deferred；C 类（与 Level C 状态迁移耦合，如 RealmRaid `fire()` 的不可达 `return False` / 死分支）**只记录不改**。

- **FIXED（4 个 Cleanup Queue issue / 5 条子项 / 6 个具名删除 / 3 个生产文件，全部 behavior-neutral）**——口径：§16 的 4 行（R-R7 死方法簇、R-R8 死 import 簇、`parse_rule`、`last_best_index`）展开成下面 5 条子项：
  - `RealmRaid.ScriptTask.medal_fire()` / `is_ticket()` 删除——全仓（`tasks/` + `module/`）零调用方、无 super/subclass/getattr/字符串/scheduler 引用（已 grep 确认）；`medal_fire` 还依赖已被删的 `medal_grid = None`（一旦调用即 `AttributeError`）。真正生效的票数检查是 `check_ticket`、进攻是 `fire`，均保留。
  - `RealmRaid` `medal_grid: ImageGrid = None` 类属性删除（仅 `medal_fire` 内部引用）；`ImageGrid` import 保留（`order_medal` cached_property 仍用）。
  - `RealmRaid` import 精简：`from tasks.RealmRaid.config import RealmRaid, AttackNumber, WhenAttackFail` → `... import WhenAttackFail`（`RealmRaid` 配置类与 `AttackNumber` 模块内零引用，`config_model.py` 另有独立 import；`WhenAttackFail` 仍用于分支判断）；`import time` 随 `medal_fire`（唯一 `time.sleep` 使用者）删除后变死一并删。
  - `KekkaiActivation` 删 `from tasks.KekkaiActivation.utils import parse_rule`（模块内零引用；`utils.py` 里函数本体保留不动，最小范围）。
  - `KekkaiUtilize.ScriptTask` 删 `last_best_index = 99` 死类属性（全仓零读取者，§8 早已记录）。
- **DEFERRED —— Level C 耦合（不改，记录）**：RealmRaid `fire()` / `fire_again()` / `check_refresh()` 尾部不可达 `return False` + `run()` 里 `if not self.fire(index)` 死分支——这三处不可达语句正是未来「加战斗页正向确认 / 加 timeout 失败路径」的接入点，删掉会抹掉设计信号；`fire` 判定改造是 Level C（R-R1/R-R2）。`find_one` 原地涂黑共享帧（R-R9）改动需真机确认涂黑是否仍必要。`harvest_card` 状态化（T4-4）。
- **DEFERRED —— 语义不唯一（不改，记录）**：`KekkaiActivation.ocr_time()` 失败 `return None` → 调用处 `set_next_run(None + now)` → `TypeError`——crash 属实，但正确恢复（`raise GameStuckError` 一致化 vs 固定兜底间隔 vs retry）**源码无法唯一确定**；`KekkaiUtilize.check_utilize_add` 「5 轮」return 语义不一致——改会让 `run()` 提前 return、跳过 `check_max_lv`/收菜/收盒子，是否有意需产品决定（§8 已记「不影响正确性」）；`run_utilize` U3 `goto_page` 失败不 return。
- **KEPT / NOT_REPRODUCED（不改，记录）**：
  - `KekkaiActivation.check_card_num` 用 stdlib `random.randint` —— **不改**：D007 的「已存在未迁移用法按既有决定保留，不为形式统一做无关重构」条款 + `RyouToppa.flush_area_cache` 同款 `random.randint`（列表滑动坐标）被 D007 明确保留的先例。留给未来专门的随机源一致性 pass。
  - `KekkaiUtilize.run` 的 `lazy_roll = random_delay(0.0, 1.0)` —— **NOT_REPRODUCED**：`random_delay` 在本项目里是 `return _rng.uniform(a, b)` 的**纯函数、无 `time.sleep` 副作用**，`lazy_roll` 已经是「从公共 `SystemRandom` 取 `[0,1]` 均匀样本」，运行行为正确；只是函数名有误导，改需新增 `random_float`/`random_probability` helper（超出安全批次范围），留给未来可读性 pass。
- **改动文件**：`tasks/RealmRaid/script_task.py`（本轮 100% 由本批产生：`-import time` / `-2 个 dead import 名` / `-medal_grid` / `-is_ticket` / `-medal_fire`，共 59 行删除）、`tasks/KekkaiActivation/script_task.py`（`-1` dead import）、`tasks/KekkaiUtilize/script_task.py`（`-1` 行 `last_best_index`，其余 `M` 是更早轮次阈值 WIP，本批未碰）、`tests/test_realm_raid_state.py`（4 个「死代码存在」测试 → 2 个「死代码已删、守卫不被重新引入」测试；`test_every_wait_until_appear_call_omits_wait_time` 阈值 `>=5` → `>=4`（`medal_fire`/`is_ticket` 删除后活跃路径剩 4 处 `wait_until_appear`））。
- **回归 710 → 708**（净 `-2`：`test_realm_raid_state.py` 41 → 39）。**无生产运行语义变化**——全部是零引用死代码删除。GeneralBattle / T7 / FrameWait 完全未碰。
- 剩余 cleanup 队列见 `docs/状态验证与重试模式归纳.md` §16 与本节 DEFERRED 项，下一批处理「语义唯一的 B 类 correctness」或等 Level C。

### 4.37 Exploration 状态机静态收口（characterization，第四案例）

2026-09-02。状态驱动主线第四个静态收口对象（前三：`list_find` §4.19、Kekkai §4.33、RealmRaid §4.34）。**只读审查 + 建模 + characterization，未改任何 Exploration 生产行为**——`git diff -- tasks/Exploration/` 为空，对 HEAD **零 diff**。完整控制流 / State Matrix（E1~E15）/ 目标选择与进攻逐条 / 四案例对比 / D015 逐条再验证 / Issue Register（E-1~E-9）见 `docs/Exploration状态机静态收口.md`。

- **Exploration 是四案例里唯一「本身已经是 page-dispatch FSM」的任务**：`run()` = `pre_process()` → `exec_exp_page()` → `post_process()`；`exec_exp_page()` 的 `while True` 每轮 `screenshot()` → `get_current_page()` → `exp_page_handle_dict` 查表执行 handler。无迭代上限 / 无总 `Timer`——靠 `check_exit()`（够怪数 / 超时 / 队友等待超时）+ `InviteFailedException` 收敛（state-bounded）。
- **与 RealmRaid 的核心差异——`fire()` 用正向战斗页确认 + 双重上界，且会返回 `False`**：判据是 `get_current_page() in (pages.page_battle_prepare, pages.page_battle) → return True`（**新页面正向出现**，不是「旧标识消失」）；`while max_tries > 0 and not timeout_timer.reached()`——`max_tries = 4` **且** `Timer(10)`（任一到即停）；耗尽 `return False` → `run_on_exp_main` 做 Task 层 recovery（`swipe(S_SWIPE_BACKGROUND_RIGHT)` 找下一个怪 / `arrive_end()` 则 `quit_exp_main()`）。这正是 `docs/RealmRaid状态机静态收口.md` §6「stronger candidate: old disappeared **and** expected appeared」里 **expected-appeared 那半在 Exploration 中已是生产实现**——RealmRaid `fire()`（R-R1）未来改造可直接照 `fire()` 形状抄，无需重新设计。
- **GeneralBattle 交接是浅耦合**：`run_on_battle` → `run_general_battle(cfg, exit_matcher=pages.page_exp_main)`（`exit_matcher` 是 `Page` 对象，走 `_evaluate_exit_matcher` 的 `isinstance(target, Page)` 分支）；返回值**被丢弃**。Exploration **只覆写 `_exit_matcher()`**（→ `page_exp_main` 三选一识别），**未覆写** `_handle_result` / `_handle_reward` / `_settlement_click` / `PREPARE_CLICK_DELAY_RANGE` / `SETTLEMENT_CLICK_INTERVAL_RANGE`——结算 100% 走基类 Contract v2 默认（`(0.7, 1.0)`）。对比 RealmRaid：覆写 `_handle_result` + 两个时序常量。
- **输入全走 `Control`**：`self.click` / `self.swipe` / `appear_then_click`，**无一处 `swipe_adb` / `click_adb` / 直连后端**（对比 Kekkai 两处 `swipe_adb` 直连绕过 BehaviorTrace）。BehaviorTrace 全覆盖。
- **结构稳定等待用既有原语**：`arrive_end()` = `click_record.count(S_SWIPE_BACKGROUND_RIGHT.name) >= 6` **或** `_match_end.stable(...)`，`_match_end = RuleAnimate(self.I_SWIPE_END)`（2 帧模板结构稳定，`module/atom/animate.py`）——**不是** `module/base/frame_wait.py`。Exploration FrameWait 生产消费者 = **0**。
- **循环边界**：`fire()` 双重有界；`open_expect_level` 第一段 `swipeCount >= 25 → GameStuckError`；`fill_shikigami` 三条 `break` + `GameStuckError` 兜底；`goto_page` `Timer(30)`。**无界裸 `while`（无 Timer 无计数）= 0**（对比 RealmRaid 6 处、KA 4 处）。**唯一 1 处 `wait_until_appear` 调用带 `wait_time=3`**（对比 RealmRaid「全部不传」）。
- **D015 再验证**：逐条对照 Exploration 证据（见专题 §18），**D015 无需修改**——四条案例里 Exploration 对每一条都正向印证，并把「未来 bounded-retry primitive」从纯设想升级为「有一个生产参照实现（`fire()`）」。唯一补充（写在专题文档，不改 D015 正文）：`fire()` 缓存了 `roi_front` 窗口（`search_up_fight` 原地改写 `I_NORMAL_BATTLE_BUTTON.roi_front`），未来迁移时 `action` callback 要包含「重新 `search_up_fight` 定位」而非只在固定 ROI re-match（对应 D015 硬约束 #2）。
- **改动**：新增 `tests/test_exploration_state.py`（33 用例）+ `docs/Exploration状态机静态收口.md`。**未改** `tasks/Exploration/*` / `GeneralBattle` / `base_task.py` / 任何生产代码。
- 测试 `tests/test_exploration_state.py`（33）：见 §7。回归 708→741。**无生产运行语义变化。**

### 4.38 `appear_then_click` / `confirm_delay` / Reaction Timing 全仓专项审查

2026-09-02。「点击前反应延迟职责收口」专项——纯静态审查，**未改任何生产代码、未新增测试**（`tests/test_base_task_confirm_click.py` 5 用例已充分），production diff = 0。完整报告 `docs/Action点击前反应时序静态审查.md`（31 节），长期契约扩写进 `docs/DECISIONS.md` D001。

- **核心问题「`confirm_delay` 能否作为可识别 Point Action 的统一 reaction timing」→ PARTIAL**：能力实现正确（识别 → `sleep(random_delay(lo,hi))` → `self.screenshot()` fresh → 二次 `appear`（目标没了 `return False` 不点）→ 在新帧 `roi_front` 上 `coord()`，`ClickSampler` 采样在 fresh + relocate 之后），满足 Fresh Frame Contract（模式 A）+ Target Relocation（`RuleImage` target、无 `action=` 时）；但**不应「统一」**——全仓 486 处 `appear_then_click` 调用**零处**传 `confirm_delay`，D001「逐点显式 opt-in」无新证据推翻。
- **`appear_then_click` 真实实现**：默认路径 = `appear`（不截图，读调用方帧）→ 命中即 `coord()` → `device.click`，返回 `appear`，**无 delay**；`confirm_delay` 路径 = 见上（唯一「等待后重新截图 + 重新生成坐标」的路径）。`interval` 是 `Timer` 门控（不 sleep），与 `confirm_delay` 顺序叠加、职责不同。
- **是否新增 `reaction_delay` API → 否**：`confirm_delay` 就是该 primitive；`reaction_delay` / `CLICK_REACTION_DELAY` 已有前科被删（D008）。
- **timing 分层**（写进 ARCHITECTURE §2 BaseTask 约定 + D001）：Micro（`confirm_delay`，单 Action 内）/ Throttle（`interval`，跨轮次）/ State Wait（`wait_until_*`、`frame_wait`）/ Macro（`FatigueManager` idle·rest，仅 task-cycle 安全节点、RyouToppa + Orochi/EvoZone 单人 + RealmRaid + Exploration solo + ActivityShikigami 爬塔线、`try_break` 不截图不重识别 state）。四者 owner 不同、不叠加。**Action Transaction**（`State recognized → reaction → fresh relocation → Action → Verify`）原子性：Fatigue 不在其中途插入（当前由构造保证），每个 Retry attempt 是新 transaction（Exploration `fire()` 已是此形态）。
- **Fatigue × confirm_delay**：当前**不会**在同一 Action 上叠加——`try_fatigue_break` 只在 RyouToppa 主循环 `attack_area()` 返回后、`continue` 前（task-cycle 边界），不在任何 `appear_then_click` / `self.click` 内部。
- **GeneralBattle**：有自己的 `PREPARE_CLICK_DELAY_RANGE` / `SETTLEMENT_CLICK_INTERVAL_RANGE` 时序契约（v2），结算走 `_sample_settlement_click(C_RANDOM_RD)` 区域点击**不走 `appear_then_click`**；**永不叠加 `confirm_delay`**（`test_general_battle_timing.py` 已守卫）。
- **RealmRaid `I_FIRE`**（`appear_then_click(I_FIRE, interval=1)`）是最典型 Image Point Target，但**在 R-R1 判定改造（bounded retry）之前加 `confirm_delay` 无意义**——`fire()` 循环本身还没有收敛保证。`partition` 点击是 Static Region（`C_PARTITION_*`），不能迁 `appear_then_click`。
- **Kekkai `harvest_card`**：8 处 `appear_then_click` 全无 `confirm_delay`、全跑同一帧；加 `confirm_delay` 会顺带引入 fresh frame，但真正缺口是「无 semantic verify / 无 reward 闭环」（T4-4），应先做 State→Action→Verify 再谈 reaction timing。
- **D001 继续成立并扩写**（`confirm_delay` = Point Action 官方 reaction-timing 机制、逐点 opt-in、不新增同义 API、macro/micro 不叠加、不替代 semantic wait / retry throttle）；**D015 继续成立**（`confirm_delay` 是「单 attempt 内 reaction + 就地 fresh revalidate」的合规缩影，与未来 bounded-retry primitive 硬约束 #2/#3/#4 一致）。
- **下一步**：只固化职责文档（已完成），不加 opt-in；首个 opt-in 待 Level C，随 RealmRaid `fire()` bounded 改造一起，参数用 manual click / BehaviorTrace 数据标定。

### 4.39 GeneralBattle 新通用结算策略迁移（SETTLEMENT CONTRACT V3）

2026-09-03。正式生产迁移——把通用结算从「旧多轮 opportunistic settlement click（`C_RANDOM_RD`
+ HABIT profile，Contract v2）」换成「**Generic Result 强制两次点击序列 + Reward
layout-aware region policy**」。当前状态见 §4.3.1（详细契约）。要点：

- **只改一个生产文件** `tasks/Component/GeneralBattle/general_battle.py`：删 `_SETTLEMENT_PRIMARY_PROFILE`
  / `_SETTLEMENT_FALLBACK_PROFILE` + `ClickProfile` / `STRATEGY_HABIT` import，加 `random_int`
  import；`_sample_settlement_click(rule)` 改整 ROI 均匀；`_settlement_click(context, region=None)`
  默认 `C_RANDOM_DEFAULT`；新增 `_is_generic_result_context` / `_advance_generic_result` /
  `_select_reward_region`；`_handle_result` / `_handle_reward` 按新结构改写。`assets.py`（三个
  新区域 + 两个 marker + 两个 PNG）是**用户此前 WIP**，本轮未再动。
- **RD/RD2 全仓清理**：生产（`general_battle.py`）零残留；`tests/test_general_battle_settlement.py`
  重写为 V3（37→54）；`tests/test_general_battle_timing.py` 2 处结算断言改 V3（仍 17）；
  `dev_tools/settlement_trace_check.py` + `tests/test_settlement_trace_check.py` 按 3 区域名 +
  整 ROI 做**最小更新**（16→17，不校验双击时序 / 80-20 分流——那是 V3 Level C 设计）；
  `tests/test_ryoutoppa_c_area_1_point_opt_in.py` 的「Settlement 未被 T7 point 路径渗透」
  护栏改指新方法名（仍 25）。
- **不变**：`is_win`（`I_FALSE`→loss）、`_exit_matcher`、2.5s missing fallback、`run_general_battle`
  FSM、`random_click()`（navigation，与 Settlement 分离）、`RuleClick.coord` 默认 `LEGACY_UNIFORM`、
  RealmRaid / RyouToppa / Exploration / Kekkai / `module/*` / Control / 后端。Fatigue / FrameWait /
  retry primitive / `confirm_delay` 不参与。
- **回归 741→759**（settlement 54 + timing 17 + trace-check 17 + ryoutoppa-opt-in 25）。
  `general_battle.py` `git diff --check` 干净。
- **Level C 待验**：见 §4.3.1 末尾列表 + `docs/DECISIONS.md` D016 + `docs/ROADMAP.md`。
- **长期契约**：`docs/DECISIONS.md` **D016**（RD/RD2 deprecated 不复活 / Generic Result
  mandatory two-action sequence / Reward Layout Discriminator policy / 三区域是 Large Safe
  Region 走 uniform；不写死 0.7~1.0 与 80/20 参数）。

### 4.40 KekkaiUtilize 蹭卡 / 好友寄养流程重新审查

2026-09-03。用户要求重新把「现在 KekkaiUtilize 到底怎么找卡 / 选卡 / 切区 / 判收益 / 滑动 /
回选 / 寄养 / 失败恢复」讲清楚，并与目标人工流程做 Gap 对比。**纯只读审查——`tasks/KekkaiUtilize/`
diff = 0，未改任何生产代码 / 测试 / 未接 FrameWait**。完整状态图 A/B + Gap Matrix（16 项）+
逐函数解析 + 最小重构边界见 `docs/KekkaiUtilize蹭卡流程重新审查.md`。

- **结论：PARTIAL。** 蹭卡状态机骨架大体到位（有界扫描、逐张点开读收益、跨区/同区双分组、
  按收益值回选、寄养两层真实 verify、不依赖好友名 OCR、fresh screenshot、随机源统一）。
- **三大差异**：
  1. **跨区 / 同区顺序 = `config.select_friend_list`，默认 `SAME_SERVER`（同区）优先——与「跨区
     优先」相反**（`run_utilize` `enumerate((friend, fallback_friend))`）。
  2. **同一屏内扫描顺序 = 屏幕 y 位置从上到下，不是星级**——`ImageGrid.find_everyone` 按 y 升序
     返回，`order_cards` 只用于 `_card_rank`（挑最优），不影响点击顺序；会先点物理靠上的 4 星
     再点靠下的 6 星（除非该类型 6 星已被点开确认满值触发剪枝）。用户要「优先检查六星」。
  3. **默认收益阈值 = 六星满值（太鼓 76 / 斗鱼 151）→ 实际行为 = 「扫完整列表 + `_reselect_best_card`
     回到顶部按收益值回选最优」，不是「找到满足条件就立即寄养」**。`_reaches_reward_threshold`
     命中会立即停，但默认阈值 = 理论最高值、满值卡罕见 → 几乎总走扫全 + 回选。
- **最小重构边界（下一轮，不重写整个 KekkaiUtilize）**：`run_utilize` 头部分组顺序（跨区固定
  优先，改 config 默认或硬编码）+ `_current_select_best` for 循环（同屏候选按星级降序排序 +
  OCR 失败 `continue` 前同步 `utilize_last_*` 防带错卡）+ `_select_optimal_resource_card` 后半 /
  `_reselect_best_card` 存废（让「命中阈值即寄养」成主路径）+ `config.py` 默认值。`check_card_num` /
  `order_targets` / `CARD_TIER_INFO` / `switch_friend_list` / `perform_swipe_action` / failure
  recovery / 寄养 verify / lazy 模式 **不动**。
- **GeneralBattle V3 与 KekkaiUtilize 无任何调用 / 继承关系**（MRO 不含 `GeneralBattle`，`grep`
  零命中）——本轮重做蹭卡属独立业务状态机调整。
- **未实现项**：detail load verify（`click(C_SELECT_CARD)` 后固定 `sleep(2)`）、swipe stable
  verify（`perform_swipe_action` `swipe_adb` 后固定 `sleep(2)`，`SWIPE_DISTANCE=416` 未真机核）
  —— Level C，本轮禁止接 FrameWait。`perform_swipe_action` 的 `swipe_adb` 直连仍不进 BehaviorTrace
  （`S_U_END` 滚到顶走 `Control.swipe` 有 trace）。

> **§4.40 是「改造前审查」；改造已于 2026-09-03 同日实施 → 见 §4.41。** 审查里的三大差异
> （跨区优先默认反了 / 同屏非星级序 / 默认阈值使行为=扫全+回选）已由 §4.41 的 PASS 序列 +
> 阶段化阈值 + 命中即寄养解决。

### 4.41 KekkaiUtilize 单向分区搜索改造（取消蛇形 / PASS 序列 / 阶段化阈值）

2026-09-03。正式业务搜索策略变更——非怠惰路径的好友结界卡搜索从「扫全列表 + global-best +
`_reselect_best_card` 回选」改成「按 PASS 序列，每个 PASS 都 TOP→BOTTOM 单向扫描、命中阈值
立即寄养、最后一个 PASS 兼任兜底」。长期契约 `docs/DECISIONS.md` **D017**。完整实施记录见
`docs/DEVELOP_LOG.md`「2026-09-03 KekkaiUtilize 单向分区搜索改造」。

- **PASS 序列**（每个 PASS 前只 `switch_friend_list(该分组)` 切一次——**2026-09-06 起**
  标准路径不再调用 legacy `_reset_utilize_friend_list`，见下方「PASS 前初始化简化」）：
  - 优先跨区（`config.select_friend_list == DIFFERENT_SERVER`）：`跨6★HIGH → 同6★HIGH →
    降一档 → 跨5/6★LOWER → 同5/6★LOWER(final)`（跨→同→跨→同）。
  - 优先同区（默认 `SAME_SERVER`）：`同6★HIGH → 跨6★HIGH → 降一档 → 同5/6★LOWER(final)`
    （同→跨→同）。相邻 PASS 的 `friend_group` 一定不同（契约，测试锁）。
- **第一阶段只搜 6★、用高阈值**（`taiko/fish_reward_threshold` 配置值，默认满值 76/151），
  不扫 5★/4★。**第一阶段全失败后阈值降低一档一次**（`lower_reward_tier`，离散档位：斗鱼
  `101…151`、太鼓 `42…76`；不是减固定数；只降一次），第二阶段搜 **5★+6★**（6★ 也可能只有
  118，星级 ≠ 收益档）。
- **发现候选 → 点击 → 详情 OCR → 达本 PASS 阈值 → 立即寄养**，不再找全列表理论最优 / 不回选。
- **最后一个 PASS 自身兼任兜底**：扫到 `I_U_EMPTY_CARD`（到底）时，本 PASS 至少点开过一个
  候选 → 直接用「最后一次点击、仍保持选中」的候选寄养（不查阈值 / 不回头 / 不存坐标·好友名·
  页码）；一张候选都没点开 → 返回失败交外层 bounded recovery，**不盲目点【进入结界】**。
  PASS 内只用一个局部 `has_clicked_candidate` bool。**没有第四种独立 FALLBACK 轮次。**
- **BOTTOM ≠ SAFETY**：`appear(I_U_EMPTY_CARD)` = 真正到底；`Timer(120)` 超时 / 滑满
  `SEARCH_MAX_SWIPES=20` 屏没见到 marker / 切分组超时 = SAFETY_ABORT（外层重试，不当作到底）。
  **「连续几屏没有目标模板」不是到底**——列表乱序，继续下滑（旧标准路径的 `miss_count >
  CONSEC_MISS → 到底` 已移除；怠惰路径豁免，保持原样）。
- **复用不变**：`ImageGrid.find_everyone`（card-column `roi_back` + 当前帧真实 bbox + y 排序）、
  `C_SELECT_CARD.roi_front = area` 动态点击、`check_card_num()` OCR。**未引入**好友行 anchor /
  固定行 / 好友名 OCR / 新列表检测器 / TOP 搜索框。用户 WIP 新加的 `I_K_SEARCH` asset
  （「结界卡顶部搜索框」）**未接线**（spec 明令不用 TOP marker）。
- **未改**（指 D017 单向分区改造本身）：`SWIPE_DISTANCE=416` 几何（**K2 2026-09-07 起标准
  minitouch 路径改随机 `SWIPE_DISTANCE_RANGE`（首档 (212,265) → 2026-09-07 Level C 回调 (140,180)），
  见下方「K2」；怠惰 / 非 minitouch 回退仍 416**）；swipe
  settle（**K3 2026-09-07 起标准 minitouch 路径从固定 2 秒等待改成 FrameWait，见下方「K3」；
  怠惰 / 非 minitouch 回退仍 2 秒**）；未改结界卡 ROI / `image.json`（`I_K_SEARCH` 是用户 WIP）；
  未新增配置项；`check_utilize_add` / `switch_friend_list` / 寄养 verify / failure recovery /
  怠惰模式 / `KekkaiActivation` 零影响。

**K1（2026-09-04）—— 标准 PASS 搜索的列表下划 ADB → minitouch trajectory（只换输入后端）**：
`_run_search_pass` 的下划入口从 `perform_swipe_action()` 换成新的 **`_perform_search_swipe()`**：
`control_method == 'minitouch'` → `TouchSwipeModel().generate((rand_x, rand_y), (rand_x,
rand_y - 416))`（同一起点安全区 `(340,600)`×`(500,565)` + **同一 416px 主方向位移**，用
模型第二阶段正式默认参数，本轮不覆盖）→ `self.device.swipe_trajectory(trajectory,
control_name='KEKKAI_UTILIZE_SWIPE')`（经 `Control.swipe_trajectory` → minitouch executor →
BehaviorTrace `ACTION`/`swipe`）→ `click_record_clear()` → `time.sleep(2)`；**非 minitouch**
（adb / uiautomator2 / …）→ 显式回退 `perform_swipe_action()`（旧 `swipe_adb` 路径逐字不变，
不抛 `NotImplementedError`）。**怠惰模式 `_select_lazy_resource_card` 仍走
`perform_swipe_action()`，全模块 `swipe_adb` 调用点仍恰 1 处。** D017 业务契约（PASS 顺序 /
threshold / bottom / final fallback / lower once / OCR / group switch / lazy）逐项不变。
`TouchSwipeModel` 由此得到**首个生产消费者**（`Control.swipe_trajectory` 首个 caller）。
`test_kekkai_utilize_state.py` 46→53，回归 897→904。**前置已解除（2026-09-04）**：`oas2`
从结界页 OCR「式神育成」导航进页此前直接 `TypeError` 崩、K1 根本到不了，`RuleOcr` 浮点 bbox
兼容修复（§4.43）后这条导航才通。

**K2（2026-09-07）—— 标准 PASS minitouch 路径的 commanded 位移固定 416px → 每次独立随机
一个较短位移**：`_perform_search_swipe()` 的 minitouch 分支里 `distance = random_int(*self.
SWIPE_DISTANCE_RANGE)`，`end = (start_x, start_y - distance)`。`SWIPE_DISTANCE_RANGE` 是
**provisional、Level C 分档调参**（`KEKKAI_ROW_PITCH_PX = 106`，y≈220/326/432/538，一屏约 4 格；
旧 416px ≈ 3.9 格接近整屏 → 严重跨项漏卡）：
  - **首档 `(212, 265)`**（≈2.0~2.5 row_pitch）—— 2026-09-07 **首次 Level C 实测「一次内容仍滚 >4 格」**，
    确证 **commanded finger distance ≠ actual content scroll**（好友列表惯性放大），判定过大。
  - **当前 `(140, 180)`**（≈1.3~1.7 row_pitch 手指位移，整体降约 1/3）—— 受惯性放大预计实际仍滚
    2~3 格，目标是相邻两屏至少保留 1~2 格重叠（A B C D → B C D E / C D E F），避免几乎无重叠的大跨步。
  - 若二次 Level C 仍实际 >3 格，下一档缩到 `(110, 150)`——单变量分阶段，本轮不直接跳第二档。
- **轻微整体斜度（2026-09-07，仅 minitouch）**：`lateral_offset = random_int(*SWIPE_LATERAL_OFFSET_RANGE)`
  （`SWIPE_LATERAL_OFFSET_RANGE = (-12, 12)`，provisional，Level C 调整），`end_x = clamp(start_x +
  lateral_offset, *SWIPE_START_X_RANGE)`，`end = (end_x, start_y - distance)`。**只作用于最终
  `end_x`**——不给每个 MOVE 点加噪声；宏观轨迹由旧的「`end_x == start_x` 接近严格竖直」变成「有的
  轻微左斜 / 有的轻微右斜 / 有的接近竖直」，整体仍明确向上 swipe。`end_x` 夹回起点安全区
  `SWIPE_START_X_RANGE`（**不扩大 `start_x` 范围**）：start_x 贴边界时偏移被裁掉、退化竖直，
  绝不滑出可接受区。`TouchSwipeModel().generate(start, end)` 仍只调一次、仍只收 start/end。
- **只改「滑多远 / 往哪斜」**：起点安全区 `(340,600)×(500,565)`（`start_x` 范围不变）/
  `TouchSwipeModel().generate(start, end)`（零参构造，只给 start/end）/ 曲率 / 时间模型 / tail /
  `swipe_trajectory` 恰一次 / `control_name='KEKKAI_UTILIZE_SWIPE'` / `click_record_clear`
  全不变（swipe settle 的 `sleep(2)` 由 **K3** 另行替换成 FrameWait，见下方「K3」）。
  **`TouchSwipeModel` 一行未改**（D018：`SWIPE_DISTANCE` / `SWIPE_DISTANCE_RANGE` /
  `SWIPE_LATERAL_OFFSET_RANGE` 具体值本就是「可 Level C 调整」、不是长期设计决策，不新建 ADR）。
- **怠惰路径（`_select_lazy_resource_card` → `perform_swipe_action` → `swipe_adb`）与非
  minitouch 回退仍固定 `SWIPE_DISTANCE=416`，本轮不动**；全模块 `swipe_adb` 调用点仍恰 1 处。
- D017 业务契约（PASS 顺序·threshold·stars·`PassResult`·`FINAL_USE_LAST`·`I_U_EMPTY_CARD`·
  `SEARCH_MAX_SWIPES=20`·`SEARCH_PASS_TIMEOUT=120`·`switch_friend_list` 初始化）逐项不变。
- **契约**：K2 只减小 **commanded finger 位移**、建立重叠；**不保证** actual content scroll
  格数与 commanded row 估计一致（Level C 已确证游戏列表惯性放大）。「finger distance ≠ content
  displacement」的测量与补偿是 **K4**（记录 `commanded distance` vs 实际移动格数 → `scroll_gain`），本轮不做。
- `PerformSearchSwipeK2Test`：距离用例（`SWIPE_DISTANCE_RANGE == (140, 180)`、`lo<hi`、≈1.3~1.7
  row_pitch、`hi < 212`、`hi < 416` / 每次独立采样 140·160·180、大样本恒在 `[140,180]` 且重采样、
  均 `< 212` / 起点范围不变 / settle·control_name·trajectory 恰一次不变 / 怠惰·非 minitouch 回退仍
  416 / D017·TouchSwipeModel 未动）；**新增 2 个斜度用例**（`SWIPE_LATERAL_OFFSET_RANGE == (-12, 12)`
  有正有负 / `end_x = clamp(start_x + lateral_offset, *SWIPE_START_X_RANGE)`、`end_y` 不受影响 /
  中段起点能左斜·右斜·竖直 / 起点贴边界时偏移被有界裁掉退化竖直、`end_x` 始终在安全区内 /
  大样本 400 次 `end_x` 恒合法、出现过左斜·右斜·竖直 / `_perform_search_swipe` 源码里
  `lateral_offset = random_int(*self.SWIPE_LATERAL_OFFSET_RANGE)` + `end = (end_x, start_y - distance)`）；
  `PerformSearchSwipeK1Test` / K3 用例的 `random_int` side_effect 补第 4 个值（lateral）。
  `test_kekkai_utilize_state.py` `84 → 86`（+2 斜度用例），完整回归 `1025 → 1027`。
- **二次 Level C 待验收**（`(140, 180)` + 斜度）：① 实际一次滚几格 / ② 是否仍 >4 格 / ③ 能否稳定保留
  1~2 格重叠 / ④ 是否出现滑动太小、列表几乎不动 / ⑤ K3 `changed` 是否仍稳定命中 / ⑥ K3 `stable`
  是否正常 / ⑦ OASX swipe trajectory 里 commanded distance 是否确实落在 140~180、`end_x` 是否呈现
  轻微左右斜且不越安全区。若距离仍实际 >3 格 → 下一档 `(110, 150)`。
  K1 的「minitouch 是否被识别为滑动 / 尾段 fling / OCR·bottom 不受影响」
  一并在同一次真机核。

**K3（2026-09-07）—— 标准 PASS minitouch 路径的 swipe settle 固定 2 秒等待 → FrameWait
changed+stable**：`_perform_search_swipe()` 的 minitouch 分支不再 `time.sleep(2)` 猜页面停稳，
改成 **baseline（swipe 前明确重截一帧）→ swipe → `wait_for_changed_and_stable(baseline,
self.device.screenshot, roi=SWIPE_WAIT_ROI, changed_threshold=…, stable_threshold=…,
stable_frames=…, timeout=…)` → 返回 `wait.success`**。方法签名 `-> None` 改 `-> bool`。
- **首个 FrameWait（`module/base/frame_wait.py`）生产消费者**——此前 D010/D012 记「纯能力 +
  零生产消费者」，现修正为「唯一消费者 = `KekkaiUtilize._perform_search_swipe`（标准 PASS +
  minitouch）」；怠惰 / 非 minitouch 回退 / 其它任何路径都不接。
- **失败语义**：`changed` 迟迟不出现 / `changed` 后一直不 `stable` / `timeout` → `wait.success`
  为 `False` → `_perform_search_swipe()` 返回 `False` → `_run_search_pass` 立即
  `return PassResult.ABORT`（外层 bounded recovery）。**`no change ≠ BOTTOM`**：D017 唯一
  BOTTOM marker 仍是 `I_U_EMPTY_CARD`；本轮不新增「滑不动 → PASS_MISS」隐式到底。方法内部
  **一次 swipe → 一次 FrameWait，无重试**（bounded recovery 只在 `run_utilize` 外层）。
- **baseline 必须 swipe 前重截**：`_run_search_pass` 里 `check_card_num()` 内部会自截，
  `self.device.image` 在 `_perform_search_swipe()` 入口可能是候选卡详情页帧，所以在方法内
  swipe 前显式 `self.device.screenshot()` 取 baseline，不复用 `self.device.image`。
- **ROI 只盯 card-column**：`SWIPE_WAIT_ROI = (525, 155, 620, 610)`（`(x1,y1,x2,y2)`，取
  `I_U_*_6` / `I_U_EMPTY_CARD` 的 `roi_back` 包络，排除右侧详情栏 / tab / 底部 UI / OCR 数字）。
- **阈值 provisional**：`SWIPE_WAIT_CHANGED_THRESHOLD=0.10` / `SWIPE_WAIT_STABLE_THRESHOLD=0.02` /
  `SWIPE_WAIT_STABLE_FRAMES=3` / `SWIPE_WAIT_TIMEOUT=3.0`，全部类常量 + 注释标「需 Level C 调整」
  （用 `swipe wait` 日志的 `elapsed` 分布回填）。FrameWait 本层无业务默认，阈值都由 KekkaiUtilize 显式传。
- **`poll_interval` 显式覆盖**：`SWIPE_WAIT_POLL_INTERVAL = 0.15`（秒）**显式传给 `wait_for_changed_and_stable`**，
  不吃 FrameWait 全局默认 `poll_interval=0.0`。理由：好友列表 swipe 后的惯性微滚可能让相邻两帧差异
  < `SWIPE_WAIT_STABLE_THRESHOLD`，零间隔高速轮询下连续 `SWIPE_WAIT_STABLE_FRAMES` 帧会提前判
  stable（甚至连抓同一渲染帧）；加一档 pacing 让这 3 帧跨越更长真实时间窗。属**检测采样 pacing**、
  叠在 `device.screenshot` 自带 `_screenshot_interval`（~0.1s）之上，**不是恢复固定 `sleep(2)`**
  （settle 仍以 changed&stable 为准、命中即返回）。**provisional，需 Level C 调整**（`_screenshot_interval`
  已够 → 可回 0；惯性帧仍 alias → 调大）。不动上面 4 个判定阈值；FrameWait 全局默认也不改。
- **不变**：K1（`TouchSwipeModel().generate(start,end)` / `swipe_trajectory` / `control_name`）、
  K2（`random_int(*SWIPE_DISTANCE_RANGE)` 每次随机采样，当前档 `(140, 180)`）、`click_record_clear`、
  BehaviorTrace（一次 swipe = 一个 ACTION，FrameWait 轮询不产生额外 ACTION）、D017 业务契约、
  怠惰 + 非 minitouch 回退（仍 `perform_swipe_action`：固定 416 + 2 秒等待，不接 FrameWait）。
  **`TouchSwipeModel` / `FrameStateDetector` / `wait_for_changed_and_stable` 本体一行未改。**
- 新增 `PerformSearchSwipeK3Test`（13 用例）+ `RunSearchPassTest.test_swipe_wait_failure_maps_to_abort_not_bottom`；
  改 `UtilizeStructureTest.test_no_frame_wait_consumer_in_utilize` → `..._is_only_perform_search_swipe`（正向锁「唯一消费者」）；
  改 K1/K2 若干用例（device 加 `screenshot` mock、FrameWait patch 成功、settle 断言从 `sleep` 改 `wait`）。
  `test_kekkai_utilize_state.py` 69→83，回归 984→998。
- **K4 不做**：actual_scroll_dy / `scroll_gain` 补偿 / 帧间投影 / 重叠去重 / 只处理新进入区域。
- **Level C 待验收**：`SWIPE_WAIT_ROI` 是否恰好框住滚动主体（不含惯性回弹外的 UI）；四个阈值
  是否合适（日志 `changed/stable/elapsed/diff` 分布）；`timeout=3.0` 是否够覆盖惯性拖尾；
  正常滚动是否稳定判 `changed&stable`、真卡死是否稳定判失败进 ABORT；是否比旧固定 2 秒更快。

**PASS 前初始化简化（2026-09-06，Level C 触发）**：Level C 明确确认「**只要 SAME/CROSS
发生实际切换，新进入的好友分组列表必定从顶部显示**」（SAME 滚到底 → 点 CROSS，CROSS 从顶部；
反向同理）。据此 `_run_search` 每个 PASS 前从
`self._reset_utilize_friend_list(search_pass.friend_group)` 改为
`self.switch_friend_list(search_pass.friend_group)`——**标准路径不再滚到底 / 不再切走再切回 /
不再调 legacy helper**。理由：① `_build_search_passes` 保证相邻 PASS 分组一定不同（新增契约测试锁）；
② 首 PASS 若已在目标分组，`switch_friend_list` 检测到选中态直接返回、0 次 tab click；不在则只点
目标 tab 一次；③ 每次实际切换后游戏自动回顶。首次 `find_everyone` 之前：**0 次列表 swipe、
0 次 away/back toggle**，列表第一次滑动只发生在 `_run_search_pass` 的 `_perform_search_swipe`。
`_reset_utilize_friend_list`（含 `S_U_END` 滚到底 + 双切）**保留但仅 `_run_lazy_utilize` 调用**
（怠惰模式行为本轮不动，docstring 标 legacy/lazy-only）。**未改**：K1 `_perform_search_swipe` /
`SWIPE_DISTANCE=416` / `switch_friend_list` 本体 / D017 业务契约（PASS 顺序·threshold·bottom·
final·lower once·OCR·lazy）/ `S_U_END` 资产定义。`test_kekkai_utilize_state.py` 53→62
（新增 `RunSearchGroupSwitchOnlyTest` 9 用例；`RunSearchSequenceTest` 断言从
`_reset_utilize_friend_list` 改 `switch_friend_list` + 断言 legacy helper 零调用），回归 944→953。
**Level C 待验收**：进列表后是否不再「先把整列表拽到底」、当前分组正确时是否 0 tab click、
每个 PASS 切一次即从顶部扫描、找卡命中率不变。
- **删除**（确认零消费者，`KekkaiActivation` 自带 `order_targets` override 不受影响）：
  `_select_optimal_resource_card` / `_current_select_best` / `_reselect_best_card` / `_card_rank` /
  `order_cards` / `order_targets`（KU 版）/ `_reward_threshold` / `_reaches_reward_threshold`；
  `utilize_best_rank/value/card_class` / `utilize_last_card_class/value` / `ap_max_num` / `jade_max_num`。
- **新增结构**：`PassResult`（str Enum）/ `SearchPass`（dataclass）/ `_rule_card_types` /
  `_pass_targets` / `_card_type_matches_rule` / `_card_meets_pass` / `_build_search_passes` /
  `_run_search` / `_run_search_pass` / `_run_lazy_utilize`（`script_task.py`）；
  `FISH_REWARD_TIERS` / `TAIKO_REWARD_TIERS` / `lower_reward_tier`（`utils.py`）。
- **测试**：`test_kekkai_utilize_state.py` 23→46、`test_kekkai_utilize_threshold.py` 25→26
  （见 §7）。回归 **759→783**。`compileall` OK、`git diff --check`（`script_task.py`/`utils.py`）
  干净。
- **Level C 待验收**（未真机，不标 VERIFIED）：`I_U_EMPTY_CARD` 是否 100% = 到底；切区是否
  稳定回顶；`SWIPE_DISTANCE=416` 是否覆盖所有候选；card-column ROI 是否需扩大；ADB→minitouch
  实际滚动量；FINAL_USE_LAST 依赖的「最后点击候选保持选中」是否稳定；`SEARCH_MAX_SWIPES=20`
  是否够滑到 marker；列表/详情卡种偶发不一致（本轮不做复杂 recovery）。

### 4.42 TouchSwipeModel（minitouch 自定义滑动轨迹：基础设施 + 运动学优化）

2026-09-04。承 `docs/Minitouch自定义轨迹能力审查.md` 的 Plan B，落地「模型出纯轨迹数据 →
minitouch 薄执行层 → 显式 `Control.swipe_trajectory` 入口」三层基础设施。长期契约
`docs/DECISIONS.md` **D018**。完整实施记录见 `docs/DEVELOP_LOG.md`「2026-09-04
TouchSwipeModel 第一阶段实现」。**只建基础设施——未接任何任务、未接 `BaseTask`、未启动
MuMu、未真机。**

- **新增 `module/device/touch_swipe_model.py`**（纯逻辑，不 import device / `Config` /
  `BaseTask`）：`TouchSwipeModel(params=None, rng=None).generate(start, end) ->
  list[(x, y, dt_ms)]`。运动学 = minimum-jerk 位置进度 `s(t)=10t³-15t⁴+6t⁵`（起步慢 /
  中段快 / 收尾慢）+ 整体曲率 `curve_amp·sin(πt)`（一次采样、可正可负、幅度受
  `min(max_curve_px, dist·curve_px_ratio)` 约束，无逐点抖动 → 支持左弯 / 右弯 / 近直线、
  不锯齿）+ 逐段 dt（基础节拍 × 两端放慢系数 + 有界抖动，全 `>0` 且夹 `[min_dt,max_dt]`）。
  MOVE 点数随距离变化（`dist/avg_step_px`，夹 `[min_points,max_points]`）。首点 dt 恒 0
  且执行层忽略；起终点强制精确。`TouchSwipeParams`（frozen dataclass，`__post_init__`
  校验）持有全部可调项。`_DefaultRng` 委托公共 `random_int`；`rng=` 可注入确定性实现。
  距离 `<2px` / 非有限坐标 / 非 `(x,y)` / bool 坐标 → `ValueError`。可选 `tail_correction_*`
  尾部微修正**默认关**（开时小概率 / 小幅 / 末段 sin 回 0、不改终点、不反向）。
- **`module/device/method/minitouch.py`（+`import math`，其余纯新增，对 HEAD 之前为零 diff）**：
  - `_ensure_trajectory(trajectory)`（模块级纯校验，**在 `@retry` 之外**调用）：点数 `>=2`、
    每点 `(x,y,dt)`、x/y 有限取整、首点 dt 规整为 0、其余点 dt 取整后 `>=1`，否则
    `ValueError`（不被重试吞成 `RequestHumanTakeover`）。
  - `swipe_minitouch_trajectory(self, trajectory)`：先 `_ensure_trajectory` 再调内层。
  - `@retry def _swipe_minitouch_trajectory_run(self, points)`：`down(p0) →
    [move(pi).commit().wait(dt_i)] → up`，各 `minitouch_send()`。**不套 `insert_swipe`、
    不叠加 `random_int(6,15)`、不改 `Command`/`CommandBuilder`/`minitouch_send`/握手。**
    整个手势用同一个 `_humanized_pressure()`（照 `_press_and_drag_minitouch`）。
- **`module/device/control.py`（纯新增一个方法，`Control.swipe` 及其它一律未改）**：
  `swipe_trajectory(self, trajectory, control_name='SWIPE')` —— `handle_control_check` →
  非 minitouch 后端 `raise NotImplementedError`（**不静默退化成端点滑动**）→ `list()`
  物化（非可迭代 `ValueError`）→ `_invalidate_image_batch_cache` → `perf_counter` 计时 →
  `swipe_minitouch_trajectory` → `logger.info` → `record('ACTION', action='swipe',
  target=control_name, elapsed_ms=...)`（端点级，**不记每个 MOVE**，延续 D004）。
- **测试**：`tests/test_touch_swipe_model.py`（29）+ `tests/test_minitouch_trajectory_executor.py`
  （15）+ `tests/test_control_swipe_trajectory.py`（9）= **+53**。完整回归 **783→836**。
  `compileall` OK；`git diff --check`（`control.py` / `minitouch.py`）干净。
- **未改 / 未接（第一阶段）**：`Control.swipe` / `BaseTask.swipe` / `RuleSwipe` /
  `CommandBuilder` / `Command` / `minitouch_send` / 握手 / `insert_swipe` / `smooth_path` /
  `D007` 的 `np.random` 保留项；`SEARCH_MAX_SWIPES` / FrameWait / 结界卡 ROI；没有
  `BaseTask.swipe_trajectory`。（KekkaiUtilize 第一阶段未接；**2026-09-04 K1 已把「标准 PASS
  搜索」的列表下划迁到 minitouch trajectory**，见 §4.41「K1」。）
- **Level C 待验收**（未真机，不标 VERIFIED）：新轨迹实际滚动量 / 落点 / 逐段 dt 在
  设备侧是否被如实执行 / 是否被游戏识别为「滑动」而非「点击」（minitouch ≥5px）/
  尾段是否自然停止、不误触 click、不产生异常 fling / 与现有 `insert_swipe` 路径的行为差异。
  第一步验收环境用**非游戏 Android 可滚动长列表**（系统设置 / 文件管理器 / 浏览器离线长页），
  过关后才接阴阳师。`TouchSwipeParams` 默认值与 `tail_correction` 去留待真机数据校准。
  **测试工具已就绪**（2026-09-04，纯 dev_tools）：`dev_tools/test_touch_swipe_mumu.py`
  —— 一次性、非循环，`Device(config=...)` 标准初始化 → `model.generate` 只调一次 →
  同一条轨迹存 `log/touch_swipe_test/touch_swipe_<id>.{png,json}` → 人工 Enter 确认 →
  `device.swipe_trajectory(..., control_name='TOUCH_SWIPE_LEVEL_C')` 执行一次 → 退出。
  PNG（cv2，1400×900）：**A1. Screen View 1280×720**（固定 `[0,1280]×[0,720]` 定义域、
  16:9 居中留白、1:1 视觉比例、Y 向下 + 网格刻度 + bbox 参考，**不按轨迹跨度独立缩放**）、
  **A2. ZOOMED VIEW**（按轨迹 bbox 自适应放大看曲率 / MOVE 细节，标题明确 "NOT screen scale"）、
  B. 每段 dt、C. 每段速度、D. 文本统计。可选 `--curve left|straight|right` 经模型已有的
  `rng=` 注入点钉曲率方向（不改生产代码）。`tests/test_touch_swipe_mumu_tool.py` 31 用例
  （纯逻辑，含 `fit_screen_rect` / `screen_to_panel` / `trajectory_bbox` / `zoom_transform`
  坐标变换，不连 MuMu）。零生产改动。

**第二阶段（2026-09-04，时间连续性 + 尾段慢拖）** —— 正式生产模型优化，**只改
`module/device/touch_swipe_model.py` + `tests/test_touch_swipe_model.py`**，未接消费者、
未真机。长期契约 `docs/DECISIONS.md` **D018 第二阶段追加**。完整记录见 `docs/DEVELOP_LOG.md`
「2026-09-04 TouchSwipeModel 第二阶段」。

- **平滑时间扰动**：逐段 dt 的随机从「每个 MOVE 独立 `randint(-3,3)`」改为**一阶低通 / EMA**
  —— `noise_i = dt_smooth_alpha*noise_{i-1} + (1-dt_smooth_alpha)*raw_i`（`noise_0=0`，
  `raw_i = rng.randint(±dt_jitter_ms)`）。凸组合 → 恒有界 / 零均值 / 不长期漂移 / 相邻无
  无界跳变。时间模型固定拆成 **`base_dt(s)` 趋势 + smooth_noise**，趋势 ≫ 噪声。消除第一
  阶段 speed 曲线的中段尖峰 / 锯齿。
- **尾段慢拖**（按「已走距离占比 s」度量，约最后 10~15% 距离）：参数 t 网格 = 主段等距 +
  尾段按 `tail_density_gain` 倍加密（`t_tail = _t_for_s(tail_start_ratio)` 二分求解）；
  尾段在 `slow` 因子上叠加 `tail_slow_gain * smoothstep(k)`（`k=0` 一阶导为 0 → 平滑接续、
  不突跳）。**终点仍精确到原 `end`、不额外滑一段、不做固定 pre-UP 停顿、不做过冲回拉**
  （`tail_correction` 仍默认关，本轮不动）。
- **`TouchSwipeParams` 新增 4 字段**（frozen，范围校验 + 中文注释）：`dt_smooth_alpha=0.72`
  `[0,1)`、`tail_start_ratio=0.85` `[0.5,1.0)`、`tail_density_gain` `[1.0,4.0]`、
  `tail_slow_gain` `[0.0,3.0]`。**改默认值**：`max_dt_ms 28→34`、`max_points 64→80`。
  **尾段力度「收一档」（2026-09-04）**：`tail_density_gain 1.55→1.35`、`tail_slow_gain
  0.55→0.35`（第二阶段 Level C 后，minimum-jerk 自带减速 + 两个 tail 参数三层叠加把末段
  速度压得过低、有「黏住终点」感 → 只调这两个默认值收一档，`tail_start_ratio` 与其它一切
  不动；见 DEVELOP_LOG「尾段慢拖收一档」条）。
  **不动**：`avg_step_px` / `base_dt_ms`(10) / `end_slow_ratio`(0.5) / `dt_jitter_ms`(3) /
  **`max_curve_px`(16) / `curve_px_ratio`(0.12)——空间曲率本轮明令不动，避免和时间模型同时
  改无法归因** / `tail_correction_*`。新增模块级纯函数 `_minimum_jerk_s` / `_t_for_s` /
  `_smoothstep`。
- **静态生成数据（非真机，`CurveRng` 曲率固定 + dt 噪声=0；speed 按 executor 时间对齐 ——
  段 `p_i→p_{i+1}` 用 `dt_i`；下列为「收一档」后 `tail_density_gain=1.35` /
  `tail_slow_gain=0.35` 的值）**：120px→~117ms（phase-1 ~93；收一档前 ~119）、260px→~202~220ms
  （~188；前 ~225~245）、440px→~366~398ms（~333；前 ~395~449）。`mid_dt≈10~11ms` 不变、
  `tail_dt≈13.2~15.2ms`（前 13.5~16.6）；`tail_speed≈0.42~0.76`（前 0.32~0.74）vs
  `mid_speed≈2.27~3.07`。每个 case `tail_avg_speed < mid_avg_speed`、`tail_avg_dt >
  mid_avg_dt`、尾段 speed 连续下降、不过冲不反向、`end` 精确、`120<260<440` 严格成立。
  末端段速度不再贴 0（如 260/left 末 3 段 `[0.20,0.118,0.10]` → `[0.28,0.212,0.111]`）。
  总时长增幅仍来自尾段结构、非 `base_dt` 整体放慢。
- **测试** `tests/test_touch_swipe_model.py` **29→56**：`SmoothDtNoiseTest`（8，
  相邻 dt 无无界跳变 / 扰动不漂移 / `SeqRng` 可复现 / 慢快慢趋势仍成立 / 噪声不盖过趋势 /
  `_t_for_s` 互逆）+ `TailDragSpaceTest`（6）+ `TailDragTimeTest`（4）+ `TotalDurationTest`
  （3，`120<260<440` + 宽松上限）+ `invalid_params` 扩 8 组 + `MoveSegmentAlignmentTest`
  （3，2026-09-04 segment/dt 对齐修正）。既有项（含 executor / Control / correction /
  minimum-jerk / ±曲率 / Level C tool）全过。完整回归 **867→888→897**（888→897 = Level C
  工具 segment speed 与 dt 对齐修正）。
- **未改**：`Minitouch.swipe_minitouch_trajectory` / executor / 协议契约 / `dt` 语义 /
  `Control.swipe_trajectory` / `Control.swipe` / `BaseTask` / `RuleSwipe` /
  KekkaiUtilize / FrameWait / GeneralBattle / RealmRaid / `insert_swipe` 的 `np.random`。
  未加 Fitts / Hick / fatigue / reaction delay。
- **segment speed 与 dt 对齐修正（2026-09-04，仅 dev 工具 + 测试 helper，生产零改动）**：
  从源码核实 executor 命令流 `DOWN(p0) | MOVE(p_i) COMMIT WAIT(dt_i) ... | UP` —— `dt_i` 是
  「到达 `p_i` 后、移动到 `p_{i+1}` 前的停留」（D018 契约本身**正确、未改**）。工具原
  `trajectory_stats` / PNG C.speed / `test_touch_swipe_model` 的统计 helper 把段
  `p_{i-1}→p_i` 配给 `dt_i`（应为 `dt_{i-1}`）—— **相邻错位一格**。修：`dev_tools/test_touch_swipe_mumu.py`
  新增 `trajectory_segments()`（段 `p_i→p_{i+1}` 用 `dt_i`，`i=1..n-2`；排除 `p0→p1`——DOWN 无
  显式 dt、`minitouch_send` 的 `DEFAULT_DELAY` 不并入；排除 `dt_{n-1}`——pre-UP dwell 无下一段），
  `trajectory_stats` 的 `segment_speeds` / `avg_speed` / `max_speed` 全走它 + 新增 `segment_count`；
  PNG C 标题 `speed per SEGMENT (p_i->p_i+1 = dist / dt_i)`、B 标题 `WAIT after MOVE`。**未动**
  `total_dt_ms`（所有显式 WAIT 之和）/ `actual_path_length_px` / `min·max_dt_ms` / JSON schema /
  A1·A2。`test_touch_swipe_mumu_tool` `31→37`（+`TrajectorySegmentsTest` 手算样本
  `[(0,0,0),(20,0,5),(25,0,20),(35,0,10)]` → 2 段 `[1.0, 0.5]` px/ms）、`test_touch_swipe_model`
  `50→56`。回归 `888→897`。上方静态数据表已改为对齐后的值。
- **首个生产消费者 = KekkaiUtilize 标准 PASS 搜索的列表下划（K1，2026-09-04）** ——
  `_perform_search_swipe` 在 minitouch 配置下走 `TouchSwipeModel().generate` →
  `Control.swipe_trajectory(..., control_name='KEKKAI_UTILIZE_SWIPE')`；非 minitouch 回退旧
  `swipe_adb`；怠惰模式不动；416px 几何不变（见 §4.41「K1」）。
- **Level C 待验收**（第二阶段 + K1，未真机）：① dev 工具在 MuMu 设置页跑
  `dev_tools/test_touch_swipe_mumu.py` 的 default / left / right / straight / 120px / 440px，
  看 PNG 的 B（dt 是否更平滑）/ C（速度中段无尖峰、尾部平滑下降）；② K1 在 KekkaiUtilize
  真实寄养流程里：是否确实走 minitouch trajectory（日志 `KekkaiUtilize trajectory swipe`）、
  没回落 `swipe_adb`、416px trajectory 正常滚动一屏、无 fling、`find_everyone`·OCR·`I_U_EMPTY_CARD`
  ·final fallback 均不受影响。据结果再定 `tail_slow_gain` / `tail_density_gain` /
  `dt_smooth_alpha` 或整体放慢。**K2 / K3 / K4-1 / K4-2 均已于 2026-09-07 实施 Level A/B**（见
  §4.41「K2」/「K3」、§4.47）；仅 `new-region-only optimization` ⏸ 未实现（optional 性能优化）。

### 4.43 RuleOcr 浮点 OCR bbox → 整数点击 ROI 兼容修复

2026-09-04。Codex 真机（`oas2`）从「结界」页导航到「式神育成」页时 `TypeError: ROI必须由整数组成：(595.0, 293.0, 34.0, 101.0)`。调用链：KekkaiUtilize 页面导航 → OCR 命中「式神育成」→ `BaseTask.ocr_appear_click()` → `RuleOcr.coord()`（FULL 模式取 `self.area`）→ `ClickSampler.sample(area)` → `LEGACY_UNIFORM` → `random_point_in_roi(area)` 在非整数 ROI 上抛 `TypeError`。

- **根因**：`Full.ocr_full()` 命中后用 OpenCV 检测框（numpy 浮点多边形角点）+ `self.roi` 偏移覆写 `self.area`，产出浮点 `(x, y, w, h)`。自 D007（`b72eec29`）起底层 `random_point_in_roi()` 强制「ROI 必须全整数」契约，`RuleOcr.coord()` 也在同一提交改成调它——**latent 断裂从 D007 就在**，只是 D007 之前 `coord()` 用 `np.random.randint`（静默截断浮点、不报错但会缩框），一直没在真机上跑到这条 FULL 模式 OCR 点击路径。T7-1（§4.24）把 `coord()` 的 `random_point_in_roi(area)` 换成 `ClickSampler.sample(area)`，`LEGACY_UNIFORM` 逐字转调同一个 `random_point_in_roi`，**严格度没变**——只是这次被真机跑到了。
- **修复位置（`RuleOcr` 专属边界）**：`module/atom/ocr.py` 新增模块级 `_normalize_ocr_click_area(area)`，`coord()` 里 `ClickSampler.sample(_normalize_ocr_click_area(area))`。**没有**改 `random_point_in_roi`（仍拒绝浮点）、**没有**让 `ClickSampler.sample` 静默强转所有浮点 ROI、**没有**动点击分布算法（`ClickSampler` 策略 / HABIT / LEGACY_UNIFORM / preferred_center / core·medium·tail / Safe ROI / fallback / `SystemRandom` / BehaviorTrace schema / `Control.click` / `BaseTask.click` / `RuleClick` / `RuleImage` 全未碰）。
- **规范化规则**：格式 `(x, y, width, height)` → `x1=floor(x)`、`y1=floor(y)`、`x2=ceil(x+width)`、`y2=ceil(y+height)` → 回到 `(x1, y1, x2-x1, y2-y1)`。左 / 上 `floor`、右 / 下 `ceil` 保证整数框**完整包住原浮点框、绝不缩小可点区域**（禁用 `tuple(int(v) for v in area)` 那种截断）。贴屏幕右下边缘时 `x2`/`y2` 裁到 1280 / 720（避免 `randrange` 半开上界越出屏幕 1px），兜底 `max(1, ...)` 保证宽 / 高 ≥ 1。已是整数的 ROI floor/ceil 是恒等变换，语义不变。
- **影响范围（零 per-task 改动）**：全仓动态 OCR 文本点击都经 `RuleOcr.coord()` 这一个点——`BaseTask.ocr_appear_click`（24 处调用，横跨 GameUi 导航 / Buy / Login / SwitchSoul / Delegation / Exploration / SoulsTidy / WantedQuests / WeeklyPurchase / KekkaiUtilize 等）、`GameUi/navigator.py` 的 OCR 导航、`module/atom/list.py` 的 OCR 列表点击、`Chess` 刷新 OCR。只有 FULL 模式用 `self.area`（浮点来源）；SINGLE / DIGIT / … 用静态 `self.roi`，本就是整数，规范化对它们是 no-op。`Quantity.ocr_quantity` 也写浮点 `self.area`，但 `coord()` 非 FULL 分支取 `self.roi`、不碰它。
- **测试**：新增 `tests/test_rule_ocr_float_roi.py`（18 用例）——真机值 `(595.0,…)` 无 TypeError、真分数框几何包含、已整数框语义不变、亚像素小框仍是有效非零区、贴边裁剪、numpy 浮点入参回纯 Python int、400 个随机分数框的包含性属性、mock `ClickSampler.sample` 确认 `RuleOcr` 在调采样器**之前**就已整数化、`Full.ocr_full` 写浮点 `self.area` → `coord()` → 真实 `ClickSampler` 端到端、`RuleClick`/`RuleImage.coord` 源码不含规范化函数。回归 `904 → 922`。
- **Level C 待验收**：真机 `oas2` 重启 → 结界 → OCR「式神育成」→ 点击进页；此前这条导航直接崩、K1（§4.41 / §4.42）都到不了，修复后 K1 的下午 Level C 才能真正开始。`behavior_trace_enable` 现已开（§4.17 前置），确认 `log/behavior/oas2_<日期>.jsonl` 落点坐标 + OASX「统计 → 点击分布」出真实散布。

### 4.44 T7-5 —— 全局 Preferred Hotspot 点击策略（生产默认策略变更，Stage 1）

> 历史落地记录。2026-09-08 的当前热点解析规则见 §4.50 / D019；本节里的
> `CENTER_FALLBACK=(0.5,0.5)` 已被 `RULE_FALLBACK=(0.58,0.59)` + preferred 尺寸适配 Supersede。

2026-09-04。把「普通生产 Point 点击的**默认** = 整 ROI `LEGACY_UNIFORM`」改成「默认 = 该
target 的 preferred 热点 + 现有 core/medium/tail 偏移模型 + Safe ROI」（`docs/DECISIONS.md`
D014 的 T7-5 段：两条旧约束 `Superseded`）。**Stage 1 只改公共 Rule 层默认语义**（§34 分批），
GeneralBattle V3 区内采样 / `device.click` 旁路迁移 / `normal_button` 重标定是 Stage 2（Level C 后）。

- **新链路**：`rule.coord()` → `ClickSampler.sample_target(roi, rule.name)` →
  `resolve_target_preference(name)`（`module/click_preference.py` 的静态 registry
  `TARGET_PREFERENCES`，按 `rule.name` 索引 = BehaviorTrace `target` 同名）→
  `resolve_profile(profile_name)` → 把 preferred 写进 profile → `adapt_point_profile`
  （T7-2/T7-4 连续尺寸适配）→ `ClickSampler.sample(strategy=HABIT, profile=effective)` →
  `(x, y)`。**一次点击一次空间采样**，后端不再偏移。
- **provenance 四级**（`Provenance` enum）：`EMPIRICAL` / `SEMANTIC_TRANSFER` /
  `PROVISIONAL` / `CENTER_FALLBACK`。没有 empirical 热点 → `CENTER_FALLBACK` =
  `(0.5, 0.5)` + 新 `default_point` profile（数值同 `default`，不写个人热点）——**不退回
  Uniform**：Tiny 目标仍有中心附近小幅正态随机（tail 按 T7-4 归零），只有 Safe ROI 收成
  1 个整数像素时才每次同坐标。
- **registry 现状**：唯一登记项 `area_1`（`RyouToppa.C_AREA_1`，`EMPIRICAL`，
  `(0.58, 0.59)` + `wide_card`，来源 `manual_click yys1_2026-09-01` cluster_A）。short_side
  116 ≥ 96 → `size_factor = 1` → effective 逐字段等于 `wide_card` base → **C_AREA_1 落点
  分布不变**。其余 ~2683 静态 target + 所有动态 / 无字面量 target = `CENTER_FALLBACK`。
  `normal_button` / `I_FIRE` 仍 `PROVISIONAL` 候选、**零 registry 引用**（缺 runtime
  ROI-relative 数据，Stage 2 用 `runtime_roi_probe` + manual click 标定，不硬造）。
- **改动文件**：`module/click_preference.py`（新）、`module/click_profile.py`（+`default_point`）、
  `module/click_sampler.py`（+`sample_target`）、`module/atom/{click,image,gif,ocr}.py`
  （`coord()` / `coord_more()` → `sample_target`；`ocr.py` 保留 `_normalize_ocr_click_area`）。
  **未改**：`ClickSampler` 采样算法 / HABIT / `adapt_point_profile` / `DEFAULT_PROFILES`
  其它条目 / `random_point_in_roi` / `Control` / 后端 / `BehaviorTrace` schema /
  `BaseTask.click` / `random_click()` 函数本身 / GeneralBattle `_sample_settlement_click`
  （V3 region policy + 区内 `LEGACY_UNIFORM` 一字不变）/ `RyouToppa._click_toppa_area`。
- **Region**：经 `.coord()` 的大安全区（`random_click()` 的 `RuleClick` 等，28 项
  `large_safe_area`）也走 `sample_target` → `CENTER_FALLBACK`（区内偏中心，仍在区内，
  `ltrb=(F,F,T,F)` RIGHT-only 基线不变）。GeneralBattle V3 三个 SAVE 区不经 `.coord()`，不受影响。
- **测试**：新增 `tests/test_t7_5_preferred_hotspot.py`（22 用例：registry 结构 / `default_point` /
  默认非 Uniform 的统计断言（中央 25% 面积聚 55% 样本）/ Tiny 仍随机且散布小 / 尺寸连续 /
  `wide_card` empirical 保留 / 一次采样 / RuleOcr 浮点+preferred）。改写 10 个锁旧 D014 契约的
  用例（`test_click_sampler` 6、`test_ryoutoppa_c_area_1_point_opt_in` 3、
  `test_general_battle_settlement` 1）。回归 `922 → 944`。完整 inventory：
  `docs/T7_TARGET_PREFERENCE_MAP.md`。
- **Level C 待验收（Stage 1，分批抽样，§35）**：Tiny / Small / Normal / Large·card /
  Dynamic RuleImage / Dynamic RuleOcr / Large Region / GeneralBattle V3 各选真实消费者，看
  BehaviorTrace + OASX 散点：热点对不对、越不越 Safe ROI、是否重复固定像素、spread 与尺寸是否匹配。

### 4.45 T7-5 Stage 2 —— 剩余点击入口收口（Region 采样 + 私有 random 迁移 + Secret + 全项目 inventory）

> 历史落地记录。2026-09-08 起 Region 仍不调用 `adapt_point_profile`，但会单独调用
> `adapt_preferred_by_size`；本节的「Region 不做 short_side 适配」仅指旧实现，当前规则见 §4.50 / D019。

2026-09-06 落地 + 2026-09-07 重新校对 + 收口。把仍绕过 Stage 1 默认路径的生产点击逐类收口。

**状态：IMPLEMENTED —— 全项目「具有可证明安全 ROI」的生产点击入口架构迁移完成。** 按已明确的
Stage 2 完成标准「所有具有*可证明安全 ROI* 的生产点击入口完成统一空间模型迁移」（≠「所有
`device.click` 都重写」；exact coordinate 无安全 ROI 时允许合法保留 + 进 inventory；empirical
calibration ≠ 迁移）：
- 生产 bare `ClickSampler.sample()`（`LEGACY_UNIFORM`）消费者 = **0**；whole-ROI Uniform
  production Point / Region = **0**；double-sampling consumer = **0**。
- 有安全 ROI 的 Point / Region 全部迁移：`GeneralInvite._random_point_in_area` → `sample_target`；
  `GeneralBattle._sample_settlement_click` → `sample_region`；**`Secret.find_battle` 关卡卡片
  `click_rule.center` ×2 → `for click_index in 1..2: click_rule.coord()`（两次独立 `sample_target`
  采样；`click_roi` 几何 / 右侧状态文字避让 / 循环次数 / 间隔 / `control_name` 一字未改）**。
- `RuleLongClick` 经 `RuleClick.coord` 继承已在模型上。
- 重新核对全部 `.center` / `.front_center()` / 就地 `RuleClick(...)` / `device.click(` 消费点：
  `PENDING_MIGRATION`（有可证明安全 ROI 但未迁移）= **0**。
- 回归 `953 → 977`。

**两个独立持续任务（不是 Stage 2 blocker，不阻塞架构结论）**：
- **A. Empirical Hotspot Calibration**：`I_FIRE` / `normal_button`（无 `runtime_roi_probe` 输出、
  `I_FIRE` 3 个不同 asset）、GeneralBattle 三个 Region、其它 target 的 `CENTER_FALLBACK → EMPIRICAL`
  升级 —— 属 Level C calibration，**不等于代码 / 架构迁移**；`CENTER_FALLBACK` 已进统一 Preferred
  模型即视为「空间模型已统一」，不伪造 empirical 值。
- **B. Exact Coordinate ROI Discovery**：`docs/T7_TARGET_PREFERENCE_MAP.md` §3.4 的 23 处（点运行时
  检测中心 / 框外偏移点 / 硬编码 / 识别失败兜底猜测点 / slave 设备）—— 无静态可证安全 ROI，只有
  Level C / 新证据确认后才迁；其中个别「有运行时 bbox 但点角点 / 偏移」的（`Dokan:376`、
  `green_mark_name`、`QuickLoadout`）需真机确认语义。

- **`ClickSampler.sample_region(roi, target_name)`（新）**：Region Target 采样入口。`resolve_target_preference`
  → provenance == CENTER_FALLBACK 时用 `REGION_FALLBACK_PROFILE="default_region"`（不是 `default_point`）
  → 写 preferred → `sample(strategy=HABIT)`。**不经 `adapt_point_profile`**（24/96 short_side 适配
  是给 Point 的，会把大区 / 细长条安全区的 σ 误缩）。`default_region` profile：preferred (0.5,0.5)、
  core σ 0.17 / medium σ 0.30 / core·medium·tail 0.62·0.30·0.08 / margin 0.05 —— 比 `default_point`
  宽、仍中心集中（**非整区均匀**），provisional 保守起点，不是复活 Settlement Contract v2。
- **`click_preference.py`**：新增 `REGION_FALLBACK_PROFILE` + 3 条 Region 显式条目
  `random_default` / `random_save_right` / `random_save_bottom` → `CENTER_FALLBACK=(0.5,0.5)` +
  `default_region`（有独立 profile 需求才显式登记；将来 Level C 有数据就地升 EMPIRICAL）。
- **GeneralBattle Settlement V3（`_sample_settlement_click`）**：`ClickSampler.sample(rule.roi_front)`
  → `ClickSampler.sample_region(rule.roi_front, rule.name)`。**region 选择**（`_select_reward_region`
  marker → DEFAULT / 80% SAVE_RIGHT·20% SAVE_BOTTOM）、Generic Result 两次点击、`positive guard`
  `I_WIN`·`I_DE_WIN`·`I_FALSE`、state machine **一字未改**；`_advance_generic_result` 两次点击仍
  两次独立 `sample_region` 采样。
- **`GeneralInvite._random_point_in_area`（任务私有整框 `random_point_in_roi`）→ `ClickSampler.sample_target(select_area, rule.name)`**：`select_area` = `_find_exact_friend_area` 返回的好友名 OCR bbox
  （真实安全点击 ROI）。删私有 staticmethod + `random_point_in_roi` import。
- **`RuleLongClick`**：确认**无 `coord` override**，经 `RuleClick.coord` 继承已在 Stage 1
  `sample_target` 模型上（长按时长属时间模型、与空间模型分离）。测试锁。
- **生产 `LEGACY_UNIFORM` 消费者 = 0**：Stage 1 后 `Rule*.coord()` 全走 `sample_target`；Stage 2
  后 GeneralBattle 结算走 `sample_region`。`grep "ClickSampler.sample(" tasks/` = 0。`LEGACY_UNIFORM`
  策略 / `sample()` 方法保留（兼容 / 测试 / `HABIT` rejection fallback）。更正 `RyouToppa` /
  `general_battle.py` 两处「= LEGACY_UNIFORM」的过期注释。
- **direct `device.click` inventory（44 处）+ 全部 `.center` / `.front_center()` / 就地 `RuleClick`
  消费点**：`ALREADY_SAMPLED` 18（坐标上游已采样，含 Chess/SwitchAccount/KekkaiActivation 就地
  `RuleClick` 经 `self.click()` → `.coord()`）/ **`PREFERRED_POINT` 迁移 2**（`GeneralInvite` friend-name
  + `Secret` 关卡卡片）/ `PREFERRED_REGION` 迁移 1 / **`PENDING_MIGRATION` = 0** / `EXACT_COORDINATE_BLOCKED`
  23（无静态可证安全 ROI → 后续任务 B）/ `NON_CLICK`（Chess `_rule_center(RuleClick(HAND_AREA))` 是
  `Press_and_Drag` 端点、不是点击；`AreaBoss`/`Exploration`/`RealmRaid`/`SixRealms` 的 `front_center()`
  是 swipe 起点 / 几何判定 / x 位置分类，非点击）。**double-sampling consumer = 0。** 完整表见
  `docs/T7_TARGET_PREFERENCE_MAP.md`。
- **`normal_button` / `I_FIRE`**：无 `runtime_roi_probe` 输出、`I_FIRE` 3 个不同 asset → 无可靠
  runtime ROI-relative 数据。空间模型已统一（`sample_target` → CENTER_FALLBACK），**个人 hotspot
  empirical calibration 属后续任务 A（Level C），不算 Stage 2 迁移未完成，不伪造 empirical 值**。
- **测试**：新增 `tests/test_t7_5_stage2.py`（24 用例：`default_region` profile / `sample_region`
  中心偏置·非均匀·非固定·Safe ROI·不做 short_side 适配·细长条不缩 σ / `RuleLongClick` 继承 +
  端到端 / GeneralInvite 迁移 + 无 double / double-sampling 审计 / **`SecretLayerCardMigrationTest`
  4 用例**：源码契约 scoped 到 `find_battle`、构造 RuleClick 路由 `sample_target`、驱动真实
  `find_battle` 验 `coord()` ×2 + `device.click` ×2 + `call_args_list` 逐一对应两次采样、ROI 几何
  常量不变）。改写 `test_general_battle_settlement` 的 `SamplingTest` 3 + `RegressionBoundaryTest` 1
  用例（`sample` → `sample_region`）。改 `test_t7_5_preferred_hotspot` registry 断言。回归 `953 → 977`。
- **Level C（后续任务 A/B，不阻塞 Stage 2 结论，不是 blocker）**：
  - **A. Empirical Hotspot Calibration**：GeneralBattle 三个 SAVE 区真实散点（中心偏置、不越区、
    非固定像素、spread 合理）→ 可就地把 registry 条目升 EMPIRICAL；`normal_button` / `I_FIRE` 的
    `runtime_roi_probe` + manual click 标定 → 升 EMPIRICAL。不伪造 empirical 值。
  - **B. Exact Coordinate ROI Discovery**：`docs/T7_TARGET_PREFERENCE_MAP.md` §3.4 的 23 处 —— 只有
    Level C / 新证据确认存在安全 ROI 且改分布不打断业务后才迁；个别有运行时 bbox 的（`Dokan:376`、
    `green_mark_name`、`QuickLoadout`）优先真机评估。

### 4.46 BehaviorTrace Swipe Trajectory Backend（可观测性：swipe 轨迹后台记录 + 统计查询）

2026-09-07。给已有 BehaviorTrace / 点击统计后端**加 additive extension**：一次完整 swipe 轨迹的
后台记录与 `/stats` 查询。**只做 Backend，本轮不动 OASX 前端**（`d:\oas_xy\OASX` 零改动）；
schema / 过滤契约稳定后前端单独做。长期契约见 `docs/DECISIONS.md` **D004 补记** + **D011 补记**。

- **事件模型不变**：仍只有 `TASK` / `ACTION`（D004）。**一次 swipe = 一个 ACTION**，轨迹点整体
  嵌进 `extra.trajectory`（`[[x, y, dt_ms], ...]`，≤ `TouchSwipeModel.max_points`≈80）。**没有**
  `MOVE` / `SWIPE_POINT` / `FRAME` 事件级别；FrameWait 轮询也不写 ACTION。
- **记录点 = `Control` 层**（`module/device/control.py`）：
  - `Control.swipe_trajectory`：`extra = {start_x, start_y, end_x, end_y, point_count, trajectory}`。
    `trajectory` 直接来自传给该方法的这一份点列（executor 真实 commanded 输入）——**不按 start/end
    重新 `generate`、不还原曲线**。模块级 `_swipe_trajectory_extra(trajectory)` 组装（`int(round())`
    规整）。`dt_ms` 原样保留、语义仍是 D018（不重解释、不新增 `duration_ms`）。
  - `Control.swipe`（legacy 端点滑动）：`extra` 只带 `start_x/start_y/end_x/end_y` + `point_count=2`，
    **不带 `trajectory` 键**（无完整轨迹就不伪造）。`swipe_adb` 直连路径（KekkaiActivation /
    KekkaiUtilize 怠惰 / 非 minitouch 回退）仍绕过 `Control.swipe`、v1 不覆盖（已知缺口）。
  - 执行成功后记录（`result='ok'`），executor 抛异常仍不写 ACTION（无 swipe 专用 error schema）。
- **关闭态自然规避**：新增 `BehaviorTrace.is_recording()`（`enabled and not _broken`，语义等价
  `record()` 首行短路）；`Control.swipe_trajectory` 仅在其为真时组装几十个点的 `extra`。读访问器、
  不改 `record()` 契约。
- **Stats reader（`module/server/behavior_stats.py`）additive 扩展**：同一个
  `read_behavior_clicks(config, date, *, task=None, interaction_type="all", target=None)`、同一个
  `GET /stats/{script_name}/behavior/clicks` 端点（**不另造 `/swipe-stats`**）。
  - 新增 `swipes[]`：`{task, action:"swipe", target, ts, start:[x,y]|null, end:[x,y]|null,
    point_count, trajectory:[[x,y,dt],...], elapsed_ms?}`。
  - **四层等值 AND 过滤**：`date AND task AND interaction_type AND target`（缺省=不限）。
    `interaction_type ∈ {all, click, swipe}`（大小写不敏感；`all`=点击+滑动，`click`=`click`/`long_click`，
    `swipe`=`action='swipe'`，不含 drag；非法 → `BehaviorStatsError(400)` / router 422）。
    `target` 对 click / swipe **同一个参数、同一语义**（等值匹配 `target` 字段）。
  - **计数**：一条 swipe 无论多少点，`summary.swipe_count` 只 +1。旧 `summary.total`（=click 点数）/
    `click_count` / `long_click_count` / `task_count` / `skipped_lines` 语义**不变**。新增
    `swipe_count` / `filtered_count`（当前过滤命中的 ACTION 数）/ `malformed_trajectories`。
  - **下拉 metadata**：`available_tasks`（排除 `task` 维）/ `available_targets`（排除 `target` 维），
    各自在「另外两维过滤」下 distinct、首见序，供前端下拉动态刷新且不塌缩成自身。
  - **兼容 / 容错**：响应旧键（`config`/`date`/`screen`/`summary` 旧计数/`tasks`/`points`）名称·类型·
    语义全保留（旧 OASX 忽略新键即可）。旧 JSONL（click-only / swipe 无 `trajectory` / 坏行）照读；
    **单条坏 `trajectory` 只降级该条**（salvage 可解析点或置 `[]` + `malformed_trajectories` +1 +
    惰性 warning），**绝不 500**。
  - **坐标系**：`trajectory`/`start`/`end` 均原始 1280×720 屏幕坐标，后端零变换（前端复用现有 click
    坐标变换）。**不做**轨迹抽稀 / DP / 贝塞尔压缩。
  - **响应新增顶层键**：`filter`（回显 `task`/`interaction_type`/`target`）、`swipes`、
    `available_tasks`、`available_targets`。
- **BehaviorTrace 只记 commanded input，不记 actual scroll**：本轮（BehaviorTrace Swipe Backend）
  未接 `actual_scroll_dy` / `scroll_gain` / dynamic row_pitch。K4-1（`actual_scroll_dy`）+ K4-2
  （projection dedup）已于 2026-09-07 在 **KekkaiUtilize 业务层**实施（§4.47），不在 BehaviorTrace
  这一层；`new-region-only optimization` ⏸ 仍未实现。
- **K1/K2/K3 一字未改**：`tasks/KekkaiUtilize/script_task.py` 零改动；K1 的
  `control_name='KEKKAI_UTILIZE_SWIPE'` 天然被 trace 到（`task=KekkaiUtilize` / `action=swipe` /
  `target=KEKKAI_UTILIZE_SWIPE` + 完整 trajectory）。
- **改动文件**：`module/behavior_trace.py`（`is_recording`）、`module/device/control.py`
  （`_swipe_trajectory_extra` + `swipe` / `swipe_trajectory` 的 `extra`）、
  `module/server/behavior_stats.py`（reader 扩 swipe + 四层过滤 + metadata）、
  `module/server/stats_router.py`（3 个 query 参 + `BehaviorSwipeEntry` / `BehaviorClickFilter`
  模型 + summary 新字段）、`tests/test_behavior_trace.py`（+1 → 15）、`tests/test_control_swipe_trajectory.py`
  （+4 → 13）、`tests/test_behavior_click_stats.py`（`test_response_shape` 改 + 新增 `ReadBehaviorSwipesTest`
  7 + `BehaviorStatsFilterTest` 14 → 45）。回归 `999 → 1025`。
- **前端下一轮消费契约**：见 §7 下方「BehaviorTrace Swipe schema（前端待接）」。

### 4.47 KekkaiUtilize K4 —— Selected Anchor 实际滚动位移 + 一帧对一帧投影去重

2026-09-07。K4 从冻结**解冻并实施 Level A/B**（合成图 / mock 集成 / 业务契约测试全绿），Level C
pending（当前好友结界卡样本不足，不伪造真机通过）。长期契约见 `docs/DECISIONS.md` **D017 K4 补记**。

**K4 阶段定义（统一口径）**：
- **K4-1** Selected Anchor → `actual_scroll_dy`（`I_IS_SELECTED` 动态识别 selected glow → before/after
  center_y → 实际滚动像素）：✅ **Level A/B implemented**，Level C pending。
- **K4-2** Frame-to-Frame Projection Dedup（previous detections 按 `actual_scroll_dy` 投影 → 与 current
  detections 做「同 candidate type + bbox overlap/IoU」one-to-one matching → duplicates + `new_detections`
  → 仅 `new_detections` 进当前候选处理流程）：✅ **Level A/B implemented**，Level C pending。
- **K4 overall Level C**：⏳ **PENDING**。
- **`new-region-only optimization`**（按 `actual_scroll_dy` 直接推导新进入的视觉区域、只在那块区域跑
  template matching / `find_everyone`——性能优化，当前**无必要**）：⏸ **NOT IMPLEMENTED / OPTIONAL**。
  当前 K4-2 是**业务层去重**（跑完整 `find_everyone` 后过滤 `new_detections`），不是视觉区域裁剪。

- **锚点资产**：用户在 Web 标注器新增 `I_IS_SELECTED`（`tasks/KekkaiUtilize/assets.py:150`，
  `utilize_is_selected.png` 21×59 = 好友卡列表右缘的选中态发光紫/白竖线，几乎无动态业务内容；
  `roi_back = (602,168,30,442)` 纵向覆盖整个可见滚动高度的**动态搜索条**；threshold 0.8）。
  静态审查（上一轮）确认生产匹配链 `_template_match_image` / `_match_all_any_template` 在 `roi_back`
  内 `cv2.matchTemplate` 全量命中 + NMS，返回 `(score, x, y, w, h)` **绝对坐标**——K4 需要的能力已具备。
- **实际滚动位移**：`actual_scroll_dy = anchor_before.center_y − anchor_after.center_y`
  （`center_y = y + h/2`，before/after 统一口径）。before = 上一屏 swipe **前**明确重截一帧测；
  after = 当前稳定屏（K3 判 changed&stable 后）测。**禁止**用 commanded 位移
  （`SWIPE_DISTANCE_RANGE`/`SWIPE_LATERAL_OFFSET_RANGE`）当 actual dy——Level C 已确认惯性放大。
  `KEKKAI_ROW_PITCH_PX=106` 只用于日志「约几格」/ sanity，不参与核心计算、不把 dy 四舍五入成整格
  （保留 sub-row 连续位移）。
- **K4-2 一帧对一帧去重**：只保留「上一稳定屏」的 `find_everyone` 结果 + 它的 anchor_before，与
  「当前稳定屏」比对一次；投影 `y − dy`；**同模板类型（`image.name`）且 bbox 真实几何交集（IoU > 0）**
  才配对，竞争按 max IoU 贪心一对一；投影**中心**出 `K4_LIST_VISIBLE_Y=(156,606)` → 该上一屏候选已
  滚出屏、忽略。匹配上的当前候选 = 上一屏已处理的 duplicate、跳过；剩下的 `new_detections` 才进
  D017 业务处理（点开 → `check_card_num` → threshold）。**无持久历史 / 全局 candidate database /
  好友身份**。类型不一致即使重叠也**绝不**去重、**不重新 OCR**。**不新增 ±px magic tolerance**。
  （出屏判定用 projected **center** 而非「bbox 完全离开可见 ROI」——后者更严格；center-based 最多倾向
  **少去重 → 重复处理旧卡**，不会漏新卡，Level C 未证明这里有真实问题前不改，见观察项。）
- **测量不可靠 → 完整扫描**：`before`/`after` 任一 `available=False`（首屏没点过卡 / 本屏无选中 /
  glow 被列表边界裁切）、NMS 后 >1 候选、`dy<=0`、`dy>=roi_back 高度` —— 全部退回当前屏
  `find_everyone` 结果的完整处理。**宁可重复读卡，不能漏新六星卡。**
- **契约不变**：`measurement unavailable ≠ ABORT ≠ BOTTOM ≠ PASS_MISS`；**K3 失败仍 ABORT**（且此时
  不进 K4 的 after anchor / dedup——`_perform_search_swipe()` 返回 True 才进）；**BOTTOM 仍只认
  `I_U_EMPTY_CARD`**（没有 new candidate / dy 很小 / anchor 不见 / 全 duplicate 都不是到底）；
  `clicked_any` / `FINAL_USE_LAST` / `utilize_found_eligible_card` 语义不变（K4 跳过 dup 不清零单调
  的 `clicked_any`）。K1 / K2 / K3 / `_perform_search_swipe` 一行不改；`select_realm_on_1~4`
  死资产不删（资产清理另开）。**未实现的是 `new-region-only optimization`**（按 `actual_scroll_dy`
  裁新进入的视觉区域、只在那块跑识别）——⏸ optional 性能优化，本轮不做，也无必要。
- **组件**：两个 task-local 纯组件——`tasks/KekkaiUtilize/selected_anchor.py`
  （`detect_selected_anchor(frame, rule, *, threshold, nms_threshold, frame_id) -> SelectedAnchorResult
  {available, center_y, bbox, score, match_count}`；NMS 后恰 1 个 → available，0 / >1 → unavailable）
  + `tasks/KekkaiUtilize/frame_projection.py`（`actual_scroll_dy_px` / `project_bbox` / `bbox_iou` /
  `dedup_by_projection -> ProjectionDedupResult{new_detections, duplicate_indices, matched_pairs}`）。
  都不 swipe / 不调 FrameWait / 不改 PASS 状态。`K4_ENABLED` 类常量是 kill switch。
- **集成点**：`_run_search_pass` 循环里——loop 顶 `screenshot` 后测 anchor_after + 算 `dedup_dy`；
  `find_everyone` 后按 `dedup_dy` 过滤成 `scan_cards`；候选循环遍历 `scan_cards`（原为 `cards`）；
  loop 底 swipe 前存 `prev_detections = cards` + 重截一帧测 anchor_before。K3 的
  `if not self._perform_search_swipe(): return ABORT` 一字不动。
- **改动文件**：新增 `tasks/KekkaiUtilize/selected_anchor.py` / `tasks/KekkaiUtilize/frame_projection.py`
  / `tests/test_kekkai_k4_selected_anchor.py`（11）/ `tests/test_kekkai_k4_projection.py`（21）；
  改 `tasks/KekkaiUtilize/script_task.py`（2 import + K4 类常量 + `_run_search_pass` 集成）、
  `tests/test_kekkai_utilize_state.py`（`RunSearchPassTest.setUp` patch `detect_selected_anchor`
  为 unavailable、新增 `K4IntegrationTest` 8）。`test_kekkai_utilize_state` `86 → 94`，
  完整回归 `1027 → 1067`（+40）。
- **Level C pending 观察项**：① selected glow 连续帧命中稳定性；② before/after 实际 dy 是否符合真实
  画面；③ 投影 bbox 与同一卡 current bbox 是否 overlap；④ duplicate/new 判定是否符合肉眼；
  ⑤ 新卡是否出现 false dedup；⑥ measurement unavailable 是否正常 full_scan；⑦ 重叠 1~2 行是否减少
  重复点击；⑧ **center-based visible filtering（投影中心出界即忽略）是否只造成重复、不漏卡**；
  ⑨ `threshold=0.8` / multi-match 收敛（当前「>1 → unavailable」）是否需实测调整；发亮框呼吸动画对
  命中率的影响。

### 4.48 全仓 Swipe Consumer 迁移 —— 普通滑动 / 列表滚动统一走 TouchSwipeModel

2026-09-07。把全仓「普通页面滑动 / 列表滚动」的输入后端从 legacy 端点滑动（`Control.swipe` →
各后端 `insert_swipe` 直线）统一迁到 `TouchSwipeModel` 轨迹（minimum-jerk + 有界曲率 + 平滑
时间 + 尾段慢拖）。**只换「怎么滑」，不换「滑多远 / 滑完等什么 / 失败怎么办」。** 长期约定见
`docs/DECISIONS.md` D018 补记。

- **新公共 helper `BaseTask.swipe_trajectory(start, end, *, control_name='SWIPE', fallback=True)`**
  （`tasks/base_task.py`）：唯一职责 = 把 start→end 变成一次滑动。minitouch →
  `TouchSwipeModel().generate(start, end)` → `Control.swipe_trajectory`（一次 swipe = 一个
  BehaviorTrace ACTION，完整 commanded 轨迹进 `extra.trajectory`）；非 minitouch →
  `fallback=True` 回退 `Control.swipe`（端点滑动，保留 distance_check / 各后端 duration 语义），
  `fallback=False` 抛 `NotImplementedError`；位移 `< 10px`（`Control.swipe` 自身「太短当点击」阈值）
  一律走端点滑动、不进轨迹模型（避免 `< 2px` 触发 `TouchSwipeModel` 的 ValueError）。
  **绝不**在 helper 里 screenshot / FrameWait / sleep / retry / 加随机延迟——那些是业务层的事
  （与 KekkaiUtilize `_perform_search_swipe` 同分工，但 helper **不含 K3 FrameWait**）。
- **`BaseTask.swipe(RuleSwipe)` 改为走 helper**：`self.device.swipe(p1, p2, ...)` → `self.swipe_trajectory(
  (x1,y1), (x2,y2), control_name=swipe.name)`。起终点仍是 `swipe.coord()` 的随机采样，方向 / 距离 /
  `interval` timer / `control_name`（进而 `click_record` 计数，Exploration `arrive_end` /
  换式神 swipe 计数依赖它）全不变。**42 个 `self.swipe(S_*)` 生产 consumer 透明迁移**（AreaBoss /
  SwitchSoul / SwitchAccount / QuickLoadout / MemoryScrolls / WeeklyPurchase / WantedQuests /
  Secret / KittyShop / Hyakkiyakou / Summon / Dokan / CollectiveMissions / DailyTrifles(经
  `S_DT_GW_OPEN_SEARCH`) / Exploration base+script / KekkaiUtilize 的 `S_GUILD_LOTTERY`·`S_U_END` /
  GeneralBattle `random_click_swipt` 的 `S_BATTLE_RANDOM_LEFT/RIGHT`）。
- **`GeneralBuff.exp_50` / `exp_100`** 的直连 `self.device.swipe(p2=(530,240), p1=(580,320))` →
  `self.swipe_trajectory((580,320),(530,240), control_name='GENERAL_BUFF_LIST')`，之后的
  `time.sleep(1)` + `max_swipe` 边界不动。
- **GeneralBattle 保护边界**：`random_click_swipt` 经 `BaseTask.swipe` chokepoint 透明迁移（战斗中
  反检测随机滑动，非 Settlement V3 / reward / result click——那些是 `click`，不涉及 swipe）。
  未改任何 GeneralBattle 结算 / 奖励 / 点击逻辑。
- **本轮未迁（各有原因，见 `docs/ROADMAP.md`）**：`BaseTask.list_find` 翻页 swipe（与 pending 的
  T5-2 FrameState/sleep 迁移绑定，现在动会冲乱 `test_list_find` characterization 基线）；
  KekkaiActivation `check_card_num` 好友卡 `swipe_adb`（距离敏感、KekkaiUtilize 的姊妹，应像
  KekkaiUtilize 那样单独走 K1 式分阶段 + Level C，`test_kekkai_activation_state` 已有基线）；
  RyouToppa `flush_area_cache`（活跃 WIP，逐 attempt 手调参数 + 显式依赖 `duration=`（T3-1 契约）+
  retry/verify）；KekkaiUtilize `perform_swipe_action`（K-series 明确保留的怠惰 / 非 minitouch 回退）。
- **保留 legacy（drag / 摇杆 / 特殊手势，永不按普通 swipe 迁移）**：`Control.drag` + `drag_minitouch`
  等各后端 drag；`tasks/Chess/runtime/press_and_drag.py`（`Press_and_Drag` 落子拖拽）；
  `AbyssShadows.move_a_little`（寮里虚拟摇杆移动，`swipe_adb` + 有意 `duration=0.5`）。
- **测试**：新增 `tests/test_base_task_swipe_trajectory.py`（16）——minitouch → 轨迹 / 非 minitouch →
  端点回退 / `generate` 只调一次 / `control_name` 透传 / `< 10px` 回退 / `fallback=False` 抛 /
  `generate` 与 executor 异常都透传不吞 / helper 体内无 screenshot·sleep·retry / `BaseTask.swipe`
  委托 helper 且源码不再直连 `self.device.swipe(` / GeneralBuff 迁移源码断言。既有回归 `1067 → 1083`
  （+16，纯新增；无既有用例改动——task-state 测试的 config 是 MagicMock，`control_method != 'minitouch'`
  自然走端点回退，行为逐字不变）。
- **Level C pending**：除 KekkaiUtilize（K1~K4 已真机连测）外，所有迁移 consumer 的真机效果均
  **PENDING**——minitouch 下曲线轨迹是否被正确识别为滑动、滚动量与直线版差异是否可接受、连续
  滚动是否因单次轨迹耗时变化触发上层 timeout、横向 ≤16px 弓形是否经过危险可点击区域。

### 4.49 全仓 FrameWait + confirm_delay 消费者审查（`list_find` FrameWait 迁移）

2026-09-08。对整个 Backend 的时序层（固定 `sleep` / `wait_*` / `Timer` / `random_delay` /
`confirm_delay`）做一次完整审查，把真正符合 FrameWait（W1 结构性 settle）/ `confirm_delay`
（Point Action reaction timing）语义的生产 consumer 找出来并尽量迁移。**目标不是「删光 sleep」
或「点击都加延迟」**，而是 eligible → migrated / ineligible → retained with reason /
uncertain → Level C pending。

**等待语义分类（W1~W7，见 `docs/TESTING.md` §5「时序层长期规则」）**：
- **W1 结构性 settle**：动作后固定 sleep 只是等页面变化 / 停稳，然后**继续按当前页面视觉状态**
  识别 → FrameWait 第一优先候选。
- **W2 语义等待**：等某个明确业务标识出现 / 消失 → 继续用 `wait_until_appear` / `appear` 循环，
  FrameWait **不替代** semantic success marker。
- **W3 协议 / 设备等待**：minitouch dwell / `DEFAULT_DELAY` / adb·scrcpy backend sleep / OCR·
  图像服务启动 / 连接等待 → 稳定性层，**禁止迁移**。
- **W4 retry backoff**：失败 → sleep → retry 的 pacing。
- **W5 业务 cooldown / 实时要求**：游戏机制固定等待 / 战斗节流 / 服务端节流。
- **W6 behavioral delay**：fatigue / idle / `random_delay` / reaction delay → 不迁 FrameWait。
- **W7 unknown**：静态判不出目的 → 保留，报告 `reason = semantic unclear`，不猜。

**Inventory 数字（静态分类估计；精确事实见下）**：`tasks/` 内 `sleep(` 约 **290 处** +
`module/` 内约 **135 处**（后者几乎全是 W3 设备后端 / W5 server / W4 retry，全部 retained）。
`tasks/` 约：W1 结构性 settle ≈ 26（1 迁移 + ~25 Batch B）、W2 语义 / 短暂 pre-marker settle ≈ 120、
W3 ≈ 55（Chess 手势 / minitouch dwell / `sleep(duration)` / 紧循环）、W4 ≈ 40、W5 ≈ 14、
W6 ≈ `random_delay` 16 caller、W7 ≈ 30。**精确事实**：FrameWait 迁移 = **1**（`list_find`）；
`confirm_delay` 生产 opt-in = **0**（本轮不变）。

**FrameWait 本轮唯一迁移 = `BaseTask.list_find` 翻页 settle（Batch A）**：
- before：`swipe_pos → self.device.swipe(p1,p2) → sleep(random.uniform(0.8, 1.3))`（注释自带「待优化」）。
- after：`settle_baseline = self.device.image`（翻页前用于识别、未被污染的那一帧）→
  `self.device.swipe(...)` → `wait_for_changed_and_stable(settle_baseline, self.device.screenshot,
  roi=_list_roi_back_to_box(target.roi_back), changed_threshold / stable_threshold / stable_frames /
  timeout / poll_interval = 模块级 `_LIST_FIND_SETTLE_*` provisional 常量)`。
- **结果丢弃、不参与控制流**：settle 成功或 timeout 都一样回循环顶 `self.screenshot()` + 重新
  `image_appear` / `ocr_appear`，`max_swipe` 仍是唯一收敛边界，**不新增 BOTTOM / ABORT / 提前返回**。
  → 阈值取错最多多等 / 少等一会儿，不会漏找 / 误判（这是它能在 Level A/B 就迁的关键）。
- **ROI = `RuleList.roi_back`**（每个 list 自己的内容区，`(x,y,w,h)` → `(x1,y1,x2,y2)`），**无全局 ROI**。
- **参数 provisional，Level C 待标定**：`changed 0.02 / stable 0.01 / stable_frames 2 / timeout 1.5s /
  poll_interval 0.12`——不得当全项目通用参数；KekkaiUtilize K3 的 `SWIPE_WAIT_*` 是卡列表专用，未照搬。
- ~15 个下游 consumer（Orochi / FallenSun / EvoZone / EternitySea 的 `check_layer`、`GeneralRoom` /
  `WeeklyPurchase navbar` / `navigator` / `Dokan`）零调用点改动、行为不变（settle 更聪明而已）。
- 测试 `tests/test_list_find.py` `22 → 27`：settle 走 `wait_for_changed_and_stable`（patch）+ ROI =
  `RuleList.roi_back` 换算 + provider = `device.screenshot` + baseline = 翻页前帧 + timeout 结果不改
  收敛 / 返回（不 BOTTOM / ABORT）+ settle-wait 异常透传；`_list_roi_back_to_box` 换算单测。

**FrameWait Batch B（eligible，本轮不迁，Level C pending）**：SwitchSoul 组 / 队伍列表滚动、
QuickLoadout、WeeklyPurchase 商店列表（special / guild / scales / shrine / thousand_things）、
GeneralBuff buff 列表、WantedQuests 悬赏列表、SwitchAccount 账号 / 服务器列表。原因：每个都嵌在
自己带 marker + `interval` timer 的定制循环里、无专属 characterization、ROI 需逐页推导、阈值
Level C；盲迁有 FSM 破坏风险。列入 Level C 矩阵按语义代表性验收，不逐个真机。

**confirm_delay：本轮生产 opt-in 仍为 0**。`appear_then_click` 真实语义（`tasks/base_task.py`
复核）= 首次 `appear` → `sleep(random_delay(*confirm_delay))` → **重新 `screenshot`** → 二次
`appear`（目标没了则不点、返回 False）→ 在新帧上 `coord()` / `action.coord()` → click。即
「delay 后重新截图 / 二次确认 / 重定位」，不是「点旧 bbox」。全仓 **486 处 `appear_then_click` +
~264 处 `self.click`/`device.click` + ~26 处 `ocr_appear_click`/`wait_until_appear_then_click`**，
**无一传 `confirm_delay`**。与 2026-09-02 专项审查（`docs/Action点击前反应时序静态审查.md`）结论
一致：能力正确完整、但 D001「按调用点风险显式 opt-in、不全局启用」+ D008「不重新引入
`reaction_delay` / 全局自动等待」下**无新证据推翻**；且**没有实测 delay 区间**，`docs/TESTING.md`
§5 与本轮 §15 均禁止拍脑袋新建 `0.3~0.8` 之类全局区间。首个真实 opt-in 仍等 Level C，随
RealmRaid `fire()` R-R1 bounded 改造一起（`I_FIRE` 的 `confirm_delay` 用 manual click /
BehaviorTrace 数据标定）。

**没有错误叠加**（`docs/DECISIONS.md` D001 / D012）：FrameWait（视觉结构等待）≠ `confirm_delay`
（识别后到点击前的 reaction）≠ fatigue（macro idle / rest）≠ minitouch dwell（DOWN→UP 按压）≠
TouchSwipeModel 逐段 dt（轨迹运动学）。`list_find` settle 只替换一个 W1 sleep，未碰任何点击 /
fatigue / dwell；`confirm_delay` 未接入，不存在与 fatigue 同一 Action 叠加的问题。

### 4.50 T7 点击热点统一规则：人工热点优先 + 未采样目标按 ROI 尺寸计算热点

2026-09-08，正式建立 **HOTSPOT RESOLUTION POLICY**（`docs/DECISIONS.md` D019），替代
T7-5 Stage 1 / 2 的 `CENTER_FALLBACK=(0.5,0.5)` 语义：

- **来源优先级**：target 自己的 `EMPIRICAL` preference 优先；未人工采样 target 使用
  `RULE_FALLBACK`，统一规则锚点 `RULE_BASE_PREFERRED=(0.58,0.59)`。`area_1` / `wide_card`
  继续是 EMPIRICAL `(0.58,0.59)`；`random_default` / `random_save_right` /
  `random_save_bottom` 与未知 target 即使数值相同，也明确是 RULE_FALLBACK。未来 target 自己的
  EMPIRICAL registry 条目会自然覆盖 resolver 兜底，不混淆证据来源。
- **preferred-only 公共能力**：`module/click_profile.py` 新增
  `adapt_preferred_by_size(preferred_u, preferred_v, roi)`。`short_side=min(width,height)`；
  24/96 锚点；`t=clamp((short_side-24)/72,0,1)`；`s=t²(3-2t)`；最终
  `(u,v)=(0.5+(base_u-0.5)s, 0.5+(base_v-0.5)s)`。`<=24` 精确为中心，`>=96` 精确为完整
  anchor，中间连续释放。profile 里的中性 `(0.5,0.5)` 仍只是 shape 模板默认值。
- **Point 链路**：`sample_target → resolve_target_preference → 写入 base profile →
  adapt_point_profile → HABIT`。`adapt_point_profile` 内部改为复用 `adapt_preferred_by_size`；它原有的
  core/medium sigma 与 tail 尺寸收缩继续保留，仍由同一个 `point_size_factor` 驱动。
- **Region 链路**：`sample_region → resolve_target_preference → adapt_preferred_by_size →
  只替换 default_region.preferred → HABIT`。明确不调用 `adapt_point_profile`，所以 Region 的
  sigma / weights / margin / tail 不继承 Point shape 收缩；只共享热点尺寸适配。
- **GeneralBattle Settlement V3 业务不变**：region marker / 80-20 选择、Generic Result 两次推进、
  timer / positive guard / state machine 一字未改。当前 ROI：DEFAULT short side 230 →
  `(0.58,0.59)`；SAVE_RIGHT short side 87 → `(0.5765625,0.5861328125)`；SAVE_BOTTOM short side 69 →
  `(0.5546875,0.5615234375)`。
- **测试**：`tests/test_click_profile.py` 新增长短边 / 端点 / 中间尺寸真实公式 / 非法输入用例；
  `tests/test_t7_5_preferred_hotspot.py` 锁来源区分、未知 target RULE_FALLBACK 与 Point effective
  preferred；`tests/test_t7_5_stage2.py` 锁 Region 只适配 preferred、shape 不变、GeneralBattle
  三个 Region 的 effective hotspot。相关 216 项离线测试通过；完整基线见 §7。
- **未做 Level C**：本轮未启动 MuMu / 游戏 / OCR；实际点击热区体验与分布仍需后续真机抽样。

### 4.51 第一批业务 Reaction Timing / `confirm_delay` 迁移（生产行为变化，Level A/B）

2026-09-08。把 6 类常用业务流程审查（`docs/常用业务点击链与Reaction审查.md`，只读）里 Batch A #1–#23
的稳定 Point 点击，正式从「识别到立即点」改成经 `BaseTask.appear_then_click(..., confirm_delay=)`
的「识别 → reaction delay → fresh screenshot → 二次 `appear`（目标没了则不点、返回 False）→
重新 `coord()` → click」。**`appear_then_click` primitive 本体未改**（D001 / D008：不新增
`reaction_delay()` / `CLICK_REACTION_DELAY` / 全局默认点击等待 / `BaseTask` 全局默认 `confirm_delay`；
不传 `confirm_delay=` 时行为逐字不变）。

- **公共 reaction profile = `module/reaction_profile.py`**（新增，与 `click_profile.py` / `click_preference.py`
  同层）：只含具名 `(min, max)` 秒区间常量，无函数 / 无 `sleep` / 无 `random_delay` / 不依赖
  task·device·config；由业务 consumer 在调用点**显式**传给 `confirm_delay=`；**不在 asset /
  `RuleImage` 层设默认**。当前值（**全部 PROVISIONAL / engineering baseline，非 Level C 标定**）：
  `REACTION_FAST=(0.18,0.35)` / `REACTION_NORMAL=(0.45,0.85)` / `REACTION_NORMAL_HIGH=(0.60,1.00)` /
  `REACTION_CONFIRM=(0.55,1.20)` / `REACTION_NAVIGATION=(0.55,1.10)` / `REACTION_DELIBERATE=(0.90,1.60)`。
- **首批生产 confirm_delay consumer = 27 个调用点 / 5 个任务**（此前 = 0）：
  - **RealmRaid**（6）：`ensure_lock` 的 `I_LOCK`/`I_UNLOCK`/`I_LOCK_2`/`I_UNLOCK_2` = FAST；
    `check_refresh` 的 `I_FRESH` = NORMAL、`I_FRESH_ENSURE` = CONFIRM。
  - **Orochi**（5）：`check_lock`（`run_leader`/`run_alone`/`run_wild` 共 3 处，经新参数）= FAST；
    `I_FORM_TEAM`（`run_leader`/`run_wild` 共 2 处）= NORMAL。
  - **EvoZone**（4）：`check_lock`（`run_leader`/`run_alone` 共 2 处）= FAST；`evozone_enter` 的
    `appear_then_click(kirintype, ...)`（**只有一个点击点**，麒麟/材料类型选择）= DELIBERATE；
    `I_FORM_TEAM`（`run_leader`）= NORMAL。
  - **RyouToppa**（3）：`_ensure_team_lock_state` 的 `appear_then_click(source, interval=0)`（`action=None`
    形态）= FAST；`start_ryou_toppa` 管理路径的 `I_SELECT_RYOU_BUTTON`/`I_START_TOPPA_BUTTON` = FAST。
  - **Exploration**（9）：`switch_rotate` 的 `I_E_AUTO_ROTATE_ON` + `run_on_exp_settings` 的
    `I_E_AUTO_ROTATE_OFF` = FAST；`run_on_exp_exit` 的 `I_E_EXIT_CANCEL` = NAVIGATION、`I_E_EXIT_CONFIRM`
    = CONFIRM；`quit_exp_main` 的 `I_UI_BACK_YELLOW` = NAVIGATION；`open_expect_level` 的
    `I_UI_CONFIRM`/`I_UI_CONFIRM_SAMLL`（两个 while 循环各一对，共 4 处）= NORMAL。
- **按 profile**：FAST 14 / NORMAL 8 / CONFIRM 2 / NAVIGATION 2 / DELIBERATE 1 / **NORMAL_HIGH 0**（本轮
  Batch A 无高频稳定 Point Action，允许 0 消费者）。
- **`GeneralBattle.check_lock` 加 `confirm_delay: tuple | None = None` 参数**并透传给两分支的
  `appear_then_click`；**默认 `None` → 原行为**，非 batch 调用方（EternitySea / FallenSun / GoryouRealm /
  OtherWorldTwilight / Sougenbi）不传、逐字不变。
- **明确排除（本轮 0 新 reaction consumer）**：RealmRaid `fire()` / `I_FIRE` / `C_PARTITION_n` /
  `fire_again` 系列（属 R2 STATE_WAIT_FIRST，须先做 R-R1 正向战斗页确认 + bounded retry）；
  Orochi `I_OROCHI_FIRE` / `I_OROCHI_WILD_FIRE`、EvoZone `I_EVOZONE_FIRE`（同 R2）；所有 `check_layer` /
  `L_LAYER_LIST` OCR 层、Exploration `fire(button)` 动态怪物 target、`O_E_EXPLORATION_LEVEL_NUMBER`、
  宝箱 / `I_REWARD` polling、`I_UI_CANCEL` 队长弹窗、`pages.random_click()` Region；
  RyouToppa `I_FIRE`（已手搓 `random_delay(0.2,0.6)` + fresh frame + 二次 appear = 等价 confirm_delay，
  **不再叠**）、`C_AREA_1~8`（有 T7 采样 + 区域 `random_delay(1.0,3.0)` pacing）；
  GeneralBattle `I_PREPARE_HIGHLIGHT`（有 `prepare_click_timer`）、Settlement V3 三个 Region（有
  `settlement_click_timer` + 强制双击间隔，D016）、`I_DISABLE_7DAYS_DIFF_SOUL` / `I_CONFIRM_CLOSE_DIFF_SOUL` /
  `I_OVER_GHOST` / `I_GB_SKIN_CONFIRM` / `green_mark` / `C_RANDOM_CLICK`（瞬态 / 战斗中）。
  上一轮审查的 Batch A #24/#25（GeneralBattle 差异御魂弹窗）、#26（RyouToppa `I_GUILD_ORDERS_REWARDS`
  带 `action=`）**本轮不实施**。
- **Timing owner 无叠加**：`confirm_delay`（reaction）与 `FrameWait`（视觉结构）/ `FatigueManager`（macro idle，
  本轮未扩）/ minitouch dwell / `random_delay` 各自 owner 不同；RyouToppa 的两处 `random_delay`、
  GeneralBattle 的 `prepare_click_timer` / `settlement_click_timer` 均保持、未被 reaction 覆盖或叠加。
- **测试**：新增 `tests/test_reaction_timing_batch1.py`（34）——profile 常量值 + provisional 身份 +
  无逻辑；每个迁移调用点带正确 `confirm_delay=REACTION_*`（源码扫描）；`check_lock` 新参数默认 `None`
  透传（mock 行为断言）；全部排除项 / 瞬态 / 动态 / OCR / Settlement / `I_PREPARE_HIGHLIGHT` 无
  `confirm_delay`；asset 模块不 import `reaction_profile`。回归 `1092 → 1126`。
- **Level C pending**：二次 confirm 成功率、reaction 实际分布、是否明显增加任务耗时、delay 期间
  target 消失导致漏点、是否需要把某高频稳定 Action 从 NORMAL 调到 NORMAL_HIGH、provisional profile
  是否按任务微调。在拿到 Level C 证据前不擅自放大区间。

### 4.52 RyouToppa / RealmRaid FIRE Reaction 统一 + RealmRaid `fire()` 状态机收口（R-R1）

2026-09-08。承接 §4.51，正式处理两个 `I_FIRE` 场景（其余 `*_FIRE` 仍等下一轮）。生产行为变化，
Level A/B。长期契约见 `docs/DECISIONS.md` D001 补记（FIRE 分节）+ D015 补记。

- **新增公共 `REACTION_FIRE = (0.4, 0.8)`**（`module/reaction_profile.py`，纳入 `REACTION_PROFILES`
  dict，`REACTION_PROFILES_PROVISIONAL` 仍 True）：「已识别到稳定的 `I_FIRE` 后、真正执行 FIRE
  click 前的人为 reaction」。**PROVISIONAL / engineering baseline**，非 Level C 标定。§4.51 的
  6 组 profile 数值不动。
- **RyouToppa `attack_area` —— 只统一 delay profile，成熟状态机不动**：`fire_delay =
  random_delay(0.2, 0.6)` → `random_delay(*REACTION_FIRE)`（仍在 `for attempt` 循环体内 → 每次
  attempt 独立采样）。保留：`RYOU_TOPPA_ACTION_RETRIES`、`_wait_for_attack_state()`（battle/fire/
  list/unknown）、`is_in_battle()`、reaction 后 `screenshot()` + 二次 `appear(I_FIRE)`（没了不点）、
  `AreaAttackResult`、区域进攻前 `random_delay(1.0, 3.0)` 业务 pacing（未删、未改）、fatigue safe
  node。**未加 `confirm_delay`**（已是等价手写链，不叠第二层）。
- **RealmRaid `fire()` —— R-R1 收口**（`tasks/RealmRaid/script_task.py`）：
  - **旧**：`wait_until_appear(I_RR_PERSON)`（无超时）→ `while True`：`if not appear(I_RR_PERSON):
    return True`（旧标识消失即成功）/ `appear_then_click(I_FIRE, interval=1)` / `click(C_PARTITION,
    interval=2)`。恒返回 True，尾部 `return False` 不可达。
  - **新**：`wait_until_appear(I_RR_PERSON, wait_time=RR_FIRE_TIMEOUT)` → `for attempt in
    range(1, RR_FIRE_MAX_TRIES + 1)` 且 `Timer(RR_FIRE_TIMEOUT)` 未到：
    ① `screenshot` → **`is_in_battle(False)`（正向战斗确认，复用 `GeneralBattle.is_in_battle`）→
    return True**；② `I_FIRE` 未就绪 → `click(C_PARTITION_{order}, interval=2)` 打开详情（原业务
    逻辑）；③ `I_FIRE` 就绪 → **每 attempt 独立 `random_delay(*REACTION_FIRE)` → `sleep` → fresh
    `screenshot` → 再次 `is_in_battle` → 二次 `appear(I_FIRE)`（reaction 期间消失则不点旧坐标、
    `continue`）→ `appear_then_click(I_FIRE, interval=0, threshold=0.8)`** → `_wait_fire_entered_battle()`；
    ④ attempt / timeout 用尽 → **`return False`（可达）**。
  - **常量（module 级，engineering baseline，非 Level C）**：`RR_FIRE_MAX_TRIES = 4`、
    `RR_FIRE_TIMEOUT = 10`（参考 Exploration `fire()` 的 `max_tries=4` + `Timer(10)`）、
    `RR_FIRE_POST_CLICK_TIMEOUT = 3`（参考 RyouToppa `RYOU_TOPPA_STATE_TIMEOUT=3`）。
  - **FIRE post-click 三态边界收口（2026-09-08，同轮追加）**：`_wait_fire_entered_battle()` 从
    「bool，`I_FIRE` 与 `I_RR_PERSON` 都不在即提前 `return False`」改为**返回 `str`，区分三态、不点
    任何坐标**：`'battle'`（`is_in_battle()` —— 唯一 positive success）/ `'retryable'`
    （`_is_realm_raid_retryable_state()` —— 明确仍在个人突破可操作页面）/ `'timeout'`（整个
    `RR_FIRE_POST_CLICK_TIMEOUT` 内一直是「旧 marker 消失、battle 未出现」的**过渡 / 未知帧**——
    **既不当 success 也不当 immediate failure**，timer 内持续等 battle / retryable）。新增纯只读
    helper **`_is_realm_raid_retryable_state()`** = `appear(I_RR_PERSON) or appear(I_FIRE) or
    appear(I_BACK_RED)`（不截图 / 不点击 / 不 sleep / 不改状态）。`fire()` 循环里 `I_FIRE` 未就绪时
    也走同一个 `_wait_fire_entered_battle()`：`'battle'` → return True；`'retryable'` → 才
    `click(C_PARTITION_{order}, interval=2)`（**partition 点击必须有明确 retryable-state 守卫，不再以
    `not appear(I_FIRE)` 为充分条件**）；`'timeout'`（transition / unknown）→ **不点任何坐标**，进入
    下一 attempt。过渡帧不再消耗「乱点 partition」，也不再被误判成 retry / failure。
  - **`I_RR_PERSON` 降级为辅助信号**：不再单独代表成功；只作为 `_is_realm_raid_retryable_state` 的
    输入之一。
  - **caller 兼容**：`run()` 的两处 `if not self.fire(index): continue`（原本就有、原本因 `fire()`
    恒 True 而不可达）现在真正生效——`fire(False)` → `continue` 回 `while 1` 顶重新 `check_ticket`
    + `find_one`，**不在非战斗页误交接 `run_general_battle`**。`run()` 本身未改。
- **明确未改**：`appear_then_click` primitive、`C_PARTITION_n` 坐标 / ROI / RuleClick / ClickSampler /
  T7 / order 逻辑、`fire_again()` / `I_FIRE_AGAIN` / `I_SHOW_AGAIN`、GeneralBattle（Settlement V3 /
  `prepare_click_timer` / `settlement_click_timer` / `_advance_generic_result`）、Orochi `I_OROCHI_FIRE` /
  `I_OROCHI_WILD_FIRE`、EvoZone `I_EVOZONE_FIRE`、Exploration `fire()`（参考实现）/ `open_expect_level`
  的 `swipe → sleep(1) → OCR`、Fatigue（RealmRaid 本轮不新增 fatigue consumer）。
- **测试**：新增 `tests/test_fire_reaction_fsm.py`（29）——`REACTION_FIRE` 值 / registry / provisional +
  §4.51 6 组不变；RyouToppa FIRE 统一 0.4~0.8（非 0.2~0.6）+ 每 attempt 独立采样 + reaction→fresh
  screenshot→recheck + 成熟状态机保留 + 区域 pacing 保留 + 无 confirm_delay；RealmRaid `fire()`
  正向战斗确认 return True（无多余点击）/ 旧 marker 消失但非战斗 ≠ success / reaction 期间 FIRE
  消失不点旧坐标 / 每 attempt 独立采样 / bounded `RR_FIRE_MAX_TRIES` → False / timeout → False /
  prologue 有界 `wait_time` / partition[order-1] `interval=2`；caller `run()` 两处 `if not
  self.fire(index): continue` + fire 返回值不被丢弃 + 成功路径到 `run_general_battle`;
  timing owner 无叠加（RealmRaid `fire` 恰 1 处 `random_delay`、RyouToppa `attack_area` 恰 2 处）;
  Orochi/EvoZone/Exploration FIRE 未迁。既有 `tests/test_realm_raid_state.py` 的
  `FireCharacterizationTest` / `LoopAndWaitBoundsTest` 与 `tests/test_general_battle_timing.py` 的
  RealmRaid fire timing 用例**改为锁新形态**（bounded / 正向确认 / `REACTION_FIRE` / 可返回 False）。
  回归 `1126 → 1156`（+30）。
- **三态边界收口测试（2026-09-08 同轮追加）**：`tests/test_fire_reaction_fsm.py` `29 → 34` +
  `tests/test_realm_raid_state.py::FireCharacterizationTest` `7 → 8` —— 过渡 blank 帧后下一帧 battle →
  return True 且不多点；transition/unknown 全程 → bounded timeout → False 且**从不点 partition /
  FIRE**；`I_BACK_RED` 在（明确 grid 页）才点 partition；`I_RR_PERSON` 在（详情已开）也算 retryable
  允许重开；transition/unknown 绝不点 partition；`_is_realm_raid_retryable_state` 纯只读（无
  screenshot/click/sleep/Timer）；`_wait_fire_entered_battle` 三态字符串 + 不点击。回归 `1156 → 1162`（+6）。
- **Level C pending**：`REACTION_FIRE` 0.4~0.8 体感（过短 / 过长）、FIRE 一次成功率 / retry 触发率 /
  最大 retry 是否真触发、FIRE click → `page_battle_prepare` / `page_battle` 实际时长、
  **transition blank 帧实际持续时间**、`RR_FIRE_TIMEOUT=10` / `RR_FIRE_POST_CLICK_TIMEOUT=3` 是否够、
  **是否频繁出现 `_is_realm_raid_retryable_state` 命中（`I_BACK_RED` 在但非战斗）**、**partition guard
  是否影响正常重开目标详情**、false retry 是否明显减少、RyouToppa 0.2~0.6 → 0.4~0.8 是否明显影响进攻
  节奏。无 Level C 证据不放大区间。

### 4.53 常驻刷本 FIRE FSM 第二批（Orochi / EvoZone 单人）+ Fatigue 安全节点第一批

2026-09-08。承接 §4.52，把 FIRE Contract 三态模板铺到 Orochi / EvoZone 的单人挑战路径，并把
`FatigueManager` 安全节点从「仅 RyouToppa」扩到 Orochi / EvoZone 单人。生产行为变化，Level A/B。
长期契约见 `docs/DECISIONS.md` D001 补记（FIRE 分节 增补 + Fatigue Safe Point 铺开补记）。

- **迁移前真实 inventory**：
  - **Orochi**：只有 `run_alone` 点 `I_OROCHI_FIRE`（threshold 0.6，`o_orochi_fire.png`），
    `run_wild` 点 `I_OROCHI_WILD_FIRE`，`run_leader` / `run_member` **不点 FIRE**（走
    `run_invite` / `wait_battle` + `run_general_battle`）。`run_alone` 内层 `while True`：
    `appear_then_click(I_OROCHI_FIRE, interval=1)` → `not appear(I_OROCHI_FIRE)` → 认为进入战斗、
    直接 `run_general_battle(exit_matcher=I_OROCHI_FIRE)`。**无正向战斗确认、无 bounded、无 reaction**。
    **`I_OROCHI_WILD_FIRE` 全仓无 `RuleImage` 定义**（只有图片 `o/o_orochi_wild_fire.png`）——
    `run_wild` 的 FIRE 路径当前会 `AttributeError`，是既有断链，本轮不修（需造资产 + ROI 标定，
    Level C），记入 ROADMAP。
  - **EvoZone**：只有 `run_alone` 点 `I_EVOZONE_FIRE`（threshold 0.6，`o_evozone_fire.png`），
    结构与 Orochi `run_alone` 内层循环逐字同构；`run_leader` / `run_member` 不点 FIRE；
    `run_wild` = `logger.error('Wild mode is not implemented')`。
  - **契灵（BondlingFairyland）**：`run_alone` 点 `I_BALL_FIRE`（结契按钮），但结构是
    **「连点直到按钮消失，否则 3 次 → `raise BondlingNumberMax`（契灵存量满 500）」** + caller
    `run_catch` 里两条独立语句 `self.run_alone(); self.run_general_battle(...)`（不是
    `if fire(): battle`）+ `run_catch` / `run_leader` 共用 `while 1`。**不是「单次稳定 Point FIRE →
    GeneralBattle」**，套三态模板需业务级重构 → **PARTIAL，本轮零改动**，记入 ROADMAP。

- **Orochi / EvoZone 三态 FIRE 状态机**（task-local，不塞 `BaseTask`；不抽公共 FireStateMachine
  primitive —— 见 `docs/DECISIONS.md` D015）：每个任务新增 3 个方法 + 3 个 module 常量。
  - `_fire_orochi_alone()` / `_fire_evozone_alone() -> bool`：`click_record_clear` →
    `for attempt in range(1, *_FIRE_MAX_TRIES + 1)` 且 `Timer(*_FIRE_TIMEOUT)` 未到 →
    ① `screenshot` → `is_in_battle(False)`（正向战斗确认，复用 `GeneralBattle.is_in_battle`）→
    return True；② `I_*_FIRE` 未就绪 → `_wait_*_fire_state()` 三态（不点坐标）；③ `I_*_FIRE`
    就绪 → 每 attempt 独立 `random_delay(*REACTION_FIRE)` → `sleep` → fresh `screenshot` → 再次
    `is_in_battle` → 二次 `appear(I_*_FIRE)`（reaction 期间消失则不点旧坐标、`continue`）→
    `appear_then_click(I_*_FIRE, interval=0)` → `_wait_*_fire_state()`；④ attempt / timeout 用尽 →
    **`return False`（可达）**。
  - `_wait_orochi_fire_state()` / `_wait_evozone_fire_state(timeout=*_FIRE_POST_CLICK_TIMEOUT) -> str`：
    有界 `Timer` 轮询、**不点任何坐标**，返回 `'battle'`（`is_in_battle()`，唯一 positive success）/
    `'retryable'`（`_is_*_challenge_retryable()`，仍在挑战页）/ `'timeout'`（整个 timer 内一直是
    「挑战按钮消失、战斗未出现」的过渡 / 未知帧 —— **既不当 success 也不当 immediate failure**）。
  - `_is_orochi_challenge_retryable()` / `_is_evozone_challenge_retryable() -> bool`：**纯只读当前帧**
    （不截图 / 不点击 / 不 sleep / 不改状态），判据 = `appear(I_*_FIRE)`（御魂 / 觉醒单人挑战页
    除进攻按钮外没有其它稳定持久 marker）。
  - **常量（module 级，engineering baseline，非 Level C）**：`OROCHI_FIRE_MAX_TRIES` /
    `EVOZONE_FIRE_MAX_TRIES = 4`、`*_FIRE_TIMEOUT = 10`、`*_FIRE_POST_CLICK_TIMEOUT = 3`
    （对齐 RealmRaid `RR_FIRE_*`）。
  - **caller**：`run_alone` 内层 `while True` 换成 `if self._fire_*_alone(): run_general_battle(...);
    try_fatigue_break(...)`——**FIRE 返回 False 时不进 `run_general_battle`**，回外层 `while 1` 顶
    `screenshot` + `is_in_orochi` / `is_in_evozone` 重新判定。

- **Fatigue 安全节点第一批**（`FatigueManager` consumer：RyouToppa → **+ Orochi + EvoZone**）：
  只在 **`run_alone`**（host-controlled 连续循环、无邀请 / 房间 / 队友同步）——
  循环前 `self.begin_fatigue_task('Orochi'/'EvoZone')` + `deadline = self.start_time + self.limit_time`；
  **一场完整战斗结束、`run_general_battle` 已回到稳定挑战页之后** `self.try_fatigue_break(safe=True,
  repeat_completed=True, deadline=deadline)`。休息结束回外层 `while 1` 顶会先 `screenshot` +
  `is_in_orochi` / `is_in_evozone` **fresh revalidate**（`try_fatigue_break` 自身不截图 / 不重识别）。
  **`run_leader` / `run_member` / `run_wild` 不接**（邀请 / 房间等待 / 队友同步 / 短窗口，idle 会破坏组队）。
  Fatigue 不进 FIRE 前 / FIRE reaction 内 / FIRE retry 内 / transition-unknown 内 / GeneralBattle 内。

- **明确未改**：`appear_then_click` primitive、`REACTION_FIRE`=(0.4,0.8) 及 §4.51 6 组 profile、
  RealmRaid `fire()` / `RR_FIRE_*` / `C_PARTITION_n` / T7、RyouToppa `attack_area` / fatigue node /
  区域 `random_delay(1.0,3.0)`、GeneralBattle（Settlement V3 / `prepare_click_timer` /
  `settlement_click_timer` / `_advance_generic_result`）、Exploration `fire()`（参考实现）、
  契灵全部代码、`FatigueManager` 本体、FrameWait、TouchSwipeModel、`begin_fatigue_task` /
  `try_fatigue_break` 签名。Orochi `run_wild` 的 `I_OROCHI_WILD_FIRE` 断链本轮不修。

- **测试**：新增 `tests/test_second_batch_fire_fsm.py`（27）——`REACTION_FIRE` / batch1 profile / 三个
  `*_FIRE_*` 常量不变；Orochi + EvoZone `_fire_*_alone` 正向战斗 return True 无多余点击 / reaction
  期间 FIRE 消失不点旧坐标 / transition blank → battle → True 不多点 / transition unknown 全程 →
  bounded False 不点 / retryable → 下一 attempt / bounded by MAX_TRIES / timeout timer 立即 False /
  每 attempt 独立采样 (0.4,0.8)；源码形态（三态字符串 / 无 `while True` / `range(1, *_FIRE_MAX_TRIES+1)`
  / `Timer(*_FIRE_TIMEOUT)` / 恰 1 处 `random_delay` / 无 `confirm_delay` / 可达 `return False`）；
  `_wait_*` / `_is_*_challenge_retryable` 纯只读无点击无 fatigue；caller AST（`run_general_battle` +
  `try_fatigue_break` 都在 `if self._fire_*_alone():` 体内、`run_general_battle` 全程只 1 处非裸调用）；
  Fatigue 只在 `run_alone`、在 `run_general_battle` 之后、`begin_fatigue_task` 在 FIRE 循环之前、
  leader/member/wild 零 fatigue；契灵 PARTIAL（模块不 import `REACTION_FIRE`、`run_alone` 结构不变、
  无 fatigue）；范围外 RealmRaid / RyouToppa / Exploration FIRE 未改。改
  `tests/test_fire_reaction_fsm.py::OtherFireNotMigratedTest`（`test_orochi_evozone_fire_have_no_reaction_fire`
  缩到非 run_alone 路径 + 新增契灵未迁用例，净 0）。回归 `1162 → 1189`（+27）。

- **Level C pending**：`REACTION_FIRE` 在 Orochi / EvoZone 单人的体感、FIRE 一次成功率 / retry 触发率、
  transition blank 帧实际时长、`*_FIRE_TIMEOUT` / `*_FIRE_POST_CLICK_TIMEOUT` 是否够、
  `_is_*_challenge_retryable` 是否过宽（`I_*_FIRE` threshold 0.6 假阳性）、**Fatigue 安全节点是否真正
  安全**（休息后页面是否仍保持挑战页 / 是否漏掉一场 / 组队模式确未被误插 idle）、fatigue 后
  fresh revalidate 是否足够、Orochi `run_wild` 断链修复。

### 4.54 通用组队挑战按钮 Reaction Timing 补齐（`GeneralInvite.click_fire`）

2026-09-08。承接 §4.53：Orochi / EvoZone 上一轮只迁了 `run_alone`，但**组队 / 房主真正点「挑战 /
开始战斗」按钮不是各自 task 点的，而是统一走 `GeneralInvite.click_fire()`**。本轮只在这个公共
challenge click owner 上补一次 Action reaction。生产行为变化，Level A/B。长期契约见
`docs/DECISIONS.md` D001 补记 FIRE 分节 增补（组队 challenge owner）。

- **迁移前真实链**（READ ONLY inventory）：
  - `Orochi.run_leader` / `EvoZone.run_leader`（`is_first` 首次 + 后续两处）→ `self.run_invite(config=…)`
    （`GeneralInvite`）→ `while 1`：`ensure_enter` → invite cadence（`Timer(20)` / `Timer(30)`）+
    `timer_wait` + emoji → **`if self.room_check_can_fire(config): self.click_fire(); return True`** →
    caller `run_general_battle(...)`。
  - `Orochi.run_member` / `EvoZone.run_member` → `check_then_accept()`（接受邀请）+ `wait_battle()`
    （等队长开战，`Timer(wait_second)` + emoji）→ `run_general_battle(...)`。**不点 challenge**。
  - `Orochi.run_wild` → 自己点 `I_OROCHI_WILD_FIRE`（**全仓无资产定义、既有断链**，§4.53），
    **不经 `click_fire`**。`EvoZone.run_wild` = not implemented。
  - `Orochi.run_alone` / `EvoZone.run_alone` → `_fire_orochi_alone` / `_fire_evozone_alone`（§4.53），
    **不经 `click_fire`**。
  - **`click_fire()` 旧实现**：`while 1: screenshot → if not is_in_room(False): break →
    appear_then_click(I_FIRE, interval=1, threshold=0.7) / appear_then_click(I_FIRE_SEA, ...)`。
    只有 `interval=1` throttle + `threshold=0.7`，**无 reaction / 无 confirm_delay / 无 random_delay /
    无 sleep / 无正向 `is_in_battle` 确认**；「进入战斗」= `not is_in_room(False)`（房间 UI 消失）。
- **改动（只改 `tasks/Component/GeneralInvite/general_invite.py` 的 `click_fire()`）**：
  识别 `I_FIRE`（优先）/ `I_FIRE_SEA` → `target` → **每 attempt 独立 `random_delay(*REACTION_FIRE)`
  → `sleep` → fresh `screenshot` → 二次确认**：① `not is_in_room(False)`（reaction 期间已离开房间 /
  战斗开始）→ `break`、不点旧坐标；② `not appear(target, 0.7)`（按钮消失但仍在房间）→ `continue`
  回循环顶重判；③ `target` 仍在 → `appear_then_click(target, interval=1, threshold=0.7)`。
  `while 1` / `is_in_room` 循环边界、上层 `run_invite` 的 `Timer`、`interval=1` throttle、minitouch
  dwell **不变**；不叠 `confirm_delay` / 第二套 reaction；**不接 Fatigue**（组队 challenge 不是疲劳
  安全节点）。正向战斗确认仍在下游 `run_general_battle`（本轮未改邀请 / 房间 / 战斗状态链——§13 的
  「现有链足够、只补 Action Reaction」）。imports 加 `random_delay` + `REACTION_FIRE`。
- **自动继承的 consumer**（`click_fire` 是唯一公共实现，无 task 覆写）：经 `run_invite` = **BondlingFairyland
  / EternitySea / EvoZone / Exploration / FallenSun / Orochi / OtherWorldTwilight**；直接调 `click_fire` =
  **ExperienceYoukai / GoldYoukai / Hunt / Tako**。共 11 个。本轮**不改这些 task 的其它逻辑**。
- **Action Owner 原则**（写入 D001 补记 + ARCHITECTURE）：battle-entry click 的 reaction 不按
  「单人 / 组队」区分，而按 **Action Owner（本机真实点「挑战 / 开始战斗」）vs Passive Waiter
  （只等别人开战）**。Owner → `REACTION_FIRE`；Passive（`wait_battle` / `check_then_accept` /
  `run_member`）→ 无 reaction click。
- **明确未改**：`REACTION_FIRE`=(0.4,0.8) 及 6 组 profile、`appear_then_click` primitive、Orochi /
  EvoZone `_fire_*_alone`（§4.53）、RealmRaid `fire()` / RyouToppa `attack_area`、GeneralBattle
  （Settlement V3 / FSM）、`run_invite` / `room_check_can_fire` / `invite_friends` / `wait_battle` /
  `check_then_accept` / `check_and_invite` / `exit_room` 的状态机、`FatigueManager` / Fatigue 布局、
  T7 / FrameWait / TouchSwipeModel、Navigation、Orochi `run_wild` 断链、契灵业务。
- **测试**：新增 `tests/test_general_invite_challenge_reaction.py`（23）——`REACTION_FIRE` 不变 +
  `click_fire` import/使用；行为（reaction 后 fresh screenshot → click / reaction 期间按钮消失不点
  stale / reaction 后已离开房间不点 / 顶端非房间不 reaction / 无按钮不 reaction / `I_FIRE_SEA` 变体
  同样走 reaction / 每 attempt 独立采样 (0.4,0.8)）；timing owner（`click_fire` 恰 1 处 `random_delay`
  + 1 处 `sleep`、无 `confirm_delay` / `reaction_delay` / `CLICK_REACTION_DELAY`、`run_invite` 的
  State Wait Timer 保留、challenge click 仍经 `room_check_can_fire` 门槛）；Action Owner（`wait_battle` /
  `check_then_accept` / `check_and_invite` / `invite_again` 无 `click_fire` / 无 `REACTION_FIRE`）；
  Orochi/EvoZone 兼容（`run_alone` FSM 未叠加且不经 `click_fire`、`run_leader` 经 `run_invite` 不自己写
  reaction、`run_member` 无 challenge reaction）；Fatigue 不扩散（`general_invite.py` 模块 + challenge /
  wait 路径无 fatigue token）；其它 consumer 继承（11 个 task 不覆写 `click_fire`、不自己写
  `random_delay(*REACTION_FIRE)`）。回归 `1189 → 1212`（+23）。
- **Level C pending**：组队挑战按钮 0.4~0.8 体感、leader challenge 是否漏点、reaction 后按钮消失的实际
  频率、challenge click → battle marker 过渡时间、member 是否完全不受影响、多副本共用 `click_fire` 是否
  一致。

### 4.55 `GeneralInvite.click_fire()` Battle Entry post-click 状态机 / bounded FSM 收口

2026-09-08。**§4.54 只补了 reaction，本轮补 post-click state contract**（两件事分开记，见
`docs/ROADMAP.md`）。承接 §4.52 RealmRaid 三态收口的思路，把公共组队 challenge 入口的「旧状态
消失即成功」+「`while 1` 无界」两个结构性问题收口。生产行为变化，Level A/B。契约见
`docs/DECISIONS.md` D001 补记 FIRE 分节 增补（GeneralInvite battle-entry FSM）。

- **修改前问题**：① `click_fire()` 核心是 `while 1: screenshot → if not is_in_room(False): break`
  → `run_invite` `return True` → caller `run_general_battle()`。`not is_in_room(False)` **隐含等价
  battle started / success**，但它也可能是房间解散 / 队长离开 / 页面 loading / overlay / marker
  临时识别失败。② `click_fire()` 自身 `while 1` 无界——`run_invite` 的 `timer_wait` 是同步调用前
  的整轮预算，进入 `click_fire()` 后不能主动打断内部 `while`；`is_in_room=True` 且 challenge 一直
  点不掉时理论上可无限等。
- **READ ONLY inventory 结论**：`class GeneralInvite(BaseTask, GeneralInviteAssets)` 自身不含
  `is_in_battle()`；但**`click_fire()` 的 11 个 consumer（7 经 `run_invite`：BondlingFairyland /
  EternitySea / EvoZone / Exploration / FallenSun / Orochi / OtherWorldTwilight；4 直接：ExperienceYoukai
  / GoldYoukai / Hunt / Tako）MRO 里全部带 `GeneralBattle`**（Exploration 经 `BaseExploration(GameUi,
  GeneralBattle, GeneralRoom, GeneralInvite, ...)`）。`general_battle.py` **不 import** `general_invite.py`
  （无循环依赖）。唯一 `GeneralInvite`-without-`GeneralBattle` 的类 `MysteryShop` **不调** `click_fire` /
  `run_invite`。`GeneralInvite` 已 `import GeneralBattleAssets`（`check_then_accept` 用 `I_EXIT`）+
  `GameUiAssets`（`wait_battle` 用 `I_CHECK_MAIN` / `I_CHECK_EXPLORATION` 判 room destroyed）。
- **方案选 A（GeneralInvite 内部拥有 battle verify + marker 兜底）**：新增只读 helper
  `_battle_entry_positive()` = `callable(getattr(self,'is_in_battle',None))` → `self.is_in_battle(False)`
  （所有真实 consumer 走这条）；否则兜底 `appear(GeneralBattleAssets.I_BATTLE_INFO) or
  appear(GeneralBattleAssets.I_PREPARE_HIGHLIGHT)` —— **`is_in_battle()` 8 个 positive marker 里的
  两个 battle-entry marker，严格子集**，不新造 detector、不引入 `is_in_battle` 未采用的更宽 heuristic
  （`MysteryShop` 结构上安全）。未选 B（callback 注入——改 11 consumer + `run_invite` 签名）/ C
  （positive verify 留 caller——caller 无法修内部 while 的 success 误判）。**（fallback 初版含
  `I_EXIT`——`I_EXIT` 不属 `is_in_battle()` marker 集、是 battle-scene 左上角退出按钮启发式；静态
  复核后 2026-09-08 收尾轮已把 `I_EXIT` 从 fallback 移除，`GeneralBattleAssets.I_EXIT` 本体及
  `exit_battle` / `check_then_accept` / `BondlingFairyland.wait_battle` 等原有 consumer 全部保留不动。）**
- **四态 FSM**（`_classify_room_entry_state()` 只读、优先级 battle > room_failed > retryable > unknown）：
  - `'battle'`：`_battle_entry_positive()` —— **唯一 positive success**；
  - `'room_failed'`：`_room_entry_failed()` = `appear(I_MATCHING) or appear(GameUiAssets.I_CHECK_MAIN)
    or appear(GameUiAssets.I_CHECK_EXPLORATION)` —— 明确房间失效（回匹配 / 庭院 / 探索；复用
    `ensure_enter` / `run_invite` / `wait_battle` 已有 marker，不新造）。「队长跑路」在 `click_fire`
    语境不适用（本机就是房主，`I_FIRE` 可见是正常待点）。
  - `'retryable'`：`is_in_room(False)` —— 明确仍在可操作组队房间；
  - `'unknown'`：三者都不是 —— loading / blank / 转换过渡帧。
  - `_wait_room_entry_state(timeout=GI_FIRE_POST_CLICK_TIMEOUT)` 有界 `Timer` 轮询、**不点坐标**，
    返回 `'battle'` / `'room_failed'` / `'retryable'` / `'timeout'`（整段一直 `'unknown'` —— 既不当
    success 也不当 immediate failure）。
- **`click_fire() -> str`**（`'battle'` / `'room_failed'` / `'timeout'`）：`overall_timer =
  Timer(GI_FIRE_TIMEOUT)` + `for attempt in range(1, GI_FIRE_MAX_TRIES + 1)`：分类 → `'battle'`
  return / `'room_failed'` return / `'unknown'` → 有界 `_wait_room_entry_state` 不点坐标 / `'retryable'`
  → 识别 `I_FIRE`（优先）/ `I_FIRE_SEA` → 每 attempt 独立 `random_delay(*REACTION_FIRE)` → `sleep`
  → fresh `screenshot` → 重新分类（battle/room_failed 立即返回；离开 retryable / 按钮消失 → 不点
  旧坐标、下一 attempt）→ `appear_then_click(target, interval=1, threshold=0.7)` → `_wait_room_entry_state`
  → battle return / room_failed return / 其它 → 下一 attempt。用尽 → `return 'timeout'`。**无 `while 1`。**
- **常量**（module 级，**PROVISIONAL / Level C 待标定**）：`GI_FIRE_MAX_TRIES = 4`（对齐
  RealmRaid / Orochi / EvoZone）、`GI_FIRE_TIMEOUT = 15`（组队进战斗比个人突破慢——队友加载 /
  队长开战同步；`run_invite` 的 `timer_wait` / `Timer(20/30)` 都不 bound「按开始→战斗加载」窗口）、
  `GI_FIRE_POST_CLICK_TIMEOUT = 4`（略宽于 RealmRaid 的 3）。
- **`GI_FIRE_TIMEOUT` 的正式语义 = soft new-attempt admission budget，不是 strict wall-clock hard
  deadline**（2026-09-08 静态复核确认）：`overall_timer.reached()` 只在 `for attempt` 循环顶检查
  ——决定「是否允许启动新 attempt」；一旦 attempt 已启动，其 `random_delay(*REACTION_FIRE)` +
  `_wait_room_entry_state`（自带独立 `Timer(GI_FIRE_POST_CLICK_TIMEOUT)`，不接收 remaining budget，
  `Timer.reached()` 纯轮询、不能异步打断）会正常跑完。因此最后一个在途 attempt 可超出
  `GI_FIRE_TIMEOUT`——显式 overrun 约最多 `max(REACTION_FIRE) 0.8 + GI_FIRE_POST_CLICK_TIMEOUT 4
  ≈ 4.8s`，显式理论返回上界 ≈ `15 + 4.8 ≈ 19.8s`，另加 screenshot / matching / device 开销。
  **仍是 bounded / finite**（`GI_FIRE_MAX_TRIES` + soft budget + 每个 `_wait_*` 的 `Timer` 三重保证），
  只是不是精确 15 秒硬边界。**保留 soft 设计**（与 RealmRaid `fire()` / Orochi·EvoZone `_fire_*_alone`
  结构一致——它们同样是「顶层 `Timer(TIMEOUT).reached()` gate + 内层独立 `Timer(POST_CLICK)`」；
  不会在接近 battle 正向确认时因 strict deadline 硬切断；对网络 / 战斗加载抖动更宽容），本轮不改
  timeout 代码。
- **caller guard**：`run_invite` 的 `if self.room_check_can_fire(config): self.click_fire(); return True`
  → `fire_result = self.click_fire(); if fire_result == 'battle': return True` else `return False`。
  `run_invite` 返回 `False` 的语义扩大（新增 `room_failed` / `timeout`）——各 caller（Orochi /
  EvoZone / EternitySea / FallenSun / BondlingFairyland / OtherWorldTwilight）已有的 `else: 邀请
  失败退出任务` 分支 / Exploration 的 `raise InviteFailedException` **天然承接**，**不误交接
  `run_general_battle`**。**4 个直接 caller**：ExperienceYoukai / GoldYoukai / Tako 加
  `if self.click_fire() == 'battle': (count += 1;) run_general_battle()`；Hunt 加
  `battle_entered = self.click_fire() == 'battle'` + `if not battle_entered: return`。业务策略未改。
- **明确未改**：`REACTION_FIRE`=(0.4,0.8) / 每 attempt 独立采样 / fresh reconfirm / no stale click /
  无 timing stack、`appear_then_click` primitive、`run_invite` 的 invite cadence（`Timer(20/30)` /
  `timer_wait` / emoji）/ `invite_friends` / `room_check_can_fire` / `check_then_accept` /
  `check_and_invite` / `invite_again` / `wait_battle` / `exit_room`、member / passive path 无 reaction、
  Orochi / EvoZone `_fire_*_alone`、RealmRaid / RyouToppa FIRE、GeneralBattle（Settlement V3 / FSM）、
  Fatigue（`click_fire` / `_classify_*` / `_wait_*` / `run_invite` / wait 路径无 fatigue token）、
  T7 / FrameWait / TouchSwipeModel、Navigation、契灵业务。
- **测试**：`tests/test_general_invite_challenge_reaction.py` `23 → 41`——加 `_FakeTimer`（patch
  `gi.Timer`，之前只 patch `sleep` / `random_delay` → 超时路径跑真墙钟 113s → 现 0.3s）；源码形态
  （无 `while 1` / `for attempt in range(1, GI_FIRE_MAX_TRIES + 1)` / `Timer(GI_FIRE_TIMEOUT)` / return
  值恰 `{'battle','room_failed','timeout'}` / 4 个 helper / classify 含四态字符串 / reaction→fresh
  screenshot→reconfirm 顺序 / `_wait_*` 与三个 classify helper 只读无点击 / `_room_entry_failed`
  复用既有 marker / `_battle_entry_positive` 优先 `is_in_battle` + marker 兜底 / 恰 1 `random_delay`
  + 1 `sleep` 无 `confirm_delay`）；行为（正向 battle return `'battle'` 无多余点击 / **「不在房间」
  单独发生 → `'timeout'` 不当 success** / transition unknown → battle 无点击 / room_failed（庭院 /
  匹配 / 探索）立即返回不点 / retryable 多 attempt 每次独立采样 / 按钮 reaction 期间消失不点 stale /
  离开 retryable 不点 stale / bounded by MAX_TRIES / overall_timer budget 0 立即 timeout 0 点击 0
  截图 / `I_FIRE_SEA` 变体 / `_battle_entry_positive` 兜底路径）；caller guard（`run_invite` 只
  `== 'battle'` return True；3 个直接 caller `if self.click_fire() == 'battle':`；Hunt `battle_entered`
  flag + `if not battle_entered:`）；Action Owner（passive 无 reaction）；Orochi/EvoZone 兼容；
  Fatigue 不扩散；11 consumer 不覆写 + `is_in_battle` in MRO。回归 `1212 → 1230`（+18）。
- **Level C pending**：challenge click → battle positive marker 实际时间、room marker 消失到 battle
  marker 出现的 blank duration、retryable room 实际命中率、room destroyed / leader gone 真实 marker
  是否够、`GI_FIRE_TIMEOUT=15` / `GI_FIRE_POST_CLICK_TIMEOUT=4` / `GI_FIRE_MAX_TRIES=4` 是否合理、
  11 consumer 行为差异、`run_invite` 返回 `False` 更频繁是否导致任务过早退出。

### 4.56 RealmRaid 九宫格固定 1→9 / 退四主流程改造 + Fatigue 安全节点

2026-09-08。用户已确定的 RealmRaid 目标选择 / 退四 / 失败策略业务改造（`docs/ROADMAP.md`「RealmRaid
目标选择 / 退四策略改造」8 条）本轮全部落地。生产行为变化，Level A/B（真机验收待窗口）。长期契约见
`docs/DECISIONS.md` **D020**（RealmRaid 主业务策略：目标选择 / 退四 / 失败 / 目标 pacing）+ D001 补记
（FIRE 分节 增补——`_fire_again` 退四内部「再次挑战」）。唯一生产文件 `tasks/RealmRaid/script_task.py`。

- **修改前真实 inventory**：`run()` 主循环 = `find_one()`（`order_medal` ImageGrid 按 `order_attack`
  配置的勋章优先级 `find_anyone` 选一格）→ `check_medal_is_frog` → `ensure_lock` →
  `click(C_PARTITION[index-1])` → `fire(index)`（§4.52 已收口三态）→ `run_general_battle`。退四 = 旧
  `run()` 里 `if index == 1`（九宫格第 1 格）触发 → `fire` 一次 + **逐字硬编码 4 次** `fire_again()`
  （前 3 次 `build_quick_exit_config` 投降、第 4 次真打）。`fire_again()` = `wait_until_appear(I_FIRE_AGAIN)`
  （无超时）+ `while 1`：`appear_then_click(I_SHOW_AGAIN)` / `(I_FRESH_ENSURE)` / `(I_FIRE_AGAIN)`，恒返回
  True、尾部 `return False` 不可达。`find_one` 在 `WhenAttackFail.CONTINUE` 下把失败格在
  `self.device.image` 上**原地涂黑**（污染共享帧，R-R9）。普通失败与退四最终失败都走 `run()` 尾部
  `when_attack_fail`（REFRESH/EXIT/CONTINUE）。
- **A. 固定 1→9，取消勋章排序**：新增 `_grid_targets() -> {1-based order: 勋章 RuleImage}`——
  `order_medal.find_everyone()` 一次扫全 9 格（`order_medal` 只当「这格有没有可挑战对手」的过滤器，
  **不再按勋章数量 / `order_attack` 优先级排序**），每个匹配按中心点映射回 `C_PARTITION_n` 的
  `roi_front`。`run()` 取 `index = min(targets)`（最小 1-based order = 从左到右、从上到下第一个）。
  `find_one()` 重写成 `_grid_targets` 的薄包装（`order = min(targets)`），保留 `(medal, order)` 签名供
  `check_medal_is_frog`——**勋章值只影响呱太判定，不再影响攻击顺序**。`order_medal` / `I_MEDAL_0..5`
  资产 / 呱太 OCR 全部保留未删（D020）。
- **B. 失败格识别脱离 mode + 不再原地涂黑**：`_broken_orders() -> set`（1-based）复用 `false_roi` +
  `false_image`（RyouToppa `loser_sign_1.png`），**所有模式都扫**（旧代码只在 `CONTINUE` 下扫——固定
  1→9 选目标后，刚失败还没刷新的格子必须排除，否则被重复选中）。`_grid_targets` 在 `image.copy()` 上
  涂黑 broken 格（`broken` 非空才 copy），**不再原地污染 `self.device.image`**（修 R-R9）。
- **C. 目标级业务 pacing `RR_TARGET_PACING = (1.0, 2.5)`**（module 常量，PROVISIONAL / Level C）：新增
  `_enter_target(order) -> bool`——`screenshot` → `_target_still_attackable(order)`（=
  `order in self._grid_targets()`，纯只读）→ `random_delay(*RR_TARGET_PACING)` → `sleep` →
  `screenshot` → `_is_realm_raid_retryable_state()` + `_target_still_attackable` 二次确认 →
  `click(C_PARTITION[order-1], interval=2)`。pacing 期间目标变不可打 / 离开可操作页 → 不点旧坐标、
  `return False`（`run()` 重新扫九宫格）。**只在每个新选定目标点开详情前一次**，不进 FIRE retry /
  post-click / 再次挑战 / battle / settlement / refresh。与 `REACTION_FIRE`（FIRE 自身，在 `fire()`）是
  两个不同 timing owner，不合并；旧记录的「1~3 秒」对 RealmRaid 目标 pacing 作废（RyouToppa 区域
  pacing `(1.0, 3.0)` 属 RyouToppa，未动）。
- **D. 普通目标失败 → 按 `when_attack_fail`（默认 REFRESH）**：AskUserQuestion 确认「保留配置，普通失败
  仍按 `when_attack_fail` 走」。普通分支落 `run()` 尾部 `if not last_battle and when_attack_fail ==
  REFRESH: check_refresh()` / `== EXIT: break`（原逻辑保留）。**「再次挑战」`_fire_again()` 绝不用于
  普通失败目标**（只在退四内部）。
- **E. 退四触发 = 「只剩最后 1 个可攻打目标」**：AskUserQuestion 确认「完全替换为『只剩最后 1 个可攻打
  目标』」——`only_last = len(targets) == 1`；`if only_last and con.raid_config.exit_four:` 进入退四。
  **替换掉旧的 `index == 1`（九宫格第 1 格）触发**（旧触发在固定 1→9 下语义完全错位）。
- **F. 退四前解锁阵容**：退四分支 `self.ensure_lock(False)`（`ensure_lock(False)` 真实语义 = 最终
  UNLOCKED，已核实非猜测）→ `_enter_target` → `fire` → 退四循环；结束 `self.ensure_lock(lock_default)`
  恢复用户配置。普通目标不动锁定状态。`lock_default = con.general_battle_config.lock_team_enable` 循环
  外捕获一次、每轮循环顶复位（呱太目标临时 `lock_team_enable = False` 一轮）。
- **G. 退四内部「再次挑战」= `REACTION_FIRE`**：`fire_again()` 重命名 `_fire_again()` 并完全重写成与
  `fire()` 同一 FIRE Contract（三态、bounded）——`wait_until_appear(I_FIRE_AGAIN,
  wait_time=RR_AGAIN_TIMEOUT)` + `Timer(RR_AGAIN_TIMEOUT)` + `for attempt in range(1,
  RR_AGAIN_MAX_TRIES + 1)`：正向 `is_in_battle(False)` → return True；`I_SHOW_AGAIN` / `I_FRESH_ENSURE`
  流程点击（无 reaction）先点掉；`I_FIRE_AGAIN` 未就绪 → 有界 `_wait_again_entered_battle()`；就绪 →
  每 attempt 独立 `random_delay(*REACTION_FIRE)` → `sleep` → fresh `screenshot` → 二次 `appear(I_FIRE_AGAIN)`
  （消失不点旧坐标）→ `appear_then_click(I_FIRE_AGAIN, interval=0, threshold=0.8)` →
  `_wait_again_entered_battle()`。用尽 → 可达 `return False`。新增 `_wait_again_entered_battle(timeout=
  RR_AGAIN_POST_CLICK_TIMEOUT) -> str`（`'battle'` / `'failure_page'`（`I_FIRE_AGAIN` / `I_FRESH_ENSURE`
  在）/ `'timeout'`，不点坐标）。常量 `RR_AGAIN_MAX_TRIES=4` / `RR_AGAIN_TIMEOUT=10` /
  `RR_AGAIN_POST_CLICK_TIMEOUT=3`（对齐 `RR_FIRE_*`，engineering baseline 非 Level C）。
- **退四结束条件 = 源码可证的 4 次**（`RR_EXIT_FOUR_SURRENDERS = 4`）：旧 `run()` 里逐字硬编码 4 次
  `fire_again()`，不是新拍的次数（§5「don't guess 退四 count」不触发）。`for i in
  range(RR_EXIT_FOUR_SURRENDERS)`：`_fire_again()` 失败 → `aborted = True; break`；`is_final = i == 3`
  → 第 4 次 `con.general_battle_config`（真打）、前 3 次 `build_quick_exit_config`（投降）。
- **H. 退四中断 / 最终失败 → 统一刷新**：`if aborted or not last_battle:` → `check_refresh()` → 成功
  `continue`（**不再点「再次挑战」**）/ CD 中 `success = False; break`。退四胜利 → 落共享尾部。
- **Fatigue 安全节点接入**（AskUserQuestion 确认「本轮就接入」）：`self.begin_fatigue_task('RealmRaid')`
  在主 `while 1:` 之前；新增 `_realm_raid_cycle_safe_break()` = `screenshot` →
  `_is_realm_raid_retryable_state()` 才 `try_fatigue_break(safe=True, repeat_completed=True,
  deadline=None)`，在普通目标 / 退四「一个完整目标业务循环（战斗 + 结果 + 必要刷新）结束、即将回循环顶
  重新 `check_ticket` + 扫九宫格」处调用。RealmRaid 无墙钟时限（挑战次数由 `number_attack` 限），
  `deadline=None`。休息 / 发呆结束回循环顶先 `screenshot` + `check_ticket`（`wait_until_appear(I_BACK_RED)`）
  + `_grid_targets` 重扫 = fresh revalidate + reselect。Fatigue 不进 target pacing / FIRE / FIRE retry /
  transition-unknown / battle / settlement / reward / 退四内部 / `_fire_again` 之间 / refresh 动画。
- **明确未改**：`fire()` R-R1 三态 / `_wait_fire_entered_battle` / `_is_realm_raid_retryable_state` /
  `RR_FIRE_*`（§4.52）；`ensure_lock` / `check_refresh` / `check_ticket` / `reward_detect_click` /
  `check_medal_is_frog` / `is_frog` / `_handle_result` / `_exit_matcher` / `false_roi` / `false_image`；
  `C_PARTITION_n` 坐标 / ROI / RuleClick / ClickSampler / T7；`order_medal` / `I_MEDAL_*` / 呱太 OCR
  资产（只是不再参与排序）；`I_FIRE` / `I_FIRE_AGAIN` / `I_SHOW_AGAIN` / `I_FRESH` / `I_FRESH_ENSURE`
  资产；`REACTION_FIRE` 数值；GeneralBattle（Settlement V3 / FSM）；GeneralInvite / RyouToppa / Orochi /
  EvoZone / Exploration / Kekkai / Navigation。
- **测试**：`tests/test_realm_raid_state.py` 重写——`FireAgainCharacterizationTest`(4) →
  `FireAgainThreeStateTest`(11，bounded / 三态 / 每 attempt 独立 reaction / 弹窗流程点击 / 消失不点
  stale / 可返回 False)；`FindOneCharacterizationTest`(5) → `FindOneFixedOrderTest`(7，`min(order)` /
  medal-independent / broken 排除 / copy 不污染帧)；`LoopAndWaitBoundsTest` 加 `_fire_again` bounded
  断言；`GeneralBattleHandoffTest` 锁 `run_general_battle` 交接次数 + `RR_EXIT_FOUR_SURRENDERS == 4`；
  新增 `MainFlowRefactorTest`(12，固定 1→9 无勋章排序 / 退四触发 = `only_last` 非 `index==1` / 退四前
  `ensure_lock(False)` / `RR_TARGET_PACING` 常量 + 唯一 owner / 普通失败按 `when_attack_fail` / Fatigue
  只在 cycle safe point / `_fire_again` 只在退四内部)。`tests/test_reaction_timing_batch1.py` 一行改
  （`fire_again` → `_fire_again`）。回归 `1235 → 1257`（+22，0 regression）。
- **Level C pending**：`_grid_targets` 用 `find_everyone` 全格扫描的稳定性（match center 落 `roi_front`
  的映射准确率）、`_broken_orders` 对刚失败未刷新格的实际命中率、`RR_TARGET_PACING (1.0, 2.5)` 体感、
  退四「只剩最后 1 个」判定在真机的可靠性、`ensure_lock(False)` 在退四场景确实解锁、`RR_AGAIN_*` 参数
  体感、退四最终失败刷新收敛、RealmRaid Fatigue safe point 实际触发位置是否稳定回到个人突破页。

**correctness follow-up（2026-09-08 同轮追加，`docs/DECISIONS.md` D020 补充，非新 ADR）**：§4.56
落地后复核出 4 个 correctness 边界，本轮只修这 4 个、不扩新功能。唯一生产文件仍是
`tasks/RealmRaid/script_task.py`。

- **A. `when_attack_fail == CONTINUE` 真正跳过刚失败目标**：§4.56 删掉了「在 `self.device.image`
  上原地涂黑失败格」的旧方案（对，见 R-R9），但旧方案承担的业务语义「CONTINUE = 当前失败目标本轮
  不再打」丢了——`_grid_targets()` 只排除 `_broken_orders()`，失败但没变 broken 的格下一轮 `min()`
  会再次选中。本轮新增**纯局部 `failed_orders: set`**（`run()` 内，不污染截图 / 不改 asset / 不伪造
  broken marker）：普通目标失败且 `when_attack_fail == CONTINUE` → `failed_orders.add(index)`；选目标
  时 `available = {order: m for order, m in targets.items() if order not in failed_orders}`，
  `index = min(available)`；`if not available:`（全破 / 全跳过）→ CONTINUE 则 `check_refresh()`；
  **刷新成功后 `failed_orders.clear()`**（每处 `check_refresh()` 成功分支都 clear，是唯一清空点）。
  `_broken_orders` / `false_image` / broken detector **未动**——failed/skipped ≠ broken。
- **B. Fatigue Safe Point 后移到 failure recovery 之后**：§4.56 里普通分支是
  `run_general_battle → _realm_raid_cycle_safe_break() → 共享尾部 → when_attack_fail → REFRESH 时
  check_refresh()`，即「battle failure → fatigue → refresh」顺序错。本轮把普通分支 battle 之后的
  `_realm_raid_cycle_safe_break()` **删掉**，改在共享尾部**每个结果流的 recovery 完成之后**触发：
  普通胜利 → 尾部末尾；普通失败 REFRESH → `check_refresh()` 成功后；普通失败 CONTINUE →
  `failed_orders.add` 后；退四胜利 → 尾部末尾（退四块不再自己调）；退四中断 / 最终失败 →
  `check_refresh()` 成功后；普通失败 EXIT → 直接 `break`（不为 fatigue 拖延退出）。
- **C. 退四前 fresh 重确认唯一目标**：§4.56 的 `only_last = len(targets) == 1` 只是某一帧判断。
  本轮：① 进入退四块先 `self.screenshot()` + 新只读 helper `_is_only_remaining_target(order)`
  （= `_is_realm_raid_retryable_state()` and `len(_grid_targets()) == 1` and `order in targets`，
  不截图 / 不点击 / 不 sleep），不满足 → `continue` 回主循环重扫；② `_enter_target(order,
  require_only_remaining=True)` —— pacing 前后的「仍可攻打」收紧成「仍是唯一可攻打目标」，pacing
  延迟期间又出现别的可攻打目标 → 返回 False。**`only_last` 仍用 raw `len(targets)`，不用
  skip 过滤后的 `available`**——退四判据是「真实 UI 上只剩 1 个可攻打」，不是「本轮失败跳过后只剩
  1 个」（`raw = {5,8}` + `failed = {5}` → `available = {8}` 但 `only_last = len({5,8}) == 1` = False，
  打 8 走普通分支，不进退四）。若 raw 唯一目标恰好在 `failed_orders` 里 → `available` 空 →
  CONTINUE 走刷新，不进退四。
- **D. 退四临时解锁用 `try/finally` 恢复**：§4.56 是 `ensure_lock(False)` … `ensure_lock(lock_default)`
  两条平行语句，`continue` / `break` / 异常路径漏恢复。本轮 `ensure_lock(False)` 之后
  `try: (_enter_target / fire / 首战 run_general_battle / 4×(_fire_again + run_general_battle))
  finally: self.ensure_lock(lock_default)`。`finally` **只恢复锁**，无 `except`、不吞原异常
  （`run_general_battle` 抛异常 → 先恢复锁再原样传播）。`lock_default =
  con.general_battle_config.lock_team_enable`（循环外捕获一次），不写死 True/False——用户原本不锁
  → 退四后恢复不锁。
- **`_realm_raid_cycle_safe_break()` 增强**：fatigue 前先
  `wait_until_appear(self.I_BACK_RED, wait_time=RR_CYCLE_STABLE_TIMEOUT)`（新常量 `= 10`，复用个人
  突破页固定返回键作 recovery-complete 判据，不用固定 sleep）确认刷新 / 结算动画结束、确实回到
  稳定九宫格，再 `screenshot` + `_is_realm_raid_retryable_state()` 守卫才 `try_fatigue_break`。
- **未改**：`fire()` R-R1 三态 FSM / `RR_FIRE_*` / `REACTION_FIRE` / partition guard / positive
  battle contract；`_fire_again()` 三态 bounded FSM / `RR_AGAIN_*`（本轮**未重写** `_fire_again`）；
  `RR_TARGET_PACING = (1.0, 2.5)` 数值 / `RR_EXIT_FOUR_SURRENDERS = 4`；`order_medal` / `I_MEDAL_*` /
  `check_medal_is_frog` / `is_frog`；GeneralBattle / GeneralInvite / RyouToppa / Orochi / EvoZone /
  Exploration / Kekkai / Navigation。
- **测试**：`tests/test_realm_raid_state.py` `63 → 93`——改 3 处
  （`test_wait_until_appear_calls_...` 带 wait_time 的 2 → 3 加 `I_BACK_RED`；
  `test_fatigue_break_after_battle_before_shared_tail` → `test_fatigue_after_failure_recovery_not_before_refresh`
  + 新 `test_cycle_safe_break_confirms_stable_grid_before_fatigue`；`test_target_pacing_...` 的
  `_enter_target(index)` 计数改前缀匹配 + 断言 `require_only_remaining=True`）；新增
  `CorrectnessFollowupSourceTest`(11，源码形态：`failed_orders` 局部 set 不涂帧 / `available` 排除
  skip / `only_last` 用 raw / 退四入口 fresh revalidate 在 unlock 前 / `_is_only_remaining_target`
  只读 / `_enter_target` `require_only_remaining` 后置复查 / `try/finally` 无 `except` 覆盖
  battles / `lock_default` 来自 config / 每处 `check_refresh` 成功都 clear 再 fatigue / battle 后不
  紧跟 fatigue / CONTINUE 分支 add→fatigue→continue / EXIT 分支无 skip·refresh·fatigue）+
  `RunLoopBehaviorTest`(19，`_RunHarness` 驱动 `run()` 主循环：CONTINUE 跳过刚失败目标 / 两次失败
  选第三个 / 失败目标 UI 仍 attackable 也 skip / 全跳过 refresh + clear / 普通 REFRESH 失败
  fatigue 在 refresh 之后 / 普通 CONTINUE 失败 fatigue 在 skip 之后无 refresh / 退四最终失败先
  恢复锁再 refresh 再 fatigue / 退四入口 fresh 帧非唯一则中止不 unlock / `only_last` 用 raw 不用
  filtered / order 5 也能进退四不要求 index==9 / `_enter_target` False → finally 恢复锁 /
  `fire` False → finally 恢复锁 / `run_general_battle` 抛异常 → finally 恢复锁且原异常传播 /
  `lock_default=False` 退四后恢复 False 从不 True / EXIT 失败 break 无 skip·refresh·fatigue /
  普通胜利 cycle 末尾 fatigue / 退四胜利经共享尾部 fatigue + 恢复锁)。回归 `1257 → 1287`
  （+30，0 regression）。
- **Level C pending（追加）**：CONTINUE `failed_orders` 与真机「失败格是否变 broken」的实际重叠
  （是否出现失败格既进 `failed_orders` 又进 `_broken_orders`——无害但值得观测）、`RR_CYCLE_STABLE_TIMEOUT
  = 10` 是否够覆盖刷新 / 结算动画、退四入口 `_is_only_remaining_target` 二次确认在真机是否偶发
  误否决（模板抖动）、`check_refresh()` 返回 True 后 `I_BACK_RED` 出现的实际延迟。

**Level C hotfix（2026-09-08，真机实测发现 + 修复，`docs/DECISIONS.md` D001 补记，非新 ADR）**：
2026-09-08 真机日志实测 —— 退四首战主动退出、`Battle result: Lose` 之后，`_fire_again()` **没有
任何 `Fire again: attempt` / reaction / `I_FIRE_AGAIN` 点击日志就直接打印 `Fire again: entered
battle`**，caller 又 `run_general_battle()` 立即重新识别同一个 `page_battle_result` → `Lose` →
循环产生「假 fire_again」，所谓 4 次退四大部分没有真实点「再次挑战」。

- **根因**：`_fire_again()` / `_wait_again_entered_battle()` 用 `GeneralBattle.is_in_battle(False)`
  作 positive battle-entry 判据。`is_in_battle()` 是「准备 + 战斗 + 结果 + 奖励」整个战斗生命周期
  detector —— OR 里含 **`I_FALSE`（失败横幅）/ `I_WIN` / `I_DE_WIN`（胜负横幅）/ `I_REWARD` /
  `I_REWARD_GOLD`（奖励页）/ `I_FRIENDS`**。退四首战退出后停在失败结算页时 `I_FALSE` 命中 →
  `is_in_battle(False)` 恒 True → 「仍停在上一场失败结果页」被误判成「再次挑战已进入下一场战斗」。
- **修复（只改 RealmRaid consumer，不动 `GeneralBattle.is_in_battle()`）**：新增 RealmRaid-local
  只读 helper **`_is_active_battle_entry() -> bool`** = `self.is_in_prepare(False) or
  self.is_in_real_battle(False)` —— 复用 GeneralBattle 已有的**两个窄 detector**：
  `is_in_prepare()`（`I_BUFF` / `I_PREPARE_HIGHLIGHT` / `I_PREPARE_DARK` / `I_PRESET` /
  `I_PRESET_WIT_NUMBER`）、`is_in_real_battle()`（`I_BATTLE_INFO`），两者都**不含** result /
  reward marker。`_fire_again()` 的 3 处 `is_in_battle(False)` + `_wait_again_entered_battle()`
  的 1 处全部换成 `_is_active_battle_entry()`。三态语义不变（`battle` / `failure_page` /
  `timeout`），只是 `battle` 的判据收窄。**`GeneralBattle.is_in_battle()` / `is_in_prepare()` /
  `is_in_real_battle()` 本体及其它 consumer 全部不动。**
- **未改**：`fire()` R-R1（其 `is_in_battle(False)` 用法**本轮不动**——`fire()` 在
  `wait_until_appear(I_RR_PERSON)` 之后、目标详情页上点第一次 FIRE，前面没有战斗结果页，
  安全-by-context；未来若做一致性收窄再评估，见 `docs/ROADMAP.md`）；`_fire_again` 的
  `RR_AGAIN_MAX_TRIES=4` / `RR_AGAIN_TIMEOUT=10` / `RR_AGAIN_POST_CLICK_TIMEOUT=3`（当前 bug 与
  timeout 参数无关，不借机调参）；`REACTION_FIRE=(0.4,0.8)` / 每 attempt 独立采样 / fresh
  reconfirm / no stale click；退四触发（`only_last` / raw count / `_is_only_remaining_target` /
  `require_only_remaining` / target pacing / try/finally unlock）；`RR_EXIT_FOUR_SURRENDERS=4`；
  普通失败 `when_attack_fail`；RealmRaid Fatigue safe point；GeneralBattle / GeneralInvite /
  RyouToppa / Orochi / EvoZone / Exploration / Kekkai / Navigation。
- **测试**：`tests/test_realm_raid_state.py` `93 → 103`——`FireAgainThreeStateTest._mk` 改 mock
  `t._is_active_battle_entry`（原 mock `t.is_in_battle`）；新增 `ActiveBattleEntryContractTest`(10)：
  源码形态（`_is_active_battle_entry` 只 `is_in_prepare(False) or is_in_real_battle(False)`、代码体
  无 `is_in_battle(` / 无 result·reward marker / 纯只读；`_fire_again` / `_wait_again_entered_battle`
  代码体不再有 `is_in_battle(`、改用 `_is_active_battle_entry()`；`GeneralBattle.is_in_battle()`
  仍宽、`is_in_prepare` / `is_in_real_battle` 仍窄）+ 行为（result/reward-only 帧 → `_is_active_battle_entry`
  False 且不问宽 detector；prepare / real-battle 帧 → True；**`I_FALSE` 帧 + `I_FIRE_AGAIN` 可见 →
  `_fire_again` 不 short-circuit、必须走 reaction + 真实 `I_FIRE_AGAIN` click**；active-battle 首帧 →
  True 不点；click 后按钮消失 + active 暂未出现 → unknown 不乱点、之后 active 出现才 True；失败页
  一直在 + active 永不出现 → bounded → False）。回归 `1287 → 1297`（+10，0 regression）。
- **同步 OASX 个人突破过时配置显示**：OASX（`d:\oas_xy\OASX`）个人突破配置文案 source of truth =
  **前端硬编码 Dart map `lib/translation/cn_parts/cn_realm_raid_config.dart`**（不是从 backend
  schema 自动生成）。旧文案 `exit_four` = 「当进攻到左上角第一个的时候先退四次再进攻」、
  `order_attack` = 「挑战顺序」+ 「使用过滤器，保持默认即可」，均为 §4.56 之前的旧逻辑。改成：
  `exit_four` →「打九退四（只剩最后一个可攻打目标时）」+ help 说明「只剩最后一个可攻打目标时先退四
  再最终挑战，其余目标按固定顺序正常攻打」；`order_attack` →「攻打的勋章档位」+ help 说明「数字
  5~0 = 勋章数量档位，先后顺序不再决定攻击顺序，目标一律按九宫格固定 1→9 选择」。**`order_attack`
  backend config field 保留**（`tasks/RealmRaid/config.py`，仍被 `order_medal` cached_property 消费
  —— 决定 `ImageGrid` 里放哪些 `I_MEDAL_*` 模板，即哪些勋章档位算「可攻打对手」；`>` 排序已 vestigial）。
  backend web i18n 副本 `module/config/i18n/zh-CN.json`（`.gitignore` 忽略、`module/server/i18n.py`
  服务）同步改了同 4 个 key。**PyQt GUI 的 `module/config/i18n/zh_CN.xml` / 编译产物 `zh_CN.qm`
  未改**（需 Qt `lrelease` 重新编译，本环境无该工具链）——记为 backend PyQt i18n 待同步项。

### 4.57 RealmRaid 再次挑战确认弹窗独立 reaction（Level A/B）

本轮只处理退四 `_fire_again()` 内「再次挑战」点击后出现的确认弹窗。静态 inventory 已确认：`I_FIRE_AGAIN` 是失败结果页的「再次挑战」按钮；`I_SHOW_AGAIN` 是「不再提示」复选项；`I_FRESH_ENSURE` 的资产注释为「刷新确认 / 再战确认」，并且在 `check_refresh()` 与 `_fire_again()` 中都是实际确认点击 target。

- **修改**：新增任务本地 `RR_AGAIN_CONFIRM_DELAY = (0.3, 0.6)`（PROVISIONAL）。仅 `_fire_again()` 的 `I_FRESH_ENSURE` 调用显式传入 `confirm_delay=RR_AGAIN_CONFIRM_DELAY`；复用 `BaseTask.appear_then_click` 已锁定的事务：识别 → `random_delay` / `sleep` → fresh screenshot → 第二次 `appear` → 新帧 `coord()` → click。第二次确认失败直接返回 False，不点击旧坐标。
- **Timing owner**：`I_FIRE_AGAIN` 保持每 attempt 的 `REACTION_FIRE=(0.4,0.8)`；确认弹窗按钮独立为 0.3~0.6。`interval=2` 仍是跨轮次 Timer 节流；不新增 sleep、Timer、repeat delay 或第二套 FIRE reaction，两个 delay 不会落到同一 click。
- **未改**：`_is_active_battle_entry()`、`RR_AGAIN_MAX_TRIES=4`、`RR_AGAIN_TIMEOUT=10`、`RR_AGAIN_POST_CLICK_TIMEOUT=3`、`RR_TARGET_PACING`、退四、失败策略、Fatigue，以及 GeneralBattle / GeneralInvite / RyouToppa / Orochi / EvoZone / Exploration / Kekkai / Navigation。`check_refresh()` 的同一共享 asset 仍使用既有 `REACTION_CONFIRM`，本轮不改。
- **测试 / Level C**：`tests/test_realm_raid_state.py` `103 → 104`，新增确认按钮 action owner / 独立区间断言；`tests/test_reaction_timing_batch1.py` 更新为锁定两个 owner 分离。静态 / mock 只能证明调用链与 stale-click 防护；真机仍需观察确认弹窗 delay 后仍在才点击、消失则不点，以及两个 reaction 未叠加。

### 4.58 Exploration Boss 直退 / Exit Contract / Chapter FrameWait / Fatigue Safe Point

> **§4.60（2026-09-08）已撤销本节的「Boss 直退 / Treasure bypass / Exit Contract（`_run_boss_exit_transaction`
> 等）」部分——那基于错误的业务需求理解。**当前生效**：Boss 战后走原项目**原生 reward / exit 链**
> （查地图宝箱 → 有则领取 → 不领小纸人 → 原生 `quit_exp_main`），见 **§4.60**。本节的
> **Chapter FrameWait**（§4.58）与 §4.59 的 **Rotation Contract** 独立成立、继续有效。以下描述保留作
> 历史。**

2026-09-08，Level A/B 已实施，Level C 待验。`tasks/Exploration/` 的生产主链从「Boss 战后继续走
`collect_reward()`，优先寻找 / 点击地图宝箱」收口为：

`Boss FIRE → GeneralBattle(result/reward) → battle_won=True → 连续 fresh frame 正向确认 page_exp_main
→ EXIT_READY → I_UI_BACK_YELLOW → EXIT_CONFIRM(I_E_CHECK_EXIT + I_E_EXIT_CONFIRM + I_E_EXIT_CANCEL)
→ I_E_EXIT_CONFIRM → TRANSITION_UNKNOWN 有界等待 → 连续两帧 page_exp_entrance(I_E_EXPLORATION_CLICK)
→ solo Fatigue Safe Point(deadline=start_time+limit_time) → fresh page_exp_entrance revalidate → 下一 cycle`。

- **Boss Completion**：`run_on_battle()` 不再丢弃 `run_general_battle()` 返回值；只有
  `fire_monster_type == 'boss' and battle_won` 才进入 `_complete_boss_business_cycle()`。GeneralBattle
  仍完整拥有 prepare / battle / result / reward Settlement V3；因其 `_handle_missing_battle_page()`
  仍有结算后 2.5 秒 fallback，返回本身不等于地图 ready，故任务层再用 `_wait_for_stable_page()`
  连续两帧正向确认 `page_exp_main`，10 秒未出现抛 `GameStuckError`，不直接退出。
- **Treasure bypass**：Boss production path 不再调用 `collect_reward()` / `collect_treasure_box()`；退出成功后
  `_skip_treasure_once_at_entrance` 阻止 `run_on_exp_entrance()` 立即补领入口宝箱。`collect_treasure_box()`、
  `collect_paper_man_reward()`、`collect_reward()` 与非 Boss / leader / member 的原 consumer 均保留，未做 dead-code
  清理。旧 treasure helper 本体只负责识别、`ui_click` 与奖励页消失等待，不承担次数 / flag / recovery；但
  旧 `collect_reward()` 组合链后的 `collect_paper_man_reward()` 在「Boss 且关闭纸人奖励」时还隐式调用
  `quit_exp_main()`。这项退出触发与「等地图可操作」职责现均由显式 `page_exp_main` ready + Exit Contract
  取代，不再依赖 reward helper 的副作用。
- **Exit Contract**：任务本地 `ExplorationExitState` 明确 `EXIT_READY / EXIT_CONFIRM /
  TRANSITION_UNKNOWN / EXIT_SUCCESS`。退出按钮只在 fresh `page_exp_main` 上经既有 `quit_exp_main()` 执行；
  confirm 复用 `run_on_exp_exit()`；旧 marker / popup 消失都不算成功，唯一成功是
  `page_exp_entrance` 连续两帧正向命中。unknown 只等待、不重按退出；事务 15 秒 timeout 抛
  `GameStuckError`，不静默进入下一 cycle。10/15 秒与连续两帧均 provisional，Level C 校准。
- **Chapter FrameWait**：`open_expect_level()` 的实际 swipe 分支从固定 `sleep(1)` 改为
  `baseline=self.device.image → swipe → wait_for_changed_and_stable → 下一轮 fresh screenshot/OCR`。
  ROI `(1065,203,1189,555)` 由现有章节 OCR `roi=(1065,203,124,352)` 直接换算；参数为 task-local
  provisional：changed `0.02`、stable `0.01`、stable_frames `2`、timeout `1.5s`、poll `0.12s`。
  wait result 不参与章节 success / direction / boundary；stable 或 timeout 都回原 OCR 业务循环，
  `swipeCount >= 25` 仍是收敛上界。未实际发出 swipe 时保留旧 `sleep(1)`，其语义已明确为 OCR / action
  retry throttle，不冒充结构 settle。
- **Fatigue**：只在 `UserStatus.ALONE` 启动 / 触发；leader / member 不接。节点位于 Boss 胜利、地图 ready、
  direct exit、`page_exp_entrance` positive success 全部完成之后，使用真实墙钟 deadline
  `start_time + limit_time`。fatigue 后再次连续 fresh frame revalidate `page_exp_entrance`；下一轮入口跳过旧
  Boss 宝箱后重置 `fire_monster_type`，再由原入口逻辑进入章节，旧 Boss target / frame / coordinate 不复用。
- **不变**：Exploration dynamic `fire(button)` 的 `max_tries=4 + Timer(10) + positive battle page`、普通怪
  搜索 / FIRE / GeneralBattle handoff、GeneralBattle Settlement V3、Navigation、RealmRaid / GeneralInvite /
  RyouToppa / Orochi / EvoZone / Kekkai 均未改。
- **测试**：`tests/test_exploration_state.py` `33 → 48`，覆盖 Boss win/loss、未 ready 不 exit、宝箱 helper
  0 call、confirm / unknown / positive success / timeout、非 Boss helper 保留、solo-only fatigue 顺序与 fresh
  revalidate、FrameWait stable/timeout 都不等于 chapter found。完整回归 `1298 → 1313`。

### 4.59 Exploration Level C hotfix：Boss 直退 success 判据 + 轮换模式归用户所有

> **§4.60（2026-09-08）撤销了本节 Bug B 的整套「Boss 直退 exit transaction」（连同 §4.58 的
> `_run_boss_exit_transaction` / `_is_boss_exit_success_state` / `_boss_exit_probe` /
> `_wait_for_boss_exit_success_state` / `_complete_boss_business_cycle` / `_skip_treasure_once_at_entrance` /
> `BOSS_EXIT_*` / `ExplorationExitState`）——它服务于错误的「Boss 后完全不领地图宝箱直接退出」需求。
> **本节 Bug A（Rotation Contract：`switch_rotate()` 的 `AutoRotate.no` = observe only）独立成立、
> 继续有效**，见 `docs/DECISIONS.md` D021 补记。以下描述保留作历史。**

2026-09-08，§4.58 首次真机 Level C 暴露两个 correctness bug，本轮只修这两个（不重构 §4.58 已实现的
Boss 直退 / treasure bypass / Fatigue / Chapter FrameWait）。`tasks/Exploration/base.py` +
`tasks/Exploration/script_task.py`。长期契约见 `docs/DECISIONS.md` **D021 补记**（Rotation Contract +
Exit Success 多态 positive）。

- **Bug B（Exit timeout，最高优先）**：真机日志 —— `Click RES_E_EXIT_CONFIRM` 之后画面已回到探索页面，
  但 `_run_boss_exit_transaction` 一直 `transition_unknown`，15 秒 `GameStuckError: Exploration boss
  exit timed out in state: transition_unknown`。**根因**：§4.58 的 `_run_boss_exit_transaction` 用
  `detect_page_in(page_exp_main, page_exp_exit, page_exp_entrance, include_global=False)` +「连续两帧
  `page_exp_entrance`（`I_E_EXPLORATION_CLICK`）」为唯一 `EXIT_SUCCESS`。真实退出后停在**探索模式列表
  `page_exploration`（`I_CHECK_EXPLORATION`，`category="global"`）**，被 `include_global=False` 直接
  排除、也不在显式列表里——`_detect_pages` 每帧返回 `None`（Level C 日志里那 11 秒无任何 `[UI]` 行
  即证据），事务对真实 outer 页面全盲。
  - **修复**：新增 task-local 只读 predicate **`_is_boss_exit_success_state()`** =
    `match_page_once(page_exp_entrance) or match_page_once(page_exploration)`——两者都是
    `exec_exp_page` 有 handler（`run_on_exp_entrance` / `run_on_exp`）、也都是
    `check_exit → activate_realm_raid` 认可的合法外层页面。`_run_boss_exit_transaction` 的成功分支
    改用它（连续 `BOSS_EXIT_STABLE_FRAMES=2` 帧 positive）；`detect_page_in` 缩到只判
    `page_exp_main` / `page_exp_exit`（驱动 `EXIT_READY` / `EXIT_CONFIRM`）。**正向 marker 命中，
    绝不以「弹窗 / 主界面标记消失」为成功**（契约不变）。
  - **可观测性**：首次进入 `transition_unknown` + 超时前各打一条 `_boss_exit_probe()`：
    `page_exp_entrance=.. page_exploration=.. page_exp_main=.. page_exp_exit=.. rotate_on=.. rotate_off=..`
    ——下一次 Level C 直接看真实 outer 页面。
  - **`_complete_boss_business_cycle` 的 fatigue 后 revalidate** 从 `_wait_for_stable_page(page_exp_entrance)`
    改为新的 `_wait_for_boss_exit_success_state()`（同样接受入口 或 探索列表）。
  - **treasure bypass 扩到 `page_exploration` 路径**：`run_on_exp()` 的 `ALONE` 分支也读 / 清
    `_skip_treasure_once_at_entrance`（与 `run_on_exp_entrance` 同一 flag、同一 `if not skip_treasure`
    守卫），Boss 直退落在探索模式列表时首次 dispatch 同样不补领地图宝箱。
  - **未调 timeout**：`BOSS_EXIT_TRANSACTION_TIMEOUT=15.0` / `BOSS_EXIT_READY_TIMEOUT=10.0` /
    `BOSS_EXIT_STABLE_FRAMES=2` 一字未动——用户肉眼确认页面早已退出成功，是 detector 错、不是等待
    不够（不「看到 timeout 就 15s→30s」）。
- **Bug A（轮换模式被脚本取消）**：用户手工在游戏里开启「自动轮换」，脚本会把它点关。**根因**：
  `BaseExploration.switch_rotate()` 的 `case AutoRotate.no:` 分支
  `appear_then_click(self.I_E_AUTO_ROTATE_ON, ...)` —— `I_E_AUTO_ROTATE_ON` 是「轮换开着」marker，点它
  = 取消轮换。config `auto_rotate`（title「自动添加候补式神」）默认 `AutoRotate.no`，`switch_rotate()`
  每次在 `page_exp_main` 被 `run_on_exp_main` 调用时就把用户的轮换关掉（为了让地图布局回到脚本
  熟悉的旧样子）。
  - **修复**：`switch_rotate()` 的 `AutoRotate.no` 分支改为 `pass`（observe only）——**脚本绝不点
    `I_E_AUTO_ROTATE_ON` / `I_E_AUTO_ROTATE_OFF` 去取消 / 重置用户的轮换**。`page_exp_main` 的识别
    本就用 `any_of(I_E_SETTINGS_BUTTON, I_E_AUTO_ROTATE_ON, I_E_AUTO_ROTATE_OFF)` 同时覆盖轮换开 /
    关两种布局，不依赖脚本恢复关闭态。`base.py` 随之移除已 dead 的 `REACTION_FAST` import。
  - **`AutoRotate.yes` 不变**：用户显式选「自动添加候补式神」时，脚本仍 `click(C_CLICK_SETTINGS)` →
    `run_on_exp_settings` → `fill_shikigami()` + `appear_then_click(I_E_AUTO_ROTATE_OFF)`（轮换关着时
    打开）——这是用户 opt-in 的「由脚本管理候补 / 轮换」，只做「开」方向、从不「取消」用户已开的轮换。
  - `_exit_matcher()`（GeneralBattle 用）/ `page_exp_main` / `page_exp_settings` 定义 / `run_on_exp_settings`
    的 `no` 分支（只 `goto_page(page_exp_main)`）均未改。
- **未改**：Exploration dynamic `fire(button)`（`max_tries=4 + Timer(10) + positive battle page`）；
  Chapter FrameWait 6 个 provisional 参数；GeneralBattle（Settlement V3 / `_exit_matcher` /
  `is_in_battle` / prepare·result·reward timing）；Fatigue 顺序契约（Exit Success positive → stable
  outer → `try_fatigue_break` → fresh revalidate）；`_wait_for_stable_page(page_exp_main)` map-ready
  门；RealmRaid / GeneralInvite / RyouToppa / Orochi / EvoZone / Kekkai / Navigation。
- **测试**：`tests/test_exploration_state.py` `48 → 66`——`BossDirectExitContractTest` 事务用例改用
  `_is_boss_exit_success_state` / `detect_page_in(main,exit)` 双序列驱动，新增「退出后停在
  `page_exploration` 也算成功」「success 判据是 positive 非 disappearance」「timeout 不放大」；
  `ExplorationFatigueSafePointTest` 改 `_wait_for_boss_exit_success_state` + 新增「exit timeout →
  fatigue 0 call」；新增 `RotationOwnershipTest`（`AutoRotate.no` 不点任何轮换开关 / `yes` 仍管候补 /
  `I_E_AUTO_ROTATE_ON` 全仓不作 click 目标）+ `BossExitSuccessStatePredicateTest`（入口 / 探索列表各
  positive、都不命中不 success、不查 `appear` disappearance、wait helper 连续两帧 + 超时）+
  `RunOnExpTreasureSkipTest`（`run_on_exp` ALONE 一次性跳宝箱 / 正常领 / 两个外层 handler 共用 flag）。
  `tests/test_reaction_timing_batch1.py::ExplorationReactionTest` 同步（`switch_rotate` 不再有轮换
  toggle）。完整回归 `1313 → 1331`（+18，0 regression）。
- **Level C re-test pending**：（§4.59 的 exit-transaction 部分已被 §4.60 撤销，以下大部分不再适用）
  轮换 ON / OFF 时探索外层页面差异仍值得观测；轮换 ON 状态跑完整 Boss cycle 轮换须保持用户原状态。

### 4.60 Exploration Boss Reward Flow 收敛：撤销「Boss 后不领地图宝箱直接退出」错误需求，恢复原生链

2026-09-08。用户重新确认 Exploration Boss 战后的真实业务需求：**不是**「不领任何地图宝箱 → 直接
退出」，**而是**原项目一直以来的「检查地图宝箱 → 有则正常领取 → 无则继续 → 不领取小纸人奖励 →
执行原生退出 → 回外层页面 → 下一轮」。§4.58 + §4.59 基于错误理解新增的 Boss 专用退出结构本轮撤销。
`tasks/Exploration/script_task.py`（唯一生产文件；`base.py` 本轮零改动）。长期契约见
`docs/DECISIONS.md` **D021（标 Superseded）+ D021 corrected 补记**。

- **原项目原生 reward / exit 链（HEAD 一直如此，本轮恢复）**：`Boss 战 → GeneralBattle → 回
  page_exp_main → run_on_exp_main → collect_reward()` = `collect_treasure_box() or
  collect_paper_man_reward()`。
  - `collect_treasure_box()`：`appear(I_E_REWARD_BOX_SMALL)` 小宝箱 / `appear(I_E_REWARD_BOX_BIG)`
    大宝箱 → `ui_click(box, I_REWARD)` + `ui_click_until_disappear(I_REWARD)` 领取，`return True`；
    **无宝箱 → `return False`**（正常继续，不做 treasure action）。可能多次 dispatch（领一个 → 返回 →
    下一轮 page_exp_main 再查），天然处理多宝箱。
  - `collect_paper_man_reward()`（treasure 返回 False 时才走）：**`fire_monster_type == 'boss' and not
    self._config.exploration_config.collect_paper_reward` → `logger.info("Not collect paper doll
    reward")` + `self.quit_exp_main()` + `return True`**——这就是用户要的「打过 Boss + 不领小纸人 →
    原生退出」，**原项目本就有**。否则（收小纸人 / 未打 Boss）出现 `I_BATTLE_REWARD` 时 `ui_get_reward`。
  - `quit_exp_main()` = `appear_then_click(I_UI_BACK_YELLOW, interval=0.8, confirm_delay=REACTION_NAVIGATION)`
    → `page_exp_exit` → `run_on_exp_exit()`（`need_exit=True` → `appear_then_click(I_E_EXIT_CONFIRM,
    ..., confirm_delay=REACTION_CONFIRM)`）→ 游戏退出 → `exec_exp_page` 的 `get_current_page()` 自然
    命中 `page_exp_entrance` / `page_exploration` → `run_on_exp_entrance` / `run_on_exp` 原生接管。
- **自动退出场景（Level C 新发现：某些 Boss 战后无地图宝箱时游戏自动结束探索跳外层页）**：**不新造
  Auto Exit FSM**。原 page-dispatch 天然接管——若游戏已自动离开 `page_exp_main`，`get_current_page()`
  直接返回外层页 → 原生 handler；即便 `page_exp_main` 多留一帧走到 `quit_exp_main()`，
  `appear_then_click(confirm_delay=REACTION_NAVIGATION)` 会在 reaction delay 后**重新截图二次确认
  `I_UI_BACK_YELLOW`**，已消失则不点 —— **天然避免 stale click**（§4.51 Batch A 的 `confirm_delay`
  就是这个语义）。`run_on_exp_exit` 的 `I_E_EXIT_CONFIRM` 同理。**未加任何新的 current-page guard。**
- **撤销的 §4.58 / §4.59 结构**（全仓 consumer audit 后确认只服务错误需求）：`ExplorationExitState`
  枚举、`BOSS_EXIT_READY_TIMEOUT` / `BOSS_EXIT_TRANSACTION_TIMEOUT` / `BOSS_EXIT_STABLE_FRAMES` 常量、
  `_resolved_page` / `_wait_for_stable_page` / `_set_exit_state` / `_is_boss_exit_success_state` /
  `_wait_for_boss_exit_success_state` / `_boss_exit_probe` / `_run_boss_exit_transaction` /
  `_complete_boss_business_cycle` 方法、`_skip_treasure_once_at_entrance` flag（及 `run_on_exp_entrance`
  / `run_on_exp` 里的 skip 守卫，两处 `collect_treasure_box()` 恢复无条件调用）、`run_on_battle` 里
  `battle_won` 捕获与 `_complete_boss_business_cycle` 调用（恢复 HEAD 原生
  `run_general_battle(exit_matcher=page_exp_main)` + `_match_end.refresh()`）。相关 import（`Timer` /
  `GameStuckError` / `Enum`）一并移除。
- **保留（独立成立，本轮不动）**：
  - **Rotation Contract（§4.59 Bug A）**：`switch_rotate()` 的 `AutoRotate.no` = observe only（不点
    `I_E_AUTO_ROTATE_ON` 取消用户轮换）；`AutoRotate.yes` 仍管候补。
  - **Chapter FrameWait（§4.58）**：`_wait_chapter_list_settle` + `EXPLORATION_LEVEL_*` 6 个 provisional
    参数，PARTIAL / Level C calibration pending，**未动**。
  - **solo Fatigue 能力**：`run()` 里 `begin_fatigue_task('Exploration')`（ALONE）保留。Safe Point
    **重新挂在原生完整 cycle 的外层稳定页**：新增 `_maybe_boss_cycle_fatigue()`，在
    `run_on_exp_entrance` / `run_on_exp` 顶部调用——这两个 handler 只在 `get_current_page()` 正向命中
    `page_exp_entrance` / `page_exploration` 时才分发（= 已在合法外层稳定页），且仅当刚完成的是
    Boss 循环（`fire_monster_type == 'boss'`，handler 稍后才重置它）+ `user_status == ALONE`；命中即
    `try_fatigue_break(safe=True, repeat_completed=True, deadline=start_time+limit_time)` + 消费 Boss
    标记（避免重复）+ 让调用方 `return`（交 `exec_exp_page` 下一轮 fresh screenshot + 重新分发 =
    fatigue 后 fresh revalidate）。**不在 `page_exp_main` 触发**（宝箱 / 小纸人 policy / 退出未完成）。
  - `fire(button)`（`max_tries=4 + Timer(10) + positive battle page`）、`run_on_exp_settings` /
    `run_on_exp_exit` / `open_expect_level` 的 §4.51 `confirm_delay` reaction、`_exit_matcher()`、
    GeneralBattle、普通怪 handoff、其它任务全未改。
- **测试**：`tests/test_exploration_state.py` `66 → 56`。**删**（对应已废弃的错误 contract）：
  `BossDirectExitContractTest` 全类（12：`_run_boss_exit_transaction` / `_is_boss_exit_success_state` /
  `_skip_treasure_once_at_entrance` / `BOSS_EXIT_*` / EXIT 状态机 + 「Boss 后 treasure 0 call」）、
  `BossExitSuccessStatePredicateTest` 全类（6）、`RunOnExpTreasureSkipTest` 全类（3）、
  `ExplorationFatigueSafePointTest` 里依赖 `_complete_boss_business_cycle` 的 3 个。**加**：
  `BossRewardFlowNativeTest`（8：无 Boss exit 结构残留 / `run_on_exp_main` 用原生 `collect_reward` /
  `collect_reward` = treasure or paper-man / 「不领小纸人 + Boss」走原生 `quit_exp_main` 且 treasure
  领取分支仍在 / `collect_treasure_box` 有则领取无则 False / `run_on_exp_entrance` · `run_on_exp` 无条件
  `collect_treasure_box` 无 skip flag / `quit_exp_main` 靠 `confirm_delay` 天然 stale-safe 且无新 exit
  transaction）+ `BossCycleFatigueTest`（7：solo Boss 循环触发 fatigue + 消费标记 / 非 Boss·非 solo 不
  触发 / 外层 handler 顶部先 safe point 再 treasure 且命中即 early return / 不在 page_exp_main 触发 /
  `begin_fatigue_task` 只 solo）。`GeneralBattleHandoffTest::test_run_on_battle_*` 改锁原生 handoff。
  完整回归 `1331 → 1321`（−10 全为删掉的废弃 contract 用例，0 regression）。
- **Level C re-test**：场景 A（有地图宝箱）Boss Win → treasure 正常领取 → 不收小纸人 → 原生 exit →
  outer page；场景 B（无地图宝箱）Boss Win → 无 treasure → 游戏自动退出 / 原生退出 → **不产生 stale
  `I_UI_BACK_YELLOW` / 错误 exit confirm** → page-dispatch 接管 outer page。两场景轮换模式都保持用户
  原状态；solo Fatigue 只在回到外层稳定页后触发。

### 4.61 普通滑动端点空间分布 v2（`SwipeEndpointSampler`，D022）

**问题**：OASX 行为统计显示同类 `swipe` 的**起点挤成一簇、终点挤成一簇、轨迹高度重合**——
`TouchSwipeModel` 中段曲线每次都变，但上层给它的起终点几乎固定。根因不是「起终点共享同一个
平移量」（`RuleSwipe.coord()` 本来就对 `roi_front` / `roi_back` 各采一次），而是大量 swipe 资产的
`roi_front` / `roi_back` 只有 ~21×21 甚至 4×4 / 2×4，`random_center_point_in_roi` 的 Bates 均值在
这么小的框里有效标准差只有 3~6px。

**方案（Level A/B，本轮落地）**：新增端点采样层 `module/atom/swipe_endpoint.py`，与 `ClickSampler`
同构：

- `sample_swipe_endpoints(roi_front, roi_back)` —— 起终点**各自独立**采样（不共享平移），
  参照点 = 各 ROI 整数取值范围几何中点；「游走尺度」由业务基准距离（两 ROI 中点距离）
  按比例（`offset_dist_ratio=0.12`）推出、夹 `[6, 40]px`；主成分（`core_weight=0.85`）窄高斯
  + 尾部（0.15）宽高斯，按轴采样；夹到 `[preferred ± hard_half] ∩ 屏幕安全边界`，越界有限
  次 rejection → 回退轴中心。
- **轴向 ROI `>= wide_axis_px=48`** 的轴逐字保持旧 `_center_biased_int`；**两端两轴都大 →
  整条 short-circuit == 旧 `coord()`**（`S_BATTLE_RANDOM_*` 480×426 / Summon `S_RANDOM_SWIPE_*`
  100~480px 分布字节级不变）。
- **联合校验**：采样向量与业务向量夹角 `<= ~25°`（`min_cos=0.906`）、距离 ∈ `[0.55, 1.45] ×
  基准` 且 `>= 10px`（避开 `swipe_trajectory` 的 <10px 端点回退）、业务主轴符号一致；不满足
  整体重采样，`joint_max_attempts=6` 用尽 → 确定性回退 `(preferred_start, preferred_end)`。
  **有界，无 `while True`。**
- 接线：`RuleSwipe.sample_endpoints()`（委托）；`BaseTask.swipe` 的 `swipe.coord()` →
  `swipe.sample_endpoints()`（唯一改动点，~50 个 `self.swipe(S_*)` consumer 透明迁移）。
  **`RuleSwipe.coord()` 本体不改**（保留给兼容 / 测试 / 回归对比）。**`TouchSwipeModel` 中段
  轨迹算法一字未改**（端点分布与中间轨迹正交，不同时改）。BehaviorTrace 天然记录真实采样端点
  （`swipe_trajectory` 的 extra 取自 `TouchSwipeModel.generate` 精确首末点），未改
  `behavior_trace.py` / `Control`。
- 未迁：`list_find` 翻页（D013）/ KekkaiUtilize K1~K4 自建端点 / `KekkaiActivation` `swipe_adb`
  直连 / `RyouToppa.flush_area_cache`（`duration=`）/ drag / press-and-drag / 摇杆。

**统计核对（20k 样本 / 资产）**：`S_SWIPE_LEVEL_UP`（21×21）起点 sd `~4 → ~9`、距离仍
`116±13`、方向不反；`S_BATTLE_RANDOM_LEFT`（两端两轴都宽）起点 sd `~80`、距离 `545±110`——
与旧 `coord()` 均值 / sd 一致（delta < 3）；全仓 ~50 个 swipe 资产（含 1px / 2px / 贴角 ROI）
采样不崩、主轴方向不反。

- **改动文件**：`module/atom/swipe_endpoint.py`（新，`??`）、`module/atom/swipe.py`
  （`+sample_endpoints()`，`coord()` 保留）、`tasks/base_task.py`（`BaseTask.swipe` 1 行）、
  `tests/test_swipe_endpoint_sampling.py`（新 36，`??`）、`tests/test_base_task_swipe_trajectory.py`
  （`test_swipe_delegates_...` 改 patch `sample_endpoints`，计数不变）。
- **回归 `1321 → 1357`**（+36 全为 `tests/test_swipe_endpoint_sampling.py`）。`compileall` OK、
  `git diff --check`（本轮改动文件）干净。

**Level C 收口（2026-09-08，`docs/DECISIONS.md` D022 Level C 补记）—— D022 = Level C PASS / 当前默认冻结**：

用户连续多轮 MuMu 真机运行，通过 OASX「统计 → 点击位置与滑动轨迹」页连续观察真实执行的
start / end / trajectory（BehaviorTrace 最终数据）。最新一日样本约「点击 590 / 滑动 42」，观察到：

- 同类横向 swipe 起点不再钉死为单点，形成**明显但仍集中**的小范围 endpoint cloud；终点同样
  形成独立的小范围分布；start / end 不是简单共用同一整体 offset。
- 多条横向 trajectory 不再完全重合（有轻微高度差 / 角度差），主方向仍非常明确，**无视觉上明显
  的反向 swipe**。
- 未观察到极端短 / 极端长 swipe、大角度错误斜滑、endpoint 大面积飞散；同图的一组纵向 swipe 也无异常。
- 连续使用未报告：误触 UI / 滑不动 / 滑过头 / 业务状态错误 / Kekkai 回退 / Exploration swipe 回退。

用户判断「看样子可以」，确认进入收口。**结论**：这是**当前 ordinary swipe 业务下的 Level C
真机行为验收通过**，不是「大规模统计学参数拟合完成」或「所有未来业务 swipe 的永久最优参数」。
`SwipeEndpointParams` 当前默认值**在无新真机反例前冻结**，**本轮禁止继续调参**（不扩大 sigma /
tail 概率 / hard_half / 角度界 / 距离比 / joint attempts——「解除固定 endpoint + 保持业务稳定」
已达成，继续扩散只会增加误触 / 危险区 / scroll 漂移 / OCR·FrameWait 收敛变化风险）。
**本轮为 Level C status / documentation closeout，未改任何生产代码 / 测试**，沿用上一轮
`1357/1357` 已验证基线（本轮另重跑 swipe endpoint targeted `62 OK` 复核）。

**重新打开条件**（否则 D022 保持 closed）：某页面 swipe 误触 / 某业务 swipe 距离不足 / 某业务
明显过滑 / start·end 落入危险控件 / direction guard 失败 / BehaviorTrace 与实际执行不一致 /
新统计图重新出现极端 endpoint 聚集 / 某特殊 consumer 被错误接入公共 sampler。

### 4.62 ActivityShikigami 当期普通爬塔线适配（入口 / FIRE / Fatigue / 活动结算弹窗，Level A/B）

**背景**：用户高频重复刷「式神活动」爬塔。上一轮 READ ONLY 审查（`docs/DEVELOP_LOG.md` 同名条）
定位到 `tasks/ActivityShikigami`（前端「式神活动」/「当期爬塔」，`config` 名 `activity_shikigami`，
production 注册）框架成熟但资产陈旧、FIRE 契约弱、无 Fatigue。用户随后重截了本期爬塔资产并给了
真机事实：本期**无**挑战按钮置灰态 / **无**资源不足弹窗 / **无**购买确认弹窗（资源不足仅一闪
而过 ~1s 提示文字）；战斗结束是一个「活动专用结算弹窗」（不是旧通用胜负结果页），可安全套用
GeneralBattle Settlement V3 的 `C_RANDOM_DEFAULT`（`random_default`）大安全区推进。

**本轮范围**：只适配 `NormalClimbAct` 普通爬塔高频刷取。大富翁 / 伪神降临线不改（`_fatigue_owns_macro_idle`
只在 `run_climb` 置位、FIRE / settlement drain 都是 `NormalClimbAct` task-local）。

**用户已放入仓库的新资产**（本轮由用户提供，AI 未截图）：`as/page/page_main_goto_act_2.png` +
`assets.py` 新 `I_MAIN_GOTO_ACT_2`（roi_front `(726,280,38,35)`）；`as/climb/*` 重截 + ROI 调整
（`I_ACT_FIRE` / `I_CHECK_BATTLE_PASS` / `I_CLIMB_MODE_*` / lock·penta 图标）；`as/climb/ocr.json`
`O_REMAIN_AP` / `O_REMAIN_PASS` / `O_REMAIN_PENTA_PASS` 的 `roiFront` 迁到本期布局；
`as/climb/pages.json` `I_TO_BATTLE_MAIN` / `I_TO_BATTLE_BOSS` ROI 换新。**未提供活动结算弹窗
专用 marker**——本轮结算靠既有 `BaseAct.before_run` 把 `I_UI_BACK_RED` 并入 `page_battle_result`
recognizer + 新增有界 `_drain_activity_settlement` 兜底，不新造假 marker。

**代码改动（3 文件，task-local，未碰 GeneralBattle / 其它任务）**：

- **入口**（`page.py`）：新 `goto_activity_entry(task)` 作 `page_main → page_act` 边动作——优先
  `appear_then_click(I_MAIN_GOTO_ACT_2, interval=1, confirm_delay=REACTION_NAVIGATION)`，旧
  `I_MAIN_GOTO_ACT` 作跨活动周期回退（两图标都在 `assets.py`，旧图标不删）；`_activity_entry_visible`
  合并二者，`find_activity_entry` 两处 `appear(I_MAIN_GOTO_ACT)` 检查改用它。入口图标消失**不**代表
  进入成功——仍由 `page_act` positive marker 判定。
- **二层爬塔入口 page graph（2026-09-10，真机确认本期链）**：真实链是 `page_act
  --I_TO_BATTLE_MAIN--> page_climb_main（中间「进入爬塔」页）--I_TO_BATTLE_MAIN_2-->
  page_climb_ap / page_climb_pass`，不再是旧的 `page_act` 直连 climb 页。用户新增资产
  `I_TO_BATTLE_MAIN_2`（`climb_to_battle_main_2.png`，252×80「战斗·<本期名>」按钮，`roi_front=(11,92,252,80)`）
  + `I_CHECK_BATTLE_PASS_2`（`climb_check_battle_pass_2.png`，本期爬塔页标题横幅，ROI 同旧
  `I_CHECK_BATTLE_PASS`）。落地：① `page.py` 新增 task-local 中间页 `page_climb_main =
  Page(I_TO_BATTLE_MAIN_2)` —— 用该页**稳定存在**的进入按钮作 positive marker（不是「上一页按钮
  消失」），它同时是 `page_climb_main → page_climb_*` 的边动作；`page_climb_main.connect(page_act,
  I_UI_BACK_YELLOW)` 作 recovery；② `page_climb_ap` / `page_climb_pass` recognizer 从
  `all_of(I_CHECK_BATTLE_PASS, MODE)` 改为 `all_of(any_of(I_CHECK_BATTLE_PASS_2, I_CHECK_BATTLE_PASS),
  MODE)` —— 本期新 marker primary + 旧 marker legacy fallback，仍 `all_of` 带 mode 保证与中间页
  互斥（只 `I_TO_BATTLE_MAIN_2` 时 climb 页 recognizer 为假，静态验证过）；climb 页 yellow-back 边
  重定向到 `page_climb_main`（`climb → climb_main → activity`）；③ `normal.py::setup_climb_pages`
  的 `page_act →(I_TO_BATTLE_MAIN) climb_ap/pass` 两条直连边换成 `page_act →(I_TO_BATTLE_MAIN)
  page_climb_main` + `page_climb_main →(I_TO_BATTLE_MAIN_2) climb_ap/pass`；mode 切换
  （`I_CLIMB_MODE_SWITCH` + `conditional_action` enter-failure hook）不变。**business boundary 天然
  保持**：`_run_climb_type` 的业务分支仍 `if current_page == destination:`（= `page_climb_ap/pass`，
  recognizer 需 `I_CHECK_BATTLE_PASS_2/PASS` + mode），中间页只有 `I_TO_BATTLE_MAIN_2` 不满足 →
  Fatigue / resource OCR / FIRE / settlement 都不会在中间页触发。**未改** `page_act` recognizer /
  priority / threshold / ROI，未改 FIRE / REACTION_FIRE / Fatigue / Challenge Ready / Resource OCR /
  Settlement / GeneralBattle。`page_climb_ap100` / `page_climb_boss`（非本期 production 路径，
  ap/pass 之外）edge 未动 —— boss 是否也有中间页 = Level C 另查。`tests/test_activity_shikigami_climb.py`
  `46 → 58`（+12 `SecondLayerClimbEntryTest`）。
- **窄 New Battle Entry Detector**（`base_act.py`）：新增 `BaseAct._is_active_battle_entry()` =
  `is_in_prepare(False) or is_in_real_battle(False)`（复用 GeneralBattle 已有窄 detector，`is_in_battle()`
  本体不动）——本期活动结算弹窗不能被宽 `is_in_battle()`（含 `I_FALSE` / `I_WIN` / `I_REWARD`）
  误判成「新战斗已开始」，同 D001 补记「Battle Lifecycle Detector ≠ New Battle Entry Detector」/
  RealmRaid `_is_active_battle_entry()`。
- **FIRE Contract 收口**（`normal.py`）：`_enter_climb_battle` 从旧 `while True` + `is_in_battle(False)`
  + 仅 `random.randint(3,5)` 次点击 改为 bounded battle-entry transaction——`_classify_climb_fire_state`
  三态（`battle` = `_is_active_battle_entry()` / `ready` = 挑战键可见 / `unknown` = 过渡帧）+
  `_wait_climb_fire_state` 有界轮询（`'timeout'` 不当成功也不当失败）；每 attempt 独立
  `random_delay(*REACTION_FIRE)` → `sleep` → fresh `screenshot` → 二次确认挑战键仍在才点，reaction
  期间离开 ready / 按钮消失 → 不点旧坐标；`for attempt in range(1, ACTIVITY_FIRE_MAX_TRIES+1)` +
  `Timer(ACTIVITY_FIRE_TIMEOUT)` + `ACTIVITY_FIRE_POST_CLICK_TIMEOUT` 三重有界，用尽 → `return False`
  → caller 转 `ActivityResourceNotEnough`。常量 `= (4, 12, 4)`，**PROVISIONAL**（对齐 GeneralInvite
  `GI_FIRE_*` / RealmRaid `RR_FIRE_*` 量级，非 Level C 标定）。
- **Challenge Ready = Fatigue Safe Point**（`normal.py`）：新增 `NormalClimbAct._activity_challenge_safe_break(
  action_type, destination, *, repeat_completed)`——**唯一** `try_fatigue_break` 调用点（task-local，
  不影响大富翁 / 伪神）：fresh screenshot → 当前页 == destination 且挑战键 positive → `try_fatigue_break(
  safe=True, repeat_completed=..., deadline=start_time+limit_time_v)` → 若真的休息 / 发呆过：结束后
  fresh screenshot 重新确认「仍在挑战页 + 挑战键仍在 + 资源 OCR 仍允许」，页面变化 → 返回 False（不点
  旧坐标），资源在休息期间耗尽 → `raise ActivityResourceNotEnough`。`repeat_completed` 首轮 `False`、
  一场 battle + 活动结算 drain 完整跑完后 `cycle_completed = True`（cycle 边界 = 「结算已处理 + 回到
  稳定挑战页 + Challenge Ready positive」，不是「结果页出现」也不是「弹窗消失」）。
- **macro-idle owner**（`base_act.py`）：新增实例标记 `_fatigue_owns_macro_idle`（`run_climb` 置 True +
  `begin_fatigue_task('ActivityShikigami')`）；`prepare_next_action` 的 `random_sleep` 改成
  `if random_sleep_cfg and not self._fatigue_owns_macro_idle:` —— 爬塔线把宏观空闲交给 Fatigue，
  大富翁 / 伪神线仍 `random_sleep`。同一 cycle 不再出现两个 macro-idle owner。
- **活动结算弹窗**（`normal.py`）：新增有界 `_drain_activity_settlement(action_type, destination)`——
  `run_general_battle` 返回后调用：直到 `get_current_page() == destination` 且挑战键可见（= cycle
  complete）或 `ACTIVITY_SETTLEMENT_MAX_CLICKS` / `Timer(ACTIVITY_SETTLEMENT_TIMEOUT)` 用尽；每次点
  `self._sample_settlement_click(self.C_RANDOM_DEFAULT)`（**复用** GeneralBattle Settlement V3 采样，
  不新造坐标 / 区域），间隔 `random_delay(*self.SETTLEMENT_CLICK_INTERVAL_RANGE)`。**弹窗消失本身不算
  成功**，必须重新识别到挑战页 + 挑战键 positive。又落回战斗态 → 返回 False 交回外层。常量 `= (6, 15)`
  PROVISIONAL。GeneralBattle Settlement V3 / `_settlement_click` / region 选择 **一字未改**。

**未改**：`RichManAct` / `FakeGodAct`（含 `_enter_fakegod_battle` 的旧 `while True`）、`GeneralBattle`
（含 Settlement V3、`is_in_battle` / `_handle_result` / `_exit_matcher`）、`before_run` 的
`page_battle_result` recognizer monkeypatch（记 P1 技债，本轮爬塔适配不依赖它改动）、其它任务。

**测试**：新增 `tests/test_activity_shikigami_climb.py`（46：入口新旧图标优先级 + navigation reaction、
`_is_active_battle_entry` 窄语义、FIRE 三态 + bounded（fire 不出现 / reaction 期间消失 / post-click
持续 unknown 都有界、无 stale click）、Fatigue safe break（首轮 `repeat_completed=False` / 休息后
fresh revalidate / 休息中资源归零 raise / 唯一调用点）、macro-idle 无 stack、settlement drain 复用
`C_RANDOM_DEFAULT` + 有界 + 正向确认回挑战页、cycle-complete 边界、RichMan/FakeGod/GeneralBattle
未改）+ `SecondLayerClimbEntryTest`（12，2026-09-10 二层爬塔入口：`page_climb_main` 自有 positive
marker / 中间页 vs climb 页互斥不靠 priority / climb 页 recognizer 新 primary + legacy fallback +
带 mode / `setup_climb_pages` 两层边 / business 只在真正 climb 页跑 / `page_act` recognizer·priority
未动）。**回归 `1357 → 1403 → 1415`（+46 + 12，0 regression）**；`compileall` OK；`git diff --check`
干净。

**Level C 待验**（用户手动跑普通爬塔连续 5~10 轮）：① 庭院 `main_goto_act_2` → `page_act` positive
→ `I_TO_BATTLE_MAIN` → `page_climb_main`（中间页，positive = `I_TO_BATTLE_MAIN_2`）→ `I_TO_BATTLE_MAIN_2`
→ 真正爬塔页 positive = `I_CHECK_BATTLE_PASS_2` + mode（先确认这条二层导航链跑通、无 unknown recovery
退回庭院、climb 页 yellow-back 走 `climb → climb_main → activity` 正确；boss / ap100 是否也有中间页）；
② Challenge Ready 识别 + Fatigue **只在**挑战 ready 时触发、休息后 fresh revalidate；③ FIRE reaction
0.4~0.8、不重复 FIRE、窄 detector 不把活动结算弹窗误判为新战斗；④ 活动结算弹窗 `random_default` 点击
安全、有界回到挑战页；⑤ 资源 OCR（新 ROI）读数正确、resource 0 后不再 FIRE 优雅停止；⑥ 无无限循环；
⑦ `ACTIVITY_FIRE_*` / `ACTIVITY_SETTLEMENT_*` PROVISIONAL 数值是否合适。**未接大富翁 / 伪神降临。**

### 4.63 RealmRaid `_fire_again()` 最后一次 attempt timing bug —— Level C hotfix

**真机失败事实**：退四（`exit_four`）首战主动退出、`Lose` 之后 `RES_FIRE_AGAIN → RES_SHOW_AGAIN →
RES_FRESH_ENSURE`，游戏已实际进入 `page_battle_prepare`（右下角「准备」按钮正常出现），但日志：

```
Fire again: attempt 4, reaction 0.77s
Fire again: button gone during reaction, re-evaluate
WARNING | Fire again: bounded retry / timeout without entering battle
```

`_fire_again()` 判超时 `return False`，`run()` 的 `aborted` 分支走 `check_refresh()`（只认 RealmRaid
九宫格「刷新」按钮，在活的战斗准备页上必然不存在 → 单帧快速 False）后 `success=False; break`，任务
异常遗留在 `page_battle_prepare`。

**根因（READ ONLY 定位已确认，非 success state 缺失）**：`_is_active_battle_entry()` =
`is_in_prepare(False) or is_in_real_battle(False)` 与 `page_battle_prepare` 的页面 recognizer 逐字
同源，`page_battle_prepare` 本来就是合法 positive state。真正问题是 `_fire_again()` 里「reaction 后
fresh screenshot 发现 `I_FIRE_AGAIN` 已消失」这条分支此前是裸 `continue`，没有像它的兄弟分支（点击前
「未就绪」）那样先调用已有的 `_wait_again_entered_battle()` 有界确认。非最后一次 attempt，这个缺口被
下一轮循环顶部的 `_is_active_battle_entry()` 隐式补一次确认掩盖；但 `attempt == RR_AGAIN_MAX_TRIES`
（最后一次）没有下一轮，`for` 循环直接耗尽退出——如果这一刻恰好是「按钮已消失、`page_battle_prepare`
marker 尚未渲染完成」的真实过渡帧，就会直接判超时，白白丢弃一次本该成功的「再次挑战」。

**修复（唯一生产改动，`tasks/RealmRaid/script_task.py::_fire_again`，一处分支）**：

```python
if not self.appear(self.I_FIRE_AGAIN, threshold=0.8):
    logger.info('Fire again: button gone during reaction, re-evaluate')
    state = self._wait_again_entered_battle()
    if state == 'battle':
        logger.info('Fire again: entered battle')
        return True
    continue
```

复用既有 `RR_AGAIN_POST_CLICK_TIMEOUT`（未新增 timeout 常量）。**严格未改** `_is_active_battle_entry()`
/ `is_in_prepare()` / `is_in_real_battle()` / `is_in_battle()`——`_fire_again` 仍用窄 detector，不因这
次真机证据回退成宽 `is_in_battle()`（失败结算页 `I_FALSE` 会让宽 detector 恒 True，见 §4.56 / D001
补记「Battle Lifecycle Detector ≠ New Battle Entry Detector」，这条既有设计本轮继续遵守）。**同源但
本轮明确不修**：`fire()`（RealmRaid 所有目标共用的首次挑战入口）里「reaction 期间 FIRE 消失」分支
（`RR_FIRE_*`）有完全相同的裸 `continue` 结构，当前 Level C 证据只指向 `_fire_again()`，按最小范围本
轮不动；`aborted` 后 `page_battle_prepare` recovery / `run_general_battle` quick_exit fallback /
navigator `page_battle_prepare` edge / `close_unknown_pages` GB_EXIT closer 均**未新增**——本修复让
attempt 4 能正确识别 `page_battle_prepare` 并 `return True`，从根本上不再走到 `aborted` 分支，因此
`run()` 侧的这层兜底本轮不需要动。

**测试**：新增 `tests/test_realm_raid_state.py::FireAgainLastAttemptReactionGoneTest`（3：CASE 1 核心
回归——最后一次 attempt 的 gone 分支 `_wait_again_entered_battle()` 返回 `'battle'` → `_fire_again()`
必须 True 且不落到 bounded timeout warning；CASE 2——`_wait_again_entered_battle()` 一直不给 `'battle'`
→ 仍 bounded False、调用次数恰好 = `RR_AGAIN_MAX_TRIES`，不形成无界循环；源码形态锁定 gone 分支必须
调用 `_wait_again_entered_battle()` 且认可其 `'battle'` 返回，防止本修复被静默回退）。`_is_active_battle_entry()`
窄语义（失败结果页 / `I_FALSE` 不当新战斗）已有 `ActiveBattleEntryContractTest` 完整覆盖，未重复造同
义测试。回归 **1415 → 1418**（+3，0 regression）；`compileall` OK；`git diff --check` 干净。

**Level C 待验**：修复后的「reaction 后按钮消失」分支在真机上是否确实能在
`RR_AGAIN_POST_CLICK_TIMEOUT=3` 内等到 `page_battle_prepare` 渲染完成（本轮判定为过渡帧窗口，未改
这个常量）；`fire()` 是否也需要同样收口（若真机再见类似「最后一次 attempt 被裸 continue 吞掉」现象）。

### 4.64 KekkaiUtilize Scheduler v1 —— 静默窗口 + 短期 retry cooldown 随机化

**背景**：上一轮 READ ONLY Inventory（`docs/DEVELOP_LOG.md` 同名条）已还原真实调度链——`set_next_run`
只是 `Config.task_delay()` 的薄包装；KekkaiUtilize 当前 5 处出口各自硬编码 5/10/20 分钟或 OCR 剩余
时间；项目已有 AntiBan 全局睡眠窗（`script.py::_in_sleep_window`/`_next_time_point`，内存覆盖、无
持久化）与 Server-Update 全局阻塞窗（`tasks/Restart/server_update.py`，`task_delay(target=)` 持久化、
无 jitter）两条"时间窗"先例，但都不是"单任务 + 有 jitter"。本轮落地 KekkaiUtilize 专属版本。

**最终调度契约**：

```
正常寄养：OCR 剩余时间 → min_run_interval 地板 → _normalize_quiet_target → set_next_run(server=False)
短期 retry：_build_retry_target（随机 5~30min cooldown） → _schedule_target（同一次 normalize）
           → set_next_run(server=False)
run() 入口：_guard_quiet_window（静默窗口内立即重排 + TaskEnd，不进任何页面/OCR/业务动作）
```

**新增纯函数模块**（`tasks/KekkaiUtilize/scheduling.py`，无设备/OCR/task config 依赖，独立实现，
不 import `script.py`）：`is_in_quiet_window(t, start, end)`（`[start,end)` 半开区间，`start>=end`
自动按跨午夜处理）、`next_quiet_window_end(now, end)`（下一个窗口结束时刻，已过则顺延明天）、
`normalize_for_quiet_window(candidate, *, enable, quiet_start, quiet_end, jitter_seconds)`
（candidate → 归一化后的 final，`jitter_seconds` 由调用方预采样传入，本函数 100% 确定性）。

**`ScriptTask` 新增 7 个 task-local helper**（`tasks/KekkaiUtilize/script_task.py`）：
`_is_in_quiet_window` / `_quiet_jitter_seconds` / `_normalize_quiet_target`（近纯函数，不调
`set_next_run`）/ `_build_retry_target`（`now + random_int(cooldown_min*60, cooldown_max*60)`，
统一随机源）/ `_schedule_target`（candidate → normalize → `set_next_run(target=final, server=False)`
唯一持久化出口）/ `_schedule_retry`（短期失败统一出口，一个 owner 一次随机）/ `_guard_quiet_window`
（`run()` 入口守卫）。

**5 处退出改造**：① `check_utilize_add` 5 次未达标（旧 `target=now+5min` 硬编码）→
`_schedule_retry`；② `check_utilize_add` 已在寄养（OCR 剩余时间，**保留不变**，只是原 `set_next_run`
换成 `_schedule_target` 接入静默窗口归一化，`min_run_interval` 地板逻辑逐字未动）；③
`_record_utilize_failure` 连续 3 次失败（旧 `target=now+10min`）→ `_schedule_retry`；④
`_finish_low_value_utilize` 跨区+同区都无达标候选（旧 `target=now+20min`）→ `_schedule_retry`，
日志改为明确"目标卡种 + 收益阈值"（不再写模糊的"没有卡"）；⑤ `utilize_enable=False` 的通用
`success_interval=6h` 路径**本轮不改**（用户明确要求不动其间隔语义；它走 `task_delay` 的
`success=True` 相对区间分支而非自算 target，硬套 normalize 需要重新实现区间换算，不做）。

**`server` 参数**：核对过 5 个出口后，全部改为显式 `server=False`——`UtilizeScheduler` 未覆盖基类
`float_time` 默认值 `Time(0,0,0)`，之前隐式 `server=True` 时 `task_delay` 里的 `server_update` jitter
叠加恒为 0 秒（无业务依赖），现在做成显式，若未来用户把 `float_time` 配置成非零值也不会再意外污染
这几个已经算好的 target。

**配置**（`tasks/KekkaiUtilize/config.py::UtilizeScheduler`，继承 `Scheduler`）：新增
`quiet_window_enable=True` / `quiet_start=Time(0,0,0)` / `quiet_end=Time(7,0,0)`（类型沿用
`AntiBan.sleep_start/sleep_end` 同一套 `Time`，不发明新 time-range 类型）/
`quiet_resume_jitter_min=5` / `quiet_resume_jitter_max=30` / `cooldown_min=5` / `cooldown_max=30`
（均分钟 `int`）。边界校验用 `field_validator('cooldown_max'/'quiet_resume_jitter_max', mode='after')`
+ `info.data` 取兄弟字段——**不用** `model_validator(mode='after')`：`ConfigBase.__init__` 的异常恢
复靠 `exc.errors()[0]['loc'][0]` 取越界字段名做默认值回退，`model_validator` 产生的模型级错误
`loc` 为空元组会让它 `IndexError` 崩溃（本轮实测复现，改用 `field_validator` 后验证通过）。

**随机源**：`_quiet_jitter_seconds`/`_build_retry_target` 均调用 `module.base.utils.random.random_int`
（`SystemRandom`），未引入 stdlib `random.Random()`；`Config.task_delay()` 里既有的 stdlib
`random.randint` jitter（`server_update` 分支）本轮未动、未复用其写法。

**测试**：新增 `tasks/KekkaiUtilize/scheduling.py` 纯函数测试 `tests/test_kekkai_utilize_scheduling.py`
（16：`is_in_quiet_window`/`next_quiet_window_end` 边界 + `normalize_for_quiet_window` CASE A~H 全覆盖，
含跨午夜窗口）；`tests/test_kekkai_utilize_state.py` 新增 5 个测试类（19）：`SchedulingHelperUnitTest`
（7，task-local helper 读 config / 调统一随机源）、`NoEligibleCardRetryExitTest`（3，含落窗场景
"23:55 完成 cooldown 20min → 次日 07:10"）、`NormalUtilizeSchedulingTest`（3，OCR 剩余时间落窗/不落窗/
min_run_interval 地板三种）、`RunEntryQuietGuardTest`（2，quiet 内拦截 + quiet 关闭不拦截）、
`RetrySingleOwnerTest`（4，三个短期失败出口都走 `_schedule_retry`、源码级锁定不各自调
`random_int`）。回归 **1418 → 1453**（+35，0 regression）；`compileall` OK；`git diff --check` 干净
（`docs/DEVELOP_LOG.md` 既有 2 处 trailing-whitespace 是早前轮次遗留，本轮未清理）。

**未改**：好友列表扫描 / 卡种筛选 / 收益阈值 / OCR / `check_utilize_harvest`（不领奖，下一轮）/
`check_max_lv`（满级检查+替换，下一轮）/ `goto_page` 失败 U3 技债（**已于 §4.68，2026-09-14
修复**）/ `Script.get_next_task()` / AntiBan / 通用 `TaskScheduler` / RealmRaid。

**Level C 待验**：00:00~07:00 静默窗口内 KekkaiUtilize 确实不会被真正启动（观察实际任务开始时间戳）；
正常寄养后 `next_run` 仍符合 OCR 剩余寄养时间语义（quiet 归一化不改变非落窗场景的值）；短期 retry 的
5~30 分钟随机分布体感；`quiet_resume_jitter_min/max`、`cooldown_min/max` 默认值是否合适。

### 4.65 KekkaiUtilize 业务开关配置：满级检查/替换新增开关，寄养奖励沿用既有字段，OASX 0 修改

**背景**：用户下一步要落地「寄养结束后不领奖」「不再检查满级/替换」两项业务简化（§4.64 末尾已定位
入口）。本轮先确认这两项是否能只靠**新增/沿用配置字段**实现"旧能力保留、默认行为可关"，而不是直接
删代码；并先 READ ONLY 核实 OASX（`d:\oas_xy\OASX`）是否会自动渲染后端新增的 `bool` 字段，只有确认
不能自动显示才允许改前端。

**OASX 渲染机制核实结论（详见 `docs/DECISIONS.md` D024）**：OASX 任务配置面板是**完全通用**的
schema-driven 表单——`TaskParameterPanel → Args(lib/modules/args/) → ArgsController.loadGroups() →
ApiClient().getScriptTask() → ArgumentModel.fromJson() → ArgumentView` 按 `model.type` 字符串分发
控件（`'boolean' => Checkbox`），`type` 字符串直接来自后端 `task.model_json_schema()`
（`module/config/config_model.py::ConfigModel.script_task`）。全仓 grep "kekkai" 在 OASX 里只命中
菜单 i18n 与 BehaviorTrace 展示名，**没有 KekkaiUtilize 专属配置页面**。任何 `ConfigBase`/
`BaseModel` 子类新增裸 `bool` 字段，前端重新拉取该任务配置即自动出现 Checkbox，唯一的隐藏机制是
显式 `dynamic_hide(*fields)`（`tasks/KekkaiUtilize/config.py` 未对任何字段调用它）。**结论：本轮
OASX 零修改**。

**`utilize_harvest`（是否领取寄养奖励）**：已存在（`UtilizeConfig.utilize_harvest: bool = True`），
未被 `dynamic_hide`，按上述链路本就会出现在前端——**不新增第二个重复字段，不改默认值**（维持
`True`，不擅自改变正在生产运行的用户既有行为）。已知间隙：OASX `cn_parts/*.dart` 目前没有
`utilize_harvest`/`utilize_harvest_help` 的中文翻译，界面会显示英文 Title Case（`"Utilize
Harvest"`）——纯文案缺口、不影响是否显示，按"确认能自动显示就不改 OASX"的口径本轮不补。

**新增 `UtilizeConfig.auto_replace_max_level: bool = False`**（`tasks/KekkaiUtilize/config.py`，
与 `utilize_harvest` 并列在业务配置类 `UtilizeConfig`，不是 `UtilizeScheduler`——区分标准见
D024）：`True` = 保留 `check_max_lv()` 全套逻辑（满级检测 → 卸下 → 切换式神 → 自动补位）；
`False`（默认）= 完全跳过。`run()` 唯一改动点：

```python
if con.auto_replace_max_level:
    self.check_max_lv(con.shikigami_class, con.auto_fill)
```

`check_max_lv()` / `unset_shikigami_max_lv()` / `switch_shikigami_class()` / `set_shikigami()`
**全部原样保留**，未删除、未改内部逻辑，只是调用点加了一层开关（业务能力"退休"= 加开关，
不是删代码，见 D024）。

**测试**：新增 `tests/test_kekkai_utilize_state.py::MaxLevelAndHarvestSwitchTest`（8）：
CASE1/2（`auto_replace_max_level` False/True 通过完整 `run()` 验证 `check_max_lv` 不调用 / 调用一次
且参数仍是 `(shikigami_class, auto_fill)`）、CASE3/4（`utilize_harvest` False/True 对
`check_utilize_harvest` 同理）、CASE5（新字段默认 `False`、旧字段默认 `True` 不变）、CASE6（完整
`KekkaiUtilize` 模型可 instantiate/dump，且 `model_json_schema()` 里两个字段的 `type` 均为
`'boolean'`——直接验证前端渲染依据）、源码形态锁定开关接线 + 旧方法未被删除。回归
**1453 → 1461**（+8，0 regression）；`compileall` OK；`git diff --check` 干净。

**未改**：好友列表扫描 / 卡种筛选 / 收益阈值 / OCR / `KekkaiUtilize Scheduler v1`（quiet
window / cooldown，D023，本轮未碰）/ `goto_page` 失败 U3 技债（**已于 §4.68，2026-09-14 修复**）/
RealmRaid；**OASX 全仓 0 修改**
（`d:\oas_xy\OASX` HEAD `035aece1242bf22ed7257814908c2f031fc94fc6` 未变，未 build、未部署）。

### 4.66 GeneralBattle Settlement Micro-Burst v1：结算 Click Session + Anchor Persistence

**背景**：Settlement Contract V3（D014/D016）已把结算点击收敛成三个 Large Safe Region + 节流
间隔，但通用结果页首帧仍是写死的「强制两次点击、各自独立采样」（`_advance_generic_result`），
之后每帧都退回「每次独立随机一个新点」的单次节流点击，不像真人会在同一个位置连续点几下。本轮
把这段升级为 Settlement Click Session：一次结算生命周期（`page_battle_result` →
`page_reward` → 离开）内维护一份总点击预算与可复用的 anchor，替代旧的固定两次序列。

**契约**（详见 `docs/DECISIONS.md` D025）：

- **总点击预算是上限，不是必须执行的次数**：`_sample_settlement_budget()` 单次
  `random_int(1,10)` 分桶（1~5→2 / 6~8→3 / 9~10→4，权重 50%/30%/20%），真实页面提前进入
  terminal 就立即停手，剩余预算作废。
- **一次 blind micro-burst 硬上限 2 次、必须复用同一 anchor**：`_sample_settlement_burst_size()`
  从 `{1,2}` 均匀二选一并夹到剩余预算；burst 内连续点击坐标完全相同，中间只隔新常量
  `SETTLEMENT_BURST_CLICK_INTERVAL_RANGE = (0.10, 0.30)`（**该值已于 2026-09-23 调整为 `(0.30, 0.60)`，见 §4.92**；下文数值是当轮记录，不回改）（与跨 burst 节流的
  `SETTLEMENT_CLICK_INTERVAL_RANGE = (0.7, 1.0)` 是不同 timing owner）。burst 后不做任何页面
  探测，下一次机会等外层 `run_general_battle()` 主循环下一帧 fresh screenshot +
  `detect_page_in`（既有机制，未新增探测逻辑）。
- **状态允许合法前向跳级**：`page_battle_result → page_reward` 之间某一帧被 burst 跳过、或
  直接在 `page_reward` 首次触发结算（从未见过 `page_battle_result`），`_settlement_burst_step`
  都能正确处理——只看「session 是否已初始化」与「当前页是否等于上一帧页」两个既有信号，
  不新增容错分支，也不放宽 FSM 判据（仍要求确实是已知的战斗页面）。
- **anchor persistence 服从安全区域交集**：状态前向变化时，`_advance_settlement_anchor()`
  先做安全校验（`_point_in_roi`：旧 anchor 是否落在新状态适用安全区域内）——不安全则**强制**
  重新采样（安全 fallback，不计入「主动换点」）；安全则按概率
  （`SETTLEMENT_ANCHOR_KEEP_PROBABILITY=50`，PROVISIONAL）决定保留或换点，且**全 session 最多
  1 次主动换点**。同一页面内默认无条件复用原 anchor。
- **Reward layout-aware 策略保持不变**：`_select_reward_region()` 本体未改；burst 只在 session
  初始化 / 状态刚切到 reward 时调用它一次（惰性 `region_provider`），避免它的 80/20 随机分支被
  每帧重新掷骰子。
- **Settlement 点击永远不能穿透到 Challenge / FIRE 页面**（用户中途明确追加的验收标准）：
  `run_general_battle()` 主循环每帧 fresh classify 之后、分发给具体 handler 之前新增
  `_teardown_settlement_session()` 调用——一旦确认当前页不是 `page_battle_result`/`page_reward`
  （`page is not None` 且不在这两者中）就立即销毁 session 的全部 7 个字段，不等到下一轮战斗
  才清理。这样连战场景里后续再出现的 `page_battle_prepare`/`page_battle`，或该任务自己在
  `run_general_battle()` 之外的目标选择/「再次挑战」页，都不可能复用上一次结算 session 的残留
  anchor/budget——任何新出现的 Challenge/FIRE 必须重新走它自己完整的 FIRE contract。
- **旧 `_advance_generic_result` 整体移除**：`_handle_result` 通用结果分支现在唯一调用
  `_settlement_burst_step`，不存在旧固定两次与新 session 同时执行的可能。

**新增 `BattleContext` 字段**（7 个，`settlement_session_active`/`settlement_click_budget`/
`settlement_clicks_used`/`settlement_anchor`/`settlement_region_name`/`settlement_stage_name`/
`settlement_anchor_switches`），随 `_build_context`/`_reset_round_context`/
`_teardown_settlement_session` 三处重建或清零，不跨轮持久化。

**新增方法**（`tasks/Component/GeneralBattle/general_battle.py`）：`_sample_settlement_budget` /
`_sample_settlement_burst_size` / `_sample_settlement_point` / `_click_settlement_point`（从
`_sample_settlement_click` 拆出的两个独立原语，原方法本体未改，仍供非通用结果 / Activity 任务
的 `_drain_activity_settlement` 使用）/ `_point_in_roi`（静态）/ `_start_settlement_session` /
`_advance_settlement_anchor` / `_fire_settlement_burst` / `_settlement_burst_step` /
`_teardown_settlement_session`。

**`_handle_result`/`_handle_reward` 改动**：通用结果分支与普通奖励分支改调
`_settlement_burst_step`；非通用结果标志（更宽的 `I_BATTLE_STATE_INFO`）/ 奖励特殊弹窗
（`I_OVER_GHOST`/`I_GB_SKIN_CONFIRM`）两条既有分支**逐字未改**。

**波及范围**：RealmRaid 非 quick_exit 路径、ActivityShikigami 首个通用结果帧（`BaseAct._handle_result`
调 `super()`）等所有通过 `super()._handle_result()`/`super()._handle_reward()` 继承公共
GeneralBattle 的任务，都会自然获得新的 Micro-Burst 行为——这是预期的（升级的是"结算怎么点"这个
公共契约本身），不是误伤。**明确不受影响**：RealmRaid `fire()`/`_fire_again()` FIRE 契约本身
（不同的 owner，独立于结算点击）；ActivityShikigami `_drain_activity_settlement()`（task-local
独立 drain，只调 `_sample_settlement_click`，不经过 `_handle_result`/`_handle_reward`/本
session，`run_general_battle()` 返回之后才被调用）。

**测试**：`tests/test_general_battle_settlement.py` 移除 `MandatoryDoubleClickTest`（旧固定两次
契约，9 例），新增 `SettlementMicroBurstTest`（15，覆盖同点复用/单次采样/状态前进保留或换点/
安全区域强制换点/budget 上限语义/跳级/blind burst 上限/旧函数移除/Reward 策略保留/Loss 同路径/
budget 分布）+ `SettlementSessionTeardownTest`（3，含一个驱动真实 `run_general_battle()` 主循环
两帧的端到端用例，日志可见 `Settlement session destroyed` 先于 `Battle result` 输出，证明销毁
发生在 handler 分发之前）；`tests/test_general_battle_timing.py`/`tests/test_reaction_timing_batch1.py`/
`tests/test_ryoutoppa_c_area_1_point_opt_in.py` 同步更新受影响的 context 字段与源码断言。回归
**1461 → 1472**（+11，0 regression）；`compileall` OK；`git diff --check` 干净。

**Level C 待验**：通用战斗结束是否观察到同点连续点击；一次结算真实总点击是否落在 2~4 内；
第二下就退出结算后是否确实不再盲点；`page_battle_result → page_reward` 跳级 FSM 是否稳定；
anchor 保留/换点是否都发生在安全区域内；Reward 特殊 layout 是否仍被正确识别；Loss/Fire Again
路径是否不受影响；结算结束后进入下一次 Challenge/FIRE 时确认没有结算残留点击。
`SETTLEMENT_BURST_CLICK_INTERVAL_RANGE`/`SETTLEMENT_ANCHOR_KEEP_PROBABILITY`/budget 权重分布
均 PROVISIONAL。

> **§4.67（2026-09-12，同日）把本节「一次 blind micro-burst 硬上限 2 次」收紧为 Observed
> Micro-Burst——第二下不再无条件执行，必须先拿到 mid-burst fresh 语义观察结果，见 §4.67。**

### 4.67 GeneralBattle Settlement Micro-Burst v1.1：Blind Burst → Observed Micro-Burst（Click → Observe → Decide）

**背景**：§4.66 落地的 v1 虽然已经用主循环级 `_teardown_settlement_session()` 保证「确认离开
结算后不再继续点击」，但同一次 burst 内的两次点击之间**没有任何 fresh 页面观察**——只隔一段
`time.sleep`。如果第一下点击已经使页面从结算推进到 Challenge/FIRE（例如 Reward → 下一场
prepare），第二下盲点仍可能在状态机尚未重新截图/分类之前先落到新页面上，出现「Settlement
点击穿透到 Challenge/FIRE」的窗口。用户明确要求把人类真实行为建模进去：点击 → 观察页面反馈
→ 没变化才允许在同一位置补点，变了就必须停手、交回状态机重新判断。

**契约变化**（详见 `docs/DECISIONS.md` D025 v1.1 修订段落）：

- **第二下点击从「burst_size 提前抽到 2 就无条件执行」改为「必须由 fresh 语义观察触发」**：
  `_fire_settlement_burst(context, current_page)` 新增 `current_page` 参数。第一下点击**一定
  执行**（沿用 v1 的 remaining/timer 判断）；只有当 `desired_burst_size >= 2` 且预算未耗尽时，
  才在第一下点击后 `time.sleep(SETTLEMENT_BURST_CLICK_INTERVAL_RANGE)`（沿用既有常量，不新增
  第二个间隔）→ `self.screenshot()` → 新增私有 helper `_classify_general_battle_page()`
  （原样转发给 `GameUi.detect_page_in(self, page_battle_prepare, page_battle, page_battle_result,
  page_reward, include_global=False)`，与 `run_general_battle()` 主循环用的是**同一个**
  matcher/classifier，不新造第二套页面分类逻辑，也不接 FrameWait 的 changed/stable 像素判定）
  → 按观察结果分支决定：
  - 观察结果 == 点击前的 `current_page`（语义上仍是同一结算页）→ 才允许用同一个 anchor 补
    第二下；
  - 观察结果是另一个已知结算页（`page_battle_result`/`page_reward` 之一，但不等于
    `current_page`）→ 当前 burst 立即结束，不在旧 state 上补点，新 state 留给下一次
    `_settlement_burst_step` 调用通过既有 `_advance_settlement_anchor` 重新决定 anchor（v1
    的安全区域交集逻辑完全不变、未被本轮触碰）；
  - 观察结果是已知的非结算页（`page_battle_prepare`/`page_battle`，即 Challenge/FIRE 相关页）
    → 立即调用 `_teardown_settlement_session()`（与主循环级的销毁调用复用同一个 helper，不
    重复 7 个字段的清零逻辑），直接 `return`，不武装节流计时器、不打印 terminal 日志；
  - 观察结果是 `None`（Unknown，四个已知页面都没能确认）→ 不补第二下，但**不**销毁
    session（不能因为一次识别失败就断定已经离开结算），沿用既有 `_handle_missing_battle_page`
    / 2.5s 兜底做后续判断。
  任何分支下一次 `_fire_settlement_burst` 调用最多点 2 次，第二下之后无论走哪个分支都直接交回
  主循环下一次 fresh classify，不产生第三下。
- **方案选择：Option A（侵入最小），不是 Option B**：保留 `_sample_settlement_burst_size()`
  「预抽 desired burst size」的既有概念与调用时机（burst 开始时抽一次，语义仍是"本次最多想点几
  下"），但第二下的**实际执行**改为在 mid-burst fresh 观察之后才决定，而不是像 v1 那样预抽到 2
  就直接连点两下。没有改成「先固定点一下，再随机决定要不要补第二下」（Option B）——那样会让
  「同一 anchor 连点」这个人类行为特征变成完全看运气，偏离用户想要的「原位置多半会补一下，只是
  补之前先看一眼」语感。
- **timing 不叠加新 owner**：mid-burst 观察复用的 `SETTLEMENT_BURST_CLICK_INTERVAL_RANGE =
  (0.10, 0.30)`（**该值已于 2026-09-23 调整为 `(0.30, 0.60)`，见 §4.92**；下文数值是当轮记录，不回改） 是 v1 就存在的常量，本轮只是把它的语义从「两次盲点之间的间隔」收紧为「点击 →
  观察前的等待」，数值和归属都没变；第二下点击完成后立即回到跨 burst 节流
  `_next_settlement_click_interval()`（未改），不会和 reaction/Fatigue 堆叠出第三个 owner。
- **teardown 现在有两个入口，复用同一个 helper**：v1 只有「主循环每帧 fresh classify 之后」一个
  销毁入口；v1.1 在 `_fire_settlement_burst` 的 mid-burst 观察分支里新增第二个入口——两者都只
  调用 `_teardown_settlement_session(context)`，没有复制 7 个字段的重置代码。
- **budget/anchor persistence/Reward layout-aware/主动换点上限/Loss 范围/Activity 独立
  drain/FIRE 契约本身全部未改**：v1 的这些既有契约本轮逐字保留，只是「blind burst 的第二下」
  这一个环节被收紧为「observed burst 的第二下」。

**新增方法**：`_classify_general_battle_page()`（`general_battle.py`，纯转发 `GameUi.detect_page_in`，
不引入新的页面识别规则）。`_fire_settlement_burst` 签名新增 `current_page` 参数（调用方
`_settlement_burst_step` 同步更新）。

**测试**：`tests/test_general_battle_settlement.py` 新增 7 例——CASE B（Result 观察到已推进
Reward，只点 1 次）、CASE E 链式（紧接 CASE B 的同一 session，下一帧 Reward 安全区域内 keep
同一 anchor，证明「burst 被观察中止 ≠ 必须换点」）、CASE C 单元级（Reward 观察到 terminal，只点
1 次并立即 teardown）、CASE D（观察到 Unknown，不补点也不 teardown）、CASE G（budget=4 但首下
即 terminal，teardown 前真实 `used=1/4` 通过日志断言）、CASE H（同 state 补点后紧接的下一次
调用被节流计时器挡下，不产生第三下）、CASE I（用调用顺序日志验证 click → observe → teardown
的严格顺序，而不只是断言最终字段状态）；同时修复 8 处既有 harness/测试对 `_fire_settlement_burst`
新签名与新增 `self.screenshot()`/`_classify_general_battle_page()` 依赖的适配（`_make_task()`
新增 `task.screenshot = Mock()`；`_SettlementHarness`/`RewardOverlayTest`/`_BurstHarness`/
`TaskCompatibilityTest` 的相关 harness 新增 `_classify_general_battle_page` 默认 mock；
`test_main_loop_destroys_active_burst_session_before_leaving` 重写为确定性端到端用例，
`random_int`/`detect_page_in` 均显式 mock 序列，不再依赖真实随机）。回归 **1472 → 1479**
（+7，0 regression）；`compileall` OK；`git diff --check` 干净。

**Level C（重新定义，取代 §4.66 的旧 Level C 列表）**：①Result 第一次点击未切页时能否观察到
自然的同点补点；②Result 第一次点击已经切到 Reward 时是否确实不出现旧 state 的第二个盲点；
③Reward 第一次点击直接切到下一场 terminal 时是否不残留任何 settlement 点击；④进入
Challenge/FIRE 前是否总是先经过 Settlement teardown、再由 FIRE 契约独立接管，视觉上没有交叠；
⑤连续点击在肉眼观感上是否仍然自然，不会因为多了一次 mid-burst 截图/识别而出现明显停顿；
⑥`SETTLEMENT_BURST_CLICK_INTERVAL_RANGE = (0.10, 0.30)`（**该值已于 2026-09-23 调整为 `(0.30, 0.60)`，见 §4.92**；下文数值是当轮记录，不回改） 的观察间隔是否足够看到真实页面更新；
⑦若真机页面响应慢于 300ms，是否会出现「仍识别到旧 state → 补第二下」但该点击仍落在安全的
结算区域内（不应该出现的坏情况：识别慢导致误点到已经切换的新页面）；⑧anchor keep/resample 在
真机上的实际观感是否自然。

### 4.68 KekkaiUtilize U3：进入好友结界寄养页导航失败必须阻断寄养业务

**背景**：§4.64/§4.65 落地 Scheduler v1 与业务开关时，末尾都挂账了同一条已知技债——
`check_utilize_add()` 里 `if not self.goto_page(page_guild_realm_utilize): logger.info(...)`
只记录一行日志，没有 `return`/`continue`，导航失败后仍会继续往下落入
`self.run_utilize(...)`，在错误页面继续好友 OCR / 收益 OCR / 列表 swipe / 结界卡点击。本轮
（U3）正式修复。

**根因（READ ONLY 源码审查先行确认，不是想当然改写）**：`GameUi.goto_page()`
（`tasks/GameUi/navigator.py:769`）的真实契约是「成功 `return True`（`_finalize_arrival` 固定
返回 `True`）／失败 `raise GamePageUnknownError`」——通读整个方法体，唯一的 `while True:` 循环
里没有任何 `return False`/`return None` 分支，只会成功返回或抛异常（或在个别 close-unknown
重试分支里继续内部轮询）。也就是说，旧代码 `if not self.goto_page(...)` 这个判断**在当前
Navigator 实现下从未真正生效过**——不是"偶尔漏判"，而是这个 `if` 分支本来就等不到一个假值。
真正会发生的失败形态是异常传播：`goto_page` 抛 `GamePageUnknownError` 会直接穿过
`check_utilize_add()`/`run()`，不经过 Kekkai 自己的失败计数与 Scheduler v1 重试管线。

**修复**（`tasks/KekkaiUtilize/script_task.py::check_utilize_add`，唯一改动点）：本地
`try/except (GamePageUnknownError, GameStuckError)` 把「异常」与「（防御性保留的）假值返回」
两种失败信号统一收敛成 `reached_utilize_page`；不为真就复用
`_finish_low_value_utilize`/`_record_utilize_failure` 最终失败分支同款的既有终态失败出口——
`self._schedule_retry('导航到好友结界寄养页失败')` + `self.utilize_terminal_failure = True` +
`return False`——不新增第二套重试/超时机制，也不触碰 `utilize_add_count`（OCR 轮询次数）与
`utilize_failed_count`（选中候选后的蹭卡失败次数）这两个既有计数器语义。`check_utilize_add()`
返回 `False` 会让 `run()` 的 `if not self.check_utilize_add(): return` 自然生效，跳过
`check_max_lv()`/`check_utilize_harvest()`/`check_box_ap_or_exp()`/`receive_guild_assets()`
全部下游业务——与「3 次蹭卡失败」「跨区+同区无达标候选」两个既有终态失败路径完全同构，不是
新发明的行为。异常类型选择 `(GamePageUnknownError, GameStuckError)`，与 `run_utilize()` 自己
对内部 `self.goto_page(page_friend_utilize)` 的既有 catch 元组保持一致（一个 `goto_page` 调用
一种失败处理口径）。导航**成功**分支后续语句（`self.run_utilize(...)` / `utilize_terminal_failure`
检查 / `self.goto_page(page_guild_realm_growth)`）逐字未改。

**未改**：Navigator/`goto_page()` 本身的返回/抛异常契约（未触碰 `tasks/GameUi/navigator.py`
一行）；好友列表扫描 / 卡种筛选 / 收益阈值 / OCR 算法本体；Scheduler v1 的 5~30 分钟 cooldown
范围与静默窗口归一化算法；`utilize_harvest`/`auto_replace_max_level` 业务开关；
`KekkaiActivation`；GeneralBattle/RealmRaid/OASX。

**测试**：新增 `tests/test_kekkai_utilize_state.py::UtilizeNavigationFailureGuardTest`（10）：
CASE1（导航成功 → `run_utilize` 恰好调用 1 次，既有「已在寄养」OCR 出口语义不变）、CASE2/2b
（导航假值失败 / 抛 `GamePageUnknownError`·`GameStuckError` 两种真实失败信号都阻断
`run_utilize`）、CASE345（不满足于外层 mock：把 `run_utilize` 换回真实方法，只 mock 它内部
仅有的两个业务分发口 `_run_search`/`_run_lazy_utilize` 及 `switch_shikigami_class`/
`set_shikigami`，证明真实方法体从未被进入而不是只验证外层一层 mock 没被调用）、CASE6/7
（复用 `_schedule_retry`——5~30min cooldown 随机 + 落入静默窗口时仍被 `normalize_for_quiet_
window` 正确顺延+jitter）、CASE8（失败只触发一次 `_schedule_retry`，不触碰既有两个计数器）、
CASE9（`goto_page(page_guild_realm_growth)` 循环底部那次调用不会发生，本轮迭代立即结束）、
CASE10/10b（源码级锁定成功分支既有语句原样保留 + 成功后 `run_utilize` 自身产生的既有
terminal failure 语义不受影响）。回归 **1479 → 1489**（+10，0 regression）；`compileall` OK；
`git diff --check` 干净。

**Level C 待验**：真机人为制造无法进入好友结界寄养页的场景（网络卡顿/异常弹窗/坑位耗尽等）→
确认日志按预期出现 `KekkaiUtilize navigation failed` 系列 → 确认不再继续任何好友/收益/结界卡
OCR、不 swipe 寄养列表、不在错误页面点击 → 确认 `next_run` 正确生成（5~30min cooldown，落入
静默窗口时正确顺延）→ 下次任务能正常重新尝试；以及正常导航成功时寄养流程完全不受影响的真机
体感确认。

### 4.69 Pre-Push Blocker Fix：ActivityShikigami Macro Idle ownership 跨玩法线泄漏

**背景**：推送前深度审查（READ ONLY）在当前工作树上只发现一个 BLOCKER。`ScriptTask.run()`
（`tasks/ActivityShikigami/script_task.py:24-28`）会在**同一个实例**上按用户配置的
`task_sequence_v` 顺序调用 `run_climb` / `run_rich_man` / `run_fakegod`；而
`NormalClimbAct.run_climb` 只把 `_fatigue_owns_macro_idle` 置 `True`（爬塔线把宏观空闲交给
Fatigue 安全节点），**没有任何线切换时的恢复**，`rich_man.py` / `fake_god.py` 也从不声明。

**后果**：配置成「爬塔,伪神降临」或「爬塔,大富翁」时，后一条线既拿不到 Fatigue 安全节点
（`try_fatigue_break` 只在 `NormalClimbAct._activity_challenge_safe_break` 里，climb-only），
又因为残留的 `True` 被 `prepare_next_action` 跳过 `random_sleep`——**出现零 macro-idle
owner**，静默丢掉这条线的拟人化宏观空闲。这与 `base_act.py` 注释里写明的设计意图
（「大富翁 / 伪神降临线保持 random_sleep」）直接矛盾。

**修复**（最小、语义明确）：把 ownership 改成**每条玩法线在自己的 `run_*` 入口显式声明**，
不继承上一条线的残留值——`run_rich_man` / `run_fakegod` 各加一行
`self._fatigue_owns_macro_idle = False`（紧跟 `logger.hr` 之后、任何业务之前），
`run_climb` 既有的 `= True` 原样保留；`base_act.__init__` 的默认值只作实例初始默认、不再
承担线间切换职责（注释已补上这条契约）。未改 Fatigue 模型 / 概率 / `random_sleep` 参数 /
任何活动业务流程；`ScriptTask.run()` 未改（ownership 由线自己决定，对 dispatch 顺序与直接
调用都成立）。

**测试**：新增 `tests/test_activity_shikigami_climb.py::MacroIdleOwnershipLifecycleTest`（5）：
CASE1 `run_climb → run_fakegod`、CASE2 `run_climb → run_rich_man`（都断言后一条线的**真实**
`prepare_next_action` 确实调用了 `random_sleep`）、CASE3 单独 `run_climb`（Fatigue 持有，
绝不再叠 `random_sleep`）、CASE4 `fakegod → climb → fakegod`（ownership 可 False→True→False
往返、不粘滞）、以及一条源码级护栏（三条线入口都必须显式声明 owner）。**全部走真实 `run_*`
入口调用链、只 mock 业务叶节点，不手工写 flag**；已用「内存中重建修复前实现」验证过
CASE1/CASE2 在修复前失败、CASE4 在修复前直接 `AttributeError`，确认不是 false positive
（旧的 `test_flag_false_still_random_sleeps` 因为手工把 flag 设成 False，抓不到这个泄漏）。

**同轮低风险清理**：删除 2 个 dead import（`tasks/base_task.py` 的 `import random`——HEAD 时
被 `sleep(random.uniform(0.8,1.3))` 使用，已被 FrameWait 取代；`tasks/KekkaiUtilize/script_task.py`
的 `next_quiet_window_end`——只在 `scheduling.py` 内部使用）；清理
`tasks/ActivityShikigami/assets.py` 本轮新增的 3 处 trailing whitespace。回归
**1489 → 1494**（+5，0 regression）。

### 4.70 GeneralBattle Settlement Micro-Burst v1.2：Level C budget 卡死修复

**Level C 失败证据**：2026-09-14，master 普通副本第三场日志为
`Settlement session: budget=2` → Generic Result `used=1/2` → fresh classify `page_reward` → Reward
`used=2/2` → `Settlement terminal budget exhausted ... stop early`；下一帧仍为 `page_reward`，真实
画面停在“点击屏幕继续”。这排除了识别、Reward asset、anchor、FIRE、账号轮换与 synevo merge；
根因是 v1.1 把随机 2~4 budget 错当成整个 Settlement lifecycle 的硬上限，合法结算尚未完成时
永久撤销了 click owner。

**v1.2 修复**（`tasks/Component/GeneralBattle/general_battle.py`，详见 D025 v1.2 修订）：

- Settlement 拆成 lifecycle + click segment。兼容保留的 `settlement_click_budget/clicks_used` 语义
  改为当前 segment；新增 `settlement_total_clicks` 仅作 observability 与固定 safety cap。
- 2/3/4 继续按 50%/30%/20% 分桶，但只在首个 known settlement state、state advance 或 fresh
  classify 确认同 state 且旧 segment 耗尽时生成。segment exhaustion 不再是 terminal。
- 采用方案 B：Generic Result → Reward 结束 Result segment，Reward 获得独立 2~4 segment；anchor
  生命周期保持独立，仍按安全区域交集 keep/resample，同 state 续段不强制换点。
- semantic state 决定 lifecycle 完成：same result/reward 可续段；Unknown 不续段、不盲补；known
  non-settlement 立即记录 `Settlement terminal reached` 并 teardown。
- 保留 Click → Observe → Decide、0.10~0.30s（**该值已于 2026-09-23 调整为 `(0.30, 0.60)`，见 §4.92**；下文数值是当轮记录，不回改） mid-burst fresh classify、same-state second-click gate、
  terminal teardown、Reward layout-aware region 与 FIRE isolation。
- 现有 `battle_timer` 不覆盖 settlement，连续点击又会重置底层 stuck timer；因此新增明确的
  `SETTLEMENT_MAX_TOTAL_CLICKS=9`，与 Device 对同 target 第 10 次调用前抛错的既有有效上限对齐，
  让 Settlement 层先停止续段。它是 provisional 故障安全帽，不是随机节奏预算；Device
  click/stuck guard 仍是第二层保护。

**测试**：`tests/test_general_battle_settlement.py` 新增 11 项（CASE 1~10 + 第二 Reward segment
端到端返回），覆盖真机 budget=2 链、segment renew、semantic terminal 优先、Unknown 不续段、
state 独立预算、anchor 跨 segment 保持、固定安全帽与至少 3 个 segment 仍有界、second-click gate
不回归。focused：Settlement **83/83 OK**；GeneralBattle timing **17/17 OK**；RealmRaid
**107/107 OK**；ActivityShikigami **63/63 OK**；reaction + RyouToppa **59/59 OK**。完整回归数字见
§7。

**状态**：Micro-Burst v1.1 Level C = **FAIL**；v1.2 = **Level A/B PASS / Level C RE-TEST
PENDING**。下一轮真机重点：budget=2 不再卡 Reward、Reward 可跨 segment 继续、正常 terminal 后无
残留点击、永久 Reward 不无限 renew、FIRE 不受影响，并观察 safety cap 9 是否合适。

### 4.71 L1 Global Click Pipeline 公共层移植到 master 基线（L2-1 前置）

2026-09-15。L2-1 要求在 master 公共能力上开发，但 master（`a5e2d7e6`）**没有 L1**——L1 / L1.2 只存在于 synevo
基线的未提交 worktree（`feature/l1-global-click-pipeline-v1`）。判断可以最小、干净地移植：L1 触及的公共文件在 master
工作区与 synevo `e9c8123c` 逐字节一致（含本工作区未提交的 Settlement v1.2 三个文件），仅 GeneralRoom / EvoZone /
navigator 三处有 synevo 业务差异，L1 hunk 用 3-way 干净套上。

新 worktree `D:/oas_xy/wt-l2-interaction-reaction`（分支 `feature/l2-interaction-reaction-layer`，精确基于 master
`a5e2d7e6`），先逐字节复制 master 工作区的 9 个未提交文件（Settlement v1.2 + 六份文档），再移植 L1 公共层：
`module/click_pipeline.py`、`RuleList.last_ocr_hit`、`Control.click_with_backend` / `_dispatch_click`、全部公共 task
点位与 `tests/test_l1_click_pipeline.py`。**未带入任何 synevo 业务代码**：master 没有网易原生控件 / MultiAccountEvo；
Login `_app_handle_login` 与 DailyTrifles `summon_recall` 属小号轮换业务，保留直接 `device.click`，在 L1 静态白名单里标为
显式排除项（因此 master 的 L1 **不是 0 bypass**：业务绕过 = 这 2 处排除项）。L1 测试 67 → 66（删除 synevo 专属网易控件
用例）。回归 master 基线 1505 → **1571/1571 OK**。L1 设计与点位见 D026（含 master 移植说明）、
`docs/T7_TARGET_PREFERENCE_MAP.md` §9 / §10。Level C 仍 PENDING。

### 4.72 L2-1 Interaction Reaction Layer（Reaction Profile + Fresh Confirm + FIRE 可配置延迟）

2026-09-15，同一 worktree，叠加在 §4.71 之上，**未提交**。设计见 D001「L2-1」补记、`docs/ARCHITECTURE.md` L2 小节。

- **L2 公共层**：新增 `module/interaction_policy.py`——`InteractionPolicy`（IMMEDIATE / FAST / NORMAL / NORMAL_HIGH / CONFIRM /
  NAVIGATION / DELIBERATE / FIRE_SPECIAL / SPECIAL）、`resolve_reaction_range(policy, confirm_delay)`、`fire_reaction_range(cfg)`；
  只做语义 → 区间，不 sleep / 不采样 / 不点。`BaseTask.appear_then_click` 新增 `policy=`（不加新方法、不造第二套 API），
  复用既有 reaction → fresh screenshot → 再识别 → 新帧 `coord()` 路径；`policy` 与 `confirm_delay` 同时给 → `ValueError`；
  不传 / IMMEDIATE = 旧立即点击。`GeneralBattle.check_lock` 透传 `policy`。
- **普通 consumer 迁移（语义等价，区间逐值相同）**：28 个 `confirm_delay=REACTION_*` → `policy=InteractionPolicy.*`
  （EvoZone 4 / Orochi 5 / RealmRaid 6 / RyouToppa 3 / Exploration 8 / ActivityShikigami 入口 2）。未迁：RealmRaid
  `RR_AGAIN_CONFIRM_DELAY=(0.3,0.6)`（非 profile legacy 区间）；Navigator 通用 `_execute_action`（保持 IMMEDIATE）；
  GeneralInvite / GeneralBattle 其它立即点击（未经逐点分析不改 NORMAL）。`NORMAL_HIGH` 0 consumer。
- **FIRE 可配置**：共享 schema `tasks/Component/config_fire_reaction.py::FireReactionConfig`（`fire_reaction_min_ms` /
  `fire_reaction_max_ms`，默认 400 / 800 ms，`0<=min<=max<=5000`，`min==max` 合法，字段级校验 + `validate_assignment`，非法
  单字段修改被拒且旧值保持），作为 `fire_reaction` 组加到 RealmRaid / RyouToppa / EvoZone / Orochi / ActivityShikigami；
  `config/template.json` 与 `assets/i18n/zh-CN.json`（FIRE 点击前最小 / 最大延迟）同步；OASX 为 schema-driven，0 修改。
  7 个 FIRE owner FSM 不重写，只把 `random_delay(*REACTION_FIRE)` 换成 `random_delay(*fire_reaction_range(<task>.fire_reaction))`；
  GeneralInvite 由 `run_invite(fire_reaction=)` → `click_fire(fire_reaction=)` 沿配置传入（Orochi / EvoZone 已传，其它
  consumer 用公共默认），不读 `self.config` / 不猜 script_name。
- **排除**：Settlement Micro-Burst、Fatigue、FrameWait、Swipe、L1 空间模型、FIRE post-click FSM / retry / recovery 零改动；
  AccountRotation / SwitchAccount / Login / DailyTrifles 不纳入。
- **状态**：Level A/B **PASS**（新增 `tests/test_l2_interaction_reaction.py` 26 项；8 组变异回退全部被抓；为源码形态变化
  同步修改 9 个既有测试文件的正向断言 / 替身配置，删除 0；全量 1571 → **1597/1597 OK**）；Level C **PENDING**——真机看
  reaction 是否符合任务配置、fresh confirm 避免旧坐标、FIRE 启动正常且不明显变慢、无 double reaction、Settlement timing 不受影响、
  导航不被过度延迟。

### 4.73 L2-2 Interaction Policy Migration（master 主线普通 UI 点击逐点分类）

2026-09-15，同一 worktree，叠加在 §4.72 之上，**未提交**。规则见 D001「L2-2」补记，逐点清单见
`docs/L2_INTERACTION_POLICY_MAP.md`。

- **审计覆盖**：10 个高频公共模块 18 个文件 179 个点击调用点逐点分类——ALREADY_L2 33 / **MIGRATE 7** / KEEP_IMMEDIATE 94 /
  KEEP_SPECIAL 38 / NEEDS_C 7。`base_task.py` 19 处为 primitive 自身；AccountRotation / SwitchAccount / Login /
  DailyTrifles / MultiAccountEvo 排除；其余 51 个模块约 720 处点击本轮未逐点审计。
- **迁移**：GeneralInvite `_open_invite_panel_if_needed` 的 `I_ADD_*` ×4 → NORMAL；GeneralBattle `switch_preset_team` 的
  `I_PRESET` / `I_PRESET_WIT_NUMBER` → NORMAL、`I_PRESET_ENSURE` → CONFIRM。只用 `appear_then_click(policy=)`。
- **刻意不迁**：`check_and_invite`（在 `_handle_reward` 奖励阶段调用，归 Settlement 生命周期）、`I_PREPARE_HIGHLIGHT`
  （准备 = Battle Entry 语义）、房间表情（防挂机节拍）、exit_room / exit_battle（recovery / 中止）、`ui_click*` helper
  （无 policy 参数，本轮不扩 API）、OCR / 区域 / 颜色状态目标、KekkaiUtilize 全部（受保护路径）、Navigator 通用执行器。
- **NEEDS_C**：GeneralInvite `check_then_accept` ×5、准备页「不同御魂」弹窗 ×2。
- **状态**：Level A/B **PASS**（新增 `tests/test_l2_policy_migration.py` 14 项；修改 `test_l2_interaction_reaction.py`
  consumer 计数与 `test_general_invite_challenge_reaction.py` import 断言各 1 处，删除 0；6 组变异全部被抓；全量
  1597 → **1611/1611 OK**）；Level C **PENDING**。

### 4.74 L2-3B FIRE Batch A：Orochi 野队 / EternitySea / FallenSun / Sougenbi 战斗入口统一

> **master 集成说明（2026-09-21）**：Orochi 野队 `_fire_orochi_wild` 按项目决定**未集成**（野队 `run_wild` 保持原内联点击，不启用 / 不扩展）；EternitySea / FallenSun / Sougenbi 三条已集成。下文关于 Orochi 野队的叙述是 worktree 历史，以本说明为准。

2026-09-18，同一 worktree，叠加在 §4.73 之上，**未提交**。规则见 D001「L2-3B」补记。

- **改造前**：四条路径都是 `while 1` 里 `appear_then_click(FIRE, interval=1)` 连点，**「FIRE 按钮消失」即交接
  `run_general_battle`**，无 reaction、无 fresh confirm、无次数 / 总时长上限；loading 帧、结果 / 奖励页残留都会被当成已进战斗。
  Orochi `run_wild` 另用宽 `is_in_battle()` 跳过点击（含 WIN / REWARD）。
- **新 owner**（各任务私有，不进 BaseTask）：Orochi `_fire_orochi_wild`（`I_OROCHI_WILD_FIRE`）、EternitySea
  `_fire_eternity_sea_alone`（`I_ETERNITY_SEA_FIRE`）、FallenSun `_fire_fallen_sun_alone`（`I_FALLEN_SUN_FIRE`）、Sougenbi
  `_fire_sougenbi`（`I_S_FIRE`），各配只读 `_classify_*_fire_state` + 有界 `_wait_*_fire_state`。每 attempt：分类当前帧 →
  unknown 只等不点 → 采样本任务 `fire_reaction` → `sleep` → fresh screenshot → 重新确认 ready → `appear_then_click(FIRE,
  interval=0)`（不带 policy）→ 有界等点击后状态。`*_FIRE_MAX_TRIES=4` / `*_FIRE_TIMEOUT=10` / `*_FIRE_POST_CLICK_TIMEOUT=3`
  （对齐 Orochi / RealmRaid，engineering baseline）。
- **正向 Battle Entry**：新增只读 `tasks/Component/fire_battle_entry.py`——`is_new_battle_entry` = `I_PREPARE_HIGHLIGHT` /
  `I_PREPARE_DARK` / `I_BATTLE_INFO`（进入准备页即算 FIRE 成功，交接既有 GeneralBattle）；`is_battle_result_residue` = WIN /
  DE_WIN / FALSE / REWARD / REWARD_GOLD → `abnormal`，不算新战斗。不用宽 `is_in_battle()`，也不用含 `I_BUFF` / `I_PRESET`
  的 `is_in_prepare()`（这两个图标是否也出现在挑战 / 房间页未经真机确认）。
- **ready 判定**：Orochi 野队 = 在房间 + FIRE（threshold 0.8），另有 `room_failed`（复用 `_room_entry_failed`）；Sougenbi =
  `I_S_CHECK_SOUGENBI` + `I_S_FIRE`；EternitySea / FallenSun = FIRE 在。
- **caller 契约**：返回成功才调用一次 `run_general_battle`（config / battle_key / exit_matcher 与改造前逐字相同）；失败回外层循环顶
  重新截图判页，不计次数。Orochi 返回 `'battle' / 'room_failed' / 'abnormal' / 'timeout'`，房间死亡仍由外层 `is_room_dead`
  处理。不调用 `click_record_clear`，连续失败仍受 `GameTooManyClickError` 兜底。
- **配置**：EternitySea / FallenSun / Sougenbi 新增 `fire_reaction` 组（共享 `FireReactionConfig`，默认 400 / 800ms），
  `config/template.json` 同步，i18n 键共用无需改；Orochi 野队复用 `orochi.fire_reaction`。EternitySea / FallenSun 的组队路径
  也把本任务 `fire_reaction` 传给 `run_invite`（与 Orochi / EvoZone 一致，GeneralInvite 本体未改）。
- **已知断链不变**：`I_OROCHI_WILD_FIRE` 全仓仍无 `RuleImage`（§4.53），野队 FIRE 运行时仍会 `AttributeError`；补资产需
  ROI 标定（Level C）。本轮只把状态机收口，测试用同名替身注入。
- **状态**：Level A/B **PASS**（新增 `tests/test_fire_batch_a.py` 19 项；修改 `test_l2_interaction_reaction.py` FIRE owner 清单与
  `test_l2_policy_migration.py` 清单 1 行（L2M-084 KEEP_SPECIAL → ALREADY_L2），删除 0；8 类变异 × 4 个文件 = 32 次全部被抓；
  全量 1611 → **1630/1630 OK**）；Level C **PENDING**。
### 4.77 FIRE 点击前延迟配置最小范围接入 master（RealmRaid / RyouToppa / EvoZone / Orochi / ActivityShikigami / EternitySea / FallenSun / Sougenbi）

2026-09-18。从 L2 worktree `wt-l2-interaction-reaction`（未合并、未提交）按「最小范围移植」搬运 FIRE reaction
配置能力到本工作树，**不带入**该 worktree 里混杂的 L1 Global Click Pipeline / L2-2 普通点击 `appear_then_click
(policy=)` 迁移（master 的 `appear_then_click` 未改签名，`InteractionPolicy` 枚举本轮不落地）。规则见
`docs/DECISIONS.md` D001 补记「FIRE 分节 增补 —— 任务级可配置 reaction」。

- **移植依赖审查**：`tasks/Component/config_fire_reaction.py`（`FireReactionConfig`）与
  `module/interaction_policy.py::fire_reaction_range()` 从 L2 worktree 逐字节复制（两文件自包含，只依赖已在
  master 的 `module/reaction_profile.py::REACTION_FIRE`，不依赖 L1 `click_pipeline` / L2-2 迁移）；
  `module/interaction_policy.py` 里未使用的 `InteractionPolicy` 枚举 / `resolve_reaction_range()` 保持原样但
  本轮**零消费者**——不改 `appear_then_click`，不新增 `policy=` 调用点。
- **8 个任务的 `config.py`** 各加 `fire_reaction: FireReactionConfig = Field(default_factory=FireReactionConfig)`
  （默认 400/800ms），`config/template.json` 同步 8 组，`assets/i18n/zh-CN.json` 追加 5 个共享翻译键（`fire_reaction`
  组名 + `fire_reaction_min_ms` / `_max_ms` 标签与说明，8 个任务共用同一组键，不按任务重复）。
- **已有 FIRE FSM（RealmRaid.fire / RealmRaid._fire_again / RyouToppa.attack_area / EvoZone._fire_evozone_alone /
  Orochi._fire_orochi_alone / ActivityShikigami._enter_climb_battle / GeneralInvite.click_fire）**：FSM 形状、正向
  战斗判据、有限 attempt / `Timer` 总超时**一律不动**，只把 `random_delay(*REACTION_FIRE)` 换成
  `random_delay(*fire_reaction_range(<task>.fire_reaction))`；`GeneralInvite.run_invite` / `click_fire` 新增可选
  形参 `fire_reaction=None`（未传 = 公共默认，`ExperienceYoukai` / `GoldYoukai` / `Hunt` / `Tako` 等未接入的
  consumer 行为不变），`Orochi` / `EvoZone` 的 `run_leader` 沿配置传入本任务 `fire_reaction`。**Orochi `run_wild`
  按要求排除**，不碰、不修复其既有 `I_OROCHI_WILD_FIRE` 资产断链。
- **EternitySea.run_alone / FallenSun.run_alone / Sougenbi.run**：这三个任务此前 FIRE 点击**完全没有 reaction**
  （`appear_then_click(FIRE, interval=1)` 裸连点，`interval=1` 只是节流不是人为反应时间）。本轮**不新建三态状态机**
  （不改成功判据 / 不改重试超时契约），只在原有点击处改用 primitive 既有的 `confirm_delay=` 机制（D001 原始
  reaction 通道，早于 L2 的 `policy=` 迁移）：`appear_then_click(FIRE, interval=0,
  confirm_delay=fire_reaction_range(<task>.fire_reaction))`——`interval` 改 0 是因为 reaction 本身已是这次点击
  唯一的 timing owner，避免和旧 `interval=1` 节流叠成两个 owner。
- **测试**：新增 `tests/test_fire_reaction_task_config.py`（30 项）——8 任务配置组 + 隔离 + 默认值；`min==max`
  合法、非法区间拒绝且旧值保持；6 个既有 FSM owner 用自定义区间（非默认 111/333ms）**真实驱动**到点击分支，
  证明 `random_delay` 收到的确实是任务配置而不是恒定 0.4/0.8（复用 `tests/test_fire_reaction_fsm.py` /
  `tests/test_second_batch_fire_fsm.py` / `tests/test_general_invite_challenge_reaction.py` 里已验证过的替身
  构造，只换配置值）；EternitySea / FallenSun / Sougenbi 三个新接入点同样真实驱动 `run_alone` / `run`，断言
  `appear_then_click` 收到的 `confirm_delay` 参数；无双重 reaction（逐 owner 扫描 `random_delay(` / `confirm_delay=`
  次数）；`ConfigModel.script_task` / `script_set_arg` 保存重载回显；OASX 翻译键；GlobalGame / 疲劳翻译不回归。
  同步改 7 个既有测试文件的 `REACTION_FIRE` 断言为 `fire_reaction_range(...)`（选择性套用 L2 worktree 里对应
  hunk，跳过其中混杂的 `policy=` 迁移断言）。10 类变异（6 个 FSM owner 改回硬编码 + 3 个新接入点去掉
  `confirm_delay` + 1 个配置校验失效）全部被抓，文件逐字节还原。全量 1530 → **1560/1560 OK（0 skipped，
  此前 1 个 skip 的 CASE10 现真实命中 8 个任务）**。实际隔离 HTTP（`127.0.0.1:22395`，临时配置副本）验证 8 个
  任务 `GET .../args` 均 200、`fire_reaction` 组默认 400/800，真实 `PUT` 改 `RealmRaid.fire_reaction_min_ms=250`
  后 `GET` 回显正确，`config/oas1.json` / `oas2.json` 全程哈希与 mtime 不变。未启动 MuMu / 游戏 / OCR，非
  Level C。

### 4.78 KekkaiUtilize 短期重试正常结束：不再被通用调度器累计为失败

2026-09-20。承接同日只读审查（成功后调度机制专项审查）发现的缺陷；规则见 `docs/DECISIONS.md` D023 补记。**未 commit / push**。

- **根因**：`_finish_low_value_utilize` / `_record_utilize_failure`（3 次）/ 导航失败这三个「稍后重试」出口都已经用
  `_schedule_retry` 写好 5~30 分钟后的 `next_run`，但 `run()` 里 `if not self.check_utilize_add(): return` 直接返回；
  `Script.run` 把「正常返回」当失败（`script.py:528` `return False`），`Script.loop` 对同一任务连续 3 次失败会
  `exit(1)`（`script.py:604-623`，失败计数按任务名、成功即清零、不受其它任务穿插影响）。而同样是业务重试的
  「5 次尝试用尽」出口返回 True 后走到 `raise TaskEnd`（记为成功），两条出口结局不一致。好友列表长期没有达标卡时，
  约 15~90 分钟内就能连续 3 次，终止该账号的调度线程。
- **修复（只改 KekkaiUtilize 任务自身，不动全局失败判断 / 阈值）**：`_schedule_retry` 写入后用
  `_is_next_run_persisted` 从 `self.config.kekkai_utilize.scheduler.next_run` 读回确认（`task_delay` 内部先 reload
  再写，写入值已截断到秒，比较同口径；`set_next_run` 没有返回值，任务 / scheduler 缺失只 warning 静默返回，只能靠读回
  发现），结果存进 `utilize_retry_scheduled`。`run()` 在 `check_utilize_add()` 返回 False 时：已确认 → `raise TaskEnd`
  （调度器记为成功，`next_run` 保持刚写入的值，收尾流程不再改写）；未确认 → 仍直接 `return`（失败照常计数，不冒充
  正常结束）。「5 次尝试用尽」出口改为 `return self.utilize_retry_scheduled`：已确认保持原语义（继续收尾业务后
  `TaskEnd`），未确认按失败返回。写入本身抛异常仍照常上抛，系统异常（`GamePageUnknownError` / `GameStuckError`
  等）没有被新增任何捕获，仍走 `Script._handle_task_exception` 的 Restart 路径。调度时间算法（成功 = OCR 剩余时间、
  重试 = 5~30 分钟、静默归一化）一行未改，没有新增字段 / 延迟。
- **出口矩阵**：无卡 / 3 次软失败 / 导航失败 → 重试 + `TaskEnd`；5 次用尽 → 重试 + 收尾 + `TaskEnd`；已在寄养 / 成功
  寄养 / OCR 兜底 → 成功路径 + `TaskEnd`；静默守卫 → 重排 + `TaskEnd`；进结界 / 育成页导航异常、写入抛异常 → 异常上抛；
  重试读回不一致 → 失败返回。
- **测试**：新增 `tests/test_kekkai_utilize_retry_scheduler.py` 23 项——`run()` 出口矩阵 + **真实 `Script.run` /
  `Script.loop` + 真实 `Config.task_delay` 落盘**（临时目录里的临时配置、冻结时钟、`exit(1)` 换成可观察替身）：连续 5 轮
  无卡只重新调度（间隔恰 20 分钟、每轮落盘 next_run 合法且未被覆盖、失败计数恒 0、未触发退出、其它任务 Duel / AreaBoss
  仍被正常选取执行）；重试读回不一致时失败照常累计并在第 3 次触发（被替身的）`exit(1)`；系统异常仍返回失败并 `task_call('Restart')`；
  微秒时钟下读回一致；两个账号配置 / 失败计数互相独立。8 组变异（恢复原缺陷 / 读回恒真 / 恒假 / 5 次出口忽略读回 /
  无条件 TaskEnd / 吞系统异常 / 多写一次 / 不截断微秒）全部被抓。修改既有 `tests/test_kekkai_utilize_state.py`：
  `_sched_cfg` 的 scheduler 加 `next_run`，新增 `_persisting_set_next_run`，`RetrySingleOwnerTest` 改用它（原 Mock 不落值，
  读回会判失败），删除 0。全量 1560 → **1583/1583 OK**。
- **当时未修的独立待办**：若寄养点击后界面无变化、育成页 `I_UTILIZE_ADD` 一直在，`run_utilize` 每次选中都会把
  `utilize_add_count` / `utilize_failed_count` 归零，`check_utilize_add` 没有硬性收敛（探针 200 次未退出）——**已在 §4.79 修复**。
  `failure_interval` 死字段、OASX `success_interval` 文案仍不动。

### 4.79 KekkaiUtilize 寄养循环收敛保护：单次任务的总尝试次数 + 总耗时硬边界

2026-09-20。修 §4.78 记下的独立待办；规则见 `docs/DECISIONS.md` D023 补记（二）。**未 commit / push**。

- **根因**：`I_UTILIZE_ADD` 是「育成页 → 寄养页」的唯一入口。`check_utilize_add` 的 `while 1` 只有三条出口：按钮消失 → 成功调度、
  `utilize_terminal_failure`、`utilize_add_count >= 5`。但业务计数器会被清零：`utilize_add_count` 在每圈顶端 +1、
  `run_utilize` 一选中目标就归零（所以 `>=5` 实际到不了）；`utilize_failed_count` 在 `run_utilize` 成功返回时归零（软失败到 3 次才终止，
  成功一次就重来）。`run_utilize` 返回 True 只表示「选中卡 → 进好友结界 → 上式神流程走完」，`set_shikigami` 的成功是
  `not appear(stop_image)` 的负向 marker，**不是寄养已生效**；权威确认只有下一圈的 `not appear(I_UTILIZE_ADD)` + OCR 剩余时间。
  于是「按钮一直在 + 每次 `run_utilize` 都返回 True」时任务永不收敛（探针 200 次未退出），只能靠 Device 层
  `GameTooManyClickError` 等外部保护——而 `_perform_search_swipe` 等会 `click_record_clear()`，外层没有可靠的设备级兜底。
- **修复（只改 `tasks/KekkaiUtilize/script_task.py`，不新增配置项、不动 BaseTask、不动调度算法）**：
  - **总尝试计数** `utilize_total_attempts`：`check_utilize_add` 每次进入 `run_utilize` 前 +1，**永不因找到卡 / `run_utilize` 成功 /
    重开好友列表 / 回育成页而清零**，只在下一次独立的 `run()` 开头归零。上限 `UTILIZE_MAX_ATTEMPTS` = 6，即 3（每个寄养位的软失败上限，
    对应 `_record_utilize_failure`）× 2（育成页 / 调度设计上只有一个寄养位，留一位余量）。边界测试证明「2 个寄养位 ×（2 次软失败 +
    1 次成功）」恰好 6 次仍能正常完成，第 7 次才被拦。
  - **总耗时** `utilize_started_at` / `UTILIZE_TOTAL_TIMEOUT = 30 * 60`：`time.monotonic()`，`check_utilize_add` 首次进入时记一次，之后
    任何计数 / 选卡 / 重开列表都不重置。依据：一个寄养位最坏 3 次 ×（4 轮好友列表 × `SEARCH_PASS_TIMEOUT` 120s）= 1440s，取 1800s。这是
    **软边界**：只在控制权回到 `check_utilize_add` 循环顶端时才检查，底层调用（当时如 `switch_shikigami_class` 的无界 `while 1`，已在 §4.81 修复）
    真卡死时它不会生效。
  - **触发时**（`_utilize_convergence_exhausted` → `_stop_utilize_for_convergence`）：中文 `logger.error` + `push_notify` 写明原因
    （次数 / 耗时），复用 `_schedule_retry` 写**一次** 5~30 分钟重试（经静默窗口归一化），置 `utilize_terminal_failure`，返回 False；
    `run()` 复用 §4.78 的读回确认：已确认 → `raise TaskEnd`（调度器记成功，`next_run` 不再被改写）；读回不一致 → 仍按失败返回。
    没有新增任何 `try/except`，`GameStuckError` / `GamePageUnknownError` 等照常上抛。
  - **检查位置**：放在「`I_UTILIZE_ADD` 消失 → 按 OCR 成功调度」**之后**、导航到寄养页**之前**：已用满次数但按钮恰好消失的那一圈仍走
    正常成功调度；耗尽后不会再做任何多余的页面操作 / 收尾。
- **业务计数与总计数的区别**：`utilize_add_count` / `utilize_failed_count` 是业务计数（衡量「这一次寄养有没有做成」，可以也应该在
  推进时清零）；`utilize_total_attempts` 是收敛计数（衡量「这次任务总共折腾了几次」，不允许清零）。两者语义不同，不能合并。
- **测试**：新增 `tests/test_kekkai_utilize_convergence.py` 17 项（真实 `check_utilize_add` / `run()` + 受控替身；调度层用真实
  `Script.run` / `Script.loop` + 真实 `Config.task_delay` 落盘，临时配置、冻结时钟）：按钮恒在 + `run_utilize` 恒 True 且清零业务计数 →
  恰 6 次即止（旧探针 200 次不退出）；正常单 / 双寄养位不受影响、6 次边界恰好通过；找到卡但上式神无效；重复重开好友列表；总耗时用
  可控 `monotonic` 触发且选卡不重启计时；重试写入确认 / 未确认；系统异常不被吞（并断言新增 helper 里没有 `except`）；静默窗口归一化；
  两账号计数与调度互相独立；真实 `Script.loop` 下保护触发后其它任务照常被调度、失败计数不累计。10 组变异（移除次数上限 /
  找到卡时清零总计数 / 每圈重启计时 / 保护后继续寄养 / 重复写 `next_run` / 不看读回 / 上限缩成 3 误伤正常多位置 / 吞系统异常 / 耗时改用
  `time.time` / 耗时检查失效）全部被抓，每项独立 120s 上限，源码逐字节还原。全量 1583 → **1600/1600 OK**。
- **未修 / 待真机**：底层阻塞调用（软边界失效点；`switch_shikigami_class` 的无界 `while 1` 已在 §4.81 修复）；`run_utilize` True 仍是乐观成功；
  真实游戏里寄养点击后按钮是否会持续存在、保护触发后是否按 5~30 分钟重排——Level C 待验。`failure_interval` 死字段、OASX
  `success_interval` 文案本轮不动。

### 4.80 KekkaiUtilize 成功寄养后的独立随机延迟（`success_jitter_min/max`）

2026-09-20。规则见 `docs/DECISIONS.md` D023 补记（三）。**未 commit / push**。

- **新增配置**：`UtilizeScheduler.success_jitter_min` / `success_jitter_max`（`tasks/KekkaiUtilize/config.py`），单位分钟，默认
  **0~0**（不增加延迟），范围 0~720（`SUCCESS_JITTER_LIMIT_MINUTES`，12 小时，与 `UTILIZE_RES_TIME_MAX` 同量级），`min == max`
  = 固定延迟。字段风格与同组的 `cooldown_min/max`、`quiet_resume_jitter_min/max` 一致；三套区间（成功延迟 / 失败重试 / 静默恢复）互相独立。
  旧用户配置文件没有这两个键，由模型默认值补齐（加载不回写，不重算已有 `next_run`）。`config/template.json` 与
  `assets/i18n/zh-CN.json`（追加式，「成功后最小/最大随机延迟」+ 说明）已同步；OASX 用后端 schema 自动生成，无前端改动。
- **成功调度公式**（唯一实现点：`check_utilize_add` 的「育成页 `I_UTILIZE_ADD` 消失 → 读 OCR」块，`script_task.py`）：
  `base = max(now + OCR 剩余, now + min_run_interval)` → `candidate = base + 一次成功延迟` → 既有 `_schedule_target`
  （**一次**静默窗口归一化）→ `set_next_run`。「刚寄养成功」和「进入时已在寄养」共用这一块，所以同属正常成功路径。
  只有 **OCR 剩余时间有效**（非零、≤12 小时）才加延迟；OCR 兜底 5 分钟（同一块里的另一个分支）、无卡 / 3 次失败 / 导航失败的短期重试、
  6 次 / 1800 秒收敛保护、静默入口守卫、`utilize_enable=False`、OASX `sync_next_run` 都不使用它，不以 `TaskEnd` / 调度器成功标志判断。
- **采样**：`_success_jitter_delta()`，走同一个 `random_int`（SystemRandom）；`max == 0` 直接返回零延迟、**不采样**（0/0 与改动前逐秒一致，
  含微秒时钟下的截断）；每次成功调度至多一次，不缓存。**静默顺序**：延迟先加在候选值上、再一起归一化——落窗则 `07:00 + 静默抖动`
  （延迟被吸收，不再叠加）；候选恰好被延迟推出窗外（如 06:50 + 20 分钟 = 07:10）则保留 07:10，不采样静默抖动。
- **单字段保存**：OASX 草稿保存按「用户编辑顺序」逐字段 PUT，失败字段保持 dirty（`args_controller.dart:saveDraftChanges`）。
  `UtilizeScheduler` 原本**没有 `validate_assignment`**（`setattr` 不校验，任何值都会落盘，包括 min > max），所以本轮给它加了
  `ConfigDict(validate_assignment=True)`，并对成功延迟的两端各做一次交叉校验：违规的一端被拒绝、旧值不变、磁盘不写入中间态。
  代价：**单次保存里先落到的一端若造成 min > max 会失败**（如 0/0 → 30/90 先保存 min），再点一次保存即可（第二轮 max 已到位）；
  测试证明任何编辑顺序都在 ≤ 2 轮内收敛且每步落盘的都是合法区间。帮助文案提示「调高先改最大值」。
  **副作用**：`validate_assignment` 是整个 `UtilizeScheduler` 级别，所以同组 `cooldown_*` / `quiet_resume_jitter_*` 的单字段修改现在也会被校验
  （负数 / 越界 / `cooldown_max < cooldown_min` 被拒绝，此前会直接落盘并在运行时让 `random_int` 抛 `ValueError`）；合法编辑不受影响。
  加载期 `ConfigBase.__init__` 对越界字段仍是既有的「回退默认值」策略，`min > max` 仍抛错。
- **测试**：新增 `tests/test_kekkai_utilize_success_jitter.py` 45 项（公式 / 0-0 逐秒兼容网格 / 采样次数与边界 / 固定与独立采样 / 已在寄养 /
  地板先于延迟 / 静默落窗与出窗 / 不重复叠加 / 各非成功路径不采样 / 配置默认值·校验·单字段保存·OASX 草稿保存收敛·旧文件兼容·GET 与翻译 /
  真实 `Script.run` / `Script.loop` + 真实 `Config.task_delay`：两账号独立、恰写一次、`sync_next_run` 原样、其它任务照常调度）；18 组变异
  （不应用 / 0-0 仍采样或加延迟 / 双采样 / 误用于重试或 OCR 兜底 / 先归一化后叠加 / 恢复后重复叠加 / 账号共享 / 不落盘 / 读回失效 /
  校验失效（两端 + 赋值校验）/ 地板顺序 / 分钟换算 / 缓存随机值 / 取消上限）全部被抓，源码逐字节还原。改既有 `tests/test_kekkai_utilize_state.py`
  的 `_sched_cfg` 替身（加两个字段）。全量 1600 → **1645/1645 OK**。
- **未做 / 待真机**：真实寄养后的调度分布与 OASX 保存两轮的实际体验（Level C）；`switch_shikigami_class` 无界 `while 1`（已在 §4.81 修复）；
  同组 `cooldown_*` / `quiet_*` 字段仍没有 zh-CN 翻译（显示原文）。

### 4.81 式神分类切换有界化：`switch_shikigami_class` 不再是无界 `while 1`

2026-09-20。规则见 `docs/DECISIONS.md` D023 补记（四）。**未 commit / push**。

- **根因**：`ReplaceShikigami.switch_shikigami_class`（`tasks/Component/ReplaceShikigami/replace_shikigami.py`）是一个没有本地边界的 `while 1`，
  唯一退出条件是目标分类的「已选中」图标 `I_RS_*_SELECTED`（左下角固定 ROI，正向标志，重新截图后判定）出现。流程本是两步点击：点当前分类图标
  （`I_RS_ALL_SELECTED`，5 秒重点击间隔）展开分类 → 点目标分类（`I_RS_N` 等，3 秒间隔 + 位置稳定等待 ≤ 2.5 秒）。点击没生效 / 目标图标识别不到 /
  当前分类既不是「全部」也不是目标（三个分支都不命中，只剩截图空转）时都没有出口。真机上它只被 Device 的兜底间接截断：无点击 60 秒
  → `GameStuckError`；同一按钮 ≥ 10 次（或两个按钮各 ≥ 6 次）→ `GameTooManyClickError`。后者 **没有被 `run_utilize` 当业务失败处理**
  （只捕获 `GamePageUnknownError` / `GameStuckError`），会升级成 `Script._handle_task_exception` 的重启游戏。
- **调用者**：KekkaiUtilize 3 处（`run_utilize` 一处，`check_max_lv` 两处，后者只在 `auto_replace_max_level` 打开时执行）+ `Exploration/base.py:fill_shikigami`
  一处（只传一个位置参数）。`set_shikigami` 自带 120 秒超时并抛 `GameStuckError`，与本函数是两个独立步骤。
- **修复**：
  - **点击次数** `SWITCH_CLASS_MAX_CLICKS = 4`：每次真正点击（当前分类图标或目标分类）后累计，不因找到按钮 / 重新截图清零。依据：正常只有 2 步，
    允许整体再重复一轮（吸收一次丢失的点击）；且小于 Device 的两按钮各 6 次 / 单按钮 10 次，先触发的是业务失败而不是重启游戏。
  - **耗时** `SWITCH_CLASS_TIMEOUT = 30` 秒（`time.monotonic()`）：4 次点击最坏约 20 秒，加最后确认；小于 Device 的 60 秒无点击判定。**软边界**——只在控制
    权回到循环时检查，不能中断底层某次永久阻塞的调用。
  - **任务截止时间**：新增可选参数 `deadline`（绝对 `monotonic` 时间），与本地 30 秒取较早者；`run_utilize` 传 `self._utilize_deadline()`
    （= 本轮 `utilize_started_at + UTILIZE_TOTAL_TIMEOUT`），所以反复调用不会每次重新获得完整预算，预算用尽后再调用会在第一次点击前失败。`check_max_lv`
    的两处不传（它不属于寄养循环），只受本地上限约束。
  - **确认宽限** `SWITCH_CLASS_SETTLE = 3` 秒：点满次数后不再点击，再观察 3 秒（即目标按钮自身的重点击间隔）——最后一次点击「刚点中还没刷新」不会被误判失败。
  - **成功判定不变**：只认重新截图后目标分类的「已选中」图标；已经在目标分类时第一帧就成功（即使截止时间已过）。**没有新增图片资源**，也没有扩展分支
    （当前是「全部」和目标以外的分类时仍无法主动展开——现有判断能力的边界，交上限收口，不改业务）。
  - **失败传播**：达到次数或耗时上限 → 中文 `logger.error` + 抛既有的 `GameStuckError`。`run_utilize` 早已把它当软失败捕获（`_record_utilize_failure`，不再放置式神、
    不返回 True），累计到 3 次才由已有的 `_schedule_retry` 写一次 5~30 分钟重试（读回确认后 `TaskEnd`）；函数内部不安排重试、不写 `next_run`。
    `check_max_lv` 与 `Exploration` 调用者不捕获它，走 `Script._handle_task_exception`（与此前的 `GameTooManyClickError` 同样是重启路径）。
- **分类切换始终失败时**：单次调用最多点 4 次、约 20 秒内（先按次数收口；从不点击的情形 30 秒）；每轮任务最多调用 3 次（3 次软失败即终态），
  合计分类切换 < 90 秒，且受 6 次总尝试 / 1800 秒总预算约束；**不会**放置式神、**不会**判为寄养成功；最终恰一次短期重试
  （`now + 5~30 分钟`，静默窗口归一化，读回确认后正常结束），不使用成功随机延迟。
- **测试**：新增 `tests/test_shikigami_class_switch_bound.py` 23 项（真实 `switch_shikigami_class` + 会随点击 / 假时钟变化的假界面；真实 `run_utilize` /
  `check_utilize_add` / `run()`；真实 `Script.loop` + `Config.task_delay`）：已在目标 / 首次成功 / 多次成功 / 最后一次点击延迟刷新仍成功 / 图标始终在但无变化 /
  目标始终识别不到 / 点击无效 / 单调时间超限 / 任务截止时间与重复调用 / 失败不放置式神 / 只安排一次重试 / 重试未确认不冒充正常结束 / 正常寄养与成功调度不变 /
  Loop 下其它任务继续；假界面自带 400 帧硬上限。16 组变异（去次数上限 / 去耗时上限 / 忽略截止时间 / 用尽后当成功 / 点击即成功 / 找到按钮清零 / 去宽限 /
  上限失效或放大 / 不传截止时间 / 每次重置预算 / 重复安排重试 / 吞异常继续放置 / 读回失效 / 失败当成功）全部被抓，源码逐字节还原。全量 1645 → **1668/1668 OK**。
- **未做 / 待真机**：`unset_shikigami_max_lv` 同样是无界 `while 1`（只在 `auto_replace_max_level` 打开时执行，本轮范围外）；`click_record` 不会在 `run_utilize`
  多次失败之间清零，历史点击可能让 Device 的 `GameTooManyClickError` 先于本地上限触发（不动 Device）；点击间隔、宽限与 30 秒上限的真机校准（Level C）。

### 4.82 L1 + L2 公共点击与反应策略集成进 master（Level A/B）

2026-09-21。把 worktree `feature/l1-global-click-pipeline-v1`（L1 / L1.2）与 `feature/l2-interaction-reaction-layer`（含 L1 公共层选择性移植、
L2-1 / L2-2 / L2-3B Batch A）**选择性**并入当前 master 工作区。**未 commit / push**；§4.71~§4.74 是这些 worktree 当时的记录（编号预留），本节是落到
master 的最终状态。规则见 D026（L1）与 D001 补记（L2）。

- **基线差异审查**：master HEAD 已含 L1-1 的执行层（BehaviorTrace / `Control` minitouch dwell 45~130ms·mode 65 / 点击热点与采样器 / `reaction_profile`）；
  master 工作区在本轮前已单独移植过 `module/interaction_policy.py` 与 `FireReactionConfig`（8 任务 FIRE 延迟配置，字节级与 L2 一致）。缺的是：
  `module/click_pipeline.py`、`Control.click_with_backend` / `_dispatch_click`、`RuleList.last_ocr_hit`、`BaseTask.appear_then_click(policy=)`、L1 各 consumer、
  L2 迁移点位、FIRE Batch A owner 与它们的测试 / 文档。L2 worktree 的 HEAD 与 master 相同（`a5e2d7e6`），改动全部未提交，所以对 master 未改动的文件直接取用其版本，
  与 master 已改动的文件做 3-way 合并（FIRE 8 任务、GeneralBattle / GeneralInvite 只冲突在「master 的最小 FIRE 移植 vs L2 的 Batch A」，取 L2 侧且逐行核对 master
  独有行全是被取代的旧写法）。Settlement 的真实版本是 **SETTLEMENT CONTRACT V3 + Micro-Burst v1.2**（`SETTLEMENT_MAX_TOTAL_CLICKS=9`），GeneralBattle 主流程零改动。
- **Stage B（L1）**：新增 `module/click_pipeline.py`（`FinalPoint` / `ClickRegion` / `ClickBounds` / Rule 目标 → `execute_single_click`）；`Control` 增
  `click_with_backend`（百鬼夜行 window_message fast 后端保留，`_dispatch_click` 与 `click` 共用一段：取整 / 日志 / BehaviorTrace）；`RuleList.last_ocr_hit`；
  Stage B 结束时显式调用 `execute_single_click` 的调用点 25 处（**这是「显式声明非 Rule 坐标语义」的调用点数，不是享受 ROI 采样的点击数**——约 900 个 Rule / helper 点击早在 `Rule*.coord()` 里按 ROI 采样，见 §4.83；这 25 处由原裸 `device.click` / 后端直调迁入：GeneralBattle 绿标 ×2、GeneralRoom、Dokan ×2、EternitySea / FallenSun / Orochi / EvoZone 层数、Chess 发现卡、QuickLoadout ×4、
  SwitchSoul、SixRealms 购买区、WantedQuests、WeeklyTrifles ×2、RichMan、Navigator 保底点、百鬼夜行、`list_appear_click`）。**一次点击一个最终坐标**：L1 决定落点，
  `Control` 只执行已定坐标，BehaviorTrace 记录实际执行坐标，L2 只决定 reaction 时机、不再偏移。
  **例外（静态白名单逐条给理由，`tests/test_l1_click_pipeline.py::CANONICAL_DIRECT_CLICKS`）**：BaseTask primitive 自身（`coord()` 已采样一次后 `device.click`）、Settlement
  两个采样 / 执行点、GeneralInvite `_detect_select`、Navigator `_execute_action`、Kekkai `switch_friend_list`、RyouToppa `_click_toppa_area`、Secret / SixRealms peacock / Chess
  `_refresh_grigri_option`（已是 L1 合规的构造 Rule / 紧邻 canonical 采样器）；**项目排除**：WeeklyPurchase navbar（直点 `list_find` 已采样点，语义无歧义）、
  Login `_app_handle_login` / DailyTrifles `summon_recall`（synevo 小号轮换业务）。
- **Stage C（L2）**：`BaseTask.appear_then_click` 增 `policy=`（**不新增方法**；`policy` 与 `confirm_delay` 同时给 → `ValueError`；IMMEDIATE / 不传 = 旧立即点击；FIRE_SPECIAL / SPECIAL 被通用点击拒绝）；
  reaction → sleep → **新截图** → 同目标再识别 → 用新帧 `coord()` → 一次点击，目标消失零点击、不重试。28 个 `confirm_delay=REACTION_*` 迁成等价 `policy=`；L2-2 的 7 个 MIGRATE
  （GeneralInvite `I_ADD_*` ×4 NORMAL、GeneralBattle `I_PRESET` / `I_PRESET_WIT_NUMBER` NORMAL、`I_PRESET_ENSURE` CONFIRM）；FIRE Batch A：新增 `tasks/Component/fire_battle_entry.py`（`is_new_battle_entry` /
  `is_battle_result_residue`）与 EternitySea `_fire_eternity_sea_alone` / FallenSun `_fire_fallen_sun_alone` / Sougenbi `_fire_sougenbi`（分类 → 采样任务 `fire_reaction` → sleep → 新截图重确认 → 点一次 →
  有界等正向进入准备 / 战斗页）。**Orochi 野队 `run_wild` 按项目决定不带入**（保持原状，测试里删除对应用例并把清单行改回 KEEP_SPECIAL）。同一个 FIRE 事件只有一个 reaction owner
  （任务 `fire_reaction`），不叠 `policy` / `confirm_delay` / 普通策略；Settlement 与 KekkaiUtilize 没有任何 policy / confirm_delay。
- **Stage D（全仓调用点）**：新增 `dev_tools/click_callsite_register.py` + 生成的 `docs/L2_CALLSITE_REGISTER.md`：`tasks/` + `module/` 共 **1092** 个点击调用点（AST；不含 tests）。
  **basis=human 179**（L2-2 逐点人工审计，沿用结论）、**basis=rule 913**（保守规则分类，**不是逐点人工审计**）。decision（Stage 2 之后重排规则：受保护模块里的执行器点击仍按 R3 归 KEEP_SPECIAL，现值 KEEP_IMMEDIATE 627 / KEEP_SPECIAL 228，其余不变；此处为当时口径）：MIGRATE 7 / ALREADY_L2 33 / KEEP_IMMEDIATE 637 / KEEP_SPECIAL 218 /
  NEEDS_C 24 / PRIMITIVE 35 / EXCLUDED 138（WeeklyPurchase 55 + DailyTrifles 38 + SwitchAccount 25 + Login 20，互斥可加总）。L1：显式 `execute_single_click` 调用点 25 处（Stage B 口径，Stage 1 之后为 33，见 §4.83）；`policy=` 32 处；legacy `confirm_delay=` 3 处
  （`check_lock` 透传 ×2 + RealmRaid 再次挑战确认 ×1）。**规则分类后没有任何新增点位满足「无需真机证据即可迁移」**：剩余 NEEDS_C 24 处（Buy 2 / GeneralBattle 准备页弹窗 2 / GeneralInvite 队员接受 5 /
  DemonRetreat 1 / Dokan 1 / Duel 2 / Pets 1 / Quiz 1 / SixRealms 9）都是「可能适合 reaction、时效 / 协作节奏无法静态判断」，等 Level C；不为提高迁移率强行加延迟。
  `ui_click*` / `ocr_appear_click` / `self.click(Rule)` 无 policy 参数，本轮不扩公共 API（KEEP_IMMEDIATE）。
- **测试**：新增 `tests/test_l1_l2_integration.py` 22 项（真实 `BaseTask.appear_then_click` + 真实 `Control.click` + 采样器计数：一个动作一次采样 / reaction 之后才用新帧采样 / 目标消失零采样零点击 / 目标移动用新框 /
  IMMEDIATE·旧接口不变 / policy+confirm_delay 拒绝 / Control 不加抖动；Settlement / FIRE owner / Kekkai / Navigator / Orochi 野队的延迟所有权静态守卫；登记册与源码对账与 NEEDS_C 钉住；真实 `Script.loop` 下 reaction 耗时不进 next_run）；
  移植 `tests/test_l1_click_pipeline.py`（去掉 WeeklyPurchase 用例、白名单加项目排除项）、`test_l2_interaction_reaction.py`、`test_l2_policy_migration.py`、`test_fire_batch_a.py`（删 Orochi 野队用例 / 清单行）及 9 个既有测试文件的
  L2 断言；`tests/test_fire_reaction_task_config.py` 对 EternitySea / FallenSun / Sougenbi 改为驱动 Batch A 真实 owner（旧的「朴素 FIRE 循环」替身在新 owner 下会挂死，已替换）。
  16 组变异全部被抓（L1 重复采样 / L2 用旧截图 / 目标消失仍点击 / FIRE 双重反应 / 结算叠普通策略 / FinalPoint 再偏移 / 后端分派丢失 / 旧接口破坏 / 三处近期寄养修复被覆盖 / 野队被扩展 /
  列表点击退回裸点 / 百鬼夜行绕过执行器 / 未审计模块偷带 reaction / Kekkai 带 reaction），源码逐字节还原。全量 1668 → **1809/1809 OK**。
- **数据**：真实 `config/oas1.json` / `oas2.json` 本轮开始前已被外部（OAS 服务 / 用户）在 11:55 写过一次（与上一轮哈希不同），本轮全程哈希与修改时间不变。
- **未做 / 待真机（Level C）**：NEEDS_C 24 处；Batch B（AreaBoss / Secret / DemonEncounter）仍待逐项审查；Orochi 野队（项目排除，且 `I_OROCHI_WILD_FIRE` 无 RuleImage 断链）；
  `ui_click*` 透传 policy 的设计；Navigator 逐 edge NAVIGATION 元数据；`RR_AGAIN_CONFIRM_DELAY` 是否归入 CONFIRM；全部 L1 consumer 的落点分布与 L2 reaction 数值都是 PROVISIONAL。
  **不能报告「全阶段正式验收完成」**。

### 4.83 L1 Stage 1：BaseTask 公共单击 primitive 的执行入口统一到 `execute_single_click`

2026-09-21。依据只读的《L1 全仓 ROI 与点击落点专项审查》。**只换执行入口，不改 ROI / 采样 / 落点分布**。**未 commit / push**。

- **审查结论（纠正此前表述）**：`Rule*.coord()`（`RuleClick` / `RuleImage` / `RuleOcr` / `RuleGif`）早已统一走 `ClickSampler.sample_target(roi_front, name)`，所以约 887 个 Rule / helper
  生产消费点本来就在 ROI 内采样一次；此前「25 处」只是显式调用 `execute_single_click` 的调用点（要为非 Rule 坐标显式声明语义），**不是**能享受 L1 的点击数。真正缺的是
  **执行入口未统一**：BaseTask primitive 采样后直接 `device.click`。
- **改了什么（`tasks/base_task.py` 的 8 个执行点，均为「保持原时机的 `coord()` 采样一次 → `FinalPoint` → `execute_single_click`」）**：`appear_then_click` 4 处（reaction 路径无 action /
  RuleClick action，立即路径无 action / RuleClick action）、`wait_until_appear_then_click` 2 处（无生产调用方，保持原语义：始终用 `target.coord()`）、`click` 1 处、`ocr_appear_click` 1 处
  （无 action 分支）。**没有**把 Rule 直接交给执行器（那会 `coord()` 之后再采一次）；`control_name` 逐点保持（`appear_then_click` 传 action 时仍是 `target.name`）；返回值、点击 / 截图次数、
  识别顺序、L2 的 reaction → 新截图 → 再识别 → 新帧 `coord()` 顺序、异常传播、Control 后端分派全部不变。长按（6 处 `device.long_click`）本阶段不动。调用形式由位置实参变为
  `x=… y=… control_name=…` 关键字实参（执行器统一约定），3 个既有测试的 Mock 断言同步改成关键字形式（语义不变）。
- **修复**：`ocr_appear_click` 的 action 分支原先 `x, y = action.coord()`（采样后丢弃）再 `self.click(action, interval)`（内部又采一次）——一次点击采样两次。`action.coord()` 只是纯采样（无识别 /
  状态副作用），已移除，最终仍只采样一次（`self.click` 内）。副作用：随机数序列位移一位（分布不变）。
- **覆盖统计（AST，`dev_tools.click_callsite_register`）**：BaseTask 直接 `device.click` 8 → **0**；BaseTask 内 `execute_single_click` 1 → **9**（8 + 既有 `list_appear_click`）；显式执行器调用点 25 → **33**；
  仍是裸点 24 → **16** = 底层与非点击 4（执行器自身 2、minitouch `__main__` 1、`scroll_window_message` 1）+ 生产消费 9 + 项目排除 3。经 primitive 汇入执行器的
  Rule / helper 生产消费点 887（另有 135 个在项目排除模块里，同样经过 primitive）。**不是 100% 全仓 L1**：剩余 9 个直接点击（已在 §4.84 迁完）、长按、项目排除项留待后续阶段。
- **测试**：新增 `tests/test_l1_stage1_primitive_execution.py` 27 项（真实 `BaseTask` 方法 + 真实 `Control.click`（假后端）+ 真实 BehaviorTrace + 包装采样器 / 执行器：一次点击 = `sample_target` 1 次 = 执行器 1 次（实参是
  `FinalPoint`）= 后端 1 次；action 与 target 不同时 `control_name` 仍是 `target.name`；L2 NORMAL 在 reaction 后的新帧采样、旧框从未被采样、目标消失零采样零点击；IMMEDIATE / 旧 `confirm_delay` 不变；
  策略冲突拒绝；`ocr_appear_click` 一次采样；OCR 未命中零点击；长按不进单击执行器；`ui_*` helper 经执行器；连续点击各自独立采样；后端异常原样传播；AST 静态守卫）；更新
  `tests/test_l1_click_pipeline.py` 的静态白名单（去掉 8 个 base_task 项，`ConvertedSitesGuardTest` 加入 4 个函数）与 `test_l1_l2_integration.py` 的统计断言。12 组变异全部被抓。全量 1809 → **1836/1836 OK**。
- **未做（后续阶段，待用户确认）**：9 个生产直接点击（Chess / Settlement ×2 / GeneralInvite / Navigator / Kekkai / RyouToppa / Secret / 孔雀国）、长按执行入口、全局静态守卫收紧、BehaviorTrace 补 ROI / 来源字段、
  ROI 质量审计（Level C）。WeeklyPurchase / synevo 模块仍是项目排除项。

### 4.84 L1 Stage 2：剩余 9 个生产直接单击迁入 `execute_single_click`（生产直接单击归零）

2026-09-21。**只迁执行入口，采样保持在原位置、用原采样函数与原参数**。**未 commit / push**。

- **复核**：迁移前重新 AST 扫描，生产直接 `device.click` 仍恰为这 9 处（Chess `_refresh_grigri_option`、Settlement `_sample_settlement_click` / `_click_settlement_point`、GeneralInvite
  `_detect_select`、Navigator `_execute_action`、Kekkai `switch_friend_list`、RyouToppa `_click_toppa_area`、Secret `find_battle`、孔雀国 `_mark_peacock_boss`），无新增；**没有统计误分类**——
  `_sample_settlement_click` 是「采样并立即点击」（`sample_region` 后 `device.click`），`_click_settlement_point` 是 burst 内执行已采样锚点，两者都是真实点击。
- **改法（逐点）**：坐标仍由原表达式产出一次，已确定的坐标以 `FinalPoint` 交给执行器（执行器对它零采样）——Chess（两次点击各自 `refresh_rule.coord()`，不复用）、GeneralInvite
  （保留 `ClickSampler.sample_target(select_area, rule.name)`，**没有**改 `ClickBounds`：它对退化框取中心、对浮点框取整，与原采样在边界上不等价）、Navigator（`action.coord()`，无 interval 的即时点击，不加等待）、
  Kekkai（目标图片未出现时沿用资产 ROI 的 `check_image.coord()`，不新增识别 / 重试）、RyouToppa（保留 `sample_point(roi, wide_card)` 显式 opt-in，不换成 `sample_target`）、Secret（人工 `click_roi` 不变，
  两次点击各自 `click_rule.coord()`）、孔雀国（`C_PK_GREEN_MAIN.coord()` 一次）、Settlement 锚点点击（`FinalPoint`，burst 内复用同一个点，零采样）。**唯一用 `ClickRegion` 的是
  `_sample_settlement_click`**：它的解析就是同一个 `ClickSampler.sample_region(roi, name)`，同 ROI、同身份、一次采样，逐字等价。结算状态机、点击次数与节奏、Reward / Result 安全区域没有改动。
- **等价性证据**：(1) 迁移前源码快照以别名模块加载，与迁移后真实模块在**同一 seed、同一 fake 输入**下对照：12 个场景 × 3 个 seed，`device.click` 的 (x, y, control_name) 序列与截图 / 识别 / 等待次数逐项相等
  （一次性对照，仓库外）；(2) 新增 `tests/test_l1_stage2_direct_clicks.py` 18 项，用固定随机源（`module.click_sampler._rng` 与 `module.base.utils.random._rng` 同一个 `random.Random`）把
  「迁移前的采样表达式」作为独立参考，断言后端坐标逐个相等，并包装采样器 / 执行器断言采样种类、ROI、身份、次数、`FinalPoint` / `ClickRegion`、`control_name`、等待 / 截图 / 识别次数与 BehaviorTrace 坐标；
  另有 AST 静态守卫（9 个函数无 `device.click`、采样调用原位保留、Navigator 无 sleep、Kekkai 仍只有一次 `appear`）。
- **既有测试的同步**：4 个「源码字符串」断言（Chess / Secret 的 `coord()` 先于 `device.click(`、GeneralInvite / Secret 在 `t7_5_stage2`、Settlement 的 `ClickSampler.sample_region(...)` 字面）改成新的结构形式并补运行期断言
  （`sample_region` 恰一次、参数是选定 region 的 roi_front 与名字、`sample_target` 从未被调用），没有删除或放宽；`test_l1_click_pipeline.py` 白名单去掉 9 项、`ConvertedSitesGuardTest` 加入 9 个函数。
- **覆盖统计（AST）**：生产直接单击 9 → **0**；显式执行器调用点 33 → **42**；裸点 16 → **7** = 底层与非点击 4 + 项目排除 3（Login / DailyTrifles / WeeklyPurchase）；长按 `device.long_click` 仍 6 处。
  登记册规则调整：受保护模块（Settlement / Kekkai / FIRE 任务 / Chess 等）里已走执行器的点击仍按 R3 归 KEEP_SPECIAL（执行器只是执行入口，不改变「由状态机拥有 timing」），
  decision 变为 KEEP_IMMEDIATE 627 / KEEP_SPECIAL 228，其余不变。
- **测试**：新增 1 个文件 18 项；修改既有测试文件 5 个（`test_l1_click_pipeline.py`、`test_t7_5_stage2.py`、`test_general_battle_settlement.py`、`test_l1_l2_integration.py`，另 `dev_tools` 登记册规则），删除 0；
  15 组变异（恢复裸点 / Rule 双采样 / 锚点重采样 / 采样函数产生点击 / Chess 复用同一个点 / GeneralInvite 采样模式改变 / RyouToppa 丢 wide_card / Secret ROI 扩大 / Navigator 加等待 /
  Kekkai 多一次识别 / control_name 改变 / 执行器丢 control_name 与后端参数）全部被抓。全量 1836 → **1854/1854 OK**。
- **未做（后续阶段，待用户确认）**：长按独立执行入口、把静态守卫收紧为「执行器之外零直接点击」的正式规则（目前白名单只剩执行器自身与项目排除项）、BehaviorTrace 补 ROI / 来源字段、ROI 质量审计（Level C）；
  WeeklyPurchase / Login / DailyTrifles 仍是项目排除项。

### 4.85 L1 Stage 3A：长按执行入口统一到独立的 `execute_long_click`

2026-09-21。**只换执行入口，不改采样 / 时长 / 后端分发 / 等待**。**未 commit / push**。

- **审计（只读，先于改动）**：生产里 `device.long_click` 恰 6 处，全部是 BaseTask primitive（`appear_then_click` ×4：立即 / reaction 路径各「`action.duration` / 显式 `duration`」两支，
  `wait_until_appear_then_click` ×1，`click` ×1）；没有其它生产旁路——`long_click_<后端>` 直调只有 `windows_impl.py` 的 `__main__` 演示，`u2.long_click` 只在 uiautomator2 后端内部。
  生产真实的 `RuleLongClick` 资产共 10 个（CollectiveMissions `L_FEED_CLICK_1~4` / `L_SL_LONG`、Exploration `L_ROTATE_1~4`、SoulsTidy `L_ONE`，时长都是 1500ms），**全部经 `BaseTask.click`**；
  另 5 个点位（`appear_then_click` / `wait_until_appear_then_click` 带长按 action）当前没有生产调用者（潜在路径，`SwitchSoul` 只是透传 `action` 形参）。`RuleLongClick` 自带 `duration`（毫秒），
  调用方 `/ 1000` 成秒后交给 `Control.long_click(x, y, duration, control_name)`。没有用「多次单击 / 滑动」模拟长按的生产写法；Chess `press_and_drag`（minitouch 按住拖拽）与 `swipe*` 属手势，不在范围。
- **改法**：`module/click_pipeline.py` 新增 `execute_long_click(device, target, duration, control_name=<缺省哨兵>)`——目标经既有 `resolve_click_point`（`FinalPoint` 零采样；直接传 Rule 才采样一次），
  然后**恰一次**调用 `device.long_click(x=, y=, duration=, control_name=)` 并返回落点。`duration` 原样透传（秒 / 区间 / `None` 都不加工，不叠加单击 dwell，不重新随机）；`control_name` 显式传入
  （含 `None` / 空串）一律原样透传，仅在完全不传时回退 `target.name or 'LongClick'`。执行器不 sleep、不截图、不重试、不吞异常；后端选择 / `handle_control_check` / BehaviorTrace 仍全在 `Control.long_click`。
  6 个 BaseTask 点位保持 `x, y = <target/action>.coord()` 在原位置一次采样，再 `execute_long_click(self.device, FinalPoint(x, y), <ms> / 1000, control_name=<原名字>)`；
  `wait_until_appear_then_click` 的长按点位仍取 `target.coord()`（不是 action 的 ROI）——既有行为原样保留，没有顺手「修正」。单击执行器依旧拒绝 `RuleLongClick`，长按执行器不接管任何单击。
- **后端矩阵（不改变）**：`Control.long_click_methods` = ADB / uiautomator2 / minitouch / scrcpy（+ Windows 上 window_message）；未配置的 `control_method`（含 `nemu_ipc`，虽有 `long_click_nemu_ipc` 但没注册）
  仍回退 `long_click_adb`；`long_click_adb` 里「0<duration<3 之外按毫秒处理」等历史启发式原样不动。BehaviorTrace 仍由 `Control.long_click` 记 `action=long_click`、`extra={x, y}`（不含 duration，未扩 schema）。
- **等价性证据**：(1) 迁移前 `base_task.py` 源码快照以别名模块加载，与迁移后真实模块在**同 seed、同假后端**下对照：7 个场景（4 个 `appear_then_click` 变体 / `wait_until_appear_then_click` / `click` ×2）×
  6 种 control_method（含未注册回退）× 3 个 seed × 正常 / 后端抛异常，共 252 组，后端收到的 (后端, x, y, duration)、sleep / reaction / 截图序列、返回值、BehaviorTrace 行、异常类型与消息逐项相等，且从未出现单击后端调用
  （一次性对照，仓库外）；(2) 新增 `tests/test_l1_stage3a_long_click.py` 40 项：执行器契约（`FinalPoint` 零采样 / Rule 采样恰一次且等于 `coord()` 参考值 / `duration` 原样 `is` 透传 / `control_name` 哨兵语义 /
  无 sleep 无截图 / 异常同一对象 / 非法目标与单击执行器同一 `TypeError`）、真实 `Control.long_click` 链路（5 种后端各自恰一次且参数一致、未注册回退 adb、`Control.click` 与单击后端从未被调、trace 一条 `long_click`
  无 `click`、后端失败无 trace 行、control_check 异常先于后端）、6 个点位的真实 primitive 链路（一次长按 = 采样 1 次 = 执行器 1 次（`FinalPoint`）= 后端 1 次；L2 长按流程与同一流程的单击版本逐事件相同，仅最后动作不同）、
  固定随机源下与「迁移前表达式」（`coord()` + `duration / 1000` + 原 `control_name`）逐值相等、10 个真实生产资产逐个覆盖、AST 静态守卫。
- **覆盖统计（AST，`dev_tools.click_callsite_register.scan_long_click_sites`，登记册新增 §2.2）**：BaseTask 直接 `device.long_click` 6 → **0**；BaseTask 内 `execute_long_click` 0 → **6**；生产消费点直调长按 **0**；
  执行器自身 1 个直调出口（`device.long_click`）+ `module/device/` 后端内部 2 处（u2 / windows 演示）；拖拽 / 滑动未误入长按执行器。单击统计不变（生产直接单击 0、显式单击执行器 42、裸点 7 = 底层 4 + 项目排除 3）。
- **测试**：新增 1 个文件 40 项；修改既有测试文件 1 个（`test_l1_stage1_primitive_execution.py`：把「长按 6 处未变」的静态断言改为「直调 0 / 执行器 6」，并更新文档字符串与注释，未删除任何用例）；删除 0；
  21 组变异（长按执行器改调 click / 落点二次采样 / 落点被偏移 / 丢 duration / 毫秒未换算（3 个 primitive 各一）/ 执行器内再乘 1000 / 叠加单击 dwell / 调用两次 / control_name 改写与空值回退 / 绕开 `Control.long_click`
  直调 adb 后端 / 吞异常 / 两个点位恢复直调 / 滑动误入长按执行器 / Rule 直接交给执行器 / 长按降级为单击 / 单击执行器接受长按 / wait 路径改采样 action）全部被抓，源码逐字节还原（哈希一致）。全量 1854 → **1894/1894 OK**。
- **未做（Stage 3B，待用户确认）**：把静态守卫收紧为「执行器之外零直接点击 / 长按」的正式全局规则（目前白名单只剩执行器自身、`module/device/` 内部与项目排除项）；BehaviorTrace 补 ROI / 来源 / duration 字段；ROI 质量审计（Level C）；
  `nemu_ipc` 长按未注册是否补齐（既有行为，本轮不动）。WeeklyPurchase / Login / DailyTrifles 仍是项目排除项。

### 4.86 L1 Stage 3B：原项目排除模块的最后 3 处单击迁入 L1 + 全局静态守卫

2026-09-21。**决定：项目业务排除 ≠ 点击架构豁免**——只要代码真实存在于当前 master 并属于生产点击，就必须走 L1 执行器。WeeklyPurchase 仍**不做** L2 Reaction Policy / FIRE 改造
（这是 L2 的排除，未变）；这里只统一「执行入口」。**未 commit / push**。

- **复核**：迁移前用 AST（含别名 / 非调用引用 / `getattr`）重新扫描 `tasks/` + `module/` + 仓库根脚本，生产直接单击恰剩 3 处（无新增、无别名漏报）：WeeklyPurchase `MallNavbar.click_and_check`、
  DailyTrifles `ScriptTask.summon_recall`、Login `LoginService._app_handle_login`；SwitchAccount / AccountRotation / MultiAccountEvo 没有直接点击。未带入任何 synevo 独有功能。
- **改法（等价迁移：原坐标表达式不变，已定坐标 → `FinalPoint` → `execute_single_click`）**：
  - WeeklyPurchase：`pos` 是 `list_find`（图片列表）已 `coord()` 采样的最终坐标，循环内同一个 `pos` 最多点 6 次，以 `FinalPoint(pos[0], pos[1])` 原样执行，`control_name` 逐值保留；不重新识别 / 采样、无新增等待。
    `list_find` 未命中返回 `False` 时仍零点击零截图。
  - DailyTrifles：`list[i].coord()`（`RuleOcr.coord()`，每次点击恰采样一次）→ `FinalPoint`；原写法没传 `control_name`（Control 默认 `'Click'`），迁移后保持不传，日志 / trace 名字不变；OCR 识别调用次数不变、不点 `(0,0)`。
  - Login：固定坐标 `(106, 535)`（误入区服设置的兜底点）→ `FinalPoint(106, 535)`，**不随机化、不猜 ROI**，`control_name` 仍是默认 `'Click'`。统一执行入口 ≠ 改落点；若要改善这个点，必须先有可靠 ROI 证据，另行实施。
- **等价性证据**：(1) 迁移前源码快照以别名模块加载，与迁移后真实模块在**同 seed、同假后端**下对照：8 个场景（WeeklyPurchase 命中 / 一直不出现 / list_find 未命中 / 浮点坐标，DailyTrifles 首次 / 第二次命中 / 从不命中，
  Login 误入区服点击）× 5 种 control_method（含未注册回退）× 3 个 seed × 正常 / 后端抛异常，共 240 组，后端 (后端, x, y)、截图 / sleep / 识别序列、返回值、BehaviorTrace 行、异常类型与消息逐项相等（一次性对照，仓库外）；
  (2) `tests/test_l1_stage3b_global_guard.py` 的运行期用例以「迁移前表达式」（`coord()` 固定随机源结果、原坐标字面量、原 control_name）为独立参考，并用采样函数「一调用就失败」的补丁证明已采样坐标不再采样。
- **全局静态守卫（`dev_tools/click_entry_guard.py`，测试 `tests/test_l1_stage3b_global_guard.py`）**：
  - **范围**：`tasks/` `module/` `deploy/` 与仓库根 `*.py` 的**实际文件**（rglob，新建文件自动被扫；另有测试要求「含 Python 的顶层目录必须显式归类为生产或非生产」）。tests / dev_tools / toolkit 等是非生产。
  - **识别（AST，不是单一正则）**：设备类接收者（`.device` 链、`device` 参数、`dev = self.device` 别名传播、`Control.` / `Device.` 类限定）上的 `click` / `long_click`；任何接收者上的 `click_with_backend` / `multi_click` /
    `click_<后端>` / `long_click_<后端>`（后端名取自 `module/device/method` 的真实定义）；对这些方法的**非调用引用**（赋值 / `partial` / 字典）；`getattr(x, 'click')` 字面量；`getattr(设备, 变量)` 无法静态确定，单独列 `unresolved`（当前 0，出现即失败待人工判定）。
    `click_record_*`、`self.click(rule)`、`click_and_check`、`swipe` / 拖动、无关对象的 `.click()` 不误报。
  - **默认禁止 + 精确白名单**：`ALLOWED_EXITS` 共 22 条，逐条精确到（文件, 函数, 调用形式, 次数）并写明层与原因——执行器 3（`execute_single_click` 的 `device.click` / `click_with_backend`、`execute_long_click` 的 `device.long_click`）、
    Control 13（后端注册表 / 兜底后端引用）、后端 3（uiautomator2 单击 / 长按、window_message 滚动内部点击）、演示入口 2（`__main__`）、死代码 1（`Control.multi_click`，此前发现其实现有误，只登记不修改）。
    **不按文件 / 目录豁免**；Login / DailyTrifles / WeeklyPurchase 没有任何条目。白名单条目在源码里找不到或次数不符 → 同样失败（防止删了合法出口仍报「覆盖完整」），必需出口缺失也失败。
  - **失败信息**：`文件:行号 函数 违规形式 → 建议使用的 L1 入口`。失败时**必须迁移到执行器，不得靠新增白名单消除**。
  - **边界**：静态守卫只证明「没有绕过执行器的直接调用」，不证明业务点击执行成功，也不证明坐标分布；这些由运行期等价测试负责。动态构造的调用（如 `getattr` 变量名、运行期拼装的方法名）、业务类继承 Control 后用 `self.click` 等超出静态可证范围的情形是剩余风险，靠 `unresolved` 单列与运行期测试兜底。
- **覆盖统计（AST）**：BaseTask 直接单击 0 → 0；生产直接单击 0 → 0；项目排除模块直接单击 **3 → 0**；BaseTask 直接长按 0 → 0；生产长按旁路 0 → 0；显式单击执行器调用点 42 → **45**；显式长按执行器调用点 6 → 6。
  登记册裸点 7 → **4** = 全部是底层 / 非点击（执行器自身 2、minitouch `__main__` 1、`scroll_window_message` 1）。项目排除模块的 138 个登记点位仍按 L2 口径标 EXCLUDED，其中 `self.click` / `appear_then_click` 等本来就经 BaseTask primitive 进入 L1，
  剩余 3 个直接点击已迁移，模块里没有别的直接点击。登记册新增 §2.3 汇总守卫结果。
- **测试**：新增 1 个文件 54 项（3 个调用点的运行期等价 + 全局不变量 + 守卫对真实仓库 / 违规注入 / 新文件发现 / 过期白名单的检验）；修改既有测试文件 2 个（`test_l1_click_pipeline.py`：`CANONICAL_DIRECT_CLICKS` 去掉 3 个排除项；
  `test_l1_l2_integration.py`：执行器调用点 42 → 45、裸点 (4,0,3) → (4,0,0)、生产裸点断言不再豁免排除模块），删除 0；21 组变异（恢复三个裸点 / BaseTask 新增裸单击与裸长按 / 新建任务文件带裸点 / 组件调 `click_with_backend` /
  任务直调后端 / 单击改长按与长按改单击 / `FinalPoint` 偏移 / Rule 双采样 / Login 落点随机化 / 守卫豁免 Login 目录 / 守卫漏扫嵌套新文件 / 守卫不核对过期与必需出口 / 守卫整文件放行 / 忽略非调用引用 / 不传播别名 /
  忽略动态 getattr / 删除合法长按出口）全部被抓，源码逐字节还原、临时新增文件已删除（哈希一致）。全量 1894 → **1948/1948 OK**。
- **未做（Level C / 后续，待用户确认）**：ROI 质量审计（Login 固定坐标是否落在真实可点击区域、小目标 / 退化 ROI、大随机区域 Point 与 Region 语义）需真机或离线标定；BehaviorTrace 补 ROI / 来源 / duration 字段；`nemu_ipc` 长按未注册（既有行为）；
  L2 对 WeeklyPurchase 的 Reaction Policy 仍不做。

### 4.87 L2 Stage C1-A1：C0 复核后首批 4 处 Reaction Policy 迁移

2026-09-21。依据外部 C0 审查（Remaining Reaction Audit：原 24 个 NEEDS_C 全部仍在、均未迁移；建议 MIGRATE 10 / KEEP_IMMEDIATE 3 / KEEP_SPECIAL 4 / NEEDS_C 7）只实施 MIGRATE 里确认的**前 4 处**，
其余不动。**未 commit / push**。C0 报告本身不在仓库里，登记册只记录本轮实际迁移的点位，其余 C0 建议**不提前改判**。

- **复核（迁移前）**：4 处都是单次 `appear_then_click`，均在有界外层里，且没有别的 reaction owner；目标都最终经 L1 `execute_single_click`。真实 `appear_then_click(policy=)` 链路 = interval 闸门 → 当前帧识别 →
  reaction 采样一次 → `sleep` → fresh 截图 → 同一目标重识别 → 新帧 `coord()` 一次 → `FinalPoint` → L1；目标消失零点击返回 `False`。
- **改法（每处只加 `policy=`，无重构，不改 L1 / `interaction_policy` / `Control` / `base_task`）**：

  | 模块 | 函数 | 目标 | Policy | reaction |
  | --- | --- | --- | --- | --- |
  | Dokan | `priority_enter_dokan` | 动态 `target_priority`（`interval=1.2` 不变） | NORMAL | 0.45~0.85s |
  | Pets | `_feed`（仅「已投喂」分支） | `I_UI_BACK_CIRCLE` | NAVIGATION | 0.55~1.10s |
  | SixRealms | `refresh_store` | 动态 `refresh_rule` | CONFIRM | 0.55~1.20s |
  | SixRealms | `choose_and_enter_island`（`interval=0.8` 不变） | 动态 `target_land` | NORMAL | 0.45~0.85s |

- **业务兼容性（逐项查证，无需额外代码修复）**：
  - **Dokan**：`priority_enter_dokan` 是 `page_dokan_priority → page_dokan` 边的 callable 动作，由 Navigator `_execute_transition` 在 `Timer(6.0)` **墙钟**预算里循环调用；页面到达等待 `_wait_for_destination` 默认 4.0s 不变。
    reaction 现在计入这 6 秒：一次成功 attempt = 循环顶截图 + reaction + fresh 截图，约 0.95~1.35s；fresh confirm 持续失败时 Navigator 仍正常超时（`add_penalty` 分支）——虚拟时钟实测 reaction 取下限 / 上限时分别
    尝试 7 / 5 次、约 6.65 / 6.75s 退出（最多超出预算一次 attempt），零点击。**不能说「总耗时不变」**：成功路径多耗约 1s，预算内可重试次数变少。另一个细微变化：policy 路径的 interval 计时器只在点击后重置
    （立即路径在识别成功时就重置），fresh 失败后下一轮可立即重试，但仍受 6 秒预算约束。失败由原 Navigator 重试路径接管，没有新增业务重试。
  - **Pets**：仅 `number == 0`（已投喂）时才识别返回按钮并 reaction；成功 → 点一次 → `goto_page(page_main)`；fresh confirm 失败 → 不点，仍走 `goto_page(page_main)` 收口；没有重复导航 / 无界循环，`_feed` 返回值仍是 `None`。
  - **SixRealms 刷新**：`refresh_store` **原本就**用 `if not self.appear_then_click(...): return False`，False 分支不进入 `wait_animate_stable(timeout=1.5)` 与「刷新成功」，所以**不需要控制流修复**。刷新次数 OCR 判断不变（读的是 reaction 前那帧）。
    调用方 `buy_skill` 遇到 `False` 会 `break` 结束本次购买（既有行为）；现在多了一种触发路径：刷新图标在 reaction 期间消失也会让本次购买提前收口，不会误刷新、不会无界重试。
  - **SixRealms 岛屿**：同一帧「识别全部 → 过滤 → 取第一个」的规则不变；reaction 后只 fresh confirm **原选定**的岛屿——移动则用新帧坐标，消失则零点击，不点旧坐标，也不改点旧帧里的其它岛屿；由外层
    `run_on_*` 下一轮重新扫描。fresh 帧是新截图，批量匹配缓存按 `frame_id` 失效，不会拿旧 ROI。
- **测试**：新增 `tests/test_l2_stage_c1_a1.py` 32 项（真实业务函数 + 真实 `BaseTask.appear_then_click` + 真实 `Control.click`（假后端）+ 真实 BehaviorTrace，帧序列驱动；每处覆盖 policy 区间 / reaction 一次 / fresh 截图 /
  新帧坐标 / 采样一次 / L1 一次 / 目标消失零点击 / 目标未出现不 reaction，外加 Dokan 用真实 `GameUi._execute_transition` + 虚拟时钟的 6 秒预算与重试 / 超时场景、Pets 真实 `run()` 的后续导航、
  SixRealms `buy_skill` 刷新失败收敛、岛屿过滤策略与「不改选」）；修改既有测试 2 个：`test_l1_l2_integration.py`（`policy` 声明允许 basis=c0 且必须在 `C1_MIGRATED` 逐点登记、policy 点位 32 → 36、
  NEEDS_C 按模块钉住 Dokan 1 / Pets 1 / SixRealms 9 → 0 / 0 / 7）与 `test_l2_interaction_reaction.py::test_case35_ordinary_reaction_consumers_use_policy`（policy consumer 按文件钉住，加入 Dokan 1 / Pets 1 / SixRealms 2；首次全量回归时它因此失败，属预期的有意更新），删除 0；变异验证 19 组（去掉 / 改错 policy、interval 改变、policy 与 confirm_delay 并用、新增直接点击、Pets 未投喂分支误触发 / 重复导航、
  refresh 忽略 False 返回值 / 动画超时改变 / 次数判断改变、岛屿消失后改选 / 选择规则改变、Navigator 预算被改）全部被抓，源码逐字节还原。全量 1948 → **1980/1980 OK**。
- **登记册**：`dev_tools/click_callsite_register.py` 新增 `C1_MIGRATED`（逐点：文件 / 函数 / 目标 / policy，对不上源码直接抛错）与 basis=`c0` / reason=`C1`；这 4 处 NEEDS_C → ALREADY_L2；policy 点位 32 → 36；
  NEEDS_C 24 → 20；basis human 179 / c0 4 / rule 909；登记册新增 §2.4 区分 1092 / 179 / 24 / 4 四个口径。
- **仍待办（未在 C1-A1；当时评估为可继续迁，用户随后决定暂缓，最终状态见 §4.88）**：MIGRATE 候选 Duel 两处练习入口、SixRealms 四处商店调用；NEEDS_C GeneralInvite `check_then_accept` ×5、GeneralBattle 准备页弹窗 ×2（等真机）；C0 建议的 KEEP_* 7 处
  暂在登记册里仍按原分类。**Level C 待验**：reaction 区间仍是 PROVISIONAL；Dokan 6 秒预算够不够、Pets / SixRealms 的 reaction 手感需真机看，未启动 MuMu / 游戏 / OCR。

### 4.88 L2 C0 分类与文档收口（当前 L2 状态快照）

2026-09-21。**只改文档与登记册元数据，不改任何生产业务行为、不调整 reaction 区间**。未 commit / push。用户已明确决定：Duel、SixRealms 剩余商店事务、GeneralInvite 接受邀请、GeneralBattle 准备弹窗
**全部暂缓，不继续开发**。**当前没有获批的 L2 功能开发任务**；接手的 AI 不得自动继续迁移，也不得把「可以开发」当成「必须开发」。

- **L2 已完成什么**：L1 Stage 1～3B（生产单击 / 长按执行入口统一 + 全局静态守卫）；L2 公共 Reaction Policy / fresh screenshot / 二次确认；FIRE 独立反应机制（任务配置 `fire_reaction`）；GeneralBattle 独立结算 FSM；
  C0 全仓剩余 24 点专项复核；C1-A1 四处实际迁移（§4.87）。**不是「全部 L2 点位已迁移」**——见下方分类。
- **C0 24 点的最终状态**（逐点在 `docs/L2_CALLSITE_REGISTER.md` §2.4 与 `docs/L2_INTERACTION_POLICY_MAP.md` §4；技术分类 `decision` 与开发排期 `dev_status` 是两个维度，不能相加）：

  | 状态 | 数量 | 点位 | decision | dev_status |
  | --- | ---: | --- | --- | --- |
  | 已完成迁移（C1-A1） | 4 | Dokan `priority_enter_dokan` NORMAL / Pets `_feed` NAVIGATION / SixRealms `refresh_store` CONFIRM / `choose_and_enter_island` NORMAL | ALREADY_L2 | COMPLETED |
  | C0 建议 MIGRATE、用户暂缓 | 6 | Duel `enter_practice_ban_mode` ×2；SixRealms 商店 `_summon_store` ×2 / `_use_breath` / `_confirm_store_entry` | DEFERRED（原建议保存在 C0 表） | DEFERRED |
  | 保持即时（已有结论，非积压） | 3 | DemonRetreat `run`（失败恢复）/ Quiz `_deal_quiz`（倒计时敏感）/ SixRealms `open_shop`（超时恢复） | KEEP_IMMEDIATE | NOT_APPLICABLE |
  | 保持专用时序（已有 timing owner） | 4 | Buy `buy_more` ×2（连续加量节奏，两次间 0.5s 保留）/ `switch_moon_sea_shikigami`（Navigator hook）/ `_mark_peacock_boss`（首领标记事务，0.3s settle 保留） | KEEP_SPECIAL | NOT_APPLICABLE |
  | 技术上需 Level C 依据、用户暂缓 | 7 | GeneralInvite `check_then_accept` ×5（共享接受邀请事务，逐按钮加 reaction 会重复等待；队长秒开有时效风险；接受循环缺墙钟上限）；GeneralBattle `_handle_prepare` ×2（准备页 FSM，受倒计时影响，不能套普通 CONFIRM） | NEEDS_C（沿用 L2-2 人工审计来源） | DEFERRED |

- **登记册统计（互斥、可加总，1092 = 7 + 37 + 630 + 232 + 7 + 6 + 35 + 138）**：MIGRATE 7（L2-2 已迁）/ ALREADY_L2 37 / KEEP_IMMEDIATE 630 / KEEP_SPECIAL 232 / NEEDS_C 7 / DEFERRED 6 / PRIMITIVE 35 / EXCLUDED 138；
  显式 policy 点位 36；basis：human 179 / c0 17 / rule 896。**`c0_reviewed`（24）是另一个维度，不与 basis 相加**——GeneralInvite / GeneralBattle 的 7 点决定来源仍是 L2-2 人工审计（human），
  所以 c0 basis = 4 + 6 + 3 + 4 = 17。四个口径务必区分：全仓 1092 点 / 最初人工审计 179 点 / C0 复核 24 点 / C1-A1 实施 4 点。
- **generator**：`dev_tools/click_callsite_register.py` 新增 `C0_TRIAGE`（其余 20 点的逐点归档：文件 / 函数 / 目标 / 第几次出现 / decision / dev_status / C0 建议 / 说明）、`decision=DEFERRED`、
  reason `C0K` / `C0S` / `C0D`、每点位 `dev_status` / `c0_reviewed` / `c0_advice` 元数据与登记册 §2.4 的 24 点表；对不上源码、归档点位已带 reaction、NEEDS_C 归档没指向 L2-2 的 NEEDS_C 点位都直接抛错。
- **测试**：新增 `tests/test_l2_c0_registry.py` 16 项（24 点逐项独立对账、暂缓点位仍是立即点击、统计口径与 basis 对账、生成结果可重复且与 Markdown 逐字一致、L2-2 历史审计不被改写、
  归档漂移 / 暂缓点位偷偷加 policy / NEEDS_C 指错点位会失败）；修改既有测试 2 个的钉住值（`test_l1_l2_integration.py` 的 NEEDS_C 按模块钉住改为 GeneralInvite 5 / GeneralBattle 2；
  `test_l2_stage_c1_a1.py` 的「已完成」以 reason=C1 判定），删除 0，无放宽。全量 1980 → **1996/1996 OK**。
- **仍未完成 / 待验**：L1 / L2 真机（Level C）验收未做，reaction 区间仍是 PROVISIONAL，Dokan 6 秒预算够不够、各 policy 手感需真机；Swipe / Drag 是另外的开发方向；ROI 质量审计、BehaviorTrace 元数据等见 ROADMAP。
  **DEFERRED 是用户排期，不是技术完成，也不是永久禁止**：日后若用户重新启动，须重新按 C0 建议与真机依据评估（GeneralInvite 应先设计事务级 reaction 与有界状态确认）。

### 4.89 ActivityShikigami 活动入口导航停滞：定位与最小修复（`find_activity_entry` 回退加固）

2026-09-22。真机事故追加发现 + 最小修复，**只改 `tasks/ActivityShikigami/page.py`**，未碰 GeneralBattle / Settlement V3 / Micro-Burst / FIRE / L1 空间模型 / L2 Reaction 区间 / Navigator 全局状态机 / RightActivity 资产。未 commit / push。

**背景**：§4.62 落地的新入口 `goto_activity_entry`（`page_main → page_act` 边动作，优先当期图标 `I_MAIN_GOTO_ACT_2`、旧图标 `I_MAIN_GOTO_ACT` 回退）落地后从未有过 Level C 记录（§4.62 原文写的是「Level C 待验」，此后全仓再无补充验证记录）。真机 2026-09-22 15:46 日志显示：`goto_activity_entry` 在 6 秒 `action_timer` 窗口内两个入口图标全程零点击 → 落入 `page_act.on_enter_failure` 的旧回退 `find_activity_entry`（庭院右侧栏目切换）→ 5 次 `AS_TOGGLE_BUTTON`（即 `RightActivityAssets.I_TOGGLE_BUTTON`，`roi_front≈(1206,540)`）点击后，进程再无任何日志输出，直至约 35 分钟后被外部重启（`log/2026-09-22_oas1.txt` 出现完整的 `Log cleanup finished / Start scheduler loop` 重启横幅，中间无一行日志，非优雅超时退出）。

- **已确认（有直接日志时间线证据）**：这次是「入口点击失败」（识别不到目标、从未点击），不是「点了但页面没变化」——`_execute_transition` 的失败分支在 6 秒 action_timer 到期时直接触发，从未先跑 `_wait_for_destination`。`find_activity_entry` 的旧回退随后确实在跑（5 次点击节奏与其 `_settle_activity_auxiliary`(1.0s)+点击+`sleep(0.5)` 的预期耗时吻合），随后停滞。
- **已确认（排除一类猜测）**：`screenshot_method=nemu_ipc`（oas1 实际配置）的截图调用链本身已有独立的 `asyncio.wait_for(timeout=0.15)` + `@retry`（`module/device/method/nemu_ipc.py`）与耗尽后 `raise RequestHumanTakeover` 的既有机制，会产生日志；`module/image/rpc.py` 的 `ImageClient` 也有 `zerorpc.Client(timeout=10)`。这两层如果是卡点，理应在数秒到数十秒内产生 warning/critical 日志，而事故期间**完全没有**——所以"设备截图 IO 硬阻塞"不是最可能的解释，但受限于只读审查，**没有进一步确认真正卡在哪一次调用**，仍是证据缺口。
- **未确认（明确标记，不假装已定位）**：真正阻塞发生在哪一行、这次两个入口图标为什么本帧都没被识别到（本期活动图标皮肤/位置变化？庭院右侧栏目当时停在别的活动列？截图时机与页面动画没对齐？）——均需真机连线诊断，本轮不猜测。
- **最小修复**（`tasks/ActivityShikigami/page.py`，只加固旧回退 `find_activity_entry` 与 `goto_activity_entry` 的诊断，业务判定顺序/图标优先级/`InteractionPolicy.NAVIGATION` 一律不动）：
  1. **点击后新帧复用**：`find_activity_entry` 每轮循环只截一次真正需要的新图——点击栏目切换按钮后立即取一次新帧，这张帧既确认这次点击是否已经带出活动入口（命中则立即返回，不必等下一轮），也直接充当下一轮循环顶部的判断画面，不再对同一状态重复截图。`_settle_activity_auxiliary`（点击前重新确认按钮仍在）语义不变。
  2. **双重独立上限**：保留原有次数上限 `ACTIVITY_COLUMN_SWITCH_MAX_TRIES=8`，新增并列的墙钟上限 `ACTIVITY_ENTRY_FALLBACK_TIMEOUT=20`（秒），任一先到都走同一条「未找到→`GamePageUnknownError`」退出路径，不吞异常、不伪造成功。**能力边界必须记住**：这个 `Timer` 只在循环重新拿到控制权、跑到循环顶部判断语句时才会被检查；如果某一次 `screenshot()`/`appear()` 本身在更底层同步阻塞、迟迟不返回，这个 Timer 不会被执行到，也无法中断那一次调用——它只保证「正常往返于循环体」的耗时有界，**不能替代设备层自身的超时**（这正是本次 35 分钟停滞更可能发生的地方，且不在本轮修复范围内）。
  3. **最小诊断日志（中文）**：`goto_activity_entry` 在两个入口图标都未命中时记一行 info；`find_activity_entry` 记录「进入回退」「第 N 次切换栏目」「切换后是否立即找到」「墙钟超时」「循环次数耗尽」；不新增覆盖异常的 try/except，`screenshot()`/`appear()` 抛出的异常原样向上传播。`goto_activity_entry`「初次识别成功但二次确认失败」这一状态无法从现有 `appear_then_click` 返回值单独区分，明确标记为**未确认**，不强行拆分 `appear_then_click` 本体。
- **测试**：`tests/test_activity_shikigami_climb.py` 新增 `FindActivityEntryFallbackDriverTest`（8 项，真实驱动而非只读源码字符串）：切换后立即找到入口且截图次数符合预期（3 次）、入口始终不出现按次数上限抛出、toggle 全程不可见同样有界、墙钟先于次数上限触发、截图异常原样传播不被吞掉、点击前二次确认失败不误判成功、无额外重复截图、点击仍经 `appear_then_click`（不引入裸 `device.click`）。**发现并修复了测试假体自身的一个帧序索引 off-by-one**（`screenshot()` 语义应为「调用后才前进到下一帧」，不是「调用时已经代表下一帧」）与 `_FakeTimer.budget` 跨测试类共享状态未还原导致 `SettlementDrainTest` 被污染的问题，两处均已修正且不影响生产代码。
- **登记册**：本轮改动影响了 `find_activity_entry` 函数体里出现的辅助调用集合（新增 `Timer`），`docs/L2_CALLSITE_REGISTER.md` 已重新生成（`total=1092` 不变，`l1_pipeline_sites=45` 不变，只有该函数的登记行辅助字段从 `sleep` 变为 `Timer,sleep`）。
- **验收**：`compileall -q tasks tests` OK；`unittest tests.test_activity_shikigami_climb` 71/71 OK；全量 `unittest discover -s tests` **1996 → 2004（+8），0 失败 0 错误 0 跳过**；静态点击守卫 `check_repo().ok = True`（未新增裸点击）；`git diff --check` 干净。
- **仍未完成 / Level C 待验**：本次真机停滞的具体阻塞调用点仍未定位（只做到排除设备截图层大概率不是主因），需要用户连线设备实测复现并观察是否停在 `find_activity_entry` 内部某次调用；墙钟超时值 `20s` 是工程经验值，未经真机标定；`goto_activity_entry`「初次识别 vs 二次确认」区分能力缺口仍待评估是否值得改造 `appear_then_click` 本体（本轮不做）。
- **文档核对说明**：上一轮《ActivityShikigami 活动入口导航问题审查报告》结尾声称已更新本文件、`ROADMAP.md`、`DEVELOP_LOG.md`，但本轮核实**这三份文档当时实际并未写入任何相关内容**（`git status` 计数不变只是因为这些文件本就在 98 项 WIP 之内，不代表内容确实被追加）——本节 §4.89 与下方 `ROADMAP.md`/`DEVELOP_LOG.md` 的更新是本轮才真正落地的记录。

### 4.90 ActivityShikigami 战后结算兜底乱点：`page_climb_pass` 误判为弹窗的最小修复

2026-09-22。真机事故追加发现 + 最小修复，**只改 `tasks/ActivityShikigami/activities/normal.py`**，未碰 GeneralBattle / Settlement V3 / Micro-Burst / L1 / L2 / Navigator。未 commit / push。

**背景**：真机日志（`log/2026-09-22_oas1.txt` 16:38:06～16:38:15）显示：`GeneralBattle` Settlement 正常完成两次 `random_save_right` 点击、`Exit matcher hit`、`Battle result: Win`，随后 `_drain_activity_settlement('pass', page_climb_pass)` 连续 6 帧都把当前页识别为 `[UI] page_climb_pass`，却依然连点 6 次 `random_default`，直到点击预算耗尽产生 `Activity settlement drain bounded out` 警告。**追加发现（比用户给出的日志窗口更靠后）**：这条警告之后，`log/2026-09-22_oas1.txt` 与 `log/behavior/oas1_2026-09-22.jsonl` 再无任何输出，直至约 **66 分钟**后被外部重启（完整 `Log cleanup finished / Start scheduler loop` 横幅，`DETECT DEVICE` 全套重连）——与上一轮 §4.89 记录的「静默停滞直至外部重启」是同一症状，但这次的触发点在 `_drain_activity_settlement` 之后，而不是 `find_activity_entry`。

- **`page_climb_pass` 的真实语义（已用源码 + 日志证据确认，不是猜测）**：这就是 [page.py:193-209](tasks/ActivityShikigami/page.py#L193-L209) 定义的**真实普通爬塔·门票模式挑战页**（`all_of(any_of(I_CHECK_BATTLE_PASS_2, I_CHECK_BATTLE_PASS), I_CLIMB_MODE_PASS)`），**不是**通用 Result/Reward 弹窗，也不是 `_drain_activity_settlement` 文档注释里说的「活动专用结算弹窗」。它正是 `_run_climb_type` 里 `destination = getattr(pages, f'page_climb_{action_type}')` 的那个 `destination` 本身。
- **根因**：`_drain_activity_settlement` 原代码把 `get_current_page() == destination and appear(fire_rule)` 当成唯一的「成功」条件，任何其它状态（包括「已经结构性落在 `destination` 页、只是挑战键 `I_ACT_FIRE` 还没渲染完成」）都无差别地当成「还有残留弹窗」去点 `C_RANDOM_DEFAULT`。日志里连续 6 帧都识别到 `page_climb_pass` 恰恰证明我们**已经在正确的挑战页上**，缺的只是挑战键的进场动画还没走完——这不是弹窗，点了没有意义（且可能干扰挑战键渲染）。
- **最小修复**：把「`current_page == destination`」与「`appear(fire_rule)`」拆成两层判断——命中 `destination` 但挑战键未就绪时，复用 FIRE 契约已有的 `_wait_climb_fire_state`（`_enter_climb_battle` 同款三态有界轮询）**等待**而不是盲点；只有 `current_page != destination`（真正的其它页面 / 未知帧）才继续走原有的盲点兜底，行为完全不变。不新增点击路径、不新增裸 `device.click`、不改既有的 `ACTIVITY_SETTLEMENT_MAX_CLICKS=6` / `ACTIVITY_SETTLEMENT_TIMEOUT=15` 上限语义。
- **追加发现的第二个缺口（同一文件、`_run_climb_type` 主循环）**：`_drain_activity_settlement` 返回值被调用方忽略，回到 `_run_climb_type` 的 `while True` 循环顶部重新截图判页；若此后 `get_current_page()` 持续返回 `None`（例如前述的连续盲点干扰了页面状态），原代码该分支只有 `time.sleep(0.5); continue`，**没有任何上限**——这正是 66 分钟零日志静默停滞的直接代码原因（该分支没有一行日志，`screenshot()`/`sleep()` 本身也不产生日志）。已加固：新增 `ACTIVITY_CLIMB_UNKNOWN_PAGE_TIMEOUT=20`（秒）墙钟，只在**连续**识别不到已知页面时计时（识别到任意已知页面立即清空，不惩罚偶发过渡帧），超时后 `raise GamePageUnknownError`（复用既有异常类型，不新发明契约），交给外层既有的异常处理，不在本层猜测恢复动作。
- **能力边界（与 §4.89 相同性质，必须同样写清楚）**：这个墙钟同样只能约束「代码正常执行到判断语句」的耗时，不能中断某一次尚未返回的同步 `screenshot()`/`get_current_page()` 调用。本轮无法确认这次 66 分钟停滞是「持续 None 但每次都正常返回、只是一直没能等到已知页面」（这种情况新墙钟能生效拦住）还是「某一次调用本身同步卡死不返回」（这种情况新墙钟同样无能为力）——**证据缺口**，需要用户真机复现观察加固后是否还会静默挂起。
- **测试**：`tests/test_activity_shikigami_climb.py` 新增 11 项真实驱动测试（`SettlementDrainTest` +6、新增 `ClimbTypeUnknownPageTest` 5 项）。核心事故复现用例 `test_incident_destination_recognized_but_fire_never_ready_zero_blind_clicks`：`page_climb_pass` 连续命中、`I_ACT_FIRE` 全程不可见，断言 `random_default` 点击次数为 **0**（修复前会产生 6 次）；`test_persistent_unknown_page_raises_after_bounded_wait` 验证 `_run_climb_type` 对持续未知页面有界抛出；`test_recovery_resets_the_unknown_page_budget` 验证未知页计时在恢复后正确清零、不跨间断累加；`test_screenshot_exception_*` 两处均验证截图异常原样传播不被吞掉；既有 71 项测试全部不改断言、全部保持通过。
- **登记册**：本轮新增 `Timer` / `GamePageUnknownError` 调用改变了 `_run_climb_type` 登记行的辅助字段，`docs/L2_CALLSITE_REGISTER.md` 已重新生成（`total=1092` 不变）。
- **验收**：`compileall -q tasks tests` OK；`unittest tests.test_activity_shikigami_climb` 82/82 OK；`unittest tests.test_general_battle_settlement tests.test_general_battle_timing tests.test_settlement_trace_check` 117/117 OK（确认 GeneralBattle Settlement V3 未受影响）；全量 `unittest discover -s tests` **2004 → 2015（+11），0 失败 0 错误 0 跳过**；静态点击守卫 `check_repo().ok = True`；`git diff --check` 干净。
- **仍未完成 / Level C 待验**：这次 66 分钟停滞的具体阻塞调用点仍未定位（只确认了代码逻辑上此前没有任何上限，加固后是否真的能生效拦住需要真机验证）；`_drain_activity_settlement` 的 `_wait_climb_fire_state` 等待分支在真机上等待时长是否合适（PROVISIONAL，沿用既有 `ACTIVITY_FIRE_POST_CLICK_TIMEOUT=4s`，未单独标定）；`ACTIVITY_CLIMB_UNKNOWN_PAGE_TIMEOUT=20s` 未经真机标定；`fake_god.py`/`normal.py` 里与 §4.89 提到的 `page_reward` 外层分支同款的其它潜在无界循环未逐一排查（本轮只加固了本次事故实际触发的两处）。

### 4.91 ActivityShikigami 普通爬塔专用结算单击：取消 Micro-Burst 连击，70/30 activity region

2026-09-23。用户主动发起的架构改造（非真机事故追加发现），**只改 `tasks/ActivityShikigami/` 内 4 个文件**（`activities/normal.py` 主体 + `base_act.py`/`activities/rich_man.py`/`activities/fake_god.py` 的 ownership 声明），未碰 `tasks/Component/GeneralBattle/general_battle.py`、L1、L2 通用层、Navigator、Swipe/Drag、结界蹭卡。未 commit / push。详见 `docs/DECISIONS.md` D025 补记（2026-09-23）。

- **背景**：§4.89 / §4.90 两次真机事故都指向同一类风险——Settlement Micro-Burst 的 anchor 跨调用复用模型，在「弹窗刚消失、真实挑战页正好出现」这个窗口期容易打出多余的第二击。用户据此要求 ActivityShikigami 普通爬塔线（仅 `NormalClimbAct`）彻底退出 Micro-Burst，换成每次只点一次、每次都重新走完整确认流程的专属机制。
- **资产**：`C_RANDOM_ACTIVITY_1`（roi_front `937,431,296,248`）/ `C_RANDOM_ACTIVITY_2`（roi_front `659,522,406,171`），用户已放入 `GeneralBattleAssets` + `gb/click.json`（本轮开始前已存在，AI 未生成，本轮予以确认）。
- **机制**（`NormalClimbAct` 新增方法）：
  - `_climb_owns_settlement_single_click`：新的 ownership flag，与 `_fatigue_owns_macro_idle` 同款契约——`run_climb()` 声明 True，`run_rich_man()` / `run_fakegod()` 声明 False，防止跨玩法线残留（声明位置在 `base_act.__init__` 默认 False + 三条 `run_*` 各自显式覆盖）。
  - `_handle_result` / `_handle_reward`：MRO 上排在 `RichManAct` 之后、`FakeGodAct`/`BaseAct` 之前（`class ScriptTask(RichManAct, NormalClimbAct, FakeGodAct, BaseAct)`），flag 为假时 `return super()._handle_result/_handle_reward(...)` 原样回落到 `BaseAct`/`GeneralBattle` 的既有实现（大富翁/伪神降临零影响，已用真实 MRO 驱动测试验证）；flag 为真时接管——逐字保留 `GeneralBattle._handle_result`/`_handle_reward` 的周边逻辑（`is_win` 判定、`click_record_clear`、`I_OVER_GHOST`/`I_GB_SKIN_CONFIRM` 特殊弹窗短路、boss 专属 `I_UI_BACK_RED` 点击），只把 `_settlement_burst_step(...)` 换成 `_activity_settlement_single_click(...)`。
  - `_activity_settlement_single_click(context, current_page)`：reaction（`random_delay(*ACTIVITY_SETTLEMENT_REACTION)` = **本线自己持有的 `(0.45, 0.85)`**，`InteractionPolicy.SPECIAL` 语义，不经过 `appear_then_click(policy=)` / `confirm_delay`，整条链路只有这一层 reaction）→ `sleep` → `self.screenshot()` → `_climb_settlement_should_stop()`（命中 `page_climb_<type>` 或挑战键即放弃）→ `_classify_general_battle_page() != current_page` 即放弃（结算状态已变化）→ `_select_activity_settlement_region()`（70/30）→ `_sample_settlement_point(region)`（复用 GeneralBattle 现有 region 采样）→ `execute_single_click(FinalPoint(...))`。**全程至多 1 次点击，不预授权第二击，不跨调用保留 anchor**——下一次仍需处理结算由外层 `run_general_battle` 主循环下一帧重新调用本方法，形成全新一轮事务。
  - `_climb_settlement_should_stop()`：复用已有的 `page_climb_<type>`（`get_current_page() == destination`）与 `_climb_fire_rule(action_type)`（`appear(fire_rule)`），不新造判据——直接吸收 §4.90 的教训（`page_climb_pass` 是真实挑战页，不是弹窗）。
  - `_select_activity_settlement_region()`：`random_int(1, 100) <= 70` 选 `C_RANDOM_ACTIVITY_1`，否则 `C_RANDOM_ACTIVITY_2`；`random_int` 来自 `module.base.utils.random`（模块级 `SystemRandom`，与 `GeneralBattle._select_reward_region` 同一随机源），未新建 `random.Random`。
- **登记册**：新增 1 处 `execute_single_click`（`KEEP_IMMEDIATE`/R10）+ 3 处 `appear_then_click`（`normal.py` 里对 `base_act.py`/`general_battle.py` 既有登记点位的逐字复制：`I_UI_BACK_RED`/`I_OVER_GHOST`/`I_GB_SKIN_CONFIRM`，均沿用原分类 `KEEP_SPECIAL`）。`total` 1092 → **1096**；`human` 179 → **182**（`tests/test_l2_policy_migration.py` 的 `INVENTORY` 按真实源码顺序插入 3 行，位置在 `_run_climb_type` 与 `_sync_climb_penta_pass` 之间，与文件里 `_handle_result`/`_handle_reward` 的真实物理位置一致）；`l1_pipeline_sites` 45 → **46**。`docs/L2_CALLSITE_REGISTER.md` 已重新生成。
- **测试**：`tests/test_activity_shikigami_climb.py` 新增 `ActivitySettlementSingleClickTest`（17 项，真实驱动）：70/30 分支分别选中对应区域、且从不落回 `random_default`/`random_save_right`/`random_save_bottom`；单次事务至多 1 次 `execute_single_click`；两次独立调用各自重新 70/30 选择 + 重新采样（不复用 anchor）；`page_climb_pass` 出现 / 挑战键出现均零点击；结算状态不明确（分类已变化）不点击；`owns=False` 时真实走到 `GeneralBattle._handle_result`（用 `patch.object(GeneralBattle, '_handle_result')` 验证确实调用到父类，不是伪装）；`owns=True` 时 boss 专属弹窗点击与 `I_OVER_GHOST` 短路分支均未丢失（回归防护）；复现用户描述的「Reward → 点击 → 弹窗消失 → 第二击穿透」场景，验证第二次独立调用发现真实挑战页已出现后放弃、不产生第二次点击；源码级护栏确认三处新方法都不含裸 `device.click`、不调用 `_settlement_burst_step`/`_fire_settlement_burst`。既有 82 项测试断言零改动、全部保持通过。
- **验收**：`compileall -q tasks tests` OK；`unittest tests.test_activity_shikigami_climb` **99/99** OK；`unittest tests.test_general_battle_settlement` **83/83** OK（GeneralBattle Settlement V3 未受影响）；全量 `unittest discover -s tests` **2015 → 2032（+17），0 失败 0 错误 0 跳过**；静态点击守卫 `check_repo().ok = True`；`git diff --check` 对本轮实际改动的文件干净（`tasks/Component/GeneralBattle/assets.py`/`gb/click.json`/`tasks/ActivityShikigami/assets.py` 等用户自己此前用资产工具生成的文件存在预先就有的行尾空格，与本轮改动无关，本轮未触碰这些文件）。
- **reaction owner 收口（同日补完，2026-09-23）**：首版实现借用了 `GeneralBattle.SETTLEMENT_BURST_CLICK_INTERVAL_RANGE`（0.10~0.30s）当 reaction，但那个常量的语义是「Micro-Burst 同一 burst 内两击之间的观察间隔」，既不是「点击前反应」、又属于通用 Settlement V3 的 timing——本线已经退出 Micro-Burst，继续借用会把两种语义混在一起，且任何一方调参都会误伤另一方。已改为本线自己持有的 **`ACTIVITY_SETTLEMENT_REACTION = (0.45, 0.85)`**（`normal.py` 常量区，PROVISIONAL，量级对齐 `REACTION_NORMAL` 但不走 `InteractionPolicy`）。`GeneralBattle.SETTLEMENT_BURST_CLICK_INTERVAL_RANGE` 数值与用途在**本条改动里**一字未改，其它任务的 Micro-Burst 不受影响（该常量已在同日后续一轮单独调整为 `(0.30, 0.60)`，见 §4.92——那是独立的通用层调参，本线 `(0.45, 0.85)` 不受牵连）。新增 6 项测试锁定：区间精确为 `(0.45, 0.85)`、函数体不再引用 burst 常量、运行期确实按本线常量采样、调用顺序严格是 `random_delay → sleep → screenshot → 确认 → 选区采样 → 单击`（证明坐标一定在等待之后才采、不跨等待复用）、单次事务只有一层 reaction（`random_delay` / `sleep` 各一次，无 `policy=` / `confirm_delay` / `appear_then_click`）、GeneralBattle 的 burst 间隔当时仍是 `(0.10, 0.30)` 且仍被 `_fire_settlement_burst` 使用（该断言已随 §4.92 的调参同步更新为 `(0.30, 0.60)`）。
- **仍未完成 / Level C 待验**：70/30 权重与新的 reaction 区间 `(0.45, 0.85)` 均未经真机标定；两处新区域 `C_RANDOM_ACTIVITY_1`/`C_RANDOM_ACTIVITY_2` 的真机点击安全性（是否会误触活动结算页上的其它控件）需要用户自行确认；改造只覆盖普通爬塔（4 种 `action_type`），未评估是否需要扩展到大富翁/伪神降临（用户本轮未要求）。

### 4.92 GeneralBattle Micro-Burst observe 间隔：`(0.10, 0.30)` → `(0.30, 0.60)`

2026-09-23。用户按真机体感提出的通用层调参，**只改一个常量值**，未重新设计 Settlement 状态机。详见 `docs/DECISIONS.md` D025 末尾补记（2026-09-23）。

- **改了什么**：`tasks/Component/GeneralBattle/general_battle.py` 的 `SETTLEMENT_BURST_CLICK_INTERVAL_RANGE` 由 `(0.10, 0.30)` 改为 **`(0.30, 0.60)`**（含模块头注释与常量注释同步）。动机：原 0.10~0.30s 在页面响应稍慢时，fresh 观察容易落在页面尚未更新的旧帧上，从而把「其实已经推进」误判成「还是同一 state」而补了第二下。
- **没改什么**：`_fire_settlement_burst` 的判定逻辑一行未动——仍是 `time.sleep(self._sample_interval(SETTLEMENT_BURST_CLICK_INTERVAL_RANGE))` 之后 fresh screenshot + 同一 classifier 重新分类，**第二下仍必须由观察结果重新授权**（same state 才补；state advance / Unknown / known non-settlement 分别取消第二下 / 交回 recovery / 立即 teardown）。segment 2~4 预算、`SETTLEMENT_MAX_TOTAL_CLICKS=9`、anchor 复用与安全区域交集、Result / Reward region 策略、L1 `execute_single_click` 链路全部原样；FIRE、L2 policy、Minitouch dwell、ClickSampler、Swipe / Drag 未动。
- **两套 timing 各自独立（本轮的直接验证）**：ActivityShikigami 普通爬塔专用结算的 `ACTIVITY_SETTLEMENT_REACTION = (0.45, 0.85)`（§4.91）**完全不受影响**——这正是把两个常量拆开的价值：通用层调参不再牵连 task-local 事务。已有测试显式钉住两者不相等。
- **测试**：`tests/test_general_battle_settlement.py` 新增 `SettlementBurstIntervalValueTest`（6 项，用真实 `_sample_interval`、只 patch `random_delay` / `time.sleep`）：常量精确为 `(0.30, 0.60)`；`_fire_settlement_burst` 确实读这个常量；运行期 `random_delay` 以该区间被调用且 `sleep` 睡的就是采样值；两次 burst **各自独立采样一次**（不是开局抽一次后固定复用）；**放宽间隔后第二下仍需重新授权**（观察到推进 → 只点 1 次；观察仍同页 → 才点第 2 次，且第二下之前确实重新截图 + 重新分类）；ActivityShikigami 的 `(0.45, 0.85)` 仍是独立常量。同步更新 2 处原本钉住旧值的断言（`test_l2_interaction_reaction.py` / `test_activity_shikigami_climb.py`），**只改数值，未放宽任何状态机断言**。
- **验收**：`compileall -q tasks tests dev_tools` OK；`tests.test_general_battle_settlement` **89/89** OK；`tests.test_activity_shikigami_climb` **105/105** OK；全量 `unittest discover -s tests` **2038 → 2044（+6）**，0 失败 0 错误 0 跳过；L1 静态点击守卫 `ok=True`；L2 登记册与上一轮完全一致（total 1096 / human 182 / l1_pipeline 46 / policy 36——本轮没有增删任何点击调用点，无需重新生成）；`git diff --check` 对本轮改动的 4 个文件干净。
- **Level C 待验**：`0.30~0.60s` 是否足够覆盖真机页面更新（是否还会出现「在旧帧上判定 same state 而补第二下」）；放慢之后连点观感是否仍自然、整体结算耗时是否可接受。**本轮只做离线验证，未做任何真机验证。**

## 5. 已确认保留的 upstream 修改

### 5.1 NemuIPC 与 scrcpy

`module/device/method/nemu_ipc.py` 和 `module/device/method/scrcpy/scrcpy.py` 保持 `upstream/self` 原版本，暂不人工融合。当前主要使用 `minitouch`，不要因为看到普通随机实现就擅自重构这两个后端。

### 5.2 Image 与 OCR

以下 upstream 修改已经审查并保留：

- `module/image/rpc.py`
- `module/image/runtime.py`
- `module/ocr/ppocr.py`
- `module/ocr/rpc.py`

默认 `low_spec_mode=false`，此时图像阈值偏移为 0，OCR 使用 medium 模型。

低配模式启用后：

- Image threshold 减少 0.1。
- OCR 使用 small 模型。
- frame TTL override 为 10 秒。

Easy Install 当前主要预置 medium OCR 模型；small 模型可能首次自动下载，离线环境可能失败，且当前没有自动回退到 medium。这是非阻断事项。

### 5.3 AntiBan 作息逻辑

当前 upstream 版本已确认保留：

- 默认 `enable=False`。
- 旧配置缺少字段时自动使用默认值。
- 支持同日窗口和跨午夜窗口。
- `start == end` 表示关闭睡眠时间窗。
- 活跃累计只计算任务执行的 wall-clock 时间。
- 触发长休息后清零累计值，并通过 `rest_until` 闭环。
- 多实例使用各自独立的 `Script` 状态。

已知非阻断事项：任务跨 00:00 时可能把整个任务耗时计入新一天；脚本进程重启后活跃累计会清零。不要因此擅自新增持久化系统。

### 5.4 业务模块

以下 upstream 版本已经审查并直接保留：

- Chess
- KekkaiUtilize
- Costume
- CostumeShikigami
- BondlingFairyland
- Sougenbi

不要因为后续看到代码变化就重新回退。`KekkaiUtilize.min_run_interval` 默认值为 0，保持旧行为。

## 6. 已知设计决策

- 点击坐标和点击时序分层处理，不在 `Control.click()` 全局叠加随机等待。
- 二次确认必须在等待后重新截图、重新识别，并重新生成最新坐标，避免点击旧坐标。
- `RyouToppa` 的 FIRE 局部状态机不应被简单替换为公共 `confirm_delay`。
- 协议等待、后端缓冲、截图 interval、RPC 轮询、重试退避和 FSM 超时属于可靠性时序，不应随意随机化。
- 任务级休息与输入协议时序不是同一种等待，不要混为一谈。
- 已确认保留的 upstream 业务模块不因整合完成后再次看到差异而随意回退。
- 源码和最新 Git 状态始终高于本文档；确认事实变化后同步更新状态快照。

## 7. 测试与验证状态

**当前基线（2026-09-21，§4.88 L2 C0 分类与文档收口）**：
`toolkit/python.exe -m compileall module tasks tests dev_tools` 通过；
`toolkit/python.exe -m unittest discover -s tests` = **1996/1996 OK**（`1980 → 1996` = §4.88 新增
`tests/test_l2_c0_registry.py` 16 项，改 2 个既有测试的钉住值，删除 0；`1948 → 1980` = §4.87 新增
`tests/test_l2_stage_c1_a1.py` 32 项，改 2 个既有测试文件（登记册锁 / policy consumer 钉住），删除 0；`1894 → 1948` = §4.86 新增
`tests/test_l1_stage3b_global_guard.py` 54 项，改 2 个既有测试文件（白名单 / 登记册锁），删除 0；`1854 → 1894` = §4.85 新增
`tests/test_l1_stage3a_long_click.py` 40 项，改 1 个既有测试文件（stage1 静态断言），删除 0；`1836 → 1854` = §4.84 新增
`tests/test_l1_stage2_direct_clicks.py` 18 项，删除 0；`1809 → 1836` = §4.83 新增
`tests/test_l1_stage1_primitive_execution.py` 27 项，删除 0；`1668 → 1809` = §4.82：移植 L1 / L2 测试 + 新增
`tests/test_l1_l2_integration.py` 22 项，删除 0（Orochi 野队相关用例按项目决定不移植；`test_fire_reaction_task_config.py` 30 → 27 项：
4 个朴素 FIRE 循环用例改为驱动 Batch A 真实 owner）；`1645 → 1668` = §4.81 新增
`tests/test_shikigami_class_switch_bound.py` 23 项，删除 0；`1600 → 1645` = §4.80 新增
`tests/test_kekkai_utilize_success_jitter.py` 45 项，改 1 个既有测试文件的替身，删除 0；`1583 → 1600` = §4.79 新增
`tests/test_kekkai_utilize_convergence.py` 17 项，并把 `tests/test_kekkai_utilize_retry_scheduler.py` 的调度层驱动抽成可复用
`SchedulerHarness`，删除 0；`1560 → 1583` = §4.78 新增
`tests/test_kekkai_utilize_retry_scheduler.py` 23 项，改 1 个既有测试文件的替身，删除 0；`1530 → 1560` = §4.77 新增
`tests/test_fire_reaction_task_config.py` 30 项，改 7 个既有测试文件的 `REACTION_FIRE` 断言，删除 0，
此前 CASE10 的 1 个 skip 现真实命中，总数不变、skip 计数归零；`1521 → 1530` = §4.76 新增
`tests/test_global_game_fatigue_i18n.py` 9 项；`1505 → 1521` = §4.75 新增
`tests/test_config_model_script_task.py` 16 项，skip 1 = CASE 10 本基线无 FIRE 配置组，0 regression）。历史增量：
`1494 → 1505` = §4.70
新增 10 项指定 CASE + 1 项第二 Reward segment 端到端返回测试，0 regression；focused 结果见
§4.70）。历史增量：`1489 → 1494` = §4.69
2026-09-14 推送前审查发现并修复唯一 BLOCKER：`_fatigue_owns_macro_idle` 在同一个 `ScriptTask`
实例连跑多条活动线时不会恢复，导致「爬塔 → 伪神降临 / 大富翁」出现零 macro-idle owner；修法是
让每条玩法线在自己的 `run_*` 入口显式声明 owner；新增 `MacroIdleOwnershipLifecycleTest`（5，
全部走真实入口调用链、不手工写 flag，已验证在修复前会失败），并清理 2 个 dead import + 3 处
本轮新增 trailing whitespace，见 §4.69、0 regression）；`1479 → 1489` = §4.68
2026-09-14 修复 `check_utilize_add()` 导航到 `page_guild_realm_utilize` 失败后仍会继续执行
`run_utilize(...)` 的旧技债（根因：`goto_page()` 真实契约是「成功 True / 失败抛
`GamePageUnknownError`」，从不返回 `False`，旧 `if not goto_page(...)` 判断从未生效过）；本地
`try/except (GamePageUnknownError, GameStuckError)` 统一收敛失败信号，复用既有终态失败出口
（`_schedule_retry` + `utilize_terminal_failure=True` + `return False`），使 `run()` 自然跳过
全部下游业务；成功路径逐字未改，未碰 Navigator/`goto_page` 契约，不新增第二套重试机制；新增
`UtilizeNavigationFailureGuardTest`（10），见 §4.68、0 regression）；`1472 → 1479` = §4.67
2026-09-12 把 v1 的「blind micro-burst 硬上限 2 次」收紧为 Observed Micro-Burst：第二下点击
改为必须先经过 mid-burst fresh 语义观察（复用既有 `GameUi.detect_page_in`，新增私有转发
helper `_classify_general_battle_page()`）才允许执行；观察到已推进到另一个结算页 → 当前
burst 立即结束不换旧 state 补点；观察到已离开结算（Challenge/FIRE 相关页）→ 立即
`_teardown_settlement_session()`（与主循环级销毁复用同一 helper）；观察到 Unknown → 不补点
也不 teardown，交回既有 bounded recovery。budget/anchor persistence/Reward layout-aware/
主动换点上限/Loss 范围/Activity 独立 drain/FIRE 契约本身逐字未改；新增 7 例（CASE B/C/D/E/
G/H/I），见 §4.67 / `docs/DECISIONS.md` D025 v1.1 修订段落、0 regression）；`1461 → 1472` = §4.66
2026-09-12 GeneralBattle 结算点击升级为 Settlement Click Session：总预算 2~4（上限非必须点满）+
blind micro-burst 硬上限 2（同一 anchor）+ burst 后 fresh classify + 状态合法前向跳级 + anchor
persistence 服从安全区域交集（全 session 最多 1 次主动换点）+ 离开结算立即销毁 session（防止
点击穿透到 Challenge/FIRE 页面）；旧 `_advance_generic_result` 固定两次移除；`_select_reward_region`
layout-aware 策略 / RealmRaid FIRE 契约 / ActivityShikigami `_drain_activity_settlement` 均未改；
新增 `SettlementMicroBurstTest`（15）+ `SettlementSessionTeardownTest`（3），见 §4.66 /
`docs/DECISIONS.md` D025、0 regression）；`1453 → 1461` = §4.65 2026-09-11
新增 `UtilizeConfig.auto_replace_max_level: bool = False`（是否自动检查满级式神并替换，`run()` 唯一
调用点 `check_max_lv()` 套一层开关，方法本体全保留）；`utilize_harvest` 沿用既有字段不新增/不改
默认值；READ ONLY 确认 OASX 配置面板完全 schema-driven（`ArgumentView` 按 `model.type=='boolean'`
自动渲染 `Checkbox`），本轮 OASX **零修改**；新增 `tests/test_kekkai_utilize_state.py::
MaxLevelAndHarvestSwitchTest`（8），见 §4.65 / `docs/DECISIONS.md` D024、0 regression）；
`1418 → 1453` = §4.64 2026-09-11
KekkaiUtilize Scheduler v1：静默窗口（默认 00:00~07:00，`[start,end)`，跨午夜安全）+ 短期 retry
cooldown 随机化（5~30min，取代旧 5/10/20 分钟硬编码）；新增纯函数模块
`tasks/KekkaiUtilize/scheduling.py`（`is_in_quiet_window`/`next_quiet_window_end`/
`normalize_for_quiet_window`）+ `ScriptTask` 7 个 task-local helper（`_build_retry_target`/
`_normalize_quiet_target`/`_schedule_target`/`_schedule_retry`/`_guard_quiet_window` 等）；正常寄养
OCR 剩余时间调度逐字保留、只接入 quiet 归一化；`run()` 入口 `_guard_quiet_window` 静默窗口内立即重排
+ `TaskEnd`，不进任何页面/OCR/业务动作；新增配置 `UtilizeScheduler.quiet_*`/`cooldown_*`
（`field_validator` 校验，未用 `model_validator`——会撞 `ConfigBase.__init__` 异常恢复的
`IndexError`）；随机源统一 `module.base.utils.random.random_int`；新增
`tests/test_kekkai_utilize_scheduling.py`（16）+ `tests/test_kekkai_utilize_state.py` 5 个新测试类
（19），见 §4.64、0 regression）；`1415 → 1418` = §4.63 2026-09-11
真机确认：退四「再次挑战」最后一次 attempt reaction 后按钮消失分支裸 `continue`，缺一次有界
`_wait_again_entered_battle()` 确认，把已成功进入的 `page_battle_prepare` 误判成超时，任务异常遗留
在准备页；修：该分支先调 `_wait_again_entered_battle()`，`'battle'` 才判成功，否则才 `continue`，
复用既有 `RR_AGAIN_POST_CLICK_TIMEOUT`；未改 `_is_active_battle_entry()` / `fire()` / GeneralBattle /
`aborted` recovery；`tests/test_realm_raid_state.py` 新增 `FireAgainLastAttemptReactionGoneTest`（3），
见 §4.63、0 regression）；`1403 → 1415` = §4.62 2026-09-10
二层爬塔入口：`page_act --I_TO_BATTLE_MAIN--> page_climb_main --I_TO_BATTLE_MAIN_2--> page_climb_ap/pass`，
新中间页 + `I_CHECK_BATTLE_PASS_2` primary / 旧 marker legacy fallback，未改 `page_act` recognizer /
FIRE / Fatigue / Settlement / Resource；`tests/test_activity_shikigami_climb.py` `46 → 58`，0 regression。
`1357 → 1403` = §4.62
——`tasks/ActivityShikigami` 普通爬塔线接入本期新入口 `I_MAIN_GOTO_ACT_2`（旧图标回退）、
FIRE Contract 收口（`_enter_climb_battle` bounded battle-entry transaction + 窄 `_is_active_battle_entry()`
+ `REACTION_FIRE` + `ACTIVITY_FIRE_*` 有界，取代旧 `while True` + 宽 `is_in_battle(False)`）、
「稳定挑战页 + Challenge Ready」= Fatigue Safe Point（`_activity_challenge_safe_break`，唯一
`try_fatigue_break`，爬塔线 `random_sleep` 让位、无 macro-idle stack）、本期活动结算弹窗有界
drain 复用 GeneralBattle `C_RANDOM_DEFAULT`（`_drain_activity_settlement`，未改 GeneralBattle）；
大富翁 / 伪神降临 / GeneralBattle 未改；新增 `tests/test_activity_shikigami_climb.py`（46），
`ACTIVITY_FIRE_*` / `ACTIVITY_SETTLEMENT_*` PROVISIONAL / Level C 待验，见 §4.62、0 regression）；
`1357/1357`（§4.61 Level C 收口，未改代码，另重跑 swipe endpoint targeted `62 OK`；D022 =
Level C PASS / 当前默认冻结，见 §4.61 末尾）；`1321 → 1357` = §4.61
——普通滑动起终点从旧 `RuleSwipe.coord()` 的窄中心偏置（tiny ROI 有效 σ≈3~6px、同类滑动挤成一簇）
改为 `module/atom/swipe_endpoint.py` 的 v2 端点采样器（起终点各自独立、主集中高斯 + 少量宽尾、
夹到安全范围、联合保方向 / 有效距离；轴向 ROI `>=48px` 的轴 + 两端两轴都大时逐字保持旧
`_center_biased_int` → `S_BATTLE_RANDOM_*` / Summon 分布不变）；`RuleSwipe.sample_endpoints()` 委托它，
`BaseTask.swipe` 的 `coord()` → `sample_endpoints()`（唯一改动点）；`RuleSwipe.coord()` / `TouchSwipeModel` /
`Control` / BehaviorTrace 未改；新增 `tests/test_swipe_endpoint_sampling.py`（36），见 §4.61 / D022，
参数全 provisional / Level C 待标定，0 regression）；`1331 → 1321` = §4.60
——用户重新确认真实需求后**撤销** §4.58 + §4.59 基于错误理解（「Boss 后完全不领地图宝箱直接退出」）
新增的整套 Boss 专用退出结构（`_run_boss_exit_transaction` / `_is_boss_exit_success_state` /
`_complete_boss_business_cycle` / `_skip_treasure_once_at_entrance` / `BOSS_EXIT_*` / `ExplorationExitState`
等），恢复原项目**原生 reward / exit 链**（page_exp_main → `collect_reward` = 地图宝箱 or 小纸人 policy
→「Boss + 不领小纸人」走原生 `quit_exp_main`），solo Fatigue Safe Point 重挂到 `_maybe_boss_cycle_fatigue()`
（外层稳定页）；**独立成立的 §4.59 Rotation Contract 与 §4.58 Chapter FrameWait 保留不动**；
`tests/test_exploration_state.py` `66 → 56`（−10 全为删掉的废弃 contract 用例）；`1313 → 1331` = §4.59
Exploration Level C hotfix（**exit-transaction 部分已被 §4.60 撤销**，Rotation Contract 保留），
`tests/test_exploration_state.py` `48 → 66`；`1298 → 1313` = §4.58 Exploration Boss 直退 / Exit Contract
/ Chapter FrameWait / solo Fatigue Safe Point（Level A/B，**Exit Contract 已被 §4.60 撤销**），
`tests/test_exploration_state.py` `33 → 48`；`1297 → 1298` = §4.57：`_fire_again()` 内实际再战确认按钮 `I_FRESH_ENSURE` 增加独立 `RR_AGAIN_CONFIRM_DELAY=(0.3,0.6)`，经 `confirm_delay` primitive 的 fresh reconfirm / stale-click 防护；`tests/test_realm_raid_state.py` `103 → 104`，`tests/test_reaction_timing_batch1.py` 同步 timing-owner guard；0 regression）；`1287 → 1297` = §4.56
Level C hotfix —— `_fire_again()` / `_wait_again_entered_battle()` 的 positive battle-entry 判据从
`GeneralBattle.is_in_battle(False)`（含 `I_FALSE` / 胜负 / 奖励 marker，退四首战失败结算页恒 True
→ 误判「已进新战斗」）换成 RealmRaid-local 窄 helper `_is_active_battle_entry()` =
`is_in_prepare(False) or is_in_real_battle(False)`（复用 GeneralBattle 已有窄 detector，`is_in_battle()`
本体不动）+ OASX `cn_realm_raid_config.dart` 退四 / 勋章档位文案同步，`tests/test_realm_raid_state.py`
`93 → 103`；`1257 → 1287` = §4.56 correctness follow-up —— CONTINUE 用局部 `failed_orders`
真正跳过刚失败目标（不涂帧）+ Fatigue Safe Point 后移到 failure recovery 之后 + 退四入口 /
`_enter_target(require_only_remaining=True)` fresh 二次确认「仍是唯一可攻打目标」（`only_last` 仍用
raw `len(targets)`）+ 退四临时解锁改 `try/finally` 恢复 + `_realm_raid_cycle_safe_break` 前
`wait_until_appear(I_BACK_RED, wait_time=RR_CYCLE_STABLE_TIMEOUT)` 确认回稳定九宫格，
`tests/test_realm_raid_state.py` `63 → 93`；`1235 → 1257` = §4.56 RealmRaid 固定 1→9 + 取消勋章排序
+ `RR_TARGET_PACING (1.0,2.5)` 目标 pacing + 普通失败按 `when_attack_fail` + 「只剩最后 1 个可攻打
目标」才退四 + 退四前解锁阵容 + `_fire_again` 三态 bounded + 退四最终失败刷新 + RealmRaid Fatigue
安全节点，`tests/test_realm_raid_state.py` 重写、`tests/test_reaction_timing_batch1.py` 一行改；
`1230 → 1235` = §4.55 静态
复核后最小收尾——`_battle_entry_positive()` fallback 移除 `I_EXIT`（收窄为 `is_in_battle` 严格子集）+
docstring / GI_FIRE_TIMEOUT soft-budget 文档修正，`tests/test_general_invite_challenge_reaction.py`
`41 → 46`，11 consumer 0 behavior change；`1212 → 1230` = §4.55
`GeneralInvite.click_fire()` Battle Entry post-click 状态机 / bounded FSM 收口，
`tests/test_general_invite_challenge_reaction.py` `23 → 41`；`1189 → 1212` = §4.54
通用组队挑战按钮 Reaction Timing 补齐（`GeneralInvite.click_fire`），新增
`tests/test_general_invite_challenge_reaction.py`（23）；`1162 → 1189` = §4.53
常驻刷本 FIRE FSM 第二批（Orochi / EvoZone 单人）+ Fatigue 安全节点第一批，新增
`tests/test_second_batch_fire_fsm.py`（27）+ 改 `test_fire_reaction_fsm.py::OtherFireNotMigratedTest`（净 0）；
`1156 → 1162` = §4.52 同轮「FIRE post-click 三态边界收口」`tests/test_fire_reaction_fsm.py` `29 → 34` +
`test_realm_raid_state.py` `FireCharacterizationTest` `7 → 8`；`1126 → 1156` = §4.52 RyouToppa/RealmRaid
FIRE reaction 统一 `REACTION_FIRE` + RealmRaid `fire()` R-R1；`1092 → 1126` = §4.51 第一批 Reaction
Timing 迁移 34 项；`1088 → 1092` = §4.50 T7 `AdaptPreferredBySizeTest` 4 项）。`appear_then_click`
primitive 本体未改，`tests/test_base_task_confirm_click.py`（5）继续锁其行为。
下方长段保留 1088 基线之前各模块的历史增量说明；其中总数与 `test_click_profile.py` 87 项已由
本段更新。

`toolkit/python.exe -m unittest discover -s tests` 最近一次为完整 Python `1088/1088 OK`（系统 `D:\miniconda3\python.exe` 缺 `zerorpc` / `websockets`，无法跑；`1067 → 1083` = 全仓 Swipe Consumer 迁移新增 `tests/test_base_task_swipe_trajectory.py` 16（§4.48）；`1083 → 1088` = 全仓 FrameWait + confirm_delay 审查、`list_find` 翻页 settle 迁到 FrameWait、`tests/test_list_find.py` `22 → 27`，见 §4.49）。其中 `tests/test_touch_swipe_model.py` 单模块 `56/56 OK`（TouchSwipeModel 第一阶段基础设施 `29`；**第二阶段**平滑时间扰动 + 尾段慢拖 `29 → 50`；**segment/dt 对齐修正** `50 → 56`，867 → 888 → 897，见 §4.42「第二阶段」/「segment speed 与 dt 对齐修正」/ D018 第二阶段追加）、`tests/test_minitouch_trajectory_executor.py` 单模块 `15/15 OK`、`tests/test_control_swipe_trajectory.py` 单模块 `13/13 OK`（TouchSwipeModel 第一阶段 `9`，783 → 836；**Swipe Trajectory Backend（§4.46，2026-09-07）+4**：`swipe_trajectory` 的 ACTION 带完整 `extra.trajectory` / 60 点仍一条 / float 取整 / 关闭态不组装 extra / legacy `Control.swipe` 只端点无 `trajectory` 键，见 §4.46 / D004 补记）、`tests/test_touch_swipe_mumu_tool.py` 单模块 `37/37 OK`（TouchSwipeModel MuMu Level C 测试工具的纯逻辑：836 → 856 建工具、856 → 867 PNG 主图改 1280×720 实屏比例 + zoom view、888 → 897 `trajectory_segments` executor 时间对齐，零生产改动，见 §4.42）、`tests/test_fatigue.py` 单模块 `92/92 OK`、`tests/test_kekkai_utilize_threshold.py` 单模块 `26/26 OK`（KU 单向分区搜索改造：25 → 26，`lower_reward_tier` 档位阶梯 + `_card_meets_pass` PASS 阈值）、`tests/test_kekkai_activation_state.py` 单模块 `18/18 OK`、`tests/test_kekkai_k4_selected_anchor.py` 单模块 `11/11 OK`（K4-A `detect_selected_anchor`：NMS 后 0/1/>1 → unavailable/available/unavailable、`center_y=y+h/2`、任意连续 Y 命中、score 保留、不调 `coord()`、不引用 commanded 位移，见 §4.47）、`tests/test_kekkai_k4_projection.py` 单模块 `21/21 OK`（K4-B `actual_scroll_dy_px`（before−after、保留 sub-row、非法→None）/ `project_bbox`（y−dy）/ `bbox_iou` / `dedup_by_projection`（同类型 + IoU>0 一对一贪心、投影出屏忽略、全 dup→[]），见 §4.47）、`tests/test_kekkai_utilize_state.py` 单模块 `94/94 OK`（KU 单向分区搜索改造：23 → 46；**K1 TouchSwipe 接入** `46 → 53`；**PASS 前初始化简化** `53 → 62`（944 → 953）；**K2 随机小步位移** `62 → 69`（977 → 984，首档 `SWIPE_DISTANCE_RANGE=(212,265)`；**2026-09-07 Level C 回调为 `(140,180)`**，用例值同步、数量不变）；**K2 轻微整体斜度** `84 → 86`（1025 → 1027 —— `SWIPE_LATERAL_OFFSET_RANGE=(-12,12)`，`end_x=clamp(start_x+lateral, *SWIPE_START_X_RANGE)`，+2 用例：中段起点能左/右斜/竖直·贴边界退化竖直·大样本 `end_x` 恒合法且三向都出现·源码断言；K1/K3 用例 `random_int` side_effect 补第 4 值）；**K3 swipe 后 FrameWait** `69 → 83`（984 → 998）；**K3 追加：显式 `poll_interval`** `83 → 84`（998 → 999 —— `PerformSearchSwipeK3Test` +1 `test_frame_wait_gets_explicit_positive_poll_interval`：`poll_interval` 被显式传且 = `SWIPE_WAIT_POLL_INTERVAL` > 0、远小于旧 `sleep(2)`、4 个判定阈值不动；另 `test_provisional_params_flagged_level_c` 加 `SWIPE_WAIT_POLL_INTERVAL` + 断言注释含 `pacing`，`test_real_frame_wait_signature_smoke` `patch.object(KU, 'SWIPE_WAIT_POLL_INTERVAL', 0.0)` 避免真 sleep）。K3 首版 13 用例：changed&stable→True / no-change·unstable·timeout→False / baseline 取 swipe 前 / 调用顺序 shot→traj→clear→wait / FrameWait 收到 `SWIPE_WAIT_ROI` + 4 个 provisional 阈值 + 有限 timeout + provider=`device.screenshot` / 一次 swipe 一次 FrameWait 无重试 / minitouch 源码无固定 `sleep(2)` / `_run_search_pass` 把 False 映射 ABORT 不经空卡 marker / ROI 是 card-column 非整屏 / 怠惰·非 minitouch 回退仍 2 秒不接 FrameWait / 真实 FrameWait 签名冒烟 / K1·K2 未被 K3 影响，外加 `RunSearchPassTest` +1 失败→ABORT 集成用例、`UtilizeStructureTest` 的「零 FrameWait 消费者」用例改成正向锁「唯一消费者 = `_perform_search_swipe`」），见 §4.41「K3」；**K4 selected anchor + 投影去重** `86 → 94`（1027 → 1067 —— `RunSearchPassTest.setUp` patch `detect_selected_anchor` 为 unavailable 让既有 8 用例走 K4 完整扫描回退、行为不变；新增 `K4IntegrationTest` 8：dedup 只点 new、measurement unavailable → 完整扫描、全 duplicate 不 ABORT/BOTTOM、K3 失败仍 ABORT 且不进 K4 after anchor、BOTTOM 仍只认 `I_U_EMPTY_CARD`、`K4_ENABLED=False` → 纯 D017、new 候选仍走 threshold、源码接线断言，见 §4.47 / D017 K4 补记）、`tests/test_realm_raid_state.py` 单模块 `41/41 OK`（cleanup 批次 1 后 41 → 39；2026-09-08 R-R1 收口 `FireCharacterizationTest` / `LoopAndWaitBoundsTest` 改锁新形态 39 → 40；FIRE 三态边界收口 `FireCharacterizationTest` 40 → 41）、`tests/test_exploration_state.py` 单模块 `33/33 OK`，`tests/test_base_task_wait_until_appear.py` 单模块 `5/5 OK`、`tests/test_behavior_trace.py` 单模块 `15/15 OK`（+1 `is_recording()` 反映 enabled / `_broken`，§4.46）、`tests/test_swipe_duration_cleanup.py` 单模块 `7/7 OK`、`tests/test_base_task_swipe_trajectory.py` 单模块 `16/16 OK`（全仓 Swipe Consumer 迁移，§4.48：`BaseTask.swipe_trajectory` helper minitouch→轨迹 / 非 minitouch→端点回退 / `generate` 只一次 / `control_name` 透传 / `<10px` 回退 / `fallback=False` 抛 / 异常不吞 / 无 screenshot·sleep·retry；`BaseTask.swipe` 委托 helper；GeneralBuff 迁移源码断言）、`tests/test_rule_swipe_trace_removed.py` 单模块 `4/4 OK`、`tests/test_frame_state.py` 单模块 `25/25 OK`、`tests/test_frame_wait.py` 单模块 `20/20 OK`、`tests/test_list_find.py` 单模块 `27/27 OK`（`22 → 27`：翻页 settle 迁到 `wait_for_changed_and_stable`（W1 结构性 settle、结果不参与控制流），锁 baseline=翻页前帧 / ROI=`RuleList.roi_back` 换算 / provider=`device.screenshot` / timeout 结果不改收敛不 BOTTOM / `_list_roi_back_to_box` 单测 / settle-wait 异常透传，见 §4.49）、`tests/test_manual_click_recorder.py` 单模块 `31/31 OK`、`tests/test_manual_click_analyze.py` 单模块 `39/39 OK`、`tests/test_runtime_roi_probe.py` 单模块 `11/11 OK`、`tests/test_click_sampler.py` 单模块 `19/19 OK`（T7-5 改写 6 个锁旧默认的用例）、`tests/test_rule_ocr_float_roi.py` 单模块 `18/18 OK`（RuleOcr 浮点 OCR bbox → 整数点击 ROI 兼容：`904 → 922`，见 §4.43）、`tests/test_t7_5_preferred_hotspot.py` 单模块 `22/22 OK`（T7-5 Stage 1 全局 preferred 热点默认：`922 → 944`，见 §4.44）、`tests/test_t7_5_stage2.py` 单模块 `24/24 OK`（T7-5 Stage 2 收口：`sample_region` / `default_region` / `RuleLongClick` / GeneralInvite + Secret 迁移 / double-sampling 审计，`953 → 977`，见 §4.45）、`tests/test_click_profile.py` 单模块 `87/87 OK`、`tests/test_behavior_click_stats.py` 单模块 `45/45 OK`（`24` → `45`：`test_response_shape` 改为 additive 键集 + 新增 `ReadBehaviorSwipesTest` 7 + `BehaviorStatsFilterTest` 14 —— swipe 解析 / 旧 JSONL 兼容 / 坏 trajectory 单条降级 / `swipe_count` 计数 / `all·click·swipe` + `task` + `target` 四层过滤 + Case A~D + `available_tasks·available_targets`，见 §4.46 / D011 补记）、`tests/test_click_roi_inventory.py` 单模块 `29/29 OK`、`tests/test_large_click_roi_review.py` 单模块 `50/50 OK`、`tests/test_general_battle_timing.py` 单模块 `17/17 OK`、`tests/test_general_battle_settlement.py` 单模块 `54/54 OK`（SETTLEMENT CONTRACT V3 重写：37 → 54；T7-5 Stage 2：`SamplingTest` 3 + `RegressionBoundaryTest` 1 用例改 `sample()` → `sample_region()`，计数不变）、`tests/test_settlement_trace_check.py` 单模块 `17/17 OK`（v3 三区域最小更新）、`tests/test_ryoutoppa_c_area_1_point_opt_in.py` 单模块 `25/25 OK`。覆盖：

- BaseTask `confirm_delay`
- BaseTask `wait_until_appear_then_click` 参数绑定：`wait_time` 必须关键字传参、默认 `None` 同样走关键字、超时返回 `False` 且不点击、首轮不得跳过截图、`wait_time=None` 时不建计时器
- BehaviorTrace v1：关闭时不建目录 / 不开文件 / 不进写入路径、开启时写合法 JSONL 且字段正确、`set_task` 默认值与显式覆盖、`TASK` 事件形状、append 不覆盖、`extra` 含 datetime / 异常 / 任意对象仍安全序列化不抛、`_open_handle` 抛 `OSError` 与 `json.dumps` 抛 `TypeError` 均被隔离且自禁用（`_broken=True`、后续调用只 return、不再尝试打开）、跨天轮转生成两个日期文件且旧文件不被改、多 config 独立文件、10000 条 enabled + 100000 条 disabled 吞吐冒烟（非严格上限，仅打印数量级）
- Control.swipe duration 后端契约：minitouch / scrcpy / window_message 调用底层 swipe 时**不带** `duration` kwarg，uiautomator2 / adb **带** `duration` kwarg；RyouToppa `flush_area_cache` 保持原逻辑——`attempt == 1` 走 `random_delay(0.342, 0.362)`、retry 走 `random_delay(0.349, 0.355)`，swipe 调用带 `duration` kwarg，起点 / 终点 / distance 抖动逻辑不变，首次识别成功只滑一次、识别失败重试第二次
- RuleSwipe 死代码清理：模块可正常导入、`coord()` 仍返回 4 元组且落在 ROI 内、`trace` / `is_default_mode` / `is_vector_mode` 已从 `RuleSwipe` 移除、`swipe.py` 不再出现 `import random` / `from math import dist` / `cached_property` / `BezierTrajectory` import
- 普通滑动端点空间分布 v2（`tests/test_swipe_endpoint_sampling.py`，D022 / §4.61）：`SwipeEndpointParams` 构造 + frozen + 非法值 fail-fast、ROI 类型 / 形状校验、输出 4 整数、永不越屏幕安全边界、贴角 ROI（0,0,10,10）不出负坐标、起终点各自独立（`(end-start)` 长度 / 角度都在变、`start_x`·`end_x` 相关性 < 0.2）、tiny ROI 起点 sd 比旧 `coord()` 明显更大但仍集中（>75% 在中心 ±15px）、方向 / 有效距离 / 主轴符号在 8 个代表资产 + 全仓静态普查上逐样本成立、章节 `S_SWIPE_LEVEL_UP/DOWN` 手指上下方向不反、两端两轴都宽（`S_BATTLE_RANDOM_*` / Summon）只走 `_center_biased_int` 且分布与旧 `coord()` 一致（delta<3）、混合宽窄轴只放宽窄轴、`random_normal` 病态时有界回退到 `(preferred_start, preferred_end)` 且源码无 `while True`、`RuleSwipe.sample_endpoints()` 委托 + `coord()` 不变、`BaseTask.swipe` 源码用 `sample_endpoints()`、采样端点原样到达 `swipe_trajectory` / `TouchSwipeModel.generate` 精确首末点、K1~K4 / `list_find` / drag / press-and-drag 不经端点采样器
- frame_state：`frame_difference` 相同帧=0 / 全图变化=1 / score 恒 `[0,1]` / ROI 内外隔离 / 小面积噪声占比精确 / 灰度支持 / shape 不一致与非法 ROI 报 `ValueError`；`FrameStateDetector` 一直静止→`changed=F` `stable=T`、变化后稳定→`changed=T` `stable=T`、持续变化→`stable=F`、变化后回基线→`changed` 不回退、相邻明显变化清零 `stable_count`、`reset` 清空状态、首个 `update` 帧自动作基线、构造参数校验
- frame_wait（`wait_for_changed_and_stable`）：变化后稳定→`success`、从未变化→`timed_out` 且 `changed=F`（即使 detector `stable=T`）、持续变化→`timed_out` 且 `stable=F`、变化后回基线→`changed` 锁存仍 `success`、`stable_count` 中途重置后重新累计、注入推进 clock 的 timeout 边界（无真实 sleep）、`frame_provider` 第 N 次抛异常透传不伪装 timeout、帧 shape 不一致 / 非法 ROI / 非法阈值由 detector 抛、非法 `timeout`（0 / 负 / bool / 非数值）与负 `poll_interval` 由本层抛、`frames_checked` 不含 baseline、`poll_interval>0` 调注入 sleeper 且默认 0 不 sleep、ROI 圈定等待范围、不推进 clock 触发 `_MAX_POLLS` 抛 `RuntimeError`、结果 `frozen` dataclass
- list_find characterization（`tests/test_list_find.py`，锁现状不锁应然）：第一屏命中→0 swipe / 0 sleep 且原样返回识别元组、翻页 N 次后命中→N+1 截图 / N swipe / N sleep 且顺序恒为 `screenshot → find → swipe → sleep → screenshot`（绝不 swipe 先于 find）、未命中耗尽 `max_swipe`→`return False` 且末轮仍 swipe+sleep、`max_swipe<=0`→0 截图直接 `False`、`target` falsy→0 截图 `False`、image 模式 `swipe_pos(after=True)` 恒定 / ocr 模式 `swipe_pos(number=1, after=result>0)`、ocr 空结果哨兵 `(0,0)` 被当命中、翻页等待恒为 `sleep(random.uniform(0.8, 1.3))`、screenshot / finder / swipe 异常均直接透传（无 try/except，swipe 异常时 sleep 未发生）、无 bottom detection 只有 `max_swipe` 收敛；`list_appear_click`：命中且传 interval→点击 `device.click(x,y)` 返回 True，命中但 `interval=None`→返回 False 不点击，未命中→False
- behavior 点击统计：`Control.click/long_click` 的 ACTION `extra` 带最终 `x/y`（caller 传 float 时取 int）、底层动作抛异常不生成 ACTION、disabled 零 IO；`read_behavior_clicks` 只回 click/long_click 有坐标点、旧格式无坐标跳过、多任务按首现顺序、空文件/缺文件返回空、坏 JSON 行跳过并计 `skipped_lines`、非法 config（`../` `.` `a.b` 控制字符等）与路径穿越报 `BehaviorStatsError`、非法 date 报 422、point 保持文件顺序、summary 计数、响应顶层 `screen=1280×720`、config 后缀归一化
- behavior swipe 轨迹（§4.46，2026-09-07）：`Control.swipe_trajectory` 的 ACTION `extra` 带 `start_x/y·end_x/y·point_count·trajectory([[x,y,dt],...])`（60 点仍一条 ACTION、caller 传 float 取 int、`is_recording()` 关闭态不组装 extra、executor 抛异常不生成 ACTION）；legacy `Control.swipe` 只带端点无 `trajectory` 键；`BehaviorTrace.is_recording()` 反映 `enabled and not _broken`；`read_behavior_clicks` 解析 `swipes[]`、旧 swipe 无 trajectory → `[]`、单条坏 trajectory 只降级该条计 `malformed_trajectories` 不 500、一条 swipe `swipe_count` 只 +1；`interaction_type ∈ {all,click,swipe}`（大小写不敏、非法 400）、`task` / `target`（click·swipe 同语义）四层等值 AND、Case A~D、`available_tasks/available_targets` 排除自身维、旧键与 `tasks/points/summary` 旧计数不变

### BehaviorTrace Swipe schema（前端待接，OASX 下一轮消费）

`GET /stats/{script_name}/behavior/clicks?date=YYYY-MM-DD[&task=<name>&interaction_type=all|click|swipe&target=<name>]`

响应（**additive**，旧字段不变，新增标 `NEW`）：

```jsonc
{
  "config": "oas1", "date": "2026-09-07",
  "screen": {"width": 1280, "height": 720},
  "filter":            { "task": "", "interaction_type": "all", "target": "" },   // NEW，回显生效过滤
  "summary": {
    "total": 12,               // 旧：命中过滤的 click 点数（== click_count + long_click_count）
    "click_count": 9, "long_click_count": 3,
    "task_count": 2, "skipped_lines": 0,
    "swipe_count": 4,           // NEW：命中过滤的 swipe ACTION 数（一条 swipe 无论多少点只 +1）
    "filtered_count": 16,       // NEW：当前过滤命中的 ACTION 总数（click + swipe）
    "malformed_trajectories": 0 // NEW：trajectory 被降级的 swipe 条数
  },
  "tasks": ["KekkaiUtilize", "RyouToppa"],          // 旧：命中过滤的 click 点里的任务，首现序
  "available_tasks":   ["KekkaiUtilize", "RyouToppa"],   // NEW：排除 task 维、按 type+target 过滤后 distinct
  "available_targets": ["KEKKAI_UTILIZE_SWIPE", "I_FIRE"], // NEW：排除 target 维、按 task+type 过滤后 distinct
  "points": [ { "x": 640, "y": 360, "task": "...", "action": "click", "target": "I_FIRE", "ts": "...", "elapsed_ms": 42 } ],
  "swipes": [ {                                     // NEW
      "task": "KekkaiUtilize", "action": "swipe", "target": "KEKKAI_UTILIZE_SWIPE",
      "ts": "2026-09-07T10:00:01.000+08:00",
      "start": [400, 540], "end": [400, 320],       // [x,y]，legacy 端点滑动可能为 null
      "point_count": 37,
      "trajectory": [[400,540,0],[400,533,8], ...], // [x,y,dt_ms]；旧日志 / legacy swipe 为 []
      "elapsed_ms": 210
  } ]
}
```

前端 query 参：`task`（精确）/ `interaction_type`（`all`/`click`/`swipe`，非法 422）/ `target`（精确，click·swipe 同一参数）。四层 `date AND task AND interaction_type AND target`。`swipes[].trajectory` 是**一个 ACTION 内部**的 MOVE 路径（原始 1280×720 坐标，前端复用现有 click 坐标变换），**不要**和「多个 click 之间的时序连线」混成同一个 path。**commanded input，不是实际 UI 滚动位移**（K4 才有 actual scroll）。
- manual_click_analyze（`tests/test_manual_click_analyze.py`）：`collapse_bursts` 单点 / 快速同坐标 4 连 / 小幅漂移 / 超时间断开 / 超距离断开 / 链式判断（P1→P2、P2→P3 合法但 P1→P3 超阈值仍一个 burst）/ 不同 `target` 不合并 / 缺标签视为兼容 / 覆盖全部下标不重叠；`burst_record` 代表点取第一点、centroid 单独算、继承标签；`landing_stats` 与 `statistics` 一致、分位数单调、归一化 1280×720、径向分位有序、ROI u/v；`burst_size_histogram` 分桶；`region_split` 水平切；`detect_calibration_prefix` 边缘点+大间隔前缀命中 / 无大间隔返回 0 / 前缀无边缘点返回 0 / 空输入；`kmeans_clusters` 三个分离 blob 收敛正确 / `max_iters=1` 单次分配 / 空种子拒绝；`transition_counts` 相邻标签转移计数；`load_jsonl` 跳坏行且不改原文件；`analyze` 只写派生文件 / `collapse_ratio` 正确 / 敏感性含 4 组固定阈值 / 三簇 + 校准剔除场景 / `calibration_count` 覆盖跳过启发式 / `exclude_calibration=False` 报 disabled；**`landing_stats` ROI 过滤**：传 roi 时只用 inside 子集算 mean/std/percentile、外点进 `outside_count/outside_ratio/outside_points` 不 clamp、全部外点时 inside count=0 不给 u/v、不传 roi 仍用全部点、`p25_u/p75_u` 等补齐
- runtime_roi_probe（`tests/test_runtime_roi_probe.py`，纯函数不装真实设备 / RPC）：`build_probe_record` matched 带 `roi_front/center/template_w/h` + unmatched 不带这些 + JSON 可序列化；`probe_record_path` 用 target+日期；`append_probe_record` 追加合法 JSONL；`summarize_roi_samples` 全同 ROI→stable、ROI 有变化→报范围且不 stable、全未匹配→不 stable、空→不 stable；`resolve_target` `I_FIRE` 解析为带 `match`/`roi_front` 的对象、未知 target 报错
- click_sampler（`tests/test_click_sampler.py`）：`ClickSampler.sample` 默认输出落在 ROI 半开区间 / 整数元组 / 不 mutate 输入 ROI / 连续不同 ROI 每次用当前值不缓存 / 1×1 ROI 恒定 / 注入固定 RNG 能取到上下界（无中心偏置）/ 透传 `random_point_in_roi` 的 `TypeError`·`ValueError`；`LEGACY_UNIFORM` 转调 `random_point_in_roi` 且参数与返回值原样、同一 RNG 序列下与直接调用逐点一致、默认策略即 `LEGACY_UNIFORM`；`HABIT/STRICT/UNIFORM` 已实现、结果落在 ROI 内、未知策略抛 `ValueError`；`RuleClick.coord`(源码里仍只 `ClickSampler.sample(self.roi_front)` 不传 strategy) / `RuleLongClick.coord`（继承）/ `RuleImage.coord`（含 `roi_front` 动态改写后用新值）/ `RuleGif.coord` / `RuleOcr.coord`（FULL 用 `area`、SINGLE 用 `roi`）都经 `ClickSampler.sample` 且返回值结构不变、端到端边界不变。`ClickSampler.sample_point`（T7-3.2 薄组合入口）的覆盖在 `tests/test_ryoutoppa_c_area_1_point_opt_in.py`（见下）
- click_profile（`tests/test_click_profile.py`）：`ClickProfile` frozen / 权重归一化 / `without_tail` / preferred·sigma·weight·margin·max_attempts 非法即 `ValueError` / 内置 profile 全合法且类别间纵向热点与 sigma 有序（tiny 最窄 → large_area 最宽）/ **8 个内置 profile 全部标 `provisional=True`**（T7-3.1：`wide_card`·`normal_button`·`large_area` 也补上）；`resolve_profile` None→default、名字、未知回退 default、实例透传、错误类型抛 `TypeError`；`_safe_roi` margin=0 返回原 ROI、正常收边、tiny ROI 仍活、margin 过大抛 `ValueError`、不 mutate 输入、非整数 ROI 抛 `TypeError`；HABIT：热点传进 `random_normal`、core/medium 用各自 sigma、每次只选一个成分、tail 在 Safe ROI 内均匀、`_choose_component` 按累计权重、越界候选被 rejection 重采、用尽 `max_attempts` 后 fallback 到 Safe ROI 内热点投影（非边界 clamp）、贴边热点投影夹进内边距、大样本恒在 Safe ROI / 均值近热点、profile=None 用 default；STRICT：默认窄 profile 居中且 >90% 落中心±20px、强制去 tail、拒绝 wide_card/large_area 宽 profile（`ValueError`）、接受 tiny/small、spread 显著窄于 habit wide、恒在 Safe ROI；UNIFORM：在 Safe ROI 内均匀、margin=0 profile 等于整 ROI、与 `LEGACY_UNIFORM` 名字不同（LEGACY 不收边能取到边缘区）；LEGACY 路径：不调 `resolve_profile`、同 RNG 序列与直接 `random_point_in_roi` 逐点一致；**T7-2 Point 尺寸适配**（+21）：锚点 `(24, 96)`、`point_size_factor` 的 `≤24→0` / `≥96→1` / `60→0.5` / smoothstep 精确公式 / `[0,1]` 且单调不减 / 两端一阶导为 0（无线性折点）；`adapt_point_profile` 取 `short_side=min(w,h)`（`320×60` 与 `60×320` 同结果）、`normal_button` / `wide_card` 各代表尺寸 effective `(u,v)` 精确值、大 ROI 不超过 base hotspot、小 ROI 不越过中心反漂、随 `short_side` 增大单调趋近 base（preferred）、`base_u<0.5` 向左释放、base 不被 mutate、返回新 frozen profile、非法 ROI 抛 `ValueError`/`TypeError`（项目风格）、不调 RNG / 设备、`ClickSampler` 默认行为不变；源码无 `tiny`/`small`/`DEFAULT_PROFILES`/`if short`/`elif` 离散分支、`tiny`/`small` 仍注册在 `DEFAULT_PROFILES`；**T7-3.1**（+3）：`wide_card` 代表尺寸基线改用 `(0.58,0.59)`（ss=24→`(0.5,0.5)`、ss=60→`(0.54,0.545)`、ss=96→`(0.58,0.59)`、ss=200 clamp）、`C_AREA_1` WIP ROI `(514,141,223,116)` short_side 116 → effective==base 回归锁、`wide_card`·`normal_button`·`large_area` `.provisional is True`、`DEFAULT_PROFILES` 每个条目 `.provisional is True`；**T7-4 Point spread 适配**（+19）：锚点常量 `POINT_MIN_CORE_SIGMA_U/V==tiny.core_σ`、`POINT_MIN_MEDIUM_SIGMA_U/V==tiny.medium_σ`、锚点比 `normal_button`/`wide_card`/`large_area`/`default` base 都窄但 `>0`；`f=0`（ss≤24）→ `core/medium σ` 恰为锚点、`tail_weight` 恰为 `0.0`、`preferred` 恰 `(0.5,0.5)`、削掉的 tail 回补 core（`medium_weight` 不动）；`f=1`（ss≥96，含 `C_AREA_1` ss=116）→ EffectiveProfile **逐字段等于 base**（`dataclasses.fields` 全比）；`sigma`/`tail` 随 ss 单调趋向 base、被夹在锚点与 base 之间、24→25 / 40→41 / 95→96 无折点跳变；三成分权重和恒 `≈base 和(1.0)` 且非负；`safe_margin`/`max_attempts`/`provisional`/`name` 仍原样透传；代表尺寸表（`normal_button`/`wide_card` 各 11 档 σ/weights 精确值）；40×30（ss=30）小按钮示例 `core_σ_u≈base 的 47%`、`tail≈0`、`preferred` 贴中心；base 不被 mutate、结果 frozen；`adapt_point_profile` 源码仍无离散分支 token
- ManualClickRecorder（`tests/test_manual_click_recorder.py`，纯函数不装真实钩子）：`screen_to_logical` 1:1 视口 / 缩放视口保持比例 / 窗口移动同一 client 点逻辑坐标不变 / resize 后相对比例一致 / 视口外 `inside=False` 且不 clamp（坐标可为负 / 超 1280）/ 非法几何抛 `ValueError`；`relative_uv` 中心 u=v=0.5 / 已知分数精确 / ROI 外不 clamp；`parse_roi` 合法 + 拒绝缺项 / 非数 / w·h≤0 / 负 / 越 1280×720；`is_injected_event` 只认 `LLMHF_INJECTED` 位；`match_mumu_toplevel_title` 认 MuMu / NemuPlayer 拒其它；`viewport_sanity` 接受 1280×720 与 1024×576@1.25、拒错窗口（提示 `--hwnd`）与退化尺寸；`build_sample` schema / 逻辑坐标 / roi 加 `u/v/inside_roi` / 外围不 clamp / JSON 可序列化；`ManualClickStats` 无 ROI 只计数、有 ROI 的 `mean/std` 与 `statistics.mean/pstdev` 一致且 ROI 外样本不进 u/v；`ManualClickWriter` 多条 append 不 truncate / reopen 追加 / 跨天轮转两文件 / 含 `_` config 名不截断 / `../evil` 路径穿越被拒；`resolve_config_name` 保留合法（含 `account_group_1`）、拒 `../` `.` `/` `\` 空 `template` 控制字符
- click_roi_inventory（`tests/test_click_roi_inventory.py`，纯 AST + 纯统计，不 import Task）：`RuleClick`/`RuleLongClick`/`RuleImage` 从 `roi_front` 抽 ROI、`RuleOcr` 非 Full 用 `roi`·Full 用 `area`、`RuleGif` 计入、`RuleSwipe`/`RuleList` 不计入；四元组字面量解析（含负整数）、表达式 / 变量 / `a+b` 计算 ROI 标 `unknown` 不猜、`<inline>` 占位符号；`C_*RANDOM*` 标 `large_safe_area` + `very_large`；`_classify_size` 的 short/long/area/aspect、degenerate(0)、very_thin(AR≥5)、very_large(short≥300 或 area≥30 万)、None 输入；`_percentile` 线性插值 + 空为 NaN、`dist_stats` 基本量 + 空、`histogram` 左闭右闭；`build_summary` 的 `unique_clickable_roi_defs` / `primary_count` 计数、`confirmed_clickable` 无条件含 RuleClick·RuleImage 需 `has_click_consumer`；真实仓库冒烟（记录数 > 500、`primary_count` > 300、类型分布无 `RuleSwipe`）
- large_click_roi_review（`tests/test_large_click_roi_review.py`，纯 AST，不 import Task）：符号名识别（接受 `C_OK`/`I_FIRE`，拒 `self`/`click`/`Config`）、`_symbols_in` 返回 `(符号, 限定前缀)`；消费者索引的 click / detect / coord / `random.choice`→indirect_click 分类、跨行调用、最内层 `def` 归属、未知 verb 不入索引、语法错误源码跳过；`build_assets_class_map` 在真仓库解析出 `GeneralBattleAssets`→`tasks/Component/GeneralBattle/assets.py`；`attribute_usages` 的唯一符号 exact、限定前缀指向别处则丢弃（`exact_by_qualifier`）、指向本条则保留、`self.` 前缀仍 ambiguous；语义初判各分支（RANDOM 优先于尺寸、整屏、结算、登录固定区、RuleImage→dynamic_template、卡片、方形大按钮）、Point/Region 分类、P0/P1/P2 规则、死资产 / 纯检测 / 窄长条追加检查问题；`build_items` 的门槛过滤、RuleOcr 永不入主清单、纯检测 RuleImage 排除、有点击消费者的 RuleImage 计入、零消费者 RuleClick 仍入清单但标 UNUSED、同名多 scope 的 ambiguous、编号连续且按 P→面积排序、`review_status` 恒 `pending`、模板 PNG 路径解析；`build_excluded` / `build_all_random`（不受门槛限制、跳过 RuleOcr）/ `build_very_large`（含纯检测项、判定文案）/ `is_settlement_group`；真实仓库冒烟（无 RuleOcr、全部 ≥96、`C_RANDOM_CLICK` 确有点击调用方）
- RuleSwipe 与中心随机点
- settlement_trace_check（`tests/test_settlement_trace_check.py`，16 用例，纯静态，不接设备，Contract v2）：只保留 `random_rd` / `random_rd2` 的 ACTION click、缺 `extra.x/y` 跳过、按 `ts` 排序；`coord_stats` 的 ROI-relative `(u,v)` / Safe ROI 内外 / 越界标记 / `distinct_xy` / 空输入；`build_report` —— 同一语义 Page 连续多帧点 RD（间隔 ~0.8s）判 OK 且不含任何 v1 键（`rd_to_rd2_gaps_s` / `observe_window_violations` / `stage_boundary_candidates` / `fast_rd2_gaps`）；短时间两次 RD（0.5s）不判违规；明显过快间隔 `< _MIN_REASONABLE_GAP`（= `0.7*0.5`）判 `fast_repeat_gaps` → FAIL；Safe ROI 越界 → FAIL；`count>=3` 且坐标全同 → FAIL；`>12s` 间隔切段；间隔汇总 `gap_summary`；无结算点击判 `NO_DATA`。
- general_battle_settlement（`tests/test_general_battle_settlement.py`，37 用例，Settlement Contract v2，纯静态）：**timer 驱动节奏**——首次即点 `C_RANDOM_RD`、未到点跳过、到点再点、同一 Page 每个 timer 周期都可继续点 RD（`["random_rd"]*5`）、`_settlement_click` 源码不含任何 v1 token（`settlement_primary_ts` / `settlement_fallback` / `settlement_stage` / `OBSERVE_SECONDS` / `monotonic` / `C_RANDOM_RD2` / `_advance_settlement`）；**每次重采**——间隔 `[0.72, 0.91, 0.78]` 依次成为 `timer.limit`、坐标每次重新 `ClickSampler.sample`；**`_handle_result`**——调 `_settlement_click(context)`、不引用 `_reward_marker_present`/`REWARD_MARKERS`/`primary_enabled`、still-result 时重复点 RD、与 HEAD 逐句形状一致；**`_handle_reward`**——两个特殊弹窗按 `(I_OVER_GHOST, I_GB_SKIN_CONFIRM)` 顺序无条件 `appear_then_click(interval=0.8)`、点中也不早退、然后 `_settlement_click(context)`、still-reward 时重复点 RD、`context.is_win = True`；**Contract v1 已彻底移除**——`gb` / `GeneralBattle` 无 `REWARD_MARKERS` / `_SETTLEMENT_PRIMARY_OBSERVE_SECONDS` / `_reward_marker_present` / `_advance_settlement` / `_reset_settlement_stage` / `_sync_settlement_stage`、`BattleContext` 无 `settlement_stage`/`settlement_primary_ts`/`settlement_fallback`、`_reset_round_context` 无 v1 重置、主循环无 `_sync_settlement_stage`；**间隔配置**——`SETTLEMENT_CLICK_INTERVAL_RANGE == (0.7, 1.0)`、非 `(0.8, 0.8)`、`_next_settlement_click_interval` 每次 `random_delay(0.7, 1.0)`、`RealmRaid` 保留 `(0.65, 0.95)` override、其它 subclass 无 override；**profile 未改**——RD `preferred (0.54,0.53)` σ `(0.10,0.10)`/`(0.16,0.16)` 权重 `0.80/0.17/0.03` `margin (0.06,0.06)` `max_attempts 12`、屏幕热点 `(1009,563)`、`_SETTLEMENT_FALLBACK_PROFILE` 在源码里除定义处零引用、`C_RANDOM_RD2` Asset 保留、两 profile 不在 `DEFAULT_PROFILES`；`_sample_settlement_click` 走 `strategy=HABIT` + `control_name=rule.name`、采样异常 `logger.error` + 退回整 ROI 均匀、不经 `BaseTask.click`；回归护栏 `test_random_click_default_right_only_intentional_baseline`（T7-3.2 改名自 `test_random_click_signature_not_touched_by_t7_line`）——`tasks/GameUi/default_pages.py` 的 `random_click` 默认 `ltrb == (False, False, True, False)`（仅 RIGHT）是**用户本人有意的业务修改**（从历史 `(T,F,T,F)` = LEFT+RIGHT 改来），锁为当前工作树的**有意基线**，T7 / 点击空间支线不得恢复历史 LEFT+RIGHT 默认值 / `C_RANDOM_LEFT/RIGHT/TOP/BOTTOM` 本轮未动 / `RuleClick.coord` 仍纯 `LEGACY_UNIFORM` / `general_battle.py` 不再 import·调用 `random_click` / moon_sea·peacock 仍自带 `random_click`
- ryoutoppa_c_area_1_point_opt_in（`tests/test_ryoutoppa_c_area_1_point_opt_in.py`，25 用例，T7-3.2，纯静态，`ScriptTask.__new__` + mock device）：**调用链**——`_click_toppa_area(0)` → `ClickSampler.sample_point(C_AREA_1.roi_front, DEFAULT_PROFILES['wide_card'])` → `self.device.click(x, y, control_name='area_1')`（patch `sample_point` 断言入参 / 出参）；最终仍走 `self.device.click`、`control_name` 恒 `rule.name` 且**不是** `wide_card`/`point_click`/`habit`；不 patch 时多次点击坐标不复用（>50 distinct / 400）且全在 wide_card Safe ROI `(525,147,201,104)` 内；**尺寸适配**——`C_AREA_1.roi_front == (514,141,223,116)`、`min(w,h)==116`、`point_size_factor(116)==1.0`、`adapt_point_profile` 后 `preferred==(0.58,0.59)`（factor 恰 1.0，不收缩）、EffectiveProfile **逐字段（`dataclasses.fields` 全比）等于 `wide_card` base**（T7-4 后仍成立——factor=1 是恒等映射，这是 T7-4 的核心生产护栏）；`sample_point` 内部把 `strategy="habit"` + effective profile 喂给 `ClickSampler.sample`（patch `sample` 断言）；**wide_card 参数冻结**——preferred `(0.58,0.59)` / core σ `(0.16,0.16)` / medium σ `(0.26,0.24)` / weights `(0.75,0.20,0.05)` / margin `(0.05,0.05)` / `max_attempts 12` / `provisional`；**C_AREA_2..8 未迁移**——`_click_toppa_area(1)` `sample_point` 不被调用、走 `self.click` → `ClickSampler.sample((C_AREA_2.roi_front,))` 无 strategy/profile kwarg（LEGACY）、`control_name='area_2'`；index 1~8 全部不走 Point 路径且 `is not C_AREA_1`；8 个 `C_AREA_*` 都是 `RuleClick`；**opt-in 唯一且受限**——`_click_toppa_area` 源码有 `if rule is self.C_AREA_1:` 守卫 + `else: self.click(rule)`、`script_task.py` 全文 `.sample_point(` 恰 1 处、全仓 `tasks/` 只有 `RyouToppa/script_task.py` 消费 `sample_point`；**未改**——`RuleClick.coord` 源码仍只 `ClickSampler.sample(self.roi_front)` 无 strategy/HABIT/sample_point/profile、`ClickSampler.sample` 默认策略 `LEGACY_UNIFORM` 且不 resolve profile、`sample_point` 是薄 wrapper（含 `adapt_point_profile`+`STRATEGY_HABIT`、无 `if short`/`elif`/`tiny`/`small`/写死 preferred）；`normal_button` 仍 `provisional` 且 `tasks/`·`module/` 生产代码零引用、`I_FIRE` 仍 `RuleImage` 且 `RyouToppa` 未把它接进 `sample_point`/HABIT/`adapt_point_profile`、GeneralBattle Settlement Contract v2 常量（`SETTLEMENT_CLICK_INTERVAL_RANGE==(0.7,1.0)`、`_SETTLEMENT_PRIMARY_PROFILE.provisional`、`_settlement_click` 源码含 `C_RANDOM_RD` 无 `sample_point`）完好
- GeneralBattle 与 RealmRaid timing
- minitouch randomization
- TouchSwipeModel（`tests/test_touch_swipe_model.py` / `test_minitouch_trajectory_executor.py` / `test_control_swipe_trajectory.py`，D018，纯逻辑 + fake builder，不接真实 minitouch）：**model 第一阶段**——起终点精确、首点 dt=0 其余 `>0`、点数合理且 `<=max_points`、无 NaN/inf 且全 int、纵向向上 y 单调不增 / 向下单调不减、负 / 正曲率（x 分别向左 / 右鼓出且精确回终点）、横向偏移始终 `<= max_curve_px+slack`、无锯齿（垂直偏移单峰，死区忽略取整噪声）、minimum-jerk 前慢中快后慢（分段速度中三分之一 `> 两端×1.5`）、距离越长总 dt 越大、极短（14px）滑动仍 `>=2` 点且 dt 合法、dt 恒在 `[min_dt,max_dt]`、非法输入（零长 / `<2px` / inf / nan / 非 (x,y) / bool 坐标 / 非法 `TouchSwipeParams`）抛 `ValueError`、注入固定 rng 两次 `generate` 完全一致、默认 `_DefaultRng` 走真实 `random_int` 循环 10 次结构均合法、`_DefaultRng.randint` 委托公共 `random_int`；**model 第二阶段（时间连续性 + 尾段慢拖）**——`_t_for_s` / `_minimum_jerk_s` 互逆；`dt_smooth_alpha` 是 `(0,1)` 低通；`SeqRng` 交替极值下非尾段相邻 dt 变化 `<=3`（未平滑会 6）；恒定偏置输入下每段偏置夹在 `[-jitter,jitter]`、中段偏置基本恒定不递增（不漂移）；同序列 `SeqRng` 可复现、不同序列 dt 变但端点不变；带噪声时慢→快→慢仍成立；中段 dt 波动 `<` 尾段趋势抬升（噪声不盖过趋势）；尾段（按已走距离占比）MOVE 点 `>=3`、空间步长比中段小、无连续重复坐标、终点精确不过冲不反向（纵向上 / 下）、源码无 `140` / 无 `pre_up`；尾段 `avg_dt` > 中段、尾段 `avg_speed` < 中段、进入尾段无 dt 突跳（相邻跳变 `<=4`）、末段属慢区；`120<260<440` 总时长严格递增 + 宽松上限（200/360/600ms，非真机）；新增 4 参数默认值 + 8 组非法组合抛 `ValueError`；曲率参数 `max_curve_px`/`curve_px_ratio` 断言未动；**model 统计 helper（2026-09-04 对齐修正）**——`_move_segments` 手算样本 `[(0,0,0),(20,0,5),(25,0,20),(35,0,10)]` → `[(5.0,5),(10.0,20)]`、`_segment_speeds` → `[1.0,0.5]`、`p0→p1`(20px) 与 `dt_last`(10) 均排除、段数 = `n-2`（上述「尾段 avg_dt/avg_speed」等断言都基于校正后的段配对）；**tail correction**——默认关、`pct=0` 与关闭逐字一致、`pct=100` 只改末段不改终点（公共前缀首个差异点在 60% 之后）、幅度 `<= max_curve_px+tail_max+slack`；**executor（`_ensure_trajectory`）**——合法轨迹取整 + 首点 dt 清零、`<2` 点 / 非可迭代 / 非三元组 / MOVE 点 dt`<1`（含 `round(0.4)`）/ NaN·inf / bool 字段 抛 `ValueError`、首点 dt 为负也被忽略清零；**executor（`swipe_minitouch_trajectory`）**——命令序列严格 `down·commit`→send→`(move·commit·wait)×N`→send→`up·commit`→send（send 3 次）、每段 dt 原样写入、x 正负变化不被夹直、`_humanized_pressure` 整手势只调一次且所有 down/move 同一个 pressure、`insert_swipe` 与 `random_int` 均不被调用、非法轨迹在 `@retry` 之外抛干净 `ValueError`（builder 无事件、send 未调）、`_swipe_minitouch_trajectory_run` 带 `__wrapped__`（确套 `@retry`）；**Control.swipe_trajectory**——minitouch 分派到 executor 且原样传轨迹、接受 iterator 输入（内部物化）、`adb`/`uiautomator2`/`scrcpy`/`window_message`/`ADB` 抛 `NotImplementedError` 且不调 executor、非可迭代抛 `ValueError`、enable 时恰记一条 `ACTION`/`swipe`/`target`/`elapsed_ms`（无 `x` 键即不记 MOVE）、默认 disable 不写文件、executor 抛错时不写 ACTION、`Control.swipe` 仍走端点 `swipe_minitouch` 路径不受影响、`swipe_trajectory` 不做 distance_check（`<10px` 也发）
- TouchSwipeModel MuMu Level C 测试工具（`tests/test_touch_swipe_mumu_tool.py`，纯逻辑，不连 MuMu / 不构造 `Device`）：`parse_point` 正反例；`make_test_id` 形如 `YYYYMMDD_HHMMSS`；**`trajectory_segments`（executor 时间对齐）**：手算样本 `[(0,0,0),(20,0,5),(25,0,20),(35,0,10)]` → 恰 2 段（`p1→p2` dist 5 / dt 5 / speed 1.0；`p2→p3` dist 10 / dt 20 / speed 0.5）、`p0→p1` 与 `dt_last` 均排除、2·3 点边界（`[]` / 1 段）、段数 = `n-2` 且 `from_index` 无缝覆盖 `1..n-2`；`trajectory_stats` 已知小轨迹的 `point_count`/`total_dt_ms`（所有显式 WAIT 之和，不变）/`straight_distance_px`/`actual_path_length_px`（全路径，不变）/`max_dx_px`/`min·max_y`/`min·max_dt_ms`（= min/max(dt_1..dt_{n-1}), 不变）/`segment_count`/段速度精确值（4 点 → 2 段）/`avg = Σseg_dist/Σseg_dt`/`max = max(段速度)`、`<2` 点抛 `ValueError`、真模型轨迹 minimum-jerk 中段段速度 `>` 两端 + `ForcedCurveRng('left')` 曲率幅度 `≈ max_curve_px`；`build_record` 必备键齐全（含 `executed=False`）、`trajectory` 逐点带 `index` 且与原始 tuple 一致、首点 `dt_ms=0`、`params` 来自 `dataclasses.asdict(model.params)` 的 13 字段真实值；`save_json` 建目录 + UTF-8 往返；`draw_trajectory_png` 生成可被 `cv2.imread` 读回的 **`(900,1400,3)`** PNG 且 `>1KB`、默认 `size=(1400,900)`、left/straight/right 三模式均出图、stats 键不变；PNG 与 JSON 用同一 `record`（同一条 trajectory）；`ForcedCurveRng` 首次 `randint` left→lo / right→hi / straight→0、其余委托公共 `random_int` 且落区间内、非法 mode 抛 `ValueError`、接进 `TouchSwipeModel(rng=...)` 后向左 / 向右鼓出且精确回终点；模块导入不在 `init_device` 之前 import `Device`；**坐标变换**（PNG 比例修正）：`fit_screen_rect` 恒 16:9 且居中留白、`screen_to_panel` 用固定 `[0,1280]×[0,720]` 定义域（与本次轨迹 x/y span 无关）且 X/Y 像素比例相等（1:1）、Y 向下、`trajectory_bbox` 支持 dict/tuple、`zoom_transform` 用 bbox 自适应放大且四角落 panel 内（非屏幕比例）
- diagnostic scrub 与 ZIP
- fatigue：active time 统计、recovery clamp、运行时 L 归一化（降低 L 后不变量与消除死区）、`try_break` 的正常 / stop / deadline / cancel / 异常终止路径、被中断 break 不施加 recovery / cooldown
- fatigue idle 事件率模型：`P_node` 随节点密度下降、相同 `IdleRate` 下整体事件率与节点频率无关、`idle_rate` 落在 `[rate_base, rate_max]`、低疲劳≈`rate_base` / 高疲劳≈`rate_max`、`GlobalFatigue` 越高 `idle_rate` 越高、`Δt` 基于 `task_active_elapsed` 且排除 idle/rest、检查基准推进与任务切换 / restart / 页面切换语义、rest 触发后基准处理、idle 后 `idle_rate` 下降、`L` 经 `TaskFatigue` 影响 `idle_rate`、idle 时长 min=15 / 众数随疲劳上移 / 均值 ≤90 秒 / 硬上限 120 秒不被突破、第一小时理论期望落在目标带、preview 参考场景（`n=170`）与生产公式一致
- fatigue scheduler_idle 自然恢复：<5min 冻结、5min 边界恢复≈0、15/30/60/120min 恢复比例 ≈25%/52%/80%/97%、渐近不低于 0、不产生未来额度（`_global_recovery ≤ RawGlobal`）、重复读取快照不重复恢复、不连续多段不累加、session 在转 active 时结束、新 session 用全新 baseline、不改 active elapsed、不动 TaskFatigue、恢复到 0 后重新 active 能再增长、`SchedulerIdleConfig` 校验
- KekkaiUtilize 收益阈值与选卡：默认阈值等于六星满值（**默认行为零变化的回归护栏**）、阈值边界、三种策略下阈值只对本策略类型生效、调低阈值提前触发、`_card_rank` 跨类型比较用排名而非原始数值、不同策略排名顺序不同、`CARD_TIER_INFO` 档位上限单调递增（回选剪枝的正确性前提）、配置拒绝非正值
- KekkaiUtilize 剩余时间兜底：`timedelta(0)` / 负值 / 非 timedelta / 超上界均走兜底间隔、正常值与边界值保持不变、**任何输入下 `next_run` 都严格晚于当前时刻**（防热循环的核心不变量）、`switch_friend_list` 超时常量为正且签名标注为 `None`
- KekkaiActivation 状态机 characterization（`tests/test_kekkai_activation_state.py`，18 用例，纯 mock，锁现状不锁应然）：`harvest_card` 恰 8 次无参 `appear_then_click`、target 顺序固定、`screenshot` 从不调用、8 步纯线性（源码无 `while`/`for`/`sleep`/`if`/`return`）、返回 `None`、全命中也不提前退出；`check_card_num`(KA 覆写) 空 OCR 时 4 OCR + 3 `swipe_adb(duration=2)` + 3 `sleep(1)` 后 `ocr_count>3` 返回 `None`、`p2=(p1.x, p1.y-410)`、用 stdlib `random.randint`（非 `random_int`）、命中返回 `name='tmpclick'` `RuleClick`、数字 `<min_num` 忽略后继续滑、未知 `card_type` 抛 `ValueError`；`run_activation`/`screening_card`(4×`while 1`)/`check_card_effect` 无 `Timer`/`range` 上限、`check_card_num` 有 `ocr_count>3` 界、`_card_not_found` 总 `raise TaskEnd`；模块无 FrameWait token
- KekkaiUtilize 状态机 characterization（`tests/test_kekkai_utilize_state.py`，23 用例，纯 mock）：`perform_swipe_action` = `random_int(340,600)`/`random_int(500,565)` 各一次 → `swipe_adb((rx,ry),(rx,ry-416),duration=2)` → `click_record_clear` → `sleep(2)`、返回 `None`、**不调用 `self.device.swipe`（Control.swipe）故无 BehaviorTrace**、源码公共 `self.swipe(` 仅注释行、常量 `(340,600)`/`(500,565)`/`416`；`check_card_num`(KU) 关键字判类型（体力/勾玉）→ `(类型, 数值)`、无关键字 `('unknown',0)` 不 push、`value<=0` push_notify + `(类型,0)`、每次都 `screenshot`；循环界锁——`check_utilize_add` `count>=5`、`run_utilize` `enumerate((friend,fallback))` 无 `while`、`_current_select_best`/`_select_lazy_*` `MAX_SWIPES=20`+`range(+1)`+`Timer(120)`+`CONSEC_MISS=3`、`_reselect_best_card` `range(21)`+`Timer(120)`、`switch_friend_list` `while 1`+`Timer(20)`+`raise GamePageUnknownError`、`check_and_get_guild_rewards` `while True`+`Timer(2)` 进度计时器、`receive_guild_assets` `range(1,N+1)`；三处「等详情」+ post-swipe 都是 `time.sleep(2)`、lazy_roll = `random_delay(0.0,1.0)` 概率判定；模块无 FrameWait token、全模块只 1 处 `self.device.swipe_adb(`
- RealmRaid 状态机 characterization（`tests/test_realm_raid_state.py`，41 用例，纯 mock，锁现状不锁应然）：**`fire()`**——`I_RR_PERSON` 首帧消失即 `return True`（1 截图 0 点击）、序幕顺序 `wait_until_appear(I_RR_PERSON) → click_record_clear → screenshot`、`wait_until_appear` 无 kwargs（无超时）、旧页面仍在时按 `I_FIRE(interval=1)` → `partition(interval=2)` 点击、`partition` 取 `order-1`、**进入战斗唯一判据是 `not appear(I_RR_PERSON)`** 且源码无 `page_battle`/`detect_page_in`/`I_EXIT`/`get_current_page`/`Timer(`、AST 证明 `while True` 无 `break`、循环内唯一 `return True`、尾部 `return False` 不可达；**`fire_again()`**——`I_FIRE_AGAIN` 消失即 True、先 `wait_until_appear`、点击顺序 `I_SHOW_AGAIN→I_FRESH_ENSURE→I_FIRE_AGAIN` 全 `interval=2`、尾部 `return False` 不可达；**`find_one()`**——返回 `(target, 1-based 序号)` / 无命中 `(None,None)` / `CONTINUE` 模式**原地涂黑**失败格（同一 ndarray、对应区域全 0、其它区不变）/ 非 CONTINUE 不碰帧 / `find_anyone` 不传 `frame_id`；**`check_ticket`**——`base` 越界 clamp 0、顺序 `wait_until_appear(I_BACK_RED)→screenshot→OCR`、`total==0` 触发 `reward_detect_click(True)`+二次 OCR、无票/低于基准返回 False、`init_tickets` 只锁存一次且按 `number_attack` 截止；**`check_refresh`**——`I_FRESH` 不在立即 False（1 截图 0 点击）、尾部 `return False` 不可达；**GeneralBattle 交接**——`_exit_matcher()` 是 `I_BACK_RED`、quick_exit 按 `appear(I_FALSE)` 返回 EXIT_WIN/EXIT_LOSE 且**不调 `_settlement_click`**、非 quick_exit 委托 `super()`、`PREPARE_CLICK_DELAY_RANGE (2.5,3.5)` vs 基类 `(3.0,3.0)`、`SETTLEMENT_CLICK_INTERVAL_RANGE (0.65,0.95)` vs 基类 `(0.7,1.0)`、`run()` 内 `run_general_battle` 6 次 / `fire_again` 4 次 / `build_quick_exit_config` 4 次；**循环边界**——6 个方法的 `while` 全无 `Timer(`/`range(`、AST 扫全模块 ≥5 处 `wait_until_appear` 全部单参数无 kwargs、主 `while 1` 无 `Timer` 且 ≥5 个 `break`、收尾 `goto_page(page_exploration)→set_next_run→raise TaskEnd` 且全模块 2 处 `goto_page(page_exploration)`；**死代码 / 结构**——`medal_fire`/`is_ticket` 全仓零调用方、`medal_grid is None`、`medal_fire` AST 无任何 `return`、`AttackNumber` 全文仅 1 次（import）、模块无 `swipe_adb`/`click_adb`/`adb_shell`/`*_minitouch`/`device.swipe(` 直连、无 FrameWait token、`false_image` 复用 RyouToppa 资产且 `false_roi` 恰 9 格
- Exploration 状态机 characterization（`tests/test_exploration_state.py`，33 用例，纯 mock，锁现状不锁应然）：**`fire()`**——正向战斗页（`page_battle_prepare`/`page_battle`）即 `return True`（1 截图 0 点击）、`page_exp_exit` → `need_exit=False`+`return True`、点击每次命中则 `max_tries` 递减第 4 次后 `return False`（`appear_then_click` 恰 4 次）、点击从不命中靠 `Timer(10).reached()` 收敛 `return False`、源码含 `max_tries = 4`/`Timer(10).start()`/`while max_tries > 0 and not timeout_timer.reached():`/`cur_page in (pages.page_battle_prepare, pages.page_battle)`/`return False` 且**不含** `not self.appear(`；**`get_fire_button`/`search_up_fight`**——`appear(I_BOSS_BATTLE_BUTTON)` → `fire_monster_type='boss'`+返回、不调 `search_up_fight`；不命中透传 `search_up_fight()`；`search_up_fight` 源码含 `I_NORMAL_BATTLE_BUTTON.match_all(`/`.roi_front = roi_front`/`fire_monster_type = 'normal'`/`distances.sort(`；**`exec_exp_page` dispatch**——`while True`+轮首 `screenshot()`+`get_current_page()`+`exp_page_handle_dict.get(...)`+`self.pre_page = current_page`、**无 `range(`/`Timer(`**、`None` → `time.sleep(0.5)`、未登记 Page → `goto_page(pages.page_exploration)`、`except InviteFailedException` → `break`、三个战斗页共用 `run_on_battle`、`page_reward` 是 `self.click(pages.random_click(), interval=0.8)` 就地 lambda；**GeneralBattle 交接**——`run_on_battle` 传 `exit_matcher=pages.page_exp_main`+随后 `_match_end.refresh()`、`_exit_matcher` 在 `BE.__dict__` 且源码含三个 `I_E_*`+`any_of`、`_handle_result`/`_handle_reward`/`_settlement_click`/`PREPARE_CLICK_DELAY_RANGE`/`SETTLEMENT_CLICK_INTERVAL_RANGE` **都不在** `BE`/`E` `__dict__`（未覆写）、`GeneralBattle in E.__mro__`、全模块无 `quick_exit`/`build_quick_exit_config`；**`arrive_end`**——`click_record.count(...) >= 6` → `click_record_clear()`+`return True`（不调 `_match_end.stable`）、计数不足则 `_match_end.stable(..., refresh_after_stable=True)`、`E.arrive_end` 覆写含 `EXPLORATION_28`/`appear(self.I_SWIPE_END)`/`return super().arrive_end()`；**`check_exit`**——`current_count >= minions_cnt`/`now-start_time >= limit_time`/`MEMBER 且 now-wait_start_time >= wait_time_v` 各 `return True`、正常 `return False` 且调 `activate_realm_raid` 一次（源码含 `set_next_run(task='RealmRaid'`/`'MemoryScrolls'`/`raise TaskEnd`）；**循环边界**——`open_expect_level` 含 `while True:`/`swipeCount >= 25`/`raise GameStuckError`/`time.sleep(1)`、`fill_shikigami` 含 `while True:`/`time.sleep(0.5)`/`>= 6`/`raise GameStuckError` 且**无 `Timer(`**、`fire` 是唯一同时含 `Timer(10).start()` 与 `max_tries = 4` 的循环、AST 扫 `BaseExploration` 模块 `wait_until_appear` **恰 1 处且带 `wait_time` kwarg**；**结构事实**——两模块源码无 `swipe_adb`/`click_adb`/`adb_shell`/`*_minitouch`/`self.device.click(`/`self.device.swipe(`、无任何 FrameWait token、含 `RuleAnimate(self.I_SWIPE_END)`+`self._match_end.stable(`、`E.run` 内 `pre_process`→`exec_exp_page`→`post_process` 顺序、`BE.post_process` 含 `raise TaskEnd`

修改疲劳核心（`module/fatigue.py`、`tasks/base_task.py` 疲劳部分、`FatigueConfig`）后至少重新运行 `tests/test_fatigue.py` 与完整回归。

整合收口时还完成：

- 36 个 staged Python 文件通过 `py_compile`。
- 23 个关键模块通过 import smoke test。
- 6 个 JSON 和 1 个 XML 解析通过。
- staged 资源引用和 PNG 解码检查通过。
- merge commit 双父关系与两个父提交的祖先关系验证通过。
- `origin/master` 已核对为 merge commit。

修改上述模块后，至少重新运行对应测试。未经用户授权，不进入设备或游戏内测试。

## 8. 已知非阻断问题

- `tasks/Component/CostumeShikigami/assets.py` 存在 20 处 upstream 生成注释行尾空格，会触发 `git diff --check` 提示。当前决定是不为此单独修改生成文件。
- Image frame 注册发生在部分方向修正前。
- 同一 `config_name` 的多个截图生产者可能竞争 frame。
- Image/OCR RPC 运行中断线后没有自动恢复。
- low spec small OCR 可能需要首次下载，离线环境可能失败。
- 诊断导出 endpoint 尚未确认统一有效鉴权。
- AntiBan 的跨日任务计时和进程重启清零行为尚未持久化。
- `Script._publish_fatigue_state` 是独立的 2 秒轮询线程，且禁用疲劳时仍持续推送、无退出条件，与“前端复用现有状态刷新链路、不单独增加高频轮询”的意图有出入。记录为后续 P2 架构审查项，本轮不改。
- GlobalFatigue 进程内累计、进程重启清零，无持久化（与既定设计一致，不为此新增持久化系统）。

### 8.1 输入层随机化的归因修正

以下四条经源码核实，用于纠正“防风控加固”这一归因中被高估的部分。它们不是缺陷，是**文档表述与实际效果不符**，后续写文档和汇报时必须按此表述。

- **`np.random` → `SystemRandom` 不改变任何可观测分布。** 两者在同一 ROI 上产生同一个均匀分布，外部观测到的坐标统计量（均值、方差、直方图）完全一致。该改动的真实价值是消除 `random.seed()` 全局污染、提升可测试性与确定性，属于**代码质量改进，不是反检测改进**。不要再把它列为“降低特征相似度”的成果。
- **minitouch pressure 随机化在当前 MuMu 环境是空操作。** 握手返回 `^ 10 540 960 0`，`max_pressure <= 0` 回退为 1，于是 `random_int(max(1, 1 // 2), 1)` 恒等于 1。代码逻辑正确，但该环境下不产生任何变化。只有在握手返回较大 `max_pressure` 的设备上才会实际生效。
- **点击坐标仍是全 ROI 均匀分布，未做中心偏置。** `module/atom/click.py` 与 `module/atom/image.py` 的 `coord()` 使用 `random_point_in_roi`（矩形内均匀）；只有 `RuleSwipe` 用了 `random_center_point_in_roi`。点击是采样量最大的事件类型，滑动少得多。§4.1 记录的“不采用 upstream 中心偏置点击”是有意决定，但需知晓其代价：大样本事件保持着与真人差异最大的分布。
- **`insert_swipe` 的 drag 尾部有两次固定 `wait(140)`**（`module/device/method/minitouch.py` 末段），与“每个 MOVE 独立采样 6~15ms”的原则不一致，固定值把该路径上的随机化打了折扣。
- **minitouch 协议层已确认支持「自定义多点触摸轨迹」**（2026-09-03 专项审查，`docs/Minitouch自定义轨迹能力审查.md`）：`Command` / `CommandBuilder` 是通用命令构造器——`m {contact} {x} {y} {pressure}` 接受任意 x/y（无「x 必须不变」约束）、`.wait(ms)` 可逐段独立、`down → (move.commit.wait(dt))* → wait(short) → up` 今天就能表达。当前 `swipe_minitouch` / `drag_minitouch` / `_press_and_drag_minitouch` **已经**在逐点发 MOVE、每 MOVE 独立 `random_int(6,15)`、路径是贝塞尔曲线（非直线、非仅端点）；缺的只是**接受调用方点列表 / 逐段 dt 的薄 executor + 公开 API**。**Plan B 第一阶段已实现**（2026-09-04，§4.42 / `docs/DECISIONS.md` **D018**）：`module/device/touch_swipe_model.TouchSwipeModel`（纯 minimum-jerk + 有界曲率轨迹生成，不 import device）→ `Minitouch.swipe_minitouch_trajectory` → `Control.swipe_trajectory`（显式 opt-in，非 minitouch 后端 `NotImplementedError`）。协议层 / `CommandBuilder` / `Control.swipe` / `BaseTask.swipe` / `RuleSwipe` / `insert_swipe` **均未改**；未接任何任务、未真机（Level C 待验收）。现成先例：`tasks/Chess/runtime/press_and_drag.py` 的 `_press_and_drag_minitouch`。`smooth_path`（minitouch.py，当前无调用方）是现成的「给点列表加 ±横向偏移」工具。

### 8.2 随机源统一的实际边界

“随机源已统一为 SystemRandom”只对**本轮迁移的低层输入与 ROI 公共路径**成立，不能表述为全仓结论。未迁移的部分：

- `module/atom/swipe.py` 的 Bezier 轨迹形状（`RuleSwipe.trace()`）曾用普通 `random`，2026-09-01 已作为死代码整体删除（见 §4.15 / DECISIONS D006）；`RuleSwipe` 现只剩 `coord()`，端点已用公共 `random_center_point_in_roi`。
- `module/device/method/minitouch.py` 的 `insert_swipe` 控制点与路径扰动仍用 `np.random`（pressure、dwell、MOVE interval 已迁移）。
- `tasks/RyouToppa/script_task.py` 列表滑动坐标（`flush_area_cache` 的起点 / 终点 / distance）用普通 `random.randint`（按 §4.10 决定保留）。`flush_area_cache` 的 swipe `duration` 由 `random_delay(0.342, 0.362)` / `(0.349, 0.355)` 采样并原样传给 `self.device.swipe(...)`——该 `duration` 只在 adb / uiautomator2 后端被消费，默认 minitouch 后端忽略它（见 §4.14）。
- `module/base/protect.py` 存在另一套用普通 `random` 的同名 `random_delay`，与公共模块重名易误用。
- **点击空间坐标**（2026-09-01 §4.20 审查补记）：`tasks/SixRealms/common.py` 购买技能处用普通 `random.randint` 在 `front_center()` 上做左移 + 纵向抖动，是唯一绕开公共 helper 的任务私有空间随机；`tasks/GameUi/default_pages.py` 的 `random_click()` 用普通 `random.choice` 从 4 个安全区 asset 里选一个（落点仍是所选 `RuleClick.coord()` 的公共均匀采样）；`module/device/method/scrcpy/scrcpy.py` `click_scrcpy` 与 `module/device/method/nemu_ipc.py` `click_nemu_ipc` 对释放点做 `± random.randint(-2, 2)` 抖动（普通 / `np.random`）——但两者都**不在 `Control.click_methods` 实际可达的后端**（scrcpy-click 静默回退 `click_adb`，nemu 不在 `Control` MRO），默认 minitouch 点击无此抖动。

### 8.3 自动化特征面清单

本节记录“这套代码有哪些可被外部确认的特征”，按**确认难度从低到高**排列。目的是让后续维护者知道各层的实际权重，不要把工程投入错配到权重最低的一层。本节只做描述性记录，不作为规避方案的设计依据。

**第 1 层 · 设备驻留物（枚举即确认，权重最高）**

- `/data/local/tmp/minitouch`（`module/config/config_manual.py` `MINITOUCH_FILEPATH_REMOTE`）
- `/data/local/tmp/DroidCast_raw.apk`（同文件 `DROIDCAST_FILEPATH_REMOTE`）
- `/data/local/tmp/hierarchy.xml`（`module/device/method/adb.py` 的 `dump_hierarchy_adb`）
- `localabstract:minitouch` 抽象域套接字（`minitouch.py` 的 `adb_forward`）
- scrcpy server jar 与 uiautomator2 ATX agent（启用对应后端时推送到设备）
- ADB daemon 与 USB 调试处于开启状态

**第 2 层 · 模拟器本体**：MuMu 的 build 属性、CPU 型号、GPU 渲染器字符串、缺失的基带与传感器底噪。完全在本仓库之外，代码层面无法处理。

**第 3 层 · 轮询与反应时序**：截图固定 `Timer(0.1)`（`module/device/screenshot.py`）；脚本靠视觉状态驱动，对状态变化的反应延迟下界由截图间隔决定，方差很小。这是架构的自然产物，不是参数没调好。

**第 4 层 · 输入层**：本轮改造所在层，权重最低。已引入的分布是平稳、有界、无跨会话漂移的（dwell 硬边界精确在 45/130ms）。

**第 5 层 · 行为聚合**：零误触、零探索性操作、任务顺序与启动时段固定、资源永远精确用尽。`FatigueManager` 是唯一针对该层的机制，但默认关闭、只接入 RyouToppa、未经真机采样验证。

以上均为记录事项，不是当前阻断问题。除非新任务明确涉及，不能顺手扩展修改范围。

## 9. 当前待办

- **文档体系已建立（2026-09-01）**：新增 `docs/ROADMAP.md` / `ARCHITECTURE.md` / `DECISIONS.md` / `TESTING.md` + 仓库根 `CLAUDE.md` / `AGENTS.md`。后续详细任务规划见 `docs/ROADMAP.md`（不再在本文件维护任务清单）；每轮开发的文档同步纪律见 §10.1。
- **当前限制（临时）**：约一周内无法进行 MuMu / 游戏内真机测试，只推进纯静态可验证、且不改变现有真实生产行为的工作。真机窗口打开后再落地 `docs/ROADMAP.md`「需要真机验证的任务」区。
- 持续维护本文档和 `DEVELOP_LOG.md`。
- 疲劳系统 P0-A（运行时 L 归一化）、P0-B（idle/rest 终止语义）已收口，仅补测试、未改这两块之外的生产代码。
- P0-D 前端数据链路：后端 `load_factor_preview` → `ui_snapshot` / `_default_fatigue_state` → `state_queue` / WS 广播这一段已就绪并有测试。缺口在 OASX Flutter 前端（独立仓库，不在本工作区）：`fatigue_load_factor_preview` 的解析、`fatigue_header_panel` 的“!”Tooltip 文案、Slider 当前档高亮、是否存在硬编码概率、前端多实例隔离、Flutter 3.35 `Tooltip.rich` → `Tooltip` 兼容与 widget test 均无法在此工作区核实。
- `Script._publish_fatigue_state` 独立 2 秒轮询循环列为 P2 架构审查项。
- **一致性修复已完成（2026-08-30，见 §4.10）**：`protect.py` 同名反语义、RyouToppa 本地随机工具、Chess 拖拽随机源三处已收敛。`module/atom/swipe.py` 的 Bezier 轨迹已随 `RuleSwipe.trace()` 死代码删除（2026-09-01，§4.15）。仍待处理：`minitouch.insert_swipe` 控制点的 `np.random`，以及 RyouToppa 滑动坐标的普通 `random.randint`（见 §8.2，均按既有决定保留）。
- **`Device.drag()` 当前零业务调用方**：`module/device/method/minitouch.py` 的 `drag_minitouch` 及其 `control.py` 入口在 `tasks/` 与 `module/` 内无调用者，属死路径。真正生效的拖拽是 `tasks/Chess/runtime/press_and_drag.py`。清理死路径前需确认没有外部脚本依赖。
- **KekkaiUtilize 单向分区搜索改造已实施（§4.41 / `docs/DECISIONS.md` D017，2026-09-03）**——§4.40 审查提出的三大差异（跨区优先默认反了 / 同屏非星级序 / 默认阈值使行为=扫全+回选）已由「PASS 序列（跨→同→跨→同 或 同→跨→同）+ 第一阶段 6★HIGH / 第二阶段 5-6★ 降一档 + 命中即寄养 + 最后一 PASS 兼兜底」解决。global-best / `_reselect_best_card` / 蛇形 / `miss-as-bottom` 已从标准路径移除；怠惰模式不变。回归 759→783。**剩余全是 Level C 真机待验收**（`docs/DECISIONS.md` D017 末尾 + §4.41 末尾）：`I_U_EMPTY_CARD` 是否 100% = 到底、切区是否稳定回顶、`SWIPE_DISTANCE=416` 覆盖性、card-column ROI 是否需扩大、ADB→minitouch 滚动量、`FINAL_USE_LAST` 依赖的「最后候选保持选中」、`SEARCH_MAX_SWIPES=20` 是否够、列表/详情卡种偶发不一致。**下一轮独立 Level C 项**：结界卡 ROI 扩展、`perform_swipe_action` ADB→minitouch。
- KekkaiUtilize 仍未处理的记录项：`check_utilize_add` 中「5 轮未蹭上」返回 `True` 与 `_record_utilize_failure` 路径返回 `False` 的语义不一致（不影响正确性；改会让 `run()` 提前 return 跳过后续维护，需产品决定，cleanup 批次 1 deferred）。（`last_best_index = 99` 死属性已于 2026-09-02 cleanup 批次 1 删除，见 §4.36。）
- Kekkai 状态机静态收口（§4.33）记录项，完整表见 `docs/Kekkai状态机静态收口.md` §9。**cleanup 批次 1（§4.36）已删**：`KekkaiActivation` 死 import `parse_rule`。**仍未修**：`check_card_num` 子类覆写改返回类型（`RuleClick` vs `(str,int)`，latent，KA 当前不进 `run_utilize` 路径故无运行时冲突）；`harvest_card` 8 连点无截图 / 无验证 / 无 reward 闭环（Level C，T4-4）；`KekkaiActivation.check_card_num` swipe 用 stdlib `random.randint`（**KEPT**——D007「已存在未迁移用法保留」+ `RyouToppa.flush_area_cache` 同款先例，留未来专门随机源 pass）；`run_activation` / `screening_card` 的 4 个 `while 1` 无总超时（Level C）；`ocr_time()` OCR 失败 `return None` → `set_next_run(None + now)` → `TypeError`（crash 属实，正确恢复语义不唯一，deferred）；`run_utilize` U3 `goto_page` 失败仅 `logger.info` 不 return（deferred）。
- RealmRaid 状态机静态收口（§4.34）记录项，完整表见 `docs/RealmRaid状态机静态收口.md` §14。**cleanup 批次 1（§4.36）已删**：`medal_fire()` / `is_ticket()` / `medal_grid` 死代码（R-R7）、`AttackNumber` + `RealmRaid` 配置类死 import（R-R8）、随之变死的 `import time`。**§4.52 已收口**：`fire()` R-R1（正向 `is_in_battle()` 确认 + `RR_FIRE_MAX_TRIES` + `Timer(RR_FIRE_TIMEOUT)` + 三态 + 可达 `return False`）、R-R2（`run()` 两处 `if not self.fire(index): continue` 死分支现生效）。**§4.56 已收口**：`fire_again()` → `_fire_again()` 三态 bounded（R-R3 的不可达 `return False` 现可达）；`find_one` / `_grid_targets` 改在 `image.copy()` 上涂黑失败格、不再原地污染 `self.device.image`（R-R9）；`fire` / `_fire_again` 的 `wait_until_appear` 均带 `wait_time`（R-R5 部分）。**仍未修（Level C 耦合）**：`check_refresh` 尾部不可达 `return False`（R-R6）；`reward_detect_click` / `check_refresh` / `ensure_lock` 等自有 `while 1` 无总超时（R-R4）；`false_image` 复用 RyouToppa 的 `loser_sign_1.png`（R-R10）；目标点击仍用静态九宫格 `C_PARTITION_*` ROI（`_grid_targets` 把 `find_everyone` 匹配中心映射回 `roi_front` 后仍点 `C_PARTITION`，非识别到的勋章位置本身，R-R12）。
- Exploration 状态机静态收口（§4.37）是迁移前历史基线，完整表见 `docs/Exploration状态机静态收口.md` §14。**§4.58 / D021 已收口 E-5 与 Boss 后业务链**：`run_on_battle` 消费 `run_general_battle` bool，Boss win 后 positive map-ready → treasure bypass → bounded direct exit → positive entrance → solo Fatigue。其余记录仍在：`search_up_fight` 动态改写 `roi_front`（E-1）、`get_fire_button` 只在 `fire` 前定位一次（E-2）、`exec_exp_page` None 无连续上限（E-3）、`fire(False)` recovery 滑地图（E-4）、`page_reward` lambda（E-6）。Exploration `fire()` 的正向 battle page + `max_tries=4` + `Timer(10)` 本轮未改。
- `appear_then_click` / `confirm_delay` / reaction timing 专项审查（§4.38，2026-09-02）记录项，完整见 `docs/Action点击前反应时序静态审查.md`。**本轮零生产改动**。结论：`confirm_delay` 已是正确的 Point Action reaction-timing 机制（fresh screenshot + 二次 `appear` + 重定位），但**零生产 opt-in**、不应「统一」、不新增 `reaction_delay`（D001 扩写）。timing 分层（micro `confirm_delay` / throttle `interval` / state wait `wait_until_*`·`frame_wait` / macro fatigue）写进 ARCHITECTURE §2。**下一步只固化文档，不加 opt-in**；首个 opt-in 待 Level C，随 RealmRaid `fire()` bounded 改造一起。
- **三案例架构归纳已完成（§4.35，2026-09-02）→ 下一阶段唯一推荐 = Level A correctness / dead-code cleanup**：`docs/状态验证与重试模式归纳.md` §16 有一份排好序的清理队列（correctness > misleading contract > dead code > consistency），全部零真机、低风险、可配 characterization 回归护栏。最高优先几项：RealmRaid `fire()` 不可达 `return False` + `run()` 死分支（与 R-R1 判定改造绑定，Level C）、`KekkaiActivation.ocr_time` 的 `None + datetime` 会崩、`KekkaiActivation.check_card_num` 用 stdlib `random.randint`、`KekkaiUtilize.run` lazy_roll 误用 `random_delay(0.0,1.0)`、死代码 `medal_fire`/`is_ticket`/`medal_grid`/`AttackNumber`/`parse_rule`/`last_best_index`。**本轮只归纳未修**——architecture synthesis 与 correctness cleanup 不混在一个 diff，cleanup 留下一轮独立做。
- 若后续明确要求，可单独评估 Image/OCR RPC 恢复、small 模型离线回退、诊断接口鉴权和 AntiBan 持久化。
- 当前没有必须立即修复的 merge 阻断项。

## 10. AI 修改规则

1. 新任务开始前按 §0 的阅读顺序读文档。
2. 只分析和修改当前任务涉及的源码；改代码前用 grep / 读文件以当前源码为准。
3. 除非发现确定性缺陷，不重新推翻 `docs/DECISIONS.md` 已确认的设计决策。
4. 不进行无关重构、无关格式化；不修改用户未授权模块。
5. 不自动 commit / push / merge --continue，除非用户明确要求。
6. 新增注释和项目文档使用中文；遵循原项目代码风格。
7. 当前事实与文档冲突时，以源码和最新 Git 状态为准，并在同一轮更新文档。
8. 默认不启动 MuMu / 设备 / 游戏 / OCR 服务；属真机级（Level C，见 `docs/TESTING.md` §2）的改动本轮不做，记入 `docs/ROADMAP.md`。

### 10.1 文档同步（强制收尾）

9. **每次开发或正式设计任务结束前，都必须逐项检查这 6 份文档。是否更新某份文档，以「本轮是否改变了该文档负责的项目事实」为判断标准，而不是以「是否修改了代码」为唯一标准。只更新实际受影响的文档**（不是每次机械改 6 个文件）。各文档「负责的项目事实」与更新触发见 §0 的表。
10. 纯设计 / 项目管理工作即使**没有源码变化**也可能改变项目事实，此时仍要更新对应文档，例如：正式确定新架构方案（→ ARCHITECTURE）、新增或废弃长期设计决策（→ DECISIONS）、改 ROADMAP 的任务 / 优先级 / 依赖（→ ROADMAP）、改测试规范或真机验证要求（→ TESTING）、改 AI 开发规则（→ 本节 + `CLAUDE.md` / `AGENTS.md`，并追加 DEVELOP_LOG）。
11. **本轮没有改变任何一份文档负责的项目事实**（纯问答、纯读代码走查、没有落地任何结论）→ 6 份都不写。
12. `DEVELOP_LOG.md`：本轮形成真实项目变更（源码 / 测试 / 配置 / 架构调整 / 正式项目规则变化 / 长期设计决策落地）时**必追加**一条，只追加、不重写历史（修正事实错误除外）。
13. 开发报告结尾固定包含「## 文档同步」段，逐个文件写「已更新 / 无需更新（原因）」。
14. 维护纪律：`AI_CONTEXT` 保持当前快照（过期内容更新或删除，不无限追加）；`DEVELOP_LOG` 只追加；`ROADMAP` 完成的任务移到已完成区、不并存冲突的「下一步」；`ARCHITECTURE` 只描述当前真实架构（历史原因放 `DECISIONS` / `DEVELOP_LOG`）；`DECISIONS` 失效用 `Superseded` 不抹除；`TESTING` 只存长期规则，一次性测试数字写 `AI_CONTEXT`。
