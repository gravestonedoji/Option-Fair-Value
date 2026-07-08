import { useMemo } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChainAnalysis, ContractAnalysis } from "../types";

interface Props {
  analysis: ChainAnalysis;
}

interface SmilePoint {
  strike: number;
  iv: number; // percent
  fitted_iv: number | null; // percent
  side: string;
  z: number | null;
  verdict: string | null;
}

// Coefficients follow numpy polyfit convention: highest power first.
function polyval(coeffs: number[], x: number): number {
  return coeffs.reduce((acc, c) => acc * x + c, 0);
}

function toPoint(c: ContractAnalysis): SmilePoint {
  return {
    strike: c.strike,
    iv: (c.iv ?? 0) * 100,
    fitted_iv: c.fitted_iv === null ? null : c.fitted_iv * 100,
    side: c.type,
    z: c.z,
    verdict: c.verdict,
  };
}

function SmileTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const p: SmilePoint & { fit?: number } = payload[0].payload;
  if (p.side === undefined) {
    // fitted-curve sample
    return (
      <div className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-300">
        Fit {(p as any).fit?.toFixed(1)}% @ {p.strike.toFixed(2)}
      </div>
    );
  }
  return (
    <div className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-300">
      <div className="font-semibold text-slate-200">
        {p.side.toUpperCase()} {p.strike.toFixed(2)}
        {p.verdict && (
          <span
            className={
              p.verdict === "rich" ? "ml-1 text-amber-400" : "ml-1 text-teal-300"
            }
          >
            {p.verdict.toUpperCase()}
          </span>
        )}
      </div>
      <div>Market IV {p.iv.toFixed(1)}%</div>
      {p.fitted_iv !== null && <div>Fit IV {p.fitted_iv.toFixed(1)}%</div>}
      {p.z !== null && <div>z {p.z >= 0 ? "+" : ""}{p.z.toFixed(2)}</div>}
    </div>
  );
}

export function IVSmilePanel({ analysis }: Props) {
  const { fit, forward } = analysis;

  const { normal, rich, cheap, curve } = useMemo(() => {
    // Far-OTM wings are outside the analysis band (no fit, no flags there);
    // plotting them would compress the region the screen actually covers.
    const model = analysis.contracts.filter(
      (c) =>
        c.iv_source === "model" &&
        c.is_otm &&
        c.iv !== null &&
        !c.filters_failed.includes("far_otm")
    );
    const pts = model.map(toPoint);
    const curve: { strike: number; fit: number }[] = [];
    if (fit.fitted && fit.k_min !== null && fit.k_max !== null) {
      const n = 60;
      for (let i = 0; i <= n; i++) {
        const k = fit.k_min + ((fit.k_max - fit.k_min) * i) / n;
        const iv = polyval(fit.coefficients, k);
        if (iv > 0) curve.push({ strike: forward * Math.exp(k), fit: iv * 100 });
      }
    }
    return {
      normal: pts.filter((p) => p.verdict === null),
      rich: pts.filter((p) => p.verdict === "rich"),
      cheap: pts.filter((p) => p.verdict === "cheap"),
      curve,
    };
  }, [analysis, fit, forward]);

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-slate-800 bg-slate-900 p-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-slate-200">
          IV Smile · {analysis.symbol}
        </h2>
        <span className="text-xs text-slate-500">{analysis.expiry}</span>
      </div>

      {!fit.fitted ? (
        <div className="flex h-48 items-center justify-center rounded-md border border-slate-800 bg-slate-950/40 text-sm text-slate-500">
          {fit.reason === "insufficient_points"
            ? "Not enough liquid OTM quotes to fit a smile for this expiry."
            : "Strike range too narrow to fit a smile for this expiry."}
        </div>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
              <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
              <XAxis
                dataKey="strike"
                type="number"
                domain={["dataMin", "dataMax"]}
                stroke="#475569"
                tick={{ fill: "#64748b", fontSize: 10 }}
                tickFormatter={(v: number) => v.toFixed(0)}
              />
              {/* No dataKey: the y-domain must union the scatters' `iv` AND
                  the curve's `fit`, or the fitted line draws outside the grid */}
              <YAxis
                type="number"
                domain={["auto", "auto"]}
                stroke="#475569"
                tick={{ fill: "#64748b", fontSize: 10 }}
                tickFormatter={(v: number) => `${v.toFixed(0)}%`}
              />
              <Tooltip content={<SmileTooltip />} isAnimationActive={false} />
              <ReferenceLine
                x={forward}
                stroke="#38bdf8"
                strokeDasharray="4 2"
                label={{ value: "F", fill: "#38bdf8", fontSize: 10, position: "top" }}
              />
              <Line
                data={curve}
                dataKey="fit"
                type="monotone"
                stroke="#38bdf8"
                strokeWidth={1.5}
                dot={false}
                activeDot={false}
                isAnimationActive={false}
              />
              <Scatter data={normal} dataKey="iv" fill="#94a3b8" isAnimationActive={false} />
              <Scatter data={rich} dataKey="iv" fill="#fbbf24" isAnimationActive={false} />
              <Scatter data={cheap} dataKey="iv" fill="#5eead4" isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-slate-500">
            <LegendItem color="#94a3b8" label="Market IV (OTM)" />
            <LegendItem color="#38bdf8" label="Fitted smile" line />
            <LegendItem color="#fbbf24" label="Rich" />
            <LegendItem color="#5eead4" label="Cheap" />
          </div>

          <div className="flex flex-wrap gap-x-4 gap-y-0.5 border-t border-slate-800 pt-2 text-[10px] text-slate-500">
            <span>
              F <span className="font-mono text-slate-400">{forward.toFixed(2)}</span>
              <span className="ml-1">({analysis.forward_source === "parity" ? "parity" : "spot carry"})</span>
            </span>
            <span>
              Rate{" "}
              <span className="font-mono text-slate-400">
                {(analysis.risk_free_rate * 100).toFixed(2)}%
              </span>
              <span className="ml-1">({analysis.rate_source})</span>
            </span>
            <span>
              Fit n <span className="font-mono text-slate-400">{fit.n_used}</span>
              {fit.n_dropped > 0 && (
                <span className="ml-1">({fit.n_dropped} dropped)</span>
              )}
            </span>
            {fit.rmse !== null && (
              <span>
                RMSE{" "}
                <span className="font-mono text-slate-400">
                  {(fit.rmse * 100).toFixed(2)}%
                </span>
              </span>
            )}
            {fit.sigma_mad !== null && (
              <span>
                σ<sub>MAD</sub>{" "}
                <span className="font-mono text-slate-400">
                  {(fit.sigma_mad * 100).toFixed(2)}%
                </span>
              </span>
            )}
          </div>
        </>
      )}

      <p className="text-[10px] leading-relaxed text-slate-600">
        Relative-value screen against this expiry's fitted smile. Quotes are
        ~15-min delayed; deviations are screening signals, not arbitrage.
      </p>
    </div>
  );
}

function LegendItem({ color, label, line }: { color: string; label: string; line?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {line ? (
        <span className="h-0.5 w-4" style={{ backgroundColor: color }} />
      ) : (
        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
      )}
      {label}
    </span>
  );
}
