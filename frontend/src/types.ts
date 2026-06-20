export type OptionType = "call" | "put";
export type ExerciseStyle = "european" | "american";

export interface OptionQuote {
  strike: number;
  bid: number | null;
  ask: number | null;
  mid: number | null;
  iv: number | null; // decimal, 0.20 = 20%
  open_interest: number | null;
  volume: number | null;
  in_the_money: boolean | null;
}

export interface OptionChainRow {
  strike: number;
  call: OptionQuote;
  put: OptionQuote;
}

export interface OptionChain {
  symbol: string;
  expiry: string; // ISO date "YYYY-MM-DD"
  spot: number;
  rows: OptionChainRow[];
  cached_at: string; // ISO datetime
}

export interface Expiries {
  symbol: string;
  expiries: string[]; // ISO dates
  cached_at: string;
}

export interface InputBands {
  vol_pct: number; // e.g., 0.20 for ±20% relative on IV
  spot_pct: number; // e.g., 0.05 for ±5% relative on spot
  rate_bps: number; // e.g., 50 for ±50 bps absolute
  dte_days: number; // e.g., 2 for ±2 days
}

export interface OptionInputs {
  spot: number;
  strike: number;
  time_to_expiry: number; // in years
  risk_free_rate: number;
  dividend_yield: number;
  volatility: number;
  option_type: OptionType;
  style: ExerciseStyle;
}

export interface Greeks {
  price: number;
  delta: number | null;
  gamma: number | null;
  theta: number | null;
  vega: number | null;
  rho: number | null;
}

export interface ModelRange {
  name: string; // "black_scholes" | "binomial" | "monte_carlo"
  base: number;
  min: number;
  p5: number;
  median: number;
  p95: number;
  max: number;
  greeks: Greeks;
}

export interface FairValueRange {
  models: Record<string, ModelRange>;
  bands: InputBands;
  base_inputs: OptionInputs;
  base_results: Record<string, Greeks>;
  samples: Record<string, number[]>;
}

export interface FairValueRequest {
  symbol: string;
  expiry: string;
  strike: number;
  type: OptionType;
  bands: InputBands;
  overrides?: Partial<OptionInputs>;
}
