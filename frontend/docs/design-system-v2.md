# Lumine Landing Page Design System V2

## DESIGN PHILOSOPHY

**"A living quantitative intelligence instrument"**

NOT: "An AI SaaS landing page"

Visual language combines:
- Modern technical editorial design
- Quantitative terminal aesthetics
- AI laboratory precision
- Premium fintech restraint
- Data visualization clarity
- Experimental but purposeful motion

---

## COLOR SYSTEM (Preserved from V1)

```css
/* Foundations */
--color-abyss: #070b12;      /* near-black base */
--color-bg: #0b0f17;         /* primary surface */
--color-raised: #0f1522;     /* elevated surface */
--color-overlay: #131b2b;    /* modal/dialog */
--color-line: #1c2534;       /* primary border */
--color-line-soft: #151d2b;  /* subtle border */

/* Typography */
--color-ink: #e8eef7;        /* primary text */
--color-ink-dim: #a7b3c5;    /* secondary text */
--color-ink-faint: #6d7c92;  /* tertiary text */

/* Semantic */
--color-accent: #4d8dff;     /* LUMINE signal (electric blue) */
--color-accent-soft: #2f5fb5;
--color-up: #34d399;         /* positive */
--color-down: #f0555b;       /* negative */
--color-warn: #ffb020;       /* warning */
--color-cyan: #22d3ee;       /* info */
```

**Accent Philosophy:**
- `#4d8dff` represents intelligence/signal/light
- Use SPARINGLY — only for:
  - System status indicators
  - Active nodes in intelligence network
  - Primary CTAs
  - Data points requiring attention
- When accent appears, it should be **meaningful**

---

## TYPOGRAPHY SYSTEM

### Font Stack (Preserved)
```css
--font-sans: "Inter Variable"     /* body, UI */
--font-display: "Archivo Variable" /* headlines */
--font-mono: "IBM Plex Mono"      /* telemetry, code, metrics */
```

### Type Scale (NEW)

```css
/* Display — Large editorial typography */
--text-display-xl: 72px/1.1  /* Hero main headline */
--text-display-lg: 56px/1.1  /* Section hero headlines */
--text-display-md: 40px/1.2  /* Subsection headlines */

/* Editorial — Medium explanatory */
--text-editorial-lg: 24px/1.4
--text-editorial-md: 18px/1.5
--text-editorial-sm: 16px/1.6

/* Technical — Monospace telemetry */
--text-technical-lg: 14px/1.4
--text-technical-md: 12px/1.5
--text-technical-sm: 10px/1.6

/* UI — Interface elements */
--text-ui-lg: 16px/1.5
--text-ui-md: 14px/1.5
--text-ui-sm: 12px/1.5
--text-ui-xs: 11px/1.5
```

### Typography Hierarchy Rules

1. **Display headlines** — use `font-display`, bold (600-700), tight tracking (-0.02em)
2. **Editorial copy** — use `font-sans`, regular (400), relaxed line-height (1.6)
3. **Technical labels** — use `font-mono`, medium (500), uppercase, wide tracking (0.1em)
4. **Metrics/data** — use `font-mono`, regular/medium, tabular-nums

---

## SPACING SYSTEM

```css
/* Rhythm scale */
--space-1: 4px
--space-2: 8px
--space-3: 12px
--space-4: 16px
--space-5: 20px
--space-6: 24px
--space-8: 32px
--space-10: 40px
--space-12: 48px
--space-16: 64px
--space-20: 80px
--space-24: 96px
--space-32: 128px
--space-40: 160px
--space-48: 192px

/* Section rhythm */
--section-padding-mobile: 60px
--section-padding-tablet: 80px
--section-padding-desktop: 120px
```

---

## MOTION LANGUAGE

### Principles
1. **Motion = Meaning** — animation must communicate, not decorate
2. **Performance First** — all animations GPU-accelerated (transform, opacity)
3. **Subtle > Flashy** — prefer 200-400ms over 800ms+
4. **Respect Accessibility** — honor `prefers-reduced-motion`

### Duration Scale
```css
--motion-instant: 100ms   /* hover feedback */
--motion-fast: 200ms      /* UI transitions */
--motion-normal: 400ms    /* section reveals */
--motion-slow: 600ms      /* hero sequences */
--motion-deliberate: 800ms /* major state changes */
```

### Easing Curves
```css
--ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);     /* smooth decel */
--ease-in-out-quad: cubic-bezier(0.45, 0, 0.55, 1); /* balanced */
--ease-spring: cubic-bezier(0.68, -0.55, 0.265, 1.55); /* subtle bounce */
```

### Animation Hierarchy

**Hover (instant, 100-200ms)**
- Button states
- Card hover
- Node hover
- Link underlines

**Enter (200-400ms)**
- Section reveals on scroll
- Modal/dialog open
- Tooltip appear
- Component mount

**Exit (150-250ms)**
- Modal close
- Tooltip disappear
- Component unmount

**Sequence (400-1200ms)**
- Hero intelligence network activation
- Risk validation steps
- Research pipeline progression
- Architecture layer reveals

---

## INTERACTION PATTERNS

### 1. Hero Intelligence Network (NEW)

**Concept:** Interactive 4-agent constellation feeding into Lumine core

**States:**
- **Idle** — agents pulse subtly (1s interval), connections dim
- **Hover Agent** — highlighted agent scales 1.1x, connection brightens, other agents dim 0.6 opacity
- **Hover Core** — all connections brighten, agents sync pulse
- **Click Agent** — open Dialog with agent details

**Implementation:**
```tsx
// Framer Motion spring physics
const springConfig = { stiffness: 300, damping: 30 };

// Agent node
<motion.div
  whileHover={{ scale: 1.1 }}
  transition={{ type: "spring", ...springConfig }}
/>

// Pulsing connection line
<motion.path
  animate={{ 
    opacity: [0.2, 0.6, 0.2],
    pathLength: [0, 1] 
  }}
  transition={{ 
    duration: 2, 
    repeat: Infinity,
    ease: "easeInOut" 
  }}
/>
```

### 2. Risk Validation Sequence (NEW)

**Concept:** Animated checklist showing AI proposal → Risk gates → Approval

**Animation:**
```
AI PROPOSAL
     ↓ (200ms delay)
✓ EXPOSURE CHECK (fade in + checkmark)
     ↓ (200ms delay)
✓ VOLATILITY CHECK
     ↓ (200ms delay)
✓ DRAWDOWN CHECK
     ↓ (200ms delay)
✓ NEWS RISK CHECK
     ↓ (200ms delay)
APPROVED (green glow)
```

### 3. Terminal Audit Stream (NEW)

**Concept:** Simulated live trade decision stream (like htop/terminal logs)

**Animation:**
- New log entries slide up from bottom
- Typewriter effect for timestamps
- Color-coded by log level (TECHNICAL=cyan, MACRO=blue, MASTER=accent, RISK=green)
- Auto-scroll with pause/resume button

### 4. Scroll-Driven Transitions (NEW)

Use Framer Motion `useScroll` + `useTransform` for:

**Hero → Intelligence transition:**
```tsx
const { scrollYProgress } = useScroll();
const opacity = useTransform(scrollYProgress, [0, 0.2], [1, 0]);
const scale = useTransform(scrollYProgress, [0, 0.2], [1, 1.1]);
```

**Section reveals:**
- Fade in from `opacity: 0 → 1`
- Slide up `translateY: 20px → 0`
- Trigger when section enters viewport (IntersectionObserver)

---

## COMPONENT REDESIGNS

### NavBar (Enhanced)

**Changes:**
- Add system status: `● SYSTEM ONLINE` in top-right (animate pulse)
- Navbar becomes denser on scroll (h-14 → h-12)
- Add subtle backdrop blur increase on scroll

### Hero (Complete Rebuild)

**Layout:** Asymmetric composition

```
┌─────────────────────────────────────┐
│  SYSTEM STATUS OVERLAY (top-right)  │
│                                      │
│                                      │
│     AI-Native                        │
│     Quantitative                  ●  │← TECH
│     Intelligence.              ╱     │
│                            CORE      │
│                              ╲       │
│  [interactive network]      ●       │← MACRO
│                                      │
│  [CTA buttons]                       │
└─────────────────────────────────────┘
```

**Interactive Network:**
- 4 agent nodes positioned in cross formation
- Lumine core in center
- Animated connection lines
- Hover states on agents
- Click opens Dialog with agent details

### Section Layouts (Varied Rhythm)

**Before (all identical):**
```
Section 1: Card
Section 2: Card
Section 3: Card
```

**After (varied):**
```
Section 1: Full-width visual field (Hero)
Section 2: Asymmetric two-column (Intelligence)
Section 3: Centered focused (Master Decision)
Section 4: Full-width dark panel (Risk Engine)
Section 5: Horizontal scroll timeline (Research)
Section 6: Dense data grid (Performance)
Section 7: Minimal typography-only (Philosophy)
```

---

## COMPONENT LIBRARY

### Interactive Agent Node

```tsx
<motion.div
  whileHover={{ scale: 1.1 }}
  whileTap={{ scale: 0.95 }}
  onClick={() => setSelectedAgent(agent)}
  className="cursor-pointer"
>
  <AgentIcon />
  <AgentLabel />
</motion.div>
```

### Animated Connection Line (SVG)

```tsx
<svg>
  <motion.line
    x1={from.x} y1={from.y}
    x2={to.x} y2={to.y}
    stroke="var(--color-accent)"
    strokeWidth={2}
    animate={{ opacity: [0.2, 0.6, 0.2] }}
    transition={{ duration: 2, repeat: Infinity }}
  />
</svg>
```

### Scroll Reveal Section

```tsx
<motion.section
  initial={{ opacity: 0, y: 20 }}
  whileInView={{ opacity: 1, y: 0 }}
  viewport={{ once: true, margin: "-100px" }}
  transition={{ duration: 0.6 }}
>
  {children}
</motion.section>
```

### Terminal Log Stream

```tsx
<div className="font-mono text-sm overflow-auto max-h-[400px]">
  {logs.map((log, i) => (
    <motion.div
      key={log.id}
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: i * 0.05 }}
      className="text-ink-dim"
    >
      <span className="text-ink-faint">{log.timestamp}</span>
      <span className={`ml-4 text-${log.color}`}>{log.message}</span>
    </motion.div>
  ))}
</div>
```

---

## ANTI-PATTERNS (Forbidden)

❌ **Generic card syndrome** — not everything is a card
❌ **Purple/blue AI glow** — accent is electric blue, use sparingly
❌ **Excessive glassmorphism** — use backdrop-blur only where needed
❌ **Fake dashboard mockups** — use real data or clearly labeled simulations
❌ **Random floating particles** — motion must be meaningful
❌ **Giant centered headlines everywhere** — vary typography rhythm
❌ **Repetitive 3-column grids** — alternate layout patterns

---

## RESPONSIVE STRATEGY

### Breakpoints
```css
--breakpoint-sm: 640px
--breakpoint-md: 768px
--breakpoint-lg: 1024px
--breakpoint-xl: 1280px
--breakpoint-2xl: 1536px
```

### Mobile Adaptations

**Hero Network:**
- Desktop: 4 agents in cross formation around core
- Mobile: Vertical stack with simplified connections

**Risk Validation:**
- Desktop: Horizontal flow diagram
- Mobile: Vertical checklist

**Performance Dashboard:**
- Desktop: 4-column grid
- Mobile: 2-column grid or carousel

**Philosophy Typography:**
- Desktop: 72px display text
- Mobile: 40px display text

---

## PERFORMANCE BUDGET

**Animation Performance:**
- All animations use `transform` and `opacity` (GPU-accelerated)
- Avoid `height`, `width`, `top`, `left` animations
- Use `will-change` sparingly (only during active animation)
- Lazy load heavy components below fold
- Use `IntersectionObserver` to trigger scroll animations

**Bundle Size:**
- Framer Motion: ~50KB gzipped (acceptable for landing page)
- Total JS budget: <300KB gzipped
- Total CSS budget: <50KB gzipped

**Lighthouse Targets:**
- Performance: >90
- Accessibility: >95
- Best Practices: >95
- SEO: >95

---

## IMPLEMENTATION PHASES

### Phase 1: Foundation
- ✅ Install Framer Motion
- ✅ Define motion language
- ✅ Create animation primitives

### Phase 2: Hero Rebuild
- Interactive intelligence network
- Asymmetric typography layout
- Scroll transition to next section

### Phase 3: Section Enhancements
- Risk validation sequence animation
- Terminal audit stream
- Scroll-reveal animations

### Phase 4: Polish
- Hover states on all interactive elements
- Focus states for accessibility
- Reduce motion fallbacks
- Performance optimization

---

## VISUAL QUALITY BAR

Before considering done, verify:

1. ✅ **No generic cards** — varied section layouts
2. ✅ **Interactive hero** — network responds to hover/click
3. ✅ **Meaningful motion** — every animation communicates something
4. ✅ **Varied rhythm** — dense → sparse → editorial → technical
5. ✅ **Distinctive identity** — doesn't look like 500 other AI startups
6. ✅ **Performance** — 60fps animations, <300ms interaction response
7. ✅ **Accessibility** — keyboard nav, focus states, reduced-motion support

---

Generated: 2026-08-15
Version: V2.0
Status: Design System Complete — Ready for Implementation
