import * as React from "react";

import { type KillSwitchTier, useKillSwitch } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { useUiStore } from "@/stores/uiStore";

const TIERS: { id: KillSwitchTier; label: string; description: string }[] = [
  { id: "global", label: "Global", description: "Halt all strategies, all books, all accounts" },
  { id: "book", label: "Book", description: "Halt a single trading book" },
  { id: "strategy", label: "Strategy", description: "Halt a single strategy" },
];

const CONFIRM_PHRASE = "KILL";

interface KillSwitchConfirmModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * W1/F-5 kill-switch confirmation. Two-step UX for activation: pick a tier
 * (global/book/strategy) and reason, then type `KILL` to engage. Releasing an
 * active switch is a single-step confirm. Fixture-backed mutation until the
 * Phase 9 backend implements POST /api/rpc/kill-switch.
 */
export function KillSwitchConfirmModal({ open, onOpenChange }: KillSwitchConfirmModalProps) {
  const killSwitchActive = useUiStore((s) => s.killSwitchActive);
  const killSwitch = useKillSwitch();
  const { toast } = useToast();

  const [step, setStep] = React.useState<"details" | "confirm">("details");
  const [tier, setTier] = React.useState<KillSwitchTier>("global");
  const [reason, setReason] = React.useState("");
  const [confirmText, setConfirmText] = React.useState("");

  React.useEffect(() => {
    if (open) {
      setTier("global");
      setReason("");
      setConfirmText("");
      setStep(killSwitchActive ? "confirm" : "details");
    }
  }, [open, killSwitchActive]);

  const phraseMatches = confirmText.trim().toUpperCase() === CONFIRM_PHRASE;

  const handleEngage = async () => {
    try {
      await killSwitch.mutateAsync({ active: true, tier, reason: reason.trim() || undefined });
      onOpenChange(false);
      toast({
        variant: "danger",
        title: "Kill switch engaged",
        description: `${tier} tier · trading halted (server-confirmed).`,
      });
    } catch {
      toast({
        variant: "danger",
        title: "Kill switch failed",
        description: "Backend rejected the engage request — check API connectivity.",
      });
    }
  };

  const handleRelease = async () => {
    try {
      await killSwitch.mutateAsync({
        active: false,
        tier: "global",
        reason: reason.trim() || undefined,
      });
      onOpenChange(false);
      toast({
        variant: "success",
        title: "Kill switch released",
        description: "Trading resumed (server-confirmed).",
      });
    } catch {
      toast({
        variant: "danger",
        title: "Release failed",
        description: "Backend rejected the release request — check API connectivity.",
      });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="kill-switch-confirm-modal">
        <DialogHeader>
          <DialogTitle>
            {killSwitchActive ? "Release kill switch?" : "Engage kill switch"}
          </DialogTitle>
          <DialogDescription>
            {killSwitchActive
              ? "This resumes order execution. Confirm to release the halt."
              : "Immediately halts new orders and cancels pending risk. This is an auditable action."}
          </DialogDescription>
        </DialogHeader>

        {killSwitchActive ? (
          <div className="my-2 space-y-3">
            <label className="block space-y-1">
              <span className="text-[11px] font-medium uppercase tracking-wider text-text-secondary">
                Reason (audit trail)
              </span>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={2}
                placeholder="Optional context for the release"
                className="w-full resize-none rounded-chip border border-border-subtle bg-bg-base p-2 text-xs text-text-primary placeholder:text-text-tertiary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                data-testid="kill-switch-reason"
              />
            </label>
          </div>
        ) : step === "details" ? (
          <div className="my-2 space-y-4">
            <div className="space-y-1">
              <span className="text-[11px] font-medium uppercase tracking-wider text-text-secondary">
                Scope
              </span>
              {TIERS.map((t) => (
                <label
                  key={t.id}
                  className="flex cursor-pointer items-start gap-2 rounded-chip border border-border-subtle bg-bg-base p-2 text-xs text-text-primary has-[:checked]:border-danger/50"
                >
                  <input
                    type="radio"
                    name="kill-switch-tier"
                    value={t.id}
                    checked={tier === t.id}
                    onChange={() => setTier(t.id)}
                    className="mt-0.5"
                    data-testid={`kill-switch-tier-${t.id}`}
                  />
                  <span>
                    <span className="block font-medium">{t.label}</span>
                    <span className="block text-[11px] text-text-secondary">{t.description}</span>
                  </span>
                </label>
              ))}
            </div>
            <label className="block space-y-1">
              <span className="text-[11px] font-medium uppercase tracking-wider text-text-secondary">
                Reason (audit trail)
              </span>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={2}
                placeholder="e.g. news shock, API anomaly, manual override"
                className="w-full resize-none rounded-chip border border-border-subtle bg-bg-base p-2 text-xs text-text-primary placeholder:text-text-tertiary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                data-testid="kill-switch-reason"
              />
            </label>
          </div>
        ) : (
          <div className="my-2 space-y-3">
            <p className="text-xs text-text-secondary">
              Engage <span className="font-mono font-medium text-text-primary">{tier}</span> kill
              switch
              {reason.trim() ? ` — "${reason.trim()}"` : ""}. Type{" "}
              <span className="font-mono text-danger">KILL</span> to confirm.
            </p>
            <input
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder={`Type ${CONFIRM_PHRASE} to confirm`}
              className="w-full rounded-chip border border-border-subtle bg-bg-base p-2 font-mono text-xs text-text-primary placeholder:text-text-tertiary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              data-testid="kill-switch-phrase-input"
            />
          </div>
        )}

        <DialogFooter>
          <Button variant="secondary" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          {killSwitchActive ? (
            <Button
              variant="primary"
              size="sm"
              onClick={handleRelease}
              disabled={killSwitch.isPending}
              data-testid="kill-switch-release"
            >
              Release switch
            </Button>
          ) : step === "details" ? (
            <Button
              variant="danger"
              size="sm"
              onClick={() => setStep("confirm")}
              data-testid="kill-switch-continue"
            >
              Continue
            </Button>
          ) : (
            <>
              <Button variant="secondary" size="sm" onClick={() => setStep("details")}>
                Back
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={handleEngage}
                disabled={!phraseMatches || killSwitch.isPending}
                data-testid="kill-switch-engage"
              >
                Engage switch
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
