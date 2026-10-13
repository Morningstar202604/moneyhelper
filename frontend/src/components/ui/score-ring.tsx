import { cn } from "@/lib/utils";

/**
 * 通用 SVG 评分圆环（纯 SVG 实现，零依赖）。
 * 用于健康评分、目标完成度等场景：0-100 分对应弧长比例。
 * 圆环中心显示分数文字。
 */
export function ScoreRing({
  score,
  size = 96,
  strokeWidth = 6,
  color,
  label,
  sublabel,
  className,
}: {
  /** 0-100 评分 */
  score: number;
  /** 圆环直径（px） */
  size?: number;
  /** 圆环粗细（px） */
  strokeWidth?: number;
  /** 弧线颜色（CSS 颜色值或 Tailwind 文本 class; 默认按分数自动着色） */
  color?: string;
  /** 分数下方一级标签 */
  label?: string;
  /** 分数下方二级标签 */
  sublabel?: string;
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(100, score));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const dashLength = (clamped / 100) * circumference;
  const center = size / 2;

  const autoColor = color ?? (clamped >= 80 ? "#10b981" : clamped >= 60 ? "#3b82f6" : clamped >= 40 ? "#f59e0b" : clamped >= 20 ? "#f97316" : "#ef4444");

  return (
    <div className={cn("inline-flex flex-col items-center", className)}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        {/* 背景轨道 */}
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke="hsl(var(--border))"
          strokeWidth={strokeWidth}
        />
        {/* 进度弧 */}
        {clamped > 0 && (
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke={autoColor}
            strokeWidth={strokeWidth}
            strokeDasharray={`${dashLength} ${circumference}`}
            strokeLinecap="round"
          />
        )}
      </svg>
      {/* 中心文字（SVG 外渲染更易定位与样式） */}
      <div
        style={{ marginTop: -(size / 2 + 8), marginBottom: size / 2 - 8 }}
        className="flex flex-col items-center pointer-events-none"
      >
        <span className="text-lg font-bold tabular-nums leading-none" style={{ color: autoColor }}>
          {Math.round(clamped)}
        </span>
        {sublabel && <span className="text-[9px] text-muted-foreground leading-none mt-0.5">{sublabel}</span>}
      </div>
      {label && <span className="text-xs text-muted-foreground mt-1">{label}</span>}
    </div>
  );
}
