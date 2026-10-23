import { ActionIcon, Button, Card, Group, Paper, Stack, Text, Title, Tooltip } from '@mantine/core';
import { MonthPickerInput } from '@mantine/dates';
import { modals } from '@mantine/modals';
import { notifications } from '@mantine/notifications';
import { IconArrowDownRight, IconArrowUpRight, IconChevronLeft, IconChevronRight } from '@tabler/icons-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { shiftMonth, signedMoney, thisMonth } from '../format';

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <Group justify="space-between" align="flex-end" mb="xl" wrap="wrap" gap="sm">
      <div>
        <Title order={1} fz="1.75rem" lts="-0.01em">
          {title}
        </Title>
        {description && (
          <Text c="dimmed" size="sm" mt={4}>
            {description}
          </Text>
        )}
      </div>
      {actions && <Group gap="xs">{actions}</Group>}
    </Group>
  );
}

/** Up/down arrow + signed amount; `goodWhen` decides which direction is green. */
export function Delta({
  value,
  goodWhen = 'up',
  suffix,
  size = 'sm',
}: {
  value: number | null | undefined;
  goodWhen?: 'up' | 'down';
  suffix?: string;
  size?: 'xs' | 'sm' | 'md';
}) {
  if (value == null) return null;
  if (value === 0) {
    return (
      <Text size={size} c="dimmed" className="num">
        No change{suffix ? ` ${suffix}` : ''}
      </Text>
    );
  }
  const good = goodWhen === 'up' ? value > 0 : value < 0;
  const Icon = value > 0 ? IconArrowUpRight : IconArrowDownRight;
  return (
    <Group gap={2} wrap="nowrap" className={good ? 'delta-up' : 'delta-down'}>
      <Icon size={14} stroke={2} aria-hidden />
      <Text size={size} inherit className="num" fw={500}>
        {signedMoney(value)}
        {suffix ? ` ${suffix}` : ''}
      </Text>
    </Group>
  );
}

export function StatCard({ label, value, footer }: { label: string; value: ReactNode; footer?: ReactNode }) {
  return (
    <Paper p="1.1rem" h="100%">
      <Text className="label-sm">{label}</Text>
      <Text className="headline num" fw={800} fz="1.75rem" mt={6} lh={1.15}>
        {value}
      </Text>
      {footer && (
        <Text component="div" size="sm" c="dimmed" mt={8}>
          {footer}
        </Text>
      )}
    </Paper>
  );
}

/** The one headline number on a page, at display size on the primary gradient wash. */
export function HeroStat({ label, value, footer }: { label: string; value: ReactNode; footer?: ReactNode }) {
  return (
    <Paper p="lg" h="100%" className="hero-card">
      <Text className="label-sm">{label}</Text>
      <Text className="headline num" fw={800} fz="clamp(2.25rem, 5vw, 3.5rem)" mt={8} lh={1.05} lts="-0.02em">
        {value}
      </Text>
      {footer && (
        <Text component="div" size="sm" c="dimmed" mt="sm">
          {footer}
        </Text>
      )}
    </Paper>
  );
}

export function SectionCard({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <Card p="1.1rem">
      <Group justify="space-between" mb="md" wrap="wrap" gap="xs">
        <Text className="headline" fw={700} size="lg">
          {title}
        </Text>
        {actions && <Group gap="xs">{actions}</Group>}
      </Group>
      {children}
    </Card>
  );
}

export function EmptyState({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <Stack align="center" py="xl" gap="sm">
      <Text c="dimmed" size="sm" ta="center">
        {message}
      </Text>
      {action}
    </Stack>
  );
}

export function MonthSwitcher({ value, onChange }: { value: string; onChange: (month: string) => void }) {
  return (
    <Group gap={4} wrap="nowrap">
      <Tooltip label="Previous month">
        <ActionIcon variant="default" size="lg" aria-label="Previous month" onClick={() => onChange(shiftMonth(value, -1))}>
          <IconChevronLeft size={18} />
        </ActionIcon>
      </Tooltip>
      <MonthPickerInput
        value={`${value}-01`}
        onChange={(v) => v && onChange(v.slice(0, 7))}
        valueFormat="MMMM YYYY"
        w={170}
        aria-label="Month"
      />
      <Tooltip label="Next month">
        <ActionIcon variant="default" size="lg" aria-label="Next month" onClick={() => onChange(shiftMonth(value, 1))}>
          <IconChevronRight size={18} />
        </ActionIcon>
      </Tooltip>
      {value !== thisMonth() && (
        <Button variant="subtle" size="xs" onClick={() => onChange(thisMonth())}>
          Today
        </Button>
      )}
    </Group>
  );
}

/**
 * A mutation that refreshes every query on success (tabs share data, e.g. holdings feed the
 * balance sheet) and shows errors as a notification.
 */
export function useAppMutation<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>, successMessage?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      queryClient.invalidateQueries();
      if (successMessage) notifications.show({ message: successMessage, color: 'green' });
    },
    onError: (error: Error) => notifications.show({ title: 'Something went wrong', message: error.message, color: 'red' }),
  });
}

export function confirmDelete(what: string, onConfirm: () => void, detail?: string) {
  modals.openConfirmModal({
    title: `Delete ${what}?`,
    children: <Text size="sm">{detail ?? 'This cannot be undone.'}</Text>,
    labels: { confirm: 'Delete', cancel: 'Cancel' },
    confirmProps: { color: 'red', variant: 'filled' },
    onConfirm,
  });
}
