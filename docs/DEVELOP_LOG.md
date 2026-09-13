# 开发日志

本文档按时间追加重要开发记录，不覆盖历史。只记录代码修改、merge、重要审查、测试和重大技术决策，不记录每一次搜索、单条命令或无意义探索。

## 2026-08-29 13:37 - upstream/self 整合完成

### 目标

将原作者 `upstream/self` 的最新修改整合到本地开发历史，在保留本地关键实现的同时完成静态审查、回归验证、双父 merge 和远程发布，并建立后续 AI 交接基线。

### 修改

- 解决全部显式 merge conflict。
- 人工融合 BaseTask `confirm_delay`、RuleSwipe、GeneralBattle、RealmRaid 和 minitouch。
- 保留 RyouToppa 本地完整实现，包括 FIRE 状态机、重试、恢复和任务级等待。
- 审查并保留 Image/OCR 的 low spec 相关 upstream 修改。
- 人工融合 diagnostic 隐私导出，确保日志写入 ZIP 前统一脱敏。
- 审查并保留 AntiBan 作息逻辑。
- 审查并保留 Chess、KekkaiUtilize、Costume、CostumeShikigami、BondlingFairyland 和 Sougenbi。
- 保持 NemuIPC 与 scrcpy 的 upstream 原版本。
- 创建 `docs/AI_CONTEXT.md` 和 `docs/DEVELOP_LOG.md`，建立持续交接规则。

### 技术决策

- `appear_then_click(..., confirm_delay=None)` 默认保持旧行为，不全局启用。
- RuleClick、RuleImage 和 RuleOcr 的点击坐标继续使用公共 `SystemRandom` 和完整 ROI 均匀随机。
- RuleSwipe 端点使用公共 `random_center_point_in_roi()` 中心偏置随机。
- GeneralBattle 的准备点击和结算点击时间统一复用公共 `random_delay()`，首次结算点击立即执行。
- RealmRaid 不恢复 `CLICK_REACTION_DELAY`，FIRE 不自动增加 `confirm_delay`。
- 普通 minitouch 点击使用 DOWN、45～130ms 等待、UP，不增加微小 MOVE。
- 不清理 `CostumeShikigami/assets.py` 中 upstream 生成的 20 处注释行尾空格。
- 诊断 ZIP 只在本地生成，不主动上传；鉴权问题留作独立架构任务。

### 验证

- 43 项回归测试全部通过。
- 36 个 staged Python 文件通过 `py_compile`。
- 23 个关键模块通过 import smoke test。
- 6 个 JSON 和 1 个 XML 解析通过。
- staged 资源引用和 PNG 解码检查通过。
- merge conflict marker、真实敏感信息、本机个人路径和临时调试残留扫描通过。
- merge commit 的双父关系和两个父提交的祖先关系验证通过。

### Git

- merge commit：`2cdf3a0571b0449748aabef259da5cbd2378536c`
- commit message：`merge: integrate upstream/self`
- parent 1：`880cd21fde5a5146cd923c0109b207d9ed234e3d`
- parent 2：`ce476e8943bb981c2cd91865cd734865c957c91d`
- 整合来源：`upstream/self`
- 整合分支：`integration/upstream-self`
- 当前分支：`master`
- 远程：`origin`，`https://github.com/Hualaijushi/OnmyojiAutoScript.git`
- 远程分支：`origin/master`
- 推送提交：`2cdf3a0571b0449748aabef259da5cbd2378536c`
- 推送方式：正常 fast-forward，未使用强制推送。

### 后续

- 重要开发任务开始前先阅读 AI 上下文和最近开发日志。
- 重要任务完成后更新当前状态快照，并追加开发日志。
- KekkaiUtilize 的跨区优先、六星结界卡、收益阈值和寄养搜索策略作为后续独立需求处理。
- Image/OCR RPC 恢复、small 模型离线回退、诊断接口鉴权和 AntiBan 持久化均应独立评估，不在其他任务中顺手重构。

## 2026-08-29 14:45 - 账号轮换分支同步通用安全加固

### 目标

将近期通用偏移点击、输入时序和安全加固选择性同步到 `origin/zoombies-account-rotation-dailytask/synevo`，同时保留该分支独立的多账号轮换和每日任务实现。

### 修改

- 同步公共随机、RuleOcr、RuleSwipe、BaseTask 二次确认和 minitouch 拟人化输入。
- 同步 GeneralBattle 与 RealmRaid 的准备点击和结算点击时序。
- 加入 AntiBan 作息约束和 KekkaiUtilize 最小再运行间隔。
- 加入 diagnostic 本地 ZIP 脱敏导出和对应接口。
- 加入 BaseTask、随机坐标、minitouch、战斗时序和诊断导出的测试。
- 在目标分支现有 `script.py` 调度器上局部融合 AntiBan，没有覆盖多账号运行时控制。
- 在目标分支现有中文 i18n 上追加安全配置键，没有覆盖账号轮换字段。

### 技术决策

- 从目标远程分支建立隔离 worktree，不在带有暂存文档的 `master` 工作区切换分支。
- 只同步通用且与账号轮换业务解耦的能力，不合入完整 `master` 或 upstream merge。
- 保持目标分支的 AccountRotation、MultiAccountEvo、GeneralInvite 和账号切换链路不变。
- 不同步 low-spec、NemuIPC、scrcpy、Image/OCR RPC、Chess、Costume 和 RyouToppa 业务链。
- 使用正常 fast-forward 和明确 refspec，不使用强制推送。

### 验证

- 19 个变更 Python 文件通过 `py_compile`。
- JSON、配置默认值、跨午夜与同起止时间窗检查通过。
- 43 项回归测试全部通过。
- `git diff --check` 通过。
- 账号轮换、MultiAccountEvo、GeneralInvite、NemuIPC、scrcpy 和 Image/OCR RPC 文件均确认保持目标分支原 blob。
- 远程跟踪引用和 `git ls-remote` 均确认目标提交为 `267a6fe6d0fbefac2da4ded3a4d1a0f066ec1fff`。

### Git

- 目标远程分支：`origin/zoombies-account-rotation-dailytask/synevo`
- 原远程提交：`921e9649b233bb65745b595f692384633a3cc9ae`
- 新提交：`267a6fe6d0fbefac2da4ded3a4d1a0f066ec1fff`
- commit message：`feat: 合入通用偏移点击与安全加固`
- 推送结果：`921e9649..267a6fe6`，正常 fast-forward。
- 强制推送：未使用。

### 后续

- 目标分支后续若继续同步通用能力，仍应从目标远程最新提交建立隔离分支并选择性转移。
- 不要用完整 `master` 覆盖该分支，也不要回退其账号轮换专属实现。

## 2026-08-30 - 疲劳系统状态同步与 P0-A / P0-B 收口

### 目标

将工作区中已领先交接文档的疲劳 / 发呆 / 休息系统实际状态同步进交接文档，并对 P0-A（运行时负荷系数归一化）和 P0-B（idle/rest 终止语义）补充确定性测试。

### 背景

接手时发现 `module/fatigue.py`、`tasks/base_task.py`、`tasks/GlobalGame/config.py`、`module/server/script_process.py`、`module/server/script_router.py`、`script.py` 中的疲劳相关实现已比交接文档新，且已包含 P0-A / P0-B 的生产修复：

- `_normalize_task_recovery()` 在 `set_load_factor()` / `update_config()` / `begin_task()` 同名分支中调用。
- `try_break()` 已有 `completed` 标志与 `should_resume` 回调；`finally` 中只有正常完成且允许恢复时才 `_resume_after_break()`，否则 `end_global_activity()`。
- `BaseTask.try_fatigue_break` 已传入基于 deadline 的 `should_resume`。
- `FatigueManager.load_factor_preview()` 及 `fatigue_load_factor_preview` 下发字段已存在（P0-D 后端）。

### 修改

- `tests/test_fatigue.py`：新增 10 个测试方法与 1 个断言辅助方法，不改动已有用例。
  - P0-A：`test_lowering_load_factor_after_real_rest_keeps_recovery_invariant`、`test_lowering_load_factor_removes_recovery_dead_zone`、`test_update_config_lower_load_factor_keeps_recovery_invariant`、`test_raising_load_factor_does_not_grow_recovery`。
  - P0-B：`test_break_normal_end_resumes_active_segment`、`test_break_stop_does_not_resume_active_segment`、`test_break_deadline_does_not_resume_active_segment`、`test_break_cancel_does_not_resume_active_segment`、`test_break_terminating_exception_does_not_resume_active_segment`、`test_interrupted_break_applies_no_recovery_or_cooldown`。
- `docs/AI_CONTEXT.md`：更新 §2 Git 状态（工作区非干净，列出疲劳 WIP 文件），新增 §4.9 疲劳系统当前状态，更新 §7 测试数字与覆盖，§8 增加 `_publish_fatigue_state` 2 秒循环 P2 项，§9 增加 P0-D 前端缺口与 P2 项。

### 技术决策

- P0-A / P0-B 生产逻辑经审查已正确，本轮不再修改这两块之外的疲劳生产代码，只补测试。
- P0-B 的 stop / cancel / 异常终止统一表现为睡眠期抛异常（`completed` 保持 `False`），deadline 表现为 `should_resume()` 返回 `False`，两类都走 `end_global_activity()` 收口，终态 `scheduler_idle`，终止后不再增长 active elapsed。
- 不修改疲劳公式和概率参数。
- `_publish_fatigue_state` 独立 2 秒轮询只记录为 P2 架构审查项，本轮不动。

### P0-D 只读审查结论

- 后端链路完整：`load_factor_preview()` 输出 `L=0.80~1.30` 步进 `0.05` 共 11 档；概率复用生产 `idle_score` / `idle_probability` / `logistic_probability` 与 `config.idle.probability`，无独立公式；参考场景为 active 60 分钟、`n=18`、`GlobalFatigue=10`、`TaskRecovery=0`，与约定一致。
- `ui_snapshot()` 与 `ScriptProcess._default_fatigue_state()` 均带 `fatigue_load_factor_preview`；WS 连接、运行中每 2 秒、`stop`、`refresh_fatigue_state` 各路径都会下发。
- `set_fatigue_load_factor` 不重算 preview，因 preview 与当前 `L` 无关，无害。
- 多实例后端隔离：`ScriptProcess` 与 `FatigueManager` 均按 `config_name` 独立。
- 无法核实项（OASX Flutter 前端为独立仓库，不在本工作区）：前端是否解析 `fatigue_load_factor_preview`、是否存在硬编码概率、Slider 当前档高亮、`fatigue_header_panel` 的“!”Tooltip 文案、前端多实例隔离、Flutter 3.35 Tooltip 兼容与 widget test。

### 验证

- `tests/test_fatigue.py` 单模块：`56/56 OK`。
- 完整 Python 回归 `toolkit/python.exe -m unittest discover -s tests`：`99/99 OK`。
- `py_compile` 覆盖 `module/fatigue.py`、`tests/test_fatigue.py`、`script.py`、`tasks/base_task.py`、`tasks/GlobalGame/config.py`、`module/server/script_process.py`、`module/server/script_router.py`、`tasks/RyouToppa/script_task.py`、`tasks/RyouToppa/config.py`：通过。
- `git diff --check` 通过；两个未跟踪疲劳文件经行尾空格检查无问题。

### Git

- 未 commit、未 push。
- 分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

### 未解决问题

- P0-D 前端半段需在 OASX Flutter 仓库中审查与修复。
- `_publish_fatigue_state` 2 秒轮询 P2 架构审查。
- GlobalFatigue 进程重启清零（既定设计，不新增持久化）。

## 2026-08-30 - idle 触发改为事件率 / hazard 模型

### 目标

解决“每个安全节点固定概率”导致高频副本（120~180 次/小时安全节点）比慢任务显著更容易触发 idle 的问题。只改 idle 触发概率如何从 IdleScore 换算，不动 TaskFatigue / GlobalFatigue / 权重 / Recovery / cooldown / activity_state / rest。

### 修改

- `module/fatigue.py`
  - 新增 `idle_intensity(score)`：`1 / (1 + exp(-k·(score - F0)))`，范围 (0,1)，不表示单节点概率。
  - 新增 `idle_rate_per_hour(snapshot)` = `idle_intensity(idle_score) · idle.rate_max`。
  - 新增静态 `_node_probability_from_rate(rate_per_hour, delta_seconds)` = `1 - exp(-rate · Δt / 3600)`。
  - 删除 `idle_probability(snapshot)` 方法。
  - `try_break`：在 `on_check` 后记录 `node_active_elapsed = task_active_elapsed()`；idle 分支改为按 `Δt = node_active_elapsed - _last_idle_check_task_elapsed` 计算 `P_node`，无论是否触发都推进 `_last_idle_check_task_elapsed`；rest 触发分支在返回前也把 `_last_idle_check_task_elapsed` 推进到 `node_active_elapsed`。
  - `FatigueBreakResult` 增加 `idle_rate: float = 0.0`；idle 结果 `probability` 改为实际 `P_node`，并带 `idle_rate`。
  - `__init__` / `begin_task`（切换与 restart 分支）初始化 / 重置 `_last_idle_check_task_elapsed = 0.0`；同名任务页面切换分支不重置。
  - `load_factor_preview`：参考 `repetitions` 18 → 150，新增 `reference_node_seconds = 25.0`；每档字段改为 `factor` / `task_fatigue` / `idle_score` / `idle_intensity` / `idle_rate_per_hour` / `idle_probability_at_25s`，移除 `idle_probability`。
- `tasks/GlobalGame/config.py`
  - `IdleFatigueConfig`：移除 `probability: FatigueProbability` 子模型，平铺新增 `steepness`（默认 0.11，原 `probability.steepness`）、`midpoint`（默认 52.0，原 `probability.midpoint`）、`rate_max`（默认 4.0，次/小时）。
  - `FatigueProbability` 类保留，仍由 `RestProbability` / `rest.probability` 使用。
- `tests/test_fatigue.py`
  - 更新 5 个既有用例：两次连续 idle 之间补真实 active 间隔；`activity_state` 用例补 30 分钟 active；`test_low_fatigue_has_low_trigger_probability` / `test_high_fatigue_never_forces_trigger` 改用 `idle_intensity` / `idle_rate_per_hour`；`test_load_factor_preview_uses_current_idle_formula` 与 `_clamp_preview_task` 改用新字段与 `n=150`。
  - 新增 18 个确定性用例，覆盖：`P_node` 随节点密度下降、相同 `IdleRate` 下 144×25s 与 1×3600s 累计不触发概率一致、`idle_rate ≤ rate_max`、低 / 高疲劳边界、首节点 `Δt`、`Δt` 排除 idle/rest、未触发也推进基准、任务切换 / restart 重置基准、页面切换不重置、rest 触发推进基准且不含 rest 时间、idle 后 `idle_rate` 下降、`L` 经 `TaskFatigue` 影响 `idle_rate`、`FatigueBreakResult.idle_rate` / `probability`、preview 参考场景与生产公式一致。

### 技术决策

- 旧 `idle.probability.maximum`（Pmax=0.18）只用于 idle 单节点概率，本轮从 idle 配置删除；不复用 `idle_probability` 字段名表达新含义，preview 直接换成 `idle_rate_per_hour` + `idle_probability_at_25s`。
- `k` / `F0` 数值不变，仅从 `idle.probability.*` 平铺到 `idle.*`（结构调整触发的重命名）。
- `Δt` 直接用 `task_active_elapsed()` 差值，天然继承现有 active time 语义，不新增后台计时线程。
- 首节点 `Δt` = 任务开始到首节点的真实 active 时间（`begin_task` 时基准置 0），不使用固定默认秒数。
- rate_max=4.0 是高疲劳理论上限，不在代码中硬编码“必须 2~3 次/小时”。
- `L` 不直接乘 `idle_rate` 或 `P_node`，仅经 `TaskFatigue` 间接影响，Slider 语义不变。
- 旧 JSON（`idle.probability.*`）被 pydantic `extra='ignore'` 忽略，新字段取默认值（与旧 k/F0 一致），无破坏性迁移。

### 验证

- `tests/test_fatigue.py` 单模块：`74/74 OK`。
- 完整 Python 回归 `toolkit/python.exe -m unittest discover -s tests`：`117/117 OK`。
- `compileall` 覆盖 `module/fatigue.py`、`tasks/GlobalGame/config.py`、`tasks/base_task.py`、`script.py`、`module/server/script_process.py`、`module/server/script_router.py`、`tasks/RyouToppa/script_task.py`、`tests/test_fatigue.py`：通过。
- `git diff --check` 通过；无行尾空格。
- 现有 P0-A / P0-B 用例全部保持通过。

### 参考场景 preview（active=60min, n=150, GlobalFatigue=10, Recovery=0）

| L | TaskFatigue | IdleScore | idle_intensity | idle_rate/小时 | P@25s | P@180s |
|---|---|---|---|---|---|---|
| 0.80 | 48.11 | 40.49 | 0.2199 | 0.880 | 0.61% | 4.30% |
| 0.90 | 54.13 | 45.30 | 0.3237 | 1.295 | 0.90% | 6.27% |
| 1.00 | 60.14 | 50.11 | 0.4483 | 1.793 | 1.24% | 8.58% |
| 1.10 | 66.16 | 54.92 | 0.5797 | 2.319 | 1.60% | 10.95% |
| 1.20 | 72.17 | 59.74 | 0.7008 | 2.803 | 1.93% | 13.08% |
| 1.30 | 78.18 | 64.55 | 0.7990 | 3.196 | 2.20% | 14.77% |

（完整 11 档见 `load_factor_preview()`。理论上限 4.0 次/小时对应 `idle_intensity → 1`，参考场景内未达到。）

### Git

- 未 commit、未 push。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

### 未解决问题

- OASX Flutter 前端需从 `idle_probability` 迁移到 `idle_rate_per_hour`（+ 可选 `idle_probability_at_25s`），并把 Tooltip 文案从“单节点概率”改为“参考发呆频率 X 次/小时”。
- 真实模拟器长时间运行采样仍未做，用于校准 `rate_max` 与 `k`/`F0` 是否让常见高频副本落在约 2~3 次/小时。

## 2026-08-30 - idle 事件率加基础值 + idle 时长重调

### 目标

在上一轮事件率模型基础上继续微调，使高频重复任务第一小时 idle 大致落在 2~3 次、时长多数 20~60 秒。不动架构与 P0-A / P0-B。

### 修改

- `module/fatigue.py`
  - `idle_rate_per_hour`：由 `idle_intensity · rate_max` 改为 `rate_base + (rate_max - rate_base) · idle_intensity`。
  - `_duration_range`：众数由 `minimum_seconds + (mode_maximum_seconds - minimum_seconds)·ratio` 改为 `mode_minimum_seconds + (mode_maximum_seconds - mode_minimum_seconds)·ratio`。
  - `load_factor_preview`：参考 `repetitions` 150 → 170；`rate` 改为调用 `self.idle_rate_per_hour(snapshot)`（去掉内联的旧 `intensity·rate_max`）。
- `tasks/GlobalGame/config.py`
  - `IdleFatigueConfig`：新增 `rate_base=1.5`；`minimum_seconds` 10 → 15；新增 `mode_minimum_seconds=25`；`mode_maximum_seconds` 90 → 70；`maximum_seconds` 180 → 150；新增 `validate_rate`（`rate_max >= rate_base`）；`validate_duration` 改为校验 `最短 <= 众数下限 <= 众数上限 <= 最长`。
  - `RestFatigueConfig`：新增 `mode_minimum_seconds=120`（等于 `minimum_seconds`，rest 时长行为不变）；`validate_duration` 同步为四段不等式。
- `tests/test_fatigue.py`
  - 更新既有用例：`_clamp_preview_task` 与 preview 相关用例改 n=170；低疲劳事件率断言从“接近 0”改为“接近 `rate_base`”；`test_idle_rate_never_exceeds_rate_max` 改名并加 `>= rate_base` 下界；`test_load_factor_preview_uses_current_idle_formula` 改用 `idle_rate_per_hour`；`test_preview_reference_scenario_uses_150_repetitions` → `_170_repetitions`。
  - 新增用例：`idle_rate = rate_base + span·intensity` 精确核对、`GlobalFatigue` 抬高 `idle_rate`、idle 时长 min=15 且众数随疲劳上移、idle 时长各疲劳档均值 ≤90 秒且 TaskFatigue≈50 时众数 20~60、第一小时 hazard 数值积分期望落在 (1.5, 3.5)。

### 技术决策

- `rate_base=1.5`、`rate_max=4.0` 保持不变：数值积分（L=1.30、连续 active 60min、n→170、Global 按公式）得第一小时理论期望约 **2.12 次**（未计 recovery，计入后略低），符合目标带，未擅自调整。
- idle 上限从 180 降到 **150**：保持 180 的同时无法同时满足“高疲劳均值不轻易超过 60~90 秒”和“1~3 分钟不成为主分布”。`maximum_seconds` 仍是可配置字段，需要更长尾可自行调大。
- `mode_minimum_seconds` 加到 idle 与 rest 两个时长配置以复用 `_duration_range`；rest 的默认值取 `minimum_seconds`，rest 时长完全不变。
- `L` 不直接乘 `idle_rate` / `P_node`；`GlobalFatigue` 仍只经 `IdleScore` 的 0.2 权重影响，未加第二个系数。
- 旧 JSON 里 `idle.probability.*` 与旧的 `mode_maximum_seconds=90` / `maximum_seconds=180` 等：pydantic `extra='ignore'`，缺字段取新默认，无破坏性迁移。

### 第一小时轨迹（L=1.30, 170 轮/时, 连续 active, 未计 recovery）

| 分钟 | TaskFatigue | GlobalFatigue | IdleScore | IdleIntensity | IdleRate/时 |
|---|---|---|---|---|---|
| 10 | 24.11 | 0.31 | 19.35 | 0.027 | 1.57 |
| 20 | 33.60 | 1.23 | 27.12 | 0.061 | 1.65 |
| 30 | 43.37 | 2.74 | 35.24 | 0.137 | 1.84 |
| 40 | 54.67 | 4.82 | 44.70 | 0.309 | 2.27 |
| 50 | 66.64 | 7.43 | 54.80 | 0.576 | 2.94 |
| 60 | 78.19 | 10.52 | 64.65 | 0.801 | 3.50 |

第一小时理论 idle 期望 ≈ **2.12 次**。

### idle 时长三角分布（min, mode, max / 均值）

| TaskFatigue | min | mode | max | 均值 |
|---|---|---|---|---|
| 0 | 15 | 25.0 | 31.2 | 23.7 |
| 20 | 15 | 34.0 | 55.0 | 34.7 |
| 40 | 15 | 43.0 | 78.7 | 45.6 |
| 60 | 15 | 52.0 | 102.5 | 56.5 |
| 80 | 15 | 61.0 | 126.2 | 67.4 |
| 100 | 15 | 70.0 | 150.0 | 78.3 |

多数落在 20~60 秒；60~120 秒为少数；>120 秒仅在接近满疲劳时偶发。

### preview（active=60min, n=170, Global=10, Recovery=0）

| L | TaskFatigue | IdleScore | IdleIntensity | IdleRate/时 | P@25s |
|---|---|---|---|---|---|
| 0.80 | 48.11 | 40.49 | 0.2199 | 2.050 | 1.41% |
| 0.90 | 54.13 | 45.30 | 0.3237 | 2.309 | 1.59% |
| 1.00 | 60.14 | 50.11 | 0.4483 | 2.621 | 1.80% |
| 1.10 | 66.16 | 54.93 | 0.5798 | 2.949 | 2.03% |
| 1.20 | 72.17 | 59.74 | 0.7008 | 3.252 | 2.23% |
| 1.30 | 78.19 | 64.55 | 0.7990 | 3.498 | 2.40% |

（完整 11 档见 `load_factor_preview()`。）

### 验证

- `tests/test_fatigue.py`：`79/79 OK`。
- 完整 Python 回归：`122/122 OK`。
- `compileall`（fatigue 相关 8 文件）：通过。
- `git diff --check`：通过；无行尾空格。
- P0-A / P0-B 用例全部保持通过。

### Git

- 未 commit、未 push。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

### 未解决问题

- OASX Flutter 前端字段迁移同上一条目。
- idle 上限降到 150 待真机采样确认是否需要更长尾。
- 真实模拟器长时间运行采样仍未做，用于确认第一小时 2~3 次目标与 recovery 反馈的实际表现。

## 2026-08-30 - scheduler_idle 调度空档 GlobalFatigue 自然恢复

### 目标

`OAS 进程运行 ≠ 一直 active`：任务之间可能空闲 2~5 小时，进程仍在跑但没有任何游戏操作。此前 scheduler_idle 只冻结 GlobalFatigue，空闲 3 小时也完全不恢复。本轮让 scheduler_idle 超过等待期后按指数曲线自然恢复 GlobalFatigue。只改这一点，不动 idle / rest / TaskFatigue / P_node / 时长 / 权重 / recovery 既有保护。

### 新模型

- 进入 scheduler_idle（`end_global_activity()` 把 `_global_activity_depth` 降到 0）时记录入口快照：`_scheduler_idle_started_at`（monotonic 墙钟）、`_scheduler_idle_global_start`（G0 = 当时 `global_fatigue()`）、`_scheduler_idle_recovery_applied = 0`。
- 前 `recovery_delay_minutes`（默认 5.0）分钟只冻结，不恢复。
- 超过后：`ratio = 1 - exp(-(idle_minutes - 5) / recovery_tau_minutes)`（默认 tau=34.0），`idle_minutes` 为真实墙钟分钟数（不是 `global_active_elapsed`）。
- `target = G0 · ratio`，`delta = target - _scheduler_idle_recovery_applied`，只把 `delta` 追加进现有 `_global_recovery`，并 `min` 到当前 `RawGlobal`，`_scheduler_idle_recovery_applied += 实际应用量`。
- `GlobalFatigue = clamp(RawGlobal - _global_recovery, 0, 100)`；因 scheduler_idle 期间 `RawGlobal` 冻结，`_global_recovery` 渐近到 `RawGlobal` 但不超过，`GlobalFatigue` 渐近到 0 且非负，不形成未来恢复额度。

### 实现方式

- baseline：入口三元组快照，之后始终基于 G0 + 真实经过时间计算“截至当前应恢复多少”，只追加增量。
- monotonic：复用 `FatigueManager` 已有的 `self._clock`（生产 `time.monotonic`，测试注入 `FakeClock`），未新增时间源或线程。
- 幂等：`global_fatigue()` 每次读取都调 `_apply_scheduler_idle_recovery()`；同一时间点 `target` 不变，`delta = target - 已应用 = 0`，`global_fatigue()` / `snapshot()` / `ui_snapshot()` 连读多次结果一致。
- 无未来额度：追加时 `min(delta, RawGlobal - _global_recovery)`；测试断言 10 小时后 `_global_recovery ≤ RawGlobal` 且重新 active 后 `GlobalFatigue` 立即从 ~0 重新增长。
- 退出：`begin_global_activity()`（depth 0→1）先 `_apply_scheduler_idle_recovery()` 落定，再清空快照结束 session；下一次进入建立全新 baseline。不连续的多段 scheduler_idle 各自重新计 5 分钟等待期，不拼接。
- 惰性：只在 `global_fatigue()` 读取点和 `begin/end_global_activity` 状态转换点计算，未新增 daemon / timer / 轮询。

### 状态转换与 fatigue

- active：TaskFatigue / GlobalFatigue 增长。
- idle：明显恢复 TaskFatigue，轻微恢复 GlobalFatigue（既有 `_apply_idle_recovery`，未改）。
- rest：明显恢复 Task + Global（既有 `_apply_rest_recovery`，未改）。
- scheduler_idle：不增 `task_active_elapsed` / `global_active_elapsed`、不增疲劳；≤5min 只冻结，>5min GlobalFatigue 指数自然恢复；不处理 TaskFatigue（任务间 TaskFatigue 生命周期已结束，新任务走现有 `begin_task`）。

### 关闭实例

本轮不加 fatigue 持久化。人为关闭 oas1 进程即 FatigueManager 生命周期结束；重启按现有语义重新初始化 `GlobalFatigue = TaskFatigue = 0`。不写库、不写 JSON、不按关闭时长补算、不跨进程恢复。

### 恢复曲线（ratio = 1 - exp(-(t-5)/34)）

| scheduler_idle | 恢复比例 | 剩余 GlobalFatigue（G0=100） |
|---|---|---|
| 4 min | 0% | 100 |
| 5 min | 0% | 100 |
| 15 min | 25.5% | 74.5 |
| 30 min | 52.1% | 47.9 |
| 60 min | 80.2% | 19.8 |
| 120 min | 96.6% | 3.4 |
| 240 min | 99.9% | 0.1 |
| 480 min | ≈100% | ≈0 |

### 修改文件

- `module/fatigue.py`：`__init__` 加三个 scheduler_idle 快照字段；`begin_global_activity` / `end_global_activity` 挂 `_end/_begin_scheduler_idle_session`；新增 `_begin_scheduler_idle_session` / `_end_scheduler_idle_session` / `_apply_scheduler_idle_recovery`；`global_fatigue()` 读取时惰性结算。
- `tasks/GlobalGame/config.py`：新增 `SchedulerIdleConfig`（`recovery_delay_minutes=5.0 ge=0`、`recovery_tau_minutes=34.0 gt=0`），`FatigueConfig` 加 `scheduler_idle` 字段。
- `tests/test_fatigue.py`：`test_scheduler_idle_time_does_not_add_global_fatigue` 断言从 `== before` 改为 `<= before` + 恢复后重新增长；新增 13 个 scheduler_idle 用例。
- `docs/AI_CONTEXT.md` / `docs/DEVELOP_LOG.md`：同步。

### 验证

- `tests/test_fatigue.py`：`92/92 OK`（旧 79 → 92）。
- 完整 Python 回归：`135/135 OK`（旧 122 → 135）。
- `compileall`（fatigue 相关 8 文件）：通过。
- `git diff --check`：通过；无行尾空格。
- 旧模型回归：idle 事件率 / idle 时长 / P0-A / P0-B / RyouToppa 安全节点相关用例全部保持通过；未改 `IdleScore` / `RestScore` 权重、`idle.rate_base` / `idle.rate_max`、`IdleIntensity`、`P_node`、idle / rest 时长、`L` 语义、cooldown、`_publish_fatigue_state`。

### Git

- 未 commit、未 push。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

### 未解决问题

- OASX Flutter 前端字段迁移同前。
- scheduler_idle 恢复到 0 后再 active，因 `global_active_elapsed` 不重置，`RawGlobal` 从冻结值续增、`_global_recovery` 停在冻结 `RawGlobal`，故 GlobalFatigue 从 0 重新增长的速率是「续增段的边际增速」，比全新进程慢——这是不改 active elapsed 定义的自然结果，非缺陷，待真机采样确认是否需要额外处理。
- 真实模拟器长时间运行采样仍未做。

## 2026-08-30 - idle 时长硬上限 150 → 120 秒

### 修改

- `tasks/GlobalGame/config.py`：`IdleFatigueConfig.maximum_seconds` 150.0 → 120.0。`minimum_seconds=15`、`mode_minimum_seconds=25`、`mode_maximum_seconds=70` 不变；三角分布与随 TaskFatigue 动态调 `high` 的逻辑不变，未改成均匀分布。
- `tests/test_fatigue.py`：新增 `test_idle_duration_hard_cap_is_120`（`maximum_seconds == 120`、各疲劳档 `high ≤ 120`、满疲劳 `high == 120`、200 次实际采样均 ≤ 120）。既有 `test_idle_duration_min_is_15_and_mode_rises_with_fatigue` / `test_idle_duration_mean_stays_moderate` 用 `self.config.idle.maximum_seconds` 动态断言，自动适配。
- `docs/AI_CONTEXT.md`：§4.9 idle 时长段与测试覆盖行同步。

### 新时长分布（min, mode, max / 均值）

| TaskFatigue | min | mode | max | 均值 |
|---|---|---|---|---|
| 0 | 15 | 25.0 | 27.6 | 22.5 |
| 20 | 15 | 34.0 | 46.1 | 31.7 |
| 40 | 15 | 43.0 | 64.6 | 40.9 |
| 60 | 15 | 52.0 | 83.0 | 50.0 |
| 80 | 15 | 61.0 | 101.5 | 59.2 |
| 100 | 15 | 70.0 | 120.0 | 68.3 |

多数 idle 仍集中在 20~60 秒；高疲劳 `P(45<X<90) ≈ 67%`；偶尔接近 120 秒；`P(X>120) = 0`（硬截断）。

### 验证

- `tests/test_fatigue.py`：`93/93 OK`（旧 92 → 93）。
- 完整 Python 回归：`136/136 OK`（旧 135 → 136）。
- `compileall`、`git diff --check`：通过。
- 未改 idle rate 模型、TaskFatigue / GlobalFatigue、recovery、rest、scheduler_idle 自然恢复、前端、RyouToppa、GeneralBattle。

### Git

- 未 commit、未 push。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-08-30 - 输入层加固归因复核与特征面记录（只读审计）

### 目标

复核“防风控加固”这一归因是否与实际效果相符，并把可被外部确认的特征面按权重记录下来，避免后续把工程投入错配。本轮未修改任何生产代码。

### 归因修正（四条，已写入 AI_CONTEXT §8.1）

- `np.random` → `SystemRandom` **不改变任何可观测分布**：两者在同一 ROI 上是同一均匀分布，外部看到的统计量一致。真实价值是消除 `random.seed()` 全局污染、提升确定性与可测试性，属代码质量改进。
- minitouch pressure 随机化在当前 MuMu 环境是**空操作**：握手 `^ 10 540 960 0` → `max_pressure <= 0` 回退 1 → `random_int(max(1, 0), 1)` 恒为 1。
- 点击坐标仍是**全 ROI 均匀**（`module/atom/click.py`、`image.py` 的 `random_point_in_roi`），只有 `RuleSwipe` 做了中心偏置；点击是采样量最大的事件类型。
- `insert_swipe` drag 尾部两次固定 `wait(140)`，与“每个 MOVE 独立采样 6~15ms”原则冲突。

### 随机源统一的实际边界（AI_CONTEXT §8.2）

未迁移：`module/atom/swipe.py` Bezier 轨迹、`minitouch.insert_swipe` 控制点（`np.random`）、`tasks/RyouToppa/script_task.py` 本地随机工具与滑动坐标、`module/base/protect.py` 同名 `random_delay`。

### 特征面清单（AI_CONTEXT §8.3）

按确认难度分五层记录：设备驻留物 → 模拟器本体 → 轮询与反应时序 → 输入层 → 行为聚合。输入层（本轮改造所在）权重最低；设备驻留物枚举即可确认，权重最高且不受输入随机化影响。

### 一致性修复候选的范围核实

- `protect.random_delay` 与公共 `random_delay` **同名不同语义**（前者 sleep 返回 None，后者返回 float 不 sleep）。外部零 import。范围：1 文件约 3 行。
- RyouToppa 本地 `random_delay` 与公共版语义相同，属真正重复；4 个调用点均显式传参。范围：1 文件约 8 行删 + 1 行 import。
- **修正上一轮结论**：`module/device/method/minitouch.py` 的 `drag_minitouch` 固定 140ms 位于死路径——`Device.drag()` 在 `tasks/` 与 `module/` 内零业务调用方。真正生效的是 `tasks/Chess/runtime/press_and_drag.py` 的 `_press_and_drag_minitouch`，它同样有两次 `wait(140)` 且用普通 `random.randint`。改 140ms 影响 Chess 真机拖拽落点，必须真机验证。

### 验证

- 完整 Python 回归：`136/136 OK`。
- `git diff --check` 通过；文档无行尾空格。

### Git

- 未 commit、未 push。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-08-30 - 随机源一致性修复（protect / RyouToppa / Chess 拖拽）

### 目标

修复 §8.1 / §8.2 记录的三处随机源问题：同名反语义、重复实现、混用普通 random。全部为等价替换，不改变任何分布或行为。

### 修改

- `module/base/protect.py`
  - `random_delay` → `sleep_random_delay`。原函数与公共 `module/base/utils/random.py` 的 `random_delay` **同名但语义相反**（前者 `sleep()` 返回 `None`，后者返回 `float` 不 sleep），import 错了不会报错、只会静默行为不对。
  - 内部改为 `sleep(round(random_delay(min, max), decimal))`，复用公共实现取值。
  - `random_sleep` 的概率抽样 `random.random()` → `random_delay(0.0, 1.0)`（同分布，与 `module/fatigue.py` 用法一致）。
  - `import random` 移除。
- `tasks/RyouToppa/script_task.py`
  - 删除 `_random = secrets.SystemRandom()` 与本地 `random_delay`（语义与公共版相同，属真正重复），改为 `from module.base.utils.random import random_delay`。
  - `import secrets` 移除；`import random` 保留（滑动坐标仍在用）。
  - 4 个调用点（0.342/0.362、0.349/0.355、1.0/3.0、0.2/0.6）均显式传参、不依赖默认值，未改动。
- `tasks/Chess/runtime/press_and_drag.py`
  - `random.randint(6, 15)` → `random_int(6, 15)`；`random.uniform(0.001, 0.004)` → `random_delay(0.001, 0.004)`。
  - `import random` 移除。

### 技术决策

- `_press_and_drag_minitouch` 终点两次固定 `wait(140)` **有意保留**，只补中文注释说明它是拖拽落点 settle 等待、属可靠性时序。改它会影响 Chess 真机拖拽落点，静态测试无法验证，未获真机测试授权不变更。
- 修正上一轮结论：`module/device/method/minitouch.py` 的 `drag_minitouch` 有同样的固定 140ms，但 `Device.drag()` 在 `tasks/` 与 `module/` 内**零业务调用方**，属死路径，本轮未动。
- `protect` 命名空间中 `random_delay` 现指向公共实现（返回 float 不 sleep）。已确认外部零 import，无静默行为变化风险。

### 验证

- `compileall` 覆盖 `module`、`tasks`、`tests`、`script.py`：通过。
- 残留引用扫描：RyouToppa 无 `secrets`、press_and_drag 无 `random.`、`protect.random_delay` 无外部 import。
- 完整 Python 回归：`136/136 OK`（与修改前一致，无用例受影响）。
- `git diff --check` 通过；无行尾空格。
- 未做真机 / 游戏内测试。

### Git

- 未 commit、未 push。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-08-30 - KekkaiUtilize 结界蹭卡选卡缺陷与可靠性修复

### 目标

审计结界蹭卡链路后修复一处功能缺陷（选中的卡不是最优卡）和四处可靠性 / 一致性问题。选卡方案由用户确认走「配置收益阈值，达标即寄养」。

### 审计发现

按严重度：

- **P0 选卡结果与记录的最优卡不一致**。点开一张卡同时就是选中它，而 `ImageGrid.find_everyone` 按 y 坐标升序返回（位置序），遍历结束时选中的是最后点开的那张。`_select_optimal_resource_card` 只要 `jade_max_num > 0` 就返回 True，于是带着次优卡进结界。同类型有 `confirmed_highest_stars` 跳过低星卡，但**跨类型完全不设防**。
- **P1 OCR 剩余时间造成热循环**。`ocr_duration` 解析失败返回 `timedelta(0)`（不是 None、不抛异常），原 `isinstance` 检查因此是死分支；`next_run = now + 0` 被设成当前时刻 → 立即重跑 → 再次失败 → 紧密循环。`min_run_interval` 默认 0 不兜底。
- **P1 `switch_friend_list` 无总超时**。目标分组图标识别不到就每秒点击一次无限循环，仅靠 `stuck_record` / `click_record` 副作用兜底。该方法在链路上调用极频繁（`_reset_utilize_friend_list` 每次调 2~3 次），回选引入后调用次数进一步翻倍。
- **P2** `receive_guild_assets` 忽略返回值固定往返；`perform_swipe_action` 混用普通 `random`。

### 修改

- `tasks/KekkaiUtilize/config.py`：`UtilizeConfig` 新增 `taiko_reward_threshold=76` / `fish_reward_threshold=151`（`ge=1`），默认等于六星满值，默认行为零变化。
- `tasks/KekkaiUtilize/script_task.py`
  - 移除 `STRATEGY_MAX_REWARDS` 与 `_is_strategy_maximum_reward`，改为 `_reward_threshold()` + `_reaches_reward_threshold()` 读配置。
  - 新增 `_card_rank()`：跨类型优劣按 `order_cards` 偏好顺序，不比较原始数值（体力与勾玉不可比）。
  - 扫描循环记录 `utilize_best_*` / `utilize_last_*`；`_select_optimal_resource_card(friend)` 增加 friend 参数并重写兜底分支。
  - 新增 `_reselect_best_card(friend)`：回顶重扫、按收益值匹配、档位上限剪枝、OCR 校验、120s + 21 屏上限。
  - 新增 `UTILIZE_RES_TIME_FALLBACK = 5min` / `UTILIZE_RES_TIME_MAX = 12h`，剩余时间异常时按兜底间隔重试。
  - `switch_friend_list` 加 `SWITCH_FRIEND_LIST_TIMEOUT = 20` 秒并抛 `GamePageUnknownError`；签名 `-> bool` 改 `-> None`；异常在 `run_utilize`（→ `_record_utilize_failure`）与 `_reselect_best_card`（→ `return False`）两处接住，不升级为重启游戏。
  - `receive_guild_assets` 加 `if not ret: break`。
  - `perform_swipe_action` 改用公共 `random_int`，魔法数字提取为 `SWIPE_START_X_RANGE` / `SWIPE_START_Y_RANGE` / `SWIPE_DISTANCE`；`run` 的怠惰骰子改用 `random_delay(0.0, 1.0)`、经验壶重试改用 `random_int`。该文件已无普通 `random`。
- `tests/test_kekkai_utilize_threshold.py`：新增，25 个用例。
- `module/config/i18n/zh-CN.json`（gitignore 内的运行时文件）：新增 4 个阈值文案 key。

### 技术决策

- 阈值默认取六星满值而非实用值（67 / 134），保证现有用户升级后行为不变，符合项目「不随意改变已确认的默认行为」规则。
- 兜底选 5 分钟：真的剩余 0 时 5 分钟后重跑无害，OCR 持续失败时也不会打爆。同时加 12 小时上界，防止 OCR 误读把任务推迟数天。
- **`swipe_adb` 有意保留不改**。查 `26715a72` 确认引入 `perform_swipe_action` 时就选定 adb swipe，公共 `self.swipe` 从创建起即为注释状态，属有意选择而非回退遗留。好友列表对滚动距离敏感，改回公共滑动会改变实际位移，必须先真机验证。已在 docstring 写明该结论。
- `switch_friend_list` 超时抛 `GamePageUnknownError` 而非返回 bool：与模块既有约定一致；但在调用点接住，避免为一次分组切换失败重启游戏。
- 回选按**收益值**而非位置匹配，因交接文档 §7.4 明确「列表首次进入可能先显示最近寄养好友、顺序混乱，不能依赖稳定排序」。

### 验证

- `tests/test_kekkai_utilize_threshold.py`：`25/25 OK`。
- 完整 Python 回归：`161/161 OK`（136 → 151 → 161）。
- `compileall` 覆盖 `module`、`tasks`、`tests`、`script.py`：通过。
- 残留扫描：`STRATEGY_MAX_REWARDS` / `_is_strategy_maximum_reward` / 旧死分支 `'Ocr remaining time error'` / 该文件内普通 `random` 均已清除。
- `git diff --check` 通过；无行尾空格；i18n JSON 解析与编码核验通过。
- 未做真机 / 游戏内测试。

### Git

- 未 commit、未 push。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

### 未解决问题

- 回选路径、`switch_friend_list` 超时分支、剩余时间兜底分支均无真机验证。默认阈值下回选会被经常走到（满值卡少见），首次实跑应关注日志 `回选最优结界卡` 段；若不稳可把阈值调低到 67 / 134，多数情况会在第一趟命中阈值而走不到回选。
- `last_best_index = 99` 死属性、`check_utilize_add` 的 True/False 语义不一致，均不影响正确性，本轮按用户要求未动。

## 2026-09-01 - 行为逻辑机械性静态审查（只读）

### 目标

按用户要求对全工作区做一次「行为逻辑机械性特征审查」：找出可能导致自动化行为长期呈现高度固定、重复、可预测的实现，并评估其稳定性与容错风险。本轮不修改代码、不 commit、不启动任何设备 / 模拟器 / 游戏 / OCR / 图像服务，不涉及任何检测规避方案设计。

### 产出

- `docs/机械性审查报告.md`：12 章完整报告。按 A（源码直接确认）/ B（沿调用链确认）/ C（结构上可能形成稳定模式）/ D（无法确认）四级标注证据强度，每条发现带文件、行号、关键代码、调用链、影响范围与稳定性风险。
- `docs/机械性修改清单.md`：按 P0 / P1 / P2 / P3 分级的 14 条修改建议（M1\~M14），含「明确不建议修改」清单与执行顺序建议。

### 主要结论

- 固定行为主要来自公共底层而非任务层。影响面排序：`screenshot._screenshot_interval`（固定 `Timer(0.1)`）> minitouch 输入层（`DEFAULT_DELAY = 0.05` 每次输入固定尾部）> `base/timer.Timer`（全项目 limit 均为常量、无抖动）> `GeneralBattle` 节奏常量 > `base_task` 的 `interval` 门控与 `list_find`。
- 确认三处「看起来已随机化、实际调用链仍固定」：`GeneralBattle` 基类 `PREPARE_CLICK_DELAY_RANGE = (3.0, 3.0)` / `SETTLEMENT_CLICK_INTERVAL_RANGE = (0.8, 0.8)` 因 `random_delay(x, x)` 短路而退化为常量（除 `RealmRaid` 外全部战斗任务受影响）；`RyouToppa` 滑动 `duration` 抖动在 minitouch 路径被 `Control.swipe` 静默丢弃；minitouch pressure 在 MuMu 环境恒为 1。
- 点击坐标**不存在**「长期点击同一单点」问题：`RuleClick` / `RuleImage` / `RuleOcr` 的 `coord()` 均为命中区域内均匀随机，图片与 OCR 还叠加识别后动态定位。
- 主要任务链路是**状态驱动**（每轮重新截图 + 重新判断页面），偏向预设动作序列的是局部环节：`KekkaiActivation.harvest_card`、`RealmRaid` 退四的固定 4 次 `fire_again`、`start_ryou_toppa` 三段式。
- 新确认 `module/atom/swipe.py` 的 `RuleSwipe.trace()` 全仓零调用方，连同 `BezierTrajectory` 导入与两个 `cached_property` 为死代码（原报告记为「需确认」，后经全仓 grep 订正并同步两份文档）。

### 验证

- 未修改任何生产代码，未运行测试（纯静态审查）。
- 所有结论均回到源码逐条核对，未依据变量名或历史文档推断。
- 涉及游戏服务端检测逻辑、长时间运行统计分布、多账号实际时间重合度等需运行数据的事项，一律在报告 §12 标注「无法确认」，未作推测。

### Git

- 未 commit、未 push。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-01 - 修复 `wait_until_appear_then_click` 参数绑定缺陷

### 目标

按用户要求，只修复 `wait_until_appear_then_click` → `wait_until_appear` 的参数绑定缺陷并补测试，其他行为逻辑暂不改动。

### 缺陷

`tasks/base_task.py` 中 `wait_until_appear_then_click` 按位置调用 `self.wait_until_appear(target, wait_time)`，而 `wait_until_appear` 的签名是 `(target, skip_first_screenshot=False, wait_time=None)` —— 第二个位置参数是 `skip_first_screenshot`，第三个才是 `wait_time`。两个后果：

- **超时计时器从不建立**：`wait_time` 在被调方恒为 `None`，`wait_timer = None`，`if wait_timer and wait_timer.reached()` 永远短路。调用方要求的「最多等 N 秒、超时返回 `False`」退化为「一直等到 `stuck_record_check` 抛 `GameStuckError`」（60s / 300s，见 `module/device/device.py:31-32`）。契约从「返回 False」变成「抛异常」。
- **首轮使用旧帧**：任何非零 `wait_time` 使 `skip_first_screenshot` 为真值，第一次循环跳过截图，直接拿调用前遗留的帧做识别。

该方法当前**全仓零调用方**（grep 只命中定义处），属潜伏缺陷而非线上故障，改动不在任何现有任务执行路径上。

### 修改

- `tasks/base_task.py:429-431`：改为关键字传参 `self.wait_until_appear(target, wait_time=wait_time)`，并补中文注释说明位置传参的陷阱。
- `tests/test_base_task_wait_until_appear.py`：新增，5 个用例——`wait_time` 必须关键字传参、默认 `None` 同样走关键字、超时返回 `False` 且不点击（并断言计时器确实被创建并 `start()`）、首轮不得跳过截图（`screenshot_calls == 1`）、`wait_time=None` 时不建计时器且旧行为不变。

### 技术决策

- **修调用侧而非改签名顺序**。已核实 `wait_until_appear` 存在按位置传 `skip_first_screenshot` 的调用方：`tasks/AreaBoss/script_task.py:240,254`、`tasks/Dokan/script_task.py:106,246,587`、`tasks/Component/SwitchAccount/login_account.py:91`、`tasks/SoulsTidy/script_task.py:204`、`tasks/Component/Login/service.py:148`。调整签名顺序会静默破坏这些调用点，正确做法是调用侧显式关键字传参。
- 测试内置 `_LoopNotBounded` 哨兵异常并限制截图次数。缺陷复现时循环不会退出，不设界会让回归测试挂死而非失败。
- 测试用真实 `RuleImage` 实例而非 `SimpleNamespace`，以使 `wait_until_appear` 内的 `isinstance(target, RuleImage)` 分支真实生效。

### 验证

- `tests/test_base_task_wait_until_appear.py` 单模块：`5/5 OK`。
- 完整 Python 回归 `toolkit/python.exe -m unittest discover -s tests`：`166/166 OK`（旧 161 → 166）。
- **双向验证**：临时回退修复后重跑，`3 failures + 1 error`（error 为 `_LoopNotBounded` 哨兵触发，实证超时计时器失效后循环确实不退出）；恢复修复后 `5/5` 通过。确认测试能真正抓住该缺陷。
- `py_compile` 覆盖 `tasks/base_task.py`、`tests/test_base_task_wait_until_appear.py`：通过。
- `git diff --check`：通过（仅两个既有 docs 文件的 LF/CRLF 提示，与本次改动无关）。
- 未做真机 / 游戏内测试。

### 文档规则变更

用户明确要求：**以后每做一步代码修改，都要同时更新 `docs/DEVELOP_LOG.md` 和 `docs/AI_CONTEXT.md`**，不区分改动大小。该要求收紧并覆盖了 `AI_CONTEXT.md` §10 原第 13 条「小型且无架构影响的修复可以只追加开发日志」。随后用户补充确认：纯分析 / 纯设计 / 只读走查通常不写。

> 后续修正（2026-09-01「文档同步规则收口」条目）：交接文档扩为 6 份，且判断标准改为**「本轮是否改变了该文档负责的项目事实」**，而非「是否修改了代码」——纯设计工作若改变了项目事实（架构方案、长期决策、ROADMAP、测试规范、AI 规则）仍要更新对应文档。以最终版为准。

### Git

- 未 commit、未 push。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-01 - BehaviorTrace v1（行为观测日志）

### 目标

实现只读、可关闭、低侵入的运行观测层，记录关键业务动作（click / swipe / long_click）和任务 episode 耗时，为后续 State→Action→Verify、列表 changed/stable、WaitPolicy、RetryPolicy、Recovery、任务状态机重构建立数据基础。**只记录，不干预。**

实现前按当前源码确认 4 点修正并严格执行：enable 由外部一次性注入而非 Trace 自读 Config；v1 `ACTION` 只承诺「动作正常返回后」的完成事件、`result` 恒为 `ok`、不实现 `ACTION error` / `ERROR` 事件；不宣称开启时零时序影响；不实现 `timed()` context manager。

### 修改

- **新增 `module/behavior_trace.py`**（~160 行）：`BehaviorTrace` 类 + `configure_behavior_trace()` / `get_behavior_trace()` / `reset_behavior_traces()`。仅依赖标准库，不 import Config / Device / Timer / BaseTask。按 `config_name` 的进程内单例注册表（仿 `module/fatigue.py`）。写 `log/behavior/<config>_<日期>.jsonl`，`buffering=1` 行缓冲，按日期跨天轮转，`json.dumps(ensure_ascii=False, default=str)`。全程 `try/except BaseException`，任何内部失败置 `_broken` 自禁用 + 尽力 `logger.warning` 一次（惰性 import logger，再套 try/except），`_broken` + `_in_record` 双重防 `record → logger → record` 递归。
- **`tasks/Script/config_optimization.py`**：`Optimization` 新增 `behavior_trace_enable: bool = False`，Chinese `description` 直写，不新增 i18n 键，无迁移。
- **`script.py`**：
  - `import` 加 `configure_behavior_trace, get_behavior_trace`。
  - `Script.__init__`：`fatigue_manager` 初始化后 `configure_behavior_trace(self.config_name, enabled=bool(self.config.script.optimization.behavior_trace_enable))`。进程级参数，只读一次。
  - `Script.run`：`begin_global_activity()` 后取 `trace`、`set_task(command)`、记 `trace_started_at` / `trace_result='fail'`；正常跑完置 `trace_result='ok'`；`except Exception` 分支把 `self._handle_task_exception` 返回值存入 `outcome` 再 `return outcome`，据此置 `trace_result`；`finally` 里 `trace.record('TASK', action='run', target=command, result=trace_result, elapsed_ms=...)` + `set_task('')`。异常传播、`_handle_task_exception` 入参与返回值、`return False` 全部不变；`exit(1)`（SystemExit）路径下 `finally` 仍会写一条 `result='fail'` 的 TASK 事件。
- **`module/device/control.py`**：`import` 加 `get_behavior_trace`。`Control.click` / `long_click` / `swipe` 各在现成 `elapsed` + `logger.info` 之后加一行 `get_behavior_trace(self.config.config_name).record('ACTION', action=..., target=control_name, elapsed_ms=round(elapsed*1000))`。未新增 try/except、未改异常传播、未改 retry、未改 logger。`Control.drag` 未接（死路径）。
- **新增 `tests/test_behavior_trace.py`**（14 用例）。

### 事件模型（v1）

- 事件类型只有 `ACTION`（click/swipe/long_click，仅动作正常返回后）和 `TASK`（Script.run episode）。
- 字段 `ts` / `config` / `task` / `event` / `action` / `target` / `result` 必有，`elapsed_ms` / `extra` 可选。不记 `state_before` / `state_after` / `retry_count`。
- **不实现** `WAIT` / `ERROR` / `RETRY` / `TIMEOUT` / `RECOVERY` / `TRANSITION` / `ACTION_START/END` / `ACTION result=error` / `timed()` / 后台线程 / 队列 / SQLite / State Enum / FSM。

### 已知缺口（刻意保留）

- `KekkaiUtilize.perform_swipe_action` / `KekkaiActivation.check_card_num` 直连 `self.device.swipe_adb(...)` 绕过 `Control.swipe`，v1 不记录这两类滑动。已写在 `Control.swipe` 注释里，后续 Kekkai 状态驱动重构时再评估是否接 `Adb.swipe_adb`。
- 底层动作抛异常时不产生 `ACTION` 事件（`record` 在动作之后，异常已中断）。
- `log/behavior/` 子目录不被 `module/logger.py:cleanup_logs` 自动清理（v1 可接受，JSONL 很小）。

### 性能（本机测量，仅供数量级参考）

- `enable=False`：100000 条 record ≈ 12.8 ms（约 0.13 µs/条），全程不建目录 / 不开文件。
- `enable=True`：10000 条 record ≈ 166 ms（约 17 µs/条），含 `json.dumps` + 行缓冲 write。
- 测试只 `assertLess(dt, 10.0)` 防数量级异常 / 死循环，并 `print` 实际值，不设机器相关的严格毫秒断言。

### 行为影响

- `enable=False`（默认）：`record()` 首行布尔判断即返回，无 IO、无 dict 构造。**无行为变化。**
- `enable=True`：动作执行完成、`logger.info` 之后同步写一行 JSONL。不改控制流、不加 sleep、不改点击/滑动顺序、不改截图/OCR 次数。**不是零开销**，是很小的同步结构化日志开销，在动作关键时序路径之外。

### 验证

- `tests/test_behavior_trace.py` 单模块：`14/14 OK`。
- 完整 Python 回归 `toolkit/python.exe -m unittest discover -s tests`：`180/180 OK`（旧 166 → 180）。
- `compileall` 覆盖 `module/behavior_trace.py`、`module/device/control.py`、`script.py`、`tasks/Script/config_optimization.py`、`tests/test_behavior_trace.py`：通过。
- `git diff --check`：通过（仅既有 docs 文件 LF/CRLF 提示，与本次无关）。
- 未做真机 / 游戏内测试。

### 与设计审查的偏差

设计审查记「文件不 flush、不 fsync（靠关闭时刷）」。实现改为 `open(..., buffering=1)` 行缓冲：测试需要立即读到内容，且观测日志在进程被杀时更需要尾部不丢。行缓冲每条一次 write 系统调用（非 fsync），开销约 17 µs/条，仍属「很小」。

### Git

- 未 commit、未 push。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-01 - BehaviorTrace set_task 生命周期复核 + Control.swipe duration 假语义清理

### 第一部分：BehaviorTrace `set_task()` 生命周期只读复核

**结论：无需修改。** 沿当前 `Script.run` 源码逐条确认所有出口：

- **正常完成 / 正常 fail / 普通 Exception**：`ScriptTask.run()` 多数以 `raise TaskEnd` 结束 → 被 `except Exception` 捕获 → `self._handle_task_exception(e, command)` 返回 True/False → `outcome` 存值、`trace_result` 据此置位 → `return outcome`。Python 在 `except` 内 `return` 时 `finally` 先执行：`trace.record('TASK', ...)` 后 `trace.set_task('')`。TASK 事件带正确 `command`，任务名随后被清空。
- **`exit(1)`（`ScriptError` / `RequestHumanTakeover` / generic）**：`_handle_task_exception` 内 `exit(1)` 抛 `SystemExit`（`BaseException`，不被 `except Exception` 捕获），但 `finally` 在异常向上传播时仍执行 → 写一条 `result='fail'` 的 TASK 事件、`set_task('')`，然后 `SystemExit` 继续。
- **`set_task(command)` 之前的提前 return / 异常**：`Script.run` 在 `trace.set_task(command)`（begin_global_activity 之后）之前没有任何 `return`；若 `get_fatigue_manager` / `begin_task` / `begin_global_activity` 抛异常，本轮 `set_task` 从未被调用，而上一轮的 `finally` 已把 `_task` 清成 `''`，无残留。
- **任务之间的 Control 动作**：上一任务 `finally` 已 `set_task('')`，下一任务 `Script.run` 早早 `set_task(next_command)`。中间若有导航 / Restart 触发的 `Control.click` / `swipe`，其 ACTION 事件正确得到 `task: ""`，**不会继承上一个任务名**。
- 顺序正确：先 `record('TASK', target=command, ...)` 再 `set_task('')`，TASK 事件不会因提前清空而丢任务名。

用户设想的「RealmRaid 结束后、下一个任务前的 Control 动作 task 错误保留为 RealmRaid」——**不会发生**。未改任何代码。

### 第二部分：清除 `Control.swipe` 的 duration 假语义（方案 A）

**全仓 duration 消费核实**：

| 后端 | 底层方法签名 | 是否消费 duration |
|---|---|---|
| minitouch | `swipe_minitouch(self, p1, p2)` | 否 |
| adb | `swipe_adb(self, p1, p2, duration=0.1)` | 是（`Control.swipe` else 分支先 `duration *= 2.5`） |
| uiautomator2 | `swipe_uiautomator2(self, p1, p2, duration=0.1)` | 是 |
| scrcpy | `swipe_scrcpy(self, p1, p2)` | 否 |
| window_message | `swipe_window_message(self, startPos, endPos)` | 否 |

`Control.swipe(..., duration=...)` 的其他调用方：仅 `Control.swipe_vector`（合法 passthrough，公共 API，不动）；`tasks/KekkaiUtilize/script_task.py:1035` 是注释掉的行。RyouToppa `flush_area_cache` 是唯一给 `duration` 传随机值的业务调用点。

调用链：`RyouToppa.flush_area_cache` → `duration = random_delay(0.342, 0.362)` → `self.device.swipe(..., duration=duration)` → `Control.swipe` → `control_method == 'minitouch'` → `self.swipe_minitouch(p1, p2)`（**duration 在此消失**，`ensure_time(duration)` 之后再无引用）。

**修改**：

- `module/device/control.py`：`Control.swipe` 新增中文 docstring，说明 duration 只对 uiautomator2 / adb 生效，minitouch / scrcpy / window_message 忽略。**未删 `duration` 形参**（adb / uiautomator2 仍需要）。
- `tasks/RyouToppa/script_task.py:flush_area_cache`：删除两处 `duration = random_delay(...)` 采样与 `self.device.swipe(...)` 的 `duration=duration` 传参，补中文注释。
- `tests/test_swipe_duration_cleanup.py`：新增，7 用例。
  - `Control.swipe` 契约：minitouch / scrcpy / window_message 调用底层 swipe **不带** `duration` kwarg；uiautomator2 / adb **带** `duration` kwarg。
  - RyouToppa `flush_area_cache`：swipe 调用只有 `p1` / `p2` / `control_name` 三个 kwarg、`control_name == '寮突破列表滑动'`、起点终点与 distance 抖动逻辑（`850+randint(-12,12)` 等）不变、成功识别时正常返回 `None`、不再调用 `random_delay`。

**未改动**：滑动距离 / 起点 / 终点 / MOVE interval / 轨迹 / 等待 / 状态机 / retry / random 分布。`random_delay` import 保留（`attack_area` 的 `random_delay(1.0, 3.0)` / `(0.2, 0.6)` 真实 `time.sleep` 仍在用）。**本轮未实现 minitouch 的 duration 支持。**

**行为影响**：

- minitouch 后端（项目当前默认配置）：`duration` 本就被丢弃，删除是**验证过的 no-op**，真实滑动时序不变。
- adb / uiautomator2 后端：RyouToppa 列表滑动时长会从传入的 ~0.35s 回落到 `Control.swipe` 默认（uiautomator2 `(0.1,0.2)`；adb `(0.1,0.2)×2.5`）。**滑动距离不变**，仅速度回到后端默认，且 `flush_area_cache` 每次滑动后 `_wait_for_ryou_toppa_page` 状态确认可自我校正。此前的 ~0.35s 本就只在这两个后端生效，属误导性代码而非有意时序设计。

### 验证

- `tests/test_swipe_duration_cleanup.py` 单模块：`7/7 OK`。
- 完整 Python 回归 `toolkit/python.exe -m unittest discover -s tests`：`187/187 OK`（旧 180 → 187）。
- `compileall` 覆盖 `module/device/control.py`、`tasks/RyouToppa/script_task.py`、`tests/test_swipe_duration_cleanup.py`：通过。
- `git diff --check`：通过（仅既有 docs 文件 LF/CRLF 提示）。
- 未做真机 / 游戏内测试。

### 已知剩余项（本轮不处理）

- BehaviorTrace v1 的 `self.device.swipe_adb(...)` 直连路径未覆盖（KekkaiUtilize / KekkaiActivation 好友列表滑动），留待 Kekkai 状态驱动重构。
- `module/atom/swipe.py` 的 `RuleSwipe.trace()` 及 `BezierTrajectory` 导入、两个 `cached_property` 为死代码，待后续清理（见机械性修改清单 M3）。
- `wait_list_changed` / `wait_list_stable` 尚未接入。
- 业务状态机改造等待真机窗口（用户约一周内无法真机实测）。

### Git

- 未 commit、未 push。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-01 - Swipe duration 收口 + RuleSwipe 死代码清理（T3-1 / T3-2）

### T3-1：收回「删除 RyouToppa duration」，恢复所有后端原行为

上一条目里「删除 RyouToppa `flush_area_cache` 的 `duration` 采样与传参」对 minitouch 是 no-op，但对 adb / uiautomator2 会把 RyouToppa 列表滑动时长从 ~0.35s 改成后端默认——属真实行为变化，且当前无法真机验证。本轮**收回该删除**：

- `tasks/RyouToppa/script_task.py:flush_area_cache` 恢复到与 HEAD 逐字一致：`attempt == 1` 用 `random_delay(0.342, 0.362)`、其他 `attempt` 用 `random_delay(0.349, 0.355)`，`self.device.swipe(p1=..., p2=..., duration=duration, control_name='寮突破列表滑动')` 原样传参。起点 / 终点 / `distance` / retry / 状态等待均未动。
- 保留上一轮已确认正确的 `Control.swipe` 中文 docstring（说明 duration 只对 uiautomator2 / adb 生效，minitouch / scrcpy / window_message 忽略）。**未删 `duration` 形参**，未改任何后端实现。
- `tests/test_swipe_duration_cleanup.py`：把两个「锁 RyouToppa 不传 duration」的用例换成「锁 RyouToppa 仍按原逻辑传 duration」——`test_flush_area_cache_first_attempt_passes_duration`（首次即识别成功只滑一次，swipe kwarg 恰为 `{p1, p2, duration, control_name}`，`random_delay` 以 `(0.342, 0.362)` 调用一次，坐标抖动逻辑不变）、`test_flush_area_cache_retry_attempt_uses_narrower_interval`（首次识别失败、第二次成功，两次滑动，`random_delay` 依次以 `(0.342, 0.362)` / `(0.349, 0.355)` 调用）。`Control.swipe` 五后端契约用例保留。

**结论**：所有控制后端下 RyouToppa 列表滑动行为与本会话之前完全一致；净新增仅 `Control.swipe` docstring + 契约测试。

### 全仓 duration 消费核实

| 后端 | 底层方法 | 消费 duration | 本轮最终行为与修改前一致 |
|---|---|---|---|
| minitouch | `swipe_minitouch(p1, p2)` | 否 | 是（一直被丢弃） |
| adb | `swipe_adb(p1, p2, duration=0.1)` | 是（`Control.swipe` else 分支先 `duration *= 2.5`） | 是（RyouToppa 仍传原 duration） |
| uiautomator2 | `swipe_uiautomator2(p1, p2, duration=0.1)` | 是 | 是（同上） |
| scrcpy | `swipe_scrcpy(p1, p2)` | 否 | 是 |
| window_message | `swipe_window_message(startPos, endPos)` | 否 | 是 |

### T3-2：RuleSwipe 死代码清理

**引用复核**（全仓 grep，排除 `toolkit/` 第三方）：

- `.trace(` 调用：`module/` `tasks/` `script.py` `dev_tools/` `tests/` 内**零命中**（仅匹配到 `class RuleSwipe:` 定义行）。
- `is_default_mode` / `is_vector_mode`：仅在 `module/atom/swipe.py` 定义（行 34 / 42）并在 `trace()` 内部使用（行 63 / 81），无外部消费者。
- `BezierTrajectory`：`module/atom/cBezier.py`（类定义）+ `module/atom/swipe.py`（import + `trace()` 使用）；**另有** `module/base/cBezier.py`（**不同文件**）被 `module/device/method/windows_impl.py:swipe_window_message` 使用。
- `RuleSwipe` 本身被 ~120 处 `assets.py` / 任务用 `RuleSwipe(roi_front=..., roi_back=..., mode="default", name=...)` 构造并交给 `BaseTask.swipe` → `Control.swipe`，全部只经 `coord()`，无一调用 `trace()`。
- `RuleSwipe.trace()` 本身已损坏：`start_pos, end_pos = self.coord()` 对 4 元组解包会 `ValueError`，进一步佐证是废弃代码。

**删除**（`module/atom/swipe.py`）：

- `RuleSwipe.trace()` 方法（含内嵌 `generate_linear_trajectory`）。
- `is_default_mode` / `is_vector_mode` 两个 `cached_property`。
- import：`import random`、`from math import dist`、`from module.base.decorator import cached_property`、`from module.atom.cBezier import BezierTrajectory`。

**保留**：

- `RuleSwipe.__init__` / `coord()` / `self.interval` / `self.name` 等生产 API。
- `from module.base.utils.random import random_center_point_in_roi`（`coord()` 依赖）。
- `from module.logger import logger`（本文件既有的未使用 import，非本次死路径造成，按范围不动）。
- `module/atom/cBezier.py` 文件（删 `trace()` 后成为孤儿，但删整个模块文件超出「清理因死路径而无用的内容」的边界，留作独立决定）。
- `module/base/cBezier.py` 与 `windows_impl.py:swipe_window_message`（window_message 后端真实生产路径，与 `RuleSwipe.trace()` 无关）。

**测试**：`tests/test_rule_swipe_trace_removed.py` 新增，4 用例——模块可导入且 `coord()` 返回 4 元组落在 ROI 内、`RuleSwipe` 不再有 `trace` / `is_default_mode` / `is_vector_mode` 属性、`swipe.py` 不再含 4 个死 import（且保留 `random_center_point_in_roi` import）、`RuleSwipe` 的 `dir()` 无 `trace`。

### 验证

- `tests/test_swipe_duration_cleanup.py` 单模块：`7/7 OK`。
- `tests/test_rule_swipe_trace_removed.py` 单模块：`4/4 OK`。
- 完整 Python 回归 `toolkit/python.exe -m unittest discover -s tests`：`191/191 OK`（旧 187 → 191；swipe_duration 仍 7 个，2 个用例被替换非新增）。
- `compileall` 覆盖 `module/` `tasks/` `tests/` `script.py`：通过。
- `git diff --check`：通过（仅既有 docs 文件 LF/CRLF 提示）。
- 未做真机 / 游戏内测试。

### 行为影响

**本会话完成后，现有真实生产行为与 T3-1 修改前完全一致。**

- RyouToppa `flush_area_cache`：byte-identical to HEAD，所有后端行为不变。
- `Control.swipe`：只加 docstring，形参与所有分支实现不变。
- `RuleSwipe`：只删零调用方死代码，`coord()` 与所有 `RuleSwipe` 消费者不受影响；minitouch / adb / uiautomator2 / scrcpy / window_message 的真实滑动路径完全未触碰。
- 未改：MOVE interval、贝塞尔轨迹、RuleSwipe endpoint 分布（`random_center_point_in_roi`）、random 算法、screenshot、Timer、BaseTask、GeneralBattle、Kekkai、RealmRaid、BehaviorTrace 模型。

### 已知剩余项

- `wait_list_changed` / `wait_list_stable` 独立设计与测试。
- `harvest_card` 状态驱动改造等待真机。
- Kekkai 列表迁移（含 BehaviorTrace 的 `swipe_adb` 直连覆盖缺口）等待真机。
- RealmRaid 核心流程等待真机。
- GeneralBattle 后期处理。
- `module/atom/cBezier.py` 孤儿文件是否删除，留作独立决定。

### Git

- 未 commit、未 push、未真机测试。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-01 - 建立 AI 开发交接文档体系

### 目标

在现有 `docs/AI_CONTEXT.md` / `docs/DEVELOP_LOG.md` 基础上，新增 4 份职责分离的项目文档，并把「每次开发后逐项同步受影响文档」固化为强制规则、写入仓库根入口文件，使换 Claude / Codex / 换会话后仍能依靠仓库自身恢复「当前状态、下一步、真实架构、设计原因、验证方法」。本轮不改任何业务代码。

### 新增文件

- `docs/ROADMAP.md`：下一步做什么、优先级、前置依赖、Level A/B（可静态验证）vs Level C（需真机）分区。按当前真实状态初始化——已完成区收录 T0-1 / T1-1 / T1-2 / T3-1 / T3-2 + 疲劳系统 + KekkaiUtilize 阈值 + 随机源一致性；P1 收录 List Changed/Stable 组件、`harvest_card` 状态驱动、Wait/Retry 策略；暂缓区收录 `cBezier.py` 孤儿、`_publish_fatigue_state` 轮询、GeneralBattle 退化区间。
- `docs/ARCHITECTURE.md`：总体分层图（Script Runtime → Scheduler/Config → Task → BaseTask/GeneralBattle/GameUi → Rule* → Control → Device Backend）+ 每层职责（负责 / 不负责 / 核心文件）+ 关键调用链（appear_then_click、swipe、通用战斗、Script.run episode、疲劳安全节点）+ 多后端 duration 差异表 + 扩展点建议。按当前源码核对。
- `docs/DECISIONS.md`：轻量 ADR，初始化 D001~D009——confirm_delay 默认不启用、稳定性基础层不因随机化修改、Control.swipe duration 后端相关、BehaviorTrace v1 范围、BehaviorTrace 任务归属由 finally 闭环、RuleSwipe 只提供端点、公共随机统一、不无依据重写 GeneralBattle FSM、upstream 业务模块不随意回退。
- `docs/TESTING.md`：默认验证流程（相关单测 → compileall → 完整回归 → git diff --check，一律用 `toolkit/python.exe`）+ 测试分级 A/B/C + 真机禁止事项 + Git 规则 + 测试失败与新增测试处理（正反向验证、哨兵防挂死、非严格性能断言）。
- 仓库根 `CLAUDE.md`：AI 入口规则——阅读顺序、以源码为准、6 文档强制同步 + 报告固定「## 文档同步」段、中文注释、默认不 commit/push、默认不碰真机、验证流程、收尾流程。
- 仓库根 `AGENTS.md`：与 `CLAUDE.md` 一致的规则（要点摘录 + 指向 `CLAUDE.md` 正文），供 Codex 使用。
- **注**：本条目创建时 `CLAUDE.md` / `AGENTS.md` 被 `.gitignore` 的 `# ai` 段忽略、未纳入版本控制。**该问题已在下一条 2026-09-01「文档同步规则收口」中解决**——`.gitignore` 加了 `!CLAUDE.md` / `!AGENTS.md` 例外，两文件现随仓库提交，跨 clone 后仍在。`.claude/` `.codex/` 等其余本地 AI 目录仍保持忽略。

### 编辑文件

- `docs/AI_CONTEXT.md`：
  - 新增 §0「文档体系与阅读顺序」（6 文档职责表 + 阅读顺序 + 指向 `CLAUDE.md` / `AGENTS.md`）。
  - §2 Git 状态：未跟踪清单补 4 份新 doc + `CLAUDE.md` / `AGENTS.md`。
  - §8.2：`module/atom/swipe.py` Bezier 轨迹条目更新为「已随 RuleSwipe.trace() 死代码删除」。
  - §9：新增「文档体系已建立」「当前限制（约一周无法真机）」两条。
  - §10「AI 修改规则」重写：合并精简 1~8 条，新增 §10.1「文档同步（强制收尾）」——纯分析不写、有代码改动逐项判断 6 文档只更新相关的、报告固定「## 文档同步」段、各文档维护纪律。

### 文档同步机制（本轮确立的长期规则）

今后每次开发任务结束前，Claude / Codex 必须逐项检查 6 份项目文档（`AI_CONTEXT` / `DEVELOP_LOG` / `ROADMAP` / `ARCHITECTURE` / `DECISIONS` / `TESTING`），**只更新真正受影响的文件**（不机械改全部），并在开发报告结尾固定输出：

```
## 文档同步
- AI_CONTEXT.md：已更新 / 无需更新（原因）
- DEVELOP_LOG.md：已更新 / 无需更新（原因）
- ROADMAP.md：已更新 / 无需更新（原因）
- ARCHITECTURE.md：已更新 / 无需更新（原因）
- DECISIONS.md：已更新 / 无需更新（原因）
- TESTING.md：已更新 / 无需更新（原因）
```

本轮没有改变任何一份文档负责的项目事实时（纯问答 / 纯读代码走查、没有落地任何结论）→ 6 份都不写。判断标准是「项目事实是否变化」，不是「是否改了代码」——该措辞在下一条 2026-09-01「文档同步规则收口」条目中被修正为最终版。

### 验证

- 本轮无代码修改，未跑完整单元测试（按任务要求）。
- 一致性检查：Markdown 内部路径引用均指向真实存在的文件；ROADMAP「已完成」与 AI_CONTEXT §4.12~4.15 一致；DECISIONS D001~D009 与 ARCHITECTURE §2/§4 无冲突；TESTING 命令与项目真实工具（`toolkit/python.exe` 3.10.11、`unittest`、无 CI/lint）一致；`CLAUDE.md` 与 `AGENTS.md` 规则一致。
- `git diff --check`：通过（仅既有 docs 文件 LF/CRLF 提示）。

### Git

- 未 commit、未 push、未修改业务源码。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-01 - AI 交接文档体系收口（Git 术语 / 同步规则 / gitignore 例外）

### 目标

对上一条「建立 AI 开发交接文档体系」做小范围收口，3 件事，不改任何业务代码：
1. 修正文档 / 报告中对 Git `??` 的错误术语；
2. 把文档同步判断标准从「是否修改了代码」改为「本轮是否改变了该文档负责的项目事实」；
3. 让 `CLAUDE.md` / `AGENTS.md` 真正进入版本控制，保证重新 clone / 换机器后仍有稳定启动入口。

### 修改

- **`.gitignore`**：在 `# ai` 段的 `AGENTS.md` / `CLAUDE.md` 忽略行之后加两行例外 `!AGENTS.md` / `!CLAUDE.md`（并加中文注释）。gitignore 后置规则覆盖前置匹配，`git check-ignore` 现命中的是 `!` 规则、`git status` 现把两文件显示为 `?? AGENTS.md` / `?? CLAUDE.md`。`.claude/` `.codex/` `openspec/` `.agents/` `skills-lock.json` `.codegraph/` 仍保持忽略——最小例外，未扩大范围。
- **`CLAUDE.md`**：重写为轻量启动入口。删除「不纳入版本控制」的头注；核心规则 2 改为「按『本轮是否改变了该文档负责的项目事实』判断是否更新某份文档，不以『是否修改了代码』为唯一标准」，并举例纯设计工作（定架构 / 增删长期决策 / 改 ROADMAP / 测试规范 / 真机要求 / AI 规则）没动代码也要更新对应文档。保留阅读顺序、核心规则、强制收尾流程 + 「## 文档同步」模板。不含 HEAD / 测试数字 / 任务详情。
- **`AGENTS.md`**：与 `CLAUDE.md` 同步为一致的等价内容（各自独立包含核心规则，不只是「去读另一个文件」）。删除「不纳入版本控制」头注。
- **`docs/AI_CONTEXT.md`**：
  - §0：文档表的「何时更新」列逐份细化为「负责的项目事实」+ 触发条件；表前加一句总纲「以『本轮是否改变了该文档负责的项目事实』为准，不以『是否修改了代码』为唯一标准」；「入口规则」段改为「`CLAUDE.md` / `AGENTS.md` 已通过 `.gitignore` `!` 例外纳入版本控制」。
  - §2：`M` / `AM` / `??` 术语解释；「未跟踪」清单标注「均为未跟踪的新文件，不是『已跟踪』」；补一条 `.gitignore` `!CLAUDE.md` / `!AGENTS.md` 例外说明。
  - §10.1：删除「没有代码修改 → 6 份都不写」的绝对措辞，改为「每次开发或正式设计任务结束前逐项检查，按『该文档负责的项目事实是否变化』决定是否更新」+ 纯设计工作没动代码也可能要更新的清单 + 「本轮没有改变任何一份文档负责的项目事实 → 6 份都不写」。条目重编号（原 9~12 → 9~14）。
  - §8.2 / §9 / §26 等随现状订正（此前几轮已做，本轮仅核对）。
- **`docs/DEVELOP_LOG.md`**：
  - 上一条「建立文档体系」条目里「没有代码修改 → 6 份都不写」的措辞，就地加一句指向本条目的修正说明；关于 `CLAUDE.md` / `AGENTS.md` 被忽略的「注」改为「已在本条目解决」。
  - 更早（2026-09-01「文档规则变更」）条目里「没有代码修改则两份文档都不写」的引述后补一段 `>` 引用说明「后续修正为 6 份 + 按项目事实判断」。历史引述本身保留。
- **`docs/ROADMAP.md`**：「已完成」表加一行「AI 交接文档体系」；「当前任务」段去掉「本轮在建文档体系」的临时描述。
- **`docs/ARCHITECTURE.md`** / **`docs/TESTING.md`**：把指向 `AI_CONTEXT.md §10` 的引用精确到「§0 表 + §10.1」；TESTING §7 收尾流程标题与步骤改为「开发 / 正式设计」并明确按「项目事实是否变化」判断。

### 未改动

- 任何业务源码 / 测试代码 / 配置行为。
- `# ai` 段的其他忽略项。
- DECISIONS.md（本轮未产生新决策，也未推翻旧决策；文档同步规则的措辞属流程规则、写在 AI_CONTEXT §10.1 + CLAUDE/AGENTS，不是 ADR）。

### 验证

- `git check-ignore -v CLAUDE.md AGENTS.md`：现命中 `.gitignore` 的 `!CLAUDE.md` / `!AGENTS.md` 例外行；`git status --short` 现显示 `?? CLAUDE.md` / `?? AGENTS.md`（此前被隐藏）。
- `git diff -- .gitignore`：仅新增 3 行（1 注释 + `!AGENTS.md` + `!CLAUDE.md`），无删除。
- 全仓 grep：无处再写「没有代码修改则 6 份 / 两份都不写」的绝对措辞（历史引述处已加修正说明）；无处把 `??` 说成「已跟踪」。
- `CLAUDE.md` ↔ `AGENTS.md` 核心规则一致；`AI_CONTEXT.md` §0 / §10.1 与两入口文件一致；`ROADMAP` 无错误 Git 术语；`ARCHITECTURE` / `DECISIONS` 与 `TESTING` 无冲突。
- `git diff --check`：通过（仅 `docs/AI_CONTEXT.md` / `docs/DEVELOP_LOG.md` 的 LF/CRLF 警告）。
- 本轮无业务源码变化，未跑 191 个单元测试（按任务要求）。

### Git

- 未 commit、未 push。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-01 - T4-1：List Changed / Stable 独立视觉状态组件

### 目标

在不改变任何真实生产任务行为的前提下，建立一个经纯单元测试验证的通用视觉 `changed` / `stable` 状态基础组件，为一周后的真实列表状态驱动改造（T5-2 `list_find` / T4-2 `harvest_card` 等）做准备。本轮**不接入任何真实任务**。

### 现有能力审查

- `module/atom/animate.py` 的 `RuleAnimate.stable`：比较连续两帧目标区域是否一致——同域，但走 image RPC（`get_image_client().match_dynamic_template`），且只返回 bool，无 `changed` vs `stable` 之分、无 `stable_count`、无归一化差异分。不适合作纯组件复用。
- `tasks/base_task.py` 的 `wait_until_stable` / `wait_animate_stable`：是 BaseTask 里的**设备轮询循环**（`while` + `screenshot` + `Timer`），正是 T4-1 明确禁止做的那一层。
- `module/atom/image.py` `RuleImage.match_mean_color`、`module/base/utils/utils.py` `color_similar` / `get_color` / `crop`：颜色 / 裁剪工具，无「连续帧差异」能力。
- `module/image/` 全是 RPC 服务层（`rpc.py` / `operators/` / `recipes/`）。
- 结论：**无现成的纯、可单测的连续帧 changed/stable 组件**。复用 `module/base/utils` 的 `crop` 语义、`area_limit`（ROI clamp）、`image_size`；差异算法与状态机需新增最小组件。不引入第三方依赖（只用 `numpy` + `module.base.utils`）。

### 新增

- **`module/atom/frame_state.py`**（~185 行）：
  - `frame_difference(frame_a, frame_b, roi=None, pixel_threshold=15) -> float`：ROI 内逐像素取各通道绝对差的最大值，`> pixel_threshold` 记为变化像素，返回变化像素占比 `[0.0, 1.0]`（方案 B）。`DEFAULT_PIXEL_THRESHOLD = 15` 为通用保守值。
  - `FrameStateResult`（frozen dataclass）：`changed` / `stable` / `difference` / `stable_count`。
  - `FrameStateDetector(changed_threshold, stable_threshold, stable_frames, roi=None, pixel_threshold=15)`：三个判定阈值**无默认值、必须显式传**。`reset(baseline)` / `update(frame) -> FrameStateResult`；不显式 `reset` 时首个 `update` 帧作基线（不计入 `stable_count`）。属性 `changed` / `stable` / `stable_count` / `last_difference`。
  - 语义（见 `docs/DECISIONS.md` D010）：`changed` 相对基线、一旦成立锁存、`reset` 前不回退；`stable` 基于相邻帧、连续 `stable_frames` 帧安静才成立、任一相邻明显变化清零；两者独立。
  - 依赖：`numpy` + `module.base.utils.{area_limit, image_size}`。不依赖 Device / BaseTask / Timer / OCR / BehaviorTrace / cv2。不截图 / 不 sleep / 不轮询。
  - 异常：帧 None / 非 ndarray / ndim 非 2·3 / 空帧 / 两帧 shape 不一致 / ROI 非四元组 / `x2<=x1` 或 `y2<=y1` / ROI 与图完全无重叠 → `ValueError`（不 silent resize）；ROI 部分越界按 `area_limit` clamp。ROI 用项目既有 `(x1,y1,x2,y2)` 约定，不引入第二种坐标格式。
- **`tests/test_frame_state.py`**（25 用例）：
  - `frame_difference`：相同帧=0、全图变化=1、ROI 内=1 / ROI 外=0、小面积噪声占比精确、`pixel_threshold` 灵敏度、灰度帧、shape 不一致 / None / 非 ndarray / 非法 ROI（零宽高 / 完全越界 / 三元组）报错、部分越界 clamp、score 恒 `[0,1]`（20 组随机 × 3 种 ROI）。
  - `FrameStateDetector`：一直静止（`changed=F`, `stable=T`, `stable_count` 序列 `[1,2,3]`）、变化后稳定（`changed=T`, `stable=T`）、持续变化（`stable=F`, 恒 `stable_count=0`）、中途明显变化清零 `stable_count`、变化后回基线（`changed` 不回退、`difference` 归 0、`stable` 仍成立）、detector 层 ROI 内外隔离、`reset` 清空、首个 `update` 帧自动作基线、属性访问器、构造参数校验（`stable_frames<1` / 负阈值）、`update` shape mismatch、`reset` 非法 ROI 立即报错、`DEFAULT_PIXEL_THRESHOLD` 常量。

### 模块位置理由

放 `module/atom/frame_state.py`：`module/atom/` 是「帧原子 / Rule*」层（ARCHITECTURE §2），`RuleAnimate`（`animate.py`）是「连续帧稳定判定」的 RPC 版兄弟，`frame_state` 是其纯 numpy、无外部依赖的对应物；ARCHITECTURE §5 扩展点表原本就建议 `module/atom/`。不放 `module/base/utils/`（那是 `from ... import *` 的函数杂货袋，不适合放有状态类；但复用了其中的 `area_limit` / `image_size`）。不放 `module/image/`（RPC 服务层）。不放 `module/` 顶层（`fatigue.py` / `behavior_trace.py` 那种带注册表 / 生命周期的子系统，本组件更小）。不新建目录（单文件）。

### 生产影响

- 未修改 BaseTask / 任何 Task / Control / Device / Screenshot / OCR / BehaviorTrace / minitouch / random / Timer。
- 未新增 screenshot / sleep / swipe 改动。
- 新增组件**零生产消费者**（全仓 grep `frame_state` / `FrameStateDetector` / `frame_difference` 在 `module/` `tasks/` `script.py` 内除自身外无命中）。

### 验证

- `tests/test_frame_state.py` 单模块：`25/25 OK`。
- 完整 Python 回归 `toolkit/python.exe -m unittest discover -s tests`：`216/216 OK`（旧 191 → 216）。
- `compileall` 覆盖 `module/atom/frame_state.py`、`tests/test_frame_state.py`：通过。
- `git diff --check`：通过（仅既有 docs 文件 LF/CRLF 提示）。
- 未做真机 / 游戏内测试。

### 尚未验证（等真机窗口）

真实列表 ROI、真实 `changed_threshold` / `stable_threshold` / `stable_frames`、真实截图轮询 interval、真实 timeout、Kekkai 实际滚动动画、其他任务页面动画（顶部动画 / 货币数值 / 聊天 / 背景特效）对稳定判断的干扰。后续路线：开 BehaviorTrace 采集旧行为 baseline → 采集真实列表帧 → 定 ROI / threshold / stable_frames → 设计真正的设备等待层 → 迁移 `BaseTask.list_find` → 再迁移 Kekkai。

### Git

- 未 commit、未 push、未真机测试。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-01 - BehaviorTrace 点击位置统计后端 v1

### 目标

为 OASX「配置详情 → 统计 → 点击分布」页面提供后端：BehaviorTrace 记录 click / long_click 真实最终坐标，并提供一个按需读取指定 config + 日期 JSONL 的只读接口。本轮只做后端，不改 OASX / Flutter。

### 后端架构审查

- OASX ↔ OAS 走 FastAPI（`module/server/app.py`，`include_router` 挂 `home / script / stats / log / tool` 五个 `APIRouter`）。
- 「统计」页面数据来自 `stats_router.py` 的 `stats_app`（prefix `/stats`），逻辑在 `module/server/log_stats.py` 的 `log_stats_service`。风格：路径参数 `{script_name}`、`date` 用 `Query(..., alias="date")`、`_parse_target_date` 非法抛 `HTTPException(422, "Invalid date format...")`、`response_model` 用 pydantic。
- `log_service.py` 有 `normalize_script_name` / `sanitize_path_name` / `ensure_child_path` 路径安全工具；`config_manager.py` 有 `ConfigManager.validate_config_name(name, allow_template=)`（拒 `. / \ : * ? " < > |` 与控制字符，抛 `ConfigNameError`）与 `all_script_files()`。
- server 单进程（`fastapi_app()`），脚本子进程是 spawn。OASX 左侧选 `oas1/oas2` 后作为 `{script_name}` 路径段传给后端。
- 结论：复用现有 FastAPI + `stats_app`，不新造 Web 服务。

### 修改

- **`module/device/control.py`**：`Control.click` / `Control.long_click` 在已有 `get_behavior_trace(...).record('ACTION', ...)` 调用里加 `extra={'x': x, 'y': y}`。`x` / `y` 是同函数内 `x, y = ensure_int(x, y)` 之后、真正 `method(x, y)` 用的最终坐标。**未改 `module/behavior_trace.py`**（`record` 早有 `extra` 形参，`json.dumps(default=str)` 兜底）。未新增 `coord()` / 随机 / screenshot / sleep，未改点击顺序与异常传播。事件类型仍只有 `ACTION` / `TASK`。
- **`module/server/behavior_stats.py`**（新增，~170 行）：
  - `read_behavior_clicks(script_name, target_day) -> dict`：`_normalize_script_name`（沿用 `log_stats` 的按 `_` 截首段）→ `_behavior_file_path`（`_SAFE_CONFIG_RE = [A-Za-z0-9][A-Za-z0-9_-]*` fullmatch + `resolve().relative_to(BEHAVIOR_LOG_ROOT)` + `path.name == file_name` 三重挡穿越）→ `path.is_file()` 才逐行 `for line in handle` 读；只留 `event=='ACTION'` 且 `action in {click,long_click}` 且 `extra.x/y` 可 `_coerce_coord`（bool 排除、float 取 round、NaN/inf → None）的记录。坏 JSON 行 / 非 dict → `skipped_lines += 1` 并继续；缺字段 / 类型错误的合法 JSON → 静默过滤。返回 `{config, date, screen{width,height}, summary{total,click_count,long_click_count,task_count,skipped_lines}, tasks[], points[]}`。`points` 保持文件顺序，`tasks` 按首现顺序。
  - `CANONICAL_SCREEN_WIDTH/HEIGHT = 1280/720`：`module/device/screenshot.py` `check_screen_size` 强制的逻辑分辨率，asset ROI 与 Control 坐标都在此空间；minitouch 的设备分辨率缩放（`CommandBuilder.convert`）发生在 Control 之后。所有事件同一坐标空间，故 `screen` 只在响应顶层返回一次，JSONL 每条不重复存宽高。
  - `BehaviorStatsError(status_code, message)`：业务异常，路径 / config 非法时抛。
- **`module/server/stats_router.py`**：
  - import `behavior_stats`（`BehaviorStatsError` / `read_behavior_clicks`）与 `config_manager`（`ConfigManager` / `ConfigNameError`）。
  - 新增 pydantic 响应模型 `BehaviorScreen` / `BehaviorClickPoint`（`elapsed_ms: int | None`）/ `BehaviorClickSummary` / `BehaviorClicksResponse`。
  - 新增 `@stats_app.get("/{script_name}/behavior/clicks", response_model=BehaviorClicksResponse)`：`ConfigManager.validate_config_name(script_name, allow_template=False)` 失败 → `HTTPException(422)`；`_parse_target_date(date)` 复用既有；`read_behavior_clicks` 抛 `BehaviorStatsError` → `HTTPException(exc.status_code)`。路由注册顺序在 `/{script_name}`（单段）之前，三段路径不冲突。
- **`tests/test_behavior_click_stats.py`**（新增，20 用例）：见下。

### 坐标体系

- 逻辑尺寸 `1280×720`（`screenshot.check_screen_size` 强制；`minitouch.py` `max_x/max_y` 亦 `1280/720`）。项目**没有**名为 `CANONICAL_*` 的共享常量，本轮在 `behavior_stats.py` 定义并注释来源。
- 无设备分辨率配置影响到 Control 层坐标：`Control.click(x, y)` 收到的永远是 1280×720 逻辑坐标，minitouch `convert()` 才按设备 `max_x/max_y` 缩放。
- `screen` 在 API 响应顶层返回一次；JSONL 不存宽高。

### 资源影响

| 场景 | 额外开销 |
|---|---|
| OAS 正常运行 | 每个 click / long_click 的 ACTION JSONL 多两个整数字段 `x` / `y`（几十字节）。无其他。 |
| 接口未被请求 | **零**——无后台线程、无定时扫描、无 JSONL 解析、无常驻任务、无数据库、无 SSE。 |
| 接口被请求一次 | 打开当天单个 JSONL、`for line in f` 逐行读一次、返回、关闭。无缓存（每次请求重读）。 |

### 安全性

- **config 校验**：router 用 `ConfigManager.validate_config_name`（项目既有）拒 `.` / 路径字符 / 控制字符；Reader 再用 `_SAFE_CONFIG_RE` fullmatch（`.` `..` `/` `\` `%` 空 均拒）。
- **date 校验**：复用 `stats_router._parse_target_date`（`strptime("%Y-%m-%d")`，非法 → `HTTPException(422)`）。
- **路径穿越**：`_behavior_file_path` 三重挡——正则 fullmatch → `(BEHAVIOR_LOG_ROOT / name).resolve().relative_to(BEHAVIOR_LOG_ROOT)` → `path.name == file_name`。`../oas1`、`..`、`/etc/passwd`、`a/../../oas1`、null 字符均在读取前抛 `BehaviorStatsError(400)`。
- **坏 JSONL 容错**：单行 `json.loads` 异常 / 非 dict → 跳过 + `skipped_lines`；不因一条坏记录整天失败；`skipped_lines` 作为调试字段随 `summary` 返回。

### 测试

- `tests/test_behavior_click_stats.py`：`20/20 OK`。
  - `ControlClickCoordTraceTest`（5）：`Control.click` / `long_click` 记录的 `extra.x/y` 与传给 mock 后端的最终坐标一致、caller 传 float 时 `extra` 为 int、`task`/`target`/`result=ok`/`elapsed_ms` 仍正确、底层动作抛异常时不写 ACTION、disabled 时零 IO。
  - `ReadBehaviorClicksTest`（15）：正常文件只回 click/long_click、旧格式无 x/y 跳过、多任务按首现顺序、空文件 / 缺文件返回空、单行坏 JSON 跳过、缺字段 / 类型错误 / bool 坐标跳过、非法 config（含 `.` `..` 控制字符 空）与路径穿越抛 `BehaviorStatsError`、非法 date 抛 `HTTPException(422)`、point 保持文件顺序、summary 计数、响应结构（顶层键集、`screen=1280×720`、point 不含 `event`/`result`/`config`）、config 后缀归一化（`oas1_2026-09-01` → `oas1`）、`elapsed_ms` 取 int。
- 完整 Python 回归 `toolkit/python.exe -m unittest discover -s tests`：`236/236 OK`（旧 216 → 236）。
- `compileall` 覆盖 `module/device/control.py`、`module/server/behavior_stats.py`、`module/server/stats_router.py`、`tests/test_behavior_click_stats.py`：通过。
- 路由注册核对：`GET /stats/{script_name}/behavior/clicks` 已挂在 `stats_app`。
- `git diff --check`：通过（仅既有 docs 文件 LF/CRLF 提示）。
- 未启动 MuMu / 游戏 / 真实设备 / 真实 OCR；未起 FastAPI server（Reader 与 `_parse_target_date` 纯函数可直接单测）。

### 给 OASX 的前端契约

- **请求**：`GET /stats/<config>/behavior/clicks?date=YYYY-MM-DD`（`<config>` = 左侧选的 `oas1` / `oas2`；`date` 默认前端传今天）。
- **响应字段**：`config` / `date` / `screen{width,height}`（画布逻辑尺寸，一次）/ `summary{total,click_count,long_click_count,task_count,skipped_lines}` / `tasks[]`（当天有有效点击的任务，按首现顺序）/ `points[]`。
- **每个 point**：`x` `y`（int，1280×720 空间）、`task`、`action`（`"click"` | `"long_click"`，用于区分散点样式）、`target`（如 `I_FIRE`，tooltip 用）、`ts`（ISO8601 带时区）、`elapsed_ms`（int，可选）。不含 `event` / `result` / `config` / 原始 `extra`。
- **task 列表**：直接用响应里的 `tasks`，不需要再请求。
- **顺序**：`points` 已按 JSONL append 顺序 = 动作时间顺序，前端「显示路径」直接顺序连线即可，无需再排序。
- **无数据**：文件不存在 / 空 → `points: []`、`tasks: []`、`summary.total: 0`，HTTP 200（不是错误）。
- **筛选 / 连线 / tooltip / 热力图**：全部前端本地做，后端不分页、不聚合。

### 暂未实现

- OASX「点击分布」页面本体、任务下拉筛选 UI、散点图 CustomPainter、时间顺序连线、hover tooltip、热力图、实时刷新。
- swipe / drag 轨迹（`extra.x1/y1/x2/y2`）——见 ROADMAP T5-3。
- minitouch MOVE 逐点记录。

### Git

- 未 commit、未 push、未真机测试。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-01 - 修复 BehaviorStats Reader 对含下划线 config_name 的截断（correctness）

### 核对结论

- **config_name 允许 `_`（含多个 `_`）**。`ConfigManager.validate_config_name` 只拒：空 / `template`（`allow_template=False` 时）/ `.` / `/ \ : * ? " < > |` / 控制字符——**不禁 `_`**。`test_01`、`account_group_1`、`my_oas`、`oas_1` 均合法。
- 当前 `config/` 只有 `oas1` / `oas2` / `template`，无带 `_` 的——但这是「目前没人用」，规则层面允许，不能判定为安全（情况 B）。
- API 的 `{script_name}` 是**完整 config_name**（与 `/stats/{script_name}` 等一致，用户 `Script(config_name)` 用的名），**不是**日志文件名。
- BehaviorTrace 写入端（`module/behavior_trace.py` `_open_handle`）用 `f"{self._config_name}_{today}.jsonl"`，`self._config_name` 来自 `Script.__init__` 的**未归一化** `self.config_name`。所以 config `account_group_1` 的文件就是 `log/behavior/account_group_1_2026-09-01.jsonl`。
- `_normalize_script_name` 的原始职责：`logger.normalize_log_name` 明说「去掉运行时后缀」，是给 `<date>_<script>.txt` 人读日志名 / error 目录名解析设计的（`log_service.normalize_script_name` 12 处、`log_stats._normalize_script_name` 4 处均在此语境）。`behavior_stats.py` 是**唯一**把它用在 JSONL 文件名上的，而写入端根本没归一化。

### Bug

`module/server/behavior_stats.py` 的 `_normalize_script_name` 对 API 传入的完整 config_name 做 `name.split("_", 1)[0]`：

```
config = "account_group_1"（合法）
真实文件 = log/behavior/account_group_1_2026-09-01.jsonl
Reader:  _normalize_script_name -> "account"
         -> log/behavior/account_2026-09-01.jsonl   ← 错误
         -> 文件不存在 -> 返回空（用户看到「当天无点击」，实际有）
         -> 若存在 config "account" 且当天有日志 -> 读到别的 config 的点击数据
```

### 修改（最小）

- **`module/server/behavior_stats.py`**：
  - 删除 `_normalize_script_name`（按 `_` 截断）与 `_SAFE_CONFIG_RE`。
  - 新增 `_validated_config_name(script_name)`：调 `ConfigManager.validate_config_name(script_name, allow_template=False)`，**原样返回**（只去首尾空白，`_` 保留），`ConfigNameError` → `BehaviorStatsError(400)`。
  - `_behavior_file_path` 保留机械兜底：`resolve().relative_to(BEHAVIOR_LOG_ROOT)` + `path.name == 期望文件名`。
  - 响应 `config` 字段返回校验后的完整 config_name。
- **未动**：`log_stats._normalize_script_name`、`log_service.normalize_script_name`、`logger.normalize_log_name`——`behavior_stats.py` 的 helper 是本模块私有、非 import 复用，其它日志统计逻辑零影响。
- **未动**：BehaviorTrace 坐标记录、API response 结构、`Control.click/long_click`、`stats_router` 的路由与 `_parse_target_date`（router 层仍先跑 `validate_config_name` → 422）。

### 安全性（保持）

- config 校验：改用项目统一的 `ConfigManager.validate_config_name`（单一来源，拒 `.` / `/ \ : * ? " < > |` / 控制字符；允许 `_` `-`），比原 `_SAFE_CONFIG_RE` 少一套会漂移的规则。
- 路径穿越：`../oas1`、`..`、`/etc/passwd`、`a/../../oas1`、`..\..`、null 字符 → 均含 `.` 或路径字符或控制字符 → `validate_config_name` 抛 → `BehaviorStatsError(400)`，在读文件前拒绝；`_behavior_file_path` 的 `relative_to` + `path.name` 比对为二次兜底。
- 固定 log root：`BEHAVIOR_LOG_ROOT = <cwd>/log/behavior` 不变。

### 测试

- `tests/test_behavior_click_stats.py`：`24/24 OK`（旧 20 → 删 1 个测「按 `_` 归一化」的错误用例、新增 5 个）。
  - 新增：`test_underscore_config_name_reads_own_file`（`account_group_1` / `test_01` / `my_oas` / `oas_1` 读自己的文件）、`test_underscore_config_does_not_misread_truncated_file`（同时存在 `account_*.jsonl` 与 `account_group_1_*.jsonl`，请求 `account_group_1` 只读后者）、`test_prefix_segment_config_reads_its_own_file`（请求 `account` 读 `account_*.jsonl`，互不串）、`test_plain_config_unaffected`（`oas1`/`oas2` 正常）、`test_configmanager_accepts_underscore_names`（`validate_config_name` 接受带 `_` 的合法名）。
  - 调整：`test_illegal_config_is_rejected` 改用 `validate_config_name` 语义——`validate_config_name` 允许 `-x`（`-` 不在保留字符里），故从「应拒绝」列表移除 `-x`；新增 `a?b` / `a*b` / `a|b` / `a"b` / `template` 到应拒绝列表。`test_path_traversal_blocked` 的所有用例仍全部被拒。
- 完整回归 `toolkit/python.exe -m unittest discover -s tests`：`240/240 OK`（旧 236 → 240）。
- `compileall` 覆盖 `module/server/behavior_stats.py`、`tests/test_behavior_click_stats.py`：通过。
- import 无环核对：`stats_router` + `behavior_stats` 载入正常（`config_manager` 不 import `server` 内其它模块）。
- `git diff --check`：通过（仅既有 docs 文件 LF/CRLF 提示）。
- 未启动 MuMu / 游戏 / 真实设备 / 真实 OCR / FastAPI server。

### 生产影响

- 普通 `oas1` / `oas2`：`_normalize_script_name` 对无 `_` 的名本就是 no-op，行为不变。
- 未改 JSONL 格式、未改 API response 结构、未改 `Control.click/long_click` 点击记录、未新增后台线程。
- 不需要真机。
- 仅「config_name 含 `_`」这一场景从「读错文件 / 读空」变为「读对文件」。

### Git

- 未 commit、未 push、未真机测试。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-01 - 实现 FrameState Wait Layer（会话内称 T4-2）

### 目标

在 `FrameStateDetector`（`module/atom/frame_state.py`，纯帧差算法）之上加一层设备无关、可单测的「连续取帧 + 有限 timeout」有限等待，为后续 `list_find` / Kekkai 列表状态驱动迁移提供基础设施。**不接任何生产任务。**

### 新增

- **`module/base/frame_wait.py`**：
  - `wait_for_changed_and_stable(baseline, frame_provider, *, changed_threshold, stable_threshold, stable_frames, timeout, roi=None, pixel_threshold=DEFAULT_PIXEL_THRESHOLD, poll_interval=0.0, clock=time.monotonic, sleeper=time.sleep) -> FrameWaitResult`。
  - `FrameWaitResult`（`@dataclass(frozen=True)`）：`changed` / `stable` / `timed_out` / `last_difference` / `stable_count` / `frames_checked`（调 `frame_provider` 的次数，不含 baseline）/ `elapsed` / `success`（property = `changed and stable and not timed_out`）。
  - 实现：建一个内部 `FrameStateDetector`（透传三阈值 + `roi` + `pixel_threshold`），`detector.reset(baseline)` 立即校验 baseline 形状 + ROI；`start = clock()` 后循环：每轮先 `clock()-start` 判 `>= timeout` 则返回 `timed_out=True`（`last is None` 时给全 0 结果，否则带最后一次 detector 状态）；再 `frame_provider()` → `detector.update(frame)` → `frames_checked += 1`；`last.changed and last.stable` 则返回成功；`poll_interval > 0` 才 `sleeper(poll_interval)`。
  - `_MAX_POLLS = 1_000_000` 兜底：注入的 `clock` 不推进时抛 `RuntimeError`，不死循环。
  - 入参校验：`timeout` 非正数 / bool / 非数值 → `ValueError`；`poll_interval` 为负 → `ValueError`。阈值 / `stable_frames` / baseline / 帧 shape / ROI 的校验全部交给 `FrameStateDetector`（不写第二套）。

### 分工与边界（详见 DECISIONS D012）

- detector 纯帧差；本层做取帧 / 轮询 / 计时 / 超时；调用方决定 baseline / ROI / 阈值 / `stable_frames` / `timeout` / retry / recovery；`Control` 只做输入。
- `baseline` 由调用方传入（本层不自截，正确链路 `screenshot()→action()→wait(baseline=)`）。
- `frame_provider` / `clock` / `sleeper` 全部注入——无 Device / Timer 硬依赖。项目 `Timer` 内部用 `time.time()` 不可 mock，故本层单独走注入 `clock` 做确定性 timeout 测试。
- `poll_interval` 默认 `0.0`：生产 `frame_provider`（`device.screenshot`）已节流，不叠第二次固定 sleep。
- 超时返回结果、**不抛异常**；成功严格 `changed and stable`（`stable=True` 单独不算成功）；能区分「从未变化」（`changed=F, timed_out=T`）与「变化但没稳定」（`changed=T, stable=F, timed_out=T`）。
- `frame_provider` / detector 抛的异常原样透传，不伪装成 timeout。
- 不 import `module.behavior_trace`，不产生 `WAIT` / `TIMEOUT` / `TRANSITION` 事件（D004 不变）。
- 模块放 `module/base/` 而非 `module/atom/`：`atom` 层不负责设备轮询 / 超时（D010），`module/base/` 已是控制流基础设施所在（`retry.py`）；`base → atom` 单向 import，`module/base/__init__.py` 只 import `.utils` / `.grids`，无环。

### 测试

- `tests/test_frame_wait.py`：`20/20 OK`（`WaitForChangedAndStableTest`）。
  - 成功：变化后稳定→`success`（`frames_checked` / `stable_count` / `last_difference` 精确）、变化后回基线→`changed` 锁存仍 `success`（`last_difference=0`）、`stable_count` 中途被变化重置后重新累计→`success`、`frames_checked` 不含 baseline。
  - 超时：从未变化→`timed_out` 且 `changed=F`（即使 detector `stable=T`）、持续变化→`timed_out` 且 `stable=F` 且 `stable_count=0`、注入 `_clock(step)` 的 timeout 边界（`elapsed` / `frames_checked` 确定，无真实 sleep）。
  - 异常透传：`frame_provider` 第 3 次抛 `RuntimeError` → 透传；帧 shape 与 baseline 不一致 → `ValueError`；非法 ROI 在 `reset(baseline)` 阶段就抛。
  - 校验分工：`timeout ∈ {0, -1, -0.5, "x", None, True, False}` 与负 `poll_interval` 由本层抛 `ValueError`；`changed_threshold<0` / `stable_threshold<0` / `stable_frames=0` / `baseline=None` 由 detector 抛。
  - 其它：`poll_interval>0` 调注入 `sleeper` 且默认 0 不 sleep、`stable` 单独为 True 非 `success`、不推进 clock（`lambda: 0.0`）触发 `_MAX_POLLS`（测试内临时改小）抛 `RuntimeError`、ROI 只圈定等待范围（ROI 内变化→成功，只 ROI 外变化→超时）、`FrameWaitResult` 冻结。
- `tests/test_frame_state.py` 回归：`25/25 OK`（未改该文件）。
- `compileall` 覆盖 `module/base/frame_wait.py`、`tests/test_frame_wait.py`：通过。
- 完整 Python 回归 `toolkit/python.exe -m unittest discover -s tests`：`260/260 OK`（旧 240 → 260）。
- `git diff --check`：通过（仅既有 `docs/*.md` LF/CRLF 提示）。
- 生产消费者核对：`grep -rn "frame_wait\|wait_for_changed_and_stable\|FrameWaitResult" module/ tasks/ script.py` 除 `module/base/frame_wait.py` 自身外**零命中**。
- 未启动 MuMu / 游戏 / 真实设备 / 真实 OCR / FastAPI server（`frame_provider` / `clock` 注入使全部路径可纯静态验证）。

### ROADMAP 编号

- 会话内本轮称「T4-2」。ROADMAP 原 P1「T4-2 `harvest_card` 状态驱动」顺延为 **T4-4**（ARCHITECTURE §5 扩展点表与「需要真机验证」列表同步改引用）；原「T4-3 Wait / Retry 策略层」编号不变。

### 生产影响

- 无。纯新增文件，零生产消费者，未改任何现有模块。
- 真实列表 ROI / 阈值 / `stable_frames` / 轮询 interval / timeout 的确定，以及接上 `device.screenshot` 并验证效果，仍是 Level C（待真机），记入 `docs/ROADMAP.md`。

### Git

- 未 commit、未 push、未真机测试。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-01 - BaseTask.list_find 迁移前静态收口 + characterization（会话内称 T4-3 / ROADMAP T5-2 前半）

### 目标

把 `list_find` 翻页后的固定 `sleep(random.uniform(0.8, 1.3))` 迁移到 FrameState 等待层**之前**，在**完全不改 `list_find` 生产行为**的前提下：逐行审查其真实语义、清点全部生产调用方、补 characterization 测试、判断是否现在抽「滑动后等待」seam。

### `list_find` 真实控制流（`tasks/base_task.py` 696-733，逐行核实）

```
if not target: return False              # 0 截图
for _ in range(max_swipe):               # 有界，默认 10；navbar / Dokan 传 3
    self.screenshot()                    # 首轮不跳过；device.screenshot 自带 Timer(0.1) 节流
    if target.is_image:
        result = target.image_appear(self.device.image, name, frame_id=self.device.image_frame_id)
        swipe_down = True                 # image 模式恒 True
    elif target.is_ocr:
        result = target.ocr_appear(self.device.image, name)
        swipe_down = result is not None and isinstance(result, int) and result > 0
        swipe_distance_ratio = 1
    if isinstance(result, tuple):         # 命中
        appear = True; break
    x1,y1,x2,y2 = target.swipe_pos(number=1, after=swipe_down)   # ocr: number=1
                  或 target.swipe_pos(after=swipe_down)          # image: 默认 number=2
    self.device.swipe(p1=(x1,y1), p2=(x2,y2))
    sleep(random.uniform(0.8, 1.3))       # 翻页后唯一等待，普通 random，注释「待优化」
return result if appear else False        # 命中原样返回识别元组，否则 False
```

- **等待方式**：翻页后只有 `sleep(random.uniform(0.8, 1.3))`（`from time import sleep` + 模块级 `import random`）。下一轮截图靠 `device.screenshot` 的 `_screenshot_interval = Timer(0.1)` 节流，被 0.8~1.3s 完全覆盖。
- **无界循环**：不可能。`for _ in range(max_swipe)` 硬上限。**不读 `RuleList.is_bottom`**，无到底部检测，纯靠 `max_swipe` 收敛。本轮未加 retry count / bottom detection。
- **异常**：函数内无任何 try/except。screenshot / finder / swipe / sleep / random 抛出均直接透传。
- **已知瑕疵（本轮不修，characterization 照实锁）**：① 末轮未命中仍 swipe + sleep；② `RuleList.ocr_appear` 无 OCR 结果时 `return 0, 0`（tuple）被当命中坐标 `(0,0)`；③ `list_appear_click` 的 `isinstance(appear, tuple) and interval`——`interval` 空时命中也返回 False 不点击（真实调用方都传 interval）。

### 生产调用方（全仓 `tasks/` `module/` `script.py` 确认）

`list_find` 直接调用方 8 处：

| 调用方 | 用途 | RuleList | 特殊参数 | 外层等待 | 未来建议 |
|---|---|---|---|---|---|
| `Orochi.check_layer` | 选层（OCR 文字列表） | `L_LAYER_LIST` | 默认 | 命中后 `while 1: screenshot; if appear(I_CHECK_TEAM)` | 翻页后 → FrameState；外层保留 semantic wait |
| `FallenSun.check_layer` | 同上 | `L_LAYER_LIST` | 默认 | 同型 | 同上 |
| `EvoZone.check_layer` | 同上 | `L_LAYER_LIST` | 默认 | 同型 | 同上 |
| `EternitySea.check_layer` | 同上 | `L_LAYER_LIST` | 默认 | 同型 | 同上 |
| `GeneralRoom.check_zones` | 选副本（OCR 列表） | `L_TEAM_LIST` | 默认 | 命中后 `Timer(1.1)` + `while 1: ocr_appear` | 翻页后 → FrameState；外层 OCR 循环保留 |
| `navbar._enter_special/_friendship/_medal/_charisma` | 商城导航条（图片列表） | `L_RM_NAVBAR` | `max_swipe=3` | `click_and_check`（`Timer(1.2)` + `appear(check_rule)`） | 翻页后 → FrameState；外层保留 |
| `navbar._enter_honor` | 同上，多目标 | `L_RM_NAVBAR` | `max_swipe=3`, `name=['honor','duel']`（图片 list-name 分支） | 同上 | 同上 |

包装入口 2 个（内部调 `list_find`）：`list_appear_click` ← `GameUi/navigator.py:341`（`interval=interval or 0.8`，恒真）、`Dokan/script_task.py:521`（`interval=3, max_swipe=3`）。

全部靠返回值 `tuple`（命中坐标）/ `False` 判断，无一依赖固定 swipe 次数或副作用。

**KekkaiActivation / KekkaiUtilize 不是 `list_find` 消费者**：各有 `check_card_num` + `perform_swipe_action`，直接 `self.device.swipe_adb(p1, p2, duration=...)`（自采样 duration，见 §4.14 / D003），是「列表内 swipe + 等待」的**平行实现**，绕过 `list_find` 与 `Control.swipe`。迁移 `list_find` 不自动覆盖它们。

### 等待迁移矩阵

| 位置 | 当前等待 | 目的 | 未来类型 |
|---|---|---|---|
| `list_find` swipe 后 | `sleep(random.uniform(0.8, 1.3))` | 等列表滚动停稳 | **视觉：frame changed + stable** |
| `check_layer` 外层 `while 1` | `screenshot` + `appear(I_CHECK_TEAM)` | 等「队伍界面」出现 | 语义：`wait_until_appear` |
| `check_zones` 外层 `while 1` | `Timer(1.1)` + `ocr_appear` | 等副本名 OCR 命中 | 语义：OCR 命中循环 |
| `navbar.click_and_check` | `Timer(1.2)` + `appear(check_rule)` | 等目标页签选中标志 | 语义：`appear` 循环 |
| `list_appear_click`（navigator/Dokan） | `interval` 的 `Timer` 门控 | 控制重试频率 | 语义 / 频率门控，保留 |

### 是否抽 seam：否

结论 + 理由固化到 `docs/DECISIONS.md` D013。要点：
- 未来正确链路要求「动作前 baseline 显式传入」（D012）。`list_find` 中滑动前可用帧是 `self.device.image`（为识别而截）。
- swipe 之后调用的 `_wait_after_list_swipe()`：要么签名无 baseline（未来不可用），要么隐式读 `self.device.image`（把 baseline 藏成全局 + 依赖「swipe 后 device.image 未刷新」这条未经真机验证的不变量）——都是 D012 要避免的错误 seam。
- 真实 ROI / 阈值 / `stable_frames` / timeout 全是 Level C，seam 参数签名此刻无法定稿。
- image/ocr 模式 `swipe_pos` 分叉 + `(0,0)` 命中瑕疵会与重构交互，提前冻结边界过早。
- 纯转发私有方法改调用图、零收益，违反「不做无关重构」。
- 收口产物 = characterization 测试 + D013 + `docs/AI_CONTEXT.md` §4.19。seam 留到真机窗口和真实参数一起定。

### 测试

- **新增 `tests/test_list_find.py`（22 用例）**：
  - `ListFindCharacterizationTest`（19）：第一屏命中（image / ocr）0 swipe / 0 sleep 且原样返回元组；翻页 1 次 / 2 次后命中的完整 event 序列（`screenshot → find → swipe → sleep → screenshot`，锁死 find 先于 swipe、sleep 在 swipe 后、下轮 screenshot 在 sleep 后）；未命中耗尽 `max_swipe` → `False` 且末轮仍 swipe+sleep；`max_swipe<=0` → 0 截图 `False`；`target` falsy → 0 截图 `False`；ocr 结果负 / 正 / 0 分别 `swipe_pos(1, False/True/False)`；ocr 空结果 `(0,0)` 被当命中；`swipe_pos` 不触发额外截图；无 bottom detection；screenshot / finder / swipe 异常直接透传（swipe 异常时 sleep 未发生）；翻页等待恒为 `sleep(random.uniform(0.8, 1.3))`。
  - `ListAppearClickCharacterizationTest`（3）：命中 + 传 interval → `device.click(x,y)` 返回 True；命中但 `interval=None` → False 不点击；未命中 → False。
  - mock 方式：`BaseTask.__new__` + `SimpleNamespace` device + patch `tasks.base_task.sleep` / `tasks.base_task.random`；`_FakeList` 替身 RuleList 按脚本返回识别结果。
- `tests/test_frame_wait.py`：`20/20 OK`（未改）。
- `tests/test_frame_state.py`：`25/25 OK`（未改）。
- `compileall` 覆盖 `tests/test_list_find.py`、`tasks/base_task.py`：通过。
- 完整回归 `toolkit/python.exe -m unittest discover -s tests`：`282/282 OK`（旧 260 → 282）。
- `git diff --check`：通过（仅既有 `docs/*.md` LF/CRLF 提示）。
- `tasks/base_task.py` 的 diff 不含 `list_find` / `list_appear_click` / `swipe_pos` / `random.uniform` 任何行——`list_find` 本轮零改动。
- `grep -rn "frame_wait\|wait_for_changed_and_stable\|FrameWaitResult\|FrameStateDetector\|frame_state" module/ tasks/ script.py` 除组件自身外零命中——`wait_for_changed_and_stable` production consumers 仍为 0。
- 未启动 MuMu / 游戏 / 真实设备 / 真实 OCR / FastAPI / OASX / 生产任务。

### 生产影响

- 无。`list_find` / `list_appear_click` 源码零改动；截图次数 / swipe 次数 / swipe 参数 / delay 位置与范围 / finder 调用顺序 / 返回值 / 异常传播 / 全部调用方行为均不变。
- 仅新增 `tests/test_list_find.py` 一个测试文件 + 6 份交接文档更新。
- FrameState 迁移（T5-2 后半）仍是 Level C（待真机）。

### Git

- 未 commit、未 push、未真机测试。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-01 - 点击空间随机 / 偏移机制全仓审查（结论落地）

### 内容

对「目标原始坐标 → 最终提交给 `Control.click` / `long_click` 的坐标」之间所有位置变化实现做静态全仓审查（**未改任何代码**）。完整报告见当轮对话；本轮把长期结论落地为 `docs/AI_CONTEXT.md` §4.20 / §8.2 补记 与 `docs/DECISIONS.md` D014。

### 核心结论

- 点击落点 = Rule 对象 ROI `(x,y,w,h)` 内**一次独立均匀随机**（`random_point_in_roi`），`x`/`y` 各自 `SystemRandom.randrange` 独立。`RuleImage/RuleClick/RuleOcr/RuleGif.coord` + `RuleLongClick`（继承）同一套；`long_click` 与 `click` 坐标生成相同。
- **空间随机整条链路只一层**（`Rule.coord()`）。`BaseTask` 透传、`Control.click/long_click` 只 `ensure_int`、默认 `click_minitouch` 无 `.move()` / 无 ±px（只随机压力 / dwell）、`CommandBuilder.convert` 是旋转 + 分辨率缩放。**全仓 0 处默认 double jitter。**
- 中心偏置（`random_center_point_in_roi`，Bates n=3）**只用于 `RuleSwipe` 端点，点击 0 处**；是分布形状不是「习惯中心」。
- **全程无状态**：无 preferred center / per-target / per-session 热点、无 EMA / AR(1) / 历史。
- 固定坐标 / 识别框几何中心点击几十处（`random_click()` 安全区、Chess / Secret / QuickLoadout / WeeklyTrifles / navigator fallback / GeneralBattle 绿名 / `list_find` 命中等）。
- 任务私有随机空间偏移仅 1 处：`tasks/SixRealms/common.py`（`front_center()` + `random.randint` 左移 + 纵抖，普通 `random`）。
- 一改影响面最大：`random_point_in_roi`、`RuleImage.coord` / `RuleClick.coord`（≈2064 `RuleImage` + 291 `RuleClick` + 292 `RuleOcr` asset；491 `appear_then_click` + 223 `self.click`）。
- 只有 Detection ROI（`roi_back`）+ Click ROI（`roi_front` ≈ 模板框），**没有系统化 Safe Click ROI**。
- BehaviorTrace 缺 `page` / `ROI` 字段、`target` 跨页同名混叠，不足以直接学 per-target preferred center；存量不可回填。

### 记录（未修）5 个 latent bug

`Control.multi_click` 传参错误 / `control_method=='scrcpy'` 时 click 静默回退 `click_adb`（scrcpy 的 ±2px 抖动走不到）/ `click_nemu_ipc` 相对 `Control` 不可达 / `RuleClick.move()` `x += x` 翻倍 bug / `RuleList.ocr_appear` 无结果返回 `(0,0)` 被当命中。

### 文档同步

AI_CONTEXT §4.20（审查结论）+ §8.2（3 处非统一空间随机源补记）；DECISIONS D014（点击空间模型演进长期边界）；ROADMAP「已完成」+ T7-1；ARCHITECTURE §5 扩展点行。

### Git

- 未 commit、未 push、未真机测试。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-01 - 人工点击采样器 ManualClickRecorder v1

### 目标

为「统计用户真实 preferred center / spread」提供人工物理鼠标点击采集工具。**只观察、不发送任何输入**，与自动 BehaviorTrace 完全分离。为后续 T7-1 点击空间模型 v2 提供人工习惯数据。

### 新增

- **`dev_tools/manual_click_recorder.py`**（开发 / 校准工具，不进生产链）：
  - 运行 `toolkit/python.exe dev_tools/manual_click_recorder.py --config oas1 [--hwnd N] [--scene S --target T --roi x,y,w,h] [--include-injected] [--every N] [--force]`。
  - **窗口定位**：`--hwnd`（直接当游戏画面窗口）> 配了 `script.device.handle` 时复用 `module/device/handle.py` `Handle.screenshot_handle_num` > 兜底按窗口标题扫 MuMu 顶层 + 找 `MuMuPlayer`/`NemuPlayer`/`MuMuNxDevice` 游戏 child（多开且未配 handle 会警告改用 `--hwnd`）。启动时 `viewport_sanity`（窗口物理尺寸 ≈ 1280×720，复用 `Handle.screenshot_size` 判定思路）做闸门，选错窗口拒绝启动（`--force` 可跳过）。
  - **坐标转换**：本进程不设 DPI awareness（与 OAS 一致，DPI-unaware）；鼠标钩子 `MSLLHOOKSTRUCT.pt` 与 `GetWindowRect` 同一虚拟化空间，换算是**纯比例** `client/win*1280(720)`，**不乘 `window_scale_rate`**（仅诊断展示 / 存档）。每次点击前重新 `GetWindowRect`，窗口移动 / resize 后仍正确。
  - **只采目标视口内真实左键**：`WH_MOUSE_LL` 全局钩子；`flags & LLMHF_INJECTED` 默认跳过；`inside_viewport=False` 不写；回调只读、始终 `CallNextHookEx` 放行、异常吞在回调内，绝不影响用户鼠标。
  - **输出**：`log/manual_click/<config>_<日期>.jsonl`（与 `log/behavior/` 分开），行缓冲，跨天轮转。字段：`ts / source="manual" / config / screen_x,y / client_x,y / x,y(1280×720 逻辑) / window_width,height / logical_width,height / inside_viewport / injected`，可选 `scene / target / roi / u / v / inside_roi`（`u=(x-roix)/roiw`、`v` 同理，**不 clamp**）。config 名 `ConfigManager.validate_config_name(allow_template=False)` 校验并原样保留（不按 `_` 截断），路径 `relative_to` 兜底防穿越。
  - **生命周期**：Ctrl+C / 异常 / 目标窗口消失 → `finally` 一定 `UnhookWindowsHookEx` + 关文件 + 打印摘要（样本数、ROI 内 / 外、Welford `mean_u/v`、`std_u/v`）。写文件失败打印错误并停止（前台工具不静默吞）。
  - **v1 不做**：不截图 / OCR / 模板匹配 / 猜 page / target、不热力图、不 ClickProfileManager、不学习、不改任何自动点击参数。`scene/target/roi` 全人工传入。
  - 纯函数（坐标换算 / u·v / 统计 / JSONL / config 安全）与 Win32 胶水（钩子 / 窗口定位）分离，前者可完整单测。
  - 无新增第三方依赖（pywin32 已是硬依赖；钩子用 `ctypes` WH_MOUSE_LL）。

### 测试

- **新增 `tests/test_manual_click_recorder.py`（31 用例，纯函数，不装真实钩子）**：`screen_to_logical`（1:1 / 缩放 / 窗口移动不变 / resize 比例一致 / 视口外不 clamp / 非法几何抛错）、`relative_uv`（中心 / 已知分数 / 外围不 clamp）、`parse_roi`（合法 + 8 类非法）、`is_injected_event`、`match_mumu_toplevel_title`、`viewport_sanity`（1280×720 与 1024×576@1.25 通过、错窗口 / 退化拒绝）、`build_sample`（schema / 逻辑坐标 / roi u·v / JSON 可序列化）、`ManualClickStats`（无 ROI 只计数、`mean/std` 与 `statistics.mean/pstdev` 一致、ROI 外不进 u/v）、`ManualClickWriter`（append 不 truncate / reopen / 跨天两文件 / 含 `_` config 名 / `../evil` 拒绝）、`resolve_config_name`（合法保留 / `../` `.` `/` `\` 空 `template` 控制字符拒绝）。
- `compileall` 覆盖 `dev_tools/manual_click_recorder.py`、`tests/test_manual_click_recorder.py`：通过。
- CLI 冒烟：`--help`、非法 `--roi`（exit 2）、非法 config（exit 2）、无效 `--hwnd`（exit 3）均按预期。
- 完整回归 `toolkit/python.exe -m unittest discover -s tests`：`313/313 OK`（旧 282 → 313）。
- `git diff --check`：通过（仅既有 `docs/*.md` LF/CRLF 提示）。
- 未启动 MuMu / 游戏 / OAS / OCR / OASX；未自行装真实钩子；未移动 / 点击鼠标测试。

### 人工验收清单

1. 启动 OAS / MuMu（1280×720）；2. 暂停该 config 的自动任务（本工具不改 scheduler）；3. `toolkit/python.exe dev_tools/manual_click_recorder.py --config oas1`（多开或未配 `device.handle` 时加 `--hwnd <OAS 日志里的 Screenshot handle num>`）；4. 把 MuMu 移到屏幕不同位置；5. 点画面左上 / 中心 / 右下，看终端 `logical=` 是否 ≈ 期望的 1280×720 坐标；6. resize MuMu 再重复；7. 加 `--roi 790,470,130,90` 连点 30~50 次；8. Ctrl+C；9. 查 `log/manual_click/oas1_<日期>.jsonl` 与 preferred-center 摘要（`u/v` 均值 / σ）。

### 生产影响

- 无。纯新增 `dev_tools/manual_click_recorder.py` + `tests/test_manual_click_recorder.py`，未改动任何现有文件。`RuleClick` / `RuleImage.coord` / `random_point_in_roi` / `Control` / minitouch / `BehaviorTrace` / 任何 Task / 自动点击坐标 / 自动点击时序 **均未改**。

### Git

- 未 commit、未 push、未真机测试。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-01 - 人工点击日志 burst collapse + 重新统计（分析器 + 首次真实样本分析）

### 目标

把 `ManualClickRecorder` 采到的原始人工点击日志清洗成更接近「独立鼠标落点」的数据，重新算 preferred center / spread。**离线只读分析**，不改任何自动点击算法。

### 新增（代码）

- **`dev_tools/manual_click_analyze.py`**：
  - `collapse_bursts(rows, *, time_threshold_ms, distance_threshold_px)`——链式合并：相邻两点（**current vs previous**，不是 vs 首点）满足 `dt ≤ 阈值` 且 `distance ≤ 阈值` 且标签兼容 → 同一 burst。一串每步在阈值内的小幅漂移整体算一个 burst。
  - `burst_record`：代表坐标默认取 burst **第一个点**（用户移动到位后首次按下，后续连点通常没重新瞄准），另算 `centroid` 对照；带 `burst_id/start_ts/end_ts/click_count/duration_ms/x/y/centroid_x/y/max_step_distance/source` + 继承 `config/scene/target/roi/u/v`。
  - `landing_stats`：count、mean、std(pstdev)、median、`p05/p25/p75/p95`(x,y)、`normalized_mean_x/y`、径向分位 `r50/r75/r90/r95`，`--roi` 时另出 u/v 系列。
  - 敏感性分析固定跑 `300/3`、`500/5`、`800/5`、`500/8`（ms/px）；参考分析参数 **`500ms/5px`**（仅本轮参考，非长期标准）。
  - 粗分区 `--y-split`（默认 330，`-1` 关闭）：水平线粗分上 / 下两区，**分析用非页面识别**。
  - 输出 `log/manual_click_analysis/<stem>_dedup.jsonl` + `<stem>_summary.json`；**原始 JSONL 永不修改**。
  - 不拟合 Gaussian / Student-t / AR(1) / EMA，不建 ClickSampler / ClickProfileManager；无新增依赖（无 matplotlib → 只出统计不出散点 PNG）。
- **`tests/test_manual_click_analyze.py`**（22 用例）：burst 链式 / 时间距离标签断开 / 代表点 + centroid / 统计量与 `statistics` 一致 / 分位数单调 / 归一化 1280×720 / 径向分位有序 / ROI u/v / 直方图 / region split / `load_jsonl` 跳坏行不改原文件 / `analyze` 只写派生文件 + collapse_ratio + 敏感性含 4 组。

### 对当前真实样本的分析（实验结果 / 当前用户样本，**不是长期 ADR**）

文件 `log/manual_click/yys1_2026-09-01.jsonl`（config `yys1`，772 条，26 分钟，无 `scene/target/roi` 标签，`window_scale_rate=1.0`）。

**1. 原始 click 数**：772。前 ~4-6 条是屏幕四角的校准 / 测试点击（`(765,8)`/`(458,264)`/`(281,652)`/`(1252,439)`…），非游戏操作；按「不删真实样本」保留在 ALL 统计里，占比 <1.5%。

**2. `500ms/5px` 去重后独立落点**：**444**（collapse 42.5%）。

**3. 重复连点占比**：772→444，即 **42.5% 的 raw click 是连点冗余**；`click_count` 直方图 `{1:274, 2:41, 3:100, 4-5:29, 6+:0}`——三连点是主要多连点形态。170 个多连点 burst 里共含 **498 条 raw click（占全部 772 的 64.5%）**。多连点 burst 时长 median 312ms / p90 482ms，其间最大鼠标移动 median 0px / p90 1px / max 5px——连点期间鼠标基本静止。

**4. 阈值敏感性（非常稳定）**：`300/3`→457（40.8%）、`500/5`→444（42.5%）、`800/5`→438（43.3%）、`500/8`→442（42.8%）；整体归一化中心在 `(0.626~0.631, 0.542~0.548)` 之间几乎不动，std 变化 <1%。→ **热点对阈值稳健，可信**。

**5. raw vs dedup（全部落点，屏幕归一化）**：
- raw：center `(0.675, 0.597)`，std px `(143, 107)`。
- dedup（首点）：center `(0.628, 0.544)`，std px `(157, 123)`。centroid 代表点结果与首点几乎一致（差 <0.1px）。
- **dedup 的 std 比 raw 更大**（x +10%，y +15%）——与「连点压小方差」方向一致，但机制是**加权偏差**：raw 过度加权高频连点所在的右下大区，使中心更深地落进该区、离散度看起来更小；去重后未受连点影响的上部按钮簇获得应有权重，中心上移、离散度回升。

**6. 粗分区（y_cut=330，规则 = 明显空带 + 下述时间周期证据）** ——⚠️ **本节页面标签已被下方同日期「人工点击 Cluster 分类修正」条目推翻，只保留原始数字供追溯，页面归属请以新条目为准**：
- **上部小簇（当时误标≈进攻按钮，高置信度可分）**：n=112，**去重前 == 去重后（此区 0 个 burst，每次按钮都是单击）**。center 屏幕归一化 `(0.503, 0.286)`，std px `(48, 39)`，x 主体 588-700 / y 主体 176-237，径向 `r50/r90/r95 = 0.026/0.059/0.116`（归一化）。**修正：这其实是 `C_AREA_1`（寮突破区域 1 目标卡片）静态资产 ROI，不是进攻按钮。**
- **下部大区（当时误标 Large Area ≈ 胜利继续 + 奖励结算，合并统计）**：raw n=660 → dedup n=332（**该区独占全部 170 个多连点 burst，50% collapse**）。center raw `(0.704, 0.650)` → dedup `(0.670, 0.631)`，dedup std px `(144, 63)`，径向 `r50/r90/r95 = 0.133/0.187/0.208`。**修正：这个二分「下部大区」实际混入了真正的进攻按钮簇（y≈340-415），是被真实进攻按钮污染后的错误合并结果，不是干净的 Large Area。**
- 时间周期证据：去重序列呈清晰的 `U L L L U L L L …` 循环（106 个 `L→U`、107 个 `U→L` 转换 ≈ 112 轮），每轮 1 次上部簇 + 3~4 次下部簇点击，方向性判断（一簇对应「区域卡片」、另一簇是「战斗后续操作」）成立，**但当时用 y=330 一刀切把「进攻按钮」和「Large Area」的界线画错了**（真进攻按钮和 Large Area 都在 y≥330，被同一刀切进了同一份「下部大区」）。
- **不能可靠拆分**：页 1（突破列表选卡）无独立簇；页 3（胜利继续）与页 4（奖励结算）在下部大区严重重叠且被连点糊在一起——这一条结论**仍然成立**，按要求合并为 Large Area，不硬分类。

**7. 对旧粗估的核对** ——⚠️ **以下两条结论已被下方新条目推翻，保留仅供追溯**：
- ~~旧 `Button ≈ (0.66, 0.52)`：真正的进攻按钮簇在屏幕归一化 `(0.50, 0.29)`，**不成立**~~ ——**错误**：`(0.50, 0.29)` 是 `C_AREA_1` 目标卡片，不是进攻按钮；真进攻按钮簇见下方新条目。
- ~~旧 `Large Area ≈ (0.75, 0.71)`：方向成立，量级偏大；**基本成立但需修正 → dedup `(0.67, 0.63)`**~~ ——**错误**：`(0.67, 0.63)` 是被进攻按钮簇污染后的数字；剔除进攻按钮后的真实 Large Area 见下方新条目（更接近旧估计原值）。

### 对后续 ClickSampler 的数据结论（不写生产代码）——⚠️ 已被下方新条目推翻

- ~~**进攻按钮**：建议热点从旧估计修正到屏幕归一化 **`(0.50, 0.29)`**~~ ——**错误**，那是 `C_AREA_1` 目标卡片，不是进攻按钮。
- ~~**Large Area（胜利继续 + 奖励结算合并）**：建议热点 **`(0.67, 0.63)`**~~ ——**错误**，被进攻按钮簇污染，见下方新条目的修正值。
- 任何 preferred center 必须基于 **burst-collapse 后的独立落点**、且报告阈值敏感性——直接用 raw click 会因连点加权偏差同时移动中心并压小方差。**此条结论不受本次修正影响，仍然成立。**

### 验证

- `tests/test_manual_click_analyze.py`：`22/22 OK`。
- `compileall` 覆盖 `dev_tools/manual_click_analyze.py`、`tests/test_manual_click_analyze.py`：通过。
- 完整回归 `toolkit/python.exe -m unittest discover -s tests`：`335/335 OK`（旧 313 → 335）。
- `git diff --check`：通过（仅既有 `docs/*.md` LF/CRLF 提示）。
- 原始日志完整性：`log/manual_click/yys1_2026-09-01.jsonl` 与用户自己的备份副本 md5 一致，工具全程只读。
- `log/` 已被 `.gitignore` 忽略，派生分析文件与原始日志都不进版本控制。
- 未启动 MuMu / 游戏 / OAS / OCR / 设备。

### 生产影响

- 无。纯新增 `dev_tools/manual_click_analyze.py` + `tests/test_manual_click_analyze.py`。`RuleClick` / `RuleImage` / `RuleOcr` / `random_point_in_roi` / `Control` / minitouch / `BehaviorTrace` / `ManualClickRecorder` 采样语义 / 任何 Task **均未改**。

### Git

- 未 commit、未 push、未真机测试。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-01 - 人工点击 Cluster 分类修正（推翻上一条目的页面标签）

### 问题

上一条目用固定 `y_split=330` 把落点二分为「上部小簇=进攻按钮」「下部大区=Large Area」。核对用户提供的真实操作流程（突破列表→点击目标卡片→进攻弹窗→进攻按钮→战斗→胜利/奖励连续点击→返回列表）与真实资产源码后确认：**这是错误分类**。真实进攻按钮的 y（≈340-415）落在“下部”，被和 Large Area 糊在一起；被误标成“进攻按钮”的上部小簇实际是目标卡片。

### 分析方法（新增可复用能力）

`dev_tools/manual_click_analyze.py` 新增三个纯函数（`tests/test_manual_click_analyze.py` 补 10 用例，回归 22→32）：

- `detect_calibration_prefix(rows, *, edge_margin_px=40, min_gap_s=8.0)`：识别日志开头「窗口映射校准点击」前缀——从第一条起找相邻间隔首次 `>= min_gap_s` 的位置 k，若 `rows[:k]` 里有屏幕边缘点则判定为校准前缀返回 k，否则返回 0（不强行剔除）。对 `yys1_2026-09-01.jsonl` 判定为 **6**（首个 10.72s 大间隔前的 6 条，含屏幕四角/边缘点），与人工目视一致。**只从「行为统计」口径剔除，ALL / raw 统计与原始 JSONL 不受影响。**
- `kmeans_clusters(points, *, seeds, max_iters=50)`：确定性 k-means（固定种子、无随机初始化），返回簇标签 + 质心；可信度看簇内距离分布（`median`/`p90` 远小于 `max` 才可信），不把种子当最终边界。
- `transition_counts(labels)`：按时间顺序统计相邻簇标签转移次数，用于验证「循环」假设。
- `region_split` 的输出改为纯几何命名 `region_upper`/`region_lower`，**去掉了错误的页面语义 note**（不再声称某一刀对应哪个页面）；`analyze()` 新增 `cluster_seeds`/`cluster_labels`/`exclude_calibration` 参数与 CLI `--three-cluster --seed-a --seed-b --seed-c --cluster-labels --no-exclude-calibration`。

### 三簇验证结果（`500ms/5px` 参考阈值，种子来自对本会话数据的探索性观察）

behavior-only（剔除 6 条校准前缀后）dedup landings = 438，k-means(3) 收敛到：

| 簇 | n (dedup/raw) | 屏幕归一化中心 | std (px) | 簇内距离 median/p90 |
|---|---|---|---|---|
| **cluster_A** | 107 / 107（0 burst，全单击） | `(0.501, 0.285)` | (34, 32) | 24.6 / 52.8 |
| **cluster_B** | 110 / 116（轻度 collapse） | `(0.527, 0.545)` | (40, 39) | 21.8 / 47.8 |
| **cluster_C** | 221 / 543（59.3% collapse，独占 170 个多连点 burst） | `(0.742, 0.672)` | (56, 50) | 62.4 / 109.8 |

**时间序列转移**（106 个循环）：`A→B 103`、`B→C 95`、`C→A 95`、`C→C 123`（同簇内连续多次，即 Large Area 内的连点）——清晰对应 `C(返回列表)→A(点目标卡片)→B(进攻按钮)→C(战斗结算连点)→…`，与用户描述的真实流程完全吻合，**验证了三簇假设成立**。

**阈值敏感性**：A、B 在 `300/3`、`500/5`、`800/5`、`500/8` 四组阈值下 **n 与归一化中心完全不变**（该二簇几乎无 burst）；C 在 215~234 之间波动（<9%），归一化中心稳定在 `(0.7417~0.7426, 0.6714~0.672)`。→ **三簇结果对阈值稳健**。

### 页面语义 + 资产核对（回到源码）

- **Cluster A = 目标：`tasks/RyouToppa/assets.py` 的 `C_AREA_1 = RuleClick(roi_front=(533,162,177,74))`**（寮突破 8 宫格的区域 1 卡片，静态、不随匹配更新）。Cluster A 落点 **91.6%（98/107）落在该 ROI 内**，视为确认。ROI 相对 `mean_u=0.610, mean_v=0.584, std_u=0.194, std_v=0.428, median_u=0.616, median_v=0.622, p05/p95 u=0.329/0.879, p05/p95 v=0.274/0.960` —— **这是本轮唯一拿到可靠 ROI-relative preferred center 的簇**，作为 Button（更准确地说是「目标卡片」）候选值。
  - ⚠️ 2026-09-02 修正：这行的 ROI 相对统计混入了 ROI 外的点（`landing_stats` 当时对全部 107 条一起换算）。按只用 inside 子集的正确口径应为 **inside n=101 / outside 6，`mean_u=0.6271, mean_v=0.6218, std_u=0.1548, std_v=0.2074`**（屏幕 std 从 (34,32) 收紧到 (27,15)）。「98/107、9 个外点」也是当时用半开区间手工数的；工具实际用闭区间 `[0,1]`，为 101/6。详见 2026-09-02「Cluster A ROI 统计口径修正 + Runtime ROI Probe v1」条目。
- **Cluster B = 真正的进攻按钮 / 进攻弹窗**：源码定位到 `tasks/RyouToppa/script_task.py:attack_area`（`self.appear_then_click(RealmRaidAssets.I_FIRE, ...)`），资产为 `RealmRaidAssets.I_FIRE = RuleImage(roi_front=(982,494,136,63), roi_back=(140,129,1024,584), ...)`。**但 `roi_front` 是 `match()` 动态更新的，其静态默认值 0 命中 Cluster B（0/110 落在该默认框内）**——RyouToppa 弹窗内进攻按钮的真实渲染位置显然与该默认值不同，无法排除是同一资产在不同上下文下 match 到了别处，但**不能从静态源码可靠确定 Cluster B 对应的运行时 ROI**。按规则不猜 ROI：**只给 screen cluster 统计，不给 ROI-relative preferred center**。屏幕统计：center `(0.527, 0.545)`，std px `(40, 39)`，x p05/p25/p75/p95=634/664/693/706，y p05/p25/p75/p95=356/376/396/427，径向 `r50/r75/r90/r95 = 0.023/0.033/0.057/0.093`。
- **Cluster C = Large Area（胜利继续 + 奖励结算，已剔除进攻按钮污染）**：center `(0.742, 0.672)`，std px `(56, 50)`（对比上一条目被污染的 `(0.670, 0.631)`，std px `(144, 63)`——剔除 B 后中心右移下移、std 显著收窄，尤其 x 方向的虚假宽扩散消失）。x p05/p25/p75/p95=858/912/984/1034，y p05/p25/p75/p95=402/450/519/560，径向 `r50/r75/r90/r95 = 0.065/0.088/0.121/0.153`。页 3（胜利继续）与页 4（奖励结算）仍**无法可靠再拆**（v1 无标签、两者深度重叠），继续合并统计，这一条结论不变。

### 对旧粗估的重新核对

- 旧 `Button ≈ (0.66, 0.52)`：既不接近 Cluster A `(0.50,0.29)` 也不接近 Cluster B `(0.53,0.55)`，判定 **不成立**——推测是早期未做任何去重 / 分区时对整批人工点击的粗略平均，不对应任何单一控件。
- 旧 `Large Area ≈ (0.75, 0.71)`：与正确剔除 B 后的 Cluster C `(0.742, 0.672)` **非常接近（Δ≈0.01/0.04）→ 基本成立**，比上一条目错误给出的「修正值」`(0.67, 0.63)` 更准。上一条目的「修正」实际上是把 Large Area 估计带偏了。

### 对后续 ClickSampler 的数据结论（不写生产代码，替换上一条目对应结论）

- **Cluster A（`C_AREA_1` 目标卡片）**：有可靠 ROI-relative 数据，`preferred (u,v) ≈ (0.61, 0.58)`，`std (u,v) ≈ (0.19, 0.43)`——v 方向偏大是因为卡片本身高度小（74px）、std_y=32px 相对占比高，不代表点击特别分散。**可作为 ClickSampler 初始数据**（仅限区域 1 这张卡片；其它 7 张卡片的样本本轮未观测到，需要更多人工采样）。
- **Cluster B（真正的进攻按钮）**：只有 screen cluster 统计（center 归一化 `(0.53,0.55)`，std 40×39px，很紧），**没有可靠 ROI**——如果要在 ClickSampler 里用，要么后续拿到运行时真实 ROI 后转换成 u/v，要么直接用当前 screen 统计做一次性场景（风险：换分辨率 / 换弹窗皮肤会失效）。**建议先补充采样确认该簇跨会话的稳定性，且需要拿到进攻按钮弹窗的真实 ROI**。
- **Cluster C（Large Area，B 已剔除）**：`preferred ≈ (0.74, 0.67)`（屏幕归一化），std 56×50px，比之前污染的估计更集中、更可信。**可作为 ClickSampler 初始数据**（仍是页 3+4 合并后的粗粒度目标，未来若拿到 page 标签可再拆）。
- 方法学结论不变：preferred center 必须基于 burst-collapse 后的独立落点、报告阈值敏感性；**新增**：多簇场景下先验证簇数与簇间转移关系（k-means + transition_counts），再套固定分割线，否则分割线本身可能把不同控件的点击混进同一组（本次错误的根因）。

### 验证

- `tests/test_manual_click_analyze.py`：`32/32 OK`（新增 `DetectCalibrationPrefixTest` 4、`KmeansClustersTest` 3、`TransitionCountsTest` 2、`IoTest` 新增三簇场景 1）。
- `compileall` 覆盖 `dev_tools/manual_click_analyze.py`、`tests/test_manual_click_analyze.py`：通过。
- 完整回归 `toolkit/python.exe -m unittest discover -s tests`：`345/345 OK`（旧 335 → 345）。
- `git diff --check`：通过（仅既有 `docs/*.md` LF/CRLF 提示）。
- 原始日志 `log/manual_click/yys1_2026-09-01.jsonl` 未改动；派生文件仍写 `log/manual_click_analysis/`（`log/` 已 gitignore）。
- 未启动 MuMu / 游戏 / OAS / OCR / 设备。

### 生产影响

- 无。仅修改分析工具 `dev_tools/manual_click_analyze.py`（新增函数 + 修正 `region_split` 的错误页面语义 note）与其测试，未改 `RuleClick` / `RuleImage` / `Control` / minitouch / `ClickSampler`（不存在）/ 任何生产任务。

### Git

- 未 commit、未 push、未真机测试。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-02 - Cluster A ROI 统计口径修正 + Runtime ROI Probe v1

### 目标

延续点击改造支线，本轮只做两件事：① 确认并修正 `manual_click_analyze.py` 的 ROI-relative 统计是否只用 ROI 内落点；② 新增只读 `dev_tools/runtime_roi_probe.py`，为拿到真进攻按钮 `I_FIRE` 的真实运行时 ROI 做准备。**不改 burst collapse / 三簇分类算法，不实现 ClickSampler。**

### 1. Cluster A ROI 统计口径确认 + 修正

**核对结论：此前是 B（107 条全部换算后一起计算），确有污染。** `landing_stats(points, roi=...)` 原实现对传入的**全部**点计算 `mean_u/v` 等，不管是否落在 ROI 内；上一条目报告的 Cluster A `mean_u=0.610, mean_v=0.584, std_u=0.194, std_v=0.428` 就是这样算出来的，混入了 ROI 外的点。

**修正**：`landing_stats()` 拆成 `_landing_stats_core()`（纯落点统计）+ 外层过滤。传 `roi=` 时，**默认只用 `inside_roi` 的子集**计算 `mean_x/y`、`std_x/y`、`median`、全部 percentile、径向 `r50..r95`，以及 `mean_u/v` 等 ROI 相对量；ROI 外样本**不删除、不 clamp**，通过新增的 `outside_count` / `outside_ratio` / `outside_points`（原始坐标）单独报告。`count` 字段现在是 inside 样本数，新增 `total_count` 是全部样本数。`p05/p25/p75/p95 u/v` 补齐（之前只有 p05/p95）。

**重新输出 Cluster A**（`500ms/5px` 参考阈值，behavior-only 107 条，对 `C_AREA_1.roi_front=(533,162,177,74)`）：

- **inside n = 101**，outside = 6（5.6%）——**不是上一条目说的「98/107、9 个外点」**：那次是用半开区间 `[x, x+w)` 手工核对得到 9 个（另 3 个恰好卡在 `u=1.0` 或 `v=1.0` 边界），而工具的 `relative_uv` 判定用的是闭区间 `0<=u<=1`（`ManualClickRecorder` 早就用这个约定，`tests/test_manual_click_recorder.py` 已锁），本轮按**工具实际使用的口径**为准：101 inside / 6 outside。
- **ROI-relative（inside-only）**：`mean_u=0.6271, mean_v=0.6218`，`std_u=0.1548, std_v=0.2074`，`median_u=0.6215, median_v=0.6216`，`p05/p25/p75/p95 u = 0.4011/0.5311/0.7345/0.8588`，`p05/p25/p75/p95 v = 0.2973/0.4730/0.7838/0.9324`。
- **屏幕坐标（inside-only）**：`mean=(643.99, 208.01)`，`std=(27.4, 15.35)`（比污染前的 `std=(34.37,31.68)` 更紧，尤其 y 方向——6 个外点里有 3 个 y 方向偏得很远）。`normalized_mean=(0.5031, 0.2889)`，径向 `r50/r75/r90/r95 = 0.0234/0.0346/0.0442/0.0534`。
- **6 个 outside 样本坐标**：`(718,203) (624,247) (588,247) (507,5) (492,10) (619,239)`。性质：
  - `(619,239)` v=1.04，`(718,203)` u=1.045：**卡片边缘的近距离越界**（超出 ROI 右 / 下边界不到 10px），像是瞄准卡片时略微点过了边；
  - `(624,247) (588,247)` y=247，超出 ROI 下边界 11px：同类边缘越界；
  - `(507,5) (492,10)`：**明显离群**，在屏幕左上角附近，离 `C_AREA_1` 卡片约 240px（正是簇内最大距离 `max=245.6` 的来源），性质不明（可能是二次窗口核对或误触），**不是卡片瞄准行为**，不强行归类。
- **已知遗留不一致（本轮不改，仅记录）**：`relative_uv` 的 `inside_roi` 判定用闭区间 `[0,1]`（两端含），而项目里 `random_point_in_roi` 等用半开区间 `[x,x+w)`——两种约定都能自洽解释，但不完全一致；`ManualClickRecorder` 已用闭区间发过一版 v1 并测过，本轮不追溯修改（超出本轮范围，需要时另开任务评估）。

### 2. calibration 启发式收紧为「可覆盖、报告依据」

`detect_calibration_prefix` 的规则（首次相邻间隔 `>=8s` 且前缀含屏幕边缘点）**明确标注为只在 `yys1_2026-09-01.jsonl` 这份日志上验证过的启发式，不是通用「窗口映射校准」协议**：

- `analyze()` 新增 `calibration_count: int | None` 参数、CLI `--calibration-count N`，显式给出时完全跳过启发式，直接用该值；`summary["calibration"]` 新增 `detected_by`（`auto_heuristic` / `override` / `disabled`）与 `excluded_range_ts`（被排除的时间范围），供人工核对。
- 函数与 CLI 帮助文本都加了警示：换一份日志前先看 `excluded_range_ts` 是否合理，不放心就用 `--calibration-count` 覆盖。**没有引入自动确认交互，按要求不扩大本轮范围。**

### 3. 新增只读 `dev_tools/runtime_roi_probe.py`

只截图 + 只识别 + 只打印 / 记录，**绝不点击、不发送任何输入、不主动启动 MuMu / 游戏 / OAS**：

- **窗口定位**：复用 `dev_tools/manual_click_recorder.py` 已实现并测过的 `resolve_viewport_hwnd` / `viewport_sanity` / `_read_handle_field`，不建第二套 HWND 查找。
- **截屏**：复用生产 `module/device/method/windows_impl.py:Window.screenshot_window_background`（BitBlt 协议本身不变）——该方法只依赖 `self.screenshot_handle_num` / `self.screenshot_size` 两个属性，用一个 `SimpleNamespace` 顶替 `self` 直接调用，不构造完整 `Window`/`Handle` 实例，不触发任何 `Handle.__init__` 之外的副作用。**明确不实例化 `Device`**——其 `__init__` 在模拟器未运行时会主动 `emulator_start()`，是必须避免的副作用；也不实例化 `BaseTask`（业务副作用过多）。
- **识别**：`target.match(frame)`，`target` 默认是 `RealmRaidAssets.I_FIRE`（`_TARGET_REGISTRY` 惰性 import，可扩展），**未修改 `RuleImage` 任何公共 API**。匹配成功后 `roi_front` 已被生产代码自身的 `_update_roi_front` 动态改写，直接读出即为运行时 ROI；未匹配也记录一条（`matched=false`），不静默丢弃。**未输出 score/similarity**——获取它需要绕开 `match()` 直接掏 RPC 返回的内部 result dict，为遵守「不改公共 API / 不新起第二套协议」的要求本轮放弃，只用 `match()` 这一个公共入口。
- **失败处理**：窗口找不到 / 视口校验不过 / 图像识别服务（Image RPC，`get_image_client()`）连不上，第一次探测就失败时打印清晰错误 + 退出码 3，不重试到死、不崩溃；提示「请确认 OAS 主进程已启动」而不是自己去启动。
- **输出**：`log/manual_click_analysis/runtime_roi/<target>_<日期>.jsonl`，字段 `ts/config/target/matched/viewport_hwnd` + 匹配成功时的 `roi_front/center/template_width/template_height`。不改 `BehaviorTrace` / `ManualClickRecorder` 原始日志。
- **CLI**：`--config yys1 --target I_FIRE`，默认 `--count 1`（等价 `--once`），可 `--count 10 --interval 2` 连续探测；`summarize_roi_samples()` 汇总 `matched_count`/`unmatched_count`/`unique_roi_count`/`unique_rois`/`x_min..h_max`/`stable`（`stable` 要求至少 1 次匹配且 `unique_roi_count<=1`，0 次匹配不算稳定）。

### 4. Cluster B ROI-relative 调用链已就绪（未执行——没有真实 ROI）

`analyze()` 的 `--three-cluster --roi x,y,w,h` 组合本轮验证过可用：全局 `roi` 会传入每个簇的 `dedup_stats`，拿到 I_FIRE 真实 ROI 后直接：

```
toolkit\python.exe dev_tools\manual_click_analyze.py log\manual_click\yys1_2026-09-01.jsonl --three-cluster --roi <fire_x>,<fire_y>,<fire_w>,<fire_h>
```

`cluster_B` 的 `dedup_stats` 就会是 inside-only 的 ROI-relative preferred center，`cluster_A`/`cluster_C` 因不落在该 ROI 里会显示 0 inside（无害）。**本轮只验证了调用链，未传入真实 I_FIRE ROI**（未接入真机，未运行 probe）。

### ⚠️ 顺带修复：`DEVELOP_LOG.md` 自身的一处历史损坏

核对本轮要新增内容的落点时发现：上一条目「人工点击 Cluster 分类修正」在文件中被**重复了 9 次**——根因是那一轮用 `Edit(replace_all=true)` 在 `"### Git\n\n- 未 commit..."` 这个**每条日志都有的通用收尾**上做锚点插入新内容，导致新内容被插到了全部 9 处历史「### Git」收尾之后，把无关的历史条目都串了一遍。已核对每个副本内容逐字相同、且只是插入不是覆盖（其余历史条目本身未被破坏），删除 8 份多余副本，只保留链末尾按时间顺序本就应该在的那一份；`git diff --check` 确认清理后文件仍合法。**这不是本轮任务目标，只是本轮编辑前的必要修复**；以后往 `DEVELOP_LOG.md` 追加内容一律锚定紧邻新内容之前的、包含足够上下文的唯一文本，不用会在多条目重复出现的通用收尾语做 `replace_all` 锚点。

### 测试

- `tests/test_manual_click_analyze.py`：`39/39 OK`（新增 6 个 ROI 过滤相关用例 + 2 个 calibration override/disabled 用例）。
- `tests/test_runtime_roi_probe.py`（新文件）：`11/11 OK`——`build_probe_record`（matched/unmatched 字段形状、JSON 可序列化）、`probe_record_path`、`append_probe_record`（IO）、`summarize_roi_samples`（全同 ROI 稳定 / 变化不稳定 / 全未匹配 / 空输入）、`resolve_target`（`I_FIRE` 解析成功、未知 target 报错）。不装真实设备 / RPC。
- `compileall` 覆盖 `dev_tools/manual_click_analyze.py`、`dev_tools/runtime_roi_probe.py`、两个测试文件：通过。
- CLI 冒烟：`runtime_roi_probe.py --help`、非法 `--target`（exit 2）、无效 `--hwnd`（exit 3，报错信息清晰、无崩溃）均按预期；`manual_click_analyze.py --three-cluster --roi ...` 端到端跑通（用假 ROI 验证调用链后已重新生成不含假数据的干净 `log/manual_click_analysis/yys1_2026-09-01_summary.json`）。
- 完整回归 `toolkit/python.exe -m unittest discover -s tests`：`363/363 OK`（旧 345 → 363）。
- `git diff --check`：通过（仅既有 `docs/*.md` LF/CRLF 提示）。
- 未启动 MuMu / 游戏 / OAS / OCR / 设备；`runtime_roi_probe.py` 本轮只做了针对无效 `--hwnd` 的失败路径冒烟，未连接真实图像识别服务。

### 生产影响

- 无。改动限于 `dev_tools/manual_click_analyze.py`（`landing_stats` 重构 + calibration 覆盖参数）、新增 `dev_tools/runtime_roi_probe.py`、两个测试文件、`docs/DEVELOP_LOG.md` 的历史损坏修复。`RuleClick` / `RuleImage` / `RuleOcr` / `Control` / minitouch / `random_point_in_roi` / 任何 Task 均未改。

### Git

- 未 commit、未 push、未真机测试。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-02 - ClickSampler v1 + LEGACY_UNIFORM 等价接入（T7-1 第 1 阶段）

### 目标

建立点击坐标空间采样的唯一公共层，**生产行为与当前版本严格等价**。本轮只做 `ClickSampler` + `LEGACY_UNIFORM` + 4 个 `Rule.coord` 接入 + 完整静态回归；**不实现 HABIT / preferred center / Safe ROI 策略，不动 swipe / dwell / pressure**。

### 当前真实调用链（接入前，逐行核实）

```
Asset: RuleImage / RuleClick / RuleOcr / RuleGif   （tasks/*/assets.py）
   │  .coord()
   ▼
random_point_in_roi(roi)   —— module/base/utils/random.py:
      _rng = SystemRandom()（模块级单例）
      x,y,w,h = roi;  return (_rng.randrange(x,x+w), _rng.randrange(y,y+h))   # 半开区间，x/y 独立均匀
   ▼
BaseTask（透传 x,y）→ Control.click(x,y) → ensure_int → backend
```

### 新增

- **`module/click_sampler.py`**：
  - `ClickSampler.sample(roi, *, strategy=LEGACY_UNIFORM) -> (int, int)`，`@staticmethod`。轻量：无 IO / 日志 / 历史 / 锁 / numpy / 建对象。
  - `LEGACY_UNIFORM` **直接 `return random_point_in_roi(roi)`**——同一函数、同一模块级 `SystemRandom`、逐字等价；`random_point_in_roi` 的 `TypeError`（非整数 ROI）/ `ValueError`（w·h ≤ 0）原样透传。
  - `STRATEGY_HABIT` / `STRATEGY_STRICT` / `STRATEGY_UNIFORM` 语义名占位，调用抛 `NotImplementedError`；未知策略抛 `ValueError`。**preferred center / Gaussian / mixture / Safe ROI / padding / tail / 历史状态 / target profile / 人工热点默认值 = 本轮 0 实现**，留给下一轮 Click Profile / Strategy。
  - ROI 沿用既有 `(x, y, w, h)` 格式，**每次用调用方传入的当前值，不缓存**（`RuleImage.roi_front` 在 `match()` 后会被 `_update_roi_front` 改写）。
- **`tests/test_click_sampler.py`**（18 用例）：见「测试」。

### 接入（最小改动，只换调用点）

| 文件 | 改动 |
|---|---|
| `module/atom/click.py` | import `random_point_in_roi` → `ClickSampler`；`RuleClick.coord()` 与 `coord_more()` 里 `random_point_in_roi(...)` → `ClickSampler.sample(...)` |
| `module/atom/image.py` | 同上（`RuleImage.coord()` + `coord_more()`） |
| `module/atom/ocr.py` | import 换；`RuleOcr.coord()` 里 `random_point_in_roi(area)` → `ClickSampler.sample(area)`（`area` = `self.area` if `mode==FULL` else `self.roi`，逻辑不变） |
| `module/atom/gif.py` | import 换；`RuleGif.coord()` → `ClickSampler.sample(self.roi_front)` |

`git diff module/atom/{click,image,ocr,gif}.py` 全部只有这 4 个 import 换行 + 6 个调用点换行（`coord` ×4、`coord_more` ×2），无任何逻辑改动。`RuleLongClick` 继承 `RuleClick.coord()`，未改。业务层调用不变（仍是 `target.coord()`），`BaseTask` / `Control` API / 后端全未动。

`coord_more`（roi_back 采样）全仓无调用方（死路径），顺带一起路由，使「空间随机入口」收敛干净、4 个 atom 里不再直接出现 `random_point_in_roi`。

### `random_point_in_roi` 全仓分类（接入后）

- **A（已由 ClickSampler 接管的正常点击路径）**：`module/atom/click.py`（`RuleClick.coord`+`coord_more`）、`image.py`（`RuleImage.coord`+`coord_more`）、`ocr.py`（`RuleOcr.coord`）、`gif.py`（`RuleGif.coord`）。`RuleLongClick` 经继承覆盖。这是全部 `Rule.coord()` 正常点击坐标生成面。
- **B（非点击 / 定义本身）**：`module/base/utils/random.py:53`（`random_point_in_roi` 定义，ClickSampler 内部调它）；`module/click_sampler.py`（import + 调用它）。
- **C（task 私有，非 `Rule.coord` 主路径，本轮不动）**：`tasks/Component/GeneralInvite/general_invite.py:_random_point_in_area`（点 OCR 命中的好友名框，绕过 `Rule.coord()`，§4.20 已记录）。
- 另：`random_center_point_in_roi` 只服务 `RuleSwipe.coord()` 滑动端点，非点击，未动；`SixRealms` 私有 `front_center` ± 偏移、`RuleClick.move()` 按要求不清理。

### 明确未改

`Control.click` / `Control.long_click` API、minitouch / adb / uiautomator2 / scrcpy / window_message 后端、`CommandBuilder.convert`、`BaseTask` 业务逻辑、`BehaviorTrace`（schema 与记录逻辑，仍记 Control 收到的最终坐标）。当前人工热点数据（卡片 `≈(0.68,0.53)` / 普通按钮 `≈(0.62,0.70)` / Large Area `≈(0.74,0.67)` / Tiny 居中略右）**未写进任何生产默认值**，仍只在实验结论里。

### 测试

- `tests/test_click_sampler.py`：`18/18 OK`。
  - `ClickSamplerBoundsTest`：输出落在 ROI 半开区间、整数元组、不 mutate 输入 ROI、连续不同 ROI 每次用当前值（不缓存）、1×1 ROI 恒定、注入固定 RNG 能取到下界与上界-1（无中心强制偏置）、透传 helper 的 `TypeError`/`ValueError`。
  - `ClickSamplerStrategyTest`：`LEGACY_UNIFORM` mock 验证「只调 `random_point_in_roi(roi)` 一次、参数与返回值原样」；同一 RNG 序列下 `ClickSampler.sample` 与直接 `random_point_in_roi` 逐点结果一致（**语义等价**，不要求独立随机调用同值）；默认策略即 `LEGACY_UNIFORM`；`HABIT/STRICT/UNIFORM` → `NotImplementedError`；未知策略 → `ValueError`。
  - `RuleCoordRoutingTest`：5 个 Rule（含 `RuleLongClick` 继承、`RuleImage` 动态 `roi_front` 改写后用新值、`RuleOcr` FULL/SINGLE 分别用 `area`/`roi`）的 `coord()` 都经 `ClickSampler.sample` 且返回值结构不变；`RuleClick.coord()` 端到端 300 次采样边界不变。
- `compileall` 覆盖 `module/`、`tasks/`：通过。
- 直接依赖模块导入冒烟：`module.atom.{click,image,ocr,gif}` + `module.atom.long_click` 均正常 import（`module.click_sampler` 只依赖 `module.base.utils.random`（stdlib），无循环）。
- 完整回归 `toolkit/python.exe -m unittest discover -s tests`：`381/381 OK`（旧 363 → 381）。
- `git diff --check`：通过（仅既有 `docs/*.md` LF/CRLF 提示）。
- 未启动 MuMu / 游戏 / OAS / OCR / 设备——本轮生产行为与 legacy 逐字等价，理论上不需要设备验证。

### 生产影响

- **本轮新增的是空间采样架构层，不改变现有生产点击分布。** `LEGACY_UNIFORM` 就是 `random_point_in_roi` 本身；4 个 `Rule.coord` 只是把调用点换成 `ClickSampler.sample`。返回值形态、ROI 边界语义、随机源、异常行为、`Control` 及后端、`BehaviorTrace` 记录全部不变。`C_RANDOM_*` 安全大区继续 `LEGACY_UNIFORM`（全 ROI 均匀），不因未来有 HABIT 而被中心偏置。

### 下一阶段（不在本轮）

Click Profile + Strategy：实现 `HABIT` / `STRICT` / `UNIFORM`，新增 `ClickProfileManager`（按 config_name 单例、默认关闭、可完全旁路），按 `task+page+target(+ROI)` 身份键引入 preferred center + core/medium/tail 混合分布 + Safe ROI 内收；届时才用已得的人工热点数据。**需真机验证**（Level C）。

### Git

- 未 commit、未 push、未真机测试。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-02 - T7-1 第 2 阶段：ClickProfile + HABIT/STRICT/UNIFORM + Safe ROI

### 目标

给 ClickSampler 加「参数（ClickProfile）+ 采样（Strategy）+ 安全边界（Safe ROI）」能力。**本轮完成后现有生产目标仍默认 `LEGACY_UNIFORM`**，新策略零生产消费者。不做在线学习 / EMA / AR(1) / 自动目标分类 / 配置系统改造 / swipe / dwell / pressure。

### 新增

- **`module/base/utils/random.py`**：新增 `random_normal(mu, sigma)` —— 复用同一模块级 `_rng`（`SystemRandom`）的 `gauss`，`sigma < 0` → `ValueError`，`sigma == 0` → 返回 `mu`。无 numpy、不新建 RNG。**生产链未调用它**（只有 HABIT/STRICT 用，而它们无生产消费者）。
- **`module/click_profile.py`**：
  - `ClickProfile`（`@dataclass(frozen=True)`）：`name` / `preferred_u,v` / `core_sigma_u,v` / `medium_sigma_u,v` / `core,medium,tail_weight` / `safe_margin_u,v` / `max_attempts` / `provisional`。全部 ROI 相对 `u/v`，**不存绝对屏幕坐标**。`__post_init__` 校验（`preferred∈[0,1]`、`sigma≥0`、`weight≥0` 且和为正、`margin∈[0,0.5)`、`max_attempts≥1`）→ 非法 `ValueError`（不静默 clamp）。`normalized_weights()` / `without_tail()`。
  - `DEFAULT_PROFILES`：`default`、`wide_card`、`normal_button`、`large_area`、`small`、`tiny`、`strict`。个人先验值 `wide_card≈(0.68,0.53)` / `normal_button≈(0.62,0.70)` / `large_area≈(0.74,0.67)`；`tiny≈(0.52,0.50)` / `small≈(0.54,0.50)` / `strict` / `default` 标 `provisional=True`（数据不足，保守）。sigma 有序：tiny < small < normal_button ≤ wide_card < large_area。**不是一个 global center**——各类别纵向热点确有差异。
  - `ClickProfileManager`（内存注册表，`get()` 回退 `default`）+ `resolve_profile(None|名字|实例)`。无配置加载、无用户 override、无 identity 树。`STRICT_MAX_CORE_SIGMA = 0.12`。

### `module/click_sampler.py` 重写（LEGACY 路径逐字不变）

- `sample(roi, *, strategy=LEGACY_UNIFORM, profile=None)`。
- **`LEGACY_UNIFORM`（默认）**：仍是第一分支 `return random_point_in_roi(roi)` —— 不 resolve profile、不算 Safe ROI、不构造状态。`test_legacy_uniform_still_delegates_directly_no_profile` 锁「不调 `resolve_profile`」；`test_legacy_uniform_semantic_equivalence_same_rng` 锁「同 RNG 序列逐点等价」。
- **`UNIFORM`**：`random_point_in_roi(_safe_roi(roi, default_profile))` —— Safe ROI 内均匀。与 LEGACY 数学同族、语义不同（见 §4.25）。
- **`HABIT`**：`_choose_component`（按归一化累计权重选 `core`/`medium`/`tail`）→ 选一个成分采样一次。`core`/`medium` = `random_normal(preferred_u, sigma_u)` × `random_normal(preferred_v, sigma_v)` 映射回原 ROI 像素 → 落 Safe ROI 内才接受，否则有限次 rejection（`max_attempts`），用尽 → `_fallback_point`（热点 u/v 夹进 `[margin, 1-margin]` 投影进 Safe ROI 的**单个确定点**，非边界 clamp）。`tail` = `random_point_in_roi(safe_roi)`（安全区内均匀，不误点）。
- **`STRICT`**：`profile=None` → 内置 `strict` profile；`without_tail()` 强制无 tail；resolve 出的 profile `core_sigma > STRICT_MAX_CORE_SIGMA` → `ValueError`（拒绝 `wide_card`/`large_area`）。其余同 HABIT 机制。
- 未知策略 → `ValueError`。

### 接入边界

`module/atom/{click,image,ocr,gif}.py` **本轮未再改**，仍 `ClickSampler.sample(roi)` 默认 `LEGACY_UNIFORM`（`test_rule_default_strategy_still_legacy_uniform_untouched` 用 `inspect.getsource` 断言 `RuleClick.coord` 源码里只有 `ClickSampler.sample(self.roi_front)`、不含 `HABIT` / `strategy`）。`Control` / minitouch / 后端 / `BehaviorTrace` 未改。人工热点数据只在 `DEFAULT_PROFILES` 里作 profile 参数，**没有**变成 ClickSampler 全局默认。

### 测试

- `tests/test_click_profile.py`（新，44 用例）：ClickProfile 数据结构 + fail-fast、`resolve_profile` / Manager、`_safe_roi`（margin 0/正常/tiny/过大退化/不 mutate/非整数）、HABIT（热点传入、core/medium sigma、单成分、tail 均匀、权重选择、rejection+resample、cap+fallback（非 clamp）、贴边投影、大样本恒在 Safe ROI、均值近热点、None→default）、STRICT（默认窄 profile >90% 落中心±20px、去 tail、拒绝宽 profile、接受 tiny/small、spread 明显窄于 habit wide、恒在 Safe ROI）、UNIFORM（Safe ROI 内、margin=0 等于整 ROI、与 LEGACY 名字不同）、LEGACY 不受影响。
- `tests/test_click_sampler.py`（改，19 用例）：原「HABIT/STRICT/UNIFORM 抛 NotImplementedError」的用例换成「已实现且落 ROI 内」+ 新增「`RuleClick.coord` 源码仍是纯 LEGACY」；其余 LEGACY 等价 + Rule 路由用例不变。
- `compileall module/ tasks/`：通过。
- 完整回归 `toolkit/python.exe -m unittest discover -s tests`：`425/425 OK`（旧 381 → 425）。
- `git diff --check`：通过（仅既有 `docs/*.md` LF/CRLF 提示）。
- 未启动 MuMu / 游戏 / 设备 / OCR——新策略无生产消费者，本轮理论上不需要设备验证。

### 生产影响

- 无。`LEGACY_UNIFORM` 逐字不变、`Rule*.coord()` 未改、默认策略仍 `LEGACY_UNIFORM`、`random_normal` 未进生产链、`Control`/后端/`BehaviorTrace` 未改。**本轮已实现新的空间模型能力，但默认生产点击仍然完全保持 `LEGACY_UNIFORM`。**

### 下一阶段（T7-1 第 3 阶段，不在本轮）

挑 4 类代表目标显式 opt-in：wide_card → HABIT、normal_button → HABIT、tiny/small → STRICT、`C_RANDOM_*` → UNIFORM，逐个验证，再 MuMu Level C 真机验收。

### Git

- 未 commit、未 push、未真机测试。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-02 - 点击 ROI 尺寸静态普查（`dev_tools/click_roi_inventory.py`）

### 目标

用只读 AST 工具普查全仓「可能最终用于点击的 ROI」的真实宽高 / 短边 / 长边 / 面积分布，为 T7-1 第 3 阶段的 tiny·small profile 尺寸门槛提供数据依据。**先给数据、再给阈值**；本轮不修改 ClickSampler / ClickProfile / Rule / Task，不采纳任何阈值、不改默认行为。不沿用此前人为的 `Tiny<24 / Small 24–47 / Normal 48–95 / Large≥96`，用仓库真实数据验证或推翻。

### 新增 `dev_tools/click_roi_inventory.py`（只读、纯 AST）

- `ast.parse` 扫 `tasks/` + `module/atom/`，抽 `RuleClick` / `RuleImage` / `RuleLongClick` / `RuleOcr` / `RuleGif` 会进 `.coord()` 的矩形：Click/LongClick/Image/Gif 取 `roi_front`；Ocr 取 `roi`，`mode=Full` 且有字面量 `area` 时取 `area`。只认字面量四元组（含 `-n`），表达式 / 变量 / `a+b` 标 `unknown` 不猜。`RuleSwipe` / `RuleList` 不计入。
- `roi_semantics`：`C_*RANDOM*` → `large_safe_area`；`RuleImage`/`RuleGif` → `dynamic_template`（`roi_front` 位置 match 后被 `_update_roi_front` 改写，但 w/h≈模板尺寸仍是点击目标尺寸的合理近似）；`RuleOcr` 多为读取用途，单独分组。
- `size_flag`：`degenerate`(w 或 h ≤0) / `very_thin`(AR≥5) / `very_large`(short≥300 或 area≥30 万) / `normal`。
- 附全仓 consumer 粗扫（按符号名，`appear_then_click` / `ui_click*` / `.click(SYM)` vs `appear(SYM)`），方向偏保守（宁可多算「可能被点」），产出 `confirmed_clickable` 子集。
- 输出 `log/click_roi_analysis/click_roi_inventory.json` + `click_roi_summary.md`。CLI：`--roots` / `--out-dir` / `--no-consumer-scan`。

### 主要数据（本轮运行）

- unique 可点击 ROI 定义 **2678**：RuleImage 2074 / RuleClick 297 / RuleOcr 297 / RuleLongClick 10 / RuleGif 0。非字面量 ROI 20；`C_*RANDOM*` 大安全区 25。
- 主分布（Click+Image+LongClick，排大安全区，n=2339）short_side：min 1 / p05 21 / p10 23 / p25 32 / median 46 / p75 68 / p90 100 / p95 120 / max 720。area median 3569 / p75 8648 / p90 14584。AR：<1.5 1317、1.5~2 280、2~3 462、3~5 219、>5 61。
- confirmed_clickable（Click/LongClick + 有点击 consumer 的 Image，n=763）short_side：min 12 / p05 21 / p25 40 / median 55 / p75 81 / p90 110 / p95 143 / max 720。比主分布偏大——大量 tiny 值来自纯检测 `I_*_CHECK` / `I_*_ON` / `I_*_LOCK`，不在点击链上。
- 按类型 short_side median：RuleClick 67（p25 47 / p75 100）、RuleImage 44（p25 32 / p75 63）、RuleOcr 37、RuleLongClick 63.5。

### 结论（阈值仍是候选，未采纳）

- 数据推导候选边界（以 confirmed_clickable short_side 分位）：Tiny `<24`（≈p05，仅 11/763）、Small `24–40`、Normal `40–96`、Large `≥96`。**下沿 24 得到数据支持；中间分界更接近 40，不是人为的 48。**
- 几何尺寸 ≠ 语义类别：`C_QUIT_AREA`(30×14)、`C_ANSWER_ENSURE_*`(≈13×26)、`C_BUY_MORE`(174×17) 等窄条按钮需按语义单独指定 profile，不能只按 short_side 归类。
- 分布单峰右偏、无明显多峰 → `size_factor = f(short_side)` 连续映射比四档硬分类更贴合；真正需要离散的是「语义 override 名单」（大安全区 / 窄条 / 登录固定点），不是尺寸本身。
- short_side 比 area 更适合做主指标：area 被宽高比拉伸（窄条 area 可能不小但实际难点中短边方向）。
- 异常项：`O_STORE_SUSHI_PRICE` / `O_DOKAN_RIGHTPAD_BOUNTY` / `C_SELECT_CARD` 等静态 `(0,0,0,0)` 占位；`tasks/Chess/runtime/recognition.py` 一处 `<inline>` `RuleImage` 1×1。均标 `degenerate` 不参与数值统计。

### 测试

- `tests/test_click_roi_inventory.py`（新，27 用例）：AST 抽取（各 Rule 类型 / `roi_front` / Ocr 的 roi·area / Gif 计入 / Swipe·List 不计入 / 负整数 / 表达式→unknown / `<inline>` / `C_*RANDOM*`→large_safe_area）+ 纯统计（`_classify_size` 各 flag、`_percentile` 插值+空 NaN、`dist_stats`、`histogram` 左闭右闭、`build_summary` 计数与 `confirmed_clickable`）+ 真实仓库冒烟。
- `compileall dev_tools/click_roi_inventory.py tests/test_click_roi_inventory.py`：通过。
- 完整回归 `toolkit/python.exe -m unittest discover -s tests`：`452/452 OK`（旧 425 → 452）。
- `git diff --check`：通过（仅既有 `docs/DEVELOP_LOG.md` LF/CRLF 提示）。
- 未启动 MuMu / 游戏 / 设备 / OCR / 后端——纯静态 AST 分析。

### 生产影响

- 无。未改任何 Asset / `module/atom/*` / ClickSampler / ClickProfile / Rule / Task / Control / 后端。只新增一个 dev_tool + 一个测试文件 + `log/click_roi_analysis/` 输出。

### Git

- 未 commit、未 push、未真机测试。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-02 - 大尺寸点击 ROI 人工审查目录（`dev_tools/large_click_roi_review.py`）

### 目标

把仓库里所有「大尺寸、真实可能用于点击」的 ROI 整理成可按编号（001、002、003…）逐项人工确认的目录，供用户判断每块区域对应哪个页面 / 控件、ROI 是否合理、是「大按钮」还是「大安全区」、是否适合个人热点、是否继续 Uniform、是否需要重新截图。**本轮不修改任何生产代码 / Asset / ClickSampler / ClickProfile**，`short_side >= 96` 只是取样线、不写进生产分类逻辑。

### 前置：inventory 数据已过期，先刷新

发现 `log/click_roi_analysis/click_roi_inventory.json` 相对工作区已过期——用户在上一轮之后**手动重新框选**了 `tasks/Component/GeneralBattle/assets.py`：`C_RANDOM_LEFT` 55×370→192×506、`C_RANDOM_RIGHT` 79×388→191×518，新增 `C_RANDOM_RD`（574×314，注释「战斗结算/奖励默认点击范围」）与 `C_RANDOM_RD2`（198×425），并新增两条 `S_BATTLE_RANDOM_*` swipe。本轮先重跑 `click_roi_inventory.py` 再做筛选。

### `dev_tools/click_roi_inventory.py` 增补（唯一改动，纯附加）

`RoiRecord` 新增 `asset_file` 字段，抽 `RuleImage(file=...)` 的模板 PNG 路径（其它 Rule 为 `None`），供审查目录直接给出可打开的资源路径。原有字段与统计逻辑不变。

### 新增 `dev_tools/large_click_roi_review.py`（只读）

- **AST 消费者索引**（比 inventory 的正则粗扫准：能跨行、记录所在函数、区分 kind）。verb 分类：`click`（`click`/`appear_then_click`/`ui_click*`/`list_appear_click`/`ocr_appear_click`…）、`coord`（`SYM.coord()`）、`indirect_click`（`random.choice([C_A, C_B, …])` 再 `click` —— `GameUi/default_pages.py:random_click`·`handle_activity_overlay` 与 `MartialArts/page.py` 的真实形状，正则粗扫会漏）、`detect`（`appear`/`wait_until_*`/`ocr`…）。
- **同名符号消歧**：`C_RANDOM_LEFT` 在 `Component`/`GameUi`/`MartialArts` 各一份。`build_assets_class_map()` 建「Assets 类名 → assets.py 路径」，消费者写 `GeneralBattleAssets.C_RANDOM_LEFT` 时精确归属（`exact_by_qualifier`）；写 `self.C_X`（mixin 继承）无法区分，标 `ambiguous` 提醒人工核对。
- **筛选口径**：`RuleOcr` 一律不进主清单；`RuleImage` 必须**确认有点击消费者**才进（纯检测 `I_*_CHECK` 类进「排除项」，共 202 条）；`RuleClick`/`RuleLongClick` 天生点击用，零消费者也进清单并标 `UNUSED / NO PRODUCTION CONSUMER`（避免用户浪费时间检查死资产，也避免漏掉「待接入的新规划」）。
- **标注**：语义初判 A~I、Point vs Region 目标类型、P0/P1/P2、每条的「人工检查重点」勾选清单、模板 PNG 路径 + 是否存在。**全部 `review_status = pending`**，不替用户做视觉判断。
- **输出**：`log/click_roi_analysis/large_click_roi_review.md`（概览 → 建议优先看的前 20 → P0 结算/奖励/随机组 → P0 其它 → P1/P2 按 task 分组 → 全部 `*RANDOM*`（不限尺寸）→ 超大区域审查表 → 排除项）+ 同名 `.json`（含 `suggested_first_20` / `all_random` / `very_large` / `excluded`，供后续自动更新审查状态）。

### 本轮快照结果

`short_side>=96` 的 ROI 定义 400 → 主审查清单 **198**（RuleClick 117 / 有点击消费者的 RuleImage 77 / RuleLongClick 4），排除 202。P0 35 / P1 109 / P2 54；settlement·reward·random 组 27；`C_*RANDOM*` 全量 27；超大区域表 36；Region 46 / Point 152。

**零消费者 40 条**，其中最值得注意：`C_GREEN_MARK_AREA` 1280×720、`C_RANDOM_ALL` 1207×543、`C_FG_RANDOM_*` 全套 5 条、`C_DOKAN_RANDOM_CLICK_AREA1~3`、以及用户刚加的 `C_RANDOM_RD` / `C_RANDOM_RD2`（规划中、尚未接入）。**确认有点击消费者的随机区**只有：`C_RANDOM_CLICK`（`general_battle.py:1098` 战斗中低概率随机点）、`C_RANDOM_LEFT`（`chess_battle.py` 结算安全点）、`C_RANDOM_RIGHT`（FallenSun `appear_then_click(action=)`）、`GameUi`/`MartialArts` 各自的 `C_RANDOM_TOP/DOWN/LEFT/RIGHT`（overlay `random.choice` 后点击）、`C_RM_RANDOM_CLOSE_SAFE(_MAIN)`。

### 测试

- `tests/test_large_click_roi_review.py`（新，50 用例）：符号识别与限定前缀、消费者索引四种 kind + 跨行 + 最内层 def + 语法错误跳过、`build_assets_class_map` 真仓库解析、`attribute_usages` 四种归属、语义初判各分支、Point/Region、P0/P1/P2、检查问题生成、`build_items` 全部筛选口径与编号排序、`build_excluded`/`build_all_random`/`build_very_large`/`is_settlement_group`、真实仓库冒烟。
- `tests/test_click_roi_inventory.py`（改，+2 用例）：`asset_file` 抽取与 RuleClick 无模板图。
- `compileall`：通过。完整回归 `504/504 OK`（旧 452 → 504）。
- `git diff --check`：本工具相关改动无问题；仅报告**用户自己**编辑的 `tasks/Component/GeneralBattle/assets.py` 有 4 处行尾空格 + 1 处 EOF 空行——那是 `dev_tools/assets_extract.py` 自动生成格式（全文件都是这个形状），本轮不动 Asset，未修。
- 未启动 MuMu / 游戏 / 设备 / OCR / 网络——纯静态 AST 分析。

### 生产影响

- 无。未改 `module/click_sampler.py` / `module/click_profile.py` / `module/atom/*` / GeneralBattle / 任何 `C_RANDOM_*` / 任何 Asset ROI / Control / 后端。只新增一个 dev_tool + 一个测试文件、给 inventory 加一个附加字段、写 `log/click_roi_analysis/` 输出。

### Git

- 未 commit、未 push、未真机测试。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-02 - T7-1 Phase A：GeneralBattle 通用结算迁到 C_RANDOM_RD / C_RANDOM_RD2

### 目标

`GeneralBattle` 的普通 `_handle_result` / `_handle_reward` 推进**不再用 `random_click()`（`C_RANDOM_LEFT/TOP/RIGHT/BOTTOM` 四边随机）**，改为：Reward marker → `C_RANDOM_RD`（主结算区）；non-reward / result → `C_RANDOM_RD2`（右侧保守 fallback）；RD 点一次后 2 秒观察窗口；2 秒未推进 → sticky `C_RANDOM_RD2`。这是 `LEGACY_UNIFORM` 之外**第一个真进生产链的 ClickSampler 策略**。上一轮迁移审计的边界（`_settlement_click` 是唯一收口点、带自定义 `ltrb` 的调用方全绕开它）在本轮实施前重新以当前源码核实无误。

### 生产改动（唯一文件：`tasks/Component/GeneralBattle/general_battle.py`）

- **import**：去掉 `from tasks.GameUi.default_pages import random_click`（`_settlement_click` 是其在本文件唯一用处）；加 `from module.atom.click import RuleClick`、`from module.click_profile import ClickProfile`、`from module.click_sampler import STRATEGY_HABIT, ClickSampler`。`random_click()` 函数本身、默认 `ltrb`、四边资产**未动**。
- **模块常量**：`REWARD_MARKERS`（9 个纯奖励标识 = `page_reward` recognizer 减 `I_OVER_GHOST` / `I_GB_SKIN_CONFIRM`）、`_SETTLEMENT_PRIMARY_PROFILE`、`_SETTLEMENT_FALLBACK_PROFILE`（页面专属 `ClickProfile` 实例，`provisional=True`，**不进 `DEFAULT_PROFILES`**）、`_SETTLEMENT_PRIMARY_OBSERVE_SECONDS = 2.0`。
- **`BattleContext` 加 3 字段**：`settlement_stage` / `settlement_primary_ts` / `settlement_fallback`；`_build_context`（dataclass 默认）+ `_reset_round_context`（显式重置）覆盖。
- **`_sample_settlement_click(rule, profile)`**：`ClickSampler.sample(rule.roi_front, strategy=HABIT, profile=profile)` → `self.device.click(x, y, control_name=rule.name)`。**不经 `BaseTask.click`**（避免 `rule.coord()` 走默认 LEGACY），保留 rule 身份供 BehaviorTrace 区分 `random_rd` / `random_rd2`。采样抛 `ValueError`/`TypeError` → `logger.error` + 退回 `ClickSampler.sample(rule.roi_front)`（整 ROI 均匀），不静默、不卡死主循环。
- **`_settlement_click(context, rule, profile) -> bool`**（签名从 `(context)` 改）：`settlement_click_timer` 节流 + 调 `_sample_settlement_click` + 重采间隔。
- **`_advance_settlement(context, stage, *, reward_present)`**：状态机。`_reset_settlement_stage`（换 stage 才清 primary_ts / fallback）→ `reward_present and not fallback`：`primary_ts is None` 且节流到点 → 点 RD 记 `time.monotonic()`；`< 2s` → 观察（不点）；`>= 2s` → `fallback=True`。其余 → RD2。
- **`_sync_settlement_stage(context, page)`**：主循环 `_sync_prepare_click_timer` 之后调用，`page` 非结算页且非 `None` 时清空 stage 状态。
- **`_reward_marker_present()`**：`for name in REWARD_MARKERS: self.appear(getattr(self, name))`，复用当前帧，无额外 screenshot / OCR。
- **`_handle_result`**：`_advance_settlement(context, "result", reward_present=False)`。
- **`_handle_reward`**：`appear_then_click(I_OVER_GHOST)` / `appear_then_click(I_GB_SKIN_CONFIRM)` 捕获返回值 → 任一为真则清 `settlement_primary_ts` 并 `return CONTINUE`（早退，不进结算点击）；否则 `_advance_settlement(context, "reward", reward_present=self._reward_marker_present())`。

### 结算 profile 数值与依据

- **primary（RD `(699,397,574,314)`）**：`preferred_uv=(0.54,0.53)` → 屏幕 `(1009,563)`；`core σ (0.10,0.10)` `medium σ (0.16,0.16)` 权重 `0.80/0.17/0.03` `margin (0.06,0.06)`。σ 取「±2σ ≈ 标注器 Core `(925,510,210,120)` / Medium `(850,475,350,195)` 观察矩形半边长再放宽 5-10%」——core u ±2σ ≈ 115px ≈ Core 半宽 105；medium u ±2σ ≈ 184px ≈ Medium 半宽 175。3000 次实测 x∈[736,1238] y∈[417,690] 均值 `(1008,563)`，全在 Safe ROI 内、不铺满 RD。
- **fallback（RD2 `(1056,237,198,425)`）**：`preferred_uv=(0.56,0.58)` → 屏幕 `(1167,484)`；`core σ (0.12,0.09)` `medium σ (0.18,0.15)` 权重 `0.86/0.14/0`（**tail=0**）`margin (0.10,0.06)`。spread 比 primary 保守。3000 次实测 x∈[1083,1233] y∈[295,622] 均值 `(1166,483)`。

### Reward marker

用轻量 `REWARD_MARKERS` 集合，不是单一 marker——`I_REWARD`（用户本轮重新框为 `(558,508,166,106)` + 重截 `gb_reward.png`）只覆盖「魂」一种；金币 / 经验 / 皮肤 / 蛇皮各有独立模板。排除 `I_GB_SKIN_CONFIRM` / `I_OVER_GHOST`（特殊确认按钮，`_handle_reward` 已单独 `appear_then_click`）。不新增 OCR、不做奖励数量检测器、复用当前帧。

### 2 秒观察 / sticky / stage 重置

- 2 秒**不是** `sleep(2)` / `random_delay`——handler 每帧被 FSM 重新调用，`_advance_settlement` 靠 `time.monotonic() - settlement_primary_ts` 跨帧记时；页面在 2 秒内推进 → 下一轮 `detect_page_in` 返回别的页 → handler 不再被调用，观察自然结束。
- sticky 只在同一 settlement stage 内：`result` → `reward` 切换 `_reset_settlement_stage` 会清 `primary_ts` / `fallback`（reward 重新获得一次 RD 机会）；`reward` → `reward` 不清。
- RD2 重复点击受 `settlement_click_timer` + 战斗硬 `battle_timer` / `_tick_timeout` / `QUICK_EXIT` 约束，无独立 `while True`。

### 特殊按钮不退化

`_handle_reward` 里 `I_OVER_GHOST` / `I_GB_SKIN_CONFIRM` 仍最先 `appear_then_click`；这一帧真点过（返回 True）就早退且清 `settlement_primary_ts`（避免特殊页耗时被算成 RD 推进失败）。interval 门控未到点的中间帧行为与迁移前一致。

### 测试

- `tests/test_general_battle_settlement.py`（新，32 用例）：覆盖 spec §27 A–H——result 只 RD2、reward RD-once + 2s 观察（patch `time.monotonic`，不真 sleep）、观察超时锁 sticky、sticky 不回 RD、`result→reward` 重置 / `reward→reward` 保持、特殊按钮优先且清 `primary_ts`、`_reward_marker_present` 只读当前帧、两个 profile 实际数值 / 热点 / 不在 `DEFAULT_PROFILES`、`_sample_settlement_click` 走 HABIT + `control_name` + 异常退回、回归护栏（`random_click` 默认 `ltrb` / 四边资产 / `RuleClick.coord` 仍 LEGACY / moon_sea·peacock 未动）。
- `tests/test_general_battle_timing.py`（改）：4 个 `_settlement_click` 用例改到新签名 `(context, rule, profile)` 与新语义（result → RD2），加 `test_result_uses_fallback_region_not_primary`；`_settlement_ns` 辅助构造带结算字段的 context。15 → 16 用例。
- `compileall module/ tasks/`：通过。完整回归 `toolkit/python.exe -m unittest discover -s tests`：`537/537 OK`（旧 504 → 537）。
- 14 个受影响模块（GeneralBattle + 7 个 subclass + Dokan / Exploration / MetaDemon / Duel / default_pages）import 冒烟：全通过。
- `git diff --check`：本轮生产文件 + 测试文件无问题；仅报告**用户自己**编辑的 `tasks/Component/GeneralBattle/assets.py`（4 处行尾空格 + EOF 空行，`assets_extract.py` 自动生成格式）。
- 未启动 MuMu / 游戏 / 设备 / OCR / 网络。

### 仍需 Level C 真机验收

静态回归全绿 ≠ 迁移完成。手动验收至少覆盖：普通胜利 / 失败 result、Reward 少 / 多的页面、RD 点后 2 秒 fallback、RD2 连续推进、`result→reward` 时 RD primary 重新启用、`I_OVER_GHOST`、`I_GB_SKIN_CONFIRM`、RealmRaid / RyouToppa exit_matcher 回业务页。

### 生产影响

- **仅限 GeneralBattle 通用 result / reward 推进**：从 `random_click()` 四边随机改为 RD / RD2 + Reward 判断 + 2s 观察 + sticky fallback。Phase A 自动覆盖 `RealmRaid` / `HeroTest` / `Orochi` / `EvoZone` / `EternitySea` / `ActivityShikigami` / `BondlingFairyland._handle_reward`（special 分支仍先执行）。
- **未改**：`random_click()` 及其所有带自定义 `ltrb` 的调用方（Duel / Dokan / SixRealms 退出页 / fake_god / normal）、`BondlingFairyland._handle_result`、`SixRealms/{moon_sea,peacock_kingdom}._handle_reward`（Phase B）、Exploration / MetaDemon task-private、`default_pages` 两个 page hook、SixRealms import-time `connect`、`module/click_sampler.py` / `module/click_profile.py` / `module/atom/*` / Control / 后端 / 任何 Asset。`RuleClick.coord()` 默认仍 `LEGACY_UNIFORM`。
- 上轮审计的两个 `random_click()` 历史问题（改共享 `Asset.name`、import-time 冻结）本轮**只记录不修**。

### Git

- 未 commit、未 push、未真机测试。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-02 - T7-1 Phase A Level C 验收准备（未跑真机）

### 本轮做了什么

本轮目标是「对 Phase A 做第一次 Level C 真机验收」，但按项目规则 + 本轮明确边界，**未自行启动 MuMu / 游戏 / OAS**，由用户手动准备环境。本轮只做静态准备：核对工作区状态（RD/RD2 asset、settlement profile、测试基线均与 Phase A 落地时一致，无漂移）、确认 BehaviorTrace 输出契约、新增只读验收分析器，并给出真机 runbook。等用户明确「环境已经准备好」后再执行真实任务并出验收报告。

### 新增 `dev_tools/settlement_trace_check.py`（只读，不接设备）

读 `log/behavior/<config>_<date>.jsonl`（BehaviorTrace v1，`Control.click` 已 `record('ACTION', action='click', target=control_name, extra={x,y})`），抽 `target in ("random_rd","random_rd2")` 的点击，做验收所需的客观检查：

- 坐标 sanity：每类 count / mean·min·max·分位 x·y、ROI-relative `(u, v)`（RD 用 `(699,397,574,314)`、RD2 用 `(1056,237,198,425)`）、落在 Safe ROI 内 / 外计数（profile `safe_margin` 从源码取）。
- 时序 / 状态：按相邻间隔 `>12s` 切「结算段」；每段第一个 RD → 之后第一个 RD2 的实测时间差（核对 ≈ ≥ `_SETTLEMENT_PRIMARY_OBSERVE_SECONDS`，`< 2s−0.15` 判 `observe_window_violation`）；同段 RD 出现 `>1` 次判 `multi_primary_segments`；某段第一个 RD2 之后又出现 RD 判 `sticky_violation`；连续 RD2 间隔 `< 0.30s` 判 `fast_rd2_gaps`。汇总 `auto_verdict` = FAIL / OK / NO_DATA。
- **不训练 profile**：程序点击是按当前参数生成的，只能验证「实现是否符合参数」，不能反向拟合个人热点（D014）。

### 测试

- `tests/test_settlement_trace_check.py`（新，13 用例）：解析过滤（只留结算 click、缺 xy 跳过、按 ts 排序）、`coord_stats`（ROI-relative、Safe ROI 内外、越界标记、空）、序列检查（健康序列 OK、observe / sticky / multi-primary / fast-RD2 各违规检出、`>12s` 切段、NO_DATA）。
- `compileall`：通过。完整回归 `550/550 OK`（旧 537 → 550，+13 = 本轮新测试）。
- `git diff --check`：本轮新文件干净；仅报告**用户 WIP** 的 `assets.py` / `gb/*.json` / `RyouToppa/dev/click.json` 行尾空格与 CRLF（`assets_extract.py` 生成格式），本轮不动。
- 未启动 MuMu / 游戏 / 设备 / OCR / 网络。

### 真机 runbook（交用户手动执行）

1. 待跑 config 的 `config/<name>.json` → `script.optimization.behavior_trace_enable` 改为 `true`（默认 `false`，进程启动时读一次，运行中不重载）。
2. 用户手动启动 MuMu → 游戏 → OAS，把游戏带到能跑 GeneralBattle 的状态（优先 RyouToppa：`run_general_battle(exit_matcher=I_TOPPA_RECORD)`，普通 config 走真实结算；RealmRaid 多数分支是 `build_quick_exit_config`，`_handle_result` 直接 EXIT、不进结算，只有最后一战走结算）。
3. 跑若干轮战斗，覆盖：普通 result、普通 reward（marker 命中）、（尽量）reward 后 2s 未推进的 fallback、result→reward 切换。
4. 回读 `log/<date>_<name>.txt`（每条 `Click (x, y) @ random_rd|random_rd2` 带毫秒时间戳）+ `log/behavior/<name>_<date>.jsonl`，跑 `toolkit\python.exe dev_tools\settlement_trace_check.py log\behavior\<name>_<date>.jsonl`。
5. `I_OVER_GHOST` / `I_GB_SKIN_CONFIRM` 用户当前无法稳定复现——不主动构造，自然出现则顺带观察，否则标 PASS_WITH_PENDING。

### Git

- 未 commit、未 push、未真机测试。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-02 - T7-1 Phase A 只读历史审计：Phase A 改造前的真实 settlement 流程

### 背景

Level C 前先查清「原项目在 RD/RD2 改造之前，战斗结算页到底怎么处理」，不用 Phase A 新逻辑反推旧行为。以 `HEAD 2cdf3a05`（= Phase A 前）对照当前工作树，只读（`git show HEAD:<path>` + `git diff HEAD`），未 checkout / reset / stash，未改任何文件。

### 确认的旧版事实

- `_handle_result`（HEAD:696-711）：清 `reward_no_battle_ts`、`is_win = not appear(I_FALSE, 0.8)`、必要时 `click_record_clear()`、**无条件** `_settlement_click(context)`、`return CONTINUE`。**不判断任何 Reward marker、没有分支。**
- `_handle_reward`（HEAD:713-731）：清 `reward_no_battle_ts`、`is_win = True`、`appear_then_click(I_OVER_GHOST, interval=0.8)`、`appear_then_click(I_GB_SKIN_CONFIRM, interval=0.8)`、必要时 `click_record_clear()`、**无条件** `_settlement_click(context)`、`return CONTINUE`。**旧版即使这一帧点中了特殊按钮，同帧仍会再做一次结算点击**——没有 early-return。
- `_settlement_click`（HEAD:547-555）：`settlement_click_timer` 门控 + `self.click(random_click())`。每帧被 handler 调，节流后约 0.8s 点一次。
- `random_click()`（`default_pages.py` HEAD:38-60）：默认 `ltrb=(True,False,True,False)` → 从 `[LEFT, TOP, RIGHT, BOTTOM]` 里 `random.choice` **只在 LEFT / RIGHT 二选一**；`low/high` 全仓无调用方（返回 list 分支是死代码）；`click.name = "SAFE_RANDOM_CLICK"` 直接改共享 Asset。
- **result 与 reward 在旧版是同一件事**：两者最终都进同一个 `_settlement_click` → 同一个 `random_click()`。没有「result 用右侧」、没有「Reward 才用主区域」。
- **Reward marker 只出现在 page recognizer 层**（`page_reward = Page(any_of(I_REWARD, I_GB_SKIN_CONFIRM, I_OVER_GHOST, I_REWARD_STATISTICS, I_REWARD_GOLD, I_REWARD_EXP_SOUL_4, I_REWARD_GOLD_SNAKE_SKIN, I_REWARD_PURPLE_SNAKE_SKIN, I_REWARD_SOUL_5, I_REWARD_SOUL_6, I_UI_REWARD)`），**不参与任何 handler 动作分流**。
- **`result → reward` 不是硬编码 transition**：`run_general_battle` 用 `detect_page_in`（纯识别、不触发 page hook），全仓无 `page_battle_result.connect(page_reward, ...)`。转移完全是「点一下当前结算页 → 真实 UI 变化 → 下一轮 `screenshot` + `detect_page_in` 重新识别」。
- `page_battle_result.add_enter_success_hooks(lambda _task: random_click())` 与 `page_reward.add_enter_success_hooks(handle_battle_reward_page)` 只在 `navigator.ui_goto` 路径触发，**不在 `run_general_battle` 的 FSM 循环里**。
- 旧版四边 ROI（HEAD）：`C_RANDOM_LEFT (17,104,55,370)`、`C_RANDOM_RIGHT (1185,115,79,388)`、`C_RANDOM_TOP (250,58,868,68)`、`C_RANDOM_BOTTOM (462,599,492,78)`；`I_REWARD (547,518,172,96)`。当前工作树的 LEFT/RIGHT/I_REWARD 变化与新增的 `C_RANDOM_RD`/`RD2` 都是**用户标注器 WIP**，不是 Phase A 代码改的（Phase A 生产改动只有 `general_battle.py` 一个文件）。
- subclass（`RealmRaid` / `HeroTest` / `Orochi` / `EvoZone` / `EternitySea` / `ActivityShikigami` / `BondlingFairyland` / `MoonSea` / `PeacockKingdom`）都没有硬编码 `result→reward`、都不用 Reward marker 选点击区域；只是插特殊弹窗处理、少数在 result 首帧提前 EXIT（RealmRaid quick_exit），或把最后的普通推进用 `random_click()` 直接写在自己 handler 里。
- RyouToppa 无 `_handle_result` / `_handle_reward` 覆写，`run_general_battle(config=..., exit_matcher=I_TOPPA_RECORD)` 走基类结算；旧代码没有「result 必须先出现 reward」的要求。

### 无法从源码判定的

`I_WIN` 亮的那一帧画面上是否已经同时有掉落 / 魂奖励面板——源码只证明两组 marker 是不同页面身份，视觉是否同帧共存需真实截图 / 运行验证。

### Git

- 本轮未修改任何文件。未 commit、未 push、未 checkout / reset / stash、未启动设备。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-02 - T7-1 Phase A 最终规格修正（Settlement Contract v1）

### 背景

上一轮历史审计确认：旧版 result 与 reward 本质是同一套「点当前结算阶段推进 UI」，且旧版 `_handle_reward` 点中特殊弹窗后**仍会继续本帧结算**。Phase A 的两处偏离据此修正，然后重新冻结、再进 Level C。本轮不扩到 Phase B / C。

### 修正一：result 从 direct-RD2 改为 RD primary

- `_handle_result`：`_advance_settlement(context, "result", reward_present=False)` → **`primary_enabled=True`**。result 现在与 reward 共用同一套 `primary once → 2s 观察 → sticky RD2 fallback`，并且**不检查任何 Reward marker**（与旧版一致）。
- `_advance_settlement` 参数 `reward_present` → **`primary_enabled`**（result 也有 primary，与 Reward 无关）；**状态机主体逻辑一行未改**，只是语义命名与文档纠正——没有复制第二套 result 专用状态机。
- 由此 `result RD → reward RD` 是**两个独立 stage 的 primary**，不是重复 primary；`result RD → 2s → result RD2 → reward RD` 同样合法（stage change 会重置 `settlement_primary_ts` / `settlement_fallback`）。

### 修正二：撤销 Phase A 新引入的特殊弹窗 early-return

`_handle_reward` 恢复 HEAD 逐句时序：删掉 `special_clicked` 变量、删掉「点中就 `context.settlement_primary_ts = None` + `return CONTINUE`」的早退分支，改回无条件 `appear_then_click(self.I_OVER_GHOST, interval=0.8)` / `appear_then_click(self.I_GB_SKIN_CONFIRM, interval=0.8)` 后继续本帧结算推进。**未新增任何 special gate / timer / FSM 状态 / retry / 额外 screenshot。**（本次编辑中一度误删 `context.is_win = True`，当轮即发现并补回。）

### 未改动

`C_RANDOM_RD` / `C_RANDOM_RD2` 的 ROI、两个结算 profile 的全部参数（`preferred` / `core_sigma` / `medium_sigma` / `weights` / `safe_margin` / `max_attempts`）、`_SETTLEMENT_PRIMARY_OBSERVE_SECONDS=2.0`、`settlement_click_timer`、`_settlement_click` / `_sample_settlement_click` / `_reset_settlement_stage` / `_sync_settlement_stage` / `_reward_marker_present`、`run_general_battle` 外层 FSM、`random_click()` 与四边资产、`ClickSampler` / `ClickProfile`、所有其它 task / subclass。

### `settlement_trace_check.py` 判定语义同步

旧判定假设「一段内只能有一个 RD、RD2 之后不能再有 RD」，与 Contract v1 冲突（`result: P F` → `reward: P` 是合法的）。修正：

- 删除 `sticky_violations` / `multi_primary_segments` 两个 **FAIL** 判定，改为信息性 `stage_boundary_candidates`（列出同段多次 RD 的时间戳 + 序列，注明需人工对照主日志的 page 变化）——BehaviorTrace 只有 `target`、看不到 stage，工具不该在这里替人判违规。
- `rd_to_rd2_gaps` 从「每段第一个 RD」改为**每个 RD → 其后第一个 RD2（中间无其它 RD）**，因此多 stage 段也能逐段量出观察窗口。
- 保留为 FAIL 的判定：`observe_window_violations`（间隔明显 < 2s）、`fast_rd2_gaps`（连续 RD2 < 0.3s）、Safe ROI 越界。
- 未新增任何分析能力。

### 测试

- `tests/test_general_battle_settlement.py`：32 → **40**。`ResultStageTest` 整组按新契约重写（首点 RD、首帧不 RD2、primary 至多一次、观察窗口内 RD/RD2 都不点、2s 后锁 fallback 转 RD2、fallback 后不回 RD、fallback 期 RD2 受 timer 节流、源码护栏 `_handle_result` 恒传 `primary_enabled=True` 且不引用 Reward marker）；新增 `test_result_rd_and_reward_rd_are_independent_stage_primaries`；`StageResetTest.test_result_to_reward_resets_and_reenables_primary` 改成真实的 `RD → 2s → RD2 → stage change → RD` 序列；`HandleRewardTest` 的两个「特殊按钮早退」用例改成「点中也不早退、不清状态」，新增「两个弹窗仍按原顺序无条件 `appear_then_click(interval=0.8)`」与「源码里无 `special_clicked` 早退」护栏。
- `tests/test_general_battle_timing.py`：16 → **16**。`test_result_uses_fallback_region_not_primary` → `test_result_uses_primary_region_first`（result 首点 RD、`settlement_primary_ts` 被设）；`test_result_and_reward_share_settlement_timer` 改为「result 点 RD 后 reward 首帧被同一 timer 节流跳过」。
- `tests/test_settlement_trace_check.py`：13 → **15**。删 `test_sticky_violation_detected` / `test_multi_primary_in_one_segment_detected`（锁的是已 supersede 的判定）；新增 `test_result_primary_then_reward_primary_is_not_a_violation`、`test_result_fallback_then_reward_primary_is_not_a_violation`、`test_gap_measured_per_primary_not_only_first`、`test_repeated_primary_is_listed_as_stage_boundary_candidate`；`test_healthy_reward_then_fallback_sequence` 改名 `test_healthy_primary_then_fallback_sequence`。
- 12 个受影响模块 import 冒烟通过；`compileall module/ tasks/ dev_tools/ tests/` 通过。
- 完整回归 `toolkit/python.exe -m unittest discover -s tests`：**560/560 OK**（550 → 560，净 +10 = settlement +8、trace-check +2、timing ±0）。
- `git diff --check`：本轮改动文件干净；仅既有 CRLF/LF 提示与用户 WIP 的 `assets.py` 行尾空格。
- 未启动 MuMu / 游戏 / 设备 / OCR。

### 生产影响

- **仅 `tasks/Component/GeneralBattle/general_battle.py`**：result 改走 RD primary、特殊弹窗恢复旧时序、`_advance_settlement` 参数改名 + 注释/docstring 纠正。其余生产代码零改动。
- Phase A 自动覆盖的 subclass 行为随之变化（result 首点从 RD2 变 RD）：`RealmRaid` / `HeroTest` / `Orochi` / `EvoZone` / `EternitySea` / `ActivityShikigami` / `BondlingFairyland._handle_reward`。
- Phase B / C 路径与所有带自定义 `ltrb` 的 `random_click()` 消费者仍完全未动。

### Git

- 未 commit、未 push、未真机测试。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-02 - T7-1 Phase A：Contract v1 → Contract v2（结算推进恢复 timer 驱动重复 RD）

### 背景：Contract v1 被真实结算 UI 流程推翻

用户结合真实游戏确认：旧版 GeneralBattle 每约 0.8 秒继续点一次结算，**不是机械重复点击**，而是一个完整战斗结算本来就需要多次推进——第 1 次点掉胜利/失败结算层、第 2 次推进御魂/奖励展示、第 3 次关闭奖励展示/退出结算。这些过程中 `page_battle_result` / `page_reward` 会连续多帧保持同一个语义 Page。因此 Contract v1 的「RD 只点一次 → 2 秒观察 → 仍是同一 stage = 推进失败 → sticky RD2」这个核心假设不成立。本轮把 Contract v1 全部相关约束 Superseded，恢复 Phase A 前成熟的「点击 → 下一帧重新识别 → 仍是 settlement 就 timer 到点后再点」节奏，只把 `random_click(LEFT/RIGHT)` 换成 `C_RANDOM_RD`、把固定 0.8s 换成每次随机 0.7~1.0s。

### 生产代码改动（唯一文件 `tasks/Component/GeneralBattle/general_battle.py`）

**删除（Contract v1 概念全部移除）**：

- `BattleContext` 三个字段 `settlement_stage` / `settlement_primary_ts` / `settlement_fallback`；`_reset_round_context` 里对应的 3 行重置。
- 方法 `_advance_settlement` / `_reset_settlement_stage` / `_sync_settlement_stage` / `_reward_marker_present`。
- 模块常量 `REWARD_MARKERS`（9 个 marker 元组）、`_SETTLEMENT_PRIMARY_OBSERVE_SECONDS = 2.0`。
- `run_general_battle` 主循环里的 `self._sync_settlement_stage(context, page)` 调用。

**改**：

- `SETTLEMENT_CLICK_INTERVAL_RANGE`：`(0.8, 0.8)` → `(0.7, 1.0)`。`_next_settlement_click_interval()` 本来就是每次调 `_sample_interval` → `random_delay(low, high)`（项目统一随机源），所以间隔天然每次重采，只改区间即可。
- `_settlement_click(context, rule, profile) -> bool` → **`_settlement_click(context) -> bool`**（回到 Phase A 前签名）：timer 到点就 `self._sample_settlement_click(self.C_RANDOM_RD, _SETTLEMENT_PRIMARY_PROFILE)`、重采间隔、`reset()`。不做任何 observe / same-page / fallback 判断。
- `_handle_result`：`_advance_settlement(context, "result", primary_enabled=True)` → `self._settlement_click(context)`。与 HEAD 旧版逐句一致（清 `reward_no_battle_ts`、`is_win = not appear(I_FALSE, 0.8)`、必要时 `click_record_clear()`、点、`return CONTINUE`），只是 `_settlement_click` 内部换了区域。
- `_handle_reward`：删掉 Contract v1 的 `primary_enabled=self._reward_marker_present()`，改为 `self._settlement_click(context)`。两个特殊弹窗 `appear_then_click(I_OVER_GHOST, interval=0.8)` / `appear_then_click(I_GB_SKIN_CONFIRM, interval=0.8)` 保持 HEAD 时序（无条件、不取返回值、不早退）。
- 模块头注释与 `_sample_settlement_click` / `_SETTLEMENT_FALLBACK_PROFILE` 注释改写为 Contract v2。

**保留**：`_SETTLEMENT_PRIMARY_PROFILE`（RD profile，参数一字未改）、`_SETTLEMENT_FALLBACK_PROFILE`（RD2 profile，参数未改，Contract v2 下**无生产消费者**、源码里除定义处零引用）、`C_RANDOM_RD2` Asset、`_sample_settlement_click(rule, profile)`（仍带参数，供未来 RD2 触发条件复用）、`import time`（`_handle_missing_battle_page` 等仍用 `time.time()` / `time.sleep`）。**不接 FrameState / FrameWait**——只保留 semantic page polling，FrameChanged 作为未来 RD2 触发候选记入 ROADMAP。

### RD2 当前生产消费者

**无。** `C_RANDOM_RD2` Asset 与 `_SETTLEMENT_FALLBACK_PROFILE` 都保留为预留 fallback region，等 Level C / FrameChanged 提供「点击后页面确实没推进」的真实证据后再定义触发条件；本轮明确不以「同一语义 Page 持续 2 秒」为自动触发。

### `dev_tools/settlement_trace_check.py` 简化

删除 Contract v1 判定（`rd_to_rd2_gaps` / `observe_window_violations` / `stage_boundary_candidates` / `fast_rd2_gaps` / `_OBSERVE_S` / `_SETTLEMENT_PRIMARY_OBSERVE_SECONDS` 导入）。保留 / 新增：

- RD/RD2 count / target / x·y / 分位 / ROI-relative `(u,v)` / Safe ROI 内外 / **`distinct_xy`**（多次点击应有多个不同坐标）。
- `click_intervals()`：每段内相邻结算点击的时间间隔汇总（`min/max/mean/p05/p50/p95`）+ `fast_repeat_gaps`（明显 `< _MIN_REASONABLE_GAP = 0.7*0.5 = 0.35s` 的高速重复）。注释说明「实际间隔因 polling/调度/截图 一般略大于配置的 0.7~1.0s，不检查上限」。
- `auto_verdict` FAIL 条件：高速重复 / Safe ROI 越界 / `count>=3` 且坐标全同 / `NO_DATA`。
- 未新增其它分析功能。

### 测试

- `tests/test_general_battle_settlement.py`：40 → **37**，按 Contract v2 重写。删掉所有 one-primary / 2s observe / sticky / stage reset / marker→region 用例；新增 timer 驱动重复节奏、每次重采间隔 `[0.72, 0.91, 0.78]`、每次重采坐标、`_settlement_click` 源码无 v1 token、`_handle_result`/`_handle_reward` 调 `_settlement_click(context)` 且 still-page 重复点、Contract v1 符号/字段/主循环调用全部消失、`SETTLEMENT_CLICK_INTERVAL_RANGE == (0.7, 1.0)` 且非 `(0.8, 0.8)`、RealmRaid 保留 `(0.65, 0.95)` 且其它 subclass 无 override、profile 参数未改、RD2 保留。
- `tests/test_general_battle_timing.py`：16 → **17**。`test_default_ranges_keep_old_values` → `test_default_ranges`（settlement 间隔在 `[0.7, 1.0]`）；新增 `test_settlement_interval_resampled_each_call`（每次 `random_delay(0.7, 1.0)`）；`_settlement_click` 相关 3 个用例改回单参签名；`test_result_uses_primary_region_first` → `test_result_uses_rd_region`（去掉已删的 `settlement_stage`/`settlement_primary_ts` 断言）。
- `tests/test_settlement_trace_check.py`：15 → **16**，按简化后接口重写。
- `compileall module/ tasks/ dev_tools/ tests/`：通过。
- 13 个受影响模块 import 冒烟通过；RD 采样 2000 次实测 distinct 1926、全在 Safe ROI 内、均值 ≈ `(1007, 565)`。
- 完整回归 `toolkit/python.exe -m unittest discover -s tests`：**559/559 OK**（560 → 559，净 -1 = settlement -3、timing +1、trace-check +1）。
- `git diff --check`：本轮改动文件干净；仅既有 CRLF/LF 提示与用户 WIP `assets.py`。
- 未启动 MuMu / 游戏 / 设备 / OCR。

### 生产影响

- **仅 `tasks/Component/GeneralBattle/general_battle.py`**：result 与 reward 都变成「timer 到点点一次 `C_RANDOM_RD`（HABIT + primary profile），不看 Reward marker，不做观察窗口 / fallback；间隔 0.7~1.0s 随机每次重采」。
- Phase A 自动覆盖的 subclass 随之（`RealmRaid` 非 quick_exit / `HeroTest` / `Orochi` / `EvoZone` / `EternitySea` / `ActivityShikigami` / `BondlingFairyland._handle_reward`）。
- Phase B / C 路径、所有带自定义 `ltrb` 的 `random_click()` 消费者、`random_click()` 本身、四边资产、`ClickSampler` / `ClickProfile` 默认、RD/RD2 profile 参数、RD/RD2 Asset ROI —— 全部未动。

### Git

- 未 commit、未 push、未真机测试。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-02 - T7-2：Point Target 连续尺寸适配（`adapt_point_profile`）

### 背景

用户决定 GeneralBattle Settlement 问题（`C_RANDOM_RD2` 未来触发条件需接 FrameChanged，暂无可靠方案）**冻结**，点击空间支线转向与 Settlement 无关的部分。本轮做 Point Target 的连续尺寸适配层：语义基础 Profile（控件足够大时完整表现的个人热点）+ 当前运行时 ROI → EffectiveProfile，取代 `if tiny / elif small / elif normal / elif large` 离散分类。**零生产消费者**。

### 生产改动（唯一文件 `module/click_profile.py`）

- 模块头 docstring 加 T7-2 段。import 加 `replace` / `Real`。
- 常量 `POINT_SIZE_MIN_PX = 24`、`POINT_SIZE_FULL_PX = 96`（provisional architecture constant，非用户配置；来自全仓 ROI 尺寸普查 §4.26 的描述性统计）。
- `_clamp01(value)`、`_roi_short_side(roi)`（`min(w, h)`；错误处理沿用 `ClickSampler._as_int_roi` 风格：非四元组 / 非数值 `w·h` → `ValueError`/`TypeError`，`w<=0 或 h<=0` → `ValueError`。**不 import `click_sampler`**——会成环，独立实现）。
- `point_size_factor(short_side) -> float`：`t = clamp((ss - 24) / (96 - 24), 0, 1)`；`3·t² - 2·t³`（smoothstep）。`≤24 → 0`、`≥96 → 1`、`60 → 0.5`。
- `adapt_point_profile(profile, roi) -> ClickProfile`：`f = point_size_factor(min(w,h))`；`effective_u = 0.5 + (base.preferred_u - 0.5) * f`（`v` 同）；`dataclasses.replace(profile, preferred_u=..., preferred_v=...)` 返回新 frozen profile，`profile` 不变。**只调 `preferred`**——`core_sigma` / `medium_sigma` / `weights` / `safe_margin` / `max_attempts` / `provisional` / `name` 全部原样保留（spread 与 preferred 是两个独立维度，小目标最终安全仍由 `ClickSampler` 的 Safe ROI + rejection + fallback 保证；AR 本轮不进算法，`short_side = min(w, h)` 已直接代表点击容错最窄方向）。公式对称——`base_u < 0.5` 向左平滑释放。

**未改**：`ClickProfile` 数据结构、`DEFAULT_PROFILES` 内容（`tiny` / `small` 不删）、`ClickProfileManager` / `resolve_profile`、`STRICT_MAX_CORE_SIGMA`、`module/click_sampler.py`、strategy API、`RuleClick.coord` / `module/atom/*`、Control / 后端、**任何 GeneralBattle / Settlement 代码**。

### 代表尺寸实测（脚本按公式算，非估计）

| short_side | factor | `normal_button` base (0.62,0.70) | `wide_card` base (0.68,0.53) |
|---|---|---|---|
| 8 / 24 | 0.0000 | `(0.5000, 0.5000)` | `(0.5000, 0.5000)` |
| 32 | 0.0343 | `(0.5041, 0.5069)` | `(0.5062, 0.5010)` |
| 40 | 0.1262 | `(0.5151, 0.5252)` | `(0.5227, 0.5038)` |
| 48 | 0.2593 | `(0.5311, 0.5519)` | `(0.5467, 0.5078)` |
| 60 | 0.5000 | `(0.5600, 0.6000)` | `(0.5900, 0.5150)` |
| 72 | 0.7407 | `(0.5889, 0.6481)` | `(0.6333, 0.5222)` |
| 80 | 0.8738 | `(0.6049, 0.6748)` | `(0.6573, 0.5262)` |
| 96 / 128 | 1.0000 | `(0.6200, 0.7000)` | `(0.6800, 0.5300)` |

与提示词 §14/§15 给的期望值一致（60px → normal ≈ (0.56, 0.60)、wide_card ≈ (0.59, 0.515)；96+ → base）。

### 测试

- `tests/test_click_profile.py` 44 → **65**（+21）：`PointSizeFactorTest`（6）—— 锚点 `(24,96)`、`≤24→0`、`≥96→1`、`60→0.5`、smoothstep 精确公式、`[0,1]` 且 200 点单调不减、两端一阶导为 0（近锚点增量 << 中段）；`AdaptPointProfileTest`（13）—— `short_side=min(w,h)`（`320×60` 与 `60×320` 同结果）、`normal_button` / `wide_card` 各代表尺寸精确 `(u,v)`、大 ROI 不超 base、小 ROI 不越中心反漂、随尺寸增大单调趋近 base、`base_u=0.30` 向左释放、base 不 mutate、返回新 frozen、spread + metadata 全不变、非法 ROI 抛 `ValueError`/`TypeError`、不调 RNG / 设备、`ClickSampler` 默认不变；`TinySmallNotUsedByAdaptationTest`（2）—— `adapt_point_profile` 源码无 `tiny`/`small`/`DEFAULT_PROFILES`/`if short`/`elif`、`tiny`/`small` 仍在 `DEFAULT_PROFILES`。
- `compileall module/ tasks/`：通过。
- 完整回归 `toolkit/python.exe -m unittest discover -s tests`：**581/581 OK**（559 → 581，净全部来自 `test_click_profile` 的 +21）。
- `git diff --check`：本轮两文件干净。
- 未启动 MuMu / 游戏 / 设备 / OCR——纯数学 / 架构组件，Level A。

### 生产影响

- **无。** `adapt_point_profile` / `point_size_factor` 当前**零消费者**，没有任何 `Rule*.coord()` 调它。生产点击仍全部 `LEGACY_UNIFORM`，唯一非 LEGACY 生产 opt-in 仍是 GeneralBattle Settlement RD（Contract v2，本轮完全未碰）。下一阶段再挑代表 target 显式 opt-in。

### 下一阶段最适合先 opt-in 的真实 target

- `normal_button` 语义：寮突破 / 各任务的「进攻」按钮（`RyouToppa` `I_FIRE` 运行时 ROI 已有只读 probe 工具，`runtime_roi_probe.py`）、`page_reward` 里的确认按钮类。
- `wide_card` 语义：契灵 / 结界卡片选择（`KekkaiUtilize` `C_AREA_*`、`Chess` `C_SHIKIGAMI_*`）。
- 均需先接真机采样 + Level C 验收，不在本轮。

### Git

- 未 commit、未 push、未真机测试。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-02 - T7-3.1：Point Semantic Profile 数据基线收口

### 背景

T7-3 只读审计（首批 Point Target opt-in 候选）发现 `DEFAULT_PROFILES` 里三个「个人先验」profile 的数据来源有问题：`wide_card (0.68,0.53)` / `normal_button (0.62,0.70)` 无法对任何版本的真实 ROI-relative 数据复现，只有 `large_area` 能对上它那簇（屏幕空间、Region 语义）。本轮收口数据基线，**只改 profile 数值 / 元数据 + 对应测试**，不动采样 / 适配算法、不接生产消费者、不碰已冻结的 GeneralBattle Settlement。

### 数据重算（用现有 manual click 原始数据，未采新样本）

- 数据源：`log/manual_click/yys1_2026-09-01.jsonl`（772 raw click），`dev_tools/manual_click_analyze.py` 的 `analyze(cluster_seeds=[(650,205),(675,390),(950,485)], cluster_labels=[cluster_A/B/C], exclude_calibration=True, cluster_roi={0: <C_AREA_1 ROI>})`。burst-collapse 772 → 444，启发式剔除开头 6 条窗口校准点击 → behavior_only 438 = cluster_A 107 + cluster_B 110 + cluster_C 221。
- **cluster_A（寮突破目标卡片）= 107 个 burst 独立落点**，屏幕 centroid `(641.0, 205.2)`。
- 对**当前 `RyouToppa.C_AREA_1` WIP RuleClick ROI** `(514,141,223,116)`（用户手动放大后的值）的 inside-only ROI-relative：inside **105 / 107**（outside 2 = `(507,5)` / `(492,10)`，屏幕左上角残留点）；`mean_uv = (0.582, 0.586)`、`median_uv = (0.579, 0.586)`、`std_uv = (0.128, 0.140)`；`p05/p25/p75/p95` u = `0.40 / 0.50 / 0.67 / 0.78`、v = `0.37 / 0.48 / 0.69 / 0.79`。
- 对照 **HEAD 版 `C_AREA_1` `(533,162,177,74)`**（更小）：inside **101 / 107**、`mean_uv = (0.627, 0.622)`、`median_uv = (0.622, 0.622)`、`std_uv = (0.155, 0.207)`。ROI 越小 → 相对散布越大、越多点判 outside → 说明 **preferred 数值依赖具体 ROI 定义版本，必须记录坐标基准**。
- **旧值 `(0.68, 0.53)` 来源已查明**：= cluster_A 屏幕 centroid `(641, 205)` 对**手工估的更大「完整可点卡片区」`(423, 142, 319, 118)`** 归一化——`u = (641-423)/319 = 0.683`、`v = (205.2-142)/118 = 0.536`。坐标基准是手工估的大框，不是真实消费的 `C_AREA_1` RuleClick ROI，不能直接喂 `adapt_point_profile(base, C_AREA_1.roi_front)`。

### 生产改动（唯一生产文件 `module/click_profile.py`）

- **`wide_card` preferred `(0.68, 0.53)` → `(0.58, 0.59)`**（对当前 `C_AREA_1` WIP ROI 的 `mean ≈ median`）。`core_sigma (0.16,0.16)` / `medium_sigma (0.26,0.24)` / `weights (0.75/0.20/0.05)` / `safe_margin (0.05,0.05)` **完全未改**（观察 `std ≈ (0.13,0.14)` 与 `core_sigma 0.16` 量级相符）。加中文注释写明来源、坐标基准、旧值为何不同、仍是单账号单次会话样本。
- **`normal_button` 加 `provisional=True`**（值 `(0.62, 0.70)` 未动）。注释写明：cluster_B（真进攻按钮）只有屏幕归一化 `mean (0.527, 0.545)`，`I_FIRE` 是 `RuleImage`（`match()` 后 `roi_front` 是模板尺寸框），没有可靠 runtime ROI-relative 数据；**本轮不重估**（禁止拿 screen-space / static ROI 猜 runtime relative），等 Level C `runtime_roi_probe --target I_FIRE` + manual click 一起标定。
- **`large_area` 加 `provisional=True`**（值 `(0.74, 0.67)` 未动）。注释写明：cluster_C 是多个战后页面混合的屏幕空间连点中心，无单一 ROI 基准，属 Region 语义；**禁止**用于 `adapt_point_profile` 的 Point Target opt-in；与 GeneralBattle `_SETTLEMENT_PRIMARY_PROFILE` 不是一回事、不合并。
- 结果：`DEFAULT_PROFILES` 8 个条目现**全部** `provisional=True`（`default` / `tiny` / `small` / `strict` 之前已标，本轮补 `wide_card` / `normal_button` / `large_area`）。
- 模块 docstring 更新：说明 T7-3.1 后全部 profile 标 `provisional`、各自原因，并强调 `provisional` 是纯文档标记、不被任何采样 / 适配逻辑读取。

**`provisional` 是纯元数据**：`ClickProfile.__post_init__` 不校验它、`ClickSampler` 的 HABIT/STRICT/UNIFORM 都不读它、`adapt_point_profile` 用 `dataclasses.replace` 原样透传。设置它**不改变任何采样行为**（`test_spread_and_metadata_unchanged` 锁）。

**未改**：`adapt_point_profile` / `point_size_factor` / `POINT_SIZE_MIN_PX` / `POINT_SIZE_FULL_PX` / `ClickProfile` 结构 / `ClickProfileManager` / `resolve_profile` / `STRICT_MAX_CORE_SIGMA` / 所有 `sigma`·`weights`·`margin` / `module/click_sampler.py` / strategy API / `module/atom/*` / `RuleClick.coord` / Control / 后端 / **任何 GeneralBattle / Settlement 代码**。未新增 `sigma_factor` / `spread_factor` / `tail_factor`（T7-4 暂缓）。未拆 `ProfileManager`（无 `PERSONAL_PROFILES` / `GENERIC_PROFILES` 分组）。

### 测试

- `tests/test_click_profile.py` 65 → **68**（+3）：`test_wide_card_normal_button_large_area_are_provisional`、`test_every_default_profile_is_provisional`、`test_wide_card_c_area_1_wip_roi_lands_at_base_hotspot`（`C_AREA_1` WIP ROI short_side 116 ≥ 96 → factor 1 → effective == base `(0.58,0.59)`）。改 2 处：`test_wide_card_representative_sizes` 重写为新基线 `(0.58,0.59)`（ss=24→`(0.5,0.5)`、ss=60→`(0.54,0.545)`、ss=96→`(0.58,0.59)`、ss=200 clamp）；`test_builtin_profiles_all_valid_and_category_differences_kept` 的 `provisional` 循环从「`wide_card`/`normal_button`/`large_area` assertFalse」翻成 7 个名字全 `assertTrue`。`AdaptPointProfileTest.WC` 类属性注释同步。
- `tests/test_general_battle_settlement.py`：`test_random_click_default_ltrb_unchanged` → `test_random_click_signature_not_touched_by_t7_line`，断言从 `(True,False,True,False)` 跟随当前工作树改为 `(False,False,True,False)`。**原因**：跑基线时该测试 RED——用户 2026-09-02 在 `tasks/GameUi/default_pages.py` 把 `random_click` 的默认 `ltrb` 从 `(T,F,T,F)`（LEFT+RIGHT）改成 `(F,F,T,F)`（仅 RIGHT），是用户自己的 WIP，与 T7 / Settlement 支线无关。护栏意图是「本支线不碰 `random_click` 签名」，因此改为跟随当前值 + 注释说明来历，不锁死历史值。计 37 用例不变。
- `compileall module/click_profile.py tests/test_click_profile.py tests/test_general_battle_settlement.py`：通过。
- 完整回归 `toolkit/python.exe -m unittest discover -s tests`：**584/584 OK**（581 → 584，净 +3 全来自 `test_click_profile`）。注：基线其实是 580 pass + 1 fail（上述 RED 测试），修 guard 后 581，再 +3 = 584。
- `git diff --check`：本轮改动文件干净（既有 `tasks/Component/GeneralBattle/assets.py` 的 upstream 行尾空格提示与本轮无关）。
- 未启动 MuMu / 游戏 / 设备 / OCR——纯数值 / 元数据 + 测试，Level A。

### 生产影响

- **无。** 只有 `wide_card` preferred 从 `(0.68,0.53)` 变 `(0.58,0.59)`，但 `wide_card`（连同整个 `adapt_point_profile` / HABIT / `DEFAULT_PROFILES`）**零生产消费者**——没有任何 `Rule*.coord()` 或调用点引用它。加 `provisional` 是纯文档标记。生产点击仍全部 `LEGACY_UNIFORM`，唯一非 LEGACY 生产 opt-in 仍是 GeneralBattle Settlement RD（Contract v2，本轮完全未碰）。

### 下一步（无需设备也能做的）

- T7-4：`adapt_point_profile` 加 spread / sigma 的尺寸适配（小 ROI 上 `core_sigma` 相对占比过大是生产 opt-in 前必须解决的问题，T7-3 审计已确认）——本轮明确暂缓、未动。
- 大尺寸点击 ROI 人工审查目录 `large_click_roi_review.md` 逐条 `review_status` 人工确认（第 3 阶段挑代表 target 的直接输入）。
- 需要设备的：`runtime_roi_probe --target I_FIRE` 采真进攻按钮运行时 ROI（`normal_button` 标定前置）、Phase A Contract v2 Level C 验收。

### Git

- 未 commit、未 push、未 merge、未真机测试。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-02 - T7-3.2：首个普通 Point Target 生产 opt-in（`RyouToppa.C_AREA_1`）

### 背景

T7-1 / T7-2 / T7-3 / T7-3.1 之后，点击空间模型的能力（`ClickSampler` 策略、`ClickProfile`、`adapt_point_profile`）已就绪且静态验证过，但除 GeneralBattle Settlement RD 外没有任何**普通 Point Target** 走非 `LEGACY_UNIFORM`。本轮把 `RyouToppa` 目标区域 1（`C_AREA_1`）作为**首个且本轮唯一**的普通 Point Target 显式生产 opt-in：`LEGACY_UNIFORM` → `wide_card` → `adapt_point_profile` → `ClickSampler` HABIT。**Point Target 生产消费者 0 → 1。仍需 Level C 真机验收。**

### C_AREA_1 原调用链

`area_map`（`script_task.py` 模块级 tuple）index 0 → `{'rule_click': RyouToppaAssets.C_AREA_1, ...}`（`RuleClick(roi_front=(514,141,223,116), name="area_1")`）。两处业务点击：

1. `ScriptTask.attack_area(index)`：`rcl = area_map[index].get("rule_click")` → `self.click(rcl)`；
2. `ScriptTask._reopen_area_after_fire_disappear(index)`：`self.click(area_map[index].get('rule_click'))`。

两处都对 index 0~7 通用 → `BaseTask.click` → `x, y = click.coord()`（`RuleClick.coord()` = `ClickSampler.sample(self.roi_front)` = `LEGACY_UNIFORM`）→ `self.device.click(x, y, control_name="area_1")` → `Control.click` 记录 BehaviorTrace `target="area_1"`。`_area_content_recognizable` 只读 `rule_click.roi_front` 做图像 std 判断，不点击、不受影响。

### 新调用链

两处调用点改成 `self._click_toppa_area(index)`（新私有方法）：

```
_click_toppa_area(index):
    rule = area_map[index]['rule_click']
    if rule is self.C_AREA_1:                       # 逐调用点身份守卫
        x, y = ClickSampler.sample_point(rule.roi_front, DEFAULT_PROFILES['wide_card'])
        self.device.click(x=x, y=y, control_name=rule.name)
    else:
        self.click(rule)                            # C_AREA_2..8 原样 LEGACY_UNIFORM
```

`ClickSampler.sample_point(roi, base_profile)` = 新增薄组合入口：`adapt_point_profile(resolve_profile(base_profile), roi)` 再 `ClickSampler.sample(roi, strategy=HABIT, profile=effective)`。

### helper / API 放在哪里、为什么不进 BaseTask

- **坐标产生**：`ClickSampler.sample_point`（`module/click_sampler.py`）。`ClickSampler` 是 D014 定义的「最终点击 x/y 空间随机的唯一公共入口」，`sample_point` 是 `adapt_point_profile` + `sample(strategy=HABIT)` 的 3 行组合，放这里语义正确、第 3 阶段其它 Point opt-in 也复用同一个公式（不各写各的）。
- **点击发送**：`RyouToppa` 私有 `_click_toppa_area`。它需要 `self.device`（`ClickSampler` 没有设备），且身份守卫是 RyouToppa 特有逻辑。
- **没有塞进 `BaseTask`**：`BaseTask` 已是 god class，长期约束是不再往里加方法（`docs/DECISIONS.md` D014 扩展）。没有做 `BaseTask.point_click(rule, profile)`。也没有让 `self.click` / `BaseTask.click` 自动识别 `wide_card` / `normal_button`——`self.click` 语义完全没动。
- **一个消费者 = 一个最小、可回滚的显式 opt-in**：没有为「以后可能复用」提前造框架。

### 尺寸适配当前不收缩（预期）

`C_AREA_1.roi_front = (514,141,223,116)` → `short_side = min(223,116) = 116`。`POINT_SIZE_FULL_PX = 96`，`116 ≥ 96` → `point_size_factor(116) = 1.0` → `adapt_point_profile` 后 `effective.preferred == wide_card` base `(0.58, 0.59)`，**不向中心 `(0.5,0.5)` 收缩**。接了 `adapt_point_profile` 但当前区域够大，这是预期行为；将来若 ROI 变小才会收缩。

### spread 不改

effective profile 的 `core_sigma (0.16,0.16)` / `medium_sigma (0.26,0.24)` / `weights (0.75/0.20/0.05)` / `safe_margin (0.05,0.05)` / `max_attempts 12` / `provisional` / `name` 全部 == base（`adapt_point_profile` 只调 `preferred`）。**未做 T7-4**——没加 `spread_factor` / `sigma_factor` / `tail_factor`。实测 `C_AREA_1` ROI + `wide_card`：20000 次采样 `_fallback_point` 命中 **0 次**（rejection 不是问题），mean ≈ 屏幕 `(640,208)` ≈ 热点 `(643,209)`，Safe ROI `(525,147,201,104)`，每次点击独立重采（distinct ≈ 3973/5000）。

### 生产改动

- `module/click_sampler.py`：import 加 `adapt_point_profile`；加 `ClickSampler.sample_point(roi, base_profile=None)` 静态方法（薄组合，不自己写死热点 / spread / 尺寸分档）；模块 docstring 的「非 LEGACY 策略消费者」段更新（HABIT 现有 Settlement RD + `RyouToppa.C_AREA_1` 两个）。
- `tasks/RyouToppa/script_task.py`：import 加 `ClickSampler` / `DEFAULT_PROFILES`；加私有 `_click_toppa_area(index)`；`_reopen_area_after_fire_disappear` 与 `attack_area` 两处 `self.click(<area rule>)` → `self._click_toppa_area(index)`；删掉 `attack_area` 里因此变死的 `rcl = ...` 局部变量。（该文件另有更早轮次的用户 WIP：`secrets` 移除、`random_delay` 改 import、`begin_fatigue_task` / `try_fatigue_break`——与本轮无关。）
- **未改**：`RuleClick/RuleImage/RuleOcr/RuleGif/RuleLongClick` 的 `coord` / `ClickSampler.sample` 默认策略 / `adapt_point_profile` / `point_size_factor` / `DEFAULT_PROFILES` 内容 / `ClickProfile` / `BaseTask.click` / `Control` / minitouch / 后端 / `normal_button`（仍 `provisional`、生产零消费者）/ `I_FIRE` / **任何 GeneralBattle Settlement 代码**。

### 护栏测试语义纠正（`random_click` RIGHT-only）

用户明确：`tasks/GameUi/default_pages.py` 的 `random_click` 默认 `ltrb = (False, False, True, False)`（RIGHT only，从历史 `(True, False, True, False)` = LEFT + RIGHT 改来）是**用户本人有意的业务修改**，不是来源不明 WIP。据此把 `tests/test_general_battle_settlement.py` 的 `test_random_click_signature_not_touched_by_t7_line` → `test_random_click_default_right_only_intentional_baseline`，断言 `(False, False, True, False)` + 注释「这是用户现有业务改动，T7 / 点击空间支线不得恢复历史 LEFT + RIGHT 默认值」。不审计 / 不改 `random_click` 其它消费者，只纠正护栏语义。用例数 37 不变。

### 测试

- 新增 `tests/test_ryoutoppa_c_area_1_point_opt_in.py`（**25 用例**，`ScriptTask.__new__` + `SimpleNamespace(click=Mock())`，纯静态）：
  - 调用链——`_click_toppa_area(0)` → `sample_point(C_AREA_1.roi_front, DEFAULT_PROFILES['wide_card'])` → `device.click(x, y, control_name='area_1')`；最终走 `self.device.click`（不是 minitouch/adb）；`control_name` 恒 `rule.name` 且不是 `wide_card`/`point_click`/`habit`/`sample_point`；不打桩时多次点击坐标不复用（>50 distinct / 400）且全在 Safe ROI `(525,147,201,104)` 内。
  - 尺寸适配——`roi_front == (514,141,223,116)`、`min(w,h)==116`、`point_size_factor(116)==1.0`、`adapt_point_profile` 后 `preferred==(0.58,0.59)`、name/sigma/weights/margin/max_attempts/provisional 全 == base；`sample_point` 把 `strategy=="habit"` + effective profile 喂给 `ClickSampler.sample`。
  - `wide_card` 参数冻结锁（preferred / σ / weights / margin / max_attempts / provisional）。
  - C_AREA_2..8 未迁移——`_click_toppa_area(1)` 不调 `sample_point`、走 `self.click` → `ClickSampler.sample((C_AREA_2.roi_front,))` 无 strategy/profile（LEGACY）、`control_name='area_2'`；index 1~8 全部不走 Point 路径且 `is not C_AREA_1`；8 个 `C_AREA_*` 都是 `RuleClick`。
  - opt-in 唯一且受限——`_click_toppa_area` 源码有 `if rule is self.C_AREA_1:` + `else: self.click(rule)`；`script_task.py` 全文 `.sample_point(` 恰 1 处；`tasks/` 下只有 `RyouToppa/script_task.py` 消费 `sample_point`。
  - 未改——`RuleClick.coord` 源码仍只 `ClickSampler.sample(self.roi_front)` 无 strategy/HABIT/sample_point；`ClickSampler.sample` 默认 `LEGACY_UNIFORM` 且不 resolve profile；`sample_point` 是薄 wrapper（有 `adapt_point_profile`+`STRATEGY_HABIT`、无 `if short`/`elif`/`tiny`/`small`/写死 preferred）；`normal_button` 仍 `provisional` 且 `tasks/`·`module/` 生产代码零引用；`I_FIRE` 仍 `RuleImage` 且 `RyouToppa` 未把它接进 Point 采样；Settlement Contract v2 常量完好。
- `tests/test_general_battle_settlement.py`：护栏测试改名 + 断言（见上），37 不变。
- `compileall module/click_sampler.py tasks/RyouToppa/script_task.py tests/test_ryoutoppa_c_area_1_point_opt_in.py tests/test_general_battle_settlement.py`：通过。
- 完整回归 `toolkit/python.exe -m unittest discover -s tests`：**609/609 OK**（584 → 609，净 +25 全来自新测试文件）。
- `git diff --check`：本轮改动文件干净（既有 `tasks/Component/GeneralBattle/assets.py` upstream 行尾空格提示与本轮无关）。
- 未启动 MuMu / 游戏 / OAS / 设备 / OCR——Level A 静态生产接入，真实落点效果等 Level C。

### 生产影响

- **`RyouToppa.C_AREA_1` 的点击坐标产生方式改变**：由 ROI 内均匀 → `wide_card` 个人热点 `(0.58,0.59)` 附近的三成分 HABIT 分布（当前 ROI 够大，`preferred` 不收缩）。点击**发送**方式（`self.device.click` + `control_name="area_1"`）、BehaviorTrace 记录（`target="area_1"`）、页面推进逻辑全不变。
- `C_AREA_2..8` 与所有其它 `RuleClick` / `random_click` 消费者、GeneralBattle Settlement、`normal_button` / `I_FIRE`：**零变化**。
- Point Target 生产消费者：**0 → 1**（`RyouToppa.C_AREA_1`）。

### 回滚点

删 `_click_toppa_area`、两处调用点还原成 `self.click(area_map[index].get('rule_click'))` / `self.click(rcl)`（恢复 `rcl` 局部变量）、删 `ClickSampler.sample_point` 及其 import → 完全回到 T7-3.1 状态（`sample_point` 无其它消费者）。

### 下一步

- Level C：`C_AREA_1` 点击后开 `behavior_trace_enable=true` 跑 `RyouToppa`，核对 `log/behavior/*.jsonl` 里 `target="area_1"` 落点集中在 ROI 相对 `(0.58,0.59)` 附近、全在 Safe ROI 内、每次不同；对照 `area_2..8` 仍全 ROI 均匀。
- 无设备时可继续：T7-4 spread 适配（仍是后续增强项，非首批接入硬前置）；`large_click_roi_review.md` 人工确认；第 3 阶段其余代表 target（需先 T7-4 + `normal_button` 真机 ROI）。

### Git

- 未 commit、未 push、未 merge、未 reset、未 stash、未真机测试。分支 `master`，HEAD 仍为 `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-02 - T7-4：Point Target spread 连续尺寸适配

### 背景

T7-2 的 `adapt_point_profile` 只把 `preferred` 按 `size_factor` 拉回中心，`core_sigma` /
`medium_sigma` / `tail_weight` 仍保持大按钮 base 的比例——小目标热点回中心了，但分布宽度
没有一起变保守。T7-4 在**不新增第二条尺寸曲线**的前提下，让**同一个** `size_factor` 同时
驱动 spread / tail 的连续收敛。纯 `ClickProfile` 数学，不新增生产消费者、不改 `C_AREA_1`
调用链 / `sample_point` API / 任何 `Rule*.coord()` / GeneralBattle Settlement。

### small-target spread anchor 的选择（先审计现成 profile）

审计 `DEFAULT_PROFILES` 里 4 个保守 profile 的离散度参数：

| profile | core σ (u,v) | medium σ (u,v) | tail_w | 语义 |
|---|---|---|---|---|
| default | (0.10, 0.10) | (0.18, 0.18) | 0.02 | 未匹配类别的 fallback |
| small | (0.09, 0.08) | (0.14, 0.12) | 0.01 | 「小目标」 |
| tiny | (0.06, 0.06) | (0.10, 0.10) | 0.0 | **「极小目标，离散度最窄、无 tail」** |
| strict | (0.05, 0.05) | (0.09, 0.09) | 0.0 | STRICT 策略专用窄 profile（受 `STRICT_MAX_CORE_SIGMA` 约束） |

**选 `tiny` 的 σ 作锚点**：它是 `DEFAULT_PROFILES` 里语义正好对应「Point Target 最小尺寸」
的一档，`core σ 0.06` 保守但不退化（不趋近 0，最终安全仍靠 Safe ROI），本身已 `tail=0`
（与「factor=0 → tail=0」自洽）。`strict` 更窄（0.05）但语义绑定 STRICT 策略、不是通用
Point 语义，不选。不为 T7-4 另拍一组新数字。

落成模块常量（`click_profile.py`，带审计依据注释）：
`POINT_MIN_CORE_SIGMA_U = POINT_MIN_CORE_SIGMA_V = 0.06`、
`POINT_MIN_MEDIUM_SIGMA_U = POINT_MIN_MEDIUM_SIGMA_V = 0.10`。
`test_point_min_spread_anchor_matches_tiny_profile` 锁「常量 == `tiny` 的 σ」这条依赖。

### 生产改动（唯一生产文件 `module/click_profile.py`）

- 新常量 `POINT_MIN_*_SIGMA_*`（见上）。
- 新 `_lerp(lo, hi, t) = lo*(1-t) + hi*t`——**端点精确**：`t=0.0` 返回恰好 `lo`、`t=1.0`
  返回恰好 `hi`（端点处一个乘子恰为 `0.0` / 一个恰为 `1.0`，无浮点舍入）。这是
  `f=1` 时 EffectiveProfile 能逐字段等于 base 的关键。
- `adapt_point_profile` 的 `replace(...)` 从「只 `preferred_u/v`」扩展为同时：
  - `preferred_u/v = 0.5 + (base - 0.5) * f`（**公式完全没改**，T7-2 逐字保留）
  - `core_sigma_u/v = _lerp(POINT_MIN_CORE_SIGMA_*, base.core_sigma_*, f)`
  - `medium_sigma_u/v = _lerp(POINT_MIN_MEDIUM_SIGMA_*, base.medium_sigma_*, f)`
  - `tail_weight = base.tail_weight * f`
  - `core_weight = base.core_weight + base.tail_weight * (1 - f)`（**被削掉的 tail 权重整体
    回补到 core**）
  - `medium_weight` **不传入 `replace`** → 保持 base 值（本轮 medium_weight 不做任何曲线）
- `safe_margin_u/v` / `max_attempts` / `provisional` / `name` **仍原样透传**——Safe ROI 是
  `ClickSampler` 的硬安全边界（职责与分布形状独立），不随尺寸缩放；不做 `margin_factor` /
  dynamic Safe ROI。
- 模块 docstring 更新（T7-2/T7-4 三件事、锚点、端点精确、C_AREA_1 factor=1 不受影响）。

**权重不变量**：`core + medium + tail` = `base_core + base_tail·(1-f) + base_medium +
base_tail·f` = base 三成分之和（所有 base profile 都是 1.0）。非负（各项 ≥ 0）。不新增第
四个 mixture 成分。`__post_init__` 校验（σ≥0、weight≥0、和>0、margin∈[0,0.5)）对所有
`f∈[0,1]` 都通过。

**未改**：`point_size_factor` / smoothstep 公式 / `POINT_SIZE_MIN_PX` / `POINT_SIZE_FULL_PX` /
`preferred` 公式 / `ClickProfile` 结构 / `ClickSampler` / `sample_point` / strategy API /
`DEFAULT_PROFILES` 数值 / `ClickProfileManager` / `resolve_profile` / `tasks/RyouToppa/*` /
GeneralBattle。未加 `spread_factor` / `sigma_factor` / `tail_factor`（继续只有一个
`size_factor`）。未给 `sample_point` / 调用方加 `spread=` / `adaptive_sigma=` 开关。

### 数学性质（脚本按公式算，非采样统计）

- `f = 0`（`short_side ≤ 24`）：`preferred = (0.5, 0.5)`、`core σ = (0.06, 0.06)`、
  `medium σ = (0.10, 0.10)`、`tail_weight = 0.0`、`core_weight = base_core + base_tail`、
  `medium_weight = base_medium`。
- `f = 0.5`（`short_side = 60`）代表值：
  - `normal_button` → preferred (0.56, 0.60)、core σ 0.095、medium σ 0.16、w (0.80, 0.18, 0.02)
  - `wide_card` → preferred (0.54, 0.545)、core σ 0.11、medium σ (0.18, 0.17)、w (0.775, 0.20, 0.025)
- `f = 1`（`short_side ≥ 96`）：EffectiveProfile 的**每个 dataclass 字段都逐字等于 base**
  （`normal_button` / `wide_card` / `default` / `large_area` / `small` 全验证过），只有对象
  identity 是新实例。
- 代表尺寸表（`normal_button` base core σ 0.13 / medium σ 0.22 / w 0.78·0.18·0.04）：

  | ss | factor | preferred | core σ | medium σ | (core_w, med_w, tail_w) |
  |---|---|---|---|---|---|
  | ≤24 | 0.0000 | (0.5000, 0.5000) | 0.0600 | 0.1000 | (0.8200, 0.1800, 0.0000) |
  | 32 | 0.0343 | (0.5041, 0.5069) | 0.0624 | 0.1041 | (0.8186, 0.1800, 0.0014) |
  | 40 | 0.1262 | (0.5151, 0.5252) | 0.0688 | 0.1151 | (0.8150, 0.1800, 0.0050) |
  | 48 | 0.2593 | (0.5311, 0.5519) | 0.0781 | 0.1311 | (0.8096, 0.1800, 0.0104) |
  | 60 | 0.5000 | (0.5600, 0.6000) | 0.0950 | 0.1600 | (0.8000, 0.1800, 0.0200) |
  | 72 | 0.7407 | (0.5889, 0.6481) | 0.1119 | 0.1889 | (0.7904, 0.1800, 0.0296) |
  | 80 | 0.8738 | (0.6049, 0.6748) | 0.1212 | 0.2049 | (0.7850, 0.1800, 0.0350) |
  | 96 / 116 / 128 | 1.0000 | (0.6200, 0.7000) | 0.1300 | 0.2200 | (0.7800, 0.1800, 0.0400) |

  `wide_card` 类似：`ss≤24` → preferred (0.5,0.5) / core σ 0.06 / medium σ 0.10 / tail 0 /
  core_w 0.80；`ss≥96` → 逐字段 base（preferred (0.58,0.59) / core σ 0.16 / medium σ
  (0.26,0.24) / w (0.75,0.20,0.05)）。

- **30px 小按钮 spread 缩小幅度**（40×30，`short_side = 30`，如 `C_DOKAN_REFRESH` 形状，
  **仅数学示例、不接生产**）：以 `normal_button` 为 base，`f ≈ 0.0197` →
  `core_sigma_u ≈ 0.0614`（**≈ base 0.13 的 47%，即收窄约 53%**）、`medium_sigma_u ≈ 0.102`
  （base 0.22）、`tail_weight ≈ 0.0008`（base 0.04，≈ 0）、`preferred ≈ (0.502, 0.504)`
  （base (0.62, 0.70)，贴近中心）。

### 测试（`tests/test_click_profile.py` 68 → 87，+19；纯参数断言，不靠随机统计）

- `AdaptPointProfileTest`：删旧的 `test_spread_and_metadata_unchanged`（T7-4 后 sigma/tail
  会变，前提不再成立），拆成 `test_safe_margin_and_metadata_pass_through_unchanged`
  （`safe_margin`/`max_attempts`/`provisional`/`name` 任意尺寸不变）与
  `test_medium_weight_never_changes`（medium_weight 恒 == base）。
- 新 `PointSpreadAnchorTest`（2）：锚点 == `tiny` 的 σ；锚点比各 base 窄但 `> 0`。
- 新 `PointSpreadAdaptationTest`（16）：factor=0 σ=锚点 / tail=0 / preferred=center / 削掉的
  tail 回补 core；factor=1 逐字段 == base（多个 base）+ 大 ROI clamp；sigma 与 tail 随 ss
  单调、夹在锚点与 base 之间；24→25 / 40→41 / 95→96 无折点；权重和守恒且非负；
  `normal_button` / `wide_card` 代表尺寸表精确值；30px 小按钮示例（σ < 60% base、tail < 0.005、
  preferred 贴中心）；base 不 mutate、结果 frozen；**`C_AREA_1` `(514,141,223,116)` →
  EffectiveProfile 逐字段 == `wide_card` base**。
- `tests/test_ryoutoppa_c_area_1_point_opt_in.py`：`test_effective_profile_keeps_spread_and_metadata`
  → `test_effective_profile_is_byte_for_byte_wide_card_base`，用 `dataclasses.fields` 全字段
  比对（含 T7-4 后仍会随尺寸变的 sigma/tail），docstring 相应更新。用例数 25 不变。
- `TinySmallNotUsedByAdaptationTest.test_adapt_point_profile_source_has_no_discrete_size_branch`：
  仍通过——`adapt_point_profile` 源码用 `_lerp` + `POINT_MIN_*` 常量，无 `tiny`/`small`/
  `DEFAULT_PROFILES`/`if short`/`elif` 字样（docstring 也避开）。
- `compileall module/`：通过。
- 完整回归 `toolkit/python.exe -m unittest discover -s tests`：**628/628 OK**（609 → 628，
  净 +19 全来自 `test_click_profile`）。
- `git diff --check`：干净。
- 未启动 MuMu / 游戏 / OAS / 设备 / OCR——纯参数变换，Level A。

### 生产影响

- **无。** `adapt_point_profile` 的唯一生产消费者 `RyouToppa.C_AREA_1`：`short_side = 116 ≥
  96` → `size_factor` 恰为 `1.0` → EffectiveProfile 逐字段等于 `wide_card` base，T7-4 前后
  `C_AREA_1` 落点分布完全一致（`test_c_area_1_effective_profile_identical_to_wide_card_base`
  + `test_effective_profile_is_byte_for_byte_wide_card_base` 双锁）。
- 其余普通 Point Target 仍**零生产消费者**；`normal_button` / `I_FIRE` 未接；`C_AREA_2..8`
  仍 `LEGACY_UNIFORM`；GeneralBattle Settlement（Region Target，不走 `adapt_point_profile`）
  完全未碰；`random_click` 默认 RIGHT-only 有意基线护栏未动。

### 回滚点

`adapt_point_profile` 的 `replace(...)` 只保留 `preferred_u/v` 两行、删掉 4 个 sigma 行与
2 个 weight 行、删 `_lerp` 与 `POINT_MIN_*` 常量、还原 3 个测试文件的相应用例 → 回到
T7-3.2 状态。

### 下一步

- Level C（需设备）：仍是 `C_AREA_1` 真机落点验收（T7-4 不改变其预期，验收项同 §4.31）。
- 无设备可做：第 3 阶段挑其余代表 Point Target opt-in（小 ROI 目标现在 spread 也会自适应
  收敛，不再是「热点回中心但分布仍偏宽」）；`normal_button` 仍需真机 `runtime_roi_probe
  --target I_FIRE` 才能标定后接入。

### Git

- 未 commit、未 push、未 merge、未 reset、未 stash、未真机测试。分支 `master`，HEAD 仍为
  `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-02 - Kekkai 状态机静态收口（KekkaiActivation / KekkaiUtilize）

### 背景

回到 OAS 状态驱动主线。此前已完成 FrameStateDetector（§4.16）/ FrameState Wait Layer
（§4.18，D012）/ `BaseTask.list_find` 迁移前静态收口（§4.19，D013）。本轮对
`KekkaiActivation` + `KekkaiUtilize` 做**同样性质的迁移前静态收口**——只读审查 + 建模 +
characterization，**不把 Kekkai 真正接入 FrameWait**，不改任何 Kekkai 生产行为。对应
ROADMAP T4-4（`harvest_card` 状态化）/ T5-1（`swipe_adb` trace）/ T5-2 后半 的准备。

### 产出

- `docs/Kekkai状态机静态收口.md`（专题文档）：两个任务的完整文本状态图、State Matrix
  （KA 11 状态 / KU 10 状态）、`harvest_card` 逐步拆解 + pilot 评估、三处列表 swipe 对照
  （`list_find` / KA `check_card_num` / KU `perform_swipe_action`）、Semantic vs Visual Wait
  迁移矩阵、Loop/Retry 三分类（bounded / state-bounded / potentially unbounded）、
  Existing Issue Register（12 条 R-A* / R-U*）、迁移候选 A/B/C/D、与 `list_find` 的
  primitive 共享分析。
- `tests/test_kekkai_activation_state.py`（18 用例）、`tests/test_kekkai_utilize_state.py`
  （23 用例）：纯 mock characterization，锁现状不锁应然。

### 关键现状（源码逐行核实）

- **`harvest_card`**：线性 8 次无参 `appear_then_click(I_A_HARVEST_*)`，8 步之间无
  `screenshot` / `sleep` / 循环 / `if` / `return`。`appear_then_click` 无 `interval` 时不
  截图 → 8 次全匹配同一帧（上一步 `goto_page` 留下的）。无验证、无 reward popup 闭环，
  返回 `None`。ROADMAP T4-4 desc 里「每次 `appear_then_click` 前有 `screenshot`」是**未来
  目标**，不是现状。
- **KA `check_card_num`**（覆写 KU 版）：返回 `RuleClick`（`name='tmpclick'`）或 `None`。
  `while 1` + `ocr_count > 3` **有界**（≈4 OCR + 3 swipe）。swipe = stdlib `random.randint`
  + `swipe_adb((rx∈[200,400], ry∈[580,600]), (rx, ry-410), duration=2)` + `sleep(1)`。
- **KU `perform_swipe_action`**：公共 `random_int` + `swipe_adb((rx∈[340,600],
  ry∈[500,565]), (rx, ry-SWIPE_DISTANCE=416), duration=2)` → `click_record_clear` →
  `sleep(2)`。调用方 `range(20|21)` + `Timer(120)` 双界。
- 两处列表 swipe 都用 `self.device.swipe_adb` 直连，**绕过 `Control.swipe`** → 不进
  BehaviorTrace、无 `distance_check`、无 `_invalidate_image_batch_cache`（`control.py:189`
  注释已说明 v1 不覆盖；KU docstring 说明「好友列表对滚动距离敏感，改回公共滑动必须先
  真机验证」）。
- **循环边界**：多数 bounded（`goto_page` `Timer(30)`、`switch_friend_list` `Timer(20)`、
  `_current_select_best`/`_select_lazy_*`/`_reselect_*` `range`+`Timer(120)`、
  `check_utilize_add` `count>=5`）。`KA.run_activation` 与 `KA.screening_card` 的 4 个
  `while 1` 是 **potentially unbounded**（无迭代上限 / 总超时）。
- **整体模型**：截图 → `appear`/OCR 判局面 → `click`/`swipe_adb` → 多数步骤靠固定 `sleep`
  或「下一轮 `while` 重判」推进，无显式 State/Action/ExpectedState，「验证」大多隐式。
- **FrameWait**：Kekkai production consumers = **0**（两个模块都不 import/引用
  `frame_wait` / `FrameStateDetector`）。本轮未写入任何 threshold / ROI / timeout 猜测。

### Issue Register（本轮全部只记录、不修，详见专题文档 §9）

`check_card_num` 子类覆写改返回类型（latent）；`harvest_card` 无验证闭环；KA `check_card_num`
随机源用 stdlib（与 §4.10 已收敛处不一致）；`swipe_adb` 直连无 trace；KA `while 1` 无超时；
`ocr_time` 失败 `None + datetime` 会崩；`check_utilize_add` return 语义相反（§8 已记）；
`last_best_index=99` 死属性（§8 已记）；lazy_roll 误用 `random_delay`；KA 死 import
`parse_rule`；`run_utilize` U3 `goto_page` 失败不 return。

### 测试

- `tests/test_kekkai_activation_state.py`：**18/18 OK**。
- `tests/test_kekkai_utilize_state.py`：**23/23 OK**。
- 既有 `tests/test_kekkai_utilize_threshold.py`：25/25 OK（未改）。
- `compileall -q tests/test_kekkai_activation_state.py tests/test_kekkai_utilize_state.py`：通过。
- 完整回归 `toolkit/python.exe -m unittest discover -s tests`：**669/669 OK**（628 → 669，
  净 +41 全来自两个新文件）。
- `git diff --check`：干净。
- 未启动 MuMu / 游戏 / OAS / ADB / OCR / server——纯 mock 静态测试，Level A。

### 生产影响

- **零。** `tasks/KekkaiActivation/*` 本轮零改动；`tasks/KekkaiUtilize/{script_task,config}.py`
  的 `M` 是更早轮次的阈值 / 随机源 WIP（§4.11），本轮未触碰。click 顺序 / target / swipe
  参数 / duration / sleep / delay / screenshot / OCR / return / exceptions / loop / 业务策略 /
  配置语义 全部不变。本轮生产 diff = **0**。

### 下一步

- 需真机（Level C）：`harvest_card` 点击后的期望状态（T4-4 pilot）、列表 swipe 后
  `sleep(1)`/`sleep(2)` → `frame changed+stable`、`SWIPE_DISTANCE` 是否跳过/重复条目、
  `swipe_adb` 接入 BehaviorTrace（T5-1）、KA `while 1` 加总超时。
- 无真机可做：其它任务（`RealmRaid` / `Exploration` 等）的迁移前静态收口 + characterization，
  凑齐 2~3 个真实案例后再评估抽公共 State 层（延续「先两个真实迁移案例再抽象」纪律）。

### Git

- 未 commit、未 push、未 merge、未 reset、未 stash、未真机测试。分支 `master`，HEAD 仍为
  `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-02 - RealmRaid 状态机静态收口

### 背景

状态驱动主线的第三个静态收口对象（前两个：`BaseTask.list_find` §4.19、Kekkai §4.33）。
方法论一致：**只读审查 + 建模 + characterization，production diff = 0**，不真正接入
FrameWait / 新 Retry / 新 Recovery / 新 timeout / 新点击模型 / 新随机参数。

### 产出

- `docs/RealmRaid状态机静态收口.md`（专题文档）：完整文本状态图、State Matrix（S1~S15）、
  目标选择 11 问 / 进攻按钮 10 问逐条回答、「战斗进入判定」专项、GeneralBattle 交接、
  Victory/Failure/Recovery 表、Exit/Return、Wait Inventory、Loop/Retry 三分类、
  Stale Screenshot 表、Action→Verify Gap Register（P1~P4）、Existing Issue Register（13 条）、
  RealmRaid vs Kekkai 对比、下一步 Level A / Level C 分列。
- `tests/test_realm_raid_state.py`（41 用例）：纯 mock characterization，锁现状不锁应然。

### 关键现状（源码逐行核实 + AST 验证）

- **`fire()` 的「旧标识消失 = 已进入战斗」**：判定进入战斗的**唯一**依据是
  `if not self.appear(self.I_RR_PERSON): return True`。源码内无 `page_battle` /
  `detect_page_in` / `I_EXIT` / `get_current_page` / `Timer(`——**没有战斗页正向标识、
  没有 timeout、没有 retry 上限**。弹窗遮挡 / 切页动画中间帧 / `threshold=0.8` 附近匹配
  抖动都可能让单帧误判成功。`fire_again()` 同构（`I_FIRE_AGAIN` 消失即成功）。
- **`fire()` 恒返回 `True`**：AST 确认 `while True` 内无 `break`、循环内唯一 `return` 是
  `True`、尾部 `logger.info` + `return False` 不可达 → `run()` 里两处
  `if not self.fire(index): continue` 是**当前死分支**，「没成功进入战斗就重来」这条设计
  意图实际从未生效。`check_refresh` 也有同样的不可达尾部 `return False`。
- **循环 / 等待**：主 `while 1` state-bounded（6 个 break 点）；**6 处自有 `while` 全部
  potentially unbounded**（`fire` / `fire_again` / `ensure_lock` / `check_refresh`×2 /
  `reward_detect_click` / 呱太弹窗）；AST 扫全模块确认 **所有 `wait_until_appear(X)` 都不传
  `wait_time`** → `BaseTask` 内不建计时器。兜底只有上游 `stuck_record`。
- **与 Kekkai 相反的等待特征**：RealmRaid 活跃路径**没有任何固定 `sleep`**（唯一
  `sleep(0.2)` 在死代码 `medal_fire` 内），节流全靠 `interval`；**没有滑动、没有「等画面
  停稳」的等待** → FrameState 候选面很小，`fire()` 的改造方向是 semantic 正向标识而非
  FrameState。
- **GeneralBattle 交接**：`run_general_battle(config) -> bool` 接进 `last_battle`；
  `exit_four` 路径 4×`build_quick_exit_config` + 4×`fire_again` + 第 5 次常规。RealmRaid
  覆写 `_exit_matcher()→I_BACK_RED`、`_handle_result`（quick_exit 时按 `appear(I_FALSE)`
  直接 EXIT_WIN/LOSE 且**不点结算**，否则 `super()`）、`PREPARE_CLICK_DELAY_RANGE=(2.5,3.5)`
  （基类 `(3.0,3.0)`）、`SETTLEMENT_CLICK_INTERVAL_RANGE=(0.65,0.95)`（基类 `(0.7,1.0)`）
  ——即 **RealmRaid 间接消费 T7 Settlement RD opt-in**，只是间隔不同。本轮未动。
- **输入全走 `Control`**：模块内无 `swipe_adb` / `click_adb` / `adb_shell` / `*_minitouch` /
  `device.swipe(` 直连 → 所有点击**都进 BehaviorTrace**（与 Kekkai 两处 `swipe_adb` 绕过
  相反）。目标点击用静态 `C_PARTITION_1..9` 的 `RuleClick.coord()` = `LEGACY_UNIFORM`，
  未做 T7 Point opt-in；本轮亦**未**把 `I_FIRE` 接入 HABIT（`normal_button` profile 仍缺
  Level C runtime ROI 标定）。
- **死代码**：`medal_fire()` / `is_ticket()` 在 `tasks/` + `module/` 全仓零调用方；
  `medal_grid` 类属性为 `None`，`medal_fire` 一旦被调用即 `AttributeError`；`medal_fire`
  声明 `-> bool` 却无任何 `return`；`AttackNumber` 导入后全模块未使用。
- **`find_one` 副作用**：`when_attack_fail == CONTINUE` 时在 `self.device.image` 上
  **原地涂黑**已失败的九宫格（共享帧缓冲副作用）；当前恰好未被消费（`fire()` 立即重截）。
  `false_image` 复用 **RyouToppa** 的 `loser_sign_1.png`（跨任务资产耦合）。

### Issue Register（13 条，本轮全部只记录、不修，详见专题文档 §14）

R-R1「消失=进战斗」无正向确认无超时（最高优先，Level C）；R-R2/R-R3/R-R6 三处不可达
`return False` 与由此产生的 run 死分支；R-R4/R-R5 六处 `while` 与全部 `wait_until_appear`
无超时；R-R7 `medal_fire`/`is_ticket` 死代码 + `medal_grid=None`；R-R8 `AttackNumber` 死
import；R-R9 `find_one` 原地涂黑共享帧；R-R10 跨任务复用 RyouToppa 资产；R-R11 覆写与基类
`I_FALSE` 阈值传法不同（等效，仅缓存路径差异）；R-R12 点静态九宫格 ROI 而非识别位置；
R-R13 `O_NUMBER` 与 `O_TEXT` 共用同一 ROI。

### 是否抽公共 Retry / State 层：否

RealmRaid 与 Kekkai 确实共有「点击 → 旧标识消失即成功」与「`while` + `interval` 无超时
反复点」两种模式（合计 10+ 处），但所有超时值都是 Level C 未知；且 `list_find` / Kekkai
的公共点是**视觉结构等待**，而 RealmRaid 根本没有这类等待——**三者的公共层不是同一个**，
不能一次抽完。延续 D013「primitive 可共享、business wrapper 不一定」与「收口阶段不抽 seam」
纪律，等真机数据后再评估。

### 测试

- `tests/test_realm_raid_state.py`：**41/41 OK**。
- `compileall -q tests/test_realm_raid_state.py`：通过。
- 完整回归 `toolkit/python.exe -m unittest discover -s tests`：**710/710 OK**（669 → 710，
  净 +41 全来自新文件）。
- `git diff --check`：干净。
- 未启动 MuMu / 游戏 / OAS / ADB / OCR / server——纯 mock 静态测试，Level A。

### 生产影响

- **零。** `git diff -- tasks/RealmRaid/` 为空。click 顺序 / target / 次数、retry / wait /
  timeout、ticket OCR、`when_attack_fail` / `three_refresh` / `exit_four` / `order_attack` /
  `number_base` / `number_attack`、刷新顺序、RealmRaid T7 点击（仍 `LEGACY_UNIFORM`，
  `I_FIRE` 未接 HABIT）、GeneralBattle（含 Settlement Contract v2）、screenshot / OCR /
  return / exceptions / loop —— 全部不变。本轮生产 diff = **0**。

### 下一步

- **Level C（首要）**：确认「`I_RR_PERSON` 消失」到「战斗页可识别」的真实过渡帧序列，据此
  把 `fire()` 改成「旧标识消失 **且** 战斗页正向标识出现」并定超时（R-R1 + R-R2 一起设计）；
  给 6 处无界 `while` 与全部 `wait_until_appear` 定超时；确认 `find_one` 涂黑是否仍必要；
  确认九宫格静态 ROI 与实际勋章位置偏差。
- **Level A**：删 `medal_fire`/`is_ticket`/`medal_grid`/`AttackNumber` 死代码（已 grep 确认
  零调用方）；继续对第 4 个任务（`Exploration` / `Dokan` 等）做同样的静态收口。

### Git

- 未 commit、未 push、未 merge、未 reset、未 stash、未真机测试。分支 `master`，HEAD 仍为
  `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-02 - 三案例 Verify / Wait / Retry / Recovery 架构归纳（决策节点）

### 背景

`list_find`（§4.19）、Kekkai（§4.33）、RealmRaid（§4.34）三个真实案例的迁移前静态收口 +
characterization 都已完成。本轮不改第四个业务模块，而是横向归纳 Verify / Wait / Retry /
Recovery 四类职责，判断哪些能力应该公共化、哪些只能做 primitive、哪些必须留在 Task，并
决定下一阶段最值得实施的单一工作。**纯设计归纳——无 Python 改动、无业务生产行为改动。**

### 产出

- `docs/状态验证与重试模式归纳.md`（专题文档，17 节 + 附十四问速答）：三案例总矩阵、
  四类定义、Semantic Transition S1~S4、Structural Transition、Retry 全量表、Timeout /
  Attempts Contract、Recovery Boundary、Fresh Screenshot Contract、Target Relocation
  Contract、Result / Exception Contract、Pattern Catalog A~E、Owner Matrix、
  BehaviorTrace 事件优先级、Level A Cleanup Queue（12 项排序）、是否抽公共层、
  下一阶段推荐、retry primitive API proposal（仅供未来参考、本轮不实现）。
- `docs/DECISIONS.md` D015：把「Verify / Wait / Retry / Recovery 职责分层与 owner」+
  「未来任何 bounded retry primitive 的硬约束」+「当前不抽 retry 抽象的决定」固化为长期契约。

### 核心结论

**是否抽公共 Retry / Verify 层：PARTIAL，且不是现在。**

- **structural wait**：`module/base/frame_wait.py::wait_for_changed_and_stable` 已就位、
  无缺口（不自截 / 阈值必须显式传 / timeout 必须为正不抛 / 不做 retry·recovery /
  无 Device·Timer·BehaviorTrace 依赖）。缺的 100% 是 Level C 参数 + 调用点 baseline 捕获。
  **不新增第二套 structural wait 抽象。**
- **semantic verify**：`wait_until_appear` / `wait_until_disappear` / `appear` 组合已足够；
  `wait_until_disappear` 补 `wait_time` 是 1 行签名扩展（不是新类，且改动本身改 `fire()`
  时序 → Level C）。**不需要 `Verifier` / `ActionVerifier` / `GenericTargetLocator` 类。**
- **bounded retry**：RealmRaid `fire`/`fire_again`/`ensure_lock`/`check_refresh`、Kekkai
  `screening_card` 有共同骨架「locate → action → verify → bounded retry → result」，但
  ① action 每轮在 2~3 个 target 间交替（不是「retry same action」）；② **当前全部无
  bound**——加 bound 就改时序，每个消费者接入都是 Level C；③ recovery 差异极大
  （`fire` 当前什么都不做且是死分支 / `ensure_lock` 直接往下走 / `screening_card` →
  `_card_not_found` → `raise TaskEnd`）。**唯一真正共同的内核只有「计 attempts + 独立
  total timeout + 返回 frozen result」约 15 行**，值得未来抽、不值得现在在零消费者下抽。
- **recovery**：`return False` / `refresh` / `switch group` / `set_next_run(+N min)` /
  改 config / `raise TaskEnd` / `find_one` 涂黑——高度业务特化，**永远留在 Task**。

### 关键契约（详见专题文档 / D015）

- **max_attempts ≠ timeout**：前者限「Action 执行次数」，后者限「整段迁移墙钟时间」，
  可同时存在，任一先到即止，**数值永远调用方给**（无项目级默认，跨案例合理值从 2s 到 120s）。
- **timeout 三层归属**：wait primitive（`wait_time` / `frame_wait.timeout`）/ retry 机制
  （若未来存在）/ Task（业务操作总超时，如 Kekkai `Timer(120)`）。禁止 `GLOBAL_ACTION_TIMEOUT`。
- **fresh screenshot**：推荐模式 B——`verify` / `action` callback 自己截图 + 识别（与现有
  `screenshot(); appear(...)` 写法零改造契合），retry primitive **不 screenshot**。必须防
  「Action 后 Verify 读到 Action 前旧帧」。
- **target relocation**：公共 retry primitive **绝不缓存业务坐标**；每次 attempt 的定位 +
  动作在 `action` callback；primitive 不理解 `RuleImage` / `RuleOcr` / `RuleClick` / list。
- **exception**：默认**透传**（把 `AttributeError` / `None+datetime` 这类真 bug 伪装成
  「retry 失败」会掩盖缺陷）；可重试异常白名单是未来显式能力。
- **result contract**：frozen dataclass，形态参照 `FrameWaitResult`——`success` /
  `timed_out` / `attempts` / `elapsed` / `last_verify`，无业务字段。

### 下一阶段推荐：Option 2 —— Level A correctness / dead-code cleanup

- 理由：项目优先级 `correctness > reliability > observability > abstraction`；专题文档 §16
  的清理队列全部零真机、低风险、有 characterization 回归护栏；retry 内核等第一个真实
  Level C 迁移时对着真实消费者抽更准。
- 不选 Option 1（零 adoption 校准、每个接入都是 Level C、悬空组件）/ Option 3（三案例形态
  已够——纯 structural / 混合 / 纯 semantic + GeneralBattle 深耦合）/ Option 4（还有一整队
  Level A 活，主线没到「只剩真机」）。
- **本轮不做 cleanup**——architecture synthesis 与 correctness cleanup 不混在一个 diff，
  cleanup 留下一轮独立做 + 逐项测试。

### BehaviorTrace 下一步观测

`RETRY` 事件（一次 bounded retry 循环结束记一条，带 target/transition 名 + attempts +
outcome，天然含 timeout 信号），优先级高于 `VERIFY`（每 attempt 一条太吵、违背 D004
「不记录 appear()」）/ `TIMEOUT`（是 RETRY 的 `timed_out` 子集）。排在 retry 抽象之后，
本轮不动 BehaviorTrace。

### 测试

- **无测试改动。** 完整回归 `toolkit/python.exe -m unittest discover -s tests`：
  **710/710 OK**（维持不变）。
- `git diff --check`：干净。
- 未启动 MuMu / 游戏 / OAS / ADB / OCR / server。

### 生产影响

- **零。** `list_find` / Kekkai / RealmRaid / GeneralBattle / FrameWait / FrameStateDetector /
  ClickSampler / ClickProfile / BehaviorTrace 全部未改。本轮只新增两份 docs（专题 + D015）
  与 4 份既有文档同步。

### Git

- 未 commit、未 push、未 merge、未 reset、未 stash、未真机测试。分支 `master`，HEAD 仍为
  `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-02 - Level A cleanup 批次 1（只删可证明零引用的死代码）

### 背景

执行上一轮架构归纳（§4.35 / D015）推荐的 Option 2 的**第一批**。严格分类后**只处理 A 类**
——「可从源码证明所有生产路径输出完全相同」的死代码 / 死 import / 零引用死属性。B 类
（会改变运行结果的 correctness 修复）本批只在正确语义唯一时处理，实际无一符合、全部
deferred；C 类（与 Level C 状态迁移耦合）只记录不改。

### FIXED（4 个 Cleanup Queue issue / 5 条子项 / 6 个具名删除 / 3 个生产文件，全部 behavior-neutral，逐项已 grep 确认零引用）

口径说明：「4 个 Cleanup Queue issue」= `docs/状态验证与重试模式归纳.md` §16 的 4 行
（R-R7 死方法簇、R-R8 死 import 簇、`parse_rule` 死 import、`last_best_index` 死属性）；
展开成下面 5 条子项、共 6 个具名删除（`medal_fire` / `is_ticket` / `medal_grid` /
`RealmRaid`·`AttackNumber`·`time` 三个 import 名 / `parse_rule` / `last_best_index`）。

1. **`RealmRaid.ScriptTask.medal_fire()` / `is_ticket()` 删除**——`tasks/` + `module/` 全仓
   零调用方，无 super/subclass override、无 `getattr` / 字符串 / scheduler / config command
   引用（`module/config/config_model.py` 的 `getattr(self, task, ...)` 是按任务名取 config
   model，不是调 ScriptTask 方法）。`medal_fire` 还依赖被同批删除的 `medal_grid = None`
   （一旦调用即 `AttributeError`）。真正生效的是 `check_ticket`（票数）与 `fire`（进攻），
   均保留。
2. **`RealmRaid` `medal_grid: ImageGrid = None` 类属性删除**（仅 `medal_fire` 内部用）。
   `from module.atom.image_grid import ImageGrid` 保留——`order_medal` cached_property 仍用。
3. **`RealmRaid` import 精简**：`from tasks.RealmRaid.config import RealmRaid, AttackNumber,
   WhenAttackFail` → `... import WhenAttackFail`。`RealmRaid`（配置类）与 `AttackNumber`
   在 `script_task.py` 内零引用（`config_model.py:49` 另有独立 `from tasks.RealmRaid.config
   import RealmRaid`；`WhenAttackFail` 仍用于 `when_attack_fail == WhenAttackFail.*` 分支）。
   `import time` 随 `medal_fire`（唯一 `time.sleep` 使用者）删除后变死，一并删。
4. **`KekkaiActivation` 删 `from tasks.KekkaiActivation.utils import parse_rule`**——模块内
   零引用。`utils.py` 里 `parse_rule` 函数本体不动（最小删除范围）。
5. **`KekkaiUtilize.ScriptTask` 删 `last_best_index = 99`** 死类属性——全仓零读取者（无
   `.last_best_index` / `getattr` / 序列化），AI_CONTEXT §8 早已记录。

（口径：RealmRaid = 2 个 Cleanup Queue issue——死方法簇 R-R7（子项 1+2）与死 import 簇
R-R8（子项 3，含 `import time` 级联）；KekkaiActivation `parse_rule` = 1 个；KekkaiUtilize
`last_best_index` = 1 个 → 共 4 个 issue / 5 条子项 / 6 个具名删除 / 3 个生产文件。）

### DEFERRED —— Level C 耦合（只记录，不改）

- `RealmRaid.fire()` / `fire_again()` / `check_refresh()` 尾部不可达 `return False` +
  `run()` 里 `if not self.fire(index)` 死分支——这三处不可达语句**正是未来「加战斗页正向
  确认 / 加 timeout 失败路径」的接入点**，删掉会抹掉设计信号；`fire` 的判定改造是 Level C
  （R-R1 / R-R2，与 `docs/RealmRaid状态机静态收口.md` 一致）。characterization 测试仍锁
  「现状不可达」，等重设计时一起动。
- `find_one` 原地涂黑共享帧（R-R9）——改动需真机确认涂黑是否仍必要。
- `harvest_card` 状态化（T4-4）。

### DEFERRED —— 正确语义不唯一（只记录，不改）

- `KekkaiActivation.ocr_time()` 失败 `return None` → 两个调用处 `set_next_run("KekkaiActivation",
  target=interval + datetime.now())` → `None + datetime` → **`TypeError`**。crash 属实，但
  正确恢复语义**源码无法唯一确定**：候选有「与同函数 `delta == 0` 分支一致改成
  `raise GameStuckError`（→ 重启游戏）」/「像 `KekkaiUtilize.UTILIZE_RES_TIME_FALLBACK`
  那样按固定兜底间隔重试」/「retry」。KU 的兜底值是它自己的一次性决定，直接照搬到 KA
  等于拍脑袋（本轮明确禁止 `now + 5 min` 这类默认）。
- `KekkaiUtilize.check_utilize_add`「5 轮未蹭上」`return True`（vs 失败路径 `return False`）
  ——改成 `False` 会让 `run()` 提前 `return`、跳过 `check_max_lv` / 收菜 / 收盒子；是否有意
  需产品决定（§8 已记「不影响正确性」）。

### KEPT / NOT_REPRODUCED（只记录，不改）

- **`KekkaiActivation.check_card_num` 用 stdlib `random.randint`**——**KEPT**。判据：D007
  的「已存在的未迁移部分按既有决定保留，不为形式统一做无关重构」条款，且
  `RyouToppa.flush_area_cache` 用同款 `random.randint`（列表滑动坐标起点 / 终点 / distance）
  被 D007 明确保留、AI_CONTEXT §8.2 列为「按 §4.10 决定保留」——KA `check_card_num` 是
  结构完全平行的列表滑动坐标 jitter，单独改会与 RyouToppa 产生不一致。留给未来专门的
  随机源一致性 pass。（`random.randint` → `random_int` 会改变 RNG 序列，不是 bit-for-bit
  neutral，本身也不符合「安全批次」的 A 类。）
- **`KekkaiUtilize.run` 的 `lazy_roll = random_delay(0.0, 1.0)`**——**NOT_REPRODUCED**。
  回源码：本项目的 `random_delay(min, max)` 是 `return _rng.uniform(min, max)` 的**纯函数、
  无 `time.sleep`**。所以 `lazy_roll` 已经就是「从公共 `SystemRandom` 取 `[0,1]` 均匀
  样本」，运行行为**正确**、无 delay 副作用。只是函数名有误导（叫 "delay" 却不等待）；
  纠正需要新增 `random_float` / `random_probability` helper（新增公共 API，超出安全批次
  范围）。留给未来可读性 pass。

### 改动文件

| 文件 | 修改 | 是否改变运行语义 | 理由 |
|---|---|---|---|
| `tasks/RealmRaid/script_task.py` | `-import time`、`-2 个 dead import 名`、`-medal_grid`、`-is_ticket`、`-medal_fire`（共 59 行删除；本轮 100% 由本批产生） | **否** | 全部零引用死代码 / 死 import；`check_ticket` / `fire` / `order_medal` / `WhenAttackFail` / `ImageGrid` / `re` 均保留 |
| `tasks/KekkaiActivation/script_task.py` | `-1` 行 dead import `parse_rule` | **否** | 模块内零引用 |
| `tasks/KekkaiUtilize/script_task.py` | `-1` 行 `last_best_index = 99`（其余 `M` hunk 是更早轮次阈值 WIP，本批未碰） | **否** | 全仓零读取者 |
| `tests/test_realm_raid_state.py` | 4 个「死代码存在」测试 → 2 个「已删 + 守卫不被重新引入」测试；`test_every_wait_until_appear_call_omits_wait_time` 阈值 `>=5` → `>=4` | 测试自身，非生产 | `medal_fire` / `is_ticket` 删除后活跃路径剩 4 处 `wait_until_appear` |

### 测试

- `tests/test_realm_raid_state.py`：**39/39 OK**（41 → 39，净 `-2`）。
- `tests/test_kekkai_activation_state.py` 18/18、`tests/test_kekkai_utilize_state.py` 23/23、
  `tests/test_kekkai_utilize_threshold.py` 25/25：全 OK（未改）。
- `compileall -q tasks/RealmRaid/script_task.py tasks/KekkaiActivation/script_task.py
  tasks/KekkaiUtilize/script_task.py tests/test_realm_raid_state.py`：通过。
- 完整回归 `toolkit/python.exe -m unittest discover -s tests`：**708/708 OK**（710 → 708）。
- `git diff --check`：干净。
- 未启动 MuMu / 游戏 / OAS / ADB / OCR / server。

### 生产影响

- **behavior-neutral cleanup only。** 三个生产文件的改动全部是「删除零引用死代码 / 死
  import」，无任何运行路径的 click / swipe / sleep / OCR / return / exception / loop / 配置
  语义变化。**本批无 intentional correctness fix**（B 类全部 deferred）。
- GeneralBattle / T7（ClickSampler / ClickProfile / Settlement / C_AREA_1）/ FrameWait /
  BehaviorTrace：完全未碰。

### 剩余 Cleanup Queue（下一批）

`docs/状态验证与重试模式归纳.md` §16 里未处理的 + 本节 DEFERRED 项。下一批建议处理「正确
语义唯一的 B 类 correctness」——但目前 §16 里的 B 类（`ocr_time` / `check_utilize_add` 返回
语义 / lazy_roll 命名）要么语义不唯一、要么需新增 helper、要么 NOT_REPRODUCED，所以**下一
步更可能是继续第四个任务的静态收口，或等 Level C**。

### Git

- 未 commit、未 push、未 merge、未 reset、未 stash、未真机测试。分支 `master`，HEAD 仍为
  `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-02 - Exploration 状态机静态收口 + characterization（第四案例）

状态驱动主线第四个迁移前静态收口对象（前三：`list_find`、Kekkai、RealmRaid）。方法论一致：
只读审查 → State / Action / ExpectedState / Verify / Wait / Retry / Recovery 建模 →
characterization tests → **production diff = 0**。`git diff -- tasks/Exploration/` 为空。

### 结论

- **Exploration 是四案例里唯一「本身已经是 page-dispatch FSM」的任务**。`run()` =
  `pre_process()` → `exec_exp_page()` → `post_process()`；`exec_exp_page()` 的 `while True`
  每轮 `screenshot()` → `get_current_page()` → `exp_page_handle_dict` 查表执行 handler。
  无迭代上限 / 无总 `Timer`——靠 `check_exit()`（够怪数 / 超时 / 队友等待超时）+
  `InviteFailedException` 收敛（state-bounded）。
- **`fire()` 与 RealmRaid `fire()` 的核心差异——这是本轮最重要的发现**：
  - 判据是 **正向战斗页确认**：`get_current_page() in (pages.page_battle_prepare,
    pages.page_battle) → return True`（新页面正向出现），**不是**「旧标识消失」。
  - **双重上界**：`while max_tries > 0 and not timeout_timer.reached():`，`max_tries = 4`
    **且** `Timer(10)`，任一到即停。
  - **会返回 `False`**：耗尽后 `return False` → `run_on_exp_main` 做 Task 层 recovery
    （`swipe(S_SWIPE_BACKGROUND_RIGHT)` 找下一个怪 / `arrive_end()` 则 `quit_exp_main()`）。
  - 即 `docs/RealmRaid状态机静态收口.md` §6 列的 stronger candidate「old disappeared
    **and** expected appeared」里 **expected-appeared 那半在 Exploration 中已是生产实现**。
    RealmRaid `fire()`（R-R1）未来改造可直接照 `fire()` 形状抄。
- **GeneralBattle 交接是浅耦合**：`run_on_battle` → `run_general_battle(cfg,
  exit_matcher=pages.page_exp_main)`（`exit_matcher` 是 `Page` 对象，走
  `_evaluate_exit_matcher` 的 `isinstance(target, Page)` 分支）；返回值**被丢弃**。
  Exploration **只覆写 `_exit_matcher()`**（→ `page_exp_main` 三选一识别），
  **未覆写** `_handle_result` / `_handle_reward` / `_settlement_click` /
  `PREPARE_CLICK_DELAY_RANGE` / `SETTLEMENT_CLICK_INTERVAL_RANGE`——结算 100% 走基类
  Contract v2 默认（`(0.7, 1.0)`）。对比 RealmRaid：覆写 `_handle_result` + 两个时序常量。
- **输入全走 `Control`**（`self.click` / `self.swipe` / `appear_then_click`），**无一处
  `swipe_adb` / 直连后端**（对比 Kekkai 两处 `swipe_adb` 绕过 BehaviorTrace）。
- **结构稳定等待用既有原语**：`arrive_end()` = `click_record.count(...) >= 6` **或**
  `_match_end.stable(...)`，`_match_end = RuleAnimate(self.I_SWIPE_END)`（2 帧模板结构稳定，
  `module/atom/animate.py`）——**不是** `module/base/frame_wait.py`。FrameWait 生产消费者 = 0。
- **无界裸 `while`（无 Timer 无计数）= 0**（对比 RealmRaid 6 处、KA 4 处）。**唯一 1 处
  `wait_until_appear` 调用带 `wait_time=3`**（对比 RealmRaid「全部不传」）。

### D015 再验证（`docs/DECISIONS.md`）

逐条对照 Exploration 证据（完整表见 `docs/Exploration状态机静态收口.md` §18），
**D015 无需修改**——四案例里 Exploration 对每一条都正向印证：
- 四类职责（Verify / Wait / Retry / Recovery）在 Exploration 里清晰分离在不同函数。
- `fire()` 是 D015「未来 bounded-retry primitive」的**近似现成参照实现**：符合硬约束
  #1（循环 + 计 attempts + 独立 timeout + 任一到即停，只差返回 frozen result 而非 bool）、
  #3（primitive 不 screenshot——`fire()` 循环体自己 `screenshot()`）、#4（不做 recovery——
  只 `return False`，调用方自己 recover）、#5（异常透传）。
- 唯一补充（写入专题文档，**不改 D015 正文**）：`fire()` 缓存了 `roi_front` 窗口
  （`search_up_fight` 原地改写 `I_NORMAL_BATTLE_BUTTON.roi_front`），未来迁移时 `action`
  callback 要包含「重新 `search_up_fight` 定位」而非只在固定 ROI re-match（对应硬约束 #2）。
- 从「三案例的 action-retry 循环当前全部无 bound」更新认识为「Exploration `fire()` 已有
  bound，是参照实现」——但「零消费者下不抽公共组件」的 PARTIAL 结论不变。

### Issue Register（E-1 ~ E-9，全部只记录，未修）

| ID | 位置 | 现状 | 分类 | Level |
|---|---|---|---|---|
| E-1 | `search_up_fight` | 原地改写共享 `RuleImage` 实例的 `roi_front`，跨轮次残留 | architecture / reliability | C |
| E-2 | `run_on_exp_main` + `fire()` | 目标在 `fire()` 循环前定位一次，retry 期间怪移出 ROI 只能靠 `Timer(10)` 超时 | reliability | C |
| E-3 | `exec_exp_page` | `current_page is None` 无连续 None 计数上限，只靠 `limit_time` 兜底 | reliability | C |
| E-4 | `fire()` False 后 | recovery 是「滑地图找下一个怪」，不重试当前怪（贪心设计取舍） | correctness / reliability | C |
| E-5 | `run_on_battle` | `run_general_battle(...)` 返回值被丢弃 | observability | — |
| E-6 | `exp_page_handle_dict` | `page_reward` handler 是就地 lambda，与其它 bound-method handler 形态不一致 | style | — |
| E-7 | `E.arrive_end` 覆写 | `EXPLORATION_28` 特判与基类结构判定并列，维护易漏改 | architecture | — |
| E-8 | `open_expect_level` 第二个 `while 1` | 无独立上界（靠第一段调对层数 + `is_in_room()` 兜底） | reliability | C |
| E-9 | `fill_shikigami` | 无总 `Timer`（有三条 `break` + `GameStuckError` 兜底） | reliability | C |

> 没有一条 E-* 达到 RealmRaid R-R1 那种优先级——Exploration 进攻链路本身已是四案例里最稳。

### 改动文件

| 文件 | 修改 | 是否改变运行语义 |
|---|---|---|
| `tests/test_exploration_state.py` | 新增，33 用例，纯 mock（`ScriptTask.__new__` + patch `screenshot` / `get_current_page` / `appear_then_click` / `Timer`；含 AST 断言） | 测试自身，非生产 |
| `docs/Exploration状态机静态收口.md` | 新增专题（21 节：控制流 / State Matrix E1~E15 / 目标选择 / `fire()` / 战斗进入四案例横向 / GeneralBattle 交接 / 战斗返回 / Wait Inventory / Loop Inventory / Fresh Screenshot / Target Relocation / Gap Register / Issue Register / characterization / 四案例对比 / FrameWait / D015 再验证 / 测试 / 生产影响 / Git） | 文档 |

**`tasks/Exploration/*` / `GeneralBattle` / `base_task.py` / 任何生产代码：未改。**

### 测试

- `tests/test_exploration_state.py`：**33/33 OK**。
- `compileall -q tests/test_exploration_state.py`：通过。
- 完整回归 `toolkit/python.exe -m unittest discover -s tests`：**741/741 OK**（708 → 741，
  净 `+33` 全来自新文件）。
- `git diff --check`：本轮新增文件干净（仓库级 non-zero 来自既有用户 WIP
  `tasks/Component/GeneralBattle/assets.py` 的行尾空格 / EOF 空行，非本轮引入，按规则不动）。
- 未启动 MuMu / 游戏 / OAS / OASX / ADB / OCR RPC / server。

### 生产影响

- **零。** `tasks/Exploration/` 对 HEAD 零 diff。FSM dispatch / `fire()` 双重上界 / 正向
  判定 / `get_fire_button` ROI 重定位 / `run_on_battle` 交接参数 / GeneralBattle Settlement
  Contract v2 / `arrive_end` 双判据 / `check_exit` 三条件 / 循环边界 / screenshot / OCR /
  swipe 通道 / return / exceptions：全部未变。Exploration 未做 T7 Point opt-in，点击仍
  `LEGACY_UNIFORM`。

### 下一步

- 四案例静态收口全部完成（`list_find` / Kekkai / RealmRaid / Exploration）。D015 经四案例
  验证稳定。下一步仍是 `docs/状态验证与重试模式归纳.md` §16 的 Level A cleanup 队列，或
  等 Level C 真机窗口做第一个真实状态化迁移（大概率 RealmRaid `fire()`，参照 Exploration
  `fire()` 形状）。

### Git

- 未 commit、未 push、未 merge、未 reset、未 stash、未真机测试。分支 `master`，HEAD 仍为
  `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-02 - appear_then_click / confirm_delay / Reaction Timing 全仓专项审查

「点击前反应延迟职责收口」专项——**纯静态审查，零生产改动、零新增测试**
（`tests/test_base_task_confirm_click.py` 5 用例已充分覆盖 `confirm_delay`）。
完整报告 `docs/Action点击前反应时序静态审查.md`（31 节）。

### 核心结论

- **`confirm_delay` 能否作为可识别 Point Action 的统一 reaction timing？→ PARTIAL。**
  能力实现正确，但当前零生产 opt-in、覆盖面有边界、不应「统一」。
- **`appear_then_click` 真实调用链**（`tasks/base_task.py:319-388`，与 commit `880cd21f`
  逐字一致，工作树对该方法零改动）：
  - **默认路径**（`confirm_delay is None`）：`self.appear(target, interval=, threshold=)`
    ——**不截图**，读调用方 `while` 循环里最近一次 `self.screenshot()` 的帧；命中即
    `target.coord()` / `action.coord()` → `self.device.click`；返回 `appear`。**无 delay。**
    `interval` 是 `Timer` 门控（未到 `return False`，命中后 `reset`），**不 sleep**。
  - **`confirm_delay=(lo,hi)` 路径**：① `interval` 门控 → ② `appear(target)` 首次（当帧）
    → ③ `delay = random_delay(*confirm_delay)`（模块级 `SystemRandom.uniform`）→ ④
    `sleep(delay)` → ⑤ `self.screenshot()`（**fresh**）→ ⑥ `appear(target)` 二次（新帧，
    **目标没了 `return False` 不点**）→ ⑦ `target.coord()` / `action.coord()`（在 fresh +
    re-appear 之后）→ ⑧ `device.click` → ⑨ `interval` `reset` → `return True`。
- **Fresh Frame / Relocation**：`confirm_delay` 路径 = 模式 A（重新 screenshot + 重新
  `appear` + 重新 `coord`）。`RuleImage.appear` → `match` → `_apply_match_result` 会把
  `roi_front` 更新到新帧匹配位置，`coord() = ClickSampler.sample(roi_front)` 吃到更新——
  **T7 空间采样发生在 fresh + relocate 之后，无 stale-coord 风险**。唯一边角：`action=`
  分支点 `action.coord()`（静态 `RuleClick` 不重定位，设计如此）。
- **全仓盘点**：`appear_then_click(` 调用 **486 处 / ~85 文件**；`confirm_delay=` 传入
  **0 处**（能力 2026-08-28 上线，`tests/test_general_battle_timing.py:256` 有
  `assertNotIn('confirm_delay')` 守卫）。`self.click(` 在 `tasks/` 共 222 处（多为
  Static Region / poll 循环）。
- **是否新增 `reaction_delay` API → 否**：`confirm_delay` 就是该 primitive；
  `reaction_delay` / `CLICK_REACTION_DELAY` 已有前科被删（RealmRaid），D008 明令禁止
  重新加入。
- **Timing Ownership 分层**：
  - **Micro**（单 Action 内）：`confirm_delay` reaction pause + 二次确认 + 重定位。
  - **Throttle**（跨轮次）：`interval` `Timer` 门控 / poll 循环 / `list_find` 翻页 sleep。
  - **State Wait**：`wait_until_appear(wait_time=)` / `wait_until_disappear`（语义）、
    `wait_for_changed_and_stable`（视觉结构，D012）。
  - **Macro**（task-cycle 安全节点）：`FatigueManager` idle / rest——`try_break(safe=True)`
    只在调用方显式安全节点触发（**当前仅 `RyouToppa`**，主循环 `attack_area()` 返回后、
    `continue` 前），`try_break` 全程不碰 `self.device`（不截图 / 不重识别 state，调用方
    负责）。
  - 四者 owner 不同、不互相替代、不在同一 Action 上叠加。
- **Action Transaction**（`State recognized → reaction → fresh relocation → Action →
  Verify`）值得作为架构描述性概念：Fatigue 不在其中途插入（当前由构造保证）；每个 Retry
  attempt 是新 transaction（Exploration `fire()` 已是此形态——每轮 `screenshot` +
  `appear_then_click`）。**不需要新建类 / 运行时强制。**
- **Fatigue × confirm_delay 当前不叠加**：break 在 task-cycle 边界，`confirm_delay` 在
  `appear_then_click` 内部，时间线分离。
- **GeneralBattle**：自有 `PREPARE_CLICK_DELAY_RANGE` / `SETTLEMENT_CLICK_INTERVAL_RANGE`
  时序契约（v2），结算走 `_sample_settlement_click(C_RANDOM_RD)` 区域点击（不走
  `appear_then_click`）；**永不叠加 `confirm_delay`**。
- **RealmRaid**：`I_FIRE` 是最典型 Image Point Target，但 `fire()` 循环在 R-R1 改造
  （bounded retry）之前无收敛保证，此时加 `confirm_delay` 无意义；`partition` 是 Static
  Region（`C_PARTITION_*`），不能迁 `appear_then_click`。
- **Kekkai `harvest_card`**：8 处 `appear_then_click` 无 `confirm_delay`、全跑同一帧；
  真正缺口是「无 semantic verify / 无 reward 闭环」（T4-4），应先做 State→Action→Verify。
- **Exploration `fire()`**：用 `appear_then_click(button, interval=0.8)`，无 `confirm_delay`
  ——它自己就是 bounded semantic retry（每轮 `screenshot` + 正向战斗页确认 + `max_tries` +
  `Timer(10)`），`confirm_delay` 能提供的已被循环结构覆盖。证明**不是所有强 Semantic
  Action 都该改成 `appear_then_click` + `confirm_delay`**（需正向状态确认 / 重新 search 的
  场景走 Task 层 bounded retry）。
- **D001 继续成立并扩写**：`confirm_delay` 正式定义为「可识别 Point Target 单击的 reaction
  timing（识别后停顿 + 二次确认 + 重定位）」，逐调用点显式 opt-in、参数调用方给、不新增
  同义 API、macro/micro 不叠加、不替代 semantic wait / retry throttle、GeneralBattle 不
  叠加、`FatigueManager` 不进入 Action transaction。
- **D015 继续成立**：`confirm_delay` 是「单 attempt 内 reaction + 就地 fresh revalidate」
  的合规缩影，与未来 bounded-retry primitive 硬约束 #2（不缓存坐标）/ #3（自己截图防读旧
  帧）/ #4（不做 recovery）一致。

### 是否新增测试

**否。** `tests/test_base_task_confirm_click.py`（5 用例，随 commit `880cd21f` 一起）已锁：
默认路径不变、confirm 路径事件序列 `['appear-A','sleep','screenshot','appear-B','coord-B',
'click']`（证明 fresh revalidation + 用二次 appear 后的位置）、目标消失不点、interval 未到
全跳过、interval 命中后 `reset`。覆盖充分，不重复造测试。

### 改动文件

| 文件 | 修改 | 是否改变运行语义 |
|---|---|---|
| `docs/Action点击前反应时序静态审查.md` | 新增专题（31 节） | 文档 |
| `docs/DECISIONS.md` D001 | 扩写：从「默认不启用」→「`confirm_delay` = Point Action 官方 reaction-timing 机制 + 逐点 opt-in + 不新增同义 API + macro/micro 不叠加 + 不替代 semantic wait/throttle + Fatigue 不进 Action transaction」 | 文档（长期契约） |
| `docs/ARCHITECTURE.md` §2 BaseTask | 新增「时序职责分层」块（Micro / Throttle / State Wait / Macro + Action Transaction 原子性） | 文档 |
| `docs/AI_CONTEXT.md` §3.2 / §4.38 / §9 | 记录审查结论 | 文档 |

**未改** `tasks/base_task.py` / `appear_then_click` / `confirm_delay` / `random_delay` /
`module/fatigue.py` / `frame_wait` / retry / `ClickSampler` / RealmRaid / Exploration /
Kekkai / GeneralBattle / 任何默认 timing。

### 测试

- 完整回归 `toolkit/python.exe -m unittest discover -s tests`：**741/741 OK**（未变）。
- `tests/test_base_task_confirm_click.py` 单模块 5/5、`tests/test_general_battle_timing.py`
  单模块 17/17：OK。
- `git diff --check`：本轮无新增/修改的已跟踪代码文件（专题文档 + 交接文档均在未跟踪的
  `docs/` 下）。仓库级 non-zero 来自既有用户 WIP `tasks/Component/GeneralBattle/assets.py`
  行尾空格，非本轮引入。
- 未启动 MuMu / 游戏 / OAS / OASX / ADB / OCR RPC / server。

### 生产影响

- **0。** 纯静态审查 + 文档。

### 下一步

- 只固化职责文档（本轮已完成 D001 扩写 + ARCHITECTURE timing 分层）。**不加任何
  `confirm_delay` opt-in。** 首个真实 opt-in 待 Level C：以 RealmRaid `fire()` 的 bounded
  改造（R-R1，按 Exploration `fire()` 形状）为载体，`I_FIRE` 的 `confirm_delay` 参数用
  manual click / BehaviorTrace 数据标定，作为「attempt 内 reaction pause」接入。

### Git

- 未 commit、未 push、未 merge、未 reset、未 stash、未真机测试。分支 `master`，HEAD 仍为
  `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-03 - GeneralBattle 新通用结算策略迁移（SETTLEMENT CONTRACT V3）

正式生产迁移。用户已做出明确业务决策：废弃旧 `C_RANDOM_RD` / `C_RANDOM_RD2` + HABIT
profile（Contract v2），改为「Generic Result 强制两次点击序列 + Reward layout-aware region
policy + 三个 Large Safe Region 整 ROI 均匀」。长期契约固化到 `docs/DECISIONS.md` D016
（取代 D014 的 Settlement Contract v1 / v2 条目）。

### 旧代码真实 Result → Reward 行为（迁移前事实）

Contract v2 没有「Result 必须两次点击」的显式业务模型。`page_battle_result` →
`_handle_result` → `_settlement_click(context)`：`settlement_click_timer` 到点就点一次
`C_RANDOM_RD`（HABIT + `_SETTLEMENT_PRIMARY_PROFILE`）、重采 0.7~1.0s 间隔、`reset()`、
`CONTINUE`；每 handler 每帧最多点一次。多次推进点击是 result handler + reward handler +
settlement timer + 多轮 FSM（`while True` 每轮 `screenshot` + `detect_page_in`）**自然
产生**的，不是显式序列。`page_reward` 里先无条件 `appear_then_click(I_OVER_GHOST /
I_GB_SKIN_CONFIRM, interval=0.8)`（点中也不早退），再 `_settlement_click`。

### 新 Result Action Sequence（`_advance_generic_result`）

`_handle_result`：`context.is_win = not appear(I_FALSE)` →
`if not settlement_click_timer.started() and _is_generic_result_context():`
`_advance_generic_result(context)`：

1. `_sample_settlement_click(C_RANDOM_DEFAULT)`（采样 #1 + click #1）
2. `time.sleep(_next_settlement_click_interval())`（序列内唯一允许的阻塞 sleep，
   `SETTLEMENT_CLICK_INTERVAL_RANGE` = `(0.7, 1.0)`，子类 RealmRaid `(0.65, 0.95)`）
3. `_sample_settlement_click(C_RANDOM_DEFAULT)`（**重新采样** #2 + click #2）
4. `timer.limit = _next_settlement_click_interval(); timer.reset()`（武装节流）

两次都是必须动作（不是 retry、不是「最多两次」、不是第一击后立即要求 `page_reward`）。
两次坐标分别独立采样（`ClickSampler.sample` 各调一次），禁止 sample-once-click-twice。
helper 不做 Page detection / is_win / exit_matcher / reward marker / retry / fatigue /
FrameWait。

### Generic Result Guard（`_is_generic_result_context`）

`return appear(I_WIN) or appear(I_DE_WIN) or appear(I_FALSE)`。这三个是「标准战斗结果
结算页」的无歧义正向标志。**更宽的 `I_BATTLE_STATE_INFO`（`page_battle_result` 基础
识别器 4 个成员之一）不纳入**——静态无法证明它出现的所有场景都适合强制双击（用户 spec
§5 明确「不要拍脑袋纳入」，允许「更保守的 first implementation」）。非 generic /
`settlement_click_timer` 已启动的帧 → 退回旧的单次 `_settlement_click(context)` 节流点击
（`C_RANDOM_DEFAULT`），行为等价现状。**positive guard，不用 Task 黑名单。**

### 新 Reward Handler 顺序（`_handle_reward`）

`context.is_win = True` → `click_record_clear`（首个 reward 帧）→
`if appear_then_click(I_OVER_GHOST, interval=0.8): return CONTINUE` →
`if appear_then_click(I_GB_SKIN_CONFIRM, interval=0.8): return CONTINUE` →
`_settlement_click(context, region=_select_reward_region())` → `CONTINUE`。

即：本轮确实点中特殊弹窗就**立即 `CONTINUE`**，下一轮 fresh screenshot 再判，不在同帧
继续 region click（新的 Action → Fresh State 边界）。旧代码是无条件两个都点、点中也不
早退——这是本轮有意的行为变更（spec §9）。

### Reward Layout Policy（`_select_reward_region`）

`if appear(I_GET_BATTLE_REWARD) or appear(I_GET_BATTLE_REWARD_2): return C_RANDOM_DEFAULT`
→ `if random_int(1, 100) <= 80: return C_RANDOM_SAVE_RIGHT` → `return C_RANDOM_SAVE_BOTTOM`。

`I_GET_BATTLE_REWARD` / `_2` 是 **Reward Layout Discriminator**——只在 `page_reward` 已
确认后判断点哪个安全区，不是 page recognizer / 点击目标 / 胜利标志，**不加入
`page_reward.recognizer`**。80/20 用项目统一 `module.base.utils.random.random_int(1,100)`
（`SystemRandom.randint`，闭区间），不新建 weighted-choice framework。

### 三个 Safe Region 的采样

`_sample_settlement_click(rule)`：`x, y = ClickSampler.sample(rule.roi_front)` →
`self.device.click(x=x, y=y, control_name=rule.name)`。**整 ROI 均匀（`LEGACY_UNIFORM`
默认策略 = `random_point_in_roi`），落点可静态证明必在 ROI 内。** 不做 HABIT 偏置
profile（缺人工点击数据，Level C 再标定），不复用旧 `_SETTLEMENT_*_PROFILE`。BehaviorTrace
`target` = `random_default` / `random_save_right` / `random_save_bottom`。

### Settlement Timer 交接

**只有一个 timer owner**（`context.settlement_click_timer`）。mandatory #2 之后按普通
settlement click 一样武装它（`limit = _next_settlement_click_interval(); reset()`）——
使下一 FSM 帧（仍 result 或已 reward）`timer.started() and not timer.reached()` → 被
`_settlement_click` 节流跳过（不出现意外第三击），同时页面若卡住能在一个间隔后恢复节流
点击。`_advance_generic_result` 只在 `settlement_click_timer` 未启动时触发（每个 battle
round 的首个结算帧一次），后续帧走单次节流。

### RD / RD2 全仓清理

| 类别 | 处理 |
|---|---|
| 生产 `general_battle.py` | `C_RANDOM_RD` / `C_RANDOM_RD2` / `_SETTLEMENT_PRIMARY_PROFILE` / `_SETTLEMENT_FALLBACK_PROFILE` 全删；`ClickProfile` + `STRATEGY_HABIT` import 删；加 `random_int` import。`grep C_RANDOM_RD` 只剩注释里「已移除」说明。 |
| asset `assets.py` | `C_RANDOM_RD` / `C_RANDOM_RD2` 已不在文件里（用户 WIP 已换成三个新区域 + 两个 marker + 两个 PNG）；本轮未再动 assets。 |
| 测试 `test_general_battle_settlement.py` | 重写为 Contract V3，37 → 54 用例。 |
| 测试 `test_general_battle_timing.py` | 2 处结算断言 `C_RANDOM_RD` → `C_RANDOM_DEFAULT`、`_sample_settlement_click` 由 2 参改 1 参；仍 17 用例。RealmRaid 相关测试不动。 |
| 分析器 `dev_tools/settlement_trace_check.py` + `tests/test_settlement_trace_check.py` | 按 3 区域名 + 整 ROI（margin 0）做**最小更新**（16 → 17 用例）；**不校验**双击时序结构与 80/20 分流——那是 V3 的 Level C 验收设计，另行处理。 |
| 护栏 `test_ryoutoppa_c_area_1_point_opt_in.py::SettlementUntouchedTest` | 改指新方法名，断言结算相关方法仍不碰 `sample_point` / `adapt_point_profile` / `STRATEGY_HABIT`；仍 25 用例。 |
| 文档 | `docs/DECISIONS.md` D016（新）+ D014 v2 条目标 Superseded；`docs/AI_CONTEXT.md` §4.3.1（新，详细契约）/ §4.39（新，log 条目）/ §4.28 标 Superseded / §4.27 解冻注 / §7 基线 741→759 / §2 WIP 说明；`docs/ARCHITECTURE.md` 通用战斗结算段重写 + HABIT 消费者更正 + Exploration V2→V3；`docs/ROADMAP.md`（见下）。 |

### Task Compatibility

| Task | `_handle_result` | `_handle_reward` | 新公共策略影响 | 结果 |
|---|---|---|---|---|
| 基类 GeneralBattle 直接用户 | 基类 | 基类 | 通用结果首帧强制双击 + reward 布局分区 | 新行为 |
| RealmRaid | override：quick_exit → 直接 EXIT 不点结算；否则 `super()` | 基类 | 非 quick_exit 分支经 guard 走强制双击（自己的 `(0.65,0.95)` 间隔） | 新行为（非 quick_exit）/ 不变（quick_exit） |
| ActivityShikigami base_act | override：boss 点 `I_UI_BACK_RED` → `super()` | 基类 | `super()` 后经 guard 走新策略 | 新行为 |
| HeroTest | override：`I_BCMJ_SKILL_ADD_CONFIRM` → 特殊技能等待 `CONTINUE`；否则 `super()` | 基类 | 非 skill-add 分支经 guard 走新策略 | 新行为（非 skill-add） |
| Orochi | override：关活动弹窗 → `CONTINUE`；否则 `super()` | override：关弹窗 / LEADER 邀请 → `CONTINUE`；否则 `super()` | `super()` 后走新策略 | 新行为 |
| EternitySea / EvoZone | 基类 | override：LEADER 邀请 → `CONTINUE`；否则 `super()` | reward `super()` 走新布局分区 | 新行为 |
| BondlingFairyland | **override，全私有**（`I_CAP_AGAIN` / `I_BATTLE_FAIL_ABANDON` + `random_click()`），不 `super()` | override → `super()`，保留 `is_win` | result **不被公共双击穿透**；reward 走新布局分区 | result 不变 / reward 新行为 |
| SixRealms moon_sea / peacock_kingdom | **override，全私有**（放弃 / 确认 / 选技能 + `random_click()`），不 `super()` | **override，全私有**（`random_click()`），不 `super()` | 完全不受影响 | 不变 |
| RyouToppa / Exploration / FallenSun / Dokan | 不 override（`__dict__` 无） | 不 override | 走基类新策略 | 新行为 |

private override 靠「不 `super()`」天然不被穿透——**未加任何 Task 黑名单**。

### is_win / exit_matcher / missing fallback

未变：`context.is_win = not appear(I_FALSE)`（result）/ `= True`（reward）；base
`_exit_matcher()` 仍 `None`；`_handle_missing_battle_page` 的 `time.time() -
reward_no_battle_ts >= 2.5` 兜底原样；`run_general_battle` FSM 结构原样。新点击 policy
只决定「怎么推进结算」，不改「谁赢谁输」「何时正式结束」。`random_click()`（navigation）
与 Settlement Policy 分离——`C_RANDOM_SAVE_*` 不接入 `random_click`（`default_pages.py`
里搜不到 `random_save_*` / `C_RANDOM_SAVE`）。

### 未参与（spec §17-20 硬边界）

`confirm_delay` / `reaction_delay` / `appear_then_click`（三个安全区是 Large Safe
Region）；`FatigueManager.try_break`（不进结算序列、不插 #1 / #2 之间）；FrameWait /
changed-stable（reward 动画由 mandatory 第二击这个业务动作推进，不用视觉等待）；
retry primitive / `max_attempts` / `timeout`（mandatory double 是 Action Sequence 不是
retry）。

### 测试

- `toolkit/python.exe -m unittest tests.test_general_battle_settlement`：**54/54 OK**。
- `toolkit/python.exe -m unittest tests.test_general_battle_timing`：**17/17 OK**。
- `toolkit/python.exe -m unittest tests.test_settlement_trace_check`：**17/17 OK**。
- `toolkit/python.exe -m unittest tests.test_ryoutoppa_c_area_1_point_opt_in`：**25/25 OK**。
- `toolkit/python.exe -m compileall -q`（改动的 5 个 py）：OK。
- `toolkit/python.exe -m unittest discover -s tests`：**759/759 OK**（741 → 759，+18：
  settlement 37→54、trace-check 16→17）。**无本轮新增失败。**
- `git diff --check`：`tasks/Component/GeneralBattle/general_battle.py` 与
  `tests/test_general_battle_timing.py` 干净。仓库级 non-zero 全部来自既有用户 WIP
  `tasks/Component/GeneralBattle/assets.py` 的行尾空格（自动生成资产风格）+ 若干 `*.json`
  的 CRLF——**非本轮引入**（`assets.py` 本轮未改）。
- 未启动 MuMu / 游戏 / OAS / OASX / ADB / OCR RPC / server。

### Production Impact

- **改动只在 `tasks/Component/GeneralBattle/general_battle.py`**（唯一生产文件）。真实行为
  变化：① 通用结果页首帧从「timer 节流单次点 RD」变成「强制两次点 `C_RANDOM_DEFAULT`
  + 中间一次阻塞 sleep」；② reward 页命中特殊弹窗后本帧立即 `CONTINUE`（旧版会继续 region
  click）；③ reward 页非弹窗帧按 `I_GET_BATTLE_REWARD` marker 选 DEFAULT / RIGHT·BOTTOM
  区域（旧版恒点 RD）；④ 点击区域从 `C_RANDOM_RD` `(699,397,574,314)` HABIT 偏置改为三个
  新安全区整 ROI 均匀。private override 任务（BondlingFairyland result / SixRealms）零影响。
- **仍需 Level C MuMu 真机验收**（见下）。

### Level C 待验证

1. `SETTLEMENT_CLICK_INTERVAL_RANGE = (0.7, 1.0)` 是否是最合适的两击间隔。
2. `C_RANDOM_DEFAULT` `(742,430,362,230)` 新 ROI 的实际安全性（不误触返回 / 分享 / 其它按钮）。
3. `I_GET_BATTLE_REWARD` / `I_GET_BATTLE_REWARD_2` 两种奖励布局识别稳定性。
4. marker miss 时 80% RIGHT / 20% BOTTOM fallback 是否覆盖绝大多数剩余布局。
5. 特殊任务真实战后 UI 有无遗漏（本轮按静态源码判定 super() / private）。
6. `I_BATTLE_STATE_INFO`-only 结果帧是否需要也纳入强制双击（本轮保守排除）。
7. 新契约的 BehaviorTrace Level C 分析器（识别双击时序结构 + 80/20 分流）——另行设计。

### Git

- 未 commit、未 push、未 merge、未 reset、未 stash、未真机测试。分支 `master`，HEAD 仍为
  `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-03 - KekkaiUtilize 蹭卡 / 好友寄养流程重新审查

用户要求重新把「现在 KekkaiUtilize 到底怎么找卡 / 选卡 / 切区 / 判收益 / 滑动 / 回选 /
寄养 / 失败恢复」讲清楚，并与「跨区优先 → 同屏六星候选逐个查实际收益 → 找到满足条件立即
寄养 → 跨区到底后同区继续」的人工流程做 Gap 对比。**纯只读审查——`tasks/KekkaiUtilize/`
diff = 0，未改任何生产代码 / 测试；未接 FrameWait；未动 `swipe_adb` / lazy 概率 / 阈值 /
failure backoff / 随机分布 / 任务调度。** 完整报告 `docs/KekkaiUtilize蹭卡流程重新审查.md`
（30 节：状态图 A/B、Gap Matrix 16 项、逐函数解析、最小重构边界、Level C 待确认）。

### 结论：PARTIAL

蹭卡状态机骨架大体到位——有界扫描（`range(21)` + `Timer(120)` + `CONSEC_MISS=3` +
`I_U_EMPTY_CARD` 四重界）、逐张点开读收益（`click(C_SELECT_CARD)` → `sleep(2)` →
`check_card_num` OCR `O_CARD_NUM` 固定 ROI）、跨区/同区双分组（`run_utilize`
`enumerate((friend, fallback_friend))`）、按收益值而非位置回选（`_reselect_best_card`）、
寄养两层真实 verify（`set_shikigami` 内 `not appear(I_U_ADD_1/2)` + 下一轮 `check_utilize_add`
`not appear(I_UTILIZE_ADD)` + 读 `O_UTILIZE_RES_TIME`）、**不依赖好友名 OCR / 控件树 /
好友身份**、每轮 fresh screenshot、随机源已统一到公共 `random_int` / `random_delay`。

### 三大差异（CURRENT → TARGET）

1. **跨区 / 同区顺序**：CURRENT = `config.kekkai_utilize.utilize_config.select_friend_list`
   决定优先分组，`config.py` 默认 `SelectFriendList.SAME_SERVER`（同区）。TARGET = 跨区固定
   优先。→ 改 config 默认为 `DIFFERENT_SERVER`，或 `run_utilize` 硬编码
   `(DIFFERENT_SERVER, SAME_SERVER)`。
2. **同屏扫描顺序**：CURRENT = `ImageGrid.find_everyone` 把所有命中的 tier 图标按屏幕 y 升序
   返回；`order_cards` / `order_targets` 顺序只用于 `_card_rank`（挑最优卡），**不影响
   `_current_select_best` 的点击顺序**——会先点物理靠上的 4 星再点靠下的 6 星（除非该类型 6 星
   已被点开确认满值触发 `maxed_card_classes` / `confirmed_highest_stars` 剪枝）。TARGET =
   同屏内优先检查六星。→ `_current_select_best` 遍历 `cards` 前按 `CARD_TIER_INFO[..][1]`
   星级降序排序。
3. **默认收益阈值**：CURRENT = `taiko_reward_threshold=76` / `fish_reward_threshold=151`
   （六星满值，`config.py` 注释「等价于改动前只有命中理论最高收益才提前停止」）。
   `_reaches_reward_threshold` 命中 → `return True` 立即停并进结界，但满值卡罕见 → 实际几乎
   总走「扫完整列表 + `_reselect_best_card` 回到顶部按收益值回选最优」（= option C，不是
   「第一张满足即用」）。TARGET = 找到满足条件就立即寄养，不要求先扫全找理论最优。→ 默认
   阈值改「可接受收益」（需产品定值，Level C 参考真实收益分布，**本轮不改阈值**）+ 让「命中
   阈值即寄养」成主路径、弱化或按分支限定 `_reselect_best_card`。

### Gap Matrix（16 项摘要）

已实现：当前屏多候选逐个检查、点击后读实际收益、按收益值匹配、当前屏检查完再滑、
跨区到底切同区（顺序取决于配置）、同区扫到底、不依赖好友名 OCR、bounded loop、
fresh screenshot、utilize success verify（两层，`run_utilize` return True 是乐观的、
权威闭环在下一轮 `check_utilize_add`）。
当前逻辑相反：跨区优先（默认同区先）。
部分实现：满足立即寄养（机制在、默认阈值取向使其=扫全+回选）、不依赖首次列表稳定排序
（`_reselect_best_card` 按值匹配鲁棒，但 `_current_select_best` OCR 失败的最后一张会残留
「侧栏已选中它」而 `utilize_last_*` 未更新 → `already_selected` 误判可能带错卡进结界）。
未实现：detail load verify（固定 `sleep(2)`）、swipe stable verify（`swipe_adb` 后固定
`sleep(2)`，`SWIPE_DISTANCE=416` 未真机核）——Level C，本轮禁止接 FrameWait。

### 其它事实

- **GeneralBattle V3 与 KekkaiUtilize 无任何调用 / 继承关系**（MRO 不含 `GeneralBattle`：
  `ScriptTask → GameUi → ChessBattleNavigationMixin → ReplaceShikigami → BaseTask → ...`；
  `grep GeneralBattle|run_general_battle|_handle_result|Settlement|C_RANDOM tasks/KekkaiUtilize/`
  零命中）。本轮重做蹭卡属独立业务状态机调整。
- **BehaviorTrace 覆盖**：`self.click(C_SELECT_CARD)` / `switch_friend_list` 的
  `self.device.click` / `_reset_utilize_friend_list` 的 `self.swipe(S_U_END)` 都走
  `Control` → 有 trace；**`perform_swipe_action` 的 `self.device.swipe_adb(p1,p2,duration=2)`
  列表翻页直连、绕过 `Control.swipe` → 无 trace**（`control.py:189` 注释「v1 不覆盖」，
  ROADMAP T5-1 已记）。
- **check_utilize_add 出口 1**（`utilize_add_count >= 5` → `set_next_run(now+5min)` →
  `return True`）与失败路径（`_record_utilize_failure` / `_finish_low_value_utilize` →
  `return False`）语义方向相反——`return True` 让 `run()` 继续做维护（收菜 / 收盒子 / 收寮
  资源），`return False` 让 `run()` 早退。**不是 bug**（5 轮没蹭上仍想收菜合理），只是
  True/False 在这里表达「run() 要不要继续」而非「蹭卡成没成」（旧收口 / cleanup 批次 1
  已记 deferred）。
- **`_reset_utilize_friend_list` 里 `self.swipe(S_U_END, interval=3)`**（滚到列表顶）走
  `Control.swipe`，与 `perform_swipe_action` 的 `swipe_adb` 是两条不同路径。

### 最小重构边界（下一轮，不重写整个 KekkaiUtilize）

只需改 3 个函数 + 1 个 config 默认：`run_utilize`（头部分组顺序）、`_current_select_best`
（for 循环：同屏按星级降序 + OCR 失败同步 `utilize_last_*`）、`_select_optimal_resource_card`
后半 / `_reselect_best_card`（存废，让命中阈值即寄养成主路径）、`config.py`
（`select_friend_list` 默认；`taiko/fish_reward_threshold` 默认待产品定，本轮不改）。
`check_card_num` / `order_targets` / `CARD_TIER_INFO` / `switch_friend_list` /
`_reset_utilize_friend_list` / `perform_swipe_action` / failure recovery / 寄养 verify /
lazy 模式 —— 不动。

### 测试

**只读——未新增 / 未修改。** 现有 `tests/test_kekkai_utilize_state.py`（23）+
`tests/test_kekkai_utilize_threshold.py`（25）已充分锁定当前 WIP 的控制流 / 边界 / 参数 /
阈值语义，且与源码一致（随本 WIP 一起写）。下一轮真正重构时同步更新这两个文件（补：同屏
按星级排序后的遍历顺序、OCR 失败不带错卡、命中阈值即寄养为主路径、跨区固定优先）。

### Production Impact

- **0。** `tasks/KekkaiUtilize/` 工作树 diff 与审查开始时完全一致（`config.py` `+4` /
  `script_task.py` `+205/-46`，均既有 2026-08-30 WIP）。未跑测试（零代码改动）。

### Git

- 未 commit、未 push、未 merge、未 reset、未 stash、未真机测试。分支 `master`，HEAD 仍为
  `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-03 - KekkaiUtilize 单向分区搜索改造（取消蛇形 / PASS 序列 / 阶段化阈值）

正式业务搜索策略变更。把非怠惰路径的好友结界卡搜索从「扫全列表 + 记 global-best +
`_reselect_best_card` 回到顶部按收益值回选」改成「按 PASS 序列，每个 PASS 都 TOP→BOTTOM
单向扫描、命中阈值立即寄养、最后一个 PASS 兼任兜底」。长期契约见 `docs/DECISIONS.md`
**D017**。怠惰模式（`_run_lazy_utilize` / `_select_lazy_resource_card`）行为不变。

### 新搜索流程

**优先跨区**（`config.select_friend_list == DIFFERENT_SERVER`）：

```
PASS 1  跨区  stars={6}    threshold=HIGH   final=False
PASS 2  同区  stars={6}    threshold=HIGH   final=False
  ── 阈值降低一档（只降一次）──
PASS 3  跨区  stars={5,6}  threshold=LOWER  final=False
PASS 4  同区  stars={5,6}  threshold=LOWER  final=True   ← 本身兼任 fallback
```

**优先同区**（默认 `SAME_SERVER`）：

```
PASS 1  同区  stars={6}    threshold=HIGH   final=False
PASS 2  跨区  stars={6}    threshold=HIGH   final=False
  ── 阈值降低一档（只降一次）──
PASS 3  同区  stars={5,6}  threshold=LOWER  final=True   ← 本身兼任 fallback
```

即 跨→同→跨→同 / 同→跨→同。每个 PASS 之前 `_reset_utilize_friend_list(group)` 把列表切回
该分组顶部（利用「切区回顶」，而不是反向 swipe / TOP marker / 蛇形）。**没有额外的第四种
FALLBACK_SEARCH 轮次**——最后一个 PASS 自身就是兜底。

### 单个 PASS（`_run_search_pass`）

```
Timer(SEARCH_PASS_TIMEOUT=120) + for screen in range(SEARCH_MAX_SWIPES=20 + 1):
  screenshot → search_pass.targets.find_everyone(...)
  for (target,_,area) in cards:               # 当前屏候选按 y 位置从上到下
     C_SELECT_CARD.roi_front = area; click; sleep(DETAIL_LOAD_WAIT=2)
     clicked_any = True
     card_type, card_value = check_card_num()  # 复用现有 OCR，不改
     unknown / value<=0 → 跳过该候选继续下一张（不做无限重读）
     _card_meets_pass(card_type, card_value, pass)? → return (HIT, clicked_any)   # 命中阈值立即结束
  appear(I_U_EMPTY_CARD)?                       # 只有它才是「真正到底」
     final_fallback and clicked_any → return (FINAL_USE_LAST, clicked_any)
     否则 → return (PASS_MISS, clicked_any)
  screen == SEARCH_MAX_SWIPES → break
  perform_swipe_action()                        # 向下滑一屏
return (ABORT, clicked_any)                     # 达到滑动上限仍没见到底部 marker
```

**关键：「当前屏没有本 PASS 的目标模板」绝不等于「到底」**。好友列表乱序（6★/4★/太阴 交错），
中间某屏没有目标只说明这一屏没候选，`perform_swipe_action` 继续向下。**旧代码的
`miss_count > CONSEC_MISS → 当作到底` 语义已从标准路径移除**（怠惰路径 §15 豁免，保持原样）。

### 最终兜底（FINAL PASS）

最后一个 PASS 扫到 `I_U_EMPTY_CARD`：
- 本 PASS **至少点开过一个候选**（`clicked_any=True`）→ `FINAL_USE_LAST`：不再检查阈值 / 不
  重新搜索 / 不回头 / 不保存坐标·好友名·页码 / 不重新定位——直接用「最后一次点击、仍保持
  选中」的候选进入好友结界寄养。
- **一张候选都没点开过**（`clicked_any=False`）→ `PASS_MISS` → `_run_search` 返回 False →
  `run_utilize` 走 `_record_utilize_failure`（外层 3 次上限的重试链），**不盲目点【进入结界】**。

`has_clicked_candidate` 只是 PASS 内一个局部 bool，不保存坐标 / 好友身份 / 页号 / 行号 /
candidate history。

### 收益降档（`lower_reward_tier`，`tasks/KekkaiUtilize/utils.py`）

真实离散奖励档位：斗鱼 `(101,109,118,126,134,143,151)`、太鼓 `(42,50,59,67,76)`。
`lower_reward_tier(value, tiers)` = 「严格小于 value 的最大真实档位；没有更低档则保持最低档」。
例：斗鱼 151→143 / 150→143 / 144→143 / 143→134 / 130→126 / 109→101 / 101→101；
太鼓 77→76 / 76→67 / 42→42。**不是 `threshold - 固定数字`**。只在第一阶段（6★HIGH）全部失败
后调用一次，把第二阶段（5/6★）阈值降低一档（PASS 3 和 PASS 4 共用同一份 lower map，不二次降）。

### 星级过滤（`_pass_targets(stars)`）

按 `stars` + `utilize_rule` 组 `ImageGrid`：
- `{6}` → DEFAULT `[I_U_FISH_6, I_U_TAIKO_6]` / FISH `[I_U_FISH_6]` / TAIKO `[I_U_TAIKO_6]`
- `{5,6}` → DEFAULT `[FISH_6, TAIKO_6, FISH_5, TAIKO_5]` / FISH `[FISH_6, FISH_5]` / TAIKO `[TAIKO_6, TAIKO_5]`

第一阶段**不扫 5★、不扫 4★**。真实奖励档位与星级不一一对应（6★斗鱼也可能只有 118），所以
第二阶段必须 5★+6★ 都扫。

### 复用 / 未改

- **识别基础设施不变**：`ImageGrid.find_everyone`（card-column `roi_back` + 当前帧真实 bbox +
  按 y 排序）、`C_SELECT_CARD.roi_front = area` 动态点击、`check_card_num()` OCR 系统——全部
  照旧。不引入好友行 anchor / 固定第 1/2/3/4 行 / 好友名 OCR / 新列表检测器 / TOP 搜索框。
  用户 WIP 新加的 `I_K_SEARCH`（「结界卡顶部搜索框」）asset **未接线**（spec 明令不用 TOP
  marker / 搜索框模板）。
- **swipe 不变**：`perform_swipe_action` 仍 `self.device.swipe_adb(p1, p2, duration=2)` 直连
  （不进 BehaviorTrace）、`SWIPE_DISTANCE=416`、几何不变。**没有 ADB→minitouch 迁移**（独立
  Level C 后续项）。`_reset_utilize_friend_list` 的 `self.swipe(S_U_END, interval=3)` 走
  `Control.swipe` 不变。
- **未接 FrameWait**：详情加载 / swipe 停稳仍是固定 `sleep(2)`（`DETAIL_LOAD_WAIT`）。
- **未改结界卡 ROI**（`image.json` / `assets.py` 的 `I_U_*` roi 不动；`I_K_SEARCH` 是用户 WIP）。
- **未改 config**：沿用 `select_friend_list`（优先分组）+ `taiko_reward_threshold` /
  `fish_reward_threshold`（HIGH 阈值），没有新增配置项。
- `check_utilize_add` / `switch_friend_list` / `_reset_utilize_friend_list` /
  `_record_utilize_failure` / 寄养 verify（`set_shikigami` 内 `not appear(I_U_ADD_*)` + 下一轮
  `not appear(I_UTILIZE_ADD)`）/ `_finish_low_value_utilize`（消息文案「四星」→「五星」）——
  照旧。

### 删除的旧标准路径（已确认零消费者）

`_select_optimal_resource_card` / `_current_select_best` / `_reselect_best_card`（global-best +
按值回选）/ `_card_rank` / `order_cards` / `order_targets`（KU 版；`KekkaiActivation` 有自己的
完整 override，不受影响）/ `_reward_threshold` / `_reaches_reward_threshold`；类属性
`utilize_best_rank/value/card_class`、`utilize_last_card_class/value`、`ap_max_num`、
`jade_max_num`（及 `run()` 里对后两者的重置）。`KekkaiActivation`（`class ScriptTask(KU, ...)`）
grep 确认不引用其中任何一个（只自带 `order_targets` override）。

### BOTTOM 与安全上限（明确区分）

- **真正到底**（→ `PASS_MISS` / `FINAL_USE_LAST`）：`appear(I_U_EMPTY_CARD)`。
- **安全中止**（→ `ABORT`，外层按失败重试，**不当作到底**）：`Timer(SEARCH_PASS_TIMEOUT=120)`
  超时 / `for` 跑满 `SEARCH_MAX_SWIPES=20` 屏仍没见到 `I_U_EMPTY_CARD` / `_reset_utilize_friend_list`
  抛 `GamePageUnknownError`。
- `I_U_EMPTY_CARD` 是否 100% 表示「列表已到底」当前**源码无法证明**，沿用现有兼容行为，
  列为 Level C 待验收（见下）。

### 新增 helper / 结构

- `tasks/KekkaiUtilize/utils.py`：`FISH_REWARD_TIERS` / `TAIKO_REWARD_TIERS` / `lower_reward_tier`。
- `tasks/KekkaiUtilize/script_task.py`：`PassResult`（str Enum：hit / pass_miss / final_use_last /
  abort）、`SearchPass`（dataclass：friend_group / stars / threshold_map / final_fallback /
  targets）、`_rule_card_types` / `_pass_targets` / `_card_type_matches_rule` / `_card_meets_pass` /
  `_build_search_passes` / `_run_search` / `_run_search_pass` / `_run_lazy_utilize`。

### 测试

- `tests/test_kekkai_utilize_threshold.py`：25→26。重写为新契约——`LowerRewardTierTest`
  （斗鱼/太鼓完整档位阶梯、非档位输入、低于最低档、只降一次）、`CardMeetsPassTest`
  （阈值边界、rule 过滤、unknown/0、高阈值拒低 6★、`_rule_card_types`）、保留 `CARD_TIER_INFO`
  单调 + config 拒非正值 + 剩余时间兜底 + switch timeout。删 `_reward_threshold` /
  `_reaches_reward_threshold` / `_card_rank` 相关测试。
- `tests/test_kekkai_utilize_state.py`：23→46。新增 `BuildSearchPassesTest`（跨区优先 4 PASS /
  同区优先 3 PASS / 只有最后一个 final / 降档只一次且 PASS3≡PASS4 lower / 第一阶段仅 6★ /
  第二阶段 5+6★ / rule 过滤模板）、`RunSearchSequenceTest`（第一 PASS 命中即停后续分组不执行 /
  第二 PASS 命中不进 lower 阶段 / FINAL_USE_LAST → True / 全 PASS_MISS 无候选 → None / 有候选
  无 final-use → False / ABORT 立即 bail）、`RunSearchPassTest`（命中即停且同屏继续查下一张 /
  空屏继续下滑不当作到底 / final 到底用最后候选（A/B/C 都点过）/ final 无候选到底 → PASS_MISS
  不盲目进结界 / 普通 PASS 到底不达标 → PASS_MISS 换下一 PASS / MAX_SWIPES=ABORT≠BOTTOM /
  OCR unknown 跳过但计入 clicked）、`LazyModeUntouchedTest`。删 `_current_select_best` /
  `_reselect_best_card` 双界测试，更新 `run_utilize` 分派与 detail-wait 断言。
- **回归**：`toolkit/python.exe -m unittest discover -s tests` → **783/783 OK**（759 → 783，
  +24：state 23→46、threshold 25→26）。`compileall -q`：OK。
  `git diff --check`（`script_task.py` + `utils.py`）：干净。仓库级 non-zero 全部来自既有用户
  WIP（`image.json` CRLF、GeneralBattle `assets.py` 行尾空格），非本轮。
- 未启动 MuMu / 游戏 / OCR server / ADB / OASX。

### Production Impact

**实际行为变化**（仅非怠惰路径）：
1. 分组顺序从「优先分组 → 备选分组（选中即停）」变成固定的 PASS 序列（跨→同→跨→同 或
   同→跨→同），且**同一分组会在两个阶段各扫一次**（6★ 一次、5/6★ 一次）。
2. 第一阶段只点 6★（不再点 4★/5★）；第二阶段点 5★+6★（不再点 4★）。
3. 命中「本 PASS 阈值」立即寄养，不再「扫全列表找理论最优 + 回选」。
4. 第一阶段全失败后阈值降低**一档**（离散档位，不是减固定数）再扫一遍。
5. 最后一个 PASS 扫到底仍无达标 → 直接用最后一次点击的候选寄养（旧代码这里会回选或失败）。
6. 「连续几屏没有目标模板」不再中断扫描（旧代码 `miss_count > 3` 会提前判到底）。
怠惰路径、`check_utilize_add` 主循环、寄养 verify、failure recovery、剩余时间调度、
`KekkaiActivation` —— 零影响。

### Level C 待验收（未真机，不得标 VERIFIED）

1. `I_U_EMPTY_CARD` 是否 100% 表示「好友结界卡列表已到底」（当前作为唯一 BOTTOM marker）。
2. 切换同区 / 跨区后列表是否稳定回到 TOP（PASS 序列依赖「切区回顶」）。
3. 当前正向 ADB swipe（`SWIPE_DISTANCE=416`、`duration=2`）是否仍覆盖所有候选、不漏不重。
4. card-column ROI 是否需要扩大（旧审查见 ~400-450px vs swipe 416px，冗余很小）——本轮未捆绑。
5. 后续 ADB→minitouch 的实际滚动量 / 惯性 / 帧间重叠（独立 Level C 项）。
6. 最后一轮扫到底后，「最后一次点击的候选」是否稳定保持选中状态（FINAL_USE_LAST 依赖它）。
7. `SEARCH_MAX_SWIPES=20` 是否足够在正常好友列表里滑到 `I_U_EMPTY_CARD`。
8. 极低概率「列表卡种与详情卡种不一致」（点击斗鱼、详情变太鼓）——本轮按当前详情 OCR 结果
   判断，未加复杂 recovery；若 Level C 日志证明影响生产稳定性再单独加有限兜底。

### Git

- 未 commit、未 push、未 merge、未 reset、未 stash、未真机测试。分支 `master`，HEAD 仍为
  `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-03 - Minitouch 自定义轨迹能力专项审查

纯只读源码审查——**未改任何代码、未接 KekkaiUtilize、未启动 MuMu、未真机**。
`module/device/method/minitouch.py` 对 HEAD 零 diff。完整报告 `docs/Minitouch自定义轨迹能力审查.md`（12 节 + 源码位置索引）。

### 结论

- **协议层 = YES（已完全具备）**：`Command`（`d/m/u/w/c/r` 逐字序列化）+ `CommandBuilder`
  （通用流式构造器 `down/move/up/wait/commit/clear`）。`m {contact} {x} {y} {pressure}`
  接受任意 x/y、**无「x 必须不变」限制**；`.wait(ms)` 可逐段独立；`down → (move.commit
  .wait(dt))* → wait(short) → up → commit` 今天就能表达。`CommandBuilder` docstring 本身
  给出 `down→move→move→up` 自定义用法示例。
- **当前执行层 = PARTIAL**：`swipe_minitouch` / `drag_minitouch` / `_press_and_drag_minitouch`
  （Chess）**已经**在逐点发 MOVE、每个 MOVE 独立 `wait(random_int(6,15))`（循环内重新采样，
  非共享值）、路径是三次贝塞尔曲线（`insert_swipe`，非直线、非仅端点、已有轻微 x 摆动）；
  `drag` / `press_and_drag` 尾部已有 `move(p2).wait(140)×2` 的 UP 前停顿。**但路径生成与
  逐段 dt 写死在 `insert_swipe` + 内联 for 循环里**，没有任何方法接受调用方传入的
  点列表 / 逐段 dt 列表。
- **当前公开 swipe API = PARTIAL（对自定义轨迹 = NO）**：`Control.swipe(p1, p2, duration=...)`
  / `BaseTask.swipe(RuleSwipe)` / `Control.swipe_vector` / `Control.drag` 只接受起终点
  （+ vector / shake 派生参数）。`duration` 在 minitouch 后端被忽略（D003 / §4.14）。
  **没有 `execute_trajectory(points)` / `swipe_path(points)` / `move_to` / `gesture` 类
  公开方法。**

### 调用链

`BaseTask.swipe(RuleSwipe)` → `swipe.coord()`（只出端点，D006）→ `Control.swipe(p1,p2,
duration,...)` → 按 `config.script.device.control_method` 分派 → `minitouch` →
`Minitouch.swipe_minitouch(p1,p2)`（`@retry`）→ `insert_swipe`（贝塞尔）→
`self.minitouch_builder`（`CommandBuilder`）→ `down.commit` / `[move.commit.wait(6-15)]` /
`up.commit` → 各 `minitouch_send()`（整批一次 `sendall()` / `ws.send`，主机 `sleep(Σw/1000
+ 0.05)`）→ minitouch server。BehaviorTrace 在 `Control.swipe` 记 `ACTION`/`swipe`（端点级，
不记 MOVE）。`KekkaiUtilize` / `KekkaiActivation` 的 `swipe_adb` 直连不经此链。

### 缺失能力（要 `TouchSwipeModel` 输出 `points + per-segment dt`）

全是**管线 / 封装**，不是协议：① 接受点列表的公开 API；② 迭代调用方 `[(x,y,dt)]` 的
minitouch executor；③（可选）per-segment pressure 透传（当前 swipe/drag 的 `move()` 不传
pressure，默认 100）；④（可选）「UP 前短暂停顿」参数。**都不需要改 `Command` /
`CommandBuilder` / `minitouch_send` / 握手。**

### ±X / 曲线 / 时间控制

- ±X / 曲线：协议允许任意 x/y；当前无「x 不变」限制；`insert_swipe` 本身已产生曲线；
  自定义 points 天然支持左偏 / 右偏 / 尾部小修正。现成 `smooth_path(points, offset_range)`
  （minitouch.py，**当前无调用方**）= 「给点列表加 ±横向偏移」工具。
- 时间控制：逐段 dt（`move().commit().wait(dt_i)`，当前已逐 MOVE 独立）、加速 / 主运动 /
  减速 / 尾部密化、总时长不依赖单独固定值（minitouch 忽略 `duration`，总时长 = Σw）、
  UP 前短停顿（`drag` 已有）—— **全部能**。唯一限制：整批 fire-and-forget，主机不在轨迹
  中途观察 / 修正（对「先生成再执行」的模型无影响）。

### 现有优化核验（当前源码为准）

`click_minitouch` = `DOWN → wait(_humanized_dwell()) → UP`，**无 ±2px MOVE** ✅；
`_humanized_dwell()` = `round(random_triangular(45,130,65))`（`SystemRandom`）✅；
`_humanized_pressure()` = `random_int(max(1, top//2), top)`，`max_pressure<=0` → 1 ✅；
swipe/drag MOVE interval `random_int(6,15)` 逐 MOVE 独立（`SystemRandom.randint`）✅；
`insert_swipe` 控制点 / `t` 分布仍 `np.random`（D007 有意保留）⚠️；drag 尾部 `wait(140)×2`
固定（D002 有意保留）⚠️。MuMu 握手 `^ 10 540 960 0` → `max_pressure=0` → 夹为 1 →
pressure 恒 1，**MuMu 下 pressure 只是合法协议常量、无业务行为**。

### 推荐接入架构：Plan B

`TouchSwipeModel`（新，纯轨迹数据，可单测、不 import device）→
`Minitouch.swipe_minitouch_trajectory(points)`（新 executor，~10-15 行 `@retry`，照
`_press_and_drag_minitouch` 写法）→ `Control.swipe_trajectory(points, control_name)`
（新入口，minitouch 分派 + BehaviorTrace 一行）。**协议层 / `CommandBuilder` /
`minitouch_send` / `Control.swipe` / `BaseTask.swipe` / `RuleSwipe` 一律不动。** 否决
Plan A（协议进模型、不可测、锁后端）、Plan C（改共享 `swipe()` = 全项目滑动行为变，
污染 control layer）。

### 文档同步

- AI_CONTEXT.md：已更新（§8.2 补一条「协议层已确认支持自定义多点轨迹，缺薄 executor +
  公开 API，Plan B」）。
- DEVELOP_LOG.md：本条。
- ROADMAP.md：已更新（「已完成」新增审查行；Level A/B 区新增「`TouchSwipeModel` 接入（Plan B）」
  最小拆分）。
- ARCHITECTURE.md：无需更新（swipe 调用链已在 §3；未形成新分层 / 新结构，只是确认既有
  `CommandBuilder` 的通用性）。
- DECISIONS.md：无需更新（审查 + 推荐，未形成「已接受」决策；D002 / D003 / D006 / D007
  均未推翻、未新增。`TouchSwipeModel` 真正实施若形成契约再补 ADR）。
- TESTING.md：无需更新（未改测试分级 / 验证规则 / 真机要求）。

### Git

- 未 commit、未 push、未 merge、未 reset、未 stash、未真机测试。分支 `master`，HEAD 仍为
  `2cdf3a0571b0449748aabef259da5cbd2378536c`。

## 2026-09-04 - TouchSwipeModel 第一阶段实现（Plan B 基础设施）

承 `docs/Minitouch自定义轨迹能力审查.md`（2026-09-03）的 Plan B，落地「模型出纯轨迹数据 →
minitouch 薄执行层 → 显式 `Control.swipe_trajectory` 入口」三层基础设施。长期契约
`docs/DECISIONS.md` **D018**。**只建基础设施 —— 未接任何任务、未接 `BaseTask`、未启动
MuMu、未真机。** 回归 **783 → 836**（+53）。

### 新增文件

- **`module/device/touch_swipe_model.py`**（纯逻辑，不 import device / `Config` / `BaseTask`）
  - `TouchSwipeModel(params=None, rng=None).generate(start, end) -> list[(x, y, dt_ms)]`。
  - 运动学：位置进度 = minimum-jerk `s(t) = 10t³ - 15t⁴ + 6t⁵`（`s(0)=0` / `s(1)=1` /
    `s'(0)=s'(1)=0` / `s'` 在 `t=0.5` 最大 → 起步慢、中段快、收尾慢）。
  - 横向曲率 = 整体函数 `curve_amp · sin(πt)`（两端 0、中间最大）；`curve_amp` 一次采样、
    可正可负，绝对值受 `min(max_curve_px, dist·curve_px_ratio)` 约束 → 支持左弯 / 右弯 /
    近直线，无逐点抖动 → 不锯齿、不蛇形。
  - 逐段 `dt` = `base_dt_ms × (1 + end_slow_ratio·(1 - sin(πt)))` + 有界抖动
    `rng.randint(±dt_jitter_ms)`，夹在 `[min_dt_ms, max_dt_ms]`。空间 minimum-jerk +
    时间两端放慢共同形成「前慢 → 中快 → 后慢」。
  - MOVE 点数 = `round(dist / avg_step_px)`，夹 `[min_points, max_points]`，且 `<= 距离像素数`。
  - `dt_ms` 语义固定为「到达当前点之后、下一次移动之前的停留」；第 0 点是落点，其 dt 恒
    0 且被执行层忽略（第一版不加按压前置停顿）。起终点强制精确（取整后 == 输入）。
  - `TouchSwipeParams`（frozen dataclass，`__post_init__` 校验）持有全部可调项。
  - `_DefaultRng` 委托公共 `random_int`（D007：不新建 SystemRandom、不引入可 seed 的全局
    `random`）；`rng=` 可注入确定性实现供单测复现。
  - 距离 `< 2px` / 非有限坐标 / 非 `(x, y)` / bool 坐标 → `ValueError`。
  - 可选尾部微修正 `tail_correction_*`：**默认关**；开启时小概率触发、幅度小（`±max_px`）、
    末段 `sin` 回到 0 —— 不改终点、不反向、不改主方向。
- **`tests/test_touch_swipe_model.py`**（29）/ **`tests/test_minitouch_trajectory_executor.py`**
  （15）/ **`tests/test_control_swipe_trajectory.py`**（9）。

### 改动文件（均为纯新增，未改任何既有函数）

- **`module/device/method/minitouch.py`**（此前对 HEAD 零 diff，本轮起 `M`）
  - `import math`。
  - `_ensure_trajectory(trajectory)`：模块级纯校验，**在 `@retry` 之外**调用——点数 `>= 2`、
    每点 `(x, y, dt)`、x/y 有限取整、首点 dt 规整为 0、其余点 dt 取整后 `>= 1`，否则
    `ValueError`（不被重试吞成 `RequestHumanTakeover`）。
  - `swipe_minitouch_trajectory(self, trajectory)`：先 `_ensure_trajectory` 再调内层。
  - `@retry def _swipe_minitouch_trajectory_run(self, points)`：`down(p0).commit()` → send →
    `for (x,y,dt) in points[1:]: move(x,y,pressure).commit().wait(dt)` → send →
    `up().commit()` → send。**不套 `insert_swipe`、不叠加 `random_int(6,15)`、不拼 raw
    command、不改 `Command` / `CommandBuilder` / `minitouch_send` / 握手。** 整个手势用同一个
    `_humanized_pressure()`（照 `_press_and_drag_minitouch`；MuMu 恒 1，仅协议兼容字段）。
- **`module/device/control.py`**（`M`，本轮只加一个方法，`Control.swipe` 等一律未动）
  - `swipe_trajectory(self, trajectory, control_name='SWIPE')`：`handle_control_check` →
    非 minitouch 后端 `raise NotImplementedError`（**不静默退化成端点直线滑动**）→
    `list(trajectory)` 物化（非可迭代 `ValueError`）→ `_invalidate_image_batch_cache` →
    `perf_counter` 计时 → `swipe_minitouch_trajectory` → `logger.info` →
    `get_behavior_trace(...).record('ACTION', action='swipe', target=control_name,
    elapsed_ms=...)`（端点级，**不记每个 MOVE**，延续 D004）。

### 未改 / 未接（范围边界）

`Control.swipe` / `BaseTask.swipe` / `RuleSwipe` / `CommandBuilder` / `Command` /
`minitouch_send` / 握手 / `insert_swipe` / `smooth_path` / D007 的 `np.random` 保留项；
KekkaiUtilize（`perform_swipe_action` 仍 `swipe_adb` 直连、`SWIPE_DISTANCE=416` 不变）/
`SEARCH_MAX_SWIPES` / FrameWait / 结界卡 ROI / config；**没有 `BaseTask.swipe_trajectory`**。

### 验证

- `tests/test_touch_swipe_model.py` `29/29`、`tests/test_minitouch_trajectory_executor.py`
  `15/15`、`tests/test_control_swipe_trajectory.py` `9/9`。
- 相关既有：`test_minitouch_randomization` / `test_swipe_duration_cleanup` /
  `test_rule_swipe_trace_removed` / `test_behavior_trace` / `test_behavior_click_stats`
  合计 `60/60` 不受影响。
- `toolkit/python.exe -m compileall -q module/device/touch_swipe_model.py
  module/device/method/minitouch.py module/device/control.py` OK。
- `toolkit/python.exe -m unittest discover -s tests` → **`836/836 OK`**（783 → 836）。
- `git diff --check`（`control.py` / `minitouch.py`）干净。

### Level C 待验收（未真机，不标 VERIFIED）

新轨迹实际滚动量 / 落点 / 逐段 dt 在设备侧是否被如实执行 / 是否被游戏识别为「滑动」而非
「点击」（minitouch ≥5px）/ 尾段是否自然停止、不误触 click、不产生异常 fling / 与
`insert_swipe` 路径的行为差异。第一步验收环境用**非游戏 Android 可滚动长列表**（系统设置 /
文件管理器 / 浏览器离线长页 / 专用测试 APK），过关后才接阴阳师。`TouchSwipeParams` 默认值
与 `tail_correction` 去留待真机数据校准。逐调用点接入（首选 KekkaiUtilize
`perform_swipe_action` 或 `list_find` 翻页）每个都单独 Level C。

### 文档同步

- AI_CONTEXT.md：已更新（§4.42 新增；§7 测试基线 783 → 836 + 覆盖点；§8.1 minitouch
  轨迹条目改「第一阶段已实现」；§2 加本轮文件说明）。
- DEVELOP_LOG.md：本条。
- ROADMAP.md：已更新（「已完成」新增「TouchSwipeModel 第一阶段实现」行；Level A/B 区对应
  项标完成；「需要真机验证的任务」新增 Level C 验收步骤）。
- ARCHITECTURE.md：已更新（§2 新增 `TouchSwipeModel` 层 + `Control` / `Device Backend`
  条目补 `swipe_trajectory` / `swipe_minitouch_trajectory`；§3 新增「自定义轨迹滑动」调用链；
  §5 扩展点新增一行）。
- DECISIONS.md：已更新（新增 **D018**「模型出数据 / 执行层发命令 / `Control.swipe` 不变 /
  显式 opt-in」，与 D002 / D003 / D004 / D006 / D007 一致、均未推翻）。
- TESTING.md：无需更新（未改测试分级 / 验证流程 / 真机要求 / 长期测试原则；本功能的 Level C
  验收条目按惯例进 ROADMAP）。

### Git

分支 `master`，HEAD 仍 `2cdf3a0571b0449748aabef259da5cbd2378536c`。未 commit / push /
merge / reset / clean / stash，未触碰无关 WIP，未真机。

## 2026-09-04 - TouchSwipeModel MuMu Level C 测试工具

新增一次性 Level C 验收工具，**零生产改动**（`module/` 对上一条记录后的状态无 diff）。
本轮只新增 2 个未跟踪文件：

- **`dev_tools/test_touch_swipe_mumu.py`** —— 在 MuMu 的 Android 设置长列表页面上执行**一条**
  `TouchSwipeModel` 轨迹，并把「本次实际发送的同一条轨迹」存成 PNG + JSON。单次执行后退出、
  不循环、不进游戏、不点条目、不调 OCR / FrameWait / KekkaiUtilize。
  - CLI：`--config`（必填）、`--start X,Y` / `--end X,Y`（默认 `520,560` → `520,300`，
    **仅开发测试坐标**，帮助文本已注明、不进生产配置、不写 `TouchSwipeParams` 默认值）、
    `--output-dir`（默认 `log/touch_swipe_test`）、`--curve left|straight|right`（可选 dev：
    经 `TouchSwipeModel(rng=ForcedCurveRng(...))` 已有的注入点钉住曲率方向，**不改生产代码**；
    需距离 ≥ 10px）、`--verbose`。
  - 流程：`resolve_config_name`（复用 `manual_click_recorder`）→ `Device(config=<name>)`
    （项目标准设备初始化路径，连**已运行**的 MuMu；失败早退不生成文件）→ 校验
    `control_method == 'minitouch'` → `model.generate(start, end)`**只调一次** → `save_json` +
    `draw_trajectory_png`（同一条轨迹）→ 打印预览 + MuMu 操作提示 → `input()` 人工确认
    （Enter 执行 / `q` 退出）→ `device.swipe_trajectory(trajectory,
    control_name='TOUCH_SWIPE_LEVEL_C')` **执行一次** → 回写 `executed=True` → 打印 PNG /
    JSON 路径 → 退出。**不做第二次执行。**
  - 每次运行按 `test_id = YYYYMMDD_HHMMSS` 输出 `touch_swipe_<id>.png` + `.json` 到
    `log/touch_swipe_test/`，不覆盖历史。
  - PNG（cv2，1200×800，项目已装 `cv2 4.10.0` / `Pillow 10.2.0`，**不新增依赖**）：
    A. XY 轨迹主图（DOWN 绿 / UP 红 / MOVE 点 / 连线 / 基准虚线 / 主方向箭头 / 部分序号 /
    左右偏移数值 / 「屏幕 Y 向下为正」注释，x 轴独立缩放并标注）；B. 每段 dt；
    C. 每段速度（px/ms，起步慢→中段快→收尾慢）；D. 文本统计（test_id / start / end /
    point_count / total_dt_ms / straight_distance / actual_path_length / max_lateral /
    max_dx / min·max dt / avg·max speed / tail_correction_enable）。所有 PNG 文字用 ASCII。
  - JSON：`test_id` / `config` / `control_name` / `curve_mode` / `start` / `end` /
    `generated_at` / `executed` / `point_count` / `total_dt_ms` / `straight_distance_px` /
    `actual_path_length_px` / `max_dx_px` / `max_lateral_offset_px` / `min_x` / `max_x` /
    `min_y` / `max_y` / `min_dt_ms` / `max_dt_ms` / `avg_speed_px_per_ms` /
    `max_speed_px_per_ms` / `params`（`dataclasses.asdict(model.params)` —— 从真实对象读，
    13 个字段）/ `trajectory`（`[{index,x,y,dt_ms}]`，与 PNG / 实际发送逐点一致）。
  - **纯逻辑函数**（可单测、不碰设备）：`parse_point` / `make_test_id` / `trajectory_stats` /
    `build_record` / `save_json` / `draw_trajectory_png` / `ForcedCurveRng`；`Device` 只在
    `init_device()` 内惰性 import。
- **`tests/test_touch_swipe_mumu_tool.py`**（20 用例）：坐标解析正反例、test_id 格式、
  `trajectory_stats`（已知小轨迹精确值 + 真模型轨迹的 minimum-jerk 中段更快 + 曲率幅度）、
  `build_record`（必备键 / trajectory 逐点带 index / params 来自真实 `TouchSwipeParams` 13 字段）、
  `save_json` 往返、`draw_trajectory_png` 生成可被 cv2 读回的 `(800,1200,3)` PNG、
  PNG 与 JSON 同一条轨迹、`ForcedCurveRng`（left→lo / right→hi / straight→0 / 其余委托 /
  非法 mode / 接进模型后向左·向右鼓出且精确到终点）、模块导入不构造 `Device`。**不连 MuMu。**

### 验证

- `tests/test_touch_swipe_mumu_tool.py` `20/20`；连同 `test_touch_swipe_model` /
  `test_minitouch_trajectory_executor` / `test_control_swipe_trajectory` 合计 `73/73`。
- `toolkit/python.exe -m compileall -q dev_tools/test_touch_swipe_mumu.py
  tests/test_touch_swipe_mumu_tool.py` OK。
- `toolkit/python.exe -m unittest discover -s tests` → **`856/856 OK`**（836 → 856，+20）。
- `git diff --check`（`dev_tools/` / `tests/` / `module/`）干净。
- 未跑真机（无用户授权、不启动 MuMu）。

### Level C 人工执行（待用户在真机窗口做）

1. 启动 MuMu（对应 config 实例）；2. 打开 Android 设置；3. 进入应用管理等可上下滚动的长列表；
4. 把列表停在中间、页面停稳；5. 回终端跑
`toolkit\python.exe dev_tools\test_touch_swipe_mumu.py --config oas1`；
6. 查看生成的 `log/touch_swipe_test/touch_swipe_<id>.png` 确认轨迹形状；7. 按 Enter；
8. 观察 MuMu 里一次 swipe；9. 查看 PNG / JSON；10. **第一轮不要进入阴阳师**。
多跑几次或加 `--curve left|straight|right` 覆盖左弯 / 近直线 / 右弯；短/中/长距离建议
`--start 520,520 --end 520,400`（~120px）、默认（~260px）、`--start 520,620 --end 520,180`（~440px）。
真机结论出来后，`TouchSwipeParams` 默认值与 `tail_correction` 去留**另开任务**调整，本工具不自动改参。

### 文档同步

- AI_CONTEXT.md：已更新（§4.42「Level C 待验收」补一句「测试工具已就绪
  `dev_tools/test_touch_swipe_mumu.py`」；§7 基线 836 → 856 + 覆盖点）。
- DEVELOP_LOG.md：本条。
- ROADMAP.md：已更新（「需要真机验证」的 TouchSwipeModel Level C 条目注明「测试工具已就绪，
  真机待执行」+ 具体命令）。
- ARCHITECTURE.md：无需更新（未新增公共层 / 未改调用链 / 未改架构级契约；dev_tools Level C
  harness 不是架构）。
- DECISIONS.md：无需更新（未形成新长期决策、未推翻 D018；工具只是执行 D018 已定的验收路径）。
- TESTING.md：无需更新（§3「不执行 dev_tools/ 下需要设备的脚本」已通用覆盖本工具；未改测试
  分级 / 默认验证流程 / 真机要求。「轨迹类输入层先在非游戏可滚动页面验证」目前仍是
  TouchSwipeModel 专项（D018 + ROADMAP 已记），样本只有一个，不提前上升为 TESTING 通用规则）。

### Git

分支 `master`，HEAD 仍 `2cdf3a0571b0449748aabef259da5cbd2378536c`。未 commit / push / merge /
reset / clean / stash，未触碰无关 WIP，未真机。本轮新增：`dev_tools/test_touch_swipe_mumu.py`、
`tests/test_touch_swipe_mumu_tool.py`。

## 2026-09-04 - TouchSwipe Level C 轨迹图比例修正（PNG 可视化）

**只改 `dev_tools/test_touch_swipe_mumu.py` 的绘图 + 对应测试**，零生产改动、未改
`TouchSwipeModel` / minitouch executor / `Control.swipe_trajectory` / CLI / JSON schema /
`Device` 初始化 / `input` 确认 / `ForcedCurveRng` / 实际发送轨迹。

### 问题

旧 Panel A 对 X、Y 各自按本次轨迹 `x_span` / `y_span` 独立自适应缩放。260px 纵向位移
配 16px 横向偏移会被画成「巨大半圆」，与用户在 1280×720 MuMu 屏幕里实际看到的比例严重不符
（16px 在真实屏幕上只是一点点弯）。

### 改动

- **PNG 尺寸 1200×800 → 1400×900**（可读性优先，见 spec §6）。
- **A1. Screen View 1280×720（新）**：固定用 `[0, SCREEN_WIDTH=1280] × [0, SCREEN_HEIGHT=720]`
  作定义域，**不再按轨迹跨度独立缩放**。绘图区经 `fit_screen_rect(panel_rect)` 取一块**保持
  1280:720 (16:9) 比例、居中留白**的子矩形 → `screen_to_panel(x, y, fit)` 里 X、Y 像素比例
  天然相等（1:1 视觉）。含：屏幕边框、淡灰网格 + 刻度（x=0/320/640/960/1280、
  y=0/180/360/540/720）、轨迹 bounding box 参考矩形（**不据此缩放**）、基准 start→end 虚线、
  实际轨迹曲线、MOVE 点、DOWN（绿）/ UP（红）真实位置、主方向箭头。Y 向下为正。
- **A2. ZOOMED VIEW（新）**：`zoom_transform(traj, panel_rect)` 按轨迹 bbox **自适应**
  （X / Y 各自缩放，margin 16%）放大，标题明确 `-- NOT screen scale`，用于看 ±X 小偏移 /
  MOVE 细节；显示 `x span` / `y span` / `max lateral offset` / `max |dx|` / MOVE 序号 /
  DOWN / UP / 基准直线 / 曲线。
- **B / C / D 面板内容不变**，只按新布局重新定位（B/C dt·速度图、D 文本统计逐字不变）。
- 移除旧文案 `x scale independent`。
- 新增纯函数（便于单测坐标变换，spec §9）：`trajectory_bbox` / `fit_screen_rect` /
  `screen_to_panel` / `zoom_transform`；模块常量 `SCREEN_WIDTH = 1280` / `SCREEN_HEIGHT = 720`
  （**仅 dev tool 展示参数，不进 `TouchSwipeParams` / 生产**）。

### 数据一致性

`model.generate` 仍只调一次；`record["trajectory"]` 同一份喂给 A1 / A2 / B / C / D / JSON /
`device.swipe_trajectory`。测试 `test_png_from_same_trajectory_as_json` 锁 JSON 逐点 == 原始
tuple 列表。绘图不重新生成轨迹 / 不重采样 dt / 不改点坐标。

### 验证

- `tests/test_touch_swipe_mumu_tool.py` `20 → 31`（新增 `ScreenViewGeometryTest` 8 用例：
  `fit_screen_rect` 恒 16:9 且居中留白、`screen_to_panel` 用固定 `[0,1280]×[0,720]` 定义域
  且不随轨迹跨度变、X/Y 像素比例相等（1:1）、Y 向下、`trajectory_bbox` 支持 dict / tuple、
  `zoom_transform` 用 bbox 且四角落 panel 内、zoom 是 bbox 自适应而非屏幕比例；+ PNG 新尺寸
  `(900,1400,3)`、`draw_trajectory_png` 默认 `size=(1400,900)`、left/straight/right 三模式
  均出图、stats 键不变）。
- `toolkit\python.exe -m unittest tests.test_touch_swipe_mumu_tool` → `31/31 OK`。
- `toolkit\python.exe -m compileall -q dev_tools\test_touch_swipe_mumu.py
  tests\test_touch_swipe_mumu_tool.py` → OK。
- `toolkit\python.exe -m unittest discover -s tests` → **`867/867 OK`**（856 → 867，+11）。
- `git diff --check`（我的 2 个文件）干净。
- 本地渲染 straight / left / right / short_auto(120px) / long_auto(440px) 五样本核对：
  A1 里 16px 横向偏移只是轻微弯、6px 更轻、2/4px 近直线，纵向位移按 720px 屏高真实显示；
  A2 里 left / right / straight 差异仍明显。未跑真机。

### 文档同步

- AI_CONTEXT.md：已更新（§4.42「Level C 待验收」的 PNG 描述改为「A1 1280×720 实屏比例 1:1
  + A2 zoom 细节」；§7 基线 856 → 867 + 覆盖点补充）。
- DEVELOP_LOG.md：本条。
- ROADMAP.md：已更新（TouchSwipeModel Level C 条目的 PNG 描述同步为 A1 实屏 + A2 zoom）。
- ARCHITECTURE.md：无需更新（dev_tools 可视化调整，未改公共层 / 调用链 / 架构契约）。
- DECISIONS.md：无需更新（未形成 / 推翻长期决策；D018 不涉及可视化）。
- TESTING.md：无需更新（未改测试分级 / 默认验证流程 / 真机要求）。

### Git

分支 `master`，HEAD 仍 `2cdf3a0571b0449748aabef259da5cbd2378536c`。未 commit / push / merge /
reset / clean / stash，未触碰无关 WIP，未真机。本轮仅改 2 个（已存在的未跟踪）文件：
`dev_tools/test_touch_swipe_mumu.py`、`tests/test_touch_swipe_mumu_tool.py`。

## 2026-09-04 - TouchSwipeModel 第二阶段：平滑时间扰动 + 尾段慢拖

正式生产模型优化。**只改 `module/device/touch_swipe_model.py` + `tests/test_touch_swipe_model.py`**。
未接生产消费者、未启动 MuMu、未真机。长期契约见 `docs/DECISIONS.md` **D018 第二阶段追加**。

### 第一阶段暴露的问题（Level C 图形 / MuMu 设置页已确认空间结构正确）

- 时间维度：每个 MOVE 的 `dt` 独立叠加 `random_int(-3, +3)` → speed 曲线在平滑大趋势上出现
  局部尖峰 / 锯齿（实测 260px：`dt=[16,16,13,14,12,13,12,7,9,12,10,11,9,15,14,13]`，
  相邻 `12→7→9→12`，speed `2.33→4.29→3.33`）。
- 尾段：minimum-jerk 已让尾部空间步长较小，但尾段 MOVE 点数偏少、`dt` 抬升太温和
  （13→15），收尾「拖感」不足。

### 改动 1：`base_dt(s) + smooth_noise` 时间模型

- `base_dt(s)`（趋势，不变的「前慢中快后慢」）：
  `base_dt_ms * (1 + end_slow_ratio*(1 - sin(pi*t)) + tail_slow_gain*smoothstep(k))`。
- `smooth_noise`（小幅自然变化）：一阶低通 / EMA ——
  `raw_i = rng.randint(-dt_jitter_ms, +dt_jitter_ms)`；
  `noise_i = dt_smooth_alpha*noise_{i-1} + (1-dt_smooth_alpha)*raw_i`，`noise_0 = 0`。
  是 `[-jitter, +jitter]` 内取值的**凸组合** → 恒有界（`|noise_i| <= jitter`）、零均值、
  **不长期漂移**；`|noise_i - noise_{i-1}| <= (1-alpha)*2*jitter` → 无无界跳变。
  取代第一阶段的独立 jitter。**趋势跨度 ~[10,25]ms ≫ 噪声 ≤3ms。**
- 不引入 scipy / numpy / 控制理论依赖；纯 `math`。

### 改动 2：尾段慢拖（按「已走距离占比 s」度量，约最后 15% 距离）

- **更密的 MOVE 点**：参数 `t` 网格 = 主段 `[0, t_tail]` 等距 + 尾段 `[t_tail, 1]` 按
  `tail_density_gain` 倍加密（`t_tail = _t_for_s(tail_start_ratio)`，二分求解）。总点数
  `max_points` 封顶，超出等比缩减。minimum-jerk 本身已让尾部空间密，这里只是「相对主运动
  更细」，不翻倍堆点。
- **`dt` 平滑增大**：尾段（`s >= tail_start_ratio`）在 `slow` 因子上叠加
  `tail_slow_gain * smoothstep(k)`，`smoothstep` 在 `k=0` 处一阶导为 0 → **平滑接续**，
  不会 8ms 突跳到 25ms。
- **speed 平滑下降**：尾部空间步长小 + `dt` 渐增 → 自然平滑降速。
- **终点仍精确到原 `end`**（取整后），不额外滑一段、**不做固定 pre-UP 停顿**（不复制
  `drag` 的 `wait(140)×2`）、**不做过冲后回拉**（`tail_correction` 仍默认关，本轮不动）。

### 改动 3：`TouchSwipeParams`（frozen dataclass）

**新增 4 个字段**（均有范围校验 + 中文注释 + 无意义组合抛 `ValueError`）：

| 字段 | 默认 | 范围 | 用途 |
|---|---|---|---|
| `dt_smooth_alpha` | `0.72` | `[0, 1)` | dt 扰动一阶低通系数（0=每段独立） |
| `tail_start_ratio` | `0.85` | `[0.5, 1.0)` | 尾段慢拖起点（按已走距离占比） |
| `tail_density_gain` | `1.55` | `[1.0, 4.0]` | 尾段 MOVE 点密度相对主段倍数 |
| `tail_slow_gain` | `0.55` | `[0.0, 3.0]` | 尾段额外时间放慢（叠加在 `end_slow_ratio` 上） |

**修改默认值**：`max_dt_ms 28 → 34`（尾段慢拖需要更高上限）、`max_points 64 → 80`
（尾段加密留余量）。

**保持不动**：`avg_step_px` / `min_points` / `base_dt_ms`（=10）/ `end_slow_ratio`（=0.5）/
`dt_jitter_ms`（=3）/ `min_dt_ms` / **`max_curve_px`（=16）/ `curve_px_ratio`（=0.12）——
空间曲率参数本轮明令不动，避免和时间模型同时改无法归因** / `tail_correction_*`。

**新增模块级纯函数**（可单测）：`_minimum_jerk_s(t)` / `_t_for_s(target_s)`（二分）/
`_smoothstep(k)`。

### 静态生成数据（`CurveRng`：曲率固定 + dt 噪声=0 的纯趋势；**非真机**）

对比 phase-1（`FakeRng(0)`）：120→93ms、260→188ms、440→333ms。

| dist/mode | n | total_ms | mid_dt | tail_dt | mid_spd | tail_spd | max_lat |
|---|---|---|---|---|---|---|---|
| 120/straight | 10 | 119 | 10.0 | 15.8 | 2.50 | 0.63 | 0 |
| 120/left · right | 11 | 139 | 10.0 | 18.0 | 2.50 | 0.32 | 14 |
| 260/straight | 18 | 225 | 10.0 | 16.1 | 3.07 | 0.56 | 0 |
| 260/left · right | 19 | 245 | 10.0 | 17.4 | 3.07 | 0.36 | 16 |
| 440/straight | 31 | 395 | 10.0 | 16.3 | 2.84 | 0.44 | 0 |
| 440/left · right | 34 | 449 | 10.0 | 17.3 | 2.84 | 0.31 | 16 |

总时长增幅 ~20~50%（尾段结构，非 `base_dt` 整体放慢），`120 < 260 < 440` 每种曲率都严格
成立；`mid_dt` 仍 ≈10ms（中段没被放慢）；`tail_dt` ≈16~18ms、`tail_spd` ≈0.3~0.6 px/ms
（中段 ~2.8~3.1）→ 尾段明显更慢且平滑下降。实际生产走真实 `SystemRandom`，平滑噪声再让
每次总时长 ±10~15ms、逐段 dt ±1~2ms。

### 验证

- `tests/test_touch_swipe_model.py` `29 → 50`：新增 `SmoothDtNoiseTest`（8）——低通后相邻
  dt 无无界跳变、扰动不漂移、`SeqRng` 可复现 / 不同序列有变化、慢→快→慢趋势仍成立、
  噪声不盖过趋势、`_t_for_s` / `_minimum_jerk_s` 互逆；`TailDragSpaceTest`（6）——尾段
  MOVE 点 ≥3、空间步长比中段小、无连续重复坐标、终点精确不过冲不反向（纵向上 / 下）、
  源码无 `140` / 无 `pre_up`；`TailDragTimeTest`（4）——尾段 `avg_dt` > 中段、尾段
  `avg_speed` < 中段、进入尾段无 dt 突跳、末段属慢区；`TotalDurationTest`（3）——
  `120<260<440` 且各有宽松上限（200 / 360 / 600ms，非真机数据）；`invalid_params` 扩展
  8 个新非法组合 + 新默认值断言。
- 既有 `test_minimum_jerk_speed_structure` / `±曲率` / `curve cap` / `correction` /
  deterministic RNG / invalid input / executor / Control / Level C tool 全部继续通过
  （`test_correction_forced_changes_only_tail_not_endpoint` 的 `head_len` 0.8 硬前缀比较
  改为「公共前缀首个差异点在 60% 之后」，更稳健）。
- `toolkit/python.exe -m compileall -q module/device/touch_swipe_model.py
  tests/test_touch_swipe_model.py` OK。
- 目标组（`test_touch_swipe_model` + `test_minitouch_trajectory_executor` +
  `test_control_swipe_trajectory` + `test_touch_swipe_mumu_tool`）`105/105`。
- `toolkit/python.exe -m unittest discover -s tests` → **`888/888 OK`**（867 → 888，+21）。
- Level C 工具（`dev_tools/test_touch_swipe_mumu.py`）**未改**：JSON 的
  `dataclasses.asdict(model.params)` 自动带上 4 个新字段；PNG 的 B（dt）/ C（speed）
  面板已能看到平滑趋势（无中段尖峰、尾部平滑下降）。
- `git diff --check`（`touch_swipe_model.py` / `test_touch_swipe_model.py`）干净。

### 回归边界（本轮未改）

- `Minitouch.swipe_minitouch_trajectory` / `_ensure_trajectory` /
  `_swipe_minitouch_trajectory_run` / `CommandBuilder` / `minitouch_send` / 握手 —— 协议 /
  executor 契约不变（trajectory 仍是 `[(x, y, dt_ms)]`、`dt` 语义不变、首点 dt=0）。
- `Control.swipe_trajectory` / `Control.swipe` / `BaseTask` / `RuleSwipe` —— 不变。
- `dev_tools/test_touch_swipe_mumu.py` —— 未改架构（§24）。
- KekkaiUtilize / FrameWait / phase correlation / 新旧区域过滤 / `SEARCH_MAX_SWIPES` /
  `I_U_EMPTY_CARD` / GeneralBattle / RealmRaid —— 未碰。
- 未新增 Fitts Law / Hick Law / fatigue / reaction delay / 点击 delay。
- `insert_swipe` 的 `np.random`（D007）—— 未动。

### 下一轮 MuMu Level C（人工，本轮不启动 MuMu）

MuMu → Android 设置 → 应用管理长列表，跑：

```
toolkit\python.exe dev_tools\test_touch_swipe_mumu.py --config oas1
toolkit\python.exe dev_tools\test_touch_swipe_mumu.py --config oas1 --curve left
toolkit\python.exe dev_tools\test_touch_swipe_mumu.py --config oas1 --curve right
toolkit\python.exe dev_tools\test_touch_swipe_mumu.py --config oas1 --curve straight
toolkit\python.exe dev_tools\test_touch_swipe_mumu.py --config oas1 --start 520,520 --end 520,400
toolkit\python.exe dev_tools\test_touch_swipe_mumu.py --config oas1 --start 520,620 --end 520,180
```

看 PNG：A1 实际屏幕路径；B `dt` 是否比第一阶段平滑；C 速度是否中段无尖峰、尾部平滑下降。
人工观察：有没有 fling；尾部是否更平稳；页面是否突然停顿；swipe 是否仍能正常识别；实际
滚动距离有没有明显改变。据结果再决定是否调 `tail_slow_gain` / `tail_density_gain` /
`dt_smooth_alpha` 或整体放慢（**另开任务**）。

### 文档同步

- AI_CONTEXT.md：已更新（§4.42 加第二阶段说明；§7 基线 867 → 888 + 覆盖点）。
- DEVELOP_LOG.md：本条。
- ROADMAP.md：已更新（TouchSwipeModel Level C 条目：第二阶段时间 / 尾段优化已实现，
  phase-2 Level C 待人工执行）。
- ARCHITECTURE.md：已更新（§2 `TouchSwipeModel` 条目补「第二阶段：dt 一阶低通平滑 +
  尾段慢拖」一句，分层不变）。
- DECISIONS.md：已更新（**D018 第二阶段追加**：时间随机用连续有界低通扰动而非逐 MOVE
  独立 jitter；尾段慢拖不改 `end` / 不做固定 pre-UP pause / 不过冲回拉；具体参数值仍
  Level C 可调、不入 ADR）。
- TESTING.md：无需更新（未改测试分级 / 默认验证流程 / 真机要求）。

### Git

分支 `master`，HEAD 仍 `2cdf3a0571b0449748aabef259da5cbd2378536c`。未 commit / push / merge /
reset / clean / stash，未触碰无关 WIP（`assets.py` whitespace warning 未动）。本轮改
2 个（已存在的未跟踪）文件：`module/device/touch_swipe_model.py`、
`tests/test_touch_swipe_model.py`。

## 2026-09-04 - TouchSwipe Level C 工具：segment speed 与 dt 对齐修正（FIXED，统计一位偏移）

**只改 3 个 dev / 测试文件**：`dev_tools/test_touch_swipe_mumu.py` +
`tests/test_touch_swipe_mumu_tool.py` + `tests/test_touch_swipe_model.py`（后者仅统计辅助
helper）。**生产模型 / executor / 协议 / `Control` 一律未改**（mtime 确认）。未启动 MuMu。

### 发现：存在一位偏移（前一轮报告「无偏移」的结论是错的）

从源码核实 executor（`Minitouch._swipe_minitouch_trajectory_run`）真实命令流：

```
DOWN(p0) COMMIT | SEND
MOVE(p1) COMMIT WAIT(dt1)  MOVE(p2) COMMIT WAIT(dt2) ...  MOVE(p_{n-1}) COMMIT WAIT(dt_{n-1}) | SEND
UP COMMIT | SEND
```

`x0, y0, _ = points[0]` —— **p0 的 dt0 被丢弃**；`for x, y, dt in points[1:]:
builder.move(x, y).commit().wait(dt)` —— `WAIT(dt_i)` 夹在「MOVE 到 p_i」与「MOVE 到
p_{i+1}」之间。**即 `dt_i` 是「到达 p_i 之后、移动到 p_{i+1} 之前的停留」**（与 D018 一致，
D018 dt 契约**正确、不改**）。因此段 `p_i → p_{i+1}` 的时间是 **`dt_i`**。

原 `trajectory_stats()` / `_segment_speeds()` / `_split_mid_tail()` 却把段
`p_{i-1} → p_i`（距离）配给 **`dt_i`**（应为 `dt_{i-1}`）—— **相邻错位一格**。

手算样本 `[(0,0,0),(20,0,5),(25,0,20),(35,0,10)]`（executor：`MOVE p1 WAIT5 MOVE p2 WAIT20
MOVE p3 WAIT10 UP`）：

| 段 | 距离 | 正确 dt | 正确 speed | 原工具（错） |
|---|---|---|---|---|
| p1→p2 | 5px | dt1 = 5ms | **1.0 px/ms** | 5 / dt2(20) = 0.25 |
| p2→p3 | 10px | dt2 = 20ms | **0.5 px/ms** | 10 / dt3(10) = 1.0 |
| p0→p1 | 20px | —（无显式 dt） | **排除** | 20 / dt1(5) = 4.0（伪造） |

### 边界处理（§14 / §15）

- **`p0 → p1`（DOWN → 第一次 MOVE）**：`p0.dt = 0` 被执行层忽略；两 batch 之间只有
  `minitouch_send` 的协议等待 `DEFAULT_DELAY = 0.05`（**不属于 trajectory dt 契约**，不并入
  统计）。没有 trajectory 显式 dt 描述这个 interval → **不给它伪造 segment speed**。
- **`dt_{n-1}`（最后一个 dt）**：是「最后一次 MOVE → UP 前的停留」，没有「下一个 MOVE」→
  **不构成 MOVE→MOVE 段、不拿来算前一段速度**。
- 结论：有确定 executor 时间的 MOVE→MOVE 段共 **`n-2` 段**（`p_i → p_{i+1}`，`i = 1..n-2`），
  段时间 = `dt_i`。`B panel`（每点 WAIT）仍展示全部 `dt_1..dt_{n-1}`（含 pre-UP dwell）。

### 修复内容（只在 dev tool + 测试）

- **`dev_tools/test_touch_swipe_mumu.py`**：
  - 新增 `trajectory_segments(trajectory)` —— 一次性对齐 `from_index` / `to_index` /
    `distance_px` / `dt_ms`（= `dt_i`）/ `speed_px_per_ms`，`i = 1..n-2`；带完整 docstring
    说明 executor 命令流与排除规则。
  - `trajectory_stats()`：`segment_speeds_px_per_ms` / `avg_speed_px_per_ms`（= Σseg_dist /
    Σseg_dt，只统计有效段）/ `max_speed_px_per_ms` 全部改走 `trajectory_segments`；新增
    `segment_count`。**未动** `total_dt_ms`（所有显式 WAIT 之和）/ `actual_path_length_px`
    （全路径）/ `min_dt_ms` / `max_dt_ms`（= min/max(dt_1..dt_{n-1})）/ `straight_distance_px`
    / `max_lateral_offset_px` / `min·max x/y` / `max_dx_px`。
  - PNG：C 面板改用 `trajectory_segments` 的段速度，标题 `C. speed per SEGMENT
    (p_i->p_i+1 = dist / dt_i, px/ms)`、横轴 `segment index (i = from-point)`；B 面板标题
    改精确为 `B. WAIT after MOVE (trajectory dt_ms, point i>=1)`、横轴 `point index (i>=1)`。
    `_plot_series` 加 `x_label` 形参。**A1 / A2 Screen View / Zoomed View 完全未动。**
  - JSON schema 字段名不变（`avg_speed_px_per_ms` / `max_speed_px_per_ms` 仍在，只是取值
    校正；`segment_count` 是 stats dict 内部字段，不进 `build_record`）。
- **`tests/test_touch_swipe_mumu_tool.py`**：新增 `TrajectorySegmentsTest`（5，手算样本精确
  断言 / p0→p1 排除 / dt_last 不错配 / 2·3 点边界 / 段数 = n-2 且无缝覆盖）；`TrajectoryStatsTest`
  按新语义重写（4 点 → 2 段、`avg = Σdist/Σdt`、`segment_count`）+ 新增 `test_unrelated_stats_unchanged`。31 → 37。
- **`tests/test_touch_swipe_model.py`**（§8 允许：仅统计 helper）：`_segment_speeds` /
  `_split_mid_tail` 改用新 `_move_segments`（段 `p_i→p_{i+1}` 用 `dt_i`，排除 p0→p1 与
  dt_last；已走距离占比从 p0 起算含前导段）；新增 `MoveSegmentAlignmentTest`（3，手算样本
  锁 helper 语义）。50 → 56。既有第二阶段方向性断言（`tail_avg_dt > mid_avg_dt` /
  `tail_avg_speed < mid_avg_speed` / minimum-jerk 慢快慢）**校正后仍全部成立**。

### 修正后的第二阶段静态数据（executor 时间对齐；CurveRng 曲率固定 + dt 噪声=0；**非真机**）

| dist/mode | n | total_ms | mid_dt | tail_dt | mid_spd | tail_spd |
|---|---|---|---|---|---|---|
| 120/straight | 10 | 119 | 11.0 | 13.5 | 2.27 | 0.74 |
| 120/left · right | 11 | 139 | 11.0 | 15.8 | 2.27 | 0.37 |
| 260/straight | 18 | 225 | 10.0 | 14.9 | 3.07 | 0.61 |
| 260/left · right | 19 | 245 | 10.2 | 16.1 | 2.88 | 0.39 |
| 440/straight | 31 | 395 | 10.2 | 15.6 | 2.75 | 0.47 |
| 440/left · right | 34 | 449 | 10.2 | 16.6 | 2.75 | 0.32 |

对比上一轮（**错位对齐**）：如 260/straight 曾记 `tail_dt=16.1 tail_spd=0.56`，校正后
`tail_dt=14.9 tail_spd=0.61`（错位把段距离配给下一点 dt，尾段 dt 递增使旧值略偏高）。
差异 ~5~10%，属一位偏移的预期量级。**`total_dt_ms` / `n` / 点坐标未变**（模型未改）。
**§16 核心结论仍成立**：每个 case `tail_avg_speed < mid_avg_speed` 且 `tail_avg_dt >
mid_avg_dt`。**未为保持旧数字调任何生产参数**（`dt_smooth_alpha` / `tail_*` /
`max_dt_ms` / `max_points` / minimum-jerk / EMA / curve 全部原样，§17 / §18）。

### 验证

- `tests/test_touch_swipe_mumu_tool.py` `31 → 37`、`tests/test_touch_swipe_model.py` `50 → 56`、
  `tests/test_minitouch_trajectory_executor.py` `15/15`、`tests/test_control_swipe_trajectory.py`
  `9/9`（目标组 `114/114`）。
- `toolkit\python.exe -m compileall -q dev_tools\test_touch_swipe_mumu.py
  tests\test_touch_swipe_mumu_tool.py tests\test_touch_swipe_model.py` OK。
- `toolkit\python.exe -m unittest discover -s tests` → **`897/897 OK`**（888 → 897，+9）。
- `git diff --check`（本轮 3 文件）干净。
- 本地渲染 PNG：B（含 pre-UP dwell 的完整 dt 曲线）/ C（17 段、单峰、尾部平滑下降）标签已更新。

### 结论

**FIXED**（统计一位偏移）。D018 的 dt 契约本身**正确**（`dt_i` = 到达 p_i 后、下次 MOVE
前的停留）—— **未重定义**；只补一句澄清「分析工具里段 `p_i→p_{i+1}` 的时间取 `dt_i`」。
executor / 协议 / 生产模型 **NO CHANGE**。

### 下一轮 MuMu Level C（人工，本轮不启动 MuMu）

MuMu → Android 设置 → 应用管理长列表：

```
toolkit\python.exe dev_tools\test_touch_swipe_mumu.py --config oas1
toolkit\python.exe dev_tools\test_touch_swipe_mumu.py --config oas1 --curve left
toolkit\python.exe dev_tools\test_touch_swipe_mumu.py --config oas1 --curve right
toolkit\python.exe dev_tools\test_touch_swipe_mumu.py --config oas1 --curve straight
toolkit\python.exe dev_tools\test_touch_swipe_mumu.py --config oas1 --start 520,520 --end 520,400
toolkit\python.exe dev_tools\test_touch_swipe_mumu.py --config oas1 --start 520,620 --end 520,180
```

看 PNG：A1 实际屏幕曲率；A2 放大轨迹；B dt / WAIT 趋势；**C 现在是 executor 时间对齐后的
segment speed**（中段 spike 是否确实减少、tail speed 是否平滑下降、tail avg 是否低于
middle、末尾是否有异常停顿 / fling）。

### 文档同步

- AI_CONTEXT.md：已更新（§4.42「第二阶段」静态数据表校正为 executor 对齐值 + 一句「segment
  speed 语义已校正」；§7 基线 888 → 897 + 覆盖点补 `trajectory_segments`）。
- DEVELOP_LOG.md：本条。
- ROADMAP.md：已更新（TouchSwipeModel Level C 条目注明「speed 统计语义已按 executor 校正」）。
- DECISIONS.md：已更新（D018 第二阶段追加补一句澄清：分析工具里段 `p_i→p_{i+1}` 的时间取
  `dt_i`；dt 契约本身未改）。
- ARCHITECTURE.md：无需更新（分层 / 调用链 / 契约不变；dev 工具统计口径不是架构事实）。
- TESTING.md：无需更新（未改测试分级 / 验证流程 / 真机要求）。

### Git

分支 `master`，HEAD 仍 `2cdf3a0571b0449748aabef259da5cbd2378536c`。未 commit / push / merge /
reset / clean / stash，未触碰无关 WIP（`assets.py` whitespace warning 未动）。本轮改
3 个（已存在的未跟踪）文件：`dev_tools/test_touch_swipe_mumu.py` /
`tests/test_touch_swipe_mumu_tool.py` / `tests/test_touch_swipe_model.py`。

## 2026-09-04 - TouchSwipeModel 第二阶段尾段慢拖「收一档」（仅两个默认参数）

**只改 `module/device/touch_swipe_model.py` 的两个 `TouchSwipeParams` 默认值**，模型结构、
算法、其它参数全部不动。未加 / 未删测试（897/897 不变），未启动 MuMu。

### 改动

| 参数 | 旧 | 新 |
|---|---|---|
| `tail_density_gain` | `1.55` | **`1.35`** |
| `tail_slow_gain` | `0.55` | **`0.35`** |

保持不动：`tail_start_ratio=0.85` / `dt_smooth_alpha=0.72` / `base_dt_ms=10` /
`end_slow_ratio=0.5` / `max_curve_px=16` / `curve_px_ratio=0.12` /
`tail_correction_enable=False` / `max_dt_ms=34` / `max_points=80` / minimum-jerk / EMA /
dt jitter 算法 / 曲率算法 / executor / `Control.swipe_trajectory` / Level C speed/dt 对齐。

### 为什么是 1.35 / 0.35

第二阶段 Level C 已确认 dt EMA 平滑、speed 单峰、曲率、minimum-jerk 均正常，但尾部
slowdown 偏强 —— minimum-jerk 自带减速 + `tail_density_gain=1.55`（尾段点更密）+
`tail_slow_gain=0.55`（尾段额外放慢）三层叠加，末段速度压到接近 0（如 260/left 末 3 段
`[0.20, 0.118, 0.10]` px/ms，440/left `[0.074, 0.05, 0.05]`），有「黏住终点」感。

本轮把「尾部力度」收一档：`tail_slow_gain` 0.55→0.35（尾段 dt 抬升斜率更温和）、
`tail_density_gain` 1.55→1.35（尾段加密幅度更小）。minimum-jerk 的自带减速仍在，尾拖
「明显但不过度」。**不动 `tail_start_ratio`** —— 尾段起点不变，只调力度。

### 静态前后对比（`CurveRng`：曲率固定 + dt 噪声=0；**静态生成，非真机**）

| dist/mode | 项 | BEFORE (1.55/0.55) | AFTER (1.35/0.35) |
|---|---|---|---|
| 120/straight | n / total_dt / mid_dt / tail_dt / mid_spd / tail_spd | 10 / 119 / 11.0 / 13.5 / 2.27 / 0.74 | 10 / 117 / 11.0 / 13.2 / 2.27 / 0.75 |
| 120/left·right | 同上 | 11 / 139 / 11.0 / 15.8 / 2.27 / 0.37 | 10 / 117 / 11.0 / 14.3 / 2.27 / 0.53 |
| 260/straight | 同上 | 18 / 225 / 10.0 / 14.9 / 3.07 / 0.61 | 17 / 202 / 10.0 / 13.8 / 3.07 / 0.76 |
| 260/left·right | 同上 | 19 / 245 / 10.2 / 16.1 / 2.88 / 0.39 | 18 / 220 / 10.2 / 15.0 / 2.88 / 0.48 |
| 440/straight | 同上 | 31 / 395 / 10.2 / 15.6 / 2.75 / 0.47 | 30 / 366 / 10.2 / 14.5 / 2.75 / 0.54 |
| 440/left·right | 同上 | 34 / 449 / 10.2 / 16.6 / 2.75 / 0.32 | 32 / 398 / 10.2 / 15.2 / 2.75 / 0.42 |

末 3 段段速度（尾端）：260/left `[0.20, 0.118, 0.10]` → **`[0.28, 0.212, 0.111]`**；
440/left `[0.074, 0.05, 0.05]` → **`[0.083, 0.124, 0.056]`** —— 仍慢（minimum-jerk 自带
减速），但不再贴 0。总时长小幅下降（尾段结构更轻）、点数 -1~2，`120 < 260 < 440` 仍严格
成立。

### 验证（8 项重点确认，全 9 种 dist/mode 组合逐一）

1. `tail_avg_dt > mid_avg_dt` —— 全 True
2. `tail_avg_speed < mid_avg_speed` —— 全 True（mid ~2.3~3.1，tail ~0.42~0.76）
3. 尾段 speed 连续下降（尾段后半均值 < 前半均值）—— 全 True
4. 不过冲 / 不反向（y 单调、`min(y) >= end_y`）—— 全 True
5. `end` 精确不变、`start` 精确 —— 全 True
6. 总时长 `120(117) < 260(202) < 440(366)` —— True
7. ±X / curve 测试不受影响 —— `test_supports_negative/positive_lateral_curvature` /
   `test_lateral_offset_within_configured_cap` / `test_no_sawtooth_lateral_single_hump` 全过
8. executor / Control / Level C tool 回归 —— `tests.test_minitouch_trajectory_executor`
   `15/15`、`tests.test_control_swipe_trajectory` `9/9`、`tests.test_touch_swipe_mumu_tool`
   `37/37`

- `toolkit\python.exe -m compileall -q module\device\touch_swipe_model.py` OK。
- `tests.test_touch_swipe_model` `56/56`（`test_new_params_have_sane_defaults` 用
  `assertGreater` 判定 → 新值 `1.35 > 1.0` / `0.35 > 0.0` 通过；`invalid_params` 的
  `tail_density_gain=0.9/5.0` / `tail_slow_gain=-0.1/3.5` 越界拒绝仍有效）。
- `toolkit\python.exe -m unittest discover -s tests` → **`897/897 OK`**（数量不变，无新增测试）。
- `git diff --check`（`touch_swipe_model.py`）干净。

### 下一轮 MuMu Level C（人工，本轮未启动 MuMu）

MuMu → Android 设置 → 应用管理长列表：

```
toolkit\python.exe dev_tools\test_touch_swipe_mumu.py --config oas1
toolkit\python.exe dev_tools\test_touch_swipe_mumu.py --config oas1 --curve left
toolkit\python.exe dev_tools\test_touch_swipe_mumu.py --config oas1 --curve right
toolkit\python.exe dev_tools\test_touch_swipe_mumu.py --config oas1 --curve straight
toolkit\python.exe dev_tools\test_touch_swipe_mumu.py --config oas1 --start 520,520 --end 520,400
toolkit\python.exe dev_tools\test_touch_swipe_mumu.py --config oas1 --start 520,620 --end 520,180
```

重点看：B —— 尾部 WAIT 仍平滑增加但**斜率比上一版温和**；C —— 尾部 speed 仍明显下降但
**最后不再长时间贴近 0**。人工观察：是否还有「黏住终点」感、UP 是否更干净、是否恢复过多
fling、页面滚动距离有无明显变化。

### 文档同步

- AI_CONTEXT.md：已更新（§4.42「第二阶段」的两个参数值 1.55/0.55 → 1.35/0.35 + 静态数据表
  改为 AFTER 值 + 一句「尾部力度收一档」）。
- DEVELOP_LOG.md：本条。
- ROADMAP.md：已更新（「已完成」第二阶段行的两个参数值同步）。
- DECISIONS.md：无需更新（D018 第二阶段追加已明确 `tail_density_gain` / `tail_slow_gain`
  等具体值「Level C 可调、不入 ADR」；本轮正是这类调整）。
- ARCHITECTURE.md：无需更新（参数调档，非架构 / 分层 / 契约变化）。
- TESTING.md：无需更新（未改测试分级 / 验证流程 / 真机要求）。

### Git

分支 `master`，HEAD 仍 `2cdf3a0571b0449748aabef259da5cbd2378536c`。未 commit / push / merge /
reset / clean / stash，未触碰无关 WIP（`assets.py` whitespace warning 未动）。本轮仅改
`module/device/touch_swipe_model.py`（2 个默认值）。

## 2026-09-04 - KekkaiUtilize TouchSwipe 接入 K1（标准 PASS 搜索的列表下划：ADB → minitouch trajectory）

正式生产消费者接入。**只改 `tasks/KekkaiUtilize/script_task.py` + `tests/test_kekkai_utilize_state.py`**。
只迁移「输入后端」——业务逻辑（D017 契约）、滑动距离、settle 全部不动。未启动 MuMu。

### 修改前调用链

`_run_search_pass`（标准 PASS 搜索）**和** `_select_lazy_resource_card`（怠惰模式）**共用**
`perform_swipe_action()`：`random_int(*SWIPE_START_X_RANGE(340,600))` /
`random_int(*SWIPE_START_Y_RANGE(500,565))` → `p1=(x,y)` / `p2=(x, y-SWIPE_DISTANCE(416))`
→ `self.device.swipe_adb(p1, p2, duration=2)`（绕过 `Control.swipe` / 无 BehaviorTrace）→
`click_record_clear()` → `time.sleep(2)`。

### 修改后调用链

- **标准 PASS** `_run_search_pass` 的下划入口 `self.perform_swipe_action()` →
  **`self._perform_search_swipe()`**（新，极薄）：
  - `control_method == 'minitouch'`：`start=(rand_x, rand_y)` / `end=(rand_x, rand_y-416)`
    （**同一起点安全区、同一 416px 主方向位移**）→ `TouchSwipeModel().generate(start, end)`
    （**只生成一次**，用第二阶段正式默认参数：minimum-jerk + ±X 有界曲率 + dt EMA 平滑 +
    尾段慢拖 `tail_density_gain=1.35` / `tail_slow_gain=0.35` / `tail_start_ratio=0.85` /
    `dt_smooth_alpha=0.72` / `tail_correction_enable=False`，本轮不覆盖）→ 一条 INFO 日志
    （start / end / distance / points / total_dt，不刷每个 MOVE 点）→
    `self.device.swipe_trajectory(trajectory, control_name='KEKKAI_UTILIZE_SWIPE')`（经
    `Control.swipe_trajectory` → minitouch executor → BehaviorTrace `ACTION`/`swipe`）→
    `click_record_clear()` → `time.sleep(2)`。
  - **非 minitouch**（adb / uiautomator2 / scrcpy / window_message）：**显式回退**
    `self.perform_swipe_action()`（旧 ADB 路径逐字不变），不构造 `TouchSwipeModel`、不调
    `swipe_trajectory`、不抛 `NotImplementedError`。这是业务调用点的显式兼容，不改
    `Control.swipe_trajectory` 的非 minitouch 契约（D018）。
- **怠惰模式** `_select_lazy_resource_card` 的下划**仍是 `perform_swipe_action()`**（`swipe_adb`
  直连），**完全不受影响**。全模块 `self.device.swipe_adb(` 调用点仍恰好 **1** 处（在
  `perform_swipe_action` 内）。

### 输入参数

| 项 | 值 | 与迁移前 |
|---|---|---|
| start.x | `random_int(340, 600)`（公共 `module/base/utils/random`，SystemRandom） | 同 |
| start.y | `random_int(500, 565)` | 同 |
| end | `(start.x, start.y - 416)` | 同（`SWIPE_DISTANCE=416` 常量未改） |
| TouchSwipe 参数 | 全部用模型当前正式默认值 | 本轮不覆盖 |
| control_name | `'KEKKAI_UTILIZE_SWIPE'` | 新（BehaviorTrace target） |
| settle | `click_record_clear()` + `time.sleep(2)` | 同 |

### D017 业务契约不变（逐项）

`_perform_search_swipe` 只是 `_run_search_pass` 循环里「点击 → 读收益 → 判阈值 → 到底判定」
之间那一次下划的**输入实现**。**未碰**：PASS 顺序（跨优先 跨6→同6→降一档→跨5/6→同5/6final /
同优先 同6→跨6→同5/6final）、`PassResult` / `SearchPass` / threshold HIT / `PASS_MISS` /
`ABORT` / `FINAL_USE_LAST` / `clicked_any` / final fallback / 最后选中候选语义 /
`lower_reward_tier` / reward tiers / `I_U_EMPTY_CARD` 到底判定 / group switch /
`_reset_utilize_friend_list`（`S_U_END` swipe）/ `check_card_num` / OCR /
`C_SELECT_CARD.roi_front` 动态点击 / `find_everyone` y 升序 / `SEARCH_MAX_SWIPES=20` /
`DETAIL_LOAD_WAIT=2` / 怠惰模式。**未做**（属后续）：2~3 行小步（K2）/ FrameWait（K3）/
实际 scroll dy·新旧区域过滤·candidate history·phase correlation（K4）/ bottom 逻辑重构。
不复制 `drag` 的 `wait(140)x2` / 不加 pre-UP pause / 不叠 `random_delay` / `confirm_delay`
/ fatigue / reaction time。

### 测试

- 新增 `tests/test_kekkai_utilize_state.py::PerformSearchSwipeK1Test`（6）：minitouch 下
  ① 用正式 `TouchSwipeModel` 且 `generate` 只调一次；② start/end 来自旧安全区（`random_int`
  `(340,600)` / `(500,565)`）；③ 主方向位移恰 `SWIPE_DISTANCE=416`、X 不变；④/⑤ 调
  `device.swipe_trajectory` 且轨迹**同一对象原样传入**；⑥ `control_name='KEKKAI_UTILIZE_SWIPE'`；
  ⑦ 不调 `swipe_adb` / `Control.swipe`；⑧ 顺序 `swipe -> click_record_clear -> sleep(2)`。
  非 minitouch（adb/uiautomator2/scrcpy/window_message）→ 回退 `perform_swipe_action`、
  不构造 `TouchSwipeModel`、不调 `swipe_trajectory`、不抛 `NotImplementedError`、旧
  `swipe_adb` 参数逐字不变。源码断言：`_run_search_pass` 调 `_perform_search_swipe` 不再调
  `perform_swipe_action`；`_perform_search_swipe` 用公共 `random_int`、无 `140` / 无
  `wait(`、有 `click_record_clear` / `sleep(2)` / `SWIPE_DISTANCE`。
- 新增 `LazyModeUntouchedTest::test_lazy_still_uses_perform_swipe_action_not_the_k1_helper`：
  `_select_lazy_resource_card` 仍调 `perform_swipe_action()`、不含 `_perform_search_swipe`。
- 改 `RunSearchPassTest`：`_task` mock `t._perform_search_swipe`（PASS 循环控制流测试不关心
  输入后端）；2 处 swipe 计数断言 `t.perform_swipe_action.call_count` → `t._perform_search_swipe.call_count`
  （语义等价：同样的滑动次数）。
- **D017 既有测试全部继续通过**（四 PASS 顺序 / threshold hit / PASS_MISS / ABORT /
  FINAL_USE_LAST / clicked_any / bottom / lower once / same·cross ordering / lazy）；
  `PerformSwipeActionCharacterizationTest`（`perform_swipe_action` 仍 `swipe_adb`）不动、
  全过；`test_swipe_adb_direct_call_sites_in_utilize_module`（`== 1`）无需改（回退复用
  `perform_swipe_action`）。
- `toolkit\python.exe -m compileall -q tasks\KekkaiUtilize\script_task.py
  tests\test_kekkai_utilize_state.py` OK。
- Kekkai 组（`test_kekkai_utilize_state` + `test_kekkai_utilize_threshold` +
  `test_kekkai_activation_state`）`97/97`；touch-swipe 组（`test_touch_swipe_model` +
  `test_minitouch_trajectory_executor` + `test_control_swipe_trajectory` +
  `test_touch_swipe_mumu_tool`）`114/114`。
- `toolkit\python.exe -m unittest discover -s tests` -> **`904/904 OK`**（897 -> 904，+7）。
- `git diff --check`（`script_task.py` / `test_kekkai_utilize_state.py`）干净。
- 端到端冒烟（真实 `TouchSwipeModel` + 真实 `random_int`）：start `(477,521)` / end `(477,105)`
  / y 位移 416 / 29 点 / total_dt 360ms / `control_name='KEKKAI_UTILIZE_SWIPE'` /
  `click_record_clear` + `sleep(2)` 均触发 / INFO 日志一行。

### 下午 MuMu Level C（人工，本轮未启动 MuMu）

**配置**：待跑 config `script.device.control_method = minitouch`（默认即是）。

**斗鱼 HIGH 阈值临时建议 152**：最高真实斗鱼档是 151，若 HIGH PASS 阈值就设 151 会在
第一张 151 卡直接 HIT、提前结束、滑不了几屏。设 152 -> HIGH PASS 不会在 151 提前结束、
能多滑几段观察 minitouch 连续扫描。**但注意 D017 的「降一档」**：`152 -> lower_reward_tier(152,
FISH_REWARD_TIERS) -> 151`，所以之后的 LOWER PASS 仍可能在 151 命中 —— 152 适合看
「前几个 HIGH PASS 多滑一段」，**不保证所有 PASS 必到底**。太鼓同理（最高档 76，HIGH 可临时
设 77）。**本轮不为测试改 reward tier 生产代码。**

**人工检查表**：

- **A 输入链路**：是否确实走 minitouch trajectory（看日志 `KekkaiUtilize trajectory swipe`
  + BehaviorTrace 若开有 `ACTION`/`swipe`/`target=KEKKAI_UTILIZE_SWIPE`）；没有回落
  `swipe_adb`；没有 `NotImplementedError`。
- **B 列表表现**：416px trajectory 能否正常滚动一屏；有没有被识别成 click；有没有明显
  fling；尾段是否正常（收一档后不「黏住」）；页面推进是否大致与旧 ADB swipe 一样。
- **C 业务**：swipe 后 `find_everyone()` 仍正常出候选；`C_SELECT_CARD` 动态 bbox 点击正常；
  详情 OCR 正常；PASS 能继续往下；`I_U_EMPTY_CARD` 到底仍能判；final fallback 未因输入迁移
  变化。
- **D 日志**：记录 start / end / point_count / total_dt / 当前 PASS / 当前 group /
  是否 minitouch。

**真机若发现滚动距离不合适 / 重复候选 / 过冲 / 需接 FrameWait / bottom 不稳** —— **本轮不预
先解决**，分别留给 K2（2~3 行小步）/ K3（FrameWait）/ K4（scroll dy·新旧区域过滤），保持
可归因。

### 文档同步

- AI_CONTEXT.md：已更新（§4.41 补 K1 接入 + §4.42「Level C 待验收」补「首个生产消费者 =
  KekkaiUtilize 标准 PASS」；§7 基线 897 -> 904 + 覆盖点；§8.2 的「perform_swipe_action 仍
  swipe_adb」补 nuance）。
- DEVELOP_LOG.md：本条。
- ROADMAP.md：已更新（TouchSwipeModel Plan B「④ 逐调用点显式接入」/ D017 Level C 清单的
  「`perform_swipe_action` ADB->minitouch」-> K1 已实现、Level C 待验；新增 K2/K3/K4 后续项）。
- ARCHITECTURE.md：已更新（§2 `TouchSwipeModel` / §3「自定义轨迹滑动」链的「零消费者」->
  「首个生产消费者 = KekkaiUtilize 标准 PASS 搜索（K1）」；「滑动」旁路的
  `perform_swipe_action` 直连 swipe_adb 说明补「标准 PASS 已 K1 迁 minitouch trajectory」）。
- DECISIONS.md：已更新（D018 补一句事实「首个生产 consumer = KekkaiUtilize 标准 PASS 搜索
  （K1，2026-09-04），仅换输入后端、几何/lazy 不动」；D017 的「不改 perform_swipe_action
  swipe_adb」注补「K1 已按 D018 把**标准 PASS**下划迁 minitouch-trajectory，几何/lazy/settle
  不动，Level C 待验」。**未新增 ADR，未把 416px 写成长期决策。**）
- TESTING.md：无需更新（未形成新的长期通用测试规则）。

### Git

分支 `master`，HEAD 仍 `2cdf3a0571b0449748aabef259da5cbd2378536c`。未 commit / push / merge /
reset / clean / stash，未触碰无关 WIP（`assets.py` whitespace warning 未动）。本轮改
`tasks/KekkaiUtilize/script_task.py`（+import、`_run_search_pass` 换调用、新 `_perform_search_swipe`）
+ `tests/test_kekkai_utilize_state.py`（+7 用例 + `RunSearchPassTest` 适配）。

## 2026-09-04 - OASX「统计 → 点击分布」显示 0：根因 = BehaviorTrace 未开启（配置项，非代码 bug）

### 中断任务回退（plot_click_scatter）

上一轮「新增 `dev_tools/plot_click_scatter.py` 离线散点工具」的方向被叫停。回退：
- **删除** `dev_tools/plot_click_scatter.py`（本轮 Claude 用 `Write` 新建、`git ls-files
  --error-unmatch` 确认从未被 git 跟踪、仅其自身 docstring 引用）+ 其 `__pycache__/*.pyc`。
- **未新建** `tests/test_click_scatter_tool.py`（中断时尚未开始）。
- **未改任何 tracked 文件、未改任何 docs**（该中断任务只做了一次 `Write`）。
- 所有既有 WIP（36 个 `M` + 全部 `??`：KekkaiUtilize K1 / TouchSwipeModel / control.py /
  minitouch.py / docs/ / assets.py / 其它 dev_tools / tests）**逐一保留、零改动**。
- 回退后 `git status` = 86 项，与 K1 轮收尾一致；无来源不明残留；全量 `904/904` 未变。

### 根因（ROOT CAUSE）

用户实际跑过 OAS、在**运行日志**（`log/2026-09-04_oas2.txt`，`control.py:0079 INFO [..] Click
(x, y) @ target`）里看到 8 次点击，据此判断「点击记录已产生」。但「统计 → 点击分布」页读的是
**BehaviorTrace JSONL**（`log/behavior/<config>_<日期>.jsonl`），这是一条**独立**的 opt-in
观测 sink：

- `config/oas1.json` / `config/oas2.json` 都是 `"behavior_trace_enable": false`
  （D004「默认关闭」的默认值，从未打开过）。
- `script.py:81` `configure_behavior_trace(config_name, enabled=bool(config.script.optimization.
  behavior_trace_enable))` → 传 `enabled=False`。
- `BehaviorTrace.record()` 在 `not self._enabled` 时**首行返回**，不建目录、不写文件。
- `Control.click` / `Control.long_click` 的 `get_behavior_trace(...).record('ACTION',
  action='click', ..., extra={'x': x, 'y': y})` 因此是**空操作**。
- 结果：**`log/behavior/` 目录根本不存在**，任何 `*.jsonl` 都没有（全仓仅
  `log/manual_click/*` 是 `ManualClickRecorder` 的另一套数据）。

**链路逐层核验（C~G 全部正确，无代码 bug）：**

| 层 | 结论 |
|---|---|
| A. `Control.click` 执行 + `logger.info` | ✅ 点击发生、写进普通运行日志 |
| A'. `BehaviorTrace.record()` | ❌ **空操作**（`behavior_trace_enable=false`） |
| B. `log/behavior/oas2_2026-09-04.jsonl` | ❌ **从未创建** |
| C. `module/server/behavior_stats.read_behavior_clicks` | ✅ 用真实 schema JSONL 实测 `total=4` / `click_count=3` / `long_click_count=1` / `task_count=2` / tasks·points·x·y·ts·elapsed_ms 全对、swipe·TASK 行被过滤；文件不存在时返回 `total:0`（= 现况）。写路径 `_LOG_DIR=Path("log/behavior")` 与读路径 `BEHAVIOR_LOG_ROOT=Path.cwd()/"log"/"behavior"` 因 `module/logger.py:60` 两个进程都 `os.chdir` 到仓库根而**一致**，无 cwd/glob/文件名不匹配 |
| D. `GET /stats/{config}/behavior/clicks?date=YYYY-MM-DD` | ✅ 透传 `read_behavior_clicks`；日期是纯 `strptime("%Y-%m-%d")` 拼文件名，无 UTC/本地歧义 |
| E. OASX `ApiClient.getBehaviorClicks` + `BehaviorClicksResponse.fromJson` | ✅ key 与后端逐字对应（`summary.total` / `click_count` / `long_click_count` / `task_count` / `tasks` / `points[].x/y/task/action/target/ts/elapsed_ms`），无 DTO 不匹配 |
| F. `HomeBehaviorClicksController` | ✅ 空响应 → `summary.total=0` / `tasks=[]` / `filteredPoints=[]`，date/task/refresh 逻辑正确（`test/behavior_clicks_test.dart` 已覆盖含「空数据」组） |
| G. `behavior_clicks_panel.dart` | ✅ `total:0` → 显示 0；`points.isEmpty` → 显示「当天暂无点击记录」——对空数据的**如实**呈现 |

即：**每一层都在正确地把「没有数据」呈现为 0**。这不是展示链 bug，是数据源（opt-in 观测层）
从未开启。

### 修复（FIX）—— 配置开关，非代码

`config/oas1.json` / `config/oas2.json` 的 `script.optimization.behavior_trace_enable`
**`false` → `true`**（两文件均 `.gitignore` 忽略，`git status` 不显示；用户可随时在 OASX
配置编辑器「优化 / Optimization」里或直接改回）。

- **未改任何代码**：OAS 侧（`BehaviorTrace` / `Control.click` / `behavior_stats` /
  `stats_router` / reader / API）与 OASX 侧（controller / models / api_client / panel /
  scatter）全部保持原样 —— 已核验正确。
- **未改点击行为**：`ClickSampler` / `HABIT` / `LEGACY_UNIFORM` / `BaseTask.click` /
  `appear_then_click` / `Control.click` / `Minitouch.click` / GeneralBattle / KekkaiUtilize /
  RealmRaid / TouchSwipeModel —— 零改动。
- **未新增测试**：整条链已被 `tests/test_behavior_trace.py`（14）+
  `tests/test_behavior_click_stats.py`（24，含 `test_disabled_trace_writes_nothing` =
  本场景、`test_click_records_final_coordinates` = `extra.x/y` 是最终执行坐标、
  `ReadBehaviorClicksTest` = 真实 schema reader）+ OASX `test/behavior_clicks_test.dart`
  覆盖。全量 `904/904` 未变。

### 用户操作（今天的旧点击无法找回）

`behavior_trace_enable` 只在**脚本进程创建时**读一次（`script.py:80` 注释；OASX 每 config
独立子进程）。因此：**停止并重新启动**对应 config 的 OAS 运行（新进程 →
`configure_behavior_trace(config, enabled=True)`）→ 跑几步产生点击 →
`log/behavior/oas2_<日期>.jsonl` 开始写入 → OASX「统计 → 点击分布 → 日期 2026-09-04 →
刷新」即出现非零散点。**开关打开之前发生的点击没有写进 JSONL，无法补录。**

### 文档同步

- AI_CONTEXT.md：已更新（§4.17 补一句「OASX 点击分布页要有数据需
  `behavior_trace_enable=true`；已在 `config/oas1.json`/`oas2.json` 打开」）。
- DEVELOP_LOG.md：本条。
- ROADMAP.md：无需更新（未新增 / 完成 / 改优先级的任务项；OASX 点击分布页本就在
  「已完成」表标为「前端页面待下一轮」，前端 WIP 属 OASX 仓库）。
- ARCHITECTURE.md：无需更新（分层 / 调用链 / 契约均未变，且已核验正确）。
- DECISIONS.md：无需更新（未形成 / 推翻长期决策；D004「BehaviorTrace 默认关闭」不变）。
- TESTING.md：无需更新（未改测试分级 / 验证流程 / 真机要求）。

### Git（OAS 仓库）

分支 `master`，HEAD 仍 `2cdf3a0571b0449748aabef259da5cbd2378536c`。未 commit / push / merge /
reset / clean / stash。本轮改动：删除中断任务的 `dev_tools/plot_click_scatter.py`；
`config/oas1.json` / `config/oas2.json` 的 `behavior_trace_enable` 翻 `true`（gitignored，
不进 `git status`）；`docs/DEVELOP_LOG.md` + `docs/AI_CONTEXT.md` 追加/一行。既有 36 个 `M`
+ 全部 `??` WIP 未触碰。

### Git（OASX 仓库 d:\oas_xy\OASX）

分支 `master`，HEAD `035aece1242bf22ed7257814908c2f031fc94fc6`。**本轮零改动** —— OASX 点击
分布 controller / models / api_client / panel / scatter / `test/behavior_clicks_test.dart`
均已核验正确，无 bug 可修。既有 26 项 WIP（13 `M` + 未跟踪的 `behavior_clicks_*` 系列）
未触碰。

## 2026-09-04 - RuleOcr 浮点 OCR bbox → 整数点击 ROI 兼容修复（FIXED）

### 背景

Codex 真机（`oas2`）从「结界」页导航到「式神育成」页时崩：

```
TypeError: ROI必须由整数组成：(595.0, 293.0, 34.0, 101.0)
```

调用链：KekkaiUtilize 页面导航 → OCR 命中「式神育成」（`O_R_SHIKIGAMI`，FULL 模式）→
`BaseTask.ocr_appear_click()` → `RuleOcr.coord()` 取 `self.area` → `ClickSampler.sample(area)`
→ `LEGACY_UNIFORM` → `module.base.utils.random.random_point_in_roi(area)` 在非整数 ROI 上
`raise TypeError('ROI必须由整数组成：...')`（消息无空格，正是 `random_point_in_roi` 抛的，
不是 `ClickSampler._as_int_roi` 的「ROI 必须由整数组成」）。

### 根因

`Full.ocr_full()`（`module/ocr/sub_ocr.py`）命中关键字后，用 OpenCV 检测框（`BoxedResult.box`
是 numpy `(4,2)` 浮点角点）+ `self.roi` 偏移覆写 `self.area`：

```python
self.area = box[0,0]+self.roi[0], box[0,1]+self.roi[1], box[1,0]-box[0,0], box[2,1]-box[0,1]
```

产出浮点 `(x, y, width, height)`。自 **D007**（`b72eec29` “统一底层随机坐标与延时生成”）起：
① 新增的 `random_point_in_roi()` 带 `if not all(isinstance(v, Integral) for v in roi): raise TypeError`；
② 同一提交把 `RuleOcr.coord()` 从 `x=np.random.randint(x, x+w)`（静默截断浮点、会缩框但不报错）
改成 `return random_point_in_roi(area)`。**latent 断裂从 D007 就在**——只是一直没在真机跑到
FULL 模式 OCR 点击这条路径。T7-1（§4.24）把 `coord()` 里 `random_point_in_roi(area)` 换成
`ClickSampler.sample(area)`，`LEGACY_UNIFORM` 逐字转调同一个 `random_point_in_roi`，
**严格度没变**，这次只是被真机跑到了。

### 修复（`RuleOcr` 专属边界，不放宽任何下游契约）

`module/atom/ocr.py`：

- 新增模块级 `_normalize_ocr_click_area(area)`：格式 `(x, y, width, height)` →
  `x1=floor(x)` / `y1=floor(y)` / `x2=ceil(x+width)` / `y2=ceil(y+height)` → 回到
  `(x1, y1, x2-x1, y2-y1)`。左 / 上 `floor`、右 / 下 `ceil` 保证整数框**完整包住原浮点框、
  绝不因取整缩小可点区域**（禁用 `tuple(int(v) for v in area)` 截断）。贴屏幕右下边缘时
  `x2`/`y2` 裁到常量 `_OCR_CLICK_MAX_X=1280` / `_OCR_CLICK_MAX_Y=720`（`random_point_in_roi`
  半开上界，越界 1px 会点到屏幕外）；兜底 `max(1, ...)` 保证宽 / 高 ≥ 1；`None` / 非四元组
  原样透传。
- `coord()`：`return ClickSampler.sample(_normalize_ocr_click_area(area))`。

**未改**：`random_point_in_roi`（仍拒绝浮点 ROI）、`ClickSampler.sample`（不静默强转所有浮点
ROI）、`ClickSampler` 策略 / HABIT / LEGACY_UNIFORM / preferred_center / core·medium·tail /
ROI 尺寸适配 / fallback 投影 / `SystemRandom` / `BehaviorTrace` schema / `Control.click` /
`BaseTask.click` / `appear_then_click` / `RuleClick` / `RuleImage`。KekkaiUtilize K1
（`TouchSwipeModel` / `Control.swipe_trajectory` / minitouch 轨迹执行 / `_perform_search_swipe` /
`SWIPE_DISTANCE=416` / `sleep(2)` / D017 PASS 逻辑）本轮**一行未动** —— K1 尚未在这次失败中
执行，K1 本身不是当前异常来源。

### 规范化验证（关键用例）

| 输入 area | 输出（整数 ROI） | 说明 |
| --- | --- | --- |
| `(595.0, 293.0, 34.0, 101.0)`（真机值） | `(595, 293, 34, 101)` | 全整数、无 TypeError、语义不变 |
| `(595.4, 293.6, 34.2, 101.7)` | `(595, 293, 35, 103)` | 完整包住 `x∈[595.4,629.6] y∈[293.6,395.3]`，不缩小 |
| `(595, 293, 34, 101)`（已整数） | `(595, 293, 34, 101)` | floor/ceil 是恒等变换 |
| `(10.8, 20.2, 0.4, 0.6)`（亚像素） | `(10, 20, 2, 1)` | 宽 / 高仍 ≥ 1，包住原框 |
| `(1279.6, 719.6, 1.0, 1.0)`（贴右下） | `(1279, 719, 1, 1)` | 裁到 1280 / 720，落点仍在屏幕内 |

### 影响范围（零 per-task 改动）

全仓动态 OCR 文本点击都收敛在 `RuleOcr.coord()` 一个点：`BaseTask.ocr_appear_click`
（`grep` 得 24 处调用，横跨 GameUi 导航 / Buy / Login / SwitchSoul / Delegation / Exploration /
SoulsTidy / WantedQuests / WeeklyPurchase / KekkaiUtilize 等）、`GameUi/navigator.py` 的 OCR
导航、`module/atom/list.py` 的 OCR 列表点击、`Chess` 刷新 OCR。只有 FULL 模式用 `self.area`
（浮点来源）会实际受益；SINGLE / DIGIT / DIGITCOUNTER / DURATION 用静态整数 `self.roi`，
规范化对它们是 no-op。`Quantity.ocr_quantity` 也写浮点 `self.area`，但 `coord()` 非 FULL 分支
取 `self.roi`、不碰它。`RuleImage` / `RuleClick` 的 `coord()` 不经此函数（测试锁）。

### 测试

新增 `tests/test_rule_ocr_float_roi.py`（18 用例）：

- `NormalizeOcrClickAreaTest`（9）：真机值 → 全整数 + 交 `random_point_in_roi` 不抛；真分数框
  几何包含且不缩小；已整数框 / list 形态 / `595.0` 全整数浮点 → 同一整数框；亚像素小框仍非零；
  贴右下裁到屏幕内；零尺寸框兜底 1px；numpy `float64` 入参 → 纯 Python `int`；400 个随机分数框
  的包含性 + 宽高 ≥ 1 属性；`None` / 三元组透传。
- `RuleOcrCoordFloatRoiTest`（4）：mock `module.atom.ocr.ClickSampler.sample`，确认 FULL 模式
  浮点 area 在**调采样器之前**就被整数化（采样器收到的是 `(595,293,34,101)`，不是靠内部兜底）；
  分数 area → 采样器收到包住原框的整数 ROI；SINGLE 模式静态整数 `self.roi` 原样透传；
  不 mock 走真实 `LEGACY_UNIFORM` → 200 次落点在 `[595,629)×[293,394)`、无 TypeError。
- `RuleOcrEndToEndOcrFullChainTest`（1）：mock `detect_and_ocr` 返回 numpy 浮点 box + `filter`
  返回 `[0]` → `Full.ocr_full()` 真的写浮点 `self.area` → `coord()` → 真实 `ClickSampler` →
  200 次落点均在「完整包住浮点框」的整数区内、且在屏幕内。
- `RuleClickRuleImageUnaffectedTest`（4）：`RuleClick.coord` / `RuleImage.coord` 源码不含
  `_normalize_ocr_click_area`；`RuleClick` 静态 ROI 落点边界不变；规范化对 `RuleClick`/`RuleImage`
  那类静态整数 ROI 是 no-op。

验证顺序：`test_rule_ocr_float_roi` `18/18 OK` → `test_click_sampler` `19/19 OK` →
KekkaiUtilize（`test_kekkai_*` 汇总 `97/97 OK`）→ T7 点击分布族（`test_click_profile` /
`test_behavior_trace` / `test_behavior_click_stats` 汇总）+ `test_touch_swipe_*` 全绿 →
`toolkit/python.exe -m compileall -q module/atom/ocr.py tests/test_rule_ocr_float_roi.py` OK →
`toolkit/python.exe -m unittest discover -s tests` **`922/922 OK`**（904 → 922，+18）→
`git diff --check -- module/atom/ocr.py` 干净。

### Level C 下一步

真机 `oas2` 重启 → 结界 → OCR「式神育成」→ 点击进页（此前直接崩、K1 到不了）；→ 式神育成 →
好友寄养 → KekkaiUtilize 搜索 → 标准 PASS → `_perform_search_swipe` → `TouchSwipeModel` →
minitouch 轨迹 → 416px K1；`behavior_trace_enable` 已开（§4.17 前置），确认
`log/behavior/oas2_<日期>.jsonl` 落点坐标 + OASX「统计 → 点击分布」出真实散布。

### 文档同步

- AI_CONTEXT.md：已更新（§4.1 补 `_normalize_ocr_click_area` 说明；§4.24 补「整数 ROI 契约
  D007 起就有、本层不放宽」；新增 §4.43；§7 基线 `904 → 922` + 列 `test_rule_ocr_float_roi.py`；
  §4.41 K1「前置已解除」；§2 `ocr.py` 的 `M` 原因补一句）。
- DEVELOP_LOG.md：本条。
- ROADMAP.md：已更新（K1 行补一句：`RuleOcr` 浮点 bbox 兼容修复解除了「结界→式神育成」导航
  崩溃这个 K1 Level C 前置阻断）。
- ARCHITECTURE.md：已更新（§调用链 `RuleOcr.coord()` 行补「FULL 模式浮点 area 先 floor/ceil
  规范化」一句，属真实调用链地图的精度修正）。
- DECISIONS.md：已更新（D014 加一条注记，**非新 ADR**）：动态 OCR bbox（`Full.ocr_full` 写入
  `self.area` 的 OpenCV 浮点框）在 `RuleOcr.coord()` 自己的边界 floor/ceil 规范化成整数 ROI
  再交给 `ClickSampler`；`ClickSampler` / `random_point_in_roi` 的整数 ROI 契约、
  `RuleClick` / `RuleImage` 静态整数 ROI 语义均不变。
- TESTING.md：已更新（§5 加一条长期原则：动态 OCR bbox 浮点 → 整数点击 ROI 的兼容必须有
  回归覆盖，`RuleOcr.coord()` FULL 模式不得把浮点 area 直接下传给采样器 / `random_point_in_roi`）。

### Git

分支 `master`，HEAD 仍 `2cdf3a0571b0449748aabef259da5cbd2378536c`。未 commit / push / merge /
reset / clean / stash。本轮改动：`module/atom/ocr.py`（`M`，加 `import math` +
`_normalize_ocr_click_area` + 常量 + `coord()` 包一层）；新增 `tests/test_rule_ocr_float_roi.py`
（`??`）；`docs/` 六份里 AI_CONTEXT / DEVELOP_LOG / ROADMAP / ARCHITECTURE / DECISIONS /
TESTING 均有追加。既有其它 `M` + `??` WIP 未触碰。

## 2026-09-04 - T7-5 全局 Preferred Hotspot 点击策略迁移（Stage 1，生产默认策略变更）

### 目标与边界

把「普通生产 Point 点击的**默认** = Rule 对象 ROI 内一次整 ROI 均匀随机（`LEGACY_UNIFORM` /
`random_point_in_roi`）」改成「默认 = 该 target 的 preferred 热点 → 语义 profile →
`adapt_point_profile` 按运行时 ROI 尺寸适配 → `ClickSampler` core/medium/tail 偏移模型 →
Safe ROI」。没有经验热点的 target **不退回 Uniform**，而是 `CENTER_FALLBACK`
（preferred = `(0.5, 0.5)`）+ 新 `default_point` profile + 同一套偏移模型。

这是 `docs/DECISIONS.md` D014 的**有意 supersede**：两条旧约束
（「默认策略永远是 `LEGACY_UNIFORM`」「Point Target 必须逐调用点显式 opt-in」）标 `Superseded`。
D014 其余边界（Safe ROI 硬边界、连续 `size_factor` 无硬分档、人工 / behavior 数据分离、
一次点击一次空间采样、`ManualClickRecorder` 只观察）继续有效。

按任务书 §34「先改公共 Rule 层默认语义 → 再盘点旁路 → 逐类迁移」，本轮只做 **Stage 1**
（公共 Rule 层）。

### 改动（生产代码）

- **新增 `module/click_preference.py`**：
  - `Provenance`（str Enum）四级：`EMPIRICAL` / `SEMANTIC_TRANSFER` / `PROVISIONAL` /
    `CENTER_FALLBACK`。
  - `TargetPreference`（frozen dataclass）：`target_name` / `preferred_u` / `preferred_v` /
    `profile_name` / `provenance` / `confidence` / `note`，构造即校验（u/v ∈ [0,1]、
    confidence ∈ [0,1]、profile_name 非空）。
  - `TARGET_PREFERENCES: dict[str, TargetPreference]`：静态代码 registry，按 `rule.name`
    索引（= BehaviorTrace `target` 同名）。**当前唯一条目 `area_1`**（`RyouToppa.C_AREA_1`，
    `EMPIRICAL`，`(0.58, 0.59)` + `wide_card`，来源 `log/manual_click/yys1_2026-09-01.jsonl`
    cluster_A vs 真实 RuleClick ROI `(514,141,223,116)`，inside 105/107，
    mean (0.582,0.586) ≈ median (0.579,0.586)）。
  - `resolve_target_preference(name)`：命中 → 该条；未命中 / 空名 → `CENTER_FALLBACK`
    （`(0.5, 0.5)` + `default_point`，confidence 0）。
  - `provenance_counts()`（inventory / 报告用）。
- **`module/click_profile.py`**：`DEFAULT_PROFILES` 加 `default_point`（数值同 `default`：
  preferred (0.5,0.5) / core σ 0.10 / medium σ 0.18 / core 0.82·medium 0.16·tail 0.02 /
  margin 0.06 / provisional）。单列名字让「全局 Point 默认」链路可读，**不写任何个人热点**。
- **`module/click_sampler.py`**：加 `ClickSampler.sample_target(roi, target_name)` =
  `resolve_target_preference` → `resolve_profile(profile_name)` → 把 preferred 写进 profile
  （`replace`）→ `adapt_point_profile(base, roi)` → `sample(strategy=HABIT, profile=effective)`。
  顶层 `from module.click_preference import resolve_target_preference`（无循环：`click_preference`
  只依赖 stdlib）。
- **`module/atom/{click,image,gif,ocr}.py`**：`coord()`（`click`/`image` 的 `coord_more()`
  一并）从 `ClickSampler.sample(roi)` 改为 `ClickSampler.sample_target(roi, self.name)`。
  `ocr.py` **保留** `_normalize_ocr_click_area()`（FULL 模式浮点 bbox → floor/ceil 整数
  ROI，见 2026-09-04 前一条），只是把整数化后的 ROI 交给 `sample_target` 而非 `sample`。
  `RuleLongClick` 继承 `RuleClick.coord`，自动覆盖。

### 未改

`ClickSampler` 采样算法 / `_sample_mixture` / `_sample_gaussian_component` / `_safe_roi` /
`_fallback_point` / HABIT·STRICT·UNIFORM / `adapt_point_profile` / `point_size_factor` /
`POINT_*` 锚点 / `DEFAULT_PROFILES` 其它条目 / `random_point_in_roi`（仍拒绝浮点、仍整 ROI
均匀）/ `random_normal` / `SystemRandom` / `BehaviorTrace` schema / `Control.click` /
`BaseTask.click` / `appear_then_click` / `random_click()` 函数本身及其 `ltrb=(F,F,T,F)`
基线 / `RyouToppa._click_toppa_area`（`C_AREA_1` 经 `sample_point(wide_card)`，与 registry
`area_1` 结果等价、冗余但无害，留作后续合并）/ **GeneralBattle Settlement V3
`_sample_settlement_click`**（直接 `ClickSampler.sample(rule.roi_front)` = 区内
`LEGACY_UNIFORM`，不经 `coord()`；region selection policy「两次 DEFAULT / marker /
80% SAVE_RIGHT·20% SAVE_BOTTOM」一字不变）。

### 影响范围（`dev_tools/click_roi_inventory.py` 重跑）

静态可点击 ROI 定义 **2684**（RuleImage 2077 / RuleClick 300 / RuleOcr 297 /
RuleLongClick 10），跨 55 个 task scope。provenance：**EMPIRICAL 1（`area_1`）/
SEMANTIC_TRANSFER 0 / PROVISIONAL 0 / CENTER_FALLBACK 其余全部**。`normal_button` /
`I_FIRE` 仍 `PROVISIONAL` 候选、**零 registry 引用**（缺 runtime ROI-relative 数据，
Stage 2 用 `runtime_roi_probe` + manual click 标定，不硬造）。28 个 `large_safe_area`
Region 经 `.coord()` 也走 `CENTER_FALLBACK`（区内偏中心、仍在区内）。约 34 处 `device.click(...)`
旁路：A 类（坐标已由 Rule 产生）不动、B 类（硬编码坐标）逐点判断、C 类（task 私有 ROI 随机）
列 BLOCKED —— **Stage 2 逐类迁移，本轮不动**。完整清单 `docs/T7_TARGET_PREFERENCE_MAP.md`。

C_AREA_1（`short_side 116 ≥ 96` → `size_factor = 1`）effective profile 逐字段等于
`wide_card` base → **生产落点分布不变**。

### 测试

- 新增 `tests/test_t7_5_preferred_hotspot.py`（22 用例）：`Provenance` 四级 / `TargetPreference`
  frozen + 校验 / 未知·空名 → `CENTER_FALLBACK` / registry 只含有据条目 + 每条有 `note` /
  `default_point` 居中无个人热点 / `sample_target` 不以 `random_point_in_roi` 为主分布 /
  一次采样（`sample` 恰一次，`strategy=HABIT`）/ 未知 target 中央 25% 面积聚 55% 样本、
  >500 不同坐标、均值贴几何中心（**不是 Uniform、不是固定中心**）/ 五个 Rule 类型 `coord`
  源码都含 `sample_target` / Tiny 20×20 多坐标·均值靠中心·绝对散布 < 大目标/3·effective
  tail=0 / 1×1 Safe ROI 是文档化的确定性例外 / `size_factor` 与 effective profile 在
  23·24·25 和 95·96·97 附近连续 / `sample_target` 源码无硬分档 token / `area_1` EMPIRICAL
  `(0.58,0.59)`+`wide_card`·非旧 `(0.68,0.53)`·f=1 effective == base·采样偏右下 /
  RuleOcr 浮点 bbox → 规范化 → 默认 preferred 采样无 `TypeError`·一次空间采样·未登记 OCR
  文本 = `CENTER_FALLBACK`。
- 改写 10 个锁旧 D014 默认契约的用例：`tests/test_click_sampler.py` 6（`RuleCoordRoutingTest`
  全组改 patch `sample_target` + 断言 `(roi, name)`；`RuleGif` 补 `appear_target`；
  `RuleOcr` 补 `o.name`；`test_rule_default_path_is_sample_target_not_legacy_uniform`；
  end-to-end 改名 `_stays_in_bounds`）、`tests/test_ryoutoppa_c_area_1_point_opt_in.py` 3
  （C_AREA_2 改断言默认 `sample_target` 路径 / `RuleClick.coord` 源码断言改 `sample_target` /
  `areas_2_to_8` 改 patch `sample_target`）、`tests/test_general_battle_settlement.py` 1
  （`RegressionBoundaryTest` 改为断言 coord 走 `sample_target` **且** `_sample_settlement_click`
  仍直接 `ClickSampler.sample(rule.roi_front)`、不含 `sample_target`）。
- `module/click_preference.py` docstring 原用 `normal_button` / `I_FIRE` 举例触发
  `test_normal_button_still_provisional_zero_consumers` 的 grep，改用「普通按钮」「战斗
  开始·进攻按钮」中文表述。

验证顺序：`test_t7_5_preferred_hotspot` `22/22` → `test_click_sampler` `19/19` →
`test_rule_ocr_float_roi` `18/18` → `test_click_profile` `87/87` →
`test_ryoutoppa_c_area_1_point_opt_in` `25/25` → `test_general_battle_settlement` /
`test_general_battle_timing` / `test_behavior_trace` 全绿 →
`toolkit/python.exe -m compileall -q <改动>` OK →
`toolkit/python.exe -m unittest discover -s tests` **`944/944 OK`**（922 → 944，+22 新用例，
10 个改写用例净 0）→ `git diff --check -- <5 个生产文件>` 干净。

### Level C（Stage 1，分批抽样，任务书 §35）

Tiny / Small / Normal / Large·card / Dynamic RuleImage / Dynamic RuleOcr / Large Region /
GeneralBattle V3 各选真实生产消费者，跑 → 看 `log/behavior/<config>_<日期>.jsonl` +
OASX「统计 → 点击分布」散点：热点位置对不对、有没有越 Safe ROI、是否重复固定像素、
spread 与目标尺寸是否匹配。`behavior_trace_enable` 已开。

### 文档同步

- AI_CONTEXT.md：已更新（新增 §4.44；§7 基线 `922 → 944` + 列 `test_t7_5_preferred_hotspot.py`；
  §4.1 RuleOcr `coord()` 说明改成 `sample_target(_normalize_ocr_click_area(...), name)`；
  §4.24 加 T7-5 默认变更注；§2 `module/atom/*` 的 `M` 原因改写 + 记 `module/click_preference.py`
  新文件）。
- DEVELOP_LOG.md：本条。
- ROADMAP.md：已更新（「已完成」加 T7-5 Stage 1 行；T7-1 支线的「第 3 阶段逐调用点 opt-in」
  标被 T7-5 取代；新增 T7-5 Stage 2 待办三项）。
- ARCHITECTURE.md：已更新（分层图 ClickSampler 段重写；Rule* 原子 `coord()` 描述改
  `sample_target`；核心调用链行改 `sample_target`；能力表「点击落点分布」行改写为「生产默认
  已变更」并指向 `T7_TARGET_PREFERENCE_MAP.md`）。
- DECISIONS.md：已更新（D014 加「T7-5（2026-09-04）—— 生产默认策略变更」段 + 两条旧 bullet
  标 `Superseded`；状态行加 T7-5 提示；「相关文件」补 `click_preference.py` /
  `test_t7_5_preferred_hotspot.py` / `T7_TARGET_PREFERENCE_MAP.md` / `atom/*` coord 说明）。
- TESTING.md：已更新（§5 加「T7-5：普通 Point 生产默认『不再整 ROI 均匀』必须有契约测试」
  长期原则，六条子项）。
- 另新增专题 `docs/T7_TARGET_PREFERENCE_MAP.md`（不属六份，全项目 inventory）。

### Git

分支 `master`，HEAD 仍 `2cdf3a0571b0449748aabef259da5cbd2378536c`。未 commit / push / merge /
reset / clean / stash。本轮改动：`module/click_sampler.py` / `module/click_profile.py` /
`module/atom/{click,image,gif,ocr}.py`（`M`）；新增 `module/click_preference.py` /
`tests/test_t7_5_preferred_hotspot.py`（`??`）；改写 `tests/test_click_sampler.py` /
`tests/test_ryoutoppa_c_area_1_point_opt_in.py` / `tests/test_general_battle_settlement.py`
（后两者此前已是 `??` / `M` WIP）；`docs/` 六份 + 新 `T7_TARGET_PREFERENCE_MAP.md`；
`log/click_roi_analysis/*` 重新生成（gitignored）。既有其它 `M` + `??` WIP 未触碰。

## 2026-09-06 - KekkaiUtilize 标准 PASS 前初始化简化（legacy `_reset_utilize_friend_list` → `switch_friend_list`）

### 背景（Level C 触发）

用户 Level C 明确确认一条游戏行为：**只要 SAME/CROSS 发生实际切换，新进入的好友分组列表
必定从顶部显示**（SAME 滚到底 → 点 CROSS，CROSS 从顶部；CROSS 滚到底 → 点 SAME，SAME 从
顶部）。

在此之前 D017 标准（非怠惰）路径每个 PASS 前调 `_reset_utilize_friend_list(group)`，其历史
实现（`9ef9e7a6` "优化蹭卡切换区服" 定型，byte-identical 存在于 HEAD，早于 D017）是：
`switch_friend_list(目标)` → `self.swipe(self.S_U_END, interval=3)`（把整份好友卡列表滚到
底部，触发全加载）→ `switch_friend_list(另一个)` → `switch_friend_list(目标)`（切走再切回
= "刷新到头部"）。用户在 Level C 观察到"进列表先把整列表拽到底、再切同区/跨区"就是这个
`S_U_END` + 双切。

既然实际单次切换就回顶，`_reset_utilize_friend_list` 的"滚到底 + away/back 双切"在 D017
TOP→BOTTOM PASS 模型下是冗余的历史初始化。

### 改动（仅 `tasks/KekkaiUtilize/script_task.py`）

1. `_run_search()`：`self._reset_utilize_friend_list(search_pass.friend_group)` →
   `self.switch_friend_list(search_pass.friend_group)`。docstring 说明依据（相邻 PASS 分组
   一定不同 + 实际切换自动回顶 + 首 PASS 已在目标分组则 `switch_friend_list` 检测选中态
   直接返回 0 click）。
2. `_build_search_passes()` docstring：把"每个 PASS 之前都会 `_reset_utilize_friend_list`
   切回顶部"改为"相邻 PASS 的 `friend_group` 一定不同（契约，测试锁）；每个 PASS 前只
   `switch_friend_list(该分组)` 一次"。
3. `_reset_utilize_friend_list()` docstring：标注 `[legacy / 仅怠惰模式]`，说明标准路径
   不再调用、仅 `_run_lazy_utilize` 在用、不要在标准路径重新引入。**函数体一字未改。**

### 未改

- `_reset_utilize_friend_list` 函数体（`S_U_END` 滚到底 + 切区双切）—— 怠惰路径
  (`_run_lazy_utilize` line 740) 仍调用，怠惰模式行为本轮不动。
- `S_U_END` 资产定义（`assets.py:183`）—— 怠惰路径仍引用，不删。
- `switch_friend_list` 本体（20s 超时 + `raise GamePageUnknownError` + `while 1` 轮询点击）。
- K1 `_perform_search_swipe` / `SWIPE_DISTANCE=416` / 起点安全区 / `sleep(2)` /
  `click_record_clear`。
- D017 全部业务契约：PASS 顺序 / stars / `taiko·fish_reward_threshold` / `lower_reward_tier`
  一次降档 / `PassResult` / `FINAL_USE_LAST` / `I_U_EMPTY_CARD` 判底 / `SEARCH_MAX_SWIPES=20`
  / `SEARCH_PASS_TIMEOUT=120` / `check_card_num` OCR / 怠惰搜索逻辑 / TouchSwipeModel。
- `run_utilize` 的 `except GamePageUnknownError` 兜底（现在每 PASS 只 1 次 `switch_friend_list`
  可能抛，比原来 3 次少，失败面更小）。

### consumer 归零核对

- 标准路径 `_run_search` 对 `_reset_utilize_friend_list` 的**调用** = 0（docstring 里仍提到
  函数名，用于说明"不再调用"，无实际调用）。
- 标准路径 `S_U_END` consumer = 0（`grep S_U_END tasks/KekkaiUtilize/`：`assets.py` 定义 +
  `script_task.py` 内 2 处均在 `_reset_utilize_friend_list` 体内，只经怠惰路径可达）。
- `_reset_utilize_friend_list` consumer = `_run_lazy_utilize` line 740（唯一）。
- lazy 路径完全不变。

### 首次进入实际调用序列（标准，优先同区默认）

```
goto_page(page_guild_realm_utilize) 成功
  → run_utilize(SAME) → _run_search(SAME)
  → _build_search_passes(SAME)  [纯计算]
  → PASS1 (same,{6},high):
       switch_friend_list(SAME)   [已在同区 → 0 tab click；不在 → 只点同区 tab 1 次]
       _run_search_pass(PASS1):  screenshot → find_everyone   ← FIRST_CANDIDATE_SCAN
                                 (此前：0 次列表 swipe、0 次 away/back toggle)
  → PASS2 (cross,{6},high): switch_friend_list(CROSS)  [点跨区 1 次，游戏自动回顶] → 扫描
  → PASS3 (same,{5,6},lower,final): switch_friend_list(SAME) [点同区 1 次，自动回顶] → 扫描
```

SAME→CROSS→SAME / CROSS→SAME→CROSS→SAME：每个 PASS 前只 `switch_friend_list(PASS.group)`，
不存在 `_reset_utilize_friend_list` / `S_U_END` / away-back。

### 测试

`tests/test_kekkai_utilize_state.py` 53 → 62：

- 新增 `RunSearchGroupSwitchOnlyTest`（9 用例）：相邻 PASS 分组必不同（`_build_search_passes`
  SAME/CROSS 两种）；SAME→CROSS→SAME 每 PASS 只 `switch_friend_list` 无 `_reset` 无 `swipe`；
  CROSS→SAME→CROSS→SAME 同上；FIRST_CANDIDATE_SCAN 前调用序 = `[('switch',SAME),('scan',SAME)]`；
  `_run_search` 源码含 `switch_friend_list(search_pass.friend_group)`、无 `S_U_END`、无
  `self._reset_utilize_friend_list(` 调用；`switch_friend_list` 已在目标分组 → 0 `device.click`；
  不在 → 恰 1 次 `device.click`（含 `x` / `control_name`，无 away/back）；`_run_search_pass`
  仍含 `self._perform_search_swipe()`；lazy 仍调 `_reset_utilize_friend_list` 且其体内仍有
  `self.swipe(self.S_U_END, interval=3)`。
- 改 `RunSearchSequenceTest`：`_task` mock `switch_friend_list` 替代 `_reset_utilize_friend_list`；
  `test_first_pass_hit_stops_immediately` / `test_second_pass_hit_skips_lower_phase` 断言从
  `_reset_utilize_friend_list.call_*` 改为 `switch_friend_list.call_*` + 新增
  `_reset_utilize_friend_list.call_count == 0`。

验证顺序：`test_kekkai_utilize_state` `62/62` → `test_kekkai_utilize_threshold` /
`test_kekkai_activation_state` / `test_rule_ocr_float_roi` / `test_touch_swipe_model` /
`test_control_swipe_trajectory` / `test_minitouch_trajectory_executor`（合计 201 OK）→
`toolkit/python.exe -m compileall -q tasks/KekkaiUtilize/script_task.py
tests/test_kekkai_utilize_state.py` OK →
`toolkit/python.exe -m unittest discover -s tests` **`953/953 OK`**（944 → 953，+9）→
`git diff --check -- tasks/KekkaiUtilize/script_task.py` 干净。

### Level C 待复核

进列表后不再"先把整列表拽到底"；当前分组正确时 0 tab click；每个 PASS `switch_friend_list`
一次即从顶部扫描；找卡命中率 / `FINAL_USE_LAST` 不变。列表第一次滑动只发生在
`_run_search_pass` 的 `_perform_search_swipe`（K1）。

### 文档同步

- AI_CONTEXT.md：已更新（§4.41 PASS 序列条 + 新增「PASS 前初始化简化」小节；§7 基线
  `944 → 953` + `test_kekkai_utilize_state` `53 → 62`）。
- DEVELOP_LOG.md：本条。
- ROADMAP.md：已更新（KekkaiUtilize 单向分区 Level C 待验收项 ②「切区回顶」标已确认 + 记录
  简化 + 新增待复核子项）。
- DECISIONS.md：已更新（D017：PASS 前 bullet 改 `switch_friend_list`；「切区是否稳定回顶」
  Level C 项标已确认；新增「PASS 前初始化补记（2026-09-06）」；相关文件行注明
  `_reset_utilize_friend_list` 现 legacy/lazy-only）。**非新 ADR。**
- ARCHITECTURE.md：无需更新（未描述 `_run_search` 每 PASS 初始化 / `_reset_utilize_friend_list`；
  改动在 KekkaiUtilize 任务内部控制流，非分层 / 契约边界；K1 / `swipe_trajectory` 链路不变）。
- TESTING.md：无需更新（未改测试分级 / 验证流程 / 真机要求；「相邻 PASS 分组必不同」是单点
  契约测试，非长期测试原则）。

### Git

分支 `master`，HEAD 仍 `2cdf3a0571b0449748aabef259da5cbd2378536c`。未 commit / push / merge /
reset / clean / stash。本轮改动：`tasks/KekkaiUtilize/script_task.py`（`M`，3 处：`_run_search`
调用点 + 2 处 docstring）；`tests/test_kekkai_utilize_state.py`（此前已是 `M` WIP，本轮再改
`RunSearchSequenceTest` + 新增 `RunSearchGroupSwitchOnlyTest`）；`docs/` 四份（AI_CONTEXT /
DEVELOP_LOG / ROADMAP / DECISIONS）。既有其它 `M` + `??` WIP 未触碰。

## 2026-09-07 - T7-5 Stage 2：剩余点击入口收口（Region 采样 + 私有 random 迁移 + 全项目 inventory）—— PARTIAL

### 背景

T7-5 Stage 1（2026-09-04）把普通 Point Rule（`RuleClick`/`RuleImage`/`RuleGif`/`RuleOcr`/
`RuleLongClick` 的 `coord()`）的默认从 `LEGACY_UNIFORM` 换成 preferred-hotspot 模型
（`ClickSampler.sample_target` → `TargetPreference` → `default_point` / registry → `HABIT`）。
Stage 2 处理仍绕过该默认路径的生产点击。

**结论 PARTIAL**：有安全 ROI 的 Point / Region 入口已统一走 Preferred 模型；无安全 ROI 的
逐条列 `EXACT_COORDINATE_BLOCKED`（不凭空造 ROI）。

### 改动（生产代码）

**`module/click_profile.py`**：`DEFAULT_PROFILES` 加 `default_region`（preferred (0.5,0.5)、
core σ 0.17 / medium σ 0.30 / core·medium·tail 0.62·0.30·0.08 / margin 0.05、provisional）——
比 `default_point`（0.10/0.18/0.82·0.16·0.02）宽、仍中心集中；保守起点，不是复活 Settlement
Contract v2。

**`module/click_preference.py`**：
- 加常量 `REGION_FALLBACK_PROFILE = "default_region"`。
- `TARGET_PREFERENCES` 加 3 条 Region 显式条目 `random_default` / `random_save_right` /
  `random_save_bottom` → `CENTER_FALLBACK=(0.5,0.5)` + `default_region`（有独立 profile 需求
  才显式登记；将来 Level C 有数据就地升 EMPIRICAL）。`provenance_counts()` 现
  `{empirical:1, center_fallback:3}`。

**`module/click_sampler.py`**：加 `ClickSampler.sample_region(roi, target_name)`：
`resolve_target_preference` → provenance == CENTER_FALLBACK 时用 `REGION_FALLBACK_PROFILE`
（不是 `default_point`）→ 写 preferred → `ClickSampler.sample(roi, strategy=HABIT, profile=base)`。
**不经 `adapt_point_profile`**（24/96 short_side 适配是给 Point 的，会把大区 / 细长条 SAVE 区
的 σ 误缩）。import 加 `REGION_FALLBACK_PROFILE` / `Provenance`。

**`tasks/Component/GeneralBattle/general_battle.py`**：`_sample_settlement_click` 一行
`x, y = ClickSampler.sample(rule.roi_front)` → `x, y = ClickSampler.sample_region(rule.roi_front,
rule.name)` + docstring + 顶部注释更正。**未改**：`_settlement_click`（节流单次）/
`_advance_generic_result`（连调两次 = 两次独立 `sample_region`）/ `_select_reward_region`
（marker → DEFAULT / `random_int(1,100) <= 80` → SAVE_RIGHT / else SAVE_BOTTOM）/
`_is_generic_result_context`（`I_WIN`/`I_DE_WIN`/`I_FALSE`）/ state machine / `random_click()`。

**`tasks/Component/GeneralInvite/general_invite.py`**：`click_x, click_y =
self._random_point_in_area(select_area)` → `ClickSampler.sample_target(select_area, rule.name)`
（`select_area` = `_find_exact_friend_area` 返回的好友名 OCR bbox，真实安全点击 ROI；
`rule.name` = `O_FRIEND_NAME_1/2`，未登记 → CENTER_FALLBACK + `default_point`）。删私有
`_random_point_in_area` staticmethod + `from module.base.utils.random import random_point_in_roi`
import，加 `from module.click_sampler import ClickSampler`。

**`tasks/RyouToppa/script_task.py`**：`_click_toppa_area` docstring 更正过期注释「区域 2~8 =
`LEGACY_UNIFORM`」→「Stage 1 起 = `sample_target` CENTER_FALLBACK」。**代码未改**（C_AREA_1
仍显式 opt-in，C_AREA_2..8 仍 `self.click(rule)`）。

### direct `device.click` 全量 inventory（44 处，重新扫描）

| status | 数量 | 处理 |
| --- | --- | --- |
| `ALREADY_SAMPLED` | 18 | 坐标已由某 `Rule.coord()` / `list_find` 在上游采样（`base_task.py` ×9、`navigator.py:350`、`Chess/round_state.py:176`、`SwitchSoul:281`、`peacock_kingdom:77`、`general_battle.py:1058`、`DailyTrifles:99`、`RyouToppa:259`、`KekkaiUtilize:417`）——不改 |
| `PREFERRED_POINT`（迁移） | 1 | `GeneralInvite._random_point_in_area` → `sample_target` |
| `PREFERRED_REGION`（迁移） | 1 采样点 / 3 region 身份 | `GeneralBattle._sample_settlement_click` → `sample_region` |
| `EXACT_COORDINATE_BLOCKED` | 24 | 点运行时检测中心（EternitySea/EvoZone/FallenSun/Orochi/WeeklyPurchase/Chess hand card）/ 框外偏移（WantedQuests -40 / rich_man -70 / SixRealms -randint(35,60) / Dokan page -20）/ 硬编码（Login 106,535）/ 计算中心（WeeklyTrifles / QuickLoadout panel 相对）/ 有意固定 fallback（navigator TOWN_FALLBACK / Secret 层卡 `.center`）/ 手搓 OCR 角点（green_mark_name +5/+30）/ slave 设备（Hyakkiyakou ×3）—— 无静态可证安全 ROI，逐条列 `docs/T7_TARGET_PREFERENCE_MAP.md` §3.4，Level C 逐点评估 |

### 生产 LEGACY_UNIFORM / double-sampling

- **生产链上 bare `ClickSampler.sample(roi)`（= `LEGACY_UNIFORM`）消费者 = 0**（`grep
  "ClickSampler.sample(" tasks/` 无匹配，除 `sample_target`/`sample_point`/`sample_region`）。
  `LEGACY_UNIFORM` 策略常量 + `sample()` 方法保留（兼容 / 测试 / `HABIT` rejection fallback /
  mixture tail 成分）。
- **double-sampling consumer = 0**：`sample_target` / `sample_region` / `sample_point` 内部各
  恰 1 次 `ClickSampler.sample`；迁移后的 consumer 无「sample 后加 random offset」/「random 后
  再 sample」；`ALREADY_SAMPLED` 18 处上游采样一次、`Control`/后端不再偏移（D002/D014）。

### RuleLongClick

`RuleLongClick(RuleClick)` **无 `coord` override**，经 `RuleClick.coord` 继承已在 Stage 1
`sample_target` 模型上。长按时长（`duration`）属时间 / 输入模型，与空间模型分离。测试锁
`RuleLongClickTest`（`RuleLongClick.coord is RuleClick.coord` / routes to `sample_target` /
端到端中心偏置 in-bounds）。

### normal_button / I_FIRE

`log/runtime_roi_analysis/` 不存在 —— 无 `runtime_roi_probe` 输出。`I_FIRE` 是 3 个不同 asset
（`RealmRaid` `(982,494,136,63)` / `AreaBoss` `(1109,490,100,73)` / `GeneralInvite`
`(1179,602,81,74)`），ROI 各异、无单一 runtime bbox；manual click cluster_B 只有屏幕归一化
中心、无可靠 runtime ROI-relative 基准。**空间模型已统一**（走 `sample_target` →
`CENTER_FALLBACK` (0.5,0.5) + `default_point`）；**个人 hotspot empirical calibration 属
Level C 待办，不算 Stage 2 迁移未完成，不伪造 empirical 值**。

### 测试

- 新增 `tests/test_t7_5_stage2.py`（20 用例）：`default_region` profile（居中 / 比 Point 宽 /
  仍 core-dominant）；`sample_region`（3 个 Region 均 CENTER_FALLBACK + `default_region` /
  未登记名也用 `default_region` 不用 `default_point` / 恰 1 次 `sample` / **不做 short_side 适配**
  ——细长条 SAVE_BOTTOM 的 effective σ 仍是 base / 源码不含 `adapt_point_profile(` / 大样本中心
  偏置·非均匀·非固定·全在 Safe ROI·不越区 / 均值贴几何中心）；`RuleLongClick`（继承 + routes +
  端到端）；`GeneralInvite` 迁移（私有 helper 删 / `sample_target(select_area, rule.name)` 一次 /
  sample→click 之间无 randint/random）；double-sampling 审计（`sample_target`/`sample_region`
  各 1 次 / `_sample_settlement_click` 恰 1 次 `sample_region` 无 `random_int`）。
- 改 `tests/test_general_battle_settlement.py`：`SamplingTest` 3 用例
  （`..._uses_region_model_and_keeps_name` / `..._forwards_sampler_coords` 改查位置参数 +
  `strategy=habit` / `..._center_biased_inside_each_region` 大样本中心偏置 + 全在自身 region）
  + `RegressionBoundaryTest.test_settlement_click_path_is_region_model_not_point_model`。
  计数不变（54）。
- 改 `tests/test_t7_5_preferred_hotspot.py::test_registry_only_contains_evidence_backed_or_region_entries`
  （允许 CENTER_FALLBACK 的 Region 兜底条目：必须 `(0.5,0.5)` + `default_region` + `note`）。

验证顺序：`test_t7_5_stage2` `20/20` → `test_general_battle_settlement` `54/54` →
`test_t7_5_preferred_hotspot` `22/22` → `test_click_profile` / `test_click_sampler` /
`test_rule_ocr_float_roi` / `test_kekkai_utilize_state` / `test_ryoutoppa_c_area_1_point_opt_in` /
`test_behavior_trace` 全绿 → `compileall -q <改动>` OK →
`toolkit/python.exe -m unittest discover -s tests` **`973/973 OK`**（953 → 973，+20）→
`git diff --check`（`general_battle.py` / `general_invite.py` / `RyouToppa/script_task.py`）干净
（仓库既有 `assets.py` 空白告警是历史 WIP，未触碰）。

### Level C 待验收

GeneralBattle 三个 SAVE 区真实散点（中心偏置、不越区、非固定像素、spread 合理）；
`normal_button` / `I_FIRE` 的 `runtime_roi_probe` + manual click 标定 → 升 EMPIRICAL；
24 个 `EXACT_COORDINATE_BLOCKED` 里个别「可能有安全 ROI」的（`Secret` 层卡 `.center`、
`green_mark_name` OCR 角点、`Dokan` bounty bbox、`QuickLoadout` panel 相对）逐个评估。

### 文档同步

- AI_CONTEXT.md：已更新（新增 §4.45 Stage 2；§7 基线 `953 → 973` + 列 `test_t7_5_stage2.py` +
  `test_general_battle_settlement` 备注 Stage 2）。
- DEVELOP_LOG.md：本条。
- ROADMAP.md：已更新（T7-5 行加 Stage 2 PARTIAL 摘要；「T7-5 Stage 2」待办项 ② 完成、① 部分
  完成，剩余拆成「empirical calibration（Level C）」+「剩余 EXACT_COORDINATE_BLOCKED 逐点评估」）。
- ARCHITECTURE.md：已更新（分层图 ClickSampler 段加 `sample_region`；§通用结算推进 + `_settlement_click`
  调用链改 `sample_region`；能力表「点击落点分布」行加 Stage 2 + Region 兜底条目 + bare sample 消费者 0）。
- DECISIONS.md：已更新（D014 T7-5 段：「Region 点击」bullet 重写为「业务选 region + region 内
  preferred 采样两件事分开」+ `sample_region` / `default_region` / `REGION_FALLBACK_PROFILE`；
  新增「Stage 2 状态（2026-09-07）」+「Exact coordinate 例外门槛」；相关文件行补 Stage 2 文件）。
  **非新 ADR。**
- TESTING.md：已更新（§5 加 T7-5 Stage 2 长期契约：一次点击一次采样 / Region ≠ Point ≠ 整区均匀 /
  无安全 ROI 的 exact 保留合法但须进 inventory / empirical calibration ≠ 代码迁移）。
- 专题 `docs/T7_TARGET_PREFERENCE_MAP.md` 重写为「全项目点击空间模型覆盖 Inventory」（三类点击 /
  44 处 direct click 分类表 / LEGACY_UNIFORM 剩余 / double-sampling 审计 / registry 现状 /
  normal_button·I_FIRE / status 统计）。

### Git

分支 `master`，HEAD 仍 `2cdf3a0571b0449748aabef259da5cbd2378536c`。未 commit / push / merge /
reset / clean / stash。本轮改动：`tasks/Component/GeneralBattle/general_battle.py` /
`tasks/Component/GeneralInvite/general_invite.py` / `tasks/RyouToppa/script_task.py`（`M`）；
`module/click_profile.py` / `module/click_preference.py` / `module/click_sampler.py`（此前已是
`??` WIP，本轮再改）；新增 `tests/test_t7_5_stage2.py`（`??`）；改
`tests/test_general_battle_settlement.py` / `tests/test_t7_5_preferred_hotspot.py`（`??` WIP）；
`docs/` 六份 + `T7_TARGET_PREFERENCE_MAP.md`。既有其它 `M` + `??` WIP（T7-5 Stage 1、Kekkai
D017 简化、K1、TouchSwipeModel、RuleOcr float ROI、GeneralBattle V3、FrameWait、BehaviorTrace/OASX）
未触碰。

## 2026-09-07 - T7-5 Stage 2 状态重新校对（按已明确完成标准；无代码改动）

用户要求按 Stage 2 之前已明确的完成标准重新校对状态，前提：**Stage 2 完成 = 「所有具有
*可证明安全 ROI* 的生产点击入口完成统一空间模型迁移」，不是「所有 `device.click` 都重写」**；
① 无法证明安全 ROI 的 exact coordinate 允许合法保留（前提：全进 inventory + 写明 blocker）；
② empirical hotspot calibration ≠ 代码 / 架构迁移，`CENTER_FALLBACK` 已进统一 Preferred 模型
即视为该 target 空间模型已统一。

### 重新核对范围

除 44 处 `device.click` 外，本轮补查全部 `.center` / `.front_center()` / 就地 `RuleClick(...)`
消费点：

- `Chess/hand_operations.py:349` `inspect_rule`、`SwitchAccount/login_account.py:109` `tmpClick`、
  `KekkaiActivation/script_task.py:280` `target` —— 均经 `self.click(...)` / `ui_click_until_disappear`
  → `RuleClick.coord()` = `sample_target` → **ALREADY_SAMPLED**（Stage 1 已覆盖）。
- `Chess/hand_operations.py:2036 / 2149` `_rule_center(RuleClick(HAND_AREA))` → 用作
  `Press_and_Drag(p2=hand_target)` → **NON_CLICK**（拖拽端点，§24 不属点击模型）。
- `AreaBoss:194` / `Exploration/base.py:225` / `RealmRaid:291` / `SixRealms/common.py:27` /
  `peacock_kingdom:28` 的 `front_center()` → swipe 起点 / 搜索 ROI 几何 / point-in-rect 判定 /
  x 位置分类 —— **非点击**。

### 发现 1 处早先误分

**`tasks/Secret/script_task.py:270`**：代码里就地构造 `click_roi = (card_x+12, card_y+8, 216,
LAYER_CARD_HEIGHT-16)`（作者注释「点击卡片左侧内容区，避开右侧状态文字」）+
`RuleClick(roi_front=click_roi, roi_back=click_roi, name='secret_layer_..._card')`，然后
`click_x, click_y = click_rule.center` → `self.device.click(x, y, ...)` ×2（`for click_index in
range(1, 3)`）。这是**已构造好的可证明安全点击 ROI**（标准与本轮迁移的
`GeneralInvite._find_exact_friend_area` 一致），却用 `.center` 精确中心**绕过 `.coord()`**。
上一轮 inventory 误把它归入 `EXACT_COORDINATE_BLOCKED`，理由（"已经是 .center 语义、迁会打散、
需 Level C"）站不住 —— 把精确中心换成安全 ROI 内的 preferred 偏置采样正是 Stage 2 目标。

应迁移为 `for click_index in range(1, 3): x, y = click_rule.coord(); self.device.click(x, y, ...)`
（两次独立 `sample_target` 采样，业务「连续两次点击」需求不变）。**清晰静态迁移、不需 Level C。**

### 结论

- Stage 2 = **PARTIAL**（架构迁移实质完成，仅差 `Secret` 那 1 个 `RuleClick`）。用户的 IMPLEMENTED
  判定条件是「重新核对后没有发现『明确已有安全 ROI 但本轮未迁移』的 consumer」—— 核对发现了 1 个，
  故**本轮不翻 IMPLEMENTED**；用户本轮又要求「不改任何生产代码」，故不在本轮迁移 `Secret`。
- 用户对另外两点的重新分类**正确、已采纳**：
  - `EXACT_COORDINATE_BLOCKED`（23，去掉 `Secret` 后）—— 无静态可证安全 ROI，逐条列文件行号原因，
    归**后续独立任务 B（Exact Coordinate ROI Discovery，Level C / 新证据后才迁）**，非 Stage 2 blocker。
  - `I_FIRE` / `normal_button` / Region empirical —— 归**后续独立任务 A（Empirical Hotspot
    Calibration，Level C）**，非 Stage 2 blocker。
- **收尾**：迁移 `Secret/script_task.py:270` `click_rule.center` → `.coord()` + 补 1 条测试 →
  Stage 2 → IMPLEMENTED。

### 文档同步

- AI_CONTEXT.md：已更新（§4.45 状态段重写：PARTIAL 理由收窄为 `Secret` 1 处 + 采纳 A/B 后续
  分类；inventory bullet / Level C bullet 同步）。
- DEVELOP_LOG.md：本条。
- ROADMAP.md：已更新（T7-5 行：`EXACT_COORDINATE_BLOCKED 24 → PENDING_MIGRATION 1 + BLOCKED 23`，
  「Stage 2 收尾（不需 Level C）= 迁 `Secret`」，A/B 后续任务分类，明确「非 Stage 2 blocker」）。
- DECISIONS.md：已更新（D014 T7-5 段：新增「Stage 2 完成标准（明确）」+「Stage 2 状态
  （2026-09-07 重新校对）」重写，`PENDING_MIGRATION` / 后续任务 A/B）。**非新 ADR。**
- ARCHITECTURE.md：无需更新（`sample_region` / `default_region` / GeneralBattle 调用链等技术事实
  未变；本轮只改状态语义）。
- TESTING.md：无需更新（测试分级 / 长期契约未变）。
- `docs/T7_TARGET_PREFERENCE_MAP.md`：已更新（§3.4 24→23、新增 §3.5 `PENDING_MIGRATION`、§8 状态表
  + 覆盖声明重写为「PARTIAL，仅差 `Secret`」+ 后续任务 A/B）。

### Git

分支 `master`，HEAD 仍 `2cdf3a0571b0449748aabef259da5cbd2378536c`。**本轮零代码 / 零测试改动**，
仅 `docs/` 五份状态语义校正（AI_CONTEXT / DEVELOP_LOG / ROADMAP / DECISIONS /
T7_TARGET_PREFERENCE_MAP）。未 commit / push / merge / reset / clean / stash。

## 2026-09-07 - T7-5 Stage 2 收口：Secret 关卡卡片点击迁移 → Stage 2 IMPLEMENTED

### 背景

前一轮重新校对发现 Stage 2 唯一剩余「有可证明安全 ROI 但未迁移」的 consumer：
`tasks/Secret/script_task.py` 的 `find_battle` 关卡卡片点击 —— 就地构造安全 ROI
`click_roi = (card_x+12, card_y+8, 216, LAYER_CARD_HEIGHT-16)`（作者注释「点击卡片左侧内容区，
避开右侧状态文字」）+ `RuleClick(roi_front=click_roi, ...)`，却用 `click_x, click_y =
click_rule.center`（几何中心）绕过 `.coord()`，然后 `for click_index in range(1,3):
device.click(同一坐标)` 连点两次。

### 改动（仅 `tasks/Secret/script_task.py`，`find_battle` 内约 3 行）

```
-            click_x, click_y = click_rule.center
-            for click_index in range(1, 3):
+            for click_index in range(1, 3):
+                click_x, click_y = click_rule.coord()
                 self.device.click(x=click_x, y=click_y, control_name=(f'SECRET_LAYER_{...}_SELECT_{click_index}'))
                 time.sleep(0.4)
```

即：把 `coord()` 移进循环，每次迭代独立取一次坐标 → 每次经 `RuleClick.coord()` →
`ClickSampler.sample_target(click_roi, 'secret_layer_{n}_card')`（未标定 → resolver fallback：
`CENTER_FALLBACK=(0.5,0.5)` + `default_point` + `adapt_point_profile` + HABIT）→ `device.click`。
`range(1,3)` 跑两次 → **两次点击 = 两次独立 `coord()` / `sample_target` 采样**（不再复用同一
`(x,y)`）。

### 未改（§8）

`click_roi` 几何（`card_x+12` / `card_y+8` / `216` / `LAYER_CARD_HEIGHT-16`）、`card_x/card_y`
计算、右侧状态文字避让、循环次数（2）、点击间隔（`time.sleep(0.4)`）、`control_name`
（`SECRET_LAYER_{layer}_SELECT_{click_index}`，BehaviorTrace target 不变）、层数识别 / 卡片
检测 / 状态 OCR / 页面判断 / 失败恢复 / 其它任务行为。**只改「每次点击坐标从哪里来」：
`.center` → `.coord()`。** 未新增 Secret 专属 preferred / profile / 经验坐标 / 随机 offset。

### §9 修改后全局 audit（重新搜 `.center` / `.front_center()` / `RuleClick(` / `device.click(` / `ClickSampler.sample(`）

- `.center`：`Secret` 已无；其余 6 处 `.front_center()`（`AreaBoss:194` swipe 起点 /
  `Exploration/base.py:225` 搜索 ROI 几何 / `RealmRaid:291` point-in-rect 判定 /
  `SixRealms/common.py:27`·`peacock_kingdom:28` x 位置分类 / `SixRealms/common.py:153`
  `- randint(35,60)` 框外偏移点）**分类不变**（NON_CLICK / EXACT_COORDINATE_BLOCKED）。
- 就地 `RuleClick(...)`：`Chess/hand_operations.py:349`（→ `self.click()` → `.coord()`，
  ALREADY_SAMPLED）/ `Chess:2036`·`2149`（`_rule_center(RuleClick(HAND_AREA))` → `Press_and_Drag`
  `p2`，NON_CLICK）/ `SwitchAccount:109`·`KekkaiActivation:280`（→ `self.click()` / `ui_click_*`
  → `.coord()`，ALREADY_SAMPLED）—— **前一轮分类保持**。
- 生产 bare `ClickSampler.sample(` 消费者 = **0**（`module/click_sampler.py` 内 3 处是
  `sample_point`/`sample_target`/`sample_region` 的 `strategy=STRATEGY_HABIT` 内部调用，非
  `LEGACY_UNIFORM`；`click_profile.py:12` 是 docstring）。
- **`PENDING_MIGRATION`（有可证明安全 ROI 但未迁移）= 0。**

### Stage 2 完成标准逐项核对

| 标准 | 结果 |
| --- | --- |
| safe ROI `PENDING_MIGRATION` | **0** |
| production bare `ClickSampler.sample()` | **0** |
| whole-ROI Uniform production Point / Region | **0** |
| double sampling | **0** |
| Exact Coordinate 只剩真正无安全 ROI 的 | **23**（逐条列文件 / 行号 / 原因，`T7_TARGET_PREFERENCE_MAP.md` §3.4）→ 后续任务 B |
| empirical calibration 仅作 follow-up | 后续任务 A（`I_FIRE`/`normal_button`/Region → EMPIRICAL），非 blocker |
| full regression | **977/977 OK** |

→ **T7-5 Stage 2：PARTIAL → IMPLEMENTED。**

### 测试

`tests/test_t7_5_stage2.py` `20 → 24`：新增 `SecretLayerCardMigrationTest`（4）：
- `test_find_battle_click_uses_coord_inside_loop_not_center`：`inspect.getsource(ScriptTask.find_battle)`
  scoped 契约 —— 无 `click_rule.center`；`click_rule.coord()` 恰 1 处且位于 `for click_index in
  range(1, 3):` 之后、对应 `self.device.click(` 之前；`click_roi` 几何字面量原样保留。
- `test_constructed_ruleclick_routes_to_sample_target`：构造同形 `RuleClick`，patch
  `ClickSampler.sample_target` → `.coord()` 调用它一次，参数 `(roi, name)`。
- `test_two_clicks_use_two_independent_coord_samples`：`ScriptTask.__new__` + 最小 mock
  （`appear`/`match_layer`/`layer_title_ocr`/`device.image.shape`，patch `RuleOcr`→'未通关'、
  `RuleClick`→`coord.side_effect=[(11,22),(33,44)]`），驱动真实 `find_battle` →
  `ret==1` / `coord` 调 2 次 / `device.click` 调 2 次 / `call_args_list` 逐一 `(11,22)`、`(33,44)` /
  `len(set(xy))==2`。
- `test_secret_click_roi_geometry_unchanged`：`LAYER_CARD_HEIGHT=121` / `LAYER_CARD_LEFT=194` /
  `LAYER_STATUS_OFFSET=(240,40,100,50)`。

验证顺序：`test_t7_5_stage2` `24/24` → `test_click_sampler` / `test_t7_5_preferred_hotspot` /
`test_general_battle_settlement` / `test_click_profile`（合计 206 OK）→
`compileall -q tasks/Secret/script_task.py tests/test_t7_5_stage2.py` OK →
`toolkit/python.exe -m unittest discover -s tests` **`977/977 OK`**（973 → 977，+4）→
`git diff --check -- tasks/Secret/script_task.py` 干净。

### 文档同步

- AI_CONTEXT.md：已更新（§4.45 状态 PARTIAL → IMPLEMENTED，加 `Secret` 迁移；inventory bullet
  `PREFERRED_POINT 迁 2` / `PENDING_MIGRATION = 0`；测试 bullet `20 → 24`；§7 基线 `973 → 977` +
  `test_t7_5_stage2` `24/24`；后续任务 A/B 明确非 blocker）。
- DEVELOP_LOG.md：本条。
- ROADMAP.md：已更新（T7-5 行 Stage 2 PARTIAL → IMPLEMENTED；`Secret` 收尾项标已完成；后续
  任务 A/B 明确「Level C，非 Stage 2 blocker」）。
- DECISIONS.md：已更新（D014 T7-5 段「Stage 2 状态」PARTIAL → IMPLEMENTED，加 `Secret` 迁移、
  `PREFERRED_POINT 迁 2` / `PENDING_MIGRATION = 0`；相关文件行加 `tasks/Secret/script_task.py`）。
  **非新 ADR。**
- T7_TARGET_PREFERENCE_MAP.md：已更新（§3.5 `PENDING_MIGRATION` → `PREFERRED_POINT`（`Secret`
  旧链/新链）；§8 状态表 `PREFERRED_POINT direct 2` / `PENDING_MIGRATION 0`；覆盖声明 PARTIAL →
  IMPLEMENTED）。
- ARCHITECTURE.md：无需更新（`sample_target` 链、`sample_region`、`default_region` 等技术架构
  未变；`Secret` 只是把一个 consumer 从 `.center` 接进既有 `RuleClick.coord()` 链）。
- TESTING.md：无需更新（测试分级 / 长期契约未变）。

### Git

分支 `master`，HEAD 仍 `2cdf3a0571b0449748aabef259da5cbd2378536c`。未 commit / push / merge /
reset / clean / stash。本轮改动：`tasks/Secret/script_task.py`（`M`，`find_battle` 内 `.center`
→ `.coord()` 移进循环 + 注释）；`tests/test_t7_5_stage2.py`（`??` WIP，+4 用例）；`docs/` 五份
（AI_CONTEXT / DEVELOP_LOG / ROADMAP / DECISIONS / T7_TARGET_PREFERENCE_MAP）。既有其它
`M` + `??` WIP 未触碰。

## 2026-09-07 - KekkaiUtilize K2：标准 PASS minitouch 路径的 commanded 位移 416px → 随机 212~265px

### 背景（Level C 几何）

K1 已把标准非 lazy 搜索的下划迁到 `_perform_search_swipe()` → `TouchSwipeModel` →
`swipe_trajectory` → minitouch，但业务层仍固定 `SWIPE_DISTANCE = 416`。Level C 真机
1280×720 截图确认：好友结界卡列表一屏约 4 格，四行卡片中心约 y≈220 / 326 / 432 / 538，
`row_pitch ≈ 106px`。旧 416px ≈ 3.9 个 row_pitch、接近整屏一次滑 4 格；游戏列表还有明显惯性
（实际内容滚动 > commanded finger 位移）→ 严重跨项漏卡风险。

### 改动（仅 `tasks/KekkaiUtilize/script_task.py`）

1. 类常量：新增 `KEKKAI_ROW_PITCH_PX = 106`、`SWIPE_DISTANCE_RANGE = (212, 265)`
   （≈2.0~2.5 个 row_pitch）。`SWIPE_DISTANCE = 416` 保留（怠惰 + 非 minitouch 回退用）。
   删掉旧注释「位移固定，保证每次滚动恰好推进一屏」。
2. `_perform_search_swipe()` minitouch 分支：
   ```
   start_x = random_int(*self.SWIPE_START_X_RANGE)
   start_y = random_int(*self.SWIPE_START_Y_RANGE)
   distance = random_int(*self.SWIPE_DISTANCE_RANGE)   # K2：每次调用独立采样
   start = (start_x, start_y)
   end = (start_x, start_y - distance)
   trajectory = TouchSwipeModel().generate(start, end)
   ```
   log 行的 `distance=%d` 参数从 `self.SWIPE_DISTANCE` 改成 `distance`。docstring 更新。

### 职责边界（§二）

「滑多远」在 Kekkai 业务层（本方法）；`TouchSwipeModel` 只负责「怎么滑」（给定 start/end →
平滑轨迹）。**`TouchSwipeModel` / `swipe_trajectory` / minitouch trajectory executor 一行未改**，
不让模型自己决定距离。D018 上方「不写进本 ADR（可 Level C 调整）」已列 `SWIPE_DISTANCE` 具体
数值 —— K2 属该范畴，非新长期决策（D018 加「K2 补记」，非新 ADR）。

### 未改

- 起点安全区 `SWIPE_START_X_RANGE=(340,600)` / `SWIPE_START_Y_RANGE=(500,565)`；X 纯纵向
  （`end_x == start_x`）；`TouchSwipeModel().generate(start,end)` 零参构造；曲率 / 时间模型 /
  tail 参数；`swipe_trajectory` 恰一次；`control_name='KEKKAI_UTILIZE_SWIPE'`；
  `click_record_clear()`；`time.sleep(2)`。
- **怠惰路径**（`_select_lazy_resource_card` → `perform_swipe_action` → `swipe_adb`）
  **仍固定 `SWIPE_DISTANCE=416`**；**非 minitouch 回退**（`_perform_search_swipe` →
  `perform_swipe_action`）**也仍 416**（§5：架构上让 fallback 用同一 sampled distance 需先
  报告再决定，本轮不动）。全模块 `swipe_adb` 调用点仍恰 1 处。
- D017 业务契约：PASS 顺序 / stars / `taiko·fish_reward_threshold` / `lower_reward_tier` /
  `PassResult` / `FINAL_USE_LAST` / `I_U_EMPTY_CARD` / `SEARCH_MAX_SWIPES=20` /
  `SEARCH_PASS_TIMEOUT=120` / `switch_friend_list` PASS 前初始化（不恢复 `S_U_END` / legacy
  reset / away-back）。
- BehaviorTrace：一次 swipe = 一个 ACTION（`swipe_trajectory` 端点级），随机 end 自然进 trace；
  不为每个 MOVE 加 ACTION；OASX swipe trajectory 可视化另开任务。
- 未接 FrameWait / changed / stable / actual_scroll_dy / candidate projection / 帧间去重 /
  scroll_gain（K3/K4）。

### 契约（§七）

K2 控制的是 **commanded finger 位移** ≈ 2.0~2.5 格；**不保证** actual content scroll 严格
= 2.0~2.5 格（Level C 已观察到游戏列表惯性）。「finger distance ≠ content displacement」的
测量（记 `commanded distance` vs 实际移动格数 → `scroll_gain = actual / finger`）+ 帧间投影
+ 重叠去重 + 只处理新进入区域 = **K4**，本轮不做惯性补偿。

### 测试

`tests/test_kekkai_utilize_state.py` `62 → 69`：
- 新增 `PerformSearchSwipeK2Test`（7）：`SWIPE_DISTANCE_RANGE=(212,265)` 且 lo/hi ≈ 2.0/2.5 ×
  `KEKKAI_ROW_PITCH_PX=106`、明显 < 416；连续三次 swipe distance 212/240/265 → `end_y =
  start_y - 该值`、`ri.call_args_list == [call(340,600), call(500,565), call(212,265)]`；
  大样本 400 次真随机 → 位移恒在 `[212,265]`、>10 个不同值（每次独立采样）、不出现 416；
  起点范围不变；`swipe_trajectory` 恰一次 + `control_name` + `click_record_clear` + `sleep(2)`
  + 轨迹原样传入；怠惰（`perform_swipe_action` src 仍 `safe_pos_y - self.SWIPE_DISTANCE`、
  `SWIPE_DISTANCE==416`）+ 非 minitouch 回退（不构造 `TouchSwipeModel`、不采样 distance）仍 416；
  D017（`_run_search` 仍 `switch_friend_list`、无 `S_U_END` / `_reset_utilize_friend_list`）+
  TouchSwipeModel（`TouchSwipeModel().generate(start, end)` 零参、无 `TouchSwipeParams`）未动。
- 改 `PerformSearchSwipeK1Test`（3）：`random_int` side_effect 加第 3 个值（distance）、
  `ri.call_args_list` 加 `call(*SWIPE_DISTANCE_RANGE)`、`gen_end`/`gen_start[1]-gen_end[1]`
  断言改成随机采样值、`test_k1_helper_...` 的 `assertIn('self.SWIPE_DISTANCE', src)` 改成
  `assertIn('random_int(*self.SWIPE_DISTANCE_RANGE)', src)` + `assertNotIn('start_y -
  self.SWIPE_DISTANCE)', src)`。

验证顺序：`test_kekkai_utilize_state` `69/69` → `test_kekkai_utilize_threshold` /
`test_touch_swipe_model` `56` / `test_control_swipe_trajectory` `9` /
`test_minitouch_trajectory_executor` `15`（合计 172 OK，K1/K2 executor / TouchSwipeModel
全绿）→ `compileall -q tasks/KekkaiUtilize/script_task.py tests/test_kekkai_utilize_state.py`
OK → `toolkit/python.exe -m unittest discover -s tests` **`984/984 OK`**（977 → 984，+7）→
`git diff --check -- tasks/KekkaiUtilize/script_task.py` 干净。

### Level C 待验收（§十二）

1. 每次 swipe 视觉距离是否有轻微变化；
2. commanded 212~265px 后实际好友列表通常移动几格；
3. 是否仍出现一次跳过 4 张以上；
4. 相邻两屏是否保留明显重复卡片（理想 ≥ 1.5~2 格重叠，如 A B C D → C D E F 或 B/C D E F）；
5. 记录 `commanded distance` vs 实际内容移动格数 → 供 K4 估 `scroll_gain`。
K1 的「minitouch 连续扫描是否识别为滑动 / 尾段 fling / `find_everyone`·OCR·`I_U_EMPTY_CARD`·
final fallback 不受影响」在同一次真机一并核。

### 后续阶段（§十三）

K1 ✅（TouchSwipeModel 接入）；K2 ✅（本轮，随机 2~2.5 格小步）；K3（swipe 后 changed +
stable，FrameWait）；K4（actual_scroll_dy + `scroll_gain` 补偿 + 帧间投影 + 重叠去重 +
只处理新进入区域）。不混阶段。

### 文档同步

- AI_CONTEXT.md：已更新（§4.41 新增「K2（2026-09-07）」子块；「未改」条 `SWIPE_DISTANCE=416`
  加 K2 前向说明；§7 基线 `977 → 984` + `test_kekkai_utilize_state` `62 → 69`）。
- DEVELOP_LOG.md：本条。
- ROADMAP.md：已更新（「已完成」表新增 K2 行；Level C 待验收项 ⑤ / TouchSwipeModel 接入项的
  「K2 另开任务」标已完成，K4 补「`scroll_gain` 补偿」）。
- DECISIONS.md：已更新（D018 加「K2 补记（2026-09-07）」，非新 ADR，明确「只改滑多远、
  `TouchSwipeModel` 未改、`SWIPE_DISTANCE` 具体值本就可 Level C 调整」；D017 PASS 前初始化补记
  的「未改 `SWIPE_DISTANCE=416`」加 K2 前向说明；D018 相关文件行补 `script_task.py` K2 /
  `PerformSearchSwipeK2Test`）。
- ARCHITECTURE.md：已更新（§自定义轨迹滑动 + 能力表「自定义滑动轨迹」行：K1 consumer 描述加
  「K2 起 commanded 位移随机 212~265px、Kekkai 业务层决定、`TouchSwipeModel` 契约不变」——
  只是 consumer 事实澄清，`swipe_trajectory` / `TouchSwipeModel` 分层与契约本身未变）。
- TESTING.md：无需更新（未形成新的长期测试分级 / 契约；K2 的 Level C 观察项记在 ROADMAP /
  §4.41，属一次性验收清单，非长期规则）。

### Git

分支 `master`，HEAD 仍 `2cdf3a0571b0449748aabef259da5cbd2378536c`。未 commit / push / merge /
reset / clean / stash。本轮改动：`tasks/KekkaiUtilize/script_task.py`（`M`，类常量 +
`_perform_search_swipe` minitouch 分支 3 行 + docstring / 注释）；`tests/test_kekkai_utilize_state.py`
（`??` WIP，新增 `PerformSearchSwipeK2Test` 7 + 改 K1 3）；`docs/` 五份（AI_CONTEXT / DEVELOP_LOG /
ROADMAP / DECISIONS / ARCHITECTURE）。既有其它 `M` + `??` WIP 未触碰。


## 2026-09-07 - KekkaiUtilize K3：标准 PASS + minitouch 的 swipe settle 固定 `time.sleep(2)` → FrameWait changed+stable

### 背景

K1 把标准非 lazy 搜索的下划迁到 minitouch trajectory，K2 把 commanded 位移改随机
212~265px，但 swipe 之后仍固定 `time.sleep(2)` 猜页面停稳——列表惯性拖尾比 2 秒长时
会在没停稳时就扫下一屏（错位/漏卡），比 2 秒短时白等。K3 把这段固定等待换成
`module/base/frame_wait.py` 的 `wait_for_changed_and_stable`（该模块此前 D012/§4.18
记「纯能力 + 零生产消费者」——K3 是首个且唯一生产消费者）。

### 改动（仅 `tasks/KekkaiUtilize/script_task.py`）

1. import：`from module.base.frame_wait import wait_for_changed_and_stable`。
2. 类常量（K2 常量之后）：
   - `SWIPE_WAIT_ROI = (525, 155, 620, 610)`（`(x1,y1,x2,y2)`，frame_state 口径；取
     `I_U_*_6` / `I_U_EMPTY_CARD` 的 `roi_back` 包络：x≈530~620 / y≈156~606；排除右侧
     详情栏 / tab / 底部 UI / OCR 数字，避免污染 changed·stable）。
   - `SWIPE_WAIT_CHANGED_THRESHOLD = 0.10` / `SWIPE_WAIT_STABLE_THRESHOLD = 0.02` /
     `SWIPE_WAIT_STABLE_FRAMES = 3` / `SWIPE_WAIT_TIMEOUT = 3.0` —— **provisional 首版，
     注释明确标「需 Level C 调整」**（用 `swipe wait` 日志的 `elapsed` / `diff` 分布回填）。
3. `_perform_search_swipe()` 签名 `-> None` → `-> bool`：
   - 非 minitouch 分支：`self.perform_swipe_action()` 后 `return True`（回退路径固定视为已滑动）。
   - minitouch 分支：`start_x/start_y/distance` 采样**之前**先 `baseline = self.device.screenshot()`
     —— `_run_search_pass` 里 `check_card_num()` 会内部自截，进入 `_perform_search_swipe()`
     时 `self.device.image` 可能是候选卡详情页帧，必须 swipe 前明确重截、不复用。
   - `swipe_trajectory` + `click_record_clear` 后，把 `time.sleep(2)` 换成：
     ```
     wait = wait_for_changed_and_stable(
         baseline, self.device.screenshot,
         roi=self.SWIPE_WAIT_ROI,
         changed_threshold=self.SWIPE_WAIT_CHANGED_THRESHOLD,
         stable_threshold=self.SWIPE_WAIT_STABLE_THRESHOLD,
         stable_frames=self.SWIPE_WAIT_STABLE_FRAMES,
         timeout=self.SWIPE_WAIT_TIMEOUT,
     )
     logger.info('KekkaiUtilize swipe wait: changed=%s stable=%s timed_out=%s frames=%d elapsed=%.2fs diff=%.3f' % (...))
     if not wait.success:
         logger.warning('... 不当作到底（BOTTOM 只认 I_U_EMPTY_CARD），交外层安全中止')
     return wait.success
     ```
4. `_run_search_pass()` 调用点 `self._perform_search_swipe()` →
   ```
   if not self._perform_search_swipe():
       logger.warning('结界卡下划后未观察到有效滚动并稳定（FrameWait 失败），安全中止')
       return PassResult.ABORT, clicked_any
   ```

### 失败语义（§核心）

`wait.success` = `changed and stable and not timed_out`（FrameWait 契约，D012）。
- SUCCESS（相对 baseline 的 card-column 确实 changed，且随后连续 3 帧相邻安静）→ `True`
  → `_run_search_pass` 扫下一屏。
- NO_CHANGE（`changed` 迟迟不出现，timeout）/ CHANGED_BUT_UNSTABLE（`changed` 后一直不
  `stable`，timeout）→ `False` → `_run_search_pass` **立即 `return PassResult.ABORT`**，
  交 `run_utilize` 外层 bounded recovery。
- **`no change ≠ BOTTOM`**：D017 唯一 BOTTOM marker 仍是 `I_U_EMPTY_CARD`；K3 不新增
  「滑不动 → PASS_MISS」隐式到底语义。
- 方法内**一次 swipe → 一次 FrameWait，无内部 retry**（有限 recovery 只在外层）。

### 职责边界

「何时算停稳 / ROI / 阈值 / 失败后做什么」在 Kekkai 业务层；`wait_for_changed_and_stable`
只做「取帧 + 轮询 + 有限 timeout」，`FrameStateDetector` 只做帧差算法——两者**一行未改**。
FrameWait 本层无业务默认，4 个阈值全部由 KekkaiUtilize 显式传。`timeout` 有限正数（3.0s），
无无界循环。settle 方式属「可 Level C 调整」的实现细节，不是新长期决策（D017 加 K3 补记、
D018 加 K3 补记、D012 加 K3 补记，均非新 ADR）。

### 未改

- K1（`TouchSwipeModel().generate(start, end)` 零参 / `swipe_trajectory` 一次 /
  `control_name='KEKKAI_UTILIZE_SWIPE'`）、K2（`random_int(*SWIPE_DISTANCE_RANGE)` 每次
  独立采样 212~265px）、起点安全区 `(340,600)×(500,565)` / X 纯纵向 / 曲率 / 时间模型 /
  tail / `click_record_clear`。
- BehaviorTrace：一次 swipe = 一个 ACTION（`swipe_trajectory` 端点级）；FrameWait 轮询
  只调 `device.screenshot`，不产生额外 ACTION。
- **怠惰路径**（`_select_lazy_resource_card` → `perform_swipe_action` → `swipe_adb`）
  **仍固定 `SWIPE_DISTANCE=416` + `time.sleep(2)`**；**非 minitouch 回退**
  （`_perform_search_swipe` → `perform_swipe_action`）**也仍 416 + `sleep(2)`**，不接 FrameWait。
  全模块 `swipe_adb` 调用点仍恰 1 处。
- D017 业务契约：PASS 顺序 / stars / `taiko·fish_reward_threshold` / `lower_reward_tier` /
  `PassResult` / `FINAL_USE_LAST` / `I_U_EMPTY_CARD` / `SEARCH_MAX_SWIPES=20` /
  `SEARCH_PASS_TIMEOUT=120` / `switch_friend_list` PASS 前初始化（不恢复 `S_U_END` /
  legacy reset / away-back）。
- `time.sleep(self.DETAIL_LOAD_WAIT)`（候选卡详情加载等待）与 `_select_lazy_resource_card`
  的 `time.sleep(2)` 不动——K3 只替换「标准 PASS + minitouch 的 swipe settle」这一处
  固定等待，不机械删全模块所有 sleep。
- K4（actual_scroll_dy + `scroll_gain` 补偿 + 帧间投影 + 重叠去重 + 只处理新进入区域）不做。

### 测试

`tests/test_kekkai_utilize_state.py` `69 → 83`：
- 新增 `PerformSearchSwipeK3Test`（13 用例）：changed&stable → `True` / NO_CHANGE·timeout →
  `False` / CHANGED_BUT_UNSTABLE → `False` / baseline 取 swipe 前（调用顺序 `shot → traj →
  clear → wait`，传给 FrameWait 的 baseline == swipe 前那帧）/ FrameWait 收到
  `SWIPE_WAIT_ROI` + 4 个 provisional 阈值 + 有限 timeout（0 < t ≤ 5）+ provider 是
  `device.screenshot` 本身 / 一次 swipe 一次 FrameWait、失败也不重试 / minitouch 源码无
  `time.sleep(`、有 `wait_for_changed_and_stable(` + `return wait.success` +
  `baseline = self.device.screenshot()` / `_run_search_pass` 把 `False` 映射 `ABORT`（窗口内
  无 `PassResult.PASS_MISS` / `PassResult.FINAL_USE_LAST` / `self.appear(`）/ ROI 是
  card-column（窄条、x1>400、x2<720、宽 < 整屏一半）/ provisional 参数在类里且注释含
  「Level C」/ 怠惰·非 minitouch 回退仍 `time.sleep(2)`、不接 FrameWait、不截 baseline /
  真实 `wait_for_changed_and_stable` 签名冒烟（真 np baseline + changed→stable 序列 → `True`）/
  K1·K2 未被 K3 影响。
- `RunSearchPassTest`：`_task` 的 `t._perform_search_swipe = Mock()` → `Mock(return_value=True)`；
  新增 `test_swipe_wait_failure_maps_to_abort_not_bottom`（`Mock(return_value=False)` +
  `empty_after=None` → `PassResult.ABORT`，一次失败即停、仍先查过 `I_U_EMPTY_CARD`）。
- `UtilizeStructureTest`：`test_no_frame_wait_consumer_in_utilize` →
  `test_frame_wait_consumer_is_only_perform_search_swipe`（正向锁：模块 import 一次、
  `wait = wait_for_changed_and_stable(` 恰一处、只在 `_perform_search_swipe` 里、
  `_run_lazy_utilize`/`_select_lazy_resource_card`/`perform_swipe_action`/`run_utilize`/
  `_run_search` 都不碰、不自己实例化 `FrameStateDetector`）。
- `PerformSearchSwipeK1Test` / `PerformSearchSwipeK2Test`：`_task` 的 `device` 加
  `screenshot=Mock(...)`；minitouch 用例 patch `wait_for_changed_and_stable` 成成功
  namespace；settle 断言从 `['traj','clear','sleep']` / `('sleep',2)` 改成
  `['traj','clear','wait']` / 无 `sleep`；`test_k1_helper_uses_public_random_and_no_fixed_140_pause`
  的 `assertIn('time.sleep(2)', src)` → `assertNotIn` + `assertIn('wait_for_changed_and_stable(')`
  + `assertIn('return wait.success')`；`_perform_search_swipe` docstring 里把
  `` `time.sleep(2)` `` / `` `sleep(2)` `` 改成「2 秒等待」以免 grep 断言误伤。

验证顺序：`test_kekkai_utilize_state` `83/83` → `test_frame_state` / `test_frame_wait` /
`test_touch_swipe_model` / `test_control_swipe_trajectory` / `test_minitouch_trajectory_executor`
合计 `122 OK` → `compileall -q tasks/KekkaiUtilize/script_task.py tests/test_kekkai_utilize_state.py`
OK → `toolkit/python.exe -m unittest discover -s tests` **`998/998 OK`**（984 → 998，+14）→
`git diff --check -- tasks/KekkaiUtilize/script_task.py tests/test_kekkai_utilize_state.py` 干净
（其它 `M` 文件既有 WIP 空白告警不属本轮）。

### Level C 待验收

1. `SWIPE_WAIT_ROI` 是否恰好框住滚动主体（不含惯性回弹之外的 UI）；
2. 4 个阈值是否合适（看 `swipe wait` 日志的 `changed / stable / elapsed / diff` 分布，
   旧固定 2 秒实际通常要多少）；
3. `timeout=3.0` 是否够覆盖惯性拖尾；
4. 正常滚动是否稳定判 `changed&stable`、真卡死是否稳定判失败进 `ABORT`；
5. 是否比旧固定 2 秒更快（整体蹭卡耗时）。
K1 / K2 的真机项在同一次真机一并核。

### 后续阶段

K1 ✅（TouchSwipeModel 接入）；K2 ✅（随机 2~2.5 格小步）；K3 ✅（本轮，swipe 后
FrameWait changed+stable）；K4（actual_scroll_dy + `scroll_gain` 补偿 + 帧间投影 +
重叠去重 + 只处理新进入区域）。不混阶段。

### 文档同步

- AI_CONTEXT.md：已更新（§4.41 新增「K3（2026-09-07）」子块；§4.41「未改」条加 K3 前向说明 +
  K2 子块 settle 措辞改为「由 K3 另行替换」；§4.18 FrameState Wait Layer「零生产消费者」→
  「首个且唯一消费者 = `KekkaiUtilize._perform_search_swipe`」；§7 基线 `984 → 998` +
  `test_kekkai_utilize_state` `69 → 83`）。
- DEVELOP_LOG.md：本条。
- ROADMAP.md：已更新（「已完成」表新增 K3 行；T4-2 FrameState Wait Layer 行「零生产消费者」→
  首个消费者事实；K1/K2 行加 K3 前向说明；Level C 待验收项 ⑤ 与 TouchSwipeModel 接入项的
  「K3 另开任务」标已完成、K4 保留）。
- DECISIONS.md：已更新（D012 加「补记（2026-09-07，KekkaiUtilize K3）」+ 「当前零生产消费者」
  条改成首个消费者、相关文件补 `script_task.py`；D017 加「K3 补记（2026-09-07）」+ 相关文件补
  `frame_wait.py` / `PerformSearchSwipeK3Test`；D018 相关文件行补 K3 补记）。均非新 ADR——
  settle 方式本就是「可 Level C 调整」的实现细节。
- ARCHITECTURE.md：已更新（能力清单「FrameState Wait Layer」+ §2「FrameState Wait Layer」
  的「零生产消费者」→ 唯一消费者 = `KekkaiUtilize._perform_search_swipe` + provisional 阈值；
  §3「自定义轨迹滑动」调用链尾补 `click_record_clear → wait_for_changed_and_stable → 失败 ABORT`）。
- TESTING.md：无需更新（未形成新的长期测试分级 / 契约；K3 的 Level C 观察项记在 ROADMAP /
  §4.41，属一次性验收清单，非长期规则）。

### Git

分支 `master`，HEAD 仍 `2cdf3a0571b0449748aabef259da5cbd2378536c`。未 commit / push / merge /
reset / clean / stash。本轮改动：`tasks/KekkaiUtilize/script_task.py`（`M`，K3 类常量 5 个 +
import 1 行 + `_perform_search_swipe` 签名 / baseline / FrameWait 替 sleep(2) / docstring +
`_run_search_pass` 调用点 ABORT 映射）；`tests/test_kekkai_utilize_state.py`（`??` WIP，新增
`PerformSearchSwipeK3Test` 13 + `RunSearchPassTest` +1 + 改 `UtilizeStructureTest` /
`PerformSearchSwipeK1Test` / `PerformSearchSwipeK2Test` 若干用例）；`docs/` 五份（AI_CONTEXT /
DEVELOP_LOG / ROADMAP / DECISIONS / ARCHITECTURE）。既有其它 `M` + `??` WIP 未触碰。

### 2026-09-07 追加：K3 显式 `poll_interval`（检测采样 pacing）

用户指出上面 K3 的 `wait_for_changed_and_stable(...)` 没显式传 `poll_interval`，吃 FrameWait
全局默认 `0.0`。场景是等 MuMu 好友列表 swipe 后的惯性真正停稳——惯性微滚可能让相邻两帧差异
< `SWIPE_WAIT_STABLE_THRESHOLD`，零间隔高速轮询下连续 `SWIPE_WAIT_STABLE_FRAMES=3` 帧会提前判
stable（甚至连抓到同一渲染帧）。

改动（仅 `tasks/KekkaiUtilize/script_task.py`）：
- 新增类常量 `SWIPE_WAIT_POLL_INTERVAL = 0.15`（秒），注释明确：属**检测采样 pacing**、
  叠在 `device.screenshot` 自带 `_screenshot_interval`（~0.1s）之上，**不是恢复固定 `sleep(2)`**
  （settle 仍以 `changed and stable` 为准、命中即返回）；**provisional，需 Level C 调整**
  （`_screenshot_interval` 已够 → 可回 0；惯性帧仍 alias → 调大）。
- `_perform_search_swipe()` 的 `wait_for_changed_and_stable(...)` 调用加
  `poll_interval=self.SWIPE_WAIT_POLL_INTERVAL`。docstring 的 provisional 说明补上 `poll_interval`。

**不动**：FrameWait 全局默认 `poll_interval=0.0`（`module/base/frame_wait.py` 一行未改）；
`SWIPE_WAIT_ROI` / `SWIPE_WAIT_CHANGED_THRESHOLD` / `SWIPE_WAIT_STABLE_THRESHOLD` /
`SWIPE_WAIT_STABLE_FRAMES` / `SWIPE_WAIT_TIMEOUT`；K1 / K2 / D017 / K4。

测试（`tests/test_kekkai_utilize_state.py`）：
- `PerformSearchSwipeK3Test` +1 `test_frame_wait_gets_explicit_positive_poll_interval`：`kw` 里有
  `poll_interval` 键（显式传，非默认）、值 == `KU.SWIPE_WAIT_POLL_INTERVAL` > 0、< 2.0（远小于旧
  `sleep(2)`）、4 个判定阈值不受影响。
- `test_provisional_params_flagged_level_c` 的常量清单加 `SWIPE_WAIT_POLL_INTERVAL` + 断言类源码
  注释含 `pacing`。
- `test_real_frame_wait_signature_smoke` 加 `patch.object(KU, 'SWIPE_WAIT_POLL_INTERVAL', 0.0)`
  ——冒烟走真实 FrameWait，避免真 `time.sleep(0.15)` 拖慢。

验证：`test_kekkai_utilize_state` `83 → 84`（新增 1）；targeted（`test_kekkai_utilize_state` +
`test_frame_wait` + `test_frame_state`）`129 OK`；`compileall` OK；完整
`toolkit/python.exe -m unittest discover -s tests` **`998 → 999 OK`**；
`git diff --check`（K3 两文件）干净。

文档同步：AI_CONTEXT §4.41 K3 块加「`poll_interval` 显式覆盖」条 + §7 基线 `998 → 999` /
`test_kekkai_utilize_state` `83 → 84`；ROADMAP K3 行「4 个阈值」→「4 个判定阈值 + `poll_interval`」
+ 回归 `984→999` / 用例 `69→84`；DECISIONS D012 K3 补记加「`poll_interval` 显式覆盖全局默认、
全局默认不改」条、D017 K3 补记「ROI / 阈值 / pacing」+「不变」条补 `poll_interval` / FrameWait
全局默认；ARCHITECTURE §2 FrameState Wait Layer 状态行补 `poll_interval`。DEVELOP_LOG 本条。
TESTING 无需更新。

## 2026-09-07 - BehaviorTrace Swipe Trajectory Backend（可观测性：swipe 轨迹后台记录 + 统计查询，additive extension）

### 范围

独立可观测性任务。**只做 Backend**（`OnmyojiAutoScript-easy-install`），**OASX 前端（`d:\oas_xy\OASX`）零改动、下一轮单独做**。
K1（TouchSwipeModel 接入）/ K2（随机 212~265px）/ K3（FrameWait + poll_interval）**全部冻结**，`tasks/KekkaiUtilize/script_task.py` 一字未改。K4 禁止实现。

目标链：`TouchSwipeModel.generate` → `trajectory=[(x,y,dt_ms),...]` → `Control.swipe_trajectory` → BehaviorTrace 一条 `ACTION`/`swipe`（`extra` 携带完整 trajectory）→ JSONL → `read_behavior_clicks` → `GET /stats/{script_name}/behavior/clicks` → 返回 `clicks` + `swipes`，支持 `date` / `task` / `interaction_type` / `target` 四层过滤。

### 改动

**`module/behavior_trace.py`**：新增 `BehaviorTrace.is_recording()` → `self._enabled and not self._broken`（语义等价 `record()` 首行短路的读访问器；供调用方在关闭态跳过大 `extra` 组装。不改 `record()` 契约、不是 v2 事件模型）。

**`module/device/control.py`**：
- 模块级 `_swipe_trajectory_extra(trajectory)`：把传入点列整理成 `{start_x,start_y,end_x,end_y,point_count,trajectory=[[int,int,int],...]}`。直接来自 executor 的真实 commanded 输入，不按 start/end 重 `generate`、不还原曲线；`int(round())` 规整；`dt_ms` 原样（语义仍 D018，不重解释、不新增 `duration_ms`）。
- `Control.swipe_trajectory`：`swipe_minitouch_trajectory` 成功后，`trace = get_behavior_trace(...)`；`extra = _swipe_trajectory_extra(trajectory) if trace.is_recording() else None`；`trace.record('ACTION', action='swipe', target=control_name, elapsed_ms=..., extra=extra)`。**仍只一条 ACTION**；executor 抛异常仍不写（无 swipe 专用 error schema）。
- `Control.swipe`（legacy 端点滑动）：既有 `record('ACTION', action='swipe', ...)` 加 `extra={start_x,start_y,end_x,end_y,point_count:2}`，**不带 `trajectory` 键**（无完整轨迹不伪造曲线）。`p1` 可能被 `distance_check` 的 `+1` 兜底改过 —— 记录的是实际执行端点。`swipe_adb` 直连路径（KekkaiActivation / KekkaiUtilize 怠惰 / 非 minitouch 回退）仍绕过 `Control.swipe`，v1 不覆盖（已知缺口，见 ROADMAP T5-1）。

**`module/server/behavior_stats.py`**（reader，additive）：
- `read_behavior_clicks(script_name, target_day, *, task=None, interaction_type="all", target=None)`。默认参数 → 旧行为 + `swipes` 追加。
- `_normalize_interaction_type` → `all`/`click`/`swipe`（大小写不敏，非法 `BehaviorStatsError(400)`）。
- `_coerce_traj_point` / `_parse_swipe(obj) -> (dict, degraded_bool)`：每条 `action='swipe'` 的 ACTION 都产出一条 `swipes[]` 条目（`{task,action:"swipe",target,ts,start:[x,y]|null,end:[x,y]|null,point_count,trajectory:[[x,y,dt],...],elapsed_ms?}`）。`trajectory` 缺失 → `[]`；非列表或含坏点 → 只留可解析点 + `degraded=True`；`start/end` 优先取 `extra` 显式端点，缺失用轨迹首尾兜底。
- 单遍循环：每条 ACTION 归 `click`（`click`/`long_click`）或 `swipe`；`type_ok`/`task_ok`/`target_ok` 三个等值判断；`available_tasks`（排除 task 维）/ `available_targets`（排除 target 维）在「另两维过滤」下收 distinct 首见序；命中三维才进 `points` / `swipes`。
- 响应：旧键 `config`/`date`/`screen`/`tasks`（= 命中过滤的 click 点里的任务，旧语义）/`points` 不变；`summary` 旧计数（`total`=click 点数、`click_count`、`long_click_count`、`task_count`、`skipped_lines`）不变，**新增** `swipe_count`（一条 swipe 只 +1）/`filtered_count`（click+swipe 命中数）/`malformed_trajectories`；**新增顶层键** `filter`（回显）/`swipes`/`available_tasks`/`available_targets`。
- `malformed_trajectories > 0` 惰性 `from module.logger import logger; logger.warning(...)`（失败静默，与 BehaviorTrace 同风格）。

**`module/server/stats_router.py`**：`behavior_clicks` 端点加 `task` / `interaction_type` / `target` 三个 `Query`；`interaction_type` 归一 + 校验（非法 422）。新增 pydantic 模型 `BehaviorSwipeEntry`（`start/end: list[int] | None`、`trajectory: list[list[int]]`）、`BehaviorClickFilter`；`BehaviorClickSummary` 加 `swipe_count`/`filtered_count`/`malformed_trajectories`（带默认值）；`BehaviorClicksResponse` 加 `filter`/`available_tasks`/`available_targets`/`swipes`。**不另造 `/swipe-stats`**（同端点 additive）。

### 长期契约（写入 D004 补记 / D011 补记 / TESTING §5）

- 事件模型永远只有 `TASK` / `ACTION`；**一次 swipe = 一条 ACTION**，轨迹整体嵌 `extra.trajectory`，禁止 `MOVE`/`SWIPE_POINT`/`FRAME` 事件级别、禁止 trajectory 点变 N 条 ACTION。
- `extra.trajectory` 直接来自传入的 commanded 点列，不重 `generate`/不还原曲线/不抽稀（`max_points ≤ 80` 数据量可控）；legacy `Control.swipe` 只端点无 `trajectory` 键。
- reader additive：旧 JSONL（click-only / swipe 无 trajectory / 坏行 / 单条坏 trajectory）都不 500，坏 trajectory 只降级该条；旧响应键语义不变。
- `swipe_count` 按 ACTION 计不按点计。四层 `date AND task AND interaction_type∈{all,click,swipe} AND target`（`target` 对 click/swipe 同参数同语义）。
- BehaviorTrace 记 commanded input，**不是**实际 UI 位移（K4 才有 `actual_scroll_dy` / `scroll_gain`）；不塞 K3 的 `changed/stable/elapsed`。

### 测试

- `tests/test_behavior_trace.py` `14 → 15`：`test_is_recording_reflects_enabled_and_broken`。
- `tests/test_control_swipe_trajectory.py` `9 → 13`：`swipe_trajectory` 的 ACTION 带完整 `extra.trajectory`（顺序 / dt / start==traj[0] / end==traj[-1] / point_count）；60 点仍一条 ACTION、无 `MOVE`；float 入参取整；关闭态 `is_recording()` False → 不调 `_swipe_trajectory_extra`、无文件；legacy `Control.swipe` trace 只端点、无 `trajectory` 键（用 x 有位移的端点避开 distance_check 的 +1）。
- `tests/test_behavior_click_stats.py` `24 → 45`：`test_response_shape` 改为 additive 键集 + 新 summary 键;
  新增 `ReadBehaviorSwipesTest`（7）：swipe 全字段 parse / 旧 swipe 无 trajectory → `[]` / 完全无 extra / 旧 click-only 兼容 / 单条坏 trajectory（坏点 + 非列表）只降级计 `malformed_trajectories` 不影响 click 与其它 swipe / 一条 60 点 swipe `swipe_count=1` / 坏 JSON 行仍 `skipped_lines` 且 swipes 不受影响;
  新增 `BehaviorStatsFilterTest`（14）：默认 all 回 click+swipe / `click` 与 `swipe` 单类型 / 大小写不敏 / 非法 type 400 / Case A~D / `target` 对 click·swipe 同语义 / `task=B+click` / `available_tasks` 排除 task 维 / `available_targets` 排除 target 维 / 旧 `tasks` 字段 click-derived。

验证：`compileall`（4 生产文件 + 3 测试文件）OK → targeted（`test_behavior_trace` + `test_behavior_click_stats` + `test_control_swipe_trajectory` + `test_minitouch_trajectory_executor` + `test_touch_swipe_model` + `test_kekkai_utilize_state` + `test_frame_wait` + `test_frame_state`）`270 OK` → 完整 `toolkit/python.exe -m unittest discover -s tests` **`1025/1025 OK`**（999 → 1025，+26）→ `git diff --check`（本轮 7 文件）干净。

### 前端下一轮消费契约

`docs/AI_CONTEXT.md` §7「BehaviorTrace Swipe schema（前端待接）」给了完整响应 JSON 示例 + query 参说明。要点：`swipes[].trajectory` 是**一个 ACTION 内部**的 MOVE path，与「多个 click 之间的时序连线」是不同结构、不混一个 `path` 字段；原始 1280×720 坐标、前端复用现有 click 坐标变换；类型下拉用 `available_*` metadata。ROADMAP T5-3 现在只剩 OASX 前端。

### 文档同步

- AI_CONTEXT.md：已更新（新增 §4.46；§7 完整基线 `999 → 1025` + `test_behavior_trace` `14→15` / `test_control_swipe_trajectory` `9→13` / `test_behavior_click_stats` `24→45` + 覆盖清单 2 条 + 新增「BehaviorTrace Swipe schema（前端待接）」小节）。
- DEVELOP_LOG.md：本条。
- ROADMAP.md：已更新（「已完成」表新增「BehaviorTrace Swipe Trajectory Backend」行；T5-3 从「前端 + swipe 后端」改为「Backend 已全部完成，只剩 OASX 前端」，允许 / 禁止 / 验收标准同步重写）。
- ARCHITECTURE.md：已更新（能力清单 BehaviorTrace / 统计后端两行；§2「BehaviorTrace」+「点击 / 滑动统计后端」两小节；§3「滑动」+「自定义轨迹滑动」链的 `record(...)` 加 `extra`）。
- DECISIONS.md：已更新（D004 加「补记（2026-09-07，Swipe Trajectory Backend）」——事件模型不变、swipe=单 ACTION+嵌入 trajectory、legacy 只端点、`is_recording()`；D011 加同名补记 + 旧「只做 click / long_click」条标删除线——additive extension、四层过滤、向后兼容、坏 trajectory 降级、`swipe_count` 按 ACTION、click path ≠ swipe trajectory）。均为补记，非新 ADR。
- TESTING.md：已更新（§5 新增「BehaviorTrace Swipe Trajectory Backend —— 长期契约」条：一次 swipe=一条 ACTION / trajectory 直接来自 executor 输入 / 旧 JSONL 必须兼容 / `swipe_count` 按 ACTION / 四层过滤 + Case A~D / commanded ≠ actual）。

### Git

分支 `master`，HEAD 仍 `2cdf3a0571b0449748aabef259da5cbd2378536c`。未 commit / push / merge / reset / clean / stash。
本轮改动：`module/device/control.py`（`M`）、`module/server/stats_router.py`（`M`）；`module/behavior_trace.py` / `module/server/behavior_stats.py` / `tests/test_behavior_trace.py` / `tests/test_behavior_click_stats.py` / `tests/test_control_swipe_trajectory.py` 均为既有 `??` WIP 文件（本轮在其中新增内容）；`docs/` 五份（AI_CONTEXT / DEVELOP_LOG / ROADMAP / ARCHITECTURE / DECISIONS / TESTING —— 实际六份，见「文档同步」）。既有其它 `M` + `??` WIP 未触碰；OASX 仓库零改动。

## 2026-09-07 - KekkaiUtilize K2 Level C 参数回调：SWIPE_DISTANCE_RANGE (212, 265) → (140, 180)

### Level C 新事实

首次真机观察确认：标准 PASS + minitouch 路径当前 commanded finger distance = 212~265px，
按 `KEKKAI_ROW_PITCH_PX = 106` 静态换算约 2.0~2.5 row_pitch，但**实际好友结界卡列表内容
一次仍滚动 >4 格**。→ 确证 **commanded finger distance ≠ actual content scroll**（好友列表
惯性放大）。首档 `(212, 265)` Level C 判定为过大，需缩短。

### 改动（仅 `tasks/KekkaiUtilize/script_task.py`，单变量）

`SWIPE_DISTANCE_RANGE = (212, 265)` → **`SWIPE_DISTANCE_RANGE = (140, 180)`**（新 provisional
Level C 参数）。整体降约 1/3；≈1.3~1.7 row_pitch 手指位移；受惯性放大预计实际仍滚 2~3 格，
目标是相邻两屏至少保留 1~2 格重叠（A B C D → B C D E / C D E F），避免几乎无重叠的大跨步。
类常量注释改成「分档」表述（首档依据 + 当前档 + 下一档 `(110, 150)` 预案）；
`_perform_search_swipe` docstring 去掉旧数值、指向类常量注释。

### 边界（本轮只改 K2 consumer 参数）

- **未改** `module/device/touch_swipe_model.py`（minimum-jerk / curve / EMA dt / tail /
  max_dt / max_points / exact endpoint 全不动）、`Control.swipe_trajectory`、minitouch trajectory
  executor、K1 起点 X/Y 范围（`(340,600)` / `(500,565)`）、`control_name='KEKKAI_UTILIZE_SWIPE'`。
- **K3 完全保持**：`SWIPE_WAIT_ROI` / `SWIPE_WAIT_CHANGED_THRESHOLD` / `SWIPE_WAIT_STABLE_THRESHOLD` /
  `SWIPE_WAIT_STABLE_FRAMES` / `SWIPE_WAIT_TIMEOUT` / `SWIPE_WAIT_POLL_INTERVAL` /
  `wait_for_changed_and_stable` 一字未动。K3 解决「什么时候停稳」，本轮只解决「滑多远」。
- **K4 继续冻结**：即使 Level C 已证明 actual scroll > commanded row 估计，也不提前进 K4
  （`actual_scroll_dy` / `scroll_gain` / actual-finger ratio / frame matching / candidate projection /
  dedup / new-region-only / dynamic row_pitch 全不做）。
- **lazy / non-minitouch fallback**（`perform_swipe_action` → `swipe_adb`）仍固定 `SWIPE_DISTANCE = 416`，不动。

### 测试（`tests/test_kekkai_utilize_state.py`，纯值更新，用例数不变 = 84）

- `PerformSearchSwipeK2Test`：
  - `test_range_constant_is_2_to_2_5_row_pitch` → 重命名 `test_range_constant_is_level_c_recalibrated_short_step`：
    锁 `SWIPE_DISTANCE_RANGE == (140, 180)`、`lo < hi`、≈1.3~1.7 row_pitch、`hi < 212`（本轮是缩短）、`hi < 416`。
  - `test_each_call_independently_samples_distance`：三次采样值 `212/240/265` → `140/160/180`，
    `ri_calls` 的 `call(212, 265)` → `call(140, 180)`，`end_y = start_y - dist` 断言随动。
  - `test_distance_always_within_range_and_resampled`：400 次大样本 `212 <= d <= 265` → `140 <= d <= 180`，
    新增 `all(d < 212)`（已从首档缩短）。
- `PerformSearchSwipeK1Test` / `PerformSearchSwipeK3Test`：distance 哨兵值 `230` / `240` / `250` → `160`
  （Mock sentinel，不影响断言语义，只为不出现范围外的误导值）。
- 类 / 方法 docstring、模块头注释里的 `212~265` 表述改为「`SWIPE_DISTANCE_RANGE`，Level C 分档」。

验证顺序：`test_kekkai_utilize_state` `84/84` → targeted（`test_kekkai_utilize_state` +
`test_touch_swipe_model` + `test_control_swipe_trajectory` + `test_minitouch_trajectory_executor` +
`test_frame_wait` + `test_frame_state`）`210 OK` → `compileall -q` OK → 完整
`toolkit/python.exe -m unittest discover -s tests` **`1025/1025 OK`**（纯参数回调，无新增 / 删除用例）→
`git diff --check -- tasks/KekkaiUtilize/script_task.py tests/test_kekkai_utilize_state.py` 干净。

### 二次 Level C 待验收（`(140, 180)`）

1. 实际一次滚动几格；2. 是否仍 >4 格；3. 是否能稳定保留 1~2 格重叠；4. 是否出现滑动太小、
列表几乎不动；5. K3 `changed` 是否仍稳定命中；6. K3 `stable` 是否正常；7. OASX swipe trajectory
里 commanded distance 是否确实落在 140~180。
若 `(140, 180)` 仍实际 >3 格 → 下一轮再缩到 `(110, 150)`（单变量、分阶段 Level C 调参，
本轮不直接跳第二档）。

### 文档同步

- AI_CONTEXT.md：已更新（§4.41「K2」子块改成「分档」结构——首档 `(212,265)` 首次 Level C 实测
  >4 格 → 回调 `(140,180)`；「未改」条 / 「不变」条 / K3 前向说明里的 `212~265` 全部改为
  `SWIPE_DISTANCE_RANGE` + 当前档；`PerformSearchSwipeK2Test` 用例描述重写；§7 K2 子行加回调说明。
  完整基线 `1025/1025` 与用例数 `84` 不变）。
- DEVELOP_LOG.md：本条。
- ROADMAP.md：已更新（K2 行状态从「已完成 / Level C 待验收」改为「静态实现完成，首轮 Level C
  发现距离过大、已回调 `(212,265)` → `(140,180)`，需二次 Level C」，验收清单换成二次 Level C 七项 +
  下一档 `(110,150)` 预案；「KekkaiUtilize 单向分区搜索 Level C 待验收」⑤ 与「TouchSwipeModel 接入」
  收尾项里的 `212~265` 同步更新）。
- DECISIONS.md：已更新（D018「K2 补记」改成分档结构、明确「回调档位不新建 ADR、只更新事实」；
  D017 PASS 前初始化补记的 K2 前向说明、D018「不变」条、D018 相关文件行里的 `(212,265)` 同步）。
  **非新 ADR**——`SWIPE_DISTANCE` / `SWIPE_DISTANCE_RANGE` 具体值本就是 D018 明列的「可 Level C 调整」。
- ARCHITECTURE.md：已更新（§自定义轨迹滑动状态段 + 能力表「自定义滑动轨迹」行里的
  `random_int(212,265)` / `212~265px` 改为 `random_int(*SWIPE_DISTANCE_RANGE)` + 分档说明）。
- TESTING.md：无需更新（没有新增长期测试原则；分档调参是一次性 Level C 事实，记在 ROADMAP / §4.41）。

### Git

分支 `master`，HEAD 仍 `2cdf3a0571b0449748aabef259da5cbd2378536c`。未 commit / push / merge /
reset / clean / stash。本轮改动：`tasks/KekkaiUtilize/script_task.py`（`M`，1 个常量值 +
注释 / docstring）、`tests/test_kekkai_utilize_state.py`（`??` WIP，K2 用例值更新 + K1/K3 哨兵值）、
`docs/` 四份（AI_CONTEXT / DEVELOP_LOG / ROADMAP / DECISIONS / ARCHITECTURE —— 实际五份）。
既有其它 `M` + `??` WIP 未触碰；OASX 仓库零改动。

## 2026-09-07 - KekkaiUtilize swipe 增加轻微整体斜度（仅标准 PASS + minitouch consumer）

### 背景

K2 之前：`start = (start_x, start_y)` / `end = (start_x, start_y - distance)` —— `end_x == start_x`，
整条 swipe 虽然 `TouchSwipeModel` 中段有轻微曲率，宏观上仍接近严格竖直。本轮给宏观轨迹加一点
随机斜度（有的轻微左斜 / 有的轻微右斜 / 有的接近竖直），整体仍明确向上 swipe。

### 改动（仅 `tasks/KekkaiUtilize/script_task.py`）

1. 新增类常量 `SWIPE_LATERAL_OFFSET_RANGE = (-12, 12)`（provisional，Level C 调整；注释说明
   只作用于最终 `end_x`、不给 MOVE 点加噪声、贴边界时被有界裁掉退化竖直、不扩大 `start_x` 范围）。
2. `_perform_search_swipe()` minitouch 分支，`distance` 采样之后：
   ```
   lateral_offset = random_int(*self.SWIPE_LATERAL_OFFSET_RANGE)
   lo_x, hi_x = self.SWIPE_START_X_RANGE
   end_x = min(hi_x, max(lo_x, start_x + lateral_offset))
   start = (start_x, start_y)
   end = (end_x, start_y - distance)
   ```
   即 minitouch 分支现在每次 `random_int` **调 4 次**：start_x / start_y / distance / lateral_offset。
3. log 行加 `lateral=%+d`（记 `end_x - start_x`，即有界后的实际横向）。docstring 加「轻微整体斜度」
   小节，「决定滑多远/何时算稳」段改成「滑多远 / 往哪斜 / 何时算稳」，明确 `end_x` 带有界斜度、
   斜度是业务层在 `end` 元组里做的、不是给 `TouchSwipeModel` 或 MOVE 点加噪声。

### 有界处理（要点 8）

`end_x` 夹回起点安全区 `SWIPE_START_X_RANGE = (340, 600)`（不新开常量、不扩大 `start_x` 范围）。
`start_x ∈ [340, 600]` + `lateral ∈ [-12, 12]` → `end_x ∈ [328, 612]` → clamp 到 `[340, 600]`。
`start_x` 落在距边界 ≤12px（约 9% 概率）时该方向的斜度被部分/全部裁掉、退化竖直，绝不滑出安全区。

### 未改

- `distance` / `SWIPE_DISTANCE_RANGE`（当前 `(140, 180)`，不因本轮改斜度再调）。
- `start_x` / `start_y` 随机范围（`SWIPE_START_X_RANGE` / `SWIPE_START_Y_RANGE`）。
- `TouchSwipeModel`（minimum-jerk / curve / EMA dt / timing / tail / max_dt / max_points /
  exact endpoint 全不动）；`TouchSwipeModel().generate(start, end)` 仍只调一次、仍只收 start/end。
- `Control.swipe_trajectory` / minitouch trajectory executor。
- K3 FrameWait（`SWIPE_WAIT_ROI` / `SWIPE_WAIT_CHANGED_THRESHOLD` / `SWIPE_WAIT_STABLE_THRESHOLD` /
  `SWIPE_WAIT_STABLE_FRAMES` / `SWIPE_WAIT_TIMEOUT` / `SWIPE_WAIT_POLL_INTERVAL` /
  `wait_for_changed_and_stable`）。
- K4（`actual_scroll_dy` / `scroll_gain` / frame projection / candidate dedup / new-region-only /
  dynamic row_pitch）—— 继续冻结。
- lazy / 非 minitouch 回退（`perform_swipe_action` → `swipe_adb`）仍固定 `SWIPE_DISTANCE = 416` 纯竖直。
- BehaviorTrace / OASX —— 无需改，`swipe_trajectory` 的 `extra.trajectory` 会自然记录并显示新的
  轻微斜度（§4.46 的 backend 契约不变）。

### 测试（`tests/test_kekkai_utilize_state.py` `84 → 86`）

- `PerformSearchSwipeK2Test` 新增 2 个用例：
  - `test_lateral_offset_makes_swipe_slightly_tilted_but_bounded`：`SWIPE_LATERAL_OFFSET_RANGE ==
    (-12, 12)` 有正有负；中段起点 lat ∈ {-12,-5,0,5,12} → `end = (start_x + lat, start_y - distance)`、
    `end_x` 始终 `∈ [340, 600]`；`-12` → `end_x < start_x`（左斜）、`+12` → `end_x > start_x`（右斜）；
    起点贴左/右边界时偏移被裁掉、`end_x == 边界值`（退化竖直、不越区）。
  - `test_lateral_offset_real_random_bounded_and_two_sided`：真随机源 400 次，`end_x` 恒合法，
    出现过左斜 / 右斜 / 竖直（`o<0` / `o>0` / `o==0` 都命中）。
- 改动既有用例：
  - `test_each_call_independently_samples_distance`（`_one_swipe` 的 `ints` 加第 4 值 lateral=0）：
    `ri_calls` 断言加 `call(-12, 12)`；`ge[1] == start_y - dist`（纵向不受斜度影响）；lateral=0 时
    `ge[0] == gs[0]`。
  - `test_distance_always_within_range_and_resampled`：去掉 `assertEqual(ge[0], gs[0])`（真随机现
    有斜度），只锁纵向 `140<=d<=180`。
  - `test_minitouch_uses_touch_swipe_model_and_swipe_trajectory`（K1）：`random_int` side_effect
    `[400, 540, 160]` → `[400, 540, 160, 7]`，`ri.call_args_list` 加 `call(*KU.SWIPE_LATERAL_OFFSET_RANGE)`，
    断言 `gen_end == (400 + 7, 540 - 160)`（斜度落到 end_x）。
  - `test_trajectory_generated_exactly_once` / `test_trajectory_and_control_name_unchanged`（K2）/
    `PerformSearchSwipeK3Test._run` / `test_real_frame_wait_signature_smoke`：`random_int` side_effect
    补第 4 值 `0`（这些用例不看斜度，保持竖直）。
  - `test_d017_and_touchswipe_untouched`：加 2 条断言——`_perform_search_swipe` 源码里有
    `lateral_offset = random_int(*self.SWIPE_LATERAL_OFFSET_RANGE)` 与 `end = (end_x, start_y - distance)`
    （证明斜度在业务层 end 元组、不在 TouchSwipeModel）。

验证顺序：`test_kekkai_utilize_state` `86/86` → targeted（+ `test_touch_swipe_model` /
`test_control_swipe_trajectory` / `test_minitouch_trajectory_executor` / `test_frame_wait` /
`test_frame_state`）`212 OK` → `compileall -q` OK → 完整
`toolkit/python.exe -m unittest discover -s tests` **`1027/1027 OK`**（1025 → 1027，+2）→
`git diff --check -- tasks/KekkaiUtilize/script_task.py tests/test_kekkai_utilize_state.py` 干净。

### Level C 待验收（并入 K2 二次 Level C）

trajectory 里 `end_x` 是否确实呈现轻微左 / 右斜且不越安全区；斜度会不会影响 K3 `changed` /
`stable` 命中（预计不会——ROI 是 card-column 整块）；对「是否被识别为滑动 / 有无 fling」有无影响。

### 文档同步

- AI_CONTEXT.md：已更新（§4.41「K2」加「轻微整体斜度」子条、把「X 方向纯纵向」改成
  「滑多远 / 往哪斜」、`PerformSearchSwipeK2Test` 描述加 2 个斜度用例、二次 Level C 项加 `end_x` 观察；
  §7 完整基线 `1025 → 1027`、`test_kekkai_utilize_state` `84 → 86` + K2 子行加「轻微整体斜度」段）。
- DEVELOP_LOG.md：本条。
- ROADMAP.md：已更新（K2 行标题加「+ 轻微整体斜度」，正文加斜度机制 + 有界处理 + 2 个新用例 +
  回归 `1025 → 1027`；「KekkaiUtilize 单向分区搜索 Level C 待验收」⑤ 与「TouchSwipeModel 接入」
  收尾项的 K2 行补斜度说明）。
- DECISIONS.md：已更新（D018「K2 补记」加「轻微整体斜度（2026-09-07 同日）」段：`end_x =
  clamp(start_x + random_int(*SWIPE_LATERAL_OFFSET_RANGE), *SWIPE_START_X_RANGE)`、只落最终 end_x、
  不扩大 start_x 范围、`TouchSwipeModel` 未改；明确「调档 / 加有界斜度不新建 ADR、只更新事实」；
  D018「不变」条与相关文件行同步补 `SWIPE_LATERAL_OFFSET_RANGE`）。**非新 ADR**。
- ARCHITECTURE.md：已更新（§滑动链「自定义轨迹滑动」状态段 + 能力表「自定义滑动轨迹」行的 K2
  说明加 `end_x` 有界斜度、`TouchSwipeModel` 仍只收 start/end）。
- TESTING.md：无需更新（没有新增长期测试原则；斜度是 K2 consumer 的一次性 provisional 形状调整，
  Level C 观察项记在 ROADMAP / §4.41）。

### Git

分支 `master`，HEAD 仍 `2cdf3a0571b0449748aabef259da5cbd2378536c`。未 commit / push / merge /
reset / clean / stash。本轮改动：`tasks/KekkaiUtilize/script_task.py`（`M`，1 个新常量 + minitouch
分支 3 行 + log/docstring）、`tests/test_kekkai_utilize_state.py`（`??` WIP，+2 斜度用例 + 既有用例
的 `random_int` side_effect 补第 4 值）、`docs/` 五份（AI_CONTEXT / DEVELOP_LOG / ROADMAP /
DECISIONS / ARCHITECTURE）。既有其它 `M` + `??` WIP 未触碰；OASX 仓库零改动。

## 2026-09-07 - KekkaiUtilize K4：Selected Anchor 实际滚动位移 + 一帧对一帧投影去重（解冻并实施 Level A/B）

### 背景

K1/K2/K3 之后，标准 PASS 每次 swipe 只知道 commanded finger 位移（`SWIPE_DISTANCE_RANGE=(140,180)`
+ `SWIPE_LATERAL_OFFSET_RANGE=(-12,12)`），Level C 已确认游戏列表惯性放大 → commanded ≠ actual。
用户在 Web 标注器新增 `I_IS_SELECTED`（选中态发光竖线，`roi_back=(602,168,30,442)` 纵向动态搜索条），
上一轮静态审查确认生产匹配链能在 `roi_back` 内返回真实绝对坐标。本轮 K4 解冻、实施 Level A/B
（合成图 / mock 集成 / 业务契约测试），Level C pending（好友卡样本不足，不伪造真机）。

### 新增两个 task-local 纯组件

**`tasks/KekkaiUtilize/selected_anchor.py`**（K4-A）：
- `SelectedAnchorResult(available, center_y, bbox, score, match_count)`（frozen）。
- `detect_selected_anchor(frame, rule, *, threshold=None, nms_threshold=0.3, frame_id=None)`：
  走 `RuleImage.match_all_any`（`roi_back` 内 `cv2.matchTemplate` 全量 + NMS，返回 `(score,x,y,w,h)`
  绝对坐标），收敛规则 = NMS 后**恰 1 个** → available（`center_y=y+h/2`）；**0 / >1** → unavailable。
  用资产自带阈值（不改）。不调 `coord()` / `front_center()`；不引用 `SWIPE_DISTANCE` / commanded /
  row_pitch。不 swipe / 不 FrameWait / 不改 PASS。

**`tasks/KekkaiUtilize/frame_projection.py`**（K4-B，纯几何、无状态、无设备依赖）：
- `actual_scroll_dy_px(before, after, *, max_dy) -> float | None`：`before.center_y − after.center_y`；
  任一 unavailable / `dy<=0` / `dy>=max_dy` → None；**保留连续像素**（不取整成格）。
- `project_bbox(bbox, dy) -> (x, y-dy, w, h)`。
- `bbox_iou(a, b)`（`(x,y,w,h)` IoU，无交集 0.0）。
- `dedup_by_projection(previous, current, dy, *, visible_y) -> ProjectionDedupResult(new_detections,
  duplicate_indices, matched_pairs)`：投影 previous → 中心出 `visible_y` 忽略（滚出屏）→ 同
  `image.name` + IoU>0 的候选按 max IoU 降序贪心一对一 → 匹配上的 current 是 duplicate、跳过，
  其余保序为 `new_detections`。**不新增 ±px tolerance**；类型不一致绝不去重；不重新 OCR。

### `tasks/KekkaiUtilize/script_task.py` 改动

- 2 个 import（`detect_selected_anchor` / `actual_scroll_dy_px` + `dedup_by_projection`）。
- 类常量：`K4_ENABLED = True`（kill switch）、`K4_LIST_VISIBLE_Y = (156, 606)`（投影出屏判定，
  取 card-column 纵向包络，provisional）。
- `_run_search_pass` 集成（K3 的 `if not self._perform_search_swipe(): return ABORT` 一字不动）：
  - loop 顶 `screenshot` 后：若 `prev_detections` + `pending_anchor_before` 都在（= 上一屏 swipe 过），
    `anchor_after = detect_selected_anchor(当前帧)` → `dedup_dy = actual_scroll_dy_px(before, after,
    max_dy=I_IS_SELECTED.roi_back[3])`；None → `logger.info(... measurement=unavailable ... fallback=full_scan)`。
  - `cards = find_everyone(...)` 后：`scan_cards = cards`；若 `cards and prev_detections and dedup_dy
    is not None` → `dedup_by_projection(...)` → `scan_cards = dedup.new_detections` + `logger.info(
    Kekkai K4: actual_dy=... rows≈... previous=... current=... duplicates=... new=...)`。
  - 候选循环遍历 `scan_cards`（原 `cards`）——D017 点开 / `check_card_num` / threshold 逻辑一字不动。
  - loop 底 swipe 前（`K4_ENABLED` 时）：`prev_detections = cards`；`self.screenshot()`（重截，
    避免候选详情页污染锚点）；`pending_anchor_before = detect_selected_anchor(当前帧)`。
  - `K4_ENABLED=False` → 顶 / 底两个 K4 块都跳过，`prev_detections` / `pending_anchor_before` 永远
    None → 纯 D017，`detect_selected_anchor` 零调用。

### 契约（写入 D017 K4 补记 / TESTING §5）

- commanded ≠ actual：`actual_scroll_dy` 只来自 anchor 视觉位移；禁止用 `SWIPE_DISTANCE_RANGE` /
  固定 gain；row_pitch 只做「约几格」日志、不参与、不取整。
- 一帧对一帧、无持久历史：只留上一屏 detections + anchor_before。禁止全 PASS / 全局 database /
  好友身份 / persistent dedup map。
- 去重 = 同 `image.name` + bbox IoU>0 的 max-IoU 一对一贪心；投影出 `K4_LIST_VISIBLE_Y` 忽略；
  类型不一致绝不去重；不加 ±px magic tolerance；不重新 OCR。
- 测量不可靠（before/after unavailable / NMS 后 >1 / `dy<=0` / `dy>=roi_back 高度`）→ 完整扫描
  （`scan_cards = cards`），宁可重复不能漏卡。
- `measurement unavailable ≠ ABORT ≠ BOTTOM ≠ PASS_MISS`；K3 失败仍 ABORT 且不进 K4；BOTTOM 仍只认
  `I_U_EMPTY_CARD`；`clicked_any` / `FINAL_USE_LAST` 单调语义不变。K1/K2/K3 一行不改；
  `select_realm_on_1~4` 死资产不删（资产清理另开）。
- `I_IS_SELECTED` 阈值 / 多匹配收敛策略（第一版「>1 → unavailable」）/ `K4_LIST_VISIBLE_Y` 都是
  provisional，等 Level C 再定。
- 阶段口径（本条最初写「K4-2 未进入」有误，此处更正）：**K4-1**（Selected Anchor → `actual_scroll_dy`）
  + **K4-2**（Frame-to-Frame Projection Dedup：previous 按 dy 投影 → 与 current 一对一匹配 →
  duplicates + `new_detections`）**均已实施 Level A/B**（就是上面描述的能力），K4 overall Level C
  pending。未实现的是 **`new-region-only optimization`**（按 dy 只裁新进入视觉区域跑识别——
  性能优化，optional，当前无必要，不改 `find_everyone` ROI / 不动态裁 `roi_back`）。

### 测试

- 新增 `tests/test_kekkai_k4_selected_anchor.py`（11）：NMS 后 0/1/>1 → unavailable/available/unavailable；
  `center_y = y + h/2`；顶/中/底 + 任意连续 Y 命中都算对；score 原样保留；边界 → matcher 0 → unavailable；
  不调 `coord()` / `front_center()`（mock 断言 + 函数体源码扫描）；不引用 commanded / row_pitch；
  `threshold=None` 透传；`SelectedAnchorResult` frozen。
- 新增 `tests/test_kekkai_k4_projection.py`（21）：`actual_scroll_dy_px`（212 / 40 保留 sub-row /
  173·221·287 不取整成格 / `dy<=0` / `dy>=442` / 任一 unavailable → None）；`project_bbox`（y−dy，
  float dy，x/w/h 不变）；`bbox_iou`（identical / disjoint / partial / 边缘相接=0）；
  `dedup_by_projection`（2 dup 2 new / 类型不一致不去重 / 一个 projected 对多个同类 current 只配
  max IoU / 投影出屏忽略 / 全 dup → [] / 无 previous 全 new / new 保序 / 一个 current 不被两个
  previous 双消费）。
- `tests/test_kekkai_utilize_state.py`：`RunSearchPassTest.setUp` patch `detect_selected_anchor` 为
  `SelectedAnchorResult(available=False)` —— 既有 8 用例走 K4 完整扫描回退、行为不变；新增
  `K4IntegrationTest`（8）：dedup 只点 new（3 vs 完整扫描 5）/ measurement unavailable → 完整扫描 /
  全 duplicate 不 ABORT/BOTTOM/PASS_MISS 且继续下滑 / K3 失败仍 ABORT 且 `detect_selected_anchor`
  只被调 1 次（无 after）/ BOTTOM 仍只到 MAX → ABORT（不是到底）/ `K4_ENABLED=False` → 纯 D017 且
  锚点零调用 / 去重后 new 候选仍走 threshold → HIT / 源码接线断言（`detect_selected_anchor` +
  `actual_scroll_dy_px` + `dedup_by_projection` + `scan_cards` + K3 ABORT + `I_U_EMPTY_CARD` +
  `prev_detections = cards` + 无 `candidate_history` / `global_dedup`）。
  `test_kekkai_utilize_state` `86 → 94`。

验证：`compileall -q tasks/KekkaiUtilize/ + 3 测试文件` OK → targeted（K4 两模块 + `test_kekkai_utilize_state`
+ `test_frame_state` + `test_frame_wait` + `test_touch_swipe_model` + `test_control_swipe_trajectory` +
`test_minitouch_trajectory_executor` + `test_behavior_trace` + `test_behavior_click_stats`）`312 OK` →
完整 `toolkit/python.exe -m unittest discover -s tests` **`1067/1067 OK`**（1027 → 1067，+40：K4-A 11 +
K4-B 21 + `K4IntegrationTest` 8）→ `git diff --check`（本轮文件）干净（`assets.py:147/149` 的空白告警
是用户 `is_selected` / `k_search` 资产注释的既有 WIP，非本轮）。

### Level C pending 观察项

selected glow 连续稳定 / 0.8 threshold 无明显假阳性 / before-after 实际 dy 正确 / 投影 bbox 与同卡
current bbox 有 overlap / 新卡不被误去重 / measurement unavailable 时完整扫描正常 / 一屏重叠 1~2 格
时不重复点旧卡；发亮框呼吸动画对命中率的影响；`K4_LIST_VISIBLE_Y` + `I_IS_SELECTED` 阈值 + 多匹配
收敛策略是否需要调。`dedup_by_projection` 的出屏判定是 **center-based**（投影中心落在
`K4_LIST_VISIBLE_Y` 外才忽略）——最坏情况是「投影中心刚好出界、卡体仍部分可见」的旧卡漏去重、
被重复处理，绝不会错误跳过新卡；是否改成 bbox-intersection 判定属 Level C 观察项，本轮不动这个算法。

### 文档同步

- AI_CONTEXT.md：已更新（新增 §4.47；§7 完整基线 `1027 → 1067` + `test_kekkai_utilize_state` `86 → 94`
  + 新增 `test_kekkai_k4_selected_anchor` 11 / `test_kekkai_k4_projection` 21 两行 + K4 子块描述）。
- DEVELOP_LOG.md：本条。
- ROADMAP.md：已更新（「已完成」表新增「KekkaiUtilize K4-1 + K4-2」行 = 均 Level A/B implemented /
  K4 overall Level C pending；「单向分区搜索 Level C 待验收」⑤ 与「TouchSwipeModel 接入」收尾项里
  原「K4 冻结 / 另开」占位改为「K4-1 + K4-2 已实施 Level A/B、K4 Level C pending、`new-region-only
  optimization` optional 未实现」）。
- ARCHITECTURE.md：已更新（§3「自定义轨迹滑动」链后新增「K4（`_run_search_pass` 循环内）」子块：
  `I_IS_SELECTED → detect_selected_anchor → actual_scroll_dy_px → dedup_by_projection → new_detections`
  完整链 + 契约要点；标 K4-1 + K4-2 Level A/B 已实施）。
- DECISIONS.md：D017 加「K4 补记（2026-09-07）」（阶段定义 K4-1 / K4-2 均 Level A/B、`new-region-only
  optimization` optional 未实现 / commanded ≠ actual / 一帧对一帧无持久历史 / 去重条件 /
  测量不可靠 → 完整扫描 / 契约不变 / center-based 出屏判定保留 / 两个纯组件）+ 相关文件行补 K4 模块 /
  资产 / 测试文件。**非新 ADR**——K-series 补记。
- TESTING.md：§5 新增「KekkaiUtilize K4 —— Selected Anchor + 一帧对一帧投影去重 —— 长期契约」
  （measurement failure 不减 candidate / 一帧对一帧无持久历史 / commanded 不替代 actual /
  去重条件 / D017 契约不受影响 / 纯组件优先合成数据）。

### Git

分支 `master`，HEAD 仍 `2cdf3a0571b0449748aabef259da5cbd2378536c`。未 commit / push / merge / reset /
clean / stash。本轮改动：新增 `tasks/KekkaiUtilize/selected_anchor.py` / `tasks/KekkaiUtilize/frame_projection.py`
/ `tests/test_kekkai_k4_selected_anchor.py` / `tests/test_kekkai_k4_projection.py`（`??`）；改
`tasks/KekkaiUtilize/script_task.py`（`M`）/ `tests/test_kekkai_utilize_state.py`（`??` WIP）/ `docs/`
五份。既有其它 `M` + `??` WIP 未触碰（`I_IS_SELECTED` 资产是用户此前标注的、本轮只消费不改）；
未启动 MuMu / 游戏 / 真机 / 图像 RPC 服务。

## 2026-09-07 - 全仓 Swipe Consumer 审查 + TouchSwipeModel 全局迁移（普通滑动 / 列表滚动）

### 背景

TouchSwipeModel（D018）+ `Control.swipe_trajectory` 基础设施已就位，KekkaiUtilize 标准 PASS
（K1~K4）是首个也是唯一生产 consumer，用户已真机连续实测正常。本轮把全仓「普通页面滑动 /
列表滚动」的输入后端从 legacy 端点滑动统一迁到 TouchSwipeModel 轨迹——**只换「怎么滑」，
不换「滑多远 / 滑完等什么 / 失败怎么办」**。先 inventory → 分类 → 逐 consumer 判断 → 再迁移。

### Inventory（生产 swipe / drag consumer）

- **`self.swipe(RuleSwipe)`（`BaseTask.swipe` → `device.swipe`）**：42 个调用点，遍布
  AreaBoss(5) / SwitchSoul(5) / SwitchAccount(3) / QuickLoadout(3) / MemoryScrolls(3) /
  WeeklyPurchase(3) / WantedQuests(2) / Hyakkiyakou(2) / Exploration base(4)+script(1) /
  KekkaiUtilize(3, `S_GUILD_LOTTERY`·`S_U_END`) / GeneralBattle(2, `random_click_swipt`) /
  Summon / Dokan / KittyShop / Secret / CollectiveMissions / DailyTrifles / GeneralBuff(`S_BUFF_UP`)。
  全部 = 普通纵向 list / 页面滚动或左右翻页。
- **直连 `self.device.swipe(...)`**：GeneralBuff `exp_50`/`exp_100`（固定 `(580,320)→(530,240)`
  buff 列表滚动）；RyouToppa `flush_area_cache`（逐 attempt 手调 start/end/distance/`duration`+retry）。
- **直连 `swipe_adb(...)`**：KekkaiUtilize `perform_swipe_action`（怠惰/非 minitouch 回退，固定 416）；
  KekkaiActivation `check_card_num`（好友卡列表滚动，固定 410 + `duration=2`）；AbyssShadows
  `move_a_little`（寮里虚拟摇杆移动，`duration=0.5`）。
- **`BaseTask.list_find` 内部 `device.swipe`**：1 处，服务 ~8 个 `list_find` / `list_appear_click`
  consumer（GameUi navigator / Orochi / FallenSun / EvoZone / EternitySea / WeeklyPurchase navbar /
  GeneralRoom / Dokan）。
- **已是 trajectory**：KekkaiUtilize `_perform_search_swipe`（K1~K4 参考实现）。
- **Drag / 特殊手势**：`Control.drag` + 各后端 `drag_*`；`tasks/Chess/runtime/press_and_drag.py`
  （`Press_and_Drag` 落子拖拽，`hand_operations.py` 消费）；`Control.swipe_vector`（0 生产 consumer）。
- **tests / dev**：`dev_tools/test_touch_swipe_mumu.py`、`dev_tools/hyakkiyakou/utils/generate.py`、
  `tests/test_*`——不计生产 consumer。

### 改动

1. **新公共 helper `BaseTask.swipe_trajectory(start, end, *, control_name='SWIPE', fallback=True)`**
   （`tasks/base_task.py`，+`import math` + `from module.device.touch_swipe_model import TouchSwipeModel`）：
   - minitouch 且位移 ≥ 10px → `TouchSwipeModel().generate(start, end)` → `device.swipe_trajectory(
     traj, control_name=control_name)`（一次 swipe = 一个 BehaviorTrace ACTION）。
   - 非 minitouch → `fallback=True` 回退 `device.swipe(p1=start, p2=end, control_name=control_name)`
     （保留 distance_check / 各后端 duration）；`fallback=False` 抛 `NotImplementedError`。
   - 位移 < 10px（`Control.swipe` 自身「太短当点击」阈值）→ 一律走端点回退、不进轨迹模型。
   - **不** screenshot / FrameWait / sleep / retry / 加随机延迟——业务层职责（helper 不含 K3）。
2. **`BaseTask.swipe(RuleSwipe)`**：`self.device.swipe(p1, p2, control_name=swipe.name)` →
   `self.swipe_trajectory((x1,y1),(x2,y2), control_name=swipe.name)`。起终点仍 `swipe.coord()`，
   方向 / 距离 / `interval` timer / `control_name`（→ `handle_control_check` → `click_record`，
   Exploration `arrive_end` 与换式神 swipe 计数依赖它，两条路径行为一致）不变。42 个 consumer 透明迁移。
3. **`GeneralBuff.exp_50` / `exp_100`**：直连 `self.device.swipe(p2=(530,240), p1=(580,320))` →
   `self.swipe_trajectory((580,320),(530,240), control_name='GENERAL_BUFF_LIST')`；`time.sleep(1)` +
   `max_swipe` 不动。

### 本轮未迁（逐项原因）

- **`BaseTask.list_find` 翻页 swipe**：与 pending 的 T5-2「翻页后固定 `sleep(0.8~1.3)` → FrameState
  等待层」迁移绑定（`tests/test_list_find.py` 是那次迁移的 characterization 基线）；现在单独换输入
  后端会冲乱基线。→ future candidate，与 T5-2 一起做。
- **KekkaiActivation `check_card_num` `swipe_adb`**：好友结界卡列表滚动，距离敏感、是 KekkaiUtilize
  的姊妹路径；`test_kekkai_activation_state.py` 已有 `swipe_adb` 参数 characterization 基线（明确
  「本轮不统一」）。应像 KekkaiUtilize 那样单独走 K1 式分阶段 + Level C。→ future candidate。
- **RyouToppa `flush_area_cache`**：活跃 WIP，逐 attempt 手调 start/end/distance + 显式依赖
  `duration=`（T3-1 契约、`test_swipe_duration_cleanup.py` 锁定）+ retry/verify 结构。迁移资格
  §7.4「不依赖 backend-specific duration」不满足。→ future candidate（需连 duration 契约一起评估）。
- **KekkaiUtilize `perform_swipe_action`**：K-series 明确保留的怠惰 / 非 minitouch 回退（固定 416 + adb）。

### 保留 legacy（drag / 摇杆 / 特殊手势，永不按普通 swipe 迁移）

- `Control.drag` + `drag_minitouch` / `drag_uiautomator2` / `drag_scrcpy` / `drag_nemu_ipc`：
  DOWN → MOVE → 保持 → UP 的拖拽语义，TouchSwipeModel 是「滑动」不是「拖住物体」。
- `tasks/Chess/runtime/press_and_drag.py`（`Press_and_Drag`）：将棋落子的按住 + 拖动手势。
- `AbyssShadows.move_a_little`：寮里虚拟摇杆的方向推动（`p1` 是摇杆中心，`duration=0.5` 决定角色
  移动量），不是列表 / 页面滚动。
- 非 minitouch 后端 `swipe_adb` / `swipe_uiautomator2` / `swipe_scrcpy` / `swipe_window_message` /
  `swipe_nemu_ipc`：`swipe_trajectory` 的回退目标，必须保留。
- `Control.swipe` / `Control.swipe_vector`：D018 保留的历史兼容 API（`swipe` 现在生产 consumer
  只剩 fallback 路径 + list_find + RyouToppa；`swipe_vector` 全仓 0 生产 consumer）。

### GeneralBattle 保护边界

`random_click_swipt`（战斗中 ~0.6%/loop 的反检测随机滑动，`S_BATTLE_RANDOM_LEFT/RIGHT`）经
`BaseTask.swipe` chokepoint 透明迁移。Settlement Contract V3 / reward / result click 全是 `click`、
不涉及 swipe，未改一行。

### 数字

- 审查到的生产 swipe/drag consumer：**约 51**（42 `self.swipe` + `list_find` 1 + GeneralBuff 直连 2 +
  RyouToppa 直连 1 + `swipe_adb` 直连 3 + 已 trajectory 1 + drag/摇杆 3 ≈ 其余为 infra/后端实现）。
- ordinary swipe（list/页面滚动）：**约 47**（42 + list_find 1 + GeneralBuff 2 + KekkaiActivation 1 +
  RyouToppa 1）。
- 本轮迁移到 trajectory：**44**（42 `self.swipe` chokepoint + GeneralBuff 2）。
- 原本已 trajectory：**1**（KekkaiUtilize `_perform_search_swipe`）。
- 保留 legacy 的 ordinary swipe：**4**（list_find / KekkaiActivation / RyouToppa / KekkaiUtilize
  `perform_swipe_action`），逐项原因见上。
- drag：**1**（`Control.drag` + 各后端）。press-and-drag：**1**（Chess）。摇杆手势：**1**（AbyssShadows）。
- **迁移后生产 ordinary legacy swipe 剩余 = 4**（均有明确保留原因，非「大部分已迁移」的模糊说法）。

### 测试

新增 `tests/test_base_task_swipe_trajectory.py`（16）：`swipe_trajectory` helper —— minitouch → 轨迹 /
非 minitouch → 端点回退 / uiautomator2 同 / `generate` 恰调一次 / `control_name` 两路透传 /
`< 10px` 回退不进模型 / int 取整 / `fallback=False` 抛 `NotImplementedError` / `generate` 与 executor
异常都透传不吞 / helper 体内无 `screenshot`·`sleep(`·`wait_for_changed_and_stable`·`for _ in range`·
`while` / `BaseTask.swipe` 委托 helper 且源码不再 `self.device.swipe(` / 非 `RuleSwipe` 仍早退 /
GeneralBuff `exp_50`·`exp_100` 源码用 `swipe_trajectory`。既有测试零改动——task-state 测试的 config
是 MagicMock，`control_method != 'minitouch'` 自然走端点回退、逐字不变。

验证：`compileall -q tasks/ module/device/` OK → targeted（`test_base_task_swipe_trajectory` +
`test_list_find` + `test_swipe_duration_cleanup` + `test_rule_swipe_trace_removed` +
`test_control_swipe_trajectory` + `test_touch_swipe_model` + `test_minitouch_trajectory_executor` +
`test_exploration_state` + `test_realm_raid_state` + `test_kekkai_activation_state` +
`test_kekkai_utilize_state`）`298 + 16 OK` → 完整 `toolkit/python.exe -m unittest discover -s tests`
**`1083/1083 OK`**（1067 → 1083，+16 纯新增）→ `git diff --check` 干净。

### Level C

- **KekkaiUtilize**：K1~K4 已真机连续实测正常（本轮不动，仅作参考实现）。
- **其余 44 个迁移 consumer**：Level A（helper 单测）+ Level B（`BaseTask.swipe` 委托、透明迁移无
  既有用例变化）完成；**Level C PENDING**——minitouch 下曲线轨迹是否被识别为滑动、滚动量与直线
  `insert_swipe` 版差异是否可接受、连续滚动是否因单次轨迹耗时变化触发上层 timeout、横向 ≤16px
  弓形（`curve_cap = min(16, dist·0.12)`）是否经过危险可点击区域、各页是否允许 curved path。
  按风险从低到高逐模块验收（纯纵向 list → 页面滚动 → 左右翻页 → 多次循环 scroll）。

### 文档同步

见本轮报告「## 文档同步」段（AI_CONTEXT §4.48 + §7 基线；本条；ROADMAP「TouchSwipeModel 接入」
收尾项 + 3 个 future candidate；ARCHITECTURE §3 新增 `BaseTask.swipe_trajectory` 链；DECISIONS
D018 补记「ordinary production swipe 优先 trajectory / drag·press-and-drag·摇杆保留 legacy」，非新
ADR；TESTING §5 新增「ordinary swipe consumer 长期契约」）。

### Git

分支 `master`，HEAD 仍 `2cdf3a0571b0449748aabef259da5cbd2378536c`。未 commit / push / merge /
reset / clean / stash。本轮改动：`tasks/base_task.py`（`M`，+2 import + `swipe_trajectory` helper +
`swipe` 一行改委托）、`tasks/Component/GeneralBuff/general_buff.py`（`M`，2 处直连 swipe → helper）、
新增 `tests/test_base_task_swipe_trajectory.py`（`??`）、`docs/` 五份。既有其它 `M` + `??` WIP
（含 OASX 仓库、RyouToppa / KekkaiUtilize 等）未触碰；未启动 MuMu / 游戏 / 真机 / 图像 RPC。

## 2026-09-08 - 全仓 FrameWait + confirm_delay 消费者审查；`list_find` 翻页 settle 迁到 FrameWait

### 背景 / 目标

对整个 Backend 的时序层（固定 `sleep` / `wait_*` / `Timer` / `random_delay` / `confirm_delay`）
做一次完整审查：把真正符合 FrameWait（W1 结构性 settle）/ `confirm_delay`（Point Action reaction
timing）语义的生产 consumer 找出来并尽量迁移。**目标不是「删光 sleep」或「点击都加延迟」**，
而是 eligible → migrated / ineligible → retained with reason / uncertain → Level C pending。

### 等待语义分类（W1~W7）

- **W1 结构性 settle**：动作后固定 sleep 只为等页面变化 / 停稳，然后继续按当前页面视觉状态识别
  → FrameWait 第一优先候选。
- **W2 语义等待**：等明确业务标识出现 / 消失 → 继续 `wait_until_appear` / `appear` 循环，FrameWait
  不替代 semantic marker。
- **W3 协议 / 设备**：minitouch dwell / `DEFAULT_DELAY` / backend sleep / OCR·图像服务启动 / 连接
  等待 → 稳定性层，禁止迁移。
- **W4 retry backoff**。**W5 业务 cooldown / 实时要求**。**W6 behavioral delay**（fatigue / idle /
  `random_delay` / reaction delay）。**W7 unknown** → 保留、报告 `semantic unclear`、不猜。

### Inventory 数字（静态分类估计；精确事实见末尾）

`tasks/` 内 `sleep(` 约 **290 处**；`module/` 约 **135 处**（几乎全 W3 设备后端 / W5 server / W4
retry，全部 retained，本轮不动）。`tasks/` 粗分：W1 结构性 settle ≈ 26（1 迁移 + ~25 Batch B）、
W2 ≈ 120、W3 ≈ 55、W4 ≈ 40、W5 ≈ 14、W6 = `random_delay` 16 caller、W7 ≈ 30。
`Timer(` 生产 caller 分布 base_task 23 / GeneralBattle 15 / GeneralInvite 10 / KekkaiUtilize 8 …；
`wait_until_*` 生产 caller **66 处**（全部 W2，保留）。
**精确事实**：FrameWait 生产消费者 `1 → 2`（K3 + `list_find`）；`confirm_delay` 生产 opt-in `0 → 0`。

### FrameWait 本轮唯一迁移 = `BaseTask.list_find` 翻页 settle（Batch A）

`tasks/base_task.py`：

- **before**：`x1,y1,x2,y2 = target.swipe_pos(...)` → `self.device.swipe(p1,p2)` →
  `sleep(random.uniform(0.8, 1.3))  # 等待滑动完成, 待优化`。
- **after**：`settle_baseline = self.device.image`（翻页前用于识别、此处未再截图故未被污染的那一帧）
  → `self.device.swipe(p1,p2)` → `wait_for_changed_and_stable(settle_baseline, self.device.screenshot,
  roi=_list_roi_back_to_box(target.roi_back), changed_threshold=_LIST_FIND_SETTLE_CHANGED_THRESHOLD,
  stable_threshold=_LIST_FIND_SETTLE_STABLE_THRESHOLD, stable_frames=_LIST_FIND_SETTLE_STABLE_FRAMES,
  timeout=_LIST_FIND_SETTLE_TIMEOUT, poll_interval=_LIST_FIND_SETTLE_POLL_INTERVAL)`。
- 新增模块级 `_LIST_FIND_SETTLE_*`（`changed 0.02 / stable 0.01 / stable_frames 2 / timeout 1.5s /
  poll_interval 0.12`，provisional、Level C 待标定，注释写明「不当全项目通用参数、K3 的 `SWIPE_WAIT_*`
  是卡列表专用不照搬」）+ `_list_roi_back_to_box(roi_back)`（`(x,y,w,h)` → `(x1,y1,x2,y2)`）。
- import 加 `from module.base.frame_wait import wait_for_changed_and_stable`。
- **结果丢弃、不参与控制流**：settle 成功或 timeout 都一样回循环顶 `self.screenshot()` + 重新
  `image_appear` / `ocr_appear`，`max_swipe` 仍是唯一收敛边界，**不新增 BOTTOM / ABORT / 提前返回**
  （§23：`list_find` 的 FrameWait timeout 绝不等价 BOTTOM）。阈值取错最多多等 / 少等一会儿、不影响
  正确性——这是它能在 Level A/B 就迁的关键。
- **ROI = `RuleList.roi_back`**（每个 list 自己的内容区），无全局 ROI（§6）。
- D013「是否抽 seam：否 / seam 与真实参数一起定」的顾虑 2026-09-08 复核可解：`list_find` 循环里
  `screenshot → 识别 → swipe_pos → device.swipe` 之间没再截图，`self.device.image` 在 swipe 时仍是
  那一帧、干净，无需像 K3 那样重截。参数 provisional 因结果不参与控制流而安全。
- ~15 个下游 consumer（Orochi / FallenSun / EvoZone / EternitySea `check_layer`、`GeneralRoom` /
  `WeeklyPurchase navbar` / `navigator` / `Dokan`）零调用点改动、行为不变。

### FrameWait Batch B（eligible，本轮不迁，Level C pending）

SwitchSoul 组 / 队伍列表滚动、QuickLoadout、WeeklyPurchase 商店列表（special / guild / scales /
shrine / thousand_things）、GeneralBuff buff 列表、WantedQuests 悬赏列表、SwitchAccount 账号 /
服务器列表。原因：各自嵌在带 marker + `interval` timer 的定制循环、无专属 characterization、ROI
需逐页推导、阈值 Level C；盲迁有 FSM 破坏风险。列 Level C 矩阵按语义代表性验收。

### confirm_delay：本轮生产 opt-in 仍为 0

`appear_then_click` 真实语义（复核 `tasks/base_task.py:321-390`）= 首次 `appear` →
`sleep(random_delay(*confirm_delay))` → **重新 `screenshot`** → 二次 `appear`（目标没了则不点、返回
False）→ 新帧上 `coord()` / `action.coord()` → click。是「delay 后重新截图 / 二次确认 / 重定位」，
不是「点旧 bbox」。全仓 **486 处 `appear_then_click` + ~264 处 `self.click`/`device.click` + ~26 处
`ocr_appear_click`/`wait_until_appear_then_click`**，**无一传 `confirm_delay`**。与 2026-09-02
专项审查（`docs/Action点击前反应时序静态审查.md`）结论一致：能力正确完整，但 D001「按调用点风险
显式 opt-in、不全局启用」+ D008「不重新引入 `reaction_delay` / 全局自动等待」下无新证据推翻；且
**无实测 delay 区间**，§15 / TESTING §5 禁止拍脑袋新建 `0.3~0.8` 之类全局区间。首个真实 opt-in
仍等 Level C，随 RealmRaid `fire()` R-R1 bounded 改造一起。T0-1 的
`wait_until_appear_then_click(target, wait_time=wait_time)` 关键字修复本轮未触碰、仍在。

### 没有错误叠加（D001 / D012）

FrameWait（视觉结构等待）≠ `confirm_delay`（识别后到点击前 reaction）≠ fatigue（macro idle / rest）
≠ minitouch dwell（DOWN→UP 按压）≠ TouchSwipeModel 逐段 dt（轨迹运动学），owner 不同、不叠加实现
同一等待目的。`list_find` settle 只替换一个 W1 sleep，未碰任何点击 / fatigue / dwell。

### 测试

`tests/test_list_find.py` `22 → 27`：settle 走 `wait_for_changed_and_stable`（patch `tasks.base_task`
引用）——baseline = 翻页前帧 / frame_provider = `device.screenshot` / ROI = `RuleList.roi_back` 换算
成 `(x1,y1,x2,y2)` / 三阈值 + timeout + poll_interval 都显式传（无全局默认）/ timeout 结果不改
收敛不 BOTTOM 不 ABORT / settle-wait 异常透传 / `_list_roi_back_to_box` 换算单测。既有 22 用例的
识别·swipe·退出·返回·异常 characterization 全部保留（`sleep`/`random.uniform` 断言换成 `wait` 断言）。

验证：`compileall -q tasks/base_task.py tests/test_list_find.py` OK → `tests/test_list_find` `27/27`
→ 完整 `toolkit/python.exe -m unittest discover -s tests` **`1088/1088 OK`**（1083 → 1088，+5 纯新增
——既有 22 用例改断言不计数变化，新增 5：settle 参数锁 / timeout 不改收敛 ×2 / settle-wait 异常 /
`_list_roi_back_to_box` ×2 中的净增）→ `git diff --check -- tasks/base_task.py` 干净。

### 文档同步

见本轮报告「## 文档同步」段（AI_CONTEXT §4.18 / §4.19 更新 + 新增 §4.49 + §7 基线 1083→1088；本条；
ROADMAP T5-2 前半标已迁 / Batch B + confirm_delay Level C 矩阵；ARCHITECTURE FrameWait 链加第 2
个消费者 + 三层职责重申；DECISIONS D013 补记（list_find FrameWait 迁移、结果不参与控制流、参数
provisional）+ D012 补记（第 2 个消费者）；TESTING §5 新增「时序层长期规则 W1~W7」）。

### Git

分支 `master`，HEAD 仍 `2cdf3a0571b0449748aabef259da5cbd2378536c`。未 commit / push / merge /
reset / clean / stash。本轮改动：`tasks/base_task.py`（`M`，+1 import + 模块级 `_LIST_FIND_SETTLE_*` /
`_list_roi_back_to_box` + `list_find` settle 一段）、`tests/test_list_find.py`（`??` WIP，`22 → 27`）、
`docs/` 六份。既有其它 `M` + `??` WIP（含 OASX 仓库、`GeneralBattle/assets.py` · `KekkaiUtilize/
assets.py` 的注释尾空白、`*.json` CRLF 等）未触碰、只报告不清理；未启动 MuMu / 游戏 / 真机 ADB /
OCR / 图像 RPC。

## 2026-09-08 - T7 点击热点统一规则：人工热点优先 + 未采样目标按 ROI 尺寸计算热点

### 目标与决策

在不改变 HABIT sampler、Safe ROI、一次点击一次采样、GeneralBattle Settlement V3 业务策略的
前提下，正式替换旧 `CENTER_FALLBACK=(0.5,0.5)`：热点解析优先级固定为
`EMPIRICAL > RULE_FALLBACK`。已有人工数据的 `area_1` / `wide_card` 继续使用自身
EMPIRICAL `(0.58,0.59)`；未采样 target 使用统一规则锚点
`RULE_BASE_PREFERRED=(0.58,0.59)`，provenance 明确为 RULE_FALLBACK。数值相同不等于来源相同，
未来 target 自己的 EMPIRICAL registry 条目自然覆盖规则兜底。长期决策记入 D019。

### 实现

- `module/click_preference.py`：`CENTER_FALLBACK` 改为 `RULE_FALLBACK`；新增
  `RULE_BASE_PREFERRED` / `RULE_FALLBACK_PROFILE`；resolver 的未知 / 空名默认返回规则锚点；
  GeneralBattle 三个 Region 显式条目改为 RULE_FALLBACK `(0.58,0.59)` + `default_region`；
  `area_1` 继续是 EMPIRICAL，不降格。
- `module/click_profile.py`：新增纯函数
  `adapt_preferred_by_size(preferred_u, preferred_v, roi)`，按 short side、24/96 锚点和
  smoothstep 公式计算 effective preferred；`adapt_point_profile` 改为复用它，同时保留原有
  sigma / tail 尺寸适配。`default_point` / `default_region` 的 `(0.5,0.5)` 仍是 shape profile
  的中性占位，不再代表 target 的最终兜底热点。
- `module/click_sampler.py`：Point 仍走 `adapt_point_profile`；Region 只调用
  `adapt_preferred_by_size` 后替换 preferred，明确不调用 Point adaptation，因此
  `default_region` 的 sigma / weights / margin / tail 不收缩。
- 原子 Rule / GeneralBattle / GeneralInvite / Secret / RyouToppa 的说明同步为 RULE_FALLBACK，
  没有改 Control、输入后端、HABIT 算法、业务状态机或 region 选择策略。

当前 GeneralBattle 三个真实 ROI 的 effective preferred：

- `random_default`：short side 230 → `(0.58,0.59)`；
- `random_save_right`：short side 87 → `(0.5765625,0.5861328125)`；
- `random_save_bottom`：short side 69 → `(0.5546875,0.5615234375)`。

### 测试与验证

- `tests/test_click_profile.py`：新增 `AdaptPreferredBySizeTest` 4 项，覆盖 short side 取最短边、
  `<=24` / 32 / 40 / 48 / 60 / 72 / 80 / `>=96` 真实公式、端点精确与非法输入 fail-fast；
  单模块从 87 → 91。
- `tests/test_t7_5_preferred_hotspot.py`：更新 provenance / 未知 target / Point effective preferred
  契约，保留 wide_card EMPIRICAL 护栏。
- `tests/test_t7_5_stage2.py`：更新 Region registry / effective preferred / 分布测试，并新增源码与
  profile 断言锁定「只适配 preferred，不调用 `adapt_point_profile`，shape 不变」。
- 相关五模块：`216/216 OK`。
- `toolkit/python.exe -m compileall module tasks tests dev_tools`：OK。
- `toolkit/python.exe -m unittest discover -s tests`：**1092/1092 OK**（1088 → 1092）。
- `git diff --check`：未全绿，仅报告本轮开始前已经存在的
  `tasks/Component/GeneralBattle/assets.py` 8 处（含 EOF 空行）与
  `tasks/KekkaiUtilize/assets.py` 2 处尾空白；按「不清理其它 WIP」约束未修改。对本轮涉及的
  代码 / 测试 / 文档另做尾空白扫描，没有新增命中（`DEVELOP_LOG.md` 两处历史尾空白除外）。
- 未启动 MuMu / 游戏 / OCR / 图像 RPC；Level C 点击体验与真机分布待后续采样。

### 文档同步

`AI_CONTEXT.md` 新增 §4.50 并更新当前基线；`ROADMAP.md` 增加完成项；`ARCHITECTURE.md` 更新
Point / Region 调用链；`DECISIONS.md` 新增 D019、对 D014 旧 fallback 表述加 supersede 指针；
`TESTING.md` 更新长期契约；本文件追加本条；`T7_TARGET_PREFERENCE_MAP.md` 更新当前 registry 与
Point / Region 链路。

### Git

分支 / HEAD / 其它 WIP 保持现状；未执行 reset / clean / stash / checkout / restore / merge /
commit / push，未清理其它修改。`module/click_preference.py`、`module/click_profile.py`、
`module/click_sampler.py`、相关测试与 `docs/` 在本工作树原本即处于未跟踪 WIP 范围，本轮只在授权
路径内继续修改。

## 2026-09-08 - 第一批业务 Reaction Timing / `confirm_delay` 迁移（Batch A #1–#23，5 个任务）

### 背景 / 目标

依 `docs/常用业务点击链与Reaction审查.md`（只读审查）的 Batch A #1–#23：把常用业务里「识别到
稳定 Point Target → 立即点击」的一批调用，正式改成经 `BaseTask.appear_then_click(..., confirm_delay=)`
的「识别 → reaction delay → fresh screenshot → 二次 `appear`（没了不点、返回 False）→ 重新
`coord()` → click」。**复用现有 primitive，不重新设计 reaction API**：不新增 `reaction_delay()` /
`CLICK_REACTION_DELAY` / 全局默认点击等待 / `BaseTask` 全局默认 `confirm_delay`；`appear_then_click`
本体一字未改，`confirm_delay=None`（不传）默认行为不变（D001 / D008）。

### 新增 `module/reaction_profile.py`（公共 reaction profile）

与 `module/click_profile.py` / `click_preference.py` 同层。**只含具名 `(min, max)` 秒区间常量**：
无函数 / 无 `sleep` / 无 `random_delay` / 不 import task·device·config；由业务 consumer 在调用点
**显式**传 `confirm_delay=`；不在 asset / `RuleImage` 层设默认。当前值（**全部 PROVISIONAL /
engineering baseline，非 Level C 标定**）：

| profile | 区间(s) | 用于 |
|---|---|---|
| `REACTION_FAST` | `(0.18, 0.35)` | 锁定 / 解锁、简单开关、低频管理按钮 |
| `REACTION_NORMAL` | `(0.45, 0.85)` | 普通进入 / 组队 / 普通稳定选择 |
| `REACTION_NORMAL_HIGH` | `(0.60, 1.00)` | 高频重复但目标长期稳定（**本轮 0 consumer，允许**） |
| `REACTION_CONFIRM` | `(0.55, 1.20)` | 刷新确认 / 明确确认 / 有流程影响的确认 |
| `REACTION_NAVIGATION` | `(0.55, 1.10)` | 返回 / 取消退出 / 导航离开 |
| `REACTION_DELIBERATE` | `(0.90, 1.60)` | 材料类型 / 阵容 / 预设等需明显选择判断 |

`REACTION_PROFILES` dict + `REACTION_PROFILES_PROVISIONAL = True` 供测试 / 工具遍历，不参与运行时。

### 迁移调用点（27 处 / 5 任务，此前生产 `confirm_delay` consumer = 0）

- **`tasks/RealmRaid/script_task.py`（6）**：`ensure_lock` 的 4 个锁定/解锁按钮
  `I_UNLOCK`/`I_UNLOCK_2`/`I_LOCK`/`I_LOCK_2` → `confirm_delay=REACTION_FAST`；`check_refresh` 的
  `I_FRESH` → `REACTION_NORMAL`（刷新动作本体，不因名字含「刷新」机械归 CONFIRM）、`I_FRESH_ENSURE`
  → `REACTION_CONFIRM`（明确确认弹窗）。`interval` / `threshold` / 控制流 / 锁定 FSM 全不变。
- **`tasks/Component/GeneralBattle/general_battle.py`（1，公共方法扩参）**：`check_lock(enable,
  lock_image, unlock_image, confirm_delay=None)` 新增可选参数并透传给两分支的 `appear_then_click`；
  **默认 `None` = 原行为**。非 batch 调用方（EternitySea / FallenSun / GoryouRealm / OtherWorldTwilight /
  Sougenbi）不传，逐字不变。
- **`tasks/Orochi/script_task.py`（5）**：`check_lock(..., I_OROCHI_LOCK, I_OROCHI_UNLOCK,
  confirm_delay=REACTION_FAST)`（`run_leader`/`run_alone`/`run_wild` 共 3 处）；`I_FORM_TEAM`
  （`run_leader`/`run_wild` 共 2 处）→ `REACTION_NORMAL`。
- **`tasks/EvoZone/script_task.py`（4）**：`check_lock(..., I_EVOZONE_LOCK, I_EVOZONE_UNLOCK,
  confirm_delay=REACTION_FAST)`（`run_leader`/`run_alone` 共 2 处）；`evozone_enter` 的
  `appear_then_click(kirintype, interval=1, confirm_delay=REACTION_DELIBERATE)` —— **真实代码只有
  一个点击点**（`kirintype` 是配置选定的 4 种麒麟类型之一，没有单独的「入口」目标），故只加一次、
  归 DELIBERATE（材料 / 类型选择）；`I_FORM_TEAM`（`run_leader`）→ `REACTION_NORMAL`。
- **`tasks/RyouToppa/script_task.py`（3）**：`_ensure_team_lock_state` 的 `appear_then_click(source,
  interval=0, confirm_delay=REACTION_FAST)`（确认过是 `action=None` 形态）；`start_ryou_toppa` 管理
  路径的 `I_SELECT_RYOU_BUTTON` / `I_START_TOPPA_BUTTON` → `REACTION_FAST`。
- **`tasks/Exploration/base.py` + `script_task.py`（9）**：`switch_rotate` 的 `I_E_AUTO_ROTATE_ON`
  + `run_on_exp_settings` 的 `I_E_AUTO_ROTATE_OFF` → `REACTION_FAST`；`run_on_exp_exit` 的
  `I_E_EXIT_CANCEL` → `REACTION_NAVIGATION`、`I_E_EXIT_CONFIRM` → `REACTION_CONFIRM`；`quit_exp_main`
  的 `I_UI_BACK_YELLOW` → `REACTION_NAVIGATION`；`open_expect_level` 两个 while 循环里的
  `I_UI_CONFIRM` / `I_UI_CONFIRM_SAMLL`（共 4 处）→ `REACTION_NORMAL`。

**按 profile**：FAST 14 / NORMAL 8 / CONFIRM 2 / NAVIGATION 2 / DELIBERATE 1 / NORMAL_HIGH 0。

### 明确排除（本轮 0 新 reaction consumer）

- **`*_FIRE` 系列（R2 STATE_WAIT_FIRST）**：RealmRaid `fire()` / `I_FIRE` / `C_PARTITION_n` /
  `fire_again`（`I_SHOW_AGAIN` / `I_FIRE_AGAIN` / `fire_again` 内 `I_FRESH_ENSURE`）；Orochi
  `I_OROCHI_FIRE` / `I_OROCHI_WILD_FIRE`；EvoZone `I_EVOZONE_FIRE`。这些成功判据仍是「旧标识消失」、
  缺正向战斗页确认 —— 先做 R-R1（正向 `page_battle_prepare/page_battle` 确认 + `max_tries` + `Timer`，
  照 `Exploration/base.py::fire()`）再接 reaction，本轮不顺手做。
- **动态 / OCR / polling / Region**：`check_layer` / `L_LAYER_LIST`、Exploration `fire(button)` 动态怪物
  target、`O_E_EXPLORATION_LEVEL_NUMBER`、宝箱 / `I_REWARD`、`I_UI_CANCEL` 队长弹窗、
  `pages.random_click()`、`C_CLICK_SETTINGS` / `C_CLICK_STANDBY_TEAM` / `L_ROTATE_1`。
- **已有同语义 timing owner（不叠加）**：RyouToppa `attack_area` 的 `I_FIRE`（已手搓
  `random_delay(0.2, 0.6)` + fresh screenshot + 二次 `appear` + click）+ 区域进攻前
  `random_delay(1.0, 3.0)`（可开关业务 pacing）+ fatigue safe node；`C_AREA_1~8`（T7 采样 + 区域
  pacing）；GeneralBattle `I_PREPARE_HIGHLIGHT`（`prepare_click_timer` = `random_delay(PREPARE_CLICK_DELAY_RANGE)`）、
  Settlement V3 三个 Region（`settlement_click_timer` + `_advance_generic_result` 强制双击间隔，D016）。
- **瞬态战斗按钮**：`I_DISABLE_7DAYS_DIFF_SOUL` / `I_CONFIRM_CLOSE_DIFF_SOUL` / `I_OVER_GHOST` /
  `I_GB_SKIN_CONFIRM` / `green_mark` / `C_RANDOM_CLICK`。
- 上一轮 Batch A **#24/#25**（GeneralBattle 差异御魂弹窗）、**#26**（RyouToppa `I_GUILD_ORDERS_REWARDS`
  带 `action=C_SELECT_FIRST_RYOU`，最终点的是 `action.coord()`、不重定位 target）**本轮不实施**。

### 测试

新增 `tests/test_reaction_timing_batch1.py`（34）：
- `ReactionProfileConstantsTest`（5）：6 个 profile 精确值 / 递增二元组 / registry 一致 /
  `REACTION_PROFILES_PROVISIONAL is True` / 模块正文（去 docstring）无 `def`·`sleep(`·`random_delay`·
  `class`·task 依赖。
- 每任务源码扫描（RealmRaid / Orochi / EvoZone / RyouToppa / Exploration）：每个迁移调用点带
  正确 `confirm_delay=REACTION_*`；排除项 / 瞬态 / 动态 / OCR / `*_FIRE` / `check_layer` 无 `confirm_delay`；
  EvoZone `evozone_enter` 只出现 1 次 `confirm_delay=`（不给 5 个类型各加）；Exploration
  `open_expect_level` 恰 2+2 处、`ocr_appear_click(O_E_EXPLORATION_LEVEL_NUMBER)` 与 `time.sleep(1)` 段未动。
- `GeneralBattleExclusionTest`（6）：`check_lock` 签名含 `confirm_delay` 默认 `None`、两分支透传；
  mock 行为断言「不传 → 内部收到 `None`」「传 `REACTION_FAST` → 内部收到 `(0.18,0.35)`」；
  `I_PREPARE_HIGHLIGHT` / `_advance_generic_result` / `_settlement_click` / `_sample_settlement_click` /
  `_handle_result` / `_handle_reward` / `random_click_swipt` 无 `confirm_delay`，`settlement_click_timer`
  + 强制双击间隔仍在。
- `TimingOwnerNoStackTest`（3）：RyouToppa `attack_area` 保留 `random_delay(1.0,3.0)` 与
  `fire_delay = random_delay(0.2, 0.6)` 且无 `confirm_delay`；GeneralBattle `PREPARE_CLICK_DELAY_RANGE` /
  `SETTLEMENT_CLICK_INTERVAL_RANGE` 仍在；6 个 `*/assets.py` 不 import `reaction_profile` / 无 `confirm_delay`。

`appear_then_click` primitive 未改，`tests/test_base_task_confirm_click.py`（5）继续锁其行为。

### 验证

`compileall -q module tasks tests dev_tools` OK → targeted（`test_reaction_timing_batch1` +
`test_base_task_confirm_click` + `test_realm_raid_state` + `test_exploration_state` +
`test_general_battle_settlement` + `test_general_battle_timing` + `test_ryoutoppa_c_area_1_point_opt_in`）
`207 OK` → 完整 `toolkit/python.exe -m unittest discover -s tests` **`1126/1126 OK`**（`1092 → 1126`，
+34 纯新增，0 回归）→ `git diff --check`：本轮新增 / 修改文件全干净；仍只命中
`tasks/Component/GeneralBattle/assets.py` 与 `tasks/KekkaiUtilize/assets.py` 的**既有 / 无关**
尾空白 + EOF WIP（本轮之前就有，**不清理**）。

### Level C pending

二次 confirm 成功率 / reaction 实际分布 / 是否明显增加任务耗时 / delay 期间 target 消失导致漏点 /
高频稳定 Action 是否需 NORMAL → NORMAL_HIGH / provisional profile 是否按任务微调。在拿到 Level C
证据前不放大区间。Fatigue 本轮未扩（Orochi / EvoZone / RealmRaid / Exploration 仍未系统接入
fatigue safe node —— 属 task-cycle macro idle，下一轮独立处理）。

### 文档同步

见本轮报告「## 文档同步」段（AI_CONTEXT §4.51 + §7 基线 1092→1126；本条；ROADMAP「Action 反应时序」
项状态从「0 opt-in / 等 R-R1」改为「Batch A #1–#23 已落地 Level A/B，参数 Level C 待标定」；
ARCHITECTURE「时序职责分层」Reaction 层从「零生产 opt-in」改为「首批 27 consumer + `module/reaction_profile.py`」；
DECISIONS D001 补记；TESTING §5 新增「Reaction Timing 长期规则」）。

### Git

分支 `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。未 commit / push / merge /
reset / clean / stash / checkout / restore。本轮改动：新增 `module/reaction_profile.py`、
`tests/test_reaction_timing_batch1.py`；改 `tasks/RealmRaid/script_task.py` / `tasks/Orochi/script_task.py` /
`tasks/EvoZone/script_task.py` / `tasks/RyouToppa/script_task.py` / `tasks/Exploration/base.py` /
`tasks/Exploration/script_task.py` / `tasks/Component/GeneralBattle/general_battle.py`（`check_lock` 扩参）/
`docs/` 六份。既有其它 WIP（含 `*/assets.py` 尾空白）未触碰。未启动 MuMu / 游戏 / OCR。

## 2026-09-08 - RyouToppa / RealmRaid FIRE Reaction 统一 + RealmRaid fire() 状态机收口（R-R1）

### 背景

承接「第一批业务 Reaction Timing」（§4.51）。`I_FIRE` 系列上一轮明确排除（RealmRaid `fire()` 属
R2 STATE_WAIT_FIRST，须先做正向战斗确认 + bounded retry；RyouToppa `I_FIRE` 已手写等价 confirm_delay
`random_delay(0.2, 0.6)`）。本轮正式处理这两个场景，其余 `*_FIRE`（Orochi / EvoZone）仍不动，先把
RyouToppa + RealmRaid 做成标准模板。

### FIRE Reaction 标准

`module/reaction_profile.py` 新增 **`REACTION_FIRE = (0.4, 0.8)`**（纳入 `REACTION_PROFILES` dict，
`REACTION_PROFILES_PROVISIONAL` 仍 True）。语义 = 「已识别到稳定 `I_FIRE` 后、真正执行 FIRE click
前的人为 reaction」。**PROVISIONAL / engineering baseline**，非 Level C 人工标定；不再让两个场景
互相跟随旧值。§4.51 的 6 组 profile 数值不动。

### RyouToppa（`tasks/RyouToppa/script_task.py`，只统一 delay profile）

`attack_area` 的 `fire_delay = random_delay(0.2, 0.6)` → **`random_delay(*REACTION_FIRE)`**（仍在
`for attempt in range(1, RYOU_TOPPA_ACTION_RETRIES + 1)` 循环体内 → 每次 attempt 独立采样）。
**其余全部保持**：`_wait_for_attack_state()`（battle/fire/list/unknown）、`is_in_battle(False)`、
reaction 后 `self.screenshot()` + 二次 `appear(RealmRaidAssets.I_FIRE, threshold=0.8)`（没了不点、
`continue`）、`AreaAttackResult`、有限 attempt、`reopen_area` 恢复、区域进攻前
`random_delay(1.0, 3.0)` 业务 pacing（`raid_config.random_delay` 开关，**未删未改**）、fatigue safe
node。**未加 `confirm_delay`**——不在已有手写 reaction 链上叠第二层。

### RealmRaid（`tasks/RealmRaid/script_task.py`，`fire()` R-R1 收口）

新增 module 级常量（engineering baseline，非 Level C）：`RR_FIRE_MAX_TRIES = 4`、`RR_FIRE_TIMEOUT = 10`
（参考 `Exploration/base.py::fire()` 的 `max_tries=4` + `Timer(10)`）、`RR_FIRE_POST_CLICK_TIMEOUT = 3`
（参考 RyouToppa `RYOU_TOPPA_STATE_TIMEOUT=3`）。imports 补 `from time import sleep` /
`from module.base.timer import Timer` / `from module.base.utils.random import random_delay` /
`REACTION_FIRE`。

- **旧 `fire()`**：`wait_until_appear(I_RR_PERSON)`（无 `wait_time`）→ `while True`：
  `if not appear(I_RR_PERSON): return True`（**旧详情页标识消失即成功**）/
  `appear_then_click(I_FIRE, interval=1)` / `click(C_PARTITION_{order}, interval=2)`。恒返回 True、
  尾部 `return False` 不可达 → `run()` 里 `if not self.fire(index): continue` 是死分支。
- **新 `fire()`**：`wait_until_appear(I_RR_PERSON, wait_time=RR_FIRE_TIMEOUT)` →
  `for attempt in range(1, RR_FIRE_MAX_TRIES + 1)` 且 `Timer(RR_FIRE_TIMEOUT)` 未 `reached()`：
  1. `screenshot` → **`is_in_battle(False)` 正向战斗确认**（复用 `GeneralBattle.is_in_battle` ——
     `I_BATTLE_INFO` / `I_PREPARE_HIGHLIGHT` / `I_WIN` / `I_DE_WIN` / `I_FALSE` / `I_REWARD` …）→ `return True`；
  2. `I_FIRE` 未就绪 → `click(C_PARTITION_{order}, interval=2)` 打开目标详情（原业务逻辑不变）；
  3. `I_FIRE` 就绪 → 本 attempt **独立** `fire_delay = random_delay(*REACTION_FIRE)` → `sleep` →
     fresh `screenshot` → 再次 `is_in_battle` → 二次 `appear(I_FIRE, threshold=0.8)`
     （**reaction 期间消失则不点旧坐标、`continue` 回循环顶按当前页面重判**）→
     `appear_then_click(I_FIRE, interval=0, threshold=0.8)` → `_wait_fire_entered_battle()`；
  4. attempt / timeout 用尽 → **`return False`（可达）**。
- **`_wait_fire_entered_battle(timeout=RR_FIRE_POST_CLICK_TIMEOUT)`**（新私有 helper）：有界
  `Timer` 内轮询 `is_in_battle(False)` → True；若 `I_FIRE` 与 `I_RR_PERSON` 都不在且非战斗 → 提前
  `return False` 交回主循环。**不新造 battle detector**，只是 `is_in_battle` 的有界轮询外壳
  （与 RyouToppa `_wait_for_attack_state` 同款）。
- **`I_RR_PERSON` 降级为辅助信号**，不再单独判成功。
- **caller `run()` 未改**：两处 `if not self.fire(index): continue`（原本就有、原本因 `fire()` 恒
  True 而不可达）现在真正生效——`fire(False)` → `continue` 回 `while 1` 顶重新 `check_ticket` +
  `find_one`，**不在非战斗页误调 `run_general_battle`**。

### timing owner check（无叠加）

- RealmRaid `fire()`：恰 **1 处** `random_delay`（FIRE reaction `REACTION_FIRE`），无 `confirm_delay`、
  无 `reaction_delay` / `CLICK_REACTION_DELAY`、无第二套 repeat/retry delay（下一次 attempt 的
  `REACTION_FIRE` + 状态检查即构成合理 retry 间隔）。
- RyouToppa `attack_area`：恰 **2 处** `random_delay` —— 区域 pacing `(1.0, 3.0)` + FIRE reaction
  `(*REACTION_FIRE)`；无 `confirm_delay`。
- GeneralBattle `prepare_click_timer` / `settlement_click_timer`、Fatigue、minitouch dwell、
  TouchSwipeModel dt 均未参与、未改。

### 明确未改

`appear_then_click` primitive；`C_PARTITION_1~9` 坐标 / ROI / RuleClick / ClickSampler / T7 hotspot /
order 逻辑 / 目标选择策略（本轮只调整「什么时候点 partition」，无空间重构）；`fire_again()` /
`I_FIRE_AGAIN` / `I_SHOW_AGAIN`；GeneralBattle（`general_battle.py` 零改动：Settlement V3 /
`_prepare_click_ready` / `prepare_click_timer` / `settlement_click_timer` / `_advance_generic_result` /
`_next_settlement_click_interval` / `C_RANDOM_*` / ClickSampler settlement policy）；Orochi
`I_OROCHI_FIRE` / `I_OROCHI_WILD_FIRE`；EvoZone `I_EVOZONE_FIRE`；Exploration `fire()`（参考实现）/
`open_expect_level` 的 `swipe → time.sleep(1) → OCR`（下一轮 FrameWait）；§4.51 的 27 个
`confirm_delay` consumer 与 6 组 profile 数值。Fatigue 本轮不扩（RealmRaid 未新增 fatigue consumer）。

### 测试

新增 `tests/test_fire_reaction_fsm.py`（29）：
- `ReactionFireProfileTest`（4）：`REACTION_FIRE == (0.4, 0.8)` / `lo < hi` / `REACTION_PROFILES['FIRE']` /
  `REACTION_PROFILES_PROVISIONAL is True` / §4.51 6 组不变。
- `RyouToppaFireReactionTest`（7）：delay 统一 `random_delay(*REACTION_FIRE)` 且非 `0.2, 0.6` /
  AST 确认采样在 `for attempt` 循环体内 / reaction → `screenshot` → `is_in_battle` → 二次
  `appear(I_FIRE)` / 没了不点 / `RYOU_TOPPA_ACTION_RETRIES` + `_wait_for_attack_state` 保留 /
  `random_delay(1.0, 3.0)` 保留 / 无 `confirm_delay`。
- `RealmRaidFireFsmTest`（12，`_FakeTimer` + `_seq` 无限尾迭代器 + patch `random_delay`/`sleep`/`Timer`）：
  正向 `is_in_battle` → True（首帧成功不点击）/ 点击后 `_wait_fire_entered_battle` → True /
  **旧 marker 消失但非战斗 ≠ success（bounded 用尽 → False，且从不 `appear_then_click`）** /
  reaction 期间 FIRE 消失不点旧坐标 / 每 attempt 独立采样（`random_delay` ≥2 次、args `(0.4, 0.8)`）/
  bounded `RR_FIRE_MAX_TRIES` → False / `_FakeTimer.budget=0` 模拟 timeout → False 立即退出 /
  prologue `wait_until_appear` 带 `wait_time=RR_FIRE_TIMEOUT` / partition[order-1] `interval=2`。
- `RealmRaidCallerCompatTest`（2）：`run()` 两处 `if not self.fire(index):` 后紧跟 `continue`；
  AST 确认无「裸 `self.fire(index)` 表达式」（返回值从不被丢弃）；成功路径到
  `run_general_battle(con.general_battle_config)`。
- `FireTimingOwnerTest`（3）：RealmRaid `fire` 恰 1 处 `random_delay(` 且无 `confirm_delay` / `REACTION_FAST`；
  RyouToppa `attack_area` 恰 2 处 `random_delay(`；`RR_FIRE_MAX_TRIES/TIMEOUT/POST_CLICK_TIMEOUT`
  = `4 / 10 / 3`。
- `OtherFireNotMigratedTest`（3）：Orochi `run_alone/run_wild/run_member` + EvoZone `run_alone/run_member`
  无 `REACTION_FIRE` / 无 `*_FIRE, ..., confirm_delay`；两模块源码不含 `REACTION_FIRE`；
  Exploration `fire()` 未动（仍 `max_tries` + `Timer(10)`，无 `REACTION_FIRE` / `confirm_delay`）。

改既有：`tests/test_realm_raid_state.py` 的 `FireCharacterizationTest`（7 用例改为锁新形态：正向战斗
确认 / 有界 `wait_time` / 旧 marker 消失非 success / bounded `for` + 可达 `return False` / 无
`confirm_delay` / `random_delay(*REACTION_FIRE)`）、`LoopAndWaitBoundsTest`（`fire` 移出 `UNBOUNDED`
列表 + 新增 `fire` bounded 断言 + `wait_until_appear` 改为「恰 1 处带 `wait_time`（fire）、其余不带」）；
`tests/test_general_battle_timing.py` 的 `test_realm_raid_fire_keeps_original_timing_arguments` 改名
`test_realm_raid_fire_uses_reaction_fire_not_confirm_delay_or_legacy_api`（锁 `random_delay(*REACTION_FIRE)` +
`I_FIRE, interval=0, threshold=0.8` + partition `interval=2` + 无 `confirm_delay`/`reaction_delay`/
`CLICK_REACTION_DELAY`）。

验证：`compileall -q module tasks tests dev_tools` OK → targeted（`test_fire_reaction_fsm` +
`test_reaction_timing_batch1` + `test_base_task_confirm_click` + `test_realm_raid_state` +
`test_ryoutoppa_c_area_1_point_opt_in` + `test_general_battle_settlement` + `test_general_battle_timing` +
`test_exploration_state`）`237 OK` → 完整 `toolkit/python.exe -m unittest discover -s tests`
**`1156/1156 OK`**（`1126 → 1156`，+30，0 回归）→ `git diff --check`：本轮文件全干净；仍只命中
`tasks/Component/GeneralBattle/assets.py` + `tasks/KekkaiUtilize/assets.py` 的**既有 / 无关**尾空白 +
EOF WIP（**不清理**）。

### Level C pending

`REACTION_FIRE` 0.4~0.8 体感（过短 / 过长 / 正常）；FIRE 一次成功率 / retry 触发率 / 二次 retry 比例 /
`RR_FIRE_MAX_TRIES` 是否真触发；FIRE click → `page_battle_prepare` / `page_battle` 实际时长、
`RR_FIRE_TIMEOUT=10` 与 `RR_FIRE_POST_CLICK_TIMEOUT=3` 是否够；是否仍存在「旧 marker 消失但没进
battle」的假转换；RyouToppa `0.2~0.6 → 0.4~0.8` 是否明显影响进攻节奏。参数当前只属 PROVISIONAL，
无 Level C 证据不继续扩大。

### Git

分支 `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。未 commit / push / merge /
reset / clean / stash / checkout / restore。本轮改动：`module/reaction_profile.py`（`M`，+`REACTION_FIRE`
+ registry）；`tasks/RyouToppa/script_task.py`（`M`，FIRE delay 统一）；`tasks/RealmRaid/script_task.py`
（`M`，imports + 3 常量 + `fire()` 重写 + `_wait_fire_entered_battle`）；新增 `tests/test_fire_reaction_fsm.py`；
改 `tests/test_realm_raid_state.py` / `tests/test_general_battle_timing.py` / `tests/test_reaction_timing_batch1.py`
（锁新形态）；`docs/` 六份。既有其它 WIP（含 `*/assets.py` 尾空白、`tasks/RyouToppa/{assets,config}.py` /
`dev/click.json`）未触碰。未启动 MuMu / 游戏 / OCR。

## 2026-09-08 - RealmRaid FIRE FSM：transition / unknown 状态边界收口（三态）

### 背景

上一轮（R-R1）已解决「`I_RR_PERSON` 消失 ≠ 进入战斗」，但 `_wait_fire_entered_battle()` 里
`if not appear(I_FIRE) and not appear(I_RR_PERSON): return False` 仍有**过早失败**问题：正常页面切换
会出现「点 FIRE → 旧 marker 消失 → 过渡 / 加载 blank 帧（`I_FIRE`=F、`I_RR_PERSON`=F、`is_in_battle`=F）
→ 稍后才出 `page_battle_prepare` / `page_battle`」。此时不应被当成 FAILED / RETRY，也不应在未知
状态下重新点 `C_PARTITION_n`。本轮只修这个状态机边界，不重做上一轮实现。

### 正式 FIRE post-click 状态模型（三态，`tasks/RealmRaid/script_task.py`）

`_wait_fire_entered_battle()` 从 `-> bool` 改为 **`-> str`，区分三态、期间不点任何坐标**：

| 状态 | 判据 | 语义 / 处理 |
|---|---|---|
| **`'battle'`** | `self.is_in_battle(False)` | 已进入 GeneralBattle 可接管流程（准备 / 战斗 / 结算 / 奖励）——唯一 positive success → `fire()` `return True` |
| **`'retryable'`** | `_is_realm_raid_retryable_state()` | 明确仍处于个人突破可操作页面 → 允许下一 bounded attempt / 由调用方决定是否重开目标详情 |
| **`'timeout'`** | `Timer(RR_FIRE_POST_CLICK_TIMEOUT)` 到期前一直是 transition / unknown | 旧 marker 消失、battle 未出现 —— **既不当 success 也不当 immediate failure**，timer 内持续等 `'battle'` / `'retryable'`；用尽则进入下一 attempt |

新增纯只读 helper **`_is_realm_raid_retryable_state() -> bool`** = `appear(I_RR_PERSON) or
appear(I_FIRE) or appear(I_BACK_RED)`。单一职责、只读当前 fresh frame：**不截图 / 不点击 / 不
sleep / 不改状态**。`I_BACK_RED` = 个人突破页固定右上返回键（`check_ticket` / `_exit_matcher` 都
依赖它）；三者任一命中即「仍可操作」，都没有 = 过渡 / 未知。

### `fire()` 循环边界（partition guard）

`I_FIRE` 未就绪的分支从「`if not appear(I_FIRE): self.click(click, interval=2); continue`」改为：

```
state = self._wait_fire_entered_battle()          # 有界三态轮询，期间不点
if state == 'battle':   return True
if state == 'retryable':  self.click(click, interval=2)   # 只有明确 retryable 才点九宫格重开详情
# state == 'timeout'（transition / unknown）→ 不点任何坐标
continue
```

**长期规则**：`C_PARTITION_n` 点击**必须**有明确 retryable-state 守卫，**不能再以 `not appear(I_FIRE)`
为充分条件**（`not I_FIRE` 可能是详情未开 / 页面切换 / FIRE 加载中 / 弹窗遮挡 / 临时识别失败 /
已离开个人突破页）。过渡帧不再消耗「乱点 partition」，也不再被误判成 retry / failure。

FIRE 就绪后的 post-click 分支也从 `if self._wait_fire_entered_battle(): return True` 改为按三态
处理（`'battle'` → return True；`'retryable'` / `'timeout'` → 下一 attempt，transition-unknown 不当
immediate failure）。

### 未破坏

`REACTION_FIRE = (0.4, 0.8)`、`RR_FIRE_MAX_TRIES = 4`、`RR_FIRE_TIMEOUT = 10`、
`RR_FIRE_POST_CLICK_TIMEOUT = 3` **数值未改**；每 attempt 独立 `random_delay(*REACTION_FIRE)` →
`sleep` → fresh `screenshot` → 正向 recheck → 二次 `appear(I_FIRE)` → click 的链**未改**；`fire()`
仍是 `for attempt in range(1, RR_FIRE_MAX_TRIES+1)` + `Timer(RR_FIRE_TIMEOUT)` bounded、可达
`return False`；transition-unknown 的等待是 `_wait_fire_entered_battle` **自己的** `Timer` 有界轮询，
不会把 bounded FSM 变回无限循环。**未新增任何随机延迟**（无 `repeat_delay` / `retry_delay` /
`confirm_delay` / 额外 sleep）。`run()` caller 未改。`C_PARTITION_n` 坐标 / ROI / RuleClick /
ClickSampler / T7 / order 逻辑、`fire_again()`、GeneralBattle / Settlement V3、RyouToppa / Orochi /
EvoZone / Exploration、FrameWait / TouchSwipeModel / Fatigue —— 全未改。

### 测试

- `tests/test_fire_reaction_fsm.py` `29 → 34`（`RealmRaidFireFsmTest` +5，`_mk` harness 加
  `I_BACK_RED` 支持）：
  - `test_transition_blank_frame_then_battle_returns_true_without_extra_click`：点 FIRE 后 blank 过渡
    帧不 return False；下一帧 `is_in_battle=True` → return True，且只点 1 次 FIRE、不点 partition。
  - `test_transition_unknown_all_frames_times_out_false_no_clicks`：post-click 一直 blank →
    `'timeout'` → 下一 attempt → 最终 bounded → False；至多点 1 次 FIRE、**从不点 partition**。
  - `test_retryable_realm_raid_state_allows_next_attempt`：post-click 非战斗但 `I_BACK_RED` 在 →
    `'retryable'` → 下一 attempt → 再 reaction+click → battle → True。
  - `test_partition_clicked_only_when_retryable_state_grid_page`：FIRE 未就绪 + `I_BACK_RED` 在 →
    点 `partition[order-1]` `interval=2`。
  - `test_partition_not_clicked_in_transition_unknown` / `test_partition_not_clicked_when_only_rr_person_visible`：
    无任何 retryable marker → 绝不点 partition；`I_RR_PERSON` 在（详情已开）算 retryable、允许重开。
  - 既有 `test_old_marker_gone_without_battle_is_not_success` 加强：transition/unknown 期间也不点
    partition / FIRE。
- `tests/test_realm_raid_state.py::FireCharacterizationTest` `7 → 8`（`_mk` harness patch `Timer` /
  `sleep` / `random_delay` + 无限尾迭代器 + `I_BACK_RED` 支持）：`test_source_uses_three_way_state_and_is_bounded`
  （AST 校验 partition 点击恰 1 处且在 `state == 'retryable'` 分支内）、`test_helpers_are_read_only`
  （`_wait_fire_entered_battle` 三态字符串 + 不点击；`_is_realm_raid_retryable_state` 无
  `screenshot`/`click`/`sleep`/`Timer` + 含 `I_BACK_RED`）、`test_old_marker_gone_but_not_battle_is_not_success`
  加 `t.click.assert_not_called()`、`test_positive_battle_confirmation_returns_true_without_click` 加
  `t.click.assert_not_called()`。
- `test_reaction_timing_batch1` / `test_general_battle_timing` / `test_general_battle_settlement` /
  `test_ryoutoppa_c_area_1_point_opt_in` 未改、全绿（RyouToppa 本轮未动）。

验证：`compileall -q module tasks tests dev_tools` OK → targeted（`test_fire_reaction_fsm` +
`test_realm_raid_state` + `test_reaction_timing_batch1` + `test_general_battle_timing` +
`test_general_battle_settlement` + `test_ryoutoppa_c_area_1_point_opt_in`）`205 OK` → 完整
`toolkit/python.exe -m unittest discover -s tests` **`1162/1162 OK`**（`1156 → 1162`，+6，0 regression）→
`git diff --check`：本轮文件全干净；仍只命中 `tasks/Component/GeneralBattle/assets.py` +
`tasks/KekkaiUtilize/assets.py` 的**既有 / 无关**尾空白 + EOF WIP（**不清理**）。

### Level C pending

transition blank 帧实际持续时间；`RR_FIRE_POST_CLICK_TIMEOUT=3` 是否足够覆盖；是否频繁出现
`_is_realm_raid_retryable_state` 命中（`I_BACK_RED` 在但非战斗 = 回到九宫格页）；partition guard 是否
影响正常重开目标详情；false retry 是否明显减少。参数（三个 `RR_FIRE_*` + `REACTION_FIRE`）仍
PROVISIONAL，无 Level C 证据不放大。

### Git

分支 `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。未 commit / push / merge /
reset / clean / stash / checkout / restore。本轮改动：`tasks/RealmRaid/script_task.py`（`M`，
`fire()` 三态化 + `_wait_fire_entered_battle` `-> str` + 新增 `_is_realm_raid_retryable_state`）；
改 `tests/test_fire_reaction_fsm.py` / `tests/test_realm_raid_state.py`（`??` WIP，锁三态边界）；
`docs/` 六份。既有其它 WIP 未触碰。未启动 MuMu / 游戏 / OCR / 真机设备。

---

## 2026-09-08 - 常驻刷本 FIRE FSM 第二批（Orochi / EvoZone 单人）+ Fatigue 安全节点第一批铺开

承接三态 FIRE 边界收口。把 §4.52 的三态 FIRE Contract 铺到 Orochi / EvoZone 的单人挑战路径，
并把 `FatigueManager` 安全节点从「仅 RyouToppa」扩到 Orochi / EvoZone 单人。生产行为变化，Level A/B。
契约见 `docs/DECISIONS.md` D001 补记（FIRE 分节 增补 + Fatigue Safe Point 铺开补记）、快照见
`docs/AI_CONTEXT.md` §4.53。

### 迁移前真实 inventory（先查源码，不依赖旧报告）

- **Orochi**（`tasks/Orochi/script_task.py`）：真正点 FIRE 的只有 `run_alone`（`I_OROCHI_FIRE`，
  threshold 0.6）；`run_wild` 点 `I_OROCHI_WILD_FIRE`；`run_leader` / `run_member` 不点 FIRE（走
  `run_invite` / `wait_battle` + `run_general_battle`）。`run_alone` 内层 `while True`：
  `appear_then_click(I_OROCHI_FIRE, interval=1)` → `not appear(I_OROCHI_FIRE)` → 直接
  `run_general_battle(exit_matcher=I_OROCHI_FIRE)`。**无正向战斗确认、无 bounded、无 reaction**。
  **`I_OROCHI_WILD_FIRE` 全仓无 `RuleImage` 定义**（只有图片 `o/o_orochi_wild_fire.png`）——`run_wild`
  的 FIRE 路径会 `AttributeError`，既有断链，本轮不修。
- **EvoZone**（`tasks/EvoZone/script_task.py`）：真正点 FIRE 的只有 `run_alone`（`I_EVOZONE_FIRE`，
  threshold 0.6），内层循环与 Orochi 逐字同构；`run_leader` / `run_member` 不点 FIRE；
  `run_wild` = `logger.error('Wild mode is not implemented')`。
- **契灵（BondlingFairyland）**：`run_alone` 点 `I_BALL_FIRE`（结契按钮），结构 = 「连点直到消失，
  否则 3 次 → `raise BondlingNumberMax`（契灵存量满 500）」+ caller `run_catch` 两条独立语句
  `self.run_alone(); self.run_general_battle(...)` + `run_catch` / `run_leader` 共用 `while 1`。
  **不是单次稳定 Point FIRE → GeneralBattle**，套三态模板需业务级重构 → **PARTIAL，本轮零改动**。

### 改动

- **Orochi / EvoZone 各新增 3 个 task-local 方法 + 3 个 module 常量**（不塞 `BaseTask`，不抽公共
  FireStateMachine primitive —— D015）：
  - `_fire_{orochi,evozone}_alone() -> bool`：`click_record_clear` → `for attempt in range(1,
    *_FIRE_MAX_TRIES + 1)` 且 `Timer(*_FIRE_TIMEOUT)` 未到 → ① `screenshot` + `is_in_battle(False)`
    正向确认 → return True；② `I_*_FIRE` 未就绪 → `_wait_*_fire_state()` 三态；③ `I_*_FIRE` 就绪 →
    每 attempt 独立 `random_delay(*REACTION_FIRE)` → `sleep` → fresh `screenshot` → 再判
    `is_in_battle` → 二次 `appear(I_*_FIRE)`（消失则不点旧坐标、`continue`）→
    `appear_then_click(I_*_FIRE, interval=0)` → `_wait_*_fire_state()`；④ 用尽 → **可达 `return False`**。
  - `_wait_{orochi,evozone}_fire_state(timeout=*_FIRE_POST_CLICK_TIMEOUT) -> str`：有界 `Timer` 轮询、
    **不点任何坐标**，`'battle'`（`is_in_battle()`）/ `'retryable'`（`_is_*_challenge_retryable()`）/
    `'timeout'`（过渡 / 未知帧 —— 既不当 success 也不当 immediate failure）。
  - `_is_{orochi,evozone}_challenge_retryable() -> bool`：纯只读当前帧（不截图 / 不点击 / 不 sleep /
    不改状态）= `appear(I_*_FIRE)`。
  - 常量：`{OROCHI,EVOZONE}_FIRE_MAX_TRIES = 4` / `*_FIRE_TIMEOUT = 10` / `*_FIRE_POST_CLICK_TIMEOUT = 3`
    （对齐 RealmRaid `RR_FIRE_*`，engineering baseline 非 Level C）。
- **caller**：`run_alone` 内层 `while True` → `if self._fire_*_alone(): run_general_battle(...);
  try_fatigue_break(...)`。FIRE 返回 False 不进 `run_general_battle`，回外层 `while 1` 顶
  `screenshot` + `is_in_orochi` / `is_in_evozone` 重新判定。
- **Fatigue 安全节点第一批**：`run_alone` 循环前 `begin_fatigue_task('Orochi' / 'EvoZone')` +
  `deadline = self.start_time + self.limit_time`；**一场完整战斗结束、`run_general_battle` 已回到
  稳定挑战页之后** `try_fatigue_break(safe=True, repeat_completed=True, deadline=deadline)`。休息结束
  回外层循环顶先 `screenshot` + `is_in_orochi` / `is_in_evozone` fresh revalidate。
  `run_leader` / `run_member` / `run_wild` **不接**（邀请 / 房间 / 队友同步）。
- **导入**：Orochi / EvoZone 各加 `from module.base.timer import Timer` /
  `from module.base.utils.random import random_delay` / `REACTION_FIRE`。

### 未改

`appear_then_click` primitive、`REACTION_FIRE`=(0.4,0.8) 及 §4.51 6 组 profile、RealmRaid `fire()` /
`RR_FIRE_*` / `C_PARTITION_n` / T7、RyouToppa `attack_area` / fatigue node / 区域 `random_delay(1.0,3.0)`、
GeneralBattle（Settlement V3 / `prepare_click_timer` / `settlement_click_timer` /
`_advance_generic_result`）、Exploration `fire()`、契灵全部代码、`FatigueManager` 本体、
`begin_fatigue_task` / `try_fatigue_break` 签名、FrameWait、TouchSwipeModel。Orochi `run_wild` 的
`I_OROCHI_WILD_FIRE` 断链本轮不修。

### 测试

- **新增 `tests/test_second_batch_fire_fsm.py`（27）**：`REACTION_FIRE` / batch1 profile / 三个
  `*_FIRE_*` 常量不变；`_mk` harness（patch `<mod>.Timer` / `sleep` / `random_delay`，`_FakeTimer`
  budget + `_seq` 无限尾）驱动 Orochi + EvoZone（`subTest`）——正向战斗 return True 无多余点击 /
  reaction 期间 FIRE 消失不点旧坐标 / transition blank → battle → True 不多点 / transition unknown
  全程 → bounded False 不点 / retryable → 下一 attempt 再 battle / bounded by MAX_TRIES /
  timeout timer 立即 False / prologue `click_record_clear` / 每 attempt 独立采样 (0.4,0.8)；
  源码形态（三态字符串 / 无 `while True` / `range(1, *_FIRE_MAX_TRIES+1)` / `Timer(*_FIRE_TIMEOUT)` /
  恰 1 处 `random_delay` / 无 `confirm_delay` / `REACTION_FAST` / 可达 `return False` / post-click 走
  `_wait_*`）；`_wait_*` 三态无点击无 sleep 无 random_delay、`_is_*_challenge_retryable` 纯只读；
  caller AST（`run_general_battle` + `try_fatigue_break` 都在 `if self._fire_*_alone():` 体内、
  `run_general_battle` 全函数只 1 处非裸调用）；Fatigue 只在 `run_alone` / 在 `run_general_battle`
  之后 / `begin_fatigue_task` 在 FIRE 循环之前 / `_fire_*` / `_wait_*` / `_is_*` 零 fatigue /
  leader·member·wild 零 fatigue；契灵 PARTIAL（模块不 import `REACTION_FIRE`、`run_alone` 结构 +
  `BondlingNumberMax` 路径不变、无 fatigue）；范围外 RealmRaid / RyouToppa / Exploration FIRE 未改。
- 改 `tests/test_fire_reaction_fsm.py::OtherFireNotMigratedTest`：
  `test_orochi_evozone_fire_have_no_reaction_fire_or_confirm_delay` →
  `test_orochi_evozone_non_alone_paths_have_no_reaction_fire_or_confirm_delay`（缩到
  `run_wild` / `run_member` / `run_leader`）；`test_reaction_profile_not_imported_by_orochi_evozone_for_fire`
  → `test_bondling_ball_fire_not_migrated`（契灵未迁）。净 0（-2 +2）；模块 docstring 更新。

验证：`compileall -q module tasks tests dev_tools` OK → targeted（`test_second_batch_fire_fsm` +
`test_fire_reaction_fsm` + `test_realm_raid_state` + `test_reaction_timing_batch1` +
`test_general_battle_timing` + `test_general_battle_settlement` + `test_ryoutoppa_c_area_1_point_opt_in`
+ `test_fatigue`）`325 OK` → 完整 `toolkit/python.exe -m unittest discover -s tests`
**`1189/1189 OK`**（`1162 → 1189`，+27，0 regression）→ `git diff --check`：本轮文件全干净；仍只命中
`tasks/Component/GeneralBattle/assets.py` + `tasks/KekkaiUtilize/assets.py` 的**既有 / 无关**尾空白 +
EOF WIP（**不清理**）。

### Level C pending

`REACTION_FIRE` 在 Orochi / EvoZone 单人的体感、FIRE 一次成功率 / retry 触发率、transition blank 帧
实际时长、`*_FIRE_TIMEOUT` / `*_FIRE_POST_CLICK_TIMEOUT` 是否够、`_is_*_challenge_retryable` 是否过宽
（`I_*_FIRE` threshold 0.6 假阳性）、**Fatigue 安全节点是否真正安全**（休息后页面是否仍保持挑战页 /
是否漏掉一场 / 组队模式确未被误插 idle / `deadline` 截断正常）、fatigue 后 fresh revalidate 是否足够、
Orochi `run_wild` 断链修复。参数（三个 `*_FIRE_*` + `REACTION_FIRE`）仍 PROVISIONAL，无 Level C 证据
不放大。

### ROADMAP 待完成任务清单固化

`docs/ROADMAP.md` 新增 **P0** 段（已确定的后续业务改造 / 需真机窗口）：FIRE FSM 收口进度（RyouToppa /
RealmRaid / Orochi / EvoZone 已完成，契灵 PARTIAL、Orochi wild 断链、活动副本 pending）；Fatigue
安全节点铺开（RyouToppa / Orochi / EvoZone 已接，RealmRaid / Exploration / 活动待接）；RealmRaid
目标选择 / 退四策略改造（九宫格固定 1→9、目标级 pacing 1.0~2.5、普通失败直接刷新、最后目标退四、
退四前解锁、失败页再次挑战）；Exploration 改造（Boss 后直接退出、不逐个领宝箱、章节列表 FrameWait、
Fatigue）；组队入口改造（庭院直接组队）；结界卡精简（不领寄养奖励 / 不检查满级式神）；活动体力 /
门票挑战 FIRE + Fatigue（12 项）；GeneralBattle repeated / settlement micro-timing。

### Git

分支 `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。未 commit / push / merge /
reset / clean / stash / checkout / restore。本轮改动：`tasks/Orochi/script_task.py` /
`tasks/EvoZone/script_task.py`（`M`，`_fire_*_alone` 三态 + `*_FIRE_*` 常量 + `run_alone`
FIRE 守卫 + Fatigue 安全节点）；`tests/test_second_batch_fire_fsm.py`（新，`??` WIP）；改
`tests/test_fire_reaction_fsm.py`（`??` WIP）；`docs/` 六份。既有其它 WIP（`tasks/Component/GeneralBattle/assets.py`
/ `tasks/KekkaiUtilize/assets.py` 尾空白等）未触碰。未启动 MuMu / 游戏 / OCR / 真机设备。

---

## 2026-09-08 - 通用组队挑战按钮 Reaction Timing 补齐（`GeneralInvite.click_fire`）

承接 §4.53。Orochi / EvoZone 上一轮只迁了 `run_alone`，但**组队 / 房主真正点「挑战 / 开始战斗」
按钮不是各自 task 点的，而是统一走 `GeneralInvite.click_fire()`**。本轮只在这个公共 challenge
click owner 上补一次 Action reaction。生产行为变化，Level A/B。契约见 `docs/DECISIONS.md` D001
补记 FIRE 分节 增补（组队 challenge owner + Action Owner vs Passive Waiter），快照见
`docs/AI_CONTEXT.md` §4.54。

### 迁移前真实调用链（READ ONLY inventory）

- `Orochi.run_leader` / `EvoZone.run_leader`（首次 `is_first=True` + 后续，共两处）→
  `self.run_invite(config=…)`（`GeneralInvite`）→ `ensure_enter` → `while 1`：invite cadence
  （`Timer(20)` 首次每 20s 补邀 / `Timer(30)` 后续）+ `timer_wait`（`config.wait_time`）+
  emoji（`timer_emoji`）→ **`if self.room_check_can_fire(config): self.click_fire(); return True`**
  → caller `run_general_battle(...)`。
- `Orochi.run_member` / `EvoZone.run_member` → `check_then_accept()`（接受邀请 / 秒开检测）+
  `wait_battle()`（`Timer(wait_second)` + emoji，等队长开战）→ `run_general_battle(...)`。
  **不点 challenge、不 `click_fire`**。
- `Orochi.run_wild` → 自己点 `I_OROCHI_WILD_FIRE`（**全仓无 `RuleImage` 定义、既有断链**，§4.53），
  **不经 `click_fire`**。`EvoZone.run_wild` = `logger.error('Wild mode is not implemented')`。
- `Orochi.run_alone` / `EvoZone.run_alone` → `_fire_orochi_alone` / `_fire_evozone_alone`（§4.53），
  **不经 `click_fire`**。
- **`GeneralInvite.click_fire()` 旧实现**：`while 1: screenshot → if not is_in_room(False): break
  → appear_then_click(I_FIRE, interval=1, threshold=0.7) / appear_then_click(I_FIRE_SEA, ...)`。
  只有 `interval=1` throttle + `threshold=0.7`，**无 reaction / confirm_delay / random_delay /
  sleep / 正向 `is_in_battle` 确认**；「进入战斗」= `not is_in_room(False)`（房间 UI 消失）。
  `I_FIRE` = `RuleImage(roi_front=(1179,602,81,74), threshold=0.8, gi_fire.png)`，稳定右下角
  「开始战斗」按钮。
- **公共 owner 认定**：`click_fire` 被 `run_invite`（经 `room_check_can_fire` 门槛）+
  ExperienceYoukai / GoldYoukai / Hunt / Tako 直接调用；`run_invite` 被 BondlingFairyland /
  EternitySea / EvoZone / Exploration / FallenSun / Orochi / OtherWorldTwilight 的 `run_leader`
  调用。**是全仓组队 / 房间 battle-entry 的唯一公共 click owner**，无 task 覆写。

### 改动（只改 `tasks/Component/GeneralInvite/general_invite.py` 的 `click_fire()`）

`while 1: screenshot → if not is_in_room(False): break →` 识别 `I_FIRE`（优先）/ `I_FIRE_SEA`
→ `target` → **每 attempt 独立 `random_delay(*REACTION_FIRE)` → `sleep(fire_delay)` → fresh
`screenshot` → 二次确认**：① `not is_in_room(False)`（reaction 期间已离开房间 / 战斗开始）→
`break`、不点旧坐标；② `not appear(target, 0.7)`（按钮消失但仍在房间）→ `continue` 回循环顶重判；
③ `target` 仍在 → `appear_then_click(target, interval=1, threshold=0.7)`。imports 加
`from module.base.utils.random import random_delay` + `from module.reaction_profile import
REACTION_FIRE`。

- `is_in_room` 循环边界（配合上层 `run_invite` 的 `timer_wait` / `Timer(20/30)` / `timer_emoji`）、
  `interval=1` click throttle、`threshold=0.7`、minitouch dwell **不变**。
- **不叠 `confirm_delay` / 第二套 reaction**；`click_fire` 代码体恰 1 处 `random_delay(` + 1 处
  `sleep(`。
- **不接 Fatigue**（组队 challenge 不是疲劳安全节点 —— 与 Fatigue Safe Point 铺开补记「不接
  邀请 / 房间路径」一致）。
- 正向战斗确认仍在下游 `run_general_battle`，**未改**邀请 / 房间 / 战斗状态链（§13 的「现有链
  足够、只补 Action Reaction」——GeneralInvite 已有 `room_check_can_fire` gate + `run_invite` 的
  `timer_wait` bounded + `wait_battle` 的房间销毁检测 + 下游 `run_general_battle` 正向确认）。
  `click_fire` 结构上属 `GeneralInvite`（`MysteryShop` 混入它但无 `GeneralBattle`），故不在此处
  引 `is_in_battle()`，用既有 `is_in_room` 房间态出口。

### Action Owner vs Passive Waiter（长期原则，写入 D001 补记 + ARCHITECTURE）

battle-entry click 的 reaction 不按「单人 / 组队」区分，而按**谁真正点击**：Action Owner（本机
真实识别并点「挑战 / 开始战斗」）→ `REACTION_FIRE` + fresh reconfirm + no stale click；Passive
Waiter（`wait_battle` / `check_then_accept` / member / invitee）→ 无 reaction click。「一个真实
action = 一个 timing owner」——同一个 `click_fire` 被多副本复用时只加一次，不在各 task 重复加。

### 自动继承的 consumer（11）

经 `run_invite`：BondlingFairyland / EternitySea / EvoZone / Exploration / FallenSun / Orochi /
OtherWorldTwilight。直接调 `click_fire`：ExperienceYoukai / GoldYoukai / Hunt / Tako。**本轮不改
这些 task 的其它逻辑。**

### 未改

`REACTION_FIRE`=(0.4,0.8) 及 6 组 profile、`appear_then_click` primitive、Orochi / EvoZone
`_fire_*_alone`（§4.53）、RealmRaid `fire()` / RyouToppa `attack_area`、GeneralBattle（Settlement
V3 / FSM）、`run_invite` / `room_check_can_fire` / `invite_friends` / `wait_battle` /
`check_then_accept` / `check_and_invite` / `invite_again` / `exit_room` 的状态机、`FatigueManager` /
Fatigue 布局、T7 / FrameWait / TouchSwipeModel、Navigation、Orochi `run_wild` 断链、契灵业务、
RealmRaid / RyouToppa（不纳入公共组队 challenge reaction）。

### 测试

**新增 `tests/test_general_invite_challenge_reaction.py`（23）**：`ReactionFireProfileTest`（2：
`REACTION_FIRE`(0.4,0.8) 不变 + `click_fire` import/使用 `random_delay(*REACTION_FIRE)`）、
`ClickFireReactionBehaviorTest`（8，`_FireHarness` patch `gi.sleep` / `gi.random_delay`：reaction
后 fresh screenshot → click（`interval=1, threshold=0.7`）/ reaction 前后 ≥2 次 screenshot /
reaction 期间按钮消失（仍在房间）不点 stale / reaction 后已离开房间不点、break / 顶端非房间不
reaction / 无按钮不 reaction / `I_FIRE_SEA` 变体同样走 reaction 且点 `I_FIRE_SEA` / 每 attempt
独立采样 (0.4,0.8)）、`ClickFireTimingOwnerTest`（3，去 docstring 扫代码体：`click_fire` 恰 1
`random_delay(` + 1 `sleep(`、无 `confirm_delay` / `reaction_delay` / `CLICK_REACTION_DELAY`；
`run_invite` 的 `Timer(20)` / `Timer(30)` / `timer_wait` State Wait 保留、challenge 仍经
`room_check_can_fire` → `click_fire`；模块无 `def reaction_delay` / `CLICK_REACTION_DELAY`）、
`ChallengeActionOwnerTest`（3：`wait_battle` / `check_then_accept` / `check_and_invite` /
`invite_again` 无 `click_fire` / 无 `REACTION_FIRE`）、`OrochiEvoZoneCompatTest`（3：`run_alone`
的 `_fire_*_alone` 恰 1 `random_delay(*REACTION_FIRE)` / 不经 `click_fire` / 不叠加；`run_leader`
经 `run_invite`、不自己写 reaction、不直接 `click_fire`；`run_member` 无 challenge reaction）、
`FatigueDoesNotSpreadToInviteTest`（2：`general_invite.py` 模块无 `begin_fatigue_task` /
`try_fatigue_break` / `FatigueManager` / `fatigue_manager`；challenge / wait 路径代码体无
`fatigue`）、`OtherConsumersInheritTest`（2：7 个 `run_invite` task + 4 个直接 task 都不覆写
`def click_fire`、直接 task 不自己写 `random_delay(*REACTION_FIRE)`）。

既有 `tests/test_t7_5_stage2.py::GeneralInviteMigrationTest` 未改、全绿（只查
`_random_point_in_area` 删除 / `_detect_select` 用 `sample_target`；新 import `random_delay` ≠
`random_point_in_roi`，不误命中）。

验证顺序（§22）：`test_general_invite_challenge_reaction` + `test_t7_5_stage2` +
`test_second_batch_fire_fsm` + `test_fire_reaction_fsm` + `test_realm_raid_state` +
`test_reaction_timing_batch1` + `test_fatigue` + `test_general_battle_timing` +
`test_general_battle_settlement` = `347 OK` → `compileall -q module tasks tests dev_tools` OK →
完整 `toolkit/python.exe -m unittest discover -s tests` **`1212/1212 OK`**（`1189 → 1212`，+23，
0 regression）→ `git diff --check`：`tasks/Component/GeneralInvite/general_invite.py` 干净；仍只
命中 `tasks/Component/GeneralBattle/assets.py` + `tasks/KekkaiUtilize/assets.py` 的**既有 /
无关**尾空白 + EOF WIP（**不清理**）。

### Level C pending

组队挑战按钮 0.4~0.8 体感；leader challenge 是否漏点；reaction 后按钮消失的实际频率；challenge
click → battle marker 过渡时间；member 是否完全不受影响；多副本共用 `click_fire` 是否一致。

### ROADMAP 待完成任务清单同步

`docs/ROADMAP.md` 新增「### FIRE / Reaction Timing 覆盖维度」子段（长期口径从「单人 FIRE
consumer」修正为三维度：① 单人 challenge / FIRE owner ② 组队 leader / host challenge owner
（= `click_fire`）③ member / passive wait path（不加））。P0 补：RealmRaid 退四「再次挑战」点击前
`REACTION_FIRE` + fresh confirm + 退四流程最终失败也统一刷新 + RealmRaid Fatigue 待主循环定型；
新增「### 返回庭院优化」（直达按钮优先 + fresh confirm + 旧 navigation fallback）、「### Navigation
READ ONLY 审查」（突破 → 式神录 异常点击链）、结界卡「静默窗口 / cooldown」（00:00~07:00 静默、
07:00 + 5~30min jitter 恢复、完成后 5~30min 随机 cooldown，均由 scheduler `next_run` 实现、不用
任务内部 blocking sleep）。此前 P0 各条（RealmRaid 九宫格固定 / 目标 pacing 1.0~2.5 / 普通失败
直接刷新 / 退四前解锁；Exploration Boss 后退出 / 不逐个领宝箱 / chapter swipe FrameWait；组队入口；
活动体力·门票 FIRE + Fatigue；GeneralBattle repeated / settlement timing；剩余 Fatigue 铺开）
**全部保留**。

### Git

分支 `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。未 commit / push / merge /
reset / clean / stash / checkout / restore。本轮改动：`tasks/Component/GeneralInvite/general_invite.py`
（`M`，`click_fire()` 加 `REACTION_FIRE` reaction + fresh reconfirm + 2 个 import）；
`tests/test_general_invite_challenge_reaction.py`（新，`??` WIP）；`docs/` 六份。既有其它 WIP
（`tasks/Component/GeneralBattle/assets.py` / `tasks/KekkaiUtilize/assets.py` 尾空白等）未触碰。
未启动 MuMu / 游戏 / OCR / 真机设备。

---

## 2026-09-08 - `GeneralInvite.click_fire()` Battle Entry post-click 状态机 / bounded FSM 收口

承接 §4.54（只补 reaction）。本轮补 post-click **state contract**（两件事分开记，见
`docs/ROADMAP.md`「FIRE / Reaction Timing 覆盖维度」）。生产行为变化，Level A/B。契约见
`docs/DECISIONS.md` D001 补记 FIRE 分节 增补（GeneralInvite battle-entry FSM），快照见
`docs/AI_CONTEXT.md` §4.55。

### 修改前两个结构性问题

1. **旧 room 状态消失仍被当成成功**：`click_fire()` 核心是 `while 1: screenshot → if not
   is_in_room(False): break` → `run_invite` `return True` → caller `run_general_battle()`。
   `not is_in_room(False)` 隐含等价 battle started / success，但它也可能是房间解散 / 队长离开 /
   页面 loading / overlay / room marker 临时识别失败。
2. **`click_fire()` 自身无界**：`click_fire()` 是 `while 1`；`run_invite` 的 `timer_wait` 是同步
   调用进入 `click_fire()` 之前的整轮预算，进入后不能主动打断内部 `while`。`is_in_room=True` 且
   challenge 一直识别不到 / 点不掉时理论上可无限等。

### READ ONLY inventory（先查真实继承 / 调用链）

- `class GeneralInvite(BaseTask, GeneralInviteAssets)` —— 自身基类**不含** `is_in_battle()`。
- **`click_fire()` 的 11 个 consumer MRO 里全部带 `GeneralBattle`**：7 个经 `run_invite`
  （BondlingFairyland / EternitySea / EvoZone / Exploration / FallenSun / Orochi /
  OtherWorldTwilight —— Exploration 经 `BaseExploration(GameUi, GeneralBattle, GeneralRoom,
  GeneralInvite, ...)`）；4 个直接调 `self.click_fire()`（ExperienceYoukai / GoldYoukai / Hunt /
  Tako）。
- `general_battle.py` **不 import** `general_invite.py`（无循环依赖）。
- 唯一 `GeneralInvite`-without-`GeneralBattle` 的类 = `MysteryShop(FriendshipPoints,
  MysteryShopAssets, GeneralInvite)` —— **不调** `click_fire` / `run_invite`（只用友邀选择 helper）。
- `GeneralInvite` 已 `import GeneralBattleAssets`（`check_then_accept` 用 `I_EXIT` 判秒开）+
  `GameUiAssets`（`wait_battle` 用 `I_CHECK_MAIN` / `I_CHECK_EXPLORATION` 判 room destroyed）。
- `run_invite` 当前：`while 1` 里 `if room_check_can_fire(config): self.click_fire(); return True`
  —— `click_fire` 后**无条件** `return True`；返回 `False` 仅在 `timer_wait.reached()` / `I_MATCHING`
  / `ensure_enter` 失败。各 caller 对 `False` 已有 `else: 邀请失败退出任务` / Exploration
  `raise InviteFailedException`。
- 4 个直接 caller：ExperienceYoukai / GoldYoukai / Tako = `self.click_fire(); (count += 1;)
  self.run_general_battle(); break`（无条件交接）；Hunt `netherworld` = `self.click_fire(); break`
  → 循环外 `self.run_general_battle(...)`（无条件）。`click_fire` 旧返回 `None`，4 个 caller 都忽略。
- `wait_battle` 已有房间失败判据：`GameUiAssets.I_CHECK_MAIN` / `I_CHECK_EXPLORATION`（两帧 →
  'Room destroyed'）、`I_FIRE` / `I_FIRE_SEA`（自己变队长 → 'Leader run away'）、`timer_wait`。

### placement 评估 → 方案 A

- **方案 A（GeneralInvite 内部拥有 battle verify + marker 兜底）—— 采用**：11 个 consumer MRO 全带
  `GeneralBattle` → `self.is_in_battle(False)` 对所有真实 caller resolve；无循环依赖；`MysteryShop`
  不调 `click_fire` 结构上安全。新增 `_battle_entry_positive()` = `callable(getattr(self,
  'is_in_battle', None))` → `self.is_in_battle(False)`，否则兜底 `appear(GeneralBattleAssets.
  I_BATTLE_INFO / I_PREPARE_HIGHLIGHT / I_EXIT)`（复用 `is_in_battle` 用的同一批 asset，不新造
  detector）。
- **方案 B（callback / capability 注入）—— 否**：`click_fire(battle_check=...)` 改 11 consumer +
  `run_invite` 签名，过度侵入。
- **方案 C（positive verify 留上层）—— 否**：caller 拿不到 `click_fire` 内部 while 的 success
  误判，改不了「旧 room 状态消失即成功」的根因。

### 改动

**`tasks/Component/GeneralInvite/general_invite.py`（唯一 FSM 改动文件）**：

- module 常量（**PROVISIONAL / Level C 待标定**）：`GI_FIRE_MAX_TRIES = 4`（对齐 RealmRaid /
  Orochi / EvoZone）、`GI_FIRE_TIMEOUT = 15`（组队进战斗比个人突破慢——队友加载 / 队长开战同步；
  `run_invite` 的 `timer_wait` / `Timer(20/30)` 都不 bound「按开始→战斗加载」窗口）、
  `GI_FIRE_POST_CLICK_TIMEOUT = 4`（略宽于 RealmRaid 的 3）。
- 新增 4 个只读 helper：
  - `_battle_entry_positive() -> bool`：见上（优先 `is_in_battle` + marker 兜底）。
  - `_room_entry_failed() -> bool` = `appear(self.I_MATCHING) or appear(GameUiAssets.I_CHECK_MAIN)
    or appear(GameUiAssets.I_CHECK_EXPLORATION)`。「队长跑路」在 `click_fire` 语境不适用（本机就是
    房主，`I_FIRE` 可见是正常待点）。
  - `_classify_room_entry_state() -> str`：优先级 `battle` > `room_failed` > `retryable`
    （`is_in_room(False)`）> `unknown`。
  - `_wait_room_entry_state(timeout=GI_FIRE_POST_CLICK_TIMEOUT) -> str`：有界 `Timer` 轮询、**不点
    坐标**，`'battle'` / `'room_failed'` / `'retryable'`（出现决定性状态即返回）/ `'timeout'`
    （整段一直 `'unknown'` —— 既不当 success 也不当 immediate failure）。
- **`click_fire()` 从 `while 1` + `return None` → bounded 四态 transaction，`-> str`**
  （`'battle'` / `'room_failed'` / `'timeout'`）：`overall_timer = Timer(GI_FIRE_TIMEOUT)` +
  `for attempt in range(1, GI_FIRE_MAX_TRIES + 1)` —— 分类：`'battle'` return / `'room_failed'`
  return（不点）/ `'unknown'` → 有界 `_wait_room_entry_state`（不点）→ battle/room_failed 返回，
  retryable/timeout → 下一 attempt / `'retryable'` → 识别 `I_FIRE`（优先）/ `I_FIRE_SEA` → 每
  attempt 独立 `random_delay(*REACTION_FIRE)` → `sleep` → fresh `screenshot` → 重新分类（battle/
  room_failed 立即返回；离开 retryable / `not appear(target, 0.7)` → 不点旧坐标、下一 attempt）→
  `appear_then_click(target, interval=1, threshold=0.7)` → `_wait_room_entry_state` → battle/
  room_failed 返回 / 其它 → 下一 attempt。用尽 → `return 'timeout'`。**无 `while 1`。**
- **`run_invite` caller guard**：`if room_check_can_fire(config): self.click_fire(); return True`
  → `fire_result = self.click_fire(); if fire_result == 'battle': return True` else
  `logger.warning(...); return False`。

**4 个直接 caller（最小 guard，不改业务策略）**：

- `tasks/ExperienceYoukai/script_task.py` / `tasks/GoldYoukai/script_task.py`：两处
  `self.click_fire(); count += 1; self.run_general_battle(); break` →
  `if self.click_fire() == 'battle': count += 1; self.run_general_battle()` + `break`（保留）。
- `tasks/Tako/script_task.py`：`self.click_fire(); self.run_general_battle(); break` →
  `if self.click_fire() == 'battle': self.run_general_battle()` + `break`。
- `tasks/Hunt/script_task.py` `netherworld`：`run_general_battle` 在循环外 →
  `battle_entered = self.click_fire() == 'battle'` + 循环外 `if not battle_entered: return`。

### 未改

`REACTION_FIRE`=(0.4,0.8) / 每 attempt 独立采样 / fresh reconfirm / no stale click / 无 timing
stack、`appear_then_click` primitive、`run_invite` 的 invite cadence（`Timer(20/30)` / `timer_wait`
/ emoji）/ `invite_friends` / `room_check_can_fire` / `check_then_accept` / `check_and_invite` /
`invite_again` / `wait_battle` / `exit_room`、member / passive path 无 reaction、Orochi / EvoZone
`_fire_*_alone`、RealmRaid / RyouToppa FIRE、GeneralBattle（Settlement V3 / FSM）、Fatigue
（`click_fire` / `_classify_*` / `_wait_*` / `run_invite` / wait 路径无 fatigue token）、T7 /
FrameWait / TouchSwipeModel、Navigation、Kekkai、契灵业务。

### 测试

`tests/test_general_invite_challenge_reaction.py` `23 → 41`：
- **加 `_FakeTimer` patch `gi.Timer`**——之前只 patch `sleep` / `random_delay`，新 `click_fire`
  用 `Timer` 重，超时路径跑真墙钟（本轮曾达 **113s**）→ 现 **0.3s**。
- `ClickFireSourceShapeTest`（10）：无 `while 1` / `while True` + `for attempt in range(1,
  GI_FIRE_MAX_TRIES + 1)` + `Timer(GI_FIRE_TIMEOUT)`；AST 校验 `return` 常量恰 `{'battle',
  'room_failed', 'timeout'}`；4 个 helper 存在 + classify 含四态字符串；`_wait_*` 与 3 个 classify
  helper 只读（无 screenshot / click / sleep / random_delay，`_wait_*` 只有一个 `Timer`）；
  `_room_entry_failed` 复用 `I_MATCHING` / `GameUiAssets.I_CHECK_MAIN` / `I_CHECK_EXPLORATION`；
  `_battle_entry_positive` 优先 `getattr(self, 'is_in_battle', None)` + `GeneralBattleAssets`
  marker 兜底；reaction → fresh screenshot → reconfirm 顺序；恰 1 `random_delay(` + 1 `sleep(`、
  无 `confirm_delay` / `reaction_delay` / `CLICK_REACTION_DELAY`；`appear_then_click(target,
  interval=1, threshold=0.7)`。
- `ClickFireFsmBehaviorTest`（15，`_CF` harness 按帧序列喂状态）：正向 battle at top → `'battle'`
  无点击；reaction → click → battle → `'battle'`（click 1 次、`(I_FIRE,) {'interval':1,
  'threshold':0.7}`）；**「不在房间」+ 无 battle marker + 无 failure marker → `'timeout'`，不当
  success，0 点击**；transition unknown → battle → `'battle'` 无点击；room_failed（庭院 / 匹配 /
  探索）→ 立即 `'room_failed'` 不点；retryable 多 attempt 每次独立采样 `(0.4,0.8)`；按钮 reaction
  期间消失 → 不点 stale → `'timeout'`；离开 retryable（→ room_failed）→ 不点 stale；bounded by
  `GI_FIRE_MAX_TRIES` → `'timeout'`；`_FakeTimer.budget=0` → 立即 `'timeout'`、0 点击、0 截图；
  `I_FIRE_SEA` 变体走 reaction + click `I_FIRE_SEA`；`_battle_entry_positive` 兜底路径（无
  `is_in_battle` → 看 `GeneralBattleAssets.I_EXIT`）。
- `RunInviteGuardTest`（2）：`fire_result = self.click_fire()` + `if fire_result == 'battle':
  return True` + `return False`；旧无条件 `self.click_fire()\n ... return True` 已删。
- `DirectCallerGuardTest`（2）：ExperienceYoukai / GoldYoukai / Tako `if self.click_fire() ==
  'battle':`；Hunt `battle_entered = self.click_fire() == 'battle'` + `if not battle_entered:` 在
  `run_general_battle` 之前。
- `ProfileAndConstantsTest`（3）/ `ChallengeActionOwnerTest`（2）/ `OrochiEvoZoneCompatTest`（3）/
  `FatigueDoesNotSpreadToInviteTest`（2）/ `ConsumerCompatibilityTest`（3，含
  `test_all_click_fire_consumers_have_general_battle_in_mro`）。

验证顺序（§29）：`test_general_invite_challenge_reaction`（41）+ `test_second_batch_fire_fsm` +
`test_fire_reaction_fsm` + `test_realm_raid_state` + `test_reaction_timing_batch1` +
`test_fatigue` + `test_general_battle_timing` + `test_general_battle_settlement` +
`test_t7_5_stage2` + `test_exploration_state` = `398 OK` → `compileall -q module tasks tests
dev_tools` OK → 完整 `toolkit/python.exe -m unittest discover -s tests` **`1230/1230 OK`**
（`1212 → 1230`，+18，0 regression）→ `git diff --check`：5 个改动文件全干净；仍只命中
`tasks/Component/GeneralBattle/assets.py` + `tasks/KekkaiUtilize/assets.py` 的**既有 / 无关**尾
空白 + EOF WIP（**不清理**）。

### Level C pending

challenge click → battle positive marker 实际时间；room marker 消失到 battle marker 出现的 blank
duration；retryable room 实际命中率；room destroyed / leader gone 真实 marker 是否够；
`GI_FIRE_TIMEOUT=15` / `GI_FIRE_POST_CLICK_TIMEOUT=4` / `GI_FIRE_MAX_TRIES=4` 是否合理（全
PROVISIONAL）；11 consumer 行为差异；`run_invite` 返回 `False` 更频繁是否导致任务过早退出。

### 公共 Battle Entry primitive 评估

现有 4 个真实同形态 consumer：RealmRaid `fire()`（三态 str + bool）、Orochi
`_fire_orochi_alone` / EvoZone `_fire_evozone_alone`（三态 str + bool）、`GeneralInvite.click_fire()`
（四态 str）。共同内核：`overall Timer` + `for attempt in range(max_tries)` + 只读 `_classify` /
`_wait` helper（battle 正向确认 + retryable + transition-unknown [+ failed]）+ 每 attempt 独立
`random_delay(*REACTION_FIRE)` + fresh reconfirm + no stale click + caller guard。**形态已趋收敛**
（约达 D015 §17 说的「多个真实 consumer 收口后再评估」门槛），但差异仍在：RealmRaid 有
`C_PARTITION_n` 守卫、RyouToppa `attack_area` 是 4 态 + `AreaAttackResult` enum + 区域 pacing、
`click_fire` 多一个 ROOM_FAILED 态且 battle 判据是注入式（`_battle_entry_positive` getattr）。
**建议**：下一轮做活动副本 FIRE 时若第 5、6 个 consumer 仍同形态，再对着 4~6 个真实消费者抽一个
接受 `(classify_helpers, click_action, constants)` 注入的薄 helper（≈15~25 行，照 D015 §17 API
proposal）。**本轮只评估，不抽**（未经用户同意不重构成全局 primitive）。

### ROADMAP 待完成任务清单同步

`docs/ROADMAP.md`「FIRE / Reaction Timing 覆盖维度」子段口径修正为「reaction 与 post-click state
contract 是两件事，分别检查」；维度 2（组队 leader / host challenge owner = `click_fire`）标注
§4.54 reaction + §4.55 bounded 四态 FSM 分别完成；「FIRE FSM 收口进度」`click_fire` 从「简化版：
无三态 FSM 重写」更新为「四态版（含 ROOM_FAILED）」；Level C 区 `*_FIRE 系列` 条补 §4.55 的
`GI_FIRE_*` PROVISIONAL + blank duration / retryable 命中率 / `run_invite` False 过早退出等观察点。
**此前 P0 各条全部保留**（RealmRaid 九宫格固定 / 目标 pacing 1.0~2.5 / 普通失败刷新 / 退四前解锁 /
退四「再次挑战」reaction / 退四最终失败刷新 / RealmRaid Fatigue；Exploration Boss 后退出 / 不逐个
领宝箱 / chapter swipe FrameWait / Fatigue；庭院直接组队入口；结界卡不领奖励 / 不检查满级式神 +
00:00~07:00 静默窗口 + 07:00 + 5~30min jitter + 完成后 5~30min cooldown（scheduler next_run）；
返回庭院短路径；Navigation「突破 → 式神录」READ ONLY 审查；活动体力 / 门票 FIRE + Fatigue；
GeneralBattle repeated / settlement timing）。

### Git

分支 `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。未 commit / push / merge /
reset / clean / stash / checkout / restore。本轮改动：`tasks/Component/GeneralInvite/general_invite.py`
（`M`，`click_fire()` → bounded 四态 FSM + `_battle_entry_positive` / `_room_entry_failed` /
`_classify_room_entry_state` / `_wait_room_entry_state` + `GI_FIRE_*` 常量 + `run_invite` guard）；
`tasks/{ExperienceYoukai,GoldYoukai,Hunt,Tako}/script_task.py`（`M`，直接 caller `== 'battle'`
guard）；`tests/test_general_invite_challenge_reaction.py`（`23 → 41` 重写，`??` WIP）；`docs/` 六份。
既有其它 WIP（`tasks/Component/GeneralBattle/assets.py` / `tasks/KekkaiUtilize/assets.py` 尾空白等）
未触碰。未启动 MuMu / 游戏 / OCR / 真机设备。

---

## 2026-09-08 - GeneralInvite Battle Entry FSM 静态复核后最小收尾

上一轮 READ ONLY 静态复核（`_battle_entry_positive` fallback marker + `GI_FIRE_TIMEOUT` 语义）
确认两处需收尾，均非 FSM 结构问题。本轮只做这两件事。

### 1. `_battle_entry_positive()` fallback 收窄（唯一代码改动）

`tasks/Component/GeneralInvite/general_invite.py`：

- 移除 fallback 里的 `or self.appear(GeneralBattleAssets.I_EXIT)`。收窄后
  `_battle_entry_positive()` fallback = `appear(GeneralBattleAssets.I_BATTLE_INFO) or
  appear(GeneralBattleAssets.I_PREPARE_HIGHLIGHT)` —— `GeneralBattle.is_in_battle()` 的
  8 个 positive marker（`I_BATTLE_INFO` / `I_PREPARE_HIGHLIGHT` / `I_FRIENDS` / `I_WIN` /
  `I_DE_WIN` / `I_FALSE` / `I_REWARD` / `I_REWARD_GOLD`）里的两个 battle-entry marker，
  **严格子集**。
- `_battle_entry_positive()` docstring 改正：原「复用 is_in_battle 用的**同一批** marker」
  是事实错误（`I_EXIT` 不在 `is_in_battle` marker 集）→ 改为「优先复用 `is_in_battle()`；无该
  能力时只取 `I_BATTLE_INFO` / `I_PREPARE_HIGHLIGHT` 两个 battle-entry marker（严格子集，不引入
  `is_in_battle` 未采用的更宽 heuristic）」。

**为什么 0 behavior change**：`click_fire()` 的 11 个真实 consumer（BondlingFairyland /
EternitySea / EvoZone / Exploration / FallenSun / Orochi / OtherWorldTwilight /
ExperienceYoukai / GoldYoukai / Hunt / Tako）MRO 里全部带 `GeneralBattle` →
`callable(getattr(self, "is_in_battle", None))` 恒 True → 正常生产路径全走
`self.is_in_battle(False)`，**从不进 fallback**。fallback 只对「混入 `GeneralInvite` 但无
`GeneralBattle` 且调 `click_fire`」的假想 consumer 生效——当前唯一此类 `MysteryShop` 不调
`click_fire` / `run_invite`。

**明确保留（未删 / 未改）**：`GeneralBattleAssets.I_EXIT` 本体（`RuleImage` 定义 /
`gb_exit.png` / ROI `(14,12,43,41)` / threshold 0.8）；`GeneralBattle.exit_battle()`、
`GeneralInvite.check_then_accept()`（「被秒开」判据）、`BondlingFairyland.wait_battle()`
（「已经在战斗场景中」）、`AbyssShadows` 退出循环、`Duel.duel_exit_battle()` 等全部现有
`I_EXIT` consumer。

### 2. `GI_FIRE_TIMEOUT` 语义定性 = SOFT_ATTEMPT_BUDGET（仅文档，不改代码）

静态复核确认：`overall_timer = Timer(GI_FIRE_TIMEOUT).start()` 的 `reached()` **只在
`for attempt` 循环顶检查**——决定「是否允许启动新 attempt」。已启动的 attempt 的
`random_delay(*REACTION_FIRE)`（≤0.8s）+ `_wait_room_entry_state`（自带独立
`Timer(GI_FIRE_POST_CLICK_TIMEOUT=4)`、不接收 remaining budget、`Timer.reached()` 纯轮询
不能异步打断）会正常跑完。因此：

- 最后一个在途 attempt 可超出 `GI_FIRE_TIMEOUT`；显式 overrun ≈ `0.8 + 4 = 4.8s`；
  显式理论返回上界 ≈ `15 + 4.8 ≈ 19.8s`，另加 screenshot（`_screenshot_interval` ≥0.1s）/
  template matching / device 开销。
- **仍 bounded / finite**（`GI_FIRE_MAX_TRIES=4` + soft budget + 每个 `_wait_*` 的 `Timer`
  三重）——不是 unbounded，只是不是精确 15s hard deadline。

**决定：保留 soft，不改 strict**。与 RealmRaid `fire()` / Orochi·EvoZone `_fire_*_alone`
结构一致（都是「顶层 `Timer(TIMEOUT).reached()` gate + 内层独立 `Timer(POST_CLICK)`」）；
strict 需 plumb remaining budget、会切断接近 battle 正向确认的战斗加载、增加测试复杂度、
与三个已定型 FIRE FSM 不一致——收益（~5s 可预测性）不值当。`GI_FIRE_MAX_TRIES=4` /
`GI_FIRE_TIMEOUT=15` / `GI_FIRE_POST_CLICK_TIMEOUT=4` 数值全部不动。

### 未改

FSM state contract（BATTLE / RETRYABLE_ROOM / ROOM_FAILED / TRANSITION_UNKNOWN）、
`_classify_room_entry_state()` / `_wait_room_entry_state()` / `click_fire() -> str` 结构、
`run_invite` caller guard、4 个直接 caller guard、`REACTION_FIRE=(0.4,0.8)` / 每 attempt
独立采样 / fresh reconfirm / no stale click、`Timer` API、`_room_entry_failed`、
GeneralBattle / RealmRaid / RyouToppa / Orochi / EvoZone / Fatigue / Exploration / Kekkai /
Navigation。

### 测试

`tests/test_general_invite_challenge_reaction.py` `41 → 46`：

- `test_battle_positive_prefers_is_in_battle_with_fallback`：fallback 含 `I_BATTLE_INFO` +
  `I_PREPARE_HIGHLIGHT`、**不含** `I_EXIT` / `I_FRIENDS` / `I_WIN` / `I_REWARD`。
- 新增 `test_battle_positive_fallback_is_strict_subset_of_is_in_battle`：fallback 里每个
  `GeneralBattleAssets.I_*` 都必须出现在 `GeneralBattle.is_in_battle()` 源码里。
- `test_battle_positive_fallback_without_is_in_battle`：无 `is_in_battle` 时 `I_BATTLE_INFO`
  / `I_PREPARE_HIGHLIGHT` 任一可见 → True；**只有 `I_EXIT` 可见 → False**（已从 fallback 移除）。
- 新增 `test_mysteryshop_mixes_generalinvite_but_never_calls_click_fire`：`MysteryShop` 有
  `GeneralInvite`、无 `is_in_battle`、不调 `click_fire` / `run_invite`。
- 新增 `IExitOtherConsumersPreservedTest`（3）：`I_EXIT` asset 仍定义（`gb_exit.png`）/
  `_battle_entry_positive` 源码不再引 `I_EXIT` / `exit_battle` · `check_then_accept` 仍引 `I_EXIT`。

验证（§18 顺序）：`test_general_invite_challenge_reaction`（46）+ `test_t7_5_stage2` +
`test_second_batch_fire_fsm` + `test_fire_reaction_fsm` + `test_realm_raid_state` +
`test_reaction_timing_batch1` + `test_fatigue` + `test_general_battle_timing` +
`test_general_battle_settlement` = `370 OK` → `compileall -q module tasks tests dev_tools` OK
→ 完整 `toolkit/python.exe -m unittest discover -s tests` **`1235/1235 OK`**（`1230 → 1235`，
+5，0 regression）→ `git diff --check`：`general_invite.py` + 测试文件干净；仍只命中
`tasks/Component/GeneralBattle/assets.py` + `tasks/KekkaiUtilize/assets.py` 的**既有 / 无关**
尾空白 + EOF WIP（**不清理**）。

### Level C

fallback 收窄不新增 Level C 需求（11 consumer 全走 `is_in_battle()`、fallback 是 dead code）。
`GI_FIRE_*` 继续原有 Level C pending（blank duration / retryable room 命中率 / room-failed
marker / `15`·`4`·`4` 参数体感 / 11 consumer 差异 / `run_invite` False 过早退出）；
`GI_FIRE_TIMEOUT` 已定性为 soft，Level C 观察其实际最坏返回时间是否可接受。

### Git

分支 `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。未 commit / push /
merge / reset / clean / stash / checkout / restore。本轮改动：`tasks/Component/GeneralInvite/general_invite.py`
（`M`，`_battle_entry_positive()` fallback 移除 `I_EXIT` + docstring 改正——仅此）；
`tests/test_general_invite_challenge_reaction.py`（`41 → 46`，`??` WIP）；`docs/` 六份。
既有其它 WIP（`tasks/Component/GeneralBattle/assets.py` / `tasks/KekkaiUtilize/assets.py` 尾空白等）
未触碰。未启动 MuMu / 游戏 / OCR / 真机设备。

## 2026-09-08 - RealmRaid 九宫格固定 1→9 / 退四主流程改造 + Fatigue 安全节点

`docs/ROADMAP.md`「RealmRaid 目标选择 / 退四策略改造」8 条用户已确定需求本轮全部落地。三个
AskUserQuestion 收口：退四触发 =「完全替换为『只剩最后 1 个可攻打目标』」；普通失败 =「保留配置，
仍按 `when_attack_fail` 走」；Fatigue =「本轮就接入」。唯一生产文件
`tasks/RealmRaid/script_task.py`。长期契约见 `docs/DECISIONS.md` **D020** + D001 补记（FIRE 分节
增补——`_fire_again`）。

### 1. 目标选择：固定 1→9，勋章排序作废

- 新增 `_grid_targets() -> {1-based order: 勋章 RuleImage}`：`order_medal.find_everyone()` 一次扫
  全 9 格（`order_medal` 降级为「这格有没有可挑战对手」的过滤器，**不再按勋章数量 / `order_attack`
  优先级排序**），每个匹配按中心点映射回 `C_PARTITION_n.roi_front`。`run()` 取 `index = min(targets)`
  = 从左到右、从上到下第一个可攻打格。
- 新增 `_broken_orders() -> set`（1-based）：复用 `false_roi` + `false_image`（RyouToppa
  `loser_sign_1.png`），**所有模式都扫**（旧代码只在 `WhenAttackFail.CONTINUE` 下扫失败格——固定
  1→9 选目标后必须每轮都排除刚失败未刷新的格，否则被重复选中）。
- `_grid_targets` 在 `image.copy()` 上涂黑 broken 格（`broken` 非空才 copy），**不再原地污染
  `self.device.image`**（修静态收口 R-R9）。
- `find_one()` 重写成 `_grid_targets` 的薄包装（`order = min(targets)`），保留 `(medal, order)` 签名
  供 `check_medal_is_frog`——**勋章值只影响呱太判定，不再影响攻击顺序**。`order_medal` /
  `I_MEDAL_0..5` / 呱太 OCR 资产全部保留未删。

### 2. 目标级业务 pacing `RR_TARGET_PACING = (1.0, 2.5)`

module 常量（PROVISIONAL / Level C）。新增 `_enter_target(order) -> bool`：`screenshot` →
`_target_still_attackable(order)`（= `order in self._grid_targets()`，纯只读）→
`random_delay(*RR_TARGET_PACING)` → `sleep` → `screenshot` → `_is_realm_raid_retryable_state()` +
`_target_still_attackable` 二次确认 → `click(C_PARTITION[order-1], interval=2)`。pacing 期间目标变
不可打 / 离开可操作页 → 不点旧坐标、`return False`（`run()` 重扫九宫格）。**只在每个新选定目标
点开详情前一次**，不进 FIRE retry / post-click / 再次挑战 / battle / settlement / refresh。与
`REACTION_FIRE`（FIRE 自身，在 `fire()`）是两个不同 timing owner，不合并。旧记录的「1~3 秒」对
RealmRaid 目标 pacing 作废；RyouToppa 区域 pacing `(1.0, 3.0)` 属 RyouToppa、未动。

### 3. 普通目标失败 → 按 `when_attack_fail`（默认 REFRESH）

普通分支落 `run()` 尾部原有 `if not last_battle and when_attack_fail == REFRESH: check_refresh()` /
`== EXIT: break`。**「再次挑战」`_fire_again()` 绝不用于普通失败目标**（只在退四内部）。

### 4. 退四：触发 = 「只剩最后 1 个可攻打目标」

- `only_last = len(targets) == 1`；`if only_last and con.raid_config.exit_four:` 进入退四。
  **替换掉旧的 `index == 1`（九宫格第 1 格）触发**（在固定 1→9 下语义完全错位）。
- 退四前 `self.ensure_lock(False)`（真实语义 = 最终 UNLOCKED，已核实）→ `_enter_target` → `fire` →
  退四循环；结束 `self.ensure_lock(lock_default)` 恢复配置。普通目标不动锁定状态。
  `lock_default = con.general_battle_config.lock_team_enable` 循环外捕获一次、每轮循环顶复位（呱太
  目标临时 `lock_team_enable = False` 一轮）。
- 结束条件 = 源码可证的 4 次（`RR_EXIT_FOUR_SURRENDERS = 4`，旧 `run()` 逐字硬编码，非新拍次数——
  §5「don't guess 退四 count」不触发）。`for i in range(RR_EXIT_FOUR_SURRENDERS)`：`_fire_again()`
  失败 → `aborted = True; break`；`is_final = i == 3` → 第 4 次 `con.general_battle_config`（真打）、
  前 3 次 `build_quick_exit_config`（投降）。
- 退四中断 / 最终失败 → `if aborted or not last_battle:` → `check_refresh()` → 成功 `continue`
  （**不再点「再次挑战」**）/ CD 中 `success = False; break`。退四胜利 → 落共享尾部。

### 5. `fire_again()` → `_fire_again()` 三态 bounded 重写

与 `fire()` 同一 FIRE Contract：`wait_until_appear(I_FIRE_AGAIN, wait_time=RR_AGAIN_TIMEOUT)` +
`Timer(RR_AGAIN_TIMEOUT)` + `for attempt in range(1, RR_AGAIN_MAX_TRIES + 1)`。正向
`is_in_battle(False)` → return True；`I_SHOW_AGAIN` / `I_FRESH_ENSURE` 流程点击（无 reaction）先点掉；
`I_FIRE_AGAIN` 未就绪 → 有界 `_wait_again_entered_battle()`；就绪 → 每 attempt 独立
`random_delay(*REACTION_FIRE)` → `sleep` → fresh `screenshot` → 二次 `appear(I_FIRE_AGAIN)`（消失
不点旧坐标）→ `appear_then_click(I_FIRE_AGAIN, interval=0, threshold=0.8)` →
`_wait_again_entered_battle()`。用尽 → 可达 `return False`（`run()` 退四路径改走刷新）。新增
`_wait_again_entered_battle(timeout=RR_AGAIN_POST_CLICK_TIMEOUT) -> str`（`'battle'` /
`'failure_page'`（`I_FIRE_AGAIN` / `I_FRESH_ENSURE` 在）/ `'timeout'`，不点坐标）。常量
`RR_AGAIN_MAX_TRIES=4` / `RR_AGAIN_TIMEOUT=10` / `RR_AGAIN_POST_CLICK_TIMEOUT=3`（对齐 `RR_FIRE_*`，
engineering baseline 非 Level C）。

### 6. Fatigue 安全节点

`self.begin_fatigue_task('RealmRaid')` 在主 `while 1:` 之前。新增 `_realm_raid_cycle_safe_break()` =
`screenshot` → `_is_realm_raid_retryable_state()` 才 `try_fatigue_break(safe=True,
repeat_completed=True, deadline=None)`，在普通目标 / 退四「一个完整目标业务循环（战斗 + 结果 +
必要刷新）结束、即将回循环顶重新 `check_ticket` + 扫九宫格」处调用。RealmRaid 无墙钟时限（挑战
次数由 `number_attack` 限），`deadline=None`。休息 / 发呆结束回循环顶先 `screenshot` +
`check_ticket`（`wait_until_appear(I_BACK_RED)`）+ `_grid_targets` 重扫 = fresh revalidate +
reselect。Fatigue 不进 target pacing / FIRE / FIRE retry / transition-unknown / battle /
settlement / reward / 退四内部 / `_fire_again` 之间 / refresh 动画。

### 未改

`fire()` R-R1 三态 / `_wait_fire_entered_battle` / `_is_realm_raid_retryable_state` / `RR_FIRE_*`
（§4.52）；`ensure_lock` / `check_refresh` / `check_ticket` / `reward_detect_click` /
`check_medal_is_frog` / `is_frog` / `_handle_result` / `_exit_matcher` / `false_roi` /
`false_image`；`C_PARTITION_n` 坐标 / ROI / RuleClick / ClickSampler / T7；`order_medal` /
`I_MEDAL_*` / 呱太 OCR 资产（只是不再参与排序）；`I_FIRE` / `I_FIRE_AGAIN` / `I_SHOW_AGAIN` /
`I_FRESH` / `I_FRESH_ENSURE` 资产；`REACTION_FIRE` 数值；GeneralBattle（Settlement V3 / FSM）；
GeneralInvite / RyouToppa / Orochi / EvoZone / Exploration / Kekkai / Navigation。

### 测试

`tests/test_realm_raid_state.py` 重写：

- `FireAgainCharacterizationTest`(4) → `FireAgainThreeStateTest`(11)：`setUp` patch
  `Timer` / `sleep` / `random_delay` + `_mk` / `_clicks` helper；bounded（永不进战斗 → 最多
  `RR_AGAIN_MAX_TRIES` 次 → `return False`）/ 三态 / 每 attempt 独立 reaction / `I_SHOW_AGAIN`·
  `I_FRESH_ENSURE` 流程点击 / reaction 期间按钮消失不点 stale / 正向 `is_in_battle` → True。
- `FindOneCharacterizationTest`(5) → `FindOneFixedOrderTest`(7)：`_grid(matches)` helper 喂
  `find_everyone`；`min(order)` / medal-independent（不同勋章值同位置结果一致）/ broken 格排除 /
  `image.copy()` 不污染 `self.device.image`。
- `LoopAndWaitBoundsTest`：`UNBOUNDED = ('ensure_lock', 'check_refresh', 'reward_detect_click')`；
  新增 `test_fire_again_is_bounded_after_exit_four_refactor`；`wait_until_appear` 带 `wait_time` 的
  恰 2 处（`I_RR_PERSON` in `fire` / `I_FIRE_AGAIN` in `_fire_again`）。
- `GeneralBattleHandoffTest`：退四路径 `run_general_battle` 交接次数 = 3（首战 + 4 次 fire_again 里
  非 abort 的） / `_fire_again()` 调用次数 / `for i in range(RR_EXIT_FOUR_SURRENDERS)` /
  `RR_EXIT_FOUR_SURRENDERS == 4`。
- 新增 `MainFlowRefactorTest`(12)：固定 1→9 无勋章排序（源码不含 `order_attack` 排序 /
  `find_anyone`）/ 退四触发 = `len(targets) == 1` 非 `index == 1` / 退四分支含 `ensure_lock(False)` /
  `RR_TARGET_PACING = (1.0, 2.5)` 常量 + `run` / `_enter_target` 里恰 1 处 `random_delay(*RR_TARGET_PACING)` /
  普通失败分支落 `when_attack_fail`（源码含 `WhenAttackFail.REFRESH` / `.EXIT`）/ `begin_fatigue_task`
  在主 `while 1` 前 + `try_fatigue_break` 只在 `_realm_raid_cycle_safe_break` / `_fire_again` 只在退四
  分支被调。

`tests/test_reaction_timing_batch1.py`：`test_fire_and_fire_again_have_no_confirm_delay` 里
`RealmRaid.fire_again` → `RealmRaid._fire_again`（一行）。

验证（§43 顺序）：`test_realm_raid_state` + `test_fire_reaction_fsm` + `test_reaction_timing_batch1`
+ `test_fatigue` + `test_second_batch_fire_fsm` + `test_general_invite_challenge_reaction` +
`test_general_battle_timing` + `test_general_battle_settlement` = `368 OK` →
`compileall -q module tasks tests dev_tools` OK → 完整 `toolkit/python.exe -m unittest discover -s
tests` **`1257/1257 OK`**（`1235 → 1257`，+22，0 regression）→ `git diff --check`：
`tasks/RealmRaid/script_task.py` + 测试文件干净；仍只命中 `tasks/Component/GeneralBattle/assets.py`
+ `tasks/KekkaiUtilize/assets.py` 的既有 / 无关尾空白 + EOF WIP（**不清理**）。

### Level C

`_grid_targets` 用 `find_everyone` 全格扫描的稳定性（match center 落 `roi_front` 映射准确率）、
`_broken_orders` 对刚失败未刷新格的命中率、`RR_TARGET_PACING (1.0, 2.5)` 体感、退四「只剩最后
1 个」判定的真机可靠性、`ensure_lock(False)` 在退四场景确实解锁、`RR_AGAIN_*` 参数体感、退四最终
失败刷新收敛、RealmRaid Fatigue safe point 是否稳定回到个人突破页。`RR_TARGET_PACING` /
`RR_AGAIN_*` 均 PROVISIONAL，改值连带更新 D020 / D001 补记 + §4.56。

### Git

分支 `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。未 commit / push / merge /
reset / clean / stash / checkout / restore。本轮改动：`tasks/RealmRaid/script_task.py`（`M`）；
`tests/test_realm_raid_state.py`（重写，`??` WIP）；`tests/test_reaction_timing_batch1.py`（一行，
`??` WIP）；`docs/` 六份。既有其它 WIP 未触碰。未启动 MuMu / 游戏 / OCR / 真机设备。

## 2026-09-08 - RealmRaid 主循环 correctness follow-up（CONTINUE 跳过 / Fatigue 后移 / Last Target fresh revalidate / Unlock try/finally）

§4.56 RealmRaid 主流程改造落地后复核出 4 个 correctness 边界，本轮只修这 4 个、不扩新功能。
唯一生产文件 `tasks/RealmRaid/script_task.py`。长期契约见 `docs/DECISIONS.md` **D020** 补充（非新
ADR）。

### 修改前问题（§4.56 之后的真实控制流）

- 普通选目标 `index = min(targets)`，`targets = self._grid_targets()` 只排除 `_broken_orders()`。
  `when_attack_fail == CONTINUE` 在共享尾部**没有任何处理**（既不 refresh 也不记录失败 order），
  失败但没变 broken 的格下一轮又被 `min()` 选中 → 无限重打同一目标。§4.56 删掉的「原地涂黑
  `self.device.image`」旧方案曾隐式承担了「CONTINUE = 本轮不再打这个目标」。
- 普通分支 `run_general_battle(...) → self._realm_raid_cycle_safe_break()`，然后共享尾部才
  `when_attack_fail` → REFRESH 时 `check_refresh()`。即 battle failure → fatigue → refresh，
  顺序错（recovery 未完成就休息）。
- `only_last = len(targets) == 1` 是某一帧判断，退四（解锁 + 投降 + fire_again）这种高影响分支
  一次 template 漏识别就能触发。
- 退四 `ensure_lock(False)` … `ensure_lock(lock_default)` 是两条平行语句，`continue` /
  `break` / 异常路径漏恢复锁。

### A. CONTINUE 真正跳过刚失败目标

- `run()` 主循环外新增 `failed_orders: set = set()`——纯局部业务状态，不污染截图 / 不改 asset /
  不伪造 broken marker。
- 选目标：`available = {order: m for order, m in targets.items() if order not in failed_orders}`；
  `index = min(available)`；`if not available:`（全破 / 全跳过）→ CONTINUE 则 `check_refresh()`
  否则 `break`。
- 普通目标失败 + `when_attack_fail == CONTINUE` → `failed_orders.add(index)` →
  `_realm_raid_cycle_safe_break()` → `continue`。
- **每一处 `check_refresh()` 成功分支**（顶部 `not available` / `three_refresh` / 普通 REFRESH /
  退四中断·最终失败）都 `failed_orders.clear()` 再 `_realm_raid_cycle_safe_break()`——刷新成功
  （换新九宫格）是唯一清空点，点击 refresh 前 / CD 失败都不清。
- `_broken_orders` / `false_image` / broken detector **未动**——failed/skipped ≠ broken。

### B. Fatigue Safe Point 后移到 failure recovery 之后

普通分支 battle 之后的 `_realm_raid_cycle_safe_break()` **删掉**，改在共享尾部每个结果流的
recovery 完成之后触发：

| 结果 | fatigue 触发点 |
|---|---|
| 普通胜利 | 共享尾部末尾 `self._realm_raid_cycle_safe_break()` |
| 普通失败 REFRESH | `check_refresh()` 成功 → `failed_orders.clear()` → `_realm_raid_cycle_safe_break()` |
| 普通失败 CONTINUE | `failed_orders.add(index)` → `_realm_raid_cycle_safe_break()` |
| 普通失败 EXIT | 直接 `break`，不为 fatigue 拖延退出 |
| 退四胜利 | 退四块不再自己调；落共享尾部末尾统一触发 |
| 退四中断 / 最终失败 | `check_refresh()` 成功 → `failed_orders.clear()` → `_realm_raid_cycle_safe_break()` |

`_realm_raid_cycle_safe_break()` 增强：fatigue 前先
`wait_until_appear(self.I_BACK_RED, wait_time=RR_CYCLE_STABLE_TIMEOUT)`（新常量 `= 10`，复用个人
突破页固定返回键作 recovery-complete 判据，不用固定 sleep）确认刷新 / 结算动画结束、确实回到
稳定九宫格，再 `screenshot` + `_is_realm_raid_retryable_state()` 守卫才 `try_fatigue_break(safe=True,
repeat_completed=True, deadline=None)`。

### C. 退四前 fresh 重确认唯一目标

- 新只读 helper `_is_only_remaining_target(order) -> bool` = `_is_realm_raid_retryable_state() and
  len(_grid_targets()) == 1 and order in targets`（不截图 / 不点击 / 不 sleep，截图责任在 caller）。
- 退四块入口：`self.screenshot()` → `if not self._is_only_remaining_target(index): continue`
  （在 `ensure_lock(False)` 之前）。
- `_enter_target(order, require_only_remaining=False)` 加参数：`require_only_remaining=True`（退四
  目标专用）时，pacing 前后的「仍可攻打」都收紧成 `_is_only_remaining_target(order)`——延迟期间
  又出现别的可攻打目标 → 返回 False 回主循环重扫。普通目标 `require_only_remaining=False`，行为
  逐字不变（`_target_still_attackable`）。
- **`only_last` 仍用 raw `len(targets)`**，不用 skip 过滤后的 `available`——退四判据是「真实 UI 上
  只剩 1 个可攻打」，不是「本轮失败跳过后只剩 1 个」。`raw = {5,8}` + `failed = {5}` →
  `available = {8}` 但 `only_last = len({5,8}) == 1` = False，打 8 走普通分支。raw 唯一目标恰在
  `failed_orders` 里 → `available` 空 → CONTINUE 走刷新，不进退四。

### D. 退四临时解锁 try/finally

```
self.ensure_lock(False)
aborted = False
try:
    _enter_target(index, require_only_remaining=True)  # False → continue
    fire(index)                                        # False → continue
    run_general_battle(build_quick_exit_config(...))   # 首战投降
    for i in range(RR_EXIT_FOUR_SURRENDERS):           # = 4
        _fire_again()                                  # False → aborted; break
        run_general_battle(... 第 4 次真打，其余投降)
finally:
    self.ensure_lock(lock_default)   # 正常 / continue / break / 异常都恢复
```

`finally` **只恢复锁**，无 `except`、不吞原异常（`run_general_battle` 抛异常 → 先恢复锁再原样
传播）。`lock_default = con.general_battle_config.lock_team_enable`（循环外捕获一次），不写死
True/False——用户原本不锁 → 退四后恢复不锁。退四中断 / 最终失败的 `check_refresh()` 分类在
`try/finally` 之外（锁已恢复），无锁变更、不需要进 finally。

### 未改

`fire()` R-R1 三态 FSM / `RR_FIRE_*` / `REACTION_FIRE` / partition guard / positive battle
contract；`_fire_again()` 三态 bounded FSM / `RR_AGAIN_*`（本轮**未重写** `_fire_again`）；
`RR_TARGET_PACING = (1.0, 2.5)` 数值 / `RR_EXIT_FOUR_SURRENDERS = 4`；`order_medal` / `I_MEDAL_*` /
`check_medal_is_frog` / `is_frog`；GeneralBattle / GeneralInvite / RyouToppa / Orochi / EvoZone /
Exploration / Kekkai / Navigation。

### 测试

`tests/test_realm_raid_state.py` `63 → 93`：

- 改 3 处既有：`test_wait_until_appear_calls_...`（带 `wait_time` 的 `2 → 3`，加
  `I_BACK_RED` + `RR_CYCLE_STABLE_TIMEOUT`）；`test_fatigue_break_after_battle_before_shared_tail`
  → `test_fatigue_after_failure_recovery_not_before_refresh` + 新
  `test_cycle_safe_break_confirms_stable_grid_before_fatigue`；`test_target_pacing_constant_and_placement`
  的 `_enter_target(index)` 计数改前缀匹配 `'self._enter_target(index'` 且断言
  `require_only_remaining=True`。
- 新增 `CorrectnessFollowupSourceTest`(11，源码 / AST 形态)：`failed_orders` 局部 set 不涂帧 /
  `available` 排除 skip / `only_last` 用 raw 不用 `len(available)` / 退四入口 fresh revalidate 在
  unlock 之前 / `_is_only_remaining_target` 只读 / `_enter_target` `require_only_remaining` 后置
  复查 / 退四块 `try` 无 `except` 且 `finally` 恢复 `lock_default`、`body` 覆盖 `_enter_target` ·
  `fire` · `run_general_battle` · `_fire_again` / `lock_default` 来自 config / 每处 `check_refresh`
  成功都 `clear` 再 fatigue / battle 后不紧跟 fatigue / CONTINUE 分支 add→fatigue→continue /
  EXIT 分支无 skip·refresh·fatigue。
- 新增 `RunLoopBehaviorTest`(19，`_RunHarness` 驱动 `run()` 主循环，除 `run()` 本体外全 mock)：
  CONTINUE 跳过刚失败目标 `[1,2,3]` / 两次失败选第三个 / 失败目标 UI 仍 attackable 也 skip /
  全跳过 → refresh + clear → 下一轮又可选 / 普通 REFRESH 失败 fatigue 在 refresh 之后（battle 与
  refresh 之间无 fatigue）/ 普通 CONTINUE 失败 fatigue 在 skip 之后且无 refresh / 退四最终失败先
  恢复锁再 refresh 再 fatigue / 退四入口 fresh 帧非唯一 → 中止不 unlock、重扫走普通分支 /
  `only_last` 用 raw 不用 filtered（`is_only_remaining` 从未被评估）/ order 5 也能进退四不要求
  `index == 9` / `_enter_target` False → finally 恢复锁 / `fire` False → finally 恢复锁 /
  `run_general_battle` 抛 `RuntimeError` → finally 恢复锁且原异常传播（不是 `TaskEnd`）/
  `lock_default=False` 退四后恢复 False、从不出现 `ensure_lock(True)` / EXIT 失败 `break` 无
  skip·refresh·fatigue / 普通胜利 cycle 末尾 fatigue / 退四胜利经共享尾部 fatigue + 恢复锁。

验证（§49 顺序）：`test_realm_raid_state`（93）+ `test_fire_reaction_fsm` +
`test_reaction_timing_batch1` + `test_fatigue` + `test_second_batch_fire_fsm` +
`test_general_invite_challenge_reaction` + `test_general_battle_timing` +
`test_general_battle_settlement` = `398 OK` → `compileall -q module tasks tests dev_tools` OK →
完整 `toolkit/python.exe -m unittest discover -s tests` **`1287/1287 OK`**（`1257 → 1287`，+30，
0 regression）→ `git diff --check`：`tasks/RealmRaid/script_task.py` + 测试文件干净；仍只命中
`tasks/Component/GeneralBattle/assets.py` + `tasks/KekkaiUtilize/assets.py` 既有 / 无关尾空白 +
EOF WIP（**不清理**）。

### Level C（追加）

CONTINUE `failed_orders` 与真机「失败格是否变 broken」的实际重叠（失败格既进 `failed_orders`
又进 `_broken_orders` —— 无害但值得观测）、`RR_CYCLE_STABLE_TIMEOUT = 10` 是否够覆盖刷新 / 结算
动画、退四入口 `_is_only_remaining_target` 二次确认在真机是否偶发误否决（模板抖动）、
`check_refresh()` 返回 True 后 `I_BACK_RED` 出现的实际延迟。`RR_CYCLE_STABLE_TIMEOUT` PROVISIONAL，
改值连带更新 D020 + §4.56。

### Git

分支 `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。未 commit / push / merge /
reset / clean / stash / checkout / restore。本轮改动：`tasks/RealmRaid/script_task.py`（`M`，
+436 / −159）；`tests/test_realm_raid_state.py`（`63 → 93`，`??` WIP）；`docs/` 六份。既有其它 WIP
（含 `tests/test_reaction_timing_batch1.py` 上一轮一行改）未触碰。未启动 MuMu / 游戏 / OCR /
真机设备。

## 2026-09-08 - RealmRaid Level C hotfix：`_fire_again()` 失败结果页误判为已进入新战斗 + OASX 个人突破过时文案同步

真机 Level C 发现的 defect + hotfix。不重构 §4.56 / correctness follow-up 已完成的逻辑。

### Level C 证据（2026-09-08 真机日志）

- `13:37:30.859 Exit four: order 9 is the last attackable target` —— **「只剩最后唯一可攻打目标才
  退四」正确工作**。
- `13:37:31.536 Click RES_LOCK` → `13:37:32.070 Target 9: business pacing 2.03s before open` →
  `13:37:34.293 Click partition_9` → `13:37:35.552 Click RES_FIRE` →
  `13:37:36.572 Fire 9: entered battle` —— 退四解锁 + 目标 pacing + 首战进入，全部正确。
- `13:37:38.481 Click GB_EXIT` → `13:37:39.434 Click GB_EXIT_ENSURE` →
  `13:37:41.373 Exit battle success` → `13:37:41.984 Battle result: Lose` —— 首战主动退出正确。
- **Bug 起点**：`13:37:42.596 Fire again: entered battle` —— `Battle result: Lose` 与它之间
  **没有 `Fire again: attempt ...` / 没有 reaction 日志 / 没有 `I_FIRE_AGAIN` 点击日志**。紧接着
  `GENERAL BATTLE START` → `[UI] page_battle_result` → `Battle result: Lose`，之后连续重复
  `Fire again: entered battle → GENERAL BATTLE START → page_battle_result → Lose`。脚本实际仍停在
  上一场失败结果页，却把它误判成「再次挑战已进入下一场战斗」——所谓 4 次 `_fire_again` 大部分没有
  真实点「再次挑战」。

### 根因

`_fire_again()`（3 处）+ `_wait_again_entered_battle()`（1 处）用 `GeneralBattle.is_in_battle(False)`
作 positive battle-entry 判据。`is_in_battle()` 是**整个战斗生命周期 detector**：

```
I_BATTLE_INFO | I_PREPARE_HIGHLIGHT | I_FRIENDS | I_WIN | I_DE_WIN | I_FALSE | I_REWARD | I_REWARD_GOLD
```

其中 `I_FALSE` 本身就是失败结算页 marker。退四首战主动退出 → `page_battle_result` → `I_FALSE`
命中 → `is_in_battle(False)` = True → `_fire_again()` 顶端 `if self.is_in_battle(False): return True`
立即命中 → caller 又 `run_general_battle()` → GeneralBattle 立即重新识别同一个 `page_battle_result`
→ `Lose` → 假 `_fire_again` 循环。

### 修复（只改 RealmRaid consumer，不动 `GeneralBattle.is_in_battle()`）

- 新增 RealmRaid-local 只读 helper **`_is_active_battle_entry() -> bool`** =
  `self.is_in_prepare(False) or self.is_in_real_battle(False)`。复用 GeneralBattle 已有的**两个窄
  detector**：
  - `is_in_prepare()` = `I_BUFF | I_PREPARE_HIGHLIGHT | I_PREPARE_DARK | I_PRESET | I_PRESET_WIT_NUMBER`
  - `is_in_real_battle()` = `I_BATTLE_INFO`

  两者都是「准备页 / 战斗进行页」的窄 positive，**均不含 result / reward marker**。纯只读：
  不截图 / 不点击 / 不 sleep（同 `_is_realm_raid_retryable_state()` 风格）。
- `_fire_again()` 的 3 处 `is_in_battle(False)` + `_wait_again_entered_battle()` 的 1 处
  → 全部 `_is_active_battle_entry()`。三态语义（`battle` / `failure_page` / `timeout`）不变，
  只是 `battle` 判据收窄。失败结算页现在：`_is_active_battle_entry()` = False → 落到
  `appear_then_click(I_SHOW_AGAIN/I_FRESH_ENSURE)` 流程点击 → `appear(I_FIRE_AGAIN)` = True →
  `Fire again: attempt N, reaction 0.xxs` → sleep → fresh screenshot → 二次 `appear(I_FIRE_AGAIN)`
  → `appear_then_click(I_FIRE_AGAIN, interval=0, threshold=0.8)` → `_wait_again_entered_battle()`
  等 `_is_active_battle_entry()` 才 `'battle'`。
- **`GeneralBattle.is_in_battle()` / `is_in_prepare()` / `is_in_real_battle()` 本体及其它 consumer
  全部不动。**

### 未改

- `fire()` R-R1 的 `is_in_battle(False)` 用法**本轮不动**——`fire()` 在 `wait_until_appear(I_RR_PERSON)`
  之后、目标详情页上点第一次 FIRE，其前没有战斗结果页，安全-by-context（Level C 日志里
  `Fire 9: entered battle` 是真进入）。未来若做一致性收窄再评估（ROADMAP Level C 项）。
- `RR_AGAIN_MAX_TRIES=4` / `RR_AGAIN_TIMEOUT=10` / `RR_AGAIN_POST_CLICK_TIMEOUT=3`（当前 bug 与
  timeout 参数无关，不借机调参）；`RR_EXIT_FOUR_SURRENDERS=4`；`REACTION_FIRE=(0.4,0.8)` /
  每 attempt 独立采样 / fresh reconfirm / no stale click / 无 `confirm_delay` / 无第二套 reaction。
- 退四触发（`only_last` / raw count / `_is_only_remaining_target` / `require_only_remaining` /
  target pacing `RR_TARGET_PACING` / try/finally unlock）；固定 1→9；`failed_orders`；
  `when_attack_fail`（REFRESH / CONTINUE / EXIT）；RealmRaid Fatigue safe point。
- GeneralBattle（Settlement V3）/ GeneralInvite / RyouToppa / Orochi / EvoZone / Exploration /
  Kekkai / Navigation。

### 测试

`tests/test_realm_raid_state.py` `93 → 103`：

- `FireAgainThreeStateTest._mk`：mock 从 `t.is_in_battle` 改成 `t._is_active_battle_entry`
  （kwarg 名保留 `in_battle`，语义 = 窄 active-battle-entry 判据）。10 个既有 `_fire_again` /
  `_wait_again` 行为 / 源码用例照旧通过。
- 新增 `ActiveBattleEntryContractTest`(10)：
  - 源码形态（去 docstring 只扫代码体）：`_is_active_battle_entry` 只
    `is_in_prepare(False) or is_in_real_battle(False)`、代码体无 `is_in_battle(` / 无
    `I_FALSE` · `I_WIN` · `I_DE_WIN` · `I_REWARD` · `I_REWARD_GOLD` · `I_FRIENDS` / 纯只读；
    `_fire_again` + `_wait_again_entered_battle` 代码体不再有 `is_in_battle(`、改用
    `_is_active_battle_entry()`；`GeneralBattle.is_in_battle()` 仍宽（含 7 个 marker），
    `is_in_prepare` / `is_in_real_battle` 仍窄（不含 result / reward）。
  - 行为：result/reward-only 帧 → `_is_active_battle_entry()` False 且**根本不问宽
    detector**（`is_in_battle` mock `assert_not_called`）；prepare / real-battle 帧 → True；
    **`I_FALSE` 帧（宽 `is_in_battle` 会 True）+ `I_FIRE_AGAIN` 可见 → `_fire_again()` 不
    short-circuit return True，必须走 reaction（`random_delay(0.4,0.8)`）+ 真实
    `I_FIRE_AGAIN` click（`interval=0, threshold=0.8`）**；active-battle 首帧 → True 不点；
    click 后按钮消失 + active 暂未出现 → unknown 阶段不对旧坐标乱点、之后 active 出现才 True；
    失败页一直在 + active 永不出现 → bounded ≤ `RR_AGAIN_MAX_TRIES` → False。

验证（§38 顺序）：`test_realm_raid_state`（103）+ `test_fire_reaction_fsm` +
`test_reaction_timing_batch1` + `test_fatigue` + `test_second_batch_fire_fsm` +
`test_general_invite_challenge_reaction` + `test_general_battle_timing` +
`test_general_battle_settlement` = `408 OK` → `compileall -q module tasks tests dev_tools` OK →
完整 `toolkit/python.exe -m unittest discover -s tests` **`1297/1297 OK`**（`1287 → 1297`，+10，
0 regression）→ `git diff --check`：`tasks/RealmRaid/script_task.py` + 测试文件干净；仍只命中
`tasks/Component/GeneralBattle/assets.py` + `tasks/KekkaiUtilize/assets.py` 既有 / 无关尾空白 +
EOF WIP（**不清理**）。

### OASX / 配置显示同步

OASX（`d:\oas_xy\OASX`）个人突破配置文案 **source of truth = 前端硬编码 Dart map**
`lib/translation/cn_parts/cn_realm_raid_config.dart`（`lib/translation/i18n.dart` 把各
`_cn_*_config` map 合并进 `content_cn`），**不是从 backend config schema 自动生成**（确认方式：
`i18n.dart` 逐个 `part 'cn_parts/cn_*_config.dart'`，配置 UI 按字段名 + `_help` 查这些 map）。

旧文案（§4.56 之前的旧逻辑）：

| key | 旧值 |
|---|---|
| `exit_four` | 当进攻到左上角第一个的时候先退四次再进攻 |
| `exit_four_help` | 为了支持打九退四，保证稳定57级 |
| `order_attack` | 挑战顺序 |
| `order_attack_help` | 使用过滤器，保持默认即可 |

新文案：

| key | 新值 |
|---|---|
| `exit_four` | 打九退四（只剩最后一个可攻打目标时） |
| `exit_four_help` | 开启后：当九宫格只剩最后一个可攻打目标时，先对它退四（投降四次）再进行最终挑战，用于打九退四、保证稳定57级。其余目标按固定顺序正常攻打。 |
| `order_attack` | 攻打的勋章档位 |
| `order_attack_help` | 决定九宫格里哪些勋章档位算作“可攻打目标”（数字 5~0 对应勋章数量，0 为无勋章）。填写的先后顺序不再决定攻击顺序——目标一律按九宫格固定顺序 1→9（从左到右、从上到下）选择。保持默认即可，除非想只打特定档位。 |

**`order_attack` backend config field 保留不删**（`tasks/RealmRaid/config.py`
`order_attack: str = Field(default='5 > 4 > 3 > 2 > 1 > 0')`）——全仓确认仍有 1 个生产 consumer：
`ScriptTask.order_medal` cached_property（`re.split('>', order_attack)` → `[int(i) for i in ...]`
→ 过滤到 `[0..5]` → `ImageGrid([I_MEDAL_i ...])`）。§4.56 之后它**不再决定攻击顺序**（那是
`min(targets)`），但仍决定 `ImageGrid` 里放哪些 `I_MEDAL_*` 模板 = 哪些勋章档位算「可攻打对手」
（`_grid_targets` 的 `order_medal.find_everyone`）。`>` 排序已 vestigial（`find_everyone` 按 y 排，
不看模板顺序）。故按项目要求「仍有其它语义 → 改名不删字段」：字段留、格式留（旧 config 兼容），
OASX label / help 改成真实语义（勋章档位过滤器，非攻击顺序），不新增「1 > 2 > ... > 9」可编辑
输入框。

同步改了 backend web i18n 副本 `module/config/i18n/zh-CN.json`（`.gitignore` 忽略，
`module/server/i18n.py` `I18n.load_zh_cn()` 服务）同 4 个 key。**未改** PyQt GUI 的
`module/config/i18n/zh_CN.xml`（Qt 翻译源）/ 编译产物 `zh_CN.qm`——需 Qt `lrelease` 重新编译，
本环境无该工具链；记为 backend PyQt i18n 待同步项。OASX 无 `flutter` / `dart` 工具链可用
（本环境），改动是纯 string-literal map 编辑、结构已核对（三引号多行串同既有 `when_attack_fail_help`
形态）、无测试引用该 map。

### Level C re-test（下一轮真机重点看的日志序列）

首战主动退出后应出现：

```
Exit battle success
Battle result: Lose
Fire again: attempt 1, reaction 0.xxs        ← 必须有
Click RES_FIRE_AGAIN                          ← 必须有真实点击
Fire again: entered battle after click
GENERAL BATTLE START
[UI] page_battle_prepare  或  page_battle     ← 真正进入新战斗
```

**不能**再出现：`Battle result: Lose` → 无 attempt / 无 click → 直接 `Fire again: entered battle`
→ 立刻又 `page_battle_result` / `Lose`。

### Git

Backend：分支 `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。未 commit / push /
merge / reset / clean / stash / checkout / restore。本轮改动：`tasks/RealmRaid/script_task.py`
（`M`，+462 / −159）；`tests/test_realm_raid_state.py`（`93 → 103`，`??` WIP）；
`module/config/i18n/zh-CN.json`（`.gitignore` 忽略、非 `git status` 可见）；`docs/` 六份。既有其它
WIP 未触碰。OASX：分支 / HEAD 未动，本轮改 `lib/translation/cn_parts/cn_realm_raid_config.dart`
（`M`，4 个 string 值），OASX 既有大量 WIP 未触碰；未 commit / push / merge / reset / clean /
stash / checkout / restore；未改 `pubspec` version。未启动 MuMu / 游戏 / OCR / 真机设备。

## 2026-09-08 - RealmRaid 再次挑战确认弹窗独立 reaction

### READ ONLY inventory

`tasks/RealmRaid/assets.py`：`I_FIRE_AGAIN` 注释为「失败再次挑战」；`I_SHOW_AGAIN` 为「不再提示」；`I_FRESH_ENSURE` 注释为「刷新确认/再战确认」。`_fire_again()` 的真实调用顺序是先处理 `I_SHOW_AGAIN`，再处理 `I_FRESH_ENSURE`，最后才对 `I_FIRE_AGAIN` 执行已有 `REACTION_FIRE`。改前 `I_FRESH_ENSURE` 只有 `interval=2`，没有 reaction / sleep / fresh reconfirm；`check_refresh()` 的同一共享 asset 已有自己的 `REACTION_CONFIRM`，不属于本轮。

### 修改

在 `tasks/RealmRaid/script_task.py` 新增任务本地 `RR_AGAIN_CONFIRM_DELAY=(0.3,0.6)`，仅 `_fire_again()` 中的 `appear_then_click(I_FRESH_ENSURE, interval=2, confirm_delay=RR_AGAIN_CONFIRM_DELAY)` 使用。复用 `BaseTask.appear_then_click`：首次识别后独立采样、sleep、fresh screenshot、二次识别、按新帧坐标点击；确认按钮在 delay 后消失则返回 False，不发生 stale click。没有修改 shared primitive。

### Timing / FSM 边界

`I_FIRE_AGAIN` 仍只使用 `REACTION_FIRE=(0.4,0.8)`；确认弹窗确认按钮只使用 `RR_AGAIN_CONFIRM_DELAY=(0.3,0.6)`。`interval=2` 保持 Timer throttle；无额外 confirm / repeat / retry delay。`_is_active_battle_entry()`、`_wait_again_entered_battle()`、`RR_AGAIN_MAX_TRIES=4` / `RR_AGAIN_TIMEOUT=10` / `RR_AGAIN_POST_CLICK_TIMEOUT=3`、bounded FSM、`I_FALSE` result-page regression、目标 pacing、退四、失败策略、Fatigue 全部未改。

### 测试

`tests/test_realm_raid_state.py` `103 → 104`：更新 no-stack source guard，并新增真实确认 action owner 的调用参数断言。`tests/test_reaction_timing_batch1.py` 改为锁定 `fire()` 无 confirm_delay、`_fire_again()` 仅确认 action 带 `RR_AGAIN_CONFIRM_DELAY`、`I_FIRE_AGAIN` click 不叠 confirm_delay。完整回归和最终 diff-check 见本轮收尾。

### Level C

用户手动复测退四时应观察：`Fire again: attempt N, reaction 0.xx` → `I_FIRE_AGAIN` click → 确认弹窗 → 约 0.3~0.6 秒后 `I_FRESH_ENSURE` click → 新 battle prepare / battle。确认弹窗或确认按钮在 delay 后消失时不得点击；`I_SHOW_AGAIN` 不应获得该 delay。未启动 MuMu / 游戏 / OCR / 设备。

### 验证 / Git

`toolkit/python.exe -m unittest tests.test_realm_raid_state` = `104 OK`；`tests.test_fire_reaction_fsm` + `tests.test_reaction_timing_batch1` + `tests.test_fatigue` = `161 OK`；`tests.test_second_batch_fire_fsm` = `27 OK`；`toolkit/python.exe -m compileall -q module tasks tests dev_tools` 通过；完整 `toolkit/python.exe -m unittest discover -s tests` = **`1298/1298 OK`**（旧基线 `1297 → 1298`，0 regression）。最终 `git diff --check` 仍只报告既有 `tasks/Component/GeneralBattle/assets.py` 与 `tasks/KekkaiUtilize/assets.py` 的尾空白 / EOF WIP，本轮文件无 whitespace 问题。分支 `master`，HEAD `2cdf3a05`；未 commit / push / merge / reset / clean / stash / checkout / restore。

## 2026-09-08 - Exploration Boss 直退 / Exit Contract / Chapter FrameWait / Fatigue Safe Point

### READ ONLY inventory

真实入口为 `ScriptTask.run → pre_process → exec_exp_page(page-dispatch while) → post_process`；章节由
`page_exploration → open_expect_level(OCR + 最多 25 次 swipe) → page_exp_entrance → I_E_EXPLORATION_CLICK
→ page_exp_main` 进入。普通怪由 `search_up_fight` 动态定位，Boss 由 `I_BOSS_BATTLE_BUTTON` 优先识别；
两者共用 `fire(button)`（4 attempts + Timer(10) + positive battle page）与 `run_on_battle → GeneralBattle`。
旧 Boss 战后 `run_general_battle` 返回值被丢弃，回 `page_exp_main` 后先 `collect_reward()`，其又先
`collect_treasure_box()`，因此地图宝箱会被搜索 / 点击；宝箱 helper 只做 reward UI transaction，不负责
次数 / flag / recovery，但组合链后的 `collect_paper_man_reward()` 在 Boss + 关闭纸人奖励时还隐式调用
`quit_exp_main()`。GeneralBattle 虽配置 `exit_matcher=page_exp_main`，仍可能走 2.5 秒 missing-page fallback，
不能单凭 return 证明 map ready。退出真实目标是 `page_exp_entrance(I_E_EXPLORATION_CLICK)`。

### 修改

`run_on_battle` 消费 battle bool；Boss win 才 `_complete_boss_business_cycle`。先连续两帧 fresh positive
`page_exp_main`，再走 task-local `EXIT_READY / EXIT_CONFIRM / TRANSITION_UNKNOWN / EXIT_SUCCESS`：复用
`quit_exp_main(I_UI_BACK_YELLOW)` 与 `run_on_exp_exit(I_E_EXIT_CONFIRM)`，只以连续两帧
`page_exp_entrance` 为 success，unknown 不重复按 exit，15 秒超时 `GameStuckError`。Boss path 与 exit 后
首次 entrance 都 bypass treasure；helper / asset 与其它 consumer 保留。solo 在 exit positive 后触发
`try_fatigue_break(... deadline=start_time+limit_time)`，随后 fresh revalidate entrance；group 不接。

`open_expect_level` 的实际 swipe 分支改为 `baseline → wait_for_changed_and_stable → 下一轮 OCR`。ROI 从
章节 OCR asset 换算为 `(1065,203,1189,555)`；changed `0.02` / stable `0.01` / frames `2` / timeout
`1.5s` / poll `0.12s` 均 provisional。FrameWait 结果不作 semantic success，最大 25 次边界不变；没发出
swipe 的旧 1 秒保留并改称 OCR/action retry throttle。

### 测试 / 边界

`tests/test_exploration_state.py` `33 → 48`：Boss win/loss、map 未 ready 不 exit、treasure 0 call、confirm、
marker disappearance != success、unknown later success / bounded timeout、非 Boss treasure 保留、solo-only
fatigue 顺序 / deadline / fresh revalidate、FrameWait stable/timeout 均不等于 chapter found。Exploration 48、
FrameWait/FrameState/Fatigue 138、GeneralBattle/GeneralInvite/reaction 关联组均通过；完整回归
**1298 → 1313**。未改 GeneralBattle / RealmRaid / GeneralInvite / RyouToppa / Orochi / EvoZone / Kekkai /
Navigation；未启动 MuMu / 游戏 / OCR / 设备；未 commit / push / merge / reset / clean / stash / checkout /
restore。Level C 待验清单见 ROADMAP Exploration 分项。

## 2026-09-08 - Exploration Level C hotfix：Boss 直退 success 判据 + 轮换模式归用户所有

§4.58 Exploration 首次真机 Level C 暴露两个 correctness bug。本轮只修这两个，不重构 §4.58 已实现
的 Boss 直退 / treasure bypass / Fatigue / Chapter FrameWait。`tasks/Exploration/base.py` +
`tasks/Exploration/script_task.py`。长期契约见 `docs/DECISIONS.md` **D021 补记**。

### Level C 证据（真机日志）

```
18:19:51.807 Battle result: Win
18:19:52.958 [UI] page_exp_main
18:19:52.960 Exploration boss exit state: exit_ready
18:19:54.220 Click (50, 38) @ UI_UI_BACK_YELLOW          ← quit_exp_main()
18:19:54.685 Exploration boss exit state: transition_unknown
18:19:55.291 [UI] page_exp_exit
18:19:55.295 Exploration boss exit state: exit_confirm
18:19:56.024 Click (783, 394) @ RES_E_EXIT_CONFIRM       ← run_on_exp_exit()
18:19:56.502 Exploration boss exit state: transition_unknown
（18:19:56.502 → 18:20:07.638 共 ~11 秒，无任何 [UI] 行）
18:20:07.638 ERROR GameStuckError: Exploration boss exit timed out in state: transition_unknown
```

`I_UI_BACK_YELLOW` 点击、`page_exp_exit` 出现、`I_E_EXIT_CONFIRM` 点击**全部成功**；用户肉眼确认
`I_E_EXIT_CONFIRM` 之后画面已回到探索页面。坏的是 **Exit Success positive detector**，不是「退出按钮
没点到」。另外用户发现脚本会主动把自己手工开着的「自动轮换」点关掉。

### Bug B — Exit timeout（最高优先）

**根因**：§4.58 的 `_run_boss_exit_transaction` 用
`detect_page_in(page_exp_main, page_exp_exit, page_exp_entrance, include_global=False)` +「连续两帧
`page_exp_entrance`（`I_E_EXPLORATION_CLICK`）」作唯一 `EXIT_SUCCESS`。真实退出后停在**探索模式列表
`page_exploration`**（`GameUiAssets.I_CHECK_EXPLORATION`，`category="global"`）——被 `include_global=False`
排除、也不在显式列表里。`_detect_pages` 每帧返回 `None`（日志里那 11 秒零 `[UI]` 行即证据，
`logger.attr` 不去重，返回 `page_exp_main` 会持续打 `[UI] page_exp_main`）。事务对真实 outer 页面全盲
→ 永久 `transition_unknown` → 15 秒 `GameStuckError`。`page_exp_entrance` 与 `page_exploration` 都是
`exec_exp_page` 有 handler（`run_on_exp_entrance` / `run_on_exp`）、也都是 `check_exit →
activate_realm_raid` 里 `current_page in (page_exploration, page_exp_entrance)` 认可的合法外层页面。

**修复**（`tasks/Exploration/script_task.py`）：

- 新增 task-local 只读 predicate **`_is_boss_exit_success_state() -> bool`** =
  `match_page_once(_resolved_page(page_exp_entrance)) or match_page_once(_resolved_page(page_exploration))`
  ——**正向 marker 命中**，绝不以「弹窗 / 主界面标记消失」为成功。
- `_run_boss_exit_transaction`：成功分支改用 `_is_boss_exit_success_state()`（连续
  `BOSS_EXIT_STABLE_FRAMES=2` 帧）；`detect_page_in` 缩到只判 `page_exp_main` / `page_exp_exit`
  （驱动 `EXIT_READY` → `quit_exp_main()` / `EXIT_CONFIRM` → `run_on_exp_exit()`）。`EXIT_READY` 仍靠
  `action_sent` 防重复点退出。
- 新增 `_boss_exit_probe() -> str`：首次进入 `transition_unknown` + 超时前各打一条
  `page_exp_entrance=.. page_exploration=.. page_exp_main=.. page_exp_exit=.. rotate_on=.. rotate_off=..`
  ——下一次 Level C 直接定位真实 outer 页面。
- 新增 `_wait_for_boss_exit_success_state(timeout)`（连续两帧 positive 的有界等待），
  `_complete_boss_business_cycle` 的 fatigue 后 revalidate 从 `_wait_for_stable_page(page_exp_entrance)`
  改用它。
- `run_on_exp()` 的 `ALONE` 分支也读 / 清 `_skip_treasure_once_at_entrance`（与 `run_on_exp_entrance`
  同一 flag、同一 `if not skip_treasure` 守卫）——Boss 直退落在探索模式列表时首次 dispatch 同样不补领
  地图宝箱。
- **未调 timeout**：`BOSS_EXIT_TRANSACTION_TIMEOUT=15.0` / `BOSS_EXIT_READY_TIMEOUT=10.0` /
  `BOSS_EXIT_STABLE_FRAMES=2` 一字未动（是 detector 错、不是等待不够）。

### Bug A — 轮换模式被脚本取消

**根因**：`BaseExploration.switch_rotate()` 的 `case AutoRotate.no:` 分支
`appear_then_click(self.I_E_AUTO_ROTATE_ON, interval=0.8, confirm_delay=REACTION_FAST)` ——
`I_E_AUTO_ROTATE_ON` 是「自动轮换开着」marker，点它 = 取消轮换。config `auto_rotate`（title
「自动添加候补式神」）默认 `AutoRotate.no`；`switch_rotate()` 由 `run_on_exp_main` 每次在 `page_exp_main`
调用，于是用户手工开着的轮换被反复点关（为把地图布局恢复成脚本熟悉的旧样子）。全 Exploration 只有
这一处点 `I_E_AUTO_ROTATE_ON`。

**修复**（`tasks/Exploration/base.py`）：`switch_rotate()` 的 `AutoRotate.no` 分支改为 `pass`
（observe only）——脚本绝不点 `I_E_AUTO_ROTATE_ON` / `I_E_AUTO_ROTATE_OFF` 去取消 / 重置用户的轮换。
`page_exp_main` 识别本就用 `any_of(I_E_SETTINGS_BUTTON, I_E_AUTO_ROTATE_ON, I_E_AUTO_ROTATE_OFF)`
同时覆盖轮换开 / 关两种布局，不依赖脚本恢复关闭态。随之移除 `base.py` 里已 dead 的 `REACTION_FAST`
import。**`AutoRotate.yes` 不变**：用户显式选「自动添加候补式神」时脚本仍
`click(C_CLICK_SETTINGS)` → `run_on_exp_settings` → `fill_shikigami()` +
`appear_then_click(I_E_AUTO_ROTATE_OFF)`（轮换关着时打开）——只做「开」方向、从不取消用户已开的轮换。

### 未改

Exploration dynamic `fire(button)`（`max_tries=4 + Timer(10) + positive battle page`）；Chapter
FrameWait 6 个 provisional 参数；`_exit_matcher()` / `page_exp_main` / `page_exp_settings` 定义 /
`run_on_exp_settings` 的 `no` 分支（只 `goto_page(page_exp_main)`）；Fatigue 顺序契约（Exit Success
positive → stable outer → `try_fatigue_break` → fresh revalidate）；`_wait_for_stable_page(page_exp_main)`
map-ready 门。GeneralBattle（Settlement V3 / `is_in_battle` / prepare·result·reward timing）；
RealmRaid / GeneralInvite / RyouToppa / Orochi / EvoZone / Kekkai / Navigation。

### 测试

`tests/test_exploration_state.py` `48 → 66`：

- `BossDirectExitContractTest`：事务用例改用 `_is_boss_exit_success_state` + `detect_page_in(main,exit)`
  双序列驱动（新 `_tail` 无限尾生成器）；新增 `test_exit_confirm_then_exploration_list_also_succeeds`
  （轮换 ON 时退出停在 `page_exploration` 也算成功，用真实 `_is_boss_exit_success_state` +
  `match_page_once` mock）、`test_success_predicate_is_positive_not_disappearance`（源码扫描
  `match_page_once` on `page_exp_entrance` / `page_exploration`，无 `not self.appear` / `disappear`，
  事务里输出 `_boss_exit_probe()`）、`test_transaction_timeout_not_widened`（`15.0` / `10.0` / `2` 原值）。
- `ExplorationFatigueSafePointTest`：`_wait_for_stable_page(page_exp_entrance)` → `_wait_for_boss_exit_success_state`；
  新增 `test_exit_timeout_before_fatigue_means_zero_fatigue`（`_run_boss_exit_transaction` raise →
  `try_fatigue_break` 0 call）；`test_group_modes_do_not_enter_fatigue` 补 `_wait_for_boss_exit_success_state` mock。
- 新增 `RotationOwnershipTest`（5）：`AutoRotate.no` + 用户轮换 ON → `switch_rotate()` 返 False、
  `appear_then_click` / `click` 都不点轮换 marker；源码 `no` 分支无 `I_E_AUTO_ROTATE_ON` / 无
  `appear_then_click` / 有 `pass`；`yes` 仍 `click(C_CLICK_SETTINGS)`；`I_E_AUTO_ROTATE_ON` 全仓不作
  `click` / `appear_then_click` / `ui_click` 目标；`run_on_exp_main` 仍 gate 在 `switch_rotate()`。
- 新增 `BossExitSuccessStatePredicateTest`（6）：入口 / 探索列表各 positive、都不命中不 success、
  predicate 不调 `appear`（disappearance）、wait helper 连续两帧 + 超时。
- 新增 `RunOnExpTreasureSkipTest`（3）：`run_on_exp` ALONE 一次性跳宝箱 / 正常领 / 两个外层 handler
  共用 `_skip_treasure_once_at_entrance`。
- `tests/test_reaction_timing_batch1.py::ExplorationReactionTest::test_auto_rotate_toggle_uses_fast`：
  `switch_rotate` 代码体（去 docstring）不再有 `I_E_AUTO_ROTATE_ON`；`run_on_exp_settings` 的
  `I_E_AUTO_ROTATE_OFF` FAST 断言保留。

验证（§32 顺序）：`test_exploration_state`（66）+ `test_frame_wait` + `test_frame_state` +
`test_fatigue` + `test_reaction_timing_batch1` + `test_general_battle_timing` +
`test_general_battle_settlement` + `test_general_invite_challenge_reaction` + `test_fire_reaction_fsm`
= `389 OK` → `compileall -q module tasks tests dev_tools` OK → 完整
`toolkit/python.exe -m unittest discover -s tests` **`1331/1331 OK`**（`1313 → 1331`，+18，0 regression）
→ `git diff --check`：`tasks/Exploration/base.py` + `script_task.py` + 测试文件干净；仍只命中
`tasks/Component/GeneralBattle/assets.py` + `tasks/KekkaiUtilize/assets.py` 既有 / 无关尾空白 + EOF WIP
（**不清理**）。

### Level C re-test（下一轮真机重点看的日志序列）

```
Battle result: Win
[UI] page_exp_main
Exploration boss exit state: exit_ready
Click (...) @ UI_UI_BACK_YELLOW
[UI] page_exp_exit
Exploration boss exit state: exit_confirm
Click (...) @ RES_E_EXIT_CONFIRM
Exploration boss exit state: transition_unknown       ← 可短暂存在
Exploration boss exit probe: page_exp_entrance=.. page_exploration=.. page_exp_main=.. page_exp_exit=.. rotate_on=.. rotate_off=..
Exploration boss exit state: exit_success             ← 必须出现（不再 15s 超时）
（rotation mode 仍保持用户原状态；Boss treasure 0 click）
try_fatigue_break ...
```

**特别观察**：probe 行里 `page_exploration` / `page_exp_entrance` 哪个是 True（确定真实 outer 页面）；
轮换 ON / OFF 时 probe 是否不同；整轮跑下来游戏里的「自动轮换」开关**没有被脚本改动**。

### Git

分支 `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。未 commit / push / merge /
reset / clean / stash / checkout / restore。本轮改动：`tasks/Exploration/base.py`（`M`）+
`tasks/Exploration/script_task.py`（`M`）；`tests/test_exploration_state.py`（`48 → 66`，`??` WIP）；
`tests/test_reaction_timing_batch1.py`（一处，`??` WIP）；`docs/` 六份。既有其它 WIP（含
`tasks/RealmRaid/script_task.py` 前几轮改动）未触碰。未启动 MuMu / 游戏 / OCR / 设备。

## 2026-09-08 - Exploration Boss Reward Flow 收敛：撤销「Boss 后不领地图宝箱直接退出」错误需求，恢复原生链

### 背景 —— 上一轮（§4.58 / §4.59 / D021）按错误业务假设实现

§4.58 曾按「Boss Win → 完全不领任何地图宝箱 → 直接退出」实现，为此新增了一整套 Boss 专用退出结构
（`_run_boss_exit_transaction` / `_is_boss_exit_success_state` / `_wait_for_boss_exit_success_state` /
`_wait_for_stable_page` / `_set_exit_state` / `_boss_exit_probe` / `_complete_boss_business_cycle` /
`_resolved_page`、`ExplorationExitState` 枚举、`BOSS_EXIT_*` 常量、`_skip_treasure_once_at_entrance`
flag）。§4.59 又对其中的 `EXIT_SUCCESS` 判据做了 Level C hotfix（多态 positive）。

**Level C + 用户业务重新确认后，正式规则修正为**：Boss Win → **检查地图宝箱 → 有则正常领取 → 无则
继续 → 不领取小纸人奖励 → 沿用原 Exploration 原生退出 flow → 回外层页面 → 下一轮**。这与原项目
（HEAD）既有设计一致。本轮把偏离原生的结构撤销。

### 原项目原生 reward / exit 链（HEAD 一直如此，本轮恢复）

- `run_on_battle`（原生）：`run_general_battle(self._config.general_battle_config,
  exit_matcher=pages.page_exp_main)` + `_match_end.refresh()` + `wait_start_time` 重置。返回值不捕获，
  之后由 `exec_exp_page` 的 page-dispatch 自然接管。
- `run_on_exp_main` → `if self.collect_reward(): return`。`collect_reward()` = `collect_treasure_box()
  or collect_paper_man_reward()`。
- `collect_treasure_box()`：`appear(I_E_REWARD_BOX_SMALL)` / `appear(I_E_REWARD_BOX_BIG)` → `ui_click(box,
  I_REWARD)` + `ui_click_until_disappear(I_REWARD)` 领取 `return True`；**无宝箱 → `return False`**。多个
  宝箱 / repeated dispatch 天然处理（领一个 → return → 下一轮 page_exp_main 再查）。
- `collect_paper_man_reward()`（treasure 返回 False 才走）：`if self.fire_monster_type == 'boss' and not
  self._config.exploration_config.collect_paper_reward: logger.info("Not collect paper doll reward");
  self.quit_exp_main(); return True`——**「打过 Boss + 配置不领小纸人 → 原生退出」原项目本就有**。
  否则（收小纸人 / 未打 Boss）出现 `I_BATTLE_REWARD` 时 `ui_get_reward`。
- `quit_exp_main()` = `appear_then_click(I_UI_BACK_YELLOW, interval=0.8, confirm_delay=REACTION_NAVIGATION)`
  → `page_exp_exit` → `run_on_exp_exit()`（`need_exit=True` → `appear_then_click(I_E_EXIT_CONFIRM, ...,
  confirm_delay=REACTION_CONFIRM)`）→ 游戏退出 → `get_current_page()` 自然命中 `page_exp_entrance` /
  `page_exploration` → `run_on_exp_entrance` / `run_on_exp` 原生接管。

### 自动退出场景（Level C 新发现）

某些 Boss 战后无地图宝箱时游戏会自动结束探索并跳外层页面。**未新造 Auto Exit FSM**：
- 若游戏已自动离开 `page_exp_main`，`get_current_page()` 直接返回外层页 → 原生 handler。
- 即便 `page_exp_main` 多留一帧走到 `quit_exp_main()`，`appear_then_click(confirm_delay=REACTION_NAVIGATION)`
  会在 reaction delay 后**重新截图二次确认 `I_UI_BACK_YELLOW`**（`base_task.py:363` 起，`confirm_delay`
  路径：`appear → sleep → screenshot → appear again → 没了不点`）——**天然避免 stale click**。
  `I_E_EXIT_CONFIRM` 同理（`confirm_delay=REACTION_CONFIRM`）。
- **未加任何新的 current-page guard**（§4.51 Batch A 的 `confirm_delay` 已提供 stale-safe 语义）。

### 撤销的结构（`tasks/Exploration/script_task.py`）

全仓 consumer audit 后确认只服务错误需求 → 删除：`ExplorationExitState` 枚举、`BOSS_EXIT_READY_TIMEOUT`
/ `BOSS_EXIT_TRANSACTION_TIMEOUT` / `BOSS_EXIT_STABLE_FRAMES` 常量、`_resolved_page` /
`_wait_for_stable_page` / `_set_exit_state` / `_is_boss_exit_success_state` /
`_wait_for_boss_exit_success_state` / `_boss_exit_probe` / `_run_boss_exit_transaction` /
`_complete_boss_business_cycle` 方法、`_skip_treasure_once_at_entrance` flag（含 `run()` 里的初始化、
`run_on_exp_entrance` / `run_on_exp` 里的 skip 守卫——两处 `collect_treasure_box()` 恢复无条件调用）、
`run_on_battle` 里 `battle_won` 捕获与 `_complete_boss_business_cycle` 调用。随之移除 `from enum import
Enum` / `from module.base.timer import Timer` / `from module.exception import GameStuckError` import。
`base.py` **本轮零改动**（§4.58 FrameWait + §4.59 Rotation + §4.51 reaction 全是 keep）。

### 保留（独立成立）

- **Rotation Contract（§4.59 Bug A）**：`BaseExploration.switch_rotate()` 的 `AutoRotate.no` = `pass`
  （observe only，不点 `I_E_AUTO_ROTATE_ON` 取消用户手工开启的轮换）；`AutoRotate.yes` 仍
  `click(C_CLICK_SETTINGS) → fill_shikigami + 开轮换`。未回退。
- **Chapter FrameWait（§4.58）**：`_wait_chapter_list_settle` + `EXPLORATION_LEVEL_*` 6 参数
  （`(1065,203,1189,555)` / `0.02` / `0.01` / `2` / `1.5` / `0.12`）PARTIAL / Level C calibration
  pending，**一字未动**。
- **solo Fatigue 能力**：`run()` 里 `begin_fatigue_task('Exploration')`（仅 ALONE）保留。Safe Point 重挂
  到新 `_maybe_boss_cycle_fatigue()`——在 `run_on_exp_entrance` / `run_on_exp` **顶部**调用（这两个 handler
  只在 `get_current_page()` 正向命中 `page_exp_entrance` / `page_exploration` 时才分发 = 已在合法外层
  稳定页），仅当 `user_status == ALONE` 且刚完成的是 Boss 循环（`fire_monster_type == 'boss'`，handler
  稍后才重置它）→ `try_fatigue_break(safe=True, repeat_completed=True, deadline=start_time+limit_time)`
  + 消费 Boss 标记（`fire_monster_type = ''`，避免下一轮外层 dispatch 重复进入）+ 让调用方 `return`
  （交 `exec_exp_page` 下一轮 fresh screenshot + 重新分发 = fatigue 后 fresh revalidate）。**不在
  `page_exp_main` 触发**（宝箱 / 小纸人 policy / 退出未完成）——`run_on_exp_main` 不调用它。
- `fire(button)` / `_exit_matcher()` / GeneralBattle / `run_on_exp_settings` · `run_on_exp_exit` ·
  `open_expect_level` 的 §4.51 `confirm_delay` / 普通怪 handoff / 其它任务全未改。

### 测试

`tests/test_exploration_state.py` `66 → 56`（净 −10，全部来自删掉的废弃 contract 用例）：

- **删**（对应已废弃的错误业务 contract）：
  - `BossDirectExitContractTest` 整类（12）：`_transaction_task` helper + `_PollTimer` / `_tail` 辅助 +
    `test_boss_win_handoff_completes_cycle_without_treasure`（断言「Boss 后 `collect_treasure_box` 0
    call」——与恢复的原生链正好相反）、`test_boss_loss_does_not_claim_completion`、
    `test_battle_return_without_stable_map_never_starts_exit`、
    `test_exit_confirm_then_positive_stable_outer_page_succeeds`、
    `test_exit_confirm_then_exploration_list_also_succeeds`、
    `test_old_marker_disappears_without_outer_page_never_succeeds`、
    `test_transition_unknown_can_later_reach_positive_outer_page`、
    `test_transition_unknown_is_bounded_and_no_repeat_exit_click`、
    `test_success_predicate_is_positive_not_disappearance`、`test_transaction_timeout_not_widened`、
    `test_post_exit_entrance_skips_treasure_once`（断言「入口跳过 treasure」——废弃）、
    `test_treasure_helper_remains_for_non_boss_entrance`（并入新 native 用例）。
  - `BossExitSuccessStatePredicateTest` 整类（6）：`_is_boss_exit_success_state` /
    `_wait_for_boss_exit_success_state` 已删。
  - `RunOnExpTreasureSkipTest` 整类（3）：`_skip_treasure_once_at_entrance` 已删。
  - `ExplorationFatigueSafePointTest` 里依赖 `_complete_boss_business_cycle` 的 3 个
    （`test_exit_then_fatigue_then_fresh_revalidate`、`test_exit_timeout_before_fatigue_means_zero_fatigue`、
    `test_group_modes_do_not_enter_fatigue`）；`test_run_begins_fatigue_only_for_solo` 迁到
    `BossCycleFatigueTest`。
- **加**：
  - `BossRewardFlowNativeTest`（8）：模块源码无任何 Boss exit transaction 结构残留 / `run_on_exp_main`
    用原生 `collect_reward` / `collect_reward` = `treasure or paper_man` / 「不领小纸人 + Boss」走原生
    `quit_exp_main` 且 `I_BATTLE_REWARD` 领取分支仍在（两个奖励不是同一开关）/ `collect_treasure_box`
    有则领取无则 `return False` / `run_on_exp_entrance` · `run_on_exp`(ALONE) 无条件 `collect_treasure_box`
    且源码无 `skip_treasure` / `quit_exp_main` 靠 `confirm_delay` 天然 stale-safe 且无新 `detect_page_in`
    / `GameStuckError`。
  - `BossCycleFatigueTest`（7）：solo Boss 循环 → `_maybe_boss_cycle_fatigue()` 触发 `try_fatigue_break`
    + 消费 `fire_monster_type` / solo 非 Boss（`'normal'` / `''`）不触发 / LEADER·MEMBER 不触发 /
    `run_on_exp_entrance` · `run_on_exp` 顶部先 safe point 且命中即 `return`（在 `collect_treasure_box`
    之前）/ Boss 循环下 `run_on_exp_entrance` 早返回不领 treasure 不导航（交下一轮）/ `run_on_exp_main`
    源码无 `_maybe_boss_cycle_fatigue` / `try_fatigue_break` / `begin_fatigue_task` / `run()` 只 solo
    `begin_fatigue_task`。
- `GeneralBattleHandoffTest::test_run_on_battle_calls_...` → `test_run_on_battle_is_native_handoff_no_boss_completion_helper`
  （锁原生 `run_general_battle(exit_matcher=page_exp_main)` + `_match_end.refresh`，源码无
  `_complete_boss_business_cycle` / `_run_boss_exit_transaction` / `battle_won`）。
- `tests/test_reaction_timing_batch1.py`：本轮无需改（`switch_rotate` / `run_on_exp_settings` /
  `run_on_exp_exit` / `open_expect_level` 的 reaction 断言全是 keep）。

验证（§24 顺序）：`test_exploration_state`（56）+ `test_frame_wait` + `test_frame_state` +
`test_fatigue` + `test_reaction_timing_batch1` + `test_general_battle_timing` +
`test_general_battle_settlement` + `test_general_invite_challenge_reaction` = `345 OK` →
`compileall -q module tasks tests dev_tools` OK → 完整 `toolkit/python.exe -m unittest discover -s
tests` **`1321/1321 OK`**（`1331 → 1321`，−10 全为删掉的废弃 contract 用例，0 regression）→
`git diff --check`：`tasks/Exploration/base.py`（本轮零改动）/ `script_task.py` + 测试文件干净；仍只
命中 `tasks/Component/GeneralBattle/assets.py` + `tasks/KekkaiUtilize/assets.py` 既有尾空白 WIP
（**不清理**）。

### Level C re-test

- **场景 A（有地图宝箱）**：Boss Win → `page_exp_main` → `collect_treasure_box` 识别到小 / 大宝箱 →
  正常领取（`I_REWARD` 出现后消失）→ 下一轮 `collect_reward` 无宝箱 → `collect_paper_man_reward` →
  `Not collect paper doll reward` → `I_UI_BACK_YELLOW` → `I_E_EXIT_CONFIRM` → outer page。
- **场景 B（无地图宝箱）**：Boss Win → `collect_treasure_box` 无宝箱 `return False` → 若游戏自动退出则
  `get_current_page()` 直接命中 outer page（**无 stale `I_UI_BACK_YELLOW` / 无错误 exit confirm**）；
  若仍在 `page_exp_main` 则 `collect_paper_man_reward` → 原生 `quit_exp_main` → outer page。
- 两场景：轮换模式都保持用户原状态；solo `_maybe_boss_cycle_fatigue()` 只在回到 `page_exp_entrance` /
  `page_exploration` 后触发。

### Git

分支 `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。未 commit / push / merge /
reset / clean / stash / checkout / restore（**未用 `git checkout` / `git restore` / `reset` 回滚旧
版本——做的是语义级手工收敛**）。本轮改动：`tasks/Exploration/script_task.py`（`M`，对 HEAD 净
+51 / −15）；`tasks/Exploration/base.py`（`M`，本轮零新增改动，仍是 §4.58 / §4.59 / §4.51 的既有
diff）；`tests/test_exploration_state.py`（`66 → 56`，`??` WIP）；`docs/` 六份。既有其它 WIP
（`tasks/RealmRaid/script_task.py` 等前几轮、`GeneralBattle/assets.py` / `KekkaiUtilize/assets.py`
尾空白）未触碰。未启动 MuMu / 游戏 / OCR / 设备。

## 2026-09-08 - 普通滑动端点空间分布 v2（`SwipeEndpointSampler`，D022）

### 起因

OASX 行为统计（`interaction_type=swipe`）显示同类 `swipe` 的**起点挤成一簇、终点挤成一簇、
轨迹高度重合**。定位：`TouchSwipeModel` 的中段曲线每次都变，但上层给它的起终点几乎固定。
`RuleSwipe.coord()` 本来就对 `roi_front` / `roi_back` 各采一次（不是共享偏移），根因是大量
swipe 资产的 `roi_front` / `roi_back` 只有 ~21×21 甚至 4×4 / 2×4，`random_center_point_in_roi`
的 3 次采样均值（Bates）在这么小的框里有效标准差只有 3~6px。

### 改动（Level A/B，不改 `TouchSwipeModel` 中段轨迹）

- **新增 `module/atom/swipe_endpoint.py`**（`SwipeEndpointSampler`，与 `module/click_sampler.py`
  的「点击空间模型」同构）：
  - `SwipeEndpointParams`（frozen + `__post_init__` fail-fast）：`wide_axis_px=48` /
    `offset_dist_ratio=0.12` / `offset_min_px=6` / `offset_max_px=40` / `clamp_sigma_mult=2.4` /
    `clamp_dist_ratio=0.30` / `core_weight=0.85` / `core_sigma_frac=0.55` / `tail_sigma_frac=1.30` /
    `axis_max_attempts=8` / `min_cos=0.906`（~25°）/ `min_dist_ratio=0.55` / `max_dist_ratio=1.45` /
    `abs_min_dist_px=10` / `joint_max_attempts=6` / 屏幕安全边界 `(2,2,1277,717)`。**全部
    provisional，Level C 待标定。**
  - `sample_swipe_endpoints(roi_front, roi_back)`：参照点 = 各 ROI 整数取值范围几何中点；
    「游走尺度」= `clamp(基准距离 × 0.12, 6, 40)`；每个端点**独立**——按权重选 core（窄高斯）
    / tail（宽高斯），按轴采样，夹到 `[preferred ± hard_half] ∩ 屏幕安全边界 ∩ ⊇原 ROI`，
    越界有限次 rejection → 回退轴中心（不对越界样本做边界 clamp，与 D014 一致）。
  - **轴向 ROI `>= 48px` 的轴逐字走旧 `_center_biased_int`；两端两轴都大 → 整条 short-circuit
    等价旧 `coord()`（连联合校验都跳过）** —— `S_BATTLE_RANDOM_*`（480×426）/ Summon
    `S_RANDOM_SWIPE_*`（100~480px）分布字节级不变。
  - **联合校验**（起终点都采完）：夹角 `cos >= 0.906` + 距离 ∈ `[0.55, 1.45] × 基准` +
    `>= 10px` + 业务主轴符号一致；不满足整体重采样，`joint_max_attempts` 用尽 → 确定性回退
    `(preferred_start, preferred_end)`（一定过校验）。**有界，无 `while True`。**
- **`module/atom/swipe.py`**：`RuleSwipe` 新增 `sample_endpoints()`（委托
  `sample_swipe_endpoints(self.roi_front, self.roi_back)`）；`coord()` 加一句 docstring 说明
  「旧访问器，保留给兼容 / 测试」，**本体逐字不变**。
- **`tasks/base_task.py`**：`BaseTask.swipe` 的 `x1, y1, x2, y2 = swipe.coord()` →
  `swipe.sample_endpoints()`（唯一改动点，~50 个 `self.swipe(S_*)` 生产 consumer 透明迁移），
  更新旁边注释。
- BehaviorTrace **天然记录真实采样端点**（`swipe_trajectory` 的 `extra.start_x/y` /
  `end_x/y` 取自 `TouchSwipeModel.generate` 精确固定的首末点），未改 `module/behavior_trace.py` /
  `Control`。

### 未迁 / 未改

`RuleSwipe.coord()` 语义；`BaseTask.list_find` 翻页（`RuleList.swipe_pos` + `device.swipe`，
D013）；`KekkaiUtilize._perform_search_swipe`（K1~K4 自建 `SWIPE_*_RANGE` → 直接喂
`TouchSwipeModel`）；`KekkaiUtilize.perform_swipe_action` / `KekkaiActivation` 好友卡 `swipe_adb`
直连（`S_CARDS_SWIPE` 资产全仓无 caller）；`RyouToppa.flush_area_cache`（`duration=`，D003）；
`Control.drag` / `drag_*` / `tasks/Chess/runtime/press_and_drag.py` / `AbyssShadows.move_a_little`
（摇杆，D018「永不按普通 swipe 迁移」）。`TouchSwipeModel` 的 minimum-jerk / 曲率 / 逐段 dt /
尾段慢拖 / pressure 一字未改。

### 统计核对（20k 样本 / 资产，非真机）

- `S_SWIPE_LEVEL_UP`（21×21 → 21×21，向下 ~116）：起点 sd `~4 → ~9`，距离 `116 ± 13`
  （min 66），方向不反。
- `S_SWIPE_SHIKI_TO_LEFT_ONE`（21×21，向左 ~88）：起终点 sd `~4 → ~7`，min 距离 50（>0.55×88）。
- `S_BUFF_UP`（456×35 → 386×37）：x 宽轴 sd `~67`（保持旧 Bates）、y 窄轴 sd `~9 → ~26`。
- `S_BATTLE_RANDOM_LEFT`（两端两轴都宽）：起点 sd `~80`、距离 `545 ± 110`——与旧 `coord()`
  均值 / sd 一致（delta < 3）。
- `S_AB_LEVEL_RIGHT` 起点 `(0,0,10,10)`：x / y 夹到屏幕安全边界 min 2，**不出负坐标**。
- 全仓 ~50 个 `RuleSwipe` 资产（含 1px / 2px / 贴角 ROI）静态普查：采样不崩、主轴方向不反。
- fallback 命中率：多数资产 ≈ 0，`S_SP_DOWN` ≈ 3.4%（宽 x + 窄 y + 近竖直，联合校验偶尔收敛
  到中心），仍是方向正确的合法滑动。

### 长期契约 —— `docs/DECISIONS.md` D022

「业务（`RuleSwipe` 两 ROI）给方向 / 距离意图 → 端点采样层（`swipe_endpoint.py`）给具体
起终点分布 → `TouchSwipeModel` 给两点间轨迹 → `Control` / minitouch 执行」四层。端点采样层
是与 `ClickSampler` 平行的公共层，**不进 `BaseTask`**（god class 约束）。大 ROI 保持旧
`_center_biased_int` 是「只治真正过度固定的小框、不动作者有意的大散布」的最小侵入选择。

### 验证（`CLAUDE.md` 默认流程）

`toolkit/python.exe -m unittest tests.test_swipe_endpoint_sampling`（36 OK）→
`tests.test_base_task_swipe_trajectory` / `test_random_center_point` / `test_rule_swipe_trace_removed`
/ `test_control_swipe_trajectory` / `test_kekkai_utilize_state` / `test_list_find` /
`test_touch_swipe_model`（213 OK）→ `compileall -q`（改动文件）OK → 完整
`toolkit/python.exe -m unittest discover -s tests` **`1357/1357 OK`**（`1321 → 1357`，+36 全为
`tests/test_swipe_endpoint_sampling.py`，0 regression）→ `git diff --check`：`module/atom/swipe.py`
/ `tasks/base_task.py` / `tests/test_base_task_swipe_trajectory.py` 干净（`git diff --check` 全仓
仍只命中 `GeneralBattle/assets.py` + `KekkaiUtilize/assets.py` 既有尾空白 WIP，**不清理**）。

### Git

分支 `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。未 commit / push /
merge / reset / clean / stash / checkout / restore。本轮改动：`module/atom/swipe_endpoint.py`
（`??` 新）、`tests/test_swipe_endpoint_sampling.py`（`??` 新，36）、`module/atom/swipe.py`（`M`，
`+sample_endpoints()` + import + `coord()` docstring）、`tasks/base_task.py`（`M`，`BaseTask.swipe`
1 行 + 注释；此前已有的 fatigue / list_find FrameWait WIP 未触碰）、`tests/test_base_task_swipe_trajectory.py`
（`M`，`test_swipe_delegates_...` 改 patch `sample_endpoints`，计数不变）、`docs/` 六份中 5 份
（`AI_CONTEXT` §4.61 + §7 + 覆盖清单 / `DECISIONS` D022 / `ARCHITECTURE` 滑动链 + RuleSwipe 原子 +
能力表 / `ROADMAP` 已完成行 + Level C 区 / 本 `DEVELOP_LOG`；`TESTING` 无需更新——无新测试级别 /
验证规则 / 真机要求变化）。未启动 MuMu / 游戏 / OCR / 设备。

## 2026-09-08 - Swipe Endpoint Sampling v2 / D022 —— Level C 收口（documentation-only，无代码变化）

### 本轮性质

Level C status / documentation closeout。**不是继续开发 Swipe Endpoint Sampling，不是继续调随机
参数。** 目标：根据用户多轮 MuMu 真机观察，将 D022 当前实现收口、冻结当前默认参数、更新项目
事实 / Roadmap / Level C 状态；不开始下一项开发。

### READ ONLY 核验

按项目规则读 `AI_CONTEXT` / `ROADMAP` / `DECISIONS` / `ARCHITECTURE` / `TESTING` +
`DEVELOP_LOG` 最近 D022 内容后，逐字核验三处生产文件仍与上一轮 D022 落地报告一致：

- `module/atom/swipe_endpoint.py`：`SwipeEndpointParams` 16 个字段默认值全部未改
  （`wide_axis_px=48` / `offset_dist_ratio=0.12` / `offset_min_px=6` / `offset_max_px=40` /
  `clamp_sigma_mult=2.4` / `clamp_dist_ratio=0.30` / `core_weight=0.85` / `core_sigma_frac=0.55` /
  `tail_sigma_frac=1.30` / `axis_max_attempts=8` / `min_cos=0.906` / `min_dist_ratio=0.55` /
  `max_dist_ratio=1.45` / `abs_min_dist_px=10` / `joint_max_attempts=6` / 屏幕安全边界
  `(2,2,1277,717)`）；`sample_swipe_endpoints` / `_sample_axis` / `_sample_one_endpoint` /
  `_direction_distance_ok` 逻辑未改；有限 rejection + 确定性回退 + 无 `while True` 仍成立。
- `module/atom/swipe.py`：`RuleSwipe.sample_endpoints()` 委托 `sample_swipe_endpoints`；
  `coord()` 本体未改（仍严格 ROI 内中心偏置，保留给兼容 / 测试）。
- `tasks/base_task.py`：`BaseTask.swipe` line ~608 = `x1, y1, x2, y2 = swipe.sample_endpoints()`
  → `swipe_trajectory(...)`，是 `RuleSwipe.coord()` 唯一 production caller 的迁移点。

三处均与上一轮报告一致 → **本轮不改任何生产代码 / 测试**（`CLAUDE.md` 规则：不为制造 diff 改代码）。

### Level C 真机证据（用户提供，未由 AI 执行）

用户连续多轮 MuMu 真机运行，通过 OASX「统计 → 点击位置与滑动轨迹」页连续观察真实执行数据
（BehaviorTrace 记录的最终 start / end / trajectory）。最新一日统计截图约「点击 590 / 滑动 42」。
观察到：

1. 同类横向 swipe 的起点不再钉死为单点。
2. 起点形成明显但仍集中的小范围 endpoint cloud。
3. 终点同样形成独立的小范围分布。
4. start / end 不是简单共用同一个整体 offset。
5. 多条横向 trajectory 不再完全重合：有轻微高度差和角度差。
6. 主方向仍然非常明确，无视觉上明显的反向 swipe。
7. 未观察到极端短 / 极端长 swipe、大角度错误斜滑、endpoint 大面积飞散。
8. 同图另一组纵向 swipe 当前也无明显异常。
9. 连续使用暂未报告：误触 UI / 滑不动 / 滑过头 / 业务状态错误 / Kekkai 回退 / Exploration swipe 回退。

用户判断「看样子可以」，确认进入收口。

### 结论

- **D022 = Level C PASS**（当前 ordinary swipe 业务下的真机行为验收通过），`SwipeEndpointParams`
  当前默认值**在无新真机反例前冻结**。表述边界：**不**声称完成「大规模统计学参数拟合」或
  「所有未来业务 swipe 的永久 / 全局最优分布」。当前状态「endpoint 有变化但仍集中、trajectory
  有变化但方向稳定」正是预期目标。
- **本轮禁止继续调参**：不改 `SwipeEndpointParams` 任一字段，不扩大 sigma / tail 概率 /
  hard_half / 角度界 / 距离比 / joint attempts。继续扩散只会增加误触控件 / 起终点进危险区 /
  scroll 距离漂移 / OCR·FrameWait 收敛变化 / 小 ROI 业务失败风险——无具体 Level C bug 不继续调。
- **大 ROI 兼容不变**：`_center_biased_int` 仍只作用于 `wide_axis_px` 以上的轴 + 两端两轴都大的
  short-circuit（`S_BATTLE_RANDOM_*` / `S_RANDOM_SWIPE_*` 字节级不变），不为「统一」让大 ROI 进
  小 ROI 扩散策略。
- **特殊 swipe 继续排除**：Kekkai K1~K4 自建 endpoint policy / `list_find` 翻页 / `KekkaiActivation`
  `swipe_adb` / RyouToppa `duration=` / drag / press-and-drag / 摇杆 / 精确拖拽 —— 均不接公共 sampler。
- **TouchSwipeModel 继续冻结**：minimum-jerk / mild curve / MOVE dt / tail density / tail slowdown /
  exact endpoint / pressure / dwell 均不在本轮范围。D022 只解决 start / end 空间分布。
- **BehaviorTrace / OASX 本轮不改**：当前统计页（start / end / trajectory 均来自 BehaviorTrace
  最终执行数据）已足够作 Level C observability；不新增 INFO 日志。

### 重新打开 D022 calibration 的条件

（否则 D022 保持 closed，不要求每次业务更新重做 swipe 校准）：① 某页面 swipe 误触控件；
② 某业务 swipe 距离不足 / 明显过滑；③ start·end 落入危险可点区；④ direction guard 失败 /
采到反向 swipe；⑤ BehaviorTrace 与实际执行不一致；⑥ 新 OASX 统计图重现极端 endpoint 聚集 /
飞散；⑦ 某特殊 consumer 被错误接入公共 sampler。

### 验证

生产代码 / 测试 = 0 改动，沿用上一轮 D022 已验证完整基线 **`1357/1357 OK`**；本轮另重跑
swipe endpoint targeted：`tests.test_swipe_endpoint_sampling`（36）+ `test_base_task_swipe_trajectory`
（16）+ `test_random_center_point`（7）+ `test_rule_swipe_trace_removed`（3）= **`62 OK`**。
未跑 `compileall` / 完整 `unittest discover`（无生产代码修改，`CLAUDE.md` 默认验证流程针对源码改动）。

### 文档

`AI_CONTEXT` §4.61（加 Level C 收口段 + reopen 条件）+ §7 基线行（标注「Level C 收口，无代码
变化」，基线数字 `1357/1357` 不变）；`DECISIONS` D022 状态行 + 新增「Level C 补记」（defaults
冻结 + 依据 + 结论范围 + 冻结项 + reopen 条件；**未删原始 provisional 历史**）；`ROADMAP` 已完成
行更新为 Level C PASS + 从「需要真机验证」区移除已完成的 pending 条（改写为「已 Level C PASS /
冻结」并指向 D022 补记）；`ARCHITECTURE` 能力表「普通滑动端点空间分布」行状态更新（调用链 /
RuleSwipe 原子描述不变）；本 `DEVELOP_LOG` 追加本条。`TESTING` 无需更新——「provisional 参数 →
Level A/B 接线 + Level C calibration → 有实测依据后冻结」已是既有长期规则（§见「W1 结构性 settle」
段与「归级原则」），D022 的具体状态归 `AI_CONTEXT` / `ROADMAP` / `DECISIONS`。

### Git

分支 `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。未 commit / push /
merge / reset / clean / stash / checkout / restore。本轮改动仅 `docs/`：`AI_CONTEXT.md` /
`DECISIONS.md` / `ROADMAP.md` / `ARCHITECTURE.md` / `DEVELOP_LOG.md`（5 份，`TESTING.md` 无需
更新）。生产代码 / 测试 0 改动。未启动 MuMu / 游戏 / OCR / 设备。

### 下一候选（本轮不实施）

`Exploration Chapter FrameWait Level C calibration`（§4.58 的 `EXPLORATION_LEVEL_*` 6 个
provisional 参数，`docs/ROADMAP.md` Level C 区），或当前 ROADMAP 下一 P0。

## 2026-09-09 - ActivityShikigami 当期普通爬塔线适配（入口 / FIRE Contract / Fatigue Safe Point / 活动结算弹窗）

### 目标

用户高频重复刷「式神活动」爬塔。上一轮 READ ONLY 审查（同名条）定位框架成熟但资产陈旧、
FIRE 弱、无 Fatigue。用户随后重截本期爬塔资产并给了真机事实。本轮只适配
`ActivityShikigami.NormalClimbAct` 普通爬塔高频刷取，不扩到大富翁 / 伪神降临。

### 用户提供的新资产（AI 未截图）

`git status` 显示用户已放入：`as/page/page_main_goto_act_2.png`（新）+ `assets.py` 重新生成含
`I_MAIN_GOTO_ACT_2`（roi_front `(726,280,38,35)`，旧 `I_MAIN_GOTO_ACT` 保留）；`as/climb/*` 15 张
PNG 重截 + `image.json` / `ocr.json` / `pages.json` ROI 迁到本期布局（`I_ACT_FIRE` `(1133,601,84,45)`、
lock/penta 图标右移、`O_REMAIN_AP` `(551,14,119,33)` / `O_REMAIN_PASS` `(752,16,97,31)` /
`O_REMAIN_PENTA_PASS` `(931,10,113,40)`、`I_TO_BATTLE_MAIN` / `I_TO_BATTLE_BOSS` 换新）；
`as/page/as_check_battle_main.png` 重截 + ROI 调整。**未提供活动结算弹窗专用 marker。**

### 用户真机事实（本轮据此实现）

- 本期**无**挑战按钮 disabled 态、**无**资源不足弹窗、**无**购买体力 / 门票确认弹窗。资源不足
  仅一闪而过 ~1s 提示文字（无稳定 marker）。→ 不新增假 disabled / popup 资产、不建 READY/DISABLED
  双模板 FSM；资源主判据 = FIRE 前 OCR。
- 本期战斗结束是一个「活动专用结算弹窗」（不是旧通用胜负结果页），可安全套用 GeneralBattle
  Settlement V3 的 `C_RANDOM_DEFAULT`（`random_default`）大安全区推进，不会点到危险控件。

### 修改（3 个生产文件，全 task-local）

**`tasks/ActivityShikigami/page.py`**
- 新 `goto_activity_entry(task)` 作 `page_main → page_act` 边动作：优先
  `appear_then_click(I_MAIN_GOTO_ACT_2, interval=1, confirm_delay=REACTION_NAVIGATION)`，旧
  `I_MAIN_GOTO_ACT` 作跨活动周期回退。新 `_activity_entry_visible(task)` 合并二者，`find_activity_entry`
  两处 `appear(I_MAIN_GOTO_ACT)` 改用它。`page_main.connect(page_act, goto_activity_entry, ...)`。
  入口图标消失不代表进入成功——仍由 `page_act` positive marker 判定。

**`tasks/ActivityShikigami/base_act.py`**
- 新 `BaseAct._is_active_battle_entry()` = `is_in_prepare(False) or is_in_real_battle(False)`（窄
  detector，复用 GeneralBattle 已有；`is_in_battle()` 本体不动）—— 本期活动结算弹窗不能被宽
  `is_in_battle()`（含 `I_FALSE` / `I_WIN` / `I_REWARD`）误判成「新战斗已开始」，同 D001 补记
  「Battle Lifecycle Detector ≠ New Battle Entry Detector」/ RealmRaid 同名 helper。
- 新实例标记 `_fatigue_owns_macro_idle`（`__init__` = False）。`prepare_next_action` 的 `random_sleep`
  改成 `if random_sleep_cfg and not self._fatigue_owns_macro_idle:`——爬塔线宏观空闲交给 Fatigue，
  大富翁 / 伪神线仍 `random_sleep`。docstring 同步。

**`tasks/ActivityShikigami/activities/normal.py`**
- module 级常量：`ACTIVITY_FIRE_MAX_TRIES=4` / `ACTIVITY_FIRE_TIMEOUT=12` /
  `ACTIVITY_FIRE_POST_CLICK_TIMEOUT=4` / `ACTIVITY_SETTLEMENT_MAX_CLICKS=6` /
  `ACTIVITY_SETTLEMENT_TIMEOUT=15`（全 PROVISIONAL，对齐 `GI_FIRE_*` / `RR_FIRE_*` 量级）。
- `run_climb`：置 `self._fatigue_owns_macro_idle = True` + `self.begin_fatigue_task('ActivityShikigami')`。
- `_run_climb_type`：新增 `cycle_completed` 标记（首轮 False，一场 battle + 活动结算 drain 完整跑完
  后 True）；`if current_page == destination:` 分支在 `prepare_next_action` 后调
  `_activity_challenge_safe_break(action_type, destination, repeat_completed=cycle_completed)`，返回
  False → `sleep(0.3); continue`；`page_battle_prepare/page_battle` 分支的 `run_general_battle` 后加
  `_drain_activity_settlement`。
- `_run_climb_action`：inline `run_general_battle` 后加 `_drain_activity_settlement(action_type, destination)`。
- **`_enter_climb_battle` 重写**：旧 `while True` + `is_in_battle(False)` + `random.randint(3,5)` 次点击
  （无墙钟 timeout）→ bounded battle-entry transaction。新增 `_classify_climb_fire_state(fire_rule)`
  三态（`battle` = `_is_active_battle_entry()` / `ready` = 挑战键可见 / `unknown` = 过渡帧）+
  `_wait_climb_fire_state(fire_rule, timeout=ACTIVITY_FIRE_POST_CLICK_TIMEOUT)` 有界轮询（`'timeout'`
  既不当 success 也不当 failure）。主循环 `for attempt in range(1, ACTIVITY_FIRE_MAX_TRIES+1)` +
  `Timer(ACTIVITY_FIRE_TIMEOUT)`：ready 态每 attempt 独立 `random_delay(*REACTION_FIRE)` → `sleep` →
  fresh `screenshot` → 二次确认挑战键仍在才 `appear_then_click(fire_rule, interval=1)`，reaction 期间
  离开 ready / 按钮消失 → 不点旧坐标；用尽 → `logger.warning` + `return False`（caller 转
  `ActivityResourceNotEnough`）。`import random` 删除（无其它用途）。
- **新 `_activity_challenge_safe_break(action_type, destination, *, repeat_completed)`**：唯一
  `try_fatigue_break` 调用点。fresh screenshot → 当前页 == destination 且挑战键 positive →
  `try_fatigue_break(safe=True, repeat_completed=..., deadline=start_time+limit_time_v)` → 若真休息 /
  发呆过（返回非 None）：fresh screenshot 重新确认「仍在挑战页 + 挑战键仍在 + 资源 OCR 仍允许」，
  页面变化 → 返回 False，资源耗尽 → `raise ActivityResourceNotEnough`。
- **新 `_drain_activity_settlement(action_type, destination)`**：`run_general_battle` 返回后调用。
  每次点 `self._sample_settlement_click(self.C_RANDOM_DEFAULT)`（复用 GeneralBattle Settlement V3
  采样入口 + `random_default` 大安全区，不新造坐标 / 区域 / `random.randint` / `RuleClick`），间隔
  `random_delay(*self.SETTLEMENT_CLICK_INTERVAL_RANGE)`；直到 `get_current_page()==destination` 且
  挑战键可见（= cycle complete）或 `ACTIVITY_SETTLEMENT_MAX_CLICKS` / `Timer(ACTIVITY_SETTLEMENT_TIMEOUT)`
  用尽。弹窗消失本身不算成功；又落回战斗态 → 返回 False 交回外层。

### 未改

`RichManAct` / `FakeGodAct`（含 `_enter_fakegod_battle` 旧 `while True`）、`GeneralBattle`（Settlement V3
/ `is_in_battle` / `_handle_result` / `_settlement_click` / region 选择一字未改）、`BaseAct.before_run`
的 `page_battle_result` recognizer monkeypatch（P1 技债，本轮不依赖它改动）、其它任务。
`RealmRaid` / `Exploration` / `Kekkai` / `SwipeEndpoint` / `TouchSwipeModel` / `Navigation` /
`GeneralInvite` / `RyouToppa` / `Orochi` / `EvoZone` 未碰。

### 验证

`tests/test_activity_shikigami_climb.py` 新增 46 用例（入口新旧图标优先级 + navigation reaction、
`_is_active_battle_entry` 窄语义、FIRE 三态 + bounded（fire 不出现 / reaction 期间消失 / post-click
持续 unknown 都有界、无 stale click、≤ MAX_TRIES）、Fatigue safe break（不在挑战页 / 挑战键未就绪
→ 不 fatigue；首轮 `repeat_completed=False`；休息后 fresh revalidate；休息中资源归零 raise；唯一
调用点）、macro-idle 无 stack、settlement drain 复用 `C_RANDOM_DEFAULT` + 有界 + 正向确认回挑战页 +
弹窗消失≠成功 + battle-entry 重现则 defer、cycle-complete 边界、RichMan/FakeGod/GeneralBattle 未改）。

targeted：`tests.test_activity_shikigami_climb` 46 OK → `test_general_battle_settlement` /
`test_general_battle_timing` / `test_reaction_timing_batch1` / `test_fatigue` / `test_fire_reaction_fsm` /
`test_general_invite_challenge_reaction` / `test_second_batch_fire_fsm` 合计 305 OK →
`compileall -q module tasks tests dev_tools` OK → 完整 `unittest discover -s tests`
**`1403/1403 OK`**（`1357 → 1403`，+46 全为新测试文件，0 regression）→ `git diff --check`：本轮 3
个生产代码文件干净（全仓其余命中项——`docs/DEVELOP_LOG.md:5267/5333`、`ActivityShikigami/assets.py`
自动生成注释尾空格、`GeneralBattle/assets.py` / `KekkaiUtilize/assets.py`——均为本轮之前已有 WIP，
不清理）。

### Git

分支 `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。未 commit / push / merge /
reset / clean / stash / checkout / restore。本轮改动：`tasks/ActivityShikigami/page.py`（`M`）、
`tasks/ActivityShikigami/base_act.py`（`M`）、`tasks/ActivityShikigami/activities/normal.py`（`M`）、
`tests/test_activity_shikigami_climb.py`（`??` 新，46）、`docs/` 五份（`AI_CONTEXT` §4.62 + §7 +
timing 分层 / `DECISIONS` D001「§4.62」补记 + 「活动体力·门票挑战仍不接」划线 / `ROADMAP` 「活动
体力 / 门票挑战 FIRE + Fatigue」条 + Level C 区新 bullet / `ARCHITECTURE` Fatigue consumer 4 处 /
本 `DEVELOP_LOG`；`TESTING` 无需更新——无新测试级别 / 验证规则 / 真机要求变化，PROVISIONAL 参数
Level C 待验已由既有长期规则覆盖）。`tasks/ActivityShikigami/assets.py` + `as/**` PNG/json +
`as/page/page_main_goto_act_2.png` 是**用户本轮之前放入**的新资产，AI 未改。未启动 MuMu / 游戏 /
OCR / 设备。

### Level C（用户手动跑普通爬塔连续 5~10 轮）

见 `docs/ROADMAP.md` Level C 区新增「ActivityShikigami 当期普通爬塔线适配 Level C 验收」条：
庭院 `main_goto_act_2` → `page_act`、Challenge Ready + Fatigue 只在挑战 ready 时、休息后 fresh
revalidate、FIRE reaction 0.4~0.8 不重复、窄 detector 不误判活动结算弹窗、`random_default` 点击安全、
资源 OCR 新 ROI 正确 + resource 0 优雅停、无无限循环、`ACTIVITY_FIRE_*` / `ACTIVITY_SETTLEMENT_*`
数值是否合适。未接大富翁 / 伪神降临。

## 2026-09-10 - ActivityShikigami 二层爬塔入口 page graph 适配（page marker / page graph）

### 目标

用户真机确认本期普通爬塔不是一层入口，真实链是：庭院 → `PAGE_MAIN_GOTO_ACT_2` → 活动主页
`page_act` → `I_TO_BATTLE_MAIN` → **中间「进入爬塔」页** → `I_TO_BATTLE_MAIN_2` → **真正爬塔挑战页**
→ `I_CHECK_BATTLE_PASS_2` → 原有普通爬塔流程。本轮只补「第二层爬塔入口」，不改 FIRE / REACTION_FIRE /
Fatigue / Challenge Ready / Resource OCR / Settlement / GeneralBattle / Repeat Cycle。

### 前置：2026-09-09 的 page_act 临时 hotfix 已全部撤回

上一条「page_act 临时 hotfix 撤回报告」已把 `_activity_main_marker_visible` / `page_act` recognizer
加 `I_TO_BATTLE_MAIN` / `I_CHECK_BATTLE_MAIN` ROI·threshold 放宽 / 爬塔页 priority 全部撤回，基线回到
`1403/1403`。本轮**不重做**这些，`page_act` 继续依赖自己的 `I_CHECK_BATTLE_MAIN`（原 ROI `(141,0,161,68)`
/ threshold 0.8）。

### 用户新增资产（本轮之前，用户用 `assets_extract` 生成）

- `I_TO_BATTLE_MAIN_2` = `RuleImage(roi_front=(11,92,252,80), roi_back=(0,74,281,105), threshold=0.8,
  file="./tasks/ActivityShikigami/as/climb/climb_to_battle_main_2.png")` —— 252×80「战斗·虚无精锐」进入
  按钮，描述「进入爬塔主页面的第二层入口」。在 `assets.py` + `as/climb/pages.json`。
- `I_CHECK_BATTLE_PASS_2` = `RuleImage(roi_front=(151,18,134,40), roi_back=(141,0,157,67), threshold=0.8,
  file="./tasks/ActivityShikigami/as/climb/climb_check_battle_pass_2.png")` —— 本期爬塔页标题横幅
  「虚无精锐」，ROI 与旧 `I_CHECK_BATTLE_PASS` 相同、只是模板换本期文字。

### 修改（2 个生产文件 + 测试，全 task-local）

**`tasks/ActivityShikigami/page.py`**
- 新增 task-local 中间页 `page_climb_main = Page(ActivityShikigamiAssets.I_TO_BATTLE_MAIN_2)` ——
  positive marker = 该页**稳定存在**的进入按钮（不是「上一页按钮消失」），它同时是
  `page_climb_main → page_climb_*` 的边动作。`page_climb_main.connect(page_act,
  GlobalGameAssets.I_UI_BACK_YELLOW, key='climb_main->activity')` 作 recovery。
- `page_climb_ap` / `page_climb_pass` recognizer：`all_of(I_CHECK_BATTLE_PASS, MODE)` →
  `all_of(any_of(I_CHECK_BATTLE_PASS_2, I_CHECK_BATTLE_PASS), MODE)` —— 本期新 marker primary +
  旧 marker legacy fallback，仍 `all_of` 带 mode 标志。静态验证互斥：只 `I_TO_BATTLE_MAIN_2` 命中时
  `page_climb_ap/pass.recognizer.evaluate` 为假，只 climb 页 marker 命中时 `page_climb_main` 为假 ——
  **不靠 priority**（`page_act` 70 / `page_climb_*` 全 50，均未动）。
- climb 页 yellow-back 边从 `→ page_act` 改为 `→ page_climb_main`（`climb → climb_main → activity`）。

**`tasks/ActivityShikigami/activities/normal.py` `setup_climb_pages`**
- 多 `resolve_page(pages.page_climb_main)`（局部名 `page_mid`）。
- `page_act.connect(page_mid, I_TO_BATTLE_MAIN, key='activity->climb_main')` 取代原
  `page_act.connect(page_ap/page_pass, I_TO_BATTLE_MAIN, key='activity->climb_ap'/'activity->climb_pass')`。
- 新增 `page_mid.connect(page_ap, I_TO_BATTLE_MAIN_2, key='climb_main->climb_ap')` +
  `page_mid.connect(page_pass, I_TO_BATTLE_MAIN_2, key='climb_main->climb_pass')`。
- mode 切换（`page_ap`/`page_pass` 的 `conditional_action` enter-failure hook + `I_CLIMB_MODE_SWITCH`
  互切边）不变。

**business boundary 天然保持（未改任何业务代码）**：`_run_climb_type` 业务分支仍
`if current_page == destination:`（`destination` = `page_climb_ap/pass`，recognizer 需
`I_CHECK_BATTLE_PASS_2/PASS` + mode）；中间页只有 `I_TO_BATTLE_MAIN_2` 不满足 →
`_sync_climb_penta_pass` / `_activity_challenge_safe_break`（Fatigue）/ `_climb_resource_available`（OCR）/
`_enter_climb_battle`（FIRE）/ `_drain_activity_settlement` 都不会在中间页触发。Challenge Ready 仍是
`_climb_fire_rule` = `I_ACT_FIRE` / `I_AS_BOSS_FIRE`，与 `I_TO_BATTLE_MAIN_2` 无关。

### 未改

`page_act` recognizer / priority / threshold / ROI（不重做已撤回的 hotfix）；`goto_activity_entry` /
`_activity_entry_visible` / `REACTION_NAVIGATION`；FIRE / `REACTION_FIRE` / bounded FIRE /
`_is_active_battle_entry`；Fatigue / `_activity_challenge_safe_break` / `_fatigue_owns_macro_idle`；
Resource OCR；Settlement / `_drain_activity_settlement` / `C_RANDOM_DEFAULT` 复用；GeneralBattle；
Repeat Cycle；RichMan / FakeGod；`page_climb_ap100` / `page_climb_boss` edge（ap/pass 之外，非本期
production 路径——boss 是否也有中间页留 Level C）。其它任务未碰。

### 验证

`tests/test_activity_shikigami_climb.py` 新增 `SecondLayerClimbEntryTest`（12）：新资产存在、
`page_climb_main` 自有 positive marker（= `I_TO_BATTLE_MAIN_2`，不含 climb 页 / Challenge Ready
marker）、recovery back-edge、climb 页 recognizer 新 primary + legacy fallback + 带 mode + 新 marker
在前、中间页 vs climb 页互斥（`recognizer.evaluate` 三组场景）、`page_act` recognizer·priority 未动、
`setup_climb_pages` 两层边 + 旧直连边已移除 + mode 切换保留 + `resolve_page(page_climb_main)`、
business 只在 `== destination` 分支跑、Challenge Ready marker 是 fire_rule 不是 `I_TO_BATTLE_MAIN_2`。

targeted `tests.test_activity_shikigami_climb` `46 → 58` OK → `compileall -q module tasks tests dev_tools`
OK → 完整 `unittest discover -s tests` **`1403 → 1415` OK**（+12，0 regression）→ `git diff --check`
（本轮 `page.py` / `normal.py` / 测试文件）干净。

### Git

分支 `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。未 commit / push / merge /
reset / restore / checkout / clean / stash。本轮改动：`tasks/ActivityShikigami/page.py`（`M`）、
`tasks/ActivityShikigami/activities/normal.py`（`M`）、`tests/test_activity_shikigami_climb.py`（`??`，
`46 → 58`）、`docs/` 四份（`AI_CONTEXT` §4.62 + §7 / `DECISIONS` D001「§4.62」补记 + 测试行 /
`ROADMAP` 「已完成」行 ①b + Level C 区 ① / 本 `DEVELOP_LOG`；`ARCHITECTURE` 无需更新——调用链 /
公共层 / 架构级 API 未变，只是 ActivityShikigami task-local page graph 细节；`TESTING` 无需更新——
无新测试级别 / 验证规则 / 真机要求变化）。`assets.py` + `as/climb/pages.json` + 两张新 PNG 是
**用户本轮之前生成 / 放入**的新资产，AI 未改。未启动 MuMu / 游戏 / OCR / 设备。

### Level C

见 `docs/ROADMAP.md` Level C 区更新的 ①：先确认二层导航链跑通（无 unknown recovery 退回庭院、
climb 页 yellow-back 走 `climb → climb_main → activity` 正确、boss/ap100 是否也有中间页），再继续
FIRE / Fatigue / Settlement 观察。

## 2026-09-11 - RealmRaid `_fire_again()` 最后一次 attempt timing bug（Level C 真机失败 → 定位 → 修复）

### 背景

用户上一轮已用 READ ONLY 定位清楚一个真机失败：退四（`exit_four`）首战主动退出、`Lose` 之后
`RES_FIRE_AGAIN → RES_SHOW_AGAIN → RES_FRESH_ENSURE`，游戏已实际进入 `page_battle_prepare`（右下角
「准备」按钮正常出现），但日志：

```
Fire again: attempt 4, reaction 0.77s
Fire again: button gone during reaction, re-evaluate
WARNING | Fire again: bounded retry / timeout without entering battle
```

`_fire_again()` 判超时 `return False`，`run()` 的 `aborted` 分支走 `check_refresh()`（单帧快速 False，
因为活的战斗准备页上没有 RealmRaid 九宫格「刷新」按钮）后 `success=False; break`，任务异常遗留在
`page_battle_prepare`。

READ ONLY 定位已排除「`page_battle_prepare` 不是合法 success state」这个可能——`_is_active_battle_entry()`
= `is_in_prepare(False) or is_in_real_battle(False)` 与 `page_battle_prepare` 的页面 recognizer 逐字
同源。真正根因：`_fire_again()` 里「reaction 后 fresh screenshot 发现 `I_FIRE_AGAIN` 已消失」这条分支
此前是裸 `continue`，没有像它的兄弟分支（点击前「未就绪」）一样先调用已有的
`_wait_again_entered_battle()` 有界确认。非最后一次 attempt 靠下一轮循环顶部的
`_is_active_battle_entry()` 隐式补一次确认掩盖了这个缺口；但 `attempt == RR_AGAIN_MAX_TRIES`（最后一
次）没有下一轮，`for` 循环直接耗尽退出——如果这一刻恰好是「按钮已消失、`page_battle_prepare` marker
尚未渲染完成」的真实过渡帧，就会直接判超时，白白丢弃一次本该成功的「再次挑战」。

### 本轮范围

只实施这一处已定位清楚的修复；不处理 `fire()` 里同构的裸 `continue`（当前 Level C 证据只指向
`_fire_again()`）；不新增 `aborted` 后 recovery / `run_general_battle` quick_exit fallback / navigator
`page_battle_prepare` edge / `close_unknown_pages` GB_EXIT closer；不改 GeneralBattle 主流程。

### 代码改动（1 文件，1 分支）

**`tasks/RealmRaid/script_task.py::_fire_again`**

reaction 后「按钮消失」分支从裸 `continue` 改为先调用 `_wait_again_entered_battle()`：

```python
if not self.appear(self.I_FIRE_AGAIN, threshold=0.8):
    logger.info('Fire again: button gone during reaction, re-evaluate')
    state = self._wait_again_entered_battle()
    if state == 'battle':
        logger.info('Fire again: entered battle')
        return True
    continue
```

复用既有 `RR_AGAIN_POST_CLICK_TIMEOUT`（未新增 timeout 常量）。同步更新 `_fire_again` docstring 记
Level C 修复说明。

### 未改（按用户要求严格锁定）

`_is_active_battle_entry()` / `is_in_prepare()` / `is_in_real_battle()` / `is_in_battle()`——`_fire_again`
继续用窄 detector，**不**因这次真机证据回退成宽 `is_in_battle()`（失败结算页 `I_FALSE` 会让宽 detector
恒 True，见 §4.56 / `docs/DECISIONS.md` D001 补记「Battle Lifecycle Detector ≠ New Battle Entry
Detector」，这条既有设计本轮继续遵守）。`fire()`（RealmRaid 所有目标共用的首次挑战入口，`RR_FIRE_*`）
里「reaction 期间 FIRE 消失」分支有完全相同的裸 `continue` 结构，本轮不动。`run()` 的 `aborted` 恢复
分支、GeneralBattle、navigator、asset、matcher、新 timeout 常量均未新增/未改——本修复让 attempt 4 能
正确识别 `page_battle_prepare` 并 `return True`，从根本上不再走到 `aborted` 分支，`run()` 侧的兜底本
轮不需要动。

### 测试

新增 `tests/test_realm_raid_state.py::FireAgainLastAttemptReactionGoneTest`（3）：
- CASE 1（核心回归）：attempt 1~3 的 gone 分支 `_wait_again_entered_battle()` 都判 `'timeout'`（继续
  下一 attempt），attempt 4（`RR_AGAIN_MAX_TRIES`，最后一次）gone 分支判 `'battle'` → `_fire_again()`
  必须 True，不落到 bounded timeout warning——精确复现真机日志的 `attempt 4` → `button gone` →
  `entered battle` 顺序（测试运行时日志逐字重现该顺序）。
- CASE 2：`_wait_again_entered_battle()` 一直不给 `'battle'`（`'timeout'` / `'failure_page'` 混合）→
  仍遵守 bounded retry，最终 False，调用次数恰好 = `RR_AGAIN_MAX_TRIES`，不形成无界循环。
- 源码形态锁定：gone 分支必须调用 `_wait_again_entered_battle()` 且认可其 `'battle'` 返回，防止本修
  复被静默回退成裸 `continue`。
- CASE 3（`_is_active_battle_entry()` 未被改宽、失败结果页 `I_FALSE` 不当新战斗）已有既有
  `ActiveBattleEntryContractTest` 完整覆盖（`test_helper_uses_narrow_prepare_or_real_battle_only` /
  `test_result_reward_only_frame_is_not_active_battle` / `test_i_false_frame_does_not_short_circuit_to_success`
  等），未重复造同义测试。

`tests.test_realm_raid_state` targeted `107 OK`（含新增 3）→ `tests.test_fire_reaction_fsm` /
`tests.test_general_battle_settlement` / `tests.test_general_battle_timing` /
`tests.test_realm_raid_state` 合并回归 `212 OK` → `compileall -q tasks/RealmRaid/script_task.py
tests/test_realm_raid_state.py` OK → 完整 `unittest discover -s tests` **`1415 → 1418` OK**（+3，
0 regression）→ `git diff --check`（本轮两个改动文件）干净。

### Git

分支 `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。未 commit / push / merge /
reset / restore / checkout / clean / stash。本轮改动：`tasks/RealmRaid/script_task.py`（`M`，既有多
轮 WIP 之上追加这一处分支修复 + docstring）、`tests/test_realm_raid_state.py`（`??`，既有多轮 WIP 文
件，追加 `FireAgainLastAttemptReactionGoneTest`）、`docs/` 三份（`AI_CONTEXT` 新增 §4.63 + 更新 §7
基线 / `ROADMAP` 「已完成」表新增一行 + Level C 区更新对应条目 / 本 `DEVELOP_LOG`；`ARCHITECTURE` 无
需更新——未新增分层 / 调用链 / 公共层 API，只是 RealmRaid task-local 一处控制流补丁；`DECISIONS` 无需
更新——未新增 ADR，只是把既有 D001「Battle Lifecycle Detector ≠ New Battle Entry Detector」/ 既有
bounded-retry-with-confirmation 契约实现补完整，未改变任何长期决策；`TESTING` 无需更新——无新测试级
别 / 验证规则 / 真机要求变化，仍是普通 bug regression characterization）。未启动 MuMu / 游戏 / OCR /
设备。

### Level C

真机重新验证：退四首战主动退出后每一次「再次挑战」（尤其最后一次 attempt）reaction 后按钮消失时，
是否能在 `RR_AGAIN_POST_CLICK_TIMEOUT=3` 内正确等到 `page_battle_prepare` 渲染完成并接管；若真机
仍观察到类似「最后一次 attempt 被裸 continue 吞掉」的现象出现在 `fire()`（普通目标首次挑战），再
评估是否对 `fire()` 做同构收口——本轮按最小范围不动。

## 2026-09-11 - KekkaiUtilize Scheduler v1：静默窗口 + 短期 retry cooldown 随机化

### 背景

上一轮 READ ONLY Inventory（`docs/DEVELOP_LOG.md` 2026-09-10 同名条）还原出 KekkaiUtilize 真实调度
链：`BaseTask.set_next_run` 只是 `Config.task_delay()` 的薄包装；当前 5 处 `set_next_run` 出口各自
硬编码 5/10/20 分钟或走 OCR 剩余寄养时间；项目已有 AntiBan 全局睡眠窗
（`script.py::_in_sleep_window`/`_next_time_point`，内存覆盖、无持久化、无 jitter）与
Server-Update 全局阻塞窗（`tasks/Restart/server_update.py`，`task_delay(target=)` 持久化、固定
09:15 无 jitter）两条"时间窗"先例，但都不是"单任务 + 带随机恢复抖动"的形状。

本轮用户给出最终业务决策：静默窗口默认 00:00~07:00；短期 retry（"没有达标卡"= 跨区+同区搜索完成后
没找到符合「目标卡种 + 收益阈值」的结界卡，以及好友列表刷新失败等）统一改随机 5~30 分钟；正常寄养
的 OCR 剩余时间调度必须逐字保留；quiet normalization 优先于 cooldown，两者不能叠加两次；`run()`
入口需要一道 task-local 防御，即使 scheduler 意外在静默窗口唤醒任务也要立即拒绝进入业务。

### 本轮范围

只实施 KekkaiUtilize 的调度层（quiet window + cooldown 随机化 + 正常寄养调度保留 + 入口 guard）。
不实施业务精简（不领奖 / 满级检查 / 替换检查，下一轮）、不改好友扫描 / 卡种筛选 / 收益阈值 / OCR、
不改 `Script.get_next_task()` / AntiBan / 通用 `TaskScheduler`、不碰 RealmRaid（§4.63 Level C 仍
pending，本轮未触碰）。

### 新增纯函数模块

**`tasks/KekkaiUtilize/scheduling.py`**（新文件，无设备 / OCR / task config object 依赖）：

- `is_in_quiet_window(t, start, end) -> bool`：`[start, end)` 半开区间；`start < end` 普通区间、
  `start >= end` 自动按跨午夜处理、`start == end` 视为空窗口。
- `next_quiet_window_end(now, end) -> datetime`：从 `now` 起下一个 `end` 时刻，今天已过则顺延明天。
- `normalize_for_quiet_window(candidate, *, enable, quiet_start, quiet_end, jitter_seconds) -> datetime`：
  candidate 落窗才顺延到窗口结束 + `jitter_seconds`，否则原样返回；`jitter_seconds` 由调用方预采样
  传入，本函数保持 100% 确定性、不产生随机数。

算法思路与 `script.py::Script._in_sleep_window`/`_next_time_point`（AntiBan）一致（同样是「跨午夜
安全的纯时间函数」），但**独立实现，不 import `script.py`**——避免把一个 task-local 需求绑死到
顶层 orchestrator。

### `ScriptTask` 新增 7 个 task-local helper（`tasks/KekkaiUtilize/script_task.py`）

`_is_in_quiet_window` / `_quiet_jitter_seconds`（`random_int(jitter_min*60, jitter_max*60)`）/
`_normalize_quiet_target`（近纯函数，不调 `set_next_run`）/ `_build_retry_target`
（`now + random_int(cooldown_min*60, cooldown_max*60)`）/ `_schedule_target`（candidate → normalize
→ `set_next_run(target=final, server=False)`，唯一持久化出口）/ `_schedule_retry`（短期失败统一
出口：一个 owner、一次随机）/ `_guard_quiet_window`（`run()` 入口守卫）。

### 5 处退出改造

| # | 场景 | 旧逻辑 | 新逻辑 |
|---|---|---|---|
| 1 | `check_utilize_add` 5 次尝试未找到合格结界卡 | `target=now+5min` 硬编码 | `_schedule_retry('5 次尝试仍未找到合格结界卡')` |
| 2 | `check_utilize_add` 已在寄养（OCR 剩余时间） | `set_next_run(target=next_time)` | **逐字保留** OCR 剩余时间 + `min_run_interval` 地板计算，只把 `set_next_run` 换成 `_schedule_target(next_time)` 接入静默窗口归一化 |
| 3 | `_record_utilize_failure` 连续 3 次蹭卡失败 | `target=now+10min` | `_schedule_retry(f'连续 3 次蹭卡失败（最后一次原因: {reason}）')` |
| 4 | `_finish_low_value_utilize` 跨区+同区都无达标候选 | `target=now+20min` | `_schedule_retry('跨区 + 同区都没有达标候选')`；日志改为明确"未找到符合『目标卡种 + 收益阈值』的结界卡"，不再写模糊的"没有卡" |
| 5 | `utilize_enable=False`（蹭卡业务关闭） | `set_next_run(finish=True, success=True)`（走通用 `success_interval=6h`） | **不改**——用户明确要求不动其间隔语义；它走 `task_delay` 的 `success=True` 相对区间分支而非自算 target |

`run()` 最开始新增 `if self._guard_quiet_window(): raise TaskEnd`——静默窗口内立即重排 next_run 并
结束，不进入任何 `goto_page` / 截图 / OCR / 好友搜索 / 点击。

### `server` 参数核对

逐个核对 5 个出口是否依赖 `server=True` 的 `server_update` jitter 叠加语义：`UtilizeScheduler`
未覆盖基类 `Scheduler.float_time` 默认值 `Time(0,0,0)`，`Config.task_delay()` 里
`random.randint(0, float_seconds)` 恒为 0——此前隐式 `server=True`（#1/#2 未显式传参默认走它）
在当前配置下本就是 no-op，无业务依赖。因此本轮统一改为显式 `server=False`，避免未来用户把
`float_time` 配置成非零值时意外污染这几个已经算好的 target。

### 配置

**`tasks/KekkaiUtilize/config.py::UtilizeScheduler`**（继承 `Scheduler`）新增：

```python
quiet_window_enable: bool = True
quiet_start: Time = Time(hour=0, minute=0, second=0)
quiet_end: Time = Time(hour=7, minute=0, second=0)
quiet_resume_jitter_min: int = 5
quiet_resume_jitter_max: int = 30
cooldown_min: int = 5
cooldown_max: int = 30
```

类型沿用 `AntiBan.sleep_start`/`sleep_end` 同一套 `Time`（`WithJsonSchema({'type': 'time'})`），
不发明新的 time-range 类型。

**跨字段边界校验踩了一个坑**：最初写成 `@model_validator(mode='after')` 抛 `ValueError`——本地
`toolkit/python.exe -c "..."` 实测直接 `IndexError: tuple index out of range`。根因：
`tasks/Component/config_base.py::ConfigBase.__init__` 的异常恢复逻辑是
`exc.errors()[0]['loc'][0]` 取出越界字段名做默认值回退，只覆盖 pydantic 内建
`ge`/`gt`/`le`/`lt` 单字段约束错误；`model_validator` 产生的是模型级错误（`loc` 为空元组），
`()[0]` 直接崩溃。改用 `@field_validator('cooldown_max'/'quiet_resume_jitter_max', mode='after')`
+ `info.data.get('cooldown_min'/'quiet_resume_jitter_min')`（沿用 `tasks/Dokan/config.py` 既有
`@field_validator(..., mode='after')` 写法）——错误 `loc` 落在具体字段上，`ConfigBase.__init__`
遇到 `'value_error'` 类型时走 `raise exc`（正常抛出 `ValidationError`，不再 `IndexError`）。
本次发现已写入 `docs/DECISIONS.md` D023，作为对 `ConfigBase` 子类做跨字段校验的长期约束。

### 随机源

`_quiet_jitter_seconds` / `_build_retry_target` 均调用 `module.base.utils.random.random_int`
（`SystemRandom`），未引入 stdlib `random.Random()`。`Config.task_delay()` 里既有的 stdlib
`random.randint`（`server_update` 分支）本轮未动、未复制其写法。

### 测试

- 新增 `tests/test_kekkai_utilize_scheduling.py`（16）：`is_in_quiet_window`/`next_quiet_window_end`
  边界 + `normalize_for_quiet_window` CASE A~H 全覆盖（quiet disabled / 不落窗 / 落窗+jitter /
  内侧边界 / `[start,end)` 右开边界 / 跨午夜三种场景），纯函数无需 mock。
- `tests/test_kekkai_utilize_state.py` 新增 5 个测试类（19）：`SchedulingHelperUnitTest`（7，
  task-local helper 正确读 config、调用统一随机源）；`NoEligibleCardRetryExitTest`（3，含
  "23:55 完成 cooldown 20min → candidate 次日 00:15 落窗 → 次日 07:10" 跨天落窗场景 + 日志文案
  锁定）；`NormalUtilizeSchedulingTest`（3，OCR 剩余时间落窗 / 不落窗 / `min_run_interval` 地板
  三种，落窗时确认恰好只采样一次抖动、不落窗时确认零随机数调用即"不套 cooldown"）；
  `RunEntryQuietGuardTest`（2，`run()` 全链路验证 quiet 内拦截时 `goto_page`/OCR/业务方法均未
  调用 + `TaskEnd`、quiet 关闭时正常进入原业务链）；`RetrySingleOwnerTest`（4，三个短期失败出口
  都走 `_schedule_retry`，源码级锁定各出口不各自调 `random_int`）。

`tests.test_kekkai_utilize_state` + `tests.test_kekkai_utilize_scheduling` 单独跑 OK →
`tests.test_kekkai_utilize_threshold` / `test_kekkai_k4_projection` / `test_kekkai_k4_selected_anchor`
/ `test_kekkai_activation_state` 合并回归 205 OK（0 regression）→ `compileall -q tasks/KekkaiUtilize
tests/test_kekkai_utilize_state.py tests/test_kekkai_utilize_scheduling.py` OK → 完整
`unittest discover -s tests` **`1418 → 1453` OK**（+35，0 regression）→ `git diff --check`（本轮
5 个改动/新增文件）干净。

### Git

分支 `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。未 commit / push / merge /
reset / restore / checkout / clean / stash。本轮改动：`tasks/KekkaiUtilize/config.py`（`M`）、
`tasks/KekkaiUtilize/script_task.py`（`M`，既有多轮 WIP 之上追加）、`tasks/KekkaiUtilize/scheduling.py`
（`??` 新文件）、`tests/test_kekkai_utilize_state.py`（`??`，既有多轮 WIP 文件，追加 5 个测试类）、
`tests/test_kekkai_utilize_scheduling.py`（`??` 新文件）、`docs/` 四份（`AI_CONTEXT` 新增 §4.64 +
更新 §7 基线 / `ROADMAP`「结界卡流程精简 + 静默窗口 / cooldown」节更新状态 + 「已完成」表新增一行 +
Level C 区新增一条 / `DECISIONS` 新增 **D023** / 本 `DEVELOP_LOG`；`ARCHITECTURE` 无需更新——未新增
调用链分层，只是 KekkaiUtilize task-local 的 `candidate → normalize → set_next_run` 管线；`TESTING`
无需更新——无新测试级别 / 验证规则变化，仍是普通 characterization + 纯函数测试）。`tasks/KekkaiUtilize
/assets.py`/`utilize/image.json`/`utils.py` 等既有 `M` 是更早轮次 K4 工作的遗留 WIP，本轮未触碰。
`docs/DEVELOP_LOG.md` 既有 2 处 trailing-whitespace（`KekkaiUtilize` 相关历史条目）本轮未清理。
未启动 MuMu / 游戏 / OCR / 设备。

### Level C

00:00~07:00 静默窗口内 KekkaiUtilize 确实不会被真正启动（观察实际任务开始时间戳）；正常寄养后
`next_run` 仍符合 OCR 剩余寄养时间语义（quiet 归一化不改变非落窗场景的值）；短期 retry 5~30 分钟
随机分布体感；`quiet_resume_jitter_min/max`、`cooldown_min/max` 默认值是否合适；candidate 跨天落窗
顺延场景（23:xx 完成 → 次日 07:xx）在真机上是否符合预期。

## 2026-09-11 - KekkaiUtilize 业务开关配置：满级检查/替换新增开关，寄养奖励沿用既有字段，OASX 0 修改

### 背景

用户下一步要落地 §4.64 末尾定位的两项业务简化（寄养结束后不领奖、不再检查满级/替换），但本轮明确
要求先优先尝试"只改后端 config，不改 OASX"——先 READ ONLY 验证 OASX 是否会根据后端 schema 自动渲染
`bool` 开关，只有确认无法自动显示才允许改前端。同时用户澄清：这两项不是简单删代码，而是"旧能力
保留、改成可配置开关"。

### 第一阶段：OASX 配置生成机制 READ ONLY 核实

在 `d:\oas_xy\OASX`（分支 `master`，HEAD `035aece1242bf22ed7257814908c2f031fc94fc6`）逐层追踪：

1. `lib/modules/home/widgets/task_parameter_panel.dart` —— `TaskParameterPanel` 不是
   KekkaiUtilize 专属页面，是所有任务共用的**通用**容器，内部渲染
   `Args(scriptName:..., taskName:..., stagingMode: true, ...)`。
2. `lib/modules/args/` —— `Args` 也是通用组件：`ArgsController.loadGroups()` 调
   `ApiClient().getScriptTask(config, task)` 拉取一份 JSON，每个字段解析成 `ArgumentModel`
   （`title`/`value`/`type`/`description`/`enumEnum`/`minimum`/`maximum`/`defaultValue`，
   `type` 直接读 JSON 的 `type` 字符串，无任何硬编码映射）。
3. `lib/modules/args/widgets/argument_view.dart::_buildFormSection()` —— `switch (model.type)`
   通用分发：`'boolean' => Checkbox(value: model.value, onChanged: ...)`、`'integer'`/`'number'`
   走文本框、`'enum'` 走下拉框、`'time'`/`'time_delta'`/`'date_time'` 分别走对应 picker
   （与后端 `tasks/Component/config_base.py` 的 `Time`/`TimeDelta`/`DateTime` Annotated 类型
   逐字对应）。**全仓 grep "kekkai" 只命中菜单 i18n 文案（`cn_menu.dart`）和 BehaviorTrace 展示
   名（`behavior_display_names.dart`），没有任何 KekkaiUtilize 专属配置页面代码。**
4. 后端 `module/config/config_model.py::ConfigModel.script_task(task)` —— `schema =
   task.model_json_schema()`（pydantic 内建）→ `merge_value()` 把每个字段的 schema `type`
   （`bool`→`"boolean"`）连同 `title`/`description`/`default`/当前 `value` 原样组装成给前端的
   JSON，**没有字段白名单**，唯一的隐藏机制是显式 `dynamic_hide(*fields)`
   （`field_serializer` + `context={'hide': True}` 输出哨兵 `0xABCDEF` 后被跳过）。
   `tasks/KekkaiUtilize/config.py` 当前未对任何字段调用它。

本地验证（`toolkit/python.exe -c "..."`）：`UtilizeConfig.model_json_schema()['properties']
['auto_replace_max_level']['type']` 与 `['utilize_harvest']['type']` 均为 `'boolean'`——与
`ArgumentView` 的 `'boolean' => Checkbox` 分支精确匹配。

**结论：BRANCH A 成立，OASX 需要 0 代码修改。** 完整依据链与"业务能力退休 = 加开关不删代码"的
长期约定已写入 `docs/DECISIONS.md` **D024**。

### `utilize_harvest`（是否领取寄养奖励）

字段已存在（`UtilizeConfig.utilize_harvest: bool = True`），`run()` 内
`if con.utilize_harvest: self.check_utilize_harvest()` 本就是配置驱动的。按上述链路核实，它
**本来就会**出现在 OASX 的 KekkaiUtilize 配置面板——**不新增第二个重复字段，不改默认值**（维持
`True`，避免静默改变正在生产运行的用户既有行为）。已知间隙：OASX `cn_parts/*.dart` 目前没有该字段
的中文翻译，界面会显示英文 Title Case（`"Utilize Harvest"`）——纯文案缺口，不影响开关是否显示，
按"确认能自动显示就不改 OASX"的口径本轮不补。

### 新增 `auto_replace_max_level`

`tasks/KekkaiUtilize/config.py::UtilizeConfig` 新增：

```python
auto_replace_max_level: bool = Field(default=False, description='auto_replace_max_level_help')
```

与 `utilize_harvest` 并列放在业务配置类 `UtilizeConfig`，不是调度配置类 `UtilizeScheduler`
（D023）——区分标准：「要不要执行这段业务逻辑」是业务开关，「什么时候执行/多久一次」才是调度字段。

`tasks/KekkaiUtilize/script_task.py::run()` 唯一改动点：

```python
# 查看育成满级：开关关闭时完全跳过，不检测、不卸下、不切换、不补位
if con.auto_replace_max_level:
    self.check_max_lv(con.shikigami_class, con.auto_fill)
```

`check_max_lv()` / `unset_shikigami_max_lv()` / `switch_shikigami_class()` / `set_shikigami()`
**全部原样保留**，方法体一字未改，只是唯一调用点加了这层开关。默认 `False`——新字段引入新行为时
默认关闭，不默认继承旧代码"无条件执行"的隐式行为，用户需要显式打开才启用满级检测/替换。

### 测试

新增 `tests/test_kekkai_utilize_state.py::MaxLevelAndHarvestSwitchTest`（8）：
- CASE1/2：`auto_replace_max_level` False/True，通过完整 `run()`（`_guard_quiet_window` mock 成
  `False` 与 Scheduler v1 解耦）验证 `check_max_lv` 不调用 / 调用一次且参数仍是
  `(shikigami_class, auto_fill)`。
- CASE3/4：`utilize_harvest` False/True 对 `check_utilize_harvest` 同理（此前无专门测试覆盖这条
  分支行为，本轮补齐，不是重复造同义测试）。
- CASE5：新字段 `auto_replace_max_level` 默认 `False`，旧字段 `utilize_harvest` 默认 `True` 不变。
- CASE6：完整 `KekkaiUtilize` config model 可 `model_dump()` / `model_json_schema()`，两个字段的
  `type` 均为 `'boolean'`——直接验证前端渲染依据成立。
- 源码形态锁定：`run()` 含 `if con.auto_replace_max_level:` / `if con.utilize_harvest:` 两条开关，
  且 `check_max_lv`/`unset_shikigami_max_lv`/`switch_shikigami_class`/`set_shikigami` 均未被删除。

`tests.test_kekkai_utilize_state.MaxLevelAndHarvestSwitchTest` 单独跑 8 OK →
Kekkai 全家桶（state + scheduling + threshold + K4×2 + activation）合并回归 213 OK（0 regression）
→ `compileall -q tasks/KekkaiUtilize tests/test_kekkai_utilize_state.py` OK → 完整
`unittest discover -s tests` **`1453 → 1461` OK**（+8，0 regression）→ `git diff --check`（本轮
两个改动文件）干净。

### Git

**Backend**：分支 `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。未 commit /
push / merge / reset / restore / checkout / clean / stash。本轮改动：
`tasks/KekkaiUtilize/config.py`（`M`）、`tasks/KekkaiUtilize/script_task.py`（`M`，既有多轮 WIP
之上追加两行）、`tests/test_kekkai_utilize_state.py`（`??`，既有多轮 WIP 文件，追加
`MaxLevelAndHarvestSwitchTest`）、`docs/` 四份（`AI_CONTEXT` 新增 §4.65 + 更新 §7 基线 /
`ROADMAP`「结界卡流程精简」节更新状态（"删除"改口为"配置开关控制"）+「已完成」表新增一行 /
`DECISIONS` 新增 **D024** / 本 `DEVELOP_LOG`；`ARCHITECTURE` 无需更新；`TESTING` 无需更新）。

**OASX**：分支 `master`，HEAD `035aece1242bf22ed7257814908c2f031fc94fc6`（未变）。**本轮 0 代码
修改**——未 commit / push / merge / reset / restore / checkout / clean / stash；工作区既有 33 处
（`M`/`??`）多轮 WIP 原样保留，未触碰、未 build、未部署。

未启动 MuMu / 游戏 / OCR / 设备。

### OASX 部署

**无需重新构建/部署前端**——两个字段（沿用的 `utilize_harvest` + 新增的
`auto_replace_max_level`）都由后端 schema 自动渲染，用户下次在 OASX 打开 KekkaiUtilize 任务配置
（重新拉取该任务的 `/args`）即可看到，不需要 `flutter analyze` / `flutter test` / release build /
部署到 `D:\oas_xy\OASX-V0.3.12\` / 更新 `OASX-V0.3.12.zip`。

### Level C

用户实际在 OASX 打开 KekkaiUtilize 任务配置，确认 `auto_replace_max_level` 开关（默认关闭）与
`utilize_harvest` 开关均可见可用、切换后 `check_max_lv`/`check_utilize_harvest` 的实际调用行为
与开关状态一致；确认 `utilize_harvest` 界面英文标题是否需要后续补中文翻译（可选，非阻断）。

## 2026-09-12 - GeneralBattle Settlement Micro-Burst v1：结算 Click Session + Anchor Persistence

### 背景

Settlement Contract V3（D014/D016，2026-09-03）已把结算点击收敛成三个 Large Safe Region
（`C_RANDOM_DEFAULT`/`C_RANDOM_SAVE_RIGHT`/`C_RANDOM_SAVE_BOTTOM`）+ 节流间隔，但通用结果页
（`I_WIN`/`I_DE_WIN`/`I_FALSE` 命中）首帧仍是写死的「强制两次点击，各自独立采样」
（`_advance_generic_result`），之后每一帧都退回「每次独立随机一个新点」的单次节流点击——不像
真人那样会在同一个位置连续点几下。用户本轮要求把这段升级为「同点连续点击」的 Micro-Burst
模型：总点击预算随机 2~4 次（上限，不是必须点满）、一次 blind burst 最多连点 2 次、每次
burst 后必须 fresh screenshot + 重新 classify、允许跨结算阶段保持同一 anchor 也允许概率换点，
且拟人点击必须服从既有 Settlement FSM，不能反过来放宽或破坏它。

### 本轮范围

只改 GeneralBattle 通用 Settlement（`_handle_result`/`_handle_reward` 及其内部点击推进逻辑）。
不碰：RealmRaid `fire()`/`_fire_again()` FIRE 契约、GeneralInvite FIRE、ActivityShikigami
task-local `_drain_activity_settlement()`、KekkaiUtilize、Navigator、FrameWait、
TouchSwipeModel、HABIT 全局模型、BehaviorTrace 架构、OASX、`device.click`/`appear_then_click`
全局语义。

### Settlement Click Session 契约

```
可点击 settlement state（page_battle_result 通用胜负 / page_reward 普通布局）
  ↓ 首次进入：采样 total_budget ∈ {2,3,4}（权重 50%/30%/20%）+ 首个 anchor
  ↓ micro-burst：1~2 次盲点（burst_size 均匀二选一，夹到剩余预算），同一 anchor，burst 内短间隔
  ↓ fresh screenshot + 重新 classify（既有 run_general_battle() 主循环天然提供）
  ↓ 仍是合法结算态 → 继续用剩余 budget；状态前向变化 → 按安全区域交集决定 anchor 保留/换点
  ↓ 到达 terminal（不再是 page_battle_result/page_reward）→ 立即销毁 session，budget 剩余作废
  ↓ budget 用尽但仍在结算态 → 本帧不再点击，交回既有节流 / FSM，不新增第二套无限等待
```

### 代码改动（1 文件 + 若干测试文件）

**`tasks/Component/GeneralBattle/general_battle.py`**：

- `BattleContext` 新增 7 个 `settlement_*` 字段（`settlement_session_active` /
  `settlement_click_budget` / `settlement_clicks_used` / `settlement_anchor` /
  `settlement_region_name` / `settlement_stage_name` / `settlement_anchor_switches`），随
  `_build_context` 初始化、`_reset_round_context`（连战开新一轮）清零。
- 新增类常量 `SETTLEMENT_BURST_CLICK_INTERVAL_RANGE = (0.10, 0.30)`（同一 burst 内两次盲点的
  间隔，独立于跨 burst 节流的 `SETTLEMENT_CLICK_INTERVAL_RANGE = (0.7, 1.0)`，不接 reaction
  timing / Fatigue）与 `SETTLEMENT_ANCHOR_KEEP_PROBABILITY = 50`（状态前向变化且安全时保留
  anchor 的概率，PROVISIONAL）。
- 从 `_sample_settlement_click`（保留不变，供非通用结果单次点击 / `_drain_activity_settlement`
  继续使用）拆出两个新原语：`_sample_settlement_point`（只采样不点击）/
  `_click_settlement_point`（只点击已采样好的坐标，不重新采样）。
- 新增 `_sample_settlement_budget`（单次 `random_int(1,10)` 分桶，不引入加权采样库）、
  `_sample_settlement_burst_size`（`random_int(1,2)`）、`_point_in_roi`（静态，安全区域交集
  校验）、`_start_settlement_session`（session 初始化）、`_advance_settlement_anchor`（状态
  前向变化时的 anchor 决策：不安全强制重采、安全按概率二选一且全 session 最多 1 次主动换点）、
  `_fire_settlement_burst`（节流到点才触发 1~2 次盲点）、`_settlement_burst_step`（统一入口，
  `_handle_result`/`_handle_reward` 每帧调用）。
- **删除** `_advance_generic_result`（旧固定两次点击序列），`_handle_result` 通用结果分支改调
  `_settlement_burst_step`；`_handle_reward` 普通奖励分支同理，`region_provider` 传
  `self._select_reward_region`（惰性调用，只在 session 初始化/状态刚切到 reward 时求值一次，
  避免其 80/20 随机分支被每帧重新掷骰子）。非通用结果标志分支、奖励特殊弹窗分支逐字未改。

**中途用户追加的验收标准（同一轮内完成）**：Settlement 的点击永远不能穿透到 Challenge/FIRE
页面——新增 `_teardown_settlement_session()`，在 `run_general_battle()` 主循环每帧 fresh
classify 之后、分发给具体 handler 之前调用：`page is not None and page not in
(page_battle_result, page_reward)` 就立即销毁 session 全部 7 个字段（`page is None` 的过渡性
丢帧不触发，避免误杀仍在进行中的 session）。这样连战场景里后续再出现的 `page_battle_prepare`/
`page_battle`，或该任务自己在 `run_general_battle()` 之外的目标选择/「再次挑战」页，都不可能
复用上一次结算 session 的残留 anchor/budget——任何新出现的 Challenge/FIRE 必须重新走它自己
完整的 FIRE contract。`_reset_round_context` 里原有的同一组字段重置继续保留，两层防御不冲突。

### 未改（按要求严格锁定）

`GeneralBattle.is_in_battle()`/`is_in_prepare()`/`is_in_real_battle()`；`run_general_battle()`
主循环与 `gb_page_handle_dict` 页面分发（只新增一次判定+一次销毁调用，未重排既有步骤顺序）；
`_handle_missing_battle_page` 2.5s 兜底；`_select_reward_region()` 本体（layout-aware 策略
未退化成统一 random_default）；`ActivityShikigami._drain_activity_settlement()`（task-local，
只调 `_sample_settlement_click`，不经过 `_handle_result`/`_handle_reward`/本 session，
`run_general_battle()` 返回之后才被调用，结构上完全独立）；RealmRaid `fire()`/`_fire_again()`
FIRE 契约（不同 owner）；KekkaiUtilize；Navigator；FrameWait；TouchSwipeModel；HABIT 全局模型；
BehaviorTrace 架构；OASX；`device.click`/`appear_then_click` 全局语义。

**波及但预期内**：RealmRaid 非 quick_exit 路径（`super()._handle_result()`）、ActivityShikigami
首个通用结果帧（`BaseAct._handle_result` 调 `super()`）等所有通过 `super()` 继承公共
GeneralBattle 结算的任务，会自然获得新的 Micro-Burst 行为——这是升级公共契约的必然结果，不是
误伤；已用 `tests.test_realm_raid_state`（107 OK）与 `tests.test_activity_shikigami_climb`
（58 OK）分别确认 FIRE / task-local drain 无回归。

### 测试

`tests/test_general_battle_settlement.py`：移除 `MandatoryDoubleClickTest`（旧固定两次契约，
9 例），新增 `NonGenericResultTest`（2，原有两条未改动测试迁移过来）、`SettlementMicroBurstTest`
（15：CASE1 同点双击 / CASE2 同一 anchor 只采样一次 / CASE3 状态前进+安全+随机保留 / CASE4
状态前进+安全+随机换点 / CASE5 不安全强制换点不计入主动换点 / CASE6 budget 是上限不是必须点满
/ CASE6b 用尽边界 / CASE7 直接从 reward 起步不报错 / CASE9+14 耗尽后重复轮询点击数冻结 /
CASE10 blind burst 硬上限 2 / CASE11 旧固定两次已移除不叠加 / CASE12 reward burst 用
`_select_reward_region` 做 provider / CASE13 Lose 与 Win 同路径 / budget 分布权重 + 范围）、
`SettlementSessionTeardownTest`（3：清空全部字段 / 未激活时 no-op / 驱动真实
`run_general_battle()` 两帧的端到端用例，日志证明 `Settlement session destroyed` 先于
`Battle result` 输出）。`tests/test_general_battle_timing.py`（`_settlement_ns` 补全新字段）、
`tests/test_reaction_timing_batch1.py`（`test_settlement_v3_has_no_confirm_delay` 改查新方法）、
`tests/test_ryoutoppa_c_area_1_point_opt_in.py`（`SettlementUntouchedTest` 改查新方法）同步更新。

`tests.test_general_battle_settlement`（65）+ `tests.test_general_battle_timing`（17）+
`tests.test_realm_raid_state`（107）+ `tests.test_activity_shikigami_climb`（58）+
`tests.test_ryoutoppa_c_area_1_point_opt_in`（25）+ `tests.test_reaction_timing_batch1`（34）
合并回归 306 OK → `compileall -q tasks tests` OK → 完整 `unittest discover -s tests`
**`1461 → 1472` OK**（+11，0 regression）→ `git diff --check`（本轮全部改动/新增文件）干净。

### Git

分支 `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。未 commit / push / merge /
reset / restore / checkout / clean / stash。本轮改动：
`tasks/Component/GeneralBattle/general_battle.py`（`M`，既有多轮 WIP 之上追加）、
`tests/test_general_battle_settlement.py`（`??`，既有 WIP 文件，大改）、
`tests/test_general_battle_timing.py`（`M`）、`tests/test_reaction_timing_batch1.py`（`??`）、
`tests/test_ryoutoppa_c_area_1_point_opt_in.py`（`??`）、`docs/` 四份（`AI_CONTEXT` 新增 §4.66
+ 更新 §7 基线 / `ROADMAP` 更新对应条目 / `DECISIONS` 新增 **D025** / 本 `DEVELOP_LOG`；
`ARCHITECTURE` 无需更新——未新增调用链分层，只是 GeneralBattle 内部结算点击策略升级；`TESTING`
无需更新——无新测试级别/验证规则变化）。`tasks/Component/GeneralBattle/assets.py`/
`gb/click.json`/`gb/gb_reward.png`/`gb/image.json` 及两张新 PNG 是更早轮次的遗留 WIP，本轮
未触碰。未启动 MuMu / 游戏 / OCR / 设备。

### Level C

通用战斗结束是否观察到同点连续点击行为；一次结算真实总点击是否落在 2~4 内；页面第二下就退出
结算后是否确实不再盲点；`page_battle_result → page_reward` 跳级 FSM 是否稳定不报错；anchor
保留/换点是否都发生在安全区域内；Reward 特殊 layout 是否仍被正确识别、不被 burst 误点；
Loss / Fire Again 路径是否不受影响；结算结束后进入下一次 Challenge/FIRE（连战下一场准备页，
或任务自己的目标选择/再次挑战页）时确认没有出现任何结算残留点击。
`SETTLEMENT_BURST_CLICK_INTERVAL_RANGE`/`SETTLEMENT_ANCHOR_KEEP_PROBABILITY`/budget 权重分布
均 PROVISIONAL，据真机数据调整时连带更新 `docs/DECISIONS.md` D025 与本文档 §4.66。

## 2026-09-12 - GeneralBattle Settlement Micro-Burst v1.1：Blind Burst → Observed Micro-Burst（Click → Observe → Decide）

### 背景

上一条目（v1）已经用主循环级 `_teardown_settlement_session()` 保证「确认离开结算后不再继续
点击」，但同一次 burst 内的两次盲点之间没有任何 fresh 页面观察，只隔一段 `time.sleep`。如果
第一下点击已经把页面从结算推进到 Challenge/FIRE（例如 Reward → 下一场 prepare），第二下盲点
仍可能在状态机重新截图/分类之前先落到新页面上——用户指出这是「Settlement 点击可能穿透到
Challenge/FIRE」的真实窗口，要求把人类真实行为建模进去：点击 → 观察页面反馈 → 没变化才在
同一位置补点，变了就立刻停手、把决定权交回状态机。

### 本轮范围

只改 v1 的「一次 burst 内第二下怎么决定要不要点」这一个环节。budget 2~4/权重 50-30-20、
anchor persistence + 安全区域交集、全 session 最多 1 次主动换点、Reward layout-aware 策略、
Loss 走同一路径、Activity 独立 drain、budget 是 ceiling、主循环级 teardown 入口——v1 的这些
既有契约本轮逐字未改。不碰 RealmRaid `fire()`/`_fire_again()`、GeneralInvite FIRE、RyouToppa
FIRE、Activity FIRE、`ActivityShikigami._drain_activity_settlement()`、KekkaiUtilize、
Navigator、FrameWait、TouchSwipeModel、HABIT 全局模型、BehaviorTrace 架构、OASX、
`device.click`/`appear_then_click` 全局语义。

### Observed Micro-Burst 契约（取代 v1 的 blind 第二下）

```
可点击 Settlement State
  ↓ 用当前 anchor 点击第 1 次（remaining>=1 时一定执行）
  ↓ desired_burst_size>=2 且预算未耗尽 → 短间隔（SETTLEMENT_BURST_CLICK_INTERVAL_RANGE，沿用
    v1 常量，不新增）→ fresh screenshot → _classify_general_battle_page()（转发既有
    GameUi.detect_page_in，不新造探测逻辑）
    ├─ 观察结果 == 点击前的 current_page（仍是同一个可点击 state）→ 允许用同一 anchor 补第 2 下
    ├─ 观察结果是另一个已知结算页（result/reward 之一，但已不是 current_page）→ 当前 burst
    │   立即结束，不补点；新 state 留给下一次 _settlement_burst_step 调用重新决定 anchor
    ├─ 观察结果是已知的非结算页（prepare/battle，即 Challenge/FIRE 相关）→ 立即
    │   _teardown_settlement_session()，不补点，不武装节流计时器
    └─ 观察结果是 Unknown（None）→ 不补点，也不 teardown，交回既有 bounded
        recovery/missing-page 处理
  ↓ 任何分支下一次调用最多点 2 次；第二下之后无论如何都交回主循环下一次 fresh classify
```

### 代码改动（1 文件 + 测试文件）

**`tasks/Component/GeneralBattle/general_battle.py`**：

- 新增私有方法 `_classify_general_battle_page(self) -> Page | None`：纯转发
  `GameUi.detect_page_in(self, page_battle_prepare, page_battle, page_battle_result,
  page_reward, include_global=False)`，与主循环用的是同一个 matcher/classifier，不新造第二套
  页面分类逻辑，也不接 FrameWait 的 changed/stable 像素级判定。
- `_fire_settlement_burst` 签名新增 `current_page: Page` 参数；内部逻辑从「预抽 burst_size==2
  就无条件连点两下」改为「第一下一定点，第二下的实际执行改由 mid-burst fresh 观察结果门控」，
  四个分支（同 state 允许补点 / 推进到另一结算页取消补点 / 离开结算立即 teardown / Unknown
  取消补点不 teardown）见上方契约图。方案选择 **Option A**（保留 `_sample_settlement_burst_size()`
  预抽 desired burst size 的既有概念，只收紧「第二下何时真正执行」），不是 Option B（先固定点
  一下再随机决定要不要补第二下）——Option A 侵入最小，且保留了「同一 anchor 大概率会补一下」
  这个人类行为特征，不会让补点变成纯随机。
- `_settlement_burst_step` 同步更新对 `_fire_settlement_burst` 的调用，传入 `current_page`。
- mid-burst 观察分支离开结算时调用的 `_teardown_settlement_session()` 与主循环级的销毁调用
  复用同一个方法，没有复制 7 个字段的重置代码——teardown 现在有两个入口，一个 helper。

### 未改（按要求严格锁定）

`_sample_settlement_budget`/`_start_settlement_session`/`_advance_settlement_anchor`/
`_point_in_roi`/`_select_reward_region`/`_is_generic_result_context`/
`_sample_settlement_point`/`_click_settlement_point`/`_sample_settlement_click`——v1 的全部
既有原语签名与实现逐字未改；`SETTLEMENT_CLICK_INTERVAL_RANGE`/
`SETTLEMENT_BURST_CLICK_INTERVAL_RANGE`/`SETTLEMENT_ANCHOR_KEEP_PROBABILITY` 三个常量数值与
归属未改（`SETTLEMENT_BURST_CLICK_INTERVAL_RANGE` 只是语义从「两次盲点间隔」收紧为「点击→
观察前等待」，用的还是同一个常量、同一次 `time.sleep`，没有叠加新的 timing owner）；
`run_general_battle()` 主循环级 `_teardown_settlement_session()` 调用点（v1 中途追加）原样
保留，不是被 v1.1 取代，而是两个入口共存；`ActivityShikigami._drain_activity_settlement()`；
RealmRaid/GeneralInvite/RyouToppa/Activity FIRE 契约；KekkaiUtilize；OASX。

### 测试

`tests/test_general_battle_settlement.py` 新增 7 例：CASE B（Result 观察到已推进 Reward，只点
1 次，session 不销毁）、CASE E 链式（紧接 CASE B 同一 session，下一帧 Reward 安全区域内
keep 同一 anchor，证明「burst 被观察中止 ≠ 必须换点」）、CASE C 单元级（Reward 观察到
terminal，只点 1 次并立即 teardown，端到端版本见既有 `test_main_loop_destroys_active_
burst_session_before_leaving`，本轮已重写为确定性用例）、CASE D（观察到 Unknown，不补点也不
teardown，anchor/budget 原样保留）、CASE G（budget=4 但首下即 terminal，通过日志断言 teardown
当下真实 `used=1/4`，而不是清零后的 0）、CASE H（同 state 补点后紧接的下一次调用被节流计时器
挡下，不产生第三下）、CASE I（用调用顺序事件日志验证 click → observe → teardown 的严格顺序，
而不只是断言最终字段状态）。同时修复 v1.1 签名/新依赖导致的 8 处既有 harness/测试失配：
`_make_task()` 新增 `task.screenshot = Mock()`；`_SettlementHarness`（默认返回
`page_battle_result`）/`RewardOverlayTest._reward_harness()`（默认返回 `page_reward`）/
`_BurstHarness`（默认跟随 `step()` 传入的 `current_page`，即「无变化」）新增
`_classify_general_battle_page` 默认 mock；`test_realm_raid_non_quick_exit_reaches_settlement_
burst_session` 同样补齐；`test_main_loop_destroys_active_burst_session_before_leaving` 重写为
确定性端到端用例（显式 mock `random_int`=`[1,2]` 与 `detect_page_in` 三段序列覆盖「主循环
第 1 帧 classify / mid-burst 观察 / 主循环第 2 帧 classify」，不再依赖真实随机）。

回归顺序（用户指定）：Settlement 相关全量 → `test_general_battle_settlement`
（**72 OK**，65+7）→ `test_general_battle_timing`/`test_realm_raid_state`/
`test_activity_shikigami_climb`/`test_reaction_timing_batch1`/
`test_ryoutoppa_c_area_1_point_opt_in`（**241 OK**，0 regression）→
`compileall -q tasks tests` OK → 完整 `unittest discover -s tests` **1472 → 1479 OK**（+7，
0 regression）→ `git diff --check`（`general_battle.py` + `test_general_battle_settlement.py`）
干净。

### Git

分支 `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。未 commit / push /
merge / reset / restore / checkout / clean / stash。本轮改动：
`tasks/Component/GeneralBattle/general_battle.py`（`M`，v1 基础上追加）、
`tests/test_general_battle_settlement.py`（既有 WIP 文件，追加 7 例 + 修复既有 harness）、
`docs/AI_CONTEXT.md`（新增 §4.67 + 更新 §7 基线）、`docs/ROADMAP.md`（更新 settlement
micro-timing 条目状态）、`docs/DECISIONS.md`（修订 **D025**，未新增 D026——审查确认本轮是
v1 内部收紧、不构成新的独立架构决策）、本 `DEVELOP_LOG`；`ARCHITECTURE.md`/`TESTING.md`
无需更新——调用链分层与验证规则/测试分级均未变化。其余仓库既有 WIP（`docs/` 下若干未跟踪
审查报告、`tasks/ActivityShikigami/` 等）本轮未触碰。未启动 MuMu / 游戏 / OCR / 设备。

### Level C（重新定义，取代上一条目的 Level C 列表）

①Result 第一次点击未切页时能否观察到自然的同点补点；②Result 第一次点击已经切到 Reward 时是否
确实不出现旧 state 的第二个盲点；③Reward 第一次点击直接切到下一场 terminal 时是否不残留任何
settlement 点击；④进入 Challenge/FIRE 前是否总是先经过 Settlement teardown、再由 FIRE 契约
独立接管；⑤连续点击视觉观感是否仍然自然，不因多了一次 mid-burst 截图/识别出现明显停顿；
⑥0.10~0.30s 的观察间隔是否足够看到真实页面更新；⑦若真机页面响应慢于 300ms，是否会出现「仍
识别到旧 state → 补第二下」但仍落在安全的结算区域内；⑧anchor keep/resample 的真机观感是否
自然。

## 2026-09-14 - KekkaiUtilize U3：进入好友结界寄养页导航失败必须阻断寄养业务

### 背景

`docs/ROADMAP.md`「结界卡流程精简 + 静默窗口 / cooldown」的调度部分（Scheduler v1，§4.64）与
业务开关部分（§4.65）落地时，末尾都各自挂账了同一条已知技债——`check_utilize_add()` 里：

```python
if not self.goto_page(page_guild_realm_utilize):
    logger.info('Utilize failed, exit')
# 开始执行寄养
self.run_utilize(con.select_friend_list, con.shikigami_class, con.shikigami_order)
```

只记录一行日志，没有 `return`/`continue`——导航到好友结界寄养页失败后，代码仍会无条件继续往下
落入 `run_utilize(...)`，在错误页面继续好友 OCR / 收益 OCR / 结界卡 OCR / 列表 swipe / 结界卡
点击 / 寄养点击。用户本轮要求：导航失败必须完全阻断寄养业务，且复用现有 `KekkaiUtilize` retry
/ scheduler pipeline，不新增第二套重试机制。

### Root Cause（先 READ 真实源码，不凭旧报告猜）

先还原真实调用链：`run()` → `check_utilize_add()`（`while 1:` 循环）→ 每轮先
`goto_page(page_guild_realm_growth)` → `appear(I_UTILIZE_ADD)` 判断是否已在寄养（是则走 OCR
剩余时间出口，`return True`）→ 否则 `goto_page(page_guild_realm_utilize)` → `run_utilize(...)`
→ 检查 `self.utilize_terminal_failure` 决定继续循环还是 `return False`。

关键发现：`GameUi.goto_page()`（`tasks/GameUi/navigator.py:769`）的真实契约不是「成功
True / 失败 False」，而是「成功 `return True`（`_finalize_arrival` 固定返回 `True`）／失败
`raise GamePageUnknownError`」——通读整个 `while True:` 循环体，没有任何 `return False`/
`return None` 分支。也就是说，旧代码 `if not self.goto_page(page_guild_realm_utilize):` 这个
判断**在当前 Navigator 实现下从未真正生效过**：不是"偶尔漏判"，而是这个 `if` 分支本来就等不到
一个假值会触发它的场景（唯一真实失败路径是异常，而异常会直接击穿这个 `if`、跳过它的 body，
继续向下传播、绕开 Kekkai 自己的失败处理）。这解释了 U3 为什么会被观察到"导航失败但业务仍在
执行"——真正发生的其实是"导航失败时异常直接向上抛出、根本没有机会被这行 `if` 拦下"，而当时
写下这行 `if not goto_page(...)` 的人可能是按"其它任务里 `goto_page` 用作 bool 判断"的旧印象
类比写的，忽略了这里异常才是真实失败信号。

### 修复

`tasks/KekkaiUtilize/script_task.py::check_utilize_add`，唯一改动点：

```python
try:
    reached_utilize_page = self.goto_page(page_guild_realm_utilize)
except (GamePageUnknownError, GameStuckError) as error:
    reached_utilize_page = False
    logger.warning(
        f'KekkaiUtilize navigation failed: target=page_guild_realm_utilize ({type(error).__name__})'
    )
if not reached_utilize_page:
    logger.warning('KekkaiUtilize navigation failed, skip utilize business')
    self._schedule_retry('导航到好友结界寄养页失败')
    self.utilize_terminal_failure = True
    return False
# 开始执行寄养（未改）
self.run_utilize(con.select_friend_list, con.shikigami_class, con.shikigami_order)
```

本地 `try/except` 把「异常」与「（防御性保留的）假值返回」两种失败信号统一收敛成
`reached_utilize_page`；异常类型选 `(GamePageUnknownError, GameStuckError)`，与
`run_utilize()` 自己对内部 `self.goto_page(page_friend_utilize)` 的既有 catch 元组保持一致
（`tasks/KekkaiUtilize/script_task.py:897` 附近），一个 `goto_page` 调用一种失败处理口径，
不新造第三种。失败即复用 `_finish_low_value_utilize`/`_record_utilize_failure` 最终失败分支
同款的既有终态失败出口——`_schedule_retry(...)` + `utilize_terminal_failure = True` +
`return False`——与「3 次蹭卡失败」「跨区+同区都没有达标候选」两个既有终态失败路径完全同构，
不是新发明的行为，也不新增第二套重试/超时机制。

### Failure Ownership（避免重复计数）

导航失败是一个**独立的终态失败出口**，不进 `utilize_add_count`（OCR 轮询次数上限 5 次的既有
计数器）也不进 `utilize_failed_count`（选中候选后蹭卡失败次数上限 3 次的既有计数器）——两者都
保持原语义不变，只在真正对应的场景下才递增。一次导航失败只触发一次 `_schedule_retry` 调用，
`return False` 立即结束本轮 `check_utilize_add()`，不会被主循环或某个内层分支重复触发第二次。

### 未改（按要求严格锁定）

Navigator/`goto_page()` 本身的返回值/异常契约——未触碰 `tasks/GameUi/navigator.py` 一行；
好友列表扫描 / 卡种筛选 / 收益阈值 / OCR 算法本体；`_run_search`/`_run_lazy_utilize`/
`switch_shikigami_class`/`set_shikigami` 内部逻辑；Scheduler v1 的 `_schedule_retry`/
`_schedule_target`/`_build_retry_target`/`_normalize_quiet_target`（5~30 分钟 cooldown 范围、
静默窗口归一化算法，D023）；`utilize_harvest`/`auto_replace_max_level` 业务开关（D024）；
`KekkaiActivation`；GeneralBattle Settlement Micro-Burst v1.1；RealmRaid；OASX；`Config`
schema；quiet window / cooldown 参数值。导航成功分支后续既有语句（`run_utilize(...)` 调用 /
`utilize_terminal_failure` 检查 / `goto_page(page_guild_realm_growth)`）逐字未改。

### 测试

`tests/test_kekkai_utilize_state.py` 新增 `UtilizeNavigationFailureGuardTest`（10）：

- CASE1：导航成功 → `run_utilize` 恰好调用 1 次（`appear(I_UTILIZE_ADD)` 用
  `side_effect=[True, False]` 让循环在"1 次寄养尝试"后经由既有"已在寄养"OCR 出口自然结束，
  不用伪造 `utilize_terminal_failure` 当测试开关），既有成功语义（`return True`）不变。
- CASE2/2b：导航假值失败、以及抛 `GamePageUnknownError`/`GameStuckError` 两种真实失败信号都
  能阻断 `run_utilize`（`run_utilize` mock 断言 0 次调用）。
- CASE345：不满足于"外层 `run_utilize` 这个黑盒 mock 没被调用"这一层证明——把 `run_utilize`
  换回真实方法本体，只 mock 它内部仅有的两个业务分发口 `_run_search`/`_run_lazy_utilize` 以及
  `switch_shikigami_class`/`set_shikigami`，证明真实 `run_utilize` 方法体从未被进入过，而不是
  只验证外层一层 mock 没被调用（呼应"不要为了测试而把这些函数整体 mock 掉后漏掉真实穿透"的
  顾虑）。
- CASE6/7：复用既有 `_schedule_retry`（`wraps=` 包装验证真实调用一次 + `random_int(300,
  1800)` 5~30min cooldown 范围）；候选时间落入静默窗口时仍被 `_normalize_quiet_target` 正确
  顺延 + jitter（跨午夜场景），证明 U3 没有绕过 Scheduler v1。
- CASE8：失败只触发一次 `_schedule_retry`，`utilize_failed_count`/`utilize_add_count` 不被
  额外重复计入。
- CASE9：`goto_page(page_guild_realm_growth)` 循环底部那次调用不会发生（只统计导航失败分支
  **之前**「进入本次循环」那一次），本轮迭代立即结束，不继续向下执行其它业务。
- CASE10/10b：`inspect.getsource` 源码级锁定成功分支既有语句原样保留在新 guard 之后；成功
  导航后 `run_utilize` 自身产生的既有 terminal failure（`_record_utilize_failure` 类语义）
  不受本轮影响，仍正确 `return False`。

回归顺序：`UtilizeNavigationFailureGuardTest` targeted（10 OK）→ `test_kekkai_utilize_state`
（**131 OK**，121+10）→ KekkaiUtilize 全家族（`test_kekkai_activation_state`/
`test_kekkai_utilize_threshold`/`test_kekkai_k4_projection`/`test_kekkai_k4_selected_anchor`/
`test_kekkai_utilize_scheduling`/`test_kekkai_utilize_state` 合计 **223 OK**，0 regression）→
`compileall -q tasks tests` OK → 完整 `unittest discover -s tests` **1479 → 1489 OK**（+10，
0 regression）→ `git diff --check`（`script_task.py` + `test_kekkai_utilize_state.py`）干净。

### Git

分支 `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。未 commit / push /
merge / reset / restore / checkout / clean / stash。本轮改动：
`tasks/KekkaiUtilize/script_task.py`（`M`，既有多轮 WIP 之上追加，唯一改动点见上）、
`tests/test_kekkai_utilize_state.py`（既有 WIP 文件，追加 1 个新测试类 + 2 个新导入）、
`docs/AI_CONTEXT.md`（新增 §4.68 + 更新 §7 基线 + 给 §4.64/§4.65 的 U3 技债备注加"已于 §4.68
修复"前向指针）、`docs/ROADMAP.md`（「已完成」表新增 U3 一行）、本 `DEVELOP_LOG`；
`DECISIONS.md` 无需更新——审查确认这是一处调用方 bool/异常判定缺陷的可靠性修复，不是新的长期
架构决策，D023/D024 已覆盖 Scheduler v1 与业务开关本身，本轮没有产生需要新 ADR 记录的独立设计
决定；`ARCHITECTURE.md` 无需更新——调用链本身未变（`run()` → `check_utilize_add()` →
`goto_page()`/`run_utilize()` 的层次关系不变，只是失败分支的处理更正确）；`TESTING.md` 无需
更新——验证级别规则、测试分级、真机要求均未变化。其余仓库既有 WIP（`docs/` 下若干未跟踪审查
报告等）本轮未触碰。未启动 MuMu / 游戏 / OCR / 设备。

### Level C

PENDING。真机人为制造无法进入好友结界寄养页的场景（网络卡顿 / 异常弹窗 / 坑位耗尽 / 好友列表
加载失败等）→ 确认日志按预期出现 `KekkaiUtilize navigation failed: target=page_guild_realm_
utilize` 与 `KekkaiUtilize navigation failed, skip utilize business` → 确认不再继续任何
好友/收益/结界卡 OCR、不 swipe 寄养列表、不在错误页面点击 → 确认 `next_run` 正确生成（5~30min
cooldown，落入静默窗口时正确顺延 + jitter）→ 下次任务能正常重新尝试；以及正常导航成功时寄养
流程完全不受影响的真机体感确认。

## 2026-09-14 - Pre-Push Blocker Fix：ActivityShikigami Macro Idle ownership 跨玩法线泄漏 + 冻结期清理

### 背景

上一轮对当前工作树做了一次 READ ONLY 的 pre-push 深度审查（77 个 tracked 改动 + 约 108 个
untracked 新文件），结论 NOT READY：BLOCKER = 1、SHOULD FIX = 5。本轮只修这个 blocker 和
明确的低风险清理项，不做任何新功能 / 不扩大设计范围。

### Root Cause（同实例连跑多条玩法线时 flag 泄漏）

`tasks/ActivityShikigami/script_task.py:20-29` 的 `ScriptTask.run()`：

```python
for activity_name in sequence:          # sequence = conf.general_config.task_sequence_v
    getattr(self, ACTIVITY_METHOD_FIELDS[activity_name])()
```

同一个 `ScriptTask` 实例按用户配置顺序连跑多条玩法线。而
`tasks/ActivityShikigami/activities/normal.py::run_climb` 只做单向声明：

```python
self._fatigue_owns_macro_idle = True    # 爬塔线把 macro idle 交给 Fatigue 安全节点
```

**没有任何线切换时的恢复**，`rich_man.py` / `fake_god.py` 也从不声明（全仓只有两处赋值：
`base_act.__init__` 的 `False` 与 `run_climb` 的 `True`）。于是配置成「爬塔,伪神降临」或
「爬塔,大富翁」时：

- `prepare_next_action`（`base_act.py`）里的
  `if self.conf.general_config.random_sleep and not self._fatigue_owns_macro_idle:`
  因为残留的 `True` 被跳过 → 没有 `random_sleep`；
- 而 `try_fatigue_break` 只出现在 `NormalClimbAct._activity_challenge_safe_break`
  （climb-only，其 docstring 明确写「不影响大富翁 / 伪神降临线」）→ 也没有 Fatigue 安全节点。

结果是后续玩法线**零 macro-idle owner**，静默丢掉拟人化宏观空闲。这与 `base_act.py` 注释
写明的设计意图（「大富翁 / 伪神降临线保持 random_sleep」）直接矛盾，属确认的 state leak。

### 修复（ownership 由当前线自己声明）

选择「每条玩法线在自己的 `run_*` 入口显式声明 owner」而不是「在 `ScriptTask.run()` dispatch
前统一重置」：ownership 归属是这条线自己的属性，写在入口处对 dispatch 顺序、对直接调用
`run_fakegod()` 都成立，也不需要在 dispatcher 里复制「哪条线用 Fatigue」这份知识。

- `tasks/ActivityShikigami/activities/rich_man.py::run_rich_man` +1 行
  `self._fatigue_owns_macro_idle = False`（紧跟 `logger.hr`、任何业务之前）。
- `tasks/ActivityShikigami/activities/fake_god.py::run_fakegod` 同上 +1 行。
- `tasks/ActivityShikigami/activities/normal.py::run_climb` 既有的 `= True` **原样保留**。
- `tasks/ActivityShikigami/base_act.py` 的字段注释补上 ownership 契约：`__init__` 的值只是
  实例初始默认，**不承担线间切换职责**，每条线必须自己声明。

**未改**：Fatigue 模型 / 概率 / `random_sleep` 参数 / `prepare_next_action` 逻辑 /
`try_fatigue_break` / 任何活动业务流程 / `ScriptTask.run()`。

### 生命周期测试（新增 5 例）

`tests/test_activity_shikigami_climb.py::MacroIdleOwnershipLifecycleTest`：

- CASE1：同实例 `run_climb → run_fakegod`，断言伪神线的**真实** `prepare_next_action`
  确实调用了 `random_sleep`（owner 已恢复）。
- CASE2：同实例 `run_climb → run_rich_man`，同上。
- CASE3：单独 `run_climb`（真实 `_run_climb_type` → 真实 `prepare_next_action`），
  断言 `random_sleep` 调用 0 次、flag 为 True、`begin_fatigue_task` 调用一次。
- CASE4：`fakegod → climb → fakegod`，断言 ownership 能 False → True → False 往返、不粘滞。
- 源码级护栏：三条线入口都必须显式声明 owner（防止新增玩法线漏声明）。

harness 只 mock 业务叶节点（页面图搭建 / 导航 / 截图 / 识别 / 具体动作），每条线跑到真实
`prepare_next_action` 之后用既有的 `ActivityResourceNotEnough` 资源耗尽出口收尾；**全程不手工
写 `_fatigue_owns_macro_idle`**，ownership 迁移完全由真实 `run_*` 入口调用链产生。

**已验证不是 false positive**：在内存中用「删掉 ownership 声明行」重建修复前的
`run_fakegod` / `run_rich_man`（不改仓库任何文件）后重跑——CASE1/CASE2 失败（`0 != 1`，
即 `random_sleep` 没被调用，正是泄漏本身），CASE4 直接 `AttributeError`（修复前没有任何真实
入口会建立这个属性），CASE3 仍通过（爬塔线本来就没坏）。旧的
`test_flag_false_still_random_sleeps` 因为手工把 flag 设成 False，结构上抓不到这个泄漏。

### 低风险清理

- 删 `tasks/base_task.py` 的 `import random`：HEAD 时被 `sleep(random.uniform(0.8, 1.3))`
  使用，本 WIP 已把那处换成 FrameWait，全文件仅剩注释里出现 `random.uniform` 字样。
- 删 `tasks/KekkaiUtilize/script_task.py` 的 `next_quiet_window_end` import：该函数只在
  `scheduling.normalize_for_quiet_window` 内部使用，任务侧无引用。
- 清 `tasks/ActivityShikigami/assets.py` 本轮新增的 3 处 trailing whitespace（line 62 / 64 /
  153）。**未动** `docs/DEVELOP_LOG.md` 既有两处历史 trailing whitespace。

### 文档

- `docs/Kekkai状态机静态收口.md` / `docs/KekkaiUtilize蹭卡流程重新审查.md`：R-U6 两处改写为
  **真实 root cause**（`goto_page` 成功 `return True`、失败抛 `GamePageUnknownError` /
  `GameStuckError`，从不返回 False/None；旧 caller 按 bool-failure 理解导致失败处理不可达、
  真实异常绕过 Kekkai 自己的 retry / quiet / terminal handling），并标 **U3 IMPLEMENTED /
  Level A/B PASS / Level C PENDING**。不再保留「异常路径下仍继续执行寄养业务」这一已被源码
  推翻的旧表述。
- `docs/ROADMAP.md`：组队入口改造标 **CANCELLED / WON'T DO**（直进 `page_team` 后缺少选层
  能力、成本高于收益，用户决定取消）；返回庭院优化标 **CLOSED / NO IMPLEMENTATION**（现有
  navigator 回庭院链已够用）；「当前任务 / 下一步」整段重写为 **CODE FREEZE + Level C pending
  + 推送准备**，并把已完成的 Kekkai Scheduler / 业务开关 / U3 / Settlement v1.1 / 活动爬塔线
  从 P0 待办里摘掉（旧「下一步」段落保留为历史快照并注明已被取代）。
- `docs/AI_CONTEXT.md`：新增 §4.69 + §7 基线 `1489 → 1494`。

### 验证

ActivityShikigami targeted（**63 OK**，58+5）→ KekkaiUtilize family（**223 OK**，验证 import
清理无影响）→ base_task consumers（`test_list_find` / `test_base_task_swipe_trajectory` /
`test_base_task_wait_until_appear` / `test_frame_wait`，**68 OK**）→
`compileall -q module tasks tests dev_tools` OK → 完整 `unittest discover -s tests`
**1489 → 1494 OK**（+5，0 regression）→ `git diff --check`：本轮改动的 4 个文件全部干净。

### Git

分支 `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。未 add / commit /
push / branch / switch / checkout / reset / restore / clean / stash / merge / rebase。约 108 个
untracked 文件按要求本轮不做 staging 处理。未启动 MuMu / 游戏 / OCR / 设备。

### 遗留（本轮明确不修）

- RealmRaid `fire()` 的裸 `continue`（reaction 后 `I_FIRE` 消失分支）——documented non-blocking，
  ROADMAP 已记为「`fire()` 同构问题本轮不动」，等真机证据再收窄。
- 推送前审查发现的其余 NON-BLOCKING 项（U3 吞 `GameStuckError` 推迟全局重启恢复、settlement
  budget 只覆盖 burst session、源码字符串断言密度、专题文档历史快照等）。
- **本轮新发现**：`git diff --check` 在另外 3 个 assets 文件里还有 16 处本轮新增 whitespace
  （`tasks/Component/GeneralBattle/assets.py` 8、`tasks/Component/GeneralRoom/assets.py` 6、
  `tasks/KekkaiUtilize/assets.py` 2）——上一轮审查因为命令被 `head -10` 截断而漏报，本轮按
  「只处理被授权的 ActivityShikigami」范围约束未动，待用户决定。
