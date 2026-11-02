import type {
  AccessList,
  AccessRole,
  Account,
  AccountInput,
  AdminOverview,
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
  ImportResult,
  HoldingInput,
  InvestmentTransaction,
  Me,
  MyInvite,
  Site,
  TradeInput,
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

export class ApiError extends Error {
  status: number;

  constructor(message: string, status = 0) {
    super(message);
    this.status = status;
  }
}

/** Fired when a request finds the session gone (signed out elsewhere, or expired). */
export const SIGNED_OUT_EVENT = 'tallyvio:signed-out';

/** The backend refuses changes without this header, so other websites can't make them (see main.py). */
const APP_HEADER = { 'X-Requested-With': 'tallyvio' };

// Which household requests work in (X-Household-Id). Unset means the backend's default: your own.
const HOUSEHOLD_KEY = 'tallyvio.household';
let householdId: number | null = (() => {
  try {
    const saved = Number(localStorage.getItem(HOUSEHOLD_KEY));
    return Number.isInteger(saved) && saved > 0 ? saved : null;
  } catch {
    return null;
  }
})();

export function currentHouseholdId(): number | null {
  return householdId;
}

/** Switch the household every later request works in (null = your own). The caller refetches. */
export function setHouseholdId(id: number | null) {
  householdId = id;
  try {
    if (id === null) localStorage.removeItem(HOUSEHOLD_KEY);
    else localStorage.setItem(HOUSEHOLD_KEY, String(id));
  } catch {
    // remembered for this visit only
  }
}

function baseHeaders(): Record<string, string> {
  return householdId === null ? { ...APP_HEADER } : { ...APP_HEADER, 'X-Household-Id': String(householdId) };
}

async function failure(response: Response): Promise<ApiError> {
  let message = `${response.status} ${response.statusText}`;
  try {
    const data = await response.json();
    if (typeof data.detail === 'string') message = data.detail;
    else if (Array.isArray(data.detail)) message = data.detail.map((d: { msg: string }) => d.msg).join('; ');
  } catch {
    // keep the status text
  }
  return new ApiError(message, response.status);
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const form = body instanceof FormData;
  const response = await fetch(`/api${path}`, {
    method,
    headers: body === undefined || form ? baseHeaders() : { ...baseHeaders(), 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : form ? body : JSON.stringify(body),
  });
  if (response.status === 401 && path !== '/me') window.dispatchEvent(new Event(SIGNED_OUT_EVENT));
  if (!response.ok) throw await failure(response);
  return response.status === 204 ? (undefined as T) : response.json();
}

/** Fetch a file the API serves as an attachment and save it under the name it gives. */
async function download(path: string): Promise<void> {
  const response = await fetch(`/api${path}`, { headers: baseHeaders() });
  if (!response.ok) throw await failure(response);
  const name = /filename="([^"]+)"/.exec(response.headers.get('Content-Disposition') ?? '')?.[1] ?? 'tallyvio.json';
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

const get = <T>(path: string) => request<T>('GET', path);

export type AccessTarget = 'household' | number;
const accessPath = (target: AccessTarget) => (target === 'household' ? '/household/access' : `/companies/${target}/access`);
const qs = (params: Record<string, string | number | boolean>) =>
  '?' + new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString();

export const api = {
  me: () => get<Me>('/me'),
  site: () => get<Site>('/site'),
  adminOverview: () => get<AdminOverview>('/admin/overview'),
  signOut: () => request<void>('POST', '/auth/logout'),
  onboarding: (body: { household_name?: string; timezone?: string; accept_terms: true }) =>
    request<void>('POST', '/onboarding', body),
  updateHousehold: (body: { name?: string; timezone?: string }) =>
    request<{ id: number; name: string; timezone: string }>('PATCH', '/household', body),

  /** Sharing. `target` is 'household' (the current one) or a company id. */
  access: (target: AccessTarget) => get<AccessList>(`${accessPath(target)}`),
  invite: (target: AccessTarget, body: { email: string; role: Exclude<AccessRole, 'owner'> }) =>
    request<void>('POST', `${accessPath(target)}/invites`, body),
  revokeInvite: (target: AccessTarget, inviteId: number) => request<void>('DELETE', `${accessPath(target)}/invites/${inviteId}`),
  setRole: (target: AccessTarget, userId: number, role: Exclude<AccessRole, 'owner'>) =>
    request<AccessList>('PATCH', `${accessPath(target)}/${userId}`, { role }),
  removeAccess: (target: AccessTarget, userId: number) => request<void>('DELETE', `${accessPath(target)}/${userId}`),
  leaveHousehold: (id: number) => request<void>('DELETE', `/me/households/${id}`),
  leaveCompany: (id: number) => request<void>('DELETE', `/me/companies/${id}`),
  myInvites: () => get<MyInvite[]>('/invites'),
  acceptInvite: (id: number) => request<{ kind: 'household' | 'company'; id: number }>('POST', `/invites/${id}/accept`),
  declineInvite: (id: number) => request<void>('POST', `/invites/${id}/decline`),

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
  /** Returns the updated holding, or null when a sale removed all of it. */
  tradeHolding: (id: number, body: TradeInput) => request<Holding | null>('POST', `/holdings/${id}/trade`, body),
  investmentTransactions: () => get<InvestmentTransaction[]>('/investment-transactions'),
  deleteInvestmentTransaction: (id: number) => request<void>('DELETE', `/investment-transactions/${id}`),
  portfolioSummary: () => get<PortfolioSummary>('/portfolio/summary'),
  portfolioHistory: (days: number) => get<PortfolioPoint[]>(`/portfolio/history${qs({ days })}`),
  refreshPrices: () => request<RefreshRun>('POST', '/prices/refresh'),

  creditCards: () => get<CreditCard[]>('/credit-cards'),
  createCreditCard: (body: CreditCardInput) => request<CreditCard>('POST', '/credit-cards', body),
  updateCreditCard: (id: number, body: CreditCardInput) => request<CreditCard>('PUT', `/credit-cards/${id}`, body),
  deleteCreditCard: (id: number) => request<void>('DELETE', `/credit-cards/${id}`),

  /** This household and every company you own, as one file. */
  downloadExport: () => download('/export'),
  downloadCompanyExport: (companyId: number) => download(`/companies/${companyId}/export`),
  importExport: (file: File) => {
    const body = new FormData();
    body.append('file', file);
    return request<ImportResult>('POST', '/import', body);
  },

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
