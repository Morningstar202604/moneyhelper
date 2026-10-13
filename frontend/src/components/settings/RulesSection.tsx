import { Wallet } from "lucide-react";
import { Section, inputCls, labelCls } from "./shared";
import { useI18n } from "@/lib/i18n";

/** 账本假设表单（月收入 / 应急目标 / 必选类别 / 储蓄比例），走底部批量保存 */
export function RulesSection({
  form,
  onField,
}: {
  form: Record<string, string>;
  onField: (k: string, v: string) => void;
}) {
  const { t } = useI18n();

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
    </Section>
  );
}
