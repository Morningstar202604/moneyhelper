/** 品牌系统：小满 —— 名称 / 标语 / Logo / 品牌色预设。 */

export const BRAND = {
  name: "小满",
  /** 品牌 slogan：二十四节气「小满」，谷物渐满未满——理财同理，慢慢存，富足自有分寸地到来 */
  slogan: "慢慢存，小满即富",
  /** 副标用动作对，不用"你的XX管家"这类换行业也通顺的口号 */
  tagline: "记一笔，问一句",
  en: "Xiaoman",
};

export interface BrandPreset {
  id: string;
  label: string;
  /** CSS 变量覆盖（HSL triplet 字符串，用于 :root 与 .dark） */
  light: Record<string, string>;
  dark: Record<string, string>;
  /** 品牌主色（浅色主题下用于图表高亮等） */
  accent: string;
}

/** 品牌色预设：麦金（默认）/ 翡翠 / 靛蓝 / 琥珀 / 石墨 */
export const BRAND_PRESETS: BrandPreset[] = [
  {
    id: "wheat",
    label: "麦金",
    light: {
      "--primary": "38 78% 45%",
      "--primary-foreground": "0 0% 100%",
      "--accent": "40 85% 94%",
      "--accent-foreground": "38 70% 22%",
      "--ring": "38 78% 50%",
      "--brand": "38 78% 45%",
    },
    dark: {
      "--primary": "40 88% 62%",
      "--primary-foreground": "35 60% 10%",
      "--accent": "40 40% 18%",
      "--accent-foreground": "40 75% 90%",
      "--ring": "40 88% 60%",
      "--brand": "40 88% 62%",
    },
    accent: "#b8891f",
  },
  {
    id: "emerald",
    label: "翡翠",
    light: {
      "--primary": "174 62% 29%",
      "--primary-foreground": "0 0% 100%",
      "--accent": "174 62% 93%",
      "--accent-foreground": "174 70% 20%",
      "--ring": "174 62% 34%",
      "--brand": "174 62% 29%",
    },
    dark: {
      "--primary": "174 62% 52%",
      "--primary-foreground": "180 60% 8%",
      "--accent": "174 40% 18%",
      "--accent-foreground": "174 60% 88%",
      "--ring": "174 62% 50%",
      "--brand": "174 62% 52%",
    },
    accent: "#0d7a66",
  },
  {
    id: "indigo",
    label: "靛蓝",
    light: {
      "--primary": "239 74% 52%",
      "--primary-foreground": "0 0% 100%",
      "--accent": "239 80% 93%",
      "--accent-foreground": "239 70% 38%",
      "--ring": "239 74% 55%",
      "--brand": "239 74% 52%",
    },
    dark: {
      "--primary": "239 84% 64%",
      "--primary-foreground": "240 60% 8%",
      "--accent": "239 40% 20%",
      "--accent-foreground": "239 70% 90%",
      "--ring": "239 84% 62%",
      "--brand": "239 84% 64%",
    },
    accent: "#4f46e5",
  },
  {
    id: "amber",
    label: "琥珀",
    light: {
      "--primary": "27 72% 36%",
      "--primary-foreground": "0 0% 100%",
      "--accent": "32 85% 93%",
      "--accent-foreground": "27 80% 28%",
      "--ring": "27 72% 42%",
      "--brand": "27 72% 36%",
    },
    dark: {
      "--primary": "35 88% 58%",
      "--primary-foreground": "25 60% 10%",
      "--accent": "32 45% 18%",
      "--accent-foreground": "35 80% 90%",
      "--ring": "35 88% 56%",
      "--brand": "35 88% 58%",
    },
    accent: "#a16207",
  },
  {
    id: "graphite",
    label: "石墨",
    light: {
      "--primary": "215 22% 34%",
      "--primary-foreground": "0 0% 100%",
      "--accent": "215 25% 92%",
      "--accent-foreground": "215 25% 24%",
      "--ring": "215 22% 38%",
      "--brand": "215 22% 34%",
    },
    dark: {
      "--primary": "215 18% 62%",
      "--primary-foreground": "215 30% 8%",
      "--accent": "215 20% 20%",
      "--accent-foreground": "215 20% 90%",
      "--ring": "215 18% 58%",
      "--brand": "215 18% 62%",
    },
    accent: "#475569",
  },
];

/**
 * 品牌 Logo：外圆古钱币 + 方孔 + 上升趋势线（钱生钱）。
 * 纯 SVG，随品牌色变化；size 为边长。
 */
export function BrandLogo({ size = 28, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      className={className}
      aria-label={`${BRAND.name} Logo`}
    >
      {/* 麦粒渐满：圆底麦粒 + 上扬的「慢慢攒」弧线 */}
      <circle cx="24" cy="24" r="21" fill="hsl(var(--primary) / 0.12)" />
      <circle cx="24" cy="24" r="21" stroke="hsl(var(--primary))" strokeWidth="2.6" />
      {/* 麦粒（居中，饱满一颗） */}
      <ellipse cx="24" cy="25" rx="5.6" ry="8.4" fill="hsl(var(--brand-gold, 43 78% 46%))" transform="rotate(-22 24 25)" />
      {/* 麦芒 */}
      <path
        d="M24 16.6 L24 10.6 M21.2 18.6 L17.6 14.4 M26.8 18.6 L30.4 14.4"
        stroke="hsl(var(--brand-gold, 43 78% 46%))"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      {/* 上扬积累弧线 */}
      <path
        d="M10.5 34 C15 28.5 20 27.5 24.5 29.5"
        stroke="hsl(var(--primary))"
        strokeWidth="2.4"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}
