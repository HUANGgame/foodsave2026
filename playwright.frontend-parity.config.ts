import {defineConfig} from '@playwright/test';
import path from 'node:path';
import live from './playwright.live.config';

const reportDir = process.env.FOODSAVE_PLAYWRIGHT_REPORT_DIR || 'test-results/frontend-parity';
const {executablePath: legacyChromium, ...launchOptions} = live.use?.launchOptions || {};
void legacyChromium;

export default defineConfig({
  ...live,
  forbidOnly: true,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 45_000,
  globalTimeout: 15 * 60_000,
  expect: {timeout: 10_000},
  outputDir: path.join(reportDir, 'results'),
  reporter: [
    ['line'],
    ['junit', {outputFile: path.join(reportDir, 'junit.xml')}],
    ['json', {outputFile: path.join(reportDir, 'results.json')}],
    ['html', {outputFolder: path.join(reportDir, 'html'), open: 'never'}],
  ],
  use: {
    ...live.use,
    browserName: 'chromium',
    serviceWorkers: 'block',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: {
      ...launchOptions,
      args: [
        ...(launchOptions.args || []),
        '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost',
      ],
    },
  },
});
