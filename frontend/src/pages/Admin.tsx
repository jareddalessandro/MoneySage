import { Avatar, Badge, Group, Pagination, SimpleGrid, Table, Text, TextInput, Tooltip } from '@mantine/core';
import { IconSearch } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import { useMemo, useState } from 'react';
import { Navigate } from 'react-router-dom';

import { api } from '../api';
import { EmptyState, PageHeader, SectionCard, StatCard } from '../components/common';
import { useMe } from '../components/Sharing';
import type { AdminUser } from '../types';

dayjs.extend(relativeTime);

const PAGE_SIZE = 25;

/** Who uses this install and when they last did. Account details only: nobody's finances. */
export default function AdminPage() {
  const me = useMe();
  if (me && !me.is_admin) return <Navigate to="/budget" replace />;
  return me ? <Overview /> : null;
}

function Overview() {
  const { data, isPending, error } = useQuery({ queryKey: ['admin'], queryFn: () => api.adminOverview() });
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);

  const users = useMemo(() => {
    const q = search.trim().toLowerCase();
    const all = data?.users ?? [];
    return q ? all.filter((u) => u.email.includes(q) || (u.name ?? '').toLowerCase().includes(q)) : all;
  }, [data, search]);
  const pages = Math.max(1, Math.ceil(users.length / PAGE_SIZE));
  const current = Math.min(page, pages);
  const shown = users.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE);

  const header = (
    <PageHeader
      title="Admin"
      description="Who has signed up and when they were last here. Account details only: nothing from anyone's households or companies."
    />
  );
  if (error) {
    return (
      <>
        {header}
        <Text c="red">{error.message}</Text>
      </>
    );
  }
  if (isPending) return header;
  const { stats } = data;

  return (
    <>
      {header}
      <SimpleGrid cols={{ base: 2, md: 4 }} spacing="lg" mb="xl">
        <StatCard
          label="Accounts"
          value={stats.users}
          footer={`${stats.onboarded} finished setup`}
        />
        <StatCard label="New in 30 days" value={stats.new_30d} footer={`${stats.new_7d} in the last 7 days`} />
        <StatCard
          label="Active in 30 days"
          value={stats.active_30d}
          footer={`${stats.active_7d} in the last 7 days`}
        />
        <StatCard
          label="Households"
          value={stats.households}
          footer={`${stats.companies} ${stats.companies === 1 ? 'company' : 'companies'}, ${stats.pending_invites} pending ${stats.pending_invites === 1 ? 'invite' : 'invites'}`}
        />
      </SimpleGrid>

      <SectionCard
        title="Accounts"
        actions={
          <TextInput
            placeholder="Search name or email"
            aria-label="Search accounts"
            leftSection={<IconSearch size={16} stroke={1.6} />}
            value={search}
            onChange={(e) => {
              setSearch(e.currentTarget.value);
              setPage(1);
            }}
            w={{ base: '100%', xs: 260 }}
          />
        }
      >
        {users.length === 0 ? (
          <EmptyState message={search ? 'No account matches that search.' : 'Nobody has signed up yet.'} />
        ) : (
          <>
            <Table.ScrollContainer minWidth={860} className="phone-fit">
              <Table highlightOnHover verticalSpacing="xs">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Person</Table.Th>
                    <Table.Th className="hide-xs">Signed up</Table.Th>
                    <Table.Th className="hide-xs">Last sign-in</Table.Th>
                    <Table.Th>Last active</Table.Th>
                    <Table.Th className="hide-xs">Status</Table.Th>
                    <Table.Th ta="right" className="hide-xs">
                      Sessions
                    </Table.Th>
                    <Table.Th ta="right" className="hide-xs">
                      Households
                    </Table.Th>
                    <Table.Th ta="right" className="hide-xs">
                      Companies
                    </Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {shown.map((u) => (
                    <UserRow key={u.id} user={u} />
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
            {pages > 1 && (
              <Group justify="flex-end" mt="md">
                <Pagination size="sm" total={pages} value={current} onChange={setPage} />
              </Group>
            )}
          </>
        )}
      </SectionCard>
    </>
  );
}

function UserRow({ user: u }: { user: AdminUser }) {
  const label = u.name || u.email;
  return (
    <Table.Tr>
      <Table.Td>
        <Group gap="sm" wrap="nowrap">
          <Avatar src={u.picture_url} alt="" name={label} color="initials" size={32} imageProps={{ referrerPolicy: 'no-referrer' }} />
          <div style={{ minWidth: 0 }}>
            <Text size="sm" fw={600}>
              {label}
            </Text>
            {u.name && (
              <Text size="xs" c="dimmed">
                {u.email}
              </Text>
            )}
            <Text size="xs" c="dimmed" className="show-xs" mt={2}>
              Signed up {dayjs(u.created_at).format('MMM D, YYYY')}
            </Text>
            <Group gap={6} className="show-xs" mt={4}>
              <StatusBadges user={u} />
            </Group>
          </div>
        </Group>
      </Table.Td>
      <Table.Td className="hide-xs num" style={{ whiteSpace: 'nowrap' }}>
        {dayjs(u.created_at).format('MMM D, YYYY')}
      </Table.Td>
      <Table.Td className="hide-xs" style={{ whiteSpace: 'nowrap' }}>
        <When at={u.last_login_at} />
      </Table.Td>
      <Table.Td style={{ whiteSpace: 'nowrap' }}>
        <When at={u.last_seen_at} />
      </Table.Td>
      <Table.Td className="hide-xs">
        <Group gap={6}>
          <StatusBadges user={u} />
        </Group>
      </Table.Td>
      <Table.Td ta="right" className="hide-xs num">
        {u.active_sessions}
      </Table.Td>
      <Table.Td ta="right" className="hide-xs num">
        {u.households}
      </Table.Td>
      <Table.Td ta="right" className="hide-xs num">
        {u.companies}
      </Table.Td>
    </Table.Tr>
  );
}

/** "3 days ago", with the exact time on hover. */
function When({ at }: { at: string | null }) {
  if (!at) {
    return (
      <Text span size="sm" c="dimmed">
        Never
      </Text>
    );
  }
  return (
    <Tooltip label={dayjs(at).format('MMM D, YYYY h:mm A')}>
      <Text span size="sm">
        {dayjs(at).fromNow()}
      </Text>
    </Tooltip>
  );
}

function StatusBadges({ user: u }: { user: AdminUser }) {
  return (
    <>
      {u.is_admin && <Badge variant="light">Admin</Badge>}
      {!u.onboarded && (
        <Badge variant="light" color="gray">
          Setup not finished
        </Badge>
      )}
      {u.onboarded && !u.terms_current && (
        <Badge variant="light" color="gray">
          Terms outdated
        </Badge>
      )}
    </>
  );
}
