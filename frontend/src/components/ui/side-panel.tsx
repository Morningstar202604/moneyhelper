import { useEffect, useRef, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { useIsDesktop } from "@/lib/use-media-query";
import { useResizableWidth } from "@/lib/use-resizable-width";

/**
 * 统一的右侧工具面板壳。
 *
 * 三档响应式行为：
 * - 手机（<768）：全屏覆盖 + 遮罩，带焦点陷阱与焦点归还
 * - 平板（768–1279）：固定宽度侧栏，覆盖在内容之上（不挤压对话）
 * - 桌面（>=1280）：可拖拽宽度的侧栏，并把主内容按宽度让位（pushContent）
 *
 * 宽度通过 CSS 变量 `--xm-panel-w` 暴露给主布局，避免父组件再复制一份状态。
 */
export function SidePanel({
  open,
  onClose,
  title,
  icon,
  headerExtra,
  children,
  z = "z-40",
  widthKey = "wo.panelWidth",
  defaultWidth = 440,
  pushContent = false,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  icon?: ReactNode;
  headerExtra?: ReactNode;
  children: ReactNode;
  z?: string;
  /** 宽度持久化 key（同一个 key 的面板共享宽度偏好） */
  widthKey?: string;
  defaultWidth?: number;
  /** 桌面宽屏下是否让主内容让位（仅数据面板需要，浮层类面板保持覆盖） */
  pushContent?: boolean;
}) {
  const { t } = useI18n();
  const isDesktop = useIsDesktop();
  const panelRef = useRef<HTMLDivElement | null>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const { width, dragging, handleProps } = useResizableWidth({
    storageKey: widthKey,
    defaultWidth,
    min: 320,
    max: 640,
  });

  // 让主内容按面板宽度让位：写 CSS 变量，App 用 mr-[var(--xm-panel-w)] 读取
  useEffect(() => {
    if (!pushContent) return;
    const root = document.documentElement;
    if (open) {
      root.style.setProperty("--xm-panel-w", `${width}px`);
    } else {
      root.style.removeProperty("--xm-panel-w");
    }
    return () => {
      root.style.removeProperty("--xm-panel-w");
    };
  }, [open, width, pushContent]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // 焦点管理：打开时记住来源元素并把焦点移入面板，关闭时归还。
  // 不做这一步，键盘用户关闭面板后焦点会掉回 <body>，需要重新 Tab 一遍。
  useEffect(() => {
    if (!open) return;
    restoreFocusRef.current = document.activeElement as HTMLElement | null;
    const node = panelRef.current;
    if (!node) return;
    const first = node.querySelector<HTMLElement>(
      "button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])",
    );
    first?.focus();
    return () => {
      restoreFocusRef.current?.focus?.();
    };
  }, [open]);

  // 手机档焦点陷阱：全屏覆盖时 Tab 不应跑到背后的对话里
  useEffect(() => {
    if (!open || isDesktop) return;
    const node = panelRef.current;
    if (!node) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const items = Array.from(
        node.querySelectorAll<HTMLElement>(
          "button:not([disabled]), [href], input:not([disabled]), select, textarea, [tabindex]:not([tabindex='-1'])",
        ),
      ).filter((el) => el.offsetParent !== null);
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    node.addEventListener("keydown", onKeyDown);
    return () => node.removeEventListener("keydown", onKeyDown);
  }, [open, isDesktop]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div className={`fixed inset-0 ${z} lg:pointer-events-none`}>
          {/* 小于 lg：面板铺满并带遮罩（模态）；lg+ 才作为并排侧栏，不遮挡对话。
              分界选 lg（1024）而不是 md：768 宽度下再并排 440px 面板，
              对话只剩不到 100px，等于把主功能挤没了。 */}
          <div
            className="absolute inset-0 bg-black/40 backdrop-blur-sm lg:hidden"
            onClick={onClose}
            aria-hidden
          />
          <motion.aside
            ref={panelRef}
            role="complementary"
            aria-label={title}
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 420, damping: 42 }}
            className="pointer-events-auto absolute right-0 top-0 flex h-full w-full flex-col border-l border-border bg-card shadow-lift lg:w-[var(--xm-panel-w,440px)]"
            style={{
              paddingTop: "env(safe-area-inset-top)",
              paddingBottom: "env(safe-area-inset-bottom)",
            }}
          >
            {/* 拖拽分隔条：仅桌面显示。双击恢复默认宽度（handleProps 内已绑定）。 */}
            <div
              role="separator"
              aria-orientation="vertical"
              aria-label={t("app.resizePanel")}
              aria-valuenow={width}
              className={`absolute -left-1 top-0 hidden h-full w-2 cursor-col-resize transition-colors hover:bg-primary/30 lg:block ${
                dragging ? "bg-primary/40" : ""
              }`}
              {...handleProps}
            />
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
                className="shrink-0 rounded-md p-2.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground lg:p-2"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            {/* @container：内容区按自身宽度响应（而非视口），面板变窄时内部自动切窄布局 */}
            <div className="@container min-h-0 flex-1 overflow-y-auto scroll-thin p-4">{children}</div>
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
