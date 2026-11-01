import { ActionIcon, AppShell, Avatar, Burger, Center, Group, Loader, NavLink, ScrollArea, Text, Tooltip } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import {
  IconBriefcase,
  IconChartLine,
  IconCreditCard,
  IconDatabaseExport,
  IconLogout,
  IconReceipt2,
  IconScale,
  IconSettings,
  IconTargetArrow,
} from '@tabler/icons-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Fragment, useEffect, useState } from 'react';
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';

import { api, ApiError, SIGNED_OUT_EVENT } from './api';
import type { Me } from './types';

import BalanceSheetPage from './pages/BalanceSheet';
import BudgetPage from './pages/Budget';
import CompaniesPage from './pages/Companies';
import CompanyPage from './pages/Company';
import CreditCardsPage from './pages/CreditCards';
import DataPage from './pages/Data';
import IncomeStatementPage from './pages/IncomeStatement';
import SettingsPage from './pages/Settings';
import SignInPage from './pages/SignIn';
import StocksPage from './pages/Stocks';

const NAV = [
  { to: '/budget', label: 'Budget', icon: IconTargetArrow },
  { to: '/income-statement', label: 'Income Statement', icon: IconReceipt2 },
  { to: '/balance-sheet', label: 'Balance Sheet', icon: IconScale },
  { to: '/investments', label: 'Investments', icon: IconChartLine },
  { to: '/credit-cards', label: 'Credit Card Info', icon: IconCreditCard },
  { to: '/companies', label: 'Companies', icon: IconBriefcase },
  { to: '/settings', label: 'Categories', icon: IconSettings },
  { to: '/data', label: 'Export & import', icon: IconDatabaseExport },
];

export default function App() {
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: ['me'], queryFn: () => api.me(), retry: false });
  const signedOut = me.error instanceof ApiError && me.error.status === 401;

  // A request that finds the session gone (expired, or signed out in another tab) asks again who's here.
  useEffect(() => {
    const recheck = () => queryClient.invalidateQueries({ queryKey: ['me'] });
    window.addEventListener(SIGNED_OUT_EVENT, recheck);
    return () => window.removeEventListener(SIGNED_OUT_EVENT, recheck);
  }, [queryClient]);
  // Nothing from the last session stays in memory once it's over.
  useEffect(() => {
    if (signedOut) queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== 'me' });
  }, [signedOut, queryClient]);

  if (signedOut) return <SignInPage />;
  if (me.isPending) {
    return (
      <Center mih="100dvh">
        <Loader />
      </Center>
    );
  }
  // Any other error (say, the backend is restarting) still shows the app; its pages report their own errors.
  return <Shell me={me.data} />;
}

function Shell({ me }: { me: Me | undefined }) {
  const [opened, { toggle, close }] = useDisclosure();
  const { pathname } = useLocation();
  // Each company gets its own link under Companies.
  const { data: companies = [] } = useQuery({ queryKey: ['companies'], queryFn: () => api.companies() });

  return (
    <AppShell
      header={{ height: { base: 56, sm: 0 } }}
      navbar={{ width: 240, breakpoint: 'sm', collapsed: { mobile: !opened } }}
      padding={{ base: 'md', sm: 'xl' }}
    >
      {/* The header only carries the menu button on small screens; on desktop the logo lives in the sidebar. */}
      <AppShell.Header hiddenFrom="sm">
        <Group h="100%" px="md" gap="sm">
          <Burger opened={opened} onClick={toggle} size="sm" aria-label="Toggle navigation" />
          <Logo />
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="sm">
        <Group px="sm" py="md" mb="sm" visibleFrom="sm">
          <Logo />
        </Group>
        <AppShell.Section grow component={ScrollArea} type="scroll">
        {NAV.map(({ to, label, icon: Icon }) => (
          <Fragment key={to}>
            <NavLink
              component={Link}
              to={to}
              label={label}
              leftSection={<Icon size={18} stroke={1.6} />}
              active={to === '/companies' ? pathname === to : pathname.startsWith(to)}
              onClick={close}
              mb={4}
              style={{ borderRadius: 'var(--mantine-radius-md)' }}
            />
            {to === '/companies' &&
              companies.map((c) => (
                <NavLink
                  key={c.id}
                  component={Link}
                  to={`/companies/${c.id}`}
                  label={c.name}
                  active={pathname === `/companies/${c.id}`}
                  onClick={close}
                  mb={4}
                  pl={44}
                  py={6}
                  style={{ borderRadius: 'var(--mantine-radius-md)' }}
                  styles={{ label: { fontSize: 'var(--mantine-font-size-sm)', overflow: 'hidden', textOverflow: 'ellipsis' } }}
                />
              ))}
          </Fragment>
        ))}
        </AppShell.Section>
        {me?.auth_mode === 'google' && (
          <AppShell.Section pt="sm">
            <UserRow user={me.user} />
          </AppShell.Section>
        )}
      </AppShell.Navbar>

      <AppShell.Main>
        <Routes>
          <Route path="/" element={<Navigate to="/budget" replace />} />
          <Route path="/budget" element={<BudgetPage />} />
          <Route path="/income-statement" element={<IncomeStatementPage />} />
          <Route path="/balance-sheet" element={<BalanceSheetPage />} />
          <Route path="/investments" element={<StocksPage />} />
          {/* The tab used to be called Stocks; keep old links (and their ?account=) working. */}
          <Route path="/stocks" element={<StocksRedirect />} />
          <Route path="/credit-cards" element={<CreditCardsPage />} />
          <Route path="/companies" element={<CompaniesPage />} />
          <Route path="/companies/:id" element={<CompanyPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/data" element={<DataPage />} />
          <Route path="*" element={<Navigate to="/budget" replace />} />
        </Routes>
      </AppShell.Main>
    </AppShell>
  );
}

function StocksRedirect() {
  const { search } = useLocation();
  return <Navigate to={`/investments${search}`} replace />;
}

function UserRow({ user }: { user: Me['user'] }) {
  const [signingOut, setSigningOut] = useState(false);
  const signOut = async () => {
    setSigningOut(true);
    try {
      await api.signOut();
    } finally {
      // A full reload drops everything the app had loaded.
      window.location.assign('/');
    }
  };
  const label = user.name || user.email;

  return (
    <Group gap="sm" px="sm" py={6} wrap="nowrap" className="user-row">
      <Avatar src={user.picture_url} alt="" name={label} color="initials" size={32} imageProps={{ referrerPolicy: 'no-referrer' }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <Text size="sm" fw={600} truncate>
          {label}
        </Text>
        {user.name && (
          <Text size="xs" c="dimmed" truncate>
            {user.email}
          </Text>
        )}
      </div>
      <Tooltip label="Sign out">
        <ActionIcon variant="subtle" color="gray" onClick={signOut} loading={signingOut} aria-label="Sign out">
          <IconLogout size={18} stroke={1.6} />
        </ActionIcon>
      </Tooltip>
    </Group>
  );
}

function Logo() {
  return (
    <Text className="headline" fw={800} size="lg" lts="-0.01em">
      💰 MoneySage
    </Text>
  );
}
