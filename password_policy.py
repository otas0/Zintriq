"""Creator password hashing and strength checks."""

from __future__ import annotations

import os
import re
from pathlib import Path

PASSWORD_MIN_LENGTH = int(os.environ.get("PASSWORD_MIN_LENGTH") or "10")
PASSWORD_MAX_LENGTH = 128

_COMMON: set[str] | None = None

_SEQ = (
    "0123456789",
    "abcdefghijklmnopqrstuvwxyz",
    "qwertyuiop",
    "asdfghjkl",
    "zxcvbnm",
)


def _common_passwords() -> set[str]:
    global _COMMON
    if _COMMON is not None:
        return _COMMON
    found: set[str] = {
        "password",
        "password123",
        "qwertyuiop",
        "1234567890",
        "123456789",
        "zintriq",
        "zintriq2026",
        "letmein",
        "welcome",
        "admin",
        "iloveyou",
    }
    for i in range(100_000):
        found.add(f"password{i}")
        found.add(str(i).zfill(6))
    path = Path(__file__).resolve().parent / "data" / "common-passwords.txt"
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            word = line.strip().lower()
            if word:
                found.add(word)
    _COMMON = found
    return found


def hash_password(password: str) -> str:
    try:
        from argon2 import PasswordHasher

        return PasswordHasher().hash(password)
    except Exception:
        from werkzeug.security import generate_password_hash

        return generate_password_hash(password, method="pbkdf2:sha256:600000")


def password_needs_rehash(stored: str) -> bool:
    return not (stored or "").startswith("$argon2")


def verify_password(stored: str, password: str) -> bool:
    stored = stored or ""
    if stored.startswith("$argon2"):
        try:
            from argon2 import PasswordHasher
            from argon2.exceptions import VerifyMismatchError

            PasswordHasher().verify(stored, password)
            return True
        except Exception:
            return False
    from werkzeug.security import check_password_hash

    try:
        return check_password_hash(stored, password)
    except Exception:
        return False


def password_issues(password: str, *, email: str = "", phone: str = "", name: str = "") -> str | None:
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"Use at least {PASSWORD_MIN_LENGTH} characters."
    if len(password) > PASSWORD_MAX_LENGTH:
        return "Use at most 128 characters."
    lowered = password.lower()
    if lowered in _common_passwords():
        return "This password appears in leaked or common password lists. Choose another."
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) >= 6 and digits in re.sub(r"\D", "", password):
        return "Don't use your phone number, email or name in your password."
    for piece in (email, phone, name, "zintriq"):
        token = re.sub(r"[^a-z0-9]", "", (piece or "").lower())
        if len(token) >= 4 and token in re.sub(r"[^a-z0-9]", "", lowered):
            return "Don't use your phone number, email or name in your password."
    if re.search(r"(.)\1{3,}", password):
        return "Avoid repeated or sequential characters like aaaa, 1234 or qwer."
    compact = re.sub(r"[^a-z0-9]", "", lowered)
    for seq in _SEQ:
        if len(compact) >= 4 and (compact in seq or compact in seq[::-1]):
            return "Avoid repeated or sequential characters like aaaa, 1234 or qwer."
        for i in range(len(seq) - 3):
            chunk = seq[i : i + 4]
            if chunk in compact or chunk[::-1] in compact:
                return "Avoid repeated or sequential characters like aaaa, 1234 or qwer."
    try:
        from zxcvbn import zxcvbn

        score = int((zxcvbn(password) or {}).get("score") or 0)
        if score < 3:
            return "This password is too easy to guess. Try something longer or less common."
    except Exception:
        pass
    return None
