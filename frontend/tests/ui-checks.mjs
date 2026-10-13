/**
 * UI 断言单入口（chat-first 形态）：懒加载边界 3 + 首屏问答 5 + 总览结构与图表 7 + 记账 7 + 设置 11 + 对话框 2 + 问答 2 + 来源徽标 1 + 空数据/空会话 4 + 移动端 5 + 待扣跨月 6 + 应急金态与对照 6。
 * 前置：后端已运行（默认 http://127.0.0.1:8787，可设 WO_BASE）。
 * 运行：node frontend/tests/ui-checks.mjs
 */

import { BASE, launchBrowser, makeChecks, loadPlaywright } from "./_harness.mjs";

const { chromium, devices } = loadPlaywright();
const { checks, check, skip, finish } = makeChecks();
const browser = await launchBrowser({ chromium });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));

// —— 环境前置：断言分两档依赖 —— HAS_DATA 需要有数据，IS_SEED 需要仍是示例数据
// （待扣跨月/应急金对照依赖示例库里那几笔特定流水，用户一旦自己记过账就改用别的门）——
const boot = await (await fetch(BASE + "/api/dashboard")).json();
const HAS_DATA = (boot.positions?.length ?? 0) > 0 || (boot.transactions?.length ?? 0) > 0;
const IS_SEED = boot.source?.seeded === true;
if (!HAS_DATA) {
  console.log("# 当前库为空（无持仓无流水）：依赖数据的断言将标记 SKIP");
} else if (!IS_SEED) {
  console.log("# 当前库为用户数据（非示例）：依赖示例数据的断言将标记 SKIP");
}

// —— index.html 层面：重依赖不进预加载清单 ——
const html = await (await fetch(BASE + "/")).text();
check("index.html 无 echarts modulepreload", !/modulepreload[^>]*echarts/.test(html) && !/echarts[^>]*modulepreload/.test(html));
check("index.html 无 markdown modulepreload", !/modulepreload[^>]*markdown/.test(html) && !/markdown[^>]*modulepreload/.test(html));
const heavyReqs = [];
page.on("request", (r) => {
  if (/echarts.*\.js|markdown.*\.js/i.test(r.url())) heavyReqs.push(r.url());
});

/** 断言统一走中文界面：默认语言已改为 en（wo.lang 缺省即 en），先把语言钉到 zh 再跑既有中文断言。 */
async function initZh(p) {
  await p.goto(BASE, { waitUntil: "domcontentloaded" });
  await p.evaluate(() => localStorage.setItem("wo.lang", "zh"));
  await p.reload({ waitUntil: "networkidle" });
  await p.waitForTimeout(300);
}

/** 页面加载完成后切到总览页（chat-first 下总览不再是首屏） */
async function gotoDashboard(p) {
  await initZh(p);
  await p.locator("nav:visible button", { hasText: "总览" }).first().click();
  await p.waitForTimeout(600);
}

// —— 首屏必须是问答页（chat-first）——
await initZh(page);
check("首屏为问答页（输入框可见）", (await page.locator("textarea[placeholder*='问点什么']").count()) === 1);
const curNav = await page.locator("nav:visible [aria-current='page']").first().innerText().catch(() => "");
check("首屏导航 aria-current 标记为问答", curNav.includes("问答"));
const chatW = await page.evaluate(() => {
  const main = document.querySelector("main");
  const c = main?.firstElementChild?.getBoundingClientRect();
  return c ? Math.round(c.width) : 0;
});
check(`问答内容宽度 >= 700（实际 ${chatW}）`, chatW >= 700);
const phCount = await page.locator("textarea[placeholder*='问点什么']").count();
const ph = phCount > 0 ? await page.locator("textarea[placeholder*='问点什么']").getAttribute("placeholder") : "";
check("输入框 placeholder 不含财务示例", phCount > 0 && !String(ph).includes("钱花哪了"));

// —— 懒加载边界：问答为首屏时 markdown 属本体、echarts 仍须懒加载 ——
check("首屏加载 markdown chunk（问答为默认页）", heavyReqs.some((u) => /markdown/i.test(u)));
check("首屏不加载 echarts chunk", !heavyReqs.some((u) => /echarts/i.test(u)));

// —— AI 接入状态与回答来源徽标 ——
const health = await page.evaluate(() => fetch("/api/health").then((r) => r.json()));
const guideCount = await page.getByText("AI 未接入").count();
check(
  health.llm_configured ? "已接入 AI 时不显示未接入引导" : "未接入 AI 显示引导条",
  health.llm_configured ? guideCount === 0 : guideCount > 0,
);
check(
  health.llm_configured ? "已接入时无需自由问答说明" : "未接入横幅含「自由问答」",
  health.llm_configured ? true : (await page.getByText("自由问答").count()) > 0,
);
const inputBox = page.locator("textarea[placeholder*='问点什么']");
if (phCount > 0) {
  await inputBox.fill("总资产是多少");
  await page.keyboard.press("Enter");
}
try {
  await page.waitForSelector(
    "span.rounded-full:has-text('内置分析'), span.rounded-full:has-text('AI 生成')",
    { timeout: 30000 },
  );
  check("回答带来源徽标（AI 生成/内置分析）", true);
} catch {
  check("回答带来源徽标（AI 生成/内置分析）", false);
}

// —— 总览页：核心结构（统计卡/明细/图表依赖示例数据，空库时走引导态分支）——
await page.locator("nav:visible button", { hasText: "总览" }).first().click();
await page.waitForTimeout(600);
check("导航含总览", (await page.locator("nav:visible button", { hasText: "总览" }).count()) > 0);
check("顶栏无行情来源", !(await page.locator("header").innerText()).includes("东方财富"));
check("导航标记 aria-current", (await page.locator("nav:visible [aria-current='page']").count()) > 0);
if (HAS_DATA) {
  if (IS_SEED) {
    check("示例数据有明示横幅", (await page.getByText("当前显示的是示例数据").count()) > 0);
  } else {
    check("用户数据不显示示例横幅", (await page.getByText("当前显示的是示例数据").count()) === 0);
    skip("示例数据明示横幅", "当前库为用户数据，非示例数据");
  }
  check("总资产卡", (await page.getByText("总资产").count()) > 0);
  check("财务目标卡", (await page.getByText("财务目标").count()) > 0);
  check("体检入口按钮", (await page.locator("button", { hasText: "财务体检" }).count()) > 0);
  await page.locator("button", { hasText: "财务体检" }).first().click();
  await page.waitForTimeout(1200);
  check("体检弹层显示综合评分", (await page.getByText("综合评分").count()) > 0);
  check("体检弹层含维度卡片", (await page.getByText(/资产配置|现金流|负债健康|应急金|目标进度/).count()) > 0);
  await page.keyboard.press("Escape");
  await page.waitForTimeout(300);
  check("体检弹层可关闭", (await page.getByText("综合评分").count()) === 0);
  check("明细分析折叠区", (await page.getByText("明细分析").count()) > 0);
  check("风险横幅", (await page.getByText(/发现 \d+ 项需关注|未发现明显风险项/).count()) > 0);
} else {
  check("空库总览显示引导卡", (await page.getByText("这里还没有你的数据").count()) > 0);
  skip("总资产卡/明细分析/风险横幅", "当前库为空，仪表盘渲染引导态");
}

// —— Radix Tooltip：悬停顶栏图标出现提示 ——
await page.locator("header button[aria-label='切换明暗']").hover();
await page.waitForTimeout(700);
check("顶栏图标悬停有 tooltip", (await page.getByText(/切换(深|浅)色/).count()) > 0);

// —— 展开明细后才加载 echarts 并渲染图表 ——
if (HAS_DATA) {
  await page.getByText("明细分析").click();
  await page.waitForTimeout(2000);
  check("展开明细后加载 echarts chunk", heavyReqs.some((u) => /echarts/i.test(u)));
  check("展开后有 canvas 图表", (await page.locator("details[open] canvas").count()) >= 2);
  check("展开后有持仓明细", (await page.getByText("持仓明细").count()) > 0);
} else {
  skip("echarts 懒加载/图表/持仓明细", "当前库为空，无明细可展开");
}

// —— 记账页 ——
await page.locator("nav:visible button", { hasText: "记账" }).first().click();
await page.waitForTimeout(500);
check("一句话记账输入框", (await page.locator("input[placeholder*='昨天打车']").count()) === 1);
check("快捷动作 5 个", (await page.locator("button", { hasText: /(记支出|记收入|导入账单|管理持仓|添加负债)/ }).count()) >= 5);
check("快捷动作含添加目标", (await page.locator("button", { hasText: "添加目标" }).count()) >= 1);
check("我的账本区", (await page.getByText("我的账本").count()) > 0);
check("账本含订阅 tab", (await page.locator("button", { hasText: /^订阅/ }).count()) > 0);
check("账本含目标 tab", (await page.locator("button", { hasText: /^目标/ }).count()) > 0);
check("支出表单默认收起", (await page.getByText("记一笔支出").count()) === 0);
await page.locator("button", { hasText: "记支出" }).click();
await page.waitForTimeout(300);
check("点记支出后出现表单", (await page.getByText("记一笔支出").count()) > 0);

// —— 目标 tab：进度列表（有数据）或空态引导 ——
await page.locator("button", { hasText: /^目标/ }).first().click();
await page.waitForTimeout(400);
const goalsTxt = await page.locator("main").innerText();
check("目标 tab 有内容", /应急金|买房|目标|建议月存|还没有财务目标/.test(goalsTxt));
check("目标 tab 有进度或空态", /%|还没有财务目标/.test(goalsTxt));

// —— 设置页（分界面导航：入口在侧栏底部，7 个子界面逐个点检）——
await page.locator("aside button", { hasText: "设置" }).first().click();
await page.waitForTimeout(500);
const menuNames = ["偏好", "账本规则", "预算", "AI 回答", "每日晨报", "长期记忆", "数据与状态", "访问口令"];
let settingsText = "";
let reportCollapsed = false;
for (const m of menuNames) {
  await page.locator("main nav:visible button", { hasText: m }).first().click();
  await page.waitForTimeout(350);
  settingsText += "\n" + (await page.locator("main").innerText());
  if (m === "每日晨报") reportCollapsed = (await page.locator("main details[open]").count()) === 0;
}
check("设置无品牌色", !settingsText.includes("品牌色"));
check("设置无界面密度", !settingsText.includes("界面密度"));
check("设置无界面动效", !settingsText.includes("界面动效"));
check("设置无行情源选择器", !settingsText.includes("仅快照价"));
check("设置含偏好", settingsText.includes("偏好"));
check("设置含账本规则", settingsText.includes("账本规则"));
check("设置含预算", settingsText.includes("预算"));
check("设置含 AI 数据出机提示", settingsText.includes("发送到你配置的模型服务商"));
check("设置含长期记忆", settingsText.includes("长期记忆"));
check("设置含数据与状态", settingsText.includes("数据与状态"));
check("设置含访问口令", settingsText.includes("访问口令"));
check("晨报历史默认折叠", reportCollapsed);

// —— 长期记忆：设置页内新增一条并删除（自清理，不留脏数据）——
const memText = `UI 冒烟记忆 ${Date.now()}`;
await page.locator("main nav:visible button", { hasText: "长期记忆" }).first().click();
await page.waitForTimeout(350);
await page.locator("main input").fill(memText);
await page.locator("main button", { hasText: "记住" }).click();
await page.waitForTimeout(600);
check("记忆新增后出现在列表", (await page.getByText(memText).count()) > 0);
await page.locator("main li", { hasText: memText }).locator("button[aria-label*='删除记忆']").click();
await page.waitForTimeout(600);
check("记忆可删除", (await page.getByText(memText).count()) === 0);

// —— 应用内确认框（Radix Dialog，替代 window.confirm）：只验证弹出与取消，绝不确认 ——
await page.locator("main nav:visible button", { hasText: "数据与状态" }).first().click();
await page.waitForTimeout(350);
await page.locator("main button", { hasText: "恢复" }).first().click();
await page.waitForTimeout(350);
check("危险操作弹应用内确认框", (await page.getByText("覆盖当前的持仓").count()) > 0 || (await page.getByText("overwrite current holdings").count()) > 0);
await page.keyboard.press("Escape");
await page.waitForTimeout(350);
check("确认框可 ESC 取消", (await page.getByText("覆盖当前的持仓").count()) === 0 && (await page.getByText("overwrite current holdings").count()) === 0);

// —— 问答页可从导航重新进入 ——
await page.locator("nav:visible button", { hasText: "问答" }).first().click();
await page.waitForTimeout(600);
check("导航可回到问答页", (await page.locator("textarea[placeholder*='问点什么']").count()) === 1);

// —— 空数据仪表盘：降级为引导，不渲染零值统计卡与风险横幅 ——
const emptyPage = await browser.newPage({ viewport: { width: 1440, height: 900 } });
emptyPage.on("pageerror", (e) => errors.push(String(e)));
await emptyPage.route("**/api/dashboard", async (route) => {
  const res = await route.fetch();
  const json = await res.json();
  json.positions = [];
  json.transactions = [];
  json.flags = [];
  const headers = { ...res.headers() };
  delete headers["content-length"];
  await route.fulfill({ status: res.status(), headers, body: JSON.stringify(json) });
});
await gotoDashboard(emptyPage);
const emptyMain = emptyPage.locator("main");
const emptyTxt = await emptyMain.innerText();
check("空数据仪表盘显示引导文案", /记下第一笔|还没有.*数据|先去记账/.test(emptyTxt));
// 只查 main 区域：侧栏会话历史里可能残留此前问答（如「总资产是多少」），
// 那是历史记录不是统计卡，不能算作零值卡泄漏。
check("空数据仪表盘不显示总资产卡", (await emptyMain.getByText("总资产").count()) === 0);
check("空数据仪表盘无风险横幅", (await emptyPage.getByText(/发现 \d+ 项需关注|未发现明显风险项/).count()) === 0);
check("空数据引导含「去记账」入口", (await emptyPage.getByText("去记账").count()) > 0);
await emptyPage.close();

// —— 空数据 + 空会话：问答首屏为通用助手引导（不假设已有数据）——
const heroPage = await browser.newPage({ viewport: { width: 1440, height: 900 } });
heroPage.on("pageerror", (e) => errors.push(String(e)));
await heroPage.route("**/api/dashboard", async (route) => {
  const res = await route.fetch();
  const json = await res.json();
  json.positions = [];
  json.transactions = [];
  json.flags = [];
  const headers = { ...res.headers() };
  delete headers["content-length"];
  await route.fulfill({ status: res.status(), headers, body: JSON.stringify(json) });
});
await heroPage.route("**/api/sessions", async (route) => {
  if (route.request().method() === "POST") {
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ thread_id: "hero-mock" }) });
  }
  return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ sessions: [] }) });
});
await heroPage.route("**/api/history?thread_id=hero-mock*", async (route) =>
  route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ runs: [] }) }),
);
await initZh(heroPage);
await heroPage.waitForTimeout(800);
const heroTxt = await heroPage.locator("main").innerText();
check("空数据首屏为通用助手引导", /没有数据也能|先随便聊聊|我是小满/.test(heroTxt));
check("空数据首屏不含持仓类建议", !heroTxt.includes("我的组合现在赚还是亏"));
check("空数据首屏无「正在准备会话…」滞留", !heroTxt.includes("正在准备会话"));
await heroPage.close();

// —— 移动端 ——
const mobile = await browser.newPage({ ...devices["iPhone 13"] });
mobile.on("pageerror", (e) => errors.push(String(e)));
await initZh(mobile);
await mobile.waitForTimeout(800);
check("移动端底部导航 4 项", (await mobile.locator("nav:visible button").count()) === 4);
check("移动端首屏为问答输入框", (await mobile.locator("textarea[placeholder*='问点什么']").count()) === 1);
await mobile.locator("nav:visible button", { hasText: "总览" }).first().click();
await mobile.waitForTimeout(600);
if (HAS_DATA) {
  check("移动端总资产可见", (await mobile.getByText("总资产").count()) > 0);
} else {
  check("移动端空库显示引导卡", (await mobile.getByText("这里还没有你的数据").count()) > 0);
  skip("移动端总资产可见", "当前库为空，仪表盘渲染引导态");
}
await mobile.locator("nav:visible button", { hasText: "记账" }).first().click();
await mobile.waitForTimeout(400);
check("移动端一句话记账可见", (await mobile.locator("input[placeholder*='昨天打车']").count()) === 1);
await mobile.close();

// —— 待扣跨月（page.clock 固定时钟；依赖示例库那几笔待扣流水）——
async function stripAt(iso) {
  const p = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  p.on("pageerror", (e) => errors.push(String(e)));
  await p.clock.setFixedTime(new Date(iso));
  await gotoDashboard(p);
  const text = await p.locator("main").innerText();
  await p.close();
  return text;
}
if (IS_SEED) {
  const at26 = await stripAt("2026-09-26T12:00:00");
  check("9-26 显示近期待扣提醒", at26.includes("近期待扣提醒"));
  check("9-26 含 28 号扣款（本月内）", at26.includes("28 号扣款"));
  check("9-26 无「下月」标注", !at26.includes("下月"));
  const at29 = await stripAt("2026-09-29T12:00:00");
  check("9-29 显示近期待扣提醒", at29.includes("近期待扣提醒"));
  check("9-29 含「下月 1 号扣款」（跨月）", /下月\s*1\s*号扣款/.test(at29));
  check("9-29 不含 28 号（已过号不重复）", !at29.includes("28 号扣款"));
} else {
  skip("待扣跨月 6 项", HAS_DATA ? "当前库为用户数据，示例待扣流水不存在" : "当前库为空，无待扣提醒可验证");
}

// —— 应急金无数据态（mock API，非破坏；明细区需要有数据才展开）——
if (HAS_DATA) {
  const emPage = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  emPage.on("pageerror", (e) => errors.push(String(e)));
  await emPage.route("**/api/dashboard", async (route) => {
    const res = await route.fetch();
    const json = await res.json();
    json.emergency = { cash: 0, essential_monthly: 0, essential_categories: [], months_covered: 0, target_months: 6, has_data: false, ok: true };
    json.flags = json.flags.filter((f) => f.id !== "EMERGENCY_FUND");
    const headers = { ...res.headers() };
    delete headers["content-length"];
    await route.fulfill({ status: res.status(), headers, body: JSON.stringify(json) });
  });
  await gotoDashboard(emPage);
  await emPage.getByText("明细分析").click();
  await emPage.waitForTimeout(600);
  const emTxt = await emPage.locator("main").innerText();
  check("应急金显示「暂无数据」", emTxt.includes("暂无数据"));
  check("不显示「0.0 个月（目标」", !emTxt.includes("0.0 个月（目标"));
  check("显示「暂无法估算」话术", emTxt.includes("暂无法估算"));
  check("无应急金不足风险文案", !/应急金[^未]*不足|应急金缺口/.test(emTxt));
  await emPage.close();
} else {
  skip("应急金无数据态 4 项", "当前库为空，仪表盘渲染引导态无应急金卡");
}

// —— 对照组：正常态（依赖示例库的现金与必要支出数据）——
if (IS_SEED) {
  const okPage = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  okPage.on("pageerror", (e) => errors.push(String(e)));
  await gotoDashboard(okPage);
  await okPage.getByText("明细分析").click();
  await okPage.waitForTimeout(600);
  const okTxt = await okPage.locator("main").innerText();
  check("正常数据显示月数/目标", /个月（目标/.test(okTxt));
  check("正常态有达标或不足徽标", okTxt.includes("达标") || okTxt.includes("不足"));
  await okPage.close();
} else {
  skip("应急金正常态对照 2 项", HAS_DATA ? "当前库为用户数据，示例必要支出数据不存在" : "当前库为空");
}

// —— 账本化视觉语言 + 来源诚实（设计打磨切片）——
// 历史消息不伪造来源：runs 表未存 route/llm，历史无法证明来源
const histPage = await browser.newPage({ viewport: { width: 1280, height: 900 } });
histPage.on("pageerror", (e) => errors.push(String(e)));
await initZh(histPage);
await histPage.waitForTimeout(600);
const chatBody = await histPage.locator("main").innerText();
check("历史回答不显示「基于你的数据计算」", !chatBody.includes("基于你的数据计算"));
check("界面无内部等级代号 L0/L1/L2", !/\bL[012]\s/.test(chatBody));
check("界面无「通用回答」这类多余标签", !chatBody.includes("通用回答"));

// 默认路径是通用 agent：无数据时给的是通用建议，不是财务问卷
const agentPage = await browser.newPage({ viewport: { width: 1280, height: 900 } });
agentPage.on("pageerror", (e) => errors.push(String(e)));
await agentPage.route("**/api/dashboard", async (route) => {
  const res = await route.fetch();
  const json = await res.json();
  json.positions = [];
  json.transactions = [];
  const headers = { ...res.headers() };
  delete headers["content-length"];
  await route.fulfill({ status: res.status(), headers, body: JSON.stringify(json) });
});
await agentPage.route("**/api/sessions", async (route) => {
  if (route.request().method() === "POST") {
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ thread_id: "agent-empty" }) });
  }
  return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ sessions: [] }) });
});
await agentPage.route("**/api/history?thread_id=agent-empty*", async (route) =>
  route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ runs: [] }) }),
);
await initZh(agentPage);
await agentPage.waitForTimeout(800);
const agentTxt = await agentPage.locator("main").innerText();
check("空态自述为通用助手", agentTxt.includes("我是小满"));
check("空态建议体现通用能力", agentTxt.includes("理一理") || agentTxt.includes("改得更专业"));
check("空态不追问财务问题", !agentTxt.includes("支持哪些方式导入账单"));
await agentPage.close();
await histPage.close();

// 统计栏金额与百分比分行，不被截断
if (HAS_DATA) {
  const dashPage = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  dashPage.on("pageerror", (e) => errors.push(String(e)));
  await gotoDashboard(dashPage);
  const pnlCard = await dashPage.evaluate(() => {
    const cards = Array.from(document.querySelectorAll("main .grid > *"));
    const card = cards.find((c) => c.textContent?.includes("累计盈亏"));
    if (!card) return null;
    const valueEl = card.querySelector(".truncate");
    return {
      text: (card.textContent || "").replace(/\s+/g, " "),
      truncated: !!valueEl && valueEl.scrollWidth > valueEl.clientWidth + 1,
    };
  });
  check("累计盈亏卡存在", pnlCard !== null);
  check("累计盈亏金额不被截断", pnlCard !== null && !pnlCard.truncated);
  check("累计盈亏百分比完整可见", pnlCard !== null && /-?\d+(\.\d+)?%/.test(pnlCard.text));
  await dashPage.close();
}

// —— 默认语言 en：界面默认英文，可一键切回中文 ——
{
  const langPage = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  langPage.on("pageerror", (e) => errors.push(String(e)));
  await langPage.goto(BASE, { waitUntil: "domcontentloaded" });
  await langPage.evaluate(() => localStorage.removeItem("wo.lang"));
  await langPage.reload({ waitUntil: "networkidle" });
  await langPage.waitForTimeout(500);
  const bodyEn = await langPage.locator("body").innerText();
  check("默认语言为英文（导航含 Chat）", bodyEn.includes("Chat"));
  check("默认英文输入框 placeholder 为英文", (await langPage.locator("textarea[placeholder*='Ask anything']").count()) === 1);
  const langBtn = await langPage
    .locator("button[aria-label='切换语言'], button[aria-label='Switch language']")
    .first()
    .click()
    .catch(() => null);
  await langPage.waitForTimeout(500);
  const bodyZh = await langPage.locator("body").innerText();
  check("一键切换后界面变中文（含 问答）", langBtn !== null && bodyZh.includes("问答"));
  await langPage.close();
}

await browser.close();
finish(errors);
