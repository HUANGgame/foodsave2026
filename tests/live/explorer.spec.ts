import {test, expect, type Page, type BrowserContext} from '@playwright/test';
import type {LiveProduct, LiveStore} from '../../lib/api';

type Point = [number, number];
type NearbyRead = {path: string; latitude: number; longitude: number};
type Scenario = {nearby: NearbyRead[]; familyReads: number; unexpected: string[]; offline: boolean};
type GeoFixture = {
  requests: number;
  started: number[];
  cleared: number[];
  active: Set<number>;
  emit: (point: Point) => void;
  late: (id: number, point: Point) => void;
};
declare global {interface Window {__explorerGeo: GeoFixture}}

const API = 'https://api.foodsave.test';
const CACHE_PREFIX = 'foodsave-shell-';
const CACHE_CURRENT = 'foodsave-shell-v1-20261009';
const scenarios = new WeakMap<Page, Scenario>();
const tokens = {a: 'EXPLORER_SYNTHETIC_SESSION_A', b: 'EXPLORER_SYNTHETIC_SESSION_B'};
const emails = {a: 'explorer-a@example.test', b: 'explorer-b@example.test'};
const stores: LiveStore[] = [
  {id: 'store-a', vendor_id: 'vendor-a', name: '晨光麵包坊', latitude: 25.0478, longitude: 121.517, product_count: 3, service_mode: 'information'},
  {id: 'store-b', vendor_id: 'vendor-b', name: '青葉餐桌', latitude: 25.04782, longitude: 121.51702, product_count: 1, service_mode: 'information'},
  {id: 'store-c', vendor_id: 'vendor-c', name: '街角雜貨', latitude: 25.0523, longitude: 121.5234, product_count: 1, service_mode: 'information'},
];
function product(id: string, store: LiveStore, name: string, sale: number, original: number): LiveProduct {
  return {
    id, store_id: store.id, vendor_id: store.vendor_id, store_name: store.name,
    name, latitude: store.latitude, longitude: store.longitude,
    photo_url: 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="40" height="40"%3E%3Crect width="40" height="40" fill="%2399aa77"/%3E%3C/svg%3E',
    sale_price_minor: sale, original_price_minor: original,
    available_quantity: 3, pickup_deadline: '2035-01-01T12:00:00Z', revision: 1,
    source: 'foodsave', service_mode: 'information',
  };
}
const products = [
  product('free-a', stores[0], '分享餐包', 0, 6000),
  product('discount-a', stores[0], '香草吐司', 4000, 8000),
  product('regular-a', stores[0], '燕麥餅乾', 2500, 2500),
  product('discount-b', stores[1], '南瓜餐盒', 6000, 12000),
  product('free-c', stores[2], '青蔬湯', 0, 5000),
];

async function mockScenario(page: Page, context: BrowserContext, denied = false): Promise<Scenario> {
  const state: Scenario = {nearby: [], familyReads: 0, unexpected: [], offline: false};
  scenarios.set(page, state);
  let account: 'a' | 'b' = 'a';
  await context.route('**/*', async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin === 'http://127.0.0.1:4174') return route.continue();
    if (url.origin === API) {
      if (state.offline) return route.abort('internetdisconnected');
      const json = (body: unknown, status = 200) => route.fulfill({status, json: body});
      if (request.method() === 'OPTIONS') return route.fulfill({status: 204, headers: {
        'access-control-allow-origin': '*',
        'access-control-allow-headers': 'authorization,content-type,idempotency-key',
        'access-control-allow-methods': 'GET,POST,PUT,OPTIONS',
      }});
      if (url.pathname === '/auth/login' && request.method() === 'POST') {
        account = request.postDataJSON().email === emails.b ? 'b' : 'a';
        return json({access_token: tokens[account]});
      }
      if (url.pathname === '/auth/logout' && request.method() === 'POST') return json({ok: true});
      if (request.method() !== 'GET') {
        state.unexpected.push(request.method() + ' ' + url.pathname);
        return route.abort();
      }
      if (url.pathname === '/auth/options') return json({registration_enabled: false, recovery_enabled: false});
      if (url.pathname === '/me') return json({id: 'explorer-' + account, email: emails[account], role: 'consumer', exp: 0, spins: 0});
      if (url.pathname === '/stores') return json(stores);
      if (url.pathname === '/products') return json(products);
      if (url.pathname === '/favorites') return json([]);
      if (url.pathname === '/notifications') return json([{id: 'notice-' + account, kind: 'test', body: 'PRIVATE EXPLORER ' + account.toUpperCase() + ' NOTICE', created_at: '2026-10-09T00:00:00Z', read_at: null}]);
      if (url.pathname === '/reservations') return json([{id: 'order-' + account, state: 'cancelled', quantity: 1, snapshot: {name: 'PRIVATE EXPLORER ' + account.toUpperCase() + ' ORDER', sale_price_minor: 100}, expires_at: '2026-01-01T00:00:00Z'}]);
      if (/^\/stores\/[^/]+\/reviews$/.test(url.pathname)) {
        if (url.pathname === '/stores/store-a/reviews') return json({average: 4.9, count: 1, items: [{rating: 5, body: '晨光店專屬評論'}]});
        if (url.pathname === '/stores/store-b/reviews') return json({average: 2, count: 1, items: [{rating: 2, body: '青葉店專屬評論'}]});
        return json({average: null, count: 0, items: []});
      }
      if (url.pathname === '/nearby/stores' || url.pathname === '/nearby/products') {
        state.nearby.push({path: url.pathname, latitude: Number(url.searchParams.get('latitude')), longitude: Number(url.searchParams.get('longitude'))});
        return json({items: url.pathname.endsWith('/stores') ? stores : products, radius_m: 1000, page_size: 100, next_cursor: null});
      }
      state.unexpected.push(request.method() + ' ' + url.pathname);
      return json({detail: 'Unmocked fixture endpoint'}, 503);
    }
    if (url.origin === 'https://stamp.family.com.tw') {
      expect(request.headers().authorization).toBeUndefined();
      if (request.method() === 'OPTIONS') return route.fulfill({status: 204, headers: {
        'access-control-allow-origin': '*', 'access-control-allow-headers': 'content-type', 'access-control-allow-methods': 'POST,OPTIONS',
      }});
      if (state.offline) return route.abort('internetdisconnected');
      state.familyReads++;
      return route.fulfill({json: {code: 1, data: [{
        oldPKey: 'family-station', name: '全家車站店', address: '合成公開門市地址',
        latitude: 25.0503, longitude: 121.514, updateDate: new Date().toISOString(),
        info: [{categories: [{name: '餐盒', products: [{code: 'family-chicken', name: '照燒雞腿', qty: 2}]}]}],
      }]}});
    }
    if (url.hostname === 'tile.openstreetmap.org' || url.hostname.endsWith('.tile.openstreetmap.org')) return route.abort();
    state.unexpected.push(request.method() + ' ' + url.origin + url.pathname);
    return route.abort();
  });
  await page.addInitScript(({denied}) => {
    let serial = 0;
    const callbacks = new Map<number, PositionCallback>();
    const allCallbacks = new Map<number, PositionCallback>();
    const position = (point: [number, number]): GeolocationPosition => ({
      coords: {latitude: point[0], longitude: point[1], accuracy: 10, altitude: null, altitudeAccuracy: null, heading: null, speed: null},
      timestamp: Date.now(),
    } as GeolocationPosition);
    const fixture: GeoFixture = {
      requests: 0, started: [], cleared: [], active: new Set<number>(),
      emit(point) {for (const callback of callbacks.values()) callback(position(point));},
      late(id, point) {allCallbacks.get(id)?.(position(point));},
    };
    window.__explorerGeo = fixture;
    Object.defineProperty(navigator, 'geolocation', {configurable: true, value: {
      getCurrentPosition(success: PositionCallback, error?: PositionErrorCallback) {
        fixture.requests++;
        queueMicrotask(() => denied ? error?.({code: 1, message: 'Synthetic permission denial', PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3} as GeolocationPositionError) : success(position([25.0478, 121.517])));
      },
      watchPosition(success: PositionCallback) {
        const id = ++serial;
        fixture.started.push(id); fixture.active.add(id);
        callbacks.set(id, success); allCallbacks.set(id, success);
        return id;
      },
      clearWatch(id: number) {
        fixture.cleared.push(id); fixture.active.delete(id); callbacks.delete(id);
      },
    }});
  }, {denied});
  return state;
}

async function login(page: Page, account: 'a' | 'b' = 'a') {
  await page.getByLabel('電子郵件').fill(emails[account]);
  await page.getByLabel('密碼', {exact: true}).fill('synthetic-password-123');
  await page.getByRole('button', {name: '登入', exact: true}).click();
  await expect(page.getByRole('button', {name: '登入', exact: true})).toHaveCount(0);
}
async function manualQuery(page: Page, state: Scenario) {
  const before = state.nearby.length;
  await page.getByLabel('選擇公開地區', {exact: true}).selectOption('taipei-station');
  expect(state.nearby).toHaveLength(before);
  await page.getByRole('button', {name: '查詢這個地區', exact: true}).click();
  await expect.poll(() => state.nearby.slice(before).some(read => read.path === '/nearby/stores')).toBe(true);
  await expect.poll(() => state.nearby.slice(before).some(read => read.path === '/nearby/products')).toBe(true);
  await expect(page.getByLabel('附近店家探索地圖', {exact: true})).toBeVisible();
  await expect(page.getByRole('heading', {name: '晨光麵包坊', exact: true})).toBeVisible();
}
async function openExplorer(page: Page, state: Scenario) {
  await page.goto('/');
  await page.getByRole('button', {name: '先手動選地區', exact: true}).click();
  await login(page);
  await manualQuery(page, state);
}
async function activeWatches(page: Page) {
  return page.evaluate(() => [...window.__explorerGeo.active]);
}
async function waitForWorker(page: Page) {
  await expect.poll(() => page.evaluate(async () => (await navigator.serviceWorker.getRegistration('/'))?.active?.state)).toBe('activated');
  await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true);
}
async function cacheSummary(page: Page) {
  return page.evaluate(async ({tokens, emails}) => {
    const secrets = [...Object.values(tokens), ...Object.values(emails), 'PRIVATE EXPLORER'];
    const entries: {cache: string; url: string; hasPrivateData: boolean}[] = [];
    const names = await caches.keys();
    for (const name of names) {
      const cache = await caches.open(name);
      for (const request of await cache.keys()) {
        const response = await cache.match(request);
        const text = response ? await response.clone().text() : '';
        entries.push({cache: name, url: request.url, hasPrivateData: secrets.some(secret => text.includes(secret) || request.url.includes(secret))});
      }
    }
    return {names, entries};
  }, {tokens, emails});
}
test.afterEach(async ({page}) => {
  const state = scenarios.get(page);
  if (state) expect(state.unexpected, 'Every external request must have an explicit fixture').toEqual([]);
});

test('manual area selection queries only after confirmation and never asks for GPS', async ({page, context}, testInfo) => {
  const state = await mockScenario(page, context);
  await page.goto('/');
  expect(await page.evaluate(() => window.__explorerGeo.requests)).toBe(0);
  await page.getByRole('button', {name: '先手動選地區', exact: true}).click();
  await login(page);
  const before = state.nearby.length;
  await page.getByLabel('選擇公開地區', {exact: true}).selectOption('taipei-station');
  await page.waitForTimeout(200);
  expect(state.nearby).toHaveLength(before);
  await manualQuery(page, state);
  expect(await page.evaluate(() => window.__explorerGeo.requests)).toBe(0);
  expect(await activeWatches(page)).toEqual([]);
  for (const read of state.nearby.slice(before)) {
    expect(read.latitude).toBeGreaterThan(25.04);
    expect(read.latitude).toBeLessThan(25.06);
    expect(read.longitude).toBeGreaterThan(121.50);
    expect(read.longitude).toBeLessThan(121.53);
  }
  const image = testInfo.outputPath('explorer-mobile-initial.png');
  await page.screenshot({path: image, fullPage: true});
  await testInfo.attach('Initial mobile explorer', {path: image, contentType: 'image/png'});
});

test('search matches current store names and product names without another API query', async ({page, context}) => {
  const state = await mockScenario(page, context);
  await openExplorer(page, state);
  const before = state.nearby.length;
  const search = page.getByLabel('搜尋本次店家或商品', {exact: true});
  await search.fill('青葉餐桌');
  await expect(page.getByRole('heading', {name: '青葉餐桌', exact: true})).toBeVisible();
  await expect(page.getByRole('heading', {name: '南瓜餐盒', exact: true})).toBeVisible();
  await expect(page.getByRole('heading', {name: '分享餐包', exact: true})).toHaveCount(0);
  await search.fill('香草吐司');
  await expect(page.getByRole('heading', {name: '晨光麵包坊', exact: true})).toBeVisible();
  await expect(page.getByRole('heading', {name: '香草吐司', exact: true})).toBeVisible();
  await expect(page.getByRole('heading', {name: '南瓜餐盒', exact: true})).toHaveCount(0);
  await search.clear();
  expect(state.nearby).toHaveLength(before);
});

test('free and discounted filters exclude full-price items and do not refetch', async ({page, context}) => {
  const state = await mockScenario(page, context);
  await openExplorer(page, state);
  const before = state.nearby.length;
  await page.getByRole('button', {name: '免費', exact: true}).click();
  await expect(page.getByRole('heading', {name: '分享餐包', exact: true})).toBeVisible();
  await expect(page.getByRole('heading', {name: '香草吐司', exact: true})).toHaveCount(0);
  await expect(page.getByRole('heading', {name: '燕麥餅乾', exact: true})).toHaveCount(0);
  await page.getByRole('button', {name: '折扣', exact: true}).click();
  await expect(page.getByRole('heading', {name: '香草吐司', exact: true})).toBeVisible();
  await expect(page.getByRole('heading', {name: '分享餐包', exact: true})).toHaveCount(0);
  await expect(page.getByRole('heading', {name: '燕麥餅乾', exact: true})).toHaveCount(0);
  await page.getByRole('button', {name: '全部', exact: true}).click();
  await expect(page.getByRole('heading', {name: '燕麥餅乾', exact: true})).toBeVisible();
  expect(state.nearby).toHaveLength(before);
});

test('FamilyMart product search remains informational and respects free versus discount filters', async ({page, context}) => {
  const state = await mockScenario(page, context);
  await openExplorer(page, state);
  await expect.poll(() => state.familyReads).toBeGreaterThan(0);
  const before = {nearby: state.nearby.length, family: state.familyReads};
  await page.getByLabel('搜尋本次店家或商品', {exact: true}).fill('照燒雞腿');
  const marker = page.getByTestId('explorer-store-family:family-station');
  await expect(marker).toBeVisible();
  await expect(page.getByTestId('explorer-store-store-a')).toHaveCount(0);
  await marker.click();
  const selected = page.getByRole('region', {name: '選取的全家門市', exact: true});
  await expect(selected.getByRole('heading', {name: '全家車站店', exact: true})).toBeVisible();
  await expect(selected.getByText('照燒雞腿', {exact: true})).toBeVisible();
  await expect(selected.getByRole('button', {name: /預約|核銷|取貨/})).toHaveCount(0);
  await page.getByRole('button', {name: '免費', exact: true}).click();
  await expect(marker).toHaveCount(0);
  await page.getByRole('button', {name: '折扣', exact: true}).click();
  await expect(marker).toBeVisible();
  expect(state.nearby).toHaveLength(before.nearby);
  expect(state.familyReads).toBe(before.family);
});

test('reconfirming the same public area preserves nearby and FamilyMart query caches', async ({page, context}) => {
  const state = await mockScenario(page, context);
  await openExplorer(page, state);
  await expect.poll(() => state.familyReads).toBeGreaterThan(0);
  const before = {nearby: state.nearby.length, family: state.familyReads};
  await page.getByRole('button', {name: '查詢這個地區', exact: true}).click();
  await page.waitForTimeout(200);
  expect(state.nearby).toHaveLength(before.nearby);
  expect(state.familyReads).toBe(before.family);
});

test('searching into a different store clears the previous review panel and rating', async ({page, context}) => {
  const state = await mockScenario(page, context);
  await openExplorer(page, state);
  const firstReview = page.getByRole('button', {name: /4\.9 ★.*1則評論/});
  await expect(firstReview).toBeVisible();
  await firstReview.click();
  await expect(page.getByText('晨光店專屬評論', {exact: true})).toBeVisible();
  await page.getByLabel('搜尋本次店家或商品', {exact: true}).fill('青葉餐桌');
  await expect(page.getByRole('heading', {name: '青葉餐桌', exact: true})).toBeVisible();
  await expect(page.getByRole('heading', {name: '南瓜餐盒', exact: true})).toBeVisible();
  await expect(page.getByText('晨光店專屬評論', {exact: true})).toHaveCount(0);
  await expect(firstReview).toHaveCount(0);
  const nextReview = page.getByRole('button', {name: /2\.0 ★.*1則評論/});
  await expect(nextReview).toBeVisible();
  await nextReview.click();
  await expect(page.getByText('青葉店專屬評論', {exact: true})).toBeVisible();
});

test('relocation after manual browsing asks again before reading GPS', async ({page, context}) => {
  const state = await mockScenario(page, context);
  await openExplorer(page, state);
  expect(await page.evaluate(() => window.__explorerGeo.requests)).toBe(0);
  await page.getByRole('button', {name: '重新定位', exact: true}).click();
  const consent = page.getByRole('dialog', {name: '探索附近定位說明', exact: true});
  await expect(consent).toBeVisible();
  expect(await page.evaluate(() => window.__explorerGeo.requests)).toBe(0);
  await consent.getByRole('button', {name: '先手動選地區', exact: true}).click();
  expect(await page.evaluate(() => window.__explorerGeo.requests)).toBe(0);
  await page.getByRole('button', {name: '重新定位', exact: true}).click();
  await consent.getByRole('button', {name: '同意並探索附近', exact: true}).click();
  await expect.poll(() => page.evaluate(() => window.__explorerGeo.requests)).toBe(1);
});

test('GPS denial still allows an explicit public-area query', async ({page, context}) => {
  const state = await mockScenario(page, context, true);
  await page.goto('/');
  await page.getByRole('button', {name: '同意並探索附近', exact: true}).click();
  await expect(page.getByRole('status').filter({hasText: '未允許定位'})).toBeVisible();
  expect(await page.evaluate(() => window.__explorerGeo.requests)).toBe(1);
  expect(state.nearby).toHaveLength(0);
  await login(page);
  await manualQuery(page, state);
  expect(await page.evaluate(() => window.__explorerGeo.requests)).toBe(1);
  expect(await activeWatches(page)).toEqual([]);
});

test('follow moves a draft viewport; query requires confirmation and stopped callbacks stay ignored', async ({page, context}) => {
  const state = await mockScenario(page, context);
  await openExplorer(page, state);
  const before = state.nearby.length;
  const query = page.getByRole('button', {name: '搜尋此區域', exact: true});
  await page.getByRole('button', {name: '開啟跟隨', exact: true}).click();
  await expect.poll(() => activeWatches(page)).toEqual([1]);
  await page.evaluate(() => window.__explorerGeo.emit([25.0505, 121.5205]));
  await page.waitForTimeout(400);
  expect(state.nearby).toHaveLength(before);
  await expect(query).toBeEnabled();
  await page.getByRole('button', {name: '停止跟隨', exact: true}).click();
  await expect.poll(() => activeWatches(page)).toEqual([]);
  expect(await page.evaluate(() => window.__explorerGeo.cleared)).toEqual([1]);
  await page.evaluate(() => window.__explorerGeo.late(1, [24.1477, 120.6736]));
  await page.waitForTimeout(400);
  expect(state.nearby).toHaveLength(before);
  await query.click();
  await expect.poll(() => state.nearby.slice(before).some(read => read.path === '/nearby/products')).toBe(true);
  await expect.poll(() => state.nearby.slice(before).some(read => read.path === '/nearby/stores')).toBe(true);
  for (const read of state.nearby.slice(before)) {
    expect(read.latitude).toBeCloseTo(25.0505, 4);
    expect(read.longitude).toBeCloseTo(121.5205, 4);
  }
});

test('follow clears on navigation and page hiding and can restart without duplicate watches', async ({page, context}) => {
  const state = await mockScenario(page, context);
  await openExplorer(page, state);
  await page.getByRole('button', {name: '開啟跟隨', exact: true}).click();
  await expect.poll(() => activeWatches(page)).toEqual([1]);
  await page.getByRole('link', {name: '個人中心', exact: true}).click();
  await expect.poll(() => activeWatches(page)).toEqual([]);
  expect(await page.evaluate(() => window.__explorerGeo.cleared)).toEqual([1]);
  await page.getByRole('link', {name: '探索地圖', exact: true}).click();
  await page.getByRole('button', {name: '開啟跟隨', exact: true}).click();
  await expect.poll(() => activeWatches(page)).toEqual([2]);
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => 'hidden'});
    Object.defineProperty(document, 'hidden', {configurable: true, get: () => true});
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect.poll(() => activeWatches(page)).toEqual([]);
  expect(await page.evaluate(() => window.__explorerGeo.cleared)).toEqual([1, 2]);
});

test('cluster members let the user choose an overlapping store', async ({page, context}) => {
  const state = await mockScenario(page, context);
  await openExplorer(page, state);
  const cluster = page.getByTestId('explorer-cluster').first();
  await expect(cluster).toBeVisible();
  await cluster.click();
  const member = page.getByTestId('explorer-store-store-b');
  await expect(member).toBeVisible();
  await member.click();
  await expect(page.getByRole('heading', {name: '青葉餐桌', exact: true})).toBeVisible();
  await expect(page.getByRole('heading', {name: '南瓜餐盒', exact: true})).toBeVisible();
  await expect(page.getByRole('heading', {name: '分享餐包', exact: true})).toHaveCount(0);
});

test('rotation at 45, 90 and 180 degrees preserves the query center and cluster selection; north resets to zero', async ({page, context}, testInfo) => {
  const state = await mockScenario(page, context);
  await openExplorer(page, state);
  const map = page.getByTestId('explorer-map');
  const queryCenter = page.getByTestId('explorer-query-center');
  await expect(queryCenter).toBeVisible();
  await expect(map).toHaveAttribute('data-rotation', '0');
  const relativeQueryCenter = async () => {
    const root = await map.boundingBox();
    const marker = await queryCenter.boundingBox();
    expect(root).not.toBeNull();
    expect(marker).not.toBeNull();
    return {x: marker!.x + marker!.width / 2 - root!.x, y: marker!.y + marker!.height / 2 - root!.y};
  };
  const initial = await relativeQueryCenter();
  const before = state.nearby.length;
  const chooseClusterMember = async (id: string, name: string, item: string) => {
    await page.getByTestId('explorer-cluster').first().click();
    const chooser = page.getByTestId('explorer-cluster-list');
    await expect(chooser).toBeVisible();
    await chooser.getByTestId('explorer-store-' + id).click();
    await expect(page.getByRole('heading', {name, exact: true})).toBeVisible();
    await expect(page.getByRole('heading', {name: item, exact: true})).toBeVisible();
    await expect(chooser).toHaveCount(0);
  };
  for (const angle of [45, 90, 135, 180]) {
    await map.getByRole('button', {name: '向右旋轉地圖', exact: true}).click();
    await expect.poll(async () => Number(await map.getAttribute('data-rotation'))).toBe(angle);
    if (angle === 135) continue;
    await chooseClusterMember('store-b', '青葉餐桌', '南瓜餐盒');
    if (angle === 45) {
      const image = testInfo.outputPath('explorer-rotation-45-store.png');
      await page.screenshot({path: image, fullPage: true});
      await testInfo.attach('45-degree map with selected store', {path: image, contentType: 'image/png'});
    }
    await expect(page.getByRole('heading', {name: '分享餐包', exact: true})).toHaveCount(0);
    const current = await relativeQueryCenter();
    expect(Math.abs(current.x - initial.x), 'Query-center x offset must stay fixed while rotating').toBeLessThanOrEqual(2);
    expect(Math.abs(current.y - initial.y), 'Query-center y offset must stay fixed while rotating').toBeLessThanOrEqual(2);
    expect(state.nearby).toHaveLength(before);
    expect(await page.evaluate(() => window.__explorerGeo.requests)).toBe(0);
    expect(await activeWatches(page)).toEqual([]);
  }
  await map.getByRole('button', {name: '地圖朝北', exact: true}).click();
  await expect(map).toHaveAttribute('data-rotation', '0');
  await chooseClusterMember('store-a', '晨光麵包坊', '分享餐包');
  await expect(page.getByRole('heading', {name: '南瓜餐盒', exact: true})).toHaveCount(0);
  const north = await relativeQueryCenter();
  expect(Math.abs(north.x - initial.x)).toBeLessThanOrEqual(2);
  expect(Math.abs(north.y - initial.y)).toBeLessThanOrEqual(2);
  expect(state.nearby).toHaveLength(before);
  expect(await page.evaluate(() => window.__explorerGeo.requests)).toBe(0);
  expect(await activeWatches(page)).toEqual([]);
});

test('mobile-width sheet scrolls normally and only its handle responds to collapse and expand drags', async ({page, context}) => {
  const state = await mockScenario(page, context);
  await openExplorer(page, state);
  const sheet = page.locator('section[data-store-id="store-a"]');
  const handle = sheet.getByRole('button', {name: /^(收起|展開)店家詳情$/});
  const body = sheet.locator(':scope > div');
  await expect(handle).toHaveAttribute('aria-expanded', 'true');
  await expect(sheet.getByRole('heading', {name: '晨光麵包坊', exact: true})).toBeVisible();
  const bodyHeading = sheet.getByRole('heading', {name: '分享餐包', exact: true});
  await bodyHeading.evaluate(element => element.scrollIntoView({block: 'center', behavior: 'instant'}));
  const headingBox = await bodyHeading.boundingBox();
  expect(headingBox).not.toBeNull();
  const scrollPosition = () => body.evaluate(element => {
    let total = window.scrollY;
    for (let current: Element | null = element; current; current = current.parentElement) total += current.scrollTop;
    return total;
  });
  const beforeScroll = await scrollPosition();
  await page.mouse.move(headingBox!.x + headingBox!.width / 2, headingBox!.y + headingBox!.height / 2);
  await page.mouse.wheel(0, 250);
  await expect.poll(scrollPosition).toBeGreaterThan(beforeScroll);
  await expect(handle).toHaveAttribute('aria-expanded', 'true');
  await expect(sheet.getByRole('heading', {name: '分享餐包', exact: true})).toBeVisible();

  // Pointer movement in the content must not trigger the sheet's handle gesture.
  await bodyHeading.evaluate(element => element.scrollIntoView({block: 'center', behavior: 'instant'}));
  const contentBox = await bodyHeading.boundingBox();
  expect(contentBox).not.toBeNull();
  const contentX = contentBox!.x + contentBox!.width / 2;
  const contentY = contentBox!.y + contentBox!.height / 2;
  await page.mouse.move(contentX, contentY);
  await page.mouse.down();
  await page.mouse.move(contentX, contentY + 80, {steps: 8});
  await page.mouse.up();
  await expect(handle).toHaveAttribute('aria-expanded', 'true');
  await expect(body).toHaveCount(1);

  const dragHandle = async (distance: number) => {
    await handle.evaluate(element => element.scrollIntoView({block: 'center', behavior: 'instant'}));
    const box = await handle.boundingBox();
    expect(box).not.toBeNull();
    const x = box!.x + box!.width / 2;
    const y = box!.y + box!.height / 2;
    const viewport = page.viewportSize()!;
    const endY = Math.max(8, Math.min(viewport.height - 8, y + distance));
    expect(Math.abs(endY - y)).toBeGreaterThan(24);
    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(x, endY, {steps: 10});
    await page.mouse.up();
  };
  await dragHandle(120);
  await expect(handle).toHaveAttribute('aria-expanded', 'false');
  await expect(handle).toHaveAccessibleName('展開店家詳情');
  await expect(sheet).toHaveAttribute('data-store-id', 'store-a');
  await expect(body).toHaveCount(0);
  await expect(sheet.getByText('已收起商品卡。點上方按鈕，或向上滑動把手查看。', {exact: true})).toBeVisible();
  await expect(sheet.getByRole('heading', {name: '分享餐包', exact: true})).toHaveCount(0);
  await dragHandle(-120);
  await expect(handle).toHaveAttribute('aria-expanded', 'true');
  await expect(handle).toHaveAccessibleName('收起店家詳情');
  await expect(sheet).toHaveAttribute('data-store-id', 'store-a');
  await expect(sheet.getByRole('heading', {name: '晨光麵包坊', exact: true})).toBeVisible();
  await expect(sheet.getByRole('heading', {name: '分享餐包', exact: true})).toBeVisible();
});

test.describe('PWA offline and cache isolation', () => {
  test.use({serviceWorkers: 'allow'});

  test('activation removes only retired FoodSave caches and preserves unrelated caches', async ({page, context}) => {
    await mockScenario(page, context);
    await page.goto('/offline.html');
    await page.evaluate(async () => {
      await (await caches.open('foodsave-shell-retired-test')).put(location.origin + '/retired-private-probe', new Response('retired'));
      await (await caches.open('unrelated-app-cache-keep')).put(location.origin + '/unrelated-probe', new Response('keep'));
    });
    await page.goto('/');
    await waitForWorker(page);
    await expect.poll(() => page.evaluate(() => caches.keys())).not.toContain('foodsave-shell-retired-test');
    const cache = await cacheSummary(page);
    expect(cache.names).toContain('unrelated-app-cache-keep');
    expect(cache.names.some(name => name.startsWith(CACHE_CURRENT))).toBe(true);
    expect(cache.entries.some(entry => entry.cache.startsWith(CACHE_CURRENT) && new URL(entry.url).pathname === '/offline.html')).toBe(true);
  });

  test('two accounts leave no private API data in shell caches and offline reload uses the fallback', async ({page, context}) => {
    test.setTimeout(60_000);
    const state = await mockScenario(page, context);
    await page.goto('/');
    await page.getByRole('button', {name: '先手動選地區', exact: true}).click();
    await login(page, 'a');
    await waitForWorker(page);
    await page.getByRole('link', {name: '個人中心', exact: true}).click();
    await page.getByRole('link', {name: /通知中心/}).click();
    await expect(page.getByText('PRIVATE EXPLORER A NOTICE', {exact: true})).toBeVisible();
    await page.getByRole('link', {name: '個人中心', exact: true}).click();
    await page.getByRole('link', {name: '我的預約', exact: true}).click();
    await expect(page.getByRole('heading', {name: 'PRIVATE EXPLORER A ORDER', exact: true})).toBeVisible();
    await page.getByRole('link', {name: '個人中心', exact: true}).click();
    await page.getByRole('button', {name: '切換帳號', exact: true}).click();
    await login(page, 'b');
    await page.getByRole('link', {name: /通知中心/}).click();
    await expect(page.getByText('PRIVATE EXPLORER B NOTICE', {exact: true})).toBeVisible();
    await expect(page.getByText('PRIVATE EXPLORER A NOTICE', {exact: true})).toHaveCount(0);
    await expect(page.getByText('PRIVATE EXPLORER A ORDER', {exact: true})).toHaveCount(0);
    const cache = await cacheSummary(page);
    const own = cache.entries.filter(entry => entry.cache.startsWith(CACHE_PREFIX));
    expect(cache.names.some(name => name.startsWith(CACHE_CURRENT))).toBe(true);
    expect(own.length).toBeGreaterThan(0);
    for (const entry of own) {
      const url = new URL(entry.url);
      expect(url.origin).toBe('http://127.0.0.1:4174');
      expect(url.pathname).not.toMatch(/^\/(?:auth|me|nearby|stores|products|favorites|reservations|notifications)(?:\/|$)/);
      expect(entry.hasPrivateData).toBe(false);
    }
    const storage = await page.evaluate(() => JSON.stringify({...localStorage, ...sessionStorage}));
    for (const secret of [...Object.values(tokens), ...Object.values(emails), 'PRIVATE EXPLORER']) expect(storage).not.toContain(secret);
    state.offline = true;
    await context.setOffline(true);
    await expect(page.getByRole('status').filter({hasText: '目前離線，連線後再操作。'})).toBeVisible();
    await page.reload();
    await expect(page.getByRole('status').filter({hasText: '目前離線，連線後再操作。'})).toBeVisible();
    await expect(page.getByText('PRIVATE EXPLORER B NOTICE', {exact: true})).toHaveCount(0);
    await context.setOffline(false);
    state.offline = false;
    await page.goto('/');
    await expect(page.getByRole('button', {name: '登入', exact: true})).toBeVisible();
    await expect(page.getByText('PRIVATE EXPLORER A NOTICE', {exact: true})).toHaveCount(0);
    await expect(page.getByText('PRIVATE EXPLORER B NOTICE', {exact: true})).toHaveCount(0);
  });
});
