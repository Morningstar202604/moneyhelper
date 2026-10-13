"""加密密钥管理系统：DB 内敏感字段加密存储。

架构（简化版 — 废除 DEK 双层）：
- master_passphrase（环境变量 VAULT_PASSPHRASE）绝不落盘/入库
- 每条敏感字段加密时生成独立随机 salt（16 B）
- 加密：PBKDF2(master_pass + per_record_salt, 100k iters) → 32 B key → Fernet(plaintext)
- 存储格式：~<base64(salt)>:<base64(ciphertext)>（前缀 ~ 标记加密态）
- 解密：识别 ~ 前缀 → 拆出 salt → 重新 PBKDF2 → 解密

安全边界：
- 单条 salt 独立 → 一次 PBKDF2 既是最小解密单位
- 主口令丢失 = 已加密字段永久丢失（ui 提示用户重新输入对应 secret）
- 并发安全：asyncio.Lock 保护 DEK lazy init
"""

from __future__ import annotations

import asyncio
import base64
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .logging_utils import get_logger

log = get_logger(__name__)

# PBKDF2 迭代次数：100,000 是 NIST SP 800-132 口径对 app key-wrap 的推荐值的 10 倍。
# 单次 ~30ms（2.4GHz x64），远低于 100ms UX 阈值。
_KDF_ITERS = 100_000
_SALT_LEN = 16
_ENCRYPTED_PREFIX = "~"  # 标记加密态，透明兼容旧明文数据

# 进程内 master passphrase 缓存（仅启动时设一次，内存驻留）
_master_passphrase: str | None = None
_vault_active: bool = False


def _derive_key(passphrase: str, salt: bytes, iters: int = _KDF_ITERS) -> bytes:
    """口令派生 32B 密钥 → url-safe base64（Fernet 接受的格式）。"""
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iters)
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def init_master_passphrase(passphrase: str) -> None:
    """注册主口令（启动入口调用一次）。 passphrase 绝对不落盘。"""
    global _master_passphrase
    if not passphrase or len(passphrase) < 8:
        raise ValueError("主口令至少 8 位")
    _master_passphrase = passphrase
    log.info("vault: master passphrase registered (length=%d)", len(passphrase))


def activate() -> None:
    """标记 vault 可用（寿命入口调用）。"""
    global _vault_active
    if not _master_passphrase:
        log.warning("vault: VAULT_PASSPHRASE 未设置 — 加密功能禁用，敏感字段将拒绝保存")
        return
    _vault_active = True
    log.info("vault: activated (KDF iters=%d)", _KDF_ITERS)


def is_active() -> bool:
    return _vault_active


def master_passphrase() -> str:
    if not _master_passphrase:
        raise RuntimeError("vault 未初始化：未设主口令（VAULT_PASSPHRASE）")
    return _master_passphrase


def _encrypt_sync(plaintext: str, pp: str) -> str:
    """同步加密原语（CPU-bound PBKDF2 + Fernet）：在事件循环线程外执行，避免阻塞 loop。"""
    salt = os.urandom(_SALT_LEN)
    key = _derive_key(pp, salt)
    f = Fernet(key)
    ct = f.encrypt(plaintext.encode("utf-8"))
    salt_b64 = base64.b64encode(salt).decode("ascii")
    ct_b64 = base64.b64encode(ct).decode("ascii")
    return f"{_ENCRYPTED_PREFIX}{salt_b64}:{ct_b64}"


def _decrypt_sync(payload: str, pp: str) -> str:
    """同步解密原语（CPU-bound PBKDF2 + Fernet）：在事件循环线程外执行。"""
    body = payload[len(_ENCRYPTED_PREFIX):]
    salt_b64, ct_b64 = body.split(":", 1)
    salt = base64.b64decode(salt_b64)
    key = _derive_key(pp, salt)
    f = Fernet(key)
    try:
        pt = f.decrypt(base64.b64decode(ct_b64))
    except Exception:
        log.error("vault: 解密失败 — 主口令错误或密文被篡改")
        raise ValueError("主口令不正确或数据已损坏") from None
    return pt.decode("utf-8")


async def encrypt_secret(plaintext: str) -> str:
    """加密敏感字符串 → "~<salt>:<ciphertext>" 格式。

    PBKDF2（CPU-bound）通过 asyncio.to_thread 推入线程池，不阻塞事件循环。
    """
    if not plaintext:
        return ""
    if not _vault_active:
        raise RuntimeError("vault 未激活 — 不能加密字段")

    pp = master_passphrase()
    return await asyncio.to_thread(_encrypt_sync, plaintext, pp)


async def decrypt_secret(payload: str) -> str:
    """解密 "~<salt>:<ciphertext>" → 明文。

    空输入直接返回空。
    无前缀（如旧明文数据）→ 原样返回。
    vault 未激活 → 抛 RuntimeError。
    PBKDF2 通过 asyncio.to_thread 推入线程池，不阻塞事件循环。
    """
    if not payload:
        return ""
    if not payload.startswith(_ENCRYPTED_PREFIX):
        return payload
    if not _vault_active:
        raise RuntimeError("vault 未激活 — 不能解密字段")

    try:
        body = payload[len(_ENCRYPTED_PREFIX):]
        _, _ = body.split(":", 1)
    except ValueError:
        raise ValueError(f"vault: 无法解析加密字段格式（期望 ~<salt>:<ct>， got {payload[:20]!r}）")

    pp = master_passphrase()
    return await asyncio.to_thread(_decrypt_sync, payload, pp)


def reset_cache() -> None:
    """进程退出时清除内存中的 master_passphrase（防核心转储泄露）。"""
    global _master_passphrase, _vault_active
    _master_passphrase = None
    _vault_active = False
