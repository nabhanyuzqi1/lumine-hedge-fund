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
import { useTranslation } from "react-i18next";

const TIERS: { id: KillSwitchTier; labelKey: string; descriptionKey: string }[] = [
  { id: "global", labelKey: "killSwitch.tierGlobal", descriptionKey: "killSwitch.tierGlobalDesc" },
  { id: "book", labelKey: "killSwitch.tierBook", descriptionKey: "killSwitch.tierBookDesc" },
  { id: "strategy", labelKey: "killSwitch.tierStrategy", descriptionKey: "killSwitch.tierStrategyDesc" },
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
  const { t } = useTranslation();
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
              title: t("killSwitch.engagedToast"),
              description: `${tier} tier · ${t("killSwitch.engagedToastDesc")}`,
            });
          } catch {
            toast({
              variant: "danger",
              title: t("killSwitch.failedToast"),
              description: t("killSwitch.engageFailedDesc"),
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
              title: t("killSwitch.releasedToast"),
              description: t("killSwitch.releasedToastDesc"),
            });
          } catch {
            toast({
              variant: "danger",
              title: t("killSwitch.releaseFailedToast"),
              description: t("killSwitch.releaseFailedDesc"),
            });
          }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="kill-switch-confirm-modal">
        <DialogHeader>
          <DialogTitle>
                      {killSwitchActive ? t("killSwitch.releaseTitle") : t("killSwitch.engageTitle")}
                    </DialogTitle>
                    <DialogDescription>
                      {killSwitchActive
                        ? t("killSwitch.releaseDescription")
                        : t("killSwitch.engageDescription")}
                    </DialogDescription>
        </DialogHeader>

        {killSwitchActive ? (
          <div className="my-2 space-y-3">
            <label className="block space-y-1">
              <span className="text-[11px] font-medium uppercase tracking-wider text-text-secondary">
                              {t("killSwitch.reasonLabel")}
                            </span>
                            <textarea
                              value={reason}
                              onChange={(e) => setReason(e.target.value)}
                              rows={2}
                              placeholder={t("killSwitch.reasonPlaceholder")}
                className="w-full resize-none rounded-chip border border-border-subtle bg-bg-base p-2 text-xs text-text-primary placeholder:text-text-tertiary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                data-testid="kill-switch-reason"
              />
            </label>
          </div>
        ) : step === "details" ? (
          <div className="my-2 space-y-4">
            <div className="space-y-1">
              <span className="text-[11px] font-medium uppercase tracking-wider text-text-secondary">
                              {t("killSwitch.scopeLabel")}
                            </span>
                            {TIERS.map((tierOpt) => (
                              <label
                                key={tierOpt.id}
                                className="flex cursor-pointer items-start gap-2 rounded-chip border border-border-subtle bg-bg-base p-2 text-xs text-text-primary has-[:checked]:border-danger/50"
                              >
                                <input
                                  type="radio"
                                  name="kill-switch-tier"
                                  value={tierOpt.id}
                                  checked={tier === tierOpt.id}
                                  onChange={() => setTier(tierOpt.id)}
                                  className="mt-0.5"
                                  data-testid={`kill-switch-tier-${tierOpt.id}`}
                                />
                                <span>
                                  <span className="block font-medium">{t(tierOpt.labelKey)}</span>
                                  <span className="block text-[11px] text-text-secondary">{t(tierOpt.descriptionKey)}</span>
                                </span>
                              </label>
                            ))}
                          </div>
                          <label className="block space-y-1">
                            <span className="text-[11px] font-medium uppercase tracking-wider text-text-secondary">
                              {t("killSwitch.reasonLabel")}
                            </span>
                            <textarea
                              value={reason}
                              onChange={(e) => setReason(e.target.value)}
                              rows={2}
                              placeholder={t("killSwitch.reasonDetailPlaceholder")}
                className="w-full resize-none rounded-chip border border-border-subtle bg-bg-base p-2 text-xs text-text-primary placeholder:text-text-tertiary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                data-testid="kill-switch-reason"
              />
            </label>
          </div>
        ) : (
          <div className="my-2 space-y-3">
            <p className="text-xs text-text-secondary">
                          {t("killSwitch.engageConfirmText")}{" "}
                          <span className="font-mono font-medium text-text-primary">{tier}</span>{" "}
                          {t("killSwitch.engageConfirmSuffix")}
                          {reason.trim() ? ` — "${reason.trim()}"` : ""}. Ketik{" "}
                          <span className="font-mono text-danger">KILL</span> untuk konfirmasi.
                        </p>
                        <input
                          value={confirmText}
                          onChange={(e) => setConfirmText(e.target.value)}
                          placeholder={t("killSwitch.typeConfirmPlaceholder")}
              className="w-full rounded-chip border border-border-subtle bg-bg-base p-2 font-mono text-xs text-text-primary placeholder:text-text-tertiary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              data-testid="kill-switch-phrase-input"
            />
          </div>
        )}

        <DialogFooter>
                  <Button variant="secondary" size="sm" onClick={() => onOpenChange(false)}>
                    {t("common.cancel")}
                  </Button>
                  {killSwitchActive ? (
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={handleRelease}
                      disabled={killSwitch.isPending}
                      data-testid="kill-switch-release"
                    >
                      {t("killSwitch.releaseSwitch")}
                    </Button>
                  ) : step === "details" ? (
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => setStep("confirm")}
                      data-testid="kill-switch-continue"
                    >
                      {t("common.continue")}
                    </Button>
                  ) : (
                    <>
                      <Button variant="secondary" size="sm" onClick={() => setStep("details")}>
                        {t("common.back")}
                      </Button>
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={handleEngage}
                        disabled={!phraseMatches || killSwitch.isPending}
                        data-testid="kill-switch-engage"
                      >
                {t("killSwitch.engageTitle")}
                              </Button>
                            </>
                          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
