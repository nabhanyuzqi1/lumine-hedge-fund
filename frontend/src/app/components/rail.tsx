import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth/role-context";
import type { Workspace } from "@/stores/uiStore";
import { WORKSPACES, useUiStore } from "@/stores/uiStore";

const WORKSPACE_PATHS: Record<string, string> = {
  trading: "/app/terminal",
  research: "/app/dashboard",
  risk: "/app/health",
  ops: "/app/journal",
  superadmin: "/superadmin",
  news: "/app/news",
};

const PATH_WORKSPACE: Record<string, string> = {
  "/app/terminal": "trading",
  "/app/dashboard": "research",
  "/app/health": "risk",
  "/app/journal": "ops",
  "/app/news": "news",
  "/terminal": "trading",
  "/dashboard": "research",
  "/health": "risk",
  "/journal": "ops",
  "/superadmin": "superadmin",
};

export function Rail() {
  const location = useLocation();
  const navigate = useNavigate();
  const workspace = useUiStore((s) => s.workspace);
  const setWorkspace = useUiStore((s) => s.setWorkspace);
  const hasRole = useAuth().hasRole;

  // Sync workspace with current route
  useEffect(() => {
    const path = location.pathname as keyof typeof PATH_WORKSPACE;
    if (PATH_WORKSPACE[path]) {
      setWorkspace(PATH_WORKSPACE[path] as Workspace);
    }
  }, [location.pathname, setWorkspace]);

  // Superadmin entry hanya untuk role superadmin (role-gated).
  const visibleWorkspaces = WORKSPACES.filter((ws) => ws.id !== "superadmin" || hasRole("superadmin"));

  return (
    <nav
      className="flex flex-row items-stretch justify-start overflow-x-auto border-t border-line bg-raised p-1 md:h-full md:w-14 md:flex-col md:overflow-x-visible md:overflow-y-auto md:border-r md:border-t-0 md:p-2"
      aria-label="Workspace navigation"
      data-testid="rail"
    >
      {visibleWorkspaces.map((ws) => {
        const active = workspace === ws.id;
        return (
          <button
            key={ws.id}
            onClick={() => {
              const path = WORKSPACE_PATHS[ws.id] || `/${ws.id}`;
              navigate(path);
            }}
            aria-current={active ? "page" : undefined}
            data-testid={`rail-${ws.id}`}
            title={ws.tooltip}
            aria-label={ws.tooltip}
            className={cn(
              "group relative flex items-center gap-1.5 whitespace-nowrap rounded-chip px-2.5 py-2 transition-colors md:w-full md:flex-col md:gap-0 md:px-0 md:py-2",
              active
                ? "bg-accent/15 text-accent shadow-[inset_2px_0_0_0_var(--color-accent)] md:shadow-[inset_2px_0_0_0_var(--color-accent)]"
                : "text-ink-faint hover:bg-raised hover:text-ink-dim"
            )}
          >
            <div className="h-4 w-4 shrink-0">{ws.icon}</div>
            {/* Label — terlihat di mobile bottom-nav, tooltip di desktop */}
            <span className="text-[10px] font-medium uppercase tracking-wide md:sr-only">
              {ws.tooltip.split(" ")[0]}
            </span>
          </button>
        );
      })}
    </nav>
  );
}
