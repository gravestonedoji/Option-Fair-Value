import clsx from "clsx";
import type { FairValueRange, ModelRange } from "../types";

interface Props {
  range: FairValueRange;
  marketBid: number | null;
  marketAsk: number | null;
}

const f2 = (v: number) => v.toFixed(2);

const MODEL_LABELS: Record<string, string> = {
  black_scholes: "Black-Scholes",
  binomial: "Binomial (CRR)",
  monte_carlo: "Monte Carlo",
};

const MODEL_COLORS: Record<string, string> = {
  black_scholes: "text-sky-300",
  binomial: "text-violet-300",
  monte_carlo: "text-amber-300",
};

export function ModelComparison({ range, marketBid, marketAsk }: Props) {
  const models = Object.values(range.models);
  const marketMid =
    marketBid !== null && marketAsk !== null
      ? (marketBid + marketAsk) / 2
      : null;

  return (
    <div className="overflow-hidden rounded-md border border-slate-800">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-800 bg-slate-950/60 text-[10px] uppercase tracking-wide text-slate-500">
            <th className="px-2 py-1.5 text-left">Model</th>
            <th className="px-2 py-1.5 text-right">Base FV</th>
            <th className="px-2 py-1.5 text-right">Min</th>
            <th className="px-2 py-1.5 text-right">P5</th>
            <th className="px-2 py-1.5 text-right">Median</th>
            <th className="px-2 py-1.5 text-right">P95</th>
            <th className="px-2 py-1.5 text-right">Max</th>
          </tr>
        </thead>
        <tbody>
          {models.map((m: ModelRange) => {
            const inMarket =
              marketBid !== null &&
              marketAsk !== null &&
              m.base >= marketBid &&
              m.base <= marketAsk;
            return (
              <tr
                key={m.name}
                className="border-b border-slate-800/60 last:border-0"
              >
                <td
                  className={clsx(
                    "px-2 py-1.5 font-medium",
                    MODEL_COLORS[m.name] ?? "text-slate-200"
                  )}
                >
                  {MODEL_LABELS[m.name] ?? m.name}
                </td>
                <td className="px-2 py-1.5 text-right font-mono tabular-nums">
                  <span
                    className={clsx(
                      inMarket ? "text-emerald-400" : "text-slate-100"
                    )}
                    title={
                      inMarket
                        ? "Base FV is within market bid/ask"
                        : "Base FV is outside market bid/ask"
                    }
                  >
                    {f2(m.base)}
                  </span>
                </td>
                <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-400">
                  {f2(m.min)}
                </td>
                <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-400">
                  {f2(m.p5)}
                </td>
                <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-200">
                  {f2(m.median)}
                </td>
                <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-400">
                  {f2(m.p95)}
                </td>
                <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-400">
                  {f2(m.max)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {marketMid !== null && (
        <div className="border-t border-slate-800 bg-slate-950/40 px-2 py-1 text-[11px] text-slate-500">
          Market mid: <span className="font-mono text-slate-300">${f2(marketMid)}</span>
          {" "}
          (bid {f2(marketBid ?? 0)} / ask {f2(marketAsk ?? 0)})
        </div>
      )}
    </div>
  );
}
