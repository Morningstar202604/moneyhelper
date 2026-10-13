"""交易数据导入路由：CSV 上传 → 解析预览 → 确认入账。

鉴权：与主路由共用 verify_api_token 中间件；无 token 时仅本机可用。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

import asyncio

from ..auth import verify_api_token
from .. import db
from ..provenance import record_provenance
from ..import_parsers import (
    get_parser,
    supported_sources,
)
from ..import_parsers.base import ParseResult, ParsedTransaction
from ..csvimport import classify as _auto_classify

log = logging.getLogger(__name__)

# 安全限制
MAX_CSV_BYTES = 10 * 1024 * 1024  # 10 MB

router = APIRouter(dependencies=[Depends(verify_api_token)])


# ---------------------------------------------------------------------------
# 请求 / 响应 Schema
# ---------------------------------------------------------------------------

class CsvPreviewRequest(BaseModel):
    """CSV 预览请求体。

    source: 导入来源（generic / wechat / alipay），默认 generic。
    content: CSV 文本内容（必须是合法 UTF-8 或 GBK 编码的文本）。
    auto_classify: 是否用 nlparse 自动分类（默认 True）。
    """
    source: str = "generic"
    content: str = Field(..., min_length=1, description="CSV 文本内容")
    auto_classify: bool = True

    @validator("content")
    def check_size(cls, v: str) -> str:
        if len(v.encode("utf-8")) > MAX_CSV_BYTES:
            raise ValueError(f"CSV 内容超过 {MAX_CSV_BYTES // 1024 // 1024}MB 上限")
        return v


class CsvConfirmRequest(BaseModel):
    """确认导入请求体。"""
    transactions: list[dict[str, Any]] = Field(..., min_items=1)
    auto_classify: bool = True


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _deduplicate_in_memory(
    transactions: list[ParsedTransaction],
) -> tuple[list[ParsedTransaction], int]:
    """内存中去重（同一批次不允许重复 date + amount + item）。

    返回 (去重后的列表, 去重数量)。
    """
    seen: set[tuple[str, float, str]] = set()
    unique: list[ParsedTransaction] = []
    dup_count = 0
    for t in transactions:
        key = (t.date, t.amount, t.item)
        if key in seen:
            dup_count += 1
            continue
        seen.add(key)
        unique.append(t)
    return unique, dup_count


async def _db_deduplicate(
    transactions: list[ParsedTransaction],
) -> tuple[list[ParsedTransaction], int]:
    """跨会话去重：查询库里是否已存在 (date, amount, item)。

    注意：sqlite 里没有 UNIQUE(date, amount, item) 约束（用户库可能是旧表），
    所以走 SELECT 查询判断而非 INSERT OR IGNORE。
    """
    existing = await db.list_transactions()
    existing_keys: set[tuple[str, float, str]] = set()
    for row in existing:
        existing_keys.add((row["date"], round(row["amount"], 2), row["item"]))

    unique: list[ParsedTransaction] = []
    dup_count = 0
    for t in transactions:
        key = (t.date, round(t.amount, 2), t.item)
        if key in existing_keys:
            dup_count += 1
            continue
        existing_keys.add(key)  # 防同批次后续行重复
        unique.append(t)
    return unique, dup_count


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------

@router.post("/api/import/csv")
async def import_csv_preview(req: CsvPreviewRequest) -> dict:
    """接收 CSV 文本内容，解析并返回预览列表（不写库）。"""
    try:
        parser = get_parser(req.source)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    result: ParseResult = parser.parse(req.content)

    # 自动分类（可选）
    if req.auto_classify:
        for t in result.transactions:
            if t.category in ("", "其他", "未分类"):
                t.category = _auto_classify(t.item) or "其他"

    warnings = list(result.errors)
    if result.skipped:
        warnings.append(f"跳过 {result.skipped} 行（汇总 / 不计收支 / 格式异常）")

    return {
        "source": req.source,
        "preview": result.to_preview(),
        "warnings": warnings,
    }


@router.post("/api/import/csv/confirm")
async def import_csv_confirm(req: CsvConfirmRequest) -> dict:
    """确认导入：将预览阶段的交易写入数据库。

    去重逻辑：
      1. 内存去重（同一批次）；
      2. 数据库去重（与已有记录比较 date+amount+item）。
    """
    # 解析 + 校验
    transactions: list[ParsedTransaction] = []
    validation_errors: list[str] = []

    for idx, item in enumerate(req.transactions, start=1):
        try:
            d = str(item.get("date", "")).strip()
            amt = float(item.get("amount", 0))
            cat = str(item.get("category", "其他")).strip() or "其他"
            label = str(item.get("item", "未命名")).strip() or "未命名"
            account = str(item.get("account", "")).strip()
        except (TypeError, ValueError) as exc:
            validation_errors.append(f"第 {idx} 行参数无效：{exc}")
            continue

        if not d or len(d) != 10:
            validation_errors.append(f"第 {idx} 行：日期格式需 YYYY-MM-DD")
            continue
        if amt == 0:
            validation_errors.append(f"第 {idx} 行：金额不能为 0")
            continue

        transactions.append(
            ParsedTransaction(
                date=d, amount=round(amt, 2), category=cat[:20],
                item=label[:80], account=account[:40],
            )
        )

    if validation_errors:
        return JSONResponse(
            {"error": "参数校验失败", "details": validation_errors},
            status_code=422,
        )

    # 内存去重
    transactions, mem_dup = _deduplicate_in_memory(transactions)
    # DB 去重
    transactions, db_dup = await _db_deduplicate(transactions)

    dup_total = mem_dup + db_dup

    # 批量入账（串行：sqlite 单写者）；自动注入当前活跃成员为 owner
    imported = 0
    db_errors: list[str] = []
    active_member = db.get_active_member()
    for t in transactions:
        try:
            await db.add_transaction(
                date=t.date,
                item=t.item,
                category=t.category,
                amount=t.amount,
                owner_id=active_member,
            )
            imported += 1
        except Exception as exc:
            db_errors.append(f"{t.date} {t.item}：{exc}")
            log.warning("import confirm 写入失败：%s %s: %s", t.date, t.item, exc)

    # 异步记录导入审计
    if imported > 0:
        asyncio.create_task(record_provenance(
            action="import_transactions",
            entity_type="transaction",
            entity_id=f"batch:{imported}_rows",
            before=None,
            after={"imported": imported, "duplicates": dup_total},
            source="api",
            username="system",
        ))

    return {
        "imported": imported,
        "duplicates": dup_total,
        "errors": db_errors,
    }


@router.get("/api/import/templates")
async def import_templates() -> list[dict]:
    """返回支持的导入模板信息（列名、描述）。"""
    return supported_sources()
