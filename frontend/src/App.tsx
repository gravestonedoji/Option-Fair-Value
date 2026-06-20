import { useMemo, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SymbolSearch } from "./components/SymbolSearch";
import { ExpirySelector } from "./components/ExpirySelector";
import { OptionsChain } from "./components/OptionsChain";
import { FairValuePanel } from "./components/FairValuePanel";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Spinner } from "./components/Loading";
import { useExpiries, useChain } from "./api/hooks";
import type { OptionQuote, OptionType } from "./types";

interface Selection {
  strike: number;
  type: OptionType;
  quote: OptionQuote;
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

function Dashboard() {
  const [symbol, setSymbol] = useState<string | null>(null);
  const [expiry, setExpiry] = useState<string | null>(null);
  const [selected, setSelected] = useState<Selection | null>(null);

  const expiriesQuery = useExpiries(symbol);
  const chainQuery = useChain(symbol, expiry);

  function handleSymbolSelect(sym: string) {
    setSymbol(sym);
    setExpiry(null);
    setSelected(null);
  }

  function handleExpiryChange(exp: string) {
    setExpiry(exp);
    setSelected(null);
  }

  function handleSelect(
    strike: number,
    type: OptionType,
    quote: OptionQuote
  ) {
    setSelected({ strike, type, quote });
  }

  const expiryList = useMemo(
    () => expiriesQuery.data?.expiries,
    [expiriesQuery.data]
  );

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-900/60">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-3">
          <h1 className="text-lg font-semibold tracking-tight text-slate-100">
            Option Fair Value Dashboard
          </h1>
          <SymbolSearch onSelect={handleSymbolSelect} current={symbol} />
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-4">
        {!symbol && (
          <div className="flex h-64 items-center justify-center text-sm text-slate-500">
            Search or select a symbol to begin.
          </div>
        )}

        {symbol && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center gap-4">
              <ExpirySelector
                expiries={expiryList}
                value={expiry}
                onChange={handleExpiryChange}
              />
              {expiriesQuery.isFetching && <Spinner className="h-4 w-4" />}
              {expiriesQuery.isError && (
                <span className="text-xs text-rose-400">
                  Failed to load expiries.
                </span>
              )}
            </div>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
              <div className="lg:col-span-3">
                {!expiry && (
                  <div className="flex h-64 items-center justify-center rounded-lg border border-slate-800 bg-slate-900 text-sm text-slate-500">
                    Select an expiry to load the chain.
                  </div>
                )}
                {expiry && chainQuery.isLoading && (
                  <div className="flex h-64 items-center justify-center rounded-lg border border-slate-800 bg-slate-900">
                    <Spinner />
                  </div>
                )}
                {expiry && chainQuery.isError && (
                  <div className="flex h-64 items-center justify-center rounded-lg border border-slate-800 bg-slate-900 text-sm text-rose-400">
                    Failed to load chain.
                  </div>
                )}
                {expiry && chainQuery.data && (
                  <OptionsChain
                    chain={chainQuery.data}
                    selectedStrike={selected?.strike ?? null}
                    selectedType={selected?.type ?? null}
                    onSelect={handleSelect}
                  />
                )}
              </div>

              <div className="lg:col-span-2">
                {selected ? (
                  <FairValuePanel
                    symbol={symbol}
                    expiry={expiry ?? ""}
                    strike={selected.strike}
                    type={selected.type}
                    quote={selected.quote}
                  />
                ) : (
                  <div className="flex h-64 items-center justify-center rounded-lg border border-slate-800 bg-slate-900 text-sm text-slate-500">
                    Select a call or put from the chain.
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <Dashboard />
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
