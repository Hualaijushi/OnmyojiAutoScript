---
name: oas-architect
description: "OAS\u516d\u89d2\u8272\u5de5\u4f5c\u6d41\u3002\u6309\u8bf7\u6c42\u9009\u62e9\u4e0a\u4e0b\u6587\u534f\u8c03\u3001\u9700\u6c42\u4e0e\u67b6\u6784\u3001\u5b9e\u65bd\u3001\u6545\u969c\u5206\u6790\u3001\u5ba1\u67e5\u9a8c\u6536\u6216\u4ea4\u63a5\u6587\u6863\u3002\u666e\u901a\u6062\u590d\u9884\u7b97\u4ec5\u63d0\u9192\u5e76\u8865\u9f50\u5fc5\u8981\u4e8b\u5b9e\uff0c\u4e25\u683c\u9a8c\u6536\u6309\u660e\u786e\u5bf9\u8c61\u89e6\u53d1\u3002Codex\u603b\u8d1f\u8d23\uff0cClaude\u9ed8\u8ba4\u5b9e\u65bd\uff0c\u6743\u9650\u6cbf\u7528\u7528\u6237\u6279\u51c6\u8303\u56f4\u3002"
---

# OAS Architect V1.2

开发前先只读核实、问清目标与保留范围，提出具体方案交用户审核；用户明确同意方案后才实施。方案内不重复审批，需求或范围变化先确认并审核。见项目规则及D070。

验证默认遵循TESTING §1/D069：最小相关检查、普通局部120秒预算、未明确批准不全量；真实画面问题不以增加mock数量代替实测。

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
