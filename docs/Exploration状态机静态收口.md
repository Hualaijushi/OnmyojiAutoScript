# Exploration 状态驱动迁移前静态收口结果

> 2026-09-02。只读审查 + 建模 + characterization，**未改任何 Exploration 生产行为**
> （`git diff -- tasks/Exploration/` 为空，对 HEAD 零 diff）。方法论与
> `docs/Kekkai状态机静态收口.md` / `docs/RealmRaid状态机静态收口.md` 一致：
> 静态收口 → characterization → production diff = 0。
> 源码基准：`tasks/Exploration/{script_task,base,config,page}.py`（HEAD `2cdf3a05`，工作树
> 对该目录无改动），逐行核实。
> 这是状态驱动主线的**第四个**静态收口对象（前三：`list_find` §4.19、Kekkai §4.33、
> RealmRaid §4.34）。

---

## 1. 总结

- **当前运行模型**：Exploration 是四案例里**唯一已经是 page-dispatch FSM** 的任务。
  `run()` = `pre_process()` → `exec_exp_page()` → `post_process()`；核心是 `exec_exp_page()`
  的 `while True`：每轮 `screenshot()` → `get_current_page()` → 用 `exp_page_handle_dict`
  把当前 `Page` 映射到 handler 并执行。没有迭代上限、没有总 `Timer`——靠 `check_exit()`
  的业务条件（够怪数 / 超时 / 队友等待超时）和 `InviteFailedException` 收敛（state-bounded）。
- **最关键的现状（与 RealmRaid 的核心差异）**：Exploration 的 `fire()` 判定「已进入战斗」
  用的是 **正向战斗页确认**——`cur_page in (pages.page_battle_prepare, pages.page_battle)
  → return True`，**不是**「旧标识消失」。而且 `fire()` 是**双重有界**的
  （`max_tries = 4` **且** `Timer(10)`），**可以返回 `False`**，返回 False 后由
  `run_on_exp_main` 做 Task 层 recovery（滑地图找下一个怪 / `arrive_end` 则退出探索）。
  这正是 `docs/RealmRaid状态机静态收口.md` §6「Stronger future candidates」里列的
  "old disappeared **and** expected appeared" 的**上半部分（expected appeared）在
  Exploration 中已经是生产实现**。
- **战斗交接**：完全委托成熟的 `GeneralBattle` Page FSM。Exploration **只覆写
  `_exit_matcher()`**（→ `page_exp_main` 的三选一识别），**不覆写任何结算时序 / 结算点击 /
  reward 处理**——Settlement 100% 走基类 Contract v2 默认。
- **输入通道**：全部经 `self.click` / `self.swipe` / `appear_then_click` → `Control` →
  BehaviorTrace **全覆盖**。**没有一处 `swipe_adb` / `click_adb` / 直连后端**（与 Kekkai
  的两处 `swipe_adb` 直连形成对比）。
- **结构稳定等待**：`arrive_end()` 用 `RuleAnimate(self.I_SWIPE_END).stable(...)`——一个
  **已在生产中的 2 帧模板结构稳定原语**，不是 `module/base/frame_wait.py`。
- **本轮是否改变生产行为**：**否。** 只新增 1 个 characterization 测试文件
  （`tests/test_exploration_state.py`，33 用例）+ 本文档 + 6 文档同步。生产 diff = 0。

---

## 2. 当前完整控制流

```
run()  [入口, tasks/Exploration/script_task.py]
 ├─ pre_process()          # E 自有：进探索页 / 读配置 / 初始化 current_count·start_time·user_status 等
 ├─ exec_exp_page()        # ★ 主 FSM
 └─ post_process()         # goto_page(page_exploration) → (可选 buff 点击) → 末尾 raise TaskEnd

exec_exp_page():            # ★ page-dispatch FSM  [state-bounded，无 range / 无 Timer]
  pre_page = None
  while True:
    screenshot()
    current_page = get_current_page()                       # Navigator：优先级最高的匹配 Page
    current_page is None → time.sleep(0.5); continue         # 未知帧，等一下重来
    check_exit(current_page) is True →
        appear_then_click(I_UI_CANCEL, interval=0.8); break  # 退出点（够怪数/超时/队友等待超时）
    handle = exp_page_handle_dict.get(current_page, None)
    handle is None → goto_page(pages.page_exploration); continue   # 已知 Page 但无 handler
    try:
        handle()
        pre_page = current_page
    except InviteFailedException as e:
        logger.warning(e); break                            # 组队邀请失败 → 结束

exp_page_handle_dict  (property):                            # Page → Callable
    page_exp_main       → run_on_exp_main
    page_exp_settings   → run_on_exp_settings
    page_exp_exit       → run_on_exp_exit
    page_exp_entrance   → run_on_exp_entrance
    page_exploration    → run_on_exp
    page_battle_prepare → run_on_battle          ┐
    page_battle         → run_on_battle          ├─ 三个战斗页共用同一 handler
    page_battle_result  → run_on_battle          ┘
    page_reward         → lambda: self.click(pages.random_click(), interval=0.8)
    page_battle_team    → run_on_battle_team

run_on_exp_main():          # ★ 探索主界面：找怪 → 打怪 / 滑地图
  (pre_page 变化) → device.click_record_clear()              # 防主界面↔奖励页抖动 too-many-click
  collect_reward() → return                                  # 有奖励先领
  user_status != ALONE:
      fire_monster_type == 'boss' → return
      not appear(I_TEAM_EMOJI) → quit_exp_main(); return     # 队友没了 → 退
  switch_rotate() or user_status == MEMBER → return
  fire_button = get_fire_button()                            # boss / normal 目标搜索
  fire_button is not None and fire(fire_button) → return     # ★ 打怪；fire() True 即本轮结束
  fire_monster_type != 'boss' and swipe(S_SWIPE_BACKGROUND_RIGHT, interval=1.5) and arrive_end():
      quit_exp_main()                                        # ← fire() 返回 False 后的 recovery：滑地图；到尽头则退出

fire(button) -> bool:        # ★ 进入战斗（双重有界 verify-retry，可返回 False）
  max_tries = 4
  timeout_timer = Timer(10).start()
  while max_tries > 0 and not timeout_timer.reached():       # [双重上界：次数 4 且 墙钟 10s]
    screenshot()
    cur_page = get_current_page()
    cur_page == page_exp_exit  → need_exit = False; return True   # 退出动画期间又见怪 → 取消退出
    cur_page in (page_battle_prepare, page_battle) → return True  # ★★ 正向战斗页确认
    appear_then_click(button, interval=0.8) → max_tries -= 1; continue
  return False                                               # ★ 四案例里唯一「verify 失败会真的返回 False」的进攻函数

get_fire_button() -> Optional[RuleImage | RuleGif]:
  appear(I_BOSS_BATTLE_BUTTON) → fire_monster_type = 'boss'; return I_BOSS_BATTLE_BUTTON
  return search_up_fight()

search_up_fight(up_type=None):
  up_type == ALL and appear(I_NORMAL_BATTLE_BUTTON) → return I_NORMAL_BATTLE_BUTTON
  按 up_type 选 find_flag (I_UP_EXP / I_UP_COIN / I_UP_DARUMA)
  not appear(find_flag) → return None
  以 find_flag.roi_front 为锚算 roi_back（上方一块区域）
  matches = I_NORMAL_BATTLE_BUTTON.match_all(image, threshold=0.9, roi=roi_back, frame_id=...)
  not matches → return None
  对每个 match 算到 find_flag 中心的欧氏距离；distances.sort()（最近优先）
  I_NORMAL_BATTLE_BUTTON.roi_front = list(最近 match[1:])    # ★ 动态重定位 ROI
  fire_monster_type = 'normal'
  return I_NORMAL_BATTLE_BUTTON

run_on_battle():            # 战斗页 handler → 交接 GeneralBattle
  run_general_battle(self._config.general_battle_config, exit_matcher=pages.page_exp_main)
  self._match_end.refresh()          # 防同一张图多次打怪导致误判「探索结束」
  self.wait_start_time = datetime.now()   # 队友等待计时重置

arrive_end() -> bool:       # 是否滑到地图尽头
  device.click_record.count(S_SWIPE_BACKGROUND_RIGHT.name) >= 6 → click_record_clear(); return True
  return self._match_end.stable(device.image, refresh_after_stable=True, frame_id=device.image_frame_id)
  # _match_end = RuleAnimate(self.I_SWIPE_END)   → 2 帧模板结构稳定
  # E.arrive_end 覆写：exploration_level == EXPLORATION_28 → 直接 return appear(I_SWIPE_END)；否则 super()

check_exit(current_page) -> bool:      # 每轮主循环判是否结束任务
  current_count >= exploration_config.minions_cnt → return True
  now - start_time >= limit_time → return True
  user_status == MEMBER and now - wait_start_time >= invite_config.wait_time_v → return True
  activate_realm_raid(scrolls, exploration_config, current_page)   # 绘卷模式跨任务调度（见 §14）
  return False

open_expect_level():        # 选探索层数（pre_process 阶段）
  swipeCount = 0
  while True:                                   # [bounded: swipeCount >= 25 → raise GameStuckError]
    screenshot; OCR 当前层数; 命中目标层 / I_E_EXPLORATION_CLICK → break
    点 I_UI_CONFIRM / I_UI_CONFIRM_SAMLL；否则按目标层与可见范围 swipe 上/下
    swipeCount += 1; swipeCount >= 25 → raise GameStuckError; time.sleep(1)
  while 1:  选中对应层数（ocr_appear_click + wait_until_appear(I_E_EXPLORATION_CLICK, wait_time=3)）→ break

fill_shikigami():           # 自动轮换填式神（run_on_exp_settings 内）
  O_E_ALTERNATE_NUMBER.ocr → cu >= 40 → goto_page(page_exp_main); return
  点 C_CLICK_STANDBY_TEAM; switch_shikigami_class(rarity)
  pre = -1
  while True:                                   # [state-bounded + stuck 兜底]
    time.sleep(0.5); screenshot
    not appear(I_E_OPEN_SETTINGS) → return             # 打开设置失败
    cur >= 40 → break
    click_record.count(S_SWIPE_SHIKI_TO_LEFT*.name) >= 6:  cur>0 → break 否则 raise GameStuckError
    appear(I_E_ROTATE_EXIST_RIGHT) → swipe 左; continue
    appear(I_E_RATATE_EXSIT)       → swipe 左一格; continue
    pre == cur → cur>0 → break 否则 raise GameStuckError
    pre = cur; click(L_ROTATE_1); click_record_clear()
  goto_page(page_exp_main)
```

---

## 3. State Matrix

| # | State | Recognition | Action | ExpectedState | Current Verify | Current Wait | Failure |
|---|---|---|---|---|---|---|---|
| E1 | ENTRY / PRE | — | `pre_process()`（进探索页、`open_expect_level`、读配置） | 探索页 + 层数正确 | Navigator + OCR 层数 | `goto_page` `Timer(30)`；`open_expect_level` `swipeCount<25` | `raise GameStuckError` / `GamePageUnknownError` |
| E2 | FSM_DISPATCH | `get_current_page()`（Navigator 优先级最高匹配） | 查表 → `handle()` | 任一已登记 Page | — | 无（每轮重新截图重判） | `None` → `sleep(0.5)` 重试；未登记 Page → `goto_page(page_exploration)` |
| E3 | EXP_MAIN / SEARCH | `page_exp_main`（`I_E_SETTINGS_BUTTON` / `I_E_AUTO_ROTATE_ON/OFF` 三选一） | `get_fire_button()` → boss 直接 / normal `search_up_fight` 重定位 ROI | 有可打目标按钮 | boss：`appear(I_BOSS_BATTLE_BUTTON)`；normal：`match_all(threshold=0.9)` 有结果 | 无 | 返回 `None` → 落到「滑地图」分支 |
| E4 | FIRE / BATTLE_ENTERING | `page_exp_main` 上 `fire_button` 存在 | `fire(button)`：循环 `appear_then_click(button, interval=0.8)` | 战斗准备页 / 战斗页 | **正向**：`get_current_page() in (page_battle_prepare, page_battle)`；或 `page_exp_exit` | **双重上界**：`max_tries=4` **且** `Timer(10)`；每轮 `screenshot()` | `return False` → `run_on_exp_main` 滑地图 recovery |
| E5 | BATTLE | `page_battle_prepare` / `page_battle` / `page_battle_result` | `run_on_battle` → `run_general_battle(cfg, exit_matcher=page_exp_main)` | 回到 `page_exp_main` | GeneralBattle Page FSM（成熟） | GeneralBattle `battle_timer` / `_tick_timeout` | `run_general_battle` 返回 `False`（Exploration 未使用其返回值） |
| E6 | BATTLE_RESULT / SETTLEMENT | GeneralBattle `page_battle_result` | 基类 Contract v2：`_settlement_click` 点 `C_RANDOM_RD` HABIT | 退出结算 → `page_exp_main` | 基类 `_evaluate_exit_matcher`（这里是 `Page` → `detect_page_in`） | 基类 `SETTLEMENT_CLICK_INTERVAL_RANGE=(0.7,1.0)`（**未覆写**） | GeneralBattle 兜底 |
| E7 | POST_BATTLE | 回 `page_exp_main` | `_match_end.refresh()` + `wait_start_time = now()` | 继续找下一个怪 | — | — | — |
| E8 | MAP_SCROLL | `fire()` 返回 False 且非 boss | `swipe(S_SWIPE_BACKGROUND_RIGHT, interval=1.5)` | 地图右移露出新怪 / 到尽头 | `arrive_end()`：`click_record.count(...) >= 6` **或** `RuleAnimate.stable` | `interval=1.5` 节流 | 未到尽头 → 下一轮 FSM 继续 |
| E9 | MAP_END | `arrive_end()` True | `quit_exp_main()` → 点 `I_UI_BACK_YELLOW` | 触发退出探索流程 | 后续 FSM 进 `page_exp_exit` | `interval=0.8` | — |
| E10 | EXP_EXIT | `page_exp_exit`（`all_of(I_E_CHECK_EXIT, I_E_EXIT_CONFIRM, I_E_EXIT_CANCEL)`，优先级 88） | `need_exit` ? 点 `I_E_EXIT_CONFIRM` : 点 `I_E_EXIT_CANCEL` | 退出探索 / 取消退出留在探索 | 下一轮 `get_current_page()` | `interval=0.8` | — |
| E11 | REWARD | `page_reward` | `lambda: click(pages.random_click(), interval=0.8)` | 关闭奖励页 | 下一轮 FSM 重判 | `interval=0.8` | — |
| E12 | SETTINGS / AUTO_ROTATE | `page_exp_settings`（`I_E_OPEN_SETTINGS`，优先级 75） | `auto_rotate==no` → 回主界面；否则 `fill_shikigami()` + 点 `I_E_AUTO_ROTATE_OFF` | 轮换开 / 关正确 | `fill_shikigami` 内 OCR `cu>=40` | `fill_shikigami` `sleep(0.5)`/轮 + swipe 计数 6 兜底 | `raise GameStuckError` |
| E13 | ENTRANCE / TEAM | `page_exp_entrance` / `page_battle_team` | 按 `user_status`（LEADER 邀请 / ALONE 进主界面 / MEMBER 接受） | 组队就绪 / 单人进图 | `check_and_invite` / `run_invite` 返回值 | `wait_start_time` 10s 判定 | `raise InviteFailedException` → `exec_exp_page` `break` |
| E14 | EXIT / COMPLETE | `check_exit()` True | `appear_then_click(I_UI_CANCEL)` + `break` → `post_process()` → `raise TaskEnd` | 探索页 → 任务结束 | Navigator | `goto_page` `Timer(30)` | `GamePageUnknownError` |
| E15 | SCROLLS_HANDOFF | `check_exit()` 内 `activate_realm_raid` | 绘卷模式：`set_next_run('RealmRaid'/'MemoryScrolls')` + `raise TaskEnd` | RealmRaid / MemoryScrolls 排入调度 | — | — | 跨任务 recovery（留在 Task 层） |

---

## 4. 目标选择

1. **第一次截图**：`exec_exp_page` 主循环开头 `self.screenshot()`；`run_on_exp_main` 内的
   `collect_reward()` / `appear(I_TEAM_EMOJI)` / `get_fire_button()` 都**复用同一帧**（除非
   它们自己再截）。
2. **目标识别**：
   - **boss**：`get_fire_button()` 先 `appear(self.I_BOSS_BATTLE_BUTTON)`，命中即
     `fire_monster_type = 'boss'`，返回 `I_BOSS_BATTLE_BUTTON`（静态资产 ROI）。
   - **normal**：落到 `search_up_fight()`——按 `up_type` 选一个「UP 标记」模板
     （`I_UP_EXP` / `I_UP_COIN` / `I_UP_DARUMA`），以它的 `roi_front` 为锚构造上方
     `roi_back` 区域，在该区域内 `I_NORMAL_BATTLE_BUTTON.match_all(threshold=0.9)`，对所有
     命中点按「到 UP 标记中心的欧氏距离」升序排序，取**最近的一个**，把
     `I_NORMAL_BATTLE_BUTTON.roi_front` **动态改写**成这个 match 的 `x,y,w,h`，
     `fire_monster_type = 'normal'`，返回 `I_NORMAL_BATTLE_BUTTON`。
   - `up_type == ALL` 且直接能 `appear(I_NORMAL_BATTLE_BUTTON)` 时走捷径，不做重定位。
3. **点击坐标产生**：`fire(button)` 里 `appear_then_click(button, interval=0.8)`。`button`
   是 `RuleImage`，其坐标由 `RuleImage` 自身 `appear_then_click` → 命中区域中心（经
   `ClickSampler.sample` 默认 `LEGACY_UNIFORM` 路径；Exploration 未做 Point opt-in）。
4. **点击之后是否立即截图**：是——`fire()` 的 `while` 每轮开头都 `self.screenshot()`。
5. **是否等待某个明确 `I_*`**：`fire()` 不等特定 `I_*`，而是等 `get_current_page()`
   返回**战斗页 `Page`**（正向）。这比「等某个 `I_FIRE`」更强——直接确认页面转换完成。
6. **是否固定 sleep**：`fire()` 内**没有** `sleep`；`interval=0.8` 只是节流。
7. **是否直接进入下一步**：不是「直接」——`fire()` 每轮重新截图 + 重新 `get_current_page()`，
   直到看到战斗页或双重上界耗尽。
8. **目标没成功打开会怎样**：`get_current_page()` 仍是 `page_exp_main`（或 `None`），
   `appear_then_click(button)` 命中则 `max_tries -= 1`。最多点 4 次、最多 10 秒。
9. **是否再次点击**：是，**最多 4 次**（受 `Timer(10)` 再收紧）。
10. **最大重试次数**：**4**（`max_tries`）。
11. **timeout**：**有**——`Timer(10)`（墙钟 10 秒）。

> **Action → Verify（相对 RealmRaid 的改进）**：`fire()` 的「点 button → 期望进入战斗」
> **有正向验证**（战斗页 `Page` 出现）**且有双重上界**。缺口只剩「4 次 / 10 秒耗尽后
> `return False`」时，`run_on_exp_main` 的 recovery 是「滑地图找下一个怪」——若怪确实
> 在原地只是点击一直没生效，这一轮就被跳过了（见 §13 E-4）。

---

## 5. 进攻 / `fire()`

1. **如何确认进入战斗**：`fire()` 每轮 `get_current_page()`，`cur_page in
   (pages.page_battle_prepare, pages.page_battle)` → `return True`。**正向页面识别**。
2. **点击前是否重新截图**：是。`fire()` 每轮 `while` 开头 `self.screenshot()`，
   `get_current_page()` 与 `appear_then_click` 都在同一新帧上。
3. **是否存在 stale frame**：`fire()` 内**不存在**——判断与点击同帧，且每轮重截。
4. **点击后 ExpectedState**：战斗准备页 / 战斗页（或退出动画页 `page_exp_exit`）。
5. **当前代码实际验证什么**：`get_current_page()` 的返回**恰好等于战斗 `Page`**。
   `get_current_page()` 走 Navigator，`page_battle_prepare` / `page_battle` 各有自己的
   正向识别条件。
6. **是否只是检查原页面标识消失**：**否。** 这是与 RealmRaid `fire()` 的根本区别——
   RealmRaid 是 `not appear(I_RR_PERSON)`（旧标识消失），Exploration 是
   `get_current_page() in (battle pages)`（新页面正向出现）。
7. **页面标识消失/抖动能否误判成功**：**基本不能**。Exploration 要的是**战斗页正向匹配**，
   弹窗遮挡 / 动画中间帧只会让 `get_current_page()` 返回别的 Page 或 `None`，不会误命中
   战斗页。唯一的软肋是 `get_current_page()` 自身把某非战斗帧误判成战斗页，属 Navigator
   识别质量问题，不是 `fire()` 的逻辑缺陷。
8. **是否检查战斗页面明确标识**：**是**（第 5、6 条）。
9. **timeout**：`Timer(10)`。
10. **有限 retry**：`max_tries = 4`。
11. **retry 用尽后**：`return False` → `run_on_exp_main` 走 `swipe(S_SWIPE_BACKGROUND_RIGHT)`
    + `arrive_end()` 分支（Task 层 recovery）。

> **设计意图**（`fire()` docstring 直译）：采用「贪心」——一旦识别到怪就锁定并直接进战斗，
> 保证不漏怪；进入前遇「违规页面」仍留在循环里，是因为怪物移动等原因可能一次点击进不去，
> 若退回主循环会因 UP 旋转等导致重新识别到别的怪、错判怪物类型。所以用**有界**循环在
> `fire()` 内消化「点击没生效」，而不是回主循环。

---

## 6. 战斗进入判定（四案例横向）

| 任务 | 「已进入战斗」判据 | 上界 | 能否返回失败 | 误判风险 |
|---|---|---|---|---|
| RealmRaid `fire()` | `not appear(I_RR_PERSON)`（**旧标识消失**） | 无（`while True`，尾部 `return False` 不可达） | **否**（恒 True） | 中——弹窗/动画/匹配抖动单帧判否即「成功」 |
| Kekkai `screening_card` 等 | `not appear(I_A_EMPTY)` 等（**旧标识消失**） | 部分 `while 1` 无界 | 部分 | 中 |
| **Exploration `fire()`** | **`get_current_page() in (page_battle_prepare, page_battle)`（新页面正向出现）** | **`max_tries=4` 且 `Timer(10)`（双重）** | **是（`return False`）** | **低**——要正向匹配战斗页 |
| `list_find` | `appear(target)` 命中即停（语义） | `for _ in range(max_swipe)`（有界） | 是（返回 None/False） | 低 |

**结论：Exploration `fire()` 是四案例里「进入战斗判定」最完整的一处**——正向确认 + 双重
上界 + 可失败 + 失败后 Task 层 recovery。它可以作为 RealmRaid `fire()` 未来改造
（`docs/RealmRaid状态机静态收口.md` §6 R-R1）的**参照实现**，而不是需要重新设计。

---

## 7. GeneralBattle 交接

- **何时交接**：FSM 命中 `page_battle_prepare` / `page_battle` / `page_battle_result` →
  `run_on_battle()` → `self.run_general_battle(self._config.general_battle_config,
  exit_matcher=pages.page_exp_main)`。
- **参数**：只传 `config` + `exit_matcher`。**不传** `buff` / `battle_key`。`exit_matcher`
  是一个 **`Page` 对象**（`pages.page_exp_main`）——`GeneralBattle._evaluate_exit_matcher`
  的 `isinstance(target, Page)` 分支会用 `detect_page_in` 判定。
- **返回语义**：`run_general_battle -> bool`。**Exploration 不接收也不使用它的返回值**
  （`run_on_battle` 直接丢弃）——胜负统计、`current_count` 递增等由 GeneralBattle /
  其它路径处理。
- **Exploration 特有 override**（`BaseExploration.__dict__` / `ScriptTask.__dict__` 实测）：
  - **`_exit_matcher()`** → `pages.any_of(self.I_E_SETTINGS_BUTTON,
    self.I_E_AUTO_ROTATE_ON, self.I_E_AUTO_ROTATE_OFF)`（= `page_exp_main` 的识别条件，
    战斗结束回到探索主界面的判据）。
  - **仅此一处**。`_handle_result` / `_handle_reward` / `_settlement_click` /
    `PREPARE_CLICK_DELAY_RANGE` / `SETTLEMENT_CLICK_INTERVAL_RANGE` **均未覆写**——
    结算时序、结算点击目标（`C_RANDOM_RD`）、结算点击间隔 `(0.7, 1.0)`、reward 处理
    **100% 走基类 Contract v2 默认**。
- **是否修改 Settlement 行为**：**否**。这是与 RealmRaid 的又一差异——RealmRaid 覆写了
  `_handle_result` + 两个时序常量，Exploration 一个都没碰。
- **T7 Settlement opt-in 是否被 Exploration 间接使用**：**是**（经基类
  `_settlement_click` → `ClickSampler.sample(C_RANDOM_RD.roi_front, strategy=HABIT,
  profile=_SETTLEMENT_PRIMARY_PROFILE)`）。**本轮未改动**。
- **无 quick_exit**：Exploration 不构造 `build_quick_exit_config`，无快退分支
  （测试 `test_no_quick_exit_in_exploration` 锁定）。
- `run_on_battle` 交接后两步收尾：`self._match_end.refresh()`（清 `RuleAnimate` 缓存，
  防同一帧被 `arrive_end` 误判成「已到地图尽头」）+ `self.wait_start_time = datetime.now()`
  （队友等待计时重置）。

---

## 8. 战斗返回 / 地图推进

- **返回判据**：GeneralBattle 内部用 `exit_matcher = page_exp_main` 判定战斗结束、回到
  探索主界面。回来后控制权交还 `exec_exp_page` 的 `while True`，下一轮 `get_current_page()`
  重新识别，命中 `page_exp_main` → `run_on_exp_main` 继续找下一个怪。
- **`arrive_end()` 的双判据**：
  1. `self.device.click_record.count(self.S_SWIPE_BACKGROUND_RIGHT.name) >= 6` —— 已经
     朝右滑了 6 次背景，判定「到底了」，`click_record_clear()` 后 `return True`。
  2. 否则 `self._match_end.stable(self.device.image, refresh_after_stable=True,
     frame_id=...)` —— `_match_end = RuleAnimate(self.I_SWIPE_END)`，用 **2 帧模板结构
     稳定**判断滑动是否已停在尽头标识上。
- **`E.arrive_end` 覆写**：`exploration_level == ExplorationLevel.EXPLORATION_28` 时直接
  `return self.appear(self.I_SWIPE_END)`（28 章版面特殊）；否则 `return super().arrive_end()`。
- **`RuleAnimate.stable` 是既有生产结构原语**——`module/atom/animate.py`，经
  `get_image_client().match_dynamic_template` 做每 ROI 模板级 2 帧稳定检查。它**不是**
  `module/base/frame_wait.py`，两者独立；Exploration 没有 `frame_wait` 消费者（§11）。

---

## 9. Wait Inventory

| 位置 | 当前等待 | 实际目的 | 类型 | 未来是否可能替换 |
|---|---|---|---|---|
| `exec_exp_page` `current_page is None` | `time.sleep(0.5)` | 未知帧，退避后重判 | fixed backoff | 可保留；或改成有上限的重试计数 |
| `fire()` | `Timer(10)` + `max_tries=4` + `interval=0.8` | 进入战斗的双重上界 + 点击节流 | **bounded retry + timeout** | **已是目标形态**（参照 D015 未来 primitive） |
| `run_on_exp_main` 滑地图 | `swipe(S_SWIPE_BACKGROUND_RIGHT, interval=1.5)` | 地图右移节流 | throttle | 保留 |
| `arrive_end()` | `RuleAnimate.stable`（2 帧模板稳定） | 判滑动是否停在尽头 | **structural wait（既有原语）** | 已有实现；理论上可换 `frame_wait`，但 `RuleAnimate` 是模板级、更精确，无必要动 |
| `run_on_exp_entrance` / `run_on_exp` | `datetime.now() - self.wait_start_time >= timedelta(seconds=10)` | 队长等待队友满 10 秒才开打 | semantic deadline | 保留 |
| `open_expect_level` | `time.sleep(1)` / 轮 + `swipeCount >= 25` 兜底 | 层数 OCR 翻页节流 + stuck 上界 | throttle + bounded | 保留 |
| `open_expect_level` 第二段 | `wait_until_appear(self.I_E_EXPLORATION_CLICK, wait_time=3)` | 选中层数后等入口按钮 | **semantic wait（带 `wait_time`）** | **已是目标形态**——Exploration 唯一的 `wait_until_appear` 调用**传了 `wait_time=3`**（与 RealmRaid「全部不传」相反） |
| `fill_shikigami` | `time.sleep(0.5)` / 轮 + swipe 计数 6 兜底 + `pre == cur` 兜底 | 式神列表翻页节流 + 双重 stuck 判定 | throttle + state-bounded | 保留 |
| `run_on_battle` | `self.wait_start_time = datetime.now()` | 战斗后重置队友等待计时 | state reset | 保留 |
| `run_general_battle` 交接后 | 基类 `PREPARE_CLICK_DELAY_RANGE=(3.0,3.0)` / `SETTLEMENT_CLICK_INTERVAL_RANGE=(0.7,1.0)` | 战斗准备 / 结算点击间隔 | frequency gate | GeneralBattle 侧，**未覆写**，本轮不动 |

> **Exploration 有一处真正的「等画面停稳」等待**（`arrive_end` 的 `RuleAnimate.stable`），
> 但它用的是既有的模板级结构原语，不是 `frame_wait`。其余等待要么是 bounded retry
> （`fire`）、要么是 throttle、要么是 semantic deadline。

---

## 10. Loop / Retry Inventory

### Bounded（有次数 / `Timer` 硬上界）

| 循环 | 上限 |
|---|---|
| `fire()` `while` | **`max_tries = 4` 且 `Timer(10)`（双重，任一到即停）** |
| `open_expect_level` 第一个 `while True` | `swipeCount >= 25` → `raise GameStuckError` |
| `goto_page`（全部导航） | `Timer(30)` → `raise GamePageUnknownError` |
| `run_general_battle` 内部 | `battle_timer` / `_tick_timeout` / `_tick_long_battle` |
| `search_up_fight` 距离排序 | `for match in matches`（`match_all` 结果有限） |

### State-bounded（靠业务状态退出，无迭代上限）

| 循环 | 退出条件 | 风险 |
|---|---|---|
| `exec_exp_page` `while True` | `check_exit()` True（够怪数 / 超时 / 队友等待超时）或 `InviteFailedException` | 若 `check_exit` 三条件都长期不满足且 FSM 一直命中已知 Page，靠 `minions_cnt` / `limit_time` 自然收敛 |
| `fill_shikigami` `while True` | `cur >= 40` / `not appear(I_E_OPEN_SETTINGS)` / swipe 计数 6 / `pre == cur` → `break` 或 `raise GameStuckError` | 有 stuck 兜底，无总 `Timer` |
| `open_expect_level` 第二个 `while 1` | `appear(I_E_EXPLORATION_CLICK)` 或 `is_in_room()` → `break` | 无独立上界；靠上一段已把层数调对 |

### Potentially unbounded

**无。** Exploration 没有「无 `Timer`、无次数上限、只靠某标识消失」的裸 `while`——
这与 RealmRaid（6 处）、Kekkai（KA 4 处）形成鲜明对比。`fill_shikigami` /
`open_expect_level` 第二段虽无总 `Timer`，但都有明确的 `break` 条件 + `GameStuckError`
/ 前置约束兜底。

> **`fire()` 是四案例里唯一「进攻 / 进入战斗」性质的、真正双重有界且会返回失败的 retry
> 循环。**

---

## 11. Fresh Screenshot / Stale Frame

| 位置 | 帧来源 | stale 风险 | Level A 可确认？ |
|---|---|---|---|
| `exec_exp_page` 每轮 | 轮首 `self.screenshot()` | 无——每轮重截，`get_current_page` + `handle()` 用同一新帧 | 是（已锁定） |
| `run_on_exp_main` | 复用 `exec_exp_page` 那一帧做 `collect_reward` / `appear(I_TEAM_EMOJI)` / `get_fire_button` | 低——三者紧邻主循环截图，中间无输入动作 | 是 |
| `fire()` 每轮 | `while` 轮首 `self.screenshot()` | **无 stale**——判断与点击同帧 | 是（已锁定） |
| `search_up_fight` | `self.device.image`（复用调用点的帧）做 `match_all` | 低——`get_fire_button` 在 `run_on_exp_main` 内、主循环截图后立即调用 | 是 |
| `arrive_end()` | `self.device.image` + `image_frame_id` 传给 `RuleAnimate.stable` | 低——`RuleAnimate` 自己管 2 帧比对，`refresh_after_stable=True` 稳定后刷新 | 是 |
| `fill_shikigami` | 每轮 `time.sleep(0.5)` 后 `self.screenshot()` | 无——先睡后截 | 是 |
| `open_expect_level` | 每轮 `self.screenshot()` | 无 | 是 |

> **Exploration 没有 RealmRaid `find_one` 那种「原地涂黑共享帧」的副作用，也没有 Kekkai
> 那种「点 A → 不截图 → 同帧继续找/点 B」的模式。** stale 风险在四案例里最低。

---

## 12. Target Relocation Contract

| 目标 | 定位方式 | ROI 是否动态 | 在哪缓存 |
|---|---|---|---|
| boss（`I_BOSS_BATTLE_BUTTON`） | `appear()` 命中区域中心 | 否——静态资产 `roi_front` | 无缓存 |
| normal（`I_NORMAL_BATTLE_BUTTON`） | `search_up_fight` 内 `match_all(threshold=0.9)` + 最近距离排序 | **是——`self.I_NORMAL_BATTLE_BUTTON.roi_front = list(match[1:])` 原地改写** | 改写在**共享的 `RuleImage` 实例**上 |

**关键 nuance（→ Issue Register E-2）**：`get_fire_button()` 在 `run_on_exp_main` 里
**在 `fire()` 循环之前**调用一次，把 `I_NORMAL_BATTLE_BUTTON.roi_front` 定死。随后
`fire()` 的最多 4 次 `appear_then_click(button, interval=0.8)` 都针对**同一个已重定位的
`roi_front`** 做模板匹配。`appear_then_click` 每次仍会在该 ROI 内重新模板匹配（不是缓存
坐标），但**如果怪在这 4 次 / 10 秒里移出了 `roi_front`**，`fire()` 会一直 `appear` 不到
→ `max_tries` 不减 → 靠 `Timer(10)` 超时 `return False`。设计上这是可接受的（贪心 +
recovery 滑地图），但「ROI 在 retry 期间不更新」是一个 Level C 需要观察的点。

> 与 D015 未来 primitive 硬约束 #2（「不缓存业务 target 坐标，每次 attempt 重新定位」）
> 对照：Exploration `fire()` **部分符合**——不缓存**坐标**（每次重 match），但**缓存了
> ROI 窗口**（`roi_front`）。未来若把 `fire()` 迁到 primitive，`action` callback 里应包含
> 「重新 `search_up_fight` 定位」而不只是「在固定 ROI 里 re-match」。

---

## 13. Action → Verify Gap Register

| 位置 | Action | 当前 Verify | 缺口 | 分类 | 未来候选 |
|---|---|---|---|---|---|
| `fire()` | `appear_then_click(button, interval=0.8)` | **`get_current_page() in (battle pages)`（正向）+ `max_tries=4` + `Timer(10)`** | 几乎无——只差「retry 期间不重定位 ROI」（§12） | **P3**（已相当完整） | `action` callback 内含重定位 |
| `run_on_exp_main` fire 失败后 | `swipe(S_SWIPE_BACKGROUND_RIGHT)` | `arrive_end()`（swipe 计数 6 或 `RuleAnimate.stable`） | 已有正向确认 | **P3** | — |
| `run_on_battle` | `run_general_battle(exit_matcher=page_exp_main)` | GeneralBattle Page FSM | 已可靠 | **P3** | — |
| `exec_exp_page` `current_page is None` | `time.sleep(0.5)` | 下一轮重判 | 无重试计数上限（但 `check_exit` 超时兜底） | **P4** | 可加「连续 N 次 None → 处理」 |
| `run_on_exp_exit` | 点 `I_E_EXIT_CONFIRM` / `I_E_EXIT_CANCEL` | 下一轮 FSM 重判 | 无显式确认退出成功 | **P4** | FSM 天然覆盖 |
| `run_on_exp_entrance` 邀请 | `check_and_invite` / `run_invite` | 返回值 + `wait_start_time` 10s | 已有 | **P3** | — |
| `fill_shikigami` | `click(L_ROTATE_1)` 补一个式神 | 下一轮 OCR `cur` 是否变 | `pre == cur` 停滞检测已覆盖 | **P3** | — |
| `open_expect_level` 选层 | `ocr_appear_click(O_E_EXPLORATION_LEVEL_NUMBER)` | `wait_until_appear(I_E_EXPLORATION_CLICK, wait_time=3)` | **已有带 timeout 的语义等待** | **P3** | — |

> **Exploration 的 Action→Verify 缺口在四案例里最小**——`fire()` 已有正向 + 双上界，
> `arrive_end` 有结构确认，选层有带 `wait_time` 的等待。剩下的都是 P3/P4。

---

## 14. Issue Register

| ID | 位置 | 当前行为 | 风险 | 分类 | Level A? | Level C? |
|---|---|---|---|---|---|---|
| E-1 | `search_up_fight` | 把 `self.I_NORMAL_BATTLE_BUTTON.roi_front` **原地改写**成动态 match 结果——修改的是**共享 `RuleImage` 实例**的属性 | 下次进探索若走 boss 分支、或 `up_type==ALL` 捷径，`roi_front` 仍是上一次的动态值，直到再次 `search_up_fight` 覆盖；跨轮次残留 | architecture / reliability | 记录（改动需真机验证） | 是 |
| E-2 | `run_on_exp_main` + `fire()` | `get_fire_button()` 在 `fire()` 循环**之前**定位一次，`fire()` 的 4 次点击针对固定 `roi_front`——retry 期间怪移出 ROI 则只能靠 `Timer(10)` 超时 | 移动怪场景下本轮可能空耗 10 秒再滑地图 | reliability | 记录 | 是（需观察移动怪实际耗时） |
| E-3 | `exec_exp_page` | `current_page is None` → `time.sleep(0.5); continue`，**无连续 None 计数上限** | 若 `get_current_page()` 长期返回 None（版面异常），只靠 `check_exit` 的 `limit_time` 兜底（可能几十分钟） | reliability | 记录 | 是（超时值需真机） |
| E-4 | `fire()` 返回 False 后 | recovery 是「滑地图找下一个怪」——**不重试当前怪** | 若怪在原地、只是点击一直没生效（模拟器卡顿），这一轮怪被跳过 | correctness / reliability | 记录（贪心设计的已知取舍） | 是 |
| E-5 | `run_on_battle` | `run_general_battle(...)` 的返回值**被丢弃** | 战斗失败 / 主动退出 Exploration 侧无感知，靠 FSM 下一轮重新识别页面兜底 | observability | 记录 | 否 |
| E-6 | `exp_page_handle_dict` | `page_reward` 的 handler 是**就地 lambda** `lambda: self.click(pages.random_click(), interval=0.8)`，其余是 bound method | 与其它 handler 形态不一致；`random_click()` 默认 `ltrb`（工作树有意基线 RIGHT-only）经 `default_pages` | style / consistency | 记录 | 否 |
| E-7 | `E.arrive_end` 覆写 | `EXPLORATION_28` 特判读 `self._config.exploration_config.exploration_level`，与基类 `arrive_end` 的结构判定并列 | 非缺陷；28 章版面特殊导致的分叉，维护时容易漏改一处 | architecture | 记录 | 否 |
| E-8 | `open_expect_level` 第二个 `while 1` | 无独立上界（靠第一段把层数调对 + `is_in_room()` 兜底） | 理论上若 `ocr_appear_click` 一直不命中且不 `is_in_room`，可空转 | reliability | 记录 | 是 |
| E-9 | `fill_shikigami` | 无总 `Timer`——靠 `cur>=40` / swipe 计数 6 / `pre==cur` 三条退出 | 已有 stuck 兜底，实际风险低；但没有「整段填式神」的墙钟上限 | reliability | 记录 | 是 |

> **没有一条 E-* 达到 RealmRaid R-R1（进入战斗判定无正向确认）那种优先级**——Exploration
> 的进攻链路本身已经是四案例里最稳的。E-1 / E-2（ROI 动态改写 + retry 期间不重定位）是
> 最值得未来真机观察的两条。

---

## 15. Characterization Tests

`tests/test_exploration_state.py`（**33 用例**，纯 mock，不启动 MuMu / ADB / OCR RPC /
游戏 / server；`ScriptTask.__new__(E)` 造壳，`Mock` / `patch` 注入 `screenshot` /
`get_current_page` / `appear_then_click` / `Timer` 等）：

- **`fire()`（6）**：正向战斗页（`page_battle_prepare` / `page_battle`）→ `return True`
  （1 次截图、0 次点击）；`page_exp_exit` → `need_exit=False` + `return True`；页面不是
  战斗页且点击每次命中 → `max_tries` 递减、**第 4 次后 `return False`**（`appear_then_click`
  恰好 4 次）；点击从不命中 `interval` → 靠 `Timer(10).reached()` 收敛 `return False`；
  源码含 `max_tries = 4` / `Timer(10).start()` / `while max_tries > 0 and not
  timeout_timer.reached():` / `cur_page in (pages.page_battle_prepare, pages.page_battle)`
  / `return False`，且**不含** `not self.appear(`（证明不是「旧标识消失」式）。
- **`get_fire_button()` / `search_up_fight`（3）**：`appear(I_BOSS_BATTLE_BUTTON)` 命中 →
  `fire_monster_type='boss'` + 返回 boss 按钮、不调 `search_up_fight`；不命中 → 透传
  `search_up_fight()` 返回值；`search_up_fight` 源码含 `I_NORMAL_BATTLE_BUTTON.match_all(`
  / `I_NORMAL_BATTLE_BUTTON.roi_front = roi_front` / `fire_monster_type = 'normal'` /
  `distances.sort(`。
- **`exec_exp_page` dispatch（5）**：`while True` + 轮首 `screenshot()` +
  `current_page = self.get_current_page()` + `handle = self.exp_page_handle_dict.get(...)`
  + `self.pre_page = current_page`，且**无 `range(` / 无 `Timer(`**（state-bounded）；
  `current_page is None` → `time.sleep(0.5)`；`handle is None` →
  `goto_page(pages.page_exploration)`；`except InviteFailedException` → `break`；
  handler 字典含 9+ 个 Page 键、三个战斗页共用 `run_on_battle`、`page_reward` 是
  `self.click(pages.random_click(), interval=0.8)` 就地 lambda。
- **GeneralBattle 交接（5）**：`run_on_battle` 调 `run_general_battle` 时
  `kwargs['exit_matcher'] == pages.page_exp_main`、随后 `_match_end.refresh()` 调用一次；
  `_exit_matcher` 在 `BE.__dict__`、源码含三个 `I_E_*` + `any_of`；
  `_handle_result` / `_handle_reward` / `_settlement_click` / `PREPARE_CLICK_DELAY_RANGE`
  / `SETTLEMENT_CLICK_INTERVAL_RANGE` **都不在** `BE.__dict__` / `E.__dict__`（未覆写）；
  `GeneralBattle in E.__mro__`；全模块无 `quick_exit` / `build_quick_exit_config`。
- **`arrive_end`（3）**：`click_record.count(...) >= 6` → `click_record_clear()` +
  `return True`（不调 `_match_end.stable`）；计数不足 → `_match_end.stable(...,
  refresh_after_stable=True)` 决定返回值；`E.arrive_end` 覆写源码含 `EXPLORATION_28` /
  `self.appear(self.I_SWIPE_END)` / `return super().arrive_end()`。
- **`check_exit`（5）**：`current_count >= minions_cnt` / `now - start_time >=
  limit_time` / `MEMBER` 且 `now - wait_start_time >= wait_time_v` 三条各自 `return True`；
  正常情况 `return False` 且调用 `activate_realm_raid` 一次；`activate_realm_raid` 源码含
  `set_next_run(task='RealmRaid'` / `set_next_run(task='MemoryScrolls'` / `raise TaskEnd`
  （跨任务 recovery 留在 Task 层）。
- **循环 / 等待边界（4）**：`open_expect_level` 源码含 `while True:` / `swipeCount >= 25`
  / `raise GameStuckError` / `time.sleep(1)`；`fill_shikigami` 含 `while True:` /
  `time.sleep(0.5)` / `>= 6` / `raise GameStuckError`，**不含 `Timer(`**；`fire` 是唯一
  同时含 `Timer(10).start()` 与 `max_tries = 4` 的循环；AST 扫 `BaseExploration` 模块——
  `wait_until_appear` 调用**恰 1 处且带 `wait_time` kwarg**（与 RealmRaid 相反）。
- **结构事实（5）**：`BaseExploration` + `ScriptTask` 两模块源码**无** `swipe_adb` /
  `click_adb` / `adb_shell` / `*_minitouch` / `self.device.click(` / `self.device.swipe(`
  （输入全走 `Control`）、**无任何 FrameWait token**（`wait_for_changed_and_stable` /
  `frame_wait` / `FrameStateDetector` / `changed_threshold` / …）、含
  `RuleAnimate(self.I_SWIPE_END)` + `self._match_end.stable(`（结构稳定用既有原语）；
  `E.run` 源码里 `pre_process` → `exec_exp_page` → `post_process` 顺序正确、
  `BE.post_process` 含 `raise TaskEnd`。

---

## 16. 四案例对比（`list_find` / Kekkai / RealmRaid / Exploration）

| 维度 | `list_find` | Kekkai | RealmRaid | **Exploration** |
|---|---|---|---|---|
| 运行模型 | 单函数翻页搜索 | 线性状态序列 + 列表滚动 | `while 1` 主循环 + 委托 GeneralBattle | **page-dispatch FSM**（`get_current_page` → handler dict） |
| 进入战斗判定 | N/A | `not appear(旧标识)` | `not appear(I_RR_PERSON)`（旧标识消失） | **`get_current_page() in (battle pages)`（新页面正向）** |
| 进攻 retry 上界 | `for _ in range(max_swipe)`（有界） | 部分 `while 1` 无界 | **无**（`while True`，`return False` 不可达，恒 True） | **`max_tries=4` 且 `Timer(10)`（双重）** |
| 进攻能否返回失败 | 是（None/False） | 部分 | **否** | **是（`return False`）+ Task 层 recovery（滑地图）** |
| `wait_until_appear` 是否带 `wait_time` | N/A | 部分带 | **全部不带**（无超时） | **唯一 1 处调用，带 `wait_time=3`** |
| swipe 通道 | `self.device.swipe`（Control） | **2 处 `swipe_adb` 直连（绕过 Control，无 BehaviorTrace）** | 无 swipe | **全走 `self.swipe`（Control），BehaviorTrace 全覆盖** |
| 结构等待（等画面停稳） | 翻页后固定 `sleep(0.8~1.3)`（D013 待迁移到 `frame_wait`） | `perform_swipe_action` 后 `sleep(2)` 等 | **几乎没有**（活跃路径零固定 sleep） | **`arrive_end` 用 `RuleAnimate.stable`（既有 2 帧模板结构原语）** |
| GeneralBattle 耦合 | 无 | 无（Kekkai 不打战斗） | **深**：覆写 `_handle_result` + `_exit_matcher` + 2 个时序常量 | **浅**：只覆写 `_exit_matcher`（→ `page_exp_main`），结算 100% 走基类 |
| Recovery 形态 | 返回 False 交调用方 | `_record_utilize_failure` / `set_next_run(+N min)` / 改 config | `when_attack_fail` 三分支 + `check_refresh` CD | **`fire()` False → 滑地图 / `arrive_end` 退出**；`check_exit` → `activate_realm_raid` 跨任务 `set_next_run` + `raise TaskEnd` |
| 无界裸 `while`（无 Timer 无计数） | 0 | KA 4 处 | 6 处 | **0** |
| FrameWait 生产消费者 | 0 | 0 | 0 | **0** |
| stale frame 风险 | 中（末轮仍 swipe 等已知瑕疵） | 中（点 A→不截图→同帧点 B） | 低（`find_one` 原地涂黑是唯一副作用） | **最低**（每轮重截，无共享帧副作用） |

### 是否出现了值得抽公共层的稳定共同模式

四案例看完，判断**没有变**（`docs/DECISIONS.md` D015 的 PARTIAL 结论继续成立）：

1. **「点击 → 等状态迁移」的骨架**在四处都有，但**判据强度差异极大**——从 `list_find` 的
   `appear(target)`、到 RealmRaid 的「旧标识消失」、到 Exploration 的「新页面 `Page` 正向
   出现」。Exploration 证明了**最强形态（正向 + 双上界 + 可失败 + Task recovery）是可行且
   已在生产中的**，但也正因为它已经写好了，**没有「零消费者下先抽一个组件」的必要**——
   未来真要抽，直接照 `fire()` 的形状抽。
2. **`fire()` 是 D015 未来 bounded-retry primitive 的近似现成参照**：
   - 符合硬约束 #1（循环 + 计 `attempts`（`max_tries`）+ 独立 `timeout`（`Timer(10)`）+
     任一到即停）——只差「返回 frozen result 而非 bool」。
   - 符合 #3（primitive 不 screenshot——`fire()` 在循环体里自己 `screenshot()`，
     verify 读新帧）。
   - 符合 #4（不做 recovery——`fire()` 只 `return False`，`run_on_exp_main` 读结果后自己
     滑地图 / 退出）。
   - 符合 #5（异常透传——`fire()` 无 try/except）。
   - **部分偏离 #2**（不缓存坐标 ✔，但缓存了 `roi_front` 窗口 ✘——见 §12 E-2）：未来迁移
     时 `action` callback 要包含「重新 `search_up_fight` 定位」。
3. **三者/四者的「等待」不是同一层**（D013 / D015 已述）：`list_find` 纯视觉结构等待、
   RealmRaid 纯语义、Kekkai 两类都有、Exploration 语义为主 + 一处 `RuleAnimate` 结构等待。
   **不能一次抽完。**

**结论：本轮不抽任何公共层。** Exploration 作为第四个案例，主要价值是**证明 D015 提的
retry primitive 形状是对的**（有一个生产实现印证），以及**把「进入战斗判定」的参照实现
从"待设计"变成"照抄 `fire()`"**。

---

## 17. FrameWait

**Exploration production FrameWait consumers = 0。**

- `tasks/Exploration/{script_task,base}.py` 不 import 也不引用
  `module/base/frame_wait.py` / `wait_for_changed_and_stable` / `module/atom/frame_state.py`
  / `FrameStateDetector` / `changed_threshold` / `stable_threshold` / `stable_frames`
  （测试 `test_no_frame_wait_consumer_in_exploration` 锁定）。
- 本轮**未写入**任何 `ROI` / `changed_threshold` / `stable_threshold` / `stable_frames` /
  `timeout` 猜测值。
- **候选面**：`arrive_end()` 的「等滑动停在尽头」是唯一 structural-wait 语义位置，但它
  已用 `RuleAnimate.stable`（模板级 2 帧稳定，比 `frame_state` 的整块帧差更精确）实现，
  **无迁移动机**。`fire()` 进入战斗更适合 **semantic（`get_current_page()` 正向）**——
  已经是这样。

---

## 18. D015 再验证

Exploration 作为第四案例，对 `docs/DECISIONS.md` D015 的每条逐一核对：

| D015 条文 | Exploration 证据 | 是否需要改 D015 |
|---|---|---|
| 四类职责分属不同 owner，不合并成万能 API | `fire()`（Verify + Retry）/ `run_on_exp_main` 滑地图（Recovery）/ `check_exit` → `activate_realm_raid`（跨任务 Recovery）/ `arrive_end` 的 `RuleAnimate`（结构 Wait）—— 四类清晰分离在不同函数 | **否**，进一步印证 |
| 不新增 `Verifier` / `ActionVerifier` 类 | Exploration 的 verify 是 `get_current_page() in (...)`，又一种形态（前三案例是坐标 tuple / `not appear` / `appear` / OCR）——抽类只会更别扭 | **否** |
| 语义等待用 `wait_until_appear(wait_time=)`，视觉结构等待用 `frame_wait` | Exploration 恰好各有一例：`wait_until_appear(I_E_EXPLORATION_CLICK, wait_time=3)` + `arrive_end` 的 `RuleAnimate.stable`。两者确实是不同机制、不同位置 | **否** |
| Recovery 永远留在 Task | `fire()` 只 `return False`；滑地图 / `quit_exp_main` / `activate_realm_raid` + `raise TaskEnd` 全在 `run_on_exp_main` / `check_exit` | **否**，教科书级印证 |
| `max_attempts` 与 `timeout` 正交、同时存在、任一先到即止、数值由调用方给 | **`fire()` 就是这个模型的现成实现**：`max_tries=4` 且 `Timer(10)`，`while max_tries > 0 and not timeout_timer.reached()` | **否**，且从"三案例都没有 bound"更新为"Exploration `fire()` 已有 bound，是参照实现" |
| 当前不新增公共 retry 抽象（PARTIAL） | Exploration 没有制造"需要抽"的新压力——`fire()` 已经把这套写好了，零消费者下抽组件仍无必要 | **否** |
| 未来 primitive 硬约束 #1~#6 | §16.2 逐条核对：#1 ✔（bool 非 frozen result）/ #2 部分（缓存 `roi_front`）/ #3 ✔ / #4 ✔ / #5 ✔ / #6 N/A | **否**，但给 #2 增加一个真实反例数据点（迁移时 `action` 要含重定位） |
| `module/base/retry.py` `@retry` 不适配 task 层 | Exploration `fire()` 是 verify 触发式（看 `get_current_page`），不是异常触发式——再次印证两者不同 | **否** |
| BehaviorTrace 下一个事件是 `RETRY` | `fire()` 一次调用 = 一次 bounded retry 循环，天然可记 `target=battle-entry` / `attempts=4-max_tries` / `elapsed` / `outcome=success|timed_out`——正是 `RETRY` 事件设想的形状 | **否**，印证事件设计 |

**结论：D015 无需修改。** Exploration 是四条案例里对 D015 每一条都正向印证的一个，且把
「未来 retry primitive」从纯设想升级为「有一个生产参照实现（`fire()`）」。唯一的补充是
给硬约束 #2 记一个真实注意点（`fire()` 缓存了 `roi_front` 窗口，迁移时 `action` callback
要包含重新定位）。这条补充写入本文档即可，不改 D015 正文（D015 #2 本就说「动态列表每次重
match / 重算」，Exploration `fire()` 的 `roi_front` 缓存是**它当前实现的瑕疵**，不是对
D015 的反驳）。

---

## 19. 测试

- 新增 `tests/test_exploration_state.py`：**33/33 OK**。
- 完整回归 `toolkit/python.exe -m unittest discover -s tests`：**741/741 OK**
  （708 → 741，净 +33 全来自新文件）。
- `toolkit/python.exe -m compileall -q tests/test_exploration_state.py`：通过。
- `git diff --check`：本轮新增文件干净（仓库级 non-zero 来自**既有用户 WIP**
  `tasks/Component/GeneralBattle/assets.py` 的行尾空格 / EOF 空行，非本轮引入，按规则不动）。
- 未启动 MuMu / 游戏 / OAS / OASX / ADB / OCR RPC / server。

---

## 20. 生产影响

| 项 | 是否改变 |
|---|---|
| FSM dispatch / handler 表 | 否 |
| `fire()` 双重上界 / 正向判定 / retry 数 | 否 |
| `get_fire_button` / `search_up_fight` ROI 重定位 | 否 |
| `run_on_battle` 交接参数（`exit_matcher=page_exp_main`） | 否 |
| GeneralBattle / Settlement Contract v2（Exploration 未覆写结算） | 否 |
| `arrive_end` 双判据 / `RuleAnimate` | 否 |
| `check_exit` 三条件 / `activate_realm_raid` 跨任务调度 | 否 |
| `open_expect_level` / `fill_shikigami` 循环边界 | 否 |
| screenshot / OCR / swipe 通道 / return / exceptions | 否 |
| Exploration T7 点击（未做 Point opt-in，仍 `LEGACY_UNIFORM`） | 否 |

`git diff -- tasks/Exploration/` 为空。本轮生产 diff = **0**。

---

## 21. Git 状态

- branch `master`，HEAD `2cdf3a0571b0449748aabef259da5cbd2378536c`（未变）。
- 本轮新增：`tests/test_exploration_state.py`、`docs/Exploration状态机静态收口.md` +
  项目文档同步（`docs/AI_CONTEXT.md` §4.37、`docs/DEVELOP_LOG.md`、`docs/ROADMAP.md`、
  `docs/ARCHITECTURE.md`——均为未跟踪新文件 / 既有未跟踪文档）。
- `tasks/Exploration/` 对 HEAD 零 diff。
- 未 commit、未 push、未 merge、未 reset、未 stash、未真机测试。
