import { SlidersHorizontal } from "lucide-react";
import { Segmented } from "@/components/ui/segmented";
import { Switch } from "@/components/ui/switch";
import { useTheme } from "@/lib/theme";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { Section } from "./shared";

/** 偏好设置（主题 / 语音 / 语言 / 涨跌配色 / 默认首页）；开关类即改即存，配色与首页走底部批量保存 */
export function PrefsSection({
  form,
  setColorScheme,
  setDefaultTab,
  onToggle,
}: {
  form: Record<string, string>;
  setColorScheme: (v: string) => void;
  setDefaultTab: (v: string) => void;
  onToggle: (k: string) => void;
}) {
  const { t, lang, setLang } = useI18n();
  const { theme: themeMode, setTheme } = useTheme();

  return (
    <Section title={t("settings.navPrefs")} icon={<SlidersHorizontal className="w-4 h-4 text-muted-foreground" />} desc={t("settings.prefsDesc")}>
      <div className="flex items-center justify-between">
        <span className="text-sm">{t("settings.theme")}</span>
        <Segmented
          value={themeMode}
          onChange={setTheme}
          options={[
            { value: "light", label: t("settings.light") },
            { value: "dark", label: t("settings.dark") },
            { value: "system", label: t("settings.system") },
          ]}
        />
      </div>
      <div className="mt-3 flex items-center justify-between">
        <div>
          <div className="text-sm">{t("settings.voice")}</div>
          <div className="text-[11px] text-muted-foreground mt-0.5">{t("settings.voiceHint")}</div>
        </div>
        <Switch checked={form.voice_input === "on"} onChange={() => onToggle("voice_input")} label={t("settings.voice")} />
      </div>
      <div className="mt-3 flex items-center justify-between">
        <div>
          <div className="text-sm">{t("settings.language")}</div>
          <div className="text-[11px] text-muted-foreground mt-0.5">{t("settings.languageHint")}</div>
        </div>
        <div className="flex gap-1.5">
          {(["en", "zh"] as const).map((l) => (
            <button
              key={l}
              type="button"
              onClick={() => setLang(l)}
              className={cn(
                "rounded-md px-2.5 py-1 text-xs font-medium border transition-colors",
                lang === l ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              {l === "en" ? "English" : "中文"}
            </button>
          ))}
        </div>
      </div>
      {/* 涨跌颜色：A股红涨绿跌 / 海外绿涨红跌 */}
      <div className="mt-3 flex items-center justify-between">
        <div>
          <div className="text-sm">{t("settings.colorScheme")}</div>
          <div className="text-[11px] text-muted-foreground mt-0.5">{t("settings.colorSchemeHint")}</div>
        </div>
        <Segmented
          value={form.color_scheme ?? "cn"}
          onChange={setColorScheme}
          options={[
            { value: "cn", label: t("settings.cnScheme") },
            { value: "us", label: t("settings.usScheme") },
          ]}
        />
      </div>
      {/* 默认首页 */}
      <div className="mt-3 flex items-center justify-between">
        <div>
          <div className="text-sm">{t("settings.defaultTab")}</div>
          <div className="text-[11px] text-muted-foreground mt-0.5">{t("settings.defaultTabHint")}</div>
        </div>
        <Segmented
          value={form.default_tab ?? "chat"}
          onChange={setDefaultTab}
          options={[
            { value: "chat", label: t("nav.chat") },
            { value: "features", label: t("nav.features") },
          ]}
        />
      </div>
    </Section>
  );
}
