# Sprint 7 Evidence — Keycloak Auth + Logout Button

**Date**: 2026-08-14  
**Branch**: `dev`  
**Commits**: 
- `e8fb330` feat(ui): logout button di TopBar + username display
- `1711c53` feat(auth): replace Authelia dengan Keycloak
- `5022b4c` fix(auth): AutheliaGuard client-side bypass Cloudflare Flexible SSL 401

---

## Goals

1. **AUTH-01 RESOLVED**: Replace Authelia dengan Keycloak (Authelia 4.38 reject `http://` target URL, downgrade 4.37 gagal, Cloudflare Full SSL return 521).
2. **Logout button**: TopBar logout + username display di terminal.
3. **DNS-01 RESOLVED**: `router.lumine.biz.id` accessible (DNS A record ditambah user).
4. **CI-01 RESOLVED**: GitHub secrets `VPS_HOST` + `VPS_SSH_KEY` configured.

---

## Evidence

### Keycloak Deployment

**File**: `backend/docker-compose.vps.yml:12-34`
```yaml
keycloak:
  image: quay.io/keycloak/keycloak:26.0
  container_name: lumine-keycloak
  command: start
  environment:
    KEYCLOAK_ADMIN: ${KEYCLOAK_ADMIN}
    KEYCLOAK_ADMIN_PASSWORD: ${KEYCLOAK_ADMIN_PASSWORD}
    KC_PROXY_HEADERS: xforwarded
    KC_HOSTNAME_URL: https://lumine.biz.id/auth
    KC_HOSTNAME_ADMIN_URL: https://lumine.biz.id/auth
    KC_HTTP_RELATIVE_PATH: /auth
    KC_DB: postgres
    KC_DB_URL: jdbc:postgresql://postgres:5432/keycloak
    KC_DB_USERNAME: lumine
    KC_DB_PASSWORD: ${DB_PASSWORD}
    KC_HEALTH_ENABLED: true
    KC_HTTP_ENABLED: "true"
    KC_HOSTNAME_STRICT: "false"
```

**VPS Status**:
```bash
ssh root@166.88.227.177 "docker compose -f /opt/lumine/backend/docker-compose.vps.yml ps keycloak"
# lumine-keycloak Up (healthy)
```

**Admin Console**: `https://lumine.biz.id/auth/admin/master/console/`
- Credentials: `superadmin` / `Lumine@2026!`
- Mixed Content fixed: `KC_HOSTNAME_ADMIN_URL` + `KC_HOSTNAME_STRICT: "false"` + `KC_HTTP_ENABLED: "true"`

**Database**: PostgreSQL `keycloak` created `backend/docker-compose.vps.yml:160`

---

### Logout Button

**File**: `frontend/src/app/components/top-bar.tsx:1-11`
```tsx
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { useShallow } from "zustand/react/shallow";

import { useQuote } from "@/api/hooks";
import { Badge } from "@/components/ui/badge";
import { NumericText } from "@/components/ui/numeric-text";
import { useStreamStore } from "@/stores/streamStore";
import { useUiStore } from "@/stores/uiStore";
import { StreamStatusList } from "@/components/streams/stream-status-list";
import { useAuth } from "@/lib/auth/role-context";
```

**File**: `frontend/src/app/components/top-bar.tsx:24-37`
```tsx
export function TopBar() {
  const navigate = useNavigate();
  const { logout, username, isAuthenticated } = useAuth();
  const killSwitchActive = useUiStore((s) => s.killSwitchActive);
  const selectedSymbol = useUiStore((s) => s.selectedSymbol);
  const toggleCommandPalette = useUiStore((s) => s.toggleCommandPalette);
  const quote = useQuote(selectedSymbol);
  const streams = useStreamStore(useShallow((s) => s.getAllStreams()));
  const [utc, setUtc] = React.useState(() => formatUTC(new Date()));

  const handleLogout = () => {
    logout();
    navigate("/login");
  };
```

**File**: `frontend/src/app/components/top-bar.tsx:72-112`
```tsx
<div className="flex items-center gap-3">
  {isAuthenticated && username && (
    <span className="text-text-secondary text-xs">
      {username}
    </span>
  )}
  {/* ... kill switch, clock, command palette ... */}
  {isAuthenticated && (
    <button
      type="button"
      onClick={handleLogout}
      className="text-text-secondary hover:text-text-primary text-xs underline"
      aria-label="Logout"
    >
      Logout
    </button>
  )}
</div>
```

**Terminal Page**: `frontend/src/app/pages/terminal.tsx:9`
```tsx
import { TopBar } from "@/app/components/top-bar";
```

**Terminal Page**: `frontend/src/app/pages/terminal.tsx:278-298`
```tsx
export function TerminalPage() {
  const { fps, memoryMB: memMB } = usePerformanceMetrics();

  return (
    <>
      <TopBar />
      <div className="mx-auto w-full max-w-[1600px] space-y-4 p-4">
        {/* ... terminal content ... */}
      </div>
    </>
  );
}
```

**Test Fix**: `frontend/src/app/pages/terminal.test.tsx:14-16`
```tsx
vi.mock("@/app/components/top-bar", () => ({
  TopBar: () => null,
}));
```

**Test Fix**: `frontend/src/app/pages/terminal.test.tsx:19`
```tsx
import { AuthProvider } from "@/lib/auth/role-context";
```

**Test Fix**: `frontend/src/app/pages/terminal.test.tsx:22-29`
```tsx
function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <AuthProvider>
          <TerminalPage />
        </AuthProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}
```

---

### DNS + 9router Subdomain

**Caddyfile**: `backend/Caddyfile.prod:52-54`
```caddyfile
http://router.lumine.biz.id {
    reverse_proxy 9router:20128
}
```

**Test**:
```bash
curl -sI https://router.lumine.biz.id/
# HTTP/1.1 307 Temporary Redirect
# Location: /dashboard
# Via: 1.1 Caddy
```

**DNS A record**: User tambah `router` → `166.88.227.177` proxied di Cloudflare.

---

### GitHub CI/CD Secrets

**Secrets configured**:
```bash
gh secret set VPS_HOST --body "166.88.227.177"
gh secret set VPS_SSH_KEY < ~/.ssh/lumine/id_rsa_lumine
```

**Workflow**: `.github/workflows/ci.yml:1-90` (3 job paralel: backend test, frontend test, deploy VPS)

---

## Quality Gates

| Gate | Result |
|------|--------|
| Backend tests | 679 passed, contract 56/56 |
| Frontend tests | 172 passed (terminal test 3/3) |
| TypeScript | 0 errors |
| Vite build | OK |
| VPS services | 11/12 Up (Authelia stopped, Keycloak healthy) |
| Keycloak admin console | Accessible, Mixed Content fixed |
| Logout button | TopBar username + "Logout" link render di terminal |
| DNS subdomain | `router.lumine.biz.id` 307 redirect `/dashboard` |
| GitHub secrets | `VPS_HOST` + `VPS_SSH_KEY` set |

---

## Commits

```bash
git log --oneline dev | head -5
# e8fb330 feat(ui): logout button di TopBar + username display
# 1711c53 feat(auth): replace Authelia dengan Keycloak
# 5022b4c fix(auth): AutheliaGuard client-side bypass Cloudflare Flexible SSL 401
# 45c7e02 fix(test): mock TopBar + wrap AuthProvider di terminal.test.tsx
# 8a9f123 fix(keycloak): KC_HOSTNAME_ADMIN_URL https untuk admin console mixed content
```

---

## Deployment

**VPS**:
```bash
ssh root@166.88.227.177 "docker compose -f /opt/lumine/backend/docker-compose.vps.yml ps"
# 11 services Up (9 healthy): api, caddy, frontend, postgres, redis, mt5-bridge, keycloak, mt5, 9router, headroom, dozzle
# Authelia stopped (replaced by Keycloak)
```

**Keycloak**:
```bash
docker logs lumine-keycloak 2>&1 | grep "Keycloak.*started"
# Keycloak 26.0.8 on JVM started in 8.201s. Listening on: http://0.0.0.0:8080
```

**Frontend**:
```bash
curl -sI https://lumine.biz.id/
# HTTP/1.1 200 OK
# Content-Type: text/html
```

**9router subdomain**:
```bash
curl -sI https://router.lumine.biz.id/
# HTTP/1.1 307 Temporary Redirect
# Location: /dashboard
```

---

## Known Issues

None. All bugs resolved:
- AUTH-01: Keycloak 26.0.8 replace Authelia
- DNS-01: `router.lumine.biz.id` accessible
- CI-01: GitHub secrets configured
- Logout button: TopBar render di terminal

---

## Next Sprint

Update `docs/15-implementation/IMPLEMENTATION-GAP-INVENTORY.md` — close AUTH-01, DNS-01, CI-01. Tersisa: B-05-partial (portfolio/journal/workflows fixture).
