import { useState } from "react";
import { Sparkles } from "lucide-react";
import { Wallet } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { Section, inputCls, labelCls } from "./shared";
import { useI18n } from "@/lib/i18n";

/** 账本假设表单（月收入 / 应急目标 / 必选类别 / 储蓄比例），走底部批量保存。
 *  「AI 建议假设」按近两月收支生成建议，采用后填入表单（仍需底部保存生效）。 */
export function RulesSection({
  form,
  onField,
}: {
  form: Record<string, string>;
  onField: (k: string, v: string) => void;
}) {
  const { t } = useI18n();
  const { toast } = useToast();
  const [busy, setBusy] = useState(false);
  const [sugg, setSugg] = useState<{
    monthly_income: number;
    emergency_target_months: number;
    essential_categories: string;
    savings_goal: number;
  } | null>(null);

  const suggest = async () => {
    setBusy(true);
    setSugg(null);
    try {
      const d = await api<{
        ok: boolean;
        suggestion?: typeof sugg;
        error?: string;
      }>("/api/rules/suggest", { method: "POST", body: JSON.stringify({}) });
      if (d.ok && d.suggestion) setSugg(d.suggestion);
      else toast(String(d.error || t("settings.rulesAiFail")), "error");
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    } finally {
      setBusy(false);
    }
  };

  const apply = () => {
    if (!sugg) return;
    onField("monthly_income", String(sugg.monthly_income));
    onField("emergency_target_months", String(sugg.emergency_target_months));
    onField("essential_categories", sugg.essential_categories);
    onField("savings_goal", String(sugg.savings_goal));
    toast(t("settings.rulesAiApplied"), "ok");
  };

  return (
    <Section title={t("settings.navRules")} icon={<Wallet className="w-4 h-4 text-muted-foreground" />} desc={t("settings.rulesDesc")}>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={labelCls}>{t("settings.monthlyIncome")}</label>
          <input className={inputCls} type="number" value={form.monthly_income ?? ""} onChange={(e) => onField("monthly_income", e.target.value)} />
        </div>
        <div>
          <label className={labelCls}>{t("settings.emergencyTarget")}</label>
          <input className={inputCls} type="number" value={form.emergency_target_months ?? ""} onChange={(e) => onField("emergency_target_months", e.target.value)} />
        </div>
        <div className="col-span-2">
          <label className={labelCls}>{t("settings.essentialCats")}</label>
          <input className={inputCls} value={form.essential_categories ?? ""} onChange={(e) => onField("essential_categories", e.target.value)} placeholder={t("settings.essentialPh")} />
        </div>
        <div>
          <label className={labelCls}>{t("settings.savingsGoal")}</label>
          <input className={inputCls} type="number" value={form.savings_goal ?? "20"} onChange={(e) => onField("savings_goal", e.target.value)} />
        </div>
      </div>

      {/* AI 建议账本假设：按近两月收支生成，采用后填入表单 */}
      <div className="mt-3 rounded-lg border border-dashed border-primary/30 bg-primary/5 p-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <div className="text-sm">{t("settings.rulesAi")}</div>
            <div className="text-xs text-muted-foreground mt-0.5">{t("settings.rulesAiHint")}</div>
          </div>
          <Button variant="outline" size="sm" onClick={() => void suggest()} disabled={busy}>
            <Sparkles className="w-3.5 h-3.5" /> {busy ? t("settings.budgetAiBusy") : t("settings.budgetAiBtn")}
          </Button>
        </div>
        {sugg && (
          <div className="mt-2 rounded-md border border-border bg-card p-2.5">
            <div className="grid grid-cols-2 gap-1 text-xs">
              <span className="text-muted-foreground">{t("settings.monthlyIncome")}</span>
              <span className="text-right tabular-nums">{sugg.monthly_income}</span>
              <span className="text-muted-foreground">{t("settings.emergencyTarget")}</span>
              <span className="text-right tabular-nums">{sugg.emergency_target_months}</span>
              <span className="text-muted-foreground">{t("settings.savingsGoal")}</span>
              <span className="text-right tabular-nums">{sugg.savings_goal}%</span>
              <span className="text-muted-foreground">{t("settings.essentialCats")}</span>
              <span className="text-right">{sugg.essential_categories}</span>
            </div>
            <div className="mt-2 flex gap-1.5">
              <Button size="sm" onClick={apply}>
                {t("settings.budgetAiAdopt")}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => void suggest()}>
                {t("settings.budgetAiAgain")}
              </Button>
            </div>
          </div>
        )}
      </div>
    </Section>
  );
}
