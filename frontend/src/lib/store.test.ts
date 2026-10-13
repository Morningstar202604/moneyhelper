import { describe, expect, it } from "vitest";
import { getQueryClient, queryKeys, setQueryClient } from "./store";
import { QueryClient } from "@tanstack/react-query";

describe("store (TanStack Query)", () => {
  it("queryKeys.dashboard 应包含 'dashboard' 字符串", () => {
    expect(queryKeys.dashboard).toContain("dashboard");
  });

  it("queryKeys 的每个值都应是包含字符串的数组", () => {
    for (const [name, key] of Object.entries(queryKeys)) {
      expect(Array.isArray(key), `${name} should be array`).toBe(true);
      expect(key.length, `${name} should be non-empty`).toBeGreaterThan(0);
    }
  });

  it("getQueryClient() 应返回 QueryClient 实例", () => {
    const client = getQueryClient();
    expect(client).toBeInstanceOf(QueryClient);
  });

  it("setQueryClient() 应替换内部 client", () => {
    const oldClient = getQueryClient();
    const newClient = new QueryClient();
    setQueryClient(newClient);
    expect(getQueryClient()).toBe(newClient);
    // 恢复
    setQueryClient(oldClient);
  });

  it("getQueryClient() 默认应创建 client（不抛错）", () => {
    expect(() => getQueryClient()).not.toThrow();
  });
});
