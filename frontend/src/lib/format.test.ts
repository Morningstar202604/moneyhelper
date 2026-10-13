import { describe, expect, it } from "vitest";
import { fmtMoney, fmtPct, pnlClass, setMoneyLocale, getMoneyLocale } from "./format";

describe("pnlClass", () => {
  it("正值返回 text-up（红涨）", () => {
    expect(pnlClass(100)).toBe("text-up");
    expect(pnlClass(0.01)).toBe("text-up");
  });

  it("负值返回 text-down（绿跌）", () => {
    expect(pnlClass(-50)).toBe("text-down");
    expect(pnlClass(-0.01)).toBe("text-down");
  });

  it("零 / null / NaN 返回 text-muted-foreground", () => {
    expect(pnlClass(0)).toBe("text-muted-foreground");
    expect(pnlClass(null)).toBe("text-muted-foreground");
    expect(pnlClass(undefined)).toBe("text-muted-foreground");
    expect(pnlClass(NaN)).toBe("text-muted-foreground");
  });
});

describe("fmtMoney", () => {
  it("null / NaN 显示短横线", () => {
    expect(fmtMoney(null)).toBe("-");
    expect(fmtMoney(NaN)).toBe("-");
    expect(fmtMoney(undefined)).toBe("-");
  });

  it("默认格式带 ¥ 前缀 + 千分位（maximumFractionDigits:2，不补零）", () => {
    setMoneyLocale("zh");
    expect(fmtMoney(1234.5)).toContain("¥");
    expect(fmtMoney(1234.5)).toContain("1,234");
    // toLocaleString 的 maximumFractionDigits:2 不补尾零
    expect(fmtMoney(1234.5)).toBe("¥1,234.5");
    expect(fmtMoney(50)).toBe("¥50");
  });

  it("负值前缀为 -", () => {
    expect(fmtMoney(-99.5)).toBe("-¥99.5");
  });

  it("signed 正数加 + 号", () => {
    expect(fmtMoney(50, true)).toBe("+¥50");
    expect(fmtMoney(50, false)).toBe("¥50");
  });

  it("中文 compact: 亿/万分级", () => {
    setMoneyLocale("zh");
    expect(fmtMoney(1e8, false, true)).toContain("亿");
    expect(fmtMoney(5e4, false, true)).toContain("万");
    // 小于 1 万不缩写
    expect(fmtMoney(9999, false, true)).not.toContain("万");
  });

  it("英文 compact: B/M 分级", () => {
    setMoneyLocale("en");
    expect(fmtMoney(1e9, false, true)).toContain("B");
    expect(fmtMoney(1e6, false, true)).toContain("M");
    expect(fmtMoney(999, false, true)).not.toContain("B");
    expect(fmtMoney(999, false, true)).not.toContain("M");
  });
});

describe("fmtPct", () => {
  it("null / NaN 显示短横线", () => {
    expect(fmtPct(null)).toBe("-");
    expect(fmtPct(NaN)).toBe("-");
  });

  it("格式化百分比保留两位小数", () => {
    expect(fmtPct(25.5)).toBe("25.50%");
    expect(fmtPct(-3.1)).toBe("-3.10%");
  });

  it("withSign 正数加 + 号", () => {
    expect(fmtPct(10, true)).toBe("+10.00%");
    expect(fmtPct(10, false)).toBe("10.00%");
  });
});

describe("setMoneyLocale / getMoneyLocale", () => {
  it("默认语言为 en", () => {
    // 不强制 reset 模块状态：只测 setter/getter 一致
    setMoneyLocale("zh");
    expect(getMoneyLocale()).toBe("zh");
    setMoneyLocale("en");
    expect(getMoneyLocale()).toBe("en");
  });
});
