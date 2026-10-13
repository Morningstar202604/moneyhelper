import { useRef } from "react";
import { ArrowDown } from "lucide-react";
import { BRAND, BrandLogo } from "@/lib/brand";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { store, useBootstrap, useSessions } from "@/lib/store";
import { useI18n } from "@/lib/i18n";
import type { AgentToolStep, AgentPlanStep } from "@/lib/types";
import type { ChatMessage, StepInfo } from "@/components/ChatMessageBubble";
import { ChatHeader } from "@/components/ChatHeader";
import { ChatInput } from "@/components/ChatInput";
import { ChatMessageBubble } from "@/components/ChatMessageBubble";
import { FinishedMessages } from "@/components/FinishedMessages";
import { AgentPanel } from "@/components/AgentPanel";
import { useChatView } from "@/components/chat-view-state";

/** 空态首屏：4 条最常用示例（覆盖记账 / 行情 / 持仓 / 晨报），点即发送 */
const CAP_EXAMPLE_KEYS = [
  "chat.capBook1",
  "chat.capMarket2",
  "chat.capHold1",
  "chat.capAct1",
];

export function ChatView({
  threadId,
  locateRunId,
  onLocateDone,
  onNewSession,
  onSwitch,
  onOpenSettings,
  onNavigate,
}: {
  threadId: string;
  locateRunId?: number | null;
  onLocateDone?: () => void;
  onNewSession: () => void;
  onSwitch: (threadId: string) => void;
  onOpenSettings: () => void;
  onNavigate: (tab: string) => void;
}) {
  const { t: tr } = useI18n();
  const { bootstrap } = useBootstrap();
  const { sessions } = useSessions();
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const {
    messages, input, setInput, attachments,
    showSteps, showSessions, sessionSearch, setSessionSearch,
    scrolledUp, handleListScroll,
    voiceOn, exportOn, suggestions, hasData,
    stream, streamingMsg, finishedMessages, panelMsg,
    bubbleCallbacks, listening, scrollNow,
    stableSend, stableToggleVoice, stableToggleSessions,
    stableCloseSessions, stableSendInput, stableStop,
    uploadAttachment, removeAttachment, refreshBootstrap,
  } = useChatView({
    threadId,
    locateRunId,
    onLocateDone,
    inputRef,
    listRef,
  });

  return (
    <div className="flex h-full min-h-0">
      <div className="flex flex-col h-full flex-1 min-w-0">
        <ChatHeader
          threadId={threadId}
          sessions={sessions}
          showSessions={showSessions}
          sessionSearch={sessionSearch}
          onToggleSessions={stableToggleSessions}
          onCloseSessions={stableCloseSessions}
          onSessionSearchChange={setSessionSearch}
          onSwitch={onSwitch}
          onNewSession={onNewSession}
        />

      {/* 消息列表 */}
      <div className="relative flex-1 min-h-0">
        <div ref={listRef} onScroll={handleListScroll} className="h-full overflow-y-auto px-4 py-4 space-y-4 scroll-thin">
          {messages.length === 0 && (
          <div className="pt-12 sm:pt-16 text-center">
            <div className="flex justify-center mb-6">
              <div className="rounded-2xl bg-primary/5 p-3 shadow-soft">
                <BrandLogo size={48} />
              </div>
            </div>
            <h1 className="text-[26px] sm:text-3xl font-semibold tracking-tight leading-[1.2] text-balance">
              {hasData ? tr("chat.heroQuestion") : tr("chat.heroTitle", { name: BRAND.name })}
            </h1>
            <div className="mt-3.5 flex items-center justify-center gap-3 text-[11px] text-muted-foreground/70">
              <span className="h-px w-8 bg-gradient-to-r from-transparent to-primary/40" />
              <span className="tracking-[0.12em]">{tr("chat.heroMotto")}</span>
              <span className="h-px w-8 bg-gradient-to-l from-transparent to-primary/40" />
            </div>
            {!hasData && (
              <div className="mt-7 mx-auto flex max-w-md flex-wrap justify-center gap-2">
                {CAP_EXAMPLE_KEYS.map((c) => (
                  <button
                    key={c}
                    type="button"
                    disabled={stream.isPending}
                    onClick={() => void stableSend(tr(c))}
                    className="rounded-full border border-border/80 bg-card px-3.5 py-1.5 text-xs text-foreground/80 shadow-soft transition-all hover:border-primary/30 hover:text-primary hover:shadow-lift hover:-translate-y-px disabled:opacity-50"
                  >
                    {tr(c)}
                  </button>
                ))}
              </div>
            )}
            {suggestions.length > 0 && (
              <div className="mt-5 flex flex-col gap-2 max-w-sm mx-auto">
                {suggestions.map((sk) => (
                  <Button key={sk} variant="outline" onClick={() => stableSend(tr(sk))} disabled={stream.isPending}>
                    {tr(sk)}
                  </Button>
                ))}
              </div>
            )}
          </div>
        )}

        <FinishedMessages
          messages={finishedMessages}
          busy={stream.isPending}
          showSteps={showSteps}
          exportOn={exportOn}
          onNavigate={onNavigate}
          {...bubbleCallbacks}
        />

        {streamingMsg && (
          <ChatMessageBubble
            message={streamingMsg}
            busy={stream.isPending}
            streaming
            showSteps={showSteps}
            exportOn={exportOn}
            onNavigate={onNavigate}
            {...bubbleCallbacks}
          />
        )}
        </div>
        {/* 上滚浮标 */}
        {scrolledUp && (
          <button
            type="button"
            aria-label={tr("chat.scrollLatest")}
            onClick={scrollNow}
            className="absolute bottom-3 right-3 z-10 flex h-8 w-8 items-center justify-center rounded-full border border-border bg-card text-muted-foreground shadow-lift transition-colors hover:text-primary"
          >
            <ArrowDown className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* 输入区 */}
      <ChatInput
        input={input}
        onInputChange={setInput}
        busy={stream.isPending}
        listening={listening}
        voiceOn={voiceOn}
        llmConfigured={!!bootstrap?.health?.llm_configured}
        inputRef={inputRef}
        onToggleVoice={stableToggleVoice}
        onSend={stableSendInput}
        onStop={stableStop}
        onOpenSettings={onOpenSettings}
        attachments={attachments}
        onAddAttachment={(f) =>
          uploadAttachment(f)
            .then(() => void store.bump())
        }
        onRemoveAttachment={(id) => {
          removeAttachment(id);
        }}
        onSlashCommand={(id) => {
          if (id === "new-session") {
            onNewSession();
          } else {
            onNavigate(id.replace(/^go-/, ""));
          }
        }}
        modelName={bootstrap?.health?.model}
        modelCatalog={bootstrap?.model_catalog}
        enabledModels={bootstrap?.enabled_models}
        onSwitchModel={async (base, model) => {
          try {
            await api("/api/settings", {
              method: "PUT",
              body: JSON.stringify({ settings: { ai_base_url: base, ai_model: model } }),
            });
            await refreshBootstrap();
          } catch {
            /* 切换失败保持现状即可 */
          }
        }}
      />
      </div>

      {/* 桌面端右侧：Agent 运行面板（计划 / 工具调用 / 状态） */}
      <AgentPanel message={panelMsg} />
    </div>
  );
}

// Type imports used by chat-view-state hook
export type { AgentToolStep, ChatMessage, StepInfo, AgentPlanStep };
