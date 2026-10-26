import { AreaChart } from '@mantine/charts';
import {
  ActionIcon,
  Badge,
  Button,
  Grid,
  Group,
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
  Tooltip,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import {
  IconAlertTriangle,
  IconCash,
  IconCheck,
  IconChevronDown,
  IconChevronRight,
  IconPencil,
  IconPlus,
  IconRefresh,
  IconTrash,
} from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { api } from '../api';
import {
  confirmDelete,
  Delta,
  EmptyState,
  PageHeader,
  SectionCard,
  SortableTh,
  StatCard,
  useAppMutation,
  type SortDir,
} from '../components/common';
import { dateLabel, money, moneyCompact, percent, quantity, signedPercent } from '../format';
import type { AssetType, Holding, HoldingInput, PortfolioPoint } from '../types';

const ASSET_LABELS: Record<AssetType, string> = { stock: 'Stock', etf: 'ETF', crypto: 'Crypto', cash: 'Cash' };
const RANGES = ['1M', '3M', '6M', 'YTD', '1Y'] as const;
type Range = (typeof RANGES)[number];
const RANGE_DAYS: Record<Exclude<Range, 'YTD'>, number> = { '1M': 30, '3M': 91, '6M': 182, '1Y': 365 };
const RANGE_LABELS: Record<Range, string> = {
  '1M': 'past month',
  '3M': 'past 3 months',
  '6M': 'past 6 months',
  YTD: 'year to date',
  '1Y': 'past year',
};

// Year to date runs from last year's final close (Dec 31), so the history opens on that day.
const rangeStart = (range: Range) =>
  range === 'YTD' ? dayjs().startOf('year').subtract(1, 'day').startOf('day') : dayjs().subtract(RANGE_DAYS[range], 'day').startOf('day');
const rangeDays = (range: Range) => Math.max(1, dayjs().startOf('day').diff(rangeStart(range), 'day'));

/** Change from the first point to the last; if history doesn't reach back to the range start, say since when. */
function performance(history: PortfolioPoint[], range: Range) {
  const first = history[0];
  const last = history[history.length - 1];
  const change = history.length >= 2 ? last.value - first.value : null;
  return {
    change,
    pct: change != null && first.value > 0 ? change / first.value : null,
    label: first && dayjs(first.date).isAfter(rangeStart(range), 'day') ? `since ${dateLabel(first.date)}` : RANGE_LABELS[range],
  };
}

type Editing = { holding: Holding | null } | null;

const UNASSIGNED = 'unassigned';

type SortKey = 'ticker' | 'value' | 'allocation' | 'gain';
type Sort = { key: SortKey; dir: SortDir };
const DEFAULT_SORT: Sort = { key: 'ticker', dir: 'asc' };
const SORT_STORAGE_KEY = 'moneysage.holdings-sort';

// The chosen sort is a per-browser convenience; storage can be unavailable, so fall back quietly.
function loadSort(): Sort {
  try {
    const saved = JSON.parse(localStorage.getItem(SORT_STORAGE_KEY) ?? 'null');
    if (saved?.key in COMPARE && (saved.dir === 'asc' || saved.dir === 'desc')) return saved;
  } catch {
    /* ignore */
  }
  return DEFAULT_SORT;
}

function saveSort(sort: Sort) {
  try {
    localStorage.setItem(SORT_STORAGE_KEY, JSON.stringify(sort));
  } catch {
    /* ignore */
  }
}

export default function StocksPage() {
  const [range, setRange] = useState<Range>('3M');
  const [editing, setEditing] = useState<Editing>(null);
  const [sort, setSort] = useState<Sort>(loadSort);

  const { data: holdings = [], isLoading } = useQuery({ queryKey: ['holdings'], queryFn: api.holdings });
  const { data: summary } = useQuery({ queryKey: ['portfolio-summary'], queryFn: api.portfolioSummary });
  const { data: accounts = [] } = useQuery({ queryKey: ['accounts'], queryFn: () => api.accounts() });
  // ?account=<id> (or 'unassigned') narrows the holdings table to one account. Set by the selector above
  // the table and by the "From Investments" link on the Balance Sheet. Without it, all accounts show combined.
  const [params, setParams] = useSearchParams();
  const accountParam = params.get('account');
  const accountFilter = accountParam == null ? null : accountParam === UNASSIGNED ? UNASSIGNED : Number(accountParam);
  const filterName =
    accountFilter === UNASSIGNED ? 'Unassigned' : accounts.find((a) => a.id === accountFilter)?.name ?? 'this account';
  const shown =
    accountFilter == null
      ? holdings
      : holdings.filter((h) => (accountFilter === UNASSIGNED ? h.account_id == null : h.account_id === accountFilter));
  // Accounts that hold something, plus the selected one even if it's empty (e.g. linked from the Balance Sheet).
  const accountOptions = [
    { value: '', label: 'All accounts' },
    ...accounts
      .filter((a) => a.id === accountFilter || holdings.some((h) => h.account_id === a.id))
      .map((a) => ({ value: String(a.id), label: a.name })),
    ...(holdings.some((h) => h.account_id == null) ? [{ value: UNASSIGNED, label: 'Unassigned' }] : []),
  ];
  const { data: history = [] } = useQuery({
    queryKey: ['portfolio-history', range],
    queryFn: () => api.portfolioHistory(rangeDays(range)),
  });
  // The YTD card always needs this range; it shares the cache with the chart when YTD is selected.
  const { data: ytdHistory = [] } = useQuery({
    queryKey: ['portfolio-history', 'YTD'],
    queryFn: () => api.portfolioHistory(rangeDays('YTD')),
  });
  const refresh = useAppMutation(() => api.refreshPrices(), 'Prices refreshed');
  const remove = useAppMutation((id: number) => api.deleteHolding(id), 'Holding deleted');

  const total = summary?.total_value ?? 0;
  const allocation = (Object.keys(ASSET_LABELS) as AssetType[])
    .map((type) => ({
      type,
      value: holdings.filter((h) => h.asset_type === type).reduce((s, h) => s + (h.market_value ?? 0), 0),
    }))
    .filter((a) => a.value > 0);
  const run = summary?.last_refresh;

  // Clicking the active column flips it; a new column starts A→Z for ticker, largest first for amounts.
  const sortBy = (key: SortKey) => {
    const dir: SortDir = sort.key === key ? (sort.dir === 'asc' ? 'desc' : 'asc') : key === 'ticker' ? 'asc' : 'desc';
    setSort({ key, dir });
    saveSort({ key, dir });
  };
  const header = (key: SortKey, label: string, align?: 'right', className?: string) => (
    <SortableTh
      label={label}
      align={align}
      className={className}
      active={sort.key === key}
      dir={sort.dir}
      onSort={() => sortBy(key)}
    />
  );
  // Allocation is against everything listed, so the rows add up to 100%.
  const holdingsTotal = shown.reduce((s, h) => s + (h.market_value ?? 0), 0);
  // Footer totals: the portfolio summary, or the filtered account's own sums.
  const totals =
    accountFilter == null
      ? { cost: summary?.total_cost, value: summary?.total_value, day: summary?.day_change, gain: summary?.total_gain }
      : {
          cost: sumOf(shown.map((h) => h.cost_basis)),
          value: sumOf(shown.map((h) => h.market_value)),
          day: sumOf(shown.map((h) => h.day_change)),
          gain: sumOf(shown.map((h) => h.gain)),
        };
  const chartData = history.map((p) => ({ date: dayjs(p.date).format('MMM D'), Value: p.value }));
  const rangePerf = performance(history, range);
  const ytd = performance(ytdHistory, 'YTD');

  return (
    <>
      <PageHeader
        title="Investments"
        description="Stocks, ETFs, crypto, and cash held in your accounts. Prices refresh automatically every evening."
        actions={
          <>
            {run?.finished_at && (
              <Tooltip
                label={run.status === 'success' ? 'All prices updated' : run.message ?? `Refresh ${run.status}`}
                multiline
                maw={320}
              >
                <Group gap={4} wrap="nowrap" mr="xs">
                  {run.status === 'success' ? (
                    <IconCheck size={14} className="delta-up" aria-label="Prices updated" />
                  ) : (
                    <IconAlertTriangle size={14} className="delta-down" aria-label="Some prices failed to update" />
                  )}
                  <Text size="xs" c="dimmed">
                    {run.status === 'success' ? 'Prices updated' : 'Price refresh had problems'}{' '}
                    {dayjs(run.finished_at).format('MMM D, h:mm A')}
                  </Text>
                </Group>
              </Tooltip>
            )}
            <Button
              variant="default"
              leftSection={<IconRefresh size={16} />}
              loading={refresh.isPending}
              onClick={() => refresh.mutate(undefined)}
              disabled={!holdings.some((h) => h.asset_type !== 'cash')}
            >
              Refresh prices
            </Button>
            <Button leftSection={<IconPlus size={16} />} onClick={() => setEditing({ holding: null })}>
              Add holding
            </Button>
          </>
        }
      />

      <SimpleGrid cols={{ base: 1, sm: 3 }} mb="xl">
        <StatCard
          label="Portfolio value"
          value={money(summary?.total_value)}
          footer={summary && holdings.length > 0 && <Delta value={summary.day_change} suffix="today" />}
        />
        <StatCard
          label="Total gain / loss"
          value={
            summary?.total_gain == null ? (
              '—'
            ) : (
              <span className={summary.total_gain < 0 ? 'delta-down' : 'delta-up'}>
                {summary.total_gain < 0 ? '−' : '+'}
                {money(Math.abs(summary.total_gain))}
              </span>
            )
          }
          footer={
            summary?.total_cost
              ? `${percent((summary.total_gain ?? 0) / summary.total_cost)} on ${money(summary.total_cost)} invested`
              : 'Add what you paid per share to track gains'
          }
        />
        <StatCard
          label="YTD performance"
          value={
            ytd.change == null ? (
              '—'
            ) : (
              <span className={ytd.change < 0 ? 'delta-down' : 'delta-up'}>
                {ytd.change < 0 ? '−' : '+'}
                {money(Math.abs(ytd.change))}
              </span>
            )
          }
          footer={ytd.pct != null ? `${signedPercent(ytd.pct)} ${ytd.label}` : 'Not enough price history yet'}
        />
      </SimpleGrid>

      <Stack gap="lg">
        <SectionCard
          title="Holdings"
          actions={
            holdings.length > 0 && (
              <Select
                size="xs"
                w={{ base: '100%', xs: 200 }}
                aria-label="Show holdings for"
                data={accountOptions}
                value={accountParam ?? ''}
                onChange={(v) => setParams(v ? { account: v } : {})}
                allowDeselect={false}
                comboboxProps={{ withinPortal: true }}
              />
            )
          }
        >
          {isLoading ? null : accountFilter != null && shown.length === 0 ? (
            <EmptyState message={`No holdings are linked to ${filterName} yet.`} />
          ) : holdings.length === 0 ? (
            <EmptyState
              message="Add the stocks, ETFs, crypto, and cash you own."
              action={
                <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setEditing({ holding: null })}>
                  Add holding
                </Button>
              }
            />
          ) : (
            <Table.ScrollContainer minWidth={900} className="phone-fit">
              <Table highlightOnHover verticalSpacing="xs">
                <Table.Thead>
                  <Table.Tr>
                    {header('ticker', 'Ticker')}
                    <Table.Th className="hide-xs">Account</Table.Th>
                    <Table.Th ta="right" className="hide-xs">
                      Quantity
                    </Table.Th>
                    <Table.Th ta="right" className="hide-xs">
                      Avg cost
                    </Table.Th>
                    <Table.Th ta="right" className="hide-xs">
                      Price
                    </Table.Th>
                    {header('value', 'Value', 'right')}
                    {header('allocation', 'Allocation', 'right', 'hide-xs')}
                    <Table.Th ta="right" className="hide-xs">
                      Today
                    </Table.Th>
                    {header('gain', 'Gain / loss', 'right', 'hide-xs')}
                    <Table.Th w={70} />
                  </Table.Tr>
                </Table.Thead>
                <HoldingsBody
                  holdings={shown}
                  sort={sort}
                  total={holdingsTotal}
                  onEdit={(h) => setEditing({ holding: h })}
                  onDelete={(h) =>
                    confirmDelete(
                      h.asset_type === 'cash'
                        ? `cash${h.account_name ? ` in ${h.account_name}` : ''}`
                        : `${h.ticker} holding${h.account_name ? ` in ${h.account_name}` : ''}`,
                      () => remove.mutate(h.id),
                    )
                  }
                />
                <Table.Tfoot>
                  <Table.Tr>
                    <Table.Th>Total</Table.Th>
                    <Table.Th colSpan={2} className="hide-xs" />
                    <Table.Th ta="right" className="num hide-xs">
                      {money(totals.cost)}
                    </Table.Th>
                    <Table.Th className="hide-xs" />
                    <Table.Th ta="right" className="num">
                      {money(totals.value)}
                    </Table.Th>
                    <Table.Th ta="right" className="num hide-xs">
                      {holdingsTotal > 0 ? '100%' : '—'}
                    </Table.Th>
                    <Table.Th ta="right" className="hide-xs">
                      <Group justify="flex-end">
                        <Delta value={totals.day} />
                      </Group>
                    </Table.Th>
                    <Table.Th ta="right" className="hide-xs">
                      <Group justify="flex-end">
                        <Delta value={totals.gain} />
                      </Group>
                    </Table.Th>
                    <Table.Th />
                  </Table.Tr>
                </Table.Tfoot>
              </Table>
            </Table.ScrollContainer>
          )}
        </SectionCard>

        {holdings.length > 0 && (
          <Grid gutter="lg">
            <Grid.Col span={{ base: 12, lg: 8 }}>
              <SectionCard
                title="Portfolio value"
                actions={
                  <SegmentedControl
                    size="xs"
                    value={range}
                    onChange={(v) => setRange(v as Range)}
                    data={[...RANGES]}
                  />
                }
              >
                {chartData.length < 2 ? (
                  <EmptyState message="Not enough price history yet." />
                ) : (
                  <>
                    <Group gap="xs" mb="sm" align="baseline">
                      <Delta
                        value={rangePerf.change}
                        size="md"
                        suffix={rangePerf.pct != null ? `(${signedPercent(rangePerf.pct)})` : undefined}
                      />
                      <Text size="sm" c="dimmed">
                        {rangePerf.label}
                      </Text>
                    </Group>
                    <AreaChart
                      h={260}
                      data={chartData}
                      dataKey="date"
                      series={[{ name: 'Value', color: 'var(--trend)' }]}
                      curveType="linear"
                      strokeWidth={2}
                      fillOpacity={0.2}
                      withDots={false}
                      valueFormatter={(v) => money(v)}
                      yAxisProps={{ tickFormatter: (v: number) => moneyCompact(v), width: 70, domain: ['auto', 'auto'] }}
                      xAxisProps={{ minTickGap: 32 }}
                      gridAxis="x"
                      strokeDasharray="0"
                    />
                    <Text size="xs" c="dimmed" mt="xs">
                      Shows what your current holdings would have been worth on each day.
                    </Text>
                  </>
                )}
              </SectionCard>
            </Grid.Col>
            <Grid.Col span={{ base: 12, lg: 4 }}>
              <SectionCard title="Allocation">
                <Stack gap="lg">
                  {allocation.map((a) => (
                    <div key={a.type}>
                      <Group justify="space-between" mb={4}>
                        <Text size="sm">{ASSET_LABELS[a.type]}</Text>
                        <Text size="sm" className="num">
                          {money(a.value)} · {total ? percent(a.value / total) : '—'}
                        </Text>
                      </Group>
                      <Progress value={total ? (a.value / total) * 100 : 0} color="var(--trend)" size="md" />
                    </div>
                  ))}
                </Stack>
              </SectionCard>
            </Grid.Col>
          </Grid>
        )}
      </Stack>

      <Modal opened={editing !== null} onClose={() => setEditing(null)} title={editing?.holding ? 'Edit holding' : 'Add holding'}>
        {editing && <HoldingForm key={editing.holding?.id ?? 'new'} holding={editing.holding} onDone={() => setEditing(null)} />}
      </Modal>
    </>
  );
}

/** One ticker's holdings across accounts, with combined figures for the summary row. */
interface Position {
  key: string;
  ticker: string;
  asset_type: AssetType;
  lots: Holding[];
  quantity: number;
  price: number | null;
  price_date: string | null;
  market_value: number | null;
  day_change: number | null;
  /** Share-weighted average over the lots that have a cost entered. */
  cost_per_unit: number | null;
  cost_basis: number | null;
  gain: number | null;
  lotsWithCost: number;
}

const sumOf = (values: (number | null)[]) => {
  const known = values.filter((v): v is number => v != null);
  return known.length ? known.reduce((s, v) => s + v, 0) : null;
};

/** Group by ticker (and type, so cash never merges with the stock that trades as CASH). */
function groupPositions(holdings: Holding[]): Position[] {
  const groups = new Map<string, Holding[]>();
  for (const h of holdings) {
    const key = `${h.asset_type}:${h.ticker}`;
    groups.set(key, [...(groups.get(key) ?? []), h]);
  }
  return [...groups].map(([key, lots]) => {
    const sorted = [...lots].sort((a, b) => (a.account_name ?? '￿').localeCompare(b.account_name ?? '￿'));
    const withCost = lots.filter((l) => l.cost_basis != null);
    const costBasis = sumOf(withCost.map((l) => l.cost_basis));
    const costQty = withCost.reduce((s, l) => s + l.quantity, 0);
    return {
      key,
      ticker: lots[0].ticker,
      asset_type: lots[0].asset_type,
      lots: sorted,
      quantity: lots.reduce((s, l) => s + l.quantity, 0),
      price: lots[0].price,
      price_date: lots[0].price_date,
      market_value: sumOf(lots.map((l) => l.market_value)),
      day_change: sumOf(lots.map((l) => l.day_change)),
      cost_per_unit: costBasis != null && costQty > 0 ? costBasis / costQty : null,
      cost_basis: costBasis,
      gain: sumOf(withCost.map((l) => l.gain)),
      lotsWithCost: withCost.length,
    };
  });
}

const positionLabel = (p: Position) => (p.asset_type === 'cash' ? 'Cash' : p.ticker);
const byTicker = (a: Position, b: Position) => positionLabel(a).localeCompare(positionLabel(b));
const byAmount = (f: (p: Position) => number | null) => (a: Position, b: Position) => (f(a) ?? 0) - (f(b) ?? 0) || byTicker(a, b);
const COMPARE: Record<SortKey, (a: Position, b: Position) => number> = {
  ticker: byTicker,
  value: byAmount((p) => p.market_value),
  // Allocation is value over one shared total, so it orders the same as value.
  allocation: byAmount((p) => p.market_value),
  gain: byAmount((p) => p.gain),
};
// Rows with no figure for the sorted column (no price yet, no cost entered, cash for gain) go last either way.
const SORT_VALUE: Record<SortKey, ((p: Position) => number | null) | null> = {
  ticker: null,
  value: (p) => p.market_value,
  allocation: (p) => p.market_value,
  gain: (p) => p.gain,
};

function sortPositions(positions: Position[], { key, dir }: Sort) {
  const value = SORT_VALUE[key];
  const known = value ? positions.filter((p) => value(p) != null) : positions;
  const missing = value ? positions.filter((p) => value(p) == null).sort(byTicker) : [];
  const sorted = [...known].sort(COMPARE[key]);
  return [...(dir === 'asc' ? sorted : sorted.reverse()), ...missing];
}

type Figures = Pick<Holding, 'asset_type' | 'quantity' | 'price' | 'price_date' | 'market_value' | 'day_change' | 'cost_per_unit' | 'cost_basis' | 'gain'>;

/** Quantity through gain/loss: shared by single holdings, combined rows, and per-account rows. */
function FigureCells({ f, total, costNote }: { f: Figures; total: number; costNote?: string }) {
  const cash = f.asset_type === 'cash';
  const share = f.market_value != null && total > 0 ? f.market_value / total : null;
  return (
    <>
      <Table.Td ta="right" className="num hide-xs">
        {cash ? '—' : quantity(f.quantity)}
      </Table.Td>
      <Table.Td ta="right" className="num hide-xs">
        {money(f.cost_per_unit)}
        {f.cost_basis != null && costNote && (
          <Text size="xs" c="dimmed">
            {costNote}
          </Text>
        )}
      </Table.Td>
      <Table.Td ta="right" className="num hide-xs">
        {money(f.price)}
        {f.price_date && (
          <Text size="xs" c="dimmed">
            {dateLabel(f.price_date)}
          </Text>
        )}
      </Table.Td>
      <Table.Td ta="right" className="num" fw={500}>
        {money(f.market_value)}
        {/* Phones hide the allocation and gain columns; both sit under the value instead. */}
        <Stack gap={0} align="flex-end" className="show-xs">
          {f.gain != null && <Delta value={f.gain} size="xs" />}
          {share != null && (
            <Text size="xs" c="dimmed" fw={400}>
              {percent(share)}
            </Text>
          )}
        </Stack>
      </Table.Td>
      <Table.Td ta="right" className="num hide-xs">
        {share == null ? (
          '—'
        ) : (
          <>
            {percent(share)}
            <Progress value={share * 100} size={3} w={56} ml="auto" mt={4} color="var(--trend)" aria-hidden />
          </>
        )}
      </Table.Td>
      <Table.Td ta="right" className="hide-xs">
        <Group justify="flex-end">{cash ? <Text size="sm">—</Text> : <Delta value={f.day_change} />}</Group>
      </Table.Td>
      <Table.Td ta="right" className="hide-xs">
        <Group justify="flex-end">{f.gain == null ? <Text size="sm">—</Text> : <Delta value={f.gain} />}</Group>
      </Table.Td>
    </>
  );
}

function TickerLabel({ ticker, asset_type }: { ticker: string; asset_type: AssetType }) {
  const cash = asset_type === 'cash';
  return (
    <Group gap={6} wrap="nowrap">
      {cash && <IconCash size={16} stroke={1.6} aria-hidden />}
      <Text fw={600} size="sm">
        {cash ? 'Cash' : ticker}
      </Text>
      {!cash && (
        <Badge size="xs" variant="light" color="gray" className="hide-xs">
          {ASSET_LABELS[asset_type]}
        </Badge>
      )}
    </Group>
  );
}

function HoldingsBody({
  holdings,
  sort,
  total,
  onEdit,
  onDelete,
}: {
  holdings: Holding[];
  sort: Sort;
  total: number;
  onEdit: (h: Holding) => void;
  onDelete: (h: Holding) => void;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const toggle = (key: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const actions = (h: Holding) => (
    <Table.Td>
      <Group gap={4} wrap="nowrap" justify="flex-end">
        <ActionIcon variant="subtle" color="gray" aria-label="Edit" onClick={() => onEdit(h)}>
          <IconPencil size={16} />
        </ActionIcon>
        <ActionIcon variant="subtle" color="red" aria-label="Delete" onClick={() => onDelete(h)}>
          <IconTrash size={16} />
        </ActionIcon>
      </Group>
    </Table.Td>
  );
  const notes = (h: Holding) =>
    h.notes && (
      <Text size="xs" c="dimmed" lineClamp={1}>
        {h.notes}
      </Text>
    );
  const account = (h: Holding) => (
    <Text size="sm" c={h.account_name ? undefined : 'dimmed'}>
      {h.account_name ?? 'Unassigned'}
    </Text>
  );
  // Phones hide the account and quantity columns; this line under the ticker stands in for them.
  const phoneLine = (text: string) => (
    <Text size="xs" c="dimmed" className="show-xs num">
      {text}
    </Text>
  );
  const holdingLine = (h: Holding) =>
    phoneLine(
      [h.asset_type === 'cash' ? null : `${quantity(h.quantity)} @ ${money(h.price)}`, h.account_name ?? 'Unassigned']
        .filter(Boolean)
        .join(' · '),
    );

  return (
    <Table.Tbody>
      {sortPositions(groupPositions(holdings), sort).flatMap((p) => {
        if (p.lots.length === 1) {
          const h = p.lots[0];
          return [
            <Table.Tr key={p.key}>
              <Table.Td>
                <TickerLabel ticker={h.ticker} asset_type={h.asset_type} />
                {holdingLine(h)}
                {notes(h)}
              </Table.Td>
              <Table.Td className="hide-xs">{account(h)}</Table.Td>
              <FigureCells f={h} total={total} />
              {actions(h)}
            </Table.Tr>,
          ];
        }

        const open = expanded.has(p.key);
        const label = p.asset_type === 'cash' ? 'cash' : p.ticker;
        return [
          <Table.Tr key={p.key} onClick={() => toggle(p.key)} style={{ cursor: 'pointer' }}>
            <Table.Td>
              <Group gap={4} wrap="nowrap">
                <ActionIcon
                  variant="subtle"
                  color="gray"
                  size="sm"
                  aria-expanded={open}
                  aria-label={`${open ? 'Hide' : 'Show'} ${label} by account`}
                  onClick={(e) => {
                    e.stopPropagation();
                    toggle(p.key);
                  }}
                >
                  {open ? <IconChevronDown size={14} /> : <IconChevronRight size={14} />}
                </ActionIcon>
                <TickerLabel ticker={p.ticker} asset_type={p.asset_type} />
              </Group>
              {phoneLine(`${p.lots.length} accounts`)}
            </Table.Td>
            <Table.Td className="hide-xs">
              <Text size="sm">Multiple</Text>
              <Text size="xs" c="dimmed">
                {p.lots.length} accounts
              </Text>
            </Table.Td>
            <FigureCells
              f={p}
              total={total}
              costNote={p.lotsWithCost < p.lots.length ? `${p.lotsWithCost} of ${p.lots.length} accounts` : undefined}
            />
            <Table.Td />
          </Table.Tr>,
          ...(open
            ? p.lots.map((h) => (
                <Table.Tr key={h.id} className="lot-row">
                  <Table.Td pl={{ base: 'md', xs: 42 }}>
                    {notes(h) || <Text size="xs" c="dimmed">{label === 'cash' ? 'Cash' : h.ticker}</Text>}
                    {holdingLine(h)}
                  </Table.Td>
                  <Table.Td className="hide-xs">{account(h)}</Table.Td>
                  <FigureCells f={h} total={total} />
                  {actions(h)}
                </Table.Tr>
              ))
            : []),
        ];
      })}
    </Table.Tbody>
  );
}

function HoldingForm({ holding, onDone }: { holding: Holding | null; onDone: () => void }) {
  const { data: accounts = [] } = useQuery({ queryKey: ['accounts'], queryFn: () => api.accounts() });
  const form = useForm({
    initialValues: {
      ticker: holding?.ticker ?? '',
      asset_type: holding?.asset_type ?? ('stock' as AssetType),
      quantity: holding?.quantity ?? ('' as number | ''),
      cost_per_unit: holding?.cost_per_unit ?? ('' as number | ''),
      account_id: holding?.account_id == null ? null : String(holding.account_id),
      notes: holding?.notes ?? '',
    },
    validate: {
      ticker: (v, values) => (values.asset_type === 'cash' || v.trim() ? null : 'Required'),
      quantity: (v, values) =>
        typeof v === 'number' && v > 0 ? null : values.asset_type === 'cash' ? 'Enter an amount' : 'Enter a quantity greater than 0',
    },
  });
  const save = useAppMutation(
    (body: HoldingInput) => (holding ? api.updateHolding(holding.id, body) : api.createHolding(body)),
    holding ? 'Holding updated' : 'Holding added',
  );

  const assetAccounts = accounts.filter((a) => a.kind === 'asset');
  const selected = assetAccounts.find((a) => String(a.id) === form.values.account_id);
  const isCrypto = form.values.asset_type === 'crypto';
  const isCash = form.values.asset_type === 'cash';

  return (
    <form
      onSubmit={form.onSubmit((v) =>
        save.mutate(
          {
            ticker: isCash ? '' : v.ticker.trim().toUpperCase(),
            asset_type: v.asset_type,
            quantity: v.quantity as number,
            cost_per_unit: isCash || v.cost_per_unit === '' ? null : v.cost_per_unit,
            account_id: v.account_id == null ? null : Number(v.account_id),
            notes: v.notes.trim() || null,
          },
          { onSuccess: onDone },
        ),
      )}
    >
      <Stack>
        <SegmentedControl
          data={Object.entries(ASSET_LABELS).map(([value, label]) => ({ value, label }))}
          {...form.getInputProps('asset_type')}
        />
        {isCash ? (
          <NumberInput
            label="Cash balance"
            description="Uninvested cash sitting in the account, including a money market sweep"
            prefix="$"
            decimalScale={2}
            thousandSeparator=","
            min={0}
            data-autofocus
            {...form.getInputProps('quantity')}
          />
        ) : (
          <>
            <TextInput
              label="Ticker"
              placeholder={isCrypto ? 'BTC or ETH' : 'e.g. AAPL or VOO'}
              description={isCrypto ? 'Saved as BTC-USD / ETH-USD for pricing' : undefined}
              data-autofocus
              styles={{ input: { textTransform: 'uppercase' } }}
              {...form.getInputProps('ticker')}
            />
            <Group grow align="flex-start">
              <NumberInput
                label={isCrypto ? 'Coins' : 'Shares'}
                decimalScale={8}
                thousandSeparator=","
                min={0}
                {...form.getInputProps('quantity')}
              />
              <NumberInput
                label={isCrypto ? 'Cost per coin' : 'Cost per share'}
                description="Optional: your average price paid"
                prefix="$"
                decimalScale={6}
                thousandSeparator=","
                min={0}
                {...form.getInputProps('cost_per_unit')}
              />
            </Group>
            {typeof form.values.quantity === 'number' && typeof form.values.cost_per_unit === 'number' && (
              <Text size="sm" c="dimmed" mt={-8}>
                Total cost basis: {money(form.values.quantity * form.values.cost_per_unit)}
              </Text>
            )}
          </>
        )}
        <Select
          label="Account"
          placeholder="Unassigned"
          clearable
          data={assetAccounts.map((a) => ({ value: String(a.id), label: a.name }))}
          description={
            selected
              ? selected.sync_from_holdings
                ? 'This holding will count toward that account on the Balance Sheet.'
                : 'Tip: turn on "Get balance from Investments tab" for this account to sync its value.'
              : isCash
                ? 'The account holding this cash (e.g. your brokerage or IRA).'
                : 'Link to a Balance Sheet account (e.g. your brokerage or 401k).'
          }
          {...form.getInputProps('account_id')}
        />
        <Textarea label="Notes" autosize minRows={1} {...form.getInputProps('notes')} />
        <Group justify="flex-end">
          <Button type="submit" loading={save.isPending}>
            {save.isPending && !isCash ? 'Checking ticker…' : 'Save'}
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
