import os
import sys
from pathlib import Path

import pytest

# 测试默认关闭限流，避免高频接口测例触发 429；限流本身由 test_rate_limit.py 显式测
os.environ.setdefault("XIAOMAN_DISABLE_RATE_LIMIT", "1")
os.environ.setdefault("VAULT_PASSPHRASE", "test-passphrase-for-unit-tests-12345")

# 在导入 app 前初始化 vault（test_api.py 使用 ASGITransport 不触发 lifespan → vault 需手动激活）
from app import vault as _vault

_vault.init_master_passphrase("test-passphrase-for-unit-tests-12345")
_vault.activate()

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture
async def temp_db(tmp_path, monkeypatch):
    """临时内存库（test_api.py 自带同语义本地 fixture，此处供其余测试文件复用）。
    生产首启为空账本（不种示例），测试业务需要示例数据，故显式种入。"""
    from app import db

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "wealth.db")
    await db.init_db()
    await db.reset_to_seed()
    yield
    await db.close_db()


@pytest.fixture(autouse=True)
async def _close_agent_checkpoints():
    """每个测试结束释放 LangGraph 磁盘 checkpoint 连接。

    agent_graph 按 event loop 缓存 AsyncSqliteSaver 连接；pytest-asyncio 每个测试
    新建并关闭 loop，若连接不及时关闭，aiosqlite worker 线程会在 loop 关闭后残留，
    导致 pytest 进程退出挂住。teardown 时统一关闭以释放文件锁与线程。
    """
    yield
    try:
        from app import agent_graph
        await agent_graph.close_checkpoints()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _no_real_llm(monkeypatch):
    """默认不触达真实模型：把 llm 配置缓存置为「未配置」，让未显式 mock 的测试走确定性路径。

    开发机 .env 若配了可用模型，llm._config() 会读到真实端点并触网（慢/超时/依赖外网）。
    这里把 _cfg 置为 {}（_config() 返回 None = 未配置），使每个测试默认按「未接入模型」
    运行，只测确定性内核；需要验证 LLM 路径的测试自行 monkeypatch llm_available /
    stream_narrate / run_agent（仍会覆盖本默认）。
    """
    from app import llm

    monkeypatch.setattr(llm, "_cfg", {})
    monkeypatch.setattr(llm, "_client_singleton", None)
