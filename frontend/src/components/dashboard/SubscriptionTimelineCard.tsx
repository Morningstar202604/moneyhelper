/** 订阅时间线：把每月固定扣款按日期排在时间轴上，看清"钱在什么时候被扣走"。
 *
 * 为什么用时间线而不是列表：订阅的价值判断依赖"这个月的现金流会不会被
 * 集中抽干"。列表只看金额看不出时间分布；时间轴能直接看到扣款是否扎堆在月初。
 */

import { useMemo, useRef } from "react";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useEChart, usePalette, axisLabelColor } from "@/lib/charts";
import { useTheme } from "@/lib/theme";
import { useI18n } from "@/lib/i18n";
import { fmtMoney } from "@/lib/format";
import { useDashboard } from "@/lib/store";
import type { EChartsCoreOption } from "echarts/core";

export function SubscriptionTimelineCard() {
  const { t } = useI18n();
  const { dashboard: data, loading } = useDashboard();
  const ref = useRef<HTMLDivElement>(null);
  const palette = usePalette();
  const { resolved } = useTheme();

  const items = useMemo(() => {
    const raw = (data?.subscriptions?.items ?? []) as {
      name: string;
      monthly: number;
      due_day?: string;
    }[];
    return raw
      .map((s) => ({
        name: s.name,
        monthly: Number(s.monthly ?? 0),
        day: Number(s.due_day || 0) || 1,
      }))
      .filter((s) => s.monthly > 0)
      // 按扣款日排序：时间轴的语义就是"先后"
      .sort((a, b) => a.day - b.day);
  }, [data]);

  const option = useMemo<EChartsCoreOption | null>(() => {
    if (items.length === 0) return null;
    const total = items.reduce((s, x) => s + x.monthly, 0);
    return {
      tooltip: {
        trigger: "item",
        renderMode: "richText",
        confine: true,
        formatter: (p: { name: string; value: [number, number] }) => {
          const item = items.find((x) => x.name === p.name);
          return `${p.name}\n${t("chart.dueDay")} ${item?.day ?? "—"} · ${fmtMoney(Number(p.value?.[1] ?? 0))}`;
        },
      },
      grid: { left: 8, right: 16, top: 16, bottom: 24, containLabel: true },
      xAxis: {
        type: "value",
        name: t("chart.day"),
        min: 1,
        max: 31,
        splitNumber: 5,
        axisLabel: { fontSize: 10, color: axisLabelColor(resolved) },
        nameTextStyle: { fontSize: 10, color: axisLabelColor(resolved) },
        splitLine: { lineStyle: { opacity: 0.12 } },
      },
      yAxis: {
        type: "value",
        name: t("chart.amount"),
        axisLabel: {
          fontSize: 10,
          color: axisLabelColor(resolved),
          formatter: (v: number) => `${v}`,
        },
        nameTextStyle: { fontSize: 10, color: axisLabelColor(resolved) },
        splitLine: { lineStyle: { opacity: 0.12 } },
      },
      series: [
        {
          type: "graph",
          layout: "none",
          coordinateSystem: "cartesian2d",
          symbolSize: (val: number[]) => Math.max(10, Math.min(40, Number(val[1]) / 20)),
          label: {
            show: true,
            position: "top",
            fontSize: 9,
            color: axisLabelColor(resolved),
            formatter: (p: { name: string }) => p.name.slice(0, 6),
          },
          itemStyle: { color: palette[3] },
          data: items.map((x) => ({
            name: x.name,
            value: [x.day, x.monthly],
          })),
        },
        {
          // 一条水平参考线：订阅月支出均值，便于判断"哪笔偏大"
          type: "line",
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { type: "dashed", opacity: 0.5, color: palette[0] },
            label: { show: false },
            data: [{ yAxis: total / items.length }],
          },
          data: [],
        },
      ],
    };
  }, [items, palette, resolved, t]);

  useEChart(ref, option, [option]);

  if (loading) {
    return (
      <Card className="p-[var(--card-pad)]">
        <Skeleton className="h-4 w-24 mb-3" />
        <Skeleton className="h-40 w-full" />
      </Card>
    );
  }
  if (!option) return null;

  const total = items.reduce((s, x) => s + x.monthly, 0);
  const earliest = items[0];
  return (
    <Card className="p-[var(--card-pad)]">
      <div className="mb-1 flex items-baseline justify-between">
        <h3 className="text-sm font-medium">{t("chart.subscriptionTimeline")}</h3>
        <span className="text-xs tabular-nums text-muted-foreground">
          {t("chart.monthlyTotal")} {fmtMoney(total)}
        </span>
      </div>
      <p className="mb-1 text-xs text-muted-foreground">
        {t("chart.subscriptionHint", { n: items.length, day: earliest?.day ?? 1 })}
      </p>
      <div ref={ref} className="h-40 w-full" />
    </Card>
  );
}
