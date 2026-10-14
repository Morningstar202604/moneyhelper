import { test, expect } from "@playwright/test";

/**
 * 数据浮层（v2：对话主导，数据按需弹出）：总览种子数据 + 从对话 chip 跳转持仓。
 * 依赖 global-setup 已种入演示数据（贵州茅台 / 沪深300ETF 等）。
 */

test.describe("数据浮层", () => {
  test("总览浮层包含资产相关文案（种子数据）", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /小满/ }).first().click();
    await expect(page.getByRole("heading", { name: "总览" })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("资产分布").first()).toBeVisible();
    // 净值卡：负债明细可见（dict 契约的前端消费回归）
    await expect(page.getByText("信用卡分期").first()).toBeVisible({ timeout: 10_000 });
  });

  test("从对话跳转持仓浮层：种子持仓可见", async ({ page }) => {
    // 已接入模型的机器上该问答走 agent 路径，给足超时
    test.setTimeout(60_000);
    await page.goto("/");
    const field = page.getByPlaceholder(/问点什么/);
    await field.fill("我的持仓怎么样");
    await field.press("Enter");
    // 确定性/模型回答都带「去持仓页」chip
    await page.getByRole("button", { name: "去持仓页" }).first().click({ timeout: 45_000 });
    await expect(page.getByText(/贵州茅台/).first()).toBeVisible({ timeout: 15_000 });
  });
});
