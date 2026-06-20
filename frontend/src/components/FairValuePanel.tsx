import { useMemo, useState } from "react";
import type { InputBands, OptionQuote, OptionType } from "../types";
import { useFairValue } from "../api/hooks";
import { InputSliders } from "./InputSliders";
import { ModelComparison } from "./ModelComparison";
import { RangeChart } from "./RangeChart";
import { GreeksTable } from "./GreeksTable";
import { Spinner } from "./Loading";

const DEFAULT_BANDS: InputBands = {
  vol_pct: 0.2,
  spot_pct: 0.05,
  rate_bps: 50,
  dte_days: 2,
};

interface Props {
  symbol: string;
  expiry: string;
  strike: number;
  type: OptionType;
  quote: OptionQuote;
}

const f2 = (v: number | null) => (v === null ? "—" : v.toFixed(2));
const fIV = (v: number | null) => (v === null ? "—" : `${(v * 100).toFixed(1)}%`);

export function FairValuePanel({ symbol, expiry, strike, type, quote }: Props) {
  const [bands, setBands] = useState<InputBands>(DEFAULT_BANDS);

  const req = useMemo(
    () => ({ symbol, expiry, strike, type, bands }),
    [symbol, expiry, strike, type, bands]
  );

  const fvQuery = useFairValue(req);

  // Reset bands to defaults when the contract changes keeps them sticky;
  // only reset on explicit button press.
  const handleReset = () => setBands(DEFAULT_BANDS);

  return (
    <div className="flex max-h-[calc(100vh-7rem)] flex-col gap-3 overflow-auto rounded-lg border border-slate-800 bg-slate-900 p-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-slate-200">
          Fair Value · {symbol} {type.toUpperCase()} {strike.toFixed(2)}
        </h2>
        <span className="text-xs text-slate-500">{expiry}</span>
      </div>

      {/* Selected contract summary */}
      <div className="grid grid-cols-4 gap-2 rounded-md border border-slate-800 bg-slate-950/40 p-2 text-xs">
        <SummaryCell label="Bid" value={f2(quote.bid)} />
        <SummaryCell label="Ask" value={f2(quote.ask)} />
        <SummaryCell label="Mid" value={f2(quote.mid)} />
        <SummaryCell label="IV" value={fIV(quote.iv)} />
      </div>

      <InputSliders bands={bands} onChange={setBands} onReset={handleReset} />

      {fvQuery.isLoading && (
        <div className="flex h-40 items-center justify-center gap-2 rounded-md border border-slate-800 bg-slate-950/40 text-sm text-slate-400">
          <Spinner className="h-4 w-4" />
          Computing fair value range (200 LHS × 50k MC paths)…
        </div>
      )}

      {fvQuery.isError && (
        <div className="rounded-md border border-rose-900/60 bg-rose-950/30 p-3 text-sm text-rose-300">
          Failed to compute fair value:{" "}
          {(fvQuery.error as Error)?.message ?? "unknown error"}
        </div>
      )}

      {fvQuery.data && (
        <div className="flex flex-col gap-3">
          <RangeChart
            range={fvQuery.data}
            marketBid={quote.bid}
            marketAsk={quote.ask}
          />
          <ModelComparison
            range={fvQuery.data}
            marketBid={quote.bid}
            marketAsk={quote.ask}
          />
          <div>
            <h3 className="mb-1.5 text-xs uppercase tracking-wide text-slate-500">
              Greeks (at base inputs)
            </h3>
            <GreeksTable range={fvQuery.data} />
          </div>
          <BaseInputsFooter range={fvQuery.data} />
        </div>
      )}

      {fvQuery.isFetching && !fvQuery.isLoading && (
        <div className="flex items-center gap-2 text-[11px] text-slate-500">
          <Spinner className="h-3 w-3" /> Updating…
        </div>
      )}
    </div>
  );
}

function SummaryCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wide text-slate-500">
        {label}
      </span>
      <span className="font-mono text-slate-200">{value}</span>
    </div>
  );
}

function BaseInputsFooter({ range }: { range: import("../types").FairValueRange }) {
  const bi = range.base_inputs;
  const dte = (bi.time_to_expiry * 365).toFixed(1);
  return (
    <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 border-t border-slate-800 pt-2 text-[10px] text-slate-500">
      <span>
        Spot <span className="font-mono text-slate-400">{bi.spot.toFixed(2)}</span>
      </span>
      <span>
        Rate <span className="font-mono text-slate-400">{(bi.risk_free_rate * 100).toFixed(2)}%</span>
      </span>
      <span>
        IV <span className="font-mono text-slate-400">{(bi.volatility * 100).toFixed(2)}%</span>
      </span>
      <span>
        DTE <span className="font-mono text-slate-400">{dte}d</span>
      </span>
      <span>
        Div yld <span className="font-mono text-slate-400">{(bi.dividend_yield * 100).toFixed(2)}%</span>
      </span>
      <span>
        Style <span className="font-mono text-slate-400">{bi.style}</span>
      </span>
    </div>
  );
}
