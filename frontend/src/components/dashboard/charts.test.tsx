import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

/** 新图表的渲染契约：有数据时出标题与结论，无数据时不渲染（不显示空图表）。 */

vi.mock("@/lib/i18n", () => ({
  useI18n: vi.fn(() => ({ t: (k: string, v?: Record<string, unknown>) => (v ? `${k}:${JSON.stringify(v)}` : k), lang: "zh" })),
}));
vi.mock("@/lib/theme", () => ({ useTheme: vi.fn(() => ({ resolved: "light" })) }));
vi.mock("@/lib/charts", () => ({
  useEChart: vi.fn(),
  usePalette: vi.fn(() => ["#0d7a66", "#2f6fed", "#16a34a", "#d97706", "#7c5cd6"]),
  axisLabelColor: vi.fn(() => "#64748b"),
}));
vi.mock("@/lib/store", () => ({ useDashboard: vi.fn() }));
vi.mock("@/lib/use-calculations", () => ({ useHealthScore: vi.fn() }));

import { useDashboard } from "@/lib/store";
import { useHealthScore } from "@/lib/use-calculations";
import { CashflowWaterfallCard } from "@/components/dashboard/CashflowWaterfallCard";
import { ExpenseTreemapCard } from "@/components/dashboard/ExpenseTreemapCard";
import { SubscriptionTimelineCard } from "@/components/dashboard/SubscriptionTimelineCard";
import { HealthRadarCard } from "@/components/dashboard/HealthRadarCard";

const dashboard = {
  cashflow: {
    month: "2026-10",
    income: 24800,
    expense: 21265,
    net: 3535,
    savings_rate: 14.3,
    by_category: [
      { category: "居住", amount: 5200 },
      { category: "购物", amount: 4300 },
    ],
  },
  subscriptions: {
    items: [
      { name: "云盘会员", monthly: 14, due_day: "1" },
      { name: "健身私教", monthly: 1999, due_day: "5" },
    ],
  },
};

const health = {
  score: 51,
  grade: "D",
  breakdown: {
    savings: { score: 7, max: 20, label: "储蓄率", detail: "" },
    dti: { score: 12, max: 20, label: "负债收入比", detail: "" },
  },
};

describe("Dashboard 图表", () => {
  it("现金流瀑布：有数据时出标题与结论", () => {
    (useDashboard as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      dashboard,
      loading: false,
    });
    render(<CashflowWaterfallCard />);
    expect(screen.getByText("chart.cashflow")).toBeInTheDocument();
    // 结论行带上收入与结余（三层结构的第一层）
    expect(screen.getByText(/chart.cashflowHint/)).toBeInTheDocument();
  });

  it("现金流瀑布：无数据时不渲染", () => {
    (useDashboard as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      dashboard: null,
      loading: false,
    });
    const { container } = render(<CashflowWaterfallCard />);
    expect(container).toBeEmptyDOMElement();
  });

  it("支出结构：显示最大支出分类", () => {
    (useDashboard as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      dashboard,
      loading: false,
    });
    render(<ExpenseTreemapCard />);
    expect(screen.getByText("chart.expenseTree")).toBeInTheDocument();
    // "居住"会同时出现在结论行与明细列表，用 getAllByText
    expect(screen.getAllByText(/居住/).length).toBeGreaterThan(0);
  });

  it("支出结构：无分类时不渲染", () => {
    (useDashboard as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      dashboard: { cashflow: { by_category: [] } },
      loading: false,
    });
    const { container } = render(<ExpenseTreemapCard />);
    expect(container).toBeEmptyDOMElement();
  });

  it("订阅时间线：显示月合计与项数", () => {
    (useDashboard as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      dashboard,
      loading: false,
    });
    render(<SubscriptionTimelineCard />);
    expect(screen.getByText("chart.subscriptionTimeline")).toBeInTheDocument();
    expect(screen.getByText(/chart.monthlyTotal/)).toBeInTheDocument();
  });

  it("健康五维：指出最弱维度", () => {
    (useHealthScore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: health,
      isLoading: false,
    });
    render(<HealthRadarCard />);
    expect(screen.getByText("chart.healthRadar")).toBeInTheDocument();
    // 最弱是储蓄率 7 分
    expect(screen.getByText(/储蓄率/)).toBeInTheDocument();
  });

  it("健康五维：无 breakdown 时不渲染", () => {
    (useHealthScore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: { score: 0, grade: "-", breakdown: {} },
      isLoading: false,
    });
    const { container } = render(<HealthRadarCard />);
    expect(container).toBeEmptyDOMElement();
  });

  it("加载中显示骨架而不是空图表", () => {
    (useDashboard as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      dashboard: null,
      loading: true,
    });
    const { container } = render(<CashflowWaterfallCard />);
    // Skeleton 的具体类名随实现变化，断言"有占位块 + 没有图表标题"更稳
    expect(container.querySelectorAll("div").length).toBeGreaterThan(0);
    expect(screen.queryByText("chart.cashflow")).not.toBeInTheDocument();
  });
});
