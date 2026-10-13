import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { ScoreRing } from "./score-ring";

describe("ScoreRing", () => {
  it("渲染为 0 分时不画进度弧", () => {
    const { container } = render(<ScoreRing score={0} />);
    // score=0 → 进度 circle 不渲染（只有轨道 circle）
    const circles = container.querySelectorAll("circle");
    expect(circles.length).toBe(1); // 仅背景轨道
  });

  it("渲染为 80 分时画进度弧 + 自动选绿色", () => {
    const { container } = render(<ScoreRing score={80} />);
    const circles = container.querySelectorAll("circle");
    expect(circles.length).toBe(2); // 轨道 + 进度弧
    // 进度弧 stroke 是绿色系 (#10b981)
    const progressCircle = circles[1];
    expect(progressCircle.getAttribute("stroke")).toBe("#10b981");
  });

  it("渲染为 30 分时进度弧为橙色", () => {
    const { container } = render(<ScoreRing score={30} />);
    const circles = container.querySelectorAll("circle");
    expect(circles.length).toBe(2);
    const progressCircle = circles[1];
    expect(progressCircle.getAttribute("stroke")).toBe("#f97316");
  });

  it("渲染为 10 分时进度弧为红色", () => {
    const { container } = render(<ScoreRing score={10} />);
    const circles = container.querySelectorAll("circle");
    expect(circles.length).toBe(2);
    const progressCircle = circles[1];
    expect(progressCircle.getAttribute("stroke")).toBe("#ef4444");
  });

  it("自定义 color 覆盖自动颜色", () => {
    const { container } = render(<ScoreRing score={30} color="#123456" />);
    const circles = container.querySelectorAll("circle");
    const progressCircle = circles[1];
    expect(progressCircle.getAttribute("stroke")).toBe("#123456");
  });

  it("score > 100 被钳到 100，score < 0 被钳到 0", () => {
    const { container: c1 } = render(<ScoreRing score={150} size={48} strokeWidth={4} />);
    // circumference = 2 * PI * (48-4)/2 = 2 * PI * 22 ≈ 138.23
    // 150 clamped to 100 ⇒ dashLength = circumference
    expect(c1.querySelector("svg")).toBeTruthy();
    const circle = c1.querySelectorAll("circle")[1];
    const dashArr = circle.getAttribute("stroke-dasharray");
    expect(dashArr).toBeTruthy();
    expect(circle.style.display).not.toBe("none");

    const { container: c2 } = render(<ScoreRing score={-20} />);
    // negative clamped to 0 ⇒ no progress circle rendered
    const circles2 = c2.querySelectorAll("circle");
    expect(circles2.length).toBe(1);
  });

  it("传递 label 和 sublabel 时渲染文字", () => {
    const { container } = render(<ScoreRing score={75} label="健康" sublabel="得分" />);
    expect(container.textContent).toContain("75");
    expect(container.textContent).toContain("健康");
    expect(container.textContent).toContain("得分");
  });

  it("size 和 strokeWidth 传递到 SVG 属性", () => {
    const { container } = render(<ScoreRing score={50} size={120} strokeWidth={8} />);
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("width")).toBe("120");
    expect(svg?.getAttribute("height")).toBe("120");
  });
});
