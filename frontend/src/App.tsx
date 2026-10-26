import { AppShell, Burger, Group, NavLink, Text } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import {
  IconBriefcase,
  IconChartLine,
  IconCreditCard,
  IconReceipt2,
  IconScale,
  IconSettings,
  IconTargetArrow,
} from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { Fragment } from 'react';
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';

import { api } from './api';

import BalanceSheetPage from './pages/BalanceSheet';
import BudgetPage from './pages/Budget';
import CompaniesPage from './pages/Companies';
import CompanyPage from './pages/Company';
import CreditCardsPage from './pages/CreditCards';
import IncomeStatementPage from './pages/IncomeStatement';
import SettingsPage from './pages/Settings';
import StocksPage from './pages/Stocks';

const NAV = [
  { to: '/budget', label: 'Budget', icon: IconTargetArrow },
  { to: '/income-statement', label: 'Income Statement', icon: IconReceipt2 },
  { to: '/balance-sheet', label: 'Balance Sheet', icon: IconScale },
  { to: '/investments', label: 'Investments', icon: IconChartLine },
  { to: '/credit-cards', label: 'Credit Card Info', icon: IconCreditCard },
  { to: '/companies', label: 'Companies', icon: IconBriefcase },
  { to: '/settings', label: 'Categories', icon: IconSettings },
];

export default function App() {
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

function Logo() {
  return (
    <Text className="headline" fw={800} size="lg" lts="-0.01em">
      💰 MoneySage
    </Text>
  );
}
