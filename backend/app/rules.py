"""轻量分类规则引擎：CSV 导入 / 对话记账的分类增强。

零新依赖，纯标准库 re。核心函数：
- validate_rule(rule_obj) -> bool：schema 校验，畸形即抛。
- match_rule(rule_obj, desc, amount, *, baseline_category=None) -> dict | None：单条匹配。
- apply_rules(rules, desc, amount="0", baseline_category=None) -> str | None：命中即返分类。
- builtin_rules() -> list[dict]：把 nlparse 关键词包装成结构化规则。

规则 schema（JSON 数组项）：
{
  "id": "uuid",
  "match": {                    // AND 组合
    "desc_contains": ["str"],   // 描述包含任意一项即过（OR）
    "desc_regex": "pattern",    // Python regex，可选
    "category_is": "str",       // 精确分类（post hoc 校验）
    "category_in": ["str"],     // 分类集合（post hoc 校验）
    "amount_min": 0,            // 金额下限（按绝对值判断）
    "amount_max": 1000000       // 金额上限
  },
  "action": {"set_category": "str"},
  "priority": 100,              // 越大越优先
  "enabled": true,
  "note": "str"
}
"""

from __future__ import annotations

import re

from . import nlparse

DEFAULT_RULE_VERSION = 1


def validate_rule(rule_obj: dict) -> bool:
    """校验规则 schema；畸形时 raise ValueError。"""
    if not isinstance(rule_obj, dict):
        raise TypeError("规则必须是一个 dict")

    for key in ("id", "match", "action"):
        if key not in rule_obj:
            raise ValueError(f"缺少必填字段：{key}")

    match = rule_obj["match"]
    if not isinstance(match, dict):
        raise TypeError("match 必须是一个 dict")

    action = rule_obj["action"]
    if not isinstance(action, dict):
        raise TypeError("action 必须是一个 dict")

    set_cat = action.get("set_category")
    if not isinstance(set_cat, str) or not set_cat.strip():
        raise ValueError("action.set_category 必须是非空字符串")

    amount_min = match.get("amount_min")
    amount_max = match.get("amount_max")
    if (
        amount_min is not None
        and amount_max is not None
        and float(amount_min) > float(amount_max)
    ):
        raise ValueError(
                f"amount_min({amount_min}) 不能大于 amount_max({amount_max})"
            )

    return True


def match_rule(
    rule_obj: dict,
    desc: str,
    amount: str = "0",
    *,
    baseline_category: str | None = None,
) -> dict | None:
    """按单条规则匹配 desc + amount + baseline_category；命中返回 action，否则 None。"""
    match = rule_obj.get("match", {})

    # desc_contains：OR 命中即过（空列表视为无此约束）
    contains = match.get("desc_contains") or []
    if contains:
        desc_lower = desc.lower()
        if not any(str(kw).lower() in desc_lower for kw in contains):
            return None

    # desc_regex：可选，用 re.search
    regex = match.get("desc_regex")
    if regex and not re.search(regex, desc):
        return None

    # amount_min / amount_max：按绝对值过滤
    amt_abs = abs(float(amount)) if amount else 0.0
    amount_min = match.get("amount_min")
    amount_max = match.get("amount_max")
    if amount_min is not None and amt_abs < float(amount_min):
        return None
    if amount_max is not None and amt_abs > float(amount_max):
        return None

    # category_is / category_in：post hoc 校验（依赖 baseline_category）
    if baseline_category is not None:
        category_is = match.get("category_is")
        if category_is and baseline_category != category_is:
            return None
        category_in = match.get("category_in")
        if category_in and baseline_category not in category_in:
            return None

    return rule_obj.get("action", {})


def apply_rules(
    rules: list[dict],
    desc: str,
    amount: str = "0",
    baseline_category: str | None = None,
) -> str | None:
    """跑全部规则，命中第一条（priority 降序）即返回 set_category；全部未命中返回 None。"""
    enabled = [r for r in rules if r.get("enabled", True)]
    enabled.sort(key=lambda r: int(r.get("priority", 0)), reverse=True)

    for rule in enabled:
        action = match_rule(
            rule, desc, amount, baseline_category=baseline_category
        )
        if action is not None:
            return action.get("set_category")

    return None


def builtin_rules() -> list[dict]:
    """把 nlparse 的 CATEGORY_KEYWORDS 包装成结构化规则，优先级从 1000 往下（低于用户自定义）。"""
    rules: list[dict] = []
    priority = 1000

    for cat, words in nlparse.CATEGORY_KEYWORDS:
        if cat == "收入":
            continue
        for w in words:
            rules.append(
                {
                    "id": f"builtin-{cat}-{w}",
                    "match": {"desc_contains": [w]},
                    "action": {"set_category": cat},
                    "priority": priority,
                    "enabled": True,
                    "note": f"内置：{cat} 关键词「{w}」",
                }
            )
            priority -= 1

    # 收入关键词
    for w in nlparse.INCOME_KEYWORDS:
        rules.append(
            {
                "id": f"builtin-收入-{w}",
                "match": {"desc_contains": [w]},
                "action": {"set_category": "收入"},
                "priority": priority,
                "enabled": True,
                "note": f"内置：收入关键词「{w}」",
            }
        )
        priority -= 1

    return rules
