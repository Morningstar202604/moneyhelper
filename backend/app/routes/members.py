"""家庭成员管理路由：CRUD + 成员间借贷 + 成员汇总。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import db

router = APIRouter()


# ---------------------------------------------------------------------------
# 成员 CRUD
# ---------------------------------------------------------------------------

@router.get("/api/members")
async def list_members() -> dict:
    """列出所有家庭成员"""
    members = await db.list_members()
    return {"members": members, "count": len(members)}


@router.post("/api/members")
async def add_member(payload: dict) -> dict:
    """添加家庭成员"""
    display_name = (payload or {}).get("display_name", "").strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="成员显示名不能为空")
    role = (payload or {}).get("role", "member")
    if role not in ("owner", "admin", "member", "viewer"):
        raise HTTPException(status_code=400, detail=f"无效角色: {role}")
    avatar_color = (payload or {}).get("avatar_color", "")
    username = (payload or {}).get("username", "")
    mid = await db.member_create(
        display_name=display_name,
        role=role,
        username=username,
        avatar_color=avatar_color,
    )
    member = await db._fetch_member(mid)
    return {"ok": True, "member": member}


@router.put("/api/members/{member_id}")
async def update_member(member_id: int, payload: dict) -> dict:
    """修改成员信息"""
    updates = {}
    p = payload or {}
    if "display_name" in p:
        updates["display_name"] = p["display_name"]
    if "role" in p:
        if p["role"] not in ("owner", "admin", "member", "viewer"):
            raise HTTPException(status_code=400, detail=f"无效角色: {p['role']}")
        updates["role"] = p["role"]
    if "avatar_color" in p:
        updates["avatar_color"] = p["avatar_color"]
    result = await db.member_update(member_id, **updates)
    if not result:
        raise HTTPException(status_code=404, detail="成员不存在")
    return {"ok": True, "member": result}


@router.delete("/api/members/{member_id}")
async def delete_member(member_id: int) -> dict:
    """移除成员"""
    result = await db.member_delete(member_id)
    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="成员不存在")
    # 如果删除的是当前活跃成员，清除 session
    if db.get_active_member() == member_id:
        db.set_active_member(None)
    return {"ok": True, "deleted": result["deleted"]}


# ---------------------------------------------------------------------------
# 当前成员 / 切换
# ---------------------------------------------------------------------------

@router.get("/api/members/me")
async def get_current_member() -> dict:
    """获取当前活跃成员信息"""
    mid = db.get_active_member()
    if mid is None:
        return {"member": None, "mode": "single"}
    member = await db._fetch_member(mid)
    if not member:
        db.set_active_member(None)
        return {"member": None, "mode": "single"}
    return {"member": member, "mode": "family"}


@router.put("/api/members/me/switch")
async def switch_member(payload: dict) -> dict:
    """切换当前活跃成员"""
    p = payload or {}
    member_id = p.get("member_id")
    if member_id is None:
        # 清除活跃成员 → 回到单用户模式
        db.set_active_member(None)
        return {"ok": True, "member": None, "mode": "single"}
    member_id = int(member_id)
    member = await db._fetch_member(member_id)
    if not member:
        raise HTTPException(status_code=404, detail="成员不存在")
    db.set_active_member(member_id)
    return {"ok": True, "member": member, "mode": "family"}


# ---------------------------------------------------------------------------
# 成员间借贷
# ---------------------------------------------------------------------------

@router.get("/api/members/loans")
async def list_loans(settled: bool | None = None) -> dict:
    """列出成员间借贷。settled=true/false 筛选，不传返回全部。"""
    if isinstance(settled, str):
        if settled.lower() == "true":
            settled = True
        elif settled.lower() == "false":
            settled = False
        else:
            settled = None
    # FastAPI may pass as query string
    loans = await db.list_loans(settled=settled)
    members = {m["id"]: m["display_name"] for m in await db.list_members()}
    enriched = []
    for ln in loans:
        enriched.append({
            **ln,
            "from_name": members.get(ln["from_member_id"], ""),
            "to_name": members.get(ln["to_member_id"], ""),
        })
    return {"loans": enriched, "count": len(enriched)}


@router.post("/api/members/loans")
async def create_loan(payload: dict) -> dict:
    """创建成员间借贷"""
    p = payload or {}
    try:
        from_id = int(p.get("from_member_id", 0))
        to_id = int(p.get("to_member_id", 0))
        amount = float(p.get("amount", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="参数格式错误") from None
    note = str(p.get("note", ""))
    currency = str(p.get("currency", "CNY"))
    try:
        lid = await db.loan_create(from_id, to_id, amount, note, currency)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "id": lid}


@router.post("/api/members/loans/{loan_id}/settle")
async def settle_loan(loan_id: int) -> dict:
    """结清一笔借贷"""
    result = await db.loan_settle(loan_id)
    if not result.get("updated"):
        raise HTTPException(status_code=404, detail="借贷不存在")
    return {"ok": True, "settled": True}


@router.delete("/api/members/loans/{loan_id}")
async def delete_loan(loan_id: int) -> dict:
    """删除一笔借贷"""
    result = await db.loan_delete(loan_id)
    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="借贷不存在")
    return {"ok": True, "deleted": True}


# ---------------------------------------------------------------------------
# 成员汇总
# ---------------------------------------------------------------------------

@router.get("/api/members/summary")
async def members_summary() -> dict:
    """每个成员的收支汇总"""
    summary = await db.all_members_summary()
    return {"members": summary, "count": len(summary)}
