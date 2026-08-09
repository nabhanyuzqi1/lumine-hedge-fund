export default function Mark({ compact = false }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true">
        <rect width="32" height="32" rx="6" fill="var(--color-raised)" />
        <path
          d="M6 22 L13 10 L17 17 L21 8 L27 22"
          fill="none"
          stroke="var(--color-accent)"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="21" cy="8" r="1.8" fill="var(--color-up)" />
      </svg>
      {!compact && (
        <span className="font-display text-[15px] font-700 tracking-[0.18em] uppercase text-ink">
          Lumine
        </span>
      )}
    </span>
  );
}
