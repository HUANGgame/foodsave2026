"""Loopback-only browser fixture. Synthetic roles; NEVER deploy this QA server."""
import os
from fastapi import Header,HTTPException
from foodsave.api import app,current_user

def synthetic_user(authorization: str=Header(default='')):
    role={'Bearer synthetic-admin':'admin','Bearer synthetic-consumer':'consumer'}.get(authorization)
    if role is None:raise HTTPException(401,'Synthetic fixture authentication only')
    return {'id':'synthetic-'+role,'role':role}

if __name__=='__main__':
    if os.getenv('FOODSAVE_QA_LOOPBACK_ONLY')!='true':raise SystemExit('Explicit local fixture flag required')
    app.dependency_overrides[current_user]=synthetic_user
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=4181,access_log=False,log_level='error')
