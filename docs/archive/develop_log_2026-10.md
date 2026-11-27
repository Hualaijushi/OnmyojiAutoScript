# 开发日志归档（2026-10）

> 2026-11-27 按 D073 从 [DEVELOP_LOG.md](../DEVELOP_LOG.md) 无损归档，共 97 条原始记录（仅搬运，未删改历史正文）。

---

## 2026-10-06 - SwitchSoul V1：数字模式时序 / 点击节奏（分组补点区间等待、队伍三轮空转改单次事务、确认框 CONFIRM）

### 背景
- 前两轮只读审查（实现审查 + 原始流程特征审查）+ 2026-10-06 oas1 / oas2 真机日志 8 次数字切换已确认：分组 `click → sleep(0.5) → click → sleep(0.5)`（两次点击完成间隔 610–650 ms，几乎无抖动）；队伍 `for range(3)` + `sleep(0.8)`，第 3 轮被 `interval=3` 挡住，**8/8 次都打假的「Click team N failed」**；固定 sleep 3.9 秒占一次切换 6.34–7.15 秒的 55%–61%；同一预设重复切换时队伍箭头仍被点中但不弹确认框（2 个样本）。
- 用户决定第一轮只做**数字模式时序 / 点击节奏**：保留分组两次点击（只改时序）、清理队伍三轮空转、关键点击加 reaction + fresh confirm；不碰滑动调度、不碰 by-name、不加最终成功判定、不改调用方。

### 实现（只改 `tasks/Component/SwitchSoul/switch_soul.py`）
- `switch_soul_one` 后半段拆成 4 个 helper：`_click_group_twice`（两次 `click`，间隔 `GROUP_CLICK_GAP=(0.4,0.8)`、第二击后 `GROUP_SETTLE=(0.3,0.6)`，两段语义不同、范围分开，随机源是公共 `random_delay`）、`_click_target_team`（`TEAM_FIND_TIMEOUT=3.0` 窗口内「截图 → `appear_then_click(target_team, policy=NORMAL)`」，恰好点一次，reaction 期间目标消失不点旧坐标）、`_observe_confirm_dialog`（`TEAM_RESPONSE_TIMEOUT=2.0` 窗口轮询，不出现 = 正常结束，包含已装备同一预设）、`_confirm_team_switch`（首次 `appear_then_click(SURE, interval=3, policy=CONFIRM)`；确认框仍在则沿用原 `click(SURE, 3)` 的 3 秒重试，`I_CHECK_BLOCK` 与末尾 `ui_click_until_disappear` 兜底保留）。
- 假 warning 删除；真正没点出去才打 `Team N not found in group N`。
- **顺手发现并修复**：`self.appear_then_click(self.I_CHECK_BLOCK, 3)` 的 `3` 落在了 `action` 形参上，`I_CHECK_BLOCK` 一出现就 `AttributeError`（自 `e4e6be23` 起保护形同虚设）；改成 `interval=3`，补 AST 守卫。全仓同形态只有这一处。
- 没动：L1 全部、滑顶 swipe / `sleep(0.5)` / OCR 判停、by-name、全部调用方、其它组件、`dev_tools` 生成器。

### 测试与验证
- 新增 `tests/test_switch_soul_numeric_v1.py` 33 项（真实 `SwitchSoul` + 真实 `appear_then_click` / `click`，帧序列 + 虚拟时钟驱动：分组两击与区间 delay、新预设、已装备、队伍 / 确认框在 reaction 期间消失零点击、确认框卡顿 3 秒重试、`I_CHECK_BLOCK`、AST 钉住滑顶 / by-name / 兜底 / 无裸 `device.click` / `policy=` 恰好两处）。**变异验证 22 组全部被抓**；变异脚本每组前后校验源文件 hash、后台运行不设外部强杀，还原后基线 OK、hash 一致。
- 测试第一次跑就暴露了上面的 `I_CHECK_BLOCK` 位置参数缺陷（我写的 `I_CHECK_BLOCK` 用例直接抛 `AttributeError`）。另有一处测试自己的错：直接驱动 `_observe_confirm_dialog` 的帧序列少了「观察帧」前的当前帧，确认框在 fresh 帧上「消失」导致 0 点击，修的是测试帧序列。
- L2 登记册重新生成：1094 → 1096、ALREADY_L2 37 → 39（队伍 NORMAL、确认首击 CONFIRM，规则 R2）、KEEP_IMMEDIATE 628 不变（队伍 -1、分组第二击 +1）、NEEDS_C 仍 7、policy 点位 36 → 38、basis rule 895 → 897；没有改函数名绕规则。同步 `tests/test_l2_c0_registry.py`（总数 / decision / basis / policy 点位）、`tests/test_l1_l2_integration.py`（policy 点位 36 → 38；policy 声明守卫新增 `POST_C1_CONSUMERS` 逐点登记 + `test_post_c1_consumers_match_the_source_exactly`）、`tests/test_l2_interaction_reaction.py`（policy consumer 文件表加 SwitchSoul），并在注释里写明原因。
- 全量 `unittest discover -s tests` **2160 → 2194**（+34）；`compileall -q tasks tests dev_tools` OK；`git diff --check` 只有 `tasks/FrogBoss/assets.py:42` 的生成器行尾空格（已有记录），本轮文件范围内干净；两个 CRLF 工作区测试文件在 `git diff` 里有 CRLF→LF 规范化提示，不是空白错误。
- 过程中把测试注释里的日期误写成 2026-10-07（当天是 2026-10-06），已在收尾前改正。

### 未做 / 待真机
- **全部是 Level A/B（离线帧序列 + 真实 primitive），没有真机通过**：分组补点间隔不再固定、两次落点不同、新预设弹确认框并确认、已装备预设无确认框正常结束、不再出现常驻 `Click team failed`、确认框卡顿重试仍有效，见 ROADMAP「SwitchSoul V1 Level C」。
- 风险（详见 AI_CONTEXT §4.99）：缩短后的 settle 在新旧分组的列表上无法区分「是哪个分组的队伍箭头」；观察窗口 2.0 秒来自 6/6 的日志证据；「已装备不弹确认框」只有 2 个样本；`I_CHECK_BLOCK` 保护修复后首次真实走到该路径需真机观察。
- 本轮没动：数字模式滑顶 interval 与循环冲突（V2）、OCR by-name、`-1,-1` 配置 `exit(1)`、AbyssShadows 异常转换、Dokan OCR 分支、约 24 个重复调用块（见 ROADMAP「SwitchSoul 后续」）。未 commit / push。

## 2026-10-06 - SwitchSoul V2：数字模式「分组列表滑到顶」调度（每滑一次重新观察，数字调用点不再传 interval）

### 背景
- V1 已 Level C 真机通过（用户 2026-10-06 验收数字预设切换）。上一轮只读设计审查把旧调度解释成「基本只盲滑 1 次」，并建议 `MAX_GROUP_TOP_SWIPES=5`。用户记得「原来的预设流程有时会连续上滑好几次」，要求**先核实历史，再决定实现与上限，不要先锁死 5**。

### 历史核实
- **Git**：滑顶自 `5b032282`（2023-08-06）起是 `while 1`：OCR → `swipe(…, 6)` → OCR → 相同则停；6 秒 interval 使它长期只能真滑 1 次。`4d74f701`（2024-07-22，提交信息「修复切换御魂时 只会滑动一次的BUG, 现在可以正确的滑动到最顶部」）改成 `swipe(…, 0.5)` + `sleep(0.5)`，**从此真正能连续多滑**；`e4e6be23`（2025-03-19，提交信息把 interval 写成「持续时间 0.5→1.5」）又让周期 < interval，第二滑被静默吞掉。**原设计就是「滑到稳定为止」**；Git 无法证明 1.5 的作者动机。资产 ROI 自 `b0c9b0df` 起没变。
- **真机 BehaviorTrace**（`log/behavior/*.jsonl`，37 个文件，仅 4 个含 `ss_group_swipe_up`）：数字模式 12 次切换，11 次真滑 1 次（10 次门会拦第二滑，无法区分「在顶」与「被吞」；1 次门可放行仍只滑 1 次 → 确在顶），**1 次真滑 2 次**（oas1 18:25:09）；by-name 1 / 2 / 2 滑；`ss_group_swipe_up` 手指位移 114~176 px、均值 147 px。
- **更正上一轮结论**：「10 次数字切换每次都只有一条 swipe」是错的——**文本日志会合并连续相同的行**，18:25:09 的两条 `[0.27s] SwipeTrajectory 10 pts @ ss_group_swipe_up` 被折叠成一行；我当时还把那次的 3.1 秒间隔解释成「OCR 慢到 2.4 秒」，实际是真的又滑了一次。滑动次数以 BehaviorTrace 为准。

### 实现（只改 `tasks/Component/SwitchSoul/switch_soul.py`）
- `switch_soul_one` 的滑顶段换成 `self._swipe_group_list_to_top()`；新增私有 `_group_list_text()`（新截图 + 原样 `str([ocr_text…])`）与 `_swipe_group_list_to_top()`（观察 → 循环 {上限检查 → `self.swipe(S_SS_GROUP_SWIPE_UP)`（**无 interval**）→ `sleep(random_delay(*GROUP_TOP_SETTLE))` → 新截图 + OCR → 与滑之前相同即停，否则继续}；达到上限 warning + 返回 False，业务照常继续）。新增常量 `GROUP_TOP_SETTLE=(0.4, 0.7)`、`MAX_GROUP_TOP_SWIPES=4`。日志：每轮 DEBUG、终局 INFO「Group list stabilized after N swipe(s), changed=[…]」、上限 WARNING。
- **`MAX_GROUP_TOP_SWIPES=4` 的依据**：分组总数与单次滑动的 UI 滚动量仓库里都得不到，所以**不由列表容量推出**；下限是真机最大需要次数 2、历史上无上限的循环、用户记忆里的「好几次」，4 次手指位移约 590 px ≈ 一屏；上限是 Device「最近 15 条记录里同名 ≥10 次」守卫——连续两次切换（EternitySea 两队 / Orochi 按层）之间只隔 3 次点击，**4 是前后切换都滑满也到不了 10 的最大值（5 会）**，用真实 `Device.click_record_check` 做成测试钉住。
- **没动**：L1 / `RuleSwipe` / `swipe_endpoint` / `TouchSwipeModel` / minitouch / `BaseTask.swipe`；V1 全部；by-name 全部；FrameWait 不引入（顶部不会动，FrameWait 会白等 timeout）；OCR 判停仍是一次相同即停（`QuickLoadout._rewind_list` 要求连续两次且空文本不算稳定，本轮按用户决定不照搬）。

### 测试与验证
- 新增 `tests/test_switch_soul_group_top_v2.py` 30 项（真实 `SwitchSoul` / `BaseTask.swipe` / `RuleSwipe.sample_endpoints` / `TouchSwipeModel`，只替换截图 / OCR / 最底层 `device.swipe_trajectory`，虚拟时钟 + 虚拟 `Timer`）。V1 测试里 4 个因钉着旧滑顶形态或受额外 delay 事件影响而改写断言，V1 行为断言不变。**变异验证 20 组全部被抓**，缓存 endpoints / trajectory 两组另用只跑 V2 模块的聚焦变异确认是被运行期用例抓住（不是靠别处报错）；脚本每组前后校验 hash、后台运行、不设外部强杀，还原后基线 OK。
- L2 登记册重新生成：**调用点数量无变化**（1096 / ALREADY_L2 39 / KEEP_IMMEDIATE 628 / policy 38），唯一变化是 `switch_soul_one#1` 的「已有等待」`sleep` → `-`（函数内的 `sleep(0.5)` 搬进了没有点击点的 helper）。
- `compileall -q tasks tests dev_tools` OK；全量 `unittest discover -s tests` **2194 → 2224**（+30）；`git diff --check` 本轮文件范围内干净。
- 文档：AI_CONTEXT §4.100 + §7 基线 + §8 ③ 改成「多数情况下只执行 1 次真实 swipe，取决于 OCR + 循环耗时是否超过 1.5 秒，行为具有时序偶然性」；V1 状态改为 Level C PASS。

### 未做 / 待真机
- **V2 是 Level A/B，不是真机通过**：列表已在顶 1 次探测、不在顶 2 / 3 次且第二滑不再被吞、独立手势、是否出现 `not stable after 4 swipes`、`changed` 序列抖动、V1 不受影响，见 ROADMAP「SwitchSoul V2 数字模式滑顶调度 Level C 验收」。
- 风险：真实总组数和 UI 滚动量未知，MAX=4 对「列表远离顶部」的覆盖是估算；「假相同」（滑动没生效 / 延迟生效）仍会误判到顶；一次相同即停没有「空文本不算稳定」保护。未 commit / push。

## 2026-10-07 - SixRealms 购买确认 P0：`buy_skill` 买成功才计数（孔雀国六道轰雷「点了没买成却记成已获得」）

### 背景
- 2026-10-06 的只读专项排查（今日 oas1 日志 + BehaviorTrace + 当前源码 + git 历史）确认：oas1 孔雀国第 6 轮（13:09:21 起）13:11:54 商店第 3 行识别到 `PK_PK_STORE_SKILL_THUNDER` 并点击，之后 1.38 秒内购买确认弹窗没有出现（BehaviorTrace 下一个动作是 2.05 秒后的 `PK_PK_STORE_EXIT`）、金币仍 500；旧 `buy_skill` 点击当刻 `buy_cnt += 1`，孔雀国 `buy_num=1`，下一轮 `Buy done` 退出，`run_on_pk_store` 把 `skill_roaring_thunder` 置 1，13:12:09 / 13:12:35 两次进店都 `Skill level is enough, skip shopping`，期间还花了 2 次唤息，13:12:40 用户手动 stop。
- 用户本轮只要求修这一个 P0：`buy_skill` 不能点击即计数；不改路线 / 价格 / 刷新动画 / OCR / 其它 SixRealms 策略。

### 根因与历史
- 不是识别失败，也不是 L1/L2 回归：`buy_cnt += 1` 紧跟点击这一语义自上游 `4ce4de4f`（2026-05-17，AzurTian）起就存在，`76d88056`（2026-08-27，唤息 / 召唤）只让这个状态更「值钱」，`68a89f4d`（2026-09-25，L1/L2）改的是刷新点击（CONFIRM）与购买点击的落点采样（支撑集与旧 `randint` 一致），判定逻辑没动。保留日志（09-30 起）与 BehaviorTrace（09-04 起）里孔雀国商店在 2026-10-06 之前从未被执行，所以无法做 L2 前后对照。
- 同日月之海 oas2 13:07:45 有一次同样的「点击、没弹窗、1.6 秒后循环重试买成」，旧代码把 2 次真实购买记成 `times: 3`（`Skill 101 level: 6`）。公共函数的返回值长期是「点击次数」，月之海 `buy_num=99` 靠金币闸门自愈，孔雀国 `buy_num=1` 一次落空就固化。
- 落空时机：两次落空点击都发生在刷新确认后约 0.36 秒（孔雀国 0.355 秒、月之海 0.364 秒），刷新后成功的样本间隔更长（孔雀国 13:07:22 为 0.47 秒；月之海 13:07:47 的重试为 1.99 秒）。样本很少，「点击落在重新发牌动画期间」是最可能的解释但**未证实**，属 P1，本轮没改。

### 改动（只动 `tasks/SixRealms/common.py`）
- 新增常量 `BUY_CONFIRM_TIMEOUT=2.5` / `BUY_COIN_TIMEOUT=2.0` / `BUY_MAX_FAILED_ATTEMPTS=3`（依据：真机弹窗 0.47~0.86 秒的 10 个样本；失败上限防止「失败不耗配额」后点击持续失效变成无界重试；全部是工程基线，不是真机标定）。
- 新增私有事务 `_confirm_skill_purchase(coin_num_rule, coin_before)`：① 弹窗 `appear_then_click(I_UI_CONFIRM, interval=0.7)` 在窗口内出现并点掉；② 之后窗口内金币 OCR 严格小于 `coin_before`；两者满足返回 True，否则返回 False，两段都有 `Timer` 上限、每轮重新截图、不抛异常。
- `buy_skill`：点击后调用事务，成功才 `buy_cnt += 1` 并清零 `failed_cnt`；失败 `failed_cnt += 1`，达到上限 `warning` + `break`，否则 `continue` 走原循环（1.5 秒节流 / 金币闸门 / 刷新判断不变，下一轮重新识别、新坐标）；返回值语义改为「已验证成功的购买次数」；加 `Try to buy …, coin before: X` 日志（事务内另有 `Purchase confirm appeared` / `Purchase verified, coin X -> Y` / 未验证的 warning）。
- `peacock_kingdom.py` / `moon_sea.py` **零改动**：`skill_roaring_thunder += buy_times` / `cnt_skill101 += buy_times` 结构不变，靠返回值修正。L1 / L2 / `ClickSampler` / `execute_single_click` / assets / json / 路线 / 唤息 / 召唤 / Boss 全部不动。

### 测试与验证
- 新增 `tests/test_six_realms_buy_verify.py` 26 项（真实 `buy_skill` / 事务 / `BaseTask.appear_then_click` / `execute_single_click` / `ClickSampler`，只替换截图 / 识别 / 金币 OCR / `device.click`；时间驱动虚拟商店 + 虚拟 `Timer`）：事故回归（点了没弹窗 → `buy_times == 0`，孔雀国经真实 `run_on_pk_store` 后状态仍 0）、连续失败上限、重试等满确认窗口、正常购买（价格 100 / 200 / 300 / 450 都算，不钉死扣费）、弹窗点掉但金币不变不算、HUD 延迟 1.2 秒仍算 / 慢于窗口有界不算、晚到 1.9 秒的弹窗仍处理、配额（成功 → 失败 → 成功凑满 `buy_num=2`；`buy_num=99` 复现月之海 13:07 只记真实 2 次；成功后失败计数清零）、失败后商品消失走刷新 / 重试新坐标 / 金币闸门不变、孔雀国状态更新（0 次保持 0 且下次仍购物、买成后才 skip、`buy_num` 仍为 1）、月之海按真实次数累计、AST 结构守卫。
- 变异验证 8 组全部被抓（点击即计数 / 不校验金币 / 金币相等也算 / 不要求弹窗 / 去掉失败上限 / 成功后不清零 / 去掉金币等待上限 / 去掉确认窗口等待）；脚本每组前后校验源文件 hash。第一次以 `run_in_background` + 命令内 `&` 启动没有产出结果文件（源文件 hash 未变，原因没查），改前台重跑后正常。
- 改既有测试 2 个：`tests/test_l1_click_pipeline.py::test_case29…`（替身补 `_confirm_skill_purchase`，只验点击区域）、`tests/test_l2_c0_registry.py`（总数 / decision / basis 三处钉住数字）。
- L2 登记册重新生成：新增 1 处调用点 `SixRealmsCommon._confirm_skill_purchase#1`（`appear_then_click(I_UI_CONFIRM)`，R8 `KEEP_IMMEDIATE`），1096 → **1097**、KEEP_IMMEDIATE 628 → **629**、basis rule 897 → **898**、ALREADY_L2 39 / policy 38 不变。
- `compileall -q tasks tests dev_tools` OK；全量 `unittest discover -s tests` **2224 → 2250**（+26）。
- 文档：AI_CONTEXT §4.101 + §2 工作区 + §7 基线 + §8 SixRealms P1/P2；ROADMAP 完成表 + Level C 清单 + SixRealms 后续；DECISIONS D028；TESTING 一条测试经验。

### 未做 / 待真机
- **Level A/B，不是真机通过**。核心验收：正常购买（`Purchase verified` → `times: 1` → `Skill level: 1`）与点击落空（`Purchase confirm not appeared` → 无 `Buy done` → `Skill level` 仍 0 → 后续进店不 skip），清单见 ROADMAP。
- 风险：弹窗晚于 2.5 秒窗口或金币 HUD 滞后超过 2 秒会漏记真实购买（偏保守，下一轮会再点同一商品；孔雀国有战斗 HUD 置位兜底）；点击当时为什么没触发弹窗仍不确认。
- P1/P2 明确未动：刷新确认后首帧过早（HUD 滞后 5/14）、价格 300 与实测 200、金币闸门先于识别、`wait_animate_stable` 的位置与 ROI、`refresh_time` 只取第一位数字、战斗 HUD 置位无日志，见 AI_CONTEXT §8 与 ROADMAP「SixRealms 商店后续」。

## 2026-10-07 - SwitchSoul V2 / SixRealms P0 Level C 状态同步 + 提交前审查与本地提交

- 用户确认 SwitchSoul V2（数字模式滑顶调度）真机运行无问题 → **Level C PASS**（V1 已于 2026-10-06 PASS）；参数仍按 D001 约定视为 PROVISIONAL。
- SixRealms 购买确认 P0：用户真机运行观察正常，本轮收口；没有逐项跑完 ROADMAP 专项清单，不标 VERIFIED；P1/P2 暂缓。
- 提交前审查后把 SwitchSoul V1 + V2、SixRealms P0 按主题拆成两个本地 commit（未 push）；FrogBoss（§4.93 ~ §4.98）仍是 Level C pending 的 WIP，原样留在工作区、未提交。
- 拆分口径：commit 里的交接文档只含对应主题的章节；§4.99 ~ §4.101 正文里的测试总数（2160 / 2194 / 2224 / 2250）与登记册总数（1094 → 1096 → 1097）是开发时工作区（含 FrogBoss WIP）的口径，各 commit 自身的基线写在该 commit 版 AI_CONTEXT §7；`tests/test_l2_c0_registry.py` 的钉住数字与 `docs/L2_CALLSITE_REGISTER.md` 按各 commit 自身的源码重新生成 / 核对。

## 2026-10-10 - 游戏 UI 更新适配：公共确认 / 获得奖励等模板重截审查 + 结界突破退四 `I_EXIT_ENSURE` 修复 + WIP 清理

### 背景
- 游戏更新后标准双按钮弹窗「确定 / 取消」、「获得奖励」标题、组队邀请勾选框、邮件「确认收取」等换了样式。真机当天：SwitchSoul 切预设确认框认不出（AreaBoss 卡住、用户手动停止）、DailyTrifles 商店签到「获得奖励」10 秒超时、结界突破退四卡死（oas2 15:29:59 GameStuck、oas1 `GameTooManyClickError: GB_EXIT`）。
- 用户当天用 annotator 按新版画面重截了公共确认 / 获得奖励等模板。重截「获得奖励」时 `itemName` 被改成 `ui_reward_1`，`I_UI_REWARD` 消失，14:52 两个账号启动时 `AttributeError` 退出；已改回 `ui_reward`。

### 改动
- 公共确认 / 取消 / 获得奖励 / 邀请勾选框 / 邮件确认 / 寄养确认：11 个模块的 PNG + json ROI + 生成器重新生成的 `assets.py`（明细见 AI_CONTEXT §4.102）。ActivityShikigami 只提交 `I_ACTIVITY_AWARD`（json / `assets.py` 只取这一处改动）；用户同时重截的新活动模板未审查，留在工作区、不提交。
- 退四退出确认：`tasks/Component/GeneralBattle/gb/gb_exit_ensure.png` 从事故原帧 `log/error/oas2_1791617399625/2026-10-10_15-29-59-470541.png` 按 (664,406,179,66) 裁出；`gb/image.json` `exit_ensure` 的 roiFront → 664,406,179,66、roiBack → 644,386,219,106；只对 GeneralBattle 重新生成 `assets.py`。`exit_battle()` 没动。
- 没动：L1 / L2 / `click_pipeline` / `interaction_policy` / 任何业务代码。

### 测试与验证
- 新增 `tests/test_ui_assets_2026_10_10.py` 7 项、`tests/test_general_battle_exit_ensure.py` 13 项，夹具 `tests/fixtures/general_battle/` 5 个（事故原帧、另一场景同一弹窗、2026-10-07 无弹窗战斗页、结界突破列表页、旧模板）。
- 审查：11 个模块资产名与 HEAD 一致，`itemName` 都没变，`assets.py` 与生成器输出逐字节一致；真实新版弹窗（两个场景）上 9 个「确定」拷贝 + 2 个「取消」拷贝全部 1.000，无弹窗画面 ≤0.301；`I_EXIT_ENSURE` 旧 -0.066 → 新 1.000。新版「获得奖励」、邀请勾选框、邮件确认、寄养确认没有真实画面，只做契约检查。
- `exit_battle()` 真实事务测试：点击序列恰为 `['GB_EXIT', 'GB_EXIT_ENSURE']`，弹窗已开时不再点 `GB_EXIT`，换回旧模板能复现事故；变异 4 组全部被抓。
- 全量（commit 口径）**2134 → 2154**；L2 登记册不变；`git diff --check` 只剩生成器带出的行尾空格（`AbyssShadows` / `GameUi` 的 `assets.py`）。

### annotator / OAS `Unknown frame id`（只读核查）
- 图像服务全局只有一个；`ImageRuntime._config_frames` 每个 `config_name` 只留一帧，注册新帧会删同配置旧帧。annotator 实时采集用完整 `Device(config=<同名配置>)`，每次截图都按同一 `config_name` 注册，把运行中 OAS 的帧挤掉（oas2 15:30:14.302 → .611 → .636）。同日只开 annotator、或只跑 OAS 的时段都没有出错。
- 2026-10-07 那次是 Chess 同一帧 16 秒后才用、超过 10 秒 TTL，与 annotator 无关。
- 临时规则与隔离方案（提议：annotator 截图不注册帧）记入 AI_CONTEXT §8 / ROADMAP；未实施。

### WIP 清理（用户决定）
- FrogBoss（原 §4.93 ~ §4.98）与 Orochi「发现宝藏」两份未提交 WIP 放弃，从工作区删除；删除前在仓库外 `D:\oas_xy\wip_backup_20261010\` 留了完整备份。Git 历史里已有的 FrogBoss / Orochi 功能不受影响。

### 未做 / 待真机
- Level C PENDING：UI 更新适配与退四退出确认（清单见 ROADMAP）。
- P1：`exit_battle()` 有界化；annotator 帧缓存隔离。P2：2026-10-07 TTL 过期。

## 2026-10-11 - KekkaiUtilize 好友结界寄养：确认后不再点式神，放置结束条件改看空位数

### 背景
- 2026-10-10 16:46:44 oas1 `GameTooManyClickError: shikigami_left_2`（`log/error/oas1_1791622004317/`）。只读审查证实：寄养已成功（截图右上本账号式神剩 05:59:42，11 秒后重跑读到 5:59:21），确认按钮 16:46:26 正常命中；失败在 `set_shikigami` 的结束条件。
- 同一模式 10-06 23:57、10-09 15:04 也出现过（都在 UI 更新之前）。8 天日志：「Right side has two」16/16 成功，「has one」12 次中 3 次失败；三次失败截图 `I_U_ADD_1` 都是 0.865 命中、`I_U_ADD_2` ≈0.01。

### 根因
- 好友结界两个寄养位都空时，`run_utilize` 把右数第一格 `I_U_ADD_1` 当结束图片；游戏先放右数第二格，右数第一格一直空着，`not appear(stop_image)` 永远不成立。确认后循环继续按 1.5 / 4.5 秒节奏点 `shikigami_left_2/6`，第 10 次点击触发 Device 兜底。

### 修改（2 个源码文件，规则见 DECISIONS D023 补记（五））
- `tasks/KekkaiUtilize/script_task.py` `run_utilize`：进场时分别判断两个空位图标，得到空寄养位数并记日志；调用 `set_shikigami(order, slot_images=(I_U_ADD_1, I_U_ADD_2), empty_slots=n)`。
- `tasks/Component/ReplaceShikigami/replace_shikigami.py` `set_shikigami`：新增仅限关键字的 `slot_images` / `empty_slots`。传入时空位数减少就退出；点过确认后不再点式神，确认最多 3 次（`SET_CONFIRM_MAX_CLICKS`），空位不变只观察 3 秒（`SET_CONFIRM_SETTLE`，provisional）。不传时执行路径不变。
- 方案取舍：最先写成 KekkaiUtilize 自己的放置方法，但那会新增 5 个点击调用点，L2 审计清单对齐失败（5 项 L1/L2 测试红），要改清单和多处钉住数字；改为在公共函数上加可选参数、复用原有点击调用点，登记册不变。

### 测试与验证
- 新增 `tests/test_kekkai_utilize_set_shikigami_slots.py` 13 项 + 夹具 `tests/fixtures/kekkai_utilize/friend_realm_after_placement_2026-10-10.png`（事故原帧）。两组变异（去掉确认后保护 / 改回单图结束条件）各被 3 项抓到，文件按 md5 还原。
- 相关测试（KekkaiUtilize 全部、分类切换、Exploration、KekkaiActivation）368 项 OK；L1/L2 170 项 OK；登记册内存重新生成与 `docs/L2_CALLSITE_REGISTER.md` 一致（1099 / policy 38）。
- 全量 **2154 → 2167 OK**；`compileall` 通过；`git diff --check` 干净。未启动 MuMu / 游戏。

### 未做 / 待真机
- Level C PENDING（清单见 ROADMAP）。**改动生效前必须重启 OAS 进程**：任务只重新加载自己的 `script_task.py`，`ReplaceShikigami` 用缓存模块，不重启会 `TypeError`。
- 候补式神分支（`I_U_CIRCLE_ALTERNATE` → `I_U_CONFIRM_ALTERNATE`）原样保留；`I_U_CONFIRM_ALTERNATE` 在新版标准弹窗上固定 ROI 内只有 0.140（全图 0.920@(687,414)），是否需要重截未核实。

## 2026-10-12 - RyouToppa 点击进攻后的过渡状态：有界等待进入战斗，不重点进攻、不判交互异常

### 背景
- 2026-10-11 00:00 ~ 00:30 oas2 寮突破 6 次「区域2进攻按钮有限重试后仍未进入战斗，判定为交互异常」（`log/error/oas2_1791648007506` 等 6 个目录），`run()` 抛 `GamePageUnknownError`，同一任务连续 3 次后「Request human takeover」、oas2 进程退出：00:04:48 一次，00:30:18 第二次后一直停到 13:40。
- 只读调查：与 23:46:19 第一次战斗失败（区域1 Lose）无关——失败后按设计改打邻近区域2，之后连胜 60 场。

### 根因
- 点击进攻后游戏的过渡分两段：列表压暗转圈（离线匹配：`I_FIRE` 0.956、`I_TOPPA_RECORD` 0.993，和正常弹窗分不开），然后全屏加载（`I_FIRE` 0.41 ~ 0.48，也不是战斗页）。
- `attack_area` 点击后调用 `_wait_for_attack_state`，第一帧见 `I_FIRE` 就返回 `'fire'`（点完 0.1 秒记「仍存在」）；第 2 次尝试截到加载画面时已是最后一次，记「状态已变化」后直接结束循环 → `INTERACTION_ERROR`。6 次都在点击后 1.04 ~ 1.37 秒判定，与正常进入战斗的最长 1.33 秒重叠；重启后先看到 `page_reward` / `page_battle`，说明战斗都已开打。

### 修改（只动 `tasks/RyouToppa/script_task.py`）
- 新增 `RYOU_TOPPA_ATTACK_ENTER_TIMEOUT = 6`（provisional）与 `_wait_for_battle_after_fire()`：点击后有界等待，期间不点任何东西，看到战斗页立即返回；到时按最后一帧返回 `'fire'` / `'list'` / `'unknown'`，交给原有重试 / 异常处理。
- `attack_area` 三处改用它：点击进攻之后、尝试开头发现按钮已消失时、最后一次尝试「按钮状态已变化」时。
- 没动：点区域后的 `_wait_for_attack_state`、重试次数、FIRE reaction、失败区域 / 主区域逻辑、调度层退出策略、图片 / json / assets / 阈值；没有新增点击调用点。

### 测试与验证
- 新增 `tests/test_ryoutoppa_attack_transition.py` 12 项 + 夹具 `tests/fixtures/ryou_toppa/`（事故当晚压暗转圈帧、全屏加载帧，走生产 `ImageRuntime`）。
- 变异：三处各自撤回分别被 4 / 1 / 1 项抓到；三处全撤回（原始逻辑）7 项失败，包括事故时序复现；文件按 md5 还原。
- RyouToppa / FIRE 相关与 L1/L2 测试 357 项 OK；登记册内存重新生成与文档一致（1099 / policy 38）；全量 **2167 → 2179 OK**；`compileall` 通过；`git diff --check` 干净。未启动 MuMu / 游戏。

### 未做 / 待真机
- Level C PENDING（清单见 ROADMAP）。本修复只改 RyouToppa 自己的 `script_task.py`、不改跨模块接口，OAS 每次运行任务都会重新加载它，下一次寮突破即生效，不需要重启（2026-10-11 KekkaiUtilize 修复仍需重启）。
- 已知边界：遮罩超过 6 秒时，到时仍按「按钮还在」交回原逻辑，第 2 次尝试会再点一次进攻（有界）。
- 本轮未处理：主区域因失败标识变成 `UNAVAILABLE` 后一直停在区域1（不影响推进）；调度层「失败 3 次退出」。

## 2026-10-12 - Secret 秘闻奖励页结算：推进区域固定用面板下方的 `C_RANDOM_SAVE_BOTTOM`

### 背景
- 2026-10-12 13:06 oas2 秘闻第 2 层战斗结束后，在奖励页同一点 (1016, 619) 点击 9 次，页面不推进；13:06:38 结算安全帽 9/9 后停止点击，13:07:38 `GameStuckError: Wait too long`（`log/error/oas2_1791781659216/`），13:07:43 用户手动停止。
- 只读调查：秘闻没有自己的结算处理，整场战斗（含结算）交给 `run_general_battle(battle_key="secret")`；`I_UI_REWARD`（0.19）、Confirm、frame cache 均未参与。

### 根因
- 秘闻奖励页被 `I_REWARD` 1.000 / `I_REWARD_GOLD` 0.992 识别为 `page_reward`，奖励宝袋标志 `I_GET_BATTLE_REWARD` 0.998 → 通用 `_select_reward_region` 选 `C_RANDOM_DEFAULT`。
- 秘闻页右下多了「本次通关时间 / 分享」面板（事故帧实测 y 546 ~ 618），占默认区约两成；锚点落在面板底边，点击无效；同一结算状态按 D025 复用锚点，9 次都点在同一处。

### 修改（只动 `tasks/Secret/script_task.py`）
- Secret 的 `ScriptTask` 覆盖 `_select_reward_region()`，固定返回 `C_RANDOM_SAVE_BOTTOM` (819, 639, 425, 69)：事故帧上整块在面板下方、深色像素 0%。右侧区会碰到「分享」按钮，不用。
- 没动：GeneralBattle、D025 合同、随机采样、点击上限、设备层、资产 / json / 阈值；其它任务仍用通用方法；没有新增点击调用点。只改任务自己的 `script_task.py`，下一次秘闻即生效。
- 方案取舍：没有给通用 `_select_reward_region` 加 `battle_key` 参数——那要改 GeneralBattle 的 `region_provider` 调用与既有源码断言；秘闻任务里只有 secret 一种战斗，任务内覆盖效果等同、范围更小。

### 测试与验证
- 新增 `tests/test_secret_settlement_region.py` 7 项 + 夹具 `tests/fixtures/secret/secret_reward_page_2026-10-12.png`（事故帧）：面板范围从画面测出；秘闻选区为底部区；生产 `_start_settlement_session` 采样 1000 次全部在底部区、面板下沿以下、落在地面像素上；结果页 → 奖励页时旧默认区锚点被强制重采样；同一帧上通用选区仍是默认区且会落进面板；RealmRaid / Orochi 仍用通用方法。
- 变异：删掉覆盖方法被 4 项抓到，文件按 md5 还原。
- GeneralBattle 结算 / L1 / L2 相关 354 项 OK；登记册内存重新生成与文档一致（1099 / policy 38）；全量 **2179 → 2186 OK**；`compileall` 通过；`git diff --check` 干净。未启动 MuMu / 游戏。

### 未做 / 待真机
- Level C PENDING（清单见 ROADMAP）。
- 范围外：秘闻结果页（若出现）仍按通用默认区点击，是否也有该面板未核实；「同一状态同一锚点多次无响应就换点」属 D025 合同调整，本轮不做。

## 2026-10-12 - SixRealms 孔雀国：唤息确认 / 退出孔雀国确认适配新版公共双按钮弹窗 + 唤息失败循环保护

### 背景
- 2026-10-12 oas1 六道之门：16:38:26 `GameTooManyClickError: MS_M_STORE_ACTIVITY, UI_UI_CANCEL`（`log/error/oas1_1791794306723/`），重跑后 16:39:43 `GameStuckError: Wait too long`（`log/error/oas1_1791794383582/`），第三次运行又进入同样的唤息循环。
- 只读调查：两个弹窗都是新版公共双按钮，公共 `I_UI_CONFIRM` 0.919 / 1.000、`I_UI_CANCEL` 1.000 都正常；失效的是六道自己的两处。

### 根因
- 唤息：`_use_breath` → `_confirm_store_entry` 等 `I_PK_STORE_STILLIN`（旧按钮「进入」，ROI 固定 (670,398)），新版确认键是「确认」(664,406)，旧模板 0.028（全图 0.61）；5 秒超时后 `run_on_pk_store_confirm` 兜底 `goto_page(page_pk_main)`，这条边点 `I_UI_CANCEL`；回主界面唤息条件不变 → 再唤息，6 轮后 TooManyClick。10-06 / 10-07 旧「进入」15 次全部成功。
- 退出：点「退出主界面」后新弹出「是否离开孔雀国？」（`I_PK_EXIT_MAIN` 在框上 0.26），到不了孔雀国页；导航失败分支先跑目标页进入失败 hook `handle_enter_peacock_kingdom`，其 `ui_click(I_SR_SWITCH, I_SR_TO_PEACOCK_KINGDOM)` 无超时，在弹窗上只截图不点击，60 秒后 GameStuck。

### 修改
- `tasks/SixRealms/peacock_kingdom/peacock_kingdom.py`：新增 `_confirm_breath_dialog`（有界；唤息弹窗正文 `I_MS_CHECK_OPEN_STORE` 命中才点 `I_UI_CONFIRM`，看到旧「进入」交回兼容分支）；`_confirm_store_entry` 新版优先、旧版「进入」兜底；新增 `breath_failed`（`before_run` 重置），确认失败后本轮 `_should_use_breath` / `_summon_store` 不再唤息；`run_on_pk_store_confirm` 先有界等 1.5 秒，弹窗已关不算失败、仍在才取消并置位。
- `tasks/SixRealms/peacock_kingdom/page.py`：`page_pk_exit → page_peacock_kingdom` 边新增 `on_leave_failure=[PK_EXIT_DIALOG_CONFIRM]`（`all_of(I_UI_CONFIRM, I_UI_CANCEL, not_(I_MS_CHECK_OPEN_STORE))` 时点「确定」），排在目标页空等 hook 之前；排除唤息弹窗，不会误确认花费相铃。
- `tasks/SixRealms/peacock_kingdom/base_peacock_kingdom.py`：`before_run` 重置 `breath_failed`。
- 没动：GlobalGame Confirm 图片 / ROI / 阈值、GeneralBattle、导航器、其它任务、月之海。
- L2：新增 1 个点击调用点 `_confirm_breath_dialog#1`（rule/R8 KEEP_IMMEDIATE，同 10-07 `_confirm_skill_purchase` 先例）；原 4 个 C0 唤息点位保留。登记册 1099 → 1100、KEEP_IMMEDIATE 632 → 633、rule 900 → 901，`--write` 重新生成并更新 `tests/test_l2_c0_registry.py` 两处钉住值与注释。
- 改动在被 import 的模块里，需重启 OAS 进程才生效。

### 测试与验证
- 新增 `tests/test_six_realms_breath_and_exit_confirm.py` 13 项 + 夹具 `tests/fixtures/six_realms/`（唤息弹窗、离开孔雀国弹窗两张事故帧，生产 `ImageRuntime`）。
- 变异 5 组（改回旧「进入」逻辑 / 去掉 `_should_use_breath` 保护 / 去掉 `_summon_store` 保护 / 去掉退出 hook / 去掉唤息弹窗排除）全部被抓到，文件按 md5 还原。第一次变异脚本经 shell heredoc 传参丢了一个反斜杠，结果作废，改为写入文件后重跑。
- SixRealms / L1 / L2 相关 249 项 OK；全量 **2186 → 2199 OK**；`compileall` 通过；`git diff --check` 干净。未启动 MuMu / 游戏。

### 未做 / 待真机
- Level C PENDING（清单见 ROADMAP）。
- `handle_enter_peacock_kingdom` 的 `ui_click` 仍无超时；月之海唤息流程本轮未核对。
- 同日 16:41 oas2 秘闻结果页卡死（§4.106 的范围外项已复现）需单独开任务。

## 2026-10-12 - SixRealms 孔雀国轰雷购买：按期望扣费 200 核对，金币稳定后才比较

### 背景
- 2026-10-12 oas1 17:46:38：第二次刷新后点击 `PK_PK_STORE_SKILL_THUNDER`，确认弹窗点掉 0.2 秒后 `Purchase verified, coin 600 -> 500`，`Skill level: 1`；0.3 秒后 `Current coin: 200`。实际扣费 ≥300，不是轰雷；之后孔雀国所有商店 `skip shopping`。
- 先做只读审查（用户「先审查，再修改」）：同期 6 次轰雷购买另外 5 次都正好扣 200（10-07 15:31 / 15:35，10-12 16:37 / 17:51 / 17:54）；刷新每次 100；刷新确认后 0.2 秒左右的金币与剩余次数读数会滞后（16:37 第二次刷新后仍是 600 / 「剩2次」）。

### 根因
- D028 的成功判据只要求金币下降，不看降多少；金币 HUD 有递减动画，中间帧 500 就满足了「下降」。

### 修改
- `tasks/SixRealms/common.py`：`buy_skill` / `_confirm_skill_purchase` 新增可选 `expected_cost=None`（不传时与原逻辑一致）。传了时：每轮读金币后 `_wait_coin_stable`（新私有方法，连续两次 OCR 相同、`BUY_COIN_TIMEOUT` 上限、只截图 + OCR）；购买后金币连续两帧相同且低于点击前才比较，等于 `expected_cost` 计数；不等 / 一直不稳定返回 `None`（日志 `Skill purchase cost mismatch: expected=200 actual=…` / `Purchase coin not stable`），`buy_skill` 不计数、重读金币、`<商品名> purchase verification failed, skip current shop.` 后结束本次购买。
- `tasks/SixRealms/peacock_kingdom/peacock_kingdom.py`：新增 `PK_SKILL_THUNDER_COST = 200`，`run_on_pk_store` 传 `expected_cost`；门槛 300、`buy_num=1` 不变。
- 没动：月之海、技能页选择、商店模板 / ROI / OCR、点击坐标、刷新逻辑。L2 无新增调用点。
- 改动在被 import 的模块里，需重启 OAS 进程才生效。
- 日志文本说明：用户要求记录 `Thunder purchase verification failed, skip current shop.`；`common.py` 是孔雀国 / 月之海共用的，所以用商品名开头，孔雀国实际输出 `PK_PK_STORE_SKILL_THUNDER purchase verification failed, skip current shop.`。

### 测试与验证
- 新增 `tests/test_six_realms_thunder_cost_verify.py` 19 项（复用 `test_six_realms_buy_verify` 虚拟商店，加金币递减动画与刷新后 HUD 滞后），覆盖用户给的 5 个场景、同店不再点、下一次进店重买、不稳定、没花钱的失败仍按 D028 重试、刷新后滞后值不当起点、调用方参数、结构守卫。既有 26 项零改动通过。
- 变异 8 组（去掉购买前稳定读数 / 去掉购买后稳定要求 / 去掉扣费比较 / 对不上落回 D028 重试 / 不稳定改为重试 / 对不上返回旧金币 / 孔雀国不传 `expected_cost` / 孔雀国把门槛 300 当扣费传）全部被抓到，文件按 md5 还原。
- SixRealms / L1 / L2 相关 373 项 OK；L2 登记册 1100 不变（内存重新生成与现有文档逐字一致）；全量 **2199 → 2218 OK**；`compileall` 通过；`git diff --check` 干净。未启动 MuMu / 游戏。

### 未做 / 待真机
- Level C PENDING（清单见 ROADMAP）。
- 刷新确认后 HUD 滞后若超过两帧，真实轰雷可能被判 `actual=300` 并跳过本店（只少记，不误记），Level C 重点看。
- 买入门槛 300 未动（AI_CONTEXT §8 ③）。

## 2026-10-13 - UI 更新五项修复：push 与 Level C 日志核对

### 背景
- `bdffc4eb`（§4.104 ~ §4.108）提交后，用户决定不等轰雷扣费的真机验证，先 push；轰雷与离开孔雀国之后单独验证。

### push
- push 前 `git fetch`：`origin/master` 仍为 `67d4d0a3`，快进推送 4 个 commit（`364ea3f9` / `96797089` / `e2d459d8` / `bdffc4eb`），普通 push，非 force。push 范围内的 ActivityShikigami 改动只有 `e2d459d8` 已审查的 `I_ACTIVITY_AWARD`，工作区里未审查的新活动模板没有进入。
- clean `git archive HEAD` 导出跑全量：2218 项 1 个 ERROR，是 KekkaiUtilize 静默窗口的时钟依赖用例（凌晨 01:02 跑）；`origin/master` 同一时刻同样失败，判为既有问题，记入 AI_CONTEXT §8。

### Level C（只读日志核对：没有启动或触发任务、没有改配置；均未标 VERIFIED）
- 先核对每项修复的生效时间：代码最后修改时间早于对应 OAS 进程的启动时间，或任务每次运行都重新加载自己的 `script_task.py`。
- §4.104 KekkaiUtilize、§4.105 RyouToppa、§4.106 Secret 奖励页、§4.107 唤息：主路径 PASS，逐项写在 ROADMAP 各条的「Level C 记录（2026-10-13）」。
- 未覆盖：§4.107 离开孔雀国（没有触发）、§4.108 轰雷扣费（修复后还没跑过孔雀国，oas1 下次 10-19）；§4.108 ⑥ 月之海默认路径 PASS（13:26:41 oas2 `Purchase verified, coin 500 -> 200`，不带 `cost`）。
- 新发现（未调查）：13:13 ~ 13:20 oas2 SixRealms 连续 3 次开局识别为 `page_battle`、导航失败后 `Game page unknown` 并重启，第 4 次正常；已列入 ROADMAP 待只读调查。

## 2026-10-13 - BondlingFairyland 契灵组队：队员按自己的战斗次数收尾

### 背景
- 10-13 oas1 队长 / oas2 队员（`limit_count=100`）：两边同一场打到 `Current count: 100`，队长 12:27:06 退出，队员 12:28:58 才「队员等待超时:120.04, 退出」。

### 根因（只读调查已证实）
- 队长 `run_leader` 打满后拉人进房再退出；队员 `run_member` 的同一检查自上游 `bab92bac`（2025-09-30）起被注释（残留 `breakpush_n`）。
- 上游 `ba0e8d46`（2026-07-17）让 `wait_battle` 把「回到契灵主界面」判为「接受邀请过慢」（返回 `None` 继续等）；队长退房后队员看到的是同一画面，12:27:09 记 `Late invitation`，只能等 2 分钟邀请计时器。改动前同一画面判 `Room destroyed`，队员立即退出。

### 修改（只动 `tasks/BondlingFairyland/script_task.py`）
- `run_member` 主循环在邀请计时器判断之后、接受邀请之前恢复 `current_count >= limit_count` → 「契灵队员次数:N已完成,退出」→ `break`，交给原有收尾；删除注释块与 `breakpush_n`。
- 没动：`wait_battle`（保留 07-17 的接受邀请过慢）、队长流程、GeneralBattle / GeneralInvite、资产、配置；不新增点击调用点。
- handoff：`limit_count //= 2` 之后队员阶段按一半场数结束并转队长，与原设计一致；本轮没有 handoff 真机样本。

### 测试与验证
- 新增 `tests/test_bondling_fairyland_member_limit_count.py` 13 项（驱动真实 `run_member`）。
- 变异 5 组（恢复原注释 / `>` 差一 / 检查后不 `break` / 先接受邀请再检查 / 接受邀请过慢改成退出）全部被抓到，文件按 md5 还原。第一版变异脚本按 CRLF 匹配失败（Git Bash 的 `grep -c $'\r$'` 把 LF 文件误报成 CRLF），断言在写入前拦下，改成 LF 后重跑。
- 契灵 / 组队 / L1 / L2 相关 387 项 OK；L2 登记册 1100 不变（内存重新生成与文档逐字一致）；全量 **2218 → 2231 OK**；`compileall` 通过；`git diff --check` 干净。没有启动 MuMu / 游戏。

### 未做 / 待真机
- Level C PENDING（清单见 ROADMAP）。
- 本次队员 100 场全记为 `Battle result: Lose`（队长 17 胜 83 负），队员侧胜负判定是否有偏差没有调查；不影响计数。

## 2026-10-20 - ActivityShikigami 首领爬塔：复用普通爬塔流程，换用首领页资产；锁定同步与式神录入口有界

### 背景
- 10-20 13:33 / 13:39 oas1 两次跑首领爬塔：都到达了首领页（`I_AS_BOSS_FIRE` 识别成功），随后卡在 `_sync_climb_team_lock('boss')`，没点任何东西，分别在 15 秒 / 24 秒被手动停止，挑战键一直没轮到。

### 只读调查结论
- 卡在 `ui_click(I_LOCK, stop=I_UNLOCK)`（第一次，要解锁）和 `ui_click(I_UNLOCK, stop=I_LOCK)`（第二次，13:36 改成要锁定）；`ui_click` 只认 stop 退出、没有上限。
- 旧 `I_LOCK` / `I_UNLOCK` 与体力那对是同一张图（锁在 801）裁的，错开 1 像素后相似度 1.000；没有同名资产遮蔽（`ScriptTask` 20 层继承里只有 ActivityShikigami 自己定义），图像服务按「路径 + 文件指纹」缓存模板，不存在旧模板问题。首领页的锁实际在 (907,651)。
- 用户随后用 annotator 从首领页截了 `climb_boss_lock.png` / `climb_boss_unlock.png` / `climb_boss_main_to_record.png`（并确认可识别），重新生成了 `assets.py` / `image.json` / `pages.json`。

### 修改
- `activities/normal.py`：`_sync_climb_team_lock` 首领改用 `I_BOSS_LOCK` / `I_BOSS_UNLOCK`；两个分支的 `ui_click` 换成同一循环体的有界版 `ui_click_until_appear_or_timeout`（间隔仍 1.5 秒），`ACTIVITY_TEAM_LOCK_TIMEOUT = 10` 秒没看到目标状态就抛 `GameStuckError`。新增 `_climb_records_entry`（首领 `I_BOSS_MAIN_TO_RECORD`，其余 `I_BATTLE_MAIN_TO_RECORDS`），`_run_climb_action` 改用它。
- `base_act.py`：`switch_soul_for` 进式神录的 `ui_click` 换成有界版，`SWITCH_SOUL_RECORDS_TIMEOUT = 8` 秒，进不去就抛 `GameStuckError`、不切御魂。
- 没动：入口、首领页识别、挑战键、战斗退出条件、五倍卷同步、FIRE、GeneralBattle、结算回收、首领次数 OCR（显示格式没有证据，列入 Level C）、全局 `ui_click`、资产文件。`I_CHECK_BATTLE_BOSS` 没有接入；`climb_item_13.png` 没有引用，未动。
- L2：`tests/test_l2_policy_migration.py` 的 `INVENTORY` 与 `docs/L2_INTERACTION_POLICY_MAP.md` 各 3 行只把调用类型改成 `ui_click_until_appear_or_timeout`；`dev_tools.click_callsite_register --write` 重新生成 `docs/L2_CALLSITE_REGISTER.md`，写入前在内存比对只有这 3 行与按调用类型的两个计数变化，总数 1100 / KEEP_IMMEDIATE 633 / policy 38 不变。

### 测试与验证
- `tests/test_activity_shikigami_climb.py` 新增 23 项：真实 `_sync_climb_team_lock` / `switch_soul_for` / `ui_click_until_appear_or_timeout` / `appear` / `appear_then_click` / L1 管线，只替换截图、`RuleImage.match`、`device.click`；虚拟时钟替换 `module.base.timer.time`（所有真实 `Timer` 一起走虚拟时间，不用逐个替换模块里的 `Timer`）。
- 反向验证在内存里替换方法、不改源码（前后 md5 一致），6 组全部被抓：首领用旧锁资产、无上限 `ui_click`、首领用体力式神录入口、式神录入口无上限、锁定失败静默继续、事故原实现（11 项失败）。
- 爬塔 + L1/L2 守卫 249 项 OK；全量 **2231 → 2254 OK**；`compileall` 通过；`git diff --check` 只报 annotator 生成的 `assets.py` 4 行注释尾随空格（生成器固有格式，本轮未改该文件），其余干净。没有启动 MuMu / 游戏。

### 未做 / 待真机
- Level C PENDING（清单见 ROADMAP「ActivityShikigami 首领爬塔适配 Level C 验收」），重点是首领次数 OCR 的显示格式、首领页五倍卷开关、切御魂后返回、点挑战后的战斗与结算。

## 2026-10-20 - oas1 下午报错分析 + 首领次数按「额外奖励」识别

### 报错一：`RemoteError … KeyError: Unknown frame id`（13:24:57、16:42:02 / 16:42:18 / 16:42:29）
- 图像服务每个配置名只留一帧（新帧注册时删同名旧帧）；annotator 实时画面用 `Device(config=Config('oas1'))` 每 0.5 秒 `screenshot()`，以「oas1」注册，把运行中 oas1 脚本刚截的帧顶掉，脚本下一次匹配报未知帧 → 未处理异常 → `exit(1)`。
- 证据：四次报错都在 annotator `config=oas1` 实时画面期间（13:17:59 ~ 13:24:58、15:43:12 ~ 16:55）；调用栈都在刚截图后（`_burst` 里的 `appear`、导航的 `match_many`）；annotator 只开会话不开实时画面时（13:33 ~ 13:37、16:56）没有出现。
- 未修：涉及 `module/device` / `module/server` 公共层，记入 AI_CONTEXT §8 与 ROADMAP，待用户决定。规避：脚本运行时不对同一实例开实时画面。

### 报错二：`TypeError: expected string or bytes-like object`（16:56:36，首领次数检查）
- 同一次运行里锁定同步已生效（一次 `CLIMB_BOSS_UNLOCK`，0.73 秒后确认）；首领页没有五倍卷开关，警告后继续。
- 原因：`O_REMAIN_BOSS` 自上游 `1874902b` 起是 Digit 模式，`ocr_single` 返回整数 110，`ocr_digit_counter` 对整数做正则；识别框 (1169,668,70,30) 只框到「励 1/10」。错误截图上这行是「额外奖励 1/100」，挑战消耗活动体力 ×12。
- 用户决定额外奖励打满就停（沿用 b − a，业务代码不改），并在 annotator 把 `remain_boss` 改成整行 (1063,669,208,31)、DigitCounter（17:16 重新生成 `ocr.json` / `assets.py`；核对 `assets.py` 相对 HEAD 只多了这一处新变化）。
- 新增 `BossRemainCountTest` 6 项（替换 `rule.__dict__['model']`，真实走模式分发与 `a/b` 解析）；内存反向验证：改回 Digit 5 项失败、改回旧框资产项失败，资产文件 md5 不变。全量 **2254 → 2260 OK**；`compileall` 通过；`git diff --check` 除 annotator 生成的 `assets.py` 注释尾随空格外干净。没有启动 MuMu / 游戏。

## 2026-10-21 - 通用双实例同步核心 P1（`module/instance_sync/`，同心之兰的前置能力）

### 目标
- 用户要做同心之兰双实例互赠（oas1 / oas2），先做与游戏业务解耦、可复用的同步框架。本轮落地 P1：核心模块 + 测试，不接入任何任务，不碰设备 / 游戏 / OCR。

### 设计过程（只读审查，未改代码）
- 用户给出三层方案（通用核心 / 同心之兰适配器 / 八岐门禁）。逐项核对真实源码后，审查结论：核心不变式成立；需修订 7 点（账本写入必须走单一事务、配置不用 YAML、账本放 `log/instance_sync/`、区分「账本缺失」与「今天第一次」、新轮次规则缺失、门禁耗时会占用八岐 `limit_time`、发送点击不能用会重复点击的 `ui_click_until_appear_or_timeout`）。
- 用户随后三次改方向：配对配置放全局配置页（核实结论：「全局配置」页也是每实例各存一份，OAS 没有跨实例共用配置，推荐两边填相同值 + 整组复制）；**同心之兰改为独立任务，不挂在八岐前面**（先后靠调度优先级；删除八岐门禁层，原 9-2 作废）；游戏每天只允许成功互赠一次（选 (a)：确认没发出去的失败当天可重来，结果未知当天不重发）。最后确认：自动新轮次上限 3 轮、结果未知 / 账本损坏按普通失败并排到下一个业务日、账本目录 `log/instance_sync/`。

### 修改
- 新增 `module/instance_sync/`（8 个文件，不改任何既有源码）：`state_machine.py`（账本文档上的纯函数 op）、`invariants.py`（写盘前独立校验）、`ledger.py`（`Ledger.transact`）、`journal.py`、`adapter.py`、`coordinator.py`、`errors.py`、`__init__.py`。
- 新增 `tests/test_instance_sync_state_machine.py`（61）/ `test_instance_sync_ledger.py`（23）/ `test_instance_sync_coordinator.py`（36）/ `test_instance_sync_multiprocess.py`（3，两个真实 spawn 进程）。
- 文档：`DECISIONS.md` 新增 D029；`ARCHITECTURE.md` §5 新增一行；`TESTING.md` §6 新增跨进程测试模式；`ROADMAP.md` 已完成 + P0「同心之兰双实例互赠任务」；`AI_CONTEXT.md` §2 / §4.111 / §7 / §9。

### 技术决策
- 见 `docs/DECISIONS.md` D029：账本是唯一事实源、`transact` 是唯一读写入口；状态机纯函数 + 独立校验器；点击前先写意图、结果未知一律失败且绝不重发；会合 600 秒（创建者落盘）与共享 180 秒预算分离；失败轮次分 safe / unsafe，每天最多 3 轮；损坏 / 丢失不重建；设备异常先写 failed 再原样上抛。
- `max_rounds=3` 取「每天每对账号总共 3 轮（含第一轮）」的口径；用户原话「次数上限3次」可能指第一轮之外再 3 次，已在 D029 / ROADMAP 标为待确认，改适配器常量即可。

### 验证
- `toolkit/python.exe -m unittest discover -s tests` = 2383/2383 OK（`2260 → 2383`，约 137 秒）；双进程用例单独约 5 秒。
- 19 条变异检查（在 scratchpad 复制包后逐条改坏规则）全部被杀，无幸存者。
- 过程中由测试 / 变异检查发现并修复两个缺陷：① 等待以「取消」结束时没通知 `adapter.after_wait`（改成 `try/finally`）；② 变异体让等待循环不终止时测试空转 10 分钟——兜底轮询上限从 100 万降到 2 万，测试虚拟时钟加一天上限哨兵。
- 追加 `DECISIONS.md` 时曾写出混合行尾（该文件是 CRLF，heredoc 追加了 LF），已统一；`AI_CONTEXT` / `DEVELOP_LOG` / `ROADMAP` 的工作区行尾是 LF，`ARCHITECTURE` / `DECISIONS` / `TESTING` 是 CRLF，各自保持。

### Git
- 未提交；HEAD 仍是 `8a82cb8f`。原有未提交内容（ActivityShikigami 首领适配、annotator 重截的模板、`docs/L2_*`）未触碰。

### 后续
- P2（独立任务骨架 + 假适配器）前需用户确认：`failure_interval`（建议 30 分钟）、`unsafe` 的人工解除方式、`max_rounds` 口径。
- P3 起需要真机窗口：同心之兰采样（各自发送还是发起 / 接受、有无明确发送证据、账号身份、每日重置时间、单次尝试耗时）。

## 2026-10-21 - 同步核心 P1 补记：轮次上限口径与 failure_interval

### 目标
- 回应上一条留下的待确认项：用户确认「第一轮之外再重来 3 次」、`failure_interval` 保持默认 1 天由自己配置。

### 修改
- **核心源码零改动**：`max_rounds` 本来就是适配器协议参数（`state_machine.PARAM_KEYS` / `op_enter` 的 `len(rounds) >= max_rounds`），核心里没有写死数字。
- 测试：四个 `tests/test_instance_sync_*.py` 的 `PARAMS['max_rounds']` 3 → 4；两个上限用例改名并改断言——`test_round_cap_is_the_first_round_plus_three_retries`（状态机：连建 4 个 safe 失败轮，第 5 次 `enter` 才得到 `round_cap`）、`test_first_round_plus_three_retries_per_day`（协调器：5 次启动的 `next_action` 依次 `retry_later ×3 / defer_next_day ×2`，账本 `seq == [1,2,3,4]`，第 5 次不进游戏）。用例数不变（123 / 全量 2383）。
- 文档：`DECISIONS.md` D029、`ROADMAP.md`、`AI_CONTEXT.md` §4.111 / §9 里的上限口径与 `failure_interval` 说明；上一条 2026-10-21 日志里的历史行不改。

### 技术决策
- **`failure_interval` 不由任务设置**：保持 `Scheduler` 默认的 1 天，用户自己配置。账本按业务日分文件，所以默认值下 `retry_later` 实际是**次日**重试、落进新账本；同一天内出现第 2 ~ 4 轮，只有用户把 `failure_interval` 调短才会发生。也就是说默认配置下 `max_rounds=4` 基本不起作用，它只是在用户调短间隔后兜住"每天最多白占调度器几次"。
- `max_rounds=4` 由 P2 / P4 的适配器去取；核心不加默认值。

### 验证
- 四个测试文件 123 项通过；全量 2383/2383（见 `docs/AI_CONTEXT.md` §7）。
- 上限相关的 3 条变异（去掉上限 / `>=` 改 `>` 多放一轮 / 最后一轮仍报 `retry_later`）全部被新断言抓到。

### Git
- 未提交；HEAD 仍是 `8a82cb8f`。

### 后续
- 只剩一项待确认：`unsafe` 当天被拦住后的人工解除方式（目前只能清空整个 `log/instance_sync/`）。

## 2026-10-21 - 同步核心 P1 追加：unsafe 的「人工确认并重置」（不是重启）

### 目标
- 回应上一条留下的最后一个待确认项：`unsafe` 当天被拦住后怎么解除。用户问「重启能不能当重置」。

### 过程与结论
- 先核对代码：`ScriptProcess.start()` 每次新建进程、`stop()` 是 `terminate()`，没有看门狗自动拉起；`config/deploy.yaml` 里 `Run: null`，服务重启也不会自启实例。游戏里的 Restart 任务只重启游戏、不换 OAS 进程。
- 结论：重启分不清「我看过游戏、确认可以重来」和「进程崩溃 / 被 stop 后又起来」，而 `unsafe` 恰恰产生在后者，重启即重置会在最需要拦的时候放行并重发。给了四个选项，用户选**任务配置里一个一次性「确认并重置」开关**（人工明确确认才放行；崩溃、重启、开机都不会误触发）。

### 修改
- `module/instance_sync/state_machine.py`：新增 `LATE_ACK`、`is_acknowledged()`、`op_acknowledge_unsafe()`；`op_enter` 的拦截条件改为「unsafe 且未被确认」。记录方式是在最后一轮（必须已 failed）的 `late_events` 追加 `acknowledge_unsafe` 事件——**不改账本 schema，不改轮次状态和 attempts**，旧证据完整保留。
- `module/instance_sync/invariants.py`：新增一条校验，`acknowledge_unsafe` 事件只能出现在 failed 轮次上（`late_events` 本来就强制只追加）。
- `module/instance_sync/coordinator.py`：抽出 `_open_ledger()`（`_run` 行为不变）；新增 `acknowledge_unsafe(reason) -> AckResult`；账本问题转成结果不抛；拦截时的 `detail` 提示怎么确认。`__init__.py` 导出 `AckResult`。
- 测试：状态机 +10（确认后新建轮次且旧轮除 `late_events` 外原样、新的 unsafe 轮需再次确认、open 轮拒绝、过期 open 轮先判 failed 再确认、无需确认的三种情况不改账本、重复确认无效、不绕过上限、非成员拒绝、校验器两条）；协调器 +7（端到端：unknown → 拦截 → 确认 → 第 2 轮 COMPLETED；任一方可确认；重复确认；无账本 / 进行中 / 损坏；不绕过上限）。
- 文档：`DECISIONS.md` D029 补记；`ROADMAP.md`（P2 加 `reset_unsafe` 开关与一次性消费、P2 没有待确认项）；`AI_CONTEXT.md` §4.111 / §7 / §9；`ARCHITECTURE.md` §5 行。

### 技术决策
- **一次性语义（P2 实现）**：任务启动时读到开关就调用一次，**不管结果如何都把开关关回去**，否则残留的开关会在之后某次新的 unsafe 出现时绕过人工检查。确认只对当前业务日的账本有效；`failure_interval` 默认 1 天时，次日是新账本，开关会被消费但没有可确认的。
- **不绕过每天上限**（`max_rounds=4`）；新轮若再次 unsafe 需要再确认一次。
- 本次**没有加任何配置字段**（开关属于 P2，现在加就是没人读的死配置）。

### 验证
- `toolkit/python.exe -m unittest discover -s tests` = 2400/2400 OK（`2383 → 2400`）。
- 变异检查：人工确认相关 8 条（确认后不放行 / 允许在 open 轮次确认 / 绕过上限 / 校验器不再限制 failed / 非成员可确认 / 不写 journal / 无账本时报丢失 / 重复确认再追加）全部被杀；另补跑「完全去掉 unsafe 拦截」（原 19 条里文本已变的那条的等价版）被杀。累计 30 条（核心规则 19 + 上限边界 3 + 人工确认 8）无幸存者。
- 过程中确认：`git ls-files --eol` 是判断文档行尾的准绳（`AI_CONTEXT` / `DEVELOP_LOG` / `ROADMAP` 是 LF，`ARCHITECTURE` / `DECISIONS` / `TESTING` 是 CRLF）；`grep -c` 对 CR 的计数在这个终端里不可靠。

### Git
- 未提交；HEAD 仍是 `8a82cb8f`。原有未提交内容（ActivityShikigami 首领适配、annotator 重截的模板、`docs/L2_*`）未触碰。

### 后续
- P2（独立任务骨架 + 假适配器）没有待用户确认的项，可以随时开始；P3 起需要真机窗口。

## 2026-10-21 - 同心之兰任务骨架 P2：XinLan 任务 + `reset_unsafe` 一次性消费

### 目标
- 按 ROADMAP P0 做 P2：把 §4.111 的同步核心接成独立任务（不需要真机），并实现 `acknowledge_unsafe` 对应的「确认并重置」一次性开关。

### 过程与结论
- 只读审查：`ConfigModel` 注册方式（照 `GuguArtStudio`）、`Config.save` / `task_delay`（`server=True` 会按 `server_update` 改写 target）、`ConfigModel.copy_task_group`（整组复制）、`script.py` 每个任务后重载配置。
- 用户定了两件事：任务名 `XinLan`；`reset_unsafe` 放**单独的 `reset` 分组**而不是 ROADMAP 原写的 `sync`——`sync` 要整组复制给另一个实例，开关放进去会被一起带到对端。
- 消费顺序定为先置 False、`save()`、再确认（fail-closed），并放在配置合法性检查之前，所以配置不合法 / 无适配器 / 确认被拒 / 确认抛异常时开关都已关回。

### 修改
- 新增 `tasks/XinLan/`：`config.py`（`SyncConfig` / `ResetConfig` / `XinLan`）、`business.py`（`BUSINESS_ID` / `PROTOCOL_PARAMS` / `DAILY_RESET` / `business_day` / `next_business_day_start`）、`script_task.py`（`ScriptTask(GameUi)`、`check_pair`、`_consume_reset_flag`、`_build_adapter`（恒 `None`）、`_build_coordinator`、`_schedule`）、`__init__.py`。
- 注册：`module/config/config_model.py`（`xin_lan`）、`config_menu.py`（"Daily Task"）、`config_manual.py`（`SCHEDULER_PRIORITY`）、`config/template.json`（手工插入 `xin_lan` 块）、`assets/i18n/zh-CN.json`。
- 新增 `tests/test_xin_lan_task.py`（26 项）。不改 `module/instance_sync/`。
- 文档：`AI_CONTEXT.md` §4.112 / §7 / §9 / 工作区；`ROADMAP.md`（P2 完成、`reset` 分组、P3 加两个占位）；`DECISIONS.md` D029 补记（P2）；`ARCHITECTURE.md` §5 行。

### 技术决策
- 见 `docs/DECISIONS.md` D029 补记（P2）：`reset` 分组与 `sync` 分开；先关先落盘后确认；P4 前没有适配器时不碰账本；`defer_next_day` 用 `server=False` + `target`。
- `template.json` 没用 `dev_tools/template_update.py` 重新生成：它会带出 `anti_ban` / `fatigue` 等模板里本来就落后的无关字段，只手工插入 `xin_lan`。（生成过一次并已从 HEAD 还原，该文件之前没有未提交改动。）
- `en-US.json` 只有 18 行、没有任务名条目，未加。

### 验证
- `toolkit/python.exe -m unittest tests.test_xin_lan_task` = 26/26；`compileall -q tasks/XinLan module/config tests/test_xin_lan_task.py` 通过；`toolkit/python.exe -m unittest discover -s tests` = 2426/2426 OK（`2400 → 2426`）。
- `git diff --check`：本轮改动的文件干净；报出的尾随空格全部在 `tasks/ActivityShikigami/assets.py`（本轮之前就在工作区的未提交改动，与 XinLan 无关，未动）。
- 没有 Level C，没有启动任何设备 / 模拟器 / OCR。

### Git
- 未提交；HEAD 仍是 `8a82cb8f`。

### 后续
- P3 同心之兰 Level C 只读采样（需要真机窗口），同时核实 `DAILY_RESET` 与 `min_attempt_cost` 两个占位；P4 适配器；P5 双开验收。

## 2026-10-21 - annotator 实时采集不再注册截图帧（方案 A）

### 目标
- 修掉 §8 记录的 `Unknown frame id`：annotator 实时画面与同名配置运行中的脚本抢图像服务里唯一的帧槽位。用户在「接下来该开发什么」之后批准了该项。

### 过程与结论
- 候选排序：同心之兰 P3–P5 需要真机；`GeneralBattle.exit_battle()` 有界化的超时 / 重试 / 失败语义要 Level C 才能定、而且是十几个副本共用的成熟循环；annotator 帧隔离能完整在 Level A/B 做完，改动最小，所以选它。
- 先核实：`image_frame_id` 的消费者全在 `tasks/`；`module/server/` 没有基于 frame 的匹配；`Device.__init__` 的 `auto` 截图基准走 `screenshot_methods`，不经 `Screenshot.screenshot`，构造期间不会注册帧；`Device.get_image_batch_cache` / `update_image_batch_cache` 已按 `None` 处理。

### 修改
- `module/device/screenshot.py`：新增 `register_image_frame: bool = True`；为 False 时 `screenshot()` 不调 `register_frame`，`image_frame_id = None`。
- `module/server/tool_capture_worker.py`：`_build_device` 设 `device.register_image_frame = False`。
- 新增 `tests/test_screenshot_frame_registration.py`（4 项）。
- 文档：`AI_CONTEXT.md` §4.113 / §7 / §8 / §9；`ROADMAP.md`（已完成表一行、Level C 条目、P1 条目划掉）；`ARCHITECTURE.md` Device / Screenshot 条目。

### 技术决策
- 采用 ROADMAP 记录的方案 A；不采用换命名空间（B，仍每秒 2 张大图占缓存、挤占全局 66 帧上限）、引用计数（C，要改 RPC 协议）、每配置多帧（D，治标、内存翻倍）。开关是实例级，默认值保持原行为。
- `DECISIONS.md` 不加新 ADR：这是一个默认关闭影响的开关，没有推翻或新增长期设计约束；契约写进 ARCHITECTURE。

### 验证
- `toolkit/python.exe -m unittest tests.test_screenshot_frame_registration` = 4/4；变异（开关判断改恒 True）2 项变红，已还原。
- `compileall -q module/device module/server tests/test_screenshot_frame_registration.py` 通过；`toolkit/python.exe -m unittest discover -s tests` = 2430/2430 OK（`2426 → 2430`）；本轮改动的文件 `git diff --check` 干净。
- 没有 Level C，没有启动任何设备 / 模拟器 / OCR。

### Git
- 未提交；HEAD 仍是 `8a82cb8f`。

### 后续
- Level C：同一配置的脚本运行时打开 annotator 实时画面，确认无 `Unknown frame id`；通过后撤掉 §8 的临时规则。
- 2026-10-07 Chess 的 TTL 型 `Unknown frame id`（ROADMAP P2）与本项无关，仍未处理。

## 2026-10-21 - 同心之兰 P3：资产采集整理与流程设计（不含适配器）

### 目标
- 用户用标注器采完第一批同心之兰界面资产并口述了流程：先看一遍整屏帧，核对 / 整理资产，把流程和适配器设计定下来，列出还要补的帧。用户选定：模板全部放 `tasks/GameUi/page/`；固定角色（`instance_a` 先送、`instance_b` 回赠）；本轮先修资产、定设计，补帧后再写适配器。

### 过程与结论
- 读 24 张整屏帧（`log/annotator/…/uploads/`），确认几处与 P1 / P2 假设不同的事实：每次送出 30 勾玉；流程先后依次进行（A 买并邀请 → B 接受 → B 回赠 → A 接受）；好友详情图标有「初始 → x/10 → x/20」三态，可作明确证据；绑定邀请接受后不跳转、没有提示。
- 邀请弹窗的 ✓ / ✗ 与组队邀请同款，按钮模板可复用 `GeneralInviteAssets.I_I_ACCEPT` / `I_I_REJECT`；接受流程不能复用 `check_then_accept()`（不分邀请类型、等 `is_in_room()` 才返回）。隐患记入 ROADMAP 待验。
- 完成判据（用户确认）：赠送完之后读到分母是 20 就算成功，不要求分子为 0——规则写「每次组队通关副本增加成长值 1 点」，当天打过副本后可能是 `3/20`。

### 修改
- `tasks/GameUi/page/`：`purchase_tongixn` → `purchase_tongxin`、`tonxin_ini` → `tongxin_ini`（采集时的拼写错误，还没有代码引用）；`the_top_friend` 的 roiBack 改成与 roiFront 一致；新增 `friend_same_open` 模板和 `name_tongxin_friend` / `name_tongxin_inviter` 两个 OCR；`tasks/GameUi/assets.py` 用 `AssetsExtractor` 重新生成（diff 只有同心之兰相关常量）。
- 文档：`AI_CONTEXT.md` §4.114 / §2 / §7 / §9；`ROADMAP.md`（已完成表一行、P3 / P4 条目改写）；`DECISIONS.md` D029 补记（P3）。`ARCHITECTURE.md` / `TESTING.md` 不改：没有代码分层或测试规范变化，钩子 `await_turn` 还没实现。

### 技术决策
- 固定角色 + 依次执行；核心只加可选钩子 `await_turn`（默认 True，P4 实现）；扣勾玉的点击只点一次，无明确证据一律 `unknown`。详见 D029 补记（P3）。

### 验证
- 6 个模板对 24 张帧做 cv2 模板匹配自检（`dev_tools/assets_test.load_image` + `RuleImage.test_match`）：命中位置全部符合预期；两个新 OCR 区域只用裁图目测核对，没有跑 OCR。
- `compileall -q tasks/GameUi/assets.py` 通过；`toolkit/python.exe -m unittest discover -s tests` = 2430/2430 OK（本轮没有逻辑改动，数量不变）；`git diff --check` 只报 `assets.py` 生成器注释行尾空格（与既有 `ActivityShikigami/assets.py` 一致）。
- 没有 Level C，没有启动任何设备 / 模拟器 / OCR。

### Git
- 未提交；HEAD 仍是 `8a82cb8f`。

### 后续
- 用户补帧 / 补文字：A 点购买、B 点回赠之后的界面，失败情况，`x/20` 之后第二天的状态，每步耗时，每日重置时间；然后回填 `DAILY_RESET` / `min_attempt_cost`，再出 P4 适配器计划。
- 孤儿文件 `tasks/GameUi/page/page_num_tongxin.png`（「0/20」小图）无规则引用，保留；完成判据读分母、分子会变，它不能当「已完成」模板，可删。

## 2026-10-21 - 同心之兰 P3 补记：A 点购买之后的提示

### 目标
- 用户补充：A 点购买之后页面不变，只有一条小字提示（附截图「邀请已发送。」）；最终核验就是赠送完之后打开好友页读分母。

### 修改
- `tasks/GameUi/page/tongxin_ocr.json` 新增 `toast_tongxin`（roi 550,222,170,34，keyword「邀请已发送」），`tasks/GameUi/assets.py` 重新生成（`O_TOAST_TONGXIN`）。用 OCR 而不是图片模板：提示条底色半透明，随背景变化。坐标取自用户给的 1280×720 截图，只做裁图目测核对，没有跑 OCR。
- 文档：`AI_CONTEXT.md` §4.114、`ROADMAP.md`（P3 条目、已完成表里 OCR 数 3 → 4）、`DECISIONS.md` D029 补记（P3）里 A 的 `judge` 改成轮询这条提示。

### 技术决策
- A 的 `judge` 不再等图标变化（要 B 接受之后才发生，证据依赖对端），改看本机的瞬时提示：看到 done，没看到 unknown。

### 验证
- `compileall -q tasks/GameUi/assets.py`、全量单测见本轮收尾记录；没有 Level C。

### 后续
- 仍待补：B 点回赠之后的界面；福袋页「每天限购 2 次（x/2）」计数点购买后是否变化；失败情况；第二天的状态；耗时与重置时间。

## 2026-10-21 - 同步核心可选钩子 `await_turn`（同心之兰 P4 前置）

### 目标
- 同心之兰是 A 先送、B 后回赠的先后顺序；同步核心里没有「等轮到本端」的位置。先把这个与截图无关的钩子在 Level A/B 做完（用户批准了该计划）。

### 修改
- `module/instance_sync/adapter.py`：`SyncAdapter.await_turn(ctx) -> bool`，非抽象、默认 True；模块「约定」补一条。
- `module/instance_sync/coordinator.py`：`_phase_execute` 在每次 `_begin_attempt` 之前调用；False → `_fail(R_PREPARE_FAILED, 'await_turn')`。
- `tests/test_instance_sync_coordinator.py`：`TurnAdapter` + `AwaitTurnTest` 8 项。
- 文档：`AI_CONTEXT.md` §4.115 / §2 / §7 / §9 / §4.114 措辞；`ROADMAP.md`（已完成表一行、P4 条目）；`DECISIONS.md` D029 补记（P3）两处措辞；`ARCHITECTURE.md` instance_sync 行补钩子。`TESTING.md` 不改（测试模式没有变化，没有写具体用例数）。

### 技术决策
- 账本 / 状态机 / 校验器不改，不新增失败原因：返回 False 复用 `prepare_failed`，是否可安全重来交给现有 `classify_failed_round`（双方都没发过 → safe；对端已有 prepared / unknown / done → unsafe）。
- `TurnAdapter` 单独做成子类，不改 `FakeAdapter.calls`，避免波及既有用例对调用顺序的断言。

### 验证
- `tests.test_instance_sync_coordinator` + `tests.test_instance_sync_multiprocess` = 54/54；`compileall -q module/instance_sync tests/test_instance_sync_coordinator.py` 通过；全量 2438/2438 OK（`2430 → 2438`）。
- 变异检查：删掉调用 → `AwaitTurnTest` 7 项变红；把 False 当放行 → 3 项变红；已还原。
- 没有 Level C。

### Git
- 未提交；HEAD 仍是 `8a82cb8f`。

### 后续
- 用户补帧 / 补文字（B 点回赠之后的界面、失败情况、第二天的状态、耗时、每日重置时间、福袋页 x/2 计数是否变化）后，出 P4 适配器计划。

## 2026-10-21 - 同心之兰 P4 设计修订：A 的证据改用 B 的回赠页面

### 目标
- 用户提议：A 先发，B 接受之后去检查回赠页面。原设计里 A 的 `judge` 只靠一闪而过的小字，漏截一帧整轮就 unsafe、停一天。

### 修改（纯设计，没有改代码）
- `docs/DECISIONS.md` D029 补记（P3）：新增「证据取舍」，改写 A / B 的 `judge` / `verify` / `inspect_attempt`，补「不会互相等」「失败都是保守的」「代价」。
- `docs/AI_CONTEXT.md` §4.114：同步设计，仍缺项里去掉「B 回赠后有没有同样的小字提示」，加上「绑定邀请弹窗会在哪些页面出现」。
- `docs/ROADMAP.md`：P3 仍缺项、P4 条目同步。ARCHITECTURE / TESTING 不改（分层和测试方式没变）。

### 技术决策
- B 只有亲眼看到 `repur_tongxin` 才写 prepared，B 的账本里出现尝试就是 B 替 A 作的确认；核心已有 `RoundView.peer_attempts` 和 `ctx.wait_until`，`await_turn`（§4.115）已够用，不再改核心。
- 有意推翻 P3 时「A 的证据不依赖对端」：勾玉有真实代价，留在界面上的对端证据比一闪而过的本机证据可靠；小字提示降为快速通道。
- 代价：A 的 `verify` 要点 ✓ 接受回赠邀请，不再纯只读（不花勾玉、无页面跳转）。

### 验证
- 纯文档，没有跑单测。核对了 `state_machine.RoundView` 字段与 `coordinator._phase_execute` 的调用位置。没有 Level C。

### 后续
- 仍待用户补：绑定邀请弹窗会出现在哪些页面；B 点回赠之后有没有确认弹窗；失败情况；第二天的状态；耗时；每日重置时间。补齐后再出 P4 适配器计划。

## 2026-10-22 - RealmRaid 退四「再次挑战」点击后加 settle 窗口（oas2 13:40 卡死）

### 目标
- 查 oas2 刚才卡死的原因并修掉触发源。

### 修改
- `tasks/RealmRaid/script_task.py`：新增 `RR_AGAIN_POST_CLICK_SETTLE = 1.5`；`_wait_again_entered_battle()` 新增 `settle` 参数；`_fire_again()` 在点击「再次挑战」和点击确认弹窗之后传 settle，确认弹窗后进入战斗直接 return True。
- `tests/test_realm_raid_state.py`：新增 `FireAgainPostClickSettleTest` 5 项，既有用例未改。
- `docs/AI_CONTEXT.md` §4.116、`docs/ROADMAP.md` 同步。

### 根因（日志 `log/2026-10-22_oas2.txt` 约 2420 行 + `log/error/oas2_1792647717073` 截图 + 源码）
- 13:40:54~56 退四第 2 场失败后，前 3 个 attempt 被「再次挑战 / 不再提示 / 确认弹窗」点击用掉；attempt 4 在过渡帧又点了一次「再次挑战」。
- 点击后 0.17s 第一帧仍是旧失败页 → `_wait_again_entered_battle()` 判 `failure_page` → 最后一次 attempt 耗尽 → `_fire_again()` False（13:40:57.07），而截图显示游戏已进 `page_battle_prepare`。
- `run()` aborted → `finally: ensure_lock(True)` 的 `while 1` 在准备页找不到锁图标，空转 60s（日志无输出）→ 13:41:56 `GameStuckError: Wait too long` → 游戏重启，Restart 13:42:36 恢复。

### 技术决策
- 修判据不放大 timeout：点击后的 settle 窗口内旧页面 marker 仍可见不作结论，只认 `battle`。
- `ensure_lock` 本轮不动（每轮循环顶也在调；有界化会带着错误锁定状态继续打）。aborted 恢复事务记入 ROADMAP。

### 验证
- `tests.test_realm_raid_state` 112 项 OK；`toolkit/python.exe -m unittest discover -s tests` = 2443/2443 OK；`compileall` 通过；本轮改动文件 `git diff --check` 无问题（工作区其它既有文件有尾部空白，非本轮）。
- Level C 待验（见 ROADMAP）。

### 后续
- 真机观察退四日志：`RES_FIRE_AGAIN` 每场只点一次；popup 那轮出现 `entered battle after confirm`；不再出现 `bounded retry` 后接 `Wait too long`。需重启 OAS 进程生效。

## 2026-10-22 - 同心之兰 P4 设计补充：进好友列表先复位到顶部

### 目标
- 用户补充游戏机制：有通知时进入好友页，列表不在最顶端，要先点「最近好友」再点「好友」才回到顶部。同心之兰的入口和 `verify` 都用固定坐标点置顶好友，不复位可能点错行、在错的人身上花勾玉。

### 修改（纯设计，没有改代码）
- `docs/DECISIONS.md` D029 补记（P3）：新增「进好友列表无条件复位」，写明不检测通知、复位后确认再点、确认不到不点购买、名字 OCR 保留。
- `docs/AI_CONTEXT.md` §4.114：游戏流程补第 ④ 条，设计条目补复位约定，仍缺项加两个标签的资产。
- `docs/ROADMAP.md`：P3 仍缺项和 P4 条目同步。ARCHITECTURE / TESTING 不改（分层和测试方式没变）。

### 技术决策
- 无条件复位而不是「检测到通知再复位」：多点两下代价小、结果幂等，也不用去猜通知的样子。
- 查过源码：`tasks/GameUi/page/` 里没有这两个标签的资产；`GeneralInvite` 的 `RECENT_FRIEND` 是组队邀请弹窗的分类，不能复用。

### 验证
- 纯文档，没有跑单测。没有 Level C。

### 后续
- 要用户用标注器采：「最近好友」「好友」标签的点击区域、「好友」选中态的图，最好再有一张有通知时列表不在顶端的帧。其余仍缺项同上一条（弹窗出现的页面、B 回赠后的确认弹窗、失败情况、第二天状态、耗时、每日重置时间）。

## 2026-10-22 - 同心之兰 P4：适配器 `tasks/XinLan/adapter.py` 并接入 `ScriptTask`

### 目标
- 用户补答了写适配器缺的几项（好友页两个标签的资产已采、绑定邀请弹窗任何页面都会弹、B 点回赠之后没有确认弹窗、福袋页点空白处关闭、每日 0 点重置），范围选「写 P4 适配器 + 单测，不碰真机」。

### 修改
- `tasks/GameUi/page/click.json` 新增 `tongxin_icon`；`tongxin_ocr.json` 的 `num_tongxin` 改 `DigitCounter`；删多余的 `page_friend_list.png`；`tasks/GameUi/assets.py` 用 `AssetsExtractor` 重新生成（diff 只有 `C_TONGXIN_ICON` 和 `O_NUM_TONGXIN` 的 mode）。
- 新增 `tasks/XinLan/adapter.py`：`XinLanAdapter` / `SenderAdapter` / `ReceiverAdapter` / `make_adapter`。`tasks/XinLan/script_task.py` 的 `_build_adapter()` 接入，删掉「适配器为 None 就跳过」的分支；`business.py` 只改 `DAILY_RESET` 的注释。
- 新增 `tests/test_xin_lan_adapter.py`（39 项）；`tests/test_xin_lan_task.py` 删 1 项、改 1 项。
- 文档：AI_CONTEXT 新增 §4.117 并更新 §4.114 / §4.115 / 基线 / 同心之兰条目；ROADMAP P4 标完成、列 P5 清单；DECISIONS D029 补记（P4）；ARCHITECTURE 同心之兰调用链；TESTING 加业务适配器的测试模式。

### 技术决策
- 按 D029 补记（P3）的证据设计实现：A 的 `judge` = 小字提示或 B 的尝试出现，B 只有亲眼看到回赠按钮才返回 `await_turn` True；核心不改。
- B 在好友详情等邀请（弹窗任何页面都会弹），接受后再开福袋页看回赠按钮；`await_turn` 里接受邀请的结果不作判据，重试时以回赠按钮在不在为准。
- 每次进好友列表先无条件复位（最近 → 好友），确认标签已选中才点固定坐标，置顶好友名字对不上就不进福袋页、不点购买。
- `_shot` 先清设备卡死计时（适配器的等待循环都有超时）；小字提示只在点完购买后的前 6 秒 OCR。

### 验证
- `tests.test_xin_lan_adapter` + `tests.test_xin_lan_task` 64 项通过；`compileall` 通过；全量 `unittest discover -s tests` = 2481/2481 OK（`2443 → 2481`）；`git diff --check` 无新问题。
- 变异检查 5 条（去掉标签复位 / 不核对邀请人 / 回赠点两次 / 不看回赠按钮 / A 的 `judge` 不看对端尝试），各有对应测试变红，已还原。
- 没有启动模拟器 / 游戏 / 真实 OCR，所以没有 Level C。

### 后续
- P5 双开真机验收（清单见 AI_CONTEXT §4.117 和 ROADMAP）：点空白关福袋页、`I_I_ACCEPT` 点中弹窗 ✓、OCR 实际识别、小字提示能不能截到、每步耗时和占位参数回填、失败情况、第二天的界面。
- 未提交，等用户明确要求再按主题拆分提交。

## 2026-10-22 - 同心之兰 P5 验收前准备：勾玉在接受时才扣

### 目标
- 用户问能不能进入实机验收，并决定自己在实机上跑一次（oas1 先送、oas2 回赠）；同时补充：勾玉在对方接受之后才扣 30。

### 修改（纯文档，没有改代码，没有跑测试）
- `docs/DECISIONS.md` D029：补记（P4）新增「勾玉在接受时才扣」，改正补记（P3）「代价」里「接受邀请不花勾玉」的错误说法。
- `docs/AI_CONTEXT.md` §4.114 / §4.117：游戏流程注明扣在接受时，加 P5 验收前准备。
- `docs/ROADMAP.md`：P5 条目加验收前准备和回传哪些日志。

### 技术决策
- 不改设计：不可撤销的点击是接受邀请，而 B 本来就只在 A 的 prepared 写进账本之后才接受，接受后任何失败都归 unsafe 停一天；名字核对仍是关键一道。
- 这条事实只让「发错人」的代价变小，不放宽自动重试。

### 验证
- 纯文档：检查各文档换行（DECISIONS CRLF，其余 LF）和 `git diff --check`。

### 后续
- 用户实机跑一次，回传日志和账本；据此回填占位参数（`budget` / `min_attempt_cost` / 适配器时间常量）并处理真机上暴露的问题。

## 2026-10-22 - 组队会合：组队任务开始前先等对方实例到场（D030）

### 目标
- 用户实机跑通同心之兰后提出：调度模式下两个实例各跑各的，组队任务可能一边已开始、另一边还在做上一个任务，组队对不上。要把通用实例同步做成配置，让先到的实例等对方做完上一个任务再一起开始。
- 用户选定：不设固定超时（一直等到对方做完上一个任务）；按任务配置里的身份（队长 / 队员）自动判断；配置放「脚本设置」。

### 修改
- 新增 `module/instance_sync/team.py`：在场文件读写、纯函数 `decide()`、`PresenceBoard.step()`（配对锁里读对方 → 判断 → 写自己）、`rendezvous()`。
- 新增 `module/script/team_sync.py`：从任务配置的 `user_status` 判断组队任务、生成 `team_tasks` 快照、心跳线程、`on_schedule()` / `gate()`；出错只记日志并放行。
- 新增 `tasks/Script/config_team_sync.py`（`enable` / `peer_instance`），挂到 `Script.team_sync`；`assets/i18n/zh-CN.json` 追加 4 个键；`config/template.json` 不改（同 `anti_ban`）。
- `script.py`：`team_sync` 用 `cached_property`；`get_next_task()` 每轮写 `idle`；`loop()` 开头起心跳；`prepare_task_execution` READY 之后调 `gate()`，推迟走 `task_delay(..., server=False)`。
- 新增 `tests/test_team_sync.py` 30 项。

### 技术决策
- 不套同心之兰的协调器 / 账本：组队没有「点了收不回」的操作，只要两边同时到场。
- 每个实例只写自己的文件，「读 → 判断 → 写」放在配对锁里，保证一边判开始、另一边下一次也判开始。
- 没有固定超时；能确定对方不会来时才推迟，并推到对方会来的时间，让两边重新对齐。
- `task_delay` 必须 `server=False`，否则服务器刷新时间不是 9 点的任务会被改到明天那个点。

### 验证
- `tests/test_team_sync.py` 全过；变异 4 条各有测试变红（其中两条最初没被抓到，已补强测试）；compileall；全量 `2481 → 2511` OK；`git diff --check`。

### 后续
- 用户在两个实例开启「脚本设置 → 组队同步」（oas1 填 oas2、oas2 填 oas1）后实机看御魂 / 契灵一先一后到时是否互相等到。
- 同心之兰：用户反馈实机跑通一次；日志和账本没回传，`budget` / `min_attempt_cost` / 适配器时间常量仍是占位。

## 2026-10-22 - 组队会合自审修补（D030 补记）

### 目标
- 用户要求自审组队会合有没有风险。

### 发现与修改
- 和同心之兰互相卡住：两边 XinLan 的 `next_run` 差 12 秒（17:15:25 / 17:15:37），组队任务也到点时，一边进 XinLan 等、另一边在御魂门口等，10 分钟后 XinLan 会合超时排到明天。`decide()` 加 `yield_to_paired_task`；`module/script/team_sync.py` 加 `PAIRED_TASKS = {'XinLan'}`，快照里 `role=pair`，不进门口。
- 契灵 `handoff1` / `handoff2` 没被认成组队：`team.py` 加身份互补表 `COMPLEMENT`，`ROLES` 由它导出。
- 对方不会来时一直推迟、没人发现，且每次先唤醒游戏：`TeamSync.precheck()` 在 `prepare_task_execution` 之前只读预检；`TeamSync.notice()` 每天每种原因一条提醒，`Script._postpone_team_task()` 统一推迟 + 推送。
- `assets/i18n/zh-CN.json` 的 `team_sync_enable_help` 补上交替身份、每日提醒、先让同心之兰。
- `tests/test_team_sync.py` 新增 8 项，改 1 个用例的断言。

### 不改（写进 D030 补记）
- 等待中游戏长时间不操作是否断线（真机看）、本端防风控睡眠时间段、OASX 界面不显示等待中的任务、两个实例须同一安装目录。

### 验证
- 变异 4 条各有测试变红并已逐字节还原；compileall；全量 `2511 → 2519` OK；`git diff --check`。

## 2026-10-22 - 每日琐事修复：吉闻奖励关闭点、庭院事务多轮领取、完成记录与循环上限（D031）

### 目标
- 用户要优化每日琐事；选定修吉闻导致的重启、修庭院事务领取（照 synevo）、修其它已知问题；补功能只要定时领体力（等截图）。

### 发现
- 10-16 oas1 11:09 / oas2 11:05 都在吉闻之后 `Game page unknown` 重启：祝福点了，2 秒计时不重置，奖励还没出来就离开，回庭院的点击落在奖励框的道具上，留下「友情点 / 体力」说明框（`log/error/oas1_1792120193075`、`oas2_1792119923651`）。用户确认奖励框改版，要改关闭点击位置。
- 庭院事务一次领不完（逢魔最多 3 次现世首领），原代码只在旧截图上点一次一键完成。
- `guild_donate_dt` 从不写；商店签到提前记完成；多处 `while True` 没有本地上限。

### 修改
- `tasks/DailyTrifles/script_task.py`：吉闻（计时重置、`_close_luck_reward` 点 `C_RANDOM_BOTTOM`、关羁绊弹窗、领到才记）；庭院事务照 synevo（`_current_courtyard_period`、3 轮、关奖励页、失败也记完成）+ 日常标签 10 秒上限；寮祈愿写日期、`switch_select` 有界；签到按钮消失才记；买体力 / 今忆召唤加上限；计时做成类常量。
- 从 synevo 拷 `dt_is_complete.png` / `dt_dailyffair_reward.png` 与 json 两条，`AssetsExtractor` 重新生成 `assets.py`；`config.py` / `config/template.json` 加 `courtyard_morning_dt` / `courtyard_evening_dt`。
- `docs/L2_CALLSITE_REGISTER.md` 重新生成（1100 → 1103），`tests/test_l2_c0_registry.py` 钉住值同步，`tests/test_l1_stage3b_global_guard.py` 替身补常量。
- 新增 `tests/test_daily_trifles.py` 23 项。

### 技术决策
- 不改公共 `C_UI_REWARD`（42 处调用），吉闻局部改点下方空白（用户选定）。
- 「领到才算完成」，庭院事务例外照 synevo 失败也记完成（避免当天反复进入误点）。
- 字段名 / 资产名与 synevo 一致，不带账号轮换部分。

### 验证
- 变异 8 条各有测试变红并已还原；compileall；全量 `2519 → 2542` OK；`git diff --check`。

### 后续
- 用户开启每日琐事实机验（见 ROADMAP Level C）；定时领体力等用户在 12–14 / 20–22 点截图。

## 2026-10-22 - 每日琐事审查后修补（D031 补记）

### 目标
- 用户要求审查刚改完的每日琐事代码，并按审查报告修补。

### 审查结论
- 改动与方案一致（资产只多两项、模板与模型一致、登记册 +3、变异 8 条全杀、全量 2542 通过），没有阻断项。
- 需要处理：今忆召唤超时后仍记当天完成，与 D031「超时不记完成」不符（行为保守，改文档）；庭院事务按钮没出来时 3 轮瞬间用完；吉闻循环里「好友羁绊提升」处理可能误点；寮祈愿短路求值让好友名单被跳过（已有 bug）；D031 调用数多算 1。
- 风险最大的一条要真机：吉闻奖励框能否被 `I_UI_REWARD` 认出。

### 修改
- `tasks/DailyTrifles/script_task.py`：① 寮祈愿 `all_done = all_done and self.donate(...)` 在寮友名单失败后短路，好友名单不执行（改动前就有），改为先执行再合并；② 庭院事务每轮先等最多 3 秒（`COURTYARD_BUTTON_WAIT`），等到「一键完成」或「全部完成」出现再判断，避免刚切到日常标签或现世首领提示还在时 3 轮在一秒内用完——这是对 synevo 写法的一处偏离；③ 吉闻循环里「好友羁绊提升」最多点 3 次（`LUCK_FRIENDSHIP_MAX`）且不重新计时，防止这张小模板在固定位置误匹配时把循环拖到上限、连续点击触发 TooManyClick。
- `tests/test_daily_trifles.py`：新增 4 项（好友名单仍执行、按钮晚出现仍点到、按钮一直不出现每轮等过再记完成、羁绊模板一直在时最多点 3 次），改 1 项名字。

### 验证
- 变异 3 条各有测试变红并已还原；登记册相关测试不受影响（调用点数不变）；compileall；全量 `2542 → 2546` OK；`git diff --check`。

## 2026-10-23 - 每日琐事：定时领庭院体力寿司（D031 补记）

### 目标
- 用户要的「定时领体力」：用户用标注器加了 `courtyard_sushi`，确认寿司 12 点、20 点出现、2 小时后消失，点了弹「获得奖励」。

### 修改
- `tasks/DailyTrifles/script_task.py`：`_current_sushi_period`、`run_courtyard_sushi`（`run()` 最先做，认出才点，寿司消失才记）、`_sushi_retry_at` 与 `plan_next_dt` 的时段内 10 分钟重试（`server=False`）。
- `tasks/DailyTrifles/config.py`：开关 `courtyard_sushi`（默认关）、`DoneRecord` 两个时段字段；`config/template.json`、`assets/i18n/zh-CN.json` 同步；`assets.py` 重新生成（只多 `I_COURTYARD_SUSHI`）。
- `docs/L2_CALLSITE_REGISTER.md` 重新生成（1103 → 1104），`tests/test_l2_c0_registry.py` 钉住值同步；`tests/test_daily_trifles.py` 新增 9 项。
- 顺带修了 `tests/test_kekkai_utilize_convergence.py::test_case10`：它没冻结时钟，0–7 点（测试配置的静默窗口）跑全量会被入口守卫直接 `TaskEnd`；两处 `t.run()` 套上 `_patch_now(NOW)`，断言不变，只改测试。

### 技术决策
- 不复用 `sushi_dt`（商店买体力）；关奖励用公共关闭区域（体力单个道具居中，商店签到已验证）；时段内重试只在没领到时发生，用 `server=False`。

### 验证
- 离线：4 张不在时段内的庭院截图上最高相似度 0.54–0.55（阈值 0.8）。
- 变异 4 条各有测试变红并已还原；compileall；全量 `2546 → 2555` OK；`git diff --check`。

### 后续
- 用户打开开关、重启 OAS 后实机验（ROADMAP Level C）。

## 2026-10-23 - 每日琐事买体力：补回被合并冲掉的修复 + 读错价格不再多买（D031 补记）

### 目标
- 用户记得买体力有 bug，不记得具体现象，要求按查到的问题修；寮祈愿这次不动。

### 发现
- 8 月 13 日 `658f5a7d`（magicemptycity，PR #245）「优化购买寿司逻辑，调整价格检测区域」修过买体力；8 月 18 日的合并 `73bcafcb`「同步 Azur mine 领先提交」保留了第一父提交 `de3f64e0` 的 `tasks/DailyTrifles/script_task.py`，把另一侧 `371b4ec9` 的修复丢了，之后一直没补回（`git log --full-history -m -S` 可查）。
- 现在的问题：买完不处理「获得奖励」（列表被盖住后空转）；价格框 60×30 太小；读到低于 60 当作「还没买」会多买；签到后停在礼包屋子页就去点底栏「杂货」；点商品等购买框是无上限的 `ui_click`。
- 同一次合并还丢了寮祈愿的修复：`73bcafcb` 合并同时丢掉的寮祈愿修复（另一侧 `371b4ec9`，开寮祈愿前要按三方合并补回，不整文件覆盖——那一侧的 `BoxedResult` 导入和 `device.click` 是更旧的写法）：赠予按钮的搜索区限定在对应那一行（`[name_roi[0]-5, name_roi[1]-15, 850, 90]`；现在是至少 1280×720，可能点到别人那一行的赠予、捐错人）；名字输入改用 uiautomator2 `device.u2.send_keys(name, clear=True)`（`59cd6c67` 修中文输入；现在是 `device.adb.send_keys`）；`process_donate` 只点一次赠予、处理确认和奖励弹窗、捐满后重新定位那一行；领奖循环里先 `ui_reward_appear_click()`；寮祈愿页面标志图与 ROI（`99fb0113`）。「两个名单短路」已在 §4.119 审查后修补里改过。

### 修改
- `tasks/DailyTrifles/script_task.py`：① 移植被冲掉的修复：价格框改成右侧 75×45；进 Special 要等到体力商品也出现（列表已加载）；勾玉购买改用 `ui_get_reward(I_STORE_COST_TYPE_JADE, click_interval=2.5)`，买完弹出的「获得奖励」会被关掉（旧写法 `ui_click_until_disappear` 不处理奖励，列表被盖住后循环空转）；资产沿用现在的 `WeeklyPurchaseAssets`，不退回已重构掉的 `RichManAssets`。② 读错价格不再多买：读价格拆成 `_read_sushi_bought`，读不出数字或价格不是 60 + 20k 就返回无效、停止购买、不记完成（以前低于 60 当作「还没买」，80 读成 8 会多买，连续读错会一直买）；本次运行最多买「设定次数 − 开始时已买次数」次，买够就不再点购买；最后一次读数确认达到设定次数才写 `sushi_dt`。③ 进杂货页之前先 `goto_page(page_mall)`：签到会停在礼包屋子页。④ 点商品等购买框改成 `ui_click_until_appear_or_timeout(..., timeout=SUSHI_DIALOG_WAIT=10)`（原来是公共方法里无上限的 `ui_click`）。
- `tests/test_daily_trifles.py`：`FakeUi` 记录去过的页面；新增假商城用例 7 项，改 1 项。
- `docs/L2_CALLSITE_REGISTER.md` 重新生成（调用点数不变，方法名变了）。

### 验证
- 变异 4 条各有测试变红并已还原；compileall；全量 `2555 → 2562` OK；`git diff --check`。

### 后续
- 用户设好次数实机验（ROADMAP Level C）；开寮祈愿之前按三方合并补回丢掉的寮祈愿修复。

## 2026-10-23 - 狩猎战（麒麟 / 阴界之门）：完整打完，修稳健性

### 目标
- 用户要定制阴界之门和麒麟：先全量查代码，再按用户选择「完整打完，修稳健性」修；开放时间用户确认为麒麟周一至周四 06–23、阴界之门周五至周日 18–23。
- 用户同日追加：麒麟分「通用阵容」和「雷麒麟」两套式神录预设，雷麒麟固定在周四。

### 查到的
- 主体 `tasks/Hunt/`（菜单「阴阳寮」）；两个号的 Hunt 都没开过，没有专门测试。EvoZone 的「麒麟」是觉醒副本、逢魔数据里的麒麟、`GuildActivityMonitor`（只监控道馆 / 狭间 / 宴会 / 退治）都与此无关。
- synevo：`tasks/Hunt` 只差阴界开始时间 17→18；`tasks/DailyTrifles/hunt_adapter.py` 是账号轮换专用的短时参战，依赖 synevo 才有的 `module/multi_account/daily_task_schedule.py`。
- 问题：阴界 17 点开始、注释与代码不一致；配置早于开放时提前醒来会空转；进入战斗前两个 `while 1` 与「已挑战」后的返回没有上限；进不去就放弃一整天。

### 修改
- `tasks/Hunt/script_task.py`：① 开放时间（用户 2026-10-23 确认，与 synevo 一致）：麒麟周一至周四 06:00–23:00、阴界之门周五至周日 18:00–23:00（原代码阴界 17:00 开始，注释又写「麒麟 19–21、阴界 19–23」，三者不一致），拆成 `_hunt_mode` / `_window` / `_planned_time`；② 计划时间 = 配置时间，不在开放时间内就用开放时间——以前配置早于开放（比如阴界 17:30）时提前醒来会把下次运行排到「今天已经过去的时间」，调度器立刻又跑，一直空转到开放；③ `kirin()` / `netherworld()` 进入战斗前的点击循环各加 60 秒上限，「已挑战」后的返回改成有界的 `_back()`（10 秒）；两个函数返回 `battle` / `done` / `timeout`；④ 没进去（超时，或阴界 `click_fire` 不是 `battle`）在当天开放时间内 10 分钟后重试，否则排到下一天；打完或已挑战排到下一天（按下一天自己的模式）；⑤ 排程统一 `set_next_run(task="Hunt", target=..., server=False)`（原来 `custom_next_run` 会走服务器刷新时间那个分支，同 D030 的教训）；⑥ 换御魂只在当天模式配了预设时才去式神录；删掉走不到的 `if not check_datetime()` 分支；⑦ 麒麟分两套式神录预设（用户同日追加）：现有「麒麟御魂切换」`kirin_group_team` 作为通用，新增「雷麒麟御魂切换」`thunder_kirin_group_team`（默认 -1,-1，`config/template.json` 同步）；雷麒麟固定在周四（用户确认，`THUNDER_KIRIN_WEEKDAY = 3`），周四填了雷麒麟预设就用它、没填回退到通用，其它麒麟日用通用，阴界之门只看自己的预设（`_soul_preset`）。战斗本身（`run_general_battle`、两套战斗配置、`exit_matcher`、`click_fire == "battle"` 守卫）不动。
- `tasks/Hunt/config.py`：两个运行时间字段加说明键；新增 `thunder_kirin_group_team`（`config/template.json` 同步）；`assets/i18n/zh-CN.json` 追加 `kirin_time_help` / `netherworld_time_help` / `thunder_kirin_group_team` / `thunder_kirin_group_team_help`（原有字段名的中文在主翻译文件 `module/config/i18n/zh-CN.json` 里早就有）。
- `tests/test_hunt.py` 新增 20 项；`tests/test_l2_c0_registry.py` 钉住值 1104 → 1103；`docs/L2_CALLSITE_REGISTER.md` 重新生成。

### 验证
- 变异 5 条各有测试变红并已还原；compileall；全量 `2562 → 2582` OK；`git diff --check`。

### 后续
- 用户打开两个号的 Hunt 后实机验（ROADMAP Level C）。

## 2026-10-23 - 集体任务：只做指定的任务，不限次数刷新直到出现

### 目标
- 用户反馈集体任务以前会捐到不是指定的材料，要求只做指定的；用户确认「固定」指任务类型、刷新免费不限次、换不到过一会儿再试。

### 根因
- `select_and_update_cur_mission()` 只看第一个任务槽（「远远不够」），读任务名、不是目标就点「换一个」，最多换 12–15 次，连续 2–3 次读到同一个任务名就判定换不动；两种情况都返回 False，但 `run()` 不看返回值，而 `current_mission` 已被设成最后读到的那个任务，于是照它去捐——这就是「捐到非指定的材料」。

### 修改
- `tasks/CollectiveMissions/script_task.py`：改成 `_select_target_mission(target) -> bool`：**不设次数上限**，一直点「换一个」直到出现指定任务（用户确认刷新免费不限次），每次照旧 `click_record_clear()`；连续 4 次读到同一个任务名才算换不动（`SWITCH_STUCK = 4`，刷新是随机的，连着两三次相同很正常）；另有 300 秒时间保护（`SELECT_TIMEOUT`，约 200 次，只防目标根本不在池子里时死循环）；只有选中时才设 `current_mission`。`run()` 选不到时**什么都不捐**，回庭院，`set_next_run(target=现在 + 1 小时, server=False)`（用户选「过一会儿再试」）；「今天已捐满」「先领已完成的奖励」与捐材料在 4 种里挑数量最多的规则都不动（用户确认「固定」指任务类型）。`missions_select` 的说明补上这条规则。
- `tests/test_collective_missions.py` 新增 8 项；`docs/L2_CALLSITE_REGISTER.md` 重新生成（调用点数不变）。

### 验证
- 变异 4 条各有测试变红并已还原；compileall；全量 `2582 → 2590` OK；`git diff --check`。

### 后续
- 重启 OAS 后实机验（ROADMAP Level C）。

## 2026-10-23 - 庭院事务满级弹窗点取消；每日琐事 / 狩猎战 / 集体任务所有点击接入 L2

### 目标
- 实测庭院事务卡在满级提取弹窗，用户决定点取消；用户反馈点击太快，要求这几轮改过的任务里任何点击都接入通用延迟点击模型。

### 根因
- 弹窗：点「一键完成」后，结界里放的式神满级时会弹「您在结界中放置的式神已满级，请确认是否提取？（取消 / 确认）」；原流程只认奖励页，6 秒没等到就记完成，回庭院时导航兜底乱点了 26 秒（10-23 09:18 两个号都是）。用户截图上 `I_UI_CANCEL_SAMLL` 0.994、`I_UI_CONFIRM_SAMLL` 0.992，弹窗后面的 `I_ONE_COMPLETE`（0.999）与 `I_CHECK_COURTYARD_AFFAIRS`（0.983）照样认得出来。
- 点击太快：每日琐事在 L2 登记册里整体排除，狩猎战 / 集体任务也全是立即点击；`click` / `ui_click*` / `ui_get_reward` 等公共方法不支持 policy。

### 修改
- `tasks/base_task.py` 的 `click` / `ui_click` / `ui_click_until_disappear` / `ui_click_until_appear_or_timeout` / `ui_reward_appear_click` 加可选 `policy`，`ui_get_reward` 加 `policy`（点目标）与 `close_policy`（关「获得奖励」）；不传时调用形状与原来完全一样（模块级 `_policy_kw` 不往下传 `policy` 这个参数，子类 / 测试替身的旧签名照常可用）。`click(policy)` 点的是固定区域，没有能在新截图里再确认的目标，所以只在点击前加反应时间（`random_delay(*resolve_reaction_range(policy))` → `sleep`）；其余方法透传给 `appear_then_click`，走原有「反应 → 新截图 → 再确认 → 点」。
- 三个任务 59 处点击逐点配档：NORMAL = 功能按钮（祝福、领取、购买商品、挑战、一键完成、换一个、提交、邮件图标）；CONFIRM = 确认 / 取消框（`I_UI_CONFIRM`、召唤确认、搜索确定、勾玉购买、满级弹窗取消）；NAVIGATION = 返回、关闭、关奖励（`I_UI_BACK_*`、羁绊弹窗、吉闻点下方空白、庭院关奖励页、`close_policy`）；FAST = 标签 / 底栏切换、反复点的加号（日常标签、寮友 / 好友、按昵称搜索、杂货、礼包屋推荐、清空搜索、集体任务的加号与 N 卡）。今忆召唤预设点击提成 `_click_recall_preset`，点之前加 NORMAL 反应。
- 庭院事务：新增 `_cancel_two_button_popup()`：同一帧里「取消」「确认」两个小按钮**都在**才点「取消」（CONFIRM 档；用户决定不提取，从不替用户点确认，单独一个取消按钮不算）；每轮点一键完成**之前**先调（弹窗开着时按钮照样认得出来），`close_reward_and_wait_page` 的等待循环里也**先**调，点了取消就重新计时、继续等奖励页。
- `dev_tools/click_callsite_register.py` 去掉 DailyTrifles 排除；登记册重新生成（1103 → 1104，ALREADY_L2 39 → 98）。
- 测试：新增 `tests/test_l2_helper_policy.py` 14 项、`tests/test_daily_trifles.py` 4 项；改 `test_l1_stage3b_global_guard` / `test_l2_c0_registry` / `test_l1_l2_integration` / `test_l2_interaction_reaction` 的钉住值与登记。

### 验证
- 变异 7 条各有测试变红并已还原；compileall；全量 `2590 → 2608` OK；`git diff --check`。

### 后续
- 重启 OAS 后实机验（ROADMAP Level C）：满级弹窗点取消并完成、点击之间有停顿、小时间窗口没有因此超时。

## 2026-10-23 - 组队会合修订：到点就进门等，把对方拉进同一任务

### 目标
- 用户反馈两个实例都空闲时组队任务不会合、各自进入下一次调度；要求到点后进入明确的等待状态，等对方进入同一任务。用户 2026-10-23 决定：被拉的任务按对方原来的调度顺序排（不插队）；对方确定不会来时照旧推迟并提醒；对方在休息时推迟到休息结束；等待不设上限、超过 30 分钟推送一次。

### 根因
- 10-23 09:23–09:30 两个号的 Orochi 每次到点都在拉起游戏之前判 `peer_not_due`（对方这个任务还没到点），把自己推到对方在场文件里的 `next_run`（两边都是 13:39:57）；用户手动把一边改成「现在运行」时，它读到的对方时间仍是 13:39:57，又被推回去，09:30:43 两边几乎同时改也一样（先判的一边读到的是对方还没更新的文件）。根因是 `decide()` 按对方的**计划时间**推迟自己（`peer_not_due` / `peer_idle`）：两边被推到同一个较晚时间后，任何一边提前都会被拉回去，对方也不会因此提前。

### 修改
- ① **到点就进门等**：`decide()` 删掉 `peer_not_due` / `peer_idle` 两条推迟，对方在跑别的任务是 `peer_busy`、空闲是 `pull_peer`，都继续等；② **把对方拉进同一任务**：`TeamSync.peer_request()`（只读）在对方在线、配对正确、状态 `waiting`、它等的任务在我这边是开启的组队任务且身份互补、在我这边还没到点、这次等待的 token 没回应过时返回任务名；`TeamSync.answer()` 再调 `config.task_call(task, force_call=False)` 把它改成现在运行（按原来的调度顺序排，不插队），并记下 token；`Script.get_next_task` 每轮 `get_next()` 之前调 `answer`，`Script.wait_until` 每 5 秒在检查配置之后调 `peer_request`，有请求就返回 False 打断所有空闲等待策略（同一 token 只打断一次）；③ **对方在休息**：`get_next_task` 把 `antiban_wake`（休息时间窗 / 长休息）作为 `rest_until` 写进在场文件（可选字段，旧文件没有当作 None），对方不在门口且 `rest_until` 晚于现在 + 1 分钟时判 `peer_resting`，推迟到那时；④ **两个门口**：不再看对方等的任务在我这边到没到点，一律后到的让（`since` 晚的，同时到按实例名），推迟 3 分钟，回到调度器后被对方拉进它等的任务；⑤ **等太久**：`rendezvous(notify=)` 同一次等待满 30 分钟（`WAIT_NOTIFY`）推送一次，之后照常每 5 分钟记日志、继续等，推送失败不影响等待；⑥ 不变：对方不在线 / 没配对 / 没开 / 身份不互补照旧推迟并每天提醒一次；配置改动中断等待；同心之兰让路；异常放行；推迟一律 `server=False`。
- `tests/test_team_sync.py` 38 → 52（改 3 项既有用例）。

### 验证
- 变异 8 条各有测试变红并已还原；compileall；全量 `2608 → 2622` OK；`git diff --check`。

### 后续
- 重启两个 OAS 后实机验（ROADMAP Level C）。

## 2026-10-23 - 组队会合补强：重启不误推迟 + 御魂次数以队长为准

### 目标
- 用户反馈 §4.125 实测「直接报错」，并说明预想的流程：对方在跑别的任务时进门等、不推迟，对方开始同一任务后两边才一起操作；不光同步时间，还要同步次数（不能一边 100 次、一边 99 次）。用户 2026-10-23 决定：次数以队长为准；先只做御魂；对方文件刚过期就进门等、过期很久才推迟；被拉的任务照旧按原顺序（不插队）。

### 根因
- 「报错」不是代码异常：10:40 两个实例一起重启，oas1 先起来，读到 oas2 旧进程 10:38:09 留下的在场文件（超过 60 秒），判 `peer_offline`，Orochi 推迟 10 分钟并推送「对方不在线」；oas2 晚 2 秒起来后正常进门等（`pull_peer` → `peer_busy`）。
- 次数：御魂每进一次 `run_general_battle` 就 `current_count += 1`，队长和队员各自判 `current_count >= limit_count` 退出；队长点了挑战却没真正开战也会多数一次，两边差一次（队长先走队员空等邀请到超时，或队员先走队长邀请失败）。

### 修改
- `module/instance_sync/team.py`：`OFFLINE_GRACE`（5 分钟），`decide()` 把不在线拆成两档（超过 5 分钟 `peer_offline`；60 秒到 5 分钟 `peer_reconnecting` 进门等，且在「同一门口 → 开始」之前判断）；在场文件加可选字段 `progress`，`PresenceBoard.report_progress()` / `snapshot()`；新增 `TeamSession`（`report` / `peer_progress`）、`Progress`、按实例名的登记表 `set_session` / `get_session` / `clear_session`。
- `module/script/team_sync.py`：`gate()` 开头清旧会话、会合成功（`met` / `peer_started_with_me`）后登记；新增 `end_task()`。
- `script.py`：`self.run()` 外面包 `try/finally` 调 `team_sync.end_task()`。
- `tasks/Orochi/script_task.py`：`run()` 取会话；队长每场后 `_team_report()`、退出主循环后 `_team_report(done=True)` 再退房间；队员 `_member_count_reached()` 取代 `current_count >= limit_count`（有会话时看队长是否打完，对齐次数，读文件节流 2 秒；没有会话时和原来一样）。
- 测试：`tests/test_team_sync.py` 52 → 67（改 1 项），新增 `tests/test_orochi_team_progress.py` 18 项。

### 验证
- 变异 11 条各有测试变红并已还原（其中 `script.py` 不调 `end_task` 最初没被抓到，补了真实 `Script.loop` 里的断言）；compileall；全量 `2622 → 2655` OK；`git diff --check`。

### 后续
- 重启两个 OAS 后实机验（ROADMAP Level C）：同时重启不再推送「不在线」；御魂组队打满两边同时结束、队员日志有 `leader finished Orochi at N`；中途停掉队长，队员约 60 秒内离开。
- 其它组队任务的次数同步在御魂 Level C 通过后逐个接入（ROADMAP）。

## 2026-10-23 - 组队会合启动宽限：刚启动 / 重启时先进门等，不再「先推迟、几秒后又被拉回」（D030 补记三）

### 目标
- 用户在 OASX 里看到 oas1 的八岐大蛇显示「11:35:08」（被推迟了 10 分钟），问日志里为什么还会推送、同一个任务还会同步失败吗；说明预想的是对方还没进同一任务时在门口等，不要推迟组队任务。

### 根因
- 同步本身没有失败，是两次「先推迟、几秒后又被拉回」：① 11:23:54 两边停了 43 分钟后一起启动，oas1 早 0.7 秒，读到 oas2 43 分钟前的旧文件，超过 §4.126 的 5 分钟宽限，判 `peer_offline` 推迟 10 分钟并推送；8 秒后 oas2 进门等，oas1 被拉回、`met`。② 11:25:08 两边又一起重启，oas1 读到 oas2 旧进程还没过期的文件（写着在跑同一任务、搭档是 oas1 旧进程的 token），判 `peer_running_alone` 推迟 10 分钟（没推送），7 秒后又被拉回。
- 手机上 11:26:28 那条推送在 oas1 / oas2 / server / api 日志里都找不到对应的推送调用，最近的是 11:23:54 那条，疑似推送服务延迟（未核实）。

### 修改
- `module/instance_sync/team.py`：`STARTUP_GRACE`（3 分钟）；`decide()` 的 `me` 加可选 `started_at`，对方「不在线」那一档里 `now - started_at < STARTUP_GRACE` 判 `WAIT peer_starting`，否则照旧 `POSTPONE peer_offline`；`peer_running_alone` 由 `POSTPONE`（10 分钟）改为 `WAIT`；`rendezvous(started_at=)` 把它放进 `me`。
- `module/script/team_sync.py`：`TeamSync(started_at=)`，`precheck()` 和 `gate()` 都带进 `decide` / `rendezvous`；默认 None（没有启动宽限）。
- `script.py`：`team_sync` 创建时传 `started_at=datetime.now()`（每个配置一个进程，`loop()` 开头就访问）。
- 测试：`tests/test_team_sync.py` 67 → 76（改 1 项既有断言；`me()` 加 `started_at`；`ScriptLoopTest._script()` 默认把 `team_sync` 设成已运行 10 分钟）。新增含复现 11:23:54、11:25:08 的两个真实 `PresenceBoard` 场景。

### 验证
- 变异 7 条各有测试变红并已还原（「宽限不看 `started_at`」表现为门口死等，90 秒超时终止）；compileall；`tests.test_team_sync` + `tests.test_orochi_team_progress` 94 OK；全量 `2655 → 2664` OK。

### 后续
- 重启两个 OAS 后实机验（ROADMAP Level C）：两边停一阵再一起启动，先起来的一边是 `peer_starting` 进门等，没有推迟和推送；御魂打到一半一起重启也不再 `postpone ... peer_running_alone`；只开一个实例约 3 分钟后推迟并推送一次。

## 2026-10-23 - AI_CONTEXT 归档：已提交的历史条目移到 docs/archive/

### 目标
- 用户要求把 AI_CONTEXT.md 里已完成且不再影响当前开发的历史条目归档到 `docs/archive/`，AI_CONTEXT 只保留当前状态、约束和待办。原文件 4543 行，其中 §4.1 ~ §4.109 就占了约 3800 行。

### 修改
- 新增 `docs/archive/AI_CONTEXT_history.md`（原样搬运，小节编号不变）：§2 提交历史与 §2.1（2026-09-02 工作区清单）、§3.2 的 2026-09-02 专项审查结论、§4.1 ~ §4.109、§7 历史基线与各模块测试覆盖面（含 BehaviorTrace Swipe schema）、§7 里原来的基线增量链、§9 里已完成或已过时的 7 条。§4.93 ~ §4.98（FrogBoss）本来就不存在（WIP 已放弃），编号空缺。
- `docs/AI_CONTEXT.md` 由 4543 行缩到约 520 行：§2 换成当前 Git 摘要（HEAD、与 origin 一致、不属于任何条目的未提交内容）加 §4.110 起的工作区条目；§4 只留 §4.110 ~ §4.127（都未提交）；§7 只留当前基线和最近三步增量；§9 只留未完成的待办和待真机验证项，加一行指向归档里的 swipe schema；§0 加「归档」说明；§10.1 加第 15 条归档规则（提交并推送、没有待真机项后整节原样移走，编号不变，其他文档里的 `AI_CONTEXT §4.N` 引用不用改）。
- 没有改任何代码、测试和其它文档里的引用。

### 验证
- 脚本搬运前断言行号边界；搬运后核对：§4.1 ~ §4.127 的标题在两个文件里合计各出现一次、无重复，缺口只有 §4.93 ~ §4.98；`@@` 占位符无残留；`docs/archive/` 没被 `.gitignore` 忽略。

### 后续
- 以后每次提交并推送一批改动后，按 §10.1 第 15 条把对应章节移进归档。
- 其他文档、代码注释里写的 `AI_CONTEXT §4.N`（N ≤ 109）现在指归档里的同编号小节，没有逐处改写。

## 2026-10-24 - 同心之兰 oas1 卡死：进好友列表的复位被标签模板误识别跳过

### 目标
- 查 oas1 同心之兰卡死的原因，按用户建议改成无条件切换「最近 → 好友」。

### 根因（`log/2026-10-24_oas1.txt` 4617~4651 行 + `log/error/oas1_1792823492258` 截图 + 模板实测）
- 14:31:20 进好友页后没有任何点标签的记录，直接连点 `the_top_friend` 9 次，名字核对一次都没过，满 10 次 `GameTooManyClickError` → 游戏重启，账本第 1 轮整轮失败（oas2 同步失败）。
- 截图里列表没在顶端、右侧详情开着另一个好友（非对端）。`_open_peer_detail` 原先用「看到 `I_FRIEND_CUR_SEL` 就不点『最近』」，而选中 / 未选中模板互相得分 0.94 以上（报错截图实测 `CUR_SEL` 0.945、`LIST_UNSEL` 0.943，阈值 0.8），复位被整个跳过。
- 14:32:16 游戏重启后列表回到顶部，第 2 轮正常；14:32:36 用户手动停了 oas1，oas2 等不到对端，第 2 轮 `prepare_failed`（await_turn 放弃）。

### 修改
- `tasks/XinLan/adapter.py`：`_open_peer_detail` 无条件点「最近」「好友」各一次，不再用标签模板判断；名字 OCR 对不上整套重做，最多新增常量 `OPEN_TRIES=3` 次。
- `tests/test_xin_lan_adapter.py`：`test_already_on_recent_tab_skips_the_first_click` 改成 `test_tabs_are_clicked_unconditionally_whatever_the_templates_say`（模板恒说「已选中」也照点），新增 `test_wrong_top_friend_redoes_the_reset_a_bounded_number_of_times`。
- `docs/DECISIONS.md` D029 补记（P3）「进好友列表无条件复位」修订；`docs/AI_CONTEXT.md` §4.117 同步。

### 技术决策
- 同区好友标题行是开关（展开时点会收起，用户确认）；用户进一步要求「只做同区识别，▶ 才点，否则按原逻辑」：展开步骤改成 `_expand_same_list()`，只认同区 ▶（新资产 `I_FRIEND_SAME_CLOSE`，`tasks/GameUi/page/image_xinlan.json` + `page_friend_same_close.png` + `assets.py` 同步），看到才点、最多 `SAME_TOGGLES=3` 次，看不到就当已展开由名字 OCR 兜底，不再用 30 秒的 `_click_until`；模板取自跨区好友行的 ▶，已用用户补的同区收起真实截图核对：同区标题行上收起模板 0.993、展开模板 0.69；展开画面上收起模板 0.70。测试 +4。
- 不再用标签的选中 / 未选中模板做判断（分不开），以置顶好友名字 OCR 为唯一核对；重做次数 3 次远小于单按钮 10 次点击上限。
- 没有改模板 / 阈值：选中与未选中外观差别小，调阈值要真机帧验证，无条件点击不依赖它。

### 验证
- `tests.test_xin_lan_adapter` + `tests.test_xin_lan_task` 65 项 OK；`toolkit/python.exe -m unittest discover -s tests` 2665 项 OK；`compileall` 通过；本轮改动文件 `git diff --check` 无问题。Level C 待验。

### 后续
- 真机观察：每次进好友页日志里应有 `PAGE_FRIEND_CUR_UNSEL` → `PAGE_FRIEND_LIST_UNSEL` → `friend_same`（若未展开）→ `the_top_friend` 的顺序；不再出现连续多次 `the_top_friend`。需重启 OAS 进程生效。
- 两边 XinLan 的 `next_run` 当前被改成了 2026-10-23（已过期），会立刻重跑；今天账本第 2 轮已 failed(safe)，会开新一轮。

## 2026-10-24 - 御魂 → 个人突破 轻量循环（D032，首版只接御魂）

### 目标
- 用户授权开发并做离线测试：御魂一批 → 个人突破 → 御魂 … 的私用循环，配对复用「组队同步」，不新建同步通道，不启动真机。

### 修改
- 新增 `module/script/loop_controller.py`（循环控制器：加入 / 绑定 / 终态 / 步骤会合 / 可信计数 / 恢复与未恢复任务 / 调度钩子 / 取消命令与停止通知）。
- `module/instance_sync/team.py`：`PresenceBoard` 加 `pid` / `boot_id` / `set_loop`，`_write` 统一带 `loop` / `prev`；`decide` 加循环门口（`peer_in_loop` / `peer_loop_pending`，覆盖提前返回 GO 的路径）；`rendezvous(loop=)`；快照可选 `rank`。
- `module/script/team_sync.py`：`_tasks()`（循环步骤视为启用、带位次）、`gate` / `precheck` 带循环信息、`_peer_waiting` 不拉循环步骤。
- `script.py`：控制器、一次性开关消费、调度钩子挂载、步骤前置（疲劳 → 会合 → 门口）、`_fatigue_prepared_for`、`loop_cancel` 命令、4 个 Restart 分支登记恢复、致命退出前写失败、`_loop_after_run`。
- `module/config/config.py`：`update_scheduler` 末尾可选钩子、`task_delay` 记录 `last_task_delay`；`module/server/script_process.py`：`stop()` 先通知再终止。
- `tasks/Orochi/`：`LoopConfig`、`_leader_fight_once`（可信计数）、队员跟随队长上报、循环里替代次数 / 时长限制、身份校验；`tasks/Component/GeneralInvite/general_invite.py`：`fire_click_issued`；`tasks/RealmRaid/script_task.py`：每个目标前 `loop.check()`。
- 配置 / 文案：`config/template.json`、`module/config/i18n/zh_CN.xml`。
- 测试：新增 `test_loop_controller`（54）、`test_loop_multiprocess`（6，真实 spawn 进程）、`test_loop_script_glue`（33）、`test_orochi_loop`（18）、`test_realm_raid_loop`（4）；改 3 个既有结构守卫测试。

### 技术决策
- 见 `docs/DECISIONS.md` D032。要点：复用 D030、不用 D029 账本；终态保留；界面停止只让脚本进程自己写；高优先级只在步骤边界插入严格更高的；队长可信计数；插入任务结果只认 `task_delay(success=)`。

### 验证
- 全量 `toolkit/python.exe -m unittest discover -s tests` 2784 项 OK；`compileall -q module tasks tests script.py` 通过；新增 / 改动的已跟踪文件 `git diff --check` 无本次引入的问题（全仓 `git diff --check` 另有 `tasks/ActivityShikigami/assets.py` 等此前就有的行尾空白，非本次）。
- 变异 14 条各有测试变红并已还原。
- 全量过程中发现并修复 3 处回归：`Script` 不经 `__init__` 构造时缺 `_fatigue_prepared_for`（现为类级默认值）、2 个结构守卫测试跟随 `_leader_fight_once` 重构；另修一个双进程测试自身的竞态（`collect` 只等指定 worker）。

### 后续
- Level C：见 ROADMAP「御魂 → 个人突破循环 Level C 验收」。
- 未做：探索及其它副本适配；跨重启续跑；FIFO 规则下的位次。

## 2026-10-24 - 御魂 → 个人突破循环：定点修复（外部停止 / 撤回就绪 / 证据顺序 / 恢复调度 / β 裁决）

### 目标
- 用户再次确认个人突破是完整、独立的任务（退四、投降、战败、刷新、换目标都是内部流程，不驱动循环判定），要求对 5 个审查问题先验证反例、成立就修，并补离线回归。保留轻量架构，不新增账本 / 同步器 / 配置事务。

### 审查结论（5 个反例全部成立）
1. 外部停止没有覆盖内层开战点：成立（`_fire_again` 的「再次挑战」和确认弹窗、`fire()` 的 `I_FIRE`、御魂 `run_invite` 的长等待与 `click_fire` 都没有再确认）。
2. 让出没有撤回就绪：成立（`abandon_run` 只清 `in_step`，prelude 的 `yield` / `reload` / `stop` 路径也没撤回）。
3. 可信计数证据顺序：成立（`_result_seen` 在任意结算 / 奖励处理器里都置位；`GeneralInvite._battle_entry_positive()` 复用的 `is_in_battle()` 含 `I_WIN` / `I_DE_WIN` / `I_FALSE` / 奖励页标志，`run_invite` 返回 True 不证明新战斗）。
4. 恢复期间回退运行原始列表：成立（首个任务的 Restart 被「Skip first restart」跳过；阻塞且无可运行任务时 `return pending, waiting`；Restart 位次排在步骤后会被丢；等最后完成时 `current_step()` 为空放开低优先级任务）。
5. β 裁决没覆盖已进门口的任务：成立（B 在 X 门口、A 不认为 X 更高时 B 无限等；`_peer_waiting` 会把位次不高的任务拉进来）。

### 修改
- `tasks/RealmRaid/script_task.py`：`_battle_allowed()` / `_loop_halted`，`fire()`、`_fire_again()`（两处）开战点前确认，`run()` 退四处据 `_loop_halted` 直接收尾。
- `tasks/Component/GeneralInvite/general_invite.py`：`_may_fire()` 钩子（默认放行），`run_invite` 等待循环顶与 `click_fire` 点击前调用。
- `tasks/Orochi/script_task.py`：`_may_fire` 覆写；`_handle_prepare` / `_handle_in_battle` 置 `_battle_seen`；结算证据只在 `_battle_seen` 之后置位；`_leader_fight_once` 用 `attempt_resolved`。
- `module/script/loop_controller.py`：`withdraw_ready()`（含写盘重试）、`attempt_resolved()`、`note_recovery` 返回是否登记、`schedule_hook` 的恢复任务置顶 / 阻塞占位项 / 等最后完成位次参照最后一步、`outranks_current_step()`。
- `module/instance_sync/team.py`：`decide()` 的 `peer_ranks_lower`；`module/script/team_sync.py`：`loop_allows`。
- `script.py`：prelude 非 go 时撤回就绪、异常请求的 Restart 置 `is_first_task = False`、`_loop_should_yield` 先 `answer()`、挂载 `loop_allows`。
- 测试：`test_realm_raid_loop`（4 → 12，含真实 `_fire_again` / `fire` / `run()` 退四路径）、`test_orochi_loop`（18 → 27，驱动真实处理器与 `_leader_fight_once` / `run_leader`，不再手动置 `_result_seen`）、`test_loop_script_glue`（33 → 51，含真实 `Script.loop` 的让出 / 首个 Restart / 阻塞等待、两侧真实调用链的 β 用例、占位项经过真实 `Config.get_next`）、`test_loop_multiprocess`（6 → 7，双进程「让出后撤回就绪」）。修正 2 个测试里「阻塞时返回原始列表 / 等最后完成放开低优先级」的旧断言（它们断言的是错误行为）。

### 验证
- 全量 `toolkit/python.exe -m unittest discover -s tests` 2820 项 OK（2784 → 2820）；`compileall -q module tasks tests script.py` 通过；本轮改动的已跟踪文件 `git diff --check` 无本轮引入的问题。
- 变异 17 条各有测试变红并已还原（其中 2 条第一次没被抓到：残留结算当证据、门口不裁决位次的测试会无限等——前者补了顺序用例，后者给测试加了有界兜底）。

### 后续
- Level C：见 ROADMAP「御魂 → 个人突破循环 Level C 验收」⑧~⑪。

## 2026-10-25 - 寮突破失败后被点「再次挑战」：结算随机点击避开按钮

### 现象与核对
- 用户观察到寮突破失败后程序点了「再次挑战」，要求个人突破的再次挑战逻辑不要用到寮突破。
- 寮突破任务类不继承 RealmRaid，源码里没有 `_fire_again` / `I_FIRE_AGAIN` 调用；日志里 `RES_FIRE_AGAIN` 的点击全部在 RealmRaid 任务内。根因在通用结算：`C_RANDOM_DEFAULT`（742,430,362,230）整个包住 `I_FIRE_AGAIN.roi_front`（830,506,61,36），寮突破 `random_default` 点击约 3% 落进该矩形（日志里全在胜利页，无影响；日志里没有寮突破失败页，没有复现用户当次事件）。

### 修改
- `tasks/Component/GeneralBattle/general_battle.py`：新增 `_settlement_avoid_rois()`（默认空）、`SETTLEMENT_AVOID_MAX_RESAMPLE=20`、`_point_in_any_roi` / `_push_point_out_of_rois`；`_sample_settlement_anchor`（叠加在 `_sample_settlement_point` 之上）与 `_settlement_click` 在有避让区时重采。
- `tasks/RyouToppa/script_task.py`：声明避开 `RealmRaidAssets.I_FIRE_AGAIN.roi_front`，余量 `SETTLEMENT_AVOID_MARGIN=(40, 20)`。
- 其它任务不变（含个人突破）；没有声明时代码路径与随机数消耗与原来一致。

### 测试
- 新增 `tests/test_ryoutoppa_settlement_avoids_again_button.py` 12 项：真实 `run_general_battle` + 结算 handler，强制采样器先落在按钮上，断言实际 `device.click` 坐标；对照组（基类 / 个人突破）仍会点到按钮，证明旧行为存在；另有分布、兜底、不调用 `_fire_again`、失败收尾走 `FAILED_MARKED` 的用例。变异 6 条各有测试变红。

### 验证
- 全量 `toolkit/python.exe -m unittest discover -s tests` 2832 项 OK（2820 → 2832）；`compileall` 通过；`git diff --check` 对本轮改动文件无问题。
- 未做真机验证。

## 2026-10-25 - 寮突破误点「再次挑战」：避让方案改为失败页改点右侧 / 底部区域

### 背景
- 上一条（2026-10-25）用「按钮坐标避让区 + 重采样 + 推出区域」修这个问题。用户要求改成：寮突破明确识别到失败页时，结算改用现有右侧 / 底部区域，胜利结算仍按原位置和规则点击。本条把避让方案整体替换。

### 修改
- `tasks/Component/GeneralBattle/general_battle.py`：
  - 删除上一轮的 `_settlement_avoid_rois` / `_sample_settlement_anchor` / `SETTLEMENT_AVOID_MAX_RESAMPLE` / `_point_in_any_roi` / `_push_point_out_of_rois`，以及 `_settlement_click` 和三个锚点采样点上的相关改动，`_sample_settlement_point` 与单次节流点击恢复原样（本文件相对 HEAD 只剩本条的新增）。
  - 新增 `SETTLEMENT_FAILURE_USES_SAVE_REGIONS`（默认 False）、`_pick_save_region()`（从 `_select_reward_region` 兜底分支拆出，随机数消耗不变）、`_rebase_anchor_for_failure()`；`_handle_result` 在打开开关且 `not context.is_win`（明确识别到 `I_FALSE`）时改用它们。
- `tasks/RyouToppa/script_task.py`：删除按钮避让声明和余量常量，改为 `SETTLEMENT_FAILURE_USES_SAVE_REGIONS = True`（`RealmRaidAssets` 的导入本来就被进攻按钮使用，保留）。
- 不新增配置；个人突破 / 其它任务 / 胜利结算 / 普通奖励页行为不变。

### 测试
- 重写 `tests/test_ryoutoppa_settlement_avoids_again_button.py`（12 → 16 项），验证业务行为而不是避让实现：失败时实际 `device.click` 坐标落在右侧 / 底部区域（掷骰确定性覆盖两个分支）、已有默认区旧锚点时不再使用旧坐标、失败不借用奖励页区域决策、单次节流点击对明确失败不可达、胜利仍是默认区且不掷区域骰子、无胜负横幅不当失败、奖励页决策树不变、个人突破 / 基类失败仍点默认区、寮突破失败仍走 `FAILED_MARKED`。变异 9 条各有测试变红。

### 验证
- 全量 `toolkit/python.exe -m unittest discover -s tests` 2836 项 OK（2820 → 2836）；相关回归 699 项 OK；`compileall -q module tasks tests script.py` 通过；`git diff --check` 对本轮改动文件无问题。
- 没有复现用户当次事件，不宣称唯一根因；未做真机验证。

## 2026-10-25 - 通用战败页结算点击统一：去掉「仅寮突破」开关，所有通用失败结算改点右侧 / 底部区域

### 背景
- 上一条把规则只给寮突破打开（`SETTLEMENT_FAILURE_USES_SAVE_REGIONS`）。用户确认御魂 / 探索 / 觉醒 / 日轮 / 御灵等使用通用战败页的任务失败页布局相同，默认结算随机区可能覆盖「再次挑战」，要求规则收敛到通用失败结算入口。

### 核查（以当前源码为准）
- `I_FALSE` 的识别入口：`GeneralBattle._handle_result` 的 `context.is_win = not appear(I_FALSE, threshold=0.8)`；皮肤适配 `CostumeBase.check_costume_battle` 在原地替换 `I_FALSE` 资产对象（主题 8 / 12 / 13 / 14，阈值均 0.8），所以通用结算自动用皮肤模板。
- 覆盖了 `_handle_result` 的任务：RealmRaid（quick_exit 直接返回、否则 `super()`）、Orochi / HeroTest / BaseAct / NormalClimbAct 非爬塔路径（最终 `super()`）走通用；BondlingFairyland、SixRealms 月之海 / 孔雀国、NormalClimbAct 爬塔单击结算是专用处理，不委托通用结算。个人突破退四：中间几次 quick_exit，最后一战（`is_final`）用完整配置走通用结算。

### 修改
- `tasks/Component/GeneralBattle/general_battle.py`：删除 `SETTLEMENT_FAILURE_USES_SAVE_REGIONS`；`_handle_result` 里 `failed = not context.is_win`，`if failed or self._is_generic_result_context()`（已确认失败的帧一定走通用 burst），失败时调用 `_rebase_anchor_for_failure()` 并用 `_pick_save_region` 作为区域提供者。
- `tasks/RyouToppa/script_task.py`：删除单独启用声明，文件恢复到与 HEAD 一致。
- 不新增配置，不恢复按钮避让 / 重采样 / 推出区域。

### 测试
- `tests/test_ryoutoppa_settlement_avoids_again_button.py` 扩到 24 项（驱动真实 `run_general_battle` / `_handle_result`，7 个任务类、80/20 两分支及边界 80 / 81、旧锚点替换、失败多帧会话节奏与安全帽 9、失败不依赖另一次通用判断、胜利 / 奖励页 / 无胜负横幅不变、个人突破普通失败 + 退四最后一战 + 中间 quick_exit、皮肤映射、六道 / 契灵 / 爬塔不被改道）。
- 更新 `tests/test_general_battle_settlement.py` CASE 13：失败页区域由 `random_default` 改为右侧（旧断言按用户确认的新需求更新，其余断言未动）。变异 10 条各有测试变红。
- 在去掉开关之前的代码上，新测试对基类 / 个人突破 / 御魂 / 探索 / 日轮的失败页全部变红。

### 验证
- 全量 `toolkit/python.exe -m unittest discover -s tests` 2844 项 OK（2836 → 2844）；相关回归 682 项 OK；`compileall -q module tasks tests script.py` 通过；本轮改动文件 `git diff --check` 无问题。
- 离线模拟，不是真机验证；仍没有复现用户当次事件，不宣称唯一根因。

## 2026-10-25 - 狩猎战接入「随机延迟时间」（D033）

### 修改
- `tasks/Hunt/script_task.py`：新增 `_daily_plan(mode, day)`（基准时间 + 一次随机延迟；上限 `Hunt.scheduler.float_time`，先按开放窗口缩小范围再 `random_int` 采样，留 1 秒保证严格早于截止点；基准在截止点上 / 只剩 1 秒 / float_time 为 0 时不采样）；`_schedule_next_day` 和「提前唤起重排当天」两处改用它；10 分钟重试不变；仍 `server=False`。
- `assets/i18n/zh-CN.json`：`kirin_time_help` / `netherworld_time_help` 改写，说明基准时间、随机延迟参与正常排期、受窗口限制、重试不加延迟、实际执行可能晚于计划。
- 不改通用调度器、庭院事务、组队同步、御魂循环、战斗结算，不新增字段，不改实例配置。

### 测试
- `tests/test_hunt.py` 20 → 38 项：延迟为 0、麒麟 / 阴界基准 + 延迟、上下界（`random_int` 固定在下界 / 上界）、靠近 23:00 范围缩小（299 / 29 秒）且 3000 次抽样不堆积在截止点、越界配置仍按开放时间算再加延迟、截止点 / 最后 1 秒不随机且不改到第二天、只随机一次、10 分钟重试不采样、非默认 `server_update` 不改写目标（真实 `set_next_run` → `Config.task_delay`，对照 `server=True` 会改写）、周四→周五 / 周日→周一。变异 10 条各有测试变红。

### 验证
- 全量 `toolkit/python.exe -m unittest discover -s tests` 2862 项 OK（2844 → 2862）；`compileall -q module tasks tests script.py` 通过；本轮改动文件 `git diff --check` 无问题。
- 离线模拟，不是真机验证。

## 2026-10-25 - 地域鬼王：明确战败有限重试（D034）

### 修改
- `tasks/AreaBoss/script_task.py`：`start_fight` 改为最多 `BATTLE_MAX_ATTEMPTS = 3` 场的循环；新增 `_fight_once`（把结果分成胜利 / 明确战败 / 结果不明）、`_detail_ready_for_retry`（重试前新截图确认详情页和挑战按钮）、`_handle_result` 覆盖（基类判定战败时记 `_loss_seen`）。`boss_fight` / `fight_reward_boss` / `run` 不动：三败后 `start_fight` 返回 False，`boss_fight` 照旧关闭详情页，`run` 继续后续目标。
- 不新增配置，不改通用结算、其它任务、御魂循环、调度器；不点失败页「再次挑战」。

### 测试
- 新增 `tests/test_area_boss_retry.py` 23 项，覆盖首胜 / 败后胜 / 两败后胜 / 三败、重试走 `I_FIRE` 不点「再次挑战」、详情页不可用放弃、时间窗口重查、结果不明与异常 / 停止不吞、每目标独立预算且不重拉起任务、悬赏与 60 级前置 / 极两个阶段。变异 11 条各有测试变红；在旧代码上新测试大部分变红。

### 验证
- 全量 `toolkit/python.exe -m unittest discover -s tests` 2885 项 OK（2862 → 2885）；`compileall -q module tasks tests script.py` 通过；本轮改动文件 `git diff --check` 无问题。
- 离线模拟，不是真机验证。

## 2026-10-25 - 预设切换后的契灵替换确认框（D035）

### 修改
- `tasks/Component/SwitchSoul/switch_soul.py`：新增 `_confirm_bondling_replace_dialog`（预设确认之后短时有界观察 `REPLACE_OBSERVE_TIMEOUT = 2.0`，出现就点「确定」，等关闭 `REPLACE_CLOSE_TIMEOUT = 8.0`，关不掉抛 `GamePageUnknownError`）和 `_press_sure`（CONFIRM 点击点，预设确认框与替换框共用）；数字模式在 `_observe_confirm_dialog()` 为 True 之后调用，按名称模式在循环结束、成功日志之前（循环里点过确定才调用）。复用 `I_SOU_SWITCH_SURE`，不新增资源、不新增配置。
- 守卫同步：`tests/test_switch_soul_numeric_v1.py` / `tests/test_switch_soul_group_top_v2.py` 的结构钉子按 `_press_sure` 更新，`tests/test_l1_l2_integration.py` 的 `POST_C1_CONSUMERS` 改名，`docs/L2_CALLSITE_REGISTER.md` 重新生成（总数 1104、policy 点位 97 不变）。

### 测试
- 新增 `tests/test_switch_soul_replace_dialog.py` 15 项，覆盖只有原确认框、替换框稍后出现、没有额外弹窗、关闭后继续、持续存在有界退出且不记成功、已装备同一预设不观察、数字 / 名称两条路径、只在预设确认之后调用。变异 10 条各有测试变红；在旧代码上行为类用例变红。

### 验证
- 全量 `toolkit/python.exe -m unittest discover -s tests` 2900 项 OK（2885 → 2900）；`compileall -q module tasks tests script.py` 通过；本轮改动文件 `git diff --check` 无问题。
- 离线模拟，不是真机验证；替换框能否被 `I_SOU_SWITCH_SURE` 识别是推断，待真机确认。

## 2026-10-25 - 预设确认的有界保护补齐（D035 补记）

### 修改
- `tasks/Component/SwitchSoul/switch_soul.py`：新增 `CONFIRM_CLOSE_TIMEOUT = 10.0` 和 `_raise_confirm_stuck`；数字模式 `_confirm_team_switch` 的恢复循环加本地超时；按名称模式的切换循环对「确定」连续出现计时（消失一帧清零），超时抛 `GamePageUnknownError`。点击间隔、反应时间、正常选择行为不变，不重写预设切换流程。
- `docs/L2_CALLSITE_REGISTER.md` 用 `dev_tools.click_callsite_register --write` 重新生成（只有行号变化）。

### 测试
- `tests/test_switch_soul_replace_dialog.py` 15 → 22 项：两个确认框连续出现无空白帧、「确定」始终点不掉（数字 / 名称两条路径都有界退出、点击次数有界、不写成功日志）、点队伍一直不成功时名称循环自己的本地超时、间歇出现不误报、点击节奏不变。变异 6 条各有测试变红。

### 验证
- 全量 `toolkit/python.exe -m unittest discover -s tests` 2907 项 OK（2900 → 2907）；`compileall -q module tasks tests script.py` 通过；本轮改动文件 `git diff --check` 无问题。
- 离线模拟，不是真机验证。

## 2026-10-25 - 名称预设切换循环的总超时（D035 补记）

### 修改
- `tasks/Component/SwitchSoul/switch_soul.py`：`switch_soul_by_name` 的「选队伍 + 处理确认」循环进入前启动 `SWITCH_LOOP_TIMEOUT = 45.0` 的总计时，每轮放在所有 `continue` 分支之前检查，超时抛 `GamePageUnknownError`。已有的「确定」连续 10 秒计时（消失清零）、契灵替换框 8 秒、0.8 秒 / 3 秒点击间隔、四次队伍点击规则不变；数字模式不动。
- `docs/L2_CALLSITE_REGISTER.md` 用 `dev_tools.click_callsite_register --write` 重新生成（只有行号变化，总数 1104、policy 点位 97 不变）。

### 测试
- `tests/test_switch_soul_replace_dialog.py` 22 → 27 项：全程没有确定且点队伍一直失败、确定间歇出现（`sure_timer` 反复清零）无进展、continue 分支绕不过总超时、正常流程不逼近总超时且点击节奏不变、三种超时各自覆盖范围。变异 7 条各有测试变红。

### 验证
- 全量 `toolkit/python.exe -m unittest discover -s tests` 2912 项 OK（2907 → 2912）；`compileall -q module tasks tests script.py` 通过；本轮改动文件 `git diff --check` 无问题。
- 离线模拟，不是真机验证；真实契灵弹窗的模板识别仍待真机确认。

## 2026-10-25 - 御魂 → 个人突破循环：OASX 配置显示英文 / 区间配置的修复（D032 补记）

### 核查
- **英文显示的根因（源码确认）**：OASX 的标签 = 参数 `name`（字段名）`.tr`、说明 = `description`（`*_help`）`.tr`、分组名 = 组 key `.tr`；翻译只来自 OASX 自带的 Dart 表（`lib/translation/cn_parts`）和启动时从后端 `/home/additional_translate`（= `assets/i18n/zh-CN.json` / `en-US.json`）追加的内容（后者覆盖前者）。`loop_config` / `start_loop` / `rounds` / `target_min` / `target_max` 和四条 `*_help` 在这两处都没有；原来写的 `module/config/i18n/zh_CN.xml` 没有任何代码读取（OASX 也不读），所以界面显示字段名原文。`module/config/i18n/zh-CN.json` 只是 OASX 把自己的 Dart 表回传给后端存的，不是输入。
- **区间「无法配置」的核对**：用真实 `ConfigModel`（`script_task` 输出、`script_set_arg` 逐字段保存、全新实例重读）和真实 `Script._loop_consume_request` 走了整条后端链：120 / 140 能保存、重读后保留、循环启动时读到 `tmin=120 tmax=140`，旧的修复前代码上这条链本来就是通的。真正查到的缺陷有三处：① 字段没有中文，看不出哪个是最少 / 最多；② `LoopConfig` 是普通 `BaseModel`，赋值不校验范围——越界值（0、1000、轮数 101，甚至非整数）会被存进文件，下次加载时 `ConfigBase.__init__` 把整个 `loop_config` 组静默重置成默认值（轮数 / 最少 / 最多一起丢）；③ 最少 > 最多被拒绝时只给原因码 `target_range_invalid`，没有中文说明。OASX 一侧另有两点（Flutter，本机没有 SDK，没有改也没有验证）：立即保存模式下 `_applyValue` 先弹「设置已保存」、不等后端结果，后端返回 False / 400 时界面静默；后端 `merge_value` 不输出 `minimum` / `maximum`，OASX 的整数范围校验永远不触发。

### 修改（只在 OAS 仓库，OASX 没有改）
- `assets/i18n/zh-CN.json`、`assets/i18n/en-US.json`：补 `loop_config` / `start_loop` / `rounds` / `target_min` / `target_max` 和四条 `*_help`（OASX 启动时从后端追加，覆盖自带表）。`module/config/i18n/zh_CN.xml` 里之前写的条目没有任何代码读取，保持原样不再增补。
- `tasks/Orochi/config.py`：`LoopConfig` 开 `validate_assignment`，越界 / 非整数保存失败、原值保留；最少 ≤ 最多不在保存时校验。
- `module/script/loop_controller.py`：新增 `REJECT_TEXT` / `reject_message`，拒绝开始时给中文说明（含当前最少 / 最多）；原因码和返回值（`invalid:<原因>`）不变。
- 没动：字段名、默认值、已有配置值、循环业务规则、其它任务的配置界面。

### 测试
- 新增 `tests/test_loop_config_ui.py` 15 项，变异 8 条各有测试变红；在修复前的代码上，翻译键、越界 / 非整数、拒绝信息相关用例变红，而 120～140 的保存 / 重读 / 读取用例本来就通过。

### 验证
- 全量 `toolkit/python.exe -m unittest discover -s tests` 2927 项 OK（2912 → 2927）；`compileall -q module tasks tests script.py` 通过；本轮改动文件 `git diff --check` 无问题。
- OASX（Flutter）没有 SDK，未运行其测试和静态检查，也没有在真实界面验证。

## 2026-10-25 - 百鬼棋局：上游第一批功能的选择性移植（购买判据 / 手牌恢复 / 点击记录）

### 目标
把上游 `xylolit-mu/OnmyojiAutoScript` 里三项棋局购买相关的修复按代码块适配到本地实现；不整体合并、不 cherry-pick、不整文件覆盖。完整来源与逐功能吸收清单见 `docs/AI_CONTEXT.md` §4.134。

### 修改
- `tasks/Chess/runtime/hand_operations.py`：`_free_one_hand_slot_for_purchase` 在紧急清理既没装配也没卖非阵容卡时，确认阶段仍是「备」后直接 `sell_one_lineup_hand_card`（来源 `0501cb195c1b403bd4eec4230c075bd239c10701`）。
- `tasks/Chess/runtime/economy.py`：`_buy_shop_slot` 重写成功判据与点击预算——点击前目标缺失返回 False；只有实际点击过且 `_confirm_shop_purchase_result` 多帧确认才算买到；一次目标购卡合计最多 3 次实际点击（恢复不重置，限流不计数）；恢复后重新识别目标；恢复标志按 `type == 'lineup'` 置位（`0501cb195c…`、思想参考 `d944d411bd8fe3932b45f43e80358d28b019c8ba` 与 `631968c6ecee7e992350b3c3713bdf3f7a3bed3f`）；确认买到后清该格点击记录、刷新确认后只清变化的格（`47a3a3bc6173e6560ab8cc3658d3e55bc2c80287`）。
- `tasks/Chess/runtime/settings.py`：新增 `SHOP_BUY_MAX_CLICKS` / `SHOP_BUY_CONFIRM_FRAMES` / `SHOP_BUY_CONFIRM_TIMEOUT` 三个类常量；没有用户配置项。
- 没动：`tasks/base_task.py`、`tasks/Chess/assets.py`、`tasks/Chess/c/ocr.json`、`tasks/Chess/script_task.py`、`tasks/GameUi/*`。`90a03025cc6af474f013e1a995a1002df254af1c`（红叉 / 鼬乐币 OCR）因缺少截图证据暂缓。

### 测试
- 新增 `tests/test_chess_shop_purchase.py` 30 项，详见 AI_CONTEXT §4.134。

### 验证
- 全量 `toolkit/python.exe -m unittest discover -s tests` 2957 项 OK（2927 → 2957）；`compileall -q tasks/Chess tests/test_chess_shop_purchase.py` 通过；改动文件 `git diff --check` 无问题。`dev_tools/click_callsite_register.py` 只读运行，未 `--write`，登记册无需重新生成（没有新增 / 删除点击点）。
- 离线模拟，不是真机验证。修改前的原始副本与哈希在 `D:\Codex\workspace\oas-chess-sync-20261025-164124`（项目之外）。

## 2026-10-25 - 百鬼棋局：撤销手写移植，改为只合入上游原始补丁 `0501cb19`

### 目标
按用户要求：直接用 Git 合入上游已有代码，不根据提交说明重新实现。完整的逐提交吸收清单见 `docs/AI_CONTEXT.md` §4.134（已取代同日早先版本）。

### 做法
- 先在 `D:\Codex\workspace\oas-chess-upstream-merge-20261025-170426` 建恢复材料，再在其中的隔离克隆里验证：克隆 = 本地 HEAD + 当前未提交工作区的完整快照提交（3923 个文件与原工作区逐字节核对）；基线测试先跑（撤销手写内容后 2927 项）。
- 用上一轮记录的差异反向应用撤销手写内容，并证明 `tasks/Chess` 与移植前 HEAD 逐字相同。
- 从固定的上游 `self`（`47a3a3bc6173e6560ab8cc3658d3e55bc2c80287`）取候选提交，用 `git merge-tree` 逐个试合：`0501cb19` 无冲突，`git cherry-pick -x` 合入；其余冲突或依赖 `631968c6` 的 Frame 重构，暂缓。
- 工作区只应用经验证的增量补丁（`git apply`），不进暂存区、不提交；应用后 `tasks/Chess` 差异与隔离结果逐字节一致。

### 修改
- `tasks/Chess/runtime/economy.py`、`hand_operations.py`：仅 `0501cb195c1b403bd4eec4230c075bd239c10701` 的原始改动（+14 / -2）。
- 撤销：上一轮手写的 `economy.py` / `hand_operations.py` / `settings.py` / `tasks/Chess/README.md` 改动与 `tests/test_chess_shop_purchase.py`（30 项）。
- 新增 `tests/test_chess_hand_recovery_upstream_0501cb19.py` 10 项（验证用，非上游代码）。
- 文档：§4.134、D036（标 Superseded）、ROADMAP 条目随之更正；新增 D037。

### 验证
- 隔离克隆与原工作区全量 `toolkit/python.exe -m unittest discover -s tests` 均为 2937 项 OK（2927 → 2937）；`compileall -q tasks/Chess tests/...` 通过；本轮改动文件 `git diff --check` 无问题。
- 离线模拟，不是真机验证。

## 2026-10-25 - 秘闻首次通关结果页：结算推进区域改走右侧 / 底部安全区（oas2 17:51 卡死）

### 目标
- 查 oas2 卡死原因；按用户建议让秘闻结算走 random_right / random_bottom 那套。

### 根因（`log/2026-10-25_oas2.txt` 3602~3684 行 + `log/error/oas2_1792921921352` 截图）
- 秘闻第 5 层首次通关，进「胜利 / 排名 / 通关阵容」结果页；通用结果页选区 `C_RANDOM_DEFAULT` 整块在通关阵容面板里，锚点 (869, 555) 点 9 次不推进，之后 60 秒无动作 → `GameStuckError`。
- 同一问题 10-12（第 10 层）、10-19（第 1 / 3 / 4 层）出现过，ROADMAP 里一直记着「需单独开任务修结果页选区」。

### 修改
- `tasks/Component/GeneralBattle/general_battle.py`：新增 `_select_result_region()`（默认 `C_RANDOM_DEFAULT`），`_handle_result` 胜利结果页改用它。
- `tasks/Secret/script_task.py`：覆盖 `_select_result_region()` → `_pick_save_region()`。
- `tests/test_secret_settlement_region.py`：新增 `SecretResultRegionTest` 4 项。
- `docs/AI_CONTEXT.md` §4.141（原写作 §4.120，与寿司 §4.120 重复，2026-10-26 改号）、`docs/ROADMAP.md` 同步。

### 技术决策
- 沿用 10-12 修奖励页的做法：只在秘闻任务里覆盖选区，通用结算流程和其它任务不变；失败页仍走 `_pick_save_region`。
- 没有收窄右 / 底安全区：用报错截图量得面板右沿约 x 1207、下沿约 y 681，右区约 25%、底区约 60% 仍在面板里，估计约三成锚点会采进面板；收窄要另给秘闻一对区域，留给用户决定。

### 验证
- `tests.test_secret_settlement_region` + `tests.test_general_battle_settlement` + `tests.test_general_battle_timing` 117 项 OK；`toolkit/python.exe -m unittest discover -s tests` = 2941 项 OK；`compileall` 通过；本轮改动文件 `git diff --check` 无问题。Level C 待验。

### 后续
- 真机秘闻首次通关观察锚点位置与是否一次推进；落进面板的比例高就收窄区域。需重启 OAS 进程生效。

## 2026-10-25 - 百鬼棋局：完成上游选择性合入并提交（631968c6 前置 + 0501cb19 + d944d411 + 47a3a3bc + 90a03025）

### 做法
- 恢复材料：`D:\Codex\workspace\oas-chess-merge-complete-20261025-174223`。隔离克隆里在 HEAD `8a82cb8f` 上依上游顺序建提交：函数级提取 631968c6 的 4 个函数（替换前后都与上游逐字核对）→ `cherry-pick -x` 0501cb19 / d944d411 / 47a3a3bc（增删行与上游逐行一致）→ 90a03025 适配提交 → 测试与文档提交。
- 工作区验证：另建分支 = 当前未提交工作区的完整快照 + 同一组改动（`base_task.py` 与工作区 L2 `policy` 的冲突手工合并），全量测试通过后才把提交落到 master，并把合并后的文件写回工作区；未提交的其他改动逐文件核对保持不变。

### 修改
- 见 `docs/AI_CONTEXT.md` §4.134 的逐提交表与「冲突适配」。
- 新增 `tests/test_chess_upstream_selective_merge.py` 30 项；重新生成 `docs/L2_CALLSITE_REGISTER.md`；`tests/test_l2_c0_registry.py` 记点位变化；`tasks/Chess/README.md` 更新购买与红叉说明。

### 验证
- 见下方提交说明与 `docs/AI_CONTEXT.md` §7；离线模拟，不是真机验证。

## 2026-10-25 - 式神活动配置页后端准备：新增可选展示信息接口 `/args/layout`

### 做法
- 核对 `GET /args`（`ConfigModel.script_task`）与 OASX `ArgumentModel` / `loadGroups` / 按 `(group, argument)` 保存的实际用法后，判断现有接口已含全部字段，只缺玩法选项、字段归属与初始折叠，于是只加一个可选只读接口，不动任何配置字段与执行逻辑。

### 修改
- 新增 `tasks/ActivityShikigami/args_layout.py`；`module/config/config_model.py` 增加 `TASK_ARGS_LAYOUTS` 与 `script_task_layout`；`module/server/script_router.py` 增加 `GET /{script}/{task}/args/layout`；`assets/i18n/zh-CN.json` / `en-US.json` 补标题；新增 `tests/test_activity_shikigami_args_layout.py` 14 项。

### 验证
- 相关测试 14 项 OK；`compileall` OK；全量 `unittest discover` 2975 项 OK；离线，非界面 / 真机验证。

### 后续
- OASX 页面（多选、分组折叠、顺序保持）另行处理；随机次数区间是单独功能，未做。

## 2026-10-25 - 式神活动体力爬塔：随机战斗次数区间 [ap_limit, ap_limit_max]

### 做法
- 先核实：`Script.run` 每次新建 `ScriptTask`，计数在对象里；`ap_limit` 的读取者只有 `limit_for` / `climb_sequence_v` / `activity_enabled` / `action_limit` / layout。区间只替换「本次目标」的来源，计数仍是 `record_action` 的进入战斗场数。

### 修改
- `tasks/ActivityShikigami/config.py`（`ap_limit_max`、缺失兼容、保存校验、`ap_range_error`、`limit_for('ap')` 取上限）、`base_act.py`（`climb_ap_target`）、`script_task.py`（启动前校验、开头确定目标）、`args_layout.py`（`range`）、`assets/i18n/*.json`、`config/template.json`、新增 `tests/test_activity_shikigami_ap_range.py`，调整 `tests/test_activity_shikigami_args_layout.py` 的字段顺序断言与旧配置夹具。

### 验证
- 新增 26 项 + 布局 14 项 OK；`compileall` OK；全量 3009 项 OK；离线，非界面 / 真机。

### 后续
- OASX 区间控件与「其他设置」去重；真机观察目标日志与实际场数。

## 2026-10-26 - 体力爬塔随机区间：补齐异常恢复边界（修正 2026-10-25 的恢复语义）

### 做法
- 追踪 `Script.run` → `_handle_task_exception` → `task_call('Restart')` → 重新调度：活动的 `next_run` 未被改动，Restart 后立刻再次到点，新对象重抽并重跑前置玩法。对象重建不能作为重新抽取的依据，上一轮的表述已更正。
- 选择「明确终止并延后」：中断瞬间的进度不可信，不猜剩余、不重抽、不清零。

### 修改
- `tasks/ActivityShikigami/script_task.py`：区间随机的体力爬塔且已进入玩法时，自动恢复类异常先 `set_next_run(success=False)` 再原样抛出；固定次数与其他异常保持原行为。新增 `tests/test_activity_shikigami_ap_recovery.py` 11 项。更正 `docs/AI_CONTEXT.md` §4.136 的恢复语义并新增 §4.137，`docs/DECISIONS.md` D039 修订。

### 验证
- 相关测试 11 项 OK（变异验证）；`compileall` OK；全量 3020 项 OK；离线，非真机。

## 2026-10-26 - 体力爬塔随机区间：修正延后排期的时间基准与失败兜底

### 做法
- 复核发现 §4.137 两处不准确：`set_next_run` 默认以任务开始时刻为基准，长时间运行后延后已过期；延后写入失败只记日志并继续抛可恢复异常，会让 Restart 后活动重新随机。已更正「调用 set_next_run 就保证不会立即重跑」「保存失败只记日志也安全」的表述。

### 修改
- `tasks/ActivityShikigami/script_task.py`：改用 `config.task_delay(start_time=中断时刻, success=False)` 并读回校验；失败时抛 `RequestHumanTakeover`（异常链保留原异常与保存失败原因）。`tests/test_activity_shikigami_ap_recovery.py` 替换「保存失败仅保留原异常」一项并新增边界用例（共 17 项）。`docs/AI_CONTEXT.md` 修订 §4.137 并新增 §4.138，`docs/DECISIONS.md` D039 修订。

### 验证
- 恢复测试 17 项 OK（两种变异均变红）；`compileall` OK；全量 3026 项 OK；离线，非真机。

## 2026-10-26 - 每日琐事：吉闻按天检查一次、寿司按时段检查一次、收邮件补已处理检查

### 目标
- 解决已领取或没有可领取内容时仍反复启动整个每日琐事的问题（10-26 oas1 / oas2 寿司持续「not found → 10 分钟后重试」）。

### 修改
- `tasks/DailyTrifles/script_task.py`：`run_luck_msg` 区分「领到 / 正常检查无奖励 / 页面没进、奖励关不掉」，前两种记 `luck_msg_dt`；`run_courtyard_sushi` 正常检查没有寿司也记本时段、`goto_page` 失败不记；删除 `_sushi_retry_at` / `SUSHI_RETRY` 与 `plan_next_dt` 的 +10 分钟分支；`run_pickup_email` 入口检查当天已处理。
- `tests/test_daily_trifles.py`：按新口径修订并新增用例（详见 `docs/AI_CONTEXT.md` §4.139）。
- `docs/AI_CONTEXT.md` §4.139、`docs/DECISIONS.md` D031 补记、`docs/ROADMAP.md` 同步。

### 技术决策
- 「没识别到」与「没打开页面 / 设备异常」分开：前者是正常检查结果，后者不记，也不写 finally。
- 没有证据要证明用户是否手动领过，正常检查完就收尾；不增加持续轮询。
- 正常排期不动，不碰通用调度与 `failure_interval`。

### 验证
- `tests.test_daily_trifles` 59 项 OK；`compileall` 通过；全量见最终报告；Level C 待验。

### 后续
- 真机：日志不再出现 `Courtyard sushi not collected yet, retry at ...`；无寿司时出现「未发现可领取寿司」且同时段不再进庭院；吉闻 / 邮件当天只做一次。需重启 OAS 进程生效。

## 2026-10-26 - 福利道馆模式（Dokan 内受开关保护的新流程）

### 做法
- 开发前只读核对后，用户截图纠正：右上角「再战道馆」就是已有的 `I_RYOU_DOKAN_FAILED_VOTE_BATTLE_AGAIN`；`log/annotator` 里的整屏截图提供了预设确认框、投票面板、「集」字与徽章相对位置等依据。

### 修改
- 新增 `tasks/Dokan/welfare.py`；`tasks/Dokan/config.py`（`welfare_mode` / `welfare_min_people`）、`script_task.py`（入口）、`res/swipe.json` + `res/image.json`（福利滑动资源、返回标志搜索范围）并用 `AssetsExtractor` 重新生成 `assets.py`；`module/device/app_control.py`（`app_process_exists`）、`module/fatigue.py`（`suspend_active`）、`script.py`（`_add_active_seconds`）；中英文说明、`config/template.json`；重新生成 `docs/L2_CALLSITE_REGISTER.md` 并更新三个守卫测试的期望数字；新增 `tests/test_dokan_welfare.py` 49 项、`tests/test_dokan_normal_mode.py` 22 项。

### 验证
- 离线：相关测试、`compileall`、全量 `unittest discover`（见最终报告）；变异验证 8 条。模板匹配 / OCR / 滑动 / 游戏时序未验证（见 ROADMAP「福利道馆模式 Level C 验收」）。

## 2026-10-26 - 福利道馆收尾：最终次数不推算、滑动按稳定性分类、再战投票不再认任意变化

### 目标
- 用户架构审查三处问题的定点修复，并核对文档编号与验证级别措辞；不重做流程、不增加功能。

### 修改
- `tasks/Dokan/welfare.py`：① `_run` 末尾最终次数读不到 → `RequestHumanTakeover`（保留已开启馆数的说明），不再 `return remaining`，入口因此不写次数、不进正常 `next_run`；读到 0 正常结束，读到仍有机会如实返回、不开第三馆。② `_swipe_list` 按 `FrameWaitResult` 契约返回 `moved` / `static`：变化且稳定 → moved；稳定无变化 → static（才计入到底）；变化未稳定 → 有界重新观察，稳定后按相对滑动前是否变了归类，仍不稳定转人工；异常上抛。③ `_vote_again` 改为：点击真的发出 + 按钮自己的框变化并稳定且最终帧仍不同 + 仍在投票界面，才算本方选中；只点一次，确认不了转人工、不启动 120 秒等待。另修 `_wait` 的浮点残差。
- `tests/test_dokan_welfare.py`：假游戏 `World` 增加滑动模式、最终次数、限流、投票反例模式；新增 16 项（见 AI_CONTEXT §4.140）。
- 文档：AI_CONTEXT 福利道馆章节改号 §4.139 → §4.140（与每日琐事 §4.139 重复）、秘闻 §4.120 → §4.141（与寿司 §4.120 重复），并修正验证级别（「小游戏模拟器」改为「离线假游戏 / 虚拟时钟测试」）、准备关闭的验收表述（点击返回后立即关闭，不承诺关闭前不进战斗）、再战投票限制；ROADMAP / DECISIONS D040 同步。

### 验证
- 福利道馆 + 普通模式 87 项离线通过；3 条变异均变红。全量见最终报告。真机项目全部未验证。

## 2026-10-26 - 福利道馆：match_all_any 五项结果被当四项拆包（§4.140 补记）

### 核查与修复
- **首次实测（2026-10-26 20:28，oas2）暴露的缺陷**：点阵容 / 一键预设 / 确认后第一次处理「鑫」候选时 `ValueError: too many values to unpack (expected 4)`，尚未开馆。根因：`RuleImage.match_all_any()` 的真实返回是 `[(score, x, y, w, h), ...]`（`module/atom/image.py` 把服务端 `matches` 逐项转 tuple），`welfare.py` 按四项坐标拆包，并按 `item[1]`（五项里是 x）排序；返回本馆处同样 `x, y, w, h = matches[0]`。离线测试的假游戏也返回四项坐标，与真实接口不符，所以没抓到。修复：新增模块内函数 `match_boxes(rule, matches)`，是唯一的「外部五项 → 内部四项 `(x, y, w, h)`」转换点（置信度在此丢弃，格式不符抛带规则名的 `ValueError`，不静默截取）；`_candidates()`（按 y 从上到下排序、指纹、`candidate["box"]`、`ClickBounds`）和 `_restart_and_return()`（唯一返回标志、徽章偏移）都经它。没动公共图像接口、模板阈值、业务规则。福利模块之外的 `match_all_any` 消费者（Chess、KekkaiUtilize 选中锚点）按五项解包，GeneralInvite 只取 `len()`，只读核对，无问题。测试：`tests/test_dokan_welfare.py` 假游戏改为五项（score / x 与行号不单调、整体按分数倒序返回），新增 `MatchContractTest` 9 项（实测原值、从上到下排序、点击落在四项框内、重定位、返回本馆唯一 / 多个 / 无 / 四项报错、空列表与边缘、格式错误、真实 `RuleImage` 包装层 + 假 RPC 客户端）；修复前 57 项报错 / 4 项失败。

### 验证
- 相关测试 `tests.test_dokan_welfare` 74 项通过；变异（排序改按 x、坐标混入 score）均被测试发现。全量 3134/3134 OK。
- 真机：只证明了本次格式错误，其余福利流程未实测。

## 2026-10-27 - SwitchSoul：按名称找分组 / 找队伍重做（D041）

### 核查
- 旧流程：固定 sleep + 两次 OCR 文字相同判到顶，找目标 `while 1` 无上限，点击 `ocr_appear_click` 用 `filter` 子串 + 单字回退；队伍滑动资源约 50px。
- 手指方向：分组 `ss_group_swipe_up` 起 y≈190 → 终 y≈332 是手指向下（回顶），`ss_group_swipe_down` 手指向上（向后）；队伍反过来命名（`ss_team_swipe_down` 手指向下 = 回顶，`ss_team_swipe_up` 手指向上且只有约 50px）。
- `RuleOcr` 的 `roi` 才是 OCR 裁剪区，`area` 是 FULL 模式会被检测框覆盖的点击区；`BoxedResult.box` 是相对裁剪区的 4×2 点阵。

### 修改
- **问题**：按名称切换预设（`SwitchSoul.switch_soul_by_name`，ActivityShikigami / AreaBoss / BondlingFairyland / DemonEncounter / DemonRetreat 在用）的找分组、找队伍是旧写法——回顶靠「两次 OCR 文字相同」加固定 `sleep`，找目标是 `while 1` 无上限滑动，点击用 `ocr_appear_click`（`filter` 子串 + 单字回退）而不是搜索时的精确相等，队伍滑动资源只有约 50px。目标不存在会无限滑；「魂土」可能点到「魂土备用」；OCR 读空两次就被当作到顶。**新流程**（只动按名称路径，数字模式一行没改）：分组回顶 → 从上到下找 → 点击前重新定位 → 点击并确认「分组行 + 中央队伍列表」变化并稳定 → 队伍回顶 → 找 → 重新定位 → 原有的预设切换确认循环（4 次队伍点击、预设确认、契灵替换、各超时全部保留）。**边界**：回顶 / 翻页每次都是 `BaseTask.swipe(RuleSwipe)`（端点采样 + 轨迹模型原样使用，不传 interval）之后用 `wait_for_changed_and_stable`（0.02 / 0.01 / 连续 2 帧，4 秒）等稳定；`success`（变化且稳定）= 滑动生效；稳定但没变化 = 静止（到边界的证据）；变化但不稳定 = 有界重观察，仍不稳定就报错（不当作到边界）；`swipe()` 没发出（返回 False）直接报错，不算一次滑动。到顶 / 到底都要「连续 2 次静止」，到顶那一帧还必须读到有效文字；OCR 读 0 行时同一次读取最多换帧重读 3 次，仍为空报错，不判到顶 / 到底 / 目标不存在。上限（故障边界，不是游戏支持数量）：回顶分组 12 次 / 队伍 20 次，翻页分组 20 屏 / 队伍 30 屏，每个阶段总时限 150 秒；另有「翻页后回到之前出现过的内容」的循环检测。**精确匹配**：首尾去空白后严格相等（`exact_matches`），不去符号 / 内部空格、不做单字回退；同屏多个精确同名直接报歧义，不点；文字框被列表上下沿裁切（离可视区边缘 <3px）的命中本屏不点，翻页后再看（已确认到底时才接受）。只检查「首次命中的那一屏」是否重名，不同屏同名不做全列表唯一性检查（要扫完整个列表，成本高且没有可靠依据）。点击前连续两帧都只命中一个、y 偏差 ≤6px 才点（列表还在滚就不点）；分组点击后无可见变化时补点一次，仍无变化只警告继续（可能本来就是当前分组），之后队伍列表必须读得到文字。失败一律抛 `SwitchSoulNameError`（继承 `GamePageUnknownError`，消息带「分组 / 队伍名 + 阶段」，沿用「通知 + 重启游戏 + 稍后重试」，不会退出进程），不回退到别的预设，也不写成功日志。**资源**：新增 OCR 专用 swipe 四个 `ss_name_group_to_top` / `ss_name_group_next` / `ss_name_team_to_top` / `ss_name_team_next`（源 JSON → 用 `AssetsExtractor` 生成 `assets.py`，只多出这四条）；分组 约 260～280px、队伍 约 250px（旧队伍资源只有约 50px），起终点都落在对应列表内（分组在右侧列表，队伍在中央列表 x≈640～760，避开左侧式神列表和底部新增按钮）；旧四个 swipe 资源与两个 OCR 区域（`O_SS_GROUP_NAME` roi `1087,91,155,566`、`O_SS_TEAM_NAME` roi `573,140,277,481`）原样未改——没有真机截图 / OCR 日志可核对，不盲目改区域；等级、御魂数字等噪声靠精确相等排除。**点击**：`ocr_appear_click_by_rule` 改名为 `_click_line`（仍是唯一的 `execute_single_click`：y 取命中行、给了预设按钮列时 x 取按钮列，两轴各采样一次），分组点击也走它；新增 `_LineTarget` 包装命中行，不修改共享的 OCR 资源（不再临时改 `keyword`）。
- 新增 `tasks/Component/SwitchSoul/name_search.py`（OCR 结果解析 / 精确匹配 / 完整性判断 / `SwitchSoulNameError`），`ss/swipe.json` 增 4 个 OCR 专用资源并生成 `assets.py`。
- `docs/L2_CALLSITE_REGISTER.md` 重新生成（总数 1124 → 1123）；`docs/T7_TARGET_PREFERENCE_MAP.md` 的 L1M-019 指向改名后的 `_click_line`。

### 测试
- **测试**：新增 `tests/test_switch_soul_name_search.py` 37 项——真实 `RuleOcr.detect_and_ocr`（只替换模型，返回真实 `BoxedResult`）+ 真实 `BaseTask.swipe` / `sample_endpoints`（只替换最底层 `swipe_trajectory`，按手指方向移动虚拟列表）+ 真实 `wait_for_changed_and_stable` / 帧差（按虚拟列表渲染的真实 ndarray）+ 虚拟时钟 + 截图次数失控保护；覆盖当前屏命中、第 8 组、滚动后才出现的队伍、从列表中间开始回顶、14 队逐个可达（边缘队伍不漏）、动画未停、目标不存在、阶段总时限、OCR 读空 / 偶发漏识别、相近名称 / 子串 / 单字碎片 / 首尾空白、同屏重名、变化但不稳定、滑动未发出 / 完全无效 / 丢一次、目标漂移后用新坐标点击、持续滚动不盲点、分组点击后队伍列表延迟刷新、点击落点（分组在命中行内、队伍在预设按钮列且行号正确）、新 swipe 资源方向与落点范围、旧资源和 OCR 区域未改。变异 12 条各有测试变红（其中 2 条首轮漏网，补了「OCR 在到顶 / 查找阶段才读空」用例后抓住）。既有测试的调整（原因：搜索阶段被新流程取代）：`test_switch_soul_replace_dialog` 的按名称沙盒把 6 个搜索阶段方法替身成固定截图数、把队伍点击换成 `_click_team_by_name`，确认循环的全部用例与断言不变；`test_switch_soul_numeric_v1` / `test_switch_soul_group_top_v2` 里冻结旧按名称流程的「固定 sleep 与 4 个旧 swipe」断言改为冻结仍成立的部分（4 次队伍点击、1.5 秒间隔、无 policy、无 sleep、旧四个资源仍在、数字模式滑顶仍只用 `S_SS_GROUP_SWIPE_UP`）；`test_l1_click_pipeline` 的守卫与 case 23 从 `ocr_appear_click_by_rule` 指向 `_click_line`，断言不变；`test_l2_c0_registry` 钉住数字 1124 → 1123（去掉 `ocr_appear_click(O_SS_GROUP_NAME)` 一点）、rule 925 → 924、KEEP_IMMEDIATE 635 → 634，登记册已重新生成。

### 验证
- 全量 `toolkit/python.exe -m unittest discover -s tests`：3171 项，仅 `test_swipe_endpoint_sampling.WideRoiPassthroughTest.test_both_wide_output_distribution_matches_legacy_coord` 一项失败（15000 样本的均值比较，差 3.23 超过 delta 3.0，纯随机抖动，与本轮无关；该模块单独重跑 6 次全过）。`test_switch_soul_name_search` 连续 4 次全过。
- **未验证（全部待真机）**：分组 / 队伍的 OCR 识别率与 OCR 区域是否会带进等级、御魂数字等噪声；新 swipe 资源在真机上的实际滚动量（分组一屏 8 个、队伍一屏约 3.4 个，翻页位移是否留有足够重叠、是否有惯性滑过头）；分组点击后中央列表刷新是否会比「连续 2 帧安静」更慢（更慢会被后面的回顶滑动再次吸收，但没实测）；点击预设按钮时 x 取按钮列、y 取队伍名所在行是否对应同一行（沿用旧口径，未变）；最终装备的预设效果。离线通过只说明定位与确认流程的逻辑。

## 2026-10-27 - SwitchSoul 按名称预设收尾：分组选中确认 / 错误分类 / 队伍小步幅（D041 补记）

### 核查
- 数字模式有 `I_SOU_CHECK_GROUP_1~7`（金色竖条，选中高亮，x≈1085~1111，皮肤会替换），原本只登记没使用；用它做名称模式的选中状态证据，不新增模板。当前页面（一屏 8 个分组）是否能识别没有实证。
- `RequestHumanTakeover` 在 `Script._handle_task_exception` 里是「通知 + 进程退出」，`GamePageUnknownError` 是「通知 + Restart」。
- 新步幅在端点采样后的实际分布：基准 135px → 约 75～190px（均值约 135），y 约 266～478，x 约 682～756。

### 修改
- **① 分组选中确认**（`_name_select_group` 整段重写）：选中的依据是「选中标志只有一个且落在目标行」这个**状态证据**，用数字模式已有的选中高亮模板（金色竖条，`I_SOU_CHECK_GROUP_2`，`copy.copy` 后临时放宽到整条左边缘 x 1080~1120，随皮肤替换；标志中心与目标行中心 y 相差 ≤25px，行距约 66px），**不再**把「区域变化」或「队伍列表读得到文字」当证据。点击前标志已在目标行 = 本来就是目标分组，不点击；否则点击（最多 2 次，每次点击前重新定位）→ 等分组区域稳定 → 再查标志；始终确认不了（标志在别的行 / 没有标志 / 多个标志）→ 转人工，不继续找队伍。**分组确认和中央队伍列表就绪分别检查**：确认选中之后，先前不是目标分组时中央队伍列表必须相对点击前「变化并稳定」（最多 3 轮观察，仍无变化 = 可能读到旧分组的队伍 → 转人工），本来就是目标分组时只要求稳定，最后队伍列表还要读得到文字；成功日志（`selection confirmed`）只在两项都满足后写。**缺的画面**：这些模板来自数字模式的旧页面，当前页面（一屏 8 个分组）是否能识别没有实证——需要**选中某个分组时右侧分组列表的整屏截图**；识别不到时按本规则安全停止（报错信息里写明缺什么），不会继续操作旧分组。**② 错误分类**（只在 SwitchSoul 局部，公共异常与调度器未改）：`SwitchSoulNameError(RequestHumanTakeover)` = 确定需要人工——空名称、完整搜索（确认的顶部到确认的底部、OCR 有效）后目标不存在、同屏精确同名、无法确认分组选中、选中后中央列表一直不变；走 `Script._handle_task_exception` 里已有的人工处理分支（通知 + 进程退出），**不安排 Restart**；`SwitchSoulPageError(GamePageUnknownError)` = 临时识别 / 页面问题——OCR 连续读空、列表不稳定、滑动没发出、阶段超时、搜索达到保护上限但没有可靠确认到底、翻页后回到旧内容、点击前定位不稳——沿用「通知 + 重启 + 稍后重试」。**「到底」新增证据要求**：除连续 2 次静止 + 有效 OCR 外，还要滑动真的生效过（回顶或翻页里出现过 moved），或最后一行下面空着一整行（列表本来就没满一屏）；否则按页面问题处理，不会把「滑动全部无效」当作「名称不存在」。已知边界：恰好一屏放满（如正好 8 个分组）且目标不存在时无法区分「列表不会动」和「滑动无效」，按页面问题处理（会重启并重试），不是人工。设备类异常（截图 / 控制失败）不经过这两个类，保持原类型。**③ 队伍向后翻页改小步幅**：`ss_name_team_next` 基准手指位移约 250px → 约 135px（front `680,430,80,20` → back `680,295,80,20`；采样后约 75～190px，均值约 135；起终点 y 约 266～478、x 约 682～756，都在中央队伍列表内、避开左侧式神列表和底部按钮），用户页面一行约 150px，所以每次最多翻约一行，边缘队伍下一屏必然完整出现。队伍回顶（约 250px）、分组两个资源、数字模式四个旧资源不变。**预算同步放大**（都是故障边界）：队伍翻页上限 30 → 60 屏、回顶 20 → 30 次、阶段时限 150 → 300 秒（`timeout_scale=2.0`；依据：平均每次约 0.9 行，60 屏约能覆盖 ≥ 40 个队伍；每屏约 3~5 秒）；分组不变（20 屏 / 12 次 / 150 秒）。达到上限只报页面问题，不写成名称不存在。循环检测对步幅变小的审查：步幅小于一行时相邻两屏文字常常完全相同，`trail` 把相邻相同的屏折叠，只有与更早的**不同**内容重复才报循环，不会误报。

### 测试
- **测试**：`tests/test_switch_soul_name_search.py` 37 → 61 项：假世界新增选中标志（贴项目里真实的 `ss_sou_check_group_2.png`）、点击无效 / 无关动画 / 列表不刷新 / 无标志 / 双标志开关，用真实 `RuleImage.match_all_any`（只换 RPC 客户端，客户端用 cv2 做真实模板匹配并返回真实 `[score, x, y, w, h]` 协议）识别；新增 `GroupConfirmationTest`（本来就是目标、点击无效、两组同名队伍、列表延迟刷新、无关动画、列表不变、无标志、双标志、选中分组在可视区外、成功日志顺序）、`ErrorClassificationTest`（五类人工错误 / 三类页面错误的类型、设备异常原样、真实 `Script._handle_task_exception` 对两类的处理：人工类 `SystemExit` 且不调 `task_call`、页面类 `task_call("Restart")`，原异常对象传到 `exception_handler`）、`SmallStepSearchTest`（相邻屏重叠、下沿裁切后找到、大量相同相邻屏不误报循环、40 队长列表预算内找到、长列表确认不存在、长列表回顶预算、预算常量、仍走 `swipe_trajectory`），并更新几何断言（新步幅 75～190、均值 120～150，回顶更大）。旧用例「无变化后警告继续」换成「已确认本来就是目标分组时不点击」。变异 14 条各有测试变红（选中不看标志 / 任何标志都算目标 / 不检查列表就绪 / 不要求列表变化 / 多标志不算歧义 / 确认不存在与保护上限的错误类别互换 / 滑动全无效也算到底 / 相邻相同屏误报循环 / 队伍翻页退回大步幅 / 预算不放大或过小 / 名称错误走重启类 / 同屏重名走页面错误）。

### 验证
- 3195/3195 OK（首轮全量；上一轮的统计性抖动用例本轮首轮未失败，分析见 §4.144 验证说明）
- **未验证（全部待真机）**：分组选中高亮（`I_SOU_CHECK_GROUP_*`）在当前页面能否识别、y 对齐是否准确（缺整屏截图，见上）；队伍翻页的实际滚动量（约 135px 基准只是手指位移，不是已验证的滚动距离）；OCR 识别率与区域；队伍行与预设按钮的对应关系；最终装备的预设效果。名称错误现在会让该实例进程以「人工接管」退出（原先是无限滑动），真机要确认通知内容和你期望的处理方式一致。
- 上一轮全量出现的 `test_swipe_endpoint_sampling.WideRoiPassthroughTest.test_both_wide_output_distribution_matches_legacy_coord`（均值差 3.23 > delta 3.0）核查：该用例用无种子的 15000 个样本比较 legacy 与 v2 两个采样器的均值 / 标准差，delta 固定为 3.0；实测 24 组独立样本里均值差的标准差约 0.7～1.05、最大 |差| 2.34，没有系统偏差，所以 3.0 约是 3σ 左右，单次全量里偶发越界的概率约 1% 量级，属于测试自身的统计性偶发。本轮全量首轮 3195 项全部通过，单独重跑 30 次也全过；没有改阈值、没有改公共随机模型。

## 2026-10-27 - 契灵队长创建房间后空等 15 秒（D042）

### 核查
- 日志：13:16:53.295 点击 `BALL_CREATE_TEAM`，13:16:53.302 `Ensure private`，13:17:08.511 `Ensure private timeout`，13:17:08.827 `Ensure enter invite page`；10-22 / 10-24 / 10-27 的实例日志共 37 次点击创建、36 次紧接着超时、没有一次点到私人设置标志。
- 源码：`create_bond_team` 点击后用点击前的旧截图判断房间，随后无条件调用 `GeneralRoom.ensure_private()`（只认私人 / 公开标志，无房间退出分支），返回值被忽略。

### 修改
- **根因（日志 + 源码确认）**：10-27 oas2 13:16:53 点击 `BALL_CREATE_TEAM` → 13:16:53 `Ensure private` → 13:17:08 `Ensure private timeout` → 13:17:08 `Ensure enter invite page`，房间早已打开。旧 `create_bond_team`（`run_leader` 里的嵌套函数）点击创建后立刻用**点击前的旧截图**判断 `I_GI_IN_ROOM`，看不到就无条件 `ensure_private()`；后者只认私人 / 公开设置标志、没有「已经在房间」的退出分支，必然等满 15 秒，返回值（False）在契灵调用处被忽略，之后下一轮循环才看到房间。10-22 ~ 10-27 的实例日志里 37 次点击创建，36 次紧接着 `Ensure private timeout`，**没有一次点到过私人设置标志**——契灵的创建按钮直接进房间，私人设置页（`GR_CREATE_ROOM` 那个创建对话框的私人勾选）在这条路径上不出现。**修复**（`tasks/BondlingFairyland/script_task.py`）：嵌套函数提取为方法 `create_bond_team()`（行为不变的部分原样保留：房间 / 选择共鸣 / 求援 / `BondlingNumberMax`），点击创建后改为：`appear_then_click` 返回 True（确实点出去）才进入有界观察 `_observe_after_create()`（窗口 `CREATE_OBSERVE_TIMEOUT=8` 秒，故障边界，不是固定等待），**每一轮都用新截图**：① 房间出现 → 立刻返回交接邀请，日志明确写「private state NOT verified」；② 创建设置页（四个私人 / 公开标志任一）→ 走原有 `ensure_private`，看到私人标志才记「private setting verified」；③ 窗口内都不是 → `pending`，回到外层循环，过渡页上不会重复点创建；点击没发出（限流 / 目标消失）不进入观察。同一次创建最多点 `CREATE_MAX_ATTEMPTS=3` 次，再不行抛 `GamePageUnknownError`（明确原因），不默认创建成功。**公共改动**（`GeneralRoom.ensure_private`）：新增可选参数 `exit_when=None`，每次新截图后先检查，出现就立刻返回 False（仅表示「没有确认私人」）；默认行为与原来逐字一致，其它 7 个调用者（EternitySea / EvoZone / Exploration / FallenSun / Orochi / OtherWorldTwilight / TrueOrochi）一律没传。`ensure_private` 返回 False 时契灵调用处不再无条件忽略：房间已出现按「房间 / 私人未验证」继续，否则仍停在设置页 = 没能确认私人，抛 `GamePageUnknownError`，不进入邀请。**两个事实分开**：A「已进房间，不必再等创建设置页」≠ B「房间私人状态已验证」——源码和资源里没有「契灵创建入口固定为私人」的依据，所以进房间时日志只写 NOT verified；私人设置页真的出现并确认了才写 verified。**顺带发现（未改）**：`BaseTask.appear(target, interval=1)` 与 `appear_then_click(target, interval=2)` 对同一目标交替使用时，`interval_timer` 按 limit 不同每次换一个未启动的 Timer，实际不限流（原 `create_bond_team` 的 2 秒点击间隔因此形同虚设）；本修复靠「点击后观察窗口内不再点击」避免重复创建，没有改公共 `appear`。

### 测试
- **测试**：新增 `tests/test_bondling_create_team.py` 20 项——虚拟世界（每帧可见标志由阶段决定，`interval` 门控与真实 `BaseTask` 一样按目标名换 Timer）驱动真实 `ScriptTask.create_bond_team` / `_observe_after_create` / `run_leader` 和真实 `GeneralRoom.ensure_private`，只替换截图 / 识别 / 时钟：房间点击后立即出现（虚拟耗时 < 5 秒，`ensure_private` 未被调用；同一世界上特征化旧逻辑耗时 ≥ 15 秒）、点击后用新截图判断、过渡 5 帧后出现房间且不重复点击、过渡超过窗口也不重复点击、进房间日志是 NOT verified 而不是 verified、创建设置页仍走原私人切换（私人开关被真实点击）、已是私人不点、设置页中途进房间不等满 15 秒且不谎称私人、私人设置失败抛 `GamePageUnknownError`（等满 15 秒预算）、创建点击无效最多 3 次后失败、限流的点击不进入观察、未知页面不当作成功且设备层 `GameStuckError` 原样传播、观察中的设备异常保持类型、真实 `run_leader` 在房间出现后立刻交给邀请流程（`run_invite(is_first=True)` 一次、总耗时 < 6 秒）且创建失败不会走到邀请、公共 `ensure_private` 默认行为不变（看到私人 True、在房间也只等到超时 False）、新参数默认 None、只有契灵传了 `exit_when`、`run_leader` 不再含嵌套闭包。变异 10 条各有测试变红（回到旧逻辑 / 忽略点击是否发出 / 观察不识别房间 / 不传退出条件 / 进房间谎称已验证 / 私人失败当成功 / 重试不设上限 / 窗口为零 / 观察不重新截图 / 公共退出条件被忽略）。登记册重新生成：总数不变（1123），契灵 3 个点击点的函数名由 `run_leader` 变为 `create_bond_team`。

### 验证
- 3215/3215 OK（首轮全量）
- **未验证（全部待真机）**：房间标志 `I_GI_IN_ROOM` 在点击后的真实出现时间与 8 秒窗口是否够；契灵创建后房间是否默认私人（没有证据，不宣称）；其它情形下是否真的会出现创建设置页；邀请本身的耗时（截图、识别、好友列表加载）仍是正常耗时。预期收益只是「消除已进房后的无效等待」，不承诺邀请总耗时。

## 2026-10-27 - 契灵组队：锁队状态与 `lock_team_enable` 衔接（D043）

### 核查
- 队长：`switch_ball` → `run_catch` → `lock_team()`（锁定图标可见才返回）→ `run_leader`（2 处 `run_general_battle(battle_config)`）；队员：`run()` → `run_member`（2 处），不经过任何锁队检查；`BattleConfig` 隐藏 `lock_team_enable` 并继承默认 False；`general_battle_config` 属性虽设 True，但同时覆盖其它参数，不能直接替换组队配置。
- `GeneralBattle._prepare_click_ready`：True 先等 `prepare_click_timer`（默认 3 秒），False 立即判断；`check_then_accept` 不设置该标志。

### 修改
- **三件事要分开看**：① 游戏内「锁定队伍」状态（锁定 / 未锁定图标 `I_BALL_LOCK` / `I_BF_LOCK` / `I_BALL_UNLOCK` / `I_BF_UNLOCK`）；② 通用战斗的配置标志 `lock_team_enable`（True 时 `_prepare_click_ready` 进准备页先等约 3 秒才允许点准备，False 时立即判断）；③ 默认邀请 / 接受邀请（`check_then_accept`，不设置任何锁队标志，也不是锁队证据）。**源码确认的不一致**：队长在 `run_catch` / `run_search` 开头调用 `lock_team()`（看到锁定图标才返回），队员原来不经过任何锁队检查；`BattleConfig` 隐藏了 `lock_team_enable`，继承默认 False；队长 2 处、队员 2 处 `run_general_battle` 直接传任务原 `battle_config`，所以游戏已锁队、自动准备时，通用战斗仍按 False 立即补点准备。实际误点发生时的画面没有捕获，不宣称这是误点的唯一原因。**修复**（只在契灵，`tasks/BondlingFairyland/script_task.py`）：新增 `team_locked`（本账号游戏内锁队已被识别确认，只在看到锁定图标时置位）、`team_battle_config()`（基于任务 `battle_config` 的 `model_copy` 副本，只设置 `lock_team_enable=team_locked`，其它字段原样保留，不改共享对象、不写回 JSON、无新用户开关）；队长 / 队员共 4 个战斗入口全部改用它；`lock_team()` 返回前置位 `team_locked`；队员 `run_member` 开头新增 `confirm_team_locked()`——**只观察、不点击**，`LOCK_CONFIRM_TIMEOUT=6` 秒有界窗口内看到锁定图标才确认，看到「未锁定」图标或什么都看不到都不确认（`lock_team_enable` 保持 False = 原行为），本账号之前已锁过（handoff 先当队长）就不重复观察。**队长 / 队员分别**：队长靠自己的 `lock_team()`；队员不能假定队长锁了就等于自己锁了，也不能用默认邀请代替证明，必须自己在页面上看到锁定图标；队员侧不替用户点锁定（原来队员从不锁队，擅自锁会改变游戏设置）。已锁队时通用战斗沿用已有的约 3 秒自动准备等待，超时后仍点准备（兜底不变）；ALONE 单人路径（`run_catch` 里传 `battle_config` 的那一处）不在本轮范围，未改。**缺口**：队员页面如果没有锁队图标（例如 handoff1 回到契灵主界面后），就确认不了，按未锁定处理；是否需要在别的页面补一次观察，要真机看队员页面实际能看到哪个图标。

### 测试
- **测试**：新增 `tests/test_bondling_team_lock.py` 17 项：驱动真实 `lock_team` / `confirm_team_locked` / `team_battle_config` / `run_leader` / `run_member`，并把生成的配置交给真实 `GeneralBattle._build_context` / `_prepare_click_ready` / `_handle_prepare`（虚拟时钟）——队长首次邀请 + 后续战斗两个入口都拿到已锁队副本（原配置对象不变，其它字段相等）、没有确认锁队时标志为 False（不是写死 True）、队员房间内 + 队长秒开两个入口、未锁定 / 无图标不确认且不点击、观察窗口有界且能等晚出现的图标、默认邀请被接受不置位、队长锁队不代替队员自己观察、先当过队长的账号不重复观察、已锁队准备页先等约 3 秒仍会点准备、等待期间自动进战斗则不点、未确认时立即点（原行为）、非契灵配置的准备行为不变、只有契灵使用 `team_battle_config` 且四个入口全部使用、公共邀请 / 战斗代码不设置该标志。变异 10 条各有测试变红。`test_bondling_fairyland_member_limit_count.py` 的夹具调整：`battle_config` 由 `object()` 改为真实 `BattleConfig()`，并把 `confirm_team_locked` 替身为未确认（该文件只关心次数收尾），断言不变。

### 验证
- 3232/3232 OK（首轮全量）
- **未验证（全部待真机）**：已锁队 + 默认邀请后自动准备时，是否还会发生误点准备（实际误点的画面没捕获）；队员页面能否看到锁定图标（`I_BF_LOCK` / `I_BALL_LOCK` 在队员所处页面是否可见、6 秒窗口够不够）；约 3 秒自动准备等待对队员 / 队长真实流程的影响；游戏确实没有自动准备时超时后点准备的兜底。

## 2026-10-28 - 悬赏封印适配新详情界面（D044）

### 核查
- 10-28 15:49 oas1 / oas2 日志：`pre_work` 完成一键追踪 → 进探索页 → `find_wq` 读到 `0/8` → `open_wq_info` 点 `WQ_TEXT_ALL` 4 次 → 滑动 4 次 → `No unfinished wanted quest after scrolling 4 times, exit` → `next_run` 排到次日，任务被当成已完成。`log/error` 里最近两份是道馆 `GameTooManyClickError`，与悬赏无关；悬赏这次没有失败截图（正常退出）。
- 用户标注器抓图（`log/annotator/.../captures`）：新版详情是全屏卷轴，右下角「取消追踪 / 追踪」按钮、右上角红叉；离线匹配新旧模板、`I_CHECK_EXPLORATION`、`I_UI_BACK_RED`，数值见 `AI_CONTEXT` §4.147。`I_TRACE_TRUE` 与 `I_TRACE_DISABLE` 外观几乎一致（0.95）。

### 修改
- `tasks/WantedQuests/script_task.py`：详情判定改 `wq_detail_opened`（`I_TRACE_TRUE` / `I_TRACE_FALSE`，点击后新截图确认，超时后补一次）；详情打不开有界重试后抛 `GameStuckError`，不再滑列表；整行 OCR 解析 `parse_wq_row_text` + `read_wq_rows` / `build_wq_info`（返回 `WQRowReading`，区分 ok / filtered / failed / absent，行绑定各自前往按钮）；`read_ordered_wq_infos` 全失败换新截图重读后抛异常；4 处 `ui_click(I_TRACE_TRUE, I_TRACE_FALSE)` 换成有界 `cancel_wq_trace` + `skip_current_wq`；未解锁判断改连续 3 帧确认。资源（`wq/ocr.json` / `image.json` / PNG / `assets.py`）保持用户标注原样。
- `docs/L2_CALLSITE_REGISTER.md` 重新生成，`tests/test_l2_c0_registry.py` 钉住数字同步（总数 1123 → 1121，rule 924 → 922，KEEP_IMMEDIATE 634 → 632）。

### 测试
- 新增 `tests/test_wanted_quests_detail_flow.py` 38 项（见 `AI_CONTEXT` §4.147）；离线图片匹配用本机标注器抓图，不在时 skip。

### 验证
- 全量结果见 `AI_CONTEXT` §7 基线。
- **未验证（全部待真机）**：取消追踪点击后详情是留下还是关闭、新整行 OCR 的真实识别质量、`GameStuckError` 重试的真实表现、`O_WQ_MONSTER_TYPE` 新 ROI。离线测试不证明真机可用。

## 2026-10-28 - 福利道馆 D-03：列表到底后仍不断滑动（滑动「是否推进」改看最终落点）

### 核查
- 10-28 oas1 20:40:20 预设结束后连续 `dokan_welfare_list_up`，20:40:42 `GameTooManyClickError`；`log/error/oas1_1793191242911/` 两张截图在 `LIST_BOX` 内逐像素相同（停在最后一张卡片「月浔」）。没有滑动过程中间帧，**不能证明这次事件全部由回弹造成**。
- 读源码确认的缺陷：`FrameStateDetector.changed` 锁存；`wait_for_changed_and_stable().success` = 曾变化 + 随后稳定；旧 `_swipe_list` 在 `success` 直接返回 `moved`；`_scan_list_once` 得到 `moved` 清零连续 static 计数。到底时的短暂回弹（最后回到原位）或角标闪动都会被当推进。

### 修改
- `tasks/Dokan/welfare.py`：`_swipe_list` 改为「滑动前独立拷贝基准帧 → `task.swipe`（返回 False → `not_sent`）→ `_settle_list` 等落点稳定并再取 3 帧确认不漂移 → `list_row_coverage(基准, 落点)` 判推进」；新增常量 `SWIPE_OBSERVE_TIMEOUT` / `SWIPE_HOLD_FRAMES` / `SWIPE_SEND_TRIES` / `LIST_CHANGED_THRESHOLD` / `LIST_STABLE_THRESHOLD` / `LIST_ROW_CHANGED` / `LIST_MOVED_ROW_COVERAGE`（后两者的取值依据见 `AI_CONTEXT` §4.148）；`_scan_list_once` 区分 `moved` / `static` / `not_sent`，连续两次实际发出的 static 才到底，`not_sent` 不计数、连续 3 次转人工；补了「没发出 / 落点稳定 / 推进判据 / static 连续计数 / 到底交刷新」的局部日志。`_refresh_list`、公共 `FrameWait` / `FrameStateDetector` / 滑动模型 / 重复操作保护、预设 / 建馆 / 集结 / Restart / 投票均未动。
- `tests/test_dokan_welfare.py`：测试替身 `World` 新增脚本化帧序列（`swipe_script`）与「没发出」（`unsent_swipes`），新增 `SwipeProgressTest` 20 项；新增 `tests/fixtures/dokan_welfare/list_box_oas1_20261028_204042.png`（报错截图 `LIST_BOX` 原始裁剪；回弹 / 滚动 / 角标闪动为合成帧序列）。
- 文档：`AI_CONTEXT` §4.148 / §7 基线、`DECISIONS` D040 ⑧ 措辞、`ROADMAP` 福利道馆 Level C 条目。

### 测试
- 先写测试、旧实现跑：`SwipeProgressTest` 9 条失败 + 8 条报错记录（含子用例）；修复后 `tests.test_dokan_welfare` + `tests.test_dokan_normal_mode` 116 项通过。
- 变异 3 条（`SWIPE_HOLD_FRAMES=0` / 推进线 0.95 / 推进线 0.2）均有测试变红。
- `toolkit/python.exe -m compileall -q tasks/Dokan/welfare.py tests/test_dokan_welfare.py` 通过；`toolkit/python.exe -m unittest discover -s tests` = 3290 项 OK（skipped=2，仅跑一次）。`git diff --check` 的告警全部来自此前已存在的未提交 `assets.py`（ActivityShikigami / SwitchSoul / DailyTrifles / Dokan / GameUi / WantedQuests），本轮改动的文件无告警。

### 未验证 / 未处理
- **D-04**（正常长列表连续滑动仍可能触发公共重复操作保护）本轮不处理；到底后刷新流程另有问题只记录。
- 推进阈值来自单张真实列表图 + 合成位移 / 噪声，未用真机中间帧校准；没有启动任何 OAS / MuMu / 游戏 / ADB / OCR，不是真实模拟器验证。

## 2026-10-28 - 福利道馆 D-04：有效翻页与公共重复操作保护的衔接

### 核查
- 调用链：`welfare._swipe_list` → `BaseTask.swipe` → `swipe_trajectory` → `Device.swipe_trajectory` 第一行 `handle_control_check(control_name)`（先 `click_record.append(str(name))`，再 `click_record_check()`），之后才真正滑动。`click_record` 为 `deque(maxlen=15)`，同名 >= 10 抛 `GameTooManyClickError`。**记录在滑动发出前写入并检查**，第 10 次滑动在 D-03 拿到结果之前就抛；10-28 oas1 History 有 10 条 `dokan_welfare_list_up`，`SwipeTrajectory` 日志只有 9 次，与此一致。
- 名字：`RuleSwipe.name = "dokan_welfare_list_up"`，记录的是 `str(control_name)`；`click_record_remove` 按 `str(button)` 匹配，`RuleSwipe` 无 `__str__`，必须传名字字符串。
- 结论：每次 moved 之后定向移除已足够，没有额外触发窗口（移除后下一次发出前最多只有未被清掉的 static + 1 条）。

### 修改
- `tasks/Dokan/welfare.py`：`_swipe_list` 判 moved 后调用新增 `_release_swipe_records()`（`click_record_remove(task.S_DOKAN_WELFARE_LIST_UP.name)` + 日志）；static 打日志保留记录。其余（D-03 判据 / 落点确认 / not_sent 上限 / 连续两次 static / 刷新 / 公共阈值）未动。
- `tests/test_dokan_welfare.py`：新增 `RecordGuard`（真实 `Device` 记录函数）与 `World(click_guard=True)`、`SwipeRecordTest` 17 项；`World.swipe` 加 400 次滑动的防失控上限。
- 文档：`AI_CONTEXT` §4.149 / §7 基线、`DECISIONS` D040 ⑨、`ROADMAP` 福利道馆条目。

### 测试
- 补丁前：`SwipeRecordTest` 17 项中 5 条失败 + 3 条报错（`GameTooManyClickError: dokan_welfare_list_up`）；补丁后 `tests.test_dokan_welfare` + `tests.test_dokan_normal_mode` 133 项通过。
- 变异 3 条（传 RuleSwipe 对象 / 清空整个记录 / static 也清）均有测试变红。
- `compileall -q tasks/Dokan/welfare.py tests/test_dokan_welfare.py` 通过；全量 `unittest discover -s tests`（只跑一次）= 3307 项运行 OK（skipped=2，首轮全量）。

### 未验证 / 未处理
- D-03 的 0.65 判据与比较区域仍待真实画面验证；真机未验证（未启动 OAS / MuMu / 游戏 / ADB / OCR）。
- 候选点击与取消详情记录在 15 条窗口内密集时可能触发「两个按钮」规则：仅观察，无日志证据，未改。
- 其他道馆 Bug 未处理。

## 2026-10-28 - 福利道馆 D-06：此前已预设过、不弹确认框时的一键预设

### 核查
- 旧 `_apply_preset`：`ui_click_until_appear_or_timeout(I_DOKAN_TEAM_PRESET, stop=I_UI_CONFIRM, interval=1.5, timeout=8)` 一直点预设等确认框，账号已预设过不弹框时约点 5 次后转人工退出。
- 点击契约：`appear_then_click(target, interval)` = `appear(interval)`（限流 + 识别）通过后执行点击并返回 `appear`，所以 True ⇔ 过了限流、识别到并真正点击；False 可能是限流或目标不在。`ui_click_*` 辅助函数在循环里重复调用它，不区分次数。
- 点击记录：预设按钮名 `res_dokan_team_preset`，最多 4 次，远低于公共阈值；本阶段不需要清记录。

### 修改
- `tasks/Dokan/welfare.py`：`_apply_preset` 改为「进阵容页（预设图标出现）→ `_click_preset()` → 确认仍在阵容页 → 返回找馆页 → 设 `preset_done`」；`_click_preset` 每帧先看确认框（优先），再按 `appear_then_click(interval=1.5)` 的真实返回值只数实际发出的点击，目标 2～4 次一次抽定，发满后观察 2 秒无框即完成；连续 3 帧既无框又无按钮 / 30 秒点不满 / 确认框关不掉转人工。新增常量 `PRESET_NO_DIALOG_CLICKS` / `PRESET_CLICK_INTERVAL` / `PRESET_OBSERVE_SECONDS` / `PRESET_TOTAL_TIMEOUT` / `PRESET_MISS_FRAMES`；日志改为「preset operation done（路径、点击数；效果未验证）」。
- `tests/test_dokan_welfare.py`：替身新增预设模式 / 限流 / 返回失败与虚拟时钟 interval 限流；`PresetFlowTest` 17 项取代旧的「无确认框 → 转人工」用例（旧口径已被用户改变）。
- `docs/L2_CALLSITE_REGISTER.md`：新增 1 个 `appear_then_click` 规则点，已用 `dev_tools.click_callsite_register --write` 重新生成。
- 文档：`AI_CONTEXT` §4.150 / §4.140 指针 / §7 基线、`DECISIONS` D040 ⑩、`ROADMAP` 福利道馆条目。

### 测试
- 修复前（旧 `_apply_preset` 补回在新用例上跑）：3 条失败 + 12 条报错记录（含子用例），集中在无确认框路径；修复后 `tests.test_dokan_welfare` + `tests.test_dokan_normal_mode` 149 项通过。
- 变异 4 条（限流调用也计数 / 每轮重抽目标 / 不观察就完成 / 取消「按钮缺失」有界保护）均有测试变红。
- `compileall -q tasks/Dokan/welfare.py tests/test_dokan_welfare.py` 通过；全量 `unittest discover -s tests`（只跑一次）= 3323 项运行，首轮全量 2 条登记册守卫失败（已重新生成登记册，相关 325 项复跑通过，未再跑第二遍全量；skipped=2）。首轮的 2 条失败是登记册守卫（新增了一个 `appear_then_click` 点击点，登记册未重新生成），`--write` 重新生成后这两项与相关 325 项通过。

### 未验证 / 未处理
- 真机未验证（未启动 OAS / MuMu / 游戏 / ADB / OCR）：有框 / 无框两条路径、2 秒观察是否覆盖弹框延迟、点 2～4 次的真实效果（程序不验证御魂 / 阵容）。
- 其他道馆 Bug 未处理；D-03 的 0.65 判据仍待真实画面验证。

## 2026-10-28 - 福利道馆 D-02：我方道馆未建立时遗漏建立流程（并落实 D-01 的一小部分）

### 核查
- 普通模式 `run_on_dokan_map` 在找目标前调 `ensure_dokan_created()`；福利模式直接进 `WelfareDokan`，没有调用。
- `ensure_dokan_created()` 点建立入口最多 2 次，两次都没出确认框就按「已建立」处理（点击无效也当已建立）；`creat_dokan()` 是无本地轮数上限的 `while True`，且忽略信息页关闭结果；返回 True 时没有「回到找馆页」的确认。
- 「建立道馆」入口两个模板（CREATE / HAVE）互相匹配分 0.96 > 默认阈值 0.8，默认阈值下分不出状态；用 `log/error` 里 4 张真实整屏截图量得本图标 0.996、另一个 0.956～0.96，取 0.98 区分。

### 修改
- `tasks/Dokan/script_task.py`：`ensure_dokan_created(strict=False)` / `creat_dokan(strict=False)` 新增默认关闭的 strict（默认路径未动）；新增 `own_dokan_state()`、`_ensure_dokan_created_strict()`、常量 `OWN_DOKAN_MARKER_THRESHOLD` / `OWN_DOKAN_STATE_TRIES` / `CREATE_DOKAN_MAX_ROUNDS`。
- `tasks/Dokan/welfare.py`：新增 `_ensure_own_dokan()`（strict 建馆检查 → 确认回到找馆页 → 设 `own_dokan_checked`），在 `_run` 里「机会 > 0」之后、预设之前调用一次。
- `tests/test_dokan_welfare.py`：替身新增建馆世界（`own` / `create_mode`）、图标高低阈值模型、虚拟时钟 `wait_until_appear`，绑定真实建馆方法；新增 `OwnDokanTest` 21、`OrdinaryCreateCompatTest` 5、`OwnDokanIconResourceTest` 3；`tests/test_dokan_normal_mode.py` 新增 `RunOnDokanMapTest` 4；新增样本 `tests/fixtures/dokan_welfare/own_dokan_icon_created_oas1_20261027.png` / `own_dokan_icon_uncreated_oas1_20261028.png`。
- `docs/L2_CALLSITE_REGISTER.md` 用工具重新生成（+2 点击点，1121 → 1123）；`tests/test_l2_c0_registry.py` 两条守卫的期望数字同步（总数 1123、KEEP_IMMEDIATE 634、rule 924）。
- 文档：`AI_CONTEXT` §4.151 / §4.140 指针 / §7 基线、`DEVELOP_LOG`、`DECISIONS` D040 ⑪、`ROADMAP` 福利道馆条目、`ARCHITECTURE` 福利道馆段（公共接口新增一条）。

### 测试
- 补丁前（福利入口不调建馆检查）新用例 29 项中 17 项红；补丁后 `tests.test_dokan_welfare`（156 项）+ `tests.test_dokan_normal_mode`（26 项）+ L1 / L2 / 登记册守卫相关共 511 项通过（登记册守卫的期望数字更新后复跑通过）。
- 变异 8 条均有测试变红（「忽略信息页关闭结果」首轮存活，补直接测公共方法返回值的用例后变红）。
- `compileall -q tasks/Dokan/script_task.py tasks/Dokan/welfare.py tests/test_dokan_welfare.py tests/test_dokan_normal_mode.py` 通过；全量 `unittest discover -s tests`（只跑一次，跑前确认没有其他 unittest 进程）= 3356 项运行 OK（skipped=2）。

### 未验证 / 未处理
- 真机未验证（未启动 OAS / MuMu / 游戏 / ADB / OCR）：「已建立」时不点击直接继续（真实游戏里点灰色锣是否会弹窗未知）；0.98 阈值仅 2 个场景 4 张截图；建立后图标变化与延迟；建立流程真实耗时。
- 其他道馆 Bug（集结等待 / Restart / 投票 / 刷新、D-01 其余部分）未处理。

## 2026-10-29 - 福利道馆 D-05：正常集结等待被公共无操作保护判成卡死

### 核查
- `Device.screenshot()` 每次先 `stuck_record_check()`；`stuck_timer`（60 秒 + 60 次检查）/ `stuck_timer_long`（300 秒 + 300 次检查）距最近一次 `stuck_record_clear`（点击、`app_start` / `app_stop`）计时；登记 `PAUSE` 等只把 60 秒延到 300 秒，300 秒到点一定抛。
- 旧 `_enter_prepare_and_close` 集结期间只截图 + `sleep(1)`，没有点击也没有保活；10-27 oas2 日志 20:40:34 `dokan opened` → 20:41:33 `Wait too long` / `Waiting for set()`，`detect_record` 为空，符合「正常集结撞上公共保护」而不是游戏卡死。
- 普通道馆 `run_on_dokan`：识别到道馆页后每轮 `stuck_record_clear()`，集结分支再 `click_record_clear()`；助威用 `stuck_record_clear()` + `stuck_record_add('PAUSE')`。

### 修改
- `tasks/Dokan/welfare.py`：`_enter_prepare_and_close` 改为「集结页（道馆页 + 集结中）证据才清一次公共卡死计时；业务总时限进入阶段时算一次不重置；可开始挑战的帧不清计时、点击次数上限 5 + 观察 3 秒；未知 / 过渡画面不清计时、容忍 30 秒（< 公共 60 秒）；不登记特殊等待状态、不捕获异常」；点准备 → `app_stop` 紧邻不变。新增常量 `GATHER_UNKNOWN_TOLERANCE` / `GATHER_START_CLICK_LIMIT` / `GATHER_START_OBSERVE` / `GATHER_LOG_INTERVAL`；新增阶段日志。公共 Device / 阈值未动。
- `tests/test_dokan_welfare.py`：替身新增 `stuck_guard`（真实 `Device` 卡死检查 + 真实 `Timer` 取虚拟时钟）、`transition` / `start_mode`；新增 `GatherGuardTest` 17 项。
- 文档：`AI_CONTEXT` §4.152 / §4.140 指针 / §7 基线、`DEVELOP_LOG`、`DECISIONS` D040 ⑫、`ROADMAP` 福利道馆条目。

### 测试
- 补丁前（旧循环原样补回在新用例上跑）17 项中 13 项失败，全部是公共 `GameStuckError: Wait too long`（整条流程那条被转成 `RequestHumanTakeover`，信息含 `GameStuckError`）；补丁后 17 项通过。
- 变异 8 条均有测试变红（「未知分支清」首轮存活，已收紧断言）。
- `compileall -q tasks/Dokan/welfare.py tests/test_dokan_welfare.py` 通过；点击登记册重新生成无差异。
- 全量 `unittest discover -s tests` 误跑了两次：第一次 3373 项、2 失败，第二次 3384 项、3 失败（`test_daily_pickup_email` 两项 + 登记册守卫一项），期间其他会话在改 `DailyTrifles` / `Restart` 资源（测试数 3373 → 3384），失败与本轮无关；本轮范围 238 项与 `test_daily_pickup_email` + `test_daily_trifles` 70 项在当前工作区复跑通过，未再跑第三遍全量。

### 未验证 / 未处理
- 真机未验证（未启动 OAS / MuMu / 游戏 / ADB / OCR）：集结页证据在真实集结全程是否稳定；集结结束到开始挑战之间的过渡是否超过 30 秒；馆主战等待这类「道馆页但既无集结也无开始挑战」的状态目前按未知处理；真实 > 5 分钟集结与点准备后立即关闭。
- 其他道馆 Bug（Restart / 投票 / 刷新、D-01 其余部分）未处理。

## 2026-10-29 - 每日琐事领取邮件：邮箱已打开后不再点顶栏信封

### 核查
- 日志 `log/2026-10-29_oas2.txt` 09:49:25~09:49:40：`DT_HARVEST_MAIL_COPY2` 与 `DT_HARVEST_MAIL_ALL` 各 6 次交替，现场截图邮箱已打开；10-28 正常那次 `ALL` 在信封点击后约 1.6 秒，失败那次约 0.9 秒。
- 模板匹配（本地 OpenCV，不启动服务）：旧标题区域 (520,48) 匹配度 0.33，放宽搜索在 y=58 为 0.942（旧标注偏 10 像素）；`I_SYSTEM_MAIL_OPEN` 0.995；用户重新标注后两者在现场截图上 1.0，其它 28 张错误截图最高 0.267 / 0.453。

### 修改
- **事故**：10-29 oas2 09:49 `DailyTrifles` 领取邮件时 `GameTooManyClickError: Too many click between 2 buttons: DT_HARVEST_MAIL_COPY2, DT_HARVEST_MAIL_ALL`，保存 `log/error/oas2_1793238580881`，重启后 09:50 重跑正常。现场截图：邮箱已打开、有未读邮件，顶栏信封图标仍露在边框上方。**直接原因**：旧 `run_pickup_email` 里 `COPY2`（顶栏信封）优先级最高、每 1.2 秒识别到就点一次，邮箱打开后照样匹配，和「一键领取」各点 6 次触发点击守卫；失败那次 `ALL` 每次都在信封点击后约 0.9 秒才点（平常约 1.6 秒），6 次都没出现确认弹窗，推测是点得太早、展开动画期间被游戏忽略（没有点击瞬间的画面，只是推测）。旧流程另有两处问题：没有「已在邮箱」判断；从没进过邮箱也照样记今天已完成。**邮箱已打开的标志**：`RestartAssets.I_HARVEST_MAIL_TITLE`（「邮箱」标题）与 `I_SYSTEM_MAIL_OPEN`（「系统邮件」标签打开状态）**任一出现**即在邮箱页面（用户已按当前界面重新标注；在现场截图上匹配度 1.0，另 28 张其它页面截图最高约 0.45，阈值 0.8；标题旧区域偏了约 10 像素，现为 y=58）。**新流程**（`tasks/DailyTrifles/script_task.py`，新增 `_in_mailbox()`，资源仍放在 Restart 任务里、DailyTrifles 引用 `RestartAssets`）：领取确认 / 奖励弹窗优先（弹窗会盖住标志）→ 已在邮箱：点「一键领取」（点了 `PICKUP_ALL_TRIES=6` 次都没出现确认弹窗就放弃）、「一键已读」不重置空闲计时，邮箱里没有可操作按钮持续 `PICKUP_IDLE=3` 秒算领完 → 还没进邮箱：才点「打开邮箱」按钮（COPY2 / MAIL / MAIL_COPY，间隔 ≥ `PICKUP_OPEN_GAP=3` 秒，最多 `PICKUP_OPEN_TRIES=3` 次）。总时限 `PICKUP_TIMEOUT=60` 秒。**只有真的进过邮箱且没有放弃才记今天已完成**；邮箱没打开 / 一键领取始终无效 / 超时都只记 warning、不记完成（下次运行再试），不再静默跳过一天。点击策略、`interval` 和 L2 policy 与原来一致（6 个点位不变）。

### 测试
- **验证**：全量 3384 项 OK（2 项 skipped，首轮全量；工作区同时有其它会话的改动，差额未逐项归因）。基线行（§7）由并行会话维护，这里不改。**测试**：新增 `tests/test_daily_pickup_email.py` 11 项（假画面 + 真实 Timer，常量缩小）：邮箱已打开且顶栏信封仍可见时不点任何打开按钮、标题 / 系统邮件标签任一出现即可、弹窗盖住标志时只点确认、一键已读常驻不让循环不结束、关着的邮箱只打开一次且之后不再点信封、邮箱始终打不开有界重试且不记完成、点击间隔、一键领取无效有界放弃且不记完成、连续两个确认弹窗、policy 与常量、同天二次运行跳过。变异 9 条各有测试变红。`tests/test_daily_trifles.py` 的 `PickupEmailTest` 夹具调整：点「打开邮箱」按钮后出现邮箱标题（原先没有邮箱标志也会记完成），常量缩小，断言不变。登记册重新生成，总数不变（1123）。

### 验证
- 全量 3384 项 OK（2 项 skipped，首轮全量；工作区同时有其它会话的改动，差额未逐项归因）
- **未验证（全部待真机）**：重新标注后的两个标志在真机各种情形下的识别（只有一张邮箱打开的截图，没有「特别邮件」标签被选中时的样本，那种情况 `I_SYSTEM_MAIL_OPEN` 不会命中，标题标志是否仍命中待确认）；`ALL` 在邮箱展开动画期间被忽略的推测；`PICKUP_*` 常量是否合适；邮箱里没有可领取邮件时（一键领取灰掉）是否按预期 3 秒后结束。Restart 任务也在用这两个标志，其资源已被重新标注，Restart 侧未改动也未验证。

## 2026-10-29 - D-07：异常请求的 Restart 被「调度器启动时跳过首次 Restart」吞掉

### 核查
- 跳过规则在 `Script.loop`：`is_first_task and task == 'Restart'` → 跳过。`is_first_task` 只在 `__init__`（True）、`_loop_note_recovery`（有活动循环时 False）、任务 `run` 结束处（False）改变。
- 异常请求：`_handle_task_exception` 五个恢复分支 → `config.task_call('Restart')`（`next_run=now` + `save()`），下一轮重载配置后被选中。
- 10-27 oas2：`log/2026-10-27_api.txt` 里 `20:38:21 ws[oas2] msg: stop`、`20:39:19 msg: start`——用户在异常处理的 10 秒等待期间点了停止再启动；`ScriptProcess.stop()` 终止进程、`start()` 新建进程并 `Script(config)`，所以 `START` / `Start scheduler loop` 是新进程，落盘的 `Restart next_run=20:38:16` 被新进程按启动规则跳过（按设计，跨进程无法区分）。10-28 oas1：同进程内 `Task call: restart` → 10 秒后 `Start task Restart`，正常执行。
- 真实的进程内缺陷：首个任务**准备阶段**抛可恢复异常时 `is_first_task` 仍为 True，刚请求的 Restart 被当成启动时的 Restart 跳过；任务运行中的异常不受影响。
- 其他会话（DailyTrifles / Restart 资源）与 `script.py` / `config.py` 无重叠，基线哈希未变；御魂循环的局部修复只覆盖有活动循环的情形。

### 修改
- `script.py`：新增 `_request_restart_recovery()`（循环登记 → `task_call('Restart')` → 登记成功才 `is_first_task=False`），替换 `_handle_task_exception` 里四处「`_loop_note_recovery()` + `task_call('Restart')`」。
- `tests/test_restart_recovery_first_task.py`（新增，13 项）：真实 `Script.loop` / `run` / `_handle_task_exception`、真实 `Config.task_call` 与调度选择。
- 文档：`AI_CONTEXT` §4.153 / §7 基线、`DEVELOP_LOG`、`DECISIONS` D045、`ROADMAP` 福利道馆条目、`ARCHITECTURE` 调用方向一句。

### 测试
- 补丁前 13 项中 3 项失败（11 个断言 / 子用例：准备阶段异常 Restart 被跳过 5、登记后状态 5、重新进入调度 1），其余 10 项本来就通过；补丁后 13 项通过。变异 3 条均变红；「跳过循环登记」由既有 `test_loop_script_glue` 3 项变红覆盖。
- `compileall -q script.py tests/test_restart_recovery_first_task.py` 通过；相关 501 项通过；全量 `unittest discover -s tests` 只跑一次：3397 项 OK（skipped=2），开始前后工作区无变化；完整输出在 `D:\Codex\workspace\d07\`。

### 未验证 / 未处理
- 跨进程（GUI 停止 → 启动）后遗留的异常请求仍按启动规则跳过；要区分需要持久化标记，本轮按要求没做，待用户决定。
- 准备阶段异常反复出现时的 Restart 循环不计入 `failure_record`（现有行为，未改）。
- 投票、刷新、D-01 其余部分未处理；真机未验证。

## 2026-10-29 - 领取邮件第二版：邮箱状态粘性 + 弹窗取消 + 点关闭叉退出

### 修改
- **补记（2026-10-29 第二版，按用户反馈改）**：领取后会弹「是否立即启用"…插画"？」（取消 / 确定）、获得插画、获得头像框等弹窗和全屏页，原先都靠最后的 `goto_page` 兜底关闭，而且会盖住邮箱标志。本地用现有模板对三张用户截图做匹配（OpenCV，不启动服务）：启用确认的大号 `I_UI_CANCEL` / `I_UI_CONFIRM` 都是 1.0；红色关闭叉 `I_UI_BACK_RED` 在启用确认 0.87、头像框 0.966、邮箱自己的叉 0.918；获得插画没有任何现有模板能识别。**改动**（`run_pickup_email`）：① **进过邮箱就一直算在邮箱流程里，直到自己点了退出**——看不到邮箱标志不再当成离开邮箱（不再点「打开邮箱」按钮）；② 弹窗：两个大按钮同时出现 → **只点取消、从不点确定**（`_pickup_popup`，policy CONFIRM）；看不到邮箱标志时的红色关闭叉（头像框等全屏页）→ 点（NAVIGATION）；③ 一键领取不再出现持续 3 秒算领完，**然后点邮箱自己的关闭叉退出**（最多等 `PICKUP_EXIT_TIMEOUT=6` 秒，退不出由 `goto_page` 兜底）；④ 进过邮箱却一直看不到标志（未知弹窗）最多等 `PICKUP_LOST_TIMEOUT=10` 秒后走兜底；⑤ 记今天已完成的条件改为「领完，或点过一键领取 / 确认弹窗」且没有放弃。**获得插画尚未处理**：等用户标注「获得插画」标题模板后，在无标志时点安全空白处关闭；在那之前它会等到 10 秒兜底。测试：`test_daily_pickup_email` 11 → 20 项（粘性邮箱状态、取消不确认、孤立的取消 / 确定按钮不当弹窗、全屏页关闭叉、领完才点邮箱关闭叉、未知弹窗有界兜底、没领取不记完成），变异 8 条各有测试变红；登记册 +3 个 policy 点（1123 → 1126，policy 97 → 100，DailyTrifles 42 → 45，`POST_C1_CONSUMERS` 逐点登记）。全量验证（如实记录，不挑结果）：首轮全量 3406 项、1 项失败——我之前写的 SwitchSoul 小步幅测试里一条依赖随机步幅的断言 `test_a_target_first_seen_clipped_at_the_bottom_is_found_after_the_next_swipe`，已改为固定 100px 步幅（确定性），该模块连续 3 次通过；修复后第二次全量 3437 项、4 项失败：`test_dokan_welfare` 3 项 + `test_l2_c0_registry` 的「生成结果与已提交 markdown 一致」1 项，全部来自并行会话正在改的福利道馆（`WelfareDokan._refresh_list` 等点位的等待标记与登记册不一致，登记册已不是最新），与本轮领取邮件无关，我没有去改福利道馆或替对方重新生成登记册；本轮相关的 `test_daily_pickup_email` + `test_daily_trifles` 79 项、SwitchSoul 名称搜索 61 项、点击登记册 / L1·L2 守卫 184 项当前工作区单独运行通过。

## 2026-10-29 - 福利道馆 D-09：刷新闭环；D-08 候选去重核查；候选双按钮保护

### 核查
- 普通刷新：`ui_click(C_DOKAN_REFRESH, I_REFRESH_ENSURE)` + 无超时 `ui_click_until_disappear` + 睡 3 秒，受 `find_dokan_refresh_count` 限制，不确认列表、不回顶。旧 `_refresh_list` 成功 = 确认框消失 + 睡 1 秒；`I_REFRESH_ENSURE` 是整屏「确认」模板，不能证明刷新生效。`log/` 里没有任何一次真实刷新，仓库里没有向上回顶的滑动资源：刷新后是否回顶没有证据。
- 批次状态 `checked` 是 `_scan_list_once` 的局部变量，每批重建（生命周期没有问题）。
- 指纹（真实卡片 A / B，`D:\Codex\workspace\d09\fp_real_out.txt`）：同一张卡偏 1 px ≈ 5.2、偏 2 px ≈ 10.1，改一行文字（4 px）整体差只有 ≈ 1.7、改 12 px ≈ 4.5，两张真实不同卡片 ≈ 8.78；旧判据（整体平均差 < 6）既会把同一张判成不同、也会把差一行文字的不同卡片判成同一张。
- 真实 `Device` 记录逻辑复现：一批里检查 6 个候选就触发「两个按钮」`GameTooManyClickError`。

### 修改
- `tasks/Dokan/welfare.py`：`_refresh_list` 改为有界点击 + `_await_refreshed_list`（回到找馆页 → 列表停稳 → 与刷新前比较变化行占比，最多 3 轮，不变转人工）；新增 `_scroll_list_to_top`（反向滑动，复用 D-03 判据，连续 2 次 static 才算在顶）、`_list_down_rule`；`_swipe_list(rule)` / `_release_swipe_records(name)` 支持指定滑动；指纹改为 ±2 px 对齐 + 分带 + 屏蔽徽记（`CardFingerprint`、`card_distance`）；候选详情关闭后按「有效结论」释放候选 / 取消两类记录（`_release_candidate_records`）；`RELOCATE_LIMIT`。
- `tests/test_dokan_welfare.py`：替身刷新模型 / 选中高亮 / 反向滑动 / 真实资源名与记录；新增 `RefreshClosureTest` 17、`CandidateRecordTest` 8、`CardIdentityTest` 6；两条既有用例改了前提（见 AI_CONTEXT §4.154）；新增 2 张真实样本。
- `docs/L2_CALLSITE_REGISTER.md`：重新生成，仅福利两行「上下文」列变化。
- 文档：`AI_CONTEXT` §4.154 / §7、`DEVELOP_LOG`、`DECISIONS` D046、`ROADMAP` 福利道馆条目。

### 测试
- 还原旧行为后新用例 31 项中 16 项失败，单独还原各项各有用例变红；变异 2 条变红；修复后 31 项通过。
- `compileall -q tasks/Dokan/welfare.py tests/test_dokan_welfare.py` 通过；相关 415 项（福利 / 普通模式 / D-07 / 登记册与 L1·L2 守卫）通过；完整输出保存在 `D:\Codex\workspace\d09\`。
- 全量结果：见本条末尾「全量」小节。

### 未验证 / 未处理
- 真机：刷新后是否回顶、反向滑动方向 / 幅度、`REFRESH_CHANGED_COVERAGE` 0.05 的取值、加载态画面、刷新限制的专门提示；指纹阈值的真实样本很少。
- 投票、D-01 其余部分、准备阶段反复失败不计入 `failure_record`、跨进程遗留 Restart（D-07 边界）。

### 全量
- `toolkit/python.exe -m unittest discover -s tests` 只跑一次：**3437 项运行 OK（skipped=2）**，2026-10-29 11:36:44 开始、11:42:09 结束；开始前确认没有其他 unittest 进程，开始前后 `git status` 条目数（189）与 `welfare.py` / `test_dokan_welfare.py` / `L2_CALLSITE_REGISTER.md` / `script.py` 哈希均不变，其他会话（DailyTrifles 领取邮件）此前已约 18 分钟没有代码改动；结果适用于运行时刻的工作区快照。完整输出：`D:\Codex\workspace\d09
ull_suite.txt`。
- **第三版补记（2026-10-29，用户已标注 `I_GET_PICTURE` 并追问风险）**：① **获得插画**：`DailyTriflesAssets.I_GET_PICTURE`（标题模板）在用户截图上匹配度 0.988，其它截图最高 0.177；识别到就点安全空白处（`random_click()` 的 SAFE_RANDOM_CLICK，policy NORMAL，间隔 1.5 秒）。② **有界性补强**：每种弹窗 / 关闭叉最多点 `PICKUP_POPUP_TRIES=5` 次，点了不消失就放弃（不记完成），避免触发点击守卫（同名 ≥10 次）；看到主界面标志 `I_CHECK_MAIN` 说明邮箱已被关掉，立即离开而不是等 10 秒；**打开邮箱之前**出现的「确定」不再让 `opened` / `claimed` 置位（只有邮箱标志才置位，防止主界面别的对话框碰巧也有「确定」时被误记为领完）。③ 对其他任务的影响：`_pickup_popup`（取消 / 获得插画）只在 `run_pickup_email` 里、且进过邮箱之后才调用，没有改公共的 GameUi / GlobalGame 处理和 `I_UI_CANCEL` / `I_UI_CONFIRM` 资源，其它任务不受影响。测试 `test_daily_pickup_email` 25 项，变异 6 条各有测试变红；登记册 +1 个 policy 点（1127，policy 101，DailyTrifles 46）。全量：本版全量 3442 项、1 项失败——`test_swipe_endpoint_sampling.WideRoiPassthroughTest.test_both_wide_output_distribution_matches_legacy_coord`（均值差 3.157 > delta 3.0，15000 样本无种子的统计性用例，此前已记录其约 1% 量级的偶发概率；单独重跑 12 次全过，未改阈值、未改公共随机模型）；其余全部通过（上一轮失败的福利道馆 3 项与登记册一致性已不再失败）。

## 2026-10-29 - 每日琐事调度：日常锚点 + 12 / 20 点时段点（D047）

### 核查
- 配置：oas1 / oas2 `scheduler.server_update = 09:00`、`float_time = 1:10 / 1:05`、`success_interval = 1 天`、优先级 4；日志里下次运行落在 12:00–13:10 / 20:00–21:10。
- 「每天早上第一次先跑」靠的是日志里 DailyTrifles 的 next_run 被改成「当前时间减一天」（每天 09:13~09:50），后端里没找到来源，不能依赖。

### 修改
- **需求**（用户）：每天开 OAS 时每日琐事要最先能跑（正常调度）；12 点、20 点庭院寿司时段仍各跑一次，都带随机延迟；晚上庭院事务跟日常调度、到点没做就补；优先级和随机延迟（`float_time`）由用户自己配置。**原来的问题**：`plan_next_dt` 每次正常结束都把 next_run 整个改成 12:00 / 20:00 / 次日 12:00（`custom_next_run`，`server=True`），配置的 `success_interval` 完全没用上；「每天早上先跑」靠的是一个没找到来源的机制（日志里每天 09:13~09:50 DailyTrifles 的 next_run 被改成「当前时间减一天」，Restart `enable_daily`、队伍同步 `task_call`、XinLan 都不会这么改），不能当作保证。另外 `custom_next_run` 默认 `server=True`：公共 `task_delay` 只在 `server_update` 恰为 09:00 时才加随机延迟，换成别的值会把目标推到明天。**新规则**（`tasks/DailyTrifles/script_task.py`）：下次运行 = `next_daily_time`（下一个服务器刷新 `scheduler.server_update`，默认 09:00；此刻已到或已过则明天）与 `next_slot_time`（今天 12:00 / 20:00，过了 20:00 是明天 12:00）中较早的一个，再加任务自己的 `float_time` 随机延迟（`random_int(0, float_time 秒数)`，只加一次）；以 `server=False` 交给 `set_next_run`，不受 `server_update` 影响。效果：每天 09:00（+延迟）一次、12:00（+延迟）一次、20:00（+延迟）一次；开 OAS 时 09:00 通常已过，每日琐事立刻到点。**不用「成功时间 + success_interval」**：12 / 20 点的运行会拖动锚点，随机延迟累计后每天往后漂，且取较早者时 12 / 20 点总是先到，等于现状。`run()` 本身不分模式：各功能已有「今天做过没有 / 当前时段」判断，三种触发共用；晚上庭院事务由 20:xx 那次运行按当前时段（≥18:00 = evening）去做，没做到就在下一次到点时补。**不变**：失败路径（异常不调用 `plan_next_dt`，Restart 后立刻重试，连续 3 次退出）、各功能逻辑、优先级（用户自己调）。

### 测试
- **测试**：新增 `tests/test_daily_schedule.py` 9 项（真实 `BaseTask.set_next_run` → 真实 `Config.task_delay`）：连续 7 次按排好的时间运行得到 12:00 / 20:00 / 次日 09:00 / 12:00 / 20:00 / 09:00 / 12:00；随机延迟范围与确实随机、只加一次；`server_update` 改成 05:00 时时段点不被推到明天、日常锚点跟着配置；09:00 整点之后的下一个刷新是明天；时段点边界；不使用 `success_interval`；早上那次实际 10:10 才跑也不影响之后的排期。变异 6 条各有测试变红（取较晚者 / 日常总是明天 / `server=True` / 不加延迟 / 20 点后排今天 / 把 `success_interval` 算进去）。`tests/test_daily_trifles.py` 里旧的 `plan_next_dt` 用例改成新契约（旧断言是 `custom_next_run` 的 12 / 20 点参数）。{BASELINE}

### 验证
- 全量 3451 项 OK（2 项 skipped，首轮全量，一次通过；工作区同时有其它会话的改动，数量差额未逐项归因）。
- **未验证（全部待真机）**：开 OAS 后每日琐事是否最先（优先级由你配置，现在是 4，前面还有 Restart / 结界等）；09:00 + 随机延迟那次运行与 12 点那次的间隔；晚上庭院事务在 20:xx 那次运行里是否按 evening 时段正常做；随机延迟你配得过大时（如 1 小时多）仍可能把寿司时段（12–14 / 20–22）挤出去，这是配置问题，代码不再限制。

## 2026-10-29 - 福利道馆：再战之后若仍停在道馆页，复用现有退出导航回到地图（定点修复 A）

### 核查
- 用户 10-25 标注器截图（原文件已不在磁盘，内嵌在会话记录里）离线匹配：道馆页黄色返回键 0.389、`I_RYOU_DOKAN_DOKAN_QUIT` 0.993；地图页相反。旧 `_back_to_find_page` 只点黄色返回键，停在道馆页就离不开。再战后停在哪一页没有证据。
- `Navigator.goto_page(timeout)` 是无进展超时（页面变化 / 转场推进会重置，到点抛 `GamePageUnknownError`），外层 deadline 中断不了它。

### 修改
- `tasks/Dokan/welfare.py`：`_back_to_find_page(timeout, leave_dokan_page=False)`，`_run` 里再战等待之后传 True；看到 `I_RYOU_DOKAN_CHECK` 时调用现有 `goto_page(page_dokan_map, timeout=剩余时间)`，返回后重新截图判断；导航次数上限 `DOKAN_EXIT_TRIES`（2）。预设返回和默认调用不变。
- `tests/test_dokan_welfare.py`：复用另一个并行会话已加的道馆页停留 / 退出确认替身，追加 `RematchReturnTest` 15 项。
- 文档：`AI_CONTEXT` §4.156 / §7、`DEVELOP_LOG`、`DECISIONS` D048、`ROADMAP`；点击登记册重新生成无差异。

### 测试
- 还原旧实现 15 项中 12 项失败；变异 4 条变红；修复后通过。
- `compileall` 通过；相关 351 项通过；全量一次 3466 项 OK（skipped=2），开始前后工作区无变化；完整输出在 `D:\Codex\workspace\d10\`。

### 未验证 / 未处理
- 再战之后实际停在哪一页、退出确认框真实样子、导航耗时；最后一馆放弃后的收尾（B）待画面。

## 2026-10-29 - 福利道馆：再战成功后的 120 秒等待与公共卡死保护衔接

### 核查
- 调用顺序（当前源码）：`_abandon` → `_vote_again()`（点击再战，之后逐帧截图等「变化并稳定」，最多 8 秒）→ `_wait_again()`（`_wait(120)`，无截图）→ `_back_to_find_page()` 首次 `screenshot()`。
- `Device.screenshot()` 先 `stuck_record_check()`：`stuck_timer = Timer(60, count=60)`，`reached()` 每次检查 +1 计数，要求「距最近一次清除超过 60 秒」且「检查次数 > 60」。再战点击清计时和计数；120 秒后时间条件满足；投票确认阶段帧数不固定（截图间隔 0.1～0.3 秒），> 60 帧时等待后的第一次截图会误报。
- 用户确认：两馆都放弃，仅第一馆再战并等 120 秒；最后一馆放弃后不会出现再战；首次找馆 / 第二馆首批回顶不处理。

### 修改
- `tasks/Dokan/welfare.py::_wait_again`：`_wait(120)` 正常结束之后调用一次 `device.stuck_record_clear()`（不动点击记录、不改阈值、不在 finally、不进离线排除）。
- `tests/test_dokan_welfare.py`：替身 `snap_step` / `vote_change_delay`；新增 `AgainWaitGuardTest` 11 项（真实 `Device` stuck 检查 + 真实 `Timer`）。
- 文档：`AI_CONTEXT` §4.157 / §7、`DEVELOP_LOG`、`DECISIONS` D049、`ROADMAP`。点击登记册重新生成无差异。

### 测试
- 修复前新用例 11 项中 5 项失败（等待后第一次截图 `GameStuckError: Wait too long`，整条流程被转成人工）；变异 5 条变红；修复后通过。
- `compileall` 通过；相关 362 项通过；全量一次 3477 项 OK（skipped=2），开始前后工作区无变化；完整输出在 `D:\Codex\workspace\d10\`。

### 未验证 / 未处理
- 真机：真实截图间隔与投票确认帧数；其余福利待真机项见 ROADMAP。

## 2026-10-29 - 发布前审查：整理累积改动并推送 origin/master

### 范围
- 推送目标：`master` → `origin/master`（Hualaijushi，用户自己的仓库，普通快进；审查期间 `origin/master` 一直是 `8a82cb8f`）；`upstream`（xylolit-mu）只作参考，不推送。没有进行中的 merge / cherry-pick / rebase，暂存区原本为空。
- 审查对象：未推送的 6 个百鬼棋局提交（§4.134；三个上游 cherry-pick 的 `(cherry picked from ...)` 来源行齐全）+ 工作区 119 个已跟踪改动 + 89 个未跟踪文件（§4.110 ~ §4.157 与领取邮件）。
- 改动前基线：`D:\Codex\workspace\oas-release-review-20261029`（分支 / HEAD / 远端 / 待推送清单、工作区与暂存区二进制 diff、未跟踪文件 tar 与哈希、本轮改动文件的原件与哈希、纳入 / 排除清单、验证输出）。
- 读的代码：`script.py` 全部新增（组队会合、循环会合、D-07 恢复登记、防沉迷活跃时长扣除）、`module/script/loop_controller.py`、`module/script/team_sync.py`、`module/config/config.py` 调度钩子、`module/server/script_process.py` 停止通知、`module/device/*`、`module/fatigue.py`、`tasks/base_task.py` 的 L2 `policy` 透传、GeneralBattle / GeneralInvite / GeneralRoom、SwitchSoul（数字模式确认顺序、契灵替换框）、Dokan 普通模式与 `welfare.py` 的开馆 / 等待 / 投票段、DailyTrifles 调度、WantedQuests、Orochi、RealmRaid、AreaBoss、Secret、BondlingFairyland、Hunt、ActivityShikigami 的区间与异常延后；资源 json 与模板尺寸逐条核对（脚本在审查目录外的临时区）。

### 审查发现与处理
- **GlobalGame 好友邀请资源（未提交，留在工作区）**：用户 10-28 用 annotator 重标、没有开发记录；`g_cat_food` / `g_dog_food` 的识别框改成与勾玉相同的 (675,516,43,46)，模板图仍是 59×65 / 60×63。图像服务在模板大于搜索区时直接返回不命中（`module/image/runtime.py` `_template_match_image`），「接受勾协和粮协」时粮协邀请永远被当成其它邀请忽略。直接证据：json / assets.py 与 png 尺寸；推断：新界面上粮食图标的位置——没有截图，不能代为修。两个实例当前都是「忽略」，不受影响；发布里没有任何代码 / 测试依赖这 6 个文件，整组留在工作区，ROADMAP 记待办。
- **4 张没有规则引用的图不提交**：`climb_item_13.png`、`ui_ui_reward_1.png`（都与已引用的图逐字节相同）、`res_dokan_enter_again.png`（废稿）、`page_num_tongxin.png`（孤儿）。用户 10-20 重截的 ActivityShikigami 模板随 §4.110 提交：重新生成的 json / assets.py 的识别框是按新图标的。
- **`docs/AI_CONTEXT.md` 两个 §4.153**：领取邮件改为 §4.158；并行会话把领取邮件第二版 / 第三版补记分别写进了 D-07 / D-09 节末，移回 §4.158；D-09 节里的说明与 ROADMAP 的引用同步。D-07 保持 §4.153（本文件已有条目引用它）。
- **一处第三方好友的游戏昵称**（AI_CONTEXT §4.117、本文件 2026-10-24 条目）改成「另一位好友（非对端）」，事实不变；两处此前都没推送过。
- **`tasks/Dokan/welfare.py` `_vote_again`**：`still_voting` 那一行丢了换行（`or` 后面接着十几个空格），补回续行，行为不变。
- **AI_CONTEXT §8 时钟依赖用例**：§4.120 已固定时钟，原文仍写「未改」，改为已解决。
- 没有问题、不改的结论：组队会合 / 循环在 `script.py` 里的新调用都自带异常兜底（`TeamSync` 各入口吞异常放行；调度钩子 `try/except` 回退原排期；`_loop_prepare_schedule` 有 `try`），组队同步没开、循环没有一次性请求时全部是空操作；Orochi / RealmRaid 的新分支只在有组队会话或循环控制器时生效；SwitchSoul 数字模式先确认原确认框消失再观察契灵替换框；GeneralBattle 只在识别到失败横幅时改点右侧 / 底部区；WantedQuests 把识别失败（抛异常）与按规则过滤（取消追踪）分开；AreaBoss 只对明确战败重试；ActivityShikigami 旧配置缺 `ap_limit_max` 时按 N～N 读入；`config/template.json` 新字段都是关闭 / 空值；5 张测试夹具与同心之兰模板只有界面和其它寮的公开名字，没有本方账号信息；候选内容里没有 token / 密码 / 密钥 / 通知地址 / 邮箱。
- 发现但不属于本次范围（HEAD 就有）：`module/server/script_router.py` 里改名 / 删除 / `/{script}/stop` 三处调用异步的 `ScriptProcess.stop()` 没有 `await`；Dokan `ryou_dokan_fighting` 模板比识别框宽；SwitchSoul `click.json` 的 `sou_team_select` 指向不存在的图。都没改。

### 验证
- 改 `welfare.py` 后：`compileall` 通过，`tests.test_dokan_welfare` + `tests.test_dokan_normal_mode` 256 项 OK。
- 发布候选（HEAD + 本次提交的 198 个文件）在仓库外的隔离副本里：`compileall -q module tasks tests script.py` 通过；`unittest discover -s tests` 只跑一次，3477 项 OK（skipped=3），15:50:55 ~ 15:56:46；期间副本和仓库里纳入提交的文件哈希都没变。skip 原因见 AI_CONTEXT §7（副本里没有真实配置 1 项；annotator 抓图不在 2 项）。三个含 skip 的模块在工作区里另跑一次：84 项 OK（skipped=2）。
- 没有启动 MuMu / 游戏 / ADB / OCR；运行中的 oas1 / oas2 进程没动。所有 Level C 项仍按 ROADMAP 待真机，离线通过不等于真机通过。

### 提交
- 累积改动作为一个提交：`script.py`、`tasks/base_task.py`、配置模型 / 模板 / 翻译、`docs/L2_CALLSITE_REGISTER.md`（测试把它的汇总数字与源码逐项对账）和六份文档被各主题交叉修改，按主题拆开会产生没测过、登记册对不上的中间状态。逐个路径暂存，没有用 `git add -A` / `.`。

## 2026-10-29 - 百鬼棋局：评估上游 73d4ae84（不合入业务代码，只加守卫测试）

### 范围
- `git fetch upstream self`：`ce476e89..73d4ae84`，相对上一轮固定目标 `47a3a3bc6173e6560ab8cc3658d3e55bc2c80287` 只多 `73d4ae8455c3a2b4d232d897a16a4b3e59a466af` 一个提交（无更多新增）。本地基线 master `f96ace76`，工作区 10 个无关文件（GlobalGame 6 个、孤儿图 4 张）原样保留、哈希核对未变。
- 备份与实验：`D:\Codex\workspace\oas-chess-merge-73d4ae84-20261029`（状态、二进制 diff、未跟踪 tar、上游完整补丁与逐文件补丁、隔离环境、实验副本、往返转换结果、反向验证、全量输出、改动前文档原件）。

### 核查
- 逐文件对比本地与上游父提交：`frame_cards.py` / `c_frame.json` / `hyakki_draft.py` / `state_loop.py` 本地不存在；其余棋局文件都与父提交不同。逐文件 `git apply --check`：只有 `economy.py`（需 Frame 版 `_hand_capacity_count`）、删 `board_positions.py`（本地仍在用）、`app.py` 与 `template.json`（属 JSON 链）能干净套用。
- Frame：`RuleFrame` 在上游 `module/atom/frame.py`，依赖上游 `RuleImage` / 图像服务 badge / `scatter.py`；本地没有 `RuleFrame` / `matched_ranges` / 任何 Frame 扫描。
- JSON：用上游 `_legacy_document` + `CustomLineup` + `strategy_from_document` 转本地 7 套：3 套一致，海国 / 荒川 / 冥府被拒，流火丢一名式神；上游内置 JSON 在本地图鉴下报「未知式神：shiki」。
- 逐项结论表见 AI_CONTEXT §4.159：编辑器 / JSON / OASX 动态选项与快照 / 购卡前容量 / 棋盘站位 / 金鱼 / 纹章羁绊 / 星级确认 / 首领核对 → 暂缓；投掷开关语义、看门狗、`module/cooperation.py` 与非棋局改动 → 排除。

### 修改
- 新增 `tests/test_chess_upstream_73d4ae84_boundary.py` 12 项（本地阵容语义、上游独有文件不存在、本地站位与回收顺序、4 个上游格式表达不了的本地特征）。
- 文档：AI_CONTEXT §2 / §4.159 / §7、ROADMAP 暂缓项、DECISIONS D037 补记、本条。

### 测试
- 新测试在隔离环境与原工作区各 12 项 OK；反向验证：上游 `settings.py` + 上游独有文件 → 5 项失败；整文件换上游 `config.py` / `lineup.py` → 导入即报错。
- 隔离环境 `compileall` 通过；全量只跑一次 3489 项 OK（skipped=3），开始结束前后源码哈希不变。

### 未验证 / 未处理
- 没有合入任何上游棋局功能，也就没有真机项；两条链是否立项由用户决定（ROADMAP）。本地提交，未推送。

## 2026-10-29 - 百鬼棋局：上游 73d4ae84 阵容编辑器 + 自定义阵容以兼容方式接入；更正上一轮过严的守卫与 D037 补记

### 范围
- 上游 `self` 仍是 `73d4ae8455c3a2b4d232d897a16a4b3e59a466af`（`git fetch` 核对，无新提交）；本地基线 `b622663c`，工作区 10 个无关文件原样保留（开始、全量前后、应用前哈希核对）。
- 备份、隔离环境（带基线 git 便于出最终适配 diff）、上游原件、嫁接脚本、变异脚本与全部输出：`D:\Codex\workspace\oas-chess-lineup-editor-20261029`。

### 修改
- 上游原样：`custom_lineups.py`、`lineup_loader.py`、纹章 `index.json`、编辑器网页三件 + 97 张卡面；`.gitignore` / `template.json` / `zh-CN.json` 的对应条目。
- 上游嫁接：`app.py` 两个 hunk、`config_model.py` 两处钩子、`grigri.lineup_bond_context` hunk、`hand_operations` 的纹章分配与御魂预留片段、`recognition._configured_lineup_key` 与快照、`script_task.run` 的阵容选择；没取的行与理由见 AI_CONTEXT §4.160。
- 本地适配：`lineup_compat.py`（站位换算、不支持设置的拒绝、只读内置模板）、`lineup.py`（「自定义阵容」枚举值、`oasx_lineup_choices` 取本地注册表并容错）、`config.py`（`custom_lineup` 字段、`oasx_args` / `select_oasx_lineup` 按本地存法）、`recognition.py`（自定义失败不回落、保留本地缓存清理）、`script_task.py`（加载失败在游戏操作前转人工）、`chesslineup_router.py`（内置只读、本地引用语义、应用提示）。
- 测试：新增 `test_chess_custom_lineup_editor.py` 36 项；`test_chess_upstream_73d4ae84_boundary.py` 改写（12 → 11 项，去掉过严断言）；`test_config_model_script_task.py` case9 对棋局按 `oasx_args` 后比较。
- 文档：AI_CONTEXT §2 / §4.159 更正注 / §4.160 / §7、ROADMAP、DECISIONS D037 第二轮补记（上一条规则划线作废）、ARCHITECTURE 新小节、本条。

### 测试
- 先跑相关模块（棋局三个模块 + `test_config_model_script_task`）93 项 OK；变异 14 条全部被抓、文件哈希恢复；`compileall` 通过；全量只跑一次 3524 项 OK（skipped=3），前后隔离环境源码与原工作区 WIP 哈希不变。

### 未验证 / 未处理
- 编辑器网页没在浏览器里操作过；自定义阵容没上真机；Frame 链仍暂缓。本地提交，未推送。

## 2026-10-29 - 百鬼棋局：完整吸收上游 73d4ae84 的 Frame 识别与状态驱动运行逻辑

### 范围
- 上游 `self` = `73d4ae8455c3a2b4d232d897a16a4b3e59a466af`（`git fetch` 核对）；本地基线 `3cda9cfe`，工作区 10 个无关文件原样保留（开始、全量前后、应用前哈希核对）。目标：完整、兼容地吸收 Frame 手牌 / 商店 / 棋盘识别、状态 / 事件 / 决策 / 状态循环、购卡、容量、清理、上阵 / 下阵、装备、纹章、金鱼、黄金复制术；排除主动投掷、看门狗、`module/cooperation.py`、非棋局。
- 备份、隔离环境（带基线 git 便于出最终适配 diff）、三方合并脚本、静态检查脚本与全部输出：`D:\Codex\workspace\oas-chess-full-absorb-20261029`。

### 修改
- 三方合并（base `ce476e8943bb981c2cd91865cd734865c957c91d` / 本地 / 上游）逐文件逐 hunk，没有整文件采用上游；上游新文件按 blob 逐个核对一致。
- Frame 隔离接入：`module/atom/frame.py`（适配）、图像服务可选 `badges` / `grayscale`、`ChessFrameCompatMixin.runframe`、提取器 `FrameExtractor` 与元数据 JSON 守卫；公共 `RuleImage` / `RuleClick` / `RuleOcr` / `BaseTask` 不变。
- 运行逻辑：新增 `state` / `events` / `decision` / `state_loop` / `frame_cards`，`script_task` / `recognition` / `hand_operations` / `economy` / `round_state` / `settings` / `grigri` / `shikigami_catalog` / `chess_battle` 合并；`board_positions.py` 与旧模板目录删除。
- 编号：七套内置阵容在选择时一次性换算成上游编号（`to_runtime_numbering`），自定义阵容不换算。
- 本地覆盖保持：段位保护 3 局、不局间重载配置、鼬乐币刷满按成功间隔排期、阵容加载失败转人工、不取看门狗与主动投掷。
- 修正：第一次全量跑出 12 项失败（提取器无条件往每个任务的 `assets.py` 加 `RuleFrame` 导入，其余任务的生成结果与已提交文件不一致），改为只在含 Frame 规则的任务里导入，之后重跑全量；上游 `card_index.json` 版面摘要过期（重算）；`3cda9cfe` 带入的元数据 JSON 让提取器崩溃（加守卫）；静态检查发现的 `RuleImage(profile=...)` 与局间 `reload=True` 两处不兼容调用。
- 测试：新增 `test_chess_frame.py`（32）、`test_chess_runtime_absorb.py`（34）、`chess_support.py`；重写 `test_chess_upstream_73d4ae84_boundary.py`（16）；其余棋局 / L1 / L2 登记册测试按新接口调整。
- 文档：AI_CONTEXT §2 / §4.161 / §7、ROADMAP、ARCHITECTURE、DECISIONS（D037 补记三 + D050）、TESTING、`L2_INTERACTION_POLICY_MAP.md`、`L2_CALLSITE_REGISTER.md`、本条。

### 测试
- 先跑相关模块（Frame 32、运行逻辑 34、编辑器 39、边界 16、合入 30、L1 / L2 登记册）逐个通过；静态检查：0 个未定义名称，861 处调用 0 处签名不符；`compileall` 通过；全量只跑一次，第一次全量 12 项失败（见上「修正」），修复后重跑 3598 项 OK（skipped=3），前后隔离环境源码哈希一致。

### 未验证 / 未处理
- 没有真机：Frame 真实命中率、上阵 / 金鱼 / 黄金复制术 / 腾位时序、鼬乐币 ROI、自定义阵容。本地提交，未推送。

## 2026-10-29 - 福利道馆：滑动后落点确认过严（oas1 `not settled (stable=True)` 连续四轮），确认改为判「内容有没有在动」

### 核查
- oas1 20:42 第一次滑动后四轮 `not settled (stable=True)` 转人工；oas2 20:41:09 同样出现过一次（重启后才通过），20:42:45 / :51 两次 static 先 not settled 再 settled。`stable=True` 而未稳定只可能是追加确认 `_holds_still` 失败。
- 两层判断区域 / 算法 / 阈值相同（LIST_BOX、`frame_difference`、1%），基准不同：观察层相邻帧，确认层固定落点帧。缓慢渐变的局部动画相邻差为 0 而累计差越线（合成：角标 5.5%、徽记 24%），旧确认判成「还在动」。后几轮每轮 3.0 秒与「最后几帧才失败」相符（推断）。基准帧 / 落点帧是独立拷贝，nemu_ipc 每帧新数组，确认阶段不识别不改画面。没有 oas1 的连续帧，动画来源未被证明。

### 修改
- `tasks/Dokan/welfare.py`：新增 `list_content_shift` / `list_change_kind`（same / local / shifted / wide）与常量 `HOLD_SHIFT_MAX`（150）/ `HOLD_SHIFT_GAIN`（0.5）；`_holds_still` → `_hold_failure`（只有 shifted / wide 拒绝）；`_settle_list` 每轮写具体原因，通过时记录放过的局部变化；最终失败前 `_save_settle_evidence` 一次性保存滑动前帧 + 最后一轮基准帧 / 失败帧 + 变化像素图 + `log.txt` 到 `log/error`（受 `save_error` 控制，失败不掩盖原错误）。D-03 / D-04、观察层、公共组件、业务流程不变。
- `tests/test_dokan_welfare.py`：World 新增 `anim_find`；新增 `ListHoldTest` 26 项。

### 测试
- 旧判据对照 8/26 红；变异 11 组均有测试变红；福利 256 项、相关 433 项通过；全量一次 3624 项 OK（skipped=2），前后哈希不变；点击登记册无差异；完整输出在 `D:\\Codex\\workspace\\d11\\`。

### 未验证 / 未处理
- 真实动画来源、`HOLD_SHIFT_*` 在真实回弹 / 滚动尾巴上的表现，等 oas1 / oas2 对照实测。稀疏列表位移 > 150 px 的局限、刷新「内容变了」线对持续局部动画的敏感度（既有，未改）。

## 2026-10-29 - 福利道馆：准备后 0.35 秒缓冲、排名遮罩不算再战成功、游戏自动回庭院后重新进入找馆页

### 核查
- 准备点击：oas2 20:47:41.787 点击返回（点击约 160 ms），20:47:41.789 开始 `app_stop`（间隔 2 ms）；用户最终确认策略为点击返回后额外等 350 ms。服务端停在哪一步没有证明。
- 遮罩：oas2 20:58:22 放弃确认 → 20:58:23 一次再战按钮点击 → 20:58:24 `vote confirmed`，中间没有遮罩关闭点击。遮罩下的按钮仍可匹配，点击只关遮罩，按钮框因此「变化并稳定」被旧判据当成选中。排名模板在用户那张画面上能否匹配没有离线证据（整屏图不在磁盘）。
- 返回：用户确认放弃后游戏内约一分钟倒计时、结束自动回庭院，与程序的 120 秒是两个独立计时。旧 `_back_to_find_page` 只处理找馆页 / 进行中的馆 / 道馆页，其余点黄色返回键；`goto_page(timeout)` 是无进展超时，不是总时限；真实 `goto_page` 遇到未知页会自己执行未知页关闭（含黄色返回键），所以未知页不能直接交给它。

### 修改
- `tasks/Dokan/welfare.py`：`PREPARE_CLOSE_BUFFER_SECONDS=0.35`，点击返回后 `_wait` 再 `app_stop`；新增 `_clear_rank_mask`（现有资源关闭 + 连续 2 帧确认消失 + 有界）、`_outside_change`；`_vote_again` 每次取基准前先处理遮罩并重建基准，点击后任何一帧看到遮罩或按钮框以外变化 > 0.15 就不采信、转人工、不重复点击；`_back_to_find_page(after_rematch=True)`：新截图 → 找馆页 / 进行中的馆 → `get_current_page` → 复用 `goto_page(page_dokan_map)` → 新截图确认，认不出只重新识别（30 秒上限）不点返回键，导航最多 3 次。`leave_dokan_page` / `DOKAN_EXIT_TRIES` 改名 `after_rematch` / `RETURN_NAV_TRIES`。
- `tests/test_dokan_welfare.py`：World 新增遮罩与游戏自动回庭院（默认 `after_again='countdown'`）；`FakeTask.get_current_page` / 逐跳真实页面转换 / `click` 的 interval 限流；新增 `PrepareBufferTest` 6、`RankMaskVoteTest` 14、`AutoHomeReturnTest` 16，调整旧用例。
- `tests/test_l2_c0_registry.py` + `docs/L2_CALLSITE_REGISTER.md`：关闭遮罩的点击移进 `_clear_rank_mask`，KEEP_IMMEDIATE 638 → 637、KEEP_SPECIAL 240 → 241（函数名 `clear` 提示 R4），总数不变，重新生成并同步精确期望值。
- 文档：AI_CONTEXT §4.163 / §4.156 更正 / §7、ROADMAP、DECISIONS D052、ARCHITECTURE（福利走 `get_current_page`）、TESTING（遮罩 / 自动转页的替身要求）。

### 测试
- 旧实现对照（缓冲 0 秒 / 只看按钮框变化的投票 / 黄色返回键 + 仅道馆页）下新增 36 项分别 7 / 9 / 21 项变红；变异 11 组均有测试变红；福利 + 普通模式 + L1·L2 登记册与守卫 + FrameState·FrameWait + 重启恢复共 469 项通过；`compileall` 通过；点击登记册重新生成并同步精确期望值（3 项原先失败：两条登记册对账 + 一条汇总对账，更新后通过）；全量一次 3660 项 OK（skipped=2），22:23:46 ~ 22:30:41，前后关键哈希不变；完整输出在 `D:\Codex\workspace\d12\`。

### 未验证 / 未处理
- 350 ms 是否足以触发离线自动战斗；排名模板在真实遮罩画面上能否匹配、`VOTE_OUTSIDE_CHANGED_MAX` 是否合适（日志 `vote confirm check`）；遮罩点击区域；倒计时结束自动回庭院的真实时长；放弃后账号状态下庭院 → 道馆地图的导航；完整两馆实测。

## 2026-10-30 - 悬赏封印：列表进度整区漏检后静默漏做的离线修复

### 范围
- 起因：oas1 10-30 13:14~13:16 的 `WantedQuests` 只做了第三个位置的三个悬赏，剩下列表里的 1/14、1/3 两个没做，日志里没有任何尝试，次日 13:16 才再排期。排查（只读日志与源码，加上标注工具与本机 OCR 对 13:23 截图的离线实验）确认是 `find_wq` 的整区检测没有框出这两条进度文字，窄条能读；按 D044 的原则，这种「有悬赏标签却读不出进度」不能当正常完成。
- 只改 `tasks/WantedQuests/script_task.py`；不改公共 OCR 模型 / 阈值 / 点击保护 / 滑动框架，不动其他任务，不改实例配置与排期，不启动任何服务或设备。

### 修改
- `find_wq` 有效标记三态（`WQ_FOUND` / `WQ_NONE` / `WQ_UNRESOLVED`）；整区路径无可选候选时按「悬赏封印」标签补读它上方的窄条（`_supplement_wq_progress` / `_read_wq_label_strip`），严格 `n/m` 解析；`run` 对未确定做有界复核后抛 `GameStuckError`。细节与边界见 AI_CONTEXT §4.164。
- 测试：新增 `tests/test_wanted_quests_list_progress.py`、真实截图夹具 `tests/fixtures/wanted_quests/list_missed_progress_oas1_20261030.png`；拆分 `tests/test_wanted_quests_detail_flow.py` 里把「仍有悬赏、一直无候选」当正常结束的用例。
- 文档：AI_CONTEXT §2 / §4.164 / §7（顺带修掉 §4.161 基线里被转义吃掉的路径分隔符）、DECISIONS D044 补记、ROADMAP、TESTING。

### 测试
- 变异检查：补读关闭 / 未确定当没有 / 无条件补读 / 宽松字符 / 污染共享 ROI / 边缘当普通 / 复核无上限 / 已完成当异常 / `m=0` / 7 分隔符 / 不裁边 / 重读已认领标签，12 条都被现有用例抓住；条带「位置校验」一条因条带几何已蕴含而被判为冗余代码，已删除。
- 真实截图离线 OCR（`OAS_REAL_OCR_TESTS=1`，本机模型）：`find_wq` 在夹具图上返回 `(1, 1, 14, [35, 180, 44, 20])`；整区检测单独仍读不到进度；抹掉两条进度后返回「未确定」。
- 全量：3693 项 OK（skipped=5：既有 2 项离线模板 + 本轮新增 3 项真实 OCR 回归默认不跑），直接在工作区跑（14:17 ~ 14:24），含其他会话的福利道馆未提交改动，全部通过

### 未验证 / 未处理
- 真机：补读候选的详情打开 / 执行 / 领奖、窄条在其他列表布局上的稳定性、`GameStuckError` 路径的重启恢复。工作区仍有其他会话的福利道馆未提交改动与 10 个 GlobalGame / 孤儿图文件，未触碰。

## 2026-10-30 - 探索：恢复 Boss 胜利后跳过地图奖励并直接退出（离线完成，等待实测）

### 背景与用户要求
用户明确要求：探索战胜 Boss 后，地图上的小纸人 / 宝箱领取与展示动画会拖慢探索效率，要**跳过**，确认 Boss 胜利后立即执行游戏内退出（不是关游戏、不是终止整个探索任务），确认回到外层后再按次数 / 时限 / 疲劳规则开下一轮。普通怪战斗与通用战斗必要的结算处理不变。
2026-09-08 的两条记录（§4.58 做了 Boss 专用退出结构、§4.60 撤回并恢复原生奖励链）保留为历史；其中「错误需求」「用户重新确认」的措辞缺少原始对话核对，**已被本轮明确需求取代**，不再作为生效结论。

### 修改前的缺口（HEAD 源码）
- `get_fire_button` 看到 Boss 按钮就设 `fire_monster_type='boss'`，此时既没开战也没胜利；`run_on_battle` 不消费 `run_general_battle` 的返回值。
- `run_on_exp_main` 先 `collect_reward()`（地图宝箱 → 小纸人）；只有「Boss 标记 + 不领小纸人」才走原生退出，且这个标记在未开战时就可能触发退出。
- 外层 `run_on_exp_entrance` / `run_on_exp` 还会补领宝箱。

### 修改（`tasks/Exploration/base.py` / `script_task.py`，任务内存状态，不写配置、不落盘）
- **归属**：`fire()` 只在**正向识别到战斗页**时写 `_battle_target`（`boss` / `normal`），退出弹窗分支清空；`run_on_battle` 开头取走并清空（只消费一次，上一场标记不会污染下一场）。队员从不 `fire`，所以不会判 Boss。
- **胜利**：`run_on_battle` 只在 `run_general_battle(...) is True` 且 `target == 'boss'` 时 `begin_boss_exit()`；战败 / 主动退出 / 结果不明 / 未开战都不触发，也不置疲劳标记。公共胜负判定未改。
- **三态** `_boss_exit_phase`：`''` → `exiting`（跳过宝箱 / 小纸人、退出中）→ `exited`（已见合法外层页，外层不补领）→ `''`（新一轮开始：进 `page_exp_main` / 战斗页 / 组队页）。`begin_boss_exit` 启动 30 秒 `Timer`。
- **退出**：`run_on_exp_main` 在 `exiting` 时先 `quit_exp_main()` 就返回（不经过 `collect_reward`，与 `collect_paper_reward` 开关无关）；退出弹窗由既有 `run_on_exp_exit` 确认（`need_exit=True`）。成功的唯一证据是 `exec_exp_page` 的新截图正向命中 `page_exp_entrance` 或 `page_exploration`（`observe_boss_exit_outer`）；游戏已自动退出时不点返回。
- **有界失败**：`exec_exp_page` 每轮 `guard_boss_exit_deadline()`，超时抛 `GameStuckError`；`exiting` 期间未知页（`None` 或无 handler）只观察、不 `goto_page`；`exiting` 期间 `check_exit` 为真也先完成本轮退出（同样受 30 秒限制）。设备异常 / 停止信号原样传播，没有 `finally` 补动作。
- **外层不补领**：`run_on_exp_entrance` / `run_on_exp`（ALONE / MEMBER）改调 `_collect_outer_treasure_box()`，`exited` 阶段不领；LEADER 的外层本来就不领宝箱。
- **疲劳**：`_boss_cycle_fatigue_due` 取代原来靠 `fire_monster_type=='boss'` 判断；在外层 handler 顶部一次性消费（所有角色都消费，仅 solo 真休息），休息后沿用 `exec_exp_page` 的新截图重新分发。
- **删除**：`collect_paper_man_reward` 里「`fire_monster_type=='boss'` 且不领小纸人 → `quit_exp_main`」分支（该标记在未开战时就会设置）；开关现在只管普通怪阶段的小纸人。Boss 战败后仍沿用原主循环（Boss 按钮还在就再次 `fire`），不新增重试策略。

### 角色
- 单人：退出 → 外层 → 疲劳安全节点 → `goto_page(page_exp_main)`。
- 队长：退出 → 外层沿用 `check_and_invite` / `enter_team`（退出确认会重置队友等待时间，既有节奏不变）；不走单人疲劳。
- 队员：**不做 Boss 判定**（从不 `fire`，看到 Boss 按钮不能证明这场是 Boss），保持原样：地图上等队长 / 好友消失后 `quit_exp_main`，外层只 `check_then_accept`。队员在 Boss 胜利后仍可能走原生奖励链，是否需要队员也跳过要等真实组队画面。

### 测试
- 新增 `tests/test_exploration_boss_exit.py`（25 项，驱动真实 `exec_exp_page` / `run_on_*` / `fire` / `check_exit`，只替换设备、识别、通用战斗）：Boss 胜利不点宝箱 / 小纸人（开关 True / False）、外层不补领、自动退出到两个外层页、已在退出弹窗、仅发现按钮 / 战败 / 结果不明不算胜利、旧标记不污染普通怪、普通怪奖励与开关原样、三种有界失败、异常透传、连续两轮、次数 / 时限到达、疲劳后新截图、队长 / 队员。
- 修复前对照（HEAD 源码 + 同一测试文件，临时 worktree，已删除）：15 个失败 + 13 个报错（报错多为旧代码没有归属 / 阶段状态）；修复后 25 项全过。
- `tests/test_exploration_state.py`：删除固化旧实现的断言（禁止 `battle_won`、必须 `collect_reward` 优先、Boss 标记 + 不领小纸人才原生退出、`BOSS_EXIT_` 子串不得出现），换成「旧标记不再触发退出」和疲劳一次性消费等；保留仍有效的异常 / 次数 / 滑动 / 轮换 / FrameWait 回归。
- 回归：`test_l2_c0_registry` / `test_l2_interaction_reaction` / `test_l2_policy_migration` / `test_fire_reaction_fsm` / `test_general_battle_settlement` / `test_team_sync` / `test_reaction_timing_batch1` 共 289 项通过；点击调用点没有新增 / 减少，登记册无需改。`compileall -q` 通过；全量 `unittest discover -s tests` = 3710 项 OK（skipped=5），含其他会话留在工作区的福利道馆 / 悬赏封印未提交改动。

### 未验证 / 待实测
- 真机：Boss 胜利后立刻点返回是否稳定出现退出弹窗、不跳过奖励是否会让外层残留宝箱影响下一轮进入、退出 30 秒上限是否合适、`page_exploration` 与 `page_exp_entrance` 哪个先出现。
- 组队：队长退出后队员的表现、队员是否需要同样跳过奖励。
- 未改：滑动模型、轮换所有权、章节 FrameWait、公共战斗 / 邀请 / 导航 / 图像接口、用户实例配置。未提交。

## 2026-10-30 - 悬赏封印列表进度补读：审查整改（合并框证据、进程内真实截图回归、两个进度都要恢复）

### 范围
- 审查对上一条（列表进度整区漏检的离线修复）提出三项：合并框里的非法进度会让标签证据丢失；真实截图测试没有证明走进程内模型；真实截图只证明了首选的 1/14。只在 `tasks/WantedQuests/script_task.py` 和 `tests/test_wanted_quests_list_progress.py` 上做最小整改，不动公共 OCR、阈值、调度器，不新增 ADR。

### 修改
- 合并框：`_WQ_PROGRESS_PATTERN` 成为整区与补读共用的进度格式；`find_wq` 在忽略非法进度时，如果同一个框里有悬赏标签（且不在底部边缘区）就记为未确定；补读跳过含该格式的标签框（合法的走原路径）。整改前后对照（mock OCR，真实 `find_wq` + 真实 `run`；`D:\Codex\outputs\wq-list-progress-review-fix-20261030\merged_box_before.txt` / `merged_box_after.txt`）：`悬赏封印3/17`、`15/14`、`0/0` 整改前 `find_wq`=`(-1,-1,-1,[0,0,0,0])`、`run` 翻页 4 次 + `next_run` 1 次 + 正常 `TaskEnd`；整改后 `find_wq`=`(-1,-2,-1,[0,0,0,0])`、`run` 复核 3 次后 `GameStuckError`、0 次翻页、0 次 `next_run`。合法未完成（`1/14`、`1714`）仍按原路径选中整个框，已完成（`14/14`）不报未确定。
- 真实截图回归改为进程内注入模型并带隔离守卫（细节见 AI_CONTEXT §4.164 复核整改②）；断言补读候选集合同时含 1/14 `[35,180,44,20]` 与 1/3 `[39,305,35,21]`，并保留整区漏检对照与抹去进度的反向对照。
- 新增 `MergedLabelBoxTest` 9 项（含真实 `run` 收尾）和一项「原路径格式不匹配的数字串不能让标签被跳过」；补读命中的来源日志。
- 文档：AI_CONTEXT §4.164 复核整改 / §7、DECISIONS D044 补记一句、TESTING §5.y、ROADMAP 一句、本条。

### 更正
- 上一轮（初版 §4.164 及对应报告）关于真实截图 OCR「用本机模型、单进程、不连接服务」的说法没有依据：默认获取点是 OCR RPC 客户端，当时没有注入进程内模型，那几次真实 OCR 很可能请求了运行中的 OCR 服务（只读识别请求）。旧的测试记录保留为历史事实，不改写；本条起的真实截图回归才是进程内。

### 测试
- 变异检查：补读的合并框证据 4 条（去掉合并框记录、不排除底部区、补读又按任意数字斜杠跳过、合并框也补读）全部被抓（其中一条最初没被抓，补了「三位数字串」用例）；去掉模型注入后 4 项真实截图用例全部失败。
- 真实截图 + 进程内模型：`OAS_REAL_OCR_TESTS=1 toolkit/python.exe -m unittest -v tests.test_wanted_quests_list_progress.RealScreenshotRegressionTest`，4 项 OK（约 4.5 秒，含模型载入）；补读候选 `1/14` -> `[35,180,44,20]`、`1/3` -> `[39,305,35,21]`；输出 `D:\Codex\outputs\wq-list-progress-review-fix-20261030\real_screenshot_inprocess_output.txt`
- 全量：3720 项 OK（skipped=6：既有 2 项离线模板 + 本轮 4 项真实截图回归默认不跑），直接在工作区跑（15:25 ~ 15:32），含其他会话的福利道馆 / 探索未提交改动，全部通过

### 未验证 / 未处理
- 真机：补读候选的详情打开 / 执行 / 领奖、条带偏移在其他布局上的稳定性、`GameStuckError` 路径的重启恢复。仍未提交；其他会话的福利道馆 / 探索等未提交改动与 10 个 GlobalGame / 孤儿图文件未触碰。

## 2026-10-30（第二轮）- 探索 Boss 直退：`fire()` 末次点击 / 10 秒边缘的归属收口 + 决策编号改 D053

### 问题
上一轮把战斗归属写在 `fire()` 循环内部的"正向识别到战斗页"分支。但循环在 4 次点击用完（`max_tries` 归零）或 10 秒到期后直接 `return False`：
- 第四次点击恰好成功，循环已结束，没再观察战斗页；
- 某次点击后恰好到 10 秒上限，也没有最后一次确认；
外层随后识别到战斗并走 `run_on_battle`，但 `_battle_target` 为空，Boss 胜利无法直退（且调用方还会误以为没进战斗而继续滑图）。

### 修改（只动 `tasks/Exploration/base.py` 的 `fire()`，新增 `_observe_fire_result()`）
- 点击预算（最多 4 次）与结果确认分开：每次实际点击起 `FIRE_RESULT_WINDOW = 2.0` 秒窗口；主循环退出后若发出过点击，就在最后一次点击的窗口内继续**只截图识别**（至少一帧），不再点击，不重置原 10 秒计时器，不重套整轮攻击。
- 取值依据：循环中两次点击最小间隔 0.8 秒（点击没出战斗页就重击），窗口取其 2.5 倍，覆盖转场；总耗时上界 = 10 秒主循环 + 约一帧 + 2 秒。
- 观察语义不变：战斗页 → True + 按所点按钮写归属；退出弹窗 → 取消退出、True、不记开战；始终未确认 → False 且不留归属；点击从未实际发出 → 无尾部确认、10 秒后 False。每次 `fire()` 开头清空上次未消费的归属。截图 / 识别 / 设备异常与停止信号照常传播。
- 点击调用点数量不变（`fire#1` 仍是同一个 `appear_then_click`），L2 登记册无需改。
- **未改**：指定加成怪定位、章节排序、到底判据、滑动、公共 FrameWait / GeneralBattle / Navigator / 图像接口、普通战斗计数、Boss 重试策略。

### 文档编号
探索 Boss 直退的决策原先写成 D050，与"棋局 Frame"的 D050 重号（D051 / D052 已被福利道馆占用）。检查全部 docs 里最大号为 D052 后，探索条目改为 **D053**，并同步 D021 头部、ARCHITECTURE、ROADMAP、TESTING、AI_CONTEXT 的引用；棋局 D050 及其引用（AI_CONTEXT、ROADMAP、DEVELOP_LOG 旧条目）保持不动。

### 范围口径（不要笼统写成"队长、队员均已跳过奖励"）
单人 / 队长 = 本地确认归属为 Boss 的胜利后直退；队员不新增 Boss 归属、不凭队长结果标记胜利，保持原跟随 / 接受邀请 / 奖励处理，其是否自动跟随队长离开、是否仍被奖励处理拖慢待组队实测。

### 测试
- `tests/test_exploration_boss_exit.py` 25 → 41 项：新增 `VirtualClock`（Timer 读虚拟时钟、截图推进，不真实等待）、`FireRig`（直接驱动真实 `fire()`，点击受 0.8 秒间隔约束）和 `FireTailObservationTest`（第四次点击成功 Boss / 普通怪、跨 10 秒上限的点击、结果窗口之外的迟到战斗、始终未开战、点击从未发出、尾部遇到未知页 / 退出弹窗 / 设备异常 / 停止信号、尾部截图帧数有界、旧归属清空、连续两轮、战败、不污染下一场、完整直退无第五次点击无地图奖励无滑图）。
- `tests/test_exploration_state.py`：原两个靠 mock `Timer` 的 `fire` 用例改成虚拟时钟；源码断言里战斗页判断改读 `_observe_fire_result`。
- 修复前对照：临时 worktree（HEAD + 现有测试 + 把 `fire()` 换回上一轮实现），新测试 9 项失败（含子用例 11 处）；修复后全过。

### 未验证
真机：2 秒窗口对真实转场是否合适、末次点击确认在真实网络延迟下的表现；组队队员行为。未提交。

## 2026-10-30 - 悬赏封印列表进度补读：最后两项边界整改（底部非法合并框、隔离违规不得变 skip）

### 范围
- 审查再提两项：①底部边缘区的非法合并框被排除后，翻页预算耗尽仍返回 `WQ_NONE`，真实 `run` 滑动 4 次后正常完成（违反「有悬赏证据但进度无法确定不得正常完成」）；②进程内真实截图回归 `setUpClass` 的 `except Exception` 会把隔离守卫抛的 `AssertionError` 包装成 skip。只改 `tasks/WantedQuests/script_task.py` 的 `find_wq` 和 `tests/test_wanted_quests_list_progress.py`，不动公共 OCR / 阈值 / 滑动次数 / 点击保护 / 调度恢复，不新增 ADR。

### 修改
- `find_wq`：非法合并框按位置分成非边缘 / 底部两个列表；底部列表只在 `allow_edge_fallback`（翻页预算耗尽）时并入未确定。结果对照（`悬赏封印3/17`，框 `(13,455,86,42)`）：翻页前（预算内）`WQ_NONE`（先翻页，不变）；预算耗尽后 `WQ_NONE` → `WQ_UNRESOLVED`；真实 `run`（该框持续存在）：滑动 4 次 + `next_run` 1 次 + 正常 `TaskEnd` → 恰好滑动 4 次（原预算）后复核 3 次、`GameStuckError`、`next_run` 0 次。
- 测试：底部边界新增 9 项（预算内等待翻页、耗尽后未确定、边缘候选不能绕过、可靠候选先做、合法已完成 / 合法未完成边缘合并框不变、真实 `run` 的恰好用满翻页预算后异常、翻页后读到合法进度、最终复核恢复合法进度、最终复核证据消失、可靠候选做完后残留底部框异常）；原 `test_merged_illegal_box_in_the_bottom_zone_waits_for_scrolling` 保留「预算内可以翻页」并补耗尽后的行为。
- 隔离：`_IsolationViolation` + `_VIOLATIONS`、`InProcessOcrCase` 公共夹具、`InProcessOcrIsolationTest` 6 项（细节见 AI_CONTEXT §4.164「最后边界整改」）。
- 文档：AI_CONTEXT §4.164 / §7、DECISIONS D044 补记一句、TESTING §5.y、本条。

### 测试
- 变异：底部整改 2 条（预算耗尽不保留证据 / 无条件保留）、隔离 5 条，全部被抓。
- 真实截图 + 进程内模型（PowerShell 里设置 `OAS_REAL_OCR_TESTS`，结束后恢复原值）：PowerShell 中设置 `OAS_REAL_OCR_TESTS=1`（`try/finally` 恢复原值）后 `cmd /c toolkit\python.exe -m unittest -v tests.test_wanted_quests_list_progress.RealScreenshotRegressionTest`，4 项 OK、skipped 为零（约 4.3 秒，含模型载入）；输出 `D:\Codex\outputs\wq-list-progress-final-boundaries-20261030\real_screenshot_inprocess_output.txt`
- 默认全量：3751 项 OK（skipped=6：既有 2 项离线模板 + 4 项真实截图回归默认不跑），16:04 ~ 16:11，直接在工作区跑，含其他会话的福利道馆 / 探索未提交改动；第一次全量在 16:03:55 无故中断（无汇总、无 traceback，原因不明），输出另存，随后整体重跑

### 未验证 / 未处理
- 真机：补读候选的详情打开 / 执行 / 领奖、底部边缘框在真实列表里的翻页行为、条带偏移在其他布局的稳定性、`GameStuckError` 重启恢复。仍未提交；其他会话的福利道馆 / 探索等未提交改动与 10 个 GlobalGame / 孤儿图文件未触碰。

## 2026-10-30 - 悬赏封印：执行记录按当前悬赏 + 当前进度阶段隔离（不同妖怪不再互相过滤挑战）

### 范围
- 用户确认：打开详情、复用已有妖怪名 OCR、确定当前悬赏上下文、只在当前悬赏范围内去重，再按原有优先级和挑战券条件选路线。只改 `tasks/WantedQuests/script_task.py`（新增 `WQContext`、`_begin_wq_attempt` / `_close_wq_context` / `_log_wq_decision`，`execute_mission` / `read_ordered_wq_infos` / `get_ordered_wq_infos` / `read_wq_rows` / `build_wq_info` 增加可选的上下文 / 进度参数）和测试；不改公共 OCR / 图像服务 / 战斗 / 导航 / 滑动、实例配置，不新增 OCR、截图、等待或点击。新增 D054。

### 修改
- 删除类级 `wq_executed_set`。执行记录改为任务对象的 `_wq_context.attempted`：`run` 开始置空；领奖（`I_WQ_BOX` / `I_E_REWARD_BOX_BIG`）或 `skip_current_wq` 取消追踪时关闭；进度增加 / 变小、总数不同、妖怪名已确认不同都建立新上下文；路线过滤只在妖怪名已确认且同一进度阶段才生效，名字读不出时由 `WQ_MAX_NO_PROGRESS_REPEATS=3` 兜底并抛 `GameStuckError`。
- 过滤日志带妖怪名 / 进度 / 路线 / 计划场数 / 原因，另有每次读完推荐行后的一条决策汇总日志；挑战券不足日志带目的地与场数。
- 既有测试：`test_executed_target_is_filtered` 改成「当前悬赏上下文里已尝试的路线被过滤、无上下文或换悬赏不被过滤」的行为验证；两个测试文件去掉对旧类级集合的重置；`run` 主循环测试里的 `execute_mission` 假实现接受新的关键字参数。

### 测试
- 新增 `tests/test_wanted_quests_exec_record.py`（21 项）。旧实现上跑跨悬赏碰撞用例：5 项断言失败（第二条悬赏的 `challenge` 只调用 1 次），另 2 项因缺新属性报错；新实现全部通过。输出：`D:\Codex\outputs\wq-exec-record-20261030\before_old_output.txt`。
- 变异 10 条（过滤永远不生效 / 进度增加仍沿用旧阶段 / 取消不关闭 / 领奖不关闭 / 取消重复上限 / 名字不同仍当同一条 / run 开始不初始化 / 未确认名字沿用旧路线 / 进度未知接旧上下文 / 模块级共享集合）全部被抓，文件逐字节还原。
- 默认全量 `unittest discover -s tests` = **3772 项运行 OK（skipped=6）**，只跑一次，22:02 ~ 22:09，开始前确认没有 unittest 进程，前后 `script_task.py` / 新旧测试 / `welfare.py` / 探索文件 / `oas1.json` / `oas2.json` 哈希一致；skipped=6 = 既有 2 项离线模板 + 4 项默认不跑的真实截图回归（本轮未改，也未重跑）。

### 未验证 / 未处理
- 真机：挑战优先选择是否恢复（日志里 `Wanted quest recommendations […]` 的汇总与 `Choose wq` 的类型）、领奖观察是否稳定地先于下一条悬赏（决定同名新悬赏边界）、名字 OCR 是否稳定。均待实测；仍未提交，其他会话的福利道馆 / 探索等未提交改动未触碰。

## 2026-10-31 - 结算：page_reward 内部奖励布局交接后重新选区（魂土小动物奖励点满 9 次）

### 范围
- 用户报告：魂土结算从普通奖励切到小动物奖励后仍沿用旧点击位置，奖励阶段点满 9 次安全上限仍停在小动物页。只改 `tasks/Component/GeneralBattle/general_battle.py` 的奖励布局交接，不动魂土次数 / 组队 / 锁队 / 御魂循环，不提高总点击上限，不新增模板 / 坐标 / 阈值。

### 修改
- 日志（`log/2026-10-31_oas1.txt` 14:43:46~14:44:32）：`page_reward` 选 `random_default`、锚点 (968, 520)，同一点点了 8 次，`total_clicks=9/9` 后停；用户观察到停在小动物页。源码缺口：`region_provider` 只在 session 初始化 / 页面类型变化时执行，同一 `page_reward` 内布局变化不会重选区。
- `_read_reward_layout`（只读标志证据）/ `_reward_region_for_layout`（按布局选区）拆出，`_select_reward_region` 为二者组合；`BattleContext` 增 `settlement_layout` / `settlement_layout_pending` / `settlement_layout_pending_frames`；`_settlement_burst_step` 增可选 `layout_probe`，`_handle_reward` 传 `_read_reward_layout`；新增 `_commit_settlement_layout` / `_note_settlement_layout` / `_rehome_settlement_anchor` / `_reconcile_settlement_layout`，`_fire_settlement_burst` 增可选 `layout_probe`，第二下 gate 加入布局一致性；常量 `SETTLEMENT_LAYOUT_CONFIRM_FRAMES=2`。细节见 AI_CONTEXT §4.167。
- 测试：新增 `tests/test_general_battle_reward_layout.py`（28 项）；`test_general_battle_settlement.py` 三处测试替身适配（见 §4.167）。

### 测试
- HEAD 版源码 + 3 个 shim（常量 / 默认字段 / 证据读取）跑新测试：13 项失败（旧锚点继续点击等）；新实现 28 项通过。
- 相关回归（结算 / 秘闻区域 / 时序 / 点击迁移守卫 / 登记册 / 爬塔）431 项 OK；`compileall -q` 通过；默认全量 3800 项 OK（skipped=6），只跑一次，前后工作区状态哈希不变。

### 未验证 / 未处理
- 真机：小动物奖励页上宝袋标志是否消失、确认帧数是否合适、兜底安全区能否推进。若标志仍命中则本修复触发不了，需要现场截图 + 新证据。未提交。

## 2026-10-31 - 御魂结算内「发现宝藏」宠物奖励弹窗：在 Orochi 结算处理层优先关闭

### 范围
- 用户确认现有 `I_PET_PRESENT` 能识别样本（similarity 0.9829），不改模板 / ROI / 阈值。只做宠物弹窗在通用结算内部的衔接，不动 SwitchSoul、魂土次数、锁队、组队同步、御魂循环，不动上一轮奖励布局交接。

### 修改
- 调用链缺口：`page_reward` 识别条件含 `I_PET_PRESENT`，但专用关闭只在外层 `run_member` / `run_alone` / `run_wild` 循环，`run_general_battle` 没返回时执行不到。新增 `ScriptTask._handle_pet_present`，由 `_handle_reward`（最先）/ `_handle_result` / `_handle_missing_battle_page` 调用；点击间隔限流时仍归本分支；连续 2 张新帧都看不到才算关闭；4 次点击 / 15 秒上限抛 `GameStuckError`；`run_general_battle` 覆盖为进入 / 退出（含异常）清状态。外层旧分支保留。细节见 AI_CONTEXT §4.168。
- 登记册：新增 1 个点击调用点（KEEP_SPECIAL），`INVENTORY` / `test_l2_c0_registry` 计数精确 +1，登记册由工具重新生成，`L2_INTERACTION_POLICY_MAP.md` 加 L2M-077a。

### 测试
- 新增 `tests/test_orochi_pet_reward.py`（25 项）；HEAD 版上 20 项失败、新实现 25 项通过；5 条变异全部被抓。
- 事故：验证中把 `test_orochi_loop.drive` 改成覆盖 `appear=False`，使 `run_leader` 建队循环不结束，Mock 无限记录，进程内存涨到 40GB+，用户要求后核对 PID 与命令行并停止。查清并修复后，所有运行改用带看门狗的 `guarded_run.py`。
- 默认全量 3825 项 OK（skipped=6），峰值 699 MB，工作区状态前后不变。

### 未验证 / 未处理
- 真机：模板连续帧稳定性、右侧点击能否关闭、关闭后落在哪个页面。FallenSun 外层有同样的分支，未处理。未提交。

## 2026-10-31 - 测试运行守护：外部私人提交 / 时限监控入口 + 事故用例的次数哨兵

### 范围
- 之前两次出现 Python 测试进程大量占用内存（2026-10-31 御魂回归约 40.95 GiB 私人提交、系统提交率 98%；2026-10-26 另有一次原因未确认的 Windows 资源耗尽记录，不视为同一缺陷）。本轮建立可复用的保护，只涉及测试基础设施与文档，不改游戏业务行为 / 调度器 / 运行时保护，不动 SwitchSoul 与宠物业务。

### 修改
- `tests/test_orochi_loop.py`：`LeaderTrustedCountTest` 增加 `_install_loop_sentinel`（`run_leader` 100 次截图上限，超限抛带用例名和阶段信息的 `AssertionError`），`screenshot` / `appear` 改成普通函数，`drive` 里的识别替身按 `I_PET_PRESENT` 单独返回 False、其余委托。受控反向验证（子类覆盖恢复统一 `appear=False`）：两个用例各在第 101 次截图时快速失败。
- 新增 `dev_tools/guarded_unittest.py`：外部守护（真实单调时钟）、测试进程树合计私人提交、总时限、日志大小、输出直接落盘并带完整用例名、只终止自己的进程树、同工作区单实例锁（PID + 创建时间校验）、Ctrl+C / 监控异常清理、摘要与非零退出码。新增 `tests/test_guarded_unittest.py`（27 项）分层验证。细节见 AI_CONTEXT §4.169、TESTING §5.ac、DECISIONS D056。
- 文档：`CLAUDE.md` / `AGENTS.md` 的验证规则同步入口；TESTING §1 / §5.ab / §5.ac。

### 测试
- 经正式入口：事故相关 70 项、相关回归 1020 项（126.9 秒，峰值 560 MiB）、全量 3852 项 OK（skipped=6，399.9 秒，采样峰值 1433 MiB）；工作区状态前后不变。日志在 `D:\Codex\outputs\20261031_测试守护入口\`。

### 未验证 / 未处理
- 守护不覆盖手工 `python -m unittest`；守护自身被强杀时测试进程可能遗留；默认阈值是初始工程上限。未提交。

## 2026-10-31 - 测试守护入口复审修复：清理失败保留运行锁 + 陈旧锁接管互斥

### 范围
- 审查指出 `dev_tools/guarded_unittest.py` 的两处缺陷：①清理异常被 `except Exception: pass` 吞掉后仍释放运行锁，`kill_tree()` 只返回已发 kill 的 PID、不报告是否真的退出；②陈旧锁接管是「读 → 判陈旧 → unlink → O_EXCL」，两个入口会互相删掉对方刚建的有效锁。只改测试基础设施，不涉及游戏业务。

### 修改
- `dev_tools/guarded_unittest.py`：`terminate_tree()`（`CleanupResult`：已请求终止 / 核验已退出 / 未确认；有界 6 轮 × 5 秒；查询或权限异常=无法确认，不当已退出）；清理只在 `finally` 做一次，`cleanup.ok` 才释放锁，否则保留运行记录（`cleanup_incomplete`，列出未确认进程身份）、退出码 16、摘要同时保留原始原因与清理结果；`RunLock` 拆成资源锁（`guarded_unittest.mutex`，独占 OS 文件锁，进程退出即释放）+ 运行记录（`guarded_unittest.lock`，仅信息）；已发现的后代身份随采样写进记录。
- `tests/test_guarded_unittest.py`：27 → 58 项（清理边界替身、清理失败贯穿 `run_guarded`、屏障 / 事件固定交错的接管竞争、两个真实进程同时争抢、守护被强杀后的接管与后代残留）。
- 文档：TESTING §5.ac（清理核验、运行锁、清理失败处理、限制、入口自身测试）、DECISIONS D056（修订，不新增 ADR）、AI_CONTEXT §4.170、CLAUDE.md / AGENTS.md 验证规则补一句 14 / 16 的处理。

### 测试
- 修改前的入口副本上跑 5 个只依赖公共接口的用例 = 5 项全失败；新实现 5 项通过；对新实现做 6 处变异，相关用例全部失败。
- 经入口：`tests.test_guarded_unittest` 58 项 OK（连续两次 65.8 / 65.5 秒，峰值 244 / 117 MiB；中途一次失败是新测试里 kill 后再按 PID 构造 Process 的竞争，已修）；事故相关 70 项 OK（4.3 秒，451 MiB）。全量没有重跑，3852 项仍是 §4.169 的修改前快照。日志在 `D:\Codex\outputs\20261031_守护入口复审修复\`。

### 未验证 / 未处理
- 采样式进程树发现不保证捕获采样间隔内创建并脱离的进程；守护被强杀时记录里可能缺少最后一个间隔内新建的后代；不覆盖手工 `python -m unittest`。未提交。
