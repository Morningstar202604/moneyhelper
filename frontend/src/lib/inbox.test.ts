import { beforeEach, describe, expect, it } from "vitest";
import { countUnread, readSeenId, writeSeenId } from "./inbox";
import type { ScheduledOutput } from "./types";

const mk = (id: number): ScheduledOutput => ({
  id,
  thread_id: "cron",
  question: "q",
  answer: "a",
  level: "已生成",
  flags: [],
  created_at: "2026-10-15T00:00:00+08:00",
  kind: "report",
  skill_id: null,
  skill_name: null,
});

describe("inbox unread", () => {
  it("countUnread 只数比游标新的条目", () => {
    const items = [mk(9), mk(8), mk(7), mk(5)];
    expect(countUnread(items, 0)).toBe(4);
    expect(countUnread(items, 7)).toBe(2);
    expect(countUnread(items, 9)).toBe(0);
    expect(countUnread([], 0)).toBe(0);
  });

  it("已读游标读写往返", () => {
    writeSeenId(42);
    expect(readSeenId()).toBe(42);
    writeSeenId(7); // 允许回退（例如清空后重来）
    expect(readSeenId()).toBe(7);
  });

  beforeEach(() => {
    localStorage.clear();
  });
});
