import { useState } from "react";
import { Sparkles } from "lucide-react";
import { useToast } from "@/lib/toast";

/** AI 一键生成：描述一句话 → 生成 skill / 角色描述建议（用户采用后才进配置，随底部保存落库）。 */
export function AiGenerate({
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
        className="inline-flex items-center gap-1 rounded-md border border-primary/30 bg-primary/5 px-2 py-1 text-xs text-primary transition-colors hover:bg-primary/10"
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
          className="rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground disabled:opacity-50"
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
          className="rounded-md px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
        >
          取消
        </button>
      </div>
      {sugg && (
        <div className="mt-2 rounded-md border border-border bg-card p-2">
          <div className="text-xs font-medium">{sugg.name}</div>
          <div className="mt-0.5 text-xs text-muted-foreground">{sugg.description}</div>
          <div className="mt-1.5 flex gap-1.5">
            <button
              type="button"
              onClick={() => {
                onApply(sugg);
                setOpen(false);
                setSugg(null);
                setPrompt("");
              }}
              className="rounded-md bg-primary/90 px-2 py-1 text-xs text-primary-foreground"
            >
              采用
            </button>
            <button
              type="button"
              onClick={generate}
              className="rounded-md px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
            >
              重生成
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
