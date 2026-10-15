import { useState } from "react";
import { Inbox, Languages, Moon, Settings, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { BrandLogo, BRAND } from "@/lib/brand";
import { useI18n } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";
import { useScheduledOutputs } from "@/lib/inbox";
import { ScheduledOutputsPanel } from "@/components/ScheduledOutputsPanel";

/**
 * 顶栏：极薄一条，只放品牌 + 右侧工具。
 * 没有 tab、没有面板开关——所有功能都在对话里，财务数据点卡片弹 modal。
 * 移动端额外承载收件箱入口（侧栏在移动端隐藏）。
 */
export function TopBar({
  onOpenSettings,
}: {
  onOpenSettings?: () => void;
}) {
  const { resolved, setTheme } = useTheme();
  const { lang, setLang, t } = useI18n();
  const { unread } = useScheduledOutputs();
  const [inboxOpen, setInboxOpen] = useState(false);

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
        {/* 收件箱：移动端专属（桌面端在左侧栏；md 以上隐藏避免重复入口） */}
        <button
          type="button"
          aria-label={t("inbox.title")}
          onClick={() => setInboxOpen(true)}
          className="relative inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground md:hidden"
        >
          <Inbox className="w-4 h-4" />
          {unread > 0 && (
            <span className="absolute right-1 top-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-primary px-0.5 text-[9px] font-semibold leading-none text-primary-foreground">
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </button>
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
      {/* 移动端收件箱（桌面端由左侧栏承载；此处仅 md 以下可达） */}
      <ScheduledOutputsPanel open={inboxOpen} onClose={() => setInboxOpen(false)} />
    </header>
  );
}
