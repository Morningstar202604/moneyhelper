import { Languages, Moon, Settings, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { BrandLogo, BRAND } from "@/lib/brand";
import { useI18n } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";

/**
 * 顶栏：极薄一条，只放品牌 + 右侧工具。
 * 没有 tab、没有面板开关——所有功能都在对话里，财务数据点卡片弹 modal。
 */
export function TopBar({
  onOpenSettings,
}: {
  onOpenSettings?: () => void;
}) {
  const { resolved, setTheme } = useTheme();
  const { lang, setLang, t } = useI18n();

  return (
    <header className="sticky top-0 z-10 flex items-center justify-between gap-2 border-b border-border bg-background/80 backdrop-blur px-4 pt-[calc(0.375rem+env(safe-area-inset-top))] pb-1.5 sm:py-2">
      <div className="flex min-w-0 items-center gap-2">
        <span className="flex items-center gap-2 min-w-0 md:hidden">
          <BrandLogo size={24} />
        </span>
        <span className="hidden text-sm font-semibold text-foreground/80 leading-tight md:inline">
          {BRAND.name}
        </span>
      </div>

      <div className="flex items-center gap-1">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label={lang === "zh" ? "Switch to English" : "切换到中文"}
              onClick={() => setLang(lang === "zh" ? "en" : "zh")}
            >
              <Languages className="w-4 h-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {lang === "zh" ? t("topbar.toEn") : t("topbar.toZh")}
          </TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label={t("topbar.toggleTheme")}
              onClick={() => setTheme(resolved === "dark" ? "light" : "dark")}
            >
              {resolved === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {resolved === "dark" ? t("topbar.toggleLight") : t("topbar.toggleDark")}
          </TooltipContent>
        </Tooltip>
        {onOpenSettings && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon" aria-label={t("topbar.settings")} onClick={onOpenSettings}>
                <Settings className="w-4 h-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{t("topbar.settings")}</TooltipContent>
          </Tooltip>
        )}
      </div>
    </header>
  );
}
