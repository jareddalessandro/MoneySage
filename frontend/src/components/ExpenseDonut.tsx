import { DonutChart } from '@mantine/charts';
import { Box, Group, Stack, Text } from '@mantine/core';

import { money, percent } from '../format';
import type { CategoryColor } from '../types';
import { categoryColor, LegendRow } from './CategoryColor';

interface Slice {
  name: string;
  color: CategoryColor;
  amount: number;
}

// Beyond this many slices a donut stops being readable; the smallest fold into "Other".
const MAX_SLICES = 8;

/** Expenses by category: donut with the total in the middle (over `caption`) and a labeled legend. */
export function ExpenseDonut({ categories, caption = 'per month' }: { categories: Slice[]; caption?: string }) {
  const sorted = [...categories].sort((a, b) => b.amount - a.amount);
  const slices: Slice[] =
    sorted.length <= MAX_SLICES
      ? sorted
      : [
          ...sorted.slice(0, MAX_SLICES - 1),
          {
            name: `Other (${sorted.length - MAX_SLICES + 1} categories)`,
            color: 'gray',
            amount: sorted.slice(MAX_SLICES - 1).reduce((s, c) => s + c.amount, 0),
          },
        ];
  const total = slices.reduce((s, c) => s + c.amount, 0);

  return (
    <Group align="center" gap="lg" wrap="wrap" justify="center">
      <Box pos="relative" w={190} h={190}>
        {/* Rendered before the chart so the hover tooltip paints over it, not under it. */}
        <Stack gap={0} align="center" justify="center" pos="absolute" inset={0} style={{ pointerEvents: 'none' }}>
          <Text className="headline num" fw={800} size="lg">
            {money(total)}
          </Text>
          <Text size="xs" c="dimmed">
            {caption}
          </Text>
        </Stack>
        <DonutChart
          size={190}
          thickness={24}
          // Clockwise from 12 o'clock, largest first, with a 2px surface gap between slices.
          startAngle={90}
          endAngle={-270}
          paddingAngle={slices.length > 1 ? 2 : 0}
          strokeWidth={0}
          data={slices.map((s) => ({ name: s.name, value: s.amount, color: categoryColor(s.color) }))}
          tooltipDataSource="segment"
          valueFormatter={(v) => `${money(v)} · ${percent(v / total)}`}
        />
      </Box>
      <Stack gap={6} style={{ flex: '1 1 200px', minWidth: 0 }}>
        {slices.map((s) => (
          <LegendRow key={s.name} color={s.color} label={s.name}>
            <Text size="sm" className="num">
              {money(s.amount)}
            </Text>
            <Text size="xs" c="dimmed" className="num" w={44} ta="right">
              {percent(s.amount / total)}
            </Text>
          </LegendRow>
        ))}
      </Stack>
    </Group>
  );
}
