import { Alert, Box, Button, Card, Center, Stack, Text, Title } from '@mantine/core';
import { IconAlertCircle } from '@tabler/icons-react';
import { useState } from 'react';

// What /api/auth/callback sends back as ?auth_error=.
const ERRORS: Record<string, string> = {
  cancelled: 'Sign-in was cancelled.',
  expired: 'That sign-in took too long, or was started in another tab or at another address. Try again.',
  not_allowed: "This Google account isn't allowed to sign in here. Ask whoever runs this MoneySage to add it.",
  unverified: "Google hasn't verified this account's email address, so it can't be used here.",
  failed: "Sign-in didn't work. Try again.",
};

/** Reads ?auth_error= once and removes it from the address bar, so a reload doesn't show it again. */
function takeAuthError(): string | null {
  const params = new URLSearchParams(window.location.search);
  const code = params.get('auth_error');
  if (code === null) return null;
  params.delete('auth_error');
  const rest = params.toString();
  window.history.replaceState(null, '', window.location.pathname + (rest ? `?${rest}` : ''));
  return ERRORS[code] ?? ERRORS.failed;
}

export default function SignInPage() {
  const [error] = useState(takeAuthError);

  return (
    <Center mih="100dvh" p="md">
      <Card w="100%" maw={420} p={{ base: 'lg', sm: 'xl' }}>
        <Stack gap="lg">
          <Text className="headline" fw={800} size="lg" lts="-0.01em">
            💰 MoneySage
          </Text>
          <div>
            <Title order={1} fz="1.75rem" lts="-0.01em" mb={6}>
              Sign in
            </Title>
            <Text size="sm" c="dimmed">
              Your budget, income statement, balance sheet and investments in one place, shared with the people
              you choose.
            </Text>
          </div>
          {error && (
            <Alert color="red" variant="light" icon={<IconAlertCircle size={18} />}>
              {error}
            </Alert>
          )}
          <Button
            component="a"
            href="/api/auth/login"
            variant="default"
            size="md"
            radius="xl"
            fullWidth
            leftSection={<GoogleLogo />}
          >
            Sign in with Google
          </Button>
          <Text size="xs" c="dimmed">
            Signing in for the first time creates your own private household. Nothing is shared until you share it.
          </Text>
        </Stack>
      </Card>
    </Center>
  );
}

/** Google's "G" mark, as their sign-in branding guidelines ask for. */
function GoogleLogo() {
  return (
    <Box component="svg" viewBox="0 0 48 48" w={18} h={18} aria-hidden display="block">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </Box>
  );
}
