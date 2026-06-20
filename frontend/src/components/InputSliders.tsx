import clsx from "clsx";
import type { InputBands } from "../types";

interface Props {
  bands: InputBands;
  onChange: (bands: InputBands) => void;
  onReset: () => void;
}

interface SliderConfig {
  key: keyof InputBands;
  label: string;
  min: number;
  max: number;
  step: number;
  display: (v: number) => string;
  help: string;
}

const SLIDERS: SliderConfig[] = [
  {
    key: "vol_pct",
    label: "IV band",
    min: 0,
    max: 0.5,
    step: 0.01,
    display: (v) => `${(v * 100).toFixed(0)}%`,
    help: "± relative on implied vol",
  },
  {
    key: "spot_pct",
    label: "Spot band",
    min: 0,
    max: 0.2,
    step: 0.005,
    display: (v) => `${(v * 100).toFixed(1)}%`,
    help: "± relative on spot",
  },
  {
    key: "rate_bps",
    label: "Rate band",
    min: 0,
    max: 200,
    step: 5,
    display: (v) => `${v.toFixed(0)} bps`,
    help: "± absolute on risk-free rate",
  },
  {
    key: "dte_days",
    label: "DTE band",
    min: 0,
    max: 14,
    step: 0.5,
    display: (v) => `${v.toFixed(1)} d`,
    help: "± calendar days on time to expiry",
  },
];

export function InputSliders({ bands, onChange, onReset }: Props) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/40 p-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-xs uppercase tracking-wide text-slate-500">
          Input Uncertainty Bands
        </h3>
        <button
          onClick={onReset}
          className="rounded border border-slate-700 px-2 py-0.5 text-[11px] text-slate-400 transition hover:bg-slate-800 hover:text-slate-200"
        >
          Reset
        </button>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {SLIDERS.map((s) => (
          <div key={s.key} className="flex flex-col gap-1">
            <div className="flex items-baseline justify-between">
              <label className="text-xs text-slate-300">{s.label}</label>
              <span className="font-mono text-xs text-sky-300">
                ±{s.display(bands[s.key])}
              </span>
            </div>
            <input
              type="range"
              min={s.min}
              max={s.max}
              step={s.step}
              value={bands[s.key]}
              onChange={(e) =>
                onChange({ ...bands, [s.key]: parseFloat(e.target.value) })
              }
              className={clsx(
                "h-1.5 w-full cursor-pointer appearance-none rounded-full bg-slate-700",
                "accent-sky-500"
              )}
            />
            <span className="text-[10px] text-slate-600">{s.help}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
