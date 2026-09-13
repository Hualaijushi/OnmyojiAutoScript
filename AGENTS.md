# 项目 AI 开发规则（Codex / Claude 通用）

> 本文件与 `CLAUDE.md` 是同一套规则的两个入口，供 Codex 等其他开发 AI 使用。两者内容一致，不维护两份相互冲突的版本；若分歧，以 `CLAUDE.md` 为准并同步修正本文件。
> 两文件均随仓库提交（`.gitignore` 已加 `!CLAUDE.md` / `!AGENTS.md` 例外），重新 clone / 换机器后仍在。

---

## 推荐阅读顺序

1. `docs/AI_CONTEXT.md` —— 当前状态快照（开发阶段、Git 状态、测试基线、核心能力、已知问题、当前限制、下一步）
2. `docs/ROADMAP.md` —— 现在做什么、优先级、前置依赖、什么能做 / 什么等真机
3. `docs/DECISIONS.md` —— 哪些设计决定不能随便推翻（ADR）
4. `docs/ARCHITECTURE.md` —— 真实分层与调用链地图
5. `docs/TESTING.md` —— 改完怎么验证
6. `docs/DEVELOP_LOG.md` —— 只在需要历史原因时读最近相关记录

---

## 核心开发规则

1. **以当前源码为准**；文档与源码冲突时以源码为准，并在同一轮修正文档。
2. **开发 / 正式设计结束后逐项检查 6 份项目文档**（`AI_CONTEXT` / `DEVELOP_LOG` / `ROADMAP` / `ARCHITECTURE` / `DECISIONS` / `TESTING`），**只更新真正受影响的**。判断标准是「本轮是否改变了该文档负责的项目事实」，**不是「是否修改了代码」**——纯设计工作（定架构、增删长期决策、改 ROADMAP / 测试规范 / 真机要求 / AI 规则）没动代码也要更新对应文档；本轮没有改变任何文档负责的项目事实时 6 份都不写。触发条件见 `docs/AI_CONTEXT.md` §0。
3. **新增代码注释 / 项目文档一律中文**。
4. **默认不 commit / push / merge --continue**，除非用户明确要求。
5. **默认不启动 MuMu / 设备 / 游戏 / OCR 服务**；Level C（真机）改动本轮不做，记入 `docs/ROADMAP.md`。
6. **验证**：相关单元测试 → `toolkit/python.exe -m compileall` → `toolkit/python.exe -m unittest discover -s tests`（全绿）→ `git diff --check`。一律用 `toolkit/python.exe`。

---

## 强制收尾

开发 / 正式设计完成 → 执行验证 → 过一遍 `git diff` / `git status` → 逐项审查 6 份文档并按「项目事实是否变化」更新 → 再次 `git diff --check` → 输出报告，固定包含：

```markdown
## 文档同步

- AI_CONTEXT.md：已更新 / 无需更新（原因）
- DEVELOP_LOG.md：已更新 / 无需更新（原因）
- ROADMAP.md：已更新 / 无需更新（原因）
- ARCHITECTURE.md：已更新 / 无需更新（原因）
- DECISIONS.md：已更新 / 无需更新（原因）
- TESTING.md：已更新 / 无需更新（原因）
```
