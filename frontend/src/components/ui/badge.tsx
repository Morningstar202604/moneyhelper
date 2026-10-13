import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * 徽章变体（shadcn 范式：cva 定义 variant 矩阵）。
 * 相比旧版 Badge 组件：保留原 variant 语义（default/secondary/outline/muted/warn/danger/ok），
 * 额外新增 ghost/destructive 变体以满足 shadcn 生态扩展需要。
 */
const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary/15 text-primary",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        outline: "border-border text-foreground",
        muted: "border-transparent bg-muted text-muted-foreground",
        warn: "border-transparent bg-amber-500/15 text-amber-700 dark:text-amber-400",
        danger: "border-transparent bg-red-500/15 text-red-700 dark:text-red-400",
        destructive: "border-transparent bg-red-500/90 text-white",
        ok: "border-transparent bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
        ghost: "border-transparent bg-transparent text-muted-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant, ...props }, ref) => {
    return (
      <span
        ref={ref}
        data-slot="badge"
        className={cn(badgeVariants({ variant }), className)}
        {...props}
      />
    );
  },
);
Badge.displayName = "Badge";

export { Badge, badgeVariants };
