// Read-only final APK verification. Never builds, signs, downloads or generates a key.
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process');
const PACKAGE='tw.foodsave.demo',BASE_VERSION=17;
const CERT='396fa79cddf94114642a391635e4682ba9002fc50082a1c229931f0fac5bcc76';
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
function checkIdentity(badging,signature){
 const packages=[...badging.matchAll(/^package: name='([^']+)' versionCode='([0-9]+)' versionName='([^']*)'/gm)];
 if(packages.length!==1||packages[0][1]!==PACKAGE)throw Error('Final APK package must match existing '+PACKAGE);
 const version=Number(packages[0][2]);
 if(!Number.isSafeInteger(version)||version<=BASE_VERSION||version>2100000000)throw Error('Final APK versionCode must be greater than 17 and valid');
 if(!/^Verified using v2 scheme \(APK Signature Scheme v2\): true\s*$/m.test(signature))throw Error('Verified APK v2 signature required');
 if(!/^Number of signers: 1\s*$/m.test(signature))throw Error('Exactly one existing signer required');
 const certificates=[...signature.matchAll(/^Signer #(\d+) certificate SHA-256 digest: ([0-9a-fA-F:]+)\s*$/gm)];
 if(certificates.length!==1||certificates[0][1]!=='1'||certificates[0][2].replaceAll(':','').toLowerCase()!==CERT)throw Error('Final APK signing certificate differs from existing App');
 return {application_id:PACKAGE,version_code:version,version_name:packages[0][3],certificate_sha256:CERT,v2_verified:true};
}
function verifyApk(apk,buildTools,run=spawnSync){
 if(!apk||!buildTools||!path.isAbsolute(buildTools))throw Error('Usage: FOODSAVE_ANDROID_BUILD_TOOLS=/absolute/installed/build-tools npm run check:release:android -- /absolute/final.apk');
 const original=path.resolve(apk),stat=fs.lstatSync(original);
 if(!stat.isFile()||stat.isSymbolicLink()||stat.size===0)throw Error('Final APK must be a nonempty regular file');
 for(const name of ['apksigner','aapt'])fs.accessSync(path.join(buildTools,name),fs.constants.X_OK);
 const bytes=fs.readFileSync(original),hash=sha(bytes),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'foodsave-apk-verify-'));
 try{
  const snapshot=path.join(temporary,'final.apk');fs.writeFileSync(snapshot,bytes,{flag:'wx',mode:0o400});
  function tool(name,args){
   const result=run(path.join(buildTools,name),args,{encoding:'utf8',timeout:120000,maxBuffer:4*1024*1024,shell:false});
   if(result.error||result.status!==0||result.signal)throw Error(name+' verification failed; no release approval');
   return result.stdout||'';
  }
  const signature=tool('apksigner',['verify','--verbose','--print-certs',snapshot]);
  const badging=tool('aapt',['dump','badging',snapshot]);
  const identity=checkIdentity(badging,signature);
  if(sha(fs.readFileSync(snapshot))!==hash||sha(fs.readFileSync(original))!==hash)throw Error('APK changed during verification');
  return {...identity,apk_sha256:hash,apk_bytes:bytes.length,status:'identity_and_signature_verified_not_deployed'};
 }finally{fs.rmSync(temporary,{recursive:true,force:true});}
}
module.exports={checkIdentity,verifyApk,PACKAGE,BASE_VERSION,CERT};
if(require.main===module){try{
 if(process.argv.length!==3)throw Error('Exactly one final APK path is required');
 console.log(JSON.stringify(verifyApk(process.argv[2],process.env.FOODSAVE_ANDROID_BUILD_TOOLS),null,2));
}catch(e){console.error(e.message);process.exitCode=1;}}
