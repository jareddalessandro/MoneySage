import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Bind-mounted source on Windows doesn't emit file events into the container.
    watch: { usePolling: true, interval: 300 },
    proxy: {
      '/api': process.env.API_PROXY_TARGET ?? 'http://localhost:8100',
    },
  },
});
