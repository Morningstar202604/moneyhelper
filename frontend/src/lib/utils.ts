/** className 合并：clsx（条件拼接）+ tailwind-merge（后项覆盖冲突类名）。
 *
 * 为什么不用手写 join：手写版会把 `bg-red-500` 和 `bg-blue-500` 同时留在 class 里，
 * 后写的不一定生效（取决于 CSS 源顺序）；twMerge 能识别 tailwind 冲突并保留后者。
 */

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...parts: ClassValue[]): string {
  return twMerge(clsx(parts));
}
