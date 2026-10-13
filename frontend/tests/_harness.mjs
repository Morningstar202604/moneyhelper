/** UI 断言公共库：playwright 解析（本地依赖优先）+ 浏览器启动 + 断言收集。 */

import { createRequire } from "node:module";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export const BASE = process.env.WO_BASE || "http://127.0.0.1:8787";

// playwright 已是 devDependency；WO_PLAYWRIGHT 仅用于非常规安装位置
export function loadPlaywright() {
  const req = createRequire(import.meta.url);
  for (const c of [process.env.WO_PLAYWRIGHT, "playwright"].filter(Boolean)) {
    try {
      return req(c);
    } catch {
      /* try next */
    }
  }
  console.error("找不到 playwright。请执行：npm i && npx playwright install chromium（或设 WO_PLAYWRIGHT=<模块路径>）");
  process.exit(2);
}

/** 在 ms-playwright 缓存里找可用的 chromium/headless-shell（不写死版本号目录）。 */
function findCachedChromium() {
  if (process.env.WO_CHROME) return process.env.WO_CHROME;
  const cache = path.join(os.homedir(), "AppData", "Local", "ms-playwright");
  if (!fs.existsSync(cache)) return undefined;
  const candidates = [];
  for (const dir of fs.readdirSync(cache)) {
    if (dir.startsWith("chromium_headless_shell")) {
      candidates.push([dir, "chrome-headless-shell-win64", "chrome-headless-shell.exe"]);
      candidates.push([dir, "chrome-headless-shell-win", "chrome-headless-shell"]);
    } else if (dir.startsWith("chromium-")) {
      candidates.push([dir, "chrome-win64", "chrome.exe"]);
      candidates.push([dir, "chrome-win", "chrome"]);
    }
  }
  for (const [dir, sub, exe] of candidates) {
    const p = path.join(cache, dir, sub, exe);
    if (fs.existsSync(p)) return p;
  }
  return undefined;
}

export async function launchBrowser(pw) {
  const executablePath = findCachedChromium();
  try {
    return await pw.chromium.launch(executablePath ? { executablePath } : undefined);
  } catch (err) {
    console.error("chromium 启动失败。请执行：npx playwright install chromium");
    throw err;
  }
}

export function makeChecks() {
  const checks = [];
  const skips = [];
  return {
    checks,
    /** 环境相关而无法执行的断言：显式记录并在结尾汇总，不静默通过 */
    skip(name, reason) {
      skips.push(`SKIP ${name} — ${reason}`);
    },
    check(name, cond) {
      checks.push(`${cond ? "PASS" : "FAIL"} ${name}`);
    },
    finish(pageErrors = []) {
      console.log(checks.join("\n"));
      if (skips.length) {
        console.log(skips.join("\n"));
        console.log(`skipped: ${skips.length} 项（依赖当前库不满足的前置数据，见上方 # 说明）`);
      }
      console.log("page errors:", pageErrors.length ? pageErrors.join("\n") : "none");
      const failed = checks.filter((c) => c.startsWith("FAIL"));
      process.exit(failed.length || pageErrors.length ? 1 : 0);
    },
  };
}
