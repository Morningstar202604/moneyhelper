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

  // 横向条形：一行一个订阅，长度=月费，右侧标出扣款日。
  // 原先用「散点 + 气泡大小」表达金额：¥2,034 的单点被放大到占半张图，
  // 而 ¥18 的点小到看不见，读者无法比较——条形长度是更可靠的编码通道。
  const option = useMemo<EChartsCoreOption | null>(() => {
    if (items.length === 0) return null;
    const avg = items.reduce((s, x) => s + x.monthly, 0) / items.length;
    const rows = [...items].sort((a, b) => a.monthly - b.monthly);
    return {
      tooltip: {
        trigger: "item",
        renderMode: "richText",
        confine: true,
        formatter: (p: { name: string; value: number }) => {
          const item = items.find((x) => x.name === p.name);
          return `${p.name}
${t("chart.dueDay")} ${item?.day ?? "—"} · ${fmtMoney(p.value)}`;
        },
      },
      grid: { left: 8, right: 56, top: 8, bottom: 8, containLabel: true },
      xAxis: { type: "value", show: false },
      yAxis: {
        type: "category",
        data: rows.map((x) => `${x.name} · ${x.day}${t("chart.dayShort")}`),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { fontSize: 11, color: axisLabelColor(resolved), width: 110, overflow: "truncate" },
      },
      series: [
        {
          type: "bar",
          data: rows.map((x) => x.monthly),
          barWidth: 12,
          itemStyle: { color: palette[3], borderRadius: 3 },
          label: {
            show: true,
            position: "right",
            fontSize: 11,
            color: axisLabelColor(resolved),
            formatter: (p: { value: number }) => fmtMoney(p.value),
          },
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { type: "dashed", opacity: 0.5, color: palette[0] },
            label: { show: false },
            data: [{ xAxis: avg }],
          },
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
