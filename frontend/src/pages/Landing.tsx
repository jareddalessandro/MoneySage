import { AreaChart } from '@mantine/charts';
import { Anchor, Box, Container, Group, Paper, SimpleGrid, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import {
  IconBriefcase,
  IconChartLine,
  IconFileInvoice,
  IconLock,
  IconReceipt2,
  IconScale,
  IconTargetArrow,
  IconUsers,
} from '@tabler/icons-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { GoogleSignInButton, SignInError } from '../components/SignIn';
import type { Site } from '../types';

const FEATURES = [
  {
    icon: IconTargetArrow,
    title: 'A budget that knows your paycheck',
    text: 'Plan income and spending as monthly amounts, and see where gross pay goes: retirement, taxes, insurance, take-home.',
  },
  {
    icon: IconFileInvoice,
    title: 'Import your bank statement',
    text: 'Upload a statement PDF and review each line before it lands. Tallyvio remembers how you categorized things last time.',
  },
  {
    icon: IconReceipt2,
    title: 'An income statement for every month',
    text: 'Budget vs. actual, the unexpected expenses you log on the go, and notes on what made the month different.',
  },
  {
    icon: IconScale,
    title: 'Net worth, month by month',
    text: 'Every account and debt on one balance sheet, with the trend of what you own minus what you owe.',
  },
  {
    icon: IconChartLine,
    title: 'Investments, valued daily',
    text: 'Stocks, ETFs, crypto and cash across accounts, with gains, allocation and prices refreshed every evening.',
  },
  {
    icon: IconBriefcase,
    title: 'Companies you own a piece of',
    text: "Income, expenses, each owner's capital, revenue-share agreements, and year-end statements as PDF or Excel.",
  },
];

// Illustrative only: the hero preview's numbers aren't anyone's real data.
const PREVIEW_TREND = [
  { month: 'Jun', value: 381200 },
  { month: 'Jul', value: 386900 },
  { month: 'Aug', value: 384100 },
  { month: 'Sep', value: 395600 },
  { month: 'Oct', value: 403900 },
  { month: 'Nov', value: 412380 },
];

export default function LandingPage({ site }: { site: Site | undefined }) {
  return (
    <Box>
      <Container size="lg" px="md">
        <Group justify="space-between" py="lg">
          <Text className="headline" fw={800} size="lg" lts="-0.01em">
            💰 Tallyvio
          </Text>
          <GoogleSignInButton size="sm" label="Sign in" />
        </Group>

        {/* Hero: the pitch and the way in, with a preview of the app beside it. */}
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing={48} py={{ base: 32, md: 72 }} style={{ alignItems: 'center' }}>
          <Stack gap="lg">
            <Text className="label-sm" c="var(--primary)">
              Family finances, kept together
            </Text>
            <Title order={1} fz={{ base: '2.25rem', sm: '3rem' }} lh={1.1} lts="-0.02em">
              See your whole financial picture, and share it with the people it belongs to.
            </Title>
            <Text size="lg" c="dimmed">
              Budget, income statement, balance sheet and investments in one place. Share your household with your
              family, and each business with its partners, separately.
            </Text>
            <SignInError />
            <Group gap="sm">
              <GoogleSignInButton size="md" label="Get started with Google" />
            </Group>
            <Text size="xs" c="dimmed">
              Free during early access. No bank logins: you upload statements, and we never ask for your bank
              password.
            </Text>
          </Stack>
          <Preview />
        </SimpleGrid>
      </Container>

      <Box bg="var(--surface-container-low)" py={{ base: 48, md: 80 }}>
        <Container size="lg" px="md">
          <SectionHeading eyebrow="What's inside" title="Everything a household's money touches" />
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="lg">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <Paper key={title} p="1.25rem" bg="var(--surface-container-high)">
                <ThemeIcon variant="light" size={40} radius="md" mb="md">
                  <Icon size={22} stroke={1.6} />
                </ThemeIcon>
                <Text fw={700} mb={6}>
                  {title}
                </Text>
                <Text size="sm" c="dimmed">
                  {text}
                </Text>
              </Paper>
            ))}
          </SimpleGrid>
        </Container>
      </Box>

      <Container size="lg" px="md" py={{ base: 48, md: 80 }}>
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing={48}>
          <div>
            <SectionHeading eyebrow="Sharing" title="Everyone sees exactly what they should" />
            <Stack gap="md">
              <Point icon={<IconUsers size={20} stroke={1.6} />} title="Your household, with your family">
                Invite your partner by their Google account. They can edit everything, or just look.
              </Point>
              <Point icon={<IconBriefcase size={20} stroke={1.6} />} title="Each company, with its owners">
                Share one business with the people who co-own it, without showing them your household.
              </Point>
              <Point icon={<IconLock size={20} stroke={1.6} />} title="Only you share what's yours">
                People you invite can't pass access on. You can change or remove anyone's access at any time.
              </Point>
            </Stack>
          </div>
          <div>
            <SectionHeading eyebrow="Privacy" title="Your data stays yours" />
            <Stack gap="md">
              <Point icon={<IconLock size={20} stroke={1.6} />} title="No ads, no selling, no bank logins">
                We don't sell your data or show you ads, and Tallyvio never connects to your bank. Statement PDFs are
                read and then discarded.
              </Point>
              <Point icon={<IconFileInvoice size={20} stroke={1.6} />} title="Take it with you">
                Export everything to a file whenever you like.
              </Point>
            </Stack>
          </div>
        </SimpleGrid>
      </Container>

      <Box bg="var(--surface-container-low)" py={{ base: 48, md: 72 }}>
        <Container size="sm" px="md">
          <Stack align="center" gap="md" ta="center">
            <Title order={2} fz={{ base: '1.75rem', sm: '2.25rem' }} lts="-0.01em">
              Start with your own private household
            </Title>
            <Text c="dimmed">It takes a minute. Nothing is shared until you share it.</Text>
            <GoogleSignInButton size="md" label="Get started with Google" />
          </Stack>
        </Container>
      </Box>

      <SiteFooter site={site} />
    </Box>
  );
}

function SectionHeading({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <Stack gap={6} mb="xl">
      <Text className="label-sm" c="var(--primary)">
        {eyebrow}
      </Text>
      <Title order={2} fz={{ base: '1.5rem', sm: '2rem' }} lts="-0.01em">
        {title}
      </Title>
    </Stack>
  );
}

function Point({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <Group gap="md" align="flex-start" wrap="nowrap">
      <ThemeIcon variant="light" size={36} radius="md" style={{ flexShrink: 0 }}>
        {icon}
      </ThemeIcon>
      <div>
        <Text fw={700}>{title}</Text>
        <Text size="sm" c="dimmed">
          {children}
        </Text>
      </div>
    </Group>
  );
}

/** A glimpse of the app with made-up figures. */
function Preview() {
  return (
    <Paper p="lg" bg="var(--surface-container-high)" aria-label="Example of the net worth view, with sample numbers">
      <Text className="label-sm">Net worth</Text>
      <Text className="headline" fw={800} fz="2.25rem" lh={1.2} mt={4}>
        $412,380
      </Text>
      <Text size="sm" className="delta-up" mb="md">
        ▲ +$8,480 vs. last month
      </Text>
      <AreaChart
        h={160}
        data={PREVIEW_TREND}
        dataKey="month"
        series={[{ name: 'value', label: 'Net worth', color: 'var(--trend)' }]}
        curveType="linear"
        fillOpacity={0.2}
        withDots={false}
        withTooltip={false}
        withYAxis={false}
        gridAxis="none"
        yAxisProps={{ domain: ['dataMin - 10000', 'dataMax + 5000'] }}
      />
      <SimpleGrid cols={2} spacing="sm" mt="md">
        <Paper p="sm" bg="var(--surface-container-highest)">
          <Text className="label-sm">Monthly surplus</Text>
          <Text className="headline" fw={800} size="lg">
            $1,240
          </Text>
        </Paper>
        <Paper p="sm" bg="var(--surface-container-highest)">
          <Text className="label-sm">Investments</Text>
          <Text className="headline" fw={800} size="lg">
            $268,900
          </Text>
        </Paper>
      </SimpleGrid>
      <Text size="xs" c="dimmed" mt="sm">
        Sample figures
      </Text>
    </Paper>
  );
}

/** Copyright and the legal links, shared by the landing and legal pages. */
export function SiteFooter({ site }: { site: Site | undefined }) {
  return (
    <Container size="lg" px="md" py="xl">
      <Group justify="space-between" gap="sm" wrap="wrap">
        <Text size="xs" c="dimmed">
          © {new Date().getFullYear()} {site?.operator_name ?? 'Tallyvio'}. Tallyvio isn't a bank or a financial
          adviser.
        </Text>
        <Group gap="lg">
          <Anchor component={Link} to="/privacy" size="xs" c="dimmed" className="hit-44">
            Privacy
          </Anchor>
          <Anchor component={Link} to="/terms" size="xs" c="dimmed" className="hit-44">
            Terms
          </Anchor>
          {site?.contact_email && (
            <Anchor href={`mailto:${site.contact_email}`} size="xs" c="dimmed" className="hit-44">
              Contact
            </Anchor>
          )}
        </Group>
      </Group>
    </Container>
  );
}
