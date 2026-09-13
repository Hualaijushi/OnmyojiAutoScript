# Minitouch 自定义轨迹能力专项审查

> 2026-09-03。**只读源码审查——未改任何代码、未接 KekkaiUtilize、未启动 MuMu、未真机。**
> 目标：确认当前 minitouch 是否已具备执行「自定义多点触摸轨迹（points + per-segment dt）」的
> 能力，为后续 `TouchSwipeModel` 接入定位最小新增接口。
> 事实源：当前工作树源码 > git diff > 六份文档 > 历史总结。
> 源码基准：HEAD `2cdf3a05`。`module/device/method/minitouch.py` 对 HEAD **零 diff**（无 WIP）。

---

## 1. 结论

| 层 | 能否执行自定义多点轨迹 | 说明 |
|---|---|---|
| **协议层**（`Command` / `CommandBuilder` / minitouch socket 协议） | **YES**（已完全具备） | `Command` 逐字支持 minitouch 的 `d/m/u/w/c/r`；`m {contact} {x} {y} {pressure}` 接受任意 x/y、无「x 必须不变」限制；`CommandBuilder` 是通用流式构造器（`.down() .move() .up() .wait(ms) .commit()`），其 docstring 就给出 `down→move→move→up` 的自定义用法示例。`DOWN → (MOVE→COMMIT→WAIT(dt_i))* → WAIT(short) → UP → COMMIT` 今天就能直接表达。|
| **当前执行层**（`swipe_minitouch` / `drag_minitouch` / `_press_and_drag_minitouch`） | **PARTIAL** | 已经在逐点发 MOVE、每个 MOVE 独立采样 `wait(random_int(6,15))`、路径是三次贝塞尔曲线（非直线、非仅端点）；但**路径生成与时序被写死在 `insert_swipe` + 各方法内联的 for 循环里**，没有任何方法接受「调用方传入的点列表 / 逐段 dt 列表」。 |
| **当前公开 swipe API**（`Control.swipe` / `BaseTask.swipe` / `Control.swipe_vector` / `Control.drag`） | **PARTIAL（对「自定义轨迹」= NO）** | 只接受 `(p1, p2, duration)`（+ vector / shake 等派生参数）。`duration` 在 minitouch 后端被忽略（D003 / §4.14）。**没有任何公开方法接受 `[(x, y, dt), ...]`。** |

**一句话**：minitouch 协议层已经足够，`insert_swipe` 生成的贝塞尔轨迹本身已经是「多点 + 逐段
独立 dt + 有曲率」。缺的只是**管线**——一个接受调用方点列表的薄 executor + 一个公开入口。
**不需要动协议层、不需要重写 control layer。**

---

## 2. 完整调用链

```
业务层
  BaseTask.swipe(swipe: RuleSwipe, interval=None)                    tasks/base_task.py:560
    swipe.coord() → (x1, y1, x2, y2)                                 module/atom/swipe.py:27
        RuleSwipe 只提供端点（起点 random_center_point_in_roi(roi_front)、
        终点 random_center_point_in_roi(roi_back)）；trace()/is_*_mode 已随 D006 删除
    self.device.swipe(p1=(x1,y1), p2=(x2,y2), control_name=swipe.name)
  ↓
Control.swipe(p1, p2, duration=(0.1,0.2), control_name='SWIPE', distance_check=True)   module/device/control.py:132
    ensure_int(p1, p2); ensure_time(duration)
    method = self.config.script.device.control_method
    distance_check: p1[0]==p2[0] → p1[0]+=1；p1[1]==p2[1] → p1[1]+=1；|p1-p2|<10 → 丢弃
    self._invalidate_image_batch_cache()
    start = perf_counter()
    if method == 'minitouch':  → self.swipe_minitouch(p1, p2)        # ← duration 不传
    elif 'window_message' / 'uiautomator2'(带 duration) / 'scrcpy' / else=adb(带 duration*2.5)
    elapsed = perf_counter() - start
    logger.info(...)
    get_behavior_trace(config_name).record('ACTION', action='swipe',
        target=control_name, elapsed_ms=round(elapsed*1000))         # ← 只记端点动作，不记每个 MOVE
  ↓
Minitouch.swipe_minitouch(self, p1, p2)     @retry                    module/device/method/minitouch.py:612
    points = insert_swipe(p0=p1, p3=p2, speed=15, min_distance=10)   # 三次贝塞尔，np.random 控制点
    builder = self.minitouch_builder                                 # cached_property → CommandBuilder(self)
    builder.down(*points[0]).commit()                                # d + c，pressure 缺省 100
    self.minitouch_send()
    for point in points[1:]:
        builder.move(*point).commit().wait(random_int(6, 15))        # m + c + w<ms>，每次独立采样 dt
    self.minitouch_send()
    builder.up().commit()                                            # u + c
    self.minitouch_send()
  ↓
CommandBuilder（module/device/method/minitouch.py:214）
    .down(x,y,contact=0,pressure=100)  → convert(x,y)（旋转 + 分辨率缩放）→ Command('d', ...)
    .move(x,y,contact=0,pressure=100)  → convert(x,y) → Command('m', ...)
    .up(contact=0)                     → Command('u', contact)
    .wait(ms=10)                       → Command('w', ms)；self.delay += ms
    .commit()                         → Command('c')
    .to_minitouch()                   → ''.join(cmd.to_minitouch() for cmd in commands)
  ↓
Minitouch.minitouch_send(self)       @Config.when(DEVICE_OVER_HTTP=False)   :516
    content = self.minitouch_builder.to_minitouch()                 # 整批命令拼成一个字符串
    self._minitouch_client.sendall(content.encode('utf-8'))         # 一次 socket 写
    self._minitouch_client.recv(0)
    time.sleep(builder.delay / 1000 + CommandBuilder.DEFAULT_DELAY(0.05))   # 主机也睡「本批 w 总和 + 50ms」
    self.minitouch_builder.clear()
  （DEVICE_OVER_HTTP=True 分支：to_atx_agent() → 逐行 await ws.send(row)，其余同）
  ↓
minitouch server（设备侧，openstf/minitouch 协议）：按 d/m/u，w<ms> 之间自行 sleep
```

**旁路**：`KekkaiUtilize.perform_swipe_action` / `KekkaiActivation.check_card_num` 直接调
`self.device.swipe_adb(...)`，**不经过 `Control.swipe`**（不进 BehaviorTrace、不走 minitouch）。
`Control.drag` 是已确认无主要生产消费者的死路径（`Control.drag` 读的还是
`self.config.script.emulator.control_method`，与 `Control.swipe` 的 `.device.control_method`
不一致——本轮只记录，不改）。真正的生产拖拽是 `tasks/Chess/runtime/press_and_drag.py`。

---

## 3. 当前 swipe 的真实实现

| 维度 | `swipe_minitouch(p1, p2)` | `drag_minitouch(p1, p2, point_random=(-10,-10,10,10))` | `_press_and_drag_minitouch`（Chess） |
|---|---|---|---|
| 点如何生成 | `insert_swipe(p1, p2, speed=15, min_distance=10)` | 端点先 `- random_rectangle_point(point_random)`，再 `insert_swipe(speed=20)` | 端点先 `_randomized_points(point_random)`，再 `insert_swipe(speed=20)` |
| 路径形状 | **三次贝塞尔曲线**（控制点 `p1=2/3·p0+1/3·p3+random_theta()·random_rho(dist·0.1)`，`p2` 对称），`t` 在 sin 曲线上采样（两端密、中间疏），再删掉相邻 <10px 的点 | 同 `swipe_minitouch`（speed=20） | 同上 |
| MOVE 如何生成 | `for point in points[1:]: builder.move(*point).commit().wait(random_int(6,15))` | 同 | `for point in points[1:]: builder.move(*point, pressure=pressure).commit().wait(random_int(6,15))` |
| MOVE 数量 | `segments = max(int(dist/speed)+1, 5)` 起步，经 `min_distance=10` 过滤 + 首点去重后**可变**（≈ `dist/15`，下限 ~5） | ≈ `dist/20` | ≈ `dist/20` |
| 每 MOVE interval | `random_int(6, 15)` —— **每次循环重新调用，逐 MOVE 独立采样**（不是一个共享值） | 同 | 同 |
| duration | **无 duration 形参**；总时长 = Σ(w) ≈ n_moves × 10.5ms（+ 主机 `sleep(Σw/1000 + 0.05)`）。不由任何单独固定值驱动 | 同 | `down` 的按压 = `wait(int(hold_duration*1000))` 由调用方给；moves 段同 |
| 尾部停顿 | **无** | `builder.move(*p2).commit().wait(140)` ×2 后再 `up()`（固定 140ms settle，D002 有意保留） | 同（`move(*p2).wait(140)` ×2） |
| DOWN | `builder.down(*points[0]).commit()` —— pressure 缺省 100 | `builder.down(*points[0]).commit()` —— pressure 缺省 100 | `builder.down(*points[0], pressure=pressure).commit().wait(hold_duration*1000)` |
| MOVE pressure | **不传** → `CommandBuilder.move` 默认 100 | **不传** → 默认 100 | 传 `pressure`（一个值，down 与所有 move 同一个 `_humanized_pressure()`） |
| UP | `builder.up().commit()` → `u {contact}` | 同 | 同 |
| 随机源 | interval `random_int` = `SystemRandom.randint`；`insert_swipe` 控制点 / `t` 分布用 `np.random`（D007 有意保留） | 同 + 端点 jitter `random_rectangle_point`（`module.base.utils`） | 同 |

`click_minitouch(x, y)`：`builder.down(x, y, pressure=self._humanized_pressure()).commit()
.wait(self._humanized_dwell())` → `builder.up().commit()` → `minitouch_send()`。**无任何
`.move()`、无 ±2px 抖动。**
`long_click_minitouch(x, y, duration=1.0)`：`down(pressure=_humanized_pressure()).commit()
.wait(int(duration*1000))` → `up().commit()`。同样无 MOVE。

---

## 4. 已有轨迹能力（可直接复用的类 / 函数）

| 名称 | 位置 | 能力 | 可否直接复用 |
|---|---|---|---|
| `CommandBuilder` | `minitouch.py:214` | 通用流式命令构造器：`down / move / up / wait / commit / reset / clear / to_minitouch / to_atx_agent`。**任意 x/y、任意 dt、任意长度序列。** | **可以直接复用**——`TouchSwipeModel` 的执行层就用它，不用碰 `Command` / 协议。 |
| `Command` | `minitouch.py:144` | 单条 minitouch 命令的序列化（`d/m/u/w/c/r` → socket 字符串 / atx-agent JSON）。 | 直接复用，不需改。 |
| `Minitouch.minitouch_builder` | `minitouch.py:431` | `cached_property` → 已初始化的 `CommandBuilder(self)`（会触发 `minitouch_init` 握手）。 | 直接复用（`swipe_minitouch` / `_press_and_drag_minitouch` 都是这样拿的）。 |
| `Minitouch.minitouch_send` | `minitouch.py:516 / 584` | 把当前 builder 的整批命令发出去（socket 或 ws）+ 主机 sleep(Σw) + clear。两个 `@Config.when(DEVICE_OVER_HTTP=...)` 变体。 | 直接复用。 |
| `insert_swipe(p0, p3, speed, min_distance)` | `minitouch.py:38` | 由起终点生成一条**贝塞尔曲线点列表**（不含 dt）。 | 作为「默认轨迹生成器」可复用；`TouchSwipeModel` 可以选择替代它。 |
| `smooth_path(points, min_distance=30, offset_range=3)` | `minitouch.py:96` | 给一个点列表，沿路径**垂直方向加 `np.random.uniform(-offset_range, offset_range)` 随机偏移**并重新插值。**当前全仓无调用方。** | 现成的「给点列表加 ±横向抖动」工具——可复用或参考。 |
| `_press_and_drag_minitouch(device, p1, p2, hold_duration, point_random)` | `tasks/Chess/runtime/press_and_drag.py:86` | **外部代码直接驱动 `device.minitouch_builder` 执行自定义轨迹的现成先例**：`down(hold)` → `[move(pt).wait(6-15)]` → `move(p2).wait(140)×2` → `up`。 | 作为 executor 的**写法模板**。 |

**没有**：`swipe_path(points)` / `execute_trajectory(...)` / `move_to(...)` / `gesture(...)` /
「接受坐标迭代器 / 点列表」的公开方法 / 低层 touch builder 的公开封装。

---

## 5. 缺失能力（要让 `TouchSwipeModel` 输出 `points + per-segment dt`）

缺的全是**管线 / 封装**，不是协议：

1. **一个接受点列表的公开 API**。当前每个入口（`Control.swipe` / `swipe_vector` / `drag`）都
   在内部由 p1/p2 合成 → `insert_swipe`，没有「路径由外部给」的口子。
2. **一个迭代调用方 `[(x, y, dt), ...]` 的 minitouch executor**。当前
   `for point in points[1:]: builder.move(*point).commit().wait(random_int(6, 15))` 这段是
   写死的，dt 固定 `random_int(6,15)`、路径固定 `insert_swipe` 输出。
3. （可选）**per-segment pressure 透传**：当前 `swipe_minitouch` / `drag_minitouch` 的
   `move()` 不传 pressure（默认 100）。若模型要控压则 executor 需把每段 pressure 传进
   `builder.move(x, y, pressure=...)`。
4. （可选）**「UP 前一个短暂停顿」参数**：当前只有 `drag` / `press_and_drag` 写死 `wait(140)×2`。

**都不需要**改 `Command` / `CommandBuilder` / `minitouch_send` / 握手 / `to_minitouch` /
`to_atx_agent`。

---

## 6. ±X / 曲线支持

| 问题 | 答案 |
|---|---|
| minitouch 协议本身是否允许任意 x/y MOVE 点 | **是**。`Command('m').to_minitouch()` = `f'm {contact} {x} {y} {pressure}\n'`，x/y 无约束；`to_atx_agent` 是归一化 `xP=x/max_x, yP=y/max_y`，同样任意。 |
| 当前代码有没有「x 必须不变」的人为限制 | **没有**。`CommandBuilder.move(x, y)` 原样接收；`convert(x, y)` 只做旋转 + 分辨率缩放，不夹取、不投影到直线。 |
| 当前 swipe helper 是否只生成直线 | **不是**。`insert_swipe` 生成的是**三次贝塞尔曲线**——控制点 `random_theta()·random_rho()` 会在垂直方向上偏，所以当前每条 swipe 本身就有轻微 x 摆动（不是竖直直线）。 |
| 输入自定义 points 能否自然实现左偏 / 右偏 / 轻微曲线 / 尾部小修正 | **能，天然支持**。模型直接产出 `[(x0,y0), (x0-2,y1), (x0-5,y2), (x0-4,y3), (x0+2,y4), ...]`，`CommandBuilder.move` 逐点原样发。另有现成 `smooth_path(points, offset_range=N)` 可给任意点列表叠加 ±横向偏移。 |

---

## 7. 时间控制支持

| 需求 | 能否 | 依据 |
|---|---|---|
| 每段 MOVE 用不同 dt | **能** | `builder.move(x, y).commit().wait(dt_i)`，`dt_i` 每次调用独立；当前 `swipe_minitouch` 已经是逐 MOVE `random_int(6,15)`。 |
| 前段 / 中段 / 尾段速度不同（加速 → 主运动 → 减速） | **能** | 让点列表里 dt 递变（首段大 = 慢起步 / 首段小 = 快起步 …）。`insert_swipe` 的 `t` 分布已经在**空间上**做了两端密中间疏，配上逐段 dt 即可控速。 |
| 尾部 MOVE 间距减小 | **能** | 由模型在点列表里安排（末尾点更密）；`insert_swipe` 的 `ts = sign·|ts|^0.9` + 归一化本身就让末尾更密。 |
| 总 duration 不依赖一个单独固定值 | **能，且当前就是这样** | minitouch 后端**忽略 `Control.swipe` 的 `duration`**（D003 / §4.14）。总时长 = Σ(所有 `w`) + 主机 `sleep(Σw/1000 + 0.05·n_send)`。 |
| UP 前可以有最后一个短暂停顿 | **能** | `builder.move(x, y).commit().wait(short_ms)` 再 `builder.up().commit()`。`drag_minitouch` / `_press_and_drag_minitouch` 已经这么做（`wait(140)×2`）。 |

**唯一限制**：`swipe_minitouch` 把整批命令累计后**一次 `sendall()`**（fire-and-forget），
`w<ms>` 由设备侧 minitouch server 在 MOVE 之间执行。主机不会在轨迹中途观察 / 调整。对
「先生成完整轨迹再执行」的模型无影响；若未来要「边执行边根据画面反馈修正」则做不到（需要
分批 send + 中途截图，超出本轮范围）。

---

## 8. pressure（只确认协议兼容）

- **如何填入**：`Command('d')` / `Command('m')` 的序列化格式**强制带 pressure 字段**
  （`d {contact} {x} {y} {pressure}` / `m {contact} {x} {y} {pressure}`）；`CommandBuilder.down`
  / `.move` 形参 `pressure=100` 缺省。
- **是否每个 MOVE 都必须带 pressure**：协议字符串层面**是**（格式固定），但业务代码可以不显式
  传 → 走默认 100。当前 `swipe_minitouch` / `drag_minitouch` 的 `move()` 就是默认 100；
  `click_minitouch` / `long_click_minitouch` / `_press_and_drag_minitouch` 显式传
  `_humanized_pressure()`（一个值用于整个动作）。
- **MuMu 下**：握手 `^ 10 540 960 0` → `max_pressure = 0` → `minitouch_init` 夹为 1、
  `_humanized_pressure()` 也夹为 1 → `random_int(1, 1) = 1` 恒定。即 **MuMu 下 pressure 只是
  一个合法协议常量（1），不参与任何业务行为**。只有握手返回较大 `max_pressure` 的设备才会有
  变化。
- **本轮不围绕 pressure 新设计随机模型**（符合 §8 要求）。`TouchSwipeModel` 的 executor 若要
  控压，把每段 pressure 传进 `builder.move(x, y, pressure=...)` 即可，无需改协议。

---

## 9. 对现有 minitouch 优化的核验（以当前源码为准）

| 项 | 现状 | 位置 |
|---|---|---|
| 普通点击 `DOWN → WAIT → UP`（无 ±2px MOVE） | ✅ `click_minitouch`：`builder.down(x, y, pressure=self._humanized_pressure()).commit().wait(self._humanized_dwell()); builder.up().commit()`。全程无 `.move()`。 | `minitouch.py:596` |
| dwell 45~130ms 三角分布（众数 65） | ✅ `_humanized_dwell()` = `round(random_triangular(45, 130, 65))`；`random_triangular` 来自 `module.base.utils.random`（`SystemRandom.triangular`）。 | `minitouch.py:428` |
| pressure 上限归一化 | ✅ `_humanized_pressure()` = `random_int(max(1, top // 2), top)`，`top = max_pressure`；`top` 非正整数 → 1。`minitouch_init` 里 `max_pressure <= 0` 也回退 1。 | `minitouch.py:422 / 496` |
| swipe / drag MOVE interval 6~15ms | ✅ `.commit().wait(random_int(6, 15))`，**每个 MOVE 循环内独立调用**（非共享值）。`random_int` = `SystemRandom.randint`。三处：`swipe_minitouch` / `drag_minitouch` / `_press_and_drag_minitouch`。 | `minitouch.py:621 / 638`，`press_and_drag.py:108` |
| SystemRandom（pressure / dwell / interval） | ✅ `from module.base.utils.random import random_int, random_triangular`（模块级 `SystemRandom`）。 | `minitouch.py:17` |
| `insert_swipe` 贝塞尔控制点 / `t` 分布 | ⚠️ 仍用 `np.random`（`random_theta` / `random_rho` / `random_normal_distribution` = `np.mean(np.random.uniform(...))`）——**D007 明确保留**，不为形式统一迁移。 | `minitouch.py:24-36 / 62-72` |
| drag / press_and_drag 尾部 `wait(140) × 2` | ⚠️ 固定 140ms，**D002 / §4.13 有意保留**（落点 settle 时序，非拟人化延迟），不在「6~15ms 逐段随机」范围内。 | `minitouch.py:641-642`，`press_and_drag.py:112-113` |
| `minitouch_send` 尾部 `sleep(delay/1000 + DEFAULT_DELAY)` | ✅ 固定 `DEFAULT_DELAY = 0.05`，D002 明确保留（协议等待）。 | `minitouch.py:522 / 593` |

---

## 10. 推荐接入架构

```
TouchSwipeModel（新，独立模块，纯逻辑、可单测、不 import device）
    (start, end, 曲线/速度/偏移参数) → list[(x, y, dt_ms[, pressure])]   [+ 可选 pre_up_pause_ms]
        ↓
薄 executor（新，~10-15 行）：
    方案 B-1：Minitouch.swipe_minitouch_trajectory(self, points)   @retry
              builder = self.minitouch_builder
              builder.down(*points[0][:2], pressure=points[0].pressure or 缺省).commit(); minitouch_send()
              for (x, y, dt, *rest) in points[1:]:
                  builder.move(x, y, pressure=...).commit().wait(dt)
              minitouch_send()
              (可选) builder.move(*points[-1][:2]).commit().wait(pre_up_pause_ms)
              builder.up().commit(); minitouch_send()
    方案 B-2：自由函数 execute_touch_trajectory(builder, send, points)（任何后端方法都能调）
        ↓
公开入口（新）：
    Control.swipe_trajectory(points, control_name='SWIPE')   —— 首选独立方法，保持 Control.swipe 契约不变
      · method == 'minitouch' → self.swipe_minitouch_trajectory(points)
      · 其它后端：本轮不实现，或退回把 points 端点丢给现有 swipe()
      · 尾部同 Control.swipe：get_behavior_trace().record('ACTION', action='swipe', target=..., elapsed_ms=...)
        （只记端点级动作，不记每个 MOVE —— 延续 D004）
        ↓
CommandBuilder（不改）→ Command（不改）→ minitouch_send（不改）→ socket / ws
```

**方案对比：**

| 方案 | 可测试性 | 耦合度 | 对其它任务影响 | 复用性 | 评价 |
|---|---|---|---|---|---|
| **A**：`TouchSwipeModel` 直接写 minitouch command 字符串 | 差（要 mock socket / 协议） | 高（协议泄漏进模型） | 无（新路径） | 差（锁死 minitouch，换后端要重写模型） | ❌ 协议细节进模型 |
| **B**：`TouchSwipeModel` 只出纯轨迹数据 → executor 执行 | **好**（模型是纯函数，executor ~10 行可 mock builder） | **低**（模型「怎么移动」/ executor「怎么发」清晰分层） | 无（新方法，`Control.swipe` / `BaseTask.swipe` 契约不变） | **好**（模型与后端无关；executor 可按后端各写一个） | ✅ **推荐** |
| **C**：把轨迹生成塞进现有 `swipe()` | 中 | **高**（`swipe()` 被所有任务、所有后端共用，混入模型逻辑污染整个 control layer） | **大**（改 `Control.swipe` 行为 = 全项目滑动行为变） | 中 | ❌ 违反「不为一个模型重写 control layer」 |

**最小新增接口**：`TouchSwipeModel`（新模块）+ `Minitouch.swipe_minitouch_trajectory(points)`
（~10-15 行，`@retry`，写法照抄 `_press_and_drag_minitouch`）+ `Control.swipe_trajectory(points,
control_name)`（分派 + BehaviorTrace 一行）。**协议层、`CommandBuilder`、`minitouch_send`、
`Control.swipe`、`BaseTask.swipe`、`RuleSwipe` 一律不动。**

---

## 11. 后续实现建议（下一阶段最小任务拆分，不修改代码）

1. **`module/device/touch_swipe_model.py`（新）** —— 纯逻辑：给定 `(start, end)` + 形状参数
   （曲率 / 三段速度比 / 尾部密度 / ±x 偏移幅度）产出 `list[(x, y, dt_ms)]`。可单测：点在
   起终点之间单调推进、dt 全为正、总 dt 在合理范围、±x 偏移有界、尾部点更密。**不 import
   device / Config。** 是否内部复用 `insert_swipe` + `smooth_path` 由实现决定。
2. **`Minitouch.swipe_minitouch_trajectory(self, points)`（新，`@retry`）** —— 迭代 `points`：
   `down(points[0]) → [move(x,y,pressure?).commit().wait(dt) for ...] → (可选 move+wait 短停顿)
   → up`，各 `minitouch_send()`。写法对齐 `_press_and_drag_minitouch`。单测用 mock builder /
   mock send 验证命令序列与每段 dt。
3. **`Control.swipe_trajectory(self, points, control_name='SWIPE')`（新）** —— `method ==
   'minitouch'` 分派到 #2；其它后端本轮先不接（或退回端点 `swipe()`）；尾部 `record('ACTION',
   action='swipe', ...)`（端点级，不记 MOVE）。
4. **接入点选择** —— 先只给一个明确受益的调用点走 `swipe_trajectory`（类似 T7 Point opt-in
   的「逐调用点显式接入」），不全局替换 `BaseTask.swipe`。
5. **真机验收（Level C）** —— 新轨迹的实际滚动量 / 落点 / 是否被游戏识别为「滑动」而非
   「点击」（minitouch ≥5px）/ 逐段 dt 在设备侧是否被如实执行 / 与现有 `insert_swipe` 路径的
   行为差异。
6. **不在本阶段** —— `Control.swipe` 增 `path=` kwarg（会动共享契约）；其它后端的 trajectory
   executor；边执行边反馈修正；`insert_swipe` np.random → SystemRandom（D007 独立项）；
   `Control.drag` 死路径清理 / `.device` vs `.emulator` config key 不一致（独立项）。

---

## 12. 关键源码位置索引

| 内容 | 文件:行 |
|---|---|
| `insert_swipe`（贝塞尔轨迹生成） | `module/device/method/minitouch.py:38` |
| `smooth_path`（未使用的垂直偏移平滑） | `module/device/method/minitouch.py:96` |
| `Command`（单命令序列化 `d/m/u/w/c/r`） | `module/device/method/minitouch.py:144` |
| `CommandBuilder`（通用流式构造器） | `module/device/method/minitouch.py:214` |
| `_humanized_pressure` / `_humanized_dwell` | `module/device/method/minitouch.py:422 / 428` |
| `click_minitouch` / `long_click_minitouch` | `module/device/method/minitouch.py:596 / 604` |
| `swipe_minitouch` / `drag_minitouch` | `module/device/method/minitouch.py:612 / 627` |
| `minitouch_send`（socket / ws 两变体） | `module/device/method/minitouch.py:516 / 584` |
| `Control.swipe`（后端分派 + BehaviorTrace） | `module/device/control.py:132` |
| `Control.swipe_vector` / `Control.drag`（死路径） | `module/device/control.py:194 / 222` |
| `BaseTask.swipe`（业务入口） | `tasks/base_task.py:560` |
| `RuleSwipe.coord`（只提供端点，D006） | `module/atom/swipe.py:27` |
| `_press_and_drag_minitouch`（外部驱动 builder 的先例） | `tasks/Chess/runtime/press_and_drag.py:86` |

---

## 文档同步

- **AI_CONTEXT.md**：已更新 —— §8.2「minitouch 待处理项」补一条：minitouch 协议层
  （`Command` / `CommandBuilder`）已确认支持自定义多点轨迹 + per-segment dt + 任意 x/y，
  缺的只是薄 executor + 公开 API（Plan B），详见本专题。
- **DEVELOP_LOG.md**：已追加 —— 「2026-09-03 Minitouch 自定义轨迹能力专项审查」条目
  （纯审查、零代码改动、产出本专题 + Plan B 结论 + 最小接口清单）。
- **ROADMAP.md**：已更新 —— T5-3 / minitouch 相关项补注：可行性已确认，`TouchSwipeModel`
  接入 = Plan B（模型出纯轨迹 → `swipe_minitouch_trajectory` executor → 新 `Control.swipe_trajectory`），
  协议层无需改。
- **ARCHITECTURE.md**：无需更新 —— swipe 调用链已在 §3 记录；本轮未形成新分层 / 新结构，
  只是确认了既有 `CommandBuilder` 的通用性（属实现细节，不是架构变更）。
- **DECISIONS.md**：无需更新 —— 本轮是审查 + 推荐，未形成「已接受」的长期决策；D002
  （稳定性时序）/ D003（`Control.swipe` duration 后端契约）/ D006（`RuleSwipe` 只提供端点）
  / D007（随机源）均未推翻、未新增。`TouchSwipeModel` 真正实施时若形成契约再补 ADR。
- **TESTING.md**：无需更新 —— 未改测试分级 / 验证规则 / 真机要求。
