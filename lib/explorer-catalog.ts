import type {LiveProduct, LiveStore} from './api';
import type {ExternalStore} from './familymart';
import type {Point} from './location';

export type ExplorerFilter = 'all' | 'free' | 'discount';

type Located = {latitude: number; longitude: number};

const EARTH_RADIUS_METERS = 6_371_000;

function normalized(value: string): string {
  return value.trim().toLowerCase();
}

function validPoint(point: Point | null): point is Point {
  return Boolean(
    point &&
    Number.isFinite(point[0]) &&
    Number.isFinite(point[1]) &&
    Math.abs(point[0]) <= 90 &&
    Math.abs(point[1]) <= 180
  );
}

/** 查詢中心到門市的直線距離，並非步行距離或所需時間。 */
export function distanceMeters(
  center: Point | null,
  point: Point | null
): number | null {
  if (!validPoint(center) || !validPoint(point)) return null;

  const radians = Math.PI / 180;
  const latitudeDifference = (point[0] - center[0]) * radians;
  const longitudeDifference = (point[1] - center[1]) * radians;
  const latitude1 = center[0] * radians;
  const latitude2 = point[0] * radians;
  const haversine =
    Math.sin(latitudeDifference / 2) ** 2 +
    Math.cos(latitude1) *
      Math.cos(latitude2) *
      Math.sin(longitudeDifference / 2) ** 2;
  const bounded = Math.min(1, Math.max(0, haversine));

  return 2 * EARTH_RADIUS_METERS *
    Math.atan2(Math.sqrt(bounded), Math.sqrt(1 - bounded));
}

function byDistance<T extends Located>(
  stores: T[],
  center: Point | null
): T[] {
  if (!validPoint(center)) return stores.slice();

  return stores
    .map((store, index) => ({
      store,
      index,
      distance: distanceMeters(center, [store.latitude, store.longitude])
    }))
    .sort((a, b) => {
      if (a.distance === null) {
        return b.distance === null ? a.index - b.index : 1;
      }
      if (b.distance === null) return -1;
      return a.distance - b.distance || a.index - b.index;
    })
    .map(({store}) => store);
}

function matchesPrice(
  product: LiveProduct,
  filter: ExplorerFilter
): boolean {
  if (filter === 'all') return true;
  if (filter === 'free') return product.sale_price_minor === 0;

  return Number.isFinite(product.sale_price_minor) &&
    Number.isFinite(product.original_price_minor) &&
    product.sale_price_minor > 0 &&
    product.sale_price_minor < product.original_price_minor;
}

/** 僅比對名稱與價格，不推算庫存、食品效期或資料是否即時。 */
export function matchesFoodProduct(
  product: LiveProduct,
  query: string,
  filter: ExplorerFilter
): boolean {
  if (!matchesPrice(product, filter)) return false;

  const needle = normalized(query);
  return !needle ||
    normalized(product.name).includes(needle) ||
    normalized(product.store_name).includes(needle);
}

/**
 * 呼叫端提供 FoodSave 查詢中心 1 公里內、全部分頁讀取完成的資料。
 * 此處只篩選已載入內容，不發送請求，也不擴大為全域搜尋。
 */
export function filterFoodStores(
  stores: LiveStore[],
  products: LiveProduct[],
  query: string,
  filter: ExplorerFilter,
  center: Point | null
): LiveStore[] {
  const needle = normalized(query);
  const eligibleStoreIds = new Set<string>();
  const matchingStoreIds = new Set<string>();

  for (const product of products) {
    if (!matchesPrice(product, filter)) continue;
    eligibleStoreIds.add(product.store_id);
    if (matchesFoodProduct(product, needle, filter)) {
      matchingStoreIds.add(product.store_id);
    }
  }

  const filtered = stores.filter(store => {
    if (filter !== 'all' && !eligibleStoreIds.has(store.id)) return false;

    return !needle ||
      normalized(store.name).includes(needle) ||
      matchingStoreIds.has(store.id);
  });

  return byDistance(filtered, center);
}

/**
 * 全家資料由來源正規化限制為當次最多 200 間門市、每店 200 項商品。
 * 全家屬折扣資訊來源；沒有免費或個別價格資料，不推算折扣金額。
 * 保留門市完整商品明細與原始數量，未知數量仍為 null。
 */
export function filterFamilyStores(
  stores: ExternalStore[],
  query: string,
  filter: ExplorerFilter,
  center: Point | null
): ExternalStore[] {
  if (filter === 'free') return [];

  const needle = normalized(query);
  const filtered = stores.filter(store =>
    !needle ||
    normalized(store.name).includes(needle) ||
    normalized(store.address).includes(needle) ||
    store.products.some(product =>
      normalized(product.name).includes(needle)
    )
  );

  return byDistance(filtered, center);
}
