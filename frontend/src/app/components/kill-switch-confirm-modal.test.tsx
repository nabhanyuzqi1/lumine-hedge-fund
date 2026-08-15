import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { useUiStore } from "@/stores/uiStore";
import { KillSwitchConfirmModal } from "./kill-switch-confirm-modal";

function renderModal() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <KillSwitchConfirmModal open onOpenChange={() => {}} />
      </ToastProvider>
    </QueryClientProvider>
  );
}

describe("KillSwitchConfirmModal", () => {
  beforeEach(() => {
    // Mock the live backend: POST /api/v1/admin/kill-switch resolves with
    // the server-confirmed status (envelope), which useKillSwitch maps into
    // the ui store.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
        const body = init?.body ? JSON.parse(String(init.body)) : {};
        return Promise.resolve(
          new Response(
            JSON.stringify({
              data: {
                armed: body.armed === true,
                reason: body.reason ?? null,
                tier: body.tier ?? "global",
                updated_at: new Date().toISOString(),
              },
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        );
      })
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    useUiStore.setState({ killSwitchActive: false });
  });

  it("requires two-step confirmation before engaging", async () => {
    const user = userEvent.setup();
    useUiStore.setState({ killSwitchActive: false });
    renderModal();

    // Step 1: tier selector + reason.
    expect(screen.getByTestId("kill-switch-tier-global")).toBeDefined();
    await user.click(screen.getByTestId("kill-switch-tier-strategy"));
    await user.type(screen.getByTestId("kill-switch-reason"), "news shock");
    await user.click(screen.getByTestId("kill-switch-continue"));

    // Step 2: phrase must match before the engage button unlocks.
    const engage = screen.getByTestId("kill-switch-engage") as HTMLButtonElement;
    expect(engage.disabled).toBe(true);
    await user.type(screen.getByTestId("kill-switch-phrase-input"), "KILL");
    expect(engage.disabled).toBe(false);

    await user.click(engage);
    await waitFor(() => expect(useUiStore.getState().killSwitchActive).toBe(true));
  });

  it("does not engage when the confirmation phrase does not match", async () => {
    const user = userEvent.setup();
    useUiStore.setState({ killSwitchActive: false });
    renderModal();

    await user.click(screen.getByTestId("kill-switch-continue"));
    await user.type(screen.getByTestId("kill-switch-phrase-input"), "stop");

    const engage = screen.getByTestId("kill-switch-engage") as HTMLButtonElement;
    expect(engage.disabled).toBe(true);
    expect(useUiStore.getState().killSwitchActive).toBe(false);
  });

  it("releases an active switch with a single confirm step", async () => {
    const user = userEvent.setup();
    useUiStore.setState({ killSwitchActive: true });
    renderModal();

    expect(screen.getByTestId("kill-switch-release")).toBeDefined();
    await user.click(screen.getByTestId("kill-switch-release"));
    await waitFor(() => expect(useUiStore.getState().killSwitchActive).toBe(false));
  });
});
