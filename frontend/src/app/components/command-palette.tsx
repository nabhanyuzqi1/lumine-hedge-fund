import * as React from 'react';
import { useNavigate } from 'react-router-dom';

import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useUiStore, type Workspace } from '@/stores/uiStore';
import { cn } from '@/lib/utils';

interface CommandItem {
  id: string;
  label: string;
  shortcut?: string;
  keywords: string[];
  group: string;
  action: () => void;
}

const WORKSPACES: { id: Workspace; label: string; number: string }[] = [
  { id: 'trading', label: 'Trading workspace', number: '1' },
  { id: 'research', label: 'Research workspace', number: '2' },
  { id: 'risk', label: 'Risk workspace', number: '3' },
  { id: 'ops', label: 'Ops workspace', number: '4' },
];

export function CommandPalette() {
  const navigate = useNavigate();
  const open = useUiStore((s) => s.commandPaletteOpen);
  const setOpen = useUiStore((s) => s.setCommandPaletteOpen);
  const setWorkspace = useUiStore((s) => s.setWorkspace);
  const setKillSwitch = useUiStore((s) => s.setKillSwitch);
  const killSwitchActive = useUiStore((s) => s.killSwitchActive);
  const [query, setQuery] = React.useState('');
  const [activeIndex, setActiveIndex] = React.useState(0);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const run = React.useCallback(
    (action: () => void) => {
      action();
      setOpen(false);
      setQuery('');
      setActiveIndex(0);
    },
    [setOpen],
  );

  const items: CommandItem[] = React.useMemo(() => {
    const list: CommandItem[] = [
      {
        id: 'nav-terminal',
        label: 'Go to Terminal',
        shortcut: '1',
        keywords: ['home', 'terminal', 'trading'],
        group: 'Go to',
        action: () => run(() => navigate('/')),
      },
      {
        id: 'nav-journal',
        label: 'Go to Journal',
        shortcut: 'J',
        keywords: ['journal', 'logs', 'audit'],
        group: 'Go to',
        action: () => run(() => navigate('/journal')),
      },
      {
        id: 'nav-admin',
        label: 'Go to Admin Keys',
        shortcut: 'A',
        keywords: ['admin', 'keys', 'api'],
        group: 'Go to',
        action: () => run(() => navigate('/admin/keys')),
      },
      {
        id: 'nav-health',
        label: 'Go to Health',
        keywords: ['health', 'status'],
        group: 'Go to',
        action: () => run(() => navigate('/health')),
      },
      {
        id: 'nav-streams',
        label: 'Go to Streams',
        keywords: ['streams', 'sse', 'realtime'],
        group: 'Go to',
        action: () => run(() => navigate('/streams')),
      },
      ...WORKSPACES.map((ws) => ({
        id: `workspace-${ws.id}`,
        label: ws.label,
        shortcut: ws.number,
        keywords: [ws.id, ws.label, 'workspace'],
        group: 'Workspace',
        action: () => run(() => setWorkspace(ws.id)),
      })),
      {
        id: 'symbol-xauusd',
        label: 'Select symbol XAUUSD',
        keywords: ['xauusd', 'gold', 'symbol'],
        group: 'Symbol',
        action: () => run(() => {}),
      },
      {
        id: 'kill-switch',
        label: killSwitchActive ? 'Deactivate kill switch' : 'Activate kill switch',
        keywords: ['kill', 'switch', 'emergency', 'stop'],
        group: 'Action',
        action: () => run(() => setKillSwitch(!killSwitchActive)),
      },
      {
        id: 'reset-workspace',
        label: 'Reset workspace to Trading',
        keywords: ['reset', 'workspace', 'trading'],
        group: 'Action',
        action: () => run(() => setWorkspace('trading')),
      },
    ];
    return list;
  }, [navigate, run, setKillSwitch, setWorkspace, killSwitchActive]);

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (item) =>
        item.label.toLowerCase().includes(q) ||
        item.keywords.some((kw) => kw.toLowerCase().includes(q)) ||
        item.group.toLowerCase().includes(q),
    );
  }, [items, query]);

  React.useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  React.useEffect(() => {
    if (open) {
      const timer = setTimeout(() => inputRef.current?.focus(), 0);
      return () => clearTimeout(timer);
    }
  }, [open]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (filtered.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((i) => (i + 1) % filtered.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((i) => (i - 1 + filtered.length) % filtered.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      filtered[activeIndex]?.action();
    }
  };

  const grouped = React.useMemo(() => {
    const map = new Map<string, CommandItem[]>();
    for (const item of filtered) {
      const arr = map.get(item.group) ?? [];
      arr.push(item);
      map.set(item.group, arr);
    }
    return map;
  }, [filtered]);

  let globalIndex = 0;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent
        className="max-w-xl p-0"
        onKeyDown={handleKeyDown}
        aria-label="Command palette"
      >
        <DialogHeader className="sr-only">
          <DialogTitle>Command palette</DialogTitle>
        </DialogHeader>
        <div className="border-b border-border-subtle p-3">
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Type a command or search..."
            className="w-full bg-transparent text-sm text-text-primary placeholder:text-text-tertiary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            aria-label="Command palette search"
          />
        </div>
        <div className="max-h-[60vh] overflow-y-auto p-2">
          {filtered.length === 0 ? (
            <div className="px-3 py-6 text-center text-xs text-text-secondary">
              No commands found.
            </div>
          ) : (
            Array.from(grouped.entries()).map(([group, groupItems]) => (
              <div key={group} role="group" aria-label={group}>
                <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-text-tertiary">
                  {group}
                </div>
                <ul role="listbox" aria-label={group}>
                  {groupItems.map((item) => {
                    const index = globalIndex++;
                    const isActive = index === activeIndex;
                    return (
                      <li key={item.id} role="option" aria-selected={isActive}>
                        <button
                          type="button"
                          onClick={item.action}
                          className={cn(
                            'flex w-full items-center justify-between rounded-chip px-3 py-2 text-left text-sm',
                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
                            isActive
                              ? 'bg-accent/10 text-text-primary'
                              : 'text-text-secondary hover:bg-bg-raised hover:text-text-primary',
                          )}
                          onMouseEnter={() => setActiveIndex(index)}
                        >
                          <span>{item.label}</span>
                          {item.shortcut && (
                            <kbd className="rounded bg-bg-overlay px-1.5 py-0.5 text-[10px] text-text-tertiary">
                              {item.shortcut}
                            </kbd>
                          )}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
