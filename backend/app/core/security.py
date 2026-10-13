import hashlib
import secrets
import hmac
import base64
import json
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from app.core.config import settings

ITERATIONS = 100_000
ALGORITHM = "sha256"
JWT_ALGORITHM = "HS256"
DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 7 días de validez para emergencias

ROLE_PERMISSIONS = {
    "ciudadano": ["alert:view", "alert:dispatch", "family:view", "user:view"],
    "operador": ["alert:view", "alert:handle", "map:view", "institution:view"],
    "analista": ["alert:view", "alert:handle", "map:view", "institution:view", "report:view"],
    "coordinador": ["alert:view", "alert:handle", "map:view", "institution:view", "institution:manage", "report:view", "user:manage"],
    "director": ["alert:view", "alert:handle", "map:view", "institution:view", "institution:manage", "report:view", "user:manage", "billing:view", "billing:manage"],
    "centrocomandob2g": ["alert:view", "alert:handle", "map:view", "institution:view", "institution:manage", "report:view", "user:manage"],
}


def normalize_role(role: Optional[str]) -> str:
    if not role:
        return "ciudadano"
    value = str(role).strip().lower().replace(" ", "")
    aliases = {
        "ciudadano": "ciudadano",
        "citizen": "ciudadano",
        "usuario": "ciudadano",
        "operador": "operador",
        "analista": "analista",
        "coordinador": "coordinador",
        "director": "director",
        "centrocomandob2g": "centrocomandob2g",
        "b2g": "centrocomandob2g",
    }
    return aliases.get(value, "ciudadano")


def build_permissions_for_role(role: Optional[str]) -> List[str]:
    normalized = normalize_role(role)
    permissions = ROLE_PERMISSIONS.get(normalized, ROLE_PERMISSIONS["ciudadano"])
    return sorted(set(permissions))


def has_permission(role: Optional[str], permission: str) -> bool:
    return permission in build_permissions_for_role(role)

def hash_password(password: str) -> str:
    """Genera un hash seguro usando PBKDF2 con sal aleatoria de 16 bytes."""
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac(ALGORITHM, password.encode('utf-8'), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${key.hex()}"

def verify_password(plain_password: str, stored_hash: str) -> bool:
    """Verifica contraseña en texto plano contra hash PBKDF2 con fallback para desarrollo previo."""
    if not stored_hash:
        return False
        
    if not stored_hash.startswith("pbkdf2_sha256$"):
        return hmac.compare_digest(plain_password, stored_hash)

    try:
        _, iterations_str, salt_hex, key_hex = stored_hash.split("$")
        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        expected_key = bytes.fromhex(key_hex)
        
        computed_key = hashlib.pbkdf2_hmac(ALGORITHM, plain_password.encode('utf-8'), salt, iterations)
        return hmac.compare_digest(computed_key, expected_key)
    except Exception:
        return False

def generar_codigo_enlace() -> str:
    """Genera un código único para enlace de red familiar."""
    return f"GEO-{secrets.token_hex(3).upper()}"

def _b64encode_url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')

def _b64decode_url(data: str) -> bytes:
    padding = '=' * (4 - (len(data) % 4)) if len(data) % 4 != 0 else ''
    return base64.urlsafe_b64decode((data + padding).encode('utf-8'))

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Genera un token JWT (RFC 7519) firmado con HMAC-SHA256."""
    to_encode = data.copy()
    now_ts = int(time.time())
    
    if expires_delta:
        expire_ts = now_ts + int(expires_delta.total_seconds())
    else:
        expire_ts = now_ts + (DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES * 60)

    role = normalize_role(to_encode.get("rol"))
    to_encode["rol"] = role
    to_encode["permisos"] = build_permissions_for_role(role)
    to_encode["iat"] = now_ts
    to_encode["exp"] = expire_ts

    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    header_b64 = _b64encode_url(json.dumps(header, separators=(',', ':')).encode('utf-8'))
    payload_b64 = _b64encode_url(json.dumps(to_encode, separators=(',', ':')).encode('utf-8'))
    
    signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
    signature = hmac.new(settings.SECRET_KEY.encode('utf-8'), signing_input, hashlib.sha256).digest()
    signature_b64 = _b64encode_url(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decodifica y valida la firma y expiración de un token JWT."""
    try:
        parts = token.strip().split('.')
        if len(parts) != 3:
            return None

        header_b64, payload_b64, signature_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
        expected_sig = hmac.new(settings.SECRET_KEY.encode('utf-8'), signing_input, hashlib.sha256).digest()
        actual_sig = _b64decode_url(signature_b64)

        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload_bytes = _b64decode_url(payload_b64)
        payload = json.loads(payload_bytes.decode('utf-8'))

        # Validar expiración
        exp = payload.get("exp")
        if exp and int(time.time()) > int(exp):
            return None

        return payload
    except Exception:
        return None

def generar_token_sesion() -> str:
    """Wrapper heredado: genera un token JWT por defecto para sesión de usuario."""
    return create_access_token({"sub": "anonimo", "rol": "Ciudadano"})
