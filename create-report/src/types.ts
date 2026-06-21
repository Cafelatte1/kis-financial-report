export interface Holding {
  symbol: string; name: string; country: string;
  qty: number; cost_basis: number; avg_cost: number;
  price: number | null; value: number | null;
  unrealized: number | null; unrealized_pct: number | null; priced: boolean;
  beta: number | null; pe: number | null; pb: number | null;
  div_yield: number | null; sector: string | null;
  fin?: Record<string, number | string | null>;
}
export interface Kpi {
  invested: number; returned: number; realized_pnl: number;
  market_value: number; unrealized: number; unrealized_pct: number | null;
  irr_annual: number | null; holdings_count: number; trades_count: number;
  period: [string, string];
}
export interface Weighted { beta: number | null; pe: number | null; pb: number | null; div_yield: number | null; }
export interface Alloc { key: string; value: number; }
export interface TimelinePoint { month: string; cum_invested: number; cum_returned: number; }

export interface ClosedPos {
  symbol: string; name: string; country: string;
  pnl: number; pnl_pct: number | null; proceeds: number; cost: number;
  first_buy: string | null; last_sell: string | null;
  hold_days: number | null; buy_count: number; sell_count: number;
}
export interface Closed {
  positions: ClosedPos[]; count: number; total_pnl: number;
  win_rate: number | null; avg_win: number | null; avg_loss: number | null; profit_factor: number | null;
}

export interface MonthlyPoint {
  month: string; value: number | null; port_ret: number | null;
  SP500_ret: number | null; ACWI_ret: number | null;
  buy: number; sell: number; n_trades: number; realized: number;
  value_chg: number | null;
  new: { symbol: string; name: string }[];
  closed: { symbol: string; name: string }[];
}
export type MonthlyLatest = MonthlyPoint;

export interface DailyPoint { date: string; port: number; value?: number; SP500: number; ACWI: number; }
export interface YearRet { year: string; port: number | null; SP500: number | null; ACWI: number | null; }
export interface Returns {
  weekly: DailyPoint[]; yearly: YearRet[];
  start: string; end: string | null; coverage: number | null; benchmarks: string[];
}
export interface Style { adj_alpha_annual: number | null; market_beta: number | null; growth_beta: number | null; }
export interface StyleCmp { key: string; ticker: string; corr: number | null; cum_pct: number | null; excess_pct: number | null; }
export interface Contribution {
  symbol: string; name: string; realized: number; unrealized: number; total: number;
  realized_pct: number | null; unrealized_pct: number | null;
}
export interface SectorTilt { sector: string; port_pct: number; bench_pct: number | null; diff: number | null; }
export interface Skill {
  beta: number | null; alpha_annual: number | null; corr: number | null;
  tracking_error: number | null; info_ratio: number | null;
  up_capture: number | null; down_capture: number | null;
  sharpe: number | null; sortino: number | null; win_rate: number | null; vs: string;
}
export interface DayMark { date: string | null; ret: number | null; }
export interface MonthMark { month: string | null; ret: number | null; }
export interface Risk {
  mdd: number | null; vol_annual: number | null;
  best_day: DayMark; worst_day: DayMark; best_month: MonthMark; worst_month: MonthMark;
  max_up_streak: number; max_down_streak: number;
}

export interface Report {
  asof: string; base_ccy: string; fx: Record<string, number>;
  kpi: Kpi; holdings: Holding[]; weighted: Weighted; fin_weighted: Record<string, number | null>; sectors: Alloc[];
  closed: Closed; timeline: TimelinePoint[];
  monthly: MonthlyPoint[]; monthly_latest: MonthlyLatest | null;
  contributions: Contribution[]; sector_tilt: SectorTilt[];
  returns: Returns; skill: Skill; risk: Risk; style: Style; styles: StyleCmp[];
}
