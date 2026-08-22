import { useLocation, useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";

/**
 * ResearchWorkspaceSwitcher (22 Aug 2026) — tab yang jelas antar dua view
 * di workspace Research:
 *   • /app/dashboard → Portfolio Dashboard (equity, drawdown, exposure,
 *     signals, allocation, correlation — pandangan portfolio secara umum)
 *   • /app/research  → Research Lab (paper vs real comparison, insight,
 *     performa per-book)
 * User feedback: "tidak ada route jelas, akses jelas, switcher jelas antar
 * 2 pages" — komponen ini menyediakan navigasi eksplisit di kedua halaman.
 */
export function ResearchWorkspaceSwitcher() {
  const location = useLocation();
  const navigate = useNavigate();

  const tabs = [
    { path: "/app/dashboard", label: "Portfolio Dashboard", desc: "Equity · drawdown · exposure · signals" },
    { path: "/app/research", label: "Research Lab", desc: "Paper vs Real · insight performa" },
  ];

  const active = tabs.find((t) => location.pathname.startsWith(t.path))?.path ?? tabs[0].path;

  return (
    <div className="flex flex-wrap items-center gap-1 rounded-chip border border-line bg-raised p-1" role="tablist" aria-label="Research workspace views">
      {tabs.map((tab) => {
        const isActive = active === tab.path;
        return (
          <button
            key={tab.path}
            role="tab"
            aria-selected={isActive}
            onClick={() => navigate(tab.path)}
            className={cn(
              "rounded-chip px-3 py-1.5 text-left transition-colors",
              isActive
                ? "bg-accent/15 text-accent shadow-[inset_0_0_0_1px_var(--color-accent)/40]"
                : "text-ink-faint hover:bg-raised hover:text-ink-dim"
            )}
          >
            <span className="block text-xs font-medium">{tab.label}</span>
            <span className="block text-[10px] text-ink-faint">{tab.desc}</span>
          </button>
        );
      })}
    </div>
  );
}
