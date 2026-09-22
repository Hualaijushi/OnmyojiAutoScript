# L2 Callsite Register（全仓生产点击入口登记册）

> 由 `dev_tools/click_callsite_register.py --write` 生成，**不要手改**；`tests/test_click_callsite_register.py` 把本表的汇总数字与
> 当前源码扫描逐项对账，新增 / 删除点击调用点会让测试失败，必须重新分类并重新生成。
> 分类术语沿用 `docs/L2_INTERACTION_POLICY_MAP.md`；逐点人工审计的 18 个文件见该文档，本表对它们沿用人工结论（basis=`human`）。

## 1. 口径与分类来源

- 统计范围：`tasks/` + `module/` 下所有生产代码里的点击入口调用（`device.click` 裸点、后端直调、`execute_single_click`、
  `self.click(<Rule>)` 与 BaseTask 的 `appear_then_click` / `ui_click*` / `ocr_appear_click` / `list_appear_click` 等 helper）；不含 tests / dev_tools。
- **basis=human**：L2-2 人工逐点审计；**basis=c0**：决定来源是 L2 Stage C0 复核的点位（已迁移的 4 点在 `C1_MIGRATED`，其余在 `C0_TRIAGE` 逐点归档，对不上源码直接报错）；**basis=rule**：其余模块的**保守规则分类**（默认保持立即点击，不因规则判定加 reaction），
  只能证明「每个点击调用点都有归属且默认不改变原有 timing」，**不是**逐点人工审计。
- 分类互斥：每个调用点恰属于下表 7 个 decision 之一（可加总）。「已迁移 L1」「已接入 L2 policy」是另一个维度（见 §2 覆盖统计），
  与 decision 有交叉，不能与 decision 相加。

## 2. 汇总

- 调用点总数：**1127**
- 按 basis：human **180** / c0 **17** / rule **930**
- 显式调用 `execute_single_click` 的调用点：**47**（其中 BaseTask primitive **9**）。**这不是「享受 ROI 采样的点击数」**：  Rule / helper 点击（约 900 处）早在 `Rule*.coord()` 内按 ROI 采样一次，并经 BaseTask primitive 汇入统一执行器。
- 仍是裸 `device.click` / 后端直调：**5** = 底层与非点击 4 + BaseTask primitive 0 + 生产消费点 0 + 项目排除 1。
- 已显式声明 L2 `policy=`：**36**；仍用 legacy `confirm_delay=`：**3**

| decision | 数量 |
| --- | ---: |
| MIGRATE | 7 |
| ALREADY_L2 | 37 |
| KEEP_IMMEDIATE | 631 |
| KEEP_SPECIAL | 232 |
| NEEDS_C | 7 |
| DEFERRED | 6 |
| PRIMITIVE | 35 |
| EXCLUDED | 172 |
| **合计** | **1127** |

### 2.1 按调用种类

| kind | 数量 |
| --- | ---: |
| appear_then_click | 507 |
| click | 240 |
| ui_click | 155 |
| ui_click_until_disappear | 91 |
| execute_single_click | 47 |
| ui_reward_appear_click | 27 |
| ocr_appear_click | 23 |
| ui_get_reward | 18 |
| ui_click_until_smt_disappear | 6 |
| ui_click_until_appear_or_timeout | 6 |
| raw_backend | 3 |
| raw_device_click | 2 |
| list_appear_click | 2 |

### 2.2 长按入口（L1 Stage 3A）

长按是独立的物理动作，走 `execute_long_click`，不并入上面的单击统计。生产消费点（consumer）里出现的任何直调都是绕过 L1 的长按。

| kind | area | 数量 |
| --- | --- | ---: |
| execute_long_click | primitive | 6 |
| raw_long_backend | device_internal | 1 |
| raw_long_click | device_internal | 1 |
| raw_long_click | executor | 1 |

### 2.3 全局入口守卫（L1 Stage 3B，`dev_tools/click_entry_guard.py`）

- 扫描范围：生产根目录 rglob + 仓库根 `*.py`（新增文件自动纳入，文件数不写进登记册以免无关改动使其失效）；未登记的直接点击 / 长按违规：**0**；过期白名单 / 缺失必需出口 / 无法静态确定：**0 / 0 / 0**。
- 白名单出口（精确到 文件 / 函数 / 调用形式 / 次数，不按文件或目录豁免；Login / DailyTrifles / WeeklyPurchase 没有豁免）：
  backend 3，control 13，dead 1，demo 2，executor 3，exempt 1。
- 守卫只证明「没有绕过执行器的直接调用」；业务点击是否执行成功 / 坐标分布由运行期测试负责。滑动 / 拖动不在守卫范围。

### 2.4 C0 复核批次（L2 Stage C0 → C1-A1）与开发状态

- **两个维度，不可相加**：`decision` = 技术分类（互斥、可加总，见 §2 表）；`dev_status` = 开发排期（只对 C0 复核的点位有意义：COMPLETED / DEFERRED / NOT_APPLICABLE）。`NEEDS_C` + `DEFERRED` = 技术上需要真机依据、且用户决定暂缓；`decision=DEFERRED` = C0 技术建议为 MIGRATE、但用户决定暂缓（原建议保留在下表「C0 建议」列）。**DEFERRED 是用户排期决策，不是技术完成，也不是永久禁止。**
- **口径区分**：全仓点击调用点 **1127**（本表）；最初 L2-2 人工审计 **180**（basis=human，历史结论不改写）；C0 复核的原 NEEDS_C **24**（`c0_reviewed`，与 basis 不是互斥维度：其中 GeneralInvite / GeneralBattle 7 点的决定来源仍是 human）；C1-A1 已实际迁移 **4**。
- **basis 统计**（互斥、可加总）：human **180** / c0 **17** / rule **930**。
- **C0 24 点的开发状态**：COMPLETED **4** / DEFERRED **13**（decision=DEFERRED 6 + decision=NEEDS_C 7） / NOT_APPLICABLE **7**（KEEP_IMMEDIATE 3 + KEEP_SPECIAL 4，已有明确决策，不属于迁移积压）。

| # | 文件 | 函数 | 目标 | C0 建议 | decision | dev_status | 说明 |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | `Dokan/page.py` | `priority_enter_dokan` | `target_priority` | NORMAL | ALREADY_L2 | COMPLETED | C1-A1 已实施 |
| 2 | `Pets/script_task.py` | `_feed` | `self.I_UI_BACK_CIRCLE` | NAVIGATION | ALREADY_L2 | COMPLETED | C1-A1 已实施 |
| 3 | `SixRealms/common.py` | `refresh_store` | `refresh_rule` | CONFIRM | ALREADY_L2 | COMPLETED | C1-A1 已实施 |
| 4 | `SixRealms/common.py` | `choose_and_enter_island` | `target_land` | NORMAL | ALREADY_L2 | COMPLETED | C1-A1 已实施 |
| 5 | `Component/GeneralBattle/general_battle.py` | `_handle_prepare` | `self.I_DISABLE_7DAYS_DIFF_SOUL` | - | NEEDS_C | DEFERRED | 准备页 FSM：可能受准备倒计时影响，不能直接套普通 CONFIRM，不得干扰组队就绪 / 进入战斗；与 Settlement 独立 |
| 6 | `Component/GeneralBattle/general_battle.py` | `_handle_prepare` | `self.I_CONFIRM_CLOSE_DIFF_SOUL` | - | NEEDS_C | DEFERRED | 同上（准备页 FSM） |
| 7 | `Component/GeneralInvite/general_invite.py` | `check_then_accept` | `self.I_I_NO_DEFAULT` | - | NEEDS_C | DEFERRED | 接受邀请事务：五个候选共享同一事务，逐按钮加 reaction 会重复等待；队长秒开有时效风险；接受循环缺少明确墙钟上限。重启前应先设计事务级 reaction 与有界状态确认 |
| 8 | `Component/GeneralInvite/general_invite.py` | `check_then_accept` | `self.I_GI_SURE` | - | NEEDS_C | DEFERRED | 同上（接受邀请事务） |
| 9 | `Component/GeneralInvite/general_invite.py` | `check_then_accept` | `self.I_I_ACCEPT_DEFAULT` | - | NEEDS_C | DEFERRED | 同上（接受邀请事务） |
| 10 | `Component/GeneralInvite/general_invite.py` | `check_then_accept` | `self.I_I_ACCEPT` | - | NEEDS_C | DEFERRED | 同上（接受邀请事务） |
| 11 | `Component/GeneralInvite/general_invite.py` | `check_then_accept` | `self.I_I_ACCEPT_APPRENTICE` | - | NEEDS_C | DEFERRED | 同上（接受邀请事务） |
| 12 | `Duel/script_task.py` | `enter_practice_ban_mode` | `self.I_BATTLE_WITH_TRAIN` | MIGRATE / NORMAL | DEFERRED | DEFERRED | 练习入口：保持即时点击，不改 `or` 短路逻辑与原 2 秒页面等待 |
| 13 | `Duel/script_task.py` | `enter_practice_ban_mode` | `self.I_BATTLE_WITH_TRAIN2` | MIGRATE / NORMAL | DEFERRED | DEFERRED | 练习入口：保持即时点击，不改 `or` 短路逻辑与原 2 秒页面等待 |
| 14 | `SixRealms/peacock_kingdom/peacock_kingdom.py` | `_summon_store` | `self.I_M_STORE_ACTIVITY` | MIGRATE / NORMAL | DEFERRED | DEFERRED | 商店事务：不实施 reaction，不改 coin 更新条件与 readiness timeout |
| 15 | `SixRealms/peacock_kingdom/peacock_kingdom.py` | `_summon_store` | `self.I_UI_CONFIRM` | MIGRATE / CONFIRM | DEFERRED | DEFERRED | 商店事务：不实施 reaction，不改 coin 更新条件与 readiness timeout |
| 16 | `SixRealms/peacock_kingdom/peacock_kingdom.py` | `_use_breath` | `self.I_M_STORE_ACTIVITY` | MIGRATE / NORMAL | DEFERRED | DEFERRED | 商店事务：不实施 reaction，不改 coin 更新条件与 readiness timeout |
| 17 | `SixRealms/peacock_kingdom/peacock_kingdom.py` | `_confirm_store_entry` | `self.I_PK_STORE_STILLIN` | MIGRATE / CONFIRM | DEFERRED | DEFERRED | 商店事务：不实施 reaction，不改 coin 更新条件与 readiness timeout |
| 18 | `DemonRetreat/script_task.py` | `run` | `self.I_DEMON_BACK_CHECK` | - | KEEP_IMMEDIATE | NOT_APPLICABLE | 失败恢复路径，保持即时 |
| 19 | `Quiz/script_task.py` | `_deal_quiz` | `self.I_ALONE_ENSURE` | - | KEEP_IMMEDIATE | NOT_APPLICABLE | 答题倒计时敏感，保持即时 |
| 20 | `SixRealms/common.py` | `open_shop` | `self.I_UI_CANCEL` | - | KEEP_IMMEDIATE | NOT_APPLICABLE | 超时恢复路径，保持即时 |
| 21 | `Component/Buy/buy.py` | `buy_more` | `self.I_BUY_PLUS` | - | KEEP_SPECIAL | NOT_APPLICABLE | 连续加量节奏：第一次点击；两次之间原有 0.5 秒等待保留 |
| 22 | `Component/Buy/buy.py` | `buy_more` | `self.I_BUY_PLUS` | - | KEEP_SPECIAL | NOT_APPLICABLE | 连续加量节奏：与第一次共享业务节奏，不拆成两次 NORMAL |
| 23 | `SixRealms/page.py` | `switch_moon_sea_shikigami` | `SixRealmsAssets.I_MSHOUZU_SELECT` | - | KEEP_SPECIAL | NOT_APPLICABLE | Navigator 单次进入 hook，不改 hook 语义 |
| 24 | `SixRealms/peacock_kingdom/base_peacock_kingdom.py` | `_mark_peacock_boss` | `self.I_LOCAL` | - | KEEP_SPECIAL | NOT_APPLICABLE | 首领标记专用事务，原有 0.3 秒 settle 保留 |

## 3. 按模块

| module | 合计 | MIGRATE | ALREADY_L2 | KEEP_IMMEDIATE | KEEP_SPECIAL | NEEDS_C | DEFERRED | PRIMITIVE | EXCLUDED |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SixRealms | 72 | 0 | 2 | 10 | 56 | 0 | 4 | 0 | 0 |
| DailyTrifles | 57 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 57 |
| WeeklyPurchase | 55 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 55 |
| ActivityShikigami | 43 | 0 | 3 | 20 | 20 | 0 | 0 | 0 | 0 |
| WantedQuests | 41 | 0 | 0 | 41 | 0 | 0 | 0 | 0 | 0 |
| AbyssShadows | 32 | 0 | 0 | 32 | 0 | 0 | 0 | 0 | 0 |
| Dokan | 31 | 0 | 1 | 25 | 5 | 0 | 0 | 0 | 0 |
| tasks/Component/SwitchAccount | 31 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 31 |
| BondlingFairyland | 30 | 0 | 0 | 27 | 3 | 0 | 0 | 0 | 0 |
| base_task.py | 30 | 0 | 0 | 0 | 0 | 0 | 0 | 30 | 0 |
| tasks/Component/GeneralInvite | 29 | 4 | 1 | 12 | 7 | 5 | 0 | 0 | 0 |
| DemonEncounter | 28 | 0 | 0 | 28 | 0 | 0 | 0 | 0 | 0 |
| SoulsTidy | 28 | 0 | 0 | 22 | 6 | 0 | 0 | 0 | 0 |
| tasks/Component/GeneralBattle | 27 | 3 | 2 | 11 | 9 | 2 | 0 | 0 | 0 |
| GameUi | 26 | 0 | 0 | 22 | 4 | 0 | 0 | 0 | 0 |
| AreaBoss | 24 | 0 | 0 | 20 | 4 | 0 | 0 | 0 | 0 |
| Duel | 24 | 0 | 0 | 17 | 5 | 0 | 2 | 0 | 0 |
| MartialArts | 22 | 0 | 0 | 19 | 3 | 0 | 0 | 0 | 0 |
| Exploration | 20 | 0 | 8 | 9 | 3 | 0 | 0 | 0 | 0 |
| KekkaiUtilize | 20 | 0 | 0 | 16 | 4 | 0 | 0 | 0 | 0 |
| tasks/Component/Login | 20 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 20 |
| MetaDemon | 19 | 0 | 0 | 19 | 0 | 0 | 0 | 0 | 0 |
| WeeklyTrifles | 18 | 0 | 0 | 16 | 2 | 0 | 0 | 0 | 0 |
| tasks/Component/Buy | 18 | 0 | 0 | 16 | 2 | 0 | 0 | 0 | 0 |
| Chess | 17 | 0 | 0 | 0 | 17 | 0 | 0 | 0 | 0 |
| DemonRetreat | 17 | 0 | 0 | 17 | 0 | 0 | 0 | 0 | 0 |
| KittyShop | 17 | 0 | 0 | 17 | 0 | 0 | 0 | 0 | 0 |
| tasks/Component/GeneralBuff | 17 | 0 | 0 | 16 | 1 | 0 | 0 | 0 | 0 |
| Hyakkiyakou | 16 | 0 | 0 | 0 | 16 | 0 | 0 | 0 | 0 |
| MemoryScrolls | 16 | 0 | 0 | 16 | 0 | 0 | 0 | 0 | 0 |
| HeroTest | 15 | 0 | 0 | 7 | 8 | 0 | 0 | 0 | 0 |
| RealmRaid | 15 | 0 | 9 | 4 | 2 | 0 | 0 | 0 | 0 |
| Delegation | 14 | 0 | 0 | 7 | 7 | 0 | 0 | 0 | 0 |
| KekkaiActivation | 13 | 0 | 0 | 5 | 8 | 0 | 0 | 0 | 0 |
| Quiz | 12 | 0 | 0 | 12 | 0 | 0 | 0 | 0 | 0 |
| CollectiveMissions | 11 | 0 | 0 | 8 | 3 | 0 | 0 | 0 | 0 |
| TrueOrochi | 11 | 0 | 0 | 11 | 0 | 0 | 0 | 0 | 0 |
| FloatParade | 10 | 0 | 0 | 9 | 1 | 0 | 0 | 0 | 0 |
| FrogBoss | 10 | 0 | 0 | 10 | 0 | 0 | 0 | 0 | 0 |
| TalismanPass | 10 | 0 | 0 | 7 | 3 | 0 | 0 | 0 | 0 |
| tasks/Component/SwitchSoul | 10 | 0 | 0 | 9 | 1 | 0 | 0 | 0 | 0 |
| FallenSun | 9 | 0 | 0 | 0 | 9 | 0 | 0 | 0 | 0 |
| MultiAccountEvo | 9 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 9 |
| Orochi | 9 | 0 | 3 | 3 | 3 | 0 | 0 | 0 | 0 |
| RyouToppa | 9 | 0 | 4 | 3 | 2 | 0 | 0 | 0 | 0 |
| DyeTrials | 8 | 0 | 0 | 8 | 0 | 0 | 0 | 0 | 0 |
| tasks/Component/GeneralRoom | 8 | 0 | 0 | 7 | 1 | 0 | 0 | 0 | 0 |
| tasks/Component/QuickLoadout | 8 | 0 | 0 | 7 | 1 | 0 | 0 | 0 | 0 |
| tasks/Component/ReplaceShikigami | 8 | 0 | 0 | 8 | 0 | 0 | 0 | 0 | 0 |
| Hunt | 7 | 0 | 0 | 7 | 0 | 0 | 0 | 0 | 0 |
| MysteryShop | 7 | 0 | 0 | 4 | 3 | 0 | 0 | 0 | 0 |
| tasks/Component/Costume | 7 | 0 | 0 | 7 | 0 | 0 | 0 | 0 | 0 |
| GuguArtStudio | 6 | 0 | 0 | 5 | 1 | 0 | 0 | 0 | 0 |
| tasks/Component/Summon | 6 | 0 | 0 | 4 | 2 | 0 | 0 | 0 | 0 |
| EternitySea | 5 | 0 | 0 | 0 | 5 | 0 | 0 | 0 | 0 |
| EvoZone | 5 | 0 | 3 | 1 | 1 | 0 | 0 | 0 | 0 |
| Nian | 5 | 0 | 0 | 5 | 0 | 0 | 0 | 0 | 0 |
| module | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 0 |
| tasks/Component/SwitchOnmyoji | 5 | 0 | 0 | 5 | 0 | 0 | 0 | 0 | 0 |
| Pets | 4 | 0 | 1 | 3 | 0 | 0 | 0 | 0 | 0 |
| Secret | 4 | 0 | 0 | 4 | 0 | 0 | 0 | 0 | 0 |
| tasks/Component/RightActivity | 4 | 0 | 0 | 3 | 1 | 0 | 0 | 0 | 0 |
| GoryouRealm | 3 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 0 |
| GuildBanquet | 3 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 0 |
| Sougenbi | 3 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 0 |
| OtherWorldTwilight | 2 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 |
| tasks/Component/CostumeBattle | 2 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 |

## 4. 理由代码

| 代码 | 含义 |
| --- | --- |
| R0 | 点击 primitive / Device 管线层自身的实现 |
| R1 | 项目决定 / 分支归属明确排除（仅限 L2 reaction 迁移；L1 点击执行入口不豁免） |
| R2 | 已显式声明 policy / confirm_delay（单一 reaction owner） |
| R3 | 受保护业务：已有独立 timing owner（状态机 / FIRE / 调度 / 小游戏） |
| R4 | 函数语义属恢复 / 关闭 / 奖励 / 退出 / 收取 / 防挂机 / 页面状态处理，由所在流程拥有 timing |
| R5 | 裸坐标 / 后端点击：没有可重新识别的目标，不能做 fresh confirm |
| R6 | `self.click(<RuleClick>)` 固定区域点击：无 appear 目标，primitive 无 policy 参数 |
| R7 | ui_click 系 / 其它 helper 自带点击循环且无 policy 参数，本轮不扩公共 API |
| R8 | 轮询循环内的探测式点击（interval / 超时预算），reaction 会吃掉循环预算；无真机证据不加 |
| R9 | 非循环内的单次 appear_then_click：可能适合 reaction，页面时效 / 节奏无法静态判断 → 等真机 |
| R10 | L1 管线点击（FinalPoint / Bounds / Region）：坐标语义已显式声明，无 reaction 语义 |
| H | L2-2 逐点人工审计结论（见 docs/L2_INTERACTION_POLICY_MAP.md） |
| C1 | L2 Stage C0 复核后已迁移到显式 policy（C1-A1，见 docs/L2_INTERACTION_POLICY_MAP.md） |
| C0K | L2 Stage C0 复核结论：保持即时点击（失败恢复 / 倒计时敏感 / 超时恢复），不是迁移积压 |
| C0S | L2 Stage C0 复核结论：已有专用 timing owner（业务节奏 / Navigator hook / 专用事务），不加普通 policy |
| C0D | L2 Stage C0 建议迁移，但用户决定暂缓（开发排期，不是技术完成；原建议保存在 C0 表） |

## 5. 逐点清单

列：`#` 序号 / 文件 / 函数#函数内第几个点击调用点（不写行号，避免无关改动让登记册失效）/ 调用 / 目标 / timing（当前延迟来源）/ 循环内 / 函数内已有等待 / decision / 依据。
「状态机」列不单独给出：由 decision=KEEP_SPECIAL 与理由 R3 / R4 表达。


### AbyssShadows

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 1 | `AbyssShadows/script_task.py` | `ScriptTask.check_current_area#1` | click | `self.I_ABYSS_MAP_EXIT` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 2 | `AbyssShadows/script_task.py` | `ScriptTask.check_current_area#2` | click | `self.I_ABYSS_ENEMY_INFO_EXIT` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 3 | `AbyssShadows/script_task.py` | `ScriptTask.change_area#1` | click | `self.I_ABYSS_MAP_EXIT` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 4 | `AbyssShadows/script_task.py` | `ScriptTask.change_area#2` | click | `self.I_ABYSS_ENEMY_INFO_EXIT` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 5 | `AbyssShadows/script_task.py` | `ScriptTask.change_area#3` | appear_then_click | `self.I_CHANGE_AREA` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 6 | `AbyssShadows/script_task.py` | `ScriptTask.select_boss#1` | click | `self.C_ABYSS_DRAGON` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 7 | `AbyssShadows/script_task.py` | `ScriptTask.select_boss#2` | click | `self.C_ABYSS_PEACOCK` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 8 | `AbyssShadows/script_task.py` | `ScriptTask.select_boss#3` | click | `self.C_ABYSS_FOX` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 9 | `AbyssShadows/script_task.py` | `ScriptTask.select_boss#4` | click | `self.C_ABYSS_LEOPARD` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 10 | `AbyssShadows/script_task.py` | `ScriptTask.goto_enemy#1` | click | `click_area` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R6 |
| 11 | `AbyssShadows/script_task.py` | `ScriptTask.goto_enemy#2` | appear_then_click | `self.I_ENSURE_BUTTON` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R8 |
| 12 | `AbyssShadows/script_task.py` | `ScriptTask.goto_enemy#3` | click | `self.I_ENSURE_BUTTON` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R6 |
| 13 | `AbyssShadows/script_task.py` | `ScriptTask.goto_enemy#4` | click | `self.I_ABYSS_GOTO_ENEMY` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R6 |
| 14 | `AbyssShadows/script_task.py` | `ScriptTask.attack_enemy#1` | click | `self.I_ENSURE_BUTTON` | IMMEDIATE | Y | Timer,wait_until | KEEP_IMMEDIATE | rule/R6 |
| 15 | `AbyssShadows/script_task.py` | `ScriptTask.attack_enemy#2` | click | `self.I_ABYSS_ENEMY_FIRE` | IMMEDIATE | Y | Timer,wait_until | KEEP_IMMEDIATE | rule/R6 |
| 16 | `AbyssShadows/script_task.py` | `ScriptTask.attack_enemy#3` | click | `self.I_ABYSS_FIRE` | IMMEDIATE | Y | Timer,wait_until | KEEP_IMMEDIATE | rule/R6 |
| 17 | `AbyssShadows/script_task.py` | `ScriptTask.start_abyss_shadows#1` | ui_click | `self.I_SELECT_DIFFICULTY` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 18 | `AbyssShadows/script_task.py` | `ScriptTask.start_abyss_shadows#2` | ui_click_until_disappear | `difficulty_btn` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 19 | `AbyssShadows/script_task.py` | `ScriptTask.start_abyss_shadows#3` | ui_click | `self.I_BTN_START` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 20 | `AbyssShadows/script_task.py` | `ScriptTask.start_abyss_shadows#4` | ui_click_until_disappear | `self.I_START_ENSURE` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 21 | `AbyssShadows/script_task.py` | `ScriptTask.open_navigation#1` | click | `self.I_ABYSS_NAVIGATION` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 22 | `AbyssShadows/script_task.py` | `ScriptTask.open_navigation#2` | click | `self.I_ABYSS_ENEMY_INFO_EXIT` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 23 | `AbyssShadows/script_task.py` | `ScriptTask.run_battle#1` | ui_click_until_disappear | `self.I_PREPARE_HIGHLIGHT` | IMMEDIATE | - | Timer,wait_until | KEEP_IMMEDIATE | rule/R7 |
| 24 | `AbyssShadows/script_task.py` | `ScriptTask.run_battle#2` | click | `self.C_MARK_MAIN` | IMMEDIATE | Y | Timer,wait_until | KEEP_IMMEDIATE | rule/R6 |
| 25 | `AbyssShadows/script_task.py` | `ScriptTask.run_battle#3` | appear_then_click | `self.I_PREPARE_HIGHLIGHT` | IMMEDIATE | Y | Timer,wait_until | KEEP_IMMEDIATE | rule/R8 |
| 26 | `AbyssShadows/script_task.py` | `ScriptTask.run_battle#4` | appear_then_click | `self.I_WIN` | IMMEDIATE | Y | Timer,wait_until | KEEP_IMMEDIATE | rule/R8 |
| 27 | `AbyssShadows/script_task.py` | `ScriptTask.run_battle#5` | appear_then_click | `self.I_REWARD` | IMMEDIATE | Y | Timer,wait_until | KEEP_IMMEDIATE | rule/R8 |
| 28 | `AbyssShadows/script_task.py` | `ScriptTask.quit_battle#1` | click | `self.I_EXIT_ENSURE` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R6 |
| 29 | `AbyssShadows/script_task.py` | `ScriptTask.quit_battle#2` | click | `self.I_WIN` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R6 |
| 30 | `AbyssShadows/script_task.py` | `ScriptTask.quit_battle#3` | click | `self.I_REWARD` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R6 |
| 31 | `AbyssShadows/script_task.py` | `ScriptTask.quit_battle#4` | click | `self.I_EXIT` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R6 |
| 32 | `AbyssShadows/script_task.py` | `ScriptTask.check_available#1` | click | `self.I_ABYSS_NAVIGATION` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |

### ActivityShikigami

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 33 | `ActivityShikigami/activities/fake_god.py` | `FakeGodAct.run_fakegod#1` | click | `pages.random_click(ltrb=(False, False, True, False))` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | human/H |
| 34 | `ActivityShikigami/activities/fake_god.py` | `FakeGodAct._enter_fakegod_battle#1` | appear_then_click | `self.I_UI_CONFIRM_SAMLL` | IMMEDIATE | Y | - | KEEP_SPECIAL | human/H |
| 35 | `ActivityShikigami/activities/fake_god.py` | `FakeGodAct._enter_fakegod_battle#2` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | - | KEEP_SPECIAL | human/H |
| 36 | `ActivityShikigami/activities/fake_god.py` | `FakeGodAct._enter_fakegod_battle#3` | appear_then_click | `self.I_FG_ACT_FIRE` | IMMEDIATE | Y | - | KEEP_SPECIAL | human/H |
| 37 | `ActivityShikigami/activities/fake_god.py` | `FakeGodAct._sync_fakegod_team_lock#1` | ui_click | `self.I_FG_UNLOCK` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 38 | `ActivityShikigami/activities/fake_god.py` | `FakeGodAct._sync_fakegod_team_lock#2` | ui_click | `self.I_FG_LOCK` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 39 | `ActivityShikigami/activities/normal.py` | `NormalClimbAct._run_climb_type#1` | click | `pages.random_click(ltrb=(False, False, True, False))` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | human/H |
| 40 | `ActivityShikigami/activities/normal.py` | `NormalClimbAct._sync_climb_penta_pass#1` | click | `click_rule` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | human/H |
| 41 | `ActivityShikigami/activities/normal.py` | `NormalClimbAct._enter_climb_battle#1` | appear_then_click | `self.I_UI_CONFIRM_SAMLL` | IMMEDIATE | Y | Timer,random_delay,sleep | KEEP_SPECIAL | human/H |
| 42 | `ActivityShikigami/activities/normal.py` | `NormalClimbAct._enter_climb_battle#2` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | Timer,random_delay,sleep | KEEP_SPECIAL | human/H |
| 43 | `ActivityShikigami/activities/normal.py` | `NormalClimbAct._enter_climb_battle#3` | appear_then_click | `fire_rule` | IMMEDIATE | Y | Timer,random_delay,sleep | ALREADY_L2 | human/H |
| 44 | `ActivityShikigami/activities/normal.py` | `NormalClimbAct._sync_climb_team_lock#1` | ui_click | `unlock_rule` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 45 | `ActivityShikigami/activities/normal.py` | `NormalClimbAct._sync_climb_team_lock#2` | ui_click | `lock_rule` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 46 | `ActivityShikigami/activities/rich_man.py` | `RichManAct.setup_rich_man_pages.enter_board#1` | appear_then_click | `task.I_RM_TO_BATTLE_MAIN` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | human/H |
| 47 | `ActivityShikigami/activities/rich_man.py` | `RichManAct.run_rich_man#1` | ui_reward_appear_click | `?` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R7 |
| 48 | `ActivityShikigami/activities/rich_man.py` | `RichManAct.run_rich_man#2` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | human/H |
| 49 | `ActivityShikigami/activities/rich_man.py` | `RichManAct._throw_until_dice_count_changes#1` | click | `self.C_RM_RANDOM_CLOSE_SAFE_MAIN` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | human/H |
| 50 | `ActivityShikigami/activities/rich_man.py` | `RichManAct._throw_until_dice_count_changes#2` | appear_then_click | `self.I_RM_THROW` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | human/H |
| 51 | `ActivityShikigami/activities/rich_man.py` | `RichManAct._run_throw_task#1` | appear_then_click | `self.I_RM_THROW_FIGHT` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | human/H |
| 52 | `ActivityShikigami/activities/rich_man.py` | `RichManAct._run_throw_task#2` | ui_reward_appear_click | `?` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R7 |
| 53 | `ActivityShikigami/activities/rich_man.py` | `RichManAct._run_throw_task#3` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | human/H |
| 54 | `ActivityShikigami/activities/rich_man.py` | `RichManAct._run_throw_task#4` | appear_then_click | `self.I_UI_CONFIRM_SAMLL` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | human/H |
| 55 | `ActivityShikigami/activities/rich_man.py` | `RichManAct._run_rob_task#1` | click | `choice` | IMMEDIATE | - | sleep | KEEP_SPECIAL | human/H |
| 56 | `ActivityShikigami/activities/rich_man.py` | `RichManAct._close_boss_level_up#1` | click | `self.C_RM_RANDOM_CLOSE_SAFE` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | human/H |
| 57 | `ActivityShikigami/activities/rich_man.py` | `RichManAct._enter_boss_fight_by_anchor#1` | execute_single_click | `self.device` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R10 |
| 58 | `ActivityShikigami/activities/rich_man.py` | `RichManAct._click_rich_man_challenge#1` | appear_then_click | `challenge_button` | IMMEDIATE | - | - | KEEP_SPECIAL | human/H |
| 59 | `ActivityShikigami/activities/rich_man.py` | `RichManAct._sync_rich_man_team_lock#1` | ui_click | `self.I_RM_MAIN_UNLOCK` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 60 | `ActivityShikigami/activities/rich_man.py` | `RichManAct._sync_rich_man_team_lock#2` | ui_click | `self.I_RM_MAIN_LOCK` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 61 | `ActivityShikigami/activities/rich_man.py` | `RichManAct._wait_for_stable_throw_before_next_round#1` | ui_reward_appear_click | `?` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R7 |
| 62 | `ActivityShikigami/activities/rich_man.py` | `RichManAct._wait_for_stable_throw_before_next_round#2` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | human/H |
| 63 | `ActivityShikigami/activities/rich_man.py` | `RichManAct._wait_for_stable_throw_before_next_round#3` | appear_then_click | `self.I_UI_CONFIRM_SAMLL` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | human/H |
| 64 | `ActivityShikigami/base_act.py` | `BaseAct._handle_result#1` | appear_then_click | `self.I_UI_BACK_RED` | IMMEDIATE | - | - | KEEP_SPECIAL | human/H |
| 65 | `ActivityShikigami/base_act.py` | `BaseAct.switch_soul_for#1` | ui_click | `enter_button` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 66 | `ActivityShikigami/page.py` | `goto_activity_entry#1` | appear_then_click | `ActivityShikigamiAssets.I_MAIN_GOTO_ACT_2` | NAVIGATION | - | - | ALREADY_L2 | human/H |
| 67 | `ActivityShikigami/page.py` | `goto_activity_entry#2` | appear_then_click | `ActivityShikigamiAssets.I_MAIN_GOTO_ACT` | NAVIGATION | - | - | ALREADY_L2 | human/H |
| 68 | `ActivityShikigami/page.py` | `find_activity_entry#1` | appear_then_click | `RightActivityAssets.I_TOGGLE_BUTTON` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | human/H |
| 69 | `ActivityShikigami/page.py` | `handle_activity_reward#1` | click | `click` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 70 | `ActivityShikigami/page.py` | `handle_activity_close#1` | appear_then_click | `GlobalGameAssets.I_UI_BACK_RED` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 71 | `ActivityShikigami/page.py` | `handle_activity_story#1` | appear_then_click | `ActivityShikigamiAssets.I_SKIP_BUTTON` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | human/H |
| 72 | `ActivityShikigami/page.py` | `handle_activity_story#2` | appear_then_click | `ActivityShikigamiAssets.I_CONFIRM_SKIP` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | human/H |
| 73 | `ActivityShikigami/page.py` | `handle_activity_story#3` | appear_then_click | `ActivityShikigamiAssets.I_CONFIRM_SKIP` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | human/H |
| 74 | `ActivityShikigami/page.py` | `handle_activity_overlay#1` | click | `click` | IMMEDIATE | Y | Timer,sleep | KEEP_SPECIAL | rule/R4 |
| 75 | `ActivityShikigami/page.py` | `handle_activity_overlay#2` | appear_then_click | `ActivityShikigamiAssets.I_ACTIVITY_SIGNIN_CLOSE` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | human/H |

### AreaBoss

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 76 | `AreaBoss/script_task.py` | `ScriptTask.boss#1` | click | `self.C_AB_FAMOUS_BTN` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R6 |
| 77 | `AreaBoss/script_task.py` | `ScriptTask.boss#2` | appear_then_click | `self.I_FILTER` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R8 |
| 78 | `AreaBoss/script_task.py` | `ScriptTask.boss#3` | ui_click | `battle` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 79 | `AreaBoss/script_task.py` | `ScriptTask.boss#4` | appear_then_click | `self.I_FIRE` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R8 |
| 80 | `AreaBoss/script_task.py` | `ScriptTask.boss#5` | ui_click | `self.I_AB_CLOSE_RED` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 81 | `AreaBoss/script_task.py` | `ScriptTask.boss_fight#1` | ui_click_until_disappear | `self.I_AB_CLOSE_RED` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 82 | `AreaBoss/script_task.py` | `ScriptTask.boss_fight#2` | ui_click_until_disappear | `self.I_AB_CLOSE_RED` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 83 | `AreaBoss/script_task.py` | `ScriptTask.boss_fight#3` | ui_click_until_disappear | `self.I_AB_CLOSE_RED` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 84 | `AreaBoss/script_task.py` | `ScriptTask.boss_fight#4` | ui_click_until_disappear | `self.I_AB_CLOSE_RED` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 85 | `AreaBoss/script_task.py` | `ScriptTask.start_fight#1` | appear_then_click | `self.I_FIRE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 86 | `AreaBoss/script_task.py` | `ScriptTask.switch_difficulty#1` | click | `_from` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 87 | `AreaBoss/script_task.py` | `ScriptTask.switch_to_floor_1#1` | ui_click | `self.C_AB_JI_FLOOR_SELECTED` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 88 | `AreaBoss/script_task.py` | `ScriptTask.switch_to_floor_1#2` | click | `self.I_AB_JI_FLOOR_ONE` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R6 |
| 89 | `AreaBoss/script_task.py` | `ScriptTask.switch_to_floor_10#1` | ui_click | `self.C_AB_JI_FLOOR_SELECTED` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 90 | `AreaBoss/script_task.py` | `ScriptTask.switch_to_floor_10#2` | click | `self.I_AB_JI_FLOOR_TEN` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R6 |
| 91 | `AreaBoss/script_task.py` | `ScriptTask.fight_reward_boss#1` | ui_click_until_disappear | `self.I_AB_CLOSE_RED` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R4 |
| 92 | `AreaBoss/script_task.py` | `ScriptTask.fight_reward_boss#2` | ui_click_until_disappear | `self.I_AB_CLOSE_RED` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R4 |
| 93 | `AreaBoss/script_task.py` | `ScriptTask.fight_reward_boss#3` | ui_click_until_disappear | `self.I_AB_CLOSE_RED` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 94 | `AreaBoss/script_task.py` | `ScriptTask.get_hot_in_reward.check_boss#1` | ui_click_until_disappear | `self.I_AB_CLOSE_RED` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 95 | `AreaBoss/script_task.py` | `ScriptTask.open_boss_detail#1` | click | `battle` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R6 |
| 96 | `AreaBoss/script_task.py` | `ScriptTask.open_filter#1` | ui_click | `self.I_FILTER` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 97 | `AreaBoss/script_task.py` | `ScriptTask.switch_to_collect#1` | click | `self.C_AB_COLLECTION_BTN` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 98 | `AreaBoss/script_task.py` | `ScriptTask.switch_to_famous#1` | click | `self.C_AB_FAMOUS_BTN` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 99 | `AreaBoss/script_task.py` | `ScriptTask.switch_to_reward#1` | click | `self.C_AB_REWARD_BTN` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R4 |

### base_task.py

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 100 | `base_task.py` | `BaseTask._burst#1` | appear_then_click | `click_button` | IMMEDIATE | Y | - | PRIMITIVE | rule/R0 |
| 101 | `base_task.py` | `BaseTask.appear_then_click#1` | execute_single_click | `self.device` | IMMEDIATE | - | Timer,random_delay,sleep | PRIMITIVE | rule/R0 |
| 102 | `base_task.py` | `BaseTask.appear_then_click#2` | execute_single_click | `self.device` | IMMEDIATE | - | Timer,random_delay,sleep | PRIMITIVE | rule/R0 |
| 103 | `base_task.py` | `BaseTask.appear_then_click#3` | execute_single_click | `self.device` | IMMEDIATE | - | Timer,random_delay,sleep | PRIMITIVE | rule/R0 |
| 104 | `base_task.py` | `BaseTask.appear_then_click#4` | execute_single_click | `self.device` | IMMEDIATE | - | Timer,random_delay,sleep | PRIMITIVE | rule/R0 |
| 105 | `base_task.py` | `BaseTask.wait_until_appear_then_click#1` | execute_single_click | `self.device` | IMMEDIATE | - | wait_until | PRIMITIVE | rule/R0 |
| 106 | `base_task.py` | `BaseTask.wait_until_appear_then_click#2` | execute_single_click | `self.device` | IMMEDIATE | - | wait_until | PRIMITIVE | rule/R0 |
| 107 | `base_task.py` | `BaseTask.click#1` | execute_single_click | `self.device` | IMMEDIATE | - | Timer | PRIMITIVE | rule/R0 |
| 108 | `base_task.py` | `BaseTask.ocr_appear_click#1` | click | `action` | IMMEDIATE | - | - | PRIMITIVE | rule/R0 |
| 109 | `base_task.py` | `BaseTask.ocr_appear_click#2` | execute_single_click | `self.device` | IMMEDIATE | - | - | PRIMITIVE | rule/R0 |
| 110 | `base_task.py` | `BaseTask.list_appear_click#1` | execute_single_click | `self.device` | IMMEDIATE | - | Timer | PRIMITIVE | rule/R0 |
| 111 | `base_task.py` | `BaseTask.ui_reward_appear_click#1` | appear_then_click | `self.I_UI_REWARD` | IMMEDIATE | - | - | PRIMITIVE | rule/R0 |
| 112 | `base_task.py` | `BaseTask.ui_get_reward#1` | ui_reward_appear_click | `?` | IMMEDIATE | Y | Timer,sleep | PRIMITIVE | rule/R0 |
| 113 | `base_task.py` | `BaseTask.ui_get_reward#2` | ui_reward_appear_click | `?` | IMMEDIATE | Y | Timer,sleep | PRIMITIVE | rule/R0 |
| 114 | `base_task.py` | `BaseTask.ui_get_reward#3` | appear_then_click | `click_image` | IMMEDIATE | Y | Timer,sleep | PRIMITIVE | rule/R0 |
| 115 | `base_task.py` | `BaseTask.ui_get_reward#4` | ocr_appear_click | `click_image` | IMMEDIATE | Y | Timer,sleep | PRIMITIVE | rule/R0 |
| 116 | `base_task.py` | `BaseTask.ui_get_reward#5` | click | `click_image` | IMMEDIATE | Y | Timer,sleep | PRIMITIVE | rule/R0 |
| 117 | `base_task.py` | `BaseTask.ui_click#1` | appear_then_click | `click` | IMMEDIATE | Y | - | PRIMITIVE | rule/R0 |
| 118 | `base_task.py` | `BaseTask.ui_click#2` | click | `click` | IMMEDIATE | Y | - | PRIMITIVE | rule/R0 |
| 119 | `base_task.py` | `BaseTask.ui_click#3` | ocr_appear_click | `click` | IMMEDIATE | Y | - | PRIMITIVE | rule/R0 |
| 120 | `base_task.py` | `BaseTask.ui_clicks#1` | appear_then_click | `click` | IMMEDIATE | Y | - | PRIMITIVE | rule/R0 |
| 121 | `base_task.py` | `BaseTask.ui_clicks#2` | click | `click` | IMMEDIATE | Y | - | PRIMITIVE | rule/R0 |
| 122 | `base_task.py` | `BaseTask.ui_clicks#3` | ocr_appear_click | `click` | IMMEDIATE | Y | - | PRIMITIVE | rule/R0 |
| 123 | `base_task.py` | `BaseTask.ui_click_until_disappear#1` | appear_then_click | `click` | IMMEDIATE | Y | - | PRIMITIVE | rule/R0 |
| 124 | `base_task.py` | `BaseTask.ui_click_until_appear_or_timeout#1` | appear_then_click | `click` | IMMEDIATE | Y | Timer | PRIMITIVE | rule/R0 |
| 125 | `base_task.py` | `BaseTask.ui_click_until_appear_or_timeout#2` | click | `click` | IMMEDIATE | Y | Timer | PRIMITIVE | rule/R0 |
| 126 | `base_task.py` | `BaseTask.ui_click_until_appear_or_timeout#3` | ocr_appear_click | `click` | IMMEDIATE | Y | Timer | PRIMITIVE | rule/R0 |
| 127 | `base_task.py` | `BaseTask.ui_click_until_smt_disappear#1` | appear_then_click | `click` | IMMEDIATE | Y | - | PRIMITIVE | rule/R0 |
| 128 | `base_task.py` | `BaseTask.ui_click_until_smt_disappear#2` | click | `click` | IMMEDIATE | Y | - | PRIMITIVE | rule/R0 |
| 129 | `base_task.py` | `BaseTask.ui_click_until_smt_disappear#3` | click | `click` | IMMEDIATE | Y | - | PRIMITIVE | rule/R0 |

### BondlingFairyland

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 130 | `BondlingFairyland/script_task.py` | `ScriptTask._handle_result#1` | appear_then_click | `self.I_CAP_AGAIN` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 131 | `BondlingFairyland/script_task.py` | `ScriptTask._handle_result#2` | appear_then_click | `self.I_BATTLE_FAIL_ABANDON` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 132 | `BondlingFairyland/script_task.py` | `ScriptTask._handle_result#3` | click | `random_click()` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 133 | `BondlingFairyland/script_task.py` | `ScriptTask.run#1` | ui_click | `self.I_MALL_SCCALES` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 134 | `BondlingFairyland/script_task.py` | `ScriptTask.run#2` | ui_click | `self.I_MALL_BONDLINGS_SURE` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 135 | `BondlingFairyland/script_task.py` | `ScriptTask.run_leader.create_bond_team#1` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 136 | `BondlingFairyland/script_task.py` | `ScriptTask.run_leader.create_bond_team#2` | appear_then_click | `self.I_CREATE_TEAM` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 137 | `BondlingFairyland/script_task.py` | `ScriptTask.run_leader.create_bond_team#3` | appear_then_click | `self.I_BALL_HELP` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 138 | `BondlingFairyland/script_task.py` | `ScriptTask.run_stone#1` | ui_click_until_disappear | `self.I_STONE_CLOSE` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R7 |
| 139 | `BondlingFairyland/script_task.py` | `ScriptTask.run_stone#2` | ui_click_until_disappear | `self.I_STONE_CLOSE` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R7 |
| 140 | `BondlingFairyland/script_task.py` | `ScriptTask.run_stone#3` | appear_then_click | `self.I_BUY_PLUS` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 141 | `BondlingFairyland/script_task.py` | `ScriptTask.run_stone#4` | appear_then_click | `self.I_GI_SURE` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 142 | `BondlingFairyland/script_task.py` | `ScriptTask.run_stone#5` | appear_then_click | `self.I_STONE_SURE` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 143 | `BondlingFairyland/script_task.py` | `ScriptTask.ball_click#1` | click | `click_target` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 144 | `BondlingFairyland/script_task.py` | `ScriptTask.goto_ball_area#1` | appear_then_click | `self.I_BALL_AREA` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 145 | `BondlingFairyland/script_task.py` | `ScriptTask.goto_ball_area#2` | ui_click | `get_click_area(index)` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 146 | `BondlingFairyland/script_task.py` | `ScriptTask.capture_setting#1` | ui_click | `self.I_CLICK_CAPTION` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 147 | `BondlingFairyland/script_task.py` | `ScriptTask.capture_setting#2` | ui_click | `self.I_C_AUTO_FALSE` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 148 | `BondlingFairyland/script_task.py` | `ScriptTask.capture_setting#3` | ui_click | `self.I_C_MINIMAL_MODE_DISABLE` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 149 | `BondlingFairyland/script_task.py` | `ScriptTask.capture_setting#4` | ui_click | `target_false` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 150 | `BondlingFairyland/script_task.py` | `ScriptTask.capture_setting#5` | ui_click_until_disappear | `target_continuous` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 151 | `BondlingFairyland/script_task.py` | `ScriptTask.capture_setting#6` | ui_click_until_disappear | `target_first` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 152 | `BondlingFairyland/script_task.py` | `ScriptTask.capture_setting#7` | ui_click_until_disappear | `self.I_CAPTION_ENSURE` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 153 | `BondlingFairyland/script_task.py` | `ScriptTask.lock_team#1` | appear_then_click | `self.I_BALL_UNLOCK` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 154 | `BondlingFairyland/script_task.py` | `ScriptTask.lock_team#2` | appear_then_click | `self.I_BF_UNLOCK` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 155 | `BondlingFairyland/script_task.py` | `ScriptTask.run_alone#1` | appear_then_click | `self.I_BALL_FIRE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 156 | `BondlingFairyland/script_task.py` | `ScriptTask.run_alone#2` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 157 | `BondlingFairyland/script_task.py` | `ScriptTask.click_search#1` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 158 | `BondlingFairyland/script_task.py` | `ScriptTask.click_search#2` | appear_then_click | `self.I_UI_CONFIRM_SAMLL` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 159 | `BondlingFairyland/script_task.py` | `ScriptTask.click_search#3` | appear_then_click | `self.I_BF_SEARSH` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |

### Chess

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 160 | `Chess/runtime/economy.py` | `ChessEconomyMixin._ensure_shop_open#1` | click | `self.I_MARKET` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | rule/R3 |
| 161 | `Chess/runtime/economy.py` | `ChessEconomyMixin._ensure_battle_economy_shop_open#1` | click | `self.I_MARKET` | IMMEDIATE | - | sleep | KEEP_SPECIAL | rule/R3 |
| 162 | `Chess/runtime/economy.py` | `ChessEconomyMixin._ensure_shop_closed#1` | click | `self.I_MARKET` | IMMEDIATE | - | sleep | KEEP_SPECIAL | rule/R3 |
| 163 | `Chess/runtime/economy.py` | `ChessEconomyMixin._ensure_shop_closed#2` | click | `self.I_MARKET` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | rule/R3 |
| 164 | `Chess/runtime/economy.py` | `ChessEconomyMixin._buy_shop_slot#1` | click | `click_rule` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | rule/R3 |
| 165 | `Chess/runtime/economy.py` | `ChessEconomyMixin._click_economy_button_and_confirm_gold#1` | click | `button` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | rule/R3 |
| 166 | `Chess/runtime/economy.py` | `ChessEconomyMixin._click_shop_refresh_and_confirm_slots#1` | click | `self.I_REFRESH` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | rule/R3 |
| 167 | `Chess/runtime/hand_operations.py` | `ChessHandOperationsMixin.close_shikigami_specifics_if_open#1` | click | `self.C_CLICK_CLOSE_SPECIFICS_AREA` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R3 |
| 168 | `Chess/runtime/hand_operations.py` | `ChessHandOperationsMixin._handle_goldfish_after_board_action_failure#1` | click | `inspect_rule` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R3 |
| 169 | `Chess/runtime/hand_operations.py` | `ChessHandOperationsMixin.discover_souls_from_hand#1` | execute_single_click | `self.device` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | rule/R3 |
| 170 | `Chess/runtime/hand_operations.py` | `ChessHandOperationsMixin.discover_souls_from_hand#2` | appear_then_click | `self.I_USE_SOUL` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | rule/R3 |
| 171 | `Chess/runtime/hand_operations.py` | `ChessHandOperationsMixin.discover_souls_from_hand#3` | click | `selected` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | rule/R3 |
| 172 | `Chess/runtime/round_state.py` | `ChessRoundStateMixin._refresh_grigri_option#1` | execute_single_click | `self.device` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | rule/R3 |
| 173 | `Chess/runtime/round_state.py` | `ChessRoundStateMixin.select_grigri#1` | click | `selected_rule` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | rule/R3 |
| 174 | `Chess/script_task.py` | `ScriptTask._close_chess_lobby_abnormal_page#1` | click | `self.I_BACK_RED` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R3 |
| 175 | `Chess/script_task.py` | `ScriptTask._wait_until_in_chess_game#1` | click | `self.C_CANCEL_WAITING` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | rule/R3 |
| 176 | `Chess/script_task.py` | `ScriptTask._wait_until_in_chess_game#2` | appear_then_click | `self.I_CHESS_START` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | rule/R3 |

### CollectiveMissions

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 177 | `CollectiveMissions/script_task.py` | `ScriptTask.select_and_update_cur_mission#1` | appear_then_click | `self.I_CM_SWITCH` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 178 | `CollectiveMissions/script_task.py` | `ScriptTask._donate#1` | ui_click | `self.C_CM_1` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R7 |
| 179 | `CollectiveMissions/script_task.py` | `ScriptTask._donate#2` | click | `random.choice(random_click)` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R6 |
| 180 | `CollectiveMissions/script_task.py` | `ScriptTask._soul#1` | ui_click | `self.C_CM_1` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R7 |
| 181 | `CollectiveMissions/script_task.py` | `ScriptTask._soul#2` | ui_click | `self.I_UI_BACK_RED` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R7 |
| 182 | `CollectiveMissions/script_task.py` | `ScriptTask._soul#3` | click | `self.L_SL_LONG` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R6 |
| 183 | `CollectiveMissions/script_task.py` | `ScriptTask._feed#1` | ui_click | `self.C_CM_1` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 184 | `CollectiveMissions/script_task.py` | `ScriptTask._feed#2` | click | `click` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 185 | `CollectiveMissions/script_task.py` | `ScriptTask.get_reward_and_close#1` | ui_reward_appear_click | `False` | IMMEDIATE | Y | Timer | KEEP_SPECIAL | rule/R4 |
| 186 | `CollectiveMissions/script_task.py` | `ScriptTask.get_reward_and_close#2` | appear_then_click | `target` | IMMEDIATE | Y | Timer | KEEP_SPECIAL | rule/R4 |
| 187 | `CollectiveMissions/script_task.py` | `ScriptTask.get_reward_and_close#3` | ui_reward_appear_click | `True` | IMMEDIATE | - | Timer | KEEP_SPECIAL | rule/R4 |

### tasks/Component/Buy

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 188 | `Component/Buy/buy.py` | `Buy.buy_one#1` | appear_then_click | `start_click` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 189 | `Component/Buy/buy.py` | `Buy.buy_one#2` | ocr_appear_click | `start_click` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 190 | `Component/Buy/buy.py` | `Buy.buy_one#3` | click | `start_click` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 191 | `Component/Buy/buy.py` | `Buy.buy_one#4` | click | `self.C_BUY_CANCEL` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 192 | `Component/Buy/buy.py` | `Buy.buy_one#5` | ui_click_until_smt_disappear | `random_click()` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 193 | `Component/Buy/buy.py` | `Buy.buy_one#6` | ui_reward_appear_click | `?` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 194 | `Component/Buy/buy.py` | `Buy.buy_one#7` | ui_reward_appear_click | `?` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 195 | `Component/Buy/buy.py` | `Buy.buy_one#8` | click | `self.C_BUY_ONE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 196 | `Component/Buy/buy.py` | `Buy.buy_more#1` | appear_then_click | `start_click` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 197 | `Component/Buy/buy.py` | `Buy.buy_more#2` | ocr_appear_click | `start_click` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R7 |
| 198 | `Component/Buy/buy.py` | `Buy.buy_more#3` | click | `start_click` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R6 |
| 199 | `Component/Buy/buy.py` | `Buy.buy_more#4` | appear_then_click | `self.I_BUY_PLUS` | IMMEDIATE | - | Timer,sleep | KEEP_SPECIAL | c0/C0S |
| 200 | `Component/Buy/buy.py` | `Buy.buy_more#5` | appear_then_click | `self.I_BUY_PLUS` | IMMEDIATE | - | Timer,sleep | KEEP_SPECIAL | c0/C0S |
| 201 | `Component/Buy/buy.py` | `Buy.buy_more#6` | appear_then_click | `self.I_BUY_ADD` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 202 | `Component/Buy/buy.py` | `Buy.buy_more#7` | ui_reward_appear_click | `?` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R7 |
| 203 | `Component/Buy/buy.py` | `Buy.buy_more#8` | ui_reward_appear_click | `?` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R7 |
| 204 | `Component/Buy/buy.py` | `Buy.buy_more#9` | ui_click_until_disappear | `self.I_UI_CONFIRM_SAMLL` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R7 |
| 205 | `Component/Buy/buy.py` | `Buy.buy_more#10` | click | `self.C_BUY_MORE` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R6 |

### tasks/Component/Costume

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 206 | `Component/Costume/costume_test.py` | `ScriptTask.run#1` | ui_click | `self.I_MAIN_GOTO_TOWN` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 207 | `Component/Costume/costume_test.py` | `ScriptTask.run#2` | ui_click | `self.I_TOWN_GOTO_MAIN` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 208 | `Component/Costume/costume_test.py` | `ScriptTask.run#3` | ui_click | `self.I_MAIN_GOTO_EXPLORATION` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 209 | `Component/Costume/costume_test.py` | `ScriptTask.run#4` | ui_click | `self.I_UI_BACK_BLUE` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 210 | `Component/Costume/costume_test.py` | `ScriptTask.run#5` | ui_click | `self.I_MAIN_GOTO_SUMMON` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 211 | `Component/Costume/costume_test.py` | `ScriptTask.run#6` | ui_click | `self.I_UI_BACK_YELLOW` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 212 | `Component/Costume/costume_test.py` | `ScriptTask.run#7` | ui_click | `self.I_PET_HOUSE` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |

### tasks/Component/CostumeBattle

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 213 | `Component/CostumeBattle/costume_test_battle.py` | `ScriptTask.attack#1` | appear_then_click | `RealmRaidAssets.I_FIRE` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 214 | `Component/CostumeBattle/costume_test_battle.py` | `ScriptTask.attack#2` | click | `rcl` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R6 |

### tasks/Component/GeneralBattle

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 215 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle._sample_settlement_click#1` | execute_single_click | `self.device` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R3 |
| 216 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle._click_settlement_point#1` | execute_single_click | `self.device` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R3 |
| 217 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle._inspection_recover_auto_mode#1` | ui_click | `hand_marker` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 218 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle._handle_prepare#1` | appear_then_click | `self.I_DISABLE_7DAYS_DIFF_SOUL` | IMMEDIATE | - | - | NEEDS_C | human/H |
| 219 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle._handle_prepare#2` | appear_then_click | `self.I_CONFIRM_CLOSE_DIFF_SOUL` | IMMEDIATE | - | - | NEEDS_C | human/H |
| 220 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle._handle_prepare#3` | appear_then_click | `self.I_PREPARE_HIGHLIGHT` | IMMEDIATE | - | - | KEEP_SPECIAL | human/H |
| 221 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle._handle_reward#1` | appear_then_click | `self.I_OVER_GHOST` | IMMEDIATE | - | - | KEEP_SPECIAL | human/H |
| 222 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle._handle_reward#2` | appear_then_click | `self.I_GB_SKIN_CONFIRM` | IMMEDIATE | - | - | KEEP_SPECIAL | human/H |
| 223 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle.exit_battle#1` | appear_then_click | `self.I_EXIT_ENSURE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | human/H |
| 224 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle.exit_battle#2` | appear_then_click | `self.I_EXIT` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | human/H |
| 225 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle.exit_battle#3` | ui_click_until_disappear | `self.I_EXIT_ENSURE` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 226 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle.green_mark_choose#1` | appear_then_click | `self.I_LOCAL` | IMMEDIATE | - | sleep | KEEP_SPECIAL | human/H |
| 227 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle.green_mark_choose#2` | execute_single_click | `self.device` | IMMEDIATE | - | sleep | KEEP_SPECIAL | rule/R3 |
| 228 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle.green_mark_name#1` | execute_single_click | `self.device` | IMMEDIATE | Y | Timer | KEEP_SPECIAL | rule/R3 |
| 229 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle.switch_preset_team#1` | appear_then_click | `self.I_PRESET` | NORMAL | Y | Timer,sleep | MIGRATE | human/H |
| 230 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle.switch_preset_team#2` | appear_then_click | `self.I_PRESET_WIT_NUMBER` | NORMAL | Y | Timer,sleep | MIGRATE | human/H |
| 231 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle.switch_preset_team#3` | appear_then_click | `self.O_PRESET` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | human/H |
| 232 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle.switch_preset_team#4` | appear_then_click | `self.O_PRESET_FULL` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | human/H |
| 233 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle.switch_preset_team#5` | click | `tmp` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | human/H |
| 234 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle.switch_preset_team#6` | click | `tmp` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | human/H |
| 235 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle.switch_preset_team#7` | click | `tmp` | IMMEDIATE | - | Timer,sleep | KEEP_IMMEDIATE | human/H |
| 236 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle.switch_preset_team#8` | appear_then_click | `self.I_PRESET_ENSURE` | CONFIRM | Y | Timer,sleep | MIGRATE | human/H |
| 237 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle.random_click_swipt#1` | click | `self.C_RANDOM_CLICK` | IMMEDIATE | - | sleep | KEEP_SPECIAL | human/H |
| 238 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle.check_lock#1` | appear_then_click | `unlock_image` | policy | Y | - | ALREADY_L2 | human/H |
| 239 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle.check_lock#2` | appear_then_click | `lock_image` | policy | Y | - | ALREADY_L2 | human/H |
| 240 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle.check_and_open_buff#1` | ui_click_until_appear_or_timeout | `self.I_BUFF` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | human/H |
| 241 | `Component/GeneralBattle/general_battle.py` | `GeneralBattle.check_and_open_buff#2` | appear_then_click | `self.I_BUFF` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | human/H |

### tasks/Component/GeneralBuff

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 242 | `Component/GeneralBuff/general_buff.py` | `GeneralBuff.open_buff#1` | appear_then_click | `self.I_BUFF_1` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 243 | `Component/GeneralBuff/general_buff.py` | `GeneralBuff.close_buff#1` | appear_then_click | `self.I_BUFF_1` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R4 |
| 244 | `Component/GeneralBuff/general_buff.py` | `GeneralBuff.gold_50#1` | ui_click | `self.I_CLOSE_RED` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 245 | `Component/GeneralBuff/general_buff.py` | `GeneralBuff.gold_50#2` | ui_click | `self.I_OPEN_YELLOW` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 246 | `Component/GeneralBuff/general_buff.py` | `GeneralBuff.gold_100#1` | ui_click | `self.I_CLOSE_RED` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 247 | `Component/GeneralBuff/general_buff.py` | `GeneralBuff.gold_100#2` | ui_click | `self.I_OPEN_YELLOW` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 248 | `Component/GeneralBuff/general_buff.py` | `GeneralBuff.exp_50#1` | ui_click | `self.I_CLOSE_RED` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R7 |
| 249 | `Component/GeneralBuff/general_buff.py` | `GeneralBuff.exp_50#2` | ui_click | `self.I_OPEN_YELLOW` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R7 |
| 250 | `Component/GeneralBuff/general_buff.py` | `GeneralBuff.exp_100#1` | ui_click | `self.I_CLOSE_RED` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R7 |
| 251 | `Component/GeneralBuff/general_buff.py` | `GeneralBuff.exp_100#2` | ui_click | `self.I_OPEN_YELLOW` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R7 |
| 252 | `Component/GeneralBuff/general_buff.py` | `GeneralBuff.awake#1` | ui_click | `self.I_CLOSE_RED` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 253 | `Component/GeneralBuff/general_buff.py` | `GeneralBuff.awake#2` | ui_click | `self.I_OPEN_YELLOW` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 254 | `Component/GeneralBuff/general_buff.py` | `GeneralBuff.soul#1` | ui_click | `self.I_CLOSE_RED` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 255 | `Component/GeneralBuff/general_buff.py` | `GeneralBuff.soul#2` | ui_click | `self.I_OPEN_YELLOW` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 256 | `Component/GeneralBuff/general_buff.py` | `GeneralBuff.reject_invite#1` | click | `gia.I_I_REJECT_3` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 257 | `Component/GeneralBuff/general_buff.py` | `GeneralBuff.reject_invite#2` | click | `gia.I_I_REJECT_2` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 258 | `Component/GeneralBuff/general_buff.py` | `GeneralBuff.reject_invite#3` | click | `gia.I_I_REJECT_1` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |

### tasks/Component/GeneralInvite

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 259 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite.run_invite#1` | appear_then_click | `self.I_GI_EMOJI_1` | IMMEDIATE | Y | Timer | KEEP_SPECIAL | human/H |
| 260 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite.run_invite#2` | appear_then_click | `self.I_GI_EMOJI_2` | IMMEDIATE | Y | Timer | KEEP_SPECIAL | human/H |
| 261 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite.exit_room#1` | appear_then_click | `GeneralInviteAssets.I_GI_SURE` | IMMEDIATE | Y | Timer,wait_until | KEEP_IMMEDIATE | human/H |
| 262 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite.exit_room#2` | appear_then_click | `GeneralInviteAssets.I_GI_SURE` | IMMEDIATE | Y | Timer,wait_until | KEEP_IMMEDIATE | human/H |
| 263 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite.exit_room#3` | appear_then_click | `self.I_BACK_YELLOW` | IMMEDIATE | Y | Timer,wait_until | KEEP_IMMEDIATE | human/H |
| 264 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite.exit_room#4` | appear_then_click | `self.I_BACK_YELLOW_SEA` | IMMEDIATE | Y | Timer,wait_until | KEEP_IMMEDIATE | human/H |
| 265 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite.click_fire#1` | appear_then_click | `target` | IMMEDIATE | Y | Timer,random_delay,sleep | ALREADY_L2 | human/H |
| 266 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite._detect_select#1` | execute_single_click | `self.device` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R3 |
| 267 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite._open_invite_panel_if_needed#1` | appear_then_click | `self.I_ADD_1` | NORMAL | Y | Timer | MIGRATE | human/H |
| 268 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite._open_invite_panel_if_needed#2` | appear_then_click | `self.I_ADD_2` | NORMAL | Y | Timer | MIGRATE | human/H |
| 269 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite._open_invite_panel_if_needed#3` | appear_then_click | `self.I_ADD_5_4` | NORMAL | Y | Timer | MIGRATE | human/H |
| 270 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite._open_invite_panel_if_needed#4` | appear_then_click | `self.I_ADD_SEA` | NORMAL | Y | Timer | MIGRATE | human/H |
| 271 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite._switch_friend_class#1` | ui_click | `self.I_FLAG_1_OFF` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 272 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite._switch_friend_class#2` | ui_click | `self.I_FLAG_2_OFF` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 273 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite._switch_friend_class#3` | ui_click | `self.I_FLAG_3_OFF` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 274 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite._switch_friend_class#4` | ui_click | `self.I_FLAG_4_OFF` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 275 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite._confirm_invite_and_validate#1` | ui_click_until_disappear | `confirm_rule` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 276 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite.invite_again#1` | appear_then_click | `self.I_I_NO_DEFAULT` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | human/H |
| 277 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite.invite_again#2` | appear_then_click | `self.I_I_DEFAULT` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | human/H |
| 278 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite.invite_again#3` | appear_then_click | `self.I_GI_SURE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | human/H |
| 279 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite.check_and_invite#1` | appear_then_click | `self.I_I_NO_DEFAULT` | IMMEDIATE | Y | - | KEEP_SPECIAL | human/H |
| 280 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite.check_and_invite#2` | appear_then_click | `self.I_GI_SURE` | IMMEDIATE | Y | - | KEEP_SPECIAL | human/H |
| 281 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite.check_then_accept#1` | appear_then_click | `self.I_I_NO_DEFAULT` | IMMEDIATE | Y | - | NEEDS_C | human/H |
| 282 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite.check_then_accept#2` | appear_then_click | `self.I_GI_SURE` | IMMEDIATE | Y | - | NEEDS_C | human/H |
| 283 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite.check_then_accept#3` | appear_then_click | `self.I_I_ACCEPT_DEFAULT` | IMMEDIATE | Y | - | NEEDS_C | human/H |
| 284 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite.check_then_accept#4` | appear_then_click | `self.I_I_ACCEPT` | IMMEDIATE | Y | - | NEEDS_C | human/H |
| 285 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite.check_then_accept#5` | appear_then_click | `self.I_I_ACCEPT_APPRENTICE` | IMMEDIATE | Y | - | NEEDS_C | human/H |
| 286 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite.wait_battle#1` | appear_then_click | `self.I_GI_EMOJI_1` | IMMEDIATE | Y | Timer | KEEP_SPECIAL | human/H |
| 287 | `Component/GeneralInvite/general_invite.py` | `GeneralInvite.wait_battle#2` | appear_then_click | `self.I_GI_EMOJI_2` | IMMEDIATE | Y | Timer | KEEP_SPECIAL | human/H |

### tasks/Component/GeneralRoom

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 288 | `Component/GeneralRoom/general_room.py` | `GeneralRoom.create_room#1` | appear_then_click | `create_room_rule` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 289 | `Component/GeneralRoom/general_room.py` | `GeneralRoom.ensure_private#1` | appear_then_click | `self.I_ENSURE_PRIVATE_FALSE` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 290 | `Component/GeneralRoom/general_room.py` | `GeneralRoom.ensure_private#2` | appear_then_click | `self.I_ENSURE_PRIVATE_FALSE_2` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 291 | `Component/GeneralRoom/general_room.py` | `GeneralRoom.ensure_public#1` | appear_then_click | `self.I_ENSURE_PUBLIC_FALSE` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 292 | `Component/GeneralRoom/general_room.py` | `GeneralRoom.ensure_public#2` | appear_then_click | `self.I_ENSURE_PUBLIC_FALSE_2` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 293 | `Component/GeneralRoom/general_room.py` | `GeneralRoom.create_ensure#1` | appear_then_click | `target` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 294 | `Component/GeneralRoom/general_room.py` | `GeneralRoom.exit_team#1` | appear_then_click | `self.I_GR_BACK_YELLOW` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R4 |
| 295 | `Component/GeneralRoom/general_room.py` | `GeneralRoom.check_zones#1` | execute_single_click | `self.device` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R10 |

### tasks/Component/Login

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 296 | `Component/Login/service.py` | `LoginService._handle_login_method_page#1` | click | `LOGIN_METHOD_PAGE_BACK` | IMMEDIATE | - | - | EXCLUDED | rule/R1 |
| 297 | `Component/Login/service.py` | `LoginService._try_click_enter_game#1` | click | `SwitchAccountAssets.C_SA_LOGIN_FORM_ENTER_GAME_BTN` | IMMEDIATE | - | wait_until | EXCLUDED | rule/R1 |
| 298 | `Component/Login/service.py` | `LoginService._try_click_enter_game#2` | ocr_appear_click | `self.O_LOGIN_ENTER_GAME` | IMMEDIATE | - | wait_until | EXCLUDED | rule/R1 |
| 299 | `Component/Login/service.py` | `LoginService._app_handle_login#1` | appear_then_click | `self.I_RETURN_CHESS_CANCEL` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 300 | `Component/Login/service.py` | `LoginService._app_handle_login#2` | appear_then_click | `self.I_CANCEL_BATTLE` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 301 | `Component/Login/service.py` | `LoginService._app_handle_login#3` | click | `self.C_LOGIN_SCROLL_CLOSE_AREA` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 302 | `Component/Login/service.py` | `LoginService._app_handle_login#4` | click | `self.I_HARVEST_ZIDU` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 303 | `Component/Login/service.py` | `LoginService._app_handle_login#5` | appear_then_click | `self.I_UI_CONFIRM_SAMLL` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 304 | `Component/Login/service.py` | `LoginService._app_handle_login#6` | appear_then_click | `self.I_LOGIN_LOAD_DOWN` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 305 | `Component/Login/service.py` | `LoginService._app_handle_login#7` | appear_then_click | `self.I_WATCH_VIDEO_CANCEL` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 306 | `Component/Login/service.py` | `LoginService._app_handle_login#8` | appear_then_click | `self.I_LOGIN_RED_CLOSE` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 307 | `Component/Login/service.py` | `LoginService._app_handle_login#9` | appear_then_click | `self.I_LOGIN_YELLOW_CLOSE` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 308 | `Component/Login/service.py` | `LoginService._app_handle_login#10` | appear_then_click | `self.I_LOGIN_LOGIN_GOTO_BIND_PHONE` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 309 | `Component/Login/service.py` | `LoginService._app_handle_login#11` | appear_then_click | `self.I_LOGIN_LOGIN_CANCEL_BIND_PHONE` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 310 | `Component/Login/service.py` | `LoginService._app_handle_login#12` | appear_then_click | `gia.I_I_REJECT` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 311 | `Component/Login/service.py` | `LoginService._app_handle_login#13` | appear_then_click | `self.I_LOGIN_LOGIN_ONMYOJI_GENIE` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 312 | `Component/Login/service.py` | `LoginService._app_handle_login#14` | ocr_appear_click | `self.O_LOGIN_SPECIFIC_SERVE` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 313 | `Component/Login/service.py` | `LoginService._app_handle_login#15` | click | `self.C_LOGIN_ENSURE_LOGIN_CHARACTER_IN_SAME_SVR` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 314 | `Component/Login/service.py` | `LoginService._app_handle_login#16` | execute_single_click | `self.device` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 315 | `Component/Login/service.py` | `LoginService._app_handle_login#17` | appear_then_click | `self.I_EARLY_SERVER_CANCEL` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |

### tasks/Component/QuickLoadout

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 316 | `Component/QuickLoadout/quick_loadout.py` | `QuickLoadout._open_quick_loadout#1` | appear_then_click | `entry` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 317 | `Component/QuickLoadout/quick_loadout.py` | `QuickLoadout._dismiss_quick_loadout#1` | click | `dismiss` | IMMEDIATE | Y | Timer | KEEP_SPECIAL | rule/R4 |
| 318 | `Component/QuickLoadout/quick_loadout.py` | `QuickLoadout._select_group#1` | execute_single_click | `self.device` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R10 |
| 319 | `Component/QuickLoadout/quick_loadout.py` | `QuickLoadout._select_group#2` | execute_single_click | `self.device` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R10 |
| 320 | `Component/QuickLoadout/quick_loadout.py` | `QuickLoadout._equip_quick_loadout_souls#1` | execute_single_click | `self.device` | IMMEDIATE | - | Timer,sleep | KEEP_IMMEDIATE | rule/R10 |
| 321 | `Component/QuickLoadout/quick_loadout.py` | `QuickLoadout._equip_quick_loadout_souls#2` | ui_click_until_disappear | `self.I_SOU_SWITCH_SURE` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R7 |
| 322 | `Component/QuickLoadout/quick_loadout.py` | `QuickLoadout._deploy_quick_loadout#1` | execute_single_click | `self.device` | IMMEDIATE | - | Timer,sleep | KEEP_IMMEDIATE | rule/R10 |
| 323 | `Component/QuickLoadout/quick_loadout.py` | `QuickLoadout._deploy_quick_loadout#2` | click | `fight_anchor` | IMMEDIATE | - | Timer,sleep | KEEP_IMMEDIATE | rule/R6 |

### tasks/Component/ReplaceShikigami

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 324 | `Component/ReplaceShikigami/replace_shikigami.py` | `ReplaceShikigami.switch_shikigami_class#1` | click | `check_click` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 325 | `Component/ReplaceShikigami/replace_shikigami.py` | `ReplaceShikigami.switch_shikigami_class#2` | appear_then_click | `self.I_RS_ALL_SELECTED` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 326 | `Component/ReplaceShikigami/replace_shikigami.py` | `ReplaceShikigami.unset_shikigami_max_lv#1` | appear_then_click | `self.I_RS_LEVEL_MAX` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 327 | `Component/ReplaceShikigami/replace_shikigami.py` | `ReplaceShikigami.set_shikigami#1` | appear_then_click | `self.I_U_CONFIRM_SMALL` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 328 | `Component/ReplaceShikigami/replace_shikigami.py` | `ReplaceShikigami.set_shikigami#2` | click | `click_match` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R6 |
| 329 | `Component/ReplaceShikigami/replace_shikigami.py` | `ReplaceShikigami.set_shikigami#3` | click | `_click_match[6]` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R6 |
| 330 | `Component/ReplaceShikigami/replace_shikigami.py` | `ReplaceShikigami.set_shikigami#4` | appear_then_click | `self.I_U_CIRCLE_ALTERNATE` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 331 | `Component/ReplaceShikigami/replace_shikigami.py` | `ReplaceShikigami.set_shikigami#5` | appear_then_click | `self.I_U_CONFIRM_ALTERNATE` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |

### tasks/Component/RightActivity

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 332 | `Component/RightActivity/right_activity.py` | `RightActivity.enter#1` | ui_click | `self.I_TOGGLE_BUTTON` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 333 | `Component/RightActivity/right_activity.py` | `RightActivity.enter#2` | ui_click_until_disappear | `target` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 334 | `Component/RightActivity/right_activity.py` | `RightActivity.right_open#1` | ui_click | `self.I_RA_CLOSE` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 335 | `Component/RightActivity/right_activity.py` | `RightActivity.right_close#1` | ui_click | `self.I_RA_OPEN` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |

### tasks/Component/Summon

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 336 | `Component/Summon/summon.py` | `Summon.summon_one#1` | appear_then_click | `self.I_BLUE_TICKET` | IMMEDIATE | Y | sleep,wait_until | KEEP_IMMEDIATE | rule/R8 |
| 337 | `Component/Summon/summon.py` | `Summon.summon_one#2` | ui_click_until_disappear | `self.I_SM_CONFIRM` | IMMEDIATE | Y | sleep,wait_until | KEEP_IMMEDIATE | rule/R7 |
| 338 | `Component/Summon/summon.py` | `Summon.summon_one#3` | ui_click_until_disappear | `self.I_SM_CONFIRM_2` | IMMEDIATE | Y | sleep,wait_until | KEEP_IMMEDIATE | rule/R7 |
| 339 | `Component/Summon/summon.py` | `Summon.summon_one#4` | appear_then_click | `self.I_UI_CANCEL` | IMMEDIATE | Y | sleep,wait_until | KEEP_IMMEDIATE | rule/R8 |
| 340 | `Component/Summon/summon.py` | `Summon.back_summon_main#1` | appear_then_click | `self.I_UI_BACK_BLUE` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R4 |
| 341 | `Component/Summon/summon.py` | `Summon.back_summon_main#2` | appear_then_click | `self.I_UI_BACK_YELLOW` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R4 |

### tasks/Component/SwitchAccount

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 342 | `Component/SwitchAccount/exit_game.py` | `ExitGame.exitGame#1` | click | `self.C_SA_EG_PROFILE_PHOTO` | IMMEDIATE | - | wait_until | EXCLUDED | rule/R1 |
| 343 | `Component/SwitchAccount/exit_game.py` | `ExitGame.exitGame#2` | appear_then_click | `self.I_SA_USER_CENTER` | IMMEDIATE | - | wait_until | EXCLUDED | rule/R1 |
| 344 | `Component/SwitchAccount/exit_game.py` | `ExitGame.exitGame#3` | ui_click_until_disappear | `self.I_SA_SWITCH_ACCOUNT_BTN` | IMMEDIATE | - | wait_until | EXCLUDED | rule/R1 |
| 345 | `Component/SwitchAccount/login_account.py` | `LoginAccount.switch_svr#1` | ui_click | `self.C_SA_LOGIN_FORM_SWITCH_SVR_BTN` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 346 | `Component/SwitchAccount/login_account.py` | `LoginAccount.switch_svr#2` | click | `self.O_SA_SELECT_SVR_CHARACTER_LIST` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 347 | `Component/SwitchAccount/login_account.py` | `LoginAccount.switch_svr#3` | click | `self.O_SA_SELECT_SVR_SVR_LIST` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 348 | `Component/SwitchAccount/login_account.py` | `LoginAccount.switch_svr#4` | click | `self.C_SA_LOGIN_FORM_CANCEL_SVR_SELECT` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 349 | `Component/SwitchAccount/login_account.py` | `LoginAccount.switch_character#1` | ui_click | `self.C_SA_LOGIN_FORM_SWITCH_SVR_BTN` | IMMEDIATE | - | sleep,wait_until | EXCLUDED | rule/R1 |
| 350 | `Component/SwitchAccount/login_account.py` | `LoginAccount.switch_character#2` | click | `self.C_SA_SELECT_SVR_CHARACTER_LIST` | IMMEDIATE | Y | sleep,wait_until | EXCLUDED | rule/R1 |
| 351 | `Component/SwitchAccount/login_account.py` | `LoginAccount.switch_character#3` | ui_click_until_disappear | `tmpClick` | IMMEDIATE | Y | sleep,wait_until | EXCLUDED | rule/R1 |
| 352 | `Component/SwitchAccount/login_account.py` | `LoginAccount.switch_character#4` | click | `self.C_SA_LOGIN_FORM_CANCEL_SVR_SELECT` | IMMEDIATE | - | sleep,wait_until | EXCLUDED | rule/R1 |
| 353 | `Component/SwitchAccount/login_account.py` | `LoginAccount.jump2SelectAccount#1` | appear_then_click | `self.I_SA_SWITCH_ACCOUNT_BTN` | IMMEDIATE | Y | - | EXCLUDED | rule/R1 |
| 354 | `Component/SwitchAccount/login_account.py` | `LoginAccount.jump2SelectAccount#2` | click | `self.C_SA_LOGIN_FORM_USER_CENTER` | IMMEDIATE | Y | - | EXCLUDED | rule/R1 |
| 355 | `Component/SwitchAccount/login_account.py` | `LoginAccount.handle_login_method_page#1` | click | `self.C_SA_LOGIN_METHOD_AGREEMENT` | IMMEDIATE | - | - | EXCLUDED | rule/R1 |
| 356 | `Component/SwitchAccount/login_account.py` | `LoginAccount.handle_login_method_page#2` | click | `self.C_SA_LOGIN_METHOD_EMAIL` | IMMEDIATE | - | - | EXCLUDED | rule/R1 |
| 357 | `Component/SwitchAccount/login_account.py` | `LoginAccount.submit_saved_account_login#1` | click | `self.C_SA_ACCOUNT_LOGIN_SAFE` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 358 | `Component/SwitchAccount/login_account.py` | `LoginAccount.select_login_platform_fast#1` | appear_then_click | `platform` | IMMEDIATE | - | - | EXCLUDED | rule/R1 |
| 359 | `Component/SwitchAccount/login_account.py` | `LoginAccount.login_fast#1` | click | `self.C_SA_LOGIN_FORM_CANCEL_SVR_SELECT` | IMMEDIATE | Y | wait_until | EXCLUDED | rule/R1 |
| 360 | `Component/SwitchAccount/login_account.py` | `LoginAccount.login_fast#2` | ui_click_until_disappear | `self.C_SA_LOGIN_FORM_ACCOUNT_CLOSE_BTN` | IMMEDIATE | - | wait_until | EXCLUDED | rule/R1 |
| 361 | `Component/SwitchAccount/login_account.py` | `LoginAccount._selectAccountByOcr#1` | ui_click_until_disappear | `self.I_SA_ACCOUNT_DROP_DOWN_CLOSED` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 362 | `Component/SwitchAccount/login_account.py` | `LoginAccount._selectAccountByOcr#2` | click | `self.O_SA_ACCOUNT_ACCOUNT_LIST` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 363 | `Component/SwitchAccount/login_account.py` | `LoginAccount.login#1` | click | `self.C_SA_LOGIN_FORM_CANCEL_SVR_SELECT` | IMMEDIATE | Y | - | EXCLUDED | rule/R1 |
| 364 | `Component/SwitchAccount/login_account.py` | `LoginAccount.login#2` | ui_click_until_disappear | `btn` | IMMEDIATE | Y | - | EXCLUDED | rule/R1 |
| 365 | `Component/SwitchAccount/login_account.py` | `LoginAccount.login#3` | ui_click_until_disappear | `self.C_SA_LOGIN_FORM_ACCOUNT_CLOSE_BTN` | IMMEDIATE | Y | - | EXCLUDED | rule/R1 |
| 366 | `Component/SwitchAccount/login_account.py` | `LoginAccount.login#4` | ui_click_until_disappear | `self.C_SA_LOGIN_FORM_USER_CENTER_CLOSE_BTN` | IMMEDIATE | Y | - | EXCLUDED | rule/R1 |
| 367 | `Component/SwitchAccount/login_account.py` | `LoginAccount.login#5` | ui_click | `self.I_SA_SWITCH_ACCOUNT_BTN` | IMMEDIATE | Y | - | EXCLUDED | rule/R1 |
| 368 | `Component/SwitchAccount/login_account.py` | `LoginAccount.login#6` | click | `self.C_SA_LOGIN_FORM_USER_CENTER` | IMMEDIATE | Y | - | EXCLUDED | rule/R1 |
| 369 | `Component/SwitchAccount/login_account.py` | `LoginAccount.ui_click_until_disappear#1` | appear_then_click | `click` | IMMEDIATE | Y | - | EXCLUDED | rule/R1 |
| 370 | `Component/SwitchAccount/login_account.py` | `LoginAccount.ui_click_until_disappear#2` | click | `click` | IMMEDIATE | Y | - | EXCLUDED | rule/R1 |
| 371 | `Component/SwitchAccount/login_account.py` | `LoginAccount.ui_click_until_disappear#3` | click | `click` | IMMEDIATE | Y | - | EXCLUDED | rule/R1 |
| 372 | `Component/SwitchAccount/netease_account_ui.py` | `NeteaseAccountUi._click_bounds#1` | raw_device_click | `?` | IMMEDIATE | - | - | EXCLUDED | rule/R1 |

### tasks/Component/SwitchOnmyoji

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 373 | `Component/SwitchOnmyoji/switch_onmyoji.py` | `SwitchOnmyoji.switch_onmyoji#1` | ui_click | `self.I_ONMYOJI_CHECK` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 374 | `Component/SwitchOnmyoji/switch_onmyoji.py` | `SwitchOnmyoji.switch_onmyoji#2` | ui_click | `self.I_HERO_CHECK` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 375 | `Component/SwitchOnmyoji/switch_onmyoji.py` | `SwitchOnmyoji.switch_role#1` | appear_then_click | `self.I_ONMYOJI_SWITCH` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 376 | `Component/SwitchOnmyoji/switch_onmyoji.py` | `SwitchOnmyoji.switch_role#2` | ui_click | `self.I_UI_BACK_BLUE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 377 | `Component/SwitchOnmyoji/switch_onmyoji.py` | `SwitchOnmyoji.switch_role#3` | click | `battle_img` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |

### tasks/Component/SwitchSoul

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 378 | `Component/SwitchSoul/switch_soul.py` | `SwitchSoul.click_preset#1` | appear_then_click | `self.I_SOUL_PRESET` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 379 | `Component/SwitchSoul/switch_soul.py` | `SwitchSoul.switch_soul_one#1` | click | `target_click` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R6 |
| 380 | `Component/SwitchSoul/switch_soul.py` | `SwitchSoul.switch_soul_one#2` | click | `self.I_SOU_SWITCH_SURE` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R6 |
| 381 | `Component/SwitchSoul/switch_soul.py` | `SwitchSoul.switch_soul_one#3` | appear_then_click | `self.I_CHECK_BLOCK` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 382 | `Component/SwitchSoul/switch_soul.py` | `SwitchSoul.switch_soul_one#4` | appear_then_click | `target_team` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 383 | `Component/SwitchSoul/switch_soul.py` | `SwitchSoul.switch_soul_one#5` | ui_click_until_disappear | `self.I_SOU_SWITCH_SURE` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R7 |
| 384 | `Component/SwitchSoul/switch_soul.py` | `SwitchSoul.exit_shikigami_records#1` | appear_then_click | `self.I_RECORD_SOUL_BACK` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R4 |
| 385 | `Component/SwitchSoul/switch_soul.py` | `SwitchSoul.switch_soul_by_name#1` | ocr_appear_click | `self.O_SS_GROUP_NAME` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R7 |
| 386 | `Component/SwitchSoul/switch_soul.py` | `SwitchSoul.switch_soul_by_name#2` | appear_then_click | `self.I_SOU_SWITCH_SURE` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 387 | `Component/SwitchSoul/switch_soul.py` | `SwitchSoul.ocr_appear_click_by_rule#1` | execute_single_click | `self.device` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R10 |

### DailyTrifles

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 388 | `DailyTrifles/cooperation_adapter.py` | `CooperationAdapter._open_wanted_quests#1` | appear_then_click | `self.I_WQ_SEAL` | IMMEDIATE | Y | Timer,sleep | EXCLUDED | rule/R1 |
| 389 | `DailyTrifles/cooperation_adapter.py` | `CooperationAdapter._return_to_main#1` | appear_then_click | `self.owner.I_UI_BACK_RED` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 390 | `DailyTrifles/hunt_adapter.py` | `HuntRotationAdapter._run_mode#1` | appear_then_click | `GeneralBattleAssets.I_PREPARE_HIGHLIGHT` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 391 | `DailyTrifles/hunt_adapter.py` | `HuntRotationAdapter._run_mode#2` | appear_then_click | `HuntAssets.I_NW` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 392 | `DailyTrifles/hunt_adapter.py` | `HuntRotationAdapter._run_mode#3` | appear_then_click | `self.owner.I_UI_CONFIRM` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 393 | `DailyTrifles/hunt_adapter.py` | `HuntRotationAdapter._run_mode#4` | appear_then_click | `challenge` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 394 | `DailyTrifles/hunt_adapter.py` | `HuntRotationAdapter._handle_netherworld_room#1` | appear_then_click | `GeneralInviteAssets.I_FIRE` | IMMEDIATE | - | - | EXCLUDED | rule/R1 |
| 395 | `DailyTrifles/hunt_adapter.py` | `HuntRotationAdapter._handle_netherworld_room#2` | appear_then_click | `GeneralInviteAssets.I_FIRE_SEA` | IMMEDIATE | - | - | EXCLUDED | rule/R1 |
| 396 | `DailyTrifles/hunt_adapter.py` | `HuntRotationAdapter._wait_and_short_battle#1` | appear_then_click | `GeneralBattleAssets.I_PREPARE_HIGHLIGHT` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 397 | `DailyTrifles/hunt_adapter.py` | `HuntRotationAdapter._exit_battle#1` | appear_then_click | `GeneralBattleAssets.I_EXIT_ENSURE` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 398 | `DailyTrifles/hunt_adapter.py` | `HuntRotationAdapter._exit_battle#2` | appear_then_click | `GeneralBattleAssets.I_EXIT` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 399 | `DailyTrifles/script_task.py` | `ScriptTask._wait_guild_medal_reward#1` | ui_reward_appear_click | `?` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 400 | `DailyTrifles/script_task.py` | `ScriptTask.run_guild_medal_donate#1` | appear_then_click | `KekkaiUtilizeAssets.I_GUILD_INFO` | IMMEDIATE | - | sleep,wait_until | EXCLUDED | rule/R1 |
| 401 | `DailyTrifles/script_task.py` | `ScriptTask.run_guild_medal_donate#2` | click | `self.C_DT_GUILD_MEDAL_OPEN` | IMMEDIATE | - | sleep,wait_until | EXCLUDED | rule/R1 |
| 402 | `DailyTrifles/script_task.py` | `ScriptTask.run_guild_medal_donate#3` | click | `self.C_DT_GUILD_MEDAL_OPEN` | IMMEDIATE | - | sleep,wait_until | EXCLUDED | rule/R1 |
| 403 | `DailyTrifles/script_task.py` | `ScriptTask.run_guild_medal_donate#4` | click | `self.C_DT_GUILD_MEDAL_OPEN` | IMMEDIATE | - | sleep,wait_until | EXCLUDED | rule/R1 |
| 404 | `DailyTrifles/script_task.py` | `ScriptTask.run_guild_medal_donate#5` | click | `self.C_DT_GUILD_MEDAL_CONFIRM` | IMMEDIATE | - | sleep,wait_until | EXCLUDED | rule/R1 |
| 405 | `DailyTrifles/script_task.py` | `ScriptTask.summon_recall#1` | appear_then_click | `self.I_UI_BACK_RED` | IMMEDIATE | Y | sleep,wait_until | EXCLUDED | rule/R1 |
| 406 | `DailyTrifles/script_task.py` | `ScriptTask.summon_recall#2` | execute_single_click | `self.device` | IMMEDIATE | Y | sleep,wait_until | EXCLUDED | rule/R1 |
| 407 | `DailyTrifles/script_task.py` | `ScriptTask.summon_recall#3` | appear_then_click | `self.I_RECALL_TICKET` | IMMEDIATE | Y | sleep,wait_until | EXCLUDED | rule/R1 |
| 408 | `DailyTrifles/script_task.py` | `ScriptTask.summon_recall#4` | ui_click_until_disappear | `self.I_RECALL_SM_CONFIRM` | IMMEDIATE | Y | sleep,wait_until | EXCLUDED | rule/R1 |
| 409 | `DailyTrifles/script_task.py` | `ScriptTask.summon_recall#5` | ui_click_until_disappear | `self.I_SM_CONFIRM_2` | IMMEDIATE | Y | sleep,wait_until | EXCLUDED | rule/R1 |
| 410 | `DailyTrifles/script_task.py` | `ScriptTask.summon_recall#6` | appear_then_click | `self.I_UI_CANCEL` | IMMEDIATE | Y | sleep,wait_until | EXCLUDED | rule/R1 |
| 411 | `DailyTrifles/script_task.py` | `ScriptTask.run_guild_donate#1` | ui_click | `self.I_DT_GW_THANKS` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 412 | `DailyTrifles/script_task.py` | `ScriptTask.run_guild_donate#2` | appear_then_click | `self.I_UI_BACK_RED` | IMMEDIATE | - | Timer | EXCLUDED | rule/R1 |
| 413 | `DailyTrifles/script_task.py` | `ScriptTask.guild_donate_get_reward#1` | ui_click | `self.I_DT_GW_DONATE_RECORD` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 414 | `DailyTrifles/script_task.py` | `ScriptTask.guild_donate_get_reward#2` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 415 | `DailyTrifles/script_task.py` | `ScriptTask.guild_donate_get_reward#3` | ui_get_reward | `self.I_DT_GW_DONATE_RECORD_THANKS` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 416 | `DailyTrifles/script_task.py` | `ScriptTask.guild_donate_get_reward#4` | ui_click | `self.I_DT_GW_GIVE` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 417 | `DailyTrifles/script_task.py` | `ScriptTask.guild_donate_get_reward#5` | appear_then_click | `self.I_DT_GW_ONE_COLLECT` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 418 | `DailyTrifles/script_task.py` | `ScriptTask.guild_donate_get_reward#6` | ui_click_until_disappear | `self.I_UI_BACK_RED` | IMMEDIATE | - | Timer | EXCLUDED | rule/R1 |
| 419 | `DailyTrifles/script_task.py` | `ScriptTask.donate#1` | appear_then_click | `self.I_DT_GW_CLEAR_SEARCH` | IMMEDIATE | Y | - | EXCLUDED | rule/R1 |
| 420 | `DailyTrifles/script_task.py` | `ScriptTask.donate#2` | ui_click | `self.C_DT_GW_INPUT_SEARCH` | IMMEDIATE | Y | - | EXCLUDED | rule/R1 |
| 421 | `DailyTrifles/script_task.py` | `ScriptTask.donate#3` | click | `self.C_DT_GW_CLICK_INPUT` | IMMEDIATE | Y | - | EXCLUDED | rule/R1 |
| 422 | `DailyTrifles/script_task.py` | `ScriptTask.donate#4` | ui_click_until_disappear | `self.I_DT_GW_CONFIRM` | IMMEDIATE | Y | - | EXCLUDED | rule/R1 |
| 423 | `DailyTrifles/script_task.py` | `ScriptTask.process_donate#1` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 424 | `DailyTrifles/script_task.py` | `ScriptTask.process_donate#2` | appear_then_click | `donate_btn` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 425 | `DailyTrifles/script_task.py` | `ScriptTask.switch_select#1` | appear_then_click | `select` | IMMEDIATE | Y | - | EXCLUDED | rule/R1 |
| 426 | `DailyTrifles/script_task.py` | `ScriptTask.switch_select#2` | appear_then_click | `other` | IMMEDIATE | Y | - | EXCLUDED | rule/R1 |
| 427 | `DailyTrifles/script_task.py` | `ScriptTask.run_luck_msg#1` | appear_then_click | `self.I_CLICK_BLESS` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 428 | `DailyTrifles/script_task.py` | `ScriptTask.run_luck_msg#2` | appear_then_click | `self.I_ONE_CLICK_BLESS` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 429 | `DailyTrifles/script_task.py` | `ScriptTask.run_luck_msg#3` | ui_reward_appear_click | `?` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 430 | `DailyTrifles/script_task.py` | `ScriptTask.run_store_sign#1` | appear_then_click | `self.I_GIFT_RECOMMEND` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 431 | `DailyTrifles/script_task.py` | `ScriptTask.run_store_sign#2` | ui_get_reward | `self.I_GIFT_SIGN` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 432 | `DailyTrifles/script_task.py` | `ScriptTask.run_buy_sushi#1` | appear_then_click | `WeeklyPurchaseAssets.I_MALL_SUNDRY` | IMMEDIATE | Y | - | EXCLUDED | rule/R1 |
| 433 | `DailyTrifles/script_task.py` | `ScriptTask.run_buy_sushi#2` | ui_click_until_disappear | `self.I_STORE_COST_TYPE_JADE` | IMMEDIATE | Y | - | EXCLUDED | rule/R1 |
| 434 | `DailyTrifles/script_task.py` | `ScriptTask.run_buy_sushi#3` | ui_click | `self.I_SPECIAL_SUSHI` | IMMEDIATE | Y | - | EXCLUDED | rule/R1 |
| 435 | `DailyTrifles/script_task.py` | `ScriptTask.run_courtyard_affairs#1` | appear_then_click | `self.I_ENTER_DAILY` | IMMEDIATE | Y | Timer,wait_until | EXCLUDED | rule/R1 |
| 436 | `DailyTrifles/script_task.py` | `ScriptTask.run_courtyard_affairs.close_reward_and_wait_page#1` | click | `self.I_ONE_COMPLETE` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 437 | `DailyTrifles/script_task.py` | `ScriptTask.run_courtyard_affairs.close_reward_and_wait_page#2` | click | `self.I_ONE_COMPLETE` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 438 | `DailyTrifles/script_task.py` | `ScriptTask.run_courtyard_affairs#2` | appear_then_click | `self.I_ONE_COMPLETE` | IMMEDIATE | Y | Timer,wait_until | EXCLUDED | rule/R1 |
| 439 | `DailyTrifles/script_task.py` | `ScriptTask.run_pickup_email#1` | appear_then_click | `self.I_DT_HARVEST_MAIL_COPY2` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 440 | `DailyTrifles/script_task.py` | `ScriptTask.run_pickup_email#2` | appear_then_click | `self.I_HARVEST_MAIL` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 441 | `DailyTrifles/script_task.py` | `ScriptTask.run_pickup_email#3` | appear_then_click | `self.I_HARVEST_MAIL_COPY` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 442 | `DailyTrifles/script_task.py` | `ScriptTask.run_pickup_email#4` | appear_then_click | `self.I_HARVEST_MAIL_CONFIRM` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 443 | `DailyTrifles/script_task.py` | `ScriptTask.run_pickup_email#5` | appear_then_click | `self.I_HARVEST_MAIL_ALL` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 444 | `DailyTrifles/script_task.py` | `ScriptTask.run_pickup_email#6` | appear_then_click | `self.I_READ_ALL_MAIL` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |

### Delegation

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 445 | `Delegation/script_task.py` | `ScriptTask.delegate_one.ui_click#1` | click | `click` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 446 | `Delegation/script_task.py` | `ScriptTask.delegate_one#1` | ui_click_until_disappear | `self.I_D_BACK` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 447 | `Delegation/script_task.py` | `ScriptTask.delegate_one#2` | appear_then_click | `self.I_D_SKIP` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R8 |
| 448 | `Delegation/script_task.py` | `ScriptTask.delegate_one#3` | appear_then_click | `self.I_D_CONFIRM` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R8 |
| 449 | `Delegation/script_task.py` | `ScriptTask.delegate_one#4` | ocr_appear_click | `self.O_D_NAME` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 450 | `Delegation/script_task.py` | `ScriptTask.delegate_one#5` | click | `self.C_D_5` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R6 |
| 451 | `Delegation/script_task.py` | `ScriptTask.delegate_one#6` | appear_then_click | `self.I_D_START` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R8 |
| 452 | `Delegation/script_task.py` | `ScriptTask.check_reward#1` | appear_then_click | `self.I_REWARDS_GET` | IMMEDIATE | Y | Timer | KEEP_SPECIAL | rule/R4 |
| 453 | `Delegation/script_task.py` | `ScriptTask.check_reward#2` | appear_then_click | `self.I_REWARDS_CHAT` | IMMEDIATE | Y | Timer | KEEP_SPECIAL | rule/R4 |
| 454 | `Delegation/script_task.py` | `ScriptTask.check_reward#3` | appear_then_click | `self.I_CHAT_1` | IMMEDIATE | Y | Timer | KEEP_SPECIAL | rule/R4 |
| 455 | `Delegation/script_task.py` | `ScriptTask.check_reward#4` | appear_then_click | `self.I_CHAT_2` | IMMEDIATE | Y | Timer | KEEP_SPECIAL | rule/R4 |
| 456 | `Delegation/script_task.py` | `ScriptTask.check_reward#5` | appear_then_click | `self.I_REWARDS_DONE` | IMMEDIATE | Y | Timer | KEEP_SPECIAL | rule/R4 |
| 457 | `Delegation/script_task.py` | `ScriptTask.check_reward#6` | appear_then_click | `self.I_REWARDS_FALSE` | IMMEDIATE | Y | Timer | KEEP_SPECIAL | rule/R4 |
| 458 | `Delegation/script_task.py` | `ScriptTask.check_reward#7` | ocr_appear_click | `self.O_D_DONE` | IMMEDIATE | Y | Timer | KEEP_SPECIAL | rule/R4 |

### DemonEncounter

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 459 | `DemonEncounter/script_task.py` | `ScriptTask.execute_boss.find_boss#1` | ui_click_until_smt_disappear | `self.I_DE_FIND` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R7 |
| 460 | `DemonEncounter/script_task.py` | `ScriptTask.execute_boss.find_boss#2` | click | `self.C_DM_BOSS_CLICK` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R6 |
| 461 | `DemonEncounter/script_task.py` | `ScriptTask.execute_boss.find_boss#3` | click | `self.I_DE_BOSS_BEST` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R6 |
| 462 | `DemonEncounter/script_task.py` | `ScriptTask.execute_boss.find_boss#4` | click | `self.I_DE_BOSS` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R6 |
| 463 | `DemonEncounter/script_task.py` | `ScriptTask.execute_boss.enter_boss#1` | ui_click_until_disappear | `self.I_UI_BACK_RED` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 464 | `DemonEncounter/script_task.py` | `ScriptTask.execute_boss.enter_boss#2` | ui_click | `self.I_BOSS_NO_SELECT` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 465 | `DemonEncounter/script_task.py` | `ScriptTask.execute_boss.enter_boss#3` | ui_click | `self.I_BOSS_CONFIRM` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 466 | `DemonEncounter/script_task.py` | `ScriptTask.execute_boss.enter_boss#4` | ui_click_until_disappear | `self.I_UI_BACK_RED` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 467 | `DemonEncounter/script_task.py` | `ScriptTask.execute_boss.enter_boss#5` | appear_then_click | `self.I_BOSS_FIRE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 468 | `DemonEncounter/script_task.py` | `ScriptTask.execute_boss.enter_boss#6` | appear_then_click | `self.I_BEST_BOSS_FIRE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 469 | `DemonEncounter/script_task.py` | `ScriptTask.execute_boss#1` | appear_then_click | `self.I_UI_CONFIRM_SAMLL` | IMMEDIATE | Y | Timer,sleep,wait_until | KEEP_IMMEDIATE | rule/R8 |
| 470 | `DemonEncounter/script_task.py` | `ScriptTask.execute_boss#2` | appear_then_click | `self.I_BOSS_BACK_WHITE` | IMMEDIATE | Y | Timer,sleep,wait_until | KEEP_IMMEDIATE | rule/R8 |
| 471 | `DemonEncounter/script_task.py` | `ScriptTask.execute_lantern#1` | appear_then_click | `self.I_DE_FIND` | IMMEDIATE | Y | Timer,sleep,wait_until | KEEP_IMMEDIATE | rule/R8 |
| 472 | `DemonEncounter/script_task.py` | `ScriptTask.execute_lantern#2` | ui_get_reward | `self.I_DE_RED_DHARMA` | IMMEDIATE | - | Timer,sleep,wait_until | KEEP_IMMEDIATE | rule/R7 |
| 473 | `DemonEncounter/script_task.py` | `ScriptTask._box#1` | click | `target_click` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 474 | `DemonEncounter/script_task.py` | `ScriptTask._box#2` | appear_then_click | `self.I_DE_FIND` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 475 | `DemonEncounter/script_task.py` | `ScriptTask._box#3` | click | `self.I_JADE_50` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 476 | `DemonEncounter/script_task.py` | `ScriptTask._box#4` | click | `self.I_JADE_50` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 477 | `DemonEncounter/script_task.py` | `ScriptTask._mail#1` | click | `target_click` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R6 |
| 478 | `DemonEncounter/script_task.py` | `ScriptTask._mail#2` | ui_reward_appear_click | `?` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R7 |
| 479 | `DemonEncounter/script_task.py` | `ScriptTask._mail#3` | ui_reward_appear_click | `?` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R7 |
| 480 | `DemonEncounter/script_task.py` | `ScriptTask._mail#4` | click | `answer_click` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R6 |
| 481 | `DemonEncounter/script_task.py` | `ScriptTask._battle#1` | appear_then_click | `self.I_DE_SMALL_FIRE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 482 | `DemonEncounter/script_task.py` | `ScriptTask._battle#2` | click | `target_click` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 483 | `DemonEncounter/script_task.py` | `ScriptTask._realm#1` | appear_then_click | `self.I_DE_REALM_FIRE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 484 | `DemonEncounter/script_task.py` | `ScriptTask._realm#2` | click | `target_click` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 485 | `DemonEncounter/script_task.py` | `ScriptTask._boss#1` | ui_click_until_disappear | `self.I_UI_BACK_RED` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 486 | `DemonEncounter/script_task.py` | `ScriptTask._boss#2` | click | `target_click` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |

### DemonRetreat

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 487 | `DemonRetreat/script_task.py` | `ScriptTask.run#1` | appear_then_click | `self.I_DEMON_BACK_CHECK` | IMMEDIATE | - | - | KEEP_IMMEDIATE | c0/C0K |
| 488 | `DemonRetreat/script_task.py` | `ScriptTask.run#2` | appear_then_click | `self.I_PRAY` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 489 | `DemonRetreat/script_task.py` | `ScriptTask.run#3` | appear_then_click | `self.I_HUNT` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 490 | `DemonRetreat/script_task.py` | `ScriptTask.run#4` | appear_then_click | `self.I_REWARD_ALL` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 491 | `DemonRetreat/script_task.py` | `ScriptTask.run#5` | ui_reward_appear_click | `True` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 492 | `DemonRetreat/script_task.py` | `ScriptTask.run#6` | appear_then_click | `self.I_DEMON_BACK_CHECK` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 493 | `DemonRetreat/script_task.py` | `ScriptTask.goto_demon_retreat#1` | appear_then_click | `self.I_SHRINE` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 494 | `DemonRetreat/script_task.py` | `ScriptTask.goto_demon_retreat#2` | appear_then_click | `self.I_HUNT` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 495 | `DemonRetreat/script_task.py` | `ScriptTask.goto_demon_retreat#3` | appear_then_click | `self.I_QUIT_BACK` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 496 | `DemonRetreat/script_task.py` | `ScriptTask.goto_demon_retreat#4` | appear_then_click | `self.I_QUIT_BACK` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 497 | `DemonRetreat/script_task.py` | `ScriptTask.goto_demon_retreat#5` | appear_then_click | `self.I_REWARD_ALL` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 498 | `DemonRetreat/script_task.py` | `ScriptTask.goto_demon_retreat#6` | appear_then_click | `self.I_DEMON_BACK_CHECK` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 499 | `DemonRetreat/script_task.py` | `ScriptTask.demon_retreat#1` | ui_click_until_disappear | `self.I_ENTER_FIRE` | IMMEDIATE | - | sleep,wait_until | KEEP_IMMEDIATE | rule/R7 |
| 500 | `DemonRetreat/script_task.py` | `ScriptTask.run_demon_battle#1` | appear_then_click | `self.I_PREPARE_HIGHLIGHT` | IMMEDIATE | Y | sleep,wait_until | KEEP_IMMEDIATE | rule/R8 |
| 501 | `DemonRetreat/script_task.py` | `ScriptTask.battle_wait#1` | ui_click_until_disappear | `self.I_WIN` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R7 |
| 502 | `DemonRetreat/script_task.py` | `ScriptTask.battle_wait#2` | appear_then_click | `self.I_PREPARE_HIGHLIGHT` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 503 | `DemonRetreat/script_task.py` | `ScriptTask.battle_wait#3` | ui_click_until_disappear | `self.I_FALSE` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R7 |

### Dokan

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 504 | `Dokan/page.py` | `map_enter_dokan#1` | execute_single_click | `task.device` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R10 |
| 505 | `Dokan/page.py` | `priority_enter_dokan#1` | appear_then_click | `target_priority` | NORMAL | - | - | ALREADY_L2 | c0/C1 |
| 506 | `Dokan/script_task.py` | `ScriptTask.exit_battle#1` | ui_click_until_disappear | `self.I_RYOU_DOKAN_QUIT_BATTLE_ENSURE` | IMMEDIATE | Y | wait_until | KEEP_SPECIAL | rule/R4 |
| 507 | `Dokan/script_task.py` | `ScriptTask.exit_battle#2` | click | `self.C_DOKAN_BATTLE_QUIT_AREA` | IMMEDIATE | Y | wait_until | KEEP_SPECIAL | rule/R4 |
| 508 | `Dokan/script_task.py` | `ScriptTask.run#1` | click | `pages.random_click(ltrb=(False, False, True, False))` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R6 |
| 509 | `Dokan/script_task.py` | `ScriptTask.run_on_dokan#1` | appear_then_click | `self.I_RYOU_DOKAN_ABANDONED_TOPPA_ABANDONED` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 510 | `Dokan/script_task.py` | `ScriptTask.run_on_dokan#2` | ui_click_until_disappear | `self.I_RYOU_DOKAN_FAILED_VOTE_BATTLE_AGAIN` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 511 | `Dokan/script_task.py` | `ScriptTask.run_on_dokan#3` | ui_click_until_disappear | `self.I_RYOU_DOKAN_FAILED_VOTE_KEEP_BOUNTY` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 512 | `Dokan/script_task.py` | `ScriptTask.click_until_in_battle#1` | appear_then_click | `self.I_RYOU_DOKAN_START_CHALLENGE` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 513 | `Dokan/script_task.py` | `ScriptTask.find_dokan.find_challengeable#1` | click | `self.C_DOKAN_CANCEL_SELECT_DOKAN` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R6 |
| 514 | `Dokan/script_task.py` | `ScriptTask.find_dokan.find_challengeable#2` | ui_click_until_appear_or_timeout | `self.I_RIGHTPAD_POINT_BOUNTY` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R7 |
| 515 | `Dokan/script_task.py` | `ScriptTask.find_dokan.find_challengeable#3` | execute_single_click | `self.device` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R10 |
| 516 | `Dokan/script_task.py` | `ScriptTask.find_dokan#1` | ui_click | `self.I_CENTER_CHALLENGE` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R7 |
| 517 | `Dokan/script_task.py` | `ScriptTask.find_dokan#2` | ui_click_until_disappear | `self.I_CHALLENGE_ENSURE` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R7 |
| 518 | `Dokan/script_task.py` | `ScriptTask.find_dokan#3` | ui_click | `self.C_DOKAN_REFRESH` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R7 |
| 519 | `Dokan/script_task.py` | `ScriptTask.find_dokan#4` | ui_click_until_disappear | `self.I_REFRESH_ENSURE` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R7 |
| 520 | `Dokan/script_task.py` | `ScriptTask.find_dokan#5` | ui_click | `self.I_CENTER_CHALLENGE` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R7 |
| 521 | `Dokan/script_task.py` | `ScriptTask.find_dokan#6` | ui_click_until_disappear | `self.I_CHALLENGE_ENSURE` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R7 |
| 522 | `Dokan/script_task.py` | `ScriptTask.ensure_dokan_created#1` | click | `self.I_RYOU_DOKAN_CREATE_DOKAN` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R6 |
| 523 | `Dokan/script_task.py` | `ScriptTask.creat_dokan#1` | ui_click_until_disappear | `self.I_RYOU_DOKAN_DOKAN_INFO_CLOSE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 524 | `Dokan/script_task.py` | `ScriptTask.creat_dokan#2` | ui_click_until_appear_or_timeout | `self.I_RYOU_DOKAN_CREATE_DOKAN_ENSURE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 525 | `Dokan/script_task.py` | `ScriptTask.creat_dokan#3` | ui_click_until_appear_or_timeout | `self.I_RYOU_DOKAN_CREATE_DOKAN` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 526 | `Dokan/script_task.py` | `ScriptTask.start_cheering#1` | appear_then_click | `self.I_RYOU_DOKAN_CD` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 527 | `Dokan/script_task.py` | `ScriptTask.start_cheering#2` | list_appear_click | `self.L_GOTO_CHEERING` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R7 |
| 528 | `Dokan/script_task.py` | `ScriptTask.start_cheering#3` | click | `pages.random_click()` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R6 |
| 529 | `Dokan/script_task.py` | `ScriptTask.start_cheering#4` | appear_then_click | `self.I_RYOU_DOKAN_CHEERING` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 530 | `Dokan/script_task.py` | `ScriptTask.abandoned_toppa#1` | ui_click | `self.I_DOKAN_ABANDONED_TOPPA` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 531 | `Dokan/script_task.py` | `ScriptTask.abandoned_toppa#2` | ui_click | `self.I_DOKAN_ABANDONED_TOPPA_ENSURE` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 532 | `Dokan/script_task.py` | `ScriptTask.abandoned_toppa#3` | ui_click_until_smt_disappear | `self.C_DOKAN_TOPPA_RANK_CLOSE_AREA` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 533 | `Dokan/script_task.py` | `ScriptTask.abandoned_toppa#4` | ui_click_until_disappear | `self.I_RYOU_DOKAN_ABANDONED_TOPPA_ABANDONED` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 534 | `Dokan/script_task.py` | `ScriptTask.abandoned_toppa#5` | ui_click_until_disappear | `self.I_RYOU_DOKAN_FAILED_VOTE_KEEP_BOUNTY` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | rule/R7 |

### Duel

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 535 | `Duel/script_task.py` | `ScriptTask.enter_battle#1` | ui_click_until_disappear | `self.I_D_BATTLE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 536 | `Duel/script_task.py` | `ScriptTask.enter_battle#2` | ui_click_until_disappear | `self.I_D_BATTLE2` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 537 | `Duel/script_task.py` | `ScriptTask.enter_battle#3` | ui_click_until_disappear | `self.I_D_BATTLE_PROTECT` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 538 | `Duel/script_task.py` | `ScriptTask.enter_practice_ban_mode#1` | appear_then_click | `self.I_BATTLE_WITH_TRAIN` | IMMEDIATE | - | sleep | DEFERRED | c0/C0D |
| 539 | `Duel/script_task.py` | `ScriptTask.enter_practice_ban_mode#2` | appear_then_click | `self.I_BATTLE_WITH_TRAIN2` | IMMEDIATE | - | sleep | DEFERRED | c0/C0D |
| 540 | `Duel/script_task.py` | `ScriptTask.enter_practice_ban_mode#3` | click | `self.C_SELECT_BAN` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R6 |
| 541 | `Duel/script_task.py` | `ScriptTask.check_duel_position_banned#1` | click | `click_rule` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R6 |
| 542 | `Duel/script_task.py` | `ScriptTask.battle_prepare#1` | appear_then_click | `self.I_BAN` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 543 | `Duel/script_task.py` | `ScriptTask.battle_prepare#2` | appear_then_click | `self.I_D_AUTO_ENTRY` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 544 | `Duel/script_task.py` | `ScriptTask.battle_prepare#3` | appear_then_click | `self.I_D_PREPARE` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 545 | `Duel/script_task.py` | `ScriptTask.wait_battle#1` | click | `random_click(ltrb=(True, True, False, True))` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R6 |
| 546 | `Duel/script_task.py` | `ScriptTask.wait_battle#2` | appear_then_click | `self.I_UI_BACK_RED` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 547 | `Duel/script_task.py` | `ScriptTask.wait_battle#3` | click | `random_click(ltrb=(True, True, False, True))` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R6 |
| 548 | `Duel/script_task.py` | `ScriptTask.wait_battle#4` | click | `random_click(ltrb=(True, True, False, True))` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R6 |
| 549 | `Duel/script_task.py` | `ScriptTask.wait_battle#5` | ui_click | `self.O_BATTLE_HAND` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R7 |
| 550 | `Duel/script_task.py` | `ScriptTask.duel_exit_battle#1` | appear_then_click | `self.I_EXIT_ENSURE` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R4 |
| 551 | `Duel/script_task.py` | `ScriptTask.duel_exit_battle#2` | appear_then_click | `self.I_DUEL_EXIT` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R4 |
| 552 | `Duel/script_task.py` | `ScriptTask.duel_exit_battle#3` | appear_then_click | `self.I_EXIT` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R4 |
| 553 | `Duel/script_task.py` | `ScriptTask.dismiss_duel_main_useless_message#1` | click | `random_click(ltrb=(True, True, False, True))` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 554 | `Duel/script_task.py` | `ScriptTask.switch_all_soul#1` | appear_then_click | `self.I_D_TEAM` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 555 | `Duel/script_task.py` | `ScriptTask.switch_all_soul#2` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 556 | `Duel/script_task.py` | `ScriptTask.switch_all_soul#3` | appear_then_click | `self.I_D_TEAM_SWTICH` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 557 | `Duel/script_task.py` | `ScriptTask.switch_all_soul#4` | ui_click | `self.I_UI_BACK_YELLOW` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 558 | `Duel/script_task.py` | `ScriptTask.check_and_get_reward#1` | click | `random_click(ltrb=(True, True, False, True))` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |

### DyeTrials

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 559 | `DyeTrials/script_task.py` | `ScriptTask.get_all#1` | appear_then_click | `self.I_FP_ACCESS` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 560 | `DyeTrials/script_task.py` | `ScriptTask.get_all#2` | appear_then_click | `self.I_FP_ACCESS_1` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 561 | `DyeTrials/script_task.py` | `ScriptTask.get_all#3` | appear_then_click | `self.I_TOGGLE_BUTTON` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 562 | `DyeTrials/script_task.py` | `ScriptTask.get_all#4` | appear_then_click | `self.I_FP_CLOSE_GET_SKIN` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 563 | `DyeTrials/script_task.py` | `ScriptTask.get_all#5` | ui_reward_appear_click | `?` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R7 |
| 564 | `DyeTrials/script_task.py` | `ScriptTask.get_all#6` | appear_then_click | `RestartAssets.I_HARVEST_CHAT_CLOSE` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 565 | `DyeTrials/script_task.py` | `ScriptTask.get_all#7` | ui_click_until_disappear | `self.I_FP_CHALLENGE` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R7 |
| 566 | `DyeTrials/script_task.py` | `ScriptTask.get_all#8` | appear_then_click | `self.I_BATTLE_SUCCESS` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |

### EternitySea

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 567 | `EternitySea/script_task.py` | `ScriptTask.run_leader#1` | appear_then_click | `self.I_FORM_TEAM` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R3 |
| 568 | `EternitySea/script_task.py` | `ScriptTask._fire_eternity_sea_alone#1` | appear_then_click | `self.I_ETERNITY_SEA_FIRE` | IMMEDIATE | Y | Timer,random_delay,sleep | KEEP_SPECIAL | rule/R3 |
| 569 | `EternitySea/script_task.py` | `ScriptTask._enter_eternity_sea#1` | appear_then_click | `self.I_ETERNITY_SEA` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R3 |
| 570 | `EternitySea/script_task.py` | `ScriptTask._enter_eternity_sea#2` | appear_then_click | `self.I_UI_BACK_RED` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R3 |
| 571 | `EternitySea/script_task.py` | `ScriptTask.check_layer#1` | execute_single_click | `self.device` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R3 |

### EvoZone

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 572 | `EvoZone/script_task.py` | `ScriptTask._return_to_main_after_run#1` | ui_click | `self.I_UI_BACK_YELLOW` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 573 | `EvoZone/script_task.py` | `ScriptTask.evozone_enter#1` | appear_then_click | `kirintype` | DELIBERATE | Y | - | ALREADY_L2 | human/H |
| 574 | `EvoZone/script_task.py` | `ScriptTask.check_layer#1` | execute_single_click | `self.device` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R3 |
| 575 | `EvoZone/script_task.py` | `ScriptTask.run_leader#1` | appear_then_click | `self.I_FORM_TEAM` | NORMAL | Y | sleep | ALREADY_L2 | human/H |
| 576 | `EvoZone/script_task.py` | `ScriptTask._fire_evozone_alone#1` | appear_then_click | `self.I_EVOZONE_FIRE` | IMMEDIATE | Y | Timer,random_delay,sleep | ALREADY_L2 | human/H |

### Exploration

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 577 | `Exploration/base.py` | `BaseExploration.open_expect_level#1` | appear_then_click | `self.I_UI_CONFIRM` | NORMAL | Y | sleep,wait_until | ALREADY_L2 | human/H |
| 578 | `Exploration/base.py` | `BaseExploration.open_expect_level#2` | appear_then_click | `self.I_UI_CONFIRM_SAMLL` | NORMAL | Y | sleep,wait_until | ALREADY_L2 | human/H |
| 579 | `Exploration/base.py` | `BaseExploration.open_expect_level#3` | appear_then_click | `self.I_UI_CONFIRM` | NORMAL | Y | sleep,wait_until | ALREADY_L2 | human/H |
| 580 | `Exploration/base.py` | `BaseExploration.open_expect_level#4` | appear_then_click | `self.I_UI_CONFIRM_SAMLL` | NORMAL | Y | sleep,wait_until | ALREADY_L2 | human/H |
| 581 | `Exploration/base.py` | `BaseExploration.open_expect_level#5` | ocr_appear_click | `self.O_E_EXPLORATION_LEVEL_NUMBER` | IMMEDIATE | Y | sleep,wait_until | KEEP_IMMEDIATE | human/H |
| 582 | `Exploration/base.py` | `BaseExploration.fill_shikigami#1` | click | `self.C_CLICK_STANDBY_TEAM` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | human/H |
| 583 | `Exploration/base.py` | `BaseExploration.fill_shikigami#2` | click | `self.L_ROTATE_1` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | human/H |
| 584 | `Exploration/base.py` | `BaseExploration.fire#1` | appear_then_click | `button` | IMMEDIATE | Y | Timer | KEEP_SPECIAL | human/H |
| 585 | `Exploration/base.py` | `BaseExploration.switch_rotate#1` | click | `self.C_CLICK_SETTINGS` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 586 | `Exploration/base.py` | `BaseExploration.collect_treasure_box#1` | ui_click | `self.I_E_REWARD_BOX_SMALL` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 587 | `Exploration/base.py` | `BaseExploration.collect_treasure_box#2` | ui_click_until_disappear | `self.I_REWARD` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 588 | `Exploration/base.py` | `BaseExploration.collect_treasure_box#3` | ui_click | `self.I_E_REWARD_BOX_BIG` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 589 | `Exploration/base.py` | `BaseExploration.collect_treasure_box#4` | ui_click_until_disappear | `self.I_REWARD` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 590 | `Exploration/base.py` | `BaseExploration.collect_paper_man_reward#1` | ui_get_reward | `self.I_BATTLE_REWARD` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 591 | `Exploration/base.py` | `BaseExploration.quit_exp_main#1` | appear_then_click | `self.I_UI_BACK_YELLOW` | NAVIGATION | - | - | ALREADY_L2 | human/H |
| 592 | `Exploration/script_task.py` | `ScriptTask.exp_page_handle_dict#1` | click | `pages.random_click()` | IMMEDIATE | - | - | KEEP_SPECIAL | human/H |
| 593 | `Exploration/script_task.py` | `ScriptTask.exec_exp_page#1` | appear_then_click | `self.I_UI_CANCEL` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | human/H |
| 594 | `Exploration/script_task.py` | `ScriptTask.run_on_exp_settings#1` | appear_then_click | `self.I_E_AUTO_ROTATE_OFF` | FAST | - | - | ALREADY_L2 | human/H |
| 595 | `Exploration/script_task.py` | `ScriptTask.run_on_exp_exit#1` | appear_then_click | `self.I_E_EXIT_CANCEL` | NAVIGATION | - | - | ALREADY_L2 | human/H |
| 596 | `Exploration/script_task.py` | `ScriptTask.run_on_exp_exit#2` | appear_then_click | `self.I_E_EXIT_CONFIRM` | CONFIRM | - | - | ALREADY_L2 | human/H |

### FallenSun

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 597 | `FallenSun/script_task.py` | `ScriptTask.fallen_sun_enter#1` | appear_then_click | `self.I_FALLEN_SUN` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R3 |
| 598 | `FallenSun/script_task.py` | `ScriptTask.check_layer#1` | execute_single_click | `self.device` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R3 |
| 599 | `FallenSun/script_task.py` | `ScriptTask.check_lock#1` | appear_then_click | `self.I_FALLEN_SUN_UNLOCK` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R3 |
| 600 | `FallenSun/script_task.py` | `ScriptTask.check_lock#2` | appear_then_click | `self.I_FALLEN_SUN_LOCK` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R3 |
| 601 | `FallenSun/script_task.py` | `ScriptTask.run_leader#1` | appear_then_click | `self.I_FORM_TEAM` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | rule/R3 |
| 602 | `FallenSun/script_task.py` | `ScriptTask.run_leader#2` | appear_then_click | `self.I_PET_PRESENT` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | rule/R3 |
| 603 | `FallenSun/script_task.py` | `ScriptTask.run_member#1` | appear_then_click | `self.I_PET_PRESENT` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R3 |
| 604 | `FallenSun/script_task.py` | `ScriptTask.run_alone#1` | appear_then_click | `self.I_PET_PRESENT` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R3 |
| 605 | `FallenSun/script_task.py` | `ScriptTask._fire_fallen_sun_alone#1` | appear_then_click | `self.I_FALLEN_SUN_FIRE` | IMMEDIATE | Y | Timer,random_delay,sleep | KEEP_SPECIAL | rule/R3 |

### FloatParade

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 606 | `FloatParade/script_task.py` | `ScriptTask.collect_exp#1` | ui_get_reward | `self.I_FP_GETALL1` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R7 |
| 607 | `FloatParade/script_task.py` | `ScriptTask.get_flower#1` | appear_then_click | `self.I_BATCH_SELECTION` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 608 | `FloatParade/script_task.py` | `ScriptTask.get_flower#2` | appear_then_click | `self.I_BATCH_SELECTION_CONFIRM` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 609 | `FloatParade/script_task.py` | `ScriptTask.get_flower#3` | appear_then_click | `match_level[level1]` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 610 | `FloatParade/script_task.py` | `ScriptTask.get_flower#4` | appear_then_click | `self.I_OVERFLOW_CONFIRME` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 611 | `FloatParade/script_task.py` | `ScriptTask.get_flower#5` | appear_then_click | `match_level[level2]` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 612 | `FloatParade/script_task.py` | `ScriptTask.get_flower#6` | appear_then_click | `self.I_OVERFLOW_CONFIRME` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 613 | `FloatParade/script_task.py` | `ScriptTask.get_flower#7` | ui_reward_appear_click | `False` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R7 |
| 614 | `FloatParade/script_task.py` | `ScriptTask.get_flower#8` | appear_then_click | `self.I_FP_GETALL0` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 615 | `FloatParade/script_task.py` | `ScriptTask.collect_placement_reward#1` | ui_get_reward | `self.I_FP_PR_CAN_GET` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |

### FrogBoss

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 616 | `FrogBoss/script_task.py` | `ScriptTask.run#1` | appear_then_click | `self.I_BET_SUCCESS_BOX` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 617 | `FrogBoss/script_task.py` | `ScriptTask.run#2` | appear_then_click | `self.I_REWARD` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 618 | `FrogBoss/script_task.py` | `ScriptTask.run#3` | appear_then_click | `self.I_NEXT_COMPETITION` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 619 | `FrogBoss/script_task.py` | `ScriptTask.run#4` | ui_click_until_disappear | `self.I_NEXT_COMPETITION` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 620 | `FrogBoss/script_task.py` | `ScriptTask.do_bet#1` | ui_click_until_disappear | `click_image` | IMMEDIATE | - | Timer | KEEP_IMMEDIATE | rule/R7 |
| 621 | `FrogBoss/script_task.py` | `ScriptTask.do_bet#2` | appear_then_click | `self.I_GOLD_30` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 622 | `FrogBoss/script_task.py` | `ScriptTask.do_bet#3` | appear_then_click | `self.I_BET_SURE` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 623 | `FrogBoss/script_task.py` | `ScriptTask.do_bet#4` | appear_then_click | `self.I_GOLD_30` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 624 | `FrogBoss/script_task.py` | `ScriptTask.do_bet#5` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 625 | `FrogBoss/script_task.py` | `ScriptTask.do_bet#6` | appear_then_click | `self.I_UI_CONFIRM_SAMLL` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |

### GameUi

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 626 | `GameUi/chess_battle.py` | `ChessBattleNavigationMixin.return_to_chess_lobby#1` | appear_then_click | `self.I_CHESS_RANK_GOTO_LOBBY` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | human/H |
| 627 | `GameUi/chess_battle.py` | `ChessBattleNavigationMixin.return_to_chess_lobby#2` | click | `GeneralBattleAssets.C_RANDOM_LEFT` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | human/H |
| 628 | `GameUi/chess_battle.py` | `ChessBattleNavigationMixin.return_to_chess_lobby#3` | appear_then_click | `self.I_CHESS_EXIT_TO_LOBBY` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | human/H |
| 629 | `GameUi/chess_battle.py` | `ChessBattleNavigationMixin.return_to_chess_lobby#4` | appear_then_click | `self.I_CHESS_EXIT_TO_LOBBY_2` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | human/H |
| 630 | `GameUi/chess_battle.py` | `ChessBattleNavigationMixin.return_to_chess_lobby#5` | click | `self.I_CHESS_EXIT_TO_LOBBY` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | human/H |
| 631 | `GameUi/chess_battle.py` | `ChessBattleNavigationMixin.return_to_chess_lobby#6` | click | `GeneralBattleAssets.C_RANDOM_LEFT` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | human/H |
| 632 | `GameUi/chess_battle.py` | `ChessBattleNavigationMixin.exit_chess_battle#1` | click | `self.I_CHESS_EXIT_CONFIRM` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | human/H |
| 633 | `GameUi/chess_battle.py` | `ChessBattleNavigationMixin.exit_chess_battle#2` | click | `self.I_CHESS_EXIT` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | human/H |
| 634 | `GameUi/default_pages.py` | `find_activity_entry#1` | appear_then_click | `RightActivityAssets.I_TOGGLE_BUTTON` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | human/H |
| 635 | `GameUi/default_pages.py` | `handle_activity_overlay#1` | click | `click` | IMMEDIATE | Y | Timer,sleep | KEEP_SPECIAL | rule/R4 |
| 636 | `GameUi/default_pages.py` | `handle_activity_overlay#2` | appear_then_click | `GameUiAssets.I_ACTIVITY_SIGNIN_CLOSE` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | human/H |
| 637 | `GameUi/default_pages.py` | `<module>#1` | ui_click | `?` | IMMEDIATE | - | - | KEEP_SPECIAL | human/H |
| 638 | `GameUi/default_pages.py` | `exploration_to_six_gates#1` | appear_then_click | `GameUiAssets.I_EXPLORATION_TO_MOON_SEA` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 639 | `GameUi/default_pages.py` | `exploration_to_six_gates#2` | appear_then_click | `GameUiAssets.I_EXPLORATION_TO_INCENSE_REALM` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 640 | `GameUi/default_pages.py` | `exploration_to_six_gates#3` | appear_then_click | `GameUiAssets.I_EXPLORATION_TO_SEASONRIFT_FOREST` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 641 | `GameUi/default_pages.py` | `exploration_to_six_gates#4` | appear_then_click | `GameUiAssets.I_EXPLORATION_TO_PURE_BUDDHA_REALM` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 642 | `GameUi/default_pages.py` | `exploration_to_six_gates#5` | appear_then_click | `GameUiAssets.I_EXPLORATION_TO_MANTRA_TOWER` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 643 | `GameUi/default_pages.py` | `exploration_to_six_gates#6` | appear_then_click | `GameUiAssets.I_EXPLORATION_TO_PEACOCK_KINGDOM` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 644 | `GameUi/default_pages.py` | `handle_battle_reward_page#1` | appear_then_click | `GeneralBattleAssets.I_OVER_GHOST` | IMMEDIATE | - | - | KEEP_SPECIAL | human/H |
| 645 | `GameUi/default_pages.py` | `handle_battle_reward_page#2` | click | `random_click()` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 646 | `GameUi/navigator.py` | `GameUi._execute_action#1` | list_appear_click | `action` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 647 | `GameUi/navigator.py` | `GameUi._execute_action#2` | appear_then_click | `action` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 648 | `GameUi/navigator.py` | `GameUi._execute_action#3` | ocr_appear_click | `action` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 649 | `GameUi/navigator.py` | `GameUi._execute_action#4` | click | `action` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 650 | `GameUi/navigator.py` | `GameUi._execute_action#5` | execute_single_click | `self.device` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R10 |
| 651 | `GameUi/navigator.py` | `GameUi._execute_transition#1` | execute_single_click | `self.device` | IMMEDIATE | - | Timer | KEEP_IMMEDIATE | rule/R10 |

### GoryouRealm

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 652 | `GoryouRealm/script_task.py` | `ScriptTask.run#1` | click | `match_click[goryou_class]` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R6 |
| 653 | `GoryouRealm/script_task.py` | `ScriptTask.run#2` | click | `self.C_GR_LEVEL_3` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R6 |
| 654 | `GoryouRealm/script_task.py` | `ScriptTask.enter_battle#1` | appear_then_click | `self.I_GR_FIRE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |

### GuguArtStudio

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 655 | `GuguArtStudio/script_task.py` | `ScriptTask.run#1` | appear_then_click | `self.I_SUBMIT_PAINT` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 656 | `GuguArtStudio/script_task.py` | `ScriptTask.run#2` | appear_then_click | `self.I_GOTO_SUBMIT` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 657 | `GuguArtStudio/script_task.py` | `ScriptTask.run#3` | appear_then_click | `self.I_GAS_CAN_FIRE` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 658 | `GuguArtStudio/script_task.py` | `ScriptTask.switch_lock#1` | ui_click | `self.I_GAS_UNLOCK` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 659 | `GuguArtStudio/script_task.py` | `ScriptTask.switch_lock#2` | ui_click | `self.I_GAS_LOCK` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 660 | `GuguArtStudio/script_task.py` | `ScriptTask.get_reward#1` | ui_get_reward | `click` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R4 |

### GuildBanquet

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 661 | `GuildBanquet/script_task.py` | `ScriptTask.switch_shikigami#1` | appear_then_click | `self.I_BANQUET_CLEAR_ALL` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 662 | `GuildBanquet/script_task.py` | `ScriptTask.switch_shikigami#2` | appear_then_click | `self.I_BANQUET_ALL_PUT` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 663 | `GuildBanquet/script_task.py` | `ScriptTask.switch_shikigami#3` | appear_then_click | `self.I_BANQUET_CONFIRM` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |

### HeroTest

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 664 | `HeroTest/script_task.py` | `ScriptTask.enter_battle#1` | appear_then_click | `self.I_START_CHALLENGE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 665 | `HeroTest/script_task.py` | `ScriptTask.enter_battle#2` | appear_then_click | `self.I_BCMJ_RESET_CONFIRM` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 666 | `HeroTest/script_task.py` | `ScriptTask.enter_battle#3` | appear_then_click | `self.O_FIRE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 667 | `HeroTest/script_task.py` | `ScriptTask.hero1_skill_wait#1` | appear_then_click | `self.I_BCMJ_SKILL_ADD1` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 668 | `HeroTest/script_task.py` | `ScriptTask.hero1_skill_wait#2` | appear_then_click | `self.I_BCMJ_SKILL_ADD2` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 669 | `HeroTest/script_task.py` | `ScriptTask.hero1_skill_wait#3` | appear_then_click | `self.I_BCMJ_BLESS` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 670 | `HeroTest/script_task.py` | `ScriptTask.hero1_skill_wait#4` | appear_then_click | `self.I_BCMJ_PROPERTY_ADD_CRITICAL` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 671 | `HeroTest/script_task.py` | `ScriptTask.hero1_skill_wait#5` | appear_then_click | `self.I_BCMJ__DEFALUT_ATTRIBUTE` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 672 | `HeroTest/script_task.py` | `ScriptTask.hero1_skill_wait#6` | appear_then_click | `self.I_BCMJ_SKILL_ADD_CONFIRM` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 673 | `HeroTest/script_task.py` | `ScriptTask.hero2_skill_wait#1` | appear_then_click | `ts` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 674 | `HeroTest/script_task.py` | `ScriptTask.hero2_skill_wait#2` | appear_then_click | `self.I_BCMJ_SKILL_ADD_CONFIRM` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 675 | `HeroTest/script_task.py` | `ScriptTask.switch_hero#1` | appear_then_click | `switch_hero_img` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 676 | `HeroTest/script_task.py` | `ScriptTask.switch_hero#2` | click | `self.C_SWITCH_HERO_BTN` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 677 | `HeroTest/script_task.py` | `ScriptTask.check_and_lock_team#1` | ui_click | `unlock_img` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 678 | `HeroTest/script_task.py` | `ScriptTask.check_and_lock_team#2` | ui_click | `lock_img` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |

### Hunt

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 679 | `Hunt/script_task.py` | `ScriptTask.kirin#1` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 680 | `Hunt/script_task.py` | `ScriptTask.kirin#2` | appear_then_click | `self.I_KIRIN_CHALLAGE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 681 | `Hunt/script_task.py` | `ScriptTask.kirin#3` | ui_click_until_disappear | `self.I_UI_BACK_YELLOW` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 682 | `Hunt/script_task.py` | `ScriptTask.netherworld#1` | appear_then_click | `self.I_NW` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 683 | `Hunt/script_task.py` | `ScriptTask.netherworld#2` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 684 | `Hunt/script_task.py` | `ScriptTask.netherworld#3` | appear_then_click | `self.I_NW_CHALLAGE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 685 | `Hunt/script_task.py` | `ScriptTask.netherworld#4` | ui_click_until_disappear | `self.I_UI_BACK_RED` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |

### Hyakkiyakou

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 686 | `Hyakkiyakou/script_task.py` | `ScriptTask.run#1` | ui_click_until_disappear | `self.I_HCLOSE_RED` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R3 |
| 687 | `Hyakkiyakou/script_task.py` | `ScriptTask._select_best_boss#1` | click | `btn` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | rule/R3 |
| 688 | `Hyakkiyakou/script_task.py` | `ScriptTask._select_best_boss#2` | click | `self._best_boss_button` | IMMEDIATE | - | sleep | KEEP_SPECIAL | rule/R3 |
| 689 | `Hyakkiyakou/script_task.py` | `ScriptTask.one#1` | ui_click | `self.I_HACCESS` | IMMEDIATE | - | sleep,wait_until | KEEP_SPECIAL | rule/R3 |
| 690 | `Hyakkiyakou/script_task.py` | `ScriptTask.one#2` | appear_then_click | `self.I_HSTART` | IMMEDIATE | Y | sleep,wait_until | KEEP_SPECIAL | rule/R3 |
| 691 | `Hyakkiyakou/script_task.py` | `ScriptTask.one#3` | click | `self._best_boss_button` | IMMEDIATE | Y | sleep,wait_until | KEEP_SPECIAL | rule/R3 |
| 692 | `Hyakkiyakou/script_task.py` | `ScriptTask.one#4` | ui_click | `self.I_HEND` | IMMEDIATE | - | sleep,wait_until | KEEP_SPECIAL | rule/R3 |
| 693 | `Hyakkiyakou/slave/hya_device.py` | `HyaDevice.fast_click#1` | execute_single_click | `self.device` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R3 |
| 694 | `Hyakkiyakou/slave/hya_device.py` | `HyaDevice.fast_click#2` | execute_single_click | `self.device` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R3 |
| 695 | `Hyakkiyakou/slave/hya_device.py` | `HyaDevice.fast_click#3` | execute_single_click | `self.device` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R3 |
| 696 | `Hyakkiyakou/slave/hya_slave.py` | `HyaSlave.invite_friend#1` | ui_click | `self.I_HINVITE` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R3 |
| 697 | `Hyakkiyakou/slave/hya_slave.py` | `HyaSlave._invite_friend#1` | ui_click | `button1` | IMMEDIATE | - | Timer | KEEP_SPECIAL | rule/R3 |
| 698 | `Hyakkiyakou/slave/hya_slave.py` | `HyaSlave._invite_friend#2` | click | `self.C_FRIEND_1_RECALL` | IMMEDIATE | Y | Timer | KEEP_SPECIAL | rule/R3 |
| 699 | `Hyakkiyakou/slave/hya_slave.py` | `HyaSlave._invite_friend#3` | click | `self.C_FRIEND_2_RECALL` | IMMEDIATE | Y | Timer | KEEP_SPECIAL | rule/R3 |
| 700 | `Hyakkiyakou/slave/hya_slave.py` | `HyaSlave._invite_friend#4` | click | `self.C_FRIEND_1` | IMMEDIATE | Y | Timer | KEEP_SPECIAL | rule/R3 |
| 701 | `Hyakkiyakou/slave/hya_slave.py` | `HyaSlave._invite_friend#5` | click | `self.C_FRIEND_2` | IMMEDIATE | Y | Timer | KEEP_SPECIAL | rule/R3 |

### KekkaiActivation

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 702 | `KekkaiActivation/script_task.py` | `ScriptTask.run_activation#1` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 703 | `KekkaiActivation/script_task.py` | `ScriptTask.run_activation#2` | appear_then_click | `self.I_A_ACTIVATE_YELLOW` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 704 | `KekkaiActivation/script_task.py` | `ScriptTask.screening_card#1` | click | `self.C_A_SELECT_CARD_LIST` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R6 |
| 705 | `KekkaiActivation/script_task.py` | `ScriptTask.screening_card#2` | appear_then_click | `target_class` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 706 | `KekkaiActivation/script_task.py` | `ScriptTask.screening_card#3` | click | `target` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R6 |
| 707 | `KekkaiActivation/script_task.py` | `ScriptTask.harvest_card#1` | appear_then_click | `self.I_A_HARVEST_EXP` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 708 | `KekkaiActivation/script_task.py` | `ScriptTask.harvest_card#2` | appear_then_click | `self.I_A_HARVEST_FISH4` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 709 | `KekkaiActivation/script_task.py` | `ScriptTask.harvest_card#3` | appear_then_click | `self.I_A_HARVEST_KAIKO_4` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 710 | `KekkaiActivation/script_task.py` | `ScriptTask.harvest_card#4` | appear_then_click | `self.I_A_HARVEST_KAIKO_3` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 711 | `KekkaiActivation/script_task.py` | `ScriptTask.harvest_card#5` | appear_then_click | `self.I_A_HARVEST_KAIKO_6` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 712 | `KekkaiActivation/script_task.py` | `ScriptTask.harvest_card#6` | appear_then_click | `self.I_A_HARVEST_FISH_6` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 713 | `KekkaiActivation/script_task.py` | `ScriptTask.harvest_card#7` | appear_then_click | `self.I_A_HARVEST_MOON_3` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 714 | `KekkaiActivation/script_task.py` | `ScriptTask.harvest_card#8` | appear_then_click | `self.I_A_HARVEST_FISH_3` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |

### KekkaiUtilize

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 715 | `KekkaiUtilize/page.py` | `<module>#1` | appear_then_click | `KekkaiUtilizeAssets.I_BOX_EXP` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 716 | `KekkaiUtilize/page.py` | `<module>#2` | appear_then_click | `KekkaiUtilizeAssets.I_BOX_EXP_MAX` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 717 | `KekkaiUtilize/script_task.py` | `ScriptTask.check_max_lv#1` | ui_click | `self.I_AUTO_FILL` | IMMEDIATE | - | - | KEEP_IMMEDIATE | human/H |
| 718 | `KekkaiUtilize/script_task.py` | `ScriptTask.check_and_get_guild_rewards#1` | ui_reward_appear_click | `?` | IMMEDIATE | Y | Timer,sleep | KEEP_SPECIAL | rule/R3 |
| 719 | `KekkaiUtilize/script_task.py` | `ScriptTask.check_and_get_guild_rewards#2` | appear_then_click | `self.I_GUILD_EXPAND` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | human/H |
| 720 | `KekkaiUtilize/script_task.py` | `ScriptTask.check_and_get_guild_rewards#3` | appear_then_click | `self.I_GUILD_ASSETS_RECEIVE` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | human/H |
| 721 | `KekkaiUtilize/script_task.py` | `ScriptTask.check_and_get_guild_rewards#4` | appear_then_click | `self.I_GUILD_ASSETS` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | human/H |
| 722 | `KekkaiUtilize/script_task.py` | `ScriptTask.check_and_get_guild_rewards#5` | appear_then_click | `self.I_GUILD_AP` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | human/H |
| 723 | `KekkaiUtilize/script_task.py` | `ScriptTask.guild_lottery#1` | ui_click_until_appear_or_timeout | `self.I_GUILD_LOTTERY` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | human/H |
| 724 | `KekkaiUtilize/script_task.py` | `ScriptTask.guild_lottery#2` | ui_reward_appear_click | `?` | IMMEDIATE | Y | Timer | KEEP_SPECIAL | rule/R3 |
| 725 | `KekkaiUtilize/script_task.py` | `ScriptTask.guild_lottery#3` | click | `self.C_UI_REWARD` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | human/H |
| 726 | `KekkaiUtilize/script_task.py` | `ScriptTask.guild_lottery#4` | appear_then_click | `self.I_UI_BACK_YELLOW` | IMMEDIATE | - | Timer | KEEP_IMMEDIATE | human/H |
| 727 | `KekkaiUtilize/script_task.py` | `ScriptTask.check_box_ap_or_exp._harvest_ap_box#1` | ui_click_until_smt_disappear | `self.C_UI_REWARD` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | human/H |
| 728 | `KekkaiUtilize/script_task.py` | `ScriptTask.check_box_ap_or_exp._harvest_ap_box#2` | appear_then_click | `self.I_AP_EXTRACT` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | human/H |
| 729 | `KekkaiUtilize/script_task.py` | `ScriptTask.check_box_ap_or_exp._harvest_exp_jug#1` | ui_click_until_disappear | `target_button` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | human/H |
| 730 | `KekkaiUtilize/script_task.py` | `ScriptTask.check_box_ap_or_exp._harvest_exp_jug#2` | click | `self.I_EXP_EXTRACT` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | human/H |
| 731 | `KekkaiUtilize/script_task.py` | `ScriptTask.check_utilize_harvest#1` | ui_get_reward | `self.I_UTILIZE_EXP` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R3 |
| 732 | `KekkaiUtilize/script_task.py` | `ScriptTask.switch_friend_list#1` | execute_single_click | `self.device` | IMMEDIATE | Y | Timer,sleep | KEEP_SPECIAL | rule/R3 |
| 733 | `KekkaiUtilize/script_task.py` | `ScriptTask._run_search_pass#1` | click | `self.C_SELECT_CARD` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | human/H |
| 734 | `KekkaiUtilize/script_task.py` | `ScriptTask._select_lazy_resource_card#1` | click | `self.C_SELECT_CARD` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | human/H |

### KittyShop

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 735 | `KittyShop/script_task.py` | `ScriptTask.run#1` | appear_then_click | `self.I_GO1` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 736 | `KittyShop/script_task.py` | `ScriptTask.run#2` | appear_then_click | `self.I_SHI` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 737 | `KittyShop/script_task.py` | `ScriptTask.run#3` | ui_click | `self.I_UI_BACK_YELLOW` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 738 | `KittyShop/script_task.py` | `ScriptTask._run#1` | ui_click | `self.I_UI_BACK_YELLOW` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 739 | `KittyShop/script_task.py` | `ScriptTask._run#2` | ui_click | `self.I_START_ENSURE` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 740 | `KittyShop/script_task.py` | `ScriptTask._run#3` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 741 | `KittyShop/script_task.py` | `ScriptTask._run#4` | appear_then_click | `self.I_UI_CONFIRM_SAMLL` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 742 | `KittyShop/script_task.py` | `ScriptTask._run#5` | appear_then_click | `self.I_MAIN_FINSH` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 743 | `KittyShop/script_task.py` | `ScriptTask._run#6` | appear_then_click | `self.I_MAIN_GIFT` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 744 | `KittyShop/script_task.py` | `ScriptTask._run#7` | appear_then_click | `self.I_MAIN_ADD` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 745 | `KittyShop/script_task.py` | `ScriptTask._run#8` | click | `self.I_MAIN_FLAG1` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 746 | `KittyShop/script_task.py` | `ScriptTask._select_kitty#1` | ui_click | `self.I_START_FARMING` | IMMEDIATE | - | Timer | KEEP_IMMEDIATE | rule/R7 |
| 747 | `KittyShop/script_task.py` | `ScriptTask._select_kitty#2` | click | `self.C_SELECT_1` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R6 |
| 748 | `KittyShop/script_task.py` | `ScriptTask._select_kitty#3` | click | `self.C_SELECT_2` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R6 |
| 749 | `KittyShop/script_task.py` | `ScriptTask._select_kitty#4` | click | `self.C_SELECT_3` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R6 |
| 750 | `KittyShop/script_task.py` | `ScriptTask._select_kitty#5` | click | `self.C_SELECT_4` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R6 |
| 751 | `KittyShop/script_task.py` | `ScriptTask._main_select_kitty#1` | click | `busy` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |

### MartialArts

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 752 | `MartialArts/page.py` | `find_martial_arts_entry#1` | appear_then_click | `RightActivityAssets.I_TOGGLE_BUTTON` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 753 | `MartialArts/page.py` | `handle_martial_arts_overlay#1` | appear_then_click | `MartialArtsAssets.I_MR_REWARD_MAIN` | IMMEDIATE | Y | Timer,sleep | KEEP_SPECIAL | rule/R4 |
| 754 | `MartialArts/page.py` | `handle_martial_arts_overlay#2` | click | `click` | IMMEDIATE | Y | Timer,sleep | KEEP_SPECIAL | rule/R4 |
| 755 | `MartialArts/page.py` | `handle_martial_arts_overlay#3` | appear_then_click | `MartialArtsAssets.I_MR_MAIN_SIGHIN_CLOSE` | IMMEDIATE | Y | Timer,sleep | KEEP_SPECIAL | rule/R4 |
| 756 | `MartialArts/script_task.py` | `ScriptTask.select_boss_search_mode#1` | appear_then_click | `self.I_MAR_CHANGE_BOSS_MODE` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 757 | `MartialArts/script_task.py` | `ScriptTask.open_existing_boss#1` | appear_then_click | `self.I_UI_CONFIRM_SAMLL` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 758 | `MartialArts/script_task.py` | `ScriptTask.open_existing_boss#2` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 759 | `MartialArts/script_task.py` | `ScriptTask.open_existing_boss#3` | click | `self.C_SELECT_FIRE_BOSS` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R6 |
| 760 | `MartialArts/script_task.py` | `ScriptTask.search_boss_in_mode#1` | appear_then_click | `fire_rule` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 761 | `MartialArts/script_task.py` | `ScriptTask.search_boss_in_mode#2` | appear_then_click | `self.I_UI_CONFIRM_SAMLL` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 762 | `MartialArts/script_task.py` | `ScriptTask.search_boss_in_mode#3` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 763 | `MartialArts/script_task.py` | `ScriptTask.switch_soul_before_battle#1` | ui_click | `enter_records` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 764 | `MartialArts/script_task.py` | `ScriptTask.lock_team#1` | ui_click | `unlock_rule` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 765 | `MartialArts/script_task.py` | `ScriptTask.lock_team#2` | ui_click | `lock_rule` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 766 | `MartialArts/script_task.py` | `ScriptTask.enter_battle#1` | appear_then_click | `self.I_UI_CONFIRM_SAMLL` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 767 | `MartialArts/script_task.py` | `ScriptTask.enter_battle#2` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 768 | `MartialArts/script_task.py` | `ScriptTask.enter_battle#3` | appear_then_click | `self.I_UI_BACK_RED` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 769 | `MartialArts/script_task.py` | `ScriptTask.enter_battle#4` | click | `self.I_MAR_FIRE_AP` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R6 |
| 770 | `MartialArts/script_task.py` | `ScriptTask.enter_boss_fight#1` | appear_then_click | `self.I_UI_CONFIRM_SAMLL` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 771 | `MartialArts/script_task.py` | `ScriptTask.enter_boss_fight#2` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 772 | `MartialArts/script_task.py` | `ScriptTask.enter_boss_fight#3` | appear_then_click | `self.I_MAR_FIRE_BOSS_MAIN` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 773 | `MartialArts/script_task.py` | `ScriptTask.enter_boss_fight#4` | appear_then_click | `self.I_MAR_FIRE_BOSS_MAIN_AGAIN` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |

### MemoryScrolls

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 774 | `MemoryScrolls/script_task.py` | `ScriptTask.goto_memoryscrolls_main#1` | click | `self.C_MS_DOUBLE_SCROLLS_2` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R6 |
| 775 | `MemoryScrolls/script_task.py` | `ScriptTask.goto_memoryscrolls_main#2` | appear_then_click | `self.I_MS_DOUBLE_SCROLLS_ENTER` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R8 |
| 776 | `MemoryScrolls/script_task.py` | `ScriptTask.goto_memoryscrolls_main#3` | appear_then_click | `self.I_MS_ENTER` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R8 |
| 777 | `MemoryScrolls/script_task.py` | `ScriptTask.goto_memoryscrolls_main#4` | ui_click | `self.I_MS_FRAGMENT_S` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 778 | `MemoryScrolls/script_task.py` | `ScriptTask.goto_memoryscrolls_main#5` | ui_click_until_disappear | `GlobalGameAssets.I_UI_BACK_YELLOW` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 779 | `MemoryScrolls/script_task.py` | `ScriptTask.goto_memoryscrolls_main#6` | ui_click_until_smt_disappear | `self.I_MS_FRAGMENT_S` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 780 | `MemoryScrolls/script_task.py` | `ScriptTask.goto_memoryscrolls_main#7` | ui_click_until_disappear | `GlobalGameAssets.I_UI_BACK_YELLOW` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 781 | `MemoryScrolls/script_task.py` | `ScriptTask.goto_scroll#1` | click | `self.C_MS_SCROLL_1` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 782 | `MemoryScrolls/script_task.py` | `ScriptTask.goto_scroll#2` | click | `self.C_MS_SCROLL_2` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 783 | `MemoryScrolls/script_task.py` | `ScriptTask.goto_scroll#3` | click | `self.C_MS_SCROLL_3` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 784 | `MemoryScrolls/script_task.py` | `ScriptTask.goto_scroll#4` | click | `self.C_MS_SCROLL_4` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 785 | `MemoryScrolls/script_task.py` | `ScriptTask.goto_scroll#5` | click | `self.C_MS_SCROLL_5` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 786 | `MemoryScrolls/script_task.py` | `ScriptTask.goto_scroll#6` | click | `self.C_MS_SCROLL_6` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 787 | `MemoryScrolls/script_task.py` | `ScriptTask.goto_scroll#7` | ui_click_until_disappear | `GlobalGameAssets.I_UI_BACK_RED` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 788 | `MemoryScrolls/script_task.py` | `ScriptTask.contribute_memoryscrolls#1` | appear_then_click | `self.I_MS_CONTRIBUTE` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R8 |
| 789 | `MemoryScrolls/script_task.py` | `ScriptTask.contribute_memoryscrolls#2` | click | `self.C_MS_CONTRIBUTED` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R6 |

### MetaDemon

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 790 | `MetaDemon/script_task.py` | `ScriptTask.run#1` | click | `ipages.random_click()` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R6 |
| 791 | `MetaDemon/script_task.py` | `ScriptTask.start_battle#1` | click | `self.I_MD_DRINK_TEA` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 792 | `MetaDemon/script_task.py` | `ScriptTask.start_battle#2` | ui_click_until_disappear | `self.I_MD_CLOSE_POPUP` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 793 | `MetaDemon/script_task.py` | `ScriptTask.start_battle#3` | appear_then_click | `self.I_MD_FIRE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 794 | `MetaDemon/script_task.py` | `ScriptTask.battle_wait#1` | click | `ipages.random_click()` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R6 |
| 795 | `MetaDemon/script_task.py` | `ScriptTask.battle_wait#2` | click | `ipages.random_click()` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R6 |
| 796 | `MetaDemon/script_task.py` | `ScriptTask.synthesis_boss_ticket#1` | ui_click | `self.I_MD_SYNTHESIS` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 797 | `MetaDemon/script_task.py` | `ScriptTask.synthesis_boss_ticket#2` | ui_click | `self.I_MD_CLOSE_POPUP` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 798 | `MetaDemon/script_task.py` | `ScriptTask.do_synthesis#1` | ui_click | `self.I_MD_CLOSE_POPUP` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 799 | `MetaDemon/script_task.py` | `ScriptTask.do_synthesis#2` | click | `ipages.random_click()` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 800 | `MetaDemon/script_task.py` | `ScriptTask.do_synthesis#3` | appear_then_click | `target_boss_ticket` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 801 | `MetaDemon/script_task.py` | `ScriptTask.do_synthesis#4` | appear_then_click | `self.I_MD_START_SYNTHESIS` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 802 | `MetaDemon/script_task.py` | `ScriptTask.check_and_switch_ticket#1` | appear_then_click | `self.I_MD_SWITCH_TICKET` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 803 | `MetaDemon/script_task.py` | `ScriptTask.check_and_switch_ticket#2` | ui_click_until_disappear | `self.I_MD_CLOSE_POPUP` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 804 | `MetaDemon/script_task.py` | `ScriptTask.check_and_switch_ticket#3` | ui_click_until_disappear | `self.I_MD_CLOSE_POPUP` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 805 | `MetaDemon/script_task.py` | `ScriptTask.check_and_switch_ticket#4` | ui_click_until_disappear | `self.I_MD_GET_BOSS` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 806 | `MetaDemon/script_task.py` | `ScriptTask.check_and_switch_ticket#5` | appear_then_click | `target_ticket_rule_image` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 807 | `MetaDemon/script_task.py` | `ScriptTask.check_and_switch_powerful#1` | ui_click | `self.I_MD_ENABLE_POWERFUL_FIRE` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 808 | `MetaDemon/script_task.py` | `ScriptTask.check_and_switch_powerful#2` | ui_click | `self.I_MD_DISABLE_POWERFUL_FIRE` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |

### MultiAccountEvo

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 809 | `MultiAccountEvo/script_task.py` | `ScriptTask.appear_then_click#1` | appear_then_click | `target` | IMMEDIATE | - | - | EXCLUDED | rule/R1 |
| 810 | `MultiAccountEvo/script_task.py` | `ScriptTask._detect_select#1` | execute_single_click | `self.device` | IMMEDIATE | Y | - | EXCLUDED | rule/R1 |
| 811 | `MultiAccountEvo/script_task.py` | `ScriptTask.check_then_accept#1` | appear_then_click | `self.I_I_NO_DEFAULT` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 812 | `MultiAccountEvo/script_task.py` | `ScriptTask.check_then_accept#2` | appear_then_click | `self.I_GI_SURE` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 813 | `MultiAccountEvo/script_task.py` | `ScriptTask.check_then_accept#3` | appear_then_click | `self.I_I_ACCEPT_DEFAULT` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 814 | `MultiAccountEvo/script_task.py` | `ScriptTask.check_then_accept#4` | execute_single_click | `self.device` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 815 | `MultiAccountEvo/script_task.py` | `ScriptTask._handle_result#1` | click | `self._multi_account_settlement_click()` | IMMEDIATE | - | - | EXCLUDED | rule/R1 |
| 816 | `MultiAccountEvo/script_task.py` | `ScriptTask._handle_reward#1` | appear_then_click | `self.I_GB_SKIN_CONFIRM` | IMMEDIATE | - | - | EXCLUDED | rule/R1 |
| 817 | `MultiAccountEvo/script_task.py` | `ScriptTask._handle_reward#2` | click | `self._multi_account_settlement_click()` | IMMEDIATE | - | - | EXCLUDED | rule/R1 |

### MysteryShop

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 818 | `MysteryShop/script_task.py` | `ScriptTask.run#1` | ui_click | `self.I_ME_ENTER` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 819 | `MysteryShop/script_task.py` | `ScriptTask.next_one#1` | appear_then_click | `self.I_MS_NEXT` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 820 | `MysteryShop/script_task.py` | `ScriptTask.next_one#2` | appear_then_click | `self.I_MS_NEXT` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 821 | `MysteryShop/script_task.py` | `ScriptTask.share#1` | ui_click | `self.I_MS_SHARE` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 822 | `MysteryShop/script_task.py` | `ScriptTask.shop_reward#1` | ui_get_reward | `self.I_MS_REWARD_3` | IMMEDIATE | - | sleep | KEEP_SPECIAL | rule/R4 |
| 823 | `MysteryShop/script_task.py` | `ScriptTask.shop_reward#2` | ui_get_reward | `self.I_MS_REWARD_5` | IMMEDIATE | - | sleep | KEEP_SPECIAL | rule/R4 |
| 824 | `MysteryShop/script_task.py` | `ScriptTask.shop_reward#3` | ui_get_reward | `self.I_MS_REWARD_10` | IMMEDIATE | - | sleep | KEEP_SPECIAL | rule/R4 |

### Nian

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 825 | `Nian/script_task.py` | `ScriptTask.run#1` | appear_then_click | `self.I_GR_AUTO_MATCH` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 826 | `Nian/script_task.py` | `ScriptTask.run#2` | click | `self.C_CLIC_SAFE` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R6 |
| 827 | `Nian/script_task.py` | `ScriptTask.run#3` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 828 | `Nian/script_task.py` | `ScriptTask.run#4` | appear_then_click | `self.I_UI_CONFIRM_SAMLL` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 829 | `Nian/script_task.py` | `ScriptTask.run#5` | appear_then_click | `self.I_N_WAITING` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |

### Orochi

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 830 | `Orochi/script_task.py` | `ScriptTask._close_orochi_soul_choice_popup#1` | appear_then_click | `self.I_GB_CLOSE_RED` | IMMEDIATE | - | - | KEEP_SPECIAL | human/H |
| 831 | `Orochi/script_task.py` | `ScriptTask.check_layer#1` | execute_single_click | `self.device` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R3 |
| 832 | `Orochi/script_task.py` | `ScriptTask.run_leader#1` | appear_then_click | `self.I_FORM_TEAM` | NORMAL | Y | - | ALREADY_L2 | human/H |
| 833 | `Orochi/script_task.py` | `ScriptTask.run_member#1` | appear_then_click | `self.I_PET_PRESENT` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | human/H |
| 834 | `Orochi/script_task.py` | `ScriptTask._fire_orochi_alone#1` | appear_then_click | `self.I_OROCHI_FIRE` | IMMEDIATE | Y | Timer,random_delay,sleep | ALREADY_L2 | human/H |
| 835 | `Orochi/script_task.py` | `ScriptTask.run_alone#1` | appear_then_click | `self.I_PET_PRESENT` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | human/H |
| 836 | `Orochi/script_task.py` | `ScriptTask.run_wild#1` | appear_then_click | `self.I_FORM_TEAM` | NORMAL | Y | - | ALREADY_L2 | human/H |
| 837 | `Orochi/script_task.py` | `ScriptTask.run_wild#2` | appear_then_click | `self.I_PET_PRESENT` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | human/H |
| 838 | `Orochi/script_task.py` | `ScriptTask.run_wild#3` | appear_then_click | `self.I_OROCHI_WILD_FIRE` | IMMEDIATE | Y | - | KEEP_SPECIAL | human/H |

### OtherWorldTwilight

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 839 | `OtherWorldTwilight/script_task.py` | `ScriptTask.run_leader#1` | ui_click | `self.I_OWT_TEAM` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 840 | `OtherWorldTwilight/script_task.py` | `ScriptTask.run_alone#1` | appear_then_click | `self.I_OWT_FIRE` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |

### Pets

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 841 | `Pets/script_task.py` | `ScriptTask._feed#1` | ui_click | `self.I_PET_FEAST` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 842 | `Pets/script_task.py` | `ScriptTask._feed#2` | appear_then_click | `self.I_UI_BACK_CIRCLE` | NAVIGATION | - | - | ALREADY_L2 | c0/C1 |
| 843 | `Pets/script_task.py` | `ScriptTask._feed#3` | ui_click | `self.I_PET_FEED` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 844 | `Pets/script_task.py` | `ScriptTask._feed#4` | ui_click_until_disappear | `self.I_PET_SKIP` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |

### Quiz

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 845 | `Quiz/script_task.py` | `ScriptTask.run#1` | ui_click | `self.I_UI_BACK_YELLOW` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 846 | `Quiz/script_task.py` | `ScriptTask.enter#1` | appear_then_click | `self.I_ENTRY` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 847 | `Quiz/script_task.py` | `ScriptTask.once#1` | appear_then_click | `self.I_START` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 848 | `Quiz/script_task.py` | `ScriptTask.once#2` | ui_reward_appear_click | `?` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R7 |
| 849 | `Quiz/script_task.py` | `ScriptTask.once#3` | ui_click | `self.I_FAIL_QUIT` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R7 |
| 850 | `Quiz/script_task.py` | `ScriptTask.once#4` | ui_click | `self.I_UI_BACK_RED` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R7 |
| 851 | `Quiz/script_task.py` | `ScriptTask._deal_quiz#1` | appear_then_click | `self.I_ALONE_ENSURE` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | c0/C0K |
| 852 | `Quiz/script_task.py` | `ScriptTask._deal_quiz#2` | click | `self.click_options[index-1]` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R6 |
| 853 | `Quiz/script_task.py` | `ScriptTask._deal_quiz#3` | click | `self.C_ANSWER_ENSURE_1` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R6 |
| 854 | `Quiz/script_task.py` | `ScriptTask._deal_quiz#4` | click | `self.C_ANSWER_ENSURE_2` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R6 |
| 855 | `Quiz/script_task.py` | `ScriptTask._deal_quiz#5` | click | `self.C_ANSWER_ENSURE_3` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R6 |
| 856 | `Quiz/script_task.py` | `ScriptTask._deal_quiz#6` | click | `self.C_ANSWER_ENSURE_4` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R6 |

### RealmRaid

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 857 | `RealmRaid/script_task.py` | `ScriptTask.run#1` | appear_then_click | `self.I_FROG_RAID` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | human/H |
| 858 | `RealmRaid/script_task.py` | `ScriptTask.ensure_lock#1` | appear_then_click | `self.I_UNLOCK` | FAST | Y | - | ALREADY_L2 | human/H |
| 859 | `RealmRaid/script_task.py` | `ScriptTask.ensure_lock#2` | appear_then_click | `self.I_UNLOCK_2` | FAST | Y | - | ALREADY_L2 | human/H |
| 860 | `RealmRaid/script_task.py` | `ScriptTask.ensure_lock#3` | appear_then_click | `self.I_LOCK` | FAST | Y | - | ALREADY_L2 | human/H |
| 861 | `RealmRaid/script_task.py` | `ScriptTask.ensure_lock#4` | appear_then_click | `self.I_LOCK_2` | FAST | Y | - | ALREADY_L2 | human/H |
| 862 | `RealmRaid/script_task.py` | `ScriptTask._enter_target#1` | click | `self.partition[order - 1]` | IMMEDIATE | - | random_delay,sleep | KEEP_SPECIAL | human/H |
| 863 | `RealmRaid/script_task.py` | `ScriptTask.reward_detect_click#1` | ui_click_until_disappear | `self.I_SOUL_RAID` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | human/H |
| 864 | `RealmRaid/script_task.py` | `ScriptTask.reward_detect_click#2` | appear_then_click | `self.I_SOUL_RAID` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | human/H |
| 865 | `RealmRaid/script_task.py` | `ScriptTask.check_refresh#1` | appear_then_click | `self.I_FRESH` | NORMAL | Y | - | ALREADY_L2 | human/H |
| 866 | `RealmRaid/script_task.py` | `ScriptTask.check_refresh#2` | appear_then_click | `self.I_FRESH_ENSURE` | CONFIRM | Y | - | ALREADY_L2 | human/H |
| 867 | `RealmRaid/script_task.py` | `ScriptTask.fire#1` | click | `click` | IMMEDIATE | Y | Timer,random_delay,sleep,wait_until | KEEP_SPECIAL | human/H |
| 868 | `RealmRaid/script_task.py` | `ScriptTask.fire#2` | appear_then_click | `self.I_FIRE` | IMMEDIATE | Y | Timer,random_delay,sleep,wait_until | ALREADY_L2 | human/H |
| 869 | `RealmRaid/script_task.py` | `ScriptTask._fire_again#1` | appear_then_click | `self.I_SHOW_AGAIN` | IMMEDIATE | Y | Timer,random_delay,sleep,wait_until | KEEP_IMMEDIATE | human/H |
| 870 | `RealmRaid/script_task.py` | `ScriptTask._fire_again#2` | appear_then_click | `self.I_FRESH_ENSURE` | confirm_delay | Y | Timer,random_delay,sleep,wait_until | ALREADY_L2 | human/H |
| 871 | `RealmRaid/script_task.py` | `ScriptTask._fire_again#3` | appear_then_click | `self.I_FIRE_AGAIN` | IMMEDIATE | Y | Timer,random_delay,sleep,wait_until | ALREADY_L2 | human/H |

### RyouToppa

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 872 | `RyouToppa/script_task.py` | `ScriptTask._wait_for_ryou_toppa_state#1` | appear_then_click | `RealmRaidAssets.I_REALM_RAID` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | human/H |
| 873 | `RyouToppa/script_task.py` | `ScriptTask._wait_for_ryou_toppa_state#2` | appear_then_click | `self.I_RYOU_TOPPA` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | human/H |
| 874 | `RyouToppa/script_task.py` | `ScriptTask._ensure_team_lock_state#1` | appear_then_click | `source` | FAST | Y | Timer | ALREADY_L2 | human/H |
| 875 | `RyouToppa/script_task.py` | `ScriptTask._click_toppa_area#1` | execute_single_click | `self.device` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R3 |
| 876 | `RyouToppa/script_task.py` | `ScriptTask._click_toppa_area#2` | click | `rule` | IMMEDIATE | - | - | KEEP_SPECIAL | human/H |
| 877 | `RyouToppa/script_task.py` | `ScriptTask.start_ryou_toppa#1` | appear_then_click | `self.I_SELECT_RYOU_BUTTON` | FAST | Y | - | ALREADY_L2 | human/H |
| 878 | `RyouToppa/script_task.py` | `ScriptTask.start_ryou_toppa#2` | appear_then_click | `self.I_GUILD_ORDERS_REWARDS` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | human/H |
| 879 | `RyouToppa/script_task.py` | `ScriptTask.start_ryou_toppa#3` | appear_then_click | `self.I_START_TOPPA_BUTTON` | FAST | Y | - | ALREADY_L2 | human/H |
| 880 | `RyouToppa/script_task.py` | `ScriptTask.attack_area#1` | appear_then_click | `RealmRaidAssets.I_FIRE` | IMMEDIATE | Y | random_delay,sleep | ALREADY_L2 | human/H |

### Secret

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 881 | `Secret/script_task.py` | `ScriptTask.run#1` | ui_click | `self.I_SE_ENTER` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R7 |
| 882 | `Secret/script_task.py` | `ScriptTask.find_battle#1` | ui_click_until_disappear | `self.I_CHAT_CLOSE_BUTTON` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R7 |
| 883 | `Secret/script_task.py` | `ScriptTask.find_battle#2` | execute_single_click | `self.device` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R10 |
| 884 | `Secret/script_task.py` | `ScriptTask.click_battle#1` | appear_then_click | `self.I_SE_FIRE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |

### SixRealms

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 885 | `SixRealms/common.py` | `SixRealmsCommon.open_shop#1` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 886 | `SixRealms/common.py` | `SixRealmsCommon.open_shop#2` | appear_then_click | `store_rule` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 887 | `SixRealms/common.py` | `SixRealmsCommon.open_shop#3` | appear_then_click | `self.I_UI_CANCEL` | IMMEDIATE | - | Timer | KEEP_IMMEDIATE | c0/C0K |
| 888 | `SixRealms/common.py` | `SixRealmsCommon.enter_battle#1` | ui_click | `normal_unlock` | IMMEDIATE | - | Timer | KEEP_IMMEDIATE | rule/R7 |
| 889 | `SixRealms/common.py` | `SixRealmsCommon.enter_battle#2` | ui_click | `boss_unlock` | IMMEDIATE | - | Timer | KEEP_IMMEDIATE | rule/R7 |
| 890 | `SixRealms/common.py` | `SixRealmsCommon.enter_battle#3` | appear_then_click | `fire_rule` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 891 | `SixRealms/common.py` | `SixRealmsCommon.refresh_store#1` | appear_then_click | `refresh_rule` | CONFIRM | - | - | ALREADY_L2 | c0/C1 |
| 892 | `SixRealms/common.py` | `SixRealmsCommon.buy_skill#1` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 893 | `SixRealms/common.py` | `SixRealmsCommon.buy_skill#2` | execute_single_click | `self.device` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R10 |
| 894 | `SixRealms/common.py` | `SixRealmsCommon.choose_and_enter_island#1` | appear_then_click | `target_land` | NORMAL | - | - | ALREADY_L2 | c0/C1 |
| 895 | `SixRealms/moon_sea/base_moon_sea.py` | `BaseMoonSea._handle_in_battle#1` | appear_then_click | `self.I_BOSS_SKIP` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 896 | `SixRealms/moon_sea/base_moon_sea.py` | `BaseMoonSea._handle_result#1` | click | `self.I_BOSS_BATTLE_GIVEUP` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 897 | `SixRealms/moon_sea/base_moon_sea.py` | `BaseMoonSea._handle_result#2` | click | `self.I_UI_CONFIRM_SAMLL` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 898 | `SixRealms/moon_sea/base_moon_sea.py` | `BaseMoonSea._handle_result#3` | appear_then_click | `select_btn` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 899 | `SixRealms/moon_sea/base_moon_sea.py` | `BaseMoonSea._handle_reward#1` | appear_then_click | `self.I_SR_DOUBLE_REWARD_USE` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 900 | `SixRealms/moon_sea/base_moon_sea.py` | `BaseMoonSea._handle_reward#2` | appear_then_click | `self.I_SR_DOUBLE_REWARD_CANCEL` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 901 | `SixRealms/moon_sea/base_moon_sea.py` | `BaseMoonSea._handle_reward#3` | appear_then_click | `self.I_SR_NOT_TIP` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 902 | `SixRealms/moon_sea/base_moon_sea.py` | `BaseMoonSea._handle_reward#4` | appear_then_click | `self.I_UI_CANCEL` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 903 | `SixRealms/moon_sea/base_moon_sea.py` | `BaseMoonSea._handle_reward#5` | click | `pages.random_click()` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 904 | `SixRealms/moon_sea/moon_sea.py` | `MoonSea.ms_page_handle_dict#1` | click | `pages.random_click(ltrb=(True, False, False, False))` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 905 | `SixRealms/moon_sea/moon_sea.py` | `MoonSea.ms_page_handle_dict#2` | click | `pages.random_click()` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 906 | `SixRealms/moon_sea/moon_sea.py` | `MoonSea.run_on_ms#1` | appear_then_click | `self.I_MCONINUE` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 907 | `SixRealms/moon_sea/moon_sea.py` | `MoonSea.run_on_ms#2` | appear_then_click | `self.I_MSTART` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 908 | `SixRealms/moon_sea/moon_sea.py` | `MoonSea.run_on_ms_prepare#1` | appear_then_click | `self.I_MSTART_CONFIRM` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 909 | `SixRealms/moon_sea/moon_sea.py` | `MoonSea.run_on_ms_prepare#2` | appear_then_click | `self.I_MSTART_CONFIRM2` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 910 | `SixRealms/moon_sea/moon_sea.py` | `MoonSea.run_on_ms_prepare#3` | appear_then_click | `self.I_MFIRST_SKILL` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 911 | `SixRealms/moon_sea/moon_sea.py` | `MoonSea.run_on_ms_mistery#1` | appear_then_click | `self.I_MISTERY_IMITATE_SKILL_101` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 912 | `SixRealms/moon_sea/moon_sea.py` | `MoonSea.run_on_ms_mistery#2` | click | `pages.random_click()` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R4 |
| 913 | `SixRealms/moon_sea/moon_sea.py` | `MoonSea.run_on_ms_mistery#3` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R4 |
| 914 | `SixRealms/moon_sea/moon_sea.py` | `MoonSea.run_on_ms_mistery#4` | appear_then_click | `self.I_MISTERY_IMITATE` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R4 |
| 915 | `SixRealms/moon_sea/moon_sea.py` | `MoonSea.run_on_ms_chaos#1` | ui_click | `self.C_NPC_FIRE_CENTER` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 916 | `SixRealms/moon_sea/moon_sea.py` | `MoonSea.run_on_ms_star#1` | ui_click | `self.C_NPC_FIRE_LEFT` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 917 | `SixRealms/moon_sea/moon_sea.py` | `MoonSea.run_on_ms_battle#1` | ui_click | `self.C_NPC_FIRE_RIGHT` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 918 | `SixRealms/page.py` | `handle_enter_moon_sea#1` | ui_click | `SixRealmsAssets.I_SR_SWITCH` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 919 | `SixRealms/page.py` | `handle_enter_moon_sea#2` | appear_then_click | `SixRealmsAssets.I_SR_TO_MOON_SEA` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 920 | `SixRealms/page.py` | `switch_moon_sea_shikigami#1` | ui_click | `SixRealmsAssets.C_SR_SWITCH_SHIKIGAMI` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 921 | `SixRealms/page.py` | `switch_moon_sea_shikigami#2` | appear_then_click | `SixRealmsAssets.I_MSHOUZU_SELECT` | IMMEDIATE | - | - | KEEP_SPECIAL | c0/C0S |
| 922 | `SixRealms/page.py` | `handle_enter_peacock_kingdom#1` | ui_click | `SixRealmsAssets.I_SR_SWITCH` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 923 | `SixRealms/page.py` | `handle_enter_peacock_kingdom#2` | appear_then_click | `SixRealmsAssets.I_SR_TO_PEACOCK_KINGDOM` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 924 | `SixRealms/page.py` | `handle_enter_incense_realm#1` | ui_click | `SixRealmsAssets.I_SR_SWITCH` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 925 | `SixRealms/page.py` | `handle_enter_incense_realm#2` | appear_then_click | `SixRealmsAssets.I_SR_TO_INCENSE_REALM` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 926 | `SixRealms/page.py` | `handle_enter_seasonrift_forest#1` | ui_click | `SixRealmsAssets.I_SR_SWITCH` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 927 | `SixRealms/page.py` | `handle_enter_seasonrift_forest#2` | appear_then_click | `SixRealmsAssets.I_SR_TO_SEASONRIFT_FOREST` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 928 | `SixRealms/page.py` | `handle_enter_pure_buddha_realm#1` | ui_click | `SixRealmsAssets.I_SR_SWITCH` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 929 | `SixRealms/page.py` | `handle_enter_pure_buddha_realm#2` | appear_then_click | `SixRealmsAssets.I_SR_TO_PURE_BUDDHA_REALM` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 930 | `SixRealms/page.py` | `handle_enter_mantra_tower#1` | ui_click | `SixRealmsAssets.I_SR_SWITCH` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 931 | `SixRealms/page.py` | `handle_enter_mantra_tower#2` | appear_then_click | `SixRealmsAssets.I_SR_TO_MANTRA_TOWER` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 932 | `SixRealms/peacock_kingdom/base_peacock_kingdom.py` | `BasePeacockKingdom._mark_peacock_boss#1` | appear_then_click | `self.I_LOCAL` | IMMEDIATE | - | sleep | KEEP_SPECIAL | c0/C0S |
| 933 | `SixRealms/peacock_kingdom/base_peacock_kingdom.py` | `BasePeacockKingdom._mark_peacock_boss#2` | execute_single_click | `self.device` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R10 |
| 934 | `SixRealms/peacock_kingdom/base_peacock_kingdom.py` | `BasePeacockKingdom._handle_result#1` | click | `self.I_BOSS_BATTLE_GIVEUP` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 935 | `SixRealms/peacock_kingdom/base_peacock_kingdom.py` | `BasePeacockKingdom._handle_result#2` | click | `self.I_UI_CONFIRM_SAMLL` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 936 | `SixRealms/peacock_kingdom/base_peacock_kingdom.py` | `BasePeacockKingdom._handle_result#3` | appear_then_click | `select_btn` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 937 | `SixRealms/peacock_kingdom/base_peacock_kingdom.py` | `BasePeacockKingdom._handle_result#4` | appear_then_click | `select_btn` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 938 | `SixRealms/peacock_kingdom/base_peacock_kingdom.py` | `BasePeacockKingdom._handle_reward#1` | appear_then_click | `self.I_SR_DOUBLE_REWARD_USE` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 939 | `SixRealms/peacock_kingdom/base_peacock_kingdom.py` | `BasePeacockKingdom._handle_reward#2` | appear_then_click | `self.I_SR_DOUBLE_REWARD_CANCEL` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 940 | `SixRealms/peacock_kingdom/base_peacock_kingdom.py` | `BasePeacockKingdom._handle_reward#3` | appear_then_click | `self.I_SR_NOT_TIP` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 941 | `SixRealms/peacock_kingdom/base_peacock_kingdom.py` | `BasePeacockKingdom._handle_reward#4` | appear_then_click | `self.I_UI_CANCEL` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 942 | `SixRealms/peacock_kingdom/base_peacock_kingdom.py` | `BasePeacockKingdom._handle_reward#5` | click | `pages.random_click()` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 943 | `SixRealms/peacock_kingdom/peacock_kingdom.py` | `PeacockKingdom.pk_page_handle_dict#1` | click | `pages.random_click(ltrb=(True, False, False, False))` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 944 | `SixRealms/peacock_kingdom/peacock_kingdom.py` | `PeacockKingdom.pk_page_handle_dict#2` | click | `pages.random_click()` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 945 | `SixRealms/peacock_kingdom/peacock_kingdom.py` | `PeacockKingdom.run_on_pk#1` | appear_then_click | `self.I_PK_CONTINUE` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 946 | `SixRealms/peacock_kingdom/peacock_kingdom.py` | `PeacockKingdom.run_on_pk#2` | appear_then_click | `self.I_PK_START` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 947 | `SixRealms/peacock_kingdom/peacock_kingdom.py` | `PeacockKingdom.run_on_pk_prepare#1` | appear_then_click | `self.I_PK_START_CONFIRM` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 948 | `SixRealms/peacock_kingdom/peacock_kingdom.py` | `PeacockKingdom.run_on_pk_prepare#2` | appear_then_click | `self.I_PK_START_CONFIRM2` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 949 | `SixRealms/peacock_kingdom/peacock_kingdom.py` | `PeacockKingdom.run_on_pk_prepare#3` | appear_then_click | `self.I_PK_START_THIRD_SKILL` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 950 | `SixRealms/peacock_kingdom/peacock_kingdom.py` | `PeacockKingdom.run_on_pk_prepare#4` | appear_then_click | `self.I_MFIRST_SKILL` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 951 | `SixRealms/peacock_kingdom/peacock_kingdom.py` | `PeacockKingdom._summon_store#1` | appear_then_click | `self.I_M_STORE_ACTIVITY` | IMMEDIATE | - | wait_until | DEFERRED | c0/C0D |
| 952 | `SixRealms/peacock_kingdom/peacock_kingdom.py` | `PeacockKingdom._summon_store#2` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | - | wait_until | DEFERRED | c0/C0D |
| 953 | `SixRealms/peacock_kingdom/peacock_kingdom.py` | `PeacockKingdom._use_breath#1` | appear_then_click | `self.I_M_STORE_ACTIVITY` | IMMEDIATE | - | - | DEFERRED | c0/C0D |
| 954 | `SixRealms/peacock_kingdom/peacock_kingdom.py` | `PeacockKingdom._confirm_store_entry#1` | appear_then_click | `self.I_PK_STORE_STILLIN` | IMMEDIATE | - | wait_until | DEFERRED | c0/C0D |
| 955 | `SixRealms/peacock_kingdom/peacock_kingdom.py` | `PeacockKingdom.run_on_pk_chaos#1` | ui_click | `self.C_NPC_FIRE_CENTER` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |
| 956 | `SixRealms/peacock_kingdom/peacock_kingdom.py` | `PeacockKingdom.run_on_pk_battle#1` | ui_click | `self.C_NPC_FIRE_RIGHT` | IMMEDIATE | - | - | KEEP_SPECIAL | rule/R4 |

### Sougenbi

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 957 | `Sougenbi/script_task.py` | `ScriptTask._fire_sougenbi#1` | appear_then_click | `self.I_S_FIRE` | IMMEDIATE | Y | Timer,random_delay,sleep | KEEP_SPECIAL | rule/R3 |
| 958 | `Sougenbi/script_task.py` | `ScriptTask.run#1` | appear_then_click | `self.I_S_SOUGENBI` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | rule/R3 |
| 959 | `Sougenbi/script_task.py` | `ScriptTask.run#2` | click | `click_target` | IMMEDIATE | Y | sleep | KEEP_SPECIAL | rule/R3 |

### SoulsTidy

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 960 | `SoulsTidy/script_task.py` | `ScriptTask.goto_souls#1` | appear_then_click | `self.I_ST_REPLACE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 961 | `SoulsTidy/script_task.py` | `ScriptTask.goto_souls#2` | appear_then_click | `self.I_ST_SOULS` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 962 | `SoulsTidy/script_task.py` | `ScriptTask.goto_souls#3` | appear_then_click | `self.I_ST_SOULS_CLOSE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 963 | `SoulsTidy/script_task.py` | `ScriptTask.goto_souls#4` | click | `self.C_ST_DETAIL` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 964 | `SoulsTidy/script_task.py` | `ScriptTask.goto_souls#5` | ocr_appear_click | `self.O_ST_OVERFLOW` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 965 | `SoulsTidy/script_task.py` | `ScriptTask.greed_maneki#1` | ui_click | `self.I_ST_GREED` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 966 | `SoulsTidy/script_task.py` | `ScriptTask.greed_maneki#2` | ui_click | `self.I_ST_GREED_HABIT` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 967 | `SoulsTidy/script_task.py` | `ScriptTask.greed_maneki#3` | ui_click_until_disappear | `self.I_ST_UNSELECTED` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 968 | `SoulsTidy/script_task.py` | `ScriptTask.greed_maneki#4` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 969 | `SoulsTidy/script_task.py` | `ScriptTask.greed_maneki#5` | appear_then_click | `self.I_ST_FEED_NOW` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 970 | `SoulsTidy/script_task.py` | `ScriptTask.greed_maneki#6` | ui_click_until_disappear | `self.I_ST_UNSELECTED` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 971 | `SoulsTidy/script_task.py` | `ScriptTask.greed_maneki#7` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 972 | `SoulsTidy/script_task.py` | `ScriptTask.greed_maneki#8` | appear_then_click | `self.I_ST_GREED_CLOSE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 973 | `SoulsTidy/script_task.py` | `ScriptTask.greed_maneki#9` | appear_then_click | `self.I_ST_BONGNA` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 974 | `SoulsTidy/script_task.py` | `ScriptTask.greed_maneki#10` | click | `self.I_UI_BACK_RED` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 975 | `SoulsTidy/script_task.py` | `ScriptTask.greed_maneki#11` | click | `self.I_ST_ABANDONED_SELECTED` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 976 | `SoulsTidy/script_task.py` | `ScriptTask.greed_maneki#12` | click | `self.L_ONE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 977 | `SoulsTidy/script_task.py` | `ScriptTask.pre_confirm#1` | click | `self.I_UI_BACK_RED` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 978 | `SoulsTidy/script_task.py` | `ScriptTask.pre_confirm#2` | ocr_appear_click | `self.O_ST_SORT_LEVEL_2` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 979 | `SoulsTidy/script_task.py` | `ScriptTask.pre_confirm#3` | ocr_appear_click | `self.O_ST_SORT_TIME` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 980 | `SoulsTidy/script_task.py` | `ScriptTask.pre_confirm#4` | ocr_appear_click | `self.O_ST_SORT_TYPE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 981 | `SoulsTidy/script_task.py` | `ScriptTask.pre_confirm#5` | ocr_appear_click | `self.O_ST_SORT_LOCATION` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R7 |
| 982 | `SoulsTidy/script_task.py` | `ScriptTask.donate_and_collect_reward#1` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | wait_until | KEEP_SPECIAL | rule/R4 |
| 983 | `SoulsTidy/script_task.py` | `ScriptTask.donate_and_collect_reward#2` | ui_reward_appear_click | `?` | IMMEDIATE | Y | wait_until | KEEP_SPECIAL | rule/R4 |
| 984 | `SoulsTidy/script_task.py` | `ScriptTask.donate_and_collect_reward#3` | click | `self.C_ST_GOD_PRSENT` | IMMEDIATE | Y | wait_until | KEEP_SPECIAL | rule/R4 |
| 985 | `SoulsTidy/script_task.py` | `ScriptTask.donate_and_collect_reward#4` | click | `self.C_ST_SOUL_OFFERING_REWARD` | IMMEDIATE | Y | wait_until | KEEP_SPECIAL | rule/R4 |
| 986 | `SoulsTidy/script_task.py` | `ScriptTask.donate_and_collect_reward#5` | click | `self.C_ST_SOUL_OFFERING_REWARD` | IMMEDIATE | Y | wait_until | KEEP_SPECIAL | rule/R4 |
| 987 | `SoulsTidy/script_task.py` | `ScriptTask.donate_and_collect_reward#6` | appear_then_click | `self.I_ST_DONATE` | IMMEDIATE | Y | wait_until | KEEP_SPECIAL | rule/R4 |

### TalismanPass

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 988 | `TalismanPass/script_task.py` | `ScriptTask.get_all#1` | ui_get_reward | `self.I_TP_GET_ALL` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R7 |
| 989 | `TalismanPass/script_task.py` | `ScriptTask.get_flower#1` | ui_click | `self.I_RED_POINT_LEVEL` | IMMEDIATE | - | Timer | KEEP_IMMEDIATE | rule/R7 |
| 990 | `TalismanPass/script_task.py` | `ScriptTask.get_flower#2` | appear_then_click | `match_level[level]` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 991 | `TalismanPass/script_task.py` | `ScriptTask.get_flower#3` | appear_then_click | `self.I_OVERFLOW_CONFIRME` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 992 | `TalismanPass/script_task.py` | `ScriptTask.get_flower#4` | ui_reward_appear_click | `False` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R7 |
| 993 | `TalismanPass/script_task.py` | `ScriptTask.get_flower#5` | appear_then_click | `self.I_TP_GET_ALL` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 994 | `TalismanPass/script_task.py` | `ScriptTask.in_task#1` | click | `self.I_RED_POINT_TASK` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R6 |
| 995 | `TalismanPass/script_task.py` | `ScriptTask.harvest_soul#1` | ui_click | `self.I_TP_SOUL_1` | IMMEDIATE | Y | Timer | KEEP_SPECIAL | rule/R4 |
| 996 | `TalismanPass/script_task.py` | `ScriptTask.harvest_soul#2` | ui_click | `self.I_TP_SOUL_2` | IMMEDIATE | Y | Timer | KEEP_SPECIAL | rule/R4 |
| 997 | `TalismanPass/script_task.py` | `ScriptTask.harvest_soul#3` | ui_click_until_disappear | `?` | IMMEDIATE | Y | Timer | KEEP_SPECIAL | rule/R4 |

### TrueOrochi

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 998 | `TrueOrochi/script_task.py` | `ScriptTask.run_true_orochi_battle#1` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 999 | `TrueOrochi/script_task.py` | `ScriptTask.run_true_orochi_battle#2` | appear_then_click | `self.I_ST_FIRE` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 1000 | `TrueOrochi/script_task.py` | `ScriptTask.run_true_orochi_battle#3` | appear_then_click | `self.I_FIND_TS` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 1001 | `TrueOrochi/script_task.py` | `ScriptTask.run_true_orochi_battle#4` | appear_then_click | `self.I_FIRE` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 1002 | `TrueOrochi/script_task.py` | `ScriptTask.run_true_orochi_battle#5` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 1003 | `TrueOrochi/script_task.py` | `ScriptTask.run_true_orochi_battle#6` | appear_then_click | `self.I_ST_CREATE_ROOM` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 1004 | `TrueOrochi/script_task.py` | `ScriptTask.run_true_orochi_battle#7` | ui_click | `self.I_ST_FIRE_PREPARE` | IMMEDIATE | - | Timer,sleep | KEEP_IMMEDIATE | rule/R7 |
| 1005 | `TrueOrochi/script_task.py` | `ScriptTask.run_true_orochi_battle#8` | appear_then_click | `self.I_ST_AUTO_FALSE` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 1006 | `TrueOrochi/script_task.py` | `ScriptTask.run_true_orochi_battle#9` | appear_then_click | `self.I_GREED_GHOST` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 1007 | `TrueOrochi/script_task.py` | `ScriptTask.run_true_orochi_battle#10` | appear_then_click | `self.I_ST_FRAME` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |
| 1008 | `TrueOrochi/script_task.py` | `ScriptTask.run_true_orochi_battle#11` | appear_then_click | `self.I_ST_FRAME` | IMMEDIATE | Y | Timer,sleep | KEEP_IMMEDIATE | rule/R8 |

### WantedQuests

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 1009 | `WantedQuests/explore.py` | `WQExplore.explore#1` | appear_then_click | `goto` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 1010 | `WantedQuests/script_task.py` | `ScriptTask.run#1` | ui_get_reward | `self.I_WQ_BOX` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R7 |
| 1011 | `WantedQuests/script_task.py` | `ScriptTask.run#2` | ui_get_reward | `self.I_E_REWARD_BOX_BIG` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R7 |
| 1012 | `WantedQuests/script_task.py` | `ScriptTask.open_wq_info#1` | click | `self.O_WQ_TEXT_ALL` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R6 |
| 1013 | `WantedQuests/script_task.py` | `ScriptTask.pre_work#1` | appear_then_click | `self.I_WQ_SEAL` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 1014 | `WantedQuests/script_task.py` | `ScriptTask.pre_work#2` | appear_then_click | `self.I_WQ_DONE` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 1015 | `WantedQuests/script_task.py` | `ScriptTask.pre_work#3` | appear_then_click | `self.I_TRACE_ENABLE` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 1016 | `WantedQuests/script_task.py` | `ScriptTask.pre_work#4` | click | `self.C_SPECIAL_MAIN` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R6 |
| 1017 | `WantedQuests/script_task.py` | `ScriptTask.pre_work#5` | ui_click_until_disappear | `self.I_UI_BACK_RED` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R7 |
| 1018 | `WantedQuests/script_task.py` | `ScriptTask.pre_work#6` | ui_click_until_disappear | `self.I_UI_BACK_RED` | IMMEDIATE | - | Timer | KEEP_IMMEDIATE | rule/R7 |
| 1019 | `WantedQuests/script_task.py` | `ScriptTask.pre_work_cooperation_only#1` | appear_then_click | `self.I_WQ_SEAL` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 1020 | `WantedQuests/script_task.py` | `ScriptTask.pre_work_cooperation_only#2` | appear_then_click | `self.I_WQ_DONE` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 1021 | `WantedQuests/script_task.py` | `ScriptTask.pre_work_cooperation_only#3` | click | `self.C_SPECIAL_MAIN` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R6 |
| 1022 | `WantedQuests/script_task.py` | `ScriptTask.pre_work_cooperation_only#4` | ui_click_until_disappear | `self.I_UI_BACK_RED` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R7 |
| 1023 | `WantedQuests/script_task.py` | `ScriptTask.pre_work_cooperation_only#5` | ui_click_until_disappear | `self.I_UI_BACK_RED` | IMMEDIATE | - | Timer | KEEP_IMMEDIATE | rule/R7 |
| 1024 | `WantedQuests/script_task.py` | `ScriptTask.trace_one#1` | click | `self.I_WQ_TRACE_ONE_DISABLE` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R6 |
| 1025 | `WantedQuests/script_task.py` | `ScriptTask.trace_one#2` | execute_single_click | `self.device` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R10 |
| 1026 | `WantedQuests/script_task.py` | `ScriptTask.trace_one#3` | ui_click_until_smt_disappear | `self.C_WQ_TRACE_ONE_CLOSE` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R7 |
| 1027 | `WantedQuests/script_task.py` | `ScriptTask.execute_mission#1` | ui_click | `self.I_TRACE_TRUE` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 1028 | `WantedQuests/script_task.py` | `ScriptTask.execute_mission#2` | ui_click | `self.I_TRACE_TRUE` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 1029 | `WantedQuests/script_task.py` | `ScriptTask.execute_mission#3` | ui_click | `self.I_TRACE_TRUE` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 1030 | `WantedQuests/script_task.py` | `ScriptTask.execute_mission#4` | ui_click | `self.I_TRACE_TRUE` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 1031 | `WantedQuests/script_task.py` | `ScriptTask.challenge#1` | ui_click | `goto_btn` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 1032 | `WantedQuests/script_task.py` | `ScriptTask.challenge#2` | ui_click | `self.I_WQC_UNLOCK` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 1033 | `WantedQuests/script_task.py` | `ScriptTask.challenge#3` | ui_click_until_disappear | `self.I_WQC_FIRE` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 1034 | `WantedQuests/script_task.py` | `ScriptTask.secret#1` | ui_click | `goto` | IMMEDIATE | - | - | KEEP_IMMEDIATE | rule/R7 |
| 1035 | `WantedQuests/script_task.py` | `ScriptTask.secret#2` | appear_then_click | `self.I_WQSE_FIRE` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R8 |
| 1036 | `WantedQuests/script_task.py` | `ScriptTask.secret#3` | click | `self.C_SECRET_CHAT` | IMMEDIATE | Y | - | KEEP_IMMEDIATE | rule/R6 |
| 1037 | `WantedQuests/script_task.py` | `ScriptTask.invite_random#1` | ui_click | `add_button` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R7 |
| 1038 | `WantedQuests/script_task.py` | `ScriptTask.invite_random#2` | click | `self.I_WQ_FRIEND_1` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R6 |
| 1039 | `WantedQuests/script_task.py` | `ScriptTask.invite_random#3` | click | `self.I_WQ_FRIEND_2` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R6 |
| 1040 | `WantedQuests/script_task.py` | `ScriptTask.invite_random#4` | click | `self.I_WQ_FRIEND_3` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R6 |
| 1041 | `WantedQuests/script_task.py` | `ScriptTask.invite_random#5` | click | `self.I_WQ_FRIEND_4` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R6 |
| 1042 | `WantedQuests/script_task.py` | `ScriptTask.invite_random#6` | click | `self.I_WQ_FRIEND_5` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R6 |
| 1043 | `WantedQuests/script_task.py` | `ScriptTask.invite_random#7` | ui_click_until_disappear | `self.I_INVITE_ENSURE` | IMMEDIATE | - | sleep | KEEP_IMMEDIATE | rule/R7 |
| 1044 | `WantedQuests/script_task.py` | `ScriptTask.cooperation_invite#1` | ui_click | `btn` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 1045 | `WantedQuests/script_task.py` | `ScriptTask.cooperation_invite#2` | ocr_appear_click | `self.O_WQ_INVITE_COLUMN_1` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 1046 | `WantedQuests/script_task.py` | `ScriptTask.cooperation_invite#3` | ocr_appear_click | `self.O_WQ_INVITE_COLUMN_2` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 1047 | `WantedQuests/script_task.py` | `ScriptTask.cooperation_invite#4` | click | `self.I_WQ_INVITE_DIFF_SVR` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R6 |
| 1048 | `WantedQuests/script_task.py` | `ScriptTask.cooperation_invite#5` | ui_click_until_disappear | `self.I_WQ_INVITE_CANCEL` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | rule/R7 |
| 1049 | `WantedQuests/script_task.py` | `ScriptTask.cooperation_invite#6` | ui_click_until_disappear | `self.I_WQ_INVITE_ENSURE` | IMMEDIATE | - | wait_until | KEEP_IMMEDIATE | rule/R7 |

### WeeklyPurchase

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 1050 | `WeeklyPurchase/mall/consignment.py` | `Consignment.execute_consignment#1` | ui_click | `self.I_CON_ENTER` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 1051 | `WeeklyPurchase/mall/navbar.py` | `MallNavbar._enter_consignment#1` | ui_click | `self.I_MALL_CONSIGNMENT` | IMMEDIATE | - | - | EXCLUDED | rule/R1 |
| 1052 | `WeeklyPurchase/mall/navbar.py` | `MallNavbar._enter_scales#1` | ui_click | `self.I_MALL_SCCALES` | IMMEDIATE | - | - | EXCLUDED | rule/R1 |
| 1053 | `WeeklyPurchase/mall/navbar.py` | `MallNavbar._enter_bondlings#1` | ui_click | `self.I_MALL_BONDLINGS_SURE` | IMMEDIATE | - | - | EXCLUDED | rule/R1 |
| 1054 | `WeeklyPurchase/mall/navbar.py` | `MallNavbar._enter_sundry#1` | ui_click | `self.I_MALL_SUNDRY` | IMMEDIATE | - | - | EXCLUDED | rule/R1 |
| 1055 | `WeeklyPurchase/mall/navbar.py` | `MallNavbar.click_and_check#1` | execute_single_click | `self.device` | IMMEDIATE | Y | Timer | EXCLUDED | rule/R1 |
| 1056 | `WeeklyPurchase/mall/navbar.py` | `MallNavbar.back_mall#1` | ui_click | `self.I_UI_BACK_YELLOW` | IMMEDIATE | - | - | EXCLUDED | rule/R1 |
| 1057 | `WeeklyPurchase/mall/scales.py` | `Scales._scales_buy_confirm#1` | appear_then_click | `start_click` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 1058 | `WeeklyPurchase/mall/scales.py` | `Scales._scales_buy_confirm#2` | appear_then_click | `self.I_BUY_PLUS` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 1059 | `WeeklyPurchase/mall/scales.py` | `Scales._scales_buy_confirm#3` | appear_then_click | `self.I_BUY_PLUS` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 1060 | `WeeklyPurchase/mall/scales.py` | `Scales._scales_buy_confirm#4` | appear_then_click | `self.I_BUY_ADD` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 1061 | `WeeklyPurchase/mall/scales.py` | `Scales._scales_buy_more#1` | click | `self.C_SCA_SOULS_GET` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 1062 | `WeeklyPurchase/mall/scales.py` | `Scales._scales_buy_more#2` | click | `self.C_BUY_MORE` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 1063 | `WeeklyPurchase/mall/scales.py` | `Scales._scales_buy_sea_more#1` | click | `self.C_BUY_MORE` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 1064 | `WeeklyPurchase/mall/scales.py` | `Scales._scales_buy_sea_more#2` | click | `self.C_SCA_SOULS_GET` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 1065 | `WeeklyPurchase/mall/scales.py` | `Scales._scales_buy_sea_more#3` | appear_then_click | `self.I_SCA_SELECT_1` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 1066 | `WeeklyPurchase/mall/scales.py` | `Scales._scales_demon#1` | ui_click | `self.I_SCA_DEMON_SOULS` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 1067 | `WeeklyPurchase/mall/scales.py` | `Scales._scales_demon#2` | ui_click | `target_class` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 1068 | `WeeklyPurchase/mall/scales.py` | `Scales._scales_demon#3` | click | `target_position` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 1069 | `WeeklyPurchase/mall/scales.py` | `Scales._scales_demon#4` | appear_then_click | `self.I_UI_BACK_RED` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 1070 | `WeeklyPurchase/mall/scales.py` | `Scales._scales_demon#5` | click | `self.C_SCA_SOULS_BACK` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 1071 | `WeeklyPurchase/shrine.py` | `Shrine.execute_shrine#1` | appear_then_click | `self.I_S_SUMMON_TO_SHRINE` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 1072 | `WeeklyPurchase/shrine.py` | `Shrine.shrine_black_daruma#1` | ui_click | `self.I_S_BLACK` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 1073 | `WeeklyPurchase/shrine.py` | `Shrine.shrine_black_daruma#2` | ui_click_until_disappear | `self.I_UI_BACK_RED` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 1074 | `WeeklyPurchase/shrine.py` | `Shrine.shrine_black_daruma#3` | ui_click | `self.I_S_BUY_BLACK` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 1075 | `WeeklyPurchase/shrine.py` | `Shrine.shrine_black_daruma#4` | ui_get_reward | `self.I_S_CONFIRM_BLACK` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 1076 | `WeeklyPurchase/shrine.py` | `Shrine.shrine_black_daruma#5` | ui_click_until_disappear | `self.I_UI_BACK_RED` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 1077 | `WeeklyPurchase/shrine.py` | `Shrine.shrine_white_five#1` | ui_click | `self.I_S_WHITE_FIVE` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 1078 | `WeeklyPurchase/shrine.py` | `Shrine.shrine_white_five#2` | ui_click_until_disappear | `self.I_UI_BACK_RED` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 1079 | `WeeklyPurchase/shrine.py` | `Shrine.shrine_white_five#3` | ui_click | `self.I_S_BUY_WHITE_FIVE` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 1080 | `WeeklyPurchase/shrine.py` | `Shrine.shrine_white_five#4` | ui_get_reward | `self.I_S_CONFIRM_WHITE_FIVE` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 1081 | `WeeklyPurchase/shrine.py` | `Shrine.shrine_white_five#5` | ui_click_until_disappear | `self.I_UI_BACK_RED` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 1082 | `WeeklyPurchase/shrine.py` | `Shrine.shrine_white_four#1` | ui_click | `self.I_S_WHITE_FOUR` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 1083 | `WeeklyPurchase/shrine.py` | `Shrine.shrine_white_four#2` | ui_click_until_disappear | `self.I_UI_BACK_RED` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 1084 | `WeeklyPurchase/shrine.py` | `Shrine.shrine_white_four#3` | ui_click | `self.I_S_BUY_WHITE_FOUR` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 1085 | `WeeklyPurchase/shrine.py` | `Shrine.shrine_white_four#4` | ui_get_reward | `self.I_S_CONFIRM_WHITE_FOUR` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 1086 | `WeeklyPurchase/shrine.py` | `Shrine.shrine_white_four#5` | ui_click_until_disappear | `self.I_UI_BACK_RED` | IMMEDIATE | - | sleep | EXCLUDED | rule/R1 |
| 1087 | `WeeklyPurchase/thousand_things.py` | `ThousandThings.execute_tt#1` | appear_then_click | `self.I_TT_ENTER` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 1088 | `WeeklyPurchase/thousand_things.py` | `ThousandThings.execute_tt#2` | appear_then_click | `self.I_UI_BACK_RED` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 1089 | `WeeklyPurchase/thousand_things.py` | `ThousandThings.tt_buy_mystery_amulet#1` | ocr_appear_click | `self.O_TT_BLUE_TICKET` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 1090 | `WeeklyPurchase/thousand_things.py` | `ThousandThings.tt_buy_black_daruma_scrap#1` | ocr_appear_click | `self.O_TT_BLACK` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 1091 | `WeeklyPurchase/thousand_things.py` | `ThousandThings.tt_buy_ap#1` | appear_then_click | `self.I_TT_BUY_UP` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 1092 | `WeeklyPurchase/thousand_things.py` | `ThousandThings.tt_buy_ap#2` | ocr_appear_click | `self.O_TT_AP` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 1093 | `WeeklyPurchase/thousand_things.py` | `ThousandThings.tt_get_reward#1` | appear_then_click | `self.I_UI_BACK_RED` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 1094 | `WeeklyPurchase/thousand_things.py` | `ThousandThings.tt_get_reward#2` | ui_reward_appear_click | `?` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 1095 | `WeeklyPurchase/thousand_things.py` | `ThousandThings.tt_get_reward#3` | ui_reward_appear_click | `?` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 1096 | `WeeklyPurchase/thousand_things.py` | `ThousandThings.tt_get_reward#4` | appear_then_click | `image_button` | IMMEDIATE | Y | sleep | EXCLUDED | rule/R1 |
| 1097 | `WeeklyPurchase/thousand_things.py` | `ThousandThings.tt_earn_money#1` | ui_click | `self.I_TT_BORROW` | IMMEDIATE | - | - | EXCLUDED | rule/R1 |
| 1098 | `WeeklyPurchase/thousand_things.py` | `ThousandThings.tt_earn_money#2` | ui_click | `self.I_TT_CONFIGURE` | IMMEDIATE | - | - | EXCLUDED | rule/R1 |
| 1099 | `WeeklyPurchase/thousand_things.py` | `ThousandThings.tt_earn_money#3` | ui_click | `self.I_TT_SHIKIGAMI` | IMMEDIATE | - | - | EXCLUDED | rule/R1 |
| 1100 | `WeeklyPurchase/thousand_things.py` | `ThousandThings.tt_earn_money#4` | appear_then_click | `self.I_UI_CONFIRM` | IMMEDIATE | Y | - | EXCLUDED | rule/R1 |
| 1101 | `WeeklyPurchase/thousand_things.py` | `ThousandThings.tt_earn_money#5` | appear_then_click | `self.I_TT_SHIKIGAMI_REPLACE` | IMMEDIATE | Y | - | EXCLUDED | rule/R1 |
| 1102 | `WeeklyPurchase/thousand_things.py` | `ThousandThings.tt_earn_money#6` | ui_click | `self.I_TT_CONFIRM` | IMMEDIATE | - | - | EXCLUDED | rule/R1 |
| 1103 | `WeeklyPurchase/thousand_things.py` | `ThousandThings.tt_earn_money#7` | ui_get_reward | `self.I_TT_BORROW_CONFIRM` | IMMEDIATE | - | - | EXCLUDED | rule/R1 |
| 1104 | `WeeklyPurchase/thousand_things.py` | `ThousandThings.tt_earn_money#8` | ui_click | `self.I_UI_BACK_RED` | IMMEDIATE | - | - | EXCLUDED | rule/R1 |

### WeeklyTrifles

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 1105 | `WeeklyTrifles/script_task.py` | `ScriptTask.click_share#1` | appear_then_click | `wechat` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 1106 | `WeeklyTrifles/script_task.py` | `ScriptTask.click_share#2` | ui_reward_appear_click | `?` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R7 |
| 1107 | `WeeklyTrifles/script_task.py` | `ScriptTask.click_share#3` | appear_then_click | `self.I_WT_QR_CODE` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 1108 | `WeeklyTrifles/script_task.py` | `ScriptTask._share_collect#1` | ui_click_until_appear_or_timeout | `self.I_WT_COLLECT_WECHAT` | IMMEDIATE | - | Timer | KEEP_IMMEDIATE | rule/R7 |
| 1109 | `WeeklyTrifles/script_task.py` | `ScriptTask._share_collect#2` | ui_reward_appear_click | `?` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R7 |
| 1110 | `WeeklyTrifles/script_task.py` | `ScriptTask._share_collect#3` | appear_then_click | `self.I_WT_QR_CODE` | IMMEDIATE | Y | Timer | KEEP_IMMEDIATE | rule/R8 |
| 1111 | `WeeklyTrifles/script_task.py` | `ScriptTask._share_area_boss#1` | click | `self.C_WT_AB_CLICK` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R6 |
| 1112 | `WeeklyTrifles/script_task.py` | `ScriptTask._share_area_boss#2` | appear_then_click | `self.I_WT_DAY_BATTLE` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 1113 | `WeeklyTrifles/script_task.py` | `ScriptTask._share_area_boss#3` | appear_then_click | `self.I_WT_SHARE_AB` | IMMEDIATE | Y | sleep | KEEP_IMMEDIATE | rule/R8 |
| 1114 | `WeeklyTrifles/script_task.py` | `ScriptTask._share_secret#1` | appear_then_click | `self.I_WT_ENTER_SE` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R8 |
| 1115 | `WeeklyTrifles/script_task.py` | `ScriptTask._share_secret#2` | appear_then_click | `self.I_WT_SE_SHARE` | IMMEDIATE | Y | wait_until | KEEP_IMMEDIATE | rule/R8 |
| 1116 | `WeeklyTrifles/script_task.py` | `ScriptTask._broken_amulet.exit_amulet#1` | appear_then_click | `self.I_BM_CONFIRM` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R4 |
| 1117 | `WeeklyTrifles/script_task.py` | `ScriptTask._broken_amulet.exit_amulet#2` | click | `random_click(ltrb=(False, False, True, False))` | IMMEDIATE | Y | - | KEEP_SPECIAL | rule/R4 |
| 1118 | `WeeklyTrifles/script_task.py` | `ScriptTask._broken_amulet#1` | appear_then_click | `self.I_BM_ENTER` | IMMEDIATE | Y | Timer,sleep,wait_until | KEEP_IMMEDIATE | rule/R8 |
| 1119 | `WeeklyTrifles/script_task.py` | `ScriptTask._broken_amulet#2` | appear_then_click | `self.I_BM_AGAIN` | IMMEDIATE | Y | Timer,sleep,wait_until | KEEP_IMMEDIATE | rule/R8 |
| 1120 | `WeeklyTrifles/script_task.py` | `ScriptTask._broken_amulet#3` | click | `random_click()` | IMMEDIATE | Y | Timer,sleep,wait_until | KEEP_IMMEDIATE | rule/R6 |
| 1121 | `WeeklyTrifles/script_task.py` | `ScriptTask._broken_amulet#4` | execute_single_click | `self.device` | IMMEDIATE | Y | Timer,sleep,wait_until | KEEP_IMMEDIATE | rule/R10 |
| 1122 | `WeeklyTrifles/script_task.py` | `ScriptTask._broken_amulet#5` | execute_single_click | `self.device` | IMMEDIATE | Y | Timer,sleep,wait_until | KEEP_IMMEDIATE | rule/R10 |

### module

| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |
| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |
| 1123 | `module/click_pipeline.py` | `execute_single_click#1` | raw_device_click | `?` | IMMEDIATE | - | - | PRIMITIVE | rule/R0 |
| 1124 | `module/click_pipeline.py` | `execute_single_click#2` | raw_backend | `?` | IMMEDIATE | - | - | PRIMITIVE | rule/R0 |
| 1125 | `module/device/control.py` | `Control.multi_click#1` | click | `button` | IMMEDIATE | Y | Timer,sleep | PRIMITIVE | rule/R0 |
| 1126 | `module/device/method/minitouch.py` | `<module>#1` | raw_backend | `200` | IMMEDIATE | - | - | PRIMITIVE | rule/R0 |
| 1127 | `module/device/method/windows_impl.py` | `Window.scroll_window_message#1` | raw_backend | `x` | IMMEDIATE | - | sleep | PRIMITIVE | rule/R0 |
