import { useMemo, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/confirm";
import { EmptyState } from "@/components/ui/empty-state";
import { StatCell } from "@/components/ui/stat";
import { PillTabs } from "@/components/ui/pill-tabs";
import { LineChart, Combine } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { store, useDashboard, useBootstrap } from "@/lib/store";
import { fmtMoney, pnlClass } from "@/lib/format";
import { PositionsTable, type PositionOps } from "@/components/PositionsTable";
import { PositionEditDialog } from "@/components/PositionEditDialog";
import { api } from "@/lib/api";
import { useMutate } from "@/lib/use-mutate";
import type { Position } from "@/lib/types";

/** 持仓页：按 股票/基金/理财 分组明细 + 风险概览（集中度 / 行业分布）。
 *  明细行支持编辑 / 删除；工具栏支持「合并重复」与「追加持仓」。 */
export function HoldingsView({ onGoMarket }: { onGoMarket?: () => void } = {}) {
  const { t } = useI18n();
  const { dashboard } = useDashboard();
  const { bootstrap } = useBootstrap();
  const compact = (bootstrap?.settings.compact_numbers ?? "on") === "on";
  const positions = dashboard?.positions ?? [];

  const kinds = useMemo(() => ["all", ...Array.from(new Set(positions.map((p) => p.kind)))], [positions]);
  const [kind, setKind] = useState<string>("all");
  const [editing, setEditing] = useState<Position | null>(null);
  const [deleting, setDeleting] = useState<Position | null>(null);

  // 同名不同 symbol 的重复持仓（合并入口只对真有重复的 name 显示）
  const dupeNames = useMemo(() => {
    const seen = new Map<string, number>();
    for (const p of positions) seen.set(p.name, (seen.get(p.name) ?? 0) + 1);
    return Array.from(seen.entries()).filter(([, n]) => n > 1).map(([n]) => n);
  }, [positions]);

  const del = useMutate<{ symbol: string; name: string }, void>({
    fn: (a) => api(`/api/positions/${encodeURIComponent(a.symbol)}`, { method: "DELETE" }).then(() => undefined),
    key: "pos.deleted",
    vars: (a) => ({ name: a.name }),
    onSettled: (_res, e) => {
      if (!e) setDeleting(null);
    },
  });

  const merge = useMutate<undefined, { n: number; count: number }>({
    fn: async () => {
      let total = 0;
      for (const name of dupeNames) {
        const r = await api<{ merged: number }>("/api/positions/merge", {
          method: "POST",
          body: JSON.stringify({ name }),
        });
        total += r.merged;
      }
      return { n: total, count: dupeNames.length };
    },
    key: (_a, res) => (res.n > 0 ? "pos.mergeAllDone" : "pos.mergeNone"),
    vars: (_a, res) => ({
      n: res.n,
      count: res.count,
      name: res.count > 0 ? dupeNames.join("、") : "",
    }),
  });

  const doMerge = () => {
    if (!dupeNames.length) return;
    void merge.mutateAsync(undefined);
  };

  const append = useMutate<{ p: Position; payload: { shares: number; cost: number; last?: number } }, { new_shares: number }>({
    fn: (a) =>
      api<{ new_shares: number }>(`/api/positions/${encodeURIComponent(a.p.symbol)}/append`, {
        method: "POST",
        body: JSON.stringify(a.payload),
      }),
    key: "pos.appendDone",
    vars: (a, res) => ({ name: a.p.name, shares: res.new_shares }),
  });

  const ops: PositionOps = {
    onEdit: (p) => setEditing(p),
    onDelete: (p) => setDeleting(p),
    onAppend: (p, payload) => void append.mutateAsync({ p, payload }),
  };

  if (!dashboard) return null;

  // 空持仓引导：新用户还没有任何持仓时不给零值统计与空图表
  if (positions.length === 0) {
    return (
      <div className="flex min-h-[calc(100vh-10rem)] flex-col justify-center space-y-3">
        <Card>
          <EmptyState
            illustration="holdings"
            title={t("hold.emptyTitle")}
            desc={t("hold.emptyDesc")}
            actions={
              <Button size="sm" onClick={() => onGoMarket?.()}>
                <LineChart className="w-4 h-4" /> {t("hold.emptyBtn")}
              </Button>
            }
          />
        </Card>
        <p className="px-2 text-center text-xs text-muted-foreground">{t("hold.emptyHint")}</p>
      </div>
    );
  }

  const filtered = kind === "all" ? positions : positions.filter((p) => p.kind === kind);
  const cash = positions.filter((p) => p.kind === "现金").reduce((s, p) => s + p.cost, 0);
  const totalMV = positions.reduce((s, p) => s + p.market_value, 0) - cash;
  const totalPnl = positions.reduce((s, p) => s + p.pnl, 0);
  const todayTotal = dashboard.today_pnl.total;
  const byAsset = [...dashboard.concentration.by_asset].sort((a, b) => b.pct - a.pct).slice(0, 3);
  const byIndustry = [...dashboard.concentration.by_industry].sort((a, b) => b.pct - a.pct).slice(0, 4);

  return (
    <div className="space-y-3">
      {/* 摘要行：市值 / 今日盈亏 / 累计盈亏 / 现金 */}
      <div className="grid grid-cols-2 gap-y-3 rounded-[var(--radius)] border border-border bg-card px-3 py-1 sm:grid-cols-4 sm:divide-x sm:divide-border/70">
        <StatCell label={t("dash.holdingsValue")} value={fmtMoney(totalMV, false, compact)} />
        <StatCell label={t("dash.todayPnl")} value={fmtMoney(todayTotal, true, compact)} valueClass={pnlClass(todayTotal)} />
        <StatCell label={t("dash.totalPnl")} value={fmtMoney(totalPnl, true, compact)} valueClass={pnlClass(totalPnl)} />
        <StatCell label={t("dash.cashAvailable")} value={fmtMoney(cash, false, compact)} />
      </div>

      {/* 操作工具栏：编辑 / 删除走明细行；这里放「合并重复」入口 */}
      <div className="flex flex-wrap items-center gap-2">
        {dupeNames.length > 0 && (
          <Button size="sm" variant="outline" onClick={() => void doMerge()} disabled={merge.isPending}>
            <Combine className="w-3.5 h-3.5" /> {t("pos.mergeBtn")}
            <span className="ml-1 text-muted-foreground">({dupeNames.length})</span>
          </Button>
        )}
      </div>

      {/* 风险概览 */}
      <div className="grid sm:grid-cols-2 gap-3">
        <Card className="p-[var(--card-pad)]">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-medium">{t("holdings.concentration")}</span>
            <Badge variant={dashboard.concentration.threshold_pct > 40 ? "warn" : "muted"}>
              {t("holdings.threshold", { n: dashboard.concentration.threshold_pct })}
            </Badge>
          </div>
          {byAsset.length === 0 ? (
            <EmptyState mode="compact" text={t("holdings.empty")} className="py-4" />
          ) : (
            <ul className="space-y-1.5 text-sm">
              {byAsset.map((a) => (
                <li key={a.name} className="flex items-center justify-between gap-2">
                  <span className="min-w-0 truncate">{a.name}</span>
                  <span className="flex items-center gap-2 shrink-0">
                    <span className="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
                      <span className="block h-full rounded-full bg-primary" style={{ width: `${Math.min(100, a.pct)}%` }} />
                    </span>
                    <span className="w-10 text-right tabular-nums text-muted-foreground">{a.pct}%</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card className="p-[var(--card-pad)]">
          <div className="mb-2 text-sm font-medium">{t("holdings.industry")}</div>
          {byIndustry.length === 0 ? (
            <EmptyState mode="compact" text={t("holdings.empty")} className="py-4" />
          ) : (
            <ul className="space-y-1.5 text-sm">
              {byIndustry.map((x) => (
                <li key={x.industry} className="flex items-center justify-between gap-2">
                  <span className="min-w-0 truncate">{x.industry}</span>
                  <span className="w-10 text-right tabular-nums text-muted-foreground">{x.pct}%</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {/* 明细：按 kind 分组，行内可编辑 / 删除 / 追加 */}
      <Card className="p-[var(--card-pad)]">
        <div className="mb-2 flex flex-wrap items-center gap-1.5">
          <PillTabs
            value={kind}
            onChange={setKind}
            size="sm"
            options={kinds.map((k) => ({ value: k, label: k === "all" ? t("holdings.all") : k }))}
          />
          <span className="ml-auto text-xs text-muted-foreground">
            {filtered.length} {t("holdings.items")}
          </span>
        </div>
        {filtered.length === 0 ? (
          <EmptyState mode="compact" text={t("holdings.empty")} />
        ) : (
          <PositionsTable rows={filtered} compact={compact} ops={ops} />
        )}
      </Card>

      {/* 编辑弹窗 */}
      <PositionEditDialog
        position={editing}
        open={editing !== null}
        onOpenChange={(o) => !o && setEditing(null)}
        onDone={() => {
          setEditing(null);
          store.bump();
        }}
      />

      {/* 删除确认 */}
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={t("pos.deleteTitle", { name: deleting?.name ?? "" })}
        description={t("pos.deleteDesc")}
        confirmText={t("confirm.confirm")}
        cancelText={t("confirm.cancel")}
        danger
        onConfirm={() => {
          if (deleting) void del.mutate({ symbol: deleting.symbol, name: deleting.name });
        }}
      />
    </div>
  );
}
