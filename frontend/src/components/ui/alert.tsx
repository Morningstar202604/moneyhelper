import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * 警告提示组件（shadcn 范式：cva 定义 variant，语义化图标槽位）。
 * 保留旧版 AlertBanner 的 warn/info 语义（对应 destructive/default）。
 *
 * 兼容导出：AlertBanner 作为别名保留，内部复用 Alert + AlertTitle。
 * 旧版调用方无需修改即可继续工作。
 */

/** 兼容旧版 AlertBanner：内部基于 shadcn Alert 组件构造 */

import type { ReactNode } from "react";

export function AlertBanner({
  tone = "warn",
  icon,
  children,
  action,
  className,
}: {
  tone?: "warn" | "info";
  icon?: ReactNode;
  children: ReactNode;
  /** 右侧操作区（按钮/链接） */
  action?: ReactNode;
  className?: string;
}) {
  const variant = tone === "warn" ? "warn" : "default";
  return (
    <Alert variant={variant} className={className}>
      {icon && <span className="mr-2 inline-flex items-center">{icon}</span>}
      <span className="flex-1">
        <AlertDescription className="inline">{children}</AlertDescription>
      </span>
      {action && <div className="ml-auto flex items-center gap-2">{action}</div>}
    </Alert>
  );
}
const alertVariants = cva(
  "relative w-full rounded-lg border px-4 py-3 text-sm [&>svg+div]:translate-y-[-3px] [&>svg]:absolute [&>svg]:left-4 [&>svg]:top-4 [&>svg]:text-foreground [&>svg~*]:pl-7",
  {
    variants: {
      variant: {
        default: "border-border bg-card text-foreground",
        destructive: "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400 [&>svg]:text-red-500",
        warn: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400 [&>svg]:text-amber-500",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

const Alert = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof alertVariants>
>(({ className, variant, ...props }, ref) => (
  <div
    ref={ref}
    role="alert"
    data-slot="alert"
    className={cn(alertVariants({ variant }), className)}
    {...props}
  />
));
Alert.displayName = "Alert";

const AlertTitle = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h5
    ref={ref}
    data-slot="alert-title"
    className={cn("mb-1 font-medium leading-none tracking-tight", className)}
    {...props}
  />
));
AlertTitle.displayName = "AlertTitle";

const AlertDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    data-slot="alert-description"
    className={cn("text-xs [&_p]:leading-relaxed", className)}
    {...props}
  />
));
AlertDescription.displayName = "AlertDescription";

export { Alert, AlertTitle, AlertDescription };
