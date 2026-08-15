import * as React from "react";
import { Navigate, useLocation, useSearchParams } from "react-router-dom";
import { useAuth } from "@/lib/auth/role-context";
import { LumineIcon } from "@/components/landing/agent-icons";

/**
 * Lumine Login — first-party internal auth.
 * Credentials verified by the backend (POST /api/auth/login, PBKDF2 in
 * PostgreSQL). Success → HttpOnly cookie `lumine_session` + redirect.
 */

export function LoginPage() {
  const { isAuthenticated, loading, login } = useAuth();
  const location = useLocation();
  const [searchParams] = useSearchParams();

  const redirectTarget =
    searchParams.get("redirect") ??
    (location.state as { from?: Location })?.from?.pathname ??
    "/app/terminal";

  const [username, setUsername] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-abyss">
        <div className="flex items-center gap-3">
          <LumineIcon className="h-6 w-6 animate-pulse text-accent" />
          <span className="font-mono text-xs uppercase tracking-widest text-ink-faint">
            Verifying session…
          </span>
        </div>
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to={redirectTarget} replace />;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username.trim(), password);
      // State update triggers the <Navigate> above.
    } catch {
      setError("Invalid credentials. Contact your administrator.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-abyss">
      {/* Ambient background */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute left-1/2 top-0 h-[420px] w-[720px] -translate-x-1/2 rounded-full bg-accent/[0.05] blur-[120px]" />
        <div
          className="absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage:
              "linear-gradient(var(--color-line) 1px, transparent 1px), linear-gradient(90deg, var(--color-line) 1px, transparent 1px)",
            backgroundSize: "64px 64px",
          }}
        />
      </div>

      <div className="relative w-full max-w-sm p-6">
        {/* Brand */}
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <LumineIcon className="h-12 w-12 text-accent" />
          <div>
            <div className="font-display text-xl font-bold tracking-[0.25em] text-ink">
              LUMINE
            </div>
            <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.22em] text-ink-faint">
              AI-Native Quantitative Intelligence
            </div>
          </div>
        </div>

        {/* Auth panel */}
        <div className="rounded-panel border border-line bg-raised/70 p-6 shadow-panel backdrop-blur">
          {/* Status strip */}
          <div className="mb-5 flex items-center justify-between border-b border-line-soft pb-4">
            <span className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.2em] text-up">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-up" />
              System Online
            </span>
            <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-ink-faint">
              Internal Access
            </span>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label
                htmlFor="login-username"
                className="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-faint"
              >
                Username
              </label>
              <input
                id="login-username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoComplete="username"
                autoFocus
                className="w-full rounded-chip border border-line bg-abyss px-3 py-2.5 font-mono text-sm text-ink placeholder-ink-faint outline-none transition-colors focus:border-accent focus:ring-1 focus:ring-accent"
                placeholder="username"
              />
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="login-password"
                className="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-faint"
              >
                Password
              </label>
              <input
                id="login-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                className="w-full rounded-chip border border-line bg-abyss px-3 py-2.5 font-mono text-sm text-ink placeholder-ink-faint outline-none transition-colors focus:border-accent focus:ring-1 focus:ring-accent"
                placeholder="••••••••"
              />
            </div>

            {error && (
              <p className="flex items-center gap-2 rounded-chip border border-down/30 bg-down/10 px-3 py-2 font-mono text-xs text-down">
                <svg className="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"
                  />
                </svg>
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-chip bg-accent px-4 py-2.5 font-mono text-xs font-semibold uppercase tracking-[0.22em] text-white transition-colors hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitting ? "Authenticating…" : "Enter System"}
            </button>
          </form>
        </div>

        <p className="mt-6 text-center font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint">
          Restricted access — authorized users only
        </p>
      </div>
    </div>
  );
}
