"""Sign-in and staff accounts."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ROLES, User, utcnow
from ..security import (LOCKOUT_MINUTES, MAX_FAILED_ATTEMPTS, hash_password, password_problem,
                        verify_password)
from .common import Actor, BusinessError, audit

GENERIC_FAIL = "Wrong username or password."


def actor_for(user: User) -> Actor:
    return Actor(user.id, user.username, user.full_name, user.role)


def login(s: Session, username: str, password: str) -> tuple[Actor, bool]:
    """Returns (actor, must_change_password). Raises BusinessError on failure."""
    user = s.scalar(select(User).where(func.lower(User.username) == username.strip().lower()).with_for_update())
    now = utcnow()
    if user is None:
        raise BusinessError(GENERIC_FAIL)
    if not user.is_active:
        raise BusinessError("This account is disabled. Ask an administrator.")
    if user.locked_until and user.locked_until > now:
        mins = int((user.locked_until - now).total_seconds() // 60) + 1
        raise BusinessError(f"Too many failed attempts. Try again in {mins} minute(s).")
    if not verify_password(user.password_hash, password):
        user.failed_attempts += 1
        if user.failed_attempts >= MAX_FAILED_ATTEMPTS:
            user.locked_until = now + dt.timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_attempts = 0
            audit(s, None, "account_locked", "user", user.id, username=user.username)
        s.commit()  # keep the failed-attempt count even though we raise
        raise BusinessError(GENERIC_FAIL)
    user.failed_attempts, user.locked_until, user.last_login_at = 0, None, now
    actor = actor_for(user)
    audit(s, actor, "login", "user", user.id)
    return actor, user.must_change_password


def verify(s: Session, actor: Actor, password: str) -> bool:
    user = s.get(User, actor.id)
    return bool(user and user.is_active and verify_password(user.password_hash, password))


def change_password(s: Session, actor: Actor, old: str, new: str) -> None:
    user = s.get(User, actor.id)
    if user is None or not verify_password(user.password_hash, old):
        raise BusinessError("Your current password is not correct.")
    if old == new:
        raise BusinessError("Choose a password you have not just used.")
    problem = password_problem(new)
    if problem:
        raise BusinessError(problem)
    user.password_hash, user.must_change_password = hash_password(new), False
    audit(s, actor, "change_password", "user", user.id)


def list_users(s: Session) -> list[User]:
    return list(s.scalars(select(User).order_by(User.is_active.desc(), User.full_name)))


def save_user(s: Session, actor: Actor, user_id: int | None, username: str, full_name: str, email: str,
              role: str, is_active: bool, new_password: str | None) -> User:
    actor.require("users")
    username = username.strip()
    if not username or not full_name.strip():
        raise BusinessError("Username and full name are required.")
    if role not in ROLES:
        raise BusinessError("Choose a role.")
    clash = s.scalar(select(User).where(func.lower(User.username) == username.lower()))
    if clash and clash.id != user_id:
        raise BusinessError(f"The username “{username}” is already taken.")
    if user_id:
        user = s.get(User, user_id)
        if user is None:
            raise BusinessError("User not found.")
        if user.id == actor.id and (not is_active or role != "admin"):
            raise BusinessError("You cannot remove your own administrator access.")
    else:
        if not new_password:
            raise BusinessError("Set a temporary password for the new user.")
        user = User(username=username, full_name=full_name, role=role, password_hash="", failed_attempts=0)
        s.add(user)
    user.username, user.full_name, user.email, user.role, user.is_active = (
        username, full_name.strip(), email.strip() or None, role, is_active)
    if new_password:
        problem = password_problem(new_password)
        if problem:
            raise BusinessError(problem)
        user.password_hash, user.must_change_password = hash_password(new_password), True
        user.failed_attempts, user.locked_until = 0, None
    s.flush()
    if not is_active or role != "admin":
        admins = s.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True)))
        if not admins:
            raise BusinessError("At least one active administrator is required.")
    audit(s, actor, "save_user", "user", user.id, username=username, role=role, active=is_active,
          password_reset=bool(new_password))
    return user
