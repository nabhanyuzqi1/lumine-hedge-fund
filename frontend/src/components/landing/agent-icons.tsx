/**
 * Agent Icon SVG Components
 * 
 * Institutional-grade SVG icons untuk Lumine intelligence agents.
 * Minimalist, geometric, dan konsisten dengan brand identity.
 */

interface IconProps {
  className?: string;
  size?: number;
}

/**
 * Technical Intelligence Icon
 * Represents: charts, trends, momentum analysis
 */
export function TechnicalIcon({ className, size = 24 }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <path
        d="M3 17L9 11L13 15L21 7"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M21 7H16M21 7V12"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M7 21V12M12 21V8M17 21V16"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * Macro Intelligence Icon
 * Represents: global economics, rates, monetary policy
 */
export function MacroIcon({ className, size = 24 }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        stroke="currentColor"
        strokeWidth="2"
      />
      <path
        d="M12 3C12 3 8 7 8 12C8 17 12 21 12 21"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M12 3C12 3 16 7 16 12C16 17 12 21 12 21"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M3 12H21"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M5 8H19"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M5 16H19"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

/**
 * News Intelligence Icon
 * Represents: market-moving events, sentiment, news flow
 */
export function NewsIcon({ className, size = 24 }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <rect
        x="3"
        y="5"
        width="18"
        height="16"
        rx="2"
        stroke="currentColor"
        strokeWidth="2"
      />
      <path
        d="M3 9H21"
        stroke="currentColor"
        strokeWidth="2"
      />
      <path
        d="M7 13H11M7 16H17"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <rect
        x="14"
        y="12"
        width="4"
        height="5"
        stroke="currentColor"
        strokeWidth="2"
      />
    </svg>
  );
}

/**
 * Market Structure Icon
 * Represents: liquidity, support/resistance, order flow
 */
export function StructureIcon({ className, size = 24 }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <path
        d="M3 21V12L12 3L21 12V21"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M9 21V15H15V21"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M9 9H10M14 9H15"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

/**
 * Lumine Mark — v3 "Lux" (filosofi cahaya).
 * LUMINE (Latin) = light. Komposisi:
 *  - Core radiant di tengah: inti cahaya dengan 4 sinar pendek
 *    (flare) — intelligence yang memancar ke semua arah.
 *  - Orbit ring putus-putus: cahaya/pengetahuan dalam sistem
 *    yang terkandung, terus berputar.
 *  - Ascending signal ke kanan-atas: arah, pertumbuhan, sinyal
 *    yang keluar dari sistem menuju tujuan.
 * Signal head emerald = titik eksekusi/realisasi.
 */
export function LumineIcon({ className, size = 24 }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      {/* Orbit ring (dashed → perpetual motion) */}
      <circle
        cx="16"
        cy="16"
        r="13.5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeDasharray="62 23"
        strokeLinecap="round"
        opacity="0.45"
      />
      {/* Core halo */}
      <circle cx="16" cy="16" r="8.5" stroke="currentColor" strokeWidth="0.8" opacity="0.25" />
      {/* Core radiant — 4 sinar (flare) */}
      <g stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" opacity="0.8">
        <path d="M16 8.2 V5.5" />
        <path d="M16 23.8 V26.5" />
        <path d="M8.2 16 H5.5" />
        <path d="M23.8 16 H26.5" />
      </g>
      {/* Core */}
      <circle cx="16" cy="16" r="3.4" fill="currentColor" />
      {/* Ascending signal */}
      <path
        d="M4.5 23.5 L10 18 L14 21 L19.5 12.5 L24 9"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Signal head */}
      <circle cx="24" cy="9" r="2.6" fill="currentColor" />
    </svg>
  );
}
