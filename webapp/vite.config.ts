import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

const coverageAll = process.env.VITEST_COVERAGE_ALL === 'true';

const testedFilesThresholds = {
  statements: 38,
  branches: 42,
  functions: 28,
  lines: 41,
};

// Staged baseline for all source files. Ratchet these upward as targeted
// coverage expands, then make this the primary gate.
const allFilesThresholds = {
  statements: 12,
  branches: 12,
  functions: 9,
  lines: 13,
};

export default defineConfig({
  plugins: [react()],
  test: {
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json-summary', 'html'],
      reportsDirectory: './coverage',
      all: coverageAll,
      include: coverageAll ? ['src/**/*.{ts,tsx}'] : undefined,
      exclude: ['src/**/*.d.ts', 'src/**/*.{test,spec}.{ts,tsx}', 'src/test/**'],
      thresholds: coverageAll ? allFilesThresholds : testedFilesThresholds,
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
