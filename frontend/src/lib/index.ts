// Barrel export: 统一管理 lib/ 模块入口，简化调用点 import 路径

// 类型
export type * from "./types";

// 格式化 / 展示
export { fmtMoney, fmtPct, pnlClass, fmtDate, setMoneyLocale, getMoneyLocale } from "./format";

// API 客户端
export { api, apiStream, setToken, uploadAttachment, deleteAttachment } from "./api";

// 状态管理
export { store, useBootstrap, useDashboard, useSessions } from "./store";

// 数据变更
export { useMutate } from "./use-mutate";
export { useStreamingMutate } from "./use-streaming-mutate";

// 国际化
export { useI18n, I18nProvider } from "./i18n";

// 主题
export { useTheme, ThemeProvider } from "./theme";

// 提示
export { useToast, Toaster } from "./toast";

// 品牌
export { BRAND, BrandLogo } from "./brand";

// 工具
export { cn } from "./utils";

// 图表配置
export { usePalette, axisLabelColor } from "./charts";
