# AI 项目上下文

> 本文档为**覆写型当前项目状态快照**（最后核对：2026-11-27）。严禁在顶部堆叠 `>` 增量流水；开发流水见 [DEVELOP_LOG.md](DEVELOP_LOG.md)，历史快照与编号详情见 `docs/archive/`。

## 0. 文档体系、归档索引与写入口径（D073）

项目交接文档共 6 份，另加单任务控制卡片 [CURRENT.md](CURRENT.md)，按 **D073** 分三类维护：

| 文件 | 类型 | 职责（负责的项目事实） | 何时更新 |
|---|---|---|---|
| `docs/AI_CONTEXT.md` | 覆写型当前态 | 当前阶段、Git 口径、约束、各模块有效能力速览、非阻断限制 | 模块现状、约束或限制变化时**覆写对应行/段** |
| `docs/ROADMAP.md` | 覆写型当前态 | 活跃待办（P0/P1/P2/暂缓）与按模块分组的 Level C 待实测清单 | 新增待办、优先级变化或真机闭环核销时**覆写对应行** |
| `docs/CURRENT.md` | 覆写型当前态 | 唯一当前活动任务的范围、基线与检查点 | 活动任务启动、检查点推进或收尾时覆写 |
| `docs/DEVELOP_LOG.md` | 按月滚动追加 | 倒序记录真实项目变更（根因、改动、验证与待实测点，建议 ≤ 15 行/条） | 形成真实项目变更时置顶追加；跨月按批准归档 |
| `docs/DECISIONS.md` | 低频长期契约 | 长期设计决策（ADR `D001`–`D073`）与替代关系 | 产生新长期决策或正式推翻旧决策时追加/标 `Superseded` |
| `docs/ARCHITECTURE.md` | 低频长期契约 | 稳定分层、核心调用链与扩展点地图 | 模块分层、公共层或核心调用链变化时更新 |
| `docs/TESTING.md` | 低频长期契约 | 长期验证规则、分级、守护入口与收尾核对口径 | 长期验证原则或守护规范变化时更新；单任务测试细则写测试文件 docstring |

### 归档索引（无损搬运，原编号与正文均保留）

| 原内容范围 | 归档位置 |
|---|---|
| `AI_CONTEXT` 更早历史（`§4.1 ~ §4.109`、旧提交、历史测试基线） | [AI_CONTEXT_history.md](archive/AI_CONTEXT_history.md) |
| `AI_CONTEXT` 2026-10 ~ 11（`§4.110 ~ §4.187`、顶部流水、旧工作区与全量链） | [AI_CONTEXT_2026-10_11.md](archive/AI_CONTEXT_2026-10_11.md) |
| `DEVELOP_LOG` 2026-08 / 2026-09 / 2026-10 | [develop_log_2026-08.md](archive/develop_log_2026-08.md)、[09.md](archive/develop_log_2026-09.md)、[10.md](archive/develop_log_2026-10.md) |
| `ROADMAP` 瘦身前全文快照（2026-11-27 原始字节） | [ROADMAP_before_slimming_2026-11-27.md](archive/ROADMAP_before_slimming_2026-11-27.md) |
| `ROADMAP` 原「已完成」总表、历史主线、已取消项与分段历史归档 | [ROADMAP_done_2026-09_11.md](archive/ROADMAP_done_2026-09_11.md) |
| `TESTING` 单任务/专项测试契约原文（原 `5.a ~ 5.ae`、L1/L2 细则） | [TESTING_case_notes_2026-09_11.md](archive/TESTING_case_notes_2026-09_11.md) |
| `CURRENT` 瘦身前历史检查点原文（2026-11-12 ~ 11-26） | [CURRENT_2026-11-26.md](archive/CURRENT_2026-11-26.md) |

- **入口与治理指针**：会话启动入口 [AGENTS.md](../AGENTS.md) / [CLAUDE.md](../CLAUDE.md)；六角色工作流 [oas-architect/SKILL.md](../.agents/skills/oas-architect/SKILL.md) 及三个按需 `references/`；核心治理决策 `D063` / `D064` / `D069` / `D070` / `D073` 见 [DECISIONS.md](DECISIONS.md)。
- **原则**：源码和最新 Git 状态始终高于本文档；确认事实变化后按 D073 仅同步真正受影响的文档。

---

## 1. 项目简介

- 项目：`OnmyojiAutoScript-easy-install-self`（Python 3.10，Windows / MuMu 模拟器）。
- 用户仓库 `origin`：`https://github.com/Hualaijushi/OnmyojiAutoScript.git`。
- 原作者仓库 `upstream`：`https://github.com/xylolit-mu/OnmyojiAutoScript.git`（只读参考，不推送）。
- 当前主要控制后端：`minitouch`。
- 主要模块：游戏任务（`tasks/`）、页面识别与导航（`tasks/GameUi/`）、图像与 OCR RPC（`module/image/`、`module/ocr/`）、输入控制与采样（`module/device/`、`module/click_pipeline.py`、`module/click_sampler.py`）、调度与双实例同步（`script.py`、`module/script/`、`module/instance_sync/`）、Web 标注器（`module/server/`）。

---

## 2. 当前 Git 与工作区口径

- 当前分支：`master`，跟踪 `origin/master`。
- 工作区长期保持「多轮改动未提交」的有意积累；实际 `HEAD`、分支、暂存、未暂存与未跟踪清单以实时 `git status` / `git rev-parse HEAD` 为准，不在本文档维护静态文件清单。
- `config/oas*.json`、`log/` 由 `.gitignore` 排除，不纳入版本控制。
- **工作区有意保留的特殊资源提示**（去留由用户决定，未修改）：
  - `tasks/GlobalGame/gg/` 好友邀请弹窗：`g_cat_food` / `g_dog_food` 的识别框 `(675,516,43,46)` 小于模板图（`59×65` / `60×63`），当前必不命中（见 §6）。
  - 4 张无规则引用的孤儿图：`tasks/ActivityShikigami/as/climb/climb_item_13.png`、`tasks/GlobalGame/ui/ui_ui_reward_1.png`、`tasks/Dokan/res/res_dokan_enter_again.png`、`tasks/GameUi/page/page_num_tongxin.png`。

---

## 3. 核心技术约束

### 3.1 公共随机模块

公共随机能力位于 `module/base/utils/random.py`，使用模块级 `SystemRandom()`（`random_delay`、`random_point_in_roi`、`random_center_point_in_roi`、`random_int`、`random_triangular`）。新增业务随机逻辑必须复用该模块，不随意新建 `SystemRandom`，不引入普通 `random` 或 `np.random`；轨迹算法中既有 `np.random` 不做无关重构（`D007`）。

### 3.2 点击确认等待与交互层

- `BaseTask.appear_then_click(..., confirm_delay=None)` 与 L2 `policy=None`（`InteractionPolicy.*`）默认关闭，保持向后兼容；启用路径遵循「首次识别 → 随机等待 → 重新截图 → 二次确认 → 重新生成最新坐标 → 点击」，目标消失则零点击（`D001`）。
- L1 单击与长按经 `execute_single_click` / `execute_long_click` 收口（`D026`、`dev_tools/click_entry_guard.py`）；禁止在 `Control.click()` 或设备驱动层全局叠加随机等待（`D002`）。
- 协议等待、截图间隔、RPC 轮询、重试退避与 FSM 超时属于稳定性时序，不随意随机化；任务级休息（`FatigueManager`）不进入 Action transaction 内部（`D001`）。

### 3.3 修改边界

- 不进行与当前任务无关的重构、格式化或删除已有测试/功能。
- 不修改用户未授权的模块，保护全部预存 WIP 与用户标注资源。
- 默认不自动 `commit` / `push` / `merge --continue` / `reset` / `checkout`，除非用户明确要求。
- 新增代码注释与项目文档一律使用中文。
- 静态编译与离线单元测试不替代用户明确授权的设备或游戏内测试（Level C）。

---

## 4. 核心模块当前状态速览

| 模块 / 领域 | 当前有效能力与最近改动摘要 | 状态与待验边界 | 权威参考 |
|---|---|---|---|
| **Chess（百鬼棋局）** | 兼容吸收上游 `Frame` 识别与阵容编辑器；备战直接先上卡、单次详情上限、跨回合 pending 调度、`board_slots` 格级真值表、回弹稳态确认、切片 `PREPARE_FOLLOWUP`、`detail_name` 白字隔离防透底、Web 标注器候选识别测试；11-27 修正：御魂留已有等对象不空留槽、同名拖前核名防降星、重复阵容副本让位、全盘 `1..12` 占位核查与局部 `unknown` 人口满员兜底 | 离线定向完成，多轮修复待 `oas2` 实盘 Level C | `D037`/`D050`/`D071`/`D072`；[DEVELOP_LOG](DEVELOP_LOG.md) 11-24~27 |
| **Dokan（福利道馆）** | 独立 `WelfareDokan` 流程，取消例行回顶；单卡锚点对齐（含滑前赏金图标前置校验与页身份解耦）、触底过冲回弹有界重滑（`<=150px`）、有效刷新后定向释放点击记录、观察层放过有界原地局部徽记闪烁、放弃后右空白主动清战绩弹窗并确认再战连续 2 帧消失再计 `120s` 回庭院；支持每周运行日与独立 `layout` | 离线及现场原图回放完成；前 3 轮刷新释放已在实盘命中，完整两馆等仍待 Level C | `D040`/`D046`/`D049`/`D051`/`D058`/`D059`/`D060`/`D061`/`D065`；[DEVELOP_LOG](DEVELOP_LOG.md) 11-23~26 |
| **SixRealms（六道之门）** | 商店购买扣费核对（孔雀国轰雷 200 校验）；孔雀国 `I_PK_STORE_STILLIN` 新素材（实盘命中）、Boss 战前无轰雷主动放弃试炼、战败放弃兼容 `I_UI_CONFIRM`；11-26 补齐 `page_ms_prepare` / `page_pk_prepare` 跨副本分类隔离 | 离线验证完成；重启实例后新开局与放弃试炼流程待 Level C | `D028`；[DEVELOP_LOG](DEVELOP_LOG.md) 11-26 |
| **MetaDemon（超鬼王）** | 庭院直达入口（`D067`）；已撤回 `D068` 纯循环误改并完整恢复原功能与配置；支持可选 `use_current_queue` 当前队列循环、末票召唤等待、准备页提前交接与不喝茶按疲劳恢复至 60 调度 | 离线兼容性完成；真实战斗/喝茶/无鬼王/OCR 调度均待 Level C | `D067`/`D068`(撤回)；[DEVELOP_LOG](DEVELOP_LOG.md) 11-11~13 |
| **XinLan & 双实例同步** | 通用账本同步核心（`module/instance_sync/`，`D029`）与组队会合（`team.py`，`D030`）、御魂→个人突破轻量循环（`D032`）；`tasks/XinLan` 骨架与适配器（含 11-23 好友页连续弹窗与有界导航恢复） | `D029`/`D030`/`D032` 离线通过；同心之兰待回传 P5 实机日志填参、异常弹窗待 Level C | `D029`/`D030`/`D032`；[ARCHITECTURE.md](ARCHITECTURE.md) |
| **SwitchSoul（御魂切换）** | 数字模式 V1/V2（滑顶、防吞滑、预设 1~8 组支持）真机初验已过；按名称精确搜索、回顶/翻页防回弹错判、分组固定点两次、契灵替换确认框均离线完成 | 按名称搜索/回弹/8 组/契灵确认框待 Level C；V3+ 待实机采样 | `D035`/`D041`；[DEVELOP_LOG](DEVELOP_LOG.md) 11-02/20 |
| **日常与副本任务** | `AreaBoss` 不同鬼王去重与空名匿名计数（`D066`）、战败 3 次重试；`WantedQuests` 新详情适配、执行记录隔离（`D054`）、进度备用窄条补读；`DailyTrifles` 调度（`D047`）、吉闻/庭院事务/寿司/买体力、领取邮件 `COPY3`；`BondlingFairyland` 建房/锁队/队员计数；`DemonRetreat` 集结 185s 等待与周六主动开启；`Secret` 奖励与结果安全区、山兔勾玉选关；`EternitySea` 金币加成；`Kekkai` 结界轮换插队兼容 | 离线验证完成，各新增/修改分支均待对应真机窗口 Level C | `D017`/`D020`/`D021`(Superseded)/`D023`/`D031`/`D033`/`D034`/`D042`~`D044`/`D047`/`D053`~`D055`/`D057`/`D062`/`D066`；[ROADMAP.md](ROADMAP.md) |
| **L1 / L2 / 轨迹 / 结算 / 观测** | L1 单击/长按全仓收口（`D026`）与静态守卫；L2 `InteractionPolicy` + Batch A FIRE FSM；`TouchSwipeModel`（`D018`）+ `SwipeEndpointSampler`（`D022` 已 Level C PASS）；Settlement Micro-Burst v1.2（`D025`）；`FrameWait` / `frame_state` 视觉等待与帧差观测（`D010` / `D012`，详见 [ARCHITECTURE.md](ARCHITECTURE.md)）；`BehaviorTrace` 与点击统计接口；Web 标注器与 `annotator` 帧隔离 | `D022` 已真机通过并冻结参数；其余 L1/L2/Settlement v1.2/K3·K4/annotator 隔离待 Level C | `D001`/`D004`/`D010`/`D012`/`D014`/`D016`/`D018`/`D019`/`D022`/`D025`/`D026`；[ARCHITECTURE.md](ARCHITECTURE.md) |

---

## 5. 已确认保留的 upstream 修改

- **NemuIPC 与 scrcpy**：`module/device/method/nemu_ipc.py`、`module/device/method/scrcpy/scrcpy.py` 保留 `upstream/self` 原版，暂不因普通随机差异做无关重构（`D009`）。
- **Image 与 OCR**：`module/image/rpc.py`、`module/image/runtime.py`、`module/ocr/ppocr.py`、`module/ocr/rpc.py` 已审查保留。默认 `low_spec_mode=false`（阈值偏移 0、medium OCR）；启用低配后阈值 `-0.1`、small OCR、frame TTL 10s。
- **AntiBan 作息逻辑**：保留 upstream 版本（默认 `enable=False`、缺键自动默认、跨午夜窗口、`start==end` 关闭、累计仅计活跃 wall-clock、多实例独立状态）。
- **业务模块**：`Chess`、`KekkaiUtilize`、`Costume`、`CostumeShikigami`、`BondlingFairyland`、`Sougenbi` 保留（`KekkaiUtilize.min_run_interval` 默认 0）。

---

## 6. 当前验证口径与主要非阻断限制

- **验证口径（`D069` / [TESTING.md](TESTING.md) §1）**：局部源码改动默认只做改动文件 `py_compile`、`git diff --check` 与 1～3 个关键离线场景；普通阶段离线测试累计默认 **120 秒**（含执行者与 Codex 复核）；统一使用 `toolkit/python.exe dev_tools/guarded_unittest.py`；全量测试非默认门禁，须明确批准。2026-10-25 ~ 11-12 历次全量基线链见 [AI_CONTEXT_2026-10_11.md](archive/AI_CONTEXT_2026-10_11.md) §7。
- **已知非阻断限制（除非任务涉及，不顺带扩改）**：
  1. `GlobalGame` 好友邀请粮协模板（59×65 / 60×63）大于当前识别框 `(675,516,43,46)`，设「接受勾协和粮协」时会退化为忽略。
  2. `SixRealms` 商店存在 P1/P2 观察项（刷新后 HUD 数字滞后、动画稳态 ROI 覆盖、月之海 300 与孔雀国 200 价差等，待真机帧）。
  3. `tasks/Component/CostumeShikigami/assets.py`（及部分生成 `assets.py`）存在预存生成器注释行尾空格，属正常现象，不为消除 `git diff --check` 提示手改生成文件。
  4. Image/OCR RPC 断线后无自动恢复；`low_spec_mode` 的 small OCR 模型首次可能尝试联网下载，离线环境无自动回退 medium。
  5. 诊断导出 endpoint 尚无统一强制鉴权；AntiBan 与 GlobalFatigue 进程重启后累计清零（与设计一致，不擅自加持久化）。
  6. `Script._publish_fatigue_state` 独立 2 秒轮询线程无退出条件，记为后续 P2 架构审查项。
  7. `Device.drag()` / `drag_minitouch` 在业务层零调用方，实际拖拽由 `tasks/Chess/runtime/press_and_drag.py` 承担。
  8. `annotator` 帧注册隔离未完成 Level C 前，避免在某配置运行中对同名配置开启实时采集（上传图片不受影响）。
  9. **输入层随机化归因与自动化特征面边界**：`SystemRandom` 仅消除全局种子污染，不改变同一 ROI 均匀分布；当前 MuMu 握手下 minitouch `pressure` 随机化恒为 1；全仓特征面权重由高到低依次为「设备驻留物 > 模拟器本体 > 轮询反应时序 > 输入层 > 行为聚合」，详见 [AI_CONTEXT_2026-10_11.md](archive/AI_CONTEXT_2026-10_11.md) §8.1–§8.3。
