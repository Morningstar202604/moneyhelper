import * as React from "react";
import { cn } from "@/lib/utils";

type PanelProps = React.HTMLAttributes<HTMLDivElement>;

/** 面板容器：与 Card 同款视觉但无 shadow-xs，padding 走 var(--card-pad)。 */
export const Panel = React.forwardRef<HTMLDivElement, PanelProps>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("rounded-[var(--radius)] border border-border bg-card p-[var(--card-pad)]", className)} {...props} />
  ),
);
Panel.displayName = "Panel";

/** 小尺寸面板：紧凑 padding 场景（如指数条）。 */
export const PanelSm = React.forwardRef<HTMLDivElement, PanelProps>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("rounded-[var(--radius)] border border-border bg-card px-3 py-2", className)} {...props} />
  ),
);
PanelSm.displayName = "PanelSm";
