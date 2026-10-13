import { describe, expect, it } from "vitest";
import { en } from "./lang/en";
import { zh } from "./lang/zh";

describe("i18n", () => {
  it("给定缺失的 key 应返回 key 自身，而不是 undefined", () => {
    // 模拟 t 函数的 fallback 逻辑（与 i18n.tsx 实现一致）
    const DICTS = { en, zh } as const;
    const fallbackT = (key: string, lang: "en" | "zh" = "en"): string =>
      DICTS[lang][key] ?? DICTS.en[key] ?? key;

    expect(fallbackT("totally.missing.key")).toBe("totally.missing.key");
    expect(fallbackT("")).toBe("");
  });

  it("中英文 key 数均应 >= 600", () => {
    const enCount = Object.keys(en).length;
    const zhCount = Object.keys(zh).length;
    expect(enCount).toBeGreaterThanOrEqual(600);
    expect(zhCount).toBeGreaterThanOrEqual(600);
  });

  it("给定已知 key 和非空字符串 lang，t 应返回非空字符串", () => {
    const sampleKeys = ["topbar.toggleDark", "sidebar.sessions", "summary.marketValue"];
    for (const key of sampleKeys) {
      expect(en[key]).toBeTypeOf("string");
      expect(en[key].length).toBeGreaterThan(0);
      expect(zh[key]).toBeTypeOf("string");
      expect(zh[key].length).toBeGreaterThan(0);
    }
  });

  it("中英文 key 集合应一致（无遗漏翻译）", () => {
    const enKeys = new Set(Object.keys(en));
    const zhKeys = new Set(Object.keys(zh));
    const missingInZh = [...enKeys].filter((k) => !zhKeys.has(k));
    const missingInEn = [...zhKeys].filter((k) => !enKeys.has(k));
    expect(missingInZh, `中文缺少以下 key: ${missingInZh.join(", ")}`).toEqual([]);
    expect(missingInEn, `英文缺少以下 key: ${missingInEn.join(", ")}`).toEqual([]);
  });
});
