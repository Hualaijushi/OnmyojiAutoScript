# 开发日志归档（2026-08）

> 2026-11-27 按 D073 从 [DEVELOP_LOG.md](../DEVELOP_LOG.md) 无损归档，共 10 条原始记录（仅搬运，未删改历史正文）。

---

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
