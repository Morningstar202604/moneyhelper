import { test, expect } from "@playwright/test";

/**
 * 冒烟测试：应用能启动、种子数据加载、核心页面可达、主题/语言切换不报错。
 * 依赖 global-setup 已种入演示数据。
 */

test.describe("应用启动 & 冒烟", () => {
  test("首屏加载出品牌 + 顶部导航", async ({ page }) => {
    await page.goto("/");
    // 品牌名出现在顶栏/首屏任一位置即可
    await expect(page.getByText("小满").first()).toBeVisible();
    await expect(page.getByRole("navigation", { name: "主导航" }).first()).toBeVisible();
  });

  test("问答页是默认入口，输入框可交互", async ({ page }) => {
    await page.goto("/");
    const input = page.getByRole("textbox").or(page.getByPlaceholder(/问点什么/));
    await expect(input.first()).toBeVisible();
  });

  test("切换到功能页并依次显示 4 个子 tab", async ({ page }) => {
    await page.goto("/");

    // 桌面：顶部「功能」tab
    await page.getByRole("tab", { name: "功能" }).click().catch(async () => {
      // 移动端底栏 nav 同名 radio
      await page.getByRole("navigation", { name: "主导航" }).getByText("功能").click();
    });

    // 子 tab：总览 / 持仓 / 行情 / 记账 —— 至少其中一个当前被选中
    await expect(page.getByRole("tab", { name: "总览" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "持仓" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "行情" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "记账" })).toBeVisible();
  });

  test("切换到设置页能看到语言 & AI 入口", async ({ page }) => {
    await page.goto("/");

    // 桌面：右上角齿轮；移动端同样在顶栏
    await page.getByRole("button", { name: "设置" }).click();

    // 设置页的一个明显标题 (AI / i18n key: settings.aiModel / settings.lang)
    await expect(page.getByText("语言")).toBeVisible();
    await expect(page.getByRole("button", { name: "English" }).or(page.getByRole("button", { name: "中文" }))).toBeVisible();
  });

  test("明暗主题切换修改 html 类名", async ({ page }) => {
    await page.goto("/");
    const html = page.locator("html");
    const before = await html.getAttribute("class");
    // Theme button aria-label = "切换明暗" (icon only, no text label)
    await page.getByRole("button", { name: "切换明暗" }).click();
    // Give React a moment to toggle class attribute
    await page.waitForTimeout(200);
    const after = await html.getAttribute("class");
    expect(before !== after || (before ?? "") !== (after ?? "")).toBeTruthy();
  });
});
