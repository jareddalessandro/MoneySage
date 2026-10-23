import { BarChart } from '@mantine/charts';
import {
  ActionIcon,
  Badge,
  Button,
  Grid,
  Group,
  Modal,
  NumberInput,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { IconPencil, IconPlus, IconTrash } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { api } from '../api';
import CategorySelect from '../components/CategorySelect';
import { confirmDelete, EmptyState, PageHeader, SectionCard, StatCard, useAppMutation } from '../components/common';
import { FREQUENCY_LABELS, money, moneyCompact, percent } from '../format';
import type { BudgetItem, BudgetItemInput, CategoryKind, Frequency } from '../types';

const MONTHLY_FACTOR: Record<Frequency, number> = {
  weekly: 52 / 12,
  biweekly: 26 / 12,
  semimonthly: 2,
  monthly: 1,
  quarterly: 1 / 3,
  annual: 1 / 12,
};

type Editing = { kind: CategoryKind; item: BudgetItem | null } | null;

export default function BudgetPage() {
  const [editing, setEditing] = useState<Editing>(null);
  const { data: items = [], isLoading } = useQuery({ queryKey: ['budget-items'], queryFn: api.budgetItems });
  const { data: summary } = useQuery({ queryKey: ['budget-summary'], queryFn: api.budgetSummary });
  const remove = useAppMutation((id: number) => api.deleteBudgetItem(id), 'Budget item deleted');

  const income = items.filter((i) => i.category.kind === 'income');
  const expenses = items.filter((i) => i.category.kind === 'expense');
  const expenseByCategory = (summary?.by_category ?? [])
    .filter((c) => c.kind === 'expense')
    .map((c) => ({ category: c.name, Monthly: c.monthly_amount }));
  const savingsRate = summary && summary.monthly_income > 0 ? summary.monthly_surplus / summary.monthly_income : null;

  const itemTable = (rows: BudgetItem[], kind: CategoryKind) =>
    rows.length === 0 ? (
      <EmptyState
        message={kind === 'income' ? 'No expected income yet.' : 'No expected expenses yet.'}
        action={
          <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setEditing({ kind, item: null })}>
            Add {kind}
          </Button>
        }
      />
    ) : (
      <Table.ScrollContainer minWidth={560}>
        <Table highlightOnHover verticalSpacing="xs">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Name</Table.Th>
              <Table.Th>Category</Table.Th>
              <Table.Th ta="right">Amount</Table.Th>
              <Table.Th>How often</Table.Th>
              <Table.Th ta="right">Per month</Table.Th>
              <Table.Th w={70} />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((item) => (
              <Table.Tr key={item.id}>
                <Table.Td>
                  <Text size="sm">{item.name}</Text>
                  {item.notes && (
                    <Text size="xs" c="dimmed" lineClamp={1}>
                      {item.notes}
                    </Text>
                  )}
                </Table.Td>
                <Table.Td>
                  <Badge variant="light" color="gray" fw={500} tt="none">
                    {item.category.name}
                  </Badge>
                </Table.Td>
                <Table.Td ta="right" className="num">
                  {money(item.amount)}
                </Table.Td>
                <Table.Td>{FREQUENCY_LABELS[item.frequency]}</Table.Td>
                <Table.Td ta="right" className="num" fw={500}>
                  {money(item.monthly_amount)}
                </Table.Td>
                <Table.Td>
                  <Group gap={4} wrap="nowrap" justify="flex-end">
                    <ActionIcon variant="subtle" color="gray" aria-label="Edit" onClick={() => setEditing({ kind, item })}>
                      <IconPencil size={16} />
                    </ActionIcon>
                    <ActionIcon
                      variant="subtle"
                      color="red"
                      aria-label="Delete"
                      onClick={() => confirmDelete(`"${item.name}"`, () => remove.mutate(item.id))}
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
                {money(rows.reduce((sum, r) => sum + r.monthly_amount, 0))}
              </Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Tfoot>
        </Table>
      </Table.ScrollContainer>
    );

  return (
    <>
      <PageHeader
        title="Budget"
        description="What you expect to earn and spend. Everything is converted to a monthly amount."
        actions={
          <>
            <Button variant="light" leftSection={<IconPlus size={16} />} onClick={() => setEditing({ kind: 'income', item: null })}>
              Add income
            </Button>
            <Button leftSection={<IconPlus size={16} />} onClick={() => setEditing({ kind: 'expense', item: null })}>
              Add expense
            </Button>
          </>
        }
      />

      <SimpleGrid cols={{ base: 1, xs: 2, md: 4 }} mb="md">
        <StatCard label="Monthly income" value={money(summary?.monthly_income)} />
        <StatCard label="Monthly expenses" value={money(summary?.monthly_expenses)} />
        <StatCard
          label="Monthly surplus"
          value={
            <span className={summary && summary.monthly_surplus < 0 ? 'delta-down' : undefined}>
              {money(summary?.monthly_surplus)}
            </span>
          }
          footer={summary && summary.monthly_surplus < 0 ? 'Planned spending exceeds income' : 'Left over each month'}
        />
        <StatCard
          label="Savings rate"
          value={savingsRate == null ? '—' : percent(savingsRate)}
          footer="Surplus as a share of income"
        />
      </SimpleGrid>

      <Grid gutter="md">
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Stack gap="md">
            <SectionCard title="Expected income">{isLoading ? null : itemTable(income, 'income')}</SectionCard>
            <SectionCard title="Expected expenses">{isLoading ? null : itemTable(expenses, 'expense')}</SectionCard>
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <SectionCard title="Monthly expenses by category">
            {expenseByCategory.length === 0 ? (
              <EmptyState message="Add expected expenses to see where the money goes." />
            ) : (
              <BarChart
                h={Math.max(160, expenseByCategory.length * 36 + 40)}
                data={expenseByCategory}
                dataKey="category"
                orientation="vertical"
                series={[{ name: 'Monthly', color: 'var(--series-2)' }]}
                valueFormatter={(v) => money(v)}
                withBarValueLabel
                valueLabelProps={{ formatter: (v: number) => moneyCompact(v), fontSize: 11 }}
                gridAxis="none"
                withXAxis={false}
                yAxisProps={{ width: 140 }}
                barProps={{ radius: [0, 4, 4, 0] }}
                barChartProps={{ margin: { right: 56 } }}
                maxBarWidth={20}
              />
            )}
          </SectionCard>
        </Grid.Col>
      </Grid>

      <BudgetItemModal editing={editing} onClose={() => setEditing(null)} />
    </>
  );
}

function BudgetItemModal({ editing, onClose }: { editing: Editing; onClose: () => void }) {
  return (
    <Modal
      opened={editing !== null}
      onClose={onClose}
      title={editing ? `${editing.item ? 'Edit' : 'Add'} expected ${editing.kind}` : ''}
    >
      {/* Keyed so the form resets each time the modal opens with a different item. */}
      {editing && <BudgetItemForm key={editing.item?.id ?? `new-${editing.kind}`} editing={editing} onDone={onClose} />}
    </Modal>
  );
}

function BudgetItemForm({ editing, onDone }: { editing: NonNullable<Editing>; onDone: () => void }) {
  const { item, kind } = editing;
  const form = useForm({
    initialValues: {
      name: item?.name ?? '',
      category_id: item?.category.id ?? (null as number | null),
      amount: item?.amount ?? ('' as number | ''),
      frequency: item?.frequency ?? ('monthly' as Frequency),
      notes: item?.notes ?? '',
    },
    validate: {
      name: (v) => (v.trim() ? null : 'Required'),
      category_id: (v) => (v ? null : 'Required'),
      amount: (v) => (typeof v === 'number' && v > 0 ? null : 'Enter an amount greater than 0'),
    },
  });
  const save = useAppMutation(
    (body: BudgetItemInput) => (item ? api.updateBudgetItem(item.id, body) : api.createBudgetItem(body)),
    item ? 'Budget item updated' : 'Budget item added',
  );

  const { amount, frequency } = form.values;
  const monthly = typeof amount === 'number' ? amount * MONTHLY_FACTOR[frequency] : null;

  return (
    <form
      onSubmit={form.onSubmit((v) =>
        save.mutate(
          {
            name: v.name.trim(),
            category_id: v.category_id!,
            amount: v.amount as number,
            frequency: v.frequency,
            notes: v.notes.trim() || null,
          },
          { onSuccess: onDone },
        ),
      )}
    >
      <Stack>
        <TextInput
          label="Name"
          placeholder={kind === 'income' ? "e.g. Jared's paycheck" : 'e.g. Mortgage'}
          data-autofocus
          {...form.getInputProps('name')}
        />
        <CategorySelect kind={kind} {...form.getInputProps('category_id')} />
        <Group grow align="flex-start">
          <NumberInput label="Amount" prefix="$" decimalScale={2} thousandSeparator="," min={0} {...form.getInputProps('amount')} />
          <Select
            label="How often"
            data={Object.entries(FREQUENCY_LABELS).map(([value, label]) => ({ value, label }))}
            allowDeselect={false}
            {...form.getInputProps('frequency')}
          />
        </Group>
        {monthly != null && frequency !== 'monthly' && (
          <Text size="sm" c="dimmed">
            ≈ {money(monthly)} per month
          </Text>
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
