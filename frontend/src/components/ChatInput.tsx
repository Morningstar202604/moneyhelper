import { memo, useEffect, useRef, useState, type RefObject } from "react";
import { BarChart3, CreditCard, LayoutDashboard, Mic, MicOff, Paperclip, Plus, Send, Settings, Sparkles, Square, Wallet, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { useToast } from "@/lib/toast";
import type { BootstrapData } from "@/lib/types";

export interface ChatInputProps {
  input: string;
  onInputChange: (v: string) => void;
  busy: boolean;
  listening: boolean;
  voiceOn: boolean;
  llmConfigured: boolean;
  inputRef: RefObject<HTMLTextAreaElement | null>;
  onToggleVoice: () => void;
  onSend: () => void;
  onStop: () => void;
  onOpenSettings: () => void;
  onSlashCommand: (id: string) => void;
  /** 当前生效的模型名（composer 显示，对标 ChatGPT） */
  modelName?: string;
  /** 模型目录 + 已点亮清单（P0 模型点亮）：输入区只显示已点亮的模型 */
  modelCatalog?: BootstrapData["model_catalog"];
  enabledModels?: string[];
  /** 快捷切换模型：写入设置 ai_base_url + ai_model */
  onSwitchModel?: (base: string, model: string) => void;
  /** @提及附件：已选附件列表 + 上传/移除 */
  attachments?: { id: number; filename: string; kind: string }[];
  onAddAttachment?: (file: File) => Promise<unknown>;
  onRemoveAttachment?: (id: number) => void;
}

/** Slash（/）快捷指令：输入 / 呼出通用命令面板（对标 Notion/ChatGPT 命令菜单）。
 *  只列「去 / 新建」这类通用导航与操作，不放具体个股示例，避免打扰、保持通用。 */
const SLASH_ITEMS = [
  { id: "go-overview", key: "cmd.goOverview", icon: LayoutDashboard },
  { id: "go-holdings", key: "cmd.goHoldings", icon: Wallet },
  { id: "go-market", key: "cmd.goMarket", icon: BarChart3 },
  { id: "go-ledger", key: "cmd.goLedger", icon: CreditCard },
  { id: "go-settings", key: "cmd.goSettings", icon: Settings },
  { id: "new-session", key: "cmd.newSession", icon: Plus },
] as const;

/** 输入区：LLM 未配置提示 + 快捷 chips + Slash 指令 + 语音/输入/停止 */
export const ChatInput = memo(({
  input,
  onInputChange,
  busy,
  listening,
  voiceOn,
  inputRef,
  onToggleVoice,
  onSend,
  onStop,
  onSlashCommand,
  modelName,
  modelCatalog,
  enabledModels,
  onSwitchModel,
  attachments,
  onAddAttachment,
  onRemoveAttachment,
}: ChatInputProps) => {
  const { t: tr } = useI18n();
  const { toast } = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  // Slash 指令面板：仅当输入以 "/" 开头时激活，平时不占版面
  const slashQ = input.startsWith("/") ? input.trim().slice(1).toLowerCase() : "";
  const slashItems = SLASH_ITEMS.filter((it) => tr(it.key).toLowerCase().includes(slashQ));
  const slashOpen = input.startsWith("/") && slashItems.length > 0;
  const [activeIdx, setActiveIdx] = useState(0);
  useEffect(() => setActiveIdx(0), [slashQ]);

  const pick = (it: (typeof SLASH_ITEMS)[number]) => {
    // 通用命令：直接执行动作（去页面 / 新建会话），不填进输入框
    onInputChange("");
    onSlashCommand(it.id);
    inputRef.current?.focus();
  };

  // 输入框自动增高：多行按内容撑开，上限 4rem*?（144px）超出滚动（对标 ChatGPT/Claude 的自增高输入区）
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 144)}px`;
  }, [input, inputRef]);

  return (
    <div className="border-t border-border bg-card/80 backdrop-blur px-3 py-3">
      {/* 输入框上方不再常驻快捷指令：版面留给对话主界面；输入 "/" 才呼出 Slash 指令面板 */}
      {slashOpen && (
        <div className="mb-2 overflow-hidden rounded-lg border border-border bg-popover shadow-lg">
          {slashItems.map((it, i) => {
            const Icon = it.icon;
            return (
              <button
                key={it.id}
                type="button"
                onMouseEnter={() => setActiveIdx(i)}
                onClick={() => pick(it)}
                className={cn(
                  "flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors",
                  i === activeIdx ? "bg-accent text-foreground" : "text-muted-foreground",
                )}
              >
                <Icon className="w-4 h-4 shrink-0" />
                <span className="min-w-0 flex-1 truncate">{tr(it.key)}</span>
                <kbd className="rounded border border-border bg-background px-1.5 py-0.5 text-[10px] text-muted-foreground">
                  ↵
                </kbd>
              </button>
            );
          })}
        </div>
      )}
      {/* @提及附件：已选附件展示 + 上传按钮 */}
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        {(attachments ?? []).map((a) => (
          <span key={a.id} className="inline-flex items-center gap-1 rounded-md border border-primary/30 bg-primary/5 px-2 py-0.5 text-[11px] text-foreground/90">
            <Paperclip className="w-3 h-3 text-primary/60" />
            <span className="max-w-[10rem] truncate">{a.filename}</span>
            <button type="button" onClick={() => onRemoveAttachment?.(a.id)} aria-label={tr("chat.removeAttachment")} className="text-muted-foreground hover:text-red-500">
              <X className="w-3 h-3" />
            </button>
          </span>
        ))}
        <label className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground">
          <Paperclip className="w-3 h-3" />
          <span>{uploading ? "…" : tr("chat.attach")}</span>
          <input
            type="file"
            ref={fileRef}
            className="hidden"
            accept=".txt,.md,.json,.csv,.log"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) {
                setUploading(true);
                onAddAttachment?.(f)
                  .catch((err) => toast(err instanceof Error ? err.message : String(err), "error"))
                  .finally(() => setUploading(false));
              }
              e.target.value = "";
            }}
          />
        </label>
      </div>
      <div className="flex items-end gap-2">
        {voiceOn && (
          <Button
            variant={listening ? "default" : "ghost"}
            size="icon"
            aria-label={tr("chat.voiceInput")}
            onClick={onToggleVoice}
            className={listening ? "animate-pulse-ring" : ""}
          >
            {listening ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
          </Button>
        )}
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={(e) => {
            // Slash 面板激活时优先响应方向键/回车/退格
            if (slashOpen) {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActiveIdx((i) => (i + 1) % slashItems.length);
                return;
              }
              if (e.key === "ArrowUp") {
                e.preventDefault();
                setActiveIdx((i) => (i - 1 + slashItems.length) % slashItems.length);
                return;
              }
              if (e.key === "Enter") {
                e.preventDefault();
                pick(slashItems[activeIdx]);
                return;
              }
              if (e.key === "Escape") {
                e.preventDefault();
                // 撤销 slash 面板：只去掉开头的 "/"，保留已输入内容，不整句清空
                const slashIdx = input.indexOf("/");
                onInputChange(slashIdx >= 0 ? input.slice(0, slashIdx) + input.slice(slashIdx + 1) : input);
                return;
              }
            }
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSend();
            }
          }}
          rows={1}
          placeholder={tr("chat.inputPh")}
          className="flex-1 resize-none rounded-xl border border-input bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring min-h-[44px] max-h-36 overflow-y-auto scroll-thin"
        />
        {busy ? (
          <Button
            size="icon"
            variant="outline"
            onClick={onStop}
            aria-label={tr("chat.stop")}
            className="shrink-0 text-danger border-danger/40 hover:bg-danger/10 active:scale-95 transition-transform"
          >
            <Square className="w-4 h-4" />
          </Button>
        ) : (
          <Button
            size="icon"
            onClick={onSend}
            disabled={!input.trim()}
            aria-label={tr("chat.send")}
            className="shrink-0 active:scale-95 transition-transform"
          >
            <Send className="w-4 h-4" />
          </Button>
        )}
      </div>
      {/* 输入区底部能力提示：快捷键说明 + 当前模型（对标 ChatGPT 的微提示） */}
      <div className="mt-1.5 flex items-center justify-between px-0.5">
        <span className="text-[11px] text-muted-foreground/80">{tr("chat.enterHint")}</span>
        <span className="flex items-center gap-3 text-[11px] text-muted-foreground/50">
          <span>{tr("chat.slashHint")}</span>
          {modelName && (
            <label className="inline-flex items-center gap-1 text-muted-foreground/70">
              <Sparkles className="w-3 h-3 text-primary/60" />
              <select
                value={modelName}
                onChange={(e) => {
                  const val = e.target.value;
                  const hit = (modelCatalog ?? []).find((m) => m.model === val);
                  onSwitchModel?.(hit ? hit.base : "", val);
                }}
                aria-label={tr("chat.switchModel")}
                title={tr("chat.switchModelHint")}
                className="appearance-none cursor-pointer bg-transparent text-[11px] text-muted-foreground/70 focus:outline-none"
              >
                <option value={modelName}>{modelName}</option>
                {(enabledModels ?? [])
                  .filter((m) => m !== modelName)
                  .map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
              </select>
            </label>
          )}
        </span>
      </div>
    </div>
  );
});

ChatInput.displayName = "ChatInput";