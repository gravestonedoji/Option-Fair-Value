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

// --- IV relative-value analysis (mirrors backend/app/analysis/models.py) ----

export type Verdict = "rich" | "cheap";

export interface AnalysisParams {
  z_threshold: number;
  max_rel_spread: number;
  min_open_interest: number;
  min_volume: number;
  min_fit_points: number;
  fit_degree: number;
  near_atm_pairs: number;
  min_parity_pairs: number;
  mad_floor: number;
  fit_band_stdevs: number;
  min_fit_band: number;
}

export interface ContractAnalysis {
  strike: number;
  type: OptionType;
  bid: number | null;
  ask: number | null;
  mid: number | null;
  rel_spread: number | null;
  open_interest: number | null;
  volume: number | null;
  is_otm: boolean;
  log_moneyness: number; // ln(K / F)
  iv: number | null;
  iv_source: "model" | "yfinance" | "none";
  iv_status: string;
  vega: number | null;
  fitted_iv: number | null;
  residual: number | null;
  z: number | null;
  fitted_price: number | null;
  price_edge: number | null; // mid - fitted_price
  used_in_fit: boolean;
  filters_failed: string[];
  verdict: Verdict | null;
}

export interface ParityRecord {
  strike: number;
  call_mid: number | null;
  put_mid: number | null;
  implied_forward: number | null;
  deviation: number | null;
  deviation_vs_spread: number | null;
  check_flag: boolean;
}

export interface SmileFitInfo {
  fitted: boolean;
  reason: "insufficient_points" | "degenerate_k_range" | null;
  degree: number | null;
  coefficients: number[]; // numpy polyfit order: highest power first
  n_used: number;
  n_dropped: number;
  rmse: number | null;
  sigma_mad: number | null;
  k_min: number | null;
  k_max: number | null;
}

export interface ChainAnalysis {
  symbol: string;
  expiry: string; // ISO date
  spot: number;
  forward: number;
  forward_source: "parity" | "spot_carry_fallback";
  n_parity_pairs: number;
  risk_free_rate: number;
  rate_source: "fred" | "fallback";
  time_to_expiry: number;
  params: AnalysisParams;
  fit: SmileFitInfo;
  contracts: ContractAnalysis[];
  parity: ParityRecord[];
  flagged_count: number;
  chain_cached_at: string;
  computed_at: string;
}

export interface AnalysisQueryParams {
  z_threshold?: number;
  max_rel_spread?: number;
  min_open_interest?: number;
  min_volume?: number;
}

// --- scanner alerts (mirrors backend/app/analysis/scanner.py) ---------------

export interface AlertRecord {
  key: string;
  symbol: string;
  expiry: string; // ISO date
  type: OptionType;
  strike: number;
  verdict: Verdict;
  z: number;
  price_edge: number | null;
  mid: number | null;
  fitted_price: number | null;
  iv: number | null;
  fitted_iv: number | null;
  rel_spread: number | null;
  open_interest: number | null;
  status: "pending" | "active" | "resolved";
  streak: number;
  first_seen: string; // ISO datetime
  last_seen: string;
  resolved_at: string | null;
}

export interface ScannerStatus {
  enabled: boolean;
  market_open: boolean;
  scanning: boolean;
  watchlist: string[];
  interval_seconds: number;
  persistence_scans: number;
  last_scan_started: string | null;
  last_scan_completed: string | null;
  last_scan_chain_count: number;
  last_scan_errors: string[];
  next_scan_at: string | null;
}

export interface AlertsResponse {
  status: ScannerStatus;
  active: AlertRecord[];
  pending: AlertRecord[];
  resolved: AlertRecord[];
}
