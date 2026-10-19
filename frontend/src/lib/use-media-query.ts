import { useEffect, useState } from "react";

/**
 * 媒体查询 hook（SSR 安全，首帧用 fallback）。
 *
 * 为什么需要它：`hidden md:flex` 只做视觉隐藏，DOM 仍然存在——
 * 屏幕阅读器与自动化工具仍会读到被"隐藏"的按钮，导致同一功能出现两个
 * 可访问入口（例如移动端抽屉与桌面侧栏里各有一个「部门」按钮）。
 * 需要"真的不渲染"时用本 hook 判断，而不是靠 CSS 隐藏。
 *
 * @param query  例如 "(min-width: 768px)"
 * @param fallback 首帧与无 window 环境下的返回值
 */
export function useMediaQuery(query: string, fallback = false): boolean {
  const [matches, setMatches] = useState<boolean>(() => {
    if (typeof window === "undefined" || !window.matchMedia) return fallback;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia(query);
    const onChange = (e: MediaQueryListEvent) => setMatches(e.matches);
    // 订阅前同步一次：SSR 首帧或热重载后可能与实际不一致
    setMatches(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

/** 桌面断点（与 Tailwind md 一致：768px）。 */
export function useIsDesktop(): boolean {
  return useMediaQuery("(min-width: 768px)", true);
}
