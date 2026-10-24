"""Booking rules: availability, create, change, cancel."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..models import (ACTIVE_RES_STATUSES, Guest, RatePlan, Reservation, Room, RoomType)
from .common import Actor, BusinessError, NeedsConfirmation, audit, daterange, money, settings
from .pricing import RateBook

LOAD = (selectinload(Reservation.guest), selectinload(Reservation.room),
        selectinload(Reservation.room_type), selectinload(Reservation.rate_plan))

# Statuses that still occupy inventory (checked-out stays did occupy it in the past).
OCCUPYING = ACTIVE_RES_STATUSES


@dataclass
class ReservationInput:
    guest_id: int
    room_type_id: int
    rate_plan_id: int
    check_in: dt.date
    check_out: dt.date
    room_id: int | None = None
    adults: int = 1
    children: int = 0
    status: str = "confirmed"
    source: str | None = "Direct"
    external_ref: str | None = None
    nightly_rate_override: Decimal | None = None
    arrival_time: str | None = None
    notes: str | None = None


def _overlap(ci: dt.date, co: dt.date):
    return and_(Reservation.check_in < co, Reservation.check_out > ci)


def get(s: Session, res_id: int) -> Reservation:
    s.flush()
    res = s.scalar(select(Reservation).where(Reservation.id == res_id).options(*LOAD)
                   .execution_options(populate_existing=True))
    if res is None:
        raise BusinessError("Reservation not found. It may have been removed by someone else.")
    return res


def room_conflicts(s: Session, room_id: int, ci: dt.date, co: dt.date, exclude_id: int | None = None) -> list[Reservation]:
    q = select(Reservation).where(Reservation.room_id == room_id, Reservation.status.in_(OCCUPYING),
                                  _overlap(ci, co)).options(*LOAD)
    if exclude_id:
        q = q.where(Reservation.id != exclude_id)
    return list(s.scalars(q))


def available_rooms(s: Session, ci: dt.date, co: dt.date, room_type_id: int | None = None,
                    exclude_id: int | None = None) -> list[Room]:
    busy = select(Reservation.room_id).where(Reservation.room_id.is_not(None),
                                             Reservation.status.in_(OCCUPYING), _overlap(ci, co))
    if exclude_id:
        busy = busy.where(Reservation.id != exclude_id)
    q = (select(Room).join(Room.room_type)
         .where(Room.is_active.is_(True), Room.status != "out_of_order", Room.id.not_in(busy))
         .options(selectinload(Room.room_type)).order_by(RoomType.sort_order, Room.number))
    if room_type_id:
        q = q.where(Room.room_type_id == room_type_id)
    return list(s.scalars(q))


def type_availability(s: Session, ci: dt.date, co: dt.date, exclude_id: int | None = None) -> dict[int, int]:
    """Rooms still sellable per room type for every night of the stay (minimum across nights)."""
    rooms = s.execute(select(Room.room_type_id, func.count()).where(Room.is_active.is_(True),
                      Room.status != "out_of_order").group_by(Room.room_type_id)).all()
    capacity = {t: n for t, n in rooms}
    q = select(Reservation.room_type_id, Reservation.check_in, Reservation.check_out).where(
        Reservation.status.in_(OCCUPYING), _overlap(ci, co))
    if exclude_id:
        q = q.where(Reservation.id != exclude_id)
    booked = s.execute(q).all()
    result = {}
    for t, cap in capacity.items():
        worst = cap
        for d in daterange(ci, co):
            used = sum(1 for (rt, a, b) in booked if rt == t and a <= d < b)
            worst = min(worst, cap - used)
        result[t] = worst
    return result


def _next_code(s: Session) -> str:
    st = settings(s, lock=True)
    n = st.next_reservation_no
    st.next_reservation_no = n + 1
    return f"R{n:06d}"


def _validate(s: Session, data: ReservationInput, existing: Reservation | None, force: bool) -> tuple[Guest, RoomType]:
    if data.check_out <= data.check_in:
        raise BusinessError("Check-out must be after check-in.")
    if (data.check_out - data.check_in).days > 365:
        raise BusinessError("A single reservation cannot be longer than 365 nights.")
    if data.adults < 1:
        raise BusinessError("At least one adult is required.")
    bdate = settings(s).business_date
    if existing is None and data.check_in < bdate:
        raise BusinessError(f"Check-in cannot be before the current business date ({bdate:%d %b %Y}).")
    guest = s.get(Guest, data.guest_id)
    if guest is None:
        raise BusinessError("Choose a guest for this reservation.")
    if guest.blacklisted and not force:
        raise NeedsConfirmation(f"{guest.full_name} is on the do-not-book list. Book anyway?")
    # Lock the room type row so two desks cannot sell the last room of a type at once.
    rtype = s.scalar(select(RoomType).where(RoomType.id == data.room_type_id).with_for_update())
    if rtype is None or not rtype.is_active:
        raise BusinessError("Choose an active room type.")
    if s.get(RatePlan, data.rate_plan_id) is None:
        raise BusinessError("Choose a rate plan.")
    if data.adults + data.children > rtype.max_occupancy and not force:
        raise NeedsConfirmation(
            f"{rtype.name} sleeps {rtype.max_occupancy}; this booking has {data.adults + data.children} guests. Continue?")
    exclude = existing.id if existing else None
    if data.room_id:
        room = s.scalar(select(Room).where(Room.id == data.room_id).with_for_update())
        if room is None or not room.is_active:
            raise BusinessError("That room is not available for sale.")
        if room.room_type_id != data.room_type_id:
            raise BusinessError(f"Room {room.number} is not a {rtype.name}.")
        if room.status == "out_of_order" and not force:
            raise NeedsConfirmation(f"Room {room.number} is out of order. Assign it anyway?")
        clash = room_conflicts(s, room.id, data.check_in, data.check_out, exclude)
        if clash:
            c = clash[0]
            raise BusinessError(
                f"Room {room.number} is already booked by {c.guest.full_name} ({c.code}) "
                f"from {c.check_in:%d %b} to {c.check_out:%d %b}.")
    avail = type_availability(s, data.check_in, data.check_out, exclude).get(data.room_type_id, 0)
    if avail <= 0 and not force:
        raise NeedsConfirmation(f"{rtype.name} is fully booked for some of these nights. Overbook?")
    return guest, rtype


def create(s: Session, actor: Actor, data: ReservationInput, force: bool = False) -> Reservation:
    actor.require("reservations")
    if data.nightly_rate_override is not None:
        actor.require("override_rate")
    if data.status not in ("tentative", "confirmed"):
        raise BusinessError("New reservations must be tentative or confirmed.")
    _validate(s, data, None, force)
    quote = RateBook(s).quote(data.room_type_id, data.rate_plan_id, data.check_in, data.check_out,
                              data.nightly_rate_override)
    res = Reservation(code=_next_code(s), created_by=actor.id, estimated_total=quote.total, **data.__dict__)
    s.add(res)
    s.flush()
    audit(s, actor, "create", "reservation", res.id, code=res.code, check_in=data.check_in,
          check_out=data.check_out, room_id=data.room_id, total=quote.total, forced=force)
    return get(s, res.id)


def update(s: Session, actor: Actor, res_id: int, data: ReservationInput, force: bool = False) -> Reservation:
    actor.require("reservations")
    res = get(s, res_id)
    if res.status in ("checked_out", "cancelled", "no_show"):
        raise BusinessError(f"A {res.status.replace('_', ' ')} reservation cannot be changed.")
    if res.status == "checked_in":
        if data.check_in != res.check_in:
            raise BusinessError("The guest is already checked in, so the arrival date cannot change.")
        if data.room_id != res.room_id:
            raise BusinessError("Use “Move room” for a checked-in guest.")
        data.status = "checked_in"
    elif data.status not in ("tentative", "confirmed"):
        data.status = res.status
    if data.nightly_rate_override != res.nightly_rate_override:
        actor.require("override_rate")
    _validate(s, data, res, force)
    before = {k: getattr(res, k) for k in data.__dict__}
    for k, v in data.__dict__.items():
        setattr(res, k, v)
    res.estimated_total = RateBook(s).quote(res.room_type_id, res.rate_plan_id, res.check_in, res.check_out,
                                            res.nightly_rate_override).total
    from ..models import utcnow
    res.updated_at = utcnow()
    changes = {k: [before[k], v] for k, v in data.__dict__.items() if before[k] != v}
    audit(s, actor, "update", "reservation", res.id, code=res.code, changes=changes, forced=force)
    s.flush()
    return get(s, res.id)


def move(s: Session, actor: Actor, res_id: int, room_id: int, check_in: dt.date | None = None,
         force: bool = False) -> Reservation:
    """Move to another room (and optionally shift dates, keeping the length of stay)."""
    res = get(s, res_id)
    room = s.get(Room, room_id)
    if room is None:
        raise BusinessError("Room not found.")
    nights = res.nights
    ci = check_in or res.check_in
    data = ReservationInput(**{k: getattr(res, k) for k in ReservationInput.__dataclass_fields__})
    data.room_id, data.room_type_id = room.id, room.room_type_id
    data.check_in, data.check_out = ci, ci + dt.timedelta(days=nights)
    if res.status == "checked_in":
        if ci != res.check_in:
            raise BusinessError("A checked-in stay cannot be moved to other dates.")
        actor.require("front_desk")
        _validate(s, data, res, force)
        old = res.room
        res.room_id, res.room_type_id = room.id, room.room_type_id
        if old:
            old.status = "dirty"
        audit(s, actor, "room_move", "reservation", res.id, code=res.code,
              from_room=old.number if old else None, to_room=room.number)
        s.flush()
        return get(s, res.id)
    return update(s, actor, res_id, data, force)


def cancel(s: Session, actor: Actor, res_id: int, reason: str) -> Reservation:
    actor.require("reservations")
    res = get(s, res_id)
    if res.status not in ("tentative", "confirmed"):
        raise BusinessError("Only reservations that have not arrived can be cancelled.")
    if not reason.strip():
        raise BusinessError("Give a reason for the cancellation.")
    res.status, res.cancel_reason = "cancelled", reason.strip()
    audit(s, actor, "cancel", "reservation", res.id, code=res.code, reason=reason)
    return res


def reinstate(s: Session, actor: Actor, res_id: int) -> Reservation:
    actor.require("reservations")
    res = get(s, res_id)
    if res.status not in ("cancelled", "no_show"):
        raise BusinessError("Only cancelled or no-show reservations can be reinstated.")
    data = ReservationInput(**{k: getattr(res, k) for k in ReservationInput.__dataclass_fields__})
    data.status = "confirmed"
    if data.check_in < settings(s).business_date:
        raise BusinessError("Its dates are in the past. Create a new reservation instead.")
    _validate(s, data, res, False)
    res.status, res.cancel_reason = "confirmed", None
    audit(s, actor, "reinstate", "reservation", res.id, code=res.code)
    return res


def search(s: Session, text: str = "", statuses: list[str] | None = None, start: dt.date | None = None,
           end: dt.date | None = None, limit: int = 500) -> list[Reservation]:
    q = select(Reservation).join(Reservation.guest).options(*LOAD)
    if text.strip():
        like = f"%{text.strip().lower()}%"
        q = q.outerjoin(Reservation.room).where(or_(
            func.lower(Reservation.code).like(like), func.lower(Guest.first_name).like(like),
            func.lower(Guest.last_name).like(like), func.lower(Guest.email).like(like),
            Guest.phone.like(like), func.lower(Room.number).like(like),
            func.lower(Reservation.external_ref).like(like)))
    if statuses:
        q = q.where(Reservation.status.in_(statuses))
    if start and end:
        q = q.where(_overlap(start, end))
    return list(s.scalars(q.order_by(Reservation.check_in.desc(), Reservation.id.desc()).limit(limit)))


def for_chart(s: Session, start: dt.date, end: dt.date) -> list[Reservation]:
    q = (select(Reservation).where(Reservation.status.in_(OCCUPYING + ("checked_out",)), _overlap(start, end))
         .options(*LOAD))
    return list(s.scalars(q))


def quote_for(s: Session, data: ReservationInput):
    return RateBook(s).quote(data.room_type_id, data.rate_plan_id, data.check_in, data.check_out,
                             data.nightly_rate_override)


def money_or_none(v) -> Decimal | None:
    return None if v in (None, "") else money(v)
