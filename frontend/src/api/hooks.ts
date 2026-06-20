import { useQuery } from "@tanstack/react-query";
import { api } from "./client";
import type { FairValueRequest } from "../types";

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
