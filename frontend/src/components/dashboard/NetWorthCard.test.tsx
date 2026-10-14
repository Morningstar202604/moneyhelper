import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { NetWorthCard } from "./NetWorthCard";

// Mock hooks from use-calculations
const mockUseNetWorth = vi.fn();
vi.mock("@/lib/use-calculations", () => ({
  useNetWorth: () => mockUseNetWorth(),
}));

const mockUseI18n = vi.fn();
vi.mock("@/lib/i18n", () => ({
  useI18n: () => mockUseI18n(),
}));

const mockUseTheme = vi.fn();
vi.mock("@/lib/theme", () => ({
  useTheme: () => mockUseTheme(),
}));

function setupHook(opts: { data?: unknown; loading?: boolean; error?: boolean }) {
  if (opts.loading) {
    mockUseNetWorth.mockReturnValue({ data: undefined, isLoading: true, isError: false });
  } else if (opts.error) {
    mockUseNetWorth.mockReturnValue({ data: undefined, isLoading: false, isError: true });
  } else {
    mockUseNetWorth.mockReturnValue({ data: opts.data, isLoading: false, isError: false });
  }
  mockUseI18n.mockReturnValue({ t: (k: string) => k });
  mockUseTheme.mockReturnValue({ resolved: "light" });
}

describe("NetWorthCard", () => {
  it("加载中态渲染骨架屏", () => {
    setupHook({ loading: true });
    const { container } = render(<NetWorthCard />);
    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
  });

  it("错误态显示加载失败文案", () => {
    setupHook({ error: true });
    render(<NetWorthCard />);
    expect(screen.getByText("netWorth.loadFail")).toBeInTheDocument();
  });

  it("空数据（全部为 0）优雅降级", () => {
    setupHook({
      data: {
        date: "2026-01-01",
        total_assets: 0,
        total_liabilities: 0,
        net_worth: 0,
        asset_breakdown: {},
        liability_breakdown: {},
      },
    });
    render(<NetWorthCard />);
    expect(screen.getByText("netWorth.title")).toBeInTheDocument();
  });

  it("有负债数据时渲染负债明细（后端 dict 契约 + 利率）", () => {
    setupHook({
      data: {
        date: "2026-01-01",
        total_assets: 70000,
        total_liabilities: 10000,
        net_worth: 60000,
        // 后端 /api/calculations/net-worth 实际返回 {名称: 金额} dict
        asset_breakdown: { 持仓: 50000, 现金: 20000 },
        liability_breakdown: { 房贷: 10000 },
        liability_rates: { 房贷: 0.035 },
      },
    });
    render(<NetWorthCard />);
    expect(screen.getByText("房贷")).toBeInTheDocument();
    expect(screen.getByText("3.50%")).toBeInTheDocument();
    expect(screen.getByText("netWorth.liabilityDetail")).toBeInTheDocument();
  });

  it("净资产为负时显示 negative badge", () => {
    setupHook({
      data: {
        date: "2026-01-01",
        total_assets: 6000,
        total_liabilities: 20000,
        net_worth: -14000,
        asset_breakdown: {},
        liability_breakdown: {},
      },
    });
    render(<NetWorthCard />);
    expect(screen.getByText("netWorth.negative")).toBeInTheDocument();
  });
});
