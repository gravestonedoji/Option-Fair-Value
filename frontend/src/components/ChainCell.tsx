import clsx from "clsx";

interface Props {
  value: number | null;
  formatter: (v: number) => string;
  onClick?: () => void;
  isSelected?: boolean;
  isITM?: boolean;
}

export function ChainCell({
  value,
  formatter,
  onClick,
  isSelected,
  isITM,
}: Props) {
  return (
    <td
      onClick={onClick}
      className={clsx(
        "px-2 py-1 text-right font-mono text-xs tabular-nums cursor-pointer select-none transition-colors",
        isITM && "bg-slate-800/70",
        isSelected && "bg-sky-600/40 font-semibold",
        !isSelected && !isITM && "hover:bg-slate-800/50"
      )}
    >
      {value === null || value === undefined ? "—" : formatter(value)}
    </td>
  );
}
