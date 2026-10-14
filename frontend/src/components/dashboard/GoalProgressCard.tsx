/** 财务目标进度卡：所有目标的进度条 / 完成标记 / 逾期警告 */

import { CheckCircle2, Target, AlertTriangle } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ProgressBar } from "@/components/ui/progress-bar";
import { ScoreRing } from "@/components/ui/score-ring";
import { useI18n } from "@/lib/i18n";
import { fmtMoney } from "@/lib/format";
import { useGoalProgress } from "@/lib/use-calculations";
import { cn } from "@/lib/utils";

export function GoalProgressCard() {
  const { t: tr } = useI18n();
  const { data, isLoading, isError } = useGoalProgress();

  if (isLoading) {
    return (
      <Card className="p-[var(--card-pad)]">
        <Skeleton className="h-4 w-20 mb-3" />
        <div className="space-y-3">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      </Card>
    );
  }
  if (isError || !data) {
    return (
      <Card className="p-[var(--card-pad)]">
        <div className="text-sm text-muted-foreground">{tr("goals.loadFail")}</div>
      </Card>
    );
  }
  if (data.length === 0) {
    return (
      <Card className="p-[var(--card-pad)]">
        <div className="flex items-center gap-2 text-sm font-medium mb-2">
          <Target className="w-4 h-4 text-primary" />
          {tr("goals.title")}
        </div>
        <div className="text-sm text-muted-foreground text-center py-4">{tr("goalsCard.empty")}</div>
      </Card>
    );
  }

  const doneCount = data.filter((g) => g.progress_pct >= 100).length;
  const avgPct = data.reduce((s, g) => s + g.progress_pct, 0) / data.length;

  return (
    <Card className="p-[var(--card-pad)]">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Target className="w-4 h-4 text-primary" />
          {tr("goals.title")}
        </div>
        <Badge variant="muted">{doneCount}/{data.length}</Badge>
      </div>

      {/* 平均进度圆环 */}
      <div className="flex items-center gap-3 mb-3 pb-3 border-b border-border/60">
        <ScoreRing score={avgPct} size={56} strokeWidth={5} sublabel={tr("goalsCard.avg")} />
        <div className="flex-1 text-sm text-muted-foreground">
          {tr("goalsCard.summary", { done: doneCount, total: data.length })}
        </div>
      </div>

      {/* 目标列表 */}
      <div className="space-y-2.5">
        {data.map((g) => {
          const isDone = g.progress_pct >= 100;
          return (
            <div key={g.name}>
              <div className="flex items-center justify-between text-xs mb-0.5">
                <span className="flex items-center gap-1.5">
                  {isDone ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-success shrink-0" />
                  ) : !g.on_track ? (
                    <AlertTriangle className="w-3.5 h-3.5 text-red-500 shrink-0" />
                  ) : (
                    <span className="w-3.5 h-3.5 rounded-full border-2 border-border shrink-0" />
                  )}
                  <span className={cn("truncate", isDone ? "text-muted-foreground line-through" : "text-foreground")}>{g.name}</span>
                </span>
                <span className="text-muted-foreground tabular-nums shrink-0 ml-2">{g.progress_pct}%</span>
              </div>
              <ProgressBar
                pct={Math.max(0, Math.min(100, g.progress_pct))}
                colorClass={isDone ? "bg-success" : !g.on_track ? "bg-red-500" : g.progress_pct >= 75 ? "bg-emerald-500" : g.progress_pct >= 40 ? "bg-primary" : "bg-amber-500"}
                className="h-1.5"
              />
              <div className="mt-0.5 text-[11px] text-muted-foreground flex items-center justify-between">
                <span>{fmtMoney(g.current_amount, false)} / {fmtMoney(g.target_amount, false)}</span>
                {!isDone && g.months_remaining !== null && g.months_remaining <= 3 && (
                  <span className={!g.on_track ? "text-red-500 font-medium" : ""}>
                    {tr("goalsCard.monthsLeft", { n: g.months_remaining })}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
