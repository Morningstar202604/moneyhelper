/** 桌面侧边栏：品牌 + 导航 + 会话列表 + 设置入口（符合人的使用逻辑：先有导航，再有历史会话）。 */

import { useState } from "react";
import { Plus, Search, Settings, Sunrise, Trash2, Pencil, MessageCircle, PanelLeftClose } from "lucide-react";
import { BrandLogo, BRAND } from "@/lib/brand";
import { useSessions } from "@/lib/store";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { MorningReportDialog } from "@/components/MorningReportDialog";
import type { SessionItem } from "@/lib/types";

/** 问AI 页的会话侧栏：品牌 + 会话历史（主导航已上移 TopBar） */
export function SessionSidebar({
  activeThread,
  onHome,
  onSelect,
  onNew,
  onDelete,
  onRename,
  onOpenSettings,
  onCollapse,
}: {
  activeThread: string | null;
  onHome: () => void;
  onSelect: (threadId: string | null) => void;
  onNew: () => void;
  onDelete: (id: number, threadId: string) => void;
  onRename: (id: number, title: string) => void;
  onOpenSettings: () => void;
  onCollapse: () => void;
}) {
  const { t } = useI18n();
  const { sessions } = useSessions();
  const [editing, setEditing] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [q, setQ] = useState("");
  const [reportOpen, setReportOpen] = useState(false);

  // 本地过滤：会话量小，无需后端接口
  const kw = q.trim().toLowerCase();
  const filtered = kw ? sessions.filter((s) => s.title.toLowerCase().includes(kw)) : sessions;
  // 会话多时折叠旧会话：默认只展开最近 30 条，避免长列表撑爆侧栏
  const [showAll, setShowAll] = useState(false);
  const visible = showAll || filtered.length <= 30 ? filtered : filtered.slice(0, 30);

  // 会话按时间分组：今天 / 过去 7 天 / 更早（对标 ChatGPT/Claude 的历史分组）
  const timeBucket = (iso: string): "today" | "week" | "older" => {
    const ts = new Date(iso).getTime();
    if (Number.isNaN(ts)) return "older";
    const days = (Date.now() - ts) / 86400000;
    if (days < 1) return "today";
    if (days < 7) return "week";
    return "older";
  };
  const GROUP_LABELS: { key: "today" | "week" | "older"; labelKey: string }[] = [
    { key: "today", labelKey: "sidebar.today" },
    { key: "week", labelKey: "sidebar.week" },
    { key: "older", labelKey: "sidebar.older" },
  ];

  // 相对时间（今天显示时:分，更早显示 M/D）：会话标题下的一行轻量元信息，
  // 帮助在一串同名「新会话」里快速定位（对标 ChatGPT 侧栏的时间辅助）
  const relTime = (iso: string): string => {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    if (sameDay) {
      return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    }
    return `${d.getMonth() + 1}/${d.getDate()}`;
  };

  const renderSession = (s: SessionItem) => (
    <div
      key={s.id}
      role="button"
      tabIndex={0}
      className={cn(
        "group flex items-center gap-1 rounded-[calc(var(--radius)-2px)] px-2 py-1.5 text-sm cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        s.thread_id === activeThread
          ? "bg-accent text-accent-foreground"
          : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
      )}
      onClick={() => onSelect(s.thread_id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(s.thread_id);
        }
      }}
    >
      {editing === s.id ? (
        <input
          autoFocus
          className="min-w-0 flex-1 rounded border border-input bg-background px-1.5 py-0.5 text-xs"
          value={editTitle}
          onChange={(e) => setEditTitle(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              onRename(s.id, editTitle.trim() || s.title);
              setEditing(null);
            }
            if (e.key === "Escape") setEditing(null);
          }}
          onClick={(e) => e.stopPropagation()}
        />
      ) : (
        <>
          <span className="min-w-0 flex-1 flex flex-col">
            <span className="truncate text-[13px] leading-tight">{s.title}</span>
            {relTime(s.updated_at) && (
              <span className="text-[11px] text-muted-foreground/70 leading-tight tabular-nums">
                {relTime(s.updated_at)}
              </span>
            )}
          </span>
          <span className="hidden group-hover:flex items-center gap-0.5 shrink-0">
            <button
              type="button"
              aria-label={t("sidebar.rename")}
              className="p-0.5 text-muted-foreground hover:text-foreground"
              onClick={(e) => {
                e.stopPropagation();
                setEditing(s.id);
                setEditTitle(s.title);
              }}
            >
              <Pencil className="w-3 h-3" />
            </button>
            <button
              type="button"
              aria-label={t("sidebar.deleteSession")}
              className="p-0.5 text-muted-foreground hover:text-red-600"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(s.id, s.thread_id);
              }}
            >
              <Trash2 className="w-3 h-3" />
            </button>
          </span>
        </>
      )}
    </div>
  );

  return (
    <div className="flex h-full flex-col">
      {/* 品牌：点击回总览首页；右侧折叠按钮把侧栏收成窄条，让位给主界面 */}
      <div className="flex items-center pr-1">
        <button
          type="button"
          className="flex items-center gap-2.5 px-4 py-3.5 text-left"
          onClick={onHome}
        >
          <BrandLogo size={30} />
          <span>
            <span className="block text-sm font-bold leading-tight">{BRAND.name}</span>
            <span className="block text-[11px] text-muted-foreground leading-tight">{t("brand.tagline")}</span>
          </span>
        </button>
        <button
          type="button"
          aria-label={t("sidebar.collapse")}
          onClick={onCollapse}
          className="ml-auto p-2 text-muted-foreground hover:text-primary transition-colors"
        >
          <PanelLeftClose className="w-4 h-4" />
        </button>
      </div>

      {/* 会话区 */}
      <div className="mt-4 flex-1 min-h-0 flex flex-col">
        <div className="flex items-center justify-between px-4 mb-1">
          <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            {t("sidebar.sessions")}
          </span>
          <span className="flex items-center gap-0.5">
            <button
              type="button"
              className="text-muted-foreground hover:text-primary p-2 -m-1"
              aria-label={t("report.generate")}
              onClick={() => setReportOpen(true)}
            >
              <Sunrise className="w-4 h-4" />
            </button>
            <button
              type="button"
              className="text-muted-foreground hover:text-primary p-2 -m-1"
              aria-label={t("sidebar.newSession")}
              onClick={onNew}
            >
              <Plus className="w-4 h-4" />
            </button>
          </span>
        </div>
        {/* 会话多了之后提供搜索（主流 agent 标配） */}
        {sessions.length > 3 && (
          <div className="px-2 mb-1">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
              <input
                type="search"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={t("sidebar.searchSession")}
                aria-label={t("sidebar.searchSession")}
                className="w-full rounded-lg border border-input bg-background pl-8 pr-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
          </div>
        )}
        <div className="flex-1 overflow-y-auto scroll-thin px-2 space-y-0.5">
          {filtered.length === 0 ? (
            <div className="px-3 py-6 text-center text-xs text-muted-foreground">
              <MessageCircle className="w-4 h-4 mx-auto mb-1.5 opacity-60" />
              {q.trim() ? t("sidebar.noMatch") : t("sidebar.noSessions")}
              {!q.trim() && (
                <>
                  <br />
                  {t("sidebar.startHint")}
                </>
              )}
            </div>
          ) : (
            <>
              {GROUP_LABELS.map((g) => {
                const items = visible.filter((s) => timeBucket(s.created_at) === g.key);
                if (items.length === 0) return null;
                return (
                  <div key={g.key} className="space-y-0.5">
                    <div className="px-2 pt-1.5 pb-0.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground/70">
                      {t(g.labelKey)}
                    </div>
                    {items.map(renderSession)}
                  </div>
                );
              })}
              {filtered.length > 30 && (
                <button
                  type="button"
                  className="w-full px-2 py-1.5 text-[11px] text-muted-foreground hover:text-foreground"
                  onClick={() => setShowAll((v) => !v)}
                >
                  {showAll ? t("sidebar.collapseOld") : t("sidebar.showOld", { n: filtered.length - 30 })}
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {/* 底部：设置入口 + 会话数 */}
      <div className="border-t border-border px-2 py-2">
        <button
          type="button"
          className="w-full flex items-center gap-2 rounded-[calc(var(--radius)-2px)] px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-foreground"
          onClick={onOpenSettings}
        >
          <Settings className="w-4 h-4" />
          {t("sidebar.settings")}
        </button>
        <div className="px-3 pt-1 text-[11px] text-muted-foreground">
          {sessions.length} {t("sidebar.sessionCount")} · {t("sidebar.localData")}
        </div>
      </div>

      {/* 今日晨报：手动触发一次（AI 生成 / 规则降级） */}
      <MorningReportDialog open={reportOpen} onOpenChange={setReportOpen} />
    </div>
  );
}
