import dayjs from 'dayjs';

const currency = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });
const currencyWhole = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
const compact = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: 'compact', maximumFractionDigits: 1 });

export const money = (n: number | null | undefined) => (n == null ? '—' : currency.format(n));
export const moneyWhole = (n: number | null | undefined) => (n == null ? '—' : currencyWhole.format(n));
export const moneyCompact = (n: number) => compact.format(n);

/** "+$1,234.56" / "−$1,234.56" — the sign is always spelled out, never left to color. */
export const signedMoney = (n: number | null | undefined) =>
  n == null ? '—' : `${n > 0 ? '+' : n < 0 ? '−' : ''}${currency.format(Math.abs(n))}`;

export const quantity = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 8 });

export const percent = (n: number) => `${(n * 100).toFixed(1)}%`;
export const signedPercent = (n: number) => `${n > 0 ? '+' : n < 0 ? '−' : ''}${percent(Math.abs(n))}`;

// Months travel as 'YYYY-MM'.
export const thisMonth = () => dayjs().format('YYYY-MM');
export const shiftMonth = (month: string, n: number) => dayjs(`${month}-01`).add(n, 'month').format('YYYY-MM');
export const monthLabel = (month: string) => dayjs(`${month}-01`).format('MMMM YYYY');
export const monthShort = (month: string) => dayjs(`${month}-01`).format("MMM 'YY");
export const dateLabel = (date: string) => dayjs(date).format('MMM D, YYYY');

export const FREQUENCY_LABELS: Record<string, string> = {
  weekly: 'Weekly',
  biweekly: 'Every 2 weeks',
  semimonthly: 'Twice a month',
  monthly: 'Monthly',
  quarterly: 'Quarterly',
  annual: 'Yearly',
};

export const DEDUCTION_TYPE_LABELS: Record<string, string> = {
  retirement: 'Retirement',
  insurance: 'Insurance',
  hsa: 'HSA / FSA',
  tax: 'Tax',
  other: 'Other',
};

export const ASSET_SUBTYPES: Record<string, string> = {
  checking: 'Checking',
  savings: 'Savings',
  brokerage: 'Brokerage',
  retirement: 'Retirement (401k/IRA)',
  hsa: 'HSA',
  crypto: 'Crypto',
  real_estate: 'Real estate',
  vehicle: 'Vehicle',
  cash: 'Cash',
  other_asset: 'Other asset',
};

export const LIABILITY_SUBTYPES: Record<string, string> = {
  mortgage: 'Mortgage',
  auto_loan: 'Auto loan',
  student_loan: 'Student loan',
  credit_card: 'Credit card',
  personal_loan: 'Personal loan',
  heloc: 'HELOC',
  other_liability: 'Other debt',
};

export const subtypeLabel = (s: string) => ASSET_SUBTYPES[s] ?? LIABILITY_SUBTYPES[s] ?? s;

/** Keep legend entries in series order (Recharts 3 sorts them alphabetically by default). */
const SERIES_RANK: Record<string, number> = { Income: 0, Expenses: 1, Net: 2 };
export const SERIES_ORDER = (item: { value?: unknown }) => SERIES_RANK[String(item.value)] ?? 3;
