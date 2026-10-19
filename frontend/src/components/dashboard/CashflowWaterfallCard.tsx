/** 现金流瀑布图：收入 → 各项支出 → 结余，一眼看出钱从哪来往哪去。
 *
 * 为什么用瀑布而不是饼图：饼图只能表达"占比"，看不出"收入减支出等于结余"
 * 这个资金流动过程。瀑布图的每根柱子从上一步的位置继续，读者能顺着台阶读下去。
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

export function CashflowWaterfallCard() {
  const { t } = useI18n();
  const { dashboard: data, loading: isLoading } = useDashboard();
  const ref = useRef<HTMLDivElement>(null);
  const palette = usePalette();
  const { resolved } = useTheme();

  const option = useMemo<EChartsCoreOption | null>(() => {
    const cf = data?.cashflow;
    if (!cf) return null;
    const cats = (cf.by_category ?? []).slice(0, 6) as { category: string; amount: number }[];
    const income = Number(cf.income ?? 0);
    const net = Number(cf.net ?? 0);

    // 瀑布图构造：收入从 0 起；支出从收入往下；结余落在最终位置
    const labels = [t("chart.income"), ...cats.map((c) => c.category), t("chart.net")];
    const steps: number[] = [income, ...cats.map((c) => -Number(c.amount ?? 0)), net];
    const bases: number[] = [];
    const values: number[] = [];
    let running = 0;
    steps.forEach((v, i) => {
      if (i === 0) {
        bases.push(0);
        values.push(v);
        running = v;
      } else if (i === steps.length - 1) {
        bases.push(0);
        values.push(v);
      } else {
        const next = running + v;
        bases.push(Math.min(running, next));
        values.push(Math.abs(v));
        running = next;
      }
    });
    // 结余柱从 0 起画，其余从累加基线起
    const isTotal = labels.map((_, i) => i === 0 || i === steps.length - 1);
    const dataSeries = values.map((v, i) => ({
      value: isTotal[i] ? steps[i] : v,
      itemStyle: {
        color: isTotal[i]
          ? palette[0]
          : steps[i] >= 0
            ? palette[2]
            : palette[5],
      },
    }));

    return {
      tooltip: {
        trigger: "axis",
        renderMode: "richText",
        confine: true,
        formatter: (p: unknown) => {
          const arr = p as { name: string; value: number }[];
          return arr.map((x) => `${x.name}: ${fmtMoney(x.value)}`).join("\n");
        },
      },
      grid: { left: 8, right: 8, top: 16, bottom: 8, containLabel: true },
      xAxis: {
        type: "category",
        data: labels,
        axisLabel: { fontSize: 10, color: axisLabelColor(resolved), interval: 0, rotate: labels.length > 5 ? 30 : 0 },
        axisLine: { lineStyle: { color: axisLabelColor(resolved), opacity: 0.3 } },
      },
      yAxis: {
        type: "value",
        axisLabel: { fontSize: 10, color: axisLabelColor(resolved), formatter: (v: number) => `${Math.round(v / 1000)}k` },
        splitLine: { lineStyle: { opacity: 0.15 } },
      },
      series: [
        {
          type: "bar",
          stack: "total",
          silent: true,
          itemStyle: { color: "transparent" },
          // 透明底座把每根柱子抬到正确的累加高度
          data: bases.map((b, i) => (isTotal[i] ? 0 : b)),
        },
        {
          type: "bar",
          stack: "total",
          data: dataSeries,
          barMaxWidth: 40,
          label: {
            show: true,
            position: "top",
            fontSize: 9,
            color: axisLabelColor(resolved),
            formatter: (p: { value: number }) => `${(p.value / 1000).toFixed(1)}k`,
          },
        },
      ],
    };
  }, [data, palette, resolved, t]);

  useEChart(ref, option, [option]);

  if (isLoading) {
    return (
      <Card className="p-[var(--card-pad)]">
        <Skeleton className="h-4 w-24 mb-3" />
        <Skeleton className="h-44 w-full" />
      </Card>
    );
  }
  if (!option) return null;

  const cf = data?.cashflow;
  return (
    <Card className="p-[var(--card-pad)]">
      <div className="mb-1 flex items-baseline justify-between">
        <h3 className="text-sm font-medium">{t("chart.cashflow")}</h3>
        <span className="text-[11px] text-muted-foreground">{cf?.month}</span>
      </div>
      {/* 图表三层结构：结论 → 图表 → 明细（结论在这里，明细在下方数值行） */}
      <p className="mb-2 text-xs text-muted-foreground">
        {t("chart.cashflowHint", {
          income: fmtMoney(Number(cf?.income ?? 0)),
          net: fmtMoney(Number(cf?.net ?? 0)),
        })}
      </p>
      <div ref={ref} className="h-48 w-full" />
      <div className="mt-2 flex justify-between text-[11px] text-muted-foreground">
        <span>
          {t("chart.expense")} {fmtMoney(Number(cf?.expense ?? 0))}
        </span>
        <span>
          {t("chart.savingsRate")} {Number(cf?.savings_rate ?? 0).toFixed(1)}%
        </span>
      </div>
    </Card>
  );
}
