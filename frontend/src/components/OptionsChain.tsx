import { useMemo } from "react";
import clsx from "clsx";
import type {
  ChainAnalysis,
  ContractAnalysis,
  OptionChain,
  OptionQuote,
  OptionType,
} from "../types";
import { ChainCell } from "./ChainCell";

interface Props {
  chain: OptionChain;
  selectedStrike: number | null;
  selectedType: OptionType | null;
  onSelect: (strike: number, type: OptionType, quote: OptionQuote) => void;
  analysis?: ChainAnalysis | null;
}

function flagTitle(c: ContractAnalysis): string {
  const z = c.z === null ? "" : ` · z=${c.z >= 0 ? "+" : ""}${c.z.toFixed(1)}`;
  const ivs =
    c.fitted_iv !== null && c.iv !== null
      ? ` · fit ${(c.fitted_iv * 100).toFixed(1)}% vs mkt ${(c.iv * 100).toFixed(1)}%`
      : "";
  return `${c.verdict}${z}${ivs}`;
}

const fmtPrice = (v: number) => v.toFixed(2);
const fmtIV = (v: number) => `${(v * 100).toFixed(1)}%`;
const fmtOI = (v: number) => v.toLocaleString("en-US");

function nearestStrikeIndex(rows: { strike: number }[], spot: number): number {
  let best = 0;
  let bestDiff = Infinity;
  for (let i = 0; i < rows.length; i++) {
    const diff = Math.abs(rows[i].strike - spot);
    if (diff < bestDiff) {
      bestDiff = diff;
      best = i;
    }
  }
  return best;
}

export function OptionsChain({
  chain,
  selectedStrike,
  selectedType,
  onSelect,
  analysis,
}: Props) {
  const atmIdx = nearestStrikeIndex(chain.rows, chain.spot);

  // Only contracts with a verdict get a visual flag in the table.
  const flagged = useMemo(() => {
    const map = new Map<string, ContractAnalysis>();
    for (const c of analysis?.contracts ?? []) {
      if (c.verdict !== null) map.set(`${c.type}:${c.strike}`, c);
    }
    return map;
  }, [analysis]);

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-lg border border-slate-800 bg-slate-900">
      <div className="flex items-center justify-between border-b border-slate-800 px-4 py-2">
        <div className="text-sm font-semibold text-slate-200">
          {chain.symbol}{" "}
          <span className="text-slate-500">@</span>{" "}
          <span className="text-emerald-400">${fmtPrice(chain.spot)}</span>
        </div>
        <div className="text-xs text-slate-500">
          Expiry {chain.expiry} · {chain.rows.length} strikes
        </div>
      </div>

      <div className="max-h-[70vh] overflow-auto">
        <table className="w-full border-collapse text-sm">
          <thead className="sticky top-0 z-10 bg-slate-900">
            <tr className="border-b border-slate-800 text-xs uppercase tracking-wide text-slate-400">
              <th colSpan={5} className="px-2 py-2 text-center text-emerald-400">
                CALLS
              </th>
              <th className="px-2 py-2 text-center text-slate-200">STRIKE</th>
              <th colSpan={5} className="px-2 py-2 text-center text-rose-400">
                PUTS
              </th>
            </tr>
            <tr className="border-b border-slate-800 text-[10px] uppercase tracking-wide text-slate-500">
              <th className="px-2 py-1 text-right">Bid</th>
              <th className="px-2 py-1 text-right">Ask</th>
              <th className="px-2 py-1 text-right">Mid</th>
              <th className="px-2 py-1 text-right">IV</th>
              <th className="px-2 py-1 text-right">OI</th>
              <th className="px-2 py-1 text-center"></th>
              <th className="px-2 py-1 text-right">Bid</th>
              <th className="px-2 py-1 text-right">Ask</th>
              <th className="px-2 py-1 text-right">Mid</th>
              <th className="px-2 py-1 text-right">IV</th>
              <th className="px-2 py-1 text-right">OI</th>
            </tr>
          </thead>
          <tbody>
            {chain.rows.map((row, idx) => {
              const isATM = idx === atmIdx;
              const callSelected =
                selectedStrike === row.strike && selectedType === "call";
              const putSelected =
                selectedStrike === row.strike && selectedType === "put";
              const callFlag = flagged.get(`call:${row.strike}`);
              const putFlag = flagged.get(`put:${row.strike}`);

              return (
                <tr
                  key={row.strike}
                  className={clsx(
                    "border-b border-slate-800/60 group",
                    isATM && "border-l-2 border-l-sky-500",
                    "hover:bg-slate-800/30"
                  )}
                >
                  <ChainCell
                    value={row.call.bid}
                    formatter={fmtPrice}
                    onClick={() => onSelect(row.strike, "call", row.call)}
                    isSelected={callSelected}
                    isITM={row.call.in_the_money ?? false}
                  />
                  <ChainCell
                    value={row.call.ask}
                    formatter={fmtPrice}
                    onClick={() => onSelect(row.strike, "call", row.call)}
                    isSelected={callSelected}
                    isITM={row.call.in_the_money ?? false}
                  />
                  <ChainCell
                    value={row.call.mid}
                    formatter={fmtPrice}
                    onClick={() => onSelect(row.strike, "call", row.call)}
                    isSelected={callSelected}
                    isITM={row.call.in_the_money ?? false}
                    flag={callFlag?.verdict ?? null}
                    flagTitle={callFlag ? flagTitle(callFlag) : undefined}
                  />
                  <ChainCell
                    value={row.call.iv}
                    formatter={fmtIV}
                    onClick={() => onSelect(row.strike, "call", row.call)}
                    isSelected={callSelected}
                    isITM={row.call.in_the_money ?? false}
                    flag={callFlag?.verdict ?? null}
                    flagTitle={callFlag ? flagTitle(callFlag) : undefined}
                  />
                  <ChainCell
                    value={row.call.open_interest}
                    formatter={fmtOI}
                    onClick={() => onSelect(row.strike, "call", row.call)}
                    isSelected={callSelected}
                    isITM={row.call.in_the_money ?? false}
                  />

                  <td
                    className={clsx(
                      "px-2 py-1 text-center font-bold font-mono tabular-nums",
                      isATM ? "text-sky-300" : "text-slate-100",
                      "bg-slate-900/60"
                    )}
                  >
                    {fmtPrice(row.strike)}
                  </td>

                  <ChainCell
                    value={row.put.bid}
                    formatter={fmtPrice}
                    onClick={() => onSelect(row.strike, "put", row.put)}
                    isSelected={putSelected}
                    isITM={row.put.in_the_money ?? false}
                  />
                  <ChainCell
                    value={row.put.ask}
                    formatter={fmtPrice}
                    onClick={() => onSelect(row.strike, "put", row.put)}
                    isSelected={putSelected}
                    isITM={row.put.in_the_money ?? false}
                  />
                  <ChainCell
                    value={row.put.mid}
                    formatter={fmtPrice}
                    onClick={() => onSelect(row.strike, "put", row.put)}
                    isSelected={putSelected}
                    isITM={row.put.in_the_money ?? false}
                    flag={putFlag?.verdict ?? null}
                    flagTitle={putFlag ? flagTitle(putFlag) : undefined}
                  />
                  <ChainCell
                    value={row.put.iv}
                    formatter={fmtIV}
                    onClick={() => onSelect(row.strike, "put", row.put)}
                    isSelected={putSelected}
                    isITM={row.put.in_the_money ?? false}
                    flag={putFlag?.verdict ?? null}
                    flagTitle={putFlag ? flagTitle(putFlag) : undefined}
                  />
                  <ChainCell
                    value={row.put.open_interest}
                    formatter={fmtOI}
                    onClick={() => onSelect(row.strike, "put", row.put)}
                    isSelected={putSelected}
                    isITM={row.put.in_the_money ?? false}
                  />
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
