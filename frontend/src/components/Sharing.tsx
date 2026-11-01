import { ActionIcon, Alert, Avatar, Badge, Button, Group, Select, Stack, Text, TextInput, Tooltip } from '@mantine/core';
import { modals } from '@mantine/modals';
import { notifications } from '@mantine/notifications';
import { IconMailForward, IconUserMinus, IconX } from '@tabler/icons-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';

import { api, setHouseholdId, type AccessTarget } from '../api';
import type { AccessRole, Me, MyInvite } from '../types';
import { SectionCard, useAppMutation } from './common';

export const ROLE_LABELS: Record<AccessRole, string> = { owner: 'Owner', editor: 'Editor', viewer: 'View only' };
const ROLE_OPTIONS = [
  { value: 'editor', label: 'Editor' },
  { value: 'viewer', label: 'View only' },
];
type ShareRole = 'editor' | 'viewer';

/** The signed-in user, from the query App already runs. */
export function useMe() {
  return useQuery({ queryKey: ['me'], queryFn: () => api.me(), retry: false }).data;
}

/** How a household reads in lists: "Your household", "Pat's household", or its own name. */
export function householdLabel(h: Me['households'][number]) {
  if (h.name !== 'Household') return h.name;
  return h.role === 'owner' ? 'Your household' : `${h.owner_name ?? 'Someone'}'s household`;
}

function PersonLine({ name, email, picture, extra }: { name: string | null; email: string; picture?: string | null; extra?: string }) {
  return (
    <Group gap="sm" wrap="nowrap" style={{ minWidth: 0, flex: 1 }}>
      <Avatar src={picture} name={name || email} color="initials" size={32} imageProps={{ referrerPolicy: 'no-referrer' }} />
      <div style={{ minWidth: 0 }}>
        <Text size="sm" fw={600} truncate>
          {name || email}
          {extra && (
            <Text span size="xs" c="dimmed" fw={400}>
              {' '}
              · {extra}
            </Text>
          )}
        </Text>
        {name && (
          <Text size="xs" c="dimmed" truncate>
            {email}
          </Text>
        )}
      </div>
    </Group>
  );
}

/**
 * Who can open a household or company: the owner manages people and invites; everyone else sees the list
 * and can leave.
 */
export function AccessCard({
  target,
  title,
  onLeave,
  leaveLabel,
}: {
  target: AccessTarget;
  title: string;
  /** Leave this household or company (for people who don't own it). */
  onLeave?: () => Promise<void>;
  leaveLabel?: string;
}) {
  const { data } = useQuery({ queryKey: ['access', target], queryFn: () => api.access(target) });
  const setRole = useAppMutation(({ userId, role }: { userId: number; role: ShareRole }) => api.setRole(target, userId, role));
  const remove = useAppMutation((userId: number) => api.removeAccess(target, userId), 'Removed');
  const revoke = useAppMutation((inviteId: number) => api.revokeInvite(target, inviteId), 'Invite withdrawn');

  const confirmRemove = (userId: number, who: string) =>
    modals.openConfirmModal({
      title: `Remove ${who}?`,
      children: <Text size="sm">They lose access right away. You can invite them again later.</Text>,
      labels: { confirm: 'Remove', cancel: 'Cancel' },
      confirmProps: { color: 'red', variant: 'filled' },
      onConfirm: () => remove.mutate(userId),
    });

  return (
    <SectionCard title={title}>
      <Stack gap="lg">
        <Stack gap={4}>
          {data?.people.map((p) => (
            <Group key={p.user_id} className="list-row" justify="space-between" wrap="nowrap" gap="sm" px="xs" py={6}>
              <PersonLine name={p.name} email={p.email} picture={p.picture_url} extra={p.is_you ? 'you' : undefined} />
              {data.can_manage && p.role !== 'owner' ? (
                <Group gap="xs" wrap="nowrap">
                  <Select
                    aria-label={`Access for ${p.name || p.email}`}
                    w={130}
                    data={ROLE_OPTIONS}
                    value={p.role}
                    allowDeselect={false}
                    onChange={(v) => v && setRole.mutate({ userId: p.user_id, role: v as ShareRole })}
                  />
                  <Tooltip label="Remove">
                    <ActionIcon variant="subtle" color="gray" aria-label="Remove" onClick={() => confirmRemove(p.user_id, p.name || p.email)}>
                      <IconUserMinus size={18} stroke={1.6} />
                    </ActionIcon>
                  </Tooltip>
                </Group>
              ) : (
                <Badge variant="light" color={p.role === 'owner' ? 'cyan' : 'gray'}>
                  {ROLE_LABELS[p.role]}
                </Badge>
              )}
            </Group>
          ))}
          {data?.invites.map((i) => (
            <Group key={`invite-${i.id}`} className="list-row" justify="space-between" wrap="nowrap" gap="sm" px="xs" py={6}>
              <PersonLine name={null} email={i.email} extra={`invited as ${ROLE_LABELS[i.role].toLowerCase()}`} />
              <Tooltip label="Withdraw invite">
                <ActionIcon variant="subtle" color="gray" aria-label="Withdraw invite" onClick={() => revoke.mutate(i.id)}>
                  <IconX size={18} stroke={1.6} />
                </ActionIcon>
              </Tooltip>
            </Group>
          ))}
        </Stack>
        {data?.can_manage && <InviteForm target={target} />}
        {data && !data.can_manage && onLeave && (
          <Button
            variant="default"
            color="red"
            style={{ alignSelf: 'flex-start' }}
            onClick={() =>
              modals.openConfirmModal({
                title: `${leaveLabel ?? 'Leave'}?`,
                children: <Text size="sm">You lose access until the owner invites you again.</Text>,
                labels: { confirm: 'Leave', cancel: 'Cancel' },
                confirmProps: { color: 'red', variant: 'filled' },
                onConfirm: () =>
                  onLeave().catch((error: Error) =>
                    notifications.show({ title: 'Something went wrong', message: error.message, color: 'red' }),
                  ),
              })
            }
          >
            {leaveLabel ?? 'Leave'}
          </Button>
        )}
      </Stack>
    </SectionCard>
  );
}

function InviteForm({ target }: { target: AccessTarget }) {
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<ShareRole>('editor');
  const [sentTo, setSentTo] = useState<string | null>(null);
  const invite = useAppMutation((body: { email: string; role: ShareRole }) => api.invite(target, body));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const address = email.trim();
    if (!address) return;
    invite.mutate({ email: address, role }, {
      onSuccess: () => {
        setSentTo(address);
        setEmail('');
      },
    });
  };

  return (
    <Stack gap="sm">
      <form onSubmit={submit}>
        <Group gap="sm" align="flex-end" wrap="wrap">
          <TextInput
            label="Invite by email"
            placeholder="Their Google account's address"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.currentTarget.value)}
            style={{ flex: '1 1 220px' }}
          />
          <Select label="Access" w={140} data={ROLE_OPTIONS} value={role} allowDeselect={false} onChange={(v) => v && setRole(v as ShareRole)} />
          <Button type="submit" leftSection={<IconMailForward size={16} />} loading={invite.isPending}>
            Invite
          </Button>
        </Group>
      </form>
      <Text size="xs" c="dimmed">
        Editors can change anything here but can't share it. View only can look but not change anything.
      </Text>
      {sentTo && (
        <Alert variant="light" color="cyan" withCloseButton onClose={() => setSentTo(null)}>
          Invited {sentTo}. MoneySage doesn't send email, so let them know: they sign in at {window.location.origin} with
          that Google account and accept.
        </Alert>
      )}
    </Stack>
  );
}

/** Invites waiting for you, with Accept and Decline. Renders nothing when there are none. */
export function PendingInvites() {
  const queryClient = useQueryClient();
  const { data: invites = [] } = useQuery({ queryKey: ['invites'], queryFn: () => api.myInvites() });
  const [busy, setBusy] = useState<number | null>(null);

  const answer = async (invite: MyInvite, accept: boolean) => {
    setBusy(invite.id);
    try {
      if (accept) {
        const accepted = await api.acceptInvite(invite.id);
        // Go straight to a household you just joined.
        if (accepted.kind === 'household') setHouseholdId(accepted.id);
        notifications.show({ message: `You can now open ${invite.name}`, color: 'green' });
      } else {
        await api.declineInvite(invite.id);
      }
      await queryClient.invalidateQueries();
    } catch (error) {
      notifications.show({ title: 'Something went wrong', message: (error as Error).message, color: 'red' });
    } finally {
      setBusy(null);
    }
  };

  if (!invites.length) return null;
  return (
    <Stack gap="sm" mb="xl">
      {invites.map((i) => (
        <Alert key={i.id} variant="light" color="cyan" icon={<IconMailForward size={18} />}>
          <Group justify="space-between" gap="sm" wrap="wrap">
            <Text size="sm">
              {i.invited_by ?? 'Someone'} invited you to {i.kind === 'company' && 'the company '}
              <b>{i.name}</b> ({ROLE_LABELS[i.role].toLowerCase()}).
            </Text>
            <Group gap="xs">
              <Button size="xs" onClick={() => answer(i, true)} loading={busy === i.id}>
                Accept
              </Button>
              <Button size="xs" variant="default" onClick={() => answer(i, false)} disabled={busy === i.id}>
                Decline
              </Button>
            </Group>
          </Group>
        </Alert>
      ))}
    </Stack>
  );
}
