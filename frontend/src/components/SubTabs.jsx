import '../styles/subtabs.css';

/**
 * Sub-tab bersih untuk halaman gabungan.
 * tabs: [{ id, label, count? }]
 */
export default function SubTabs({ tabs, value, onChange, ariaLabel = 'Sub-tab' }) {
  return (
    <div className="subtabs" role="tablist" aria-label={ariaLabel}>
      {tabs.map((t) => {
        const active = t.id === value;
        return (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={active}
            className={`subtab${active ? ' is-active' : ''}`}
            onClick={() => onChange(t.id)}
          >
            {t.label}
            {typeof t.count === 'number' && t.count > 0 && (
              <span className="subtab-count">{t.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
