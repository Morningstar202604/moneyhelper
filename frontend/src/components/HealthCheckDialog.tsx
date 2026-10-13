import { useEffect, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { HeartPulse, Loader2, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { fetchHealthCheck } from "@/lib/api";
import type { HealthReport } from "@/lib/types";
import { useI18n } from "@/lib/i18n";

const STATUS_LABEL: Record<string, { text: string; variant: "ok" | "warn" | "danger" }> = {
  good: { text: "hc.good", variant: "ok" },
  warn: { text: "hc.warn", variant: "warn" },
  bad: { text: "hc.bad", variant: "danger" },
};

export function HealthCheckDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { t } = useI18n();
  const [report, setReport] = useState<HealthReport | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    let alive = true;
    setReport(null);
    setError("");
    fetchHealthCheck(t("hc.locale"))
      .then((r) => alive && setReport(r))
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [open]);

  const scoreColor = report && (report.score >= 80 ? "text-success" : report.score >= 60 ? "text-amber-500" : "text-red-500");

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/45 backdrop-blur-sm data-[state=open]:animate-fade-in" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(94vw,34rem)] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-card p-4 shadow-lift data-[state=open]:animate-fade-in max-h-[86vh] overflow-y-auto scroll-thin">
          <Dialog.Title className="flex items-center justify-between text-sm font-semibold">
            <span className="flex items-center gap-1.5">
              <HeartPulse className="w-4 h-4 text-primary" /> {t("hc.title")}
            </span>
            <Dialog.Close asChild>
              <button className="p-1 text-muted-foreground hover:text-foreground" aria-label={t("hc.close")}>
                <X className="w-4 h-4" />
              </button>
            </Dialog.Close>
          </Dialog.Title>

          {error ? (
            <div className="mt-4 text-sm text-red-600 dark:text-red-400">{t("hc.error")}: {error}</div>
          ) : !report ? (
            <div className="mt-6 flex items-center justify-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" /> {t("hc.checking")}
            </div>
          ) : (
            <div className="mt-3 space-y-3">
              {/* 总分 */}
              <div className="flex items-center justify-between rounded-lg border border-border bg-muted/40 px-3 py-2">
                <span className="text-sm text-muted-foreground">{t("hc.score")}</span>
                <span className={`text-2xl font-semibold tabular-nums ${scoreColor}`}>{report.score}</span>
              </div>
              <p className="text-sm text-balance">{report.summary}</p>

              {/* 各维度 */}
              <div className="space-y-2">
                {report.dimensions.map((d) => {
                  const st = STATUS_LABEL[d.status] ?? STATUS_LABEL.good;
                  return (
                    <div key={d.key} className="rounded-lg border border-border px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-medium">{d.title}</span>
                        <Badge variant={st.variant}>{t(st.text)}</Badge>
                      </div>
                      <p className="mt-1 text-xs text-foreground/80">{d.detail}</p>
                      {d.suggestion && <p className="mt-1 text-xs text-muted-foreground">{t("hc.suggestion")}: {d.suggestion}</p>}
                    </div>
                  );
                })}
                {report.dimensions.length === 0 && (
                  <div className="py-4 text-center text-sm text-muted-foreground">
                    {t("hc.notEnough")}
                  </div>
                )}
              </div>
              <p className="text-[11px] text-muted-foreground">{t("notAdvice")}</p>
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
