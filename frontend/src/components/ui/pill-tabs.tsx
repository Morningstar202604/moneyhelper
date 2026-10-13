import { cn } from "@/lib/utils";

/** 通用 pill 标签组：border 样式（区别于 Segmented 的底色切换），size 兼容两种现有密度。 */
export function PillTabs<T extends string>({
  value,
  options,
  onChange,
  size = "sm",
  className,
  role,
  label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  size?: "sm" | "md";
  className?: string;
  /** 首层容器 role（FeaturesView 传 "tablist"） */
  role?: string;
  label?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)} role={role} aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={cn(
            "rounded-md font-medium border transition-colors",
            size === "sm" ? "px-2.5 py-1 text-xs" : "px-3 py-1.5 text-sm",
            value === o.value
              ? "border-primary bg-primary/10 text-primary"
              : "border-border text-muted-foreground hover:text-foreground",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
