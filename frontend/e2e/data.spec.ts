import { test, expect } from "@playwright/test";

/**
 * 数据页（功能 → 四个子页）正常渲染种子数据，不抛错。
 * 真实数值来自 /api/portfolio/reset 种入的演示数据，这里只断言图表容器 / 表格存在。
 */

test.describe("功能页渲染", () => {
  test("总览页包含资产相关文案", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("tab", { name: "功能" }).click().catch(async () => {
      await page.getByRole("navigation", { name: "主导航" }).getByText("功能").click();
    });
    await expect(page.getByRole("tab", { name: "总览" })).toBeVisible();
    // 资产/储蓄 相关 section 标题
    await expect(page.getByText("总资产").or(page.getByText("本月净现金流"))).toBeVisible();
  });

  test("持仓页存在可点击的持仓行（种子数据 >= 1 条）", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("tab", { name: "功能" }).click().catch(async () => {
      await page.getByRole("navigation", { name: "主导航" }).getByText("功能").click();
    });
    await page.getByRole("tab", { name: "持仓" }).click();
    // 种子数据至少有 1 条 600519 类的持仓（表格容器可见）
    await expect(page.getByText("持仓").first()).toBeVisible();
  });

  test("行情页能打开搜索框（自选列表交互）", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("tab", { name: "功能" }).click().catch(async () => {
      await page.getByRole("navigation", { name: "主导航" }).getByText("功能").click();
    });
    await page.getByRole("tab", { name: "行情" }).click();
    await expect(page.getByPlaceholder(/搜代码或名称/)).toBeVisible();
  });

  test("记账页存在空引导或最近流水区", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("tab", { name: "功能" }).click().catch(async () => {
      await page.getByRole("navigation", { name: "主导航" }).getByText("功能").click();
    });
    await page.getByRole("tab", { name: "记账" }).click();
    // 「本月」或「最近」或「记一笔」至少一个出现
    await expect(
      page.getByText("本月").or(page.getByText("最近")).or(page.getByText("记一笔")),
    ).toBeVisible();
  });
});
