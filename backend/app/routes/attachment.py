"""附件：上传（multipart）/ 列出 / 删除。

从 routes/system.py 拆出（M1.4 收尾）：原文件把 9 个互不相关的域塞在一起，
任何一个域的改动都要在 500+ 行里定位。
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import db

router = APIRouter()


# ---------------------------------------------------------------------------
# 附件（P2 能力扩展）：上传 / 列出 / 删除
# ---------------------------------------------------------------------------


@router.get("/api/attachments")
async def attachments(limit: int = 50) -> dict:
    return {"attachments": await db.list_attachments(limit)}


@router.post("/api/attachments")
async def upload_attachment(request: Request) -> dict:
    """上传附件（multipart/form-data，字段 file）。文本/CSV 直接提取，PDF 走 pypdf（有则用）。"""
    try:
        form = await request.form()
    except Exception as exc:  # noqa: BLE001 — 表单解析失败给可读错误
        return JSONResponse({"error": f"表单解析失败：{exc}"}, status_code=400)
    upload = form.get("file")
    if upload is None or not hasattr(upload, "filename"):
        return JSONResponse({"error": "缺少 file 字段"}, status_code=400)
    filename = str(upload.filename or "未命名")
    raw = await upload.read()
    size = len(raw)
    if size > 2 * 1024 * 1024:
        return JSONResponse({"error": "附件过大（最多 2MB）"}, status_code=400)
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        text = ""
    lower = filename.lower()
    kind = "csv" if lower.endswith(".csv") else "text"
    if not text.strip():
        return JSONResponse(
            {"error": "无法读取该文件内容（仅支持文本/CSV）"}, status_code=400
        )
    out = await db.add_attachment(filename, kind, size, text)
    return out


@router.delete("/api/attachments/{att_id}")
async def remove_attachment(att_id: int) -> dict:
    return await db.delete_attachment(att_id)
