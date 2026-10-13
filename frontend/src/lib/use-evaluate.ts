/** 评估引擎前端 Hook：拉取 + 分组 + i18n 文案组装。 */

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface EvalItem {
  kind: "todo" | "warn" | "info" | "goal";
  priority: number;
  code: string;
  title: string;
  detail: string;
  vars: Record<string, unknown>;
  action?: { path: string; label?: string } | null;
}

export interface EvalResult {
  month: string;
  refreshed_at: string;
  items: EvalItem[];
  summary: {
    todo: number;
    warn: number;
    info: number;
    goal: number;
    max_priority: number;
  };
}

export function fetchEvaluate(month?: string): Promise<EvalResult> {
  const qs = month ? `?month=${encodeURIComponent(month)}` : "";
  return api<EvalResult>(`/api/evaluate${qs}`);
}

export function useEvaluate(month?: string) {
  return useQuery({
    queryKey: ["evaluate", month ?? ""],
    queryFn: () => fetchEvaluate(month),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
}
