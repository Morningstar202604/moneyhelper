# 架构决策记录（ADR）
- ADR-001 确定性内核优先：数字只由代码计算，LLM 只叙述（provenance 可复核的地基）
- ADR-002 单库多域 → db/ 域模块包（M1.2）：门面兼容层保持 `db.X` 用法不变
- ADR-003 HITL 大额审批：LangGraph interrupt + pending 落库，向 MCP Elicitation 迁移
- ADR-004 部署形态无关：core 不依赖壳（FastAPI/Tauri/CLI 都是薄壳）
