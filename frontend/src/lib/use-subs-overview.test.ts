import { describe, expect, it } from "vitest";
import { computeSubscriptionsOverview } from "./use-subs-overview";

describe("computeSubscriptionsOverview", () => {
  const baseNow = new Date(2026, 5, 15); // 2026-06-15

  it("空订阅返回全部零值结构与空 upcoming", () => {
    const r = computeSubscriptionsOverview([], baseNow);
    expect(r.monthly_total).toBe(0);
    expect(r.annual_total).toBe(0);
    expect(r.upcoming).toEqual([]);
    expect(r.upcoming_monthly_total).toBe(0);
  });

  it("月度合计应为各项 monthly 之和（不依赖 due_day）", () => {
    const r = computeSubscriptionsOverview(
      [
        { name: "Netflix", monthly: 45, note: "", due_day: "" },
        { name: "Spotify", monthly: 15, note: "", due_day: "" },
      ],
      baseNow,
    );
    expect(r.monthly_total).toBe(60);
    expect(r.annual_total).toBe(720);
  });

  it("本月 7 天内到期的订阅应入 upcoming 并按 days_until 升序", () => {
    const r = computeSubscriptionsOverview(
      [
        // 6 月 20 日 → 5 天后（在窗口内）
        { name: "A", monthly: 100, note: "", due_day: "20" },
        // 6 月 16 日 → 1 天后（在窗口内，更接近）
        { name: "B", monthly: 50, note: "", due_day: "16" },
        // 6 月 30 日 → 15 天后（窗口外）
        { name: "C", monthly: 80, note: "", due_day: "30" },
      ],
      baseNow,
    );
    expect(r.upcoming.map((u) => u.name)).toEqual(["B", "A"]);
    expect(r.upcoming[0].days_until).toBe(1);
    expect(r.upcoming[1].days_until).toBe(5);
    expect(r.upcoming_monthly_total).toBe(150);
  });

  it("due_day 缺失或格式非法的订阅应跳过（不出现在 upcoming）", () => {
    const r = computeSubscriptionsOverview(
      [
        { name: "Empty", monthly: 30, note: "", due_day: "" },
        { name: "Bad", monthly: 20, note: "", due_day: "abc" },
        { name: "Zero", monthly: 10, note: "", due_day: "0" },
        { name: "Over31", monthly: 10, note: "", due_day: "32" },
      ],
      baseNow,
    );
    expect(r.upcoming.length).toBe(0);
    expect(r.monthly_total).toBe(70);
  });

  it("跨年（due_day 已进入下月窗口）应计入 upcoming", () => {
    // 2026-06-29 + 窗口 7 天 → 7 月 6 号（6 天后）在窗口内；7 月 1 号也在
    const now = new Date(2026, 5, 29);
    const r = computeSubscriptionsOverview([{ name: "Sub", monthly: 100, note: "", due_day: "6" }], now);
    expect(r.upcoming.length).toBe(1);
    expect(r.upcoming[0].days_until).toBe(7);
  });

  it("当日到期（due_day = today）应标记 days_until = 0 并计入 upcoming", () => {
    const r = computeSubscriptionsOverview([{ name: "Now", monthly: 99, note: "", due_day: "15" }], baseNow);
    expect(r.upcoming.length).toBe(1);
    expect(r.upcoming[0].days_until).toBe(0);
  });

  it("due_day 字符串数字（含前后空格）应能正确解析", () => {
    const r = computeSubscriptionsOverview([{ name: "Trim", monthly: 50, note: "", due_day: " 18 " }], baseNow);
    expect(r.upcoming.length).toBe(1);
    expect(r.upcoming[0].days_until).toBe(3);
  });
});
