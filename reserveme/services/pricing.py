"""Room prices and taxes.

``RateBook`` loads every rate and tax once, so quoting many nights or many
reservations costs one round-trip to the (possibly remote) database.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Rate, RoomType, Tax
from .common import ZERO, daterange, money

WEEKEND_NIGHTS = (4, 5)  # Friday and Saturday nights


@dataclass
class NightPrice:
    date: dt.date
    amount: Decimal
    season: str | None


@dataclass
class TaxAmount:
    name: str
    amount: Decimal


@dataclass
class Quote:
    nights: list[NightPrice]
    room_total: Decimal
    taxes: list[TaxAmount]
    tax_total: Decimal
    total: Decimal
    min_stay: int = 1
    warnings: list[str] = field(default_factory=list)

    @property
    def average_rate(self) -> Decimal:
        return money(self.room_total / len(self.nights)) if self.nights else ZERO


class RateBook:
    def __init__(self, s: Session):
        self.rates = list(s.scalars(select(Rate).order_by(Rate.start_date)))
        self.base = {rt.id: money(rt.base_rate) for rt in s.scalars(select(RoomType))}
        self.taxes = list(s.scalars(select(Tax).where(Tax.is_active.is_(True)).order_by(Tax.sort_order, Tax.id)))

    def night(self, room_type_id: int, rate_plan_id: int, date: dt.date) -> NightPrice:
        # The most recently starting season that covers the date wins.
        best = None
        for r in self.rates:
            if r.room_type_id == room_type_id and r.rate_plan_id == rate_plan_id and r.start_date <= date <= r.end_date:
                if best is None or r.start_date >= best.start_date:
                    best = r
        if best is None:
            return NightPrice(date, self.base.get(room_type_id, ZERO), None)
        amount = best.amount
        if best.weekend_amount is not None and date.weekday() in WEEKEND_NIGHTS:
            amount = best.weekend_amount
        return NightPrice(date, money(amount), best.season_name)

    def min_stay(self, room_type_id: int, rate_plan_id: int, date: dt.date) -> int:
        for r in self.rates:
            if r.room_type_id == room_type_id and r.rate_plan_id == rate_plan_id and r.start_date <= date <= r.end_date:
                return r.min_stay
        return 1

    def tax_for_night(self, room_amount: Decimal) -> list[TaxAmount]:
        out = []
        for t in self.taxes:
            if t.kind == "percent":
                out.append(TaxAmount(t.name, money(room_amount * Decimal(t.value) / 100)))
            else:
                out.append(TaxAmount(t.name, money(t.value)))
        return out

    def quote(self, room_type_id: int, rate_plan_id: int, check_in: dt.date, check_out: dt.date,
              override: Decimal | None = None) -> Quote:
        nights = []
        for d in daterange(check_in, check_out):
            p = self.night(room_type_id, rate_plan_id, d)
            if override is not None:
                p = NightPrice(d, money(override), "Manual rate")
            nights.append(p)
        tax_totals: dict[str, Decimal] = {}
        for n in nights:
            for t in self.tax_for_night(n.amount):
                tax_totals[t.name] = tax_totals.get(t.name, ZERO) + t.amount
        room_total = money(sum((n.amount for n in nights), ZERO))
        taxes = [TaxAmount(k, money(v)) for k, v in tax_totals.items()]
        tax_total = money(sum((t.amount for t in taxes), ZERO))
        ms = self.min_stay(room_type_id, rate_plan_id, check_in)
        warnings = []
        if len(nights) < ms:
            warnings.append(f"This season has a minimum stay of {ms} nights.")
        return Quote(nights, room_total, taxes, tax_total, money(room_total + tax_total), ms, warnings)
