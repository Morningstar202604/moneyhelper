import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import { Inbox, Sunrise, Zap } from "lucide-react";
import { SidePanel } from "@/components/ui/side-panel";
import { EmptyState } from "@/components/ui/empty-state";
import { useI18n } from "@/lib/i18n";
import { fmtDate } from "@/lib/format";
import { levelLabel, isLevelAlert } from "@/lib/level";
import { useScheduledOutputs } from "@/lib/inbox";
import type { ScheduledOutput } from "@/lib/types";

/** 定时产出收件箱：晨报 + 技能触发的统一时间线（最新在前），
 *  打开即整体标读（侧栏徽标随之清零）。 */
export function ScheduledOutputsPanel({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const { outputs, refresh, markAllRead } = useScheduledOutputs();
  const [expanded, setExpanded] = useState<number | null>(null);

  useEffect(() => {
    if (!open) return;
    // 打开时拉最新并整体标读（先拿到列表再写游标，避免把未取到的新产出误标已读）
    void refresh().then((items) => markAllRead(items));
  }, [open, refresh, markAllRead]);

  return (
    <SidePanel
      open={open}
      onClose={onClose}
      title={t("inbox.title")}
      icon={<Inbox className="w-4 h-4 text-primary" />}
      headerExtra={
        outputs && outputs.length > 0 ? (
          <span className="shrink-0 text-[11px] text-muted-foreground">
            {t("inbox.count", { n: outputs.length })}
          </span>
        ) : undefined
      }
    >
      {outputs === null ? (
        <div className="py-10 text-center text-xs text-muted-foreground">{t("app.loading")}</div>
      ) : outputs.length === 0 ? (
        <EmptyState mode="compact" text={t("inbox.empty")} className="py-8" />
      ) : (
        <ul className="space-y-2.5">
          {outputs.map((o) => (
            <OutputCard
              key={o.id}
              item={o}
              expanded={expanded === o.id}
              onToggle={() => setExpanded(expanded === o.id ? null : o.id)}
            />
          ))}
        </ul>
      )}
    </SidePanel>
  );
}

function OutputCard({
  item,
  expanded,
  onToggle,
}: {
  item: ScheduledOutput;
  expanded: boolean;
  onToggle: () => void;
}) {
  const { t } = useI18n();
  const isReport = item.kind === "report";
  return (
    <li className="rounded-xl border border-border bg-card p-3">
      <div className="flex items-center gap-2">
        <span
          className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
            isReport
              ? "bg-amber-500/15 text-amber-600 dark:text-amber-400"
              : "bg-sky-500/15 text-sky-600 dark:text-sky-400"
          }`}
        >
          {isReport ? <Sunrise className="w-3 h-3" /> : <Zap className="w-3 h-3" />}
          {isReport ? t("inbox.kindReport") : item.skill_name || t("inbox.kindSkill")}
        </span>
        {item.level && (
          <span
            className={`shrink-0 rounded-full px-1.5 py-0.5 text-[11px] ${
              isLevelAlert(item.level)
                ? "bg-amber-500/15 text-amber-600 dark:text-amber-400"
                : "bg-primary/10 text-primary"
            }`}
          >
            {levelLabel(t, item.level)}
          </span>
        )}
        <span className="ml-auto shrink-0 text-[11px] text-muted-foreground">{fmtDate(item.created_at)}</span>
      </div>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="mt-1.5 w-full text-left"
      >
        <div className="text-xs text-muted-foreground">{item.question}</div>
        <div
          className={`prose-sm mt-1 max-w-none text-sm leading-relaxed text-foreground/90 ${
            expanded ? "" : "line-clamp-3"
          } [&_h1]:text-base [&_h2]:text-sm [&_h3]:text-sm [&_p]:my-1`}
        >
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>
            {item.answer}
          </ReactMarkdown>
        </div>
        <span className="mt-1 inline-block text-[11px] text-primary">
          {expanded ? t("inbox.collapse") : t("inbox.expand")}
        </span>
      </button>
    </li>
  );
}
