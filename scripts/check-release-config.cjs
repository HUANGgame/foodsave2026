// Run BEFORE a release web build; no secrets are needed or emitted.
const required=['NEXT_PUBLIC_API_BASE_URL','NEXT_PUBLIC_OPERATOR_NAME','NEXT_PUBLIC_PRIVACY_CONTACT','NEXT_PUBLIC_RETENTION_SUMMARY','FOODSAVE_APPLICATION_ID'];
const missing=required.filter(k=>!process.env[k]);
if(process.env.NEXT_PUBLIC_APP_MODE!=='live')missing.push('NEXT_PUBLIC_APP_MODE=live');
let base;
try{base=new URL(process.env.NEXT_PUBLIC_API_BASE_URL||'');}catch{}
if(!base||base.protocol!=='https:'||base.username||base.password||base.search||base.hash||base.hostname==='localhost'||/\.(test|invalid|example)$/.test(base.hostname))missing.push('approved HTTPS API hostname');
if(process.env.FOODSAVE_APPLICATION_ID==='tw.foodsave.demo')missing.push('owner-approved package ID');
if(missing.length){console.error('Release configuration incomplete:',missing.join(', '));process.exit(1);}
console.log('Release environment fields present. This does not verify privacy content, backend health or device acceptance.');
