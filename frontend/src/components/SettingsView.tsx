import { useState } from "react";
import { motion } from "framer-motion";
import {
  Bot, Brain, BrainCog, KeyRound, Newspaper, PiggyBank, ScrollText, ShieldCheck, SlidersHorizontal, Wallet,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useDashboard } from "@/lib/store";
import { useI18n } from "@/lib/i18n";
import { useSettingsForm, type SectionId } from "@/components/settings/use-settings-form";
import { PrefsSection } from "@/components/settings/PrefsSection";
import { RulesSection } from "@/components/settings/RulesSection";
import { BudgetSection } from "@/components/settings/BudgetSection";
import { AiSection } from "@/components/settings/AiSection";
import { ReportSection } from "@/components/settings/ReportSection";
import { MemorySection } from "@/components/settings/MemorySection";
import { DataSection } from "@/components/settings/DataSection";
import { TokenSection } from "@/components/settings/TokenSection";
import { LogsSection } from "@/components/settings/LogsSection";
import { AuditSection } from "@/components/settings/AuditSection";
import { AgentSection } from "@/components/settings/AgentSection";

const SECTIONS: { id: SectionId; labelKey: string; icon: typeof Wallet }[] = [
  { id: "prefs", labelKey: "settings.navPrefs", icon: SlidersHorizontal },
  { id: "rules", labelKey: "settings.navRules", icon: Wallet },
  { id: "budget", labelKey: "settings.navBudget", icon: PiggyBank },
  { id: "ai", labelKey: "settings.navAi", icon: Brain },
  { id: "agent", labelKey: "settings.navAgent", icon: Bot },
  { id: "report", labelKey: "settings.navReport", icon: Newspaper },
  { id: "memory", labelKey: "settings.navMemory", icon: BrainCog },
  { id: "data", labelKey: "settings.navData", icon: ShieldCheck },
  { id: "token", labelKey: "settings.navToken", icon: KeyRound },
  { id: "logs", labelKey: "settings.navLogs", icon: ScrollText },
  { id: "audit", labelKey: "settings.navAudit", icon: ShieldCheck },
];

export function SettingsView() {
  const { t } = useI18n();
  const { dashboard } = useDashboard();
  const { bootstrap, form, toggleMutate, reset, set, toggle } = useSettingsForm();

  // active tab 状态很小，直接放组件内即可
  const [active, setActive] = useState<SectionId>("prefs");

  if (!bootstrap) {
    return <div className="p-8 text-center text-sm text-muted-foreground">{t("settings.loading")}</div>;
  }

  return (
    <div className="md:flex md:items-start md:gap-3">
      <nav className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-1 gap-1.5 md:w-48 md:shrink-0 md:sticky md:top-4 mb-3 md:mb-0">
        {SECTIONS.map((s) => {
          const Icon = s.icon;
          const on = active === s.id;
          return (
            <button
              key={s.id}
              type="button"
              aria-current={on ? "page" : undefined}
              onClick={() => setActive(s.id)}
              className={cn(
                "flex flex-col md:flex-row items-center justify-center md:justify-start gap-1 rounded-lg px-2 py-2 text-xs transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                on
                  ? "bg-accent text-accent-foreground font-medium"
                  : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
              )}
            >
              <Icon className="w-4 h-4 shrink-0" />
              <span className="truncate">{t(s.labelKey)}</span>
            </button>
          );
        })}
      </nav>

      <motion.div
        key={active}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.15, ease: "easeOut" }}
        className="flex-1 min-w-0 space-y-3"
      >
        {active === "prefs" && (
          <PrefsSection
            form={form}
            setColorScheme={(v) => {
              set("color_scheme", v);
              toggleMutate.mutate({ k: "color_scheme", v });
            }}
            setDefaultTab={(v) => {
              set("default_tab", v);
              toggleMutate.mutate({ k: "default_tab", v });
            }}
            onToggle={toggle}
          />
        )}

        {active === "rules" && <RulesSection form={form} onField={set} />}

        {active === "budget" && <BudgetSection />}

        {active === "ai" && (
          <AiSection
            form={form}
            onField={set}
            onToggle={toggle}
            health={bootstrap.health}
            modelCatalog={bootstrap.model_catalog}
            enabledModels={bootstrap.enabled_models}
            onSaved={() => set("monthly_income", bootstrap.settings.monthly_income)}
          />
        )}

        {active === "report" && (
          <ReportSection form={form} onField={set} scheduler={bootstrap.scheduler} />
        )}

        {active === "agent" && <AgentSection />}

        {active === "memory" && <MemorySection />}

        {active === "data" && (
          <DataSection dashboard={dashboard} bootstrap={bootstrap} onRestoreDemo={() => void reset.mutate(undefined)} />
        )}

        {active === "token" && <TokenSection />}

        {active === "logs" && <LogsSection />}

        {active === "audit" && <AuditSection />}
      </motion.div>
    </div>
  );
}
