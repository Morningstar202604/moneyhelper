/** 定时产出收件箱：晨报 + 技能触发的统一读取层（数据源 /api/scheduled-outputs）。
 *
 * 未读口径：本地记录「已读到的最大产出 id」（localStorage），
 * 比它新的一律计未读；打开面板即整体标读。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { ScheduledOutput } from "./types";

const SEEN_KEY = "wo.schedSeenId";
const POLL_MS = 60_000;
/** 手动触发/清账后广播：让所有收件箱实例立即重拉（不等轮询） */
export const INBOX_REFRESH_EVENT = "wo:schedRefresh";
const SEEN_EVENT = "wo:schedSeen";

export function emitInboxRefresh(): void {
  try {
    window.dispatchEvent(new Event(INBOX_REFRESH_EVENT));
  } catch {
    /* ignore */
  }
}

export function readSeenId(): number {
  try {
    return Number(localStorage.getItem(SEEN_KEY) || 0) || 0;
  } catch {
    return 0;
  }
}

export function writeSeenId(id: number): void {
  try {
    localStorage.setItem(SEEN_KEY, String(id));
  } catch {
    /* 隐私模式等场景忽略 */
  }
  // 广播标读：同页多个实例（侧栏徽标 / 顶栏徽标）同步清零
  try {
    window.dispatchEvent(new Event(SEEN_EVENT));
  } catch {
    /* ignore */
  }
}

/** 纯函数：未读条数（id 比已读游标新）。抽出来便于单测。 */
export function countUnread(outputs: ScheduledOutput[], seenId: number): number {
  return outputs.filter((o) => o.id > seenId).length;
}

export function fetchScheduledOutputs(limit = 30): Promise<ScheduledOutput[]> {
  return api<{ outputs: ScheduledOutput[] }>(`/api/scheduled-outputs?limit=${limit}`).then(
    (r) => r.outputs ?? [],
  );
}

export function useScheduledOutputs() {
  const [outputs, setOutputs] = useState<ScheduledOutput[] | null>(null);
  const [seenId, setSeenId] = useState<number>(readSeenId);
  // 用 ref 暴露最新列表给 markAllRead：若让 markAllRead 依赖 outputs，
  // 回调身份会随每次刷新变化，导致依赖它的 effect 反复触发（请求循环）。
  const outputsRef = useRef<ScheduledOutput[] | null>(null);
  outputsRef.current = outputs;

  const refresh = useCallback(async (): Promise<ScheduledOutput[]> => {
    try {
      const items = await fetchScheduledOutputs(30);
      setOutputs(items);
      return items;
    } catch {
      setOutputs((prev) => prev ?? []);
      return [];
    }
  }, []);

  useEffect(() => {
    void refresh();
    const onFocus = () => void refresh();
    const onRefresh = () => void refresh();
    const onSeen = () => setSeenId(readSeenId());
    window.addEventListener("focus", onFocus);
    window.addEventListener(INBOX_REFRESH_EVENT, onRefresh);
    window.addEventListener(SEEN_EVENT, onSeen);
    const timer = window.setInterval(() => void refresh(), POLL_MS);
    return () => {
      window.removeEventListener("focus", onFocus);
      window.removeEventListener(INBOX_REFRESH_EVENT, onRefresh);
      window.removeEventListener(SEEN_EVENT, onSeen);
      window.clearInterval(timer);
    };
  }, [refresh]);

  /** 整体标读；不传参时用当前已加载列表（打开面板场景会先 refresh 再传入最新列表）。

   * 依赖保持为空：内部只通过 ref 读最新列表，回调身份稳定，
   * 依赖它的 effect 不会因为一次刷新就重新触发。
   */
  const markAllRead = useCallback((items?: ScheduledOutput[]) => {
    const list = items ?? outputsRef.current ?? [];
    if (list.length === 0) return;
    const maxId = Math.max(...list.map((o) => o.id));
    writeSeenId(maxId);
    setSeenId(maxId);
  }, []);

  return { outputs, unread: countUnread(outputs ?? [], seenId), refresh, markAllRead };
}
