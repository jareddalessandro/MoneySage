import { ActionIcon, Badge, Button, Group, SimpleGrid, Stack, Switch, Text, TextInput, Tooltip } from '@mantine/core';
import { IconArchive, IconArchiveOff, IconCheck, IconPencil, IconPlus, IconTrash, IconX } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { api } from '../api';
import { CategoryColorPicker } from '../components/CategoryColor';
import { confirmDelete, PageHeader, SectionCard, useAppMutation } from '../components/common';
import type { Category, CategoryColor, CategoryKind } from '../types';

export default function SettingsPage() {
  const [showArchived, setShowArchived] = useState(false);
  const { data: categories = [] } = useQuery({
    queryKey: ['categories', 'all'],
    queryFn: () => api.categories(true),
  });

  return (
    <>
      <PageHeader
        title="Categories"
        description="Used by the Budget and Income Statement. Archive a category to hide it without losing history."
        actions={<Switch label="Show archived" checked={showArchived} onChange={(e) => setShowArchived(e.currentTarget.checked)} />}
      />
      <SimpleGrid cols={{ base: 1, md: 2 }}>
        {(['income', 'expense'] as const).map((kind) => (
          <CategoryList
            key={kind}
            kind={kind}
            categories={categories.filter((c) => c.kind === kind && (showArchived || !c.is_archived))}
          />
        ))}
      </SimpleGrid>
    </>
  );
}

function CategoryList({ kind, categories }: { kind: CategoryKind; categories: Category[] }) {
  const [name, setName] = useState('');
  const create = useAppMutation(
    (n: string) => api.createCategory({ name: n, kind }),
    'Category added',
  );

  const add = () => {
    if (!name.trim()) return;
    create.mutate(name.trim(), { onSuccess: () => setName('') });
  };

  return (
    <SectionCard title={kind === 'income' ? 'Income categories' : 'Expense categories'}>
      <Group gap="xs" mb="sm" wrap="nowrap">
        <TextInput
          placeholder="New category name"
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
          onKeyDown={(e) => e.key === 'Enter' && add()}
          style={{ flex: 1 }}
        />
        <Button leftSection={<IconPlus size={16} />} onClick={add} loading={create.isPending} disabled={!name.trim()}>
          Add
        </Button>
      </Group>
      <Stack gap={0}>
        {categories.map((c) => (
          <CategoryRow key={c.id} category={c} />
        ))}
      </Stack>
    </SectionCard>
  );
}

function CategoryRow({ category }: { category: Category }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(category.name);
  const update = useAppMutation((body: { name?: string; color?: CategoryColor; is_archived?: boolean }) =>
    api.updateCategory(category.id, body),
  );
  const remove = useAppMutation(() => api.deleteCategory(category.id), 'Category deleted');

  const rename = () =>
    update.mutate({ name: name.trim() }, { onSuccess: () => setEditing(false) });

  return (
    <Group
      justify="space-between"
      py={6}
      px="xs"
      wrap="nowrap"
      className="list-row"
    >
      {editing ? (
        <TextInput
          size="xs"
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') rename();
            if (e.key === 'Escape') setEditing(false);
          }}
          autoFocus
          style={{ flex: 1 }}
        />
      ) : (
        <Group gap={6}>
          <CategoryColorPicker value={category.color} onChange={(color) => update.mutate({ color })} />
          <Text size="sm" c={category.is_archived ? 'dimmed' : undefined}>
            {category.name}
          </Text>
          {category.is_archived && (
            <Badge size="xs" color="gray" variant="light">
              Archived
            </Badge>
          )}
        </Group>
      )}
      <Group gap={2} wrap="nowrap">
        {editing ? (
          <>
            <ActionIcon variant="subtle" aria-label="Save" onClick={rename} disabled={!name.trim()}>
              <IconCheck size={16} />
            </ActionIcon>
            <ActionIcon variant="subtle" color="gray" aria-label="Cancel" onClick={() => setEditing(false)}>
              <IconX size={16} />
            </ActionIcon>
          </>
        ) : (
          <>
            <Tooltip label="Rename">
              <ActionIcon
                variant="subtle"
                color="gray"
                aria-label="Rename"
                onClick={() => {
                  setName(category.name);
                  setEditing(true);
                }}
              >
                <IconPencil size={16} />
              </ActionIcon>
            </Tooltip>
            <Tooltip label={category.is_archived ? 'Unarchive' : 'Archive'}>
              <ActionIcon
                variant="subtle"
                color="gray"
                aria-label={category.is_archived ? 'Unarchive' : 'Archive'}
                onClick={() => update.mutate({ is_archived: !category.is_archived })}
              >
                {category.is_archived ? <IconArchiveOff size={16} /> : <IconArchive size={16} />}
              </ActionIcon>
            </Tooltip>
            <Tooltip label="Delete (only if unused)">
              <ActionIcon
                variant="subtle"
                color="red"
                aria-label="Delete"
                onClick={() => confirmDelete(`"${category.name}"`, () => remove.mutate(undefined))}
              >
                <IconTrash size={16} />
              </ActionIcon>
            </Tooltip>
          </>
        )}
      </Group>
    </Group>
  );
}
