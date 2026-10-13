import { useEffect, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import { Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { EmptyState } from "@/components/ui/empty-state";
import { useToast } from "@/lib/toast";
import { useI18n } from "@/lib/i18n";
import { isLevelAlert, levelLabel } from "@/lib/level";

/** 今日晨报弹层：手动触发一次晨报（AI 生成 + 数据附注；无 AI 时规则降级），
 *  空库不生成（后端 skipped），markdown 渲染展示。 */
export function MorningReportDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useI18n();
  const { toast } = useToast();
  const [state, setState] = useState<{ loading: boolean; answer?: string; level?: string; skipped?: boolean }>({
    loading: false,
  });

  useEffect(() => {
    if (!open) return;
    let alive = true;
    setState({ loading: true });
    api<{ ok: boolean; answer?: string; level?: string; skipped?: boolean; reason?: string; error?: string }>("/api/reports/generate", { method: "POST", body: JSON.stringify({}) })
      .then((r) => {
        if (!alive) return;
        setState({ loading: false, answer: r.answer, level: r.level, skipped: r.skipped });
      })
      .catch((e) => {
        if (!alive) return;
        setState({ loading: false });
        toast(e instanceof Error ? e.message : String(e), "error");
      });
    return () => {
      alive = false;
    };
  }, [open, toast]);

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/45 backdrop-blur-sm data-[state=open]:animate-fade-in" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex max-h-[82vh] w-[min(94vw,40rem)] -translate-x-1/2 -translate-y-1/2 flex-col rounded-xl border border-border bg-card shadow-lift data-[state=open]:animate-fade-in">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <Dialog.Title className="text-sm font-semibold flex items-center gap-2">
              {t("report.title")}
              {state.level && (
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                    isLevelAlert(state.level)
                      ? "bg-amber-500/15 text-amber-600 dark:text-amber-400"
                      : "bg-primary/10 text-primary"
                  }`}
                >
                  {levelLabel(t, state.level)}
                </span>
              )}
            </Dialog.Title>
            <Dialog.Close asChild>
              <button
                type="button"
                className="rounded-md p-1 text-muted-foreground hover:text-foreground hover:bg-accent"
                aria-label={t("pos.close")}
              >
                ✕
              </button>
            </Dialog.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto scroll-thin p-4">
            {state.loading ? (
              <div className="flex h-40 items-center justify-center text-xs text-muted-foreground">
                <Loader2 className="w-4 h-4 animate-spin mr-2" /> {t("report.generating")}
              </div>
            ) : state.skipped ? (
              <EmptyState mode="compact" text={t("report.noData")} className="py-8" />
            ) : state.answer ? (
              <article className="prose-sm prose-headings:font-semibold prose-p:my-1.5 prose-ul:my-1.5 prose-li:my-0.5 prose-strong:text-foreground max-w-none text-sm leading-relaxed text-muted-foreground [&_h1]:text-base [&_h2]:text-sm [&_h3]:text-sm">
                <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>{state.answer}</ReactMarkdown>
                <p className="mt-3 border-t border-border/60 pt-2 text-[11px] text-muted-foreground/70">{t("notAdvice")}</p>
              </article>
            ) : (
              <EmptyState mode="compact" text={t("report.failed", { e: "" })} className="py-8" />
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
