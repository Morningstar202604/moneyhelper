import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { X, Loader2 } from "lucide-react";
import { Dashboard } from "@/components/Dashboard";
import { HoldingsView } from "@/components/HoldingsView";
import { MarketView } from "@/components/MarketView";
import { EntryView } from "@/components/EntryView";
import { fetchHealthCheck } from "@/lib/api";
import type { HealthReport } from "@/lib/types";
import { useI18n } from "@/lib/i18n";

/**
 * 数据浮层 —— 对话里的卡片点"展开"才弹出，居中 modal。
 * 不是常驻侧栏：95% 屏幕留给对话，财务数据只是对话里浮出来的小卡。
 */
export type DataKind = "overview" | "holdings" | "market" | "ledger" | "health";

function HealthBody() {
  const { t } = useI18n();
  const [report, setReport] = useState<HealthReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    fetchHealthCheck(t("hc.locale"))
      .then((r) => alive && setReport(r))
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [t]);

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
        <Loader2 className="w-4 h-4 animate-spin" /> {t("hc.checking")}
      </div>
    );
  }
  if (error) return <div className="py-6 text-sm text-red-600">{error}</div>;
  if (!report) return null;

  const scoreColor = report.score >= 80 ? "text-success" : report.score >= 60 ? "text-amber-500" : "text-red-500";

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between rounded-lg border border-border bg-muted/40 px-3 py-2">
        <span className="text-sm text-muted-foreground">{t("hc.score")}</span>
        <span className={`text-2xl font-semibold tabular-nums ${scoreColor}`}>{report.score}</span>
      </div>
      <p className="text-sm">{report.summary}</p>
      <div className="space-y-2">
        {report.dimensions.map((d) => (
          <div key={d.key} className="rounded-lg border border-border px-3 py-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium">{d.title}</span>
              <span className="text-xs text-muted-foreground">{d.status}</span>
            </div>
            <p className="mt-1 text-xs text-foreground/80">{d.detail}</p>
          </div>
        ))}
      </div>
      <p className="text-[11px] text-muted-foreground">{t("notAdvice")}</p>
    </div>
  );
}

const TITLE_KEY: Record<DataKind, string> = {
  overview: "nav.dashboard",
  holdings: "nav.holdings",
  market: "nav.market",
  ledger: "nav.ledger",
  health: "hc.title",
};

export function DataModal({ kind, onClose }: { kind: DataKind; onClose: () => void }) {
  const { t } = useI18n();

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.96, y: 12, opacity: 0 }}
        animate={{ scale: 1, y: 0, opacity: 1 }}
        exit={{ scale: 0.96, y: 12, opacity: 0 }}
        transition={{ type: "spring", stiffness: 380, damping: 32 }}
        className="w-[min(94vw,48rem)] max-h-[86vh] overflow-y-auto scroll-thin rounded-xl border border-border bg-card shadow-lift"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-card px-4 py-2.5">
          <h2 className="text-sm font-semibold">{t(TITLE_KEY[kind])}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("app.close")}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-4">
          {kind === "overview" && <Dashboard />}
          {kind === "holdings" && <HoldingsView />}
          {kind === "market" && <MarketView />}
          {kind === "ledger" && <EntryView />}
          {kind === "health" && <HealthBody />}
        </div>
      </motion.div>
    </motion.div>
  );
}
