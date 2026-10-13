"""输入护栏：真实日历校验 / 持仓数值校验 / 问答长度与分页限制。

这些脏输入会污染月度统计（趋势/预算/现金流/体检），必须在写入前拦截。
"""

from __future__ import annotations

import pytest
from app import db


@pytest.mark.asyncio
async def test_add_transaction_rejects_fake_calendar_dates(temp_db) -> None:
    for bad in ("2026-13-99", "2026-02-30", "2026-00-10", "2026-1-1", "not-a-date"):
        with pytest.raises(ValueError):
            await db.add_transaction(bad, "x", "其他", -5)


@pytest.mark.asyncio
async def test_add_transaction_rejects_zero_and_nan(temp_db) -> None:
    with pytest.raises(ValueError):
        await db.add_transaction("2026-09-01", "x", "其他", 0)
    with pytest.raises(ValueError):
        await db.add_transaction("2026-09-01", "x", "其他", float("nan"))


@pytest.mark.asyncio
async def test_add_position_rejects_bad_numbers(temp_db) -> None:
    base = {"symbol": "600519", "name": "茅台", "shares": 100, "cost": 1500, "last": 1400}
    for patch in ({"shares": -1}, {"shares": 0}, {"cost": -1}, {"last": -1}, {"fee": -0.5}):
        with pytest.raises(ValueError):
            await db.add_position({**base, **patch})
    ok = await db.add_position(base)
    assert ok["ok"] is True
