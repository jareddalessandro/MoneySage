import { BarChart } from '@mantine/charts';
import {
  ActionIcon,
  Anchor,
  Autocomplete,
  Badge,
  Button,
  Grid,
  Group,
  Menu,
  Modal,
  NumberInput,
  Progress,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core';
import { DateInput } from '@mantine/dates';
import { useForm } from '@mantine/form';
import {
  IconAlertCircle,
  IconArrowLeft,
  IconDots,
  IconDownload,
  IconFileSpreadsheet,
  IconFileTypePdf,
  IconPencil,
  IconPlus,
  IconTrash,
  IconUserPlus,
} from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { useState } from 'react';
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';

import { api } from '../api';
import {
  confirmDelete,
  EmptyState,
  PageHeader,
  SectionCard,
  StatCard,
  useAppMutation,
} from '../components/common';
import { money, moneyCompact, percent, SERIES_ORDER, signedMoney } from '../format';
import type {
  Company,
  CompanyEntry,
  CompanyEntryInput,
  CompanyEntryKind,
  CompanyMember,
  CompanyMemberInput,
  CompanyProduct,
  CompanySummary,
  RevenueShare,
} from '../types';
import { MEMBER_KINDS } from '../types';
import { CompanyForm, equity } from './Companies';
import { ProductForm, Products } from './CompanyProducts';
import { dueText, PayeeStatement, RevenueShareForm, RevenueShares, ShareMonths } from './CompanyRevenueShares';

const KIND_LABELS: Record<CompanyEntryKind, string> = {
  income: 'Income',
  expense: 'Expense',
  contribution: 'Contribution',
  distribution: 'Distribution',
  funding: 'Funding',
};

type Filter = 'all' | CompanyEntryKind;
/** 'all', 'none' (no product), or a product id. */
type ProductFilter = string;
type EntryEditing = { entry: CompanyEntry | null; kind: CompanyEntryKind; preset?: Partial<CompanyEntryInput> } | null;
type MemberEditing = { member: CompanyMember | null } | null;
type ProductEditing = { product: CompanyProduct | null } | null;
type ShareEditing = { share: RevenueShare | null } | null;

export default function CompanyPage() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const thisYear = dayjs().year();
  const [year, setYear] = useState(thisYear);
  const [filter, setFilter] = useState<Filter>('all');
  const [editingCompany, setEditingCompany] = useState(false);
  const [editingEntry, setEditingEntry] = useState<EntryEditing>(null);
  const [editingMember, setEditingMember] = useState<MemberEditing>(null);
  const [editingProduct, setEditingProduct] = useState<ProductEditing>(null);
  const [editingShare, setEditingShare] = useState<ShareEditing>(null);
  const [monthsShare, setMonthsShare] = useState<RevenueShare | null>(null);
  const [statementShare, setStatementShare] = useState<RevenueShare | null>(null);
  const [productFilter, setProductFilter] = useState<ProductFilter>('all');

  const { data: company, isError } = useQuery({
    queryKey: ['company', id],
    queryFn: () => api.company(id),
    enabled: Number.isFinite(id),
    retry: false,
  });
  const { data: summary } = useQuery({
    queryKey: ['company-summary', id, year],
    queryFn: () => api.companySummary(id, year),
    enabled: !!company,
  });
  const { data: entries = [] } = useQuery({
    queryKey: ['company-entries', id, year],
    queryFn: () => api.companyEntries(id, year),
    enabled: !!company,
  });
  const { data: shares = [] } = useQuery({
    queryKey: ['revenue-shares', id, year],
    queryFn: () => api.revenueShares(id, year),
    enabled: !!company,
  });

  const removeCompany = useAppMutation(() => api.deleteCompany(id), 'Company deleted');
  const removeEntry = useAppMutation((entryId: number) => api.deleteCompanyEntry(id, entryId), 'Entry deleted');
  const removeMember = useAppMutation((memberId: number) => api.deleteCompanyMember(id, memberId), 'Member removed');

  if (!Number.isFinite(id) || isError) return <Navigate to="/companies" replace />;
  if (!company) return null;

  const memberName = (memberId: number | null) => company.members.find((m) => m.id === memberId)?.name ?? '—';
  const years = Array.from(new Set([thisYear, year, ...(summary?.years ?? [])])).sort((a, b) => b - a);
  const productName = (productId: number | null) => company.products.find((p) => p.id === productId)?.name;
  const payeeName = (shareId: number | null) => shares.find((s) => s.id === shareId)?.payee;
  const hasProducts = company.products.length > 0;
  const visible = entries.filter(
    (e) =>
      (filter === 'all' || e.kind === filter) &&
      (productFilter === 'all' ||
        (productFilter === 'none' ? e.product_id == null : e.product_id === Number(productFilter))),
  );
  const recordPayment = (share: RevenueShare) =>
    setEditingEntry({
      entry: null,
      kind: 'expense',
      preset: {
        description: `${share.category} · ${share.payee}`,
        amount: share.balance_due > 0 ? share.balance_due : undefined,
        category: share.category,
        product_id: share.product_id,
        revenue_share_id: share.id,
      },
    });
  const recordFunding = (share: RevenueShare) =>
    setEditingEntry({
      entry: null,
      kind: 'funding',
      preset: { description: `Funding from ${share.payee}`, revenue_share_id: share.id },
    });
  const hasFunding = shares.some((s) => s.funding_received > 0) || entries.some((e) => e.kind === 'funding');
  const hasActivity = summary?.months.some((m) => m.income || m.expenses);
  const expensesFooter =
    [
      summary && summary.cost_of_revenue > 0 ? `Includes ${money(summary.cost_of_revenue)} cost of revenue` : '',
      summary && summary.funding_repaid > 0 ? `excludes ${money(summary.funding_repaid)} that repaid funding` : '',
    ]
      .filter(Boolean)
      .join(' · ') || 'What the company spent';

  return (
    <>
      <Anchor component={Link} to="/companies" size="sm" c="dimmed" mb="xs" display="inline-flex" style={{ alignItems: 'center', gap: 4 }}>
        <IconArrowLeft size={14} /> All companies
      </Anchor>
      <PageHeader
        title={company.name}
        description={company.description ?? 'Income, expenses, member contributions, and ownership.'}
        actions={
          <>
            <Select
              aria-label="Year"
              w={100}
              data={years.map(String)}
              value={String(year)}
              onChange={(v) => v && setYear(Number(v))}
              allowDeselect={false}
            />
            <Menu position="bottom-end" width={260}>
              <Menu.Target>
                <Button variant="default" leftSection={<IconDownload size={16} />}>
                  Export
                </Button>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Label>
                  {year < thisYear ? `Year-end statements · ${year}` : `Statements · ${year} year to date`}
                </Menu.Label>
                <Menu.Item
                  component="a"
                  href={`/api/companies/${id}/statements?year=${year}&format=pdf`}
                  download
                  leftSection={<IconFileTypePdf size={14} />}
                >
                  PDF
                </Menu.Item>
                <Menu.Item
                  component="a"
                  href={`/api/companies/${id}/statements?year=${year}&format=xlsx`}
                  download
                  leftSection={<IconFileSpreadsheet size={14} />}
                >
                  Excel
                </Menu.Item>
                <Text size="xs" c="dimmed" px="sm" py={6}>
                  Income statement, members' capital, cash summary, and every transaction.
                </Text>
              </Menu.Dropdown>
            </Menu>
            <Button leftSection={<IconPlus size={16} />} onClick={() => setEditingEntry({ entry: null, kind: 'expense' })}>
              Add entry
            </Button>
            <Menu position="bottom-end">
              <Menu.Target>
                <ActionIcon variant="default" size="lg" aria-label="Company actions">
                  <IconDots size={18} />
                </ActionIcon>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item leftSection={<IconPencil size={14} />} onClick={() => setEditingCompany(true)}>
                  Edit company
                </Menu.Item>
                <Menu.Item
                  color="red"
                  leftSection={<IconTrash size={14} />}
                  onClick={() =>
                    confirmDelete(
                      `"${company.name}"`,
                      () => removeCompany.mutate(undefined, { onSuccess: () => navigate('/companies') }),
                      'Its members and every income, expense, and contribution entry are deleted too. This cannot be undone.',
                    )
                  }
                >
                  Delete company
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </>
        }
      />

      {summary && (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3, xl: 5 }} mb="xl">
          <StatCard label={`Income · ${year}`} value={money(summary.income)} footer="What the company earned" />
          <StatCard
            label={`Expenses · ${year}`}
            value={money(summary.expenses)}
            footer={expensesFooter}
          />
          <StatCard
            label={`Net profit · ${year}`}
            value={signedMoney(summary.net)}
            footer={summary.income > 0 ? `${percent(summary.net / summary.income)} profit margin` : 'Income minus expenses'}
          />
          <StatCard
            label={`Member contributions · ${year}`}
            value={money(summary.contributions_year)}
            footer={`${money(summary.contributions_total)} all time`}
          />
          <StatCard
            label={`Distributions · ${year}`}
            value={money(summary.distributions_year)}
            footer={`${money(summary.distributions_total)} all time`}
          />
        </SimpleGrid>
      )}

      <Stack gap="xl">
        <Grid gutter="lg">
          <Grid.Col span={{ base: 12, lg: 7 }}>
            <SectionCard
              title="Owners"
              actions={
                <Button size="xs" variant="default" leftSection={<IconUserPlus size={14} />} onClick={() => setEditingMember({ member: null })}>
                  Add member
                </Button>
              }
            >
              {summary && (
                <Owners
                  summary={summary}
                  onEdit={(memberId) => setEditingMember({ member: company.members.find((m) => m.id === memberId)! })}
                  onDelete={(m) => confirmDelete(`member "${m.name}"`, () => removeMember.mutate(m.member_id))}
                  onAdd={() => setEditingMember({ member: null })}
                />
              )}
            </SectionCard>
          </Grid.Col>
          <Grid.Col span={{ base: 12, lg: 5 }}>
            <SectionCard title={`Income vs. expenses · ${year}`}>
              {summary && hasActivity ? (
                <BarChart
                  h={260}
                  data={summary.months.map((m) => ({
                    month: dayjs(`${m.month}-01`).format('MMM'),
                    Income: m.income,
                    Expenses: m.expenses,
                  }))}
                  dataKey="month"
                  series={[
                    { name: 'Income', color: 'var(--series-1)' },
                    { name: 'Expenses', color: 'var(--series-2)' },
                  ]}
                  withLegend
                  legendProps={{ verticalAlign: 'top', height: 36, itemSorter: SERIES_ORDER }}
                  valueFormatter={(v) => money(v)}
                  yAxisProps={{ tickFormatter: (v: number) => moneyCompact(v), width: 64 }}
                  gridAxis="x"
                  strokeDasharray="0"
                  barProps={{ radius: [4, 4, 0, 0] }}
                  barChartProps={{ barGap: 2 }}
                  maxBarWidth={14}
                />
              ) : (
                <EmptyState message={`Income and expenses for ${year} will chart here by month.`} />
              )}
            </SectionCard>
          </Grid.Col>
        </Grid>

        <RevenueShares
          company={company}
          shares={shares}
          year={year}
          onAdd={() => setEditingShare({ share: null })}
          onEdit={(share) => setEditingShare({ share })}
          onPay={recordPayment}
          onFund={recordFunding}
          onMonths={setMonthsShare}
          onStatement={setStatementShare}
        />

        <Products
          company={company}
          summary={summary}
          onAdd={() => setEditingProduct({ product: null })}
          onEdit={(product) => setEditingProduct({ product })}
        />

        <SectionCard
          title={`Entries · ${year}`}
          actions={
            <>
              {hasProducts && (
                <Select
                  aria-label="Product"
                  size="xs"
                  w={160}
                  value={productFilter}
                  onChange={(v) => setProductFilter(v ?? 'all')}
                  allowDeselect={false}
                  data={[
                    { value: 'all', label: 'All products' },
                    ...company.products.map((p) => ({ value: String(p.id), label: p.name })),
                    { value: 'none', label: 'No product' },
                  ]}
                />
              )}
              <SegmentedControl
                size="xs"
                value={filter}
                onChange={(v) => setFilter(v as Filter)}
                data={[
                  { value: 'all', label: 'All' },
                  { value: 'income', label: 'Income' },
                  { value: 'expense', label: 'Expenses' },
                  { value: 'contribution', label: 'Contributions' },
                  { value: 'distribution', label: 'Distributions' },
                  ...(hasFunding ? [{ value: 'funding', label: 'Funding' }] : []),
                ]}
              />
            </>
          }
        >
          {entries.length === 0 ? (
            <EmptyState
              message={`No entries for ${year} yet. Add income, expenses, contributions, and distributions as they happen.`}
              action={
                <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setEditingEntry({ entry: null, kind: 'expense' })}>
                  Add entry
                </Button>
              }
            />
          ) : (
            <Table.ScrollContainer minWidth={640} maxHeight={520}>
              <Table highlightOnHover stickyHeader verticalSpacing="xs">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th w={100}>Date</Table.Th>
                    <Table.Th>Description</Table.Th>
                    <Table.Th w={130}>Type</Table.Th>
                    <Table.Th>Category or member</Table.Th>
                    {hasProducts && <Table.Th>Product</Table.Th>}
                    <Table.Th ta="right">Amount</Table.Th>
                    <Table.Th w={70} />
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {visible.map((e) => (
                    <Table.Tr key={e.id}>
                      <Table.Td className="num">{dayjs(e.date).format('MMM D')}</Table.Td>
                      <Table.Td>
                        <Text size="sm">{e.description}</Text>
                        {e.notes && (
                          <Text size="xs" c="dimmed" lineClamp={1}>
                            {e.notes}
                          </Text>
                        )}
                      </Table.Td>
                      <Table.Td>
                        <Badge size="sm" variant="light" color="gray">
                          {KIND_LABELS[e.kind]}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        {e.kind === 'funding' ? (
                          <Text size="sm">From {payeeName(e.revenue_share_id) ?? 'a revenue-share payee'}</Text>
                        ) : (
                          <Text size="sm" c={MEMBER_KINDS.includes(e.kind) || e.category ? undefined : 'dimmed'}>
                            {MEMBER_KINDS.includes(e.kind) ? memberName(e.member_id) : (e.category ?? '—')}
                          </Text>
                        )}
                        {e.kind === 'expense' && e.revenue_share_id != null && (
                          <Text size="xs" c="dimmed">
                            Pays {payeeName(e.revenue_share_id) ?? 'a revenue share'}
                            {e.funding_repaid
                              ? e.funding_repaid >= e.amount
                                ? ' · repaid funding'
                                : ` · ${money(e.funding_repaid)} repaid funding`
                              : ''}
                          </Text>
                        )}
                      </Table.Td>
                      {hasProducts && (
                        <Table.Td>
                          <Text size="sm" c={e.product_id == null ? 'dimmed' : undefined}>
                            {productName(e.product_id) ?? '—'}
                          </Text>
                        </Table.Td>
                      )}
                      <Table.Td ta="right" className="num" fw={500}>
                        {e.kind === 'income' ? '+' : e.kind === 'expense' ? '−' : ''}
                        {money(e.amount)}
                      </Table.Td>
                      <Table.Td>
                        <Group gap={4} wrap="nowrap" justify="flex-end">
                          <ActionIcon variant="subtle" color="gray" aria-label="Edit" onClick={() => setEditingEntry({ entry: e, kind: e.kind })}>
                            <IconPencil size={16} />
                          </ActionIcon>
                          <ActionIcon
                            variant="subtle"
                            color="red"
                            aria-label="Delete"
                            onClick={() => confirmDelete(`"${e.description}"`, () => removeEntry.mutate(e.id))}
                          >
                            <IconTrash size={16} />
                          </ActionIcon>
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                  {visible.length === 0 && (
                    <Table.Tr>
                      <Table.Td colSpan={hasProducts ? 7 : 6}>
                        <Text size="sm" c="dimmed" ta="center" py="md">
                          No {filter === 'all' ? '' : `${KIND_LABELS[filter as CompanyEntryKind].toLowerCase()} `}entries
                          {productFilter === 'all' ? '' : productFilter === 'none' ? ' without a product' : ` for ${productName(Number(productFilter))}`} in {year}.
                        </Text>
                      </Table.Td>
                    </Table.Tr>
                  )}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          )}
        </SectionCard>
      </Stack>

      <Modal opened={editingCompany} onClose={() => setEditingCompany(false)} title="Edit company">
        {editingCompany && <CompanyForm company={company} onDone={() => setEditingCompany(false)} />}
      </Modal>
      <Modal
        opened={editingMember !== null}
        onClose={() => setEditingMember(null)}
        title={editingMember?.member ? 'Edit member' : 'Add member'}
      >
        {editingMember && (
          <MemberForm
            key={editingMember.member?.id ?? 'new'}
            company={company}
            member={editingMember.member}
            onDone={() => setEditingMember(null)}
          />
        )}
      </Modal>
      <Modal
        opened={editingEntry !== null}
        onClose={() => setEditingEntry(null)}
        title={editingEntry?.entry ? 'Edit entry' : 'Add entry'}
        size="lg"
      >
        {editingEntry && (
          <EntryForm
            key={editingEntry.entry?.id ?? 'new'}
            company={company}
            summary={summary}
            shares={shares}
            year={year}
            editing={editingEntry}
            onDone={() => setEditingEntry(null)}
          />
        )}
      </Modal>
      <Modal
        opened={editingProduct !== null}
        onClose={() => setEditingProduct(null)}
        title={editingProduct?.product ? 'Edit product' : 'Add product'}
      >
        {editingProduct && (
          <ProductForm companyId={id} product={editingProduct.product} onDone={() => setEditingProduct(null)} />
        )}
      </Modal>
      <Modal
        opened={editingShare !== null}
        onClose={() => setEditingShare(null)}
        title={editingShare?.share ? 'Edit revenue share' : 'Add revenue share'}
        size="lg"
      >
        {editingShare && (
          <RevenueShareForm company={company} summary={summary} share={editingShare.share} onDone={() => setEditingShare(null)} />
        )}
      </Modal>
      <Modal
        opened={monthsShare !== null}
        onClose={() => setMonthsShare(null)}
        title={monthsShare ? `${monthsShare.payee} · by month` : ''}
        size="xl"
      >
        {monthsShare && (
          <ShareMonths key={monthsShare.id} companyId={id} share={monthsShare} year={year} onDone={() => setMonthsShare(null)} />
        )}
      </Modal>
      <Modal
        opened={statementShare !== null}
        onClose={() => setStatementShare(null)}
        title={statementShare ? `Monthly statement for ${statementShare.payee}` : ''}
      >
        {statementShare && <PayeeStatement key={statementShare.id} companyId={id} share={statementShare} />}
      </Modal>
    </>
  );
}

function Owners({
  summary,
  onEdit,
  onDelete,
  onAdd,
}: {
  summary: CompanySummary;
  onEdit: (memberId: number) => void;
  onDelete: (m: CompanySummary['members'][number]) => void;
  onAdd: () => void;
}) {
  if (summary.members.length === 0) {
    return (
      <EmptyState
        message="Add the company's members and how much of it each one owns."
        action={
          <Button size="xs" variant="light" leftSection={<IconUserPlus size={14} />} onClick={onAdd}>
            Add member
          </Button>
        }
      />
    );
  }
  const unassigned = 100 - summary.equity_assigned;
  const totalShare = summary.members.reduce((s, m) => s + m.profit_share, 0);
  return (
    <>
      <Table.ScrollContainer minWidth={680}>
        <Table verticalSpacing={6} highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Member</Table.Th>
              <Table.Th w={140}>Ownership</Table.Th>
              <Table.Th ta="right">Contributed {summary.year}</Table.Th>
              <Table.Th ta="right">Distributed {summary.year}</Table.Th>
              <Table.Th ta="right">Share of profit</Table.Th>
              <Table.Th ta="right">Net invested</Table.Th>
              <Table.Th w={70} />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {summary.members.map((m) => (
              <Table.Tr key={m.member_id}>
                <Table.Td>
                  <Text size="sm" fw={500}>
                    {m.name}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" className="num">
                    {equity(m.equity_percent)}
                  </Text>
                  <Progress value={m.equity_percent} color="var(--series-1)" size="sm" mt={4} aria-hidden />
                </Table.Td>
                <Table.Td ta="right" className="num">
                  {money(m.contributed_year)}
                </Table.Td>
                <Table.Td ta="right" className="num">
                  {money(m.distributed_year)}
                </Table.Td>
                <Table.Td ta="right" className="num">
                  {signedMoney(m.profit_share)}
                </Table.Td>
                <Table.Td ta="right" className="num">
                  {money(m.contributed_total - m.distributed_total)}
                </Table.Td>
                <Table.Td>
                  <Group gap={4} wrap="nowrap" justify="flex-end">
                    <ActionIcon variant="subtle" color="gray" aria-label={`Edit ${m.name}`} onClick={() => onEdit(m.member_id)}>
                      <IconPencil size={16} />
                    </ActionIcon>
                    <ActionIcon variant="subtle" color="red" aria-label={`Remove ${m.name}`} onClick={() => onDelete(m)}>
                      <IconTrash size={16} />
                    </ActionIcon>
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
          <Table.Tfoot>
            <Table.Tr>
              <Table.Th>Total</Table.Th>
              <Table.Th className="num">{equity(summary.equity_assigned)}</Table.Th>
              <Table.Th ta="right" className="num">
                {money(summary.contributions_year)}
              </Table.Th>
              <Table.Th ta="right" className="num">
                {money(summary.distributions_year)}
              </Table.Th>
              <Table.Th ta="right" className="num">
                {signedMoney(totalShare)}
              </Table.Th>
              <Table.Th ta="right" className="num">
                {money(summary.contributions_total - summary.distributions_total)}
              </Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Tfoot>
        </Table>
      </Table.ScrollContainer>
      <Stack gap={4} mt="sm">
        {unassigned > 0.00005 && (
          <Group gap={6} wrap="nowrap">
            <IconAlertCircle size={14} color="var(--primary)" aria-hidden />
            <Text size="xs" c="dimmed">
              {equity(unassigned)} of the company isn't assigned to a member yet.
            </Text>
          </Group>
        )}
        <Text size="xs" c="dimmed">
          Share of profit is {summary.year}'s net profit times each member's ownership: what they're entitled to on
          paper. Distributed is what was actually paid out to them. Net invested is everything they've contributed
          minus everything distributed to them, all time; below $0 means they've taken out more than they put in.
        </Text>
      </Stack>
    </>
  );
}

function MemberForm({ company, member, onDone }: { company: Company; member: CompanyMember | null; onDone: () => void }) {
  const others = company.members.filter((m) => m.id !== member?.id).reduce((s, m) => s + m.equity_percent, 0);
  const available = Number((100 - others).toFixed(4));
  const form = useForm({
    initialValues: { name: member?.name ?? '', equity_percent: member?.equity_percent ?? ('' as number | '') },
    validate: {
      name: (v) => (v.trim() ? null : 'Required'),
      equity_percent: (v) => (v !== '' && v > available ? `At most ${available}%: the others own ${equity(others)}` : null),
    },
  });
  const save = useAppMutation(
    (body: CompanyMemberInput) =>
      member ? api.updateCompanyMember(company.id, member.id, body) : api.createCompanyMember(company.id, body),
    member ? 'Member updated' : 'Member added',
  );
  return (
    <form
      onSubmit={form.onSubmit((v) =>
        save.mutate(
          { name: v.name.trim(), equity_percent: v.equity_percent === '' ? 0 : v.equity_percent },
          { onSuccess: onDone },
        ),
      )}
    >
      <Stack>
        <TextInput label="Name" placeholder="e.g. Jared" data-autofocus {...form.getInputProps('name')} />
        <NumberInput
          label="Ownership"
          description={`${available}% of the company is available`}
          suffix="%"
          decimalScale={4}
          min={0}
          max={100}
          {...form.getInputProps('equity_percent')}
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={onDone}>
            Cancel
          </Button>
          <Button type="submit" loading={save.isPending}>
            {member ? 'Save' : 'Add member'}
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

function EntryForm({
  company,
  summary,
  shares,
  year,
  editing,
  onDone,
}: {
  company: Company;
  summary: CompanySummary | undefined;
  shares: RevenueShare[];
  year: number;
  editing: NonNullable<EntryEditing>;
  onDone: () => void;
}) {
  const { entry, preset } = editing;
  const defaultDate = year === dayjs().year() ? dayjs().format('YYYY-MM-DD') : `${year}-01-01`;
  const form = useForm({
    initialValues: {
      kind: entry?.kind ?? editing.kind,
      date: entry?.date ?? defaultDate,
      description: entry?.description ?? preset?.description ?? '',
      amount: entry?.amount ?? preset?.amount ?? ('' as number | ''),
      category: entry?.category ?? preset?.category ?? '',
      member_id: entry?.member_id != null ? String(entry.member_id) : company.members.length === 1 ? String(company.members[0].id) : null,
      product_id: idString(entry ? entry.product_id : preset?.product_id),
      revenue_share_id: idString(entry ? entry.revenue_share_id : preset?.revenue_share_id),
      notes: entry?.notes ?? '',
    },
    validate: {
      date: (v) => (v ? null : 'Required'),
      description: (v) => (v.trim() ? null : 'Required'),
      amount: (v) => (typeof v === 'number' && v > 0 ? null : 'Enter an amount greater than 0'),
      member_id: (v, values) =>
        MEMBER_KINDS.includes(values.kind) && !v
          ? values.kind === 'contribution'
            ? 'Pick who made the contribution'
            : 'Pick who was paid'
          : null,
      revenue_share_id: (v, values) => (values.kind === 'funding' && !v ? 'Pick who provided the funding' : null),
    },
  });
  const save = useAppMutation(
    (body: CompanyEntryInput) =>
      entry ? api.updateCompanyEntry(company.id, entry.id, body) : api.createCompanyEntry(company.id, body),
    entry ? 'Entry updated' : 'Entry added',
  );
  const kind = form.values.kind;
  const isContribution = kind === 'contribution';
  const isMemberEntry = MEMBER_KINDS.includes(kind);
  const isFunding = kind === 'funding';
  const suggestions = (kind === 'income' ? summary?.income_categories : summary?.expense_categories) ?? [];
  const noMembers = isMemberEntry && company.members.length === 0;
  const paidShare = shares.find((s) => String(s.id) === form.values.revenue_share_id);
  const pickShare = (value: string | null) => {
    form.setFieldValue('revenue_share_id', value);
    const share = shares.find((s) => String(s.id) === value);
    if (!share) return;
    // Fill in what the agreement implies, without overwriting what's been typed.
    if (!form.values.category.trim()) form.setFieldValue('category', share.category);
    if (!form.values.product_id && share.product_id != null) form.setFieldValue('product_id', String(share.product_id));
    if (!form.values.description.trim()) form.setFieldValue('description', `${share.category} · ${share.payee}`);
  };

  const submit = (addAnother: boolean) =>
    form.onSubmit((v) =>
      save.mutate(
        {
          kind: v.kind,
          date: v.date,
          description: v.description.trim(),
          amount: v.amount as number,
          category: isMemberEntry || isFunding ? null : v.category.trim() || null,
          member_id: isMemberEntry && v.member_id ? Number(v.member_id) : null,
          product_id: !isMemberEntry && !isFunding && v.product_id ? Number(v.product_id) : null,
          revenue_share_id:
            (kind === 'expense' || isFunding) && v.revenue_share_id ? Number(v.revenue_share_id) : null,
          notes: v.notes.trim() || null,
        },
        {
          onSuccess: () => {
            if (addAnother) {
              // Keep the type, date, category or member, and product (or funder) for the next one.
              form.setValues({ description: '', amount: '', notes: '', ...(isFunding ? {} : { revenue_share_id: null }) });
              form.resetDirty();
            } else onDone();
          },
        },
      ),
    );

  return (
    <form onSubmit={submit(false)}>
      <Stack>
        <SegmentedControl
          fullWidth
          value={kind}
          onChange={(v) => form.setFieldValue('kind', v as CompanyEntryKind)}
          data={[
            { value: 'income', label: 'Income' },
            { value: 'expense', label: 'Expense' },
            { value: 'contribution', label: 'Contribution' },
            { value: 'distribution', label: 'Distribution' },
            ...(shares.length > 0 || isFunding ? [{ value: 'funding', label: 'Funding' }] : []),
          ]}
        />
        <Group grow align="flex-start">
          <DateInput label="Date" valueFormat="MMM D, YYYY" {...form.getInputProps('date')} />
          <NumberInput label="Amount" prefix="$" decimalScale={2} thousandSeparator="," min={0} {...form.getInputProps('amount')} />
        </Group>
        <TextInput
          label="Description"
          placeholder={
            isFunding
              ? 'e.g. Data costs funding'
              : isContribution
              ? 'e.g. Startup capital'
              : kind === 'distribution'
                ? 'e.g. Q3 profit distribution'
                : kind === 'income'
                  ? 'e.g. Client invoice #104'
                  : 'e.g. Website hosting'
          }
          data-autofocus
          {...form.getInputProps('description')}
        />
        {isFunding ? (
          <Select
            label="From"
            placeholder="Pick a revenue share"
            description="Recorded as a liability for the sale of future revenue, not income. Payments to them repay it first."
            data={shares.map((s) => ({ value: String(s.id), label: s.payee }))}
            comboboxProps={{ withinPortal: true }}
            {...form.getInputProps('revenue_share_id')}
          />
        ) : isMemberEntry ? (
          noMembers ? (
            <Group gap={6} wrap="nowrap">
              <IconAlertCircle size={16} color="var(--primary)" aria-hidden />
              <Text size="sm" c="dimmed">
                Add a member under Owners first, then record their {kind}.
              </Text>
            </Group>
          ) : (
            <Select
              label={isContribution ? 'Contributed by' : 'Paid to'}
              placeholder="Pick a member"
              data={company.members.map((m) => ({ value: String(m.id), label: m.name }))}
              comboboxProps={{ withinPortal: true }}
              {...form.getInputProps('member_id')}
            />
          )
        ) : (
          <Autocomplete
            label="Category"
            description="Optional. Pick one you've used or type a new one."
            placeholder={kind === 'income' ? 'e.g. Consulting' : 'e.g. Software'}
            data={suggestions}
            comboboxProps={{ withinPortal: true }}
            {...form.getInputProps('category')}
          />
        )}
        {!isMemberEntry && !isFunding && (company.products.length > 0 || (kind === 'expense' && shares.length > 0)) && (
          <Group grow align="flex-end">
            {company.products.length > 0 && (
              <Select
                label="Product"
                placeholder="No product"
                data={company.products.map((p) => ({ value: String(p.id), label: p.name }))}
                clearable
                comboboxProps={{ withinPortal: true }}
                {...form.getInputProps('product_id')}
              />
            )}
            {kind === 'expense' && shares.length > 0 && (
              <Select
                label="Pays a revenue share"
                placeholder="No"
                description={paidShare ? dueText(paidShare) : undefined}
                data={shares.map((s) => ({ value: String(s.id), label: s.payee }))}
                clearable
                comboboxProps={{ withinPortal: true }}
                value={form.values.revenue_share_id}
                onChange={pickShare}
              />
            )}
          </Group>
        )}
        <Textarea label="Notes" autosize minRows={1} {...form.getInputProps('notes')} />
        <Group justify="flex-end">
          {!entry && (
            <Button variant="default" loading={save.isPending} disabled={noMembers} onClick={() => submit(true)()}>
              Save &amp; add another
            </Button>
          )}
          <Button type="submit" loading={save.isPending} disabled={noMembers}>
            Save
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

const idString = (id: number | null | undefined) => (id != null ? String(id) : null);
