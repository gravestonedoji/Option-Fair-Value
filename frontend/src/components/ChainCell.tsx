import clsx from "clsx";
import type { Verdict } from "../types";

interface Props {
  value: number | null;
  formatter: (v: number) => string;
  onClick?: () => void;
  isSelected?: boolean;
  isITM?: boolean;
  flag?: Verdict | null;
  flagTitle?: string;
}

export function ChainCell({
  value,
  formatter,
  onClick,
  isSelected,
  isITM,
  flag,
  flagTitle,
}: Props) {
  return (
    <td
      onClick={onClick}
      title={flagTitle}
      className={clsx(
        "px-2 py-1 text-right font-mono text-xs tabular-nums cursor-pointer select-none transition-colors",
        isITM && "bg-slate-800/70",
        isSelected && "bg-sky-600/40 font-semibold",
        !isSelected && !isITM && "hover:bg-slate-800/50",
        // inset rings overlay cleanly on the ITM/selected backgrounds
        flag === "rich" && "ring-1 ring-inset ring-amber-400/70",
        flag === "cheap" && "ring-1 ring-inset ring-teal-300/70"
      )}
    >
      {value === null || value === undefined ? "—" : formatter(value)}
    </td>
  );
}
