import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import React from "react";
import { flushSync } from "react-dom";

// React 19 未公开导出 act，polyfill 回退到 flushSync 实现（最小可用版本）。
type ActCallback = () => void | Promise<void>;
if (typeof (React as unknown as { act?: unknown }).act !== "function") {
  (React as unknown as { act: (cb: ActCallback) => void }).act = (cb: ActCallback) => {
    flushSync(cb);
  };
}

// 让 @testing-library/react 知道当前处于 act 环境
(globalThis as Record<string, unknown>)["IS_REACT_ACT_ENVIRONMENT"] = true;

// 每次测试后清理 DOM，避免测试间污染
afterEach(() => {
  cleanup();
});
