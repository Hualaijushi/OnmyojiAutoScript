# 项目 AI 开发规则（Claude / Codex 通用）

> 本文件是所有开发 AI 的启动入口（简短）。`AGENTS.md` 内容与本文件保持一致；两者随仓库提交（`.gitignore` 已加 `!CLAUDE.md` / `!AGENTS.md` 例外），重新 clone / 换机器后仍在。
> 项目：`OnmyojiAutoScript-easy-install`（阴阳师自动化脚本，Python 3.10，Windows / MuMu）。
> 本文件只承担「启动入口」：阅读顺序 + 核心规则。当前 HEAD / 测试数字 / 任务详情等易过期内容由 `docs/AI_CONTEXT.md` 与 `docs/ROADMAP.md` 维护，不复制到这里。

---

## 推荐阅读顺序

不必每次通读整个 `DEVELOP_LOG.md`：

1. `docs/AI_CONTEXT.md` —— 当前状态快照（开发阶段、Git 状态、测试基线、核心能力状态、已知问题、当前限制、下一步）
2. `docs/ROADMAP.md` —— 现在应该做什么、优先级、前置依赖、什么能做 / 什么等真机
3. `docs/DECISIONS.md` —— 哪些设计决定不能随便推翻（ADR）
4. `docs/ARCHITECTURE.md` —— 真实分层与调用链地图
5. `docs/TESTING.md` —— 改完怎么验证
6. `docs/DEVELOP_LOG.md` —— **只在需要某次改动的历史原因时**读最近相关记录

---

## 核心开发规则

1. **以当前源码为准**。历史文档可能滞后；改之前用 grep / 读文件确认真实源码。文档与源码冲突时以源码为准，并在同一轮修正文档。
2. **开发 / 正式设计结束后逐项检查 6 份项目文档，只更新受影响的**（`AI_CONTEXT` / `DEVELOP_LOG` / `ROADMAP` / `ARCHITECTURE` / `DECISIONS` / `TESTING`）。是否更新某份文档，以**「本轮是否改变了该文档负责的项目事实」**为准，**不以「是否修改了代码」为唯一标准**——纯设计工作（定架构方案、增删长期决策、改 ROADMAP / 测试规范 / 真机要求 / AI 规则）即使没动代码也要更新对应文档。本轮没有改变任何一份文档负责的项目事实时，6 份都不写。各文档触发条件见 `docs/AI_CONTEXT.md` §0 的表。
3. **新增代码注释、新增项目文档一律用中文**。不写大段解释型注释，只解释非显然的设计原因 / 异常隔离原因 / 为什么某段不能影响业务。
4. **默认不 commit / push / merge --continue**，除非用户明确要求。工作区长期「多轮改动未提交」是有意的。不用 `git reset --hard` / `git checkout --` 丢弃改动。
5. **默认不启动 MuMu / 模拟器 / 游戏 / 真实 ADB 设备 / 真实 OCR 服务**（无用户明确授权时）。属真机级（Level C，见 `docs/TESTING.md` §2）的改动本轮不做，记入 `docs/ROADMAP.md`。
6. **默认验证流程**：源码改完依次「相关单元测试 → `toolkit/python.exe -m compileall -q <改动>` → `toolkit/python.exe -m unittest discover -s tests`（全绿）→ `git diff --check`」。一律用 `toolkit/python.exe`（系统 python 缺依赖）。细则见 `docs/TESTING.md`。

---

## 强制收尾流程

```
开发 / 正式设计工作完成
 → 执行所需验证（源码改动跑上面「默认验证流程」）
 → 人工过一遍 git diff / git status（无误改 / 无调试残留）
 → 逐项审查 6 份项目文档，按「项目事实是否变化」决定更新哪些
 → 再次 git diff --check
 → 输出最终报告，固定包含下面的「## 文档同步」段
```

```markdown
## 文档同步

- AI_CONTEXT.md：已更新 / 无需更新（原因）
- DEVELOP_LOG.md：已更新 / 无需更新（原因）
- ROADMAP.md：已更新 / 无需更新（原因）
- ARCHITECTURE.md：已更新 / 无需更新（原因）
- DECISIONS.md：已更新 / 无需更新（原因）
- TESTING.md：已更新 / 无需更新（原因）
```
