import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import { useToast } from "@/lib/toast";
import { AiGenerate } from "./ai-generate";

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
