import { test, expect } from "@playwright/test";

/**
 * 移动端适配回归：抽屉导航、输入框可见性、无横向溢出、触摸目标。
 * 用真实移动视口（iPhone SE 是最窄的常见尺寸，最容易暴露布局问题）。
 */

// 只装了 Chromium（webkit 未安装，CI 也不跑 webkit）。
// 用 Chromium + iPhone SE 的视口尺寸复现最窄场景；UA 不伪装成 Safari，
// 因为我们验证的是布局与交互，不是 Safari 特性差异。
test.use({
  viewport: { width: 375, height: 667 },
  hasTouch: true,
  isMobile: true,
});

test.describe("移动端布局", () => {
  test("首屏：输入框完整可见，无横向溢出", async ({ page }) => {
    await page.goto("/");
    const input = page.locator("textarea").first();
    await expect(input).toBeVisible({ timeout: 20_000 });

    // 输入框不能被视口底部裁掉（iOS 地址栏/安全区的典型问题）
    const box = await input.boundingBox();
    const vh = page.viewportSize()!.height;
    expect(box).not.toBeNull();
    expect(box!.y + box!.height).toBeLessThanOrEqual(vh + 1);

    // 横向溢出会让页面能左右拖动，移动端体验极差
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1,
    );
    expect(overflow).toBe(false);
  });

  test("抽屉：打开、背景锁滚动、遮罩关闭、Esc 关闭", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("textarea").first()).toBeVisible({ timeout: 20_000 });

    // 桌面侧栏在移动端隐藏，导航只能靠顶栏菜单
    const navBtn = page.locator('button[aria-label="会话"]').first();
    await expect(navBtn).toBeVisible();
    await navBtn.click();

    const dialog = page.locator('[role="dialog"][aria-modal="true"]');
    await expect(dialog).toBeVisible();
    // 抽屉打开时背景不该跟着滚
    expect(await page.evaluate(() => document.body.style.overflow)).toBe("hidden");
    // 会话入口与部门入口都在
    await expect(page.locator('button[aria-label="财务部门"]').first()).toBeVisible();

    // 点遮罩关闭（点抽屉右侧空白区域）
    await page.mouse.click(370, 400);
    await expect(dialog).not.toBeVisible();
    expect(await page.evaluate(() => document.body.style.overflow)).not.toBe("hidden");

    // Esc 也能关
    await navBtn.click();
    await expect(dialog).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
  });

  test("部门面板在移动端全屏可用", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("textarea").first()).toBeVisible({ timeout: 20_000 });
    await page.locator('button[aria-label="会话"]').first().click();
    await page.locator('button[aria-label="财务部门"]').first().click();

    // 面板标题与派工输入可见
    await expect(page.getByText("一句话派工，四部门并行取数")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByLabel("比如：盘一下上季度")).toBeVisible();

    // 移动端面板应占满宽度（SidePanel 在 <md 为 w-full）
    const panel = page.locator('[role="complementary"]').first();
    const box = await panel.boundingBox();
    const vw = page.viewportSize()!.width;
    expect(box!.width).toBeGreaterThanOrEqual(vw - 1);
  });
});
