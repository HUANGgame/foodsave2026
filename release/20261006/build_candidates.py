"""Fixed-source candidates only. No deployment, credentials, migrations or policy enablement."""
from pathlib import Path
import subprocess,hashlib,json,os,zipfile,tarfile,io,argparse
SOURCE='1a5a6d6ab9a5c098c46d54601a677eec18323143'
API='https://foodsave-web-tku-aqhxdnhpe8fdhfee.eastasia-01.azurewebsites.net'
ROOT=Path(__file__).resolve().parents[2]
def sha(data):return hashlib.sha256(data).hexdigest()
def zip_tree(path,files):
    manifest={name:{'sha256':sha(data),'bytes':len(data)} for name,data in files.items()}
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo(name,(2026,10,6,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,data)
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        assert {n:sha(z.read(n)) for n in z.namelist()}=={n:v['sha256'] for n,v in manifest.items()}
    return {'file':path.name,'sha256':sha(path.read_bytes()),'bytes':path.stat().st_size,'entries':manifest}
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    source=out/'source';source.mkdir()
    data=subprocess.check_output(['git','archive',SOURCE],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(data)) as t:t.extractall(source,filter='data')
    (source/'node_modules').symlink_to(ROOT/'node_modules',target_is_directory=True)
    public=json.loads((source/'infra/privacy-public-settings.example.json').read_text())
    public={k:v for k,v in public.items() if k.startswith('NEXT_PUBLIC_')}
    public.update(NEXT_PUBLIC_API_BASE_URL=API,NEXT_PUBLIC_APP_MODE='live')
    # Keep policy-complete=false; do not invent an Android app ID just to pass gate.
    env={k:v for k,v in os.environ.items() if not k.startswith(('NEXT_PUBLIC_','FOODSAVE_','AZURE_'))};env.update(public)
    with (out/'release-gate.log').open('w') as f:gate=subprocess.run(['node','scripts/check-release-config.cjs'],cwd=source,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
    with (out/'frontend-build.log').open('w') as f:subprocess.run(['npm','run','build'],cwd=source,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
    web={str(p.relative_to(source/'out')):p.read_bytes() for p in (source/'out').rglob('*') if p.is_file()}
    assert any(API.encode() in b for b in web.values())
    assert not any(b'api.foodsave.test' in b for b in web.values())
    demo_present=any(any(term.encode() in b for term in ['幸福飯糰','米香烘焙坊','鮪魚玉米飯糰']) for b in web.values())
    assert not any(n.endswith(('.map','.env','.py','.sql')) for n in web)
    backend={str(p.relative_to(source/'backend')):p.read_bytes() for p in (source/'backend/foodsave').rglob('*') if p.is_file() and p.suffix in ('.py','.json','.js','.css','.html') and p.name not in ('cli.py','migrate.py','erasure.py','diagnose.py') and p.name!='demo-prizes.json'}
    backend['requirements.txt']=(source/'backend/requirements.txt').read_bytes()
    result={'source_commit':SOURCE,'api':API,'public_build_settings':public,'release_gate_exit_code':gate,'frontend_demo_data_present':demo_present,'frontend_delivery':'QUARANTINED: fixed source bundles demo data' if demo_present else 'candidate only','backend_demo_fallback_excluded':True,'status':'CANDIDATE_NOT_DEPLOYED_NOT_APPROVED','backend_start_command':'python -m uvicorn foodsave.api:app --host 0.0.0.0 --port 8000 --no-proxy-headers','backend_requirements':'Existing Python environment and verified installed ODBC driver; dependency installation/startup must match existing App Service. ZIP alone is not a self-contained runtime.','packages':[zip_tree(out/'foodsave-web-1a5a6d6-candidate.zip',web),zip_tree(out/'foodsave-api-1a5a6d6-candidate.zip',backend)]}
    (out/'manifest.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:result[k] for k in ['source_commit','status','release_gate_exit_code']}));print(json.dumps([{k:v for k,v in x.items() if k!='entries'} for x in result['packages']]))
if __name__=='__main__':main()
