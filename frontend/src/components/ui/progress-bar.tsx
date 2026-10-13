import { cn } from "@/lib/utils";

/** 进度条：默认按完成比例着色（>=100 绿 / >=50 主色 / <50 amber）。
 *  调用方传 className（如 bg-red-500/bg-emerald-500）可覆盖配色（预算卡阈值着色）。 */
export function ProgressBar({
  pct,
  className,
  colorClass,
  bgClass,
}: {
  pct: number;
  className?: string;
  /** 进度条填充色 class（覆盖默认阈值配色） */
  colorClass?: string;
  bgClass?: string;
}) {
  const clamped = Math.max(0, Math.min(100, pct));
  const color = colorClass ?? (pct >= 100 ? "bg-success" : pct >= 50 ? "bg-primary" : "bg-amber-500");
  return (
    <div className={cn("h-2 w-full rounded-full overflow-hidden", bgClass ?? "bg-muted", className)}>
      <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${clamped}%` }} />
    </div>
  );
}
