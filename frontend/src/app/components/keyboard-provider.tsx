import * as React from 'react';
import { useNavigate } from 'react-router-dom';

import { resolveShortcut } from '@/lib/keyboard';
import { useUiStore } from '@/stores/uiStore';

export function KeyboardProvider({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const setWorkspace = useUiStore((s) => s.setWorkspace);
  const setCommandPaletteOpen = useUiStore((s) => s.setCommandPaletteOpen);

  React.useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const shortcut = resolveShortcut(event);
      if (!shortcut) return;

      event.preventDefault();

      switch (shortcut) {
        case 'command-palette:toggle':
          setCommandPaletteOpen(true);
          break;
        case 'workspace:trading':
          setWorkspace('trading');
          break;
        case 'workspace:research':
          setWorkspace('research');
          break;
        case 'workspace:risk':
          setWorkspace('risk');
          break;
        case 'workspace:ops':
          setWorkspace('ops');
          break;
        case 'nav:journal':
          navigate('/journal');
          break;
        case 'nav:admin-keys':
          navigate('/admin/keys');
          break;
        default:
          break;
      }
    };

    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [navigate, setCommandPaletteOpen, setWorkspace]);

  return <>{children}</>;
}
