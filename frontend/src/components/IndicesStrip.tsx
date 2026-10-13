import { Activity } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { fmtPct, pnlClass } from "@/lib/format";
import { PanelSm } from "@/components/ui/panel";
import type { IndexQuote } from "@/lib/types";

/** 指数行情条：四大指数实时涨跌，横向滚动（失败时整条隐藏）。总览与行情页共用。 */
export function IndicesStrip({ indices }: { indices: IndexQuote[] }) {
  const { t, lang } = useI18n();
  if (!indices.length) return null;
  return (
    <PanelSm>
      <div className="mb-1 flex items-center gap-1.5 text-xs text-muted-foreground">
        <Activity className="w-3.5 h-3.5" /> {t("dash.market")}
      </div>
      <div className="flex gap-6 overflow-x-auto scroll-thin pb-0.5">
        {indices.map((i) => (
          <div key={i.symbol} className="shrink-0 text-sm">
            <span className="text-muted-foreground">{i.name}</span>
            {/* 指数点位是点数不是金额：完整千分位（不压缩、不带货币符号） */}
            <span className="ml-2 tabular-nums font-medium">
              {i.price.toLocaleString(lang === "zh" ? "zh-CN" : "en-US", { maximumFractionDigits: 2 })}
            </span>
            <span className={`ml-1.5 tabular-nums ${pnlClass(i.change_pct)}`}>{fmtPct(i.change_pct, true)}</span>
          </div>
        ))}
      </div>
    </PanelSm>
  );
}
