# 开发日志

> 按时间倒序（最新在顶）追加真实项目变更，不覆盖历史。遵循 `DECISIONS` D073：单条建议 ≤ 15 行，写清根因/改动/验证/待实测点，不写本机临时路径或一次性日志文件名；按月滚动归档，不删历史。

| 月份 | 状态 | 位置 | 条目数 |
|---|---|---|---|
| 2026-11 | 活跃（含瘦身与补救条目） | 本文件（统一倒序） | 83 |
| 2026-10 | 已归档 | [develop_log_2026-10.md](archive/develop_log_2026-10.md) | 97 |
| 2026-09 | 已归档 | [develop_log_2026-09.md](archive/develop_log_2026-09.md) | 112 |
| 2026-08 | 已归档 | [develop_log_2026-08.md](archive/develop_log_2026-08.md) | 10 |

---

## 2026-11-27 — 审查阶段收尾发布（整合至 origin/master，不含 	ests/ 变更）

- **发布范围与整合基线**：基于远端 origin/master（保留既有每日琐事无红点邮箱修复与远端既有测试），整合本地最终生产源码、配置模型、模板规则、开发/守护工具（含 dev_tools/assets_extract.py、dev_tools/guarded_unittest.py）、精简归档文档、Skill 入口及全部业务素材（含 login_login_8.png、login_login_16.png 及 MetaDemon 等未引用/预留素材）。
- **排除与校验口径**：本发布提交不含任何 	ests/ 用例或测试夹具变更（原工作区测试改动原样保留）；P1-3、P1-6、P2-3 未处理，[CURRENT.md](CURRENT.md) 保持 idle 原样未改；仅代表审查范围内局部静态与最小离线复核，不代表全量、真机、浏览器或远端树完整测试已通过，待实测项见 [ROADMAP.md](ROADMAP.md)。

## 2026-11-27 — 审查 P2-4 ~ P2-8 局部修复（标注器保存隔离、文档口径对账与普通恢复 stderr 处理）

- **标注器阈值保存去 `os.chdir` 与事件循环解耦（`P2-4`）**：
  - [assets_extract.py](../dev_tools/assets_extract.py) `AssetsExtractor` / `ImageExtractor` / `ListExtractor` 新增可选 `root_path`（默认仍回落 `Path.cwd()` 兼容旧调用）；[tool.py](../module/server/tool.py) `save_chess_candidate_thresholds()` 移除 `os.chdir()`，改用显式根目录加管理器保存锁串行化四份产物及热更新，[tool_router.py](../module/server/tool_router.py) 改用 `asyncio.to_thread()` 调度并保留 `AnnotatorError` 映射。
- **L2 映射、ROADMAP 与核心文档对账（`P2-5` / `P2-6` / `P2-7`）**：
  - [L2_INTERACTION_POLICY_MAP.md](L2_INTERACTION_POLICY_MAP.md) 标注 §7 `D068` 已撤回作废并指回恢复后的 [script_task.py](../tasks/MetaDemon/script_task.py)，§2 表内实算修正为 `KEEP_SPECIAL=39` / `合计=184`（含 `L2M-077a`）；
  - [ROADMAP.md](ROADMAP.md) 补回 `D059` 道馆 `layout` 前端未实现待办、`D025`（`page_reward` 布局交接 / `I_FALSE` 战败安全区）及 `D055`（`I_PET_PRESENT`）待真机项；
  - 补全 [AI_CONTEXT.md](AI_CONTEXT.md) `ROADMAP_before_slimming_2026-11-27.md` 索引，同步 `AGENTS.md` / `CLAUDE.md` 的 `TESTING §1/§5.1` 引用，统一 [ARCHITECTURE.md](ARCHITECTURE.md) 探索 `D053` 局部三态及 `frame_state` / `FrameWait`（含 `SwitchSoul` 与 `Dokan/welfare.py`）生产消费者口径。
- **普通恢复 `stderr` 透传与冲突口径（`P2-8`）**：
  - [oas_context.py](../.agents/skills/oas-architect/scripts/oas_context.py) `git_output()` 在 `returncode=0` 遇非空 `stderr` 时透传 `sys.stderr` 而不中断恢复或污染 `stdout`；保留 `oas_strict.py` 遇警告即失败的严格契约与 `count_changes()` 多维并列计数（补充非互斥说明，原报告冲突计数缺陷判未证实）。
- **最小离线验证（D069，未跑全量/设备/浏览器，阶段累计 8.4s / 120s，余 111.6s）**：
  - 5 个改动 `.py` 文件 `py_compile` 通过；[test_chess_annotator_and_detail_name.py](../tests/test_chess_annotator_and_detail_name.py) 2 项隔离/线程/并发保存测试通过（退出码 `0`）；`oas_context` / `oas_strict` 合成样本与文档静态/链接核对全部通过。

## 2026-11-27 — 审查 P2-1 / P2-2 局部修复（Chess 穿戴连败优先核名与 `direct_only` 占格收口）

- **穿戴连败优先核名可达性（`P2-1`）**：
  - [hand_operations.py](../tasks/Chess/runtime/hand_operations.py) `_run_board_check_and_arrange_slice()` 内的 `_inspect_priority()` 将 `stale_reason == 'equip_failed_needs_reverify'` / `suspect_merge` 的 `(0, 0, ...)` 判定移至 `valid and satisfies_config` 提前返回之前（保留 `vis_state == 'occupied'` 与 `slot_inspect_cooldown` 守卫在最前），不清空现有有效身份/星级/装备缓存；核名成功按现有流程清除 `stale_reason`，失败写入冷却且受单切片预算保护。
- **`direct_only` 阶段受阻占用格防提前核名与防硬顶错位卡（`P2-2`）**：
  - [hand_operations.py](../tasks/Chess/runtime/hand_operations.py) `deploy_shikigami_from_hand()` 在 `direct_only=True` 时：① 对 `occupied` 且缓存失效格不提前消耗核名预算，直接置 `_last_deploy_stopped_for_direct_only = True`、暂缓并继续其他空位候选；② 对目标格占着其他错位非可回收重复阵容卡时不再跳过 D2 直落拖拽顶回手牌，同样置停止标记暂缓交由后续 `direct_only=False` 先搬后上；保留合法同名高星替换、共位/降星/有装备及金鱼保护。
- **最小离线验证（D069，未跑全量、未启设备/OCR，阶段累计 8.8s / 120s，余 111.2s）**：
  - [test_chess_prep_arrange.py](../tests/test_chess_prep_arrange.py) 新增 `P2EquipReverifyAndDirectOnlyDeployTest` 3 项（已在 B 基线复现失败）；修复后定向 5 组 13 项跑通 12 项（含全部新增 3 项），仅范围外既有 `test_higher_star_replaces_unequipped_lower_but_defers_equipped_with_warning` 因既有过滤与日志适配器问题在 B/C 均未通过；真机流程待 Level C 实测。

## 2026-11-27 — 审查 P1-4 / P1-5 局部修复（L2 点击登记对账与福利道馆 1.85s 缓冲对齐）

- **L2 点击登记册与守卫漂移收口（`P1-4`）**：
  - 使用 [dev_tools/click_callsite_register.py](dev_tools/click_callsite_register.py) 重新生成 [docs/L2_CALLSITE_REGISTER.md](docs/L2_CALLSITE_REGISTER.md)，将现行源码规则增量（`1146 → 1159`、`rule 942 → 955`、`KEEP_IMMEDIATE 640 → 650`、`ALREADY_L2 105 → 106`、`NEEDS_C 7 → 9`、`policy_sites 104 → 105`）同步至 [tests/test_l2_c0_registry.py](tests/test_l2_c0_registry.py)、[tests/test_l1_l2_integration.py](tests/test_l1_l2_integration.py) 与 [tests/test_l2_interaction_reaction.py](tests/test_l2_interaction_reaction.py)，保留 `human=187` / `c0=17` 及 C0 原有 7 处 `human` `NEEDS_C` 不变；
  - 将 `XinLan` `recover_xin_lan_navigation(I_FRIENDSHIP_UP, policy=InteractionPolicy.NAVIGATION)` 逐点纳入 `POST_C1_CONSUMERS` 与 `TimingOwnershipTest`，新增的 `DemonRetreat._open_demon_retreat(I_DEMON_START)` 与 `SixRealms` `BasePeacockKingdom._confirm_boss_giveup_dialog(I_UI_CONFIRM)` 按 `rule/R9` 标为 `NEEDS_C` 候选（尚待真机/复核，不计作完成）。
- **福利道馆准备缓冲文案与断言对齐（`P1-5`）**：
  - 保留 [tasks/Dokan/welfare.py](tasks/Dokan/welfare.py) `PREPARE_CLOSE_BUFFER_SECONDS = 1.85` 与流程逻辑不变，同步该文件文档字符串、`assets/i18n/zh-CN.json` / `en-US.json` 帮助文案、[docs/ROADMAP.md](docs/ROADMAP.md) 与 [tests/test_dokan_welfare.py](tests/test_dokan_welfare.py) / [tests/test_dokan_welfare_weekdays.py](tests/test_dokan_welfare_weekdays.py) 的 `1.85` 断言（未改动 `1 秒` 排名遮罩说明）。
- **最小离线验证（D069，未跑全量、未启设备/OCR，阶段累计 40.0s / 120s，余 80.0s）**：
  - 6 个 `.py` 修改文件 `compile()` 与两份 i18n JSON 解析通过；定向守护测试 40 项（涵盖 `test_l2_c0_registry`、`CallsiteRegisterGuardTest`、`TimingOwnershipTest`、`TemplateAndTranslationTest` 及 `PrepareBufferTest` 等 `1.85s` 用例）全部通过（退出码 `0`）；真机表现与新增 `NEEDS_C` 候选待 Level C 实测。

## 2026-11-27 — 审查 P1-1 / P1-2 局部修复（Chess 续作经济阻塞防忙循环与孔雀国放弃超时异常出口）

- **Chess 准备续作经济阻塞收口（`P1-1`）**：
  - [tasks/Chess/runtime/state.py](tasks/Chess/runtime/state.py) 的 `ChessRoundProgress` 声明 `_followup_economy_done: bool = False`，确保经 `decide_round` 的 `dataclasses.replace()` 跨帧保留并在新回合 `begin_round()` 自然重置；
  - [tasks/Chess/script_task.py](tasks/Chess/script_task.py) `_run_preparation_economy_until_time_limit()` 显式返回 `'complete' | 'blocked' | 'time_limit' | 'interrupted'`（保持原有调用方兼容）；`_run_preparation_followup_slice()` 第 7 步收到 `'blocked'` 后置 `_followup_economy_done = True`、在备阶段内顺手关闭已开商店且不再自增 `budget.actions_done`，保留本回合其余续作与下回合经济尝试，切战/符咒/余时 `<15s` 保护不变。
- **孔雀国放弃试炼超时出口（`P1-2`）**：
  - [tasks/SixRealms/peacock_kingdom/peacock_kingdom.py](tasks/SixRealms/peacock_kingdom/peacock_kingdom.py) `_give_up_trial()` 超过 `GIVEUP_TIMEOUT`（30s）后不再返回 `False` 回主循环重入清卡死，直接带相位/页面上下文抛出 `GameStuckError`；`run_on_pk_main()` 保留成功路径 `raise TaskEnd`，超时分支不清空 `stuck_record`。
- **最小离线验证（D069，未跑全量、未启设备/OCR，阶段累计 10.4s / 120s，余 109.6s）**：
  - 5 个改动文件 `compile()` 检查与 2 组 12 项定向守护测试（[tests/test_chess_prep_arrange.py](tests/test_chess_prep_arrange.py) `PreparationFollowupContinuationTest` 3 项、[tests/test_six_realms_breath_and_exit_confirm.py](tests/test_six_realms_breath_and_exit_confirm.py) `BossGiveUpWithoutThunderTest` 9 项）全部通过（退出码 `0`）；真机阻塞与超时恢复待 Level C 实测。

## 2026-11-27 — DOC-SLIM-20261127 最小范围补救（ROADMAP 完整原文快照与证据口径修正）

- **补救范围**（仅涉及 3 份文档，不回滚上一轮瘦身成果、不改 `D001`–`D072` 与既有归档）：
  - 新增 [ROADMAP_before_slimming_2026-11-27.md](archive/ROADMAP_before_slimming_2026-11-27.md)（按上一轮瘦身前原始字节逐字节无损复制，345,101 字节），补齐此前分段归档未覆盖的旧 P0/P1/P2 细则（如式神活动配置页 `initial_expanded`、`range.min/max` 保存计数与旧后端 404/空响应回退等）；
  - 修正 [ROADMAP.md](ROADMAP.md) 归档指针，明确区分「瘦身前完整原文快照」与分段历史归档 [ROADMAP_done_2026-09_11.md](archive/ROADMAP_done_2026-09_11.md)，主文件活跃待办与 Level C 清单保持不变；
  - 修正下方上一轮瘦身条目的证据表述：明确上一轮非目标业务 WIP 缺少开始内容指纹，无法仅凭 Git 状态证明内容未变（亦未发现业务文件被误改），并与本轮全仓指纹校验所证明的「补救前后非目标文件未变」区分记录。
- **验证**：来源与新快照字节数/SHA-256 及逐字节比对一致、相对链接有效、`ROADMAP` 正文待办与 Level C 零变化、UTF-8 与 `git diff --check` 通过、全仓基线 B→C 仅上述 3 份允许文件变化。

## 2026-11-27 — 文档体系无损归档瘦身与单事实源（D073）规则收口

- **背景**：6 份核心文档累计达 19,457 行 / ~2.90 MB，存在顶部流水堆积、跨文档全文复写、本机临时路径残留及 `DEVELOP_LOG.md` 11 月条目首尾断层问题。
- **改动范围**（计划并操作 10 份文档/规则与 7 份归档；更正说明：上一轮基线 manifest 仅保存上述 10 份目标文件指纹，非目标业务 WIP 缺少开始内容指纹，无法仅凭 Git 状态证明内容未变，亦未发现业务文件被误改）：
  - 按月归档 [develop_log_2026-08.md](archive/develop_log_2026-08.md)（10 条）、[09.md](archive/develop_log_2026-09.md)（112 条）、[10.md](archive/develop_log_2026-10.md)（97 条），合并并统一倒序保留 2026-11 全量 81 条历史记录；
  - 将 `AI_CONTEXT`（`§4.110~§4.187` 及顶部流水/旧基线）、`ROADMAP`（分段历史归档，部分旧 P0/P1/P2 细则未纳入该分段归档，已由上方同日补救条目另存完整原文快照 [ROADMAP_before_slimming_2026-11-27.md](archive/ROADMAP_before_slimming_2026-11-27.md)）、`TESTING`（单任务测试桩细则）、`CURRENT`（旧检查点）分别迁入 `docs/archive/` 对应文件，主文档重置为轻量快照/活跃清单/通用规则；
  - `DECISIONS.md` 保留 `D001`–`D072` 原文不动，新增顶部模块索引与 `D073`；同步更新 `AGENTS.md`、`CLAUDE.md` 与 `oas-architect` 收尾同步口径。
- **验证**：归档条数守恒、`D001`–`D072` 逐字节校验、UTF-8 编码、相对链接、`oas_context.py status` 与 `git diff --check` 静态检查均通过。

## 2026-11-27 — 百鬼棋局上卡受阻全盘恢复最小补丁（1..12 占位回收与局部 unknown 人口兜底）

- **现场排查（`log/2026-11-27_oas2.txt`，12:21～12:28）**：
  - 回合 19/21/22（L5752、L5864、L5921）：`round_state.py:0756` 连续记录 `level=8, occupied=9 [1, 2, 4, 5, 6, 8, 9, 11, 12], unknown=[3], arakawa=active(count=4, reason=qualified), expected_occupied=9, visual_state=unknown, full=False, source=runtime_state_fallback`，紧接着 `寻香行` 连续三个回合被反复直拖向 `target_state_before=unknown` 的 3 号位并因 `slice_wall_exhausted` / `specifics_not_opened` 失败；同时若 1 号位站着重复副本或非阵容单位，`_find_verified_arakawa_recall_slot()` 仅扫 `BOARD_RECALL_POSITIONS=(6,12,5,11)` 不会查 1 号位。
- **开始基线与增量范围**（基线 `C:\Users\cbz19\.gemini\antigravity\brain\20a23827-6a35-4e98-9dc1-4196c4f10194\scratch\baseline_blocked_recover`；不改公共人口计算 `round_state.py`、`settings.py`、装备/买卡/金鱼策略及 `docs/CURRENT.md`，仅局部修改 [hand_operations.py](file:///d:/oas_xy/OnmyojiAutoScript-easy-install-self/OnmyojiAutoScript-easy-install/tasks/Chess/runtime/hand_operations.py) `+409/-106` 与 [test_chess_prep_arrange.py](file:///d:/oas_xy/OnmyojiAutoScript-easy-install-self/OnmyojiAutoScript-easy-install/tests/test_chess_prep_arrange.py) `+277/-0`）：
  1. **局部人口满员证据兜底**：`_classify_lineup_capacity_state()`（L4108）与 `_can_direct_deploy_lineup_card()`（L7237）在保持 `round_state.py` 不动的前提下，对非 Boss 回合且 `board_occupied >= expected_occupied > 0` 返回 `'full'`（`expected_occupied` 为 `None` 或未达标时仍保守返回 `'unknown'`，不自行按 `level+1` 猜测）；
  2. **全盘 `1..12` 占位查找与有界核名**：`_find_verified_arakawa_recall_slot()`（L4459）扩展为 `(6,12,5,11,1..12)` 全盘扫描——先 0 点击复核全盘已确认 `non_lineup` 与可回收重复副本，再有界核查未登记占格（在切片预算 `budget is not None` 下最多主动详情 1 次，保护金鱼、本体、更高星副本及 `unknown` 单位）；`_verify_arakawa_recall_candidate()`（L4314）在无预算时检查余时、回写 `_record_slot_inspection_result()` 至共享 `board_slots` 并在失败/不可读时写入 `slot_inspect_cooldown` 防止重复点同一格；
  3. **受阻统一恢复与 `unknown` 防盲拖**：抽出 `_execute_verified_blocker_recall_and_rescan()`（L4663），`deploy_shikigami_from_hand()`（L7347）覆盖「可回收占位挡目标格」「空位或局部 `unknown` 但人口已满」「未查明 `unknown` 目标格」三类情况——一次只收 1 人、回收失败即停、确认腾格后新截图重扫新坐标上配置格、余时不足仅存 `_record_await_deploy_todo()`，禁止向 `unknown` 目标格反复盲拖。
- **验证与证据（D069 最小验证，未跑整模块/全量、未启设备或 OCR，阶段累计 `9.4s / 120s`，余 `110.6s`）**：
  - `py_compile` 与目标 `git diff --check` 退出码 `0`；
  - 首轮 `BlockedDeployFullBoardReliefTest` + `SameNameStarProtectionAndDuplicateYieldTest` + `BounceBackAndStaleRecoveryTest`（[related_20261127_125225_4468.log](file:///d:/oas_xy/OnmyojiAutoScript-easy-install-self/OnmyojiAutoScript-easy-install/log/test_runs/related_20261127_125225_4468.log)，`5.0s` / `448 MiB`）：`SameNameStarProtectionAndDuplicateYieldTest`（2/2）与 `BounceBackAndStaleRecoveryTest`（2/2）及 `BlockedDeployFullBoardReliefTest` 场景 1、2 全部通过，仅场景 3 测试桩 `_read_left_arakawa_bond_status` 返回 `'ok'` 而非 `'qualified'`；
  - 仅修正场景 3 测试桩 `'reason': 'qualified'` 后复跑 `BlockedDeployFullBoardReliefTest`（[related_20261127_125309_23924.log](file:///d:/oas_xy/OnmyojiAutoScript-easy-install-self/OnmyojiAutoScript-easy-install/log/test_runs/related_20261127_125309_23924.log)，`4.4s` / `Ran 3 tests in 0.072s` / 峰值 `455 MiB`，0 skipped）：**3/3 通过**。真实真机效果待 `oas2` Level C 实测。

## 2026-11-27 — 百鬼棋局御魂空留解除、同名拖前核名护星与重复式神让位（三项局部修复）

- **现场证据与根因（`log/2026-11-27_oas2.txt`）**：
  - `10:43:15~10:43:19`（L2391–2409）：`1★ kappa` 拖向身份缓存已失效的 12 号位，拖后详情才读出 `kappa`，记为 `confirmed_at_target` 但出现 `hand_consumed=False (2->2), hand_stars=(1,1)->(1,2), board_star=2->1`；
  - `11:08:15~11:08:17`（L3501–3510）：`1★ zashiki_Warashi` 拖向身份缓存失效的 2 号位，详情 `insufficient_remaining_for_inspect` 未开，`hand_stars=(1,)->(2,), board_star=2->1`；
  - `11:11:53`（L3661–3668）：`emergency_cleanup_hand()` 因旧槽预留规则与先判 `equip_sale` 顺序导致 `equipped=[], sold_equipment=[]` 并 `10->10/10` 退出，进而触发兜底出售 `kappa`。
  - 另按用户实盘场景补充重复式神让位：6 号位已确认站定配置式神（如 `kingyohime` 带装备）而系统自动上阵同星副本到 11 号位占格/满员时，新阵容卡被阻挡。
- **开始基线与修改范围**（基线 `C:\Users\cbz19\.gemini\antigravity\brain\20a23827-6a35-4e98-9dc1-4196c4f10194\scratch\baseline`，保留全部预存 WIP、用户配置/阵容/素材/ROI/阈值、`economy.py`/`frame_cards.py`/`assets.py`/`strategy/*`/公共交互入口及 `docs/CURRENT.md` 不动，仅局部调整 `tasks/Chess/runtime/hand_operations.py` 与 `tests/test_chess_prep_arrange.py`）：
  1. **御魂与候选空间（替代 D072 原“配两件指定御魂就常规空留两槽”策略）**：
     - `_unit_equipment_slot_budget()`（L809）解除对未到手指定御魂的空槽锁定（`generic_free_slots = max(0, free_slots - unmet_emblems)`），保留两槽上限、禁重复与指定纹章硬预留；
     - `_soul_hand_reserve_info()` / `_soul_reserve_count()`（L5362–5425）按当前手牌与每个式神 `unmet_soul_slots` 有界预留（不按 `preferred_souls` 候选列表长度机械锁死），`_soul_target_entries()` 在 `relax_soul_reserve=True` 且指定对象仍未上阵时放行通用分配（仍不释放指定纹章）；
     - `_select_next_sellable_equipment_for_cleanup()`（L8151）复用同一有界预留口径并在 `protected` 计算中剔除已在 `reserve_owners`/`emblem_needing` 计入的式神防重复计数；`emergency_cleanup_hand()`（L8289）重排为「普通装配 → 满仓释放未上阵指定御魂走通用装配 → 既有卖超预留装备 → 非阵容卡」，不新增卖阵容卡行为。
  2. **同名星级保护（替代 D071/D072 占用格未核名先直拖尝试）**：
     - `_registered_actual_position()`（L881）拒绝失效的非 `init` 格级记录；
     - `deploy_shikigami_from_hand()`（L7114）在目标格 `occupied` 且 `_is_board_slot_cache_valid()` 为 False（或非 `legacy_seed` 视觉星级变动）时，拖前必须先执行至多 `1` 次有界核名：无查询预算、余时不足或核名失败均零拖拽暂缓；同名任一必要星级缺失不按 1★ 猜、`场上 >= 候选` 零拖拽；不同名转入既有占位处理；
     - `_deploy_lineup_hand_card_direct()`（L3544）在拖后详情即使同名也拒绝把降星（`same_name_board_star_decreased`）或高星替换未确认（`same_name_replace_not_confirmed` / `same_name_replace_star_unconfirmed`）记为成功，并失效格缓存、记告警与有界留证，防止同轮盲目循环补拖。
  3. **重复阵容式神让位（扩展原仅回收 `non_lineup` 规则）**：
     - 新增 `_has_other_satisfied_copy()` / `_is_recallable_duplicate_slot()` / `_find_verified_duplicate_recall_slot()`（L4137–4310），严格要求本体与副本身份/位置/星级有效且一致、本体在配置位且 `main_star >= dup_star`、副本不在配置格且非已站定金鱼（保留 `liuhuo` 等同位多配置兼容）；
     - `deploy_shikigami_from_hand()`（分支 D2/E）与 `_recover_after_confirmed_not_deployed()` / `_find_verified_arakawa_recall_slot()` 在上卡因副本地占或满人口被挡、`needed_names` 非空、手牌 `< 10` 且余时充足时直接保护本体并回收副本（`_recall_one_system_board_card(..., allow_verified_duplicate=True)`，L8925），随后 `screenshot()` 重扫手牌新坐标上阵；余时不足以 `_record_await_deploy_todo()`（L6694）登记待办绝不复用旧坐标；
     - `_run_board_check_and_arrange_slice()`（L6719）按已过滤的 `needed_names`（剔除无可补卡如仅持有已上阵同名多余卡）仅在受阻且有待补阵容卡时作为 `non_lineup` 之后备选让位；`_mark_board_unit_returned_to_hand()`（L731）与 `_recall_one_system_board_card()` 在本体仍满足配置位时仅清副本格并保持本体上阵/站位/装备历史无损、不打 `'uncertain_after_return'` 且不生成反复拖向本体格的待办。
- **验证与证据（D069 最小验证，未跑全量/未启动设备或 OCR，阶段累计 `16.5s / 120s`，余 `103.5s`）**：
  - `tasks/Chess/runtime/hand_operations.py` 与 `tests/test_chess_prep_arrange.py` 编译（`py_compile`）及 `git diff --check` 均退出 0；
  - `tests.test_chess_prep_arrange` 首跑（`related_20261127_114829_26688.log`，7.7s / `Ran 25 tests in 3.100s`）：22 项通过；仅 `CandidateComparisonAndStarPriorityTest::test_higher_star_replaces_unequipped_lower_but_defers_equipped_with_warning` 因基线预存 WIP `_candidate_deploy_eligibility_exclusions()`（L6950）先于分支 C 静默排除已穿装备式神而缺少 `WARNING`（范围外预存缺陷，仅记录不顺带修改），以及新加测试 A/C 的 2 处测试夹具断言调整；
  - 修正测试夹具复跑针对性增量类 `EquipmentPolicyATest` + `SameNameStarProtectionAndDuplicateYieldTest`（`related_20261127_115113_29144.log`，4.2s / `Ran 5 tests in 0.266s`，峰值 455 MiB，0 skipped）：**5/5 通过**（覆盖场景 A/B/C 及边界）。
  - 附记录（未跑且已知受替代旧断言）：`tests/test_chess_frame.py` 中 `DirectDeployResilienceTest::test_acceptance1` / `PreparationOrderAndBlockingGoldfishTest` / `LineupCapacityStatusTest` 仍按 D071 旧口径断言“未核名占格先直拖再查详情”，未顺带改写该长耗时测试组。真机实效待用户 `oas2` 实测。

## 2026-11-27 — 最小验证与改动范围收口补充

- 用户明确要求“只要做最小测验，审查改动内容不要扩散bug，收住口子”。在D069、TESTING及项目/Skill入口同步：仅审查本次增量与直接调用方，默认复用最小用例、不新增测试文件/复杂替身；范围外缺陷只记录报告，扩大修改须先确认。批准范围内明确缺陷先修，完成最小检查即停止离线扩测。
- 本轮仅规则文档调整，检查编码、入口一致性及本轮diff，不跑业务测试、不启动设备、不改业务代码/CURRENT、不提交。ARCHITECTURE和ROADMAP无需更新，软件分层和业务待办未变。

## 2026-11-27 — 验证预算收紧与执行者角色通用化（D069补记）

- 用户批准：降低离线测试占比，采用最小离线检查→尽早交付实测→按现场反馈小步修正；开发后由Codex审查并测试。用户另明确不固定谁开发，统一称执行者。
- 同步AGENTS/CLAUDE入口、oas-architect主Skill及交接/审查references、TESTING、D069与AI_CONTEXT；默认1～3个关键场景，普通阶段累计120秒覆盖实施/复修/复核，交接不重置，已有有效证据复用。保留现有测试、授权与守护边界。
- 本轮仅规则/文档更新，采用静态一致性、链接、编码与本轮增量检查，不运行unittest、compileall或游戏场景。未改业务代码、未启设备/服务、未提交；未宣称客户端自动发现或真机通过。ARCHITECTURE及ROADMAP无需更新：未改变软件分层、玩法及业务待办/实机授权范围。CURRENT保持原样。

## 2026-11-26 — 百鬼棋局准备阶段整理流程首版（CHESS-PREP-ARRANGE-V1）

- **现场复核（`log/2026-11-26_oas2.txt` 与两组报错截图）**：
  - `19:53:10~19:53:15`（及对应 `log/error/oas2_1795693995123/`、`log/error/oas2_1795694489054/` 原图 `720×1280`）：离线用 `ImageRuntime` + `FrameShim` 解码实图证实，久次良拖 9 号位瞬间前帧仅剩 1 张手牌（`2 -> 1`）、后帧恢复 2 张，座敷童子拖 2 号位同理从丢失恢复为 1 张（`score ~ 0.995`），而旧判据见单帧掉牌即按 `hand_consumed=True` 记入长期 `pending`，导致久次良被永久封锁；
  - `20:20:07~20:20:30`：查询 9 号位由 `O_DETAIL_NAME` 读出他阵容式神「言灵」，却只保留 `target_occupied_by_other` 与久次良 `pending`，没有触发言灵换位或逐格整理；随后继续买久次良直至剩 2 秒跳过补上阵，首轮结束后约 20 秒干等直到开战。
- **基线与约束**（开始基线 `C:\Users\cbz19\.gemini\antigravity\brain\ef2c17eb-212b-4b2f-a490-ca543301cf96\scratch\oas-chess-prep-v1-20261126\baseline`，`HEAD cbba5986ed23e62af3d16ee303a3e9ad1036c389`；仅改动 `tasks/Chess/runtime/{settings,state,decision,state_loop,round_state,hand_operations}.py`、`tasks/Chess/script_task.py`、`tests/test_chess_frame.py`（4 处已批准行为同步）与新增 `tests/test_chess_prep_arrange.py`，保留全部既有 WIP，不改 `economy.py`、`frame_cards.py`、`assets.py`、`strategy/*`、素材/ROI/阈值、`module/*`、`config/*` 及 `docs/CURRENT.md`）：
  - `tasks/Chess/runtime/settings.py` & `state.py`：新增 V1 运行常量（`DEPLOY_SETTLE_WAIT_TIMEOUT=1.6`、`DEPLOY_CONFIRM_STABLE_FRAMES=2`、`PREP_SLICE_MAX_INSPECTS=1`、`PREP_SLICE_MAX_WALL_SECONDS=4.5`、`PREP_ACTION_MIN_REMAINING=3`、`DISPLACED_LINEUP_COOLDOWN_SECONDS=2.0`、`DISPLACED_CHAIN_MAX_STEPS=4`、`SLOT_EMPTY_CONFIRM_FRAMES=2`、`SLOT_STAR_CHANGE_CONFIRM_FRAMES=2`、`PREP_FOLLOWUP_MAX_DURATION_S=25.0`、`PREP_UNKNOWN_TIME_SLICE_BUDGET_S=8.0` 等）及 `ChessRoundProgress` / `ChessGameState` 主状态字段（`board_slots`、`last_board_snapshot`、`board_equipment_status`、`displaced_lineup_todos`、`board_check_cursor`、`goldfish_search_progress` 等）。
  - `tasks/Chess/runtime/decision.py` & `state_loop.py` & `round_state.py`：新增 `ChessAction.PREPARE_FOLLOWUP` 与备阶段续作切片分派；`_GAME_STATE_FIELDS` 补齐代理，切战/符咒弹窗/新开局正确复位；`round_state.py` 百鬼后对账同步刷新 `board_slots`。
  - `tasks/Chess/runtime/hand_operations.py` & `script_task.py`：
    1. `_confirm_deploy_settled_state()` 结合手牌数/星级与目标占格状态等待稳定，`confirmed_not_deployed` 记 `hand_consumed=False` 且不永久封锁，`_cleanup_nonblocking_pending_deploys()` 可按当前稳定格证据恢复旧 `pending`；
    2. 建立以格号 `1~12` 为主键的 `board_slots` 真值表与视觉两帧防抖（`_sync_board_slots_with_visual_scan()`），切回合及非策略测试夹具兼容同步，已放置金鱼受视觉防误清保护；
    3. 候选对比（同名 `>=` 跳过、`>` 且无装备替换、星级 `None` 暂缓、已有装备低星暂缓并经 `_candidate_deploy_eligibility_exclusions()` 放行至分支 C 记 `WARNING` 告警、错位高星优先整理移位）；被顶回手经 `_reconcile_displaced_slot_occupants()`（含三合一 `copy_units` 差分与 `'uncertain_after_return'` 保留历史属性标记）及 `_process_displaced_lineup_todos()` 重扫最新手牌坐标重上；支持 `LIUHUO` 同格多配置保护，无阵容可上卡不回收非阵容、绝对不回收 `unknown`；
    4. `_run_board_check_and_arrange_slice()` + 共享 `PrepSliceBudget` 推进逐格巡检整理与金鱼跨切片续查，首轮第 5 步装备在经济前保底执行；
    5. 装备策略 A `_unit_equipment_slot_budget()` 按 0/1/2/多偏好御魂上限封顶 2 槽、满手 `relax_soul_reserve=True` 适度退让、偏好纹章永不退让、通用魂按配置前后排选魂按实际格号落点、`uncertain_after_return` 禁配新装备；
    6. `script_task.py` 新增 `_should_enter_preparation_followup()` 与 `_run_preparation_followup_slice()`，无变化零动作累加 `prep_followup_idle_count` 防忙循环，`_start_chess_game()` 全量初始化新字段。
- **既有测试断言同步**（`tests/test_chess_frame.py` 4 处，均对应已批准设计变更）：
  - `test_preferred_equipment_priority_reservation_and_surplus_allocation`（`shouzu` `position` `9 -> 3` 对齐策略 A 前/后排配置判别）；
  - `test_generic_souls_use_actual_row_respect_slots_and_keep_state_on_unconfirmed_drag`（`kaoru` 配置后排 8 实际 2 仍配输出魂 `wangqie@2`、`suzuka_gozen` 配置前排 3 实际 9 仍配功能魂 `beifu@9`）；
  - `test_preparation_order_initial_deploy_and_post_buy_redeploy_before_economy_and_goldfish`（断言首轮 `equip_events[0]` 发生在 `idx_eco1` 之前）；
  - `test_blocking_goldfish_pending_relocation_keeps_guards_in_tail_and_next_round_retry`（步骤 4b 将错位 `arakawa_no_nushi` 从 12 移回 10 后期望 `['CHESS_DEPLOY_KAPPA_SET_11', 'CHESS_MOVE_BOARD_SET_12_TO_10']`）。
- **验证与证据（D069 最小相关、未跑全量、未启动设备/OCR，均 `--timeout-s 120` 顺序执行）**：
  - 全 9 个目标 `.py` `py_compile` 与目标文件 `git diff --check` 均返回 0；
  - `tests.test_chess_prep_arrange`（**22/22 通过**，`Ran 22 tests in 2.161s`/守护 `6.2s`，峰值 472 MiB，`log/test_runs/related_20261126_230024_2060.log`，0 skipped；含 `oas2_1795693995123` / `oas2_1795694489054` 真实两帧 PNG 静态离线解码回放）；
  - `tests.test_chess_runtime_absorb tests.test_chess_frame.BoardScanTest`（**50/50 通过**，`Ran 50 tests in 11.646s`/守护 `15.5s`，峰值 505 MiB，`log/test_runs/related_20261126_230039_23048.log`，0 skipped）；
  - `tests.test_chess_frame.PreparationOrderAndBlockingGoldfishTest`（**10/10 通过**，`Ran 10 tests in 39.930s`/守护 `43.8s`，峰值 539 MiB，`log/test_runs/related_20261126_230107_11744.log`，0 skipped）；
  - `tests.test_chess_frame.DirectDeployResilienceTest`（**20/20 通过**，`Ran 20 tests in 50.253s`/守护 `54.4s`，峰值 536 MiB，`log/test_runs/related_20261126_230203_2444.log`，0 skipped）；
  - `tests.test_chess_frame.EquipmentAndHandCleanupTest`（**8/8 通过**，`Ran 8 tests in 109.887s`/守护 `113.5s`，峰值 514 MiB，`log/test_runs/related_20261126_224102_29996.log`，0 skipped；运行于末尾 1 行 `_candidate_deploy_eligibility_exclusions` 放行告警修正前，且已核实该 8 项不涉及该入口）。真实动画与连续对局节奏仍待 `oas2` Level C 实测。

## 2026-11-26 — 福利道馆放弃后战绩弹窗主动清屏与「再战道馆」消失确认（DOKAN-REMATCH-DISAPPEAR-01）

- **现场排查（`oas2` 第一馆放弃后未再战）**：
  - 核查 `log/2026-11-26_oas2.txt`（L13395–13408）：`21:02:00.092` 点 `DOKAN_ABANDONED_TOPPA`、`21:02:01.096` 点 `ABANDONED_TOPPA_ENSURE`、`21:02:02.462` 仅点一次 `RES_RYOU_DOKAN_FAILED_VOTE_BATTLE_AGAIN` 后直接记 `rematch click sent` 并退出，未见 `rank mask close clicked`，游戏实际停留在 `保留0 | 再战0`。
  - 经生产 `cv2.TM_CCOEFF_NORMED` 实测用户提供的 3 张原图：无弹窗态（`保留0 | 再战0`）上 `I_RYOU_DOKAN_FAILED_VOTE_BATTLE_AGAIN` 得 `0.9688`（`(1161,245,104,73)`）、`I_RYOU_DOKAN_TOPPA_RANK` `0.1419`；「击败排名 / 攻破进度 99%」弹窗上左框边界在 `x≈1130`，既无法触发 `I_RYOU_DOKAN_TOPPA_RANK`（`0.1531`、全图最大 `0.3103`），又把半暗的「再战道馆」（`0.9570`）露在框外，导致按旧 D060 口径仅点击一次被弹窗吃掉、未重试也未消掉按钮就退出；另在「失败 / 突破排名」弹窗上 `I_RYOU_DOKAN_TOPPA_RANK=0.9761`、`再战=0.2487`。
  - 区域安全性核对：`GameUiAssets.C_RANDOM_RIGHT` `(1100,158,140,437)` 上缘覆盖 `y=160..342` 投票面板，会误点「保留赏金」/「再战道馆」；既有 `DokanAssets.C_DOKAN_TOPPA_RANK_CLOSE_AREA` `(1150,380,100,150)` 位于投票区正下方安全空白处，故选用它关闭战绩弹窗。
- **基线与约束**（基线 `C:\Users\cbz19\.gemini\antigravity\brain\4b092f9d-10c8-4d17-87ea-3a20ad68eed1\scratch\oas-dokan-rematch-disappear-20261126\baseline` (`cbba5986ed23e62af3d16ee303a3e9ad1036c389`)；仅改 `tasks/Dokan/welfare.py` 与 `tests/test_dokan_welfare.py`，保留 `welfare.py:165` 预存 WIP `PREPARE_CLOSE_BUFFER_SECONDS=1.85`、不动 `script_task.py`、`module/*`、资产/JSON 及 `docs/CURRENT.md`）：
  - `tasks/Dokan/welfare.py`：新增 `ABANDON_POPUP_WAIT_SECONDS = 1.5`、`VOTE_MAX_CLICKS = 3`、`VOTE_CLICK_TRIES = 3`、`VOTE_DISAPPEAR_TIMEOUT = 3.0`、`VOTE_GONE_FRAMES = 2`（保留 `RANK_CLOSE_TIMEOUT=10.0`、`RANK_CLOSE_CLICK_LIMIT=4`、`RANK_GONE_FRAMES=2`、`VOTE_MASK_ROUNDS=3`）；`_abandon()` 在确认放弃消失后先 `_wait(1.5)` 并调用 `_clear_rank_mask(dismiss_once=True)`（必发一次 `C_DOKAN_TOPPA_RANK_CLOSE_AREA` 再连续 `RANK_GONE_FRAMES=2` 帧无 `RANK`）；新增 `_wait_vote_disappear(*, initial_gone=0)`；`_vote_again()` 发出点击后在 `3.0s` 内等待 `I_RYOU_DOKAN_FAILED_VOTE_BATTLE_AGAIN` 连续 2 帧消失（且未出现 `I_RYOU_DOKAN_TOPPA_RANK`）才调用 `_start_again_timer(started_at=last_clicked_at)` 建立唯一 `120s` 计时并继续回庭院/第二馆，仍可见或遇未识别弹窗吃点击时有界重试至多 `3` 次（遇可识别排名弹窗先 `_clear_rank_mask()`），耗尽转人工且不计时。
  - `tests/test_dokan_welfare.py`：适配 `World.visible()` 为点击后经过 `vote_change_delay` 再隐藏再战标识，更新 `RankMaskVoteTest` / `AgainWaitGuardTest` / `FlowTest` 以覆盖「主动右空白清 1 秒战绩弹窗」「确认按钮连续 2 帧消失再启动 120s」「不可识别延迟弹窗吃掉第 1 击后补点第 2 次成功」「3 次后仍不消失转人工且不启动 120s」。
- **验证与证据（D069 最小相关，未跑全量、未启动模拟器/OCR）**：
  - `py_compile`（`tasks/Dokan/welfare.py`、`tests/test_dokan_welfare.py`）通过。
  - `tests.test_dokan_normal_mode`：**26/26 通过**（`log/test_runs/related_20261126_214028_31108.log`）；同日志中 `tests.test_l2_c0_registry` 经 `dev_tools.click_callsite_register` diff 核对确认 `Dokan` 51 点分类与规范化行 **0 变更**，失败 4 项均源于工作区其他模块预存 WIP（`SixRealms +10`、`Chess +1`、`MetaDemon +1`、`DemonRetreat +1`、`XinLan +1` 合计 `1160 != 1146`、`policy_sites 105 != 104`）。
  - 最终编辑后定向守护（`log/test_runs/related_20261126_214449_4916.log`，14.2s / 486 MiB，`11` 类共 `123` 项）：`RankMaskVoteTest`、`AutoHomeReturnTest`、`RematchReturnTest`、`CourtyardReturnTest`、`AgainWaitGuardTest`、`SecondDokanCountRecheckTest`、`ActiveTimeTest`、`StopAndErrorTest`、`MatchContractTest`、`RematchDeadlineTest` 及再战/主流程相关 `FlowTest` 共 **122/123 通过**；唯一失败 `FlowTest.test_prepare_click_is_followed_by_the_buffer_and_then_app_stop` 为既有 WIP `PREPARE_CLOSE_BUFFER_SECONDS = 1.85 != 1.3`（基线 `welfare.py:159` 已是 `1.85`）。真机两馆表现待重启 OAS 后 Level C 实测。

## 2026-11-26 — 六道准备页跨副本分类隔离修复（PK-PREPARE-ISOLATION-01）

- **事故排查（`oas1` 19:44~19:46 无限卡死重启 & `I_PK_STORE_STILLIN` 实盘核对）**：
  - 核查 `log/2026-11-26_oas1.txt`：L20234（`17:24:00.414`）已实盘命中新版 `PK_PK_STORE_STILLIN`（`(734, 436)`），`16:37~19:44` 连续运行约 3 小时零 `PK_PK_LAND_STORE` 报错，证明 `PK-STILLIN-GIVEUP-01` 工作正常。
  - `19:44~19:46` 新发死循环（`log/error/oas1_1795693526144/`，`GameTooManyClickError: UI_UI_BACK_BLUE`）源于六道模块既有隐患（`53eb7455` 2026-05-16 / `4ce4de4f` 2026-05-18 遗留，此前 `log/2026-11-19_oas2.txt` 亦出现过 70 行 `page_ms_prepare`）：孔雀国开局 `19:44:48.928` 单击 `MS_MFIRST_SKILL` `(337, 577)` 后仍停在初始技能三选一界面（`极道轰炸` / `铭心之仇` / `怪力乱神`），原图 `2026-11-26_19-45-26-120367.png` 上仅 `I_MFIRST_SKILL`（`0.9564`）与 `I_UI_BACK_BLUE`（`0.9255`）命中，`I_MS_CHECK_EXIT_PREPARE` 仅 `0.1796`。因 `page_ms_prepare`（先导入）与 `page_pk_prepare`（后导入）均未传 `category` 而同处 `"six_realms"`，`_detect_pages` 与 `goto_page(page_peacock_kingdom)` 均被 `page_ms_prepare` 抢先识别并走 `page_ms_prepare -> page_sr_prepare_exit` 连点返回，重启点 `PK_PK_CONTINUE` 又直接回到同一三选一界面形成死循环。
  - 用户追问「点开离开试炼后不点」同步核实：当前 16:37~19:46 日志未触发 Boss 无轰雷放弃分支（`No roaring thunder before boss battle` 为 0 次）；离线测试下午「离开试炼 / 放弃试炼 / 确认」两张截图上 `I_PK_GIVEUP=0.9800`、`I_UI_CONFIRM=0.9708`、`I_UI_CANCEL=0.9446` 均正常命中；而 `19:44~19:46` 点返回后空等 4 秒不点确认正是上述误入 `page_ms_prepare -> page_sr_prepare_exit`（旧模板「是否离开月之海？」在孔雀国截图仅 `0.1758`/`0.5018`）所致。
- **基线与约束**（基线 `C:\Users\cbz19\.gemini\antigravity\brain\e08ae3fc-79b4-4591-8180-911e4f74916d\scratch\oas-pk-prepare-isolation-20261126\baseline`；不改 `tasks/GameUi/navigator.py`、`page_sr_prepare_exit`、月之海/孔雀国以外任务及用户标注 4 份素材，不动 `tasks/Chess/*` WIP）：
  - `tasks/SixRealms/moon_sea/page.py`：`page_ms_prepare` 补 `category="moon_sea"`。
  - `tasks/SixRealms/peacock_kingdom/page.py`：`page_pk_prepare` 补 `category="peacock_kingdom"`。
  - `tasks/SixRealms/peacock_kingdom/peacock_kingdom.py` & `moon_sea/moon_sea.py`：各自新增 `_navigation_detect_categories(self, destination)` 覆写，往集合内保留 `"peacock_kingdom"` / `"moon_sea"`，保证跨分类导航（如 `goto_page(page_peacock_kingdom)` / `goto_page(page_moon_sea)`）首轮即在自身分类内识别准备页，不再回退全量扫描被另一副本抢占。
  - `tests/fixtures/six_realms/pk_prepare_first_skill_2026-11-26.png` & `tests/test_six_realms_prepare_page_isolation.py`：保留 `script_task.py` 相同导入顺序（先月之海后孔雀国），覆盖静态分类与任务推理、真实报错原图生产 `ImageRuntime` 隔离识别，以及首击 `MS_MFIRST_SKILL` 被动画吞掉时保持 `page_pk_prepare`/`page_ms_prepare` 并重试到达各自 `main` 页。
- **验证与证据（D069 最小相关，未跑全量、未启动设备/OCR）**：
  - 受保护 4 份用户素材（`assets.py`、`pk/image.json`、`pk_pk_store_stillin.png`、`pk_pk_giveup.png`）SHA-256 与基线一致；5 个改动 `.py` `py_compile` 与 `git diff --check` 通过。
  - 首轮 2 模块 31 项（`log/test_runs/related_20261126_201205_12484.log`，11.0s，峰值 472 MiB）：`tests.test_six_realms_breath_and_exit_confirm` **27/27 通过**；`tests.test_six_realms_prepare_page_isolation` 通过 2/4，另 2 项仅因测试侧覆写 `_detect_pages` 未能拦截 `GameUi._detect_pages(...)` 静态调用导致 `detected_page_names` 为空（日志显示生产代码已正确重试并到达 `page_pk_main`/`page_ms_main`）。
  - 仅修正 `tests/test_six_realms_prepare_page_isolation.py` 测试探针至 `_detect_current_page_with_fallback` / `get_current_page`（生产源码零改动）后复跑（`log/test_runs/related_20261126_201304_16804.log`）：**`Ran 4 tests in 3.888s`（守护 8.8s，峰值 456 MiB，`OK`，0 skipped）**；2 模块合并 **31/31 离线通过**，重启实例后真机效果待 Level C。

## 2026-11-26 — 百鬼棋局 Web 标注器「候选式神识别测试」入口与 `detail_name` OCR 防榜单透底修复

- **基线与约束**（基线 `C:\Users\cbz19\.gemini\antigravity\brain\4b092f9d-10c8-4d17-87ea-3a20ad68eed1\scratch\oas-chess-annotator-detail-fix-20261126\baseline`，保留全部预存 WIP 且未改 `docs/CURRENT.md` / `tasks/Chess/c/ocr.json` / `c/image.json` / `resource/c_frame.json` / `resource/card_index.json` / `assets.py`）：
- **Part 1 — Web 标注器增加「候选式神识别测试」入口**：
  - `tasks/Chess/runtime/frame_cards.py`：抽取共享角标定位、头像预处理/评分与 `0.03` 歧义判断辅助（`FRAME_PORTRAIT_AMBIGUITY_MARGIN = 0.03`、`_score_frame_portraits`、`_resolve_card_identity_detail`、`_scan_hand_card_badge_anchors`、`_build_local_card_frame`），新增 `diagnose_hand_card_candidates()` 返回逐张角标框/分、头像裁剪框与 Top3（含低于阈值）及灰度/余量明细；正常运行 `_frame_card_scan` / `_frame_card_identity` 行为不变。
  - `tasks/Chess/runtime/hand_operations.py`：抽取 `_pick_weighted_deploy_candidate()` 与 `_runtime_exclusion_reasons_for_card()`，新增 `evaluate_hand_card_deploy_candidates()` 计算配置阵容归属、`deploy_weight`、目标格、`HAND_DEPLOY_TEMPLATE_THRESHOLD`（`0.75`）/ `HAND_DEPLOY_CONFIRM_FRAMES`（`1`）筛选结果及 `runtime_snapshot` 状态判定（未提供快照时标 `"运行时排除状态未知"`）。
  - `module/server/tool.py`、`module/server/tool_router.py`、`module/server/web/annotator/static/{widget/right-window.html,widget/center-panel.html,css/right-window.css,css/center-panel.css,js/app.js}`：新增 `AnnotatorManager.get_chess_candidate_meta()`、`test_chess_candidate_cards()`、`save_chess_candidate_thresholds()` 与路由 `GET /tool/annotator/api/chess/candidates/meta`、`POST /tool/annotator/api/chess/candidates/test`、`POST /tool/annotator/api/chess/candidates/save-thresholds`；右侧栏增加 `规则编辑 | 候选式神识别测试` 模式切换、可选运行时快照模板导入、暂调阈值对比渲染与裁剪图预览，显式点击确认保存才同步写入 `c_frame.json`、`card_index.json`（`card` 摘要）、`assets.py` 与 `settings.py`。
  - **实拍图离线实测**：`oas2_1795687829313`（r9）与 `oas2_1795687591561`（r5）分别以 `0.9866` / `0.9808` 高分认出 `久次良(kujira)` 并命中目标 9 格（注入 `pending_deploys` 快照后切换至 `座敷童子`）；`oas2_1795600081627/2026-11-25_17-47-58-292523.png`（红光特效）第 6 张卡 Top1 为 `久次良 0.7542`（`< 0.8` 报 `未识别`），第 4 张卡 Top1 为 `海坊主 0.7683`，临时阈值 `0.8/0.74/0.74` 翻转两卡为可上候选且已保存配置保持原样。
- **Part 2 — `detail_name` OCR 混入玩家名排查与修复**：
  - **现场原因**：`log/2026-11-26_oas2.txt`（如 L10728–11435 出现 `['河童热记忆的碎片']`、`['河童灼热记忆的碎片']`、`['古笼火七百比丘尼']`、`['河童七百比丘尼']`、`['本真三尾狐比丘尼']`、`['白童子七百比丘尼']`、`['金鱼姬北溟有']`、`['河童北溟有']` 及 L11378 误过 `['本真三尾狐溟有']`；注：当时 `OcrLogger` 关且旧代码读错未留 crop，本轮据此新增失败有界留图，原因由同局留存截图实测证实）与 `oas2_1795684837661` / `1795682817984`（详情 `x=1000..1077, y=105..127` 白字，`x=1086..1200` 暗底透出右侧第 2 名榜单原始亮度 `38/46`，底图榜单亮度高达 `254`）、`ppocr.ocr_single_line` 拼接框内全部分行文本、首帧未判稳、点击前偶现未闭旧面板（`oas2_1795682824677/1`）及模糊匹配缺长度差守卫。
  - **源码修复**（`tasks/Chess/runtime/settings.py` + `hand_operations.py`）：新增 `SPECIFICS_DETAIL_NAME_WHITE_MIN_CHANNEL=145` 等 5 项常量；`_inspect_board_set_shikigami()` 点击前先确认关闭旧详情并共享 `3.0s` 单次点击预算调用 `_wait_specifics_detail_name_stable()`；`_prepare_specifics_detail_name_image()` 仅在 `O_DETAIL_NAME` `(996,92,204,52)` 副本上分离白字前景（`oas2_1795684837661`/`1795682817984` 右区统一压至 `28`，合成低对比用例保留原图不误清）；`_resolve_specifics_shikigami_name()` 加长度差 `abs(len(cleaned)-len(chinese_name)) <= 1` 拒绝拼接脏串；`_save_specifics_evidence_bundle()` / `_record_detail_name_failure_evidence()` 复用每局最多 2 组留存失败诊断。参考坐标建议 `(996,100,162,32)`（保留原配置未改）。
- **验证（D069 定向最小，未跑全量、未启动设备/OCR）**：
  - 受保护文件 SHA-256 与开始基线一致；`py_compile`（6 改动 `.py`）与 `node --check module/server/web/annotator/static/js/app.js` 通过。
  - 新增 `tests/test_chess_annotator_and_detail_name.py` 并在守护下运行 3 组测试全部通过：`log/test_runs/related_20261126_185255_31420.log`（`ShippedDataConsistencyTest` 7、`RuntimeProtocolTest` 6、`CardScanTest` 8、`ArakawaDirectDeployTest` 10，**31/31**，`31.313s`）、`log/test_runs/related_20261126_185344_25404.log`（`PreparationOrderAndBlockingGoldfishTest` 10、`DirectDeployResilienceTest` 20，**30/30**，`71.385s`）、`log/test_runs/related_20261126_190455_31516.log`（`ChessAnnotatorCandidateTest` 4、`ChessDetailNameStabilityAndIsolationTest` 4，**8/8**，`2.512s`），合并 **69/69 通过**（0 skipped）；`oas2` 真机稳态读名与红光阈值调整待 Level C。

## 2026-11-26 — 百鬼棋局式神详情名称 OCR 改用 `detail_name`

- **资产与基线核对**（基线 `C:\Users\cbz19\.gemini\antigravity\brain\4b092f9d-10c8-4d17-87ea-3a20ad68eed1\scratch\oas-chess-detail-name-ocr-20261126\baseline`，不改 `CURRENT.md` / `ocr.json` / `image.json` / `assets.py` / 公共核心）：
  - 核对 `tasks/Chess/c/ocr.json` 与 `tasks/Chess/assets.py`：`detail_name` / `O_DETAIL_NAME` 为 `roi=(996,92,204,52)`、`mode="Single"`、`method="Default"`；`name_range` / `O_NAME_RANGE` 保持原配置 `(933,41,319,205)`、`mode="Full"` 不变；`tasks/Chess/c/image.json` 中 `shikigami_specifics` / `I_SHIKIGAMI_SPECIFICS`（`roi_front=(933,246,319,36)`、`roi_back=(918,172,344,157)`）及模板 `tasks/Chess/c/c_shikigami_specifics.png`（`36×319`）与 `assets.py` 完全一致。
- **实际改动**：
  - `tasks/Chess/runtime/settings.py`：新增 `SPECIFICS_DETAIL_NAME_MAX_READS = 3`，约束详情打开后的 `O_DETAIL_NAME` 初读与预算内复读总次数。
  - `tasks/Chess/runtime/hand_operations.py`：
    - `_read_specifics_shikigami_identity()` 保留 `I_CHECK_GOLDFISH` 判断，普通式神名字改为直接调用 `self.O_DETAIL_NAME.ocr(self.device.image)` 并沿用 `_normalize_ocr_text` 与 `_resolve_specifics_shikigami_name()`，停止调用 `O_NAME_RANGE`、y 坐标过滤（`max_y`）及扩大面板范围，局部移除无调用者的 `_specifics_header_ocr_rule()` 与 `_extract_specifics_header_texts()`；
    - `_inspect_board_set_shikigami()` 在单次点击确认预算（`ACTION_ICON_WAIT_TIMEOUT = 3.0s`）内将 `deadline` 传入 `_read_specifics_shikigami_identity()`；初次读空或未解析时仅在准备+关店+未超时且 `I_SHIKIGAMI_SPECIFICS` 仍可见下新截图复读同一 `detail_name` 小框；日志明确记录 `rule=detail_name`、`roi`、原始文字与解析结果，成功交调用方登记实际站位与解除 pending、失败按既有单张暂缓与配额推进。
  - `tests/test_chess_frame.py`：在 `ShippedDataConsistencyTest` 新增 JSON/资产一致断言（含 `name_range` 与 `shikigami_specifics`），将 `ArakawaDirectDeployTest` / `LineupCapacityStatusTest` / `PreparationOrderAndBlockingGoldfishTest` / `DirectDeployResilienceTest` 的详情替身迁至 `DETAIL_NAME`（并禁止 `detect_and_ocr` 误回旧宽框），重写 `test_specifics_detail_name_ocr_crop_and_budgeted_reread`（验证真实 `RuleOcr.ocr` 仅裁 `(52,204,3)` 且忽略外部干扰、时间/次数预算）并在 `DirectDeployResilienceTest` 新增「复读解除 pending 并触发真实御魂分配」「读名失败不重复点详情不误记且继续其他牌/找金鱼/队友装备」2 项回归。
- **验证与证据（D069 定向最小，未跑全量、未启动模拟器/游戏/OCR）**：
  - `py_compile`（`settings.py`、`hand_operations.py`、`assets.py`、`tests/test_chess_frame.py`）与受保护 4 文件 SHA-256 校验通过。
  - 第一组 4 类 29 项（`log/test_runs/related_20261126_174859_14308.log`，34.5s，峰值 529 MiB）：`ShippedDataConsistencyTest` (7)、`ArakawaGoldfishTriggerTest` (6)、`LineupCapacityStatusTest` (6) 全过，`ArakawaDirectDeployTest` (10) 中 `test_specifics_detail_name_ocr_crop_and_budgeted_reread` 因新测试误禁用 `Single.ocr_single` 内部 `detect_and_ocr` 兜底失败；仅修正该测试桩后复跑（`log/test_runs/related_20261126_175013_15072.log`，`Ran 1 test in 0.209s` / 守护 5.0s，**`OK`**）。
  - 第二组 2 类 30 项（`log/test_runs/related_20261126_175018_24476.log`，90.2s，峰值 534 MiB）：`PreparationOrderAndBlockingGoldfishTest` (10) 与 `DirectDeployResilienceTest` (20) 通过 29/30，仅 `test_detail_name_unreadable_defers_single_card_keeps_goldfish_deploy_and_other_equip` 因新增 `suzuka_gozen` 置 2 号位排在 3 号 `shouzu` 之前消耗火灵而失败；调整测试夹具至 4 号位后复跑（`log/test_runs/related_20261126_175221_25124.log`，`Ran 1 test in 5.089s` / 守护 9.2s，峰值 480 MiB，**`OK`**）。6 类合并 **59/59 离线通过**（0 skipped），`oas2` 实测链路仍待 Level C。

## 2026-11-26 — 六道孔雀国觉：万相铃不足进宁息验证与 Boss 无轰雷放弃试炼接入

- **现场排查（`oas1` 连续三日同款卡死）**：
  - 核查 `log/error/oas1_1795522906364/`（11-24 20:21）、`oas1_1795594020130/`（11-25 16:07）与 `oas1_1795678376999/`（11-26 15:32）：均在买完轰雷剩 `300` 万相铃后立即触发唤息跳回合扣至 `0`，下一帧点击 `PK_PK_LAND_STORE` 弹出「大人的万相铃不足，是否仍要进入宁息之屿?」，因旧 `I_PK_STORE_STILLIN` 模板在 2026-10-10 新版「进入」按钮上固定 ROI 仅匹配 `0.0275`（即使放宽 `roi_back` 亦仅 `0.6988`），`run_on_pk_main()` 无法接管而继续连点背景上的宁息旗帜触发 `GameTooManyClickError: PK_PK_LAND_STORE`。
  - 用户已完成 `I_PK_STORE_STILLIN`（`(670,413,166,51)`/`(657,398,191,82)`）与 `I_PK_GIVEUP`（`(715,323,47,46)`）标注；经生产 `ImageRuntime` 实测，重标后的 `I_PK_STORE_STILLIN` 在 3 天现场原图全部 `1.0000` 命中，且在 `pk_breath_dialog_2026-10-12.png`（`0.6032`）与 `pk_exit_dialog_2026-10-12.png`（`0.5719`）上保持低于 `0.8` 阈值，现有 `run_on_pk_main()` -> `run_on_pk_store_confirm()` 链路无需改业务代码。
- **基线与隔离边界**：开始前在 `C:\Users\cbz19\.gemini\antigravity\brain\e08ae3fc-79b4-4591-8180-911e4f74916d\scratch\oas-pk-stillin-giveup-20261126\baseline` 保存 7 个待涉及文件起点副本并记录用户 4 个素材文件 SHA-256；源码改动严格限定在 `tasks/SixRealms/peacock_kingdom/base_peacock_kingdom.py` 与 `peacock_kingdom.py`，未改用户素材、`peacock_kingdom/page.py`、月之海、`GeneralBattle` 及公共核心。
- **实际改动**：
  - `tasks/SixRealms/peacock_kingdom/base_peacock_kingdom.py`：
    - 新增 `thunder_state_known: bool = False` 与 `_boss_giveup_requested: bool = False`（均在 `before_run()` 重置 `False`；不改动全局 `pages.page_battle_result.recognizer`）。
    - `_handle_in_battle()` 清零 `_boss_giveup_requested`，在非 Boss 战或识别到 `I_PK_BATTLE_THUNDER` 时置 `thunder_state_known = True`。
    - 新增局部 `_confirm_boss_giveup_dialog()` 与 `_handle_missing_battle_page()` 覆盖，并在 `_handle_result()` 点击 `I_BOSS_BATTLE_GIVEUP` 时置 `_boss_giveup_requested = True`、`_handle_reward()` 清零，使战败放弃在保留旧 `I_UI_CONFIRM_SAMLL` 的同时兼容新版公共确认弹窗（`I_UI_CONFIRM` + `I_UI_CANCEL` 且排除 `I_MS_CHECK_OPEN_STORE`）。
  - `tasks/SixRealms/peacock_kingdom/peacock_kingdom.py`：
    - `run_on_pk()` 点击 `I_PK_START`（不含 `I_PK_CONTINUE`）与新方法 `_enter_pk_main_from_prepare()`（替换 `pk_page_handle_dict` 中 `page_pk_prepare` 入口）置 `thunder_state_known = True`，防止中途续打未经战斗检查在 Boss 界面误放弃。
    - 新增 `GIVEUP_TIMEOUT = 30.0`、`_should_give_up_boss()` 与有界闭环 `_give_up_trial()`；`run_on_pk_main()` 命中 `I_PK_BOSS_PREPARE` 且确认无轰雷时走 `I_UI_BACK_BLUE` → `I_PK_GIVEUP` → 单次 `I_UI_CONFIRM`（等确认离开主界面后再于结算期取消双倍并点击奖励）直到回到 `page_peacock_kingdom` 并 `raise TaskEnd`（计 1 次）。保留 `page_pk_exit -> page_peacock_kingdom` 暂离边及默认关闭行为不动。
  - `tests/fixtures/six_realms/pk_store_stillin_dialog_2026-11-26.png`、`tests/test_six_realms_breath_and_exit_confirm.py`：复制 11-26 无损现场图作夹具，保留全部 13 项旧用例并新增 `StoreStillInDialogTest`（2）、`BossGiveUpWithoutThunderTest`（9）与 `BossDefeatGiveUpConfirmTest`（3）共 14 项用例（模块总计 27 项）。
- **验证与证据（D069 定向最小，未跑全量、未启动设备/OCR）**：
  - 3 改动文件 `py_compile`、`git diff --check` 与 4 份受保护素材 SHA-256 校验全部通过。
  - 首轮 3 模块 72 项守护测试（`log/test_runs/related_20261126_163503_16624.log`）：`test_six_realms_buy_verify`（28）与 `test_six_realms_thunder_cost_verify`（17）共 45/45 通过；`test_six_realms_breath_and_exit_confirm` 新增测试因 `device` 缺 `click_record_clear` 桩、`BREATH_DIALOG` 缺少 `page_map` 与 `assertNotIn('I_UI_CONFIRM')` 子串误命中 `I_UI_CONFIRM_SAMLL` 出现 2 失败 1 错误。
  - 仅修正这 3 处测试桩/断言（生产源码零改动）后复跑 `tests.test_six_realms_breath_and_exit_confirm`（`log/test_runs/related_20261126_163558_200.log`）：**`Ran 27 tests in 2.138s`（守护 5.5s，峰值 457 MiB，`OK`，0 skipped）**；3 模块合并 **72/72 离线通过**，重启 OAS 后真机 Level C 待验。

## 2026-11-26 — 百鬼棋局买卡后补上卡调用顺序补丁（新卡 -> 找金鱼 -> 旧 pending）

- **问题定位**：`tasks/Chess/script_task.py::_redeploy_after_preparation_economy_purchase()` 调用 `deploy_shikigami_from_hand(run_regular_goldfish=False)` 时未传 `reconcile_pending=False`，导致经济买卡后可能先点旧 pending 详情，再进 `_run_preparation_regular_goldfish_once(context='preparation_post_buy_deploy')`；若本轮依赖该批买卡首次激活二荒川，旧 pending 会抢先消耗详情时间。
- **基线与改动**（基线 `C:\Users\cbz19\.gemini\antigravity\brain\4b092f9d-10c8-4d17-87ea-3a20ad68eed1\scratch\oas-chess-post-buy-reconcile-order-20261126\baseline`，不改 `CURRENT.md`/公共核心/素材/配置）：
  - `tasks/Chess/script_task.py`：`_redeploy_after_preparation_economy_purchase()` 传 `reconcile_pending=False`；保留准备/关店/上卡或待查判定与 `preparation_post_buy_deploy` 找鱼机会后，仍在准备且关店时再调用 `_reconcile_pending_deploys_once()`（沿用全轮 `<= 1`、`remaining >= 6s` 且可读与轮转规则；找鱼因未激活、已执行或已放好跳过时旧 pending 仍获机会）。
  - `tests/test_chess_frame.py`：在 `DirectDeployResilienceTest` 新增 `test_post_buy_redeploy_runs_goldfish_before_pending_reconcile_and_keeps_round_budget`，覆盖初始荒川 `<2` 未耗找鱼/配额 → 买金鱼姬激活二荒川 → `新卡上阵 -> 找鱼 -> 旧 pending` 顺序、找鱼后余时 `<6s` 或切战不点旧 pending、已放好跳过仍核实及全轮单一配额复用。
- **验证与证据（D069 定向最小，未跑全量、未启动设备）**：
  - 2 改动文件 `py_compile` 与 `git diff --check` 退出码 `0`。
  - 直接相关 3 类 39 项守护（`log/test_runs/related_20261126_163210_14544.log`，54.774s/守护 58.8s）：`PreparationOrderAndBlockingGoldfishTest`(10) 与 `StateLoopTest`(11) 共 **21/21 通过**，`DirectDeployResilienceTest`(18) 中 17 通过、新增用例因 8 号金鱼未在上卡回调刷出而失败 1 项；仅修正该测试夹具并复跑 `DirectDeployResilienceTest`（`log/test_runs/related_20261126_163406_20584.log`，`Ran 18 tests in 30.696s` / 守护 34.7s，峰值 512 MiB，**`OK`**）。直接相关 3 类合并 **39/39 通过**，`oas2` 实盘待 Level C。

## 2026-11-26 — 百鬼棋局跨回合待核实记录后置调度、全轮单一上限与公平轮转修复

- **问题根因**：前序 `CHESS-PREP-DIRECT-DEPLOY-01` 中 `deploy_shikigami_from_hand(direct_only=False)` 入口前置遍历全部 `_pending_deploys`，积累多条已消耗/疑似合卡旧记录时仍会先连续点多次详情挤占新候选与常规找鱼时机、`remaining_time=None` 未拦截主动点详情、`once` 未约束同一准备回合多个入口总次数，且仅按 `dict` 插入顺序从第一条开始尝试可能导致后续可核实记录长期饥饿。
- **基线与修改范围**：在 `C:\Users\cbz19\.gemini\antigravity\brain\4b092f9d-10c8-4d17-87ea-3a20ad68eed1\scratch\oas-chess-pending-reconcile-fix-20261126\baseline` 保存 8 个待涉文件起点快照；严守不改 `economy.py`、`frame_cards.py`、`assets.py`、素材/ROI、`module/*` 与用户配置，且不改动 `docs/CURRENT.md`（仅在交付中给出建议检查点）。
- **实际改动**：
  - `tasks/Chess/runtime/settings.py`：新增 `PENDING_DEPLOY_MAX_INSPECTS_PER_ROUND = 1` 与 `PENDING_DEPLOY_RECONCILE_MIN_REMAINING = GOLDFISH_SINGLE_INSPECT_MIN_REMAINING + 2`（`6s`：实测单次详情 `3.5~3.61s` / 含 `3.0s` 等待 + `2s` 后续收尾与御魂缓冲）。
  - `tasks/Chess/runtime/hand_operations.py`：
    - `_ensure_prep_goldfish_round_state()` 新增 `pending_reconcile_clicks_used = 0` 实现全准备回合共享上限（随回合号切换及 `_start_chess_game()` 自动重置）；`_inspect_board_set_shikigami()` 增加 `clicked` 内部标记精确区分点击前中止与实际发出点击；
    - 新增 `_cleanup_nonblocking_pending_deploys()`（零点击清理已确认上阵及上轮未消耗/无升星线索记录）、`_has_reconcilable_pending_deploys()` 与 `_select_pending_probe_slot()`（带 `GameStuckError` 防护）；
    - 重写 `_reconcile_pending_deploys_once()`：先零点击清理，再校验全轮配额（`< 1`）与准备/关店/`remaining is not None and >= 6s` 门槛；跳过当前无合法核实格者（不消耗唯一配额），在有合法格者中按 `(last_attempt_round, insert_idx)` 最久未尝试轮转选中唯一目标，真实发出点击后计 `pending_reconcile_clicks_used += 1`，成功按 `probe_slot` 实占登记并清除，失败/不可读/他卡更新 `last_attempt_round` 并保留记录与同名防重保护；
    - `deploy_shikigami_from_hand(..., reconcile_pending: bool = True)` 改为入口零点击清理 -> 本轮可用新候选卡全部尝试 ->（若 `run_regular_goldfish=True`）常规找金鱼 ->（若 `reconcile_pending=True` 且无全局中断）后置单次核实旧 pending。
  - `tasks/Chess/script_task.py`：`_handle_preparation()` 先让新候选及未触发过的常规找鱼机会执行，再调用 `_reconcile_pending_deploys_once(round_state)` 并在最后穿戴御魂（使初始、经济买卡后与收尾入口严格共用整轮 1 次配额）。
  - `tests/test_chess_frame.py`：在 `DirectDeployResilienceTest` 新增 6 项完整验收回归（3 条 pending+新卡+找金鱼顺序、初始/经济/收尾全轮共享 1 次配额与免费清理、跨多轮公平轮转、`None`/`5s`/`6s` 时间门控、无合法核实格不耗配额、结果登记/保护与新局重置）。
- **验证与证据（D069 定向最小，未跑全量、未启动设备/游戏/OCR）**：
  - 首轮编译、`git diff --check` 与 7 类共 **76 项**守护测试（`log/test_runs/related_20261126_154329_5148.log`，91.118s/守护 95.0s，峰值 545 MiB）：`BoardScanTest`(16)、`ArakawaDirectDeployTest`(10)、`ArakawaGoldfishTriggerTest`(6)、`LineupCapacityStatusTest`(6)、`PreparationOrderAndBlockingGoldfishTest`(10)、`StateLoopTest`(11) 共 **59/59 通过**，仅 `DirectDeployResilienceTest` 新增测试有 2 处测试夹具设错（金鱼优先扫描占用 7 号格及经济买卡 mock 漏 `arakawa_no_nushi` 分支）。
  - 仅修复这 2 处测试夹具（生产代码零改动）后复跑 `DirectDeployResilienceTest`（`log/test_runs/related_20261126_154549_6452.log`，`Ran 17 tests in 25.019s`，守护 28.4s，峰值 508 MiB，**`OK`**），`py_compile` 与 `git diff --check` 全通过；7 类合并 **76/76 通过**，实盘仍待 `oas2` Level C 验证。

## 2026-11-26 — 百鬼棋局准备阶段直接先上卡、单次详情上限与单张暂缓（CHESS-PREP-DIRECT-DEPLOY-01）

- **问题根因**：`oas2` 准备阶段多次出现目标格先查详情或拖后连续 3 次点详情全败（`specifics_not_opened`），导致待上阵式神长期滞留候选区并 `break` 整段上卡，拖延后续式神部署、提前找金鱼与御魂装备。
- **基线与修改范围**：任务基线保存于 `C:\Users\cbz19\.gemini\antigravity\brain\4b092f9d-10c8-4d17-87ea-3a20ad68eed1\scratch\oas-chess-prep-direct-deploy-20261126\baseline`（`master` @ `cbba5986ed23e62af3d16ee303a3e9ad1036c389`，含 169 项工作区预存状态指纹），严格未改 `economy.py`、`frame_cards.py`、`assets.py`、素材/ROI JSON、`module/*` 与用户配置。
- **实际改动**：
  - `tasks/Chess/runtime/state.py`、`state_loop.py`、`script_task.py`：`ChessGameState` 新增 `pending_deploys` 字段及 `_GAME_STATE_FIELDS` 代理映射；`_start_chess_game()` 新增清理 `_pending_deploys`、`_pending_arakawa_deploy`、`_specifics_evidence_saved_slots` 与 `_specifics_evidence_save_count`。
  - `tasks/Chess/runtime/hand_operations.py`：
    - 统一荒川与非荒川阵容式神直拖逻辑 `_deploy_lineup_hand_card_direct()`（`_deploy_arakawa_hand_card_direct()` 保持兼容委托），默认 `_inspect_board_set_shikigami(..., max_attempts=None)` 收敛为最多点 `1` 次；
    - 落地确认项 1：空位变占、手牌消耗且无冲突/升星/邻格腾空时 0 点击登记确认；否则最多单点并区分四类状态；
    - 落地确认项 2 方案 B（`_handle_known_goldfish_before_direct_deploy()`）：已确认站定配置位的金鱼在拖前硬保护 0 拖拽；已确认错位金鱼优先搬移后重扫再拖（0 点详情），阻塞或失败只暂缓当前式神；
    - `deploy_shikigami_from_hand()` 允许 `capacity=None` 直拖与先搬错位金鱼，仅禁止系统卡回收；确认 `not_full` 且目标空时跳过旁侧回收；对 `_set_position` 的 `GameStuckError` 与非准备/开店走全局 `break`，其余局部失败记入 `_pending_deploys`（并记录 `newly_occupied_slots`）仅暂缓该式神、同轮去重并继续后续式神与准备工作；
    - `_reconcile_pending_deploys_once()` 跨回合在 `direct_only=True` 直接清除上轮未消耗待核实记录、对已消耗/疑似合卡升星记录在余时充足时优先对唯一新增占格或目标格单点详情归位；
    - `_diagnose_and_save_specifics_failure()` 捕获点击前后帧右半区像素变化（`SPECIFICS_PANEL_ROI`）与扩大区域模板分（`SPECIFICS_EXPANDED_SEARCH_ROI`）记 `WARNING`，并在 `save_error=True` 时每局最多留存 2 组对比图与 `log.txt`（同格去重）。
  - `tests/test_chess_runtime_absorb.py`、`tests/test_chess_frame.py`：更新 `GameStateTest`/`StateLoopTest`/`BoardScanTest`/`ArakawaDirectDeployTest`/`ArakawaGoldfishTriggerTest`/`LineupCapacityStatusTest`/`PreparationOrderAndBlockingGoldfishTest`，并新增 `DirectDeployResilienceTest`（11 项覆盖 6 条验收场景、两项确认规则边界、`O_LEVEL=None` 与锚点丢失保护、详情诊断日志与有界留存、旧单卡兼容入口）。
- **验证与证据（D069 定向最小，未跑全量、未启动模拟器/游戏/OCR）**：
  - 全部 6 个修改 `.py` 文件 `py_compile` 与 `git diff --check` 退出码 `0`。
  - 定向守护单元测试（`--timeout-s 120`）：
    - `log/test_runs/related_20261126_152424_29968.log`（73 项，82.939s）：`ArakawaDirectDeployTest`(10)、`ArakawaGoldfishTriggerTest`(6)、`PreparationOrderAndBlockingGoldfishTest`(10)、`GameStateTest`(3)、`StateLoopTest`(11) 合计 **40/40 通过**（生产代码及此 5 类此后未改）；
    - 修复测试夹具与补充 `not_full`/兼容断言后 `log/test_runs/related_20261126_152909_9628.log`（33 项，32.066s）：`DirectDeployResilienceTest` **11/11 通过**（此类此后未改）；
    - 修复最后 2 处测试夹具后复跑 `log/test_runs/related_20261126_153023_24120.log`（`Ran 22 tests in 14.850s`，`OK`）：`BoardScanTest`(16) + `LineupCapacityStatusTest`(6) **22/22 通过**。8 个目标测试类合并 **73/73 通过**（0 skipped）。
- **真机待验与后续独立项**：真机实测项及「多卡合成落入原本已占非新增格的全盘 12 格跨位纠位」「采集事故图后标定 `I_SHIKIGAMI_SPECIFICS` 模板/ROI」均记入 `docs/ROADMAP.md`。

## 2026-11-26 — 福利道馆观察层允许有界原地局部徽记动画（DOKAN-SETTLE-OBSERVE-LOCAL-01）

- **现场排查（`log/error/oas2_1795671508493/` & `log/2026-11-26_oas2.txt`）**：
  - `oas2` 今日实跑中已验证 `DOKAN-REFRESH-REBOUND-01` 的前 3 轮连续刷新均顺利释放 `dokan_refresh`、`RES_RYOU_DOKAN_REFRESH_ENSURE` 与 `dokan_welfare_list_up` 记录（L5948–5955，第 4 批后续轮次与 `>= 6` 轮及过冲回弹仍待续测）。
  - 第 3 次刷新后第 4 滑在 `13:38:29` 转人工报「滑动列表后画面一直在变化、没有稳定下来」。逐像素核对 4 张现场诊断图与 `log.txt`：① 滑动本身有效推进 `+261px`（`before_y=556 -> after_y=295`、`score=0.951`），且第 4 轮首尾两帧（`welfare_list_2_round_anchor.png` 与 `welfare_list_3_round_final.png`）位移 `0px`、`score=1.000`，列表完全静止；② 变化像素掩码集中在右侧 3 枚同时出现的「紫色弯月」动态寮徽记星光点（`灵壹` / `一梦千年` / `春夏秋冬`，`x=1135..1190`），相邻帧局部变化率持续处于 `0.010–0.017`（变化行占比 `0.10`）；③ 此前第二层 `_hold_failure` 已能经 `list_change_kind` 放过 `local`（近三日实跑已正常放过 38 次 `0.010–0.020` 局部动画），但第一层 `_observe_list` 仍调用公共 `wait_for_changed_and_stable` 的裸 `0.01`（`LIST_STABLE_THRESHOLD`）像素线，导致连拒 4 轮共 36 帧（`10.5s`）未能进入第二层确认。
- **基线与隔离边界**：按用户批准方案，开始前在 `C:\Users\cbz19\.gemini\antigravity\brain\4b092f9d-10c8-4d17-87ea-3a20ad68eed1\scratch\oas-dokan-settle-observe-local-20261126\baseline` 保存 7 个待改文件快照与 4 张现场只读原图 sha256；严守不动公共 `module/base/frame_wait.py`、`module/atom/frame_state.py`、`module/device/device.py`、普通道馆、`list_change_kind` 既有阈值与 `welfare.py` L680 `if count <= 0: return 0`。
- **实际改动**（仅 `tasks/Dokan/welfare.py` 与 `tests/test_dokan_welfare.py`）：
  - `tasks/Dokan/welfare.py`：
    - 新增 `OBSERVE_STABLE_FRAMES = 2`、`OBSERVE_LOCAL_RATIO_MAX = 0.05`、`OBSERVE_LOCAL_ROWS_MAX = 0.35`、`OBSERVE_MAX_POLLS = 1_000_000` 与纯函数 `_is_observe_local_stable(info)`。
    - 改写 `WelfareDokan._observe_list()`（保持返回 `FrameWaitResult` 契约，每次截新帧做独立拷贝 `np.array(task.device.image)`）：相邻帧经 `list_change_kind(prev, curr)` 判定，`ratio <= LIST_STABLE_THRESHOLD` 直接走快速路径计稳；超过 `0.01` 时仅 `_is_observe_local_stable()` 成立才累计安静计数并记入 `self._observe_locals`，而 `shifted`、`wide` 或超界 `local` 一律清零 `stable_count`；仍由后续 `_hold_failure` 与 `list_progress` 双重守卫。
    - 新增 `WelfareDokan._observe_note()` 接入 `_settle_list()` 成功日志（`ignored local change in observe`），同步更新 `_settle_list()` 注释与 `_save_settle_evidence()` 阈值文本。
  - `tests/test_dokan_welfare.py`：
    - 新增共用辅助函数 `moon_twinkle_boxes()` / `alternating_twinkle()`；在 `ListHoldTest` 新增 4 项回归：3/4 动态徽记每帧超 `1%` 在第一轮判稳并返回 `moved`/`static`（含公共 `wait_for_changed_and_stable` 裸 `1%` 失败对照）、`log/error/oas2_1795671508493/` 现场原图回放（含真实星光掩码增强超 `1%` 序列）、稠密/稀疏 `1px`/`3px` 滚动叠加 3 动态徽记不提前判稳、超 `0.05` 像素占比与超 `0.35` 行占比的局部噪点被拒绝且保留滑动记录。
- **离线验证与原图回放（D069，未跑全量、未启动设备/游戏）**：
  - `py_compile`（`tasks/Dokan/welfare.py`、`tests/test_dokan_welfare.py`）退出码 `0`；4 张现场原图 sha256 未变；`oas2_1795671508493` 离线回放 `list_progress(f1, f3)` 为 `moved (+261px, score=0.951)`、增强星光帧 `list_change_kind` 为 `local`（`ratio=0.0116, rows=0.105`）、`_is_observe_local_stable=True`。
  - 首轮守护 5 类 118 项（`log/test_runs/related_20261126_135515_28804.log`，76.936s/守护 81.1s，峰值 688 MiB）：`SwipeProgressTest`(20)+`ListProgressTest`(34)+`SwipeRecordTest`(17)+`SearchTest`(17) 全部通过，`ListHoldTest` 新增反向对照因使用有限迭代器而非模拟时钟失败 2 项 subTest；仅修复该测试时钟夹具并复跑 `ListHoldTest`（`log/test_runs/related_20261126_135718_28104.log`）：**`Ran 30 tests in 20.070s`（守护 25.1s，峰值 737 MiB，`OK`，0 skipped）**；合并 5 类共 118 项离线全部通过。真实同屏多动态徽记一轮判稳仍待真机（重启对应实例后）Level C 验收。

## 2026-11-25 — 百鬼棋局准备阶段金鱼时机提前与放好跳过条件调整

- **范围与基线（保留工作区预存改动）**：仅修改 `tasks/Chess/runtime/state.py`（基线 `b1188363...`）、`tasks/Chess/runtime/state_loop.py`（基线 `99d74fac...`）、`tasks/Chess/script_task.py`（基线 `0c5b887a...`）、`tasks/Chess/runtime/hand_operations.py`（基线 `e591a096...`）、`tests/test_chess_frame.py`（基线 `318a7ffa...`）、`tests/test_chess_runtime_absorb.py`（基线 `dc338a4c...`）。
- **核心改动**：
  - `ChessGameState.arakawa_goldfish_placed`（`_GAME_STATE_FIELDS` + `_start_chess_game()`）：记录本局金鱼是否已确认放好在配置位，并在新开一局重置。
  - 提前常规找鱼时点与单轮机会控制：`deploy_shikigami_from_hand(..., direct_only=True)` 在首批关店后只部署目标格已确认空位且人口允许的直上牌，并在阻塞搬鱼或未知容量多格回收前暂停（`_last_deploy_stopped_for_direct_only`）；`_run_preparation_initial_deploy_stage()` 随即触发 `_run_preparation_regular_goldfish_once(context='preparation_initial')`，之后再续行 `direct_only=False` 并于上卡后按需触发 `context='preparation_post_deploy'`。买卡补上卡（`preparation_post_buy_deploy`）及收尾阶段上卡（`preparation_tail_deploy`）/ 装备御魂后（`preparation_tail`）统一经 `_run_preparation_regular_goldfish_once()`：若二荒川未激活（`< 2`）则保留本轮机会待后续补卡或装备`荒川纹章`后补触发一次；一旦已启动（`regular_search_started=True`），同一准备阶段收尾不再重复搜索，未查完的 `search_progress` 留待下轮续查。
  - 放好完成登记与跳过条件：`_detect_pending_arakawa_goldfish()` 顶部在 `_arakawa_goldfish_placed=True` 时直接返回（零羁绊检查、零扫格、零点击、零搬运），并清理未经详情确认的旧位置记录；`_handle_blocking_target_slot_before_deploy()` 在目标格即配置位时直接登记完成；统一 `_move_arakawa_goldfish()` 的 `_check_goldfish_target_slot_usable()`（保护已站位阵容棋子）与拖后新画面确认（`source_after == 'empty'` 且 `target_after == 'occupied'`），仅详情确认在配置位或拖后新画面确认落位才调用 `_mark_arakawa_goldfish_placed()`，失败/中断/未确认保留待处理而不记完成。
- **验证与证据**：
  - `py_compile` 全部 6 个代码与测试文件通过；`git diff --check` 无空白错误。
  - 分组单测首轮（`log/test_runs/related_20261125_225747_24624.log`，82 项 / `62.071s` / guarded `66.1s` / 峰值 `538 MiB`）：`ArakawaGoldfishTriggerTest` (6)、`BoardScanTest` (16)、`ArakawaDirectDeployTest` (10)、`LineupCapacityStatusTest` (6)、`tests.test_chess_runtime_absorb` (34) 共 72 项及 `PreparationOrderAndBlockingGoldfishTest` 中 6 项通过，4 项因测试桩夹具未同步失败。
  - 仅修正 `tests/test_chess_frame.py` 测试夹具后（未改动生产源码）复跑 `PreparationOrderAndBlockingGoldfishTest`（`log/test_runs/related_20261125_230207_24612.log`）：共 10 项在 `27.898s`（guarded `31.6s` / 峰值 `506 MiB`）全部通过（`OK`，0 failed，0 skipped）。
  - 本轮未启动模拟器/游戏/OCR，新增真机回归已记入 `docs/ROADMAP.md`。

## 2026-11-25 — 福利道馆有效刷新记录释放与触底过冲回弹有界恢复（DOKAN-REFRESH-REBOUND-01）

- **现场排查（对比 2026-11-24 修复）**：
  - 核查 `log/2026-11-25_oas1.txt` 与 `log/2026-11-25_oas2.txt`：2026-11-24 新增的滑前赏金图标前置校验在今天实跑中已彻底生效——两机累计 **85 次 `moved` + 38 次 `static`**，全程 **0 次 `ambiguous`**、**0 次滑前锚点获取失败**，触底稳定停在 `y=561`。
  - 翻页跑通后暴露两项后续故障：① **第 6 次刷新必触双按钮保护**：`oas1`（21:20:59 `oas1_1795612859749`、21:24:29 `oas1_1795613069493`）与 `oas2`（21:24:04 `oas2_1795613044421`）均在第 6 次点刷新确认前因 `click_record`（maxlen=15）中 `dokan_refresh` 与 `RES_RYOU_DOKAN_REFRESH_ENSURE` 各满 6 次抛出 `GameTooManyClickError`，触发自动 `Restart` 循环重刷；② **触底过冲静滞回弹**：`oas2`（21:19:50～21:19:58，`log/error/oas2_1795612797739/`）第 4 滑后过冲停在 `y=509` 并保持静止超过 2.6 秒，第 5 滑正常上滑（行为轨迹已核实为 `(1146,459)->(1146,337)`）唤醒底部弹性约束回落至真实底位 `y=561`（`actual_dy=-52px`、`score=0.958`），被 `wrong_direction` 直接转人工。
- **基线与保护**：按用户确认方案（保留 D046 不设刷新次数上限、允许两项一起局部修复），开始前在 `C:\Users\cbz19\.gemini\antigravity\brain\4b092f9d-10c8-4d17-87ea-3a20ad68eed1\scratch\oas-dokan-refresh-rebound-20261125\baseline` 保存 `master` (`cbba5986ed23e62af3d16ee303a3e9ad1036c389`) 下 7 个待触及文件快照与只读原图指纹，完整保留公共 `Device`、普通道馆、`assets.py`、`swipe.json` 与其他 WIP。
- **实际改动**（业务/测试仅 `tasks/Dokan/welfare.py` 与 `tests/test_dokan_welfare.py`）：
  - `tasks/Dokan/welfare.py`：
    - **有效刷新释放记录**：新增 `WelfareDokan._release_refresh_records()` 并在 `_refresh_list()` 调用 `_await_refreshed_list(before)` 成功后执行，按名移除 `C_DOKAN_REFRESH.name`（`'dokan_refresh'`）、`I_REFRESH_ENSURE.name`（`'RES_RYOU_DOKAN_REFRESH_ENSURE'`）与 `S_DOKAN_WELFARE_LIST_UP.name`（`'dokan_welfare_list_up'`，结清旧批 `static` 记录防止短列表 5 轮撞 10 次单按钮保护）；任何刷新失败路径均不释放，严禁调用 `click_record_clear()`。
    - **过冲回弹有界复位重滑**：新增 `ANCHOR_REBOUND_MAX = 150`、`SWIPE_REBOUND_CONSECUTIVE_LIMIT = 1`、`SWIPE_REBOUND_BATCH_LIMIT = 2` 与 `_is_recoverable_rebound(info)`（高置信度 `wrong_direction` 且 `0 < -dy <= 150`）；`_swipe_list(..., allow_rebound_recovery=False)` 保持先做同帧找馆页确认及 `on_unknown()` 扫当前屏「鑫」（命中合格直接开馆，点过不合格卡则先 `_hide_popup()`），允许恢复时记录日志并返回 `'rebounded'`（不计 `static`、不释放滑动记录）；`_scan_list_once()` 维护连续/批次计数，遇到 `'rebounded'` 清零此前的疑似到底 `unchanged` 后重滑确认（`'not_sent'` 不清连续计数，`'moved'`/`'static'` 清连续计数；超配额或 `|dy| > 150` 仍补观察 1 次后留图转人工）。
  - `tests/test_dokan_welfare.py`：同步适配 7 项涉及刷新后记录状态与 `SWIPE_NAME` 释放集合的既有断言（继续严格断言刷新前 `static`/`unknown` 不释放且绝不调用 `click_record_clear`）；新增连续 10+ 轮刷新防双按钮（含旁路 `_release_refresh_records` 第 6 次必崩反向对照）、短列表 8+ 轮防单按钮、4 类刷新失败不释放、真实 `oas2_1795612797739` 原图回放 `-52px` 恢复后两次 `static` 刷新、回弹清零疑似到底、回弹先扫「鑫」去重、连续 2 次/同批超 2 次/超 `150px` 转人工及切页拦截用例。
- **离线验证与原图回放（D069，未跑全量、未启动设备/游戏）**：
  - 3 对现场原图回放（RGB）：`oas2_1795612797739` 稳定输出 `wrong_direction, before_y=509, after_y=561, actual_dy=-52px, score=0.958`（`recoverable_rebound=True`）；`oas2_1795524394112` 与 `oas1_1795524566294` 仍稳定输出 `moved`（`+218px` / `+231px`，`recoverable_rebound=False`）。
  - 首轮守护 6 类 116 项（`log/test_runs/related_20261125_222327_27004.log`，59.9s，峰值 564 MiB）中 `SwipeProgressTest`(20)+`SearchTest`(17) 全部通过，`ListProgressTest`/`SwipeRecordTest`/`RefreshClosureTest`/`CandidateRecordTest` 因新释放契约适配及 `strip_view` 测试切片下沿越界出现 4 fail / 2 error；修正测试后 `py_compile` 与受影响 4 类复跑 79 项全部通过（`Ran 79 tests in 49.207s`，守护 52.6s，峰值 582 MiB，`log/test_runs/related_20261125_222611_34800.log`，0 skipped），`git diff --check` 通过。真实连续 6+ 次刷新与过冲回弹仍待 `oas1`/`oas2` Level C 验证。

## 2026-11-25 — 百鬼棋局常规找金鱼跨回合续查

- `oas2` 多轮找鱼从 6 号重新开始，短倒计时下反复点同一格，排在后面的 10 号没查到（`log/2026-11-25_oas2.txt` L6010–6014、L6235–6239、L6314–6321）。常规找鱼现在跨轮保留已查集合，每次按当前占用格重建候选并优先查没查过的格子。确认已空或登记为阵容位的格子从跨轮进度移除。候选全部查过仍未识别到金鱼时，后续回合才开始下一遍。
- 定向守护首轮的 12 项既有测试通过，新增跨轮用例因测试夹具缺少 OCR 注入失败。补齐夹具后，新增用例复跑通过，覆盖 `6 → 5 → 11 → 12 → 10` 分五轮续查、同轮结束后不重头查和下轮重扫（`log/test_runs/related_20261125_202401_26220.log`、`log/test_runs/related_20261125_202445_24844.log`）。真机待验。

## 2026-11-25 — 百鬼棋局统一扩大两套棋盘的勾玉搜索框

- 将普通和首领棋盘各 12 格的勾玉搜索框统一为 `52×50`，保留搜索框左上角坐标。同步 `c_frame.json` 与运行时 `assets.py`。定位继续用表情按钮锚点与各格相对坐标，金鱼仍按 `6 → 5 → 11 → 12` 优先搜索。
- 合成帧逐格覆盖两套棋盘扩框右下边缘，检查勾玉只命中所属格。18 项定向守护测试通过（`log/test_runs/related_20261125_194751_25548.log`）。普通及首领棋盘原图和实盘仍待复测。

## 2026-11-25 — 百鬼棋局扩大普通棋盘 11 号位勾玉搜索框

- `oas2` 第 8 回合关店后 11 号位仍为 `unknown`（`log/2026-11-25_oas2.txt` L4197–4199）。根据截图中勾玉可能贴近原框下沿的情况，普通棋盘 11 号勾玉框从 `(737,413,33,32)` 向右、向下扩为 `(737,413,52,50)`，同步 `c_frame.json` 与 `assets.py`。勾玉阈值、小纸人规则和上阵落点沿用现有配置。
- 新增合成帧回归覆盖勾玉落在旧框之外、且相邻 12 号位仍独立识别的情况。4 项定向守护测试通过，日志 `log/test_runs/related_20261125_193846_21936.log`。原图识别结果与实盘找鱼仍待复测。

## 2026-11-25 — 百鬼棋局备战直接上卡优先与挡位待搬金鱼保护局部修复

- 按仓库规则在当前百鬼棋局准备阶段 WIP 之上完成两项局部修复，完整保留已有 WIP（满员单张核实回收、手牌重排重定位、小纸人判空、左栏「荒川 ≥ 2」、常规找金鱼 `6 -> 5 -> 11 -> 12` 顺序及跨轮续查不改）、`docs/CURRENT.md` 与其他模块 WIP。
- **任务开始内容指纹**（`master` @ `cbba5986ed23e62af3d16ee303a3e9ad1036c389`）：
  - `tasks/Chess/runtime/hand_operations.py` SHA256 `2228015AFB5FA47E224F82580C70FA1E467C71F7E45C71B85F327C87B016F01E`
  - `tasks/Chess/script_task.py` SHA256 `49FEAE885411D547193DACFD1D871FDBB9F139E78DFE9B4DD6A7DAD18BF9AEA3`
  - `tests/test_chess_frame.py` SHA256 `DEA4D3E3C94AAF00A266D720392CDDCE7A3FF3F6EF58AB20A58887054AA39AF8`
- **实际改动**：
  - `tasks/Chess/runtime/hand_operations.py`：
    - 新增 `_can_direct_deploy_lineup_card()` 与 `_select_next_deploy_candidate()`，在 `deploy_shikigami_from_hand()` 每次以最新帧扫描棋盘与手牌后，先从「配置目标格确认 `empty` 且 `not capacity.get('full')`」的阵容卡中按原 `deploy_weight` 和左至右排序选牌；存在可直接上卡候选时先完成直接上卡，跳过阻塞格详情查询/搬鱼，并在非荒川直上路径排除 `_recall_one_system_board_card()` 试回收别的格（不因荒川 `< 2` 先拉回收位）；无直接可上卡时再回退按原权重处理需要腾位的牌，保留剩余时间门槛、单格一次查询与满员核实回收保护，每次上卡/回收/搬鱼后于下一循环用新帧重判空位与坐标；入口清零 `_last_system_recall_outcome`。
    - 新增 `_set_goldfish_relocation_pending()` 与 `_is_blocking_goldfish_relocation_pending()`，配合 `_goldfish_relocation_source`（并在 `_reconcile_displaced_slot_occupants()` 清理金鱼占格时同步清零）；`_handle_blocking_target_slot_before_deploy()` 在确认金鱼时间不足或配置金鱼位不可用/被保留单位占用标记待搬时保留 `'blocking'` 来源；`_move_arakawa_goldfish()` 自身、`_detect_pending_arakawa_goldfish()` 与 `_handle_goldfish_after_board_action_failure()` 均对 `'blocking'` 待搬请求强制 `use_blocking_guards=True`，发拖前用当前帧复核准备阶段、商店已关、`remaining >= GOLDFISH_BLOCKED_KNOWN_MOVE_MIN_REMAINING (6)`、`_check_goldfish_target_slot_usable()`（配置金鱼位 `empty` 且非源格/非保留单位）及左栏荒川 `>= 2`，任一不满足保留待办且 0 拖拽；仅在新帧确认原格 `empty` 且配置金鱼位 `occupied` 后更新站位并清除待办。
  - `tasks/Chess/script_task.py`：`_start_chess_game()` 初始化 `self._goldfish_relocation_source = None`。
  - `tests/test_chess_frame.py`：
    - 在 `PreparationOrderAndBlockingGoldfishTest` 新增 `test_direct_deploy_cards_run_before_blocked_cards_without_premature_inspect_or_recall`（河童 weight=1 目标 11 被未知单位堵住、铃鹿/白狼 weight=2 目标空着且允许直上时，用递减倒计时验证先上铃鹿/白狼；余时跌至 8s 不点 11；余时留 10s 再查 11 一次并搬鱼重定位上河童；并验证荒川 `< 2` 时直上路径不先试回收 6 号格）与 `test_blocking_goldfish_pending_relocation_keeps_guards_in_tail_and_next_round_retry`（11 查出金鱼而 12 有已登记荒川之主时，备战收尾 0 拖拽且双方位置保持正确；跨到下轮后各重试入口对余时 4s/开店/非备/荒川 `<2`/12 未知/12 被占均保持 0 拖拽，腾空但未确认落位不记 12 到达，确认后才更新 12）；
    - 同步 `BoardScanTest.test_single_system_recall_unknown_after_drag_stops_recall_and_deploy_pass`（第 2 轮目标格空且未满走直上不触发系统回收，补充目标未知且回收位全空时的 `not_found` 断言）与 `PreparationOrderAndBlockingGoldfishTest.test_blocking_slot_guards_and_fallback_to_other_deployable_cards`（`move_unconfirmed` 场景改为先上铃鹿再尝试 11->12 搬鱼）。
- **验证（D069 最小相关，未跑全量、未启动设备/游戏/服务）**：
  - 首轮 3 文件 `py_compile` 与守护测试 93 项中 92 通过、1 失败（`BoardScanTest.test_single_system_recall_unknown_after_drag_stops_recall_and_deploy_pass` 行 567 因新规则第 2 轮 `all_empty` 不再先试系统回收而保留旧值 `'unknown_after_drag'`，`log/test_runs/related_20261125_185244_25064.log`）。
  - 修正入口清零 `_last_system_recall_outcome = None` 并更新该用例及补充未知目标 `not_found` 断言后，复跑 3 文件 `py_compile`、相关目标守护 **93/93 全部通过**（`Ran 93 tests in 45.017s`，守护耗时 `48.7s`，采样峰值 `552 MiB`，日志 `log/test_runs/related_20261125_185424_28656.log`），3 个源码/测试文件 `git diff --check` 通过。
  - **真机待验（Level C）**：详见 `docs/ROADMAP.md` 2026-11-25 备战顺序与挡位金鱼条目，待在 `oas2` 等真机窗口核对。

## 2026-11-25 — 百鬼棋局备战执行顺序、堵格金鱼处理、时间门控与 `6 -> 5 -> 11 -> 12` 常规找金鱼去重试改

- 依据 `log/2026-11-25_oas2.txt` 第 16 回合复现（L3282–3291：初始购卡结束剩 `14s` 停止升级/刷新后，17:35:02 `deploy_shikigami_from_hand()` 关店先找金鱼，点 2 号位 3 次耗时 10.56s、点 4 号位 1 次至 17:35:17 进入战斗，手牌内河童始终未被扫描或拖拽），按用户已批准方案在当前工作区试改百鬼棋局准备阶段执行顺序、堵格清金鱼、时间门控与常规找金鱼去重，完整保留前几轮荒川满员单格核实回收、手牌重排重定位、小纸人判空、左栏「荒川 ≥ 2」原始 OCR、购卡 3 次总预算/第 3 击延迟确认、`<= 9/10` 零卖卡、装备优先链、既有 `Press_and_Drag`/点击接口、`docs/CURRENT.md` 及其他任务 WIP。
- **任务开始基线**（`master` @ `cbba5986ed23e62af3d16ee303a3e9ad1036c389`，副本与校验保存在 `C:\Users\cbz19\.gemini\antigravity\brain\0f2ca2de-294b-4d72-a661-c271baf9b9ca\scratch\baseline_prep_goldfish_20261125\`）：
  - `tasks/Chess/runtime/settings.py` SHA256 `3643AA44FF19E08112322C615C5451B0C1EA2498AB5DC53242F3422DD8348D5`
  - `tasks/Chess/runtime/economy.py` SHA256 `CBB2BF9C12C9F5C558D356D5818F56DE20755896E0C24787601A015944897EBF`
  - `tasks/Chess/script_task.py` SHA256 `8C09E78AC10D46AC7DFC91AE74FDE68499E02D2712BF49E7FE9466C90D2EAD9B`
  - `tasks/Chess/runtime/hand_operations.py` SHA256 `DF60A5F43AAD2D2C619C6C66A8D6051537756A72EBA49F1973970D12A6E3DD2F`
  - `tests/test_chess_frame.py` SHA256 `C81F04C10EDD0105D25F2BC3170D0864E60CE55943768C67B016A084EB051BA6`
  - 注：`tasks/Chess/runtime/state_loop.py`（281 行，本轮 `+4 / -0`）与 `tests/test_chess_runtime_absorb.py`（466 行，本轮 `+6 / -2`）以读取快照作为本轮对照基线；`docs/CURRENT.md` 与无关 WIP 保持未动。
- **实测耗时与时间阈值确定**（均提取自 `log/2026-11-25_oas2.txt` 实盘时间戳）：
  - `Press_and_Drag` 22 次样本：最小 `0.78s`、均值 `0.93s`、最大 `1.24s`。
  - 关店 + 棋盘/人口首帧扫描（`C_MARKET` → `Chess lineup capacity`）：`0.58~1.00s`（L2912–2913 0.58s、L2958–2959 1.00s、L3229–3230 0.73s、L3285–3286 0.73s）。
  - 单次详情核查（`chess_inspect_*` + `_wait_chess_action_state(3.0s)`）：1 次打开失败 `3.5~3.6s`、3 次连续失败 `10.56s`（L3284–3288），1 次正常打开读取并关闭 `3.61s`（L3191–3192）。
  - 在 `tasks/Chess/runtime/settings.py` 新增集中常量：
    - `GOLDFISH_INSPECT_PRIORITY_POSITIONS = (6, 5, 11, 12)`
    - `GOLDFISH_SINGLE_INSPECT_MIN_REMAINING = 4`（1 次详情耗时 `~3.5~3.61s`）
    - `GOLDFISH_REGULAR_MOVE_MIN_REMAINING = 3`（仅补拖已定位金鱼约 `1.2s + 1~2s` 确认）
    - `GOLDFISH_REGULAR_SEARCH_MIN_REMAINING = 6`（启动常规巡检：单次查格 `~3.6s` + 搬运 `~1.1s` + 余量）
    - `GOLDFISH_BLOCKED_KNOWN_MOVE_MIN_REMAINING = 6`（已知金鱼搬运 + 确认腾空到位 + 扫牌上卡）
    - `GOLDFISH_BLOCKED_INSPECT_AND_MOVE_MIN_REMAINING = 9`（未知阻塞格先点 1 次详情 `~3.6s` + 搬运/回收 + 确认 + 扫牌上卡，合计 `~8.7s`）
    - `PREPARATION_ECONOMY_POST_BUY_REDEPLOY_MIN_REMAINING = 4`（经济环买到新卡后关店扫牌 `0.7~1.0s` + 单次拖卡确认 `1.5~2.5s`）
- **实际改动**：
  - `tasks/Chess/runtime/settings.py`（`+17 / -0` 行）：增加上述优先格序及 6 项时间阈值常量与实测说明注释。
  - `tasks/Chess/runtime/economy.py`（`+7 / -0` 行）：`_reset_economy_state()` 与 `_run_economy_atomic_batch()` 在 `refresh` 后且非战斗模式买到新卡时记录 `_economy_purchased_cards_pending_deploy`。
  - `tasks/Chess/runtime/state_loop.py`（`+4 / -0` 行）与 `tasks/Chess/script_task.py`（`+61 / -6` 行）：
    - 将 `PREPARE` 主序调整为 `purchase_lineup_cards_once() -> _run_preparation_initial_deploy_stage() -> _run_preparation_economy_until_time_limit() -> _handle_preparation_stage(1)`；
    - 新增 `_run_preparation_initial_deploy_stage()` 与 `_redeploy_after_preparation_economy_purchase()`（买到新卡且仍在备战、`remaining is None or >= 4s` 时立即关店上阵）；
    - `_handle_preparation(run_regular_goldfish=True)` 仅在备战收尾完成上卡与上御魂后且处于准备+关店状态时调用 `_detect_pending_arakawa_goldfish(context='preparation_tail')`，并在 `_start_chess_game()` 初始化 `_goldfish_lookup_needed` 与 `_prep_goldfish_round_state`。
  - `tasks/Chess/runtime/hand_operations.py`（`+682 / -104` 行）：
    - 审计全部 `_detect_pending_arakawa_goldfish()` 调用点：移除 `deploy_shikigami_from_hand()` 入口与荒川落位后的中途全盘扫描、将 `_equip_selected_hand_equipment()` 装备「荒川纹章」后调用改为置 `_goldfish_lookup_needed = True` 延至备战收尾，仅留 `_handle_preparation()` 尾入口；
    - 新增 `_ensure_prep_goldfish_round_state()` / `_reset_prep_goldfish_round_state()` 按回合跟踪 `inspected_slots`、`blocked_card_attempts`、`candidate_snapshot` / `board_complete_snapshot`、`candidate_order`；
    - 新增 `_handle_blocking_target_slot_before_deploy()`：当候选牌配置格为 `occupied` 且非己方已登记占格、处于准备+关店且左栏荒川 `>= 2` 时，单轮单卡最多尝试 1 次介入——未知身份仅在 `remaining >= 9s`（未查重）点 1 次详情（`_inspect_board_set_shikigami(..., max_attempts=1)`）；确认普通非阵容卡直接复用 `_recall_and_relocate_arakawa_card()` 单格回收重定位后上卡；确认金鱼则通过 `_check_goldfish_target_slot_usable()` 与 `_move_arakawa_goldfish(..., verify_vacated_source=True)` 核对 `remaining >= 6s`、配置金鱼位为 `empty` 且非保留单位、拖拽后新画面确认原格 `empty` 且金鱼格 `occupied` 再重扫上卡；时间不足、倒计时返回 `None`、详情未开、移动未确认或金鱼位不可用均本轮暂缓该牌并继续上其余可上阵容卡；
    - 非荒川卡当目标格为空、人口未满且左栏荒川 `>= 2` 时直接上阵不盲拉系统回收位；`_recall_one_system_board_card()` 避开已确认金鱼格并在 `raise_on_failure=True` 且首次回收失败、荒川 `>= 2` 时补检 1 次防把未识别金鱼三连拖抛 `GameStuckError`；
    - `_detect_pending_arakawa_goldfish()` 改用 `_sort_goldfish_candidate_slots()`（`6 -> 5 -> 11 -> 12` 再其余未登记占格升序）、`max_attempts=1`、入口与逐格时间检查、同轮已查去重及完整棋盘快照未变时从剩余候选续查（变化或含未知格重算重排），日志输出 `remaining_time`、候选顺序及 11 号位等站位过滤原因。
  - `tests/test_chess_frame.py`（`+657 / -0` 行）与 `tests/test_chess_runtime_absorb.py`（`+6 / -2` 行）：同步 `ArakawaGoldfishTriggerTest._build_shim`、`ScriptedBase`/`StateLoopTest` 备战阶段序列，新增 `PreparationOrderAndBlockingGoldfishTest` 4 组综合回归（备战顺序与买卡补上阵/重排坐标 + `荒川纹章` 延迟标志；阻塞金鱼与普通非阵容卡清格重定位上卡；时间不足/倒计时 `None`/详情打不开/搬运未确认/金鱼位被保留单位占用 5 类边界回退；`6 -> 5 -> 11 -> 12` 常规顺序/同轮去重/中途停下与完整盘面续查/变盘重算/跨回合清零）。
- **验证（D069 最小相关，全部在末次代码编辑后重跑，未跑全量、未启动设备/游戏/服务）**：
  - 7 份改动文件 `py_compile` 通过；
  - 守护第一组 `BoardScanTest`（15）+ `ArakawaDirectDeployTest`（10）+ `ArakawaGoldfishTriggerTest`（6）+ `LineupCapacityStatusTest`（6）+ `PreparationOrderAndBlockingGoldfishTest`（4）+ `test_chess_runtime_absorb`（34）+ `test_chess_upstream_73d4ae84_boundary`（16）合计实跑 **91/91 全部通过**（`Ran 91 tests in 42.813s`，守护耗时 `46.8s`，采样峰值 `554 MiB`，日志 `log/test_runs/related_20261125_181210_25184.log`；`test_chess_frame.py` 按所选 5 个直接相关测试类执行，未展开未选的 `CardScanTest` 等）；
  - 守护第二组 `EquipmentAndHandCleanupTest` **8/8 全部通过**（`Ran 8 tests in 112.030s`，守护耗时 `115.7s`，采样峰值 `519 MiB`，日志 `log/test_runs/related_20261125_181306_28648.log`）；
  - **真机待验（Level C）**：详见 `docs/ROADMAP.md` 同名条目，待在 `oas2` 等真实对局窗口验证。

## 2026-11-25 — 百鬼棋局荒川卡直上满员/未知人口核实回收与重定位修复

- 依据 `log/2026-11-25_oas2.txt`（第 5 回合 L2957–2973：三阶、`occupied=3 [6, 9, 12]`、`unknown=[2, 11]`、`visual_state=unknown` 回退给出 `full=False`，座敷童子直拖 2 号弹回返回 `specifics_not_opened` 且手牌 `1->1`），按用户已批准范围修复 `tasks/Chess/runtime/hand_operations.py` 中荒川直上分支与 `_recall_one_system_board_card()`，保留普通上卡、金鱼识别与移动、装备分配、人口判断规则、`docs/CURRENT.md` 及其他任务 WIP 原样，不改触控模型。
- **任务开始基线**（`master` @ `cbba5986ed23e62af3d16ee303a3e9ad1036c389`，副本与校验保存在 `C:\Users\cbz19\.gemini\antigravity\brain\0f2ca2de-294b-4d72-a661-c271baf9b9ca\scratch\baseline_arakawa_recall_20261125\`）：
  - `tasks/Chess/runtime/hand_operations.py` SHA256 `F7303D3653B290D10DC683DAC767DD142E3EACF8C1E4DFC32609D688D9F033B8`
  - `tests/test_chess_frame.py` SHA256 `A986E007616F0ED510256A802EE868EBD45AD3126E9CBADA2838F12F99C79C4C`
- **实际改动**：
  - `tasks/Chess/runtime/hand_operations.py`（相对本轮基线 `+675 / -16` 行；唯一修改的生产文件）：
    - 在 `_deploy_arakawa_hand_card_direct()` 补充返回并记录 `hand_stars_before` / `hand_stars_after`（含 `shop_not_closed` 分支对齐字段）。
    - 新增 `_classify_lineup_capacity_state()`、`_protected_recall_positions()`、`_classify_inspected_recall_occupant()`、`_verify_arakawa_recall_candidate()`、`_find_verified_arakawa_recall_slot()`、`_recall_and_relocate_arakawa_card()`、`_evaluate_unknown_capacity_arakawa_retry()` 与 `_build_pending_arakawa_deploy()`：
      1. **确认满员**：目标格 `occupied` 时先经详情与阵容配置核实；若确认为非阵容系统棋子（如 6/12 号占位），优先只回收目标格；若目标格确认 `empty`，按 `BOARD_RECALL_POSITIONS` 顺序核实并只回收 1 张可安全回收的系统棋子；若目标格为金鱼/已登记/阵容单位/身份未知，或棋盘无可回收候选、候选区已满（`>= 10/10`）、准备阶段结束，则本轮暂缓（不靠清他格硬挤占格）。
      2. **确认未满或人口不明确**：保留 1 次直拖到配置格。确认未满未确认仍直接退出本轮待重刷；人口不明确时，仅当新画面仍在准备且关店、同一张卡仍在候选区（未消耗且 `_lineup_hand_stars` 前后完整一致）、目标位确认未上卡（`specifics_not_opened` 单独出现不算失败证据，须新帧确认目标格 `empty` 且无星级；或 `target_occupied_by_other` 且目标为同星可回收非阵容系统单位）且无合卡/升星证据时，才允许补充 1 次核实回收再尝试 1 次拖拽。手牌已消耗、星级/身份不明、目标为金鱼或保留单位或结果歧义时绝不回收、不重拖。
      3. **回收与重定位约束**：为 `_recall_one_system_board_card()` 新增 `candidate_positions` 与 `raise_on_failure=False` 约束及发拖前准备阶段检查，使荒川分支只拖已核实的唯一格且绝不跌落到后续未核实候选格（普通上卡默认全保留原样）。回收后必须重新截图确认该格确实腾出（`empty`），并调用 `_find_best_shikigami_hand_card()` 重扫候选区定位同一张卡的新坐标再拖到配置格，禁用回收前坐标；每卡最多回收 1 张、回收后最多拖 1 次，仅详情确认式神一致才登记实际站位。
    - `deploy_shikigami_from_hand()` 新增 `deferred_names` 本轮暂缓排除集合，并在关键路径输出包含人口来源、目标格、实际回收格及跳过/阻止原因的结构化日志。
  - `tests/test_chess_frame.py`（相对本轮基线 `+643 / -34` 行）：
    - 在 `ArakawaDirectDeployTest` 同步既有 `not_full` 直上及单卡盘面用例的 `capacity` 条件，新增 `_wire_multi_step_board()` 与 4 组完整正负向回归：`test_full_capacity_target_six_or_twelve_occupied_by_verified_system_recalls_target_first_and_relocates_hand`、`test_full_capacity_target_two_empty_recalls_verified_alternate_once_skips_protected_and_deploys_to_two`、`test_unknown_capacity_direct_deploy_unconfirmed_recalls_once_and_retries_once_or_stops` 与 `test_arakawa_guards_block_unjustified_recall_and_second_drag`（覆盖 `specifics_not_opened` 缺证据、`hand_consumed`、手牌星级不明确、金鱼/未知身份、满手牌 `10/10`、回收后 `unknown_after_drag`、切战阶段 7 类保护）。
    - 在 `LineupCapacityStatusTest` 更新满员荒川子用例以验证确认满员先核实回收 `10` 号系统卡并重定位上阵，以及目标未知 `???` 安全暂缓不盲拖。
- **详情识别已知缺口**：当前详情页（`I_SHIKIGAMI_SPECIFICS`、`I_CHECK_GOLDFISH`、`O_NAME_RANGE` 与头部兜底 OCR）无法打开或返回空文本/乱码/歧义/未收录名，以及棋盘目标格自身为 `unknown` 时，均无法证明占位可安全回收，本改动严格保留跳过与暂缓逻辑。
- **验证（D069 最小相关，未跑全量、未启动设备/游戏/服务）**：
  - 首轮守护运行 `BoardScanTest`（15）+ `ArakawaDirectDeployTest`（10）+ `ArakawaGoldfishTriggerTest`（6）+ `LineupCapacityStatusTest`（6）共 37 项中，前三组 31/31 全通过，`LineupCapacityStatusTest` 因新写测试 `patch(..., side_effect=fake_ara_detect)` 传参少了 `self` 报 `TypeError`（1 ERROR，`log/test_runs/related_20261125_174118_29744.log`）。
  - 修正该测试 mock 为 `new=fake_ara_detect` 并补充未知目标暂缓子断言后，按 D069 复跑 `LineupCapacityStatusTest` 6 项全部通过（2.571s，守护 6.9s，峰值 490 MiB，日志 `log/test_runs/related_20261125_174234_11480.log`），2 文件 `py_compile` 与 `git diff --check` 退出码均为 0。
  - **真机待验（Level C）**：见 `docs/ROADMAP.md` oas2 第 5 回合同类三阶满员（`visual=full` 及 `visual=unknown` 回退）实盘对局验证项。

## 2026-11-25 — 百鬼棋局第 3 次购卡点击后延迟确认收尾

- 按要求修复 `tasks/Chess/runtime/economy.py` 中第 3 次购卡点击后在 `0.3s` 过早返回 `still_present` 导致错过延迟消失（如点击后约 `0.6s` 消失）的问题；完整保留 3 次实际点击总预算、满仓清理优先顺位、有空位零卖卡契约、公共 `tasks/base_task.py`、`module/`、用户标注素材、`docs/CURRENT.md` 及其他预存 WIP。
- **任务开始基线**（`master` @ `cbba5986ed23e62af3d16ee303a3e9ad1036c389`，副本与校验保存在 `C:\Users\cbz19\.gemini\antigravity\brain\0f2ca2de-294b-4d72-a661-c271baf9b9ca\scratch\baseline_buy_3rd_click_confirm_20261125\`）：
  - `tasks/Chess/runtime/economy.py` SHA256 `7A7F5D00E2F2E9A42B2B475A8282237EBA5613514698D574526BC2582FB0942D`
  - `tests/test_chess_frame.py` SHA256 `4A7B8EA731E21133784D807A2D3BAF53452CCB7834AFF40E8B60B8A6C2663C39`
  - `tests/test_chess_upstream_selective_merge.py` SHA256 `0AB0398235481218C1448C29AE02AA0C0B882FABA6E2F4F4B0D02FDFC758EC50`
- **实际改动**：
  - `tasks/Chess/runtime/economy.py`（相对本轮基线 `+23 / -10` 行）：
    - `_click_shop_slot_once_and_confirm()` 新增仅关键字参数 `stop_on_still_present: bool = True`：默认前两次点击仍在 `interval=0.3s` 仍见目标时返回 `still_present`；当传入 `stop_on_still_present=False` 时，跳过 0.3s 早退分支，仅继续截图与识别观察画面，直到连续两帧消失返回 `confirmed`、被阶段切换/符咒弹窗打断返回 `aborted`，或达到 `attempt_deadline = min(deadline, enter + attempt_timeout)` 返回 `timeout`。
    - `_buy_shop_slot()` 在即将发出预算内最后一击（`clicks_used + 1 >= max_clicks`）时传 `stop_on_still_present=False`；确认成功即清理该格点击记录并返 `True`；若非 `confirmed` 且 `clicks_used >= max_clicks`（或 `status in ('aborted', 'missing_before_click')`），立即记录日志并返 `False`，即使手牌为满也不触发清理、卖卡或第 4 击；复用 `still_present`/`timeout` 携带的末帧 `match` 避免同帧重复识别。
  - `tests/test_chess_upstream_selective_merge.py`（相对本轮基线 `+165 / -0` 行）：在 `BuyShopSlotTest` 新增 `test_third_click_delayed_disappearance_at_point_six_seconds_succeeds`、`test_third_click_always_visible_until_timeout_fails_with_three_clicks_and_no_cleanup` 与 `test_third_click_single_frame_loss_or_interrupt_after_point_three_fails`（覆盖 0.6s 仅缺一帧后重现、鬼阶段切换、符咒弹窗打断与 `deadline` 截断 4 条子路径）。
  - `tests/test_chess_frame.py`（相对本轮基线 `+147 / -1` 行）：`_bind_real_buy_click_loop()` 支持可选 `on_frame` 回调；新增 `test_buy_third_click_delayed_confirmation_and_full_hand_isolation`（覆盖 8/10 第 3 击 0.3s 仍在、0.6s 连续两帧消失成功；10->9 清理后共用预算并在第 3 击 0.6s 确认成功；以及第 3 击后手牌满 10/10 且目标一直可见直至超时失败、恰好 3 击、第 3 击后 0 清理 0 卖卡）。
- **验证（D069 最小相关，未跑全量、未启动设备/游戏/服务）**：
  - 守护运行 `EquipmentAndHandCleanupTest`（8）+ `UiClickUntilDisappearTest`（6）+ `BuyShopSlotTest`（17）+ `HandRecoveryTest`（7）共 38 项全部通过（110.289s，守护总耗时 114.9s，峰值 515 MiB，日志 `log/test_runs/related_20261125_171155_27292.log`）；3 文件 `py_compile` 与目标文件 `git diff --check` 全部通过（退出码 0）。
  - **真机待验（Level C）**：真机商店第 3 击若卡面动画在 0.3s~2.0s 间延迟消失时能否稳定等到两帧消失确认返回成功，以及始终未确认/切阶段/符咒打断时停在第 3 击不误清理、不卖卡。

## 2026-11-25 — 百鬼棋局 `_buy_shop_slot()` 实际点击总预算修复

- 按用户明确要求与 `docs/DECISIONS.md` D036 预算语义，在 `tasks/Chess/runtime/economy.py`、`tests/test_chess_frame.py` 与 `tests/test_chess_upstream_selective_merge.py` 修复单次目标购卡最多可点到 9 次的问题，收口为全流程总计最多 **3 次**实际购卡点击；完整保留前几轮全部 Chess 改动（小纸人判空、荒川直拖、左栏「荒川 ≥ 2」触发、上卡人口判断、装备分配与满仓清理、购卡重试零误卖）、公共 `tasks/base_task.py`、`module/`、用户标注素材、`docs/CURRENT.md` 及其他预存 WIP。
- **任务开始基线**（`master` @ `cbba5986ed23e62af3d16ee303a3e9ad1036c389`，副本与清单保存在 `C:\Users\cbz19\.gemini\antigravity\brain\0f2ca2de-294b-4d72-a661-c271baf9b9ca\scratch\baseline_buy_click_budget_20261125\`）：
  - `tasks/Chess/runtime/economy.py` SHA256 `D23989A4C4EA891E130D95F6551BE8926A893470695883FFF9C2A41EFC0DCFC6`
  - `tests/test_chess_frame.py` SHA256 `1E665418945A5F15C2ABBE79293D28E15CC76A48CA6B036DA9175204BC253237`
  - `tests/test_chess_upstream_selective_merge.py` SHA256 `CE775EB9F7E66980954DE2B1272ABBF9413F60FACEF48DC1F476AACF73216867`
- **实际改动**：
  - `tasks/Chess/runtime/economy.py`（相对基线 `+225 / -115` 行；唯一修改的生产文件）：
    - 在 `ChessEconomyMixin` 新增局部常量 `SHOP_BUY_MAX_CLICKS = 3`、`SHOP_BUY_CLICK_INTERVAL = 0.3`、`SHOP_BUY_CLICK_ATTEMPT_TIMEOUT = 2.0`、`SHOP_BUY_CONFIRM_FRAMES = 2` 及局部单次可计数确认方法 `_click_shop_slot_once_and_confirm()`（不修改公共 `tasks/base_task.py`）。每次最多发出 1 次 `self.click(click_rule, interval=interval)`，仅当 `click()` 返回 `True` 时记 `clicked=True`，之后仍完成连续 `confirm_frames=2` 帧消失确认；未发出点击前目标消失（`missing_before_click`）、触发百鬼/符咒弹窗（`aborted`）或未发点击超时均直接返回失败。
    - 改造 `_buy_shop_slot()` 在同一目标卡的首次点击、失败重试及满仓清理重开店之间共用一份 `clicks_used < SHOP_BUY_MAX_CLICKS`（3 次）实际点击预算：关店、清理与重开店均不消耗也不重置预算；购前及购后清理重开店后重新识别目标格，消失或身份变化立即退出且 0 点击失败；第 3 次实际点击发出后仍完成两帧确认（成功则清该格点击记录返回 `True`，未确认或 `clicks_used >= 3` 则直接退出、绝不发第 4 次点击也不做第 3 击后额外清理）；移除了循环末尾误将 `current_match is None` 当成成功的兜底；继续沿用 `<= 9/10` 零清理零卖卡、仅确认 `>= 10/10` 且尚有预算时走统一满仓清理（`sell_lineup=False`）规则。
  - `tests/test_chess_frame.py`（相对基线 `+189 / -56` 行）：
    - 在 `EquipmentAndHandCleanupTest` 更新 `_bind_real_buy_click_loop()`（移除 `BaseTask.ui_click_until_disappear` 绑定与未用导入，改为按 `interval` 节流并只记录 `C_SHIKIGAMI_1..5` 点击清理记录，排除 `I_MARKET` 开关店）；`test_twelve_of_ten_full_hand_clears_via_equipment_to_nine_without_selling_shikigami` 同步改用真实购卡点击流程并断言实际购卡点击 1 次。
    - 更新 `test_both_pre_purchase...`（`2` 击成功、0 卖卡）、`test_buy_retry_continuous_failure_at_8_of_10_never_sells_and_exits_within_budget`（A 8/10 连续失败 `3` 击 0 清理 0 卖卡、B 10->9 清理后降到 8/10 共用 `3` 击 1 清理 0 卖卡、C 第 3 击连续两帧消失成功 `3` 击、D1/D2 清理重开换卡及点击前消失均为 `0` 击失败）与 `test_buy_retry_post_click_confirmed_10_of_10_prioritizes_equipment_and_stops_at_9_without_selling_shikigami`（A `2` 击成功 0 卖式神、B 两轮清理共用总计 `3` 击成功 0 卖式神、C 装备出售未确认中止 `1` 击）。
  - `tests/test_chess_upstream_selective_merge.py`（相对基线 `+54 / -13` 行）：更新 `BuyShopSlotTest` 中受 9/6/4/3 旧预算假设影响的 7 个用例断言为总预算 `<= 3`（A1 `2` 击、空位连续失败 `3` 击、`NOOP` 卖阵容兜底 `2` 击、重开失败 `1` 击等），并新增 `test_third_click_confirmed_by_two_missing_frames_returns_true`、`test_target_disappearing_before_first_click_is_not_success` 与 `test_cleanup_shares_three_click_budget_and_stops_at_three_without_extra_cleanup`；`UiClickUntilDisappearTest`（6）与 `HandRecoveryTest`（7）保持原样并全部通过。
- **验证（D069 最小相关，未跑全量、未启动设备/游戏/服务）**：
  - 首轮测试时 `tests/test_chess_frame.py` 新增的 `removed_records` 未过滤 `_ensure_shop_closed/open` 清空的 `I_MARKET` 导致 3 条点击记录断言失败（`log/test_runs/related_20261125_164337_3604.log`），在 `_bind_real_buy_click_loop()` 仅统计 `C_SHIKIGAMI_1..5` 后复跑：守护运行 `EquipmentAndHandCleanupTest`（7）+ `UiClickUntilDisappearTest`（6）+ `BuyShopSlotTest`（14）+ `HandRecoveryTest`（7）共 34 项全部通过（89.751s，守护总耗时 93.5s，峰值 523 MiB，日志 `log/test_runs/related_20261125_164554_25328.log`），3 文件 `py_compile` 与目标文件 `git diff --check` 全部通过（退出码 0）。
  - **真机待验（Level C）**：真机商店连续购卡未确认在总计 3 次点击内停止不误多点、清理/重开店沿用剩余预算（不重置）、第 3 击成功两帧确认与目标先消失/换卡 0 击不误判成功。

## 2026-11-25 — 百鬼棋局购卡重试误卖修复

- 针对 `tasks/Chess/runtime/economy.py::_buy_shop_slot()` 在购卡点击失败且 `hand_count_after_fail < 10` 时仍经 `sell_lineup = emergency_cleanup_done and hand_count_after_fail < 10` 与 `_purchase_recovery_require_free_one = True` 误触发清理或直跳卖阵容式神的缺陷实施修复，完整保留既有装备分配、满仓清理、上卡人口判断、小纸人判空、荒川直拖与左栏「荒川 ≥ 2」触发改动、用户素材（`tasks/Chess/c/*`、`tasks/Chess/assets.py`）、`module/`、`docs/CURRENT.md` 及其他预存 WIP；沿用现有 `ui_click_until_disappear`（两帧确认、每轮最多 3 次点击）与购买预算，未做额外重构。
- **任务开始基线**（`master` @ `cbba5986ed23e62af3d16ee303a3e9ad1036c389`，副本与校验保存在 `C:\Users\cbz19\.gemini\antigravity\brain\0f2ca2de-294b-4d72-a661-c271baf9b9ca\scratch\baseline_buy_retry_fix_20261125\`）：
  - `tasks/Chess/runtime/economy.py` SHA256 `11C87DE2D213E5FA0F77E0EB0EB78C09175398A1CDF4E5925F1B2AB491C931EB`
  - `tasks/Chess/runtime/hand_operations.py` SHA256 `149C8E9009A1A60FCE5E276B624E826E804E54FB35988FCEB71E7A68CC5F8E06`
  - `tests/test_chess_frame.py` SHA256 `1C1CB3D5FBD2DE6FFB8E98A6B0BC9086C11D5AF4662DAA6E7818C40ACF0E6C70`
  - `tests/test_chess_upstream_selective_merge.py` SHA256 `4459C76CBFFB374CE429EC7D91659439625D66A46228EAD24AE73B7A524F8A85`
- **实际改动**：
  - `tasks/Chess/runtime/economy.py`（相对基线 `+56 / -34` 行）：
    - 移除 `emergency_cleanup_done`、`sell_lineup = emergency_cleanup_done and hand_count_after_fail < 10` 及全部 `_purchase_recovery_require_free_one` 赋值，引入 `max_attempts = 3` 点击轮次上限保护（`attempts >= max_attempts` 即中止）。
    - 统一检查「购前满仓」「首次购后失败」「后续购后失败」三个入口：购后点击未确认且目标仍在、模式/金币/符咒检查通过后，以当前截图 `self._hand_capacity_count()` 重新确认手牌数量。若 `hand_count_after_fail <= 9`（有空位），绝不调用 `_free_one_hand_slot_for_purchase()` 或触发任何卖卡/清理，若已触发过阵容兜底卖卡或已用满 `max_attempts = 3` 轮点击则干净取消购买，否则直接进入下一轮重试。
    - 仅当 `hand_count_after_fail >= 10`（确认仍满）且未超 `post_click_recoveries >= 2` / `attempts >= max_attempts` / `lineup_sale_done` 时，始终以 `sell_lineup=False` 调用 `_free_one_hand_slot_for_purchase()` 走完统一满仓清理顺序，严禁凭「之前清理过」直跳卖阵容卡；返回 `None`（含装备出售未确认/切阶段/重开商店失败）或清理后复测仍 `>= 10/10` 均立即中止。
  - `tasks/Chess/runtime/hand_operations.py`（相对基线 `+3 / -15` 行）：
    - 在 `emergency_cleanup_hand()` 移除 `_purchase_recovery_require_free_one` 与 `actions_done` 绕过，将停机条件收紧为纯 `if current_count <= 9: break`。
    - 在 `_free_one_hand_slot_for_purchase()` 移除 `require_free_one`，调整 `still_needs_slot = (cap_after >= 10) or (not freed_by_cleanup and result.get('hand_count_after') is None)`：真实清理路径返回 `hand_count_after` 时 `<= 9/10` 绝不误入 `_sell_lineup_until_ready()`，同时保留对既有替身单测 `HandRecoveryTest`（`NOOP` 无 `hand_count_after` 与显式直调 `sell_lineup=True`）的兼容；docstring 注明 `_buy_shop_slot` 严禁传 `sell_lineup=True`。
  - `tests/test_chess_frame.py`（相对基线 `+278 / -6` 行）：在 `EquipmentAndHandCleanupTest` 新增 `_bind_real_buy_click_loop()`（绑定真实 `BaseTask.ui_click_until_disappear` 与可控假时钟）、更新 `test_both_pre_purchase_and_post_click_recovery_follow_same_priority_without_premature_lineup_sale` 并在其中与新增两条回归用例直接断言实际 `sell_hand_card` / `Press_and_Drag` / `_free_one_hand_slot_for_purchase` 次数及 `state['hand']`：
    - `test_buy_retry_continuous_failure_at_8_of_10_never_sells_and_exits_within_budget`：验证 8/10 初始手牌及「10->9 清理后降至 8/10」后连续点击未确认，均 0 次售卖、保留全部装备和式神，在 3 轮×3 次（9 次点击）预算内退出。
    - `test_buy_retry_post_click_confirmed_10_of_10_prioritizes_equipment_and_stops_at_9_without_selling_shikigami`：覆盖首次购后确认 10/10、已清理一轮后二轮再次 10/10 仍走统一顺序不直跳卖式神（先卖 `yinmoluo` 到 9/10 即停、0 卖式神并购卡成功），以及装备出售未确认中止保护。
  - `tests/test_chess_upstream_selective_merge.py`（相对基线 `+21 / -3` 行）：保持 `HandRecoveryTest` 7 项不动；在 `BuyShopSlotTest` 中将依赖「购后确认 10/10 才清理」的 3 项用例显式设 `_hand_capacity_count` 在首轮失败时为 `10`、`test_each_click_loop_is_capped_at_three_and_purchase_cancels` 更新为 `2/10` 有空位连续失败 9 次点击且 0 清理 0 卖卡，并新增 `test_free_space_after_pre_purchase_cleanup_never_triggers_lineup_sale`。
- **验证（D069 最小相关，未跑全量、未启动设备/游戏/服务）**：
  - 首轮守护运行 `EquipmentAndHandCleanupTest`（7）+ `BuyShopSlotTest`（11）+ `HandRecoveryTest`（7）共 25 项全部通过（88.748s，守护总耗时 92.3s，峰值 492 MiB，日志 `log/test_runs/related_20261125_155907_23840.log`）。
  - 审查日志发现 `BuyShopSlotTest::test_shop_reopen_failure_stops_without_more_clicks` 的 mock 在清理后仍返回 10/10 导致未测到重开失败分支，修正该用例 lambda 仅在 `cleanup_calls == 0` 时返回 `10` 并补充 `reopen_calls == 1` 断言后，复跑受影响分组 `BuyShopSlotTest`（11）+ `HandRecoveryTest`（7）共 18 项全部通过（0.070s，守护总耗时 3.6s，峰值 445 MiB，日志 `log/test_runs/related_20261125_160124_26012.log`）；4 个修改文件 `py_compile` 与 `git diff --check` 全部通过（退出码 0）。
  - **真机待验（Level C）**：真机对局中商店购卡失败时「手牌已 ≤9/10 不触发清理与不误卖阵容卡并在 3 轮内退出」「购后实屏仍 ≥10/10 按统一顺序清理并在 9/10 停下重试」，以及普通御魂拖拽出售真实响应。

## 2026-11-25 — 百鬼棋局装备分配与满仓清理

- 按用户批准顺序在 `tasks/Chess/runtime/hand_operations.py`、`tasks/Chess/runtime/economy.py` 与 `tests/test_chess_frame.py` 实施，完整保留既有 Chess 改动（含上卡人口交叉判断、小纸人判空、荒川直拖与左栏「荒川 ≥ 2」触发）、用户标注素材（`tasks/Chess/c/*`、`tasks/Chess/assets.py`）、公共 `module/`、`docs/CURRENT.md` 及其他预存 WIP；未改阵容配置格式、站位、金鱼查找搬运、商店与经济核心规则。
- **任务开始基线**（`master` @ `cbba5986ed23e62af3d16ee303a3e9ad1036c389`，副本与校验保存在 `C:\Users\cbz19\.gemini\antigravity\brain\0f2ca2de-294b-4d72-a661-c271baf9b9ca\scratch\baseline_equip_cleanup_20261125\`）：
  - `tasks/Chess/runtime/hand_operations.py` SHA256 `2663EE707DEBA67889D7DBDD05454FB715570CB008394E6995D94993C0EB3016`
  - `tasks/Chess/runtime/economy.py` SHA256 `ECAC774DEA3D8583C70E92B4F0BDE39FB470BF94AB1B65D7FF08DDC354387103`
  - `tests/test_chess_frame.py` SHA256 `AE81E646A599A73A95B951B82D46441584A7BA8364AA15B98440207BAF8D1C3F`
- **实际改动**：
  - `tasks/Chess/runtime/hand_operations.py`（相对基线 `+1044 / -409` 行）：
    - **实站位与目标筛选**：新增 `_registered_actual_position()` 与 `_verified_board_lineup_names()`，`_shikigami_name_at_set()`、`_hakuzosu_protect_target_position()`、`_golden_copy_targets()`、`_soul_targets()` 与 `_emblem_targets()` 统一以本局已登记 `_board_actual_positions`（1～12 且非 `_arakawa_goldfish_current_position`）为准（仅兼容未初始化 `_board_actual_positions` 的纯策略离线测试回落配置站位），自动跳过系统未核名格、无站位格与金鱼格；装备不再等待人口满员。
    - **指定优先 + 未上阵留够 + 通用分配**：新增 `_can_equip_soul_on_unit()`、`_soul_preferred_needing_units()`、`_soul_reserve_count()`、`_soul_generic_target_entries()`、`_soul_target_entries()` 与纹章对称 helper `_can_equip_emblem_on_unit()` / `_emblem_preferred_needing_units()` / `_emblem_reserve_count()` / `_emblem_generic_target_entries()` / `_emblem_target_entries()`；`_select_next_equipment_action()` 按「指定纹章 → 指定御魂 → 通用纹章 → 通用御魂」四层严格排序（指定对象无视通用前后排并走实际站位；未上阵指定对象按尚需张数预留，多出预留的同名副本才进入通用前排 1～6 功能 / 后排 7～12 输出分配）；新增 `_equip_selected_hand_equipment()` 与 `_soul_hand_cards()` 同帧 `(image_frame_id, id(image))` 缓存，`_hand_card_identity_count('soul', name)` 统一走 `_soul_hand_cards()` 多尺度识别口径；拖动后以同名手牌减少确认再写 `_record_shikigami_soul()`，单次未确认保留全部记录并 `self.screenshot()` 复查，不判槽满也不移除站位，不误卖有合法目标的纹章；守护之印与发现/复制卡保留独立流程。
    - **满仓逐张清理**：新增 `_protected_special_hand_x_positions()`、`_select_next_sellable_equipment_for_cleanup()`（先卖已识别、当前无合法目标且超预留的装备，排序为「同名多余普通御魂 → 无目标超预留纹章 → 单张无目标普通御魂」，跳过未知卡、预留阵容装备、守护之印、发现卡与黄金复制术）与 `_select_next_non_lineup_shikigami_for_cleanup()`（仅选已识别非阵容式神）。改造 `emergency_cleanup_hand()` 与 `_free_one_hand_slot_for_purchase()`：每次仅处理一张并重截统计 `_hand_capacity_count()`，达到 `<= 9/10` 立即停止；装备出售未确认或阶段/符咒/商店状态变化直接返回 `None` 中止、绝不跳卖式神；确认无可装/可卖装备且仍满时按日志原因进入先卖非阵容式神、再卖阵容手牌式神 `sell_one_lineup_hand_card()` 兜底（同样逐张停在 `<= 9/10`）并重开商店。完整记录装给谁、实际几号位、卖哪张、手牌数变化及进入卖式神原因。
  - `tasks/Chess/runtime/economy.py`（相对基线 `+42 / -12` 行）：`_buy_shop_slot()` 统一购前满仓检查（`>= 10`）与购后失败恢复两个入口，经 `_purchase_recovery_require_free_one` 区分「购前清到 `<= 9/10` 即放行」与「购后仍需再清一格」；购前不标记跳过后续优先级（除非购前已耗尽所有分支卖了阵容卡），购后恢复在手牌仍 `>= 10` 或首次购后恢复时均严守 `sell_lineup=False` 先走完整优先链，禁止跳过直接卖阵容卡。
  - `tests/test_chess_frame.py`（相对基线 `+686 / -0` 行）：新增 `EquipmentAndHandCleanupTest`（5 项，在 `setUpClass/tearDownClass` 将 `RuleImage.match_all_any` 接入 `FrameShim.runtime._match_all_any_payload` 离线执行），验证指定优先+无视前后排+未上阵留够与超额通用、实际前后排+跳系统/金鱼/预留槽+未满员可装+未确认保记录、`12/10` 全装到 `9/10` 与装 2+卖 1 超预留镜姬停在 `9/10` 且不卖式神、卖装备优先级/保护清单/出售未确认与切阶段中止及无装备时先非阵容后阵容兜底原因日志，以及购前+购后双入口一致与战阶段只卖不装流程。
- **验证（D069 最小相关，未跑全量、未启动设备/游戏/服务）**：
  - 守护运行 `tests.test_chess_frame`（`BoardScanTest` 15 + `ArakawaDirectDeployTest` 6 + `ArakawaGoldfishTriggerTest` 6 + `LineupCapacityStatusTest` 6 + `EquipmentAndHandCleanupTest` 5）+ `UpstreamRuntimePiecesTest`（6）+ `BuyShopSlotTest`（10）+ `HandRecoveryTest`（7）共 61 项全部通过（74.486s 测试耗时，守护总耗时 79.1s，峰值 554 MiB，日志 `log/test_runs/related_20261125_154149_29928.log`）；3 个修改文件 `py_compile` 与目标文件 `git diff --check` 通过。
  - **边界诚实说明**：普通御魂经既有 `sell_hand_card()`（拖向 `I_EXPERIENCE` 区域）出售的动作与数量减少确认在本轮仅通过合成帧/替身测试覆盖，尚无真机对局实拍证据，需在 Level C 真机实测确认。

## 2026-11-25 — 百鬼棋局普通备战关店帧上卡人口交叉判断

- 按用户批准方案在 `tasks/Chess/runtime/round_state.py`、`tasks/Chess/runtime/hand_operations.py` 与 `tests/test_chess_frame.py` 实施，完整保留既有 Chess 小纸人判空/荒川直拖/左栏荒川 `>= 2` 触发改动、用户标注素材（`tasks/Chess/c/*`、`tasks/Chess/assets.py`）、公共 `module/ocr/`、`docs/CURRENT.md` 及其他预存 WIP；未改动站位/金鱼查找与搬运/装备/卖卡/商店经济规则，也未逐格点开详情。
- **任务开始基线**（`master` @ `cbba5986ed23e62af3d16ee303a3e9ad1036c389`，基线文件副本与清单保存在 `C:\Users\cbz19\.gemini\antigravity\brain\0f2ca2de-294b-4d72-a661-c271baf9b9ca\scratch\baseline_lineup_capacity_20261125\`）：
  - `tasks/Chess/runtime/round_state.py` SHA256 `DB82D1623E18516B6F1E666B5F8FD22EAE054E0E4FB9E421872C916DE0E3A62F`
  - `tasks/Chess/runtime/hand_operations.py` SHA256 `0CA12048D4B7A93F4C7F334F5B1DEC33F36F5EA0AA0C2E028E1F770532610B9A`
  - `tests/test_chess_frame.py` SHA256 `41A6CF072B04B5B7E8EA223C5519D37284409E5416AAABC4978DD027781273A6`
- **实际改动**：
  - `tasks/Chess/runtime/round_state.py`：
    - 新增 `_evaluate_visual_lineup_capacity(self, level: int)`：在普通备战关店帧（`not self._is_boss_challenge_round()`、`self._is_preparation_mode()`、`not self._is_shop_open()`）同帧复用 `_read_board_position_count()` 与 `self._check_arakawa_bond_qualified()`；未激活荒川（`count_below_threshold`）预期占格 `level`，确认激活（`qualified`，含恰好 `2`）预期占格 `level + 1`（额外 1 格为金鱼，式神人口上限仍等于 `level`）；仅在棋盘扫描完整（`board_complete` 即 `unknown_positions == []`）且荒川状态明确时，按 `board_occupied == expected_occupied` 判 `full`（含系统自动补卡，无需逐格核名）、`board_occupied < level` 判 `not_full`；其余条件（`boss_round`、`not_preparation`、`shop_open`、`board_anchor_missing`、`board_incomplete`、`arakawa_sign_not_found`/`arakawa_count_unreadable` 等 `arakawa_state == 'unknown'`、`occupied_exceeds_expected`，以及荒川激活且 `board_occupied == level` 的 `arakawa_active_ambiguous_count`）一律记 `visual_state = 'unknown'`。
    - 改造 `_read_lineup_capacity_status(self)`：先通过 `_read_level()` 读取式神人口上限 `level`（`level is None` 时仍返回 `None`），`visual_state` 为 `'full'`/`'not_full'` 时采用 `source = 'board_visual'` 决定 `full`，为 `'unknown'` 时保留旧脚本登记口径并标明 `source = 'runtime_state_fallback'`、`fallback_to_runtime = True`（`current` 保持 `runtime_current`）；通过 `logger.info` 输出阶数、确认占格数及格位列表、未知格、荒川状态/数字/原始文本/原因、预期占格、`visual_state/visual_reason`、`full`、`source`（回退时带「新判定未知，改走旧判断」）与 `runtime_population`，同时保留并扩展兼容返回字典。
  - `tasks/Chess/runtime/hand_operations.py`：更新 `deploy_shikigami_from_hand()` 满员中止处的 `logger.warning`，通过 `.get(...)` 安全带出 `source`、`level`、`board_occupied/expected_occupied`、`unknown` 与 `arakawa(count)`；保持普通上阵调用链、回收顺序 `BOARD_RECALL_POSITIONS`、回收后重截 `self.screenshot()` 与重找手牌流程及阵容内荒川式神直拖分支全部不变。
  - `tests/test_chess_frame.py`：新增 `LineupCapacityStatusTest`（6 项），覆盖：① 六阶荒川未激活（1）且占 6 格、仅登记 5 个式神时 `board_visual` 判满员（无系统回收位中止且 0 拖拽；有 6 号系统位时先回收 6 号、重截重找后正常上阵；荒川卡仍走直拖）；② 六阶荒川恰好 `2` 且完整 7 占格（登记 5 只）判满员；③ 六阶荒川激活（2/3）但仅占 6 格时输出 `unknown`（`arakawa_active_ambiguous_count`）并按旧判断回退且日志包含全部要求字段与「改走旧判断」；④ 明确有空位（6 阶仅 5 占格，未激活与 `2` 激活，即便旧登记误记为 6 仍判未满）；⑤ 找不到荒川标识（普通阵容可继续上阵）、OCR `?`/空串、棋盘有未知格、占格超预期、缺棋盘锚点以及首领/非「备」/开店均安全回退旧判断（其中首领/非「备」/开店在禁用 OCR 下通过）；⑥ `_detect_pending_arakawa_goldfish()` 与 `_read_lineup_capacity_status()` 同帧复用左栏缓存仅调 1 次 `CHESS_ARAKAWA_SIGN_COUNT` OCR。
- **验证（D069 最小相关，未跑全量、未启动设备/游戏/服务）**：
  - 守护单测：`BoardScanTest`（15）+ `ArakawaDirectDeployTest`（6）+ `ArakawaGoldfishTriggerTest`（6）+ `LineupCapacityStatusTest`（6）共 33 项全部通过（20.9s，峰值 509 MiB，日志 `log/test_runs/related_20261125_150429_9168.log`）。
  - 静态检查：`toolkit\python.exe -m py_compile` 3 文件与目标文件 `git diff --check` 均通过（退出码 0）。
  - 本地 1280×720 原图进程内回放（绑定真实 `ChessRoundStateMixin._read_chess_mode`、启用 `toolkit/.paddlex` `TextSystem(model_size='medium')` 与 `ImageRuntime`、禁止 RPC/socket）：
    - `log/error/oas1_1795502821875/2026-11-24_14-47-01-270144.png`：`level=7`、`occupied=7 [2, 4, 5, 9, 10, 11, 12]`、`unknown=[3, 6]`、`arakawa=active(count=4, raw='4', reason=qualified)`、`expected_occupied=8` → `visual_state='unknown'`, `visual_reason='board_incomplete'`, `source='runtime_state_fallback'`, `full=False`。
    - `log/annotator/72e02b60c0c64443a52358760ba41205/uploads/1611c31e193146c5a422c5efd0588f6e_MuMu-20261124-152455-972.png`：`level=9`、`occupied=9 [2, 3, 4, 5, 6, 9, 10, 11, 12]`、`unknown=[8]`、`arakawa=active(count=7, raw='7', reason=qualified)`、`expected_occupied=10` → `visual_state='unknown'`, `visual_reason='board_incomplete'`, `source='runtime_state_fallback'`, `full=False`。
    - 说明：上述两张本地真实「备+关店」原图验证了真实 `LEVEL` OCR、荒川计数 OCR、阶数/占格/预期日志记录与含未知格时的安全回退；因两张图均存在未命中勾玉或小纸人的未知格（`[3, 6]` 与 `[8]`），完整 12 格扫描下的 `board_visual` 判满/未满尚无本地无未知格实图可覆盖，需真机实测。
- **真机待验（Level C）**：真机普通「备」关店稳定帧下完整 12 格 `board_visual` 判满（含系统自动补卡与荒川 `2` 多占 1 金鱼位）及 `occupied < level` 判未满、荒川激活占格等于阶数时的模糊回退、普通非荒川阵容找牌与回退日志、系统格回收与荒川直拖并存表现。

## 2026-11-25 — 百鬼棋局左栏「荒川 ≥ 2」触发金鱼查找与发拖前复核

- 按用户批准方案在 `tasks/Chess/runtime/settings.py`、`tasks/Chess/runtime/hand_operations.py` 与 `tests/test_chess_frame.py` 实施，完整保留用户标注规则与素材（`tasks/Chess/c/c_c_arakawa_sign.png`、`c_c_paper_1..3.png`、`tasks/Chess/c/image.json`、`tasks/Chess/assets.py`）、既有小纸人判空/荒川直拖改动、`CURRENT.md` 及其他预存 WIP；未改公共 `module/ocr/`；金鱼搜索顺序 `6 → 5 → 11 → 12` 留待下一步。
- **任务开始基线**（`master` @ `cbba5986ed23e62af3d16ee303a3e9ad1036c389`）：
  - `settings.py` SHA256 `0C93500D9DC7D0226EC68A1D4CDB8B48E63A721022713A8B1B8A9E9B3E3CD6A5`、`hand_operations.py` `502149E3B2245D29982B118A1708CF572F730BE797410D3FA1A1E6A2D9623D83`、`test_chess_frame.py` `08FB9EA9C2FDA0C86D6059EEEB7F29EFEA097BFFAA57E719F432ED38D73DFFA8`。
- **实际改动**：
  - `tasks/Chess/runtime/settings.py`：新增 `ARAKAWA_SIGN_COUNT_OFFSET = (14, 15)`、`ARAKAWA_SIGN_COUNT_SIZE = (12, 16)`、`ARAKAWA_SIGN_COUNT_UPSCALE = 3`、`ARAKAWA_GOLDFISH_MIN_COUNT = 2`。
  - `tasks/Chess/runtime/hand_operations.py`：新增 `_match_left_arakawa_sign()`（复用 `ChessAssets.I_C_ARAKAWA_SIGN` 的 `roi_back` 与 `threshold` 在左栏做灰度 `TM_CCOEFF_NORMED` 匹配）、`_ocr_arakawa_sign_count_raw()`（对 `(x + 14, y + 15, 12, 16)` 裁图以 `cv2.INTER_LINEAR` 放大 3 倍至 `36×48` 后，用 `RuleOcr(mode='Single', method='Default')` 读取原始文本，绕开公共 `Digit` 将 `?`/`？` 转为 `2` 的纠偏）、`_parse_arakawa_sign_count()`（仅接受纯 ASCII 数字，拒绝空串/问号/带杂字）、`_read_left_arakawa_bond_status()`（按 `(image_frame_id, id(image))` 同帧缓存复用）、`_check_arakawa_bond_qualified()`（准备阶段且商店收起后校验左栏 >= 2）及 `_is_confirmed_arakawa_goldfish()` / `_known_deployed_lineup_positions()`。
  - `_detect_pending_arakawa_goldfish()`：在查找前校验左栏条件；达标后即便脚本未登记两只荒川或没有 `_pending_goldfish_probe` 也可按当前帧确认占格（排除已知上阵格）进入查找，有快照时仍用快照过滤候选；未达标则 0 点击 0 拖拽，普通上阵流程照常。`deploy_shikigami_from_hand()` 与 `equip_emblems_from_hand()` 在上阵荒川卡或装备 `荒川纹章` 后即使无基准快照也会触发查找检查。
  - `_move_arakawa_goldfish()`：仅允许详情页确认 `I_CHECK_GOLDFISH`（「金鱼·助阵」，`identified=True`）的金鱼移动；正常查找、已排队补拖与 `_handle_goldfish_after_board_action_failure()` 均在发拖前关闭详情并复核当前帧左栏条件，失效时保留 `_goldfish_relocation_pending = True` 并 0 拖拽等待后续帧。
  - `tests/test_chess_frame.py`：新增 `ArakawaGoldfishTriggerTest`（6 项），覆盖灰度匹配+3 倍线性放大+同帧缓存、非「备」/弹窗/开店拒止、空串/`?`/`？`/杂字/`1` 门槛及公共 `Digit` 未变、不达标时查找与排队补拖 0 点击 0 拖拽且普通上阵继续、无快照与无两只荒川登记时由 `2` 触发系统凑齐查找、快照缩小候选，以及正常/排队/回收失败三条路径发拖前复核和未确认「金鱼·助阵」拒拖。
- **验证（D069 最小相关，未跑全量、未启动设备/游戏/服务）**：
  - 代码验证：守护运行 `tests.test_chess_frame.BoardScanTest`（15）+ `ArakawaDirectDeployTest`（6）+ `ArakawaGoldfishTriggerTest`（6）共 27 项全部通过（18.7s，峰值 522 MiB，日志 `log/test_runs/related_20261125_142837_30544.log`）；3 个改动文件 `py_compile` 与目标文件 `git diff --check` 通过。
  - 原图 OCR 验证（进程内本地 `toolkit/.paddlex` `TextSystem(model_size='medium')`，封死 RPC/socket）：
    - `log/annotator/72e02b60c0c64443a52358760ba41205/uploads/` 红色 `3`（6 张）命中 `(32, 110)` 分数 `1.0000`、`roi=(46, 125, 12, 16)` 原始文本 `'3'`（`0.9996~0.9997`）；金色 `7`（`MuMu-20261124-152455-972.png`）命中 `(32, 243)` 分数 `0.9331`、`roi=(46, 258, 12, 16)` 原始文本 `'7'`（`0.9980`），真实 `ChessRoundStateMixin._read_chess_mode` 下「备+关店」门控放行、`战` 帧拒止。
    - 仓库现存现场截图同步实测 `4`（`log/error/oas1_1795502821875/2026-11-24_14-47-01-*.png`：`pos=(32, 110)` 得分 `0.9717`，`raw='4'` 分数 `0.9999`，备+关店门控放行）与 `6`（`log/error/oas2_1795337044967/2026-11-22_16-44-04-*.png`：`pos=(32, 243)` 得分 `0.9200`，`raw='6'` 分数 `0.9999`，因真实阶段为 `战` 门控拒止）。
    - 缺项：仓库无 `1` 和 `2` 的真实 1280×720 原图，门槛已由定向单测验收，这两数字的真实图 OCR 仍待验。
  - 真机待验：恰好 `2` 只荒川触发与 `1` 只时不误触发的真实帧 OCR、系统自动凑齐二荒川查找金鱼、左栏临时被遮挡时延后至后续帧补拖，以及下一步金鱼搜索顺序 `6 → 5 → 11 → 12`。

## 2026-11-25 — 百鬼棋局阵容荒川式神直拖配置格与详情身份确认（试改）

- 按用户批准方案在 `tasks/Chess/runtime/hand_operations.py` 实施，完整保留既有小纸人判空改动、标注素材、工作区预存 WIP 及 `docs/CURRENT.md`。
- **任务开始基线**（`master` @ `cbba5986ed23e62af3d16ee303a3e9ad1036c389`）：
  - `hand_operations.py` SHA256 `173EAAC5...1D44C`、`frame_cards.py` `F10ADD60...9431`、`round_state.py` `DB82D162...A62F`、`settings.py` `0C93500D...D6A5`、`test_chess_frame.py` `103F033D...82E6`。
- **问题核对**（`log/2026-11-24_oas1.txt` L3817～3823）：旧流程选中 `荒川之主` 后先调用 `_recall_one_system_board_card()` 回收 6 号位，再拖向已占用的 10 号位，仅凭 `hand_count=1->0` 报成功且未核对 10 号实际式神（该日志可用于核对问题，无法证明满员替换成功）。
- **实际改动**（仅 `tasks/Chess/runtime/hand_operations.py` 与 `tests/test_chess_frame.py`）：
  - `deploy_shikigami_from_hand()`：在准备阶段且商店收起后，对命中 `_lineup_arakawa_names()` 的候选式神走直拖分支，跳过 `_recall_one_system_board_card()` 与 `capacity['full']` 拦截；无论目标配置格为空、占用或未知均允许尝试直拖一次；未确认到位时记录 `_pending_arakawa_deploy`、置 `_chess_deploy_needs_refresh = True` 并结束本轮上阵（不补回收、不重拖、不复用旧手牌坐标，下次进入上阵先 `self.screenshot()` 再找手牌）；非荒川式神完整沿用原流程。
  - `_deploy_arakawa_hand_card_direct()`：严格区分动作线索（手牌数/星级变化）与位置确认；拖后调用 `_inspect_board_set_shikigami()` 打开目标格详情（复用 `I_SHIKIGAMI_SPECIFICS` 与 `close_shikigami_specifics_if_open()`），调用 `_read_specifics_shikigami_identity()` 优先复用 `I_CHECK_GOLDFISH`（避免金鱼误匹配 `金鱼姬`）、`O_NAME_RANGE`（过滤 `I_SHIKIGAMI_SPECIFICS` 以下技能描述，头部为空时回退至锚定 `I_SHIKIGAMI_SPECIFICS` 上方的头部 `RuleOcr`）及 `resolve_shikigami` / `_fuzzy_text_match` 核对式神名；仅身份一致才登记站位（目标原为同名式神时确认站位并如实记录是否消耗手牌/升星）。
  - `_reconcile_displaced_slot_occupants()`：目标格确认新式神后，原占格记录按可验证画面处理（回手牌则移出棋盘登记；唯一新增占格且详情核对一致则迁至新格；去向无法验证则解除原格占用记录；若原格登记金鱼亦同步解除），避免两只式神同记一格。
  - 保留小纸人判空、普通卡回收、购卡、阵容权重与荒川金鱼原有触发/搜索/移动逻辑。
- **验证（D069 最小相关，未跑全量、未启动设备/游戏/服务）**：
  - 代码验证：守护运行 `tests.test_chess_frame.BoardScanTest`（15 项）+ `tests.test_chess_frame.ArakawaDirectDeployTest`（6 项）共 21 项全部通过（16.8s，峰值 498 MiB，日志 `log/test_runs/related_20261125_115115_24872.log`）；2 文件 `py_compile` 与 `git diff --check` 通过。
  - 原图回放：仓库当前无式神详情页原图，详情 OCR 与实机身份核对未做原图回放；另用现存 2026-11-24 关店准备帧 `log/error/oas1_1795502821875/2026-11-24_14-47-01-270144.png` 复核小纸人判空扫描（`1/7/8` 空 `0.871~0.979`、`2/4/5/9/10/11/12` 占、`3/6` 未知）。
  - 真机待验（首要）：满员拖入占用格时游戏实际行为（拒绝、合卡还是替换）及原格棋子去向，以及详情页头部 OCR 真实区域与命中率。

## 2026-11-24 — 福利道馆滑前锚点赏金图标前置校验

- 按用户批准方案修复 oas2 2026-11-24 20:46:34（`log/error/oas2_1795524394112/`）第 4 次上滑后滑前选锚点误判。修改前保存独立基线及现场原图副本于 `D:\Codex\workspace\oas-dokan-anchor-bounty-20261124\baseline`（`master` / `cbba5986ed23e62af3d16ee303a3e9ad1036c389`，开始时暂存 0、未暂存 118、未跟踪 43；全部预存 WIP、共享素材、`CURRENT.md` 与现场原图完整保留）。
- **改动**（仅 `tasks/Dokan/welfare.py` 与 `tests/test_dokan_welfare.py`）：
  - `tasks/Dokan/welfare.py`：新增局部常量 `ANCHOR_BOUNTY_X = 1125 - LIST_BOX[0]`、`ANCHOR_BOUNTY_DY = -30`、`ANCHOR_BOUNTY_X_PAD = 3`、`ANCHOR_BOUNTY_Y_PAD = 4`、`ANCHOR_BOUNTY_MATCH_MIN = 0.80` 及 `_bounty_icon_template()` / `_bounty_icon_score()`，复用既有 `DokanAssets.I_RIGHTPAD_POINT_BOUNTY`（27×29）做与 `_list_gray` 一致的灰度 `TM_CCOEFF_NORMED` 局部校验（不改共享资源属性/阈值及普通道馆代码）。调整 `_find_card_bar_edges()` 严格执行「找到疑似阶跃下沿 → 验证身份区域完整与赏金图标 → 排除相近重复候选（NMS）→ 从下往上返回」，确保底部仅露徽记的半张卡在 NMS 前被排除、不再挤掉上方完整卡；前后两帧匹配仍只用战力数字与馆名，名义 120px 手势、分差 `0.15`、静止容差 `±2px`、两次静止刷新、同帧找馆页复核、第二馆次数检查与滑前无锚点最多补拍一次/0 手势转人工均保持不变。滑前无锚点诊断日志补充赏金图标校验参数说明。
  - `tests/test_dokan_welfare.py`：在离线替身 `synthetic_card()` 对应位置绘入赏金图标；在 `ListProgressTest` 新增 3 项用例（基于已有真实裁图 `tests/fixtures/dokan_welfare/` 及明确标注的合成裁剪/位移/回弹），覆盖「底部无赏金图标半张卡不挤掉上方完整卡，合成 +218px 上滑继续、合成回弹与静止按两次确认到底刷新」「底部缺图标自动往上选完整卡、整屏无可靠锚点时滑前补拍一次仍失败留图转人工且 0 手势」「滑后遮盖赏金图标仍按馆名+数字匹配同卡」。
- **现场原图前后对照（`log/error/oas2_1795524394112/welfare_list_1_before_swipe.png` & `welfare_list_2_final.png`，RGB 读入同运行态）**：
  - 旧版（基线快照）：候选下沿 `[544, 340, 194, 47]`（`y=544` 挤掉 `y=486`），输出 `unknown (reason=ambiguous: anchor before_y=544 after_y=326 actual_dy=unknown, score=0.977 [pow=0.972 name=0.982], next=0.830, margin=0.147, self_next=0.809)`，与现场 `log.txt` 逐项一致。
  - 新版：`y=544` 赏金图标得分 `0.299`（`< 0.80`，在 NMS 前排除），`y=486` 得分 `0.967`（`>= 0.80`，保留），候选下沿 `[486, 340, 194, 47]`（滑后图亦同步排除 `y=326` 假下沿），输出 `moved (anchor before_y=486 after_y=268 actual_dy=+218px, score=0.971 [pow=0.978 name=0.963], next=0.362, margin=0.609, self_next=0.354)`。
- **离线验证（D069，未跑全量、未启动设备/游戏）**：`py_compile` 检查 `welfare.py` / `test_dokan_welfare.py` 与 `git diff --check` 通过；反向变异验证（临时旁路 `_bounty_icon_score`）使新用例稳定失败；守护运行 `ListProgressTest` / `SwipeProgressTest` / `SwipeRecordTest` / `RefreshClosureTest` / `SearchTest` 共 98 项全部通过（43.0s，峰值 556 MiB，日志 `log/test_runs/related_20261124_210940_1412.log`）。游戏内实测由用户自行验证。

## 2026-11-24 — 百鬼棋局普通准备阶段小纸人判空与未知格保护（第一步）

- 按用户批准的修订方案（含单次回收拖拽后变未知中止本轮上阵补充）实施百鬼棋局棋盘占位识别第一步，完整保留工作区既有用户标注素材（`tasks/Chess/c/c_c_paper_1..3.png`、`tasks/Chess/c/image.json`、`tasks/Chess/assets.py`）与其他预存 WIP，未修改 `docs/CURRENT.md`。
- **实际改动**（6 文件：`tasks/Chess/runtime/settings.py`、`frame_cards.py`、`round_state.py`、`hand_operations.py`、`tests/chess_support.py`、`tests/test_chess_frame.py`）：
  - `settings.py`：新增 `BOARD_EMPTY_PAPER_OFFSET = (-31, -26)` 与 `BOARD_EMPTY_PAPER_SIZE = (59, 55)`（对应 1 号位落点 `(377, 398)` → 搜索框 `(346, 372, 59, 55)`）。
  - `frame_cards.py`：`_board_frame_scan()` 保持单帧一次 `F_BOARD_OCCUPANCY / F_BOSS_BOARD_OCCUPANCY` 定位与 `(image_frame_id, id(image), boss)` 缓存，从同次 `frame.matched_ranges[12:24]` 计算 12 格落点 `(cx, cy)`；新增 `_can_confirm_board_empty_with_paper(boss)`（仅 `not boss` + `_is_preparation_mode()` + `not _is_shop_open()` 同时满足时启用）、`_board_empty_paper_rules()`（固定顺序 `I_C_PAPER_3 → I_C_PAPER_1 → I_C_PAPER_2`）与 `_match_board_paper_in_slot()`（达 `0.80` 即停）。普通回合启用门控满足时融合同帧勾玉与小纸人输出三态（仅勾玉=`occupied`、仅小纸人=`empty`、双无或同格冲突=`unknown` 且 `star=None`）；门控不满足（非「备」/ 符咒弹窗 / 开店遮挡帧）禁用小纸人判空，未命中勾玉一律记 `unknown`；首领回合保持原勾玉行为不变。
  - `round_state.py`：新增 `_board_set_state()`；`_board_set_has_shikigami_visual()` 仅认 `occupied`；`_board_set_is_empty()` 仅认 `empty`；`_reconcile_lineup_after_hyakki_round()` 改为仅确认空格时移除上阵记录，未知格与开店遮挡帧保留登记；`_read_board_position_count()` 锚点缺失返回 `None`，命中时补充 `empty_positions / unknown_positions / all_empty / complete`（仅 12 格全确认 `empty` 时 `all_empty=True`）。
  - `hand_operations.py`：`_recall_one_system_board_card()` 区分 `'not_found'` 与 `'unknown_after_drag'`（首格发出拖拽后等待超时或移金鱼后格态未知时不再重试拖拽、不再继续拖下一候选格，立即返回并标记 `unknown_after_drag`）；`deploy_shikigami_from_hand()` 遇到 `unknown_after_drag` 时结束本轮上阵尝试并置 `_chess_deploy_needs_refresh`，下次进入上阵流程时先 `self.screenshot()` 再找手牌，而 `'not_found'` 继续沿用原人口判断。`recall_all_board_cards()` 仅在 `all_empty=True` 时判整盘为空，按 `cleared_positions` 只移除已确认清空格子的登记（未知格保留记录），超时后非 `occupied` 不重复拖拽；两处金鱼移动后回收分支改为仅 `source_state == 'empty'` 才确认源格腾空，保留原有金鱼留在目标格分支。保留现有勾玉识别框、星级识别、阵容人口规则、首领回合、点击流程与金鱼触发/搜索/移动逻辑。
- **合成帧离线验证（D069，未跑全量、未启动设备/游戏）**：`FrameShim` 补入 `ChessEconomyMixin` 与 `chess_mode`，`tests.test_chess_frame.BoardScanTest` 15 项全部通过（12.8s，峰值 479 MiB，日志 `log/test_runs/related_20261124_204215_9864.log`），覆盖空/占/未知/同格冲突、3→1→2 顺序短路、12 格与锚点平移及格内位移、普通/备/关店门控与首领保留、计数与符咒后清点保护、金鱼移走后判空/留守/未知、批量回收保留未知登记与不重拖，以及「首格拖后变未知且下格确认有人时仅拖 1 次、本轮不上阵、下轮刷新手牌」针对性验收。6 个改动文件 `py_compile` 与 `git diff --check` 通过。
- **原图离线量测与改后回放状态**：
  - 改前只读量测（18:51，`log/annotator/fc73a41d014d47c285a3426ba8705ebb/uploads/` 三张样本）：商店收起帧 `152455-972.png` / `152456-674.png`（`I_REFRESH=0.0868`）表情锚点 `(154,498)` 匹配 `0.9999`，1/7 号位小纸人 `0.887~1.000` 命中、2~6 与 9~12 号位勾玉 `0.899~0.998` 命中，8 号金鱼位现有勾玉框 `(396,413,33,32)` 得分 `[0.193, 0.135, 0.096]`（漏检）且小纸人框 `(430,479,59,55)` 最高 `0.266~0.378`（未命中）；商店展开帧 `152455-285.png`（`I_REFRESH=1.0000`）6 号位勾玉被概率条遮挡至 `0.627`。另实查三张用户 PNG（`c_c_paper_1..3.png`）像素并不相同，分别精确对应三帧 1 号位。
  - 改后新入口实跑回放（20:44）：**未执行**——复查时 `log/annotator/fc73a41d014d47c285a3426ba8705ebb/uploads/` 已被外部清空，不以改前量测替代改后入口实跑通过；待用户重新提供原图即可补跑，真机实测亦待后续 Level C。

## 2026-11-23 — 福利道馆滑前补拍、滑后停稳与回退扫屏找馆页确认

- 基于已完成的单卡锚点滑动与第二馆次数检查，按用户批准方案在 `tasks/Dokan/welfare.py` 补齐找馆页身份确认。本轮基线：`D:\Codex\workspace\oas-dokan-page-recheck-20261123\baseline`，仅改动 `welfare.py`、`tests/test_dokan_welfare.py` 与受影响文档，未新增素材或修改公共组件。
- **实现**：抽离 `_find_page_flags()` / `_verify_find_page_on_current_frame()` / `_save_page_check_evidence()`，复用 `_await_refreshed_list()` 同组标志（`I_RYOU_DOKAN_FINDING_DOKAN` 且无 `I_RYOU_DOKAN_FOUND_DOKAN`、`I_REFRESH_ENSURE`），直接基于当前截图判断，不加固定等待、不补滑、不自动导航：
  - 滑前补拍第 2 张时，用第 2 张同一帧先确认找馆页；不通过则即便能匹配馆卡也记「`滑前补拍后无法确认找馆页，滑动未发出`」，按 `save_error` 留两张滑前图并转人工（0 手势、不计静止、不刷新）；
  - 首次停稳及补观察停稳后，均先确认找馆页再采信推进/静止或进入「鑫」回退扫屏；不通过则留滑前+当前停稳图转人工（不点候选、不计静止、不刷新、不清除滑动记录）；
  - 回退扫屏在 `_candidates` 扫「鑫」与 `_relocate` 点击前重新截图时，每次均用最新帧复核找馆页，不拿前一帧确认结果背书。
- **离线验证（D069，未跑全量、未启动设备/游戏）**：`py_compile` 检查 `welfare.py`、`test_dokan_welfare.py` 通过；守护运行 `ListProgressTest` + `SwipeProgressTest` + `SwipeRecordTest` + `SecondDokanCountRecheckTest` 共 66 项全部通过（31.6s，日志 `log/test_runs/related_20261123_221803_38032.log`），新增覆盖滑前补拍切页/刷新弹窗、首次及补观察停稳切页/刷新弹窗、回退扫屏与点击前重定位切页场景，并回归正常补拍/翻页/回退/刷新与第二馆次数检查。真机待用户实测。
- **独立审查后收尾（同帧绑定 + 旧替身签名修复，基线 `D:\Codex\workspace\oas-dokan-same-frame-closeout-20261123\baseline`）**：
  - `WelfareDokan._verify_find_page_on_current_frame()` 在通过校验后返回当前帧独立拷贝，`_swipe_list()` 在首次滑后停稳与补观察停稳两处均直接使用该返回值作为 `final` 传入 `list_progress()` 与 `_save_progress_evidence()`，保证页面确认、位移计算与诊断留图绑定同一张最后确认帧（`_settle_list()` 共用流程未改）。
  - 修复 `CandidateRecordTest.test_relocation_that_keeps_failing_is_bounded_and_clicks_nothing` 中 `_relocate` 测试替身签名以接受 `verify_find_page=False`，原限次停止与零点击断言保持不变（独立审查失败日志 `log/test_runs/related_20261123_222134_23292.log` 保留）。
  - 新增 `test_post_swipe_page_check_and_list_progress_use_the_exact_same_final_frame` 覆盖首次停稳与补观察两处较早落点帧与最后确认帧不同的场景。守护验证 `ListProgressTest` / `CandidateRecordTest` / `SwipeProgressTest` / `SwipeRecordTest` / `RefreshClosureTest` 共 86 项（`log/test_runs/related_20261123_222750_26608.log`，41.5s）85 通过、1 项因 `save_image` RGB/BGR 通道比较失败修正后复跑单项通过（`log/test_runs/related_20261123_222901_35180.log`，3.9s），2 文件编译通过。本轮福利道馆代码修改收尾，状态为「离线验证完成，待用户真机实测」。

## 2026-11-23 — 福利道馆第二馆前重读今日可挑战机会

- 按用户批准方案修改 `tasks/Dokan/welfare.py` 中 `WelfareDokan._run()`。本轮基线：`D:\Codex\workspace\oas-dokan-second-count-20261123\baseline`，保留既有未提交改动，仅修改 `welfare.py`、`tests/test_dokan_welfare.py` 与受影响文档。
- **行为**：第一馆放弃后沿用原投票、回庭院、120 秒等待与 `_back_to_find_page(after_rematch=True)`；确认回到找馆页后、进入第二馆的我方建馆检查与找馆前立即调用 `_read_count()`：
  - 读到 `1`：继续原第二馆流程；
  - 读到 `0`（含「今日已打完」）：直接 `return 0`，交由调用方按正常收尾写入次数，不进入第二馆，也不绕到末尾多读一次；
  - 读不到（`None`）：沿用 `_read_count()` 最多 6 次截图识别，仍读不到转人工，不进入第二馆、不把未知写成 `0`；
  - 读到 `2`：记录「投票时 1 次，回找馆页后 2 次」并转人工，不进入第二馆、不写入 `2`。
  - 第一馆进页检查、投票时「剩余 1 次」检查、正常完成后最终次数识别以及列表内刷新不额外读次数均保持不变。
- **离线验证（D069，未跑全量、未启动设备/游戏）**：`py_compile` 检查 `welfare.py`、`test_dokan_welfare.py` 通过；守护运行 `SecondDokanCountRecheckTest` + `CountTest` + `FlowTest` + `RematchReturnTest` 共 48 项全部通过（7.1s，日志 `log/test_runs/related_20261123_220509_36996.log`），覆盖回页读到 `1`、`0`（`COUNT_ZERO` / `COUNT_DONE`）、未知（6 次截图）、`2` 及列表内刷新不额外读次数。真机待用户实测。

## 2026-11-23 — 福利道馆发滑动前先取锚点（DOKAN-SWIPE-ANCHOR-01 补充修复）

- 基于 `DOKAN-SWIPE-ANCHOR-01` 成果，按用户批准方案补充「发手势前先取锚点」，避免先发滑动后才发现滑前图无可用参照卡。本轮独立基线：`D:\Codex\workspace\oas-dokan-pre-anchor-20261123\baseline`，仅改动 `tasks/Dokan/welfare.py`、`tests/test_dokan_welfare.py` 及受影响文档。
- **实现**：`WelfareDokan._swipe_list` 在关闭详情并确认找馆页后、发手势前新增 `_acquire_pre_swipe_anchor()`，调用现有 `extract_list_anchor()` 取最下方身份区完整的馆卡；第 1 张失败则在滑前补拍 1 次，第 2 张成功则以第 2 张及其锚点为基准只发 1 次名义 120px 上滑，`list_progress(..., anchor=anchor)` 复用滑前已取得的同一锚点计算位移；两张滑前图均失败时不发手势、不进 `_settle_list`、不计静止、不刷新，日志明确输出「`滑前锚点获取失败，滑动未发出`」，并按 `save_error` 一次性保存 `welfare_list_before_swipe_1.png` / `welfare_list_before_swipe_2.png` 与 `log.txt`（标明两张均为滑动前画面）后转人工。滑前有锚点但滑后识别失败继续沿用现有回退扫屏「鑫」与至多 1 次滑后补观察。
- **离线验证（D069，未跑全量、未启动设备/游戏）**：`py_compile` 检查 `welfare.py`、`test_dokan_welfare.py` 通过；守护运行 `ListProgressTest` + `SwipeProgressTest` + `SwipeRecordTest` 共 57 项全部通过（20.5s，日志 `log/test_runs/related_20261123_214622_36080.log`），新增覆盖四类场景（第 1 张有锚点、第 1 张无/第 2 张有、两张都无且按 `save_error` 开关留图、滑前有/滑后失败原回退照常）。实测待用户启动游戏验证。

## 2026-11-23 — 福利道馆单卡锚点滑动修复与缩短名义步长（DOKAN-SWIPE-ANCHOR-01）

- 按用户审核同意的 `DOKAN-SWIPE-ANCHOR-01` 局部方案实施。任务基线：`D:\Codex\workspace\oas-dokan-swipe-anchor-20261123\baseline`（`master` / `cbba5986ed23e62af3d16ee303a3e9ad1036c389`，开始时暂存 0、未暂存 108、未跟踪 49；`welfare.py` / `test_dokan_welfare.py` 的预存修改与快照已分离保存）。
- **手势资源**：仅将 `tasks/Dokan/res/swipe.json` 与 `tasks/Dokan/assets.py` 中 `dokan_welfare_list_up`（`S_DOKAN_WELFARE_LIST_UP`）的 `roiBack` 从 `1110,270,70,20` 改为 `1110,330,70,20`（中心 `(1145,460)->(1145,340)`，名义纵向位移 `120px`）；保留起点、横向范围、操控后端、记录名与普通道馆 `dokan_list_up`。日志分开记录名义手势与实际内容位移（250～280px 仅作现场观察目标，不作拒绝阈值或自动调参）。
- **单卡锚点推进与到底**：`tasks/Dokan/welfare.py` 沿用取消反向回顶与两层停稳确认；滑动前关闭详情并确认仍在找馆页，从新鲜基准帧取最下方身份区（深色战力条亮字 + 米白馆名暗字）完整且本屏唯一的馆卡（不要求带「鑫」），以高通战力数字带与馆名带做 OpenCV `TM_CCOEFF_NORMED` 刚体模板匹配计算 `dy = 滑前 y - 滑后 y`（避开徽记、右上角标动画、金圆图标与外边框；不再由旧整列 `poor_match` 否决）。唯一同卡可信上移（`dy > 2`）判 `moved`、清疑似到底并仅释放 `dokan_welfare_list_up` 记录；`|dy| <= 2` 判 `static`（保留记录，记疑似到底，连续 2 次可靠静止才交原刷新）；`dy < -2` 判 `wrong_direction`（`unknown`）。
- **未知回退扫描与隔离**：停稳后 `unknown`（锚点缺失/裁切/反向/歧义/无可用锚点）先按现有逻辑扫完当前屏「鑫」，找到合格候选直接开馆，否则至多补 1 次只截图观察（`SWIPE_UNKNOWN_OBSERVES=1`，不再发手势），仍未知按 `save_error` 一次性保存滑前图、最后停稳图与 `log.txt` 后转人工；未知不计静止、保留滑动记录，并清除未知前的疑似到底状态，禁止与未知后结果拼成到底确认。
- **离线验证（D069 最小相关，未跑全量、未启动设备/游戏）**：`py_compile` 检查 `welfare.py` / `assets.py` / `test_dokan_welfare.py` 通过。守护首轮运行 `ListProgressTest` / `SwipeProgressTest` / `SwipeRecordTest` / `SwipeResourceTest` / `SearchTest` / `RefreshClosureTest` / `ListHoldTest` 共 118 项（`log/test_runs/related_20261123_205141_9276.log`，50.5s），115 通过、3 项测试构造问题修正后复跑 `ListProgressTest` 17 项通过（`related_20261123_205406_37160.log`，6.9s）；补充验证 `FlowTest` + `CandidateRecordTest` 24 项通过（`related_20261123_205424_38264.log`，7.4s），基于仓库真实列表裁图与明确标注的合成位移/回弹/馆卡。真实运行、120px 手势实际位移与真机到底行为待用户实测。

## 2026-11-23 — 同心之兰好友页连续弹窗及意外恢复

- 用户批准扩大后的局部方案，并回复「可以」确认实施及其他写入会话停写。开始基线：`D:/Codex/workspace/oas-xinlan-popup-20261123-090617`；master / `cbba5986ed23e62af3d16ee303a3e9ad1036c389`，开始 105 项已跟踪修改、39 项未跟踪、暂存 0，全部预存 WIP 保留。
- 好友列表复位、展开、详情核名、福袋入口受阻时处理连续羁绊提示，并调用公共未知页关闭逻辑后重新导航核名。羁绊连续处理有 8 秒时限，好友定位/福袋入口各有 30 秒循环上限（嵌套导航另受原有超时约束）；关闭福袋最多试两次，避免持续盲点。无法识别关闭入口则有界失败，沿用同步核心和调度收尾，不承诺任意新弹窗均能关闭。
- 本任务的默认关闭列表复用公共返回、关闭、跳过动作，移除通用确认和探索退出确认。每个导航动作重新截图检查绑定邀请；适配器普通点击也避让绑定邀请。未知页恢复不通用关闭福袋或绑定邀请，接受仍走原有对端名字核对；互赠意图、次数和配置未改。
- 相关离线用例共 80 项分组验证：既有 69 项通过；加入恢复用例后 79 项中 2 项失败（抽象基类测试构造错误、展开失败未接恢复），修正后 12 项针对复跑通过；新增福袋中途遮挡及加强真实公共关闭链路后 2 项验证通过。合并证据覆盖 80 个不同用例，未进行一次性 80 项完整重跑或全量测试。四个改动 Python 文件编译通过。
- 守护日志：`log/test_runs/related_20261123_090727_26908.log`（69 通过）、`related_20261123_090846_19612.log`（保留失败证据）、`related_20261123_090910_27048.log`（12 通过）、`related_20261123_090953_26908.log`（2 通过）。真实设备/游戏未启动，未修改截图或 OCR 规则，真实弹窗恢复与后端加载均待验证。
- 最终增加导航前先清理连续提示，避免一开始就被公共未知页的同动作去重限制截断；17 项好友定位与恢复场景复跑通过，日志 `log/test_runs/related_20261123_091153_25136.log`。本轮增量差异检查通过；全仓 `git diff --check` 仍有预存素材文件尾随空白等问题，未修改无关 WIP。

## 2026-11-21 — 首领退治集结结束后交接战斗

- oas1 真机已点开启和勋章确认并到达集结。旧流程把集结误判为迟到，识别到灰色「退治」后连点至保护中止。按用户确认，进入退治页后等待 185 秒，优先识别自动进入的准备或战斗页。只有仍在首领退治页且原按钮规则相符、按钮金色亮起时点一次。已有战斗画面则跳过准备。进战观察设 15 秒上限，单次退治点击后重计该上限。
- 8 项局部测试通过，修改亮态返回值后针对进战 4 项复跑通过。两张灰态与四张金色亮态原图通过模板及色差回放，灰态无点击，自动进战和准备由局部流程模拟，真实交接待验。基线与亮态原图在 D:/Codex/workspace/oas-demon-retreat-gather-20261121。

## 2026-11-21 — 秘闻无编号关卡恢复勾玉兜底

- oas2 山兔竞速关卡标题无层号，旧流程跳过所有候选，反复滑动后由设备保护中止。按用户指定顺序，先确认同一卡片未通关，保留标题层号优先判定，无编号时读取该行勾玉，只有 7～70 的 7 的整数倍才判层。原战斗、加成、结算与排期不变。
- 19 项局部守护用例及编译通过。3 张山兔事故原图均读出 49、56、63、70，分别对应第 7～10 层；原图均为未解锁，回放没有选关点击。实际未通关卡片选中待真机验证。基线在 D:/Codex/workspace/oas-secret-jade-fallback-20261121。

## 2026-11-21 — 首领退治周六主动开启

- 「首领退治时间」新增默认关闭的主动开启开关。启用后周六到配置时间，沿用游戏当前难度，识别用户标注的开启按钮与明确的勋章确认框，提交一次后等待退治页。点击入口后换帧判定，原换御魂、参战、领奖和排期逻辑保留。
- 4 项局部守护用例通过。标注器开启页和确认弹窗两张原图通过实际图片匹配及内置 OCR 回放。真机提交和进入集结待验证。标注与原图基线在 D:/Codex/workspace/oas-demon-retreat-20261121。

## 2026-11-20 — 每周购买与公共调度日志中文化试点

用户批准先试点。每周购买的千物宝箱、神龛、寮商店和杂货铺调整 19 处运行日志文案，公共调度调整 6 处启动、跳过重启、重新调度和任务起止提示。保留日志级别、动态参数、触发时机、输出格式及人工接管关键词。5 个源码文件通过编译和改前字节对照，2 项相关调度用例通过。未启动 OAS 或设备，运行中的界面显示未核对。

## 2026-11-20 — 结界寄养 / 挂卡插入御魂轮换的结果兼容

事故：两实例完成第一批御魂后分别执行结界寄养；寄养成功排期仅传 `target`，轮换收到未知结果后以 `unknown_task_result:KekkaiUtilize` 停止。用户批准寄养与挂卡先接入统一结果，已确认安排重试时轮换先继续，挂卡原立即重试排期不改。新增独立任务结果 `completed` / `retry_scheduled`：本次确有排期记录、内存和磁盘时间一致才报告，`TaskEnd` 后由 Script 交给轮换；只允许这两个任务的同名结果生效，异常、未确认写入、未知结果和显式失败不放行。挂卡未找到卡的立即重试仍可能优先于轮换下一步调度。保留全部实例设置与排期公式。局部真实任务出口 / 轮换测试、真实配置文件排期、相关调度与旧功能回归通过；设备和双实例未测，旧失败循环不自动恢复。基线 `D:\Codex\workspace\oas-kekkai-loop-outcome-20261120`。

## 2026-11-20 — 御魂轮换进度日志

用户批准在御魂→个人突破轮换的队长侧，每次有效计数后记录轮次、已完成 / 目标与剩余场数；继续使用现有可信计数，不改计数、调度和队员行为。守护入口运行 `TrustedCountTest` 9 项通过，覆盖到达目标、残留结算、未确认场次和队员不输出；编译通过。未重启正在运行的实例，运行中的旧进程是否加载改动未验证。基线 `D:\Codex\workspace\oas-loop-progress-log-20261120`。

## 2026-11-20 — 永生之海金币加成

用户批准金币 50% / 100% 独立开关，默认关闭；进入任务前在庭院复用 GeneralBuff 识别加成状态，确认关闭才开启并记录，原已开启的保留；正常返回庭院后只关闭本次记录项。未找到或状态不明确时告警并跳过；任务开始时已在战斗中跳过设置，异常中断不保证恢复。队长、队员、单人共用入口，不修改实例配置。7 项局部测试通过（含旧配置兼容、分别与同时开启、三种身份、原先开启、识别不明确、战斗中启动、开启失败），编译及模板 JSON 检查通过；真实识别与游戏状态未验证。基线 `D:\Codex\workspace\oas-eternity-gold-20261120`。

## 2026-11-20 — 御魂数字切换支持第八组

用户批准并确认其他会话和标注器停写。沿用用户新增的 `sou_group_8` 点击区域 `(1087,578,156,47)`，数字模式组号扩展至 1～8，继续沿用原分组两次点击和队伍选择；更新通用配置提示，不改实例配置。守护入口运行数字模式测试 35 项通过，新增第 1～7 组映射回归后仅复跑第八组测试类 3 项通过；语法和 JSON 静态检查通过。分组是否真实选中、列表回顶后的区域是否准确以及最终装配效果均未真机验证。基线 `D:\Codex\workspace\oas-soul-group8-20261120`。

## 2026-11-18 — 悬赏列表进度备用窄条

用户确认旧执行者停写并批准保留原窄条、失败后再用标签顶部上方22像素、高28像素的备用窄条；两者均无法可靠读取仍按原未确定路径处理。oas1 真实截图的 1/2 原框漏检，备用框进程内离线 OCR 可读；旧截图 1/14、1/3 仍可读。局部测试首轮60项中2项旧调用次数断言失败，修正断言后仅复跑两项均通过；真实截图用例首轮通过，编译通过。未进行真机验证；任务前基线 `D:\Codex\workspace\oas-wq-progress-20261118\baseline`。

## 2026-11-13 — 超鬼王末票召唤等待

用户批准调整当前队列流程：已有挑战按钮优先挑战；召唤前确认无票才结束；点击召唤后等待挑战按钮，继续处理确认弹窗和战斗准备画面，不因过渡期间无票而结束；原30秒总限内未确认则抛页面异常。局部兼容性测试8项通过，编译通过；未进行真机验证。基线 `D:\Codex\workspace\oas-summon-wait\20261113-baseline-130245`。

## 2026-11-12 — 开发前需求确认与方案审核（D070）

用户明确要求每次开发前问清问题、定具体方案并由用户审核后再实施。同步AGENTS、CLAUDE、oas-architect入口及接力资料；同一已批准方案内不重复审批，超范围先确认。本轮为规则与文档变更，按D069做静态检查，不执行业务测试或全量。

本文档按时间追加重要开发记录，不覆盖历史。只记录代码修改、merge、重要审查、测试和重大技术决策，不记录每一次搜索、单条命令或无意义探索。

## 2026-11-12 — 超鬼王疲劳恢复至60再调度

- 用户批准按1点/分钟、目标60加1分钟缓冲；关闭自动茶时适用，OCR异常或矛盾沿用设置间隔。弹窗关闭后fresh截图；保留自动茶及其他配置。
- 3项针对性测试和编译通过，未跑全量或设备；基线 `D:\Codex\workspace\oas-fatigue-60\20261112-688e94ca\baseline`。

## 2026-11-12 — 超鬼王准备页卡住的局部交接修复

- 根据oas2两次错误日志及实际准备页截图，当前队列召唤后可能已进入准备页，却仍等待强力开关。按用户批准最小方案增加准备/战斗正向交接、强力等待15秒/60轮上限，保留原功能和配置。
- 针对性兼容测试6项及编译通过；全量和真机未运行。本轮开始内容基线：`D:\Codex\workspace\oas-prepare-fix\20261112-4febd9b6`。

## 2026-11-12 — 纠正超鬼王功能删减，修改验证默认（D069）

- 将“只用战斗”误扩大为删流程/隐藏配置，现已撤回；恢复原功能与设置，保留截图适配，当前队列作为默认关闭的可选项。未覆盖用户实际配置文件。
- 纯循环38项模拟测试撤出发现目录并归档，保留3项素材检查；3项兼容性检查通过，素材/兼容共6项约5秒。无全量、无设备运行。
- AGENTS/CLAUDE/TESTING/Skill统一最小验证、普通局部120秒、全量显式批准；真实画面和已授权短实测优先。输出：`D:\Codex\outputs\oas-metademon-restore\20261112-03dd0a93`。

## 2026-11-12 — 超鬼王按当前队列循环召唤、喝茶与战斗（MD-LOOP-01）

- 用户先提出只要战斗，最终明确不重新选星、先手动清高星，剩余直接召唤→战斗→结算直到无鬼王，并要求自动消耗茶。原选星方案被最新要求替代；未把高星过滤/OCR扩进任务。
- 删除任务私有选票、合成、换魂与倍率切换调用；不再读旧50场/45分钟上限；旧配置保留但在API隐藏。自动茶仅发既有喝茶点击，需疲劳下降确认，不做购买。
- 标题识别与鬼王入口分离；挑战旧图在本期实拍上匹配约0.476，现从同一原图精确裁出；复制用户已标注入口建立独立规则。保存来源指纹；旧挑战原图从HEAD读出并与任务开始SHA一致后补入基线副本，未回写仓库旧文件，其他用户标注原样保护。
- 新循环与入口、配置API、FIRE/登记护栏验证中。初轮新组因random_delay导入路径错误导致循环测试未加载，修正后相关112项OK；扩展组发现新FIRE owner漏登记，已补精确元组，结果和原日志均保留。最终相关/全量结果见AI_CONTEXT §7与CURRENT。
- 开始基线4142文件、77已跟踪修改/31未跟踪；输出`D:\Codex\outputs\oas-metademon-loop\20261112-f3c790a1`。未启动设备或服务，未真实消耗茶，未提交。
- 最终验证：相关160项OK（循环38、入口27）、编译通过；首轮4128项OK后，自审补迟到结算缓存分支，旧分支受控对照失败、新分支回归通过；最终全量4129项PASS，skipped=6，退出码0。本轮空白检查通过，全仓保留既有DailyTrifles生成注释尾空格。Level C NOT_TESTED，未真实消耗茶。

## 2026-11-11 — 超鬼王庭院直达入口重构（MD-ENTRY-01）

- 用户要求活动入口与式神活动同方式；替换旧活动列表进入/返回连接，改为庭院直达，独立两入口、NAVIGATION新帧确认、右侧栏目有界查找。未改活动内部玩法或共享导航。
- 基线：master/cbba5986，开始61已跟踪修改、28未跟踪、暂存0；所有脏文件及修改目标备份，4139文件指纹。保留用户本轮已标注的式神活动两PNG、JSON、assets；入口素材只复制到超鬼王独立文件并留来源。
- 新增26项入口回归，新增点击登记3处（2 NAVIGATION、1即时栏目查找），同步精确统计。MetaDemon assets由生成器单模块生成，再自动去尾空格；资源护栏比较生成器AST及JSON/PNG/属性配套，未改生成器。
- 验证：开始全量4064项OK、skipped=6；首轮相关239项中1项旧policy总数断言未同步（102应为104），已补精确计数，日志保留，最终相关/全量结论另记CURRENT与AI_CONTEXT §7。
- 证据：`D:\Codex\outputs\oas-metademon-entry\20261111-450be2cb`；原文基线：`D:\Codex\workspace\oas-metademon-entry\20261111-450be2cb\baseline`。未启动设备、游戏或OCR，未提交；本期入口目标和主页/鬼王页模板仍待Level C。
- 最终结果：相关239项OK；编译通过；全量4090项1失败、skipped=6（既有守护中断用例`MARK-0`时序断言），同源独立复核FAIL，全量失败保留、不重跑整组。入口自审PASS，全量门禁FAIL，Level C NOT_TESTED。

## 2026-11-05 - AB-NAME-01 地鬼空名优先挑战及匿名成功计数

- 用户指出此前空名即跳过会漏打，明确“宁可出现之前那种重复打也不要漏”。本轮Codex按该优先级修正局部分支，D066部分取代D062旧门槛。
- 空名继续既有已上榜／挑战流程；可靠名字仍判重，未知身份实际胜利单列匿名次数，失败／结果不明及未知名字此前已上榜不新增完成。目标按可靠名字数与匿名成功次数之和收口，汇总明确可能重复，保留原战败与排期规则。
- 先建新策略回归，旧实现13项运行10处失败并保留原输出；修正后13项通过。64项地鬼相关、四个Python文件compileall及最终受守护全量4064项OK（skipped=6），守护退出0且清理确认。Codex在CURRENT25单独进入reviewing后自审，最终26登记离线通过与真机待验。
- 首轮全量04运行4064项，5处失败、6项跳过：4处为移除空名跳过关闭调用后的登记依赖未同步，1处为守护中断测试子进程首条输出缺失。同步登记册及C0固定数量断言；守护中断用例单独复查通过，但未证明历史失败根因已解决。06补充命令误列不存在模块，109项实际用例通过并有1项模块导入错误，保留该失败记录。最终07全量对修正后的组合重新验证，原日志均保留。
- 业务源码仅tasks/AreaBoss/script_task.py、boss_result.py局部改变，配套distinct测试及调用点登记册、C0数量断言同步。两份原始故障日志和开始内容均保存，原福利交付、公共OCR、资源、配置和其他WIP受保护；未启动设备或执行Git写入。
- 当前实现解除空名的挑战门槛，名字OCR空结果底层原因仍未解决，排名反向判断风险沿用；真实游戏是否按预期打满与日志收口待Level C。完整证据见`D:\Codex\outputs\oas-phase5-area-boss-name\20261105-114758`，开始基线见`D:\Codex\workspace\oas-phase5-area-boss-name\20261105-114758\baseline`。

## 2026-11-05 - DOKAN-LIST-01 Claude停写后Codex接管、离线验证与自审

- 用户要求Claude无法继续时由Codex接管，并确认Claude已停止写入。原合同、任务B0与接管B1分别保留。交接后仅福利源码和对应测试有内容变化，当前Git仍master／cbba5986ed23e62af3d16ee303a3e9ad1036c389，全部预存WIP受保护。
- Claude已完成取消例行回顶、结构位移判断及局部回归，保存两次失败运行。323项运行9处失败属当时缓冲断言；接管时当前组合再验6处失败，均与1.0／1.3及等待分段断言有关。Codex保留Claude业务源码，将测试改为检查仅sleep及累计1.3秒，并修正缓冲异常注入；未改用户1.3及业务等待。
- 39项缓冲／集结／流程专项、410项相关回归通过，编译通过。旧任务源码的零回顶、亮度变化假推进、稀疏小位移三场景均失败，最终组合均通过，原文件未被替换。
- 单轮受守护全量4059项通过，skipped=6，守护退出0、清理确认；未重跑第二轮全量，未启动设备或执行Git写入。完整命令、输出与摘要见`D:\Codex\outputs\oas-phase5-dokan-list\20261105-092558\codex-takeover\20261105-104853\tests`。
- Codex在实施后单独进入reviewing，从原合同与最终增量自审，明确该审查方式。D046实施状态及D065局部推进判据同步，AI_CONTEXT §4.181和ROADMAP列明离线完成与真机待验，CURRENT21→22→23。
- 本任务离线范围PASS，用户审核及真实游戏Level C待完成。阈值仅有历史截图裁剪和合成回归依据，本轮没有确认当前设备连续帧根因。地鬼需求与其他范围未自动开展。
- 接管报告和保护记录见`D:\Codex\outputs\oas-phase5-dokan-list\20261105-092558\codex-takeover\20261105-104853`，Claude原失败证据保留，原任务增量与Codex接管增量分别保存。预存DailyTrifles尾空白单列，未为刷绿修改。

## 2026-11-05 - Phase5首项福利找馆方案与Claude任务包

- 用户确认福利道馆刚进入和刷新后都已在顶部，要求取消回顶；到底仍继续滑动或触发重复操作保护。用户指定Codex架构指导Claude实施，并确认welfare.py和对应测试停止其他写入，选择由用户在Claude独立对话执行。
- 源码确认_find_and_open刷新后必调_scroll_list_to_top，两次static才确认在顶；初次入口当前直接扫描。11月4日oas1日志27次刷新对应54次实际反向滑动，21:21:31.179至21:21:36.217一例额外约5秒。
- _swipe_list目前以变化行覆盖0.65判断推进，存在动画假推进及稀疏列表漏推进风险，不能仅据静态代码认定本次现场具体误判根因。方案保留落点确认，增加可信内容位移／静止／未知区分和有界复核，保留公共保护与定向记录释放。
- D046补记替代用户已确认的旧回顶假设，其余福利规则和用户1.3缓冲保持。Claude仅修改tasks/Dokan/welfare.py与tests/test_dokan_welfare.py，更新旧回顶假设测试并补充具体回归，Codex统一维护项目文档。
- CURRENT revision19→20，DOKAN-LIST-01方案和手工交接包就绪；业务源码、测试和设备均未执行修改／运行，业务验证及Codex最终验收待Claude报告。地鬼具体需求仍待提供。
- 任务包与分析证据见`D:\Codex\outputs\oas-phase5-dokan-list\20261105-092558`，源码开始副本与保护清单见`D:\Codex\workspace\oas-phase5-dokan-list\20261105-092558\baseline`，生效交接清单见`D:\Codex\workspace\oas-phase5-dokan-list\20261105-092558\handoff\manifest.json`。全部预存WIP和历史报告受保护。

## 2026-11-05 - Phase5授权与试运行任务准备

- 用户明确可以开始Phase5，并同意当前优化后置，随后说明要改道馆和地鬼，具体文件不确定。阶段授权已取得，具体业务问题、期望及用户自改／Phase5分工待澄清。
- 当前映射为tasks/Dokan与tasks/AreaBoss；本轮只定位目录及现有测试，不实施业务修改。用户可持续自行修改，双方按文件和公共依赖协调，重叠文件先交接写入权。准备观察快照不能替代未来业务任务开始基线。
- CURRENT revision18→19，生命周期planning，Phase4收尾PASS保留，Phase5已授权并处于准备，真实任务实施／验证／验收未执行。Codex负责需求及最终审查，Claude默认实施。
- 本轮局部同步四份状态文档，原始Phase4报告、历史FAIL与WIP保留。准备授权及基线见`D:\Codex\workspace\oas-architect-phase5-preparation\20261105-091125`，交付见`D:\Codex\outputs\oas-architect-phase5-preparation\20261105-091125`。

## 2026-11-05 - Phase4 V1.2收尾审核

- 用户要求开始Phase4收尾审核。主控曾实施，本轮按批准合同、D064、TESTING §8及原始证据单独复核，另有06独立审查会话作为证据。
- 01／02普通恢复与预算提醒及03至07五角色共7/7指定独立场景PASS，55次调用均配对完整。04限实施准备和权限说明，真实业务实施与Claude协作未执行。五角色证据见`D:\Codex\outputs\oas-architect-v12-role-review\20261105-085310`。
- 当前实现与受测快照匹配，三批64项交付清单及889份历史材料核验一致。13/13工具针对性历史结果保持有效，本轮未重跑业务测试或全量；执行了frontmatter、六角色、链接、入口共同核心、Python AST、批准合同、快照及增量保护静态核验。
- 03至07共45次工具返回719695 Unicode码点，16次带截断标记，后续必要信息已交付。读取效率与重读作为非阻断优化项，当前批准标准采用普通预算提醒。
- 旧V4.2.5 FAIL、旧T12 PARTIAL及原始失败记录保留，T9未触发条件性显式回退仍NOT_TESTED。旧六份源日志差异待核实，01／02源SHA已变但归档仍匹配登记且各23条消息／调用／返回payload一致，功能PASS依据归档，本轮不推断变化来源。
- CURRENT revision17→18，登记Phase4的V1.2批准范围收尾审核PASS。生命周期awaiting_approval，实施完成、七场景及静态验证通过、技术验收PASS与待用户确认分别记录，Phase5未授权未开始。
- 本轮仅局部同步CURRENT、AI_CONTEXT、DEVELOP_LOG、ROADMAP，其他文档负责的长期规则及业务架构事实未变。完整收尾证据与保护结果见`D:\Codex\outputs\oas-architect-phase4-closeout\20261105-090006`，新测开始基线见`D:\Codex\workspace\oas-architect-phase4-closeout\20261105-090006\baseline`。

## 2026-11-04 - V1.2两项普通恢复独立复测通过登记

- 用户批准同步两项PASS、保留原始日志和旧FAIL，并列清剩余角色。CURRENT实际revision16→17，完整受测正文仍对应revision16，17为本轮结果登记。
- 普通恢复会话01a1a6ad-4bd1-7801-95d4-3a8502414d65，原日志`C:\Users\cbz19\.codex\sessions\2026\11\04\rollout-2026-11-04T21-08-57-01a1a6ad-4bd1-7801-95d4-3a8502414d65.jsonl`，SHA 41bf56db83a288926297f99962b2c8c72f5b9e074290bafbfc1ed9e96b48a855。5次工具调用，完整返回32828码点，最大单次16275，必要Git／CURRENT／授权和下一步已恢复，V1.2普通恢复PASS。
- 预算提醒会话01a1a6ad-9001-7870-982d-7ff6eb9af701，原日志`C:\Users\cbz19\.codex\sessions\2026\11\04\rollout-2026-11-04T21-09-15-01a1a6ad-9001-7870-982d-7ff6eb9af701.jsonl`，SHA 76b0964032b16bb46167dd9a9c6cbc5ddf711b29276f2aa0be021f311c016687。5次工具调用，完整返回46294码点，最大单次26149。17052明确为场景输入，提醒后继续必要读取，V1.2预算提醒回归PASS。精确接收量与脚本局部估算分别记录。
- 两份日志无截断、缺失输出或重复call_id。主控核对实际调用与完整CURRENT正文，记录普通恢复只读边界。读取记忆过宽、重复记忆、全文查看辅助脚本及宽章节索引列为优化项，按V1.2普通预算提醒规则判断。
- 需求与架构、代码实施准备、故障分析、审查验收、交接文档五角色仍待独立复测。04只验证准备和权限，实际业务实施另需真实任务授权。
- 原始日志、V1.1历史FAIL／T12 PARTIAL和既有证据保留。本轮证据登记见`D:\Codex\outputs\oas-architect-v12\20261104-213053-retest-sync-828cf`，开始副本见`D:\Codex\workspace\oas-architect-v12\20261104-213053-retest-sync-828cf\baseline`。Phase4未完成，Phase5未授权未开始。
- 收尾比较使用较早日志基线，发现六份旧会话现况指纹不同，变化时间和来源无法由现有比较确认。差异与当前副本单独保存，原始路径仅作读取，本次两份复测日志及副本指纹一致。详细记录见本轮historical-log-fingerprint-differences.json。

## 2026-11-04 - OAS Architect V1.2 简化方案实施

- 用户批准六角色、普通恢复预算提醒、严格验收独立触发，保护WIP和历史证据，范围限Skill与治理文档。开始master／cbba5986ed23e62af3d16ee303a3e9ad1036c389，57已跟踪修改／27未跟踪／暂存0，84份dirty副本和4,138指纹见`D:\Codex\workspace\oas-architect-v12\20261104-203832-v1_2-22593\baseline`。
- V4.2.5原始对话17052码点、单次12902，旧合同预算FAIL，当前任务正文未取得。原始合同和失败记录保留，新普通恢复按V1.2单独验证。
- 普通脚本改为可选status，输出Git和CURRENT可读摘要，未知字段保留，真实失败局部报告。spent／remaining旧参数作为提醒，正文继续交付。宿主记忆复用会话结果，角色按本轮请求选择。
- 旧严格代码复制到oas_strict.py并加显式--strict入口，保留历史行为以供旧合同快照兼容。主Skill保留ASCII和标准YAML中文转义兼容，表格列出六角色，中文职责在按需reference。此目录细节由本轮实施选择确定。
- 当前CURRENT原83字段全文按原字节保存并绑定SHA，整理为八组当前信息，revision15→16。D064记录批准的流程调整，AGENTS／CLAUDE共同核心一致。六份项目知识按受影响事实同步，运行架构无变化。
- 针对性验证、静态检查、受控恢复与完整保护结果见`D:\Codex\outputs\oas-architect-v12\20261104-203832-v1_2-22593`。独立新对话由用户执行，历史T1/T10/T11/T14保留未重跑，T9 NOT_TESTED，旧T12 PARTIAL，Phase4未完成，Phase5未授权未开始。

## 2026-11-04 - OAS Architect V1.1：V4.2.4复核与V4.2.5首次加载整改

- 用户批准“开始继续修改”。开始master／cbba5986ed23e62af3d16ee303a3e9ad1036c389，57已跟踪修改／27未跟踪／暂存0；CURRENT revision14→15。84份dirty副本和4,138文件指纹保护，八文件范围，原始日志／报告／基线保留。
- V4.2.4独立会话01a1a5fb-93dd-7cd1-bd28-94e2b2fb8423实收四次1834／2425／2480／181，共6920码点，预算PASS而内容FAIL。首个Get-Content -Raw未指定UTF8导致乱码，entry重复加载Skill；bootstrap --remaining2500拒绝预计4971的交付。脚本内部读源不代表Agent收到正文，L1及接收桥接未执行；不能将2500当真实剩余额度。原日志SHA b161b8c933b505cdf8ce37d2ef1a550f62f72a2608cb4db540d7dc996f90c65f保留。
- 首读兼容检查发现BOM会被现有quick_validate拒绝，未采用BOM或修改全局编码。将主Skill改为501字节ASCII发现引导，中文YAML值用标准转义保存，中文架构职责完整移入现有context-loading；entry同缓存加载职责和必要规则，不再单独调用rules，也不重复返回入口正文。发现入口在entry只核raw指纹作内容绑定，明确为元数据读取；知识源仍只读一次，不把发现绑定伪称知识正文零I/O。
- L0预留发现1300／entry5200／bootstrap5500，总12000，不扩预算。bootstrap默认使用预留；若自填remaining必须给spent依据，校验在Git／CURRENT读源前完成。额外成本按12000-spent收紧，不自动忽略用户上限或扩大预算。消费桥接、未知字段、WIP保护和必要L1保持。
- 仓库外22项初检通过，覆盖真实字段、原始9977及本轮6920不同失败、默认PowerShell首读和中文YAML、入口正文不重复、中文知识一次读取、无依据remaining前置拒绝及真实spent收紧。最终部署回放／保护核验见本轮证据；不宣称新独立对话通过。
- 仅现有Skill入口／context-loading／读取器及必要文档，无业务源码／测试／资源、AGENTS／CLAUDE／其他references或全局配置改动，用户Dokan1.3保留。不执行业务测试／compileall、设备或Git写入。T1/T10/T11/T14历史PASS保留未重跑，T9 NOT_TESTED，T12 PARTIAL、Phase4未完成、Phase5未授权未开始；交付复测材料后停止。

## 2026-11-04 - OAS Architect V1.1：V4.2.3复核与V4.2.4启动编排整改

- 用户批准“开始着手下一步修复”。实际master／cbba5986ed23e62af3d16ee303a3e9ad1036c389，57已跟踪修改／27未跟踪／暂存0；CURRENT revision13→14。84份dirty副本和4,138文件指纹受保护，八文件范围，原报告及基线不覆盖。
- 原始V4.2.3会话01a1a576-07ce-7851-96c6-b4f4c40d3992复算三次返回2592／9977／2364，共14933码点；单次9977硬超，L0超软未超15000硬限，整体FAIL。记忆正文2245＋7269，有搜索／固定行窗重叠；Git、CURRENT、必要L1未执行。Skill／rules实际正文及来源SHA匹配，不能据此认定Agent已做实收核验。原始日志SHA 71618e5913406cabe4ddf1ea2b3b5e4e700ea5c46c10c1fef543a35ed02dfd13保留。
- 修复重点从局部解析器转为启动编排：entry在宿主要求时只带一次完整定向记忆命中及正文，不改宿主要求／全局记忆；rules后bootstrap合并Git／CURRENT，减少调用包装。L0涵盖前置成本、整个返回、回执和包装；不返回完整exec对象，不合并多个大正文。
- 接收桥接将实际工具返回文本交verify，核SHA／长度／计划／尾标，不重开源补hash；缓存缺失或完整注入场景如实列未核实，不冒充完整通过。materials合并合同／快照核验，已读源全复用实收SHA；必要L1仍包括四份任务知识，不删设计依据。
- 仓库外18项针对性初检通过：保留既有解析／Git／权限／证据覆盖，增加定向记忆无旧事实、实收破坏、原始9977整次硬超复核、延迟回执与整次预算。初始配额rules2600不足预计3094，调整entry／rules分配，总预算未扩展；最终部署回放和静态结果见本轮证据。
- 仅现有Skill／读取器与必要文档增量；业务源码／测试／资源、用户Dokan1.3、AGENTS／CLAUDE／其他references及全局配置不改。不运行业务测试／compileall、设备服务或Git写入。新独立对话未执行；旧T1/T10/T11/T14 PASS保留未重跑，T9 NOT_TESTED，T12 PARTIAL，Phase4未完成，Phase5未授权未开始。交付复测材料后停止。

## 2026-11-04 - OAS Architect V1.1：V4.2.2失败复核与V4.2.3执行入口整改

- 用户批准“你开始着手解决这轮发现的问题”。开始master／cbba5986ed23e62af3d16ee303a3e9ad1036c389，57个已跟踪修改、26个未跟踪文件、暂存为空。CURRENT revision12→13；83份dirty副本、4,137文件指纹及历史证据保留，基线见CURRENT。新增同Skill只读辅助脚本为本轮明确披露的实现选择，不伪称旧合同原文；不改变业务架构／D063。
- V4.2.2真实独立会话01a1a536-d1a1-7030-b758-4b431cd1d79a三次完整返回2854/4864/432，共8150码点，预算内但CURRENT STOP且body_delivered=false，未完成A～E／必要L1，整体FAIL。8587只是未发送内容估算，不是实收超限；LF规范化后正文SHA核对可成立。Git未加untracked-files=all，21条目录记录不能代表26个文件；首次PS管道的中文规划文字亦有乱码，不能据此断言源文件损坏。
- 原外部模型没有部署给恢复会话，Agent临时重写解析器，规则未形成确定入口。本轮在同一Skill增加scripts/oas_context.py：冷启动skill及rules/git/current固定模式，动态原键／值／章节／源行账本、可逆路径缩写，只有已解释历史字段用引用；未知保留、重复／超长／预算不足停读。源同次缓存，正文LF后取SHA，实收长度／摘要／尾标独立核验。
- Git只回当前身份与六项整数，使用一次porcelain v1 -z --untracked-files=all，R/C消费旧路径。knowledge core按当前任务提取四份必要知识；合同核SHA及当前权限，快照按真实schema核内容，已读来源复用实收SHA，空匹配不通过。脚本只读，不创建状态／缓存文件或导入业务模块。
- 仓库外14项针对性测试覆盖真实CURRENT、未知键／围栏／重复、路径回解、缓存、实收破坏／UTF8、预算拒绝、Git完整文件计数及删除／重命名／冲突、精确任务列表、合同／证据、非PTY。初轮13/14，规则预算2828失败；第二轮2808仍失败，均保留。压缩重复规则及元数据表达后14/14通过；最终内容的静态／受控实收及保护核验另见本轮证据，不代表新VSCode对话通过。
- 仅七份文档局部增量和一个Skill脚本；用户Dokan1.3、业务源码／测试／资源及原日志／报告／基线不动。无业务测试／compileall、设备服务、Git写入。旧T1/T10/T11/T14 PASS及T9 NOT_TESTED保留未重跑；T12 PARTIAL、Phase4未完成、Phase5未授权未开始；交付V4.2.3独立复测材料后停止。

## 2026-11-04 - OAS Architect V1.1：V4.2.1失败复核与V4.2.2最小整改

- 用户批准“开始下一步整改”并确认旧会话停写，由本会话接管；保存83份dirty内容、Git差异/index及124份旧材料指纹，未枚举其他worktree或计算全仓SHA。开始CURRENT revision10，接管为11；合同和开始副本在`D:\Codex\workspace\oas-architect-v422-remediation-20261104\baseline`。
- V4.2.1原始前缀1–81行SHA `4bcc14bd2fa34da1d3173fc7b991c3a0b46b03957dcab7761d09b051bc7b9a9d`保留；9调用L0=24582、L1=11693、总=36275、最大单次11734，硬超FAIL。仅复核已结束片段，不混本轮调用，且不是另一独立会话外审。失败细节、逐call_id和层级依据见`D:\Codex\outputs\oas-architect-t12-remediation\20261104-v4_2_2-remediation\V4.2.1-已结束片段审查.json`。
- 非PTY标准执行会关闭stdin，不采用常驻stdin/base64链；规则改为单源同次缓存、必要输出，放不下即停。最终正文先变换/LF，再计算UTF8摘要；接收侧从实际文本复算。预算按最终码点及包装/错误预留，跨软目标前停读，保持默认上限。
- 按旧快照实际project_files[path].after_sha256与unchanged_entries核实12项均匹配；旧空匹配为解析不适配，不据此抹除证据。合同核SHA并摘录关键授权，历史字段仍缓存/引用、未知项保留待解释。
- 仓库外模型和Q1–Q12针对性结果、生产者预算估算、非PTY宿主探针、静态/增量/WIP核对见`D:\Codex\outputs\oas-architect-t12-remediation\20261104-v4_2_2-remediation`。早期失败另存，不冒充新Agent通过，不运行OAS业务测试/compileall或设备服务。
- 七文件局部增量；运行架构与D063不变；原日志/报告/基线及用户Dokan1.3保留。T12 PARTIAL、Phase4未完成、Phase5未授权未开始；交付新独立复测材料即停。


- 补充验证：初次Q11因L0估算12091拒绝；中间规划因L1估算10337拒绝，均未扩预算。消除重复元数据、历史引用按源行和同缓存账本呈现，并将小型必要材料合并返回后Q1–Q12通过。未知baseline样式新字段仍须正文待解释，不能因名字像历史字段而隐藏。非PTY受控返回按实际文本复算通过；CURRENT实际10→11→12。最终快照变化后重新执行针对性检查，结果见交付目录。

- 收尾发现写入助手统一了部分既有混合换行，已按开始副本逐行恢复未修改内容的原换行，仅保留本轮文本增量；静态核验曾误将预存第107行当纯空白，已改为与开始原行精确比对，初次诊断保留。

## 2026-11-04 - OAS Architect V1.1：T12 V4.2.1动态恢复定点整改

- 实时master／cbba5986ed23e62af3d16ee303a3e9ad1036c389，57个已跟踪修改、26个未跟踪、暂存为空。CURRENT开始revision9及SHA 40f0bd2146a9c0046105c27abc9c563518048c4ae432f423271d8009642e001d与原证据一致；主／整改／V4.2合同SHA均核对。本轮用户任务覆盖必要七文件及外部材料，未授独立复测或Phase5。实际9→10。
- 原V4.2会话01a1a49d-43cc-7683-b4a7-902b88d2becb复算7次完整返回3724/431/1360/5898/373/1804/441，总14031；工具发现1360、错误警告和包装全部计入，软FAIL硬PASS。原日志SHA 782564b5df569b89ee8f62a976efcb142a12fbf87bf7f4b2d5437ced1871995a保留。源有76字段、8个二级章节；108正文行／计末尾空行109，非漂移。
- PS采用严格UTF8及BitConverter兼容hex，同raw计算SHA；正文实收与hash分记，不为补hash重读。使用现有工具，不再为Node查目录；标题／列表／SHA／摘录用同一缓存。
- 动态模型保留原键／原值／章节／行及新增未知项；A～E覆盖合同、权限、实施、验证／失效、验收／风险和交接。短名仅显示压缩，路径别名可逆；非关键历史仅可追溯引用，不筛23项或只回8项。context保留全部关键规则并按真实标题取必要节，不删除知识。
- 初次路径别名数字边界验证失败，原代码／记录保留，改明确分隔符后逐字段无损还原。R1–R12初轮11/12，预算12077失败；任务状态同步后第二轮12026仍失败，记录不覆盖。收束重复规则、精确审计口径引用既有TESTING §8后12/12通过；旧V4.2基准12项回放通过，仅基准兼容参考，非新Agent行为证明。最终CURRENT快照另作预算／字段覆盖补充核验。
- 开始83份dirty副本／4,137指纹见 `D:\Codex\workspace\oas-architect-t12-remediation\20261104-121333-v4_2_1-107a6\baseline`；用户Dokan1.3、预存源码／测试／资源、原T1/T12日志与历史基线／报告保护。本轮仅七文件局部增量，ARCHITECTURE／DECISIONS／入口不改。
- 输出 `D:\Codex\outputs\oas-architect-t12-remediation\20261104-121333-v4_2_1-107a6`；独立材料在隔离通过后生成，本轮未创建或执行新VSCode会话，无业务测试／compileall、设备服务、Git写入或全局配置修改。T12 PARTIAL，Phase4未完成，Phase5未授权未开始。

- 收尾增量空白检查发现本轮reference新增EOF空行（exit3），失败输出保留；局部移除该空行后重新核验，未触碰业务预存空白问题。

## 2026-11-03 - OAS Architect V1.1：T12 V4.2最小整改与复测准备

- 实时master／cbba5986ed23e62af3d16ee303a3e9ad1036c389，57个已跟踪修改、26个未跟踪、暂存为空，CURRENT实际8→9。开始83份dirty副本和4,137指纹见 `D:\Codex\workspace\oas-architect-t12-remediation\20261103-231517-v4_2-015a5\baseline`，业务WIP／用户Dokan1.3保护。
- V4.1原会话01a1a1b9-30b1-7ea1-88cc-462f6d48b2f7复核，源SHA 956a99befad059a1935661d7c792768f3808bbefcdc4e9f43e66394f39fc899b。任务书旧值L0/L1/L2为13872/1171/187、总15230、最大5194；现有外审器块间单LF口径为13879/1172/188、总15239、最大5195。9调用各多1个LF；Git Python调用形式旧分类器漏识别，先保留未分类结果，再有依据映射L0。两种口径均硬通过、L0软失败，旧数／原报告不改。
- 只补首读完整接收元数据、Windows文件／stdout UTF8、CURRENT单次解析全部白名单及失败字段补修；当前验收独立核对ROADMAP列表和TESTING §8。通用层级表／条件尾部按触发加载，不删除规则，不宣称未读内容完整。
- 原V4.1 20项兼容回归通过；新增首轮11/12，L0夹具估算12594超过软目标，原代码／输入／失败结果保留。按本轮任务更新CURRENT并改精确规则入口后，新增12/12通过，估算11917（非实测）；最终状态更新的快照另作预算核验。例行L1定位脚本一度因正则转义失败，未返回正文，修正后成功，未修改业务文件。
- 隔离仅仓库外参考模型，不是Agent强制执行器，不等同VSCode通过；原外审器和旧20项源码／报告不改。本轮输出 `D:\Codex\outputs\oas-architect-t12-remediation\20261103-231517-v4_2-015a5`，T12 PARTIAL，Phase4未完成，Phase5未授权未开始。
- 独立V4.2提示只在隔离通过后生成，由用户执行；本轮无VSCode新对话、OAS测试／compileall、设备服务、Git写入或全局配置修改。

## 2026-11-03 - OAS Architect V1.1：T12-V4.1定点整改与独立复测准备

- V4原会话01a1a174-e96c-7201-b40b-356d284e8a38重新只读审计：7调用，L0 17,113／L1 3,872／L2 0，总20,985；首返回10,742，L0超2,113、首返回超2,742。原日志SHA 3a2b23a6203ebc148a0ca8916b142ea6a8926631aba4ebdbd3861e0138cc2ca6保留。两处既有OAS输出根未发现持久化V4报告，任务书旧审计数值与本轮原日志重算一致。
- 首调用合并Git、六worktree、SKILL和完整CURRENT；内部stdout已10,132，不能把超限全归因包装。规则在第二次才加载，第一次没有生产者预检；max_output_tokens不是字符预算。V4最大可解码包装／转义差值610，本轮预留至少640；第二次6,118也超建议目标但未超硬限。
- 修改主Skill发现描述及前置约束，先独立加载Skill再读规则与CURRENT字段；普通恢复禁止Worktree枚举，Git只标量，CURRENT白名单＋源行号并显式阶段。成功只回stdout，输出前含元数据预检／超建议范围分块；UTF8、标题／长表、去重、截断检测和会话外JSONL审计保留。压缩Skill与reference重复措辞，未精简知识库；最终夹具计划含每次640预留，L0估算11,927、单次最大5,607，仅为静态模型，非真实会话。
- 仓库外20项夹具通过，内含原JSONL审计器20项夹具回归；当前协议副本可完整读取，缺块／缺尾标记／摘要变更不标完整。参考模型测试不是部署执行器，更不是真实VSCode行为通过。原审计器及历史20项结果未改。
- CURRENT实际7→8；T12仍PARTIAL，待V4.1独立复测和原JSONL外审，Phase4未完成，Phase5未授权未开始。开始83份dirty副本／4,137指纹见 `D:\Codex\workspace\oas-architect-t12-remediation\20261103-210449-v4_1-94e88\baseline`；本轮七文件局部增量，其余WIP、用户Dokan1.3、原始日志及历史报告保护。
- 输出 `D:\Codex\outputs\oas-architect-t12-remediation\20261103-210449-v4_1-94e88`；只在夹具通过后生成独立提示，由用户执行。本轮无独立会话、OAS业务测试／compileall、设备服务、Git写入或全局配置修改。

## 2026-11-03 - OAS Architect V1.1：T12-V3定点整改与V4准备

- 原V3会话01a1a0c1-7431-7191-9dfb-8e8026b40f88已用原JSONL独立重审：15调用，L0 24,089／L1 3,987／L2 261，总28,337，最大单次5,889；无截断／缺失／未分类／重复call_id。L0超过该次明确批准的23,000共1,089，不能将该历史扩展带到V4。
- 末次内部计量1,502，之前L0 22,587仅余413；首次计量326，CURRENT两段6,908、元数据3,577、范围计划579和末尾版本／Git1,189也构成浪费。普通恢复改最小字段／行号、Git最小摘要，取消内部完整计量及默认末尾七文件复核；保留已通过UTF8／定位／去重／截断机制及专项WIP审计。
- 硬预算保持15k/12k/5k/32k；内部软目标12k/9.6k/4k/25.6k。解码命令可复算最大包装／转义开销410，预留至少512，不以r.output.length自证完整宿主量。
- 独立标准库审计器和隔离测试位于 `D:\Codex\outputs\oas-architect-t12-remediation\20261103-201523-v3-v4-98fe3`，拒绝OAS项目路径，不执行日志代码，原日志SHA保持；17项后补项目路径拒绝为18项，再补计量特征为19项，最后补两种宿主截断标记，最终20/20 PASS；运行记录均保留，最终结果为JSONL审计测试结果-release.json。最初CLI JSON参数被PowerShell去引号导致解析失败，改外部limits文件后成功；非审计数值变化。
- CURRENT实际6→7，T12仍PARTIAL等待V4；外审工具通过不是V4通过。原始保护基线 `D:\Codex\workspace\oas-architect-t12-remediation\20261103-201523-v3-v4-98fe3\baseline`，Dokan用户1.3与业务／测试／资源、入口及历史报告保留。
- V4提示只在隔离通过后生成，由用户独立新会话执行、主控会话外审计；本轮不执行V4、不运行OAS unittest／compileall／设备或Git写入，Phase4未完成，Phase5未授权未开始。

## 2026-11-03 - OAS Architect V1.1：T12第二轮整改与V3准备

- 用户确认T1独立会话01a1a03a-847d-7f83-8806-422b85bfcdb6已PASS；本机原JSONL存在并核对SHA，不重跑、不改AGENTS／CLAUDE／SKILL自动发现入口。T10/T11/T14既有PASS、T9 NOT_TESTED保留。
- 审核T12原会话01a1a052-f948-7640-949c-8cb81e54c4cc：81记录、10调用，完整工具文本91,099字符；内部命令口径82,418另记，含原会话重建的首次5,990，不能混为Token。乱码重读、错误章节／表格定位、截断误报完整、默认全仓审计和宽Memory搜索证据保留。
- context-loading局部补首次UTF8／元数据正文去重、准确六级标题、当前短列表和可靠表格、完整返回硬限额、接收后分块完整性、A普通恢复/B专项审计及定向历史检索。临时解析器和计量程序在仓库外，不加项目辅助工具。
- 隔离覆盖A标题、B表格、C编码、D预算、E截断／缺块、F Git标量；最终32项PASS。首次31项有1项夹具预期结束行误写，失败已保留，修正后31项PASS；随后增加每块文件／范围验证为32项PASS。实际模型新对话未执行，不能宣称T12通过。
- 原始基线 `D:\Codex\workspace\oas-architect-t12-remediation\20261103-160143-85963\baseline` 保存83份dirty副本与4,137指纹；Dokan用户1.3保留。输出 `D:\Codex\outputs\oas-architect-t12-remediation\20261103-160143-85963`，包含问题映射、隔离记录、预算口径和V3提示。
- CURRENT按实际5→6更新，保持awaiting_approval、实施完成／验证部分通过／待审核；T12仍PARTIAL等待第三轮独立复测，Phase4未完成，Phase5未授权未开始。无OAS unittest／compileall、服务／设备、UI／Claude启动或Git写入。

## 2026-11-02 - OAS Architect V1.1：T11用户修改归属复核与人工补测准备

- 原始T11按范围外内容完全不变检查为FAIL，记录Dokan缓冲常量1.0→1.25→1.3，当时未取得归属依据；原报告／JSON／基线保持原样，不回填历史通过。
- 用户本轮明确确认两次修改均为本人操作、不属于Skill建设任务，也未要求恢复。实际核对三个历史版本与当前1.3，除该常量外其余字节一致，Agent编辑日志不含welfare.py。
- 原77份WIP、Phase0～3的13份交付、原21个未跟踪、8份Phase4整改文件和其余保护内容均核验，无其他未解释变化。T11现复核为PASS：用户主动修改造成的预期WIP漂移，保护机制正常识别并保留；不代表所有并发写入场景通过。
- 本轮只增量修改CURRENT、AI_CONTEXT、本日志和ROADMAP；CURRENT按实际4→5递增，保留OAS-SKILL-V1／V1.1，awaiting_approval／整改实施完成／验证部分通过／待用户审核。
- 新交付 `D:\Codex\outputs\oas-architect-phase4-remediation\20261102-220531-t11-review-0b2b1`，包含独立T11复核JSON／MD、报告复核版、T1与T12人工提示及操作说明。两项仍BLOCKED，T9 NOT_TESTED；本轮没有尝试UI、启动CLI、执行新会话或业务测试，T10/T14仅保留既有PASS。
- welfare.py用户修改完整保留，未改源码／测试／资源、Skill、ARCHITECTURE、DECISIONS或TESTING；没有Git写入。Phase4仍待实际人工补测，Phase5未授权、未开始，交付后停止。

## 2026-11-02 - OAS Architect Skill V1.1：Phase4整改与针对性复测

- 用户批准方案A，限T10严格只读、T12读取策略、针对性复测及必要文档同步；Phase5未授权、未开始，不改业务／测试／资源、全局Claude配置，不做Git写入。
- 整改前实际为master／cbba5986ed23e62af3d16ee303a3e9ad1036c389，57个已跟踪修改、26个未跟踪、暂存为空、6个worktree；83份dirty副本及4,137文件指纹保存在 `D:\Codex\workspace\oas-architect-phase4-remediation-baseline\20261102-202827-f94679`。原Phase0和Phase4全部证据继续保护。
- 增量调整context-loading的字符预算、长行字段摘录及去重；task-handoff区分READONLY-V1与正常授权开发；主Skill将初始建设范围改为从CURRENT和最新授权定位阶段。
- T10：CLI 2.1.248改用safe-mode/restricted/dontAsk，实际工具仅Read/Glob/Grep；5次Read、0写入尝试，调用结果配对完整，输入文件、测试期间OAS及用户Claude目录内容不变，PASS。临时配置和日志在仓库外，未改生产权限；旧Plan Mode写入尝试原证据保留，不以被拒当通过。
- T12/T1：Windows UI自动化native pipe不可用，轻量重试及运行时重置均失败，新独立会话未能创建，均BLOCKED；人工提示词已提供，不用当前对话或历史T1替代。T14仅做停写未知的只读轻量回归PASS。T11范围外不变性FAIL：检测到tasks/Dokan/welfare.py常量1.0→1.25的来源未明漂移，已保存前后指纹和差异，不纳入整改、不覆盖或回滚；五份待同步文档仍匹配开始内容后才进行增量同步。T9仍NOT_TESTED，未重跑其他全部用例。
- 证据 `D:\Codex\outputs\oas-architect-phase4-remediation\20261102-202827-f94679`；CURRENT从实际revision 2递增到3，保持awaiting_approval／实施完成／验证部分通过／待验收。T12策略改善尚未得到新会话证明，Phase4不宣称全部通过。
- 逐份同步AI_CONTEXT、ROADMAP、TESTING与本日志；ARCHITECTURE无运行架构变化不改，DECISIONS无新ADR不改。未运行OAS业务测试或compileall，既有DailyTrifles/assets.py:107空白保留。
- 交付前再次观测到同一Dokan常量1.25→1.3，保存第二份快照与差异；不声称其稳定，不覆盖或回滚。CURRENT按实际3→4再记检查点，T11仍FAIL，其他验收结论不因持续漂移改为通过。

## 2026-11-02 - OAS Architect Skill V1.1：Phase 0～3 建设（后续协作验收未执行）

### 授权与保护

- 用户正式任务书批准 Codex 直接实施 Phase 0～3，不交 Claude；Phase 4～5、业务修改、设备、测试运行、Git 写入均不在本轮范围。
- 实时基线：master／`cbba5986ed23e62af3d16ee303a3e9ad1036c389`，56 个已跟踪修改、21 个未跟踪文件、暂存为空，6 个登记 worktree。全部 77 个变更文件的内容与 SHA-256、HEAD 二进制差异及暂存差异已保存并核对；这些是预存 WIP，不属于本 Skill 任务增量。
- 基线：`D:\Codex\workspace\oas-architect-skill-v1-baseline`，完整清单与快照见 `manifest.json`、`snapshot/`，复制校验见 `baseline-verification.json`；未修改其他 worktree。

### 实施

- 新建 `.agents/skills/oas-architect/SKILL.md` 与三个 references；`.gitignore` 仅开放目标 Skill 及必要父目录，其他本地 Agent 内容继续忽略。
- 双入口局部增加角色路由、渐进读取和相同的共同核心补充，原有六条核心与收尾规则保留；AI_CONTEXT 同步恢复入口与定位策略，ROADMAP 记录本任务阶段，DECISIONS 追加 D063，TESTING 增加 §8。
- 创建 `docs/CURRENT.md`，保存 `OAS-SKILL-V1`／V1.1 合同、实际 worktree、基线、范围和三个状态；交付后等待用户审核 Phase 4，不把静态交付写成完整任务验收。
- ARCHITECTURE 无需本轮更新：没有改变 OAS 运行时分层、调用链或公共业务 API。业务源码、测试、图片、配置与 L2 登记册均不属于本轮修改范围。

### 验证与未完成

- 本轮只做静态验证，实际命令、输入快照与保护核对记录在 `D:\Codex\outputs\oas-architect-skill-v1.1-20261102`；局部编辑的可逆字节记录在 `D:\Codex\workspace\oas-architect-skill-v1-work\edit-journal.json`。
- Codex 目标客户端的实际发现、新对话自动恢复、Claude 共享规范读取、T1～T17 和真实业务试运行均未执行；不声称已通过。
- 实施前已知 `tasks/DailyTrifles/assets.py:107` 行尾空白保持原样，全局 `git diff --check` 与本轮增量检查分开报告，不为修空白改业务资产。

## 2026-11-02 - 地域鬼王：悬赏与热门重叠后漏打，目标改为「不同鬼王」数量（D062）

- **背景**：oas1 现场 `boss_number=3`、`boss_reward=True`；悬赏鬼王恰是热门第二只，09:49:55 悬赏 → 09:51:26 热门第一只 → 09:52:45 打开热门第二只后关闭（没有再战斗）→ 09:53 正常收尾，只完成两只不同鬼王。根因：`run()` 悬赏成功后按 `boss_number - boss_fought` 固定调用热门前 N 个位置，重叠位置被「已上榜」跳过后不补下一个；`boss_fight` 的 `True` 同时表示「新挑战成功」和「已上榜跳过」。
- **改动**：`tasks/AreaBoss/script_task.py` 改为按候选位置逐个处理直到凑够不同鬼王；`boss_fight` 在详情已打开后读一次名字（新增 `_boss_name_texts` / `_read_detail_name`，`get_bossName` 复用），按名字判重 / 已上榜 / 难度 / 重试；`start_fight` 与 `boss_fight` 返回新增的 `BossResult`（`tasks/AreaBoss/boss_result.py`，`__bool__` 保持旧真值语义）；本轮完成记录 `BossRunRecord` 是 `run()` 内新建的实例属性；补全开 / 跳过 / 准备挑战 / 重试 / 结果 / 汇总日志；不足时 `warning` 报告「完成 X / 目标 Y」并仍 `success=True` 排期（`success=False` 会被循环控制器记为未恢复并阻塞循环）。未动 `is_group_ranked`、OCR ROI / 模型 / 服务、悬赏名字匹配、公共战斗 / 调度。
- **测试**：新增 `tests/test_area_boss_distinct.py` 36 项（有限状态页面世界 + 虚拟计时器 + 次数哨兵）；`test_area_boss_retry.py` 23 项适配（名字替身，一条期望随新口径变化）；`test_l2_c0_registry.py` 精确期望随登记册重新生成同步（总数 1141 → 1143、`KEEP_IMMEDIATE` 637 → 639、rule 937 → 939，`docs/L2_CALLSITE_REGISTER.md` 重新生成，只多 2 个同构的关闭详情页点）。同一世界下 HEAD 版得 `fights=['B','A']`（2 个不同鬼王），修复后 `['B','A','C']`；变异 14 组全部变红。
- **验证**：相关测试、`compileall -q`、登记册 / L1 / L2 相关 144 项均经守护入口通过；全量一次 = **4048 项 OK、skipped=6**（上一基线 4012），486.2 秒，输出 `log/test_runs/full_20261102_160009_21108.log`。
- **文档**：AI_CONTEXT 新增 §4.180、§2 / §7 各加一行；DECISIONS 新增 D062；ROADMAP 已完成表 + Level C 验收项；ARCHITECTURE（不涉及分层 / 调用链 / 公共 API 契约）与 TESTING（无长期验证规则变化）无需更新。
- **待真机**：悬赏 = 热门某只时的完整日志链；`O_AB_BOSS_NAME` 的真实读出稳定性；`NAME_UNKNOWN` 发生频率；`is_group_ranked` 的真实判断；游戏对「不同鬼王」的计数口径。

## 2026-11-02 - SwitchSoul 按名称分组点击改为固定两次，取消分组选中标志模板确认（用户需求修正）

- **背景**：11:58 名称模式点两次后报「没有识别到任何分组选中标志」；用户更新 `I_SOU_CHECK_GROUP_2` 后 12:20 两个实例都改报「同时识别到多个分组选中标志」。名称模式只用 `I_SOU_CHECK_GROUP_2` 在整条左边缘搜索，多个匹配框就报歧义；数字模式取得 `target_check` 却没用它验证。用户决定不再采用这套边框模板确认（不再聚类 / 降阈值 / 取最高分）。
- **改动**：`_name_select_group` 重写为固定两次点击（每次点击前新截图 + 已有 OCR 重新定位，连续两帧稳定；两次之间 `GROUP_CLICK_GAP`，第二次之后 `GROUP_SETTLE`），之后 `_name_settle` 等中央队伍列表稳定（不要求相对点击前变化）并要求 OCR 读得到内容；删除 `_group_selection_state`、`_name_team_ready`、`NAME_MARKER_COLUMN`、`NAME_MARKER_TOL`、`NAME_GROUP_CLICK_TRIES`、`NAME_TEAM_READY_ROUNDS`、`import copy`、`parse_matches`。`I_SOU_CHECK_GROUP_1~7` 的 PNG / JSON / 生成资产原样保留。成功日志不再声称「选中状态已确认」。
- **已接受的边界**：两次点击只证明操作已发出；点击未生效且旧分组有同名队伍时仍可能选错。
- **测试**：`test_switch_soul_name_search` 81 → 85；替换了依赖旧口径的用例（目标已选中零点击 / 无标志·多标志转人工 / 中央列表不变转人工 / 点击未生效一定能阻止旧分组同名队伍），新增 `GroupClickTest` 14 项；11 组变异均变红。点击登记册扫描结果与已入库文件逐字节一致。
- **验证**：相关 10 个模块 339 项通过；`compileall` 通过；全量一次：`dev_tools/guarded_unittest.py --profile full -- discover -s tests` = **4012 项 OK、skipped=6**，只跑一次，514.6 秒（守护入口总耗时 519.3 秒），采样峰值 1444 MiB，退出码 0，输出保存在 `log/test_runs/c_full.log`；`test_switch_soul_name_search` 81 → 85。
- **文档**：AI_CONTEXT 新增 §4.179、§4.144 / §4.177 加更正说明、§2 / §7 各加一行；DECISIONS D041 补记四（并在 10-27 补记标注被取代部分）；ROADMAP 已完成表 + Level C 验收项；TESTING 加测试世界约定；ARCHITECTURE 无 SwitchSoul 内容，无需更新。
- **待真机**：游戏是否真的切到目标分组；点击未生效的旧分组同名队伍风险；间隔 / settle 是否足够。

## 2026-11-02 - SwitchSoul 稳定复查必须确认 stable；福利道馆 120 秒从再战点击起算、点完立即回庭院

### A. SwitchSoul：复查没有检查 stable（`tasks/Component/SwitchSoul/switch_soul.py`）
- 缺口：`_name_settle` 的复查只用 `if not recheck.changed: break`；`NAME_CHANGED=0.02`（相对复查起点）与 `NAME_STABLE=0.01`（相邻帧）使复查可能 `changed=False, stable=False`，旧代码仍把最后一帧当落点。
- 修改：通过条件改为 `recheck.stable and not recheck.changed`；未稳定进入既有有界重观察，耗尽抛 `SwitchSoulPageError`；阈值与返回结构不变。
- 测试：`RecheckMustConfirmStableTest` 6 项（真实 FrameWait + 约 1.7% 面积闪烁帧序列；先证明 `changed=False, stable=False` 真的出现）；测试世界新增 `overlay` / `overlay_tail`。变异 R1/R2/R3 均有测试变红（R1 = 旧条件）。

### B. 福利道馆：120 秒从再战点击起算（`tasks/Dokan/welfare.py`）
- 修改：`_vote_again` 在点击实际发出后 `_start_again_timer()`（唯一截止时刻）；`_run` 顺序改为 `_return_to_courtyard()` → `_wait_again()`（只补等剩余，正常结束后 `stuck_record_clear()`）→ `_back_to_find_page(after_rematch=True)`；无计时进入补等转人工；提示文字里的「再战等待结束后」改为「再战之后」；模块 / 方法文档同步。
- 测试（用户需求修正）：新增 `RematchDeadlineTest` 13 项；改写依赖旧顺序的用例；新增导航中断 / 补等中断；测试世界补一处替身缺口。`test_dokan_welfare` 309 → 324。变异 9 组均有测试变红。

### 验证
- 经守护入口：SwitchSoul 相关 216 项、道馆 / 登记册相关 575 项通过；`compileall` 通过；全量一次 4008 项运行，1 项失败（其余通过）：`test_guarded_unittest.InjectedSamplerTest.test_keyboard_interrupt_cleans_up_and_is_reported_not_passed`——守护入口自身测试（另一会话的未提交文件，本轮未改）的时序竞争，断言「被中断的子进程日志里已有 MARK-0」，满载时日志尚未写出；同一模块在此前的相关分组里通过，没有为它重跑全量，skipped=6；点击登记册无需重新生成。

### 未验证 / 待真机
- SwitchSoul：`NAME_MOVED` / `NAME_RECHECK_TIMEOUT` 仍待真机；道馆：点完再战那一刻游戏停在什么画面、能否立即回庭院、真实耗时；完整两馆流程。没有启动模拟器 / 游戏 / ADB / OCR。

## 2026-11-02 - SwitchSoul 按名称预设：到顶后拖动回弹被当成推进，连续拖动直到 GameTooManyClickError

### 现场与根因（源码确认）
- `log/2026-11-02_oas1.txt` 10:02:40 ~ 10:02:53（oas2 同）：分组列表已在顶部，仍连续拖 `ss_name_group_to_top` 9 次，第 10 次在发出前被 `Device.handle_control_check` 拦下，抛 `GameTooManyClickError`，没进名称查找。
- 缺陷一：`_name_settle` 把 `FrameWaitResult.success`（`changed` 锁存）当「列表动了」；到顶后向下拖回弹回原位也是 success → 每次 moved → 连续两次静止的计数归零。缺陷二：公共保护在发出前登记并检查，回顶上限（12 / 30）大于 9，记录从不释放。
- 没有连续实机录像，「回弹」是推断，不是看到的。

### 修改（只改 `tasks/Component/SwitchSoul/switch_soul.py` 与测试）
- `_name_settle` 返回 `(moved | static, 差异比例)`：先等稳定（有界重试，仍不稳定抛 `SwitchSoulPageError`），过程中变过的稳定后再观察 `NAME_RECHECK_TIMEOUT = 0.8` 秒，最后比较基准帧与最终稳定帧在列表区域内的不同像素比例，`>= NAME_MOVED = 0.03` 为 moved。`NAME_SETTLE_RETRIES` 2 → 3。
- `_name_swipe`：滑动前存独立基准帧；仅在「已发出且 moved」之后 `self.device.click_record_remove(rule.name)`；每次滑动一行 info（差异比例、结果、释放条数），回顶 / 翻页循环再一行（连续静止 x/2）。
- `_name_team_ready` 取返回元组的第一项；`_name_select_group` 不变。

### 测试
- `tests/test_switch_soul_name_search.py` 61 → 75：世界新增回弹序列 / 局部闪烁 / 常亮高亮 / 稀疏内容 / 事件顺序；设备换成真实 `Device` 操作记录逻辑（先登记检查、后发出）；新增 `BounceAndRecordReleaseTest` 14 项（合成帧，不是实机录像）。
- 静态守卫两处随源码形态调整：`test_switch_soul_numeric_v1` 放行 `click_record_remove`（仅 `_name_swipe`，仍禁 `click_record_clear`）；`test_switch_soul_group_top_v2` 的 `self.swipe(getattr(self, attr))` → `self.swipe(rule)`。

### 验证
- 变异 7 组（锁存判定 / 不释放 / static 也释放 / 阈值 0.0001 / 阈值 0.9 / 无复查 / 传 RuleSwipe）经守护入口均有测试变红；旧判定 + 不释放复现现场的 `GameTooManyClickError`。
- 相关 15 个模块 450 项通过；`compileall` 通过；全量一次 3987 项 OK、skipped=6；`git diff --check` 通过。

### 未验证 / 待真机
- 真实回弹形态、`NAME_MOVED = 0.03` / `NAME_RECHECK_TIMEOUT = 0.8` 是否合适；> 0.8 秒的回弹中途停顿；回弹时每次滑动多约 0.8 秒复查；没有启动模拟器 / 游戏 / ADB / OCR。

## 2026-11-01 - 福利道馆：每一馆找「鑫」之前都重新做我方建馆检查（用户需求修正）

### 需求
- 用户修正规则：第二馆仍要做我方建馆检查，此前「两馆只检查一次」作废；阵容预设仍只做一次。

### 核对与修改（只改 `tasks/Dokan/welfare.py` 与测试）
- 核对缓存：原 `_run` 用 `if not self.own_dokan_checked: self._ensure_own_dokan()` 守卫，第一馆置 True 后第二馆会被跳过——只增加调用不够，必须去掉守卫。
- 修改：`_ensure_own_dokan()` 移到每一馆循环开头（第一馆仍在预设之前，第二馆在 `_back_to_find_page(after_rematch=True)` 确认找馆页之后、找「鑫」之前）；`own_dokan_checked` 改为「最近一次检查已通过」，进入时清零；模块 docstring 同步。预设 / 计数 / `opened` / 提前结束路径不动。
- 测试：替换固化「检查只一次」的旧断言（需求修正），新增每馆实际检查一次、顺序、不复用、第二馆未建立先建后找、检查 / 建馆失败不找馆不开馆、预设仍一次、初始一次机会 / 提前结束 / 机会 0 不多检查、旧缓存对照；`tests/test_dokan_welfare.py` 修改后 301 → 309 项。

### 验证
- 只改生产代码后 `test_dokan_welfare` 恰有 2 项失败（固化旧口径的两条）；替换 / 新增后相关类全绿。变异 8 组经守护入口（临时改 `welfare.py`、核对恢复哈希）均有测试变红。
- 全量（守护入口，一次）3973 项 OK、skipped=6，退出码 0；`compileall` 通过。

### 未验证 / 待真机
- 第二馆检查时我方道馆的真实状态与建馆入口表现；完整两馆流程；没有启动模拟器 / 游戏 / ADB / OCR。

## 2026-11-01 - 福利道馆第一馆放弃后的再战衔接：再战点击实际发出即计时，等完先回庭院再进地图

### 需求（用户调整成功口径，取代旧确认要求）
- 关闭并确认排名遮罩消失 → 新截图识别再战按钮 → 实际发出一次再战点击 → 等 120 秒 → 回庭院 → 重新进入道馆地图 → 找第二馆；点击发出后不再等按钮框变化 / 稳定，不再要求旧投票模板继续存在，不再补点。

### 修改（只改 `tasks/Dokan/welfare.py` 与测试）
- `_vote_again` 重写：每轮新截图，遮罩先 `_clear_rank_mask`；`appear_then_click` 返回 True 即返回；未发出有界重试，用尽转人工。移除 `_outside_change`、`VOTE_CHANGED_THRESHOLD` / `VOTE_STABLE_THRESHOLD` / `VOTE_CONFIRM_TIMEOUT` / `VOTE_OUTSIDE_CHANGED_MAX` 与 `vote confirm check` 日志（先核对：引用只在 welfare.py 与 test_dokan_welfare.py）。`_wait_again` 日志改为 `rematch click sent, wait 120s`，卡死保护注释同步。
- 新增 `_return_to_courtyard`（`goto_page(page_main)` + 新截图确认，游戏已在庭院直接确认；地图有进行中的馆转人工；未知页只重新识别；导航失败有界；无 finally），`_run` 在 `_wait_again` 与 `_back_to_find_page(after_rematch=True)` 之间调用。准备后 1 秒缓冲（§4.174）与其他流程不动。
- `tests/test_dokan_welfare.py`：替身 `FakeTask.goto_page` 新增 `page_main` 分支（`_goto_main`，道馆页先走真实退出转换）；按新口径替换旧用例并说明需求变更；新增 `CourtyardReturnTest`。

### 测试
- 第一次改完生产代码后相关组 18 项失败（13 FAIL + 5 ERROR），全部是依赖旧口径的用例或替身缺 `page_main` 导航；逐项替换 / 补齐后 `test_dokan_welfare` 301 项通过。变异 8 组均有测试变红。
- 全量（守护入口）第一次 3965 项中 1 项失败：`test_l2_c0_registry` 的登记册与生成器不一致（`_vote_again#1` 行的辅助标记 `frame_wait` 随变化确认移除）；用 `dev_tools.click_callsite_register --write` 重新生成（只变这一行）后重跑全量 3965 项 OK、skipped=6，退出码 0。

### 未验证 / 待真机
- 游戏是否接受这次再战点击（程序不再二次确认）、放弃后账号状态下回庭院的真实路径与耗时、完整两馆流程；没有启动模拟器 / 游戏 / ADB / OCR。

## 2026-11-01 - 福利道馆：准备后关闭缓冲 0.35 秒 → 1 秒

### 修改
- `tasks/Dokan/welfare.py`：`PREPARE_CLOSE_BUFFER_SECONDS = 1.0`（两馆共用）；模块与 `_enter_prepare_and_close` docstring 同步。顺序、异常传播（无 finally）、不新增截图 / 识别 / 进程查询、600 秒起点均不变；这 1 秒在 `app_stop` 之前，计入在线活跃时间。
- `assets/i18n/zh-CN.json` / `en-US.json`：`welfare_mode_help` 的 0.35 秒改为 1 秒。
- `tests/test_dokan_welfare.py`：`PrepareBufferTest` 及相关断言的 0.35 改 1.0；`tests/test_dokan_welfare_weekdays.py` 的帮助文案断言改查「1 秒」。

### 测试
- 第一次守护相关组 1 项红：`test_the_buffer_is_online_time_only_the_closed_wait_is_excluded` 的 `end - start <= 600` 得到 600.0000000000001（虚拟时钟浮点累加，缓冲变长后数值变大才暴露，与业务逻辑无关）；给该断言加 1e-6 容差后相关组通过，没有放宽 600 秒语义。
- 守护入口：相关组 341 项通过；全量一次 3956 项 OK、skipped=6，退出码 0；compileall 通过。

### 未验证 / 待真机
- 1 秒是否足以让游戏接受「准备」并在离线后自动战斗；没有启动模拟器 / 游戏 / ADB，没有任何真机证据。

## 2026-11-01 - 道馆配置页改版：后端展示信息（kind = "dokan"）+ 去掉七个星期的重复长说明

### 核查
- 现有接口：`GET /{script}/{task}/args/layout` → `ConfigModel.script_task_layout` → `TASK_ARGS_LAYOUTS`（原来只有 `activity_shikigami`，返回结构含活动专属的 `selector / plays / common / advanced`，没有 `kind`）；道馆另起 `kind = "dokan"`，不把道馆伪装成活动玩法。
- 字段清单：`/args` 共 59 个参数（`scheduler` 8、`dokan_config` 19、两个战斗配置各 10、两个切换御魂各 5、`attack_count_config` 2）；`remain_attack_count` / `attack_date` 本来隐藏，不在 `/args`。用 AST 核对执行代码：福利只读 `welfare_min_people` 和星期选择；普通找馆 / 战斗 / 御魂切换 / 馆主次数字段福利都不读；`dokan_run_time`、`daily_attack_count` 两种模式的 `next_run` 都读；`dokan_config.random_delay` 全仓没有读者。

### 修改
- 新增 `tasks/Dokan/args_layout.py`（`build_args_layout`，只读，kind / version / mode / sections）；`module/config/config_model.py` 的 `TASK_ARGS_LAYOUTS` 注册 `dokan`。
- `tasks/Dokan/config.py`：七个星期字段只有周一保留 `description`（其余去掉，字段名 / 类型 / 默认值 / 保存路径 / 兼容代码不变）。
- `assets/i18n/zh-CN.json` / `en-US.json`：星期标题改为「周一」…「周日」/ Mon … Sun，`welfare_run_days_help` 精简（不含迁移原理），`dokan_run_time_help` 说明福利不把它当开始钟点，新增布局用的标题 / 徽标 / 提示键。
- `tests/test_dokan_args_layout.py`（新增 22 项）；`tests/test_dokan_welfare_weekdays.py` 更新旧标题 / description 断言。
- 文档：AI_CONTEXT §4.173（含 OASX 接入契约与 JSON 示例）/ §7、ROADMAP、DECISIONS D059、ARCHITECTURE、TESTING。

### 测试
- 不注册布局 → 22 项中 10 项红；变异 12 组均有测试变红。过程中的两处自己的问题：测试里 `attack_dokan_master` 的读取点是配置方法 `attack_dokan_master_count()`（不是属性），已按真实调用点改；英文帮助 164 字符超过我先设的 160 上限，改为 200（中文约 70）。另有一次 shell heredoc 会吞掉反斜杠，导致正则编辑脚本失败，改用文件脚本。
- 守护入口：相关 436 项通过；全量一次 3956 项 OK、skipped=6（上一轮那个双进程 ready 撤回时序用例这次没有失败，未查原因，不下结论）。

### 未实现 / 待办
- OASX 道馆页面（模式下拉、分区折叠、紧凑七天选择器、摘要、兜底分区）；没有构建 / 部署 / 真机验证。

## 2026-11-01 - 福利道馆：每周允许运行日期（七个星期勾选，解除只能周一到周四）

### 核查
- `run()` 在判断 `welfare_mode` 之前先用 `monday_to_thursday` + `weekday() >= 4` 跳过；`next_run` 跳过今天分支也读它；`next_run` 共 7 个 `set_next_run` 出口。Dokan 排期入口只有 `script_task.py` 一处，没有别的模块读 `monday_to_thursday`。
- 福利整轮结束收尾是 `next_run(False, True)`：只有最终剩余机会 == 1 且每日 2 次才走 `failure_interval`（默认 1 天），正常完成（最终 0）走明天 `dokan_run_time`，没有「整轮结束被当成第一馆刚结束而立即重试」。
- `ConfigModel.script_set_arg` 逐字段 `setattr` 后 `save()` 整体 `model_dump`；`write_json` 是静态方法。

### 修改
- `tasks/Dokan/config.py`：七个布尔字段 + `model_validator(after)`（按 `model_fields_set` 区分缺键 / 显式 False，缺键按 `monday_to_thursday` 推导）+ `welfare_runs_on` / `welfare_allowed_weekdays` + `WEEKDAY_NAMES`。
- `tasks/Dokan/script_task.py`：`run()` 福利 / 普通分开判断；新增 `_schedule`（福利模式叠加星期约束：已允许原样，否则逐天往后推并保留钟点，七天全关保持原排期），`next_run` 所有出口改走它，福利的跳过今天不再走旧的「周一」分支。
- `config/template.json`、`assets/i18n/zh-CN.json` / `en-US.json`：七个键与翻译；更正 `welfare_mode_help` 里「立即关闭游戏」。
- `tests/test_dokan_welfare_weekdays.py`（新增 27 项）；`tests/test_dokan_welfare.py` 一处替身补两个属性；`tests/test_dokan_normal_mode.py` 一个用例改名并写明原因。
- 文档：AI_CONTEXT §4.172 / §7、ROADMAP、DECISIONS D058、ARCHITECTURE、TESTING。

### 测试
- 旧入口 → 27 项中 18 项红；`_schedule` 不约束 → 17 项红；变异 6 组均有测试变红。过程中发现两处我自己的测试写法问题（`write_json` 要用 `staticmethod` 打补丁；`failure_interval` 默认 1 天，不是分钟级），已修正。
- 守护入口：相关 400 项通过（第一次相关组有 1 项错误：`test_final_count_unknown_...` 的 `SimpleNamespace` 替身缺新属性，是我的改动引起，已改替身后通过）；全量 3934 项，1 失败（`test_loop_multiprocess` ready 撤回时序，既有失败，未处理）、6 skip；`compileall`、`git diff --check`（本轮文件）通过。

### 未验证 / 未处理
- OASX 界面勾选与保存、真实调度器；`test_loop_multiprocess` 的失败根因没有查。

## 2026-11-01 - 每日琐事领取邮件：无红点信封入口（COPY3）+「尚未打开邮箱」阶段独立时限

### 范围
- 2026-11-01 oas1 / oas2 多次在 `PICK UP EMAIL` 回到 `page_main` 后没有发出打开邮箱的点击，约 60 秒后 `GameStuckError: Wait too long` 并 Restart；现场信封没有红点，旧入口 COPY2 约 0.5608（阈值 0.9）。只处理邮件入口及其失败边界，不动其他每日任务、调度或用户配置。

### 修改
- `tasks/DailyTrifles/script_task.py`：`run_pickup_email` 的打开入口链末尾追加 `I_DT_HARVEST_MAIL_COPY3`（用户新增资源，`assets.py` / `image_pickup_email.json` 已由生成器产出，未手改）；新增常量 `PICKUP_OPEN_TIMEOUT=20` 与 `open_phase` 计时器，只在尚未确认进邮箱的分支检查，到点记原因、`gave_up`、不记完成、走原有 `goto_page` 兜底。
- `tests/test_daily_pickup_email.py` 25 → 49 项 + 三张真实夹具 `tests/fixtures/daily_pickup_email/`；`docs/L2_CALLSITE_REGISTER.md` 重新生成（+1，`run_pickup_email#9`）；`test_l1_l2_integration` / `test_l2_c0_registry` / `test_l2_interaction_reaction` 的精确计数同步。
- 文档：AI_CONTEXT §4.171、ROADMAP（真机验收项）、DECISIONS D057、TESTING §5.ad。

### 测试
- 旧实现对照：HEAD 的 `run_pickup_email` 在同一批 49 项上 12 项失败（8 failures + 4 errors），入口认不出的用例直接抛 `GameStuckError`；新实现 49 项全过。
- 经守护入口：`tests.test_daily_pickup_email` 49 项；相关回归 589 项 + `test_l2_interaction_reaction`；全量 `unittest discover -s tests` 3907 项运行、1 项失败（`test_loop_multiprocess` 的双进程时序用例，与本轮无关，见 §7 基线与 TESTING §5.ad）、skipped=6，461.6 秒，采样峰值 1445 MiB。 日志在 `D:\Codex\outputs\20261101_每日琐事邮箱入口\`。

### 未验证 / 未处理
- 真机：无红点信封点击能否打开邮箱、邮箱空 / 有奖励两种情况、入口认不出时 20 秒后不再空等重启。COPY3 离线 1.0 为自匹配；没有「邮箱已打开且信封无红点」样本。未提交。
