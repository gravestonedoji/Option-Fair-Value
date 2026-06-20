import { useState } from "react";
import { Search } from "lucide-react";
import clsx from "clsx";

const WATCHLIST = ["SPY", "AAPL", "TSLA", "MSFT", "NVDA", "QQQ", "IWM", "GLD"];
const SYMBOL_RE = /^[A-Z]{1,6}$/;

interface Props {
  onSelect: (symbol: string) => void;
  current?: string | null;
}

export function SymbolSearch({ onSelect, current }: Props) {
  const [value, setValue] = useState(current ?? "");
  const [error, setError] = useState<string | null>(null);

  function submit(sym: string) {
    const clean = sym.trim().toUpperCase();
    if (!SYMBOL_RE.test(clean)) {
      setError("Symbol must be 1-6 uppercase letters");
      return;
    }
    setError(null);
    onSelect(clean);
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value.toUpperCase())}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit(value);
            }}
            placeholder="Enter symbol (e.g. SPY)"
            className="w-full rounded-md border border-slate-700 bg-slate-900 py-1.5 pl-8 pr-3 text-sm text-slate-100 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            maxLength={6}
          />
        </div>
        <button
          type="button"
          onClick={() => submit(value)}
          className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-400"
        >
          Load
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs text-slate-500">Watchlist:</span>
        {WATCHLIST.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => {
              setValue(s);
              submit(s);
            }}
            className={clsx(
              "rounded border px-1.5 py-0.5 text-xs font-medium transition-colors",
              current === s
                ? "border-sky-500 bg-sky-600/20 text-sky-300"
                : "border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-500 hover:text-slate-100"
            )}
          >
            {s}
          </button>
        ))}
      </div>

      {error && <span className="text-xs text-rose-400">{error}</span>}
    </div>
  );
}
