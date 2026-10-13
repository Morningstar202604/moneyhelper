import { useState } from "react";
import { KeyRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getToken, setToken } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { useI18n } from "@/lib/i18n";
import { Section, inputCls, labelCls } from "./shared";

/** 访问口令设置（本地 token 读写 + 保存） */
export function TokenSection() {
  const { t } = useI18n();
  const { toast } = useToast();
  const [tokenInput, setTokenInput] = useState(getToken());

  return (
    <Section title={t("settings.navToken")} icon={<KeyRound className="w-4 h-4 text-muted-foreground" />}>
      <div className="flex items-end gap-2">
        <div className="flex-1">
          <label className={labelCls}>{t("settings.tokenInput")}</label>
          <input className={inputCls} type="password" value={tokenInput} onChange={(e) => setTokenInput(e.target.value)} placeholder={t("settings.tokenPh")} />
        </div>
        <Button size="sm" onClick={() => { setToken(tokenInput.trim()); toast(t("settings.tokenUpdated"), "ok"); }}>
          {t("settings.save")}
        </Button>
      </div>
      <div className="mt-2 text-[11px] text-muted-foreground">
        {t("settings.tokenHint")}
      </div>
    </Section>
  );
}
