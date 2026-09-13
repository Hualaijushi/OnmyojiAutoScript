# Kekkai 状态驱动迁移前静态收口结果

> 2026-09-02。只读审查 + characterization + 建模，**未改任何 Kekkai 生产行为**。
> 对应 ROADMAP 的 T4-4（`harvest_card` 状态化）/ T5-1（`swipe_adb` BehaviorTrace）/
> T5-2 后半 的迁移前准备；等价于 §4.19 为 `list_find` 做过的静态收口，只是对象换成
> `KekkaiActivation` / `KekkaiUtilize`。
> 源码基准：`tasks/KekkaiActivation/script_task.py`、`tasks/KekkaiUtilize/script_task.py`
> （HEAD `2cdf3a05` + 当前工作树，逐行核实）。

---

## 1. 总结

- **整体运行模型**：两个任务都是「截图 → `appear` / OCR 判当前局面 → `click` / `swipe_adb`
  → 大多数步骤靠固定 `sleep` 或『下一轮再截图重判』推进，少数步骤有明确 `wait_until_*` /
  `Timer` 超时」的黑盒轮询。没有显式 State/Action/ExpectedState 结构；「验证」主要是隐式的
  ——下一轮 `while` 循环重新识别，识别不到期望局面就继续点 / 继续滑。
- **本轮是否改变生产行为**：**否。** 只新增 2 个 characterization 测试文件 + 本文档 + 6 文档
  同步。`tasks/KekkaiActivation/*` 完全未动；`tasks/KekkaiUtilize/*` 的 `M` 是更早轮次的
  阈值 / 随机源 WIP，本轮未触碰。生产 diff = 0。

---

## 2. KekkaiActivation 状态图

```
run()  [入口, 假设已在游戏内某处]
 └─ goto_page(page_guild_realm)            # 导航层负责, timeout=30 raise GamePageUnknownError
 ├─ (exchange_before?) check_max_lv(...)   # 继承自 KU, 换满级式神; 内部 goto_page + ui_click
 ├─ harvest_card()                         # ★ 8 连点, 见 §5
 ├─ run_activation(con)                    # ★ 主状态机
 │   └─ goto_page(page_guild_card)
 │      sleep(0.5)                         # 动画最小等待(硬编码)
 │      while 1:                           # [state-bounded, 无迭代上限/总超时]
 │        screenshot()
 │        card_status  = not appear(I_A_EMPTY)          # 有没有卡在位
 │        card_effect  = appear(I_A_INVITE) ? True
 │                     : appear(I_A_ACTIVATE_YELLOW) ? False
 │                     : <while 1 兜底: 等 INVITE/YELLOW/GRAY>   # [无上限]
 │        ┌─ (not status and not effect) and appear(I_A_ACTIVATE_YELLOW,0.95) → continue  # 动画未稳
 │        ├─ (not status and not effect) and appear(I_A_DEMOUNT)              → continue  # 动画中
 │        ├─ status and effect      → 卡使用中: ocr_time(); set_next_run(now+间隔); return False
 │        ├─ status and not effect  → 已选中未激活:
 │        │     while 1:                    # [无上限] 等 I_A_INVITE
 │        │       screenshot()
 │        │       appear(I_A_INVITE,0.8) → break
 │        │       appear_then_click(I_UI_CONFIRM, interval=0.6) → continue
 │        │       appear_then_click(I_A_ACTIVATE_YELLOW, interval=1) → continue
 │        │     ocr_time(True); set_next_run(now+间隔); return True
 │        └─ not status and not effect → screening_card(card_type)  # 挑卡, 见下; 返回后 while 再转一圈
 ├─ goto_page(page_guild_realm)
 ├─ (exchange_max?) check_max_lv(...)
 ├─ goto_page(page_main)
 └─ raise TaskEnd('KekkaiActivation')

screening_card(rule):                      # 挑选并确认挂卡
  # 1) 选卡类别
  while 1:                                  # [无上限] 等 target_class(斗鱼/太鼓标签)出现
    screenshot()
    appear(target_class) → sleep(0.3); screenshot(); appear(target_class) → break   # 0.3s 双确认
    click(C_A_SELECT_CARD_LIST, interval=2.5) → continue                            # 每 2.5s 点一次
  # 2) 点掉类别标签
  while 1:                                  # [无上限] 直到 target_class 消失
    screenshot()
    not appear(target_class) → break
    appear_then_click(target_class, interval=1) → continue
  # 3) 找最优卡 + 确认
  while 1:                                  # [无上限]
    screenshot()
    target = check_card_num()               # RuleClick 或 None, 见 §6.A
    target is None → _card_not_found()       # 累计计数, 切卡种 / 180min 后重试, 总是 raise TaskEnd
    appear(I_A_EMPTY):
      while 1:                              # [无上限] 点 target 直到 I_A_EMPTY 消失
        screenshot()
        not appear(I_A_EMPTY) → 清计数; save_image('确认挂卡'); return
        click(target, interval=1) → continue

check_max_lv / unset_shikigami_max_lv / set_shikigami / switch_shikigami_class
  → 委托 ReplaceShikigami 组件, 不在本轮 Kekkai 建模范围
```

## 3. KekkaiUtilize 状态图

```
run()  [入口]
 ├─ 重置 8 个 utilize_* 实例状态
 ├─ (utilize_enable and lazy_mode?) lazy_roll = random_delay(0.0, 1.0)   # ← 当随机数用, 非等待
 │     utilize_lazy_mode_active = lazy_roll < lazy_mode_weight
 ├─ goto_page(page_guild_realm)
 ├─ (utilize_enable?) check_utilize_add()      # ★ 蹭卡主循环
 │   └─ while 1:                               # [bounded: utilize_add_count >= 5 → return True]
 │        utilize_add_count += 1
 │        add_count >= 5 → push_notify; set_next_run(now+5min); return True
 │        sleep(0.5)                           # settle(硬编码)
 │        goto_page(page_guild_realm_growth); screenshot()
 │        not appear(I_UTILIZE_ADD):           # 已蹭上 → 读剩余时间
 │          remaining = O_UTILIZE_RES_TIME.ocr(...)
 │          异常(非 timedelta / <=0 / >12h) → 兜底 5min       # 防热循环, 已有测试
 │          set_next_run(now + max(remaining, min_interval)); return True
 │        goto_page(page_guild_realm_utilize)
 │        run_utilize(select_friend_list, shikigami_class, shikigami_order)   # ★ 见下
 │        utilize_terminal_failure → return False
 │        goto_page(page_guild_realm_growth)   # 回到育成, while 再转一圈
 ├─ check_max_lv(...)
 ├─ (utilize_harvest?) check_utilize_harvest()     # appear(I_UTILIZE_EXP) → ui_get_reward
 ├─ check_box_ap_or_exp(...)                       # 体力盒 Timer(6) / 经验壶 Timer(12)+max_tries
 ├─ receive_guild_assets(max_times)                # for i in range(1, N+1): goto_page(page_guild) ...
 │     └─ check_and_get_guild_rewards()            # while True + Timer(2) 进度计时器, state-bounded
 ├─ (not utilize_enable?) set_next_run(finish=True, success=True)
 ├─ goto_page(page_main)
 └─ raise TaskEnd

run_utilize(friend, ...):
  for (friend, fallback_friend):               # [bounded: 恰好 2 个分组]
    _reset_utilize_friend_list(target)         # switch_friend_list ×2~3 + swipe(S_U_END, interval=3)
      GamePageUnknownError → _record_utilize_failure(...); return
    lazy_mode? _select_lazy_resource_card()  :  _select_optimal_resource_card(target)
      True  → selected_friend=target; break     # 选中即停, 不看另一区
      False → return False                      # 有可用卡但选卡失败, 不切区
      None  → 这个分组没有当前策略四星+, 继续 fallback
  selected_friend is None → _finish_low_value_utilize(); return   # 两区都低价值, 20min 后重试
  screenshot()
  not appear(I_U_ENTER_REALM) → _record_utilize_failure('未识别到进入结界按钮')
  goto_page(page_friend_utilize)  (GamePageUnknownError/GameStuckError → _record_utilize_failure)
  screenshot()
  stop_image = appear(I_U_ADD_1) ? I_U_ADD_1
             : (appear(I_U_ADD_2) and not appear(I_U_ADD_1)) ? I_U_ADD_2 : None
  stop_image is None → save_image('没有坑位'); _record_utilize_failure('没有可用坑位')
  switch_shikigami_class(...); set_shikigami(order, stop_image)   # 委托 ReplaceShikigami
    GamePageUnknownError/GameStuckError → _record_utilize_failure('式神寄养失败')
  utilize_failed_count = 0; return True

_current_select_best():                        # 普通模式浏览+保留最优
  for swipe_count in range(MAX_SWIPES=20 + 1): # [bounded] ＆ Timer(TIMEOUT=120)  [double-bounded]
    timer.reached() → return False
    screenshot(); cards = order_targets.find_everyone(image, frame_id=...)
    not cards:
      miss_count += 1
      miss_count > CONSEC_MISS(3) or appear(I_U_EMPTY_CARD) → scan_completed=True; return False
      perform_swipe_action(); continue
    for (target, _, area) in cards:            # 按位置排序
      card_class = target_to_card_class(target); tier = CARD_TIER_INFO.get(card_class)
      已在 maxed_card_classes / 星级低于已确认星级 → continue（剪枝, 不点开）
      C_SELECT_CARD.roi_front = area; click(C_SELECT_CARD); sleep(2)   # ← 等详情加载(硬编码)
      card_type, card_value = check_card_num()                        # (type, value) 元组, 见 §6.B
      无效(unknown / <=0 / 不在 RESOURCE_CONFIG) → continue
      更新 confirmed_highest_stars / maxed_card_classes / ap_max_num / jade_max_num
      更新 utilize_last_* / utilize_best_*（按 _card_rank）
      _reaches_reward_threshold(type, value) → return True            # 达阈值即停, 当前选中即目标
    appear(I_U_EMPTY_CARD) → scan_completed=True; return False
    perform_swipe_action()
  scan_completed=True; return False

_select_lazy_resource_card():                  # 怠惰模式: 选当前可见首张高星, 否则首张四星
  for swipe_count in range(max_swipes=20 + 1): ＆ Timer(120)  [double-bounded], consecutive_miss_limit=3
    screenshot(); cards = lazy_scan_targets.find_everyone(...)
    eligible(符合当前策略的四星+) 存在 → 选 high_star 首张 / eligible 首张; click; sleep(2); return True
    miss_count = 0 if cards else miss_count+1
    appear(I_U_EMPTY_CARD) → scan_completed=True; return None
    miss_count > 3 → scan_completed=True; return None
    perform_swipe_action()
  return None

_reselect_best_card(friend):                   # 回到顶部按收益值找回最优卡
  _reset_utilize_friend_list(friend)
  for _ in range(21): ＆ Timer(120)  [double-bounded], miss_count>3 或 I_U_EMPTY_CARD 退出
    screenshot(); cards = order_targets.find_everyone(...)
    对每张类型匹配且档位上限>=target_value 的卡: click; sleep(2); check_card_num() 校验
    perform_swipe_action()

switch_friend_list(friend):                    # 切同区/跨区分组
  while 1: ＆ Timer(SWITCH_FRIEND_LIST_TIMEOUT=20)  [timeout-bounded → raise GamePageUnknownError]
    screenshot(); appear(check_image) → break
    timer_click(1s) 到点 → click(check_image.coord())
  DIFFERENT_SERVER: sleep(1);  然后统一 sleep(0.5)

perform_swipe_action():                        # 好友列表统一下划, 见 §6.C
  swipe_adb((rx∈[340,600], ry∈[500,565]), (rx, ry-416), duration=2)   # 直连, 绕过 Control.swipe
  click_record_clear(); sleep(2)
```

---

## 4. State Matrix

`Recognition` 空 = 该「状态」当前不是靠某个固定 `I_*` 直接判定的。
`Verify` = 动作后是否有对「期望状态」的显式检查。`Wait` = 该步的等待机制。

### 4.A KekkaiActivation

| # | State | Recognition | Action | ExpectedState | Verify | Wait | Failure |
|---|---|---|---|---|---|---|---|
| A1 | 任务开始 | — | `goto_page(page_guild_realm)` | 寮结界主页 | 导航层两帧稳定确认 | `Timer(30)` | `raise GamePageUnknownError` |
| A2 | 结界主页 | — | `harvest_card()` 8×`appear_then_click` | 经验已领 | **无** | 无（同一帧连点） | 无（图不在即 no-op） |
| A3 | 结界主页 | — | `goto_page(page_guild_card)` + `sleep(0.5)` | 挂卡页 | 导航层 | `Timer(30)` + 固定 0.5s | `raise GamePageUnknownError` |
| A4 | 挂卡页·动画未稳 | `not I_A_EMPTY` 且 `not INVITE/YELLOW`；或 `I_A_ACTIVATE_YELLOW@0.95`；或 `I_A_DEMOUNT` | `continue`（重截重判） | 卡状态可辨 | 隐式（下一轮重判） | 轮询无休眠 | `while 1` 无上限 |
| A5 | 挂卡页·卡使用中 | `not I_A_EMPTY` 且 `I_A_INVITE` | `ocr_time()` → `set_next_run` | 任务结束 | OCR 值合理性（`==0` → `GameStuckError`） | — | OCR 失败 `return None` 后仍 `set_next_run(None+now)`（**瑕疵**） |
| A6 | 挂卡页·已选未激活 | `not I_A_EMPTY` 且 `I_A_ACTIVATE_YELLOW` | `while 1`：点 `I_UI_CONFIRM`/`I_A_ACTIVATE_YELLOW` 直到 `I_A_INVITE` | 卡已激活 | 等 `I_A_INVITE` 出现 | `interval` 门控（0.6 / 1s），`while 1` 无总超时 | 潜在无限 |
| A7 | 挂卡页·空位 | `not I_A_EMPTY` 全否 | `screening_card(card_type)` | 挑到卡并挂上 | 见 A8~A11 | — | 见下 |
| A8 | 选卡类别 | `appear(target_class)` + 0.3s 双确认 | `click(C_A_SELECT_CARD_LIST, interval=2.5)` | 类别标签出现 | 0.3s 后重截再 `appear` | `interval=2.5`，`while 1` 无总超时 | 潜在无限 |
| A9 | 点掉类别标签 | `appear(target_class)` | `appear_then_click(target_class, interval=1)` | 标签消失 | `not appear(target_class)` → break | `interval=1`，`while 1` 无总超时 | 潜在无限 |
| A10 | 找最优卡 | OCR「体力/勾玉」数字 ≥ `min_*_num` | `check_card_num()` 返回 `RuleClick` | 有目标卡 | `numeric_results` 非空 | `check_card_num` 内 `ocr_count > 3` 有界 + `swipe_adb`+`sleep(1)` | 4 次未命中 → `_card_not_found` → `raise TaskEnd` |
| A11 | 确认挂卡 | `appear(I_A_EMPTY)` | `while 1`：`click(target, interval=1)` 直到 `not I_A_EMPTY` | 卡挂上（空位被填） | `not appear(I_A_EMPTY)` → 清计数 return | `interval=1`，`while 1` 无总超时 | 潜在无限（若 `check_card_num` 反复返回目标但点击不生效） |

### 4.B KekkaiUtilize

| # | State | Recognition | Action | ExpectedState | Verify | Wait | Failure |
|---|---|---|---|---|---|---|---|
| U1 | 任务开始 | — | `goto_page(page_guild_realm)` | 寮结界主页 | 导航层 | `Timer(30)` | `raise GamePageUnknownError` |
| U2 | 育成页·是否已蹭上 | `not appear(I_UTILIZE_ADD)` | 读 `O_UTILIZE_RES_TIME` | 设定 next_run | OCR 合理性（兜底 5min，`next_run` 恒晚于 now） | 固定 `sleep(0.5)` | 兜底间隔重试（已有测试锁） |
| U3 | 进入好友寄养页 | — | `goto_page(page_guild_realm_utilize)` → `run_utilize` | 好友列表 | 导航层 | `Timer(30)` | `logger.info('Utilize failed')`（**不阻断，继续 run_utilize**） |
| U4 | 刷新好友列表到顶部 | — | `switch_friend_list`×2~3 + `swipe(S_U_END, interval=3)` | 列表在顶部 | `switch_friend_list` 内 `appear(check_image)` | `Timer(20)` / `interval=3` / `sleep(0.5~1)` | `GamePageUnknownError` → `_record_utilize_failure` |
| U5 | 浏览列表找目标 | `order_targets.find_everyone` 命中卡图 | 逐张 `click(C_SELECT_CARD)` + `check_card_num` | 记录/选中最优卡 | `check_card_num` 返回 `(type,value)`；`_reaches_reward_threshold` | 固定 `sleep(2)` 等详情；`perform_swipe_action` 内 `sleep(2)` 等列表 | `range(21)` + `Timer(120)` 双界；连续 3 屏无卡 / `I_U_EMPTY_CARD` → scan_completed |
| U6 | 翻页 | — | `perform_swipe_action()` = `swipe_adb(duration=2)` 直连 | 列表滚动一屏 | **无**（纯固定 `sleep(2)`） | 固定 `sleep(2)` | 无（下一轮 `find_everyone` 再判） |
| U7 | 回选最优卡 | 类型匹配 + 档位上限 ≥ target_value | `click` + `check_card_num` 校验 | 选中的就是最优卡 | `card_type==target and card_value>=target_value` | 固定 `sleep(2)` | `range(21)` + `Timer(120)`；失败 `return False` |
| U8 | 进入好友结界 | `appear(I_U_ENTER_REALM)` | `goto_page(page_friend_utilize)` | 好友结界内 | 页面识别 `any_of(I_CHECK_FRIEND_REALM_*)` | `Timer(30)` | `_record_utilize_failure`（累计 3 次 → 10min 后重试） |
| U9 | 判断坑位 | `I_U_ADD_1` / `I_U_ADD_2` | 选 `stop_image` | 有可上式神的坑 | `appear` 组合 | — | `save_image('没有坑位')` → `_record_utilize_failure` |
| U10 | 上式神寄养 | — | `switch_shikigami_class` + `set_shikigami(order, stop_image)` | 式神已寄养 | 委托 ReplaceShikigami（`stop_image` 消失） | 组件内部 | `GamePageUnknownError/GameStuckError` → `_record_utilize_failure` |

---

## 5. harvest_card

### 当前动作序列（`tasks/KekkaiActivation/script_task.py:333-345`）

线性 8 次 `self.appear_then_click(target)`，**无参数**（无 `interval` / `threshold` / `action`）：

```
I_A_HARVEST_EXP → I_A_HARVEST_FISH4 → I_A_HARVEST_KAIKO_4 → I_A_HARVEST_KAIKO_3
→ I_A_HARVEST_KAIKO_6 → I_A_HARVEST_FISH_6 → I_A_HARVEST_MOON_3 → I_A_HARVEST_FISH_3
```

- **无 `interval` 时 `appear_then_click` 不截图**——`appear(target, interval=None)` 直接匹配
  `self.device.image`。所以这 8 次全部匹配**同一帧**（`run()` 里上一步 `goto_page(page_guild_realm)`
  留下的最后一帧）。
- 8 步之间**无 `screenshot()`、无 `sleep`、无循环、无 `if`、无 `return`**（characterization
  测试 `test_source_is_linear_no_loop_no_wait_no_verify` 锁定）。
- **无验证**：点完某个 `I_A_HARVEST_*` 后不检查它是否消失 / 页面是否变化 / 是否弹出「获得
  奖励」。
- **无 reward popup 处理**：`harvest_card` 里完全没有 `I_UI_REWARD` / `ui_get_reward` /
  `ui_reward_appear_click`。
- 返回 `None`。即使 8 个 target 全部「点中」也仍是 8 次调用、无提前退出。

### 验证缺口

| 步骤 | Action | 期望状态 | 当前验证 | 缺口 |
|---|---|---|---|---|
| 每个 `appear_then_click(I_A_HARVEST_*)` | 点「领取经验」按钮 | 弹「获得奖励」/ 该按钮消失 / 页面回到结界主页 | **无** | 既没有点击前重新截图，也没有点击后确认 |

### 是否适合成为第一个 State→Action→Verify pilot

**中等适合，但不是最优先。**

- 有利：动作少（≤8）、目标都是明确 `RuleImage`（Strong Semantic State）、失败代价低（漏领
  经验，不损坏账号）、无业务策略耦合。
- 不利：
  1. 每个 `I_A_HARVEST_*` 是**互斥出现**的（游戏最后没领的那一档才显示对应按钮），正常一轮
     最多命中 1~2 个；「扫描 → 命中 → 点击 → 验证消失 → 继续」结构里「继续」几乎立刻结束，
     状态收益不大。
  2. 点击后的「期望状态」到底是什么（弹奖励？按钮直接消失？跳页？）**需要 Level C 真机观察**
     才能确定——这正是 pilot 要解决的第一个未知。
  3. ROADMAP T4-4 已把它列为 pilot 且标「改变点击时序 → Level C」。本轮无真机，只能把现状
     锁死，不能落地。
- 对比：`RyouToppa` 的 `_finish_area_battle` / `GeneralBattle` 结算已经是更成熟的 State/Action
  循环；`harvest_card` 作为「最小、低风险」的**首个纯 semantic-wait pilot** 仍然合理，前提是
  真机确认了「点击后按钮消失」这一期望状态。

---

## 6. 列表 / swipe

### 6.A KekkaiActivation —— `check_card_num`（`script_task.py:238-298`）

| 项 | 当前值 |
|---|---|
| baseline（滑动前状态） | 不取；每轮 `while 1` 开头 `self.screenshot()` |
| screenshot 时机 | 每轮循环开头 1 次；swipe 后**不额外截图**（靠下一轮开头） |
| 识别 | `O_CHECK_CARD_NUMBER.detect_and_ocr(image)`（OCR），每轮 1 次，`ocr_count += 1` |
| swipe 后端 | `self.device.swipe_adb(p1, p2, duration=2)` —— **直连 ADB**，绕过 `Control.swipe` |
| p1 | `(random.randint(200,400), random.randint(580,600))` —— **stdlib `random`**，非公共 helper |
| p2 | `(p1.x, p1.y - 410)` —— 固定位移 410，x 不变（纯竖直） |
| duration | `2`（int 秒 → `swipe_adb` 内 `*1000` = 2000ms ADB swipe） |
| swipe 后等待 | `time.sleep(1)`（固定；目的隐含「等列表滚动停」，无变化 / 停稳判断） |
| 循环边界 | `while 1` + `ocr_count > 3` → `return None`（**bounded**，约 4 次 OCR + 3 次 swipe） |
| 命中 | 构造 `RuleClick(roi_front=roi, name="tmpclick")`，`roi` = `O_CHECK_CARD_NUMBER.roi[:2] + OCR box 偏移` |
| continuation | 未命中就滑；`ocr_count>3` 退出返回 `None` → 上层 `screening_card` 调 `_card_not_found` → `raise TaskEnd` |
| 是否重复处理同一屏 | 会——滑动位移固定 410，未做「已扫过的卡去重」；连续两屏若滚动不足会重看 |

### 6.B KekkaiUtilize —— `check_card_num`（`script_task.py:1039-1071`）

- 与 KekkaiActivation 的**同名方法不同签名**：这里返回 `(card_type: str, value: int)`，**不滑动**。
- `self.screenshot()` → `O_CARD_NUM.ocr(image)` → 关键字判类型（`体/カ/力`→斗鱼，`勾/玉`→太鼓，
  否则 `('unknown', 0)`）→ 正则取数字。
- `value <= 0` → `push_notify` + 返回 `(card_type, 0)`。
- **latent 冲突**：`KekkaiActivation` 继承 `KekkaiUtilize` 并**覆写** `check_card_num`（返回
  `RuleClick`）。当前无运行时冲突（KA 的 `run` 分支永远不进 `run_utilize` / `_current_select_best`），
  但若将来给 `KekkaiActivation` 加 `run_utilize` 路径，`_current_select_best` 里
  `card_type, card_value = self.check_card_num()` 会拿到 `RuleClick` 并在解包时崩。见 §9 Issue R-A1。

### 6.C KekkaiUtilize —— `perform_swipe_action`（`script_task.py:1019-1037`）

| 项 | 当前值 |
|---|---|
| baseline | 不取 |
| screenshot | 本方法内 0 次（调用方 `_current_select_best` / `_select_lazy_*` / `_reselect_*` 下一轮开头截） |
| swipe 后端 | `self.device.swipe_adb(p1, p2, duration=2)` —— 直连 ADB，绕过 `Control.swipe`（**有意**，见 §4.11 / docstring） |
| p1 | `(random_int(340,600), random_int(500,565))` —— **公共 `random_int`**（闭区间 SystemRandom），常量 `SWIPE_START_X_RANGE` / `SWIPE_START_Y_RANGE` |
| p2 | `(p1.x, p1.y - SWIPE_DISTANCE)`，`SWIPE_DISTANCE = 416`，x 不变 |
| duration | `2`（秒） |
| swipe 后 | `self.device.click_record_clear()` → `time.sleep(2)`（固定） |
| 顺序 | `swipe_adb → click_record_clear → sleep(2)`（characterization 锁定） |
| 循环边界 | 本方法无循环；调用方 `range(20|21)` + `Timer(120)` 双界 |
| continuation | 下一轮 `find_everyone`；`I_U_EMPTY_CARD` 或连续 `CONSEC_MISS(3)` 屏无卡 → 结束扫描 |

---

## 7. Semantic vs Visual Wait 迁移矩阵

| 位置 | Action | 当前等待 | 等待目的（源码证据） | 未来类型 |
|---|---|---|---|---|
| KA `run_activation` 前 | `goto_page(page_guild_card)` 后 | `sleep(0.5)` | 注释「那么长的动画先休息一会」 | **animation minimum**（保留下限，可叠加 semantic） |
| KA `screening_card` 双确认 | `appear(target_class)` 后 | `sleep(0.3)` + 重截再 `appear` | 防抖：等类别标签渲染稳 | **visual changed/stable** 候选（或直接 `wait_until_stable`） |
| KA `check_card_num` swipe 后 | `swipe_adb` 后 | `sleep(1)` | 隐含「等列表滚动停」 | **visual changed/stable**（frame changed→stable） |
| KA `run_activation` A6 循环 | 点 CONFIRM/YELLOW | `interval` 门控 + 等 `I_A_INVITE` | 等「激活成功」标出现 | **semantic wait**（`wait_until_appear(I_A_INVITE)`） |
| KA `screening_card` A8/A9/A11 | 点类别 / 点标签 / 点目标 | `interval` + `while 1` 重判 | 等标签出现 / 消失 / `I_A_EMPTY` 消失 | **semantic wait**（`wait_until_appear` / `wait_until_disappear`），需补总超时 |
| KU `check_utilize_add` | `goto_page(growth)` 前 | `sleep(0.5)` | 注释「无论收不收到菜，至少看一眼」settle | **animation minimum** / 可能可删（需 Level C） |
| KU `_current_select_best` / `_select_lazy_*` / `_reselect_*` | `click(C_SELECT_CARD)` 后 | `sleep(2)` | 注释「等待结界卡详情加载」 | **semantic wait** 候选（等详情页某标识出现），需真机确认标识 |
| KU `perform_swipe_action` 后 | `swipe_adb` 后 | `sleep(2)` | 「等列表停稳」（无显式判断） | **visual changed/stable**（与 `list_find` 翻页等待同类，D013） |
| KU `switch_friend_list` | 切分组后 | `sleep(0.5)`（+ 跨区额外 `sleep(1)`） | 切分组动画 settle | **semantic wait**（该方法已有 `appear(check_image)` 判定，sleep 可能可删） |
| KU `check_and_get_guild_rewards` | 收资金 / 体力后 | `sleep(1)` | 注释「等待看到获得奖励」 | **animation minimum** / semantic（等 `I_UI_REWARD`） |
| KU `run` lazy_roll | — | `random_delay(0.0, 1.0)` | **不是等待**——被当成 `[0,1)` 随机数做概率判定 | **frequency gate / 应改用 `random.random()` 语义**（Issue R-U3） |

---

## 8. Loop / Retry

### Bounded（有 `range` / `Timer` / 计数硬上限）

| 循环 | 上限 |
|---|---|
| KA `check_card_num` `while 1` | `ocr_count > 3`（≈4 OCR + 3 swipe） |
| KA `_card_not_found` | 无循环；两分支都 `raise TaskEnd` |
| KU `check_utilize_add` `while 1` | `utilize_add_count >= 5` |
| KU `run_utilize` `for` | 恰好 2 个好友分组 |
| KU `_current_select_best` `for` | `range(21)` ＆ `Timer(120)` ＆ `CONSEC_MISS=3` |
| KU `_select_lazy_resource_card` `for` | `range(21)` ＆ `Timer(120)` ＆ `consecutive_miss_limit=3` |
| KU `_reselect_best_card` `for` | `range(21)` ＆ `Timer(120)` ＆ `miss_count>3` |
| KU `switch_friend_list` `while 1` | `Timer(20)` → `raise GamePageUnknownError` |
| KU `guild_lottery` | `Timer(4)` ×2 段 |
| KU `check_box_ap_or_exp._harvest_ap_box` | `Timer(6)` |
| KU `check_box_ap_or_exp._harvest_exp_jug` | `Timer(12)` ＆ `max_tries=random_int(2,3)` |
| KU `receive_guild_assets` `for` | `range(1, max_tries+1)` |
| `BaseTask.goto_page`（所有 Kekkai 导航） | `Timer(30)` → `raise GamePageUnknownError` |
| `BaseTask.ui_click_until_appear_or_timeout` | `Timer(timeout)` |

### State-bounded（靠页面状态退出，无迭代上限）

| 循环 | 退出条件 | 风险 |
|---|---|---|
| KA `run_activation` `while 1` | `card_status`/`card_effect` 组合命中（return False/True）；否则 `screening_card` 后再转 | 若游戏卡在无法辨识的中间态 → 不退出 |
| KA `check_card_effect` `while 1`（兜底） | `I_A_INVITE`/`I_A_ACTIVATE_YELLOW`/`I_A_ACTIVATE_GRAY` 之一出现 | 三者都不出现 → 不退出 |
| KU `check_and_get_guild_rewards` `while True` | `Timer(2)` 到点且期间无任何奖励 → return False | 奖励持续出现会一直 reset（实际有限） |

### Potentially unbounded（无可靠上限）

| 循环 | 说明 |
|---|---|
| KA `run_activation` A6：`while 1` 点 CONFIRM/YELLOW 等 `I_A_INVITE` | 无总超时；激活标永不出现则死循环 |
| KA `screening_card` 循环 1：`while 1` 点 `C_A_SELECT_CARD_LIST` 等类别标签 | 无总超时 |
| KA `screening_card` 循环 2：`while 1` 点类别标签等其消失 | 无总超时 |
| KA `screening_card` 循环 3（外层）+ 循环 3.内（`I_A_EMPTY` 块） | `check_card_num` 反复返回目标但点击不生效 → 外层不退；内层等 `I_A_EMPTY` 消失无超时 |

> 依赖上游 `self.device.stuck_record` / `GameStuckError`（截图长时间不变触发）作为**兜底**，
> 但 Kekkai 这些循环内每轮都在 `screenshot()` + `click`，画面可能一直在小幅变化，未必触发
> stuck 检测。本轮只记录，不修。

---

## 9. Existing Issue Register

| ID | 位置 | 当前行为 | 风险 | 分类 | Level A 可修？ | 需要 Level C？ |
|---|---|---|---|---|---|---|
| R-A1 | `KekkaiActivation.check_card_num` vs `KekkaiUtilize.check_card_num` | 子类覆写改了返回类型（`RuleClick` vs `(str,int)`） | 现无运行时冲突；将来给 KA 加 `run_utilize` 路径会解包崩 | architecture | 记录即可（重命名其一需谨慎，可能改调用图） | 否 |
| R-A2 | `harvest_card` | 8 连点前后无截图 / 无验证 / 无 reward 闭环 | 漏领经验（低危）；若某按钮点击弹出遮挡后续判断的窗口，本方法不处理 | reliability | 否（加截图 / 验证＝改点击时序） | 是 |
| R-A3 | `check_card_num` swipe | 用 stdlib `random.randint`，非公共 `random_int` | 随机源不统一（与 §4.10 已收敛的其它处不一致）；`random.seed()` 可污染 | correctness / observability | **是**（纯换 helper，行为等价，但仍属生产 diff，本轮按「0 diff」原则只记录） | 否 |
| R-A4 | `check_card_num` / `perform_swipe_action` | `swipe_adb` 直连，绕过 `Control.swipe` → 无 BehaviorTrace、无 `distance_check`、无 `_invalidate_image_batch_cache` | 观测缺口（这两类列表滑动不进 `log/behavior/`）；控制不统一 | observability | 记录（ROADMAP T5-1 已计划） | 是（改动需真机验证滚动距离） |
| R-A5 | `run_activation` A6 / `screening_card` 三循环 | `while 1` 无总超时 | 游戏异常态可能死循环，仅靠 stuck 兜底 | reliability | 记录（加 `Timer` 属改控制流） | 是 |
| R-A6 | `run_activation` A5 | `ocr_time()` OCR 失败 `return None`，随后 `set_next_run(None + now)` | `None + datetime` → `TypeError`（会崩而非静默）；OCR==0 走 `raise GameStuckError` | correctness | 记录 | 是 |
| R-U1 | `check_utilize_add` | 「5 轮未蹭上」`return True`，与 `_record_utilize_failure` 的 `return False` 语义相反 | 调度器对「失败」的记账可能不一致（AI_CONTEXT §8 已记录，「不影响正确性」） | correctness | 记录 | 否 |
| R-U2 | `ScriptTask.last_best_index = 99` | 类属性，全仓无读取者 | 死属性 | architecture | **是**（删死代码，全仓 grep 已确认零调用方；本轮按 0-diff 只记录） | 否 |
| R-U3 | `run` lazy_roll | `random_delay(0.0, 1.0)` 当随机浮点用做概率判定 | 语义误用；`random_delay` 若将来加最小间隔逻辑会改变概率分布 | correctness | **是**（换 `_rng.random()` 或 `random_triangular`，需保持同分布） | 否 |
| R-U4 | `_current_select_best` / `_select_lazy_*` / `_reselect_*` | `click(C_SELECT_CARD)` 后固定 `sleep(2)` 等详情 | 慢（每张卡 +2s）；详情没加载完就 OCR 会误判 | reliability | 否（改 semantic wait 需知道详情页标识 + 改时序） | 是 |
| R-U5 | `perform_swipe_action` 后 `sleep(2)` | 无「列表是否真的滚动 / 停稳」判断 | 滚动不足→重复扫同屏；滚动过头→漏卡（`SWIPE_DISTANCE=416` 未经真机核） | reliability | 否（FrameState 接入是 Level C） | 是 |
| R-U6 | `check_utilize_add` U3 | `if not self.goto_page(page_guild_realm_utilize): logger.info(...)` 后**不 return**。**2026-09-14 源码复核修正本条的 root cause**：`goto_page()` 成功固定 `return True`、失败**抛** `GamePageUnknownError` / `GameStuckError`，**从不返回 False/None**，所以这个 `if not ...` 分支实际不可达；真实失败是异常直接向上传播，绕过 Kekkai 自己的 retry / quiet window / terminal handling（**不是**「异常路径下继续执行 `run_utilize`」） | 导航失败不走本任务的失败调度，退化成全局 task 失败 | reliability | **IMPLEMENTED（2026-09-14，U3）**：本地 `try/except (GamePageUnknownError, GameStuckError)` 统一收敛失败信号 → `_schedule_retry` + `utilize_terminal_failure=True` + `return False`。Level A/B PASS（`UtilizeNavigationFailureGuardTest` 10 例），Level C PENDING | 是（Level C） |
| R-U7 | `KekkaiActivation` imports `parse_rule` | `from tasks.KekkaiActivation.utils import parse_rule`，模块内无调用 | 死 import | architecture | **是**（删 import；本轮 0-diff 只记录） | 否 |

---

## 10. Characterization tests

### `tests/test_kekkai_activation_state.py`（18 用例）

- **harvest_card**：恰好 8 次 `appear_then_click`、target 顺序固定、每次仅 1 位置参数无
  kwargs、`screenshot` 从不调用、返回 `None`、8 个 target 全命中也不提前退出；源码无
  `screenshot`/`while`/`for`/`Timer`/`sleep`/`if`/`return`（纯线性）。
- **check_card_num（KA 覆写）**：空 OCR 时 4 次 OCR + 3 次 `swipe_adb`(`duration=2`) + 3 次
  `sleep(1)`，`ocr_count>3` 返回 `None`；`swipe_adb` 的 `p1=(randint(200,400),randint(580,600))`、
  `p2=(p1.x, p1.y-410)`；用 `tasks.KekkaiActivation.script_task.random.randint`（stdlib，非
  `random_int`）；命中返回 `name='tmpclick'` 的 `RuleClick` 且 `roi` = `O_CHECK_CARD_NUMBER.roi`
  前两位 + OCR box 偏移，命中时 0 swipe / 1 screenshot；数字 `< min_num` 被忽略后继续滑；
  未知 `card_type` 抛 `ValueError`。
- **循环边界（源码级）**：`run_activation` `while 1` 无 `range`/`Timer`；`screening_card` 4 个
  `while 1` 无 `Timer`/`range`；`check_card_effect` 有 `while 1` 无 `Timer`；`check_card_num`
  有 `ocr_count > 3` 上界；`_card_not_found` 总以 `raise TaskEnd` 收尾、只 `set_next_run` 一次。
- **结构**：入口 `run` 先 `harvest_card()` 后 `run_activation(con)`、以 `raise TaskEnd('KekkaiActivation')`
  结束；`KA` 继承 `KU.ScriptTask` 且两者都定义 `check_card_num`；模块无 `wait_for_changed_and_stable`
  等 FrameWait token。

### `tests/test_kekkai_utilize_state.py`（23 用例）

- **perform_swipe_action**：`random_int(340,600)` / `random_int(500,565)` 各一次；`swipe_adb`
  的 `p1=(rx,ry)`、`p2=(rx, ry-416)`、`kwargs={'duration':2}`；顺序 `swipe_adb → click_record_clear
  → sleep(2)`；返回 `None`；**不调用 `self.device.swipe`（Control.swipe）** → 无 BehaviorTrace；
  常量 `SWIPE_START_X_RANGE=(340,600)` / `SWIPE_START_Y_RANGE=(500,565)` / `SWIPE_DISTANCE=416`；
  源码用 `swipe_adb` 且公共 `self.swipe(` 仅在注释行、用 `random_int`。
- **check_card_num（KU）**：`体力/カ/力` → `('斗鱼', n)`，`勾/玉` → `('太鼓', n)`，无关键字 →
  `('unknown', 0)` 且不 push_notify，`value<=0` → push_notify + `(type, 0)`，每次都 `screenshot`。
- **循环 / retry 边界（源码级）**：`check_utilize_add` `count>=5`；`run_utilize` `enumerate((friend,
  fallback_friend))` 且无额外 `while`；`_current_select_best` `MAX_SWIPES=20`+`range(+1)`+`Timer(120)`+
  `CONSEC_MISS=3`；`_select_lazy_resource_card` 同形；`_reselect_best_card` `range(21)`+`Timer(120)`；
  `switch_friend_list` `while 1`+`Timer(20)`+`raise GamePageUnknownError`（`SWITCH_FRIEND_LIST_TIMEOUT==20`）；
  `check_and_get_guild_rewards` `while True`+`Timer(2)` 进度计时器；`receive_guild_assets` `range(1,N+1)`。
- **等待清单**：三处「等详情」= `time.sleep(2)`；`perform_swipe_action` 后 = `time.sleep(2)`；
  lazy_roll = `random_delay(0.0, 1.0)` 用于 `utilize_lazy_mode_active` 概率判定。
- **结构**：模块无 FrameWait token；全模块只有 `perform_swipe_action` 一处 `self.device.swipe_adb(`；
  入口 `run` 以 `raise TaskEnd` 结束。

> 所有测试均为纯 mock（`ScriptTask.__new__` + `SimpleNamespace` device + patch
> `sleep`/`random*`/`screenshot`）。**不启动** MuMu / ADB / OCR RPC / 游戏 / server。

---

## 11. FrameWait

**本轮 Kekkai production consumers = 0。**

- `tasks/KekkaiActivation/script_task.py` 与 `tasks/KekkaiUtilize/script_task.py` 均**不 import
  也不引用** `module/base/frame_wait.py` / `wait_for_changed_and_stable` /
  `module/atom/frame_state.py` / `FrameStateDetector`（characterization
  `test_no_frame_wait_consumer_in_*` 锁定）。
- 本轮**未写入**任何 `changed_threshold` / `stable_threshold` / `stable_frames` / ROI /
  timeout 猜测值。这些是 Level C 真机标定项（与 D013 对 `list_find` 的结论一致）。

---

## 12. 与 `list_find` 的关系

| 维度 | `BaseTask.list_find` | KA `check_card_num` swipe | KU `perform_swipe_action` |
|---|---|---|---|
| baseline 来源 | `self.device.image`（为识别而截，非等待基线） | 同左（每轮开头截） | 同左（调用方下一轮截） |
| ROI | `RuleList` / `swipe_pos` 几何 | 无（全屏竖直滑，固定像素） | 无（同左） |
| swipe backend | `self.device.swipe`（Control.swipe → BehaviorTrace） | `self.device.swipe_adb`（直连，无 trace） | `self.device.swipe_adb`（直连，无 trace，**有意**） |
| 翻页几何 | `target.swipe_pos(after=...)`（image `after=True` 恒定 / ocr `number=1, after=result>0`） | 固定：`p1.y-410`，起点 x∈[200,400] y∈[580,600] | 固定：`p1.y-416`，起点 x∈[340,600] y∈[500,565] |
| post-swipe wait | `sleep(random.uniform(0.8, 1.3))` | `sleep(1)` | `sleep(2)` |
| loop | `for _ in range(max_swipe)`（默认 10） | `while 1` + `ocr_count>3` | 调用方 `range(20|21)` + `Timer(120)` |
| 命中判定 | 结果是 `tuple` | `numeric_results` 非空（OCR 数字 ≥ min） | `order_targets.find_everyone` 命中卡图 |
| 到底部判定 | **无**（纯靠 `max_swipe`） | **无**（纯靠 `ocr_count>3`） | `appear(I_U_EMPTY_CARD)` 或连续 `CONSEC_MISS` 屏无卡 |
| failure handling | 耗尽 `return False` | `_card_not_found` → `raise TaskEnd` | scan_completed → `return False`/`None` → 上层失败计数 |

**可未来共享的 primitive**：三者「swipe 后等列表停稳」都属 D013 的**视觉结构等待**，未来可以
共用同一个 `wait_for_changed_and_stable(baseline=滑动前帧, ...)` primitive——**前提是**每个调用点
自己在 swipe 前把 baseline 帧显式传进去（D012/D013 硬要求）。

**Kekkai 特有、不共享的部分**：
- 命中判定（OCR 数字阈值 / `find_everyone` 卡图）是业务识别，不进 primitive。
- 到底部判定（`I_U_EMPTY_CARD` / 连续空屏）是 Kekkai 特有的列表结束语义。
- `swipe_adb` 直连 vs `Control.swipe`：KU 的 docstring 明确「好友列表对滚动距离敏感，改回公共
  滑动必须先真机验证」——primitive 共享**不代表** swipe backend 也要统一。
- 选卡 / 回选 / 跨区双分组 / 怠惰模式是 KU 的 business wrapper，不进任何公共层（同 D013：
  「primitive 可共享，business wrapper 不一定」）。

---

## 13. 下一步候选

### Candidate A —— Level A 可纯静态推进（无真机）

- 本文档 + 两个 characterization 测试文件本身（已完成）。
- （若放宽「0 diff」）R-A3 / R-U2 / R-U3 / R-U7 是纯代码质量修（换随机源 helper、删死属性 /
  死 import、修 lazy_roll 语义），可行为等价，但**本轮按用户「0 生产 diff」要求只记录**，留作
  独立小任务或和状态迁移一起做。

### Candidate B —— 需要 FrameState / Level C

- KA `check_card_num` swipe 后 `sleep(1)`、KU `perform_swipe_action` 后 `sleep(2)`：换成
  `frame changed + stable`（需真实 ROI / 阈值 / `stable_frames` / timeout）。
- KU `SWIPE_DISTANCE=416` / KA `-410` 的滚动距离是否跳过 / 重复条目（ROADMAP 已列，Level C）。
- ROADMAP T5-1：把 `swipe_adb` 直连路径接入 BehaviorTrace（或明确不接）。

### Candidate C —— 需要业务真机观察

- `harvest_card` 每个 `I_A_HARVEST_*` 点击后的**期望状态**（弹奖励？按钮消失？跳页？）——
  T4-4 pilot 的第一个未知。
- KU 「等结界卡详情加载」的详情页标识（R-U4）。
- KA `screening_card` / `run_activation` A6 的 `while 1` 无超时循环加 `Timer` 上限（R-A5）——
  需真机观察正常一轮耗时以定超时值。
- KA A5 `ocr_time` 失败路径 `None + datetime`（R-A6）。

### Candidate D —— 当前已可靠，暂不动

- `goto_page`（`Timer(30)` + raise）、`switch_friend_list`（`Timer(20)` + raise）、
  `_current_select_best` / `_select_lazy_*` / `_reselect_*`（`range` + `Timer(120)` 双界）、
  `check_utilize_add`（`count>=5`）、剩余时间兜底（已有测试锁）。

### 无真机时最推荐的下一项

继续做**其它任务的迁移前静态收口 / characterization**（如 `RealmRaid`、`Exploration` 的
State/Action 循环），凑齐 2~3 个真实案例后再评估是否抽公共 State 层（延续「先两个真实迁移
案例再抽象」的既定纪律）。本轮 Kekkai 静态收口本身已经是可交付产物。

---

## 14. 测试

- 新增：`tests/test_kekkai_activation_state.py` **18/18 OK**、`tests/test_kekkai_utilize_state.py`
  **23/23 OK**（合计 +41）。
- 相关既有：`tests/test_kekkai_utilize_threshold.py` **25/25 OK**（未改）。
- 完整回归 `toolkit/python.exe -m unittest discover -s tests`：**669/669 OK**（628 → 669，
  净 +41 全来自两个新文件）。
- `toolkit/python.exe -m compileall -q tests/test_kekkai_activation_state.py
  tests/test_kekkai_utilize_state.py`：通过。
- `git diff --check`：干净。
- 未启动 MuMu / 游戏 / OAS / ADB / OCR / server。

---

## 15. 生产影响

| 项 | 是否改变 |
|---|---|
| click 顺序 / target | 否 |
| swipe 参数 / duration | 否 |
| sleep / delay | 否 |
| screenshot | 否 |
| OCR | 否 |
| return 值 | 否 |
| exceptions | 否 |
| loop 边界 | 否 |
| 业务策略（星级 / 阈值 / 跨区 / 选卡 / 寄养） | 否 |
| 配置语义 | 否 |

`tasks/KekkaiActivation/*` 本轮零改动；`tasks/KekkaiUtilize/{script_task,config}.py` 的 `M` 是
更早轮次的阈值 / 随机源 WIP（AI_CONTEXT §4.11 / §2），本轮未触碰。本轮生产 diff = **0**。

---

## 16. Git 状态

- branch `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。
- 本轮新增：`tests/test_kekkai_activation_state.py`、`tests/test_kekkai_utilize_state.py`、
  `docs/Kekkai状态机静态收口.md` + 6 文档同步（均未跟踪新文件 / 既有未跟踪文档）。
- 未 commit、未 push、未 merge、未 reset、未 stash、未真机测试。
