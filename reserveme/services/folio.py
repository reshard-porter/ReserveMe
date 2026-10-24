"""Guest bills: room nights, extra charges, payments, reversals, invoices."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import FolioLine, Invoice, Reservation, utcnow
from .common import ZERO, Actor, BusinessError, audit, daterange, money, settings
from .pricing import RateBook


@dataclass
class FolioSummary:
    lines: list[FolioLine]
    charges: Decimal
    payments: Decimal
    balance: Decimal


def lines(s: Session, res_id: int) -> list[FolioLine]:
    return list(s.scalars(select(FolioLine).where(FolioLine.reservation_id == res_id)
                          .options(selectinload(FolioLine.user)).order_by(FolioLine.id)))


def summary(s: Session, res_id: int) -> FolioSummary:
    ls = lines(s, res_id)
    charges = money(sum((l.amount for l in ls if l.kind != "payment"), ZERO))
    payments = money(-sum((l.amount for l in ls if l.kind == "payment"), ZERO))
    return FolioSummary(ls, charges, payments, money(charges - payments))


def balance(s: Session, res_id: int) -> Decimal:
    return summary(s, res_id).balance


def _posted_nights(s: Session, res_id: int) -> set[dt.date]:
    """Nights with a room charge that has not been reversed."""
    ls = lines(s, res_id)
    reversed_ids = {l.reverses_id for l in ls if l.reverses_id}
    return {l.stay_date for l in ls if l.kind == "room" and l.reverses_id is None and l.id not in reversed_ids}


def post_night(s: Session, actor: Actor | None, res: Reservation, night: dt.date, book: RateBook,
               bdate: dt.date) -> Decimal:
    """Post the room charge and its taxes for one night. Returns room amount (0 if already posted)."""
    if night in _posted_nights(s, res.id):
        return ZERO
    price = book.night(res.room_type_id, res.rate_plan_id, night)
    amount = money(res.nightly_rate_override) if res.nightly_rate_override is not None else price.amount
    room_no = res.room.number if res.room else "unassigned"
    s.add(FolioLine(reservation_id=res.id, business_date=bdate, stay_date=night, kind="room",
                    description=f"Room {room_no} – {res.rate_plan.name} – night of {night:%d %b %Y}",
                    amount=amount, user_id=actor.id if actor else None))
    for t in book.tax_for_night(amount):
        if t.amount:
            s.add(FolioLine(reservation_id=res.id, business_date=bdate, stay_date=night, kind="tax",
                            description=f"{t.name} – {night:%d %b}", amount=t.amount,
                            user_id=actor.id if actor else None))
    s.flush()
    return amount


def post_missing_nights(s: Session, actor: Actor | None, res: Reservation, until: dt.date) -> int:
    book = RateBook(s)
    bdate = settings(s).business_date
    posted = 0
    for night in daterange(res.check_in, min(until, res.check_out)):
        if post_night(s, actor, res, night, book, bdate):
            posted += 1
    return posted


def add_charge(s: Session, actor: Actor, res_id: int, description: str, unit_amount: Decimal,
               quantity: Decimal = Decimal("1")) -> FolioLine:
    actor.require("billing")
    res = s.get(Reservation, res_id)
    if res is None:
        raise BusinessError("Reservation not found.")
    if res.status in ("cancelled",) and unit_amount > 0 and not description:
        raise BusinessError("Describe the charge.")
    if not description.strip():
        raise BusinessError("Describe the charge.")
    quantity = Decimal(quantity)
    if quantity <= 0:
        raise BusinessError("Quantity must be more than zero.")
    total = money(Decimal(unit_amount) * quantity)
    if total == 0:
        raise BusinessError("The amount cannot be zero.")
    line = FolioLine(reservation_id=res_id, business_date=settings(s).business_date, kind="charge",
                     description=description.strip(), quantity=quantity, amount=total, user_id=actor.id)
    s.add(line)
    s.flush()
    audit(s, actor, "charge", "folio_line", line.id, reservation=res.code, amount=total, description=description)
    return line


def add_payment(s: Session, actor: Actor, res_id: int, amount: Decimal, method: str, reference: str = "",
                currency: str | None = None, refund: bool = False) -> FolioLine:
    """Record money received (or paid back when refund=True). ``amount`` is in ``currency``."""
    actor.require("take_payment")
    res = s.get(Reservation, res_id)
    if res is None:
        raise BusinessError("Reservation not found.")
    amount = money(amount)
    if amount <= 0:
        raise BusinessError("Enter an amount greater than zero.")
    st = settings(s)
    currency = (currency or st.base_currency).upper()
    rate = None
    base_amount = amount
    if currency != st.base_currency:
        if currency != (st.alt_currency or "").upper() or not st.alt_rate:
            raise BusinessError(f"No exchange rate is set for {currency}. Set it in Settings.")
        rate = Decimal(st.alt_rate)
        base_amount = money(amount / rate)
    signed = base_amount if refund else -base_amount
    desc = ("Refund" if refund else "Payment") + f" – {method}"
    line = FolioLine(reservation_id=res_id, business_date=st.business_date, kind="payment", description=desc,
                     amount=signed, method=method, reference=reference or None,
                     original_currency=currency if rate else None, original_amount=amount if rate else None,
                     exchange_rate=rate, user_id=actor.id)
    s.add(line)
    s.flush()
    audit(s, actor, "refund" if refund else "payment", "folio_line", line.id, reservation=res.code,
          amount=amount, currency=currency, method=method)
    return line


def reverse(s: Session, actor: Actor, line_id: int, reason: str) -> FolioLine:
    actor.require("reverse_line")
    line = s.get(FolioLine, line_id)
    if line is None:
        raise BusinessError("Line not found.")
    if line.reverses_id is not None:
        raise BusinessError("A correction line cannot itself be reversed.")
    if s.scalar(select(FolioLine.id).where(FolioLine.reverses_id == line.id)):
        raise BusinessError("This line has already been reversed.")
    if not reason.strip():
        raise BusinessError("Give a reason for the correction.")
    rev = FolioLine(reservation_id=line.reservation_id, business_date=settings(s).business_date,
                    stay_date=line.stay_date, kind=line.kind if line.kind != "room" else "adjustment",
                    description=f"Reversal of “{line.description}” – {reason.strip()}"[:200],
                    quantity=line.quantity, amount=-line.amount, method=line.method, reverses_id=line.id,
                    original_currency=line.original_currency,
                    original_amount=-line.original_amount if line.original_amount else None,
                    exchange_rate=line.exchange_rate, user_id=actor.id)
    if line.kind == "room":
        rev.kind = "room"
    s.add(rev)
    s.flush()
    audit(s, actor, "reverse", "folio_line", line.id, amount=line.amount, reason=reason)
    return rev


def issue_invoice(s: Session, actor: Actor, res_id: int) -> Invoice:
    actor.require("billing")
    st = settings(s, lock=True)
    summ = summary(s, res_id)
    if not summ.lines:
        raise BusinessError("There is nothing on this bill yet.")
    n = st.next_invoice_no
    st.next_invoice_no = n + 1
    inv = Invoice(number=f"INV-{n:06d}", reservation_id=res_id, total_charges=summ.charges,
                  total_payments=summ.payments, user_id=actor.id, issued_at=utcnow())
    s.add(inv)
    s.flush()
    audit(s, actor, "invoice", "invoice", inv.id, number=inv.number, reservation_id=res_id)
    return inv


def open_balances(s: Session, include_departed: bool = True) -> list[tuple[Reservation, Decimal]]:
    """Reservations whose bill does not net to zero (one grouped query)."""
    from sqlalchemy import func
    from .reservations import LOAD
    rows = s.execute(select(FolioLine.reservation_id, func.sum(FolioLine.amount)).group_by(FolioLine.reservation_id)
                     .having(func.sum(FolioLine.amount) != 0)).all()
    bal = {rid: money(b) for rid, b in rows}
    if not bal:
        return []
    q = select(Reservation).where(Reservation.id.in_(bal)).options(*LOAD)
    if not include_departed:
        q = q.where(Reservation.status == "checked_in")
    return [(r, bal[r.id]) for r in s.scalars(q.order_by(Reservation.check_out))]
