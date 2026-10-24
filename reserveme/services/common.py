"""Shared helpers for the service layer."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AuditLog, PropertySettings
from ..security import require

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


class BusinessError(Exception):
    """A rule was broken; the message is safe to show to staff."""


class NeedsConfirmation(BusinessError):
    """The action is allowed but risky; retry with force=True after the user confirms."""


@dataclass(frozen=True)
class Actor:
    id: int
    username: str
    full_name: str
    role: str

    def require(self, permission: str) -> None:
        require(self.role, permission)


def money(value: Any) -> Decimal:
    if value is None:
        return ZERO
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def settings(s: Session, lock: bool = False) -> PropertySettings:
    q = select(PropertySettings).order_by(PropertySettings.id).limit(1)
    if lock:
        q = q.with_for_update()
    obj = s.scalar(q)
    if obj is None:
        raise BusinessError("Property settings are missing. Run the setup SQL.")
    return obj


def business_date(s: Session) -> dt.date:
    return settings(s).business_date


def audit(s: Session, actor: Actor | None, action: str, entity: str, entity_id: int | None = None,
          **details: Any) -> None:
    s.add(AuditLog(user_id=actor.id if actor else None, action=action, entity=entity, entity_id=entity_id,
                   details=json.dumps(details, default=str, ensure_ascii=False) if details else None))


def daterange(start: dt.date, end: dt.date):
    """Dates from start (inclusive) to end (exclusive)."""
    d = start
    while d < end:
        yield d
        d += dt.timedelta(days=1)
