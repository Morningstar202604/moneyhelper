/** 财务健康评分卡：大字评分 + A/B/C/D/F 等级 + 五维进度条 */

import { HeartPulse } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ProgressBar } from "@/components/ui/progress-bar";
import { ScoreRing } from "@/components/ui/score-ring";
import { useI18n } from "@/lib/i18n";
import { useHealthScore, type HealthScoreResult } from "@/lib/use-calculations";

/** 每维 0-20 分映射到颜色 */
function dimColor(score: number, max: number): string {
  const pct = max > 0 ? (score / max) * 100 : 0;
  return pct >= 70 ? "bg-emerald-500"
    : pct >= 40 ? "bg-amber-500"
    : "bg-red-500";
}

/** 后端 breakdown 转为前端维度数组 */
function toDimensions(breakdown: HealthScoreResult["breakdown"]) {
  return Object.entries(breakdown).map(([key, v]) => ({
    key,
    title: v.label,
    score: v.score,
    max: v.max,
    suggestion: v.detail,
  }));
}

/** 等级 -> Tailwind 颜色 class */
const GRADE_COLORS: Record<string, { ring: string; badge: string; label: string }> = {
  A: { ring: "text-emerald-500", badge: "ok", label: "A" },
  B: { ring: "text-blue-500", badge: "default", label: "B" },
  C: { ring: "text-amber-500", badge: "warn", label: "C" },
  D: { ring: "text-orange-500", badge: "warn", label: "D" },
  F: { ring: "text-red-500", badge: "danger", label: "F" },
};

export function HealthScoreCard() {
  const { t: tr } = useI18n();
  const { data, isLoading, isError } = useHealthScore();

  if (isLoading) {
    return (
      <Card className="p-[var(--card-pad)]">
        <Skeleton className="h-4 w-20 mb-3" />
        <div className="flex items-center gap-4">
          <Skeleton className="h-24 w-24 rounded-full" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-3/4" />
          </div>
        </div>
      </Card>
    );
  }
  if (isError || !data) {
    return (
      <Card className="p-[var(--card-pad)]">
        <div className="text-sm text-muted-foreground">{tr("health.loadFail")}</div>
      </Card>
    );
  }

  const dims = toDimensions(data.breakdown);
  const gradeColor = GRADE_COLORS[data.grade] ?? GRADE_COLORS.C;

  return (
    <Card className="@container p-[var(--card-pad)]">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <HeartPulse className="w-4 h-4 text-primary" />
          {tr("health.title")}
        </div>
        <Badge variant={gradeColor.badge as "ok" | "default" | "warn" | "danger"}>
          {tr("health.grade")} {data.grade}
        </Badge>
      </div>

      {/* 窄容器（侧面板 400px）下横向排布会把中文标签挤成逐字竖排，
          用容器查询在 <340px 时改为纵向堆叠：分数环在上、维度列表在下。 */}
      <div className="flex flex-col items-center gap-3 @[340px]:flex-row @[340px]:items-center @[340px]:gap-4">
        <ScoreRing
          score={data.score}
          size={88}
          strokeWidth={7}
          sublabel={tr("health.scoreLabel")}
        />

        <div className="w-full min-w-0 space-y-2 @[340px]:flex-1">
          {dims.map((d) => {
            const pct = d.max > 0 ? Math.round((d.score / d.max) * 100) : 0;
            return (
              <div key={d.key}>
                <div className="flex items-center justify-between text-[11px] mb-0.5">
                  <span className="text-foreground">{d.title}</span>
                  <span className="text-muted-foreground tabular-nums">{d.score}/{d.max}</span>
                </div>
                <ProgressBar pct={pct} colorClass={dimColor(d.score, d.max)} className="h-1.5" />
                {d.suggestion && (
                  <div className="mt-0.5 text-[11px] text-muted-foreground leading-snug text-balance">{d.suggestion}</div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </Card>
  );
}
