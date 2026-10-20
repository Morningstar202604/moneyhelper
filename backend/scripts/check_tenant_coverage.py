"""检查数据层 SQL 是否带租户过滤（多租户回归护栏）。

用法（在 backend/ 下）：
    .venv/Scripts/python -m scripts.check_tenant_coverage
    # 或 python -m pytest tests/test_tenant_isolation.py -q

规则：出现在 _TENANT_TABLES / _COMPOSITE_TABLES 里的表，任何 SELECT/UPDATE/DELETE
都必须带 user_id 条件；INSERT 必须写 user_id。例外用 `# tenant: allow` 标注（同一行）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DB_DIR = Path(__file__).resolve().parents[1] / "app" / "db"

TENANT_TABLES = {
    "positions",
    "transactions",
    "subscriptions",
    "debts",
    "budgets",
    "goals",
    "watchlist",
    "user_memory",
    "attachments",
    "dept_reports",
    "conversation_summary",
    "pending_actions",
    "undo_records",
    "member_loans",
    "members",
    "provenance_log",
    "audit_logs",
    "runs",
    "sessions",
}

# 表名前的动作决定检查方式
_READ_RE = re.compile(r"\b(?:FROM|UPDATE|DELETE\s+FROM|JOIN)\s+(\w+)", re.I)
_INSERT_RE = re.compile(r"\bINSERT\s+(?:OR\s+\w+\s+)?INTO\s+(\w+)", re.I)


def _statements(src: str) -> list[tuple[int, str]]:
    """粗粒度提取 SQL 字符串字面量（含跨行拼接），返回 (起始行号, 文本)。"""
    out: list[tuple[int, str]] = []
    for m in re.finditer(r'((?:"[^"]*"\s*)+)', src):
        text = "".join(re.findall(r'"([^"]*)"', m.group(1)))
        if not re.search(r"\b(SELECT|INSERT|UPDATE|DELETE)\b", text, re.I):
            continue
        line = src[: m.start()].count("\n") + 1
        out.append((line, text))
    return out


def main() -> int:
    problems: list[str] = []
    for path in sorted(DB_DIR.glob("*.py")):
        src = path.read_text(encoding="utf-8")
        if "_migrate_multitenant" in src or "PRAGMA" in src:
            pass  # 迁移本身要绕过检查
        for line, sql in _statements(src):
            # 迁移/建表语句不属于运行期查询
            if re.search(r"\b(CREATE|ALTER|DROP)\b", sql, re.I):
                continue
            tables = {t.lower() for t in _READ_RE.findall(sql)}
            inserts = {t.lower() for t in _INSERT_RE.findall(sql)}
            hit_read = tables & TENANT_TABLES
            hit_insert = inserts & TENANT_TABLES
            if not hit_read and not hit_insert:
                continue
            if "user_id" in sql:
                continue
            # 允许显式豁免（例如迁移、全库统计、跨租户导出）
            context = src.splitlines()[max(0, line - 1) : line]
            if context and "tenant: allow" in context[0]:
                continue
            problems.append(
                f"{path.name}:{line} 缺少 user_id 过滤 → {' '.join(sql.split())[:90]}"
            )
    if problems:
        print(f"发现 {len(problems)} 处未按租户过滤的 SQL：")
        for p in problems:
            print("  " + p)
        return 1
    print("OK: 数据层 SQL 均已带租户过滤")
    return 0


if __name__ == "__main__":
    sys.exit(main())
