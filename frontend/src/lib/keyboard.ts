export type WorkspaceShortcut =
  'workspace:trading' | 'workspace:research' | 'workspace:risk' | 'workspace:ops';

export type NavigationShortcut = 'nav:terminal' | 'nav:journal' | 'nav:admin-keys';

export type ActionShortcut = 'command-palette:toggle';

export type Shortcut = WorkspaceShortcut | NavigationShortcut | ActionShortcut;

export interface ShortcutDef {
  key: string;
  mod?: boolean;
  alt?: boolean;
  shift?: boolean;
}

export const SHORTCUTS: Record<Shortcut, ShortcutDef> = {
  'command-palette:toggle': { key: 'k', mod: true },
  'workspace:trading': { key: '1', mod: true },
  'workspace:research': { key: '2', mod: true },
  'workspace:risk': { key: '3', mod: true },
  'workspace:ops': { key: '4', mod: true },
  'nav:terminal': { key: '1', mod: true },
  'nav:journal': { key: 'j', mod: true },
  'nav:admin-keys': { key: 'a', mod: true },
};

export function isModActive(event: KeyboardEvent): boolean {
  const isMac = navigator.platform.toLowerCase().includes('mac');
  return isMac ? event.metaKey : event.ctrlKey;
}

export function isTypingTarget(event: KeyboardEvent): boolean {
  const target = event.target as HTMLElement | null;
  if (!target) return false;
  return target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || !!target.isContentEditable;
}

export function matchShortcut(event: KeyboardEvent, shortcut: ShortcutDef): boolean {
  if (event.key.toLowerCase() !== shortcut.key.toLowerCase()) return false;
  if (shortcut.mod && !isModActive(event)) return false;
  if (shortcut.alt && !event.altKey) return false;
  if (shortcut.shift && !event.shiftKey) return false;
  return true;
}

export function resolveShortcut(event: KeyboardEvent): Shortcut | null {
  const isCommandPalette = matchShortcut(event, SHORTCUTS['command-palette:toggle']);
  if (!isCommandPalette && isTypingTarget(event)) return null;

  for (const [name, def] of Object.entries(SHORTCUTS)) {
    if (matchShortcut(event, def)) {
      return name as Shortcut;
    }
  }
  return null;
}
