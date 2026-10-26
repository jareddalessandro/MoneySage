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
  Company,
  CompanyEntry,
  CompanyEntryInput,
  CompanyInput,
  CompanyListItem,
  CompanyMember,
  CompanyMemberInput,
  CompanyProduct,
  CompanyProductInput,
  CompanySummary,
  CreditCard,
  CreditCardInput,
  Holding,
  HoldingInput,
  IncomeStatement,
  IncomeTrendPoint,
  NetWorthPoint,
  PortfolioPoint,
  PortfolioSummary,
  RefreshRun,
  RevenueShare,
  RevenueShareInput,
  RevenueShareMonth,
  StatementImport,
  StatementImportInput,
  StatementPreview,
  TotalsFrom,
  Transaction,
  TransactionInput,
} from './types';

export class ApiError extends Error {}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const form = body instanceof FormData;
  const response = await fetch(`/api${path}`, {
    method,
    headers: body === undefined || form ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : form ? body : JSON.stringify(body),
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
  setMonthNotes: (month: string, notes: string) => request<void>('PUT', '/income-statement/notes', { month, notes }),
  setTotalsFrom: (month: string, totals_from: TotalsFrom) =>
    request<void>('PUT', '/income-statement/totals-from', { month, totals_from }),
  previewStatement: (file: File) => {
    const body = new FormData();
    body.append('file', file);
    return request<StatementPreview>('POST', '/statements/preview', body);
  },
  importStatement: (body: StatementImportInput) => request<StatementImport>('POST', '/statements', body),
  statementImports: (month: string) => get<StatementImport[]>(`/statements${qs({ month })}`),
  undoStatementImport: (id: number) => request<void>('DELETE', `/statements/${id}`),

  holdings: () => get<Holding[]>('/holdings'),
  createHolding: (body: HoldingInput) => request<Holding>('POST', '/holdings', body),
  updateHolding: (id: number, body: HoldingInput) => request<Holding>('PUT', `/holdings/${id}`, body),
  deleteHolding: (id: number) => request<void>('DELETE', `/holdings/${id}`),
  portfolioSummary: () => get<PortfolioSummary>('/portfolio/summary'),
  portfolioHistory: (days: number) => get<PortfolioPoint[]>(`/portfolio/history${qs({ days })}`),
  refreshPrices: () => request<RefreshRun>('POST', '/prices/refresh'),

  creditCards: () => get<CreditCard[]>('/credit-cards'),
  createCreditCard: (body: CreditCardInput) => request<CreditCard>('POST', '/credit-cards', body),
  updateCreditCard: (id: number, body: CreditCardInput) => request<CreditCard>('PUT', `/credit-cards/${id}`, body),
  deleteCreditCard: (id: number) => request<void>('DELETE', `/credit-cards/${id}`),

  companies: (year?: number) => get<CompanyListItem[]>(`/companies${year ? qs({ year }) : ''}`),
  company: (id: number) => get<Company>(`/companies/${id}`),
  createCompany: (body: CompanyInput) => request<Company>('POST', '/companies', body),
  updateCompany: (id: number, body: CompanyInput) => request<Company>('PUT', `/companies/${id}`, body),
  deleteCompany: (id: number) => request<void>('DELETE', `/companies/${id}`),
  companySummary: (id: number, year: number) => get<CompanySummary>(`/companies/${id}/summary${qs({ year })}`),
  createCompanyMember: (companyId: number, body: CompanyMemberInput) =>
    request<CompanyMember>('POST', `/companies/${companyId}/members`, body),
  updateCompanyMember: (companyId: number, id: number, body: CompanyMemberInput) =>
    request<CompanyMember>('PUT', `/companies/${companyId}/members/${id}`, body),
  deleteCompanyMember: (companyId: number, id: number) => request<void>('DELETE', `/companies/${companyId}/members/${id}`),
  companyEntries: (companyId: number, year: number) =>
    get<CompanyEntry[]>(`/companies/${companyId}/entries${qs({ year })}`),
  createCompanyEntry: (companyId: number, body: CompanyEntryInput) =>
    request<CompanyEntry>('POST', `/companies/${companyId}/entries`, body),
  updateCompanyEntry: (companyId: number, id: number, body: CompanyEntryInput) =>
    request<CompanyEntry>('PUT', `/companies/${companyId}/entries/${id}`, body),
  deleteCompanyEntry: (companyId: number, id: number) => request<void>('DELETE', `/companies/${companyId}/entries/${id}`),
  createCompanyProduct: (companyId: number, body: CompanyProductInput) =>
    request<CompanyProduct>('POST', `/companies/${companyId}/products`, body),
  updateCompanyProduct: (companyId: number, id: number, body: CompanyProductInput) =>
    request<CompanyProduct>('PUT', `/companies/${companyId}/products/${id}`, body),
  deleteCompanyProduct: (companyId: number, id: number) => request<void>('DELETE', `/companies/${companyId}/products/${id}`),
  revenueShares: (companyId: number, year: number) =>
    get<RevenueShare[]>(`/companies/${companyId}/revenue-shares${qs({ year })}`),
  createRevenueShare: (companyId: number, body: RevenueShareInput) =>
    request<RevenueShare>('POST', `/companies/${companyId}/revenue-shares`, body),
  updateRevenueShare: (companyId: number, id: number, body: RevenueShareInput) =>
    request<RevenueShare>('PUT', `/companies/${companyId}/revenue-shares/${id}`, body),
  deleteRevenueShare: (companyId: number, id: number) =>
    request<void>('DELETE', `/companies/${companyId}/revenue-shares/${id}`),
  revenueShareMonths: (companyId: number, id: number, year: number) =>
    get<RevenueShareMonth[]>(`/companies/${companyId}/revenue-shares/${id}/months${qs({ year })}`),
  setRevenueShareMonths: (companyId: number, id: number, months: { month: string; revenue: number | null }[]) =>
    request<void>('PUT', `/companies/${companyId}/revenue-shares/${id}/months`, { months }),

};
