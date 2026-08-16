import { useState } from "react";
import { useTranslation } from "react-i18next";

import { useSimulateTrade } from "@/api/hooks";
import { NumericText } from "@/components/ui/numeric-text";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const SYMBOLS = ["XAUUSD", "XAGUSD", "EURUSD", "BTCUSD", "USOIL"];

/**
 * What-if simulation panel (F-03): pre-trade NAV/margin projection backed by
 * POST /api/v1/portfolio/{id}/simulate. Pure fixture fallback on error.
 */
export function WhatIfPanel() {
  const { t } = useTranslation();
  const [symbol, setSymbol] = useState("XAUUSD");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [volume, setVolume] = useState("1.0");
  const [price, setPrice] = useState("2450.00");
  const simulate = useSimulateTrade();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    simulate.mutate({
      symbol,
      side,
      volume: Number(volume) || 0,
      price: Number(price) || 0,
    });
  };

  return (
    <Card data-testid="what-if-panel">
      <CardHeader>
        <CardTitle>{t("terminal.whatIf")}</CardTitle>
        <CardDescription>{t("terminal.whatIfDescription")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-2" aria-label="What-if simulation">
          <label className="col-span-1 text-xs text-text-secondary">
            {t("terminal.whatIfSymbol")}
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="mt-1 w-full rounded-chip border border-border-subtle bg-bg-base px-2 py-1 text-sm"
            >
              {SYMBOLS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label className="col-span-1 text-xs text-text-secondary">
            {t("terminal.whatIfSide")}
            <select
              value={side}
              onChange={(e) => setSide(e.target.value as "buy" | "sell")}
              className="mt-1 w-full rounded-chip border border-border-subtle bg-bg-base px-2 py-1 text-sm"
            >
              <option value="buy">BUY</option>
              <option value="sell">SELL</option>
            </select>
          </label>
          <label className="col-span-1 text-xs text-text-secondary">
            {t("terminal.whatIfVolume")}
            <input
              type="number"
              step="0.01"
              min="0"
              value={volume}
              onChange={(e) => setVolume(e.target.value)}
              className="mt-1 w-full rounded-chip border border-border-subtle bg-bg-base px-2 py-1 font-mono text-sm"
            />
          </label>
          <label className="col-span-1 text-xs text-text-secondary">
            {t("terminal.whatIfPrice")}
            <input
              type="number"
              step="0.01"
              min="0"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              className="mt-1 w-full rounded-chip border border-border-subtle bg-bg-base px-2 py-1 font-mono text-sm"
            />
          </label>
          <button
            type="submit"
            disabled={simulate.isPending}
            className="col-span-2 rounded-chip bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-accent/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"
          >
            {simulate.isPending ? t("terminal.whatIfSimulating") : t("terminal.whatIfSimulate")}
          </button>
        </form>

        {simulate.error && (
          <p className="text-xs text-danger" role="alert" data-testid="what-if-error">
            {t("terminal.whatIfError")}
          </p>
        )}

        {simulate.data && (
          <dl
            className="grid grid-cols-3 gap-2 border-t border-border-subtle pt-2 text-xs"
            data-testid="what-if-result"
          >
            <div>
              <dt className="text-text-tertiary">{t("terminal.whatIfProjectedNav")}</dt>
              <dd className="font-mono text-text-primary">
                <NumericText value={simulate.data.projected_nav} decimals={2} />
              </dd>
            </div>
            <div>
              <dt className="text-text-tertiary">{t("terminal.whatIfMargin")}</dt>
              <dd className="font-mono text-text-primary">
                <NumericText value={simulate.data.margin_required} decimals={2} />
              </dd>
            </div>
            <div>
              <dt className="text-text-tertiary">{t("terminal.whatIfPnl")}</dt>
              <dd className="font-mono text-text-primary">
                <NumericText value={simulate.data.pnl_change} decimals={2} />
              </dd>
            </div>
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

