"""Pure-Python RFC 8032 Ed25519 digital signature scheme with persistent key management.

Compliant with IETF RFC 8032 Section 5.1 (Ed25519).
Uses extended Edwards coordinates (X:Y:Z:T) for fast scalar multiplication
without intermediate modular inversions.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Tuple

from ..config import settings

# -----------------------------------------------------------------------------
# RFC 8032 Curve25519 Parameters
# -----------------------------------------------------------------------------
Q = 2**255 - 19
L = 2**252 + 27742317777372353535851937790883648493
D = (-121665 * pow(121666, -1, Q)) % Q
I = pow(2, (Q - 1) // 4, Q)


def inv(x: int) -> int:
    return pow(x, Q - 2, Q)


# Base point B = (Bx, By)
By = (4 * inv(5)) % Q
Bx = pow((By**2 - 1) * inv(D * By**2 + 1), (Q + 3) // 8, Q)
if (Bx**2 - (By**2 - 1) * inv(D * By**2 + 1)) % Q != 0:
    Bx = (Bx * I) % Q
if Bx % 2 != 0:
    Bx = Q - Bx

# Extended coordinates: (X, Y, Z, T) where x = X/Z, y = Y/Z, xy = T/Z
B_EXT: Tuple[int, int, int, int] = (Bx, By, 1, (Bx * By) % Q)
IDENTITY: Tuple[int, int, int, int] = (0, 1, 1, 0)


# -----------------------------------------------------------------------------
# Extended Edwards Arithmetic
# -----------------------------------------------------------------------------
def _ext_add(P: Tuple[int, int, int, int], Q_pt: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
    X1, Y1, Z1, T1 = P
    X2, Y2, Z2, T2 = Q_pt
    A = ((Y1 - X1) * (Y2 - X2)) % Q
    B = ((Y1 + X1) * (Y2 + X2)) % Q
    C = (2 * D * T1 * T2) % Q
    D_val = (2 * Z1 * Z2) % Q
    E = (B - A) % Q
    F = (D_val - C) % Q
    G = (D_val + C) % Q
    H = (B + A) % Q
    return ((E * F) % Q, (G * H) % Q, (F * G) % Q, (E * H) % Q)


def _ext_double(P: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
    X1, Y1, Z1, _ = P
    A = (X1 * X1) % Q
    B = (Y1 * Y1) % Q
    C = (2 * Z1 * Z1) % Q
    H = (A + B) % Q
    E = (H - pow(X1 + Y1, 2, Q)) % Q
    G = (A - B) % Q
    F = (C + G) % Q
    return ((E * F) % Q, (G * H) % Q, (F * G) % Q, (E * H) % Q)


def _ext_scalar_mult(P: Tuple[int, int, int, int], k: int) -> Tuple[int, int, int, int]:
    R = IDENTITY
    temp = P
    while k > 0:
        if k & 1:
            R = _ext_add(R, temp)
        temp = _ext_double(temp)
        k >>= 1
    return R


def _ext_to_affine(P: Tuple[int, int, int, int]) -> Tuple[int, int]:
    X, Y, Z, _ = P
    z_inv = inv(Z)
    return ((X * z_inv) % Q, (Y * z_inv) % Q)


def _affine_to_ext(P: Tuple[int, int]) -> Tuple[int, int, int, int]:
    x, y = P
    return (x, y, 1, (x * y) % Q)


def _encode_point(P: Tuple[int, int]) -> bytes:
    x, y = P
    b = bytearray(y.to_bytes(32, "little"))
    if x & 1:
        b[31] |= 0x80
    return bytes(b)


def _decode_point(b: bytes) -> Tuple[int, int] | None:
    if len(b) != 32:
        return None
    y = int.from_bytes(b, "little") & ((1 << 255) - 1)
    sign = (b[31] >> 7) & 1
    denom = (D * y * y + 1) % Q
    if denom == 0:
        return None
    x2 = ((y * y - 1) * inv(denom)) % Q
    if x2 == 0:
        if sign:
            return None
        return (0, y)
    x = pow(x2, (Q + 3) // 8, Q)
    if (x * x - x2) % Q != 0:
        x = (x * I) % Q
    if (x * x - x2) % Q != 0:
        return None
    if (x & 1) != sign:
        x = Q - x
    return (x, y)


# -----------------------------------------------------------------------------
# Raw RFC 8032 Functions (bytes in, bytes out)
# -----------------------------------------------------------------------------
def public_key_from_seed(seed: bytes) -> bytes:
    """Derive 32-byte public key from 32-byte seed."""
    if len(seed) != 32:
        raise ValueError(f"Seed must be 32 bytes, got {len(seed)}")
    h = hashlib.sha512(seed).digest()
    h_clamped = bytearray(h[:32])
    h_clamped[0] &= 248
    h_clamped[31] &= 127
    h_clamped[31] |= 64
    s = int.from_bytes(h_clamped, "little")
    A_ext = _ext_scalar_mult(B_EXT, s)
    return _encode_point(_ext_to_affine(A_ext))


def generate_keypair() -> tuple[bytes, bytes]:
    """Generate (seed_bytes, public_key_bytes)."""
    seed = os.urandom(32)
    pub = public_key_from_seed(seed)
    return seed, pub


def sign(seed: bytes, message: bytes) -> bytes:
    """Sign message using 32-byte private seed according to RFC 8032."""
    if len(seed) != 32:
        raise ValueError(f"Seed must be 32 bytes, got {len(seed)}")
    h = hashlib.sha512(seed).digest()
    h_clamped = bytearray(h[:32])
    h_clamped[0] &= 248
    h_clamped[31] &= 127
    h_clamped[31] |= 64
    s = int.from_bytes(h_clamped, "little")
    prefix = h[32:]
    A_ext = _ext_scalar_mult(B_EXT, s)
    pk = _encode_point(_ext_to_affine(A_ext))

    r = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little")
    R_ext = _ext_scalar_mult(B_EXT, r % L)
    R_enc = _encode_point(_ext_to_affine(R_ext))

    k = int.from_bytes(hashlib.sha512(R_enc + pk + message).digest(), "little")
    S = (r + k * s) % L
    return R_enc + S.to_bytes(32, "little")


def verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """Verify Ed25519 signature on message using 32-byte public key."""
    if len(public_key) != 32 or len(signature) != 64:
        return False
    R_enc, S_bytes = signature[:32], signature[32:]
    S = int.from_bytes(S_bytes, "little")
    if S >= L:
        return False
    A_pt = _decode_point(public_key)
    R_pt = _decode_point(R_enc)
    if A_pt is None or R_pt is None:
        return False
    k = int.from_bytes(hashlib.sha512(R_enc + public_key + message).digest(), "little")
    SB_ext = _ext_scalar_mult(B_EXT, S)
    A_ext = _affine_to_ext(A_pt)
    kA_ext = _ext_scalar_mult(A_ext, k % L)
    R_ext = _affine_to_ext(R_pt)
    R_plus_kA_ext = _ext_add(R_ext, kA_ext)
    return _ext_to_affine(SB_ext) == _ext_to_affine(R_plus_kA_ext)


# -----------------------------------------------------------------------------
# Keypair Persistence and Hex Interfaces
# -----------------------------------------------------------------------------
KEYPAIR_FILE = settings.data_dir / "ledger_ed25519.json"


def get_or_create_keypair(key_file: Path | str | None = None) -> tuple[str, str]:
    """Load persistent Ed25519 keypair as hex strings (private_hex, public_hex).

    If missing, creates a new persistent keypair in the data directory.
    """
    path = Path(key_file) if key_file else KEYPAIR_FILE
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if "private_key" in data and "public_key" in data:
                return data["private_key"], data["public_key"]
        except Exception:
            pass

    path.parent.mkdir(parents=True, exist_ok=True)
    seed, pub = generate_keypair()
    priv_hex, pub_hex = seed.hex(), pub.hex()
    data = {"private_key": priv_hex, "public_key": pub_hex}
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return priv_hex, pub_hex


def get_public_key(key_file: Path | str | None = None) -> str:
    """Return the persistent Ed25519 public key as a 64-character hex string."""
    _, pub_hex = get_or_create_keypair(key_file)
    return pub_hex


def sign_message(msg: bytes | str, private_key_hex: str | None = None, key_file: Path | str | None = None) -> str:
    """Sign a message (bytes or UTF-8 str), returning 128-char hex signature."""
    if private_key_hex is None:
        private_key_hex, _ = get_or_create_keypair(key_file)
    msg_bytes = msg.encode("utf-8") if isinstance(msg, str) else msg
    seed = bytes.fromhex(private_key_hex)
    sig_bytes = sign(seed, msg_bytes)
    return sig_bytes.hex()


def verify_signature(
    msg: bytes | str,
    sig_hex: str,
    public_key_hex: str | None = None,
    key_file: Path | str | None = None,
) -> bool:
    """Verify hex signature against message and public key."""
    if public_key_hex is None:
        public_key_hex = get_public_key(key_file)
    msg_bytes = msg.encode("utf-8") if isinstance(msg, str) else msg
    try:
        sig_bytes = bytes.fromhex(sig_hex)
        pk_bytes = bytes.fromhex(public_key_hex)
    except (ValueError, TypeError):
        return False
    return verify(pk_bytes, msg_bytes, sig_bytes)
