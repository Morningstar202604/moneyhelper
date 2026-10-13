/** 轻量 i18n：默认 English，可切换中文，本地持久化，即时生效。
 * 文案字典：src/lib/lang/{en,zh}.ts（扁平 key）。
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { setMoneyLocale } from "./format";
import { en } from "./lang/en";
import { zh } from "./lang/zh";

export type Lang = "en" | "zh";

const KEYS = { lang: "wo.lang" };
const DICTS: Record<Lang, Record<string, string>> = { en, zh };

interface I18nState {
  lang: Lang;
  setLang: (v: Lang) => void;
  /** 取当前语言文案；缺失时回退英文，再缺失回退 key 本身。支持 {var} 占位替换。 */
  t: (key: string, vars?: Record<string, string | number>) => string;
}

const I18nCtx = createContext<I18nState | null>(null);

function load(): Lang {
  try {
    const v = localStorage.getItem(KEYS.lang);
    if (v === "zh" || v === "en") return v;
    // 未手动设置时跟随浏览器语言：中文环境默认中文（国内用户优先，不弹英文界面）
    return navigator.language.toLowerCase().startsWith("zh") ? "zh" : "en";
  } catch {
    return "zh";
  }
}

export function I18nProvider({ children }: { children: ReactNode }) {
  // load 时就同步货币本地化，避免首帧金额闪烁
  const [lang, setLangState] = useState<Lang>(() => {
    const l = load();
    setMoneyLocale(l);
    return l;
  });

  const setLang = useCallback((v: Lang) => {
    setLangState(v);
    setMoneyLocale(v);
    try {
      localStorage.setItem(KEYS.lang, v);
    } catch {
      /* ignore */
    }
  }, []);

  // 同步 <html lang>（利于无障碍与浏览器翻译提示）
  useEffect(() => {
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  }, [lang]);

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>) => {
      let v = DICTS[lang][key] ?? DICTS.en[key] ?? key;
      if (vars) {
        for (const [k, val] of Object.entries(vars)) {
          v = v.replaceAll(`{${k}}`, String(val));
        }
      }
      return v;
    },
    [lang],
  );

  const value = useMemo<I18nState>(() => ({ lang, setLang, t }), [lang, setLang, t]);
  return <I18nCtx.Provider value={value}>{children}</I18nCtx.Provider>;
}

export function useI18n(): I18nState {
  const ctx = useContext(I18nCtx);
  if (!ctx) throw new Error("useI18n 必须在 I18nProvider 内使用");
  return ctx;
}
