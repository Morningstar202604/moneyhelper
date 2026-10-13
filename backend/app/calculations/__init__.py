"""确定性金融计算引擎：所有数值计算纯代码执行，LLM 只做叙述解读。

本包提供四个计算模块：
- net_worth:     净值追踪（持仓市值 + 现金 - 负债 = 净值）
- returns:       收益率计算（XIRR / TWR / 简单收益率）
- health:        财务健康评分（五维 0-100 分）
- goals:         目标进度确定性计算

设计原则：
1. 所有函数均为纯函数（无副作用、无 I/O、无全局状态），可直接单测。
2. 仅依赖 Python 标准库（datetime, dataclasses），不引入 numpy/scipy。
3. 金额统一 round(..., 2)，日期使用 datetime.date。
4. 数值稳定性检查前置，异常输入立即 raise ValueError。
5. 与 analysis.py / evaluate.py 常量保持一致（CONCENTRATION_MAX_PCT, DTI_WARN_PCT 等）。

参考：FinRobot 设计哲学 — "所有数值计算必须纯代码确定性执行，LLM 只做叙述解读"。
"""

from .goals import GoalProgress, calculate_goal_progress
from .health import FinancialHealthScore, calculate_health_score
from .net_worth import NetWorthSnapshot, calculate_net_worth
from .returns import calculate_simple_return, calculate_twr, calculate_xirr

__all__ = [
    "FinancialHealthScore",
    "GoalProgress",
    "NetWorthSnapshot",
    "calculate_goal_progress",
    "calculate_health_score",
    "calculate_net_worth",
    "calculate_simple_return",
    "calculate_twr",
    "calculate_xirr",
]
