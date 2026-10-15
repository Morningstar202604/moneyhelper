import { useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import { useToast } from "@/lib/toast";
import { listSkillRuns } from "@/lib/api";
import { emitInboxRefresh } from "@/lib/inbox";
import { fmtDate } from "@/lib/format";
import type { RunRecord } from "@/lib/types";
import { AiGenerate } from "./ai-generate";

/** 内置技能 id（与后端 agent_config.BUILTIN_SKILLS 同口径）：有运行时落点，不可删除；其余为自定义技能 */
const BUILTIN_SKILL_IDS = new Set(["risk_analysis", "goals_tracking", "morning_report", "long_memory"]);

interface SkillAction {
  prompt: string;
  /** HH:MM（24 小时制，Asia/Shanghai） */
  time: string;
  /** 0=周一 … 6=周日；空数组 = 每天 */
  weekdays: number[];
}

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
    action?: SkillAction | null;
  }>;
  defaults: Record<string, unknown>;
}

const WEEKDAY_LABELS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

/** 动作摘要文案：每天 09:00 / 周一、周日 20:00 */
function fmtAction(a: SkillAction): string {
  const days = a.weekdays.length ? a.weekdays.map((d) => WEEKDAY_LABELS[d]).join("、") : "每天";
  return `${days} ${a.time}`;
}

export function AgentSection() {
  const { t } = useI18n();
  const [config, setConfig] = useState<AgentConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedJson, setSavedJson] = useState("");
  const [running, setRunning] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<{ skillId: string; answer: string } | null>(null);
  const [historyFor, setHistoryFor] = useState<string | null>(null);
  const [history, setHistory] = useState<RunRecord[] | null>(null);
  /** 正在编辑动作的技能 id；null = 无 */
  const [editingAction, setEditingAction] = useState<string | null>(null);
  /** 动作编辑草稿（保存按钮写回 config；与定时任务行为按"保存即生效"） */
  const [draft, setDraft] = useState<{ time: string; weekdays: number[]; prompt: string }>({
    time: "20:00",
    weekdays: [],
    prompt: "",
  });
  const { toast } = useToast();

  useEffect(() => {
    fetch("/api/agent-config")
      .then((r) => r.json())
      .then((d) => {
        if (d.ok) {
          setConfig(d.config);
          setSavedJson(JSON.stringify(d.config));
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const openActionEditor = (skillId: string) => {
    const a = config?.skills[skillId]?.action;
    setDraft({
      time: a?.time ?? "20:00",
      weekdays: a?.weekdays ?? [],
      prompt: a?.prompt ?? "",
    });
    setEditingAction(skillId);
  };

  /** 保存动作草稿进本地 config（点「保存配置」落库；未填 prompt 视为移除动作） */
  const commitDraft = (skillId: string) => {
    if (!config) return;
    const next = { ...config.skills };
    if (draft.prompt.trim()) {
      next[skillId] = {
        ...next[skillId],
        action: { prompt: draft.prompt.trim(), time: draft.time, weekdays: [...draft.weekdays].sort((a, b) => a - b) },
      };
    } else {
      const { action: _drop, ...rest } = next[skillId];
      next[skillId] = rest;
    }
    setConfig({ ...config, skills: next });
    setEditingAction(null);
  };

  const save = async (): Promise<boolean> => {
    if (!config) return false;
    setSaving(true);
    try {
      const r = await fetch("/api/agent-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config }),
      });
      const d = await r.json();
      if (d.ok) {
        // 服务端会剔除非法定时动作并回报；如实展示而不是假装全保存成功
        const warnings: string[] = Array.isArray(d.warnings) ? d.warnings : [];
        if (warnings.length) toast(warnings.join("；"), "error");
        else toast(t("agent.saved"), "ok");
        setSavedJson(JSON.stringify(config));
        return true;
      }
      toast(t("agent.saveFailed"), "error");
      return false;
    } catch {
      toast(t("agent.saveFailed"), "error");
      return false;
    } finally {
      setSaving(false);
    }
  };

  /** 立即触发技能动作：先保存（未保存的编辑直接生效，与定时行为一致）再触发 */
  const runNow = async (skillId: string) => {
    if (!config) return;
    const dirty = JSON.stringify(config) !== savedJson;
    if (dirty && !(await save())) return;
    setRunning(skillId);
    try {
      const r = await fetch(`/api/skills/${encodeURIComponent(skillId)}/run`, { method: "POST" });
      const d = await r.json();
      if (d.ok) {
        toast(t("agent.ranOk"), "ok");
        setLastRun({ skillId, answer: String(d.answer ?? "") });
        // 通知侧栏收件箱徽标立即刷新（不等轮询）
        emitInboxRefresh();
        if (historyFor === skillId) void loadHistory(skillId);
      } else {
        toast(String(d.error || t("agent.runFailed")), "error");
      }
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    } finally {
      setRunning(null);
    }
  };

  /** 触发历史（归档线程 skill:<id>）：与「最近一次」互补，用于核查到点是否真的跑过 */
  const loadHistory = async (skillId: string) => {
    try {
      setHistory(await listSkillRuns(skillId, 10));
    } catch {
      setHistory([]);
    }
  };

  const toggleHistory = async (skillId: string) => {
    if (historyFor === skillId) {
      setHistoryFor(null);
      return;
    }
    setHistoryFor(skillId);
    setHistory(null);
    await loadHistory(skillId);
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
            hint="一句话描述新技能，比如：每周日晚提醒我检查定投计划并给一句风险提示"
            onApply={(s) =>
              setConfig({
                ...config,
                skills: {
                  ...config.skills,
                  [s.id]:
                    s.id in config.skills
                      ? {
                          ...config.skills[s.id],
                          name: s.name,
                          description: s.description,
                          // 模型识别出定时意图时一并带上动作
                          ...(s.action ? { action: s.action as unknown as SkillAction } : {}),
                        }
                      : {
                          name: s.name,
                          description: s.description,
                          enabled: true,
                          ...(s.action ? { action: s.action as unknown as SkillAction } : {}),
                        },
                },
              })
            }
          />
        </div>
        <div className="mb-1.5 text-xs text-muted-foreground">
          内置技能的开关会真正改变 AI 能力（如关闭「长期记忆」后不再记忆/召回）；自定义技能会作为指令注入助手；
          带定时动作的技能到点自动执行（结果归档在「问AI」历史外的独立线程，可在下方查看最近一次）。
        </div>
        <div className="space-y-2">
          {Object.entries(config.skills).map(([key, skill]) => (
            <div key={key} className="rounded-lg border border-border px-3 py-2">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-sm">
                    {skill.name}
                    {!BUILTIN_SKILL_IDS.has(key) && (
                      <span className="ml-1.5 rounded bg-primary/10 px-1.5 py-0.5 text-[11px] text-primary">自定义</span>
                    )}
                    {skill.action && (
                      <span className="ml-1.5 rounded bg-sky-500/10 px-1.5 py-0.5 text-[11px] text-sky-600 dark:text-sky-400">
                        ⏰ {fmtAction(skill.action)}
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground">{skill.description}</div>
                </div>
                <span className="flex shrink-0 items-center gap-1.5">
                  {!BUILTIN_SKILL_IDS.has(key) && (
                    <button
                      type="button"
                      aria-label={t(skill.action ? "agent.scheduleEdit" : "agent.scheduleAdd", { c: skill.name })}
                      className="rounded px-1.5 py-0.5 text-[11px] text-muted-foreground hover:bg-primary/10 hover:text-primary"
                      onClick={() => (editingAction === key ? setEditingAction(null) : openActionEditor(key))}
                    >
                      {t(skill.action ? "agent.scheduleEditLabel" : "agent.scheduleAddLabel")}
                    </button>
                  )}
                  {skill.action && (
                    <button
                      type="button"
                      aria-label={t("agent.runNow", { c: skill.name })}
                      className="rounded px-1.5 py-0.5 text-[11px] text-muted-foreground hover:bg-primary/10 hover:text-primary disabled:opacity-50"
                      disabled={running === key}
                      onClick={() => void runNow(key)}
                    >
                      {running === key ? t("agent.running2") : t("agent.runNowLabel")}
                    </button>
                  )}
                  {skill.action && (
                    <button
                      type="button"
                      aria-label={t("agent.historyToggle", { c: skill.name })}
                      aria-expanded={historyFor === key}
                      className="rounded px-1.5 py-0.5 text-[11px] text-muted-foreground hover:bg-primary/10 hover:text-primary"
                      onClick={() => void toggleHistory(key)}
                    >
                      {historyFor === key ? t("agent.historyHideLabel") : t("agent.historyShowLabel")}
                    </button>
                  )}
                  {!BUILTIN_SKILL_IDS.has(key) && (
                    <button
                      type="button"
                      aria-label={`删除技能 ${skill.name}`}
                      className="rounded p-1 text-muted-foreground hover:bg-red-500/10 hover:text-red-600"
                      onClick={() => {
                        const next = { ...config.skills };
                        delete next[key];
                        setConfig({ ...config, skills: next });
                      }}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                  <button
                    type="button"
                    aria-label={`${skill.enabled ? "关闭" : "启用"}技能 ${skill.name}`}
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
                </span>
              </div>

              {/* 定时动作编辑：时间 + 星期（不选=每天） + 提示词；清空提示词并保存 = 移除动作 */}
              {editingAction === key && (
                <div className="mt-2 rounded-md border border-dashed border-primary/30 bg-primary/5 p-2.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <label className="flex items-center gap-1 text-xs text-muted-foreground">
                      {t("agent.actionTime")}
                      <input
                        type="time"
                        value={draft.time}
                        onChange={(e) => setDraft({ ...draft, time: e.target.value })}
                        className="rounded border border-input bg-background px-1.5 py-0.5 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
                      />
                    </label>
                    <span className="flex flex-wrap items-center gap-1">
                      {WEEKDAY_LABELS.map((label, idx) => (
                        <button
                          key={idx}
                          type="button"
                          aria-pressed={draft.weekdays.includes(idx)}
                          aria-label={label}
                          onClick={() =>
                            setDraft({
                              ...draft,
                              weekdays: draft.weekdays.includes(idx)
                                ? draft.weekdays.filter((d) => d !== idx)
                                : [...draft.weekdays, idx],
                            })
                          }
                          className={`rounded px-1.5 py-0.5 text-[11px] transition-colors ${
                            draft.weekdays.includes(idx)
                              ? "bg-primary text-primary-foreground"
                              : "bg-muted text-muted-foreground hover:text-foreground"
                          }`}
                        >
                          {label}
                        </button>
                      ))}
                      <span className="text-[11px] text-muted-foreground">{t("agent.actionEveryDayHint")}</span>
                    </span>
                  </div>
                  <textarea
                    value={draft.prompt}
                    onChange={(e) => setDraft({ ...draft, prompt: e.target.value })}
                    placeholder={t("agent.actionPromptPh")}
                    rows={2}
                    maxLength={200}
                    className="mt-1.5 w-full resize-none rounded-md border border-input bg-background px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                  <div className="mt-1.5 flex items-center gap-1.5">
                    <Button size="sm" className="h-6 px-2 text-xs" onClick={() => commitDraft(key)}>
                      {t("agent.actionOk")}
                    </Button>
                    <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={() => setEditingAction(null)}>
                      {t("agent.actionCancel")}
                    </Button>
                    <span className="text-[11px] text-muted-foreground">{t("agent.actionSaveHint")}</span>
                  </div>
                </div>
              )}

              {/* 最近一次手动触发结果（如实回显，不落会话） */}
              {lastRun?.skillId === key && lastRun.answer && (
                <div className="mt-2 rounded-md border border-border bg-card p-2 text-xs">
                  <div className="text-[11px] text-muted-foreground">{t("agent.lastRun")}</div>
                  <div className="mt-1 whitespace-pre-wrap text-foreground/90">{lastRun.answer.slice(0, 400)}</div>
                </div>
              )}

              {/* 触发历史（含定时触发）：核查"到点到底跑没跑" */}
              {historyFor === key && (
                <div className="mt-2 rounded-md border border-border bg-muted/30 p-2 text-xs">
                  <div className="text-[11px] text-muted-foreground">{t("agent.historyTitle")}</div>
                  {history === null ? (
                    <div className="mt-1 text-muted-foreground">{t("app.loading")}</div>
                  ) : history.length === 0 ? (
                    <div className="mt-1 text-muted-foreground">{t("agent.historyEmpty")}</div>
                  ) : (
                    <ul className="mt-1 space-y-1.5">
                      {history.map((r) => (
                        <li key={r.id} className="rounded border border-border bg-card px-2 py-1.5">
                          <div className="flex items-baseline justify-between gap-2">
                            <span className="text-[11px] text-muted-foreground">{fmtDate(r.created_at)}</span>
                            <span className="text-[11px] text-muted-foreground">{r.level}</span>
                          </div>
                          <div className="mt-0.5 line-clamp-2 text-foreground/90" title={r.answer}>
                            {r.question}
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
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
