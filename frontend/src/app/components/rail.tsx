import { WORKSPACES, useUiStore } from "@/stores/uiStore";

export function Rail() {
  const workspace = useUiStore((s) => s.workspace);
  const setWorkspace = useUiStore((s) => s.setWorkspace);

  return (
    <nav
      className="flex h-14 w-full flex-row items-center justify-around border-t border-border-subtle bg-bg-raised px-2 md:h-auto md:w-14 md:flex-col md:justify-start md:gap-1 md:border-r md:border-t-0 md:p-2"
      aria-label="Workspace"
      data-testid="rail"
    >
      {WORKSPACES.map((ws) => {
        const active = workspace === ws.id;
        return (
          <button
            key={ws.id}
            type="button"
            onClick={() => setWorkspace(ws.id)}
            aria-current={active ? "page" : undefined}
            data-testid={`rail-${ws.id}`}
            className={[
              "flex flex-col items-center justify-center rounded-chip text-[10px] font-medium transition-colors md:w-full md:py-2",
              active
                ? "bg-bg-base text-text-primary"
                : "text-text-secondary hover:bg-bg-base/50 hover:text-text-primary",
            ].join(" ")}
          >
            <span className="text-xs font-semibold md:hidden">{ws.label.slice(0, 2)}</span>
            <span className="hidden md:block">{ws.label.slice(0, 2)}</span>
            <span className="hidden md:block">{ws.label.slice(2)}</span>
          </button>
        );
      })}
    </nav>
  );
}
