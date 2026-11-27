# 项目开发路线图

> 回答「接下来做什么、优先级、前置依赖、什么时候才能做」（最后核对：2026-11-27）。
> 本文档为**覆写型当前清单**：2026-11-27 瘦身前完整原文快照见 [ROADMAP_before_slimming_2026-11-27.md](archive/ROADMAP_before_slimming_2026-11-27.md)；原已完成总表、历史主线、已取消项与 Level C 分段历史归档见 [ROADMAP_done_2026-09_11.md](archive/ROADMAP_done_2026-09_11.md)。禁止在顶部堆叠 `>` 增量流水，不在待办中复制临时测试数字或本机路径（D073）。

---

## 当前阶段目标

1. 严格遵循 **D070**（开发前先问清需求与保留范围、提交具体方案经用户审核后再实施）。
2. 遵循 **D069**（局部最小离线验证：编译 + diff + 1～3 关键场景，阶段预算 120s），尽早交付待实测版本与最短实测步骤，不以离线堆 mock 替代真机。
3. 结合实机日志与报错原图按模块小步闭环，逐项核销下方 Level C 待验证清单。

---

## 活跃待办（未完成开发项）

### P0

- **同心之兰双实例互赠（P5 日志回填，D029）**：任务骨架（`tasks/XinLan/`）与适配器已接入并完成初跑，待双开实机回传 `log/*_oas*.txt` 及 `log/instance_sync/` 账本/journal 后，核对各步耗时并回填 `PROTOCOL_PARAMS`（`budget` / `min_attempt_cost` / `DAILY_RESET` 占位）；绑定邀请不建议自动化（或需独立识别+弹窗消失判据）。
- **式神活动配置页 OASX 前端展示（D038 / D039）**：后端 `GET /args/layout` 与体力随机区间已就绪，待在 OASX 前端仓实现玩法多选排序、分组折叠与 `activity_ap_range_min/max` 区间控件。
- **道馆配置页 OASX 前端展示（D059）**：后端 `GET /{script}/Dokan/args/layout`（`kind = "dokan"`、`version = 1`）已就绪，OASX 前端 renderer（模式下拉绑定 `welfare_mode`、分区首次折叠 `initial_expanded`、紧凑七天选择器、空选提示与摘要/兜底）**尚未实现**，待在 OASX 前端仓开发。
- **FIRE FSM 剩余接入**：① 评估契灵 `I_BALL_FIRE` 是否拆出三态适配（`BondlingNumberMax` 语义特殊）；② 补齐八岐野队 `I_OROCHI_WILD_FIRE` 资产与 ROI 标定并收口断链；③ 活动大富翁 / 伪神降临的 FIRE 与 Fatigue；④ L2-3 Batch B/C/D/E/F（待逐项评估或真机依据）。
- **Navigation「突破 → 式神录」只读审查**：排查 `goto_page(page_shikigami_records)` 前后是否存在多余点击或异常回退链，先产出清单。

### P1

- **T4-4 `harvest_card` 状态驱动改造**：`tasks/KekkaiActivation/script_task.py` 目前为无截图 8 连点，需结合 Level C 观察「点击后期望状态」后做局部 State → Action → Verify 落地（已锁定 characterization 基线）。
- **`GeneralBattle.exit_battle()` 有界化**：退出确认键认不出时当前无界每 6 秒重击 `GB_EXIT`，需改为有界等待确认与重试（`AbyssShadows` / `Duel` 同类）。
- **SixRealms 只读调查与商店 P1/P2**：① 调查 `oas2` 偶发开局识别为 `page_battle` 导致跳转式神录失败的现场截图；② 商店刷新后 HUD 滞后、动画稳态 ROI 覆盖、月之海 300 / 孔雀国 200 价差等 6 项待真机帧后再改。
- **SwitchSoul V3+**：待采集 6 张预设页实机信号截图后评估 FrameWait 判顶、by-name 找组找队有界化与「目标预设已生效」确认（附修复 Dokan 不可达 OCR 分支、`-1,-1` 越界抛 `ValueError` 等审查项）。
- **组队次数同步推广**：御魂 `TeamSession` 机制通过 Level C 后，逐项核对并接入探索 / 永生之海 / 日轮之陨 / EvoZone / 异界黄昏 / 契灵。
- **GlobalGame 好友邀请粮协资源重标**：`g_cat_food` / `g_dog_food` 识别框 `(675,516,43,46)` 小于模板，待新界面整屏截图重标；工作区 4 张孤儿 PNG 去留待用户决定。
- **ActivityShikigami 遗留收敛**：`BaseAct.before_run` 全局 monkeypatch `page_battle_result` recognizer 收敛；评估大富翁/伪神降临是否存同族无界循环（参考 `fake_god.py`）。

### P2

- **T5-1 BehaviorTrace 覆盖 `swipe_adb` 直连**：决定 `KekkaiUtilize.perform_swipe_action` 与 `KekkaiActivation.check_card_num` 补观测还是迁移到 `Control.swipe`。
- **T5-3 OASX 点击与轨迹可视化前端**：后端 `GET /stats/{script_name}/behavior/clicks` 已完备，待 OASX 前端实现散点/折线与 4 维过滤。
- **T7-1 人工热点标定与私有结算迁移**：待用 `runtime_roi_probe.py` 采集 `I_FIRE` 运行时 ROI、`large_click_roi_review.md` 人工确认 001~198、BehaviorTrace 补 `page`/`ROI` 元数据；后续评估 Phase B/C（`BondlingFairyland` / `SixRealms` / `Exploration` / `MetaDemon` 私有结算接入 V3）与 Exact Coordinate ROI Discovery。
- **补回被合并 `73bcafcb` 冲掉的寮祈愿修复**：开寮祈愿前按三方合并补回同行搜索区、中文输入、单次赠予与页标资源。
- **Chess `Unknown frame id`（10s TTL）**：长时间操作后超服务端 10 秒 TTL 的帧过期重截或 `KeyError` 恢复。
- **OASX 个人突破 PyQt i18n 同步**：`zh_CN.xml` / `.qm` 文案待同步。

### 暂缓任务

- **百鬼棋局上游 `73d4ae84` 未取部分**：内置 7 套阵容改 JSON、海国迁移、每局重载、不重复装同名纹章等改动现有已确认行为，暂缓待定；主动投掷/活动看门狗/刷满改排周一已明确排除。
- **T6-1 `module/atom/cBezier.py` 孤儿文件**：无消费者，低收益暂不删。
- **T6-2 `Script._publish_fatigue_state` 2 秒轮询**：无退出条件且禁用疲劳仍推，待连同 OASX 前端评估。
- **T6-3 GeneralBattle 默认区间**：基类 `PREPARE_CLICK_DELAY_RANGE=(3.0,3.0)` 等调整影响全战斗任务，需真机逐任务评估。
- **L1 / L2 / Swipe 后续候选**：L2 Batch B、NEEDS_C 共 9 处（其中 C0 `human` 7 处：`GeneralInvite` ×5 / `GeneralBattle` 准备弹窗 ×2；另新增 2 处 `rule/R9` 候选：`DemonRetreat._open_demon_retreat` 与 `SixRealms` `BasePeacockKingdom._confirm_boss_giveup_dialog`，尚待真机/复核）、`ui_click*` 透传 `policy`、Navigator 逐 edge 元数据、`RR_AGAIN_CONFIRM_DELAY` 归属、`Control.multi_click` 死代码与 `nemu_ipc` 长按未注册、ROI 质量审计；全仓 Swipe 剩余 3 项（`list_find` / `KekkaiActivation` / `RyouToppa`）；`KekkaiActivation` 静默窗口/cooldown 与 `Dokan` 跨进程 Restart 持久化评估。

---

## 需要真机验证的任务（Level C，按模块分组）

> 以下条目已完成 Level A/B 离线改造或验证，**不得标 VERIFIED**；请在获得实机窗口或实跑日志后逐项核销（详尽历史背景见 [DEVELOP_LOG.md](DEVELOP_LOG.md)、瘦身前完整原文快照 [ROADMAP_before_slimming_2026-11-27.md](archive/ROADMAP_before_slimming_2026-11-27.md) 与分段历史归档 [ROADMAP_done_2026-09_11.md](archive/ROADMAP_done_2026-09_11.md)）。

### 百鬼棋局（Chess）

- **上卡受阻全盘 1..12 恢复（2026-11-27）**：在 `oas2` 复测满人口且棋盘含 `unknown` 格时不再反复盲拖目标格；1 号位等非传统回收位存在副本/非阵容单位时切片有界 1 次核名并只收 1 只重扫上阵；无待补卡或余时不足不无谓减员。
- **御魂空留解除、同名核名护星与重复式神让位（2026-11-27）**：核对场上式神不再为未拿到指定御魂锁空槽、满手清仓先释放未上阵预留走通用分配；缓存失效/升星占格先单次核名再拖且拒认异常降星；站定本体在副本占位挡部署时护本体收副本并重扫上阵。
- **准备阶段整理流程首版 `CHESS-PREP-ARRANGE-V1`（2026-11-26，11-27 补修 `P1-1`/`P2-1`/`P2-2`）**：核对拖卡回弹正确判 `hand_consumed=False` 不误锁、被顶他阵容重扫归位、按配置前后排选通用魂按实际格落点、穿戴连败后触发高优核名（成功清标/失败冷却）、`direct_only` 对未验证/错位占用格暂缓而不提前核名或顶回他卡（同时放行空位卡并在后续先搬后上）、`PREPARE_FOLLOWUP` 切片推进无忙循环且经济 `blocked` 后本回合不重复开关店（下回合恢复）、不误吞开战、站定金鱼硬保护与 `board_slots` 两帧防抖。
- **`detail_name` OCR 防污染与标注器候选调参（2026-11-26）**：核对稳态门控+白字分离是否消除「式神名+玩家名」透底错读与 `145` 阈值误清、评估 `O_DETAIL_NAME` 是否收窄为 `(996,100,162,32)`、跑通读名→解除 pending→配御魂闭环，并用 Web 标注器实测红光手牌阈值。
- **直接先上卡、单次详情上限与跨回合待核实调度（2026-11-26）**：核对「空格变占+消耗」0 点击快确认、错位金鱼先搬后上、新牌→找鱼→旧 pending 后置顺序与每回合合计最多 1 次旧 pending 轮转、以及 `save_error` 详情未开留证图（另待收集后处理 12 格合卡纠位与 `I_SHIKIGAMI_SPECIFICS` 校准）。
- **备战顺序、提前找鱼与跨轮续查（2026-11-25）**：核对先直上可落位卡→`preparation_initial` 提前找鱼（`6→5→11→12`）→余时再查堵格/经济买卡补上阵与补查鱼、放好金鱼后跳过零检查、`3/4/6/9s` 时限与挡位搬鱼 `'blocking'` 来源保护。
- **装备清理、购卡预算与人口交叉判断（2026-11-24~25）**：重点核对普通御魂拖卖实效、同张卡 3 次购卡总预算与第 3 击延迟确认、`<=9/10` 零卖卡、`board_visual` 满员交叉判据、左栏「荒川 ≥ 2」补采 `1`/`2` 实图、小纸人判空稳定率与 8 号金鱼勾玉框表现。
- **Frame 完整吸收与阵容编辑器（2026-10-25~29，11-25 扩展勾玉框）**：重启 OAS 后跑普通/首领多局，核对手牌/商店/纹章/鼬乐币/24 个 `52×50` 勾玉框识别率、低配多角标阈值、购卡两帧确认、红叉浮窗关闭及 `/tool/chesslineup` 自定义阵容上阵效果。

### 福利道馆（Dokan）

- **放弃清屏与再战消失确认（2026-11-26）**：重启跑完整两馆，核对放弃确认后 `1.5s` 点安全右空白清战绩弹窗不误触、点再战确认连续 2 帧消失（遇遮罩吃点击最多补至 3 次）后立即回庭院并自有效点击计 `120s`、第二馆重读机会数开馆或收尾。
- **观察层局部动态徽记放过（2026-11-26）**：同屏多枚紫色弯月等闪烁徽记时一轮判稳（`ignored local change in observe`），且慢速滚动与大面积抖动仍被拦截。
- **有效刷新释放与触底过冲回弹（2026-11-25）**：继实盘已命中前 3 轮释放后，续验连续刷新 `>=6` 次及短列表不再撞 `GameTooManyClickError`，以及 `|dy|<=150px` 过冲回弹复位重滑正常扫「鑫」或两次 `static` 交刷新。
- **单卡锚点、赏金校验与找馆页解耦（2026-11-23~24）**：核对滑前补拍与赏金图标校验避开底部半张卡、名义 `120px` 手势在真实动画/亮度下的位移稳定性与 `±2px` 容差、异常切页/弹窗即留图转人工；采集投票选中阶段与重启地图进行中道馆截图。
- **每周运行日、道馆配置与前置衔接（2026-10-28~11-05）**：核对福利七天星期后端配置保存与跨周调度、每馆前置我方建馆检查、准备后 `1.85s` 缓冲、一键预设无弹窗路径、集结超 5 分钟不卡死及 `DOKAN-LIST-01` 完整两馆闭环（OASX 前端 `layout` 展示待前端实现后另行核对）。

### 六道之门（SixRealms）

- **孔雀国宁息确认、无轰雷放弃、战败确认与准备页隔离（2026-11-26，11-27 补修 `P1-2`）**：重启重载后核对 `PK_PK_STORE_STILLIN` 长期稳定、开局/战过小怪无轰雷到达 Boss 时有界放弃并拿单次计数（30s 超时直接抛 `GameStuckError` 退出不重入）、续打直达 Boss 不误放、战败放弃 `I_UI_CONFIRM` 兼容，以及开局三选一首击未切屏保持 `page_pk_prepare` / `page_ms_prepare` 不串页死循环。
- **孔雀国唤息/退出与轰雷扣费核对（2026-10-12）**：核对唤息确认不再连点取消、退出不误点、以及轰雷扣费 200 校验（刷新后 HUD 滞后需真实商店与弹窗图）。

### 超鬼王（MetaDemon）

- **恢复原功能与当前队列可选循环（2026-11-11~13）**：核对庭院直达两入口及切栏预算、主页/鬼王页模板、`use_current_queue` 召唤/末票等待/准备页提前交接/自动喝茶及疲劳 OCR 下降、不喝茶按 60 恢复调度、连续两帧无鬼王收尾及保留原功能配置不回归。

### 双实例同步、组队与轮换

- **同心之兰双实例互赠与异常恢复（2026-10-22~11-23）**：双开实测点空白关福袋、名称 OCR、`DigitCounter`、绑定邀请排斥、好友页连续羁绊弹窗关闭与回退重定位，并回传日志/账本。
- **组队会合修订/补强/启动宽限（2026-10-23）**：核对空闲 5 秒唤醒、同重启 `peer_reconnecting`/`peer_starting` 进门等、御魂以队长计数为准及离线推送。
- **御魂 → 个人突破轻量循环与配置界面（2026-10-24~25）**：双开互填配置开启循环，核对开关消费、步骤插入更高优先级（含结界轮换结果兼容 11-20）、停止/强杀收口、退四中途停止及 OASX 配置分组回显。

### 御魂切换（SwitchSoul）

- **数字模式第 8 组、按名称搜索与回弹修复（2026-10-06~11-20）**：V1/V2 数字切换初验已过（持续观察偶发卡顿与分组数）；待验数字第 8 组、按名称长列表翻页与回顶防回弹、`NAME_MOVED=0.03` 实测分布、分组固定两次点击与契灵替换确认框。

### 日常与其它副本任务

- **悬赏封印（WantedQuests）**：新详情整行 OCR 与取消追踪后画面（补录取消追踪后整屏图）、列表标签进度补读与备用窄条（11-18）、执行记录隔离不跨怪误跳（`D054`）。
- **地域鬼王（AreaBoss）**：不同鬼王去重与空名继续挑战匿名计数（`D066`）、明确战败最多 3 次重试。
- **每日琐事（DailyTrifles）**：吉闻 `RANDOM_BOTTOM` 关闭、庭院事务 12/20 点多轮领取、买体力价格/次数与连续签到跳转、庭院寿司、领取邮件红点与无红点 `COPY3` 及 `20s` 时限、每日调度、L2 反应延迟与满级取消弹窗。
- **契灵（BondlingFairyland）**：创建房间跳过 15 秒等待并核对默认私人设置、队长/队员锁队衔接与队员打满不滞留。
- **探索（Exploration）**：Boss 胜利跳过地图奖励三态直退（单人/队员、外层宝箱影响与 30s 上限）、Rotation 开关归用户所有、Chapter FrameWait 参数与 solo Fatigue。
- **结界突破（RealmRaid）与寮突破（RyouToppa）**：九宫格 1→9 与只剩最后目标退四、`CONTINUE` 跳过、退四 `ensure_lock` 恢复与 settle 窗口、`_fire_again` 窄战斗判据与确认弹窗 reaction、`I_EXIT_ENSURE` 退出确认；寮突破进攻过渡 6s 窗口与 `C_AREA_1` 落点分布。
- **式神活动（ActivityShikigami）**：普通爬塔二层导航/资源 OCR/专用结算单击 `(0.45,0.85)`、首领爬塔锁定/额外奖励 `DigitCounter`、入口回退 `20s` 与未知页 `20s` 防停滞。
- **首领退治（DemonRetreat）、秘闻（Secret）、狩猎（Hunt）、集体（CollectiveMissions）、永生之海（EternitySea）、结界蹭卡（KekkaiUtilize）**：
  - 首领退治：集结 185 秒等待+金色退治单次点击、周六管理员主动开启；
  - 秘闻：首次通关结果页与奖励页安全区结算、山兔竞速未通关行勾玉选关；
  - 狩猎/集体/永生之海：麒麟/阴界与随机延迟、集体任务换一个不空捐、永生之海 50%/100% 金币加成开关与结束仅关本次开启项；
  - 结界蹭卡：单向分区搜索、K1~K4（`SWIPE_DISTANCE_RANGE=(140,180)` + 斜度 + FrameWait + `I_IS_SELECTED` 锚点去重）、Scheduler v1 静默/cooldown 与好友两空位放置。
- **八岐大蛇结算宠物弹窗（`D055`，2026-10-31）**：真机核验御魂结算内「发现宝藏」`I_PET_PRESENT` 独占连续新帧关闭、1 秒间隔与次数/时长上限是否稳定不漏关。

### 基础架构、交互层与工具

- **L1 / L2 / Settlement / 滑动 / 观测 / UI 适配**：L1 执行器落点与 BehaviorTrace 一致性；L2 首批 reaction 区间与 Batch A 四个 FIRE FSM；Settlement Micro-Burst v1.2（含 `budget=2`、`0.30~0.60s` 观察间隔、9 次上限、`D025` `page_reward` 宝袋布局交接连续 2 帧重选区及 `I_FALSE` 战败改点 `C_RANDOM_SAVE_RIGHT`/`C_RANDOM_SAVE_BOTTOM` 推进与皮肤失败模板命中）及 V3 安全区；全仓 `BaseTask.swipe_trajectory` 迁移消费方与 `list_find` FrameWait 参数标定；`TouchSwipeModel` v2 尾段真机运动学验收；Fatigue 各任务安全节点；2026-10-10 UI 更新全资产与 `annotator` 帧隔离（通过后撤掉同配置禁用实时采集临时规避）；ManualClickRecorder / BehaviorTrace 开销与样本采集。

---

## 已完成与历史归档

- 瘦身前完整原文快照（2026-11-27 原始字节）：[ROADMAP_before_slimming_2026-11-27.md](archive/ROADMAP_before_slimming_2026-11-27.md)。
- 分段历史归档（原已完成总表、OAS Architect V1.2 前四阶段记录、已取消改造与 Level C 分段原文）：[ROADMAP_done_2026-09_11.md](archive/ROADMAP_done_2026-09_11.md)。
