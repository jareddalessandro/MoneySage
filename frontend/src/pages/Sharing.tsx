import { SimpleGrid, Text } from '@mantine/core';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

import { api, currentHouseholdId, setHouseholdId } from '../api';
import { PageHeader, SectionCard } from '../components/common';
import { AccessCard, householdLabel, PendingInvites, useMe } from '../components/Sharing';

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
