"""First-run data, shared by the SQL script generator and the in-app setup."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import SCHEMA_VERSION
from .models import (Guest, PropertySettings, Rate, RatePlan, Room, RoomType, SchemaInfo,
                     Tax, User)
from .security import hash_password

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "ChangeMe2026!"

PROPERTY = dict(
    name="My Resort", address="Edit me in Settings", phone="", email="",
    base_currency="USD", alt_currency="JMD", alt_rate=Decimal("157.0000"),
    check_in_time="15:00", check_out_time="11:00",
    invoice_footer="Thank you for staying with us!",
    next_reservation_no=1001, next_invoice_no=1,
)

RATE_PLANS = [
    dict(code="RO", name="Room only", includes_breakfast=False,
         description="Accommodation only."),
    dict(code="BB", name="Bed & breakfast", includes_breakfast=True,
         description="Accommodation with daily breakfast."),
]

SAMPLE_ROOM_TYPES = [
    dict(code="STD", name="Standard Garden View", base_occupancy=2, max_occupancy=3,
         base_rate=Decimal("140.00"), sort_order=1),
    dict(code="DLX", name="Deluxe Ocean View", base_occupancy=2, max_occupancy=3,
         base_rate=Decimal("210.00"), sort_order=2),
    dict(code="STE", name="One-Bedroom Suite", base_occupancy=2, max_occupancy=4,
         base_rate=Decimal("320.00"), sort_order=3),
    dict(code="VIL", name="Beach Villa", base_occupancy=4, max_occupancy=6,
         base_rate=Decimal("550.00"), sort_order=4),
]

SAMPLE_ROOMS = (
    [dict(number=f"10{i}", type="STD", building="Main", floor="1") for i in range(1, 7)]
    + [dict(number=f"20{i}", type="DLX", building="Main", floor="2") for i in range(1, 7)]
    + [dict(number=f"30{i}", type="STE", building="Main", floor="3") for i in range(1, 4)]
    + [dict(number=f"V{i}", type="VIL", building="Beachfront", floor="G") for i in range(1, 3)]
)

# Example seasons; edit them in Settings ▸ Rates.
SAMPLE_SEASONS = [
    ("Low season 2026", dt.date(2026, 4, 16), dt.date(2026, 12, 14), Decimal("1.00")),
    ("Peak season 2026/27", dt.date(2026, 12, 15), dt.date(2027, 4, 15), Decimal("1.35")),
    ("Low season 2027", dt.date(2027, 4, 16), dt.date(2027, 12, 14), Decimal("1.00")),
]
BB_SUPPLEMENT = Decimal("25.00")

SAMPLE_TAXES = [
    dict(name="Example tax % (set the real rate)", kind="percent", value=Decimal("10.0000"), sort_order=1),
    dict(name="Example per-night levy (set the real amount)", kind="fixed_per_night",
         value=Decimal("2.0000"), sort_order=2),
]

SAMPLE_GUESTS = [
    dict(first_name="Alicia", last_name="Campbell", email="alicia@example.com", phone="+1 876 555 0101",
         nationality="Jamaican"),
    dict(first_name="Mark", last_name="Thompson", email="mark.t@example.com", phone="+1 305 555 0144",
         nationality="American", vip=True),
    dict(first_name="Sophie", last_name="Müller", email="sophie@example.de", phone="+49 30 555 0199",
         nationality="German"),
]


def sample_rates() -> list[dict]:
    out = []
    for rt in SAMPLE_ROOM_TYPES:
        for name, start, end, factor in SAMPLE_SEASONS:
            base = (rt["base_rate"] * factor).quantize(Decimal("1"))
            for plan in RATE_PLANS:
                amount = base + (BB_SUPPLEMENT * rt["base_occupancy"] if plan["includes_breakfast"] else 0)
                out.append(dict(plan=plan["code"], type=rt["code"], season_name=name, start_date=start,
                                end_date=end, amount=Decimal(amount).quantize(Decimal("0.01")),
                                min_stay=3 if factor > 1 else 1))
    return out


def seed_required(s: Session, business_date: dt.date | None = None) -> None:
    if s.scalar(select(SchemaInfo.id)) is None:
        s.add(SchemaInfo(version=SCHEMA_VERSION))
    if s.scalar(select(PropertySettings.id)) is None:
        s.add(PropertySettings(business_date=business_date or dt.date.today(), **PROPERTY))
    if s.scalar(select(User.id)) is None:
        s.add(User(username=DEFAULT_ADMIN_USERNAME, full_name="System Administrator", role="admin",
                   password_hash=hash_password(DEFAULT_ADMIN_PASSWORD), must_change_password=True,
                   is_active=True, failed_attempts=0))
    for rp in RATE_PLANS:
        if s.scalar(select(RatePlan.id).where(RatePlan.code == rp["code"])) is None:
            s.add(RatePlan(**rp))
    s.flush()


def seed_sample(s: Session) -> None:
    types = {}
    for rt in SAMPLE_ROOM_TYPES:
        obj = s.scalar(select(RoomType).where(RoomType.code == rt["code"]))
        if obj is None:
            obj = RoomType(**rt)
            s.add(obj)
        types[rt["code"]] = obj
    s.flush()
    for r in SAMPLE_ROOMS:
        if s.scalar(select(Room.id).where(Room.number == r["number"])) is None:
            s.add(Room(number=r["number"], room_type_id=types[r["type"]].id, building=r["building"],
                       floor=r["floor"], status="clean"))
    plans = {p.code: p for p in s.scalars(select(RatePlan))}
    if s.scalar(select(Rate.id)) is None:
        for r in sample_rates():
            s.add(Rate(rate_plan_id=plans[r["plan"]].id, room_type_id=types[r["type"]].id,
                       season_name=r["season_name"], start_date=r["start_date"], end_date=r["end_date"],
                       amount=r["amount"], min_stay=r["min_stay"]))
    if s.scalar(select(Tax.id)) is None:
        for t in SAMPLE_TAXES:
            s.add(Tax(**t))
    if s.scalar(select(Guest.id)) is None:
        for g in SAMPLE_GUESTS:
            s.add(Guest(**g))
    s.flush()
