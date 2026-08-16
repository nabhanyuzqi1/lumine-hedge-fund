import * as React from "react";

import { useApiKeys, useCreateApiKey, useRevokeApiKey } from "@/api/hooks";
import { get, put } from "@/api/client";
import { ApiKeyTable } from "@/components/admin/api-key-table";
import { CreateKeyModal } from "@/components/admin/create-key-modal";
import { LLMRoutingTab } from "@/components/superadmin/llm-routing-tab";
import { BacktestTab } from "@/components/superadmin/backtest-tab";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

// ── Types (backend: backend/src/lumine/api/routers/admin.py) ────────────────

interface ServiceStatus {
  name: string;
  status: string;
  health: string | null;
  image: string | null;
  uptime: string | null;
}

interface SystemInfo {
  services: ServiceStatus[];
  llm_gateway_url: string;
  llm_gateway_configured: boolean;
  demo_data: boolean;
  paper_trading: boolean;
  environment: string;
  version: string;
  enabled_symbols: string[];
}

interface ConfigForm {
  llm_gateway_api_key: string;
  llm_gateway_url: string;
  llm_default_model: string;
  llm_fallback_models: string;
  llm_auto_fallback: boolean;
  llm_daily_budget_usd: string;
  max_exposure_per_trade: string;
  risk_per_trade: string;
  max_daily_loss_pct: string;
  demo_data: boolean;
  paper_trading: boolean;
}

// B9: kandidat symbol untuk enable/disable (multicurrency). Default fokus
// XAUUSD — matangkan 1 stream dulu sebelum multi-stream.
const SYMBOL_CANDIDATES = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USOIL", "BTCUSD"];

// ── Tabs ──────────────────────────────────────────────────────────────────────

type Tab = "overview" | "services" | "config" | "keys" | "mt5" | "logs" | "llm" | "autogen" | "backtest";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "services", label: "Services" },
  { id: "config", label: "System Config" },
  { id: "keys", label: "API Keys" },
  { id: "llm", label: "LLM Routing" },
  { id: "mt5", label: "MT5 Desktop" },
  { id: "logs", label: "Logs" },
  { id: "autogen", label: "AutoGen Studio" },
  { id: "backtest", label: "Backtest" },
];

// ── Hooks (real backend calls — no demo fallback) ───────────────────────────

function useSystemInfo() {
  return useQuery({
    queryKey: ["system-info"],
    queryFn: () => get<SystemInfo>("/admin/system-info"),
    staleTime: 30_000,
  });
}

interface EAStatus {
  ea_version: string;
  ea_build: string;
  seed_phase: string;
  seed_done: string;
  last_tick_ts: string | null;
  ticks_sent: string;
  ticks_pending: number;
  proxy_url: string;
  connected: boolean;
  logs: string[];
  error?: string;
}

function useEAStatus() {
  return useQuery({
    queryKey: ["ea-status"],
    queryFn: () => get<EAStatus>("/admin/ea-status"),
    staleTime: 0,
    refetchInterval: 5_000,
    retry: 1,
  });
}

function EAStatusCard() {
  const { data, isLoading, isError } = useEAStatus();
  if (isLoading) return <div className="h-8 animate-pulse rounded bg-raised" />;
  if (isError || !data) return <p className="text-xs text-danger">EA status unavailable</p>;
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Badge tone={data.connected ? "ok" : "warn"} label={data.connected ? "Connected" : "No Status"} />
        {data.ea_version !== "unknown" && (
          <span className="font-mono text-xs text-ink-dim">v{data.ea_version}</span>
        )}
        {data.ea_build !== "unknown" && (
          <span className="font-mono text-xs text-ink-faint">build {data.ea_build}</span>
        )}
      </div>
      <div className="grid grid-cols-2 gap-1 text-[11px]">
        <span className="text-ink-faint">Seed Phase</span>
        <span className="font-mono text-ink">{data.seed_phase || "—"}</span>
        <span className="text-ink-faint">Seed Done</span>
        <span className="font-mono text-ink">{data.seed_done === "1" ? "✅ Yes" : "⏳ No"}</span>
        <span className="text-ink-faint">Ticks Sent</span>
        <span className="font-mono text-ink">{data.ticks_sent}</span>
        <span className="text-ink-faint">Ticks Pending</span>
        <span className="font-mono text-ink">{data.ticks_pending}</span>
        {data.last_tick_ts && (
          <>
            <span className="text-ink-faint">Last Tick</span>
            <span className="font-mono text-ink text-[10px]">{new Date(Number(data.last_tick_ts) * 1000).toLocaleTimeString()}</span>
          </>
        )}
      </div>
    </div>
  );
}

function EALogsPanel() {
  const { data, isLoading } = useEAStatus();
  return (
    <div className="rounded-panel border border-line bg-bg-raised p-3">
      <h3 className="mb-2 font-mono text-xs font-semibold text-ink">EA Logs (live)</h3>
      {isLoading ? (
        <div className="space-y-1">{[...Array(3)].map((_, i) => <div key={i} className="h-4 animate-pulse rounded bg-raised" />)}</div>
      ) : (data?.logs?.length ?? 0) === 0 ? (
        <p className="text-xs text-ink-faint">No logs in mt5:logs — EA mungkin belum push logs ke Redis</p>
      ) : (
        <ul className="max-h-64 space-y-0.5 overflow-auto overscroll-none font-mono text-[10px] text-ink-dim">
          {(data?.logs ?? []).map((line, i) => (
            <li key={i} className={`whitespace-pre-wrap rounded px-1 py-0.5 ${line.includes("ERROR") || line.includes("failed") ? "bg-danger/10 text-danger" : line.includes("RECOVERED") || line.includes("OK") ? "bg-ok/10 text-ok" : ""}`}>
              {line}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function useUpdateConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Record<string, unknown>) => {
      return await put<{ updated: string[]; note: string }>("/admin/system-config", payload);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin", "system-info"] });
    },
  });
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function HealthBadge({ health, status }: { health: string | null; status: string }) {
  if (status !== "running") return <Badge tone="danger" label="stopped" />;
  if (health === "healthy") return <Badge tone="ok" label="healthy" />;
  if (health === "unhealthy") return <Badge tone="danger" label="unhealthy" />;
  if (health === "starting") return <Badge tone="warn" label="starting" />;
  return <Badge tone="neutral" label="running" />;
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-panel border border-down/30 bg-down/10 px-4 py-3">
      <p className="font-mono text-xs text-down">
        Gagal memuat data dari backend: {message}
      </p>
      <p className="mt-1 text-xs text-ink-faint">
        Pastikan session aktif (login ulang) dan backend API reachable.
      </p>
    </div>
  );
}

function ServicesTab({ data, isError }: { data: SystemInfo | undefined; isError: boolean }) {
  if (isError) return <ErrorBanner message="system-info" />;
  if (!data) return <p className="text-xs text-ink-faint">Loading…</p>;
  const healthy = data.services.filter(
    (s) => s.health === "healthy" || (s.status === "running" && !s.health)
  ).length;
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Badge
          tone={healthy >= data.services.length ? "ok" : "warn"}
          label={`${healthy}/${data.services.length} healthy`}
        />
        <span className="text-xs text-ink-faint">Auto-refresh: 15s</span>
      </div>
      <div className="overflow-x-auto rounded-panel border border-line">
        <table className="w-full text-xs" role="table">
          <thead>
            <tr className="border-b border-line bg-raised text-left text-ink-faint">
              <th className="px-3 py-2 pr-4 font-mono text-[10px] uppercase tracking-widest">Container</th>
              <th className="px-3 py-2 pr-4 font-mono text-[10px] uppercase tracking-widest">Status</th>
              <th className="px-3 py-2 pr-4 font-mono text-[10px] uppercase tracking-widest">Image</th>
              <th className="px-3 py-2 font-mono text-[10px] uppercase tracking-widest">Uptime</th>
            </tr>
          </thead>
          <tbody>
            {data.services.map((svc) => (
              <tr key={svc.name} className="border-b border-line/40 hover:bg-raised">
                <td className="px-3 py-2 pr-4 font-mono">{svc.name}</td>
                <td className="px-3 py-2 pr-4"><HealthBadge health={svc.health} status={svc.status} /></td>
                <td className="px-3 py-2 pr-4 font-mono text-ink-dim">{svc.image}</td>
                <td className="px-3 py-2 text-ink-dim">{svc.uptime}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function OverviewTab({ data, isError }: { data: SystemInfo | undefined; isError: boolean }) {
  if (isError) return <ErrorBanner message="system-info" />;
  if (!data) return <p className="text-xs text-ink-faint">Loading…</p>;
  // B2 fix: hitung konsisten dengan ServicesTab — service running tanpa
  // health (docker tidak expose healthcheck) tetap dianggap healthy.
  const healthy = data.services.filter(
    (s) => s.health === "healthy" || (s.status === "running" && !s.health)
  ).length;
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      <Card>
        <CardHeader><CardTitle>Stack Health</CardTitle></CardHeader>
        <CardContent>
          <p className="text-3xl font-bold tabular-nums text-ink">
            {healthy}<span className="text-lg text-ink-faint">/{data.services.length}</span>
          </p>
          <p className="mt-1 text-xs text-ink-dim">services healthy</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>LLM Gateway</CardTitle></CardHeader>
        <CardContent>
          <Badge
            tone={data.llm_gateway_configured ? "ok" : "warn"}
            label={data.llm_gateway_configured ? "Configured" : "No API Key"}
          />
          <p className="mt-2 font-mono text-xs text-ink-dim">{data.llm_gateway_url}</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Data Mode</CardTitle></CardHeader>
        <CardContent>
          <Badge
            tone={data.demo_data ? "warn" : "ok"}
            label={data.demo_data ? "Demo Data" : "Live DB"}
          />
          <p className="mt-1 text-xs text-ink-dim">
            {data.demo_data ? "Router pakai demo-data in-memory" : "Repository terhubung ke PostgreSQL"}
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Environment</CardTitle></CardHeader>
        <CardContent>
          <Badge tone="neutral" label={data.environment} />
          <p className="mt-1 text-xs text-ink-dim">Version: {data.version}</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>EA Status</CardTitle></CardHeader>
        <CardContent>
          <EAStatusCard />
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Quick Links</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          <a href="/novnc/" target="_blank" rel="noreferrer" className="block text-xs text-accent hover:underline">
            MT5 noVNC Desktop →
          </a>
          <a href="/dozzle/" target="_blank" rel="noreferrer" className="block text-xs text-accent hover:underline">
            Dozzle Log Viewer →
          </a>
          <a href="https://router.lumine.biz.id" target="_blank" rel="noreferrer" className="block text-xs text-accent hover:underline">
            9router Dashboard →
          </a>
        </CardContent>
      </Card>
    </div>
  );
}

function ConfigTab({ data, isError }: { data: SystemInfo | undefined; isError: boolean }) {
  const { toast } = useToast();
  const update = useUpdateConfig();
  // B9: enabled_symbols dari system-info (default XAUUSD).
  const [enabledSymbols, setEnabledSymbols] = React.useState<string[]>(
    data?.enabled_symbols ?? ["XAUUSD"]
  );
  React.useEffect(() => {
    if (data?.enabled_symbols) setEnabledSymbols(data.enabled_symbols);
  }, [data?.enabled_symbols]);
  const [form, setForm] = React.useState<ConfigForm>({
      llm_gateway_api_key: "",
      llm_gateway_url: data?.llm_gateway_url ?? "http://9router:20128",
      llm_default_model: "deepseek-v4",
            llm_fallback_models: "",
            llm_auto_fallback: true,
            llm_daily_budget_usd: "50",
            max_exposure_per_trade: "0.02",
            risk_per_trade: "0.01",
            max_daily_loss_pct: "0.03",
            demo_data: data?.demo_data ?? false,
            paper_trading: data?.paper_trading ?? true,
          });

  if (isError) return <ErrorBanner message="system-info" />;

  const handleSubmit = (e: React.FormEvent) => {
      e.preventDefault();
      const payload: Record<string, unknown> = {
        llm_gateway_api_key: form.llm_gateway_api_key || undefined,
        llm_gateway_url: form.llm_gateway_url,
        demo_data: form.demo_data,
        llm_daily_budget_usd: parseFloat(form.llm_daily_budget_usd),
        llm_default_model: form.llm_default_model,
        max_exposure_per_trade: parseFloat(form.max_exposure_per_trade),
        risk_per_trade: parseFloat(form.risk_per_trade),
        max_daily_loss_pct: parseFloat(form.max_daily_loss_pct),
        // B9: enabled symbols (enable/disable currency)
        enabled_symbols: enabledSymbols,
      };
      // ADR-0042: auto-fallback + chain fallback models (comma-separated).
      payload.llm_auto_fallback = form.llm_auto_fallback;
            payload.llm_fallback_models = form.llm_fallback_models
              .split(",")
              .map((m) => m.trim())
              .filter(Boolean);
            payload.paper_trading = form.paper_trading;
      update.mutate(payload, {
        onSuccess: (result) => {
          toast({ variant: "success", title: "Config saved", description: result.note });
        },
        onError: () => {
          toast({ variant: "danger", title: "Save failed", description: "Periksa session/API key admin." });
        },
      });
    };

  const field = (label: string, key: keyof ConfigForm, type = "text", placeholder = "") => (
    <div>
      <label className="text-[11px] uppercase tracking-wider text-ink-dim">{label}</label>
      <input
        type={type}
        value={String(form[key])}
        onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
        placeholder={placeholder}
        className="mt-1 w-full rounded-chip border border-line bg-bg px-3 py-2 font-mono text-xs text-ink focus:outline-none focus:ring-2 focus:ring-accent"
      />
    </div>
  );

  return (
    <form onSubmit={handleSubmit} className="max-w-2xl space-y-6">
      <div className="space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-faint">LLM Gateway (9router)</h3>
                {field("LLM Gateway URL", "llm_gateway_url")}
                {field("API Key (kosong = tidak diubah)", "llm_gateway_api_key", "password", "sk-...")}
                {field("Default Model", "llm_default_model")}
                {field("Fallback Models (comma-separated, ADR-0042)", "llm_fallback_models", "text", "kimi-k3, qwen-3.7, glm-5.2")}
                <div>
                  <label className="flex items-center gap-2 text-xs text-ink-dim">
                    <input
                      type="checkbox"
                      checked={form.llm_auto_fallback}
                      onChange={(e) => setForm((f) => ({ ...f, llm_auto_fallback: e.target.checked }))}
                      className="accent-accent"
                    />
                    Auto-fallback aktif — otomatis pakai model cadangan saat primary gagal/rate-limited
                  </label>
                </div>
                {field("Daily Budget (USD)", "llm_daily_budget_usd", "number")}
      </div>
      <div className="space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-faint">Trading Parameters</h3>
        {field("Max Exposure per Trade (e.g. 0.02 = 2%)", "max_exposure_per_trade", "number")}
        {field("Risk per Trade (e.g. 0.01 = 1%)", "risk_per_trade", "number")}
        {field("Max Daily Loss (e.g. 0.03 = 3%)", "max_daily_loss_pct", "number")}
        <div>
          <label className="flex items-center gap-2 text-xs text-ink-dim">
            <input
              type="checkbox"
              checked={form.demo_data}
              onChange={(e) => setForm((f) => ({ ...f, demo_data: e.target.checked }))}
              className="accent-accent"
            />
            Demo Data Mode (router pakai in-memory, bukan PostgreSQL)
          </label>
        </div>
        <div>
          <label className="flex items-center gap-2 text-xs text-ink-dim">
            <input
              type="checkbox"
              checked={form.paper_trading}
              onChange={(e) => setForm((f) => ({ ...f, paper_trading: e.target.checked }))}
              className="accent-accent"
            />
            Paper Trading Mode — order disimulasikan, TIDAK dikirim ke MT5 broker
          </label>
          {!form.paper_trading && (
            <p className="mt-1 text-[11px] text-danger">
              ⚠ Real trading aktif — order akan dikirim ke akun MT5 live/demo
            </p>
          )}
        </div>
      </div>
      <div className="space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-faint">
          Active Symbols (B9 — enable/disable currency)
        </h3>
        <p className="text-xs text-ink-faint">
          Fokus matangkan 1 stream XAUUSD dulu; aktifkan symbol lain setelah
          multi-stream siap. Perubahan berlaku setelah restart api.
        </p>
        <div className="grid grid-cols-2 gap-2">
          {SYMBOL_CANDIDATES.map((sym) => {
            const checked = enabledSymbols.includes(sym);
            return (
              <label
                key={sym}
                className={`flex cursor-pointer items-center justify-between rounded-chip border px-3 py-2 text-xs ${
                  checked
                    ? "border-accent/60 bg-accent/10 text-ink"
                    : "border-line bg-bg text-ink-dim"
                }`}
              >
                <span className="font-mono">{sym}</span>
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(e) =>
                    setEnabledSymbols((prev) =>
                      e.target.checked
                        ? [...prev, sym]
                        : prev.filter((s) => s !== sym)
                    )
                  }
                  className="accent-accent"
                />
              </label>
            );
          })}
        </div>
      </div>
      <div className="flex items-center gap-3">
        <Button type="submit" variant="primary" size="sm" disabled={update.isPending}>
          {update.isPending ? "Saving…" : "Save Config"}
        </Button>
        <p className="text-xs text-ink-faint">Restart api container diperlukan agar apply sepenuhnya.</p>
      </div>
    </form>
  );
}

function EmbedTab({ url, title }: { url: string; title: string }) {
  return (
    <div className="flex h-full min-h-[600px] flex-col">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs text-ink-faint">{title}</p>
        <a href={url} target="_blank" rel="noreferrer" className="text-xs text-accent hover:underline">
          Buka tab baru →
        </a>
      </div>
      <iframe
        src={url}
        title={title}
        className="h-full w-full flex-1 rounded-panel border border-line bg-bg"
        style={{ minHeight: 600 }}
        allow="clipboard-read; clipboard-write"
      />
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function SuperadminPage() {
  const [tab, setTab] = React.useState<Tab>("overview");
  const systemInfo = useSystemInfo();
  const [utc, setUtc] = React.useState(() =>
    new Date().toISOString().replace("T", " ").slice(0, 19)
  );

  React.useEffect(() => {
    const id = setInterval(
      () => setUtc(new Date().toISOString().replace("T", " ").slice(0, 19)),
      1000
    );
    return () => clearInterval(id);
  }, []);

  const healthyCount =
    systemInfo.data?.services.filter(
      (s) => s.health === "healthy" || (s.status === "running" && !s.health)
    ).length ?? 0;
  const totalCount = systemInfo.data?.services.length ?? 0;
  const apiKeys = useApiKeys();
  const create = useCreateApiKey();
  const revoke = useRevokeApiKey();
  const { toast } = useToast();
  const [createOpen, setCreateOpen] = React.useState(false);
  const [secret, setSecret] = React.useState<{ key_id: string; secret: string } | null>(null);
  const [revokeTarget, setRevokeTarget] = React.useState<string | null>(null);

  const handleCreate = (scopes: string[]) => {
    create.mutate(scopes, {
      onSuccess: (created) => {
        setSecret({ key_id: created.key_id, secret: created.secret });
        setCreateOpen(false);
        toast({ variant: "success", title: "API key created", description: created.key_id });
      },
    });
  };

  const confirmRevoke = () => {
    if (!revokeTarget) return;
    revoke.mutate(revokeTarget, {
      onSuccess: () => {
        setRevokeTarget(null);
        toast({ variant: "warn", title: "API key revoked", description: revokeTarget });
      },
    });
  };

  return (
    <div className="mx-auto w-full max-w-[1600px] space-y-3 p-4">
      {/* Bloomberg-style control center header */}
      <header className="flex items-center justify-between border-b border-line pb-2">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] uppercase tracking-widest text-ink-faint">LUMINE</span>
          <span className="h-3 w-px bg-line" aria-hidden="true" />
          <span className="font-mono text-[11px] uppercase tracking-widest text-ink-dim">CONTROL CENTER</span>
          <span className="h-3 w-px bg-line" aria-hidden="true" />
          <div className="flex items-center gap-1.5">
            <span
              className={`h-1.5 w-1.5 rounded-full ${healthyCount >= totalCount && totalCount > 0 ? "bg-up" : healthyCount > 0 ? "bg-warn" : "bg-down"}`}
              aria-hidden="true"
            />
            <span className="font-mono text-[11px] text-ink-dim tabular-nums">
              {healthyCount}/{totalCount} SVC
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] text-ink-faint tabular-nums">{utc} UTC</span>
        </div>
      </header>

      {/* Tabs — Bloomberg uppercase monospace */}
      <nav role="tablist" aria-label="Superadmin sections" className="flex items-center gap-0 border-b border-line">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`border-r border-line px-4 py-1.5 font-mono text-[10px] uppercase tracking-widest transition-colors first:border-l ${
              tab === t.id
                ? "bg-raised text-accent"
                : "text-ink-faint hover:bg-raised hover:text-ink"
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {/* Tab content */}
      <div role="tabpanel" className="min-h-[400px]">
        {tab === "overview" && <OverviewTab data={systemInfo.data} isError={systemInfo.isError} />}
        {tab === "services" && <ServicesTab data={systemInfo.data} isError={systemInfo.isError} />}
        {tab === "config" && <ConfigTab data={systemInfo.data} isError={systemInfo.isError} />}
        {tab === "llm" && <LLMRoutingTab />}
        {tab === "mt5" && (
          <div className="space-y-4">
            <EmbedTab url="/novnc/" title="MT5 HFM — noVNC Desktop (session-protected)" />
            <EALogsPanel />
          </div>
        )}
        {tab === "logs" && <EmbedTab url="/dozzle/" title="Dozzle — Container Log Viewer (session-protected)" />}
        {tab === "autogen" && (
          <EmbedTab
            url="/autogen-studio/"
            title="AutoGen Studio — Visual Agent Management (session-protected)"
          />
        )}
        {tab === "backtest" && <BacktestTab />}
        {tab === "keys" && (
          <div className="space-y-4">
            <div className="flex items-baseline justify-between">
              <h2 className="text-sm font-medium text-ink">API Keys</h2>
              <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
                Create Key
              </Button>
            </div>
            <Card>
              <CardContent className="pt-4">
                {apiKeys.isLoading ? (
                  <p className="text-xs text-ink-faint">Loading…</p>
                ) : apiKeys.isError ? (
                  <ErrorBanner message="admin/keys" />
                ) : (
                  <ApiKeyTable
                    keys={apiKeys.data ?? []}
                    onRevoke={(keyId) => setRevokeTarget(keyId)}
                  />
                )}
              </CardContent>
            </Card>
          </div>
        )}
      </div>

      {/* Modals */}
      <CreateKeyModal open={createOpen} onOpenChange={setCreateOpen} onCreate={handleCreate} />

      {secret && (
        <Dialog open={!!secret} onOpenChange={() => setSecret(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>API Key Created</DialogTitle>
              <DialogDescription>
                Copy the secret — it will not be shown again.
              </DialogDescription>
            </DialogHeader>
            <div className="rounded-chip bg-raised p-3 font-mono text-xs break-all text-ink">
              {secret.secret}
            </div>
            <DialogFooter>
              <Button
                variant="secondary"
                size="sm"
                onClick={async () => {
                  await navigator.clipboard.writeText(secret.secret);
                  toast({ variant: "success", title: "Copied" });
                }}
              >
                Copy
              </Button>
              <Button variant="primary" size="sm" onClick={() => setSecret(null)}>
                Done
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      <Dialog open={revokeTarget !== null} onOpenChange={(o) => !o && setRevokeTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Revoke key?</DialogTitle>
            <DialogDescription>
              Key <span className="font-mono">{revokeTarget}</span> akan langsung tidak valid.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="secondary" size="sm" onClick={() => setRevokeTarget(null)}>Cancel</Button>
            <Button variant="danger" size="sm" onClick={confirmRevoke}>Revoke</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
