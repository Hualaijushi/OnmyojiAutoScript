# 设计决策记录（ADR）

> 保存已经审查并明确确定的**长期设计决策**，防止后续 AI 因不了解背景又把正确设计改回去。
> 只记录长期有效的设计原则，不记录普通实现细节和会频繁变化的参数。
> 失效的决策标记 `Superseded` 并指向新决策，**不直接删除**。
> 更新触发：产生新的长期设计决定，或旧决定被推翻。普通 Bug 修复不动本文档。
> 临时状态（如「本周无法真机」）不写这里，写 `docs/AI_CONTEXT.md` / `docs/ROADMAP.md`。

核对时间：2026-09-01。

---

## D001 `appear_then_click(confirm_delay=)` 是 Point Action 的 reaction timing 机制，默认不启用、逐点 opt-in

状态：Accepted
日期：2026-08-29（整合期确定），2026-09-01 复核，2026-09-02 专项审查后扩写（`docs/Action点击前反应时序静态审查.md`）

背景：`BaseTask.appear_then_click` 支持 `confirm_delay=(lo, hi)`：识别成功后随机等待、重新截图、二次确认、重新生成坐标再点击。这是唯一「等待后重新截图 + 重新生成坐标」的防旧坐标路径。2026-09-02 全仓专项审查确认：`confirm_delay` 路径实现正确——首次 `appear` → `sleep(random_delay(lo,hi))` → `self.screenshot()`（fresh）→ 二次 `appear`（目标消失则 `return False` 不点）→ 在新帧 `roi_front` 上 `target.coord()`（`ClickSampler` 采样在 fresh + relocate 之后）→ 点击。全仓 486 处 `appear_then_click` 调用，**至今零处传 `confirm_delay`**。

决定：
- **`confirm_delay` 正式承担「可识别 Point Target 单次点击的 reaction timing」职责**：识别后停顿 + 二次确认 + 重定位。**不新增** `reaction_delay` / 任何同义 API（避免「两个名字做同一件事」；`reaction_delay` / `CLICK_REACTION_DELAY` 已有前科被删，见 D008）。
- 默认 `confirm_delay=None`，完全保持旧行为（命中即点当帧坐标）。需要 reaction timing 的调用点**显式传入** `confirm_delay`，**参数由调用方给**，不设项目级默认区间。
- 不给 `RealmRaid.fire` / `GeneralBattle` / `RyouToppa` FIRE 等自动套用。**GeneralBattle 永不叠加**——它有自己的 `PREPARE_CLICK_DELAY_RANGE` / `SETTLEMENT_CLICK_INTERVAL_RANGE` 时序契约（v2）。
- **`confirm_delay` 是 micro timing（单个 Action 内），与 macro timing（`FatigueManager` idle/rest，只在 task-cycle 安全节点）分属两层，不得在同一个 Action 内叠加**。`FatigueManager.try_break` 不进入 Action transaction（当前由「只在调用方显式 `safe=True` 的安全节点触发」保证）。
- **`confirm_delay` ≠ semantic wait ≠ retry throttle**：等某标识出现/消失用 `wait_until_appear(wait_time=)` / `wait_until_disappear` / `frame_wait`；重试间隔用 `interval`（`Timer` 门控）。三者 owner 不同，不能互相替代。
- 不适合 `confirm_delay` 的 Action（永不套用）：Static Region（`C_AREA_*` / 九宫格 `C_PARTITION_*`）、Settlement Region（`C_RANDOM_RD`）、Dynamic Search Result（`find_anyone` / `search_up_fight` 的 `match_all` 结果——delay 后需重新 search 而非重新 `appear` 单 target）、短生命周期 Transitional Button、Repeated Poll Click、Navigation / 现有 FSM handler、Swipe / Drag。

原因：全局启用会给采样量最大的点击热路径普遍增加一次截图 + 等待，改变所有任务时序；旧坐标风险已被外层 `while 1: screenshot` 循环稀释。二次确认应按调用点风险单独评估。能力上线约一周（commit `880cd21f`）零生产 opt-in，说明没有「必须全局」的实际压力。四类 timing（reaction / macro fatigue / semantic wait / retry throttle）职责不同，硬合并成一套「点击前等待」会在同一 Action 上重复叠加延迟。

禁止 / 注意事项：不要把默认值改成非 `None`；不要在 `Control` / `Device` 层加全局点击前等待；不新增 `reaction_delay` 类 API；不在 GeneralBattle handler / poll 循环 / Static Region 点击上加 `confirm_delay`；不把 `FatigueManager.try_break` 塞进 `appear_then_click` 或循环体内部。首个真实 opt-in 待 Level C（大概率随 RealmRaid `fire()` 的 bounded 改造一起，参数用 manual click / BehaviorTrace 数据标定）。

**补记（2026-09-08，第一批生产 opt-in 落地）**：`docs/常用业务点击链与Reaction审查.md` 的 Batch A #1–#23 正式实施——**27 个调用点 / 5 个任务**（RealmRaid / Orochi / EvoZone / RyouToppa / Exploration）从「识别到立即点」改成经 `appear_then_click(..., confirm_delay=REACTION_*)`。本 ADR 的所有决定条目**不变**（primitive 未改、默认 `None`、逐点显式、参数不设项目级自动默认、不给 `*_FIRE` / GeneralBattle / Static Region / poll 循环加、不与 fatigue 叠加）。落地细节：

- **语义 profile 收敛到 `module/reaction_profile.py`**（新公共模块，与 `click_profile.py` 同层）：只含具名 `(min,max)` 秒区间常量，无函数 / 无 `sleep` / 无 `random_delay` / 不 import task·device·config；由业务 consumer 在调用点**显式**传 `confirm_delay=`；**不在 asset / `RuleImage` 层设默认**（reaction 归业务 consumer）。这不是「新增 `reaction_delay` API」——没有函数、不自动应用、不改 `appear_then_click` 默认；只是把「本来要在 RealmRaid / Orochi / … 各写一遍的 tuple」提到一处具名。当前 6 组值 —— `FAST=(0.18,0.35)` / `NORMAL=(0.45,0.85)` / `NORMAL_HIGH=(0.60,1.00)` / `CONFIRM=(0.55,1.20)` / `NAVIGATION=(0.55,1.10)` / `DELIBERATE=(0.90,1.60)` —— **全部 PROVISIONAL / engineering baseline**（来自旧 C++ 延迟分析的业务抽象，非 Level C 人工标定），`REACTION_PROFILES_PROVISIONAL = True`。它们是「当前工程默认」，**不是本 ADR 固化的长期契约数值**；Level C 后可整组或按任务微调，改动连带更新本补记 + §4.51。
- **按 profile 分配（27）**：FAST 14（锁定 / 解锁 toggle、低频管理按钮）/ NORMAL 8（组队、刷新动作本体、章节确认）/ CONFIRM 2（刷新确认弹窗、退出确认）/ NAVIGATION 2（取消退出、返回）/ DELIBERATE 1（EvoZone 麒麟 / 材料类型选择）/ **NORMAL_HIGH 0**（本轮无高频稳定 Point Action，允许 0 consumer）。
- **`GeneralBattle.check_lock(enable, lock_image, unlock_image, confirm_delay=None)`** 加可选参数并透传给两分支的 `appear_then_click`；**默认 `None` = 原行为**，非 batch 调用方（EternitySea / FallenSun / GoryouRealm / OtherWorldTwilight / Sougenbi）不传、逐字不变。这是本 ADR「参数由调用方给」的直接体现——`check_lock` 是业务 consumer 方法（非 asset 层），Orochi / EvoZone 在各自调用点传 `REACTION_FAST`。
- **排除项（本轮 0 新 reaction）与本 ADR 一致**：`*_FIRE` 系列（RealmRaid `I_FIRE` / `fire_again`、Orochi `I_OROCHI_FIRE` / `I_OROCHI_WILD_FIRE`、EvoZone `I_EVOZONE_FIRE`）属「成功判据仅『旧标识消失』、缺正向战斗页确认」，先做 R-R1（正向 `page_battle_prepare/page_battle` 确认 + `max_tries` + `Timer`）再接 reaction；RyouToppa `I_FIRE` 已手搓等价 `random_delay(0.2,0.6)` + fresh frame + 二次 appear（**不叠**）；`C_AREA_1~8` / `C_PARTITION_n`（静态 / Region + T7 采样 + 区域 pacing）；GeneralBattle `I_PREPARE_HIGHLIGHT`（`prepare_click_timer`）/ Settlement Micro-Burst v1.2（自有跨 burst 节流 + fresh semantic gate，D025）/ 瞬态战斗按钮 / 动态 / OCR / polling。上一轮 Batch A #24/#25/#26 本轮不实施。
- **测试**：`tests/test_reaction_timing_batch1.py`（34，源码扫描 + `check_lock` mock 行为 + 排除项断言 + profile 常量）。`appear_then_click` primitive 未改，`tests/test_base_task_confirm_click.py`（5）继续锁其行为。回归 `1092 → 1126`。**非新 ADR**——本 ADR 预留的「首个真实 opt-in」落地。

**补记（2026-09-08，FIRE 分节 —— `I_FIRE` 的 reaction + 状态机收口）**：`docs/常用业务点击链与Reaction审查.md` 里 `*_FIRE` 明确排除、留待 R-R1。本轮把 **RyouToppa + RealmRaid 的 `I_FIRE`** 做成标准模板（Orochi / EvoZone 的 `I_*_FIRE` 第二批已迁，见下方「FIRE 分节 增补」）。本 ADR 的所有决定条目**不变**（primitive 未改、逐点显式、不与 fatigue 叠、不给 Settlement / `I_PREPARE_HIGHLIGHT` / poll / Static Region 加）。

- **`I_FIRE` 用专属 `REACTION_FIRE = (0.4, 0.8)`**（`module/reaction_profile.py`，纳入 `REACTION_PROFILES` dict）。语义 = 「已识别到稳定 `I_FIRE` 后、真正执行 FIRE click 前的人为 reaction」。**PROVISIONAL / engineering baseline，非 Level C 标定**；§4.51 的 6 组数值不动。为什么不用 `REACTION_FAST` / `confirm_delay`：`I_FIRE` 的 reconfirm 不是 `appear_then_click(confirm_delay=)` 的「二次 `appear` 同一 target」——它要在 reaction 后**同时**判「是否已进入战斗（`is_in_battle`）」与「`I_FIRE` 是否还在」，属业务状态机自己的 fresh-confirm，`confirm_delay` primitive 表达不了；且 RyouToppa 早已手写等价链。因此 FIRE reaction 是「业务 consumer 在 FSM 里显式 `sleep(random_delay(*REACTION_FIRE))`」，不经 `appear_then_click`。
- **长期契约（数值不固化，行为固化）**：`I_FIRE` 点击必须满足 —— ① 每次真实 attempt **独立采样** reaction（禁止进 `fire()` 只采样一次给所有 retry 共用）；② reaction 后 **fresh screenshot + 二次确认**（`I_FIRE` 消失则不点旧坐标）；③ 成功判据是**正向战斗状态**（`is_in_battle()` / `page_battle_prepare` / `page_battle`）；**旧页面标识消失（`I_RR_PERSON` / 目标列表）既 ≠ 成功、也 ≠ immediate failure / retry** —— 只作辅助信号，过渡 / 加载 blank 帧必须在有界 timer 内继续等正向状态（见「三态边界补记」）；④ **bounded retry + finite timeout**（有限 attempt 数 + 墙钟 `Timer`）；⑤ 用尽 → 可达的失败返回值，caller 必须据此**不误交接 `run_general_battle`**；⑥ **不叠第二套 repeat/retry delay**（下一次 attempt 的 `REACTION_FIRE` + 状态检查即合理 retry 间隔），也不叠 `confirm_delay` / fatigue。区域级 pacing（RyouToppa `random_delay(1.0, 3.0)`，可开关）是不同 owner、与 FIRE reaction 并存不合并；⑦ **partition / 对手选择点击（RealmRaid `C_PARTITION_n`）必须有明确「仍处于可操作状态」守卫**，`not appear(I_FIRE)` 不是充分条件。
- **RyouToppa `attack_area`**：只把手写 `fire_delay = random_delay(0.2, 0.6)` → `random_delay(*REACTION_FIRE)`（仍在 `for attempt` 循环体内）。成熟状态机（`RYOU_TOPPA_ACTION_RETRIES` / `_wait_for_attack_state` / `is_in_battle` / fresh screenshot / 二次 appear / `AreaAttackResult` / 区域 pacing / fatigue safe node）**未动**，**未加 `confirm_delay`**。
- **RealmRaid `fire()` R-R1**：`while True` + 「`I_RR_PERSON` 消失即成功」+ 恒返回 True → `for attempt in range(1, RR_FIRE_MAX_TRIES+1)` + `Timer(RR_FIRE_TIMEOUT)` + `is_in_battle(False)` 正向确认 + 每 attempt 独立 `REACTION_FIRE` + fresh reconfirm + 有界 `_wait_fire_entered_battle()`（复用 `is_in_battle`，不新造 detector）+ **可达 `return False`**。常量 `RR_FIRE_MAX_TRIES=4` / `RR_FIRE_TIMEOUT=10` / `RR_FIRE_POST_CLICK_TIMEOUT=3` 是 module 级 engineering baseline（参考 `Exploration/base.py::fire()` 与 RyouToppa `RYOU_TOPPA_STATE_TIMEOUT`），**非 Level C 标定、不是不可调架构契约**。`run()` 未改：两处 `if not self.fire(index): continue`（原本不可达）现在生效。`C_PARTITION_n` 空间行为 / T7 / order 逻辑未动。
- **三态边界补记（2026-09-08，同轮追加 —— transition / unknown 收口）**：R-R1 后 `_wait_fire_entered_battle()` 里「`I_FIRE` 与 `I_RR_PERSON` 都不在即 `return False`」仍有**过早失败**——正常页面切换会有「旧 marker 消失 → 过渡 / 加载 blank 帧 → 稍后才出战斗页」。改为 **`-> str` 三态**：`'battle'`（`is_in_battle()`，唯一 positive success）/ `'retryable'`（新纯只读 helper `_is_realm_raid_retryable_state()` = `appear(I_RR_PERSON) or appear(I_FIRE) or appear(I_BACK_RED)` —— 明确仍在个人突破可操作页面）/ `'timeout'`（整个 `RR_FIRE_POST_CLICK_TIMEOUT` 内一直 transition / unknown —— **既不当 success 也不当 immediate failure**，timer 内持续等，用尽进入下一 bounded attempt）。`_is_realm_raid_retryable_state()` **纯只读当前 fresh frame**：不截图 / 不点击 / 不 sleep / 不改状态。`fire()` 循环里 `I_FIRE` 未就绪也走同一三态轮询，**`C_PARTITION_n` 只在 `'retryable'` 分支点击**（对应契约条 ⑦）。`REACTION_FIRE` / `RR_FIRE_*` 数值未改、bounded 未破坏、未新增随机延迟、`run()` caller 未改。
- **测试**：新增 `tests/test_fire_reaction_fsm.py`（`29 → 34`，含三态边界）+ 改 `tests/test_realm_raid_state.py`（`FireCharacterizationTest` `7 → 8` / `LoopAndWaitBoundsTest` 锁新形态）+ `tests/test_general_battle_timing.py`（RealmRaid fire timing 用例）。回归 `1126 → 1156 → 1162`。**非新 ADR**——D001 的 FIRE 落地 + 边界补记（与 D015「bounded retry / recovery 在 Task 层」一致，见 D015 补记）。

**补记（2026-09-08，FIRE 分节 增补 —— 第二批 Orochi / EvoZone 单人 `I_*_FIRE`）**：把上面的三态 FIRE Contract 铺到 Orochi `run_alone` 的 `I_OROCHI_FIRE` 与 EvoZone `run_alone` 的 `I_EVOZONE_FIRE`。本 ADR 决定条目与「长期契约（数值不固化，行为固化）」①~⑦ **全部不变**。

- **迁的是 `run_alone`**：Orochi / EvoZone 真正点 FIRE 的只有 `run_alone`（`run_leader` / `run_member` 走 `run_invite` / `wait_battle` + `run_general_battle`，不点 FIRE，**不迁**）。旧形态 = 内层 `while True`：`appear_then_click(I_*_FIRE, interval=1)` → `not appear(I_*_FIRE)` → 直接 `run_general_battle`（无正向战斗确认、无 bounded、无 reaction）。
- **task-local 三态状态机**（不塞 `BaseTask`、不抽公共 FireStateMachine primitive —— D015）：每任务 3 方法 `_fire_{orochi,evozone}_alone() -> bool` / `_wait_{orochi,evozone}_fire_state(timeout=*_FIRE_POST_CLICK_TIMEOUT) -> str`（`'battle'` / `'retryable'` / `'timeout'`，**不点坐标**）/ `_is_{orochi,evozone}_challenge_retryable() -> bool`（**纯只读**：`appear(I_*_FIRE)`，御魂 / 觉醒单人挑战页除进攻按钮外无其它稳定持久 marker）+ 3 个 module 常量 `{OROCHI,EVOZONE}_FIRE_MAX_TRIES=4` / `*_FIRE_TIMEOUT=10` / `*_FIRE_POST_CLICK_TIMEOUT=3`（对齐 RealmRaid `RR_FIRE_*`，engineering baseline 非 Level C）。
- **caller**：`run_alone` 内层 `while True` → `if self._fire_{orochi,evozone}_alone(): run_general_battle(...); try_fatigue_break(...)`——契约条 ⑤，FIRE 返回 False **不进 `run_general_battle`**，回外层 `while 1` 顶 `screenshot` + `is_in_orochi` / `is_in_evozone` 重新判定。
- **PARTIAL / 未迁**：① 契灵（BondlingFairyland）`I_BALL_FIRE` —— 结构是「连点直到消失，否则 3 次 → `raise BondlingNumberMax`（契灵存量满 500）」+ caller `run_catch` 两条独立语句 + `run_catch` / `run_leader` 共用 `while 1`，**不是单次稳定 Point FIRE → GeneralBattle**，套模板需业务级重构 → 记入 ROADMAP。② Orochi `run_wild` 的 `I_OROCHI_WILD_FIRE` —— 全仓无 `RuleImage` 定义（只有图片 `o/o_orochi_wild_fire.png`），FIRE 路径当前 `AttributeError`，既有断链，修复需造资产 + ROI 标定（Level C）→ 记入 ROADMAP。
- **测试**：新增 `tests/test_second_batch_fire_fsm.py`（27）；改 `tests/test_fire_reaction_fsm.py::OtherFireNotMigratedTest`（`test_orochi_evozone_fire_*` 缩到非 `run_alone` 路径 + 新增契灵未迁用例，净 0）。回归 `1162 → 1189`。

**补记（2026-09-08，FIRE 分节 增补 —— 组队 challenge owner + Action Owner vs Passive Waiter）**：`run_alone` 的 `_fire_*_alone` 只覆盖单人。组队 / 房主真正点「挑战 / 开始战斗」按钮**不是各自 task 点的，而是统一走 `GeneralInvite.click_fire()`**（`run_invite` 里 `room_check_can_fire(config)` 为真时调用；ExperienceYoukai / GoldYoukai / Hunt / Tako 直接调用）。本轮**只在这个公共 owner 上补一次 reaction**，不在 Orochi / EvoZone 各自重复加（避免「公共入口 + task-local 双重 reaction」）。本 ADR 决定条目与「长期契约」①~⑦ 不变。

- **长期原则：battle-entry click 的 reaction 按 Action Owner 而非「单人 / 组队」区分**。**Action Owner**（本机真实识别并点击稳定「挑战 / 开始战斗」按钮）→ `REACTION_FIRE`（每 attempt 独立采样）+ fresh reconfirm + no stale click；**Passive Waiter**（只等别人开战 —— `wait_battle` / `check_then_accept` / member / invitee）→ 无 reaction click。「一个真实 action = 一个 timing owner」：同一个 `click_fire` 被多副本复用时只加一次。
- **`GeneralInvite.click_fire()`**（`tasks/Component/GeneralInvite/general_invite.py`，唯一改动点）：`while 1: screenshot → if not is_in_room(False): break →` 识别 `I_FIRE`（优先）/ `I_FIRE_SEA` → **每 attempt 独立 `random_delay(*REACTION_FIRE)` → `sleep` → fresh `screenshot` → 二次确认**：① `not is_in_room(False)`（reaction 期间已离开房间 / 战斗开始）→ `break` 不点旧坐标；② `not appear(target, 0.7)`（按钮消失但仍在房间）→ `continue` 回循环顶；③ `target` 仍在 → `appear_then_click(target, interval=1, threshold=0.7)`。`is_in_room` 循环边界 + 上层 `run_invite` 的 `Timer(20/30)` / `timer_wait` + `interval=1` throttle + minitouch dwell **不变**；**不叠 `confirm_delay` / 第二套 reaction**；**不接 Fatigue**（组队 challenge 不是疲劳安全节点 —— 与 Fatigue Safe Point 铺开补记「不接邀请 / 房间路径」一致）。正向战斗确认仍在下游 `run_general_battle`，本轮**未改**邀请 / 房间 / 战斗状态链（§13「现有链足够、只补 Action Reaction」；`click_fire` 结构上属 `GeneralInvite`（`MysteryShop` 混入它但无 `GeneralBattle`），故不在此处引 `is_in_battle()`，用既有 `is_in_room` 房间态出口）。
- **自动继承**（`click_fire` 无 task 覆写）：经 `run_invite` = BondlingFairyland / EternitySea / EvoZone / Exploration / FallenSun / Orochi / OtherWorldTwilight；直接调 = ExperienceYoukai / GoldYoukai / Hunt / Tako。共 11 个，本轮不改其它逻辑。
- **RealmRaid / RyouToppa 不纳入**：不是本轮的公共组队挑战入口，各自 FIRE FSM 保持独立实现。
- **测试**：新增 `tests/test_general_invite_challenge_reaction.py`（23）。回归 `1189 → 1212`。

**补记（2026-09-08，FIRE 分节 增补 —— `GeneralInvite.click_fire()` Battle Entry post-click 状态机 / bounded FSM）**：§4.54 只补了 reaction；本轮补 post-click **state contract**（两件事分开记）。承接 RealmRaid 三态收口思路，修 `click_fire()` 的两个结构性问题：① 核心 `while 1: if not is_in_room(False): break` 使**「旧 room 状态消失」隐含等价 success**（但也可能是房间解散 / 队长离开 / loading / overlay / marker 临时失败）；② `click_fire()` 自身 `while 1` **无界**（`run_invite` 的 `timer_wait` 不能打断已进入的同步 `while`）。「长期契约」①~⑦ 不变，追加落地：

- **placement = 方案 A（GeneralInvite 内部拥有 battle verify + marker 兜底）**：READ ONLY inventory 证实 `click_fire()` 的 **11 个 consumer MRO 里全部带 `GeneralBattle`**（Exploration 经 `BaseExploration(GameUi, GeneralBattle, GeneralRoom, GeneralInvite, ...)`）；`general_battle.py` **不 import** `general_invite.py`（无循环依赖）；唯一 `GeneralInvite`-without-`GeneralBattle` 的 `MysteryShop` **不调** `click_fire` / `run_invite`。新增只读 helper `_battle_entry_positive()` = `callable(getattr(self, 'is_in_battle', None))` → `self.is_in_battle(False)`（所有真实 consumer 走这条），否则兜底 **`appear(GeneralBattleAssets.I_BATTLE_INFO) or appear(GeneralBattleAssets.I_PREPARE_HIGHLIGHT)`——`is_in_battle()` 8 个 positive marker 里的两个 battle-entry marker、严格子集**，不新造 detector、不引入 `is_in_battle` 未采用的更宽 heuristic。未选 B（callback 注入——改 11 consumer + `run_invite` 签名）/ C（positive verify 留 caller——caller 无法修内部 while 的 success 误判）。**上一条补记里「不在此处引 `is_in_battle()`」的判断本轮据实测 MRO 收敛为「优先引、带 getattr 兜底」。**（fallback 初版含 `I_EXIT`——`I_EXIT` 不属 `is_in_battle()` marker 集、是 battle-scene 左上角退出按钮的启发式；静态复核后 2026-09-08 收尾轮把 `I_EXIT` 从 `_battle_entry_positive` fallback 移除，见下方「静态复核后最小收尾」补记。`GeneralBattleAssets.I_EXIT` 本体及 `exit_battle` / `check_then_accept` / `BondlingFairyland.wait_battle` / `AbyssShadows` / `Duel` 等原有 consumer 全部保留。）
- **四态**（`_classify_room_entry_state()` 只读，优先级 battle > room_failed > retryable > unknown）：`'battle'`（`_battle_entry_positive()`，**唯一 positive success**）/ `'room_failed'`（`_room_entry_failed()` = `appear(I_MATCHING) or appear(GameUiAssets.I_CHECK_MAIN) or appear(GameUiAssets.I_CHECK_EXPLORATION)`——复用 `ensure_enter` / `run_invite` / `wait_battle` 已有 marker，不新造；「队长跑路」在 `click_fire` 语境不适用）/ `'retryable'`（`is_in_room(False)`）/ `'unknown'`（loading / blank / 转换过渡帧——**既不当 success 也不当 immediate failure**，`_wait_room_entry_state` 有界 `Timer` 内持续等、不点坐标）。**「旧 room 状态消失」单独发生 = `'unknown'`，绝不单独当 BATTLE。**
- **`click_fire() -> str`**（`'battle'` / `'room_failed'` / `'timeout'`）：`Timer(GI_FIRE_TIMEOUT)` + `for attempt in range(1, GI_FIRE_MAX_TRIES + 1)`——分类 → battle/room_failed 立即返回；unknown → 有界 `_wait_room_entry_state` 不点；retryable → 识别 `I_FIRE`（优先）/ `I_FIRE_SEA` → 每 attempt 独立 `random_delay(*REACTION_FIRE)` → `sleep` → fresh `screenshot` → 重新分类 + 二次 `appear(target)`（离开 retryable / 按钮消失 → 不点旧坐标、下一 attempt）→ `appear_then_click(target, interval=1, threshold=0.7)` → `_wait_room_entry_state` → battle/room_failed 返回 / 其它 → 下一 attempt。用尽 → `'timeout'`。**无 `while 1`。** 常量 `GI_FIRE_MAX_TRIES = 4` / `GI_FIRE_TIMEOUT = 15`（组队进战斗比个人突破慢，`run_invite` 的 `timer_wait` / `Timer(20/30)` 都不 bound「按开始→战斗加载」窗口）/ `GI_FIRE_POST_CLICK_TIMEOUT = 4`，均 **PROVISIONAL / Level C 待标定**。**`GI_FIRE_TIMEOUT` 是 soft new-attempt admission budget，不是 strict 15s wall-clock hard deadline**（2026-09-08 静态复核确认）：`overall_timer.reached()` 只在 `for attempt` 循环顶 gate「是否允许启动新 attempt」；已启动的 attempt 的 reaction + `_wait_room_entry_state`（自带独立 `Timer(GI_FIRE_POST_CLICK_TIMEOUT)`、不接收 remaining budget、`Timer.reached()` 纯轮询不打断）会跑完 —— 最后一个在途 attempt 显式 overrun ≈ `max(REACTION_FIRE) 0.8 + GI_FIRE_POST_CLICK_TIMEOUT 4 ≈ 4.8s`，显式返回上界 ≈ `19.8s`（另加 device 开销）。**仍 bounded / finite**（`GI_FIRE_MAX_TRIES` + soft budget + 每个 `_wait_*` 的 `Timer` 三重），**保留 soft**（与 RealmRaid `fire()` / Orochi·EvoZone `_fire_*_alone` 同结构：顶层 `Timer(TIMEOUT).reached()` gate + 内层独立 `Timer(POST_CLICK)`；不在接近 battle 正向确认时因 strict deadline 硬切断；对网络 / 战斗加载抖动更宽容）——本轮及静态复核后收尾轮均不改 timeout 代码。
- **caller guard**：`run_invite` 的 `if room_check_can_fire(config): self.click_fire(); return True` → `fire_result = self.click_fire(); if fire_result == 'battle': return True` else `return False`。`run_invite` 返回 `False` 语义扩大（+`room_failed` / `timeout`）——各 caller 已有的 `else: 邀请失败退出任务` / Exploration 的 `raise InviteFailedException` **天然承接**，**不误交接 `run_general_battle`**。**4 个直接 caller**：ExperienceYoukai / GoldYoukai / Tako 加 `if self.click_fire() == 'battle': (count += 1;) run_general_battle()`；Hunt 加 `battle_entered = self.click_fire() == 'battle'` + `if not battle_entered: return`。业务策略未改。
- **未改**：`REACTION_FIRE`=(0.4,0.8) / 每 attempt 独立采样 / fresh reconfirm / no stale click / 无 timing stack；`run_invite` 的 invite cadence（`Timer(20/30)` / `timer_wait` / emoji）/ `invite_friends` / `room_check_can_fire` / `check_then_accept` / `check_and_invite` / `invite_again` / `wait_battle` / `exit_room`；member / passive path 无 reaction；Orochi / EvoZone `_fire_*_alone`；GeneralBattle FSM；Fatigue（`click_fire` / `_classify_*` / `_wait_*` / `run_invite` / wait 路径无 fatigue token）；RealmRaid / RyouToppa。
- **测试**：`tests/test_general_invite_challenge_reaction.py` `23 → 41`（加 `_FakeTimer` patch `gi.Timer` —— 之前只 patch `sleep` / `random_delay`，超时路径跑真墙钟 113s → 现 0.3s）。回归 `1212 → 1230`。

**静态复核后最小收尾补记（2026-09-08，同 §4.55 追加）**：READ ONLY 静态复核发现两处需收尾（均非 FSM 结构问题）：

- **① `_battle_entry_positive()` fallback 收窄**：移除 `or self.appear(GeneralBattleAssets.I_EXIT)` —— `I_EXIT` 不在 `GeneralBattle.is_in_battle()` 的 8 个 positive marker 里（`is_in_battle` = `I_BATTLE_INFO` / `I_PREPARE_HIGHLIGHT` / `I_FRIENDS` / `I_WIN` / `I_DE_WIN` / `I_FALSE` / `I_REWARD` / `I_REWARD_GOLD`），它是 battle-scene 左上角退出按钮的启发式（`exit_battle` / `check_then_accept` / `BondlingFairyland.wait_battle` / `AbyssShadows` / `Duel` 在用）。收窄后 fallback = `appear(I_BATTLE_INFO) or appear(I_PREPARE_HIGHLIGHT)` —— `is_in_battle()` 的**严格子集**。**11 / 11 真实 `click_fire` consumer MRO 都带 `GeneralBattle` → 正常路径全走 `self.is_in_battle(False)`，从不进 fallback → 0 behavior change**；`MysteryShop`（唯一 `GeneralInvite`-without-`GeneralBattle`）不调 `click_fire` / `run_invite`，不受影响。**`GeneralBattleAssets.I_EXIT` 本体（`gb_exit.png` / ROI / threshold）及全部其它 consumer 保留不动。** docstring 同步改正（原「复用 is_in_battle 用的同一批 marker」是事实错误）。
- **② `GI_FIRE_TIMEOUT` 语义定性 = SOFT_ATTEMPT_BUDGET**（文档修正，**不改代码**）：见上「`GI_FIRE_TIMEOUT` 是 soft new-attempt admission budget」条。保留 soft 设计——与 RealmRaid `fire()` / Orochi·EvoZone `_fire_*_alone` 结构一致；strict deadline 需 plumb remaining budget、切断接近确认的战斗加载、增加测试复杂度、与三个已定型 FIRE FSM 不一致，收益（~5s 可预测性）不值当。
- **测试**：`tests/test_general_invite_challenge_reaction.py` `41 → 46`（fallback 不再引 `I_EXIT` / 是 `is_in_battle` 严格子集 / `I_EXIT`-only 时 fallback 不判 battle / `MysteryShop` 不调 `click_fire` / `I_EXIT` asset 与 `exit_battle` · `check_then_accept` 其它 consumer 未动）。`GI_FIRE_*` 数值 / `Timer` / FSM / `run_invite` guard / 4 直接 caller guard / `REACTION_FIRE` 均未改。回归 `1230 → 1235`。D001 早已划定 micro（`confirm_delay`）/ macro（`FatigueManager` idle·rest，仅 task-cycle 安全节点）的边界。本补记固化 macro 侧「安全节点放哪 / 不放哪」的长期契约，供后续任务逐个铺开时对照（当前 consumer：RyouToppa + Orochi / EvoZone 单人 + RealmRaid + Exploration solo）。

- **只允许放在**：一个完整 Business Cycle 已结束 → 已回到稳定可继续页面（Stable Return State）→ Fatigue Safe Point（`try_fatigue_break(safe=True, repeat_completed=True, deadline=)`）→ optional idle / rest → **fresh screenshot + revalidate 当前业务页面**（`try_fatigue_break` 自身不截图 / 不重识别 state，由业务 Task 在 safe node 之后负责）→ Next Cycle。
- **禁止放在**：FIRE 点击前 / FIRE reaction 内 / FIRE retry 内 / transition-unknown 内 / battle 中 / battle prepare 中 / GeneralBattle result / Settlement 双击之间 / reward polling 内 / room critical timing 内。
- **不接的路径**：存在邀请 / 房间等待 / 队友同步 / 短窗口的路径（leader / member / wild）——idle 会破坏组队。只在安全的 `run_alone` 或明确 host-controlled 连续循环先接。
- **不新增第二套 fatigue 系统**；`GeneralBattle` **永不**成为 Fatigue owner（它不知道战斗后业务是下一场 / 刷新 / 退出 / 活动下一轮）——owner 永远是外层 Task。
- ~~**活动体力·门票挑战仍不接**（尚无 FIRE FSM）~~ —— **2026-09-09 §4.62 已接入 ActivityShikigami 普通爬塔线**（见本 ADR 末尾「§4.62」补记）：`_activity_challenge_safe_break` 在「稳定挑战页 + 挑战键 positive」触发 `try_fatigue_break`，休息后 fresh revalidate 页 / 键 / 资源；爬塔线旧 `random_sleep` 由 `_fatigue_owns_macro_idle` gate 关掉。大富翁 / 伪神降临不接。**RealmRaid 已于 §4.56 接入**；**Exploration solo 已于 §4.58 / D021 接入**——只在 Boss win、map ready、direct exit 与 `page_exp_entrance` positive success 后触发，deadline=`start_time+limit_time`，之后 fresh revalidate；leader/member 不接。当前 Fatigue consumer = RyouToppa + Orochi / EvoZone 单人 + RealmRaid + Exploration solo + ActivityShikigami 爬塔线。

**补记（2026-09-08，FIRE 分节 增补 —— RealmRaid `_fire_again()` 退四内部「再次挑战」）**：§4.56 RealmRaid 主业务改造把退四内部的失败结算页「再次挑战」按钮也纳入 FIRE Contract。旧 `fire_again()` = `wait_until_appear(I_FIRE_AGAIN)`（无超时）+ `while 1` 连点，恒返回 True、尾部 `return False` 不可达（静态收口 R-R3）。**「长期契约（数值不固化，行为固化）」①~⑦ 不变**，落地：

- **`fire_again()` → `_fire_again() -> bool`**（改私有名，`run()` 退四路径唯一调用方）：`wait_until_appear(I_FIRE_AGAIN, wait_time=RR_AGAIN_TIMEOUT)` + `Timer(RR_AGAIN_TIMEOUT)` + `for attempt in range(1, RR_AGAIN_MAX_TRIES + 1)`——① 正向 `is_in_battle(False)` → `return True`（唯一 positive success，复用 `GeneralBattle.is_in_battle`，不以「`I_FIRE_AGAIN` 消失」判成功）；② `I_SHOW_AGAIN`（「不再提示」复选框）/ `I_FRESH_ENSURE`（共享确认弹窗）是**流程点击、无 reaction**，先 `appear_then_click(..., interval=2)` 点掉；③ `I_FIRE_AGAIN` 未就绪 → 有界 `_wait_again_entered_battle()`；④ 就绪 → 每 attempt 独立 `random_delay(*REACTION_FIRE)` → `sleep` → fresh `screenshot` → 二次 `appear(I_FIRE_AGAIN, threshold=0.8)`（消失不点旧坐标）→ `appear_then_click(I_FIRE_AGAIN, interval=0, threshold=0.8)` → `_wait_again_entered_battle()`。用尽 → **可达 `return False`**（`run()` 退四路径 → `check_refresh()` 刷新，不再点「再次挑战」）。
- **`_wait_again_entered_battle(timeout=RR_AGAIN_POST_CLICK_TIMEOUT) -> str`**（有界 `Timer`，**不点任何坐标**）：`'battle'`（`is_in_battle()`）/ `'failure_page'`（`appear(I_FIRE_AGAIN, 0.8) or appear(I_FRESH_ENSURE)` —— 仍在失败结算页，retryable）/ `'timeout'`（整个 timer 内一直是「按钮消失、battle 未出现」的过渡 / 未知帧 —— **既不当 success 也不当 immediate failure**）。
- **常量**（module 级 engineering baseline，**非 Level C**，对齐 `RR_FIRE_*`）：`RR_AGAIN_MAX_TRIES = 4` / `RR_AGAIN_TIMEOUT = 10` / `RR_AGAIN_POST_CLICK_TIMEOUT = 3`。
- **退四次数 `RR_EXIT_FOUR_SURRENDERS = 4`** 不是 FIRE 契约的一部分，是 RealmRaid 业务策略（见 **D020**）——旧 `run()` 逐字硬编码的 4 次 `fire_again()`，源码可证，非新拍。
- **未纳入 FIRE 契约**：`RR_TARGET_PACING = (1.0, 2.5)`（目标级业务 pacing，见 **D020**）与 FIRE reaction 是不同 owner——同「长期契约」条 ⑥ 里 RyouToppa 区域 pacing `(1.0, 3.0)` 的定位，并存不合并。
- **测试**：`tests/test_realm_raid_state.py` 重写——`FireAgainCharacterizationTest`(4) → `FireAgainThreeStateTest`(11)。`tests/test_reaction_timing_batch1.py` 一行改（`fire_again` → `_fire_again`）。回归 `1235 → 1257`。**非新 ADR**——D001 FIRE 分节落地 + D020（RealmRaid 主业务策略）。

**补记（2026-09-08，FIRE 分节 增补 —— Level C hotfix：Battle Lifecycle Detector ≠ New Battle Entry Detector）**：2026-09-08 真机日志实测发现，退四首战主动退出、`Battle result: Lose` 之后 `_fire_again()` **没有任何 `Fire again: attempt` / reaction / `I_FIRE_AGAIN` 点击就直接 `Fire again: entered battle`**，caller 又 `run_general_battle()` 立即重新识别同一个 `page_battle_result` → 假退四循环。根因：上面「`fire_again()` → `_fire_again()`」补记里的「正向 `is_in_battle(False)` → `return True`」用错了 detector —— `GeneralBattle.is_in_battle()` 是「准备 + 战斗 + 结果 + 奖励」整个战斗生命周期 detector（`I_BATTLE_INFO | I_PREPARE_HIGHLIGHT | I_FRIENDS | I_WIN | I_DE_WIN | I_FALSE | I_REWARD | I_REWARD_GOLD`），其中 `I_FALSE` / `I_WIN` / `I_DE_WIN` / `I_REWARD` / `I_REWARD_GOLD` 是 result / reward marker，失败结算页 `I_FALSE` 命中即 `is_in_battle() = True`。

- **长期规则（行为固化）**：**challenge / `fire_again` / retry 这类「点了按钮后判断是否进入了一场*新*战斗」的 positive 成功确认，不得使用包含 result / reward marker 的宽生命周期 detector（`is_in_battle()`）**——它回答的是「还在战斗生命周期里」，不是「已进入一场新战斗」。应使用**只含 active prepare / battle marker 的窄 positive detector**。这不推翻「长期契约 ③ 成功判据是正向战斗状态」——是把「正向战斗状态」在「retry-after-battle」语境下**收窄**到 prepare / active-battle（排除 result / reward），因为此时上一场的 result 页会先于新战斗出现。
- **RealmRaid 落地（只改 RealmRaid consumer，`GeneralBattle.is_in_battle()` / `is_in_prepare()` / `is_in_real_battle()` 本体及其它 consumer 全不动）**：新增 RealmRaid-local 只读 helper **`_is_active_battle_entry() -> bool`** = `self.is_in_prepare(False) or self.is_in_real_battle(False)` —— 复用 GeneralBattle 已有的**两个窄 detector**：`is_in_prepare()`（`I_BUFF` / `I_PREPARE_HIGHLIGHT` / `I_PREPARE_DARK` / `I_PRESET` / `I_PRESET_WIT_NUMBER`）、`is_in_real_battle()`（`I_BATTLE_INFO`），两者都不含 result / reward marker。`_fire_again()` 的 3 处 + `_wait_again_entered_battle()` 的 1 处 `is_in_battle(False)` 全部换成 `_is_active_battle_entry()`。三态语义（`battle` / `failure_page` / `timeout`）不变，只是 `battle` 判据收窄。失败结算页现在正确落 `failure_page`（`I_FIRE_AGAIN` / `I_FRESH_ENSURE` 可见）→ 走 reaction + 真实 `I_FIRE_AGAIN` click。
- **`fire()` R-R1 本轮不动**：`fire()` 也用 `is_in_battle(False)` 作 positive，但它在 `wait_until_appear(I_RR_PERSON)` 之后、目标详情页上点第一次 FIRE，其前没有战斗结果页（RealmRaid 主循环里 `check_ticket` / `_grid_targets` / `_enter_target` 已把页面带回九宫格）——安全-by-context。未来若要一致性收窄再评估（`docs/ROADMAP.md` Level C 项），本轮 scope 只限 `_fire_again`。
- **不借机调参**：当前 bug 与 `RR_AGAIN_MAX_TRIES = 4` / `RR_AGAIN_TIMEOUT = 10` / `RR_AGAIN_POST_CLICK_TIMEOUT = 3` 无关，数值全不动；`REACTION_FIRE = (0.4, 0.8)` / 每 attempt 独立采样 / fresh reconfirm / no stale click / 无 `confirm_delay` 不变；`RR_EXIT_FOUR_SURRENDERS = 4` / 退四触发 / `RR_TARGET_PACING` / try/finally unlock / `failed_orders` / `when_attack_fail` / Fatigue safe point 不动。
- **测试**：`tests/test_realm_raid_state.py` `93 → 103`——`FireAgainThreeStateTest._mk` 改 mock `t._is_active_battle_entry`；新增 `ActiveBattleEntryContractTest`(10，源码形态 + 行为，含核心回归「`I_FALSE` 帧 + `I_FIRE_AGAIN` 可见 → `_fire_again()` 不 short-circuit、必须真实点『再次挑战』」）。回归 `1287 → 1297`。**非新 ADR**——D001 FIRE 分节 Level C 落地。同步：OASX `lib/translation/cn_parts/cn_realm_raid_config.dart`（退四 / 勋章档位文案，`order_attack` 字段保留——仍被 `order_medal` 消费，改名不删）+ backend `module/config/i18n/zh-CN.json`（同 4 key）。

相关文件：`tasks/base_task.py`（`appear_then_click` / `begin_fatigue_task` / `try_fatigue_break`），`module/reaction_profile.py`（**语义 profile 常量，含 `REACTION_FIRE`**），`tests/test_base_task_confirm_click.py`（5，primitive 行为）/ `tests/test_reaction_timing_batch1.py`（34，第一批迁移护栏 + `_fire_again` 无 confirm_delay）/ `tests/test_fire_reaction_fsm.py`（34，FIRE reaction + R-R1 + 三态）/ `tests/test_second_batch_fire_fsm.py`（27，Orochi/EvoZone 单人 + Fatigue 第一批 + 契灵 PARTIAL）/ `tests/test_general_invite_challenge_reaction.py`（46，公共组队 challenge owner reaction + Battle Entry post-click 四态 / bounded FSM + `_battle_entry_positive` fallback 收窄 + Action Owner vs Passive Waiter）/ `tests/test_realm_raid_state.py`（`fire()` R-R1 三态 + `_fire_again()` 三态 bounded + 固定 1→9 + 退四主流程 + Fatigue safe point）+ `tests/test_general_battle_timing.py`（FIRE 新形态），`tasks/RealmRaid/script_task.py`（`fire()` R-R1 + `_wait_fire_entered_battle` + `RR_FIRE_*`；`_fire_again()` + `_wait_again_entered_battle` + `_is_active_battle_entry()`（Level C hotfix：窄 active-battle-entry positive，替代 `is_in_battle()`）+ `RR_AGAIN_*`；`_grid_targets` / `_broken_orders` / `find_one` / `_enter_target` / `RR_TARGET_PACING` / 退四主流程 / `_realm_raid_cycle_safe_break` —— 见 **D020**）/ `tasks/Component/GeneralBattle/general_battle.py`（`is_in_battle` 宽 / `is_in_prepare` · `is_in_real_battle` 窄 —— 本体不动，RealmRaid `_is_active_battle_entry` 复用后两者）/ OASX `lib/translation/cn_parts/cn_realm_raid_config.dart` + backend `module/config/i18n/zh-CN.json`（退四 / `order_attack` 文案同步）/ `tasks/RyouToppa/script_task.py`（`attack_area` FIRE delay 统一 + fatigue safe node）/ `tasks/Orochi/script_task.py` / `tasks/EvoZone/script_task.py`（`_fire_*_alone` 三态 + `*_FIRE_*` 常量 + `run_alone` fatigue）/ `tasks/Component/GeneralInvite/general_invite.py`（`click_fire` 公共组队 challenge owner reaction + Battle Entry 四态 / bounded FSM + `_battle_entry_positive` / `_room_entry_failed` / `_classify_room_entry_state` / `_wait_room_entry_state` + `GI_FIRE_*` 常量 + `run_invite` guard）/ `tasks/{ExperienceYoukai,GoldYoukai,Hunt,Tako}/script_task.py`（直接 caller `== 'battle'` guard）/ `tasks/Exploration/{base,script_task}.py`（Batch A consumer），`tasks/Component/GeneralBattle/general_battle.py`（`check_lock` 扩参 + `is_in_battle` 被 FIRE FSM 复用 + 自有时序契约），`docs/常用业务点击链与Reaction审查.md` / `docs/Action点击前反应时序静态审查.md`，`docs/RealmRaid状态机静态收口.md`（R-R1 由此提出），`module/fatigue.py`（macro timing 边界），`docs/AI_CONTEXT.md` §4.51 / §4.52 / §4.53 / §4.54 / §4.55 / §4.56。

---

**补记（2026-09-08，RealmRaid 再次挑战确认弹窗）**：`I_FRESH_ENSURE` 的资产语义为「刷新确认 / 再战确认」，而 `I_SHOW_AGAIN` 是「不再提示」复选项，不能按名称猜测或互换。`_fire_again()` 内的 `I_FIRE_AGAIN`（再次挑战）继续由业务 FSM 的 `REACTION_FIRE=(0.4,0.8)` 独立 owner；其后的真实确认动作才显式使用 `confirm_delay=RR_AGAIN_CONFIRM_DELAY=(0.3,0.6)`。该调用复用 D001 primitive 的「随机等待 → fresh screenshot → 二次 `appear` → 新坐标 click」事务，确认按钮消失即不点击。两个 owner 不复用区间、不在同一 click 上叠加；`interval=2` 仍只是跨轮次 Timer 节流。区间是 PROVISIONAL，改值需同步本补记、§4.57、ROADMAP 和测试。

**补记（2026-09-09，§4.62 —— ActivityShikigami 当期普通爬塔线接入 FIRE 分节 + Fatigue Safe Point）**：`tasks/ActivityShikigami` 普通爬塔（`NormalClimbAct`）成为 FIRE 分节的又一 consumer，同时接入「Challenge Ready = Fatigue Safe Point」。**非新 ADR**——是 D001 FIRE 分节 / narrow new-entry contract / Fatigue Safe Point 铺开补记的又一次落地。大富翁 / 伪神降临线不改。

**补记（2026-09-18，FIRE 分节 增补 —— 任务级可配置 reaction，从 L2 worktree 最小范围移植）**：此前 FIRE reaction
一律用公共常量 `REACTION_FIRE=(0.4,0.8)`，OASX 无法按任务单独调整。本轮从未合并的 L2 worktree
`wt-l2-interaction-reaction` 按「最小范围」移植配置能力，**不带入**该 worktree 的 L1 Global Click Pipeline /
L2-2 普通点击 `policy=` 迁移（master `appear_then_click` 签名不变）。落地：

- 共享 schema `tasks/Component/config_fire_reaction.py::FireReactionConfig`（`fire_reaction_min_ms` /
  `fire_reaction_max_ms`，默认 400/800，单位 ms，`0<=min<=max<=5000`，`min==max` 合法，字段级交叉校验 +
  `validate_assignment`，非法单字段修改被拒且旧值保持）+ `module/interaction_policy.py::fire_reaction_range()`
  （ms→秒换算，`None` = 回落 `REACTION_FIRE`）；`InteractionPolicy` 枚举本轮**零消费者**，不改
  `appear_then_click`。
- 8 个 FIRE consumer（RealmRaid `fire`/`_fire_again`、RyouToppa `attack_area`、EvoZone、Orochi 单人+组队（`run_wild`
  按要求排除）、ActivityShikigami、`GeneralInvite.run_invite`/`click_fire`）**FSM 不重写**，只把
  `random_delay(*REACTION_FIRE)` 换成 `random_delay(*fire_reaction_range(<task>.fire_reaction))`；`click_fire`
  新增可选 `fire_reaction=None` 形参、调用方沿配置传入，未接入的其它 consumer（ExperienceYoukai / GoldYoukai /
  Hunt / Tako 等）行为不变。
- EternitySea `run_alone` / FallenSun `run_alone` / Sougenbi `run` 此前**完全无 reaction**（裸 `interval=1` 连点），
  本轮新增：不建三态状态机，直接用 primitive 既有 `confirm_delay=fire_reaction_range(<task>.fire_reaction)`（
  `interval` 同步改 0，避免与旧节流叠成两个 timing owner）。
- **测试**：新增 `tests/test_fire_reaction_task_config.py`（30，含真实驱动到点击分支的配置生效证明），改 7 个
  既有测试文件的 `REACTION_FIRE` 断言（跳过其中的 `policy=` 迁移断言）。回归 `1530 → 1560`。**非新 ADR**——
  D001 FIRE 分节的又一次落地，长期契约①~⑦不变，只是 reaction 数值来源从常量变成「任务配置，缺省=常量」。

- **窄 New Battle Entry Detector**：新增 `BaseAct._is_active_battle_entry()` = `self.is_in_prepare(False) or self.is_in_real_battle(False)`（同 RealmRaid 同名 helper；`GeneralBattle.is_in_battle()` / `is_in_prepare()` / `is_in_real_battle()` 本体及其它 consumer 不动）。理由与上面「Battle Lifecycle Detector ≠ New Battle Entry Detector」补记一致：**本期活动战斗结束是一个「活动专用结算弹窗」**，宽 `is_in_battle()`（含 `I_FALSE` / `I_WIN` / `I_REWARD`）会把结算弹窗 / 上一场结果残留误判成「已进入下一场新战斗」。`_enter_climb_battle` 与 `_drain_activity_settlement` 的 battle-entry 判据都走窄 helper。
- **FIRE Contract**：`_enter_climb_battle` 从旧 `while True` + `is_in_battle(False)` + 仅 `random.randint(3,5)` 次点击 改为 bounded battle-entry transaction——`_classify_climb_fire_state` 三态（`battle` / `ready` / `unknown`）+ `_wait_climb_fire_state` 有界轮询（`'timeout'` 既不当 success 也不当 failure）；每 attempt 独立 `random_delay(*REACTION_FIRE)` → `sleep` → fresh `screenshot` → 二次确认挑战键仍在才点，reaction 期间离开 ready / 按钮消失 → 不点旧坐标；`for attempt in range(1, ACTIVITY_FIRE_MAX_TRIES+1)` + `Timer(ACTIVITY_FIRE_TIMEOUT)` + `ACTIVITY_FIRE_POST_CLICK_TIMEOUT` 三重有界，用尽 → `return False` → caller 转 `ActivityResourceNotEnough`。常量 **`ACTIVITY_FIRE_MAX_TRIES=4` / `ACTIVITY_FIRE_TIMEOUT=12` / `ACTIVITY_FIRE_POST_CLICK_TIMEOUT=4`** —— module 级 engineering baseline，对齐 `GI_FIRE_*` / `RR_FIRE_*` 量级，**非 Level C 标定**，改值连带更新本补记 + §4.62。
- **RESOURCE_EMPTY 语义**：本期**无**挑战按钮置灰态、**无**资源不足弹窗、**无**购买确认弹窗（资源不足仅一闪而过 ~1s 提示文字，无稳定 marker）。因此不新增假 disabled / popup 资产、不建 READY/DISABLED 双模板 FSM。资源主判据 = FIRE 前 `_climb_resource_available` 的 OCR（`O_REMAIN_AP` / `_PASS` / `_BOSS` / `_AP100`，`_normalize_climb_consumable_count` 容错保留）；bounded battle-entry 用尽后统一转 `ActivityResourceNotEnough` 作 fallback（日志 `Climb resource exhausted: <type>`）。
- **Challenge Ready = Fatigue Safe Point**：`NormalClimbAct._activity_challenge_safe_break(action_type, destination, *, repeat_completed)` 是**唯一** `try_fatigue_break` 调用点（task-local）：fresh screenshot → 当前页 == destination 且挑战键 positive → `try_fatigue_break(safe=True, repeat_completed=..., deadline=start_time+limit_time_v)` → 若真休息 / 发呆过：结束后 fresh screenshot 重新确认「仍在挑战页 + 挑战键仍在 + 资源 OCR 仍允许」，页面变化 → 返回 False（不点旧坐标），资源在休息期间耗尽 → `raise ActivityResourceNotEnough`。**Cycle 边界 = 「活动结算已处理 + 回到稳定挑战页 + Challenge Ready positive」**，不是「结果页出现」也不是「弹窗消失」：`repeat_completed` 首轮 `False`，一场 battle + 活动结算 drain 完整跑完后 `cycle_completed = True`。**禁止**把 `try_fatigue_break` 直接塞进 `prepare_next_action`（它只管次数 / 时限 / 计数）。
- **macro-idle owner 唯一**：新增 `BaseAct._fatigue_owns_macro_idle`（`run_climb` 置 True + `begin_fatigue_task('ActivityShikigami')`）；`prepare_next_action` 的 `random_sleep` 改成 `if random_sleep_cfg and not self._fatigue_owns_macro_idle:` —— 爬塔线宏观空闲交给 Fatigue，同一 cycle 不再出现 `random_sleep` + Fatigue 两个 macro-idle owner；大富翁 / 伪神线（不接 Fatigue）仍 `random_sleep`。`BaseAct` 通用能力不全局删除。
- **活动结算弹窗复用 `random_default`**：新增有界 `NormalClimbAct._drain_activity_settlement(action_type, destination)`——`run_general_battle` 返回后调用，每次点 `self._sample_settlement_click(self.C_RANDOM_DEFAULT)`（**复用** GeneralBattle Settlement V3 的采样入口 + `random_default` 大安全区，不新造坐标 / 区域 / `random.randint`），间隔 `random_delay(*self.SETTLEMENT_CLICK_INTERVAL_RANGE)`；直到 `get_current_page()==destination` 且挑战键可见（= cycle complete）或 `ACTIVITY_SETTLEMENT_MAX_CLICKS=6` / `Timer(ACTIVITY_SETTLEMENT_TIMEOUT=15)` 用尽。**弹窗消失本身不算成功**，必须重新识别到挑战页 + 挑战键 positive；又落回战斗态 → 返回 False 交回外层。**GeneralBattle Settlement V3 / `_settlement_click` / `_sample_settlement_click` / region 选择一字未改**——是否需要把这个弹窗纳入 GeneralBattle 通用 result layout 待 Level C 证据（用户当前描述是「本期活动结算变化」，默认 task-local）。
- **入口**：`page_main → page_act` 边动作换成 `goto_activity_entry(task)` callable——优先 `appear_then_click(I_MAIN_GOTO_ACT_2, interval=1, confirm_delay=REACTION_NAVIGATION)`，旧 `I_MAIN_GOTO_ACT` 作跨活动周期回退（两图标都保留在 `assets.py`）。入口图标消失不代表进入成功，仍由 `page_act` positive marker 判定。
- **二层爬塔入口 page graph（2026-09-10，真机确认本期链，纯 page marker / page graph）**：本期普通爬塔真实链 = `page_act --I_TO_BATTLE_MAIN--> page_climb_main（中间「进入爬塔」页）--I_TO_BATTLE_MAIN_2--> page_climb_ap / page_climb_pass`（旧的 `page_act` 直连 climb 页已不成立）。用户新增资产 `I_TO_BATTLE_MAIN_2`（`climb_to_battle_main_2.png`，「战斗·<本期名>」进入按钮）+ `I_CHECK_BATTLE_PASS_2`（`climb_check_battle_pass_2.png`，本期爬塔页标题横幅）。落地：① `page.py` 新增 task-local 中间页 `page_climb_main = Page(I_TO_BATTLE_MAIN_2)` —— positive marker 是**该页稳定存在的进入按钮**（不是「上一页按钮消失」），它同时是 `page_climb_main → page_climb_*` 的边动作；`page_climb_main.connect(page_act, I_UI_BACK_YELLOW)` 作 recovery。② `page_climb_ap` / `page_climb_pass` recognizer：`all_of(I_CHECK_BATTLE_PASS, MODE)` → `all_of(any_of(I_CHECK_BATTLE_PASS_2, I_CHECK_BATTLE_PASS), MODE)`（本期新 marker primary + 旧 legacy fallback，仍 `all_of` 带 mode → 与中间页互斥，**不靠 priority**，静态验证「只 `I_TO_BATTLE_MAIN_2` 时 climb 页 recognizer 为假」）；climb 页 yellow-back 边重定向到 `page_climb_main`（`climb → climb_main → activity`）。③ `normal.py::setup_climb_pages` 的 `page_act →(I_TO_BATTLE_MAIN) climb_ap/pass` 两条直连边换成 `page_act →(I_TO_BATTLE_MAIN) page_climb_main` + `page_climb_main →(I_TO_BATTLE_MAIN_2) climb_ap/pass`；mode 切换（`I_CLIMB_MODE_SWITCH` + `conditional_action` enter-failure hook）不变。**business boundary 天然保持**：`_run_climb_type` 业务分支仍 `if current_page == destination:`（= `page_climb_ap/pass`，需 `I_CHECK_BATTLE_PASS_2/PASS` + mode），中间页只有 `I_TO_BATTLE_MAIN_2` → Fatigue / resource OCR / FIRE / settlement 不在中间页触发。**未改** `page_act` recognizer / priority / threshold / ROI（不重做已撤回的 hotfix），未改 FIRE / REACTION_FIRE / Fatigue / Challenge Ready（仍 `_climb_fire_rule` = `I_ACT_FIRE`/`I_AS_BOSS_FIRE`，与 `I_TO_BATTLE_MAIN_2` 无关）/ Resource OCR / Settlement / GeneralBattle。`page_climb_ap100` / `page_climb_boss`（ap/pass 之外，非本期 production 路径）edge 未动——是否也有中间页 = Level C 另查。旧活动一层结构 vs 本期二层结构不做复杂多分支 FSM，优先本期。
- **未改**：`RichManAct` / `FakeGodAct`（含 `_enter_fakegod_battle` 旧 `while True`）、`GeneralBattle`、`BaseAct.before_run` 的 `page_battle_result` recognizer monkeypatch（P1 技债，本轮爬塔适配不依赖它改动）、其它任务。
- **测试**：新增 `tests/test_activity_shikigami_climb.py`（46 → 58，+12 `SecondLayerClimbEntryTest` 为 2026-09-10 二层入口）。回归 `1357 → 1403 → 1415`，0 regression。相关文件追加：`tasks/ActivityShikigami/{page.py, base_act.py, activities/normal.py, assets.py（用户生成 I_TO_BATTLE_MAIN_2 / I_CHECK_BATTLE_PASS_2）, as/climb/pages.json}`、`docs/AI_CONTEXT.md` §4.62 / §7。

**补记（2026-09-15，L2-1 Interaction Reaction Layer：InteractionPolicy + FIRE 任务配置）**：本 ADR 的
「reaction 只在调用点显式 opt-in、primitive 默认不启用、不与 Fatigue 叠加、不给 Settlement / poll 加」全部**不变**，
在其上补一层正式语义：

- **分层 ownership**：L1（`module/click_pipeline.py` → `Control.click` → 后端，D026）只管「点在哪 / 怎么落下」，
  执行器、`Control.click`、minitouch 里**不许**出现 reaction / 随机等待 / fresh 截图；L2（`module/interaction_policy.py`
  + `BaseTask.appear_then_click`）只管「目标已识别后等多久、点前是否 fresh confirm」；L3（业务 FSM）拥有点击后状态判定 /
  有限重试 / 超时 / 恢复。L2 confirm 失败 = 本次不点、返回 False，**不重试**。
- **`InteractionPolicy`**：`IMMEDIATE / FAST / NORMAL / NORMAL_HIGH / CONFIRM / NAVIGATION / DELIBERATE`
  映射到 `module/reaction_profile.py` 既有区间（数值不改，仍 PROVISIONAL）；`FIRE_SPECIAL / SPECIAL` 表示 timing 由专门状态机
  拥有，交给 `appear_then_click` 直接 `ValueError`。
- **legacy 兼容与参数优先级**：`appear_then_click(target)` / `policy=IMMEDIATE` = 原立即点击，**不因 API 改造变慢**；
  只传 legacy `confirm_delay=(lo, hi)` = 原样沿用；只传 `policy` = profile 区间；**同时传两者直接 `ValueError`**（一个
  动作只能有一个 reaction owner，静默取其一会掩盖叠加写法）。`GeneralBattle.check_lock` 原样透传两个参数。
- **fresh confirm contract 沿用 primitive**：识别 → `random_delay`（SystemRandom，每次调用独立采样）→ `sleep` →
  `screenshot` → 同一目标再 `appear`（更新 `roi_front`）→ 用新帧的 `coord()` 交给 L1；目标消失零点击。
- **既有具名 reaction 统一用 policy 表达**：`confirm_delay=REACTION_*` 的 28 个生产调用点（EvoZone 4 / Orochi 5 / RealmRaid 6 /
  RyouToppa 3 / Exploration 8 / ActivityShikigami 入口 2）改为 `policy=InteractionPolicy.*`，区间逐值相同；非 profile 的
  `RR_AGAIN_CONFIRM_DELAY=(0.3, 0.6)` 保留 legacy 写法（不借机调参）。未分析过的立即点击**不**批量改 NORMAL；Navigator
  `_execute_action` 是所有 transition / hook 的通用引擎，区分不了「页面首次显现后的用户动作」与 polling / 恢复，本轮保持
  IMMEDIATE。`NORMAL_HIGH` 仍 0 consumer。
- **FIRE = Battle Entry Action**（本机点击直接让业务从 Ready / Prepare 进入正式 Battle 的挑战 / 进攻 / 开始）：7 个 owner
  （RealmRaid `fire` / `_fire_again`、RyouToppa `attack_area`、EvoZone / Orochi `_fire_*_alone`、GeneralInvite `click_fire`、
  ActivityShikigami `_enter_climb_battle`）的 FSM **不重写**——仍是 owner 自己每 attempt `random_delay` → `sleep` → fresh
  screenshot → 窄 positive-state → 目标仍在 → `appear_then_click(target, interval=0/1)`（**不带** policy / confirm_delay）→
  post-click 分类 → bounded retry。唯一改动是区间来源：`random_delay(*fire_reaction_range(<当前任务配置>.fire_reaction))`。
- **FIRE 配置 = 当前任务的 override**：共享 schema `tasks/Component/config_fire_reaction.py::FireReactionConfig`
  （`fire_reaction_min_ms` / `fire_reaction_max_ms`，默认 400 / 800，单位 ms，运行时 /1000 转秒），按任务保存在
  RealmRaid / RyouToppa / EvoZone / Orochi / ActivityShikigami 的 `fire_reaction` 组；没有该组 / 没传入 = 公共默认
  `REACTION_FIRE`。校验 `0 <= min <= max <= 5000`，`min == max` 合法；非法值在配置层拒绝，运行时不交换、不钳制。
  用字段级交叉校验 + `validate_assignment`：OASX 单字段修改（`setattr`）失败时旧值保持不变（model 级 after 校验会先写入非法值）。
- **公共组件不猜配置**：`GeneralInvite.run_invite(..., fire_reaction=None)` → `click_fire(fire_reaction=None)` 由调用方沿配置
  传入（Orochi / EvoZone 已传）；GeneralInvite 不读 `self.config` / script_name / 配置文件。其它 `click_fire` / `run_invite`
  consumer（ExperienceYoukai / GoldYoukai / Hunt / Tako / FallenSun / EternitySea / BondlingFairyland / Exploration /
  OtherWorldTwilight）暂用公共默认。
- **明确排除**：GeneralBattle Settlement Micro-Burst（segment / 0.30~0.60 observe / anchor 生命周期是它自己的 timing owner，
  不读 InteractionPolicy / FIRE 配置）；Fatigue（macro idle owner，L2 不调用）；AccountRotation / SwitchAccount / Login /
  DailyTrifles 不纳入 master L2。

相关文件：`module/interaction_policy.py`、`tasks/Component/config_fire_reaction.py`、`tasks/base_task.py::appear_then_click`、
`tasks/Component/GeneralBattle/general_battle.py::check_lock`、7 个 FIRE owner、`assets/i18n/zh-CN.json`、`config/template.json`、
`tests/test_l2_interaction_reaction.py`（26）。状态：Level A/B PASS，Level C PENDING。

---

**补记（2026-09-15，L2-2 Interaction Policy Migration：逐点分类，只迁高置信 Point Action）**：L2-1 的 policy 语义、
区间、legacy 兼容与「一个 reaction owner」全部**不变**。本轮对 master 主线高频公共路径（GeneralInvite / GeneralBattle /
GameUi / EvoZone / Orochi / RealmRaid / RyouToppa / Exploration / ActivityShikigami / KekkaiUtilize，18 个文件 179 个点击调用点）
逐点回答「为什么现在点、属于哪个 policy、reaction / retry owner 是谁、是否 fresh confirm」，清单见
`docs/L2_INTERACTION_POLICY_MAP.md`。长期规则：

- **分类必须显式**：MIGRATE / ALREADY_L2 / KEEP_IMMEDIATE / KEEP_SPECIAL / NEEDS_C 五类，审计范围内每个点击都登记在册并由
  测试锁定源码 timing；新增点击或改 timing 必须先分类。**IMMEDIATE 不需要归零**，以下都是合法立即点击：polling / 搜索探测、
  recovery / teardown（离房、quick exit、遮挡清理）、helper 自带点击循环且无 policy 参数（`ui_click*` 系，本轮不扩 API）、
  动态 OCR / 区域 / 颜色状态目标（fresh confirm 不能重新得到等价 target）、受保护业务（KekkaiUtilize harvest / D017 / 满级替换）、
  低频冷门流程、0 调用方的死代码。
- **KEEP_SPECIAL = 已有独立 timing owner**：Settlement / 奖励阶段弹窗（含由 `_handle_reward` 调用的「再次邀请」
  `check_and_invite`）、Battle Entry 语义但不是 FIRE_SPECIAL owner 的点击（GeneralBattle「准备」`I_PREPARE_HIGHLIGHT`、
  Orochi wild、伪神降临 / 大富翁旧流程——未来按 FIRE contract 收口，不能给普通 policy）、防挂机节拍（房间表情）、
  业务 pacing（RealmRaid `RR_TARGET_PACING`）、随机安全区点击。
- **NEEDS_C 保持原样**：静态无法判断时效 / 协作节奏的动作不猜——GeneralInvite 队员 `check_then_accept`（5）、准备页
  「不同御魂」弹窗（2）。
- **Navigator 禁止全局注入**：`GameUi._execute_action` 是所有 transition / hook 的通用执行器，保持 IMMEDIATE；以后要给页面级
  入口加 NAVIGATION，只能逐 edge 在动作本身声明，GameUi 模块不 import `interaction_policy`。
- **迁移只用现有 API**：`appear_then_click(target, ..., policy=...)`，不另写 random_delay / screenshot / appear / click，
  不在 policy 点击之前叠本地 `random_delay`；FIRE 目标点击永不带普通 policy。
- **本轮迁移 7 个**：GeneralInvite `_open_invite_panel_if_needed` 的 `I_ADD_*` ×4 → NORMAL（房间开邀请面板，Timer(1) 节流 +
  Timer(5) 预算）；GeneralBattle `switch_preset_team` 的 `I_PRESET` / `I_PRESET_WIT_NUMBER` → NORMAL、`I_PRESET_ENSURE`
  → CONFIRM（准备页、Timer(4) 预算；OCR 兜底 `O_PRESET*` 与颜色选择保持立即）。`RR_AGAIN_CONFIRM_DELAY` 仍不替换。
- 审计范围外其余 master 模块点击未逐点审计，保持 legacy 立即点击，后续按模块批次推进；WeeklyPurchase 按用户决定
  EXCLUDED_BY_PROJECT_DECISION（不做 Reaction Policy / FIRE 改造、不进 backlog、L2 自动审计跳过）。

**补记（2026-09-21，L2 Stage C1-A1：采用 C0 复核对首批 4 处的 MIGRATE 结论）**：

- **正式采用的部分**：C0 对 Dokan `priority_enter_dokan`（NORMAL）、Pets `_feed` 返回按钮（NAVIGATION）、SixRealms `refresh_store`（CONFIRM）、`choose_and_enter_island`（NORMAL）的 MIGRATE 结论，且只做「给现有
  `appear_then_click` 加 `policy=`」——不改 L1 / `interaction_policy` / `Control` / `base_task`，不增删业务重试。**C0 其余建议（MIGRATE 6 / KEEP_* 7 / NEEDS_C 7）尚未实施，不是已生效决定**，登记册对它们仍按原分类。
- **timing owner**：每个点击仍是「一个 reaction owner」——就是这个 `policy`；点击后的状态判定 / 重试 / 超时仍归各自的外层（Dokan = Navigator `Timer(6.0)` 预算与边重试；Pets = `goto_page(page_main)` 收口；
  SixRealms 刷新 = `buy_skill` 的 `break`；岛屿 = `run_on_*` 每轮重扫）。fresh confirm 失败 = 本次零点击、返回 `False`、不重试、不改点别的目标。
- **已知语义变化（不掩盖）**：reaction 计入 Navigator 的 6 秒墙钟预算（成功 attempt 多耗约 1 秒，预算内可重试次数变少，持续 fresh 失败时仍正常超时）；policy 路径的 interval 计时器在点击后才重置。
- **登记册规则**：完成迁移的点位必须在 `dev_tools/click_callsite_register.py::C1_MIGRATED` 逐点登记（文件 / 函数 / 目标 / policy），生成时与源码核对，对不上直接报错；basis=`c0`。`policy=` 只允许出现在人工审计文件或 `C1_MIGRATED`。

**补记（2026-09-21，L2 C0 分类收口：正式归档 C0 24 点，区分「技术分类」与「开发排期」）**：本补记取代上一条里「C0 其余建议尚未实施，不是已生效决定」的临时表述。

- **C0 结论的正式地位**：C0 对原 24 个 NEEDS_C 的逐点结论（建议 MIGRATE 10 / KEEP_IMMEDIATE 3 / KEEP_SPECIAL 4 / NEEDS_C 7）已在 `dev_tools/click_callsite_register.py` 以 `C1_MIGRATED`（已实施 4）与 `C0_TRIAGE`（其余 20）逐点归档，生成时与源码核对。其中 **KEEP_IMMEDIATE（DemonRetreat `run` 失败恢复 / Quiz `_deal_quiz` 倒计时敏感 / SixRealms `open_shop` 超时恢复）与 KEEP_SPECIAL（Buy `buy_more` 两次连续加量共享业务节奏、`switch_moon_sea_shikigami` 的 Navigator 单次进入 hook、`_mark_peacock_boss` 首领标记专用事务）是已生效的技术决定**：它们已有明确 timing owner，不属于迁移积压，不得再当作 NEEDS_C 或自动加 reaction；`buy_more` 两次点击之间的 0.5 秒等待、首领标记的 0.3 秒 settle 是各自事务的节奏，不拆成两次 NORMAL。
- **技术分类与开发排期分开记录**：`decision`（互斥、可加总）表达技术判断；`dev_status`（COMPLETED / DEFERRED / NOT_APPLICABLE）表达是否开发。**`DEFERRED` 是用户的排期决策，不是技术完成，也不是永久禁止**：`decision=DEFERRED`（6 点：Duel 练习入口 ×2、SixRealms 商店 ×4）= C0 技术建议为 MIGRATE、用户决定暂缓，原建议（NORMAL / CONFIRM）保留供日后参考，代码里仍是立即点击；`decision=NEEDS_C` + `dev_status=DEFERRED`（7 点：GeneralInvite `check_then_accept` ×5、GeneralBattle `_handle_prepare` ×2）= 技术上需要 Level C 依据、且用户暂缓，**不得自动迁移**，也不得改判为 ALREADY_L2 / KEEP_IMMEDIATE。
- **暂缓点位的边界**：不添加 policy、不改 Duel 的 `or` 短路与 2 秒页面等待、不改 SixRealms 商店的 coin 更新条件与 readiness timeout；GeneralInvite 的接受邀请是共享事务（逐按钮 reaction 会重复等待、队长秒开有时效风险、接受循环缺墙钟上限），日后重启须先设计事务级 reaction 与有界状态确认；GeneralBattle 准备页是 FSM（受准备倒计时影响、不能干扰组队就绪 / 进入战斗），与 Settlement 独立。FIRE 与 Settlement 仍归各自专用 FSM，不受普通 policy 影响。
- **统计口径**：全仓 1092 / 最初人工审计 179 / C0 复核 24 / C1-A1 实施 4 是四个口径，不可混用；basis（决定来源，互斥）与 `c0_reviewed`（是否经 C0 复核）也是两个维度，不可相加。

---

**补记（2026-09-18，L2-3B FIRE Batch A：Battle Entry 正向确认契约铺到 Orochi 野队 / EternitySea / FallenSun / Sougenbi）**：

> **master 集成说明（2026-09-21）**：Orochi 野队 `_fire_orochi_wild` 按项目决定**未集成**（野队 `run_wild` 保持原内联点击，不启用 / 不扩展）；EternitySea / FallenSun / Sougenbi 三条已集成。下文关于 Orochi 野队的叙述是 worktree 历史，以本说明为准。

FIRE 分节与 L2-1 的「FIRE owner 自己拥有 reaction」**不变**，本补记只把旧式「连点直到按钮消失」的四条入口收口，并把契约写实：

- **Battle Entry 契约**：Pre-State → FIRE Reaction（本任务 `fire_reaction`，每 attempt 独立采样）→ fresh screenshot + 重新确认
  ready → 一次 `appear_then_click(FIRE, interval=0)`（不带 policy / confirm_delay）→ 正向 Battle Entry → 有界重试 / 显式失败。
  点击后状态至少区分 ENTERED（准备 / 战斗页）/ STILL_READY（下一 attempt，重新采样 reaction）/ TRANSITIONING（只等不点）/
  ABNORMAL（结果 / 奖励页残留、房间失效）/ TIMEOUT；unknown 不得立即重点。
- **成功判据**：「FIRE 按钮消失」永远不是成功。正向 = `tasks/Component/fire_battle_entry.py::is_new_battle_entry`
  （`I_PREPARE_HIGHLIGHT` / `I_PREPARE_DARK` / `I_BATTLE_INFO`；进入准备页即 FIRE 成功，准备按钮与后续战斗归 GeneralBattle）；
  宽 `is_in_battle()`（含 WIN / REWARD）与含 `I_BUFF` / `I_PRESET` 的 `is_in_prepare()` 不作新 FIRE 的成功判据。
- **retry / timeout owner = FIRE owner**：有限 attempt + 总时长 `Timer` + 点击后确认窗口，`interval` 不是上限；失败返回 caller，
  caller 回自己的外层循环重新判页，不计战斗次数，不清 click record（`GameTooManyClickError` 兜底保留）。
- **FIRE owner 现为 11 个（master 集成后 10 个：不含 `Orochi._fire_orochi_wild`）**：L2-1 的 7 个 + `Orochi._fire_orochi_wild` / `EternitySea._fire_eternity_sea_alone` /
  `FallenSun._fire_fallen_sun_alone` / `Sougenbi._fire_sougenbi`。EternitySea / FallenSun / Sougenbi 新增 `fire_reaction` 组；
  EternitySea / FallenSun 的 `run_invite` 也改为传本任务 `fire_reaction`（不再用公共默认）。
- 其余旧式入口按 L2-3A 批次（B / C / D / E / F）逐批收口，不做全仓通用 FSM；GeneralBattle「准备」（Batch C）先设计再实现。

---

## D002 稳定性基础层不因行为随机化而修改

状态：Accepted
日期：2026-08-30

背景：项目做过一轮「输入层随机化」审查。部分固定值（截图间隔、Timer 超时、minitouch 协议等待、retry 退避）看起来「机械」，但它们是可靠性时序，不是拟人化参数。

决定：以下内容属于稳定性基础，**不得**因为「让行为看起来更随机 / 更像人」而修改：
- `module/device/screenshot.py` 的 `_screenshot_interval = Timer(0.1)` 与 `screenshot_interval_set` 的 `limit_in` 限幅。
- `module/base/timer.py` 的 `Timer`（所有 `limit` 为常量、无抖动接口）。
- 协议等待、后端缓冲、RPC 轮询、重试退避、FSM 超时。
- minitouch 的握手 / 连接 / `minitouch_send` 尾部固定等待。

原因：这些决定识别可靠性和卡死检测的正确性；随意随机化会引入难复现的稳定性问题，且收益（分布形态）远低于代价。

禁止 / 注意事项：任务级休息（FatigueManager）与输入协议时序是**两种不同的等待**，不要混为一谈。要改这些必须有明确的可靠性理由 + 真机验证。

相关文件：`module/device/screenshot.py`, `module/base/timer.py`, `module/device/method/minitouch.py`。

---

## D003 `Control.swipe` 的 `duration` 是后端相关参数，不是通用滑动时长

状态：Accepted
日期：2026-09-01

背景：`Control.swipe(p1, p2, duration=...)` 的 `duration` 在不同后端语义不同。曾尝试「因为 minitouch 不用就删掉调用方的 duration」，但这对 adb / uiautomator2 是真实行为变化，已收回。

决定：
- 保留 `Control.swipe` 的 `duration` 形参和所有后端分支不变。
- 消费边界（源码确认）：
  - **消费**：`swipe_uiautomator2(p1, p2, duration)`、`swipe_adb(p1, p2, duration)`（后者先 `duration *= 2.5`）。
  - **忽略**：`swipe_minitouch(p1, p2)`、`swipe_scrcpy(p1, p2)`、`swipe_window_message(startPos, endPos)`。
- `Control.swipe` docstring 已注明该边界。
- 调用方（如 `RyouToppa.flush_area_cache`）传随机 `duration` 保持原样——在默认 minitouch 环境下不影响真实滑动时序，在 adb / uiautomator2 环境下才有实际语义。

原因：删除会在非默认后端造成不可静态验证的行为变化；`duration` 本身不是坏设计，只是接口说明缺失。

禁止 / 注意事项：**不实现 minitouch 的 duration 支持**（不通过 duration 缩放 MOVE 间隔 / 数量 / 轨迹速度 / 总时长），那会改变真实设备行为，必须真机验证。

相关文件：`module/device/control.py`（`Control.swipe`），`module/device/method/{minitouch,adb,uiautomator_2,scrcpy}.py`, `module/device/method/windows_impl.py`, `tasks/RyouToppa/script_task.py`（`flush_area_cache`）。

---

## D004 BehaviorTrace v1 的范围与边界

状态：Accepted
日期：2026-09-01

背景：为后续 State→Action→Verify、List Changed/Stable、WaitPolicy、RetryPolicy、Recovery 等改造需要「改造前 vs 改造后」的运行数据，新增只读观测层 `module/behavior_trace.py`。

决定：
- **默认关闭**（`config.script.optimization.behavior_trace_enable = False`）。关闭时 `record()` 首行返回，不建目录、不开文件、不构造事件。
- v1 只记录两类事件：`ACTION`（click / swipe / long_click 在 `Control` 层正常返回后，`result` 恒为 `ok`）、`TASK`（`Script.run` 一个 episode 的耗时与结果）。
- **不记录**：screenshot、`appear()` / OCR、`Timer.reached()`、minitouch 每个 MOVE、每条 adb 指令、每个 while tick。
- **不实现**（留给对应架构阶段）：`WAIT` / `ERROR` / `RETRY` / `TIMEOUT` / `RECOVERY` / `TRANSITION` / `ACTION_START/END` 事件、`ACTION result=error`、`timed()` context manager、后台线程 / 队列 / SQLite、完整 State Enum / FSM。
- 配置来源由 `Script.__init__` 一次性 `configure_behavior_trace(config_name, enabled)` 注入，`BehaviorTrace` 不 import `Config`，进程生命周期内 enable 稳定（不动态 reload）。
- 任何内部异常都被吞掉并自禁用（`_broken`），绝不抛给业务、不改 click/swipe/long_click 返回值。
- 输出 `log/behavior/<config>_<日期>.jsonl`，每 config 独立文件（spawn 多进程），`buffering=1` 行缓冲。

原因：观测层必须「只记录、不干预」；范围收窄到「业务动作」而非「所有底层细节」，避免为填日志模型反向要求所有 Task 先改架构。

禁止 / 注意事项：不要扩 v1 事件模型；不要给 `Control` 为 Trace 增加 try/except 或改异常传播；后续 `WAIT` 等事件由对应 Policy 层各自 `record(...)`，不改 BehaviorTrace 本身。

**补记（2026-09-07，Swipe Trajectory Backend）**：给 `action='swipe'` 的 ACTION 扩了 `extra`，**事件模型不变**——仍只有 `TASK` / `ACTION` 两类，`result` 恒 `ok`（执行成功后记录），失败仍不写 ACTION（无 swipe 专用第二套 error schema）。
- **一次 swipe = 一个 ACTION，轨迹点整体嵌进 `extra.trajectory`**（`[[x, y, dt_ms], ...]`，最多 ~80 点，见 D018 `max_points`）。**严禁**把 `TouchSwipeModel` 的每个 MOVE 写成独立 ACTION，**严禁**新增 `MOVE` / `SWIPE_POINT` / `FRAME` 事件级别。
- `Control.swipe_trajectory`：`extra = {start_x, start_y, end_x, end_y, point_count, trajectory}`。`trajectory` 直接来自传给该方法的这一份点列（executor 的真实 commanded 输入），**不按 start/end 重新 `generate`、不还原贝塞尔**。`dt_ms` 原样保留、语义仍是 D018 的「MOVE 到该点后 `wait(dt)`」，本轮不重新解释、不新增 `duration_ms`。
- `Control.swipe`（legacy 端点滑动）：`extra` 只带 `start_x/start_y/end_x/end_y` + `point_count=2`，**不带 `trajectory` 键**（没有完整轨迹就不伪造，避免下游误认为执行过某条曲线）。
- 关闭态自然规避：新增 `BehaviorTrace.is_recording()`（`enabled and not _broken`，语义等价 `record()` 首行短路），`Control.swipe_trajectory` 仅在 `is_recording()` 为真时才组装那几十个点的 `extra`。这是读访问器、不改 `record()` 契约、不是 v2 事件模型。
- BehaviorStats 侧记录时**不塞 K3 的 `changed/stable/elapsed/diff`**（那走 FrameWait 日志），**不塞 K4 的 actual_scroll_dy / scroll_gain**（BehaviorTrace 记的是 commanded input，不是实际 UI 位移）。

相关文件：`module/behavior_trace.py`, `module/device/control.py`（`Control.swipe` / `Control.swipe_trajectory` / `_swipe_trajectory_extra`），`script.py`（`Script.run` / `Script.__init__`），`tasks/Script/config_optimization.py`，`tests/test_behavior_trace.py` / `tests/test_control_swipe_trajectory.py`。

---

## D005 BehaviorTrace 的任务归属由 `Script.run` 的 `finally` 闭环

状态：Accepted
日期：2026-09-01

背景：`ACTION` 事件的 `task` 字段来自 `BehaviorTrace._task`，由 `Script.run` 通过 `set_task` 维护。需要保证一个任务 episode 结束后一定清空，否则任务之间的 Control 动作会错误继承上一个任务名。

决定：
- `Script.run` 进入时 `trace.set_task(command)`，`finally` 里先 `trace.record('TASK', target=command, ...)` 再 `trace.set_task('')`。
- 顺序固定为 **先 record TASK、后 set_task('')**，保证 TASK 事件带正确任务名。
- 所有出口（正常完成 / `_handle_task_exception` 返回 True/False / `exit(1)` 引发的 SystemExit）都经过 `finally`，`set_task('')` 一定执行。
- 任务之间（下一次 `Script.run` 之前）的 Control 动作正确得到 `task: ""`。

原因：`finally` 是唯一能覆盖所有异常出口的位置；进程内单例保证 `loop` / `run` / 中间动作读写同一 `_task`。

禁止 / 注意事项：不要把 `set_task('')` 移到 `record` 之前；不要在 `Script.run` 的 `set_task(command)` 之前加提前 return。

相关文件：`script.py`（`Script.run`），`module/behavior_trace.py`。

---

## D006 `RuleSwipe` 只提供端点，不提供轨迹

状态：Accepted
日期：2026-09-01

背景：`module/atom/swipe.py` 的 `RuleSwipe.trace()` 及 `is_default_mode` / `is_vector_mode` 全仓零调用方，且 `trace()` 自身已损坏（对 4 元组解 2 个变量会 `ValueError`）。真实滑动轨迹由各后端自己生成（minitouch 的 `insert_swipe`、window_message 的内联 `BezierTrajectory`、adb/uiautomator2 的系统命令）。

决定：
- `RuleSwipe` 只保留 `__init__` 与 `coord()`（端点 = 起点 `roi_front` / 终点 `roi_back` 各用 `random_center_point_in_roi` 中心偏置随机）。
- `trace()` / `is_default_mode` / `is_vector_mode` 及只服务它们的 import（`random` / `math.dist` / `cached_property` / `module.atom.cBezier.BezierTrajectory`）已删除。
- `module/atom/cBezier.py` 变为孤儿文件，本轮保留（删整个模块超出「清死路径」边界），是否删除留作独立决定。
- `module/base/cBezier.py` 是**另一个文件**，被 `module/device/method/windows_impl.py:swipe_window_message` 使用，**不能动**。

原因：轨迹生成属于后端职责；`RuleSwipe.trace()` 是废弃的重复实现，留着会误导「滑动轨迹形状已随机化」。

禁止 / 注意事项：不要为了「统一轨迹」在 `RuleSwipe` 重新加轨迹生成；不要动 `windows_impl.py` 的内联贝塞尔。

相关文件：`module/atom/swipe.py`, `module/atom/cBezier.py`, `module/base/cBezier.py`, `module/device/method/windows_impl.py`。

---

## D007 公共随机统一走 `module/base/utils/random.py`

状态：Accepted
日期：2026-08-30

背景：项目历史上混用 `random` / `np.random` / 各处自建 `SystemRandom`。已收敛低层输入与 ROI 公共路径到一个模块级 `SystemRandom`。

决定：
- 新增业务随机逻辑优先复用 `module/base/utils/random.py` 的 `random_delay` / `random_int` / `random_triangular` / `random_point_in_roi` / `random_center_point_in_roi`。
- 不无理由新建 `SystemRandom` 实例，不无理由重新引入普通 `random` / `np.random`。
- 已存在的未迁移部分（`module/atom/swipe.py` Bezier 已随 D006 删除；`module/device/method/minitouch.py:insert_swipe` 控制点仍用 `np.random`；`RyouToppa.flush_area_cache` 滑动坐标用 `random.randint`）按既有决定保留，不为形式统一做无关重构。

原因：统一随机源消除 `random.seed()` / `np.random.seed()` 全局污染、提升可测试性与确定性。**注意**：`np.random → SystemRandom` 在同一 ROI 上是同一均匀分布，不改变任何可观测分布——属代码质量改进，不是反检测改进。

禁止 / 注意事项：不要把这次迁移记为「降低特征相似度」的成果。

相关文件：`module/base/utils/random.py`, `module/atom/*.py`, `module/device/method/minitouch.py`。

---

## D008 不无依据重写 GeneralBattle 的 Page FSM

状态：Accepted
日期：2026-08-29

背景：`tasks/Component/GeneralBattle/general_battle.py` 的 `run_general_battle` 是基于 Page FSM 的通用战斗，被大量任务复用，人工融合并验证过。

决定：不要因为「看起来复杂」「想换个写法」而重写整个 `run_general_battle` / `gb_page_handle_dict` / `BattleContext` 结构。局部修 Bug 或按任务覆写 `PREPARE_CLICK_DELAY_RANGE` / `SETTLEMENT_CLICK_INTERVAL_RANGE` / `_exit_matcher` 可以。

原因：该 FSM 每轮 `screenshot` + `detect_page_in` 重判当前页，是状态驱动的正确形态；重写风险高、必须真机验证、收益不明。

禁止 / 注意事项：不重新加入 `reaction_delay` / `CLICK_REACTION_DELAY` / BaseTask 全局自动等待。

相关文件：`tasks/Component/GeneralBattle/general_battle.py`。

---

## D009 已确认保留的 upstream 业务模块不随意回退

状态：Accepted
日期：2026-08-29

背景：整合 `upstream/self` 时，部分业务模块（Chess、KekkaiUtilize、Costume、CostumeShikigami、BondlingFairyland、Sougenbi 等）经审查后直接保留 upstream 版本。

决定：不因为整合完成后再次看到与本地历史的差异，就把这些模块回退。要改必须有明确缺陷依据。

原因：这些是有意的保留决定，反复回退会制造 merge 噪声。

相关文件：见 `docs/AI_CONTEXT.md` §5。

---

## D010 `frame_state` 组件的语义与解耦边界

状态：Accepted
日期：2026-09-01

背景：`module/atom/frame_state.py`（T4-1）为「列表状态驱动」改造提供 `changed` / `stable` 基础语义。以下语义是刻意选择，后续改造 / 接入时不要「顺手改回去」。

决定：
- **`changed` 锁存**：`FrameStateDetector.changed` 表示「自上一次 `reset()` / 首帧以来，是否出现过『相对基线差异 >= changed_threshold』」。一旦为 True 就保持，直到下一次 `reset()`；即使画面又接近 / 回到基线也**不**自动退回 False。原因：未来完整流程是「滑动前 baseline → 列表移动 → `changed=True` → 列表停下 → `stable=True`」，若 `changed` 会因当前帧又接近基线而回退，状态语义就不稳定。
- **`stable` 基于相邻帧、与 baseline 无关**：连续 `stable_frames` 帧满足「相邻帧差异 <= stable_threshold」才 `stable=True`；任何一次相邻帧明显变化都把 `stable_count` 清零。`changed` 与 `stable` 是两个独立概念——「一直静止」会得到 `changed=False, stable=True`（画面稳定但没证明滑动真的产生了变化）。业务层**不能**把 `stable=True` 直接解释成「swipe 成功」。
- **判定阈值必须由调用方显式传入**：`changed_threshold` / `stable_threshold` / `stable_frames` 无默认值。`pixel_threshold`（`DEFAULT_PIXEL_THRESHOLD = 15`）是纯算法参数、有通用保守默认值，但同样**不代表任何游戏页面的最佳参数**。真机窗口打开后才有依据确定各任务的真实阈值 / ROI / `stable_frames`。
- **与设备 / 任务解耦，永不做轮询**：`frame_state.py` 只依赖 `numpy` 与 `module.base.utils` 的 ROI 工具，**不**依赖 Device / BaseTask / ScriptTask / Timer / OCR / BehaviorTrace，**不**截图、**不** `sleep`、**不**做 timeout。`detector.update(frame)` 只推进纯状态。设备截图轮询与超时是上层（未来 WaitPolicy / 设备等待层）的职责，不要为了方便把这些塞进本组件。
- **ROI 复用项目既有 `(x1, y1, x2, y2)` 约定**（与 `module.base.utils.crop` / `area_*` 一致），越界 clamp（复用 `area_limit`），不引入第二种坐标格式；组件本身不得硬编码任何任务 ROI。

禁止 / 注意事项：不要给 `frame_state` 加 `wait_list_changed` / `wait_list_stable` 这类内部截图 / 轮询 / timeout 的包装；不要让它 import BehaviorTrace 或新增 `WAIT` 事件（BehaviorTrace v1 契约仍只有 `ACTION` / `TASK`，见 D004）。

相关文件：`module/atom/frame_state.py`, `tests/test_frame_state.py`, `module/base/utils/utils.py`（`area_limit` / `image_size`）。

---

## D011 点击统计后端只按需读 JSONL，不做后台聚合

状态：Accepted
日期：2026-09-01

背景：OASX「配置详情 → 统计 → 点击分布」页面需要某 config 某日期的 click / long_click 坐标。BehaviorTrace 已按 `log/behavior/<config>_<date>.jsonl` 落盘。

决定：
- **记录轻量化**：OAS 正常运行时，点击统计的唯一新增成本是 `Control.click` / `Control.long_click` 在已有 `record('ACTION', ...)` 的 `extra` 里多写 `x` / `y` 两个整数。不新增事件类型（仍只有 `ACTION` / `TASK`，见 D004）、不新增 `coord()` / 随机 / screenshot、不改点击顺序与异常传播。
- **坐标语义**：记录的 `x` / `y` 是 `ensure_int` 之后、真正提交给控制后端执行的**最终坐标**，不是 ROI 中心 / 模板原坐标 / RuleImage 原始框。
- **统计按需化**：只有 HTTP 接口 `GET /stats/{script_name}/behavior/clicks?date=` 被请求时，才打开当天单个 JSONL 逐行读一次、返回、关闭。**不启动后台统计线程、不定时扫描、不实时聚合、不建数据库、不开 SSE**。接口未被请求时点击统计零额外后台 CPU / 内存。
- **前端渲染化**：接口一次返回当天全部点击点，任务筛选 / 时间连线 / hover tooltip / 热力图 / 聚类全部由 OASX 前端本地完成。后端不做网格聚合 / 密度 / 轨迹平滑。`points` 保持 JSONL append 顺序（即动作时间顺序），`tasks` 按首次出现顺序。
- **只存 x/y，不存截图**：JSONL 只记录坐标；`screen`（逻辑分辨率 1280×720）在响应顶层返回一次，不在每条记录重复；点击统计不保存任何截图。
- **兼容与容错**：旧 JSONL（无 `extra.x/y`）跳过不报错；单行坏 JSON / 缺字段 / 类型错误跳过并计入 `skipped_lines`；文件不存在 / 空返回空结果不报 500。
- **`{script_name}` 永远是完整 config_name**：API 路径里的 `{script_name}` 就是用户 `Script(config_name)` 用的那个名（`oas1` / `test_01` / `account_group_1`），Reader 用项目统一的 `ConfigManager.validate_config_name(allow_template=False)` 校验并**原样**拼进 `log/behavior/<config>_<date>.jsonl`。**不做** `log_service` / `log_stats` 的 `normalize_script_name` 那种「按 `_` 截首段去运行时后缀」——那个 helper 是为 `<date>_<script>.txt` 人读日志名 / error 目录名解析设计的；config_name 本身允许含 `_`（`validate_config_name` 只禁 `.` / `/ \ : * ? " < > |` / 控制字符），截断会读到别的 config 的文件（2026-09-01 曾按 `_` 截断，已收口）。`log_stats._normalize_script_name` / `log_service.normalize_script_name` 各自服务 `.txt` 日志语境，不受影响、不要动。
- **只允许固定目录**：Reader 校验用 `ConfigManager.validate_config_name`（拒 `.` / 路径字符 / 控制字符），`_behavior_file_path` 再用 `resolve().relative_to(log/behavior)` + `path.name == 期望文件名` 机械兜底；router 层也先跑一遍 `validate_config_name`（非法 → 422）与既有 `_parse_target_date`。

~~本轮范围：只做 click / long_click。**不记录 swipe / drag 轨迹、minitouch MOVE**~~（2026-09-01 第一版）——**2026-09-07 已扩 swipe 轨迹，见下方补记**。

禁止 / 注意事项：不要为了「更快」把 JSONL 解析改成后台常驻聚合 / SQLite；不要让接口每切一次 task 就重新读文件；不要在 JSONL 每条记录里塞 width/height 或截图。

**补记（2026-09-07，Swipe Trajectory Backend——additive extension，Backend done / OASX 前端 pending）**：同一个 `GET /stats/{script_name}/behavior/clicks` 端点、同一个 `read_behavior_clicks` reader 扩出 swipe。**不另造 `/swipe-stats`。**
- **记录轻量化不变**：`Control.swipe_trajectory` 在已有的 `record('ACTION', action='swipe', ...)` 上多写 `extra`（端点 + `point_count` + 完整 `trajectory` 点列，见 D004 补记）；`Control.swipe` 多写端点。不新增事件类型、不新增后台线程。
- **按需读不变**：reader 仍单次逐行读当天单文件。新增：把 `action='swipe'` 的 ACTION 解析成 `swipes[]` 条目（`{task, action, target, ts, start:[x,y]|null, end:[x,y]|null, point_count, trajectory:[[x,y,dt],...], elapsed_ms?}`）。
- **四层等值 AND 过滤**：`date AND task AND interaction_type AND target`。`interaction_type ∈ {all, click, swipe}`（大小写不敏感，非法 → 400 / router 422）：`all` = 点击 + 滑动；`click` = `click`/`long_click`；`swipe` = `action='swipe'`（**不含** drag / 其它）。`target` 对 click 与 swipe 用**同一个参数、同一语义**（等值匹配记录的 `target`），未传 = 全部。
- **计数**：一条 swipe 无论 `trajectory` 多少点，`summary.swipe_count` 只 +1。旧 `summary.total` / `click_count` / `long_click_count` / `task_count` / `skipped_lines` 语义**不变**（`total` 仍是 click 点数）。新增 `swipe_count` / `filtered_count`（当前过滤下命中的 ACTION 数）/ `malformed_trajectories`。
- **向后兼容（additive）**：响应旧键（`config` / `date` / `screen` / `summary` 旧计数 / `tasks` / `points`）名称·类型·语义全部保留；旧 OASX 忽略新增 `swipes` / `available_tasks` / `available_targets` / `filter` / 新 summary 计数即可继续工作。旧 JSONL（只有 click、swipe 无 `trajectory`、坏行）照常读；**单条坏 `trajectory` 只降级该条**（保留可解析点或置 `[]`，计入 `malformed_trajectories` + 惰性 warning），**绝不 500**。
- **坐标系**：`trajectory` / `start` / `end` 都是原始 1280×720 屏幕坐标，后端不做任何 Y 翻转 / 缩放 / DPI 变换（前端复用现有 click 坐标变换）。**不做**轨迹抽稀 / Douglas-Peucker / 贝塞尔压缩（`max_points ≤ 80`，数据量可控）。
- **下拉候选 metadata**：`available_tasks`（排除 `task` 维、按 `interaction_type` + `target` 过滤后 distinct 的 task）、`available_targets`（排除 `target` 维、按 `task` + `interaction_type` 过滤后 distinct 的 target），供前端下拉动态刷新且选定后不塌缩成自身。
- **click 路径 ≠ swipe 轨迹**：OASX「显示路径」= 多个 click event 之间的时序连线；swipe `trajectory` = **一个 ACTION 内部**的 MOVE 路径。两者是不同结构，后端分别放在 `points` 与 `swipes`，不混进同一个 `path` 字段。

相关文件：`module/device/control.py`（`Control.click` / `Control.long_click` / `Control.swipe` / `Control.swipe_trajectory`），`module/behavior_trace.py`（`is_recording`），`module/server/behavior_stats.py`, `module/server/stats_router.py`, `tests/test_behavior_click_stats.py`。

---

## D012 FrameState Wait Layer 只做「取帧 + 轮询 + 有限 timeout」

状态：Accepted
日期：2026-09-01

背景：`module/atom/frame_state.py`（D010）是纯帧差算法，刻意不截图 / 不 sleep / 不做 timeout。要真正驱动「滑动后等列表停下」这类流程，需要在它之上加一层设备无关、可单测的有限等待。该层为 `module/base/frame_wait.py` 的 `wait_for_changed_and_stable(...)`（会话内称 T4-2）。以下边界是刻意选择。

决定：
- **模块位置在 `module/base/` 不在 `module/atom/`**：`atom` 层「不负责设备轮询 / 超时」（ARCHITECTURE §2、D010），`module/base/` 已是控制流基础设施所在（`retry.py`）。`base → atom` 单向 import，`module/base/__init__.py` 只 import `.utils` / `.grids`，`frame_wait` 不被它加载，无环。
- **只负责三件事**：调用注入的 `frame_provider` 取帧、把帧喂给一个内部 `FrameStateDetector`、按注入的 `clock` 计时并在 `timeout` 到达时停止。**不做** retry、不做 recovery、不做「失败后换动作」、不内置任何业务阈值——那些是调用方（未来的 Task / WaitPolicy）的职责。
- **复用 `FrameStateDetector`，不维护第二套 `changed` / `stable`**：本层只读 detector 的结果，`changed` 锁存、`stable` 相邻帧语义、阈值校验全部沿用 D010。
- **`baseline` 由调用方传入**，本层不自截。正确链路是 `baseline = screenshot() → action() → wait(baseline=baseline)`；本层自截会把 baseline 取在动作之后，语义错误。
- **依赖全部可注入**：`frame_provider: Callable[[], np.ndarray]`（生产传 `self.device.screenshot`，测试传 fake，无 Device 硬依赖）；`clock: Callable[[], float]`（默认 `time.monotonic`；项目 `Timer` 内部用 `time.time()` 不可 mock，故本层单独走注入 clock 做确定性 timeout 测试）；`sleeper: Callable[[float], None]`（默认 `time.sleep`，仅 `poll_interval > 0` 时调用）。
- **`poll_interval` 默认 `0.0`**：生产 `frame_provider`（`device.screenshot`）已有 `_screenshot_interval` 节流（D002），不叠第二次固定 sleep。
- **阈值必须显式传、无业务默认**：`changed_threshold` / `stable_threshold` / `stable_frames` 直接透传给 `FrameStateDetector` 并由它校验（不写第二套校验）。`pixel_threshold` 沿用 `frame_state.DEFAULT_PIXEL_THRESHOLD`。
- **`timeout` 必须是有限正数**：非正数 / bool / 非数值 → `ValueError`。没有 `while True` 无界循环；另有 `_MAX_POLLS` 兜底，注入的 `clock` 不推进时抛 `RuntimeError` 而非死循环。
- **超时返回结果、绝不抛异常**：到 `timeout` 时返回 `FrameWaitResult(timed_out=True, ...)`，由调用方决定后续。
- **成功严格等于 `changed and stable and not timed_out`**：`FrameWaitResult.success` 只在三者同时满足时为 True。「一直静止」得到的 `stable=True`（`changed=False`）**不算成功**（与 D010 一致）。结果能区分：成功 / 失败 A「从未变化」（`changed=False, timed_out=True`）/ 失败 B「变化但没稳定」（`changed=True, stable=False, timed_out=True`）。
- **异常透传、不伪装成 timeout**：`frame_provider` 抛出的异常，以及 `FrameStateDetector` 因帧为 None / 非 ndarray / shape 不一致 / 非法 ROI / 非法阈值抛出的 `ValueError`，都原样向上传播。
- **不碰 BehaviorTrace**：本层不 import `module.behavior_trace`，不产生 `WAIT` / `TIMEOUT` / `TRANSITION` 事件。BehaviorTrace v1 契约仍只有 `ACTION` / `TASK`（D004 不变）。
- **~~当前零生产消费者~~**（2026-09-04 前）→ **生产消费者（2 个，2026-09-08）**：① `KekkaiUtilize._perform_search_swipe`（2026-09-07 K3，见「补记（2026-09-07）」与 D017 K3 补记，结果参与控制流——失败 → `PassResult.ABORT`）；② `BaseTask.list_find` 翻页 settle（2026-09-08，见「补记（2026-09-08）」与 D013 补记，结果**不参与控制流**——W1 结构性 settle，取代固定 `sleep(0.8~1.3)`）。真实 ROI / 阈值 / `stable_frames` / timeout 的进一步真机标定仍是 Level C。

禁止 / 注意事项：不要给本层加 retry / 退避 / recovery（那是 T4-3 WaitPolicy / RetryPolicy 的事，`frame_wait` 只作它的一个雏形被参照，不承担其职责）；不要让它 import Device / BaseTask / Timer / BehaviorTrace；不要把 `timeout` 改成可选或允许 `None` / `inf`；不要把「超时」变成抛异常。

**补记（2026-09-07，KekkaiUtilize K3）**：`frame_wait` 得到首个生产消费者。`KekkaiUtilize._perform_search_swipe`（标准 PASS + minitouch）在 `swipe_trajectory` + `click_record_clear` 之后，用 `wait_for_changed_and_stable(baseline, self.device.screenshot, roi=SWIPE_WAIT_ROI, changed_threshold=…, stable_threshold=…, stable_frames=…, timeout=…)` 取代原来的固定 `time.sleep(2)`：
- 完全遵守本 ADR 的调用契约——`baseline` 在 swipe **前**由业务层显式 `self.device.screenshot()` 取（不复用可能被详情页污染的 `self.device.image`）；4 个判定阈值全部由 KekkaiUtilize 作 provisional 类常量显式传入（`changed 0.10` / `stable 0.02` / `stable_frames 3` / `timeout 3.0s`，注释标「需 Level C 调整」），本层无业务默认；`roi` 限 card-column（`I_U_*_6` / `I_U_EMPTY_CARD` 的 `roi_back` 包络）。
- **`poll_interval` 由 KekkaiUtilize 显式覆盖本 ADR 的全局默认 `0.0`**：`SWIPE_WAIT_POLL_INTERVAL = 0.15`（provisional，注释标「需 Level C 调整」）。本 ADR 上方「`poll_interval` 默认 `0.0`」的理由是「`frame_provider` 自带节流、不叠第二次固定 sleep」；K3 的场景是「等 MuMu 好友列表 swipe 后惯性真正停稳」——惯性微滚可能让相邻两帧差异 < `stable_threshold`，零间隔高速轮询下连续 `stable_frames` 帧会提前判 stable（甚至连抓同一渲染帧）。加一档 pacing 让这 3 帧跨越更长真实时间窗，属**检测采样 pacing**、叠在 `device.screenshot` 的 `_screenshot_interval`（~0.1s）之上，**不是恢复固定 `sleep(2)`**（settle 仍以 `changed and stable` 为准、命中即返回，不到 `poll_interval` 也不会白等）。**本 ADR 的全局默认 `poll_interval=0.0` 不改**——只是这个消费者按自己场景显式传值。
- **失败语义映射由调用方负责**（符合「retry / recovery 是调用方职责」）：`wait.success is False`（从未变化 / 变化未稳定 / timeout）→ `_perform_search_swipe()` 返回 `False` → `_run_search_pass` `return PassResult.ABORT`，交 `run_utilize` 外层 bounded recovery。**`no change` 不映射成 BOTTOM / PASS_MISS**——D017 唯一 BOTTOM marker 仍是 `I_U_EMPTY_CARD`。方法内一次 swipe → 一次 FrameWait，不做内部 retry。
- `frame_wait` / `FrameStateDetector` 本体一行未改；本 ADR 的所有边界（模块位置、不做 retry/recovery、阈值必须显式传、超时不抛、成功严格 `changed and stable`、异常透传、不碰 BehaviorTrace）全部保持。

**补记（2026-09-08，`list_find` 第 2 个消费者）**：全仓时序层审查（`docs/AI_CONTEXT.md` §4.49）把 `BaseTask.list_find` 翻页 `sleep(random.uniform(0.8, 1.3))` 迁到 `wait_for_changed_and_stable`。同样完全遵守本 ADR 调用契约——`settle_baseline` 在 swipe **前**取（`self.device.image`，`list_find` 循环里 swipe 前未再截图、干净，无需重截）；三阈值 + `timeout` + `poll_interval` 由 `tasks/base_task.py` 模块级 `_LIST_FIND_SETTLE_*` provisional 常量显式传（`changed 0.02 / stable 0.01 / stable_frames 2 / timeout 1.5s / poll_interval 0.12`，注释标 Level C 待标定 + 不当全项目通用参数 + 不照搬 K3 的 `SWIPE_WAIT_*`）；`roi` = `_list_roi_back_to_box(target.roi_back)`（每个 RuleList 自己的内容区，无全局 ROI）。**与 K3 的差异**：`list_find` 的 sleep 从来只是 W1 结构性 settle、不是成功 / 失败门，所以 `wait_for_changed_and_stable(...)` 的**返回值丢弃**——settle 成功或 timeout 都回循环顶重新识别，`max_swipe` 仍是唯一收敛边界，**不映射 BOTTOM / ABORT**（`list_find` 无到底部检测）。`frame_wait` / `FrameStateDetector` 本体仍一行未改。

相关文件：`module/base/frame_wait.py`, `module/atom/frame_state.py`, `tests/test_frame_wait.py`, `module/base/retry.py`（同层控制流基础设施先例）, `tasks/KekkaiUtilize/script_task.py`（K3 首个消费者）, `tests/test_kekkai_utilize_state.py`（`PerformSearchSwipeK3Test`）, `tasks/base_task.py`（`list_find` 第 2 个消费者，见 D013 补记）, `tests/test_list_find.py`。

---

## D013 语义等待与视觉结构等待分属两类；`list_find` 迁移必须保留动作前 baseline，收口阶段不抽 seam

状态：Accepted
日期：2026-09-01

背景：`BaseTask.list_find` 翻页后是固定 `sleep(random.uniform(0.8, 1.3))`（注释自带「待优化」），计划迁移到 `wait_for_changed_and_stable`（D012）。迁移前先做静态收口：审查真实语义 + 全部生产调用方 + 补 characterization 测试（`tests/test_list_find.py`），并判断是否现在抽一个「滑动后等待」的可替换 seam。

决定：

- **两类等待不互相替代**：
  - **语义等待**——等某按钮出现 / 某页面出现 / 某标识消失。继续用 `appear` / `wait_until_appear` / `wait_until_disappear` / `appear_then_click`。`list_find` 各调用方的**外层**循环（如 `Orochi.check_layer` 之后 `while 1: screenshot; if appear(I_CHECK_TEAM)`、`GeneralRoom.check_zones` 的 `ocr_appear` 循环、`navbar.click_and_check`）都属这类，**不**规划成 FrameState。
  - **视觉结构等待**——滑动后列表是否真的发生了变化、是否已经停稳。只有这类才对应 `frame changed + stable`。`list_find` 翻页后的那次 `sleep` 是唯一属于这类的点。
  - 不要为「统一 Wait Layer」把语义等待也塞进 `frame_wait`；也不要反过来用 `wait_until_appear` 去做「列表停稳」判断。
- **`list_find` 迁移到 `frame_wait` 必须保留「动作前 baseline」**：正确链路是 `baseline = 滑动前一帧 → swipe → wait_for_changed_and_stable(baseline=...)`（D012）。`list_find` 中滑动前可用的帧是 `self.device.image`（本轮为识别而截，不是为等待基线而截）。迁移实现必须把这一帧显式作为 baseline 传入等待层，不能让等待层自己截（那会把 baseline 取在 swipe 之后，语义错误）。
- **本轮（静态收口）不抽 seam**。理由：
  1. 一个在 `self.device.swipe(...)` 之后调用的 `_wait_after_list_swipe()`，要么签名里没有 baseline（未来接 `frame_wait` 不可用），要么隐式去读 `self.device.image`（把 baseline 藏成全局，且依赖「swipe 后到 seam 调用之间 `device.image` 未被刷新」这条**未经真机验证**的不变量）。两种都是 D012 明确要避免的「错误 seam」。
  2. 未来正确的 seam 可能需要覆盖「swipe 前取 baseline + swipe + swipe 后等待」整段，而不只是「swipe 后等待」——收口阶段无法确定边界。
  3. 真实 ROI（来自 `target.roi_back` 还是新 asset 字段）、`changed_threshold` / `stable_threshold` / `stable_frames` / timeout 全部是 Level C 真机标定项，seam 的**参数签名此刻无法定稿**。
  4. `list_find` 还有 image 模式 `swipe_pos(after=True)` 恒定 vs ocr 模式 `swipe_pos(number=1, after=result>0)` 的分叉，以及 `ocr_appear` 无结果返回 `(0,0)` 被当命中的既有瑕疵——滑动 / 等待重构会与这些交互，提前冻结 seam 边界过早。
  5. 抽一个纯转发的私有方法会改调用图（多一层 traceback、多一个 mock 点），当前零收益，违反「不做无关重构」。
- **可接受的收口产物就是**：characterization 测试（锁现状）+ 本 ADR + `docs/AI_CONTEXT.md` §4.19 的审查记录。seam 留到真机窗口打开、和真实参数一起定。

禁止 / 注意事项：迁移落地时不要用「等某按钮出现」替换 `list_find` 翻页等待，也不要把外层语义等待改成 FrameState；不要抽一个拿不到动作前 baseline 的 `_wait_after_list_swipe`；`RuleList.swipe_pos` 的翻页几何（endpoint 分布）不在迁移范围内。

**补记（2026-09-08，迁移落地）**：全仓时序层审查（`docs/AI_CONTEXT.md` §4.49）中把 `list_find` 翻页 `sleep(random.uniform(0.8, 1.3))` 迁到了 `wait_for_changed_and_stable`，`list_find` 成为 FrameWait 第 2 个生产消费者（K3 之后）。落地方式与本 ADR 一致，并回应了「不抽 seam」的 5 条理由：

- **不抽独立 seam**——直接在 `list_find` 循环体内替换那一行（多一层转发的顾虑第 5 点不触发）。
- **动作前 baseline**——`settle_baseline = self.device.image`，取在 `swipe` **之前**。2026-09-08 复核：`list_find` 循环里 `self.screenshot()` → `image_appear`/`ocr_appear` → `swipe_pos` → `self.device.swipe` 之间**没有再截图**，`self.device.image` 在 swipe 时仍是那一帧、干净（不像 K3 需重截），所以「swipe 后 `device.image` 未刷新」那条不变量对 `list_find` 是静态可证的，理由第 1 点在此消解。
- **ROI**——`_list_roi_back_to_box(target.roi_back)`（每个 RuleList 自己的内容区 `(x,y,w,h)` → `(x1,y1,x2,y2)`），**无全局 ROI**（理由第 3 点的 ROI 项）。
- **阈值 provisional**——模块级 `_LIST_FIND_SETTLE_*`（`changed 0.02 / stable 0.01 / stable_frames 2 / timeout 1.5s / poll_interval 0.12`），标注「Level C 待标定、不当全项目通用参数、K3 的 `SWIPE_WAIT_*` 是卡列表专用不照搬」。理由第 3 点的「参数此刻无法定稿」仍成立——但因为 **FrameWait 结果不参与控制流**（见下）而降级为「Level A/B 接线 + Level C 标定」，不再是迁移阻断项。
- **结果不参与控制流**——`wait_for_changed_and_stable(...)` 的返回值**丢弃**：settle 成功或 timeout 都一样回循环顶 `self.screenshot()` + 重新识别，`max_swipe` 仍是唯一收敛边界，**不新增 BOTTOM / ABORT / 提前返回**（`list_find` 本就没有到底部检测）。这与 K3「FrameWait 失败 → `PassResult.ABORT`」不同——`list_find` 的 sleep 从来只是 W1 结构性 settle，不是成功 / 失败门。阈值取错最多多等 / 少等一会儿，理由第 4 点（与既有瑕疵交互）也因「不改控制流」而不成立。
- 外层语义等待（`check_layer` / `check_zones` 的 `while 1: screenshot; if appear(...)`）**未动**，仍是 W2。`RuleList.swipe_pos` 几何未动。`tests/test_list_find.py` `22 → 27`（characterization 全保留，`sleep` 断言换 `wait` 断言 + 5 个新锁）。**非新 ADR**——本 ADR 预留的迁移落地。

相关文件：`tasks/base_task.py`（`list_find` / `list_appear_click` / 模块级 `_LIST_FIND_SETTLE_*` / `_list_roi_back_to_box`），`module/atom/list.py`（`RuleList.roi_back`），`tests/test_list_find.py`, `module/base/frame_wait.py`（第 2 个生产消费者，见 D012 补记）, `docs/ROADMAP.md` T5-2, `docs/AI_CONTEXT.md` §4.19 / §4.49。

---

## D014 点击空间模型演进的长期边界

状态：Accepted（**2026-09-04 T7-5 起，「默认 = 整 ROI 均匀 / 逐调用点 opt-in」两条已 Superseded；2026-09-08 起热点来源与 Region 尺寸适配由 D019 继续 Supersede**）
日期：2026-09-01

背景：计划把「ROI 内均匀随机」的点击落点升级为「Safe ROI → preferred center → 集中分布 + 少量中等偏移 + 极少外围偏移」。落地前做了一次点击空间机制全仓静态审查（结论见 `docs/AI_CONTEXT.md` §4.20），并新增人工点击采样工具 `dev_tools/manual_click_recorder.py`（见 §4.21）。以下边界长期有效。

### T7-5（2026-09-04）—— 生产默认策略变更（有意 supersede）

> 本段保留 Stage 1 / Stage 2 的历史落地事实。自 2026-09-08 起，其中
> `CENTER_FALLBACK=(0.5,0.5)`、Region「不做 short_side preferred 适配」等当前规则已由
> **D019** Supersede；实现与后续决策以 D019 为准。

**新默认**：所有「可定义为点击目标」的生产 Point 点击（`RuleClick` / `RuleImage` / `RuleOcr` /
`RuleGif` / `RuleLongClick` 的 `coord()`）默认走 `ClickSampler.sample_target(roi, rule.name)` ——
「该 target 的 preferred 热点 + 现有 core/medium/tail 偏移模型 + Safe ROI」，**不再是整 ROI
`LEGACY_UNIFORM`**。

- **每个 target 一定有 preferred**：`module/click_preference.py` 的 `TARGET_PREFERENCES`
  （静态代码 registry，按 `rule.name` 索引，与 BehaviorTrace `target` 同名）+
  `resolve_target_preference()`。`TargetPreference` = `(preferred_u, preferred_v,
  profile_name, provenance, confidence, note)`，frozen。
- **provenance 四级**：`EMPIRICAL`（自身人工样本 + 正确 ROI basis + ROI-relative 统计）/
  `SEMANTIC_TRANSFER`（从同类 EMPIRICAL target 借热点方向，必须标此级、不冒充）/
  `PROVISIONAL`（有历史 / 屏幕空间依据，缺 ROI-relative 标定）/ `CENTER_FALLBACK`
  （无依据 → `(0.5, 0.5)` + `default_point` profile）。
- **没有 empirical hotspot ≠ 退回 Uniform**：`CENTER_FALLBACK` 仍是「中心附近正态 + Safe ROI」——
  Tiny 目标仍有小幅随机（core/medium 成分，tail 按 T7-4 规则归零），**不是**每次固定同一像素
  （除非 Safe ROI 只剩一个整数像素）。禁止 `CENTER_FALLBACK` 实现成 `return roi_center`。
- **profile 与 preference 分离**：`ClickProfile`（形状：sigma / weights / margin / 尺寸适配
  基础参数）不含「哪个 target 的热点在哪」；`TargetPreference` 只提供 preferred + 来源。
  新增 `default_point` profile（数值同 `default`，单列名字让「全局 Point 默认」链路可读，
  **不写任何个人热点**）。
- **`LEGACY_UNIFORM` 保留但不再是普通 Point 生产默认**：用于兼容测试 / characterization /
  显式特殊调用 / 回归对比 / 必要 fallback。报告 / 文档区分「策略仍存在」vs「生产默认已不用」。
- **仍然只做一次空间采样**（无 double jitter）：`sample_target` → `adapt_point_profile` →
  `sample(strategy=HABIT)` 一次；`Control` / 后端不得再偏移（延续 D002）。
- **仍然禁止硬分档**：尺寸适配走连续 `size_factor`（smoothstep，锚点 24 / 96），不写
  `if tiny / elif small`。
- **Region 点击 = 业务选 region + region 内 preferred 采样两件事分开**（Stage 2，2026-09-06）：
  业务层先选 region（如 `GeneralBattle._select_reward_region`：marker → DEFAULT，否则
  80% SAVE_RIGHT / 20% SAVE_BOTTOM）—— **这层逻辑不动**；选定 region 内取坐标走
  `ClickSampler.sample_region(roi, name)` —— `TargetPreference`（无人工数据 →
  `CENTER_FALLBACK=(0.5,0.5)`）+ **`default_region`** profile（比 `default_point` 宽、仍中心集中、
  **不做 Point 的 short_side 尺寸适配**，24/96 锚点是给 Point 的）→ `HABIT` 一次。
  **不是整 region 均匀、不是固定中心**。`default_region` 参数是保守 provisional 起点，
  **不是复活 Settlement Contract v2**（`_SETTLEMENT_PRIMARY_PROFILE` 等不恢复）。
  `random_click()` 的 `RuleClick`（经 `.coord()`）仍走 `sample_target` → Point CENTER_FALLBACK，
  `ltrb=(F,F,T,F)` RIGHT-only 基线不变。
- **Stage 2 完成标准（明确）**：**「所有具有*可证明安全 ROI* 的生产点击入口完成统一空间模型迁移」**，
  **不是「所有 `device.click` 都被重写」**。其中：① 无法证明安全 ROI 的 exact coordinate 允许合法
  保留，前提是全部进 inventory + 写明 blocker；② empirical hotspot calibration ≠ 代码 / 架构迁移，
  `CENTER_FALLBACK` 已进统一 Preferred 模型即视为该 target「空间模型已统一」。
- **Stage 2 状态（2026-09-07 重新校对 + 收口）—— IMPLEMENTED**：
  - 普通 Point Rule 默认 preferred（Stage 1）；`RuleLongClick` 经 `RuleClick.coord` 继承已在模型上。
  - `ClickSampler.sample_region` + `default_region` + 3 条 Region 兜底条目落地；
    `GeneralBattle._sample_settlement_click` `sample()` → `sample_region()`（**region selection
    marker/80-20 / Generic Result 两次点击 / positive guard / state machine 一字未改**，两次点击
    仍两次独立采样）；`GeneralInvite._random_point_in_area` → `sample_target`（删私有 helper）；
    **`Secret.find_battle` 关卡卡片 `click_rule.center` ×2 → `for click_index in 1..2:
    click_rule.coord()`（两次独立 `sample_target` 采样；`click_roi` 几何 / 右侧状态文字避让 /
    循环次数 / 间隔 / `control_name` 一字未改，仅「坐标从哪里来」变）**。
  - **生产链上 bare `ClickSampler.sample(roi)`（`LEGACY_UNIFORM`）消费者 = 0**（`LEGACY_UNIFORM`
    策略保留：兼容 / 测试 / `HABIT` fallback）；whole-ROI Uniform production Point / Region = 0；
    double-sampling consumer = 0。
  - direct `device.click`（44）+ 全部 `.center` / `.front_center()` / 就地 `RuleClick` 消费点重新
    核对：`ALREADY_SAMPLED` 18（含 Chess/SwitchAccount/KekkaiActivation 就地 `RuleClick` 经
    `self.click()`）/ **`PREFERRED_POINT` 迁 2**（`GeneralInvite` + `Secret`）/ `PREFERRED_REGION`
    迁 1 / **`PENDING_MIGRATION`（有可证明安全 ROI 但未迁移）= 0** / `EXACT_COORDINATE_BLOCKED` 23 /
    `NON_CLICK`（Chess `_rule_center(RuleClick(HAND_AREA))` 是 `Press_and_Drag` 端点；其它
    `front_center()` 是 swipe 起点 / 几何判定 / x 位置分类）。
  - 回归 `953 → 977`（+24 `tests/test_t7_5_stage2.py`，含 `SecretLayerCardMigrationTest` 4）。
  - **后续两个独立持续任务（非 Stage 2 blocker，不阻塞架构结论）**：
    - **A. Empirical Hotspot Calibration**：`I_FIRE` / `normal_button`（无 `runtime_roi_probe` 输出、
      `I_FIRE` 3 个不同 asset）/ GeneralBattle 三个 Region / 其它 target 的
      `CENTER_FALLBACK → EMPIRICAL` 升级 —— Level C，不伪造 empirical 值。
    - **B. Exact Coordinate ROI Discovery**：§3.4 的 23 处，只有 Level C / 新证据确认存在安全 ROI
      且改分布不打断业务后才迁（个别「有运行时 bbox 但点角点 / 偏移」的 `Dokan:376` /
      `green_mark_name` / `QuickLoadout` 优先评估）。
- **Exact coordinate 例外的门槛**：只有「确实不存在安全 ROI，且坐标语义就是必须点这个精确
  像素 / 检测中心 / 识别失败兜底猜测点」才允许保留 `device.click(x, y)`，且必须进 inventory
  写明文件 / 行号 / 原因。**禁止为追求 100% 覆盖凭空围绕硬编码点造大 ROI。**
- 完整 inventory：`docs/T7_TARGET_PREFERENCE_MAP.md`。落地记录：`docs/AI_CONTEXT.md` §4.44（Stage 1）/ §4.45（Stage 2）。

以下 2026-09-01/02 的原始条目除被本段显式 `Superseded` 的两条外，其余（Safe ROI 硬边界、
连续 `size_factor`、人工 / behavior 数据分离、`ManualClickRecorder` 只观察、身份键要求等）
**继续有效**。

决定：

- **当前点击空间契约是基线，任何改动必须是「有意的 supersede」**：~~当前点击落点 = Rule 对象 ROI `(x, y, w, h)` 内**一次独立均匀随机**（`random_point_in_roi`），全程**无状态**~~ —— **T7-5（2026-09-04）Superseded：普通 Point 默认改为 `TargetPreference`（含 `CENTER_FALLBACK=(0.5,0.5)`）+ `adapt_point_profile` 尺寸适配 + `HABIT` 三成分 mixture，见上方 T7-5 段**。仍然成立的部分：空间随机在整条链路上**只发生一层**（`Rule.coord()` → `ClickSampler`），`Control` / minitouch / backend 转换均不再偏移，无 double jitter；中心偏置（`random_center_point_in_roi`）仍只用于 `RuleSwipe` 滑动端点、点击 0 处使用。再次演进（在线学习 preferred / 引入点击历史）仍必须在本 ADR 补 `Superseded` 说明。
- **自动动作与人工动作的原始数据永久分开**：自动点击 / 长按由 `BehaviorTrace` 记到 `log/behavior/<config>_<日期>.jsonl`；人工物理鼠标点击由 `ManualClickRecorder` 记到 `log/manual_click/<config>_<日期>.jsonl`。两类原始事件**不写进同一个 JSONL**，也不混入对方的统计。
- **`ManualClickRecorder` 只观察，不发送任何输入**：不 `Control.click` / minitouch / adb / uiautomator2，不点击、不移动鼠标、不发键盘、不抢焦点、不移动 / 缩放目标窗口。鼠标钩子回调只读事件并始终 `CallNextHookEx` 放行；采样异常一律吞在回调内，不影响用户当前鼠标操作。
- **人工采样只统计目标 MuMu 游戏画面内的真实左键**：视口窗口取 OAS 自己截图 / `window_message` 点击用的那个句柄（MuMu 游戏画面 child，见 `module/device/handle.py` `screenshot_handle_num`）；坐标换算是**纯比例** `client / window * 1280(720)`，与 OAS 一致的 DPI-unaware 空间，**不额外乘 `window_scale_rate`**；注入事件（`LLMHF_INJECTED`）默认跳过。
- **自动点击的最终坐标由「统一点击采样入口 ClickSampler」决定，`ManualClickRecorder` 只负责采样、不参与执行**。2026-09-02 已落地 `module/click_sampler.py` + `module/click_profile.py`（T7-1 第 1、2 阶段）：`ClickSampler.sample(roi, *, strategy=LEGACY_UNIFORM, profile=None) -> (int, int)`，`RuleClick` / `RuleImage` / `RuleOcr` / `RuleGif` 的 `coord()`（及 `coord_more()`）统一经它。`Control` / minitouch / scrcpy / window_message / `CommandBuilder.convert` **不因人工采样器或 preferred-center 模型增加任何空间偏移**（延续 D002）。以下边界长期有效：
  - ~~**默认策略永远是 `LEGACY_UNIFORM`，逐字等价 `random_point_in_roi`**——`Rule*.coord()` 只传 `roi`，不传 strategy~~ —— **T7-5（2026-09-04）Superseded**：`Rule*.coord()` 默认改走 `ClickSampler.sample_target(roi, name)` = `HABIT` + `TargetPreference`。仍成立：`LEGACY_UNIFORM` 路径本身极轻（不 resolve profile / 不算 Safe ROI）、逐字等价 `random_point_in_roi`，且**仍是唯一「不带 preferred 偏置」的策略**，保留给兼容测试 / characterization / 显式特殊调用 / fallback；**不做自动目标分类**（禁止 `if roi_w < N: strategy = STRICT` —— 尺寸只经连续 `size_factor` 影响 spread，不切策略）。
  - **profile（「参数是什么」）与 strategy（「怎么采样」）分离**：`ClickProfile`（`module/click_profile.py`，frozen，全 ROI 相对 `u/v`、不存绝对屏幕坐标、构造即 fail-fast）只描述热点 / spread / margin，**不产生随机坐标**；`ClickSampler` 读 profile、算 Safe ROI、按策略采样。不在 `if/else` 里写死热点 / spread / margin。`DEFAULT_PROFILES` 的个人先验值（`wide_card≈(0.58,0.59)` / `normal_button≈(0.62,0.70)` / `large_area≈(0.74,0.67)`；**T7-3.1 起全部 8 个条目都标 `provisional=True`**）是「第一版个人先验」，不是所有用户通用真值、**不是 ClickSampler 全局默认**；至少保持类别差异（tiny/small/normal_button/wide_card/large_area 纵向热点与 sigma 不同），禁止单一 `GLOBAL_PREFERRED_CENTER`。
  - **Empirical profile 必须记录坐标基准（coordinate basis），screen-space / 混合来源数据不得直接当 Point ROI-relative profile**（T7-3.1，2026-09-02）：`adapt_point_profile` 操作的坐标系是**运行时 `rule.roi_front`**（`RuleClick` 是静态 ROI；`RuleImage` 是 `match()` 后 `_update_roi_front` 写成的「模板尺寸框@匹配位置」）。任何写进 `DEFAULT_PROFILES` 的 `preferred_uv` 必须能追溯到「对哪个具体 ROI 定义算的 inside-only ROI-relative」。`wide_card` 旧值 `(0.68,0.53)` 是把 cluster_A 屏幕热点 `(641,205)` 对**手工估的更大「完整可点卡片区」`(423,142,319,118)`** 归一化得到的，坐标基准与真实消费的 `RyouToppa.C_AREA_1` RuleClick ROI 不一致——T7-3.1 用现有 manual click 原始数据（`yys1_2026-09-01` cluster_A，burst-collapse 后 107 独立落点）对当前 `C_AREA_1` WIP ROI `(514,141,223,116)` 重算，得 `(0.58,0.59)`（inside 105/107，mean≈median）。`normal_button` 的 cluster_B 只有屏幕归一化 `(0.53,0.55)`、**没有可靠 runtime `I_FIRE` roi_front**，因此 T7-3.1 **不重估**，保留旧值并标 `provisional`，等 Level C `runtime_roi_probe` + manual click 一起标定。`large_area` 是多个战后页面混合的屏幕空间中心，属 Region 语义，**禁止**用于 Point Target opt-in。`provisional` 只是文档标记，不被任何采样 / 适配逻辑读取。
  - **Safe ROI 是硬边界，越界 rejection 不 clamp**：最终坐标不能为模拟 spread 跑出 Safe ROI（= 原 ROI + 相对 margin，收成 <1px 抛 `ValueError`）。候选越界 → 有限次 rejection 重采（`max_attempts`），用尽 → fallback 到「热点 u/v 夹进 `[margin, 1-margin]` 投影进 Safe ROI」的**单个确定点**——不对越界样本做边界 clamp（会在四条边堆积）。tail 成分也必须落在 Safe ROI 内，不产生真正误点。
  - **tiny / small 可靠性优先**：STRICT 强制窄 profile（`without_tail()`、`core_sigma > STRICT_MAX_CORE_SIGMA(0.12)` 即 `ValueError` 拒绝 `wide_card`/`large_area`）。Safe ROI 内收留给未来 Safe ROI 只做「原 ROI + 相对 margin」，不做相邻控件识别 / 视觉语义 / 风险地图。
  - **Point Target 尺寸适配走连续 `size_factor`，不走离散分类**（T7-2 preferred / T7-4 spread + tail，2026-09-02）：全仓 ROI 尺寸普查（§4.26）确认点击目标 `short_side` 分布连续、无天然多峰，因此**禁止**在生产算法里写 `if tiny / elif small / elif normal / elif large`。`module/click_profile.py` 的 `adapt_point_profile(base_profile, roi) -> ClickProfile`：`short_side = min(w, h)` → `t = clamp((short_side - POINT_SIZE_MIN_PX) / (POINT_SIZE_FULL_PX - POINT_SIZE_MIN_PX), 0, 1)` → `factor = 3·t² - 2·t³`（smoothstep）→ `effective_uv = 0.5 + (base.preferred_uv - 0.5) * factor`。长期约束：**锚点 `POINT_SIZE_MIN_PX = 24` / `POINT_SIZE_FULL_PX = 96`**（provisional architecture constant，来自 ROI inventory 描述性统计，**不做用户配置**）；**同一个 `size_factor` 同时驱动「热点释放」和「小目标 spread 收敛」，不拆成第二条 / 第三条尺寸曲线**（禁止 `spread_size_factor` / `sigma_size_factor` / `tail_size_factor`）——`preferred` 向中心、`core_sigma` / `medium_sigma` 向「最保守小目标锚点」（`POINT_MIN_*_SIGMA_*`，取值 = `DEFAULT_PROFILES["tiny"]` 的 σ，审计结论见常量注释）、`tail_weight` 向 0（削掉的权重整体回补 `core_weight`，`medium_weight` 不参与曲线），都用 `f` 线性插值，`f=0` 到锚点 / `f=1` 逐字段恢复 base（`_lerp` 写成 `lo*(1-t)+hi*t` 保证端点精确）。**`safe_margin_u/v` 独立、不随尺寸变化**——Safe ROI 是 `ClickSampler` 的硬安全边界（职责与「分布形状」正交），禁止 `margin_factor` / dynamic Safe ROI；`max_attempts` / `provisional` / `name` 也原样透传。**AR 不进 `size_factor`**（`short_side` 直接代表点击容错最窄方向，`320×60` 长条不能按大面积释放）；公式对称，`base_u < 0.5` 也正确向左平滑释放，不假设个人热点只能右偏；`adapt_point_profile` 纯计算——不产生坐标、不调 RNG / 设备 / screenshot、不改传入 profile、返回新 frozen `ClickProfile`。**Region Target（`C_RANDOM_*` 大安全区 / 页面 SafeRegion / RegionSet / 全屏空白区 / GeneralBattle Settlement RD）不使用 Point Target `size_factor`**。`tiny` / `small` DEFAULT_PROFILES 条目本轮不删（测试 / 历史兼容 / 显式 profile 仍可用），但新动态算法不引用它们。T7-2 落地时零生产消费者；**T7-3.2（2026-09-02）起 `adapt_point_profile` 的唯一生产消费者是 `RyouToppa.C_AREA_1`**（见下条）。
  - ~~**Point Target 必须逐调用点显式 opt-in，禁止按 ROI 自动全局启用**（T7-3.2，2026-09-02）~~ —— **T7-5（2026-09-04）Superseded**：改为**全局默认**每个 Point target 都经 `sample_target` 拿到自己的 preferred（未标定 → `CENTER_FALLBACK=(0.5,0.5)`）。仍成立的部分：**热点必须有来源**（`provenance` 四级，不许「凭感觉」给某个 target 填非中心热点）；`ClickSampler.sample_point(roi, base_profile)`（逐调用点显式传某个语义 profile 的薄入口）仍保留，与 `sample_target`（按身份查表）并存、都走 `adapt_point_profile` + `HABIT`；采样入口**不进 `BaseTask`**（god class 约束）；`control_name = rule.name` 不被 helper / profile 名污染。`RyouToppa.ScriptTask._click_toppa_area`（`C_AREA_1` 经 `sample_point`，`rule is self.C_AREA_1` 身份守卫）本轮**保持不动**——现在 `C_AREA_2..8` 经默认 `sample_target` 也是 `HABIT`（`CENTER_FALLBACK`），`_click_toppa_area` 对 `C_AREA_1` 的显式 `wide_card` 与 registry 的 `area_1` 结果等价、冗余但无害，合并留作后续清理。
  - **`UNIFORM` ≠ `LEGACY_UNIFORM`**：数学同族但语义不同——`LEGACY_UNIFORM` 是「兼容旧行为」的默认 fallback（不收边、整 ROI）；`UNIFORM` 是「该目标业务语义就是全区域均匀」的显式声明（经 Safe ROI）。`C_RANDOM_*` 安全大区默认继续 `LEGACY_UNIFORM`（未来可显式声明 `UNIFORM`），永不被自动中心偏置。
  - **随机源**：HABIT/STRICT 的正态用 `module/base/utils/random.py` 的 `random_normal`（复用同一模块级 `SystemRandom`），不新建 `random.Random`、不引入 numpy，不在 profile 里存 RNG。ClickProfileManager 用内存结构，不每次 click 解析 JSON/YAML。
- **未来学习 preferred center 的身份键**：至少 `task + page + target`，最稳 `task + page + target + 记录时 ROI 几何`。当前 `BehaviorTrace` 缺 page 与 ROI 字段、`target` 存在跨页同名混叠，存量数据不可回填——补字段后需重新积累。
- **preferred center / spread 必须基于去重后的独立落点**：人工采样日志里大量「鼠标不动、对同一位置连点 3~6 次」，直接用 raw click 会因加权偏差**同时**把中心拉向高频连点区、把方差人为压小。必须先做 burst collapse（时空连续的相邻点击链式合并、代表点取 burst 首点，见 `dev_tools/manual_click_analyze.py`），再统计；且任何用于建模的阈值都要报告敏感性（当前样本在 300/3~800/5 ms/px 下中心稳定到 ±0.003，说明热点可信）。原始日志永不修改，派生结果写 `log/manual_click_analysis/`。
- **给落点分组贴页面 / 控件语义之前必须先验证簇假设，不能靠固定分割线直接贴标签**：2026-09-01 曾用固定 `y_split=330` 把点击二分为「上区=进攻按钮」「下区=Large Area」，实际上真进攻按钮的 y 落在下区、被和 Large Area 混在一起，是一次真实的错误分类（见 `docs/DEVELOP_LOG.md` 同日「人工点击 Cluster 分类修正」条目）。正确流程：先用确定性 k-means（`kmeans_clusters`，种子来自数据观察）分出候选簇，用簇内距离分布（`median`/`p90` 应明显小于簇间距离）判断簇是否紧致，再用相邻簇标签的时间转移关系（`transition_counts`）核对是否匹配已知操作流程，最后才回到源码找对应的 `RuleClick`/`RuleImage` 资产核实（静态 `RuleClick.roi_front` 可信；`RuleImage.roi_front` 是 `match()` 动态更新的，其静态默认值不能直接当作运行时 ROI，对不上就如实说明「无法确定」，不猜）。`region_split`（固定分割线）仍可用于纯几何粗看，但输出不得再附带页面语义。

- **ROI-relative preferred center / spread 只用 ROI 内落点算**（2026-09-02）：`landing_stats(points, roi=...)` 默认只对 `inside_roi` 子集计算全部统计量；ROI 外样本不删除、不 clamp，单独进 `outside_count` / `outside_ratio` / `outside_points` 报告，供人工判断是聚类边缘误分 / 其它控件 / ROI 定义不完整。少量外点会同时拉偏中心和 spread，必须排除后再当 preferred center 候选。（已知遗留：`relative_uv` 的 `inside_roi` 判定用闭区间 `[0,1]`，与 `random_point_in_roi` 的半开区间 `[x,x+w)` 不完全一致，`ManualClickRecorder` v1 已按闭区间发布，暂不追溯。）
- **拿资产运行时 ROI 用只读 probe，不碰生产行为**（2026-09-02）：`dev_tools/runtime_roi_probe.py` 复用生产 `Window.screenshot_window_background` 截屏 + `RuleImage.match()` 识别读 `roi_front`——**不改 `RuleImage` 公共 API、不实例化 `Device`（其 `__init__` 会 `emulator_start()`）/ `BaseTask`、不点击、不主动启动 MuMu / 游戏 / OAS / 图像识别服务**；服务不可用就清晰报错退出、不重试到死。窗口定位复用 `manual_click_recorder.resolve_viewport_hwnd`，不建第二套 HWND 查找。
- **首个非 LEGACY 生产 opt-in = GeneralBattle 通用结算（T7-1 Phase A，2026-09-02）**：`GeneralBattle._handle_result` / `_handle_reward` 的普通推进从 `random_click()`（`C_RANDOM_LEFT`/`TOP`/`RIGHT`/`BOTTOM` 四边随机）迁到两个结算区域，是 `LEGACY_UNIFORM` 之外**第一个真进生产链的策略**。以下为长期约束：
  - **迁移范围只到 `_settlement_click` 收口点**：`random_click()` 函数本身、其默认 `ltrb=(True,False,True,False)`、`C_RANDOM_LEFT/TOP/RIGHT/BOTTOM` 资产、以及所有**带自定义 `ltrb`** 的调用方（Duel `(T,T,F,T)` 明确排除 RIGHT、Dokan / fake_god / normal 仅 RIGHT、moon_sea / peacock 退出页仅 LEFT、SixRealms `page.py` import 时 `connect` 的 6 条）都**不动**。`random_click()` 保留（仍有 ~23 个消费者），暂不改名。上轮审计发现的两个历史问题（`random_click()` 改共享 `Asset.name`、`connect(..., random_click())` import-time 冻结）单独立项、本线不顺手修。
  - ~~**Reward primary → `C_RANDOM_RD`；non-reward / result → `C_RANDOM_RD2`**：`page_battle_result` 与「特殊页处理完但无 Reward marker」的 `page_reward` 直接走右侧保守 RD2。~~ —— **Superseded（2026-09-02，见下条「Settlement Contract v1」）**。该版本把 RD 当成「Reward 专用区」、把 result 当成「无 primary」，与原项目「result 与 reward 都是点当前结算阶段推进 UI」的语义不符（HEAD 旧版两者用的是同一个 `random_click()`，且 result handler 与 Reward marker 无关）。
  - ~~**Settlement Contract v1**：RD = 每个结算 stage 只点一次的 primary；点后 2 秒观察窗口；same-page 持续 2 秒 = 推进失败 → `settlement_fallback=True` → sticky RD2；`REWARD_MARKERS` / `_reward_marker_present` 决定 reward 走 RD 还是 RD2；`settlement_stage` / `settlement_primary_ts` / `settlement_fallback` + `_advance_settlement` / `_reset_settlement_stage` / `_sync_settlement_stage` 状态机。~~ —— **全部 Superseded（2026-09-02，见下条「Settlement Contract v2」）**。结合真实结算 UI 确认：一次完整战斗结算本来就需要多次点击推进（点掉胜利/失败结算层 → 推进御魂/奖励展示 → 关闭奖励展示 / 退出结算），同一语义 Page 连续多帧是**正常内部推进**，不是「点击失败」。「RD 只点一次 + same-page 超时判失败 + sticky RD2」的假设不可靠。
  - ~~**Settlement Contract v2（最终，2026-09-02）**~~ —— **Superseded（2026-09-03，见 D016 SETTLEMENT CONTRACT V3）**。`C_RANDOM_RD` / `C_RANDOM_RD2` 区域与 `_SETTLEMENT_PRIMARY_PROFILE` / `_SETTLEMENT_FALLBACK_PROFILE`（HABIT profile）已从生产代码移除；用户给出「结果页必须两次推进点击」的真实业务事实后，改为「Generic Result 强制两次点击序列 + Reward layout-aware region policy + 三个 Large Safe Region 整 ROI 均匀」。下方 v2 条目只保留历史。恢复 Phase A 前成熟的「点击 → 下一帧重新截图识别 → 仍是 settlement 就 timer 到点后再点」节奏，只把旧 `random_click(LEFT/RIGHT)` 换成 `C_RANDOM_RD`、把固定 0.8s 换成每次独立随机 0.7~1.0s。（历史）长期约束：
    - **`page_battle_result` 与 `page_reward` 走同一条 `_settlement_click(context)`**：`settlement_click_timer` 到点 → 点一次 `C_RANDOM_RD`（HABIT + `_SETTLEMENT_PRIMARY_PROFILE`，每次重新采样坐标）→ 重采下一次 `0.7~1.0s` 随机间隔（`random_delay`，项目统一随机源）→ `timer.reset()` → `return CONTINUE`。**不看 Reward marker、不做观察窗口 / same-page 超时 / fallback。**
    - **页面是否推进由外层 FSM 判断**：仍是同一 Page → 下一次 timer 到点后继续点 RD（每个 timer 周期都可以，同一语义 Page 连续多帧不判失败）；Page 变化 → 立即由新 Page handler 接管（`result → reward` 下一轮直接进 `_handle_reward`，不等旧 Page 的 timer）。`result → reward → exit` 由 `context.last_page` + `detect_page_in` 处理，**不维护第二套 stage tracking**——`BattleContext` 只保留 `settlement_click_timer`。
    - **两个限定特殊弹窗保持 Phase A 前调用时序**：`_handle_reward` 里 `appear_then_click(I_OVER_GHOST, interval=0.8)` / `appear_then_click(I_GB_SKIN_CONFIRM, interval=0.8)` **无条件尝试**、**点中也不 early-return**、不清任何状态，然后照常 `_settlement_click`。这两个页面当前无法稳定 Level C 复现，不为它们新增 gate / timer /「必须等弹窗消失才允许 RD」/ 特殊 FSM 状态 / retry / 额外 screenshot。
    - **默认间隔 `SETTLEMENT_CLICK_INTERVAL_RANGE = (0.7, 1.0)`**，每次成功点击后独立重采（不是任务开始随机一次后复用）。子类 override：只有 `RealmRaid`（有意 `(0.65, 0.95)`），本轮不动；其它 subclass 无 override。这个随机化只是 settlement 操作节奏的正常随机化，不是任何规避检测机制。
    - **`C_RANDOM_RD2` / `_SETTLEMENT_FALLBACK_PROFILE` 保留为预留 fallback region，Contract v2 下无生产消费者**——不再以「同一语义 Page 持续 2 秒」为自动触发。未来合理触发条件可能是「page 未变 + frame 也没有有效变化 + 多次确认没推进 → RD2」，但**本轮不接 FrameState / FrameWait 进 GeneralBattle**，只保留 semantic page polling，FrameChanged 是独立下一阶段（见 `docs/ROADMAP.md`）。
    - **保留 Rule 身份**：点击经 `_sample_settlement_click(rule, profile)` → `device.click(x, y, control_name=rule.name)`（`rule` = `C_RANDOM_RD`），BehaviorTrace 的 `target` = `random_rd`；不复用 `random_click()` 改 `Asset.name` 的副作用。
    - **结算 profile 页面专属 + provisional，不进 `DEFAULT_PROFILES`，参数冻结**：`_SETTLEMENT_PRIMARY_PROFILE`（`preferred_uv=(0.54,0.53)` 屏幕≈`(1009,563)`、core σ 0.10 / medium σ 0.16、tail 0.03、margin 0.06）、`_SETTLEMENT_FALLBACK_PROFILE`（`preferred_uv=(0.56,0.58)` 屏幕≈`(1167,484)`、core σ (0.12,0.09) / medium σ (0.18,0.15)、tail 0、margin (0.10,0.06)）。Settlement Region 走 HABIT + 这些 profile，**不走** Point Target 的 `short_side → size_factor` 连续模型（独立下一阶段）。
    - **采样异常不静默退 LEGACY**：`_sample_settlement_click` 的 `ClickSampler.sample(...)` 抛 `ValueError`/`TypeError` → `logger.error` 后退回**整 ROI 均匀**采样一次（不卡死主循环），不静默当作正常路径。
    - **`_settlement_click` 签名**：`(context) -> bool`（回到 Phase A 前的单参形式；`_advance_settlement` / `primary_enabled` / `reward_present` 均已删）。
- **calibration 前缀识别是启发式、可覆盖**（2026-09-02）：`detect_calibration_prefix` 的「首次相邻间隔 ≥ 8s + 前缀含屏幕边缘点」只在 `yys1_2026-09-01` 上验证过，不是通用协议；`--calibration-count` / `analyze(calibration_count=)` 可显式覆盖，`summary` 报 `detected_by` + `excluded_range_ts` 供人工核对。
- **动态 OCR bbox → 整数点击 ROI 的类型兼容在 `RuleOcr` 边界解决，不放宽下游整数契约**（2026-09-04，注记，**非新 ADR**）：`RuleOcr` FULL 模式的 `coord()` 用的是 `Full.ocr_full()` 用 OpenCV 检测框覆写的 `self.area` —— 天然是 numpy 浮点 `(x, y, w, h)`。`RuleClick` / `RuleImage` 的静态 ROI 是人工框选的整数、必须保持整数契约；OpenCV 检测框是浮点是常态。因此浮点→整数的责任放在「OCR 检测框 → 点击采样」这一条 `RuleOcr` 专属边界上：`module/atom/ocr.py` 的 `_normalize_ocr_click_area(area)`（左 / 上 `floor`、右 / 下 `ceil` → 完整包住原浮点框、不缩小可点区；贴屏幕右下边缘裁到 `1280` / `720`；宽 / 高兜底 ≥ 1；已整数 ROI 是恒等变换），`coord()` 里 `ClickSampler.sample(_normalize_ocr_click_area(area))`。**不改** `module/base/utils/random.py` 的 `random_point_in_roi`（仍拒绝浮点 ROI）、**不让** `ClickSampler.sample` 静默强转所有浮点 ROI、**不动**点击分布算法。此断裂自 D007（`random_point_in_roi` 加整数校验 + `RuleOcr.coord` 改调它）起 latent，2026-09-04 才在 `oas2` 结界→式神育成 FULL 模式 OCR 点击真机跑到（`TypeError: ROI必须由整数组成：(595.0, 293.0, 34.0, 101.0)`）。详见 `docs/AI_CONTEXT.md` §4.43 / `docs/DEVELOP_LOG.md` 2026-09-04 同名条目。

禁止 / 注意事项：不要把两类 JSONL 合并；不要让 `ManualClickRecorder` / `runtime_roi_probe` 发任何输入或改窗口或启动设备；不要在 `Control` / minitouch / `CommandBuilder.convert` 里加点击空间抖动；不要在未做「有意 supersede」说明的情况下把 `random_point_in_roi` 的均匀语义改掉；§4.20 记录的 5 个 latent bug 未经确认不要顺手修。

相关文件：`module/click_sampler.py`（T7-3.2 `ClickSampler.sample_point` + **T7-5 Stage 1 `ClickSampler.sample_target`** + **T7-5 Stage 2 `ClickSampler.sample_region`**）, `module/click_preference.py`（**T7-5 新增**：`Provenance` / `TargetPreference` / `TARGET_PREFERENCES` / `resolve_target_preference` / **Stage 2 `REGION_FALLBACK_PROFILE` + `random_default`·`random_save_right`·`random_save_bottom` 三条 Region 条目**）, `module/click_profile.py`（含 T7-2/T7-4；**T7-5 Stage 1 `default_point` + Stage 2 `default_region` profile**）, `module/atom/{click,image,gif,ocr}.py`（**Stage 1：`coord()` / `coord_more()` 改走 `ClickSampler.sample_target`**；`ocr.py` 保留 `_normalize_ocr_click_area`；`RuleLongClick` 经 `RuleClick.coord` 继承）, `tasks/Component/GeneralBattle/general_battle.py`（**Stage 2：`_sample_settlement_click` → `ClickSampler.sample_region(rule.roi_front, rule.name)`**，region 选择 / 两次点击 / policy 未改）, `tasks/Component/GeneralInvite/general_invite.py`（**Stage 2：`_random_point_in_area` → `ClickSampler.sample_target`**，删私有 helper + `random_point_in_roi` import）, `tasks/Secret/script_task.py`（**Stage 2 收口：`find_battle` 关卡卡片 `click_rule.center` ×2 → `for click_index in 1..2: click_rule.coord()`**，`click_roi` 几何 / 状态文字避让 / 循环 / 间隔 / `control_name` 未改）, `tasks/RyouToppa/script_task.py`（T7-3.2 `_click_toppa_area`；Stage 2 只更正注释「区域 2~8 = LEGACY_UNIFORM」→「= `sample_target` CENTER_FALLBACK」）, `tests/test_ryoutoppa_c_area_1_point_opt_in.py`, `tests/test_click_sampler.py`, `tests/test_t7_5_preferred_hotspot.py`（Stage 1 契约回归）, `tests/test_t7_5_stage2.py`（**Stage 2 契约回归**：`default_region` / `sample_region` / `RuleLongClick` / GeneralInvite 迁移 / double-sampling 审计）, `tests/test_general_battle_settlement.py`（Stage 2：`SamplingTest` 改 `sample_region`）, `tests/test_rule_ocr_float_roi.py`, `tests/test_click_profile.py`, `docs/T7_TARGET_PREFERENCE_MAP.md`（**T7-5 全项目点击空间模型覆盖 inventory**）, `dev_tools/manual_click_recorder.py`, `dev_tools/manual_click_analyze.py`, `dev_tools/runtime_roi_probe.py`, `dev_tools/click_roi_inventory.py`, `dev_tools/large_click_roi_review.py`, `tests/test_manual_click_recorder.py`, `tests/test_manual_click_analyze.py`, `tests/test_runtime_roi_probe.py`, `tests/test_click_roi_inventory.py`, `tests/test_large_click_roi_review.py`, `module/atom/click.py` / `image.py` / `ocr.py` / `gif.py`（`coord()` 经 `ClickSampler`），`module/base/utils/random.py`（`random_point_in_roi` / `random_center_point_in_roi` / `random_normal`），`module/device/control.py`, `module/behavior_trace.py`, `module/device/handle.py`, `tasks/Component/GeneralBattle/general_battle.py`（T7-1 Phase A Contract v2：`_settlement_click(context)` / `_sample_settlement_click` / `_SETTLEMENT_PRIMARY_PROFILE` / 预留 `_SETTLEMENT_FALLBACK_PROFILE` / `SETTLEMENT_CLICK_INTERVAL_RANGE=(0.7,1.0)`）, `dev_tools/settlement_trace_check.py`, `tests/test_general_battle_settlement.py`, `tests/test_general_battle_timing.py`, `tests/test_settlement_trace_check.py`, `docs/AI_CONTEXT.md` §4.20 / §4.21 / §4.22 / §4.24 / §4.25 / §4.26 / §4.27 / §4.28 / §4.29 / §4.30 / §4.31 / §4.32。

---

## D015 Verify / Wait / Retry / Recovery 的职责分层，与未来 retry primitive 的硬约束

状态：Accepted
日期：2026-09-02

背景：三个真实案例（`BaseTask.list_find` §4.19、`KekkaiActivation`/`KekkaiUtilize` §4.33、
`RealmRaid` §4.34）都已完成迁移前静态收口 + characterization。本 ADR 把横向归纳
（`docs/状态验证与重试模式归纳.md`）里形成的长期职责边界固化下来，作为 T4-3（Wait/Retry
Policy）与后续任何状态化迁移的约束。D010（frame_state 边界）/ D012（frame_wait 只做
取帧+轮询+timeout）/ D013（语义等待 vs 视觉结构等待、收口阶段不抽 seam）已覆盖的部分本
ADR 不重复，只补「retry / recovery 层」与四类职责的 owner。

决定：

- **四类职责分属不同 owner，不合并成一个万能 API**：
  - **Verify**（Action 后确认业务结果是否成立）：`Task` 用既有 `appear` /
    `wait_until_appear` / `wait_until_disappear` / `GameUi.detect_page_in` 组合。**不新增
    `Verifier` / `ActionVerifier` 类**——三案例的 Verify 形态（结果是坐标 tuple / `not
    appear(X)` / `appear(X)` / `appear(X)` 后 `not appear(X)` / OCR 条件）差异过大，抽类
    只会逼业务扭曲。
  - **Wait**（有限时间窗口内等条件成立）：语义等待用 `wait_until_appear(wait_time=)` /
    `wait_until_disappear`（当前缺 `wait_time`，未来补的是 1 行签名，不是新类）；视觉结构
    等待用 `module/base/frame_wait.py::wait_for_changed_and_stable`（已完整，D012）。
    **不新增第二套 structural wait 抽象。**
  - **Retry**（Verify 失败后是否再次执行 Action，带 attempt 上界）：见下条。
  - **Recovery**（retry 用尽 / 状态最终失败后业务做什么）：**永远留在 Task**。三案例的
    Recovery 是 `return False` / `refresh` / `switch group` / `set_next_run(+N min)` /
    改 config / `raise TaskEnd` / `find_one` 涂黑跳过——高度业务特化，无公共形态。
- **禁止合并成 `wait_for_action_success(changed=, stable=, marker=)` 这类万能 verifier**：
  `视觉结构状态（frame changed/stable）≠ 业务语义状态（appear/disappear）`（D010 已述），
  三案例进一步证明——`list_find` 纯结构、`RealmRaid` 纯语义、`Kekkai` 两类都有且要分开处理。
- **`max_attempts` 与 `timeout` 是两个正交约束**：`max_attempts` 限「Action 执行次数」，
  `timeout` 限「整段状态迁移的墙钟时间」；允许同时存在、任一先到即止；**数值永远由调用方
  显式给，不设项目级默认**（三案例合理 timeout 从 2 秒到 120 秒跨两个数量级，
  `GLOBAL_ACTION_TIMEOUT` 这类常量是错的）。timeout 可能分三层：wait primitive 自己 /
  retry 机制（若存在）/ Task 的业务操作总超时（如 Kekkai `Timer(120)`）。
- **当前不新增公共 retry 抽象（PARTIAL 结论）**：三案例的 action-retry 循环有共同骨架，
  但 action 多 target 交替、当前全部无 bound（加 bound 即改时序 → 每个消费者接入都是
  Level C）、recovery 差异极大。唯一真正共同的内核只有「计 attempts + 独立 total
  timeout + 返回 frozen result」约 15 行——**值得未来抽，不值得现在在零消费者下抽**（会
  变成又一个像 `frame_wait` 一样长期悬空、且缺真实 adoption 校准形状的组件）。等**第一个
  真实 Level C 迁移**（大概率 RealmRaid `fire()`）时对着真实消费者抽。
- **未来若抽 bounded retry primitive，硬约束（提前锁定，防止设计走歪）**：
  1. **只**负责：循环、计 `attempts`、按注入 `clock` 计 `elapsed`、`max_attempts` /
     `timeout` 任一到即停、返回 frozen `RetryResult`（`success` / `timed_out` /
     `attempts` / `elapsed` / `last_verify`，无业务字段，形态参照 `FrameWaitResult`）。
  2. **不缓存业务 target 坐标**——每次 attempt 的「定位 + 动作」在 `action` callback
     里完成（`RuleImage` / `RuleOcr` / 动态列表每次重 match / 重算；静态 `RuleClick`
     恰好 ROI 不变但 primitive 无从判断）。primitive **不理解** `RuleImage` /
     `RuleOcr` / `RuleClick` / list / partition 等业务类型。
  3. **不 screenshot**——`verify` / `action` callback 自己截图 + 识别（模式 B，与现有
     `screenshot(); appear(...)` 写法零改造契合）。必须防「Action 后 Verify 读到 Action
     前旧帧」。
  4. **不做 recovery**——`success=False` 时只返回 `RetryResult`；`goto_page` /
     `refresh` / `raise TaskEnd` / `set_next_run` / `switch_friend_list` / 选下一个
     target / 改 config 一律由 Task 读结果后自己做。
  5. **异常默认透传**——`action` / `verify` 抛出的异常原样向上，不计入 attempt、不当
     verify 失败（把 `AttributeError` / `None+datetime` 这类真 bug 伪装成「retry 失败」
     会掩盖缺陷）。「可重试异常白名单」是未来的显式能力，需单独讨论。
  6. 放 `module/base/` 下，依赖全部可注入（`clock` 等），`timeout` 必须为正、不允许
     `None` / `inf`、超时不抛——与 `frame_wait` 同款。
- **`module/base/retry.py` 的 `@retry` 装饰器不适配 task 层**：它是异常触发式
  （`try: f() except`）、只用于 device / connection / adb / minitouch 等基础设施层，
  `tasks/` 内零使用；没有 verify callback / fresh screenshot / result 对象 / timeout。
  未来的 task 层 bounded retry 是 verify 触发式，另起，不复用它。
- **BehaviorTrace 下一个事件是 `RETRY`**（一次 bounded retry 循环结束记一条：target /
  transition 名、attempts、elapsed、outcome=success/timed_out，天然含 timeout 信号），
  优先级高于 `VERIFY`（每 attempt 一条太吵、违背 D004「不记录 appear()」的克制）/
  `TIMEOUT`（是 `RETRY` 的子集）。排在 retry 抽象之后。

禁止 / 注意事项：不要为「本轮要有成果」新建 `RetryPolicy` / `ActionVerifier` /
`RecoveryEngine` / `GenericStateMachine` / `GenericTargetLocator`；不要把 `frame_wait` /
语义等待 / retry / recovery 合并成一个巨型 API；不要给 retry primitive 加 recovery /
target 类型理解 / 坐标缓存 / 异常吞咽；`list_find` §4.19 记录的已知瑕疵（末轮仍 swipe、
`ocr_appear` 空结果 `(0,0)` 当命中）与翻页等待重构耦合，不进 Level A cleanup 队列。

**补记（2026-09-08，RealmRaid `fire()` R-R1 —— bounded retry 就地落地，不抽 primitive）**：本 ADR
说「未来的 task 层 bounded retry 是 verify 触发式，另起、不复用 `@retry`」，并把 RealmRaid `fire()`
列为 R-R1 候选（`docs/ROADMAP.md`）。RealmRaid `fire()` 收口时**没有**抽通用 `RetryPolicy`/primitive
——就在 `fire()` 里写 `for attempt in range(1, RR_FIRE_MAX_TRIES+1)` + `Timer(RR_FIRE_TIMEOUT)`，
verify = `is_in_battle()`（正向战斗确认，复用 `GeneralBattle.is_in_battle`，不新造 detector），
recovery = **调用方 `run()` 的 `if not self.fire(index): continue`**（回外层循环重新 `check_ticket` +
`find_one`），完全符合本 ADR「Recovery 永远在 Task」「retry 是每个 attempt 一次独立 Action
Transaction（重新 screenshot + reaction）」。`fire()` 的 reaction（`REACTION_FIRE`）与 bounded retry
是同一段 FSM 里的两件事，不叠 `confirm_delay` / 第二套 delay。这次落地印证 D015 的分层稳定：
**局部就地实现足够，通用 bounded-retry primitive 仍不抽**（等 Orochi / EvoZone / RyouToppa /
RealmRaid 四个 FIRE 收口后若形状确实一致再评估）。`Exploration.fire()` 仍是形状参照。

**增补（2026-09-08 同轮，transition / unknown 状态边界）**：`fire()` 的 verify 从「二元 battle /
not-battle」细化为**三态**：`'battle'`（success）/ `'retryable'`（明确仍可操作 → 下一 attempt）/
`'timeout'`（过渡 / 未知帧 —— **既不成功也不 immediate failure**，有界 timer 内继续等）。新增
纯只读 helper `_is_realm_raid_retryable_state()`（`I_RR_PERSON` / `I_FIRE` / `I_BACK_RED` 任一）作为
「retryable」判据。**与 D015「verify = Task 组合既有 `appear` / `detect_page_in`，不新增 Verifier
类」一致** —— 这个 helper 只是几个 `appear()` 的组合，不是通用 verifier；bounded FSM 边界（`for` +
两层 `Timer`）不变，transition-unknown 的等待在 `_wait_fire_entered_battle` 自己的 `Timer` 内，不会
把 FSM 变回无界。

相关文件：`docs/状态验证与重试模式归纳.md`（完整分析源）, `module/base/frame_wait.py`,
`module/base/retry.py`（异常触发式先例，不复用）, `tasks/base_task.py`（`wait_until_appear`
/ `wait_until_disappear` / `appear` / `list_find`）, `module/behavior_trace.py`,
`docs/ROADMAP.md` T4-3 / T4-4 / T5-2。

---

## D016 GeneralBattle 通用结算 SETTLEMENT CONTRACT V3

状态：Accepted
日期：2026-09-03

背景：Contract v2（D014，`C_RANDOM_RD` / `C_RANDOM_RD2` + HABIT profile + timer 节流的
opportunistic settlement click）在结合真实结算 UI + 用户实测后被推翻。用户明确给出一条
**真实业务事实**（不是代码推断）：战斗结果页 → 第一次点击进入奖励蹦出动画 → 第二次点击
推进该动画 → 页面才稳定进入奖励结算。即 result → reward **不是单次 click transition，而是
一个不可拆的 mandatory action sequence**。同时用户提供三个新的大安全点击区与两个奖励布局
判别标志。

决定（长期契约）：

- **旧 `C_RANDOM_RD` / `C_RANDOM_RD2` 区域、`_SETTLEMENT_PRIMARY_PROFILE` /
  `_SETTLEMENT_FALLBACK_PROFILE` 视为 deprecated / removed**：不恢复、不做兼容 alias
  （不写 `C_RANDOM_RD = C_RANDOM_DEFAULT`）、不为让旧测试通过重建旧资源。
- **三个结算安全区是 Large Safe Region，不是 Point Target**：`C_RANDOM_DEFAULT`（默认推进）
  / `C_RANDOM_SAVE_RIGHT` / `C_RANDOM_SAVE_BOTTOM`（Reward 布局 fallback）。采样一律整 ROI
  均匀（`ClickSampler.sample(roi)` 默认 `LEGACY_UNIFORM`）——**不走** `appear_then_click` /
  `confirm_delay` / `reaction_delay`，**不做** HABIT 偏置 profile。GeneralBattle 自己的
  settlement timing（`SETTLEMENT_CLICK_INTERVAL_RANGE` + 下面的强制双击序列）是它唯一的
  micro timing owner。
- **Generic Result mandatory two-action sequence**：`_handle_result` 在**通用结果上下文
  首帧**（`_is_generic_result_context()` = `I_WIN` / `I_DE_WIN` / `I_FALSE` 正向命中，且
  `settlement_click_timer` 未启动）执行 `_advance_generic_result(context)`：采样
  `C_RANDOM_DEFAULT` 点 #1 → `time.sleep(_next_settlement_click_interval())`（**这个专用
  序列内允许一次明确的随机 sleep**，因为 #1→interval→#2 已确认是同一不可拆业务动作）→
  **重新采样** `C_RANDOM_DEFAULT` 点 #2 → 用同一区间武装 `settlement_click_timer` → 返回
  `CONTINUE`。两次点击都是必须动作（**不是 retry、不是「最多两次」、不是第一击后立即要求
  `page_reward`**），两次坐标分别独立采样（禁止 sample-once-click-twice）。
- **positive generic guard，不用 Task 黑名单**：更宽的 `I_BATTLE_STATE_INFO`（`page_battle_result`
  基础识别器成员之一）**不纳入** guard——静态无法证明其所有出现场景都适合强制双击；这类
  帧、以及 `settlement_click_timer` 已启动的后续帧，退回旧的单次 `_settlement_click` 节流
  点击（保持现状）。private override（`BondlingFairyland._handle_result`、SixRealms
  `moon_sea` / `peacock_kingdom` 的 `_handle_result` / `_handle_reward`）不 `super()`，
  **不被公共双击穿透**；`super()` 调用方经 guard 后才走双击。
- **`_advance_generic_result` 只负责动作序列**：不做 Page detection / `is_win` 判定 /
  exit matcher / reward marker / overlay / retry / fatigue / FrameWait。
- **settlement timer 交接**：mandatory #2 之后 `timer.limit = _next_settlement_click_interval();
  timer.reset()`——把 #2 视为最近一次 settlement click，使下一 FSM 帧（仍 result 或已
  reward）被节流跳过（不出现意外第三击），同时保证页面若卡住能在一个间隔后恢复节流点击。
  **只有一个 timer owner**，不叠加第二套。
- **Reward layout-aware policy**：`_handle_reward` 先处理特殊弹窗——本轮确实点中
  `I_OVER_GHOST` / `I_GB_SKIN_CONFIRM` 之一就**立即 `CONTINUE`**（Action → Fresh State
  边界，不在同帧继续 region click）；都没点中才 `_select_reward_region()`：
  `I_GET_BATTLE_REWARD` / `I_GET_BATTLE_REWARD_2` 命中任一 → `C_RANDOM_DEFAULT`；都没命中
  → `random_int(1, 100) <= 80` 走 `C_RANDOM_SAVE_RIGHT`，否则 `C_RANDOM_SAVE_BOTTOM`；然后
  `_settlement_click(context, region=...)` 节流点一次。
- **`I_GET_BATTLE_REWARD` / `I_GET_BATTLE_REWARD_2` 是 Reward Layout Discriminator**：只在
  `page_reward` 已确认后用于「点哪个安全区」，**不是** page recognizer / 点击目标 / 胜利
  标志，**不得**加入 `page_reward.recognizer`。
- **不变**：`is_win`（`I_FALSE` → loss、其它 → win；private task 保持各自胜负逻辑）、
  `_exit_matcher`、结算消失后约 2.5s 的 missing fallback、`run_general_battle` FSM 结构、
  `default_pages.random_click()` 的既有职责（navigation 与 Settlement Policy 分离，SAVE
  区域**不**反向接入 `random_click`）、`RuleClick.coord()` 默认 `LEGACY_UNIFORM`。

不写进本 ADR（可能 Level C 调整的具体参数，按项目 ADR 风格不固化）：`SETTLEMENT_CLICK_INTERVAL_RANGE`
的 `(0.7, 1.0)` 具体值、Reward fallback 的 `80 / 20` 具体比例、`C_RANDOM_*` 的具体 ROI。

Level C 待验：0.7~1.0 是否是最合适两击间隔；`C_RANDOM_DEFAULT` 新 ROI 实际安全性；两种
奖励布局 marker 识别稳定性；marker miss 的 RIGHT / BOTTOM fallback 是否覆盖绝大多数剩余
布局；特殊任务真实战后 UI 有无遗漏；`I_BATTLE_STATE_INFO`-only 结果帧是否需要也纳入强制
双击。新契约的 BehaviorTrace Level C 分析器（`dev_tools/settlement_trace_check.py` 已按 3
区域名做最小更新，未校验双击时序结构与 80/20 分流）另行设计。

禁止 / 注意事项：不恢复 RD / RD2；不给三个安全区加 `confirm_delay` / `reaction_delay` /
HABIT profile；不把 `FatigueManager.try_break` 塞进结算序列；不在 mandatory #1 / #2 之间
插 fatigue idle / rest；不引入 FrameWait 判断 reward 动画；不把 mandatory double-click
做成 retry_until / max_attempts / timeout primitive；不因 marker miss 直接 return battle
result 或退出（正式结束仍由原 `exit_matcher` + missing fallback 判断）；不重写
`run_general_battle` FSM（D008）。

相关文件：`tasks/Component/GeneralBattle/general_battle.py`（`_is_generic_result_context` /
`_advance_generic_result` / `_select_reward_region` / `_sample_settlement_click` /
`_settlement_click` / `_handle_result` / `_handle_reward`）, `tasks/Component/GeneralBattle/assets.py`
（`C_RANDOM_DEFAULT` / `C_RANDOM_SAVE_RIGHT` / `C_RANDOM_SAVE_BOTTOM` / `I_GET_BATTLE_REWARD` /
`I_GET_BATTLE_REWARD_2`，用户 WIP）, `tests/test_general_battle_settlement.py`,
`tests/test_general_battle_timing.py`, `dev_tools/settlement_trace_check.py`,
`tests/test_settlement_trace_check.py`, `docs/AI_CONTEXT.md` §4.3.1 / §4.39,
`docs/ARCHITECTURE.md`（通用战斗结算段）。取代 D014 的 Settlement Contract v1 / v2 条目。

---

## D017 KekkaiUtilize 好友结界卡搜索：单向分区 PASS 序列 + 阶段化阈值

状态：Accepted
日期：2026-09-03

背景：`KekkaiUtilize` 非怠惰路径原本是「扫全当前分组整列表 → 记 global-best（按
`_card_rank`）→ `_reselect_best_card` 回到顶部按收益值回选最优」（AI_CONTEXT §4.11）。真机
观察到好友列表**首次进入不稳定排序 / 收益不按高低排列 / 中间星级交错**，「扫全找理论最优 +
回选」既慢又不可靠，且 `miss_count > CONSEC_MISS` 会把乱序列表中间的 target-miss 误判为
「列表到底」。用户确认新流程尽量贴近人工操作。

决定（KekkaiUtilize 非怠惰搜索的长期契约）：

- **取消一切「蛇形 / BOTTOM→TOP / 反向 swipe / reverse scan / TOP marker / 搜索框布局识别 /
  swipe-no-change 判 TOP / FrameWait 判 TOP」**。所有好友列表扫描统一 **TOP→BOTTOM 单向**。
  利用「切换同区 ↔ 跨区后列表自动回到顶部」来重置到 TOP，而不是反向滑。
- **按 PASS 序列搜索**，每个 PASS = `(friend_group, stars, threshold_map, final_fallback)`：
  - 优先跨区（`config.select_friend_list == DIFFERENT_SERVER`）：
    `跨6★HIGH → 同6★HIGH → 降一档 → 跨5/6★LOWER → 同5/6★LOWER(final)`（跨→同→跨→同）。
  - 优先同区（默认 `SAME_SERVER`）：`同6★HIGH → 跨6★HIGH → 降一档 → 同5/6★LOWER(final)`
    （同→跨→同）。
  - 每个 PASS 前 `switch_friend_list(group)` 切到目标分组；实际 SAME/CROSS 切换后游戏自动
    把新分组列表显示在顶部（**2026-09-06 Level C 确认**，见下方「PASS 前初始化补记」）；
    PASS 内只向下 swipe。
- **第一阶段只搜 6★、用高阈值**（`taiko_reward_threshold` / `fish_reward_threshold` 配置值，
  默认六星满值 76 / 151）。**不扫 5★、不扫 4★**。
- **第一阶段（所有 6★HIGH PASS）全部失败后，阈值降低一档一次**，第二阶段搜 **5★+6★**
  （真实奖励档位与星级不一一对应，6★ 也可能只有 118，所以 5/6★ 都必须扫）。「降一档」=
  `lower_reward_tier(value, tiers)`（`tasks/KekkaiUtilize/utils.py`）：取严格小于当前阈值的
  最大真实离散档位，斗鱼档位 `(101,109,118,126,134,143,151)`、太鼓 `(42,50,59,67,76)`；
  没有更低档则保持最低档。**不是 `threshold - 固定数字`**。**只降一次**（第二阶段所有 PASS
  共用同一份 lower map）。
- **发现候选 → 点击 → 详情 OCR → 达到本 PASS 阈值 → 立即用当前选中的卡进入寄养**。
  **不要求找到全列表理论最优**，不再有 global-best / `_reselect_best_card` / 第二遍回选。
- **最后一个 PASS 自身兼任最终兜底**，没有独立的第四种 `FALLBACK_SEARCH` 轮次、没有「扫到底
  → 切区 → 再从顶部找第一张」。final PASS 扫到 `I_U_EMPTY_CARD`（到底）时：
  - 本 PASS 至少点开过一个候选 → **直接用「最后一次点击、仍保持选中」的候选**寄养：不再
    检查阈值 / 不重新搜索 / 不回头 / 不保存坐标·好友名·页码·行号·candidate history。
  - 本 PASS 一张候选都没点开 → **不能盲目点【进入结界】**，返回失败交外层 bounded recovery
    （`_record_utilize_failure` 3 次上限）。
  - PASS 内只需一个局部 `has_clicked_candidate` bool，不保存任何位置/身份信息。
- **BOTTOM 与安全上限严格区分**：`appear(I_U_EMPTY_CARD)` = 真正到底（→ PASS_MISS /
  FINAL_USE_LAST）；`Timer(SEARCH_PASS_TIMEOUT=120)` 超时 / 滑满 `SEARCH_MAX_SWIPES=20` 屏仍
  没见到 `I_U_EMPTY_CARD` / 切分组超时 = **SAFETY_ABORT**（外层按失败重试，不当作到底）。
  **「连续几屏没有目标模板」不是 BOTTOM**——列表乱序，继续向下滑。
- **识别基础设施复用不变**：`ImageGrid.find_everyone`（card-column `roi_back` + 当前帧真实
  bbox + 按 y 排序）、`C_SELECT_CARD.roi_front = area` 动态点击、`check_card_num()` OCR。
  不引入好友行 anchor / 固定第 1/2/3/4 行 / 好友名 OCR / 新列表检测器 / TOP 搜索框模板。
  不跨 swipe 复用旧坐标。
- **怠惰模式（`_run_lazy_utilize` / `_select_lazy_resource_card`）不受本决定影响**，保留原
  「优先分组 → 备选分组、首张符合策略的高星卡即拿」双分组流程，包括其 `miss_count >
  consecutive_miss_limit` 的到底启发式。

不写进本 ADR（可 Level C 调整的具体值）：`SEARCH_MAX_SWIPES` / `SEARCH_PASS_TIMEOUT` /
`DETAIL_LOAD_WAIT` / `SWIPE_DISTANCE` 具体数值、`taiko/fish_reward_threshold` 默认值、
离散档位表的最终值。

禁止 / 注意事项：不恢复蛇形 / global-best / `_reselect_best_card`；不把 `miss` 当 BOTTOM；
不新增第四种 fallback 轮次；不接 FrameWait 到 KekkaiUtilize；不改滚动几何（`SWIPE_DISTANCE`
等）/ 不扩大结界卡 ROI（独立 Level C）；不新增配置项；不为「列表/详情卡种偶发不一致」提前
做复杂 recovery。`I_U_EMPTY_CARD` 是否可靠表示到底 —— **Level C 待验收，不得标 VERIFIED**。
（「切区是否稳定回顶」已于 2026-09-06 Level C 确认，见下方补记。）

**PASS 前初始化补记（2026-09-06，Level C 触发）**：Level C 明确确认「**只要 SAME/CROSS
发生实际切换，新进入的好友分组列表必定从顶部显示**」。据此 `_run_search` 每个 PASS 前
从 `_reset_utilize_friend_list(search_pass.friend_group)` 改为
`switch_friend_list(search_pass.friend_group)` —— **标准（非怠惰）路径不再滚到列表底部
（`S_U_END`）、不再切走再切回、不再调用 legacy `_reset_utilize_friend_list`**。依据：
① `_build_search_passes` 保证相邻 PASS 分组一定不同（新增契约测试锁 `RunSearchGroupSwitchOnlyTest`）；
② `switch_friend_list` 对已在目标分组的情形检测到选中态直接返回、0 次 tab click。
`_reset_utilize_friend_list`（`S_U_END` 滚到底 + 切区双切）**保留但仅怠惰路径
（`_run_lazy_utilize`）调用**，docstring 标 legacy/lazy-only；`S_U_END` 资产定义不删。
未改（指本次 PASS 前初始化简化）：K1 `_perform_search_swipe` / `SWIPE_DISTANCE=416`（K2 2026-09-07 起标准 minitouch 路径改随机 `SWIPE_DISTANCE_RANGE`，首档 `(212,265)` → 同日 Level C 回调 `(140,180)`，见下方 K2 补记）/ `switch_friend_list` 本体 /
本 ADR 全部业务契约（PASS 顺序·threshold·bottom·final·lower once·OCR·lazy）。
`test_kekkai_utilize_state.py` 53→62，回归 944→953。**标准路径进列表后不再「先把整列表
拽到底」、当前分组正确时 0 tab click —— Level C 待复核。**

**K1 补记（2026-09-04）**：D017 定稿时「swipe 后端」不动。之后按 **D018** 落地了
**K1 —— 只把「标准 PASS 搜索」（`_run_search_pass`）的列表下划从 `swipe_adb` 迁到
minitouch trajectory**（minitouch 配置 → `_perform_search_swipe` → `TouchSwipeModel` +
`Control.swipe_trajectory`；非 minitouch 显式回退旧 `perform_swipe_action`）。**滚动几何
（起点安全区、416px 主方向位移）、settle（`click_record_clear` + `sleep(2)`）、怠惰模式
（`_select_lazy_resource_card` 仍走 `perform_swipe_action`）、以及本 ADR 的全部业务契约
逐项不变。** K1 只换输入后端，Level C 待真机验收。

**K2 补记（2026-09-07；含同日 Level C 分档回调）**：标准 PASS 的 **minitouch 路径** commanded
finger 位移从固定 416px 改成每次 `_perform_search_swipe()` 独立 `random_int(*SWIPE_DISTANCE_RANGE)`
采样一个较短位移。`SWIPE_DISTANCE_RANGE` 是 **provisional、Level C 分档调参**（`KEKKAI_ROW_PITCH_PX
= 106`、一屏约 4 格；旧 416px ≈ 3.9 格）：
- **首档 `(212, 265)`**（≈2.0~2.5 row_pitch）—— 首次 Level C 实测「一次内容仍滚 >4 格」，确证
  **commanded finger distance ≠ actual content scroll**（好友列表惯性放大），判定过大。
- **当前 `(140, 180)`**（≈1.3~1.7 row_pitch 手指位移，整体降约 1/3）—— 预计实际仍滚 2~3 格，目标
  相邻两屏保留 1~2 格重叠；若二次 Level C 仍实际 >3 格，下一档 `(110, 150)`（单变量分阶段）。

**轻微整体斜度（2026-09-07 同日）**：旧 `end_x == start_x` 让宏观轨迹接近严格竖直
（`TouchSwipeModel` 只在中段给轻微曲率）。改成每次 `_perform_search_swipe()` 独立
`lateral_offset = random_int(*SWIPE_LATERAL_OFFSET_RANGE)`（`SWIPE_LATERAL_OFFSET_RANGE = (-12, 12)`，
provisional），`end_x = clamp(start_x + lateral_offset, *SWIPE_START_X_RANGE)`，`end = (end_x,
start_y - distance)`。**只作用于最终 `end_x`**——不给每个 MOVE 点加随机噪声；宏观轨迹变成「有的
轻微左斜 / 有的轻微右斜 / 有的接近竖直」，整体仍明确向上 swipe。`end_x` 夹回起点安全区
（**不扩大 `start_x` 范围**）：start_x 贴边界时偏移被有界裁掉、退化竖直，绝不滑出可接受区。

**只改「滑多远 / 往哪斜」**——决定 start/end/距离/斜度在 Kekkai 业务层，`TouchSwipeModel` 只负责
「怎么滑」（给定 start/end → 平滑轨迹），**一行未改**、仍只调一次、仍只收 start/end；起点安全区
（`start_x` / `start_y` 范围不变）/ 曲率 / 时间模型 / tail / `swipe_trajectory` 一次 /
`control_name` / settle（K3 的 FrameWait 与 `SWIPE_WAIT_*` / `poll_interval`）均不变。
**怠惰路径 + 非 minitouch 回退（`perform_swipe_action` → `swipe_adb`）仍固定 `SWIPE_DISTANCE=416`
纯竖直。** 本 ADR 上方「不写进本 ADR」已列 `SWIPE_DISTANCE` 具体数值为「可 Level C 调整」——
`SWIPE_DISTANCE_RANGE` / `SWIPE_LATERAL_OFFSET_RANGE` 及其档位同属该范畴，**调档 / 加有界斜度不新建
ADR、只更新事实**。**契约**：K2 只减小 commanded 位移 + 给宏观轨迹一点斜度、建立重叠；
`finger distance ≠ content displacement`（游戏列表惯性）的测量 + `scroll_gain` + 帧间投影去重是
**K4**，不在 K2。

**K3 补记（2026-09-07）**：标准 PASS 的 **minitouch 路径** swipe settle 从固定 `time.sleep(2)`
改成 **FrameWait**（`module/base/frame_wait.py` 的 `wait_for_changed_and_stable`，见 D012 K3 补记）：
`_perform_search_swipe()` 在 swipe **前**明确重截 `baseline`（不复用可能被候选卡详情页污染的
`self.device.image`）→ `swipe_trajectory` + `click_record_clear` → 等「相对 baseline 的 card-column
区域 `changed` 且随后 `stable`」→ 返回 `wait.success`（方法签名 `-> None` 改 `-> bool`）。
- **失败即 ABORT，不当作到底**：`changed` 迟迟不出现 / `changed` 后不 `stable` / `timeout`
  → 返回 `False` → `_run_search_pass` `return PassResult.ABORT`（外层 bounded recovery）。
  **`no change ≠ BOTTOM`**——本 ADR 的唯一 BOTTOM marker 仍是 `I_U_EMPTY_CARD`；K3 不新增
  「滑不动 → PASS_MISS」隐式到底。方法内一次 swipe → 一次 FrameWait，无内部 retry。
- **ROI / 阈值 / pacing 由 Kekkai 业务层决定**：`SWIPE_WAIT_ROI = (525,155,620,610)`（card-column 包络）+
  4 个 provisional 判定阈值（`changed 0.10` / `stable 0.02` / `stable_frames 3` / `timeout 3.0s`）+
  **显式 `poll_interval=SWIPE_WAIT_POLL_INTERVAL=0.15`**（覆盖 D012 的全局默认 `0.0`——惯性微滚下
  零间隔轮询会提前判 stable，加一档检测采样 pacing 让连续 `stable_frames` 帧跨越更长真实时间窗；
  叠在 `_screenshot_interval` 之上，**非恢复固定 `sleep(2)`**）。全部注释标「需 Level C 调整」。
  FrameWait 本层无业务默认、全局 `poll_interval` 默认也不改（D012 K3 补记）。
- **不变**：K1（`TouchSwipeModel().generate` / `swipe_trajectory` / `control_name`）、K2（随机
  `SWIPE_DISTANCE_RANGE` 采样档位当前 `(140,180)` + 有界斜度 `SWIPE_LATERAL_OFFSET_RANGE=(-12,12)`）、
  BehaviorTrace（一次 swipe = 一个 ACTION，FrameWait 轮询不产生额外 ACTION）、
  怠惰 + 非 minitouch 回退（`perform_swipe_action`：固定 416 + `time.sleep(2)`，**不接 FrameWait**）、
  FrameWait 全局默认、本 ADR 全部业务契约。`TouchSwipeModel` / `FrameStateDetector` /
  `wait_for_changed_and_stable` 本体一行未改。settle 方式（含 `poll_interval` 取值）属「可 Level C
  调整」的实现细节，**不是新长期决策**。

**K4 补记（2026-09-07，解冻并实施 Level A/B；Level C pending）**：标准 PASS 用 `I_IS_SELECTED`
（好友卡列表右缘选中态发光竖线，`roi_back = (602,168,30,442)` 纵向覆盖整个可见滚动高度的动态搜索条）
做**动态锚点**，测「上一稳定屏 → 当前稳定屏」的**实际**列表滚动像素，把上一屏候选投影到当前屏去重，
只把真正新进入的候选交给业务处理。

**阶段定义（统一口径）**：**K4-1** = Selected Anchor → `actual_scroll_dy` —— ✅ Level A/B；
**K4-2** = Frame-to-Frame Projection Dedup（previous detections 按 `actual_scroll_dy` 投影 → 与 current
做「同 candidate type + bbox overlap/IoU」one-to-one matching → duplicates + `new_detections`，仅
`new_detections` 进候选处理）—— ✅ Level A/B。**K4 overall Level C** ⏳ pending。
**`new-region-only optimization`**（按 `actual_scroll_dy` 直接裁新进入的视觉区域、只在那块跑 template
matching / `find_everyone`——性能优化）—— ⏸ **NOT IMPLEMENTED / OPTIONAL**，当前无必要。

以下是**长期契约**（K-series 补记，非新 ADR）：
- **commanded ≠ actual**：`SWIPE_DISTANCE_RANGE=(140,180)` / `SWIPE_LATERAL_OFFSET_RANGE` 只是
  commanded 指令位移 metadata（Level C 已确认游戏列表惯性放大）。K4 的 `actual_scroll_dy` **只能**
  来自 selected anchor 视觉位移 = `before.center_y − after.center_y`（`center_y = y + h/2`，before/after
  统一口径）。**禁止** `actual_scroll_dy = commanded_distance` / `× 固定 gain` / 用 `SWIPE_DISTANCE_RANGE`
  推算。`KEKKAI_ROW_PITCH_PX = 106` 只用于把 dy 解释成「约几格」/ sanity，**不参与** dy 核心计算，
  **不把 dy 四舍五入成整数格**（保留 sub-row 连续位移）。
- **一帧对一帧、无持久历史**：只保留「上一稳定屏」的 `find_everyone` 结果与它 swipe 前的 anchor，
  与「当前稳定屏」比对一次后当前屏成为新的「上一屏」。**禁止**全 PASS 永久历史 / 全局 candidate
  database / 好友身份历史 / persistent dedup map。
- **去重条件**：投影 = `y − actual_scroll_dy`；上一屏候选与当前屏候选**类型一致（`image.name`）且 bbox
  真实几何交集（IoU > 0）**才可配对，竞争时按 max IoU 贪心一对一（一个 previous 不重复消费多个
  current，一个 current 不被多个 previous 消费）。**不新增 ±px magic tolerance**。投影中心出
  `K4_LIST_VISIBLE_Y` → 该上一屏候选已滚出屏、忽略。类型不一致即使位置重叠也**绝不**去重、**不重新 OCR** 好友名。
- **测量不可靠 → 完整扫描**：`before`/`after` anchor 任一不可用（首屏没点过卡 / 本屏无选中 / glow 被
  列表边界裁切）、NMS 后 >1 个候选、`dy <= 0`、`dy >= roi_back 高度` —— 全部退回当前屏
  `find_everyone` 结果的**完整** D017 处理。**宁可重复读卡，不能漏掉真正的新六星卡。**
- **measurement unavailable ≠ ABORT ≠ BOTTOM ≠ PASS_MISS**。**K3 失败仍 ABORT**（且此时不进 K4 的
  after anchor / dedup——`_perform_search_swipe()` 返回 True 才进）。**BOTTOM 仍只认 `I_U_EMPTY_CARD`**
  （没有 new candidate / dy 很小 / anchor 不见 / 投影后全 duplicate 都**不是**到底）。
- `clicked_any` / `FINAL_USE_LAST` / `utilize_found_eligible_card` 语义不变（K4 跳过 dup 不会清零已置位的
  `clicked_any`——它单调只置 True）。K2 / K3 / `_perform_search_swipe` / `SelectedAnchorDetector` 之外的
  资产（`select_realm_on_1~4` 死资产不删）一行不改。`I_IS_SELECTED` 阈值 / 收敛策略（多匹配、
  score_gap）/ `K4_LIST_VISIBLE_Y` 都是 provisional，等 Level C（当前好友卡样本不足）再定。
- **出屏判定**用 projected **center** 是否在 `K4_LIST_VISIBLE_Y` 内，而非「bbox 完全离开可见 ROI」
  （后者更严格）。center-based 最多倾向**少去重 → 重复处理旧卡**，**不会漏新卡**；Level C 未证明
  这里有真实问题前**不改**（不换 bbox intersection、不加 tolerance、不加 magic threshold），仅列为
  Level C 观察项。
- 实现拆两个 task-local 纯组件：`tasks/KekkaiUtilize/selected_anchor.py`（`detect_selected_anchor` /
  `SelectedAnchorResult`，只找 glow —— **K4-1**）+ `tasks/KekkaiUtilize/frame_projection.py`
  （`actual_scroll_dy_px` / `project_bbox` / `bbox_iou` / `dedup_by_projection`，纯几何 —— **K4-2**），
  都不 swipe / 不调 FrameWait / 不改 PASS。
- **`new-region-only optimization`**（按 `actual_scroll_dy` 只裁新进入的视觉区域跑识别）本轮**未实现**
  ——当前 K4-2 是**业务层去重**（跑完整 `find_everyone` 后过滤 `new_detections`），不是视觉区域裁剪；
  该性能优化 optional、当前无必要，禁止顺手做（不改 `find_everyone` ROI / 不动态裁 `roi_back` /
  不跳过完整当前帧 detection / 不加复杂 persistent tracker）。

相关文件：`tasks/KekkaiUtilize/script_task.py`（`PassResult` / `SearchPass` / `_pass_targets` /
`_card_meets_pass` / `_build_search_passes` / `_run_search`（每 PASS 前 `switch_friend_list`）/
`_run_search_pass` / `_run_lazy_utilize`；`_reset_utilize_friend_list` 现为 legacy/lazy-only）、
`tasks/KekkaiUtilize/utils.py`（`FISH_REWARD_TIERS` /
`TAIKO_REWARD_TIERS` / `lower_reward_tier`）、`module/base/frame_wait.py`（K3 首个消费者，见 D012 K3 补记）、
`tasks/KekkaiUtilize/selected_anchor.py` + `tasks/KekkaiUtilize/frame_projection.py`（K4 两个 task-local 纯组件）、
`tasks/KekkaiUtilize/utilize/utilize_is_selected.png` + `assets.py` 的 `I_IS_SELECTED`（K4 锚点资产，用户标注）、
`tests/test_kekkai_utilize_state.py`（含 `PerformSearchSwipeK1/K2/K3Test` + `K4IntegrationTest`） /
`tests/test_kekkai_k4_selected_anchor.py` / `tests/test_kekkai_k4_projection.py` /
`tests/test_kekkai_utilize_threshold.py`、`docs/AI_CONTEXT.md` §4.11 / §4.41 / §4.47、
`docs/KekkaiUtilize蹭卡流程重新审查.md`（改造前审查）。取代 §4.11 里「global-best + reselect」
的选卡描述。

---

## D018 自定义滑动轨迹：模型出数据 / 执行层发命令 / `Control.swipe` 不变 / 显式 opt-in（Plan B）

状态：Accepted
日期：2026-09-04

背景：`docs/Minitouch自定义轨迹能力审查.md`（2026-09-03 专项审查）确认 minitouch 协议层
（`Command` / `CommandBuilder`）已完全能表达「自定义多点触摸轨迹 + 逐段 dt + 任意 x/y」，
缺的只是「一个接受调用方点列表的薄执行层 + 一个公开入口」。审查给出三个接入方案，推荐
**Plan B**（模型只产纯轨迹数据 → 执行层负责发给 minitouch）。2026-09-04 落地第一阶段
（`module/device/touch_swipe_model.py` + `Minitouch.swipe_minitouch_trajectory` +
`Control.swipe_trajectory`），本 ADR 把这套分层与边界固化为长期契约。

决定（自定义滑动轨迹的长期分层）：

- **`TouchSwipeModel`（`module/device/touch_swipe_model.py`）= 「怎么移动」**：纯数学轨迹
  生成器，`generate(start, end) -> list[(x, y, dt_ms)]`。**不 import** device / `Config` /
  `BaseTask`，不碰截图 / FrameWait / OCR / ROI / 业务状态 / minitouch socket /
  BehaviorTrace / 旋转分辨率换算。可脱离设备单测。运动学 = minimum-jerk 位置进度
  `s(t)=10t³-15t⁴+6t⁵`（起步慢 / 中段快 / 收尾慢）+ 整体曲率 `curve_amp·sin(πt)`
  （一次采样、可正可负、幅度有上限，不给每个 MOVE 点加独立随机抖动）+ 逐段 dt（基础
  节拍 + 两端放慢 + 有界抖动，全 `>0` 且夹在 `[min,max]`）。
- **执行层（`Minitouch.swipe_minitouch_trajectory`）= 「怎么发给 minitouch」**：迭代模型
  产出的点列表 → `builder.down` / `[builder.move.commit.wait(dt)]` / `builder.up`。**不套用
  `insert_swipe`、不对 dt 叠加 `random_int(6,15)`、不自己拼 raw command、不改 `Command` /
  `CommandBuilder` / `minitouch_send` / 握手。** `pressure` 与 `click_minitouch` /
  `_press_and_drag_minitouch` 一致——整个手势用同一个 `_humanized_pressure()`，只是协议
  兼容字段（MuMu 恒 1），**不是 `TouchSwipeModel` 的行为变量**。
- **`dt_ms` 语义固定为「到达当前点之后、下一次移动之前的停留」**：`trajectory[i][2]` 是
  「MOVE 到第 `i` 点后 `wait` 的毫秒」。第 0 点是落点、没有「移动到达」，其 dt 恒为 0 且
  被执行层忽略（第一版**不加**按压前置停顿）。也**不加**普通 swipe 的 UP 前固定 `wait`
  ——尾部减速由「末段 dt 变化 + 点更密」表达，不复制 `drag` 的 `wait(140)×2`（那是 D002
  的落点 settle 语义，不迁移到普通轨迹滑动）。
- **输入校验（`_ensure_trajectory`）在 `@retry` 之外**：非法轨迹（点数 < 2 / 非
  `(x,y,dt)` / NaN·inf / MOVE 点 dt 取整后 < 1）立即抛 `ValueError`，不被重试逻辑吞成
  `RequestHumanTakeover`。真正发命令的内层 `_swipe_minitouch_trajectory_run` 才套 `@retry`
  （长战斗后 socket 断开时重建控制连接，与 `swipe_minitouch` 同款）。
- **公开入口 `Control.swipe_trajectory(trajectory, control_name='SWIPE')` 是独立 opt-in**：
  不改 `Control.swipe` 的签名 / 分支 / 任何行为，不给它加 `path=` kwarg。非 minitouch
  后端 `raise NotImplementedError`——**不静默用首尾点退化成端点直线滑动**，以免自定义轨迹
  语义被悄悄丢掉。BehaviorTrace 与 `Control.swipe` 一致：只 `record('ACTION',
  action='swipe', target=control_name, elapsed_ms=...)`，**不记每个 MOVE**（延续 D004）。
- **随机源**：新代码走公共 `module/base/utils/random.py`（`random_int`）；`TouchSwipeModel`
  支持 `rng=` 注入以便确定性单测（默认 `_DefaultRng` 委托 `random_int`）。**不**为测试把
  生产随机源改成可 seed 的全局 `random`；D007「`insert_swipe` 的 `np.random` 保留」不变。
- **范围**：第一阶段只建基础设施——**不接** `BaseTask`（不加 `BaseTask.swipe_trajectory`）、
  **不接** KekkaiUtilize / 任何任务、不改 `RuleSwipe` / `BaseTask.swipe` / 416px ADB swipe /
  `SEARCH_MAX_SWIPES` / FrameWait。真正把某个调用点切到 `swipe_trajectory` 是逐调用点显式
  opt-in（类似 T7 Point opt-in），且是 Level C。
  **首个生产 consumer = `KekkaiUtilize` 标准 PASS 搜索的列表下划（K1，2026-09-04）**：
  `_run_search_pass` 的下划入口 `_perform_search_swipe` 在 minitouch 配置下走
  `TouchSwipeModel().generate` → `Control.swipe_trajectory(..., control_name='KEKKAI_UTILIZE_SWIPE')`；
  非 minitouch 后端由**业务调用点显式回退**旧 `swipe_adb`（不改本 ADR 的「非 minitouch =
  `NotImplementedError`」契约）；怠惰模式仍走旧 `perform_swipe_action`。**K1 只换输入后端 ——
  滚动几何（416px）、settle、D017 业务契约不动**；`SWIPE_DISTANCE=416` 只是 K1 baseline，
  **不是长期设计决策**。K1 真机验收 = Level C。

不写进本 ADR（可 Level C 调整）：`TouchSwipeParams` 的具体默认值（`avg_step_px` /
`min/max_points` / `base_dt_ms` / `end_slow_ratio` / dt 抖动与边界 / `max_curve_px` /
`curve_px_ratio`）、尾部微修正（`tail_correction_*`，第一版默认关）的最终去留。

原因：模型是纯函数最易测、与后端解耦（换后端只需另写执行层）；把轨迹生成塞进共享
`Control.swipe` 会污染整个 control layer、改变全项目滑动行为；协议细节进模型则锁死
minitouch 且不可测。

禁止 / 注意事项：不把 `TouchSwipeModel` 的输出直接写成 minitouch 命令字符串；不改
`Command` / `CommandBuilder` / `minitouch_send` / 握手 / `Control.swipe`；不给 `Control.swipe`
加 `path=`；不让非 minitouch 后端静默退化；不在执行层重新 `insert_swipe` 或叠加
`random_int(6,15)`；不加按压前置停顿 / UP 前固定 wait；pressure 不进模型行为参数。
**实际滚动量 / 落点 / 逐段 dt 在设备侧是否被如实执行 / 是否被游戏识别为「滑动」而非
「点击」（minitouch ≥5px）/ 与 `insert_swipe` 路径的行为差异 —— Level C 待验收，不得标
VERIFIED。**

### 第二阶段追加（2026-09-04，时间连续性 + 尾段慢拖）

第一阶段 Level C（图形 + MuMu 设置页）确认空间结构正确后，对时间维度做优化。以下是
长期契约（**不推翻上面第一阶段任何条目**）：

- **逐段 `dt` 的随机用「连续、有界、零均值」扰动，而不是逐 MOVE 独立 jitter**。第一版实现
  是一阶低通（EMA）：`noise_i = alpha*noise_{i-1} + (1-alpha)*rng.randint(±jitter)`，
  `noise_0 = 0`。它必须满足：恒有界（`|noise| <= jitter`）、不长期漂移、相邻 MOVE 无
  无界跳变。时间模型固定拆成 **`base_dt(s)`（趋势，负责前慢中快后慢）+ smooth_noise
  （只做小幅自然变化）**，且**趋势 > 噪声**。不引入 scipy / numpy / 控制理论依赖。
- **尾段慢拖靠「MOVE 点更密 + `dt` 平滑增大」表达**，按「已走距离占比 s」度量（约最后
  10~15% 距离）。硬约束：**最终仍精确到原 `end`**（取整）、**不额外滑一段 / 不改滑动距离**、
  **不做固定 pre-UP 停顿**（不复制 `drag` 的 `wait(140)×2`）、**不做过冲后回拉**。进入
  尾段的放慢用 `smoothstep`（`k=0` 处一阶导为 0）平滑接续，禁止 `dt` 从中段值突跳一大截。
- **minimum-jerk 本身已让尾部空间密**，尾段加密只是「相对主运动更细」，禁止机械翻倍 /
  堆几十个几乎相同的终点 MOVE（`max_points` 封顶 + 相邻整数点去重照旧）。
- **`dt_ms` 语义不变**（仍是「到达当前点后、下次移动前的停留」，首点 dt=0），executor /
  协议契约不变，`Control.swipe` / `BaseTask` / `RuleSwipe` 不变。**澄清**（2026-09-04，非契约
  改动）：executor 命令流是 `DOWN(p0) | MOVE(p_i) COMMIT WAIT(dt_i) … | UP`，所以分析 / 绘图里
  「段 `p_i → p_{i+1}` 的时间」必须取 **`dt_i`**（``speed = dist(p_i,p_{i+1}) / dt_i``，
  `i = 1 .. n-2`）；**`p0 → p1` 无 trajectory 显式 dt**（`p0.dt=0` 被忽略，两 batch 间只有
  `minitouch_send` 的 `DEFAULT_DELAY`，不并入），**`dt_{n-1}` 是 pre-UP dwell**、不配给任何
  MOVE→MOVE 段。见 `docs/DEVELOP_LOG.md` 2026-09-04「segment speed 与 dt 对齐修正」（仅修
  dev 工具 + 测试统计，生产零改动）。
- **`tail_correction`（过冲微修正）继续默认关**，不是本阶段内容。
- **空间曲率参数（`max_curve_px` / `curve_px_ratio`）本阶段不动** —— 不与时间模型同时改，
  否则 Level C 无法归因。

不写进本 ADR（Level C 可调）：`dt_smooth_alpha` / `tail_start_ratio` / `tail_density_gain` /
`tail_slow_gain` / `max_dt_ms` / `max_points` 的具体值、总时长的最终量级（第一版静态数据
120→~120ms / 260→~230ms / 440→~400ms，`短 < 中 < 长` 严格成立；是否整体再放慢等第二轮
MuMu Level C）。实施记录见 `docs/DEVELOP_LOG.md` 2026-09-04「第二阶段」条、`docs/AI_CONTEXT.md`
§4.42。

### 全仓迁移补记（2026-09-07，ordinary swipe 优先 trajectory / drag 保留 legacy）

第一阶段说「真正把某个调用点切到 `swipe_trajectory` 是逐调用点显式 opt-in」。KekkaiUtilize
K1~K4 真机验证成功后，本轮把这条推广为长期约定：

- **普通页面滑动 / 列表滚动一律优先 trajectory**。统一走公共 helper
  **`BaseTask.swipe_trajectory(start, end, *, control_name='SWIPE', fallback=True)`**（`tasks/base_task.py`
  ——第一阶段「不加 `BaseTask.swipe_trajectory`」的约束在本轮解除）：minitouch 且位移 ≥ 10px →
  `TouchSwipeModel().generate` → `Control.swipe_trajectory`；非 minitouch → `fallback=True` 回退
  `Control.swipe`（端点滑动，D003 各后端 duration 契约不变），`fallback=False` 抛 `NotImplementedError`；
  位移 < 10px 走端点回退、不进模型。helper **只负责「怎么滑一次」**——不 screenshot / 不 FrameWait /
  不 sleep / 不 retry / 不加随机延迟（那些是业务层职责；helper 不含 D017 K3 的 FrameWait）。
- **`BaseTask.swipe(RuleSwipe)` 改为委托 helper**——42 个 `self.swipe(S_*)` 生产 consumer 透明迁移，
  起终点仍 `swipe.coord()`、方向 / 距离 / `interval` / `control_name`（→ `click_record` 计数）不变。
- **drag / press-and-drag / 摇杆手势永不按 ordinary swipe 迁移**：`Control.drag` + 各后端 `drag_*`
  （DOWN→MOVE→保持→UP 语义，D002）、`tasks/Chess/runtime/press_and_drag.py`、
  `AbyssShadows.move_a_little`（虚拟摇杆，有意 `duration=`）保持 legacy。
- **`Control.swipe` / `Control.swipe_vector` 仍不删**（历史兼容 API）；本 ADR「不给 `Control.swipe`
  加 `path=` / 非 minitouch 不静默退化」等条目全部不变。helper 的非 minitouch 回退是**调用方
  显式选择**走 `Control.swipe`，不是 `swipe_trajectory` 内部退化。
- 本轮未迁：`BaseTask.list_find` 翻页 swipe（绑 T5-2）、KekkaiActivation 好友卡 `swipe_adb`
  （距离敏感，需独立 K 式分阶段）、RyouToppa `flush_area_cache`（依赖 `duration=`，D003 契约）、
  KekkaiUtilize `perform_swipe_action`（K-series 保留的回退）。
- **非新 ADR**——是 D018「逐调用点 opt-in」的推广 + 落地一个薄公共 helper。所有迁移 consumer 的
  真机效果（曲线是否识别为滑动 / 滚动量差异 / 连续滚动 timeout / ≤16px 弓形是否碰危险区）
  **Level C PENDING**，KekkaiUtilize 除外。实施记录见 `docs/DEVELOP_LOG.md` 2026-09-07「全仓 Swipe
  Consumer 审查 + TouchSwipeModel 全局迁移」、`docs/AI_CONTEXT.md` §4.48、`docs/TESTING.md` §5。

相关文件：`module/device/touch_swipe_model.py`（`TouchSwipeModel` / `TouchSwipeParams` /
`_DefaultRng`）、`module/device/method/minitouch.py`（`_ensure_trajectory` /
`swipe_minitouch_trajectory` / `_swipe_minitouch_trajectory_run`）、`module/device/control.py`
（`Control.swipe_trajectory`）、`tests/test_touch_swipe_model.py` /
`tests/test_minitouch_trajectory_executor.py` / `tests/test_control_swipe_trajectory.py`、
`tasks/base_task.py`（**全仓迁移补记：公共 helper `BaseTask.swipe_trajectory` + `BaseTask.swipe`
委托它**）、`tasks/Component/GeneralBuff/general_buff.py`（`exp_50`/`exp_100` 直连 swipe → helper）、
`tests/test_base_task_swipe_trajectory.py`（16 用例）、
`tasks/KekkaiUtilize/script_task.py`（K1 消费者 `_perform_search_swipe`；**K2 补记：其
minitouch 路径的 `SWIPE_DISTANCE_RANGE` 随机位移（Level C 分档，首档 `(212,265)` → 2026-09-07 回调
`(140,180)`）+ 有界斜度 `SWIPE_LATERAL_OFFSET_RANGE=(-12,12)`（`end_x` 夹回起点安全区）都是 Kekkai
业务层决定，`TouchSwipeModel` 未改**；**K3 补记（见 D017 K3 补记）：该路径 swipe settle 从
`time.sleep(2)` 改成 FrameWait，
仍不动 `swipe_trajectory` / `TouchSwipeModel`**）、`tests/test_kekkai_utilize_state.py`
（`PerformSearchSwipeK1Test` / `PerformSearchSwipeK2Test` / `PerformSearchSwipeK3Test`）、
`docs/Minitouch自定义轨迹能力审查.md`（可行性审查）、`docs/AI_CONTEXT.md` §4.41「K1」/「K2」/「K3」 / §4.42。
与 D002（稳定性时序不改）/ D003（`Control.swipe` duration 后端契约）/ D004（BehaviorTrace
v1 范围）/ D006（`RuleSwipe` 只提供端点）/ D007（公共随机源）一致，均未推翻。

## D019 点击热点解析统一为「人工热点优先 + 未采样目标规则锚点 + preferred 尺寸适配」

状态：Accepted
日期：2026-09-08

背景：T7-5 已把生产 Point / Region 点击收口到 `ClickSampler`，但旧的
`CENTER_FALLBACK=(0.5,0.5)` 只表达「没有人工数据时取中心」，会让大目标永远以正中心作为最终
热点；同时 Point 的 24/96 smoothstep 尺寸适配被包在 `adapt_point_profile` 内，Region 无法只复用
热点释放而不继承 Point 的 sigma / tail 收缩。`RyouToppa.C_AREA_1` 已有可靠人工样本，其
`wide_card preferred=(0.58,0.59)` 必须继续保持 EMPIRICAL 身份。

决定：

- **热点来源优先级固定为 `EMPIRICAL` > `RULE_FALLBACK`**。已登记人工样本的 target 使用自己的
  empirical anchor；没有自身人工热点的 target 使用统一规则锚点
  `RULE_BASE_PREFERRED=(0.58,0.59)`，provenance 必须是 `RULE_FALLBACK`。数值相同不代表证据来源
  相同：`area_1` 的 `(0.58,0.59)` 是 EMPIRICAL，GeneralBattle 三个 Settlement Region 及 resolver
  默认的 `(0.58,0.59)` 是 RULE_FALLBACK。未来某个 target 登记自己的 EMPIRICAL 后，按 target
  registry 命中自然覆盖规则兜底，禁止把人工条目降格成规则条目，也禁止把通用锚点冒充人工数据。
- **不再把「无人工数据 → 永远正中心 `(0.5,0.5)`」作为大目标最终热点**。`default_point` 与
  `default_region` profile 仍保留中性的 `preferred=(0.5,0.5)`，只承担分布形状模板职责；解析出的
  target anchor 会在采样前复制到实际 profile。profile shape 与 target preference / provenance
  继续分离。
- **抽出 preferred-only 尺寸适配**：`adapt_preferred_by_size(preferred_u, preferred_v, roi)` 用
  `short_side=min(width,height)`、`SMALL_ANCHOR=24`、`FULL_ANCHOR=96`，先算
  `t=clamp((short_side-24)/(96-24),0,1)`，再算 `s=t²(3-2t)`，最终
  `u=0.5+(base_u-0.5)s`、`v=0.5+(base_v-0.5)s`。因此短边 `<=24` 精确回到中心，短边
  `>=96` 精确使用完整 anchor，中间连续释放。函数只返回 effective preferred，不采样、不改 profile
  shape、不访问设备。
- **Point 与 Region 复用同一 preferred 适配，但职责仍分开**。Point 链路仍是
  `sample_target → resolve preference → adapt_point_profile → HABIT`；`adapt_point_profile` 内部复用
  `adapt_preferred_by_size`，并继续用同一个 smoothstep factor 收缩 core/medium sigma 与 tail。
  Region 链路是 `sample_region → resolve preference → adapt_preferred_by_size → 只替换 preferred →
  HABIT`，明确**不调用** `adapt_point_profile`，所以 `default_region` 的 sigma / weights / margin / tail
  不随 ROI 尺寸变化。
- **GeneralBattle Settlement 业务策略不变**：marker → DEFAULT / 80-20 的 region 选择、Generic Result
  两次点击、timer、positive guard、state machine 均不改；仅选定 Region 内的 effective preferred
  按上述规则计算。当前真实 ROI 下：`random_default`（short side 230）使用完整 `(0.58,0.59)`；
  `random_save_right`（87）与 `random_save_bottom`（69）按公式部分释放。
- **一次点击一次空间采样、Safe ROI、HABIT mixture、控制后端不再偏移等 D014 契约继续有效**。
  本决策只 supersede D014/T7-5 的 `CENTER_FALLBACK` 语义，以及 Region「完全不做尺寸适配」的表述；
  Region 仍不继承 Point shape adaptation。

相关文件：`module/click_preference.py`、`module/click_profile.py`、`module/click_sampler.py`、
`tests/test_click_profile.py`、`tests/test_t7_5_preferred_hotspot.py`、`tests/test_t7_5_stage2.py`、
`docs/T7_TARGET_PREFERENCE_MAP.md`、`docs/AI_CONTEXT.md` §4.50。

## D020 RealmRaid 主业务策略：九宫格固定 1→9 / 只剩最后目标才退四 / 普通失败按 `when_attack_fail` / 目标 pacing 独立 owner

状态：Accepted
日期：2026-09-08

背景：`tasks/RealmRaid/script_task.py` 的 `run()` 主循环历史形态 = `find_one()` 按 `order_attack`
配置的**勋章优先级**（`order_medal` ImageGrid + `find_anyone`）选一格 → `ensure_lock` →
`click(C_PARTITION[index-1])` → `fire(index)` → `run_general_battle`；退四由 `if index == 1`
（九宫格第 1 格）触发，然后 `fire` 一次 + **逐字硬编码 4 次** `fire_again()`（前 3 次 quick_exit
投降、第 4 次真打）；失败格只在 `WhenAttackFail.CONTINUE` 下在 `self.device.image` 上**原地涂黑**
（污染共享帧，静态收口 R-R9）。用户已确定要把目标选择改成「九宫格固定从左到右、从上到下」、把退四
触发改成「只剩最后 1 个可攻打目标」、并在选定目标到点开详情之间加一段目标级业务 pacing。三个
AskUserQuestion 收口：退四触发「完全替换为『只剩最后 1 个可攻打目标』」；普通失败「保留配置，仍按
`when_attack_fail` 走」；Fatigue「本轮就接入」。FIRE 本体（`fire()` R-R1、退四内「再次挑战」
`_fire_again()`）的 reaction / bounded FSM 归 **D001 FIRE 分节**，本 ADR 只固化 RealmRaid 侧的
**目标选择 / 退四触发 / 失败策略 / 目标 pacing** 四项长期业务契约。

决定：

- **目标选择 = 九宫格固定 1→9，与勋章数量 / `order_attack` 优先级无关**。新增
  `_grid_targets() -> {1-based order: 勋章 RuleImage}`：`order_medal.find_everyone()` 一次扫全 9 格，
  `order_medal` 降级为「这一格有没有可挑战对手」的**过滤器**，每个匹配按中心点映射回
  `C_PARTITION_n.roi_front`。`run()` 取 `index = min(targets)`（最小 1-based order = 从左到右、
  从上到下第一个可攻打格）。`find_one()` 重写成 `_grid_targets` 的薄包装（保留 `(medal, order)`
  签名供 `check_medal_is_frog`）——**勋章值只影响呱太判定，不再影响攻击顺序**。`order_medal` /
  `I_MEDAL_0..5` / 呱太 OCR 资产**保留不删**（仍用于「有没有对手」和呱太识别）。`order_attack`
  config 字段保留（`order_medal` cached_property 仍读它构造 ImageGrid 的模板集），只是不再决定顺序。
- **失败格识别脱离 mode + 不再原地涂黑**。`_broken_orders() -> set`（1-based）复用 `false_roi` +
  `false_image`（RyouToppa `loser_sign_1.png`），**所有模式都扫**——固定 1→9 选目标后，刚失败还没
  刷新的格必须每轮排除，否则被重复选中。`_grid_targets` 在 `image.copy()` 上涂黑 broken 格
  （`broken` 非空才 copy），**不再原地写 `self.device.image`**（修 R-R9）。
- **退四触发 = 「只剩最后 1 个可攻打目标」**（`only_last = len(targets) == 1`），**完全替换旧
  `index == 1`**（在固定 1→9 下第 1 格语义完全错位）。`if only_last and con.raid_config.exit_four:`
  进入退四分支。
- **退四前解锁阵容**：退四分支 `self.ensure_lock(False)`（`ensure_lock(False)` 已核实真实语义 =
  最终 UNLOCKED，非猜测）→ `_enter_target` → `fire` → 退四循环；结束 `self.ensure_lock(lock_default)`
  恢复用户配置。普通目标不动锁定状态。`lock_default = con.general_battle_config.lock_team_enable`
  在主循环外捕获一次、每轮循环顶复位（呱太目标临时 `lock_team_enable = False` 一轮）。
- **退四次数 = 源码可证的 4 次**：`RR_EXIT_FOUR_SURRENDERS = 4` module 常量 —— 旧 `run()` 里逐字
  硬编码的 4 次 `fire_again()`，不是新拍的业务数字（不触发「no provable end condition → PARTIAL /
  BLOCKED ON BUSINESS COUNT」）。`for i in range(RR_EXIT_FOUR_SURRENDERS)`：`_fire_again()` 失败 →
  `aborted = True; break`；`is_final = i == RR_EXIT_FOUR_SURRENDERS - 1` → 第 4 次
  `con.general_battle_config`（真打）、前 3 次 `build_quick_exit_config`（投降）。
- **普通目标失败 → 按 `when_attack_fail`（默认 `REFRESH`），不重试同目标、不点「再次挑战」**。普通
  分支落 `run()` 尾部原有 `if not last_battle and when_attack_fail == REFRESH: check_refresh()` /
  `== EXIT: break`。`_fire_again()`（退四内「再次挑战」）**只在退四分支被调**，普通失败绝不调用。
- **退四中断 / 退四最终失败 → 统一走刷新**：`if aborted or not last_battle:` → `check_refresh()`
  → 成功 `continue` / CD 中 `success = False; break`。**不再点「再次挑战」**（与普通失败的刷新收敛
  一致，不停在失败页）。
- **目标级业务 pacing `RR_TARGET_PACING = (1.0, 2.5)`** 是**独立 timing owner**，与 `fire()` 的
  `REACTION_FIRE`（D001）**不合并、不叠加**——定位同 D001「长期契约」条 ⑥ 里 RyouToppa 区域 pacing
  `(1.0, 3.0)` 的地位。新增 `_enter_target(order) -> bool`：`screenshot` →
  `_target_still_attackable(order)`（= `order in self._grid_targets()`，纯只读）→
  `random_delay(*RR_TARGET_PACING)` → `sleep` → `screenshot` → `_is_realm_raid_retryable_state()` +
  `_target_still_attackable` 二次确认 → `click(C_PARTITION[order-1], interval=2)`。pacing 期间目标变
  不可打 / 离开可操作页 → **不点旧坐标、`return False`**（`run()` 重扫九宫格）。**只在每个新选定
  目标点开详情前发生一次**，不进 FIRE retry / post-click polling / 再次挑战 / battle / settlement /
  reward / refresh。此前记录的「RealmRaid 目标 pacing 1~3 秒」**作废**（RyouToppa 区域 pacing
  `(1.0, 3.0)` 属 RyouToppa，与此无关、未动）。**PROVISIONAL / Level C**——`RR_TARGET_PACING` /
  `RR_AGAIN_*`（D001 补记）改值连带更新本 ADR / D001 补记 + `docs/AI_CONTEXT.md` §4.56。
- **Fatigue Safe Point 接入 RealmRaid 主循环**（符合 D001「Fatigue Safe Point 铺开补记」）：
  `begin_fatigue_task('RealmRaid')` 在主 `while 1:` 之前；`_realm_raid_cycle_safe_break()` =
  `screenshot` → `_is_realm_raid_retryable_state()` 才 `try_fatigue_break(safe=True,
  repeat_completed=True, deadline=None)`，在普通目标 / 退四「一个完整目标业务循环（战斗 + 结果 +
  必要刷新）结束、即将回循环顶重新 `check_ticket` + 扫九宫格」处调用。**RealmRaid 无墙钟时限**
  （挑战次数由 `number_attack` 限），故 `deadline=None`。Fatigue **不进** target pacing / FIRE /
  FIRE retry / transition-unknown / battle / settlement / reward / 退四内部 / `_fire_again` 之间 /
  refresh 动画。
- **未推翻**：D001（FIRE reaction / bounded FSM，`fire()` R-R1 与 `_fire_again()` 归它）、D008
  （不引入全局自动等待）、D015（bounded retry / recovery 在 Task 层，不抽 primitive）、D016
  （GeneralBattle Settlement V3——RealmRaid 只覆写 `_handle_result` 的 quick_exit 分支和
  `_exit_matcher`，本轮未动）。`C_PARTITION_n` 坐标 / ROI / RuleClick / ClickSampler / T7 空间行为
  未动（`_grid_targets` 把 match 中心映射回 `roi_front` 后仍点 `C_PARTITION`，R-R12 仍在）。

Level C（真机窗口后验收）：`_grid_targets` 用 `find_everyone` 全格扫描的稳定性（match center →
`roi_front` 映射准确率、相邻格串位）、`_broken_orders` 对刚失败未刷新格的命中率、
`RR_TARGET_PACING (1.0, 2.5)` 体感、退四「只剩最后 1 个」判定的真机可靠性、`ensure_lock(False)` 在
退四场景确实解锁、退四最终失败刷新收敛、RealmRaid Fatigue safe point 是否稳定回到个人突破页。

**补充（2026-09-08，correctness follow-up —— CONTINUE / Fatigue 顺序 / Last Target fresh revalidate / Unlock cleanup）**：D020 落地后复核出 4 个 correctness 边界，本轮只修这 4 个（不扩新功能）。以下条目补入本 ADR，不新增 ADR：

- **RealmRaid Failure Policy 三种语义定死**（`when_attack_fail`，config 值 `Refresh` / `Continue` / `Exit`）：
  - **REFRESH**（默认）：普通目标失败 → 共享尾部 `check_refresh()` → 刷新成功 `failed_orders.clear()` → 疲劳安全节点 → 下一轮新九宫格；CD 中 → `success = False; break`。
  - **CONTINUE**：普通目标失败 → **不刷新** → `failed_orders.add(order)`（本轮 skip）→ 疲劳安全节点 → 下一轮固定 1→9 从 `_grid_targets() - failed_orders` 继续选。九宫格里所有可攻打目标都被 skip / 已破（`available` 空）→ 才 `check_refresh()` + `failed_orders.clear()`。
  - **EXIT**：普通目标失败 → 直接 `break`，不 skip、不 refresh、不为 fatigue 拖延退出、退出后不再点任何目标。
  - 退四路径的最终失败 **不受 `when_attack_fail` 影响**——一律 `check_refresh()`（D020 主条已定）。
- **`failed_orders` != `broken`**：`failed_orders` 是 CONTINUE 的**纯局部业务 set**（`run()` 内），表示「本轮业务决定不再打」，UI 上该格可能仍 attackable。`_broken_orders()` / `false_image` / broken detector 表示「视觉上已攻破 / 已失败标记」。两者**不混用**：不改 `false_roi` / `false_image` / broken detector 去表达 CONTINUE，不把 `failed_orders` 当 broken，不涂 `self.device.image`（D020 主条已禁止污染帧，本补充明确 CONTINUE 也走局部 set 而非涂帧）。`failed_orders` 只在 `check_refresh()` **成功**后清空（换新九宫格），点击 refresh 前 / CD 失败都不清。
- **Last Target Policy —— 退四判据用 raw UI 可攻打数，不用 skip 过滤后的数**：`only_last = len(targets) == 1`（`targets = _grid_targets()` 原始结果），**不是** `len(available) == 1`。理由：「只剩最后一个目标」的原业务定义是「九宫格其它目标均已破 / 不可攻击」，不是「其它目标只是本轮失败被跳过」。`failed_orders` 只影响普通固定 1→9 选目标。`raw = {5,8}` + `failed = {5}` → `available = {8}`，但 `only_last` = False，打 8 走普通分支。raw 唯一目标恰在 `failed_orders` 里 → `available` 空 → CONTINUE 走刷新，不进退四。
- **退四是高影响分支，进入前 + 点击目标前都要 fresh 重确认唯一性**：新增只读 helper `_is_only_remaining_target(order)` = `_is_realm_raid_retryable_state() and len(_grid_targets()) == 1 and order in targets`（不截图 / 不点击 / 不 sleep，截图责任在 caller）。退四块入口 `screenshot()` + `_is_only_remaining_target(index)` 不满足 → `continue` 回主循环重扫（不解锁 / 不投降 / 不 fire_again）。`_enter_target(order, require_only_remaining=False)` 加参数：`True` 时 pacing 前后的「仍可攻打」收紧成「仍是唯一可攻打目标」。普通目标 `require_only_remaining=False`，逐字不变。
- **Fatigue 必须在 failure recovery 完成之后**（D001「Fatigue Safe Point 铺开补记」的 RealmRaid 具体化）：`battle failure → fatigue → refresh` 顺序**禁止**。普通分支 battle 之后不再直接 `_realm_raid_cycle_safe_break()`；改在共享尾部每个结果流的 recovery 之后触发（普通胜利 = 尾部末尾；REFRESH 失败 = `check_refresh()` 成功后；CONTINUE 失败 = `failed_orders.add` 后；EXIT 失败 = 不触发直接 break；退四胜利 = 落尾部末尾；退四中断 / 最终失败 = `check_refresh()` 成功后）。`_realm_raid_cycle_safe_break()` 前先 `wait_until_appear(self.I_BACK_RED, wait_time=RR_CYCLE_STABLE_TIMEOUT)`（新常量 `= 10`，PROVISIONAL）——复用个人突破页固定返回键作 recovery-complete 判据，不用固定 sleep；再 `screenshot` + `_is_realm_raid_retryable_state()` 守卫才 `try_fatigue_break(deadline=None)`。
- **退四临时解锁必须用 `try/finally` 恢复**：`ensure_lock(False)` → `try:` (`_enter_target` / `fire` / 首战 `run_general_battle` / 4×(`_fire_again` + `run_general_battle`)) → `finally: self.ensure_lock(lock_default)`。`finally` **只恢复锁**——无 `except`、不吞原异常（`run_general_battle` 抛异常 → 先恢复锁再原样传播）。`lock_default = con.general_battle_config.lock_team_enable`（循环外捕获一次），不写死 True/False——用户原本不锁 → 退四后恢复不锁。退四结果分类（`if aborted or not last_battle:` → `check_refresh()`）在 `try/finally` 之外，锁已恢复、无锁变更、不进 finally。**只有 fresh-confirmed last-remaining-target + `exit_four` enabled 才进临时 unlock**；普通目标不调退四专用 unlock。
- **测试**：`tests/test_realm_raid_state.py` `63 → 93`——`CorrectnessFollowupSourceTest`(11，源码 / AST) + `RunLoopBehaviorTest`(19，`_RunHarness` 驱动 `run()` 主循环) + 改 3 处既有。回归 `1257 → 1287`。

相关文件：`tasks/RealmRaid/script_task.py`（`run()` 主循环 + `failed_orders` / `available` +
`_grid_targets` / `_broken_orders` / `find_one` / `_target_still_attackable` /
`_is_only_remaining_target` / `_enter_target(require_only_remaining=)` /
`_realm_raid_cycle_safe_break` + `RR_TARGET_PACING` / `RR_EXIT_FOUR_SURRENDERS` /
`RR_CYCLE_STABLE_TIMEOUT` 常量；`_fire_again` / `_wait_again_entered_battle` / `RR_AGAIN_*` 见
D001 补记）、`tasks/RealmRaid/config.py`（`RaidConfig`：`exit_four` / `when_attack_fail`
（`Refresh` / `Continue` / `Exit`）/ `order_attack` / `number_attack`，本轮未改字段）、
`tests/test_realm_raid_state.py`（`FindOneFixedOrderTest` / `FireAgainThreeStateTest` /
`LoopAndWaitBoundsTest` / `GeneralBattleHandoffTest` / `MainFlowRefactorTest` /
`CorrectnessFollowupSourceTest` / `RunLoopBehaviorTest`）、`tests/test_reaction_timing_batch1.py`
（`_fire_again` 一行）、`docs/RealmRaid状态机静态收口.md`（R-R1 / R-R2 / R-R3 / R-R9 由此提出）、
`module/fatigue.py`、`docs/AI_CONTEXT.md` §4.56 / §4.52、`docs/ROADMAP.md`「RealmRaid 目标选择 /
退四策略改造」。

---

## D021：Exploration Boss 完成后跳过地图宝箱，直接退出并正向确认稳定入口

**状态：Superseded（2026-09-08）** —— 「Boss 后不搜索 / 不点击地图 treasure，直接退出」这一前提基于
**错误的业务需求理解**。用户 2026-09-08 重新确认：Boss 战后应「检查地图宝箱 → 有则正常领取 → 无则
继续 → 不领取小纸人奖励 → 沿用原 Exploration 原生退出 flow」，与原项目（HEAD）一致。**当前生效的
决定见本条末尾的「D021 corrected 补记」。** 下面「Boss Completion / Treasure Policy / Exit Contract」
三段保留作历史，不代表当前架构。其中 **Chapter FrameWait 段** 与 §4.59 补记的 **Rotation Contract**
独立成立、继续有效。

决定（已被撤销，保留作历史）：Exploration 的一个 Boss 业务 cycle 以「Boss 战胜利 + GeneralBattle
settlement 完成 + 探索地图 ready + direct exit + `page_exp_entrance` positive stable」为完成边界。
Boss 后不再搜索 / 点击地图 treasure，也不以退出按钮、地图 marker 或确认弹窗消失作为成功。

- **Boss Completion**：`run_general_battle(..., exit_matcher=page_exp_main)` 的返回值必须被消费；只有
  `battle_won=True` 且本轮 `fire_monster_type == 'boss'` 才进入直退。GeneralBattle 的 result/reward / V3
  settlement 保持唯一 owner。因 GeneralBattle 保留结算后 2.5 秒 missing-page fallback，Task 需在返回后
  连续 fresh frame 正向确认 `page_exp_main`，不能把返回本身当 exit-ready。
- **Treasure Policy**：Boss production path 不调用 `collect_reward()` / `collect_treasure_box()`，退出成功后
  入口第一次 dispatch 也跳过宝箱；helper / asset 保留给非 Boss / 其它状态，不做 dead-code 扩张清理。旧
  `collect_reward()` 后半段曾由 `collect_paper_man_reward()` 在 Boss + 关闭纸人奖励时隐式触发退出；该职责
  已迁入下面的显式 Exit Contract，不再依赖 reward helper 副作用。
- **Exit Contract**：task-local 状态固定为 `EXIT_READY(page_exp_main)` → `EXIT_CONFIRM(page_exp_exit)` →
  `TRANSITION_UNKNOWN` → `EXIT_SUCCESS(page_exp_entrance)`。ACTION 复用 `quit_exp_main()`，确认复用
  `run_on_exp_exit()`；unknown 只做 finite wait，不重复按 exit。唯一 success 是 `page_exp_entrance` 的
  连续 fresh positive marker，timeout 抛 `GameStuckError` 交现有 Task recovery，不静默进入下一 cycle。
- **Chapter FrameWait**：章节 OCR asset 同时提供专属结构 ROI；只有实际发出章节 swipe 才执行
  `baseline → wait_for_changed_and_stable → 下一轮 OCR`。FrameWait `success/stable` **永远不等于 chapter
  found**，结果不改变 OCR direction / `swipeCount>=25` convergence。无 swipe 时的 1 秒保留为 retry
  throttle。ROI / changed / stable / frames / timeout / poll 均为 task-local provisional，不升级为全局参数。
- **Fatigue**：仅 Exploration solo 接入。节点必须在 exit positive success 后，deadline 使用现有墙钟
  `start_time + limit_time`；fatigue 后必须 fresh revalidate `page_exp_entrance`。leader/member 不接，
  GeneralBattle / FIRE / settlement / exit action / confirm / unknown / chapter swipe / OCR retry 内均不触发。

未选择：删 treasure helper / asset（仍有其它 consumer）；用 `goto_page` 隐去 Boss exit transaction（无法在
task contract 中清楚区分旧 marker 消失与 positive success）；把 FrameWait stable 当 OCR 成功；把 Fatigue
放在刚回地图或 exit 前；改 Exploration dynamic `fire(button)` / GeneralBattle / Navigation。

**补记（2026-09-08，Level C hotfix —— Exit Success 多态 positive + Rotation Contract）**：§4.58 首次
真机 Level C 暴露两个 correctness bug，本轮修复但不推翻上面任何条目。

- **Exit Success 判据从「单一 `page_exp_entrance`」放宽为「探索外层合法页面的多态 positive」**：真机
  点 `I_E_EXIT_CONFIRM` 后实际停在**探索模式列表 `page_exploration`**（`GameUiAssets.I_CHECK_EXPLORATION`，
  `category="global"`），而 §4.58 的 `detect_page_in(..., include_global=False)` 显式排除它、成功又只认
  `page_exp_entrance`，导致永久 `transition_unknown` → 15 秒 `GameStuckError`（用户肉眼确认早已退出成功）。
  新契约：**`EXIT_SUCCESS` = task-local `_is_boss_exit_success_state()` = `match_page_once(page_exp_entrance)
  or match_page_once(page_exploration)` 连续 2 帧**。两者都是 `exec_exp_page` 有 handler
  （`run_on_exp_entrance` / `run_on_exp`）、也都是 `check_exit → activate_realm_raid` 里
  `current_page in (page_exploration, page_exp_entrance)` 认可的合法外层页面。**仍是正向 marker 命中，
  绝不以「弹窗 / 主界面标记消失」为成功**（Exit Contract 原则不变）。允许 Exit Success 有多个合法
  positive state，但每个都必须有正向 semantic marker；`page_exp_main` / `page_exp_exit` 只用于驱动
  `EXIT_READY` / `EXIT_CONFIRM`，不参与成功判定。timeout `15.0` / ready `10.0` / stable_frames `2`
  **一字未动**（是 detector 错、不是等待不够；修 detector 后 Level C 若仍 > 15s 才考虑调）。首次进入
  `transition_unknown` + 超时前各打一条 `_boss_exit_probe()` marker 快照供 Level C 定位真实 outer 页面。
  fatigue 后 revalidate 同步改用 `_wait_for_boss_exit_success_state()`；`_skip_treasure_once_at_entrance`
  treasure bypass flag 同时被 `run_on_exp()` 的 ALONE 分支消费（Boss 直退落在探索列表也不补领宝箱）。
- **Rotation Contract：轮换模式（游戏内「自动轮换」开关）归用户所有，脚本默认 observe only**。
  §4.58 之前 `BaseExploration.switch_rotate()` 的 `case AutoRotate.no:` 会
  `appear_then_click(I_E_AUTO_ROTATE_ON)` —— `I_E_AUTO_ROTATE_ON` 是「轮换开着」marker，点它 = 取消
  轮换。config `auto_rotate`（默认 `AutoRotate.no`）→ 用户手工开着的轮换被 `run_on_exp_main` 反复点关。
  新规则：**`auto_rotate=no`（默认）时脚本绝不点 `I_E_AUTO_ROTATE_ON` / `I_E_AUTO_ROTATE_OFF` 去
  取消 / 重置 / 恢复用户的轮换状态**（`switch_rotate()` 的 `no` 分支 = `pass`）。`page_exp_main` 的识别
  本就是 `any_of(I_E_SETTINGS_BUTTON, I_E_AUTO_ROTATE_ON, I_E_AUTO_ROTATE_OFF)`，同时覆盖轮换开 / 关
  两种布局，脚本无需把轮换恢复成关闭态来维持页面识别。**例外：`auto_rotate=yes`** 是用户显式 opt-in
  的「由脚本管理候补 / 轮换」——脚本仍 `click(C_CLICK_SETTINGS)` → `fill_shikigami()` +
  `appear_then_click(I_E_AUTO_ROTATE_OFF)`（轮换关着时**打开**），只做「开」方向、从不取消用户已开的
  轮换。未来若要脚本更主动地管理轮换 OFF，需新增专门配置，当前没有。
- **不变**：Boss Completion / Treasure Policy / Chapter FrameWait / Fatigue 顺序 / Exploration dynamic
  `fire(button)` / GeneralBattle / `_exit_matcher()` / Navigation。
- **测试**：`tests/test_exploration_state.py` `48 → 66`（`BossDirectExitContractTest` 多态成功 +
  probe + timeout-not-widened；`ExplorationFatigueSafePointTest` `_wait_for_boss_exit_success_state` +
  exit-timeout-zero-fatigue；新增 `RotationOwnershipTest` / `BossExitSuccessStatePredicateTest` /
  `RunOnExpTreasureSkipTest`）+ `tests/test_reaction_timing_batch1.py` 同步。回归 `1313 → 1331`。

> **上面这条 §4.59 补记的「Exit Success 多态 positive」部分连同 §4.58 的整个 Exit Contract 已被下方
> 「D021 corrected 补记」撤销。本条补记里的 Rotation Contract 段独立成立、继续有效。**

**D021 corrected 补记（2026-09-08，当前生效）—— 恢复原生 Boss reward / exit 链**：用户重新确认
Exploration Boss 战后的真实业务需求 = 原项目一直以来的做法：

- **地图宝箱：检查 + 有则正常领取 + 无则继续**。`run_on_exp_main → collect_reward() =
  collect_treasure_box() or collect_paper_man_reward()`。`collect_treasure_box()` 识别到
  `I_E_REWARD_BOX_SMALL` / `I_E_REWARD_BOX_BIG` → `ui_click(box, I_REWARD)` +
  `ui_click_until_disappear(I_REWARD)` `return True`；无宝箱 → `return False`（多宝箱 / repeated
  dispatch 天然处理）。**不为简化而跳过 treasure。**
- **小纸人奖励：不领取**（配置 `exploration_config.collect_paper_reward`）。`collect_paper_man_reward()`
  里 `fire_monster_type == 'boss' and not collect_paper_reward` → `logger.info("Not collect paper doll
  reward")` + `quit_exp_main()` + `return True`——**原项目本就有这条原生「打过 Boss + 不领小纸人 →
  退出」链**，直接复用，不新造第二套 Boss direct-exit owner。收小纸人 / 未打 Boss 时 `I_BATTLE_REWARD`
  出现则 `ui_get_reward`。**地图 treasure 与小纸人是两个独立开关，不得混成一个。**
- **退出：复用原生 flow**。`quit_exp_main()` = `appear_then_click(I_UI_BACK_YELLOW, interval=0.8,
  confirm_delay=REACTION_NAVIGATION)` → `page_exp_exit` → `run_on_exp_exit()` → `I_E_EXIT_CONFIRM`
  （`confirm_delay=REACTION_CONFIRM`）→ `exec_exp_page` 的 page-dispatch 自然接管外层页
  （`page_exp_entrance` / `page_exploration` → `run_on_exp_entrance` / `run_on_exp`）。**不新造 Boss
  专用 exit transaction / EXIT_READY..EXIT_SUCCESS 状态机。**
- **自动退出场景**（Level C：无地图宝箱时游戏可能自动结束探索跳外层页）：**不新造 Auto Exit FSM**。
  page-dispatch 天然接管；`quit_exp_main` / `run_on_exp_exit` 的 `appear_then_click(confirm_delay=)`
  在 reaction delay 后**重新截图二次确认**目标 marker，已消失则不点 —— 天然避免 stale click（§4.51
  `confirm_delay` 语义）。**只有真机证明原生 `quit_exp_main` 会在页面已自动离开后 stale click，才加
  最小 current-page guard；本轮判定无需，未加。**
- **撤销的 §4.58 / §4.59 结构**（全仓 consumer audit 后确认只服务错误需求）：`ExplorationExitState`
  枚举、`BOSS_EXIT_*` 常量、`_resolved_page` / `_wait_for_stable_page` / `_set_exit_state` /
  `_is_boss_exit_success_state` / `_wait_for_boss_exit_success_state` / `_boss_exit_probe` /
  `_run_boss_exit_transaction` / `_complete_boss_business_cycle`、`_skip_treasure_once_at_entrance`
  flag（`run_on_exp_entrance` / `run_on_exp` 两处 `collect_treasure_box()` 恢复无条件）、`run_on_battle`
  的 `battle_won` 捕获 + `_complete_boss_business_cycle` 调用（恢复 HEAD 原生
  `run_general_battle(exit_matcher=page_exp_main)` + `_match_end.refresh()`）。**未用 `git checkout` /
  `restore` / `reset` 回滚——做的是语义级手工收敛。**
- **Fatigue（solo）保留，Safe Point 重挂到原生 cycle**：`run()` 里 `begin_fatigue_task('Exploration')`
  （仅 ALONE）保留。新增 `_maybe_boss_cycle_fatigue()`，在 `run_on_exp_entrance` / `run_on_exp` **顶部**
  调用（这两个 handler 只在 `get_current_page()` 正向命中 `page_exp_entrance` / `page_exploration` 时
  才分发 = 已在合法外层稳定页），仅当 `user_status == ALONE` 且刚完成的是 Boss 循环
  （`fire_monster_type == 'boss'`，handler 稍后才重置）→ `try_fatigue_break(safe=True,
  repeat_completed=True, deadline=start_time+limit_time)` + 消费 Boss 标记 + 让调用方 `return`
  （交下一轮 fresh dispatch = fatigue 后 fresh revalidate）。**禁止在 `page_exp_main`（地图宝箱 /
  小纸人 policy / 退出未完成）触发**——`run_on_exp_main` 不调用它。禁止在 treasure 未处理完 / 小纸人
  policy 未完成 / 仍在 `page_exp_main` 时 fatigue。
- **独立成立、保留不动**：§4.58 Chapter FrameWait（`_wait_chapter_list_settle` + `EXPLORATION_LEVEL_*`
  6 provisional 参数，PARTIAL / Level C）、§4.59 Rotation Contract（`switch_rotate()` `AutoRotate.no`
  = observe only）、`fire(button)` / `_exit_matcher()` / §4.51 `confirm_delay` reaction / GeneralBattle。
- **测试**：`tests/test_exploration_state.py` `66 → 56`（−10 全为删掉的废弃 contract 用例——
  `BossDirectExitContractTest` 12 + `BossExitSuccessStatePredicateTest` 6 + `RunOnExpTreasureSkipTest`
  3 + `ExplorationFatigueSafePointTest` 依赖 `_complete_boss_business_cycle` 的 3；新增
  `BossRewardFlowNativeTest` 8 + `BossCycleFatigueTest` 7）。回归 `1331 → 1321`，0 regression。

相关：`tasks/Exploration/script_task.py`（原生 `run_on_battle` / `run_on_exp_main` / `run_on_exp_entrance`
/ `run_on_exp` + 新 `_maybe_boss_cycle_fatigue`）、`tasks/Exploration/base.py`（`collect_reward` /
`collect_treasure_box` / `collect_paper_man_reward` / `quit_exp_main` 原生，本轮零改动；§4.58
FrameWait + §4.59 `switch_rotate` 保留）、`tasks/GameUi/default_pages.py`（`page_exploration =
Page(I_CHECK_EXPLORATION, category="global")`）、`tests/test_exploration_state.py`、`docs/AI_CONTEXT.md`
§4.58 / §4.59 / §4.60。

---

## D022 普通滑动端点空间分布：业务给方向 / 距离，端点采样层给具体起终点，`TouchSwipeModel` 给中间轨迹

状态：Accepted（2026-09-08 Level C：当前 `SwipeEndpointParams` 默认值经多轮 MuMu 真机观察接受，
在无新反例前**冻结**——见本条末「Level C 补记」）
日期：2026-09-08

背景：OASX 行为统计（`GET /stats/.../behavior/clicks?interaction_type=swipe`）显示同类
`swipe` 的**起点挤成一簇、终点挤成一簇、轨迹高度重合**——`TouchSwipeModel` 的中段曲线
每次都在变，但上层给它的起终点几乎固定。根因不是「起终点共享同一个平移量」（`RuleSwipe.coord()`
本来就对 `roi_front` / `roi_back` 各采一次），而是大量 swipe 资产的 `roi_front` / `roi_back`
只有 ~21×21 甚至 4×4 / 2×4，`random_center_point_in_roi` 的 3 次采样均值（Bates）在这么小的
框里有效标准差只有 3~6px。2026-09-08 落地 v2 端点采样器 + 本 ADR 固化分层。

决定（普通滑动的长期分层，从「方向意图」到「设备执行」）：

- **业务层 = `RuleSwipe(roi_front, roi_back)`**：只用两个 ROI 的相对位置表达「往哪个方向、
  滑多远」。业务**不**指定具体像素起终点，也**不**关心分布形状。
- **端点采样层 = `module/atom/swipe_endpoint.py` 的 `sample_swipe_endpoints(roi_front, roi_back)`**
  （唯一公共责任点，沿用 `module/click_sampler.py` 的「点击空间模型」思路）：把这对 ROI
  变成一次滑动的**具体整数起点 / 终点**。
  - **起点、终点各自独立采样**——严禁「给整条线加一个共同偏移」（那只是把同类滑动平移成
    一簇平行线，起终点仍过度固定）。
  - 每个端点：参照点 `preferred` = 该 ROI 整数取值范围几何中点（**不发明业务坐标**）；
    「游走尺度」由**业务基准距离**（两 ROI 中点距离）按比例推出，夹在 `[offset_min_px,
    offset_max_px]`（短滑少游走、长滑多游走、有绝对上限）；主成分（~85%）= 以 `preferred`
    为中心的窄高斯，尾部（~15%）= 更宽高斯；二选一后按轴采样。
  - **轴向 ROI 足够大（`>= wide_axis_px`，默认 48px）的那个轴，逐字保持旧
    `_center_biased_int`**——作者已用大 ROI 表达期望散布（`S_BATTLE_RANDOM_*` 480×426 /
    Summon `S_RANDOM_SWIPE_*` 100~480px），不去二次收缩。**两端两轴都大 → 整条 short-circuit
    等价旧 `coord()`（连联合校验都不做）**，`S_BATTLE_RANDOM_*` / `S_RANDOM_SWIPE_*` 分布不变。
  - 高斯样本必须落在 `[preferred ± hard_half] ∩ 屏幕安全边界`（且不小于原 ROI 范围）内，
    有限次 rejection，用尽 → 回退该轴中心（**不对越界样本做边界 clamp**，避免边缘堆积，与
    D014 一致）。
  - **联合校验**（起终点都采完）：采样向量与业务向量夹角 `<= ~acos(min_cos)`（默认 ~25°）、
    采样距离 ∈ `[min_dist_ratio, max_dist_ratio] × 基准距离` 且 `>= abs_min_dist_px`（默认
    10px，避免落进 `BaseTask.swipe_trajectory` 的 <10px 端点回退）、业务主轴方向符号一致。
    不满足 → **整体重采样，`joint_max_attempts` 次用尽 → 确定性回退到
    `(preferred_start, preferred_end)` 两个中点**（一定过校验）。**全程有界，无 `while True`。**
- **`TouchSwipeModel` = 「两个端点之间怎么走」**：minimum-jerk + 曲率 + 逐段 dt + 尾段慢拖
  （D018）。**本轮一字未改**——端点分布与中间轨迹是两件正交的事，不同时改（否则 Level C
  无法归因）。
- **执行层 = `Control` / minitouch`**：把点列发给设备（D018）。

接线：`RuleSwipe` 新增 `sample_endpoints()`（委托 `sample_swipe_endpoints`）；`BaseTask.swipe`
的 `swipe.coord()` → `swipe.sample_endpoints()`（唯一改动点，~50 个 `self.swipe(S_*)` 生产
consumer 透明迁移）。**`RuleSwipe.coord()` 本体不改**——保留给兼容 / 测试 / 回归对比，仍是
「严格 ROI 内中心偏置」。BehaviorTrace **天然记录真实采样端点**（`swipe_trajectory` 的
`extra.start_x/y` / `end_x/y` 取自 `TouchSwipeModel.generate` 精确固定的首末点），无需改
`module/behavior_trace.py` / `Control`。

不改 / 不迁（各有原因，保持 legacy）：`RuleSwipe.coord()` 语义；`BaseTask.list_find` 翻页
（`RuleList.swipe_pos` + `device.swipe`，D013 明令翻页几何不动）；`KekkaiUtilize._perform_search_swipe`
（K1~K4 自建 `SWIPE_START_X_RANGE` / `SWIPE_DISTANCE_RANGE` / `SWIPE_LATERAL_OFFSET_RANGE`
→ 直接喂 `TouchSwipeModel`，Level C 已连测）；`KekkaiUtilize.perform_swipe_action` /
`KekkaiActivation` 好友卡 `swipe_adb`（距离敏感、独立 K 式）；`RyouToppa.flush_area_cache`
（依赖 `duration=`，D003）；`Control.drag` / `drag_*` / `tasks/Chess/runtime/press_and_drag.py` /
`AbyssShadows.move_a_little`（摇杆，D018「永不按普通 swipe 迁移」）。

不写进本 ADR（Level C 可调）：`SwipeEndpointParams` 的全部默认值（`wide_axis_px` /
`offset_dist_ratio` / `offset_min_px` / `offset_max_px` / `clamp_sigma_mult` / `clamp_dist_ratio` /
`core_weight` / `core_sigma_frac` / `tail_sigma_frac` / `axis_max_attempts` / `min_cos` /
`min_dist_ratio` / `max_dist_ratio` / `abs_min_dist_px` / `joint_max_attempts` / 屏幕安全边界）
——全部 provisional 工程默认，等真实滑动的起终点 / 距离 / 方向分布标定；真机是否被游戏识别为
「滑动」而非「点击」、连续滚动量差异、宽 ROI short-circuit 是否够 —— Level C 待验收，不得标
VERIFIED。

原因：端点采样是纯函数、最易测、与设备解耦（与 `ClickSampler` 同构）；把端点分布塞进
`TouchSwipeModel` 会让「端点在哪」和「中间怎么走」耦合、Level C 无法归因；塞进 `Control.swipe`
会污染整个 control layer。对大 ROI 保持旧 `_center_biased_int` 是「只治真正过度固定的小框、
不动作者有意的大散布」的最小侵入选择。

禁止 / 注意事项：不要给整条滑动线加共同偏移（起终点必须各自独立采）；不要在本层改
`TouchSwipeModel` 的轨迹 / dt / 曲率 / pressure；不要把端点采样入口塞进 `BaseTask`（god class
约束，与 D014 `sample_point` 不进 `BaseTask` 一致）；不要用 `sample_endpoints()` 去迁 `list_find`
/ drag / press-and-drag / 摇杆 / `swipe_adb` 直连路径；不要因为「统一」把 `RuleSwipe.coord()`
删掉或改语义；`SwipeEndpointParams` 默认值调整必须走 Level C，不在静态轮次里凭感觉改。

相关文件：`module/atom/swipe_endpoint.py`（`SwipeEndpointParams` / `sample_swipe_endpoints` +
私有 `_sample_axis` / `_sample_one_endpoint` / `_direction_distance_ok`）、`module/atom/swipe.py`
（`RuleSwipe.sample_endpoints()`，`coord()` 保留）、`tasks/base_task.py`（`BaseTask.swipe` 改调
`sample_endpoints()`）、`tests/test_swipe_endpoint_sampling.py`（36 用例）、
`tests/test_base_task_swipe_trajectory.py`（`test_swipe_delegates_...` 改 patch `sample_endpoints`）、
`docs/AI_CONTEXT.md` §4.61 / §7、`docs/ARCHITECTURE.md`「滑动」链、`docs/ROADMAP.md`。
与 D006（`RuleSwipe` 只提供端点——本 ADR 是「端点怎么给」的细化，未加轨迹生成）/ D007（公共
随机源，复用 `random_normal` / `_center_biased_int` / `_rng`）/ D014（点击空间模型、`ClickSampler`
同构、`_center_biased_int` 仍只用于 swipe 端点）/ D018（`TouchSwipeModel` / `swipe_trajectory`
不变）一致，均未推翻。

### Level C 补记（2026-09-08，defaults 冻结）

**上面「不写进本 ADR（Level C 可调）」列出的 `SwipeEndpointParams` 全部默认值仍是 provisional
工程默认，但本轮起在无新真机反例前冻结、静态轮次不再调整。** 保留原始 provisional 表述作历史。

- **依据**：用户连续多轮 MuMu 真机运行，通过 OASX「统计 → 点击位置与滑动轨迹」页连续观察真实
  执行的 start / end / trajectory（BehaviorTrace 最终数据；最新一日样本约「点击 590 / 滑动 42」）。
  观察结论：同类横向 swipe 起点不再钉死为单点、形成**明显但仍集中**的 endpoint cloud；终点形成
  独立小范围分布；start / end 非共用整体 offset；多条横向 trajectory 不再完全重合（轻微高度 /
  角度差），主方向明确、无反向；无极端短 / 极端长 swipe、大角度错误斜滑、endpoint 飞散；同图纵向
  swipe 无异常；连续使用未报告误触 / 滑不动 / 滑过头 / 业务状态错误 / Kekkai 回退 / Exploration
  swipe 回退。用户判断「看样子可以」。
- **结论范围**：这是**当前 ordinary swipe 业务下的 Level C 真机行为验收通过**——不等于「大规模
  统计学参数拟合完成」或「所有未来业务 swipe 的永久最优 / 全局最优分布」。当前状态（endpoint
  有变化但仍集中、trajectory 有变化但方向稳定）**正是预期目标**：「解除固定 endpoint + 保持业务
  稳定」已达成，继续扩大随机范围反而增加误触控件 / 起终点进危险区 / scroll 距离漂移 / OCR·FrameWait
  收敛变化 / 小 ROI 业务失败的风险。
- **冻结项**：`wide_axis_px` / `offset_dist_ratio` / `offset_min_px` / `offset_max_px` /
  `clamp_sigma_mult` / `clamp_dist_ratio` / `core_weight` / `core_sigma_frac` / `tail_sigma_frac` /
  `axis_max_attempts` / `min_cos` / `min_dist_ratio` / `max_dist_ratio` / `abs_min_dist_px` /
  `joint_max_attempts` / 屏幕安全边界 —— 一律不因「还能再随机一点」在静态轮次改动。
- **重新打开 calibration 的条件**（否则 D022 保持 closed，不要求每次业务更新重做 swipe 校准）：
  ① 某页面 swipe 误触控件；② 某业务 swipe 距离不足 / 明显过滑；③ start·end 落入危险可点区；
  ④ direction guard 失败 / 采到反向 swipe；⑤ BehaviorTrace 记录的 start·end·trajectory 与设备
  实际执行不一致；⑥ 新 OASX 统计图重新出现极端 endpoint 聚集 / 大面积飞散；⑦ 某特殊 consumer
  （K1~K4 / `list_find` / `swipe_adb` 直连 / drag / press-and-drag / 摇杆）被错误接入公共 sampler。
- **本轮无代码 / 测试变化**：`module/atom/swipe_endpoint.py` / `swipe.py` / `tasks/base_task.py` /
  `tests/test_swipe_endpoint_sampling.py` 与上一轮 D022 落地报告逐字一致；`TouchSwipeModel` 仍
  一字未改（minimum-jerk / 曲率 / MOVE dt / tail / 精确端点 / pressure / dwell 均不在本轮范围）。

## D023 KekkaiUtilize Scheduler v1：candidate → quiet normalize → set_next_run 单向管线，quiet 是 scheduler timing owner、不替代业务语义

状态：Accepted
日期：2026-09-11

背景：Inventory（`docs/DEVELOP_LOG.md` 2026-09-10 同名条）还原出 KekkaiUtilize 当前 5 处
`set_next_run` 出口各自硬编码 5/10/20 分钟或走 OCR 剩余寄养时间，且项目已有两条"时间窗"先例
——AntiBan 全局睡眠窗（`script.py::_in_sleep_window`/`_next_time_point`，内存覆盖、无持久化、
无 jitter）与 Server-Update 全局阻塞窗（`tasks/Restart/server_update.py`，`task_delay(target=)`
持久化、固定 09:15 无 jitter）——但都不是"单任务 + 带随机恢复抖动"的形状。本轮需要一个可复用的
落地模式，同时严禁「cooldown + quiet jitter 两次随机抖动叠加」。

决定：

- **单向管线，唯一持久化出口**：业务侧先算出 `candidate_next_run`（正常寄养 = OCR 剩余时间 +
  `min_run_interval` 地板；短期失败 = `now + random(cooldown_min, cooldown_max)` 分钟）→ 统一喂给
  `normalize_for_quiet_window(candidate, ...)` 做**一次**静默窗口归一化 → 结果通过
  `BaseTask.set_next_run(target=final, server=False)` 写回。**不允许**任何分支绕过这条管线直接
  `set_next_run(target=候选值)`，也不允许 normalize 之后再叠加任何其它随机延迟。
- **quiet window 判定与归一化是纯函数，task-local 独立实现**（`tasks/KekkaiUtilize/scheduling.py`：
  `is_in_quiet_window` / `next_quiet_window_end` / `normalize_for_quiet_window`）——`[start, end)`
  半开区间语义，`start >= end` 自动按跨午夜处理，`jitter_seconds` 由调用方预采样传入使其保持
  100% 确定性。算法思路与 AntiBan 的 `_in_sleep_window`/`_next_time_point` 一致，但**不 import
  `script.py`**——避免把一个 task-local 需求绑死到顶层 orchestrator，也避免为复用而改动 AntiBan。
- **quiet window 是 scheduler timing owner，不是业务 owner**：`quiet_window_enable`/`quiet_start`/
  `quiet_end`/`quiet_resume_jitter_min`/`max`/`cooldown_min`/`max` 六个新字段挂在
  `UtilizeScheduler`（`Scheduler` 子类）而不是 `UtilizeConfig`（业务配置），类型沿用
  `AntiBan.sleep_start`/`sleep_end` 同一套 `Time`，不发明新的 time-range 类型。
- **cooldown 不替代正常寄养的 OCR remaining 语义**：唯二两类候选值来源——「正常寄养」（OCR
  剩余寄养时间 + `min_run_interval` 地板，典型数小时级）与「短期 retry」（5~30 分钟随机
  cooldown，用于"未找到达标结界卡 / 好友列表刷新失败"等短期失败）——是两个不同语义、不同量级
  的 owner，quiet normalize 只负责"候选值落不落窗"，**不改写候选值本身的来源逻辑**。
  `utilize_enable=False` 时的通用 `success_interval=6h` 路径本轮明确排除在这条管线之外（它走
  `task_delay` 的 `success=True` 相对区间分支，不是自算 target，量级也不属于"短期 retry"）。
- **`run()` 入口 task-local quiet guard 作为独立防御层**：`_guard_quiet_window()` 在 `run()`
  最开始、任何 `goto_page`/截图/OCR/点击之前执行——即使 scheduler 意外在静默窗口内唤醒任务
  （例如手动 `task_call` 强制插队、或用户手改配置把 `next_run` 落进窗内），业务也不会真正执行，
  只会重新计算 `final = quiet_end + jitter` 并立即 `set_next_run` + `TaskEnd`。**第一版不改**
  `Script.get_next_task()` / AntiBan / 通用 `TaskScheduler` pick 逻辑——quiet guard 只是
  KekkaiUtilize 任务自己的入口防御，不是新的调度器分层。
- **配置层跨字段校验用 `field_validator`，不用 `model_validator`**：`UtilizeScheduler` 继承
  `ConfigBase`（经 `Scheduler`），而 `ConfigBase.__init__` 的越界恢复逻辑是
  `exc.errors()[0]['loc'][0]` 取出单个字段名做默认值回退——只覆盖 pydantic 内建的
  `ge`/`gt`/`le`/`lt` 单字段约束错误。`model_validator(mode='after')` 产生的是模型级错误
  （`loc` 为空元组），会让这段恢复逻辑直接 `IndexError` 崩溃（本轮实测复现）。凡是
  `ConfigBase`/`Scheduler` 子类要做"字段 B 不小于字段 A"这类跨字段校验，一律用
  `field_validator('B', mode='after')` + `info.data.get('A')`（参见 `tasks/Dokan/config.py`
  既有 `@field_validator(..., mode='after')` 先例），使错误 `loc` 落在具体字段上。**纯
  `BaseModel`（非 `ConfigBase`）子类不受此限制**（如 `tasks/GlobalGame/config.py` 的
  `RestCooldownConfig` 用 `model_validator` 完全没问题）——这是两套不同的基类，不要混用判断。
- **随机源统一 `module.base.utils.random.random_int`**（`SystemRandom`）：`_quiet_jitter_seconds`
  与 `_build_retry_target` 均走它。`Config.task_delay()` 里既有的 stdlib `random.randint`
  （`server_update` 分支）是历史遗留，本条 ADR **不** 追认它为可复制的写法，新代码一律不模仿。

不改：好友列表扫描 / 卡种筛选 / 收益阈值 / OCR / 不领奖逻辑 / 满级检查·替换逻辑（下一轮）；
`goto_page` 失败 U3 技债（下一轮）；`Script.get_next_task()` / AntiBan / 通用 `TaskScheduler`；
RealmRaid（§4.63 独立收口，Level C 仍 pending，本轮未触碰）。

Level C 待验：00:00~07:00 静默窗口内 KekkaiUtilize 确实不会被真正启动（任务开始时间戳观测）；
正常寄养后 `next_run` 仍符合 OCR 剩余寄养时间语义；短期 retry 5~30 分钟随机分布体感；
`quiet_resume_jitter_min/max`、`cooldown_min/max` 默认值是否合适——这些数值本身仍是
provisional，调整时不需要改本条 ADR 的分层决定，只需在 `docs/AI_CONTEXT.md` §4.64 追记。

## D024 后端 config bool 字段 = 前端自动出现的开关：OASX 是纯 schema-driven 表单，业务能力退休一律走「开关，不删代码」

状态：Accepted
日期：2026-09-11

背景：KekkaiUtilize 计划新增「是否自动检查满级并替换式神」的前端可配置能力，且已有
`utilize_harvest`（是否领取寄养奖励）字段但不确定 OASX 是否已展示。本轮 READ ONLY 核实 OASX
（`d:\oas_xy\OASX`）配置渲染机制，确认整条链路完全 schema-driven，为本次改动、也为未来任何任务
新增简单配置字段定下一条可复用的判断依据。

决定：

- **OASX 任务配置面板是通用组件，不是每个任务各写一份**：`TaskParameterPanel` → `Args`
  （`lib/modules/args/`）→ `ArgsController.loadGroups()` 调用 `ApiClient().getScriptTask(config,
  task)` 拉取 JSON → `ArgumentModel.fromJson()` 按 `type` 字符串分发 → `ArgumentView` 的
  `switch (model.type) { 'boolean' => Checkbox(...), 'integer'/'number' => 文本框, 'enum' =>
  下拉框, 'time'/'time_delta'/'date_time' => 对应 picker, ... }`。全程按 `type` 字符串做**通用
  分发**，没有任何 `if taskName == 'KekkaiUtilize'` 这类硬编码分支，全仓 grep "kekkai" 只命中
  菜单 i18n 文案和 BehaviorTrace 展示名，没有专属配置页面。
- **`type` 字符串直接来自后端 pydantic 的 `model_json_schema()`**：`module/config/config_model.py
  ::ConfigModel.script_task(task)` 调 `task.model_json_schema()`，`merge_value()` 把每个字段的
  schema `type`（`bool`→`"boolean"`、`int`→`"integer"`、`float`→`"number"`、`str`→`"string"`，
  `Time`/`TimeDelta`/`DateTime` 走 `tasks/Component/config_base.py` 的 `WithJsonSchema` annotation
  产出 `"time"`/`"time_delta"`/`"date_time"`）逐字透传给前端。**任何 `ConfigBase`/`BaseModel`
  子类新增一个裸 `bool` 字段，下次前端重新拉取该任务的 args（切换任务 / 重新打开配置面板）就会
  自动出现一个 `Checkbox`，不需要改 OASX 一行代码**——唯一的隐藏机制是显式
  `dynamic_hide(*fields)`（`field_serializer` 配合 `context={'hide': True}` 输出哨兵值
  `0xABCDEF` 后被 `merge_value`/`update_scheduler` 跳过），`tasks/KekkaiUtilize/config.py`
  当前没有对任何字段调用它。
- **`utilize_harvest` 结论**：字段已存在、未被 `dynamic_hide`，按上述链路**本就会**出现在 OASX
  的 KekkaiUtilize 配置面板（用户下次打开该任务配置即可看到），**不新增第二个重复字段，不改
  默认值**（`True`，维持既有用户行为）。**已知的唯一间隙**：OASX 的 `cn_parts/*.dart` i18n 文件
  当前没有 `utilize_harvest`/`utilize_harvest_help` 的中文翻译条目，界面会显示 pydantic 自动生成
  的英文 Title Case 标题（`"Utilize Harvest"`）而非中文——这是纯文案缺口，不影响开关本身是否
  显示，按 Branch A「确认能自动显示就不改 OASX」的口径本轮**不**为此新增翻译，留给用户或后续
  轮次决定是否需要。
- **业务能力退休的标准做法：加开关，不删代码**——`check_max_lv()` / `unset_shikigami_max_lv()` /
  `switch_shikigami_class()` / `set_shikigami()` 全部原样保留，只在唯一调用点
  `KekkaiUtilize.run()` 套一层 `if con.auto_replace_max_level:`。新字段
  `UtilizeConfig.auto_replace_max_level: bool = False` 与 `utilize_harvest` 并列放在
  `UtilizeConfig`（业务配置类），不是 `UtilizeScheduler`（D023 的调度配置类）——区分标准：
  「要不要执行这段业务逻辑」是业务开关，「什么时候执行 / 多久执行一次」才是调度字段。
- **默认值语义不同、都是有意的**：`utilize_harvest` 默认 `True`（维持既有用户已经在跑的行为，
  改默认值等于替用户静默改变正在生产运行的任务）；`auto_replace_max_level` 默认 `False`（这是
  一个全新字段，新增字段引入新行为时默认关闭，不默认继承旧代码里「无条件执行」的隐式行为，
  用户需要显式打开才启用满级检测/替换）——**新字段默认关闭 ≠ 旧字段默认值也要跟着改**，两条
  规则不冲突。

不改：好友列表扫描 / 卡种筛选 / 收益阈值 / OCR / `KekkaiUtilize Scheduler v1`（`quiet_window`/
`cooldown`，D023，本轮未碰）/ `goto_page` 失败 U3 技债 / RealmRaid；OASX **零代码修改**（本 ADR
的核心结论就是不需要改）。

推广价值（不止 KekkaiUtilize）：以后任何任务想要新增一个简单的 bool/int/str/enum 业务开关，
默认应该先假设「后端加字段、前端自动出现」成立，用本 ADR 记录的 `model_json_schema() →
ConfigModel.script_task() → ApiClient().getScriptTask() → ArgumentModel → ArgumentView` 链路
自行核实，而不是默认需要改 OASX；只有确认字段被 `dynamic_hide` 或确实需要新的字段类型（现有
`type` 分支之外的形态，例如列表编辑器、富文本、专属可视化控件）时才需要碰前端代码。

## D025 GeneralBattle Settlement Micro-Burst：segment budget 有界、semantic state 决定 lifecycle 完成、anchor persistence 服从安全区域交集

状态：Accepted（当前有效版本 v1.2）
日期：2026-09-12（v1 落地）；2026-09-12（v1.1 修订）；2026-09-14（v1.2 Level C 修订）

> 当前有效契约以本条末尾的 **v1.2 Level C 修订**为准。下方 v1/v1.1 的 `total_budget=2~4`
> lifecycle 硬上限仅保留作历史记录，已被真机失败证据推翻。

背景：Settlement Contract V3（D014/D016）已把结算点击收敛成「三个 Large Safe Region + 节流
间隔」，但通用结果页首帧仍是写死的「强制两次点击，各自独立采样」（`_advance_generic_result`），
且结果页/奖励页之外的所有后续帧都退回「每次独立随机一个新点」的单次节流点击——不像真人那样
会在同一个位置连续点几下。本轮把这一段升级为 Settlement Click Session：一次结算生命周期
（`page_battle_result` → `page_reward` → 离开）内维护一份总点击预算与可复用的 anchor，替代旧的
固定两次序列。

决定：

- **总点击预算是上限，不是必须执行的次数**：进入结算 session 时用
  `_sample_settlement_budget()` 抽一次 `total_budget ∈ {2,3,4}`（单次 `random_int(1,10)` 分桶
  1~5→2 / 6~8→3 / 9~10→4，权重 50%/30%/20%，不引入加权采样库）。真实页面提前进入 terminal
  （不再是 `page_battle_result`/`page_reward`，`_handle_result`/`_handle_reward` 根本不会再被
  调用——page-dispatch 结构未改）就立即停手，剩余预算作废，绝不为了「点满」继续点击已经离开的
  页面。
- **一次 micro-burst 硬上限 2 次，且必须复用同一个 anchor**：`_sample_settlement_burst_size()`
  从 `{1,2}` 均匀二选一、夹到剩余预算，得到「desired burst size」。burst 内连续点击使用完全
  相同的坐标（`context.settlement_anchor` 只在 session 初始化 / 状态前向变化时才可能被重新
  采样，同 burst 内绝不重新采样），中间只隔 `SETTLEMENT_BURST_CLICK_INTERVAL_RANGE`（新常量，
  见下）。
  **★ v1.1 修订**：v1 最初的实现是「desired burst size==2 就无条件连点两下，中间只隔
  `time.sleep`，不做任何页面观察」——这留了一个窗口：如果第一下点击已经把页面从结算推进到
  Challenge/FIRE，第二下盲点仍可能在状态机重新截图/分类之前先落到新页面上。v1.1 把第二下的
  **实际执行**改为必须先经过一次 mid-burst fresh 语义观察（Option A，最小侵入——保留
  「预抽 desired burst size」这个概念，只收紧第二下何时真正触发，不是 Option B「先固定点一下
  再随机决定要不要补」）：第一下点击后，若 `desired_burst_size>=2` 且预算未耗尽，
  `time.sleep(SETTLEMENT_BURST_CLICK_INTERVAL_RANGE)`（沿用同一常量，语义从「两次盲点间隔」
  收紧为「点击→观察前等待」）→ `self.screenshot()` → 新增私有 helper
  `_classify_general_battle_page()`（纯转发 `GameUi.detect_page_in`，与主循环用的是**同一个**
  matcher/classifier，不新造第二套页面分类逻辑，不接 FrameWait 的 changed/stable 像素判定）→
  按观察到的页面分支决定：观察结果仍等于点击前的 `current_page`（语义上还是同一个结算
  state）→ 才允许用同一 anchor 补第二下；观察到已经推进到**另一个**已知结算页
  （`page_battle_result`/`page_reward` 之一但不等于 `current_page`）→ 当前 burst 立即结束，
  不在旧 state 上补点，新 state 交给下一次 `_settlement_burst_step` 调用通过既有
  `_advance_settlement_anchor` 重新决定 anchor；观察到已知的非结算页（`page_battle_prepare`/
  `page_battle`，即 Challenge/FIRE 相关）→ 立即 `_teardown_settlement_session()`，不补点、
  不武装节流计时器；观察到 Unknown（`None`，四个已知页面都未确认）→ 不补点，但**不**
  teardown（不能因一次识别失败就断定已离开结算），交回既有 `_handle_missing_battle_page` /
  2.5s 兜底。任何分支下，一次调用最多点 2 次，第二下之后无论走哪个分支都直接交回主循环下一次
  fresh classify，不产生第三下——burst 结束后仍然不做任何**额外**的页面探测（这一点未变），
  只是「要不要点第二下」这一步骤本身现在天然包含了一次观察。
- **状态允许合法前向跳级，FSM 判据保持「已知前向状态集合」而非放宽成「不是当前页就算成功」**：
  `page_battle_result` → `page_reward` 之间即使某一帧被 burst 跳过（例如两次快速点击直接从结果页
  推进到奖励页而没有单独观察到中间帧），下一次 `_handle_reward` 调用时
  `context.settlement_session_active` 已经是 `True`、`context.last_page != page_reward` 触发
  `_advance_settlement_anchor` 而不是报错；若从未经过 `page_battle_result`（直接在 `page_reward`
  首次触发结算），`_settlement_burst_step` 一样能正确从「未初始化」状态直接
  `_start_settlement_session`。这两种跳级路径都不需要新的容错分支——`_settlement_burst_step`
  只区分「session 是否已初始化」与「当前页是否等于上一帧页」两个既有信号，天然覆盖跳级。
  Unknown / terminal 状态完全不在 `_handle_result`/`_handle_reward` 的职责范围内，继续交给未改的
  `_handle_missing_battle_page`（2.5s 兜底）与 page-dispatch。
- **anchor persistence 必须服从安全区域交集，不能为了「同点拟人化」牺牲安全**：状态前向变化
  （`context.last_page != current_page`）时，`_advance_settlement_anchor()` 先做**安全校验**——
  旧 anchor 是否落在新状态适用安全区域的 `roi_front` 内（`_point_in_roi`）。不安全 → **强制**
  重新采样（安全 fallback，不计入「主动换点」次数）。安全 → 才按概率
  （`SETTLEMENT_ANCHOR_KEEP_PROBABILITY`，PROVISIONAL 默认 50%）决定保留还是主动换点，且**全
  session 最多允许 1 次主动换点**（`context.settlement_anchor_switches` 上限 1），避免
  `A→B→C→D` 频繁重新随机。同一页面内（`last_page == current_page`）默认无条件复用原 anchor，
  不触发任何安全校验或换点判断。
- **Reward 的 layout-aware 安全区域策略保持不变，只是接入点变了**：`_select_reward_region()`
  本体一字未改（marker → DEFAULT，否则 80/20）；burst 只在 session 初始化 / 状态刚切到 reward
  时才调用它一次（`region_provider` 惰性求值），避免它的 80/20 随机分支被每帧重新掷骰子、把
  anchor 一致性打散。
- **新增结算 burst 专属间隔常量，不复用/不污染既有 timing owner**：`SETTLEMENT_BURST_CLICK_INTERVAL_RANGE
  = (0.30, 0.60)`（2026-09-23 由 `(0.10, 0.30)` 放宽，见文末补记）是同一 burst 内两次盲点之间的间隔（同点快速连点的真实语义），与跨 burst 节流
  的 `SETTLEMENT_CLICK_INTERVAL_RANGE = (0.7, 1.0)` 是不同的 timing owner，也不接
  `module/reaction_profile.py` 的 reaction timing 或 FatigueManager。两个常量都是 class-level
  PROVISIONAL，Level C 待标定。
- **旧 `_advance_generic_result`（首帧强制两次、各自独立采样）整体移除，不保留成第二个 owner**：
  `_handle_result` 的通用结果分支现在唯一调用 `_settlement_burst_step`；不存在「旧固定两次 +
  新 session 随机 2~4」同时执行的可能。
- **Settlement 点击永远不能穿透到 Challenge / FIRE 页面——离开结算立即销毁 session，不等到
  下一轮战斗才清理**：`run_general_battle()` 主循环每帧 fresh classify 之后、分发给具体
  handler 之前新增一次判定——`page is not None and page not in (page_battle_result,
  page_reward)`（即确认当前页是 `page_battle_prepare`/`page_battle`，或曾经短暂经过
  `_handle_missing_battle_page` 之后又重新识别出的其它已知页）就立即调用
  `_teardown_settlement_session()`，把 `settlement_session_active`/`settlement_click_budget`/
  `settlement_clicks_used`/`settlement_anchor`/`settlement_region_name`/
  `settlement_stage_name`/`settlement_anchor_switches` 全部清零。`page is None`（本帧暂时没
  识别到任何战斗页，可能是结算页内部一次过渡性丢帧）不触发销毁，避免误杀仍在进行中的 session。
  这样即使同一次 `run_general_battle()` 调用内（连战场景）后续又回到 Challenge/FIRE 相关页面
  （`page_battle_prepare`/`page_battle`，或该任务自己在 `run_general_battle()` 之外的目标选择 /
  「再次挑战」页），也**不可能**复用上一次结算 session 的残留 anchor/budget 继续点击——任何
  新出现的 Challenge/FIRE 必须重新走它自己完整的 FIRE contract（窄 detector + reaction +
  fresh 二次确认），不会被本 session 绕过。`_reset_round_context`（连战开新一轮）里原有的
  同一组字段重置继续保留，与这次的即时销毁是两层防御，不冲突。
  **★ v1.1 新增第二个入口，复用同一个 helper**：仅有「主循环每帧」这一个入口还不够
  ——第一下点击导致页面推进到 Challenge/FIRE 的那一帧里，主循环自己的下一次 fresh classify
  要等到*下一次*循环迭代才会跑到。v1.1 在 `_fire_settlement_burst` 的 mid-burst 观察分支里
  新增第二个入口：一旦观察到已知的非结算页就立即调用 `_teardown_settlement_session()`，
  在**同一次**函数调用内完成销毁，不等下一次主循环迭代。两个入口调用的是同一个方法，没有
  复制 7 个字段的重置代码。

不改（v1 与 v1.1 均适用）：`GeneralBattle.is_in_battle()` / `is_in_prepare()` /
`is_in_real_battle()`；`gb_page_handle_dict` 页面分发（主循环本身只新增一次判定+一次销毁调用，
未重排既有步骤顺序）；`_handle_missing_battle_page` 2.5s 兜底；`_select_reward_region()` 本体；
`_sample_settlement_budget`/`_start_settlement_session`/`_advance_settlement_anchor`/
`_point_in_roi`/`_is_generic_result_context`/`_sample_settlement_point`/
`_click_settlement_point`/`_sample_settlement_click`（v1.1 只改了 `_fire_settlement_burst`
内部逻辑与签名，新增 `_classify_general_battle_page`，其余原语逐字未动）；
`ActivityShikigami._drain_activity_settlement()`（task-local，只调 `_sample_settlement_click`，
不经过 `_handle_result`/`_handle_reward`/本 session，结构上完全独立，参见 D001「§4.62」补记）；
RealmRaid `fire()`/`_fire_again()` FIRE 契约（D001/D023 之外的另一套 owner，本 ADR只影响
RealmRaid 通过 `super()._handle_result()`
继承的通用结算，不影响 FIRE 契约本身）；GeneralInvite FIRE；RyouToppa FIRE；Activity FIRE；
KekkaiUtilize；导航；FrameWait；TouchSwipeModel；HABIT
全局模型；BehaviorTrace 架构；OASX。

Level C 待验（v1.1 重新定义，取代 v1 版本的列表）：①Result 第一次点击未切页时能否观察到自然的
同点补点；②Result 第一次点击已经切到 Reward 时是否确实不出现旧 state 的第二个盲点；③Reward
第一次点击直接切到下一场 terminal 时是否不残留任何 settlement 点击；④进入 Challenge/FIRE 前
是否总是先经过 Settlement teardown、再由 FIRE 契约独立接管；⑤连续点击视觉观感是否仍然自然，
不因多了一次 mid-burst 截图/识别出现明显停顿；⑥`SETTLEMENT_BURST_CLICK_INTERVAL_RANGE =
(0.30, 0.60)` 的观察间隔是否足够看到真实页面更新；⑦若真机页面响应慢于 600ms，是否会出现
「仍识别到旧 state → 补第二下」但仍落在安全的结算区域内（不应该出现的坏情况：识别慢导致误点
到已经切换的新页面）；⑧anchor keep/resample 的真机观感是否自然。
`SETTLEMENT_BURST_CLICK_INTERVAL_RANGE` /
`SETTLEMENT_ANCHOR_KEEP_PROBABILITY` / budget 权重分布均 PROVISIONAL，据真机数据调整时连带
更新本条 ADR 与 `docs/AI_CONTEXT.md` §4.67。

### v1.2 Level C 修订：2~4 是 Click Segment 节奏预算，不是 Settlement Lifecycle 终止条件

2026-09-14，master 真机普通副本第三场明确复现 v1.1 失败：session 抽到 `budget=2`，Generic
Result 点击 1 次推进到 Reward，Reward 再点击 1 次后日志输出 `Settlement terminal budget
exhausted: used=2/2, stop early`；下一帧 fresh classify 仍明确是 `page_reward`，真实画面停留在
“点击屏幕继续”。因此识别、Reward asset、anchor、FIRE 与账号轮换均不是根因；根因是把随机
2~4 错当成整个 lifecycle 的点击硬上限，导致合法结算尚未完成时永久失去 click owner。

v1.2 修订决定（取代上方 v1/v1.1 的 lifecycle budget 语义，但保留其余能力）：

- **两层模型**：Settlement Lifecycle 持有 semantic state、anchor、状态迁移、总安全帽与当前
  Click Segment；`settlement_click_budget` / `settlement_clicks_used` 为兼容现有字段名而保留，
  但正式语义改为**当前 segment**的 budget/used。新增 `settlement_total_clicks` 只用于日志与固定
  safety cap，不重新承担随机 2~4 hard cap。
- **segment budget**：`_sample_settlement_segment_budget()` 继续用单次 `random_int(1,10)` 分桶
  2/3/4，权重仍为 50%/30%/20%。只在 session 首个已知 settlement state、semantic state
  advance，或 fresh outer classify 确认同一 state 且当前 segment 已耗尽时生成；不按帧、不按
  点击重抽，Unknown / terminal 不续段。
- **选择方案 B**：Generic Result → Reward 属 semantic state advance，旧 Result segment 立即结束，
  Reward 获得独立 2~4 segment；这样 Result 已用点击不会侵占 Reward 的节奏预算。segment 生命周期
  与 anchor 生命周期解耦：状态变化仍先走既有安全区域交集与 keep/resample 策略，安全时可继续
  使用同一 anchor；同 state 的 segment renewal 从不强制换点。
- **semantic state 优先于 segment budget**：同 state segment 耗尽只记录
  `Settlement segment exhausted ... renew=true` 并在 fresh known settlement state 上续段；它
  不是 terminal。只有 fresh classify 明确离开 `page_battle_result/page_reward` 才记录
  `Settlement terminal reached` 并 `_teardown_settlement_session()`。Unknown 不补第二下、不续段、
  不擅自 teardown，继续交给既有 missing-page recovery。
- **Click → Observe → Decide 不变**：first click 后只有 desired burst 仍允许第二下时，才等待
  `0.30~0.60s`、fresh screenshot、复用同一个 classifier；same state 才用同一 anchor 补第二下，
  state advance 取消第二下，known non-settlement 立即 teardown。第二下之后仍交回主循环，不产生
  第三下。
- **固定 safety cap**：现有 `battle_timer` 只在 prepare/battle 阶段判定，点击又会重置底层 stuck
  timer，不能单独证明 Reward 续段有界；通用 `Device.click_record` 会在同 target 第 10 次调用前
  抛错，但它是异常兜底。因此 v1.2 新增 `SETTLEMENT_MAX_TOTAL_CLICKS=9`，与该现有有效上限对齐，
  在 Settlement 层先停止生成 segment/点击；它是 PROVISIONAL 故障安全帽，不是正常节奏目标，也
  不把 safety exhaustion 称作 terminal。Device click/stuck guard 继续作为第二层保护。

保留不变：Reward layout-aware region policy；anchor 安全交集与全 session 最多 1 次主动换点；
`SETTLEMENT_CLICK_INTERVAL_RANGE` / `SETTLEMENT_BURST_CLICK_INTERVAL_RANGE` 数值与 owner；特殊 Reward
overlay 的 fresh-state 边界；非通用 result 的单次节流路径；FIRE 独立 owner；ActivityShikigami
task-local drain；RealmRaid / RyouToppa / GeneralInvite / Exploration / KekkaiUtilize / Navigator /
FrameWait / TouchSwipeModel / HABIT / BehaviorTrace / OASX。

Level C 状态：v1.1 = **FAIL**；v1.2 = **Level A/B PASS，Level C RE-TEST PENDING**。下一轮真机须
验证：`budget=2` 不再卡 Reward；Reward 能跨 segment 继续；semantic terminal 后无残留点击；永久
Reward 不会无限 renew；FIRE 完全不受影响；并观察总安全帽 9 是否过紧或过松。未有新证据前不改
2/3/4 权重或 anchor keep 概率（observe 间隔已于 2026-09-23 单独调整为 `0.30~0.60s`，见文末补记）。

**补记（2026-09-23）—— ActivityShikigami 普通爬塔线退出本 Micro-Burst，改用task-local 专属单击结算**：
用户明确要求本线（仅 `NormalClimbAct`，不含大富翁 / 伪神降临）不再参与 Settlement V3 的
segment 预算 / burst 连击 / anchor 跨调用复用机制，理由是本线两处真机事故（2026-09-22，见
`docs/AI_CONTEXT.md` §4.89 / §4.90）已经证明：这套「同一 anchor 连续打两下」的模型在本线的
结算 → 挑战页转场场景下，容易在弹窗已经消失、真实挑战页刚出现时仍打出第二击，穿透到底层
业务页面。

- **机制**：`NormalClimbAct._handle_result` / `_handle_reward`（`normal.py`）在
  `_climb_owns_settlement_single_click` 为真（`run_climb()` 期间显式声明，ownership 契约与
  `_fatigue_owns_macro_idle` 同款，避免跨玩法线残留）时完全接管，不调用
  `_settlement_burst_step`；每次只执行 **1 次** `execute_single_click`，且每次都是独立完整的
  一轮事务（reaction → fresh screenshot → 再确认结算状态仍存在 → 70/30 选活动专属区域
  `C_RANDOM_ACTIVITY_1` / `C_RANDOM_ACTIVITY_2` → 现采坐标 → 单击），不预授权第二击、不跨调用
  复用 anchor。
- **reaction owner 归本线自己持有（同日收口）**：首版曾借用
  `GeneralBattle.SETTLEMENT_BURST_CLICK_INTERVAL_RANGE`（0.10~0.30s），随即纠正——**那个常量的
  语义是「Micro-Burst 同一 burst 内两击之间的观察间隔」，不是「点击前反应」，而且它属于通用
  Settlement V3 的 timing**；本线既然已经退出 Micro-Burst，就不能再借它的常量，否则两种语义
  混在一起、任何一方调参都会误伤另一方。现由本线自己的
  `ACTIVITY_SETTLEMENT_REACTION = (0.45, 0.85)`（`normal.py` 常量区，PROVISIONAL）持有，量级对齐
  `REACTION_NORMAL` 但**不走** `InteractionPolicy` / `appear_then_click(policy=)` / `confirm_delay`
  ——本事务的 timing 由本状态机自己拥有（`InteractionPolicy.SPECIAL` 语义），整条链路只有这一层
  reaction。**一般规则**：一个已经从公共机制里独立出来的 task-local 事务，必须同时独立出它自己的
  timing 常量；继续引用原机制的常量是「看起来没新增常量」的假节省，实际制造了跨机制耦合。
- **状态门控**：每次事务的 fresh confirm 阶段除了「结算状态是否还是原来那个 result/reward 页」，
  还显式检查真实挑战页 `page_climb_<type>` 与挑战键（`_climb_fire_rule`）是否已经出现——任一出现
  立即放弃、不点，直接吸收 §4.90 的事故教训，不留同类缺口。
- **不变**：GeneralBattle 本体（`general_battle.py`）、`_settlement_burst_step` / `_fire_settlement_burst` /
  `_select_reward_region` / `SETTLEMENT_MAX_TOTAL_CLICKS` / `SETTLEMENT_BURST_CLICK_INTERVAL_RANGE`
  （当时仍是 `(0.10, 0.30)`；该数值已于同日后续一轮单独调整为 `(0.30, 0.60)`，见文末补记，仍只被 `_fire_settlement_burst` 用作 burst 内观察间隔）等公共 Settlement V3 机制一字未改；
  大富翁 / 伪神降临、其它所有使用 GeneralBattle 的任务继续走原有 Micro-Burst；`_drain_activity_settlement`
  （战后回挑战页的有界兜底）与 FIRE 契约不受影响。
- **新增资产**：`C_RANDOM_ACTIVITY_1` (937,431,296,248) / `C_RANDOM_ACTIVITY_2` (659,522,406,171)，
  定义在 `GeneralBattleAssets`（用户提供，非本次改动生成），70/30 由
  `module.base.utils.random.random_int`（模块级 `SystemRandom`）选择。
- **Level C 待验**：70/30 权重、本线 reaction 区间 `ACTIVITY_SETTLEMENT_REACTION = (0.45, 0.85)`
  均未经真机标定；两处新区域的真机安全性由用户自行确认。

**补记（2026-09-23）—— Micro-Burst observe 间隔 `(0.10, 0.30)` → `(0.30, 0.60)`**：用户按真机体感
要求放宽「第一下点击之后等多久再看」，让 fresh 观察更容易落在页面真正更新之后（原 0.10~0.30s
在页面响应稍慢时容易在旧帧上判定「还是同一 state」）。

- **只改一个数值，状态机一个字未动**：`SETTLEMENT_BURST_CLICK_INTERVAL_RANGE` 的定义值改为
  `(0.30, 0.60)`，`_fire_settlement_burst` 仍是 `time.sleep(self._sample_interval(...))` 同一行、
  仍由 `random_delay` 每次独立采样。**第二下依旧必须由观察结果重新授权**：same state 才允许同
  anchor 补第二下，state advance / Unknown / known non-settlement 分别取消第二下、交回 recovery、
  立即 teardown——绝不因为等得更久就退化成「固定 sleep 后无条件第二击」。segment 预算、
  `SETTLEMENT_MAX_TOTAL_CLICKS=9`、anchor 复用与安全区域交集、Result / Reward region 策略、
  L1 `execute_single_click` 链路全部原样。
- **两套 timing 完全独立**：ActivityShikigami 普通爬塔线的专用单击结算 reaction
  `ACTIVITY_SETTLEMENT_REACTION = (0.45, 0.85)` **不受本次调整影响**（上一条补记把它独立出来的
  价值正体现在这里——通用层调参不再牵连 task-local 事务）。FIRE、L2 policy、Minitouch dwell、
  ClickSampler、Swipe / Drag 同样未动。
- **文档内联数值已同步**：本 ADR 正文里描述该常量的几处数值（含 Level C 清单第 ⑥ 项、
  「未有新证据前不改」那句）都已改成新值，机制描述文字未改；`docs/DEVELOP_LOG.md` 属只追加的
  历史流水，旧条目保持原样不回改。
- **Level C 待验**：`0.30~0.60s` 是否足够覆盖真机页面更新（是否还会出现「在旧帧上判定 same
  state 而补了第二下」），以及放慢之后连点观感是否仍然自然、整体结算耗时是否可接受。

## D026 L1 全局单击管线：坐标语义显式化（Target / Bounds / Region / FinalPoint）+ 单一单击执行器，只管「点在哪、怎么落下」

> **master 基线移植说明（2026-09-15，L2-1 前置）**：本 ADR 原在 synevo 分支 L1 worktree 形成，未提交。L2-1 以 master `a5e2d7e6`（+ 工作区 Settlement v1.2）为基线，把 L1 / L1.2 **公共层**原样移植进来：`module/click_pipeline.py`、`RuleList.last_ocr_hit`、`Control.click_with_backend` / `_dispatch_click` 与全部公共 task 点位；synevo 专属点位（网易原生控件 `netease_account_ui`、MultiAccountEvo）在 master 不存在，小号轮换业务（Login `_app_handle_login` 固定退出点、DailyTrifles `summon_recall`）**刻意不迁**，作为 master 静态白名单里的显式排除项保留直接 `device.click`。下文提到这些点位的地方以此说明为准。

状态：Accepted（Level A/B PASS，Level C PENDING）
日期：2026-09-15

背景：点击空间模型（D014 / D019）已经把 `Rule*.coord()` 收到 `ClickSampler`，`Control.click`
也早就是「只执行最终坐标、不做空间抖动」的执行器。但大量业务点位仍直接调用
`device.click(x, y)`：裸坐标看不出它是「目标中心」还是「已经采样过的最终落点」，于是既可能
**漏掉**点击模型（手算中心 / 固定坐标 / 原生控件中心），也可能被人「顺手」再采样一次造成
**double randomization**（例如 `list_find` 的图片列表结果已经是 `coord()` 采样过的点）。

决定：

- **新增 `module/click_pipeline.py` 作为 L1 公共入口**：`resolve_click_point(target) → (x, y)`
  + `execute_single_click(device, target, control_name) → (x, y)`。执行仍然落到既有
  `Control.click`（不改 `Control` / 后端 / BehaviorTrace），不往 `BaseTask` 加方法。
- **坐标语义必须显式，裸 `(x, y)` / list / `None` / `RuleSwipe` 一律 `TypeError`**：
  - `Rule*`（`RuleImage` / `RuleClick` / `RuleOcr` / `RuleGif`）→ `rule.coord()`。
  - `ClickBounds(roi, name)` 游戏内运行时矩形 → `sample_target(roi, name)`。
  - `ClickBounds(roi, name, native=True)` 原生 Android 控件 → `sample_region(roi, None)`：只用
    RULE_FALLBACK 区域模型，**绝不按名字查游戏图片的 empirical 热点**；宽或高为 0 → 中心点。
  - `ClickRegion(roi, name)` 业务已选安全区 → `sample_region(roi, name)`，不改业务的区域选择。
  - `FinalPoint(x, y)` 业务已算好的最终落点 → **原样执行，零采样**；取整口径与 `ensure_int`
    （`int()` 截断）一致，拒绝 `bool`。
- **EMPIRICAL > RULE_FALLBACK 不变**（D019），本轮不调任何 Gaussian / tail / habit / hotspot 参数。
- **一次调用 = 一次物理点击**：L1 不做 reaction delay / `confirm_delay` / fresh screenshot /
  二次确认 / 业务重试 / 连点 / Fatigue / FrameWait；这些属于 L2（Reaction）/ L3（业务状态机）。
  `execute_single_click` 拒绝 `RuleLongClick`，长按不能降级为轻点。
- **`Control.multi_click` 不成为公共入口**：保留不删、不启用（其实现把 `button` 当 `x` 传、缺
  `y`，本身不可用），无生产消费者；GeneralBattle Settlement 的多次点击继续由自己的状态机多次调用单击。
- **Settlement / FIRE 的 timing ownership 不下沉**：Settlement 的 segment / burst / observe
  间隔 / anchor 生命周期、FIRE 的 `REACTION_FIRE` / fresh confirm / bounded retry 都留在业务里；
  L1 只接它们决定好的那一击。
- **固定坐标先审语义，不一律随机**：只有「目标中心」语义才换成采样；以下三类刻意保持精确中心 /
  偏移并显式标为 `FinalPoint`——① 作者注明的安全控件中心（MultiAccountEvo 接受邀请按钮）；
  ② 模板未识别时的保底点（Navigator town fallback：`roi_front` 是旧资源框、不是当前帧真实边界，
  往框边采样可能点空）；③ 业务偏移点（锚点上方 70px、名字框下方 +30px、无控件范围的固定退出点）。
- **已经直接调用规范采样器且带目标名的点位保持不动**（`BaseTask` 内部 `coord()` 路径、Settlement
  两个原语、GeneralInvite 好友名框 `sample_target`、RyouToppa `C_AREA_1` 的 `sample_point`、
  Navigator / KekkaiUtilize 的 `coord()` 点击）：语义已等价于上面的分支，改写只是换壳且会打破既有
  源码契约测试；它们的「不重采样」契约用行为测试锁定。

不改：`Control` / `multi_click` / minitouch dwell `triangular(45, 130, 65)` 与 pressure 归一化 /
`@retry` 传输层重连 / BehaviorTrace / `click_preference` / `click_profile` / swipe（`TouchSwipeModel` /
`SwipeEndpointSampler`）/ Fatigue / FrameWait / Settlement FSM / FIRE FSM / MultiAccountEvo 结算覆写 /
`behavior_trace_enable` 默认值与 oas3~oas5 配置。

已知未覆盖（不能宣称 100% global）：Hyakkiyakou 直接调 `click_minitouch` / `click_window_message`
（绕过 `Control` 与 BehaviorTrace）；GeneralRoom `check_zones` 在 OCR 列表中心上自加 `randint(±5)`
（当前是单次随机，若列表改成图片模式会变成 double randomization）；Chess / QuickLoadout /
WeeklyTrifles / WantedQuests / SixRealms / Secret / Dokan / EternitySea / FallenSun / Orochi /
WeeklyPurchase / SwitchSoul 的直接 `device.click`；`RuleList.ocr_appear` 只返回 OCR 框中心（文字列表项
暂不能在框内采样）。另：`random_click()` 用 Point 模型采样大安全区（应属 Region 模型），并会永久把
共享资源改名为 `SAFE_RANDOM_CLICK`；`RuleList.ocr_appear` 在 OCR 无结果时返回真值 `(0, 0)`，
`list_find` 会把它当命中——均为既有问题，本轮只记录。

Level C 待验：图片按钮真实落点与小 ROI 安全性；NetEase 原生控件（账号列表 / 选择 / 登录按钮）
在 bounds 内采样后仍能正确命中；AccountRotation 登录与切号；DailyTrifles 召唤；MultiAccountEvo
接受邀请（精确中心）；FIRE 与 Settlement 行为不变；有无随机漂移过大 / double randomization；
BehaviorTrace 记录坐标与真机点击位置一致。

### D026 补记（2026-09-15，L1.2 Global Click Migration）

上面「已知未覆盖」的业务点位已全部收口（清单 `docs/T7_TARGET_PREFERENCE_MAP.md` §10）。补充三条长期规则：

- **后端直调政策**：业务模块不得直接调用 `click_minitouch` / `click_window_message` 等后端方法
  （只允许在 `module/device/` 内）。确有「必须指定后端」的高频场景（百鬼夜行撒豆：配置选
  minitouch 或 window_message 且要 10~40ms 快按），走 `execute_single_click(..., backend=...)` →
  `Control.click_with_backend`：只换后端、不读 `control_method`、不做 `control_check`（原高速路径就不进
  click_record），坐标取整 / 日志 / BehaviorTrace 与 `Control.click` 共用 `_dispatch_click`。**不把
  window_message 强行统一成 minitouch**。
- **本地随机迁移规则**：业务在点击坐标上自加的 `randint` / `uniform` 先判语义——只是模拟点击分布的
  （GeneralRoom OCR 中心 ±5、SixRealms 技能左侧 35~60px）删掉本地随机，改为 `ClickBounds` /
  `ClickRegion` 交统一模型，Region 取旧随机的支撑集，保证不漂出原范围；有业务含义的偏移保留为
  `FinalPoint` 计算。同一函数里「点击 + 本地坐标随机」由静态守卫禁止。
- **列表命中**：`RuleList.ocr_appear` 命中时额外记录 `last_ocr_hit`（中心 + 屏幕整数 OCR 框，返回值
  契约不变），`list_click_target` 据此给文字列表 `ClickBounds`；图片列表 `pos` 已由 `coord()` 采样，
  一律 `FinalPoint`，拿不到匹配框（含旧 `(0, 0)` 行为）也 `FinalPoint`。上一轮 `list_appear_click` /
  `EvoZone.check_layer` 的「OCR 中心 FinalPoint」同步改走这条。
- **显式白名单**：仍直接调 `device.click` 的函数只能是「紧邻 canonical 采样器 / 已选 Region / anchor 点
  + 具名 control_name」的已合规路径，以「文件 + 函数 → 次数」白名单锁在测试里；新增条目必须先说明
  坐标语义。只有业务绕过为 0 才能称全局收口；长按与拖拽不是单击，不计入。

推断几何保持精确：WeeklyTrifles 复选框（由文字左边界减勾选框宽度推算）、QuickLoadout 面板布局常量
交点、WantedQuests 按钮上方 40px、Dokan 地图文字上方 20px 均为 `FinalPoint`，不在推算框内随机。
坐标分布有变化、需 Level C 的点位：Chess 发现卡、GeneralRoom 副本名、Dokan 赏金图标（原点匹配框
左上角）、EternitySea / FallenSun / Orochi / EvoZone 层数与 `list_appear_click` 的文字列表、SixRealms
购买区（均匀 → Region 模型，范围不变）；百鬼夜行后端行为不变，新增 trace 与 Control 日志。

**补记（2026-09-21，L1 + L2 集成进 master 的边界）**：

- **一个动作一个最终坐标、一个 reaction owner**：L1 决定落点（`FinalPoint` 不再采样），`Control` 只执行已定坐标，BehaviorTrace 记录实际坐标；L2 只决定 reaction 时机与二次确认（新截图 → 同目标再识别 → 新帧
  `coord()` → 一次点击，失败零点击不重试）。FIRE 事件的 reaction 只归任务 `fire_reaction`，Settlement / KekkaiUtilize 不带任何普通 policy / confirm_delay。
- **全仓审计 ≠ 全仓加延迟**：`docs/L2_CALLSITE_REGISTER.md` 登记 `tasks/` + `module/` 全部 1092 个点击调用点，分类沿用 L2 术语；basis=human（L2-2 逐点审计 179）与 basis=rule（保守规则 913）**不混为一谈**，
  规则分类默认保持立即点击。没有真机证据的候选一律 NEEDS_C（24），不因迁移率强行迁移。`policy=` / `confirm_delay=` 只允许出现在人工审计过的文件，由 `tests/test_l1_l2_integration.py` 钉住。
- **项目排除**：WeeklyPurchase（不做 Reaction Policy / FIRE / L1 迁移）、synevo 小号轮换业务（AccountRotation / SwitchAccount / Login / DailyTrifles / MultiAccountEvo）、Orochi 野队 `run_wild`（不启用、不扩展）。
- **集成方式**：选择性移植、不整分支合并、不整目录覆盖；与 master 已有改动冲突的文件用 3-way 合并并逐行核对被取代的旧写法；Settlement / Kekkai / GlobalGame / FIRE 配置 / 疲劳翻译等 master 近期修复零回退（变异验证）。

**补记（2026-09-21，L1 Stage 1：BaseTask primitive 的执行入口统一，只换入口不改采样）**：

- **决定**：BaseTask 公共单击 primitive（`appear_then_click` / `wait_until_appear_then_click` / `click` / `ocr_appear_click`）的 8 个原 `device.click` 执行点统一为
  `execute_single_click(self.device, FinalPoint(x, y), control_name=…)`：坐标仍由目标 `coord()` 在**原时机**采样恰一次，再以 `FinalPoint` 传递。**不把 Rule 直接交给执行器**——那会在提前
  `coord()` 之后再采一次（double sampling），也会让 `SimpleNamespace(coord=…)` 之类测试替身撞上执行器的严格类型判断；`FinalPoint` 既零采样又保持 primitive 的公共契约不变。
- **等价性要求**：`control_name` 逐点保持（`appear_then_click` 传 action 时仍是 `target.name`）、返回值 / 点击次数 / 截图次数 / 识别顺序 / L2 reaction 顺序 / 异常传播 / 后端分派不变；不新增等待。
  执行器改用关键字实参调用 `device.click(x=, y=, control_name=)`，仅影响 Mock 断言形式。
- **「25 处」的正确读法**：显式调用执行器的调用点数（为非 Rule 坐标声明语义），**不是**享受 ROI 采样的点击数——`Rule*.coord()` 早就统一走 `ClickSampler.sample_target`。Stage 1 的意义是统一执行入口
  （守卫 / 观测 / 后续元数据都挂在同一个入口），不是给约 887 个调用点首次引入随机落点。
- **修复**：`ocr_appear_click` action 分支的无效重复采样（采样后丢弃 + `self.click` 再采）已移除。
- **范围**：长按、9 个生产直接点击、全局静态守卫、BehaviorTrace 元数据、ROI 质量审计留给后续阶段；WeeklyPurchase / synevo 仍是项目排除项。

**补记（2026-09-21，L1 Stage 2：剩余 9 个生产直接单击迁入执行器，采样原位保留）**：

- **决定**：9 个原直接 `device.click` 的生产点位统一走 `execute_single_click`，且**采样表达式、函数与参数逐点保持原样**：已确定的坐标以 `FinalPoint` 交给执行器；唯一例外 `_sample_settlement_click` 用 `ClickRegion`
  ——其解析就是同一个 `ClickSampler.sample_region(roi, name)`（同 ROI、同身份、一次采样）。**不为「统一类型」改采样算法**：GeneralInvite 保留 `sample_target(select_area, …)`（不换 `ClickBounds`：对退化 / 浮点框处理不同），
  RyouToppa 保留 `sample_point(roi, wide_card)`（不换 `sample_target`），Chess / Secret 的两次点击各自独立采样（不复用），Settlement burst 只采样一次锚点、点击时 `FinalPoint` 复用。
- **不变量**：一个点击动作只采样一次最终坐标；采样次数、点击次数、`control_name`、等待 / 截图 / 识别次数、后端参数与 BehaviorTrace 坐标与迁移前一致；不新增 reaction / 等待；FIRE / L2 / Settlement /
  Kekkai 调度与收敛逻辑不受影响。
- **验收口径**：以「当前项目范围内没有未经解释的生产单击执行旁路」为准，不以固定文件修改数量为准；裸点只剩执行器自身、底层 / 非点击 4 处与项目排除项 3 处。
- **登记册规则**：受保护模块里已走执行器的点击仍归 KEEP_SPECIAL（R3）——执行器只是执行入口，不改变「由状态机拥有 timing」。
- **范围外**：长按独立执行入口、正式的「执行器之外零直接点击」守卫、BehaviorTrace 元数据、ROI 质量审计。

**补记（2026-09-21，L1 Stage 3A：长按走独立的 `execute_long_click`，与单击执行器互不替代）**：

- **决定**：长按是另一种物理动作（DOWN → 持续 `duration` → UP，由各后端自己实现），**不并入 `execute_single_click`**，也不用「重复单击 / 滑动」模拟。`module/click_pipeline.py` 提供独立的
  `execute_long_click(device, target, duration, control_name=<缺省哨兵>)`：落点解析复用 `resolve_click_point`（`FinalPoint` 零采样），随后恰一次 `device.long_click(...)`。BaseTask 的 6 个长按点位保持
  `coord()` 原位采样一次，再以 `FinalPoint` + `<ms> / 1000` 秒交给它。单击执行器继续拒绝 `RuleLongClick`（不降级为轻点）；长按执行器不接管单击。
- **职责边界**：执行器只回答「最终点在哪 + 这一按怎么交给 Control」。`duration` 原样透传（不换算、不随机、不叠加单击 dwell）；`control_name` 显式传入一律原样（含 `None` / 空串），只在完全不传时回退；
  不 sleep / 不截图 / 不重试 / 不吞异常；后端选择、`handle_control_check`、BehaviorTrace（`action=long_click`，`extra={x, y}`）仍全在 `Control.long_click`。
- **不变量**：一次长按 = 采样至多一次 = 执行器一次 = `Control.long_click` 一次 = 后端一次；业务不得先 `coord()` 再把 Rule 交给执行器（双采样）；不新增 reaction / 等待；`wait_until_appear_then_click`
  的长按点位取 `target.coord()`（非 action ROI）是既有行为，迁移不「顺手修正」。
- **验收口径**：生产范围内没有绕过 `execute_long_click` 的长按——BaseTask 直调 `device.long_click` 为 0，业务消费点直调为 0；执行器自身与 `module/device/` 后端内部不计入旁路。拖拽 / 滑动（Chess `press_and_drag`、
  `swipe*`）不是长按，不进长按执行器。
- **范围外（Stage 3B，待确认）**：「执行器之外零直接点击 / 长按」的正式全局静态守卫、BehaviorTrace 元数据、ROI 质量审计、`nemu_ipc` 长按未注册的既有行为。

**补记（2026-09-21，L1 Stage 3B：项目排除不再豁免点击执行入口；全局静态守卫落地）**：

- **决定**：**项目业务排除 ≠ 点击架构豁免。** WeeklyPurchase（不做 L2 Reaction Policy / FIRE 改造）与 synevo 小号轮换业务（Login / DailyTrifles 等）的排除只针对 L2 / 业务迁移；只要代码真实存在于当前 master、
  属于生产点击，执行入口就必须是 `execute_single_click` / `execute_long_click`。据此把最后 3 处直接单击（WeeklyPurchase navbar 的 `list_find` 已采样点、DailyTrifles 的 `RuleOcr.coord()`、Login 的固定坐标 (106, 535)）
  以 `FinalPoint` 迁入执行器：**只统一入口，不改落点**——不随机化固定坐标、不猜 ROI、不新增等待 / 截图 / 重试。改善 Login 固定坐标必须先有可靠 ROI 证据，另行实施。不把 synevo 独有业务带入 master。
- **守卫规则（`dev_tools/click_entry_guard.py`）**：默认禁止生产直接点击 / 长按；只允许 `ALLOWED_EXITS` 里明确登记的内部出口——精确到（文件, 函数, 调用形式, 次数）并写明层（executor / control / backend / demo / dead）与原因，
  **不允许按文件名 / 目录整体豁免，也不永久豁免 Login / DailyTrifles / WeeklyPurchase**。白名单条目找不到或次数不符、必需出口缺失同样失败。守卫扫描生产目录的**实际文件**（rglob），不是登记册；含 Python 的顶层目录必须显式归类。
  违规时报「文件:行号 函数 违规形式 → 建议的 L1 入口」，**修复方式是迁到执行器，不是加白名单**（新增白名单条目属于架构决定，需要在本 ADR 补记理由）。
- **职责边界**：静态守卫回答「有没有绕过执行器的直接调用」；运行期等价测试回答「坐标 / 采样 / 时序 / 后端 / 返回值 / 异常是否不变」。两者互不替代。滑动 / 拖动 / 连续触摸手势不属于单击或长按，不在守卫范围；`Control` 内部向已注册后端分派与设备后端自身实现属合法内部出口。
- **验收口径**：生产单击对所有模块（含原项目排除模块）通过 `execute_single_click`，生产长按通过 `execute_long_click`；未解释的生产旁路 = 0。`Control.multi_click` 是无生产消费者且实现有误的死代码，只登记不顺手修改。
- **范围外**：ROI 质量审计（Level C）、BehaviorTrace 元数据、`nemu_ipc` 长按注册、L2 对 WeeklyPurchase 的 Reaction Policy（仍不做）。
