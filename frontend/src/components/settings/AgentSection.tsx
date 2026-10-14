import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import { useToast } from "@/lib/toast";

interface AgentConfig {
  version: string;
  agents: Record<string, {
    name: string;
    description: string;
    enabled: boolean;
    tools: string[] | string;
    temperature: number;
  }>;
  skills: Record<string, {
    name: string;
    description: string;
    enabled: boolean;
  }>;
  defaults: Record<string, unknown>;
}

/** AI 一键生成：描述一句话 → 生成 skill / 角色描述建议（用户采用后才进配置，随底部保存落库）。 */
function AiGenerate({
  kind,
  agent,
  hint,
  onApply,
}: {
  kind: "skill" | "agent";
  agent?: string;
  hint: string;
  onApply: (s: Record<string, string>) => void;
}) {
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [sugg, setSugg] = useState<Record<string, string> | null>(null);
  const { toast } = useToast();

  const generate = async () => {
    if (!prompt.trim()) return;
    setBusy(true);
    setSugg(null);
    try {
      const r = await fetch("/api/agent-config/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, agent, prompt }),
      });
      const d = await r.json();
      if (d.ok) setSugg(d.suggestion);
      else toast(String(d.error || "生成失败"), "error");
    } catch {
      toast("生成失败", "error");
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1 rounded-md border border-primary/30 bg-primary/5 px-2 py-1 text-[11px] text-primary transition-colors hover:bg-primary/10"
      >
        <Sparkles className="w-3 h-3" /> AI 生成
      </button>
    );
  }

  return (
    <div className="w-full rounded-lg border border-primary/30 bg-primary/5 p-2.5">
      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder={hint}
        rows={2}
        className="w-full resize-none rounded-md border border-input bg-background px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
      />
      <div className="mt-1.5 flex items-center gap-1.5">
        <button
          type="button"
          disabled={busy || !prompt.trim()}
          onClick={generate}
          className="rounded-md bg-primary px-2.5 py-1 text-[11px] font-medium text-primary-foreground disabled:opacity-50"
        >
          {busy ? "AI 生成中…" : "生成"}
        </button>
        <button
          type="button"
          onClick={() => {
            setOpen(false);
            setSugg(null);
            setPrompt("");
          }}
          className="rounded-md px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground"
        >
          取消
        </button>
      </div>
      {sugg && (
        <div className="mt-2 rounded-md border border-border bg-card p-2">
          <div className="text-xs font-medium">{sugg.name}</div>
          <div className="mt-0.5 text-[11px] text-muted-foreground">{sugg.description}</div>
          <div className="mt-1.5 flex gap-1.5">
            <button
              type="button"
              onClick={() => {
                onApply(sugg);
                setOpen(false);
                setSugg(null);
                setPrompt("");
              }}
              className="rounded-md bg-primary/90 px-2 py-1 text-[11px] text-primary-foreground"
            >
              采用
            </button>
            <button
              type="button"
              onClick={generate}
              className="rounded-md px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground"
            >
              重生成
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function AgentSection() {
  const { t } = useI18n();
  const [config, setConfig] = useState<AgentConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    fetch("/api/agent-config")
      .then((r) => r.json())
      .then((d) => {
        if (d.ok) setConfig(d.config);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const save = async () => {
    if (!config) return;
    setSaving(true);
    try {
      const r = await fetch("/api/agent-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config }),
      });
      const d = await r.json();
      if (d.ok) toast(t("agent.saved"), "ok");
      else toast(t("agent.saveFailed"), "error");
    } catch {
      toast(t("agent.saveFailed"), "error");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="text-sm text-muted-foreground">加载中…</div>;
  if (!config) return <div className="text-sm text-red-500">加载失败</div>;

  return (
    <div className="space-y-6">
      {/* Agents */}
      <div>
        <h3 className="mb-3 text-sm font-medium">Agent 角色</h3>
        <div className="space-y-3">
          {Object.entries(config.agents).map(([key, agent]) => (
            <div key={key} className="rounded-lg border border-border p-3">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium">{agent.name}</div>
                  <div className="text-xs text-muted-foreground">{agent.description}</div>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setConfig({
                      ...config,
                      agents: { ...config.agents, [key]: { ...agent, enabled: !agent.enabled } },
                    })
                  }
                  className={`relative h-6 w-11 rounded-full transition-colors ${agent.enabled ? "bg-primary" : "bg-muted"}`}
                >
                  <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${agent.enabled ? "translate-x-5" : "translate-x-0.5"}`} />
                </button>
              </div>
              <div className="mt-2 flex items-center justify-between gap-2">
                <div className="text-xs text-muted-foreground">
                  工具：{agent.tools === "all" ? "全部" : Array.isArray(agent.tools) ? `${agent.tools.length} 个` : agent.tools}
                </div>
                <AiGenerate
                  kind="agent"
                  agent={key}
                  hint="描述这个角色该怎么工作，比如：回答更简洁，先给结论再给数字"
                  onApply={(s) =>
                    setConfig({
                      ...config,
                      agents: {
                        ...config.agents,
                        [key]: {
                          ...agent,
                          name: s.name || agent.name,
                          description: s.description || agent.description,
                        },
                      },
                    })
                  }
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Skills */}
      <div>
        <div className="mb-3 flex items-center justify-between gap-2">
          <h3 className="text-sm font-medium">Skills 技能</h3>
          <AiGenerate
            kind="skill"
            hint="一句话描述新技能，比如：每周提醒我检查定投计划"
            onApply={(s) =>
              setConfig({
                ...config,
                skills: {
                  ...config.skills,
                  [s.id]:
                    s.id in config.skills
                      ? { ...config.skills[s.id], name: s.name, description: s.description }
                      : { name: s.name, description: s.description, enabled: true },
                },
              })
            }
          />
        </div>
        <div className="space-y-2">
          {Object.entries(config.skills).map(([key, skill]) => (
            <div key={key} className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
              <div>
                <div className="text-sm">{skill.name}</div>
                <div className="text-xs text-muted-foreground">{skill.description}</div>
              </div>
              <button
                type="button"
                onClick={() =>
                  setConfig({
                    ...config,
                    skills: { ...config.skills, [key]: { ...skill, enabled: !skill.enabled } },
                  })
                }
                className={`relative h-6 w-11 rounded-full transition-colors ${skill.enabled ? "bg-primary" : "bg-muted"}`}
              >
                <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${skill.enabled ? "translate-x-5" : "translate-x-0.5"}`} />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Defaults */}
      <div>
        <h3 className="mb-3 text-sm font-medium">默认配置</h3>
        <div className="rounded-lg border border-border p-3 text-sm">
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>默认语言：{String(config.defaults.default_lang)}</div>
            <div>默认模型：{String(config.defaults.default_model)}</div>
            <div>审批阈值：¥{String(config.defaults.approval_threshold)}</div>
            <div>最大工具轮次：{String(config.defaults.max_tool_turns)}</div>
          </div>
        </div>
      </div>

      <Button onClick={save} disabled={saving}>
        {saving ? "保存中…" : "保存配置"}
      </Button>
    </div>
  );
}
