import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DepartmentPanel } from "@/components/DepartmentPanel";

// 与 ImportPanel.test.tsx 一致：自包含 mock，避免 vi.mock 提升问题
vi.mock("@/lib/i18n", () => ({
  useI18n: vi.fn(() => ({ t: (k: string) => k, lang: "zh" })),
}));
vi.mock("@/lib/toast", () => ({
  useToast: vi.fn(() => ({ toast: vi.fn() })),
}));
vi.mock("@/lib/api", () => ({
  api: vi.fn(),
  apiStream: vi.fn(),
}));

import { api, apiStream } from "@/lib/api";

const seen = { api: api as unknown as ReturnType<typeof vi.fn>, apiStream: apiStream as unknown as ReturnType<typeof vi.fn> };

const ORDER_ACCOUNTING = {
  id: "o1",
  dept: "accounting" as const,
  task: "编制本期收支与结余报表",
  status: "pending" as const,
  metrics: {},
  tokens_used: 0,
  budget_tokens: 4000,
  error: "",
};

const REPORT = {
  report_id: "r1",
  question: "盘一下上季度",
  verdict: "4 个部门口径一致，可以直接决策。",
  report: "# 呈批件\n\n结论行",
  orders: [{ ...ORDER_ACCOUNTING, status: "done" as const, metrics: { expense: 21265 } }],
  conflicts: [],
  dispatch: "rules",
  status: "pending" as const,
};

describe("DepartmentPanel", () => {
  it("关闭时不渲染内容", () => {
    seen.api.mockResolvedValue({ reports: [] });
    render(<DepartmentPanel open={false} onClose={() => {}} />);
    expect(screen.queryByText("dept.desc")).not.toBeInTheDocument();
  });

  it("打开时加载历史呈批件", async () => {
    seen.api.mockResolvedValue({ reports: [REPORT] });
    render(<DepartmentPanel open onClose={() => {}} />);
    await waitFor(() => expect(seen.api).toHaveBeenCalled());
    expect(seen.api.mock.calls[0][0]).toContain("/api/department/reports");
  });

  it("派工后按事件流渲染工位并显示呈批件", async () => {
    seen.api.mockResolvedValue({ reports: [] });
    // 模拟后端 SSE：dept_start → dept(running/done) → dept_report
    seen.apiStream.mockImplementation(
      async (
        _path: string,
        _body: unknown,
        onLine: (obj: Record<string, unknown>) => void,
      ) => {
        onLine({ type: "dept_start", dispatch: "rules", orders: [ORDER_ACCOUNTING] });
        onLine({ type: "dept", order: { ...ORDER_ACCOUNTING, status: "running" } });
        onLine({
          type: "dept",
          order: {
            ...ORDER_ACCOUNTING,
            status: "done",
            metrics: { expense: 21265 },
            tokens_used: 120,
          },
        });
        onLine({ type: "dept_report", report: REPORT });
      },
    );

    render(<DepartmentPanel open onClose={() => {}} />);
    const input = screen.getByLabelText("dept.askPh");
    await userEvent.type(input, "盘一下上季度");
    await userEvent.click(screen.getByRole("button", { name: /dept.run/ }));

    await waitFor(() => expect(screen.getByText("dept.verdict")).toBeInTheDocument());
    expect(seen.apiStream).toHaveBeenCalledWith(
      "/api/department/stream",
      { question: "盘一下上季度", lang: "zh" },
      expect.any(Function),
      expect.anything(),
    );
    // 派工来源与结论都要显示
    expect(screen.getByText("dept.dispatch.rules")).toBeInTheDocument();
    expect(screen.getByText("4 个部门口径一致，可以直接决策。")).toBeInTheDocument();
  });

  it("显示对账冲突", async () => {
    seen.api.mockResolvedValue({ reports: [] });
    const conflicted = {
      ...REPORT,
      conflicts: [
        {
          metric: "expense",
          detail: "会计部报 21,265.00；记账部报 21,000.00",
          depts: ["accounting", "bookkeeping"],
        },
      ],
    };
    seen.apiStream.mockImplementation(
      async (_p: string, _b: unknown, onLine: (o: Record<string, unknown>) => void) => {
        onLine({ type: "dept_start", dispatch: "rules", orders: [ORDER_ACCOUNTING] });
        onLine({ type: "dept_report", report: conflicted });
      },
    );
    render(<DepartmentPanel open onClose={() => {}} />);
    await userEvent.type(screen.getByLabelText("dept.askPh"), "盘一下");
    await userEvent.click(screen.getByRole("button", { name: /dept.run/ }));
    await waitFor(() => expect(screen.getByText("dept.conflicts")).toBeInTheDocument());
    expect(screen.getByText(/会计部报 21,265/)).toBeInTheDocument();
  });

  it("驳回必须先填理由（点了不会直接发请求）", async () => {
    // 先给出一个 pending 呈批件
    seen.api.mockResolvedValue({ reports: [REPORT] });
    seen.apiStream.mockImplementation(
      async (_p: string, _b: unknown, onLine: (o: Record<string, unknown>) => void) => {
        onLine({ type: "dept_report", report: REPORT });
      },
    );
    render(<DepartmentPanel open onClose={() => {}} />);
    await userEvent.type(screen.getByLabelText("dept.askPh"), "盘一下");
    await userEvent.click(screen.getByRole("button", { name: /dept.run/ }));
    await waitFor(() => expect(screen.getByText("dept.reject")).toBeInTheDocument());

    seen.api.mockClear();
    await userEvent.click(screen.getByText("dept.reject"));
    // 没有理由时只展开输入框，不发审批请求
    expect(seen.api).not.toHaveBeenCalled();
    expect(screen.getByPlaceholderText("dept.rejectNotePh")).toBeInTheDocument();
  });

  it("批准后调用 decide 接口", async () => {
    seen.api.mockResolvedValue({ reports: [] });
    seen.apiStream.mockImplementation(
      async (_p: string, _b: unknown, onLine: (o: Record<string, unknown>) => void) => {
        onLine({ type: "dept_report", report: REPORT });
      },
    );
    render(<DepartmentPanel open onClose={() => {}} />);
    await userEvent.type(screen.getByLabelText("dept.askPh"), "盘一下");
    await userEvent.click(screen.getByRole("button", { name: /dept.run/ }));
    await waitFor(() => expect(screen.getByText("dept.approve")).toBeInTheDocument());

    seen.api.mockResolvedValue({ ok: true, report: { ...REPORT, status: "approved" } });
    await userEvent.click(screen.getByText("dept.approve"));
    await waitFor(() =>
      expect(seen.api).toHaveBeenCalledWith(
        "/api/department/reports/r1/decide",
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });

  it("已处理的呈批件不再显示审批按钮", async () => {
    const decided = { ...REPORT, status: "approved" as const, decision_note: "同意" };
    seen.api.mockResolvedValue({ reports: [decided] });
    seen.apiStream.mockImplementation(
      async (_p: string, _b: unknown, onLine: (o: Record<string, unknown>) => void) => {
        onLine({ type: "dept_report", report: decided });
      },
    );
    render(<DepartmentPanel open onClose={() => {}} />);
    await userEvent.type(screen.getByLabelText("dept.askPh"), "盘一下");
    await userEvent.click(screen.getByRole("button", { name: /dept.run/ }));
    // "dept.approved" 会同时出现在状态徽标与历史列表里，用 getAllByText
    await waitFor(() => expect(screen.getAllByText("dept.approved").length).toBeGreaterThan(0));
    // 审批按钮是 pending 专属，已处理时必须消失
    expect(screen.queryByText("dept.approve")).not.toBeInTheDocument();
  });

  it("历史列表点击可回看旧呈批件", async () => {
    const old = { ...REPORT, report_id: "r0", question: "上上季度的盘", status: "rejected" as const };
    seen.api.mockResolvedValue({ reports: [old] });
    render(<DepartmentPanel open onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText("上上季度的盘")).toBeInTheDocument());
    await userEvent.click(screen.getByText("上上季度的盘"));
    await waitFor(() => expect(screen.getByText("dept.secretary")).toBeInTheDocument());
  });
});
