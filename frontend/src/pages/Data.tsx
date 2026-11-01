import { Button, FileButton, Group, List, SimpleGrid, Stack, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconDownload, IconFileUpload, IconX } from '@tabler/icons-react';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { api, currentHouseholdId } from '../api';
import { PageHeader, SectionCard, useAppMutation } from '../components/common';
import { useMe } from '../components/Sharing';
import type { ImportResult } from '../types';

function plural(n: number, word: string) {
  return `${n.toLocaleString()} ${word}${n === 1 ? '' : 's'}`;
}

function describe(result: ImportResult) {
  const parts = [];
  if (result.household) {
    parts.push(`Household with ${plural(result.transactions, 'transaction')} and ${plural(result.holdings, 'holding')}`);
  }
  if (result.companies.length) parts.push(`${result.companies.join(', ')}`);
  return parts.join('. ') || 'The file was empty.';
}

export default function DataPage() {
  return (
    <>
      <PageHeader
        title="Export & import"
        description="Download a copy of your data, or bring in a file exported from another Tallyvio, such as an offline install."
      />
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
        <ExportCard />
        <ImportCard />
      </SimpleGrid>
    </>
  );
}

function ExportCard() {
  const [busy, setBusy] = useState(false);
  const download = async () => {
    setBusy(true);
    try {
      await api.downloadExport();
    } catch (error) {
      notifications.show({ title: 'Something went wrong', message: (error as Error).message, color: 'red' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <SectionCard title="Export" fill>
      <Stack gap="md" align="flex-start">
        <Text size="sm">
          One file with this household (budget, income statement, balance sheet, investments, credit cards and
          categories) and every company you own.
        </Text>
        <Button leftSection={<IconDownload size={16} />} onClick={download} loading={busy}>
          Download export
        </Button>
        <Text size="xs" c="dimmed">
          The file isn't encrypted and holds all of your financial details. Keep it somewhere private, and delete it
          once you've moved it.
        </Text>
      </Stack>
    </SectionCard>
  );
}

function ImportCard() {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const importFile = useAppMutation((f: File) => api.importExport(f));
  const me = useMe();
  const household = me?.households.find((h) => h.id === currentHouseholdId()) ?? me?.households[0];
  const ownHousehold = !household || household.role === 'owner';

  const run = () => {
    if (!file) return;
    importFile.mutate(file, {
      onSuccess: (result) => {
        setFile(null);
        notifications.show({ title: 'Imported', message: describe(result), color: 'green' });
        // Prices aren't part of the file; load them for the imported holdings.
        if (result.holdings) api.refreshPrices().then(() => queryClient.invalidateQueries(), () => undefined);
      },
    });
  };

  return (
    <SectionCard title="Import" fill>
      <Stack gap="md">
        <List size="sm" spacing={4}>
          <List.Item>Its household goes into this one, which must be empty (only the starting categories).</List.Item>
          <List.Item>Each company is added as a new company you own.</List.Item>
          <List.Item>If anything in the file can't be imported, nothing is.</List.Item>
        </List>
        {!ownHousehold ? (
          <Text size="sm" c="dimmed">
            Imports go into a household you own. Switch to your own household in the sidebar to import.
          </Text>
        ) : file ? (
          <Group gap="sm" wrap="wrap">
            <Button leftSection={<IconFileUpload size={16} />} onClick={run} loading={importFile.isPending}>
              Import {file.name}
            </Button>
            <Button variant="default" leftSection={<IconX size={16} />} onClick={() => setFile(null)} disabled={importFile.isPending}>
              Cancel
            </Button>
          </Group>
        ) : (
          <FileButton onChange={setFile} accept="application/json,.json">
            {(props) => (
              <Button {...props} variant="default" leftSection={<IconFileUpload size={16} />} style={{ alignSelf: 'flex-start' }}>
                Choose a file
              </Button>
            )}
          </FileButton>
        )}
      </Stack>
    </SectionCard>
  );
}
