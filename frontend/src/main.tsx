import '@fontsource-variable/inter';
import '@fontsource-variable/manrope';
import '@mantine/core/styles.css';
import '@mantine/dates/styles.css';
import '@mantine/charts/styles.css';
import '@mantine/notifications/styles.css';
import './styles.css';

import { MantineProvider } from '@mantine/core';
import { DatesProvider } from '@mantine/dates';
import { ModalsProvider } from '@mantine/modals';
import { Notifications } from '@mantine/notifications';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import App from './App';
import { cssVariablesResolver, theme } from './theme';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, refetchOnWindowFocus: false, placeholderData: (prev: unknown) => prev },
  },
});

// Preferences saved before the app was renamed (moneysage.*) carry over to the new keys (tallyvio.*).
try {
  for (const key of Object.keys(localStorage)) {
    if (!key.startsWith('moneysage.')) continue;
    const renamed = `tallyvio.${key.slice('moneysage.'.length)}`;
    if (localStorage.getItem(renamed) === null) localStorage.setItem(renamed, localStorage.getItem(key)!);
    localStorage.removeItem(key);
  }
} catch {
  // storage unavailable: nothing to carry over
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MantineProvider theme={theme} cssVariablesResolver={cssVariablesResolver} forceColorScheme="dark">
      <DatesProvider settings={{ firstDayOfWeek: 0 }}>
        <QueryClientProvider client={queryClient}>
          <ModalsProvider>
            <Notifications position="top-right" />
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </ModalsProvider>
        </QueryClientProvider>
      </DatesProvider>
    </MantineProvider>
  </StrictMode>,
);
