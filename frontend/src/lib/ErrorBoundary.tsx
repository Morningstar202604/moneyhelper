import { Component, type ErrorInfo, type ReactNode } from "react";
import { useI18n } from "@/lib/i18n";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  message?: string;
}

/**
 * 全局错误边界：任何子组件（含 lazy chunk 加载失败、渲染期异常）崩掉时，
 * 不再整页白屏，而是展示可读错误 + 「重新加载」按钮，保证首屏可用性与可恢复性。
 * 类组件无法直接使用 hook，语言检测走 localStorage（wo.lang）与 html lang 属性双通道。
 */
class ErrorBoundaryInner extends Component<Props & { t: (k: string) => string }, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(err: Error): State {
    return { hasError: true, message: err?.message || String(err) };
  }

  componentDidCatch(err: Error, info: ErrorInfo): void {
    // 生产环境清 console（通过 vite build 的 drop_console 移除）
    console.error("[ErrorBoundary]", err, info.componentStack);
  }

  private reload = (): void => {
    this.setState({ hasError: false });
    window.location.reload();
  };

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children;
    const { t } = this.props;
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-6">
        <div className="w-full max-w-md rounded-xl border border-border bg-card p-6 text-center shadow-sm">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-red-500/10 text-lg">
            ⚠️
          </div>
          <h1 className="text-base font-semibold text-foreground">
            {t("error.title")}
          </h1>
          {this.state.message && (
            <p className="mt-1.5 break-words text-xs text-muted-foreground">{this.state.message}</p>
          )}
          <button
            type="button"
            onClick={this.reload}
            className="mt-4 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
          >
            {t("error.reload")}
          </button>
        </div>
      </div>
    );
  }
}

export function ErrorBoundary({ children }: Props) {
  const { t } = useI18n();
  return <ErrorBoundaryInner t={t}>{children}</ErrorBoundaryInner>;
}
