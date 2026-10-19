"""财务部门模式的工单模型（M3.1）。

## 为什么从 dataclass 换成 pydantic

原来的 `@dataclass WorkOrder` 只承载"部门 + 任务 + 状态"，没有任何约束：
部门名拼错、任务为空、状态写成任意字符串都能构造出来，错误要到执行阶段才暴露。
而 M3.2 的 LLM 派工要直接产出工单数组——模型输出的东西必须严格校验，
否则一个拼错的部门名会让整轮派工静默少一个部门。

pydantic 在这里承担三个职责：
1. **类型约束**：dept / status 是 Literal，非法值直接拒绝
2. **模型输出校验**：LLM 产出的 JSON 用 `WorkOrder.model_validate` 卡一遍
3. **token 预算**：每个工单带 `budget_tokens`，防止单个部门吃掉整轮预算

## 结构化指标（对账的前提）

M3.4 要求"数字交叉对账"：会计部报的支出总额与记账部报的必须一致。
纯文本输出无法可靠对账（正则抠数字太脆），所以每个部门除了 `output`
文本外还产出 `metrics`（如 `{"expense": 21265.0, "income": 24800.0}`）。
秘书按 key 比对，不一致就标记冲突并指向两个部门。
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Dept = Literal["bookkeeping", "accounting", "risk", "invest"]
OrderStatus = Literal["pending", "running", "done", "failed", "rejected"]

DEPARTMENTS: tuple[Dept, ...] = ("accounting", "risk", "invest", "bookkeeping")

DEPT_TITLES: dict[str, str] = {
    "accounting": "会计部",
    "risk": "风控部",
    "invest": "投资部",
    "bookkeeping": "记账部",
}


class WorkOrder(BaseModel):
    """一张工单：谁做什么、能用哪些工具、最多花多少 token。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    dept: Dept
    task: str = Field(..., min_length=1, max_length=200)
    tools_allowed: list[str] = Field(default_factory=list)
    budget_tokens: int = Field(4000, ge=100, le=100_000)
    status: OrderStatus = "pending"
    output: str = ""
    error: str = ""
    # 结构化指标：秘书交叉对账的依据（文本比对不可靠）
    metrics: dict[str, float] = Field(default_factory=dict)
    # 实际消耗（M3.3 token 预算的执行结果）
    tokens_used: int = Field(0, ge=0)

    @field_validator("task")
    @classmethod
    def _task_not_blank(cls, v: str) -> str:
        """任务描述不能只有空白：空白任务意味着这次派工没有实质内容。"""
        if not v.strip():
            raise ValueError("task 不能为空")
        return v.strip()

    def over_budget(self) -> bool:
        return self.tokens_used > self.budget_tokens


class WorkOrderDraft(BaseModel):
    """LLM 派工的输出形态：只包含模型该决定的部分。

    模型不该决定 id / status / output / metrics —— 那些是运行时状态。
    单独定义这个模型，避免模型误传运行时字段（extra="forbid" 会直接拒绝）。
    """

    model_config = ConfigDict(extra="forbid")

    dept: Dept
    task: str = Field(..., min_length=1, max_length=200)
    tools_allowed: list[str] = Field(default_factory=list)
    budget_tokens: int = Field(4000, ge=100, le=100_000)


class DispatchPlan(BaseModel):
    """LLM 一次结构化输出：若干工单（M3.2 的产出形态）。"""

    model_config = ConfigDict(extra="forbid")

    orders: list[WorkOrderDraft] = Field(..., min_length=1, max_length=len(DEPARTMENTS))

    @field_validator("orders")
    @classmethod
    def _unique_depts(cls, v: list[WorkOrderDraft]) -> list[WorkOrderDraft]:
        """同一部门在一轮派工里只出现一次。

        重复部门意味着模型把同一件事派了两遍，执行时会重复取数并让对账
        出现"自己跟自己冲突"的假象。
        """
        seen = [o.dept for o in v]
        if len(seen) != len(set(seen)):
            raise ValueError("同一部门不能在一轮派工中出现多次")
        return v


def to_orders(plan: DispatchPlan) -> list[WorkOrder]:
    """把 LLM 派工计划转成可执行工单。"""
    return [
        WorkOrder(
            dept=o.dept,
            task=o.task,
            tools_allowed=list(o.tools_allowed),
            budget_tokens=o.budget_tokens,
        )
        for o in plan.orders
    ]


def order_to_dict(o: WorkOrder) -> dict[str, Any]:
    """工单的可序列化形态（供 SSE 事件与 API 返回，不含内部运行时字段）。"""
    return {
        "id": o.id,
        "dept": o.dept,
        "task": o.task,
        "status": o.status,
        "metrics": o.metrics,
        "tokens_used": o.tokens_used,
        "budget_tokens": o.budget_tokens,
        "error": o.error,
    }
