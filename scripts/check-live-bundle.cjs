// Check emitted bytes, not only visible UI. Does not contact any API.
const fs=require('node:fs');
const path=require('node:path');
const markers=['幸福飯糰','米香烘焙坊','小樹蔬食','鮪魚玉米飯糰','暖心茶葉蛋','奶油可頌組','今日分享小餐包','繽紛蔬食餐盒','validation-only-not-a-login-hash','synthetic-consumer','PRIVATE OLD ORDER'];
function inspectBundle(directory,api){
 const base=new URL(api);if(base.protocol!=='https:'||base.username||base.password)throw Error('Expected HTTPS API URL');
 const files=[];function walk(dir){for(const entry of fs.readdirSync(dir,{withFileTypes:true})){const file=path.join(dir,entry.name);if(entry.isDirectory())walk(file);else if(entry.isFile())files.push(file);else throw Error('Unexpected non-regular output');}}walk(directory);
 if(!files.length)throw Error('Empty output');let foundAPI=false;const failures=[];
 for(const file of files){const raw=fs.readFileSync(file,'utf8'),text=raw.replace(/\\u\{([0-9a-f]+)\}|\\u([0-9a-f]{4})/gi,(_,a,b)=>String.fromCodePoint(parseInt(a||b,16)));
  foundAPI ||= text.includes(api);for(const marker of markers)if(text.includes(marker))failures.push(path.relative(directory,file)+': '+marker);
  if(/(?:^|\/)(?:tests?|qa|fixtures?|\.env)(?:\/|\.|$)/i.test(path.relative(directory,file)))failures.push('Unexpected test/config path');
  if(api!=='https://api.foodsave.test'&&text.includes('https://api.foodsave.test'))failures.push('Fixture API remains');
 }
 if(failures.length)throw Error('Non-production data found: '+failures.join('; '));if(!foundAPI)throw Error('Expected API missing');
 return {files:files.length,expected_api:api,demo_catalog_markers_absent:true,fixture_markers_absent:true};
}
module.exports={inspectBundle,markers};
if(require.main===module){try{const directory=process.argv[2]||'out',api=process.argv[3]||process.env.NEXT_PUBLIC_API_BASE_URL;if(!directory||!api)throw Error('Usage: node scripts/check-live-bundle.cjs OUTPUT HTTPS_API');console.log(JSON.stringify(inspectBundle(directory,api)));}catch(e){console.error(e.message);process.exitCode=1;}}
