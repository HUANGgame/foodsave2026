import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const {inspectBundle,markers}=require('../scripts/check-live-bundle.cjs');
const api='https://foodsave.example.org';
test('bundle scanner rejects every legacy catalog marker, even in an unused chunk',()=>{
 const dir=mkdtempSync(join(tmpdir(),'foodsave-bundle-'));
 try{for(const marker of markers){writeFileSync(join(dir,'unused.js'),api+';'+marker);assert.throws(()=>inspectBundle(dir,api),/Non-production data/);}writeFileSync(join(dir,'unused.js'),api+';'+Array.from('幸福飯糰').map((c:any)=>'\\u'+c.charCodeAt(0).toString(16)).join(''));assert.throws(()=>inspectBundle(dir,api),/Non-production data/);}finally{rmSync(dir,{recursive:true});}
});
test('bundle scanner requires expected API and rejects fixture endpoint in formal build',()=>{
 const dir=mkdtempSync(join(tmpdir(),'foodsave-bundle-'));
 try{writeFileSync(join(dir,'app.js'),'nothing');assert.throws(()=>inspectBundle(dir,api),/API missing/);writeFileSync(join(dir,'app.js'),api+' https://api.foodsave.test');assert.throws(()=>inspectBundle(dir,api),/Fixture API/);writeFileSync(join(dir,'app.js'),api+' /demo-prizes /vendor/store');assert.equal(inspectBundle(dir,api).demo_catalog_markers_absent,true);}finally{rmSync(dir,{recursive:true});}
});
