import { Anchor, Button, Card, Center, Checkbox, Select, Stack, Text, TextInput, Title } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useQueryClient } from '@tanstack/react-query';
import { useMemo, useState, type FormEvent } from 'react';

import { api } from '../api';
import type { Me } from '../types';

/** Every IANA zone the browser knows, with the browser's own first. */
export function timezoneOptions(current?: string): string[] {
  let zones: string[] = [];
  try {
    zones = Intl.supportedValuesOf('timeZone');
  } catch {
    // older browsers: the browser's zone (and the current one) only
  }
  const own = browserTimezone();
  return [...new Set([own, ...(current ? [current] : []), ...zones])];
}

export function browserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/New_York';
  } catch {
    return 'America/New_York';
  }
}

/**
 * Shown before the app the first time someone signs in (household name, timezone, agreeing to the terms),
 * and again with just the agreement when the terms change.
 */
export default function OnboardingPage({ me }: { me: Me }) {
  const queryClient = useQueryClient();
  const firstName = me.user.name?.split(' ')[0];
  const [name, setName] = useState(firstName ? `${firstName}'s household` : 'My household');
  const [timezone, setTimezone] = useState<string>(browserTimezone);
  const [agreed, setAgreed] = useState(false);
  const [saving, setSaving] = useState(false);
  const zones = useMemo(() => timezoneOptions(), []);
  const setup = me.needs_setup;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      await api.onboarding(setup ? { household_name: name.trim(), timezone, accept_terms: true } : { accept_terms: true });
      await queryClient.invalidateQueries();
    } catch (error) {
      notifications.show({ title: 'Something went wrong', message: (error as Error).message, color: 'red' });
      setSaving(false);
    }
  };

  // The legal pages open in a new tab, so nothing typed here is lost.
  const legal = (to: string, label: string) => (
    <Anchor href={to} target="_blank" rel="noopener">
      {label}
    </Anchor>
  );

  return (
    <Center mih="100dvh" p="md">
      <Card w="100%" maw={460} p={{ base: 'lg', sm: 'xl' }}>
        <form onSubmit={submit}>
          <Stack gap="lg">
            <Text className="headline" fw={800} size="lg" lts="-0.01em">
              💰 MoneySage
            </Text>
            <div>
              <Title order={1} fz="1.75rem" lts="-0.01em" mb={6}>
                {setup ? `Welcome${firstName ? `, ${firstName}` : ''}` : "We've updated our terms"}
              </Title>
              <Text size="sm" c="dimmed">
                {setup
                  ? 'Set up your household. Only you can see it until you share it.'
                  : 'Please review the Terms of Service and Privacy Policy, and agree to carry on.'}
              </Text>
            </div>
            {setup && (
              <>
                <TextInput
                  label="Household name"
                  description="Shown to people you share it with."
                  value={name}
                  onChange={(e) => setName(e.currentTarget.value)}
                  maxLength={100}
                  required
                />
                <Select
                  label="Timezone"
                  description="Decides which day and month it is for your budget and statements."
                  data={zones}
                  value={timezone}
                  onChange={(v) => v && setTimezone(v)}
                  searchable
                  allowDeselect={false}
                  nothingFoundMessage="No matching timezone"
                />
              </>
            )}
            <Checkbox
              checked={agreed}
              onChange={(e) => setAgreed(e.currentTarget.checked)}
              label={
                <>
                  I agree to the {legal('/terms', 'Terms of Service')} and {legal('/privacy', 'Privacy Policy')}.
                </>
              }
            />
            <Button type="submit" size="md" disabled={!agreed || (setup && !name.trim())} loading={saving}>
              {setup ? 'Get started' : 'Continue'}
            </Button>
            {setup && (
              <Text size="xs" c="dimmed">
                Moving from an offline MoneySage? After this, open Export &amp; import and bring in your export file.
              </Text>
            )}
          </Stack>
        </form>
      </Card>
    </Center>
  );
}
