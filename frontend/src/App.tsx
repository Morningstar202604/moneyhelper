import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { MotionConfig } from "framer-motion";
import { PanelLeftOpen, X } from "lucide-react";
import { SessionSidebar } from "@/components/SessionSidebar";
import { Onboarding } from "@/components/Onboarding";
import { CommandPalette } from "@/components/CommandPalette";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ConfirmDialog } from "@/components/ui/confirm";
import { OfflineBanner } from "@/components/ui/offline-banner";
import { PasswordDialog } from "@/components/ui/password-dialog";
import { ErrorBoundary } from "@/lib/ErrorBoundary";
import { useBootstrap, useSessions, store } from "@/lib/store";
import { api, getToken } from "@/lib/api";
import { LoginView } from "@/components/LoginView";
import { useToast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
import { useIsDesktop } from "@/lib/use-media-query";
import { useResizableWidth } from "@/lib/use-resizable-width";
import { TopBar } from "@/components/TopBar";
import { MobileDrawer } from "@/components/MobileDrawer";
import { MobileTabBar } from "@/components/MobileTabBar";

// 首屏只需要 TopBar + 会话栏 + 对话区。以下面板都是"点开才用"，
// 静态引入会把它们的依赖（Dashboard 的图表、部门看板、设置表单）压进主包。
const ChatView = lazy(() => import("@/components/ChatView").then((m) => ({ default: m.ChatView })));
const SettingsView = lazy(() => import("@/components/SettingsView").then((m) => ({ default: m.SettingsView })));
const DataModal = lazy(() => import("@/components/DataModal").then((m) => ({ default: m.DataModal })));
const ScheduledOutputsPanel = lazy(() =>
  import("@/components/ScheduledOutputsPanel").then((m) => ({ default: m.ScheduledOutputsPanel })),
);
const DepartmentPanel = lazy(() =>
  import("@/components/DepartmentPanel").then((m) => ({ default: m.DepartmentPanel })),
);

export type DataKind = "overview" | "holdings" | "market" | "ledger" | "health";

export default function App() {
  const { t } = useI18n();
  const { sessions, loading: sessionsLoading } = useSessions();
  const { bootstrap } = useBootstrap();
  const { toast } = useToast();

  // 数据浮层：对话里的卡片点"展开"才弹出，非常驻侧栏
  const [dataModal, setDataModal] = useState<{ open: boolean; kind: DataKind }>({ open: false, kind: "overview" });
  const [settingsOpen, setSettingsOpen] = useState(false);

  const [activeThread, setActiveThread] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<{ id: number; threadId: string } | null>(null);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [cmdOpen, setCmdOpen] = useState(false);
  // 侧栏面板状态集中在此：桌面侧栏与移动抽屉都要能打开它们
  const [inboxOpen, setInboxOpen] = useState(false);
  const [deptOpen, setDeptOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  // 桌面侧栏按视口条件渲染（而非 CSS 隐藏）：避免同一入口在移动端出现两份
  // 可访问 DOM（屏幕阅读器与自动化工具都会读到）
  const isDesktop = useIsDesktop();
  // 桌面侧栏宽度可拖拽（持久化）；最小 200 保证会话标题可读，最大 420 不挤压对话
  const navWidth = useResizableWidth({
    storageKey: "wo.navWidth",
    defaultWidth: 240,
    min: 200,
    max: 420,
  });
  const [locateRunId, setLocateRunId] = useState<number | null>(null);

  const [userCount, setUserCount] = useState<number | null>(null);
  const [authed, setAuthed] = useState<boolean>(!!getToken());

  useEffect(() => {
    if (getToken()) return;
    api<{ count: number }>("/api/auth/user-count")
      .then((r) => setUserCount(r.count ?? 0))
      .catch(() => setUserCount(0));
  }, []);

  const [sidebarOpen, setSidebarOpen] = useState(() => {
    try {
      return localStorage.getItem("wo.sidebar") !== "0";
    } catch {
      return true;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem("wo.sidebar", sidebarOpen ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [sidebarOpen]);

  const colorScheme = bootstrap?.settings.color_scheme ?? "cn";
  useEffect(() => {
    document.documentElement.dataset.scheme = colorScheme === "us" ? "us" : "cn";
  }, [colorScheme]);

  // 适老化：字号档位与高对比度写进根元素，由 index.css 的 data-* 规则统一放大
  const textScale = bootstrap?.settings.text_scale ?? "normal";
  const highContrast = bootstrap?.settings.high_contrast ?? "off";
  useEffect(() => {
    const root = document.documentElement;
    root.dataset.textScale = textScale;
    root.dataset.contrast = highContrast === "on" ? "high" : "normal";
  }, [textScale, highContrast]);

  useEffect(() => {
    if (bootstrap?.settings.data_note !== "empty") return;
    try {
      if (localStorage.getItem("wo.onboarded") === "1") return;
    } catch {
      return;
    }
    setShowOnboarding(true);
  }, [bootstrap]);

  const newSession = useCallback(async () => {
    const tmp = `__tmp_${Date.now()}`;
    setActiveThread((cur) => (cur === null ? tmp : cur));
    try {
      const r = await api<{ id: number; thread_id: string }>("/api/sessions", {
        method: "POST",
        body: JSON.stringify({}),
      });
      await store.refreshSessions();
      if (typeof r.id === "number") {
        try {
          await api(`/api/sessions/${r.id}/migrate?from=${encodeURIComponent(tmp)}`, {
            method: "POST",
            body: JSON.stringify({}),
          });
        } catch {
          /* ignore */
        }
      }
      setActiveThread((cur) => (cur === tmp ? r.thread_id : cur));
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    }
  }, [toast]);

  const openChat = useCallback(
    (threadId: string | null) => {
      if (!threadId && sessions.length === 0) {
        void newSession();
        return;
      }
      setActiveThread(threadId ?? sessions[0]?.thread_id ?? null);
    },
    [sessions, newSession],
  );

  const deleteSession = useCallback(
    async (id: number, threadId: string) => {
      try {
        await api(`/api/sessions/${id}`, { method: "DELETE" });
        await store.refreshSessions();
        if (activeThread === threadId) {
          setActiveThread(null);
          if (sessions.length <= 1) void newSession();
          else {
            const next = sessions.find((s) => s.thread_id !== threadId);
            setActiveThread(next?.thread_id ?? null);
          }
        }
        toast(t("app.sessionDeleted"), "ok");
      } catch (e) {
        toast(e instanceof Error ? e.message : String(e), "error");
      }
    },
    [activeThread, sessions, newSession, toast, t],
  );

  const renameSession = useCallback(
    async (id: number, title: string) => {
      try {
        await api(`/api/sessions/${id}`, {
          method: "PATCH",
          body: JSON.stringify({ title }),
        });
        await store.refreshSessions();
      } catch (e) {
        toast(e instanceof Error ? e.message : String(e), "error");
      }
    },
    [toast],
  );

  useEffect(() => {
    if (activeThread) return;
    // 会话列表加载完成前不下结论：否则会把「加载中」误判为「没有任何会话」，
    // 每次打开都新建垃圾会话，且首发消息可能滞留在 __tmp_ 线程。
    if (sessionsLoading) return;
    if (sessions.length > 0) setActiveThread(sessions[0].thread_id);
    else void newSession();
  }, [activeThread, sessions, sessionsLoading, newSession]);

  // 对话里的"跳转意图"：弹数据浮层，不切页面、不占常驻侧栏
  const openData = useCallback((kind: string) => {
    if (kind === "settings") {
      setSettingsOpen(true);
      return;
    }
    const valid: DataKind[] = ["overview", "holdings", "market", "ledger", "health"];
    const k = (valid as string[]).includes(kind) ? (kind as DataKind) : "overview";
    setDataModal({ open: true, kind: k });
  }, []);

  // 需要登录但还没登录：渲染登录页。
  // 必须放在**所有 hooks 之后**——hooks 数量在多次渲染间必须一致，
  // 提前 return 会触发 "Rendered fewer hooks than expected" 白屏。
  if (userCount !== null && userCount > 0 && !authed) {
    return (
      <MotionConfig reducedMotion="user">
        <LoginView onAuthed={() => setAuthed(true)} />
      </MotionConfig>
    );
  }

  return (
    <MotionConfig reducedMotion="user">
      <TooltipProvider>
        <OfflineBanner />
        <ErrorBoundary>
          <div className="flex h-full">
            {/* 左侧会话栏：窄、常驻、可折叠（仅桌面渲染，移动端用抽屉） */}
            {isDesktop && (
            <aside
              className={cn(
                "relative flex shrink-0 flex-col border-r border-border bg-card/40 transition-[width] duration-200",
                sidebarOpen ? "" : "w-12",
              )}
              style={sidebarOpen ? { width: navWidth.width } : undefined}
            >
              {sidebarOpen ? (
                <SessionSidebar
                  activeThread={activeThread}
                  onHome={() => setDataModal({ open: true, kind: "overview" })}
                  onSelect={openChat}
                  onNew={() => void newSession()}
                  onDelete={(id, threadId) => setPendingDelete({ id, threadId })}
                  onRename={renameSession}
                  onOpenSettings={() => setSettingsOpen(true)}
                  onCollapse={() => setSidebarOpen(false)}
                  onOpenDept={() => setDeptOpen(true)}
                  onOpenInbox={() => setInboxOpen(true)}
                />
              ) : (
                <div className="flex h-full w-12 flex-col items-center pt-2">
                  <button
                    type="button"
                    aria-label={t("sidebar.expand")}
                    onClick={() => setSidebarOpen(true)}
                    className="p-2 text-muted-foreground hover:text-primary transition-colors"
                  >
                    <PanelLeftOpen className="w-4 h-4" />
                  </button>
                </div>
              )}
              {sidebarOpen && (
                <div
                  role="separator"
                  aria-orientation="vertical"
                  aria-label={t("sidebar.resize")}
                  aria-valuenow={navWidth.width}
                  className={cn(
                    "absolute -right-1 top-0 z-10 h-full w-2 cursor-col-resize transition-colors hover:bg-primary/30",
                    navWidth.dragging && "bg-primary/40",
                  )}
                  {...navWidth.handleProps}
                />
              )}
            </aside>
            )}

            {/* 中间对话区：占满，绝对主角；数据面板在 lg+ 展开时按面板宽度让位。
                变量 --xm-panel-w 由 SidePanel 写入，断点必须与 SidePanel 的
                "模态 vs 并排"分界一致（lg），否则会出现"面板盖住对话但不让位"。 */}
            <div
              className={cn(
                "flex flex-1 min-w-0 flex-col transition-[margin] duration-200",
                dataModal.open && "lg:mr-[var(--xm-panel-w,440px)]",
              )}
            >
              <TopBar
                onOpenSettings={() => setSettingsOpen(true)}
                onOpenNav={() => setMobileNavOpen(true)}
              />

              <main className="flex-1 min-h-0 pb-[calc(3.25rem+env(safe-area-inset-bottom))] md:pb-0">
                <div className="mx-auto w-full max-w-3xl h-full flex flex-col view-enter">
                  <Suspense
                    fallback={
                      <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
                        {t("app.preparing")}
                      </div>
                    }
                  >
                    {activeThread ? (
                      <ChatView
                        key={activeThread}
                        threadId={activeThread}
                        locateRunId={locateRunId}
                        onLocateDone={() => setLocateRunId(null)}
                        onNewSession={() => void newSession()}
                        onSwitch={openChat}
                        onOpenSettings={() => setSettingsOpen(true)}
                        onNavigate={openData}
                      />
                    ) : (
                      <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
                        {t("app.preparing")}
                      </div>
                    )}
                  </Suspense>
                </div>
              </main>
            </div>
          </div>

          {/* 移动端导航抽屉：桌面侧栏在 <md 隐藏，此处提供等价入口（会话列表/新建/部门/收件箱） */}
          {!isDesktop && (
          <MobileDrawer open={mobileNavOpen} onClose={() => setMobileNavOpen(false)}>
            <SessionSidebar
              activeThread={activeThread}
              onHome={() => {
                setMobileNavOpen(false);
                setDataModal({ open: true, kind: "overview" });
              }}
              onSelect={(tid) => {
                setMobileNavOpen(false);
                openChat(tid);
              }}
              onNew={() => {
                setMobileNavOpen(false);
                void newSession();
              }}
              onDelete={(id, threadId) => setPendingDelete({ id, threadId })}
              onRename={renameSession}
              onOpenSettings={() => {
                setMobileNavOpen(false);
                setSettingsOpen(true);
              }}
              onCollapse={() => setMobileNavOpen(false)}
              onOpenDept={() => {
                setMobileNavOpen(false);
                setDeptOpen(true);
              }}
              onOpenInbox={() => {
                setMobileNavOpen(false);
                setInboxOpen(true);
              }}
            />
          </MobileDrawer>
          )}

          {/* 侧栏面板：桌面与移动端共用同一份状态（避免两端各挂一份导致重复请求） */}
          <Suspense fallback={null}>
            {inboxOpen && <ScheduledOutputsPanel open onClose={() => setInboxOpen(false)} />}
            {deptOpen && <DepartmentPanel open onClose={() => setDeptOpen(false)} />}
          </Suspense>

          {/* 手机端底部导航：高频入口常驻拇指区，其余功能走抽屉 */}
          {!isDesktop && (
            <MobileTabBar
              active={dataModal.open ? dataModal.kind : "chat"}
              onChat={() => setDataModal((d) => ({ ...d, open: false }))}
              onData={(k) => setDataModal({ open: true, kind: k })}
              onInbox={() => setInboxOpen(true)}
              onSettings={() => setSettingsOpen(true)}
            />
          )}

          {/* 数据工具侧面板：按需从右侧滑出，不遮挡对话（自管理开合动画） */}
          <Suspense fallback={null}>
            <DataModal
              open={dataModal.open}
              kind={dataModal.kind}
              onKindChange={(k) => setDataModal({ open: true, kind: k })}
              onClose={() => setDataModal({ ...dataModal, open: false })}
            />
          </Suspense>

          {/* 设置页：全屏 overlay */}
          {settingsOpen && (
            <div className="fixed inset-0 z-40 overflow-y-auto bg-background">
              <div className="sticky top-0 z-10 flex justify-end border-b border-border bg-background/90 backdrop-blur px-4 py-2">
                <button
                  type="button"
                  onClick={() => setSettingsOpen(false)}
                  className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-foreground"
                >
                  <X className="w-4 h-4" /> {t("app.close")}
                </button>
              </div>
              <Suspense
                fallback={
                  <div className="py-12 text-center text-sm text-muted-foreground">{t("app.preparing")}</div>
                }
              >
                <SettingsView />
              </Suspense>
            </div>
          )}

          <ConfirmDialog
            open={pendingDelete !== null}
            onOpenChange={(o) => {
              if (!o) setPendingDelete(null);
            }}
            title={t("app.deleteTitle")}
            description={t("app.deleteDesc")}
            confirmText={t("app.delete")}
            danger
            onConfirm={() => {
              const td = pendingDelete;
              setPendingDelete(null);
              if (td) void deleteSession(td.id, td.threadId);
            }}
          />

          <PasswordDialog />

          <CommandPalette
            open={cmdOpen}
            onOpenChange={setCmdOpen}
            onNavigateChat={() => undefined}
            onNavigateFeature={openData}
            onOpenSettings={() => setSettingsOpen(true)}
            onNewSession={() => void newSession()}
            sessions={sessions}
            onSelectSession={openChat}
          />

          {showOnboarding && (
            <Onboarding
              onNavigate={(where) => {
                if (where === "settings") setSettingsOpen(true);
                else openData(where);
              }}
              onDone={() => {
                try {
                  localStorage.setItem("wo.onboarded", "1");
                } catch {
                  /* ignore */
                }
                setShowOnboarding(false);
              }}
            />
          )}
        </ErrorBoundary>
      </TooltipProvider>
    </MotionConfig>
  );
}
