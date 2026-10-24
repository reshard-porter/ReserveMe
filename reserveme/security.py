"""Password hashing and role permissions."""
from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()  # Argon2id with library defaults

MIN_PASSWORD_LENGTH = 10
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
IDLE_LOCK_MINUTES = 10


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_problem(password: str) -> str | None:
    """Return a plain-language reason the password is too weak, or None."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if password.lower() == password or password.upper() == password:
        return "Password needs both upper- and lower-case letters."
    if not any(c.isdigit() for c in password):
        return "Password needs at least one number."
    return None


ROLE_LABELS = {
    "admin": "Administrator",
    "manager": "General manager",
    "front_desk": "Front desk",
    "reservations": "Reservations",
    "housekeeping": "Housekeeping",
    "accounting": "Accounting / night audit",
}

_ALL = set(ROLE_LABELS)

PERMISSIONS: dict[str, set[str]] = {
    "dashboard": _ALL,
    "tape_chart": {"admin", "manager", "front_desk", "reservations", "housekeeping"},
    "reservations": {"admin", "manager", "front_desk", "reservations"},
    "front_desk": {"admin", "manager", "front_desk"},
    "guests": {"admin", "manager", "front_desk", "reservations", "accounting"},
    "housekeeping": {"admin", "manager", "front_desk", "housekeeping"},
    "billing": {"admin", "manager", "front_desk", "accounting"},
    "take_payment": {"admin", "manager", "front_desk", "accounting"},
    "reverse_line": {"admin", "manager", "accounting"},
    "override_rate": {"admin", "manager"},
    "reports": {"admin", "manager", "accounting"},
    "night_audit": {"admin", "manager", "front_desk", "accounting"},
    "settings": {"admin", "manager"},
    "users": {"admin"},
    "audit_log": {"admin", "manager"},
}


def can(role: str | None, permission: str) -> bool:
    return bool(role) and role in PERMISSIONS.get(permission, set())


class PermissionDenied(Exception):
    pass


def require(role: str | None, permission: str) -> None:
    if not can(role, permission):
        raise PermissionDenied("Your role is not allowed to do this. Ask a manager.")
