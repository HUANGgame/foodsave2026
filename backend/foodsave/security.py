import base64
import hashlib
import hmac
import secrets


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return 'scrypt$' + base64.b64encode(salt).decode() + '$' + base64.b64encode(key).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt, expected = encoded.split('$')
        if algorithm != 'scrypt':
            return False
        key = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=16384, r=8, p=1)
        return hmac.compare_digest(key, base64.b64decode(expected))
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
