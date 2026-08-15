import * as React from "react";

import { useApiKeys, useCreateApiKey, useRevokeApiKey } from "@/api/hooks";
import { get, put } from "@/api/client";
import { ApiKeyTable } from "@/components/admin/api-key-table";
import { CreateKeyModal } from "@/components/admin/create-key-modal";
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
  environment: string;
  version: string;
}

interface ConfigForm {
  llm_gateway_api_key: string;
  llm_gateway_url: string;
  llm_default_model: string;
  llm_daily_budget_usd: string;
  max_exposure_per_trade: string;
  risk_per_trade: string;
  max_daily_loss_pct: string;
  demo_data: boolean;
}

// ── Tabs ──────────────────────────────────────────────────────────────────────

type Tab = "overview" | "services" | "config" | "keys" | "mt5" | "logs";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "services", label: "Services" },
  { id: "config", label: "System Config" },
  { id: "keys", label: "API Keys" },
  { id: "mt5", label: "MT5 Desktop" },
  { id: "logs", label: "Logs (Dozzle)" },
];

// ── Hooks (real backend calls — no demo fallback) ───────────────────────────

function useSystemInfo() {
  return useQuery({
    queryKey: ["admin", "system-info"],
    queryFn: () => get<SystemInfo>("/admin/system-info"),
    refetchInterval: 15_000,
  });
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
  const [form, setForm] = React.useState<ConfigForm>({
    llm_gateway_api_key: "",
    llm_gateway_url: data?.llm_gateway_url ?? "http://9router:20128",
    llm_default_model: "deepseek-v4",
    llm_daily_budget_usd: "50",
    max_exposure_per_trade: "0.02",
    risk_per_trade: "0.01",
    max_daily_loss_pct: "0.03",
    demo_data: data?.demo_data ?? false,
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
    };
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
        {tab === "mt5" && <EmbedTab url="/novnc/" title="MT5 HFM — noVNC Desktop (session-protected)" />}
        {tab === "logs" && <EmbedTab url="/dozzle/" title="Dozzle — Container Log Viewer (session-protected)" />}
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
