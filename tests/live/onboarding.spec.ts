import {test,expect} from '@playwright/test';
import {randomUUID} from 'node:crypto';

test('same account creates its store and uses existing first product form',async({page})=>{
 let assigned=false,submitted:any=null;
 const token=randomUUID(),store=randomUUID();
 await page.route('https://api.foodsave.test/**',async route=>{
  const request=route.request(),path=new URL(request.url()).pathname;
  const json=(body:unknown,status=200)=>route.fulfill({json:body,status});
  if(path==='/auth/login')return json({access_token:token});
  if(path==='/me')return json({id:'synthetic-vendor',email:'vendor@example.test',role:'consumer',is_vendor:assigned,exp:0,spins:0});
  if(path==='/vendor/store'&&request.method()==='POST'){assigned=true;expect(request.postDataJSON()).toMatchObject({name:'我的店',latitude:25,longitude:121});return json({id:store},201);}
  if(path==='/vendor/catalog')return json({stores:assigned?[{id:store,name:'新指派測試店',service_mode:'information',pending_orders:0}]:[],products:submitted?[{...submitted,id:'synthetic-product',revision:1}]:[]});
  if(path==='/vendor/products'&&request.method()==='POST'){submitted=request.postDataJSON();return json({id:'synthetic-product',revision:1},201);}
  return json([]);
 });
 await page.addInitScript(()=>{navigator.geolocation.getCurrentPosition=(ok)=>ok({coords:{latitude:25,longitude:121}} as GeolocationPosition);});
 await page.goto('/vendor/');
 await page.getByLabel('電子郵件').fill('vendor@example.test');await page.getByLabel('密碼',{exact:true}).fill(randomUUID());await page.getByRole('button',{name:'登入',exact:true}).click();
 await expect(page.getByRole('heading',{name:'建立我的店家'})).toBeVisible();
 await page.getByLabel('店家名稱').fill('我的店');await page.getByRole('button',{name:'使用目前位置'}).click();await page.getByRole('button',{name:'建立店家',exact:true}).click();
 await expect(page.getByRole('heading',{name:'開始上架第一件商品'})).toBeVisible();
 await expect(page.getByLabel('新指派測試店 服務模式')).toHaveValue('information');
 await page.getByRole('button',{name:'上架第一件商品',exact:true}).click();
 await page.getByLabel('商品名稱',{exact:true}).fill('首件測試便當');await page.getByLabel('已授權商品照片網址').fill('https://images.example.test/meal.png');await page.getByLabel('原價（元）').fill('100');await page.getByLabel('惜食價（元）').fill('50');await page.getByLabel('剩餘數量').fill('2');await page.getByLabel('領取截止').fill('2027-01-01T12:00');await page.getByRole('button',{name:'儲存商品',exact:true}).click();
 await expect(page.getByText('商品已儲存',{exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'開始上架第一件商品'})).toHaveCount(0);
 expect(submitted).toMatchObject({store_id:store,name:'首件測試便當',available_quantity:2,revision:1,active:true});
});
