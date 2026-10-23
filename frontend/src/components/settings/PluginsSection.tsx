import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Loader2, Plug, Plus, RefreshCw, Trash2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { useI18n } from "@/lib/i18n";
import { Section, inputCls, labelCls } from "./shared";

interface McpServer {
  name: string;
  url: string;
  tools: string[];
}

/**
 * MCP 插件：外部工具服务器（Claude Code / Cursor 用的同一套协议）。
 *
 * 之前只能手改 backend/data/mcp.json，改错一个逗号整个配置失效且没有任何提示。
 * 现在可在此增删、测试连通性，并看到每台服务器实际暴露的工具名。
 * 凭据（URL 里的 user:token）由后端打码后回显。
 */
export function PluginsSection() {
  const { t } = useI18n();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);

  const list = useQuery({
    queryKey: ["/api/mcp/servers"],
    queryFn: () => api<{ servers: McpServer[] }>("/api/mcp/servers").then((r) => r.servers ?? []),
  });
  const servers = list.data ?? [];

  const save = async (next: McpServer[]) => {
    setSaving(true);
    try {
      await api("/api/mcp/servers", {
        method: "PUT",
        body: JSON.stringify({ servers: next.map((s) => ({ name: s.name, url: s.url })) }),
      });
      await qc.invalidateQueries({ queryKey: ["/api/mcp/servers"] });
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    } finally {
      setSaving(false);
    }
  };

  const add = async () => {
    const n = name.trim();
    const u = url.trim();
    if (!n || !u) return;
    if (servers.some((s) => s.name === n)) {
      toast(t("plugins.nameTaken"), "error");
      return;
    }
    await save([...servers, { name: n, url: u, tools: [] }]);
    setName("");
    setUrl("");
    toast(t("plugins.saved"), "ok");
  };

  const test = async () => {
    const u = url.trim();
    if (!u) return;
    setTesting(true);
    try {
      const r = await api<{ tools: string[] }>("/api/mcp/test", {
        method: "POST",
        body: JSON.stringify({ url: u }),
      });
      toast(t("plugins.testOk", { n: (r.tools ?? []).length }), "ok");
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    } finally {
      setTesting(false);
    }
  };

  return (
    <Section
      title={t("settings.navPlugins")}
      icon={<Plug className="w-4 h-4 text-muted-foreground" />}
      desc={t("plugins.desc")}
    >
      <div className="space-y-3">
        <div className="grid gap-2 sm:grid-cols-[10rem_minmax(0,1fr)]">
          <div>
            <label className={labelCls}>{t("plugins.name")}</label>
            <input
              className={inputCls}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="my-server"
              maxLength={40}
            />
          </div>
          <div>
            <label className={labelCls}>{t("plugins.url")}</label>
            <input
              className={inputCls}
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com/mcp"
              spellCheck={false}
            />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={() => void add()} disabled={saving || !name.trim() || !url.trim()}>
            <Plus className="h-3.5 w-3.5" /> {t("plugins.add")}
          </Button>
          <Button size="sm" variant="outline" onClick={() => void test()} disabled={testing || !url.trim()}>
            {testing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            {t("plugins.test")}
          </Button>
          <span className="text-[11px] text-muted-foreground">{t("plugins.hint")}</span>
        </div>

        {list.isPending ? (
          <p className="py-4 text-center text-xs text-muted-foreground">{t("plugins.loading")}</p>
        ) : servers.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">
            {t("plugins.empty")}
          </div>
        ) : (
          <ul className="space-y-2">
            {servers.map((s) => (
              <li key={s.name} className="rounded-lg border border-border px-3 py-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5 text-sm font-medium">
                      {s.tools.length > 0 ? (
                        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                      ) : (
                        <XCircle className="h-3.5 w-3.5 text-muted-foreground" />
                      )}
                      {s.name}
                    </div>
                    <div className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground">{s.url}</div>
                    {s.tools.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {s.tools.slice(0, 8).map((tool) => (
                          <span
                            key={tool}
                            className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
                          >
                            {tool}
                          </span>
                        ))}
                        {s.tools.length > 8 && (
                          <span className="text-[10px] text-muted-foreground">+{s.tools.length - 8}</span>
                        )}
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    aria-label={t("plugins.remove", { name: s.name })}
                    className="shrink-0 rounded p-1.5 text-muted-foreground hover:bg-red-500/10 hover:text-red-600"
                    onClick={() => void save(servers.filter((x) => x.name !== s.name))}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}

        <p className="text-[11px] leading-relaxed text-muted-foreground">{t("plugins.writeGuard")}</p>
      </div>
    </Section>
  );
}
