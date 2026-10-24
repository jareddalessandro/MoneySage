import { Badge, Box, ColorSwatch, Group, Popover, SimpleGrid, Text, Tooltip, UnstyledButton } from '@mantine/core';
import { IconCheck } from '@tabler/icons-react';
import { type ReactNode, useState } from 'react';

import type { CategoryColor } from '../types';

/**
 * Category palette, in the validated order (adjacent hues stay distinct, incl. for color
 * blindness, on surface_container_high). Hexes live in styles.css as --cat-*. Eight hues can't
 * all be told apart pairwise, so wherever color identifies a category its name is shown too.
 */
export const CATEGORY_COLORS: { key: CategoryColor; label: string }[] = [
  { key: 'blue', label: 'Blue' },
  { key: 'orange', label: 'Orange' },
  { key: 'teal', label: 'Teal' },
  { key: 'violet', label: 'Violet' },
  { key: 'gold', label: 'Gold' },
  { key: 'pink', label: 'Pink' },
  { key: 'green', label: 'Green' },
  { key: 'plum', label: 'Plum' },
  { key: 'gray', label: 'Gray' },
];

export const categoryColor = (key: CategoryColor | undefined) => `var(--cat-${key ?? 'gray'})`;

export function CategoryDot({ color, size = 8 }: { color: CategoryColor; size?: number }) {
  return <Box w={size} h={size} style={{ borderRadius: '50%', background: categoryColor(color), flexShrink: 0 }} aria-hidden />;
}

/** Neutral badge with a colored dot: text stays in text color, the dot carries the category's color. */
export function CategoryBadge({ category }: { category: { name: string; color: CategoryColor } }) {
  return (
    <Badge variant="light" color="gray" fw={500} tt="none" leftSection={<CategoryDot color={category.color} size={7} />}>
      {category.name}
    </Badge>
  );
}

export function CategoryColorPicker({ value, onChange }: { value: CategoryColor; onChange: (color: CategoryColor) => void }) {
  const [opened, setOpened] = useState(false);
  const current = CATEGORY_COLORS.find((c) => c.key === value);
  return (
    <Popover opened={opened} onChange={setOpened} position="bottom-start" withArrow>
      <Popover.Target>
        <Tooltip label="Change color" disabled={opened}>
          <UnstyledButton
            onClick={() => setOpened((o) => !o)}
            aria-label={`Color: ${current?.label ?? value}. Change color`}
            p={4}
            style={{ borderRadius: 'var(--mantine-radius-sm)', display: 'flex' }}
            className="list-row"
          >
            <CategoryDot color={value} size={12} />
          </UnstyledButton>
        </Tooltip>
      </Popover.Target>
      <Popover.Dropdown p="xs">
        <Text className="label-sm" mb={6}>
          Color
        </Text>
        <SimpleGrid cols={5} spacing={6}>
          {CATEGORY_COLORS.map((c) => (
            <Tooltip key={c.key} label={c.label}>
              <ColorSwatch
                component="button"
                type="button"
                color={categoryColor(c.key)}
                size={22}
                aria-label={c.label}
                aria-pressed={c.key === value}
                onClick={() => {
                  onChange(c.key);
                  setOpened(false);
                }}
                style={{ cursor: 'pointer', color: 'var(--surface)' }}
              >
                {c.key === value && <IconCheck size={14} stroke={3} />}
              </ColorSwatch>
            </Tooltip>
          ))}
        </SimpleGrid>
      </Popover.Dropdown>
    </Popover>
  );
}

/** Legend row: dot, name, then right-aligned values. */
export function LegendRow({ color, label, children }: { color: CategoryColor; label: string; children: ReactNode }) {
  return (
    <Group justify="space-between" wrap="nowrap" gap="xs">
      <Group gap={8} wrap="nowrap" style={{ minWidth: 0 }}>
        <CategoryDot color={color} size={10} />
        <Text size="sm" truncate>
          {label}
        </Text>
      </Group>
      <Group gap="sm" wrap="nowrap">
        {children}
      </Group>
    </Group>
  );
}
