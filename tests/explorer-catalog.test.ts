import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {LiveProduct, LiveStore} from '../lib/api';
import type {ExternalStore} from '../lib/familymart';
import type {Point} from '../lib/location';
import {
  distanceMeters,
  filterFamilyStores,
  filterFoodStores,
  matchesFoodProduct
} from '../lib/explorer-catalog';

function foodStore(
  id: string,
  changes: Partial<LiveStore> = {}
): LiveStore {
  return {
    id,
    vendor_id: `vendor-${id}`,
    name: `門市 ${id}`,
    latitude: 25,
    longitude: 121,
    service_mode: 'reservation',
    product_count: 1,
    ...changes
  };
}

function foodProduct(
  id: string,
  storeId: string,
  changes: Partial<LiveProduct> = {}
): LiveProduct {
  return {
    id,
    store_id: storeId,
    store_name: `門市 ${storeId}`,
    name: '原味飯糰',
    photo_url: '',
    latitude: 25,
    longitude: 121,
    original_price_minor: 6_000,
    sale_price_minor: 3_000,
    available_quantity: null,
    pickup_deadline: '2026-10-09T12:00:00Z',
    revision: 1,
    ...changes
  };
}

function familyStore(
  id: string,
  changes: Partial<ExternalStore> = {}
): ExternalStore {
  return {
    id,
    name: `全家 ${id} 店`,
    address: '臺北市信義區松仁路 1 號',
    latitude: 25,
    longitude: 121,
    sourceUpdatedAt: null,
    products: [{
      id: `product-${id}`,
      name: '原味飯糰',
      quantity: null,
      category: '鮮食'
    }],
    quantity: null,
    ...changes
  };
}

function ids(stores: {id: string}[]): string[] {
  return stores.map(store => store.id);
}

test('距離使用緯度、經度順序，結果單位為公尺', () => {
  assert.equal(distanceMeters([25, 121], [25, 121]), 0);

  const oneDegree = distanceMeters([0, 0], [1, 0]);
  assert.ok(oneDegree !== null);
  assert.ok(Math.abs(oneDegree - 111_194.9266) < 1);

  const crossingDateLine = distanceMeters([0, 179.9], [0, -179.9]);
  assert.ok(crossingDateLine !== null);
  assert.ok(Math.abs(crossingDateLine - 22_238.9853) < 1);
});

test('無效座標不產生 NaN 或誤導性的零距離', () => {
  const invalid: Point[] = [
    [NaN, 121],
    [25, Infinity],
    [-Infinity, 121],
    [90.01, 121],
    [-90.01, 121],
    [25, 180.01],
    [25, -180.01]
  ];

  assert.equal(distanceMeters(null, [25, 121]), null);
  assert.equal(distanceMeters([25, 121], null), null);

  for (const point of invalid) {
    assert.equal(distanceMeters(point, [25, 121]), null);
    assert.equal(distanceMeters([25, 121], point), null);
  }

  const antipodal = distanceMeters([90, 0], [-90, 180]);
  assert.ok(antipodal !== null && Number.isFinite(antipodal));
});

test('FoodSave 搜尋去除頭尾空白，並比對商品與門市名稱', () => {
  const product = foodProduct('p1', 's1', {
    name: '海苔飯糰',
    store_name: 'Small CAFE'
  });

  assert.equal(matchesFoodProduct(product, '  飯糰  ', 'all'), true);
  assert.equal(matchesFoodProduct(product, '  cafe  ', 'all'), true);
  assert.equal(matchesFoodProduct(product, '   ', 'all'), true);
  assert.equal(matchesFoodProduct(product, '便當', 'all'), false);
});

test('免費與折扣分開篩選，原價商品不算折扣', () => {
  const free = foodProduct('free', 's1', {sale_price_minor: 0});
  const discount = foodProduct('discount', 's1');
  const fullPrice = foodProduct('full', 's1', {
    sale_price_minor: 6_000
  });

  assert.equal(matchesFoodProduct(free, '', 'free'), true);
  assert.equal(matchesFoodProduct(free, '', 'discount'), false);
  assert.equal(matchesFoodProduct(discount, '', 'free'), false);
  assert.equal(matchesFoodProduct(discount, '', 'discount'), true);
  assert.equal(matchesFoodProduct(fullPrice, '', 'discount'), false);

  for (const product of [free, discount, fullPrice]) {
    assert.equal(matchesFoodProduct(product, '', 'all'), true);
  }
});

test('異常價格不被判定為折扣商品', () => {
  const changes: Partial<LiveProduct>[] = [
    {sale_price_minor: -1},
    {sale_price_minor: NaN},
    {sale_price_minor: Infinity},
    {original_price_minor: NaN},
    {original_price_minor: Infinity},
    {original_price_minor: -1},
    {sale_price_minor: 7_000}
  ];

  for (const change of changes) {
    assert.equal(
      matchesFoodProduct(foodProduct('p1', 's1', change), '', 'discount'),
      false
    );
  }
});

test('FoodSave 門市名稱搜尋仍須符合選擇的商品價格類別', () => {
  const stores = [
    foodStore('free', {name: '夜市一店'}),
    foodStore('discount', {name: '夜市二店'}),
    foodStore('full', {name: '夜市三店'})
  ];
  const products = [
    foodProduct('p1', 'free', {sale_price_minor: 0}),
    foodProduct('p2', 'discount'),
    foodProduct('p3', 'full', {sale_price_minor: 6_000})
  ];

  assert.deepEqual(
    ids(filterFoodStores(stores, products, '  夜市 ', 'free', null)),
    ['free']
  );
  assert.deepEqual(
    ids(filterFoodStores(stores, products, '夜市', 'discount', null)),
    ['discount']
  );
  assert.deepEqual(
    ids(filterFoodStores(stores, products, '夜市', 'all', null)),
    ['free', 'discount', 'full']
  );
});

test('商品名稱與價格類別必須由同一項商品符合', () => {
  const stores = [foodStore('s1', {name: '街角小店'})];
  const products = [
    foodProduct('free-rice', 's1', {
      name: '飯糰',
      store_name: '街角小店',
      sale_price_minor: 0
    }),
    foodProduct('discount-yogurt', 's1', {
      name: '優格',
      store_name: '街角小店'
    })
  ];

  assert.deepEqual(
    filterFoodStores(stores, products, '飯糰', 'discount', null),
    []
  );
  assert.deepEqual(
    ids(filterFoodStores(stores, products, '優格', 'discount', null)),
    ['s1']
  );
});

test('門市比對使用 store_id，不會把其他門市商品接過來', () => {
  const stores = [foodStore('s1')];
  const products = [
    foodProduct('p1', 'other-store', {name: '限定便當'})
  ];

  assert.deepEqual(
    filterFoodStores(stores, products, '限定便當', 'all', null),
    []
  );
  assert.deepEqual(
    filterFoodStores(stores, products, '', 'discount', null),
    []
  );
});

test('全部保留無商品門市，免費與折扣需要對應商品', () => {
  const stores = [foodStore('empty', {
    name: '尚無商品門市',
    product_count: 0
  })];

  assert.deepEqual(
    ids(filterFoodStores(stores, [], '   ', 'all', null)),
    ['empty']
  );
  assert.deepEqual(
    ids(filterFoodStores(stores, [], '尚無商品', 'all', null)),
    ['empty']
  );
  assert.deepEqual(filterFoodStores(stores, [], '', 'free', null), []);
  assert.deepEqual(filterFoodStores(stores, [], '', 'discount', null), []);
  assert.deepEqual(
    filterFoodStores(stores, [], '不存在的商品', 'all', null),
    []
  );
});

test('FoodSave 距離排序不改動輸入，無效座標排在最後', () => {
  const stores = [
    foodStore('invalid-first', {latitude: NaN}),
    foodStore('far', {latitude: 25.02}),
    foodStore('near-first', {latitude: 25.001}),
    foodStore('near-second', {latitude: 25.001}),
    foodStore('invalid-last', {longitude: Infinity})
  ];
  const originalIds = ids(stores);
  Object.freeze(stores);
  for (const store of stores) Object.freeze(store);

  const result = filterFoodStores(stores, [], '', 'all', [25, 121]);

  assert.deepEqual(ids(result), [
    'near-first',
    'near-second',
    'far',
    'invalid-first',
    'invalid-last'
  ]);
  assert.deepEqual(ids(stores), originalIds);
  assert.notEqual(result, stores);
  assert.equal(result[0], stores[2]);
});

test('未提供有效查詢中心時保留來源順序', () => {
  const stores = [
    foodStore('far', {latitude: 25.02}),
    foodStore('near', {latitude: 25.001})
  ];

  for (const center of [null, [NaN, 121] as Point, [91, 121] as Point]) {
    assert.deepEqual(
      ids(filterFoodStores(stores, [], '', 'all', center)),
      ['far', 'near']
    );
  }
});

test('FoodSave 不額外截斷已讀取全部分頁的資料', () => {
  const stores = Array.from({length: 305}, (_, index) =>
    foodStore(`s${index}`)
  );
  const products = [foodProduct('last-product', 's304', {
    name: '最後一頁商品'
  })];

  assert.equal(
    filterFoodStores(stores, products, '', 'all', null).length,
    305
  );
  assert.deepEqual(
    ids(filterFoodStores(stores, products, '最後一頁', 'all', null)),
    ['s304']
  );
});

test('FoodSave 商品與門市中繼資料、未知庫存保持原值', () => {
  const store = foodStore('s1', {
    name: '街角小店',
    product_count: 17
  });
  const product = foodProduct('p1', 's1', {
    store_name: '街角小店',
    available_quantity: null,
    stale: true,
    sourceUpdatedAt: null
  });
  const stores = [store];
  const products = [product];

  Object.freeze(store);
  Object.freeze(product);
  Object.freeze(stores);
  Object.freeze(products);

  const result = filterFoodStores(
    stores,
    products,
    '街角小店',
    'discount',
    [25, 121]
  );

  assert.equal(result[0], store);
  assert.equal(result[0].product_count, 17);
  assert.equal(matchesFoodProduct(product, '街角小店', 'discount'), true);
  assert.equal(product.available_quantity, null);
  assert.equal(product.stale, true);
  assert.equal(product.sourceUpdatedAt, null);
});

test('名稱与價格篩選不將零庫存或未知庫存改寫成可領取數量', () => {
  const unknown = foodProduct('unknown', 's1', {
    available_quantity: null
  });
  const empty = foodProduct('empty', 's1', {
    available_quantity: 0
  });

  assert.equal(matchesFoodProduct(unknown, '', 'discount'), true);
  assert.equal(matchesFoodProduct(empty, '', 'discount'), true);
  assert.equal(unknown.available_quantity, null);
  assert.equal(empty.available_quantity, 0);
});

test('全家搜尋門市名稱、地址與商品名稱，並忽略頭尾空白和大小寫', () => {
  const stores = [
    familyStore('s1', {
      name: '全家 CIVIC 店',
      address: '臺北市信義區市府路 1 號',
      products: [{
        id: 'p1',
        name: '焗烤義大利麵',
        quantity: 2,
        category: '鮮食'
      }]
    }),
    familyStore('s2', {
      name: '全家河岸店',
      address: '新北市板橋區文化路 2 號'
    })
  ];

  for (const query of ['  civic  ', '  市府路 ', ' 義大利麵 ']) {
    assert.deepEqual(
      ids(filterFamilyStores(stores, query, 'all', null)),
      ['s1']
    );
  }
  assert.deepEqual(
    filterFamilyStores(stores, '不存在的商品', 'all', null),
    []
  );
});

test('全家沒有免費價格資料，全部與折扣均保留符合搜尋的門市', () => {
  const stores = [familyStore('s1')];

  assert.deepEqual(filterFamilyStores(stores, '', 'free', null), []);
  assert.deepEqual(
    ids(filterFamilyStores(stores, '飯糰', 'all', null)),
    ['s1']
  );
  assert.deepEqual(
    ids(filterFamilyStores(stores, '飯糰', 'discount', null)),
    ['s1']
  );
});

test('全家命中門市、地址或其中商品時保留完整明細和未知庫存', () => {
  const store = familyStore('s1', {
    name: '全家市府店',
    address: '臺北市信義區市府路 1 號',
    products: [
      {id: 'unknown', name: '飯糰', quantity: null, category: '鮮食'},
      {id: 'empty', name: '沙拉', quantity: 0, category: '鮮食'},
      {id: 'known', name: '麵包', quantity: 2, category: '麵包'}
    ],
    quantity: null,
    sourceUpdatedAt: '2026-10-09T18:30:00+08:00'
  });
  const stores = [store];
  const originalProducts = store.products;

  for (const product of store.products) Object.freeze(product);
  Object.freeze(store.products);
  Object.freeze(store);
  Object.freeze(stores);

  for (const query of ['市府店', '市府路', '飯糰']) {
    const result = filterFamilyStores(stores, query, 'discount', null);

    assert.equal(result[0], store);
    assert.equal(result[0].products, originalProducts);
    assert.equal(result[0].products.length, 3);
    assert.equal(result[0].products[0].quantity, null);
    assert.equal(result[0].products[1].quantity, 0);
    assert.equal(result[0].quantity, null);
    assert.equal(
      result[0].sourceUpdatedAt,
      '2026-10-09T18:30:00+08:00'
    );
  }
});

test('全家距離排序保留同距離順序，不修改輸入', () => {
  const stores = [
    familyStore('far', {latitude: 25.02}),
    familyStore('invalid', {longitude: NaN}),
    familyStore('near-first', {latitude: 25.001}),
    familyStore('near-second', {latitude: 25.001})
  ];
  const originalIds = ids(stores);
  Object.freeze(stores);

  const result = filterFamilyStores(stores, '', 'all', [25, 121]);

  assert.deepEqual(
    ids(result),
    ['near-first', 'near-second', 'far', 'invalid']
  );
  assert.deepEqual(ids(stores), originalIds);
  assert.notEqual(result, stores);
  assert.equal(result[0], stores[2]);

  assert.deepEqual(
    ids(filterFamilyStores(stores, '', 'discount', null)),
    originalIds
  );
  assert.deepEqual(
    ids(filterFamilyStores(stores, '', 'all', [NaN, 121])),
    originalIds
  );
});
