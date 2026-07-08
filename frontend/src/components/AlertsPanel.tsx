import { useState } from "react";
import clsx from "clsx";
import { Bell, ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useAlerts } from "../api/hooks";
import type { AlertRecord, OptionType } from "../types";

interface Props {
  onSelectAlert: (
    symbol: string,
    expiry: string,
    strike: number,
    type: OptionType
  ) => void;
}

const fmt2 = (v: number | null) => (v === null ? "—" : v.toFixed(2));
const fmtZ = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}`;

function ago(iso: string): string {
  const mins = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60_000));
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

function timeOf(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function AlertsPanel({ onSelectAlert }: Props) {
  const alertsQuery = useAlerts();
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(true);
  const [showResolved, setShowResolved] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);

  const data = alertsQuery.data;
  if (!data) return null;
  const { status, active, pending, resolved } = data;

  if (!status.enabled) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900 px-4 py-2 text-xs text-slate-500">
        Mispricing scanner is off. Start the backend with{" "}
        <code className="text-slate-400">OFV_SCANNER_ENABLED=1</code> to sweep a
        watchlist automatically.
      </div>
    );
  }

  async function handleScanNow() {
    setScanning(true);
    setScanError(null);
    try {
      // Fire-and-forget on the backend: the response returns immediately and
      // the alerts query (fast-polling while status.scanning) tracks progress.
      await api.triggerScan();
      await queryClient.invalidateQueries({ queryKey: ["alerts"] });
    } catch (err) {
      setScanError(err instanceof Error ? err.message : "Scan request failed");
    } finally {
      setScanning(false);
    }
  }

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2">
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-2 text-sm font-semibold text-slate-200"
        >
          {expanded ? (
            <ChevronDown className="h-3.5 w-3.5 text-slate-500" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-slate-500" />
          )}
          <Bell className="h-3.5 w-3.5 text-slate-400" />
          Mispricing Alerts
          {active.length > 0 && (
            <span className="rounded-full bg-amber-400/20 px-2 py-0.5 text-[11px] font-bold text-amber-400">
              {active.length}
            </span>
          )}
        </button>

        <span className="text-[11px] text-slate-500">
          watching {status.watchlist.join(", ")}
        </span>
        <span className="text-[11px] text-slate-500">
          market {status.market_open ? "open" : "closed"} · last sweep{" "}
          {timeOf(status.last_scan_completed)}
          {pending.length > 0 && ` · ${pending.length} watching`}
        </span>
        {status.last_scan_errors.length > 0 && (
          <span
            className="text-[11px] text-rose-400"
            title={status.last_scan_errors.join("\n")}
          >
            {status.last_scan_errors.length} fetch error(s)
          </span>
        )}
        {scanError && (
          <span className="text-[11px] text-rose-400" title={scanError}>
            scan request failed
          </span>
        )}

        <button
          onClick={handleScanNow}
          disabled={scanning || status.scanning}
          className="ml-auto flex items-center gap-1.5 rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-800 disabled:opacity-50"
        >
          <RefreshCw
            className={clsx("h-3 w-3", (scanning || status.scanning) && "animate-spin")}
          />
          {scanning || status.scanning ? "Sweeping…" : "Scan now"}
        </button>
      </div>

      {expanded && (
        <div className="border-t border-slate-800 px-4 py-2">
          {active.length === 0 ? (
            <div className="py-2 text-xs text-slate-500">
              No persistent mispricings right now. Alerts appear when a
              contract stays off its fitted smile for{" "}
              {status.persistence_scans}+ consecutive sweeps.
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
                  <th className="px-1.5 py-1 text-right">Persisted</th>
                  <th className="px-1.5 py-1 text-right"></th>
                </tr>
              </thead>
              <tbody>
                {active.map((a: AlertRecord) => (
                  <tr
                    key={a.key}
                    onClick={() => onSelectAlert(a.symbol, a.expiry, a.strike, a.type)}
                    className="cursor-pointer border-b border-slate-800/60 font-mono tabular-nums text-slate-300 hover:bg-slate-800/40"
                  >
                    <td className="px-1.5 py-1 text-left">
                      <span className="font-semibold text-slate-200">{a.symbol}</span>{" "}
                      <span
                        className={a.type === "call" ? "text-emerald-400" : "text-rose-400"}
                      >
                        {a.type === "call" ? "C" : "P"}
                      </span>{" "}
                      {a.strike.toFixed(2)}{" "}
                      <span className="text-slate-500">{a.expiry}</span>
                    </td>
                    <td className="px-1.5 py-1 text-right">{fmt2(a.mid)}</td>
                    <td className="px-1.5 py-1 text-right">{fmt2(a.fitted_price)}</td>
                    <td
                      className={clsx(
                        "px-1.5 py-1 text-right",
                        (a.price_edge ?? 0) > 0 ? "text-amber-400" : "text-teal-300"
                      )}
                    >
                      {a.price_edge !== null && a.price_edge > 0 ? "+" : ""}
                      {fmt2(a.price_edge)}
                    </td>
                    <td className="px-1.5 py-1 text-right">{fmtZ(a.z)}</td>
                    <td className="px-1.5 py-1 text-right text-slate-400">
                      {ago(a.first_seen)}
                    </td>
                    <td className="px-1.5 py-1 text-right">
                      <span
                        className={clsx(
                          "rounded px-1.5 py-0.5 text-[10px] font-semibold",
                          a.verdict === "rich"
                            ? "bg-amber-400/15 text-amber-400"
                            : "bg-teal-300/15 text-teal-300"
                        )}
                      >
                        {a.verdict.toUpperCase()}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {resolved.length > 0 && (
            <div className="mt-1">
              <button
                onClick={() => setShowResolved((v) => !v)}
                className="flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-400"
              >
                {showResolved ? (
                  <ChevronDown className="h-3 w-3" />
                ) : (
                  <ChevronRight className="h-3 w-3" />
                )}
                Recently resolved ({resolved.length})
              </button>
              {showResolved && (
                <div className="mt-1 flex flex-col gap-0.5">
                  {resolved.slice(0, 10).map((a) => (
                    <div
                      key={a.key}
                      className="px-1.5 py-0.5 font-mono text-[11px] tabular-nums text-slate-500"
                    >
                      {a.symbol} {a.type === "call" ? "C" : "P"} {a.strike.toFixed(2)}{" "}
                      {a.expiry} · was {a.verdict} · healed{" "}
                      {a.resolved_at ? `${ago(a.resolved_at)} ago` : ""}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <p className="mt-2 text-[10px] text-slate-600">
            Screening signals on ~15-min-delayed data — persistence-filtered,
            liquidity-gated, and still not arbitrage.
          </p>
        </div>
      )}
    </div>
  );
}
