/** 后端返回的 level 中文代号 → i18n key 的映射，前端统一本地化（避免英文界面出现中文等级）。 */
export const LEVEL_KEYS: Record<string, string> = {
  "L2 建议": "summary.l2",
  "L1 洞察": "summary.l1",
  "已记账": "summary.recorded",
  "待确认": "summary.pending",
  "已执行": "summary.executed",
  "已取消": "summary.cancelled",
  "失败": "summary.failed",
  "需要补充": "summary.needsInput",
  "已生成": "summary.generated",
  "未识别": "summary.unrecognized",
  "已入账": "summary.booked",
  "已记住": "summary.remembered",
};

/** 取本地化后的 level 文案；未命中则原样返回（防御性兜底）。 */
export function levelLabel(
  t: (k: string, vars?: Record<string, string | number>) => string,
  level: string,
): string {
  const key = LEVEL_KEYS[level];
  return key ? t(key) : level;
}

/** 是否为「需要处理」级告警（原后端代号 L2 建议）。 */
export function isLevelAlert(level: string): boolean {
  return level === "L2 建议";
}