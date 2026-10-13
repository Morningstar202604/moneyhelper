import { useCallback, useEffect, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { Button } from "@/components/ui/button";
import { setAuthPromptHandler } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/** 访问口令输入对话框：替代浏览器原生 window.prompt（样式统一、可键盘操作）。
 * App 挂载时注册为 api 层的 401 回调：输入后自动重试，取消则放弃。 */
export function PasswordDialog() {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const resolveRef = useRef<((v: string | null) => void) | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const submit = useCallback(() => {
    const resolve = resolveRef.current;
    resolveRef.current = null;
    setOpen(false);
    resolve?.(value.trim());
  }, [value]);

  const cancel = useCallback(() => {
    const resolve = resolveRef.current;
    resolveRef.current = null;
    setOpen(false);
    resolve?.(null);
  }, []);

  useEffect(() => {
    setAuthPromptHandler(
      () =>
        new Promise<string | null>((resolve) => {
          resolveRef.current = resolve;
          setValue("");
          setOpen(true);
        }),
    );
    return () => setAuthPromptHandler(null);
  }, []);

  // 打开后自动聚焦 + Enter 提交
  useEffect(() => {
    if (open) {
      const timer = window.setTimeout(() => inputRef.current?.focus(), 50);
      return () => window.clearTimeout(timer);
    }
  }, [open]);

  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && cancel()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/45 backdrop-blur-sm data-[state=open]:animate-fade-in" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(92vw,24rem)] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-card p-5 shadow-lift data-[state=open]:animate-fade-in">
          <Dialog.Title className="text-sm font-semibold">{t("auth.title")}</Dialog.Title>
          <Dialog.Description className="mt-1.5 text-xs text-muted-foreground">
            {t("auth.desc")}
          </Dialog.Description>
          <input
            ref={inputRef}
            type="password"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder={t("auth.placeholder")}
            autoComplete="off"
            className="mt-3 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
          />
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={cancel}>
              {t("auth.cancel")}
            </Button>
            <Button size="sm" onClick={submit} disabled={!value.trim()}>
              {t("auth.ok")}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
