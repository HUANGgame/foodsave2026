import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
const {checkIdentity,verifyApk,CERT}=require('../scripts/check-android-release.cjs');
const signature=`Verified using v2 scheme (APK Signature Scheme v2): true\nNumber of signers: 1\nSigner #1 certificate SHA-256 digest: ${CERT}\n`;
const badging="package: name='tw.foodsave.demo' versionCode='18' versionName='next-test'\n";
const env:NodeJS.ProcessEnv={NODE_ENV:"test",NEXT_PUBLIC_API_BASE_URL:'https://foodsave.example.org',NEXT_PUBLIC_APP_MODE:'live',NEXT_PUBLIC_OPERATOR_NAME:'HUANG',NEXT_PUBLIC_PRIVACY_CONTACT:'contact@example.org',NEXT_PUBLIC_RETENTION_SUMMARY:'approved',NEXT_PUBLIC_PRIVACY_POLICY_COMPLETE:'true'};
test('web gate accepts complete approved web configuration without Android identity',()=>{
 const result=spawnSync(process.execPath,['scripts/check-release-config.cjs'],{env,encoding:'utf8'});
 assert.equal(result.status,0,result.stderr);
});
test('web gate still rejects every missing policy/operator field and unsafe API/mode',()=>{
 for(const key of Object.keys(env).filter(k=>k!=="NODE_ENV")){
  const incomplete={...env};delete incomplete[key];
  assert.notEqual(spawnSync(process.execPath,['scripts/check-release-config.cjs'],{env:incomplete}).status,0,key);
 }
 for(const [key,value] of [['NEXT_PUBLIC_API_BASE_URL','http://foodsave.example.org'],['NEXT_PUBLIC_API_BASE_URL','https://api.foodsave.test'],['NEXT_PUBLIC_API_BASE_URL','https://u:p@api.example.org'],['NEXT_PUBLIC_API_BASE_URL','https://api.example.org?x=1'],['NEXT_PUBLIC_APP_MODE','demo'],['NEXT_PUBLIC_PRIVACY_POLICY_COMPLETE','false']]){
  assert.notEqual(spawnSync(process.execPath,['scripts/check-release-config.cjs'],{env:{...env,[key]:value}}).status,0);
 }
});
test('Android parsed final output requires exact package, increased version and verified matching signer',()=>{
 assert.equal(checkIdentity(badging,signature).version_code,18);
 for(const [apk,sig] of [[badging.replace('tw.foodsave.demo','tw.foodsave.new'),signature],[badging.replace("'18'","'17'"),signature],[badging.replace("'18'","'7'"),signature],[badging.replace("'18'","'99999999999999'"),signature],[badging,signature.replace(CERT,'0'.repeat(64))],[badging,signature.replace(': true',': false')],[badging,signature.replace('signers: 1','signers: 2')],[badging,signature+`Signer #2 certificate SHA-256 digest: ${CERT}\n`],['',signature],[badging,'']])assert.throws(()=>checkIdentity(apk,sig));
});
test('Android gate executes verifier on immutable snapshot, fails closed and never signs',()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'foodsave-gate-test-'));
 try{
  const apk=path.join(root,'input.apk');fs.writeFileSync(apk,'synthetic bytes; NOT an APK');
  for(const name of ['apksigner','aapt'])fs.writeFileSync(path.join(root,name),'',{mode:0o700});
  const calls:any[]=[];
  const run=(file:string,args:string[],options:any)=>{calls.push([file,args]);assert.equal(options.shell,false);assert.notEqual(args.at(-1),apk);assert.equal(fs.readFileSync(args.at(-1)!,'utf8'),'synthetic bytes; NOT an APK');return {status:0,stdout:path.basename(file)==='apksigner'?signature:badging};};
  assert.equal(verifyApk(apk,root,run).application_id,'tw.foodsave.demo');
  assert.deepEqual(calls.map(c=>c[1].slice(0,-1)),[['verify','--verbose','--print-certs'],['dump','badging']]);
  assert.throws(()=>verifyApk(apk,root,()=>({status:1,stdout:signature})),/failed/);
  assert.throws(()=>verifyApk(apk,root,()=>({error:Error('timeout'),status:null})),/failed/);
  assert.throws(()=>verifyApk(apk,root,(f:string,a:string[],o:any)=>{fs.writeFileSync(apk,'changed');return run(f,a,o);}),/changed/);
  assert.throws(()=>verifyApk(apk,path.join(root,'missing'),run));
  assert.throws(()=>verifyApk(undefined,root,run));
 }finally{fs.rmSync(root,{recursive:true,force:true});}
});
