import base64
import hashlib
import hmac
import secrets
from threading import BoundedSemaphore


class PasswordCapacityError(Exception):
    pass


_PASSWORD_SLOTS = BoundedSemaphore(2)


def _scrypt(password, salt, cost):
    if not isinstance(password, str) or len(password) > 128:
        raise ValueError("Invalid password length")
    if not _PASSWORD_SLOTS.acquire(timeout=1):
        raise PasswordCapacityError()
    try:
        return hashlib.scrypt(password.encode(), salt=salt, n=cost, r=8, p=1, maxmem=256*1024*1024)
    finally:
        _PASSWORD_SLOTS.release()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = _scrypt(password, salt, 131072)
    return 'scrypt-v2$' + base64.b64encode(salt).decode() + '$' + base64.b64encode(key).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt, expected = encoded.split('$')
        if algorithm not in ('scrypt','scrypt-v2'):
            return False
        salt_bytes=base64.b64decode(salt,validate=True);expected_bytes=base64.b64decode(expected,validate=True)
        if len(salt_bytes)!=16 or len(expected_bytes)!=64:
            return False
        key = _scrypt(password, salt_bytes, 16384 if algorithm=='scrypt' else 131072)
        return hmac.compare_digest(key, expected_bytes)
    except (ValueError, TypeError):
        return False


def weighted_choice(prizes, randbelow=secrets.randbelow):
    """Only server-held eligible prizes; no client probabilities or near misses."""
    total = sum(p['weight'] for p in prizes)
    if total <= 0:
        raise ValueError('No eligible prize')
    position = randbelow(total)
    for prize in prizes:
        position -= prize['weight']
        if position < 0:
            return prize
    raise ValueError('Invalid random source')
