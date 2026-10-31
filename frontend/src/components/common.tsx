import {
  ActionIcon,
  Card,
  Group,
  Menu,
  Paper,
  SegmentedControl,
  Select,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
  UnstyledButton,
} from '@mantine/core';
import { MonthPickerInput } from '@mantine/dates';
import { useMediaQuery } from '@mantine/hooks';
import { modals } from '@mantine/modals';
import { notifications } from '@mantine/notifications';
import {
  IconArrowDownRight,
  IconArrowUpRight,
  IconChevronDown,
  IconChevronLeft,
  IconChevronRight,
  IconChevronUp,
  IconDots,
  IconSelector,
} from '@tabler/icons-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { shiftMonth, signedMoney } from '../format';

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <Group justify="space-between" align="flex-end" mb="xl" wrap="wrap" gap="sm">
      <div>
        <Title order={1} fz={{ base: '1.5rem', sm: '1.75rem' }} lts="-0.01em">
          {title}
        </Title>
        {description && (
          <Text component="div" c="dimmed" size="sm" mt={4}>
            {description}
          </Text>
        )}
      </div>
      {/* On phones the actions get their own full-width row, so buttons don't wrap one per line. */}
      {actions && (
        <Group gap="xs" w={{ base: '100%', sm: 'auto' }} className="page-actions">
          {actions}
        </Group>
      )}
    </Group>
  );
}

/** Up/down arrow + signed amount; `goodWhen` decides which direction is green. */
export function Delta({
  value,
  goodWhen = 'up',
  suffix,
  size = 'sm',
  format = signedMoney,
}: {
  value: number | null | undefined;
  goodWhen?: 'up' | 'down';
  suffix?: string;
  size?: 'xs' | 'sm' | 'md';
  /** Signed text for the value; money by default (signedPercent for a rate). */
  format?: (value: number) => string;
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
        {format(value)}
        {suffix ? ` ${suffix}` : ''}
      </Text>
    </Group>
  );
}

/** `compact` trims the padding and number size (not the footer, which stays readable), for a row that
    shares its width with other cards. */
export function StatCard({
  label,
  value,
  footer,
  compact,
}: {
  label: string;
  value: ReactNode;
  footer?: ReactNode;
  compact?: boolean;
}) {
  return (
    <Paper p={compact ? { base: '0.75rem', sm: '0.9rem' } : { base: '0.85rem', sm: '1.1rem' }} h="100%">
      <Text className="label-sm">{label}</Text>
      <Text
        className="headline num"
        fw={800}
        fz={compact ? { base: '1.2rem', sm: '1.45rem' } : { base: '1.3rem', sm: '1.75rem' }}
        mt={compact ? 4 : 6}
        lh={1.15}
      >
        {value}
      </Text>
      {footer && (
        <Text component="div" fz={{ base: 'xs', sm: 'sm' }} c="dimmed" mt={compact ? 6 : 8}>
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

/** `fill` stretches the card to its grid cell's height, so cards side by side line up. */
export function SectionCard({
  title,
  actions,
  fill,
  children,
}: {
  title: string;
  actions?: ReactNode;
  fill?: boolean;
  children: ReactNode;
}) {
  return (
    <Card p={{ base: '0.85rem', sm: '1.1rem' }} h={fill ? '100%' : undefined}>
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

export type SortDir = 'asc' | 'desc';

/** A table header that sorts its column when clicked; the arrow shows the active direction. */
export function SortableTh({
  label,
  active,
  dir,
  onSort,
  align = 'left',
  w,
  className,
}: {
  label: string;
  active: boolean;
  dir: SortDir;
  onSort: () => void;
  align?: 'left' | 'right';
  w?: number;
  className?: string;
}) {
  const Icon = !active ? IconSelector : dir === 'asc' ? IconChevronUp : IconChevronDown;
  return (
    <Table.Th ta={align} w={w} className={className} aria-sort={active ? (dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
      <UnstyledButton onClick={onSort} className="sort-button" data-active={active || undefined}>
        <Group gap={4} wrap="nowrap" justify={align === 'right' ? 'flex-end' : 'flex-start'}>
          <span>{label}</span>
          <Icon size={12} stroke={2} aria-hidden />
        </Group>
      </UnstyledButton>
    </Table.Th>
  );
}

/** A filter with a few options: segmented buttons, or a dropdown on phones where they wouldn't fit. */
export function FilterControl({
  label,
  value,
  onChange,
  data,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  data: { value: string; label: string }[];
}) {
  const phone = useMediaQuery('(max-width: 36em)');
  return phone ? (
    <Select
      w="100%"
      aria-label={label}
      data={data}
      value={value}
      onChange={(v) => v && onChange(v)}
      allowDeselect={false}
    />
  ) : (
    <SegmentedControl size="xs" aria-label={label} value={value} onChange={onChange} data={data} />
  );
}

export interface RowAction {
  label: string;
  icon: ReactNode;
  onClick: () => void;
  color?: string;
  disabled?: boolean;
  /** Desktop hover hint, when the icon alone isn't clear. */
  tooltip?: string;
}

/**
 * A row's actions (edit, delete, ...). Desktop shows small icon buttons; phones get one 44px "⋯" menu,
 * since small icons side by side are easy to mis-tap (and tapping delete instead of edit is costly).
 */
export function RowActions({ label, actions }: { label: string; actions: RowAction[] }) {
  const phone = useMediaQuery('(max-width: 36em)');
  if (phone) {
    return (
      <Group justify="flex-end" wrap="nowrap">
        <Menu position="bottom-end">
          <Menu.Target>
            <ActionIcon variant="subtle" color="gray" aria-label={label}>
              <IconDots size={18} />
            </ActionIcon>
          </Menu.Target>
          <Menu.Dropdown>
            {actions.map((a) => (
              <Menu.Item key={a.label} leftSection={a.icon} color={a.color} disabled={a.disabled} onClick={a.onClick}>
                {a.label}
              </Menu.Item>
            ))}
          </Menu.Dropdown>
        </Menu>
      </Group>
    );
  }
  return (
    <Group gap={4} wrap="nowrap" justify="flex-end">
      {actions.map((a) => {
        const button = (
          <ActionIcon
            key={a.label}
            variant="subtle"
            color={a.color ?? 'gray'}
            aria-label={a.label}
            disabled={a.disabled}
            onClick={a.onClick}
          >
            {a.icon}
          </ActionIcon>
        );
        return a.tooltip ? (
          <Tooltip key={a.label} label={a.tooltip}>
            {button}
          </Tooltip>
        ) : (
          button
        );
      })}
    </Group>
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
    <Group gap={4} wrap="nowrap" className="month-switcher">
      <Tooltip label="Previous month">
        <ActionIcon variant="default" size="lg" aria-label="Previous month" onClick={() => onChange(shiftMonth(value, -1))}>
          <IconChevronLeft size={18} />
        </ActionIcon>
      </Tooltip>
      <MonthPickerInput
        value={`${value}-01`}
        onChange={(v) => v && onChange(v.slice(0, 7))}
        valueFormat="MMMM YYYY"
        w={{ base: 'auto', xs: 170 }}
        miw={130}
        style={{ flex: '1 1 auto' }}
        aria-label="Month"
      />
      <Tooltip label="Next month">
        <ActionIcon variant="default" size="lg" aria-label="Next month" onClick={() => onChange(shiftMonth(value, 1))}>
          <IconChevronRight size={18} />
        </ActionIcon>
      </Tooltip>
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
