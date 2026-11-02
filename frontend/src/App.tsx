import { ActionIcon, Alert, AppShell, Avatar, Burger, Center, Group, Loader, NavLink, ScrollArea, Select, Text, Tooltip } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import {
  IconBriefcase,
  IconChartLine,
  IconCreditCard,
  IconDatabaseExport,
  IconEye,
  IconLogout,
  IconReceipt2,
  IconScale,
  IconSettings,
  IconTargetArrow,
  IconUsers,
} from '@tabler/icons-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Fragment, useEffect, useState } from 'react';
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';

import { api, ApiError, currentHouseholdId, setHouseholdId, SIGNED_OUT_EVENT } from './api';
import { CanEditContext } from './components/common';
import { householdLabel, PendingInvites } from './components/Sharing';
import type { Me, Site } from './types';

import BalanceSheetPage from './pages/BalanceSheet';
import BudgetPage from './pages/Budget';
import CompaniesPage from './pages/Companies';
import CompanyPage from './pages/Company';
import CreditCardsPage from './pages/CreditCards';
import DataPage from './pages/Data';
import IncomeStatementPage from './pages/IncomeStatement';
import SettingsPage from './pages/Settings';
import LandingPage from './pages/Landing';
import { PrivacyPage, TermsPage } from './pages/Legal';
import OnboardingPage from './pages/Onboarding';
import SharingPage from './pages/Sharing';
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
  { to: '/sharing', label: 'Sharing', icon: IconUsers, accountsOnly: true },
];

export default function App() {
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: ['me'], queryFn: () => api.me(), retry: false });
  const { data: site } = useQuery({ queryKey: ['site'], queryFn: () => api.site(), staleTime: Infinity });
  const signedOut = me.error instanceof ApiError && me.error.status === 401;
  const { pathname } = useLocation();

  // A request that finds the session gone (expired, or signed out in another tab) asks again who's here.
  useEffect(() => {
    const recheck = () => queryClient.invalidateQueries({ queryKey: ['me'] });
    window.addEventListener(SIGNED_OUT_EVENT, recheck);
    return () => window.removeEventListener(SIGNED_OUT_EVENT, recheck);
  }, [queryClient]);
  // Nothing from the last session stays in memory once it's over.
  useEffect(() => {
    if (signedOut) queryClient.removeQueries({ predicate: (q) => !['me', 'site'].includes(q.queryKey[0] as string) });
  }, [signedOut, queryClient]);
  // A remembered household you no longer have access to (you left, or were removed): back to your own.
  const households = me.data?.households;
  useEffect(() => {
    const chosen = currentHouseholdId();
    if (households && chosen !== null && !households.some((h) => h.id === chosen)) {
      setHouseholdId(null);
      queryClient.invalidateQueries();
    }
  }, [households, queryClient]);

  // The legal pages are reachable signed out and during setup (its links open them in a new tab).
  const legal = pathname === '/privacy' || pathname === '/terms';
  const needsOnboarding = !!me.data && me.data.auth_mode === 'google' && (me.data.needs_setup || me.data.needs_terms);
  if ((signedOut || needsOnboarding) && legal) return <PublicLegal site={site} />;
  if (signedOut) return <LandingPage site={site} />;
  if (needsOnboarding) return <OnboardingPage me={me.data!} />;
  if (me.isPending) {
    return (
      <Center mih="100dvh">
        <Loader />
      </Center>
    );
  }
  // Any other error (say, the backend is restarting) still shows the app; its pages report their own errors.
  return <Shell me={me.data} site={site} />;
}

function PublicLegal({ site }: { site: Site | undefined }) {
  return (
    <Routes>
      <Route path="/privacy" element={<PrivacyPage site={site} />} />
      <Route path="/terms" element={<TermsPage site={site} />} />
    </Routes>
  );
}

function Shell({ me, site }: { me: Me | undefined; site: Site | undefined }) {
  const [opened, { toggle, close }] = useDisclosure();
  const { pathname } = useLocation();
  // Each company gets its own link under Companies.
  const { data: companies = [] } = useQuery({ queryKey: ['companies'], queryFn: () => api.companies() });
  const accounts = me?.auth_mode === 'google';
  const household = me?.households.find((h) => h.id === currentHouseholdId()) ?? me?.households[0];
  const companyId = /^\/companies\/(\d+)/.exec(pathname)?.[1];
  const viewOnly = companyId
    ? companies.find((c) => c.id === Number(companyId))?.role === 'viewer'
    : !['/companies', '/sharing', '/privacy', '/terms'].includes(pathname) && household?.role === 'viewer';

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
        {me && me.households.length > 1 && <HouseholdSwitcher households={me.households} current={household?.id} />}
        <AppShell.Section grow component={ScrollArea} type="scroll">
        {NAV.filter((item) => accounts || !item.accountsOnly).map(({ to, label, icon: Icon }) => (
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
                  rightSection={
                    c.role !== 'owner' && (
                      <Tooltip label={c.role === 'viewer' ? 'Shared with you, view only' : 'Shared with you'}>
                        {c.role === 'viewer' ? <IconEye size={14} stroke={1.6} /> : <IconUsers size={14} stroke={1.6} />}
                      </Tooltip>
                    )
                  }
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
            <Group gap="md" px="sm" pt={6}>
              <Text component={Link} to="/privacy" size="xs" c="dimmed" onClick={close} className="hit-44">
                Privacy
              </Text>
              <Text component={Link} to="/terms" size="xs" c="dimmed" onClick={close} className="hit-44">
                Terms
              </Text>
            </Group>
          </AppShell.Section>
        )}
      </AppShell.Navbar>

      <AppShell.Main>
        {accounts && pathname !== '/sharing' && <PendingInvites />}
        {viewOnly && (
          <Alert variant="light" color="gray" icon={<IconEye size={18} />} mb="xl">
            You have view-only access {companyId ? 'to this company' : `to ${household ? householdLabel(household) : 'this household'}`}:
            you can look around, but not change anything.
          </Alert>
        )}
        <CanEditContext.Provider value={!viewOnly}>
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
          <Route path="/sharing" element={<SharingPage />} />
          <Route path="/privacy" element={<PrivacyPage site={site} signedIn />} />
          <Route path="/terms" element={<TermsPage site={site} signedIn />} />
          <Route path="*" element={<Navigate to="/budget" replace />} />
        </Routes>
        </CanEditContext.Provider>
      </AppShell.Main>
    </AppShell>
  );
}

function StocksRedirect() {
  const { search } = useLocation();
  return <Navigate to={`/investments${search}`} replace />;
}

/** Which household the app shows: your own, or one shared with you. */
function HouseholdSwitcher({ households, current }: { households: Me['households']; current: number | undefined }) {
  const queryClient = useQueryClient();
  return (
    <Select
      aria-label="Household"
      mx="sm"
      mb="md"
      data={households.map((h) => ({
        value: String(h.id),
        label: householdLabel(h) + (h.role === 'viewer' ? ' (view only)' : ''),
      }))}
      value={current === undefined ? null : String(current)}
      allowDeselect={false}
      comboboxProps={{ width: 280, position: 'bottom-start' }}
      leftSection={<IconUsers size={16} stroke={1.6} />}
      onChange={(value) => {
        if (!value) return;
        const id = Number(value);
        // Your own household is the backend's default, so it needs no header.
        setHouseholdId(households[0]?.role === 'owner' && households[0].id === id ? null : id);
        queryClient.invalidateQueries();
      }}
    />
  );
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
      💰 Tallyvio
    </Text>
  );
}
