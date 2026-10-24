export type CategoryKind = 'income' | 'expense';
export type CategoryColor = 'blue' | 'orange' | 'teal' | 'violet' | 'gold' | 'pink' | 'green' | 'plum' | 'gray';
export type Frequency = 'weekly' | 'biweekly' | 'semimonthly' | 'monthly' | 'quarterly' | 'annual';
export type AccountKind = 'asset' | 'liability';
export type AssetType = 'stock' | 'etf' | 'crypto' | 'cash';
export type DeductionType = 'retirement' | 'insurance' | 'hsa' | 'tax' | 'other';
export type DeductionStage = 'pre_tax' | 'tax' | 'post_tax';

export interface Category {
  id: number;
  name: string;
  kind: CategoryKind;
  color: CategoryColor;
  is_archived: boolean;
}

export interface BudgetItem {
  id: number;
  name: string;
  category: Category;
  amount: number;
  frequency: Frequency;
  monthly_amount: number;
  notes: string | null;
  /** Pay before deductions. When set, `amount` is take-home pay. */
  gross_amount: number | null;
  monthly_gross_amount: number | null;
  deductions: Deduction[];
}

export interface Deduction {
  name: string;
  type: DeductionType;
  pre_tax: boolean;
  amount: number;
}

export interface BudgetItemInput {
  name: string;
  category_id: number;
  amount: number;
  frequency: Frequency;
  notes: string | null;
  gross_amount: number | null;
  deductions: Deduction[];
}

/** Yearly totals for one paycheck or all combined; divide by 12 for monthly, or paychecks_per_year for one paycheck. */
export interface PaycheckBreakdown {
  budget_item_id: number | null;
  name: string;
  paychecks: number;
  paychecks_per_year: number | null;
  annual_gross: number;
  annual_pre_tax: number;
  annual_taxes: number;
  annual_after_tax: number;
  annual_post_tax: number;
  annual_unitemized: number;
  annual_take_home: number;
  lines: { name: string; type: DeductionType; stage: DeductionStage; annual_amount: number }[];
}

export interface BudgetSummary {
  monthly_income: number;
  monthly_expenses: number;
  monthly_surplus: number;
  by_category: { category_id: number; name: string; kind: CategoryKind; color: CategoryColor; monthly_amount: number }[];
  paycheck: PaycheckBreakdown | null;
  paycheck_items: PaycheckBreakdown[];
}

export interface Account {
  id: number;
  name: string;
  kind: AccountKind;
  subtype: string;
  sync_from_holdings: boolean;
  is_archived: boolean;
  notes: string | null;
}

export interface AccountInput {
  name: string;
  kind: AccountKind;
  subtype: string;
  sync_from_holdings: boolean;
  notes: string | null;
}

export interface BalanceRow {
  account: Account;
  balance: number | null;
  previous_balance: number | null;
}

export interface BalanceSheet {
  month: string;
  rows: BalanceRow[];
  total_assets: number;
  total_liabilities: number;
  net_worth: number;
}

export interface NetWorthPoint {
  month: string;
  /** Null for a month with nothing recorded between recorded months. */
  assets: number | null;
  liabilities: number | null;
  net_worth: number | null;
}

export interface Transaction {
  id: number;
  date: string;
  description: string;
  amount: number;
  category: Category;
  is_unexpected: boolean;
  notes: string | null;
  account_id: number | null;
  source: string;
}

export interface TransactionInput {
  date: string;
  description: string;
  amount: number;
  category_id: number;
  is_unexpected: boolean;
  notes: string | null;
  account_id: number | null;
}

export interface StatementCategory {
  category_id: number;
  name: string;
  kind: CategoryKind;
  color: CategoryColor;
  actual: number;
  unexpected: number;
  budgeted: number;
}

export interface IncomeStatement {
  month: string;
  total_income: number;
  total_expenses: number;
  net: number;
  unexpected_income: number;
  unexpected_expenses: number;
  budgeted_income: number;
  budgeted_expenses: number;
  categories: StatementCategory[];
}

export interface IncomeTrendPoint {
  month: string;
  income: number;
  expenses: number;
  net: number;
  unexpected_income: number;
  unexpected_expenses: number;
}

export interface Holding {
  id: number;
  ticker: string;
  asset_type: AssetType;
  quantity: number;
  /** What was paid per share/coin. */
  cost_per_unit: number | null;
  /** Total cost: quantity x cost_per_unit. */
  cost_basis: number | null;
  account_id: number | null;
  account_name: string | null;
  notes: string | null;
  price: number | null;
  price_date: string | null;
  previous_close: number | null;
  market_value: number | null;
  day_change: number | null;
  gain: number | null;
}

export interface HoldingInput {
  ticker: string;
  asset_type: AssetType;
  quantity: number;
  cost_per_unit: number | null;
  account_id: number | null;
  notes: string | null;
}

export interface RefreshRun {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: 'running' | 'success' | 'partial' | 'failed';
  tickers_updated: number;
  message: string | null;
}

export interface PortfolioSummary {
  total_value: number;
  total_cost: number | null;
  total_gain: number | null;
  day_change: number;
  last_refresh: RefreshRun | null;
}

export interface PortfolioPoint {
  date: string;
  value: number;
}

