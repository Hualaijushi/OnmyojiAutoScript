# KekkaiUtilize 当前蹭卡 / 好友寄养流程重新审查

> **本文是改造前审查（图 A = 改造前的真实流程）。改造已于 2026-09-03 同日实施——非怠惰路径
> 的 `_select_optimal_resource_card` / `_current_select_best` / `_reselect_best_card` / global-best
> 已被「单向分区 PASS 序列」取代，见 `docs/DECISIONS.md` D017 + `docs/AI_CONTEXT.md` §4.41 +
> `docs/DEVELOP_LOG.md`「2026-09-03 KekkaiUtilize 单向分区搜索改造」。下文的 §22 Gap Matrix
> 三大差异已解决；§4 图 A、§10、§14 描述的旧标准路径已删除；§6「当前列表扫描算法 = C」不再
> 成立。§5（跨区/同区机制）、§7-9（识别 / OCR / 回列表）、§11-13（滑动 / 到底 / switch）、
> §16-17（寄养 verify / failure recovery）、§21 图 B（用户目标流程）仍是有效背景。怠惰模式
> 相关描述仍然准确。**

> 2026-09-03。**只读审查——未改任何 KekkaiUtilize 生产代码、未改测试**（`production diff = 0`）。
> 目的：用当前真实源码把「现在 KekkaiUtilize 到底怎么找卡 / 选卡 / 切区 / 判收益 / 滑动 /
> 回选 / 寄养 / 失败恢复」彻底讲清楚，并与用户目标流程做逐项 Gap 对比。
> 事实源优先级：当前源码 > 当前 git diff > `docs/AI_CONTEXT.md` > 专题 / DEVELOP_LOG > 历史总结。
> 源码基准：HEAD `2cdf3a05` + 工作树未提交 WIP（`tasks/KekkaiUtilize/script_task.py` `+205/-46`、
> `config.py` `+4`）。

---

## 1. 总结

**当前实现与用户目标流程：PARTIAL。**

蹭卡状态机的「骨架」大体到位——有界扫描、逐张点开读收益、跨区/同区双分组、按收益值回选、
寄养有真实 verify、不依赖好友名 OCR。但与「跨区优先 → 同屏六星候选逐个查实际收益 → 找到
满足条件立即寄养 → 跨区到底后同区继续」这条人工流程相比，三个最大差异：

1. **跨区 / 同区顺序由配置项 `select_friend_list` 决定，默认是「同区优先」——与「跨区优先」
   相反**（`run_utilize` `enumerate((friend, fallback_friend))`；`config.py` 默认
   `SelectFriendList.SAME_SERVER`）。要「跨区优先」得改默认值或改成硬编码顺序。
2. **同一屏内的扫描顺序是「屏幕 y 位置从上到下」，不是「星级从高到低」**。
   `ImageGrid.find_everyone` 把所有命中的 tier 图标按 y 升序返回；`order_cards` / `order_targets`
   的顺序只影响 `_card_rank`（挑「最优」），**不影响点击顺序**。于是会先点物理靠上的 4 星、
   再点靠下的 6 星（除非该类型 6 星已被点开确认满值触发剪枝）。用户要「优先检查六星」。
3. **默认收益阈值 = 六星满值（太鼓 76 / 斗鱼 151）→ 实际行为是「扫完当前分组整列表 +
   `_reselect_best_card` 回到顶部按收益值回选最优」，不是「找到满足条件的卡就立即寄养」**。
   `_reaches_reward_threshold` 命中会立刻停，但默认阈值等于理论最高值、满值卡罕见，所以几乎
   总是走到「扫全 + 回选」。用户要「找到满足条件就可以立即寄养，不要求先扫全找理论最优」。

其余目标项（当前屏多候选逐个检查、点击后读实际收益、按收益值而非位置匹配、当前屏检查完
再滑、跨区到底切同区、同区扫到底、不依赖好友名 OCR、bounded loop、fresh screenshot、寄养
success verify）**已实现或基本实现**；「detail load verify」「swipe stable verify」当前是
固定 `sleep(2)`，属未实现（本轮不接 FrameWait）。

---

## 2. Git 状态

- branch：`master`
- HEAD：`2cdf3a0571b0449748aabef259da5cbd2378536c`
- staged：无
- unstaged（本审查相关）：`tasks/KekkaiUtilize/script_task.py`（`+205/-46`，2026-08-30 选卡/可靠性
  WIP，见 `docs/AI_CONTEXT.md` §4.11）、`tasks/KekkaiUtilize/config.py`（`+4`，两个收益阈值字段）。
  其余 unstaged / untracked 为无关的长期 WIP（疲劳系统、BehaviorTrace、ClickSampler、
  GeneralBattle V3、docs 体系等）。
- 未 commit、未 push、未 merge、未 reset、未 stash、未真机。

---

## 3. 当前 `run()` 完整调用链

```
run()
 ├─ 重置 8 个 utilize_* 实例标志
 ├─ (utilize_enable and lazy_mode) → lazy_roll = random_delay(0.0, 1.0)   # 当 [0,1] 随机数用，不是等待
 │      utilize_lazy_mode_active = lazy_roll < lazy_mode_weight           # 默认 weight=1.0 → 恒 active（若 lazy_mode 开）
 ├─ goto_page(page_guild_realm)
 ├─ (utilize_enable) → check_utilize_add()                               # ★ 蹭卡主循环，返回 bool
 │     └─ (返回 False 仅当 utilize_terminal_failure) → run() 直接 return（不 raise TaskEnd）
 ├─ check_max_lv(shikigami_class, auto_fill)                             # 维护：满级式神替换 / auto_fill
 ├─ (utilize_harvest) → check_utilize_harvest()                          # appear(I_UTILIZE_EXP) → ui_get_reward
 ├─ check_box_ap_or_exp(box_ap_enable, box_exp_enable, box_exp_waste)    # 体力盒 Timer(6) / 经验壶 Timer(12)+max_tries
 ├─ receive_guild_assets(harvest_guild_max_times)                        # for i in range(1,N+1)，一次没收到即 break
 ├─ (not utilize_enable) → set_next_run(finish=True, success=True)       # 注意：utilize_enable 时这里不设 next_run
 ├─ goto_page(page_main)
 └─ raise TaskEnd

check_utilize_add():                                                     # while 1，bounded: utilize_add_count >= 5
   utilize_add_count += 1
   >= 5:
     not utilize_found_eligible_card → push_notify('未检测到四星及以上<目标>, 5分钟后再次执行')
     else                           → logger('已检测到四星以上，但未能完成选择，5分钟后重试')
     set_next_run(now + 5min); return True                              # ★ 不区分「没卡」vs「有卡没选上」，都 return True
   sleep(0.5)
   goto_page(page_guild_realm_growth); screenshot()
   not appear(I_UTILIZE_ADD):                                           # ★ 成功闭环：育成页「加寄养卡」按钮已消失
     remaining = O_UTILIZE_RES_TIME.ocr(image)                          # RuleOcr mode=Duration → timedelta（失败→timedelta(0)）
     异常(非 timedelta / <= 0 / > 12h) → remaining = 5min 兜底
     next_time = now + remaining；min_run_interval>0 时 next_time = max(next_time, now+min_run_interval)
     set_next_run(now=next_time); return True                           # ★ 唯一「真正蹭上了」出口
   if not goto_page(page_guild_realm_utilize): logger('Utilize failed, exit')   # R-U6：不 return，继续往下
   run_utilize(select_friend_list, shikigami_class, shikigami_order)    # ★ 选卡 + 寄养
   utilize_terminal_failure → return False
   goto_page(page_guild_realm_growth)                                   # while 再转一圈
```

---

## 4. 当前状态图（图 A：真实实现）

```
run_utilize(friend = config.select_friend_list):        # 默认 friend = SAME_SERVER（同区）
  fallback_friend = 另一个分组
  for (index, target_friend) in enumerate((friend, fallback_friend), start=1):   # 恰好 2 组，配置项决定谁先
    _reset_utilize_friend_list(target_friend)           # switch_friend_list ×2~3 + self.swipe(S_U_END, interval=3)[Control]
        GamePageUnknownError → _record_utilize_failure('刷新好友列表失败'); return（→ False，不切区）
    lazy_mode_active?
      _select_lazy_resource_card()                      → True / None / False
      _select_optimal_resource_card(target_friend)      → True / None / False
    True  → selected_friend = target_friend; break      # 选中即停，不再看另一区
    False → return False                                # 有可用卡但选卡失败：不切区、不记 failure，交给 check_utilize_add 重转
    None  → 这个分组没有当前策略四星+，继续 fallback
  selected_friend is None → _finish_low_value_utilize()（set_next_run +20min，terminal）; return（→ False）

  # ---- 已在某分组选中目标（当前屏侧栏选中的即目标）----
  utilize_add_count = 0
  screenshot()
  not appear(I_U_ENTER_REALM) → _record_utilize_failure('未识别到进入结界按钮'); return
  goto_page(page_friend_utilize)                        # GamePageUnknownError/GameStuckError → _record_utilize_failure
  screenshot()
  stop_image = appear(I_U_ADD_1)                       ? I_U_ADD_1        # 右侧第一坑
             : (appear(I_U_ADD_2) and not appear(I_U_ADD_1)) ? I_U_ADD_2 # 只剩右侧第二坑
             : None
  stop_image is None → save_image('没有坑位'); _record_utilize_failure('目标结界已经没有可用坑位'); return
  switch_shikigami_class(shikigami_class)
  set_shikigami(shikigami_order, stop_image)            # 委托 ReplaceShikigami；while 1 + Timer(120)→GameStuckError
                                                        #   verify = not appear(stop_image) → 坑位被填 = 寄养成功
      GamePageUnknownError/GameStuckError → _record_utilize_failure('式神寄养失败'); return
  utilize_failed_count = 0; return True

_select_optimal_resource_card(friend):                  # 普通模式（非 lazy）
  reset ap_max_num / jade_max_num / utilize_best_* / utilize_last_*
  reached_threshold = _current_select_best()            # 浏览当前分组、逐张点开读收益、记录最优/最后
  reached_threshold → return True                       # 扫描中命中 config 阈值 → 当前侧栏选中的就是目标
  utilize_best_card_class is not None?
    (utilize_last_card_class == utilize_best_card_class and utilize_last_value == utilize_best_value)
        → return True                                   # 最后点开的正好是最优 → 直接进结界
    else:
        _reselect_best_card(friend) ? return True : return False   # 回到顶部按「收益值」回选最优
  utilize_current_group_has_eligible_card → return False # 有四星+ 但 OCR 全失败
  not utilize_current_group_scan_completed → return False# 没扫完，不能判低价值
  → return None                                         # 全是当前策略低价值卡

_current_select_best():                                 # for swipe_count in range(21)  &  Timer(120)
  每屏:
    screenshot(); cards = order_targets.find_everyone(image)   # 所有命中的 tier 图标，★按屏幕 y 升序（上→下）
    not cards:
      miss_count += 1
      miss_count > 3 or appear(I_U_EMPTY_CARD) → scan_completed=True; return False   # 到底
      perform_swipe_action(); continue
    miss_count = 0
    for (target, _, area) in cards:                     # ★按屏幕位置，不是星级
      card_class = target_to_card_class(target); tier = CARD_TIER_INFO.get(card_class)
      tier → utilize_found_eligible_card = True; utilize_current_group_has_eligible_card = True
      card_class in maxed_card_classes → continue       # 该档已确认满值，不再点同档
      star < confirmed_highest_stars[card_type] → continue   # 已确认更高星，不再点同类型更低星
      C_SELECT_CARD.roi_front = area; click(C_SELECT_CARD); sleep(2)   # 选中该卡（侧栏刷新）；固定等 2s
      card_type, card_value = check_card_num()          # O_CARD_NUM 固定 ROI(800,421,150,33) OCR → 关键字判类型 + 正则取数
      unknown / value<=0 / 类型不在 RESOURCE_CONFIG → logger('跳过无效卡'); continue   # ★OCR 失败 = 跳过，不更新 last/best
      更新 confirmed_highest_stars / maxed_card_classes / ap_max_num|jade_max_num（取 max）
      utilize_last_card_class/value = 本次
      rank = _card_rank(card_class)                     # order_cards.index，越小越优先；跨类型比较只看 rank
      rank < best_rank 或 (rank==best_rank and value>best_value) → 更新 utilize_best_*
      _reaches_reward_threshold(card_type, card_value)? → return True   # 停止浏览，当前选中即目标
    appear(I_U_EMPTY_CARD) → scan_completed=True; return False
    perform_swipe_action()                             # 滑一屏
  scan_completed=True; return False                     # 21 屏跑完

_reselect_best_card(friend):                            # 回选：回到顶部按「收益值」找回最优
  _reset_utilize_friend_list(friend)
  for _ in range(21)  &  Timer(120):
    screenshot(); cards = order_targets.find_everyone(image)
    not cards: miss_count += 1; (miss_count>3 or I_U_EMPTY_CARD → return False); perform_swipe_action(); continue
    for (target, _, area) in cards:
      tier = CARD_TIER_INFO.get(card_class)
      not tier or tier[0] != target_type → continue    # 类型不符跳过
      tier[2] < target_value → continue                # 档位上限低于目标值不可能是目标，剪枝不点开
      C_SELECT_CARD.roi_front = area; click; sleep(2); (card_type, card_value) = check_card_num()
      card_type==target_type and card_value>=target_value → return True   # OCR 校验通过才算找回
    appear(I_U_EMPTY_CARD) → return False
    perform_swipe_action()
  return False                                          # 21 屏跑完仍没找回

_select_lazy_resource_card():                           # 怠惰模式
  for swipe_count in range(21)  &  Timer(120):
    screenshot(); cards = lazy_scan_targets.find_everyone(image)   # 全部四星+ 资源卡（6 张模板）
    eligible = [符合当前 rule 的卡]（_lazy_card_matches_rule）
    eligible 非空:
      high_star = [星级>=5 的]；target = high_star[0] if high_star else eligible[0]   # ★首张，不点开不读收益
      C_SELECT_CARD.roi_front = area; click; sleep(2); return True   # 选首张符合策略的即完成，不 OCR 收益、不回选
    miss_count = 0 if cards else miss_count + 1         # 当前屏有别策略四星+ 也算「仍在有效区」，不计 miss
    appear(I_U_EMPTY_CARD) → scan_completed=True; return None
    miss_count > 3 → scan_completed=True; return None
    perform_swipe_action()
  return None

switch_friend_list(friend):
  check_image = I_UTILIZE_FRIEND_GROUP(同区) / I_UTILIZE_ZONES_GROUP(跨区)
  while 1  &  Timer(20) → raise GamePageUnknownError:
    screenshot(); appear(check_image) → break
    timer_click(1s) 到点 → self.device.click(check_image.coord())
  DIFFERENT_SERVER: sleep(1);  统一 sleep(0.5)

perform_swipe_action():
  p1 = (random_int(340,600), random_int(500,565)); p2 = (p1.x, p1.y - 416); duration = 2
  self.device.swipe_adb(p1, p2, duration=2)             # ★直连，绕过 Control.swipe / BehaviorTrace / distance_check / cache invalidation
  self.device.click_record_clear(); time.sleep(2)       # ★固定 sleep 等列表停稳，无 changed/stable 判定
```

---

## 5. 跨区 / 同区顺序

| 项 | 事实（源码） |
|---|---|
| 谁先扫 | `run_utilize` `for target_friend in enumerate((friend, fallback_friend))`。`friend` = `config.kekkai_utilize.utilize_config.select_friend_list`。**`config.py` 默认 `SelectFriendList.SAME_SERVER`（同区）**。所以默认「同区优先，跨区备选」。 |
| 两个分组叫什么 | `SAME_SERVER='same_server'`（同区，图标 `I_UTILIZE_FRIEND_GROUP` @ `(216,92)`）/ `DIFFERENT_SERVER='different_server'`（跨区，图标 `I_UTILIZE_ZONES_GROUP` @ `(337,92)`）。 |
| 是否必然两个都扫 | 否。第一分组 `_select_*` 返回 `True`（选中）→ `break`，不看第二组；返回 `False`（有卡但选卡失败）→ `run_utilize` 直接 `return False`，也不看第二组；只有返回 `None`（该组没有当前策略四星+）才继续 `fallback`。 |
| 满足卡后 | 立即 `break`，不再扫另一区（`selected_friend = target_friend`）。 |
| 跨区扫完无卡 → 切同区 | 若 config = `DIFFERENT_SERVER`：跨区 `_select_*` 返回 `None` → for 循环进入 `fallback = SAME_SERVER`。（默认 config 顺序相反。） |
| 同区扫完无卡 → 退出 | 两个分组都返回 `None` → `selected_friend is None` → `_finish_low_value_utilize()`（`set_next_run` +20min，`utilize_terminal_failure=True`）→ `run_utilize` `return`（→ False）→ `check_utilize_add` `return False` → `run()` 直接 `return`。 |
| 切换失败 | `_reset_utilize_friend_list` 里 `switch_friend_list` 超时 20s → `raise GamePageUnknownError` → `run_utilize` catch → `_record_utilize_failure('刷新好友列表失败')` → `return`（→ False，不升级为重启游戏）。`_reselect_best_card` 里同样的异常 → `return False`。 |
| `switch_friend_list` timeout | 有：`Timer(SWITCH_FRIEND_LIST_TIMEOUT=20)` → `raise GamePageUnknownError`。 |
| 切换后是否等页面确认 | 有：`while 1` 靠 `appear(check_image)` 退出；之后 `DIFFERENT_SERVER` 额外 `sleep(1)`，统一 `sleep(0.5)`。除 `appear(check_image)` 外无其它验证。 |

---

## 6. 当前列表扫描算法

**结论：C（扫完当前分组整列表，再按收益值 `_reselect_best_card` 回选最优）+ 一个几乎不触发的
「命中 config 阈值即停」早退。**

- 进入某分组后，`_current_select_best` 的 `for swipe_count in range(21)`：每屏 `screenshot` →
  `order_targets.find_everyone` → **对当前屏所有命中候选逐个** `click(C_SELECT_CARD)` +
  `sleep(2)` + `check_card_num()`（读实际收益）→ 记录 `utilize_best_*`（按 `_card_rank`）/
  `utilize_last_*` → `_reaches_reward_threshold` 命中 → **`return True` 立即停**。
- 当前屏所有候选查完 → `perform_swipe_action()` 滑下一屏 → 重复，直到 `I_U_EMPTY_CARD` /
  连续 3 屏无卡 / 21 屏 / `Timer(120)`。
- 扫完没命中阈值：`_select_optimal_resource_card` 检查「最后点开的 == 最优」？是 → 直接进结界；
  否 → `_reselect_best_card(friend)`：**回到列表顶部再走一遍，按收益值（而非位置）匹配**，
  用 `CARD_TIER_INFO` 档位上限剪枝，OCR 校验 `card_value >= target_value` 才算找回。
- **默认阈值 `taiko_reward_threshold=76` / `fish_reward_threshold=151` = 六星满值**（`config.py`
  注释：「等价于改动前只有命中理论最高收益才提前停止的行为」）。满值卡罕见 → 实际几乎总是
  「扫全 + 回选」。调低阈值（如 67 / 134）→ 绝大多数情况在第一趟命中阈值早退、不走回选。

**不是**：A（第一张满足即用——只有把阈值调得很低才近似）；也不是 B（只扫当前屏选 best）。

---

## 7. 星级 / 卡种 / 收益识别

### 能识别的星级 / 卡种

- `order_targets`（普通模式扫描用的 `ImageGrid`）：
  - `UtilizeRule.DEFAULT` → `[I_U_FISH_6, I_U_TAIKO_6, I_U_FISH_5, I_U_TAIKO_5, I_U_FISH_4, I_U_TAIKO_4]`
  - `UtilizeRule.FISH` → `[I_U_FISH_6, I_U_FISH_5, I_U_FISH_4]`
  - `UtilizeRule.TAIKO` → `[I_U_TAIKO_6, I_U_TAIKO_5, I_U_TAIKO_4]`
- 即**只识别 4 / 5 / 6 星的斗鱼（fish）与太鼓（taiko）**。`target_to_card_class` 还能映射
  `I_U_TAIKO_3` / `I_U_FISH_3` / `I_U_MOON_2..6`，但这些**不在任何 rule 的 `order_targets`**
  里，扫描阶段不会命中（`order_cards` 里有 `TAIKO3`/`FISH3` 但只用于 `_card_rank` 排序，
  `CARD_TIER_INFO` 也不含 3 星，`_card_rank` 对不在表里的返回 999）。
- 卡种 = **模板图匹配**（`RuleImage` `method="Template matching"` `threshold=0.8`，
  `find_everyone` 内 `threshold=0.8` `nms_threshold=0.3`），匹配的是每张好友结界卡上的
  「卡种 + 星级」小图标（`utilize_u_fish_6.png` 等），图标 `roi_back` 是一条 x≈530-620、
  y≈156-600 的竖直条带（好友卡在这一列纵向排列）。**不用 OCR / 颜色判卡种星级。**

### 优先什么

- `UtilizeRule` 决定卡种优先（DEFAULT = 太鼓或斗鱼都行 / TAIKO = 只太鼓 / FISH = 只斗鱼）。
- 星级：`order_cards` / `order_targets` 把 6 星排在 5 星前、5 星前于 4 星，但**这只影响
  `_card_rank`（挑最优卡）与剪枝，不影响同屏点击顺序**（见 §1 差异 2）。
- 收益：`_reaches_reward_threshold(card_type, card_value)` = `card_value >= config 阈值` **且**
  `card_type` 符合当前 rule。命中即停止浏览、当前选中即目标。
- 组合：卡种（rule）为硬条件，收益阈值为「够好就停」条件，`_card_rank` 为「都不够阈值时选谁」。

### 星级识别与收益识别谁先

- **先星级/卡种（模板匹配 `find_everyone`）→ 再点开卡 → 再 OCR 收益（`check_card_num`）。**
- **每张通过剪枝的候选都点开一次**再读收益——不是「先判六星再点」。剪枝
  （`maxed_card_classes` / `confirmed_highest_stars`）只在「同类型更高星已被点开确认过」之后
  才生效，减少重复点击。

---

## 8. 收益判断完整链路

```
click(C_SELECT_CARD)                 # C_SELECT_CARD.roi_front 被设为该卡 tier 图标的 match bbox
   ↓  time.sleep(2)                   # 固定等「结界卡详情侧栏加载」，无 semantic 判定（R-U4）
check_card_num():
   self.screenshot()                  # 新截图
   raw_text = O_CARD_NUM.ocr(image)   # RuleOcr(roi=(800,421,150,33), mode="Single", method="Default")
                                      #   Single.ocr_single → str；无结果 / 失败 → "" （不是 0、不是 None）
   卡种判定（关键字）:
     '体' / 'カ' / '力' in raw_text  → '斗鱼'   （斗鱼给体力/AP）
     '勾' / '玉'      in raw_text    → '太鼓'   （太鼓给勾玉/jade）
     否则 → logger.warning('结界卡类型识别失败')；return ('unknown', 0)
   数值提取: re.sub(r'[^\d+]','', raw_text) → re.search(r'\d+') → int()（异常 → 0）
   value <= 0 → self.push_notify(f'数值异常...'); return (card_type, 0)
   return (card_type, value)
```

比较与去向（`_current_select_best`）：

```
(card_type, card_value) = check_card_num()
card_type == 'unknown' or card_value <= 0 or card_type not in {'斗鱼','太鼓'}
    → logger('⏭️ 跳过无效卡'); continue        # ★OCR 失败 / 0 值 → 跳过该卡（不计入 best/last，不当 0 比较）
更新 ap_max_num / jade_max_num（取 max，仅日志用途）
更新 utilize_last_* ；按 _card_rank 更新 utilize_best_*
_reaches_reward_threshold(card_type, card_value):
    threshold = taiko_reward_threshold (太鼓) / fish_reward_threshold (斗鱼) / None
    threshold is None or card_value < threshold → False
    且 card_type 符合 rule → True → return True（停止浏览）
```

| 问题 | 事实 |
|---|---|
| OCR 方法 | `O_CARD_NUM` `mode="Single"`, `method="Default"`；`Single.ocr_single` 返回 str |
| OCR ROI | 固定 `(800,421,150,33)`（详情侧栏右侧，**不随卡变**） |
| 返回值格式 | `check_card_num` → `(str card_type, int value)`；`card_type ∈ {'斗鱼','太鼓','unknown'}` |
| 失败返回 | OCR 空串 → `('unknown', 0)`；数值解析失败 → `(card_type, 0)` + `push_notify` |
| 是否 retry | **否**。`check_card_num` 内无循环、无重试；每次调用只 1 次 `screenshot` + 1 次 OCR |
| 阈值配置字段 | `UtilizeConfig.taiko_reward_threshold`（默认 76）/ `fish_reward_threshold`（默认 151），`ge=1` |
| 是否区分体力/勾玉/金币 | 只区分「体力→斗鱼」「勾玉→太鼓」两类；无金币等其它收益概念 |
| 是否只接受斗鱼 / 太鼓 | 是。`RESOURCE_CONFIG` 只有 `'斗鱼'` / `'太鼓'`；其它类型的卡在 `find_everyone` 阶段就不在 `order_targets` 里 |
| 同种卡多个收益值如何比较 | `utilize_best_*` 按 `(_card_rank 升序, 同 rank 时 card_value 降序)`；跨类型不比数值只比 rank（斗鱼体力 vs 太鼓勾玉不可比） |
| OCR 失败会不会被当 0 | **不会当「收益 0」参与比较**——直接 `continue` 跳过该卡（但卡已被点开=侧栏已选中它，见 §9 风险） |
| OCR 失败会不会跳过该卡 | 会（`continue`） |

---

## 9. 点击一张卡之后怎么回列表

**关键事实：好友结界卡是「列表 + 详情侧栏」同屏共存，点击一张卡的 tier 图标 = 在侧栏选中它，
列表不翻页、不跳页。** 所以：

| 问题 | 事实 |
|---|---|
| 是否返回原好友列表 | 不需要——列表一直在，点下一张卡的图标即切换选中 |
| 关闭详情还是点下一张 | 直接 `continue` 到 `for (target, _, area) in cards` 的下一个候选，`self.click(C_SELECT_CARD)` 点下一张图标 |
| 是否重新 screenshot | 当前屏所有候选**共用同一次** `find_everyone` 的 `area`（`for` 循环开头 `screenshot` 一次）；`check_card_num` 自己 `screenshot` 一次（只为读侧栏，不重找卡） |
| 是否重新识别列表位置 | 当前屏的候选**不重新识别**——`area` 是循环开始那一帧的 match bbox，直到 `perform_swipe_action` 才换屏。滑动后下一轮 `range` 迭代重新 `find_everyone` |
| 是否保存 index / row / page | **不保存 index / row / page / screen**。只保存 `utilize_best_*`（card_class + value + rank）与 `utilize_last_*`（card_class + value）——**按收益值 / 卡类，不按位置** |
| stale coordinate 风险 | 同屏内低：列表在一屏内不动，`area` 有效。跨屏无：滑动后重新 `find_everyone`。**唯一风险**：若某候选 `check_card_num` OCR 失败被 `continue` 跳过，该卡**已被点开=侧栏当前选中它**，但 `utilize_last_*` 未更新（更新在 `continue` 之后）。若这是扫描最后一次点击且 `utilize_last_* == utilize_best_*` 恰好成立 → `_select_optimal_resource_card` 判「最后点开即最优，直接进结界」→ **实际侧栏选中的是那张 OCR 失败的卡**（`CURRENT FLOW GAP`，见 §12 Gap #7 / Issue Register KU-3） |
| 列表刷新/动画导致索引失效 | 同屏内不会（不用索引）；`_reselect_best_card` 专门为「重进列表后顺序变了」设计——按收益值匹配，位置无关 |

---

## 10. `_current_select_best` / `_select_lazy_resource_card` / `_reselect_best_card` 逐函数

### `_current_select_best() -> bool`（普通模式浏览主体）

- 真实语义：**浏览当前分组整列表，每张通过剪枝的候选点开读收益，记录 `utilize_best_*` /
  `utilize_last_*`，命中 config 阈值立即 `return True`。**
- 返回：`True` = 扫描中命中阈值（当前选中即目标）；`False` = 到底/超时/21 屏跑完（未命中阈值，
  是否有可用卡看 `utilize_best_card_class` / `utilize_current_group_*` 标志）。
- 剪枝：`maxed_card_classes`（某档已点开确认到 `CARD_TIER_INFO` 上限）、`confirmed_highest_stars`
  （某卡种已确认的最高星，低于它的同类型不再点开）——**只减少重复点击，不改「谁先点」**。
- `RESOURCE_CONFIG = {'斗鱼':'ap_max_num', '太鼓':'jade_max_num'}`——`ap_max_num` / `jade_max_num`
  只在扫描内取 max、只用于日志（`📝 第一阶段浏览完成 | 斗鱼:.. 太鼓:..`），不参与选卡决策。

### `_select_lazy_resource_card() -> bool | None`（怠惰模式）

- 真实语义：**选「当前可见的首张符合当前策略的高星卡（≥5 星优先），否则首张符合策略的四星卡」，
  点开即完成——不读收益、不比较、不回选。**
- `lazy_scan_targets` = 固定 6 张 4~6 星 fish/taiko 模板（与 DEFAULT 的 `order_targets` 相同）。
- `_lazy_card_matches_rule`：按 `UtilizeRule` 过滤卡种。
- `high_star_cards = [星级 >= 5]`；`target = high_star[0] if high_star else eligible[0]`——
  **`[0]` 是 `find_everyone` 排序后的第一个，即屏幕最上面那张**。
- 返回：`True` = 选中；`None` = `I_U_EMPTY_CARD` / 连续 `miss > 3` / 21 屏跑完（该组无卡）；
  `False` = **仅** `Timer(120)` 超时。
- 「怠惰」= 省掉「逐张 OCR 收益 + 回选最优」，只要类型对、星够、在屏上即拿——加快单轮、
  降低点击量。**默认 `lazy_mode=False`**（`config.py`）；开了则 `lazy_mode_weight` 默认 1.0
  → `lazy_roll(0~1) < 1.0` 恒真 → 每轮都 lazy。调低 weight 可按概率混用两套。

### `_reselect_best_card(friend) -> bool`（回选兜底）

- 真实语义：**`_current_select_best` 扫完未命中阈值、且「最后点开的 != 记录的最优」时，
  回到列表顶部重走一遍，按收益值把 `utilize_best_*` 那张再选中一次。**
- `_reset_utilize_friend_list(friend)` 重新滚到顶 → `for _ in range(21)` & `Timer(120)`：
  对每张 `tier_info[0] == target_type`（同卡种）**且** `tier_info[2] >= target_value`（档位上限
  够得着目标值）的卡：`click` + `sleep(2)` + `check_card_num()` 校验 `card_value >= target_value`
  → 命中即 `return True`。
- `target_type` / `target_value` 来自 `utilize_best_card_class` / `utilize_best_value`（一个具体
  卡种 + 具体收益）。
- 失败：`miss_count > 3` / `I_U_EMPTY_CARD` / 21 屏 / `Timer(120)` / 刷新列表异常 → `return False`
  → `_select_optimal_resource_card` `return False` → `run_utilize` `return False` →
  `check_utilize_add` while 再转（不记 failure、不切区）。
- **`best`/`reselect` 保存的是 `card_class` + `value` + `rank`，不保存 index / page / 坐标。
  回选靠「类型 + 收益值」匹配，不反向滑动、不依赖位置**——对「首次列表顺序不稳定 / 重进后
  重排」是鲁棒的。风险：目标卡在重进后被排到 `I_U_EMPTY_CARD` 之后 / 21 屏之外 → 找不回 →
  整轮失败。

`current_select` = 「浏览当前分组并保留最优」；`lazy` = 「首张够用即拿」；`reselect` = 「按值回选」；
`best_*` = 「本分组扫描中见过的最优卡（类+值+rank）」；`last_*` = 「最后一次实际点开的卡」；
`candidate` = `find_everyone` 返回的一条 `(image, score, (x,y,w,h))`。

---

## 11. 滑动

| 维度 | `perform_swipe_action`（列表翻页） | `_reset_utilize_friend_list` 里的滚到顶 |
|---|---|---|
| backend | **`self.device.swipe_adb(p1, p2, duration=2)` 直连** | `self.swipe(self.S_U_END, interval=3)` → `BaseTask.swipe` → `self.device.swipe` = `Control.swipe` |
| 起点 | `p1 = (random_int(340,600), random_int(500,565))` | `S_U_END.coord()`（`roi_front=(175,179,26,26)` → `roi_back=(164,518,49,102)`） |
| 终点 | `p2 = (p1.x, p1.y - 416)`（`SWIPE_DISTANCE`，纵向向上拖 = 列表下滚一屏） | 由 `RuleSwipe` 端点（从上区拖到下区 = 列表上滚回顶） |
| distance | 固定 `SWIPE_DISTANCE = 416` px（注释：「改动位移会影响扫描是否漏卡」，**未真机核**） | `RuleSwipe` 决定 |
| duration | `2`（秒；传给 `swipe_adb` 的 `duration` kwarg） | 无 `duration`（`interval=3` 是 `Timer` 门控，不是滑动时长） |
| 滑动后 sleep | `self.device.click_record_clear()` → `time.sleep(2)` | `interval=3` 门控；无额外 sleep |
| 是否重新截图 | 否（下一轮 `for` / `range` 迭代开头 `screenshot`） | 否 |
| 是否等 changed/stable | **否**（纯固定 `sleep(2)`，无「列表真的滚了 / 停稳了」判定） | 否 |
| semantic marker | 无 | 无（靠 `interval` + 后续 `switch_friend_list` 的 `appear(check_image)`） |
| BehaviorTrace | **不进**（`swipe_adb` 绕过 `Control.swipe`；`control.py:189` 注释「v1 不覆盖」） | **进**（走 `Control.swipe` → BehaviorTrace `ACTION`/`swipe`） |
| 清 click record | `self.device.click_record_clear()`（swipe 后立即） | 否 |

> 与旧静态收口一致：`perform_swipe_action` 仍是 `random_int(...)` → `swipe_adb(duration=2)` →
> `click_record_clear()` → `sleep(2)`。只是随机源已从 stdlib `random.randint` 换成公共
> `random_int`（WIP），魔法数已提取为类常量。**本轮不改成 FrameWait。**

---

## 12. 到底判断

**结论：heuristic + 一个弱 semantic marker 的组合，不是强 semantic。**

| 触发 | 是什么 | 语义 |
|---|---|---|
| `appear(I_U_EMPTY_CARD)` | 竖直条带里出现「空卡」图标（`roi_back=(536,164,75,442)`） | **弱 semantic**——「这一屏的好友没有结界卡」。游戏把有卡的好友排在前面，所以出现空卡≈列表有效区结束。但只要当前屏还有卡就先处理完再判 |
| `miss_count > CONSEC_MISS(3)` | 连续 4 屏 `find_everyone` 返回 `None`（当前策略的 4~6 星卡一张都没匹配到） | heuristic——「连续多屏没有目标卡 → 视为该分组扫完」 |
| `range(21)` / `range(MAX_SWIPES + 1)` | 最多滑 20 屏（+初始屏） | 硬迭代上限 |
| `Timer(120)` | 单分组浏览总墙钟上限 120s | 硬时间上限 → `return False` |

- **`miss` 的含义**：`_current_select_best` / `_reselect_best_card` 里 `miss` = `find_everyone`
  返回 `None`（当前策略 tier 图标一张没命中）——**不是「屏幕完全没有任何卡」**（别的卡种 / 更低
  星仍可能在，只是不在 `order_targets` 里）。`_select_lazy_resource_card` 里同理，且额外
  「当前屏有卡但都不符策略 → `miss_count = 0`（仍在有效区）」。
- **可能提前判到底吗**：可能。若当前策略的 4~6 星卡恰好连续 4 屏没出现（但列表里更靠后还有），
  `miss_count > 3` 会提前结束该分组扫描（`CONSEC_MISS=3` 未经真机标定）。
- **可能无限滑吗**：不能。`range(21)` + `Timer(120)` + `miss` + `I_U_EMPTY_CARD` 四重。
- **总上界**：`range(21)` / `Timer(120)` / `CONSEC_MISS(3)` / `I_U_EMPTY_CARD`（`switch_friend_list`
  另有 `Timer(20)`→raise）。

---

## 13. `switch_friend_list`

```
switch_friend_list(friend):
  check_image = I_UTILIZE_FRIEND_GROUP (同区)  /  I_UTILIZE_ZONES_GROUP (跨区)
  timer_click = Timer(1).start()
  timeout = Timer(SWITCH_FRIEND_LIST_TIMEOUT = 20).start()
  while 1:
    self.screenshot()
    if appear(check_image): break                         # ★ 唯一「切换成功」判据
    if timeout.reached(): raise GamePageUnknownError(...)  # 20s 未见目标分组图标 → 页面异常
    if timer_click.reached(): timer_click.reset(); self.device.click(check_image.coord())
  if friend == DIFFERENT_SERVER: time.sleep(1)
  time.sleep(0.5)
```

- 签名 `-> None`（WIP 从谎报的 `-> bool` 改来）。
- 有 timeout（`Timer(20)` → `raise GamePageUnknownError`）——WIP 新增，防「图标一直识别不到就
  无限点」。异常在两个调用点接住：`_reset_utilize_friend_list`（经 `run_utilize` / `_reselect_best_card`
  的 try）。
- 切换后「等待页面确认」= `appear(check_image)`；跨区额外 `sleep(1)`，统一 `sleep(0.5)`
  （切分组动画 settle，无独立判定，旧收口 §7 标为「sleep 可能可删」）。
- `_reset_utilize_friend_list(friend)`：同区 = `switch(SAME)` → `swipe(S_U_END, interval=3)` →
  `switch(DIFFERENT)` → `switch(SAME)`；跨区 = `switch(DIFFERENT)` → `swipe(S_U_END)` →
  `switch(SAME)` → `switch(DIFFERENT)`（注释：「跨区必须切两次否则结界卡不会刷新到顶部」）。
  即每次进一个分组前都做 2~3 次分组切换 + 1 次滚到顶。

---

## 14. `check_utilize_add`

- 业务目的：**蹭卡主循环**——反复「进育成页 → 判断是否已有寄养卡 → 没有就 `run_utilize` 选卡
  寄养 → 回育成页再看」，直到蹭上 / 5 轮 / terminal failure。
- 在 `run()` 里的位置：`goto_page(page_guild_realm)` 之后、`check_max_lv` 之前，仅当
  `con.utilize_enable`。
- `return True` 表示：**「本轮蹭卡阶段已结束、`next_run` 已设好、`run()` 可以继续做后续维护
  （满级替换 / 收菜 / 收盒子 / 收寮资源）」**——**不表示「蹭卡成功」**。三条 True 出口：
  1. `utilize_add_count >= 5`（5 轮没搞定）→ `set_next_run(now+5min)` → `return True`
  2. `not appear(I_UTILIZE_ADD)`（已经有寄养卡）→ 读剩余时间 → `set_next_run(now+remaining)` →
     `return True`（**唯一「真的蹭上了」**）
  3. （无——`run_utilize` 返回后不直接 return True，靠下一轮 while 从出口 2 退出）
- `return False` 表示：`utilize_terminal_failure`（`_record_utilize_failure` 累计 3 次 /
  `_finish_low_value_utilize` / `switch` 异常升级）→ `run()` 里 `if not check_utilize_add(): return`
  → **`run()` 提前 return，跳过后续所有维护步骤，不 `raise TaskEnd`**（`next_run` 已由失败
  处理设为 +10min / +20min）。
- 最多几轮：`utilize_add_count` 从 0，每轮 +1，`>= 5` 即出口 1。即最多 4 次实际 `run_utilize`
  尝试（第 5 轮开头就 return）。`run_utilize` 成功后会 `utilize_add_count = 0` 重置。
- 为什么循环：一次 `run_utilize` 可能因「选卡失败 / 坑位被抢 / 导航抖动」返回 `False` 但未
  terminal，需要重试；成功后也要再转一圈从出口 2 正式退出并读剩余时间。
- 失败后调用方（`run()`）：`return`（早退，`next_run` 已设）。
- **历史疑点复核**：出口 1 的「5 轮 → `return True`」与 `_record_utilize_failure` / `_finish_low_value_utilize`
  的「`return False`」语义方向相反——出口 1 让 `run()` **继续做维护**并按 +5min 重排；
  失败路径让 `run()` **跳过维护**并按 +10/20min 重排。这**不是 bug**（5 轮没蹭上仍想收菜/收
  资源是合理的），只是「True/False」在这里表达的是「run() 要不要继续」而非「蹭卡成没成」。
  旧收口 §8 / cleanup 批次 1 已记为 deferred「不影响正确性，改动需产品决定」。

---

## 15. `run_utilize` 所有分支

见 §4 图 A 的 `run_utilize` 段。要点：

- **U1~U3 历史状态**：旧收口的 U1（进 growth 页）/ U2（判 `I_UTILIZE_ADD`）/ U3（`goto_page(page_guild_realm_utilize)`）
  现在都在 **`check_utilize_add`** 里（`run_utilize` 之前），不在 `run_utilize` 内。`run_utilize`
  从「已在寄养页、开始选卡」起。
- **`goto_page` 失败**：`check_utilize_add` 里 `if not self.goto_page(page_guild_realm_utilize):
  logger.info('Utilize failed, exit')` —— **只打日志，不 return，继续调 `run_utilize`**（旧收口
  R-U6，本轮仍是 gap）。`run_utilize` 内 `goto_page(page_friend_utilize)` 失败则 catch
  `GamePageUnknownError/GameStuckError` → `_record_utilize_failure`。
- **group 切换怎么发生**：`for target_friend in (friend, fallback_friend)` + 每组开头
  `_reset_utilize_friend_list(target_friend)`（内含 2~3 次 `switch_friend_list`）。
- **找到目标卡后如何进入寄养**：`_select_*` 返回 `True` → `break` → `screenshot` →
  `appear(I_U_ENTER_REALM)` 校验 → `goto_page(page_friend_utilize)` → 判坑位
  （`I_U_ADD_1` / `I_U_ADD_2`）→ `switch_shikigami_class` → `set_shikigami(order, stop_image)`。
- **寄养成功的 Verify**：见 §16。
- **Task 何时返回 / `TaskEnd`**：`run_utilize` 返回 `True`（寄养 API 走完）/ `False`
  （失败或低价值）。`raise TaskEnd` 只在 `run()` 末尾（`goto_page(page_main)` 之后）；
  terminal failure 时 `run()` 直接 `return`（不 `raise TaskEnd`）。

---

## 16. 寄养成功 Verify

**当前有真实 verify，两层：**

### 层 1（即时，在 `set_shikigami` 内，委托 `ReplaceShikigami`）

```
State:  好友寄养页，右侧有空坑位（stop_image = I_U_ADD_1 或 I_U_ADD_2 可见）
Action: while 1（Timer(120) → raise GameStuckError）:
          screenshot
          appear_then_click(I_U_CONFIRM_SMALL) → continue
          not appear(stop_image) → break                    # ★ Verify
          not clicked → click(C_SHIKIGAMI_LEFT_<order>) / click(C_SHIKIGAMI_LEFT_6) → clicked=True
          appear_then_click(I_U_CIRCLE_ALTERNATE) ...
ExpectedState: 空坑位按钮消失 = 式神已放进寄养位
Verify: not appear(stop_image)
Failure: Timer(120) → GameStuckError → run_utilize catch → _record_utilize_failure('式神寄养失败')
```

### 层 2（下一轮，在 `check_utilize_add` 主循环）

```
run_utilize 返回 True（乐观）→ check_utilize_add: goto_page(page_guild_realm_growth); screenshot()
not appear(I_UTILIZE_ADD)  →  育成页「加寄养卡」按钮已消失 = 确实已有寄养卡
  → O_UTILIZE_RES_TIME.ocr() 读到剩余寄养时间 → set_next_run(now + remaining) → return True   # ★ 权威闭环
appear(I_UTILIZE_ADD) 仍在 → 寄养没真的生效 → while 再转一轮（最多到 utilize_add_count >= 5）
```

即：`run_utilize` 的 `return True` 是**乐观**的（式神点进去了）；**权威成功判据是下一轮
`check_utilize_add` 看到 `not appear(I_UTILIZE_ADD)` 并成功读到 `O_UTILIZE_RES_TIME`**。
比 `KekkaiActivation.harvest_card`（8 连点无验证）强很多。

---

## 17. Failure / Recovery

| 场景 | 当前处理 |
|---|---|
| **找不到卡（当前分组无当前策略 4 星+）** | `_current_select_best` / `_select_lazy_*` `return None` → `run_utilize` for 循环进入 `fallback` 分组；两组都 `None` → `_finish_low_value_utilize()`（`set_next_run` **+20min**，`utilize_terminal_failure=True`）→ `run()` 早退 |
| **OCR 失败（单张卡）** | `check_card_num` → `('unknown', 0)` → `_current_select_best` `continue` 跳过该卡（不计 miss、不记 best/last） |
| **OCR 全失败（有 4 星+ 但一张都读不出收益）** | `_current_select_best` `return False` + `utilize_current_group_has_eligible_card=True` → `_select_optimal_resource_card` `return False` → `run_utilize` `return False`（不切区、不记 failure）→ `check_utilize_add` while 再转 |
| **列表到底 / 21 屏 / Timer(120)** | `_current_select_best` `scan_completed=True; return False`；`_reselect_best_card` `return False` |
| **页面切换失败（`switch_friend_list` 20s 超时）** | `raise GamePageUnknownError` → `_reset_utilize_friend_list` 冒泡 → `run_utilize` catch → `_record_utilize_failure('刷新好友列表失败')`（+1 failure，3 次 → terminal +10min）；`_reselect_best_card` 里 → `return False` |
| **`goto_page(page_guild_realm_utilize)` 失败** | 只 `logger.info('Utilize failed, exit')`，**不 return**，继续 `run_utilize`（R-U6，未修） |
| **`goto_page(page_friend_utilize)` 失败** | catch `GamePageUnknownError/GameStuckError` → `_record_utilize_failure('进入好友结界失败')` |
| **寄养按钮 / 进入结界按钮没识别到（`not appear(I_U_ENTER_REALM)`）** | `_record_utilize_failure('未识别到进入结界按钮')` |
| **寄养位满 / 没坑位（`stop_image is None`）** | `save_image('没有坑位')` + `_record_utilize_failure('目标结界已经没有可用坑位')` |
| **式神寄养失败（`set_shikigami` GameStuckError）** | catch → `_record_utilize_failure('式神寄养失败')` |
| **两个分组都没有符合条件卡** | `_finish_low_value_utilize()`（+20min，terminal） |
| **连续 3 次「已选中目标后」失败** | `_record_utilize_failure` 第 3 次 → `set_next_run(finish=True, server=False, now+10min)` + `utilize_terminal_failure=True` |
| **5 轮 `check_utilize_add` 没搞定** | `push_notify` + `set_next_run(now+5min)` + `return True`（run() 继续做维护） |
| **回选失败（`_reselect_best_card` return False）** | `_select_optimal_resource_card` `return False` → `run_utilize` `return False` → `check_utilize_add` while 再转（不记 failure） |

- `utilize_failed_count`：`_record_utilize_failure` 每次 +1，`< 3` 返回 `False`（软失败），`== 3`
  → terminal（+10min，`utilize_terminal_failure=True`）。跨 `check_utilize_add` 轮次累计，
  `run_utilize` 成功时 `= 0` 重置。
- 无退避曲线 / 无 backoff 递增——固定 5min（5 轮）/ 10min（3 次选中后失败）/ 20min（两组低价值）。

---

## 18. Loop / Timer / Sleep / range / while / wait Inventory

| Function | Loop / Wait | Bound | Exit Condition | Failure |
|---|---|---|---|---|
| `check_utilize_add` | `while 1` | **bounded** | `utilize_add_count >= 5` → `return True`；`not appear(I_UTILIZE_ADD)` → `return True`；`utilize_terminal_failure` → `return False` | 无（内层负责） |
| `run_utilize` | `for _ in enumerate((friend, fallback))` | **bounded**（恰 2） | 选中 `break` / `False` `return` / 两组 `None` → `_finish_low_value_utilize` | `_record_utilize_failure` / `_finish_low_value_utilize` |
| `_current_select_best` | `for swipe_count in range(MAX_SWIPES+1=21)` + `Timer(TIMEOUT=120)` | **double-bounded** + `CONSEC_MISS=3` + `I_U_EMPTY_CARD` | 命中阈值 `return True`；到底/超时/跑完 `return False` | `return False` |
| `_current_select_best` 内 `for (target,_,area) in cards` | 一屏候选数 | **bounded**（命中数有限） | 遍历完 | `continue` 跳过无效卡 |
| `_select_lazy_resource_card` | `for swipe_count in range(max_swipes+1=21)` + `Timer(120)` | **double-bounded** + `consecutive_miss_limit=3` + `I_U_EMPTY_CARD` | 选中 `return True`；跑完 `return None` | `Timer` 超时 → `return False` |
| `_reselect_best_card` | `for _ in range(21)` + `Timer(120)` | **double-bounded** + `miss_count>3` + `I_U_EMPTY_CARD` | 找回 `return True` | `return False` |
| `switch_friend_list` | `while 1` | **timeout-bounded** `Timer(20)` | `appear(check_image)` → `break` | `Timer(20)` → `raise GamePageUnknownError` |
| `_reset_utilize_friend_list` | 无循环（顺序调用 `switch_friend_list` ×2~3 + `swipe(S_U_END, interval=3)`） | — | — | `switch_friend_list` 异常冒泡 |
| `check_and_get_guild_rewards` | `while True` + `Timer(2)` 进度计时器 | **state-bounded**（收到奖励 `reset`，2s 无奖励 `return False`） | `timer_check.reached()` / `any(harvest) and not appear(I_UI_REWARD)` | `return False` |
| `guild_lottery` | 2× `while not timeout_timer.reached()`（`Timer(4)`，抽奖后 `reset`） | **timeout-bounded** | timer reached | — |
| `receive_guild_assets` | `for i in range(1, max_tries+1)` | **bounded** | 一次没收到即 `break` | — |
| `check_box_ap_or_exp._harvest_ap_box` | `while True` + `Timer(6)` | **timeout-bounded** | `appear(I_UI_REWARD)` / `Timer(6)` | — |
| `check_box_ap_or_exp._harvest_exp_jug` | `while True` + `Timer(12)` + `max_tries=random_int(2,3)` | **double-bounded** | page / confirm-cancel / `cur==total` / timer / `max_tries<=0` | — |
| `set_shikigami`（组件） | `while 1` + `time.time()` `TIMEOUT_SEC=120` | **timeout-bounded** | `not appear(stop_image)` → `break` | `Timer(120)` → `raise GameStuckError` |
| `goto_page`（组件） | `Timer(30)` | **timeout-bounded** | 到达目标页 | `GamePageUnknownError` |

**固定 / 随机 sleep（本轮不替换 FrameWait）**：

| 位置 | 值 | 真实用途 |
|---|---|---|
| `check_utilize_add` 每轮开头 | `time.sleep(0.5)` | 业务 pacing——「至少看一眼时间」前的缓一下 |
| `_current_select_best` / `_select_lazy_*` / `_reselect_best_card` 每次 `click(C_SELECT_CARD)` 后 | `time.sleep(2)` | 等「结界卡详情侧栏加载」（无 semantic 判定，R-U4） |
| `perform_swipe_action` 末尾 | `time.sleep(2)` | 等「列表滚动停稳」（无 changed/stable 判定，R-U5） |
| `switch_friend_list` 末尾 | `time.sleep(0.5)`（跨区额外 `sleep(1)`） | 切分组动画 settle |
| `check_and_get_guild_rewards` | `time.sleep(1)`（收资金 / 收体力后） | 「看到获得奖励」动画 |
| `run` 的 `lazy_roll` | `random_delay(0.0, 1.0)` | **不是等待**——当 `[0,1]` 随机浮点用于 lazy 概率判定（既有瑕疵，NOT_REPRODUCED，见 AI_CONTEXT §4.36） |

**random_delay / random_int**：`run` `random_delay(0.0,1.0)`（lazy 概率）；`_harvest_exp_jug`
`random_int(2,3)`（重试次数）；`perform_swipe_action` `random_int(340,600)` / `random_int(500,565)`
（swipe 起点）。全部来自公共 `module.base.utils.random`（WIP 已从 stdlib `random` 迁完，
该文件已无普通 `random`）。

---

## 19. BehaviorTrace 覆盖

| 动作 | 路径 | 是否进 BehaviorTrace |
|---|---|---|
| `self.click(C_SELECT_CARD)`（选卡） | `BaseTask.click` → `C_SELECT_CARD.coord()` → `self.device.click(x,y,control_name='select_card')` → `Control.click` | **是**（`Control.click` → `ACTION`/`click`，最终坐标 + `target='select_card'`） |
| `switch_friend_list` 里 `self.device.click(check_image.coord())` | `Control.click`（`control_name` = `I_UTILIZE_FRIEND_GROUP` / `I_UTILIZE_ZONES_GROUP` 的 name） | **是** |
| 各 `appear_then_click` / `ui_*` | `Control.click` | **是** |
| `_reset_utilize_friend_list` 的 `self.swipe(S_U_END, interval=3)` | `BaseTask.swipe` → `self.device.swipe` = `Control.swipe` | **是**（`ACTION`/`swipe`） |
| **`perform_swipe_action` 的 `self.device.swipe_adb(p1, p2, duration=2)`（列表翻页）** | `Adb.swipe_adb` **直连**，绕过 `Control.swipe` | **否**（`control.py:189` 注释「v1 不覆盖」；旧收口 R-A4 / ROADMAP T5-1 已记） |

**结论：click / `S_U_END` 滚到顶 有 trace；列表翻页 `perform_swipe_action` 没 trace。**
本轮不改。

---

## 20. GeneralBattle V3 关系

**无直接影响。**

- `KekkaiUtilize.ScriptTask` MRO：`ScriptTask → GameUi → ChessBattleNavigationMixin →
  ReplaceShikigami → BaseTask → GlobalGameAssets → CostumeBase → GameUiAssets →
  ReplaceShikigamiAssets → KekkaiUtilizeAssets → object`。**不含 `GeneralBattle`。**
- `grep -rn "GeneralBattle\|run_general_battle\|_handle_result\|_handle_reward\|Settlement\|C_RANDOM"
  tasks/KekkaiUtilize/` → **零命中**。
- 好友寄养不打战斗、不进结算页。

> GeneralBattle V3（SETTLEMENT CONTRACT V3）与 KekkaiUtilize 好友寄养核心流程没有任何调用 /
> 继承关系。本轮重做蹭卡流程属于独立业务状态机调整。

---

## 21. 用户目标流程（图 B）

```
进入好友结界卡选择页（好友寄养页）
  ↓
优先切到【跨区】                                     # 不看配置默认，跨区固定优先
  ↓
_reset_utilize_friend_list(跨区)（滚到顶）
  ↓
┌─────────────── 每屏循环（bounded：range + Timer + miss + I_U_EMPTY_CARD）───────────────┐
│  screenshot                                                                              │
│  find_everyone（当前策略 4~6 星卡）                                                        │
│  当前屏候选按【星级降序】排序（六星在前）          # 目标：优先检查六星                     │
│  for 候选 in 排序后候选:                                                                  │
│     click 该卡（选中，侧栏刷新）                                                           │
│     等详情稳定（未来：semantic wait，本轮不实现）                                          │
│     check_card_num() 读【实际收益】                                                       │
│     收益满足目标（>= 阈值 且 卡种符合 rule）?                                              │
│        YES → 直接进入寄养（当前选中即目标，不再扫、不回选）                                │
│        NO  → 继续检查当前屏下一个候选（回列表 = 点下一张图标）                             │
│  当前屏候选全不满足 → perform_swipe_action 向下滑                                          │
│  I_U_EMPTY_CARD / 连续 miss / range / Timer → 跨区列表【真正到底】                         │
└──────────────────────────────────────────────────────────────────────────────────────────┘
  ↓
跨区没有符合条件的卡
  ↓
切换【同区】→ _reset_utilize_friend_list(同区)（滚到顶）
  ↓
重复【完全相同】的每屏循环
  ↓
找到 → 寄养（switch_shikigami_class + set_shikigami，verify = stop_image 消失）
没有 → 结束本轮 / 进入既有 fallback（_finish_low_value_utilize +20min / _record_utilize_failure）

关键原则：
① 不假设首次进入的好友列表已稳定排序
② 不假设收益由高到低排列
③ 不因当前屏第一张六星不满足就跳过同屏其它六星
④ 优先看六星，但卡种 / 收益条件仍按配置
⑤ 找到满足条件即可立即寄养，不要求先扫全找「理论最优」
⑥ 跨区优先
⑦ 跨区到底仍没有，才切同区
⑧ 同区同样扫到底
⑨ 不为记好友身份引入好友名 OCR
⑩ 滑动后页面稳定 / 详情加载 / 寄养成功 verify 后续按状态驱动原则设计
```

---

## 22. Gap Matrix

| Target Requirement | Current Behavior | Status | Gap | Source |
|---|---|---|---|---|
| **跨区优先** | 顺序 = `config.select_friend_list`，默认 `SAME_SERVER`（同区）先 | **当前逻辑相反（默认）** | 改默认为 `DIFFERENT_SERVER`，或 `run_utilize` 硬编码「跨区 → 同区」 | `run_utilize:525`；`config.py:31` |
| **六星优先（同屏内先查六星）** | `find_everyone` 按屏幕 y 升序返回；`order_cards` 只用于 `_card_rank`，不影响点击顺序；剪枝仅在「更高星已确认」后生效 | **未实现** | `_current_select_best` 遍历 `cards` 前按 `CARD_TIER_INFO[..][1]`（星级）降序排序 | `image_grid.py:54`；`_current_select_best:910` |
| **当前屏多六星逐个检查** | `for (target,_,area) in cards` 遍历当前屏**所有**通过剪枝的候选 | **已实现** | — | `_current_select_best:910-1002` |
| **点击后读实际收益** | `click(C_SELECT_CARD)` → `sleep(2)` → `check_card_num()`（OCR `O_CARD_NUM`） | **已实现** | — | `_current_select_best:939-944` |
| **满足立即寄养** | `_reaches_reward_threshold` 命中 → `return True` 立即停并进结界；但**默认阈值 = 六星满值** → 实际总走「扫全 + `_reselect_best_card` 回选」 | **部分实现** | 默认阈值改为「可接受收益」而非「理论最高」；并让「命中阈值 = 直接寄养」成为主路径、弱化 `_reselect_best_card`（或仅在「阈值命中失败且已扫完」才回选） | `_reaches_reward_threshold`；`_select_optimal_resource_card:785-802`；`config.py:34-35` |
| **不依赖收益排序** | `_current_select_best` 逐张点开读收益、不假定顺序；`_reselect_best_card` 显式「按收益值而非位置匹配」 | **已实现** | — | `_reselect_best_card` docstring/body |
| **不依赖首次列表稳定排序** | `_reselect_best_card` 按值匹配对重排鲁棒；但 OCR 失败的最后一张会残留「侧栏已选中它」而 `utilize_last_*` 未更新 → `already_selected` 误判可能带错卡进结界 | **部分实现** | `_current_select_best` OCR 失败 `continue` 前也要清 / 更新 `utilize_last_*` 为「无效」，或进结界前对当前侧栏选中卡再 `check_card_num` 校验一次 | `_current_select_best:947-949` vs `:982-983`；`_select_optimal_resource_card:788-795` |
| **当前屏检查完再滑** | `for` 遍历完当前屏 `cards` 才 `perform_swipe_action()` | **已实现** | — | `_current_select_best:1004-1009` |
| **跨区到底后切同区** | 第一分组 `_select_*` 返回 `None` → for 循环进 `fallback` 分组 | **已实现**（顺序取决于配置，见「跨区优先」行） | 同「跨区优先」——把 config 默认 / 硬编码改成跨区先 | `run_utilize:525-552` |
| **同区扫到底** | 同一 `_current_select_best` / `_select_lazy_*`（`range(21)` + `Timer(120)` + `CONSEC_MISS=3` + `I_U_EMPTY_CARD`） | **已实现** | `CONSEC_MISS=3` / `SWIPE_DISTANCE=416` 未真机标定 → 可能提前判到底 / 漏卡（Level C） | `_current_select_best:862-864` |
| **不依赖好友名 OCR** | 全模块无好友名识别 / 无控件树 / 无好友身份；扫描 = 卡种星级模板 + 固定 ROI 收益 OCR | **已实现** | — | 全模块 |
| **bounded loop** | 每个循环 `range` + `Timer(120)` + miss-count 多重界；`switch_friend_list` `while 1` 由 `Timer(20)` → raise 收敛 | **已实现** | — | §18 表 |
| **fresh screenshot** | 每轮扫描开头 `self.screenshot()`；`check_card_num` 自己 `screenshot()` | **已实现** | — | `_current_select_best:884`；`check_card_num:1040` |
| **detail load verify** | `click(C_SELECT_CARD)` 后固定 `time.sleep(2)`，无「侧栏详情已加载」判定 → 加载慢时 OCR 读空 → 误跳过 | **未实现** | 换成等某详情标识出现（需 Level C 确认标识）；本轮不接 FrameWait | `_current_select_best:941`（×3 处） |
| **swipe stable verify** | `perform_swipe_action` `swipe_adb` → `sleep(2)`，无「列表真滚了 / 停稳」判定；`SWIPE_DISTANCE=416` 未核 | **未实现** | FrameState / changed-stable（Level C，本轮禁止接 FrameWait） | `perform_swipe_action:1032-1036` |
| **utilize success verify** | 层 1：`set_shikigami` 内 `not appear(I_U_ADD_1/2)`（坑位填）+ `Timer(120)`→GameStuckError；层 2：下一轮 `check_utilize_add` `not appear(I_UTILIZE_ADD)` + 读 `O_UTILIZE_RES_TIME` | **部分实现**（有真实 verify，但 `run_utilize` return True 是乐观的，权威闭环在下一轮） | 可选：`run_utilize` 成功前在寄养页直接确认坑位已填 + 读到寄养时间，再 return True | `replace_shikigami.py:109`；`check_utilize_add:149-171` |

---

## 23. 哪些现有代码值得保留

- **卡种 / 星级识别**：`order_targets` / `order_cards` / `lazy_scan_targets` / `CardClass` /
  `target_to_card_class` / `CARD_TIER_INFO`（档位上限单调，回选剪枝正确性前提）——完整覆盖
  4~6 星 fish/taiko，模板匹配可靠。
- **收益 OCR**：`check_card_num`（关键字判卡种 + 正则取数 + `('unknown',0)` 兜底 + `value<=0`
  push_notify）——逻辑清晰，返回 `(str, int)` 稳定。
- **收益阈值机制**：`_reward_threshold` / `_reaches_reward_threshold` / `taiko_reward_threshold` /
  `fish_reward_threshold`（`ge=1` 校验）+ `_card_rank`（跨类型不比数值只比 rank）——本身对，
  只是默认值取向需调（见 Gap #5）。
- **跨区 / 同区双分组扫描**：`run_utilize` 的 `for (friend, fallback)` + `_reset_utilize_friend_list`
  （跨区切两次刷新到顶的经验注释）——结构对，只是「谁先」是配置默认问题。
- **到底 / miss 检测**：`I_U_EMPTY_CARD` + `CONSEC_MISS` + `range` + `Timer(120)` 多重界——
  bounded 完备，只需真机标定 `CONSEC_MISS` / `SWIPE_DISTANCE`。
- **failure backoff / recovery 分层**：`_record_utilize_failure`（3 次 → +10min terminal）/
  `_finish_low_value_utilize`（+20min）/ 5 轮 → +5min / `utilize_terminal_failure` 标志 /
  异常在调用点接住不升级重启——分层清楚。
- **剩余时间兜底**：`UTILIZE_RES_TIME_FALLBACK` / `UTILIZE_RES_TIME_MAX` + 「`next_run` 严格
  晚于当前时刻」不变量（`tests/test_kekkai_utilize_threshold.py` 已锁）——防热循环，值得留。
- **`switch_friend_list` 20s timeout + `-> None` 签名**——防无限点击。
- **寄养 verify（两层）**：`set_shikigami` 的 `stop_image` 消失 + 下一轮 `not appear(I_UTILIZE_ADD)`。
- **随机源统一**：`random_int` / `random_delay`（公共 `SystemRandom`）——已迁完，别退回。

---

## 24. 哪些现有代码应在下一轮重写（只列候选，不修改）

| 候选 | 原因 | 触及范围 |
|---|---|---|
| `run_utilize` 分组顺序 | 「跨区优先」需求 → 改 config 默认 `SelectFriendList` 或 `run_utilize` 内固定顺序（保留 config 作「关掉某一区」用途待定） | `run_utilize` 头部 + `config.py` 默认值 |
| `_current_select_best` 的候选遍历 | 同屏内先按星级降序排序再遍历（「六星优先」）；OCR 失败 `continue` 前同步 `utilize_last_*`（防带错卡） | `_current_select_best` for 循环 |
| `_select_optimal_resource_card` + `_reselect_best_card` | 若「命中阈值即寄养」成为主路径、默认阈值调低，则 `_reselect_best_card`「全列表回选理论最优」的必要性下降——考虑：仅当「扫完整个分组都没命中阈值、但有 eligible 卡」时才回选 best；或直接删回选、改成「没命中阈值 = 该组无满足卡，继续 fallback」 | `_select_optimal_resource_card` 后半 + `_reselect_best_card` 存废 |
| `config.py` 默认阈值 | `taiko_reward_threshold=76` / `fish_reward_threshold=151`（六星满值）→ 若目标是「够好就停」，默认应是用户可接受收益（需产品定值，Level C 参考真实收益分布） | `config.py:34-35`（**本轮禁止改阈值**，只记录） |
| detail load / swipe stable 的 `sleep(2)` | 换 semantic wait / FrameState（Level C；本轮禁止接 FrameWait） | `_current_select_best` / `_reselect_best_card` / `_select_lazy_*` / `perform_swipe_action` |
| `check_utilize_add` 出口 1 的 `return True` | 与失败路径 `return False` 语义方向相反（run() 要不要继续维护）——可留注释澄清，或引入第三态；改动影响 `run()` 分支，需产品决定（deferred） | `check_utilize_add` + `run()` |
| `R-U6`：`goto_page(page_guild_realm_utilize)` 失败不 return —— **已于 2026-09-14 实施（U3），并修正 root cause** | **真实 root cause（源码复核后修正）**：`goto_page()` 成功固定 `return True`、失败**抛** `GamePageUnknownError` / `GameStuckError`，**从不返回 False/None**——旧 caller 按 bool-failure 契约理解，`if not goto_page(...)` 分支实际不可达；真实失败以异常向上传播，绕过 KekkaiUtilize 自己的 retry / quiet window / terminal handling。**不是**「异常路径下仍继续执行 `run_utilize` 业务」。**修复**：本地 `try/except (GamePageUnknownError, GameStuckError)` 收敛两种失败信号 → `_schedule_retry` + `utilize_terminal_failure=True` + `return False`（复用既有终态失败出口，不新增调度）。**状态：U3 IMPLEMENTED / Level A/B PASS（`UtilizeNavigationFailureGuardTest` 10 例）/ Level C PENDING** | `check_utilize_add`（详见 `docs/AI_CONTEXT.md` §4.68） |

---

## 25. 推荐的最小重构边界

**下一轮只重写这 3 个函数 + 1 个 config 默认值即可贴近目标流程，无需重写整个 KekkaiUtilize：**

1. **`run_utilize`（头部）** —— 分组优先顺序改为「跨区固定优先」（改 `config.py` 默认
   `select_friend_list = DIFFERENT_SERVER`，或在 `run_utilize` 里忽略 config 顺序、硬编码
   `(DIFFERENT_SERVER, SAME_SERVER)`；config 保留为「是否只扫某一区」）。
2. **`_current_select_best`（for 循环）** —— (a) 遍历 `cards` 前按星级降序排序（同星保持 y 序）
   实现「同屏六星优先」；(b) OCR 失败 `continue` 分支里也把 `utilize_last_card_class/value` 置为
   一个「无效」哨兵，避免 `already_selected` 误判带错卡进结界。
3. **`_select_optimal_resource_card`（后半）+ `_reselect_best_card`** —— 让「命中阈值 →
   直接寄养」成为唯一「选中即进结界」路径；「扫完没命中阈值」时的行为二选一：
   (a) 若仍要「实在没满足就退而求其次选 best」→ 保留 `_reselect_best_card` 但仅在此分支触发；
   (b) 若严格按「找到满足条件才寄养」→ 删 `_reselect_best_card`，「没命中阈值」直接当该分组
   无满足卡（`return None` → fallback）。**(a)/(b) 取舍需产品确认**（用户描述偏 b，但保留 a
   作 fallback 更稳）。
4. **`config.py`** —— `select_friend_list` 默认值（配合 #1）；`taiko/fish_reward_threshold`
   默认值待产品给「可接受收益」（**本轮不改**）。

`check_card_num` / `order_targets` / `CARD_TIER_INFO` / `switch_friend_list` / `_reset_utilize_friend_list` /
`perform_swipe_action` / failure recovery / 寄养 verify / lazy 模式 —— **不动**。

---

## 26. Level C 需要确认什么

1. **首次进入好友结界卡列表的真实排序行为**——用户已口头描述（最近寄养过的好友先出现、
   收益不按高低、点过一圈退出再进星级顺序更稳但收益仍无序）。需真机录屏确认：滑动到底后
   是否稳定、`I_U_EMPTY_CARD` 是否可靠标记有效区结束。
2. **`SWIPE_DISTANCE = 416` / `CONSEC_MISS = 3`**——一屏能显示几张好友卡、416px 是否恰好推进
   一屏不漏不重、连续几屏无目标卡才算真到底。
3. **详情侧栏加载**——`click(C_SELECT_CARD)` 后侧栏 `O_CARD_NUM` 稳定可读需要多久，有没有可作
   semantic wait 的标识（决定能否把 `sleep(2)` 换掉）。
4. **「可接受收益」阈值真实分布**——太鼓 / 斗鱼 4/5/6 星的实际收益范围，用户能接受的下限
   （决定 `taiko/fish_reward_threshold` 新默认值）。
5. **`_reselect_best_card` 回选是否真的会被走到**——默认阈值下满值卡多罕见、回选成功率多少
   （AI_CONTEXT §4.11「未验证」）。
6. **`perform_swipe_action` 的 `swipe_adb` 直连 vs `Control.swipe`**——改成公共滑动是否改变实际
   滚动距离（旧收口 R-A4 / ROADMAP T5-1）。
7. **同屏是否真有多张六星**——决定「同屏六星优先排序」的实际收益（若一屏通常只有 0~1 张
   目标卡，排序意义不大）。

---

## 27. Production Impact

**0。** 本轮纯只读审查——未改 `tasks/KekkaiUtilize/` 任何文件、未改 `KekkaiActivation` /
`GeneralBattle` / `base_task` / 任何生产代码、未改测试、未接 FrameWait、未动 `swipe_adb` /
lazy 概率 / 阈值 / failure backoff / 随机分布 / 任务调度。

---

## 28. Tests

**只读——未新增 / 未修改测试。**

现有覆盖：

- `tests/test_kekkai_utilize_state.py`（23 用例）—— `perform_swipe_action` 参数与调用顺序、
  `check_card_num`(KU) 关键字判类型、循环边界（`check_utilize_add` `>=5` / `run_utilize` 双分组
  无 while / `_current_select_best` `MAX_SWIPES=20`+`range(+1)`+`Timer(120)`+`CONSEC_MISS=3` /
  `_select_lazy_*` / `_reselect_best_card` `range(21)`+`Timer(120)` / `switch_friend_list`
  `Timer(20)`+raise / `check_and_get_guild_rewards` 进度计时器 / `receive_guild_assets` range）、
  三处「等详情」+ post-swipe `sleep(2)`、lazy_roll = `random_delay(0.0,1.0)`、FrameWait 零 token、
  全模块只 1 处 `swipe_adb`、不走 `Control.swipe`。
- `tests/test_kekkai_utilize_threshold.py` —— 默认阈值 = 六星满值（默认行为零变化护栏）、
  阈值边界、三策略下阈值只对本策略类型生效、调低提前触发、`_card_rank` 跨类型用排名、
  不同策略排名不同、`CARD_TIER_INFO` 档位上限单调、config 拒非正值、剩余时间兜底
  （`timedelta(0)` / 负 / 非 timedelta / 超上界 → 兜底；`next_run` 恒晚于当前时刻）、
  `switch_friend_list` timeout 常量为正 + 签名 `-> None`。

**评估**：现有 characterization 已充分锁定当前 WIP 的控制流、边界、参数与阈值语义。本轮不
新增测试（避免干扰大量在途 WIP，且没有「旧 characterization 已明显过时」的情况——两个测试
文件都是随本 WIP 一起写的、当前与源码一致）。下一轮真正重构 `run_utilize` / `_current_select_best` /
`_reselect_best_card` 时，应先补：同屏候选按星级排序后的遍历顺序、OCR 失败不带错卡、
「命中阈值即寄养」为主路径、跨区固定优先 —— 届时同步更新这两个测试文件。

- targeted：未跑（未改）。已知基线 `test_kekkai_utilize_state` 23、`test_kekkai_utilize_threshold` 25。
- full regression：未跑（本轮零代码改动，`docs/AI_CONTEXT.md` §7 基线 759/759 不受影响）。
- compileall：无改动文件。
- diff-check：`tasks/KekkaiUtilize/` 工作树 diff 与审查开始时完全一致（`config.py` `+4` /
  `script_task.py` `+205/-46`，均为既有 WIP）。

---

## 29. Git

- branch：`master`
- HEAD：`2cdf3a0571b0449748aabef259da5cbd2378536c`
- staged：无
- unstaged：`tasks/KekkaiUtilize/script_task.py`、`tasks/KekkaiUtilize/config.py`（既有 2026-08-30
  WIP，本轮未触碰）；以及无关的长期 WIP（见 `docs/AI_CONTEXT.md` §2）
- untracked：`docs/`（本审查新增本文件）等
- 未 commit、未 push、未真机。

---

## 30. 文档同步

- **AI_CONTEXT.md**：已更新 —— §4.x 新增本审查记录 + §9 待办把「KekkaiUtilize 剩余工作 = 真机
  验证回选/超时」细化为「跨区优先默认反了 / 同屏非星级序 / 默认阈值使行为=扫全+回选，最小
  重构 = `run_utilize` 顺序 + `_current_select_best` 排序&防带错卡 + `_reselect_best_card` 存废 +
  config 默认」。
- **DEVELOP_LOG.md**：已追加 —— 「2026-09-03 KekkaiUtilize 蹭卡流程重新审查」条目（PARTIAL、
  三大差异、Gap Matrix 摘要、最小重构边界、production diff = 0）。
- **ROADMAP.md**：已更新 —— 「已完成」新增本审查行；「需要真机验证」区把 KekkaiUtilize 项
  替换为本文 §26 的 7 条 Level C 待确认；把「KekkaiUtilize 蹭卡策略均已实现」的旧结论修正为
  「机制在、但跨区优先默认 / 同屏星级序 / 默认阈值取向 与目标不符，下一轮做 §25 最小重构」。
- **ARCHITECTURE.md**：无需更新 —— KekkaiUtilize 不是分层地图里的公共层，无调用链 / 职责边界
  变化；未形成新架构结构。
- **DECISIONS.md**：无需更新 —— 本轮只审查，未形成 / 未推翻任何长期设计决策。
- **TESTING.md**：无需更新 —— 未改测试分级 / 验证规则 / 真机要求。
