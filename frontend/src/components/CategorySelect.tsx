import { Select, type SelectProps } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';

import { api } from '../api';
import type { CategoryKind } from '../types';

interface Props extends Omit<SelectProps, 'data' | 'value' | 'onChange'> {
  value?: number | null;
  onChange: (id: number | null) => void;
  kind?: CategoryKind;
}

/** Category picker grouped into Income / Expenses (or limited to one kind). */
export default function CategorySelect({ value, onChange, kind, ...props }: Props) {
  const { data: categories = [] } = useQuery({ queryKey: ['categories'], queryFn: () => api.categories() });

  const groups = (['income', 'expense'] as const)
    .filter((k) => !kind || k === kind)
    .map((k) => ({
      group: k === 'income' ? 'Income' : 'Expenses',
      items: categories.filter((c) => c.kind === k).map((c) => ({ value: String(c.id), label: c.name })),
    }));

  return (
    <Select
      label="Category"
      placeholder="Pick a category"
      searchable
      selectFirstOptionOnChange
      data={groups}
      value={value == null ? null : String(value)}
      onChange={(v) => onChange(v == null ? null : Number(v))}
      nothingFoundMessage="No matching category — add one under Categories"
      {...props}
    />
  );
}
