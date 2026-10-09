/* Only public static assets are cached. API data, locations and actions never are. */
const CACHE='foodsave-shell-v1-20261009';
const PUBLIC_FILES=['/offline.html','/manifest.webmanifest','/icons/foodsave.svg'];
self.addEventListener('install',event=>{
 event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(PUBLIC_FILES)));
});
self.addEventListener('activate',event=>{
 event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('foodsave-shell-')&&key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim()));
});
self.addEventListener('fetch',event=>{
 const request=event.request,url=new URL(request.url);
 if(request.method!=='GET'||url.origin!==self.location.origin||request.headers.has('Authorization'))return;
 if(request.mode==='navigate'){
  event.respondWith(fetch(request).catch(async()=>await caches.match('/offline.html')||new Response('目前離線，連線後再操作。',{status:503,headers:{'Content-Type':'text/plain; charset=utf-8'}})));
  return;
 }
 if(url.search||(!PUBLIC_FILES.includes(url.pathname)&&!url.pathname.startsWith('/_next/static/')))return;
 event.respondWith(caches.open(CACHE).then(async cache=>{
  const cached=await cache.match(request);if(cached)return cached;
  const response=await fetch(request);
  if(response.ok&&response.type==='basic'&&!response.headers.has('Set-Cookie'))await cache.put(request,response.clone());
  return response;
 }));
});
