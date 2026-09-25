# 验证规则

> 统一告诉所有开发 AI：改完代码以后到底怎么验证。
> 本文档保存**长期验证规则**；当前一次性的测试数字（如「191 个用例」）记在 `docs/AI_CONTEXT.md`，不累积到这里。
> 更新触发：测试命令变化、基线规则变化、新增验证级别、真机要求变化、新增长期测试原则、CI / lint / formatter 变化。

核对时间：2026-09-01。

---

## 1. 默认验证流程

任何源码修改后，默认依次执行：

```
1. 相关单元测试
   toolkit/python.exe -m unittest tests.<改动相关的测试模块> -v

2. 语法 / 编译检查
   toolkit/python.exe -m compileall -q <改动的文件或目录>
   （或整目录：toolkit/python.exe -m compileall -q module/ tasks/ tests/ script.py）

3. 完整回归
   toolkit/python.exe -m unittest discover -s tests

4. 行尾 / 空白检查
   git diff --check
```

说明：

- **解释器**：项目自带 `toolkit/python.exe`（Python 3.10.11）。系统 `python` 可能缺 `zerorpc` / `websockets`，用它跑不了完整回归——**一律用 `toolkit/python.exe`**。
- 完整回归当前基线数字见 `docs/AI_CONTEXT.md` §7。修改后要求：**原有全部用例通过 + 新增用例全部通过**。基线数字会随每次加测试增长，不要盲写历史数字。
- `git diff --check` 只报空白 / 行尾错误。`docs/*.md` 出现 `LF will be replaced by CRLF` 是**警告不是错误**，不影响通过。
- 项目**没有测试 / lint CI**。`.github/workflows/auto-create-pr.yaml` 是上游的「每周四自动从 `dev` 建 PR 到 `master`」helper，不跑测试、不跑 lint，与本地 AI 开发无关（本 fork 直接在 `master` 工作、默认不提交）。
- 没有强制 lint / formatter（无 `pyproject.toml` / `.flake8` / `.ruff.toml` / `.pre-commit-config`）。不要为验证任务引入新工具（black / ruff / mypy 等），除非用户要求。

---

## 2. 测试分级

| 级别 | 含义 | 典型改动 | 本轮能否自证 |
|---|---|---|---|
| **Level A：纯静态 / 单元测试** | 逻辑可被 mock + 断言完全覆盖，不依赖真实设备 / 页面 / OCR | BehaviorTrace、纯图像 / 状态 detector、Config 字段、死代码删除、API 参数契约、纯函数、异常隔离 | 是 |
| **Level B：集成逻辑测试** | 跨多个模块的控制流，仍可用 mock 驱动，但要拼装较多依赖 | `Script.run` 出口语义、`Control.swipe` 后端分发、`flush_area_cache` 分支、通用战斗 FSM 的 handler 分派 | 是（用 `__new__` + `SimpleNamespace` / `Mock` 拼装） |
| **Level C：MuMu / 游戏内真机** | 必须连真实模拟器 / 游戏 / OCR 服务才能验证 | 列表滚动距离阈值、minitouch 真实时序变化、RealmRaid / RyouToppa 页面流程、Kekkai 滑动与稳定判定、GeneralBattle 实际行为变化、任何改变真实滑动 / 点击时序的改动 | **否**——需要用户明确授权并提供真机窗口 |

**归级原则**：如果一个改动「在 minitouch / adb / uiautomator2 等真实后端上的可观测行为可能变化，且无法用单元测试证明不变」，它就是 Level C，本轮不做，记入 `docs/ROADMAP.md` 的「需要真机验证」区。

---

## 3. 当前禁止事项（无用户明确授权时）

- 不启动 MuMu / 任何模拟器。
- 不启动游戏客户端。
- 不连接真实 ADB 设备。
- 不运行需要真实 Image / OCR RPC 服务的流程（`toolkit/python.exe -m unittest discover -s tests` 内的用例已用 mock，不触发真实服务；不要另跑 `script.py` / 各 `script_task.py` 的 `__main__`）。
- 不执行 `dev_tools/` 下需要设备的脚本。

---

## 4. Git 规则

默认（无用户明确要求时）：

- 不 `git commit`。
- 不 `git push`。
- 不 `git merge --continue` / `git rebase --continue`。
- 不 `git reset --hard` / `git checkout --` 丢弃他人改动。
- 在默认分支上工作时，若需要提交先建分支（但本项目当前约定是**不提交**，改动留在工作区）。

当前分支 `master`，HEAD 见 `docs/AI_CONTEXT.md` §2。工作区长期处于「多轮改动未提交」状态，这是有意的——每轮只追加改动 + 更新文档，由用户统一决定何时提交。

---

## 5. 测试失败与新增测试的处理

- **不为了让测试变绿而修改无关业务代码**。测试红了先定位根因。
- **区分本轮回归失败与既有基线失败**：跑一次 `discover` 记住基线，改完再跑，只对「本轮新出现的失败」负责；既有失败单独报告，不顺手改。
- **新增测试必须真实锁住修复语义**：
  - correctness Bug 尽量做**正向 + 反向验证**——修复后测试通过；临时回退修复后测试应失败（证明测试真的抓得住这个 Bug）。回退验证做完必须恢复修复。
  - API 契约测试要断言「谁被调用、带什么参数」，不只是「没抛异常」。
- **配置 API（`GET /{script}/{task}/args` / `script_set_arg`）护栏（2026-09-18，`tests/test_config_model_script_task.py`）**：新增 / 改动任何配置模型（尤其是嵌套子模型、`default_factory`、枚举）都要跑它：每个组必须是标量参数列表、不得把嵌套模型整体当一个值、默认值等于模型默认实例、实际值不被默认值覆盖、GET 不写文件、其它任务输出与旧实现逐字一致。测试或脚本里切到临时配置目录时，`os.chdir` 必须放在所有项目 import **之后**——`module/logger.py` 与 `deploy/logger.py` 在 import 时都会 chdir 到仓库根，先 chdir 再 import 会静默读到仓库里的真实 `config/`。
- **配置页中文覆盖护栏（2026-09-18，`tests/test_global_game_fatigue_i18n.py`）**：改 `GlobalGame.fatigue` 字段或 `assets/i18n/zh-CN.json` 时，从真实 `script_task('GlobalGame')` 取全部 fatigue 字段，逐项检查标签键与 `_help` 说明键在远程翻译里有中文、不等于原始键、键唯一且不遮蔽其它任务字段；`enable` 属 OASX 本地全局键，远程不得覆盖。`zh-CN.json` 已有重复键，**只能按原格式追加、不能整体重新序列化**。需要 OASX 端证据时，在 OASX 隔离 worktree 里用真实 `ApiClient` 连隔离后端跑 Flutter 测试：`flutter_test` 下必须先 mock `dev.fluttercommunity.plus/connectivity`（`check` → `wifi`）与 `plugins.flutter.io/path_provider`，并 `HttpOverrides.global = null`，否则请求静默失败。
- **不允许挂死测试**：任何可能进入循环等待 / 无限重试的被测路径，测试里必须有哨兵异常或次数上限（例：`tests/test_base_task_wait_until_appear.py` 的 `_LoopNotBounded` + 截图次数上限；`tests/test_behavior_trace.py` 的 throughput 用极宽松 `assertLess` 只防数量级异常）。
- **性能 / 吞吐测试用非严格断言**：`assertLess(dt, <很宽松的上限>)` 只防死循环 / 数量级异常，并 `print` 实际值供人工查看；不写 `assert dt < 50ms` 这种受机器波动影响的脆弱断言。
- **mock 而非真实依赖**：用 `unittest.mock` / `SimpleNamespace` / 对象 `__new__` 拼装最小实例。参考现有 `tests/test_swipe_duration_cleanup.py`（`Control.__new__` + `SimpleNamespace` config）、`tests/test_behavior_trace.py`（`tempfile` + monkeypatch 模块级 `_LOG_DIR` / `_now`）。
- **动态 OCR bbox 浮点 → 整数点击 ROI 的兼容必须有回归覆盖**（2026-09-04，`tests/test_rule_ocr_float_roi.py`）：`RuleOcr` FULL 模式的 `coord()` 拿的是 `Full.ocr_full()` 用 OpenCV 检测框写入的浮点 `self.area`，而 `random_point_in_roi` / `ClickSampler` 的整数 ROI 契约不放宽。任何改到 `RuleOcr.coord()` / `_normalize_ocr_click_area` / `Full.ocr_full` / `ClickSampler` 默认策略的改动，都要保证：① 真机浮点值（如 `(595.0, 293.0, 34.0, 101.0)` 及带真分数的）不再 `TypeError`；② 整数化后的 ROI **完整包住原浮点框、不缩小**（几何包含断言，不只是「都是 int」）；③ 已是整数的静态 ROI 语义不变；④ 至少一个用例 mock `ClickSampler.sample`，确认 `RuleOcr` 在调采样器**之前**就已整数化（不是靠采样器内部兜底）。
- **T7 点击热点解析必须锁「来源优先级 + 真实公式」**（2026-09-08，D019；`tests/test_click_profile.py` / `tests/test_t7_5_preferred_hotspot.py`）：`Rule*.coord()` 默认走 `ClickSampler.sample_target(roi, name)`。任何改到 `sample_target` / `click_preference` registry / `default_point` / `adapt_point_profile` / `adapt_preferred_by_size` 的改动，都要保证：① 已登记 target 使用自身 `EMPIRICAL` anchor，未登记 target 使用 `RULE_FALLBACK` anchor `(0.58,0.59)`，数值即使相同也不能混淆 provenance；② `area_1` / `wide_card` empirical `(0.58,0.59)` 不被通用规则覆盖，`C_AREA_1`（short side 116）effective profile 逐字段等于 base；③ preferred 尺寸适配严格按 short side、24/96 锚点与 smoothstep 公式计算，覆盖 `<=24` / 32 / 40 / 48 / 60 / 72 / 80 / `>=96`，测试比较公式值而不是反向迎合展示四舍五入；④ Tiny 仍随机（多坐标 / 均值靠中心 / effective tail=0），只有 Safe ROI 收成 1 个整数像素才允许固定坐标；⑤ 尺寸适配在 23/24/25、95/96/97 附近无突跳；⑥ 一次点击只调 `ClickSampler.sample` 一次；⑦ 每个显式 registry 条目必须有 `note`，不允许把 RULE_FALLBACK 冒充 empirical。
- **T7-5 Stage 2（2026-09-07，`tests/test_t7_5_stage2.py`）—— 长期契约**：
  - **一次点击只允许一次空间采样**：`sample_target` / `sample_region` / `sample_point` 内部各恰调 `ClickSampler.sample` 一次；已由 `Rule.coord()` 采样的坐标再 `device.click(x, y)` 属 `ALREADY_SAMPLED`，`Control` / 后端不得再 jitter。任何迁移后的 consumer 都要能证明 **double-sampling = 0**（不得 `sample_*` 后又加 random offset，也不得 `random_point` 后再 `sample_*`）。
  - **Region Target ≠ Point Target，但共享 preferred-only 适配**：业务已选定 region 内的采样走 `ClickSampler.sample_region`（`default_region` profile，比 Point 宽）→ `adapt_preferred_by_size` 只计算 effective preferred → HABIT。Region **不得调用 `adapt_point_profile`**，其 sigma / weights / margin / tail 不随尺寸收缩；但 preferred 必须与 Point 一样按 short side 24/96 smoothstep 适配。region 的**选择**逻辑（GeneralBattle `_select_reward_region` 的 marker → DEFAULT / 80-20、Generic Result 两次点击、`positive guard`、state machine）与采样无关、必须有独立回归证明「policy 一字未变，只有区内坐标分布可能变」。
  - **无安全 ROI 的 exact click 保留合法**：`EXACT_COORDINATE_BLOCKED`（点运行时检测中心 / 框外偏移 / 硬编码 / 有意固定 fallback / slave 设备）不强行迁移、不凭空造 ROI；但必须进 `docs/T7_TARGET_PREFERENCE_MAP.md` 写文件 / 行号 / 原因。
  - **empirical calibration ≠ 代码迁移**：`normal_button` / `I_FIRE` 等在缺真实 runtime ROI 时保持 `RULE_FALLBACK`，不伪造 empirical 值；这是 Level C calibration，不阻塞「空间模型已统一」的结论。未来取得自身人工数据后以 EMPIRICAL 条目覆盖规则兜底。
- **L1 全局单击管线（2026-09-15，D026；`tests/test_l1_click_pipeline.py`）—— 长期契约**：任何改到 `module/click_pipeline.py`、`ClickSampler.sample_target` / `sample_region`、`Control.click`，或把某个业务点位接入 / 移出 `execute_single_click` 的改动，都要保证：
  - **坐标语义显式**：裸 `(x, y)` / list / `None` / `RuleSwipe` 必须 `TypeError`；`FinalPoint` 在 `ClickSampler` 全部方法被打桩为抛错时仍能解析（零采样），numpy 浮点按 `int()` 截断与 `ensure_int` 逐像素一致。
  - **原生控件不借图片热点**：`ClickBounds(native=True)` 即使传入已登记为 EMPIRICAL 的名字，`resolve_target_preference` 也只能收到 `None`；退化 bounds（宽或高为 0）回中心且零采样。
  - **一次调用 = 一次物理点击**：端到端串到真实 `Minitouch.click_minitouch` 时恰好一次 DOWN / 一次 UP，dwell 仍调 `random_triangular(45, 130, 65)`；`execute_single_click` 拒绝 `RuleLongClick`；后端抛错时只尝试一次。
  - **BehaviorTrace 坐标 = 执行坐标**：记录的 `extra` 与传给后端的 `(x, y)`、`execute_single_click` 的返回值三者相等；trace 关闭或 `_write_line` 抛错都不影响点击。
  - **L1 不拥有 L2 / L3**：`click_pipeline` 可执行代码不出现 `sleep` / `random_delay` / `confirm_delay` / `REACTION_*` / `Timer` / `screenshot` / 循环，import 只允许 atom 规则类 + `click_sampler`；生产代码无 `multi_click(` 消费者。
  - **业务已给定落点不被重采**：Settlement `_click_settlement_point` 原样执行、`_sample_settlement_click` 走 Region 而非 Point；`list_appear_click` / `EvoZone.check_layer` / `green_mark_name` 在采样器被打桩为抛错时仍逐像素执行原坐标。
  - **收口点位不回退**：`ConvertedSitesGuardTest` 列出的函数体必须含 `execute_single_click(` 且不含 `self.device.click(`。新增语义断言要按本节「正向 + 反向验证」做变异回退，确认能抓到 double randomization / 原生控件查热点 / 接受裸坐标。
  - **L1.2 静态迁移守卫（`StaticMigrationGuardTest`，按「文件 + 函数」不按行号）**：`module/` + `tasks/` 里直接 `device.click(` 的函数与次数必须**等于** `CANONICAL_DIRECT_CLICKS` 白名单（新增直调要么走 `execute_single_click`，要么先证明语义清晰再进白名单）；`click_minitouch(` / `click_window_message(` 只能出现在 `module/device/`；同一函数里不得同时有点击与 `randint` / `uniform` / `random_point_in_roi` / `random_rectangle_point`；`multi_click` 无 AST 调用；`Control.click_with_backend` / `_dispatch_click` / `list_click_target` / `HyaDevice.fast_click` 无 sleep / Timer / screenshot / 循环。
  - **文字列表命中在 OCR 框内采样**：真实 `RuleList.ocr_appear` 命中后 `list_click_target` 得到 `ClickBounds(OCR 框)`，pos 不对应 / 无结果 / 图片列表都退回 `FinalPoint` 且零采样；迁移后的本地随机（SixRealms）Region 必须等于旧 `randint` 支撑集。
  - **指定后端不改后端行为**：`click_with_backend('window_message')` 必须仍以 `fast=True` 调用、不读 `control_method`、不调 `handle_control_check`，BehaviorTrace 记录执行坐标；默认 `Control.click` 仍做 `handle_control_check`。
- **BehaviorTrace Swipe Trajectory Backend（2026-09-07，`tests/test_control_swipe_trajectory.py` / `test_behavior_click_stats.py` / `test_behavior_trace.py`）—— 长期契约**（见 `docs/DECISIONS.md` D004 补记 + D011 补记）：
  - **一次 swipe = 一条 ACTION**：`Control.swipe_trajectory` 无论 `trajectory` 有多少点（≤~80）都只 `record()` 一次 `ACTION`（`action='swipe'`）。任何改到 `Control.swipe` / `Control.swipe_trajectory` / `_swipe_trajectory_extra` / `BehaviorTrace` 的改动都要证明：**没有** `MOVE` / `SWIPE_POINT` / `FRAME` 事件、`trajectory` 点不会变成 N 条 ACTION、FrameWait 轮询不产生 ACTION。事件模型永远只有 `TASK` / `ACTION`（D004）。
  - **trajectory 直接来自 executor 输入**：记录的 `extra.trajectory` 是传给 `Control.swipe_trajectory` 的那一份 commanded 点列（`[x,y,dt_ms]` 三元，`dt` 语义 = D018），**不按 start/end 重新 `generate`、不还原曲线、不抽稀**。legacy `Control.swipe` 只带端点、**无 `trajectory` 键**（不许伪造完整曲线）。
  - **旧 JSONL 必须兼容**：`read_behavior_clicks` 对「只有 click 的旧日志」「`action='swipe'` 但 `extra` 无 `trajectory`」「坏 JSON 行」「单条 `trajectory` 结构坏 / 含坏点」都不得抛、不得 500——坏 `trajectory` 只降级该条（保留可解析点或 `[]` + `summary.malformed_trajectories`）。响应旧键（`points` / `tasks` / `summary` 的 `total`·`click_count`·`long_click_count`·`task_count`·`skipped_lines`）名称·类型·语义保持不变（additive extension，旧 OASX 忽略新键即可工作）。
  - **计数**：一条 swipe 无论多少轨迹点，`summary.swipe_count` 只 +1（不得按点数累加）。
  - **四层等值 AND 过滤**：`date AND task AND interaction_type AND target`。`interaction_type ∈ {all, click, swipe}`（大小写不敏、非法 → `BehaviorStatsError(400)` / router 422）；`target` 对 click 与 swipe 用**同一个参数、同一语义**（不许 `click_target` / `swipe_target` 两套）。测试要覆盖 Case A（task + swipe）/ B（task + click）/ C（全任务 + swipe）/ D（task + swipe + target）。
  - **commanded ≠ actual**：BehaviorTrace 记的是输入指令轨迹，不是实际 UI 滚动位移；K4（`actual_scroll_dy` / `scroll_gain` / dedup）不在此层，测试不得假设 trajectory 反映真实内容位移。
- **KekkaiUtilize K4 —— Selected Anchor + 一帧对一帧投影去重（2026-09-07，`tests/test_kekkai_k4_selected_anchor.py` / `test_kekkai_k4_projection.py` / `test_kekkai_utilize_state.py` 的 `K4IntegrationTest`）—— 长期契约**（见 `docs/DECISIONS.md` D017 K4 补记）：
  - **measurement failure 永远不能让 candidate 数量减少**：`SelectedAnchorDetector` 不可用（NMS 后 0 或 >1）、`actual_scroll_dy` 非法（`<=0` / `>= I_IS_SELECTED.roi_back 高度` / anchor 不可用）时，`_run_search_pass` 必须遍历当前屏 `find_everyone` 的**完整**结果（`scan_cards = cards`）。任何改到 K4 的改动都要有用例证明：before/after anchor unavailable、multi-match、invalid dy 四种情形下 **current candidate 数量不减**（宁可重复读卡，不能漏卡）。
  - **一帧对一帧去重、无持久历史**：只保留「上一稳定屏」的 detections + 它 swipe 前的 anchor；比对一次后当前屏成为新的「上一屏」。禁止全 PASS / 全局 candidate database / 好友身份历史 / persistent dedup map（源码不得出现 `candidate_history` / `global_dedup` 之类）。
  - **commanded distance 不得替代 actual dy**：`actual_scroll_dy` 只能来自 `anchor_before.center_y − anchor_after.center_y`（`center_y = y + h/2`，before/after 统一口径）。测试不得让 `SWIPE_DISTANCE_RANGE` / `SWIPE_LATERAL_OFFSET_RANGE` / 固定 gain 参与 dy；`KEKKAI_ROW_PITCH_PX` 只做「约几格」解释，dy **保留连续像素、不四舍五入成整格**（sub-row 位移必须能测）。
  - **去重条件**：同 `image.name`（类型）+ bbox 真实几何交集（IoU > 0）才配对，竞争按 max IoU 一对一贪心（一个 previous 不消费多个 current、一个 current 不被多个 previous 消费）；投影出可见范围的 previous 忽略。类型不一致即使 bbox 重叠也**绝不**去重（要有专门用例）。**不新增 ±px magic tolerance**。
  - **D017 契约不受 K4 影响**：`measurement unavailable ≠ ABORT ≠ BOTTOM ≠ PASS_MISS`；**K3 失败仍 `return ABORT`**（且此时不进 K4 after anchor / dedup）；**BOTTOM 仍只认 `I_U_EMPTY_CARD`**（没有 new candidate / dy 很小 / anchor 不见 / 投影后全 duplicate 都不是到底）；`clicked_any` / `FINAL_USE_LAST` 单调语义不变。K1 / K2 / K3 一行不改。`K4_ENABLED=False` 必须能证明退回纯 D017（`detect_selected_anchor` 零调用）。
  - **纯组件优先合成数据**：`detect_selected_anchor` 用 mock `match_all_any` 返回 `(score,x,y,w,h)` 元组测收敛逻辑；`dedup_by_projection` 用 `SimpleNamespace(name=...)` 构造 detection 测几何——都不需要真实图像 RPC。
- **全仓 Swipe Consumer 迁移 —— ordinary swipe 走 `BaseTask.swipe_trajectory`（2026-09-07，`tests/test_base_task_swipe_trajectory.py`）—— 长期契约**（见 `docs/DECISIONS.md` D018 全仓迁移补记 / `docs/AI_CONTEXT.md` §4.48）：
  - **每个 ordinary swipe consumer（现在与将来）必须两条路径都验证**：`control_method == 'minitouch'` → `TouchSwipeModel().generate` + `Control.swipe_trajectory`（不落端点 `Control.swipe`）；非 minitouch（`adb` / `uiautomator2` / `scrcpy` / `window_message`）→ 回退 `Control.swipe` 端点滑动（不构造 `TouchSwipeModel`）。新增走 `swipe_trajectory` 的 consumer 若没有非 minitouch 回退用例，视为未完成。
  - **helper 只负责「怎么滑一次」**：`BaseTask.swipe_trajectory` 体内**不得**出现 `screenshot` / `sleep(` / `wait_for_changed_and_stable` / `frame_wait` / `random_delay` / `for _ in range` / `while`——截图 / 等页面稳定 / sleep / 重试 / 随机延迟都是业务层职责（有源码扫描护栏）。K3 的 FrameWait 是 KekkaiUtilize `_perform_search_swipe` 专属，**不因为迁移 trajectory 就给全仓 swipe 套 FrameWait**。
  - **`TouchSwipeModel().generate` 每次滑动恰调用一次**；`control_name` 两条路径都原样透传（→ `handle_control_check` → `click_record`，Exploration `arrive_end` / 换式神 swipe 计数依赖它）。
  - **异常不吞**：`generate`（<2px `ValueError`）与 executor（minitouch socket 异常）抛出的异常都必须透传，不得被 helper 吞成静默 no-op。位移 `< 10px` 走端点回退（`Control.swipe` 自带「太短当点击」处理）、不进模型。
  - **既有 task-state 测试零改动**：它们的 config 是 MagicMock，`control_method != 'minitouch'` 自然走端点回退，行为逐字不变——迁移不得要求批量改这些测试；真要改说明 helper 设计破坏了向后兼容。
  - **drag / press-and-drag / 摇杆手势不适用本契约**：`Control.drag`、`tasks/Chess/runtime/press_and_drag.py`、`AbyssShadows.move_a_little` 保留 legacy，不套 `swipe_trajectory`。
- **时序层长期规则 —— W1~W7 等待分类（2026-09-08，`docs/AI_CONTEXT.md` §4.49 / `docs/DECISIONS.md` D001 / D012 / D013）**：
  - **W1 结构性 settle（动作后固定 sleep 只为等页面变化 / 停稳，然后继续按当前页面视觉状态识别）→ 优先迁 `wait_for_changed_and_stable`**，前提：动作前 baseline 显式传入（D012 / D013）、ROI 从该 consumer 已有的 asset / list / page ROI 推导（**禁止全局 `GLOBAL_FRAMEWAIT_ROI` / 全局阈值**）、timeout 有限、失败按**原业务语义**降级（`list_find` = 结果丢弃回循环顶重扫、`max_swipe` 收敛，**不映射 BOTTOM**；K3 = `PassResult.ABORT`；**禁止统一「timeout → success」或「timeout → bottom」**）。参数缺实测依据时可 Level A/B 接线 + 标 `Level C calibration pending`，不得写成「全局最佳参数」。
  - **W2 语义等待（等某业务 marker 出现 / 消失）→ 继续 `wait_until_appear` / `appear` 循环**，FrameWait 不替代 semantic success marker。
  - **W3 协议 / 设备等待**（minitouch dwell / `DEFAULT_DELAY` / backend sleep / OCR·图像服务启动 / 连接）→ 稳定性层，**禁止迁移**（D002）。
  - **W4 retry backoff / W5 业务 cooldown·实时要求 / W6 behavioral delay（fatigue / `random_delay` / reaction）→ 保留**；**W7 静态判不出目的 → 保留、报告 `semantic unclear`、不猜**。
  - **`confirm_delay` explicit opt-in（D001）**：`appear_then_click(confirm_delay=(lo,hi))` 默认 `None`，**不得**改成有默认区间；只有「稳定、长期可见、位置稳定、允许 reaction timing、且已有可信实测区间」的 Point Action 才显式接入。**禁止为覆盖率拍脑袋新建 `0.3~0.8` / `0.5~1.5` 之类全局区间**——无实测依据的 consumer 标 `eligible / Level C calibration pending`。
  - **reaction timing 不与 fatigue 自动叠加（D001）**：同一次 Point Action，若已被 fatigue 注入同语义 reaction delay，则不再叠 `confirm_delay`。`confirm_delay`（识别后到点击前 reaction）≠ FrameWait（视觉结构等待）≠ fatigue（macro idle / rest）≠ minitouch dwell（DOWN→UP 按压）≠ TouchSwipeModel 逐段 dt——owner 不同、不互相替代、不在同一 Action 上叠加实现同一等待目的。
  - **T0-1 回归护栏**：`wait_until_appear_then_click` 必须 `wait_until_appear(target, wait_time=wait_time)` 关键字传参（历史上按位置传把等待时长绑成 `skip_first_screenshot`），批量迁移不得重新引入参数错位。
- **Reaction Timing / `confirm_delay` 迁移长期规则（2026-09-08，`docs/DECISIONS.md` D001 补记 / `docs/AI_CONTEXT.md` §4.51；`tests/test_reaction_timing_batch1.py`）**：
  - **只给 stable Point Target 加**：稳定页面、长期可见、位置在等待期间不移动 / 目标不会自动消失、不是抢窗口 / 短命弹窗 / 高频 poll、且不是 `action=` 分支（点的是 `action.coord()` 静态坐标、不重定位）。动态搜索结果 / OCR / 滑动列表候选 / `*_FIRE`（缺正向战斗页确认，属 R2 STATE_WAIT_FIRST）不加。
  - **explicit opt-in，profile 来自 `module/reaction_profile.py`**：consumer 在调用点显式传 `confirm_delay=REACTION_*`；**不在 `RuleImage` / asset / `Control` / `Device` 层设默认**，不改 `appear_then_click` 默认 `None`。`module/reaction_profile.py` 只允许具名 `(min,max)` tuple 常量 —— 任何改动都要保证：无 `def` / `sleep(` / `random_delay` / `class` / task·device 依赖（正文扫描，去 docstring）；6 组值精确、递增二元组；`REACTION_PROFILES` dict 与具名常量一致；`REACTION_PROFILES_PROVISIONAL is True`。**当前 6 组区间是 PROVISIONAL engineering baseline**，改值必须连带更新 D001 补记 + §4.51，且不在无 Level C 证据时放大区间。
  - **excluded critical timing 不叠加**：已有同语义 timing owner 的点击不再加 `confirm_delay` —— RyouToppa `attack_area` 的 `I_FIRE`（手搓 `random_delay(0.2,0.6)` + fresh frame + 二次 appear）、GeneralBattle `I_PREPARE_HIGHLIGHT`（`prepare_click_timer`）、Settlement Micro-Burst v1.2 三个 Region（跨 burst `settlement_click_timer` + burst 内 `0.30~0.60s` fresh semantic gate，2026-09-23 由 `0.10~0.30s` 放宽，D025 补记）。任何改到这些路径的改动要有用例证明 `confirm_delay` 未被加入、原 timer / `random_delay` 仍在。
  - **公共 helper 扩参保持向后兼容**：给共享方法（如 `GeneralBattle.check_lock`）加 `confirm_delay` 时默认必须 `None` 并透传，非 opt-in 调用方行为逐字不变（mock 断言「不传 → 内部收到 `None`」）。
  - **迁移用源码扫描 + mock 断言**，不为实现方便大范围重写既有用例；`appear_then_click` primitive 本体由 `tests/test_base_task_confirm_click.py` 独立锁定，迁移轮不改 primitive。
- **L2 Timing Ownership（2026-09-15，D001 补记 L2；`tests/test_l2_interaction_reaction.py`）—— 长期契约**：任何改到 `module/interaction_policy.py`、`BaseTask.appear_then_click`、FIRE owner 的 reaction、`FireReactionConfig` 或新增 `policy=` consumer 的改动，都要保证：
  - **legacy 默认不变慢**：`appear_then_click(target)` 与 `policy=IMMEDIATE` 不调 `random_delay` / `sleep` / `screenshot`；`policy` / `confirm_delay` 默认都是 `None`。
  - **一个 reaction owner**：同时传 `policy` 与 `confirm_delay` 必须 `ValueError` 且零副作用；全仓不得出现两者同时（非形参透传）的调用；`confirm_delay=REACTION_*` 不得回流（具名 profile 一律 `policy=`）。FIRE 目标的 `appear_then_click` 不得带 `policy` / `confirm_delay`。
  - **fresh confirm**：reaction → 新截图 → 同目标再识别 → 用新帧 `coord()`；reaction 后目标消失零点击、`appear` 恰两次、不重试；每次调用独立采样（SystemRandom）。
  - **FIRE 配置**：无 override = `REACTION_FIRE`；ms / 1000；`0 <= min <= max <= 5000`，`min == max` 合法；非法构造与非法 `setattr` 都要 `ValidationError` 且旧值不变；运行时不交换非法区间。`fire_reaction_range(` 只允许出现在 11 个 FIRE owner 函数里（2026-09-18 L2-3B Batch A 起），每个 owner 恰一次、位于有限 attempt 循环内，reaction 与 FIRE 点击之间必须有 `sleep` + `screenshot` + positive-state 检查；`tasks/` 不再直接引用 `REACTION_FIRE`；`config/template.json` 与 `zh-CN.json` 同步。
  - **L2 不下沉 / 不越界**：`click_pipeline` / `Control.click` / `click_with_backend` / `_dispatch_click` / `click_minitouch` 不引用 reaction 相关名字，且对应模块不 import `interaction_policy` / `reaction_profile`；Settlement 方法不引用 policy / FIRE 配置 / REACTION_*；`interaction_policy` 与 Fatigue 互不 import。变异回退（legacy 默认改 NORMAL、静默吞掉双 owner、去掉 fresh 截图、FIRE owner 忽略任务配置、ms 不换算、放行 min>max、FIRE 点击叠 policy、Control 里加 sleep）必须全部被抓。
- **Timing Ownership Migration Guard（2026-09-15，L2-2，D001 补记；`tests/test_l2_policy_migration.py`）—— 长期契约**：
  - **审计清单锁源码**：`AUDIT_SCOPE` 内每个点击调用点的（文件, 函数, 调用, 目标, 当前 timing）必须与 `INVENTORY` 逐行一致，
    分类与 `docs/L2_INTERACTION_POLICY_MAP.md` 一一对应；新增点击 / 改 policy / 去掉 policy 都要同时更新清单与文档。
  - **分类不变量**：MIGRATE 用声明的 policy（CONFIRM 决策不能是 NORMAL）；KEEP_IMMEDIATE / KEEP_SPECIAL / NEEDS_C 必须仍是立即点击；
    FIRE 目标、Settlement / 奖励阶段弹窗不带普通 policy；GameUi（navigator / default_pages / chess_battle）不 import
    `interaction_policy`、点击不带 policy / confirm_delay。
  - **行为验证用真实迁移函数**：驱动 `GeneralInvite._open_invite_panel_if_needed` 与 `GeneralBattle.switch_preset_team`
    走真实 `appear_then_click`——第二帧仍在 → 恰一次点击且坐标来自新帧；第二帧消失 → 零点击；reaction 区间来自 profile。
  - **静态 ownership**：任何函数里 `random_delay(` 之后不得出现带 `policy=` 的 `appear_then_click`；click_pipeline / Control /
    minitouch / Fatigue 不引用 `interaction_policy`。变异回退（NORMAL 改回立即、FIRE 加 NORMAL、奖励阶段加 policy、去掉 fresh
    截图、policy 前加 random_delay、navigator 执行器注入 NAVIGATION）必须全部被抓。
- **FIRE Battle Entry 契约（2026-09-18，L2-3B Batch A，D001 补记 L2-3B；`tests/test_fire_batch_a.py`）—— 长期契约**：把旧式「连点直到按钮消失」入口收口为 FIRE owner 时，必须**真实驱动 owner 方法**（帧序列替身 + 确定性 Timer，不能只靠源码字符串），逐任务覆盖：成功（reaction → fresh 截图 → 新帧上恰一次点击 → 准备 / 战斗页）；reaction 中目标消失零点击；pre-state 变化不点旧帧；按钮消失但无正向状态不算成功；仍在页有界重试且每次重新采样 reaction；过渡帧只等不点；结果 / 奖励页不算成功；次数用尽与总时长用尽都显式失败；caller 只在成功时交接一次 `run_general_battle`、失败不计次。配置：默认 400~800ms、ms→秒、每个任务独立组、复用组的任务读对的组。正向判据只能用窄 detector（`fire_battle_entry.is_new_battle_entry`），不得用 `is_in_battle()`。变异回退（去 reaction / 去 fresh 截图 / 按钮消失即成功 / 结果奖励页当正向 / 去次数上限 / 去总超时 / FIRE 加普通 policy / 忽略任务配置）必须在每个 owner 上都被抓。
- **任务「稍后重试」出口的调度器结局（2026-09-20，D023 补记；`tests/test_kekkai_utilize_retry_scheduler.py`）**：改到任何会写 `next_run` 的重试 / 失败出口时，不能只断言 `set_next_run` 被调用——必须证明它在**真实 `Script.run` / `Script.loop`** 下的结局：① 连续 N（>3）轮都实际执行、每轮落盘的 `next_run` 合法且未被收尾流程覆盖、失败计数不累计、`exit(1)` 不触发、其它任务仍被选取（`exit` 用可观察替身，不能真的结束进程；循环类用例要有轮数上限，回归时不能挂死）；② 写入没有确认（读回不一致）时**不得**报告正常结束、失败照常累计；③ 系统异常仍走原失败路径；④ 时钟带微秒（生产 `datetime.now()`）时读回比较仍成立。调度层驱动用临时目录 + 临时配置 + 冻结时钟（`Config` / `script` / 任务模块的 `datetime` 一起替换，`isinstance(x, datetime)` 要仍成立），不碰真实 `config/*.json`。
- **循环收敛保护的测试（2026-09-20，D023 补记（二）；`tests/test_kekkai_utilize_convergence.py`）**：给「不能死循环」的保护写测试时，替身必须复现**真实的清零语义**（例如 `run_utilize` 替身也要清零业务计数、返回 True），否则测不到「计数被清零所以永不收敛」这类真实缺陷；每个用例自带硬上限（超过即抛出而不是挂死）；同时要有「正常多位置 / 边界恰好用满上限仍成功」的反向用例，防止保护误伤；耗时类用例用可控的 `monotonic` 替身，并证明「选卡 / 计数不重启计时」；触发后要在真实 `Script.loop` 下证明只重排一次、其它任务照常被调度。变异验证每项独立超时、结束后逐字节还原源码。
- **调度延迟类配置的测试（2026-09-20，D023 补记（三）；`tests/test_kekkai_utilize_success_jitter.py`）**：给「只作用于某一类调度路径」的随机延迟写测试时：① 用**分区间供值并记录调用**的随机源替身，区分该延迟与 cooldown / 静默抖动，多采样直接失败；默认值（0/0）要有**与旧公式逐秒对比的网格**（含微秒时钟）并断言完全不采样；② 逐条证明非适用路径（OCR 兜底 / 重试 / 收敛保护 / 静默守卫 / 功能关闭）没有采样；③ 静默边界必须同时覆盖「延迟推入窗内（被吸收、不叠加）」与「延迟推出窗外（保留候选、不再采样静默抖动）」；④ 配置层用真实 `script_set_arg` 单字段 PUT + 落盘文件断言，**每一步落盘的都是合法区间**，并模拟 OASX 草稿保存（按编辑顺序逐字段、失败保持 dirty、再保存一次）证明 ≤ 2 轮收敛；GET 不写文件、旧配置文件缺字段时用默认值补齐且不回写；⑤ 调度层用真实 `Script.run` / `Script.loop` + 真实 `Config.task_delay`，断言每次成功调度恰写一次、两账号互相独立、其它任务照常被调度。变异验证每项独立超时并逐字节还原源码。
- **共享 UI 循环有界化的测试（2026-09-20，D023 补记（四）；`tests/test_shikigami_class_switch_bound.py`）**：给「点击 → 重新截图 → 确认状态」类循环加边界时：① 用**随点击 / 假时间变化的假界面**驱动真实循环（截图推进假时钟、`appear(interval=)` 沿用真实语义），覆盖「已在目标 / 首次成功 / 丢点后成功 / 最后一次点击延迟刷新仍成功 / 图标始终在但点击无效 / 目标始终识别不到 / 点位不稳定」；假界面自带独立硬帧数上限，保护失效时立刻失败而不是挂死；② 证明本地边界**小于** Device 兜底（点击次数 < 6、耗时 < 60 秒），否则先触发的是重启游戏的异常；③ 上层预算穿透（预算耗尽后再次调用一次点击都不做、每次调用共用同一个绝对截止时间）；④ 失败传播链：不继续放置、不冒充成功、只安排一次重试、读回未确认不冒充正常结束、真实 `Script.loop` 下其它任务继续；⑤ 变异验证每项独立超时并逐字节还原源码。
- **FIRE 任务级可配置 reaction（2026-09-18，D001 补记，`docs/AI_CONTEXT.md` §4.77；`tests/test_fire_reaction_task_config.py`）**：`REACTION_FIRE=(0.4,0.8)` 现只是 `fire_reaction_range(None)` 的返回值；RealmRaid（`fire` / `_fire_again`）/ RyouToppa（`attack_area`）/ EvoZone / Orochi（单人 `_fire_*_alone` + 组队 `run_invite` 传参，`run_wild` 排除）/ ActivityShikigami / `GeneralInvite.click_fire` 改读 `fire_reaction_range(self.config.<task>.fire_reaction)`（`click_fire` 读调用方传入的 `fire_reaction` 形参，未传 = `None` = 公共默认）；EternitySea / FallenSun / Sougenbi 从「零 reaction 裸连点」新接入 `appear_then_click(FIRE, interval=0, confirm_delay=fire_reaction_range(<task>.fire_reaction))`（不新建状态机、不改成功判据 / 重试超时契约）。改到这些函数或新增消费者时必须证明：① 8 个任务的 `fire_reaction` 配置组默认 400/800ms 且互相隔离（`default_factory`，改一个不影响另一个）；② 每个 owner 恰一次 reaction 来源（`random_delay(` 或 `confirm_delay=fire_reaction_range(`计数，RyouToppa 的区域 pacing `random_delay(1.0,3.0)` 例外允许 2 处）；③ **真实驱动**（不能只读源码）证明改配置真的改变了实际采样区间，不是恒等于旧硬编码值；④ `min==max` 合法、非法区间在配置层拒绝且旧值保持、运行时不交换 / 钳制；⑤ `ConfigModel.script_task` 展开为 `fire_reaction.fire_reaction_min_ms` /`_max_ms` 两个叶子参数、`script_set_arg` 保存重载回显正确（复用 §4.75 的嵌套字段展开机制，非新逻辑）。
- **FIRE Action / R-R1 长期规则（2026-09-08，`docs/DECISIONS.md` D001 补记 FIRE 分节 + 增补 + D015 补记 / `docs/AI_CONTEXT.md` §4.52 / §4.53 / §4.56；`tests/test_fire_reaction_fsm.py` + `tests/test_second_batch_fire_fsm.py` + `tests/test_realm_raid_state.py`）**：任何改到 `RealmRaid.fire()` / `RealmRaid._fire_again()`（退四内「再次挑战」，§4.56 已收口）/ `RyouToppa.attack_area()` 的 `I_FIRE` 路径、或 `Orochi._fire_orochi_alone()` / `EvoZone._fire_evozone_alone()` 的 `I_*_FIRE` 路径（`run_alone`，第二批已收口）、或未来收口其它 `*_FIRE` 时，都必须有用例证明：
  1. **旧页面标识消失（`I_RR_PERSON` / 目标列表）既不代表进入战斗、也不代表 immediate failure / retry**——mock 「旧 marker 消失、`I_FIRE` / `I_RR_PERSON` / `I_BACK_RED` 全 False、`is_in_battle()` 全 False」（= transition / unknown 过渡帧）时 `fire()` 既不得立即 `return True`，也不得立即 `return False` / 进入下一 attempt / 点 `C_PARTITION_n` / 点 `I_FIRE`——必须在有界 `Timer(RR_FIRE_POST_CLICK_TIMEOUT)` 内继续 polling，直到出现 `battle` / `retryable` / timeout。再 mock 「过渡帧之后下一帧 `is_in_battle()`=True」→ `fire()` `return True` 且不多点。
  2. **成功判据是正向战斗状态**：`is_in_battle()` / `page_battle_prepare` / `page_battle`（复用 `GeneralBattle.is_in_battle` 或 `get_current_page`，不新造 detector）。FIRE post-click / FIRE 未就绪的状态判定必须是**三态**（`'battle'` / `'retryable'` / `'timeout'`），不能简化成 battle / not-battle。「retryable」的判据是纯只读 helper（如 `_is_realm_raid_retryable_state()` = `appear(I_RR_PERSON) or appear(I_FIRE) or appear(I_BACK_RED)`）——**不截图 / 不点击 / 不 sleep / 不改状态**（有源码扫描护栏）。
  2b. **`C_PARTITION_n`（对手选择）点击必须有明确 retryable-state 守卫**：mock「`I_FIRE`=False 且 transition/unknown（无任何 retryable marker）」→ 不得点 `C_PARTITION_n`；mock「`I_FIRE`=False 且明确 retryable（`I_BACK_RED` 在 / `I_RR_PERSON` 在）」→ 允许按业务点 `C_PARTITION_{order}` `interval=2`。`not appear(I_FIRE)` 不再是点 partition 的充分条件。
  3. **retry 必须 bounded**：mock 「永不进战斗」时最多执行 `RR_FIRE_MAX_TRIES`（RealmRaid）/ `RYOU_TOPPA_ACTION_RETRIES`（RyouToppa）次真实 FIRE attempt，然后 `return False`，不得无限循环。
  4. **timeout 必须 finite**：mock `Timer` 到期 → `fire()` 明确 `return False` 退出，不继续 partition / FIRE / sleep / poll。
  5. **FIRE reaction 后必须 fresh frame**：reaction（`random_delay(*REACTION_FIRE)` + `sleep`）之后必有一次 `screenshot()` 再做判定。
  6. **target 消失不点旧坐标**：mock 「reaction 前 `appear(I_FIRE)`=True、reaction 后 `appear(I_FIRE)`=False」时不得 `appear_then_click(I_FIRE)` / `device.click`。
  7. **failure 不得 handoff GeneralBattle**：源码断言 caller（`RealmRaid.run`）每处 `self.fire(index)` 都是 `if not self.fire(index): continue` 形态、返回值从不被丢弃（AST 无「裸 `self.fire(index)` 表达式」）。
  8. **每次真实 FIRE retry 独立采样 reaction**：`random_delay(*REACTION_FIRE)` 必须在 `for attempt` 循环体内（AST 校验），禁止进 `fire()` 只采样一次给所有 retry 共用。
  9. **禁止同语义 timing stack**：RealmRaid `fire()` 恰 1 处 `random_delay(`（FIRE reaction）、无 `confirm_delay` / `reaction_delay` / `CLICK_REACTION_DELAY` / 第二套 repeat/retry delay；RyouToppa `attack_area` 恰 2 处 `random_delay(`（区域 pacing `(1.0,3.0)` + FIRE `(*REACTION_FIRE)`）、无 `confirm_delay`；Orochi `_fire_orochi_alone` / EvoZone `_fire_evozone_alone` 各恰 1 处 `random_delay(*REACTION_FIRE)`、无 `confirm_delay` / `REACTION_FAST` / 第二套 delay、无 `while True`。`REACTION_FIRE = (0.4, 0.8)` 是 PROVISIONAL，改值连带更新 D001 补记 + §4.52 / §4.53，无 Level C 证据不放大。
  10. **run_alone 才是 FIRE owner**：Orochi / EvoZone 的 `run_leader` / `run_member` / `run_wild` 不点 FIRE（源码断言无 `REACTION_FIRE`、`I_*_FIRE` 不叠 `confirm_delay`）；契灵（BondlingFairyland）`I_BALL_FIRE` = PARTIAL（模块不 import `REACTION_FIRE`、`run_alone` 结构与 `BondlingNumberMax` 路径不变），改到契灵 FIRE 时要有用例证明未被机械套三态模板。
  11. **caller 守卫**：`Orochi.run_alone` / `EvoZone.run_alone` 里 `run_general_battle` 与 `try_fatigue_break` 必须都在 `if self._fire_{orochi,evozone}_alone():` 体内（AST 校验），`run_general_battle` 全函数只 1 处非裸调用；`_fire_*_alone` 用尽有可达 `return False`。
  12. **公共组队 challenge owner = `GeneralInvite.click_fire()`（2026-09-08，§4.54 reaction + §4.55 Battle Entry FSM；`tests/test_general_invite_challenge_reaction.py`）**：`click_fire` 是 Orochi / EvoZone 等 11 个副本组队 / 房主点「挑战 / 开始战斗」的唯一公共实现（`run_invite` 经 `room_check_can_fire` 门槛调用，或 ExperienceYoukai / GoldYoukai / Hunt / Tako 直接调用）。改到它必须有用例证明：
     - **reaction（§4.54）**：① 识别 `I_FIRE`（优先）/ `I_FIRE_SEA` 后先 `random_delay(*REACTION_FIRE)` + `sleep` + fresh `screenshot`，再二次确认才 `appear_then_click(target, interval=1, threshold=0.7)`；② reaction 期间按钮消失（仍在房间）→ 不点 stale 坐标；③ 每 attempt 独立采样 `REACTION_FIRE`；④ `click_fire` 代码体恰 1 处 `random_delay(` + 1 处 `sleep(`，无 `confirm_delay` / `reaction_delay` / `CLICK_REACTION_DELAY`。
     - **Battle Entry 四态 / bounded FSM（§4.55）**：⑤ **`click_fire()` 返回 `str`，取值恰 `{'battle', 'room_failed', 'timeout'}`**（AST 校验所有 `return` 常量）；⑥ **无 `while 1` / `while True`**，有 `for attempt in range(1, GI_FIRE_MAX_TRIES + 1)` + `Timer(GI_FIRE_TIMEOUT)`；⑦ **「不在房间」单独发生（`not is_in_room(False)` 且无 battle marker、无 room-failed marker）→ 返回 `'timeout'`，绝不当 success**，且不点任何坐标（本轮最重要护栏）；⑧ transition unknown（loading / blank）→ 有界 `_wait_room_entry_state` polling、不点，之后出 battle → `'battle'`、无多余点击；⑨ ROOM_FAILED（`I_MATCHING` / `GameUiAssets.I_CHECK_MAIN` / `I_CHECK_EXPLORATION` 任一）→ 立即返回 `'room_failed'`、不点挑战；⑩ RETRYABLE（`is_in_room(False)`）→ 允许下一 bounded attempt；⑪ `overall_timer` budget 0 → 立即 `'timeout'`、0 点击、0 截图；⑫ 4 个状态 helper（`_battle_entry_positive` / `_room_entry_failed` / `_classify_room_entry_state` / `_wait_room_entry_state`）**纯只读**——无 `screenshot` / `.click(` / `appear_then_click` / `sleep(` / `random_delay`（`_wait_*` 只有一个自己的 `Timer`）；⑬ `_battle_entry_positive` 优先 `getattr(self, 'is_in_battle', None)` → `is_in_battle(False)`，否则兜底 **`appear(I_BATTLE_INFO) or appear(I_PREPARE_HIGHLIGHT)` —— `GeneralBattle.is_in_battle()` 8 个 positive marker 的严格子集**：fallback 里出现的每个 `GeneralBattleAssets.I_*` 都必须能在 `is_in_battle()` 源码里找到（用例断言），**不允许扩张到 `is_in_battle` 未采用的更宽 heuristic**（`I_EXIT` 已于静态复核后移除）；`GeneralBattleAssets.I_EXIT` 本体及 `exit_battle` / `check_then_accept` 等其它 consumer 保留（source-shape 护栏）；⑬b **`GI_FIRE_TIMEOUT` 语义是 soft new-attempt admission budget**——timeout 用例只锁 `overall_timer.reached()` 在 `for attempt` 顶 gate 新 attempt + `budget=0 → 立即 'timeout'` + `bounded/finite`，**不得断言「整个 `click_fire` 必须 ≤ `GI_FIRE_TIMEOUT` 秒返回」**（避免把 soft budget 测成 strict contract；显式返回上界 ≈ `GI_FIRE_TIMEOUT + 4.8s`）；⑭ `_room_entry_failed` 复用 `ensure_enter` / `wait_battle` 已有 marker、不新造。
     - **caller guard（§4.55）**：⑮ `run_invite` 只在 `click_fire() == 'battle'` 才 `return True`，否则 `return False`；⑯ 直接 caller ExperienceYoukai / GoldYoukai / Tako 有 `if self.click_fire() == 'battle':` 才 `run_general_battle()`，Hunt 有 `battle_entered = self.click_fire() == 'battle'` + `if not battle_entered: return`；⑰ 11 个 `click_fire` consumer MRO 里都有 `is_in_battle`（`callable(getattr(cls, 'is_in_battle', None))`）。
     - **不变**：⑱ `run_invite` 的 `Timer(20/30)` / `timer_wait` / emoji State Wait 不动，challenge 仍经 `room_check_can_fire` 门槛；⑲ **Passive Waiter**（`wait_battle` / `check_then_accept` / `check_and_invite` / `invite_again` / Orochi·EvoZone `run_member`）源码无 `click_fire` / 无 `REACTION_FIRE`；⑳ Orochi / EvoZone `run_alone` 的 `_fire_*_alone` 不经 `click_fire`、不叠加，`run_leader` 经 `run_invite` 不自己写 reaction；㉑ **Fatigue 不扩散**——`general_invite.py` 模块 + `click_fire` / `_classify_*` / `_wait_*` / `run_invite` / `wait_battle` / `check_then_accept` 代码体无 `fatigue` / `begin_fatigue_task` / `try_fatigue_break`；㉒ 11 个继承 task 不覆写 `def click_fire`；直接 caller 只加 `== 'battle'` guard、不引入 `REACTION_FIRE` / 新循环。
     - **测试性能**：`gi.Timer` 必须 patch 成 `_FakeTimer`（否则超时路径跑真墙钟——本轮曾达 113s）。源码扫描去首个 docstring。`GI_FIRE_MAX_TRIES=4` / `GI_FIRE_TIMEOUT=15` / `GI_FIRE_POST_CLICK_TIMEOUT=4` 是 PROVISIONAL，改值连带更新 D001 补记 + §4.55。
  13. **RealmRaid `_fire_again()` + 主业务改造（2026-09-08，§4.56 / `docs/DECISIONS.md` D020 + D001 补记 `_fire_again`；`tests/test_realm_raid_state.py`）**：改到 `tasks/RealmRaid/script_task.py` 的目标选择 / 退四 / `_fire_again` / 目标 pacing / Fatigue 时必须有用例证明：
     - **`_fire_again()` 与 `fire()` 同契约**：`for attempt in range(1, RR_AGAIN_MAX_TRIES + 1)` + `Timer(RR_AGAIN_TIMEOUT)`，永不进战斗 → 最多 `RR_AGAIN_MAX_TRIES` 次真实 attempt → **可达 `return False`**（不无限循环、尾部 `return False` 不再是死代码）；成功判据 `is_in_battle()`（不以「`I_FIRE_AGAIN` 消失」判成功）；每 attempt 独立 `random_delay(*REACTION_FIRE)` 在 `for attempt` 体内；reaction 后 fresh `screenshot` + 二次 `appear(I_FIRE_AGAIN)`（消失不点旧坐标）；`I_SHOW_AGAIN` / `I_FRESH_ENSURE` 是**无 reaction 的流程点击**；`_wait_again_entered_battle()` 返回 `{'battle','failure_page','timeout'}`、**不点任何坐标**；`_fire_again` **只在退四分支被调**（源码 / AST 断言普通失败路径不出现）。
     - **固定 1→9 目标选择**：`_grid_targets()` 用 `order_medal.find_everyone()`（不是 `find_anyone` / `order_attack` 排序）；`run()` 取 `index = min(targets)`；同一位置换不同勋章模板 → 选出的 order 不变（medal-independent）；`_broken_orders()` 命中的 order 不进 `targets`；`_grid_targets` 在 `image.copy()` 上涂黑、不写 `self.device.image`（mock 断言原帧未被改）。
     - **退四触发 = `len(targets) == 1`**（源码断言含 `len(targets) == 1` / `only_last`，**不含**旧 `index == 1` 触发）；退四分支含 `ensure_lock(False)` 且在 `fire` 之前、结束含 `ensure_lock(lock_default)`；退四循环 `for i in range(RR_EXIT_FOUR_SURRENDERS)` 且 `RR_EXIT_FOUR_SURRENDERS == 4`；退四中断 / 最终失败分支走 `check_refresh()`、不含 `_fire_again` 再调用。
     - **`RR_TARGET_PACING` 独立 timing owner**：`RR_TARGET_PACING = (1.0, 2.5)` module 常量；`_enter_target()` 里恰 1 处 `random_delay(*RR_TARGET_PACING)` + `sleep`，pacing 后有 fresh `screenshot` + `_target_still_attackable` / `_is_realm_raid_retryable_state` 二次确认（不可打 → `return False` 不点旧坐标）；**不与 `fire()` 的 `REACTION_FIRE` 合并**（`fire()` 仍恰 1 处 `random_delay(*REACTION_FIRE)`）；`_enter_target` / `run()` 无 `confirm_delay`。旧「RealmRaid 目标 pacing 1~3 秒」不得复活。
     - **Fatigue safe point**：`begin_fatigue_task('RealmRaid')` 在主 `while 1` 之前；`try_fatigue_break(safe=True, repeat_completed=True, deadline=None)` 只在 `_realm_raid_cycle_safe_break()`（`screenshot` + `_is_realm_raid_retryable_state()` 守卫）里出现；`_grid_targets` / `_broken_orders` / `_enter_target` / `fire` / `_fire_again` / `_wait_*` 源码扫描无 `fatigue` / `begin_fatigue_task` / `try_fatigue_break`（不进 target pacing / FIRE / retry / 退四内部 / refresh）。
     - **`RR_TARGET_PACING` / `RR_AGAIN_*` / `RR_CYCLE_STABLE_TIMEOUT` 是 PROVISIONAL**，改值连带更新 D020 / D001 补记 + §4.56，无 Level C 证据不放大。
  13b. **RealmRaid 主循环 correctness follow-up（2026-09-08，§4.56 correctness follow-up / `docs/DECISIONS.md` D020 补充；`tests/test_realm_raid_state.py::CorrectnessFollowupSourceTest` + `RunLoopBehaviorTest`）**：改到 `run()` 的失败策略 / 退四入口 / 疲劳时机 / 临时解锁时，除源码形态外必须有 **`_RunHarness` 驱动 `run()` 主循环的行为用例** 证明：
     - **`when_attack_fail == CONTINUE` 真正跳过刚失败目标**：mock `_grid_targets` 每轮返回含刚失败 order 的 grid（UI 仍 attackable）、battle 连续失败 → `fire` 的 order 序列**不重复**已失败 order（`[1,2,3]` 而非 `[1,1,1]`）。跳过用**纯局部 `failed_orders: set`**——`run()` 源码有 `failed_orders: set = set()` / `failed_orders.add(index)` / `failed_orders.clear()`，且 `run()` 里**没有**对 `self.device.image` 的切片赋值（`'self.device.image['` / `'] = 0'` 不在 `run()` 源码里；涂帧只在 `_grid_targets` 的 `image.copy()` 上）。
     - **`failed_orders` 生命周期**：只在 `check_refresh()` **成功**分支 `failed_orders.clear()`（每处 `if self.check_refresh():` 后 240 字符内先 `clear()` 再 `_realm_raid_cycle_safe_break()`）；点击 refresh 前 / CD 失败不清。
     - **退四判据用 raw 不用 filtered**：`only_last = len(targets) == 1`（**不含** `len(available) == 1`）。behavior：`raw = {5,8}` + `failed = {5}` → 打 8 走普通分支、`_is_only_remaining_target` 从不被调。
     - **退四入口 fresh revalidate**：退四块入口先 `self.screenshot()` + `_is_only_remaining_target(index)`（在 `ensure_lock(False)` 之前），不满足 → `continue`（不解锁 / 不 `_enter_target` / 不 `fire`）。`_is_only_remaining_target` 纯只读（无 `screenshot` / `.click(` / `sleep(` / `random_delay` / `Timer(`；含 `_grid_targets()` + `len(targets) == 1` + `order in targets` + `_is_realm_raid_retryable_state()`）。`_enter_target` 加 `require_only_remaining` 参数，`True` 时 pacing 后复查 `_is_only_remaining_target`。
     - **Fatigue 在 failure recovery 之后**：普通 `run_general_battle(con.general_battle_config)` 之后 160 字符内**不含** `_realm_raid_cycle_safe_break`。behavior：REFRESH 失败流 `run_general_battle(False)` → `check_refresh(True)` → `cycle_safe_break`（三者顺序，且 battle 与 refresh 之间无 `cycle_safe_break`）；CONTINUE 失败流 battle 之后 `cycle_safe_break` 且无 `check_refresh`；退四最终失败流 `ensure_lock(lock_default)`（finally）→ `check_refresh` → `cycle_safe_break`；EXIT 失败流只 `break`（无 skip / refresh / fatigue）。`_realm_raid_cycle_safe_break()` 源码有 `wait_until_appear(self.I_BACK_RED, wait_time=RR_CYCLE_STABLE_TIMEOUT)` 在 `try_fatigue_break(` 之前、无 `sleep(`。
     - **退四临时解锁 try/finally**：退四块有 `try:` + `finally:`，`finally` 里 `self.ensure_lock(lock_default)`，**无 `except`**（AST：退四块 `Try` 节点 `handlers == []`），`try` body 覆盖 `_enter_target` / `self.fire(index)` / `run_general_battle` / `_fire_again`；`self.ensure_lock(True)` 不出现在退四块（用 `lock_default`）。behavior：`_enter_target` False / `fire` False / `run_general_battle` 抛异常 三种情况都执行 `ensure_lock(lock_default)`；异常情况**原异常传播**（不是 `TaskEnd`）；`lock_default=False` 时退四结束恢复 `ensure_lock(False)`、从不 `ensure_lock(True)`。
     - **现有胜利路径不回归**：普通胜利 cycle 末尾 `cycle_safe_break`；退四胜利经共享尾部 `cycle_safe_break` + 恢复锁；固定 1→9 / medal-independent / `RR_TARGET_PACING` / FIRE 三态 / AGAIN 三态 / 退四 4 次 / GeneralBattle handoff 全部照旧。
  13c. **Battle Lifecycle Detector ≠ New Battle Entry Detector（2026-09-08 Level C hotfix / `docs/DECISIONS.md` D001 补记；`tests/test_realm_raid_state.py::ActiveBattleEntryContractTest`）**：challenge / `fire_again` / retry 这类「点按钮后判断是否进入了一场*新*战斗」的 positive 成功确认，改动时必须有用例证明：
     - **result / reward marker 不是 new-battle-entry positive**：`I_FALSE`（失败横幅）/ `I_WIN` / `I_DE_WIN`（胜负横幅）/ `I_REWARD` / `I_REWARD_GOLD`（奖励页）/ `I_FRIENDS` 任一单独出现，**不得**让 `_fire_again()` / 未来同类 retry helper 返回 `True` / 判 `'battle'`。用例 mock「窄 detector（`is_in_prepare` / `is_in_real_battle`）= False，宽 `is_in_battle()` = True（模拟 `I_FALSE`）」→ helper 必须返回 False，且**根本不调用宽 `is_in_battle`**（`assert_not_called`）。
     - **C 端回归永不复现**：`Battle result: Lose` → 没有 `Fire again: attempt` / reaction / `I_FIRE_AGAIN` click → 直接 `Fire again: entered battle`。用例：`I_FALSE` 帧 + `I_FIRE_AGAIN` 可见 → `_fire_again()` **不 short-circuit return True**，必须走 `random_delay(*REACTION_FIRE)` + 真实 `appear_then_click(I_FIRE_AGAIN, interval=0, threshold=0.8)`，之后才可能返回 True。
     - **窄 detector 是窄的**：`_is_active_battle_entry()` 代码体（去 docstring）只 `is_in_prepare(False) or is_in_real_battle(False)`，无 `is_in_battle(`、无 result / reward marker 名、纯只读（无 screenshot / click / sleep / Timer）；`_fire_again` / `_wait_again_entered_battle` 代码体不再有 `is_in_battle(`。
     - **不改宽 detector**：`GeneralBattle.is_in_battle()` 源码仍含 `I_BATTLE_INFO` / `I_PREPARE_HIGHLIGHT` / `I_WIN` / `I_DE_WIN` / `I_FALSE` / `I_REWARD` / `I_REWARD_GOLD`（其它 consumer 依赖宽语义）；`is_in_prepare` / `is_in_real_battle` 源码不含 result / reward marker。
     - `fire()` R-R1 的 `is_in_battle()` 用法本轮**不在**此规则范围内（目标详情页点第一次 FIRE，其前无结果页）——若未来做一致性收窄，届时补对应用例。
- **RealmRaid 再次挑战确认 owner（2026-09-08，§4.57 / D001 补记；`tests/test_realm_raid_state.py::FireAgainThreeStateTest`）**：改到 `_fire_again()` 的确认流时必须证明：① `I_FIRE_AGAIN` 是再次挑战按钮，仍只用 `REACTION_FIRE=(0.4,0.8)`；② `I_FRESH_ENSURE` 是再战确认按钮，且仅该调用传 `confirm_delay=RR_AGAIN_CONFIRM_DELAY=(0.3,0.6)`；③ primitive 的随机等待后必 fresh screenshot、二次确认、重新取坐标，确认消失不点 stale target；④ `I_SHOW_AGAIN`、`_wait_again_entered_battle()`、`RR_AGAIN_*`、bounded FSM 与窄 `_is_active_battle_entry()` 均不改；⑤ 不在 `I_FIRE_AGAIN` click 上叠 `confirm_delay`，且确认 delay 不复用 `REACTION_FIRE`。
- **Fatigue Safe Point 铺开长期规则（2026-09-08，`docs/DECISIONS.md` D001 / D021 corrected 补记；`docs/AI_CONTEXT.md` §4.53 / §4.56 / §4.60）**：任何给某任务新接 `begin_fatigue_task` / `try_fatigue_break`，或改到已接入任务（RyouToppa / Orochi / EvoZone 单人 / RealmRaid / **Exploration solo：`_maybe_boss_cycle_fatigue()` 在 `run_on_exp_entrance` / `run_on_exp` 顶部，Boss 循环回外层稳定页时**）的疲劳节点时，必须有用例证明：
  1. **`begin_fatigue_task` 在重复循环之前**、`try_fatigue_break(safe=True, repeat_completed=True, deadline=)` 只在一个完整 Business Cycle 结束、**且 failure recovery（刷新 / skip 记录）也完成、已回到稳定可继续页面之后**（源码顺序：`begin_fatigue_task` 在 FIRE 循环前；`try_fatigue_break` 在 `run_general_battle` **且** `check_refresh()` 之后——RealmRaid 是在 `_realm_raid_cycle_safe_break()` 里、helper 先 `wait_until_appear(I_BACK_RED, wait_time=RR_CYCLE_STABLE_TIMEOUT)` 确认 recovery 完成再由 `_is_realm_raid_retryable_state()` 守卫，`deadline=None` 因 RealmRaid 无墙钟时限；**禁止 `battle failure → fatigue → refresh` 顺序**）。
  2. **不放在** FIRE 点击前 / FIRE reaction 内 / FIRE retry 内 / transition-unknown 内 / GeneralBattle 内——`_fire_*` / `_wait_*` / `_is_*` 系列方法源码扫描无 `fatigue` / `begin_fatigue_task` / `try_fatigue_break`。
  3. **组队 / member / wild 路径零 fatigue**（`run_leader` / `run_member` / `run_wild` 源码无 `begin_fatigue_task` / `try_fatigue_break`）。
  4. **fatigue 后 fresh revalidate**：safe node 之后回到业务循环顶必须先 `screenshot` + 重新确认当前业务页面（`try_fatigue_break` 自身不截图 / 不重识别 state）。
  5. `GeneralBattle` 永不是 Fatigue owner（`run_general_battle` / `_handle_*` / Settlement 内不出现 `FatigueManager` / `try_fatigue_break`）。
- **Exploration Boss reward / exit 长期回归（2026-09-08，D021 corrected 补记 / §4.60；`tests/test_exploration_state.py`）**：
  > §4.58 / §4.59 曾按「Boss 后完全不领地图宝箱直接退出」的**错误需求**建 `_run_boss_exit_transaction`
  > / `EXIT_READY..EXIT_SUCCESS` / `_is_boss_exit_success_state` / `_skip_treasure_once_at_entrance`
  > 等结构并配套测试；§4.60 撤销后这些用例已删。以下是当前生效的原生链回归。
  1. **`run_on_battle` 是原生 handoff**：`run_general_battle(exit_matcher=pages.page_exp_main)` +
     `_match_end.refresh()` + `wait_start_time` 重置；源码**无** `_complete_boss_business_cycle` /
     `_run_boss_exit_transaction` / `battle_won` 捕获。模块源码整体无
     `_run_boss_exit_transaction` / `_is_boss_exit_success_state` / `_wait_for_boss_exit_success_state`
     / `_complete_boss_business_cycle` / `_wait_for_stable_page` / `_boss_exit_probe` /
     `_skip_treasure_once_at_entrance` / `ExplorationExitState` / `BOSS_EXIT_` / `exit_ready` /
     `exit_success` 等残留。
  2. **地图宝箱：检查 + 有则领取**。`run_on_exp_main` 源码有 `if self.collect_reward(): return`；
     `collect_reward` = `collect_treasure_box() or collect_paper_man_reward()`；`collect_treasure_box`
     识别 `I_E_REWARD_BOX_SMALL` / `I_E_REWARD_BOX_BIG` → `ui_click` 领取 + `ui_click_until_disappear`，
     无宝箱 `return False`。`run_on_exp_entrance` / `run_on_exp`（ALONE）**无条件** `collect_treasure_box()`
     （源码无 `skip_treasure`）。**不为简化跳过 treasure。**
  3. **小纸人：不领取**。`collect_paper_man_reward` 源码有
     `fire_monster_type == 'boss' and not self._config.exploration_config.collect_paper_reward` →
     `logger.info("Not collect paper doll reward")` + `self.quit_exp_main()` + `return True`（原生链）；
     且 `I_BATTLE_REWARD` + `collect_paper_reward` 领取分支仍在（**地图 treasure 与小纸人是两个独立
     开关，测试防止再混成一个**）。
  4. **自动退出 / stale click**：`quit_exp_main` 源码用
     `appear_then_click(I_UI_BACK_YELLOW, interval=0.8, confirm_delay=REACTION_NAVIGATION)`——
     `confirm_delay` 在 delay 后重新截图二次确认，marker 消失则不点，天然 stale-safe；`quit_exp_main`
     / `run_on_exp_exit` 源码**无** `detect_page_in` / `GameStuckError` / 新造 exit transaction /
     current-page guard。
  5. 章节 FrameWait 必须显式传 baseline / OCR-derived ROI / task-local 参数；stable 与 timeout 都回原 OCR 循环，`swipeCount>=25` 不变；至少一例锁定 stable=True 但 chapter 未找到会继续 OCR。**（§4.58，未动）**
  6. **solo Fatigue Safe Point = `_maybe_boss_cycle_fatigue()`**：只在 `run_on_exp_entrance` /
     `run_on_exp` **顶部**调用（这两个 handler 只在 `get_current_page()` 正向命中外层页时才分发），
     仅 `user_status == ALONE` 且刚完成的是 Boss 循环（`fire_monster_type == 'boss'`）→
     `try_fatigue_break(safe=True, repeat_completed=True, deadline=start_time+limit_time)` + 消费
     `fire_monster_type` + 调用方 `return`（交下一轮 fresh dispatch = fatigue 后 fresh revalidate）。
     **`run_on_exp_main` 源码无 `_maybe_boss_cycle_fatigue` / `try_fatigue_break` / `begin_fatigue_task`**
     （不在 `page_exp_main`、宝箱 / 小纸人 policy / 退出未完成时 fatigue）。非 Boss / 非 solo 不触发；
     `run()` 只 solo `begin_fatigue_task`。
  7. `fire(button)` 的动态目标、`max_tries=4`、`Timer(10)`、positive battle page 与普通怪 handoff 保持原回归。
  8. **Rotation Contract（2026-09-08 §4.59，§4.60 保留不动）**：`switch_rotate()` 的 `AutoRotate.no`（默认）分支代码体（去 docstring）**无 `I_E_AUTO_ROTATE_ON` / 无 `appear_then_click` / 有 `pass`**；配置 `no` + 用户轮换 ON 时 `switch_rotate()` 返 `False` 且 `click` / `appear_then_click` 都不点轮换 marker。全 Exploration 生产代码里 `I_E_AUTO_ROTATE_ON` **绝不**作 `click` / `appear_then_click` / `ui_click` 目标（点它 = 取消用户轮换）。`AutoRotate.yes` 仍 `click(C_CLICK_SETTINGS)` 管候补（回归保留）。

---

## 6. 测试文件组织

- 目录：`tests/`，`unittest` 风格，文件名 `test_*.py`。
- 一个特性 / 一个修复对应一个测试模块，模块 docstring 说明背景与锁的是什么。
- 需要清理进程内单例的（`BehaviorTrace` / `FatigueManager`）在 `setUp` / `tearDown` 调对应 `reset_*`。
- 需要隔离文件系统的用 `tempfile.TemporaryDirectory` + monkeypatch，不碰真实 `log/` / `config/`。

---

## 7. 收尾（每轮开发 / 正式设计结束前）

```
工作完成
 → 有源码改动则跑 §1 默认验证流程全部通过
 → git diff / git status 人工过一遍（确认没有误改、没有调试残留）
 → 逐项检查 6 份项目文档，按「本轮是否改变了该文档负责的项目事实」决定更新哪些
   （见 CLAUDE.md 核心规则 2 / docs/AI_CONTEXT.md §0 表 + §10.1）
 → 再次 git diff --check
 → 输出报告（含固定的「## 文档同步」段）
```
- **L1 × L2 联动与全仓登记册（2026-09-21，`tests/test_l1_l2_integration.py`）—— 长期契约**：① 联动用**真实** `BaseTask.appear_then_click` + 真实 `Control.click`（假后端）+ 包装采样器计数：
  一个动作恰一次采样、reaction 之后才在新帧上采样、目标消失零采样零点击、目标移动用新框、IMMEDIATE / 无参调用无 reaction、policy 与 confirm_delay 同给拒绝、Control 不加抖动；
  ② 登记册汇总与源码扫描对账（`dev_tools.click_callsite_register`，登记册不写行号，无关改动不会让它失效；新增 / 删除点击调用点必须重新分类并 `--write`）；NEEDS_C 按模块钉住；
  `policy` / `confirm_delay` 只允许出现在 L2-2 人工审计文件；③ Settlement / FIRE owner / Kekkai / Navigator / Orochi 野队的延迟所有权静态守卫（AST，不是字符串）；
  ④ 真实 `Script.loop` 下 reaction 的耗时不进 next_run。变异验证覆盖「重复采样 / 旧截图 / 目标消失仍点击 / FIRE 双重反应 / 结算叠策略 / FinalPoint 再偏移 / 后端分派丢失 / 旧接口破坏 /
  近期寄养修复被覆盖」，每项独立超时并逐字节还原。**给旧「朴素循环」写的替身在新状态机下可能挂死**：移植 / 替换 FSM 后必须逐个跑测试模块（带超时）定位挂死用例，不能只看整套 discover。
- **L1 Stage 1：BaseTask primitive 执行入口统一（2026-09-21，D026 补记；`tests/test_l1_stage1_primitive_execution.py`）—— 长期契约**：改 `BaseTask.appear_then_click` / `click` / `ocr_appear_click` /
  `wait_until_appear_then_click` 的点击执行时：① 用**真实方法 + 真实 `Control.click`（假后端）+ 真实 BehaviorTrace + 包装采样器与执行器**断言「一次点击 = `sample_target` 一次 = 执行器一次（第一个实参是
  `FinalPoint`）= 后端一次 = trace 记录同一坐标」，不是只看源码里有没有 `execute_single_click` 字符串；② action 与 target 不同时 `control_name` 必须仍是 `target.name`、落点在 action 的 ROI；
  ③ L2：NORMAL 在 reaction 后的新帧上采样（旧框从未被采样）、目标消失零采样零点击、IMMEDIATE / 旧 `confirm_delay` 不变、策略冲突拒绝；④ `ocr_appear_click` 带 action 只采样一次、OCR 未命中零点击；
  ⑤ 长按不进单击执行器（Stage 3A 起长按走独立的 `execute_long_click`，见下条）；⑥ AST 静态守卫：BaseTask 无 `device.click`，每个执行点第一个实参是 `FinalPoint(...)`（防「先 `coord()` 再把 Rule 交给执行器」的双采样），
  `ocr_appear_click` 只有一次 `coord()`；⑦ 把 primitive 的调用形式从位置实参改成关键字实参会让旧 Mock 断言失败——这类断言要同步改成关键字形式（语义不变），不能删除或改成恒真。
  变异验证（恢复直接点击 / Rule 双采样 / 旧帧 / 目标消失仍点击 / 错 control_name / FinalPoint 偏移 / 恢复重复采样 / 执行器加等待 / 长按并入单击）每项独立超时并逐字节还原源码。
- **L2 登记册「技术分类 + 开发状态」对账契约（2026-09-21，D001 补记 C0 收口；`tests/test_l2_c0_registry.py`）—— 长期规则**：① C0 复核的 24 点必须逐点对账，期望值在测试里**独立写死**（不从生成器的归档表推导）：已完成 4（ALREADY_L2 + COMPLETED，且声明的 policy 与预期一致）/ 暂缓 6（decision=DEFERRED，保留 C0 建议）/ KEEP_IMMEDIATE 3 / KEEP_SPECIAL 4 / NEEDS_C + DEFERRED 7；② **暂缓 ≠ 已完成**：DEFERRED / NEEDS_C / KEEP_* 的点位在源码里必须仍是立即点击（无 `policy` / `confirm_delay`），有人偷偷给暂缓点位加 reaction 时生成器直接报错；③ decision 互斥可加总（总数 1092），basis 互斥可加总，`c0_reviewed` 是独立维度不与 basis 相加；④ 登记册由生成器产出，测试要求「重复生成结果一致、且与已提交 Markdown 逐字一致」，归档与源码对不上（点位不存在 / 重复 / NEEDS_C 指错点位）必须失败而不是静默兜底；⑤ L2-2 的 179 点历史审计结论（MIGRATE 7 / NEEDS_C 7）不被改写；⑥ 已有断言的钉住值随分类变化时只更新数值与归属，不能删除或放宽断言。
- **L2 policy 迁移的 fresh-confirm 验证契约（2026-09-21，D001 补记 C1-A1；`tests/test_l2_stage_c1_a1.py`）—— 长期规则**：给一个调用点加 `policy=` 时，测试必须用**真实业务函数 + 真实 `BaseTask.appear_then_click` + 真实 `Control.click`（假后端）+ 真实 BehaviorTrace**，由帧序列驱动（`frames[n]` = 第 n 次截图之后可见目标，`frames[0]` = reaction 前的当前帧），包装采样器 / L1 执行器 / `random_delay` / `sleep` 记录事件顺序，逐项断言：① reaction 区间等于该 policy 的 profile 且只采样一次，`sleep` 用的就是它；② reaction 之后**一次** fresh 截图；③ 目标仍在 → 恰一次采样（在 fresh 帧的 roi 上）、L1 执行器一次（实参 `FinalPoint`）、后端一次、trace 记录同一坐标；④ **fresh confirm 失败分支**（长期契约）：目标消失 → 零采样零点击零 trace，返回 `False`，reaction 不重试，**不用旧坐标、不改点旧帧里的其它候选**，且业务后续分支符合预期（Pets 仍走 `goto_page`、刷新不误报成功且不进动画等待、岛屿由外层下一轮重扫）；⑤ 目标移动 → 用新帧坐标、旧 roi 从未被采样；⑥ 目标一开始就不在 → 不触发 reaction；⑦ 原 interval / 业务门槛（OCR 次数、`number == 0`）不变且不满足时不 reaction；⑧ 目标在 Navigator 边动作里时，用真实 `GameUi._execute_transition` + **虚拟时钟**（截图 / reaction 推进时钟，替换其 `Timer`）证明 6 秒 action 预算下「fresh 失败后重试成功」与「持续失败仍有界超时」，并在报告里给出成功路径耗时与超时尝试次数，不能宣称「总耗时不变」；⑨ AST 守卫只钉 `policy=InteractionPolicy.X` 关键字、无 `confirm_delay`、无新增直接点击，不替代运行期用例。变异验证同一工作区只能运行**一个**变异任务（脚本用锁文件互斥），每项独立子进程 + 超时，逐字节还原并核对哈希后再跑全量。
- **L1 Stage 3B：全局静态守卫与「项目排除模块单击迁入」的验证契约（2026-09-21，D026 补记；`dev_tools/click_entry_guard.py` + `tests/test_l1_stage3b_global_guard.py`）—— 长期规则**：
  ① 守卫失败信息是「文件:行号 函数 违规形式 → 建议的 L1 入口」：**修复 = 迁到 `execute_single_click` / `execute_long_click`，不是往 `ALLOWED_EXITS` 加条目**（新增出口须在 D026 补记理由）；② 守卫扫真实文件（rglob + 根脚本），新增文件天然被扫，含 Python 的顶层目录必须归类（`unclassified_roots`）；③ 识别形式是 AST：设备类接收者的 `click` / `long_click`、任何接收者的 `click_with_backend` / `click_<后端>` / `long_click_<后端>` / `multi_click`、非调用引用、`getattr` 字面量、设备别名传播；无法静态确定的动态调用进 `unresolved` 且视为失败待人工判定；④ 白名单精确到（文件, 函数, 调用形式, 次数），过期条目 / 缺失必需出口同样失败；⑤ **静态守卫 ≠ 运行期证明**：它不证明点击成功或坐标分布，运行期等价用例（迁移前表达式作独立参考、采样函数「一调用就失败」补丁、真实 `Control` + 假后端 + 真实 BehaviorTrace、迁移前源码快照 A/B 对照）必须同时存在；⑥ 验证守卫本身要用「违规注入」（普通任务 / 组件 / Login / DailyTrifles / WeeklyPurchase 的路径 + 真实文件恢复裸点）、「新文件 / 新目录发现」、「删除合法出口后不误报完整」、「整文件 / 整目录放行」类变异，每项独立超时并逐字节还原（含临时新增文件）；⑦ 同一守卫的测试代码里的假设备调用不属于生产，`tests/` `dev_tools/` 不被扫描。
- **L1 Stage 3A：长按执行入口统一的验证契约（2026-09-21，D026 补记；`tests/test_l1_stage3a_long_click.py`）—— 长期契约**：长按与单击的验证互相独立，任何一边都不能借另一边的断言过关。
  ① 执行器契约用**只暴露 `long_click` 的假设备**（执行器多碰 `click` / `screenshot` 属性当场失败）+ 包装采样器：`FinalPoint` 零采样、Rule 采样恰一次且等于 `coord()` 的固定随机源参考值、`duration` 用 `is` 断言原样透传、
  `control_name` 缺省 / 显式（含 `None`、空串）语义、`time.sleep` 从未被调、后端异常是同一对象、非法目标与单击执行器抛同一 `TypeError`；② 用**真实 `Control.long_click` + 假后端表 + 真实 BehaviorTrace** 逐个后端断言
  「恰一次、参数 `(x, y, duration)` 一致」，未注册的 `control_method` 回退 `long_click_adb`，`Control.click` / `click_with_backend` / 单击后端从未被调，trace 只有一条 `long_click`、后端失败不留 trace 行；
  ③ 6 个 primitive 点位用真实 BaseTask 方法驱动，事件序列（sample / execute_long / long / reaction / sleep / screenshot）与同一流程的**单击版本逐事件对照**（长按流程 = 单击流程，仅最后动作不同）；
  ④ 「迁移前表达式」参考（`coord()` + `<ms> / 1000` + 原 `control_name`）在同一 seed 下逐值相等；⑤ 生产真实的 `RuleLongClick` 资产逐个跑一遍；⑥ AST 守卫：BaseTask 无 `device.long_click`，6 个点位第一目标是
  `FinalPoint(...)`、时长是 `<ms> / 1000`、只有 3 个 primitive 使用长按执行器（`swipe*` / 拖拽不在其中），执行器体内只调 `resolve_click_point` / `getattr` / `device.long_click`，单击执行器不含长按调用；
  登记册 `scan_long_click_sites()` 锁定「业务消费点直调长按 = 0」。变异验证 21 组（改调 click / 二次采样 / 偏移 / 丢 duration / 毫秒未换算 / 再乘 1000 / 叠加 dwell / 调两次 / 改 control_name / 绕开 Control /
  吞异常 / 恢复直调 / 滑动误入 / Rule 直接交给执行器 / 降级为单击 / 单击执行器接受长按 / wait 路径改采样 action）每项独立超时并逐字节还原源码、核对哈希。
- **导航回退循环的真实驱动验证 + 墙钟能力边界的诚实表述（2026-09-22，ActivityShikigami 活动入口导航停滞；`tests/test_activity_shikigami_climb.py::FindActivityEntryFallbackDriverTest`）—— 长期规则**：
  ① 类似 `find_activity_entry` 这种「次数上限 + 逐帧识别 + 条件点击」的回退循环，只能用**真实驱动的帧序列假体**证明——假体必须显式区分「已经截过的当前帧」与「下一次 screenshot() 才会前进到的新帧」，
  不能让 `appear()` 提前看到未来帧的状态，否则测出的是假体的 bug 不是被测函数的行为（本轮就踩过一次这个 off-by-one）；
  ② 断言范围至少覆盖：切换成功后新帧立即生效返回、始终找不到时按次数上限退出、墙钟与次数上限两个独立上限谁先触发就按谁退出、截图 / 识别抛出的异常原样传播不被吞掉、
  「二次确认失败」不误判成切换成功、**截图调用次数**（不只是点击次数）符合「点击后新帧同时服务本轮确认与下一轮判断」的设计意图；
  ③ 加了新的第二重墙钟上限时，测试与文档都必须写清楚它的**能力边界**——只约束「正常返回控制权、跑到检查语句」的耗时，不能证明也不能保证中断某一次尚未返回的同步设备调用，
  不得把「离线测试通过」等同于「真机停滞已修复」；
  ④ 用到共享的确定性假体（如本文件既有的 `_FakeTimer`）时，凡是靠直接改类属性（如 `.budget`）传参的，测试必须显式保存并在 `finally` 里还原，
  不能只改不还——本轮就因为漏还原污染了同文件里另一个测试类（`SettlementDrainTest`），属于测试基础设施本身要长期防范的坑，不是一次性修复完就可以忘记的细节。
- **「已到目的页但子状态未就绪」不能并入盲点兜底分支 + 无界循环墙钟只在连续失败时计时（2026-09-22，ActivityShikigami 战后结算兜底乱点；`tests/test_activity_shikigami_climb.py::SettlementDrainTest` / `ClimbTypeUnknownPageTest`）—— 长期规则**：
  ① 一个「未命中目标状态就盲点」式的兜底循环，必须先分清楚「已经到了正确的目的页、只是某个子条件（如挑战键）还没就绪」与「压根不在目的页（真正的残留弹窗 / 未知帧）」——前者不该盲点，
  该复用同一任务已有的窄状态判定（本例是 `_enter_climb_battle` 的三态 `_wait_climb_fire_state`）去等，不能把两种状态合并成同一个「继续点安全区」分支，事故复现测试必须显式断言前者场景下盲点次数为 **0**（不是「更少」，是零），
  仅断言「点击次数不超过预算」不足以证明修复生效；
  ② 任何 `while True` / 无外部墙钟的主循环，只要存在「继续在循环体内空转、不落入任何有日志的分支」的路径，就是一个静默挂起隐患——真机上会表现为进程存活但日志长时间零输出，
  必须补墙钟，且这个计时器只应在**连续**处于该状态时累积，一旦状态变化立刻清零，用测试证明「短暂过渡不误判超时」与「间歇性恢复不会跨间断累加」两种场景都成立，而不是只测「一直失败会超时」这一种；
  ③ 同一次真机事故的证据可能不止对应一处代码缺陷——本轮任务给出的日志窗口只到「点击预算耗尽」的 WARNING 为止，实际读原始日志文件继续往后看，才发现同一次事故还牵出了下游一个完全独立的无界循环（且是 66 分钟量级的更严重停滞）；核对证据时不能只看用户截取的窗口，要顺着同一个日志文件核实窗口之外是否还有更多信号。

- **task-local 条件穿透 GeneralBattle 共享 handler 的验证契约（2026-09-23，ActivityShikigami 普通爬塔专用结算单击；`tests/test_activity_shikigami_climb.py::ActivitySettlementSingleClickTest`）—— 长期规则**：
  ① 一个「按 ownership flag 决定 `super()` 还是接管」的覆写（本例 `NormalClimbAct._handle_result`/`_handle_reward` 按 `_climb_owns_settlement_single_click` 二选一），flag 为假的分支必须用**真实 MRO** 驱动证明——`patch.object(GeneralBattle, '_handle_result')` 之类直接打在共享基类上、断言确实被调用到，而不是只读源码字符串确认写了 `return super()...`；MRO 本身也要单独断言一次（`ScriptTask.__mro__` + `ScriptTask._handle_result.__qualname__`），防止未来调整 mixin 顺序时静默改变谁先接管；
  ② 覆写重新实现共享方法的「周边逻辑」（本例 is_win 判定 / click_record_clear / 特殊弹窗短路 / boss 专属点击）时，必须为每一条周边逻辑单独写回归测试，证明接管分支没有丢失原方法里的既有业务行为——不能因为专注在「新加的单击事务」上就漏掉这些容易被悄悄砍掉的旁支；
  ③ 「每次都是独立完整事务、不预授权第二击、不跨调用复用 anchor」这类约束，要用**两次独立调用**去驱动（不是一次调用内部循环两次），并断言两次调用各自触发了完整的 reaction/采样/选择流程（如两次 `random_int` 都被真实调用、选中的 region 可能不同）——只测「单次调用最多点一次」不足以证明「连续调用之间也不共享状态」；
  ④ 改动会新增生产点击调用点（`execute_single_click` / `appear_then_click` 等）时，若目标文件已经在 `tests/test_l2_policy_migration.py` 的人工 `INVENTORY` 名单里，新增点位必须按真实源码出现顺序插入对应行，
  不能追加到列表末尾——登记册生成器按位置严格对齐，顺序错了会在完全不相关的报错信息里体现（“审计清单第 N 行不一致”），需要照着源码里方法定义的真实先后顺序找准插入点；
  ⑤ **task-local 事务必须持有自己的 timing 常量，测试要同时钉两头**（2026-09-23 同日收口）：一个已经从公共机制里独立出来的事务，若继续引用原机制的常量当 reaction（本例首版借用了 Micro-Burst 的
  `SETTLEMENT_BURST_CLICK_INTERVAL_RANGE`），就是把两种不同语义绑在一起、任一方调参都会误伤另一方；测试要**同时**断言「本线常量的精确值」「函数体（`_body()` 去掉 docstring 后）不再出现原机制常量名」
  「公共常量的值与用途原样未变（含它在原机制里的调用点仍在）」三件事，只测前者不足以证明没有顺手改掉全局；
  ⑥ 「reaction 必须在采样之前」这类顺序约束，要用**共享事件列表**把 `random_delay` / `sleep` / `screenshot` / 采样 / 点击各打一个标记，断言完整顺序等于预期列表，而不是分别断言各自被调用过——
  顺序错了（先采样再等待、跨等待复用坐标）在「调用次数」维度上完全看不出来。

- **L1 Stage 2：直接单击迁入执行器的等价性证明（2026-09-21，D026 补记；`tests/test_l1_stage2_direct_clicks.py`）—— 长期契约**：迁移点击执行入口而不改采样时，等价性不能用「当前实现对比当前实现」证明：
  ① **固定随机源对照**——把 `module.click_sampler._rng` 与 `module.base.utils.random._rng` 换成同一个 `random.Random(seed)`，以「迁移前的采样表达式」（如 `ClickSampler.sample_target(select_area, rule.name)`、`rule.coord()` ×2、
  `ClickSampler.sample_point(roi, wide_card)`）作独立参考，迁移后真实函数在同 seed 下驱动，后端坐标逐个相等；② 包装采样器与执行器，断言采样种类 / ROI / 身份 / 次数、执行器实参（`FinalPoint`，区域点击是
  `ClickRegion`）、`control_name`、等待 / 截图 / 识别次数与 BehaviorTrace 坐标；③ 需要时用迁移前源码快照（仓库外）以别名模块加载做一次性 A/B 对照；④ AST 守卫：目标函数无 `device.click`、原采样调用原位保留、
  没有新增等待 / 识别；⑤ 「源码字符串」型旧断言（如 `ClickSampler.sample_region(...)` 字面、`coord()` 先于 `device.click(`）随实现形态变化时改成结构等价的新形式并补运行期断言，**不能删除或放宽**；
  ⑥ 爆发式点击（Settlement burst）要单独断言「一个锚点只采样一次、多次点击坐标相同」。变异验证覆盖恢复裸点 / Rule 双采样 / 锚点重采样 / 采样函数产生点击 / 复用同一个点 / 采样模式改变 / 丢 profile / ROI 扩大 /
  新增等待或识别 / control_name 与后端参数丢失，每项独立超时并逐字节还原。
