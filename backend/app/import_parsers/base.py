"""导入解析器抽象基类与数据类。

所有解析器（通用 CSV / 微信 / 支付宝）继承 TransactionParser，
实现 parse(csv_text) → ParseResult 单一入口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date


# ---------------------------------------------------------------------------
# 纯数据：解析产物
# ---------------------------------------------------------------------------

@dataclass
class ParsedTransaction:
    """一行解析后的交易记录。

    amount 约定：正数 = 收入，负数 = 支出（与 db.add_transaction 同口径）。
    """
    date: str           # YYYY-MM-DD
    amount: float       # 正=收入, 负=支出
    category: str       # 分类名
    item: str           # 项目 / 备注（截断到 80 字符以内以匹配 DB 字段）
    account: str = ""   # 来源账户（卡号/平台名，可为空）
    raw: dict = field(default_factory=dict)  # 原始行数据（审计用）


@dataclass
class ParseResult:
    """一次解析的完整产物。"""
    transactions: list[ParsedTransaction] = field(default_factory=list)
    total_income: float = 0.0
    total_expense: float = 0.0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def recalc_totals(self) -> None:
        """重算总额（在子类修改 transactions 后调用）。"""
        self.total_income = round(
            sum(t.amount for t in self.transactions if t.amount > 0), 2
        )
        self.total_expense = round(
            sum(t.amount for t in self.transactions if t.amount < 0), 2
        )

    def to_preview(self) -> dict:
        """序列化为前端预览 JSON。"""
        return {
            "transactions": [
                {
                    "date": t.date,
                    "amount": t.amount,
                    "category": t.category,
                    "item": t.item,
                    "account": t.account,
                }
                for t in self.transactions
            ],
            "summary": {
                "total_income": self.total_income,
                "total_expense": self.total_expense,
                "count": len(self.transactions),
                "skipped": self.skipped,
            },
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# 工具函数（子类可复用）
# ---------------------------------------------------------------------------

def _is_real_date(d: str) -> bool:
    """YYYY-MM-DD 字符串且日历真实（挡 2026-13-45 等）。"""
    try:
        date.fromisoformat(d)
    except ValueError:
        return False
    return True


def _parse_date(v: str) -> str | None:
    """常见日期格式 → YYYY-MM-DD；无法解析返回 None。"""
    import re

    m = re.search(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})", v)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # MM-DD（缺年份）
    m = re.search(r"\b(\d{1,2})[-/.](\d{1,2})\b", v)
    if m:
        y = date.today().year
        return f"{y}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return None


def _parse_amount(v: str) -> float | None:
    """从字符串提取第一个合法数字金额。

    - 支持千分位逗号：1,234.56
    - 支持人民币符号 / 前导 +/-
    - 找不到 → None
    """
    import re

    if not v:
        return None
    # 剥掉货币符号 / 空格，保留数字 / 点 / 逗号 / 负号
    cleaned = re.sub(r"[¥￥\s]", "", v.strip())
    m = re.search(r"[+-]?\d[\d,]*\.?\d*", cleaned)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _detect_encoding(raw: bytes) -> str:
    """检测字节流的编码：优先 UTF-8，失败则回退 GBK。

    不依赖 chardet（零外部依赖），对账单 CSV 足够。
    若两种都失败则抛出 CSVEncodingError。
    """
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            raw.decode(enc)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
    raise CSVEncodingError("无法识别文件编码（需为 UTF-8 或 GBK）")


# ---------------------------------------------------------------------------
# 自定义异常
# ---------------------------------------------------------------------------

class CSVEncodingError(ValueError):
    """编码无法识别时抛出。"""
    pass


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------

class TransactionParser(ABC):
    """解析器基类。子类必须实现 parse()，可选覆盖来源描述信息。"""

    # -- 子类可选覆盖的元信息 -----------------------------------------------

    @classmethod
    def label(cls) -> str:
        """展示名：'微信' / '支付宝' / '通用 CSV' 等。"""
        return "通用 CSV"

    @classmethod
    def description(cls) -> str:
        """一行说明。"""
        return "自动识别表头的通用 CSV 解析器。"

    @classmethod
    def sample_columns(cls) -> list[str]:
        """示例列名（前端展示用）。"""
        return ["日期", "金额", "分类", "备注"]

    # -- 核心接口 ------------------------------------------------------------

    @abstractmethod
    def parse(self, csv_text: str, **kwargs: object) -> ParseResult:
        """解析 CSV 文本，返回解析结果（不访问数据库）。"""
        ...

    # -- 通用工具：子类可直接使用 -------------------------------------------

    @staticmethod
    def _safe_item(item: str) -> str:
        return (item or "未命名")[:80]

    @staticmethod
    def _safe_category(cat: str) -> str:
        return (cat or "其他")[:20]
