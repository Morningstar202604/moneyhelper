/// <reference types="vite/client" />

interface Window {
  __swReady?: Promise<ServiceWorkerRegistration | undefined>;
}

interface CustomEventMap {
  "sw-controller-change": CustomEvent;
}

declare global {
  interface WindowEventMap extends CustomEventMap {}
}

export {};
