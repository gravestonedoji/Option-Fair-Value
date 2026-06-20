import type { FairValueRange, ModelRange } from "../types";

interface Props {
  range: FairValueRange;
  marketBid: number | null;
  marketAsk: number | null;
}

const MODEL_LABELS: Record<string, string> = {
  black_scholes: "Black-Scholes",
  binomial: "Binomial",
  monte_carlo: "Monte Carlo",
};

const MODEL_DOT: Record<string, string> = {
  black_scholes: "bg-sky-400",
  band_black_scholes: "bg-sky-500/30 border-sky-500/60",
  line_black_scholes: "bg-sky-500/50",
  binomial: "bg-violet-400",
  band_binomial: "bg-violet-500/30 border-violet-500/60",
  line_binomial: "bg-violet-500/50",
  monte_carlo: "bg-amber-400",
  band_monte_carlo: "bg-amber-500/30 border-amber-500/60",
  line_monte_carlo: "bg-amber-500/50",
};

export function RangeChart({ range, marketBid, marketAsk }: Props) {
  const models = Object.values(range.models) as ModelRange[];

  const extremes: number[] = [];
  models.forEach((m) => extremes.push(m.min, m.max));
  if (marketBid !== null) extremes.push(marketBid);
  if (marketAsk !== null) extremes.push(marketAsk);

  let xMin = Math.min(...extremes);
  let xMax = Math.max(...extremes);
  if (!isFinite(xMin) || !isFinite(xMax) || xMax <= xMin) {
    xMin = 0;
    xMax = 1;
  }
  const pad = (xMax - xMin) * 0.05;
  xMin -= pad;
  xMax += pad;
  const span = xMax - xMin;

  const pct = (v: number) => ((v - xMin) / span) * 100;

  const ticks = 5;
  const tickVals = Array.from({ length: ticks + 1 }, (_, i) => xMin + (span * i) / ticks);

  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/40 p-3">
      <h3 className="mb-2 text-xs uppercase tracking-wide text-slate-500">
        Fair Value Range (min · P5 · median · P95 · max)
      </h3>

      <div className="relative">
        {/* market bid/ask vertical lines spanning all rows */}
        {marketBid !== null && (
          <MarketLine
            pos={pct(marketBid)}
            color="border-emerald-400 text-emerald-400"
            label={`bid ${marketBid.toFixed(2)}`}
            rowCount={models.length}
            labelSide="left"
          />
        )}
        {marketAsk !== null && (
          <MarketLine
            pos={pct(marketAsk)}
            color="border-rose-400 text-rose-400"
            label={`ask ${marketAsk.toFixed(2)}`}
            rowCount={models.length}
            labelSide="right"
          />
        )}

        <div className="flex flex-col gap-2">
          {models.map((m) => {
            const left = pct(m.min);
            const width = pct(m.max) - pct(m.min);
            const p5Left = pct(m.p5);
            const p95Width = pct(m.p95) - pct(m.p5);
            const medianLeft = pct(m.median);
            const baseLeft = pct(m.base);
            return (
              <div key={m.name} className="flex items-center gap-2">
                <div className="w-24 shrink-0 text-right text-[11px] text-slate-400">
                  {MODEL_LABELS[m.name] ?? m.name}
                </div>
                <div className="relative h-6 flex-1 rounded bg-slate-900/60">
                  {/* min-max line */}
                  <div
                    className={`absolute top-1/2 h-px -translate-y-1/2 ${MODEL_DOT[`line_${m.name}`] ?? "bg-slate-600"}`}
                    style={{ left: `${left}%`, width: `${width}%` }}
                  />
                  {/* p5-p95 band */}
                  <div
                    className={`absolute top-1/2 h-3 -translate-y-1/2 rounded border ${MODEL_DOT[`band_${m.name}`] ?? "bg-slate-700/40 border-slate-600"}`}
                    style={{ left: `${p5Left}%`, width: `${Math.max(p95Width, 0.5)}%` }}
                  />
                  {/* median tick */}
                  <div
                    className="absolute top-1/2 h-4 w-0.5 -translate-x-1/2 -translate-y-1/2 bg-slate-100"
                    style={{ left: `${medianLeft}%` }}
                    title={`median ${m.median.toFixed(2)}`}
                  />
                  {/* base FV marker */}
                  <div
                    className={`absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-slate-950 ${MODEL_DOT[m.name] ?? "bg-slate-300"}`}
                    style={{ left: `${baseLeft}%` }}
                    title={`base ${m.base.toFixed(2)}`}
                  />
                </div>
                <div className="w-14 shrink-0 text-right font-mono text-[11px] text-slate-300">
                  {m.base.toFixed(2)}
                </div>
              </div>
            );
          })}
        </div>

        {/* x-axis ticks */}
        <div className="mt-1 flex items-center gap-2">
          <div className="w-24 shrink-0" />
          <div className="relative h-4 flex-1">
            {tickVals.map((t, i) => (
              <span
                key={i}
                className="absolute -translate-x-1/2 font-mono text-[10px] text-slate-600"
                style={{ left: `${pct(t)}%` }}
              >
                {t.toFixed(1)}
              </span>
            ))}
          </div>
          <div className="w-14 shrink-0" />
        </div>
      </div>

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-slate-500">
        <LegendDot className="bg-slate-100" label="Base FV" />
        <LegendBar className="bg-slate-700/60" label="P5–P95" />
        <LegendLine label="Min–Max" />
        <LegendDot className="bg-emerald-400" label="Market bid" />
        <LegendDot className="bg-rose-400" label="Market ask" />
      </div>
    </div>
  );
}

function MarketLine({
  pos,
  color,
  label,
  rowCount,
  labelSide = "right",
}: {
  pos: number;
  color: string;
  label: string;
  rowCount: number;
  labelSide?: "left" | "right";
}) {
  const rowH = 24;
  const gap = 8;
  const totalH = rowCount * rowH + (rowCount - 1) * gap;
  const labelClass =
    labelSide === "left"
      ? "absolute -top-4 right-1 whitespace-nowrap text-[9px]"
      : "absolute -top-4 left-1 whitespace-nowrap text-[9px]";
  return (
    <div
      className={`pointer-events-none absolute z-10 border-l border-dashed ${color}`}
      style={{ left: `${pos}%`, top: 0, height: totalH }}
    >
      <span className={`${labelClass} ${color.split(" ")[1]}`}>
        {label}
      </span>
    </div>
  );
}

function LegendDot({ className, label }: { className: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className={`inline-block h-2 w-2 rounded-full ${className}`} />
      {label}
    </span>
  );
}

function LegendBar({ className, label }: { className: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className={`inline-block h-2 w-4 rounded border border-slate-600 ${className}`} />
      {label}
    </span>
  );
}

function LegendLine({ label }: { label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className="inline-block h-px w-4 bg-slate-600" />
      {label}
    </span>
  );
}
