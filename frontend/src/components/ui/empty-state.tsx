import { BarChart3, FolderOpen, Inbox, Layers, Search, Target, Wallet } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

/** 内置默认插图映射：常见空态场景自动匹配风格化图标 */
const ILLUSTRATIONS: Record<string, ReactNode> = {
  data: <Layers className="w-10 h-10 text-primary/50" />,
  holdings: <BarChart3 className="w-10 h-10 text-primary/50" />,
  search: <Search className="w-10 h-10 text-muted-foreground/50" />,
  goal: <Target className="w-10 h-10 text-primary/50" />,
  wallet: <Wallet className="w-10 h-10 text-primary/50" />,
  inbox: <Inbox className="w-10 h-10 text-muted-foreground/50" />,
  folder: <FolderOpen className="w-10 h-10 text-muted-foreground/50" />,
};

/** 空态占位：compact=纯文字一行；默认=卡片式（插图+标题+描述+操作区）。 */
export function EmptyState({
  icon,
  illustration,
  text,
  title,
  desc,
  actions,
  mode = "card",
  className,
}: {
  /** 自定义图标（优先级高于 illustration） */
  icon?: ReactNode;
  /** 内置插图名称：data | holdings | search | goal | wallet | inbox | folder */
  illustration?: keyof typeof ILLUSTRATIONS;
  /** compact 模式的一行文字 */
  text?: ReactNode;
  /** card 模式的标题 */
  title?: ReactNode;
  /** card 模式的描述 */
  desc?: ReactNode;
  /** card 模式的按钮区 */
  actions?: ReactNode;
  mode?: "compact" | "card";
  className?: string;
}) {
  const resolvedIcon = icon ?? (illustration ? ILLUSTRATIONS[illustration] : undefined);

  if (mode === "compact") {
    return (
      <div
        className={cn(
          "flex items-center justify-center gap-2 py-5 text-sm text-muted-foreground",
          className,
        )}
      >
        {resolvedIcon}
        {text}
      </div>
    );
  }
  return (
    <div className={cn("flex flex-col items-center justify-center px-4 py-8 text-center", className)}>
      {resolvedIcon && (
        <div className="mb-3 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/5">
          {resolvedIcon}
        </div>
      )}
      {title && <div className="text-sm font-semibold text-foreground">{title}</div>}
      {desc && <p className="mt-1.5 max-w-xs text-sm leading-relaxed text-muted-foreground text-balance">{desc}</p>}
      {actions && <div className="mt-4 flex flex-wrap justify-center gap-2">{actions}</div>}
    </div>
  );
}
