import * as React from "react";

interface RouteErrorBoundaryProps {
  children: React.ReactNode;
}

interface RouteErrorState {
  hasError: boolean;
  message: string;
}

/**
 * RouteErrorBoundary — catch render errors in a route subtree and show a
 * graceful fallback instead of the React "Unexpected Application Error"
 * white screen. Works alongside react-router's errorElement for loader
 * errors; this one catches render/effect crashes inside lazy pages.
 */
export class RouteErrorBoundary extends React.Component<
  RouteErrorBoundaryProps,
  RouteErrorState
> {
  constructor(props: RouteErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, message: "" };
  }

  static getDerivedStateFromError(error: unknown): RouteErrorState {
    return {
      hasError: true,
      message: error instanceof Error ? error.message : String(error),
    };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Keep the error visible for debugging in dev console
    console.error("[RouteErrorBoundary]", error, info.componentStack);
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-[50vh] items-center justify-center p-6">
          <div className="w-full max-w-md space-y-4 rounded-panel border border-line bg-raised p-6 text-center">
            <div className="font-mono text-xs uppercase tracking-[0.25em] text-warn">
              ⚠ Runtime Error
            </div>
            <div className="font-display text-lg font-semibold text-ink">
              Something went wrong rendering this view
            </div>
            <p className="font-mono text-xs break-words text-ink-dim">
              {this.state.message || "Unknown error"}
            </p>
            <div className="flex justify-center gap-3 pt-2">
              <button
                type="button"
                onClick={this.handleReload}
                className="rounded-chip bg-accent px-4 py-2 font-mono text-[11px] uppercase tracking-[0.2em] text-white hover:bg-accent-soft"
              >
                Reload page
              </button>
              <a
                href="/app/terminal"
                className="rounded-chip border border-line px-4 py-2 font-mono text-[11px] uppercase tracking-[0.2em] text-ink hover:bg-raised"
              >
                Back to terminal
              </a>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default RouteErrorBoundary;