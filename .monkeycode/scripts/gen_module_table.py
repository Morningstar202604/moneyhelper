#!/usr/bin/env python3
"""生成 docs/module-map.md 的模块表（M0.7 产出物）。

从每个后端模块的 docstring 与 AST 统计生成表格，保证文档里的"职责"
与代码实际结构同步；手写清单会随时间失真。

用法（仓库根目录）：
    python .monkeycode/scripts/gen_module_table.py

输出：直接打印 Markdown 表格，粘贴/重定向到 docs/module-map.md 的
「全部模块」小节即可。
"""

from __future__ import annotations

import ast
import pathlib
import sys


def collect(root: pathlib.Path) -> list[tuple[str, int, str, int, int]]:
    rows = []
    for p in sorted(root.rglob("*.py")):
        if "__pycache__" in str(p):
            continue
        text = p.read_text(encoding="utf-8")
        n = len(text.splitlines())
        try:
            tree = ast.parse(text)
        except SyntaxError:
            rows.append((str(p.relative_to(root.parent)), n, "PARSE ERROR", 0, 0))
            continue
        doc = (ast.get_docstring(tree) or "").strip().splitlines()
        first = doc[0].strip() if doc else "（无模块 docstring）"
        funcs = sum(
            1 for x in ast.walk(tree) if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        classes = sum(1 for x in ast.walk(tree) if isinstance(x, ast.ClassDef))
        rows.append((str(p.relative_to(root.parent)), n, first, funcs, classes))
    return rows


def main() -> int:
    root = pathlib.Path("backend/app")
    if not root.is_dir():
        print("请在仓库根目录运行本脚本", file=sys.stderr)
        return 1
    rows = collect(root)
    print("| 模块 | 行数 | 函数 | 类 | 职责 |")
    print("|---|---:|---:|---:|---|")
    for path, n, first, f, c in rows:
        name = path.replace("app/", "", 1)
        safe = first.replace("|", "\\|").replace("\n", " ")[:80]
        print(f"| `{name}` | {n} | {f} | {c} | {safe} |")
    print()
    print(f"合计 {len(rows)} 个文件、{sum(r[1] for r in rows)} 行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
