/**
 * BackgroundTexture — global ambient texture layer for the landing page.
 *
 * Layered, theme-aware, pointer-events-none. Sits behind all page content
 * (z-0) so sections stay readable while the background stops feeling flat:
 *   - fine grid        (trading-terminal blueprint feel)
 *   - dot matrix       (subtle technical depth)
 *   - film grain noise (SVG turbulence, data-URI)
 *   - scanlines        (very subtle CRT cadence)
 *   - accent glows     (electric blue / cyan ambience)
 *   - HUD glyphs       (sparse mono fragments — pairs, coords, status)
 *
 * All layers use theme CSS variables, so dark mode stays deep-navy and
 * light mode stays soft without extra JS.
 */

const HUD_GLYPHS: Array<{ text: string; className: string }> = [
  { text: "XAU/USD · 24.31 · Δ+0.42%", className: "left-[6%] top-[18%]" },
  { text: "HFT-42 ▸ PIPELINE ACTIVE", className: "right-[7%] top-[30%]" },
  { text: "52.3516°N, 4.9053°E", className: "left-[8%] bottom-[24%]" },
  { text: "EUR/USD · 1.0842", className: "right-[9%] bottom-[14%]" },
  { text: "LAT 12.4ms · SRC 3/3", className: "left-[14%] top-[48%]" },
];

export function BackgroundTexture() {
  return (
    <div
      aria-hidden="true"
      className="lumine-texture pointer-events-none fixed inset-0 z-0 overflow-hidden"
    >
      {/* Fine blueprint grid */}
      <div className="lumine-texture-grid absolute inset-0" />

      {/* Dot matrix */}
      <div className="lumine-texture-dots absolute inset-0" />

      {/* Film grain noise */}
      <div className="lumine-texture-noise absolute inset-0" />

      {/* Scanlines */}
      <div className="lumine-texture-scanlines absolute inset-0" />

      {/* Accent glows */}
      <div className="absolute -top-32 left-1/4 h-[480px] w-[680px] rounded-full bg-accent/[0.05] blur-[140px]" />
      <div className="absolute -right-24 top-1/3 h-[420px] w-[420px] rounded-full bg-cyan/[0.04] blur-[120px]" />
      <div className="absolute -left-32 bottom-0 h-[380px] w-[520px] rounded-full bg-accent/[0.04] blur-[130px]" />

      {/* Sparse HUD glyphs */}
      <div className="absolute inset-0 hidden lg:block">
        {HUD_GLYPHS.map((g) => (
          <span
            key={g.text}
            className={`lumine-texture-glyph absolute font-mono text-[9px] uppercase tracking-[0.25em] ${g.className}`}
          >
            {g.text}
          </span>
        ))}
      </div>
    </div>
  );
}