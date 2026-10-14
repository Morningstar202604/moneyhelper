import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { defineConfig, devices } from "@playwright/test";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

/**
 * e2e 配置：启动后端（uvicorn :8788，专用测试库 e2e.db）+ 前端 dev（vite :5198，/api 反代到后端）。
 * globalSetup 先加载种子数据（positions/transactions/subscriptions），再开始测试。
 *
 * 用法：
 *   npx playwright test                # 头默模式
 *   npx playwright test --headed       # 看得见的浏览器
 *   npx playwright test --debug        # 单步调试
 */
export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  timeout: 30_000,
  expect: { timeout: 7_000 },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: process.env.CI ? "github" : [["list"]],
  use: {
    baseURL: "http://127.0.0.1:5198",
    locale: "zh-CN",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: [
    {
      // 后端：专用测试库，避免污染研发者的 wealth.db
      command: "bash ../scripts/e2e-backend.sh",
      cwd: __dirname,
      port: 8788,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
      stdout: "pipe",
      stderr: "pipe",
      env: {
        XIAOMAN_DB_PATH: "backend/data/e2e.db",
      },
    },
    {
      // 前端 dev：/api 反代到 8788
      command: "npm run dev",
      cwd: __dirname,
      port: 5198,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
      stdout: "pipe",
      stderr: "pipe",
    },
  ],
});
