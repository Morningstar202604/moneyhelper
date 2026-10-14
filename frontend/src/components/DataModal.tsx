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
import { cn } from "@/lib/utils";

/**
 * 数据侧面板（ChatGPT 式辅助工具区）—— 桌面从右侧滑出，不遮挡对话；
 * 面板内可在 总览/持仓/行情/记账/体检 间直接切换；移动端全屏展开。
 * 对话仍是主角：面板只是「按需展开、用完即收」的工具抽屉。
 */
export type DataKind = "overview" | "holdings" | "market" | "ledger" | "health";

const KINDS: DataKind[] = ["overview", "holdings", "market", "ledger", "health"];

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

export function DataModal({
  kind,
  onClose,
  onKindChange,
}: {
  kind: DataKind;
  onClose: () => void;
  onKindChange?: (k: DataKind) => void;
}) {
  const { t } = useI18n();

  // Esc 关闭（与 settings overlay 行为一致）
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <motion.div className="fixed inset-0 z-40 md:pointer-events-none">
      {/* 移动端遮罩（桌面不遮挡：对话保持可交互） */}
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm md:hidden" onClick={onClose} />
      <motion.aside
        role="complementary"
        aria-label={t(TITLE_KEY[kind])}
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", stiffness: 420, damping: 42 }}
        className="pointer-events-auto absolute right-0 top-0 flex h-full w-full flex-col border-l border-border bg-card shadow-lift md:w-[380px] lg:w-[440px]"
      >
        {/* 头部：标题 + 工具页切换 + 关闭 */}
        <div className="flex items-center justify-between gap-2 border-b border-border px-3.5 py-2.5">
          <h2 className="shrink-0 text-sm font-semibold">{t(TITLE_KEY[kind])}</h2>
          <div className="flex min-w-0 items-center gap-0.5 overflow-x-auto" role="tablist" aria-label={t("nav.features")}>
            {KINDS.map((k) => (
              <button
                key={k}
                type="button"
                role="tab"
                aria-selected={k === kind}
                onClick={() => onKindChange?.(k)}
                className={cn(
                  "shrink-0 rounded-md px-2 py-1 text-xs transition-colors",
                  k === kind
                    ? "bg-primary/10 font-medium text-primary"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground",
                )}
              >
                {t(TITLE_KEY[k])}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("app.close")}
            className="shrink-0 rounded-md p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto scroll-thin p-4">
          {kind === "overview" && <Dashboard />}
          {kind === "holdings" && <HoldingsView />}
          {kind === "market" && <MarketView />}
          {kind === "ledger" && <EntryView />}
          {kind === "health" && <HealthBody />}
        </div>
      </motion.aside>
    </motion.div>
  );
}
