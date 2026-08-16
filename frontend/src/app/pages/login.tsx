import * as React from "react";
import { Link, Navigate, useLocation, useSearchParams } from "react-router-dom";
import { useAuth } from "@/lib/auth/role-context";
import { motion } from "framer-motion";
import { LumineIcon } from "@/components/landing/agent-icons";
import { useTranslation } from "react-i18next";
import { LanguageSwitcher } from "@/components/language-switcher";
import { LoadingScreenSkeleton } from "@/components/ui/skeleton";

/**
 * Lumine Login — first-party internal auth.
 * Credentials verified by the backend (POST /api/auth/login, PBKDF2 in
 * PostgreSQL). Success → HttpOnly cookie `lumine_session` + redirect.
 */

/* ── Inline icons ─────────────────────────────────────────────────── */

function UserIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}

function LockIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="11" width="18" height="11" rx="2" />
      <path d="M7 11V7a5 5 0 0110 0v4" />
    </svg>
  );
}

function EyeIcon({ size = 14, off = false }: { size?: number; off?: boolean }) {
  return off ? (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M9.88 9.88a3 3 0 104.24 4.24" />
      <path d="M10.73 5.08A10.43 10.43 0 0112 5c7 0 10 7 10 7a13.16 13.16 0 01-1.67 2.68" />
      <path d="M6.61 6.61A13.526 13.526 0 002 12s3 7 10 7a9.74 9.74 0 005.39-1.61" />
      <line x1="2" y1="2" x2="22" y2="22" />
    </svg>
  ) : (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

/* ── System terminal panel (brand side) ──────────────────────────── */

const SYSTEM_LINES = [
  { ok: true, textKey: "login.systemAuthService" },
  { ok: true, textKey: "login.systemSessionStore" },
  { ok: true, textKey: "login.systemAgents" },
  { ok: true, textKey: "login.systemRiskEngine" },
  { ok: false, textKey: "login.systemMarketFeed" },
];

function SystemTerminal() {
  const { t } = useTranslation();
  return (
    <div 
      className="w-full max-w-md overflow-hidden rounded-panel border shadow-lg backdrop-blur-xl"
      style={{
        backgroundColor: "var(--glass-bg)",
        borderColor: "var(--glass-border)",
        boxShadow: "var(--glass-shadow)",
      }}
    >
      {/* Terminal header */}
      <div className="flex items-center gap-2 border-b border-line-soft bg-raised/40 px-4 py-2.5 backdrop-blur-sm">
        <span className="h-2.5 w-2.5 rounded-full bg-down/70" />
        <span className="h-2.5 w-2.5 rounded-full bg-warn/70" />
        <span className="h-2.5 w-2.5 rounded-full bg-up/70" />
        <span className="ml-3 font-mono text-[10px] uppercase tracking-widest text-ink-faint">
          lumine://auth
        </span>
      </div>

      {/* Terminal body */}
      <div className="space-y-2 p-5 font-mono text-xs">
        {SYSTEM_LINES.map((line, i) => (
                  <motion.div
                    key={line.textKey}
                    className="flex items-center gap-2.5"
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.35, delay: 0.3 + i * 0.15 }}
                  >
                    <span className="text-up">[{line.ok ? "OK" : "●"}]</span>
                    <span className={line.ok ? "text-ink-dim" : "text-up"}>
                      {t(line.textKey)}
                    </span>
                  </motion.div>
                ))}

        {/* Blinking cursor */}
        <motion.div
          className="flex items-center gap-2.5"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.2 }}
        >
          <span className="text-ink-faint">❯</span>
          <span className="inline-block h-3.5 w-2 animate-pulse bg-accent/80" />
        </motion.div>
      </div>
    </div>
  );
}

/* ── Page ────────────────────────────────────────────────────────── */

export function LoginPage() {
  const { t } = useTranslation();
  const { isAuthenticated, loading, login } = useAuth();
  const location = useLocation();
  const [searchParams] = useSearchParams();

  const redirectTarget =
    searchParams.get("redirect") ??
    (location.state as { from?: Location })?.from?.pathname ??
    "/app/terminal";

  const [username, setUsername] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [showPassword, setShowPassword] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);

  if (loading) {
    return <LoadingScreenSkeleton />;
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

  const inputBase =
    "w-full rounded-chip border bg-abyss py-2.5 pl-9 pr-9 font-mono text-sm text-ink placeholder-ink-faint outline-none transition-colors focus:ring-1";
  const inputState = error
    ? "border-down/60 focus:border-down focus:ring-down"
    : "border-line focus:border-accent focus:ring-accent";

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

      {/* Back to landing */}
      <motion.div
        className="absolute left-5 top-5 z-10 md:left-8 md:top-8"
        initial={{ opacity: 0, x: -12 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.5, delay: 0.2 }}
      >
        <Link
          to="/"
          className="group flex items-center gap-2 rounded-chip border border-line-soft bg-abyss/80 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.18em] text-ink-dim backdrop-blur transition-colors hover:border-line hover:text-ink"
        >
          <svg
            className="h-3.5 w-3.5 transition-transform duration-300 group-hover:-translate-x-0.5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 12H5m0 0l6 6m-6-6l6-6"
            />
          </svg>
          {t("login.backToHome")}
                  </Link>
      </motion.div>

      {/* Language Switcher - pojok kanan atas (mirror back button) */}
      <motion.div
        className="absolute right-5 top-5 z-10 md:right-8 md:top-8"
        initial={{ opacity: 0, x: 12 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.5, delay: 0.2 }}
      >
        <LanguageSwitcher />
      </motion.div>

      <div className="relative grid w-full max-w-4xl items-center gap-10 px-6 lg:grid-cols-[1.15fr_1fr] lg:gap-14">
        {/* LEFT — brand + system terminal (desktop) */}
        <motion.div
          className="hidden flex-col items-start gap-8 lg:flex"
          initial={{ opacity: 0, x: -24 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.7, ease: "easeOut" }}
        >
          <div className="flex items-center gap-4">
            <LumineIcon className="h-14 w-14 text-accent" />
            <div>
              <div className="font-display text-2xl font-bold tracking-[0.25em] text-ink">
                LUMINE
              </div>
              <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.22em] text-ink-faint">
                              {t("login.brandSubtitle")}
                            </div>
                          </div>
                        </div>

                        <SystemTerminal />

                        <p className="max-w-sm text-sm leading-relaxed text-ink-dim">
                          {t("login.systemDescription")}
                        </p>
        </motion.div>

        {/* RIGHT — auth panel */}
        <motion.div
          className="w-full"
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.15, ease: "easeOut" }}
        >
          {/* Mobile brand */}
          <div className="mb-8 flex flex-col items-center gap-3 text-center lg:hidden">
            <LumineIcon className="h-12 w-12 text-accent" />
            <div>
              <div className="font-display text-xl font-bold tracking-[0.25em] text-ink">
                LUMINE
              </div>
              <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.22em] text-ink-faint">
                              {t("login.brandSubtitle")}
                            </div>
                          </div>
                        </div>

                        <div className="rounded-panel border border-line bg-raised/70 p-6 shadow-panel backdrop-blur">
                          {/* Status strip */}
                          <div className="mb-5 flex items-center justify-between border-b border-line-soft pb-4">
                            <span className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.2em] text-up">
                              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-up" />
                              {t("login.systemOnline")}
                            </span>
                            <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-ink-faint">
                              {t("login.internalAccess")}
                            </span>
                          </div>

            {/* Language Switcher sudah dipindah ke atas */}

            <form onSubmit={handleSubmit} className="space-y-4" noValidate>
              <div className="space-y-1.5">
                <label
                  htmlFor="login-username"
                  className="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-faint"
                >
                  {t("login.username")}
                </label>
                            <div className="relative">
                              <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint">
                                <UserIcon />
                              </span>
                              <input
                                id="login-username"
                                type="text"
                                value={username}
                                onChange={(e) => setUsername(e.target.value)}
                                required
                                autoComplete="username"
                                autoFocus
                                className={`${inputBase} ${inputState}`}
                                placeholder="username"
                              />
                            </div>
                          </div>

                          <div className="space-y-1.5">
                            <label
                              htmlFor="login-password"
                              className="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-faint"
                            >
                              {t("login.password")}
                            </label>
                            <div className="relative">
                              <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint">
                                <LockIcon />
                              </span>
                              <input
                                id="login-password"
                                type={showPassword ? "text" : "password"}
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                required
                                autoComplete="current-password"
                                className={`${inputBase} ${inputState}`}
                                placeholder="••••••••"
                              />
                              <button
                                type="button"
                                onClick={() => setShowPassword((s) => !s)}
                                className="absolute right-2 top-1/2 -translate-y-1/2 rounded-chip p-1.5 text-ink-faint transition-colors hover:text-ink"
                                aria-label={showPassword ? "Hide password" : "Show password"}
                              >
                                <EyeIcon off={!showPassword} />
                              </button>
                            </div>
                          </div>

                          {error && (
                            <motion.p
                              key={error}
                              className="flex items-center gap-2 rounded-chip border border-down/30 bg-down/10 px-3 py-2 font-mono text-xs text-down"
                              initial={{ opacity: 0, x: -8 }}
                              animate={{ opacity: 1, x: 0 }}
                            >
                              <svg className="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={2}
                                  d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"
                                />
                              </svg>
                              {t("login.error")}
                            </motion.p>
                          )}

                          <button
                            type="submit"
                            disabled={submitting}
                            className="flex w-full items-center justify-center gap-2 rounded-chip bg-accent px-4 py-2.5 font-mono text-xs font-semibold uppercase tracking-[0.22em] text-white transition-colors hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {submitting ? (
                              <>
                                <svg className="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                                </svg>
                                {t("login.submitting")}
                  </>
                ) : (
                                  t("login.submit")
                                )}
                              </button>
                            </form>
                          </div>

                          <p className="mt-6 text-center font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint">
                            {t("login.restricted")}
                          </p>
        </motion.div>
      </div>
    </div>
  );
}
