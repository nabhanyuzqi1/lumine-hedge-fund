import * as React from "react";

/**
 * InfoHint (18 Aug 2026) — user request: "penjelasan ditaruh di tabel tapi
 * ikon tanda tanya di pojok tabel biar ga rame". Tooltip ringkas per kolom/
 * elemen; penjelasan panjang tidak memenuhi UI.
 */
export function InfoHint({
  text,
  label,
}: {
  text: string;
  label?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLSpanElement>(null);

  React.useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  return (
    <span ref={ref} className="relative inline-flex items-center">
      <button
        type="button"
        aria-label={`Info: ${text}`}
        title={label ?? text}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        className="ml-1 inline-flex h-3.5 w-3.5 items-center justify-center rounded-full border border-line bg-bg-raised font-mono text-[9px] leading-none text-ink-faint hover:text-ink"
      >
        ?
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute left-0 top-full z-50 mt-1 w-56 rounded-chip border border-line bg-bg-raised px-2.5 py-2 text-[11px] leading-relaxed text-ink-dim shadow-lg"
        >
          {text}
        </span>
      )}
    </span>
  );
}

/** Header penolong: label + InfoHint di sampingnya (pojok tabel). */
export function HintHeader({ label, hint }: { label: string; hint: string }) {
  return (
    <span className="inline-flex items-center whitespace-nowrap">
      {label}
      <InfoHint text={hint} label={hint} />
    </span>
  );
}