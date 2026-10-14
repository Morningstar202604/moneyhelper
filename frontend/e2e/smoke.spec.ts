import { test, expect } from "@playwright/test";

/**
 * 冒烟测试（v2 对话主导布局）：品牌可见、对话是默认入口、数据浮层 / 设置 / 主题可达。
 * 依赖 global-setup 已种入演示数据；语言固定 zh-CN（playwright.config.ts locale）。
 */

test.describe("应用启动 & 冒烟", () => {
  test("首屏加载品牌 + 对话输入框", async ({ page }) => {
    await page.goto("/");
    // 品牌：侧栏 logo 按钮（小满 + 标语）
    await expect(page.getByText("小满").first()).toBeVisible();
    await expect(page.getByText("记一笔，问一句").first()).toBeVisible();
    // 对话是默认入口：输入框可见
    await expect(page.getByPlaceholder(/问点什么/)).toBeVisible();
  });

  test("侧栏品牌按钮打开总览浮层，可关闭", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /小满/ }).first().click();
    // 总览浮层：标题 + 关闭按钮
    await expect(page.getByRole("heading", { name: "总览" })).toBeVisible({ timeout: 10_000 });
    await page.getByRole("button", { name: "关闭" }).first().click();
    await expect(page.getByRole("button", { name: "关闭" })).toHaveCount(0);
  });

  test("打开应用不会新建垃圾会话（会话列表加载竞态回归）", async ({ page, request }) => {
    const api = "http://127.0.0.1:8788";
    const list = async () =>
      ((await (await request.get(`${api}/api/sessions`)).json()).sessions ?? []) as unknown[];
    let sessions = await list();
    if (sessions.length === 0) {
      // 全新库场景：先自建一个会话，再验证「打开应用不会额外新建」
      await request.post(`${api}/api/sessions`, { data: {} });
      sessions = await list();
    }
    const before = sessions.length;
    await page.goto("/");
    // 等首屏初始化（bootstrap + 会话列表）稳定
    await expect(page.getByPlaceholder(/问点什么/)).toBeVisible({ timeout: 10_000 });
    await page.waitForTimeout(1200);
    expect((await list()).length).toBe(before);
  });

  test("设置页能打开，看到语言切换与 AI 入口", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "设置" }).first().click();
    await expect(page.getByRole("button", { name: "关闭" })).toBeVisible();
    await expect(page.getByText("AI 回答").first()).toBeVisible();
    await expect(page.getByText("偏好").first()).toBeVisible();
  });

  test("明暗主题切换修改 html 类名", async ({ page }) => {
    await page.goto("/");
    const html = page.locator("html");
    const before = await html.getAttribute("class");
    // Theme button aria-label = 切换明暗（icon only）
    await page.getByRole("button", { name: "切换明暗" }).click();
    await page.waitForTimeout(200);
    const after = await html.getAttribute("class");
    expect(before !== after).toBeTruthy();
  });

  test("切换品牌主题色即时生效并可恢复默认", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "设置" }).first().click();
    const primaryVar = () =>
      page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--primary").trim());

    // 选「麦金」：--primary 变为预设明色值
    await page.getByRole("radio", { name: "麦金" }).click();
    await expect.poll(primaryVar).toBe("38 78% 45%");

    // 恢复默认：变量回落 index.css 墨绿
    await page.getByRole("radio", { name: "墨绿（默认）" }).click();
    await expect.poll(primaryVar).toBe("168 76% 24%");
  });
});
