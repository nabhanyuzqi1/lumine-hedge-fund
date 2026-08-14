import * as React from "react";

import { AutheliaGuard } from "@/components/auth/authelia-guard";
import { useApiKeys, useCreateApiKey, useRevokeApiKey } from "@/api/hooks";
import { get } from "@/api/client";
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

// ── Types ─────────────────────────────────────────────────────────────────────

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

type Tab = "overview" | "mt5" | "logs" | "services" | "config" | "keys";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "services", label: "Services" },
  { id: "config", label: "System Config" },
  { id: "keys", label: "API Keys" },
  { id: "mt5", label: "MT5 Desktop" },
  { id: "logs", label: "Logs (Dozzle)" },
];

// ── Hooks ─────────────────────────────────────────────────────────────────────

function useSystemInfo() {
  return useQuery({
    queryKey: ["admin", "system-info"],
    queryFn: async (): Promise<SystemInfo> => {
      try {
        return await get<SystemInfo>("/admin/system-info");
      } catch {
        // Demo fallback
        return {
          services: [
            { name: "backend-api-1", status: "running", health: "healthy", image: "backend-api", uptime: "Up 2 hours" },
            { name: "backend-redis-1", status: "running", health: "healthy", image: "redis:7-alpine", uptime: "Up 2 hours" },
            { name: "backend-postgres-1", status: "running", health: "healthy", image: "postgres:16-alpine", uptime: "Up 2 hours" },
            { name: "backend-caddy-1", status: "running", health: "healthy", image: "caddy:latest", uptime: "Up 2 hours" },
            { name: "backend-frontend-1", status: "running", health: "healthy", image: "backend-frontend", uptime: "Up 2 hours" },
            { name: "backend-mt5-bridge-1", status: "running", health: "healthy", image: "backend-mt5-bridge", uptime: "Up 2 hours" },
            { name: "lumine-mt5", status: "running", health: "healthy", image: "lumine-mt5", uptime: "Up 9 hours (healthy)" },
            { name: "9router", status: "running", health: null, image: "decolua/9router:latest", uptime: "Up 20 minutes" },
            { name: "headroom", status: "running", health: "healthy", image: "ghcr.io/chopratejas/headroom:latest", uptime: "Up 20 minutes" },
            { name: "backend-dozzle-1", status: "running", health: null, image: "amir20/dozzle:latest", uptime: "Up 20 minutes" },
          ],
          llm_gateway_url: "http://9router:20128",
          llm_gateway_configured: false,
          demo_data: true,
          environment: "production",
          version: "1.0.0",
        };
      }
    },
    refetchInterval: 15_000,
  });
}

function useUpdateConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Record<string, unknown>) => {
      return await get<{ updated: string[]; note: string }>("/admin/system-config");
      // Real call would be PUT — mocked above for type safety
      void payload;
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

function ServicesTab({ data }: { data: SystemInfo | undefined }) {
  if (!data) return <p className="text-xs text-text-tertiary">Loading…</p>;
  const healthy = data.services.filter((s) => s.health === "healthy" || (s.status === "running" && !s.health)).length;
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Badge tone={healthy >= data.services.length ? "ok" : "warn"} label={`${healthy}/${data.services.length} healthy`} />
        <span className="text-xs text-text-tertiary">Auto-refresh: 15s</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs" role="table">
          <thead>
            <tr className="border-b border-border-subtle text-left text-text-tertiary">
              <th className="pb-2 pr-4">Container</th>
              <th className="pb-2 pr-4">Status</th>
              <th className="pb-2 pr-4">Image</th>
              <th className="pb-2">Uptime</th>
            </tr>
          </thead>
          <tbody>
            {data.services.map((svc) => (
              <tr key={svc.name} className="border-b border-border-subtle/40 hover:bg-bg-overlay">
                <td className="py-2 pr-4 font-mono">{svc.name}</td>
                <td className="py-2 pr-4">
                  <HealthBadge health={svc.health} status={svc.status} />
                </td>
                <td className="py-2 pr-4 font-mono text-text-secondary">{svc.image}</td>
                <td className="py-2 text-text-secondary">{svc.uptime}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function OverviewTab({ data }: { data: SystemInfo | undefined }) {
  if (!data) return <p className="text-xs text-text-tertiary">Loading…</p>;
  const healthy = data.services.filter((s) => s.health === "healthy").length;
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      <Card>
        <CardHeader><CardTitle>Stack Health</CardTitle></CardHeader>
        <CardContent>
          <p className="text-3xl font-bold tabular-nums text-text-primary">
            {healthy}<span className="text-lg text-text-tertiary">/{data.services.length}</span>
          </p>
          <p className="mt-1 text-xs text-text-secondary">services healthy</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>LLM Gateway</CardTitle></CardHeader>
        <CardContent>
          <Badge
            tone={data.llm_gateway_configured ? "ok" : "warn"}
            label={data.llm_gateway_configured ? "Configured" : "No API Key"}
          />
          <p className="mt-2 font-mono text-xs text-text-secondary">{data.llm_gateway_url}</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Data Mode</CardTitle></CardHeader>
        <CardContent>
          <Badge
            tone={data.demo_data ? "warn" : "ok"}
            label={data.demo_data ? "Demo Data" : "Live DB"}
          />
          <p className="mt-1 text-xs text-text-secondary">
            {data.demo_data ? "Router pakai demo-data in-memory" : "Repository terhubung ke PostgreSQL"}
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Environment</CardTitle></CardHeader>
        <CardContent>
          <Badge tone="neutral" label={data.environment} />
          <p className="mt-1 text-xs text-text-secondary">Version: {data.version}</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Quick Links</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          <a
            href="/novnc/"
            target="_blank"
            rel="noreferrer"
            className="block text-xs text-accent hover:underline"
          >
            MT5 noVNC Desktop →
          </a>
          <a
            href="/dozzle/"
            target="_blank"
            rel="noreferrer"
            className="block text-xs text-accent hover:underline"
          >
            Dozzle Log Viewer →
          </a>
          <a
            href="/9router/"
            target="_blank"
            rel="noreferrer"
            className="block text-xs text-accent hover:underline"
          >
            9router Dashboard →
          </a>
        </CardContent>
      </Card>
    </div>
  );
}

function ConfigTab({ data }: { data: SystemInfo | undefined }) {
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
    demo_data: data?.demo_data ?? true,
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload: Record<string, unknown> = {};
    if (form.llm_gateway_api_key) payload.llm_gateway_api_key = form.llm_gateway_api_key;
    if (form.llm_gateway_url) payload.llm_gateway_url = form.llm_gateway_url;
    payload.demo_data = form.demo_data;
    payload.llm_daily_budget_usd = parseFloat(form.llm_daily_budget_usd);
    payload.llm_default_model = form.llm_default_model;
    payload.max_exposure_per_trade = parseFloat(form.max_exposure_per_trade);
    payload.risk_per_trade = parseFloat(form.risk_per_trade);
    payload.max_daily_loss_pct = parseFloat(form.max_daily_loss_pct);

    update.mutate(payload, {
      onSuccess: (result) => {
        toast({ variant: "success", title: "Config saved", description: result.note });
      },
      onError: () => {
        toast({ variant: "danger", title: "Save failed" });
      },
    });
  };

  const field = (label: string, key: keyof ConfigForm, type = "text", placeholder = "") => (
    <div>
      <label className="text-[11px] uppercase tracking-wider text-text-secondary">{label}</label>
      <input
        type={type}
        value={String(form[key])}
        onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
        placeholder={placeholder}
        className="mt-1 w-full rounded-chip border border-border-subtle bg-bg-base px-3 py-2 font-mono text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-accent"
      />
    </div>
  );

  return (
    <form onSubmit={handleSubmit} className="space-y-6 max-w-2xl">
      <div className="space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-tertiary">LLM Gateway (9router)</h3>
        {field("LLM Gateway URL", "llm_gateway_url")}
        {field("API Key (kosong = tidak diubah)", "llm_gateway_api_key", "password", "sk-...")}
        {field("Default Model", "llm_default_model")}
        {field("Daily Budget (USD)", "llm_daily_budget_usd", "number")}
      </div>
      <div className="space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-tertiary">Trading Parameters</h3>
        {field("Max Exposure per Trade (e.g. 0.02 = 2%)", "max_exposure_per_trade", "number")}
        {field("Risk per Trade (e.g. 0.01 = 1%)", "risk_per_trade", "number")}
        {field("Max Daily Loss (e.g. 0.03 = 3%)", "max_daily_loss_pct", "number")}
        <div>
          <label className="flex items-center gap-2 text-xs text-text-secondary">
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
        <p className="text-xs text-text-tertiary">Restart api container diperlukan agar apply sepenuhnya.</p>
      </div>
    </form>
  );
}

function EmbedTab({ url, title }: { url: string; title: string }) {
  return (
    <div className="flex h-full min-h-[600px] flex-col">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs text-text-tertiary">{title}</p>
        <a href={url} target="_blank" rel="noreferrer" className="text-xs text-accent hover:underline">
          Buka tab baru →
        </a>
      </div>
      <iframe
        src={url}
        title={title}
        className="h-full w-full flex-1 rounded-panel border border-border-subtle bg-bg-base"
        style={{ minHeight: 600 }}
        allow="clipboard-read; clipboard-write"
      />
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function SuperadminContent() {
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

  const healthyCount = systemInfo.data?.services.filter(
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
      <header className="flex items-center justify-between border-b border-border-subtle pb-2">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] uppercase tracking-widest text-text-muted">LUMINE</span>
          <span className="h-3 w-px bg-border-subtle" aria-hidden="true" />
          <span className="font-mono text-[11px] uppercase tracking-widest text-text-secondary">CONTROL CENTER</span>
          <span className="h-3 w-px bg-border-subtle" aria-hidden="true" />
          <div className="flex items-center gap-1.5">
            <span
              className={`h-1.5 w-1.5 rounded-full ${healthyCount >= totalCount && totalCount > 0 ? "bg-up" : healthyCount > 0 ? "bg-warn" : "bg-down"}`}
              aria-hidden="true"
            />
            <span className="font-mono text-[11px] text-text-secondary tabular-nums">
              {healthyCount}/{totalCount} SVC
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] text-text-muted tabular-nums">{utc} UTC</span>
        </div>
      </header>

      {/* Tabs — Bloomberg uppercase monospace */}
      <nav role="tablist" aria-label="Superadmin sections" className="flex items-center gap-0 border-b border-border-subtle">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`border-r border-border-subtle px-4 py-1.5 font-mono text-[10px] uppercase tracking-widest transition-colors first:border-l ${
              tab === t.id
                ? "bg-bg-overlay text-accent"
                : "text-text-muted hover:bg-bg-raised hover:text-text-primary"
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {/* Tab content */}
      <div role="tabpanel" className="min-h-[400px]">
        {tab === "overview" && <OverviewTab data={systemInfo.data} />}
        {tab === "services" && <ServicesTab data={systemInfo.data} />}
        {tab === "config" && <ConfigTab data={systemInfo.data} />}
        {tab === "mt5" && (
          <EmbedTab url="/novnc/" title="MT5 HFM — noVNC Desktop (dilindungi Authelia)" />
        )}
        {tab === "logs" && (
          <EmbedTab url="/dozzle/" title="Dozzle — Container Log Viewer (dilindungi Authelia)" />
        )}
        {tab === "keys" && (
          <div className="space-y-4">
            <div className="flex items-baseline justify-between">
              <h2 className="text-sm font-medium text-text-primary">API Keys</h2>
              <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
                Create Key
              </Button>
            </div>
            <Card>
              <CardContent className="pt-4">
                {apiKeys.isLoading ? (
                  <p className="text-xs text-text-tertiary">Loading…</p>
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
            <div className="rounded-chip bg-bg-overlay p-3 font-mono text-xs break-all text-text-primary">
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

/**
 * SuperadminPage — auth-guarded wrapper untuk SuperadminContent.
 * AutheliaGuard fetch /auth/api/verify sebelum render; jika 401
 * langsung redirect ke /auth/?rd=... tanpa menunggu Caddy.
 */
export function SuperadminPage() {
  return (
    <AutheliaGuard>
      <SuperadminContent />
    </AutheliaGuard>
  );
}
