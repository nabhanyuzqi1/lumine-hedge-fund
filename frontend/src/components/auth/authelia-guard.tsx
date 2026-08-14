/**
 * AutheliaGuard — client-side auth check untuk route /superadmin.
 *
 * Masalah: Caddy v2 forward_auth mengembalikan 401 mentah ke browser
 * tanpa redirect ke Authelia login page (handle_errors tidak intercept
 * upstream 401). Solusi: React guard ini fetch /auth/api/verify sebelum
 * render, dan redirect ke /auth/?rd=... jika unauthenticated.
 *
 * Note: verify endpoint terima path /auth/api/verify karena Authelia
 * server.address dikonfigurasi dengan prefix /auth.
 */
import * as React from "react";

interface Props {
  children: React.ReactNode;
}

type AuthState = "checking" | "authenticated" | "unauthenticated";

export function AutheliaGuard({ children }: Props) {
  const [state, setState] = React.useState<AuthState>("checking");

  React.useEffect(() => {
    let cancelled = false;

    async function checkAuth() {
      try {
        const resp = await fetch("/auth/api/verify", {
          method: "GET",
          credentials: "include",
          headers: { "Accept": "text/plain" },
        });

        if (cancelled) return;

        if (resp.status === 200) {
          setState("authenticated");
        } else {
          setState("unauthenticated");
          const rd = encodeURIComponent(window.location.pathname + window.location.search);
          window.location.href = `/auth/?rd=${rd}`;
        }
      } catch {
        if (!cancelled) {
          // Network error — redirect ke login daripada menampilkan blank
          setState("unauthenticated");
          const rd = encodeURIComponent(window.location.pathname + window.location.search);
          window.location.href = `/auth/?rd=${rd}`;
        }
      }
    }

    void checkAuth();
    return () => { cancelled = true; };
  }, []);

  if (state === "checking") {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "100vh",
          background: "#070b12",
          fontFamily: "'IBM Plex Mono', monospace",
          color: "#e8eef7",
          flexDirection: "column",
          gap: "1rem",
        }}
        role="status"
        aria-live="polite"
        aria-label="Verifying authentication"
      >
        <div
          style={{
            width: 24,
            height: 24,
            border: "2px solid rgba(77,141,255,0.2)",
            borderTop: "2px solid #4d8dff",
            borderRadius: "50%",
            animation: "spin 0.8s linear infinite",
          }}
        />
        <span style={{ fontSize: "11px", letterSpacing: "0.1em", textTransform: "uppercase", color: "#6d7c92" }}>
          Verifying session…
        </span>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  if (state === "unauthenticated") {
    // Redirect sudah terjadi di effect — render placeholder
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "100vh",
          background: "#070b12",
          fontFamily: "'IBM Plex Mono', monospace",
          color: "#6d7c92",
          fontSize: "11px",
          letterSpacing: "0.1em",
          textTransform: "uppercase",
        }}
      >
        Redirecting to login…
      </div>
    );
  }

  return <>{children}</>;
}
