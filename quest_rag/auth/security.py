import hashlib
import hmac
import re
import uuid
from datetime import datetime, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from gmssl import sm2
from gmssl.sm2 import default_ecc_table
from gmssl import func as gmssl_func

from quest_rag.core.config import (
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    AUTH_ACCESS_TOKEN_MINUTES,
    AUTH_REFRESH_TOKEN_HOURS,
    AUTH_ID_NUMBER_PEPPER,
    SM2_PRIVATE_KEY,
)

ph = PasswordHasher()

_ID_NUMBER_RE = re.compile(r"^\d{17}[\dXx]$")

_sm2_crypt: sm2.CryptSM2 | None = None
_sm2_public_key: str | None = None


def _ensure_sm2_keys():
    global _sm2_crypt, _sm2_public_key
    if _sm2_crypt is not None:
        return

    sk = SM2_PRIVATE_KEY if SM2_PRIVATE_KEY else gmssl_func.random_hex(32)

    # Derive public key: pk = sk * G
    temp = sm2.CryptSM2(private_key=sk, public_key=default_ecc_table["g"])
    pk = temp._kg(int(sk, 16), default_ecc_table["g"])  # 128-char hex string

    _sm2_public_key = pk
    _sm2_crypt = sm2.CryptSM2(private_key=sk, public_key=pk)


def get_sm2_public_key() -> str:
    _ensure_sm2_keys()
    return "04" + _sm2_public_key


def sm2_decrypt(ciphertext_hex: str) -> str:
    """Decrypt SM2-encrypted hex ciphertext, return plaintext."""
    _ensure_sm2_keys()
    try:
        plain_bytes = _sm2_crypt.decrypt(bytes.fromhex(ciphertext_hex))
        return plain_bytes.decode("utf-8")
    except Exception as e:
        raise ValueError(f"SM2解密失败: {e}")


def normalize_id_number(id_number: str) -> str:
    """Strip whitespace, uppercase X, validate 18-char format."""
    cleaned = id_number.strip().upper()
    if not _ID_NUMBER_RE.match(cleaned):
        raise ValueError("身份证号格式不正确")
    return cleaned


def compute_id_number_digest(id_number: str) -> str:
    """HMAC-SHA256 digest of normalized id_number with pepper."""
    return hmac.new(
        AUTH_ID_NUMBER_PEPPER.encode("utf-8"),
        id_number.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def mask_id_number(id_number: str) -> str:
    """Mask middle digits: 6201**********0000"""
    return id_number[:4] + "*" * 10 + id_number[-4:]


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return ph.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(
    user_id: int,
    sid: str,
    role: str,
    token_version: int,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "sid": sid,
        "jti": uuid.uuid4().hex,
        "role": role,
        "token_version": token_version,
        "type": "access",
        "iat": now,
        "exp": now.timestamp() + AUTH_ACCESS_TOKEN_MINUTES * 60,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(
    user_id: int,
    sid: str,
    token_version: int,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "sid": sid,
        "jti": uuid.uuid4().hex,
        "token_version": token_version,
        "type": "refresh",
        "iat": now,
        "exp": now.timestamp() + AUTH_REFRESH_TOKEN_HOURS * 3600,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and verify JWT. Raises jwt.PyJWTError on failure."""
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])


def validate_password_policy(password: str) -> str | None:
    """Return error message if password doesn't meet policy, else None."""
    if len(password) < 8:
        return "密码长度不能少于8位"
    return None
