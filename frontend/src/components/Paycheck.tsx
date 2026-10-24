import { Box, Group, Progress, SegmentedControl, Select, SimpleGrid, Stack, Table, Text, Tooltip } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';
import { useState } from 'react';

import { money, percent } from '../format';
import type { Deduction, DeductionStage, DeductionType, PaycheckBreakdown } from '../types';

export const stageOf = (d: Pick<Deduction, 'type' | 'pre_tax'>): DeductionStage =>
  d.type === 'tax' ? 'tax' : d.pre_tax ? 'pre_tax' : 'post_tax';

/** Common pay stub lines, offered as quick-adds in the paycheck form. */
export const DEDUCTION_PRESETS: { label: string; group: string; deduction: Omit<Deduction, 'amount'> }[] = [
  { group: 'Retirement', label: '401(k)', deduction: { name: '401(k)', type: 'retirement', pre_tax: true } },
  { group: 'Retirement', label: 'Roth 401(k)', deduction: { name: 'Roth 401(k)', type: 'retirement', pre_tax: false } },
  { group: 'Insurance', label: 'Health insurance', deduction: { name: 'Health insurance', type: 'insurance', pre_tax: true } },
  { group: 'Insurance', label: 'Dental insurance', deduction: { name: 'Dental insurance', type: 'insurance', pre_tax: true } },
  { group: 'Insurance', label: 'Vision insurance', deduction: { name: 'Vision insurance', type: 'insurance', pre_tax: true } },
  { group: 'Insurance', label: 'Life insurance', deduction: { name: 'Life insurance', type: 'insurance', pre_tax: false } },
  { group: 'Savings', label: 'HSA', deduction: { name: 'HSA', type: 'hsa', pre_tax: true } },
  { group: 'Savings', label: 'FSA', deduction: { name: 'FSA', type: 'hsa', pre_tax: true } },
  { group: 'Taxes', label: 'Federal income tax', deduction: { name: 'Federal income tax', type: 'tax', pre_tax: false } },
  { group: 'Taxes', label: 'State income tax', deduction: { name: 'State income tax', type: 'tax', pre_tax: false } },
  { group: 'Taxes', label: 'Social Security', deduction: { name: 'Social Security', type: 'tax', pre_tax: false } },
  { group: 'Taxes', label: 'Medicare', deduction: { name: 'Medicare', type: 'tax', pre_tax: false } },
  { group: 'Other', label: 'Other deduction', deduction: { name: '', type: 'other', pre_tax: false } },
];

interface Line {
  name: string;
  stage: DeductionStage;
  type: DeductionType;
  amount: number;
}

const STAGE_LABELS: Record<DeductionStage, string> = {
  pre_tax: 'Pre-tax deductions',
  tax: 'Taxes',
  post_tax: 'After-tax deductions',
};

const round2 = (n: number) => Math.round(n * 100) / 100;

/**
 * Gross → take-home, top to bottom: pre-tax deductions, taxes, after-tax pay, after-tax
 * deductions, anything not itemized, and take-home. Subtotals use a tone shift, not lines.
 */
export function PaycheckWaterfall({
  gross,
  takeHome: enteredTakeHome,
  lines,
}: {
  gross: number;
  /** null while it hasn't been entered: show take-home as gross minus the itemized deductions. */
  takeHome: number | null;
  lines: Line[];
}) {
  const total = (stage: DeductionStage) => lines.filter((l) => l.stage === stage).reduce((s, l) => s + l.amount, 0);
  const preTax = total('pre_tax');
  const taxes = total('tax');
  const postTax = total('post_tax');
  const takeHome = enteredTakeHome ?? round2(gross - preTax - taxes - postTax);
  const unitemized = round2(gross - preTax - taxes - postTax - takeHome);
  const pct = (n: number) => (gross > 0 ? percent(n / gross) : '');

  const row = (label: string, amount: number, opts: { sign?: boolean; strong?: boolean; tone?: boolean; key?: string } = {}) => (
    <Table.Tr key={opts.key ?? label} bg={opts.tone ? 'var(--surface-container-highest)' : undefined}>
      <Table.Td pl={opts.sign ? 'lg' : undefined}>
        <Text size="sm" fw={opts.strong ? 700 : undefined}>
          {label}
        </Text>
      </Table.Td>
      <Table.Td ta="right" className="num">
        <Text size="sm" fw={opts.strong ? 700 : undefined}>
          {opts.sign ? `−${money(amount)}` : money(amount)}
        </Text>
      </Table.Td>
      <Table.Td ta="right" className="num" w={70}>
        <Text size="xs" c="dimmed">
          {pct(amount)}
        </Text>
      </Table.Td>
    </Table.Tr>
  );

  const stageRows = (stage: DeductionStage) => {
    const stageLines = lines.filter((l) => l.stage === stage);
    if (stageLines.length === 0) return null;
    return [
      <Table.Tr key={`${stage}-head`}>
        <Table.Td colSpan={3} pt="sm" pb={2}>
          <Text className="label-sm">{STAGE_LABELS[stage]}</Text>
        </Table.Td>
      </Table.Tr>,
      ...stageLines.map((l, i) => row(l.name || 'Unnamed', l.amount, { sign: true, key: `${stage}-${i}` })),
    ];
  };

  return (
    <Stack gap="xs">
      <Table verticalSpacing={5} highlightOnHover={false}>
        <Table.Tbody>
          {row('Gross pay', gross, { strong: true, tone: true })}
          {stageRows('pre_tax')}
          {stageRows('tax')}
          {taxes > 0 && row('After-tax pay', gross - preTax - taxes, { strong: true, tone: true })}
          {stageRows('post_tax')}
          {unitemized > 0 && [
            <Table.Tr key="unitemized-head">
              <Table.Td colSpan={3} pt="sm" pb={2}>
                <Text className="label-sm">Not itemized</Text>
              </Table.Td>
            </Table.Tr>,
            row(taxes > 0 ? 'Other withholding' : 'Taxes or other withholding', unitemized, { sign: true }),
          ]}
          {row(enteredTakeHome == null ? 'Take-home pay (calculated)' : 'Take-home pay', takeHome, { strong: true, tone: true })}
        </Table.Tbody>
      </Table>
      {taxes === 0 && gross > 0 && (
        <Text size="xs" c="dimmed">
          Add your tax withholding to see after-tax pay.
        </Text>
      )}
      {unitemized < 0 && (
        <Group gap={6} wrap="nowrap" className="delta-down">
          <IconAlertTriangle size={14} aria-hidden />
          <Text size="xs" inherit>
            Deductions add up to {money(-unitemized)} more than gross minus take-home. Check the amounts.
          </Text>
        </Group>
      )}
    </Stack>
  );
}

type Period = 'paycheck' | 'month' | 'year';

interface Segment {
  key: string;
  label: string;
  color: string;
  /** Striped: an estimate rather than an entered amount. */
  hatched?: boolean;
  amount: number;
}

/**
 * Where gross pay goes. Hues are validated as a set on surface_container_high. Gray is the
 * neutral for HSA/other deductions; the not-itemized remainder is striped because it's inferred.
 */
function splitSegments(data: PaycheckBreakdown): Segment[] {
  const sumType = (...types: DeductionType[]) =>
    data.lines.filter((l) => types.includes(l.type)).reduce((s, l) => s + l.annual_amount, 0);
  const hasTax = data.annual_taxes > 0;
  const hsa = sumType('hsa');
  const other = sumType('other');
  const segments: Segment[] = [
    { key: 'take_home', label: 'Take-home', color: 'var(--series-1)', amount: data.annual_take_home },
    { key: 'retirement', label: 'Retirement', color: 'var(--split-retirement)', amount: sumType('retirement') },
    { key: 'tax', label: 'Taxes', color: 'var(--split-tax)', amount: data.annual_taxes },
    { key: 'insurance', label: 'Insurance', color: 'var(--split-insurance)', amount: sumType('insurance') },
    {
      key: 'other',
      label: hsa && other ? 'HSA / FSA & other' : hsa ? 'HSA / FSA' : 'Other deductions',
      color: 'var(--split-other)',
      amount: hsa + other,
    },
    {
      // With no taxes entered, the gap between gross and take-home is mostly tax withholding.
      key: 'unitemized',
      label: hasTax ? 'Not itemized' : 'Taxes or not itemized',
      color: hasTax ? 'var(--split-other)' : 'var(--split-tax)',
      hatched: true,
      amount: Math.max(data.annual_unitemized, 0),
    },
  ];
  return segments.filter((s) => s.amount > 0);
}

const COMBINED = 'combined';

/** Budget-page card: every paycheck combined, or one at a time; per paycheck, monthly, or yearly. */
export function IncomeBreakdownCard({ combined, items }: { combined: PaycheckBreakdown; items: PaycheckBreakdown[] }) {
  const [view, setView] = useState(COMBINED);
  const [period, setPeriod] = useState<Period>('year');

  // Fall back to the combined view if the selected paycheck was deleted (or there's only one).
  const single = items.length === 1 ? items[0] : items.find((i) => String(i.budget_item_id) === view);
  const data = single ?? combined;
  const perYear = single?.paychecks_per_year ?? null;
  const activePeriod: Period = period === 'paycheck' && !perYear ? 'month' : period;
  const k = activePeriod === 'year' ? 1 : activePeriod === 'month' ? 1 / 12 : 1 / perYear!;

  const gross = data.annual_gross;
  const segments = splitSegments(data);
  const retirement = data.lines.filter((l) => l.type === 'retirement').reduce((s, l) => s + l.annual_amount, 0);
  const hasTax = data.annual_taxes > 0;

  return (
    <Stack gap="md">
      <Group justify="space-between" wrap="wrap" gap="xs">
        {items.length > 1 ? (
          <Select
            size="xs"
            w={210}
            aria-label="Which paycheck"
            allowDeselect={false}
            value={single ? String(single.budget_item_id) : COMBINED}
            onChange={(v) => v && setView(v)}
            data={[
              { value: COMBINED, label: `All ${items.length} paychecks combined` },
              ...items.map((i) => ({ value: String(i.budget_item_id), label: i.name })),
            ]}
          />
        ) : (
          <Text size="sm" c="dimmed">
            {data.name}
          </Text>
        )}
        <SegmentedControl
          size="xs"
          value={activePeriod}
          onChange={(v) => setPeriod(v as Period)}
          data={[
            ...(perYear ? [{ value: 'paycheck', label: 'Per paycheck' }] : []),
            { value: 'month', label: 'Monthly' },
            { value: 'year', label: 'Yearly' },
          ]}
        />
      </Group>
      {perYear && (
        <Text size="xs" c="dimmed" mt={-8}>
          {perYear} paychecks a year
        </Text>
      )}

      {/* Two per row: four across is too narrow for yearly amounts at this card's width. */}
      <SimpleGrid cols={2} spacing="xs">
        <MiniStat label="Gross pay" value={money(gross * k)} />
        <MiniStat label="Take-home pay" value={money(data.annual_take_home * k)} />
        <MiniStat label="Retirement" value={money(retirement * k)} />
        {hasTax ? (
          <MiniStat label="Tax rate" value={gross > 0 ? percent(data.annual_taxes / gross) : '—'} />
        ) : (
          <MiniStat label="Not itemized" value={gross > 0 ? percent(Math.max(data.annual_unitemized, 0) / gross) : '—'} />
        )}
      </SimpleGrid>

      <Box>
        <Text className="label-sm" mb={6}>
          Where gross pay goes
        </Text>
        <Progress.Root size={14} style={{ gap: 2, background: 'transparent' }} aria-label="Where gross pay goes">
          {segments.map((s) => (
            <Tooltip key={s.key} label={`${s.label}: ${money(s.amount * k)} (${percent(s.amount / gross)})`}>
              <Progress.Section value={(s.amount / gross) * 100} color={s.color} className={s.hatched ? 'hatched' : undefined} />
            </Tooltip>
          ))}
        </Progress.Root>
        <Stack gap={4} mt="sm">
          {segments.map((s) => (
            <Group key={s.key} justify="space-between" wrap="nowrap" gap="xs">
              <Group gap={8} wrap="nowrap">
                <Box
                  w={10}
                  h={10}
                  className={s.hatched ? 'hatched' : undefined}
                  style={{ borderRadius: 3, backgroundColor: s.color, flexShrink: 0 }}
                />
                <Text size="sm">{s.label}</Text>
              </Group>
              <Group gap="sm" wrap="nowrap">
                <Text size="sm" className="num">
                  {money(s.amount * k)}
                </Text>
                <Text size="xs" c="dimmed" className="num" w={44} ta="right">
                  {percent(s.amount / gross)}
                </Text>
              </Group>
            </Group>
          ))}
        </Stack>
      </Box>

      <Box>
        <Text className="label-sm" mb={4}>
          Gross to take-home
        </Text>
        <PaycheckWaterfall
          gross={gross * k}
          takeHome={data.annual_take_home * k}
          lines={data.lines.map((l) => ({ name: l.name, stage: l.stage, type: l.type, amount: l.annual_amount * k }))}
        />
      </Box>
    </Stack>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <Box p="xs" style={{ background: 'var(--surface-container-highest)', borderRadius: 'var(--mantine-radius-md)' }}>
      <Text className="label-sm" style={{ letterSpacing: '0.06rem' }}>
        {label}
      </Text>
      <Text className="headline num" fw={800} size="md" mt={2}>
        {value}
      </Text>
    </Box>
  );
}
