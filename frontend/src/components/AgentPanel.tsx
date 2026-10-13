import { useEffect, useState } from "react";
import { Loader2, PanelRightClose, PanelRightOpen, Sparkles, Wrench } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import type { ChatMessage } from "@/components/ChatMessageBubble";
import type { AgentToolStep } from "@/lib/types";
import { cn } from "@/lib/utils";

/** 工具名 → 用户可读的动作（与 ChatMessageBubble 一致） */
const TOOL_LABEL_KEYS: Record<string, string> = {
  get_market_view: "chat.toolMarket",
  get_ledger_view: "chat.toolLedger",
  get_risk_flags: "chat.toolRisk",
  get_budget: "chat.toolBudget",
  get_trend: "chat.toolTrend",
  record_transaction: "chat.toolRecord",
  get_kline: "chat.toolKline",
  search_symbol: "chat.toolSearch",
  get_quote: "chat.toolQuote",
  add_to_watchlist: "chat.toolWatch",
};

function toolLabel(tr: (k: string) => string, name: string): string {
  const k = TOOL_LABEL_KEYS[name];
  return k ? tr(k) : name;
}

function ToolRow({ tool }: { tool: AgentToolStep }) {
  const { t: tr } = useI18n();
  const running = tool.status === "running";
  const err = tool.status === "error";
  const pending = tool.status === "pending";
  return (
    <div className="flex items-start gap-2 text-xs">
      {running ? (
        <Loader2 className="w-3.5 h-3.5 shrink-0 text-primary animate-spin mt-0.5" />
      ) : err ? (
        <span className="shrink-0 text-red-500 mt-0.5">✗</span>
      ) : pending ? (
        <span className="shrink-0 text-muted-foreground mt-0.5">○</span>
      ) : (
        <span className="shrink-0 text-primary mt-0.5">✓</span>
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <b className="text-foreground truncate">{toolLabel(tr, tool.name)}</b>
          {tool.duration_ms != null && (
            <span className="text-[10px] text-muted-foreground">{tool.duration_ms}ms</span>
          )}
        </div>
        {tool.summary ? (
          <div className="mt-0.5 text-[11px] text-muted-foreground line-clamp-2">{tool.summary}</div>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Agent 运行面板（桌面端右侧栏）：实时展示当前这一轮 Agent 的
 * 执行计划（plan）、工具调用链（tools）、状态（running/done）。可折叠。
 */
export function AgentPanel({
  message,
  compact = false,
}: {
  /** 正在流式/最近一条 assistant 消息（未开始流式时为 null） */
  message: ChatMessage | null;
  /** compact：面板内嵌在对话区顶部（移动端）时不用高度撑满 */
  compact?: boolean;
}) {
  const { t: tr } = useI18n();
  const [open, setOpen] = useState(false);

  const plan = message?.plan;
  const tools = message?.tools ?? [];
  const running = message?.agentStatus === "running" || tools.some((t) => t.status === "running");

  // Agent 有过程数据（工具调用/计划）时自动展开面板；跑完仍保持展开（用户可自行收起）
  const hasActivity = (plan && plan.steps.length > 0) || tools.length > 0;
  useEffect(() => {
    if (hasActivity) setOpen(true);
  }, [hasActivity]);

  if (!plan && tools.length === 0) {
    // 空态：完全不渲染，不占任何右边空间。
    // 只有当 agent 真正在跑（有 plan / tools）时才出现右侧面板。
    return null;
  }

  return (
    <div
      className={cn(
        "hidden lg:flex w-64 shrink-0 flex-col border-l border-border bg-card/30",
        compact && "lg:hidden",
      )}
    >
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-border/60">
        <span className="text-[11px] font-medium text-foreground/70 inline-flex items-center gap-1.5">
          <Sparkles className="w-3.5 h-3.5 text-primary" />
          {tr("agent.panelTitle")}
          {running && <Loader2 className="w-3 h-3 animate-spin text-primary" />}
        </span>
        <button
          type="button"
          aria-label={tr("agent.panelToggle")}
          className="p-1 text-muted-foreground hover:text-foreground"
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <PanelRightClose className="w-4 h-4" /> : <PanelRightOpen className="w-4 h-4" />}
        </button>
      </div>

      {open && (
        <div className="flex-1 min-h-0 overflow-y-auto scroll-thin p-3 space-y-4">
          {/* 执行计划 */}
          {plan && plan.steps.length > 0 && (
            <section>
              <h3 className="mb-1.5 text-[11px] text-muted-foreground font-medium">
                {tr("agent.planTitle")}
              </h3>
              <ol className="space-y-1">
                {plan.steps.map((s, i) => (
                  <li key={s.id} className="flex items-start gap-1.5 text-xs text-foreground">
                    <span className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-primary/15 text-[10px] text-primary shrink-0">
                      {i + 1}
                    </span>
                    <span className="min-w-0">
                      <b>{s.label}</b>
                      {s.detail ? <div className="text-[11px] text-muted-foreground">{s.detail}</div> : null}
                    </span>
                  </li>
                ))}
              </ol>
            </section>
          )}

          {/* 工具调用链 */}
          {tools.length > 0 && (
            <section>
              <h3 className="mb-1.5 text-[11px] text-muted-foreground font-medium inline-flex items-center gap-1">
                <Wrench className="w-3 h-3" />
                {tr("agent.toolsTitle")} · {tools.length}
              </h3>
              <div className="space-y-2">
                {tools.map((t, i) => (
                  <ToolRow key={i} tool={t} />
                ))}
              </div>
            </section>
          )}

          {/* 运行状态 */}
          <section className="mt-auto pt-2">
            <div className="flex items-center gap-2 rounded-md border border-border/70 bg-background/40 px-2 py-1.5 text-[11px] text-muted-foreground">
              <span className={cn("h-2 w-2 rounded-full", running ? "bg-primary animate-pulse" : "bg-emerald-500")} />
              {running ? tr("agent.running") : tr("agent.done")}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}