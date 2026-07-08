import axios from "axios";
import type {
  AlertsResponse,
  AnalysisQueryParams,
  ChainAnalysis,
  Expiries,
  OptionChain,
  FairValueRequest,
  FairValueRange,
} from "../types";

// The API is same-origin in every mode: production builds are served by the
// FastAPI backend itself, and the Vite dev server proxies all API routes to
// it (see vite.config.ts). Same-origin also keeps remote access working when
// the app is reached over LAN or Tailscale instead of localhost. Set
// VITE_API_BASE_URL only for split deploys where the API lives elsewhere.
const baseURL = import.meta.env.VITE_API_BASE_URL || "";

export const http = axios.create({
  baseURL,
  headers: { "Content-Type": "application/json" },
});

export const api = {
  async getExpiries(symbol: string): Promise<Expiries> {
    const { data } = await http.get<Expiries>(`/expiries/${encodeURIComponent(symbol)}`);
    return data;
  },
  async getChain(symbol: string, expiry: string): Promise<OptionChain> {
    const { data } = await http.get<OptionChain>(
      `/chain/${encodeURIComponent(symbol)}`,
      { params: { expiry } }
    );
    return data;
  },
  async computeFairValue(req: FairValueRequest): Promise<FairValueRange> {
    const { data } = await http.post<FairValueRange>("/fairvalue", req);
    return data;
  },
  async getAnalysis(
    symbol: string,
    expiry: string,
    params?: AnalysisQueryParams
  ): Promise<ChainAnalysis> {
    const { data } = await http.get<ChainAnalysis>(
      `/analysis/${encodeURIComponent(symbol)}`,
      { params: { expiry, ...params } }
    );
    return data;
  },
  async getAlerts(): Promise<AlertsResponse> {
    const { data } = await http.get<AlertsResponse>("/alerts");
    return data;
  },
  async triggerScan(): Promise<AlertsResponse> {
    const { data } = await http.post<AlertsResponse>("/alerts/scan");
    return data;
  },
};
