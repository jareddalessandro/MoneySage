import { AppShell, Burger, Group, NavLink, Text } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import {
  IconChartLine,
  IconCreditCard,
  IconReceipt2,
  IconScale,
  IconSettings,
  IconTargetArrow,
} from '@tabler/icons-react';
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';

import BalanceSheetPage from './pages/BalanceSheet';
import BudgetPage from './pages/Budget';
import CreditCardsPage from './pages/CreditCards';
import IncomeStatementPage from './pages/IncomeStatement';
import SettingsPage from './pages/Settings';
import StocksPage from './pages/Stocks';

const NAV = [
  { to: '/budget', label: 'Budget', icon: IconTargetArrow },
  { to: '/income-statement', label: 'Income Statement', icon: IconReceipt2 },
  { to: '/balance-sheet', label: 'Balance Sheet', icon: IconScale },
  { to: '/stocks', label: 'Stocks', icon: IconChartLine },
  { to: '/credit-cards', label: 'Credit Card Info', icon: IconCreditCard },
  { to: '/settings', label: 'Categories', icon: IconSettings },
];

export default function App() {
  const [opened, { toggle, close }] = useDisclosure();
  const { pathname } = useLocation();

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
          <NavLink
            key={to}
            component={Link}
            to={to}
            label={label}
            leftSection={<Icon size={18} stroke={1.6} />}
            active={pathname.startsWith(to)}
            onClick={close}
            mb={4}
            style={{ borderRadius: 'var(--mantine-radius-md)' }}
          />
        ))}
      </AppShell.Navbar>

      <AppShell.Main>
        <Routes>
          <Route path="/" element={<Navigate to="/budget" replace />} />
          <Route path="/budget" element={<BudgetPage />} />
          <Route path="/income-statement" element={<IncomeStatementPage />} />
          <Route path="/balance-sheet" element={<BalanceSheetPage />} />
          <Route path="/stocks" element={<StocksPage />} />
          <Route path="/credit-cards" element={<CreditCardsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/budget" replace />} />
        </Routes>
      </AppShell.Main>
    </AppShell>
  );
}

function Logo() {
  return (
    <Text className="headline" fw={800} size="lg" lts="-0.01em">
      💰 MoneySage
    </Text>
  );
}
