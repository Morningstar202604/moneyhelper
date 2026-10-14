import { useEffect, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { useI18n } from "@/lib/i18n";

/**
 * 统一的右侧工具面板壳（ChatGPT 式辅助工具区）。
 * - 桌面：从右滑出，**不遮挡对话**（聊天保持可交互；宽屏下调用方自行让位）
 * - 移动端：全屏展开 + 半透明遮罩，点击遮罩或 Esc 关闭
 * - 头部：图标 + 标题 +（可选 headerExtra：tabs/操作）+ 统一关闭按钮
 * 所有"预览/数据/报告"类工具都应复用本壳，保证交互一致。
 */
export function SidePanel({
  open,
  onClose,
  title,
  icon,
  headerExtra,
  children,
  z = "z-40",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  icon?: ReactNode;
  headerExtra?: ReactNode;
  children: ReactNode;
  z?: string;
}) {
  const { t } = useI18n();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div className={`fixed inset-0 ${z} md:pointer-events-none`}>
          {/* 移动端遮罩（桌面不遮挡：对话保持可交互） */}
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm md:hidden" onClick={onClose} />
          <motion.aside
            role="complementary"
            aria-label={title}
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 420, damping: 42 }}
            className="pointer-events-auto absolute right-0 top-0 flex h-full w-full flex-col border-l border-border bg-card shadow-lift md:w-[400px] lg:w-[440px]"
          >
            <div className="flex items-center justify-between gap-2 border-b border-border px-3.5 py-2.5">
              <h2 className="flex min-w-0 shrink-0 items-center gap-1.5 text-sm font-semibold">
                {icon}
                <span className="truncate">{title}</span>
              </h2>
              {headerExtra}
              <button
                type="button"
                onClick={onClose}
                aria-label={t("app.close")}
                className="shrink-0 rounded-md p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            {/* @container：内容区按自身宽度响应（而非视口）——面板内表格等可自适应为窄布局 */}
            <div className="@container min-h-0 flex-1 overflow-y-auto scroll-thin p-4">{children}</div>
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
