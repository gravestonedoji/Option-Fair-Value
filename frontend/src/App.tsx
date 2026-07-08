import { useEffect, useMemo, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SymbolSearch } from "./components/SymbolSearch";
import { ExpirySelector } from "./components/ExpirySelector";
import { OptionsChain } from "./components/OptionsChain";
import { FairValuePanel } from "./components/FairValuePanel";
import { IVSmilePanel } from "./components/IVSmilePanel";
import { MispricingList } from "./components/MispricingList";
import { AlertsPanel } from "./components/AlertsPanel";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Spinner } from "./components/Loading";
import { useExpiries, useChain, useAnalysis } from "./api/hooks";
import type { OptionQuote, OptionType } from "./types";

interface Selection {
  strike: number;
  type: OptionType;
  quote: OptionQuote;
}

interface PendingSelection {
  symbol: string;
  expiry: string;
  strike: number;
  type: OptionType;
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
  const [pendingSel, setPendingSel] = useState<PendingSelection | null>(null);

  const expiriesQuery = useExpiries(symbol);
  const chainQuery = useChain(symbol, expiry);
  const analysisQuery = useAnalysis(symbol, expiry);

  function handleSymbolSelect(sym: string) {
    setSymbol(sym);
    setExpiry(null);
    setSelected(null);
    setPendingSel(null);
  }

  function handleExpiryChange(exp: string) {
    setExpiry(exp);
    setSelected(null);
    setPendingSel(null);
  }

  function handleSelect(
    strike: number,
    type: OptionType,
    quote: OptionQuote
  ) {
    setSelected({ strike, type, quote });
  }

  function handleAlertSelect(
    sym: string,
    exp: string,
    strike: number,
    type: OptionType
  ) {
    setSymbol(sym);
    setExpiry(exp);
    setSelected(null);
    setPendingSel({ symbol: sym, expiry: exp, strike, type });
  }

  // Alert deep-link: once the chain for the alert's symbol/expiry arrives,
  // select the flagged contract as if it had been clicked in the table.
  useEffect(() => {
    if (!pendingSel || !chainQuery.data) return;
    if (symbol !== pendingSel.symbol || expiry !== pendingSel.expiry) return;
    // A stale cached chain is served synchronously while a background refetch
    // runs; wait for the refetch so the selection snapshots fresh quotes and
    // sees strikes the cached copy may not have had yet.
    if (chainQuery.isFetching) return;
    const row = chainQuery.data.rows.find((r) => r.strike === pendingSel.strike);
    if (row) {
      const quote = pendingSel.type === "call" ? row.call : row.put;
      setSelected({ strike: pendingSel.strike, type: pendingSel.type, quote });
    }
    setPendingSel(null);
  }, [pendingSel, chainQuery.data, chainQuery.isFetching, symbol, expiry]);

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

      <main className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-4">
        <AlertsPanel onSelectAlert={handleAlertSelect} />

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
                    analysis={analysisQuery.data ?? null}
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

            {expiry && (
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
                {analysisQuery.isLoading && (
                  <div className="flex h-48 items-center justify-center gap-2 rounded-lg border border-slate-800 bg-slate-900 text-sm text-slate-400 lg:col-span-5">
                    <Spinner className="h-4 w-4" />
                    Analyzing IV smile…
                  </div>
                )}
                {analysisQuery.isError && (
                  <div className="flex h-48 items-center justify-center rounded-lg border border-slate-800 bg-slate-900 text-sm text-rose-400 lg:col-span-5">
                    IV analysis unavailable for this expiry.
                  </div>
                )}
                {analysisQuery.data && chainQuery.data && (
                  <>
                    <div className="lg:col-span-3">
                      <IVSmilePanel analysis={analysisQuery.data} />
                    </div>
                    <div className="lg:col-span-2">
                      <MispricingList
                        analysis={analysisQuery.data}
                        chain={chainQuery.data}
                        onSelect={handleSelect}
                      />
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </main>

      <footer className="mx-auto max-w-7xl px-4 py-6 text-center text-xs text-slate-600">
        Market data is delayed (~15 min) and may be incomplete. Model outputs
        are estimates for educational purposes only — not financial advice.
      </footer>
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
