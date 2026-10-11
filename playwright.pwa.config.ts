import {defineConfig} from '@playwright/test';
import path from 'node:path';

const reportDir = process.env.FOODSAVE_PWA_REPORT_DIR || 'test-results/pwa-validation';

export default defineConfig({
  testDir: './tests/pwa',
  forbidOnly: true,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  globalTimeout: 5 * 60_000,
  expect: {timeout: 15_000},
  outputDir: path.join(reportDir, 'results'),
  reporter: [
    ['line'],
    ['junit', {outputFile: path.join(reportDir, 'junit.xml')}],
    ['json', {outputFile: path.join(reportDir, 'results.json')}],
    ['html', {outputFolder: path.join(reportDir, 'html'), open: 'never'}],
  ],
  use: {baseURL: 'http://127.0.0.1:4175'},
  webServer: {
    command: 'node scripts/pwa-validation-server.cjs',
    url: 'http://127.0.0.1:4175/__pwa_qa__/version',
    reuseExistingServer: false,
    timeout: 30_000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
});
