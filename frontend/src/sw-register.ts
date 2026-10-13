/* PWA Service Worker 注册
 * - 生产环境注册（import.meta.env.PROD），开发环境跳过避免干扰 HMR
 * - 注册失败静默处理（console.warn 不 throw）
 * - 暴露 window.__swReady Promise 供业务代码 await 就绪
 * - 新 SW 接管后 controllerchange 事件提示刷新 */

declare global {
  interface Window {
    __swReady?: Promise<ServiceWorkerRegistration | undefined>;
  }
}

if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.__swReady = navigator.serviceWorker
    .register("/sw.js", { scope: "/" })
    .then((registration) => {
      // 后台定期检查更新（不阻塞就绪 Promise）
      registration.update().catch(() => {});
      return registration;
    })
    .catch((err) => {
      console.warn("[PWA] Service Worker 注册失败:", err);
      return undefined;
    });

  // 新 SW 接管所有标签页时，提示用户刷新以获取最新版本
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    window.dispatchEvent(new CustomEvent("sw-controller-change"));
  });
}

export {};
