import {
  ActionIcon,
  Anchor,
  Autocomplete,
  Button,
  Group,
  Menu,
  NumberInput,
  SegmentedControl,
  Select,
  Stack,
  Table,
  TagsInput,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core';
import { DateInput, MonthPickerInput } from '@mantine/dates';
import { useForm } from '@mantine/form';
import {
  IconAlertCircle,
  IconBuildingBank,
  IconCash,
  IconDots,
  IconFileSpreadsheet,
  IconFileTypePdf,
  IconPencil,
  IconPlus,
  IconTable,
  IconTrash,
} from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { useState } from 'react';

import { api } from '../api';
import { confirmDelete, EmptyState, SectionCard, useAppMutation } from '../components/common';
import { money, monthLabel, signedMoney } from '../format';
import type { Company, CompanySummary, RevenueShare, RevenueShareBasis, RevenueShareInput } from '../types';

/** Agreements to pay non-members a percentage of revenue, with what's earned, paid, and due. */
export function RevenueShares({
  company,
  shares,
  year,
  onAdd,
  onEdit,
  onPay,
  onFund,
  onMonths,
  onStatement,
}: {
  company: Company;
  shares: RevenueShare[];
  year: number;
  onAdd: () => void;
  onEdit: (share: RevenueShare) => void;
  onPay: (share: RevenueShare) => void;
  onFund: (share: RevenueShare) => void;
  onMonths: (share: RevenueShare) => void;
  onStatement: (share: RevenueShare) => void;
}) {
  const remove = useAppMutation((shareId: number) => api.deleteRevenueShare(company.id, shareId), 'Revenue share deleted');

  return (
    <SectionCard
      title="Revenue shares"
      actions={
        shares.length > 0 && (
          <Button size="xs" variant="default" leftSection={<IconPlus size={14} />} onClick={onAdd}>
            Add agreement
          </Button>
        )
      }
    >
      {shares.length === 0 ? (
        <EmptyState
          message="Track what you owe people who aren't members but get a percentage of revenue, like an investor's share or a sales commission."
          action={
            <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={onAdd}>
              Add agreement
            </Button>
          }
        />
      ) : (
        <>
          <Table.ScrollContainer minWidth={620}>
            <Table verticalSpacing={8} highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Payee</Table.Th>
                  <Table.Th ta="right">Earned {year}</Table.Th>
                  <Table.Th ta="right">Paid {year}</Table.Th>
                  <Table.Th ta="right">Due now</Table.Th>
                  <Table.Th w={150} />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {shares.map((s) => (
                  <Table.Tr key={s.id}>
                    <Table.Td>
                      <Text size="sm" fw={500}>
                        {s.payee}
                      </Text>
                      <Text size="xs" c="dimmed">
                        {s.terms}
                      </Text>
                      {s.funding_received > 0 && (
                        <Text size="xs" mt={2}>
                          Funding: {money(s.funding_received)} received · {money(s.funding_repaid)} repaid ·{' '}
                          <Text span size="xs" fw={600}>
                            {s.funding_outstanding > 0 ? `${money(s.funding_outstanding)} still owed` : 'fully repaid'}
                          </Text>
                        </Text>
                      )}
                      {s.missing_months.length > 0 && (
                        <Group gap={4} wrap="nowrap" mt={4}>
                          <IconAlertCircle size={14} color="var(--primary)" aria-hidden />
                          <Anchor component="button" type="button" size="xs" onClick={() => onMonths(s)}>
                            {s.missing_months.length === 1
                              ? `Enter revenue for ${monthLabel(s.missing_months[0])}`
                              : `Enter revenue for ${s.missing_months.length} months`}
                          </Anchor>
                        </Group>
                      )}
                    </Table.Td>
                    <Table.Td ta="right" className="num">
                      {money(s.earned_year)}
                    </Table.Td>
                    <Table.Td ta="right" className="num">
                      {money(s.paid_year)}
                    </Table.Td>
                    <Table.Td ta="right" className="num" fw={600}>
                      {s.balance_due < 0 ? `${money(-s.balance_due)} ahead` : money(s.balance_due)}
                    </Table.Td>
                    <Table.Td>
                      <Group gap={4} wrap="nowrap" justify="flex-end">
                        <Button size="xs" variant="default" leftSection={<IconCash size={14} />} onClick={() => onPay(s)}>
                          Record payment
                        </Button>
                        <Menu position="bottom-end">
                          <Menu.Target>
                            <ActionIcon variant="subtle" color="gray" aria-label={`More for ${s.payee}`}>
                              <IconDots size={16} />
                            </ActionIcon>
                          </Menu.Target>
                          <Menu.Dropdown>
                            <Menu.Item leftSection={<IconTable size={14} />} onClick={() => onMonths(s)}>
                              {s.basis === 'reported' ? 'Enter monthly revenue' : 'Monthly detail'}
                            </Menu.Item>
                            <Menu.Item leftSection={<IconBuildingBank size={14} />} onClick={() => onFund(s)}>
                              Record funding from {s.payee}
                            </Menu.Item>
                            <Menu.Item leftSection={<IconFileTypePdf size={14} />} onClick={() => onStatement(s)}>
                              Monthly statement for {s.payee}
                            </Menu.Item>
                            <Menu.Item leftSection={<IconPencil size={14} />} onClick={() => onEdit(s)}>
                              Edit agreement
                            </Menu.Item>
                            <Menu.Item
                              color="red"
                              leftSection={<IconTrash size={14} />}
                              onClick={() => confirmDelete(`${s.payee}'s revenue share`, () => remove.mutate(s.id))}
                            >
                              Delete
                            </Menu.Item>
                          </Menu.Dropdown>
                        </Menu>
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          <Text size="xs" c="dimmed" mt="sm">
            Earned is calculated month by month and rounded to the cent. Due now is everything earned minus everything
            paid, all time. Payments are expense entries, counted as cost of revenue
            {shares.some((s) => s.funding_received > 0)
              ? ". Funding a payee provided is a liability, not income: their payments repay it first, and only what's paid beyond it is an expense."
              : '.'}
          </Text>
        </>
      )}
    </SectionCard>
  );
}

const BASIS_HELP: Record<RevenueShareBasis, string> = {
  income: "Calculated from the income you record, optionally one product's, after any fee categories you list.",
  reported: 'You enter the revenue it applies to each month, e.g. sales from customers someone referred.',
};

export function RevenueShareForm({
  company,
  summary,
  share,
  onDone,
}: {
  company: Company;
  summary: CompanySummary | undefined;
  share: RevenueShare | null;
  onDone: () => void;
}) {
  const form = useForm({
    initialValues: {
      payee: share?.payee ?? '',
      basis: share?.basis ?? ('income' as RevenueShareBasis),
      product_id: share?.product_id != null ? String(share.product_id) : null,
      rate_percent: share?.rate_percent ?? ('' as number | ''),
      deduct_categories: share?.deduct_categories ?? [],
      start_date: share?.start_date ?? dayjs().startOf('month').format('YYYY-MM-DD'),
      end_date: share?.end_date ?? null,
      category: share?.category ?? 'Revenue share',
      notes: share?.notes ?? '',
    },
    validate: {
      payee: (v) => (v.trim() ? null : 'Required'),
      rate_percent: (v) => (typeof v === 'number' && v > 0 && v <= 100 ? null : 'Enter a percentage above 0, up to 100'),
      start_date: (v) => (v ? null : 'Required'),
      end_date: (v, values) => (v && values.start_date && v < values.start_date ? "Can't be before the start date" : null),
      category: (v) => (v.trim() ? null : 'Required'),
    },
  });
  const save = useAppMutation(
    (body: RevenueShareInput) =>
      share ? api.updateRevenueShare(company.id, share.id, body) : api.createRevenueShare(company.id, body),
    share ? 'Agreement updated' : 'Agreement added',
  );
  const basis = form.values.basis;
  const products = company.products.map((p) => ({ value: String(p.id), label: p.name }));

  return (
    <form
      onSubmit={form.onSubmit((v) =>
        save.mutate(
          {
            payee: v.payee.trim(),
            basis: v.basis,
            product_id: v.product_id ? Number(v.product_id) : null,
            rate_percent: v.rate_percent as number,
            deduct_categories: v.basis === 'income' ? v.deduct_categories : [],
            start_date: v.start_date,
            end_date: v.end_date || null,
            category: v.category.trim(),
            notes: v.notes.trim() || null,
          },
          { onSuccess: onDone },
        ),
      )}
    >
      <Stack>
        <Group grow align="flex-start">
          <TextInput label="Paid to" placeholder="e.g. Seed investor" data-autofocus {...form.getInputProps('payee')} />
          <NumberInput label="Share" suffix="%" decimalScale={4} min={0} max={100} {...form.getInputProps('rate_percent')} />
        </Group>
        <div>
          <Text size="sm" fw={500} mb={4}>
            Percentage of
          </Text>
          <SegmentedControl
            fullWidth
            value={basis}
            onChange={(v) => form.setFieldValue('basis', v as RevenueShareBasis)}
            data={[
              { value: 'income', label: 'Recorded income' },
              { value: 'reported', label: 'Revenue I enter monthly' },
            ]}
          />
          <Text size="xs" c="dimmed" mt={6}>
            {BASIS_HELP[basis]}
          </Text>
        </div>
        <Select
          label={basis === 'income' ? 'Income from' : 'Product'}
          description={basis === 'income' ? undefined : 'Optional. Payments are tagged with it.'}
          placeholder={basis === 'income' ? 'All company income' : 'No product'}
          data={products}
          clearable
          comboboxProps={{ withinPortal: true }}
          {...form.getInputProps('product_id')}
        />
        {basis === 'income' && (
          <TagsInput
            label="Calculated after"
            description="Expense categories subtracted from that income first, like App Store or Stripe fees. Leave empty if you record income after fees."
            placeholder="Pick or type a category, then Enter"
            data={summary?.expense_categories ?? []}
            comboboxProps={{ withinPortal: true }}
            {...form.getInputProps('deduct_categories')}
          />
        )}
        <Group grow align="flex-end">
          <DateInput label="Starts" valueFormat="MMM D, YYYY" {...form.getInputProps('start_date')} />
          <DateInput
            label="Ends"
            placeholder="Never"
            description="Leave empty if it never ends"
            valueFormat="MMM D, YYYY"
            clearable
            {...form.getInputProps('end_date')}
          />
        </Group>
        <Autocomplete
          label="Payment category"
          description="Payments are recorded as expenses in this category and count as cost of revenue."
          data={summary?.expense_categories ?? []}
          comboboxProps={{ withinPortal: true }}
          {...form.getInputProps('category')}
        />
        <Textarea label="Notes" description="Private: not on the payee's statement." autosize minRows={1} {...form.getInputProps('notes')} />
        <Group justify="flex-end">
          <Button variant="default" onClick={onDone}>
            Cancel
          </Button>
          <Button type="submit" loading={save.isPending}>
            {share ? 'Save' : 'Add agreement'}
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

/** Month-by-month figures for the year; for the reported basis, revenue is entered here. */
export function ShareMonths({
  companyId,
  share,
  year,
  onDone,
}: {
  companyId: number;
  share: RevenueShare;
  year: number;
  onDone: () => void;
}) {
  const reported = share.basis === 'reported';
  const startYear = dayjs(share.start_date).year();
  const [shownYear, setShownYear] = useState(Math.max(year, startYear));
  const { data: months = [], isLoading } = useQuery({
    queryKey: ['revenue-share-months', companyId, share.id, shownYear],
    queryFn: () => api.revenueShareMonths(companyId, share.id, shownYear),
  });
  const [edits, setEdits] = useState<Record<string, number | null>>({});
  const save = useAppMutation(
    (rows: { month: string; revenue: number | null }[]) => api.setRevenueShareMonths(companyId, share.id, rows),
    'Revenue saved',
  );
  const hasFees = share.deduct_categories.length > 0;
  const changed = Object.entries(edits).map(([month, revenue]) => ({ month, revenue }));
  const years = Array.from({ length: dayjs().year() - startYear + 1 }, (_, i) => String(dayjs().year() - i));

  return (
    <Stack>
      <Group justify="space-between" wrap="nowrap" align="flex-start">
        <Text size="sm" c="dimmed">
          {share.terms}.
        </Text>
        <Select
          aria-label="Year"
          w={100}
          data={years}
          value={String(shownYear)}
          onChange={(v) => {
            if (v) {
              setShownYear(Number(v));
              setEdits({});
            }
          }}
          allowDeselect={false}
          comboboxProps={{ withinPortal: true }}
        />
      </Group>
      {isLoading ? null : months.length === 0 ? (
        <EmptyState message={`Nothing for ${shownYear}: the agreement starts ${dayjs(share.start_date).format('MMM D, YYYY')}.`} />
      ) : (
        <Table.ScrollContainer minWidth={hasFees ? 640 : 520}>
          <Table verticalSpacing={4}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Month</Table.Th>
                <Table.Th ta="right">{reported ? 'Eligible revenue' : 'Revenue'}</Table.Th>
                {hasFees && <Table.Th ta="right">Fees</Table.Th>}
                {hasFees && <Table.Th ta="right">Base</Table.Th>}
                <Table.Th ta="right">Earned</Table.Th>
                <Table.Th ta="right">Paid</Table.Th>
                <Table.Th ta="right">Due at month end</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {months.map((m) => (
                <Table.Tr key={m.month}>
                  <Table.Td>{dayjs(`${m.month}-01`).format('MMMM')}</Table.Td>
                  <Table.Td ta="right" className="num">
                    {reported ? (
                      <NumberInput
                        aria-label={`Revenue for ${monthLabel(m.month)}`}
                        size="xs"
                        w={130}
                        ml="auto"
                        prefix="$"
                        decimalScale={2}
                        thousandSeparator=","
                        min={0}
                        placeholder="Not entered"
                        className={m.revenue == null && !(m.month in edits) ? 'needs-entry' : undefined}
                        value={m.month in edits ? (edits[m.month] ?? '') : (m.revenue ?? '')}
                        onChange={(v) => setEdits((e) => ({ ...e, [m.month]: typeof v === 'number' ? v : null }))}
                      />
                    ) : (
                      money(m.revenue)
                    )}
                  </Table.Td>
                  {hasFees && (
                    <Table.Td ta="right" className="num">
                      {m.deductions ? `−${money(m.deductions)}` : money(0)}
                    </Table.Td>
                  )}
                  {hasFees && (
                    <Table.Td ta="right" className="num">
                      {money(m.base)}
                    </Table.Td>
                  )}
                  <Table.Td ta="right" className="num">
                    {money(m.earned)}
                  </Table.Td>
                  <Table.Td ta="right" className="num">
                    {money(m.paid)}
                  </Table.Td>
                  <Table.Td ta="right" className="num" fw={500}>
                    {m.balance < 0 ? `${money(-m.balance)} ahead` : money(m.balance)}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
      <Group justify="flex-end">
        {reported ? (
          <>
            <Button variant="default" onClick={onDone}>
              Cancel
            </Button>
            <Button
              disabled={changed.length === 0}
              loading={save.isPending}
              onClick={() => save.mutate(changed, { onSuccess: onDone })}
            >
              Save revenue
            </Button>
          </>
        ) : (
          <Button variant="default" onClick={onDone}>
            Close
          </Button>
        )}
      </Group>
    </Stack>
  );
}

/** Pick a month and download the payee's statement for it. */
export function PayeeStatement({ companyId, share }: { companyId: number; share: RevenueShare }) {
  const start = dayjs(share.start_date).startOf('month');
  const lastFull = dayjs().subtract(1, 'month').startOf('month');
  const [month, setMonth] = useState((lastFull.isBefore(start) ? dayjs().startOf('month') : lastFull).format('YYYY-MM-DD'));
  const ym = month.slice(0, 7);
  const href = (format: 'pdf' | 'xlsx') =>
    `/api/companies/${companyId}/revenue-shares/${share.id}/statement?month=${ym}&format=${format}`;
  const current = ym === dayjs().format('YYYY-MM');

  return (
    <Stack>
      <Text size="sm">
        For {share.payee}: the month's revenue and their share, payments made, the balance due, and the year to date
        by month. Your notes aren't included.
      </Text>
      <MonthPickerInput
        label="Month"
        valueFormat="MMMM YYYY"
        value={month}
        onChange={(v) => v && setMonth(v)}
        minDate={start.format('YYYY-MM-DD')}
        maxDate={dayjs().format('YYYY-MM-DD')}
        popoverProps={{ withinPortal: true }}
      />
      {current && (
        <Text size="xs" c="dimmed">
          This month isn't over, so the statement runs through today.
        </Text>
      )}
      {share.basis === 'reported' && share.missing_months.includes(ym) && (
        <Group gap={6} wrap="nowrap">
          <IconAlertCircle size={14} color="var(--primary)" aria-hidden />
          <Text size="xs" c="dimmed">
            No revenue entered for {monthLabel(ym)} yet, so its share shows as $0.
          </Text>
        </Group>
      )}
      <Group justify="flex-end">
        <Button component="a" href={href('xlsx')} download variant="default" leftSection={<IconFileSpreadsheet size={16} />}>
          Excel
        </Button>
        <Button component="a" href={href('pdf')} download leftSection={<IconFileTypePdf size={16} />}>
          PDF
        </Button>
      </Group>
    </Stack>
  );
}

/** "$85.00 due" / "$20.00 paid ahead" / "Nothing due", for the payment form. */
export const dueText = (share: RevenueShare) =>
  share.balance_due > 0 ? `${money(share.balance_due)} due` : share.balance_due < 0 ? `${signedMoney(-share.balance_due)} paid ahead` : 'Nothing due';
