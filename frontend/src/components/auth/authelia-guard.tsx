import { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";

/**
 * AutheliaGuard — client-side auth check untuk routes yang dilindungi Authelia.
 * 
 * Workflow:
 * 1. Browser fetch GET /auth/api/verify (Authelia verify endpoint)
 * 2. Response 200 → render children (user authenticated)
 * 3. Response 401 → redirect ke /auth/?rd=<current-url> (Authelia login)
 * 4. Loading state: spinner
 * 
 * Kenapa client-side:
 * - Caddy forward_auth upstream 401 tidak trigger handle_errors (Caddy v2 limitation)
 * - Cloudflare Flexible SSL → VPS terima HTTP → Authelia 4.38 reject `http://` target URL
 * - AutheliaGuard bypass Caddy forward_auth dengan fetch langsung dari browser
 */
export function AutheliaGuard({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<"loading" | "authenticated" | "unauthenticated">("loading");
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const verifyAuth = async () => {
      try {
        const response = await fetch("/auth/api/verify", {
          method: "GET",
          credentials: "include", // kirim cookies
          headers: {
            "X-Original-URL": `https://lumine.biz.id${location.pathname}`,
          },
        });

        if (response.ok) {
          setStatus("authenticated");
        } else if (response.status === 401) {
          // Redirect ke Authelia login dengan return URL
          const redirectUrl = `/auth/?rd=${encodeURIComponent(location.pathname + location.search)}`;
          window.location.href = redirectUrl;
        } else {
          // Unexpected error, redirect ke login juga
          window.location.href = `/auth/?rd=${encodeURIComponent(location.pathname)}`;
        }
      } catch (error) {
        console.error("AutheliaGuard verify error:", error);
        window.location.href = `/auth/?rd=${encodeURIComponent(location.pathname)}`;
      }
    };

    verifyAuth();
  }, [location.pathname, location.search, navigate]);

  if (status === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-abyss">
        <div className="text-center space-y-4">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-accent border-t-transparent" />
          <p className="text-ink-dim font-mono text-sm">Verifying session...</p>
        </div>
      </div>
    );
  }

  if (status === "authenticated") {
    return <>{children}</>;
  }

  return null;
}
