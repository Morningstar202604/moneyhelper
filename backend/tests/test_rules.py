"""轻量规则引擎单测：match_rule / apply_rules / validate_rule / builtin_rules。"""

from __future__ import annotations

import pytest
from app import rules


# ---------------------------------------------------------------------------
# 1. 规则命中优先于 nlparse 关键词
# ---------------------------------------------------------------------------
def test_user_rule_overrides_builtin_keyword() -> None:
    """用户自定义规则（高优先级）命中后，不再走 nlparse 的关键词分类。"""
    # nlparse 会把「美团-XX酒店-住宿」误判为「购物」（因含「淘宝」等词不会命中）
    # 我们用一条用户的「酒店」规则来覆盖。
    user_rules = [
        {
            "id": "user-hotel-001",
            "match": {"desc_contains": ["酒店", "宾馆", "旅馆"]},
            "action": {"set_category": "居住"},
            "priority": 200,
            "enabled": True,
            "note": "酒店类统一归居住",
        },
    ]
    desc = "美团-XX酒店-住宿"
    # nlparse.classify 这里不做断言（依赖其具体实现），只断言规则命中结果。
    result = rules.apply_rules(user_rules, desc, amount="500")
    assert result == "居住"


# ---------------------------------------------------------------------------
# 2. amount 上下界过滤
# ---------------------------------------------------------------------------
def test_amount_bounds_filtering() -> None:
    """金额在界内才匹配，超出则跳过。"""
    rule = {
        "id": "user-big-expense",
        "match": {"desc_contains": ["购物"], "amount_min": 1000, "amount_max": 50000},
        "action": {"set_category": "大额消费"},
        "priority": 100,
        "enabled": True,
        "note": "",
    }
    # 金额 500 不在 [1000, 50000] 内 → 不匹配
    assert rules.apply_rules([rule], "商场购物", amount="500") is None
    # 金额 3000 在范围内 → 命中
    assert rules.apply_rules([rule], "商场购物", amount="3000") == "大额消费"
    # 支出用负数（按绝对值判断）：-3000 同样命中
    assert rules.apply_rules([rule], "商场购物", amount="-3000") == "大额消费"


# ---------------------------------------------------------------------------
# 3. 多个规则冲突取优先级
# ---------------------------------------------------------------------------
def test_priority_conflict_resolution() -> None:
    """priority 高的规则先匹配，同一描述多条命中的情况下取最高优先级。"""
    ruleset = [
        {
            "id": "r-low",
            "match": {"desc_contains": ["美团"]},
            "action": {"set_category": "餐饮"},
            "priority": 50,
            "enabled": True,
            "note": "",
        },
        {
            "id": "r-high",
            "match": {"desc_contains": ["美团"]},
            "action": {"set_category": "交通"},
            "priority": 300,
            "enabled": True,
            "note": "美团打车优先",
        },
    ]
    # 两条都命中 desc，但 priority 300 的先跑
    result = rules.apply_rules(ruleset, "美团打车-快车", amount="30")
    assert result == "交通"


# ---------------------------------------------------------------------------
# 4. 全部未命中时回退 nlparse（回退本身不属于本模块，但 apply_rules 返回 None）
# ---------------------------------------------------------------------------
def test_no_rule_match_returns_none_for_nlparse_fallback() -> None:
    """所有规则都不命中时返回 None，由调用方回退 nlparse 关键词分类。"""
    ruleset = [
        {
            "id": "r1",
            "match": {"desc_contains": ["滴滴"]},
            "action": {"set_category": "交通"},
            "priority": 100,
            "enabled": True,
            "note": "",
        },
    ]
    # 描述不含「滴滴」→ 不命中
    result = rules.apply_rules(ruleset, "买了一台笔记本电脑", amount="8000")
    assert result is None


# ---------------------------------------------------------------------------
# 5. validate_rule 拒绝畸形 schema
# ---------------------------------------------------------------------------
def test_validate_rule_rejects_malformed_schema() -> None:
    """缺少必填字段、amount_min > amount_max、set_category 非空均应 raise。"""
    # 缺少 id
    with pytest.raises(ValueError, match="id"):
        rules.validate_rule({"match": {}, "action": {"set_category": "餐饮"}})

    # 缺少 match
    with pytest.raises(ValueError, match="match"):
        rules.validate_rule({"id": "x", "action": {"set_category": "餐饮"}})

    # 缺少 action
    with pytest.raises(ValueError, match="action"):
        rules.validate_rule({"id": "x", "match": {}})

    # set_category 为空字符串
    with pytest.raises(ValueError, match="set_category"):
        rules.validate_rule(
            {"id": "x", "match": {}, "action": {"set_category": ""}}
        )

    # amount_min > amount_max
    with pytest.raises(ValueError, match="amount_min"):
        rules.validate_rule(
            {
                "id": "x",
                "match": {"amount_min": 9999, "amount_max": 100},
                "action": {"set_category": "餐饮"},
            }
        )

    # 正常规则通过
    assert rules.validate_rule(
        {
            "id": "ok",
            "match": {"desc_contains": ["打车"]},
            "action": {"set_category": "交通"},
            "priority": 100,
            "enabled": True,
            "note": "",
        }
    )
