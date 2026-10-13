/** 首页评估卡：渲染 /api/evaluate 返回的行动项，按 kind 分组 + 彩色侧栏。
 *  纯确定性输出（不依赖 LLM），代价低可每次首页加载时拉取。 */

import { AlertTriangle, Bell, CheckCircle2, ChevronRight, Info, ListTodo, Target } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useI18n } from "@/lib/i18n";
import { useEvaluate, type EvalItem } from "@/lib/use-evaluate";

const KIND_META: Record<
  EvalItem["kind"],
  { icon: typeof Bell; label: string; bar: string; badge: string }
> = {
  todo: { icon: ListTodo, label: "eval.kind.todo", bar: "border-l-rose-500", badge: "bg-rose-500/15 text-rose-600 dark:text-rose-400" },
  warn: { icon: AlertTriangle, label: "eval.kind.warn", bar: "border-l-amber-500", badge: "bg-amber-500/15 text-amber-600 dark:text-amber-400" },
  info: { icon: Info, label: "eval.kind.info", bar: "border-l-sky-500", badge: "bg-sky-500/15 text-sky-600 dark:text-sky-400" },
  goal: { icon: Target, label: "eval.kind.goal", bar: "border-l-violet-500", badge: "bg-violet-500/15 text-violet-600 dark:text-violet-400" },
};

function EvalRow({ item }: { item: EvalItem }) {
  const { t: tr } = useI18n();
  const meta = KIND_META[item.kind];
  const Icon = meta.icon;
  const titleKey = `eval.${item.code}.title`;
  const detailKey = `eval.${item.code}.detail`;
  const title = tr(titleKey, item.vars as Record<string, string | number>) === titleKey
    ? (item.title || item.code)
    : tr(titleKey, item.vars as Record<string, string | number>);
  const detail = item.detail
    ? item.detail
    : tr(detailKey, item.vars as Record<string, string | number>) === detailKey
      ? ""
      : tr(detailKey, item.vars as Record<string, string | number>);

  return (
    <div className={`border-l-[3px] ${meta.bar} pl-3 py-1.5`}>
      <div className="flex items-start gap-2">
        <Icon className="w-4 h-4 mt-0.5 text-muted-foreground shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium text-balance">{title}</div>
          {detail && <div className="mt-0.5 text-xs text-muted-foreground text-balance">{detail}</div>}
        </div>
        {item.action?.path && (
          <a
            href={item.action.path}
            className="shrink-0 text-xs text-primary hover:underline flex items-center gap-0.5"
          >
            {item.action.label ?? "→"} <ChevronRight className="w-3 h-3" />
          </a>
        )}
      </div>
    </div>
  );
}

export function SmartEvalCard() {
  const { t: tr } = useI18n();
  const { data, isLoading, isError } = useEvaluate();

  if (isLoading) {
    return (
      <Card className="p-[var(--card-pad)]">
        <div className="flex items-center gap-2 mb-3">
          <Skeleton className="w-4 h-4 rounded" />
          <Skeleton className="w-32 h-4 rounded" />
        </div>
        <div className="space-y-2">
          <Skeleton className="h-5 w-full rounded" />
          <Skeleton className="h-5 w-3/4 rounded" />
        </div>
      </Card>
    );
  }

  if (isError || !data) {
    return (
      <Card className="p-[var(--card-pad)]">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Info className="w-4 h-4" />
          {tr("eval.loadFail")}
        </div>
      </Card>
    );
  }

  const { items, summary, refreshed_at } = data;
  const sumTodo = summary.todo + summary.warn;

  if (items.length === 0) {
    return (
      <Card className="p-[var(--card-pad)]">
        <div className="flex items-center gap-2 text-sm">
          <CheckCircle2 className="w-4 h-4 text-success" />
          <span className="font-medium">{tr("eval.allClear")}</span>
          <span className="text-xs text-muted-foreground">
            · {tr("eval.refreshed", { at: refreshed_at })}
          </span>
        </div>
      </Card>
    );
  }

  return (
    <Card className="p-[var(--card-pad)]">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Bell className="w-4 h-4 text-primary" />
          <span className="text-sm font-medium">{tr("eval.title")}</span>
          {sumTodo > 0 && (
            <Badge variant="warn" className="text-[10px]">
              {tr("eval.actionNeeded", { n: sumTodo })}
            </Badge>
          )}
        </div>
        <span className="text-[11px] text-muted-foreground">
          {tr("eval.refreshed", { at: refreshed_at })}
        </span>
      </div>
      <div className="space-y-1">
        {items.map((it, i) => (
          <EvalRow key={`${it.code}-${i}`} item={it} />
        ))}
      </div>
    </Card>
  );
}
