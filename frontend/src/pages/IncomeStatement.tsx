import { BarChart } from '@mantine/charts';
import {
  ActionIcon,
  Badge,
  Button,
  Checkbox,
  Grid,
  Group,
  Menu,
  Modal,
  NumberInput,
  Progress,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core';
import { DateInput } from '@mantine/dates';
import { useForm } from '@mantine/form';
import { IconAlertTriangle, IconChevronDown, IconPencil, IconPlus, IconSearch, IconTrash } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { useMemo, useState } from 'react';

import { api } from '../api';
import CategorySelect from '../components/CategorySelect';
import {
  confirmDelete,
  Delta,
  EmptyState,
  MonthSwitcher,
  PageHeader,
  SectionCard,
  StatCard,
  useAppMutation,
} from '../components/common';
import { dateLabel, money, monthLabel, monthShort, moneyCompact, SERIES_ORDER, signedMoney, thisMonth } from '../format';
import type { CategoryKind, IncomeStatement, StatementCategory, Transaction, TransactionInput } from '../types';

type Filter = 'all' | 'income' | 'expense' | 'unexpected';
type Editing = { txn: Transaction | null; unexpected?: boolean; kind?: CategoryKind } | null;

export default function IncomeStatementPage() {
  const [month, setMonth] = useState(thisMonth);
  const [filter, setFilter] = useState<Filter>('all');
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<Editing>(null);

  const { data: txns = [] } = useQuery({ queryKey: ['transactions', month], queryFn: () => api.transactions(month) });
  const { data: statement } = useQuery({ queryKey: ['income-statement', month], queryFn: () => api.incomeStatement(month) });
  const { data: trend = [] } = useQuery({ queryKey: ['income-trend'], queryFn: () => api.incomeTrend(12) });
  const remove = useAppMutation((id: number) => api.deleteTransaction(id), 'Transaction deleted');

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return txns.filter((t) => {
      if (filter === 'unexpected' && !t.is_unexpected) return false;
      if ((filter === 'income' || filter === 'expense') && t.category.kind !== filter) return false;
      return !term || t.description.toLowerCase().includes(term) || t.category.name.toLowerCase().includes(term);
    });
  }, [txns, filter, search]);

  const unexpected = txns.filter((t) => t.is_unexpected);
  const trendData = trend.map((p) => ({ month: monthShort(p.month), Income: p.income, Expenses: p.expenses }));
  const hasTrend = trend.some((p) => p.income || p.expenses);

  const rowActions = (t: Transaction) => (
    <Group gap={4} wrap="nowrap" justify="flex-end">
      <ActionIcon variant="subtle" color="gray" aria-label="Edit" onClick={() => setEditing({ txn: t })}>
        <IconPencil size={16} />
      </ActionIcon>
      <ActionIcon
        variant="subtle"
        color="red"
        aria-label="Delete"
        onClick={() => confirmDelete(`"${t.description}"`, () => remove.mutate(t.id))}
      >
        <IconTrash size={16} />
      </ActionIcon>
    </Group>
  );

  return (
    <>
      <PageHeader
        title="Income Statement"
        description="What actually came in and went out each month."
        actions={
          <>
            <MonthSwitcher value={month} onChange={setMonth} />
            <Button leftSection={<IconPlus size={16} />} onClick={() => setEditing({ txn: null })}>
              Add transaction
            </Button>
          </>
        }
      />

      <SimpleGrid cols={{ base: 1, xs: 2, md: 4 }} mb="md">
        <StatCard
          label="Income"
          value={money(statement?.total_income)}
          footer={statement && budgetFooter(statement.total_income, statement.budgeted_income, 'income')}
        />
        <StatCard
          label="Expenses"
          value={money(statement?.total_expenses)}
          footer={statement && budgetFooter(statement.total_expenses, statement.budgeted_expenses, 'expense')}
        />
        <StatCard
          label="Net"
          value={<span className={statement && statement.net < 0 ? 'delta-down' : undefined}>{money(statement?.net)}</span>}
          footer={statement && statement.net >= 0 ? 'Saved this month' : 'Spent more than earned'}
        />
        <StatCard
          label="Unexpected"
          value={money(statement?.unexpected_expenses)}
          footer={
            statement && statement.unexpected_income > 0
              ? `in expenses · ${money(statement.unexpected_income)} in income`
              : 'in unplanned expenses'
          }
        />
      </SimpleGrid>

      <Stack gap="md">
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
                w={180}
              />
              <SegmentedControl
                size="xs"
                value={filter}
                onChange={(v) => setFilter(v as Filter)}
                data={[
                  { value: 'all', label: 'All' },
                  { value: 'income', label: 'Income' },
                  { value: 'expense', label: 'Expenses' },
                  { value: 'unexpected', label: 'Unexpected' },
                ]}
              />
            </>
          }
        >
          {txns.length === 0 ? (
            <EmptyState
              message={`No transactions for ${monthLabel(month)} yet.`}
              action={
                <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setEditing({ txn: null })}>
                  Add transaction
                </Button>
              }
            />
          ) : (
            <Table.ScrollContainer minWidth={640} maxHeight={480}>
              <Table highlightOnHover stickyHeader verticalSpacing="xs">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th w={120}>Date</Table.Th>
                    <Table.Th>Description</Table.Th>
                    <Table.Th>Category</Table.Th>
                    <Table.Th ta="right">Amount</Table.Th>
                    <Table.Th w={70} />
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {visible.map((t) => (
                    <Table.Tr key={t.id}>
                      <Table.Td className="num">{dayjs(t.date).format('MMM D')}</Table.Td>
                      <Table.Td>
                        <Group gap={6} wrap="nowrap">
                          <Text size="sm">{t.description}</Text>
                          {t.is_unexpected && (
                            <Badge size="xs" color="orange" variant="light" leftSection={<IconAlertTriangle size={10} />}>
                              Unexpected
                            </Badge>
                          )}
                        </Group>
                        {t.notes && (
                          <Text size="xs" c="dimmed" lineClamp={1}>
                            {t.notes}
                          </Text>
                        )}
                      </Table.Td>
                      <Table.Td>
                        <Badge variant="light" color={t.category.kind === 'income' ? 'blue' : 'gray'} fw={500} tt="none">
                          {t.category.name}
                        </Badge>
                      </Table.Td>
                      <Table.Td ta="right" className="num" fw={500}>
                        {t.category.kind === 'income' ? '+' : '−'}
                        {money(t.amount)}
                      </Table.Td>
                      <Table.Td>{rowActions(t)}</Table.Td>
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

        <Grid gutter="md">
          <Grid.Col span={{ base: 12, lg: 7 }}>
            <SectionCard title="Budget vs. actual">
              {statement && statement.categories.length > 0 ? (
                <BudgetVsActual statement={statement} />
              ) : (
                <EmptyState message="Add budget items or transactions to compare plan vs. reality." />
              )}
            </SectionCard>
          </Grid.Col>
          <Grid.Col span={{ base: 12, lg: 5 }}>
            <SectionCard
              title="Unexpected items"
              actions={
                <Menu position="bottom-end">
                  <Menu.Target>
                    <Button size="xs" variant="light" color="orange" rightSection={<IconChevronDown size={14} />}>
                      Add unexpected
                    </Button>
                  </Menu.Target>
                  <Menu.Dropdown>
                    <Menu.Item onClick={() => setEditing({ txn: null, unexpected: true, kind: 'expense' })}>
                      Unexpected expense
                    </Menu.Item>
                    <Menu.Item onClick={() => setEditing({ txn: null, unexpected: true, kind: 'income' })}>
                      Unexpected income
                    </Menu.Item>
                  </Menu.Dropdown>
                </Menu>
              }
            >
              {unexpected.length === 0 ? (
                <EmptyState message="Nothing unexpected this month. 🎉" />
              ) : (
                <Table verticalSpacing="xs">
                  <Table.Tbody>
                    {unexpected.map((t) => (
                      <Table.Tr key={t.id}>
                        <Table.Td>
                          <Text size="sm">{t.description}</Text>
                          <Text size="xs" c="dimmed">
                            {dateLabel(t.date)} · {t.category.name}
                          </Text>
                        </Table.Td>
                        <Table.Td ta="right" className="num" fw={500}>
                          {t.category.kind === 'income' ? '+' : '−'}
                          {money(t.amount)}
                        </Table.Td>
                        <Table.Td w={70}>{rowActions(t)}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                  <Table.Tfoot>
                    <Table.Tr>
                      <Table.Th>Net unexpected</Table.Th>
                      <Table.Th ta="right" className="num">
                        {statement && signedMoney(statement.unexpected_income - statement.unexpected_expenses)}
                      </Table.Th>
                      <Table.Th />
                    </Table.Tr>
                  </Table.Tfoot>
                </Table>
              )}
            </SectionCard>
          </Grid.Col>
        </Grid>

        <SectionCard title="Income vs. expenses · last 12 months">
          {hasTrend ? (
            <BarChart
              h={280}
              data={trendData}
              dataKey="month"
              series={[
                { name: 'Income', color: 'var(--series-1)' },
                { name: 'Expenses', color: 'var(--series-2)' },
              ]}
              withLegend
              legendProps={{ verticalAlign: 'top', height: 36, itemSorter: SERIES_ORDER }}
              valueFormatter={(v) => money(v)}
              yAxisProps={{ tickFormatter: (v: number) => moneyCompact(v), width: 70 }}
              gridAxis="x"
              strokeDasharray="0"
              barProps={{ radius: [4, 4, 0, 0] }}
              barChartProps={{ barGap: 2 }}
              maxBarWidth={24}
            />
          ) : (
            <EmptyState message="Your monthly history will appear here as you add transactions." />
          )}
        </SectionCard>
      </Stack>

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
          <Table.Th colSpan={4} bg="var(--mantine-color-default-hover)">
            {kind === 'income' ? 'Income' : 'Expenses'}
          </Table.Th>
        </Table.Tr>
        {rows.map((c) => {
          const ratio = c.budgeted > 0 ? c.actual / c.budgeted : null;
          const over = kind === 'expense' && c.actual > c.budgeted;
          return (
            <Table.Tr key={c.category_id}>
              <Table.Td>
                <Text size="sm">{c.name}</Text>
                {ratio != null && (
                  <Progress
                    value={Math.min(ratio, 1) * 100}
                    color={over ? 'red' : kind === 'income' ? 'blue' : 'teal'}
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
              </Table.Td>
              <Table.Td ta="right">
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
    <Table.ScrollContainer minWidth={480}>
      <Table verticalSpacing={6}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Category</Table.Th>
            <Table.Th ta="right">Budgeted</Table.Th>
            <Table.Th ta="right">Actual</Table.Th>
            <Table.Th ta="right">Difference</Table.Th>
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
        <Group grow align="flex-start">
          <DateInput label="Date" valueFormat="MMM D, YYYY" {...form.getInputProps('date')} />
          <NumberInput label="Amount" prefix="$" decimalScale={2} thousandSeparator="," min={0} {...form.getInputProps('amount')} />
        </Group>
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
