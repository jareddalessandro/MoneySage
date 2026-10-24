import {
  ActionIcon,
  Button,
  Group,
  Menu,
  Modal,
  NumberInput,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { IconCheck, IconDots, IconExternalLink, IconPencil, IconPlus, IconTrash } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { useState } from 'react';

import { api } from '../api';
import { confirmDelete, EmptyState, PageHeader, StatCard, useAppMutation } from '../components/common';
import { money } from '../format';
import type { CreditCard, CreditCardInput } from '../types';

const MONTHS = Array.from({ length: 12 }, (_, i) => dayjs().month(i).format('MMMM'));

type Editing = { card: CreditCard | null } | null;

/** "chase.com" from "https://www.chase.com/pay", for the button label. */
function siteName(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

/** The card whose annual fee posts soonest, counting this month as the soonest. */
function nextFee(cards: CreditCard[]) {
  const now = dayjs().month() + 1;
  const upcoming = cards
    .filter((c) => c.annual_fee > 0 && c.annual_fee_month != null)
    .map((c) => ({ card: c, monthsAway: (c.annual_fee_month! - now + 12) % 12 }))
    .sort((a, b) => a.monthsAway - b.monthsAway);
  return upcoming[0] ?? null;
}

export default function CreditCardsPage() {
  const [editing, setEditing] = useState<Editing>(null);
  const { data: cards = [], isLoading } = useQuery({ queryKey: ['credit-cards'], queryFn: api.creditCards });
  const remove = useAppMutation((id: number) => api.deleteCreditCard(id), 'Card deleted');

  const totalFees = cards.reduce((s, c) => s + c.annual_fee, 0);
  const next = nextFee(cards);

  return (
    <>
      <PageHeader
        title="Credit Card Info"
        description="Where to pay each card, what it offers, and what it costs. Don't store card numbers or passwords here."
        actions={
          <Button leftSection={<IconPlus size={16} />} onClick={() => setEditing({ card: null })}>
            Add card
          </Button>
        }
      />

      {cards.length > 0 && (
        <SimpleGrid cols={{ base: 1, sm: 3 }} mb="xl">
          <StatCard label="Cards" value={cards.length} />
          <StatCard
            label="Annual fees"
            value={money(totalFees)}
            footer={totalFees > 0 ? `${money(totalFees / 12)} a month` : 'No annual fees'}
          />
          <StatCard
            label="Next annual fee"
            value={next ? MONTHS[next.card.annual_fee_month! - 1] : '—'}
            footer={
              next
                ? `${next.card.name} · ${money(next.card.annual_fee)}${next.monthsAway === 0 ? ' · this month' : ''}`
                : 'Add a fee month to a card to see it here'
            }
          />
        </SimpleGrid>
      )}

      {isLoading ? null : cards.length === 0 ? (
        <Paper p="1.1rem">
          <EmptyState
            message="Add your credit cards to keep their payment sites, benefits, and annual fees in one place."
            action={
              <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setEditing({ card: null })}>
                Add card
              </Button>
            }
          />
        </Paper>
      ) : (
        <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }} spacing="lg">
          {cards.map((card) => (
            <CardTile
              key={card.id}
              card={card}
              onEdit={() => setEditing({ card })}
              onDelete={() => confirmDelete(`"${card.name}"`, () => remove.mutate(card.id))}
            />
          ))}
        </SimpleGrid>
      )}

      <Modal
        opened={editing !== null}
        onClose={() => setEditing(null)}
        title={editing?.card ? 'Edit card' : 'Add card'}
        size="lg"
      >
        {editing && <CardForm key={editing.card?.id ?? 'new'} card={editing.card} onDone={() => setEditing(null)} />}
      </Modal>
    </>
  );
}

function CardTile({ card, onEdit, onDelete }: { card: CreditCard; onEdit: () => void; onDelete: () => void }) {
  return (
    <Paper p="1.1rem" h="100%">
      <Stack gap="md" h="100%">
        <Group justify="space-between" align="flex-start" wrap="nowrap">
          <div>
            <Text className="headline" fw={700} size="lg" lh={1.25}>
              {card.name}
            </Text>
            {card.issuer && (
              <Text size="sm" c="dimmed">
                {card.issuer}
              </Text>
            )}
          </div>
          <Menu position="bottom-end">
            <Menu.Target>
              <ActionIcon variant="subtle" color="gray" aria-label={`${card.name} actions`}>
                <IconDots size={16} />
              </ActionIcon>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item leftSection={<IconPencil size={14} />} onClick={onEdit}>
                Edit card
              </Menu.Item>
              <Menu.Item color="red" leftSection={<IconTrash size={14} />} onClick={onDelete}>
                Delete
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
        </Group>

        <div>
          <Text className="label-sm">Annual fee</Text>
          <Text size="sm" mt={4} className="num">
            {card.annual_fee > 0 ? (
              <>
                <Text span fw={600} inherit>
                  {money(card.annual_fee)}
                </Text>
                {card.annual_fee_month != null && ` · posts in ${MONTHS[card.annual_fee_month - 1]}`}
              </>
            ) : (
              'No annual fee'
            )}
          </Text>
        </div>

        {card.benefits.length > 0 && (
          <div>
            <Text className="label-sm">Benefits</Text>
            <Stack gap={6} mt={6}>
              {card.benefits.map((b, i) => (
                <Group key={i} gap={8} wrap="nowrap" align="flex-start">
                  <IconCheck size={14} stroke={2.2} color="var(--primary)" style={{ marginTop: 3, flexShrink: 0 }} aria-hidden />
                  <Text size="sm">{b}</Text>
                </Group>
              ))}
            </Stack>
          </div>
        )}

        {card.notes && (
          <Text size="sm" c="dimmed" style={{ whiteSpace: 'pre-line' }}>
            {card.notes}
          </Text>
        )}

        {card.payment_url && (
          <Button
            component="a"
            href={card.payment_url}
            target="_blank"
            rel="noopener noreferrer"
            variant="default"
            size="sm"
            mt="auto"
            fullWidth
            rightSection={<IconExternalLink size={14} />}
          >
            Pay at {siteName(card.payment_url)}
          </Button>
        )}
      </Stack>
    </Paper>
  );
}

function CardForm({ card, onDone }: { card: CreditCard | null; onDone: () => void }) {
  const form = useForm({
    initialValues: {
      name: card?.name ?? '',
      issuer: card?.issuer ?? '',
      payment_url: card?.payment_url ?? '',
      annual_fee: card?.annual_fee ?? (0 as number | ''),
      annual_fee_month: card?.annual_fee_month != null ? String(card.annual_fee_month) : (null as string | null),
      benefits: card?.benefits.join('\n') ?? '',
      notes: card?.notes ?? '',
    },
    validate: { name: (v) => (v.trim() ? null : 'Required') },
  });
  const save = useAppMutation(
    (body: CreditCardInput) => (card ? api.updateCreditCard(card.id, body) : api.createCreditCard(body)),
    card ? 'Card updated' : 'Card added',
  );
  const hasFee = typeof form.values.annual_fee === 'number' && form.values.annual_fee > 0;

  return (
    <form
      onSubmit={form.onSubmit((v) =>
        save.mutate(
          {
            name: v.name.trim(),
            issuer: v.issuer.trim() || null,
            payment_url: v.payment_url.trim() || null,
            annual_fee: v.annual_fee === '' ? 0 : v.annual_fee,
            annual_fee_month: hasFee && v.annual_fee_month ? Number(v.annual_fee_month) : null,
            benefits: v.benefits.split('\n').map((b) => b.trim()).filter(Boolean),
            notes: v.notes.trim() || null,
          },
          { onSuccess: onDone },
        ),
      )}
    >
      <Stack>
        <Group grow align="flex-start">
          <TextInput label="Card name" placeholder="Sapphire Preferred" data-autofocus {...form.getInputProps('name')} />
          <TextInput label="Issuer" placeholder="Chase" {...form.getInputProps('issuer')} />
        </Group>
        <TextInput
          label="Payment site"
          description="Where you log in to pay the bill"
          placeholder="chase.com"
          {...form.getInputProps('payment_url')}
        />
        <Group grow align="flex-start">
          <NumberInput
            label="Annual fee"
            prefix="$"
            decimalScale={2}
            thousandSeparator=","
            min={0}
            {...form.getInputProps('annual_fee')}
          />
          <Select
            label="Fee posts in"
            placeholder={hasFee ? 'Pick a month' : 'No fee'}
            data={MONTHS.map((m, i) => ({ value: String(i + 1), label: m }))}
            clearable
            disabled={!hasFee}
            {...form.getInputProps('annual_fee_month')}
          />
        </Group>
        <Textarea
          label="Benefits"
          description="One per line, e.g. 3x points on dining"
          autosize
          minRows={4}
          maxRows={12}
          {...form.getInputProps('benefits')}
        />
        <Textarea label="Notes" autosize minRows={2} maxRows={6} {...form.getInputProps('notes')} />
        <Group justify="flex-end">
          <Button variant="default" onClick={onDone}>
            Cancel
          </Button>
          <Button type="submit" loading={save.isPending}>
            {card ? 'Save' : 'Add card'}
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
