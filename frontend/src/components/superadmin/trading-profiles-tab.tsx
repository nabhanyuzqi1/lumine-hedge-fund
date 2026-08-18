import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { get, post, put } from "@/api/client";

/**
 * TradingProfilesTab (18 Aug 2026) — user request: profile custom
 * scalping 1m/5m, intraday 15m/1h, swing 4h/1d + transisi. Semua auto
 * SL/TP/BE + entry/exit otomatis. Per-agent prompt override (prompt bisa
 * diatur sendiri). Simpan → Redis realtime, TANPA restart container.
 */

export interface TradingProfile {
  id: string;
  name: string;
  description: string;
  timeframe: string;
  risk_per_trade: number;
  max_exposure: number;
  sl_atr_mult: number;
  tp_atr_mult: number;
  be_after_r: number;
  trail_after_r: number;
  max_positions: number;
  min_confidence: number;
  agent_overrides: Record<string, string>;
  active?: boolean;
}

const AGENTS = ["technical_analyst", "macro_analyst", "news_analyst", "smc_analyst"];

const AGENT_LABEL: Record<string, string> = {
  technical_analyst: "Technical",
  macro_analyst: "Macro",
  news_analyst: "News",
  smc_analyst: "SMC",
};

const FIELD_LABEL: Record<string, string> = {
  risk_per_trade: "Risk per trade",
  max_exposure: "Max exposure",
  sl_atr_mult: "SL (xATR)",
  tp_atr_mult: "TP (xATR)",
  be_after_r: "BE after (R)",
  trail_after_r: "Trail after (R)",
  max_positions: "Max positions",
  min_confidence: "Min confidence",
};

export function TradingProfilesTab() {
  const qc = useQueryClient();
  const { data: profiles = [], isLoading } = useQuery({
    queryKey: ["profiles"],
    queryFn: () => get<TradingProfile[]>("/admin/profiles"),
    staleTime: 15_000,
  });

  const setActive = useMutation({
    mutationFn: (profileId: string) =>
      post("/admin/profiles/active", { profile_id: profileId }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });

  const saveProfile = useMutation({
    mutationFn: (p: TradingProfile) =>
      put(`/admin/profiles/${p.id}`, p),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });

  const [editing, setEditing] = React.useState<TradingProfile | null>(null);

  return (
    <div className="space-y-4">
      <div className="rounded-panel border border-line bg-bg px-3 py-2">
        <p className="text-xs leading-relaxed text-ink-faint">
          <span className="font-medium text-ink">Trading Profiles</span> —
          pilih gaya trading (scalping/intraday/swing/transisi). Profil aktif
          dibaca worker <span className="font-mono">setiap decision cycle</span>{" "}
          dari Redis — simpan langsung berlaku <span className="text-ink">tanpa
          restart container</span>. Prompt per-agent bisa di-override bebas;
          output tetap mengikuti template sistem Lumine (schema JSON).
        </p>
      </div>

      {isLoading ? (
        <p className="text-xs text-ink-faint">loading profiles…</p>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {profiles.map((p) => (
            <div
              key={p.id}
              className={
                "rounded-panel border px-3 py-2.5 " +
                (p.active ? "border-accent bg-accent/5" : "border-line bg-bg")
              }
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="flex items-center gap-2 text-sm font-semibold text-ink">
                    {p.name}
                    {p.active && (
                      <span className="rounded bg-accent/20 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-accent">
                        aktif
                      </span>
                    )}
                  </p>
                  <p className="mt-0.5 line-clamp-2 text-[11px] text-ink-faint">
                    {p.description}
                  </p>
                </div>
                <span className="shrink-0 rounded bg-bg-raised px-1.5 py-0.5 font-mono text-[10px] text-ink-dim">
                  {p.timeframe}
                </span>
              </div>

              <div className="mt-2 flex flex-wrap gap-1.5">
                {(["timeframe", "sl_atr_mult", "tp_atr_mult", "be_after_r", "min_confidence"] as const).map(
                  (k) => (
                    <span
                      key={k}
                      className="rounded bg-bg-raised px-1.5 py-0.5 font-mono text-[9px] text-ink-dim"
                    >
                      {k}: <span className="text-ink">{p[k]}</span>
                    </span>
                  )
                )}
              </div>

              {p.agent_overrides && Object.keys(p.agent_overrides).length > 0 && (
                <div className="mt-2 space-y-0.5">
                  {Object.entries(p.agent_overrides).map(([agent, txt]) => (
                    <p key={agent} className="truncate text-[10px] text-ink-faint">
                      <span className="font-mono text-ink-dim">
                        {AGENT_LABEL[agent] ?? agent}:
                      </span>{" "}
                      {txt}
                    </p>
                  ))}
                </div>
              )}

              <div className="mt-2.5 flex gap-2">
                {!p.active && (
                  <button
                    type="button"
                    onClick={() => setActive.mutate(p.id)}
                    className="rounded bg-accent px-2 py-1 text-[11px] font-medium text-bg"
                  >
                    Aktifkan
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setEditing(p)}
                  className="rounded border border-line px-2 py-1 text-[11px] text-ink-dim hover:text-ink"
                >
                  Edit
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {editing && (
        <ProfileEditor
          profile={editing}
          onClose={() => setEditing(null)}
          onSave={async (p) => {
            await saveProfile.mutateAsync(p);
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}

function ProfileEditor({
  profile,
  onClose,
  onSave,
}: {
  profile: TradingProfile;
  onClose: () => void;
  onSave: (p: TradingProfile) => Promise<void>;
}) {
  const [draft, setDraft] = React.useState<TradingProfile>({
    ...profile,
    agent_overrides: { ...(profile.agent_overrides ?? {}) },
  });
  const set = <K extends keyof TradingProfile>(k: K, v: TradingProfile[K]) =>
    setDraft((d) => ({ ...d, [k]: v }));

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4">
      <div className="mt-8 w-full max-w-2xl rounded-panel border border-line bg-bg-raised p-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-ink">
            Edit Profile — {profile.name}
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-line px-2 py-1 text-xs text-ink-dim"
          >
            Tutup
          </button>
        </div>

        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <label className="block text-xs text-ink-dim">
            Nama
            <input
              className="mt-1 w-full rounded border border-line bg-bg px-2 py-1.5 text-sm text-ink"
              value={draft.name}
              onChange={(e) => set("name", e.target.value)}
            />
          </label>
          <label className="block text-xs text-ink-dim">
            Timeframe
            <select
              className="mt-1 w-full rounded border border-line bg-bg px-2 py-1.5 text-sm text-ink"
              value={draft.timeframe}
              onChange={(e) => set("timeframe", e.target.value)}
            >
              {["1m", "5m", "15m", "1h", "4h", "1d"].map((tf) => (
                <option key={tf} value={tf}>
                  {tf}
                </option>
              ))}
            </select>
          </label>
        </div>

        <label className="mt-3 block text-xs text-ink-dim">
          Deskripsi
          <textarea
            className="mt-1 w-full rounded border border-line bg-bg px-2 py-1.5 text-sm text-ink"
            rows={2}
            value={draft.description}
            onChange={(e) => set("description", e.target.value)}
          />
        </label>

        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          {(Object.keys(FIELD_LABEL) as (keyof TradingProfile)[]).map((k) => (
            <label key={k} className="block text-xs text-ink-dim">
              {FIELD_LABEL[k]}
              <input
                type="number"
                step="0.01"
                className="mt-1 w-full rounded border border-line bg-bg px-2 py-1.5 font-mono text-sm text-ink"
                value={String(draft[k] ?? "")}
                onChange={(e) => set(k, Number(e.target.value) as never)}
              />
            </label>
          ))}
        </div>

        <div className="mt-4">
          <p className="text-xs font-medium text-ink">
            Agent Prompt Override (khusus profil ini)
          </p>
          <p className="mt-0.5 text-[10px] text-ink-faint">
            Prompt custom per analyst — di-inject ke stage sebagai{" "}
            <span className="font-mono">profile_override</span>. Output tetap
            mengikuti schema Lumine (JSON template sistem).
          </p>
          <div className="mt-2 space-y-2">
            {AGENTS.map((agent) => (
              <label key={agent} className="block text-xs text-ink-dim">
                {AGENT_LABEL[agent] ?? agent}
                <textarea
                  className="mt-1 w-full rounded border border-line bg-bg px-2 py-1.5 text-[11px] text-ink"
                  rows={2}
                  placeholder="Kosongkan = pakai prompt default Lumine"
                  value={draft.agent_overrides?.[agent] ?? ""}
                  onChange={(e) =>
                    setDraft((d) => ({
                      ...d,
                      agent_overrides: { ...d.agent_overrides, [agent]: e.target.value },
                    }))
                  }
                />
              </label>
            ))}
          </div>
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-line px-3 py-1.5 text-xs text-ink-dim"
          >
            Batal
          </button>
          <button
            type="button"
            onClick={() => void onSave(draft)}
            className="rounded bg-accent px-3 py-1.5 text-xs font-medium text-bg"
          >
            Simpan (realtime, tanpa restart)
          </button>
        </div>
      </div>
    </div>
  );
}