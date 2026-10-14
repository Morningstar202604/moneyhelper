import { describe, expect, it } from "vitest";
import { presetCss } from "./theme";

describe("presetCss（品牌主题色变量注入）", () => {
  it("麦金预设包含明暗两套主色变量", () => {
    const css = presetCss("wheat");
    expect(css).toContain(":root");
    expect(css).toContain(".dark");
    expect(css).toContain("--primary");
    // 明色主色 = brand.ts 麦金 light
    expect(css).toContain("38 78% 45%");
  });

  it("default 与未知 id 均返回空串（回落 index.css 默认墨绿主题）", () => {
    expect(presetCss("default")).toBe("");
    expect(presetCss("nope")).toBe("");
  });
});
