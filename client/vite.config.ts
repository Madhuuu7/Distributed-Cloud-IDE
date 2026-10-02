// vitest/config, not vite: it re-exports defineConfig with the `test` key
// typed. Importing from 'vite' type-checks everything except the test block,
// which then fails `tsc -b` and takes the production build down with it.
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '0.0.0.0'
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    // Monaco ships browser-only globals that jsdom does not provide, and no
    // test here drives the editor itself.
    exclude: ['node_modules/**', 'dist/**'],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/main.tsx', 'src/vite-env.d.ts', 'src/types/**', 'src/test/**']
    }
  }
});
