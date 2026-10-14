import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { SidePanel } from "@/components/ui/side-panel";
import { cn } from "@/lib/utils";
import { fmtMoney } from "@/lib/format";
import { api } from "@/lib/api";
import { useEChart, axisLabelColor } from "@/lib/charts";
import { useTheme } from "@/lib/theme";
import { useI18n } from "@/lib/i18n";

export interface KlinePoint {
  date: string;
  close: number;
  pct_change?: number | null;
}

/** K 线侧面板：近 60 日收盘价走势（A股/ETF；其他标的会提示不可用）。
 *  持仓表与行情页自选共用；右侧滑出，不遮挡对话。 */
export function KlineDialog({
  symbol,
  name,
  open,
  onOpenChange,
}: {
  symbol: string;
  name: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t: tr } = useI18n();
  const ref = useRef<HTMLDivElement>(null);
  const { resolved } = useTheme();
  const klineQuery = useQuery({
    queryKey: ["/api/kline", symbol],
    queryFn: () =>
      api<{ points: KlinePoint[]; source: string; error?: string }>(
        `/api/kline?symbol=${encodeURIComponent(symbol)}&period=daily&limit=120`,
      ),
    enabled: open && !!symbol,
  });

  // K 线涨跌色跟随全局颜色主题（--color-up/--color-down：A股红涨绿跌，可切换海外）
  // 用 CSS var 直接写进 echarts option，ECharts canvas 渲染时由浏览器解析，
  // 主题/颜色方案切换时无需重算 option（canvas 内联 style 里的 var() 会随 document 变化）。
  // 这里保留取值是为了给 lineStyle/areaStyle（echarts 不支持 var() 语法在 canvas 填充里），
  // 因此依赖 resolved + data-scheme 变化来重算。
  const [colorTick, setColorTick] = useState(0);
  useEffect(() => {
    const root = document.documentElement;
    const mo = new MutationObserver(() => setColorTick((v) => v + 1));
    mo.observe(root, { attributes: true, attributeFilter: ["data-scheme", "class", "data-theme"] });
    return () => mo.disconnect();
  }, []);

  const points = klineQuery.data?.points ?? [];
  const source = klineQuery.data?.source;
  const error = klineQuery.isError
    ? klineQuery.error instanceof Error
      ? klineQuery.error.message
      : String(klineQuery.error)
    : undefined;

  const option = useMemo(() => {
    const first = points[0]?.close;
    const last = points[points.length - 1]?.close;
    const up = first != null && last != null && last >= first;
    const rootStyle = getComputedStyle(document.documentElement);
    const lineColor = up
      ? rootStyle.getPropertyValue("--color-up").trim() || "#dc2626"
      : rootStyle.getPropertyValue("--color-down").trim() || "#059669";
    return {
      tooltip: { trigger: "axis", triggerOn: "click", renderMode: "richText", confine: true },
      grid: { left: 8, right: 8, top: 20, bottom: 4, containLabel: true },
      xAxis: { type: "category", data: points.map((p) => p.date), axisLabel: { fontSize: 10, color: axisLabelColor(resolved) } },
      yAxis: {
        type: "value",
        scale: true,
        axisLabel: { fontSize: 10, color: axisLabelColor(resolved) },
        splitLine: { lineStyle: { type: "dashed", color: "hsl(var(--border))" } },
      },
      series: [
        {
          type: "line",
          data: points.map((p) => p.close),
          symbol: "none",
          lineStyle: { width: 2, color: lineColor },
          itemStyle: { color: lineColor },
          areaStyle: { opacity: 0.08, color: lineColor },
          markLine:
            first != null
              ? {
                  silent: true,
                  symbol: "none",
                  label: { show: false },
                  lineStyle: { type: "dashed", color: "hsl(var(--muted-foreground) / 0.4)" },
                  data: [{ yAxis: first }],
                }
              : undefined,
        },
      ],
    };
  }, [points, resolved, colorTick]);
  useEChart(ref, points.length ? option : null, [points, resolved, colorTick]);

  return (
    <SidePanel
      open={open}
      onClose={() => onOpenChange(false)}
      title={`${name} ${symbol}`}
      z="z-50"
    >
      <div>
        {klineQuery.isPending ? (
          <div className="flex h-52 items-center justify-center text-xs text-muted-foreground">
            <Loader2 className="w-4 h-4 animate-spin mr-2" /> {tr("pos.loading")}
          </div>
        ) : error || !points.length ? (
          <div className="flex h-52 items-center justify-center text-xs text-muted-foreground px-4 text-center">
            {error || tr("pos.noKline")}
          </div>
        ) : (
          <>
            <div ref={ref} className="h-56 w-full" />
            <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
              <span>
                {tr("pos.klineInfo", { n: points.length })} · {source === "snapshot" ? tr("pos.snapshot") : tr("pos.realtime")}
              </span>
              {points.length >= 2 && (
                <span className={cn("tabular-nums", points[points.length - 1].close >= points[0].close ? "text-up" : "text-down")}>
                  {fmtMoney(points[points.length - 1].close)}
                </span>
              )}
            </div>
          </>
        )}
      </div>
    </SidePanel>
  );
}
