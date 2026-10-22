"""限流 IP 归一化回归：同一客户端的 IPv4/IPv6 写法必须共用一份配额。

背景：uvicorn 双栈监听时 client.host 可能是 ::1，而 curl/浏览器走 IPv4 是
127.0.0.1。按原始字符串建桶 = 同一来源可拿两份配额，等于限流可绕过。
"""

from __future__ import annotations

import pytest
from app.middleware import _normalize_ip


@pytest.mark.parametrize("raw", ["::1", "0:0:0:0:0:0:0:1", "localhost", "LOCALHOST"])
def test_loopback_variants_normalize(raw: str) -> None:
    assert _normalize_ip(raw) == "127.0.0.1"


def test_ipv4_mapped_ipv6_normalizes() -> None:
    assert _normalize_ip("::ffff:127.0.0.1") == "127.0.0.1"
    assert _normalize_ip("::ffff:192.168.1.9") == "192.168.1.9"


def test_public_ip_unchanged() -> None:
    assert _normalize_ip("8.8.8.8") == "8.8.8.8"
    assert _normalize_ip("2001:db8::1") == "2001:db8::1"
