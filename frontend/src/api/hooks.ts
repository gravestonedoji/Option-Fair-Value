import { useQuery } from "@tanstack/react-query";
import { api } from "./client";
import type { AnalysisQueryParams, FairValueRequest } from "../types";

export function useExpiries(symbol: string | null) {
  return useQuery({
    queryKey: ["expiries", symbol],
    queryFn: () => api.getExpiries(symbol as string),
    enabled: !!symbol,
    staleTime: 60 * 60 * 1000, // 1h
  });
}

export function useChain(symbol: string | null, expiry: string | null) {
  return useQuery({
    queryKey: ["chain", symbol, expiry],
    queryFn: () => api.getChain(symbol as string, expiry as string),
    enabled: !!symbol && !!expiry,
    staleTime: 60 * 1000, // 60s
  });
}

export function useFairValue(req: FairValueRequest | null) {
  return useQuery({
    queryKey: ["fairvalue", req],
    queryFn: () => api.computeFairValue(req as FairValueRequest),
    enabled: !!req,
    staleTime: 60 * 1000,
  });
}

export function useAnalysis(
  symbol: string | null,
  expiry: string | null,
  params?: AnalysisQueryParams
) {
  return useQuery({
    queryKey: ["analysis", symbol, expiry, params],
    queryFn: () => api.getAnalysis(symbol as string, expiry as string, params),
    enabled: !!symbol && !!expiry,
    staleTime: 60 * 1000,
  });
}

export function useAlerts() {
  return useQuery({
    queryKey: ["alerts"],
    queryFn: () => api.getAlerts(),
    // Poll fast while a sweep is in flight so the feed updates promptly when
    // it finishes; otherwise the scanner only changes on its own cadence.
    refetchInterval: (query) =>
      query.state.data?.status.scanning ? 3 * 1000 : 60 * 1000,
    staleTime: 0,
  });
}
