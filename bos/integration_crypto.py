"""Encrypt integration tokens at rest using the app secret key."""

from __future__ import annotations

import base64
import hashlib


def _fernet(secret_key: str):
    from cryptography.fernet import Fernet
    digest = hashlib.sha256(secret_key.encode()).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_token(plaintext: str, secret_key: str) -> str:
    if not plaintext:
        return ""
    return _fernet(secret_key).encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str, secret_key: str) -> str:
    if not ciphertext:
        return ""
    return _fernet(secret_key).decrypt(ciphertext.encode()).decode()
