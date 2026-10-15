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

  test("设置区都有 AI 生成入口（预算/规则/晨报/记忆/Agent）", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "设置" }).first().click();

    // 一键建议型：点「生成建议」；Agent 区是"先描述再生成"型：入口为「AI 生成」
    const expectAi = async (section: string, entry: RegExp) => {
      await page.getByText(section, { exact: true }).first().click();
      await expect(page.getByRole("button", { name: entry }).first()).toBeVisible({ timeout: 10_000 });
    };

    await expectAi("预算", /生成建议/);
    await expectAi("账本规则", /生成建议/);
    await expectAi("每日晨报", /生成建议/);
    await expectAi("长期记忆", /生成建议/);
    await expectAi("Agent 与技能", /^AI 生成$/);
  });

  test("技能定时动作：配置时间/星期并立即触发（结果回显）", async ({ page, request }) => {
    const api = "http://127.0.0.1:8788";
    // 自建技能（e2e 库也可能是被复用的研发库：用独立 id + 测试完删除，避免污染）
    const cfg = (await (await request.get(`${api}/api/agent-config`)).json()).config as {
      skills: Record<string, unknown>;
    };
    cfg.skills["e2e_weekly_note"] = {
      name: "E2E 周报提醒",
      description: "每周日晚提醒看持仓",
      enabled: true,
      action: { prompt: "帮我看看这个月的支出", time: "20:00", weekdays: [6] },
    };
    const saveResp = await request.post(`${api}/api/agent-config`, { data: { config: cfg } });
    expect((await saveResp.json()).ok).toBe(true);

    try {
      await page.goto("/");
      await page.getByRole("button", { name: "设置" }).first().click();
      await page.getByText("Agent 与技能", { exact: true }).first().click();

      // 动作徽标显示 周几 + 时间；「立即触发」按钮（aria-label 带技能名）可用
      const runBtn = page.getByRole("button", { name: "立即触发 E2E 周报提醒" });
      await expect(runBtn).toBeVisible({ timeout: 10_000 });
      await expect(page.getByText("周日 20:00").first()).toBeVisible();
      await runBtn.click();

      // 触发结果如实回显（走真实问答管线：确定性兜底即可产生回答）
      await expect(page.getByText("最近一次触发结果")).toBeVisible({ timeout: 30_000 });

      // 触发记录：归档线程可查（含刚触发的一条；标题 + 问题可见）
      await page.getByRole("button", { name: "查看 E2E 周报提醒 的触发记录" }).click();
      await expect(page.getByText(/触发记录（含定时/)).toBeVisible({ timeout: 10_000 });
      await expect(page.getByText("帮我看看这个月的支出").first()).toBeVisible({ timeout: 10_000 });
    } finally {
      // 清理：删除测试技能并保存
      const cfg2 = (await (await request.get(`${api}/api/agent-config`)).json()).config as {
        skills: Record<string, unknown>;
      };
      delete cfg2.skills["e2e_weekly_note"];
      await request.post(`${api}/api/agent-config`, { data: { config: cfg2 } });
    }
  });
});
