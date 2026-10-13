import { request } from "@playwright/test";

/**
 * 全局 setup：后端起好后调用 /api/portfolio/reset 种入演示数据，
 * 确保进测试时持仓/流水/订阅/债务都有可断言的内容。
 */
export default async function globalSetup() {
  const ctx = await request.newContext({ baseURL: "http://127.0.0.1:8788" });
  const resp = await ctx.post("/api/portfolio/reset");
  if (!resp.ok()) {
    const body = await resp.text();
    throw new Error(`/api/portfolio/reset failed: ${resp.status()} ${body}`);
  }
  await ctx.dispose();
}
