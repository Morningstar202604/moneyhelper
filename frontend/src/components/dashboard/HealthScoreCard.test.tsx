import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { HealthScoreCard } from "./HealthScoreCard";

const mockUseHealthScore = vi.fn();
const mockUseI18n = vi.fn();

vi.mock("@/lib/use-calculations", () => ({
  useHealthScore: () => mockUseHealthScore(),
}));

vi.mock("@/lib/i18n", () => ({
  useI18n: () => mockUseI18n(),
}));

function setup(opts: { data?: unknown; loading?: boolean; error?: boolean }) {
  if (opts.loading) {
    mockUseHealthScore.mockReturnValue({ data: undefined, isLoading: true, isError: false });
  } else if (opts.error) {
    mockUseHealthScore.mockReturnValue({ data: undefined, isLoading: false, isError: true });
  } else {
    mockUseHealthScore.mockReturnValue({ data: opts.data, isLoading: false, isError: false });
  }
  mockUseI18n.mockReturnValue({ t: (k: string) => k });
}

describe("HealthScoreCard", () => {
  it("加载中态渲染骨架屏", () => {
    setup({ loading: true });
    const { container } = render(<HealthScoreCard />);
    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
  });

  it("错误态显示加载失败", () => {
    setup({ error: true });
    render(<HealthScoreCard />);
    expect(screen.getByText("health.loadFail")).toBeInTheDocument();
  });

  it("各等级图渲染对应颜色", () => {
    const grades = [
      { grade: "A", score: 90 },
      { grade: "B", score: 75 },
      { grade: "C", score: 55 },
      { grade: "D", score: 35 },
      { grade: "F", score: 10 },
    ];

    for (const g of grades) {
      setup({
        data: {
          score: g.score,
          grade: g.grade,
          breakdown: {
            savings_rate: { score: g.score, max: 20, label: "储蓄率", detail: "储蓄率 20%" },
          },
        },
      });
      const { unmount } = render(<HealthScoreCard />);
      expect(screen.getByText(`health.grade ${g.grade}`)).toBeInTheDocument();
      unmount();
    }
  });

  it("五维度评分各渲染一个进度条", () => {
    setup({
      data: {
        score: 68,
        grade: "B",
        breakdown: {
          savings_rate: { score: 14, max: 20, label: "储蓄率", detail: "建议增加储蓄" },
          dti: { score: 12, max: 20, label: "负债收入比", detail: "建议降低负债" },
          emergency_fund_months: { score: 16, max: 20, label: "应急金覆盖率", detail: "良好" },
          concentration_risk: { score: 10, max: 20, label: "集中度风险", detail: "建议分散" },
          investment_diversity: { score: 15, max: 20, label: "投资多样性", detail: "良好" },
        },
      },
    });
    render(<HealthScoreCard />);
    expect(screen.getByText("储蓄率")).toBeInTheDocument();
    expect(screen.getByText("负债收入比")).toBeInTheDocument();
    expect(screen.getByText("应急金覆盖率")).toBeInTheDocument();
    expect(screen.getByText("建议增加储蓄")).toBeInTheDocument();
  });
});
