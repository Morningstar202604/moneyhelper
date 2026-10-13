"""加密备份单测：PBKDF2+Fernet 往返、口令校验、坏包拒绝。"""

from __future__ import annotations

import pytest
from app import backup


def _sample_export() -> dict:
    return {
        "version": 2,
        "exported_at": "2026-10-01T00:00:00+08:00",
        "transactions": [{"id": 1, "date": "2026-10-01", "item": "咖啡", "category": "餐饮", "amount": -28.0}],
        "positions": [],
        "settings": {"color_scheme": "cn"},
    }


def test_encrypt_decrypt_roundtrip():
    """带口令加密 → 正确口令解密 → 内容一致。"""
    data = _sample_export()
    payload = backup.encrypt_export(data, "test-pass-123")
    assert payload.get("encrypted") is True
    assert "transactions" not in payload  # 加密包不暴露明文明细
    dec = backup.decrypt_export(payload, "test-pass-123")
    assert dec["transactions"] == data["transactions"]
    assert dec["settings"] == data["settings"]


def test_decrypt_wrong_passphrase_rejected():
    """错误口令必须抛错（口令不正确或备份文件已损坏）。"""
    payload = backup.encrypt_export(_sample_export(), "right-pass")
    with pytest.raises(ValueError):
        backup.decrypt_export(payload, "wrong-pass")


def test_decrypt_tampered_payload_rejected():
    """篡改密文/结构应被拒绝，不返回部分数据。"""
    payload = backup.encrypt_export(_sample_export(), "pass-1")
    payload["payload"] = payload["payload"][:-4] + "AAAA"
    with pytest.raises(ValueError):
        backup.decrypt_export(payload, "pass-1")
