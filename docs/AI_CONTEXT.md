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

**归档**：`docs/archive/AI_CONTEXT_history.md` 存放已提交、已推送、不再影响当前开发的历史内容（§4.1 ~ §4.109 各章节、提交历史、历史测试基线与各模块测试覆盖面、已完成的待办），原样搬运、小节编号不变。其他文档和代码注释里写的 `AI_CONTEXT §4.N`（N ≤ 109）都指归档里的同编号小节。只在需要某次改动的细节或历史原因时查阅，不必通读；还没在真机上核对完的项目由 `docs/ROADMAP.md` 跟踪。

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

以下状态核对时间为 2026-10-29（发布前审查）。2026-10-20 ~ 10-25 的逐日工作区清单已归档，见 `docs/archive/AI_CONTEXT_history.md` §2.2；更早的提交历史见同文件 §2。

- 当前分支：`master`，跟踪 `origin/master`（`https://github.com/Hualaijushi/OnmyojiAutoScript.git`，用户自己的仓库）；`upstream`（xylolit-mu）只作参考，不推送。
- 2026-10-29 发布前审查：此前未推送的 6 个百鬼棋局提交（§4.134，`b9c7c181` ~ `cf1c8a48`，上游 cherry-pick 的来源行齐全）与工作区累积的 §4.110 ~ §4.158 改动一起以普通快进推送到 `origin/master`（推送前 `origin/master` 仍是 `8a82cb8f`）。累积改动作为一个提交入库（`script.py` / `base_task.py` / 配置模型 / 模板 / 翻译 / L2 登记册和六份文档被各主题交叉修改，拆开会产生没测过的中间状态）；本节随该提交一起提交，不写自身 hash，以 `git log` 为准。审查发现、纳入 / 排除清单与验证见 `DEVELOP_LOG` 2026-10-29「发布前审查」条目，原始材料在 `D:\Codex\workspace\oas-release-review-20261029`。
- `config/oas*.json`、`log/` 等本地文件由 `.gitignore` 排除，不纳入版本控制。
- **有意留在工作区、没有提交的文件**（去留由用户决定）：
  - GlobalGame 好友邀请弹窗资源：`tasks/GlobalGame/gg/` 下 `gg_g_accept` / `gg_g_reject` / `gg_g_jade` / `gg_g_ignore` 四张图、`gg/image.json` 与 `tasks/GlobalGame/assets.py`（用户 10-28 用 annotator 重标，没有对应的开发记录）。猫粮 / 狗粮两条的识别框被改成与勾玉相同的 (675,516,43,46)，模板图却仍是旧的 59×65 / 60×63，模板比搜索区大，永远认不出（见 §8）。
  - 没有任何规则引用的图：`tasks/ActivityShikigami/as/climb/climb_item_13.png`（与 `climb_boss_lock.png` 逐字节相同）、`tasks/GlobalGame/ui/ui_ui_reward_1.png`（与 `ui_ui_reward.png` 逐字节相同）、`tasks/Dokan/res/res_dokan_enter_again.png`（福利道馆旧废稿，§4.140）、`tasks/GameUi/page/page_num_tongxin.png`（§4.114 的孤儿小图）。
  - 用户 10-20 用 annotator 重截的 ActivityShikigami 模板（原先列为「去留由用户决定」）已随 §4.110 提交：重新生成的 `as/climb/image.json`、`as/page/image.json` 与 `assets.py` 里的识别框是按新图标的，不能和它们分开。

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

2026-09-02 全仓专项审查结论（当时零 opt-in、不新增 `reaction_delay`）已归档；长期契约见 `docs/DECISIONS.md` D001，后续的 L2 反应层见 `docs/ARCHITECTURE.md`。

### 3.3 修改边界

- 不进行与当前任务无关的重构或格式化。
- 不修改用户未授权的模块。
- 不自动提交或推送，除非用户明确要求。
- 新增注释和项目文档使用中文。
- 遵循现有项目代码风格。
- 静态编译和单元测试不能替代用户明确授权的设备或游戏内测试。

## 4. 已完成的重要修改

§4.1 ~ §4.109 已提交并推送，全文移到 `docs/archive/AI_CONTEXT_history.md`（编号不变）；其中还没在真机上核对完的项目在 `docs/ROADMAP.md` 跟踪。
这里只保留还在等真机验证的条目（§4.110 ~ §4.158）。各节里的「未提交（在工作区）」是写作当时的状态：这些改动已在 2026-10-29 发布前审查后提交并推送到 `origin/master`（见 §2）。

### 4.110 ActivityShikigami 首领爬塔：复用普通爬塔流程，换用首领页资产；锁定同步与式神录入口有界

2026-10-20。未提交（在工作区）。**Level A/B PASS；Level C PENDING**，首领爬塔还从未在真机上完整跑通过（09-09 §4.62 时首领就被列为「非本期生产路径」）。

- **事故**：10-20 13:33 / 13:39 oas1 两次进入首领页（`page_climb_boss`，靠挑战键 `I_AS_BOSS_FIRE` 识别，两次都成功到达），随后卡在 `_sync_climb_team_lock('boss')` 的 `ui_click`：第一次要解锁、第二次要锁定，两次都没有任何点击、也没退出循环，分别在 15 秒 / 24 秒被手动停止（没到 60 秒卡死判定）。只读核查：旧 `I_LOCK` / `I_UNLOCK` 与体力那对 `I_AP_LOCK` / `I_AP_UNLOCK` 是同一张图（锁在 801）裁的（错开 1 像素后相似度 1.000），调用链、匹配实现、参数都没有问题；首领页的锁实际在 (907,651)，旧模板带的背景与首领页不同，两种状态都认不出。没有同名资产遮蔽，也没有旧模板缓存。
- **资产（用户 10-20 用 annotator 从首领页截取，确认可识别）**：`I_BOSS_LOCK` / `I_BOSS_UNLOCK`（`climb_boss_lock.png` / `climb_boss_unlock.png`，24×24，roi_front (907,651)，roi_back (744,632,265,74)，阈值 0.8）、`I_BOSS_MAIN_TO_RECORD`（`climb_boss_main_to_record.png`，(1024,561,39,42)）、`I_CHECK_BATTLE_BOSS`（首领页标题，**本轮没有接入**，首领页仍只用 `I_AS_BOSS_FIRE` 识别）。旧 `I_LOCK` / `I_UNLOCK` 现在没有代码引用，资产保留未删。
- **修改**：
  - `_sync_climb_team_lock`：首领用 `I_BOSS_LOCK` / `I_BOSS_UNLOCK`，体力 / 门票 / 百体仍用 `I_AP_LOCK` / `I_AP_UNLOCK`；两个分支的 `ui_click` 换成同一循环体的有界版 `ui_click_until_appear_or_timeout`（点击间隔仍是 1.5 秒），`ACTIVITY_TEAM_LOCK_TIMEOUT = 10` 秒内没看到目标状态就抛 `GameStuckError`，不带着未知状态去挑战。目标状态已显示时只截一帧、不点；相反状态时点一下并等到目标状态出现。
  - 新增 `_climb_records_entry`：首领用 `I_BOSS_MAIN_TO_RECORD`，其余类型仍用 `I_BATTLE_MAIN_TO_RECORDS`；`_run_climb_action` 把它交给 `switch_soul_for`。
  - `BaseAct.switch_soul_for`：进式神录的 `ui_click` 换成有界版，`SWITCH_SOUL_RECORDS_TIMEOUT = 8` 秒（间隔 1 秒）内没进式神录就抛 `GameStuckError`，不再调用切换御魂。伪神降临也走这个函数，成功路径不变，只是失败从 60 秒卡死判定变成 8 秒明确报错。
  - 两个上限都是 PROVISIONAL，点击次数都低于 Device 单按钮 10 次连点兜底。全局 `ui_click` 未改。
- **未改**：入口 `page_act --I_TO_BATTLE_BOSS--> page_climb_boss`、首领页识别、挑战键（首领 `I_AS_BOSS_FIRE`，其余 `I_ACT_FIRE`）、战斗退出条件、五倍卷同步、次数 / 时限、挑战前安全节点、FIRE、GeneralBattle、结算回收。
- **首领次数（同日 17:16 补充）**：16:56 真机首跑已证实锁定同步生效（点一次 `CLIMB_BOSS_UNLOCK`，0.73 秒后确认），随后在「CHECK BOSS RESOURCE」`TypeError: expected string or bytes-like object` 退出。原因：`O_REMAIN_BOSS` 自上游 `1874902b`（2026-05-07）起是 Digit 模式，`ocr_single` 已转成整数 110，`ocr_digit_counter` 再对整数做正则；识别框 (1169,668,70,30) 也只框到「1/10」。首领页这行字实际是「**额外奖励 1/100**」（额外奖励进度，挑战本身消耗活动体力 ×12）。**用户决定：额外奖励打满就停**，即沿用代码原有的「剩余 = b − a」，不按体力判断。用户在 annotator 里把识别框改成整行 (1063,669,208,31)、模式改成 DigitCounter（`ocr.json` / `assets.py` 17:16 重新生成），业务代码没改。新增 `BossRemainCountTest` 6 项：资产必须是 DigitCounter 且框住整行（防止以后 annotator 再存回 Digit）；只替换最底层识别模型，真实走模式分发 / 「a/b」解析 / 次数归一化——「1/100」→ 99、「100/100」→ 0 停止、打一场后按消耗快照 98、读不出不抛异常、换回 Digit 复现 TypeError。反向验证（内存里改回 Digit / 改回旧框）都被抓到。五倍卷：首领页没有这个开关，日志会打「Cannot identify climb penta toggle state」并继续，不卡住（未改）。
- **测试**：`tests/test_activity_shikigami_climb.py` 新增 23 项（`BossClimbAssetMappingTest` / `ClimbTeamLockSyncTest` / `ClimbSwitchSoulRecordsEntryTest` / `BossClimbFlowTest`）。沙盒用真实 `_sync_climb_team_lock` / `switch_soul_for` / `ui_click_until_appear_or_timeout` / `appear`（含 interval 门控）/ `appear_then_click` / L1 点击管线，只替换截图、`RuleImage.match` 与 `device.click`，虚拟时钟替换 `module.base.timer.time`。覆盖：资产与 annotator JSON 一致、任务实例取到的就是这些资产；首领入口与页面标志；目标已满足不点；相反状态只点一下并确认；首次点击丢失后按 1.5 秒间隔重试；认不出 / 点了不生效都在本地上限内抛错（点击 < 10、耗时 < 60 秒）；首领不认体力资产、体力不认首领资产、体力原行为不变；式神录入口正确传入并在切御魂之前；入口认不出 / 点不进都有界失败且不切御魂；锁定同步成功后进入挑战、失败时不进入挑战。反向验证（在内存里替换方法，不改源码）6 组全部被抓：首领用旧锁资产、回到无上限 `ui_click`、首领用体力式神录入口、式神录入口无上限、锁定失败静默继续、事故原实现（11 项失败）。L2 审计清单 3 行只改调用类型，登记册重新生成后总数与分类不变。
- **Level C 待验**：见 ROADMAP「ActivityShikigami 首领爬塔适配」条。

### 4.111 通用双实例同步核心 P1（`module/instance_sync/`，同心之兰的前置能力）

2026-10-21。未提交（在工作区）。**Level A/B PASS；尚未接入任何任务，没有 Level C。** 契约与取舍见 `docs/DECISIONS.md` D029。

- **起因与方向**：用户要做同心之兰双实例互赠（oas1 / oas2），要求先做可复用的通用同步框架。经只读设计审查后定为：同心之兰是**独立任务**（不挂在八岐前面，先后靠调度优先级）、游戏每天只允许成功互赠一次、自动新轮次为第一轮之外最多再重来 3 次（每天最多 4 轮，`max_rounds=4`）、`failure_interval` 保持默认 1 天由用户自己配置、结果未知 / 账本损坏按普通失败并排到下一个业务日、账本目录 `log/instance_sync/`。
- **新增**（全在 `module/instance_sync/`，**不改任何既有源码文件**）：
  - `state_machine.py`：账本文档上的纯函数 `op_enter` / `op_poll` / `op_ready` / `op_start` / `op_begin_attempt` / `op_resolve_attempt` / `op_verify` / `op_fail`，加 `expire`（会合 / 预算超时）、`classify_failed_round`（safe / unsafe）、只读快照 `RoundView`。
  - `invariants.py`：`validate_document`（读盘时结构 + 自洽）与 `validate_transition`（写盘前转换合法性）——终态不可逆、失败优先、时间戳只写一次、attempt 只追加、done / unknown / aborted 之后不重发、重试间隔、预算内才能开始新尝试。
  - `ledger.py`：`Ledger.transact`——FileLock（带超时）内「读 → 校验 → 变更 → 再校验 → 原子写」；损坏只备份 `.corrupt-<哈希>` 不覆盖，缺失 / journal 记录过却不在账本里 → `LedgerLostError`，不重建；`PermissionError` 有界退避。
  - `journal.py`（每实例只追加，仅用于发现账本丢失）、`adapter.py`（`SyncAdapter` 协议 + 只读 `SyncContext`）、`coordinator.py`（`SyncCoordinator.run()` → `SyncResult(status, reason, next_action)`）、`errors.py`。
- **行为要点**：任务启动时 `op_enter` 按当天最近一轮决定新建 / 加入 / 恢复 / 当天已完成（直接短路、不进游戏）/ 需人工（`unsafe_prior_round`）/ 达上限（`round_cap`）；会合窗口 600 秒（创建者落盘）、第二个 ready 起共享 180 秒预算、确认失败后至少等 30 秒再试且预算要容得下下一次；点击前先写 `prepared`，`dispatch` 之后任何异常都记 `unknown`、整轮失败、绝不重发；对端失败时在一个轮询周期内抛 `SyncCancelled` 退出；崩溃恢复只在整轮仍 open 且未过期时才 `inspect_attempt`；设备 / 适配器异常先把整轮写成 failed 再原样上抛同一个对象。`SyncResult.next_action`：`done` / `retry_later`（safe 且未达上限）/ `defer_next_day`（其余）。
- **人工确认并重置（同日追加，D029 补记）**：`unsafe` 当天被拦住后，解除方式是任务配置里一个一次性「确认并重置」开关，**不是重启**（重启分不清「人工核对过游戏」和「进程崩溃后又起来」）。核心已实现 `SyncCoordinator.acknowledge_unsafe(reason) -> AckResult` / `state_machine.op_acknowledge_unsafe`：在最后一轮（必须已 failed）的 `late_events` 追加 `acknowledge_unsafe` 事件，不改 schema、不改轮次状态和 attempts；之后 `op_enter` 照常开新轮。不绕过每天上限；open 轮次拒绝（过期的先判 failed）；completed / safe / 已确认过都无需确认；校验器限定该事件只能在 failed 轮次出现。**开关字段和「读到就调用一次、无论结果都关回去」的消费逻辑属于 P2，本次没有加任何配置字段。**清空整个 `log/instance_sync/` 仍是最后手段。
- **测试**（4 个文件共 140 项）：`test_instance_sync_state_machine.py` 71（op 序列每一步都用校验器交叉检查 + 手工改坏账本必须被拦）、`test_instance_sync_ledger.py` 23（损坏 / 未知版本 / 键不符 / 丢失 / 锁超时 / 写失败 / `PermissionError` 重试 / journal 半行）、`test_instance_sync_coordinator.py` 43（人工确认端到端：unknown → 拦截 → 确认 → 新建第 2 轮并 COMPLETED、旧证据保留；任一方可确认；重复确认无效；无账本 / 进行中 / 损坏的反应；不绕过上限；虚拟时钟 + 脚本化对端 + 假适配器：完整链路、会合超时、重试 30 秒不重置预算、预算不够立即失败、unknown 不重发、点击前被取消记 aborted、对端失败及时退出、四种崩溃恢复、轮次上限、握手不一致、账本损坏 / 丢失 / 锁超时 / 写失败、旧会话被取代）、`test_instance_sync_multiprocess.py` 3（两个真实 spawn 进程共用账本：同时提交最后一次核验恰好一次 completed、一方核验失败时绝不出现 completed、对端在 2 秒内感知 unknown）。另做 30 条变异检查（核心规则 19 条 + 轮次上限边界 3 条 + 人工确认 8 条，把规则逐条改坏，测试必须变红，全部被杀，见 D029 验证段）。
- **测试与变异检查中发现并已修的缺陷**：① 等待以「取消」（对端失败 / 会合超时）结束时没通知 `adapter.after_wait`（只在正常结束时通知），改成 `try/finally` 覆盖所有退出路径；② 变异体让等待循环不终止时测试空转了 10 分钟——兜底轮询上限从 100 万降到 2 万，测试虚拟时钟加「虚拟时间超过一天直接 `AssertionError`」哨兵。
- **未做 / 限制**：同心之兰任务、适配器、配置、`ConfigModel` 注册、菜单（P2–P5，见 ROADMAP P0「同心之兰双实例互赠任务」）；游戏机制（各自发送还是发起 / 接受、有无明确发送证据、账号身份、每日重置时间）全部**未核实**；`max_rounds` 是适配器协议参数，核心里没有写死数字，用户 2026-10-21 确认取 4（第一轮 + 最多 3 次自动重来），P2 / P4 写适配器时用 4，测试里的 `PARAMS` 也是 4。`failure_interval` 保持 `Scheduler` 默认的 1 天、由用户自己配置：账本按业务日分文件，默认值下 `retry_later` 实际是次日重试，同一天内出现第 2 ~ 4 轮只有用户把它调短才会发生。
- **工作区**：新增 `module/instance_sync/`（8 个文件）与 `tests/test_instance_sync_*.py`（4 个文件）；六份文档同步。HEAD 仍是 `8a82cb8f`，原有未提交内容（ActivityShikigami 首领适配与 annotator 重截的模板等）未被触碰。

### 4.112 同心之兰任务骨架 P2（`tasks/XinLan/`，`reset_unsafe` 一次性消费）

2026-10-21。未提交（在工作区）。**Level A/B PASS；还没有适配器，没有 Level C。** 契约与取舍见 `docs/DECISIONS.md` D029「补记（P2）」。

- **起因**：§4.111 的同步核心已提供 `SyncCoordinator.acknowledge_unsafe()`，但开关和消费逻辑留给 P2。本轮按 ROADMAP P0 把同心之兰作为**独立任务**接上编排，适配器（P4）依赖 P3 真机采样，所以这里只做不碰游戏的部分。用户本轮定名 `XinLan`（`tasks/XinLan/`，配置字段 `xin_lan`，与核心测试里的 `business_id='xinlan'` 一致）。
- **新增**：`tasks/XinLan/config.py`（`XinLan` = `scheduler` + `sync`（`instance_a` / `alias_a` / `instance_b` / `alias_b` / `rendezvous_timeout` 60~1800，默认 600）+ `reset`（只有 `reset_unsafe: bool = False`））、`business.py`（`BUSINESS_ID` / `PROTOCOL_PARAMS`（`max_rounds=4`）/ `DAILY_RESET` / `business_day()` / `next_business_day_start()`）、`script_task.py`（`ScriptTask(GameUi)` + 纯函数 `check_pair()`）、`__init__.py`。注册：`ConfigModel.xin_lan`、`ConfigMenu` 的 "Daily Task"、`SCHEDULER_PRIORITY` 末尾、`config/template.json`（手工插入，见下）、`assets/i18n/zh-CN.json`（只有中文）。
- **`reset_unsafe` 放在单独的 `reset` 分组，不在 `sync` 里（偏离 ROADMAP 原写法，用户本轮选定）**：`PUT /config/task/group/copy` → `ConfigModel.copy_task_group` 是整组复制，`sync` 本来就要从一个实例复制给另一个；开关放在 `sync` 里时，复制会把「已打开」带到对端，对端之后在一轮新的 unsafe 上无人工检查就被确认。整任务复制（`copy_script_task`）仍会带过去，只能靠 help 文案提醒。
- **一次性消费 = 先关、先落盘、后确认（fail-closed）**：`run()` 第一步 `_consume_reset_flag()`：读到开关 → 置 False → `config.save()` → 才往下走；`save` 抛异常则异常上抛、确认不会发生。「先确认、后关」时若确认成功但落盘失败，开关会残留到下一轮新的 unsafe 上，正是 D029 要防的绕过。消费放在配置合法性检查**之前**：配置不合法 / 没有适配器 / 确认被拒（`round_open` 等）/ 确认抛异常，开关都已经关掉（代价：修好配置后要重新打开一次）。确认和 `run()` 用同一个 `SyncCoordinator`。
- **编排**：消费开关 → `check_pair`（四个字段 strip 后非空、a ≠ b、别名 a ≠ b、自己的 `config_name` 在 a / b 里；不合法按失败排期，不写 pydantic validator）→ `_build_adapter()`（**P2 恒返回 `None`**，记警告、按失败排期、不碰账本）→ `_build_coordinator()` → 读到过开关则 `acknowledge_unsafe` 并记日志 → `coordinator.run()` → 按 `next_action` 排期：`done` → `success=True`；`retry_later` → `success=False`（`failure_interval` 由用户配置，任务不替用户设）；`defer_next_day` → `target=next_business_day_start(now), server=False`（不加 `server=False` 时 `task_delay` 会按 `server_update` 把 target 改写）。不抛 `RequestHumanTakeover`；适配器 / 设备异常由核心原样上抛，走调度器现有异常处理。`_build_adapter` / `_build_coordinator` 是测试注入点，P4 只改前者。
- **占位（未核实，P3 确认）**：`DAILY_RESET = 00:00`（决定账本业务日）、`PROTOCOL_PARAMS['min_attempt_cost'] = 10`（等 P3 测出单次尝试耗时）。
- **`config/template.json` 为什么手工插入**：`dev_tools/template_update.py` 重新生成会带出大量无关差异（`anti_ban`、`fatigue`、`behavior_trace_enable` 等模板里本来就落后的字段），只保留 `xin_lan` 一块，另一半不属于本轮。
- **测试**：新增 `tests/test_xin_lan_task.py` 26 项——开关（关着不 save 不确认；开着时调用顺序恰为 save(False) → build → ack → run；确认被拒仍继续跑；确认抛异常开关已关；配置不合法 / 无适配器时开关已关且不确认；save 抛异常则不确认）、`check_pair` 5 组、排期映射 4 项、适配器异常透传、协调器构造参数、业务日边界（含把重置时刻改成 05:00 的边界）、配置默认值 / `reset_unsafe` 不在可复制的 `sync` 里 / 旧配置缺 `xin_lan` 仍可加载 / 菜单 / `template.json` 与模型一致 / i18n 键齐全。全部用假配置 + 假协调器，不碰账本文件、设备、真实 `config/`。
- **未做 / 限制**：适配器（P4）、同心之兰 Level C 采样（P3）、双开验收（P5）；OASX 前端不改（bool 字段自动渲染成开关，D024）；`en-US.json` 只有 18 行、没有任务名条目，未加。**现在在配置里启用 XinLan 只会每次记一条警告并按失败排期**——这是有意的（没有适配器就不进游戏）。
- **工作区**：新增 `tasks/XinLan/`（4 个文件）与 `tests/test_xin_lan_task.py`；改 `config_model.py` / `config_menu.py` / `config_manual.py` / `config/template.json` / `assets/i18n/zh-CN.json`。HEAD 仍是 `8a82cb8f`。

### 4.113 annotator 实时采集不再注册截图帧（`Screenshot.register_image_frame`）

2026-10-21。未提交（在工作区）。**Level A/B PASS；Level C 待验。**

- **起因**：§8 记录的 `Unknown frame id`：图像服务全局只有一个，`ImageRuntime._config_frames` 每个 `config_name` 只保留一帧，`register_frame` 会删掉同配置旧帧；annotator 实时画面用 `Device(config=<同名配置>)` 每 0.5 秒 `screenshot()`，把同名配置正在运行的脚本刚截的帧顶掉（2026-10-10 / 10-20 两次，进程 `exit(1)`）。annotator 只要原始画面做预览 / 截图，不做匹配，用不着注册。采用 ROADMAP 记录的方案 A。
- **修改**：`module/device/screenshot.py` 新增类属性 `register_image_frame: bool = True`；`screenshot()` 里为 True 时行为与原来完全一致，为 False 时不调用 `register_frame`、`image_frame_id` 置 `None`（`Device.get_image_batch_cache` / `update_image_batch_cache` 本来就按 `None` 处理）。`module/server/tool_capture_worker.py` 的 `_build_device` 构造后设 `device.register_image_frame = False`。除这两处没有别的生产改动；`module/image/runtime.py`、TTL、RPC 协议都没动。
- **核实过的前提**：`image_frame_id` 的消费者全在 `tasks/`（`BaseTask.appear` / `match` 等）；`module/server/` 里没有任何基于 frame 的匹配；`Device.__init__` 的 `auto` 截图基准走 `screenshot_methods`（原始截图方法），不经过 `Screenshot.screenshot`，所以构造期间不会注册帧。
- **测试**：新增 `tests/test_screenshot_frame_registration.py` 4 项（默认每次截图注册一次并写入 `image_frame_id`；关闭后零次注册、旧 id 被清成 `None`、图像照常返回；开关是实例级、互不影响；`_build_device` 产出的设备已关闭注册且保留原有的 `disable_stuck_detection` / `screenshot_interval_set` 调用）。变异检查：把开关判断改成恒 True，其中 2 项变红。
- **未做 / 限制**：Level C 还没验——同一配置的脚本在运行时打开 annotator 实时画面，确认脚本不再出现 `Unknown frame id`。**验证通过之前，§8 的临时规则（同配置运行时不开 annotator 实时采集）继续保留。** 2026-10-07 Chess 那次 `Unknown frame id` 是另一种原因（同一帧 16 秒后才用、超过服务端 10 秒 TTL），与本项无关，仍未处理（ROADMAP P2）。
- **工作区**：改 `module/device/screenshot.py`、`module/server/tool_capture_worker.py`；新增 `tests/test_screenshot_frame_registration.py`。HEAD 仍是 `8a82cb8f`。

### 4.114 同心之兰 P3 资产采集与流程设计（`tasks/GameUi/page/image_xinlan.json`）

2026-10-21。未提交（在工作区）。**Level A 完成（对已采的 24 张整屏帧做模板命中自检）；没有 Level C；适配器（P4）见 §4.117。** 契约与取舍见 `docs/DECISIONS.md` D029「补记（P3）」。

- **起因 / 约定**：P2 之后 `_build_adapter()` 仍是 `None`，缺的是游戏里互赠的真实界面和流程。用户用标注器采集，**同心之兰的全部模板放 `tasks/GameUi/page/`**（由 `GameUiAssets` 导出，XinLan 直接引用，用户 2026-10-21 选定）。标注器整屏帧在 `log/annotator/<会话id>/uploads/`，会话关闭即删。
- **资产（`GameUiAssets`）**：图片 `I_TONGXIN_INI`（好友详情右上角图标的「初始」态，阈值 0.9）/ `I_INVITE_TONGXIN`（福袋页识别）/ `I_PURCHASE_TONGXIN`（A 的 30 勾玉购买按钮）/ `I_REPUR_TONGXIN`（B 的回赠按钮）/ `I_ACC_TONGXIN`（庭院左侧「同心之兰绑定邀请」弹窗的标题文字）/ `I_FRIEND_SAME_OPEN`（同区好友列展开时的 ▼）；OCR `O_NUM_TONGXIN`（图标下的 x/10、x/20）/ `O_NAME_TONGXIN_FRIEND`（好友详情头部名字）/ `O_NAME_TONGXIN_INVITER`（邀请弹窗里的邀请人名字）/ `O_TOAST_TONGXIN`（keyword「邀请已发送」，A 点购买后的小字提示）；点击 `C_FRIEND_SAME` / `C_THE_TOP_FRIEND`。规则文件 `image_xinlan.json` / `tongxin_ocr.json` / `click.json`。邀请弹窗的 ✓ / ✗ 复用 `GeneralInviteAssets.I_I_ACCEPT` / `I_I_REJECT`。
- **采集后的整理**：两处拼写错误（`purchase_tongixn`、`tonxin_ini`）在还没有代码引用时改成 `purchase_tongxin` / `tongxin_ini`（png 同步改名）；`the_top_friend` 的 roiBack 原来抄的是 `friend_same`，改成与 roiFront 一致；补 `friend_same_open` 模板（从 112228 帧切 458,164,30,22；导航据此决定要不要点 `friend_same`，避免已展开时再点把列表收起）和两个 OCR 名字区域。`assets.py` 用 `AssetsExtractor('tasks/GameUi').extract()` 重新生成，diff 里只有同心之兰相关常量（生成器写的注释行尾带一个空格，`git diff --check` 会报，与既有 `ActivityShikigami/assets.py` 一致）。`tasks/GameUi/page/page_num_tongxin.png`（「0/20」小图）没有任何规则引用，保留未删。完成判据读的是分母（见下），分子会变，所以它不能当「已完成」模板，可删。
- **游戏流程（从截图读出，与 P1 / P2 的假设不同）**：① 同心之兰要花 **30 勾玉**（**扣在对方接受时**，不是点购买 / 回赠时，用户 2026-10-22 确认；福袋页「每天限购 2 次（0/2）」；规则文字「每天最多送出 2 次，接收 1 次」，好友接受后可立即回赠，成长值到 20 后获得第 2 次奖励）；② **先后依次进行**：A 在好友页（好友 → 同区好友 ▼ → 置顶好友）点右上角图标 → 福袋页点 30 勾玉购买并邀请 → B 庭院左侧弹出「同心之兰绑定邀请」→ B 点 ✓（**接受后不跳转页面、没有提示，弹窗只是消失**），B 的图标变成 `0/10` → B 打开福袋页点「回赠」（同样 30 勾玉）→ A 弹出同样的弹窗，点 ✓ → 双方图标都显示 `x/20`；③ 图标三态「初始 → x/10 → x/20」加上回赠按钮在不在，是好友页上能读到的状态，核验和崩溃恢复都有明确证据；④ **进好友列表无条件复位（用户 2026-10-22 补充）**：有通知时进入好友页，列表不会停在最顶端，要先点「最近好友」标签、再点「好友」标签才会回到顶部；固定坐标的 `friend_same` / `the_top_friend` 不复位就可能点到别的行，A 会在错的人身上花 30 勾玉。
- **自检**：6 个模板对 24 张帧逐一匹配（`dev_tools/assets_test.load_image` + `RuleImage.test_match`，只做 cv2 模板匹配），命中位置全部符合预期：A 的福袋页命中 invite + purchase，B 的福袋页命中 invite + repur，弹窗帧命中 acc，好友页命中 friend_same_open，福袋页覆盖时不命中 friend_same_open。两个新 OCR 区域只用裁图目测核对，真实 OCR 识别留到 Level C。
- **A 点购买之后（用户 2026-10-21 确认并给出截图）**：没有确认弹窗，页面不变，只出现一条一闪而过的小字「邀请已发送。」（约在 550,222 一带的深色横条上）。这就是 A 那次点击「已发出」的瞬时证据，对应 `O_TOAST_TONGXIN`（OCR + keyword；提示底色是半透明的，不用图片模板）。提示一闪而过，适配器必须点完立刻连续截图轮询；没看到只能算 unknown，不是失败证据。**它只是快速通道**：A 的主证据改为 B 的回赠页面（见下「设计」）。
- **设计（写进 D029 补记（P3），代码留给 P4）**：固定角色（`instance_a` 永远先送，`instance_b` 永远回赠，用户选定）+ 依次执行。同步核心不改，只加一个可选适配器钩子 `await_turn(ctx) -> bool`（默认 True，§4.115 已加，在每次写 prepared 之前调用；B 在这里等 A 的尝试出现、接受弹窗、打开回赠页面，**亲眼看到 `repur_tongxin` 才返回 True**，否则返回 False 按 `prepare_failed` 安全失败）。**证据（用户 2026-10-21 提议）**：B 只有看到回赠按钮才写 prepared，所以 B 的账本里出现尝试 = B 替 A 确认了「送到了」；A 的 `judge` = 小字提示或 B 的尝试出现，任一成立算 done；B 的 `judge` 等 A `verified`；A 的 `verify` 等回赠弹窗 → 点 ✓ → 读分母；三处等的都是对方更早的一步，没有环，核心不用改（`peer_attempts` / `wait_until` 已有）。**每次进好友列表（A 的入口、A / B 的 `verify`）先无条件点「最近好友」→「好友」复位，确认好友标签已选中才点固定坐标，确认不到就不点购买**。扣勾玉的点击只点一次；没有明确证据一律 `unknown`，当天停下等人工 `reset_unsafe`。
- **用户 2026-10-22 补答**：好友页「好友」「最近」两个标签的选中 / 未选中图已采（`I_FRIEND_LIST_SEL/UNSEL`、`I_FRIEND_CUR_SEL/UNSEL`）；绑定邀请弹窗**在任何页面都会弹**；B 点回赠之后**没有确认弹窗**；福袋页**点空白处关闭**；每日 **0 点**重置。其余仍缺项（福袋页「每天限购 2 次（x/2）」计数点购买后会不会变；失败情况：勾玉不足、当天次数用完、对方不在线、邀请没人接受会不会过期 / 退不退勾玉；已经 `x/20` 的第二天图标和福袋页；每步耗时）要在 P5 真机上看，见 §4.117。**完成判据（用户 2026-10-21 确认）**：赠送完之后 OCR 读到**分母是 20** 就算互赠成功，不要求分子为 0（规则写「每次组队通关副本增加成长值 1 点」，当天打过副本后可能是 `3/20`）。
- **关联隐患（ROADMAP 待验）**：`GeneralInvite.check_then_accept()` 不区分邀请类型，且点 ✓ 后循环到 `is_in_room()` 才返回；绑定邀请接受后不进房间，组队任务的队员若在等待时收到绑定邀请，可能误点并卡住。
- **工作区**：新增 `tasks/GameUi/page/image_xinlan.json` / `tongxin_ocr.json` 与 7 张 png（含孤儿的 `page_num_tongxin.png`），改 `tasks/GameUi/page/click.json` / `tasks/GameUi/assets.py`。没有代码逻辑改动，全量测试 2430/2430 不变。HEAD 仍是 `8a82cb8f`。

### 4.115 同步核心可选钩子 `await_turn`（先后有序的业务用，P4 前置）

2026-10-21。未提交（在工作区）。**Level A/B PASS；没有 Level C。** 设计与取舍见 `docs/DECISIONS.md` D029「补记（P3）」。

- **起因**：同心之兰是先后依次进行的（A 先送、B 后回赠，§4.114），而 `SyncCoordinator._phase_execute` 在 `ready` 之后直接写 prepared、点击，B 没有地方「等 A 先送」。钩子不依赖任何截图，所以先于适配器（P4）做完。
- **修改**：`module/instance_sync/adapter.py` 新增 `SyncAdapter.await_turn(ctx) -> bool`，**非抽象、默认 `True`**（现有适配器和 `FakeAdapter` 不受影响）；`module/instance_sync/coordinator.py` 的 `_phase_execute` 在每次 `_begin_attempt` 之前调用它（含「not_done 后 30 秒重试」的下一次，所以适配器必须幂等）。返回 `False` → `self._fail(sm.R_PREPARE_FAILED, 'await_turn')` 并结束执行阶段。**账本、状态机、校验器都不改，不新增失败原因常量。**
- **语义**：失败后能不能安全重来由现有 `classify_failed_round` 判定——双方都没有尝试 → safe → `retry_later`；对端已经有 prepared / unknown / done 的尝试 → unsafe → `defer_next_day`（勾玉有真实代价，等人工 `reset_unsafe`）。钩子抛异常沿用 `run()` 里 `BaseException` 分支（先把整轮写成 `exception:<类型>` 再原样上抛）。适配器等对端先发用已有的 `ctx.wait_until(lambda v: bool(v.peer_attempts), timeout=ctx.remaining())`，对端 prepared 就够，不要等 done（否则会和对端的 `judge` 互相等）。
- **测试**：`tests/test_instance_sync_coordinator.py` 新增 `TurnAdapter`（`FakeAdapter` 子类，脚本化 `await_turn`；单独子类是为了不让 `await_turn` 出现在 `FakeAdapter.calls` 里、不改既有用例对调用顺序的断言）和 `AwaitTurnTest` 8 项：默认适配器放行；调用顺序恰为 `prepare → await_turn → dispatch → judge → verify`；返回 False 且无任何尝试 = 安全失败、不 dispatch、整轮 failed；返回 False 而对端已 prepared = unsafe、不再重来；钩子异常先写 failed 再原样上抛；重试前再问一次（共 2 次）；等对端尝试出现才发（对端 20 秒写 prepared、22 秒才 done，我方在 20~22 秒之间发）；对端永远不发则在预算内放弃。变异检查：删掉调用 7 项变红，把 False 当放行 3 项变红，均已还原。全量 `2430 → 2438`。
- **一个值得记的细节**：等待上限取 `ctx.remaining()` 时，是钩子先到点返回 False（`prepare_failed`），而不是 `budget_timeout`（后者要 now 严格大于 deadline 才触发）。两种都是安全失败。
- **未做 / 限制**：XinLan 适配器（当时未写，已在 §4.117 完成）。
- **工作区**：改 `module/instance_sync/adapter.py` / `coordinator.py`、`tests/test_instance_sync_coordinator.py`。HEAD 仍是 `8a82cb8f`。

### 4.116 RealmRaid 退四「再次挑战」点击后的 settle 窗口（oas2 10-22 13:40 卡死）

2026-10-22。未提交（在工作区）。**Level A/B PASS；Level C 待验。**

- **起因**：oas2 退四第 2 场失败后，`_fire_again()` 依次点了「再次挑战」→「不再提示」复选框 → 共享确认弹窗（前 3 个 attempt 全被用掉），attempt 4 又点了一次「再次挑战」。`_wait_again_entered_battle()` 在点击后 0.1~0.2s 的第一帧仍看到旧失败页（`I_FIRE_AGAIN` 可见），立刻返回 `failure_page`；这已是最后一次 attempt，循环耗尽返回 False。实际游戏已进 `page_battle_prepare`（报错截图可证）。`run()` 走 aborted 分支，`finally: ensure_lock(lock_default)` 的 `while 1` 在准备页找不到锁图标，空转 60s → `GameStuckError` → 游戏重启（Restart 约 40s 恢复，之后 RealmRaid 正常）。
- **根因**：点击后第一帧还没反映游戏响应，却被当成「仍在失败页」的决定性结论。近两天日志几乎每轮退四都有一次重复点击「再次挑战」，以往靠后续 attempt 的「按钮消失」分支兜底，这次 popup 把余量用到 0。与 2026-09-11 Level C（最后一次 attempt 的 gone 分支裸 continue）同一家族。
- **修改**（只动 `tasks/RealmRaid/script_task.py`）：新增 `RR_AGAIN_POST_CLICK_SETTLE = 1.5`；`_wait_again_entered_battle(timeout, settle=0)` 新增 `settle` 参数——settle 窗口内只认 `battle`，旧失败页 / 弹窗 marker 仍可见不作结论，窗口过后才按 `failure_page` 判定；`_fire_again()` 在点击「再次挑战」后、以及点击确认弹窗 `I_FRESH_ENSURE` 后都传 `settle`（确认弹窗后进入战斗则 return True，不再在过渡帧补点「再次挑战」）。pre-click 未就绪与 reaction 期间按钮消失两个分支保持无参（settle=0）调用，行为不变。**不放大任何 timeout**（`RR_AGAIN_POST_CLICK_TIMEOUT` 仍为 3）。
- **没做 / 为什么**：`ensure_lock` 没加超时或页面前提——它每轮循环顶也在调，识别失败时有界化会带着错误锁定状态继续打，比 GameStuck 更隐蔽；aborted 之后真正需要的是「从失败页 / 准备页回九宫格」的恢复事务，属新流程设计、没有真机证据，记入 ROADMAP。目前剩余的真 aborted 由 GameStuck → Restart 兜底。
- **测试**：`tests/test_realm_raid_state.py` 新增 `FireAgainPostClickSettleTest` 5 项（settle 内失败页不判 failure_page / settle 过后判 failure_page / 默认无 settle 立即判 / 确认弹窗点击后进战斗且不再点「再次挑战」/ 源码形态）。既有用例一个未改。全量 `2438 → 2443`。
- **Level C 待验**：退四日志里 `RES_FIRE_AGAIN` 每场只点一次；popup 那一轮出现 `Fire again: entered battle after confirm`；不再出现 `bounded retry` 后接 `Wait too long`。**需重启 OAS 进程生效。**
- **工作区**：改 `tasks/RealmRaid/script_task.py`、`tests/test_realm_raid_state.py`。HEAD 仍是 `8a82cb8f`。

### 4.117 同心之兰 P4 适配器（`tasks/XinLan/adapter.py`，已接入 `ScriptTask`）

2026-10-22。未提交（在工作区）。**Level A/B PASS；Level C：用户 2026-10-22 实机跑过一次，反馈「同心之兰功能没问题」；日志 / 账本没有回传，占位参数还没回填。** 设计见 `docs/DECISIONS.md` D029「补记（P3）」「补记（P4）」。

- **起因**：用户 2026-10-22 补答了写适配器缺的几项：好友页「好友」「最近」两个标签的选中 / 未选中图已采；绑定邀请弹窗**在任何页面都会弹**；B 点回赠之后**没有确认弹窗**（之前说的「确认弹窗」指的是 B 回赠后 A 那边弹出的绑定邀请）；福袋页**点空白处关闭**；每日 **0 点**重置，当天账本里已有成功记录就不再发起（核心的 `already_completed` 本来就支持）。
- **资产小修**：`tasks/GameUi/page/click.json` 新增 `tongxin_icon`（好友详情右上角图标，`C_TONGXIN_ICON`）——`I_TONGXIN_INI` 是模板（阈值 0.9）只匹配初始态，B 接受后图标变成 `0/10`，所以打开福袋页改用固定区域点击；`tongxin_ocr.json` 的 `num_tongxin` 由 `Single` 改成 `DigitCounter`，直接读 `(cur, remain, total)` 判分母；删掉 `page_friend_list.png`（与 `page_friend_list_sel.png` 逐字节相同、没有引用的多余副本）；`assets.py` 用 `AssetsExtractor` 重新生成，diff 只有这两处。
- **适配器**：`XinLanAdapter`（两端共用的导航 / 读数）+ `SenderAdapter`（instance_a）+ `ReceiverAdapter`（instance_b）+ 工厂 `make_adapter(task, sync, config_name)`；`ScriptTask._build_adapter()` 返回它，「适配器为 None 就跳过」的分支已删。所有碰设备的操作收在 `_shot / _seen / _tap / _ocr / _goto_friends / _keepalive / _pause` 几个薄方法里，测试覆盖它们就能离线跑完整流程；不往 `BaseTask` 加 helper。
- **时序（按 D029 补记（P3）的证据设计）**：A `prepare` = 进好友列表 → 无条件复位（最近 → 好友各点一次，不看标签模板）→ 展开同区好友 → 点置顶好友并 OCR 核对头部名字就是对端（对不上整套重做，最多 `OPEN_TRIES=3` 次）→ 点图标进福袋页 → 看到购买按钮；`dispatch` 只点一次购买；`judge` = 前 6 秒读小字提示「邀请已发送」，或账本里出现 B 的尝试，任一成立 done，`JUDGE_WAIT`（90 秒，受总预算约束）内都没有 unknown；`verify` = 等 B 回赠后弹出的绑定邀请 → 邀请人对得上才点 ✓ → 点空白关福袋页 → 再进好友详情读分母 == 20。B `prepare` 停在好友详情；`await_turn` = 等 A 的尝试出现 → 接受绑定邀请 → 开福袋页 → **亲眼看到回赠按钮才返回 True**（接受邀请这一步的结果不作判据，重试时弹窗早已接受，以回赠按钮在不在为准）；`dispatch` 只点一次回赠；`judge` 等 A `verified`；`verify` 读分母 == 20。`inspect_attempt` 只读账本：A 看 B 有没有尝试，B 看 A 有没有 `verified`，其余 unknown。
- **实现时的取舍**：① `_shot` 每次先清设备卡死计时——适配器里的等待循环都有明确超时，不清的话「只截图不点击」满 60 秒会被当成卡死；`after_wait` 同理（账本里的纯等待不截图）；② 小字提示只在点完购买后的前 `TOAST_WINDOW`（6 秒）OCR，之后再读也读不到，省掉无谓的 OCR；③ 邀请人名字对不上就不接受（别的邀请不是本任务的），日志只在名字变化时记一次；④ 角色拆成两个子类而不是一个带 if 的类。
- **测试**：新增 `tests/test_xin_lan_adapter.py` 39 项——`FakeGame`（每端的页面 / 标签 / 列表是否在顶端 / 弹窗 / 福袋页 / 图标分母 + 点击日志）；复位顺序与有通知时不点错行、已展开不收起、名字不对不进福袋页；2026-10-24 起另有两项：标签模板怎么说都照点最近 / 好友各一次、名字不对整套重做且次数有限；A 的 `dispatch` 只点一次、取消后不点；`judge` 三种证据组合；`verify` 只看分母、不看分子；B 的 `await_turn`（对端没发就不碰屏幕 / 外人邀请不接受 / 重入幂等 / 看不到回赠按钮就 False）；两个线程各跑一个真实 `SyncCoordinator` 共用临时账本：正常完成且各点一次、同一天再跑两边都是 `already_completed` 且不碰屏幕、漏掉小字仍靠 B 的回赠按钮完成、A 没送到则整轮 unsafe 停一天且没有第二次购买。`tests/test_xin_lan_task.py` 删 1 项（适配器为 None 的用例）、改 1 项（默认任务按配置名构造对应角色的适配器）。变异检查 5 条（去掉标签复位 / 不核对邀请人 / 回赠点两次 / 不看回赠按钮 / A 的 `judge` 不看对端尝试）各有对应测试变红，已还原。全量 `2443 → 2481`。
- **2026-10-24 oas1 卡死修复（Level A/B，未上真机）**：oas1 进好友页后列表没回顶，`the_top_friend` 连点在已选中的另一位好友（非对端）上，满 10 次触发 `GameTooManyClickError`，游戏被重启、第 1 轮整轮失败（oas2 跟着失败）。根因：`_open_peer_detail` 原先「看到 `I_FRIEND_CUR_SEL` 就跳过点『最近』」，而标签的选中 / 未选中模板互相得分都在 0.94 以上（阈值 0.8 分不开；用报错截图实测 `CUR_SEL` 0.945、`LIST_UNSEL` 0.943），未选中的「最近」被判成已选中，复位整个被跳过。修复：最近 → 好友各无条件点一次（点完各等 `CLICK_GAP`），不再用标签模板判断；名字 OCR 对不上就整套重做，最多 `OPEN_TRIES=3` 次，不在原地连点同一坐标。同区好友的标题行是开关（用户 2026-10-24 确认：展开时点会收起），所以展开步骤改成 `_expand_same_list()`，**只认同区的 ▶（已收起）**：看到 ▶ 才点标题行（点完再看，最多 `SAME_TOGGLES=3` 次），看不到就当作已展开、往下点置顶好友，由名字 OCR 兜底；绝不在没看到 ▶ 时点。新增资产 `I_FRIEND_SAME_CLOSE`（`page_friend_same_close.png`，从用户 2026-10-24 给的截图里跨区好友行的 ▶ 裁出，30×26）；实测 ▼ 画面上得分 0.70、▶ 画面上 1.0（阈值 0.8）。模板取自跨区行的同形状 ▶；已用用户 2026-10-24 补的同区收起真实截图核对：同区标题行上 `I_FRIEND_SAME_CLOSE` 0.993、`I_FRIEND_SAME_OPEN` 0.69（同区收起时跨区好友展开、标题行上移，固定的置顶好友点击区会落在跨区标题上，所以必须先展开同区）。 不再复用 30 秒的 `_click_until`（同一按钮来回开关会先撞单按钮 10 次点击上限）。`I_FRIEND_SAME_OPEN` 现在没有调用方，资产保留。新增 4 项测试（见到 ▶ 点一次、没见到 ▶ 不点、点击次数有界、▶ 漏识别不进福袋页）。
- **未做 / 限制**：没有上真机。所有时间常量（`POLL / CLICK_GAP / NAV_TIMEOUT / ACCEPT_WAIT / REPUR_WAIT / NUM_WAIT / JUDGE_WAIT / TOAST_WINDOW`）和协议参数里的 `budget=180` / `min_attempt_cost=10` 仍是占位。
- **勾玉在接受时才扣（用户 2026-10-22）**：不可撤销的点击是 `_accept_invite` 里的 ✓，不是购买 / 回赠；现有时序已经保守（B 在 A 的 prepared 写进账本之后才接受，接受后任何失败都归 unsafe 停一天），不改设计，见 DECISIONS D029 补记（P4）。
- **P5 验收前准备**：① 两个实例的 XinLan `sync` 分组填相同的值（`instance_a=oas1`、`instance_b=oas2`；`alias_a` = oas2 好友详情头部显示的 oas1 角色名，`alias_b` = oas1 好友详情头部显示的 oas2 角色名，别名也用来核对绑定邀请弹窗里的邀请人），两边都把对方放在「同区好友」的置顶好友位置；② 两个实例的 XinLan 都 `enable`，`priority` 调到 1（`duel` 等任务 `next_run` 已过期，不调高优先级会排在它们后面）；③ 两边各自起脚本，间隔别超过 `rendezvous_timeout`（600 秒），最好都在庭院空闲时；④ 这一轮共 60 勾玉，都扣在对方接受时；⑤ 跑完回传 `log/<日期>_oas1.txt` / `_oas2.txt` 里 `XinLan` / `Instance sync` 的部分、`log/instance_sync/` 下的账本 `*.json` 和两个 `*.journal.jsonl`，中途停下就附上停在哪个界面的截图。失败时先人工看游戏里有没有发出去、勾玉有没有扣（发出但没被接受的邀请可能还挂着），再决定要不要打开 `reset_unsafe`。
- **P5 真机清单**：点空白（`C_RANDOM_LEFT`）关福袋页是不是真的点在空白、会不会点到好友列表；`GeneralInviteAssets.I_I_ACCEPT` 能不能点中同心之兰弹窗的 ✓；名字 OCR 和 `DigitCounter` 的实际识别；小字提示能不能截到；B 接受后重开的福袋页会不会立刻出现回赠按钮；每步实际耗时（回填占位）；失败情况（勾玉不足、次数用完、对方不在线、邀请过期会不会退勾玉）；已经 `x/20` 的第二天界面；福袋页「每天限购 2 次（x/2）」计数点购买后会不会变。
- **工作区**：新增 `tasks/XinLan/adapter.py`、`tests/test_xin_lan_adapter.py`；改 `tasks/XinLan/script_task.py` / `business.py`（只改注释）、`tests/test_xin_lan_task.py`、`tasks/GameUi/page/click.json` / `tongxin_ocr.json` / `assets.py`，删 `page_friend_list.png`。HEAD 仍是 `8a82cb8f`。

### 4.118 组队会合：组队任务开始前先等对方实例到场（`module/instance_sync/team.py`）

2026-10-22。未提交（在工作区）。**Level A/B PASS；Level C 待验（用户实机跑）。** 设计见 `docs/DECISIONS.md` D030。

- **起因**：用户实机跑通同心之兰后提出：调度模式下两个实例各跑各的，A 先做完上一个任务进了组队任务，B 还在做上一个任务，组队对不上（队长邀请等 2 分钟没人就失败）。要求组队任务开始前等对方做完上一个任务再一起开始；不设固定超时；按身份自动判断哪些任务要会合；配置放「脚本设置」。
- **做法**：每个实例只写自己的在场文件 `log/instance_sync/team/<实例名>.json`（`idle` / `running` / `waiting`，带本实例所有组队任务的 `next_run` 快照，心跳 10 秒，60 秒没更新算不在线）；组队任务门口在配对锁里「读对方 → `decide()` → 写自己」，每 2 秒一次。对方在忙、这个任务在它那边已到点就一直等；确定对方不会来才推迟（推到对方这个任务的 `next_run` / 它空闲到的时间；不在线 10 分钟；身份不互补 30 分钟）；两个组队任务卡住时后到的一方推迟 3 分钟让路。规则表见 D030。
- **接入**：`Script.loop` 在 `prepare_task_execution` READY 之后调 `self.team_sync.gate()`（`team_sync` 是 `cached_property`，现有用 `Script.__new__` 构造的调度器测试不用改）；推迟走 `task_delay(..., server=False)`；`get_next_task()` 每轮写 `idle`；`loop()` 开头起心跳线程。非组队任务只写一下 `running` 就放行；没开同步时不写任何文件。
- **配置**：脚本设置 →「组队同步」（`Script.team_sync`：`enable` / `peer_instance`），oas1 填 `oas2`、oas2 填 `oas1`。`zh-CN.json` 追加 4 个键；`config/template.json` 不改（同 `anti_ban`）。现在两边在用的组队任务身份已互补：御魂 oas1 队员 / oas2 队长，契灵 oas1 队长 / oas2 队员。
- **测试**：新增 `tests/test_team_sync.py` 30 项——`decide()` 逐行；两个组队任务卡住时对两边各算一次，断言恰好一边让、而且是后到的那边；在场文件往返 / 坏文件 / 心跳；两个真实 `PresenceBoard` 在两个线程里会合（同时到、一先一后、对方先在跑别的任务、不在线、配置变了中断、中断前对方已开始仍开始）；用真实配置模型判断身份；真实 `Script.loop` + 真实 `Config`：没开同步照常跑、对方不在线推迟 10 分钟且不执行、非组队任务照常跑。变异 4 条（`task_delay` 不传 `server=False` / 让路顺序反过来 / 不认对方的 `partner_token` / 中断覆盖开始）各有测试变红，已还原；前两条最初没被抓到，补强了测试（推迟用例把御魂的服务器刷新时间改成 5 点、让路用例断言具体哪一边让）。全量 `2481 → 2511`。
- **自审修补（同日，D030 补记（自审））**：① 对方正在跑（或马上要跑）同心之兰、而同心之兰在我这边也到点时，我推迟当前组队任务 3 分钟让路（`yield_to_paired_task`）——否则两边 XinLan 的 `next_run` 差几秒时，一边在 XinLan 里等、另一边在御魂门口等，10 分钟后 XinLan 会合超时并排到明天；同心之兰以 `role=pair` 进快照（胶水层常量 `PAIRED_TASKS`），但不进门口；我这边是否到点每 2 秒按当前时间重判。② 契灵的交替身份 `handoff1` / `handoff2` 也算组队，身份互补改查表（`leader↔member`、`handoff1↔handoff2`）。③ `Script.loop` 在 `prepare_task_execution` 之前先 `TeamSync.precheck()`（只读对方文件、不加锁不写文件），确定对方不会来就直接推迟，不唤醒模拟器 / 游戏；「不在线 / 没配成对方 / 对方没开这个任务 / 身份不互补」每个实例每天每种原因用 `config.notifier.push` 推一次提醒。 `tests/test_team_sync.py` 新增 8 项；变异 4 条（去掉让路 / 身份规则退回旧写法 / 去掉 precheck / 去掉每日去重）各有测试变红，已还原；全量 `2511 → 2519`。
- **未做 / 限制**：没上真机。只同步开始，不同步结束；各组队任务内部的邀请等待照旧；对方的 `next_run` 快照有一轮调度的滞后；等待中不检查本实例的防风控睡眠时间段；长时间停在庭院会不会断线要真机看。
- **真机要看**：两边开启后，御魂 / 契灵一先一后到时先到的一方日志出现 `Team sync: waiting for ...`，对方做完上一个任务后两边都是 `-> go (met / peer_started_with_me)`；一边停脚本时另一边 60 秒后改成推迟 10 分钟；`log/instance_sync/team/` 下两个在场文件的内容；对方不在线时这边不再拉起游戏、当天收到一次推送；同心之兰和组队任务同时到点时出现 `yield_to_paired_task` 并先做同心之兰。
- **工作区**：新增 `module/instance_sync/team.py`、`module/script/team_sync.py`、`tasks/Script/config_team_sync.py`、`tests/test_team_sync.py`；改 `script.py`、`tasks/Script/config.py`、`assets/i18n/zh-CN.json`。HEAD 仍是 `8a82cb8f`。

### 4.119 每日琐事修复：吉闻奖励关闭点、庭院事务多轮领取（照 synevo）、完成记录与循环上限

2026-10-22。未提交（在工作区）。**Level A/B PASS；Level C 待验（用户实机跑）。** 设计见 `docs/DECISIONS.md` D031。

- **起因**：用户要优化每日琐事。10-16 两个号都在吉闻之后「页面未知 → 重启」，现场截图是庭院上盖着「友情点」/「体力」道具说明框；用户确认是奖励框改版，公共关闭区域 `C_UI_REWARD` 会点到道具。原循环 2 秒计时点了祝福也不重置，奖励还没出来就记「没有吉闻」并离开，而且没领到也记完成。庭院事务一次领不完（逢魔最多 3 次现世首领），原代码只在旧截图上试点一次一键完成；用户要求照 synevo。另查出：寮祈愿从不写 `guild_donate_dt`（开启后一天每次运行都重新捐）、商店签到进礼包屋前就记完成、多处 `while True` 没有本地上限。用户要的「定时领体力」等截图后再写。
- **吉闻**：「没事可做」计时每点一次祝福就重置（3 秒），总上限 20 秒；看到「获得奖励」后点 `GeneralBattleAssets.C_RANDOM_BOTTOM` 关到消失（`_close_luck_reward`，有界 5 秒）；顺带关「好友羁绊提升」；只有领到奖励才写 `luck_msg_dt`。
- **庭院事务（照 synevo，去掉轮换部分）**：从 synevo 拷 `dt_is_complete.png` / `dt_dailyffair_reward.png` 及 json 两条，重新生成 `assets.py`（只多 `I_IS_COMPLETE` / `I_DAILYFFAIR_REWARD`）；`DoneRecord` 加 `courtyard_morning_dt` / `courtyard_evening_dt`（`config/template.json` 同步）；`_current_courtyard_period` 分 05:00–18:00 / 18:00 之后，05 点前不做；最多 3 轮「一键完成 → 点同一位置关奖励页 → 5 秒内看全部完成」，各种失败也记完成（synevo 的取舍）；进「日常」标签加 10 秒上限。
- **其它**：寮祈愿结束写 `guild_donate_dt`，`switch_select` 加 10 秒上限并返回成败，`donate` 切换失败就停；商店签到最多等 3 秒按钮，领完按钮消失才记完成（没有按钮按原规则当作已签）；买体力进杂货页 15 秒、购买 60 秒上限，超时不记完成；今忆召唤点券 / 单抽确认每步 15 秒上限（超时返回后 `run_one_summon` 照旧记当天已完成，避免重复花券）。领取邮件、普通召唤、调度不动。
- **L2 登记册**：新增 3 个点击调用点（吉闻关闭 `click`、关羁绊弹窗 `appear_then_click`、去掉 `ui_reward_appear_click`；庭院关奖励页两处 `click`），`--write` 重新生成 `docs/L2_CALLSITE_REGISTER.md`：1100 → 1103、EXCLUDED 138 → 141、rule 901 → 904，`tests/test_l2_c0_registry.py` 钉住值与注释同步；`tests/test_l1_stage3b_global_guard.py` 的今忆召唤替身补一个 `RECALL_STEP_TIMEOUT`。
- **测试**：新增 `tests/test_daily_trifles.py` 23 项（假界面驱动真实方法）——吉闻：奖励晚于旧 2 秒窗口仍领到、关奖励只点下方空白从不点 `C_UI_REWARD`、没吉闻 / 奖励不出现都不记且有界、羁绊弹窗被关；庭院事务：时段边界、出现 2 次现世首领要 3 轮、一直不完成只点 3 轮后记完成、已完成不点击、没入口记完成、标签进不去有界、该时段做过跳过；寮祈愿：写日期后同日跳过、切换有界；商店签到三种情况；买体力两处上限。变异 8 条（关奖励改回 `C_UI_REWARD` / 吉闻总记完成 / 不重置计时 / 庭院只点一轮 / 不写 `guild_donate_dt` / 签到按钮还在也记 / 去掉进杂货页上限 / 去掉切换上限）各有测试变红，已还原。全量 `2519 → 2542`。
- **审查后修补（同日，D031 补记）**：① 寮祈愿 `all_done = all_done and self.donate(...)` 在寮友名单失败后短路，好友名单不执行（改动前就有），改为先执行再合并；② 庭院事务每轮先等最多 3 秒（`COURTYARD_BUTTON_WAIT`），等到「一键完成」或「全部完成」出现再判断，避免刚切到日常标签或现世首领提示还在时 3 轮在一秒内用完——这是对 synevo 写法的一处偏离；③ 吉闻循环里「好友羁绊提升」最多点 3 次（`LUCK_FRIENDSHIP_MAX`）且不重新计时，防止这张小模板在固定位置误匹配时把循环拖到上限、连续点击触发 TooManyClick。 `tests/test_daily_trifles.py` 再加 4 项；变异 3 条（短路写回 / 不等按钮 / 去掉羁绊次数上限）各有测试变红，已还原；全量 `2542 → 2546`。吉闻修复成立的前提（奖励框能被 `I_UI_REWARD` 认出）只能实机确认，见 ROADMAP 每日琐事 Level C ①。
- **未做 / 限制**：没上真机；定时领体力已在 §4.120 实现；签到「按钮消失才算」依赖领完后按钮确实消失；吉闻的奖励识别仍用公共 `I_UI_REWARD`。
- **工作区**：改 `tasks/DailyTrifles/script_task.py` / `config.py` / `assets.py` / `dt/image_courtyard_affairs.json`，新增 `dt/dt_is_complete.png` / `dt/dt_dailyffair_reward.png`、`tests/test_daily_trifles.py`；改 `config/template.json`、`tests/test_l2_c0_registry.py`、`tests/test_l1_stage3b_global_guard.py`、`docs/L2_CALLSITE_REGISTER.md`。HEAD 仍是 `8a82cb8f`。

### 4.120 每日琐事：定时领庭院体力寿司（`run_courtyard_sushi`）

2026-10-23。未提交（在工作区）。**Level A/B PASS；Level C 待验（用户实机跑）。** 规则见 `docs/DECISIONS.md` D031「补记（领庭院体力寿司）」。

- **起因**：用户要的「定时领体力」。用户用标注器在 `tasks/DailyTrifles/dt/image_courtyard_affairs.json` 加了 `courtyard_sushi`（`dt_courtyard_sushi.png`，前框 1000,433,24,24，搜索区 781,331,343,231，阈值 0.8），并确认寿司 12 点、20 点出现、2 小时后消失，点了弹「获得奖励」。
- **做法**：开关 `courtyard_sushi`（默认关）；12:00–14:00 为 `noon`、20:00–22:00 为 `evening`，各记 `courtyard_sushi_noon_dt` / `courtyard_sushi_evening_dt`（不复用商店买体力的 `sushi_dt`）；`run()` 最先做：庭院主页最多等 5 秒认出寿司，`ui_get_reward(I_COURTYARD_SUSHI)` 只在认出时点它、用公共关闭区域关「获得奖励」（体力单个道具居中，商店签到已验证这个关闭区域）；**寿司消失才记这个时段完成**；`plan_next_dt` 在时段内且该时段没领到时排「现在 + 10 分钟」（不超过时段结束），**用 `server=False`**，否则照原来 12:00 / 20:00 / 次日 12:00。
- **配置**：`DailyTriflesConfig.courtyard_sushi`（界面「领庭院体力寿司」，`zh-CN.json` 加两个键）；`DoneRecord` 加两个时段字段；`config/template.json` 同步三处；`assets.py` 重新生成（只多 `I_COURTYARD_SUSHI`，标注器保存时已自动生成过一次）。
- **离线核对**：4 张 10-16 上午（不在时段内）的庭院现场截图在搜索区里的最高相似度 0.54–0.55，远低于 0.8；没有带寿司的整屏截图，「认得出」要真机看。
- **L2 登记册**：新增 1 处 `ui_get_reward`，`--write` 重新生成，1103 → 1104、EXCLUDED 141 → 142、rule 904 → 905，`tests/test_l2_c0_registry.py` 钉住值同步。
- **测试**：`tests/test_daily_trifles.py` 新增 9 项——时段边界（11:59 / 12:00 / 13:59 / 14:00 / 19:59 / 20:00 / 21:59 / 22:00）、领到且寿司消失才记、寿司不出现有界不记、领完还在不记、时段已做跳过、`run()` 只在开关开着且时段内才领、`_sushi_retry_at` 各分支、`plan_next_dt` 重试用 `server=False` / 没有重试走原来的固定时间。变异 4 条（领完还在也记 / 去掉重试 / 重试 `server=True` / 时段边界含 14:00）各有测试变红，已还原。全量 `2546 → 2555`。
- **顺带修了一个依赖当前时间的旧测试**：`tests/test_kekkai_utilize_convergence.py::test_case10` 没有冻结时钟，测试配置的结界寄养静默窗口是 0–7 点，在这个时段跑全量时 `run()` 入口守卫直接 `TaskEnd`，拿不到期望的 `GameStuckError`（2026-10-23 00:20 的全量因此 1 个错误，之前白天跑都通过）。两处 `t.run()` 套上 `_patch_now(NOW)`（与同文件其它用例一样固定 14:00），断言不变；00:24 在窗口内复跑通过。只改测试，不动业务代码。
- **未做 / 限制**：没上真机；开关默认关，要用户打开；如果其它任务常在 12–14 / 20–22 点长时间占着调度，可能整个时段都轮不到，可调高每日琐事优先级。
- **工作区**：改 `tasks/DailyTrifles/script_task.py` / `config.py` / `assets.py` / `dt/image_courtyard_affairs.json`（用户加的条目），新增 `dt/dt_courtyard_sushi.png`（用户截的图）；改 `config/template.json`、`assets/i18n/zh-CN.json`、`tests/test_daily_trifles.py`、`tests/test_l2_c0_registry.py`、`tests/test_kekkai_utilize_convergence.py`，重新生成 `docs/L2_CALLSITE_REGISTER.md`。HEAD 仍是 `8a82cb8f`。

### 4.121 每日琐事买体力：补回被合并冲掉的修复 + 读错价格不再多买（`run_buy_sushi`）

2026-10-23。未提交（在工作区）。**Level A/B PASS；Level C 待验（用户实机跑）。** 见 `docs/DECISIONS.md` D031「补记（买体力）」。

- **起因**：用户记得买体力有 bug（不记得具体现象，要求按查到的问题修）。根源：8 月 13 日 `658f5a7d`（magicemptycity，PR #245）「优化购买寿司逻辑，调整价格检测区域」修过买体力；8 月 18 日的合并 `73bcafcb`「同步 Azur mine 领先提交」保留了第一父提交 `de3f64e0` 的 `tasks/DailyTrifles/script_task.py`，把另一侧 `371b4ec9` 的修复丢了，之后一直没补回（`git log --full-history -m -S` 可查）。
- **修法**：① 移植被冲掉的修复：价格框改成右侧 75×45；进 Special 要等到体力商品也出现（列表已加载）；勾玉购买改用 `ui_get_reward(I_STORE_COST_TYPE_JADE, click_interval=2.5)`，买完弹出的「获得奖励」会被关掉（旧写法 `ui_click_until_disappear` 不处理奖励，列表被盖住后循环空转）；资产沿用现在的 `WeeklyPurchaseAssets`，不退回已重构掉的 `RichManAssets`。② 读错价格不再多买：读价格拆成 `_read_sushi_bought`，读不出数字或价格不是 60 + 20k 就返回无效、停止购买、不记完成（以前低于 60 当作「还没买」，80 读成 8 会多买，连续读错会一直买）；本次运行最多买「设定次数 − 开始时已买次数」次，买够就不再点购买；最后一次读数确认达到设定次数才写 `sushi_dt`。③ 进杂货页之前先 `goto_page(page_mall)`：签到会停在礼包屋子页。④ 点商品等购买框改成 `ui_click_until_appear_or_timeout(..., timeout=SUSHI_DIALOG_WAIT=10)`（原来是公共方法里无上限的 `ui_click`）。
- **测试**：`tests/test_daily_trifles.py` 新增 7 项（假商城：价格 = 60 + 20 × 已买次数，点勾玉弹「获得奖励」盖住列表）——正好买到目标并记完成、先去商城主页再点杂货、已买够不买、价格读成 8 不买不记、价格一直读成 60 最多买「目标 − 0」次后停下不记、购买框不出现有界不记、`_read_sushi_bought` 各种读数与价格框位置；旧的「进杂货页后认不出商品」用例改成「Special 里没有体力商品」。测试里购买循环上限默认调到 6 秒（每买一次 `ui_get_reward` 会 sleep 0.5 秒）。变异 4 条（退回 `ui_click_until_disappear` / 低于 60 当作 0 次 / 去掉本次购买上限 / 不回商城主页）各有测试变红，已还原。点击调用点数不变（1104），但登记行的方法名变了，`--write` 重新生成。全量 `2555 → 2562`。
- **未做 / 限制**：没上真机；签到后停在礼包屋子页那一条是推测（`goto_page(page_mall)` 本来就在主页时直接返回，无副作用）；购买框读数不对时直接停下，购买框留着，交给后面的 `goto_page(page_main)` 处理；同一次合并丢掉的寮祈愿修复没补（用户决定），见 ROADMAP。
- **工作区**：改 `tasks/DailyTrifles/script_task.py`、`tests/test_daily_trifles.py`，重新生成 `docs/L2_CALLSITE_REGISTER.md`。HEAD 仍是 `8a82cb8f`。

### 4.122 狩猎战（麒麟 / 阴界之门）：完整打完，修稳健性（`tasks/Hunt/script_task.py`）

2026-10-23。未提交（在工作区）。**Level A/B PASS；Level C 待验（两个号的 Hunt 都还没开过）。**

- **起因**：用户要定制阴界之门和麒麟。全量查过后（`tasks/Hunt/` 是主体；觉醒副本 EvoZone 里的「麒麟」、逢魔数据里的麒麟与此无关；`GuildActivityMonitor` 不监控狩猎战 / 阴界之门；synevo 只有阴界开始时间 17→18 的 1 行差异，另有账号轮换专用的 `tasks/DailyTrifles/hunt_adapter.py` 短时参战），用户选择**保留完整打完的打法，只修稳健性**，并确认开放时间。
- **修法**：① 开放时间（用户 2026-10-23 确认，与 synevo 一致）：麒麟周一至周四 06:00–23:00、阴界之门周五至周日 18:00–23:00（原代码阴界 17:00 开始，注释又写「麒麟 19–21、阴界 19–23」，三者不一致），拆成 `_hunt_mode` / `_window` / `_planned_time`；② 计划时间 = 配置时间，不在开放时间内就用开放时间——以前配置早于开放（比如阴界 17:30）时提前醒来会把下次运行排到「今天已经过去的时间」，调度器立刻又跑，一直空转到开放；③ `kirin()` / `netherworld()` 进入战斗前的点击循环各加 60 秒上限，「已挑战」后的返回改成有界的 `_back()`（10 秒）；两个函数返回 `battle` / `done` / `timeout`；④ 没进去（超时，或阴界 `click_fire` 不是 `battle`）在当天开放时间内 10 分钟后重试，否则排到下一天；打完或已挑战排到下一天（按下一天自己的模式）；⑤ 排程统一 `set_next_run(task="Hunt", target=..., server=False)`（原来 `custom_next_run` 会走服务器刷新时间那个分支，同 D030 的教训）；⑥ 换御魂只在当天模式配了预设时才去式神录；删掉走不到的 `if not check_datetime()` 分支；⑦ 麒麟分两套式神录预设（用户同日追加）：现有「麒麟御魂切换」`kirin_group_team` 作为通用，新增「雷麒麟御魂切换」`thunder_kirin_group_team`（默认 -1,-1，`config/template.json` 同步）；雷麒麟固定在周四（用户确认，`THUNDER_KIRIN_WEEKDAY = 3`），周四填了雷麒麟预设就用它、没填回退到通用，其它麒麟日用通用，阴界之门只看自己的预设（`_soul_preset`）。战斗本身（`run_general_battle`、两套战斗配置、`exit_matcher`、`click_fire == "battle"` 守卫）不动。
- **界面文字**：任务名和各字段的中文名早就在主翻译文件 `module/config/i18n/zh-CN.json` 里（`assets/i18n/zh-CN.json` 只是追加文件，之前只查了它，误以为没有）；本轮只给 `kirin_time` / `netherworld_time` 加了说明（`description` 指向新增的 `kirin_time_help` / `netherworld_time_help`，写在追加文件里），写明开放时间和「早于开放按开放时间算、进不去 10 分钟再试」；新字段 `thunder_kirin_group_team` 的名字「雷麒麟御魂切换」和说明也写在追加文件里。
- **L2 登记册**：两处 `ui_click_until_disappear`（R7）合并成 `_back()` 里 1 处 `appear_then_click`（函数名带 back，R4 KEEP_SPECIAL，时序仍是立即点击），总数 1104 → 1103、KEEP_IMMEDIATE 633 → 631、KEEP_SPECIAL 235 → 236、rule 905 → 904；`tests/test_l2_c0_registry.py` 钉住值同步，`--write` 重新生成。
- **测试**：新增 `tests/test_hunt.py` 20 项（复用 `tests/test_daily_trifles.py` 的 `FakeUi`，时间用替身固定）——模式按星期、计划时间夹到开放时间、提前醒来不排到过去的时间、阴界 17:59 不打 18:00 打、周四 / 周日 23:30 排到下一天的模式、换御魂只换当天模式；麒麟正常开打 / 已挑战排明天 / 进不去有界并 10 分钟重试 / 22:55 进不去不再重试；阴界之门房间开打 / `click_fire` 不是 battle 不打并重试 / 已挑战排明天 / 进不去有界 / 房间里没有挑战键有界；两套预设：周四用雷麒麟、周四没填回退通用、周一至周三用通用、阴界只看自己的、周四先换预设再进麒麟页、都没填不去式神录。`tests/test_general_invite_challenge_reaction.py` 对 Hunt 源码的 `battle_entered` 守卫断言仍满足。变异 7 条（阴界 17 点开 / 不夹到开放时间 / 去掉麒麟进入上限 / 排程 `server=True` / 去掉阴界进入上限 / 雷麒麟写成周三 / 周四没填不回退通用）各有测试变红，已还原。全量 `2562 → 2582`。
- **未做 / 限制**：没上真机；短时参战、两个号配合不做（用户没选）；未引用的 `I_HUNT_SHRINE` / `I_HUNT_HUNT` / `I_KIRIN_GATHER` / `C_HUNT_ENTER` 不动；60 秒进入上限是工程默认值，要真机确认够不够。
- **工作区**：改 `tasks/Hunt/script_task.py` / `config.py`、`config/template.json`、`assets/i18n/zh-CN.json`、`tests/test_l2_c0_registry.py`，新增 `tests/test_hunt.py`，重新生成 `docs/L2_CALLSITE_REGISTER.md`。HEAD 仍是 `8a82cb8f`。

### 4.123 集体任务：只做指定的任务，不限次数刷新直到出现（`tasks/CollectiveMissions/script_task.py`）

2026-10-23。未提交（在工作区）。**Level A/B PASS；Level C 待验（用户实机跑）。**

- **起因**：用户反馈集体任务以前会捐到不是指定的材料。根因：`select_and_update_cur_mission()` 只看第一个任务槽（「远远不够」），读任务名、不是目标就点「换一个」，最多换 12–15 次，连续 2–3 次读到同一个任务名就判定换不动；两种情况都返回 False，但 `run()` 不看返回值，而 `current_mission` 已被设成最后读到的那个任务，于是照它去捐——这就是「捐到非指定的材料」。两个号都开着集体任务，目标都是「御灵一」；最近日志里没有运行记录。
- **修法**：改成 `_select_target_mission(target) -> bool`：**不设次数上限**，一直点「换一个」直到出现指定任务（用户确认刷新免费不限次），每次照旧 `click_record_clear()`；连续 4 次读到同一个任务名才算换不动（`SWITCH_STUCK = 4`，刷新是随机的，连着两三次相同很正常）；另有 300 秒时间保护（`SELECT_TIMEOUT`，约 200 次，只防目标根本不在池子里时死循环）；只有选中时才设 `current_mission`。`run()` 选不到时**什么都不捐**，回庭院，`set_next_run(target=现在 + 1 小时, server=False)`（用户选「过一会儿再试」）；「今天已捐满」「先领已完成的奖励」与捐材料在 4 种里挑数量最多的规则都不动（用户确认「固定」指任务类型）。`missions_select` 的说明补上这条规则。
- **L2 登记册**：调用点数不变（1103），选任务那一行的函数名变了，`--write` 重新生成。
- **测试**：新增 `tests/test_collective_missions.py` 8 项（复用 `FakeUi`，任务名替身每点一次「换一个」前进一格）——第 20 次才出现仍选中（原来 15 次放弃）、连着 3 次同一个任务不算换不动、换不动不捐并 1 小时后重试（`server=False`）、一直换不到被时间保护结束且不捐（回归原 bug）、「换一个」认不出按换不动处理、认不出的任务名继续换、御魂 / 养成 / 觉醒各走自己的流程、今天已捐满不碰任务。变异 4 条（恢复 15 次上限 / 照最后读到的任务去做 / 换不动阈值 2 / 重试 `server=True`）各有测试变红，已还原。全量 `2582 → 2590`。
- **未做 / 限制**：没上真机；只看第一个任务槽（与原来一致）；「换不动」若是因为当天已做过别的任务而锁住，会每小时回来看一次直到第二天。
- **工作区**：改 `tasks/CollectiveMissions/script_task.py` / `config.py`，新增 `tests/test_collective_missions.py`，重新生成 `docs/L2_CALLSITE_REGISTER.md`。HEAD 仍是 `8a82cb8f`。

### 4.124 庭院事务满级弹窗点取消；每日琐事 / 狩猎战 / 集体任务所有点击接入通用延迟点击模型（L2）

2026-10-23。未提交（在工作区）。**Level A/B PASS；Level C 待验（用户实机跑）。**

- **起因**：实测两个问题。① 庭院事务卡住：点「一键完成」后，结界里放的式神满级时会弹「您在结界中放置的式神已满级，请确认是否提取？（取消 / 确认）」；原流程只认奖励页，6 秒没等到就记完成，回庭院时导航兜底乱点了 26 秒（10-23 09:18 两个号都是）。用户截图上 `I_UI_CANCEL_SAMLL` 0.994、`I_UI_CONFIRM_SAMLL` 0.992，弹窗后面的 `I_ONE_COMPLETE`（0.999）与 `I_CHECK_COURTYARD_AFFAIRS`（0.983）照样认得出来。② 点击太快：每日琐事在 L2 登记册里整体是项目排除项（「synevo 小号轮换业务，不做 L2 迁移」），狩猎战 / 集体任务也全是立即点击；用户要求「任何关于点击的地方都要接入点击模型」，范围选「这几轮改过的任务」。
- **公共方法**：`tasks/base_task.py` 的 `click` / `ui_click` / `ui_click_until_disappear` / `ui_click_until_appear_or_timeout` / `ui_reward_appear_click` 加可选 `policy`，`ui_get_reward` 加 `policy`（点目标）与 `close_policy`（关「获得奖励」）；不传时调用形状与原来完全一样（模块级 `_policy_kw` 不往下传 `policy` 这个参数，子类 / 测试替身的旧签名照常可用）。`click(policy)` 点的是固定区域，没有能在新截图里再确认的目标，所以只在点击前加反应时间（`random_delay(*resolve_reaction_range(policy))` → `sleep`）；其余方法透传给 `appear_then_click`，走原有「反应 → 新截图 → 再确认 → 点」。反应延迟仍只在 BaseTask 这一层，不下沉到 click_pipeline / Control / minitouch；`policy` 与 `confirm_delay` 仍不能叠加。
- **逐点配档**（三个任务共 59 处 + 新增 1 处）：NORMAL = 功能按钮（祝福、领取、购买商品、挑战、一键完成、换一个、提交、邮件图标）；CONFIRM = 确认 / 取消框（`I_UI_CONFIRM`、召唤确认、搜索确定、勾玉购买、满级弹窗取消）；NAVIGATION = 返回、关闭、关奖励（`I_UI_BACK_*`、羁绊弹窗、吉闻点下方空白、庭院关奖励页、`close_policy`）；FAST = 标签 / 底栏切换、反复点的加号（日常标签、寮友 / 好友、按昵称搜索、杂货、礼包屋推荐、清空搜索、集体任务的加号与 N 卡）。今忆召唤预设那一处直接调 `execute_single_click`，提成 `_click_recall_preset`，在里面先加 NORMAL 反应时间再点（单独成方法：同一函数里先有本地 `random_delay`、后有带 policy 的点击，会被 `tests/test_l2_policy_migration.py` 的守卫当成叠加反应）。狩猎战：返回 NAVIGATION、确认 CONFIRM、挑战 / 阴界之门入口 NORMAL（开战的 `click_fire` 原本就有 FIRE 反应）。集体任务：换一个 / 进任务 / 提交 / 长按 NORMAL、返回与关奖励 NAVIGATION、加号与 N 卡 FAST。
- **满级弹窗**：新增 `_cancel_two_button_popup()`：同一帧里「取消」「确认」两个小按钮**都在**才点「取消」（CONFIRM 档；用户决定不提取，从不替用户点确认，单独一个取消按钮不算）；每轮点一键完成**之前**先调（弹窗开着时按钮照样认得出来），`close_reward_and_wait_page` 的等待循环里也**先**调，点了取消就重新计时、继续等奖励页。
- **登记册**：`dev_tools/click_callsite_register.py` 的 `EXCLUDED_MODULES` 去掉 DailyTrifles，`--write` 重新生成：总数 1103 → 1104（弹窗取消 +1）、ALREADY_L2 39 → 98、KEEP_IMMEDIATE 631 → 619、KEEP_SPECIAL 236 → 232、EXCLUDED 142 → 100、`policy=` 点位 38 → 97。今忆召唤的 `_click_recall_preset` 里的 `execute_single_click` 静态规则看不到手动加的反应时间，仍按 R10 归 KEEP_IMMEDIATE，由新静态守卫兜住。`tests/test_l1_l2_integration.py::POST_C1_CONSUMERS` 逐点登记 58 条（同一函数里目标与档位都相同的合成一条）。
- **测试**：新增 `tests/test_l2_helper_policy.py` 14 项（`click` 不传 / IMMEDIATE 不等、传了先反应再点、长按也等、interval 没到既不等也不点、FSM 档位被拒；各 helper 把档位透传到 `appear_then_click` / `click`，`ui_get_reward` 分别用 `policy` 与 `close_policy`；不传时不往下传 `policy`；静态守卫：三个任务文件里每个点击调用都带 `policy=InteractionPolicy.*`，`ui_get_reward` 还带 `close_policy`，`execute_single_click` 紧挨的上一句是反应时间）；`tests/test_daily_trifles.py` 庭院事务新增 4 项（满级弹窗点取消不点确认、之后领到奖励并完成；弹窗开着时第一下点的是取消；单独一个取消按钮不当弹窗；各点击的档位），`FakeUi` 记录每次点击的档位。改既有测试：`test_l1_stage3b_global_guard` 今忆召唤的替身补 `_click_recall_preset`、把反应时间换成确定值（不消耗种子随机数），sleep 钉住值 18 → 27 并断言每次点击前紧挨一次 NORMAL 反应；`test_l2_c0_registry` / `test_l1_l2_integration` 钉住值；`test_l2_interaction_reaction` case35 加三个文件（每日琐事 42 / 狩猎战 6 / 集体任务 11）。变异 7 条（去掉一处 policy / `click()` 不加反应 / 弹窗点确认 / 一键完成前不先关弹窗 / 只认取消按钮 / 关奖励页等待里不处理弹窗 / 不传 policy 时也往下传）各有测试变红，已还原。全量 `2590 → 2608`。
- **预期变化 / 限制**：三个任务整体变慢（每次点击多 0.18–1.2 秒），属预期；共享组件里的点击（每日普通召唤的 `Summon`、导航 `goto_page`、战斗、组队房间）和滑动不在本轮范围，仍是原样；`ui_get_reward` / `ui_click` 的 RuleOcr 分支不支持 policy（这三个任务没用到）；满级弹窗只在庭院事务里处理，取消后若游戏不出奖励页，6 秒后照原规则记完成。没上真机。
- **工作区**：改 `tasks/base_task.py`、`tasks/DailyTrifles/script_task.py`、`tasks/Hunt/script_task.py`、`tasks/CollectiveMissions/script_task.py`、`dev_tools/click_callsite_register.py`，新增 `tests/test_l2_helper_policy.py`，改 `tests/test_daily_trifles.py` / `test_l1_stage3b_global_guard.py` / `test_l2_c0_registry.py` / `test_l1_l2_integration.py` / `test_l2_interaction_reaction.py`，重新生成 `docs/L2_CALLSITE_REGISTER.md`。HEAD 仍是 `8a82cb8f`。

### 4.125 组队会合改成「到点就进门等，把对方拉进同一任务」（D030 修订，`module/instance_sync/team.py`）

2026-10-23。未提交（在工作区）。**Level A/B PASS；Level C 待验（用户实机跑）。**

- **起因**：用户反馈两个实例都空闲时，组队任务不会合，而是各自直接进入下一次调度。10-23 09:23–09:30 两个号的 Orochi 每次到点都在拉起游戏之前判 `peer_not_due`（对方这个任务还没到点），把自己推到对方在场文件里的 `next_run`（两边都是 13:39:57）；用户手动把一边改成「现在运行」时，它读到的对方时间仍是 13:39:57，又被推回去，09:30:43 两边几乎同时改也一样（先判的一边读到的是对方还没更新的文件）。根因是 `decide()` 按对方的**计划时间**推迟自己（`peer_not_due` / `peer_idle`）：两边被推到同一个较晚时间后，任何一边提前都会被拉回去，对方也不会因此提前。
- **用户要的**：组队任务到点后进入明确的「等待对方」状态，自己在门口等，直到对方进入同一任务再一起开始。用户 2026-10-23 决定：被拉的任务按对方原来的调度顺序排（不插队）；对方确定不会来时照旧推迟并提醒；对方在休息时推迟到休息结束；等待不设上限、超过 30 分钟推送一次。
- **修法**：① **到点就进门等**：`decide()` 删掉 `peer_not_due` / `peer_idle` 两条推迟，对方在跑别的任务是 `peer_busy`、空闲是 `pull_peer`，都继续等；② **把对方拉进同一任务**：`TeamSync.peer_request()`（只读）在对方在线、配对正确、状态 `waiting`、它等的任务在我这边是开启的组队任务且身份互补、在我这边还没到点、这次等待的 token 没回应过时返回任务名；`TeamSync.answer()` 再调 `config.task_call(task, force_call=False)` 把它改成现在运行（按原来的调度顺序排，不插队），并记下 token；`Script.get_next_task` 每轮 `get_next()` 之前调 `answer`，`Script.wait_until` 每 5 秒在检查配置之后调 `peer_request`，有请求就返回 False 打断所有空闲等待策略（同一 token 只打断一次）；③ **对方在休息**：`get_next_task` 把 `antiban_wake`（休息时间窗 / 长休息）作为 `rest_until` 写进在场文件（可选字段，旧文件没有当作 None），对方不在门口且 `rest_until` 晚于现在 + 1 分钟时判 `peer_resting`，推迟到那时；④ **两个门口**：不再看对方等的任务在我这边到没到点，一律后到的让（`since` 晚的，同时到按实例名），推迟 3 分钟，回到调度器后被对方拉进它等的任务；⑤ **等太久**：`rendezvous(notify=)` 同一次等待满 30 分钟（`WAIT_NOTIFY`）推送一次，之后照常每 5 分钟记日志、继续等，推送失败不影响等待；⑥ 不变：对方不在线 / 没配对 / 没开 / 身份不互补照旧推迟并每天提醒一次；配置改动中断等待；同心之兰让路；异常放行；推迟一律 `server=False`。
- **等待状态的可见性**：GUI「运行中」本来就显示这个任务（`get_schedule_data` 把已到点的当前任务列为 running）；日志 `Team sync: wait for <对方> before <任务>`、`waiting ... (pull_peer / peer_busy, Ns)`；被拉的一方日志 `Team sync: peer is waiting at <任务>, stop idle wait` 和 `Team sync: <对方> is waiting at <任务>, call it now`；在场文件 `state: waiting`。
- **测试**：`tests/test_team_sync.py` 38 → 52 项。改 3 项既有用例（`peer_not_due` 改成等待；空闲的对方改成 `pull_peer`；两个门口不看到没到点、后到的让），通知测试里的「正常对齐不提醒」换成 `peer_resting`；新增：对方在休息推迟到休息结束（旧文件没有该字段照常等）、在场文件读写 `rest_until`、等满 30 分钟恰好推一次且继续等、推送失败不影响等待、`peer_request` / `answer` 只回应一次同一 token（对方重新进门再回应）、不是给我的请求（任务关了 / 身份相同 / 我这边已到点 / 对方不在门口 / 单人 / 同步关）一律忽略、对方不在线或没配对忽略、异常返回 None、`on_schedule` 写 `rest_until`、`precheck` 对空闲的对方不再推迟而对休息中的推迟、**复现 10-23 日志**（两个真实 `TeamSync` 共用临时目录：A 到点进门，B 的 Orochi 在 4 小时后、空闲，B 读到请求后被拉到现在，两边都开始）、`Script.wait_until` 被对方请求打断 / 没有请求照常等完、真实 `Script.loop` 里空闲的一方被拉进对方等的任务（不进空闲等待）。变异 8 条（恢复 `peer_not_due` 推迟 / 不按 token 去重 / 空闲等待不看请求 / 两个门口都不让 / 忽略 `rest_until` / 推送不止一次 / 调度器不回应 / 空闲的对方照旧推迟）各有测试变红，已还原；其中「空闲等待不看请求」最初表现为挂住，给 `sleep` 替身加了 50 次硬上限。全量 `2608 → 2622`。
- **取舍 / 限制**：对方在跑别的任务时，要等它跑完回到调度器才会被拉过来，这期间本实例其它任务都被挡住（用户要的「自行等待」）；被拉的任务不插队，对方还有几个待执行任务时要多等这几个任务的时间；对方的空闲等待最多 5 秒才发现请求；没上真机。
- **工作区**：改 `module/instance_sync/team.py`、`module/script/team_sync.py`、`script.py`、`tests/test_team_sync.py`。HEAD 仍是 `8a82cb8f`。

### 4.126 组队会合补强：重启不误推迟 + 御魂次数以队长为准（D030 修订二）

2026-10-23。未提交（在工作区）。**Level A/B PASS；Level C 待验（用户实机跑）。**

- **起因**：§4.125 实测（10-23 10:40）两个实例一起重启，先起来的 oas1 读到 oas2 旧进程留下的在场文件（10:38:09 最后一次写，已超过 60 秒），判 `peer_offline`：Orochi 推迟 10 分钟并推送「对方实例 oas2 不在线」，用户看到的「报错」就是这条推送；oas2 晚 2 秒起来后正常进门等。用户同时说明预想的流程：对方在跑别的任务时进门等、**不推迟**，对方开始同一任务后两边才一起操作；不光同步时间，还要同步次数，不能出现一边记 100 次、一边记 99 次。
- **次数为什么会差**：御魂每进一次 `run_general_battle` 就 `current_count += 1`，队长和队员各自判 `current_count >= limit_count` 退出。队长点了挑战却没真正开战也会多数一次，两边就差一次：队长先数满走人，队员在房间空等邀请到超时；或队员先走，队长邀请失败、任务判失败。
- **用户决定**：次数以队长为准（队员不按自己的计数退出，队长打完才退，并把自己的次数对齐到队长的）；先只做御魂，机制做成通用的；对方文件刚过期就进门等、过期很久才推迟并提醒；被拉的任务照旧按原顺序排（不插队，不改）。
- **改动一：刚过期的对方进门等**：`decide()` 把「不在线」拆成两档。文件不存在 / 没有时间 / 超过 `OFFLINE_GRACE`（5 分钟）没更新：照旧 `POSTPONE peer_offline`（推迟 10 分钟，每天推送一次）；超过 `STALE`（60 秒）但不到 5 分钟：`WAIT peer_reconnecting`，不推送、不推迟。这个判断在「同一门口 → 开始」之前，所以旧文件里即使写着 `waiting` 同一任务，或「已带着我开始」，也不会被当成会合，只等它重新写。`precheck()` 不用改（判等待时返回 None，照常准备游戏再进门）。对方一直没回来时，它的文件过期满 5 分钟那一轮判 `peer_offline`，推迟并提醒，最多多等约 4 分钟。
- **改动二：任务中途的组队进度（通用机制）**：在场文件加可选字段 `progress = {count, done}`（`parse_presence` 读，格式不对按 None，版本号不变；`publish()` 换状态时不带，上一次的进度不留给下一次；`PresenceBoard.report_progress()` 在 `_mutex` 里改后写盘，心跳带着它刷新）。`TeamSession`（`team.py`）：`report(count, done)` 给队长写、`peer_progress() -> Progress(count, finished)` 给队员读；对方文件里 `state == running`、`task` 相同、`token` 是会合时记下的对方 token、`partner_token` 是我的 token 才算「还在这一次组队里」；`waiting`（对方比我晚一轮才写 running）算没结束；换了任务 / 状态 / token、掉线（超过 60 秒没更新）、文件不存在都算结束，并返回最后一次读到的次数；`UNREADABLE` 或出错算没结束（任务原有的超时兜底）。按实例名登记在模块级字典里（和 `module.fatigue` 的 manager 同一个做法）：`set_session` / `get_session(identity, task)`（任务名不符返回 None）/ `clear_session`。`TeamSync.gate()` 开头清旧会话，会合成功（`met` / `peer_started_with_me`）后从 `board.snapshot()` 取双方 token 登记；`TeamSync.end_task()` 清会话，`script.py` 用 `try/finally` 在 `self.run()` 之后调。
- **改动三：御魂接入**（`tasks/Orochi/script_task.py`）：`run()` 开头 `self.team_session = get_session(config.config_name, 'Orochi')`，没有会话（没开同步 / 单人 / 野队 / 出错）时全部走原逻辑。**队长**每场 `run_general_battle` 之后 `report(current_count)`，主循环退出后（次数到 / 时间到 / 邀请失败 / 房间失效四种 `break` 都经过这里）先 `report(current_count, done=True)` 再退房间。**队员**主循环里原来的 `current_count >= limit_count` 改成 `_member_count_reached()`：有会话时看 `peer_progress().finished`，队长打完或离开才退，退出时 `current_count` 对齐到队长的次数并记日志 `Team sync: leader finished Orochi at N, member counted M`；读文件节流 2 秒（`OROCHI_TEAM_POLL_INTERVAL`）。时间上限和 `wait_battle` 超时退出原样保留当兜底。
- **测试**：`tests/test_team_sync.py` 52 → 67 项（改 1 项：61 秒不再算不在线，换成 6 分钟）；新增：刚过期（61 / 150 / 299 秒）等待而 301 秒推迟、旧文件里写着在同一门口等 / 已带我开始也只等、`progress` 往返 / 心跳后保留 / 换状态清掉 / 格式坏按 None、`TeamSession`（队员跟着队长到 done、队长离开保留最后次数、换任务 / token / 搭档算离开、交接中不算结束、过期或没文件算结束、`UNREADABLE` 与异常不抛）、登记表按实例按任务、**复现 10:40 重启**（oas1 先进门，oas2 的旧文件 2.5 分钟前、写着在同一门口等；oas2 新进程起来后会合，没有推送）、对方一直不回来过 5 分钟才推迟、`precheck` 对刚过期不推迟对 6 分钟推迟、两个真实 `TeamSync` 会合后双方会话 token 互相对上并能读到队长上报的次数、`end_task` 只清自己、没开同步 / 非组队任务 / 异常 / 推迟都不留旧会话、真实 `Script.loop` 里任务运行时取得到会话且异常穿出后被清掉。新增 `tests/test_orochi_team_progress.py` 18 项：队员有会话时自己数到 100 队长没完也继续等、队长 done 才退并对齐次数（含队员落后的情况）、队长离开无次数、时间上限仍是兜底、读文件节流、没有会话时仍按自己的计数退出；队长每场上报且退出前先上报 done 再退房间（次数到 / 邀请失败 / 时间到）、没有会话时和以前一样；`run()` 取到本实例御魂的会话、不取别的任务的；结构守卫。变异 11 条（去掉 5 分钟分档 / 刚过期旧文件当真 / 队员仍按自己计数 / 队长退出前不报 done / `peer_progress` 不核对 token 或 partner_token / `end_task` 不清 / `script.py` 不调 `end_task` / 队长每场不报 / `gate` 开头不清旧会话 / 队员不对齐次数）各有测试变红，已还原；其中「`script.py` 不调 `end_task`」最初没被抓到，补了真实 `Script.loop` 里的断言。
- **取舍 / 限制**：只做了御魂，其它组队任务（探索 / 永生之海 / 日轮之陨 / EvoZone / 异界黄昏 / 契灵）的计数逻辑不动；队长若在旧版本上不上报，队员靠时间上限和邀请超时兜底；队员最多隔 2 秒才发现队长打完；任务结束后两边各自算下次时间，互不联动；没上真机。
- **工作区**：改 `module/instance_sync/team.py`、`module/script/team_sync.py`、`script.py`、`tasks/Orochi/script_task.py`、`tests/test_team_sync.py`，新增 `tests/test_orochi_team_progress.py`。HEAD 仍是 `8a82cb8f`。

### 4.127 组队会合启动宽限：两边一起启动 / 重启时先进门等，不再「先推迟、几秒后又被拉回」（D030 修订三）

2026-10-23。未提交（在工作区）。**Level A/B PASS；Level C 待验（用户实机跑）。**

- **起因**：用户在 OASX 里看到 oas1 的八岐大蛇显示「11:35:08」（被推迟了 10 分钟）。日志里这样「先推迟、几秒后又被拉回」发生了两次：① 11:23:54 两边停了 43 分钟后一起启动，oas1 早 0.7 秒，读到 oas2 43 分钟前的旧文件（已超过 §4.126 的 5 分钟宽限），判 `peer_offline`，推迟 10 分钟并推送「对方不在线」；oas2 晚 0.7 秒进门等，8 秒后 oas1 被拉回、`met`，两边正常打；② 11:25:08 两边又一起重启，oas1 读到 oas2 旧进程还没过期的文件（还写着在跑 Orochi、搭档是 oas1 旧进程的 token），判 `peer_running_alone`，推迟 10 分钟（这次没推送），7 秒后又被拉回。手机上 11:26:28 的那条推送在日志里找不到对应的推送调用，最近的是 11:23:54 那条，疑似推送服务延迟（未核实）。两次同步本身都没失败，问题只是不必要的推迟和推送。
- **用户的预期 / 决定**：对方还没进同一任务时在门口等，不要推迟组队任务；启动宽限取 3 分钟。
- **修法**：① 新增 `STARTUP_GRACE`（3 分钟）。`decide()` 的 `me` 加可选 `started_at`（本进程启动时刻）；对方「不在线」那一档（文件不存在 / 没有时间 / 超过 `OFFLINE_GRACE`）里，`now - started_at < STARTUP_GRACE` 判 `WAIT peer_starting`（不推迟、不推送），否则照旧 `POSTPONE peer_offline`。`rendezvous(started_at=)` 和 `TeamSync(started_at=)`（`precheck` / `gate` 都带）往下传；`script.py` 的 `team_sync` 用 `datetime.now()` 创建（每个配置一个进程，`loop()` 开头就访问，等于脚本启动时刻）。`started_at` 默认 None 表示没有启动宽限，其它调用方行为不变。② `peer_running_alone` 从 `POSTPONE`（10 分钟）改成 `WAIT`：对方文件没过期、配对的是我、在跑同一任务，但搭档 token 不是我的，说明是和我旧进程的那一次。之后要么对方也在重启（新进程进门，会合），要么对方确实还在旧的那一次里：队员读到我的新 token 判对方离开而退出（§4.126 `peer_progress`），队长邀请失败退出，回到空闲后看到我在门口等，把同一任务拉到现在。一直等不到仍有 `WAIT_NOTIFY`（30 分钟）推送兜底。过期判断仍在前面，所以过期的 running 文件走不到这一档。
- **测试**：`tests/test_team_sync.py` 67 → 76 项，`tests/test_orochi_team_progress.py` 18 项不变。改 1 项既有断言（`peer_running_alone` 由推迟改为等待）；`me()` 加 `started_at`；`ScriptLoopTest._script()` 默认把 `team_sync` 设成「已运行 10 分钟」（否则「对方不在」的用例会在门口真等 3 分钟），原断言不变。新增：启动 0 / 10 / 179 秒内对方不在或过期 43 分钟都 `peer_starting`、181 秒后推迟、没有 `started_at` 时照旧推迟、宽限只覆盖「不在线」那一档（只过期 2 分钟仍是 `peer_reconnecting`，没配对仍推迟）、**复现 11:23:54**（A 先启动，B 的文件 43 分钟前，B 晚起来进门，两边会合、没有推送）、宽限满 3 分钟后推迟、**复现 11:25:08**（B 的旧文件写着和 A 旧 token 在跑，A 进门等，B 新进程进门后会合）、对方确实还在旧会话里（`peer_running_alone` → `pull_peer` → `peer_started_with_me`）、`precheck` / `gate` 对新进程等、对 4 分钟前启动的推迟、真实 `Script.loop` 里刚启动的一边进门等（照常准备、没推迟、没推送、在场文件是 waiting）、`Script.team_sync` 带着进程启动时刻。变异 7 条（去掉启动宽限 / 宽限不看 `started_at` / `peer_running_alone` 改回推迟 / `script.py` 不传 / `rendezvous` 不带进 `me` / `gate` 不交给 `rendezvous` / `precheck` 不带）各有测试变红，已还原；其中「宽限不看 `started_at`」表现为门口死等，用 90 秒超时终止，也算被抓到。全量 `2655 → 2664`。
- **取舍 / 限制**：对方真没开时，「不在线」的推迟和推送最多晚约 3 分钟（脚本启动后 3 分钟内不推迟），期间游戏已拉起、在门口等；宽限只看本进程的启动时刻，脚本跑了很久之后对方才重启仍走 §4.126 的 5 分钟「刚过期就等」；`peer_running_alone` 不再推迟，对方一直卡在旧会话里不退出时本实例一直在门口等（30 分钟推送一次）；没上真机。
- **工作区**：改 `module/instance_sync/team.py`、`module/script/team_sync.py`、`script.py`、`tests/test_team_sync.py`。HEAD 仍是 `8a82cb8f`。

### 4.128 御魂 → 个人突破 轻量循环（D032，首版只接御魂）

2026-10-24。未提交（在工作区）。**Level A/B（离线 + 跨进程文件协调）PASS；Level C 未做（用户实机跑）。** 设计见 `docs/DECISIONS.md` D032。

- **功能**：在八岐大蛇设置里新增「御魂→个人突破循环」分组（`loop_config`：`start_loop` 一次性开关、`rounds` 轮数、`target_min` / `target_max` 每批场数范围）。两个实例都打开后：御魂一批（队长在范围内随机一次目标场数，队员用同一个数）→ 个人突破 → 御魂 … 共 `rounds` 轮，最后一轮个人突破双方都完成后结束，回到普通调度；之后普通御魂不会自动再起循环。个人突破沿用自己的配置和结束规则（无票 / 达到上限 / 战败退出 / 无目标 / 刷新失败，只要正常走到自己的结束出口就算这一步完成），普通排期开关关着也能作为循环步骤运行。
- **配对**：直接复用「脚本设置 → 组队同步」的 `enable` / `peer_instance`（oas1 填 oas2、oas2 填 oas1），不新增配对字段；`loop_id` 由程序生成（队长生成、队员采用），用户不填。第一轮由用户分别手动打开开关，先打开的一边无固定超时地等；两边打开后校验轮数 / 目标范围 / 身份（一个队长一个队员），不一致第一场之前就双方失败。
- **没有新建同步通道**：循环信息放在 D030 的在场文件里（`loop` 字段，上一次的终态摘要放 `prev`，另有 `pid` / `boot_id`），由 `PresenceBoard._write()` 在每次写盘（`publish` / 心跳 / `report_progress`）统一带上；会合、心跳、配对锁、原子写入都是现有的。不用 D029 账本（它是「一天一次、固定超时」的语义，和循环不合）。
- **步骤交接**（`Script.loop`）：`get_next_task` → `prepare_task_execution` → 步骤疲劳（`begin_task(restart=True)` → `try_break(safe=True)`，`Script.run` 不重复初始化）→ 循环会合 `barrier()`（双方都准备好才开始；先到的一边等）→ 御魂再进 D030 门口（带 `{id, step}`，只和同一次循环同一步骤的对方会合）→ `Script.run`。会合等待期间每 2 秒看一次是否有严格更高优先级的任务到点，有就让出。
- **普通御魂不会误入循环**：`decide()` 在所有提前返回 GO 的路径之前，对方正在循环且当前步骤就是这个任务时，不带循环信息的普通门口判 `peer_in_loop` 推迟 30 分钟；循环门口要求对方在同一 `id` 同一步骤，否则 `peer_loop_pending` 继续等。`TeamSync._peer_waiting` 不拉循环步骤。
- **终态保留**：循环结束不清除 `loop`，只改成 COMPLETED / FAILED / CANCELLED 并写 `final`；新循环开始才把旧终态移进 `prev`（最多一份）。对端晚读、或我方已开始新循环而对端还在收尾旧循环，都能按 `id` 在 `loop` / `prev` 里读到旧循环的终态，不会把完成误判成离开；对方文件过期也不抹掉已写下的终态。进程重启后内存清空，对端读不到完成记录时按失败，不做跨重启续跑。
- **失联 / 取消 / 失败**：绑定本次参与者之前（还没人加入）只等待，不算失联；绑定之后对方退出、重启（`boot_id` 变）、文件过期 60 秒、`loop` 消失都失败并传播同一个 `loop_id`。界面停止：`ScriptProcess.stop()` 先读自己的在场文件（`pid` 匹配、有未结束循环）→ 往现有 `command_queue` 放带 `boot_id` / `loop_id` / `pid` 的 `loop_cancel` → 脚本进程自己的命令线程把循环写成 CANCELLED 并发布 → 父进程只读确认（最多 3 秒，异步睡眠不阻塞事件循环）→ 照常 `terminate()`；超时也终止，对端按失联处理；残留的旧命令 `boot_id` 对不上被忽略。
- **队长可信计数**：`current_count` 不当作完成证据。每次邀请前 `attempt_begin()` 记「可能开战」；`run_invite` 失败且没点过挑战按钮（`GeneralInvite.fire_click_issued`，每次邀请前清零）可撤销，点过则无法确认→停止；进入战斗并且看到结算 / 奖励页（Orochi 的 `_handle_result` / `_handle_reward` 置 `_result_seen`）才计一场；其余无法确认→循环失败，不猜剩余次数。循环里只对本次调用用的配置拷贝关掉内部连战，不改用户配置。同进程内恢复保留目标和计数；恢复时带着「可能开战」标记会停止。队员以队长上报的 `batch`（`done` / `ok`）为准退出。
- **恢复与插入任务**：`_handle_task_exception` 的 4 个 `task_call('Restart')` 分支先登记 `recovery_pending`（Restart 没开则循环失败）；Restart 以 `recovered` 结束才解除，恢复结束前不推进、不解除阻塞，保留的完成事实（个人突破走到 `TaskEnd` / 队长上报批次 ok）在恢复结束后直接推进，不重跑。插入任务的业务结果只认任务自己通过 `Config.task_delay` 记下的 `success`（`Config.last_task_delay`）；`False` / 异常进内存集合 `unrecovered`，各任务只清除自己，集合非空时不插入步骤、只放行能解除阻塞的任务；`None` 或排到未来不算成功→循环失败。
- **调度**：`Config.update_scheduler` 末尾加可选钩子 `scheduler_hook`（`Script` 每轮挂到当前配置对象上），循环期间暂停普通的 Orochi / RealmRaid，注入当前步骤（enable 视为开），只放行位次严格高于步骤的任务（默认规则看固定顺序、PRIORITY 看数字、FIFO 只放行 Restart）；组队任务只有两边在快照里的 `rank` 都高于各自步骤才插入，否则 `task_delay` 推迟 3 分钟。
- **普通模式**：`loop` 字段、`pid` / `boot_id`、`rank` 都是可选字段，旧文件没有时行为不变；`Script` 的新增逻辑在循环未激活时直接返回；`GeneralInvite.fire_click_issued` 只是旁路标志；Orochi 队长的两处邀请合并进 `_leader_fight_once`（行为不变，3 个结构守卫测试跟着改）；RealmRaid 只多一处 `loop.check()`。
- **测试**：新增 `tests/test_loop_controller.py` 54 项（加入 / 延迟加入 / 参数与身份冲突 / 绑定后退出·重启·失联 / 两轮交替·先完成者等待 / 终态在 publish·心跳·任务切换后保留 / 晚读·新旧循环区分 / 单方补跑 / 可信计数 / 恢复与完成同时存在 / 多个未恢复任务 / 取消命令 / 停止通知 / `decide` 门口）、`tests/test_loop_multiprocess.py` 7 项（**两个真实 spawn 进程**共用同一目录：队长先开队员很久后才开、队员先开、配置不一致、杀掉一个进程另一边失联停止、界面停止通知被确认且对端不等失联、旧进程的取消命令不影响新循环；进程内时钟 60 倍速，让 60 秒失联判定约 1 秒）、`tests/test_loop_script_glue.py` 51 项（调度钩子、真实 `Script.loop` 里的循环步骤前置、`_handle_task_exception` 登记恢复、一次性开关、`ScriptProcess.stop`）、`tests/test_orochi_loop.py` 27 项、`tests/test_realm_raid_loop.py` 12 项（数字为第二轮修复后）。改 3 个既有结构守卫（`test_orochi_team_progress` / `test_general_invite_challenge_reaction` / `test_l2_interaction_reaction`，因御魂队长邀请合并进 `_leader_fight_once`）。变异 14 条（去掉 `peer_in_loop` / 已绑定后不判失联 / `_write` 不带 loop / 没看到结算也计数 / 取消命令不核对 `boot_id` / 恢复未结束就推进 / 一个成功清空整个集合 / 忽略已建立的疲劳上下文 / 钩子不暂停普通任务 / 终态可被改写 / 队员不等队长 / 点过挑战不置位 / 停止不通知）各有测试变红，已还原；其中「终态可被改写」第一次没被抓到，补了 `test_a_second_terminal_event_never_overwrites_the_first`。全量 `2820/2820 OK`（2784 → 2820 为第二轮定点修复）。
- **取舍 / 限制（不掩盖）**：① 插入任务的结果只认 `task_delay(success=)`，没有明确 success 的任务（只传 `target=`）被插入时会按「结果未知」停止循环——严格按「无可靠依据按未知停止」；真机上若频繁出现 `unknown_task_result:<任务>`，需要给那个任务补 success 约定，不要放宽判据；② 队长可信计数依赖「看到结算 / 奖励页」的识别，识别不到就保守停止，宁可停不多算；③ 进程重启后循环不续跑，对端读不到完成记录按失败；④ 只接御魂 → 个人突破，探索及其它副本未适配；⑤ 循环期间同级和更低优先级的普通任务不会运行（直到循环结束），这是「只插入严格更高优先级」的直接结果；⑥ 只在 `ScheduleRule.FILTER` / `PRIORITY` 下有位次，FIFO 下只放行 Restart；⑦ 等对方不设固定超时，等满 30 分钟推送一次；⑧ 没上真机，页面识别 / 计数 / 真实断线表现都是 Level C。
- **定点修复（同日第二轮，用户再次确认个人突破的业务边界后）**：个人突破是完整、独立的任务，完全按自己的配置执行；退四、投降、战败、刷新、换目标都是它的内部流程，**内部某场输赢 / 刷新既不代表循环失败，也不代表整个任务完成**，只有整个任务正常走到自己的结束出口（`TaskEnd`）才标记步骤完成，控制器仍按这个口径判定、不监听每场胜负。审查 5 个反例，**全部成立**并已修：① **外部停止没有覆盖内层开战点**——`RealmRaid` 在 `fire()` 点 `I_FIRE`、`_fire_again()` 点「再次挑战」和确认弹窗 `I_FRESH_ENSURE` 之前各加 `_battle_allowed()`（`loop.check(force=True)`），外部取消或确认失联后不再开新战斗，置 `_loop_halted`，`run()` 退四处据此直接收尾（保留 `finally` 里恢复锁定阵容），不走「退四中断 → 刷新」；这不是按退四输赢判失败，只是执行外部停止请求，当前单场允许结算完；御魂在 `run_invite` 等待循环顶和 `click_fire` 点击前各调 `GeneralInvite._may_fire()`（默认放行，Orochi 覆写为 `loop.check(force=True)`），被拦住时 `click_fire` 返回 `timeout`、不点；普通运行 `loop is None` 完全不受影响。② **让出任务时没有撤回就绪**——新增 `LoopController.withdraw_ready()`（已开始的步骤 `in_step` 不撤回、不会被中途抢占；写盘失败重试 8 次，因为对方正在读文件时 Windows 的替换会被拒、文件里会残留旧的 ready），`abandon_run()` 调它，`Script.loop` 在 prelude 返回 `yield` / `reload` / `stop` 时也调；恢复后重新经过疲劳和会合。③ **可信计数证据顺序**——`GeneralInvite._battle_entry_positive()` 复用的 `is_in_battle()` 本身含失败 / 胜利横幅和奖励页标志，所以 `run_invite` 返回 True 并不能证明「新战斗开始」（实测代码如此）。现在 Orochi 覆写 `_handle_prepare` / `_handle_in_battle` 置 `_battle_seen`，`_handle_result` / `_handle_reward` 只有 `_battle_seen` 之后才置 `_result_seen`；`LoopController.attempt_resolved(fire_clicked, battle_seen, result_seen)`：点过挑战 + 见到准备 / 战斗页 + 之后见到结算页才计一场（重复结算帧只计一次）；没点挑战且没见到准备 / 战斗页、只有结算页 → 残留，不计数也不失败；其余（点过却没确认战斗、确认战斗却没看到结算、没点却见到战斗、先残留结算后新战斗但新战斗结算没观察到）一律保守停止。证据按每次邀请重置。④ **恢复期间回退运行原始任务列表**——(a) `Script.loop` 的「Skip first restart」会把首个任务准备阶段异常请求的 Restart 当成启动 Restart 跳过：`_loop_note_recovery` 登记成功时置 `is_first_task = False`（没有活动循环时不动，普通行为不变）；(b) `schedule_hook` 里恢复任务现在显式排在最前，不再因位次排在步骤后面被丢掉；(c) 阻塞（`recovery_pending` / `unrecovered`）且没有任何可运行或可等待的任务时不再返回原始 pending / waiting（会让普通御魂和低优先级任务绕过阻塞），改为只给一个远在未来的占位项，调度器走循环的明确等待路径；(d) 本方完成最后一步等对方时 `current_step()` 为空，以前会放开所有低优先级任务，现在位次参照最后一步（个人突破），只放行位次更高的任务、不注入步骤。⑤ **β 裁决覆盖已经进入门口的任务**——`decide()` 新增 `peer_ranks_lower`：对方在循环里（`loop.step_rank`）且它发布的该任务 `rank` 不严格高于自己的步骤时，我这边已在门口的同一任务按既有让路间隔（3 分钟）推迟，不再无限等；对方后来才进循环 / 才发布位次也由门口每 2 秒的重判覆盖；位次缺失（对方没开循环 / 旧文件）不下结论；对方已和我在同一任务（门口等 / 在跑）不管。`TeamSync` 新增 `loop_allows`，位次不高于步骤的任务不会被对方「拉」进来；`_loop_should_yield` 在看调度前先 `answer()`，对方在门口等的、且位次高于步骤的任务会被拉到现在并让出。不强制另一边启动未启用的任务（沿用门口既有的 `peer_task_off`）；运行中的御魂批次 / 个人突破不会被切换。本轮另新增 `tests/test_loop_multiprocess.py` 的「让出后撤回就绪」双进程用例。**旧行为为何应失败**：外层 `check` 之后的内层开战点会照常点；让出后的旧 ready 让对端放行（双进程用例里队员的第一步会早于队长回来）；残留结算页 / 重复结算帧会被当成战斗证据；阻塞时普通御魂能绕过；首个任务的 Restart 被跳过后恢复永远结束不了；B 在 X 门口无限等不认为 X 更高的 A。变异 17 条（撤回就绪 ×2、再次挑战 / 确认弹窗 / 首战 / `click_fire` / `run_invite` 的开战前确认、取消后仍走刷新、残留结算当证据 ×2、Restart 被跳过、阻塞时退回原始列表、等最后完成放开低优先级、恢复任务被丢掉、门口不裁决位次、位次不高的任务被拉进来、让出前不接对方的等待）各有测试变红，已还原；其中「残留结算当证据」第一次没被抓到，补了「先残留结算后新战斗」的顺序用例。
- **工作区**：见 §2。HEAD 仍是 `8a82cb8f`。

### 4.129 通用战败页的结算点击：明确识别到 `I_FALSE` 后改点右侧 / 底部区域（D025 补记）

2026-10-25。未提交（在工作区）。**Level A/B（离线）PASS；Level C 未做（用户实机观察）。**

- **现象与业务规则**：用户观察到寮突破失败后程序点了「再次挑战」。用户随后确认御魂 / 探索 / 觉醒 / 日轮 / 御灵等使用通用战败页的任务失败页布局相同，所以规则收敛到通用失败结算入口，**没有逐任务开关**（曾短暂用过 `SETTLEMENT_FAILURE_USES_SAVE_REGIONS` 只给寮突破，已删除；更早的「按按钮坐标避让 + 重采样 + 推出区域」方案也已删除）。
- **核对结论**：寮突破 `tasks/RyouToppa/script_task.py` 继承 `GeneralBattle` / `GameUi` / `SwitchSoul`，**不继承 RealmRaid**，源码里没有任何对 `_fire_again` / `I_FIRE_AGAIN` 的调用（`tasks/` 下它们只在 RealmRaid、Dokan、Nian）；失败收尾走自己的 `_finish_area_battle` → `FAILED_MARKED` → 邻近区域 / 主区域重试，按 `skip_difficult` 配置处理。通用结算有一条能点到按钮的路径：`C_RANDOM_DEFAULT`（742,430,362,230）整个包住 `I_FIRE_AGAIN.roi_front`（830,506,61,36），结算锚点落在按钮上时，突破失败页上的「再次挑战」会被点中。因为没有复现用户当次事件，**不宣称这是当次事件的唯一根因**。
- **日志证据**：10-20 ~ 10-24 的 oas1 / oas2 日志里，`RES_FIRE_AGAIN` 的点击全部出现在 `RealmRaid` 任务内，`RyouToppa` 内没有；寮突破的 `random_default` 点击约 3%（共 42 次、1,481 次中）落进该按钮矩形，全部发生在胜利页（没有造成影响）。这些日志里寮突破没有失败页，**没有复现用户当次事件**。
- **修复**：`GeneralBattle._handle_result` 在**明确识别到失败横幅 `I_FALSE`**（`context.is_win` 为假，阈值 0.8，同一帧只判一次；不是「没识别到胜利」）时，结算推进改用现有 `C_RANDOM_SAVE_RIGHT` / `C_RANDOM_SAVE_BOTTOM`，沿用 80% 右侧 / 20% 底部（从 `_select_reward_region` 拆出 `_pick_save_region()`，随机数消耗不变；失败页不借用整个 `_select_reward_region`，因为它会返回默认区）；已确认失败的帧一定走通用 burst，不依赖 `_is_generic_result_context` 另一次判断；会话里若已保存默认区旧锚点，`_rebase_anchor_for_failure()` 重采右侧 / 底部区的新坐标（只改区域名不够）。段预算、总点击数、节流、点击后截图确认沿用原会话。 胜利结算、普通奖励页、没有胜负横幅的单次节流点击都保持原规则。
- **影响范围与不变**：所有进入通用 `_handle_result` 的任务（御魂 / 探索 / 觉醒 / 日轮 / 御灵 / 个人突破 / 寮突破等，以及 ActivityShikigami 非爬塔路径）。个人突破：普通失败和退四最后一战（`is_final` 用完整配置）走新规则；退四中间的 quick_exit 由 RealmRaid 自己的 `_handle_result` 直接返回结果，不推进结算页；`_fire_again()` / 确认弹窗 / 刷新 / 结束规则不动。皮肤：`CostumeBase.check_costume_battle` 在原地替换 `I_FALSE` 资产对象，通用结算读 `self.I_FALSE`，皮肤失败模板（主题 8 / 12 / 13 / 14，阈值均 0.8）自动适用。六道（`BaseMoonSea` / `BasePeacockKingdom`）、契灵、爬塔单击结算（`NormalClimbAct`）等不委托通用结算的专用处理器不受影响；组队开战失败、寮突破列表失败印记、道馆失败投票 / 冷却不是通用战败页，不纳入。御魂循环、寮突破失败后的区域处理、结算 2~4 段预算 / burst / 安全帽不变。
- **测试**：`tests/test_ryoutoppa_settlement_avoids_again_button.py` 24 项（真实 `run_general_battle` + 结算 handler，只替换截图、页面识别、设备点击和掷骰；覆盖基类 / 寮突破 / 个人突破 / 御魂 / 觉醒 / 探索 / 日轮 / 活动共 7 个任务类的失败页、80/20 两个分支及边界 80 / 81、旧锚点替换、失败多帧的会话节奏、皮肤映射、专用处理器不被改道）；`test_general_battle_settlement` 的 CASE 13 按新规则更新（失败页区域由 `random_default` 改为右侧）。变异 10 条各有测试变红。
- **未做 / 已知边界**：用户已确认各通用战败页布局相同，但仍**没有复现用户当次事件**，也没有在真机上确认各任务失败页的按钮位置。**Level C 待验**：各任务失败后右侧 / 底部点击能正常推进结算、不再误开新战斗；皮肤失败模板在真机上仍能命中（离线只验证了映射和判定入口，没有做真实模板匹配）。

### 4.130 狩猎战接入「随机延迟时间」（`Hunt.scheduler.float_time`）

2026-10-25。未提交（在工作区）。**Level A/B（离线）PASS；Level C 未做。**

- **起因**：用户要求 Hunt 使用现有的随机延迟配置，不新增字段、不改通用调度器。
- **规则**：正常每日计划 = 有效基准时间（`hunt_time.kirin_time` / `netherworld_time`，越界仍按开放时间算）+ 一次随机延迟，上限用现有 `Hunt.scheduler.float_time`；先按当天开放窗口缩小范围再采样：基准离 23:00 还剩 N 秒，延迟在 `[0, min(float_time, N-1)]` 里均匀抽（`random_int`），不是先抽大延迟再统一截到 23:00；留 1 秒是因为计划时间必须严格早于截止点（23:00:00 醒来时 `now > end` 已算过窗口，与 10 分钟重试的 `retry < end` 一致）；基准已在截止点上（配置 23:00:00）或只剩 1 秒时没有随机空间，保持基准、不改到第二天；float_time 为 0 不采样。仍是 `server=False` 写入，没有改成 `server=True`，所以非默认 `server_update` 不会改写目标时间，`task_delay` 也不会再叠加 float_time。
- **接入位置**：`tasks/Hunt/script_task.py` 新增 `_daily_plan(mode, day)`，`_schedule_next_day`（打完 / 已挑战 / 过窗口后排下一天）和 `run()` 里「到点前被提前唤起」两处正常每日计划改用它；`_planned_time` 仍只返回基准时间；写入后不会因读取 / 轮询重新随机。
- **不加延迟的**：未能进入战斗的 10 分钟重试（`run()` 里直接 `_schedule(retry)`，仍要求 `retry < end`）；重试超出窗口改排明天时，那是新的每日计划，只随机一次。
- **不变**：日期分工（周一至周四麒麟、周五至周日阴界之门）、开放窗口、越界配置的处理、已挑战 / 正常结束的排期语义、任务被提前唤起且在窗口内时照常立即执行（见下）。
- **界面文字**：`assets/i18n/zh-CN.json` 的 `kirin_time_help` / `netherworld_time_help` 说明下方时间是基准时间、上方随机延迟参与正常每日排期、范围受开放窗口限制、重试不加延迟，以及到点后仍可能因其他任务 / 疲劳晚于计划，窗口内排上不保证赶得上。
- **测试**：`tests/test_hunt.py` 20 → 38 项（延迟为 0、麒麟 / 阴界基准 + 延迟、上下界、靠近 23:00 范围缩小与不堆积、越界配置、截止点与最后 1 秒边界、只随机一次、重试不叠加、非默认 `server_update`（走真实 `set_next_run` → `Config.task_delay`）、周四→周五 / 周日→周一）；变异 10 条各有测试变红。
- **已知边界（不是本轮引入，没有改）**：① 配置基准时间正好是 23:00:00 时，每天到点醒来都已 `now > 23:00:00`，会一直排到下一天、不会打；② 任务被提前唤起（手动 / next_run 陈旧）且当时已在开放窗口内，会直接执行，不等基准 + 延迟；③ 到点后仍受其他任务、疲劳休息影响，计划在窗口内不保证实际赶得上。
- **未做**：没上真机；随机延迟对实际开战时间的体感、日志里的 `Hunt ... plan: base ... + Ns random delay` 需要用户实测确认。

### 4.131 地域鬼王：当前目标明确战败后有限重试（`tasks/AreaBoss/script_task.py`）

2026-10-25。未提交（在工作区）。**Level A/B（离线）PASS；Level C 未做。**

- **规则（用户 2026-10-25 确认）**：`AreaBoss.ScriptTask.start_fight` 里明确战败最多打 3 场（含首次，固定值 `BATTLE_MAX_ATTEMPTS = 3`，不做配置）：任意一场明确胜利立即结束；连续 3 次明确战败记警告、`boss_fight` 照旧关闭详情页并返回 False，`run()` 继续原有的后续目标流程，不重跑整个任务。「明确战败」= 本场里识别到失败横幅 `I_FALSE`（`AreaBoss._handle_result` 在基类判定 `is_win` 为假时记 `_loss_seen`）且 `run_general_battle` 返回 False；返回 False 但没见过失败横幅（`is_win` 默认 False，例如没识别到结果页）、或返回胜利却见过失败横幅，都算结果不明：不重试、按原样返回 False，不猜测。每次重试前先 `check_can_run()`，再用新截图确认仍在鬼王详情页且挑战按钮 `I_FIRE` 可点（上限 `RETRY_DETAIL_TIMEOUT` 5 秒，否则放弃该目标），然后走同一个挑战入口 `I_FIRE`；不点失败页的「再次挑战」，不重开详情页、不重切层数 / 难度、不重做换御魂和筛选。异常（卡死、页面未知、设备异常）和任务停止不捕获，照旧向上抛。
- **各路径的次数边界**：普通目标、悬赏目标都经 `boss_fight` → `start_fight`，各最多 3 场；悬赏目标走 `fight_reward_boss` → `boss_fight(ultra=True)`，同样每阶段 3 场；开启「没有极时拉到 60 级再打」时，60 级前置战斗是一个阶段（最多 3 场，3 败则放弃该目标、不进极），60 级胜利后切极地鬼是**后续阶段**、有自己的 3 场预算（一个目标最多 3 + 3 场）；重试只在 `start_fight` 一层，外层没有再套重试，所以同一阶段不会超过 3 场。每个目标各自的预算；`boss_fight` 的「已打过直接跳过」「打不开详情页」不是战败，不重试。
- **耗尽后的行为**：日志有 `Area boss battle lost (n/3)` 和 `lost 3 times, skip this boss`，随后 `boss_fight` 仍打 `Area Boss Fight Failed` 并关闭详情页；悬赏目标 3 败不计入 `boss_fought`（和原来失败一致），任务整体仍按原规则 `success=True` 排期。
- **不变**：热门 / 收藏 / 悬赏选择、层数、难度切换、已挑战判断；通用失败结算（右侧 / 底部点击，§4.129）、其它任务、御魂循环、调度器；不新增配置、不新增通用重试框架。
- **测试**：新增 `tests/test_area_boss_retry.py` 23 项（驱动真实 `run` / `boss_fight` / `start_fight` / `_handle_result`，只替换设备、识别、导航和战斗本体）：首胜 1 场、败后胜 2 场、两败后胜 3 场、三败无第四场、重试前新截图并只点 `I_FIRE`（详情页上放「再次挑战」陷阱资产，从不点）、详情页 / 挑战按钮不可用就放弃、每次重试重查时间窗口、结果不明 / 横幅与返回值矛盾不重试、卡死 / 停止异常向上传、打不开详情页和已打过不是战败、失败标记每场重置、每个目标独立预算且不重拉起整个任务、悬赏路径、60 级前置与极的两个阶段。变异 11 条各有测试变红。
- **已知边界 / 未做**：① 若战败结算页之后又经过奖励页，基类 `_handle_reward` 会把 `is_win` 改成 True，`run_general_battle` 返回胜利但见过失败横幅 → 记为结果不明、不重试（以前会被当成胜利）；② 重试默认失败后详情页的难度 / 层数保持不变，没有重新校验（真机要确认）；③ 没上真机。

### 4.132 预设切换后的契灵替换确认框（`tasks/Component/SwitchSoul/switch_soul.py`）

2026-10-25。未提交（在工作区）。**Level A/B（离线）PASS；Level C 未做。**

- **现象**：切换队伍预设、确认之后，如果预设里的契灵已装配在其他阴阳师身上，游戏会再弹「当前契灵已装配于其他阴阳师，是否替换？」，不处理会挡住后面的导航。
- **规则**：预设切换（数字 / 按名称两条路径）在预设确认框出现并确认之后，用 `SwitchSoul._confirm_bondling_replace_dialog` 做一次短时有界观察（`REPLACE_OBSERVE_TIMEOUT = 2.0` 秒）：出现「当前契灵已装配于其他阴阳师，是否替换？」就点「确定」并等它关闭（`REPLACE_CLOSE_TIMEOUT = 8.0` 秒）再继续；没出现就正常继续；弹窗持续存在或确认未生效，超时后抛 `GamePageUnknownError` 交还 `script.py` 原有异常处理（通知 + 重启），不无限点击、不记切换成功。用户选了这个预设就等于允许替换，不加配置开关。只在预设确认之后调用，没有预设确认框（已装备同一预设）时不观察，不是全局的「看到确定就点」。
- **识别资源**：复用 `I_SOU_SWITCH_SURE`（「确定」按钮，与预设确认框同一位置、同一风格），没有新增资源、没有降阈值、没有固定坐标。**离线只验证了流程**，该模板能不能识别替换框是推断（同一风格的「确定」按钮），没有该弹窗的截图可比对；若真机识别不到，需要补一张替换框的资源。
- **接入方式**：数字模式在 `switch_soul_one` 里 `_observe_confirm_dialog()` 返回 True（预设确认过）之后调用；按名称模式在 `switch_soul_by_name` 的切换循环里记录 `confirmed`（点过 `I_SOU_SWITCH_SURE`），循环结束、写成功日志之前调用。两条路径共用同一个小方法；点「确定」抽成 `_press_sure()`（CONFIRM reaction + fresh confirm，3 秒间隔），预设确认框的首次确认也改走它，登记册里的点击点数量不变。替换框的首次点击在预设确认刚点过之后最多晚到 3 秒（期间继续截图观察，不额外点击）。
- **不变**：分组、队伍选择、滑顶、已装备同一预设时的正常结束、OCR 按名称的原有节奏和点 4 次队伍的流程、其它任务。
- **有界保护补齐（同日第二次）**：预设确认框「确定」连续存在、始终点不掉时也有本地明确超时（`CONFIRM_CLOSE_TIMEOUT = 10.0` 秒）：数字模式 `_confirm_team_switch` 的恢复循环（原来是无界的 `while 1`）和按名称模式的切换循环（原来「确定」分支会一直点，点队伍不成功时循环也不会结束）都在超时后经 `_raise_confirm_stuck` 抛 `GamePageUnknownError`，交还 `script.py` 原有处理，调用方不再写切换成功日志。点击间隔（3 秒 / 0.8 秒）、反应时间、正常选择行为不变；按名称模式的计时在「确定」消失一帧后清零，间歇出现不会误报。原确认框与契灵替换框连续出现（中间没有空白帧）时，两个框都在同一段超时内处理完才继续。
- **测试**：新增 `tests/test_switch_soul_replace_dialog.py` 15 项（真实 `SwitchSoul` 方法 + 真实 `appear_then_click`，沿用 `test_switch_soul_numeric_v1` 的虚拟时钟 Sandbox）：只有原确认框、原确认后替换框稍后出现、没有额外弹窗（有界短观察）、点击后弹窗关闭继续并记成功、弹窗持续存在有界退出（异常、点击次数有界、不记成功）、已装备同一预设不观察、数字 / 名称两条路径、只在预设确认之后调用。变异 10 条各有测试变红。两处结构钉子测试按「点击点抽成 `_press_sure`」更新（`test_switch_soul_numeric_v1` / `test_switch_soul_group_top_v2`），`tests/test_l1_l2_integration.py` 的 `POST_C1_CONSUMERS` 里 `_confirm_team_switch` 改成 `_press_sure`，`docs/L2_CALLSITE_REGISTER.md` 用 `dev_tools.click_callsite_register --write` 重新生成（总数仍 1104、policy 点位仍 97，只是行号 / 函数名变化）。
- **总超时补充（同日第三次）**：按名称模式「选队伍 + 处理确认」循环有总超时 `SWITCH_LOOP_TIMEOUT = 45.0` 秒：进入循环前启动，每轮在所有 `continue` 分支之前检查，不因看到 / 看不到「确定」、点击失败或空白帧重置，超时经 `_raise_confirm_stuck` 抛 `GamePageUnknownError`（不写成功日志）。封住「确定和队伍都识别不到」和「确定间歇出现、`sure_timer` 反复清零但始终无进展」两条原来无界的路径。取值依据：正常流程是 4 次队伍点击（每次最少隔 1.5 秒，约 6 秒）加预设确认的 0.8 秒间隔点击，慢模拟器上加 OCR 与页面响应也在 10~15 秒内，45 秒留 3 倍以上余量，是故障保护、不是节奏参数。三种超时各管一段：「确定」连续存在 10 秒（`CONFIRM_CLOSE_TIMEOUT`，消失后清零）、循环之后的契灵替换框 8 秒（`REPLACE_CLOSE_TIMEOUT`）、整段循环 45 秒（`SWITCH_LOOP_TIMEOUT`）。只覆盖这一段循环；名称模式里的分组查找 / 滑动 / 导航没有总超时（本轮没动）。
- **总超时的测试**：`tests/test_switch_soul_replace_dialog.py` 再增 5 项（共 27 项）：全程没有确定且点队伍一直失败（不靠沙箱的截图失控保护）、确定间歇出现无进展（由总超时而不是 `sure_timer` 退出）、「点确定 → continue」分支绕不过总超时、三种正常流程不逼近总超时且 0.8 秒间隔 / 四次队伍点击不变、三种超时各自覆盖范围与报错信息；变异 7 条各有测试变红。
- **有界保护的测试**：`tests/test_switch_soul_replace_dialog.py` 再增 7 项（共 22 项）：两个框连续出现无空白帧（数字 / 名称）、「确定」从第一次出现起就点不掉（数字 / 名称，含点队伍一直不成功的名称模式）、点击仍是 3 秒间隔且只有首次带 reaction、名称模式计时间歇清零；变异 6 条各有测试变红（旧代码上这些卡死用例会撞上 300 次截图的失控保护）。
- **未做**：没上真机；替换框的识别、替换后契灵是否确实换到当前预设、预设确认到替换框出现的实际间隔（2 秒窗口是否够）都待真机确认。

### 4.133 御魂 → 个人突破循环的配置在 OASX 里的显示与保存（D032 补记）

2026-10-25。未提交（在工作区）。**Level A/B（离线，仅后端侧）PASS；OASX 真实界面未验证。**

- **起因**：用户反馈循环配置在 OASX 上显示英文、每批场数的随机区间配置不了。
- **英文显示的根因（源码确认）**：OASX 的标签 = 参数 `name`（字段名）`.tr`、说明 = `description`（`*_help`）`.tr`、分组名 = 组 key `.tr`；翻译只来自 OASX 自带的 Dart 表（`lib/translation/cn_parts`）和启动时从后端 `/home/additional_translate`（= `assets/i18n/zh-CN.json` / `en-US.json`）追加的内容（后者覆盖前者）。`loop_config` / `start_loop` / `rounds` / `target_min` / `target_max` 和四条 `*_help` 在这两处都没有；原来写的 `module/config/i18n/zh_CN.xml` 没有任何代码读取（OASX 也不读），所以界面显示字段名原文。`module/config/i18n/zh-CN.json` 只是 OASX 把自己的 Dart 表回传给后端存的，不是输入。
- **区间「无法配置」的核对**：用真实 `ConfigModel`（`script_task` 输出、`script_set_arg` 逐字段保存、全新实例重读）和真实 `Script._loop_consume_request` 走了整条后端链：120 / 140 能保存、重读后保留、循环启动时读到 `tmin=120 tmax=140`，旧的修复前代码上这条链本来就是通的。真正查到的缺陷有三处：① 字段没有中文，看不出哪个是最少 / 最多；② `LoopConfig` 是普通 `BaseModel`，赋值不校验范围——越界值（0、1000、轮数 101，甚至非整数）会被存进文件，下次加载时 `ConfigBase.__init__` 把整个 `loop_config` 组静默重置成默认值（轮数 / 最少 / 最多一起丢）；③ 最少 > 最多被拒绝时只给原因码 `target_range_invalid`，没有中文说明。OASX 一侧另有两点（Flutter，本机没有 SDK，没有改也没有验证）：立即保存模式下 `_applyValue` 先弹「设置已保存」、不等后端结果，后端返回 False / 400 时界面静默；后端 `merge_value` 不输出 `minimum` / `maximum`，OASX 的整数范围校验永远不触发。
- **修复（只在 OAS，不需要重新构建 OASX）**：① 翻译补到 OASX 实际加载的 `assets/i18n/zh-CN.json`（单一来源，另有 `en-US.json`）：分组「御魂→个人突破循环」，字段「开始循环（一次性）/ 循环轮数 / 每批御魂最少场数 / 每批御魂最多场数」，说明讲清一轮的含义、队长随机一次、队员同一个数、个人突破跑到正常结束、开始循环是读取后自动关回的一次性请求；② `LoopConfig` 开 `validate_assignment`，越界 / 非整数保存失败（`script_set_arg` 返回 False，原值保留，整组不再被静默重置）；最少 ≤ 最多**不在保存时校验**（改区间的中间状态 10～30 → 120～30 → 120～140 不会被卡住），只在打开「开始循环」时检查，下限等于上限表示固定场数；③ 拒绝开始时给中文说明（含当前最少 / 最多的数值，提示开关已关回、需要重新打开）。字段名、默认值、已有配置值、业务规则都没动。
- **测试**：新增 `tests/test_loop_config_ui.py` 15 项（翻译键覆盖、参数输出两个整数场数字段、120～140 保存 / 重读 / 循环读取、两种修改顺序、逐位输入、下限等于上限、最少大于最多的拒绝与中文信息、越界 / 非整数拒绝且整组不被重置、1 / 999 / 100 边界、旧配置兼容、字段名与默认值不变）；变异 8 条各有测试变红。
- **是否要重新构建 OASX**：不需要——翻译走后端追加（OASX 启动时 `refreshTransFromRemote`，现有源码已具备），重启 OAS 后端 + 重启（或重新连接）OASX 即可；仍运行很旧的 OASX 构建（没有追加翻译的逻辑）则需要更新。OASX 的两处缺陷（保存反馈、范围校验）是否值得改，见 ROADMAP。
- **未验证**：真实 OASX 界面里标签是否显示中文、输入 120 / 140 离开再回来是否保留（后端侧已验证，界面侧只读了源码）。

### 4.134 百鬼棋局：从上游 `self` 选择性合入购买 / 手牌恢复 / 点击记录 / 红叉浮窗 / 鼬乐币 OCR

2026-10-25。**已提交到 master（未推送）。Level A/B（离线）PASS；Level C 待验。** 这是**选择性合入**，不是「同步至某个上游 SHA」：只有下表列出的部分进入了本地，`ce476e8943bb981c2cd91865cd734865c957c91d..47a3a3bc6173e6560ab8cc3658d3e55bc2c80287` 之间其余触及棋局的上游提交（08-31 荒川阵容 / 符咒选取 / 快速匹配、09-09 结算点击、09-20 状态决策流程、09-29 / 09-30 点击与 `profile` 统一、主动投掷与新阵容等）**都没有合入**。固定上游目标 `47a3a3bc6173e6560ab8cc3658d3e55bc2c80287`（当日 `git ls-remote` 核对）。

| 来源（完整 SHA） | 合入方式 | 结论 | 实际范围 |
|---|---|---|---|
| `631968c6ecee7e992350b3c3713bdf3f7a3bed3f` | 函数级提取（本地提交「chess: 选择性提取上游 631968c6 的购买与紧急清理前置」） | **部分合入（仅前置）** | 只取 4 个函数：`economy._buy_shop_slot`、`base_task.ui_click_until_disappear`、`hand_operations.emergency_cleanup_hand`、`hand_operations._free_one_hand_slot_for_purchase`。替换前本地这 4 个函数与上游父提交 `00c083e83a6ad8a258b05536dab8454a77e20325` 逐字相同（脚本校验），替换后与 631968c6 逐字相同；不含相邻函数的改动。其余 1243 个文件（Frame 卡牌识别重写、`ui_click_until_appear` 等新方法、`profile` / Scatter、资源再生成、几十个无关任务）不合入。 |
| `0501cb195c1b403bd4eec4230c075bd239c10701` | `git cherry-pick -x` | **已合入** | 增删行与上游逐行一致。 |
| `d944d411bd8fe3932b45f43e80358d28b019c8ba` | `git cherry-pick -x` | **已合入** | 含 `tasks/base_task.py` 的 `max_clicks`。增删行与上游逐行一致。 |
| `47a3a3bc6173e6560ab8cc3658d3e55bc2c80287` | `git cherry-pick -x` | **已合入（两段都在）** | 增删行与上游逐行一致。 |
| `90a03025cc6af474f013e1a995a1002df254af1c` | 适配提交（本地提交「chess: 合入上游 90a03025 …」） | **已合入（有命名与 profile 适配）** | `_burst()` 覆盖、红叉原图 `page_close_red.png`（逐字节相同）、红叉模板条目、`O_COIN` ROI。见下方「冲突适配」。 |
| `51dbf56475dcbb63ddd46f8f99fe6f90982c8620` | 不合入 | 未合入 | 上游用它把 GeneralBuff 的 `I_CLOSE_RED` 改名来解决与红叉的重名；它还混有寮宴会第二种旗帜等无关改动。本地改为给棋局一侧命名（见下）。 |
| `a8af52233157ac5a0177c1e232746f78b3cae674` / `dd72b786d4e2ecea034173f5026bc23d4efbbea3` / `d856707abb83e3daf3a6d3e2f9f3e7c3f0588a8f` / `521e1a8d151bd3f804bbb3975b2a08912e3ca684` | 不合入 | 本轮范围外 | 主动投掷 / 黄金复制 / 新阵容 / 站位替换。 |

**购买的最终语义（上游原样）**：
- `_buy_shop_slot` 进入时识别不到目标 → 返回 False，不点击。
- 每一轮调用 `ui_click_until_disappear(click_target=该格, interval=0.3, timeout≤2s, confirm_frames=2, max_clicks=3, guard=允许购买且无符咒弹窗)`：至少点过一次、且该格连续两帧识别不到原目标才返回 True（上游判据**不额外检查商店是否仍展开**）；guard 失败（鬼阶段 / 符咒弹窗）→ 购买返回 False；超时或点满 3 次仍在 → 回到外层。
- 外层：重新识别仍是目标 → 检查金币 → 恢复（先紧急清理；清理既没装配也没卖非阵容卡时直接卖一张最右侧已识别阵容卡；已清理过则卖阵容卡）→ 下一轮；清理 + 卖阵容卡之后仍买不到 → 「cancel current purchase」返回 False；重新识别不到 → False。
- **点击上限是「每轮最多 3 次」，不是整次购买的总预算**：初始 + 最多两次恢复 = 最多 3 轮，一个目标最多 9 次点击（无腾位直接卖卡时最多 6 次）；另有 `SHOP_BUY_TIMEOUT = 30` 秒总时限。
- 确认买到后 `click_record_remove(该格)`；刷新确认成功（≥3 格变化）后只清确认变化的格子。失败 / 未确认不清，不清其他按钮。
- 紧急清理与卖阵容卡的关店现在允许「备」「战」两个阶段（631968c6 的前置），战斗阶段的购买恢复不再在关店处失败。

**冲突适配**（只在冲突处，业务逻辑不改）：
- `tasks/base_task.py::ui_click_until_disappear`：提交里是上游原样（HEAD 上该函数还没有 `policy`）。工作区里的未提交 L2 改动给它加了 `policy`，合并后的工作区签名是 `(click, interval=1, policy=None, *, click_target, visible, guard, timeout, confirm_frames, max_clicks)`：`policy` 仍是第 3 个位置参数，旧调用不变；两个点击分支都用 `**_policy_kw(policy)` 透传，`policy=None` 时与上游完全一致。
- 红叉资产名 `I_CLOSE_RED` → `I_CHESS_CLOSE_RED`（`image_chess.json` 的 `itemName` 由 `close_red` 改为 `chess_close_red`）：上游原名会生成 `GameUiAssets.I_CLOSE_RED`，实测在 20 个任务类（Exploration / Hunt / Secret / ActivityShikigami / Chess 等）的 MRO 中遮蔽 `GeneralBuffAssets.I_CLOSE_RED`（加成开关）。上游另用 `51dbf564` 改 GeneralBuff 一侧，本次不引入。
- 不写 `profile="High"`：本地 `RuleImage` 没有该参数；上游它只传给 `RuleClick` 作 Scatter 点击密度，与识别无关；本地点击走 L1 采样。`GameUi/assets.py` 由 `dev_tools/assets_extract.py` 生成（在 HEAD 上对 GameUi 逐字节可复现），只多出红叉一行。
- 上游 `_burst` 写在 `ChessLegacyScriptTask`，本地棋局类是 `ScriptTask`。

**同日早先两版的处理**：先手写过一版购买判据 / 预算 / 点击记录（D036，已撤销，代码不在仓库），后又只合入过 `0501cb19`；本版取代两者。上一版验证测试 `tests/test_chess_hand_recovery_upstream_0501cb19.py`（未跟踪）已并入新的测试模块后删除。

**保留**：七套本地阵容（默认荒川）、保段位规则、L1 / L2 点击采样与反应、拖动时序、匹配 / 结算 / 退出、`tasks/GameUi/chess_battle.py`、其余任务。

**测试**：新增 `tests/test_chess_upstream_selective_merge.py` 30 项（驱动真实 `_buy_shop_slot` + `BaseTask.ui_click_until_disappear`、`_free_one_hand_slot_for_purchase` / `sell_one_lineup_hand_card`、`_click_shop_refresh_and_confirm_slots`、`Device.click_record_remove`、棋局 `ScriptTask._burst`；只替换点击 / 截图 / 识别 / 阶段 OCR / 时钟）；`policy` 透传一项只在带 `policy` 的工作区版本运行，在仅含提交的 HEAD 上跳过。在合入前代码上运行，21 项失败 / 报错。`docs/L2_CALLSITE_REGISTER.md` 重新生成；`tests/test_l2_c0_registry.py` 记一笔点位变化（总数 +2、KEEP_SPECIAL +1、PRIMITIVE +1，均为规则分类）。
- **未验证**：红叉模板、新 `O_COIN` 位置在当前界面上的识别效果；`_burst` 对棋局任务每次截图都检查右上 (1077,19,151,144) 区域，若别的界面在此处有红叉按钮也会被点；真机购买两帧确认与 9 次点击上限的实际节奏；战斗阶段关店清理。

### 4.141 秘闻首次通关结果页：结算推进区域改走右侧 / 底部安全区（oas2 10-25 17:51 卡死）

2026-10-25。未提交（在工作区）。**Level A/B PASS；Level C 待验。**

- **起因**：oas2 秘闻第 5 层（妖刀·伍式，未通关）首次通关，弹出「胜利 / 排名 / 通关阵容」结果页，结算锚点 (869, 555) 点满 9 次没推进，`Settlement safety bound reached: total_clicks=9/9` 之后 60 秒无动作 → `GameStuckError: Wait too long`，游戏重启。报错截图 `log/error/oas2_1792921921352/`。
- **根因**：`GeneralBattle._handle_result` 里通用结果页的选区写死 `C_RANDOM_DEFAULT`（742,430,362,230），整块落在「通关阵容」面板（右面板约 x 668~1207、y 220~681）里；同一结算状态复用锚点，9 次都点在同一处。秘闻只覆盖了「奖励页」的选区（§4.106），结果页没覆盖。**反复出现的已知问题**：10-12 16:41 oas2 第 10 层（锚点 (886, 474)）、10-19 oas2 第 1 / 3 / 4 层（三次 `Wait too long`，第 2 层点一次就过）、今天第 5 层。
- **修改**：`tasks/Component/GeneralBattle/general_battle.py` 新增可覆盖的 `_select_result_region()`（默认 `C_RANDOM_DEFAULT`，所有其它任务行为不变），`_handle_result` 的通用胜利结果页改用它作 `region_provider`（失败页仍固定走 `_pick_save_region`）；`tasks/Secret/script_task.py` 覆盖成 `_pick_save_region()`（右侧 80% / 底部 20%，用户 2026-10-25 建议）。
- **已知局限（按报错截图实测几何，未改）**：`C_RANDOM_SAVE_RIGHT`（x 1185~1272）左侧约 25% 仍在面板里（面板右沿约 x 1207），`C_RANDOM_SAVE_BOTTOM`（y 639~708）上部约 60% 仍在面板里（面板下沿约 y 681）；锚点每个结算状态只采一次，估计约三成会采进面板——这时仍会和以前一样点满 9 次。要消除，需要给秘闻单独收窄一对区域（面板右侧 x ≥ 1215、底部 y ≥ 684）。是否收窄由用户决定。
- **测试**：`tests/test_secret_settlement_region.py` 新增 `SecretResultRegionTest` 4 项（秘闻选区只在右 / 底两个安全区、80/20 偏向右侧；锚点落在所选区域内；其它任务（GeneralBattle / RealmRaid / Orochi）仍是默认区；`_handle_result` 走钩子且失败页仍用 `_pick_save_region`）。既有用例未改。
- **Level C 待验**：秘闻首次通关一层，日志 `Settlement first click: state=generic_result, anchor=(x, y)` 的锚点在右侧 / 底部安全区，1~3 次点击后回到秘闻列表（`Exit matcher hit`），不再出现 `Settlement safety bound reached` 与 `Wait too long`；多跑几次统计落进面板的比例，决定要不要收窄。**需重启 OAS 进程生效。**
- **工作区**：改 `tasks/Component/GeneralBattle/general_battle.py`、`tasks/Secret/script_task.py`、`tests/test_secret_settlement_region.py`。

### 4.135 式神活动配置页后端准备：可选展示信息 `GET /{script}/{task}/args/layout`

2026-10-25。未提交（在工作区）。**Level A/B（离线）PASS；OASX 页面未做、未验证；不是界面或真机通过。**

- **目标**：OASX 要把式神活动页整理成「活动玩法」多选 + 按玩法归集的折叠分组。本轮只做后端准备，不改任何已持久化字段、默认值、`task_sequence` 字符串语义、别名 / 去重 / 次数为零跳过规则、旧配置迁移和执行逻辑。随机次数区间**未实现**，仍是固定次数。
- **核实结论**：`/args` 已给出全部字段的真实 `(group, argument)`、值、默认值与类型，前端折叠不需要服务端删字段；缺的只有「玩法选项与别名、字段归属、初始折叠、爬塔子分组」这类 OASX 无法从 schema 推出的信息。
- **做法**：新增只读接口 `GET /{script}/{task}/args/layout`（`ConfigModel.script_task_layout` → `TASK_ARGS_LAYOUTS` 注册表，目前只有 `activity_shikigami`，其他任务返回 `{}`）；构造逻辑在 `tasks/ActivityShikigami/args_layout.py`。`/args` 输出不变，旧客户端不请求新接口即完全不受影响；展示信息不写进用户配置。i18n 补 `activity_play_*` / `activity_battle_*` / `activity_advanced_settings` 的中英文标题。
- **接口要点**：`selector`（落在 `general_config.task_sequence`，含 `options`、`aliases`、`separator`、`selected`=按旧字符串顺序解析出的玩法、`invalid`=无法识别的项、`min_selected=1`）；`plays[]`（`rich_man` / `climb` / `fakegod`，各含 `selected`、`initial_expanded`、`battles[]`，每个 battle 给 `limit` / `soul`（四个御魂预设字段）/ `battle_group`；爬塔下 `ap` / `pass` / `boss` / `ap100` 四个子分组，`extra` 里是 `use_penta_pass`）；`common`；`advanced`（`scheduler`、`fire_reaction`，默认收起）。所有引用都是 `/args` 里原样的 `(group, argument)`，保存仍走 `PUT /{script}/{task}/{group}/{argument}/value`。
- **折叠语义**：`initial_expanded` 只用于首次打开（选中且次数 > 0 才展开）；前端编辑过程中不应因重新读取而改变折叠状态，只在首次加载时采用。
- **执行顺序**：`selected` 按 `task_sequence` 原顺序给出，不规范化；前端多选必须按该顺序回写（取消 / 勾选只增删项，不重排）；全部取消会得到空串，`task_sequence_v` 会因此抛错，所以最少保留一项。
- **测试**：新增 `tests/test_activity_shikigami_args_layout.py` 14 项（选项与别名、旧顺序不变、非法项不抛异常、六类战斗字段归属与引用均存在于 `/args`、初始折叠、读取不写文件不改状态、其他任务返回 `{}` 且 `/args` 不变、默认值与字段名不变、按原路径保存后重读保留顺序与未选玩法参数、旧配置迁移、真实路由 200 且 `/args` 逐字一致）。全量 2975 项 OK。
- **未验证**：OASX 实际界面；前端待办见 ROADMAP。

### 4.136 式神活动 → 爬塔 → 体力：可配置随机战斗次数区间 [ap_limit, ap_limit_max]

2026-10-25。未提交（在工作区）。**Level A/B（离线）PASS；OASX 未改、页面还不能输入区间；未做真机验证。**

- **字段**：`ap_limit` 保留为下限（单位不变：进入战斗的场数），新增 `ap_limit_max` 为上限（整数，默认 0）。旧配置缺 `ap_limit_max` 时在内存里按 `N～N` 读入（`GeneralConfig` 的 before 校验只看「键是否缺失」），不写文件；明确写了 0 就是 0（`100～0` 非法，不当作旧配置）。旧 `general_climb` 迁移路径同样得到 `N～N`。读取 / GET 不写文件。
- **保存**：只给这两个字段做保存时校验（`GeneralConfig.__setattr__`，严格非负整数；其他字段保存行为不变，`GeneralConfig` 没开 `validate_assignment`）。失败保留原值、不重置整组。上下限逐字段保存，中间状态（如 100～30）允许；完整区间关系 `1 ≤ 最少 ≤ 最多` 或 `0～0` 只在 `ScriptTask.run` 开头校验，非法抛 `RequestHumanTakeover`（中文信息含实际上下限），早于 `before_run` 和任何游戏操作；不截断、不交换、不回退默认值。区间非法时即使没选爬塔也拒绝启动。
- **旧配置改下限**：旧 `ap_limit=120` 读入为 `120～120`，把下限改成 100 保存后，上限已按旧固定次数落成 120（`100～120`，不会超过旧运行量），之后可单独把上限改到 140。
- **随机目标**：`BaseAct.climb_ap_target()`，用 `module.base.utils.random.random_int` 在闭区间取一个整数，缓存在任务对象 `ap_target`，不写回配置；固定区间不采样；`0～0` 返回 0 不采样。`ScriptTask.run` 在顺序确定后、跑任何玩法之前先确定（体力排在大富翁之后也用同一个值）。日志：`体力爬塔本次目标：126 次，配置区间：100～140 次`。
- **恢复语义（2026-10-26 修正，§4.137）**：`Script.run` 每次新建 `ScriptTask`，目标与计数留不下来，**但这不等于「新的一次执行」**——对象重建不是重新抽取的依据。区间随机的活动执行被自动恢复类异常打断时，改为终止本次执行并延后（见 §4.137）；同一任务对象内部的恢复沿用目标；人工停止 / 进程退出不自动续跑。
- **五倍券**：`record_action` 在成功进入战斗时 +1，不看五倍券；`_record_climb_consumption` 另记资源快照（开五倍券时体力 5、五倍券 1）。所以开五倍券后「目标 100 次」＝进入 100 场战斗，每场按 5 份体力、1 张五倍券消耗；与旧 `ap_limit=100` 完全一致，没有换算。
- **接口**：`/args` 多一个 `ap_limit_max`（integer）和 `ap_limit` 的 `description`；layout 版本仍为 1，体力那个 battle 多一个可选 `range`（`min`＝`ap_limit`、`max`＝`ap_limit_max`、`min_title` / `max_title`），原 `limit` 引用不变。已读 OASX 解析器：未知键被忽略，不触发版本回退；旧前端的引用无重复，`ap_limit_max` 会作为普通整数出现在「其他设置」。新前端须把 `range.min` 与 `limit` 当同一个参数只数一次，并把 `range.max` 记为已覆盖，才不会在「其他设置」重复显示。
- **测试**：新增 `tests/test_activity_shikigami_ap_range.py` 26 项；`tests/test_activity_shikigami_args_layout.py` 的字段顺序断言新增 `ap_limit_max`（原有字段及顺序断言保留），并让「旧配置」用例的文件不带 `ap_limit_max`。全量 3009 项 OK。
- **未做**：OASX 区间控件；门票 / 首领 / 百体 / 大富翁 / 伪神的区间；真机验证。

### 4.137 体力爬塔随机区间：异常恢复边界（修正 §4.136 的恢复语义）

2026-10-26。未提交（在工作区）。**Level A/B（离线）PASS；未做真机验证。**

- **问题**：§4.136 把「异常后 `ScriptTask` 被重建、目标与计数归零」当作新的一次执行，允许重新随机并从零开始。例如目标 120 已打 80 场，卡死 Restart 后重新抽 135 从 0 开始——与需求不符。
- **真实调用链**：`ScriptTask.run` 抛 `GameStuckError` / `GameTooManyClickError` / `GameBugError` / `GamePageUnknownError` / `GameNotRunningError` → `Script.run` 的 `_handle_task_exception` → `config.task_call('Restart')`、返回失败 → `loop` 里 `del_cached_property(config)` → 下一轮调度：活动自己的 `next_run` 没被动过（仍是过去时间），Restart 先跑，随后活动**立刻再次到点**，新建 `ScriptTask` 重抽、计数归零、已做过的前置玩法重跑。其他异常（`ScriptError` / `RequestHumanTakeover` / 未识别异常）是 `exit(1)`，不会被自动重跑。
- **选择：明确终止，不做续跑**。目标虽然可以保存，但中断瞬间那一场战斗是否打完、是否已计入不可确认，没有可信进度；不猜剩余场次，不用下限 / 重抽 / 清零伪装恢复。
- **做法**（只改 `tasks/ActivityShikigami/script_task.py`，不改 `script.py` / 公共调度）：当本次执行含「区间随机的体力爬塔」（已选爬塔、体力启用、`ap_limit < ap_limit_max`）且**已经进入过任一玩法**时，自动恢复类异常会先把活动的 `next_run` 延后，再原样抛出原异常。延后用 `config.task_delay(start_time=中断时刻, success=False)`（**不用** `set_next_run`：它默认以任务开始时刻为基准，运行 30 分钟、失败间隔 10 分钟时结果已在过去，Restart 后会立刻重跑），沿用现有失败间隔与 `server_update` 规则（09:00 为「中断时刻＋失败间隔＋浮动」，非 09:00 为下一个服务器更新点）。写入后**从磁盘读回**确认 `next_run` 严格晚于当前时间。
- **兜底（§4.138）**：写入失败（磁盘不可写等）、读回的 `next_run` 不在未来（如失败间隔为 0 且 `server_update` 为默认 09:00）、或保存接口没报错但没生效时，普通的自动 Restart 会让活动立刻重跑并重新随机，所以改抛 `RequestHumanTakeover`（现有人工处理路径：推送并 `exit(1)`，不安排 Restart），提示「本次体力目标和进度无法可靠恢复，延后排期也未成功，需要人工处理」；异常链为 人工处理 ← 保存失败 ← 原始游戏异常（读回无效时直接 ← 原始游戏异常）。**日志里写「已终止」而排期没改成不算保护**。
- **保证范围**：当前进程内，自动恢复不会重新拉起本次活动。持久化保护只有活动的 `next_run`：写入成功才有；进程被强杀、磁盘不可写时没有任何持久化保护，只能靠当前进程停止。用户之后重新启动并把活动改成「现在运行」（或下次排期到点）视为新的一次执行，重新抽取；进程重启本身不会让活动变成到点。状态清理：正常结束由 `finish_activity_task` 的成功排期覆盖。
- **不变**：固定次数（含旧配置 N～N）没有随机目标，异常后的重跑行为保持原样；进入任何玩法之前的异常、`exit(1)` 类致命异常、其他任务的 Restart 恢复规则均不变；同一任务对象内的恢复不重抽。
- **测试**：新增 `tests/test_activity_shikigami_ap_recovery.py` 17 项（§4.137 的 11 项 + §4.138 的 7 项并替换了原「保存失败仅保留原异常」一项），驱动真实 `Script.run` / `_handle_task_exception` / `task_call('Restart')` / 真实 `Config` 排期和真实 `ScriptTask.run`：80 场后卡死不重抽不重跑、前置大富翁后卡死不重跑、重复 Restart 不被拉起、手动改成现在运行是新执行、正常完成后重新抽取、同对象重进不重抽、固定次数 / 旧 N / 玩法前异常 / 致命异常 / 其他任务 Restart 原行为；§4.138：已运行 30 分钟＋失败间隔 10 分钟仍在未来且 Restart 后其他任务照常、非 09:00 `server_update` 的最终排期、失败间隔 0（默认 09:00 → 人工处理，非 09:00 → 有效）、写入失败与「写入无异常但未生效」均转人工处理且不 Restart / 不再构造任务 / 不再抽取、人工处理不记成功。变异验证：回退时间基准、把兜底改成只记日志，均有测试变红。
- **未验证**：真机上的实际卡死恢复链路与日志。

### 4.138 体力爬塔随机区间：延后排期的时间基准与失败兜底（修正 §4.137 的两处缺陷）

2026-10-26。未提交（在工作区）。**Level A/B（离线）PASS；未做真机验证。**

- **问题 1**：§4.137 用 `set_next_run(success=False)`，其默认以任务开始时刻为基准；活动已运行 30 分钟、失败间隔 10 分钟时，算出的 `next_run` 早已过去，Restart 之后活动仍立刻重跑。**修复**：改为 `config.task_delay(start_time=中断时刻, success=False)`，并从磁盘读回确认确实在未来。
- **问题 2**：延后写入失败时只记日志再抛原异常，公共处理随后 Restart，活动重新到点、重抽、计数归零。**修复**：写入失败 / 读回不在未来时抛 `RequestHumanTakeover`（见 §4.137 的「兜底」），不再走自动 Restart。
- **范围**：仅 `tasks/ActivityShikigami/script_task.py`；不改公共异常分类与其他任务。
- **未验证**：真机；真实磁盘故障。

### 4.139 每日琐事：吉闻按天检查一次、寿司按时段检查一次、收邮件补已处理检查（取消寿司 10 分钟重试）

2026-10-26。未提交（在工作区）。**Level A/B PASS；Level C 待验。** 业务口径是用户 2026-10-26 明确给定的，见 `docs/DECISIONS.md` D031「补记（检查一次口径）」。

- **起因**：10-26 oas1 / oas2 日志里寿司持续「not found → 10 分钟后重试」，整个每日琐事被反复启动；吉闻没识别到奖励同样不记完成、跟着任务重试；收邮件虽写了完成时间，入口却没检查，每次运行都重新收。用户确认 oas1 的吉闻实际已领取，不能再把「没识别到奖励」当作必须重试。
- **吉闻**（`run_luck_msg`）：区分三种结局。领到奖励且弹窗关掉 → 日志「吉闻已领取，今日处理完成。」，记 `luck_msg_dt`；正常检查完（有界等待结束）没有可领内容 → 「未发现可领取吉闻，今日检查完成。」，同样记；`goto_page(page_friends_luck)` 返回 `False`（页面没进去）、看到奖励但关不掉弹窗 → 不记（警告日志）；设备 / 流程异常直接上抛，不写 finally，同样不记。当天再进入直接跳过，次日重新检查。保留原有有界等待、友情点弹窗处理与 `C_RANDOM_BOTTOM` 关奖励，没有加重试或扩大点击范围。
- **寿司**（`run_courtyard_sushi`）：每个时段（中午 12:00–14:00 / 晚间 20:00–22:00）只检查一次，两个时段各用 `courtyard_sushi_noon_dt` / `courtyard_sushi_evening_dt`。领到且寿司消失 → 「庭院寿司已领取，本时段（…）处理完成。」，记；`goto_page(page_main)` 成功后等 `SUSHI_FIND_WAIT`（5 秒）仍没有寿司 → 「未发现可领取寿司，本时段（…）检查完成。」，也记；`goto_page` 返回 `False`、领完寿司仍在、异常 → 不记。时段外不执行（`_current_sushi_period` 没动）。
- **调度**：删除 `_sushi_retry_at`、`SUSHI_RETRY` 和 `plan_next_dt` 里的 +10 分钟分支，`plan_next_dt` 只剩原来的正常排期：12 点前排当天 12:00、12–20 点排 20:00、20 点后排次日 12:00（`custom_next_run`，随机延迟与时间计算行为不变）。没有改通用调度器、`failure_interval`。
- **邮件**（`run_pickup_email`）：入口加 `today_is_done('pickup_email')`，当天已处理直接跳过（不进主页、不点击），次日重新收；其余流程、开关、异常处理不变。
- **测试**：`tests/test_daily_trifles.py` 吉闻 / 寿司 / 调度 / 邮件相关改为新口径，并新增行为用例——吉闻：有奖励记 + 「已领取」日志、无奖励记 + 「未发现」日志、同日跳过、次日恢复、页面没进 / 异常 / 奖励关不掉不记；寿司：中午有 / 无寿司记中午、中午记录不影响晚间、同时段第二次跳过且不截图、次日恢复、页面没进 / 异常 / 领完仍在不记、`_sushi_retry_at` 与 `SUSHI_RETRY` 已删、真实 `plan_next_dt` 在 9:00 / 12:05 / 13:50 / 20:30 走原排期且不调 `set_next_run`；邮件：当天第二次跳过、次日恢复。**按新口径修订的旧断言**：吉闻「无奖励 / 奖励一直不出现 / 友情点模板不消失」原断言「不记完成」改为「记当天已处理」；寿司「没找到寿司有界且不记」改为「记本时段」；删除 `test_retry_only_inside_an_unfinished_period` 与两个 `plan_next_dt` 重试用例（被真实排期用例替换）。异常保护类断言（有界、不记）一条未删。
- **未做 / 限制**：没上真机；没改每日召唤、寮祈愿 / 捐赠、商店签到 / 买体力、庭院事务、点击策略与 L1 / L2；没有批量给用户配置写「今天已完成」，新记录靠正常运行产生。

### 4.140 福利道馆模式（Dokan 内的受开关保护的新流程）

2026-10-26。未提交（在工作区）。**Level A/B（离线假游戏 / 虚拟时钟测试）PASS，不是真实 MuMu 实测；模板匹配 / OCR / 滑动 / 游戏时序全部待真机验收（Level C）。**

- **配置**：`DokanConfig.welfare_mode`（默认关）、`welfare_min_people`（默认 100，严格整数 ≥ 1，保存失败保留原值，不重置整组）；中英文说明、`config/template.json` 已补。关闭时 `ScriptTask.run` 不进入新流程，普通道馆的系数 / 刷新上限 / 馆主次数 / `next_run` 排期不变（`tests/test_dokan_normal_mode.py` 固定了这些行为）。
- **流程**（`tasks/Dokan/welfare.py`，`run()` 里 `welfare_mode` 为真时整体交给 `WelfareDokan`，结束后按「道馆已开启」安排下次）：开始前检查 `handle_error`（`app_stop` / `app_start` 的前置）→ 读剩余机会（0 正常结束、1 一馆、2 两馆，**未知 / 已有进行中的馆转人工**）→ **我方道馆建立检查（§4.151，一次运行只一次）**→ 第一次找馆前一键预设一次（阵容 → 预设：有确认框就确认，没有确认框则实际点 2～4 次视为操作完成，§4.150 → 返回）→ 严格找「鑫」馆 → 开启 → 集结（§4.152：只有「集结页」证据才保活公共卡死计时）→ 准备页点准备后**紧接** `app_stop` → 两次查询确认进程不存在才开始 600 秒 → `app_start` + 登录服务 → 地图上用「集」字定位并点徽章进馆 → 放弃（区分「放弃 / 继续」与「再战道馆 / 保留赏金」两个投票阶段，只点「再战道馆」）→ 选择成功后等 120 秒（游戏开着）→ 第二馆（不再预设）→ 最后一馆无投票、不等 120 秒 → 读最终剩余机会收尾：**必须来自识别（有限重试），读不到转人工，不推算、不写次数、不按正常完成收尾**；读到 0 正常结束，读到仍有机会就如实返回、不开第三馆。
- **找馆**：只在右侧候选列表识别「鑫」（`match_all_any`），按纵坐标从上到下逐个检查；每次点击前先让上一个详情卡片消失，点击后等详情和「防守人数」，连续两次读到同一个数才采信；人数不足 / 读不到 / 不可挑战都跳过；以卡片指纹（灰度小图）去重和重新定位，不用旧坐标；滑动走 `BaseTask.swipe` → `swipe_trajectory`，福利专用资源 `S_DOKAN_WELFARE_LIST_UP`（起终点都在列表内、竖直向上）；每次滑动后用 `wait_for_changed_and_stable` 并按真实契约分类：变化且稳定 → 重新识别候选；**明确稳定且没变化 → 计入「可能到底」，连续 2 次才算到底（2026-10-28 起「是否推进」的判据改为最终落点相对滑动前的行覆盖，见 §4.148）**；变化了但一直没稳定 / 只有未稳定的噪声 → 不计入到底，有界重新观察（`SWIPE_SETTLE_TRIES` 次、每次最多 `SWIPE_SETTLE_TIMEOUT` 秒，期间不再滑动），稳定后按相对滑动前是否真的变了归类，仍不稳定转人工；截图 / 设备异常原样上抛；到底后刷新再从头；不设刷新次数上限、不降门槛、不做系数兜底；刷新确认框出不来（游戏限制）转人工。
- **点准备后的时序**：识别到 `I_PREPARE_HIGHLIGHT` → `execute_single_click` → `device.app_stop()`，点击接口返回后立即关闭，中间没有截图、sleep，也不进通用战斗循环（离线测试用事件序断言紧邻，验证这个策略实际生效）。**目标是「点击返回后立即关闭」，不承诺也不要求「关闭前绝不进入战斗」**——游戏何时开始战斗不受本程序控制，真机上是否来得及要实测。
- **关闭确认**：新增 `AppControl.app_process_exists`（`pidof`，查询失败**抛异常**，不像 `app_is_alive` 吞成 False）；两次连续确认不存在才计时，异常 / 仍存在不计时，超时转人工且不启动游戏。
- **等待与活跃时长**：等待分段（≤ 1 秒一段，进程被终止即停，停止时没有任何收尾去启动游戏）；600 秒用 `FatigueManager.suspend_active()`（只暂停活跃计时，不改休息状态、不产生恢复）并把时长记到 `config.__dict__['excluded_active_seconds']`，`Script._add_active_seconds` 从防沉迷当日活跃时长里扣除（两处都处理）；120 秒游戏开着，计入真实活跃时长。
- **异常**：开过馆之后出现自动恢复类异常（卡死 / 页面未知等）直接转 `RequestHumanTakeover`（保留原异常链），避免公共 Restart 从头重跑；开馆前的异常保持原行为。重跑时若地图上已有进行中的馆也转人工。
- **资源核对**：`find_xin` / `dokan_team` / `dokan_team_preset` / `dokan_again_enter` 均已登记并生成；旧废稿 `res_dokan_enter_again.png` 没有登记，也没有引用。`dokan_again_enter`（「集」字）整屏搜索会命中底栏「道馆突破集结中」，已把 `roiBack` 改为 `(0,90,1280,520)`（排除顶栏和底栏），并要求恰好 1 个匹配、且 `FOUND_DOKAN` 横幅在场；徽章位置按 2026-10-25 整屏截图量得「集」字中心右 84、上 100 的固定偏移（`BADGE_OFFSET`）。右上角「再战道馆」就是已有的 `I_RYOU_DOKAN_FAILED_VOTE_BATTLE_AGAIN`，没有新建第二个再战资源。
- **登记册**：`docs/L2_CALLSITE_REGISTER.md` 已用工具重新生成（总数 1106 → 1124，新增 18 个规则分类点，3 个 `execute_single_click`）；`tests/test_l2_c0_registry.py` / `test_l1_l2_integration.py` / `test_l1_stage3b_global_guard.py` 的期望数字随之更新（原因：新增福利点击点；断言本身没有放宽）。
- **测试**：新增 `tests/test_dokan_welfare.py` 49 项（离线假游戏 + 虚拟时钟：测试替身 `World` 驱动真实 `WelfareDokan`，不是真实 MuMu / 游戏）、`tests/test_dokan_normal_mode.py` 22 项（普通模式特征、福利入口、配置、活跃时长）；变异验证 8 条（插入截图、`<=`、不隐藏详情、等待计入活跃、点保留赏金、查询异常当已关闭、到底判定、不去重）均有测试变红。**2026-10-26 收尾修正**（用户架构审查三处）：① 最终次数读不到不再推算（`return remaining` 删除）；② `_swipe_list` 不再只看 `changed`，按稳定性分类（见上）；③ `_vote_again` 不再认「任意区域变化 / 按钮消失」。新增 16 项反例测试（`tests/test_dokan_welfare.py` 49 → 65）并另做 3 条变异（投票接受任意变化 / 超时不稳定当到底 / 最终次数读不到按 0 收尾）均变红。顺带修了 `_wait` 的浮点残差（虚拟时钟下 `now` 很大时极小剩余不前进会空转）。公共代码没有变化（只改 `tasks/Dokan/welfare.py`；`wait_for_changed_and_stable` / `FrameWaitResult` 语义未动）。
- **未完成 / 缺证据**（不盲点，到达前安全停止）：① 预设点「确定」后没有可识别的完成提示，只能确认确认框消失且仍在阵容页；② **投票选「再战道馆」后缺本方选中后的整屏截图**（资源里只有未选中的「再战道馆」/「保留赏金」模板）。现在的成功依据（缺一不可）：点击真的发出（限流没发出的不算，最多重试 3 次）；只看按钮自己的框（点击时的匹配框，不含票数 / 倒计时）相对点击前**变化并稳定**，且最后稳定的一帧仍与点击前不同；稳定那帧仍在投票界面。动画（不稳定）、只有票数变化、按钮短暂漏识别后恢复原样、无关页面切换、按钮消失都**不算**成功；只点一次，确认不了就转人工、不启动 120 秒等待、不找第二馆。**这是推断出的依据，不是已验证的选中样式**：需要补一张「点再战道馆后、投票阶段的整屏截图」才能改用明确的选中模板；在此之前这一步的真机行为不能当作已完成；③ 重启后地图上「集结」丝带是否还在、徽章偏移是否稳定；④ 候选卡片被点击后是否有高亮会影响指纹去重（只会重复检查，不会漏）；⑤ 找馆页是否显示「今日可挑战机会」（截图显示在底部中央，ROI 覆盖）。

### 4.142 福利道馆：图像匹配结果格式修复（§4.140 补记）

2026-10-26。未提交（在工作区）。**Level A/B（离线）PASS；真机只证明了这一处格式错误，其余流程仍待实测。**

- **首次实测（2026-10-26 20:28，oas2）暴露的缺陷**：点阵容 / 一键预设 / 确认后第一次处理「鑫」候选时 `ValueError: too many values to unpack (expected 4)`，尚未开馆。根因：`RuleImage.match_all_any()` 的真实返回是 `[(score, x, y, w, h), ...]`（`module/atom/image.py` 把服务端 `matches` 逐项转 tuple），`welfare.py` 按四项坐标拆包，并按 `item[1]`（五项里是 x）排序；返回本馆处同样 `x, y, w, h = matches[0]`。离线测试的假游戏也返回四项坐标，与真实接口不符，所以没抓到。修复：新增模块内函数 `match_boxes(rule, matches)`，是唯一的「外部五项 → 内部四项 `(x, y, w, h)`」转换点（置信度在此丢弃，格式不符抛带规则名的 `ValueError`，不静默截取）；`_candidates()`（按 y 从上到下排序、指纹、`candidate["box"]`、`ClickBounds`）和 `_restart_and_return()`（唯一返回标志、徽章偏移）都经它。没动公共图像接口、模板阈值、业务规则。福利模块之外的 `match_all_any` 消费者（Chess、KekkaiUtilize 选中锚点）按五项解包，GeneralInvite 只取 `len()`，只读核对，无问题。测试：`tests/test_dokan_welfare.py` 假游戏改为五项（score / x 与行号不单调、整体按分数倒序返回），新增 `MatchContractTest` 9 项（实测原值、从上到下排序、点击落在四项框内、重定位、返回本馆唯一 / 多个 / 无 / 四项报错、空列表与边缘、格式错误、真实 `RuleImage` 包装层 + 假 RPC 客户端）；修复前 57 项报错 / 4 项失败。
- **未验证**：预设日志 `preset applied once` 只说明点击序列执行完，不代表预设效果已验证；候选点击、人数 OCR、滑动、开馆、返回本馆等仍待真机。

### 4.143 SwitchSoul 按名称找分组 / 找队伍：有界搜索 + 精确匹配 + 稳定等待

2026-10-27。未提交（在工作区）。**Level A/B（离线）PASS；真机未验证。**

- **（首版描述；分组选中确认、错误分类、队伍翻页步幅、预算已在 §4.144 修订，以 §4.144 为准）** **问题**：按名称切换预设（`SwitchSoul.switch_soul_by_name`，ActivityShikigami / AreaBoss / BondlingFairyland / DemonEncounter / DemonRetreat 在用）的找分组、找队伍是旧写法——回顶靠「两次 OCR 文字相同」加固定 `sleep`，找目标是 `while 1` 无上限滑动，点击用 `ocr_appear_click`（`filter` 子串 + 单字回退）而不是搜索时的精确相等，队伍滑动资源只有约 50px。目标不存在会无限滑；「魂土」可能点到「魂土备用」；OCR 读空两次就被当作到顶。**新流程**（只动按名称路径，数字模式一行没改）：分组回顶 → 从上到下找 → 点击前重新定位 → 点击并确认「分组行 + 中央队伍列表」变化并稳定 → 队伍回顶 → 找 → 重新定位 → 原有的预设切换确认循环（4 次队伍点击、预设确认、契灵替换、各超时全部保留）。**边界**：回顶 / 翻页每次都是 `BaseTask.swipe(RuleSwipe)`（端点采样 + 轨迹模型原样使用，不传 interval）之后用 `wait_for_changed_and_stable`（0.02 / 0.01 / 连续 2 帧，4 秒）等稳定；`success`（变化且稳定）= 滑动生效；稳定但没变化 = 静止（到边界的证据）；变化但不稳定 = 有界重观察，仍不稳定就报错（不当作到边界）；`swipe()` 没发出（返回 False）直接报错，不算一次滑动。到顶 / 到底都要「连续 2 次静止」，到顶那一帧还必须读到有效文字；OCR 读 0 行时同一次读取最多换帧重读 3 次，仍为空报错，不判到顶 / 到底 / 目标不存在。上限（故障边界，不是游戏支持数量）：回顶分组 12 次 / 队伍 20 次，翻页分组 20 屏 / 队伍 30 屏，每个阶段总时限 150 秒；另有「翻页后回到之前出现过的内容」的循环检测。**精确匹配**：首尾去空白后严格相等（`exact_matches`），不去符号 / 内部空格、不做单字回退；同屏多个精确同名直接报歧义，不点；文字框被列表上下沿裁切（离可视区边缘 <3px）的命中本屏不点，翻页后再看（已确认到底时才接受）。只检查「首次命中的那一屏」是否重名，不同屏同名不做全列表唯一性检查（要扫完整个列表，成本高且没有可靠依据）。点击前连续两帧都只命中一个、y 偏差 ≤6px 才点（列表还在滚就不点）；分组点击后无可见变化时补点一次，仍无变化只警告继续（可能本来就是当前分组），之后队伍列表必须读得到文字。失败一律抛 `SwitchSoulNameError`（继承 `GamePageUnknownError`，消息带「分组 / 队伍名 + 阶段」，沿用「通知 + 重启游戏 + 稍后重试」，不会退出进程），不回退到别的预设，也不写成功日志。**资源**：新增 OCR 专用 swipe 四个 `ss_name_group_to_top` / `ss_name_group_next` / `ss_name_team_to_top` / `ss_name_team_next`（源 JSON → 用 `AssetsExtractor` 生成 `assets.py`，只多出这四条）；分组 约 260～280px、队伍 约 250px（旧队伍资源只有约 50px），起终点都落在对应列表内（分组在右侧列表，队伍在中央列表 x≈640～760，避开左侧式神列表和底部新增按钮）；旧四个 swipe 资源与两个 OCR 区域（`O_SS_GROUP_NAME` roi `1087,91,155,566`、`O_SS_TEAM_NAME` roi `573,140,277,481`）原样未改——没有真机截图 / OCR 日志可核对，不盲目改区域；等级、御魂数字等噪声靠精确相等排除。**点击**：`ocr_appear_click_by_rule` 改名为 `_click_line`（仍是唯一的 `execute_single_click`：y 取命中行、给了预设按钮列时 x 取按钮列，两轴各采样一次），分组点击也走它；新增 `_LineTarget` 包装命中行，不修改共享的 OCR 资源（不再临时改 `keyword`）。
- **测试**：新增 `tests/test_switch_soul_name_search.py` 37 项——真实 `RuleOcr.detect_and_ocr`（只替换模型，返回真实 `BoxedResult`）+ 真实 `BaseTask.swipe` / `sample_endpoints`（只替换最底层 `swipe_trajectory`，按手指方向移动虚拟列表）+ 真实 `wait_for_changed_and_stable` / 帧差（按虚拟列表渲染的真实 ndarray）+ 虚拟时钟 + 截图次数失控保护；覆盖当前屏命中、第 8 组、滚动后才出现的队伍、从列表中间开始回顶、14 队逐个可达（边缘队伍不漏）、动画未停、目标不存在、阶段总时限、OCR 读空 / 偶发漏识别、相近名称 / 子串 / 单字碎片 / 首尾空白、同屏重名、变化但不稳定、滑动未发出 / 完全无效 / 丢一次、目标漂移后用新坐标点击、持续滚动不盲点、分组点击后队伍列表延迟刷新、点击落点（分组在命中行内、队伍在预设按钮列且行号正确）、新 swipe 资源方向与落点范围、旧资源和 OCR 区域未改。变异 12 条各有测试变红（其中 2 条首轮漏网，补了「OCR 在到顶 / 查找阶段才读空」用例后抓住）。既有测试的调整（原因：搜索阶段被新流程取代）：`test_switch_soul_replace_dialog` 的按名称沙盒把 6 个搜索阶段方法替身成固定截图数、把队伍点击换成 `_click_team_by_name`，确认循环的全部用例与断言不变；`test_switch_soul_numeric_v1` / `test_switch_soul_group_top_v2` 里冻结旧按名称流程的「固定 sleep 与 4 个旧 swipe」断言改为冻结仍成立的部分（4 次队伍点击、1.5 秒间隔、无 policy、无 sleep、旧四个资源仍在、数字模式滑顶仍只用 `S_SS_GROUP_SWIPE_UP`）；`test_l1_click_pipeline` 的守卫与 case 23 从 `ocr_appear_click_by_rule` 指向 `_click_line`，断言不变；`test_l2_c0_registry` 钉住数字 1124 → 1123（去掉 `ocr_appear_click(O_SS_GROUP_NAME)` 一点）、rule 925 → 924、KEEP_IMMEDIATE 635 → 634，登记册已重新生成。
- **未验证（全部待真机）**：分组 / 队伍的 OCR 识别率与 OCR 区域是否会带进等级、御魂数字等噪声；新 swipe 资源在真机上的实际滚动量（分组一屏 8 个、队伍一屏约 3.4 个，翻页位移是否留有足够重叠、是否有惯性滑过头）；分组点击后中央列表刷新是否会比「连续 2 帧安静」更慢（更慢会被后面的回顶滑动再次吸收，但没实测）；点击预设按钮时 x 取按钮列、y 取队伍名所在行是否对应同一行（沿用旧口径，未变）；最终装备的预设效果。离线通过只说明定位与确认流程的逻辑。

### 4.144 SwitchSoul 按名称预设收尾：分组选中确认 / 错误分类 / 队伍向后翻页小步幅（§4.143 补记）

2026-10-27。未提交（在工作区）。**Level A/B（离线）PASS；真机未验证。**

- **① 分组选中确认**（`_name_select_group` 整段重写）：选中的依据是「选中标志只有一个且落在目标行」这个**状态证据**，用数字模式已有的选中高亮模板（金色竖条，`I_SOU_CHECK_GROUP_2`，`copy.copy` 后临时放宽到整条左边缘 x 1080~1120，随皮肤替换；标志中心与目标行中心 y 相差 ≤25px，行距约 66px），**不再**把「区域变化」或「队伍列表读得到文字」当证据。点击前标志已在目标行 = 本来就是目标分组，不点击；否则点击（最多 2 次，每次点击前重新定位）→ 等分组区域稳定 → 再查标志；始终确认不了（标志在别的行 / 没有标志 / 多个标志）→ 转人工，不继续找队伍。**分组确认和中央队伍列表就绪分别检查**：确认选中之后，先前不是目标分组时中央队伍列表必须相对点击前「变化并稳定」（最多 3 轮观察，仍无变化 = 可能读到旧分组的队伍 → 转人工），本来就是目标分组时只要求稳定，最后队伍列表还要读得到文字；成功日志（`selection confirmed`）只在两项都满足后写。**缺的画面**：这些模板来自数字模式的旧页面，当前页面（一屏 8 个分组）是否能识别没有实证——需要**选中某个分组时右侧分组列表的整屏截图**；识别不到时按本规则安全停止（报错信息里写明缺什么），不会继续操作旧分组。**② 错误分类**（只在 SwitchSoul 局部，公共异常与调度器未改）：`SwitchSoulNameError(RequestHumanTakeover)` = 确定需要人工——空名称、完整搜索（确认的顶部到确认的底部、OCR 有效）后目标不存在、同屏精确同名、无法确认分组选中、选中后中央列表一直不变；走 `Script._handle_task_exception` 里已有的人工处理分支（通知 + 进程退出），**不安排 Restart**；`SwitchSoulPageError(GamePageUnknownError)` = 临时识别 / 页面问题——OCR 连续读空、列表不稳定、滑动没发出、阶段超时、搜索达到保护上限但没有可靠确认到底、翻页后回到旧内容、点击前定位不稳——沿用「通知 + 重启 + 稍后重试」。**「到底」新增证据要求**：除连续 2 次静止 + 有效 OCR 外，还要滑动真的生效过（回顶或翻页里出现过 moved），或最后一行下面空着一整行（列表本来就没满一屏）；否则按页面问题处理，不会把「滑动全部无效」当作「名称不存在」。已知边界：恰好一屏放满（如正好 8 个分组）且目标不存在时无法区分「列表不会动」和「滑动无效」，按页面问题处理（会重启并重试），不是人工。设备类异常（截图 / 控制失败）不经过这两个类，保持原类型。**③ 队伍向后翻页改小步幅**：`ss_name_team_next` 基准手指位移约 250px → 约 135px（front `680,430,80,20` → back `680,295,80,20`；采样后约 75～190px，均值约 135；起终点 y 约 266～478、x 约 682～756，都在中央队伍列表内、避开左侧式神列表和底部按钮），用户页面一行约 150px，所以每次最多翻约一行，边缘队伍下一屏必然完整出现。队伍回顶（约 250px）、分组两个资源、数字模式四个旧资源不变。**预算同步放大**（都是故障边界）：队伍翻页上限 30 → 60 屏、回顶 20 → 30 次、阶段时限 150 → 300 秒（`timeout_scale=2.0`；依据：平均每次约 0.9 行，60 屏约能覆盖 ≥ 40 个队伍；每屏约 3~5 秒）；分组不变（20 屏 / 12 次 / 150 秒）。达到上限只报页面问题，不写成名称不存在。循环检测对步幅变小的审查：步幅小于一行时相邻两屏文字常常完全相同，`trail` 把相邻相同的屏折叠，只有与更早的**不同**内容重复才报循环，不会误报。
- **测试**：`tests/test_switch_soul_name_search.py` 37 → 61 项：假世界新增选中标志（贴项目里真实的 `ss_sou_check_group_2.png`）、点击无效 / 无关动画 / 列表不刷新 / 无标志 / 双标志开关，用真实 `RuleImage.match_all_any`（只换 RPC 客户端，客户端用 cv2 做真实模板匹配并返回真实 `[score, x, y, w, h]` 协议）识别；新增 `GroupConfirmationTest`（本来就是目标、点击无效、两组同名队伍、列表延迟刷新、无关动画、列表不变、无标志、双标志、选中分组在可视区外、成功日志顺序）、`ErrorClassificationTest`（五类人工错误 / 三类页面错误的类型、设备异常原样、真实 `Script._handle_task_exception` 对两类的处理：人工类 `SystemExit` 且不调 `task_call`、页面类 `task_call("Restart")`，原异常对象传到 `exception_handler`）、`SmallStepSearchTest`（相邻屏重叠、下沿裁切后找到、大量相同相邻屏不误报循环、40 队长列表预算内找到、长列表确认不存在、长列表回顶预算、预算常量、仍走 `swipe_trajectory`），并更新几何断言（新步幅 75～190、均值 120～150，回顶更大）。旧用例「无变化后警告继续」换成「已确认本来就是目标分组时不点击」。变异 14 条各有测试变红（选中不看标志 / 任何标志都算目标 / 不检查列表就绪 / 不要求列表变化 / 多标志不算歧义 / 确认不存在与保护上限的错误类别互换 / 滑动全无效也算到底 / 相邻相同屏误报循环 / 队伍翻页退回大步幅 / 预算不放大或过小 / 名称错误走重启类 / 同屏重名走页面错误）。
- **未验证（全部待真机）**：分组选中高亮（`I_SOU_CHECK_GROUP_*`）在当前页面能否识别、y 对齐是否准确（缺整屏截图，见上）；队伍翻页的实际滚动量（约 135px 基准只是手指位移，不是已验证的滚动距离）；OCR 识别率与区域；队伍行与预设按钮的对应关系；最终装备的预设效果。名称错误现在会让该实例进程以「人工接管」退出（原先是无限滑动），真机要确认通知内容和你期望的处理方式一致。

### 4.145 契灵队长创建房间后不再空等 15 秒私人设置

2026-10-27。未提交（在工作区）。**Level A/B（离线）PASS；真机未验证。**

- **根因（日志 + 源码确认）**：10-27 oas2 13:16:53 点击 `BALL_CREATE_TEAM` → 13:16:53 `Ensure private` → 13:17:08 `Ensure private timeout` → 13:17:08 `Ensure enter invite page`，房间早已打开。旧 `create_bond_team`（`run_leader` 里的嵌套函数）点击创建后立刻用**点击前的旧截图**判断 `I_GI_IN_ROOM`，看不到就无条件 `ensure_private()`；后者只认私人 / 公开设置标志、没有「已经在房间」的退出分支，必然等满 15 秒，返回值（False）在契灵调用处被忽略，之后下一轮循环才看到房间。10-22 ~ 10-27 的实例日志里 37 次点击创建，36 次紧接着 `Ensure private timeout`，**没有一次点到过私人设置标志**——契灵的创建按钮直接进房间，私人设置页（`GR_CREATE_ROOM` 那个创建对话框的私人勾选）在这条路径上不出现。**修复**（`tasks/BondlingFairyland/script_task.py`）：嵌套函数提取为方法 `create_bond_team()`（行为不变的部分原样保留：房间 / 选择共鸣 / 求援 / `BondlingNumberMax`），点击创建后改为：`appear_then_click` 返回 True（确实点出去）才进入有界观察 `_observe_after_create()`（窗口 `CREATE_OBSERVE_TIMEOUT=8` 秒，故障边界，不是固定等待），**每一轮都用新截图**：① 房间出现 → 立刻返回交接邀请，日志明确写「private state NOT verified」；② 创建设置页（四个私人 / 公开标志任一）→ 走原有 `ensure_private`，看到私人标志才记「private setting verified」；③ 窗口内都不是 → `pending`，回到外层循环，过渡页上不会重复点创建；点击没发出（限流 / 目标消失）不进入观察。同一次创建最多点 `CREATE_MAX_ATTEMPTS=3` 次，再不行抛 `GamePageUnknownError`（明确原因），不默认创建成功。**公共改动**（`GeneralRoom.ensure_private`）：新增可选参数 `exit_when=None`，每次新截图后先检查，出现就立刻返回 False（仅表示「没有确认私人」）；默认行为与原来逐字一致，其它 7 个调用者（EternitySea / EvoZone / Exploration / FallenSun / Orochi / OtherWorldTwilight / TrueOrochi）一律没传。`ensure_private` 返回 False 时契灵调用处不再无条件忽略：房间已出现按「房间 / 私人未验证」继续，否则仍停在设置页 = 没能确认私人，抛 `GamePageUnknownError`，不进入邀请。**两个事实分开**：A「已进房间，不必再等创建设置页」≠ B「房间私人状态已验证」——源码和资源里没有「契灵创建入口固定为私人」的依据，所以进房间时日志只写 NOT verified；私人设置页真的出现并确认了才写 verified。**顺带发现（未改）**：`BaseTask.appear(target, interval=1)` 与 `appear_then_click(target, interval=2)` 对同一目标交替使用时，`interval_timer` 按 limit 不同每次换一个未启动的 Timer，实际不限流（原 `create_bond_team` 的 2 秒点击间隔因此形同虚设）；本修复靠「点击后观察窗口内不再点击」避免重复创建，没有改公共 `appear`。
- **测试**：新增 `tests/test_bondling_create_team.py` 20 项——虚拟世界（每帧可见标志由阶段决定，`interval` 门控与真实 `BaseTask` 一样按目标名换 Timer）驱动真实 `ScriptTask.create_bond_team` / `_observe_after_create` / `run_leader` 和真实 `GeneralRoom.ensure_private`，只替换截图 / 识别 / 时钟：房间点击后立即出现（虚拟耗时 < 5 秒，`ensure_private` 未被调用；同一世界上特征化旧逻辑耗时 ≥ 15 秒）、点击后用新截图判断、过渡 5 帧后出现房间且不重复点击、过渡超过窗口也不重复点击、进房间日志是 NOT verified 而不是 verified、创建设置页仍走原私人切换（私人开关被真实点击）、已是私人不点、设置页中途进房间不等满 15 秒且不谎称私人、私人设置失败抛 `GamePageUnknownError`（等满 15 秒预算）、创建点击无效最多 3 次后失败、限流的点击不进入观察、未知页面不当作成功且设备层 `GameStuckError` 原样传播、观察中的设备异常保持类型、真实 `run_leader` 在房间出现后立刻交给邀请流程（`run_invite(is_first=True)` 一次、总耗时 < 6 秒）且创建失败不会走到邀请、公共 `ensure_private` 默认行为不变（看到私人 True、在房间也只等到超时 False）、新参数默认 None、只有契灵传了 `exit_when`、`run_leader` 不再含嵌套闭包。变异 10 条各有测试变红（回到旧逻辑 / 忽略点击是否发出 / 观察不识别房间 / 不传退出条件 / 进房间谎称已验证 / 私人失败当成功 / 重试不设上限 / 窗口为零 / 观察不重新截图 / 公共退出条件被忽略）。登记册重新生成：总数不变（1123），契灵 3 个点击点的函数名由 `run_leader` 变为 `create_bond_team`。
- **未验证（全部待真机）**：房间标志 `I_GI_IN_ROOM` 在点击后的真实出现时间与 8 秒窗口是否够；契灵创建后房间是否默认私人（没有证据，不宣称）；其它情形下是否真的会出现创建设置页；邀请本身的耗时（截图、识别、好友列表加载）仍是正常耗时。预期收益只是「消除已进房后的无效等待」，不承诺邀请总耗时。

### 4.146 契灵组队：游戏锁队状态与通用战斗 `lock_team_enable` 的衔接

2026-10-27。未提交（在工作区）。**Level A/B（离线）PASS；真机未验证。**

- **三件事要分开看**：① 游戏内「锁定队伍」状态（锁定 / 未锁定图标 `I_BALL_LOCK` / `I_BF_LOCK` / `I_BALL_UNLOCK` / `I_BF_UNLOCK`）；② 通用战斗的配置标志 `lock_team_enable`（True 时 `_prepare_click_ready` 进准备页先等约 3 秒才允许点准备，False 时立即判断）；③ 默认邀请 / 接受邀请（`check_then_accept`，不设置任何锁队标志，也不是锁队证据）。**源码确认的不一致**：队长在 `run_catch` / `run_search` 开头调用 `lock_team()`（看到锁定图标才返回），队员原来不经过任何锁队检查；`BattleConfig` 隐藏了 `lock_team_enable`，继承默认 False；队长 2 处、队员 2 处 `run_general_battle` 直接传任务原 `battle_config`，所以游戏已锁队、自动准备时，通用战斗仍按 False 立即补点准备。实际误点发生时的画面没有捕获，不宣称这是误点的唯一原因。**修复**（只在契灵，`tasks/BondlingFairyland/script_task.py`）：新增 `team_locked`（本账号游戏内锁队已被识别确认，只在看到锁定图标时置位）、`team_battle_config()`（基于任务 `battle_config` 的 `model_copy` 副本，只设置 `lock_team_enable=team_locked`，其它字段原样保留，不改共享对象、不写回 JSON、无新用户开关）；队长 / 队员共 4 个战斗入口全部改用它；`lock_team()` 返回前置位 `team_locked`；队员 `run_member` 开头新增 `confirm_team_locked()`——**只观察、不点击**，`LOCK_CONFIRM_TIMEOUT=6` 秒有界窗口内看到锁定图标才确认，看到「未锁定」图标或什么都看不到都不确认（`lock_team_enable` 保持 False = 原行为），本账号之前已锁过（handoff 先当队长）就不重复观察。**队长 / 队员分别**：队长靠自己的 `lock_team()`；队员不能假定队长锁了就等于自己锁了，也不能用默认邀请代替证明，必须自己在页面上看到锁定图标；队员侧不替用户点锁定（原来队员从不锁队，擅自锁会改变游戏设置）。已锁队时通用战斗沿用已有的约 3 秒自动准备等待，超时后仍点准备（兜底不变）；ALONE 单人路径（`run_catch` 里传 `battle_config` 的那一处）不在本轮范围，未改。**缺口**：队员页面如果没有锁队图标（例如 handoff1 回到契灵主界面后），就确认不了，按未锁定处理；是否需要在别的页面补一次观察，要真机看队员页面实际能看到哪个图标。
- **测试**：新增 `tests/test_bondling_team_lock.py` 17 项：驱动真实 `lock_team` / `confirm_team_locked` / `team_battle_config` / `run_leader` / `run_member`，并把生成的配置交给真实 `GeneralBattle._build_context` / `_prepare_click_ready` / `_handle_prepare`（虚拟时钟）——队长首次邀请 + 后续战斗两个入口都拿到已锁队副本（原配置对象不变，其它字段相等）、没有确认锁队时标志为 False（不是写死 True）、队员房间内 + 队长秒开两个入口、未锁定 / 无图标不确认且不点击、观察窗口有界且能等晚出现的图标、默认邀请被接受不置位、队长锁队不代替队员自己观察、先当过队长的账号不重复观察、已锁队准备页先等约 3 秒仍会点准备、等待期间自动进战斗则不点、未确认时立即点（原行为）、非契灵配置的准备行为不变、只有契灵使用 `team_battle_config` 且四个入口全部使用、公共邀请 / 战斗代码不设置该标志。变异 10 条各有测试变红。`test_bondling_fairyland_member_limit_count.py` 的夹具调整：`battle_config` 由 `object()` 改为真实 `BattleConfig()`，并把 `confirm_team_locked` 替身为未确认（该文件只关心次数收尾），断言不变。
- **未验证（全部待真机）**：已锁队 + 默认邀请后自动准备时，是否还会发生误点准备（实际误点的画面没捕获）；队员页面能否看到锁定图标（`I_BF_LOCK` / `I_BALL_LOCK` 在队员所处页面是否可见、6 秒窗口够不够）；约 3 秒自动准备等待对队员 / 队长真实流程的影响；游戏确实没有自动准备时超时后点准备的兜底。

### 4.147 悬赏封印：适配新详情界面（详情判定 / 整行 OCR / 取消追踪出口 / 失败不再按完成收尾）

2026-10-28。未提交（在工作区）。**Level A/B（离线）PASS；真机未验证。**

- **根因（日志 + 用户标注抓图确认）**：10-28 15:49 oas1 / oas2 的 `WantedQuests`：`pre_work` 正常、列表 OCR 读到 `0/8`、点了列表 4 次，但旧 `I_TRACE_TRUE`（列表旁小图标）在新版详情里不存在，`open_wq_info` 一直等不到 → 滑动列表 4 次 → `No unfinished wanted quest after scrolling 4 times, exit` → `next_run` 排到明天，任务被当成「已完成」。新版详情是全屏卷轴，右下角「取消追踪 / 追踪」菱形按钮、右上角红叉；用用户抓图离线匹配：新 `I_TRACE_TRUE` 在已追踪详情 0.947 / 未追踪详情 0.151，`I_TRACE_FALSE` 反之 0.935 / 0.258，互不命中；详情盖住列表，`I_CHECK_EXPLORATION` 在详情上 0.009、在列表上 0.92，`I_UI_BACK_RED` 在详情上 0.918（可关详情）。**仍是推断**：点击列表进度文字确实打开了详情（日志里没有失败截图，只能由「4 次点击后旧模板不命中、新模板在新版详情命中」推断，点击位置没有证据显示有问题，故没改坐标）。
- **资源**：用户用标注器更新的 `wq/ocr.json` / `image.json` / PNG / `assets.py` 原样保留。`wq_info_1~4` 现在是整行「类型 + 目的地 + 数量」（`Single` 模式，`RuleOcr.ocr` 返回单个字符串，失败 `""`），旧 `wq_type_1~4` 保留但新流程不再读。**注意**：`I_TRACE_TRUE` 与主界面 `I_TRACE_DISABLE`（一键取消追踪）外观几乎一致（模板互匹 0.95），所以 `I_TRACE_TRUE` 只能在探索页的详情场景使用，不能拿去判断主界面。
- **整行解析**：`parse_wq_row_text` 按开头类型词（`式神碎片` / 旧 `式神` / `挑战` → 内部「挑战」，`探索` / `秘闻` / `妖气`）+ `数量:n` 解析，中间作 dest；容忍空格、全角括号 / 冒号、末尾残留右括号 / 引号；类型未知、dest 空、数量缺失 / 0 / 非数字一律返回 None，不猜。`build_wq_info(index, info_rule, goto_btn_rule, num_want)` 返回 `WQRowReading`，状态 `ok / filtered / failed / absent`：规则过滤（类型不在优先级、高层秘闻、已执行过）= `filtered`，解析失败 / 有字无前往按钮 = `failed`，无字无按钮 = `absent`（推荐不足四条）。第 i 行始终绑自己的 `I_GOTO_i`。高层秘闻的 `番外` 现在用 `endswith` 判断（原 `dest[-1] in {…, "番外"}` 永远不可能命中「番外」）。
- **详情打开**：`open_wq_info` 点击后用新截图确认，详情（`I_TRACE_TRUE`，或未追踪的 `I_TRACE_FALSE`）一出现立刻停止点击列表；5 秒窗口结束后补一次新截图再确认。打不开返回 False，主循环有界重试（`WQ_OPEN_MAX_RETRIES=2`，不滑列表），耗尽抛 `GameStuckError`。
- **取消追踪出口**：4 处无界 `ui_click(I_TRACE_TRUE, I_TRACE_FALSE)` 换成有界 `cancel_wq_trace`：点「取消追踪」最多 3 次（interval 1.5 秒）→ 看到未追踪标志后点红叉关详情 → 探索列表连续 2 帧才算成功；一帧消失 / 列表上没有任何取消证据 / 未知页面 / 超时 12 秒都返回 False。`skip_current_wq` 取消失败抛 `GameStuckError`，单次运行最多 12 次跳过（防取消没生效时反复打开同一悬赏）。只有「未解锁秘闻（连续 3 帧没有前往按钮）/ 忽略妖怪 / 全部推荐被规则过滤 / 没有可执行推荐」才走取消跳过。
- **异常收尾**：全部推荐识别失败（换新截图重读 3 次后仍失败）、详情打不开、取消失败都抛 `GameStuckError`，沿用调度器现有路径：保存 `log/error` 现场截图 + 推送 + `task_call('Restart')`，返回失败、`failure_record` +1，**不改 `next_run`（任务仍在待办里，重启后很快重试）**，连续失败 3 次走现有「失败三次 exit(1)」。**取舍**：这会重启游戏，但留下现场截图；只要其他行有证据完整的候选，就不要求四行全读出（可能比读失败的那行优先级低，日志有 warning）。确认没有悬赏（`is_wq_remained` 为假 / 滑动 4 次仍无未完成）仍走原正常排期。
- **保留的业务规则**：`battle_priority`（默认 挑战 > 秘闻 > 探索）、挑战券 < 5 跳过、高层秘闻过滤、忽略妖怪名单、`wq_executed_set` 重复保护、`do_num = ceil(剩余 / 推荐数量)`、探索 / 挑战 / 秘闻实际战斗与御魂预设、列表识别 `find_wq` 与奖励宝箱领取不动。
- **点击登记册**：`docs/L2_CALLSITE_REGISTER.md` 用 `--write` 重新生成（WantedQuests 41 → 39，总数 1123 → 1121，rule 924 → 922，KEEP_IMMEDIATE 634 → 632），`tests/test_l2_c0_registry.py` 钉住数字同步并在注释里写了原因。
- **测试**：新增 `tests/test_wanted_quests_detail_flow.py` 38 项，驱动真实 `ScriptTask` 方法与真实 `BaseTask.appear` / `appear_then_click` / `click`，只替换 `RuleImage.match`（按帧）/ `RuleOcr.ocr` / `detect_text` / 设备点击 / 截图 / 时钟：整行解析（四类标签、空格 / 全半角 / 错误 OCR）、第 2 行失败第 3 行仍绑第 3 个前往按钮、优先级 / 挑战券 / 高层秘闻 / 已执行 / 忽略妖怪保持、详情确认后不再点列表、`0/8` 但详情打不开 → 抛异常且不 `next_run` 不滑动、全部识别失败与全部规则过滤结果不同、取消成功 / 无效 / 一帧闪消 / 停在未追踪详情 / 列表无证据、跳过后继续下一项、正常完成仍 `next_run` 一次；离线图片匹配（`OfflineTemplateStateTest`）用用户标注器抓图验证两个状态互不命中，抓图不在时明确 skip。
- **未验证（全部待真机）**：点击列表进度文字确实打开新详情；「取消追踪」点击后详情是留下（变成「追踪」）还是直接关闭（两种分支都有处理，实际是哪种没证据）；新整行 OCR 在真实画面上的识别质量（用户标注的 ROI 未经 OCR 实测，抓图里的文字能读但没跑过真实 OCR）；`GameStuckError` 重启后重试的真实表现；`O_WQ_MONSTER_TYPE` 新 ROI 的怪物名读取。**状态区分只验证了「已追踪 / 未追踪」两张抓图，没有「取消后立刻关闭」的画面。**

### 4.148 福利道馆 D-03：列表到底后仍不断滑动（滑动「是否推进」改看最终落点）

2026-10-28。未提交（在工作区）。**D-03 离线修复完成，等待验证；福利道馆整体尚未修完。**

- **现象**：10-28 oas1 20:40:20 预设结束后连续 `dokan_welfare_list_up`，20:40:42 `GameTooManyClickError`（`log/error/oas1_1793191242911/`）。两张报错截图的右侧列表区（`LIST_BOX`）逐像素相同，停在最后一张卡片「月浔」处。**缺滑动过程中的中间帧，不能证明这次事件全部由回弹造成。**
- **已确认的逻辑缺陷（读源码）**：`FrameStateDetector.changed` 是锁存值，过程中一旦超过 0.02 就一直为 True；`wait_for_changed_and_stable().success` = 「曾变化 + 随后稳定」；旧 `_swipe_list` 在 `success` 时直接返回 `moved`，`_scan_list_once` 得到 `moved` 就把连续 static 计数清零。所以到底时「短暂回弹、最后回到原位」或「角标闪一下」都会被当推进，永远累计不到连续两次 static。
- **修复（只改 `tasks/Dokan/welfare.py`，公共 `FrameWait` / `FrameStateDetector` / 滑动模型 / 重复操作保护未动）**：滑动前存独立拷贝基准帧（`np.array`）→ `task.swipe`（沿用 `S_DOKAN_WELFARE_LIST_UP`，返回 False = 没发出 → `not_sent`）→ `_settle_list`：先用原 `wait_for_changed_and_stable` 观察，稳定后再取 `SWIPE_HOLD_FRAMES`（3）帧都与落点一致才采信（挡住回弹中途的暂停；漂移则以最新帧重新观察，每轮有 timeout，轮数 `SWIPE_SETTLE_TRIES + 1`，仍不稳定转人工）→ `list_row_coverage(基准, 落点)` 判推进。`_scan_list_once`：`moved` 清零连续 static；`static` 计数 + 日志，连续 `SWIPE_NO_CHANGE_LIMIT`（2）次到底，返回 False，交给原 `_refresh_list`；`not_sent` 不计入 static / moved，连续 `SWIPE_SEND_TRIES`（3）次转人工。
- **推进判据**：`LIST_BOX` 内逐像素通道差 > 15（沿用 `DEFAULT_PIXEL_THRESHOLD`）记为变化；一行里变化像素占比 >= `LIST_ROW_CHANGED`（0.05）该行记为「变了」；变化行占全部行 >= `LIST_MOVED_ROW_COVERAGE`（0.65）才算推进。理由：列表滚动哪怕 1 px，整列卡片的文字 / 徽记 / 边框都错位，几乎每行都有变化；角标 / 闪光动画只落在局部几行。不能用「变化像素总占比」——够大的动画块就能追平 1 px 滚动的占比（按变化像素总占比：1 px 位移 0.24，角标 + 徽记整块噪声 0.25，两者追平）。用真实截图合成量得：1 / 2 / 4 / 8 px 位移的变化行占比 0.84 / 0.90 / 0.92 / 0.97，角标整体闪动 0.24，角标 + 徽记整块噪声 ≈ 0.57（偏极端的合成上限）；阈值 0.65 夹在两者之间。**这些数字来自单张真实列表图 + 合成位移 / 噪声，未用真机录下的小幅滚动或真实动画校准。**
- **图像证据**：`tests/fixtures/dokan_welfare/list_box_oas1_20261028_204042.png` = 上述报错截图 `LIST_BOX` 的原始裁剪；回弹 / 滚动 / 角标闪动是在它上面**合成**的帧序列（角标 / 徽记位置按截图目测，近似）。
- **测试**：`tests/test_dokan_welfare.py` 新增 `SwipeProgressTest` 20 项（测试替身 `World` 新增脚本化帧序列 `swipe_script` 与「没发出」`unsent_swipes`，驱动真实 `_swipe_list` / `_scan_list_once` / `_find_and_open` 与真实 `wait_for_changed_and_stable`），覆盖：正常推进、回弹回原位、回弹中途暂停后回原位、暂停后继续滚动、仅角标 / 闪光、小幅滚动（1 ~ 12 px）、滚动叠加角标动画、独立基准拷贝、连续两次 static 交刷新、回弹算 static、static 后推进清零、一直不稳定有界转人工、没发出不计到底（含连续没发出转人工）、截图异常在观察 / 落点确认阶段原样传播、当前屏无「鑫」仍翻页。**修复前（旧实现，只加了测试）该类 20 项跑出 9 条失败 + 8 条报错记录（含子用例）：回弹回原位、回弹中途暂停、仅角标闪动、没发出等是行为失败，其余是缺新符号；修复后全部通过。** 变异验证 3 条：去掉落点确认（`SWIPE_HOLD_FRAMES=0`）→ 暂停回弹用例变红；推进线 0.95 → 小幅滚动 / 清零用例变红；推进线 0.2 → 动画用例变红。
- **未处理 / 待真机**：① D-04（正常长列表连续滑动触发公共重复操作保护）已在 §4.149 离线修复；② 到底后 `_refresh_list` 的流程与次数相关保护未动，如有问题留待后续；③ 真机：抓一次到底的滑动中间帧，核对回弹形态、`LIST_MOVED_ROW_COVERAGE` 对真实角标 / 闪光 / 小幅滚动是否有余量，核对静态滑动单次耗时（`wait_for_changed_and_stable` 对「从未变化」要等满 4 秒 + 落点确认）。不能声称完成真实模拟器验证。

### 4.149 福利道馆 D-04：有效翻页与公共重复操作保护的衔接

2026-10-28。未提交（在工作区）。**D-04 离线修复完成；正常长列表翻页与到底判断可以进入针对性实测，福利道馆整体尚未修完。**

- **证据（读源码 + 10-27 / 10-28 日志）**：滑动调用链 `welfare._swipe_list` → `BaseTask.swipe` → `swipe_trajectory` → `Device.swipe_trajectory`（`module/device/control.py`）的**第一行**就是 `handle_control_check(control_name)`：`click_record.append(str(name))` 后立即 `click_record_check()`，滑动本身在检查**之后**才执行。`click_record` 是 `deque(maxlen=15)`，同名 >= 10 抛 `GameTooManyClickError`（另有「两个不同按钮各 >= 6」一条）。所以第 10 次滑动在发出前、D-03 拿到该次 moved 结果之前就已经抛异常（日志里 10-28 oas1 的 `SwipeTrajectory` 只打印了 9 次，而 History 里有 10 条 `dokan_welfare_list_up`）。仅在 moved 之后清理即可覆盖：每次推进后该名字清零，下一次发出前最多只有「此前未被推进清掉的 static」+ 1 条。
- **修复（只改 `tasks/Dokan/welfare.py`）**：`_swipe_list` 判定为 moved 之后调用新增的 `_release_swipe_records()`，用现有 `Device.click_record_remove(名字)` 只移除福利滑动自己的记录并打日志（`list advanced, released N click record(s) of dokan_welfare_list_up`）；static 打 `static swipe, its click records are kept` 并保留记录。名字必须传字符串 `task.S_DOKAN_WELFARE_LIST_UP.name`（= `dokan_welfare_list_up`，与记录的 `control_name` 同一个字符串）：`click_record_remove` 按 `str(button)` 匹配，`RuleSwipe` 没有 `__str__`，传对象会匹配不到（测试固定）。
- **边界（为什么不会取消卡死保护）**：只有「确实发出 + 最终落点相对滑动前推进」才清；static / not_sent（本来就没写记录）/ 未稳定 / 截图或设备异常都不清；不清其它按钮（候选点击、取消详情、刷新）的记录；不 `click_record_clear`；公共阈值、`click_record_check`、`disable_stuck_detection` 未动。连续两次 static 判到底、`not_sent` 上限、不稳定等待的时间边界都没动。每批只有 static 的短列表（没有任何推进）不会被清，公共保护最终仍会触发。
- **测试**：`tests/test_dokan_welfare.py` 新增 `SwipeRecordTest` 17 项；测试替身新增 `RecordGuard`（`World(click_guard=True)` 开启）——写入 / 检查 / 移除直接使用真实 `Device.handle_control_check` / `click_record_check` / `click_record_remove`（不 mock 公共保护，仅把类属性 deque 换成实例自有）；`FakeTask.swipe` / `click` 与真实调用链一样「先记录并检查、再执行」。覆盖：连续 13 次真实推进（共 15 次滑动）不触发；写入 → 滑动 → 移除的先后顺序；只清福利滑动名字、其它记录原样保留；到底两次 static 记录保留并交刷新；static / not_sent / 不稳定 / 截图异常都不清；每批只有 static 的无进展循环仍被公共保护终止（有界）；公共阈值默认值不变；福利代码不调用 `click_record_clear`；D-03 回归（回弹 / 角标动画 static、小幅推进 moved、脚本化长列表翻页后到底交刷新）。**补丁前**该类 17 项中 5 条失败 + 3 条报错（报错即 `GameTooManyClickError: dokan_welfare_list_up`，来自真实检查逻辑）；补丁后全部通过。变异 3 条（传 RuleSwipe 对象 / 清空整个记录 / static 也清）均有测试变红。
- **未处理 / 待真机**：① D-03 的 0.65 判据、比较区域与落点确认仍待真实画面验证；② 观察到但未验证、未处理：`_check_candidate` 每个候选会写 `dokan_welfare_candidate` + `dokan_cancel_select_dokan` 两类记录，若 15 条窗口内「鑫」候选密集（各 >= 6）可能触发「两个按钮」规则，日志里尚无此类报错，按要求不清这些记录；③ 其他道馆 Bug（预设 / 建馆 / 集结等待 / Restart / 投票 / 刷新）未处理。

### 4.150 福利道馆 D-06：此前已预设过、不弹确认框时的一键预设

2026-10-28。未提交（在工作区）。**D-06 离线修复完成，等待预设有框 / 无框两条路径实测；福利道馆整体尚未修完。**

- **原调用链与缺陷**：旧 `_apply_preset` 在阵容页用 `ui_click_until_appear_or_timeout(I_DOKAN_TEAM_PRESET, stop=I_UI_CONFIRM, interval=1.5, timeout=8)` 反复点预设直到「确定」确认框出现；账号此前已预设过时游戏不弹框，8 秒内约点 5 次后 `_human('点击一键预设后没有出现「确定」确认框…')`，福利任务退出。
- **用户确认的口径（2026-10-28）**：首次预设可能弹确认框，出现就正常确认；已预设过可能不弹，此时在正确的阵容页上完成 2～4 次实际预设点击即视为本次预设操作完成。**这是用户接受的操作完成判据，程序不验证最终御魂 / 阵容效果**（日志措辞为「preset operation done」，并注明 effect not verified）。
- **修复（只改 `tasks/Dokan/welfare.py`；SwitchSoul、普通道馆、D-03 / D-04、建馆 / 集结 / Restart / 投票 / 刷新未动）**：`_apply_preset` 仍先用 `ui_click_until_appear_or_timeout(I_DOKAN_TEAM, stop=I_DOKAN_TEAM_PRESET, interval=1.5, timeout=10)` 进阵容页（出现预设图标才算到达），然后交给新增 `_click_preset()`：每帧新截图，**先看确认框（优先于任何预设点击，重试期间迟到的确认框也先确认）**→ 出现就 `ui_click_until_disappear(I_UI_CONFIRM, interval=1.5, timeout=10, max_clicks=3)`，不消失转人工；其次看预设按钮，在则用 `appear_then_click(I_DOKAN_TEAM_PRESET, interval=PRESET_CLICK_INTERVAL=1.5)`，**只有返回 True（过了限流、识别到目标并真正执行了点击）才计数**，被限流 / 目标消失的调用不计；目标次数 `random.randint(2, 4)` 一次抽定（`PRESET_NO_DIALOG_CLICKS`），不随循环重抽；发满后再观察 `PRESET_OBSERVE_SECONDS`（2 秒）仍无确认框 → 「无确认框路径」完成。
- **有界边界**：连续 `PRESET_MISS_FRAMES`（3）帧既没有确认框又没有预设按钮（被其它弹窗遮挡 / 未知页面）→ 转人工；总时限 `PRESET_TOTAL_TIMEOUT`（30 秒）内点击凑不满目标（一直没发出）→ 转人工，不凑数；确认框关不掉、阵容页进不去、完成后不在阵容页、返回找馆页失败（`_back_to_find_page` 15 秒）、设备 / 截图异常都按原机制转人工 / 原样上抛。
- **`preset_done`**：只在预设结束、确认仍在阵容页、`_back_to_find_page` 确认找馆页出现之后才设置，任何失败 / 异常出口都不设置；同一次福利运行第二馆仍不重复预设。
- **点击记录**：预设按钮名 `res_dokan_team_preset`，≤ 4 次远低于公共阈值（同名 10 / 两个按钮各 6），不需要、也没有清记录。
- **点击登记册**：`_click_preset` 新增 1 个 `appear_then_click` 规则点（`WelfareDokan._click_preset#2`，KEEP_IMMEDIATE / rule/R8），`docs/L2_CALLSITE_REGISTER.md` 用 `toolkit/python.exe -m dev_tools.click_callsite_register --write` 重新生成（`appear_then_click` 504 → 505）；首轮全量因此有 2 条登记册守卫失败（`test_l1_l2_integration.CallsiteRegisterGuardTest.test_register_doc_summary_matches_the_current_source_scan`、`test_l2_c0_registry.C0RegistryTest.test_generation_is_repeatable_and_matches_the_committed_markdown`），重新生成后这两项及登记册 / L1 / L2 / 福利相关 325 项通过；断言没有放宽，也没有再跑第二遍全量。
- **测试**：`tests/test_dokan_welfare.py` 用 `PresetFlowTest` 17 项取代旧的「没有确认框 → 转人工」用例（该用例固化的是旧业务口径，不是被放宽的保护）；测试替身新增预设模式（dialog / none / late / stuck / vanish）、预设限流、返回失败，`FakeTask.appear_then_click` 用虚拟时钟模拟真实 interval 限流。覆盖：有确认框确认并返回；无确认框目标 2 / 3 / 4 各恰好发出对应次数、间隔 ≥ 1.5 秒、不出现第 5 次；目标只抽一次且落在 2～4；确认框延迟出现（0.3 / 1.0 / 1.49 秒）先确认、不继续点背后的预设；发满后才弹框仍被观察捕获；限流调用不计数；点击一直发不出有界转人工；阵容页进不去 / 点后进入未知弹窗 / 确认框关不掉 / 返回失败 / 截图异常都不设 `preset_done`；整轮无确认框路径仍只预设一次并进入找馆；记录保护不被清。**修复前（旧 `_apply_preset` 补回后在新用例上跑）17 项中 3 条失败 + 12 条报错记录（含子用例）**，主要是无确认框路径；修复后全部通过。变异 4 条（把限流调用也计数 / 每轮重抽目标 / 不观察就完成 / 取消按钮缺失的有界保护）均有测试变红。
- **未验证 / 待真机**：有框 / 无框两条路径的真实表现；无确认框时点 2～4 次的真实效果（程序只认「点击发出 + 无框 + 仍在阵容页」，不验证御魂 / 阵容）；`PRESET_OBSERVE_SECONDS`（2 秒）是否覆盖游戏弹框延迟；预设按钮被确认框遮挡时是否仍可识别（测试替身里确认框出现时按钮不可见，真实情况未知，代码以确认框优先，不依赖它）。其他道馆 Bug 未处理。

### 4.151 福利道馆 D-02：我方道馆未建立时遗漏建立流程（同时落实 D-01 的一小部分：复用普通道馆建馆能力）

2026-10-28。未提交（在工作区）。**D-02 离线修复完成，福利模式已接入我方建馆前置流程；福利道馆整体尚未修完。**

- **原契约（以当前源码重新核对）**：普通模式在寻找目标前调 `ensure_dokan_created()`；福利模式直接进 `WelfareDokan`，没有调用，没有可靠的校验。`ensure_dokan_created()` 点建立入口（最多 2 次），出现创建确认框就 `creat_dokan()`；**两次点击都没等到确认框时按「已建立」处理**（点击无效 / 确认框没出来也会被当成已建立）；入口图标一次也没识别到才返回 False。`creat_dokan()` 是 `while True`，没有本地轮数上限（只靠公共点击记录兜底），并且**忽略 `ui_click_until_disappear(信息页关闭)` 的返回值**，信息页关不掉也记「Create Dokan Success」。返回 True 时页面应在道馆地图，没有任何「已回到找馆页」的确认。
- **图标证据（真实截图离线核对）**：`I_RYOU_DOKAN_CREATE_DOKAN`（金色锣）与 `I_RYOU_DOKAN_HAVE_DOKAN`（灰色锣）两个模板互相匹配分 **0.96**，高于默认阈值 0.8，所以默认阈值下两个图标同时命中、不能用来判断状态。用 `log/error` 里 2026-10-26～28 四张真实整屏截图量得：本图标得分 0.996～0.997，另一个 0.956～0.96；「已建立」样本取自 10-27，「未建立」样本取自 10-26 / 10-28（正是 D-02 现象：未建馆就进了找馆）。阈值取 **0.98**（`OWN_DOKAN_MARKER_THRESHOLD`）。**样本只有 4 个场景（2 个账号 × 已建 / 未建，日期 10-26～28），覆盖面有限，需真机继续观察。**
- **修复**：① `ScriptTask.ensure_dokan_created(strict=False)` / `creat_dokan(strict=False)` 新增 **默认关闭的 strict**，默认路径一行未动（普通模式行为不变）；② strict：新增 `own_dokan_state()`（高阈值下 `created` / `uncreated` / `None`），`created` 不点击直接返回 True；`uncreated` 才点建立入口，**两次点击都没弹确认框返回 False（不再当成已建立）**，状态分辨不出（含两图标同时或都不像）连看 `OWN_DOKAN_STATE_TRIES`（3）帧后返回 False；`creat_dokan(strict=True)` 轮数有界（`CREATE_DOKAN_MAX_ROUNDS` = 3），信息页关闭用 `ui_click_until_disappear(timeout=10, max_clicks=4)` 并在返回 False 时再截图确认，关不掉返回 False；③ `WelfareDokan._ensure_own_dokan()`：调 `ensure_dokan_created(strict=True)`，False 转人工；再用 `_map_state` 确认**回到找馆页**（`finding`），否则转人工；成功才设 `own_dokan_checked`（失败 / 异常出口都不设）。
- **接入位置**：`_run` 里在「确认没有进行中的馆 → 读到剩余机会 > 0」之后、预设之前，一次运行只检查一次，第二馆不重复。已有进行中的馆 / 机会为 0 / 机会未知仍按原规则在它之前结束或转人工，不建馆。
- **边界**：建我方道馆不增加 `opened`（只统计「确认开启」过的对方馆）、不扣减 / 推算攻打次数、不写成功排期；不读 `try_start_dokan`（福利模式本身已明确要求自动找馆开馆），也不改写用户配置；转人工的话术不会说「已开启对方道馆」。
- **点击登记册**：新增 2 个点击点（`_ensure_dokan_created_strict#1` 的 `click`，R6；`creat_dokan#1` 的 `ui_click_until_disappear`，R7），均 KEEP_IMMEDIATE；`docs/L2_CALLSITE_REGISTER.md` 用 `dev_tools.click_callsite_register --write` 重新生成（总数 1121 → 1123，basis rule 922 → 924），`tests/test_l2_c0_registry.py` 两条守卫里的期望数字随之更新（断言本身没有放宽）。
- **测试**：`tests/test_dokan_welfare.py` 新增 `OwnDokanTest` 21 项（真实 `WelfareDokan._run` + 真实 `ScriptTask.ensure_dokan_created / creat_dokan`，只替换设备 / 识别 / 虚拟时钟；World 的图标按真实量得的 0.96 交叉分建模）、`OrdinaryCreateCompatTest` 5 项（默认路径行为不变，同一画面 strict 会拒绝）、`OwnDokanIconResourceTest` 3 项（真实截图裁出的图标样本 `tests/fixtures/dokan_welfare/own_dokan_icon_*.png` + 真实模板文件，直接 `TM_CCOEFF_NORMED`）；`tests/test_dokan_normal_mode.py` 新增 `RunOnDokanMapTest` 4 项（普通模式 `run_on_dokan_map` 仍无参调用 `ensure_dokan_created()`，`try_start_dokan=False` 仍直接退出）。覆盖：已建立不点击；未建立 → 点入口 → 确认 → 关信息页 → 回到找馆页 → 预设 → 找馆；确认框晚到 1.5 秒仍只点一次入口；点入口没反应 / 确认没反应 / 信息页关不掉 / 点确认后进未知弹窗 / 图标分辨不出 / 图标不在 / 建完不在找馆页，全部有界停止且不预设、不找馆、不开馆；进行中的馆 / 机会 0 / 机会未知不建馆；调用顺序；两馆只检查一次；`opened` / 次数 / 排期不变；配置不被改写、`try_start_dokan` 不是门槛。
- **修复前后**：补丁前（福利入口不调建馆检查）新用例 29 项中 17 项红；补丁后全绿。变异 8 条（图标状态用默认阈值 / strict 把无框当已建立 / 忽略信息页关闭结果 / 取消轮数上限 / 取消找馆页确认 / 先设 `own_dokan_checked` / 建馆计入 `opened` / 福利调非 strict）均有测试变红；其中「忽略信息页关闭结果」首轮存活（被福利侧的找馆页检查兜住），已补直接测 `ensure_dokan_created(strict=True)` 返回值的用例后变红。
- **未验证 / 待真机**：① 「已建立」不点击就继续——真实游戏里点击灰色锣是否会弹别的窗口无法确认（原流程会点两次），目前是不点；② 0.98 阈值只有 2 个场景的 4 张截图支撑；③ 建立后图标是否变成「已建立」、动画延迟多久未验证，当前不以图标变化作为成功证据，只以关闭信息页 + 回到找馆页为准；④ 建立流程真实耗时 / 确认框延迟是否在 3 秒窗口内；⑤ 其他道馆 Bug（集结等待 / Restart / 投票 / 刷新、D-01 的其余部分）未处理。

### 4.152 福利道馆 D-05：正常集结等待被公共无操作保护判成卡死

2026-10-29。未提交（在工作区）。**D-05 离线修复完成，等待长时间集结与准备后立即关闭的实测；福利道馆整体尚未修完。**

- **原因（以当前源码重新确认）**：`Device.screenshot()` 每次先 `stuck_record_check()`；`Device.stuck_timer = Timer(60, count=60)`、`stuck_timer_long = Timer(300, count=300)` 是类属性，**距最近一次 `stuck_record_clear`（每次点击、`app_start` / `app_stop` 都会清）超过 60 秒且已检查 > 60 次**就抛 `GameStuckError('Wait too long')`；登记 `stuck_long_wait_list`（`PAUSE` 等）只能把上限从 60 秒延到 300 秒，300 秒的长计时器到点无论如何都抛。旧 `_enter_prepare_and_close` 在集结期间只截图 + `sleep(1)`，没有点击、也没有保活，所以约 60 秒必报。10-27 oas2 日志：20:40:34 `dokan opened` → 20:41:33 `Wait too long`、`Waiting for set()`（`detect_record` 为空，没有登记任何等待）——不是已证明的游戏卡死，是正常集结和公共保护冲突。**`stuck_record_add` 不够**：最多撑到 300 秒，撑不住 900 秒的业务上限。
- **普通道馆的做法与复用**：`run_on_dokan` 识别到道馆页（`I_RYOU_DOKAN_CHECK`）后每轮 `device.stuck_record_clear()`，集结分支再 `click_record_clear()`；助威期间 `stuck_record_clear()` + `stuck_record_add('PAUSE')`。福利沿用同一思路（识别到合法等待页再清），但不照抄「道馆页每帧都清」：只在「道馆页 + 集结中」两个证据同时在的帧清。
- **修复（只改 `tasks/Dokan/welfare.py::_enter_prepare_and_close`，公共 Device / 阈值 / 其它任务未动）**：① 「道馆页 `I_RYOU_DOKAN_CHECK` + 集结中 `I_RYOU_DOKAN_GATHERING`」的帧清一次公共卡死计时（识别在先、清在后，所以下一次 `screenshot()` 前的检查看到的总是刚清过的计时，距离最近一次清除的间隔只有 1～2 秒）；② 业务总时限 `GATHER_TIMEOUT`（900 秒）在进入本阶段时算一次 `deadline`，识别 / 保活都不重置；③ 「可开始挑战」的帧（无集结中 + `I_RYOU_DOKAN_START_CHALLENGE`，沿用原条件与 `appear_then_click(interval=2)`）**不清计时**，靠点击本身推进；本阶段发出的开始挑战点击上限 `GATHER_START_CLICK_LIMIT`（5），点满后再观察 `GATHER_START_OBSERVE`（3 秒）仍没进准备页 → 转人工（点击无效不是在等）；④ 其余画面（过渡 / 未知，含「集结中但不在道馆页」）**不清计时**，连续超过 `GATHER_UNKNOWN_TOLERANCE`（30 秒，小于公共 60 秒，所以先于公共保护给出具体原因）→ 转人工；⑤ 不登记任何特殊等待状态、不捕获异常，退出（含异常）后公共保护不受影响，`app_stop` 本身仍会清计时。
- **时序**：识别到 `I_PREPARE_HIGHLIGHT` → `execute_single_click` → `app_stop()` 紧邻不变（日志放在点击之前和关闭之后，中间没有截图 / sleep / 查询）；确认关闭 / 600 秒 / 登录 / 放弃 / 再战未动。
- **日志**：进入集结（含业务上限）、首次识别到集结页（说明保活只在识别到该页时进行）、每 60 秒一条「still gathering」、开始挑战点击次数、点准备 / 已请求关闭；未知画面首次出现（说明不保活 + 容忍时长）、未知超时 / 开始挑战无效 / 业务超时的具体原因（转人工信息）。日志只说「识别到集结页」，不宣称流程必然正常。
- **测试**：`tests/test_dokan_welfare.py` 新增 `GatherGuardTest` 17 项；测试替身新增 `World(stuck_guard=True)`——设备带真实 `Device.stuck_record_add / clear / check`（实例自有的真实 `Timer`，时间取自被替换的虚拟时钟，60 / 300 秒 + 检查次数条件都在），`screenshot` 前先检查、点击和 `app_stop` / `app_start` 清除，与真实 `Device` 的顺序一致；不是 mock 掉 `stuck_record_check`。覆盖：集结 100 / 320 / 850 秒不误报并能继续开始挑战；900 秒业务上限从阶段起点算、不被保活重置；开始挑战点击 → 准备 → 点击与 `app_stop` 紧邻；未知画面 30 秒内转人工且集结页消失后一次都没清；开始挑战无效恰好 5 次点击后转人工；20 秒过渡恢复 / 40 秒过渡转人工；截图异常 / `KeyboardInterrupt` / `SystemExit` / `app_stop` 异常原样传播且不开战；正常 / 异常退出后无遗留特殊等待状态，+70 秒 + 超过 60 次检查后公共保护仍抛 `GameStuckError`；每次检查距最近一次清除的最大间隔 < 5 秒；整条两馆流程在 400 秒集结下跑通；普通道馆 `run_on_dokan` 的保活写法保持原样。
- **修复前后**：补丁前（旧循环原样补回）17 项中 13 项失败，全部是公共 `GameStuckError: Wait too long`（整条流程那条被 `run()` 转成 `RequestHumanTakeover`，信息里带 `GameStuckError('Wait too long')`）；补丁后全绿。变异 8 条（去掉保活 / 只登记 `PAUSE` / 每次截图后无条件清 / 未知分支清 / 保活时重置业务上限 / 去掉开始挑战点击上限 / 未知容忍长于公共 60 秒 / 点准备与 `app_stop` 之间加截图）均有测试变红；其中「未知分支清」首轮存活（只清了一次，落在原断言窗口内），已把断言收紧为「集结页消失之后一次都没清」。
- **点击登记册**：没有新增 / 删除点击调用点，重新生成后无差异。
- **未验证 / 待真机**：① 集结页证据（`I_RYOU_DOKAN_CHECK` + `I_RYOU_DOKAN_GATHERING`，ROI 653,76 阈值 0.85）在真实集结全程是否稳定可见（动画 / 弹窗期间会被当成未知画面，容忍 30 秒）；② 集结结束到「开始挑战」出现之间是否有超过 30 秒的未知过渡画面；③ 馆主战等待（`I_DOKAN_BOSS_WAITING`）这类「道馆页但既无集结也无开始挑战」的状态目前按未知处理（30 秒转人工），福利路径下是否会出现尚无真实画面；④ 真实长时间集结（> 5 分钟）和点准备后立即关闭的实测；⑤ 其他道馆 Bug（Restart / 投票 / 刷新、D-01 其余部分）未处理。

### 4.158 每日琐事领取邮件：已在邮箱里不再点「打开邮箱」按钮（oas2 10-29 09:49 点击守卫报错）（原与 D-07 重号为 §4.153，2026-10-29 发布审查改号）

2026-10-29。未提交（在工作区）。**Level A/B（离线）PASS；真机未验证。**

- **事故**：10-29 oas2 09:49 `DailyTrifles` 领取邮件时 `GameTooManyClickError: Too many click between 2 buttons: DT_HARVEST_MAIL_COPY2, DT_HARVEST_MAIL_ALL`，保存 `log/error/oas2_1793238580881`，重启后 09:50 重跑正常。现场截图：邮箱已打开、有未读邮件，顶栏信封图标仍露在边框上方。**直接原因**：旧 `run_pickup_email` 里 `COPY2`（顶栏信封）优先级最高、每 1.2 秒识别到就点一次，邮箱打开后照样匹配，和「一键领取」各点 6 次触发点击守卫；失败那次 `ALL` 每次都在信封点击后约 0.9 秒才点（平常约 1.6 秒），6 次都没出现确认弹窗，推测是点得太早、展开动画期间被游戏忽略（没有点击瞬间的画面，只是推测）。旧流程另有两处问题：没有「已在邮箱」判断；从没进过邮箱也照样记今天已完成。**邮箱已打开的标志**：`RestartAssets.I_HARVEST_MAIL_TITLE`（「邮箱」标题）与 `I_SYSTEM_MAIL_OPEN`（「系统邮件」标签打开状态）**任一出现**即在邮箱页面（用户已按当前界面重新标注；在现场截图上匹配度 1.0，另 28 张其它页面截图最高约 0.45，阈值 0.8；标题旧区域偏了约 10 像素，现为 y=58）。**新流程**（`tasks/DailyTrifles/script_task.py`，新增 `_in_mailbox()`，资源仍放在 Restart 任务里、DailyTrifles 引用 `RestartAssets`）：领取确认 / 奖励弹窗优先（弹窗会盖住标志）→ 已在邮箱：点「一键领取」（点了 `PICKUP_ALL_TRIES=6` 次都没出现确认弹窗就放弃）、「一键已读」不重置空闲计时，邮箱里没有可操作按钮持续 `PICKUP_IDLE=3` 秒算领完 → 还没进邮箱：才点「打开邮箱」按钮（COPY2 / MAIL / MAIL_COPY，间隔 ≥ `PICKUP_OPEN_GAP=3` 秒，最多 `PICKUP_OPEN_TRIES=3` 次）。总时限 `PICKUP_TIMEOUT=60` 秒。**只有真的进过邮箱且没有放弃才记今天已完成**；邮箱没打开 / 一键领取始终无效 / 超时都只记 warning、不记完成（下次运行再试），不再静默跳过一天。点击策略、`interval` 和 L2 policy 与原来一致（6 个点位不变）。
- **验证**：全量 3384 项 OK（2 项 skipped，首轮全量；工作区同时有其它会话的改动，差额未逐项归因）。基线行（§7）由并行会话维护，这里不改。**测试**：新增 `tests/test_daily_pickup_email.py` 11 项（假画面 + 真实 Timer，常量缩小）：邮箱已打开且顶栏信封仍可见时不点任何打开按钮、标题 / 系统邮件标签任一出现即可、弹窗盖住标志时只点确认、一键已读常驻不让循环不结束、关着的邮箱只打开一次且之后不再点信封、邮箱始终打不开有界重试且不记完成、点击间隔、一键领取无效有界放弃且不记完成、连续两个确认弹窗、policy 与常量、同天二次运行跳过。变异 9 条各有测试变红。`tests/test_daily_trifles.py` 的 `PickupEmailTest` 夹具调整：点「打开邮箱」按钮后出现邮箱标题（原先没有邮箱标志也会记完成），常量缩小，断言不变。登记册重新生成，总数不变（1123）。
- **未验证（全部待真机）**：重新标注后的两个标志在真机各种情形下的识别（只有一张邮箱打开的截图，没有「特别邮件」标签被选中时的样本，那种情况 `I_SYSTEM_MAIL_OPEN` 不会命中，标题标志是否仍命中待确认）；`ALL` 在邮箱展开动画期间被忽略的推测；`PICKUP_*` 常量是否合适；邮箱里没有可领取邮件时（一键领取灰掉）是否按预期 3 秒后结束。Restart 任务也在用这两个标志，其资源已被重新标注，Restart 侧未改动也未验证。
- **补记（2026-10-29 第二版，按用户反馈改）**：领取后会弹「是否立即启用"…插画"？」（取消 / 确定）、获得插画、获得头像框等弹窗和全屏页，原先都靠最后的 `goto_page` 兜底关闭，而且会盖住邮箱标志。本地用现有模板对三张用户截图做匹配（OpenCV，不启动服务）：启用确认的大号 `I_UI_CANCEL` / `I_UI_CONFIRM` 都是 1.0；红色关闭叉 `I_UI_BACK_RED` 在启用确认 0.87、头像框 0.966、邮箱自己的叉 0.918；获得插画没有任何现有模板能识别。**改动**（`run_pickup_email`）：① **进过邮箱就一直算在邮箱流程里，直到自己点了退出**——看不到邮箱标志不再当成离开邮箱（不再点「打开邮箱」按钮）；② 弹窗：两个大按钮同时出现 → **只点取消、从不点确定**（`_pickup_popup`，policy CONFIRM）；看不到邮箱标志时的红色关闭叉（头像框等全屏页）→ 点（NAVIGATION）；③ 一键领取不再出现持续 3 秒算领完，**然后点邮箱自己的关闭叉退出**（最多等 `PICKUP_EXIT_TIMEOUT=6` 秒，退不出由 `goto_page` 兜底）；④ 进过邮箱却一直看不到标志（未知弹窗）最多等 `PICKUP_LOST_TIMEOUT=10` 秒后走兜底；⑤ 记今天已完成的条件改为「领完，或点过一键领取 / 确认弹窗」且没有放弃。**获得插画尚未处理**：等用户标注「获得插画」标题模板后，在无标志时点安全空白处关闭；在那之前它会等到 10 秒兜底。测试：`test_daily_pickup_email` 11 → 20 项（粘性邮箱状态、取消不确认、孤立的取消 / 确定按钮不当弹窗、全屏页关闭叉、领完才点邮箱关闭叉、未知弹窗有界兜底、没领取不记完成），变异 8 条各有测试变红；登记册 +3 个 policy 点（1123 → 1126，policy 97 → 100，DailyTrifles 42 → 45，`POST_C1_CONSUMERS` 逐点登记）。全量验证（如实记录，不挑结果）：首轮全量 3406 项、1 项失败——我之前写的 SwitchSoul 小步幅测试里一条依赖随机步幅的断言 `test_a_target_first_seen_clipped_at_the_bottom_is_found_after_the_next_swipe`，已改为固定 100px 步幅（确定性），该模块连续 3 次通过；修复后第二次全量 3437 项、4 项失败：`test_dokan_welfare` 3 项 + `test_l2_c0_registry` 的「生成结果与已提交 markdown 一致」1 项，全部来自并行会话正在改的福利道馆（`WelfareDokan._refresh_list` 等点位的等待标记与登记册不一致，登记册已不是最新），与本轮领取邮件无关，我没有去改福利道馆或替对方重新生成登记册；本轮相关的 `test_daily_pickup_email` + `test_daily_trifles` 79 项、SwitchSoul 名称搜索 61 项、点击登记册 / L1·L2 守卫 184 项当前工作区单独运行通过。
- **第三版补记（2026-10-29，用户已标注 `I_GET_PICTURE` 并追问风险）**：① **获得插画**：`DailyTriflesAssets.I_GET_PICTURE`（标题模板）在用户截图上匹配度 0.988，其它截图最高 0.177；识别到就点安全空白处（`random_click()` 的 SAFE_RANDOM_CLICK，policy NORMAL，间隔 1.5 秒）。② **有界性补强**：每种弹窗 / 关闭叉最多点 `PICKUP_POPUP_TRIES=5` 次，点了不消失就放弃（不记完成），避免触发点击守卫（同名 ≥10 次）；看到主界面标志 `I_CHECK_MAIN` 说明邮箱已被关掉，立即离开而不是等 10 秒；**打开邮箱之前**出现的「确定」不再让 `opened` / `claimed` 置位（只有邮箱标志才置位，防止主界面别的对话框碰巧也有「确定」时被误记为领完）。③ 对其他任务的影响：`_pickup_popup`（取消 / 获得插画）只在 `run_pickup_email` 里、且进过邮箱之后才调用，没有改公共的 GameUi / GlobalGame 处理和 `I_UI_CANCEL` / `I_UI_CONFIRM` 资源，其它任务不受影响。测试 `test_daily_pickup_email` 25 项，变异 6 条各有测试变红；登记册 +1 个 policy 点（1127，policy 101，DailyTrifles 46）。全量：本版全量 3442 项、1 项失败——`test_swipe_endpoint_sampling.WideRoiPassthroughTest.test_both_wide_output_distribution_matches_legacy_coord`（均值差 3.157 > delta 3.0，15000 样本无种子的统计性用例，此前已记录其约 1% 量级的偶发概率；单独重跑 12 次全过，未改阈值、未改公共随机模型）；其余全部通过（上一轮失败的福利道馆 3 项与登记册一致性已不再失败）。

### 4.153 福利道馆 D-07：异常请求的 Restart 被「调度器启动时跳过首次 Restart」吞掉

2026-10-29。未提交（在工作区）。**D-07 已核实并完成必要修复 / 验证；福利道馆整体仍待剩余问题核对与真机验收。**

- **「启动时跳过 Restart」为什么存在**：`Script.loop` 里 `if self.is_first_task and task == 'Restart'` → 跳过并 `task_delay(Restart, success=True)`。脚本刚启动时，配置里常有已到点的例行 / 陈旧 Restart（每天 09:20 的例行重启、上次进程留下的请求），不跳过就会每次启动 OAS 都无条件重启游戏。该规则应保留。`is_first_task` 只在三处改变：`__init__` 置 True、`_loop_note_recovery` 里有活动循环时置 False（御魂循环那次局部修复）、`loop` 里任一任务 `run` 结束后置 False。
- **异常请求怎么写入、传递**：`Script._handle_task_exception` 的五个恢复分支（`GameNotRunningError` / `GameStuckError`·`GameTooManyClickError` / `GameBugError` / `GamePageUnknownError`）调用 `config.task_call('Restart')`——`force_call=True` 时把 `restart.scheduler.next_run` 设为当前时间并 `save()` 落盘；下一轮 `del_cached_property(config)` 重载后 `get_next_task` 把它当到点任务选出。（`RuntimeController._run_restart_recovery` 是直接 `script.run('Restart')`，不经过调度选择，不受跳过规则影响。）
- **真实触发条件（以日志与源码重新核实，不照抄原结论）**：
  1. **10-27 oas2 的 `START` / `Start scheduler loop` 是新进程，不是同一进程内重新进入调度**：`log/2026-10-27_api.txt` 显示 `20:38:21 ws[oas2] msg: stop`（异常处理 `device.sleep(10)` 期间用户在 GUI 点了停止）、`20:39:19 msg: start`；`ScriptProcess.stop()` 终止进程、`start()` 新建进程并 `Script(config)`（`__init__` 打 `START`、`is_first_task=True`）。新进程读到落盘的 `Restart next_run=20:38:16`，与「启动时的例行 / 陈旧 Restart」无法区分，于是 `Skip task Restart at scheduler start`。这是启动规则按设计工作，**跨进程不属于本进程内的恢复请求**。
  2. **10-28 oas1 同一进程内正常执行**：20:40:43 `Task call: restart` → 20:40:53 `Pending tasks: ['Restart', 'Dokan']` → `Start task Restart`（没有新的 `START`；该进程 17:21 启动，早已有任务跑完，`is_first_task` 已为 False）。
  3. **真实的进程内缺陷（本轮修复的）**：首个任务**准备阶段**（`prepare_task_execution` / `get_next_task` / `team_sync.precheck`）抛出可恢复异常时，`loop` 的 `except` 分支只 `_handle_task_exception` + 重载配置 + `continue`，`is_first_task` 仍是 True（只有「任务 run 结束」处才置 False；`_loop_note_recovery` 也只在有活动循环时置 False）；下一轮 Restart 刚被请求就被当成启动时的 Restart 跳过。任务**运行中**的异常不受影响（`run` 返回后 `is_first_task=False`）。
- **其他会话的改动是否已覆盖 D-07**：没有。当前工作区其他会话只改了 `DailyTrifles` / `Restart` 资源（`tasks/Restart/assets.py`、`harvest/*`），`script.py` / `module/config/config.py` 相对本轮基线（sha256 前 16 位 `346f3251d941d75e` / `24052b682cf91316`）未变，无重叠；御魂循环那次局部修复只覆盖「有活动循环」的情形。
- **修复（只改 `script.py`）**：新增 `Script._request_restart_recovery()`：`_loop_note_recovery()` → `config.task_call('Restart')` → **登记成功（返回真）之后**才 `is_first_task = False`；`task_call` 抛异常或返回 False 时不改状态、异常照旧上抛。`_handle_task_exception` 的四处「`_loop_note_recovery()` + `task_call('Restart')`」改为调用它（行为：登记顺序不变，仅多了登记后的状态更新）。例行 Restart 的跳过规则、失败计数 / 3 次上限、`_loop_note_recovery`（含御魂循环置顶 / 阻塞等待语义）、Restart 内部实现、福利的转人工规则均未动。
- **区分 A / B 与状态清理**：`is_first_task` 是单向锁存，B 登记成功后置 False 只是「启动阶段已经结束」，没有新增请求标记；Restart 运行结束后由它自己的 `task_delay` 排下一次，请求自然消失，不会再被反复拉起。
- **福利边界**：开馆前的可恢复异常（`GameTooManyClickError` 等）沿用恢复路径，Restart 真实执行；已开启对方道馆后，`WelfareDokan.run` 仍把自动恢复类异常转成 `RequestHumanTakeover` → `exit(1)`，不登记 Restart、不重跑福利路线、不误开下一馆（测试用真实 `WelfareDokan.run` + 真实 `Script.loop` 验证）。
- **测试**：新增 `tests/test_restart_recovery_first_task.py` 13 项：真实 `Script.loop` / `run` / `_handle_task_exception`、真实 `Config.task_call` 与调度选择（临时目录里的真实配置文件，每次失败后重载），只替身设备、运行时准备和任务叶节点，叶节点调用总数有独立的 40 次失控上限。覆盖：例行 Restart 仍被跳过且被推迟；首个任务之后到点的 Restart 正常执行；首个任务运行中异常 → Restart 真执行恰好一次；首个任务准备阶段的五种可恢复异常 → Restart 真执行；同进程内配置重载 + 重新进入调度；新进程遇到遗留请求按启动规则跳过（已知边界，见下）；失败 3 次上限（`Dokan, Restart, Dokan, Restart, Dokan` 后 `SystemExit`）；致命异常不登记 Restart；`task_call` 抛异常 / 返回 False 时不改 `is_first_task`；五个恢复分支都是「先登记、登记成功后才改状态」；福利开馆前异常 → Restart 执行、开馆后异常 → 转人工且 `task_call` 从未被调用。
- **修复前后**：补丁前 13 项中 3 项失败（共 11 个断言 / 子用例：准备阶段 5 种异常下 Restart 未执行、五个分支「登记后状态」、重新进入调度 1），其余 10 项（运行中异常、福利、失败上限等）本来就通过，说明任务运行中的路径原本没问题；补丁后全部通过。变异 3 条（登记前就改状态 / 登记返回 False 也改 / 不改 = 原缺陷）均有测试变红；「跳过御魂循环登记」在本文件不会红（没有活动循环），由既有 `test_loop_script_glue` 3 项变红覆盖。
- **验证**：`compileall -q script.py tests/test_restart_recovery_first_task.py` 通过；相关 501 项（本文件 + 循环 / 疲劳 / 组队同步 / 活动恢复 / 福利 / 普通道馆等）通过；全量 `unittest discover -s tests` 只跑一次，**3397 项运行 OK（skipped=2）**，开始 10:49:02、结束 10:54:37，开始前后 `git status` 条目数（189）与 `script.py` 哈希不变、其他会话文件无新改动；完整输出保存在 `D:\Codex\workspace\d07\`（`full_suite.txt` / `related_tests.txt` / `new_tests_before_fix.txt` / `new_tests_after_fix.txt`）。上一轮 D-05 因并发改动只能说明范围，本轮全量不在并发改动下，结果适用于「本次运行时的工作区快照」。
- **未处理 / 待决定**：① **跨进程（用户在 GUI 点停止再启动、或进程因其它原因重启）后遗留的异常请求仍会被启动规则跳过**——要区分它和陈旧例行 Restart 必须新增持久化标记（或按 `next_run` 与进程启动时间做启发式判断），本轮按要求没有新增持久化协议，是否需要由用户决定；② 准备阶段异常反复出现时「Restart 成功 → 再次准备失败」不计入 `failure_record`（现有行为，对非首个任务本来就如此，本轮未改，修复后首个任务与之一致）；③ 投票、刷新、D-01 其余部分未处理；④ 真机未验证（未启动 OAS / MuMu / 游戏 / ADB / OCR）。

### 4.154 福利道馆 D-09：到底后的刷新与重新搜索闭环；D-08 候选去重核查；候选「点击 + 取消」双按钮保护

2026-10-29。未提交（在工作区）。**D-09 刷新闭环与 D-08 候选去重已核查并完成必要修复，等待针对性实测；福利道馆整体尚未完成真机验收。**（注：「每日琐事领取邮件」原先与 D-07 重号为 §4.153，2026-10-29 发布审查时改为 §4.158，并把误放在 D-07 / D-09 节末的领取邮件第二版、第三版补记移回该节。）

- **普通刷新流程与复用**：普通模式 `find_dokan` 刷新 = `ui_click(C_DOKAN_REFRESH, I_REFRESH_ENSURE)` → 无超时的 `ui_click_until_disappear(I_REFRESH_ENSURE)` → 睡 3 秒 → 继续找；刷新次数受 `find_dokan_refresh_count` 限制，刷新后不确认列表、也不回顶（`find_all_element` 直接从列表区域起点往下找）。福利复用同样的两个资源（`C_DOKAN_REFRESH` 点刷新、`I_REFRESH_ENSURE` 点确认），但没有复用 `find_dokan`（它带普通评分 / 人数 / 刷新上限），福利的点击与等待是有界版本，`welfare.py` 不读 `find_dokan_refresh_count`。
- **旧 `_refresh_list` 成功时到底确认了什么**：只确认「确认框出现过、点击后消失了」，再睡 1 秒。`I_REFRESH_ENSURE` 是整屏「确认」模板，别的弹窗（货币不足 / 刷新限制）上的「确认」也会命中，确认框消失不能证明列表刷新了；也没有任何刷新后位置的证据：`log/` 与 `log/error/` 里没有任何一次真实刷新（没有 `@ dokan_refresh` 点击记录），仓库里也没有「向上回顶」的滑动资源（只有 `dokan_list_up` / `dokan_welfare_list_up` 两个向下翻页的）——**列表刷新后是否回顶没有源码 / 截图证据，不能默认回顶**。批次状态（`_scan_list_once` 里的 `checked`）本来就是函数局部变量，每批重建，生命周期严格限定在一批。
- **修复（只改 `tasks/Dokan/welfare.py`）**：`_find_and_open`：到底（D-03）→ `_refresh_list()` → `_scroll_list_to_top()` → 新一批。① `_refresh_list` 点刷新前先存「到底时的列表」做基准；点击 / 弹窗 / 点确认仍有界（`REFRESH_TRIES` 3 次、确认 10 秒 / 3 次点击），弹窗出不来 / 关不掉转人工；然后 `_await_refreshed_list`：页面必须回到找馆页（`FINDING` 在、`FOUND` 和确认框都不在，最多 `REFRESH_PAGE_TIMEOUT` 6 秒，否则转人工）→ 用 D-03 的 `_settle_list` 等列表停稳（不稳定转人工）→ 稳定后的列表与基准比较变化行占比（`list_row_coverage`）≥ `REFRESH_CHANGED_COVERAGE`（0.05）才算新一批就绪，最多 `REFRESH_LOAD_ROUNDS`（3）轮（覆盖延迟加载），一直没变化转人工，不把旧列表当新一批重复检查、也不为「看起来没生效」反复花钱重刷；日志写出每次的实测变化行占比。② `_scroll_list_to_top`：因为没有刷新后位置的证据，不假设回顶——用现有 `S_DOKAN_WELFARE_LIST_UP` 的起终点对调派生反向滑动（`dokan_welfare_list_down`，同一列表区域，未新增资源 / 坐标文件），复用 `_swipe_list` 的 D-03 判据（落点稳定 + 与滑动前比较行占比），连续两次 static 才算在顶部；有效推进上限 `TOP_MAX_MOVES`（30）、没发出上限 `SWIPE_SEND_TRIES`，推进的反向滑动同样只在 moved 之后移除它自己的记录（D-04 做法）。D-03 的 0.65 判据与最终落点逻辑未动。
- **D-08 候选去重核查结果**：① **已证实的问题**——旧指纹判据（34x30 小图整体平均绝对差 < 6.0）用真实卡片量得：同一张卡裁剪偏 1 px ≈ 5.2、偏 2 px ≈ 10.1（偏 2 px 就会被当成不同卡片）；而在真实卡片上把一行文字（4 px 高）换掉整体差只有 ≈ 1.7、换 12 px 也只有 ≈ 4.5（仍被当成同一张，即不同的馆可能被误去重、漏检）；两张真实不同卡片 ≈ 8.78，余量很窄。② **修复**：`card_fingerprint` 上下各多留 `CARD_MARGIN`（2）行并屏蔽「鑫」徽记（含余量，比较时取两张的并集），`same_card` 改为 ±2 px 对齐后按 6 条水平带分别比较、取最大带差 < `CARD_BAND_SAME`（6.0）；同样数据下偏 ≤ 2 px ≈ 2，换一行文字 ≈ 10（4 px 即 10.1），两张真实不同卡片 ≈ 18.5，徽记闪动 = 0。指纹仍是 30x34 数组（`CardFingerprint` 子类，附带 `tall` / `badge`），`same_card` 对普通数组仍退回旧判据。③ **已核对无问题**：每屏从上到下（按纵坐标排序）、点击前重新定位（`_relocate` 用指纹而非旧坐标）、点击前先关闭上一个详情（`_hide_popup`）、翻页重叠同一馆不重复（逐张只检查一次）、刷新后批次状态重建（上一批的记录不阻止新一批同样的卡片被检查，测试里同一张 `x` 在两批各检查一次）、选中高亮不破坏身份（指纹取自未选中状态，比较发生在详情关闭之后）。④ **未证实的风险**：真实不同卡片样本只有 2 张（2 个账号 / 2 天），上面的 6.0 阈值余量来自这 2 张加改文字的合成对照；各种背景相似 / 人数相同的真实相邻卡片没有样本；新增 `RELOCATE_LIMIT`（5）：同一批里连续 5 次点击前重新定位失败转人工（原来只靠公共 60 秒无操作保护兜底，无点击不触发公共操作记录）。
- **候选双按钮保护（复现并局部修复）**：用真实 `Device` 记录逻辑复现——每个候选各记 1 次 `dokan_welfare_candidate` 和 1 次 `dokan_cancel_select_dokan`，D-04 又会在有效滑动后移除滑动记录，使窗口里只剩这两类，**检查第 6 个候选就抛 `GameTooManyClickError: Too many click between 2 buttons`**（测试 `test_the_same_scan_trips_the_two_button_rule_without_the_release` 复现）。修复：一个新候选详情已打开、得出明确结论（读到人数且低于门槛，或确认不可挑战）、并且**详情已成功关闭**（`_hide_popup` 看到详情消失）之后，才 `click_record_remove` 这两个名字；记录在点击发出前写入并检查，释放发生在下一次候选点击之前，窗口里始终最多一对。只点击已发出不清；人数读不出 / 没有详情 / 详情关不掉 / 重新定位失败都不置有效标记，仍受公共保护且各自有局部上限（`HIDE_ATTEMPTS`、`RELOCATE_LIMIT`）；`click_record_remove` 只能按名字整体移除，不动其它按钮。没有关闭任何保护、没改公共阈值。
- **点击登记册**：没有新增 / 删除点击调用点，`docs/L2_CALLSITE_REGISTER.md` 用 `dev_tools.click_callsite_register --write` 重新生成后只有福利两行的「上下文」列变化（`_refresh_list` 不再含 `sleep`）。
- **测试**：`tests/test_dokan_welfare.py` 新增 `RefreshClosureTest` 17 项、`CandidateRecordTest` 8 项、`CardIdentityTest` 6 项；样本 `tests/fixtures/dokan_welfare/list_xin_oas2_2026102{6,7}.png`（真实整屏截图的列表列裁剪）。测试替身新增：刷新模型（回顶 / 保持位置、延迟加载、确认后列表不变 / 进入未知画面）、选中高亮、反向滑动、操作记录用真实资源名且 `appear_then_click` 也写记录（更贴近真实 `Device`）。**一条既有用例改了前提**：`test_endless_lists_without_progress_are_still_stopped_by_the_public_guard` 原先断言「公共保护最终会终止无限刷新」，那是因为替身没记录刷新 / 确认点击，只有滑动记录在累计；真实记录里每轮还有刷新和确认的点击，同名占不到 10、两个按钮各不到 6，而福利业务上本来就允许无限多轮（D-09），所以改为 `test_batches_without_progress_never_release_their_static_swipe_records_and_stay_bounded`（static 记录一次不清、每批恰好 2 次滑动）；`test_unsent_swipe_writes_no_record_and_releases_nothing` 的 `record_add` 断言收窄到滑动名（替身现在也记录预设等点击）。
- **修复前后**：把旧行为原样还原（不释放候选记录 / 不确认刷新结果 / 不回顶 / 旧指纹判据）在新用例上跑，31 项中 16 项失败；单独还原每一项各有对应用例变红（释放 3、刷新就绪 2、回顶 5、指纹 5）；变异 2 条（不看有效标记就清记录 / 指纹不做对齐）均变红；修复后 31 项全部通过。
- **未验证 / 待真机**：① 刷新后列表是否回顶、新一批是否自动回顶（回顶滑动方向 / 幅度是反向派生的，未经真机验证，每次刷新会多约 2 次 static 反向滑动的时间）；② `REFRESH_CHANGED_COVERAGE`（0.05）没有真机刷新前后画面，未校准，日志会输出实测值；刷新结果「恰好与旧列表完全相同」的短列表会被当成未生效转人工；③ 刷新中的加载态（空白 / 转圈）画面未知，列表稳定判据可能把加载态当成就绪；④ 货币不足 / 刷新限制没有专门的弹窗模板，只能靠「列表没变化」间接判断；⑤ 指纹阈值 6.0 的真实样本很少；⑥ 其余：投票、D-01 其余部分、准备阶段反复失败不计入 `failure_record`、跨进程遗留的异常 Restart 仍按启动规则跳过（见 §4.153 D-07）。

### 4.155 每日琐事调度：下一个服务器刷新（09:00）与 12 / 20 点时段点取较早者

2026-10-29。未提交（在工作区）。**Level A/B（离线）PASS；真机未验证。**

- **需求**（用户）：每天开 OAS 时每日琐事要最先能跑（正常调度）；12 点、20 点庭院寿司时段仍各跑一次，都带随机延迟；晚上庭院事务跟日常调度、到点没做就补；优先级和随机延迟（`float_time`）由用户自己配置。**原来的问题**：`plan_next_dt` 每次正常结束都把 next_run 整个改成 12:00 / 20:00 / 次日 12:00（`custom_next_run`，`server=True`），配置的 `success_interval` 完全没用上；「每天早上先跑」靠的是一个没找到来源的机制（日志里每天 09:13~09:50 DailyTrifles 的 next_run 被改成「当前时间减一天」，Restart `enable_daily`、队伍同步 `task_call`、XinLan 都不会这么改），不能当作保证。另外 `custom_next_run` 默认 `server=True`：公共 `task_delay` 只在 `server_update` 恰为 09:00 时才加随机延迟，换成别的值会把目标推到明天。**新规则**（`tasks/DailyTrifles/script_task.py`）：下次运行 = `next_daily_time`（下一个服务器刷新 `scheduler.server_update`，默认 09:00；此刻已到或已过则明天）与 `next_slot_time`（今天 12:00 / 20:00，过了 20:00 是明天 12:00）中较早的一个，再加任务自己的 `float_time` 随机延迟（`random_int(0, float_time 秒数)`，只加一次）；以 `server=False` 交给 `set_next_run`，不受 `server_update` 影响。效果：每天 09:00（+延迟）一次、12:00（+延迟）一次、20:00（+延迟）一次；开 OAS 时 09:00 通常已过，每日琐事立刻到点。**不用「成功时间 + success_interval」**：12 / 20 点的运行会拖动锚点，随机延迟累计后每天往后漂，且取较早者时 12 / 20 点总是先到，等于现状。`run()` 本身不分模式：各功能已有「今天做过没有 / 当前时段」判断，三种触发共用；晚上庭院事务由 20:xx 那次运行按当前时段（≥18:00 = evening）去做，没做到就在下一次到点时补。**不变**：失败路径（异常不调用 `plan_next_dt`，Restart 后立刻重试，连续 3 次退出）、各功能逻辑、优先级（用户自己调）。
- **测试**：新增 `tests/test_daily_schedule.py` 9 项（真实 `BaseTask.set_next_run` → 真实 `Config.task_delay`）：连续 7 次按排好的时间运行得到 12:00 / 20:00 / 次日 09:00 / 12:00 / 20:00 / 09:00 / 12:00；随机延迟范围与确实随机、只加一次；`server_update` 改成 05:00 时时段点不被推到明天、日常锚点跟着配置；09:00 整点之后的下一个刷新是明天；时段点边界；不使用 `success_interval`；早上那次实际 10:10 才跑也不影响之后的排期。变异 6 条各有测试变红（取较晚者 / 日常总是明天 / `server=True` / 不加延迟 / 20 点后排今天 / 把 `success_interval` 算进去）。`tests/test_daily_trifles.py` 里旧的 `plan_next_dt` 用例改成新契约（旧断言是 `custom_next_run` 的 12 / 20 点参数）。{BASELINE}
- **未验证（全部待真机）**：开 OAS 后每日琐事是否最先（优先级由你配置，现在是 4，前面还有 Restart / 结界等）；09:00 + 随机延迟那次运行与 12 点那次的间隔；晚上庭院事务在 20:xx 那次运行里是否按 evening 时段正常做；随机延迟你配得过大时（如 1 小时多）仍可能把寿司时段（12–14 / 20–22）挤出去，这是配置问题，代码不再限制。

### 4.156 福利道馆：再战之后若仍停在道馆页，复用现有退出导航回到地图（定点修复 A）

2026-10-29。未提交（在工作区）。**再战后返回找馆页的道馆退出分支已补齐并完成离线验证，等待完整福利道馆实测；最后一馆特殊投票收尾（B）仍待画面确认。**

- **缺口与证据**：旧 `_back_to_find_page` 只点黄色返回键。用户 2026-10-25 标注器整屏截图（原文件已不在磁盘，内嵌在会话记录里）离线匹配：道馆页（含投票页）黄色返回键 0.389（不匹配）、`I_RYOU_DOKAN_DOKAN_QUIT` 0.993；地图页反过来（黄色返回键 0.983、退出图标 0.505）。所以再战等待后若仍在道馆页，旧实现永远离不开，只能等 90 秒转人工。**再战之后到底停在哪一页没有证据**（投票页 20:59:04 与下一张地图找馆页 21:00:32 之间没有截图），本次只是同时支持两种起始页面，不改再战业务规则。
- **修复（只改 `tasks/Dokan/welfare.py::_back_to_find_page`，新增参数 `leave_dokan_page=False`，只有 `_run` 里再战等待之后传 True）**：循环顺序不变——找馆页 → 直接返回；进行中的馆（`FOUND`）→ 转人工；新增：`leave_dokan_page` 且看到道馆页标志（`I_RYOU_DOKAN_CHECK`）→ 调现有 `task.goto_page(pages.page_dokan_map, timeout=剩余时间)`，由 `page.py` 33-37 的 `page_dokan → page_dokan_map`（退出图标 → 退出确认）导航处理，不复制点击循环；**导航返回后 `continue`，下一轮重新截图判断**（找馆页 → 返回；进行中 → 转人工；其它 → 沿原来的黄色返回键 / 到 deadline 转人工）；同一次调用里导航最多 `DOKAN_EXIT_TRIES`（2）次，导航「返回了但仍在道馆页」超过次数转人工。预设返回（`timeout=15`）和默认调用不传该参数，行为不变，不扩大为任意页面都走退出导航。
- **真实边界（核对 `tasks/GameUi/navigator.py` 770-890）**：`goto_page(timeout)` 是**无进展**超时，不是总时限——页面变化 / 转场推进会重置计时，到点抛 `GamePageUnknownError`（`_log_navigation_timeout` 末尾 raise）；所以外层 `deadline` **不能**中断这次调用，这里只把剩余时间作为它的 timeout 上限（不重置方法总时限）。`GamePageUnknownError` 在已开馆之后由 `WelfareDokan.run()` 转成 `RequestHumanTakeover`（不是 Restart），导航失败不会重新投票、不会重新等待 120 秒（它们都在本方法之前，且各只执行一次）。设备 / 截图异常和停止信号不被捕获。
- **三种地图结果**：finding → 返回，继续找下一馆（第二馆不重复建馆和预设）；found → 沿用「回到地图后发现存在进行中的道馆」转人工；unknown / 认不出 → 导航自己的无进展超时抛 `GamePageUnknownError`（转人工），或导航返回后重新截图仍认不出则按原 deadline 转人工。
- **并发说明**：本轮开始时另一个会话正在改同一个测试文件（`World` 的 `after_again` / `exit_mode` / `exit_result` / `exit_delay` 和 `FakeTask.goto_page` 按真实 `pages.page_dokan.transitions` 导航的替身）；我没有覆盖它的内容，复用了这些替身，只追加了 `RematchReturnTest`。
- **测试**：`tests/test_dokan_welfare.py::RematchReturnTest` 15 项（真实 `_back_to_find_page`；替身 `goto_page` 在「目的地 = 地图且当前在道馆页」时取 `pages.page_dokan.transitions` 里真实的「退出图标 → 退出确认」序列逐步识别点击、用新截图确认到达，无进展超时抛 `GamePageUnknownError`）：起始找馆页不走导航；道馆页走退出图标 + 确认各一次后回到找馆页；导航 timeout 受剩余时间限制；退出后仍是进行中的馆 → 转人工且不搜索；认不出的画面 → 导航超时、有界；退出图标 / 退出确认没反应 → 导航失败不当作成功；导航失败后不重新投票、不再等 120 秒；导航「返回了但仍在道馆页」→ 有限次后转人工（不把调用返回当到达）；转场延迟后用新截图确认；截图 / 设备 / 停止信号原样传播；整条两馆流程投票 → 等一次 120 秒 → 退出道馆页 → 第二馆，建馆和预设各只一次；游戏自己回到地图时完全不走退出导航；最后一馆不走这条链；预设返回 / 默认调用不走退出导航；旧实现停在道馆页只能超时。
- **修复前后**：还原旧实现，15 项中 12 项失败（凡涉及道馆页的）；变异 4 条（退出分支对任何调用者生效 / 不限导航次数 / 导航后直接返回 / timeout 不收紧）均有测试变红；修复后 15 项通过。
- **验证**：`compileall -q tasks/Dokan/welfare.py tests/test_dokan_welfare.py` 通过；相关 351 项（福利 / 普通模式 / D-07 / 登记册守卫 / L1·L2）通过；全量 `unittest discover -s tests` 只跑一次：**3466 项 OK（skipped=2）**，13:10:08 开始、13:16:42 结束，开始前后 `git status` 条目数（192）与 `welfare.py` / `test_dokan_welfare.py` / 登记册 / `script.py` 哈希不变（总数比上一轮多出的部分来自并行会话的测试）；点击登记册重新生成无差异（没有新增点击调用点，`goto_page` 不是点击调用）；完整输出在 `D:\Codex\workspace\d10\`。
- **未验证 / 待真机**：再战选择成功并等 120 秒后实际停在哪一页（道馆页 / 地图找馆页 / 进行中）；道馆页的退出确认框真实样子（`I_RYOU_DOKAN_EXIT_ENSURE` 来自上游，本地没有该框的真实截图）；`goto_page` 在真实游戏里从道馆页退出的耗时。最后一馆放弃后不会出现再战（用户已确认），不再为假设中的投票页面补分支。

### 4.157 福利道馆：再战成功后的 120 秒等待与公共卡死保护衔接（收尾修复）

2026-10-29。未提交（在工作区）。**福利道馆本轮代码修复与离线收尾完成，等待用户完整实测；不宣称真机已通过。**

- **已确认的业务规则（用户）**：两馆都必须放弃——第一馆：准备后关闭 → 等 600 秒 → 登录返回 → 放弃 → **再战** → 等 120 秒 → 找第二馆；第二馆：准备后关闭 → 等 600 秒 → 登录返回 → 放弃 → 核实次数 → 收尾（**最后一馆放弃后不会出现再战**，不再为假设中的投票页面补分支）；首次找馆、第二馆首批列表的回顶问题**不处理**，保持当前行为（刷新之后的回顶仍是 D-09 的已做内容）。
- **问题（以当前源码重新核对）**：`_run` 里 `_abandon` → `_vote_again()`（点击再战 → `wait_for_changed_and_stable` 逐帧截图，最多 8 秒）→ `_wait_again()`（`_wait(120)`，**无截图**）→ `_back_to_find_page()` 首次 `screenshot()`。`Device.screenshot()` 在取画面前先 `stuck_record_check()`：`stuck_timer = Timer(60, count=60)` 的 `reached()` 每次检查 +1 计数，要求「距最近一次清除超过 60 秒」**且**「自那以后的检查次数 > 60」才抛 `GameStuckError`。再战点击会清计时和计数；120 秒等待时间条件一定满足；投票确认阶段的帧数不固定（截图间隔被夹在 0.1～0.3 秒，按钮变化到稳定可能要好几秒），一旦 > 60，等待之后的第一次截图就在识别页面之前被判成卡死（开馆之后由 `run()` 转人工）。之前「约 35 帧所以安全」只是估算，不是保证。
- **修复（只改 `tasks/Dokan/welfare.py::_wait_again`，一行）**：`_wait(AGAIN_WAIT_SECONDS)` 正常结束之后调用一次 `self.task.device.stuck_record_clear()`。只重置 stuck 计时和检查次数；**不动 `click_record`**（`stuck_record_clear` 不碰点击记录，点击重复计数是另一套）；不改 `Timer.count`、60 / 300 秒阈值，不新增接口 / 上下文管理器，不登记长等待（登记 `PAUSE` 等最多延到 300 秒，且这里不需要）。清除放在等待**已经等满之后**：`_wait` 是分段 `sleep`（≤ 1 秒一段），停止信号 / 异常从等待里传出时不会走到这行（没有 `finally`），不做任何业务收尾；等待只执行一次、总时长不因保护而重新起算；这 120 秒是在线等待，不进 `_excluded_from_active()`，不暂停疲劳 / 活跃计时，不增加 `excluded_active_seconds`；600 秒离线等待的计时和疲劳处理不变；清除之后没有任何豁免，之后真正的无进展照常触发公共保护。
- **测试**：`tests/test_dokan_welfare.py::AgainWaitGuardTest` 11 项——设备带真实 `Device.stuck_record_check / clear` 与真实 `Timer`（`World(stuck_guard=True)`，时间取虚拟时钟）；替身新增 `snap_step`（每次截图推进的虚拟秒数，用 0.1）和 `vote_change_delay`（再战点击之后按钮框晚多少秒才变，用来制造「等待前检查次数 > 60、时间 < 60 秒」）。覆盖：等待前累计 > 60 次检查时等待后的第一次真实截图不误报（整条两馆流程同样通过）；检查次数少时原路径通过；等待结束后继续长期无进展仍抛 `GameStuckError`、没有留下登记 / 豁免、公共检查方法与阈值未被替换；只等待一次（一整块 120 秒、期间没有截图 / 点击 / 滑动、分段）；整条流程只投一次票、只等一次、两馆都放弃、第二馆不再战不等待；在线计时（不调用 `suspend_active`、不增加 `excluded_active_seconds`，只有两次 600 秒离线等待被排除）；`KeyboardInterrupt` / `SystemExit` / `OSError` 从等待传出后没有清除、没有截图 / 导航 / 点击；`click_record` 不变；再战后停在道馆页的退出导航回归。
- **修复前后**：旧实现（只等待）在等待后的第一次真实截图触发 `GameStuckError: Wait too long`（整条流程被 `run()` 转成 `RequestHumanTakeover`，`__cause__` 是 `GameStuckError`，不继续找第二馆）——修复前新用例 11 项中 5 项失败（全是这个原因）；变异 5 条（清除放在等待之前 / 放进 `finally` / 改清点击记录 / 把等待放进离线排除 / 等待两次）均有测试变红；修复后 11 项通过。
- **验证**：`compileall -q tasks/Dokan/welfare.py tests/test_dokan_welfare.py` 通过；相关 362 项（福利 / 普通模式 / D-07 / 登记册守卫 / L1·L2）通过；点击登记册重新生成无差异（没有新增点击调用点）；全量 `unittest discover -s tests` 只跑一次：**3477 项 OK（skipped=2）**，15:07:25 开始、15:12:57 结束，开始前确认没有其他 unittest 进程，开始前后 `git status` 条目数（192）与 `welfare.py` / `test_dokan_welfare.py` / 登记册 / `script.py` / `test_restart_recovery_first_task.py` 哈希不变；完整输出在 `D:\Codex\workspace\d10\`。
- **未验证 / 待真机**：真实截图间隔与投票确认的实际帧数；其余福利道馆待真机项见 ROADMAP「福利道馆模式 Level C 验收」。

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

**当前基线（2026-10-29，发布候选口径：HEAD `cf1c8a48` + 本次提交的 198 个文件，在仓库外的隔离副本里跑，不含被排除的 10 个文件、`config/oas*.json` 与 `log/`）**：
`toolkit/python.exe -m compileall -q module tasks tests script.py` 通过；
`toolkit/python.exe -m unittest discover -s tests` = **3477 项运行 OK（skipped=3）**，只跑一次，2026-10-29 15:50:55 开始、15:56:46 结束，期间副本与仓库里纳入提交的文件哈希都没变（副本里只多了测试自己生成的 `config/oas.json` 和日志）。skip：`RealLocalConfigTest` 1 项（副本里没有真实 `config/oas1.json` / `oas2.json`，在工作区里会跑并通过——说明个人配置不是其它测试的隐性依赖）；`OfflineTemplateStateTest` 2 项（依赖的 annotator 抓图已不在 `log/annotator/`，工作区里同样 skip——悬赏封印详情两个状态模板互不命中的离线检查目前没有在任何地方跑过）。完整输出 `D:\Codex\workspace\oas-release-review-20261029\13_full_suite.txt`。

**上一基线（2026-10-25，工作区口径：master 上 §4.134 已提交、未推送；其余 §4.110 ~ §4.133 仍未提交）**：
`toolkit/python.exe -m compileall -q module tasks tests` 通过；
`toolkit/python.exe -m unittest discover -s tests` = **3477 项运行 OK（skipped=2）**（§4.157 福利道馆再战后 120 秒等待与公共卡死保护衔接：新增 `AgainWaitGuardTest` 11 项，一次全量，开始前后工作区无变化，完整输出在 `D:\Codex\workspace\d10\full_suite2.txt`；上一轮 3466 项 OK：§4.156 福利道馆再战返回的道馆页退出分支：新增 `RematchReturnTest` 15 项，一次全量，开始前后工作区无变化，完整输出在 `D:\\Codex\\workspace\\d10\\full_suite.txt`；上一轮 3437 项 OK：§4.154 福利道馆 D-09 / D-08：新增 `RefreshClosureTest` 17 项 / `CandidateRecordTest` 8 项 / `CardIdentityTest` 6 项；一次全量，开始前后工作区无变化，完整输出在 `D:\Codex\workspace\d09ull_suite.txt`）；上一轮：**3397 项运行 OK（skipped=2）**（§4.153 福利道馆 D-07，新增 `test_restart_recovery_first_task` 13 项；一次全量，开始前后工作区无变化，完整输出在 `D:\Codex\workspace\d07\full_suite.txt`；上一轮 D-05：**全量跑了两次（第一次输出被截断后又重跑了一遍，违反「只跑一次」）：第一次 3373 项、2 项失败，第二次 3384 项、3 项失败（`test_daily_pickup_email` 两项 + 登记册守卫一项）；两次之间测试数 3373 → 3384，期间工作区被其他会话改动（`DailyTrifles` / `Restart` 资源，与本轮无关）；这些失败来自对方改到一半，本轮改动范围的 238 项（福利 / 普通模式 / 登记册 / L1·L2 集成）和 `test_daily_pickup_email` + `test_daily_trifles` 70 项在当前工作区复跑通过，没有再跑第三遍全量；skipped=2**（§4.152 福利道馆 D-05，`test_dokan_welfare` 新增 `GatherGuardTest` 17 项；上一轮 3356 项运行 OK（skipped=2）：§4.151 福利道馆 D-02，`test_dokan_welfare` 新增 `OwnDokanTest` 21 项 / `OrdinaryCreateCompatTest` 5 项 / `OwnDokanIconResourceTest` 3 项，`test_dokan_normal_mode` 新增 `RunOnDokanMapTest` 4 项；上一轮 3323 项运行，首轮全量 2 条登记册守卫失败（已重新生成登记册，相关 325 项复跑通过，未再跑第二遍全量；skipped=2）：§4.150 福利道馆 D-06，`test_dokan_welfare` 新增 `PresetFlowTest` 17 项、删旧预设用例 1 项；上一轮 3307 项 OK（skipped=2）：§4.149 福利道馆 D-04，新增 `SwipeRecordTest` 17 项；再上一轮 3290 项 OK（skipped=2）：§4.148 福利道馆 D-03，新增 `SwipeProgressTest` 20 项；再上一轮 3270/3270 OK：§4.147 悬赏封印新详情界面，新增 `test_wanted_quests_detail_flow` 38 项；再上一轮 3232/3232 OK（首轮全量）：§4.146 契灵锁队衔接，新增 `test_bondling_team_lock` 17 项；再上一轮 3215/3215 OK（首轮全量）：§4.145 契灵创建房间修复，新增 `test_bondling_create_team` 20 项；上一轮 3195/3195 OK：§4.144 SwitchSoul 按名称收尾，`test_switch_soul_name_search` 37 → 61 项；上一轮：3171 项运行，仅 1 项统计性用例随机抖动失败（1 项 skipped）；§4.143 SwitchSoul 按名称搜索新增 `test_switch_soul_name_search` 37 项；此前 3134/3134 OK：本轮 §4.142 福利道馆匹配格式修复使 `test_dokan_welfare` 新增 9 项，与上一基线 2961 的差额还含工作区其它改动，未逐项归因；此前 `2941 → 2961` = §4.134 百鬼棋局上游选择性合入：新增 `test_chess_upstream_selective_merge` 30 项、删去早先的 `test_chess_hand_recovery_upstream_0501cb19` 10 项；`2927 → 2941` = 早先那 10 项 + 工作区 `test_secret_settlement_region` 新增 4 项（非棋局，本轮之前已在工作区）；此前 `2912 → 2927` = §4.133 循环配置显示与保存，新增 `test_loop_config_ui` 15 项；此前 `2907 → 2912` = §4.132 名称模式总超时，`test_switch_soul_replace_dialog` 22 → 27；此前 `2900 → 2907` = §4.132 有界保护补齐，`test_switch_soul_replace_dialog` 15 → 22；此前 `2885 → 2900` = §4.132 预设切换契灵替换确认框，新增 `test_switch_soul_replace_dialog` 15 项；此前 `2862 → 2885` = §4.131 地域鬼王战败有限重试，新增 `test_area_boss_retry` 23 项；此前 `2844 → 2862` = §4.130 狩猎战随机延迟，`test_hunt` 20 → 38；此前 `2820 → 2844` = §4.129 通用战败页结算改点右侧 / 底部区域，新增 `test_ryoutoppa_settlement_avoids_again_button` 24 项，更新 `test_general_battle_settlement` CASE 13 一项；此前 `2784 → 2820` = §4.128 第二轮定点修复（外部停止覆盖内层开战点 / 让出撤回就绪 / 可信计数证据顺序 / 恢复期间不回退原始列表 / β 裁决进门口），`test_loop_script_glue` 33 → 51、`test_orochi_loop` 18 → 27、`test_realm_raid_loop` 4 → 12、`test_loop_multiprocess` 6 → 7；此前 `2665 → 2784` = §4.128 御魂 → 个人突破循环，新增 5 个测试文件共 115 项（`test_loop_controller` 54、`test_loop_multiprocess` 6、`test_loop_script_glue` 33、`test_orochi_loop` 18、`test_realm_raid_loop` 4），改 3 个既有结构守卫；其余增量来自同期工作区的其它改动；此前 `2655 → 2664` = §4.127 组队会合启动宽限，`tests/test_team_sync.py` 67 → 76 项，改 1 项既有断言（`peer_running_alone` 由推迟改为等待）；此前 `2622 → 2655` = §4.126 组队会合补强，`tests/test_team_sync.py` 52 → 67 项（改 1 项），新增 `tests/test_orochi_team_progress.py` 18 项；此前 `2608 → 2622` = §4.125 组队会合改造，`tests/test_team_sync.py` 38 → 52 项（改 3 项既有用例）。更早的增量链（`2260 → 2608`，§4.111 ~ §4.124）与当时的基线原文在 `docs/archive/AI_CONTEXT_history.md` §7 的「2026-10-21 ~ 10-23 基线增量链」一节）。全量约 112 ~ 150 秒。

历史基线（2026-10-20 及更早）与各模块测试覆盖面说明已移到 `docs/archive/AI_CONTEXT_history.md` §7。

修改上述模块后，至少重新运行对应测试。未经用户授权，不进入设备或游戏内测试。

## 8. 已知非阻断问题

- **GlobalGame 好友邀请弹窗的猫粮 / 狗粮认不出（2026-10-29 发布审查发现，相关文件未提交、留在工作区）**：用户 10-28 重标的 `gg/image.json` 把 `g_cat_food` / `g_dog_food` 的识别框改成 (675,516,43,46)，模板图仍是 59×65 / 60×63；图像服务在模板大于搜索区时直接返回不命中（`module/image/runtime.py` `_template_match_image`），不会报错。影响：好友邀请设成「接受勾协和粮协」时，粮协邀请会被当成其它邀请点「忽略」。oas1 / oas2 当前都是「忽略」，不受影响。仓库里（`origin/master`）仍是旧界面的坐标。修法要新界面上粮协邀请的整屏截图（见 ROADMAP）。
- **全量测试里有一个时钟依赖用例（2026-10-13 发现，自 2026-09-25 `139f3bcd` 起就存在）**：`tests/test_kekkai_utilize_convergence.py` 的 `test_case10_system_errors_are_not_swallowed_by_the_guard` 直接调 `run()`，没有 stub `_guard_quiet_window`；本机时间落在 KekkaiUtilize 静默窗口（凌晨，窗口由配置给出）时 `run()` 先 `raise TaskEnd`，测试期望的 `GameStuckError` 走不到，全量多 1 个 ERROR。白天全绿；同一时刻 `origin/master` 同样失败，不是回归。修法：case10 里 patch `_guard_quiet_window` 返回 False 或固定时钟。**已解决**：§4.120 给两处 `t.run()` 套上固定时钟。
- **SixRealms 商店 P1/P2（2026-10-07 孔雀国六道轰雷漏买专项确认，P0 已由 §4.101 修复；2026-10-12 §4.108 只动了 ③ 的验证侧，并在轰雷路径上缓解了 ① 的金币读数滞后，其余未动）**：① 刷新确认后 0.21~0.26 秒就用同一帧做商品识别 + 金币 / 剩余次数 OCR，14 次刷新里有 5 次 HUD 数字仍是旧值（该帧上的商品识别结果不可信，下一步直接再刷新，那一套商品从未被可靠地看过）——§4.108 只在带 `expected_cost` 的孔雀国轰雷路径上改为取稳定金币读数（商品识别因此晚约一帧），刷新等待与识别本身未动；② `refresh_store` 的 `wait_animate_stable(timeout=1.5)` 在点刷新图标之后、确认弹窗出现时就返回（约 0.75 秒），根本没等到「确认之后真正重新发牌」的动画，且 `C_STORE_ANIMATE_KEEP` ROI (825,87,317,466) 盖不到商店第 3 行（y>553）和第 1 列；③ 价格写死 300，孔雀国 3 次真实购买金币差都是 200（月之海是 300）——2026-10-12 §4.108 只把**验证**改成按 200 核对（`PK_SKILL_THUNDER_COST`），买入门槛仍是 300；④ `coin < price` 的闸门排在 `appear(skill)` 之前，金币 200~299 时轰雷看得见也没机会被识别 / 购买；⑤ `refresh_time = int(matches.group()[1])` 只取第一位数字（现在最多 3 次，不触发）；⑥ 战斗 HUD `I_PK_BATTLE_THUNDER` 置位 `skill_roaring_thunder = 1` 没有日志。这些要等真机帧（点击前后 +0.0 / +0.3 / +0.8 / +1.4 秒、完整商店网格、购买弹窗）再动，不能凭推测改。
- `tasks/Component/CostumeShikigami/assets.py` 存在 20 处 upstream 生成注释行尾空格，会触发 `git diff --check` 提示。当前决定是不为此单独修改生成文件。
- Image frame 注册发生在部分方向修正前。
- 同一 `config_name` 的多个截图生产者会竞争 frame——**2026-10-10 已确认**：图像服务全局只有一个（`127.0.0.1:22269`），`ImageRuntime._config_frames` 每个 `config_name` 只保留一帧，`register_frame` 会删掉同配置的旧帧（`module/image/runtime.py:237-242`）。annotator 实时采集用的是完整的 `Device(config=<同名配置>)`，每次 `screenshot()` 都会按同一个 `config_name` 注册（`module/device/screenshot.py:75`），于是把正在运行的 OAS 手里的帧挤掉，OAS 下一次匹配就 `KeyError: Unknown frame id`（oas2 15:30:14.302 OAS 注册帧 → 15:30:14.611 annotator 首帧 → 15:30:14.636 报错；同日只开 annotator、或只跑 OAS 的时段都没有出错）。**临时规则：某个配置的 OAS 在运行时，不要用同一个配置开 annotator 实时采集；需要实采先停该配置的 OAS（上传图片不受影响）。** 另外 2026-10-07 那次 `Unknown frame id`（oas2，Chess `_hand_card_detections`）是另一种原因：同一帧在 16 秒后才用来匹配，超过服务端 10 秒 TTL 被清掉，与 annotator 无关。隔离方案（annotator 截图不注册帧）已于 2026-10-21 实施（§4.113，Level A/B），Level C 待验；验证通过前上面的临时规则继续有效。
- Image/OCR RPC 运行中断线后没有自动恢复。
- low spec small OCR 可能需要首次下载，离线环境可能失败。
- 诊断导出 endpoint 尚未确认统一有效鉴权。
- AntiBan 的跨日任务计时和进程重启清零行为尚未持久化。
- `Script._publish_fatigue_state` 是独立的 2 秒轮询线程，且禁用疲劳时仍持续推送、无退出条件，与“前端复用现有状态刷新链路、不单独增加高频轮询”的意图有出入。记录为后续 P2 架构审查项，本轮不改。
- GlobalFatigue 进程内累计、进程重启清零，无持久化（与既定设计一致，不为此新增持久化系统）。
- **SwitchSoul（2026-10-06 两轮只读审查 + 日志复盘确认，§4.99 只处理其中数字模式时序，其余未动）**：① 两条切换路径都没有「目标预设已生效」的判定（数字模式盲点、OCR 模式只数点击次数），`run_switch_soul*` 返回 `None`，失败后任务带着任意御魂继续；② 配置值 `-1,-1` / 越界在进页滑顶之后才抛 `ValueError`，被调度器当未识别异常 `exit(1)`，只有 ActivityShikigami / MartialArts 会预校验，格式错误（如中文逗号）却是静默 `return`；③ 数字模式「滑到顶」（**已由 §4.100 SwitchSoul V2 修复**，下面是修复前的行为，保留作历史）：旧调度多数情况下只执行 1 次真实 swipe；是否允许后续 swipe 取决于 OCR + 循环耗时是否超过 1.5 秒的 `interval`（一轮通常约 0.9~1.1 秒，OCR 偏慢时才放行，真机 BehaviorTrace 里 12 次数字切换有 1 次真滑了 2 次），因此行为具有时序偶然性，不是「原设计只滑一次」；④ OCR by-name 的找组 / 找队循环无局部上限，名字找不到时靠 Device 的同名 10 次点击守卫收口（今天 oas1 的 by-name「秘闻 → 通用」日志中断在找队搜索，找队每次只滑约 51 px）；⑤ OCR by-name 查找用精确相等、点击用子串 + 合并框，名字互为前缀时可能点错行（静态推断）；⑥ Dokan 的 OCR 分支读 `dokan_{type}_switch_soul_by_name`，该配置字段不存在，分支不可达；⑦ AbyssShadows 把 `run_switch_soul` 里的所有异常（含 `GameStuckError` / `GameTooManyClickError`）转成 `RequestHumanTakeover` → `exit(1)`；⑧ 约 24 个任务入口复制同一段「`enable` + `enable_switch_by_name`」调用块，两个开关同时开时的优先级各任务不一致；⑨ 文件日志会合并连续相同内容，日志里的「1 行」不等于「1 次」。
- **标注工具实时画面与运行中的脚本抢同一个截图槽位（2026-10-20 发现，2026-10-21 已修 Level A/B，Level C 待验）**：图像服务对每个配置名只保留一帧，新帧注册时删掉同名旧帧（`module/image/runtime.py` `register_frame`）；annotator 打开实时画面时，后台进程用 `Device(config=Config(<所选配置>))` 每 0.5 秒 `screenshot()`，以同一个配置名注册（`module/server/tool_capture_worker.py`），于是运行中的该配置脚本刚截的帧被顶掉，下一次匹配报 `RemoteError … KeyError: Unknown frame id`，属未处理异常，进程 `exit(1)`。10-20 oas1 的 13:24:57 与 16:42 三次报错都落在 annotator `config=oas1` 实时画面期间，annotator 没开实时画面时没有出现。规避：脚本运行时不要对同一实例开 annotator 实时画面。已修（§4.113）：annotator 的 `Device` 不再注册帧；真机验证通过前，上面的规避办法继续保留。

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

- P0-D 前端数据链路：后端 `load_factor_preview` → `ui_snapshot` / `_default_fatigue_state` → `state_queue` / WS 广播这一段已就绪并有测试。缺口在 OASX Flutter 前端（独立仓库，不在本工作区）：`fatigue_load_factor_preview` 的解析、`fatigue_header_panel` 的“!”Tooltip 文案、Slider 当前档高亮、是否存在硬编码概率、前端多实例隔离、Flutter 3.35 `Tooltip.rich` → `Tooltip` 兼容与 widget test 均无法在此工作区核实。
- `Script._publish_fatigue_state` 独立 2 秒轮询循环列为 P2 架构审查项。
- **`Device.drag()` 当前零业务调用方**：`module/device/method/minitouch.py` 的 `drag_minitouch` 及其 `control.py` 入口在 `tasks/` 与 `module/` 内无调用者，属死路径。真正生效的拖拽是 `tasks/Chess/runtime/press_and_drag.py`。清理死路径前需确认没有外部脚本依赖。
- **KekkaiUtilize 单向分区搜索改造已实施（§4.41 / `docs/DECISIONS.md` D017，2026-09-03）**——§4.40 审查提出的三大差异（跨区优先默认反了 / 同屏非星级序 / 默认阈值使行为=扫全+回选）已由「PASS 序列（跨→同→跨→同 或 同→跨→同）+ 第一阶段 6★HIGH / 第二阶段 5-6★ 降一档 + 命中即寄养 + 最后一 PASS 兼兜底」解决。global-best / `_reselect_best_card` / 蛇形 / `miss-as-bottom` 已从标准路径移除；怠惰模式不变。回归 759→783。**剩余全是 Level C 真机待验收**（`docs/DECISIONS.md` D017 末尾 + §4.41 末尾）：`I_U_EMPTY_CARD` 是否 100% = 到底、切区是否稳定回顶、`SWIPE_DISTANCE=416` 覆盖性、card-column ROI 是否需扩大、ADB→minitouch 滚动量、`FINAL_USE_LAST` 依赖的「最后候选保持选中」、`SEARCH_MAX_SWIPES=20` 是否够、列表/详情卡种偶发不一致。**下一轮独立 Level C 项**：结界卡 ROI 扩展、`perform_swipe_action` ADB→minitouch。
- KekkaiUtilize 仍未处理的记录项：`check_utilize_add` 中「5 轮未蹭上」返回 `True` 与 `_record_utilize_failure` 路径返回 `False` 的语义不一致（不影响正确性；改会让 `run()` 提前 return 跳过后续维护，需产品决定，cleanup 批次 1 deferred）。（`last_best_index = 99` 死属性已于 2026-09-02 cleanup 批次 1 删除，见 §4.36。）
- Kekkai 状态机静态收口（§4.33）记录项，完整表见 `docs/Kekkai状态机静态收口.md` §9。**cleanup 批次 1（§4.36）已删**：`KekkaiActivation` 死 import `parse_rule`。**仍未修**：`check_card_num` 子类覆写改返回类型（`RuleClick` vs `(str,int)`，latent，KA 当前不进 `run_utilize` 路径故无运行时冲突）；`harvest_card` 8 连点无截图 / 无验证 / 无 reward 闭环（Level C，T4-4）；`KekkaiActivation.check_card_num` swipe 用 stdlib `random.randint`（**KEPT**——D007「已存在未迁移用法保留」+ `RyouToppa.flush_area_cache` 同款先例，留未来专门随机源 pass）；`run_activation` / `screening_card` 的 4 个 `while 1` 无总超时（Level C）；`ocr_time()` OCR 失败 `return None` → `set_next_run(None + now)` → `TypeError`（crash 属实，正确恢复语义不唯一，deferred）；`run_utilize` U3 `goto_page` 失败仅 `logger.info` 不 return（deferred）。
- RealmRaid 状态机静态收口（§4.34）记录项，完整表见 `docs/RealmRaid状态机静态收口.md` §14。**cleanup 批次 1（§4.36）已删**：`medal_fire()` / `is_ticket()` / `medal_grid` 死代码（R-R7）、`AttackNumber` + `RealmRaid` 配置类死 import（R-R8）、随之变死的 `import time`。**§4.52 已收口**：`fire()` R-R1（正向 `is_in_battle()` 确认 + `RR_FIRE_MAX_TRIES` + `Timer(RR_FIRE_TIMEOUT)` + 三态 + 可达 `return False`）、R-R2（`run()` 两处 `if not self.fire(index): continue` 死分支现生效）。**§4.56 已收口**：`fire_again()` → `_fire_again()` 三态 bounded（R-R3 的不可达 `return False` 现可达）；`find_one` / `_grid_targets` 改在 `image.copy()` 上涂黑失败格、不再原地污染 `self.device.image`（R-R9）；`fire` / `_fire_again` 的 `wait_until_appear` 均带 `wait_time`（R-R5 部分）。**仍未修（Level C 耦合）**：`check_refresh` 尾部不可达 `return False`（R-R6）；`reward_detect_click` / `check_refresh` / `ensure_lock` 等自有 `while 1` 无总超时（R-R4）；`false_image` 复用 RyouToppa 的 `loser_sign_1.png`（R-R10）；目标点击仍用静态九宫格 `C_PARTITION_*` ROI（`_grid_targets` 把 `find_everyone` 匹配中心映射回 `roi_front` 后仍点 `C_PARTITION`，非识别到的勋章位置本身，R-R12）。
- Exploration 状态机静态收口（§4.37）是迁移前历史基线，完整表见 `docs/Exploration状态机静态收口.md` §14。**§4.58 / D021 已收口 E-5 与 Boss 后业务链**：`run_on_battle` 消费 `run_general_battle` bool，Boss win 后 positive map-ready → treasure bypass → bounded direct exit → positive entrance → solo Fatigue。其余记录仍在：`search_up_fight` 动态改写 `roi_front`（E-1）、`get_fire_button` 只在 `fire` 前定位一次（E-2）、`exec_exp_page` None 无连续上限（E-3）、`fire(False)` recovery 滑地图（E-4）、`page_reward` lambda（E-6）。Exploration `fire()` 的正向 battle page + `max_tries=4` + `Timer(10)` 本轮未改。
- 若后续明确要求，可单独评估 Image/OCR RPC 恢复、small 模型离线回退、诊断接口鉴权和 AntiBan 持久化。
- **同心之兰双实例互赠（2026-10-21）**：P1 同步核心（§4.111 / D029）与 P2 任务骨架（§4.112：`tasks/XinLan/`，`reset_unsafe` 在单独的 `reset` 分组、先关先落盘再确认）已完成；P4 适配器已写（§4.117，`tasks/XinLan/adapter.py`；`_build_adapter()` 按配置名返回先送 / 回赠适配器，未上真机）。P3 已采第一批资产并整理（§4.114：`tasks/GameUi/page/image_xinlan.json` 等；流程是先后依次进行、每次送出 30 勾玉、图标三态是证据；固定角色 + 依次执行；核心的可选钩子 `await_turn` 已加，§4.115）。**P5 双开真机：用户 2026-10-22 实机跑过一次，反馈「同心之兰功能没问题」；日志 / 账本没有回传，占位参数还没回填**（失败情况、第二天的状态、每步耗时仍要看，拿到日志后回填 `PROTOCOL_PARAMS` 的 `budget` / `min_attempt_cost` 占位，清单见 §4.117）。详见 `docs/ROADMAP.md` P0「同心之兰双实例互赠任务」。
- **组队会合修订（2026-10-23，§4.125 / D030 补记）**：到点就在门口等，对方会被拉进同一任务（空闲等待最多 5 秒被打断），不再按对方的计划时间推迟；对方在休息推迟到休息结束；等满 30 分钟推送一次。Level A/B 完成；待重启 OAS 后实机验。
- **组队会合补强（2026-10-23，§4.126 / D030 补记二）**：对方在场文件刚过期（5 分钟内，多半在重启）进门等不推迟不推送；御魂组队次数以队长为准（队长每场上报、打完报 done，队员不按自己的计数退出、对齐到队长的次数）。Level A/B 完成；待重启 OAS 后实机验。
- **组队会合启动宽限（2026-10-23，§4.127 / D030 补记三）**：脚本启动后 3 分钟内，对方不在线 / 文件过期很久也进门等，不推迟不推送（两边一起启动 / 重启，先起来的一边不再先推迟、几秒后又被拉回）；对方还在和我旧进程那一次组队时也进门等，不再推迟 10 分钟。对方真没开时，「不在线」推送最多晚约 3 分钟。Level A/B 完成；待重启 OAS 后实机验。
- **御魂 → 个人突破循环（2026-10-24，§4.128 / D032）**：首版只接御魂；Level A/B（含两个真实进程的文件协调测试）完成，**Level C 未做**。待用户两边开启组队同步并互填对方实例名后，分别在八岐大蛇设置里打开「开始循环」实机验，见 ROADMAP「御魂 → 个人突破循环 Level C 验收」。
- **点击接入 L2（2026-10-23，§4.124）**：每日琐事 / 狩猎战 / 集体任务所有点击都带档位（每次点击前有反应时间，整体变慢属预期）；庭院事务满级提取弹窗点取消。Level A/B 完成；待重启 OAS 后实机验。
- **集体任务（2026-10-23，§4.123）**：只做指定的任务（两个号都是「御灵一」），一直「换一个」到出现为止，换不到不捐、1 小时后再试，Level A/B 完成；待重启 OAS 后实机验。
- **狩猎战（2026-10-23，§4.122）**：麒麟 / 阴界之门保留完整打完的打法，修了开放时间、提前醒来空转、进入无上限、时段内重试，并把麒麟分成通用 / 雷麒麟（周四）两套式神录预设，Level A/B 完成；两个号的 Hunt 都还没开，待用户打开后实机验。
- **每日琐事（2026-10-22，§4.119 / D031）**：吉闻奖励关闭点、庭院事务多轮领取、完成记录与循环上限已修，Level A/B 完成；待用户开启每日琐事实机验。定时领庭院体力寿司已实现（§4.120），开关默认关，待用户打开后实机验。买体力补回被合并 `73bcafcb` 冲掉的修复并防多买（§4.121）；同一次合并丢掉的寮祈愿修复没补，见 ROADMAP。
- **组队会合（2026-10-22，§4.118 / D030）**：组队任务开始前先等对方实例到场，Level A/B 完成；待用户两边开启「脚本设置 → 组队同步」后实机看御魂 / 契灵一先一后到时是否互相等到。
- **annotator 帧注册隔离（2026-10-21，§4.113）**：Level A/B 完成；Level C 待验（脚本运行时开同配置 annotator 实时画面，确认不再 `Unknown frame id`），通过后可撤掉 §8 的临时规则。
- BehaviorTrace swipe 查询接口的 JSON 约定（前端待接，OASX 下一轮消费）在归档里：`docs/archive/AI_CONTEXT_history.md` 的「BehaviorTrace Swipe schema」一节。
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
15. **`AI_CONTEXT` 归档规则**：某个 §4.N 章节对应的改动已提交并推送、且不再影响当前开发（没有待真机验证项、没有未收口的后续）时，把整节原样移到 `docs/archive/AI_CONTEXT_history.md`，小节编号不变（其他文档和代码注释里的 `AI_CONTEXT §4.N` 引用因此不用改）；还要等真机验证的项目由 `docs/ROADMAP.md` 跟踪。§7 只留当前基线和最近两三步的增量，更早的基线、各模块测试覆盖面、§9 里已完成的条目一并移走。归档文件只增不改，不写进 §0 的 6 份文档职责表。
