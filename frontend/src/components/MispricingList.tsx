import { useMemo, useState } from "react";
import clsx from "clsx";
import { ChevronDown, ChevronRight } from "lucide-react";
import type {
  ChainAnalysis,
  ContractAnalysis,
  OptionChain,
  OptionQuote,
  OptionType,
} from "../types";

interface Props {
  analysis: ChainAnalysis;
  chain: OptionChain;
  onSelect: (strike: number, type: OptionType, quote: OptionQuote) => void;
}

const MAX_ROWS = 15;

const FILTER_LABELS: Record<string, string> = {
  no_bid: "no bid",
  crossed: "crossed",
  wide_spread: "wide spread",
  low_liquidity: "low liq",
  itm: "ITM",
  iv_unsolved: "no IV",
  inside_spread: "inside spread",
  far_otm: "far OTM",
};

const fmt2 = (v: number | null) => (v === null ? "—" : v.toFixed(2));
const fmtZ = (v: number | null) =>
  v === null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(1)}`;
const fmtPct = (v: number | null) =>
  v === null ? "—" : `${(v * 100).toFixed(0)}%`;

export function MispricingList({ analysis, chain, onSelect }: Props) {
  const [showNearMisses, setShowNearMisses] = useState(false);

  const { flagged, nearMisses } = useMemo(() => {
    const byAbsZ = (a: ContractAnalysis, b: ContractAnalysis) =>
      Math.abs(b.z ?? 0) - Math.abs(a.z ?? 0);
    return {
      flagged: analysis.contracts
        .filter((c) => c.verdict !== null)
        .sort(byAbsZ)
        .slice(0, MAX_ROWS),
      nearMisses: analysis.contracts
        .filter(
          (c) =>
            c.verdict === null &&
            c.z !== null &&
            Math.abs(c.z) >= analysis.params.z_threshold
        )
        .sort(byAbsZ)
        .slice(0, MAX_ROWS),
    };
  }, [analysis]);

  function handleClick(c: ContractAnalysis) {
    const row = chain.rows.find((r) => r.strike === c.strike);
    if (!row) return;
    const quote = c.type === "call" ? row.call : row.put;
    onSelect(c.strike, c.type, quote);
  }

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-slate-800 bg-slate-900 p-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-slate-200">
          Mispricing Screen
        </h2>
        <span className="text-xs text-slate-500">
          |z| ≥ {analysis.params.z_threshold.toFixed(1)} + liquidity + edge
        </span>
      </div>

      {!analysis.fit.fitted ? (
        <div className="py-6 text-center text-sm text-slate-500">
          No smile fit for this expiry — nothing to screen against.
        </div>
      ) : flagged.length === 0 ? (
        <div className="py-6 text-center text-sm text-slate-500">
          No contracts pass the screen. The chain is priced in line with its
          fitted smile.
        </div>
      ) : (
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="border-b border-slate-800 text-[10px] uppercase tracking-wide text-slate-500">
              <th className="px-1.5 py-1 text-left">Contract</th>
              <th className="px-1.5 py-1 text-right">Mid</th>
              <th className="px-1.5 py-1 text-right">Fit</th>
              <th className="px-1.5 py-1 text-right">Edge</th>
              <th className="px-1.5 py-1 text-right">z</th>
              <th className="px-1.5 py-1 text-right">Sprd</th>
              <th className="px-1.5 py-1 text-right">OI</th>
              <th className="px-1.5 py-1 text-right"></th>
            </tr>
          </thead>
          <tbody>
            {flagged.map((c) => (
              <tr
                key={`${c.type}:${c.strike}`}
                onClick={() => handleClick(c)}
                className="cursor-pointer border-b border-slate-800/60 font-mono tabular-nums text-slate-300 hover:bg-slate-800/40"
              >
                <td className="px-1.5 py-1 text-left">
                  <span
                    className={
                      c.type === "call" ? "text-emerald-400" : "text-rose-400"
                    }
                  >
                    {c.type === "call" ? "C" : "P"}
                  </span>{" "}
                  {c.strike.toFixed(2)}
                </td>
                <td className="px-1.5 py-1 text-right">{fmt2(c.mid)}</td>
                <td className="px-1.5 py-1 text-right">{fmt2(c.fitted_price)}</td>
                <td
                  className={clsx(
                    "px-1.5 py-1 text-right",
                    (c.price_edge ?? 0) > 0 ? "text-amber-400" : "text-teal-300"
                  )}
                >
                  {c.price_edge !== null && c.price_edge > 0 ? "+" : ""}
                  {fmt2(c.price_edge)}
                </td>
                <td className="px-1.5 py-1 text-right">{fmtZ(c.z)}</td>
                <td className="px-1.5 py-1 text-right">{fmtPct(c.rel_spread)}</td>
                <td className="px-1.5 py-1 text-right">
                  {c.open_interest === null
                    ? "—"
                    : c.open_interest.toLocaleString("en-US")}
                </td>
                <td className="px-1.5 py-1 text-right">
                  <VerdictPill verdict={c.verdict!} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {analysis.fit.fitted && nearMisses.length > 0 && (
        <div className="mt-1">
          <button
            onClick={() => setShowNearMisses((v) => !v)}
            className="flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-400"
          >
            {showNearMisses ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
            High |z|, failed filters ({nearMisses.length})
          </button>
          {showNearMisses && (
            <div className="mt-1 flex flex-col gap-1">
              {nearMisses.map((c) => (
                <div
                  key={`${c.type}:${c.strike}`}
                  onClick={() => handleClick(c)}
                  className="flex cursor-pointer items-center justify-between rounded px-1.5 py-1 text-[11px] text-slate-500 hover:bg-slate-800/40"
                >
                  <span className="font-mono tabular-nums">
                    {c.type === "call" ? "C" : "P"} {c.strike.toFixed(2)} · z{" "}
                    {fmtZ(c.z)}
                  </span>
                  <span className="flex flex-wrap gap-1">
                    {c.filters_failed.map((f) => (
                      <span
                        key={f}
                        className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400"
                      >
                        {FILTER_LABELS[f] ?? f}
                      </span>
                    ))}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function VerdictPill({ verdict }: { verdict: "rich" | "cheap" }) {
  return (
    <span
      className={clsx(
        "rounded px-1.5 py-0.5 text-[10px] font-semibold",
        verdict === "rich"
          ? "bg-amber-400/15 text-amber-400"
          : "bg-teal-300/15 text-teal-300"
      )}
    >
      {verdict.toUpperCase()}
    </span>
  );
}
