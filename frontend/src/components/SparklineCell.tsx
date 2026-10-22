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
/** 与后端 quotes._to_secid 对齐：只有 6 位数字且属于沪深股票/场内基金才有 K 线。
 *  场外基金（如 110011）、现金等直接返回占位，避免每次列表渲染都打一条 404。 */
function hasKline(symbol: string): boolean {
  const s = symbol.trim().toUpperCase();
  if (!/^\d{6}$/.test(s)) return false;
  return s[0] === "6" || s[0] === "5" || s[0] === "0" || s[0] === "3" || s.startsWith("15") || s.startsWith("16");
}

export function SparklineCell({ symbol }: { symbol: string }) {
  const supported = hasKline(symbol);
  const q = useQuery({
    queryKey: ["/api/kline", symbol, "spark"],
    queryFn: () =>
      api<{ points: KlinePoint[] }>(`/api/kline?symbol=${encodeURIComponent(symbol)}&period=daily&limit=60`),
    staleTime: 5 * 60_000,
    retry: 0,
    enabled: supported,
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
