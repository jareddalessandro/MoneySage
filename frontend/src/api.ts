import type {
  Account,
  AccountInput,
  BalanceSheet,
  BudgetItem,
  BudgetItemInput,
  BudgetSummary,
  Category,
  CategoryColor,
  CategoryKind,
  Holding,
  HoldingInput,
  IncomeStatement,
  IncomeTrendPoint,
  NetWorthPoint,
  PortfolioPoint,
  PortfolioSummary,
  RefreshRun,
  Transaction,
  TransactionInput,
} from './types';

export class ApiError extends Error {}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const data = await response.json();
      if (typeof data.detail === 'string') message = data.detail;
      else if (Array.isArray(data.detail)) message = data.detail.map((d: { msg: string }) => d.msg).join('; ');
    } catch {
      // keep the status text
    }
    throw new ApiError(message);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

const get = <T>(path: string) => request<T>('GET', path);
const qs = (params: Record<string, string | number | boolean>) =>
  '?' + new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString();

export const api = {
  categories: (includeArchived = false) => get<Category[]>(`/categories${qs({ include_archived: includeArchived })}`),
  createCategory: (body: { name: string; kind: CategoryKind; color?: CategoryColor }) => request<Category>('POST', '/categories', body),
  updateCategory: (id: number, body: { name?: string; color?: CategoryColor; is_archived?: boolean }) =>
    request<Category>('PATCH', `/categories/${id}`, body),
  deleteCategory: (id: number) => request<void>('DELETE', `/categories/${id}`),

  budgetItems: () => get<BudgetItem[]>('/budget/items'),
  budgetSummary: () => get<BudgetSummary>('/budget/summary'),
  createBudgetItem: (body: BudgetItemInput) => request<BudgetItem>('POST', '/budget/items', body),
  updateBudgetItem: (id: number, body: BudgetItemInput) => request<BudgetItem>('PUT', `/budget/items/${id}`, body),
  deleteBudgetItem: (id: number) => request<void>('DELETE', `/budget/items/${id}`),

  accounts: (includeArchived = false) => get<Account[]>(`/accounts${qs({ include_archived: includeArchived })}`),
  createAccount: (body: AccountInput) => request<Account>('POST', '/accounts', body),
  updateAccount: (id: number, body: Partial<AccountInput> & { is_archived?: boolean }) =>
    request<Account>('PATCH', `/accounts/${id}`, body),
  deleteAccount: (id: number) => request<void>('DELETE', `/accounts/${id}`),
  balanceSheet: (month: string) => get<BalanceSheet>(`/balance-sheet${qs({ month })}`),
  saveBalances: (month: string, balances: { account_id: number; balance: number | null }[]) =>
    request<BalanceSheet>('PUT', `/balance-sheet${qs({ month })}`, { balances }),
  copyPreviousBalances: (month: string) => request<BalanceSheet>('POST', `/balance-sheet/copy-previous${qs({ month })}`),
  netWorthTrend: (months = 24) => get<NetWorthPoint[]>(`/balance-sheet/trend${qs({ months })}`),

  transactions: (month: string) => get<Transaction[]>(`/transactions${qs({ month })}`),
  createTransaction: (body: TransactionInput) => request<Transaction>('POST', '/transactions', body),
  updateTransaction: (id: number, body: TransactionInput) => request<Transaction>('PUT', `/transactions/${id}`, body),
  deleteTransaction: (id: number) => request<void>('DELETE', `/transactions/${id}`),
  incomeStatement: (month: string) => get<IncomeStatement>(`/income-statement${qs({ month })}`),
  incomeTrend: (months = 12) => get<IncomeTrendPoint[]>(`/income-statement/trend${qs({ months })}`),

  holdings: () => get<Holding[]>('/holdings'),
  createHolding: (body: HoldingInput) => request<Holding>('POST', '/holdings', body),
  updateHolding: (id: number, body: HoldingInput) => request<Holding>('PUT', `/holdings/${id}`, body),
  deleteHolding: (id: number) => request<void>('DELETE', `/holdings/${id}`),
  portfolioSummary: () => get<PortfolioSummary>('/portfolio/summary'),
  portfolioHistory: (days: number) => get<PortfolioPoint[]>(`/portfolio/history${qs({ days })}`),
  refreshPrices: () => request<RefreshRun>('POST', '/prices/refresh'),

};
