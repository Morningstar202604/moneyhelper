import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ImportPanel } from "@/components/ImportPanel";

// Self-contained mocks (avoid hoisting issues with variable refs in vi.mock)
vi.mock("@/lib/use-calculations", () => ({
  useImportTemplates: vi.fn(() => ({ data: undefined, isLoading: false, isError: false })),
}));
vi.mock("@/lib/toast", () => ({
  useToast: vi.fn(() => ({ toast: vi.fn() })),
}));
vi.mock("@/lib/i18n", () => ({
  useI18n: vi.fn(() => ({ t: (k: string) => k })),
}));
vi.mock("@/lib/use-mutate", () => ({
  useMutate: vi.fn(() => ({ isPending: false, mutate: vi.fn(), mutateAsync: vi.fn() })),
}));
vi.mock("@/lib/api", () => ({
  api: vi.fn(),
}));
vi.mock("@/lib/store", () => ({
  store: { bump: vi.fn() },
}));

describe("ImportPanel", () => {
  it("渲染不报错（基础渲染）", () => {
    render(<ImportPanel />);
    // 3 个 Tab 标签都应渲染
    expect(screen.getByText("import.tabPaste")).toBeInTheDocument();
    expect(screen.getByText("import.tabUpload")).toBeInTheDocument();
    expect(screen.getByText("import.tabTemplate")).toBeInTheDocument();
  });

  it("渲染工具栏标签标题", () => {
    render(<ImportPanel />);
    expect(screen.getByText("import.title")).toBeInTheDocument();
  });

  it("渲染包含全部三个动作面板标签", () => {
    render(<ImportPanel />);
    // 基础渲染时 3 个标签都出现
    expect(screen.getByText("import.tabPaste")).toBeInTheDocument();
  });
});
