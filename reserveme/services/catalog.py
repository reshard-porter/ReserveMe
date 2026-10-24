"""Property setup (room types, rooms, rate plans, rates, taxes), guests and settings."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..models import (AuditLog, Guest, PropertySettings, Rate, RatePlan, Reservation, Room, RoomType,
                      Tax, utcnow)
from .common import Actor, BusinessError, audit, money, settings
from .reservations import LOAD


# ---------------------------------------------------------------- lookups
def room_types(s: Session, active_only: bool = False) -> list[RoomType]:
    q = select(RoomType).order_by(RoomType.sort_order, RoomType.name)
    if active_only:
        q = q.where(RoomType.is_active.is_(True))
    return list(s.scalars(q))


def rooms(s: Session, active_only: bool = False) -> list[Room]:
    q = select(Room).join(Room.room_type).options(selectinload(Room.room_type)).order_by(RoomType.sort_order, Room.number)
    if active_only:
        q = q.where(Room.is_active.is_(True))
    return list(s.scalars(q))


def rate_plans(s: Session, active_only: bool = False) -> list[RatePlan]:
    q = select(RatePlan).order_by(RatePlan.code)
    if active_only:
        q = q.where(RatePlan.is_active.is_(True))
    return list(s.scalars(q))


def rates(s: Session) -> list[Rate]:
    return list(s.scalars(select(Rate).options(selectinload(Rate.rate_plan), selectinload(Rate.room_type))
                          .order_by(Rate.start_date, Rate.room_type_id, Rate.rate_plan_id)))


def taxes(s: Session) -> list[Tax]:
    return list(s.scalars(select(Tax).order_by(Tax.sort_order, Tax.id)))


# ---------------------------------------------------------------- generic save
def _save(s: Session, actor: Actor, model, obj_id: int | None, values: dict[str, Any], entity: str):
    actor.require("settings")
    obj = s.get(model, obj_id) if obj_id else model()
    if obj is None:
        raise BusinessError("Record not found.")
    for k, v in values.items():
        setattr(obj, k, v)
    if not obj_id:
        s.add(obj)
    s.flush()
    audit(s, actor, "save", entity, obj.id, **values)
    return obj


def save_room_type(s, actor, obj_id, *, code, name, description, base_occupancy, max_occupancy, base_rate,
                   sort_order, is_active):
    code = code.strip().upper()
    if not code or not name.strip():
        raise BusinessError("Code and name are required.")
    if max_occupancy < base_occupancy:
        raise BusinessError("Maximum occupancy cannot be lower than base occupancy.")
    dup = s.scalar(select(RoomType.id).where(RoomType.code == code))
    if dup and dup != obj_id:
        raise BusinessError(f"Room type code {code} already exists.")
    return _save(s, actor, RoomType, obj_id, dict(code=code, name=name.strip(), description=description or None,
                 base_occupancy=base_occupancy, max_occupancy=max_occupancy, base_rate=money(base_rate),
                 sort_order=sort_order, is_active=is_active), "room_type")


def save_room(s, actor, obj_id, *, number, room_type_id, building, floor, is_active, notes):
    number = number.strip()
    if not number:
        raise BusinessError("Room number is required.")
    dup = s.scalar(select(Room.id).where(Room.number == number))
    if dup and dup != obj_id:
        raise BusinessError(f"Room {number} already exists.")
    if obj_id and not is_active:
        future = s.scalar(select(func.count()).select_from(Reservation).where(
            Reservation.room_id == obj_id, Reservation.status.in_(("tentative", "confirmed", "checked_in"))))
        if future:
            raise BusinessError(f"Room {number} has {future} upcoming or current booking(s). Move them first.")
    return _save(s, actor, Room, obj_id, dict(number=number, room_type_id=room_type_id, building=building or None,
                 floor=floor or None, is_active=is_active, notes=notes or None), "room")


def save_rate_plan(s, actor, obj_id, *, code, name, includes_breakfast, description, is_active):
    code = code.strip().upper()
    if not code or not name.strip():
        raise BusinessError("Code and name are required.")
    dup = s.scalar(select(RatePlan.id).where(RatePlan.code == code))
    if dup and dup != obj_id:
        raise BusinessError(f"Rate plan {code} already exists.")
    return _save(s, actor, RatePlan, obj_id, dict(code=code, name=name.strip(), includes_breakfast=includes_breakfast,
                 description=description or None, is_active=is_active), "rate_plan")


def save_rate(s, actor, obj_id, *, rate_plan_id, room_type_id, season_name, start_date, end_date, amount,
              weekend_amount, min_stay):
    if end_date < start_date:
        raise BusinessError("The season must end on or after its start date.")
    if money(amount) <= 0:
        raise BusinessError("The nightly rate must be more than zero.")
    return _save(s, actor, Rate, obj_id, dict(rate_plan_id=rate_plan_id, room_type_id=room_type_id,
                 season_name=season_name or None, start_date=start_date, end_date=end_date, amount=money(amount),
                 weekend_amount=money(weekend_amount) if weekend_amount else None, min_stay=max(1, min_stay)), "rate")


def delete_rate(s: Session, actor: Actor, rate_id: int) -> None:
    actor.require("settings")
    r = s.get(Rate, rate_id)
    if r:
        audit(s, actor, "delete", "rate", rate_id, season=r.season_name, amount=r.amount)
        s.delete(r)


def save_tax(s, actor, obj_id, *, name, kind, value, is_active, sort_order):
    if not name.strip():
        raise BusinessError("Name the tax.")
    if Decimal(value) < 0:
        raise BusinessError("Tax cannot be negative.")
    return _save(s, actor, Tax, obj_id, dict(name=name.strip(), kind=kind, value=Decimal(value),
                 is_active=is_active, sort_order=sort_order), "tax")


def save_settings(s: Session, actor: Actor, **values) -> PropertySettings:
    actor.require("settings")
    st = settings(s, lock=True)
    if not values.get("name", "x").strip():
        raise BusinessError("The property needs a name.")
    for k, v in values.items():
        setattr(st, k, v)
    st.updated_at = utcnow()
    audit(s, actor, "save", "property_settings", st.id, **values)
    return st


# ---------------------------------------------------------------- guests
def search_guests(s: Session, text: str = "", limit: int = 300) -> list[Guest]:
    q = select(Guest)
    t = text.strip().lower()
    if t:
        like = f"%{t}%"
        q = q.where(or_(func.lower(Guest.first_name).like(like), func.lower(Guest.last_name).like(like),
                        func.lower(Guest.email).like(like), Guest.phone.like(like),
                        func.lower(Guest.company).like(like), func.lower(Guest.id_number).like(like)))
    return list(s.scalars(q.order_by(Guest.last_name, Guest.first_name).limit(limit)))


GUEST_FIELDS = ("first_name", "last_name", "email", "phone", "nationality", "id_type", "id_number", "address",
                "date_of_birth", "company", "vip", "blacklisted", "notes")


def possible_duplicates(s: Session, first: str, last: str, email: str, phone: str, exclude: int | None = None) -> list[Guest]:
    conds = []
    if email.strip():
        conds.append(func.lower(Guest.email) == email.strip().lower())
    if phone.strip():
        conds.append(Guest.phone == phone.strip())
    if first.strip() and last.strip():
        conds.append((func.lower(Guest.first_name) == first.strip().lower()) &
                     (func.lower(Guest.last_name) == last.strip().lower()))
    if not conds:
        return []
    q = select(Guest).where(or_(*conds))
    if exclude:
        q = q.where(Guest.id != exclude)
    return list(s.scalars(q.limit(5)))


def save_guest(s: Session, actor: Actor, guest_id: int | None, **values) -> Guest:
    actor.require("guests")
    if not values.get("first_name", "").strip() or not values.get("last_name", "").strip():
        raise BusinessError("First and last name are required.")
    email = (values.get("email") or "").strip()
    if email and ("@" not in email or "." not in email.split("@")[-1]):
        raise BusinessError("That email address does not look right.")
    if values.get("blacklisted"):
        actor.require("settings")
    g = s.get(Guest, guest_id) if guest_id else Guest()
    if g is None:
        raise BusinessError("Guest not found.")
    for k in GUEST_FIELDS:
        if k in values:
            v = values[k]
            setattr(g, k, v.strip() if isinstance(v, str) else v)
    if not guest_id:
        s.add(g)
    s.flush()
    audit(s, actor, "save", "guest", g.id, name=g.full_name)
    return g


def guest_history(s: Session, guest_id: int) -> list[Reservation]:
    return list(s.scalars(select(Reservation).where(Reservation.guest_id == guest_id).options(*LOAD)
                          .order_by(Reservation.check_in.desc())))


def audit_entries(s: Session, start: dt.date, end: dt.date, text: str = "", limit: int = 1000) -> list[AuditLog]:
    q = (select(AuditLog).options(selectinload(AuditLog.user))
         .where(AuditLog.at >= dt.datetime.combine(start, dt.time.min),
                AuditLog.at < dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min)))
    if text.strip():
        like = f"%{text.strip().lower()}%"
        q = q.where(or_(func.lower(AuditLog.action).like(like), func.lower(AuditLog.entity).like(like),
                        func.lower(AuditLog.details).like(like)))
    return list(s.scalars(q.order_by(AuditLog.id.desc()).limit(limit)))
