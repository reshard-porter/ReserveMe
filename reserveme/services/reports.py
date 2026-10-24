"""Dashboard figures and management reports.

Each report loads its data in a few queries and computes in Python, which
keeps it fast over a remote database connection.
"""
from __future__ import annotations

import calendar
import datetime as dt
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import FolioLine, Reservation, Room
from .common import ZERO, daterange, money, settings
from .frontdesk import arrivals, departures, in_house
from .pricing import RateBook
from .reservations import LOAD

SOLD = ("tentative", "confirmed", "checked_in", "checked_out")


@dataclass
class DayStats:
    date: dt.date
    available: int
    sold: int
    arrivals: int
    departures: int
    room_revenue: Decimal
    actual: bool  # True when revenue comes from posted charges

    @property
    def occupancy(self) -> float:
        return (self.sold / self.available * 100) if self.available else 0.0

    @property
    def adr(self) -> Decimal:
        return money(self.room_revenue / self.sold) if self.sold else ZERO

    @property
    def revpar(self) -> Decimal:
        return money(self.room_revenue / self.available) if self.available else ZERO


def daily(s: Session, start: dt.date, end: dt.date) -> list[DayStats]:
    """Stats for each night from start to end (exclusive)."""
    bdate = settings(s).business_date
    rooms = s.scalar(select(func.count()).select_from(Room).where(Room.is_active.is_(True),
                                                               Room.status != "out_of_order")) or 0
    res = list(s.scalars(select(Reservation).where(Reservation.status.in_(SOLD), Reservation.check_in < end,
                                                    Reservation.check_out > start)))
    posted = defaultdict(lambda: ZERO)
    for d, amt in s.execute(select(FolioLine.stay_date, func.sum(FolioLine.amount)).where(
            FolioLine.kind == "room", FolioLine.stay_date >= start, FolioLine.stay_date < end)
            .group_by(FolioLine.stay_date)):
        posted[d] = money(amt)
    book = RateBook(s)
    out = []
    for d in daterange(start, end):
        staying = [r for r in res if r.check_in <= d < r.check_out]
        if d < bdate:
            revenue, actual = posted[d], True
        else:
            revenue = money(sum(((money(r.nightly_rate_override) if r.nightly_rate_override is not None
                                  else book.night(r.room_type_id, r.rate_plan_id, d).amount) for r in staying), ZERO))
            actual = False
        out.append(DayStats(d, rooms, len(staying), sum(1 for r in res if r.check_in == d),
                            sum(1 for r in res if r.check_out == d), revenue, actual))
    return out


@dataclass
class PeriodStats:
    label: str
    nights_available: int
    nights_sold: int
    room_revenue: Decimal
    stays: int
    stay_nights: int

    @property
    def occupancy(self) -> float:
        return self.nights_sold / self.nights_available * 100 if self.nights_available else 0.0

    @property
    def adr(self) -> Decimal:
        return money(self.room_revenue / self.nights_sold) if self.nights_sold else ZERO

    @property
    def revpar(self) -> Decimal:
        return money(self.room_revenue / self.nights_available) if self.nights_available else ZERO

    @property
    def alos(self) -> float:
        return self.stay_nights / self.stays if self.stays else 0.0


def monthly(s: Session, year: int) -> list[PeriodStats]:
    days = daily(s, dt.date(year, 1, 1), dt.date(year + 1, 1, 1))
    res = list(s.scalars(select(Reservation).where(Reservation.status.in_(SOLD),
               Reservation.check_in >= dt.date(year, 1, 1), Reservation.check_in < dt.date(year + 1, 1, 1))))
    out = []
    for m in range(1, 13):
        md = [d for d in days if d.date.month == m]
        arr = [r for r in res if r.check_in.month == m]
        out.append(PeriodStats(calendar.month_abbr[m] + f" {year % 100:02d}", sum(d.available for d in md),
                               sum(d.sold for d in md), money(sum((d.room_revenue for d in md), ZERO)),
                               len(arr), sum(r.nights for r in arr)))
    return out


@dataclass
class Dashboard:
    business_date: dt.date
    property_name: str
    currency: str
    arrivals: list[Reservation]
    departures: list[Reservation]
    in_house: list[Reservation]
    rooms_total: int
    rooms_ooo: int
    rooms_dirty: int
    today: DayStats
    next_days: list[DayStats]
    payments_today: Decimal
    charges_today: Decimal


def dashboard(s: Session) -> Dashboard:
    st = settings(s)
    bdate = st.business_date
    rooms = list(s.scalars(select(Room).where(Room.is_active.is_(True))))
    days = daily(s, bdate, bdate + dt.timedelta(days=14))
    pay = s.scalar(select(func.sum(FolioLine.amount)).where(FolioLine.business_date == bdate,
                                                            FolioLine.kind == "payment")) or 0
    chg = s.scalar(select(func.sum(FolioLine.amount)).where(FolioLine.business_date == bdate,
                                                            FolioLine.kind != "payment")) or 0
    return Dashboard(bdate, st.name, st.base_currency, arrivals(s, bdate), departures(s, bdate), in_house(s),
                     len(rooms), sum(1 for r in rooms if r.status == "out_of_order"),
                     sum(1 for r in rooms if r.status == "dirty"), days[0], days, money(-Decimal(pay)), money(chg))


def cashier(s: Session, day: dt.date) -> list[FolioLine]:
    from sqlalchemy.orm import selectinload
    return list(s.scalars(select(FolioLine).where(FolioLine.business_date == day)
                          .options(selectinload(FolioLine.reservation).selectinload(Reservation.guest),
                                   selectinload(FolioLine.user)).order_by(FolioLine.kind, FolioLine.id)))


def guest_register(s: Session, day: dt.date) -> list[Reservation]:
    """Everyone staying on the night of ``day`` (the police / guest register)."""
    return list(s.scalars(select(Reservation).where(Reservation.status.in_(("checked_in", "checked_out")),
                                                    Reservation.check_in <= day, Reservation.check_out > day)
                          .options(*LOAD).order_by(Reservation.room_id)))


def reservation_list(s: Session, start: dt.date, end: dt.date, by: str = "created") -> list[Reservation]:
    col = {"created": Reservation.created_at, "arrival": Reservation.check_in}[by]
    lo = dt.datetime.combine(start, dt.time.min) if by == "created" else start
    hi = dt.datetime.combine(end, dt.time.min) if by == "created" else end
    return list(s.scalars(select(Reservation).where(col >= lo, col < hi).options(*LOAD).order_by(col)))
