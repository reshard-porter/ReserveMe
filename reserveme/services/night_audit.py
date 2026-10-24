"""End of day: post room charges, mark no-shows, roll the business date."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FolioLine, NightAuditRun, Reservation, utcnow
from . import folio
from .common import ZERO, Actor, BusinessError, audit, money, settings
from .frontdesk import _set_status, arrivals, in_house
from .pricing import RateBook


@dataclass
class AuditPreview:
    business_date: dt.date
    pending_departures: list[Reservation]
    expected_no_shows: list[Reservation]
    in_house: list[Reservation]

    @property
    def can_run(self) -> bool:
        return not self.pending_departures


def preview(s: Session) -> AuditPreview:
    bdate = settings(s).business_date
    house = in_house(s)
    return AuditPreview(
        business_date=bdate,
        pending_departures=[r for r in house if r.check_out <= bdate],
        expected_no_shows=[r for r in arrivals(s, bdate) if r.status in ("tentative", "confirmed")],
        in_house=[r for r in house if r.check_out > bdate],
    )


def run(s: Session, actor: Actor) -> NightAuditRun:
    actor.require("night_audit")
    st = settings(s, lock=True)  # only one audit at a time
    bdate = st.business_date
    if s.scalar(select(NightAuditRun.id).where(NightAuditRun.business_date == bdate)):
        raise BusinessError("The night audit for this date has already run.")
    pv = preview(s)
    if pv.pending_departures:
        names = ", ".join(f"{r.guest.full_name} ({r.room.number if r.room else '-'})" for r in pv.pending_departures)
        raise BusinessError(f"Check out or extend these departures first: {names}.")
    for r in pv.expected_no_shows:
        r.status = "no_show"
        audit(s, actor, "no_show", "reservation", r.id, code=r.code)
    book = RateBook(s)
    room_rev = ZERO
    posted = 0
    for r in pv.in_house:
        amount = folio.post_night(s, actor, r, bdate, book, bdate)
        if amount:
            posted += 1
            room_rev += amount
        if r.room:
            _set_status(s, actor, r.room, "dirty", "Night audit – occupied")
    s.flush()
    tax_rev = money(sum((l.amount for l in s.scalars(select(FolioLine).where(
        FolioLine.business_date == bdate, FolioLine.kind == "tax", FolioLine.stay_date == bdate))), ZERO))
    run = NightAuditRun(business_date=bdate, user_id=actor.id, rooms_posted=posted, room_revenue=money(room_rev),
                        tax_revenue=tax_rev, no_shows=len(pv.expected_no_shows), run_at=utcnow())
    s.add(run)
    st.business_date = bdate + dt.timedelta(days=1)
    st.updated_at = utcnow()
    audit(s, actor, "night_audit", "business_date", None, closed=bdate, opened=st.business_date,
          rooms_posted=posted, room_revenue=room_rev)
    s.flush()
    return run
