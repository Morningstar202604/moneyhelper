import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { ProgressBar } from "./progress-bar";

/** 取 ProgressBar 内的「填充条」元素：outer wrapper 的唯一的 div 子元素 */
function fillEl(container: HTMLElement): HTMLElement {
  const outer = container.firstElementChild as HTMLElement;
  return outer.firstElementChild as HTMLElement;
}

describe("ProgressBar", () => {
  it("默认 50% 宽度 + 主色 class", () => {
    const { container } = render(<ProgressBar pct={50} />);
    const fill = fillEl(container);
    expect(fill.style.width).toBe("50%");
    // 50% 落在主色档（pct >= 50 → bg-primary）
    expect(fill.className).toContain("bg-primary");
  });

  it("pct >= 100 使用成功色", () => {
    const { container } = render(<ProgressBar pct={100} />);
    const fill = fillEl(container);
    expect(fill.className).toContain("bg-success");
  });

  it("pct < 50 使用 amber", () => {
    const { container } = render(<ProgressBar pct={30} />);
    const fill = fillEl(container);
    expect(fill.className).toContain("bg-amber-500");
  });

  it("pct > 100 被钳到 100%", () => {
    const { container } = render(<ProgressBar pct={999} />);
    const fill = fillEl(container);
    expect(fill.style.width).toBe("100%");
  });

  it("pct < 0 被钳到 0%", () => {
    const { container } = render(<ProgressBar pct={-10} />);
    const fill = fillEl(container);
    expect(fill.style.width).toBe("0%");
  });

  it("自定义 colorClass 覆盖比例配色", () => {
    const { container } = render(<ProgressBar pct={80} colorClass="bg-rose-500" />);
    const fill = fillEl(container);
    expect(fill.className).toContain("bg-rose-500");
  });

  it("自定义 bgClass 落到外层容器", () => {
    const { container } = render(<ProgressBar pct={60} bgClass="bg-zinc-800" />);
    const outer = container.firstChild as HTMLElement;
    expect(outer.className).toContain("bg-zinc-800");
  });

  it("自定义 className 落到外层容器", () => {
    const { container } = render(<ProgressBar pct={60} className="h-4" />);
    const outer = container.firstChild as HTMLElement;
    expect(outer.className).toContain("h-4");
  });
});
