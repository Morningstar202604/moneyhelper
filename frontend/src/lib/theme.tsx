/** 主题系统：浅色/深色/跟随系统，本机持久化（localStorage），即时生效，不依赖服务端。 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export type ThemeMode = "light" | "dark" | "system";

const KEYS = { theme: "wo.theme" };

interface ThemeState {
  theme: ThemeMode;
  /** 实际生效的明暗（system 已解析） */
  resolved: "light" | "dark";
  setTheme: (v: ThemeMode) => void;
}

const ThemeCtx = createContext<ThemeState | null>(null);

function load<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    return v ? (v as T) : fallback;
  } catch {
    return fallback;
  }
}

function save(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* ignore */
  }
}

function systemDark(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<ThemeMode>(() => load<ThemeMode>(KEYS.theme, "system"));

  const resolved: "light" | "dark" =
    theme === "system" ? (systemDark() ? "dark" : "light") : theme;

  // 明暗 -> html 属性
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", resolved === "dark");
    root.dataset.theme = resolved;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", resolved === "dark" ? "#0b1120" : "#f6f8fb");
  }, [resolved]);

  // 跟随系统切换（首帧与主 effect 一致；后续系统明暗变化只改 class 与 meta）
  useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => {
      const root = document.documentElement;
      root.classList.toggle("dark", mq.matches);
      const meta = document.querySelector('meta[name="theme-color"]');
      if (meta) meta.setAttribute("content", mq.matches ? "#0b1120" : "#f6f8fb");
    };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [theme]);

  const setTheme = useCallback((v: ThemeMode) => {
    setThemeState(v);
    save(KEYS.theme, v);
  }, []);

  const value = useMemo<ThemeState>(() => ({ theme, resolved, setTheme }), [theme, resolved, setTheme]);

  return <ThemeCtx.Provider value={value}>{children}</ThemeCtx.Provider>;
}

export function useTheme(): ThemeState {
  const ctx = useContext(ThemeCtx);
  if (!ctx) throw new Error("useTheme 必须在 ThemeProvider 内使用");
  return ctx;
}
