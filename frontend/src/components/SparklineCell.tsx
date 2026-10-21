import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { MiniSparkline } from "@/components/MiniSparkline";
import type { KlinePoint } from "@/components/KlineDialog";

/**
 * 列表里的迷你走势格（股票软件的「分时/近 60 日」列）。
 *
 * 懒加载策略：每行独立查询，React Query 统一缓存（同 symbol 不重复请求），
 * 60 日数据 5 分钟内复用。失败时留空而不是显示错误——列表里不该出现红字。
 */
export function SparklineCell({ symbol }: { symbol: string }) {
  const q = useQuery({
    queryKey: ["/api/kline", symbol, "spark"],
    queryFn: () =>
      api<{ points: KlinePoint[] }>(`/api/kline?symbol=${encodeURIComponent(symbol)}&period=daily&limit=60`),
    staleTime: 5 * 60_000,
    retry: 0,
  });
  const points = q.data?.points ?? [];
  if (!points.length) return <span className="text-[11px] text-muted-foreground/40">—</span>;
  const first = points[0].close;
  const last = points[points.length - 1].close;
  const up = last >= first;
  return (
    <MiniSparkline
      points={points}
      className="h-7 w-full"
      positiveColor={up ? "#dc2626" : "#059669"}
      negativeColor={up ? "#dc2626" : "#059669"}
    />
  );
}
