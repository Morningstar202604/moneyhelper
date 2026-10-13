import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { AlertBanner } from "./alert";

describe("AlertBanner", () => {
  it("warn variant 应包含 amber 相关 class", () => {
    const { container } = render(
      <AlertBanner tone="warn">警告信息</AlertBanner>
    );
    const classNames = container.firstChild as HTMLElement;
    expect(classNames.className).toContain("amber");
  });

  it("info variant 应包含 border-border class", () => {
    const { container } = render(
      <AlertBanner tone="info">提示信息</AlertBanner>
    );
    const classNames = container.firstChild as HTMLElement;
    expect(classNames.className).toContain("border-border");
  });

  it("默认 tone 为 warn", () => {
    const { container } = render(
      <AlertBanner>默认提示</AlertBanner>
    );
    const classNames = container.firstChild as HTMLElement;
    expect(classNames.className).toContain("amber");
  });

  it("应渲染 children 文本内容", () => {
    render(<AlertBanner tone="info">测试内容</AlertBanner>);
    expect(screen.getByText("测试内容")).toBeInTheDocument();
  });

  it("应渲染 action slot", () => {
    render(
      <AlertBanner tone="warn" action={<button>操作</button>}>
        带操作
      </AlertBanner>
    );
    expect(screen.getByText("操作")).toBeInTheDocument();
  });

  it("应渲染 icon slot", () => {
    render(
      <AlertBanner tone="info" icon={<span data-testid="icon">★</span>}>
        带图标
      </AlertBanner>
    );
    expect(screen.getByTestId("icon")).toBeInTheDocument();
  });

  it("自定义 className 应合并到容器", () => {
    const { container } = render(
      <AlertBanner tone="info" className="custom-class">自定义样式</AlertBanner>
    );
    const classNames = container.firstChild as HTMLElement;
    expect(classNames.className).toContain("custom-class");
  });
});
