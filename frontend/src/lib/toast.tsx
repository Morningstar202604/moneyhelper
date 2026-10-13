/** Toast 通知：基于 sonner（~8KB），保持既有 useToast API 不变。
 *  sonner 自带 ARIA live region、自动消失、堆叠与点击关闭；
 *  调用侧仍走 `const { toast } = useToast()`，14 个组件无需改动。 */

import { Toaster as SonnerToaster, toast as sonnerToast, type ExternalToast } from "sonner";
import { useMemo } from "react";

export type ToastKind = "ok" | "error" | "info";

function emit(text: string, kind: ToastKind = "info"): void {
  const opts: ExternalToast = { duration: 3200 };
  if (kind === "ok") sonnerToast.success(text, opts);
  else if (kind === "error") sonnerToast.error(text, opts);
  else sonnerToast.info(text, opts);
}

export function useToast() {
  const value = useMemo(
    () => ({
      toast: (text: string, kind?: ToastKind) => emit(text, kind),
    }),
    [],
  );
  return value;
}

/** 挂载在 App 根部一次；位置/样式沿用右下角堆叠视觉。 */
export function Toaster() {
  return <SonnerToaster position="bottom-right" richColors closeButton />;
}
