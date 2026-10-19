import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MobileDrawer } from "@/components/MobileDrawer";

vi.mock("@/lib/i18n", () => ({
  useI18n: vi.fn(() => ({ t: (k: string) => k })),
}));

describe("MobileDrawer", () => {
  it("关闭时不渲染", () => {
    render(
      <MobileDrawer open={false} onClose={() => {}}>
        <div>内容</div>
      </MobileDrawer>,
    );
    expect(screen.queryByText("内容")).not.toBeInTheDocument();
  });

  it("打开时渲染内容并标记为模态对话框", () => {
    render(
      <MobileDrawer open onClose={() => {}}>
        <div>会话列表</div>
      </MobileDrawer>,
    );
    expect(screen.getByText("会话列表")).toBeInTheDocument();
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
  });

  it("打开时锁定背景滚动（移动端关键体验）", () => {
    render(
      <MobileDrawer open onClose={() => {}}>
        <div>内容</div>
      </MobileDrawer>,
    );
    expect(document.body.style.overflow).toBe("hidden");
  });

  it("关闭后恢复背景滚动", () => {
    const { rerender } = render(
      <MobileDrawer open onClose={() => {}}>
        <div>内容</div>
      </MobileDrawer>,
    );
    expect(document.body.style.overflow).toBe("hidden");
    rerender(
      <MobileDrawer open={false} onClose={() => {}}>
        <div>内容</div>
      </MobileDrawer>,
    );
    expect(document.body.style.overflow).not.toBe("hidden");
  });

  it("点遮罩关闭", async () => {
    const onClose = vi.fn();
    render(
      <MobileDrawer open onClose={onClose}>
        <div>内容</div>
      </MobileDrawer>,
    );
    // 遮罩是 aria-hidden 的兄弟节点，点它触发关闭
    const overlay = document.querySelector('[aria-hidden="true"]') as HTMLElement;
    expect(overlay).toBeTruthy();
    await userEvent.click(overlay);
    expect(onClose).toHaveBeenCalled();
  });

  it("Esc 关闭", async () => {
    const onClose = vi.fn();
    render(
      <MobileDrawer open onClose={onClose}>
        <div>内容</div>
      </MobileDrawer>,
    );
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });

  it("只在移动端显示（md 以上隐藏）", () => {
    render(
      <MobileDrawer open onClose={() => {}}>
        <div>内容</div>
      </MobileDrawer>,
    );
    const wrapper = screen.getByText("内容").closest(".fixed");
    expect(wrapper?.className).toContain("md:hidden");
  });
});
