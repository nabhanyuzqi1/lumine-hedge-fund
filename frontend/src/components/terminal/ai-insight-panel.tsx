import { useSignals } from "@/api/hooks";
import { AnalystCard } from "@/components/dashboard/analyst-card";
import type { SignalPoint } from "@/data/fixtures";

/**
 * AIInsightPanel (18 Aug 2026) — jawaban user: "AI lebih jelas menganalisa,
 * bullish/volatility/news/calendar/plan, apa arti confidence, bar minimum
 * eksekusi". Menampilkan sinyal analyst REAL (dari DB signals, di-persist
 * worker tiap decision cycle): direction (bullish/bearish/neutral),
 * confidence, rationale — plus penjelasan threshold eksekusi.
 */
export function AIInsightPanel({ symbol }: { symbol: string }) {
  const { data: signals = [], isLoading } = useSignals(symbol);
  // Decision cycle tiap 5 menit — sinyal terbaru di atas.
  const sorted = [...signals].sort((a, b) => b.time - a.time).slice(0, 12);
  const latest = sorted[0];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-mono text-[10px] uppercase tracking-widest text-ink-dim">
          AI Insight — {symbol}
        </h3>
        <span className="font-mono text-[10px] text-ink-faint">
          {isLoading ? "loading…" : `${signals.length} signals`}
        </span>
      </div>

      {!isLoading && signals.length === 0 && (
        <p className="rounded-chip border border-line bg-bg px-3 py-2 text-xs text-ink-faint">
          Belum ada sinyal AI. Decision cycle berjalan tiap ~5 menit — sinyal
          analyst muncul di sini setelah cycle pertama selesai.
        </p>
      )}

      {latest && (
        <div className="rounded-chip border border-accent/30 bg-accent/5 px-3 py-2">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-semibold text-ink">Verdict terakhir:</span>
            <span
              className={
                latest.direction === "bullish"
                  ? "text-up"
                  : latest.direction === "bearish"
                    ? "text-down"
                    : "text-ink-dim"
              }
            >
              {latest.direction}
            </span>
            <span className="font-mono text-ink-dim">
              conf {Math.round((latest.confidence ?? 0) * 100)}%
            </span>
            <span className="font-mono text-[10px] text-ink-faint">
              {latest.analyst}
            </span>
          </div>
          {latest.rationale && (
            <p className="mt-1 text-[11px] leading-relaxed text-ink-dim">
              {latest.rationale}
            </p>
          )}
        </div>
      )}

      {/* Apa arti confidence + bar minimum eksekusi */}
      <div className="rounded-chip border border-line bg-bg px-3 py-2 text-[11px] leading-relaxed text-ink-dim">
        <p className="mb-1 font-medium text-ink">
          Confidence & bar minimum eksekusi
        </p>
        <p>
          <span className="font-mono text-ink">confidence</span> = keyakinan AI
          terhadap arah (0–100%). Di bawah 70%: sinyal dianggap{" "}
          <span className="text-ink">belum layak eksekusi</span> — ini
          standar institutional (minta margin of safety). Eksekusi hanya
          terjadi jika SEMUA terpenuhi:
        </p>
        <ul className="mt-1 list-disc space-y-0.5 pl-4">
          <li>
            Action <span className="font-mono">BUY/SELL</span> dari CIO
            proposal (bukan HOLD/REJECT)
          </li>
          <li>
            Confidence <span className="font-mono">≥ 70%</span> (threshold
            bisa diubah di System Config → execution_min_confidence)
          </li>
          <li>
            Side valid + size <span className="font-mono">≥ 0.01 lot</span>{" "}
            + SL/TP terisi dari proposal AI
          </li>
          <li>Kill switch tidak armed (opsional halt)</li>
        </ul>
        <p className="mt-1">
          Jika salah satu tidak terpenuhi → cycle mencatat{" "}
          <span className="font-mono">skipped_reason</span> (
          confidence_below_threshold / no_valid_side_size / halted) — bisa
          dicek di tab Backtest superadmin (status cycle).
        </p>
      </div>

      <div className="space-y-1.5">
        {sorted.map((s: SignalPoint, i: number) => (
          <AnalystCard key={`${s.analyst}-${i}`} signal={s} />
        ))}
      </div>
    </div>
  );
}
