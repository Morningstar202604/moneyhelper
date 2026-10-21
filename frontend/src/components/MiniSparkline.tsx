import { useMemo } from "react";
import type { KlinePoint } from "@/components/KlineDialog";

/**
 * 极简走势线（纯 SVG，不引图表库）。
 *
 * 为什么不用 ECharts：列表里可能同时有十几条迷你图，每条都 init 一个
 * ECharts 实例代价过高；这里只是折线，SVG path 足够，且天然随容器缩放。
 */
export function MiniSparkline({
  points,
  className,
  positiveColor = "#dc2626",
  negativeColor = "#059669",
}: {
  points: KlinePoint[];
  className?: string;
  positiveColor?: string;
  negativeColor?: string;
}) {
  const { path, area, up } = useMemo(() => {
    if (points.length < 2) return { path: "", area: "", up: true };
    const values = points.map((p) => p.close);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const w = 100;
    const h = 32;
    const step = w / (values.length - 1);
    const coords = values.map((v, i) => [i * step, h - ((v - min) / span) * h] as const);
    const line = coords.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
    const fill = `${line} L${w},${h} L0,${h} Z`;
    return { path: line, area: fill, up: values[values.length - 1] >= values[0] };
  }, [points]);

  if (!path) return <div className={className} />;
  const color = up ? positiveColor : negativeColor;
  return (
    <svg className={className} viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden="true">
      <path d={area} fill={color} opacity={0.08} />
      <path d={path} fill="none" stroke={color} strokeWidth={1.2} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
