import { useCallback, useEffect, useState } from "react";
import { BrainCog, Check, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm";
import { FieldError } from "@/components/ui/field-error";
import { addMemory, clearMemory, deleteMemory, listMemory, forgetMemory, listReflections, resolveReflection, clearReflections, type ReflectionItem } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { useI18n } from "@/lib/i18n";
import { fmtDate } from "@/lib/format";
import type { MemoryItem } from "@/lib/types";
import { Section, inputCls, labelCls } from "./shared";

/** 长期记忆 + 主动遗忘 + 经验库（P1 反思/踩坑复盘） */
export function MemorySection() {
  const { t } = useI18n();
  const [items, setItems] = useState<MemoryItem[] | null>(null);
  const [text, setText] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [clearOpen, setClearOpen] = useState(false);
  const [forgetOpen, setForgetOpen] = useState(false);
  const [reflections, setReflections] = useState<ReflectionItem[] | null>(null);
  const { toast } = useToast();

  const reload = useCallback(async () => {
    try {
      setItems(await listMemory());
    } catch {
      setItems([]);
    }
    try {
      setReflections(await listReflections());
    } catch {
      setReflections([]);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const submit = async () => {
    setErr("");
    if (!text.trim()) return;
    setBusy(true);
    try {
      const r = await addMemory(text.trim());
      setText("");
      toast(r.deduped ? t("settings.memDup") : t("settings.memSaved"), "ok");
      void reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const doForget = async () => {
    try {
      const r = await forgetMemory(180);
      toast(r.deleted ? t("settings.memForgot", { n: r.deleted }) : t("settings.memForgetNone"), "ok");
      setForgetOpen(false);
      void reload();
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    }
  };

  return (
    <Section title={t("settings.navMemory")} icon={<BrainCog className="w-4 h-4 text-muted-foreground" />} desc={t("settings.memDesc")}>
      <div className="flex items-end gap-2">
        <div className="flex-1">
          <label className={labelCls}>{t("settings.memNew")}</label>
          <input
            className={inputCls}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void submit();
            }}
            placeholder={t("settings.memPh")}
            maxLength={500}
          />
        </div>
        <Button size="sm" onClick={() => void submit()} disabled={busy || !text.trim()}>
          <Plus className="w-3.5 h-3.5" /> {t("settings.memSave")}
        </Button>
      </div>
      {err ? <FieldError className="mt-1">{err}</FieldError> : null}

      <div className="mt-3 flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          {items == null ? t("settings.loading") : items.length === 0 ? t("settings.memEmpty") : t("settings.memCount", { n: items.length })}
        </span>
        <span className="flex items-center gap-2">
          {items && items.length > 0 && (
            <Button variant="outline" size="sm" className="h-6 px-2 text-xs" onClick={() => setForgetOpen(true)} title={t("settings.memForgetHint")}>
              {t("settings.memForget")}
            </Button>
          )}
          {items && items.length > 0 && (
            <Button variant="outline" size="sm" className="h-6 px-2 text-xs" onClick={() => setClearOpen(true)}>
              {t("settings.memClear")}
            </Button>
          )}
        </span>
      </div>

      {items && items.length > 0 && (
        <ul className="mt-2 space-y-1.5">
          {items.map((m) => (
            <li key={m.id} className="flex items-start justify-between gap-2 rounded-lg border border-border px-2.5 py-1.5 text-sm">
              <span className="min-w-0 flex-1">
                <span className="block break-words">{m.content}</span>
                <span className="mt-0.5 block text-[11px] text-muted-foreground">
                  {m.kind !== "fact" ? `${m.kind} · ` : ""}{t("settings.memUpdated")} {fmtDate(m.updated_at)}
                </span>
              </span>
              <button
                className="shrink-0 text-muted-foreground hover:text-red-600"
                onClick={() => {
                void deleteMemory(m.id)
                  .then(reload)
                  .catch((e) => toast(e instanceof Error ? e.message : String(e), "error"));
              }}
                aria-label={t("settings.memDelete", { c: m.content })}
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* 主动遗忘：清理 180 天未使用的记忆 */}
      <ConfirmDialog
        open={forgetOpen}
        title={t("settings.memForgetTitle")}
        description={t("settings.memForgetDesc")}
        confirmText={t("settings.memForget")}
        danger
        onOpenChange={setForgetOpen}
        onConfirm={() => void doForget()}
      />

      <ConfirmDialog
        open={clearOpen}
        title={t("settings.memClearTitle")}
        description={t("settings.memClearDesc")}
        confirmText={t("settings.memClear")}
        danger
        onOpenChange={setClearOpen}
        onConfirm={() => {
          void clearMemory()
            .then(() => {
              setClearOpen(false);
              toast(t("settings.memCleared"), "ok");
              void reload();
            })
            .catch((e) => toast(e instanceof Error ? e.message : String(e), "error"));
        }}
      />

      {/* 经验库（P1 反思 / 踩坑复盘）：工具失败的记录，供模型反思避免重复犯错 */}
      <div className="mt-4 pt-3 border-t border-border/60">
        <div className="flex items-center justify-between">
          <div className="text-sm font-medium">{t("settings.reflectionsTitle")}</div>
          {reflections && reflections.length > 0 && (
            <Button variant="outline" size="sm" className="h-6 px-2 text-xs" onClick={() => {
              void clearReflections()
                .then(() => {
                  toast(t("settings.reflectionsCleared"), "ok");
                  void reload();
                })
                .catch((e) => toast(e instanceof Error ? e.message : String(e), "error"));
            }}>
              {t("settings.reflectionsClear")}
            </Button>
          )}
        </div>
        <p className="mt-0.5 text-[11px] text-muted-foreground/70">{t("settings.reflectionsDesc")}</p>
        {reflections == null ? (
          <div className="mt-2 text-xs text-muted-foreground">{t("settings.loading")}</div>
        ) : reflections.length === 0 ? (
          <div className="mt-2 text-xs text-muted-foreground/70">{t("settings.reflectionsEmpty")}</div>
        ) : (
          <ul className="mt-2 space-y-1.5">
            {reflections.map((r) => (
              <li key={r.id} className="flex items-start justify-between gap-2 rounded-lg border border-amber-400/30 bg-amber-50/40 px-2.5 py-1.5 text-sm">
                <span className="min-w-0 flex-1">
                  <span className="block break-words"><span className="font-mono text-[11px] text-amber-700">{r.tool}</span> · {r.lesson}</span>
                  <span className="mt-0.5 block text-[11px] text-muted-foreground">{fmtDate(r.created_at)}</span>
                </span>
                <button
                  className="shrink-0 text-muted-foreground hover:text-green-600"
                  onClick={() => {
                    void resolveReflection(r.id)
                      .then(reload)
                      .catch((e) => toast(e instanceof Error ? e.message : String(e), "error"));
                  }}
                  aria-label={t("settings.reflectionsResolve")}
                  title={t("settings.reflectionsResolve")}
                >
                  <Check className="w-3.5 h-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Section>
  );
}
