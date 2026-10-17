# M0 逐行通读发现（持续更新）
> 2026-10-17 · 已全文精读：main/agent_graph/service/llm/agent/tools/analysis/nlparse/scheduler（含 520+ 测试实证）；结构级：db/mcp_server/quotes/前端
> 待补：db.py 全文、quotes.py、mcp_server.py、前端 16.5k 行（下一批）

## 本批新发现（P3/边界，均不阻塞）
1. analysis.collect_dashboard L489 注释"三个外部行情请求并行"实际 gather 只有 2 个；live_quotes 在 L470 串行先行——可并入 gather（性能小优化）
2. analysis.ledger_view 应急金月数=当月现金/当月必要支出——月初数据少时 months_covered 虚高（建议用近 3 个月均值）
3. 口径混用：DTI 用 settings.monthly_income，储蓄率用当月流水收入——同一报告两个"收入"口径
4. nlparse：无股票语境的 6 位纯数字（如"转账 600519"）会被当金额；parse_with_ai 日期非法时丢相对日期回退今天
5. scheduler：CronTrigger 时区硬编码 Asia/Shanghai，而报告内容日期用系统时区 astimezone()——服务器非 CST 时会"8 点发报告写的却是昨天/今天错位"；订阅提醒先删后写非原子（崩溃窗口丢当日提醒）
6. scheduler 状态时间戳格式不一致（L96 aware / L241 naive）

## 结论
- 未发现新 P1/P2；项目核心路径（解析→入账→计算→风控→成文）实现质量高于预期
- 与 M0 已修项合并后，"数字可复核"叙事的技术底座成立

## 2026-10-17 深夜批（M0.7 第二轮）
- **db.py**：1-1200 全文 + undo/runs 核心段全文。undo 有 consumed_at TOCTOU 防护 ✅；clear_history 不清审计/撤销记录（正确的留存设计）✅。新发现：`_COUNT_ALLOWED_TABLES` 含 `audit_log`/`transactions_fts`，但真实表名是 `audit_logs` 且 FTS 表不存在——被调用会 OperationalError（当前无调用方，属死配置，M1 拆分时清理）
- **quotes.py**：全文。降级链（东财→新浪→快照）完整、TTLCache 统一注册、盘前 0 价用昨收兜底——质量标杆模块；小点：live_quotes 每次调用都查 settings 表（可缓存）
- **mcp_server**：20+ 工具已暴露，FastMCP 缺失时有假装饰器兜底（防御性设计）
- **前端**：网络层 fetch-event-source（POST SSE+abort）规范；会话切换有 abort 清理
- **覆盖度**：后端 10 文件全文 + db 主体 + 其余结构级；前端组件级逐行待 M1 重构时顺带完成（重构即审查）

## M0 收口结论
- 全量验证：412+23+90=525 passed（deselect 1=东财联网测试）+ tsc 0 错误 + ruff 全绿
- v2.1.0 打 tag，M0 关闭；剩余逐行项并入 M1（重构即审查，避免二次返工）
