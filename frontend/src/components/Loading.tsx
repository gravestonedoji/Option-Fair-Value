import clsx from "clsx";

export function Spinner({ className }: { className?: string }) {
  return (
    <div
      className={clsx(
        "inline-block h-5 w-5 animate-spin rounded-full border-2 border-slate-600 border-t-sky-400",
        className
      )}
      role="status"
      aria-label="loading"
    />
  );
}

export function Skeleton({
  className,
}: {
  className?: string;
}) {
  return (
    <div
      className={clsx(
        "animate-pulse rounded bg-slate-800/70",
        className
      )}
    />
  );
}
