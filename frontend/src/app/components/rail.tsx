import { WORKSPACES, useUiStore } from '@/stores/uiStore';

export function Rail() {
  const workspace = useUiStore((s) => s.workspace);
  const setWorkspace = useUiStore((s) => s.setWorkspace);

  return (
    <nav
      className="flex w-14 flex-col gap-1 border-r border-border-subtle bg-bg-raised p-2"
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
            aria-current={active ? 'page' : undefined}
            data-testid={`rail-${ws.id}`}
            className={[
              'flex flex-col items-center justify-center rounded-chip py-2 text-[10px] font-medium transition-colors',
              active
                ? 'bg-bg-base text-text-primary'
                : 'text-text-secondary hover:bg-bg-base/50 hover:text-text-primary',
            ].join(' ')}
          >
            <span>{ws.label.slice(0, 2)}</span>
            <span>{ws.label.slice(2)}</span>
          </button>
        );
      })}
    </nav>
  );
}
