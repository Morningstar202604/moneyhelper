import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useI18n } from "@/lib/i18n";

/**
 * 移动端抽屉（从左侧滑出）。
 *
 * 为什么需要它：桌面端的会话列表在 `<md` 时完全隐藏（`hidden md:flex`），
 * 而移动端此前没有任何替代入口——用户看不到历史会话，也无法新建。
 * 抽屉复用 SessionSidebar，保证两端行为一致。
 *
 * 交互细节（移动端体验的关键）：
 * - 打开时锁 body 滚动：否则背景页面会跟着手指滑动
 * - 点击遮罩关闭；Esc 关闭（外接键盘场景）
 * - 抽屉宽度 `min(85vw, 320px)`：留一条窄边露出背景，暗示"这是覆盖层"
 * - 顶部/底部补 safe-area，避免刘海与手势条遮挡
 */
export function MobileDrawer({
  open,
  onClose,
  children,
}: {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const { t } = useI18n();

  // 锁背景滚动：抽屉打开时不该让下层内容跟着滚
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

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
        <motion.div className="fixed inset-0 z-50 md:hidden">
          <motion.div
            className="absolute inset-0 bg-black/40 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            aria-hidden
          />
          <motion.aside
            role="dialog"
            aria-modal="true"
            aria-label={t("sidebar.sessions")}
            initial={{ x: "-100%" }}
            animate={{ x: 0 }}
            exit={{ x: "-100%" }}
            transition={{ type: "spring", stiffness: 420, damping: 42 }}
            className="absolute left-0 top-0 flex h-full flex-col border-r border-border bg-card shadow-lift"
            style={{
              width: "min(85vw, 320px)",
              paddingTop: "env(safe-area-inset-top)",
              paddingBottom: "env(safe-area-inset-bottom)",
            }}
          >
            {children}
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
