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
  /** The category imported credit card payments go to. */
  is_card_payments: boolean;
}

export interface BudgetItem {
  id: number;
  name: string;
  category: Category;
  amount: number;
  frequency: Frequency;
  monthly_amount: number;
  notes: string | null;
  /** Expenses paid with a credit card; a bank statement only shows them inside card payments. */
  paid_by_card: boolean;
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
  paid_by_card: boolean;
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
  /** 'manual' or 'statement' (imported from a bank statement). */
  source: string;
  statement_import_id: number | null;
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
  /** On the card payments line in a statement month: the paid-by-card budget items it covers. */
  card_items: string[];
}

/** Which transactions make up a month's totals; the other kind only explains them. */
export type TotalsFrom = 'statement' | 'manual';

export interface IncomeStatement {
  month: string;
  totals_from: TotalsFrom;
  has_statement: boolean;
  /** The household's own notes about the month. */
  notes: string | null;
  total_income: number;
  total_expenses: number;
  net: number;
  unexpected_income: number;
  unexpected_expenses: number;
  budgeted_income: number;
  budgeted_expenses: number;
  categories: StatementCategory[];
}

export interface PreviewAccount {
  key: string;
  name: string;
  kind: string;
  last4: string;
  beginning: number | null;
  ending: number | null;
  row_total: number;
  /** Ending − (beginning + rows); anything but 0 means some lines weren't read. */
  difference: number | null;
  account_id: number | null;
}

export interface PreviewRow {
  key: string;
  date: string;
  account_key: string;
  section: string;
  bank_type: string;
  description: string;
  /** Signed: deposits positive, withdrawals negative. */
  amount: number;
  category_id: number | null;
  skip: boolean;
  reason: string;
  duplicate: boolean;
}

export interface StatementPreview {
  bank: string;
  period_start: string;
  period_end: string;
  month: string;
  accounts: PreviewAccount[];
  rows: PreviewRow[];
}

export interface StatementImportInput {
  bank: string;
  file_name: string;
  period_start: string;
  period_end: string;
  accounts: Pick<PreviewAccount, 'key' | 'name' | 'beginning' | 'ending' | 'account_id'>[];
  rows: Pick<PreviewRow, 'key' | 'date' | 'account_key' | 'description' | 'amount' | 'category_id' | 'skip'>[];
  update_balances: boolean;
}

export interface StatementImport {
  id: number;
  bank: string;
  file_name: string;
  period_start: string;
  period_end: string;
  accounts: { key: string; name: string; beginning: string | null; ending: string | null; account_id: number | null }[];
  transaction_count: number;
  created_at: string;
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

/** Reference info for a credit card. Never card numbers or logins. */
export interface CreditCard {
  id: number;
  name: string;
  issuer: string | null;
  payment_url: string | null;
  annual_fee: number;
  /** 1-12: the month the annual fee posts. */
  annual_fee_month: number | null;
  benefits: string[];
  notes: string | null;
}

export type CreditCardInput = Omit<CreditCard, 'id'>;

// ---------- Companies ----------

export interface CompanyMember {
  id: number;
  name: string;
  /** 0-100. A company's members never total more than 100. */
  equity_percent: number;
}

export interface CompanyProduct {
  id: number;
  name: string;
  description: string | null;
}

export type CompanyProductInput = Omit<CompanyProduct, 'id'>;

export interface Company {
  id: number;
  name: string;
  description: string | null;
  members: CompanyMember[];
  products: CompanyProduct[];
}

export type CompanyInput = { name: string; description: string | null };
export type CompanyMemberInput = Omit<CompanyMember, 'id'>;

export interface CompanyListItem extends Omit<Company, 'products'> {
  year: number;
  income: number;
  expenses: number;
  net: number;
  contributions_total: number;
  distributions_total: number;
}

/** funding: money a revenue-share payee paid for their share. A liability repaid by payments to them, not income. */
export type CompanyEntryKind = 'income' | 'expense' | 'contribution' | 'distribution' | 'funding';

/** Entry kinds that belong to a member rather than a category. */
export const MEMBER_KINDS: CompanyEntryKind[] = ['contribution', 'distribution'];

export interface CompanyEntry {
  id: number;
  kind: CompanyEntryKind;
  date: string;
  description: string;
  amount: number;
  /** Income and expenses only. */
  category: string | null;
  /** Contributions and distributions only: who put the money in or was paid. */
  member_id: number | null;
  /** Income and expenses only. */
  product_id: number | null;
  /** Set on an expense that pays a revenue share, and on funding (required) from its payee. */
  revenue_share_id: number | null;
  notes: string | null;
  /** On a revenue-share payment: the part that repaid funding, so isn't an expense. */
  funding_repaid?: number | null;
}

export type CompanyEntryInput = Omit<CompanyEntry, 'id' | 'funding_repaid'>;

export interface CompanyMemberSummary {
  member_id: number;
  name: string;
  equity_percent: number;
  contributed_year: number;
  contributed_total: number;
  distributed_year: number;
  distributed_total: number;
  /** The year's net profit times their equity. A paper share, not money paid out. */
  profit_share: number;
}

export interface CompanyProductSummary {
  product_id: number | null;
  name: string;
  income: number;
  cost_of_revenue: number;
  other_expenses: number;
  net: number;
}

export interface CompanySummary {
  company_id: number;
  year: number;
  income: number;
  expenses: number;
  net: number;
  contributions_year: number;
  contributions_total: number;
  distributions_year: number;
  distributions_total: number;
  equity_assigned: number;
  /** Revenue-share payments and the fee categories agreements subtract. Part of `expenses`. */
  cost_of_revenue: number;
  /** Revenue-share funding received this year (a liability, not income). */
  funding_received: number;
  /** The part of this year's revenue-share payments that repaid funding. Not in `expenses`. */
  funding_repaid: number;
  months: { month: string; income: number; expenses: number }[];
  members: CompanyMemberSummary[];
  /** One row per product, then "No product" (product_id null) if anything is untagged. Empty without products. */
  products: CompanyProductSummary[];
  /** Years with entries, newest first. */
  years: number[];
  income_categories: string[];
  expense_categories: string[];
}

/** income: a % of recorded income (optionally one product's) after fee categories. reported: a % of revenue entered monthly. */
export type RevenueShareBasis = 'income' | 'reported';

export interface RevenueShareInput {
  payee: string;
  basis: RevenueShareBasis;
  product_id: number | null;
  rate_percent: number;
  /** Income basis: expense categories subtracted before the rate applies (platform fees). */
  deduct_categories: string[];
  start_date: string;
  end_date: string | null;
  /** Category for payment entries. */
  category: string;
  notes: string | null;
}

export interface RevenueShare extends RevenueShareInput {
  id: number;
  terms: string;
  earned_year: number;
  paid_year: number;
  earned_total: number;
  paid_total: number;
  /** Earned minus paid, all time. Negative means overpaid or paid ahead. */
  balance_due: number;
  /** Reported basis: finished months with no revenue entered ('YYYY-MM'), oldest first. */
  missing_months: string[];
  /** Funding received from the payee, repaid by payments, and still owed, all time. */
  funding_received: number;
  funding_repaid: number;
  funding_outstanding: number;
}

export interface RevenueShareMonth {
  month: string;
  /** Reported basis: null when nothing's been entered. */
  revenue: number | null;
  deductions: number;
  base: number;
  earned: number;
  paid: number;
  /** Balance due at the end of the month. */
  balance: number;
}
