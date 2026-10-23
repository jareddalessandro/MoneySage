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
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { IconAlertTriangle, IconCheck, IconPencil, IconPlus, IconRefresh, IconTrash } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { useState } from 'react';

import { api } from '../api';
import { confirmDelete, Delta, EmptyState, PageHeader, SectionCard, StatCard, useAppMutation } from '../components/common';
import { dateLabel, money, moneyCompact, percent, quantity } from '../format';
import type { AssetType, Holding, HoldingInput } from '../types';

const ASSET_LABELS: Record<AssetType, string> = { stock: 'Stock', etf: 'ETF', crypto: 'Crypto' };
const RANGES = { '1M': 30, '3M': 91, '6M': 182, '1Y': 365 } as const;
type Range = keyof typeof RANGES;
type Editing = { holding: Holding | null } | null;

export default function StocksPage() {
  const [range, setRange] = useState<Range>('3M');
  const [editing, setEditing] = useState<Editing>(null);

  const { data: holdings = [], isLoading } = useQuery({ queryKey: ['holdings'], queryFn: api.holdings });
  const { data: summary } = useQuery({ queryKey: ['portfolio-summary'], queryFn: api.portfolioSummary });
  const { data: history = [] } = useQuery({
    queryKey: ['portfolio-history', range],
    queryFn: () => api.portfolioHistory(RANGES[range]),
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
  const chartData = history.map((p) => ({ date: dayjs(p.date).format('MMM D'), Value: p.value }));

  return (
    <>
      <PageHeader
        title="Stocks"
        description="Stocks, ETFs, and crypto. Prices refresh automatically every evening."
        actions={
          <>
            <Button
              variant="default"
              leftSection={<IconRefresh size={16} />}
              loading={refresh.isPending}
              onClick={() => refresh.mutate(undefined)}
              disabled={holdings.length === 0}
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
              : 'Add cost basis to holdings to track gains'
          }
        />
        <StatCard
          label="Prices updated"
          value={run?.finished_at ? dayjs(run.finished_at).format('MMM D, h:mm A') : '—'}
          footer={
            run && (
              <Group gap={4}>
                {run.status === 'success' ? (
                  <IconCheck size={14} className="delta-up" />
                ) : (
                  <IconAlertTriangle size={14} className="delta-down" />
                )}
                <Text size="sm" c="dimmed">
                  {run.status === 'success' ? 'All prices updated' : run.message ?? `Refresh ${run.status}`}
                </Text>
              </Group>
            )
          }
        />
      </SimpleGrid>

      <Stack gap="lg">
        <SectionCard title="Holdings">
          {isLoading ? null : holdings.length === 0 ? (
            <EmptyState
              message="Add the stocks, ETFs, and crypto you own."
              action={
                <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setEditing({ holding: null })}>
                  Add holding
                </Button>
              }
            />
          ) : (
            <Table.ScrollContainer minWidth={900}>
              <Table highlightOnHover verticalSpacing="xs">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Ticker</Table.Th>
                    <Table.Th>Account</Table.Th>
                    <Table.Th ta="right">Quantity</Table.Th>
                    <Table.Th ta="right">Price</Table.Th>
                    <Table.Th ta="right">Value</Table.Th>
                    <Table.Th ta="right">Today</Table.Th>
                    <Table.Th ta="right">Cost basis</Table.Th>
                    <Table.Th ta="right">Gain / loss</Table.Th>
                    <Table.Th w={70} />
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {holdings.map((h) => (
                    <Table.Tr key={h.id}>
                      <Table.Td>
                        <Group gap={6} wrap="nowrap">
                          <Text fw={600} size="sm">
                            {h.ticker}
                          </Text>
                          <Badge size="xs" variant="light" color="gray">
                            {ASSET_LABELS[h.asset_type]}
                          </Badge>
                        </Group>
                        {h.notes && (
                          <Text size="xs" c="dimmed" lineClamp={1}>
                            {h.notes}
                          </Text>
                        )}
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm" c={h.account_name ? undefined : 'dimmed'}>
                          {h.account_name ?? 'Unassigned'}
                        </Text>
                      </Table.Td>
                      <Table.Td ta="right" className="num">
                        {quantity(h.quantity)}
                      </Table.Td>
                      <Table.Td ta="right" className="num">
                        {money(h.price)}
                        {h.price_date && (
                          <Text size="xs" c="dimmed">
                            {dateLabel(h.price_date)}
                          </Text>
                        )}
                      </Table.Td>
                      <Table.Td ta="right" className="num" fw={500}>
                        {money(h.market_value)}
                      </Table.Td>
                      <Table.Td ta="right">
                        <Group justify="flex-end">
                          <Delta value={h.day_change} />
                        </Group>
                      </Table.Td>
                      <Table.Td ta="right" className="num">
                        {money(h.cost_basis)}
                      </Table.Td>
                      <Table.Td ta="right">
                        <Group justify="flex-end">
                          {h.gain == null ? <Text size="sm">—</Text> : <Delta value={h.gain} />}
                        </Group>
                      </Table.Td>
                      <Table.Td>
                        <Group gap={4} wrap="nowrap" justify="flex-end">
                          <ActionIcon variant="subtle" color="gray" aria-label="Edit" onClick={() => setEditing({ holding: h })}>
                            <IconPencil size={16} />
                          </ActionIcon>
                          <ActionIcon
                            variant="subtle"
                            color="red"
                            aria-label="Delete"
                            onClick={() => confirmDelete(`${h.ticker} holding`, () => remove.mutate(h.id))}
                          >
                            <IconTrash size={16} />
                          </ActionIcon>
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
                <Table.Tfoot>
                  <Table.Tr>
                    <Table.Th colSpan={4}>Total</Table.Th>
                    <Table.Th ta="right" className="num">
                      {money(summary?.total_value)}
                    </Table.Th>
                    <Table.Th ta="right">
                      <Group justify="flex-end">
                        <Delta value={summary?.day_change} />
                      </Group>
                    </Table.Th>
                    <Table.Th ta="right" className="num">
                      {money(summary?.total_cost)}
                    </Table.Th>
                    <Table.Th ta="right">
                      <Group justify="flex-end">
                        <Delta value={summary?.total_gain} />
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
                    data={Object.keys(RANGES)}
                  />
                }
              >
                {chartData.length < 2 ? (
                  <EmptyState message="Not enough price history yet." />
                ) : (
                  <>
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

function HoldingForm({ holding, onDone }: { holding: Holding | null; onDone: () => void }) {
  const { data: accounts = [] } = useQuery({ queryKey: ['accounts'], queryFn: () => api.accounts() });
  const form = useForm({
    initialValues: {
      ticker: holding?.ticker ?? '',
      asset_type: holding?.asset_type ?? ('stock' as AssetType),
      quantity: holding?.quantity ?? ('' as number | ''),
      cost_basis: holding?.cost_basis ?? ('' as number | ''),
      account_id: holding?.account_id == null ? null : String(holding.account_id),
      notes: holding?.notes ?? '',
    },
    validate: {
      ticker: (v) => (v.trim() ? null : 'Required'),
      quantity: (v) => (typeof v === 'number' && v > 0 ? null : 'Enter a quantity greater than 0'),
    },
  });
  const save = useAppMutation(
    (body: HoldingInput) => (holding ? api.updateHolding(holding.id, body) : api.createHolding(body)),
    holding ? 'Holding updated' : 'Holding added',
  );

  const assetAccounts = accounts.filter((a) => a.kind === 'asset');
  const selected = assetAccounts.find((a) => String(a.id) === form.values.account_id);
  const isCrypto = form.values.asset_type === 'crypto';

  return (
    <form
      onSubmit={form.onSubmit((v) =>
        save.mutate(
          {
            ticker: v.ticker.trim().toUpperCase(),
            asset_type: v.asset_type,
            quantity: v.quantity as number,
            cost_basis: v.cost_basis === '' ? null : v.cost_basis,
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
            label="Total cost basis"
            description="Optional — what you paid in total"
            prefix="$"
            decimalScale={2}
            thousandSeparator=","
            min={0}
            {...form.getInputProps('cost_basis')}
          />
        </Group>
        <Select
          label="Account"
          placeholder="Unassigned"
          clearable
          data={assetAccounts.map((a) => ({ value: String(a.id), label: a.name }))}
          description={
            selected
              ? selected.sync_from_holdings
                ? 'This holding will count toward that account on the Balance Sheet.'
                : 'Tip: turn on "Get balance from Stocks tab" for this account to sync its value.'
              : 'Link to a Balance Sheet account (e.g. your brokerage or 401k).'
          }
          {...form.getInputProps('account_id')}
        />
        <Textarea label="Notes" autosize minRows={1} {...form.getInputProps('notes')} />
        <Group justify="flex-end">
          <Button type="submit" loading={save.isPending}>
            {save.isPending ? 'Checking ticker…' : 'Save'}
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
