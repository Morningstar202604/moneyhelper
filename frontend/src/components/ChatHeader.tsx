import { memo } from "react";
import { ChevronDown, MessageCircle, Search, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { SessionItem } from "@/lib/types";

export interface ChatHeaderProps {
  threadId: string;
  sessions: SessionItem[];
  showSessions: boolean;
  sessionSearch: string;
  onToggleSessions: () => void;
  onCloseSessions: () => void;
  onSessionSearchChange: (v: string) => void;
  onSwitch: (threadId: string) => void;
  onNewSession: () => void;
}

/** 会话头：点当前会话可切换（移动端无侧栏，这是唯一入口）；移动端压缩高度把版面留给对话 */
export const ChatHeader = memo(({
  threadId,
  sessions,
  showSessions,
  sessionSearch,
  onToggleSessions,
  onCloseSessions,
  onSessionSearchChange,
  onSwitch,
  onNewSession,
}: ChatHeaderProps) => {
  const { t: tr } = useI18n();
  // 会话本地过滤（量小，无需后端）
  const kw = sessionSearch.trim().toLowerCase();
  const filteredSessions = kw
    ? sessions.filter((s) => s.title.toLowerCase().includes(kw))
    : sessions;

  return (
    <div className="relative flex items-center justify-between gap-2 px-4 py-2 border-b border-border/60 py-1.5 sm:py-2">
      <div className="relative min-w-0">
        <button
          type="button"
          className="text-xs text-muted-foreground inline-flex items-center gap-1 hover:text-foreground"
          onClick={onToggleSessions}
        >
          <MessageCircle className="w-3.5 h-3.5 shrink-0" />
          <span className="truncate">{tr("chat.currentSession")}</span>
          <ChevronDown className={cn("w-3 h-3 shrink-0 transition-transform", showSessions && "rotate-180")} />
        </button>
        {showSessions && (
          <>
            <div
              className="fixed inset-0 z-20"
              onClick={onCloseSessions}
              aria-hidden
            />
            <div className="absolute left-0 top-full mt-1 z-30 w-72 max-h-80 overflow-y-auto scroll-thin rounded-xl border border-border bg-card shadow-lift p-1.5">
              {sessions.length > 3 && (
                <div className="relative px-1 pt-1 pb-1.5">
                  <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
                  <input
                    type="search"
                    value={sessionSearch}
                    onChange={(e) => onSessionSearchChange(e.target.value)}
                    placeholder={tr("sidebar.searchSession")}
                    aria-label={tr("sidebar.searchSession")}
                    className="w-full rounded-lg border border-input bg-background pl-8 pr-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                </div>
              )}
              {filteredSessions.length === 0 ? (
                <div className="px-3 py-3 text-xs text-muted-foreground">
                  {sessionSearch.trim() ? tr("sidebar.noMatch") : tr("sidebar.noSessions")}
                </div>
              ) : (
                filteredSessions.slice(0, 30).map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    className={cn(
                      "w-full text-left truncate rounded-lg px-2.5 py-2 text-sm",
                      s.thread_id === threadId
                        ? "bg-accent text-accent-foreground font-medium"
                        : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                    )}
                    onClick={() => {
                      onCloseSessions();
                      if (s.thread_id !== threadId) onSwitch(s.thread_id);
                    }}
                  >
                    {s.title}
                  </button>
                ))
              )}
            </div>
          </>
        )}
      </div>
      <Button variant="ghost" size="sm" onClick={onNewSession}>
        <Sparkles className="w-3.5 h-3.5" /> {tr("chat.newSession")}
      </Button>
    </div>
  );
});

ChatHeader.displayName = "ChatHeader";
