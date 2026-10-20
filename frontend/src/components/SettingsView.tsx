import { useState } from "react";
import { motion } from "framer-motion";
import { ChevronDown } from "lucide-react";
import {
  Bot, Brain, BrainCog, GitCompareArrows, KeyRound, Newspaper, PiggyBank, ScrollText, ShieldCheck, SlidersHorizontal, Wallet,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useDashboard } from "@/lib/store";
import { useI18n } from "@/lib/i18n";
import { useIsDesktop } from "@/lib/use-media-query";
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
import { ProvenanceSection } from "@/components/settings/ProvenanceSection";
import { Button } from "@/components/ui/button";
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
  { id: "provenance", labelKey: "settings.navProvenance", icon: GitCompareArrows },
];

const SECTION_GROUPS: { key: string; ids: SectionId[] }[] = [
  { key: "settings.groupGeneral", ids: ["prefs", "rules", "budget"] },
  { key: "settings.groupAi", ids: ["ai", "agent", "report", "memory"] },
  { key: "settings.groupData", ids: ["data", "token", "logs", "audit", "provenance"] },
];

export function SettingsView() {
  const { t } = useI18n();
  const { dashboard } = useDashboard();
  const isDesktop = useIsDesktop();
  const { bootstrap, form, saveMutate, toggleMutate, reset, set, toggle, resetForm, dirty } = useSettingsForm();

  // active tab 状态很小，直接放组件内即可
  const [active, setActive] = useState<SectionId>("prefs");
  // 手机端：分组折叠。桌面端常开侧栏，这个状态不参与渲染。
  const [openGroup, setOpenGroup] = useState<string | null>("settings.groupGeneral");

  if (!bootstrap) {
    return <div className="p-8 text-center text-sm text-muted-foreground">{t("settings.loading")}</div>;
  }

  const sectionButton = (s: (typeof SECTIONS)[number]) => {
    const Icon = s.icon;
    const on = active === s.id;
    return (
      <button
        key={s.id}
        type="button"
        aria-current={on ? "page" : undefined}
        // 不在这里收起分组：同组切换是高频操作，收起会让用户每次都要重新展开
        onClick={() => setActive(s.id)}
        className={cn(
          "flex flex-row items-center gap-1.5 rounded-lg px-2 py-2 text-xs transition-colors",
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
  };

  return (
    <div className="md:flex md:items-start md:gap-3">
      {/* 手机/平板：分组折叠。一次只展开一组，避免 11 个入口同时铺满首屏。
          用条件渲染而不是 md:hidden：隐藏的 DOM 仍会被读屏与自动化工具命中，
          同一入口出现两份可访问副本（与移动抽屉同一类问题）。 */}
      {!isDesktop && (
        <nav aria-label={t("nav.main")} className="mb-3 space-y-1">
          {SECTION_GROUPS.map((g) => {
            const ids = new Set<SectionId>(g.ids);
            const items = SECTIONS.filter((s) => ids.has(s.id));
            const expanded = openGroup === g.key;
            const containsActive = items.some((s) => s.id === active);
            return (
              <div key={g.key} className="rounded-lg border border-border">
                <button
                  type="button"
                  aria-expanded={expanded}
                  onClick={() => setOpenGroup(expanded ? null : g.key)}
                  className="flex w-full items-center justify-between px-3 py-2 text-sm"
                >
                  <span className={cn("font-medium", containsActive && "text-primary")}>{t(g.key)}</span>
                  <ChevronDown
                    className={cn("h-4 w-4 text-muted-foreground transition-transform", expanded && "rotate-180")}
                  />
                </button>
                {expanded && (
                  <div className="grid grid-cols-2 gap-1 border-t border-border p-1.5">
                    {items.map((s) => sectionButton(s))}
                  </div>
                )}
              </div>
            );
          })}
        </nav>
      )}

      {/* 桌面：常驻侧栏 */}
      {isDesktop && (
        <nav
          aria-label={t("nav.main")}
          className="w-48 shrink-0 sticky top-4 grid grid-cols-1 gap-1.5"
        >
          {SECTIONS.map((s) => sectionButton(s))}
        </nav>
      )}

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

        {active === "provenance" && <ProvenanceSection />}

        {dirty && (
          <div className="sticky bottom-0 z-10 -mx-1 flex items-center justify-between gap-3 border-t border-border bg-background/95 px-3 py-2 backdrop-blur">
            <span className="text-xs text-muted-foreground">{t("settings.unsavedHint")}</span>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => resetForm()}
                disabled={saveMutate.isPending}
              >
                {t("settings.discard")}
              </Button>
              <Button size="sm" onClick={() => void saveMutate.mutate(undefined)} disabled={saveMutate.isPending}>
                {saveMutate.isPending ? t("settings.saving") : t("settings.saveSettings")}
              </Button>
            </div>
          </div>
        )}
      </motion.div>
    </div>
  );
}
