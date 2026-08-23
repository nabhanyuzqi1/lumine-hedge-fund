---
title: "Frontend Architecture"
aliases: ["React Frontend", "UI"]
type: concept
status: evergreen
created: 2026-08-23
updated: 2026-08-23
tags: ["#frontend", "#react", "#typescript", "#ui"]
---

# Frontend Architecture

React TypeScript frontend untuk Lumine.

## 🏗️ Stack

| Component | Technology |
|-----------|------------|
| Framework | React 18 + TypeScript |
| Build | Vite |
| Styling | Tailwind CSS + shadcn-ui |
| Charts | Lightweight Charts + Recharts |
| State | React Query + Context |
| Realtime | EventSource (SSE) |

## 📁 Directory Structure

```
frontend/
├── src/
│   ├── app/                  # Pages (file-based routing)
│   │   ├── dashboard/        # /dashboard
│   │   ├── terminal/         # /terminal
│   │   ├── research/         # /research
│   │   └── superadmin/       # /superadmin
│   ├── components/
│   │   ├── ui/               # shadcn-ui primitives
│   │   ├── charts/           # CandlestickChart, etc
│   │   └── layout/           # Header, Sidebar, etc
│   ├── hooks/                # Custom hooks
│   ├── lib/                  # Utilities
│   └── types/                # TypeScript types
├── public/
└── package.json
```

## 📄 Pages

### Dashboard (`/dashboard`)
- Overview cards (equity, PnL, positions)
- Positions table (real-time)
- Recent trades
- LLM status indicator

### Terminal (`/terminal`)
- Fullscreen chart (TradingView-like)
- Order entry panel
- Position management
- Real-time ticks

### Research (`/research`)
- News feed dengan LLM analysis
- Market sentiment
- Economic calendar

### Superadmin (`/superadmin`)
- System config
- LLM routing management
- Agent status

## 🎨 Components

### CandlestickChart

```tsx
<CandlestickChart
  data={bars}           // OHLCV data
  symbol="EURUSD"
  height={400}
  showVolume={false}    // Volume histogram removed (22 Aug)
/>
```

### PositionsTable

```tsx
<PositionsTable
  positions={positions}
  realtime={true}       // SSE updates
  onClose={(id) => ...}
/>
```

### NewsFeed

```tsx
<NewsFeed
  headlines={news}
  sentiment={true}      // Show LLM sentiment
/>
```

## 🔄 Real-time Updates

### SSE Connection

```typescript
// hooks/useStatusStream.ts
useEffect(() => {
  const es = new EventSource('/api/sse/status');

  es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    setPositions(data.positions);
    setEquity(data.equity);
  };

  es.onerror = () => {
    // Auto-reconnect after 5s
    setTimeout(() => window.location.reload(), 5000);
  };

  return () => es.close();
}, []);
```

### React Query for API

```typescript
// hooks/useMarketQuotes.ts
export function useMarketQuotes() {
  return useQuery({
    queryKey: ['market', 'quotes'],
    queryFn: () => fetch('/api/market/quotes').then(r => r.json()),
    refetchInterval: 5000,  // Poll every 5s
  });
}
```

## 🔐 Authentication

### HMAC Signing

```typescript
// lib/auth.ts
export async function signRequest(timestamp: string): Promise<string> {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw',
    encoder.encode(VITE_LUMINE_API_SECRET),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const signature = await crypto.subtle.sign(
    'HMAC',
    key,
    encoder.encode(timestamp)
  );
  return Array.from(new Uint8Array(signature))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}
```

### API Client

```typescript
// lib/api.ts
const api = axios.create({
  baseURL: '/api',
});

api.interceptors.request.use(async (config) => {
  const timestamp = Date.now().toString();
  const signature = await signRequest(timestamp);
  config.headers['X-Timestamp'] = timestamp;
  config.headers['X-Signature'] = signature;
  config.headers['X-API-Key'] = VITE_LUMINE_API_KEY;
  return config;
});
```

## 🚀 Development

### Run Locally

```bash
cd frontend
npm install
npm run dev
# http://localhost:5173
```

### Build

```bash
npm run build
# Output: dist/
```

### Type Check

```bash
npx tsc --noEmit
```

### Test

```bash
npx vitest run
```

### Deploy

```bash
ssh root@166.88.227.177 "cd /opt/lumine/backend && \
  git pull && \
  docker compose -f docker-compose.vps.yml up -d --build --force-recreate frontend"
```

## 🎨 Styling

### Tailwind + shadcn-ui

```tsx
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';

<Button variant="default">Click me</Button>
<Card>
  <CardHeader>Title</CardHeader>
  <CardContent>Content</CardContent>
</Card>
```

### Theme

```css
/* Using CSS variables for theming */
:root {
  --background: 0 0% 100%;
  --foreground: 222.2 84% 4.9%;
  --primary: 222.2 47.4% 11.2%;
  --accent: 210 40% 96%;
}
```

---

## 🔗 Related

- [[Architecture Overview]] — System design
- [[Backend Architecture]] — API endpoints
- [[MT5 & EA]] — Data source
- [[Deployment Runbook]] — Deploy steps
