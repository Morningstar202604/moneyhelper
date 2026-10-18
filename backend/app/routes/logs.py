"""运行日志查看与清空。

从 routes/system.py 拆出（M1.4 收尾）：原文件把 9 个互不相关的域塞在一起，
任何一个域的改动都要在 500+ 行里定位。
"""

from __future__ import annotations

from fastapi import APIRouter

from ..logging_utils import clear_logs, read_log_lines
from ..logging_utils import get_logger as _get_logger

log = _get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# 日志查看接口
# ---------------------------------------------------------------------------


@router.get("/api/logs")
async def get_logs(limit: int = 200) -> dict:
    """返回日志文件最近 limit 行（从尾部），供前端日志页使用。"""
    lines = read_log_lines(min(max(1, limit), 1000))
    return {"lines": lines, "total": len(lines)}


@router.post("/api/logs/clear")
async def clear_logs_endpoint() -> dict:
    """清空日志文件，返回清空前行数。"""
    cleared = clear_logs()
    log.info("logs cleared manually (%d lines removed)", cleared)
    return {"ok": True, "cleared_lines": cleared}
