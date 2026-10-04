import {test} from 'node:test';
import assert from 'node:assert/strict';
import {passwordLength,passwordLengthError} from '../lib/password';
test('password limits count Unicode code points without altering whitespace',()=>{
 assert.equal(passwordLength('🍀'.repeat(14)),14);
 assert.ok(passwordLengthError('🍀'.repeat(14),15));
 assert.equal(passwordLengthError('🍀'.repeat(128),15),'');
 assert.ok(passwordLengthError('🍀'.repeat(129),15));
 assert.equal(passwordLength(' a '),3);
});
