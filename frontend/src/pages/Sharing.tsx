import { Button, Group, Select, SimpleGrid, Text, TextInput } from '@mantine/core';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';

import { api, currentHouseholdId, setHouseholdId } from '../api';
import { PageHeader, SectionCard, useAppMutation } from '../components/common';
import { AccessCard, householdLabel, PendingInvites, useMe } from '../components/Sharing';
import type { Me } from '../types';
import { timezoneOptions } from './Onboarding';

export default function SharingPage() {
  const me = useMe();
  const queryClient = useQueryClient();
  const { hash } = useLocation();

  // Company pages link here as /sharing#company-<id>.
  useEffect(() => {
    if (hash && me) document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [hash, me]);

  if (!me) return null;
  if (me.auth_mode !== 'google') {
    return (
      <>
        <PageHeader title="Sharing" />
        <SectionCard title="Sharing needs sign-in">
          <Text size="sm">
            This install runs without accounts (AUTH_MODE=none), so there's nobody to share with. Set AUTH_MODE=google
            to turn on Google sign-in and sharing.
          </Text>
        </SectionCard>
      </>
    );
  }

  const household = me.households.find((h) => h.id === currentHouseholdId()) ?? me.households[0];
  const leaveHousehold = async () => {
    await api.leaveHousehold(household.id);
    setHouseholdId(null);
    await queryClient.invalidateQueries();
  };

  return (
    <>
      <PageHeader
        title="Sharing"
        description="Share your household with family, and each company with its partners. They're shared separately: someone in your household never sees your companies unless you share those too."
      />
      <PendingInvites />
      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg">
        {household?.role === 'owner' && <HouseholdSettings key={household.id} household={household} />}
        {household && (
          <AccessCard
            key={`household-${household.id}`}
            target="household"
            title={householdLabel(household)}
            onLeave={leaveHousehold}
            leaveLabel="Leave this household"
          />
        )}
        {me.companies.map((c) => (
          <div key={c.id} id={`company-${c.id}`} style={{ scrollMarginTop: 16 }}>
            <AccessCard
              target={c.id}
              title={c.name}
              onLeave={async () => {
                await api.leaveCompany(c.id);
                await queryClient.invalidateQueries();
              }}
              leaveLabel="Leave this company"
            />
          </div>
        ))}
      </SimpleGrid>
    </>
  );
}

/** The owner names their household and sets the timezone that decides which day and month it is. */
function HouseholdSettings({ household }: { household: Me['households'][number] }) {
  const [name, setName] = useState(household.name);
  const [timezone, setTimezone] = useState(household.timezone);
  const zones = useMemo(() => timezoneOptions(household.timezone), [household.timezone]);
  const save = useAppMutation(() => api.updateHousehold({ name: name.trim(), timezone }), 'Household saved');
  const changed = name.trim() !== household.name || timezone !== household.timezone;

  return (
    <SectionCard title="Household settings">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (changed && name.trim()) save.mutate(undefined);
        }}
      >
        <Group gap="sm" align="flex-end" wrap="wrap">
          <TextInput label="Name" value={name} onChange={(e) => setName(e.currentTarget.value)} maxLength={100} style={{ flex: '1 1 200px' }} />
          <Select
            label="Timezone"
            data={zones}
            value={timezone}
            onChange={(v) => v && setTimezone(v)}
            searchable
            allowDeselect={false}
            style={{ flex: '1 1 200px' }}
          />
          <Button type="submit" disabled={!changed || !name.trim()} loading={save.isPending}>
            Save
          </Button>
        </Group>
      </form>
      <Text size="xs" c="dimmed" mt="sm">
        The timezone decides which day and month it is for the budget, income statement and balance sheet.
      </Text>
    </SectionCard>
  );
}
