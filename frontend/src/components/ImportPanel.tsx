/** 数据导入面板（独立组件）：CSV 粘贴 / 文件上传 / 模板说明 —— Tab 切换 + 自动识别 + 预览 + 确认导入。
 *  与 EntryView 内联版不冲突（EntryView 保留其内部版本做快捷记账；本组件可在 Dashboard 侧栏复用）。 */

import { useState } from "react";
import { FileUp, Clipboard, BookOpen, CheckCircle2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/lib/toast";
import { useI18n } from "@/lib/i18n";
import { api } from "@/lib/api";
import { useMutate } from "@/lib/use-mutate";
import { useImportTemplates } from "@/lib/use-calculations";
import { fmtMoney } from "@/lib/format";
import { store } from "@/lib/store";

const inputCls =
  "w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring";

interface ParsedRow {
  date: string;
  item: string;
  category: string;
  amount: number;
}

interface ParseResult {
  columns: string[];
  mapping: { date: number; amount: number; type: number; desc: number };
  preview: ParsedRow[];
  rows: ParsedRow[];
  total: number;
  skipped: number;
}

interface ImportConfirmResult {
  imported: number;
  failed: string[];
}

function detectParser(content: string): string {
  if (content.includes("微信支付账单") || content.includes("微信昵称")) return "wechat";
  if (content.includes("支付宝") || content.includes("余额宝")) return "alipay";
  if (content.includes("银行") || content.includes("交易对手信息")) return "bank";
  return "generic";
}

export function ImportPanel({ onDone }: { onDone?: () => void }) {
  const { toast } = useToast();
  const { t: tt } = useI18n();
  const [content, setContent] = useState("");
  const [parsed, setParsed] = useState<ParseResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"paste" | "upload" | "template">("paste");
  const templates = useImportTemplates();

  const doCommit = useMutate<ParseResult, ImportConfirmResult>({
    fn: (rows) =>
      api<ImportConfirmResult>("/api/import/csv/confirm", {
        method: "POST",
        body: JSON.stringify({ rows: rows.rows }),
      }),
    key: undefined,
    silentError: true,
    onSettled: (res, e) => {
      setBusy(false);
      if (e) {
        toast(e instanceof Error ? e.message : String(e), "error");
        return;
      }
      if (!res) return;
      const okMsg = res.failed.length === 0
        ? tt("import.ok", { n: res.imported })
        : tt("import.partial", { n: res.imported, m: res.failed.length });
      toast(okMsg, res.failed.length === 0 ? "ok" : "error");
      setContent("");
      setParsed(null);
      store.bump();
      onDone?.();
    },
  });

  const parseCsv = async () => {
    if (!content.trim()) return;
    setBusy(true);
    const parser = detectParser(content);
    try {
      const r = await api<ParseResult>("/api/import/csv", {
        method: "POST",
        body: JSON.stringify({ content, parser }),
      });
      setParsed(r);
    } catch (e) {
      setParsed(null);
      toast(e instanceof Error ? e.message : String(e), "error");
    } finally {
      setBusy(false);
    }
  };

  const commit = () => {
    if (!parsed) return;
    setBusy(true);
    void doCommit.mutateAsync(parsed);
  };

  const readFile = (file: File) => {
    file.text()
      .then((text) => {
        if (!text.includes("\uFFFD")) return text;
        return file.arrayBuffer().then((buf) => new TextDecoder("gbk").decode(buf));
      })
      .then((text) => setContent(text))
      .catch(() => toast(tt("import.fileReadFail"), "error"));
  };

  const parserLabel = parsed ? detectParser(content) : "generic";
  const parserName = parserLabel === "wechat" ? tt("import.wechat") : parserLabel === "alipay" ? tt("import.alipay") : parserLabel === "bank" ? tt("import.bank") : tt("import.generic");

  return (
    <div className="rounded-xl border border-border p-3">
      <div className="flex items-center gap-2 text-sm font-medium mb-2">
        <FileUp className="w-4 h-4 text-primary" />
        {tt("import.title")}
      </div>

      <Tabs defaultValue="paste" value={tab} onValueChange={(v) => setTab(v as "paste" | "upload" | "template")}>
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="paste">
            <Clipboard className="w-3.5 h-3.5" /> {tt("import.tabPaste")}
          </TabsTrigger>
          <TabsTrigger value="upload">
            <FileUp className="w-3.5 h-3.5" /> {tt("import.tabUpload")}
          </TabsTrigger>
          <TabsTrigger value="template">
            <BookOpen className="w-3.5 h-3.5" /> {tt("import.tabTemplate")}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="paste" className="mt-3 space-y-3">
          <textarea
            className={`${inputCls} min-h-24 resize-y`}
            value={content}
            onChange={(e) => { setContent(e.target.value); setParsed(null); }}
            placeholder={tt("import.pastePh")}
          />
          <div className="flex items-center gap-2">
            <Button size="sm" onClick={() => void parseCsv()} disabled={busy || !content.trim()}>
              {busy ? tt("import.parsing") : tt("import.preview")}
            </Button>
            {parsed && (
              <Badge variant="outline" className="text-[11px]">
                {parserName}
              </Badge>
            )}
          </div>
        </TabsContent>

        <TabsContent value="upload" className="mt-3 space-y-3">
          <div className="rounded-lg border-2 border-dashed border-border/60 p-6 text-center">
            <FileUp className="w-6 h-6 text-muted-foreground mx-auto mb-2" />
            <p className="text-xs text-muted-foreground mb-3">{tt("import.dropHint")}</p>
            <label className="inline-flex items-center text-xs text-muted-foreground cursor-pointer hover:text-primary">
              {tt("import.uploadBtn")}
              <input
                type="file"
                accept=".csv,.txt,text/csv,text/plain"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) readFile(f);
                  e.target.value = "";
                }}
              />
            </label>
          </div>
          {content && (
            <Button size="sm" onClick={() => void parseCsv()} disabled={busy}>
              {busy ? tt("import.parsing") : tt("import.preview")}
            </Button>
          )}
        </TabsContent>

        <TabsContent value="template" className="mt-3">
          <div className="space-y-2">
            {templates?.data?.map((t) => (
              <div key={t.key} className="rounded-lg bg-muted/30 p-2.5">
                <div className="font-medium text-xs mb-1">{t.label}</div>
                <div className="text-[11px] text-muted-foreground">{t.description}</div>
                <div className="flex flex-wrap gap-1 mt-1.5">
                  {t.sample_columns.map((f) => (
                    <Badge key={f} variant="outline" className="text-[9px]">{f}</Badge>
                  ))}
                </div>
              </div>
            ))}
            {(!templates?.data || templates.data.length === 0) && (
              <div className="text-xs text-muted-foreground text-center py-4">
                {templates?.isLoading ? tt("import.loadingTemplates") : tt("import.noTemplates")}
              </div>
            )}
          </div>
        </TabsContent>
      </Tabs>

      {/* 预览结果 */}
      {parsed && (
        <div className="mt-3 pt-3 border-t border-border/60">
          <div className="text-xs mb-2 flex items-center gap-2">
            {parsed.skipped === 0
              ? <CheckCircle2 className="w-3.5 h-3.5 text-success" />
              : <AlertCircle className="w-3.5 h-3.5 text-amber-500" />
            }
            {tt("import.recognized", { n: parsed.total })}
            {parsed.skipped > 0 && ` · ${tt("import.skipped", { n: parsed.skipped })}`}
          </div>
          {parsed.preview.length > 0 && (
            <div className="overflow-x-auto max-h-40 overflow-y-auto scroll-thin">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-muted-foreground text-left">
                    <th className="py-1 pr-3">{tt("import.colDate")}</th>
                    <th className="py-1 pr-3">{tt("import.colName")}</th>
                    <th className="py-1 pr-3">{tt("import.colCategory")}</th>
                    <th className="py-1 text-right">{tt("import.colAmount")}</th>
                  </tr>
                </thead>
                <tbody>
                  {parsed.preview.map((p, i) => (
                    <tr key={i} className="border-t border-border/40">
                      <td className="py-1 pr-3 tabular-nums whitespace-nowrap">{p.date}</td>
                      <td className="py-1 pr-3 truncate max-w-32">{p.item}</td>
                      <td className="py-1 pr-3">{p.category}</td>
                      <td className={`py-1 text-right tabular-nums ${p.amount > 0 ? "text-up" : "text-down"}`}>
                        {fmtMoney(p.amount, true)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {parsed.total > parsed.preview.length && (
            <div className="text-[11px] text-muted-foreground mt-1 text-center">
              {tt("import.truncated", { shown: parsed.preview.length, total: parsed.total })}
            </div>
          )}
          <div className="mt-2 flex gap-2">
            <Button size="sm" onClick={commit} disabled={doCommit.isPending || busy || parsed.total === 0}>
              {busy ? tt("import.importing") : tt("import.confirm", { n: parsed.total })}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => { setParsed(null); setContent(""); }}>
              {tt("import.cancel")}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
