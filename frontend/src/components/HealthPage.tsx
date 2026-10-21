import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, HeartPulse, Loader2 } from "lucide-react";
import { fetchHealthCheck } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { HealthReport } from "@/lib/types";

type Status = "good" | "warn" | "bad";

const STATUS_STYLE: Record<Status, { ring: string; text: string; bg: string }> = {
  good: { ring: "border-emerald-500/30", text: "text-emerald-700 dark:text-emerald-400", bg: "bg-emerald-500/10" },
  warn: { ring: "border-amber-500/30", text: "text-amber-700 dark:text-amber-400", bg: "bg-amber-500/10" },
  bad: { ring: "border-red-500/30", text: "text-red-700 dark:text-red-400", bg: "bg-red-500/10" },
};

const asStatus = (s: string): Status => (s === "good" || s === "bad" ? s : "warn");

/** 财务体检整页：评分 + 五维明细。原先是侧栏里的裸文本（直接显示 warn/bad），改为可读的状态卡。 */
export function HealthPage() {
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
      <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> {t("hc.checking")}
      </div>
    );
  }
  if (error) return <div className="py-8 text-sm text-red-600">{error}</div>;
  if (!report) return null;

  // 数据不足时后端返回 score=0 + 空 dimensions：不该展示"0 分"（会被误读为极度不健康），
  // 也不该出现三个全 0 的徽章，直接给引导态。
  if (report.dimensions.length === 0) {
    return (
      <div className="rounded-2xl border border-border bg-card px-6 py-14 text-center">
        <HeartPulse className="mx-auto h-8 w-8 text-muted-foreground/50" />
        <p className="mt-3 text-sm font-medium">{t("hc.notEnough")}</p>
        <p className="mt-1.5 text-xs text-muted-foreground">{t("notAdvice")}</p>
      </div>
    );
  }

  const scoreTone =
    report.score >= 80 ? "text-emerald-600" : report.score >= 60 ? "text-amber-600" : "text-red-600";
  const counts = report.dimensions.reduce(
    (acc, d) => {
      acc[asStatus(String(d.status))] += 1;
      return acc;
    },
    { good: 0, warn: 0, bad: 0 } as Record<Status, number>,
  );

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-[minmax(0,14rem)_1fr]">
        <div className="rounded-2xl border border-border bg-card p-5">
          <div className="text-xs text-muted-foreground">{t("hc.score")}</div>
          <div className={cn("mt-1 text-5xl font-semibold tabular-nums", scoreTone)}>
            {report.score}
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5 text-[11px]">
            <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-emerald-700 dark:text-emerald-400">
              {t("hc.good")} {counts.good}
            </span>
            <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-amber-700 dark:text-amber-400">
              {t("hc.warn")} {counts.warn}
            </span>
            <span className="rounded-full bg-red-500/10 px-2 py-0.5 text-red-700 dark:text-red-400">
              {t("hc.bad")} {counts.bad}
            </span>
          </div>
        </div>

        <div className="rounded-2xl border border-border bg-card p-5">
          <div className="text-sm font-medium">{t("hc.title")}</div>
          <p className="mt-1.5 text-sm leading-relaxed text-foreground/80">{report.summary}</p>
          <p className="mt-3 text-[11px] text-muted-foreground">{t("notAdvice")}</p>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {report.dimensions.map((d) => {
          const st = asStatus(String(d.status));
          const style = STATUS_STYLE[st];
          const Icon = st === "good" ? CheckCircle2 : AlertTriangle;
          return (
            <div key={d.key} className={cn("rounded-xl border bg-card p-4", style.ring)}>
              <div className="flex items-start justify-between gap-2">
                <span className="text-sm font-medium">{d.title}</span>
                <span
                  className={cn(
                    "inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium",
                    style.bg,
                    style.text,
                  )}
                >
                  <Icon className="h-3 w-3" />
                  {t(`hc.${st}`)}
                </span>
              </div>
              <p className="mt-2 text-[13px] leading-relaxed text-foreground/75">{d.detail}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
