# RealmRaid 状态驱动迁移前静态收口结果

> 2026-09-02。只读审查 + 建模 + characterization，**未改任何 RealmRaid 生产行为**
> （`tasks/RealmRaid/` 对 HEAD 零 diff）。方法论与 `docs/Kekkai状态机静态收口.md` 一致：
> 静态收口 → characterization → production diff = 0。
> 源码基准：`tasks/RealmRaid/{script_task,config,assets,page}.py`（HEAD `2cdf3a05`，工作树
> 对该目录无改动），逐行核实。

---

## 1. 总结

- **当前运行模型**：`run()` 是一个 `while 1` 主循环——「查票 → `find_one` 选目标 →
  `fire(index)` 点目标+点进攻 → `run_general_battle()` 打 → 三胜奖励 / 刷新 / 失败分支 →
  下一轮」。战斗本身完全委托给成熟的 `GeneralBattle` Page FSM；RealmRaid 自己只负责
  **突破页面内**的目标选择、进攻、刷新、票数与退出。
- **最关键的现状**：`fire()` 判定「已进入战斗」的唯一依据是 **旧页面标识 `I_RR_PERSON`
  消失**（`if not self.appear(self.I_RR_PERSON): return True`）——没有任何战斗页面的正向
  标识、没有 timeout、没有 retry 上限。且 `fire()` **永远不可能返回 False**（`while True`
  内无 `break`，尾部 `return False` 不可达），因此 `run()` 里两处
  `if not self.fire(index): continue` 是**当前不可达分支**。
- **本轮是否改变生产行为**：**否。** 只新增 1 个 characterization 测试文件 + 本文档 + 6
  文档同步。生产 diff = 0。

---

## 2. 当前完整控制流

```
run()  [入口]
 ├─ goto_page(page_realm_raid)                       # Navigator, Timer(30), 失败 raise
 ├─ check_ticket(number_base)  == False →            # 票不足 / 已达 number_attack
 │     goto_page(page_exploration); set_next_run(success=False, finish=True); raise TaskEnd
 ├─ (switch_soul.enable?)          goto_page(page_shikigami_records); run_switch_soul(...)
 ├─ (enable_switch_by_name?)       goto_page(page_shikigami_records); run_switch_soul_by_name(...)
 ├─ goto_page(page_realm_raid)                       # 切魂后必须回突破页
 ├─ screenshot(); appear(I_FROG_RAID)?               # 呱太活动首次进入的弹窗
 │     while 1:  screenshot; not appear(I_FROG_RAID) → break
 │               appear_then_click(I_FROG_RAID, interval=1) → continue      # [无上限]
 ├─ ensure_lock(lock_team_enable)                    # while 1 点锁/解锁直到目标态  [无上限]
 ├─ frog = is_frog(True)                             # appear(I_FROG_MEDAL)
 │
 └─ while 1:                                         # ★ 主循环 [state-bounded]
      screenshot()
      check_ticket(number_base) == False → break                        # 退出点 1
      medal, index = find_one(False)                 # 复用上面这帧
      (medal, index) == (None, None):                # 没有可打的目标
        when_attack_fail == CONTINUE → check_refresh() ? continue : (success=False; break)
        else                          → success=False; break            # 退出点 2/3
      lock_before = general_battle_config.lock_team_enable
      handled_first_target = False
      index == 1 and exit_four:                      # ★ 左上角第一个 + 四连快退
        fire(1) == False → continue                  # ← 当前不可达（fire 恒 True）
        run_general_battle(quick_exit) ; fire_again()      ×4 组
        last_battle = run_general_battle(general_battle_config)          # 第 5 次常规打
        handled_first_target = True
      elif check_medal_is_frog(frog, medal, index):  # 呱太 → 本轮改成不锁阵容
        general_battle_config.lock_team_enable = False
      not handled_first_target:
        fire(index) == False → continue              # ← 当前不可达
        last_battle = run_general_battle(general_battle_config)
      lock_before → 还原 lock_team_enable
      reward_detect_click(False) → continue          # 三胜奖励已处理，重开一轮
      three_refresh and appear(I_RR_THREE,0.8):
        check_refresh() ? continue : (success=False; break)              # 退出点 4
      not last_battle and when_attack_fail == REFRESH:
        check_refresh() ? continue : (success=False; break)              # 退出点 5
      not last_battle and when_attack_fail == EXIT → break               # 退出点 6

 goto_page(page_exploration)
 set_next_run(task='RealmRaid', success=success, finish=True)
 raise TaskEnd

fire(order):                                          # ★ 目标点击 + 进攻
  click = partition[order-1]
  wait_until_appear(I_RR_PERSON)                      # 无 wait_time → 无超时
  device.click_record_clear()
  while True:                                         # [potentially unbounded]
    screenshot()
    not appear(I_RR_PERSON) → return True             # ★★ 唯一的「进入战斗」判据
    appear_then_click(I_FIRE, interval=1) → continue
    click(partition[order-1], interval=2) → continue
  # 以下不可达：logger.info(...) ; return False

fire_again():                                         # 失败结算页再战
  wait_until_appear(I_FIRE_AGAIN)                     # 无超时
  while True:                                         # [potentially unbounded]
    screenshot()
    not appear(I_FIRE_AGAIN) → return True            # 同样是「标识消失 = 成功」
    appear_then_click(I_SHOW_AGAIN,   interval=2) → continue
    appear_then_click(I_FRESH_ENSURE, interval=2) → continue
    appear_then_click(I_FIRE_AGAIN,   interval=2) → continue
  # 不可达：return False

check_ticket(base):
  base<0 or base>30 → base=0（clamp + warning）
  wait_until_appear(I_BACK_RED); screenshot()
  cu,res,total = O_NUMBER.ocr(image)
  total==0 → reward_detect_click(True) → 用新帧重新 ocr    # 聊天框遮挡兜底
  cu==0 and cu+res==total → False（没票）
  cu+res==total and cu<base → False（不够基准）
  init_tickets = cu（仅第一次锁存）
  init_tickets-cu >= number_attack → False（已达次数）
  → True

find_one(screenshot):
  when_attack_fail==CONTINUE:
    for i, roi in enumerate(false_roi):               # 9 格
      false_image.roi_back = roi
      appear(false_image) → **原地涂黑** image[partition[i].roi_back] = 0
  target = order_medal.find_anyone(image)             # 不传 frame_id
  target → 用 target.front_center() 落在哪个 partition.roi_front → return (target, i+1)
  否则 return (None, None)

check_refresh(screenshot):
  not appear(I_FRESH) → return False（CD 中）
  while 1: appear(I_FRESH_ENSURE) → break ; appear_then_click(I_FRESH, interval=1)   [无上限]
  while 1: not appear(I_FRESH_ENSURE) → return True ; click(I_FRESH_ENSURE, interval=1) [无上限]
  # 不可达：return False

reward_detect_click(screenshot):
  wait_until_appear(I_BACK_RED)                       # 无超时；等回到突破页再判奖励
  ui_click_until_disappear(I_SOUL_RAID, interval=1.2) # BaseTask while 1，无超时
  text = O_TEXT.ocr(image)
  text 含中文（聊天框遮挡）:
    while 1:                                          # [potentially unbounded]
      screenshot(); result = O_TEXT.ocr(image)
      不含中文 且 匹配 (\d+)/(\d+) → return True
      appear_then_click(I_SOUL_RAID, interval=1.5) → continue
  → False

ensure_lock / is_frog / check_medal_is_frog：见 §3 表
medal_fire() / is_ticket()：**全仓零调用方的死代码**（§14 R-R7）
```

---

## 3. State Matrix

| # | State | Recognition | Action | ExpectedState | Current Verify | Current Wait | Failure |
|---|---|---|---|---|---|---|---|
| S1 | ENTRY | — | `goto_page(page_realm_raid)` | 突破页 | Navigator 两帧稳定确认 | `Timer(30)` | `raise GamePageUnknownError` |
| S2 | TICKET_CHECK | `I_BACK_RED` + `O_NUMBER` OCR | 判票 / `reward_detect_click` 兜底 | 有票且未达上限 | OCR 数值条件（3 条） | `wait_until_appear(I_BACK_RED)` **无超时** | `False` → 早退 / `break` |
| S3 | SOUL_SWITCH | — | `goto_page(page_shikigami_records)` + `run_switch_soul*` | 御魂已切 | 委托 SwitchSoul 组件 | 组件内部 | 组件异常上抛 |
| S4 | FROG_POPUP | `appear(I_FROG_RAID)` | `while 1` 点它直到消失 | 弹窗关闭 | `not appear(I_FROG_RAID)` | `interval=1`，**无总超时** | 潜在无限 |
| S5 | LOCK_STATE | `I_LOCK`/`I_LOCK_2`/`I_UNLOCK`/`I_UNLOCK_2`(0.9) | `while 1` 点锁定/解锁 | 达到目标锁定态 | `appear(目标态, 0.9)` → break | `interval=1`，**无总超时** | 潜在无限 |
| S6 | TARGET_LIST | `order_medal.find_anyone` 命中勋章图 | 定位到 9 宫格序号 | 有可打目标 | `front_center()` 落在某 `partition.roi_front` | 无（复用主循环这一帧） | `(None,None)` → 刷新 / `break` |
| S7 | TARGET_SELECTED → FIRE_READY | `I_RR_PERSON` 仍在 | `click(partition[i], interval=2)` 打开目标详情 | 详情页 + `I_FIRE` 就绪 | **无**（不等 `I_FIRE`，靠下一轮循环再判） | `interval=2` 节流 | 下一轮继续点 |
| S8 | BATTLE_ENTERING | `I_FIRE` 出现 | `appear_then_click(I_FIRE, interval=1)` | 进入战斗 | **仅 `not appear(I_RR_PERSON)`**（旧页面标识消失） | `interval=1`，`while True` **无超时/无 retry 上限** | 潜在无限；无失败返回值 |
| S9 | BATTLE | GeneralBattle `detect_page_in` | `run_general_battle(config)` | 战斗结束 | GeneralBattle Page FSM（成熟） | `battle_timer` / `_tick_timeout` | 返回 `False` |
| S10 | BATTLE_RESULT | GeneralBattle `page_battle_result` | `_handle_result` 覆写 | 退出结算 | `quick_exit`：`not appear(I_FALSE)` → EXIT_WIN/LOSE；否则 `super()`（Contract v2 点 RD） | RealmRaid `SETTLEMENT_CLICK_INTERVAL_RANGE=(0.65,0.95)` | GeneralBattle 兜底 |
| S11 | FIRE_AGAIN（仅 exit_four） | `I_FIRE_AGAIN` | 点 `I_SHOW_AGAIN`/`I_FRESH_ENSURE`/`I_FIRE_AGAIN`(interval=2) | 再次进入战斗 | **仅 `not appear(I_FIRE_AGAIN)`** | `while True` **无超时** | 潜在无限 |
| S12 | THREE_WIN_REWARD | `O_TEXT` OCR 出中文（聊天框遮挡） | `ui_click_until_disappear(I_SOUL_RAID)` + `while 1` 点 | 票数区恢复 `n/m` | OCR 正则 `(\d+)/(\d+)` 且无中文 | `interval=1.2/1.5`，**无总超时** | 潜在无限 |
| S13 | REFRESH | `appear(I_FRESH)` | 点 `I_FRESH` → 点 `I_FRESH_ENSURE` | 目标列表已刷新 | `appear(I_FRESH_ENSURE)` → 再 `not appear(...)` | 两个 `while 1`，`interval=1`，**无总超时** | `I_FRESH` 不在 → 直接 `False`（CD） |
| S14 | FAILED（业务失败） | `last_battle == False`（`run_general_battle` 返回） | 按 `when_attack_fail` 分支：REFRESH / EXIT / CONTINUE | 刷新后继续 / 结束任务 | 返回值 | — | `success=False` → `break` |
| S15 | RETURNING / COMPLETE | — | `goto_page(page_exploration)` + `set_next_run` + `raise TaskEnd` | 探索页 | Navigator | `Timer(30)` | `raise GamePageUnknownError` |

---

## 4. 目标选择

1. **第一次截图**：主循环开头 `self.screenshot()`（`run()` 内），随后 `find_one(False)`
   **复用同一帧**（`screenshot=False`）。
2. **目标识别**：`self.order_medal.find_anyone(image)`——`order_medal` 是按配置
   `order_attack`（默认 `'5 > 4 > 3 > 2 > 1 > 0'`）解析出的 `ImageGrid`，按星级优先顺序
   逐个模板匹配，**返回第一个命中的 `RuleImage`**。调用**不传 `frame_id`** → 不复用批量
   匹配缓存。
3. **点击坐标产生**：`find_one` 只返回 `(target, order)`；真正点击在 `fire(order)` 里，
   点的是 `self.partition[order-1]`（`C_PARTITION_1..9` 静态 `RuleClick`）。坐标经
   `RuleClick.coord()` → `ClickSampler.sample(roi_front)` = **`LEGACY_UNIFORM`**（T7 默认
   路径，RealmRaid 未做 Point opt-in）。
4. **点击之后是否立即截图**：是——`fire()` 的 `while True` 每轮开头都 `self.screenshot()`。
5. **是否等待某个明确 `I_*`**：**否**。点完 `partition` 后不 `wait_until_appear(I_FIRE)`，
   靠下一轮循环里的 `appear_then_click(I_FIRE, interval=1)` 顺带判断。
6. **是否固定 sleep**：`fire()` 内**没有** `sleep`；节流靠 `interval`（`I_FIRE` 1s /
   `partition` 2s）。
7. **是否直接进入下一步**：不是「直接」，但也没有显式确认——循环每轮重新判断。
8. **目标没成功打开会怎样**：`I_RR_PERSON` 仍在 → 循环继续 → 2 秒后**再点一次同一个
   partition**，1 秒节流下反复尝试 `I_FIRE`。
9. **是否再次点击**：是，无限次（受 `interval` 节流）。
10. **最大重试次数**：**无**。
11. **timeout**：**无**（`wait_until_appear(I_RR_PERSON)` 也不传 `wait_time`）。

> **Action → Verify gap**：`click(partition[i])` → 期望「目标详情页打开、`I_FIRE` 出现」，
> 当前**没有对 `I_FIRE` 出现的显式验证**，只有「反复点 + 反复试」。

---

## 5. 进攻按钮 / `I_FIRE`

1. **如何确认按钮出现**：`appear_then_click(self.I_FIRE, interval=1)` —— `appear` 与点击
   合一，`interval` 只是**节流**不是等待。没有先 `appear(I_FIRE)` 再点的两段式。
2. **点击前是否重新截图**：是。`fire()` 每轮 `while True` 开头 `self.screenshot()`，
   `appear_then_click` 在同一帧上判断并点击。
3. **是否存在 stale frame**：`fire()` 内**不存在**——判断与点击在同一帧内完成，且每轮重截。
   （RealmRaid 的 stale 风险在别处，见 §12。）
4. **点击后 ExpectedState**：应为「进入战斗准备页 / 战斗页」。
5. **当前代码实际验证什么**：只验证 **`not appear(self.I_RR_PERSON)`** ——
   `I_RR_PERSON` = `res_rr_person.png`，`roi_front=(1203,236,56,100)`，`threshold=0.8`，
   是突破页右侧的「个人」栏标识。
6. **是否只是检查原页面标识消失**：**是，确实只有这一项。**
7. **页面标识消失是否可能由动画 / 弹窗 / 短暂遮挡 / 匹配抖动引起**：**可能**。
   `I_RR_PERSON` 的 ROI 在右侧边栏，任何覆盖该区域的弹窗（活动公告、好友邀请、体力提示）、
   页面切换动画的中间帧、或模板匹配在 `threshold=0.8` 附近抖动，都会让这一帧 `appear`
   返回 False → `fire()` 立刻 `return True` → `run()` 直接调用 `run_general_battle()`。
   届时 `GeneralBattle` 会在非战斗页上跑它自己的 `_handle_missing_battle_page` 兜底逻辑
   （有 `reward_no_battle_ts` / `_tick_timeout` 保护），**不会立即崩**，但会浪费一整段
   battle timeout 并可能误记一次 `current_count`。
8. **是否检查战斗页面明确标识**：**否**。`fire()` 源码内无 `page_battle` / `detect_page_in`
   / `I_EXIT` / `get_current_page`（测试锁定）。
9. **timeout**：无。
10. **有限 retry**：无。

> 本轮**未**把 `I_FIRE` 接入 T7 `HABIT` —— `normal_button` profile 仍缺真实 runtime ROI 的
> Level C 标定（见 `docs/AI_CONTEXT.md` §4.30），点击坐标模型不属于本轮。

---

## 6. 战斗进入判定

**结论：是的，当前仍然是 `old state disappear → assume battle`。**

### Current inference

```
fire():   not appear(I_RR_PERSON)      → return True   → run() 立刻 run_general_battle()
fire_again(): not appear(I_FIRE_AGAIN) → return True
```

两处都是「旧标识消失即成功」，且都**没有**正向确认新状态。

### 是否可能把「旧页面暂时识别失败」误认为「进入战斗成功」

**可能。** 触发条件：任何让 `I_RR_PERSON`（或 `I_FIRE_AGAIN`）在某一帧匹配不到的因素——
弹窗遮挡、切页动画中间帧、模板匹配抖动、截图撕裂。当前代码对单帧判否没有任何
「连续 N 帧确认」或「正向标识确认」保护。

### Stronger future candidates（只分析，不实施）

| 方案 | 说明 | 需要什么 |
|---|---|---|
| battle semantic marker | 等 `page_battle_prepare` / `page_battle` 的正向标识出现 | GeneralBattle 已有 `detect_page_in`，可直接复用 |
| GeneralBattle page recognition | 把「是否已进战斗」交给 `GameUi.detect_page_in(...)` 判定 | 真机确认突破→战斗过渡期的可识别帧 |
| old disappeared **and** expected appeared | 双条件：`not appear(I_RR_PERSON)` **且** 新页面标识出现 | 最小改动、最强收益；需 Level C 确认过渡期时长 |
| changed + semantic verification | FrameState「画面变了」+ 语义确认 | Level C 标定 ROI / 阈值 |

---

## 7. GeneralBattle 交接

- **何时交接**：`fire()` 返回 True 之后，`run()` 立刻 `self.run_general_battle(config)`。
- **参数**：常规路径 `run_general_battle(con.general_battle_config)`；`exit_four` 路径
  `run_general_battle(config=self.build_quick_exit_config(con.general_battle_config))`
  连打 4 次（每次之间 `fire_again()`），第 5 次用常规 config。**不传** `buff` /
  `battle_key` / `exit_matcher`。
- **返回语义**：`run_general_battle -> bool`，`True` = 本轮获胜，`False` = 失败或主动退出。
  RealmRaid 用 `last_battle` 接住，只用于 §8 的失败分支。
- **RealmRaid 特有 override**（`ScriptTask.__dict__` 实测）：
  - `_exit_matcher()` → `self.I_BACK_RED`（战斗结束后回突破页的识别条件）。
  - `_handle_result(context, config)`：`config.quick_exit` 为真时
    `context.reward_no_battle_ts = None`；`context.is_win = not self.appear(self.I_FALSE)`；
    直接 `return EXIT_WIN / EXIT_LOSE`——**不调 `_settlement_click`**（快退不点结算）。
    非 quick_exit 时 `return super()._handle_result(context, config)`。
  - `PREPARE_CLICK_DELAY_RANGE = (2.5, 3.5)`（基类 `(3.0, 3.0)`）。
  - `SETTLEMENT_CLICK_INTERVAL_RANGE = (0.65, 0.95)`（基类 `(0.7, 1.0)`）。
- **是否修改 Settlement 行为**：只改**间隔**，不改契约。Contract v2 的
  `_settlement_click` / `C_RANDOM_RD` / `_SETTLEMENT_PRIMARY_PROFILE` 全部沿用基类。
- **T7 Settlement opt-in 是否被 RealmRaid 间接使用**：**是**。非 quick_exit 的结算推进走
  基类 `_handle_result` → `_settlement_click` → `ClickSampler.sample(C_RANDOM_RD.roi_front,
  strategy=HABIT, profile=_SETTLEMENT_PRIMARY_PROFILE)`，只是间隔用 RealmRaid 自己的
  `(0.65, 0.95)`。**本轮未改动**。
- 细节差异（不影响结果）：基类 `_handle_result` 用 `appear(I_FALSE, threshold=0.8)`（显式
  阈值 → 绕过批量匹配缓存），RealmRaid 覆写用 `appear(I_FALSE)`（走缓存，阈值取资产自身
  的 0.8）。等效阈值相同。

---

## 8. Victory / Failure / Recovery

| Failure | Recognition | Action | Expected Recovery State | Current Verify |
|---|---|---|---|---|
| 战斗失败（常规） | `run_general_battle()` 返回 `False` → `last_battle=False` | 按 `when_attack_fail`：`REFRESH` → `check_refresh()`；`EXIT` → `break`；`CONTINUE` → 不特殊处理，靠 `find_one` 涂黑跳过 | 回突破页 / 结束任务 | 只有返回值；**不看任何失败标识** |
| 战斗失败（快退 quick_exit） | `_handle_result` 里 `appear(I_FALSE)` | 返回 `EXIT_LOSE` | GeneralBattle 走退出流程 | `I_FALSE`（`gb_false.png`，`threshold=0.8`） |
| 目标格已失败（历史） | `find_one` 内 `appear(false_image)`（复用 **RyouToppa** 的 `loser_sign_1.png`），逐个 9 格 | 把该格在 `device.image` 上**原地涂黑**，使 `find_anyone` 不会再选中它 | 只选未失败的目标 | 无（纯图像屏蔽，仅 `CONTINUE` 模式启用） |
| 没有可打目标 | `find_one` 返回 `(None, None)` | `CONTINUE` → `check_refresh()`；否则 `success=False; break` | 刷新出新目标 / 结束 | `check_refresh()` 返回值 |
| 刷新在 CD | `not appear(I_FRESH)` | `return False` | — | `appear(I_FRESH)` |
| 票不足 / 达次数上限 | `check_ticket()` OCR | `break` → 收尾 | 探索页 | OCR 三条件 |

> 「回庭院出现失败标识」这一历史说法在**当前源码中不成立**：RealmRaid 收尾是
> `goto_page(page_exploration)`（探索页，非庭院），且失败判定完全来自
> `run_general_battle` 的返回值与 quick_exit 分支的 `I_FALSE`，与「回庭院」无关。

---

## 9. Exit / Return

- **主收尾**：`goto_page(page_exploration)` → `set_next_run(task='RealmRaid',
  success=success, finish=True)` → `raise TaskEnd`。早退路径（票不足）同样先
  `goto_page(page_exploration)` 再 `set_next_run(success=False)`。全模块共 2 处
  `goto_page(page_exploration)`（测试锁定）。
- **连续多次点击**：`fire` / `fire_again` / `ensure_lock` / `check_refresh` /
  `reward_detect_click` 都是「`while` + `interval` 节流反复点」，**每次点击前都重新截图**，
  但**每次点击后不单独验证**，靠下一轮的循环条件收敛。
- **固定 sleep**：RealmRaid 生产路径里**只有一处** `time.sleep(0.2)`，且在**死代码**
  `medal_fire()` 内。活跃路径无固定 sleep，节流全靠 `interval` / `Timer`。
- **是否靠页面消失判断**：是（§6）。`fire` / `fire_again` / `ensure_lock` /
  `check_refresh` 第二段 / `ui_click_until_disappear` 全部是「消失即成功」。
- **有限 retry**：**无**。所有 RealmRaid 自有循环都没有次数上限或 `Timer`。
- **是否可能点到旧坐标**：`partition` 是**静态** `RuleClick`（`C_PARTITION_1..9` 固定 ROI），
  不随识别结果移动，所以不存在「用旧帧算出的动态坐标」问题；但也意味着**点的是格子中心
  区域而不是识别到的勋章位置**。
- **最终 ExpectedState**：`page_exploration`，由 Navigator 两帧稳定确认 + `Timer(30)` 保护。

---

## 10. Wait Inventory

| 位置 | 当前等待 | 实际目的 | 类型 | 未来是否可能替换 |
|---|---|---|---|---|
| `check_ticket` / `is_ticket` / `reward_detect_click` | `wait_until_appear(I_BACK_RED)`（无 `wait_time`） | 等回到突破页再读票 / 判奖励 | semantic | 保留语义，**建议补 `wait_time`** |
| `fire` | `wait_until_appear(I_RR_PERSON)`（无 `wait_time`） | 确认在突破页再开始点 | semantic | 同上 |
| `fire_again` | `wait_until_appear(I_FIRE_AGAIN)`（无 `wait_time`） | 等失败结算页出现 | semantic | 同上 |
| `medal_fire`（死代码） | `wait_until_appear(self.I_FIRE)` + `time.sleep(0.2)` | 等进攻按钮 / 动画 | semantic + minimum animation | 死代码，建议删 |
| `fire` | `appear_then_click(I_FIRE, interval=1)` | 点击频率门控 | retry throttle / frequency gate | 保留 |
| `fire` | `click(partition, interval=2)` | 「适应不同模拟器速度」的点击节流 | retry throttle | 保留 |
| `fire_again` | 三个 `interval=2` | 同上 | retry throttle | 保留 |
| `ensure_lock` | `interval=1` | 锁定按钮点击节流 | retry throttle | 保留 |
| `check_refresh` | `interval=1` ×2 | 刷新/确认按钮节流 | retry throttle | 保留 |
| `reward_detect_click` | `ui_click_until_disappear(I_SOUL_RAID, interval=1.2)` + `appear_then_click(..., interval=1.5)` | 关掉遮挡的魂之器窗口 | semantic（等消失）+ throttle | 保留语义 |
| `run` 呱太弹窗 | `interval=1` | 关弹窗节流 | retry throttle | 保留 |
| GeneralBattle 交接后 | `PREPARE_CLICK_DELAY_RANGE=(2.5,3.5)` / `SETTLEMENT_CLICK_INTERVAL_RANGE=(0.65,0.95)` | 战斗准备点击 / 结算点击间隔 | frequency gate | GeneralBattle 侧，本轮不动 |

> **RealmRaid 活跃路径没有一处「等画面停稳」性质的等待**——不像 Kekkai / `list_find` 有
> swipe 后的固定 sleep。所以**视觉结构等待（FrameState）在 RealmRaid 的候选面很小**。

---

## 11. Loop / Retry Inventory

### Bounded

| 循环 | 上限 |
|---|---|
| `goto_page`（全部导航） | `Timer(30)` → `raise GamePageUnknownError` |
| `run_general_battle` 内部 | `battle_timer` / `_tick_timeout` / `_tick_long_battle` |
| `find_one` 的 9 格扫描 | `for i, roi in enumerate(false_roi)` = 9 |
| `exit_four` 快退段 | 固定 4×(`run_general_battle` + `fire_again`) + 1 次常规 |

### State-bounded

| 循环 | 退出条件 | 风险 |
|---|---|---|
| `run()` 主 `while 1` | 6 个 `break` 点（无票 / 无目标 / 刷新失败 ×3 / 失败退出） | 若 `check_ticket` 恒 True 且总能找到目标，靠票数递减自然收敛 |

### Potentially unbounded（无 `Timer`、无次数上限——测试已锁定）

| 循环 | 说明 |
|---|---|
| `fire()` `while True` | 只在 `I_RR_PERSON` 消失时返回；无超时无上限 |
| `fire_again()` `while True` | 只在 `I_FIRE_AGAIN` 消失时返回 |
| `ensure_lock()` `while 1` | 只在达到目标锁定态时 `break` |
| `check_refresh()` 两个 `while 1` | 分别等 `I_FRESH_ENSURE` 出现 / 消失 |
| `reward_detect_click()` 遮挡分支 `while 1` | 只在 OCR 出 `n/m` 且无中文时返回 |
| `run()` 呱太弹窗 `while 1` | 只在 `I_FROG_RAID` 消失时 `break` |
| `medal_fire()` 三个 `while 1`（死代码） | — |
| 所有 `wait_until_appear(X)` | RealmRaid 全部**不传 `wait_time`** → `BaseTask` 内不建计时器（AST 测试锁定：≥5 处调用，全部单参数无 kwargs） |

> 兜底只有上游 `device.stuck_record` / `GameStuckError`（画面长时间不变）。但这些循环每轮都在
> 截图 + 按 `interval` 点击，画面可能持续小幅变化，未必触发 stuck 检测。

---

## 12. Stale Screenshot

| 位置 | stale source | current risk | Level A 可确认？ | Level C？ |
|---|---|---|---|---|
| `run()` 主循环 → `find_one(False)` | 主循环开头截的那一帧被 `find_one` 复用 | 低——两者紧邻，中间无动作 | 是（已锁定 `find_one(False)`） | 否 |
| `check_ticket` `total==0` 分支 | `reward_detect_click(True)` 内部会多次截图，返回后 `check_ticket` 用 `self.device.image` 重新 OCR | 低——注释明确「重新识别票数」，用的确实是新帧 | 是 | 否 |
| `find_one` 涂黑 | **原地修改 `self.device.image`**（共享帧缓冲），涂黑后该帧对后续任何 `appear` 都是被污染的 | 中——同一帧若被后续代码复用会看到黑块；当前 `find_one` 返回后 `run()` 立即进入 `fire()`，`fire()` 第一件事是重新截图，所以实际未被消费 | 是（已锁定原地修改行为） | 否（但改动需真机） |
| `find_one` → `find_anyone(image)` 不传 `frame_id` | 不复用批量匹配缓存 | 低（只是多算一次） | 是 | 否 |
| `fire()` / `fire_again()` | 每轮 `while` 开头都重新截图，判断与点击同帧 | **无 stale** | 是 | 否 |
| `reward_detect_click` 首段 | `screenshot()` → `wait_until_appear` → `ui_click_until_disappear` 之后才 `O_TEXT.ocr(self.device.image)` | 低——中间各步都在刷新 `device.image` | 是 | 否 |

> RealmRaid 的 stale 风险总体**低于** Kekkai：没有「点 A → 不截图 → 在同一帧继续找/点 B」
> 的模式。唯一值得记录的是 `find_one` 对共享帧的原地涂黑副作用。

---

## 13. Action → Verify Gap Register

| 位置 | Action | 当前 Verify | 缺口 | 分类 | 未来候选 |
|---|---|---|---|---|---|
| `fire()` | `click(partition[i], interval=2)` 打开目标详情 | 无 | 不确认详情页/`I_FIRE` 是否就绪，靠反复点 | **P1** | `wait_until_appear(I_FIRE, wait_time=N)` |
| `fire()` | `appear_then_click(I_FIRE)` 进攻 | 仅 `not appear(I_RR_PERSON)` | 无战斗页正向确认；单帧判否即认定成功 | **P1** | `not appear(I_RR_PERSON)` **且** `detect_page_in(page_battle_prepare, page_battle)` |
| `fire_again()` | 点 `I_FIRE_AGAIN` / `I_SHOW_AGAIN` / `I_FRESH_ENSURE` | 仅 `not appear(I_FIRE_AGAIN)` | 同上 | **P1** | 同上 |
| `ensure_lock()` | 点锁定/解锁 | `appear(目标态, 0.9)` | 已有正向确认，只缺超时 | **P3** | 补 `Timer` 即可 |
| `check_refresh()` | 点 `I_FRESH` → `I_FRESH_ENSURE` | `appear(I_FRESH_ENSURE)` 出现 → 消失 | 已有双向确认，只缺超时 | **P3** | 补 `Timer` |
| `reward_detect_click()` | `ui_click_until_disappear(I_SOUL_RAID)` | `not appear(I_SOUL_RAID)` | 已有确认，缺超时 | **P3** | 补 `Timer` |
| `reward_detect_click()` 遮挡分支 | 点 `I_SOUL_RAID` 等票数区恢复 | OCR 正则 `(\d+)/(\d+)` | 已有正向确认，缺超时 | **P3** | 补 `Timer` |
| `run()` 呱太弹窗 | 点 `I_FROG_RAID` | `not appear(I_FROG_RAID)` | 消失即成功，缺超时 | **P2/P3** | 补 `Timer` |
| `find_one()` 涂黑 | 原地污染共享帧 | 无 | 副作用未被显式界定 | **P4** | 需真机确认涂黑是否仍必要 |
| `goto_page(page_exploration)` 收尾 | 导航 | Navigator 两帧稳定 | 已可靠 | **P3** | — |
| `run_general_battle` | 战斗 | GeneralBattle Page FSM | 已可靠 | **P3** | — |

> **P2（FrameState candidate）在 RealmRaid 几乎没有**——没有滑动、没有「等列表停稳」。
> 唯一勉强算 P2 的是呱太弹窗关闭动画。这与 Kekkai / `list_find` 形成鲜明对比。

---

## 14. Existing Issue Register

| ID | 位置 | 当前行为 | 风险 | 分类 | Level A? | Level C? |
|---|---|---|---|---|---|---|
| R-R1 | `fire()` | 「`I_RR_PERSON` 消失 = 已进入战斗」，无正向战斗标识、无超时、无 retry 上限 | 弹窗/动画/匹配抖动导致的单帧误判 → 在非战斗页调 `run_general_battle`，浪费一段 battle timeout | correctness / reliability | 否（改判定＝改时序） | **是** |
| R-R2 | `fire()` | `while True` 无 `break`，尾部 `logger.info` + `return False` **不可达**；函数恒返回 `True` | `run()` 里两处 `if not self.fire(index): continue` 是**死分支**——「没成功进入战斗就重来」这条设计意图实际从未生效 | correctness | 记录（修需同时定义失败判据） | 是 |
| R-R3 | `fire_again()` | 同 R-R1/R-R2：「`I_FIRE_AGAIN` 消失 = 成功」，尾部 `return False` 不可达 | 同上 | correctness | 记录 | 是 |
| R-R4 | `fire` / `fire_again` / `ensure_lock` / `check_refresh` ×2 / `reward_detect_click` / 呱太弹窗 | 全部 `while` 无 `Timer` 无次数上限 | 异常态可能长时间空转，仅靠上游 stuck 兜底 | reliability | 否（加超时＝改控制流） | 是（超时值需真机定） |
| R-R5 | 全部 `wait_until_appear(X)` | 均不传 `wait_time` → `BaseTask` 不建计时器，可无限等 | 同 R-R4 | reliability | 否 | 是 |
| R-R6 | `check_refresh()` | 尾部 `return False` 不可达（第二个 `while 1` 只会 `return True`） | 死代码，且「刷新确认失败」无表达路径 | correctness | 记录 | 否 |
| R-R7 | `medal_fire()` / `is_ticket()` | **全仓零调用方**（已 grep `tasks/` + `module/` 确认）；`medal_fire` 还依赖 `medal_grid = None`，一旦被调用即 `AttributeError`；`medal_fire` 声明 `-> bool` 但无任何 `return` | 死代码，误导后续维护 | architecture | **是**（删死代码；本轮按 0-diff 只记录） | 否 |
| R-R8 | `script_task.py` import | `AttackNumber` 枚举导入后全模块未使用（全文仅出现 1 次） | 死 import | architecture | **是**（本轮只记录） | 否 |
| R-R9 | `find_one()` | 在 `self.device.image` 上**原地涂黑**失败格（共享帧缓冲副作用） | 该帧被后续复用会看到黑块；当前恰好未被消费（`fire()` 立即重截） | architecture / reliability | 记录 | 是 |
| R-R10 | `find_one()` | `false_image` 复用 **RyouToppa** 的 `./tasks/RyouToppa/dev/loser_sign_1.png` | 跨任务资产耦合，RyouToppa 换图会静默影响 RealmRaid | architecture | 记录 | 否 |
| R-R11 | `_handle_result` 覆写 | `appear(I_FALSE)` 不传 threshold（走批量缓存），基类传 `threshold=0.8`（强制重匹配） | 等效阈值相同，仅缓存路径不同；无功能差异 | observability | 记录 | 否 |
| R-R12 | `partition` 点击 | 点的是 9 宫格**静态 `C_PARTITION_*` ROI 中心区**，不是 `find_one` 识别到的勋章实际位置 | 若某格布局偏移，可能点空 | reliability | 记录 | 是 |
| R-R13 | `check_ticket` | `O_NUMBER` 与 `O_TEXT` 共用同一 `roi=(1143,13,80,39)`，仅 mode 不同 | 非缺陷，但两条 OCR 语义耦合在同一区域 | observability | 记录 | 否 |

---

## 15. Characterization Tests

`tests/test_realm_raid_state.py`（**41 用例**，纯 mock，不启动 MuMu / ADB / OCR RPC / 游戏 /
server）：

- **`fire()`（8）**：`I_RR_PERSON` 首帧消失即 `return True`（1 次截图、0 次点击）；序幕顺序
  `wait_until_appear(I_RR_PERSON) → click_record_clear → screenshot`；`wait_until_appear`
  不带任何 kwargs（无超时）；旧页面仍在时按 `I_FIRE(interval=1)` → `partition(interval=2)`
  的顺序点击；`partition` 取 `order-1` 下标；**「进入战斗」唯一判据是 `not appear(I_RR_PERSON)`**
  且源码无 `page_battle`/`detect_page_in`/`I_EXIT`/`get_current_page`/`Timer(`；AST 证明
  `while True` 内无 `break`、循环内唯一 `return` 是 `True`、尾部 `return False` 不可达。
- **`fire_again()`（4）**：`I_FIRE_AGAIN` 消失即 `True`；先 `wait_until_appear(I_FIRE_AGAIN)`；
  点击顺序 `I_SHOW_AGAIN → I_FRESH_ENSURE → I_FIRE_AGAIN` 且全部 `interval=2`；尾部
  `return False` 不可达。
- **`find_one()`（5）**：返回 `(target, 1-based 序号)`；无命中返回 `(None, None)`；
  `CONTINUE` 模式**原地涂黑**失败格（同一 ndarray 对象、对应区域全 0、其它区域不变）；
  非 `CONTINUE` 模式完全不碰帧；`find_anyone` 调用**不传 `frame_id`**。
- **`check_ticket` / `check_refresh`（7）**：`base` 越界 clamp 到 0；顺序
  `wait_until_appear(I_BACK_RED) → screenshot → OCR`；`total==0` → `reward_detect_click(True)`
  + 二次 OCR；无票 / 低于基准 → False；`init_tickets` 只锁存一次且按 `number_attack` 截止；
  `I_FRESH` 不在 → 立即 `False`（1 次截图、0 次点击）；`check_refresh` 尾部 `return False`
  不可达。
- **GeneralBattle 交接（6）**：`_exit_matcher()` 是 `I_BACK_RED`；quick_exit 分支按
  `appear(I_FALSE)` 返回 `EXIT_WIN`/`EXIT_LOSE`、置 `reward_no_battle_ts=None`、
  **不调 `_settlement_click`**；覆写用 `appear(self.I_FALSE)` 而基类用 `threshold=0.8`；
  非 quick_exit 委托 `super()._handle_result(ctx, cfg)`；`PREPARE_CLICK_DELAY_RANGE
  (2.5,3.5)` vs 基类 `(3.0,3.0)`、`SETTLEMENT_CLICK_INTERVAL_RANGE (0.65,0.95)` vs 基类
  `(0.7,1.0)`；`run()` 内 `run_general_battle` 6 次 / `fire_again` 4 次 /
  `build_quick_exit_config` 4 次。
- **循环 / 等待边界（4）**：`fire`/`fire_again`/`ensure_lock`/`check_refresh`/
  `reward_detect_click`/`medal_fire` 全部有 `while` 且无 `Timer(`/`range(`；AST 扫全模块
  ≥5 处 `wait_until_appear` 调用**全部单参数、无 kwargs**；`run()` 主 `while 1` 无 `Timer`、
  ≥5 个 `break`、以 `raise TaskEnd` 收尾；收尾顺序 `goto_page(page_exploration) →
  set_next_run → raise TaskEnd`，全模块 2 处 `goto_page(page_exploration)`。
- **死代码 / 结构（7）**：`medal_fire` / `is_ticket` 在 `tasks/` + `module/` 全仓零调用方；
  `medal_grid is None` 且 `medal_fire` 会调 `self.medal_grid.find_anyone`；`medal_fire`
  AST 无任何 `return`；`AttackNumber` 全文仅出现 1 次（import）；模块内无 `swipe_adb` /
  `click_adb` / `adb_shell` / `*_minitouch` / `device.swipe(` 等绕过 `Control` 的直连；
  模块无任何 FrameWait token；`false_image` 复用 RyouToppa 资产且 `false_roi` 恰 9 格。

---

## 16. RealmRaid vs Kekkai

| 维度 | Kekkai | RealmRaid |
|---|---|---|
| 主状态类型 | 列表浏览 + 卡片选择（滚动式） | 九宫格目标选择（固定版面，无滚动） |
| semantic marker | 较丰富：`I_UTILIZE_ADD` / `I_U_ENTER_REALM` / `I_U_ADD_1/2` / `I_A_EMPTY` / `I_A_INVITE` | 较丰富：`I_RR_PERSON` / `I_FIRE` / `I_BACK_RED` / `I_FRESH` / `I_FIRE_AGAIN` |
| structural wait（等画面停稳） | **有且是主要缺口**：`perform_swipe_action` 后 `sleep(2)`、KA `check_card_num` 后 `sleep(1)` | **几乎没有**：活跃路径零固定 `sleep`（唯一 `sleep(0.2)` 在死代码里），全靠 `interval` 节流 |
| click verify | 多为「点完 `sleep(2)` 等详情」→ 无显式验证 | 多为「点完靠下一轮 `while` 重判」→ 无显式验证；进攻更是「旧标识消失即成功」 |
| swipe | 两处 `swipe_adb` 直连，**绕过 `Control.swipe` → 无 BehaviorTrace** | **完全没有 swipe**；所有输入走 `device.click`（Control）→ **BehaviorTrace 全覆盖** |
| loop | 多数 bounded（`range(20\|21)` + `Timer(120)` + `count>=5`）；KA 有 4 个无界 `while 1` | 主循环 state-bounded；**6 处自有 `while` 全部无界**，且所有 `wait_until_appear` 无超时 |
| recovery | 结构化：`_record_utilize_failure`（3 次→10min）/`_finish_low_value_utilize`（20min）/剩余时间兜底 | **几乎没有**：只有 `when_attack_fail` 三分支（REFRESH/EXIT/CONTINUE）+ `check_refresh` CD 判定；无失败计数、无退避 |
| GeneralBattle | KekkaiUtilize/Activation **不打战斗**，不接 GeneralBattle | **深度耦合**：`run_general_battle` 是主路径；覆写 `_handle_result` / `_exit_matcher` / 两个时序常量；间接消费 T7 Settlement RD |

### 是否已经出现值得抽公共策略的稳定共同模式

有两个，但**都还不到抽象的时候**：

1. **「点击 → 旧标识消失即成功」**：两个任务都有（Kekkai `screening_card` 等 `I_A_EMPTY`
   消失、RealmRaid `fire` 等 `I_RR_PERSON` 消失）。但**期望状态的强度差别很大**——Kekkai
   那处消失后紧接着有 `save_image('确认挂卡')` 这类业务确认，RealmRaid 那处直接把控制权
   交给 GeneralBattle。抽一个 `click_until_disappear(..., verify=...)` 之前必须先在
   Level C 确认「消失」能否被误触发。
2. **「`while` + `interval` 节流反复点，无总超时」**：两个任务合计 10+ 处。这是最像
   `RetryPolicy` 的模式，但**超时值全部是 Level C 未知**，现在抽只会把一堆猜测参数固化进
   公共层。

**结论：本轮不抽。** 按既定纪律（`docs/DECISIONS.md` D013 的「primitive 可共享、business
wrapper 不一定」+「收口阶段不抽 seam」），等第三组（`list_find`）与这两组一起有真机数据后
再评估。特别注意：`list_find` / Kekkai 的公共点是**视觉结构等待**，而 RealmRaid 根本没有
这类等待——**三者的公共层不是同一个**，不能一次抽完。

---

## 17. FrameWait

**RealmRaid production FrameWait consumers = 0。**

- `tasks/RealmRaid/script_task.py` 不 import 也不引用 `module/base/frame_wait.py` /
  `wait_for_changed_and_stable` / `module/atom/frame_state.py` / `FrameStateDetector`
  （测试 `test_no_frame_wait_consumer_in_realm_raid` 锁定）。
- 本轮**未写入**任何 `ROI` / `changed_threshold` / `stable_threshold` / `stable_frames` /
  `timeout` 猜测值。
- **候选面很小**：RealmRaid 活跃路径没有滑动、没有「等列表/画面停稳」的等待。唯一勉强算
  candidate 的是呱太弹窗关闭动画（S4）；进攻进入战斗（S8）更适合
  **semantic（正向页面标识）** 而不是 FrameState。

---

## 18. 下一步建议

### Level A（无真机即可做，本轮均只记录未做）

- 删死代码：`medal_fire()` / `is_ticket()` / `medal_grid` 类属性 / `AttackNumber` 死 import
  （R-R7 / R-R8，已 grep 确认零调用方）。
- 删三处不可达的尾部 `return False`（R-R2 / R-R3 / R-R6）——但**注意**：删掉等于承认
  `fire()` 无失败路径，应与 R-R1 的判定改造一起设计，不要单独删。
- 继续对第 4 个任务（如 `Exploration` / `Dokan`）做同样的静态收口 + characterization。

### Level C（必须真机）

- **R-R1 首要**：确认「`I_RR_PERSON` 消失」到「战斗页可识别」之间的真实过渡帧序列，据此
  把 `fire()` 的判定改成「旧标识消失 **且** 战斗页正向标识出现」，并定超时值。
- R-R4 / R-R5：给 6 处无界 `while` 与全部 `wait_until_appear` 定合理超时（需观察正常一轮
  各阶段耗时）。
- R-R9：确认 `find_one` 的原地涂黑是否仍必要、能否改为不污染共享帧。
- R-R12：确认 9 宫格 `C_PARTITION_*` 静态 ROI 与实际勋章位置的偏差。

---

## 19. 测试

- 新增 `tests/test_realm_raid_state.py`：**41/41 OK**。
- 完整回归 `toolkit/python.exe -m unittest discover -s tests`：**710/710 OK**
  （669 → 710，净 +41 全来自新文件）。
- `toolkit/python.exe -m compileall -q tests/test_realm_raid_state.py`：通过。
- `git diff --check`：干净。
- 未启动 MuMu / 游戏 / OAS / ADB / OCR / server。

---

## 20. 生产影响

| 项 | 是否改变 |
|---|---|
| click 顺序 / target / 次数 | 否 |
| retry / wait / timeout | 否 |
| ticket OCR | 否 |
| skip_difficult / when_attack_fail / three_refresh / exit_four / order_attack | 否 |
| 刷新顺序 | 否 |
| RealmRaid T7 点击（`partition` 仍 `LEGACY_UNIFORM`，`I_FIRE` 未接 HABIT） | 否 |
| GeneralBattle（含 Settlement Contract v2） | 否 |
| screenshot / OCR / return / exceptions / loop | 否 |

`tasks/RealmRaid/` 对 HEAD **零 diff**（`git diff -- tasks/RealmRaid/` 为空）。本轮生产
diff = **0**。

---

## 21. Git 状态

- branch `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。
- 本轮新增：`tests/test_realm_raid_state.py`、`docs/RealmRaid状态机静态收口.md` + 4 份
  项目文档同步（均为未跟踪新文件 / 既有未跟踪文档）。
- 未 commit、未 push、未 merge、未 reset、未 stash、未真机测试。
