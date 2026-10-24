import { AreaChart, LineChart } from '@mantine/charts';
import {
  ActionIcon,
  Badge,
  Button,
  Group,
  Menu,
  Modal,
  NumberInput,
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
import { useForm } from '@mantine/form';
import {
  IconAlertCircle,
  IconArchive,
  IconArchiveOff,
  IconCopy,
  IconDeviceFloppy,
  IconDots,
  IconLink,
  IconPencil,
  IconPlus,
  IconTrash,
} from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { Fragment, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { api } from '../api';
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
import {
  ASSET_SUBTYPES,
  LIABILITY_SUBTYPES,
  money,
  moneyCompact,
  monthLabel,
  monthShort,
  signedPercent,
  subtypeLabel,
  thisMonth,
} from '../format';
import type { Account, AccountInput, AccountKind, BalanceRow } from '../types';

const CASH_SUBTYPES = new Set(['checking', 'savings', 'cash']);
const INVESTMENT_SUBTYPES = new Set(['brokerage', 'retirement', 'hsa', 'crypto']);

// Assets break down the same way as the cards at the top.
const ASSET_GROUPS = [
  { key: 'cash', label: 'Cash', has: (subtype: string) => CASH_SUBTYPES.has(subtype) },
  { key: 'investments', label: 'Investments', has: (subtype: string) => INVESTMENT_SUBTYPES.has(subtype) },
  {
    key: 'other',
    label: 'Other assets',
    has: (subtype: string) => !CASH_SUBTYPES.has(subtype) && !INVESTMENT_SUBTYPES.has(subtype),
  },
];

/** Total of a group of accounts, and its change vs. last month over the accounts that have both months. */
function groupTotal(rows: BalanceRow[], subtypes: Set<string>) {
  const group = rows.filter((r) => r.account.kind === 'asset' && subtypes.has(r.account.subtype));
  const both = group.filter((r) => r.balance != null && r.previous_balance != null);
  const previous = both.reduce((s, r) => s + r.previous_balance!, 0);
  const change = both.length ? both.reduce((s, r) => s + r.balance! - r.previous_balance!, 0) : null;
  return {
    total: group.some((r) => r.balance != null) ? group.reduce((s, r) => s + (r.balance ?? 0), 0) : null,
    change,
    pct: change != null && previous > 0 ? change / previous : null,
  };
}

/**
 * Y-axis range fitted to the data instead of starting at $0, so month-to-month moves are visible:
 * padded so no point sits on the edge, with ticks at round, evenly spaced steps.
 */
function fittedAxis(values: number[]): { domain: [number, number]; ticks: number[] } | undefined {
  if (values.length === 0) return undefined;
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const pad = (hi - lo) * 0.15 || Math.abs(hi) * 0.02 || 1;
  const rough = (hi - lo + 2 * pad) / 4;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((m) => m >= rough)!;
  const min = Math.floor((lo - pad) / step) * step;
  const steps = Math.max(4, Math.ceil((hi + pad - min) / step));
  return { domain: [min, min + step * steps], ticks: Array.from({ length: steps + 1 }, (_, i) => min + step * i) };
}

type Draft = Record<number, number | ''>;
type Editing = { account: Account | null } | null;

const draftFrom = (rows: BalanceRow[]): Draft =>
  Object.fromEntries(rows.map((r) => [r.account.id, r.balance ?? '']));

export default function BalanceSheetPage() {
  const [month, setMonth] = useState(thisMonth);
  const [editing, setEditing] = useState<Editing>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [trendView, setTrendView] = useState<'net' | 'split'>('net');

  const { data: sheet } = useQuery({ queryKey: ['balance-sheet', month], queryFn: () => api.balanceSheet(month) });
  const { data: trend = [] } = useQuery({ queryKey: ['net-worth-trend'], queryFn: () => api.netWorthTrend(36) });

  // Reset the editable balances whenever fresh data for a month arrives.
  useEffect(() => {
    if (sheet?.month === month) setDraft(draftFrom(sheet.rows));
  }, [sheet, month]);

  // Synced accounts are read-only this month (live from Stocks) and in future months (no value until then);
  // past months stay editable for entering history. 'YYYY-MM' strings compare in date order.
  const isSyncedMonth = month >= thisMonth();
  const isSynced = (r: BalanceRow) => r.account.sync_from_holdings && isSyncedMonth;
  const rows = sheet?.month === month ? sheet.rows : [];

  const changed = rows.filter((r) => !isSynced(r) && (draft[r.account.id] ?? '') !== (r.balance ?? ''));
  // Balances still to enter: every active account this month, or in a past month the ones that had a
  // balance the month before. Future months aren't nagged about.
  const unentered = new Set(
    rows
      .filter(
        (r) =>
          month <= thisMonth() &&
          !isSynced(r) &&
          !r.account.is_archived &&
          (draft[r.account.id] ?? '') === '' &&
          (month === thisMonth() || r.previous_balance != null),
      )
      .map((r) => r.account.id),
  );

  const save = useAppMutation(
    () =>
      api.saveBalances(
        month,
        changed.map((r) => {
          const v = draft[r.account.id];
          return { account_id: r.account.id, balance: v === '' || v == null ? null : v };
        }),
      ),
    'Balances saved',
  );
  const copyPrevious = useAppMutation(() => api.copyPreviousBalances(month), 'Copied last month’s balances');
  const updateAccount = useAppMutation(
    ({ id, ...body }: { id: number; is_archived: boolean }) => api.updateAccount(id, body),
  );
  const deleteAccount = useAppMutation((id: number) => api.deleteAccount(id), 'Account deleted');

  const previousNetWorth = rows.some((r) => r.previous_balance != null)
    ? rows.reduce((sum, r) => sum + (r.account.kind === 'asset' ? 1 : -1) * (r.previous_balance ?? 0), 0)
    : null;

  const cash = groupTotal(rows, CASH_SUBTYPES);
  const investments = groupTotal(rows, INVESTMENT_SUBTYPES);

  const missing = rows.filter((r) => r.balance == null && r.previous_balance != null && !isSynced(r)).length;

  const accountRow = (r: BalanceRow, kind: AccountKind) => {
    const value = draft[r.account.id] ?? '';
    const current = value === '' ? null : value;
    const change = current != null && r.previous_balance != null ? current - r.previous_balance : null;
    return (
      <Table.Tr key={r.account.id} opacity={r.account.is_archived ? 0.6 : 1}>
        <Table.Td>
          <Group gap={6} wrap="nowrap">
            <Text size="sm" fw={500}>
              {r.account.name}
            </Text>
            {r.account.sync_from_holdings && (
              <Tooltip label="Value comes from this account's holdings on the Stocks tab. Click to see them.">
                <Badge
                  component={Link}
                  to={`/stocks?account=${r.account.id}`}
                  size="xs"
                  variant="light"
                  leftSection={<IconLink size={10} />}
                  style={{ cursor: 'pointer' }}
                >
                  From Stocks
                </Badge>
              </Tooltip>
            )}
            {r.account.is_archived && (
              <Badge size="xs" variant="light" color="gray">
                Archived
              </Badge>
            )}
          </Group>
          <Text size="xs" c="dimmed">
            {subtypeLabel(r.account.subtype)}
          </Text>
        </Table.Td>
        <Table.Td ta="right">
          {isSynced(r) ? (
            <Text size="sm" className="num" fw={500}>
              {money(r.balance)}
            </Text>
          ) : (
            <NumberInput
              size="xs"
              w={150}
              ml="auto"
              prefix="$"
              decimalScale={2}
              thousandSeparator=","
              min={0}
              placeholder={unentered.has(r.account.id) ? 'Enter balance' : '—'}
              hideControls
              value={value}
              onChange={(v) => setDraft((d) => ({ ...d, [r.account.id]: v === '' ? '' : Number(v) }))}
              aria-label={`${r.account.name} balance`}
              // Compact height, but the same text size and weight as the read-only (synced) balances.
              styles={{ input: { textAlign: 'right', fontSize: 'var(--mantine-font-size-sm)', fontWeight: 500 } }}
              className={unentered.has(r.account.id) ? 'num needs-entry' : 'num'}
            />
          )}
        </Table.Td>
        <Table.Td ta="right">
          <Group justify="flex-end">
            {/* Paying down debt is good, so liabilities count "down" as the good direction. */}
            <Delta value={change} goodWhen={kind === 'asset' ? 'up' : 'down'} />
          </Group>
        </Table.Td>
        <Table.Td>
          <Menu position="bottom-end">
            <Menu.Target>
              <ActionIcon variant="subtle" color="gray" aria-label="Account actions">
                <IconDots size={16} />
              </ActionIcon>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item leftSection={<IconPencil size={14} />} onClick={() => setEditing({ account: r.account })}>
                Edit account
              </Menu.Item>
              <Menu.Item
                leftSection={r.account.is_archived ? <IconArchiveOff size={14} /> : <IconArchive size={14} />}
                onClick={() => updateAccount.mutate({ id: r.account.id, is_archived: !r.account.is_archived })}
              >
                {r.account.is_archived ? 'Unarchive' : 'Archive (closed account)'}
              </Menu.Item>
              <Menu.Item
                color="red"
                leftSection={<IconTrash size={14} />}
                onClick={() =>
                  confirmDelete(
                    `"${r.account.name}"`,
                    () => deleteAccount.mutate(r.account.id),
                    'This deletes the account and every monthly balance recorded for it. To keep history for a closed account, archive it instead.',
                  )
                }
              >
                Delete
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
        </Table.Td>
      </Table.Tr>
    );
  };

  const section = (kind: AccountKind) => {
    const group = rows.filter((r) => r.account.kind === kind);
    if (group.length === 0) return null;
    const total = group.reduce((s, r) => s + (r.balance ?? 0), 0);
    const subgroups =
      kind === 'asset'
        ? ASSET_GROUPS.map((g) => ({ ...g, rows: group.filter((r) => g.has(r.account.subtype)) })).filter((g) => g.rows.length)
        : [{ key: 'all', label: null, rows: group }];
    return (
      <>
        <Table.Tr>
          <Table.Th colSpan={4} bg="var(--mantine-color-default-hover)">
            {kind === 'asset' ? 'Assets' : 'Liabilities'}
          </Table.Th>
        </Table.Tr>
        {subgroups.map((g) => (
          <Fragment key={g.key}>
            {g.label && (
              <Table.Tr>
                <Table.Td pt="sm">
                  <Text className="label-sm">{g.label}</Text>
                </Table.Td>
                <Table.Td ta="right" pt="sm">
                  <Text size="xs" c="dimmed" className="num">
                    {g.rows.some((r) => r.balance != null) ? money(g.rows.reduce((s, r) => s + (r.balance ?? 0), 0)) : ''}
                  </Text>
                </Table.Td>
                <Table.Td colSpan={2} />
              </Table.Tr>
            )}
            {g.rows.map((r) => accountRow(r, kind))}
          </Fragment>
        ))}
        <Table.Tr>
          <Table.Td fw={600}>Total {kind === 'asset' ? 'assets' : 'liabilities'}</Table.Td>
          <Table.Td ta="right" className="num" fw={600}>
            {money(total)}
          </Table.Td>
          <Table.Td colSpan={2} />
        </Table.Tr>
      </>
    );
  };

  const trendData = trend.map((p) => ({
    month: monthShort(p.month),
    'Net worth': p.net_worth,
    Assets: p.assets,
    Liabilities: p.liabilities,
  }));
  const recordedMonths = trend.filter((p) => p.net_worth != null).length;

  return (
    <>
      <PageHeader
        title="Balance Sheet"
        description="Month-end balances for every account and debt."
        actions={
          <>
            <MonthSwitcher value={month} onChange={setMonth} />
            <Button leftSection={<IconPlus size={16} />} onClick={() => setEditing({ account: null })}>
              Add account
            </Button>
          </>
        }
      />

      <SimpleGrid cols={{ base: 1, sm: 2, lg: 5 }} mb="xl">
        <StatCard label="Total assets" value={money(sheet?.total_assets)} />
        <StatCard label="Total liabilities" value={money(sheet?.total_liabilities)} />
        <StatCard
          label="Net worth"
          value={money(sheet?.net_worth)}
          footer={
            sheet && previousNetWorth != null ? (
              <Delta value={sheet.net_worth - previousNetWorth} suffix="vs. last month" />
            ) : (
              'Assets minus liabilities'
            )
          }
        />
        <StatCard
          label="Cash total"
          value={money(cash.total)}
          footer={
            cash.change != null ? (
              <Delta value={cash.change} suffix="vs. last month" />
            ) : (
              'Checking and savings'
            )
          }
        />
        <StatCard
          label="Investment total"
          value={money(investments.total)}
          footer={
            investments.change != null ? (
              <Delta
                value={investments.change}
                suffix={`${investments.pct != null ? `(${signedPercent(investments.pct)}) ` : ''}vs. last month`}
              />
            ) : (
              'No balances for last month yet'
            )
          }
        />
      </SimpleGrid>

      <Stack gap="lg">
        <SectionCard
          title={`Balances · ${monthLabel(month)}`}
          actions={
            rows.length > 0 && (
              <>
                {unentered.size > 0 && (
                  <Group gap={4} wrap="nowrap" mr="xs">
                    <IconAlertCircle size={14} color="var(--primary)" aria-hidden />
                    <Text size="xs" c="dimmed">
                      {unentered.size} {unentered.size === 1 ? 'balance' : 'balances'} not entered for {monthLabel(month)}
                    </Text>
                  </Group>
                )}
                {missing > 0 && (
                  <Button
                    size="xs"
                    variant="light"
                    leftSection={<IconCopy size={14} />}
                    loading={copyPrevious.isPending}
                    onClick={() => copyPrevious.mutate(undefined)}
                  >
                    Copy {missing} from last month
                  </Button>
                )}
                <Button
                  size="xs"
                  leftSection={<IconDeviceFloppy size={14} />}
                  disabled={changed.length === 0}
                  loading={save.isPending}
                  onClick={() => save.mutate(undefined)}
                >
                  Save{changed.length > 0 ? ` (${changed.length})` : ''}
                </Button>
              </>
            )
          }
        >
          {rows.length === 0 ? (
            <EmptyState
              message="Add your bank accounts, investments, and debts to start tracking net worth."
              action={
                <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setEditing({ account: null })}>
                  Add account
                </Button>
              }
            />
          ) : (
            <Table.ScrollContainer minWidth={520}>
              <Table verticalSpacing={6}>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Account</Table.Th>
                    <Table.Th ta="right" w={170}>
                      {monthLabel(month)}
                    </Table.Th>
                    <Table.Th ta="right" w={190}>
                      Change vs. last month
                    </Table.Th>
                    <Table.Th w={40} />
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {section('asset')}
                  {section('liability')}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          )}
        </SectionCard>

        <SectionCard
          title="Net worth over time"
          actions={
            <SegmentedControl
              size="xs"
              value={trendView}
              onChange={(v) => setTrendView(v as 'net' | 'split')}
              data={[
                { value: 'net', label: 'Net worth' },
                { value: 'split', label: 'Assets & liabilities' },
              ]}
            />
          }
        >
          {recordedMonths < 2 ? (
            <EmptyState message="Record balances for at least two months to see the trend." />
          ) : trendView === 'net' ? (
            <AreaChart
              h={260}
              data={trendData}
              dataKey="month"
              series={[{ name: 'Net worth', color: 'var(--trend)' }]}
              curveType="linear"
              connectNulls
              strokeWidth={2}
              fillOpacity={0.2}
              withDots={false}
              valueFormatter={(v) => money(v)}
              yAxisProps={{
                tickFormatter: (v: number) => moneyCompact(v),
                width: 70,
                ...fittedAxis(trend.flatMap((p) => (p.net_worth == null ? [] : [p.net_worth]))),
              }}
              gridAxis="x"
              strokeDasharray="0"
            />
          ) : (
            <LineChart
              h={260}
              data={trendData}
              dataKey="month"
              series={[
                { name: 'Assets', color: 'var(--series-1)' },
                { name: 'Liabilities', color: 'var(--series-2)' },
              ]}
              curveType="linear"
              connectNulls
              strokeWidth={2}
              withDots={false}
              withLegend
              valueFormatter={(v) => money(v)}
              yAxisProps={{ tickFormatter: (v: number) => moneyCompact(v), width: 70 }}
              gridAxis="x"
              strokeDasharray="0"
            />
          )}
          {recordedMonths >= 2 && trend.some((p) => p.net_worth == null) && (
            <Text size="xs" c="dimmed" mt="xs">
              Months with no balances recorded are bridged with a straight line.
            </Text>
          )}
        </SectionCard>
      </Stack>

      <Modal opened={editing !== null} onClose={() => setEditing(null)} title={editing?.account ? 'Edit account' : 'Add account'}>
        {editing && <AccountForm key={editing.account?.id ?? 'new'} account={editing.account} onDone={() => setEditing(null)} />}
      </Modal>
    </>
  );
}

function AccountForm({ account, onDone }: { account: Account | null; onDone: () => void }) {
  const form = useForm({
    initialValues: {
      name: account?.name ?? '',
      kind: account?.kind ?? ('asset' as AccountKind),
      subtype: account?.subtype ?? 'checking',
      sync_from_holdings: account?.sync_from_holdings ?? false,
      notes: account?.notes ?? '',
    },
    validate: { name: (v) => (v.trim() ? null : 'Required') },
  });
  const save = useAppMutation(
    (body: AccountInput) => (account ? api.updateAccount(account.id, body) : api.createAccount(body)),
    account ? 'Account updated' : 'Account added',
  );

  const subtypes = form.values.kind === 'asset' ? ASSET_SUBTYPES : LIABILITY_SUBTYPES;

  return (
    <form
      onSubmit={form.onSubmit((v) =>
        save.mutate(
          {
            ...v,
            name: v.name.trim(),
            sync_from_holdings: v.kind === 'asset' && v.sync_from_holdings,
            notes: v.notes.trim() || null,
          },
          { onSuccess: onDone },
        ),
      )}
    >
      <Stack>
        <SegmentedControl
          data={[
            { value: 'asset', label: 'Asset (something you own)' },
            { value: 'liability', label: 'Liability (debt)' },
          ]}
          value={form.values.kind}
          onChange={(k) => {
            form.setFieldValue('kind', k as AccountKind);
            form.setFieldValue('subtype', k === 'asset' ? 'checking' : 'mortgage');
          }}
        />
        <TextInput label="Name" placeholder="e.g. Chase Joint Checking" data-autofocus {...form.getInputProps('name')} />
        <Select
          label="Type"
          data={Object.entries(subtypes).map(([value, label]) => ({ value, label }))}
          allowDeselect={false}
          {...form.getInputProps('subtype')}
        />
        {form.values.kind === 'asset' && (
          <Switch
            label="Get balance from Stocks tab"
            description="Value this account using the holdings you link to it on the Stocks tab, updated with daily prices."
            {...form.getInputProps('sync_from_holdings', { type: 'checkbox' })}
          />
        )}
        <Textarea label="Notes" autosize minRows={1} {...form.getInputProps('notes')} />
        <Group justify="flex-end">
          <Button type="submit" loading={save.isPending}>
            Save
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
