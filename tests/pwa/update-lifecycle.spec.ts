import {test, expect, chromium, type BrowserContext, type Page, type Worker} from '@playwright/test';
import {mkdtemp, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash, randomUUID} from 'node:crypto';

const BASE = 'http://127.0.0.1:4175';
const VERSION_ENDPOINT = BASE + '/__pwa_qa__/version';
const CURRENT = 'foodsave-shell-v1-20261009';
const SUCCESSOR = 'foodsave-shell-v2-qa-20261011';
const STALE = 'foodsave-shell-stale-qa-20261011';
const UNRELATED = 'unrelated-pwa-qa-20261011';
const MARKER = '/__pwa_qa__/unrelated-marker';
const MARKER_VALUE = 'retain unrelated cache across FoodSave activation';
const UPDATE_TEXT = '有新版可用。請先完成手邊操作，再關閉所有食在可惜頁面後重新開啟。';

type WorkerSnapshot = {
  cacheVersion: string;
  activeState: string | null;
  waitingState: string | null;
  cacheNames: string[];
  controlledClientCount: number;
  unrelatedValue: string | null;
};

async function waitForController(page: Page) {
  await expect.poll(async () => page.evaluate(async () => {
    const registration = await navigator.serviceWorker.getRegistration();
    return {
      controlled: Boolean(navigator.serviceWorker.controller),
      active: registration?.active?.state || null,
      scope: registration?.scope || null
    };
  }), {timeout: 20_000}).toEqual({
    controlled: true,
    active: 'activated',
    scope: BASE + '/'
  });
}

async function installDocumentProbe(page: Page) {
  const token = randomUUID();
  await page.evaluate(token => {
    const controller = navigator.serviceWorker.controller;
    if (!controller) throw new Error('A controlled document is required.');
    const probe = {token, controller, changes: 0};
    (window as any).__foodsavePwaQa = probe;
    navigator.serviceWorker.addEventListener('controllerchange', () => {probe.changes++;});
  }, token);
  return token;
}

async function pageSnapshot(page: Page) {
  return page.evaluate(async ({unrelated, marker}) => {
    const registrations = await navigator.serviceWorker.getRegistrations();
    const registration = await navigator.serviceWorker.getRegistration();
    const probe = (window as any).__foodsavePwaQa;
    const stored = await caches.match(marker, {cacheName: unrelated});
    return {
      registrationCount: registrations.length,
      scope: registration?.scope || null,
      documentToken: probe?.token || null,
      controllerUnchanged: Boolean(probe && navigator.serviceWorker.controller === probe.controller),
      activeUnchanged: Boolean(probe && registration?.active === probe.controller),
      controllerChanges: probe?.changes ?? null,
      activeState: registration?.active?.state || null,
      waitingState: registration?.waiting?.state || null,
      waitingIsDifferent: Boolean(registration?.waiting && registration.waiting !== probe?.controller),
      cacheNames: (await caches.keys()).sort(),
      unrelatedValue: stored ? await stored.text() : null
    };
  }, {unrelated: UNRELATED, marker: MARKER});
}

async function workerSnapshot(worker: Worker): Promise<WorkerSnapshot> {
  // A read of the genuine worker realm distinguishes versions with the same /sw.js URL.
  // No register(), skipWaiting(), postMessage(), or lifecycle events are synthesized.
  return worker.evaluate('(async () => {' +
    'const stored = await caches.match(' + JSON.stringify(MARKER) + ', {cacheName:' + JSON.stringify(UNRELATED) + '});' +
    'return {' +
    'cacheVersion: CACHE,' +
    'activeState: self.registration.active ? self.registration.active.state : null,' +
    'waitingState: self.registration.waiting ? self.registration.waiting.state : null,' +
    'cacheNames: (await caches.keys()).sort(),' +
    'controlledClientCount: (await self.clients.matchAll({type:"window", includeUncontrolled:false})).length,' +
    'unrelatedValue: stored ? await stored.text() : null' +
    '};})()');
}

async function assertWaitingWithoutReplacement(page: Page, token: string) {
  const snapshot = await pageSnapshot(page);
  expect(snapshot).toMatchObject({
    registrationCount: 1,
    scope: BASE + '/',
    documentToken: token,
    controllerUnchanged: true,
    activeUnchanged: true,
    controllerChanges: 0,
    activeState: 'activated',
    waitingState: 'installed',
    waitingIsDifferent: true,
    unrelatedValue: MARKER_VALUE
  });
  expect(snapshot.cacheNames).toEqual([CURRENT, SUCCESSOR, STALE, UNRELATED].sort());
  await expect(page.getByText(UPDATE_TEXT, {exact: true})).toBeVisible();
  return snapshot;
}

async function observeStableWaiting(page: Page, token: string, durationMs: number) {
  // This bounded interval is a negative-behavior observation, not a readiness delay.
  // Every sample checks for premature activation, document replacement, and cache deletion.
  const until = Date.now() + durationMs;
  do {
    await assertWaitingWithoutReplacement(page, token);
    await new Promise(resolve => setTimeout(resolve, 100));
  } while (Date.now() < until);
}

test('current worker waits for every controlled tab to close before the controlled successor takes over', async ({request}, testInfo) => {
  test.setTimeout(120_000);
  const evidence: Record<string, unknown> = {
    scope: 'Current repository worker to a cache-token-only controlled successor.',
    legacyProductionWorkerCompatibility: 'Not tested; a verified legacy worker was not supplied.'
  };
  let context: BrowserContext | undefined;
  const profile = await mkdtemp(join(tmpdir(), 'foodsave-pwa-update-'));
  const outsideRequests: string[] = [];
  const pageErrors: string[] = [];

  try {
    const reset = await request.post(VERSION_ENDPOINT, {data: {version: 1}});
    expect(reset.status()).toBe(200);
    expect(await reset.json()).toEqual({version: 1});

    const invalid = await request.post(VERSION_ENDPOINT, {data: {version: 3}});
    expect(invalid.status()).toBe(400);
    const foreignOrigin = await request.post(VERSION_ENDPOINT, {
      headers: {Origin: 'https://untrusted.example.test'},
      data: {version: 2}
    });
    expect(foreignOrigin.status()).toBe(403);
    const unchanged = await request.get(VERSION_ENDPOINT);
    expect(unchanged.status()).toBe(200);
    expect(await unchanged.json()).toEqual({version: 1});
    evidence.controlEndpoint = {invalidVersion: invalid.status(), foreignOrigin: foreignOrigin.status(), versionAfterRejectedRequests: 1};

    const originalResponse = await request.get(BASE + '/sw.js');
    expect(originalResponse.status()).toBe(200);
    expect(originalResponse.headers()['cache-control']).toBe('no-store');
    const originalBytes = await originalResponse.body();
    const originalText = originalBytes.toString('utf8');
    expect(originalText.split(CURRENT)).toHaveLength(2);
    expect(originalText).toContain("const CACHE='" + CURRENT + "';");
    expect(originalText).not.toContain(SUCCESSOR);

    context = await chromium.launchPersistentContext(profile, {
      channel: 'chromium',
      headless: true,
      serviceWorkers: 'allow',
      permissions: [],
      viewport: {width: 1000, height: 800},
      args: [
        '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost',
        '--proxy-server=' + BASE,
        '--proxy-bypass-list=127.0.0.1;localhost'
      ]
    });
    await context.tracing.start({screenshots: true, snapshots: true});
    context.on('request', request => {
      const url = request.url();
      if (/^https?:/.test(url) && new URL(url).origin !== BASE) outsideRequests.push(url);
    });
    context.on('page', page => page.on('pageerror', error => pageErrors.push(error.message)));
    for (const initialPage of context.pages()) await initialPage.close();

    // A new opaque blank page has no opener and cannot hold this origin's worker active.
    const observer = await context.newPage();
    const observerState = await observer.evaluate(() => {
      let controller: string | null = null;
      try {
        controller = navigator.serviceWorker?.controller?.scriptURL || null;
      } catch (error) {
        if (!(error instanceof DOMException) || error.name !== 'SecurityError') throw error;
      }
      return {url: location.href, origin: location.origin, hasOpener: Boolean(window.opener), controller};
    });
    expect(observerState).toEqual({url: 'about:blank', origin: 'null', hasOpener: false, controller: null});
    evidence.observer = observerState;

    const first = await context.newPage();
    await first.goto(BASE + '/privacy/', {waitUntil: 'load'});
    await waitForController(first);
    await expect(first.getByText(UPDATE_TEXT, {exact: true})).toHaveCount(0);

    const originalWorker = context.serviceWorkers().find(worker => worker.url() === BASE + '/sw.js');
    expect(originalWorker, 'The application must register a real service worker.').toBeTruthy();
    expect(await originalWorker!.evaluate('CACHE')).toBe(CURRENT);
    await first.evaluate(async ({stale, unrelated, marker, value}) => {
      await (await caches.open(stale)).put('/__pwa_qa__/stale-marker', new Response('remove only during activation'));
      await (await caches.open(unrelated)).put(marker, new Response(value));
    }, {stale: STALE, unrelated: UNRELATED, marker: MARKER, value: MARKER_VALUE});

    const second = await context.newPage();
    await second.goto(BASE + '/privacy/', {waitUntil: 'load'});
    await waitForController(second);
    await expect(second.getByText(UPDATE_TEXT, {exact: true})).toHaveCount(0);
    const firstToken = await installDocumentProbe(first);
    const secondToken = await installDocumentProbe(second);
    const navigationCounts = {first: 0, second: 0};
    first.on('framenavigated', frame => {if (frame === first.mainFrame()) navigationCounts.first++;});
    second.on('framenavigated', frame => {if (frame === second.mainFrame()) navigationCounts.second++;});
    await expect.poll(() => originalWorker!.evaluate(
      'self.clients.matchAll({type:"window",includeUncontrolled:false}).then(clients => clients.length)'
    )).toBe(2);
    evidence.beforeUpdate = await pageSnapshot(first);
    expect((evidence.beforeUpdate as any).cacheNames).toEqual([CURRENT, STALE, UNRELATED].sort());

    const promote = await request.post(VERSION_ENDPOINT, {data: {version: 2}});
    expect(promote.status()).toBe(200);
    expect(await promote.json()).toEqual({version: 2});
    const successorResponse = await request.get(BASE + '/sw.js');
    expect(successorResponse.status()).toBe(200);
    const successorBytes = await successorResponse.body();
    expect(successorBytes.equals(Buffer.from(originalText.replace(CURRENT, SUCCESSOR), 'utf8'))).toBe(true);
    evidence.servedWorkerSha256 = {
      original: createHash('sha256').update(originalBytes).digest('hex'),
      successor: createHash('sha256').update(successorBytes).digest('hex')
    };

    const [successorWorker] = await Promise.all([
      context.waitForEvent('serviceworker', {predicate: worker => worker.url() === BASE + '/sw.js', timeout: 20_000}),
      first.evaluate(async () => {
        const registration = await navigator.serviceWorker.getRegistration();
        if (!registration) throw new Error('Application registration is missing.');
        await registration.update();
      })
    ]);
    await expect.poll(() => first.evaluate(async () =>
      (await navigator.serviceWorker.getRegistration())?.waiting?.state || null
    ), {timeout: 20_000}).toBe('installed');
    expect(await successorWorker.evaluate('CACHE')).toBe(SUCCESSOR);
    evidence.waiting = await assertWaitingWithoutReplacement(first, firstToken);
    await assertWaitingWithoutReplacement(second, secondToken);
    await observeStableWaiting(first, firstToken, 2000);
    await assertWaitingWithoutReplacement(second, secondToken);
    expect(navigationCounts).toEqual({first: 0, second: 0});
    await testInfo.attach('update-waiting', {body: await first.screenshot({fullPage: true}), contentType: 'image/png'});

    await first.close();
    await expect.poll(() => originalWorker!.evaluate(
      'self.clients.matchAll({type:"window",includeUncontrolled:false}).then(clients => clients.length)'
    )).toBe(1);
    await observeStableWaiting(second, secondToken, 1000);
    evidence.oneControlledTabRemaining = await assertWaitingWithoutReplacement(second, secondToken);
    expect(navigationCounts).toEqual({first: 0, second: 0});

    await second.close();
    expect(context.pages()).toEqual([observer]);
    // Observe from the new worker itself, without opening another controlled document.
    // Activation is allowed once the LAST old client closes; reopening is not required.
    await expect.poll(async () => {
      const snapshot = await workerSnapshot(successorWorker);
      return {
        version: snapshot.cacheVersion,
        active: snapshot.activeState,
        waiting: snapshot.waitingState,
        controlledClients: snapshot.controlledClientCount,
        cacheNames: snapshot.cacheNames,
        unrelatedValue: snapshot.unrelatedValue
      };
    }, {timeout: 20_000}).toEqual({
      version: SUCCESSOR,
      active: 'activated',
      waiting: null,
      controlledClients: 0,
      cacheNames: [SUCCESSOR, UNRELATED].sort(),
      unrelatedValue: MARKER_VALUE
    });
    evidence.activatedWithoutControlledTabs = await workerSnapshot(successorWorker);

    const reopened = await context.newPage();
    await reopened.goto(BASE + '/privacy/', {waitUntil: 'load'});
    await waitForController(reopened);
    await expect.poll(async () => (await workerSnapshot(successorWorker)).controlledClientCount).toBe(1);
    const finalRegistration = await reopened.evaluate(async () => {
      const registrations = await navigator.serviceWorker.getRegistrations();
      const registration = await navigator.serviceWorker.getRegistration();
      return {
        count: registrations.length,
        scope: registration?.scope,
        controllerUrl: navigator.serviceWorker.controller?.scriptURL,
        waiting: Boolean(registration?.waiting),
        caches: (await caches.keys()).sort()
      };
    });
    expect(finalRegistration).toEqual({
      count: 1,
      scope: BASE + '/',
      controllerUrl: BASE + '/sw.js',
      waiting: false,
      caches: [SUCCESSOR, UNRELATED].sort()
    });
    await expect(reopened.getByText(UPDATE_TEXT, {exact: true})).toHaveCount(0);
    evidence.reopened = finalRegistration;
    expect(outsideRequests, 'The privacy-page lifecycle must stay entirely on loopback.').toEqual([]);
    expect(pageErrors).toEqual([]);
  } finally {
    evidence.outsideRequests = outsideRequests;
    evidence.pageErrors = pageErrors;
    await testInfo.attach('pwa-update-lifecycle', {
      body: Buffer.from(JSON.stringify(evidence, null, 2)),
      contentType: 'application/json'
    });
    if (context) {
      await context.tracing.stop({path: testInfo.outputPath('pwa-update-trace.zip')}).catch(() => {});
      await context.close().catch(() => {});
    }
    await rm(profile, {recursive: true, force: true});
  }
});
