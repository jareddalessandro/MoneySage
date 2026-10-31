import { BarChart } from '@mantine/charts';
import {
  Anchor,
  Badge,
  Button,
  Checkbox,
  Grid,
  Group,
  Modal,
  NumberInput,
  Pagination,
  Paper,
  Progress,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Table,
  Text,
  Textarea,
  TextInput,
  Tooltip,
} from '@mantine/core';
import { DateInput } from '@mantine/dates';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import {
  IconAlertTriangle,
  IconFileInvoice,
  IconFileUpload,
  IconInfoCircle,
  IconPencil,
  IconPlus,
  IconSearch,
  IconTrash,
} from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { CategoryBadge, CategoryDot } from '../components/CategoryColor';
import { api } from '../api';
import CategorySelect from '../components/CategorySelect';
import StatementImportModal from '../components/StatementImport';
import {
  confirmDelete,
  Delta,
  EmptyState,
  MonthSwitcher,
  PageHeader,
  RowActions,
  SectionCard,
  SortableTh,
  StatCard,
  useAppMutation,
  type SortDir,
} from '../components/common';
import { money, monthLabel, monthShort, moneyCompact, SERIES_ORDER, signedMoney, thisMonth } from '../format';
import type {
  CategoryKind,
  IncomeStatement,
  StatementCategory,
  StatementImport,
  TotalsFrom,
  Transaction,
  TransactionInput,
} from '../types';

type Filter = 'all' | 'income' | 'expense';
type Editing = { txn: Transaction | null; unexpected?: boolean; kind?: CategoryKind } | null;

type TxnSortKey = 'date' | 'category' | 'amount';
type TxnSort = { key: TxnSortKey; dir: SortDir };
const TXN_SORT_KEY = 'moneysage.transactions-sort';
const DEFAULT_TXN_SORT: TxnSort = { key: 'date', dir: 'desc' };

function loadTxnSort(): TxnSort {
  try {
    const saved = JSON.parse(localStorage.getItem(TXN_SORT_KEY) ?? 'null');
    if (['date', 'category', 'amount'].includes(saved?.key) && ['asc', 'desc'].includes(saved?.dir)) return saved;
  } catch {
    /* ignore */
  }
  return DEFAULT_TXN_SORT;
}

function saveTxnSort(sort: TxnSort) {
  try {
    localStorage.setItem(TXN_SORT_KEY, JSON.stringify(sort));
  } catch {
    /* ignore */
  }
}

/** Ties keep the API's order (newest first), since the sort is stable. Amount compares size, ignoring
    whether it's income or an expense, so the biggest items surface either way. */
function sortTransactions(rows: Transaction[], { key, dir }: TxnSort): Transaction[] {
  const sign = dir === 'asc' ? 1 : -1;
  const compare: Record<TxnSortKey, (a: Transaction, b: Transaction) => number> = {
    date: (a, b) => a.date.localeCompare(b.date) || a.id - b.id,
    category: (a, b) => a.category.name.localeCompare(b.category.name),
    amount: (a, b) => a.amount - b.amount,
  };
  return [...rows].sort((a, b) => sign * compare[key](a, b));
}

export default function IncomeStatementPage() {
  const [month, setMonth] = useState(thisMonth);
  const [filter, setFilter] = useState<Filter>('all');
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<Editing>(null);
  const [importing, setImporting] = useState(false);
  const [sort, setSort] = useState<TxnSort>(loadTxnSort);
  const [byCategory, setByCategory] = useState(loadByCategory);

  const { data: txns = [] } = useQuery({ queryKey: ['transactions', month], queryFn: () => api.transactions(month) });
  // While a month loads, `statement` still holds the previous month's (placeholderData); isPlaceholderData says so.
  const { data: statement, isPlaceholderData: statementLoading } = useQuery({
    queryKey: ['income-statement', month],
    queryFn: () => api.incomeStatement(month),
  });
  const { data: trend = [] } = useQuery({ queryKey: ['income-trend'], queryFn: () => api.incomeTrend(12) });
  const { data: imports = [] } = useQuery({ queryKey: ['statement-imports', month], queryFn: () => api.statementImports(month) });
  const { data: accounts = [] } = useQuery({ queryKey: ['accounts', 'all'], queryFn: () => api.accounts(true) });
  const { data: categories = [] } = useQuery({ queryKey: ['categories'], queryFn: () => api.categories() });
  const remove = useAppMutation((id: number) => api.deleteTransaction(id), 'Transaction deleted');
  // Unexpected items start in Miscellaneous / Other Income; most are one-offs that fit no budget category.
  const unexpectedDefaults = useMemo(
    () => ({
      expense: categories.find((c) => c.kind === 'expense' && c.name === 'Miscellaneous')?.id,
      income: categories.find((c) => c.kind === 'income' && c.name === 'Other Income')?.id,
    }),
    [categories],
  );
  const cardCategoryId = categories.find((c) => c.is_card_payments)?.id;

  const accountNames = useMemo(() => new Map(accounts.map((a) => [a.id, a.name])), [accounts]);
  const totalsFrom = statement?.totals_from ?? 'manual';
  // In a statement month, manual entries explain the totals instead of adding to them (and vice versa).
  const counted = (t: Transaction) => (t.source === 'statement') === (totalsFrom === 'statement');

  // Manual unexpected items are listed in their own card, so the transactions table leaves them out.
  // (An imported statement line flagged unexpected is a real bank transaction and stays.)
  const listed = useMemo(() => txns.filter((t) => !(t.is_unexpected && t.source !== 'statement')), [txns]);
  // Budget vs. actual stays empty until the month has real records (a statement or regular entries);
  // unexpected items alone only explain a month, so against the budget they'd read as a huge shortfall.
  const hasRecords = listed.length > 0;

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    const shown = listed.filter((t) => {
      if (filter !== 'all' && t.category.kind !== filter) return false;
      return !term || t.description.toLowerCase().includes(term) || t.category.name.toLowerCase().includes(term);
    });
    return sortTransactions(shown, sort);
  }, [listed, filter, search, sort]);

  const sortBy = (key: TxnSortKey) => {
    // Amount opens largest first; date opens newest first; category opens A–Z.
    const dir: SortDir = sort.key === key ? (sort.dir === 'asc' ? 'desc' : 'asc') : key === 'category' ? 'asc' : 'desc';
    const next = { key, dir };
    setSort(next);
    saveTxnSort(next);
  };
  const header = (key: TxnSortKey, label: string, props: { align?: 'right'; w?: number; className?: string } = {}) => (
    <SortableTh label={label} active={sort.key === key} dir={sort.dir} onSort={() => sortBy(key)} {...props} />
  );

  // Newest entry first (by when it was added, not its date: the card doesn't show dates).
  const unexpected = useMemo(() => txns.filter((t) => t.is_unexpected).sort((a, b) => b.id - a.id), [txns]);
  // The chart and its totals cover this calendar year only. The trend spans the last 12 months, so it
  // always holds January through now, and each month follows its own totals source (statement or manual).
  const year = thisMonth().slice(0, 4);
  const yearTrend = trend.filter((p) => p.month.startsWith(year));
  const trendData = yearTrend.map((p) => ({ month: monthShort(p.month), Income: p.income, Expenses: p.expenses, Net: p.net }));
  const hasTrend = yearTrend.some((p) => p.income || p.expenses);
  const ytd = yearTrend.reduce(
    (t, p) => ({ income: t.income + p.income, expenses: t.expenses + p.expenses }),
    { income: 0, expenses: 0 },
  );

  const rowActions = (t: Transaction) => (
    <RowActions
      label={`Actions for ${t.description}`}
      actions={[
        { label: 'Edit', icon: <IconPencil size={16} />, onClick: () => setEditing({ txn: t }) },
        { label: 'Delete', icon: <IconTrash size={16} />, color: 'red', onClick: () => confirmDelete(`"${t.description}"`, () => remove.mutate(t.id)) },
      ]}
    />
  );

  const source = (t: Transaction) =>
    [
      t.source === 'statement' ? (t.account_id != null && accountNames.get(t.account_id)) || 'Imported' : 'Manual',
      counted(t) ? null : 'Not in totals',
      t.notes,
    ]
      .filter(Boolean)
      .join(' · ');

  return (
    <>
      <PageHeader
        title="Income Statement"
        description={
          imports.length > 0 || statement?.has_statement ? (
            <StatementHeader month={month} imports={imports} statement={statement} />
          ) : (
            'What actually came in and went out each month.'
          )
        }
        actions={
          <>
            <MonthSwitcher value={month} onChange={setMonth} />
            <Button variant="default" leftSection={<IconPlus size={16} />} onClick={() => setEditing({ txn: null })}>
              Add transaction
            </Button>
            <Button leftSection={<IconFileUpload size={16} />} onClick={() => setImporting(true)}>
              Import statement
            </Button>
          </>
        }
      />


      {/* Summary cards with the month's notes beside them (below them on smaller screens). */}
      <Grid gutter={{ base: 'sm', sm: 'md' }} mb="xl">
        <Grid.Col span={{ base: 12, lg: 8 }}>
          <SimpleGrid cols={{ base: 2, sm: 4 }} spacing={{ base: 'sm', sm: 'md' }} h="100%">
            <StatCard
              compact
              label="Income"
              value={money(statement?.total_income)}
              footer={statement && budgetFooter(statement.total_income, statement.budgeted_income, 'income')}
            />
            <StatCard
              compact
              label="Expenses"
              value={money(statement?.total_expenses)}
              footer={statement && budgetFooter(statement.total_expenses, statement.budgeted_expenses, 'expense')}
            />
            <StatCard
              compact
              label="Net"
              value={<span className={statement && statement.net < 0 ? 'delta-down' : undefined}>{money(statement?.net)}</span>}
              footer={statement && statement.net >= 0 ? 'Saved this month' : 'Spent more than earned'}
            />
            <StatCard
              compact
              label="Unexpected"
              value={money(statement?.unexpected_expenses)}
              footer={
                statement && statement.unexpected_income > 0
                  ? `in expenses · ${money(statement.unexpected_income)} in income`
                  : 'in unplanned expenses'
              }
            />
          </SimpleGrid>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 4 }}>
          {/* The editor takes its text when it mounts, so wait for this month's notes, not the last month's. */}
          {statement && !statementLoading ? (
            <MonthNotes key={month} month={month} saved={statement.notes} />
          ) : (
            <MonthNotesCard month={month} />
          )}
        </Grid.Col>
      </Grid>

      <Stack gap="lg">
        <SectionCard
          title="Unexpected items"
        >
          <QuickUnexpected key={month} month={month} defaults={unexpectedDefaults} />
          <SimpleGrid cols={{ base: 1, md: 2 }} spacing="xl" verticalSpacing="lg">
            {(['expense', 'income'] as const).map((kind) => (
              <UnexpectedList
                key={`${kind}-${month}`}
                kind={kind}
                items={unexpected.filter((t) => t.category.kind === kind)}
                rowActions={rowActions}
              />
            ))}
          </SimpleGrid>
        </SectionCard>
        <SectionCard
          title="Budget vs. actual"
          actions={
            hasRecords && (
            <Switch
              size="sm"
              label="By category"
              checked={byCategory}
              onChange={(e) => {
                setByCategory(e.currentTarget.checked);
                saveByCategory(e.currentTarget.checked);
              }}
            />
            )
          }
        >
          {!hasRecords ? (
            <EmptyState
              message={`Nothing to compare yet. Import a statement or add transactions for ${monthLabel(month)} to see how it stacks up against the budget.`}
            />
          ) : statement && statement.categories.length > 0 ? (
            <>
              <BudgetSummary statement={statement} />
              {byCategory && (
                <>
                  <CardBudgetTip statement={statement} cardCategoryId={cardCategoryId} />
                  <BudgetVsActual statement={statement} />
                </>
              )}
            </>
          ) : (
            <EmptyState message="Add budget items or transactions to compare plan vs. reality." />
          )}
        </SectionCard>

        <SectionCard
          title={`Transactions · ${monthLabel(month)}`}
          actions={
            <>
              <TextInput
                size="xs"
                placeholder="Search"
                leftSection={<IconSearch size={14} />}
                value={search}
                onChange={(e) => setSearch(e.currentTarget.value)}
                w={{ base: '100%', xs: 180 }}
              />
              <SegmentedControl
                size="xs"
                value={filter}
                onChange={(v) => setFilter(v as Filter)}
                data={[
                  { value: 'all', label: 'All' },
                  { value: 'income', label: 'Income' },
                  { value: 'expense', label: 'Expenses' },
                ]}
              />
              {/* Phones hide the category column header, so sorting gets its own control there. */}
              <Select
                className="show-xs"
                w="100%"
                aria-label="Sort transactions"
                allowDeselect={false}
                value={`${sort.key}-${sort.dir}`}
                onChange={(v) => {
                  if (!v) return;
                  const [key, dir] = v.split('-') as [TxnSortKey, SortDir];
                  setSort({ key, dir });
                  saveTxnSort({ key, dir });
                }}
                data={[
                  { value: 'date-desc', label: 'Newest first' },
                  { value: 'date-asc', label: 'Oldest first' },
                  { value: 'category-asc', label: 'Category A–Z' },
                  { value: 'category-desc', label: 'Category Z–A' },
                  { value: 'amount-desc', label: 'Largest amount first' },
                  { value: 'amount-asc', label: 'Smallest amount first' },
                ]}
              />
            </>
          }
        >
          {listed.length === 0 ? (
            <EmptyState
              message={`No transactions for ${monthLabel(month)} yet.`}
              action={
                <Group gap="xs" justify="center">
                  <Button size="xs" variant="light" leftSection={<IconFileUpload size={14} />} onClick={() => setImporting(true)}>
                    Import statement
                  </Button>
                  <Button size="xs" variant="default" leftSection={<IconPlus size={14} />} onClick={() => setEditing({ txn: null })}>
                    Add transaction
                  </Button>
                </Group>
              }
            />
          ) : (
            <Table.ScrollContainer minWidth={640} maxHeight={480} className="phone-fit">
              <Table highlightOnHover stickyHeader verticalSpacing="xs">
                <Table.Thead>
                  <Table.Tr>
                    {header('date', 'Date', { w: 70 })}
                    <Table.Th>Description</Table.Th>
                    {header('category', 'Category', { className: 'hide-xs' })}
                    {header('amount', 'Amount', { align: 'right' })}
                    <Table.Th w={70} />
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {visible.map((t) => (
                    <Table.Tr key={t.id} className={counted(t) ? undefined : 'row-muted'}>
                      <Table.Td className="num">{dayjs(t.date).format('MMM D')}</Table.Td>
                      <Table.Td>
                        <Group gap={6} wrap="wrap" style={{ rowGap: 2 }}>
                          <Text size="sm">{t.description}</Text>
                          {t.is_unexpected && (
                            <Badge size="xs" color="orange" variant="light" leftSection={<IconAlertTriangle size={10} />}>
                              Unexpected
                            </Badge>
                          )}
                        </Group>
                        <Text size="xs" c="dimmed" lineClamp={1}>
                          {source(t)}
                        </Text>
                        {/* On phones the category column is hidden, so it sits under the description. */}
                        <Group className="show-xs" mt={4}>
                          <CategoryBadge category={t.category} />
                        </Group>
                      </Table.Td>
                      <Table.Td className="hide-xs">
                        <CategoryBadge category={t.category} />
                      </Table.Td>
                      <Table.Td ta="right" className="num" fw={500} style={{ whiteSpace: 'nowrap' }}>
                        {t.category.kind === 'income' ? '+' : '−'}
                        {money(t.amount)}
                      </Table.Td>
                      <Table.Td className="keep-opaque">{rowActions(t)}</Table.Td>
                    </Table.Tr>
                  ))}
                  {visible.length === 0 && (
                    <Table.Tr>
                      <Table.Td colSpan={5}>
                        <Text size="sm" c="dimmed" ta="center" py="md">
                          No transactions match.
                        </Text>
                      </Table.Td>
                    </Table.Tr>
                  )}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          )}
        </SectionCard>

        <SectionCard title={`Income vs. expenses · ${year}`}>
          {hasTrend && (
            <SimpleGrid cols={3} spacing="sm" mb="md">
              {[
                { label: `Income · ${year} YTD`, value: ytd.income },
                { label: `Expenses · ${year} YTD`, value: ytd.expenses },
                { label: `Net · ${year} YTD`, value: ytd.income - ytd.expenses },
              ].map((f) => (
                <div key={f.label}>
                  <Text className="label-sm">{f.label}</Text>
                  <Text
                    className={`headline num${f.label.startsWith('Net') && f.value < 0 ? ' delta-down' : ''}`}
                    fw={700}
                    fz={{ base: 'md', sm: 'lg' }}
                    mt={4}
                  >
                    {f.label.startsWith('Net') ? signedMoney(Math.round(f.value * 100) / 100) : money(f.value)}
                  </Text>
                </div>
              ))}
            </SimpleGrid>
          )}
          {hasTrend ? (
            <BarChart
              h={280}
              data={trendData}
              dataKey="month"
              series={[
                { name: 'Income', color: 'var(--chart-income)' },
                { name: 'Expenses', color: 'var(--chart-expenses)' },
                { name: 'Net', color: 'var(--chart-net)' },
              ]}
              withLegend
              legendProps={{ verticalAlign: 'top', height: 36, itemSorter: SERIES_ORDER }}
              valueFormatter={(v) => money(v)}
              yAxisProps={{ tickFormatter: (v: number) => moneyCompact(v), width: 56 }}
              gridAxis="x"
              strokeDasharray="0"
              barProps={{ radius: [4, 4, 0, 0] }}
              barChartProps={{ barGap: 2 }}
              maxBarWidth={24}
            />
          ) : (
            <EmptyState message={`Your ${year} months will appear here as you add transactions.`} />
          )}
        </SectionCard>
      </Stack>

      <StatementImportModal opened={importing} onClose={() => setImporting(false)} onImported={setMonth} />

      <Modal
        opened={editing !== null}
        onClose={() => setEditing(null)}
        title={editing?.txn ? 'Edit transaction' : editing?.unexpected ? `Add unexpected ${editing.kind}` : 'Add transaction'}
      >
        {editing && (
          <TransactionForm
            key={editing.txn?.id ?? 'new'}
            editing={editing}
            month={month}
            onDone={() => setEditing(null)}
          />
        )}
      </Modal>
    </>
  );
}

/** The page header's subtitle in a month with a statement: the import (with undo) and the totals switch. */
function StatementHeader({
  month,
  imports,
  statement,
}: {
  month: string;
  imports: StatementImport[];
  statement: IncomeStatement | undefined;
}) {
  const setSource = useAppMutation((v: TotalsFrom) => api.setTotalsFrom(month, v));
  const undo = useAppMutation((id: number) => api.undoStatementImport(id), 'Import undone');

  return (
    <Group gap="xs" wrap="wrap" style={{ rowGap: 6 }}>
      {imports.map((i) => (
        <Group key={i.id} gap={6} wrap="wrap" style={{ rowGap: 0 }}>
          <IconFileInvoice size={16} stroke={1.6} aria-hidden />
          <Text size="sm" c="dimmed">
            {i.bank} statement · {dayjs(i.period_start).format('MMM D')} – {dayjs(i.period_end).format('MMM D')} ·{' '}
            {i.transaction_count} transactions
          </Text>
          <Anchor
            component="button"
            type="button"
            size="sm"
            c="red.4"
            className="hit-44"
            onClick={() =>
              confirmDelete(
                `the ${i.bank} statement import`,
                () => undo.mutate(i.id),
                `This removes the ${i.transaction_count} transactions it added, including any edits made to them. Balance Sheet balances stay as they are.`,
              )
            }
          >
            Undo import
          </Anchor>
        </Group>
      ))}
      {statement?.has_statement && (
        <Group gap={6} wrap="nowrap">
          <Text size="sm" c="dimmed">
            Totals from
          </Text>
          <SegmentedControl
            size="xs"
            value={statement.totals_from}
            onChange={(v) => setSource.mutate(v as TotalsFrom)}
            data={[
              { value: 'statement', label: 'Statement' },
              { value: 'manual', label: 'Manual entries' },
            ]}
          />
          <Tooltip
            multiline
            w={260}
            label={
              statement.totals_from === 'statement'
                ? "The statement's lines are the totals. Manual entries explain differences from the budget but don't add to them."
                : 'Your manual entries are the totals, and the imported lines are ignored this month.'
            }
          >
            <IconInfoCircle size={16} color="var(--mantine-color-dimmed)" aria-label="About totals" />
          </Tooltip>
        </Group>
      )}
    </Group>
  );
}

const BY_CATEGORY_KEY = 'moneysage.budget-by-category';

function loadByCategory(): boolean {
  try {
    return localStorage.getItem(BY_CATEGORY_KEY) === 'true';
  } catch {
    return false;
  }
}

function saveByCategory(on: boolean) {
  try {
    localStorage.setItem(BY_CATEGORY_KEY, String(on));
  } catch {
    /* ignore */
  }
}

const cents = (n: number) => Math.round(n * 100) / 100;

/**
 * Income and expenses against the budget, next to what the month's unexpected items add up to.
 * "Everything else" is the part of the difference the unexpected items don't account for.
 */
function BudgetSummary({ statement: s }: { statement: IncomeStatement }) {
  const inProgress = s.totals_from !== 'statement' && s.month >= thisMonth();
  const rows = [
    {
      label: 'Income',
      budget: s.budgeted_income,
      actual: s.total_income,
      unexpected: s.unexpected_income,
      goodWhen: 'up' as const,
    },
    {
      label: 'Expenses',
      budget: s.budgeted_expenses,
      actual: s.total_expenses,
      unexpected: s.unexpected_expenses,
      goodWhen: 'down' as const,
    },
  ];

  return (
    <>
      <Table.ScrollContainer minWidth={560} className="phone-fit">
        <Table verticalSpacing={6}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th />
              <Table.Th ta="right" className="hide-xs">
                Budget
              </Table.Th>
              <Table.Th ta="right" className="hide-xs">
                Actual
              </Table.Th>
              <Table.Th ta="right">vs. budget</Table.Th>
              <Table.Th ta="right">Unexpected items</Table.Th>
              <Table.Th ta="right">Everything else</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((r) => {
              const diff = cents(r.actual - r.budget);
              return (
                <Table.Tr key={r.label}>
                  <Table.Td fw={500}>{r.label}</Table.Td>
                  <Table.Td ta="right" className="num hide-xs">
                    {money(r.budget)}
                  </Table.Td>
                  <Table.Td ta="right" className="num hide-xs">
                    {money(r.actual)}
                  </Table.Td>
                  <Table.Td ta="right">
                    <Group justify="flex-end">
                      <Delta value={diff} goodWhen={r.goodWhen} />
                    </Group>
                  </Table.Td>
                  <Table.Td ta="right" className="num">
                    {r.unexpected ? signedMoney(cents(r.unexpected)) : '—'}
                  </Table.Td>
                  <Table.Td ta="right">
                    <Group justify="flex-end">
                      <Delta value={cents(diff - r.unexpected)} goodWhen={r.goodWhen} />
                    </Group>
                  </Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      <Text size="xs" c="dimmed" mt="xs" mb="lg">
        {inProgress
          ? "This month isn't over yet, so income and expenses still read low against the budget. "
          : ''}
        Everything else is the difference from budget that your unexpected items don&apos;t account for.
      </Text>
    </>
  );
}

/** In a statement month, card payments with no paid-by-card budget items all read as overspending. */
function CardBudgetTip({ statement: s, cardCategoryId }: { statement: IncomeStatement; cardCategoryId?: number }) {
  const card = s.categories.find((c) => c.category_id === cardCategoryId);
  if (s.totals_from !== 'statement' || card == null || card.actual <= 0 || card.card_items.length > 0) return null;
  return (
    <Text size="xs" c="dimmed" mb="sm">
      Card payments have no budget yet, so they show as unbudgeted while categories like Groceries look underspent.
      Mark the budget items you pay by card on the{' '}
      <Anchor component={Link} to="/budget" size="xs" className="hit-44">
        Budget page
      </Anchor>{' '}
      (&ldquo;Paid by credit card&rdquo;) to compare them with card payments as one line.
    </Text>
  );
}

function CardItems({ names }: { names: string[] }) {
  const more = names.length - 3;
  return (
    <Tooltip label={names.join(', ')} multiline w={260} disabled={more <= 0}>
      <Text size="xs" c="dimmed">
        Covers {names.slice(0, 3).join(', ')}
        {more > 0 ? `, +${more} more` : ''}
      </Text>
    </Tooltip>
  );
}

/**
 * Inline entry for unexpected items, which get logged often: type a description, Tab to the amount,
 * press Enter. Type and category stay as they were for the next one, and focus returns to the
 * description. Expenses default to Miscellaneous and income to Other Income.
 */
function QuickUnexpected({
  month,
  defaults,
}: {
  month: string;
  defaults: Record<CategoryKind, number | undefined>;
}) {
  const [kind, setKind] = useState<CategoryKind>('expense');
  const [description, setDescription] = useState('');
  // Kept as the input gives it: a string while typing (e.g. "12."), a number once it parses.
  const [amount, setAmount] = useState<number | string>('');
  const [categoryId, setCategoryId] = useState<number | null>(defaults.expense ?? null);
  // The card doesn't ask for a date: today in the current month, else the month's 1st.
  const date = month === thisMonth() ? dayjs().format('YYYY-MM-DD') : `${month}-01`;
  const amountRef = useRef<HTMLInputElement>(null);
  const add = useAppMutation((body: TransactionInput) => api.createTransaction(body));

  // The categories load after the first render; fill in the default once they arrive.
  useEffect(() => {
    if (categoryId == null && defaults[kind] != null) setCategoryId(defaults[kind]!);
  }, [defaults, kind, categoryId]);

  const value = typeof amount === 'number' ? amount : Number(amount);
  const valid = description.trim() !== '' && amount !== '' && value > 0 && categoryId != null;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    add.mutate(
      {
        date,
        description: description.trim(),
        amount: value,
        category_id: categoryId!,
        is_unexpected: true,
        notes: null,
        account_id: null,
      },
      {
        onSuccess: () => {
          setDescription('');
          setAmount('');
          amountRef.current?.focus();
        },
      },
    );
  };

  return (
    <form onSubmit={submit}>
      {/* One line on wide screens; wraps to two on narrow ones. */}
      <Group gap="xs" wrap="wrap" mb="lg" align="flex-start">
          <NumberInput
            ref={amountRef}
            size="sm"
            placeholder="Amount"
            aria-label="Amount"
            prefix="$"
            decimalScale={2}
            thousandSeparator=","
            min={0}
            hideControls
            value={amount}
            onChange={setAmount}
            w={140}
          />
          <TextInput
            size="sm"
            placeholder={kind === 'expense' ? 'What was it? e.g. Car repair' : 'What was it? e.g. Birthday money'}
            aria-label="Description"
            value={description}
            onChange={(e) => setDescription(e.currentTarget.value)}
            style={{ flex: '2 1 220px' }}
          />
          <SegmentedControl
            size="sm"
            value={kind}
            onChange={(v) => {
              const next = v as CategoryKind;
              setKind(next);
              setCategoryId(defaults[next] ?? null);
            }}
            data={[
              { value: 'expense', label: 'Expense' },
              { value: 'income', label: 'Income' },
            ]}
          />
          <CategorySelect
            label={null}
            aria-label="Category"
            size="sm"
            kind={kind}
            value={categoryId}
            onChange={setCategoryId}
            style={{ flex: '1 1 160px' }}
          />
          <Button type="submit" size="sm" leftSection={<IconPlus size={16} />} disabled={!valid} loading={add.isPending}>
            Add
          </Button>
      </Group>
    </form>
  );
}

/** One side of the Unexpected items card (expenses or income): the noted items and their total. How they
    compare with the budget is in the Budget vs. actual card. */
const UNEXPECTED_PAGE_SIZE = 8;

function UnexpectedList({
  kind,
  items,
  rowActions,
}: {
  kind: CategoryKind;
  items: Transaction[];
  rowActions: (t: Transaction) => ReactNode;
}) {
  const expenses = kind === 'expense';
  const noted = cents(items.reduce((t, i) => t + i.amount, 0));
  const [page, setPage] = useState(1);
  const pages = Math.max(1, Math.ceil(items.length / UNEXPECTED_PAGE_SIZE));
  const current = Math.min(page, pages); // e.g. after deleting the last item on the last page
  const first = (current - 1) * UNEXPECTED_PAGE_SIZE;
  const shown = items.slice(first, first + UNEXPECTED_PAGE_SIZE);

  // A new item lands at the top of the list, so jump back to the first page to show it.
  const count = useRef(items.length);
  useEffect(() => {
    if (items.length > count.current) setPage(1);
    count.current = items.length;
  }, [items.length]);

  return (
    <div>
      <Text className="label-sm" mb={4}>
        {expenses ? 'Unexpected expenses' : 'Unexpected income'}
      </Text>
      {items.length === 0 ? (
        <Text size="sm" c="dimmed" py={6}>
          None noted yet.
        </Text>
      ) : (
        <Table verticalSpacing={6}>
          <Table.Tbody>
            {shown.map((t) => (
              <Table.Tr key={t.id}>
                <Table.Td>
                  <Text size="sm">{t.description}</Text>
                  <Text size="xs" c="dimmed">
                    {t.category.name}
                  </Text>
                </Table.Td>
                <Table.Td ta="right" className="num" fw={500} style={{ whiteSpace: 'nowrap' }}>
                  {money(t.amount)}
                </Table.Td>
                <Table.Td w={70}>{rowActions(t)}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
          <Table.Tfoot>
            <Table.Tr>
              <Table.Th>Total</Table.Th>
              <Table.Th ta="right" className="num">
                {money(noted)}
              </Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Tfoot>
        </Table>
      )}
      {pages > 1 && (
        <Group justify="space-between" mt="xs" gap="xs">
          <Text size="xs" c="dimmed" className="num">
            {first + 1}–{first + shown.length} of {items.length}
          </Text>
          <Pagination size="sm" total={pages} value={current} onChange={setPage} />
        </Group>
      )}
    </div>
  );
}

const NOTES_SAVE_DELAY = 800;

/**
 * Free-form notes about the month. Saves on its own a moment after typing stops, on blur, and when
 * leaving the month, so there's no Save button to forget.
 */
function MonthNotes({ month, saved }: { month: string; saved: string | null }) {
  const queryClient = useQueryClient();
  const [text, setText] = useState(saved ?? '');
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved'>('idle');
  // What the server has; null after a failed save, so the next change or blur retries.
  const lastSaved = useRef<string | null>(saved ?? '');
  const latest = useRef(text);
  latest.current = text;

  const cache = (notes: string) =>
    queryClient.setQueryData<IncomeStatement>(['income-statement', month], (old) =>
      old ? { ...old, notes: notes.trim() || null } : old,
    );
  const save = useMutation({
    mutationFn: (notes: string) => api.setMonthNotes(month, notes),
    onSuccess: (_, notes) => {
      cache(notes);
      setStatus('saved');
    },
    onError: (error: Error) => {
      lastSaved.current = null;
      setStatus('idle');
      notifications.show({ title: "Couldn't save notes", message: error.message, color: 'red' });
    },
  });
  const flush = () => {
    if (latest.current === lastSaved.current) return;
    lastSaved.current = latest.current;
    save.mutate(latest.current);
  };

  useEffect(() => {
    if (text === lastSaved.current) return;
    setStatus('saving');
    const timer = setTimeout(flush, NOTES_SAVE_DELAY);
    return () => clearTimeout(timer);
  }, [text]);

  // Switching months unmounts this; save anything typed in the last moment. The cache is updated too,
  // or coming back to this month (before it's refetched) would show the notes from before that edit.
  useEffect(
    () => () => {
      if (latest.current === lastSaved.current) return;
      cache(latest.current);
      api.setMonthNotes(month, latest.current).catch((error: Error) => {
        queryClient.invalidateQueries({ queryKey: ['income-statement', month] });
        notifications.show({ title: "Couldn't save notes", message: error.message, color: 'red' });
      });
    },
    [month],
  );

  return (
    <MonthNotesCard
      month={month}
      status={status}
      value={text}
      onChange={(value) => setText(value)}
      onBlur={flush}
    />
  );
}

/** The notes card itself; without `value` it's the read-only stand-in shown while the month loads. */
function MonthNotesCard({
  month,
  status = 'idle',
  value,
  onChange,
  onBlur,
}: {
  month: string;
  status?: 'idle' | 'saving' | 'saved';
  value?: string;
  onChange?: (value: string) => void;
  onBlur?: () => void;
}) {
  const loading = value === undefined;
  // Sized like the summary cards beside it: a label row, then a box that grows as notes get longer.
  return (
    <Paper p={{ base: '0.75rem', sm: '0.9rem' }} h="100%">
      <Group justify="space-between" gap="xs" wrap="nowrap">
        <Text className="label-sm">Notes</Text>
        <Text size="xs" c="dimmed" aria-live="polite">
          {status === 'saving' ? 'Saving…' : status === 'saved' ? 'Saved' : ''}
        </Text>
      </Group>
      <Textarea
        mt={6}
        size="sm"
        aria-label={`Notes for ${monthLabel(month)}`}
        placeholder={loading ? 'Loading…' : 'Anything to remember about this month…'}
        autosize
        minRows={3}
        maxRows={8}
        disabled={loading}
        value={value ?? ''}
        onChange={(e) => onChange?.(e.currentTarget.value)}
        onBlur={onBlur}
      />
    </Paper>
  );
}

function budgetFooter(actual: number, budgeted: number, kind: CategoryKind) {
  if (!budgeted) return 'No budget set';
  // For income, beating the budget is good; for expenses, staying under it is.
  return <Delta value={actual - budgeted} goodWhen={kind === 'income' ? 'up' : 'down'} suffix="vs. budget" />;
}

function BudgetVsActual({ statement }: { statement: IncomeStatement }) {
  const section = (kind: CategoryKind, rows: StatementCategory[]) =>
    rows.length > 0 && (
      <>
        <Table.Tr>
          <Table.Th colSpan={3} bg="var(--mantine-color-default-hover)">
            {kind === 'income' ? 'Income' : 'Expenses'}
          </Table.Th>
          <Table.Th className="hide-xs" bg="var(--mantine-color-default-hover)">
          </Table.Th>
        </Table.Tr>
        {rows.map((c) => {
          const ratio = c.budgeted > 0 ? c.actual / c.budgeted : null;
          const over = kind === 'expense' && c.actual > c.budgeted;
          return (
            <Table.Tr key={c.category_id}>
              <Table.Td>
                <Group gap={6} wrap="nowrap">
                  <CategoryDot color={c.color} />
                  <Text size="sm">{c.name}</Text>
                </Group>
                {c.card_items.length > 0 && <CardItems names={c.card_items} />}
                {ratio != null && (
                  <Progress
                    value={Math.min(ratio, 1) * 100}
                    color={over ? 'var(--delta-down)' : kind === 'income' ? 'var(--series-1)' : 'var(--series-2)'}
                    size="sm"
                    mt={4}
                    aria-label={`${Math.round(ratio * 100)}% of budget`}
                  />
                )}
              </Table.Td>
              <Table.Td ta="right" className="num">
                {c.budgeted ? money(c.budgeted) : '—'}
              </Table.Td>
              <Table.Td ta="right" className="num">
                {money(c.actual)}
                {/* Phones hide the difference column; it sits under the actual amount instead. */}
                {c.budgeted > 0 && (
                  <Group justify="flex-end" className="show-xs" mt={2}>
                    <Delta value={c.actual - c.budgeted} goodWhen={kind === 'income' ? 'up' : 'down'} size="xs" />
                  </Group>
                )}
              </Table.Td>
              <Table.Td ta="right" className="hide-xs">
                {c.budgeted ? (
                  <Group justify="flex-end">
                    <Delta value={c.actual - c.budgeted} goodWhen={kind === 'income' ? 'up' : 'down'} />
                  </Group>
                ) : (
                  <Text size="sm" c="dimmed">
                    Unbudgeted
                  </Text>
                )}
              </Table.Td>
            </Table.Tr>
          );
        })}
      </>
    );

  return (
    <Table.ScrollContainer minWidth={480} className="phone-fit">
      <Table verticalSpacing={6}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Category</Table.Th>
            <Table.Th ta="right">Budgeted</Table.Th>
            <Table.Th ta="right">Actual</Table.Th>
            <Table.Th ta="right" className="hide-xs">
              Difference
            </Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {section('income', statement.categories.filter((c) => c.kind === 'income'))}
          {section('expense', statement.categories.filter((c) => c.kind === 'expense'))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}

function TransactionForm({ editing, month, onDone }: { editing: NonNullable<Editing>; month: string; onDone: () => void }) {
  const { txn } = editing;
  const defaultDate = month === thisMonth() ? dayjs().format('YYYY-MM-DD') : `${month}-01`;
  const initial = {
    date: txn?.date ?? defaultDate,
    description: txn?.description ?? '',
    amount: txn?.amount ?? ('' as number | ''),
    category_id: txn?.category.id ?? (null as number | null),
    is_unexpected: txn?.is_unexpected ?? editing.unexpected ?? false,
    notes: txn?.notes ?? '',
  };
  const form = useForm({
    initialValues: initial,
    validate: {
      date: (v) => (v ? null : 'Required'),
      description: (v) => (v.trim() ? null : 'Required'),
      amount: (v) => (typeof v === 'number' && v > 0 ? null : 'Enter an amount greater than 0'),
      category_id: (v) => (v ? null : 'Required'),
    },
  });
  const save = useAppMutation(
    (body: TransactionInput) => (txn ? api.updateTransaction(txn.id, body) : api.createTransaction(body)),
    txn ? 'Transaction updated' : 'Transaction added',
  );

  const submit = (addAnother: boolean) =>
    form.onSubmit((v) =>
      save.mutate(
        {
          date: v.date,
          description: v.description.trim(),
          amount: v.amount as number,
          category_id: v.category_id!,
          is_unexpected: v.is_unexpected,
          notes: v.notes.trim() || null,
          account_id: txn?.account_id ?? null,
        },
        {
          onSuccess: () => {
            if (addAnother) {
              // Keep the date and category; most people enter several from the same statement.
              form.setValues({ description: '', amount: '', notes: '' });
              form.resetDirty();
            } else onDone();
          },
        },
      ),
    );

  return (
    <form onSubmit={submit(false)}>
      <Stack>
        <SimpleGrid cols={{ base: 1, xs: 2 }}>
          <DateInput label="Date" valueFormat="MMM D, YYYY" {...form.getInputProps('date')} />
          <NumberInput label="Amount" prefix="$" decimalScale={2} thousandSeparator="," min={0} {...form.getInputProps('amount')} />
        </SimpleGrid>
        <TextInput label="Description" placeholder="e.g. Costco" data-autofocus {...form.getInputProps('description')} />
        <CategorySelect kind={editing.kind} {...form.getInputProps('category_id')} />
        <Checkbox
          label="Unexpected"
          description="Something you didn't plan or budget for"
          {...form.getInputProps('is_unexpected', { type: 'checkbox' })}
        />
        <Textarea label="Notes" autosize minRows={1} {...form.getInputProps('notes')} />
        <Group justify="flex-end">
          {!txn && (
            <Button variant="default" loading={save.isPending} onClick={() => submit(true)()}>
              Save &amp; add another
            </Button>
          )}
          <Button type="submit" loading={save.isPending}>
            Save
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
