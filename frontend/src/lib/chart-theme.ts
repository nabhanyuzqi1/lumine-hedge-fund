/**
 * Chart theme — maps Lumine design tokens (docs/10-frontend/design-tokens.md,
 * defined as CSS custom properties in src/index.css) onto lightweight-charts
 * and ECharts option objects.
 *
 * Colors are read live from `getComputedStyle` so a theme change in CSS
 * propagates without recompiling; the constants below are the fallbacks used
 * in jsdom (tests) and when a token is missing.
 */
import { type ChartOptions, ColorType, CrosshairMode, type DeepPartial } from "lightweight-charts";

export const CHART_COLORS = {
  up: "#34d399",
  down: "#f0555b",
  accent: "#4d8dff",
  warn: "#ffb020",
  cyan: "#22d3ee",
  grid: "#151d2b",
  crosshair: "#2b3a52",
  text: "#a7b3c5",
  textStrong: "#e8eef7",
  faint: "#6d7c92",
  border: "#1c2534",
} as const;

export const CHART_FONTS = {
  family: "'Inter', ui-sans-serif, system-ui, sans-serif",
  mono: "'IBM Plex Mono', ui-monospace, 'SFMono-Regular', monospace",
} as const;

const TOKEN_TO_FALLBACK: Record<string, string> = {
  "--color-up": CHART_COLORS.up,
  "--color-down": CHART_COLORS.down,
  "--color-accent": CHART_COLORS.accent,
  "--color-warn": CHART_COLORS.warn,
  "--color-cyan": CHART_COLORS.cyan,
  "--color-line-soft": CHART_COLORS.grid,
  "--color-line": CHART_COLORS.border,
  "--color-ink": CHART_COLORS.textStrong,
  "--color-ink-dim": CHART_COLORS.text,
  "--color-ink-faint": CHART_COLORS.faint,
};

export function readCssVar(name: string, fallback: string): string {
  if (typeof document === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value.length > 0 ? value : fallback;
}

export function getChartColors(): Record<keyof typeof CHART_COLORS, string> {
  const resolved = { ...CHART_COLORS } as Record<keyof typeof CHART_COLORS, string>;
  for (const [token, fallback] of Object.entries(TOKEN_TO_FALLBACK)) {
    const value = readCssVar(token, fallback);
    if (token === "--color-up") resolved.up = value;
    if (token === "--color-down") resolved.down = value;
    if (token === "--color-accent") resolved.accent = value;
    if (token === "--color-warn") resolved.warn = value;
    if (token === "--color-cyan") resolved.cyan = value;
    if (token === "--color-line-soft") resolved.grid = value;
    if (token === "--color-line") resolved.border = value;
    if (token === "--color-ink") resolved.textStrong = value;
    if (token === "--color-ink-dim") resolved.text = value;
    if (token === "--color-ink-faint") resolved.faint = value;
  }
  return resolved;
}

/** Format helper shared by price scales — gold trades in 2 decimals. */
export function formatPrice(value: number): string {
  return value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/**
 * Base lightweight-charts options for every Lumine pane: transparent
 * background, mono tabular labels, subtle grid, crosshair with raised label
 * chip. Components extend this with series-specific options.
 */
export function buildLwcOptions(): DeepPartial<ChartOptions> {
  const colors = getChartColors();
  return {
    layout: {
      background: { type: ColorType.Solid, color: "transparent" },
      textColor: colors.text,
      fontFamily: CHART_FONTS.mono,
      fontSize: 11,
    },
    grid: {
      vertLines: { color: colors.grid },
      horzLines: { color: colors.grid },
    },
    crosshair: {
      mode: CrosshairMode.Normal,
      vertLine: { color: colors.crosshair, labelBackgroundColor: colors.accent, width: 1 },
      horzLine: { color: colors.crosshair, labelBackgroundColor: colors.accent, width: 1 },
    },
    rightPriceScale: { borderColor: colors.border },
    timeScale: { borderColor: colors.border, timeVisible: true, secondsVisible: false },
    localization: { locale: "en-US", priceFormatter: formatPrice },
  };
}

/** ECharts theme object — passed straight to `echarts.init(el, theme)`. */
export function buildEchartsTheme(): Record<string, unknown> {
  const colors = getChartColors();
  return {
    color: [colors.accent, colors.up, colors.down, colors.warn, colors.cyan, colors.text],
    backgroundColor: "transparent",
    textStyle: {
      fontFamily: CHART_FONTS.family,
      fontSize: 11,
      color: colors.text,
    },
    categoryAxis: {
      axisLine: { lineStyle: { color: colors.border } },
      axisLabel: { color: colors.faint, fontFamily: CHART_FONTS.mono },
      splitLine: { show: false },
    },
    valueAxis: {
      axisLine: { show: false },
      axisLabel: { color: colors.faint, fontFamily: CHART_FONTS.mono },
      splitLine: { lineStyle: { color: colors.grid } },
    },
    tooltip: {
      backgroundColor: "rgba(11, 15, 23, 0.95)",
      borderColor: colors.border,
      textStyle: { color: colors.textStrong, fontFamily: CHART_FONTS.mono, fontSize: 11 },
    },
  };
}
