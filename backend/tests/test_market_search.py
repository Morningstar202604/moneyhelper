"""行情搜索解析回归：东财 suggest 的响应没有外层 data。

此前按 {"data": {"QuotationCodeTable": ...}} 解析，实际返回是顶层
{"QuotationCodeTable": ...}，导致搜索永远返回空列表（前端显示"没找到"）。
"""

from __future__ import annotations

import httpx
import pytest
from app import main


@pytest.fixture(autouse=True)
async def _temp_db(temp_db):
    """复用 conftest 的临时库：搜索路由仍会经过租户中间件。"""
    yield


@pytest.fixture
async def client(_temp_db):
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8787") as ac:
        yield ac


@pytest.mark.parametrize(
    "payload",
    [
        # 真实返回：顶层就有 QuotationCodeTable
        {
            "QuotationCodeTable": {
                "Data": [
                    {
                        "Code": "600519",
                        "Name": "贵州茅台",
                        "SecurityTypeName": "沪A",
                    }
                ]
            }
        },
        # 兼容旧格式：外面多包一层 data
        {
            "data": {
                "QuotationCodeTable": {
                    "Data": [
                        {
                            "Code": "600519",
                            "Name": "贵州茅台",
                            "SecurityTypeName": "沪A",
                        }
                    ]
                }
            }
        },
    ],
)
async def test_search_parses_both_payload_shapes(client, monkeypatch, payload) -> None:
    from app.routes import market

    async def fake_fetch(kw: str) -> dict:  # noqa: ARG001
        return payload

    monkeypatch.setattr(market, "_fetch_suggest", fake_fetch)
    r = await client.get("/api/search", params={"q": "600519"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert items == [{"symbol": "600519", "name": "贵州茅台", "kind": "股票"}]


async def test_search_empty_query_returns_empty(client) -> None:
    r = await client.get("/api/search", params={"q": "   "})
    assert r.json() == {"items": []}
