import { cn } from "@/lib/utils";

/**
 * 骨架屏组件（shadcn 范式：工具类驱动 + 复用 CSS shimmer 动画）。
 * 保留原 .skeleton 工具类（定义在 index.css），组合出 shadcn 风格的 Skeleton。
 */
function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      data-slot="skeleton"
      className={cn("skeleton", className)}
      {...props}
    />
  );
}

/** 仪表盘骨架：统计卡 + 图表面板。保留旧版 DashboardSkeleton 的完整布局。 */
function DashboardSkeleton() {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="card-surface p-[var(--card-pad)]">
            <Skeleton className="h-3 w-16" />
            <Skeleton className="mt-2 h-6 w-24" />
            <Skeleton className="mt-1.5 h-3 w-14" />
          </div>
        ))}
      </div>
      <Skeleton className="h-14 w-full" />
      <div className="grid lg:grid-cols-2 gap-3">
        <div className="card-surface p-[var(--card-pad)]">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="mt-3 h-48 w-full" />
        </div>
        <div className="card-surface p-[var(--card-pad)]">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="mt-3 h-48 w-full" />
        </div>
      </div>
    </div>
  );
}

export { Skeleton, DashboardSkeleton };
