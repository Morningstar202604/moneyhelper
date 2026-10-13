/* 每次构建时自动替换 sw.js 中的缓存版本号，保证发布新版本时浏览器更新 SW 并清理旧缓存。 */
import { readFileSync, writeFileSync } from "node:fs";

const swPath = new URL("../public/sw.js", import.meta.url);
const src = readFileSync(swPath, "utf8");

// 匹配 xiaoman-pwa-<任意版本> 并替换为新版本戳
const stamp = `xiaoman-pwa-${Date.now()}`;
const out = src.replace(/xiaoman-pwa-v[\d.]+/g, stamp);

writeFileSync(swPath, out);
console.log("[bump-sw] cache version:", stamp);
