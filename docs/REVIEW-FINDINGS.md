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
