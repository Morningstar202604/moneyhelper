"""交易数据导入解析器包：按不同来源（通用 CSV / 微信 / 支付宝）提供统一解析接口。

用法：
    from app.import_parsers import get_parser

    parser = get_parser("wechat")          # or "alipay" / "generic"
    result = parser.parse(csv_text)
    for tx in result.transactions:
        print(tx.date, tx.amount, tx.item)
"""

from __future__ import annotations

from .base import ParseResult, ParsedTransaction, TransactionParser
from .generic_csv import GenericCSVParser
from .wechat import WeChatParser
from .alipay import AlipayParser

# 注册表：来源名称 → 解析器类
_REGISTRY: dict[str, type[TransactionParser]] = {
    "generic": GenericCSVParser,
    "wechat": WeChatParser,
    "alipay": AlipayParser,
}


def get_parser(source: str) -> TransactionParser:
    """按来源名称返回解析器实例。大小写不敏感。"""
    key = (source or "generic").strip().lower()
    cls = _REGISTRY.get(key)
    if cls is None:
        raise ValueError(f"不支持的导入来源：{source}（可选：{', '.join(_REGISTRY)}）")
    return cls()


def supported_sources() -> list[dict]:
    """返回所有支持的来源及说明（供 /api/import/templates 使用）。"""
    return [
        {
            "key": key,
            "label": cls.label(),
            "description": cls.description(),
            "sample_columns": cls.sample_columns(),
        }
        for key, cls in _REGISTRY.items()
    ]


__all__ = [
    "get_parser",
    "supported_sources",
    "TransactionParser",
    "ParsedTransaction",
    "ParseResult",
    "GenericCSVParser",
    "WeChatParser",
    "AlipayParser",
]
