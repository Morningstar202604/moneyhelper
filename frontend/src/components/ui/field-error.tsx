import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** 表单错误提示：单行红字（替代 7 处手写 div）。 */
export function FieldError({ children, className }: { children: ReactNode; className?: string }) {
  if (!children) return null;
  return <div className={cn("text-xs text-red-600 dark:text-red-400", className)}>{children}</div>;
}
