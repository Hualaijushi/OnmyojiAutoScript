---
name: oas-architect
description: "OAS六角色工作流。按请求选择上下文协调、需求与架构、实施、故障分析、审查验收或交接文档。普通恢复补齐必要事实，严格验收按明确对象触发。执行者不绑定模型；Codex负责审查、最小验证与验收，权限沿用用户批准范围。"
---

# OAS Architect V1.2

开发前先只读核实、问清目标与保留范围，提出具体方案交用户审核；用户明确同意方案后才实施。方案内不重复审批，需求或范围变化先确认并审核。见项目规则及D070。

验证默认遵循TESTING §1/D069：默认1～3个关键离线场景，阶段累计120秒包含实施、复修与Codex复核，拆组或交接不重置。执行者不绑定模型；开发后Codex负责源码审查、必要的最小测试和验收，不默认重跑已有测试组。无实机授权时尽早交付待实测版本，不继续堆mock替代实测；批准范围内明确缺陷先修，范围外只报告，未批准不扩测/全量。

收口原则：仅审查本次增量及直接调用方，验证批准行为和直接回归风险；默认不新增测试文件或复杂替身，优先复用最小现有用例。发现范围外缺陷只记录并报告，不顺带修复、重构或扩大验证；确需扩大修改范围先交用户确认。最小检查满足后停止离线扩测，交付待实测版本。

| role | intent | reference |
|---|---|---|
| context_coordinator | recover / status | [context-loading](references/context-loading.md) |
| architect | requirements / design | [context-loading](references/context-loading.md) |
| implementer | approved_implementation | [task-handoff](references/task-handoff.md) |
| diagnostician | diagnose / troubleshoot | [context-loading](references/context-loading.md) |
| reviewer | review / acceptance | [review-closeout](references/review-closeout.md) |
| handoff_editor | handoff / checkpoint / docs | [task-handoff](references/task-handoff.md) |

```javascript
const r=await tools.exec_command({cmd:"toolkit/python.exe -B -X utf8 .agents/skills/oas-architect/scripts/oas_context.py status",max_output_tokens:4500});
text(r.output);
```
