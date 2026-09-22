# L2 Interaction Policy Map（L2-2 审计与迁移清单）

> **本分支（synevo 集成分支）说明（2026-09-22）**：本文件由 master 整合而来，正文里的「全仓 1092 点」等数字是 **master 的口径**。
> 本分支的真实全仓统计以重新生成的 `docs/L2_CALLSITE_REGISTER.md` 为准：**1127 点**（basis human 180 / c0 17 / rule 930），
> 差异来自 synevo 独有的 AccountRotation / MultiAccountEvo / SwitchAccount 等轮换业务调用点（大部分归 EXCLUDED）与 1 个 EvoZone 收尾调用点。
> §1~§3 的 179 点人工审计、§4 的 C0 24 点分类结论本身不随分支变化。

> 2026-09-15 在 worktree `feature/l2-interaction-reaction-layer` 形成；**2026-09-21 已集成进 master 工作区**（未提交，见 `docs/AI_CONTEXT.md` §4.82）。
> 全仓（`tasks/` + `module/`）逐点登记册见 `docs/L2_CALLSITE_REGISTER.md`（`dev_tools/click_callsite_register.py` 生成、
> `tests/test_l1_l2_integration.py` 对账）：本表是其中 basis=human 的 179 个点，其余为保守规则分类。
> **统计范围说明**：本文件 §1～§3 是 **L2-2 最初的 179 点人工审计**（历史结论，保持不变；§2 的 NEEDS_C = 7 只是这 179 点里的数字，不是全仓完整数据）；全仓 24 个原 NEEDS_C 的 C0 复核与 C1-A1 实施状态见 **§4**。四个口径不可混用：全仓 1092 点 / 最初人工审计 179 点 / C0 复核 24 点 / C1-A1 实施 4 点。
> 设计依据：`docs/DECISIONS.md` D001「L2-1」「L2-2」补记；护栏：`tests/test_l2_policy_migration.py`
> （本表的「文件 / 函数 / 调用 / 目标 / 当前 timing」逐行锁定，改动点击 timing 必须同步改本表与测试清单）。

## 1. 范围与分类口径

审计范围（18 个文件）：GeneralInvite、GeneralBattle、GameUi（navigator / default_pages / chess_battle）、EvoZone、
Orochi、RealmRaid、RyouToppa、Exploration、ActivityShikigami（page / base_act / normal / fake_god / rich_man）、
KekkaiUtilize（script_task / page）里的全部点击调用（`appear_then_click` / `ui_click*` / `self.click` /
`ocr_appear_click` / `list_appear_click`）。明确排除 AccountRotation / SwitchAccount / Login / DailyTrifles /
MultiAccountEvo（synevo 小号业务）。

**WeeklyPurchase → EXCLUDED_BY_PROJECT_DECISION**（2026-09-15 用户决定）：不做 Reaction Policy / FIRE 改造，不列入 L2
待迁移 / ordinary Reaction backlog / FIRE 候选，后续 L2 自动审计一律跳过。

| 分类 | 含义 |
| --- | --- |
| **MIGRATE** | 本轮迁到显式 `policy=InteractionPolicy.*`（高频或明确 UI Point Action、目标稳定、fresh confirm 安全、无其它 timing owner） |
| **ALREADY_L2** | 已有显式 reaction owner：L2-1 policy consumer、FIRE owner（任务配置 `fire_reaction`）、legacy 非 profile `confirm_delay`、形参透传 |
| **KEEP_IMMEDIATE** | 合法立即点击：polling / 搜索探测 / recovery / teardown、helper 无 policy 参数、动态 OCR / 区域目标、受保护业务、低频冷门流程 |
| **KEEP_SPECIAL** | 已有独立 timing owner：Settlement / 奖励阶段、Battle Entry 语义（准备 / 挑战 / 旧 FIRE 流程）、防挂机节拍、业务 pacing、随机安全区点击 |
| **NEEDS_C** | 可能该加 reaction，但时效 / 协作节奏无法静态判断——保持原样，等真机证据 |

## 2. 结果

| 分类 | 数量 |
| --- | --- |
| ALREADY_L2 | 33 |
| MIGRATE | 7 |
| KEEP_IMMEDIATE | 94 |
| KEEP_SPECIAL | 38 |
| NEEDS_C | 7 |
| **合计** | **179** |

迁移（7）：GeneralInvite `_open_invite_panel_if_needed` 的 `I_ADD_1 / I_ADD_2 / I_ADD_5_4 / I_ADD_SEA` → NORMAL；
GeneralBattle `switch_preset_team` 的 `I_PRESET / I_PRESET_WIT_NUMBER` → NORMAL、`I_PRESET_ENSURE` → CONFIRM。

L2-3B FIRE Batch A（2026-09-18）：worktree 里曾把 Orochi `run_wild` 的 `I_OROCHI_WILD_FIRE` 移入 FIRE owner `_fire_orochi_wild`；
**master 集成时按项目决定不带入野队**（`run_wild` 保持内联点击，仍是 KEEP_SPECIAL，故 ALREADY_L2 33 / KEEP_SPECIAL 38）。EternitySea /
FallenSun / Sougenbi 的 FIRE 在本清单审计范围外，见 `docs/AI_CONTEXT.md` §4.74。

NEEDS_C（7）：GeneralInvite `check_then_accept` 5 处（队员接受邀请：邀请时效、队长秒开 issue #230、多开协作节奏）；
GeneralBattle `_handle_prepare` 的 `I_DISABLE_7DAYS_DIFF_SOUL / I_CONFIRM_CLOSE_DIFF_SOUL`（准备阶段倒计时 / 组队就绪）。

范围外：`tasks/base_task.py` 19 处是 `appear_then_click` / `ui_click*` 等 primitive 自身实现；WeeklyPurchase 约 48 处为
EXCLUDED_BY_PROJECT_DECISION；其余 50 个 master 模块约 670 处点击调用本轮**未逐点审计**，保持 legacy 立即点击（例如
SixRealms 70、WantedQuests 38、AbyssShadows 32、BondlingFairyland 30、Dokan 29）。

## 3. 逐点清单

| ID | 文件 | 函数 | 调用 | 目标 | 当前 timing | 分类 | Policy | 原因 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| L2M-001 | `Component/GeneralInvite/general_invite.py` | `run_invite` | `appear_then_click` | `self.I_GI_EMOJI_1` | IMMEDIATE | **KEEP_SPECIAL** | - | 房间防挂机表情，由 timer_emoji 节拍拥有 timing，不是用户式响应点击 |
| L2M-002 | `Component/GeneralInvite/general_invite.py` | `run_invite` | `appear_then_click` | `self.I_GI_EMOJI_2` | IMMEDIATE | **KEEP_SPECIAL** | - | 房间防挂机表情，由 timer_emoji 节拍拥有 timing，不是用户式响应点击 |
| L2M-003 | `Component/GeneralInvite/general_invite.py` | `exit_room` | `appear_then_click` | `GeneralInviteAssets.I_GI_SURE` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 离房恢复路径：Timer(5) 有界、条件表达式内点击；reaction 会吃掉恢复预算，retry owner = 调用方 |
| L2M-004 | `Component/GeneralInvite/general_invite.py` | `exit_room` | `appear_then_click` | `GeneralInviteAssets.I_GI_SURE` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 离房恢复路径：Timer(5) 有界、条件表达式内点击；reaction 会吃掉恢复预算，retry owner = 调用方 |
| L2M-005 | `Component/GeneralInvite/general_invite.py` | `exit_room` | `appear_then_click` | `self.I_BACK_YELLOW` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 离房恢复路径：Timer(5) 有界、条件表达式内点击；reaction 会吃掉恢复预算，retry owner = 调用方 |
| L2M-006 | `Component/GeneralInvite/general_invite.py` | `exit_room` | `appear_then_click` | `self.I_BACK_YELLOW_SEA` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 离房恢复路径：Timer(5) 有界、条件表达式内点击；reaction 会吃掉恢复预算，retry owner = 调用方 |
| L2M-007 | `Component/GeneralInvite/general_invite.py` | `click_fire` | `appear_then_click` | `target` | IMMEDIATE | **ALREADY_L2** | FIRE_SPECIAL | FIRE battle-entry owner（任务配置 fire_reaction） |
| L2M-008 | `Component/GeneralInvite/general_invite.py` | `_open_invite_panel_if_needed` | `appear_then_click` | `self.I_ADD_1` | NORMAL | **MIGRATE** | NORMAL | 房间「+」开邀请面板：稳定普通按钮，Timer(1) 节流 + Timer(5) 预算内，fresh confirm 安全（位子被占即不点） |
| L2M-009 | `Component/GeneralInvite/general_invite.py` | `_open_invite_panel_if_needed` | `appear_then_click` | `self.I_ADD_2` | NORMAL | **MIGRATE** | NORMAL | 房间「+」开邀请面板：稳定普通按钮，Timer(1) 节流 + Timer(5) 预算内，fresh confirm 安全（位子被占即不点） |
| L2M-010 | `Component/GeneralInvite/general_invite.py` | `_open_invite_panel_if_needed` | `appear_then_click` | `self.I_ADD_5_4` | NORMAL | **MIGRATE** | NORMAL | 房间「+」开邀请面板：稳定普通按钮，Timer(1) 节流 + Timer(5) 预算内，fresh confirm 安全（位子被占即不点） |
| L2M-011 | `Component/GeneralInvite/general_invite.py` | `_open_invite_panel_if_needed` | `appear_then_click` | `self.I_ADD_SEA` | NORMAL | **MIGRATE** | NORMAL | 房间「+」开邀请面板：稳定普通按钮，Timer(1) 节流 + Timer(5) 预算内，fresh confirm 安全（位子被占即不点） |
| L2M-012 | `Component/GeneralInvite/general_invite.py` | `_switch_friend_class` | `ui_click` | `self.I_FLAG_1_OFF` | IMMEDIATE | **KEEP_IMMEDIATE** | - | ui_click 系 helper 自带点击循环且无 policy 参数；本轮不扩公共 API（后续 L2 设计项） |
| L2M-013 | `Component/GeneralInvite/general_invite.py` | `_switch_friend_class` | `ui_click` | `self.I_FLAG_2_OFF` | IMMEDIATE | **KEEP_IMMEDIATE** | - | ui_click 系 helper 自带点击循环且无 policy 参数；本轮不扩公共 API（后续 L2 设计项） |
| L2M-014 | `Component/GeneralInvite/general_invite.py` | `_switch_friend_class` | `ui_click` | `self.I_FLAG_3_OFF` | IMMEDIATE | **KEEP_IMMEDIATE** | - | ui_click 系 helper 自带点击循环且无 policy 参数；本轮不扩公共 API（后续 L2 设计项） |
| L2M-015 | `Component/GeneralInvite/general_invite.py` | `_switch_friend_class` | `ui_click` | `self.I_FLAG_4_OFF` | IMMEDIATE | **KEEP_IMMEDIATE** | - | ui_click 系 helper 自带点击循环且无 policy 参数；本轮不扩公共 API（后续 L2 设计项） |
| L2M-016 | `Component/GeneralInvite/general_invite.py` | `_confirm_invite_and_validate` | `ui_click_until_disappear` | `confirm_rule` | IMMEDIATE | **KEEP_IMMEDIATE** | - | ui_click 系 helper 自带点击循环且无 policy 参数；本轮不扩公共 API（后续 L2 设计项） |
| L2M-017 | `Component/GeneralInvite/general_invite.py` | `invite_again` | `appear_then_click` | `self.I_I_NO_DEFAULT` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 0 个生产调用方（死代码），不为覆盖率改 |
| L2M-018 | `Component/GeneralInvite/general_invite.py` | `invite_again` | `appear_then_click` | `self.I_I_DEFAULT` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 0 个生产调用方（死代码），不为覆盖率改 |
| L2M-019 | `Component/GeneralInvite/general_invite.py` | `invite_again` | `appear_then_click` | `self.I_GI_SURE` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 0 个生产调用方（死代码），不为覆盖率改 |
| L2M-020 | `Component/GeneralInvite/general_invite.py` | `check_and_invite` | `appear_then_click` | `self.I_I_NO_DEFAULT` | IMMEDIATE | **KEEP_SPECIAL** | - | 「再次邀请」弹窗由 Orochi / EvoZone / FallenSun 等 `_handle_reward` 在奖励 / 结算阶段调用，属 Settlement 生命周期，排除普通 L2 |
| L2M-021 | `Component/GeneralInvite/general_invite.py` | `check_and_invite` | `appear_then_click` | `self.I_GI_SURE` | IMMEDIATE | **KEEP_SPECIAL** | - | 「再次邀请」弹窗由 Orochi / EvoZone / FallenSun 等 `_handle_reward` 在奖励 / 结算阶段调用，属 Settlement 生命周期，排除普通 L2 |
| L2M-022 | `Component/GeneralInvite/general_invite.py` | `check_then_accept` | `appear_then_click` | `self.I_I_NO_DEFAULT` | IMMEDIATE | **NEEDS_C** | - | 队员接受邀请：邀请弹窗时效、队长秒开（issue #230）与多开协作节奏未经真机确认 |
| L2M-023 | `Component/GeneralInvite/general_invite.py` | `check_then_accept` | `appear_then_click` | `self.I_GI_SURE` | IMMEDIATE | **NEEDS_C** | - | 队员接受邀请：邀请弹窗时效、队长秒开（issue #230）与多开协作节奏未经真机确认 |
| L2M-024 | `Component/GeneralInvite/general_invite.py` | `check_then_accept` | `appear_then_click` | `self.I_I_ACCEPT_DEFAULT` | IMMEDIATE | **NEEDS_C** | - | 队员接受邀请：邀请弹窗时效、队长秒开（issue #230）与多开协作节奏未经真机确认 |
| L2M-025 | `Component/GeneralInvite/general_invite.py` | `check_then_accept` | `appear_then_click` | `self.I_I_ACCEPT` | IMMEDIATE | **NEEDS_C** | - | 队员接受邀请：邀请弹窗时效、队长秒开（issue #230）与多开协作节奏未经真机确认 |
| L2M-026 | `Component/GeneralInvite/general_invite.py` | `check_then_accept` | `appear_then_click` | `self.I_I_ACCEPT_APPRENTICE` | IMMEDIATE | **NEEDS_C** | - | 队员接受邀请：邀请弹窗时效、队长秒开（issue #230）与多开协作节奏未经真机确认 |
| L2M-027 | `Component/GeneralInvite/general_invite.py` | `wait_battle` | `appear_then_click` | `self.I_GI_EMOJI_1` | IMMEDIATE | **KEEP_SPECIAL** | - | 同上（队员等开战的防挂机表情，timer_emoji 拥有） |
| L2M-028 | `Component/GeneralInvite/general_invite.py` | `wait_battle` | `appear_then_click` | `self.I_GI_EMOJI_2` | IMMEDIATE | **KEEP_SPECIAL** | - | 同上（队员等开战的防挂机表情，timer_emoji 拥有） |
| L2M-029 | `Component/GeneralBattle/general_battle.py` | `_inspection_recover_auto_mode` | `ui_click` | `hand_marker` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 战斗内自动模式恢复（recovery） |
| L2M-030 | `Component/GeneralBattle/general_battle.py` | `_handle_prepare` | `appear_then_click` | `self.I_DISABLE_7DAYS_DIFF_SOUL` | IMMEDIATE | **NEEDS_C** | - | 准备页「不同御魂」弹窗：准备阶段倒计时 / 组队就绪节奏未经真机确认 |
| L2M-031 | `Component/GeneralBattle/general_battle.py` | `_handle_prepare` | `appear_then_click` | `self.I_CONFIRM_CLOSE_DIFF_SOUL` | IMMEDIATE | **NEEDS_C** | - | 准备页「不同御魂」弹窗：准备阶段倒计时 / 组队就绪节奏未经真机确认 |
| L2M-032 | `Component/GeneralBattle/general_battle.py` | `_handle_prepare` | `appear_then_click` | `self.I_PREPARE_HIGHLIGHT` | IMMEDIATE | **KEEP_SPECIAL** | - | 「准备」= Prepare → Battle 的 Battle Entry 语义，由 `_prepare_click_ready` 门控；D001 明确不加普通 reaction，未来按 FIRE contract 单独设计 |
| L2M-033 | `Component/GeneralBattle/general_battle.py` | `_handle_reward` | `appear_then_click` | `self.I_OVER_GHOST` | IMMEDIATE | **KEEP_SPECIAL** | - | 奖励页特殊弹窗属 Settlement 阶段，排除普通 L2 |
| L2M-034 | `Component/GeneralBattle/general_battle.py` | `_handle_reward` | `appear_then_click` | `self.I_GB_SKIN_CONFIRM` | IMMEDIATE | **KEEP_SPECIAL** | - | 奖励页特殊弹窗属 Settlement 阶段，排除普通 L2 |
| L2M-035 | `Component/GeneralBattle/general_battle.py` | `exit_battle` | `appear_then_click` | `self.I_EXIT_ENSURE` | IMMEDIATE | **KEEP_IMMEDIATE** | - | quick exit / 组队清理的中止路径，QUICK_EXIT_WAIT_TIMEOUT 有界，retry owner = 战斗 FSM |
| L2M-036 | `Component/GeneralBattle/general_battle.py` | `exit_battle` | `appear_then_click` | `self.I_EXIT` | IMMEDIATE | **KEEP_IMMEDIATE** | - | quick exit / 组队清理的中止路径，QUICK_EXIT_WAIT_TIMEOUT 有界，retry owner = 战斗 FSM |
| L2M-037 | `Component/GeneralBattle/general_battle.py` | `exit_battle` | `ui_click_until_disappear` | `self.I_EXIT_ENSURE` | IMMEDIATE | **KEEP_IMMEDIATE** | - | quick exit / 组队清理的中止路径，QUICK_EXIT_WAIT_TIMEOUT 有界，retry owner = 战斗 FSM |
| L2M-038 | `Component/GeneralBattle/general_battle.py` | `green_mark_choose` | `appear_then_click` | `self.I_LOCAL` | IMMEDIATE | **KEEP_SPECIAL** | - | 战斗内标记序列（I_LOCAL → sleep(0.3) → 标记点）由标记流程拥有 timing |
| L2M-039 | `Component/GeneralBattle/general_battle.py` | `switch_preset_team` | `appear_then_click` | `self.I_PRESET` | NORMAL | **MIGRATE** | NORMAL | 打开预设面板的图片按钮：普通 UI 动作；Timer(4) 预算内 |
| L2M-040 | `Component/GeneralBattle/general_battle.py` | `switch_preset_team` | `appear_then_click` | `self.I_PRESET_WIT_NUMBER` | NORMAL | **MIGRATE** | NORMAL | 打开预设面板的图片按钮：普通 UI 动作；Timer(4) 预算内 |
| L2M-041 | `Component/GeneralBattle/general_battle.py` | `switch_preset_team` | `appear_then_click` | `self.O_PRESET` | IMMEDIATE | **KEEP_IMMEDIATE** | - | OCR 兜底目标：框体每帧动态，fresh confirm 不能保证等价 target |
| L2M-042 | `Component/GeneralBattle/general_battle.py` | `switch_preset_team` | `appear_then_click` | `self.O_PRESET_FULL` | IMMEDIATE | **KEEP_IMMEDIATE** | - | OCR 兜底目标：框体每帧动态，fresh confirm 不能保证等价 target |
| L2M-043 | `Component/GeneralBattle/general_battle.py` | `switch_preset_team` | `click` | `tmp` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 分组 / 队伍选择按颜色状态循环点 RuleClick，没有可重新识别的 appear 目标 |
| L2M-044 | `Component/GeneralBattle/general_battle.py` | `switch_preset_team` | `click` | `tmp` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 分组 / 队伍选择按颜色状态循环点 RuleClick，没有可重新识别的 appear 目标 |
| L2M-045 | `Component/GeneralBattle/general_battle.py` | `switch_preset_team` | `click` | `tmp` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 分组 / 队伍选择按颜色状态循环点 RuleClick，没有可重新识别的 appear 目标 |
| L2M-046 | `Component/GeneralBattle/general_battle.py` | `switch_preset_team` | `appear_then_click` | `self.I_PRESET_ENSURE` | CONFIRM | **MIGRATE** | CONFIRM | 确认阵容预设：CONFIRM 语义；Timer(4) 预算内，fresh confirm 安全 |
| L2M-047 | `Component/GeneralBattle/general_battle.py` | `random_click_swipt` | `click` | `self.C_RANDOM_CLICK` | IMMEDIATE | **KEEP_SPECIAL** | - | 战斗内防挂机随机点击，不是 UI Point Action |
| L2M-048 | `Component/GeneralBattle/general_battle.py` | `check_lock` | `appear_then_click` | `unlock_image` | policy | **ALREADY_L2** | caller | policy / confirm_delay 透传，由调用方显式给 |
| L2M-049 | `Component/GeneralBattle/general_battle.py` | `check_lock` | `appear_then_click` | `lock_image` | policy | **ALREADY_L2** | caller | policy / confirm_delay 透传，由调用方显式给 |
| L2M-050 | `Component/GeneralBattle/general_battle.py` | `check_and_open_buff` | `ui_click_until_appear_or_timeout` | `self.I_BUFF` | IMMEDIATE | **KEEP_IMMEDIATE** | - | GeneralBuff 开关序列（逐项 toggle + sleep(0.1)）自有 timing，低频 |
| L2M-051 | `Component/GeneralBattle/general_battle.py` | `check_and_open_buff` | `appear_then_click` | `self.I_BUFF` | IMMEDIATE | **KEEP_IMMEDIATE** | - | GeneralBuff 开关序列（逐项 toggle + sleep(0.1)）自有 timing，低频 |
| L2M-052 | `GameUi/navigator.py` | `_execute_action` | `list_appear_click` | `action` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 通用 transition / hook 执行器：禁止全局注入 NAVIGATION；需要逐 edge 声明时再加元数据 |
| L2M-053 | `GameUi/navigator.py` | `_execute_action` | `appear_then_click` | `action` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 通用 transition / hook 执行器：禁止全局注入 NAVIGATION；需要逐 edge 声明时再加元数据 |
| L2M-054 | `GameUi/navigator.py` | `_execute_action` | `ocr_appear_click` | `action` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 通用 transition / hook 执行器：禁止全局注入 NAVIGATION；需要逐 edge 声明时再加元数据 |
| L2M-055 | `GameUi/navigator.py` | `_execute_action` | `click` | `action` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 通用 transition / hook 执行器：禁止全局注入 NAVIGATION；需要逐 edge 声明时再加元数据 |
| L2M-056 | `GameUi/default_pages.py` | `find_activity_entry` | `appear_then_click` | `RightActivityAssets.I_TOGGLE_BUTTON` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 活动入口搜索循环里的侧栏展开探测（polling） |
| L2M-057 | `GameUi/default_pages.py` | `handle_activity_overlay` | `appear_then_click` | `GameUiAssets.I_ACTIVITY_SIGNIN_CLOSE` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 导航途中遮挡弹窗清理（recovery） |
| L2M-058 | `GameUi/default_pages.py` | `<module>` | `ui_click` | `?` | IMMEDIATE | **KEEP_SPECIAL** | - | 安全区随机点击关闭界面（页面图 edge 动作，非目标按钮） |
| L2M-059 | `GameUi/default_pages.py` | `exploration_to_six_gates` | `appear_then_click` | `GameUiAssets.I_EXPLORATION_TO_MOON_SEA` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 低频入口（六道之门，6 个互斥图标串联探测）；本轮不为冷门入口改 |
| L2M-060 | `GameUi/default_pages.py` | `exploration_to_six_gates` | `appear_then_click` | `GameUiAssets.I_EXPLORATION_TO_INCENSE_REALM` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 低频入口（六道之门，6 个互斥图标串联探测）；本轮不为冷门入口改 |
| L2M-061 | `GameUi/default_pages.py` | `exploration_to_six_gates` | `appear_then_click` | `GameUiAssets.I_EXPLORATION_TO_SEASONRIFT_FOREST` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 低频入口（六道之门，6 个互斥图标串联探测）；本轮不为冷门入口改 |
| L2M-062 | `GameUi/default_pages.py` | `exploration_to_six_gates` | `appear_then_click` | `GameUiAssets.I_EXPLORATION_TO_PURE_BUDDHA_REALM` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 低频入口（六道之门，6 个互斥图标串联探测）；本轮不为冷门入口改 |
| L2M-063 | `GameUi/default_pages.py` | `exploration_to_six_gates` | `appear_then_click` | `GameUiAssets.I_EXPLORATION_TO_MANTRA_TOWER` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 低频入口（六道之门，6 个互斥图标串联探测）；本轮不为冷门入口改 |
| L2M-064 | `GameUi/default_pages.py` | `exploration_to_six_gates` | `appear_then_click` | `GameUiAssets.I_EXPLORATION_TO_PEACOCK_KINGDOM` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 低频入口（六道之门，6 个互斥图标串联探测）；本轮不为冷门入口改 |
| L2M-065 | `GameUi/default_pages.py` | `handle_battle_reward_page` | `appear_then_click` | `GeneralBattleAssets.I_OVER_GHOST` | IMMEDIATE | **KEEP_SPECIAL** | - | 奖励页弹窗属 Settlement 阶段 |
| L2M-066 | `GameUi/chess_battle.py` | `return_to_chess_lobby` | `appear_then_click` | `self.I_CHESS_RANK_GOTO_LOBBY` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 棋盘退出 / 回大厅恢复序列，Chess 自有 Timer / FAST_OPERATION_INTERVAL |
| L2M-067 | `GameUi/chess_battle.py` | `return_to_chess_lobby` | `click` | `GeneralBattleAssets.C_RANDOM_LEFT` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 棋盘退出 / 回大厅恢复序列，Chess 自有 Timer / FAST_OPERATION_INTERVAL |
| L2M-068 | `GameUi/chess_battle.py` | `return_to_chess_lobby` | `appear_then_click` | `self.I_CHESS_EXIT_TO_LOBBY` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 棋盘退出 / 回大厅恢复序列，Chess 自有 Timer / FAST_OPERATION_INTERVAL |
| L2M-069 | `GameUi/chess_battle.py` | `return_to_chess_lobby` | `appear_then_click` | `self.I_CHESS_EXIT_TO_LOBBY_2` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 棋盘退出 / 回大厅恢复序列，Chess 自有 Timer / FAST_OPERATION_INTERVAL |
| L2M-070 | `GameUi/chess_battle.py` | `return_to_chess_lobby` | `click` | `self.I_CHESS_EXIT_TO_LOBBY` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 棋盘退出 / 回大厅恢复序列，Chess 自有 Timer / FAST_OPERATION_INTERVAL |
| L2M-071 | `GameUi/chess_battle.py` | `return_to_chess_lobby` | `click` | `GeneralBattleAssets.C_RANDOM_LEFT` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 棋盘退出 / 回大厅恢复序列，Chess 自有 Timer / FAST_OPERATION_INTERVAL |
| L2M-072 | `GameUi/chess_battle.py` | `exit_chess_battle` | `click` | `self.I_CHESS_EXIT_CONFIRM` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 棋盘退出 / 回大厅恢复序列，Chess 自有 Timer / FAST_OPERATION_INTERVAL |
| L2M-073 | `GameUi/chess_battle.py` | `exit_chess_battle` | `click` | `self.I_CHESS_EXIT` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 棋盘退出 / 回大厅恢复序列，Chess 自有 Timer / FAST_OPERATION_INTERVAL |
| L2M-074 | `EvoZone/script_task.py` | `evozone_enter` | `appear_then_click` | `kirintype` | DELIBERATE | **ALREADY_L2** | DELIBERATE | L2-1 已迁（麒麟类型选择） |
| L2M-075 | `EvoZone/script_task.py` | `run_leader` | `appear_then_click` | `self.I_FORM_TEAM` | NORMAL | **ALREADY_L2** | NORMAL | L2-1 已迁 |
| L2M-076 | `EvoZone/script_task.py` | `_fire_evozone_alone` | `appear_then_click` | `self.I_EVOZONE_FIRE` | IMMEDIATE | **ALREADY_L2** | FIRE_SPECIAL | FIRE owner |
| L2M-077 | `Orochi/script_task.py` | `_close_orochi_soul_choice_popup` | `appear_then_click` | `self.I_GB_CLOSE_RED` | IMMEDIATE | **KEEP_SPECIAL** | - | 在 `_handle_result` / `_handle_reward` / missing-page 分支调用，属战后结算生命周期 |
| L2M-078 | `Orochi/script_task.py` | `run_leader` | `appear_then_click` | `self.I_FORM_TEAM` | NORMAL | **ALREADY_L2** | NORMAL | L2-1 已迁 |
| L2M-079 | `Orochi/script_task.py` | `run_member` | `appear_then_click` | `self.I_PET_PRESENT` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 偶发猫咪奖励弹窗，点安全区关闭；与 ui_reward_appear_click 同族，未单独立项 |
| L2M-080 | `Orochi/script_task.py` | `_fire_orochi_alone` | `appear_then_click` | `self.I_OROCHI_FIRE` | IMMEDIATE | **ALREADY_L2** | FIRE_SPECIAL | FIRE owner |
| L2M-081 | `Orochi/script_task.py` | `run_alone` | `appear_then_click` | `self.I_PET_PRESENT` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 偶发猫咪奖励弹窗，点安全区关闭；与 ui_reward_appear_click 同族，未单独立项 |
| L2M-082 | `Orochi/script_task.py` | `run_wild` | `appear_then_click` | `self.I_FORM_TEAM` | NORMAL | **ALREADY_L2** | NORMAL | L2-1 已迁 |
| L2M-083 | `Orochi/script_task.py` | `run_wild` | `appear_then_click` | `self.I_PET_PRESENT` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 偶发猫咪奖励弹窗，点安全区关闭；与 ui_reward_appear_click 同族，未单独立项 |
| L2M-084 | `Orochi/script_task.py` | `run_wild` | `appear_then_click` | `self.I_OROCHI_WILD_FIRE` | IMMEDIATE | **KEEP_SPECIAL** | - | L2-3B Batch A：FIRE owner（任务配置 `orochi.fire_reaction`）；资产仍缺 RuleImage（既有断链） |
| L2M-085 | `RealmRaid/script_task.py` | `run` | `appear_then_click` | `self.I_FROG_RAID` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 呱太活动首次进入弹窗（低频），循环直到消失 |
| L2M-086 | `RealmRaid/script_task.py` | `ensure_lock` | `appear_then_click` | `self.I_UNLOCK` | FAST | **ALREADY_L2** | FAST | L2-1 已迁 |
| L2M-087 | `RealmRaid/script_task.py` | `ensure_lock` | `appear_then_click` | `self.I_UNLOCK_2` | FAST | **ALREADY_L2** | FAST | L2-1 已迁 |
| L2M-088 | `RealmRaid/script_task.py` | `ensure_lock` | `appear_then_click` | `self.I_LOCK` | FAST | **ALREADY_L2** | FAST | L2-1 已迁 |
| L2M-089 | `RealmRaid/script_task.py` | `ensure_lock` | `appear_then_click` | `self.I_LOCK_2` | FAST | **ALREADY_L2** | FAST | L2-1 已迁 |
| L2M-090 | `RealmRaid/script_task.py` | `_enter_target` | `click` | `self.partition[order - 1]` | IMMEDIATE | **KEEP_SPECIAL** | - | 目标 pacing owner = RR_TARGET_PACING（L3 业务节奏），不能再叠 reaction |
| L2M-091 | `RealmRaid/script_task.py` | `reward_detect_click` | `ui_click_until_disappear` | `self.I_SOUL_RAID` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 三胜奖励：OCR 遮挡轮询循环；Batch A 已明确排除（有测试锁定） |
| L2M-092 | `RealmRaid/script_task.py` | `reward_detect_click` | `appear_then_click` | `self.I_SOUL_RAID` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 三胜奖励：OCR 遮挡轮询循环；Batch A 已明确排除（有测试锁定） |
| L2M-093 | `RealmRaid/script_task.py` | `check_refresh` | `appear_then_click` | `self.I_FRESH` | NORMAL | **ALREADY_L2** | NORMAL | L2-1 已迁 |
| L2M-094 | `RealmRaid/script_task.py` | `check_refresh` | `appear_then_click` | `self.I_FRESH_ENSURE` | CONFIRM | **ALREADY_L2** | CONFIRM | L2-1 已迁 |
| L2M-095 | `RealmRaid/script_task.py` | `fire` | `click` | `click` | IMMEDIATE | **KEEP_SPECIAL** | - | FIRE FSM 内重新打开目标详情（retryable 分支） |
| L2M-096 | `RealmRaid/script_task.py` | `fire` | `appear_then_click` | `self.I_FIRE` | IMMEDIATE | **ALREADY_L2** | FIRE_SPECIAL | FIRE owner |
| L2M-097 | `RealmRaid/script_task.py` | `_fire_again` | `appear_then_click` | `self.I_SHOW_AGAIN` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 失败结果流程中间复选框：§4.57 明确「无 reaction」 |
| L2M-098 | `RealmRaid/script_task.py` | `_fire_again` | `appear_then_click` | `self.I_FRESH_ENSURE` | confirm_delay | **ALREADY_L2** | legacy RR_AGAIN_CONFIRM_DELAY | 独立弹窗确认区间 (0.3,0.6)，非 profile；静态不能证明与 CONFIRM 等价，不替换 |
| L2M-099 | `RealmRaid/script_task.py` | `_fire_again` | `appear_then_click` | `self.I_FIRE_AGAIN` | IMMEDIATE | **ALREADY_L2** | FIRE_SPECIAL | FIRE owner |
| L2M-100 | `RyouToppa/script_task.py` | `_wait_for_ryou_toppa_state` | `appear_then_click` | `RealmRaidAssets.I_REALM_RAID` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 入口状态等待超时后的有界重点（entry FSM retry） |
| L2M-101 | `RyouToppa/script_task.py` | `_wait_for_ryou_toppa_state` | `appear_then_click` | `self.I_RYOU_TOPPA` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 入口状态等待超时后的有界重点（entry FSM retry） |
| L2M-102 | `RyouToppa/script_task.py` | `_ensure_team_lock_state` | `appear_then_click` | `source` | FAST | **ALREADY_L2** | FAST | L2-1 已迁 |
| L2M-103 | `RyouToppa/script_task.py` | `_click_toppa_area` | `click` | `rule` | IMMEDIATE | **KEEP_SPECIAL** | - | FIRE FSM 内区域点击（L1 C_AREA_1 显式 sample_point） |
| L2M-104 | `RyouToppa/script_task.py` | `start_ryou_toppa` | `appear_then_click` | `self.I_SELECT_RYOU_BUTTON` | FAST | **ALREADY_L2** | FAST | L2-1 已迁 |
| L2M-105 | `RyouToppa/script_task.py` | `start_ryou_toppa` | `appear_then_click` | `self.I_GUILD_ORDERS_REWARDS` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 识别列表标记后点「第一个寮」区域：target 与 action 不同，Batch A 已排除（有测试锁定） |
| L2M-106 | `RyouToppa/script_task.py` | `start_ryou_toppa` | `appear_then_click` | `self.I_START_TOPPA_BUTTON` | FAST | **ALREADY_L2** | FAST | L2-1 已迁 |
| L2M-107 | `RyouToppa/script_task.py` | `attack_area` | `appear_then_click` | `RealmRaidAssets.I_FIRE` | IMMEDIATE | **ALREADY_L2** | FIRE_SPECIAL | FIRE owner |
| L2M-108 | `Exploration/base.py` | `open_expect_level` | `appear_then_click` | `self.I_UI_CONFIRM` | NORMAL | **ALREADY_L2** | NORMAL | L2-1 已迁 |
| L2M-109 | `Exploration/base.py` | `open_expect_level` | `appear_then_click` | `self.I_UI_CONFIRM_SAMLL` | NORMAL | **ALREADY_L2** | NORMAL | L2-1 已迁 |
| L2M-110 | `Exploration/base.py` | `open_expect_level` | `appear_then_click` | `self.I_UI_CONFIRM` | NORMAL | **ALREADY_L2** | NORMAL | L2-1 已迁 |
| L2M-111 | `Exploration/base.py` | `open_expect_level` | `appear_then_click` | `self.I_UI_CONFIRM_SAMLL` | NORMAL | **ALREADY_L2** | NORMAL | L2-1 已迁 |
| L2M-112 | `Exploration/base.py` | `open_expect_level` | `ocr_appear_click` | `self.O_E_EXPLORATION_LEVEL_NUMBER` | IMMEDIATE | **KEEP_IMMEDIATE** | - | OCR 动态目标（章节号），Batch A 排除 |
| L2M-113 | `Exploration/base.py` | `fill_shikigami` | `click` | `self.C_CLICK_STANDBY_TEAM` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 补位区域 / 列表点击，无可重新识别的 appear 目标 |
| L2M-114 | `Exploration/base.py` | `fill_shikigami` | `click` | `self.L_ROTATE_1` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 补位区域 / 列表点击，无可重新识别的 appear 目标 |
| L2M-115 | `Exploration/base.py` | `fire` | `appear_then_click` | `button` | IMMEDIATE | **KEEP_SPECIAL** | - | 探索怪物 battle entry：目标会移动，贪心 FSM（max_tries + Timer）拥有节奏 |
| L2M-116 | `Exploration/base.py` | `switch_rotate` | `click` | `self.C_CLICK_SETTINGS` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 设置区域点击（RuleClick 区域） |
| L2M-117 | `Exploration/base.py` | `collect_treasure_box` | `ui_click` | `self.I_E_REWARD_BOX_SMALL` | IMMEDIATE | **KEEP_IMMEDIATE** | - | ui_click 系 helper 自带点击循环且无 policy 参数；本轮不扩公共 API（后续 L2 设计项）；D021 corrected：Boss 后宝箱流程不重写 |
| L2M-118 | `Exploration/base.py` | `collect_treasure_box` | `ui_click_until_disappear` | `self.I_REWARD` | IMMEDIATE | **KEEP_IMMEDIATE** | - | ui_click 系 helper 自带点击循环且无 policy 参数；本轮不扩公共 API（后续 L2 设计项）；D021 corrected：Boss 后宝箱流程不重写 |
| L2M-119 | `Exploration/base.py` | `collect_treasure_box` | `ui_click` | `self.I_E_REWARD_BOX_BIG` | IMMEDIATE | **KEEP_IMMEDIATE** | - | ui_click 系 helper 自带点击循环且无 policy 参数；本轮不扩公共 API（后续 L2 设计项）；D021 corrected：Boss 后宝箱流程不重写 |
| L2M-120 | `Exploration/base.py` | `collect_treasure_box` | `ui_click_until_disappear` | `self.I_REWARD` | IMMEDIATE | **KEEP_IMMEDIATE** | - | ui_click 系 helper 自带点击循环且无 policy 参数；本轮不扩公共 API（后续 L2 设计项）；D021 corrected：Boss 后宝箱流程不重写 |
| L2M-121 | `Exploration/base.py` | `quit_exp_main` | `appear_then_click` | `self.I_UI_BACK_YELLOW` | NAVIGATION | **ALREADY_L2** | NAVIGATION | L2-1 已迁 |
| L2M-122 | `Exploration/script_task.py` | `exp_page_handle_dict` | `click` | `pages.random_click()` | IMMEDIATE | **KEEP_SPECIAL** | - | 安全区随机点击 |
| L2M-123 | `Exploration/script_task.py` | `exec_exp_page` | `appear_then_click` | `self.I_UI_CANCEL` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 退出时清理队长结束邀请弹窗（teardown），Batch A 排除（有测试锁定） |
| L2M-124 | `Exploration/script_task.py` | `run_on_exp_settings` | `appear_then_click` | `self.I_E_AUTO_ROTATE_OFF` | FAST | **ALREADY_L2** | FAST | L2-1 已迁 |
| L2M-125 | `Exploration/script_task.py` | `run_on_exp_exit` | `appear_then_click` | `self.I_E_EXIT_CANCEL` | NAVIGATION | **ALREADY_L2** | NAVIGATION | L2-1 已迁 |
| L2M-126 | `Exploration/script_task.py` | `run_on_exp_exit` | `appear_then_click` | `self.I_E_EXIT_CONFIRM` | CONFIRM | **ALREADY_L2** | CONFIRM | L2-1 已迁 |
| L2M-127 | `ActivityShikigami/page.py` | `goto_activity_entry` | `appear_then_click` | `ActivityShikigamiAssets.I_MAIN_GOTO_ACT_2` | NAVIGATION | **ALREADY_L2** | NAVIGATION | L2-1 已迁 |
| L2M-128 | `ActivityShikigami/page.py` | `goto_activity_entry` | `appear_then_click` | `ActivityShikigamiAssets.I_MAIN_GOTO_ACT` | NAVIGATION | **ALREADY_L2** | NAVIGATION | L2-1 已迁 |
| L2M-129 | `ActivityShikigami/page.py` | `find_activity_entry` | `appear_then_click` | `RightActivityAssets.I_TOGGLE_BUTTON` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 入口搜索循环侧栏展开（polling） |
| L2M-130 | `ActivityShikigami/page.py` | `handle_activity_close` | `appear_then_click` | `GlobalGameAssets.I_UI_BACK_RED` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 活动页遮挡关闭（recovery） |
| L2M-131 | `ActivityShikigami/page.py` | `handle_activity_story` | `appear_then_click` | `ActivityShikigamiAssets.I_SKIP_BUTTON` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 剧情跳过对话（低频、首次进入） |
| L2M-132 | `ActivityShikigami/page.py` | `handle_activity_story` | `appear_then_click` | `ActivityShikigamiAssets.I_CONFIRM_SKIP` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 剧情跳过对话（低频、首次进入） |
| L2M-133 | `ActivityShikigami/page.py` | `handle_activity_story` | `appear_then_click` | `ActivityShikigamiAssets.I_CONFIRM_SKIP` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 剧情跳过对话（低频、首次进入） |
| L2M-134 | `ActivityShikigami/page.py` | `handle_activity_overlay` | `appear_then_click` | `ActivityShikigamiAssets.I_ACTIVITY_SIGNIN_CLOSE` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 签到遮挡关闭（recovery） |
| L2M-135 | `ActivityShikigami/base_act.py` | `_handle_result` | `appear_then_click` | `self.I_UI_BACK_RED` | IMMEDIATE | **KEEP_SPECIAL** | - | Boss 结算页返回，属战斗结果生命周期 |
| L2M-136 | `ActivityShikigami/base_act.py` | `switch_soul_for` | `ui_click` | `enter_button` | IMMEDIATE | **KEEP_IMMEDIATE** | - | ui_click 系 helper 自带点击循环且无 policy 参数；本轮不扩公共 API（后续 L2 设计项） |
| L2M-137 | `ActivityShikigami/activities/normal.py` | `_run_climb_type` | `click` | `pages.random_click(ltrb=(False, False, True, False))` | IMMEDIATE | **KEEP_SPECIAL** | - | 安全区随机点击 |
| L2M-138 | `ActivityShikigami/activities/normal.py` | `_sync_climb_penta_pass` | `click` | `click_rule` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 五连通行状态同步区域点击（按状态判定，无 appear 目标） |
| L2M-139 | `ActivityShikigami/activities/normal.py` | `_enter_climb_battle` | `appear_then_click` | `self.I_UI_CONFIRM_SAMLL` | IMMEDIATE | **KEEP_SPECIAL** | - | FIRE battle-entry FSM 内资源确认弹窗（§4.62），归 FIRE owner |
| L2M-140 | `ActivityShikigami/activities/normal.py` | `_enter_climb_battle` | `appear_then_click` | `self.I_UI_CONFIRM` | IMMEDIATE | **KEEP_SPECIAL** | - | FIRE battle-entry FSM 内资源确认弹窗（§4.62），归 FIRE owner |
| L2M-141 | `ActivityShikigami/activities/normal.py` | `_enter_climb_battle` | `appear_then_click` | `fire_rule` | IMMEDIATE | **ALREADY_L2** | FIRE_SPECIAL | FIRE owner |
| L2M-142 | `ActivityShikigami/activities/normal.py` | `_sync_climb_team_lock` | `ui_click` | `unlock_rule` | IMMEDIATE | **KEEP_IMMEDIATE** | - | ui_click 系 helper 自带点击循环且无 policy 参数；本轮不扩公共 API（后续 L2 设计项） |
| L2M-143 | `ActivityShikigami/activities/normal.py` | `_sync_climb_team_lock` | `ui_click` | `lock_rule` | IMMEDIATE | **KEEP_IMMEDIATE** | - | ui_click 系 helper 自带点击循环且无 policy 参数；本轮不扩公共 API（后续 L2 设计项） |
| L2M-144 | `ActivityShikigami/activities/fake_god.py` | `run_fakegod` | `click` | `pages.random_click(ltrb=(False, False, True, False))` | IMMEDIATE | **KEEP_SPECIAL** | - | 安全区随机点击 |
| L2M-145 | `ActivityShikigami/activities/fake_god.py` | `_enter_fakegod_battle` | `appear_then_click` | `self.I_UI_CONFIRM_SAMLL` | IMMEDIATE | **KEEP_SPECIAL** | - | Battle Entry 语义但伪神降临线仍是旧 while True（D001 §4.62 未改）；待 FIRE contract 收口 |
| L2M-146 | `ActivityShikigami/activities/fake_god.py` | `_enter_fakegod_battle` | `appear_then_click` | `self.I_UI_CONFIRM` | IMMEDIATE | **KEEP_SPECIAL** | - | Battle Entry 语义但伪神降临线仍是旧 while True（D001 §4.62 未改）；待 FIRE contract 收口 |
| L2M-147 | `ActivityShikigami/activities/fake_god.py` | `_enter_fakegod_battle` | `appear_then_click` | `self.I_FG_ACT_FIRE` | IMMEDIATE | **KEEP_SPECIAL** | - | Battle Entry 语义但伪神降临线仍是旧 while True（D001 §4.62 未改）；待 FIRE contract 收口 |
| L2M-148 | `ActivityShikigami/activities/fake_god.py` | `_sync_fakegod_team_lock` | `ui_click` | `self.I_FG_UNLOCK` | IMMEDIATE | **KEEP_IMMEDIATE** | - | ui_click 系 helper 自带点击循环且无 policy 参数；本轮不扩公共 API（后续 L2 设计项） |
| L2M-149 | `ActivityShikigami/activities/fake_god.py` | `_sync_fakegod_team_lock` | `ui_click` | `self.I_FG_LOCK` | IMMEDIATE | **KEEP_IMMEDIATE** | - | ui_click 系 helper 自带点击循环且无 policy 参数；本轮不扩公共 API（后续 L2 设计项） |
| L2M-150 | `ActivityShikigami/activities/rich_man.py` | `enter_board` | `appear_then_click` | `task.I_RM_TO_BATTLE_MAIN` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 入口前已有 RICHMAN_ENTRY_SETTLE_SECONDS 等待 owner，再加 reaction 会叠加 |
| L2M-151 | `ActivityShikigami/activities/rich_man.py` | `run_rich_man` | `appear_then_click` | `self.I_UI_CONFIRM` | IMMEDIATE | **KEEP_SPECIAL** | - | 大富翁掷骰主循环确认，由掷骰 FSM 拥有节奏 |
| L2M-152 | `ActivityShikigami/activities/rich_man.py` | `_throw_until_dice_count_changes` | `click` | `self.C_RM_RANDOM_CLOSE_SAFE_MAIN` | IMMEDIATE | **KEEP_SPECIAL** | - | 掷骰 FSM（等骰子数变化）拥有节奏 |
| L2M-153 | `ActivityShikigami/activities/rich_man.py` | `_throw_until_dice_count_changes` | `appear_then_click` | `self.I_RM_THROW` | IMMEDIATE | **KEEP_SPECIAL** | - | 掷骰 FSM（等骰子数变化）拥有节奏 |
| L2M-154 | `ActivityShikigami/activities/rich_man.py` | `_run_throw_task` | `appear_then_click` | `self.I_RM_THROW_FIGHT` | IMMEDIATE | **KEEP_SPECIAL** | - | 掷骰任务：战斗入口 + 确认，属掷骰 / battle entry FSM |
| L2M-155 | `ActivityShikigami/activities/rich_man.py` | `_run_throw_task` | `appear_then_click` | `self.I_UI_CONFIRM` | IMMEDIATE | **KEEP_SPECIAL** | - | 掷骰任务：战斗入口 + 确认，属掷骰 / battle entry FSM |
| L2M-156 | `ActivityShikigami/activities/rich_man.py` | `_run_throw_task` | `appear_then_click` | `self.I_UI_CONFIRM_SAMLL` | IMMEDIATE | **KEEP_SPECIAL** | - | 掷骰任务：战斗入口 + 确认，属掷骰 / battle entry FSM |
| L2M-157 | `ActivityShikigami/activities/rich_man.py` | `_run_rob_task` | `click` | `choice` | IMMEDIATE | **KEEP_SPECIAL** | - | 抢夺选择区域点击（业务随机选择） |
| L2M-158 | `ActivityShikigami/activities/rich_man.py` | `_close_boss_level_up` | `click` | `self.C_RM_RANDOM_CLOSE_SAFE` | IMMEDIATE | **KEEP_IMMEDIATE** | - | 升级弹窗安全区关闭 |
| L2M-159 | `ActivityShikigami/activities/rich_man.py` | `_click_rich_man_challenge` | `appear_then_click` | `challenge_button` | IMMEDIATE | **KEEP_SPECIAL** | - | Boss 挑战 = Battle Entry 语义，旧流程未收口 FIRE |
| L2M-160 | `ActivityShikigami/activities/rich_man.py` | `_sync_rich_man_team_lock` | `ui_click` | `self.I_RM_MAIN_UNLOCK` | IMMEDIATE | **KEEP_IMMEDIATE** | - | ui_click 系 helper 自带点击循环且无 policy 参数；本轮不扩公共 API（后续 L2 设计项） |
| L2M-161 | `ActivityShikigami/activities/rich_man.py` | `_sync_rich_man_team_lock` | `ui_click` | `self.I_RM_MAIN_LOCK` | IMMEDIATE | **KEEP_IMMEDIATE** | - | ui_click 系 helper 自带点击循环且无 policy 参数；本轮不扩公共 API（后续 L2 设计项） |
| L2M-162 | `ActivityShikigami/activities/rich_man.py` | `_wait_for_stable_throw_before_next_round` | `appear_then_click` | `self.I_UI_CONFIRM` | IMMEDIATE | **KEEP_SPECIAL** | - | 下一轮前稳定等待循环内确认（掷骰 FSM） |
| L2M-163 | `ActivityShikigami/activities/rich_man.py` | `_wait_for_stable_throw_before_next_round` | `appear_then_click` | `self.I_UI_CONFIRM_SAMLL` | IMMEDIATE | **KEEP_SPECIAL** | - | 下一轮前稳定等待循环内确认（掷骰 FSM） |
| L2M-164 | `KekkaiUtilize/script_task.py` | `check_max_lv` | `ui_click` | `self.I_AUTO_FILL` | IMMEDIATE | **KEEP_IMMEDIATE** | - | KekkaiUtilize 受保护路径（harvest / auto_replace_max_level / D017 选卡 / quiet scheduler 附近），不为 L2 覆盖率改 |
| L2M-165 | `KekkaiUtilize/script_task.py` | `check_and_get_guild_rewards` | `appear_then_click` | `self.I_GUILD_EXPAND` | IMMEDIATE | **KEEP_IMMEDIATE** | - | KekkaiUtilize 受保护路径（harvest / auto_replace_max_level / D017 选卡 / quiet scheduler 附近），不为 L2 覆盖率改 |
| L2M-166 | `KekkaiUtilize/script_task.py` | `check_and_get_guild_rewards` | `appear_then_click` | `self.I_GUILD_ASSETS_RECEIVE` | IMMEDIATE | **KEEP_IMMEDIATE** | - | KekkaiUtilize 受保护路径（harvest / auto_replace_max_level / D017 选卡 / quiet scheduler 附近），不为 L2 覆盖率改 |
| L2M-167 | `KekkaiUtilize/script_task.py` | `check_and_get_guild_rewards` | `appear_then_click` | `self.I_GUILD_ASSETS` | IMMEDIATE | **KEEP_IMMEDIATE** | - | KekkaiUtilize 受保护路径（harvest / auto_replace_max_level / D017 选卡 / quiet scheduler 附近），不为 L2 覆盖率改 |
| L2M-168 | `KekkaiUtilize/script_task.py` | `check_and_get_guild_rewards` | `appear_then_click` | `self.I_GUILD_AP` | IMMEDIATE | **KEEP_IMMEDIATE** | - | KekkaiUtilize 受保护路径（harvest / auto_replace_max_level / D017 选卡 / quiet scheduler 附近），不为 L2 覆盖率改 |
| L2M-169 | `KekkaiUtilize/script_task.py` | `guild_lottery` | `ui_click_until_appear_or_timeout` | `self.I_GUILD_LOTTERY` | IMMEDIATE | **KEEP_IMMEDIATE** | - | KekkaiUtilize 受保护路径（harvest / auto_replace_max_level / D017 选卡 / quiet scheduler 附近），不为 L2 覆盖率改 |
| L2M-170 | `KekkaiUtilize/script_task.py` | `guild_lottery` | `click` | `self.C_UI_REWARD` | IMMEDIATE | **KEEP_IMMEDIATE** | - | KekkaiUtilize 受保护路径（harvest / auto_replace_max_level / D017 选卡 / quiet scheduler 附近），不为 L2 覆盖率改 |
| L2M-171 | `KekkaiUtilize/script_task.py` | `guild_lottery` | `appear_then_click` | `self.I_UI_BACK_YELLOW` | IMMEDIATE | **KEEP_IMMEDIATE** | - | KekkaiUtilize 受保护路径（harvest / auto_replace_max_level / D017 选卡 / quiet scheduler 附近），不为 L2 覆盖率改 |
| L2M-172 | `KekkaiUtilize/script_task.py` | `_harvest_ap_box` | `ui_click_until_smt_disappear` | `self.C_UI_REWARD` | IMMEDIATE | **KEEP_IMMEDIATE** | - | KekkaiUtilize 受保护路径（harvest / auto_replace_max_level / D017 选卡 / quiet scheduler 附近），不为 L2 覆盖率改 |
| L2M-173 | `KekkaiUtilize/script_task.py` | `_harvest_ap_box` | `appear_then_click` | `self.I_AP_EXTRACT` | IMMEDIATE | **KEEP_IMMEDIATE** | - | KekkaiUtilize 受保护路径（harvest / auto_replace_max_level / D017 选卡 / quiet scheduler 附近），不为 L2 覆盖率改 |
| L2M-174 | `KekkaiUtilize/script_task.py` | `_harvest_exp_jug` | `ui_click_until_disappear` | `target_button` | IMMEDIATE | **KEEP_IMMEDIATE** | - | KekkaiUtilize 受保护路径（harvest / auto_replace_max_level / D017 选卡 / quiet scheduler 附近），不为 L2 覆盖率改 |
| L2M-175 | `KekkaiUtilize/script_task.py` | `_harvest_exp_jug` | `click` | `self.I_EXP_EXTRACT` | IMMEDIATE | **KEEP_IMMEDIATE** | - | KekkaiUtilize 受保护路径（harvest / auto_replace_max_level / D017 选卡 / quiet scheduler 附近），不为 L2 覆盖率改 |
| L2M-176 | `KekkaiUtilize/script_task.py` | `_run_search_pass` | `click` | `self.C_SELECT_CARD` | IMMEDIATE | **KEEP_IMMEDIATE** | - | KekkaiUtilize 受保护路径（harvest / auto_replace_max_level / D017 选卡 / quiet scheduler 附近），不为 L2 覆盖率改 |
| L2M-177 | `KekkaiUtilize/script_task.py` | `_select_lazy_resource_card` | `click` | `self.C_SELECT_CARD` | IMMEDIATE | **KEEP_IMMEDIATE** | - | KekkaiUtilize 受保护路径（harvest / auto_replace_max_level / D017 选卡 / quiet scheduler 附近），不为 L2 覆盖率改 |
| L2M-178 | `KekkaiUtilize/page.py` | `<module>` | `appear_then_click` | `KekkaiUtilizeAssets.I_BOX_EXP` | IMMEDIATE | **KEEP_IMMEDIATE** | - | harvest 使用的经验酒壶页面 edge；KekkaiUtilize 受保护路径（harvest / auto_replace_max_level / D017 选卡 / quiet scheduler 附近），不为 L2 覆盖率改 |
| L2M-179 | `KekkaiUtilize/page.py` | `<module>` | `appear_then_click` | `KekkaiUtilizeAssets.I_BOX_EXP_MAX` | IMMEDIATE | **KEEP_IMMEDIATE** | - | harvest 使用的经验酒壶页面 edge；KekkaiUtilize 受保护路径（harvest / auto_replace_max_level / D017 选卡 / quiet scheduler 附近），不为 L2 覆盖率改 |

## 4. C0 全仓剩余 24 点复核与 C1-A1 实施状态（2026-09-21）

C0 复核（外部审查报告，原文不在仓库里，逐点结论已归档进 `dev_tools/click_callsite_register.py` 的 `C1_MIGRATED` / `C0_TRIAGE`）针对全仓登记册里原 24 个 NEEDS_C，建议 MIGRATE 10 / KEEP_IMMEDIATE 3 / KEEP_SPECIAL 4 / NEEDS_C 7。
随后 **C1-A1 实施了 MIGRATE 里确认的 4 处**；用户决定其余 6 处 MIGRATE 与 7 处 NEEDS_C **暂缓，不继续开发**。**技术分类（decision）与开发排期（dev_status）分开记录，不能相加**：
`DEFERRED` 是用户排期，不是技术完成，也不是永久禁止；`NEEDS_C + DEFERRED` 表示技术上需要真机依据、且用户暂缓，不得自动迁移。

**当前没有获批的 L2 功能开发任务。** 最终状态（24 = 4 + 6 + 3 + 4 + 7）：

| 状态 | 数量 | decision | dev_status |
| --- | ---: | --- | --- |
| 已完成迁移（C1-A1） | 4 | ALREADY_L2 | COMPLETED |
| C0 建议 MIGRATE、用户暂缓 | 6 | DEFERRED | DEFERRED |
| 保持即时 | 3 | KEEP_IMMEDIATE | NOT_APPLICABLE |
| 保持专用时序 | 4 | KEEP_SPECIAL | NOT_APPLICABLE |
| 需 Level C 依据、用户暂缓 | 7 | NEEDS_C | DEFERRED |

### 4.1 已完成（C1-A1，Level C 待验，reaction 区间仍是 PROVISIONAL）

| ID | 文件 | 函数 | 目标 | 原 timing | 新 policy | reaction（秒） | fresh confirm 失败后的业务分支 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C1A1-01 | `Dokan/page.py` | `priority_enter_dokan` | 动态 `target_priority` | IMMEDIATE | **NORMAL** | 0.45~0.85 | 返回 `False`，由 Navigator 6s 预算内原重试路径接管 |
| C1A1-02 | `Pets/script_task.py` | `_feed`（已投喂分支） | `I_UI_BACK_CIRCLE` | IMMEDIATE | **NAVIGATION** | 0.55~1.10 | 不点，仍 `goto_page(page_main)` 收口 |
| C1A1-03 | `SixRealms/common.py` | `refresh_store` | 动态 `refresh_rule` | IMMEDIATE | **CONFIRM** | 0.55~1.20 | 返回 `False`（原代码已检查返回值），不进动画等待 / 不误报刷新成功；`buy_skill` 随之 `break` |
| C1A1-04 | `SixRealms/common.py` | `choose_and_enter_island` | 动态 `target_land` | IMMEDIATE | **NORMAL** | 0.45~0.85 | 不点旧坐标、不改选其它岛屿，外层下一轮重新扫描 |

### 4.2 用户暂缓（C0 建议 MIGRATE；代码里仍是立即点击，decision=DEFERRED）

| 文件 | 函数 | 目标 | C0 建议 | 暂缓期间的边界 |
| --- | --- | --- | --- | --- |
| `Duel/script_task.py` | `enter_practice_ban_mode` | `I_BATTLE_WITH_TRAIN` / `I_BATTLE_WITH_TRAIN2` | NORMAL | 保持即时；不改 `or` 短路逻辑与原 2 秒页面等待 |
| `SixRealms/peacock_kingdom/peacock_kingdom.py` | `_summon_store` | `I_M_STORE_ACTIVITY` | NORMAL | 不实施 reaction；不改 coin 更新条件与 readiness timeout |
| 同上 | `_summon_store` | `I_UI_CONFIRM` | CONFIRM | 同上 |
| 同上 | `_use_breath` | `I_M_STORE_ACTIVITY` | NORMAL | 同上 |
| 同上 | `_confirm_store_entry` | `I_PK_STORE_STILLIN` | CONFIRM | 同上 |

### 4.3 保持即时（KEEP_IMMEDIATE，已有明确结论，不是迁移积压）

| 文件 | 函数 | 目标 | 理由 |
| --- | --- | --- | --- |
| `DemonRetreat/script_task.py` | `run` | `I_DEMON_BACK_CHECK` | 失败恢复 |
| `Quiz/script_task.py` | `_deal_quiz` | `I_ALONE_ENSURE` | 倒计时敏感 |
| `SixRealms/common.py` | `open_shop` | `I_UI_CANCEL` | 超时恢复 |

### 4.4 保持专用时序（KEEP_SPECIAL，已有独立 timing owner）

| 文件 | 函数 | 目标 | 原因 |
| --- | --- | --- | --- |
| `Component/Buy/buy.py` | `buy_more` | `I_BUY_PLUS`（两处） | 连续加量节奏；两次点击之间原有 0.5 秒等待保留，不拆成两次 NORMAL |
| `SixRealms/page.py` | `switch_moon_sea_shikigami` | `I_MSHOUZU_SELECT` | Navigator 单次进入 hook，不改 hook 语义 |
| `SixRealms/peacock_kingdom/base_peacock_kingdom.py` | `_mark_peacock_boss` | `I_LOCAL` | 首领标记专用事务，原有 0.3 秒 settle 保留 |

### 4.5 技术上需要 Level C 依据、且用户暂缓（NEEDS_C + DEFERRED）

| 文件 | 函数 | 目标 | 原因 |
| --- | --- | --- | --- |
| `Component/GeneralInvite/general_invite.py` | `check_then_accept` | `I_I_NO_DEFAULT` / `I_GI_SURE` / `I_I_ACCEPT_DEFAULT` / `I_I_ACCEPT` / `I_I_ACCEPT_APPRENTICE` | 五个候选共享接受邀请事务：逐按钮加 reaction 会重复等待；队长秒开有时效风险；当前接受循环缺少明确墙钟上限。日后重启应先设计事务级 reaction 与有界状态确认 |
| `Component/GeneralBattle/general_battle.py` | `_handle_prepare` | `I_DISABLE_7DAYS_DIFF_SOUL` / `I_CONFIRM_CLOSE_DIFF_SOUL` | 准备页 FSM：可能受准备倒计时影响，不能直接套普通 CONFIRM；不得干扰组队就绪 / 进入战斗；与 Settlement 独立 |

### 4.6 统计对账

登记册（`docs/L2_CALLSITE_REGISTER.md` §2 / §2.4）：1092 = MIGRATE 7 + ALREADY_L2 37 + KEEP_IMMEDIATE 630 + KEEP_SPECIAL 232 + NEEDS_C 7 + DEFERRED 6 + PRIMITIVE 35 + EXCLUDED 138（互斥、可加总）；
basis：human 179 / c0 17 / rule 896（互斥、可加总；`c0_reviewed` = 24 是独立维度，GeneralInvite / GeneralBattle 的 7 点决定来源仍是 human，所以 c0 basis = 4 + 6 + 3 + 4 = 17）。
