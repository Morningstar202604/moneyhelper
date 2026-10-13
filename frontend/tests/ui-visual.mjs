/**
 * 量化视觉审查：四页容器宽度/溢出 + 问答细节 + 宽屏抽查（不判定，只输出）。
 * 运行：node frontend/tests/ui-visual.mjs
 */

import { BASE, launchBrowser, loadPlaywright } from "./_harness.mjs";

const { chromium } = loadPlaywright();
const browser = await launchBrowser({ chromium });

async function audit(page, name) {
  const out = await page.evaluate(() => {
    const vw = window.innerWidth;
    const rect = (el) => {
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
    };
    const main = document.querySelector("main");
    let maxRight = 0;
    const wide = [];
    for (const el of document.querySelectorAll("main *")) {
      const r = el.getBoundingClientRect();
      if (r.width < 40 || r.height < 8) continue;
      const st = getComputedStyle(el);
      if (st.visibility === "hidden" || st.display === "none") continue;
      if (r.right > maxRight) maxRight = r.right;
      if (r.right > vw + 1) wide.push(el.tagName + "." + String(el.className).slice(0, 60));
    }
    const kids = [];
    if (main) {
      for (const el of main.querySelectorAll(":scope > *")) {
        const r = el.getBoundingClientRect();
        if (r.height > 20) kids.push({ cls: String(el.className).slice(0, 70), w: Math.round(r.width), h: Math.round(r.height) });
      }
    }
    return {
      vw,
      hOverflow: document.documentElement.scrollWidth > vw + 1,
      main: rect(main),
      mainKids: kids,
      contentMaxRight: Math.round(maxRight),
      overflowingEls: wide.slice(0, 6),
    };
  });
  console.log(`\n=== ${name} (${out.vw}px) ===`);
  console.log(JSON.stringify(out, null, 1));
  return out;
}

const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await page.goto(BASE, { waitUntil: "networkidle" });

for (const text of ["总览", "问答", "记账", "设置"]) {
  const scope = text === "设置" ? "aside" : "nav";
  await page.locator(`${scope}:visible button`, { hasText: text }).first().click();
  await page.waitForTimeout(900);
  await audit(page, text);
}

// 问答细节
await page.locator("nav:visible button", { hasText: "问答" }).first().click();
await page.waitForTimeout(600);
const detail = await page.evaluate(() => {
  const box = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { w: Math.round(r.width), h: Math.round(r.height), x: Math.round(r.x) };
  };
  const main = document.querySelector("main");
  const container = main?.firstElementChild;
  const cr = container?.getBoundingClientRect();
  return {
    viewport: window.innerWidth,
    chatContainer: cr ? { w: Math.round(cr.width), x: Math.round(cr.x) } : null,
    inputArea: box("main .border-t"),
    textarea: box("main textarea"),
    sidebarW: box("aside")?.w,
    mainW: box("main")?.w,
  };
});
console.log("\n=== 问答细节 ===");
console.log(JSON.stringify(detail, null, 1));

// 宽屏 1920
const wide = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
await wide.goto(BASE, { waitUntil: "networkidle" });
await wide.locator("nav:visible button", { hasText: "问答" }).first().click();
await wide.waitForTimeout(700);
const wideDetail = await wide.evaluate(() => {
  const main = document.querySelector("main");
  const c = main?.firstElementChild?.getBoundingClientRect();
  return { vw: window.innerWidth, chatW: c ? Math.round(c.width) : null, chatX: c ? Math.round(c.x) : null, mainW: Math.round(main?.getBoundingClientRect().width || 0) };
});
console.log("\n=== 宽屏 1920 问答 ===");
console.log(JSON.stringify(wideDetail, null, 1));

console.log("\npage errors:", errors.length ? errors.join("\n") : "none");
await browser.close();
