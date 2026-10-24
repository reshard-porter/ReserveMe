"""Arrivals, departures, check-in, check-out, room status."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Reservation, Room, RoomStatusLog, RoomType, utcnow
from . import folio
from .common import Actor, BusinessError, NeedsConfirmation, audit, settings
from .reservations import LOAD, get, room_conflicts


def arrivals(s: Session, day: dt.date) -> list[Reservation]:
    return list(s.scalars(select(Reservation).where(Reservation.check_in == day,
                Reservation.status.in_(("tentative", "confirmed", "checked_in"))).options(*LOAD)
                .order_by(Reservation.status.desc(), Reservation.id)))


def departures(s: Session, day: dt.date) -> list[Reservation]:
    return list(s.scalars(select(Reservation).where(Reservation.check_out == day,
                Reservation.status.in_(("checked_in", "checked_out"))).options(*LOAD)
                .order_by(Reservation.status, Reservation.id)))


def in_house(s: Session) -> list[Reservation]:
    return list(s.scalars(select(Reservation).where(Reservation.status == "checked_in").options(*LOAD)
                .order_by(Reservation.check_out, Reservation.id)))


def check_in(s: Session, actor: Actor, res_id: int, room_id: int | None = None, force: bool = False) -> Reservation:
    actor.require("front_desk")
    res = get(s, res_id)
    bdate = settings(s).business_date
    if res.status not in ("tentative", "confirmed"):
        raise BusinessError(f"Reservation {res.code} is {res.status.replace('_', ' ')} and cannot be checked in.")
    if not (res.check_in <= bdate < res.check_out):
        if res.check_in > bdate:
            raise BusinessError(f"This reservation arrives on {res.check_in:%d %b %Y}. Change the dates to check in early.")
        raise BusinessError("This stay has already ended. Change the dates first.")
    if res.guest.blacklisted and not force:
        raise NeedsConfirmation(f"{res.guest.full_name} is on the do-not-book list. Check in anyway?")
    room_id = room_id or res.room_id
    if not room_id:
        raise BusinessError("Assign a room before check-in.")
    room = s.scalar(select(Room).where(Room.id == room_id).with_for_update())
    if room is None or not room.is_active:
        raise BusinessError("That room is not available.")
    if room.room_type_id != res.room_type_id and not force:
        raise NeedsConfirmation(
            f"Room {room.number} is a {room.room_type.name}, not the booked {res.room_type.name}. Use it anyway?")
    clash = room_conflicts(s, room.id, bdate, res.check_out, res.id)
    if clash:
        c = clash[0]
        raise BusinessError(f"Room {room.number} is held by {c.guest.full_name} ({c.code}). Choose another room.")
    if room.status == "out_of_order":
        raise BusinessError(f"Room {room.number} is out of order.")
    if room.status == "dirty" and not force:
        raise NeedsConfirmation(f"Room {room.number} is still marked dirty. Check in anyway?")
    res.room_id, res.room_type_id = room.id, room.room_type_id
    res.status, res.checked_in_at = "checked_in", utcnow()
    audit(s, actor, "check_in", "reservation", res.id, code=res.code, room=room.number, forced=force)
    s.flush()
    return get(s, res.id)


def check_out(s: Session, actor: Actor, res_id: int, force: bool = False) -> Reservation:
    actor.require("front_desk")
    res = get(s, res_id)
    if res.status != "checked_in":
        raise BusinessError("Only in-house guests can be checked out.")
    bdate = settings(s).business_date
    if bdate < res.check_out:
        # Early departure: shorten the stay (always at least one night).
        new_out = max(bdate, res.check_in + dt.timedelta(days=1))
        if new_out < res.check_out:
            if not force:
                raise NeedsConfirmation(
                    f"{res.guest.full_name} is due to leave on {res.check_out:%d %b}. "
                    f"Check out early and shorten the stay to {new_out:%d %b}?")
            audit(s, actor, "early_departure", "reservation", res.id, code=res.code,
                  old_check_out=res.check_out, new_check_out=new_out)
            res.check_out = new_out
    folio.post_missing_nights(s, actor, res, res.check_out)
    bal = folio.balance(s, res.id)
    if bal != 0:
        raise BusinessError(f"The bill has a balance of {bal:,.2f}. Settle it before check-out.")
    res.status, res.checked_out_at = "checked_out", utcnow()
    if res.room:
        _set_status(s, actor, res.room, "dirty", "Guest checked out")
    audit(s, actor, "check_out", "reservation", res.id, code=res.code)
    s.flush()
    return get(s, res.id)


def _set_status(s: Session, actor: Actor | None, room: Room, status: str, note: str | None = None) -> None:
    if room.status == status:
        return
    s.add(RoomStatusLog(room_id=room.id, old_status=room.status, new_status=status,
                        user_id=actor.id if actor else None, note=note))
    room.status = status


def set_room_status(s: Session, actor: Actor, room_id: int, status: str, note: str | None = None) -> Room:
    actor.require("housekeeping")
    if status == "out_of_order":
        actor.require("front_desk")
    room = s.get(Room, room_id)
    if room is None:
        raise BusinessError("Room not found.")
    _set_status(s, actor, room, status, note)
    if note is not None and status == "out_of_order":
        room.notes = note
    audit(s, actor, "room_status", "room", room.id, number=room.number, status=status, note=note)
    return room


def room_board(s: Session) -> list[tuple[Room, Reservation | None, Reservation | None]]:
    """Every room with its current guest and today's arrival (if any)."""
    bdate = settings(s).business_date
    rooms = list(s.scalars(select(Room).join(Room.room_type).where(Room.is_active.is_(True))
                           .options(selectinload(Room.room_type)).order_by(RoomType.sort_order, Room.number)))
    occ = {r.room_id: r for r in in_house(s)}
    arr = {r.room_id: r for r in arrivals(s, bdate) if r.status != "checked_in" and r.room_id}
    return [(room, occ.get(room.id), arr.get(room.id)) for room in rooms]
