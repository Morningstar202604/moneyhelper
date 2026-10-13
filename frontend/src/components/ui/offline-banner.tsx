/** 离线横幅：navigator.onLine=false 时顶部提醒；网络恢复后自动隐藏。 */
import { useEffect, useState } from "react";
import { WifiOff } from "lucide-react";

export function OfflineBanner() {
  const [offline, setOffline] = useState(!navigator.onLine);

  useEffect(() => {
    const onOnline = () => setOffline(false);
    const onOffline = () => setOffline(true);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  if (!offline) return null;

  return (
    <div className="sticky top-0 z-50 flex items-center justify-center gap-2 bg-amber-500 px-4 py-2 text-center text-sm font-medium text-white">
      <WifiOff className="h-4 w-4" />
      网络已断开 — 部分功能暂不可用，将自动恢复连接
    </div>
  );
}
