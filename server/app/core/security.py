import base64
import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt

from app.core.config import ALGORITHM, SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES


def _prepare(password: str) -> bytes:
    """Reduce a password to a fixed 44 bytes before bcrypt sees it.

    bcrypt hashes at most 72 bytes and ignores everything after. passlib used
    to truncate silently, which turns a long passphrase into only its first 72
    bytes of entropy; modern bcrypt raises instead, which is safer but means a
    long password is a 500 rather than a login.

    Hashing to SHA-256 first and base64-encoding the digest keeps the entropy
    of the whole password inside bcrypt's limit. The base64 step matters: the
    raw digest can contain a NUL byte, and bcrypt stops reading there.
    """
    digest = hashlib.sha256(password.encode("utf-8")).digest()

    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(plain_password), hashed_password.encode("utf-8"))
    except ValueError:
        # A malformed or truncated hash in the database is a failed login, not
        # a 500 - and definitely not a success.
        return False


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": subject, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str | None:
    """Return the subject claim, or None if the token is invalid or expired."""
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    return payload.get("sub")
