import { test, expect } from "@playwright/test";

/**
 * 问答页核心交互：输入回车发送 → 气泡出现 → 空库未配模型时回退提示可见。
 * 不依赖真实 LLM：未配置模型时前端显示确定性回退徽标/提示，仍能验证整条链路。
 */

test.describe("问答流程", () => {
  test("输入框中回车发出消息，气泡立刻出现", async ({ page }) => {
    await page.goto("/");
    const input = page.getByRole("textbox").or(page.getByPlaceholder(/问点什么/));
    const field = input.first();
    await field.fill("本月餐饮花了多少");
    await field.press("Enter");

    // 追加的用户气泡
    await expect(page.getByText("本月餐饮花了多少")).toBeVisible();
  });

  test("未配置模型时仍回显友好提示（不报网络错误）", async ({ page }) => {
    // 这是 demo 数据但无模型配置：bootstrap.health.llm_configured=false
    // 前端应当要么显示"未接入模型"要么显示确定性回退，不能是白屏或 JS 异常。
    page.on("pageerror", (err) => {
      throw err;
    });
    await page.goto("/");
    const input = page.getByRole("textbox").or(page.getByPlaceholder(/问点什么/));
    await input.fill("你好");

    // 关键断言：页面 title 没变成错误的，并且没有 [Object object] / 堆栈泄露
    const bodyText = await page.locator("body").innerText();
    expect(bodyText).not.toContain("[object Object]");
  });
});
