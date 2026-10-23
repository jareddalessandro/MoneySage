import { AreaChart, BarChart } from '@mantine/charts';
import { Anchor, Grid, Group, Progress, SimpleGrid, Stack, Text } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

import { api } from '../api';
import { Delta, EmptyState, HeroStat, PageHeader, SectionCard, StatCard } from '../components/common';
import { money, moneyCompact, monthLabel, monthShort, SERIES_ORDER } from '../format';

export default function DashboardPage() {
  const { data: d } = useQuery({ queryKey: ['dashboard'], queryFn: api.dashboard });
  const { data: netWorth = [] } = useQuery({ queryKey: ['net-worth-trend'], queryFn: () => api.netWorthTrend(36) });
  const { data: trend = [] } = useQuery({ queryKey: ['income-trend'], queryFn: () => api.incomeTrend(12) });

  const netWorthData = netWorth.map((p) => ({ month: monthShort(p.month), 'Net worth': p.net_worth }));
  const trendData = trend.map((p) => ({ month: monthShort(p.month), Income: p.income, Expenses: p.expenses }));
  const hasTrend = trend.some((p) => p.income || p.expenses);
  const spentRatio = d && d.budget_monthly_expenses > 0 ? d.month_expenses / d.budget_monthly_expenses : null;

  return (
    <>
      <PageHeader title="Dashboard" description={d ? `Family finances at a glance · ${monthLabel(d.month)}` : undefined} />

      <Grid gutter="lg" mb="xl">
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <HeroStat
            label="Net worth"
            value={money(d?.net_worth)}
            footer={
              d?.net_worth == null ? (
                <Anchor component={Link} to="/balance-sheet" size="sm">
                  Add balances →
                </Anchor>
              ) : d.net_worth_change != null ? (
                <Delta value={d.net_worth_change} suffix="vs. prior month" />
              ) : (
                `as of ${monthLabel(d.net_worth_month!)}`
              )
            }
          />
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <SimpleGrid cols={{ base: 1, xs: 3 }} h="100%">
            <StatCard
              label="Net this month"
              value={<span className={d && d.month_net < 0 ? 'delta-down' : undefined}>{money(d?.month_net)}</span>}
              footer={d && `${money(d.month_income)} in · ${money(d.month_expenses)} out`}
            />
            <StatCard
              label="Investments"
              value={money(d?.portfolio_value)}
              footer={d && d.portfolio_value > 0 ? <Delta value={d.portfolio_day_change} suffix="today" /> : undefined}
            />
            <StatCard
              label="Planned monthly surplus"
              value={money(d ? d.budget_monthly_income - d.budget_monthly_expenses : null)}
              footer={d && `${money(d.budget_monthly_income)} income · ${money(d.budget_monthly_expenses)} expenses`}
            />
          </SimpleGrid>
        </Grid.Col>
      </Grid>

      <Grid gutter="lg">
        <Grid.Col span={{ base: 12, lg: 8 }}>
          <Stack gap="lg">
            <SectionCard title="Net worth">
              {netWorthData.length < 2 ? (
                <EmptyState message="Record balances on the Balance Sheet for two or more months to see your net worth trend." />
              ) : (
                <AreaChart
                  h={240}
                  data={netWorthData}
                  dataKey="month"
                  series={[{ name: 'Net worth', color: 'var(--trend)' }]}
                  curveType="monotone"
                  strokeWidth={2}
                  fillOpacity={0.2}
                  withDots={false}
                  valueFormatter={(v) => money(v)}
                  yAxisProps={{ tickFormatter: (v: number) => moneyCompact(v), width: 70 }}
                  gridAxis="x"
                  strokeDasharray="0"
                />
              )}
            </SectionCard>
            <SectionCard title="Income vs. expenses · last 12 months">
              {hasTrend ? (
                <BarChart
                  h={240}
                  data={trendData}
                  dataKey="month"
                  series={[
                    { name: 'Income', color: 'var(--series-1)' },
                    { name: 'Expenses', color: 'var(--series-2)' },
                  ]}
                  withLegend
                  legendProps={{ verticalAlign: 'top', height: 36, itemSorter: SERIES_ORDER }}
                  valueFormatter={(v) => money(v)}
                  yAxisProps={{ tickFormatter: (v: number) => moneyCompact(v), width: 70 }}
                  gridAxis="x"
                  strokeDasharray="0"
                  barProps={{ radius: [4, 4, 0, 0] }}
                  barChartProps={{ barGap: 2 }}
                  maxBarWidth={24}
                />
              ) : (
                <EmptyState message="Add transactions on the Income Statement to see monthly income and spending." />
              )}
            </SectionCard>
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 4 }}>
          <SectionCard title="This month's spending">
            {d && spentRatio != null ? (
              <Stack gap="xs">
                <Group justify="space-between">
                  <Text size="sm">
                    {money(d.month_expenses)} of {money(d.budget_monthly_expenses)}
                  </Text>
                  <Text size="sm" c="dimmed" className="num">
                    {Math.round(spentRatio * 100)}%
                  </Text>
                </Group>
                <Progress
                  value={Math.min(spentRatio, 1) * 100}
                  color={spentRatio > 1 ? 'var(--delta-down)' : 'sky'}
                  size="lg"
                  aria-label="Share of monthly expense budget spent"
                />
                <Text size="sm" c="dimmed">
                  {spentRatio > 1
                    ? `Over budget by ${money(d.month_expenses - d.budget_monthly_expenses)}`
                    : `${money(d.budget_monthly_expenses - d.month_expenses)} left in the budget`}
                </Text>
                {d.month_unexpected_expenses > 0 && (
                  <Text size="sm">
                    Includes {money(d.month_unexpected_expenses)} in unexpected expenses.
                  </Text>
                )}
                <Anchor component={Link} to="/income-statement" size="sm">
                  View income statement →
                </Anchor>
              </Stack>
            ) : (
              <EmptyState
                message="Set up a budget to track spending against it."
                action={
                  <Anchor component={Link} to="/budget" size="sm">
                    Go to Budget →
                  </Anchor>
                }
              />
            )}
          </SectionCard>
        </Grid.Col>
      </Grid>
    </>
  );
}
