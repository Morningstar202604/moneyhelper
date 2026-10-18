"""系统域聚合入口（M1.4 收尾拆分后的门面）。

历史上这里是 534 行的「杂物间」：认证、健康、指标、引导、记忆、反思、审计、
附件、导出、晨报、调度、日志、Agent 配置 9 个互不相关的域塞在一个文件里。
现已按域拆成独立模块，本文件只负责：

1. 把各子路由合并成一个 router（保持 main.py 的 include 次数与顺序不变）
2. re-export 历史符号，供 main.py 的兼容别名段与测试直接引用

子模块：
- routes/auth.py        注册 / 登录 / 当前用户 / 用户数
- routes/status.py      健康 / 指标 / bootstrap / 模型目录
- routes/memory.py      长期记忆 + 经验库（reflections）
- routes/audit.py       审计日志
- routes/attachment.py  附件上传 / 列出 / 删除
- routes/export.py      数据导出 / 备份恢复 / CSV 导出
- routes/reports.py     晨报 / 调度器 / 定时产出收件箱
- routes/logs.py        运行日志
- routes/agentcfg.py    Agent 配置 / 技能触发 / AI 生成
"""

from __future__ import annotations

from fastapi import APIRouter

from .agentcfg import router as agentcfg_router
from .attachment import router as attachment_router
from .audit import router as audit_router
from .auth import router as auth_router
from .export import router as export_router
from .logs import router as logs_router
from .memory import router as memory_router
from .reports import router as reports_router
from .status import router as status_router

router = APIRouter()

# 合并顺序与原 system.py 中的定义顺序一致：OpenAPI 展示顺序不变，
# 也避免新增路由意外遮蔽既有同名路径。
router.include_router(auth_router)
router.include_router(status_router)
router.include_router(memory_router)
router.include_router(audit_router)
router.include_router(attachment_router)
router.include_router(export_router)
router.include_router(reports_router)
router.include_router(logs_router)
router.include_router(agentcfg_router)

# ---------------------------------------------------------------------------
# 兼容 re-export：main.py 的过渡别名段与测试直接引用这些处理函数
# ---------------------------------------------------------------------------

from .agentcfg import (  # noqa: E402,F401
    generate_agent_config,
    get_agent_config,
    run_skill_now,
    update_agent_config,
)
from .memory import (  # noqa: E402,F401
    clear_memory,
    clear_reflections,
    create_memory,
    create_reflection,
    forget_memory,
    memory_list,
    reflections,
    remove_memory,
    resolve_reflection,
    suggest_memories,
)
from .reports import (  # noqa: E402,F401
    generate_report_now,
    reports,
    scheduled_outputs,
    scheduler_status,
)
from .status import (  # noqa: E402,F401
    _enabled_model_list,
    _llm_model,
    bootstrap,
    health,
    metrics,
)

__all__ = [
    "_enabled_model_list",
    "_llm_model",
    "bootstrap",
    "clear_memory",
    "clear_reflections",
    "create_memory",
    "create_reflection",
    "forget_memory",
    "generate_agent_config",
    "generate_report_now",
    "get_agent_config",
    "health",
    "memory_list",
    "metrics",
    "reflections",
    "remove_memory",
    "reports",
    "resolve_reflection",
    "router",
    "run_skill_now",
    "scheduled_outputs",
    "scheduler_status",
    "suggest_memories",
    "update_agent_config",
]
