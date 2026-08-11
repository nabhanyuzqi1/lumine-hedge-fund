import { useUiStore } from '@/stores/uiStore';

export function KillSwitchBanner() {
  const killSwitchActive = useUiStore((s) => s.killSwitchActive);

  if (!killSwitchActive) return null;

  return (
    <div
      className="flex items-center justify-center gap-2 border-b border-danger bg-danger/10 px-3 py-1 text-xs text-danger"
      data-testid="kill-switch-banner"
    >
      <span className="h-2 w-2 rounded-full bg-danger" aria-hidden="true" />
      <span className="font-semibold">Kill switch active</span>
      <span className="text-text-secondary">Writes are disabled across the platform.</span>
    </div>
  );
}
