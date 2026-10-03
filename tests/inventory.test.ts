import test from 'node:test';
import assert from 'node:assert/strict';
import {canReserve,stockLabel} from '../lib/inventory';
test('information and external providers never expose reservation actions',()=>{
 assert.equal(canReserve({source:'foodsave',service_mode:'reservation'}),true);
 for(const source of ['foodsave','seven-eleven','familymart',undefined])assert.equal(canReserve({source,service_mode:'information'}),false);
 for(const source of ['seven-eleven','familymart',undefined])assert.equal(canReserve({source,service_mode:'reservation'}),false);
 assert.equal(canReserve({source:'foodsave'}),false);
 assert.equal(stockLabel(null),'數量待確認');assert.equal(stockLabel(0),'剩餘 0 份');
});
