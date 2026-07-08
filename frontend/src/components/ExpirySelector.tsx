interface Props {
  expiries: string[] | undefined;
  value: string | null;
  onChange: (expiry: string) => void;
}

function dte(expiry: string): number {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const exp = new Date(expiry + "T00:00:00");
  const ms = exp.getTime() - today.getTime();
  return Math.round(ms / (1000 * 60 * 60 * 24));
}

export function ExpirySelector({ expiries, value, onChange }: Props) {
  const sorted = expiries ? [...expiries].sort() : undefined;
  // Alert deep-links can set an expiry the (up to 1h stale) cached list
  // doesn't contain yet; a controlled select with an unmatched value renders
  // blank, so always include the current value as an option.
  const options =
    sorted && value && !sorted.includes(value)
      ? [...sorted, value].sort()
      : sorted;

  return (
    <div className="flex items-center gap-2">
      <label className="text-sm text-slate-400">Expiry:</label>
      <select
        value = {value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        disabled={!options}
        className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-slate-100 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500 disabled:opacity-50"
      >
        {!options && (
          <option value={value ?? ""}>{value ?? "Loading..."}</option>
        )}
        {options?.map((d) => (
          <option key={d} value={d}>
            {d} ({dte(d)}d)
          </option>
        ))}
      </select>
    </div>
  );
}
