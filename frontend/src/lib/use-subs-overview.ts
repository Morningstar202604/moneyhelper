/** 订阅总览：月度/年度合计 + 未来 7 天到期列表（纯前端计算，无需新增后端）。 */

import { useMemo } from "react";

const REMIND_WITHIN_DAYS = 7;

function safeDate(year: number, month: number, day: number): Date | null {
  const d = new Date(year, month - 1, day);
  if (d.getMonth() !== month - 1 || d.getDate() !== day) return null;
  return d;
}

function upcomingDueDate(today: Date, dueDay: number): Date | null {
  const thisMonth = safeDate(today.getFullYear(), today.getMonth() + 1, dueDay);
  const end = new Date(today);
  end.setDate(end.getDate() + REMIND_WITHIN_DAYS);
  const inWindow = (d: Date | null) => d && d >= today && d <= end;
  if (inWindow(thisMonth)) return thisMonth;
  const nextM = today.getMonth() + 2; // 下月
  const ny = today.getFullYear() + (nextM > 12 ? 1 : 0);
  const nm = nextM > 12 ? 1 : nextM;
  const nmDate = safeDate(ny, nm, dueDay);
  if (inWindow(nmDate)) return nmDate;
  return null;
}

function daysUntil(today: Date, target: Date): number {
  const a = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const b = new Date(target.getFullYear(), target.getMonth(), target.getDate()).getTime();
  return Math.round((b - a) / 86_400_000);
}

export interface SubDueRow {
  name: string;
  monthly: number;
  note: string;
  due_day: number;
  days_until: number;
  due_date: string;
}

export interface SubsOverviewResult {
  monthly_total: number;
  annual_total: number;
  upcoming: SubDueRow[];
  upcoming_monthly_total: number;
}

export function computeSubscriptionsOverview(
  subs: { name: string; monthly: number; note: string; due_day: string }[],
  now: Date = new Date(),
): SubsOverviewResult {
  let monthly = 0;
  const upcoming: SubDueRow[] = [];
  for (const s of subs) {
    monthly += Number(s.monthly) || 0;
    const dd = (s.due_day || "").trim();
    if (!dd) continue;
    const dueDay = Number(dd);
    if (!Number.isFinite(dueDay) || dueDay < 1 || dueDay > 31) continue;
    const due = upcomingDueDate(now, dueDay);
    if (!due) continue;
    upcoming.push({
      name: s.name,
      monthly: Number(s.monthly) || 0,
      note: s.note || "",
      due_day: dueDay,
      days_until: daysUntil(now, due),
      due_date: due.toISOString().slice(0, 10),
    });
  }
  upcoming.sort((a, b) => a.days_until - b.days_until);
  const upcomingMonthly = upcoming.reduce((acc, r) => acc + (Number(r.monthly) || 0), 0);
  return {
    monthly_total: monthly,
    annual_total: monthly * 12,
    upcoming,
    upcoming_monthly_total: upcomingMonthly,
  };
}

/** React hook wrapper */
export function useSubscriptionsOverview(
  subs: { name: string; monthly: number; note: string; due_day: string }[] | undefined,
): SubsOverviewResult {
  return useMemo(() => computeSubscriptionsOverview(subs ?? []), [subs]);
}
