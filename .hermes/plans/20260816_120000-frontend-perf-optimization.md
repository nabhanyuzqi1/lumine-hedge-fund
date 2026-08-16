# Frontend Performance Optimization Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Optimalkan performa frontend Lumine dengan lazy loading translations, skeleton loaders, dan code splitting — tanpa mengubah fungsi core yang sudah ada.

**Architecture:** 
- i18next dengan dynamic import untuk bahasa (hanya load bahasa yang dipilih)
- React.lazy + Suspense untuk page/component lazy loading
- Skeleton components dengan shimmer effect untuk loading states
- Optimasi bundle size dengan dynamic imports

**Tech Stack:** React 19, Vite, react-i18next, framer-motion, Tailwind CSS v4

---

## Task List (Bite-sized, 2-5 min each)

### Phase 1: Lazy Loading Translations (i18n Optimization)

#### Task 1: Ubah i18n config ke lazy loading

**Objective:** translations Bahasa Indonesia dan English di-load secara dynamic, tidak semuanya sekaligus

**Files:**
- Modify: `frontend/src/i18n/index.ts`

**Step 1: Update i18n config**

```typescript
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";

// Hapus import static:
// import en from "./locales/en.json";
// import id from "./locales/id.json";

// Gunakan lazy loading
const resources = {
  en: () => import("./locales/en.json"),
  id: () => import("./locales/id.json"),
};

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: { /* embed minimal default keys */ } },
      id: { translation: { /* embed minimal default keys */ } }
    },
    fallbackLng: "en",
    supportedLngs: ["en", "id"],
    interpolation: { escapeValue: false },
    detection: {
      order: ["localStorage", "navigator"],
      caches: ["localStorage"],
    },
    // Tambahkan lazy load
    ns: ["translation"],
    defaultNS: "translation",
  });

// Lazy load bahasa lengkap saat dibutuhkan
export const loadLanguage = async (lang: string) => {
  if (i18n.hasResourceBundle(lang, "translation")) return;
  
  const translations = await resources[lang as keyof typeof resources]();
  i18n.addResourceBundle(lang, "translation", translations.default || translations);
};

export default i18n;
```

**Step 2: Update LanguageSwitcher untuk load bahasa on-demand**

```typescript
// Di frontend/src/components/language-switcher.tsx
import { useTranslation } from "react-i18next";
import { loadLanguage } from "@/i18n";

const handleLanguageChange = async (langCode: string) => {
  await loadLanguage(langCode);
  i18n.changeLanguage(langCode);
};
```

**Verification:** 
```bash
# Build dan cek network tab untuk lihat bahasa di-load terpisah
npm run build
```

---

### Phase 2: Skeleton Loader dengan Shimmer Effect

#### Task 2: Buat BaseSkeleton component dengan shimmer

**Objective:** Buat reusable skeleton component dengan shimmer animation

**Files:**
- Create: `frontend/src/components/ui/skeleton.tsx`

**Step 1: Write skeleton component**

```tsx
import { cn } from "@/lib/utils";

interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-md bg-line/50",
        "bg-gradient-to-r from-line/20 via-line/40 to-line/20",
        "bg-[length:200%_100%] animate-shimmer",
        className
      )}
    />
  );
}

// Skeleton variants untuk common layouts
export function CardSkeleton() {
  return (
    <div className="rounded-panel border border-line bg-raised p-4 space-y-3">
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="h-8 w-2/3" />
      <Skeleton className="h-4 w-full" />
    </div>
  );
}

export function InputSkeleton() {
  return (
    <div className="space-y-1.5">
      <Skeleton className="h-3 w-20" />
      <Skeleton className="h-10 w-full" />
    </div>
  );
}

export function ButtonSkeleton() {
  return <Skeleton className="h-9 w-24 rounded-chip" />;
}
```

**Step 2: Tambahkan shimmer animation ke CSS**

```css
/* Di frontend/src/index.css */
@theme {
  --animate-shimmer: shimmer 1.5s ease-in-out infinite;
}

@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
```

**Step 3: Verify**
```bash
npm run build
```

#### Task 3: Update Landing Page dengan skeleton states

**Objective:** Tambah loading skeleton di komponen-komponen yang heavy

**Files:**
- Modify: `frontend/src/app/pages/landing-public.tsx`

**Step 1: Wrap heavy components dengan Suspense + Skeleton**

```tsx
import { Suspense, lazy } from "react";
import { Skeleton, CardSkeleton } from "@/components/ui/skeleton";

// Lazy load komponen yang berat
const PerformanceDashboard = lazy(() => 
  import("@/components/landing/performance-dashboard").then(m => ({ default: m.PerformanceDashboard }))
);

// Loading skeleton
function SectionLoader() {
  return (
    <div className="space-y-4 py-12">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-10 w-1/2" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

// Ganti import static dengan lazy + Suspense
// Gunakan Suspense di section yangheavy
export function LandingPage() {
  return (
    // ...
    <Suspense fallback={<SectionLoader />}>
      <PerformanceDashboard />
    </Suspense>
    // ...
  );
}
```

---

### Phase 3: Route-based Code Splitting

#### Task 4: Setup React.lazy untuk pages

**Objective:** Setiap page di-load hanya saat dibutuhkan

**Files:**
- Modify: `frontend/src/app/router.tsx`

**Step 1: Update router dengan lazy loading**

```tsx
import { createBrowserRouter, defer } from "react-router-dom";

// Hapus import static:
// import { LandingPage } from "./pages/landing-public";
// import { LoginPage } from "./pages/login";

// Lazy load pages
const LandingPage = lazy(() => import("./pages/landing-public").then(m => ({ default: m.LandingPage || m.LoginPage })));
// Note: adjust berdasarkan exports yang ada

// Untuk routes yang butuh auth
const DashboardPage = lazy(() => 
  import("./pages/dashboard").then(m => ({ default: m.DashboardPage }))
);

const router = createBrowserRouter([
  {
    path: "/",
    element: (
      <Suspense fallback={<div className="min-h-screen bg-abyss flex items-center justify-center"><Skeleton className="h-96 w-full max-w-4xl" /></div>}>
        <LandingPage />
      </Suspense>
    ),
  },
  {
    path: "/login",
    element: (
      <Suspense fallback={<Skeleton className="min-h-screen" />}>
        <LoginPage />
      </Suspense>
    ),
  },
  // ... route lain
]);

export { router };
```

**Step 2: Verify**
```bash
npm run build
# Cek output: harusnya ada chunk terpisah per page
```

---

### Phase 4: Component Lazy Loading

#### Task 5: Lazy load heavy components di Landing Page

**Objective:** Komponen visual berat (charts, visualizations) di-load on-demand

**Files:**
- Modify: `frontend/src/app/pages/landing-public.tsx`

**Step 1: Identify dan lazy load heavy components**

```tsx
// Sebelum (static import - load semua sekaligus):
import { IntelligenceField } from "@/components/landing/intelligence-field";
import { EquityCurve } from "@/components/landing/equity-curve";
// dst...

// Sesudah (lazy load - load hanya saat visible):
const IntelligenceField = lazy(() => 
  import("@/components/landing/intelligence-field").then(m => ({ default: m.IntelligenceField }))
);

const EquityCurve = lazy(() => 
  import("@/components/landing/equity-curve").then(m => ({ default: m.EquityCurve }))
);

// ... untuk semua komponen heavy
```

**Step 2: Wrap dengan Suspense**

```tsx
function HeroSection() {
  return (
    <Suspense fallback={<Skeleton className="h-[600px] w-full" />}>
      <IntelligenceField />
    </Suspense>
  );
}
```

---

### Phase 5: Image dan Asset Optimization

#### Task 6: Optimasi assets

**Objective:** Pastikan assets di-load secara optimal

**Files:**
- Modify: `frontend/vite.config.ts`
- Create: `frontend/public/` assets jika perlu

**Step 1: Check vite config untuk optimasi**

```ts
// Di vite.config.ts sudah ada:
// - build.target: esnext
// - rollupOptions.output.manualChunks

// Tambahkan untuk optimal:
export default defineConfig({
  build: {
    target: "esnext",
    minify: "esbuild",
    rollupOptions: {
      output: {
        manualChunks: {
          // Pisahkan vendor chunks
          "vendor-react": ["react", "react-dom"],
          "vendor-ui": ["@radix-ui/react-dialog", "@radix-ui/react-dropdown-menu"],
          "vendor-charts": ["echarts", "lightweight-charts"],
          "vendor-motion": ["framer-motion"],
        },
      },
    },
    chunkSizeWarningLimit: 500,
  },
});
```

---

### Phase 6: Loading States untuk Login Page

#### Task 7: Tambah skeleton di Login Page

**Objective:** Login page ada loading state yang smooth

**Files:**
- Modify: `frontend/src/app/pages/login.tsx`

**Step 1: Add loading skeleton**

```tsx
function LoginPageSkeleton() {
  return (
    <div className="min-h-screen bg-abyss flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="rounded-panel border border-line bg-raised/70 p-6">
          <div className="space-y-4">
            <InputSkeleton />
            <InputSkeleton />
            <ButtonSkeleton />
          </div>
        </div>
      </div>
    </div>
  );
}

// Wrap dengan Suspense di router atau gunakan saat loading
```

---

## Summary of Changes

| Phase | Task | Files Changed |
|-------|------|---------------|
| 1 | Lazy i18n | `src/i18n/index.ts`, `src/components/language-switcher.tsx` |
| 2 | Skeleton components | Create `src/components/ui/skeleton.tsx`, modify `index.css` |
| 3 | Route splitting | `src/app/router.tsx` |
| 4 | Component lazy load | `src/app/pages/landing-public.tsx` |
| 5 | Asset optimization | `vite.config.ts` (sudah ada, review) |
| 6 | Login skeleton | `src/app/pages/login.tsx` |

## Verification Commands

```bash
# Build dan lihat chunk sizes
npm run build

# Preview production build
npm run preview

# Check performance di DevTools:
# 1. Network tab - harus ada chunk terpisah untuk setiap bahasa
# 2. Coverage - harusnya banyak code di-load on-demand
# 3. Lighthouse - target: Performance > 90
```

## Expected Results

- **Initial bundle reduction:** ~40-60% (bahasa tidak di-load semua)
- **LCP improvement:** < 2.5s
- **TTFP (Time to First Paint):** < 1s
- **User experience:** Smooth skeleton shimmer selama loading

## Risks & Tradeoffs

- **Risk:** Lazy loading bisa cause flash of unstyled content (FOUC)
- **Mitigation:** Gunakan Suspense dengan meaningful skeleton
- **Tradeoff:** Pertama kali切换 bahasa akan ada slight delay
- **Mitigation:** Preload bahasa yang paling sering digunakan (fallback ke navigator language)

---

**Plan complete. Ready to execute using subagent-driven-development — I'll dispatch a fresh subagent per task with two-stage review (spec compliance then code quality). Shall I proceed?**