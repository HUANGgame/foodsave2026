import {test, expect, chromium} from '@playwright/test';

const ORIGIN = 'http://127.0.0.1:4175';

test('full Chromium validates the manifest and installability with a failing no-manifest control', async ({request}, testInfo) => {
  const reset = await request.post(ORIGIN + '/__pwa_qa__/version', {data: {version: 1}});
  expect(reset.ok()).toBe(true);
  expect(await reset.json()).toEqual({version: 1});
  // A temporary persistent profile is non-incognito. The chromium channel selects
  // full Chromium rather than headless-shell's content-layer installability stub.
  // No install command is issued and no browser permission is granted.
  const context = await chromium.launchPersistentContext('', {
    channel: 'chromium',
    headless: true,
    baseURL: ORIGIN,
    viewport: {width: 390, height: 844},
    serviceWorkers: 'allow',
    args: [
      '--no-sandbox',
      '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost',
      '--proxy-server=http://127.0.0.1:4175',
      '--proxy-bypass-list=127.0.0.1;localhost',
    ],
  });
  await context.tracing.start({screenshots: true, snapshots: true});
  const unexpected: string[] = [];
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin === ORIGIN) return route.continue();
    if (url.origin === 'https://api.foodsave.test' && url.pathname === '/auth/options' && route.request().method() === 'GET') {
      return route.fulfill({json: {registration_enabled: false, recovery_enabled: false}});
    }
    unexpected.push(route.request().method() + ' ' + url.origin + url.pathname);
    return route.abort();
  });
  await context.addInitScript(() => {
    const probe = window as Window & {__pwaLocationRequests?: number};
    probe.__pwaLocationRequests = 0;
    Object.defineProperty(navigator, 'geolocation', {configurable: true, value: {
      getCurrentPosition() {probe.__pwaLocationRequests!++;},
      watchPosition() {probe.__pwaLocationRequests!++; return 1;},
      clearWatch() {},
    }});
  });
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  try {
    const browser = await cdp.send('Browser.getVersion');
    await page.goto('/offline.html');
    await expect(page.locator('link[rel="manifest"]')).toHaveCount(0);
    const negative = await cdp.send('Page.getInstallabilityErrors');
    await testInfo.attach('installability-negative-control.json', {
      body: Buffer.from(JSON.stringify({browser, negative}, null, 2)), contentType: 'application/json',
    });
    expect(negative.installabilityErrors.some(error => error.errorId.toLowerCase().includes('manifest')),
      'The no-manifest page must fail: an always-empty CDP implementation is not evidence').toBe(true);

    await page.goto('/');
    await expect.poll(() => page.evaluate(async () =>
      (await navigator.serviceWorker.getRegistration('/'))?.active?.state)).toBe('activated');
    await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true);
    const manifest = await cdp.send('Page.getAppManifest');
    const result = await cdp.send('Page.getInstallabilityErrors');
    await testInfo.attach('candidate-installability.json', {
      body: Buffer.from(JSON.stringify({
        browser, manifest, result,
        scope: 'Fresh full-Chromium profile, loopback synthetic site. Eligibility only; no installed app or production migration tested.',
      }, null, 2)), contentType: 'application/json',
    });
    expect(manifest.url).toBe(ORIGIN + '/manifest.webmanifest');
    expect(manifest.errors).toEqual([]);
    expect(manifest.data).toBeTruthy();
    const parsed = JSON.parse(manifest.data!);
    expect(parsed.name || parsed.short_name).toBeTruthy();
    expect(parsed.start_url).toBe('/');
    expect(parsed.scope).toBe('/');
    expect(parsed.display).toBe('standalone');
    expect(Array.isArray(parsed.icons) && parsed.icons.length > 0).toBe(true);
    expect(result.installabilityErrors).toEqual([]);
    expect(unexpected).toEqual([]);
    expect(await page.evaluate(() => (window as Window & {__pwaLocationRequests?: number}).__pwaLocationRequests)).toBe(0);
  } finally {
    const screenshot = testInfo.outputPath('installability-page.png');
    await page.screenshot({path: screenshot, fullPage: true}).then(() =>
      testInfo.attach('Installability page', {path: screenshot, contentType: 'image/png'})).catch(() => {});
    await cdp.detach();
    const trace = testInfo.outputPath('installability-trace.zip');
    await context.tracing.stop({path: trace});
    await testInfo.attach('Installability trace', {path: trace, contentType: 'application/zip'});
    await context.close();
  }
});
