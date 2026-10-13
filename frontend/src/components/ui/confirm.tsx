import * as Dialog from "@radix-ui/react-dialog";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";

/** 应用内确认框，替代原生 window.confirm（样式统一、可键盘操作）。 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmText,
  cancelText,
  danger = false,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
  onConfirm: () => void | Promise<void>;
}) {
  const { t } = useI18n();
  const cf = confirmText || t("confirm.confirm");
  const cc = cancelText || t("confirm.cancel");
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/45 backdrop-blur-sm data-[state=open]:animate-fade-in" />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 z-50 w-[min(92vw,24rem)] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-card p-5 shadow-lift data-[state=open]:animate-fade-in"
          aria-describedby={description ? "confirm-desc" : undefined}
        >
          <Dialog.Title className="text-sm font-semibold">{title}</Dialog.Title>
          {description && (
            <Dialog.Description id="confirm-desc" className="mt-1.5 text-xs text-muted-foreground">
              {description}
            </Dialog.Description>
          )}
          <div className="mt-4 flex justify-end gap-2">
            <Dialog.Close asChild>
              <Button variant="outline" size="sm">
                {cc}
              </Button>
            </Dialog.Close>
            <Button
              size="sm"
              variant={danger ? "destructive" : "default"}
              onClick={() => {
                onOpenChange(false);
                void onConfirm();
              }}
            >
              {cf}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
