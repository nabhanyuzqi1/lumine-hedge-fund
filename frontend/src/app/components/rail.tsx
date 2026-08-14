import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import type { Workspace } from "@/stores/uiStore";
import { WORKSPACES, useUiStore } from "@/stores/uiStore";

const WORKSPACE_PATHS: Record<string, string> = {
  trading: "/terminal",
  research: "/dashboard",
  risk: "/health",
  ops: "/journal",
  superadmin: "/superadmin",
};

const PATH_WORKSPACE: Record<string, string> = {
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

  // Sync workspace with current route
  useEffect(() => {
    const path = location.pathname as keyof typeof PATH_WORKSPACE;
    if (PATH_WORKSPACE[path]) {
      setWorkspace(PATH_WORKSPACE[path] as Workspace);
    }
  }, [location.pathname, setWorkspace]);

  return (
    <nav
      className="flex flex-col items-center justify-start border-t border-border-subtle bg-bg-raised p-2 md:h-full md:w-14 md:border-r md:border-t-0"
      aria-label="Workspace navigation"
      data-testid="rail"
    >
      {WORKSPACES.map((ws) => {
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
            className={cn(
                    "flex w-full items-center justify-center rounded-chip p-2 transition-all duration-100",
                    active
                      ? "bg-accent/15 text-accent shadow-[inset_2px_0_0_0_var(--color-accent)]"
                      : "text-text-muted hover:bg-bg-overlay hover:text-text-secondary"
                  )}
                >
                  <div className="h-4 w-4">{ws.icon}</div>
            <span className="sr-only">{ws.tooltip}</span>
          </button>
        );
      })}
    </nav>
  );
}
