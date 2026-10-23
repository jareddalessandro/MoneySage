import { ActionIcon, AppShell, Burger, Group, NavLink, Text, Tooltip, useMantineColorScheme } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import {
  IconChartLine,
  IconLayoutDashboard,
  IconMoon,
  IconReceipt2,
  IconScale,
  IconSettings,
  IconSun,
  IconTargetArrow,
} from '@tabler/icons-react';
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';

import BalanceSheetPage from './pages/BalanceSheet';
import BudgetPage from './pages/Budget';
import DashboardPage from './pages/Dashboard';
import IncomeStatementPage from './pages/IncomeStatement';
import SettingsPage from './pages/Settings';
import StocksPage from './pages/Stocks';

const NAV = [
  { to: '/', label: 'Dashboard', icon: IconLayoutDashboard },
  { to: '/budget', label: 'Budget', icon: IconTargetArrow },
  { to: '/income-statement', label: 'Income Statement', icon: IconReceipt2 },
  { to: '/balance-sheet', label: 'Balance Sheet', icon: IconScale },
  { to: '/stocks', label: 'Stocks', icon: IconChartLine },
  { to: '/settings', label: 'Categories', icon: IconSettings },
];

export default function App() {
  const [opened, { toggle, close }] = useDisclosure();
  const { pathname } = useLocation();
  const { colorScheme, setColorScheme } = useMantineColorScheme();
  const dark = colorScheme === 'dark';

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{ width: 230, breakpoint: 'sm', collapsed: { mobile: !opened } }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="sm">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <Text fw={700} size="lg">
              💰 MoneySage
            </Text>
          </Group>
          <Tooltip label={dark ? 'Light mode' : 'Dark mode'}>
            <ActionIcon
              variant="default"
              size="lg"
              aria-label="Toggle color scheme"
              onClick={() => setColorScheme(dark ? 'light' : 'dark')}
            >
              {dark ? <IconSun size={18} /> : <IconMoon size={18} />}
            </ActionIcon>
          </Tooltip>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="xs">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            component={Link}
            to={to}
            label={label}
            leftSection={<Icon size={18} stroke={1.6} />}
            active={to === '/' ? pathname === '/' : pathname.startsWith(to)}
            onClick={close}
          />
        ))}
      </AppShell.Navbar>

      <AppShell.Main>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/budget" element={<BudgetPage />} />
          <Route path="/income-statement" element={<IncomeStatementPage />} />
          <Route path="/balance-sheet" element={<BalanceSheetPage />} />
          <Route path="/stocks" element={<StocksPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell.Main>
    </AppShell>
  );
}
