import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { store, useBootstrap } from "@/lib/store";
import { useMutate } from "@/lib/use-mutate";
import { useI18n } from "@/lib/i18n";

/** 「保存设置」按钮覆盖的键（其余开关即时生效、AI 配置走独立保存）。 */
export const BATCH_KEYS = [
  "monthly_income",
  "emergency_target_months",
  "essential_categories",
  "savings_goal",
  "report_time",
] as const;

type SectionId = "prefs" | "rules" | "budget" | "ai" | "agent" | "report" | "memory" | "data" | "token" | "logs" | "audit";

export function useSettingsForm() {
  const { t } = useI18n();
  const { bootstrap } = useBootstrap();
  const [form, setForm] = useState<Record<string, string>>({});

  useEffect(() => {
    if (bootstrap) setForm({ ...bootstrap.settings });
  }, [bootstrap]);

  // hooks 必须无条件调用：bootstrap 为 null 时的 loading 早退放在 hooks 之后
  const saveMutate = useMutate<undefined, void>({
    fn: async () => {
      const settings: Record<string, string> = {};
      for (const k of BATCH_KEYS) if (form[k] !== undefined) settings[k] = form[k];
      const res = await api<{ ok: boolean; errors: string[] }>("/api/settings", {
        method: "PUT",
        body: JSON.stringify({ settings }),
      });
      if (res.errors.length) throw new Error(`${t("settings.saveFail")}: ${res.errors.join("; ")}`);
      await store.refreshBootstrap();
      return undefined;
    },
    key: "settings.saved",
  });

  const toggleMutate = useMutate<{ k: string; v: string }, void>({
    fn: async (a) => {
      const res = await api<{ ok: boolean; errors: string[] }>("/api/settings", {
        method: "PUT",
        body: JSON.stringify({ settings: { [a.k]: a.v } }),
      });
      if (res.errors.length) throw new Error(`${t("settings.saveFail")}: ${res.errors.join("; ")}`);
      await store.refreshBootstrap();
      return undefined;
    },
    key: undefined,
  });

  const reset = useMutate<undefined, void>({
    fn: async () => {
      await api("/api/portfolio/reset", { method: "POST" });
      await store.refreshBootstrap();
      return undefined;
    },
    key: "settings.demoRestored",
  });

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  /** 开关类即改即生效（与外观一致，无需点保存按钮）。 */
  const toggle = (k: string) => {
    const v = form[k] === "on" ? "off" : "on";
    set(k, v);
    void toggleMutate.mutate({ k, v });
  };

  return {
    bootstrap,
    form,
    saveMutate,
    toggleMutate,
    reset,
    set,
    toggle,
  };
}

export type { SectionId };
