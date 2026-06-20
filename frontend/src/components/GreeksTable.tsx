import type { FairValueRange, Greeks } from "../types";

interface Props {
  range: FairValueRange;
}

const MODEL_LABELS: Record<string, string> = {
  black_scholes: "Black-Scholes",
  binomial: "Binomial",
  monte_carlo: "Monte Carlo",
};

const f2 = (v: number | null) => (v === null ? "—" : v.toFixed(4));

export function GreeksTable({ range }: Props) {
  const models = Object.entries(range.base_results) as [string, Greeks][];
  return (
    <div className="overflow-hidden rounded-md border border-slate-800">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-800 bg-slate-950/60 text-[10px] uppercase tracking-wide text-slate-500">
            <th className="px-2 py-1.5 text-left">Model</th>
            <th className="px-2 py-1.5 text-right">Price</th>
            <th className="px-2 py-1.5 text-right">Delta</th>
            <th className="px-2 py-1.5 text-right">Gamma</th>
            <th className="px-2 py-1.5 text-right">Theta<span className="font-normal normal-case text-slate-600">/d</span></th>
            <th className="px-2 py-1.5 text-right">Vega<span className="font-normal normal-case text-slate-600">/1%</span></th>
            <th className="px-2 py-1.5 text-right">Rho<span className="font-normal normal-case text-slate-600">/1%</span></th>
          </tr>
        </thead>
        <tbody>
          {models.map(([name, g]) => (
            <tr key={name} className="border-b border-slate-800/60 last:border-0">
              <td className="px-2 py-1.5 text-slate-300">
                {MODEL_LABELS[name] ?? name}
              </td>
              <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-100">
                {g.price.toFixed(2)}
              </td>
              <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-300">
                {f2(g.delta)}
              </td>
              <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-300">
                {f2(g.gamma)}
              </td>
              <td className="px-2 py-1.5 text-right font-mono tabular-nums text-rose-300">
                {f2(g.theta)}
              </td>
              <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-300">
                {f2(g.vega)}
              </td>
              <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-300">
                {f2(g.rho)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
