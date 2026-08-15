import { useEffect, useState } from "react";

/**
 * Network ping live client — ukur latensi ke backend (GET /health)
 * tiap 10s + jitter. Data REAL (bukan demo): dipakai header TopBar
 * "NET x ms" + status koneksi pengunjung web.
 */
export interface NetworkPing {
  latencyMs: number | null;
  jitterMs: number | null;
  lastPingAt: string | null;
  ok: boolean;
}

export function useNetworkPing(intervalMs = 10_000): NetworkPing {
  const [state, setState] = useState<NetworkPing>({
    latencyMs: null,
    jitterMs: null,
    lastPingAt: null,
    ok: false,
  });

  useEffect(() => {
    let active = true;
    let lastLatency: number | null = null;

    const ping = async () => {
      const started = performance.now();
      try {
        // Same-origin /health (Caddy) — probe infra, tanpa HMAC.
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 5_000);
        const res = await fetch("/health", { signal: controller.signal, cache: "no-store" });
        clearTimeout(timer);
        const latency = Math.round(performance.now() - started);
        const jitter =
          lastLatency != null ? Math.abs(latency - lastLatency) : null;
        lastLatency = latency;
        if (active) {
          setState({
            latencyMs: latency,
            jitterMs: jitter,
            lastPingAt: new Date().toISOString(),
            ok: res.ok,
          });
        }
      } catch {
        if (active) {
          setState((prev) => ({
            ...prev,
            ok: false,
            lastPingAt: new Date().toISOString(),
          }));
        }
      }
    };

    void ping();
    const id = setInterval(() => void ping(), intervalMs);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [intervalMs]);

  return state;
}
