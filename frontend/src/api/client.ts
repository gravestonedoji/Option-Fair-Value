import axios from "axios";
import type {
  Expiries,
  OptionChain,
  FairValueRequest,
  FairValueRange,
} from "../types";

const baseURL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

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
};
