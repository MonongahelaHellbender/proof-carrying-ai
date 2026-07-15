"""HMAC signing for certificates — shared-key authenticity, honestly scoped.

An HMAC-SHA256 signature over the certificate's digest proves the certificate was
produced by a holder of the signing key. This is authenticity WITHIN a shared-key
trust domain: the verifier needs the same secret key, and anyone holding it can
both sign and verify (and therefore forge). It is NOT public-key signing — a third
party cannot verify without the secret.

Public, anyone-can-verify signatures (e.g. Ed25519) need a crypto dependency or a
from-scratch implementation; that is the next step, deliberately not this one. This
module keeps the zero-dependency guarantee (hmac, hashlib, os only).
"""

from __future__ import annotations

import hashlib
import hmac
import os

SCHEME = "hmac-sha256"
DEFAULT_KEY_PATH = os.path.expanduser("~/.pcai/signing.key")


def _read_key(path: str) -> bytes:
    with open(path, encoding="utf-8") as f:
        return bytes.fromhex(f.read().strip())


def load_key(path: str = DEFAULT_KEY_PATH):
    """Return the key bytes if the key file exists, else None."""
    return _read_key(path) if os.path.exists(path) else None


def load_or_create_key(path: str = DEFAULT_KEY_PATH) -> bytes:
    """Return the signing key, creating a fresh random one if absent.

    The key file holds 64 hex chars (32 random bytes) and is created with 0600
    permissions. It is a LOCAL SECRET: keep it out of certificates and out of git.
    """
    existing = load_key(path)
    if existing is not None:
        return existing
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    key = os.urandom(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key.hex())
    return key


def key_id(key: bytes) -> str:
    """A non-secret label for a key (first 8 hex of sha256(key)).

    Lets a certificate say WHICH key signed it without revealing the key.
    """
    return hashlib.sha256(key).hexdigest()[:8]


def sign(digest: str, key: bytes) -> str:
    """Detached HMAC-SHA256 over the certificate digest string."""
    mac = hmac.new(key, digest.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{SCHEME}:{mac}"


def verify_signature(digest: str, signature: str, key: bytes) -> bool:
    """Constant-time check that `signature` is a valid HMAC of `digest` under `key`."""
    if not signature or not signature.startswith(SCHEME + ":"):
        return False
    return hmac.compare_digest(sign(digest, key), signature)
