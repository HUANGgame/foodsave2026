"""Local opt-in demonstration pool. No SQL, grants, coupons, mail or real rewards."""
import json
import os
import secrets
import tempfile
from pathlib import Path
from threading import RLock
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

NOTICE = '示範，暫不可兌換'
_LOCK = RLock()
DEFAULT = Path(__file__).parent / 'static' / 'demo-prizes.json'


class DemoPrize(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^demo-[1-6]$')
    name: str = Field(min_length=1, max_length=24)
    icon: str = Field(pattern=r'^(coffee|ticket|leaf|gift|heart|frog)$')
    weight: int = Field(ge=1, le=1000, strict=True)
    terms: str = Field(min_length=1, max_length=240)


class DemoPoolUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1, strict=True)
    prizes: list[DemoPrize] = Field(min_length=6, max_length=6)


def enabled():
    return os.getenv('FOODSAVE_DEMO_PRIZES_ENABLED') == 'true'


def require_enabled():
    if not enabled():
        raise HTTPException(404, '示範獎池未開放')


def path():
    value = os.getenv('FOODSAVE_DEMO_PRIZE_STORE', '')
    p = Path(value)
    if not value or not p.is_absolute() or p.name != 'demo-prizes.json' or not p.parent.is_dir() or p.is_symlink():
        raise HTTPException(503, '示範設定儲存未配置，尚未修改')
    return p


def read():
    require_enabled()
    p = path()
    data = json.loads((p if p.exists() else DEFAULT).read_text())
    parsed = DemoPoolUpdate.model_validate(data)
    if len({item.id for item in parsed.prizes}) != 6:
        raise HTTPException(503, '示範獎池設定不完整')
    return parsed.model_dump()


def public(data):
    return {'enabled': True, 'demonstration': True, 'notice': NOTICE,
            'revision': data['revision'], 'prizes': [
                {k: v for k, v in item.items() if k != 'weight'} for item in data['prizes']]}


def update(body):
    # Supported local runtime uses one worker. Optimistic revision prevents lost edits.
    with _LOCK:
        data = read()
        if body.revision != data['revision']:
            raise HTTPException(409, '設定已更新，請重新載入後再編輯')
        if len({item.id for item in body.prizes}) != 6:
            raise HTTPException(422, '需要六個不同的示範獎項')
        result = body.model_dump()
        result['revision'] += 1
        p = path()
        fd, temporary = tempfile.mkstemp(prefix='.demo-prizes-', dir=p.parent)
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(result, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, p)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return result


class DemoDrawRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1, strict=True)


def draw(expected_revision):
    # Snapshot and selected result come from the same config read. No credentials issued.
    with _LOCK:
        data = read()
        if expected_revision != data['revision']:
            return {**public(data), 'code': 'pool_changed', 'detail': '獎池已更新，請確認新版內容後再試；本次未抽獎。'}
        ticket = secrets.randbelow(sum(p['weight'] for p in data['prizes']))
        for prize in data['prizes']:
            ticket -= prize['weight']
            if ticket < 0:
                return {**public(data), 'prize': {k: v for k, v in prize.items() if k != 'weight'},
                        'redeemable': False, 'consumes_real_spin': False}
