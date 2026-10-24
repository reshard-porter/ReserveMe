import datetime as dt
import threading
from decimal import Decimal

import pytest
from sqlalchemy import select

from reserveme import db
from reserveme.models import FolioLine, PropertySettings, Room
from reserveme.seed import DEFAULT_ADMIN_PASSWORD
from reserveme.security import PermissionDenied
from reserveme.services import auth, catalog, folio, frontdesk, night_audit, reports
from reserveme.services import reservations as R
from reserveme.services.common import Actor, BusinessError, NeedsConfirmation

from conftest import BDATE

D = dt.timedelta


def booking(refs, room="101", ci=BDATE, nights=3, **kw):
    rtype = "DLX" if room and room.startswith("2") else "STD"
    return R.ReservationInput(guest_id=refs["guests"][0], room_type_id=refs["types"][rtype],
                              rate_plan_id=refs["plans"]["RO"], room_id=refs["rooms"][room] if room else None,
                              check_in=ci, check_out=ci + D(days=nights), adults=2, **kw)


def make_user(admin, role, name="u1"):
    with db.session() as s:
        u = auth.save_user(s, admin, None, name, name.title(), "", role, True, "Secret12345x")
        return Actor(u.id, u.username, u.full_name, u.role)


# ------------------------------------------------------------------ auth
def test_login_and_forced_password_change(admin):
    with db.session() as s:
        actor, must_change = auth.login(s, "ADMIN", DEFAULT_ADMIN_PASSWORD)
    assert must_change and actor.role == "admin"
    with db.session() as s:
        with pytest.raises(BusinessError):
            auth.change_password(s, actor, DEFAULT_ADMIN_PASSWORD, "short")
        auth.change_password(s, actor, DEFAULT_ADMIN_PASSWORD, "NewPassword2026")
    with db.session() as s:
        _, must_change = auth.login(s, "admin", "NewPassword2026")
    assert not must_change


def test_lockout_after_five_failures(admin):
    for _ in range(5):
        with pytest.raises(BusinessError):
            with db.session() as s:
                auth.login(s, "admin", "wrong")
    with pytest.raises(BusinessError, match="Too many failed attempts"):
        with db.session() as s:
            auth.login(s, "admin", DEFAULT_ADMIN_PASSWORD)


def test_cannot_remove_last_admin(admin):
    with pytest.raises(BusinessError):
        with db.session() as s:
            auth.save_user(s, admin, admin.id, "admin", "Admin", "", "manager", True, None)


# ------------------------------------------------------------------ pricing
def test_quote_uses_season_and_taxes(admin, refs):
    with db.session() as s:
        q = R.quote_for(s, booking(refs, nights=2))
    # Low season STD room-only = 140/night; 10% tax + 2.00 per night levy.
    assert q.room_total == Decimal("280.00")
    assert q.tax_total == Decimal("32.00")
    assert q.total == Decimal("312.00")


def test_peak_season_minimum_stay_warning(admin, refs):
    with db.session() as s:
        q = R.quote_for(s, booking(refs, ci=dt.date(2026, 12, 20), nights=2))
    assert q.nights[0].amount == Decimal("189.00") and q.warnings


# ------------------------------------------------------------------ reservations
def test_no_double_booking_same_room(admin, refs):
    with db.session() as s:
        R.create(s, admin, booking(refs))
    with pytest.raises(BusinessError, match="already booked"):
        with db.session() as s:
            R.create(s, admin, booking(refs, ci=BDATE + D(days=2)))
    with db.session() as s:  # back-to-back stays are fine
        R.create(s, admin, booking(refs, ci=BDATE + D(days=3)))


def test_type_sold_out_needs_confirmation(admin, refs):
    with db.session() as s:
        for n in range(1, 7):
            R.create(s, admin, booking(refs, room=f"10{n}"))
    with pytest.raises(NeedsConfirmation):
        with db.session() as s:
            R.create(s, admin, booking(refs, room=None))
    with db.session() as s:
        assert R.create(s, admin, booking(refs, room=None), force=True).id


def test_cannot_book_in_the_past(admin, refs):
    with pytest.raises(BusinessError, match="business date"):
        with db.session() as s:
            R.create(s, admin, booking(refs, ci=BDATE - D(days=1)))


def test_housekeeping_cannot_book(admin, refs):
    hk = make_user(admin, "housekeeping")
    with pytest.raises(PermissionDenied):
        with db.session() as s:
            R.create(s, hk, booking(refs))


def test_rate_override_needs_manager(admin, refs):
    fd = make_user(admin, "front_desk")
    with pytest.raises(PermissionDenied):
        with db.session() as s:
            R.create(s, fd, booking(refs, nightly_rate_override=Decimal("99")))


def test_move_and_cancel(admin, refs):
    with db.session() as s:
        res = R.create(s, admin, booking(refs))
    with db.session() as s:
        moved = R.move(s, admin, res.id, refs["rooms"]["201"], BDATE + D(days=5))
    assert moved.room.number == "201" and moved.room_type.code == "DLX" and moved.nights == 3
    with db.session() as s:
        R.cancel(s, admin, res.id, "Guest changed plans")
    with db.session() as s:  # room is free again
        R.create(s, admin, booking(refs, room="201", ci=BDATE + D(days=5)))


# ------------------------------------------------------------------ stay lifecycle
def test_full_stay_with_night_audit(admin, refs):
    with db.session() as s:
        res = R.create(s, admin, booking(refs, nights=2))
        noshow = R.create(s, admin, booking(refs, room="102", nights=1))
    with db.session() as s:
        frontdesk.check_in(s, admin, res.id)
    with db.session() as s:
        pv = night_audit.preview(s)
        assert len(pv.expected_no_shows) == 1 and len(pv.in_house) == 1
        run = night_audit.run(s, admin)
    assert run.rooms_posted == 1 and run.room_revenue == Decimal("140.00")
    with db.session() as s:
        assert s.scalar(select(PropertySettings.business_date)) == BDATE + D(days=1)
        assert R.get(s, noshow.id).status == "no_show"
        assert s.get(Room, refs["rooms"]["101"]).status == "dirty"
    with pytest.raises(BusinessError, match="already run"):
        with db.session() as s:  # same date cannot run twice (simulate by resetting date)
            s.scalar(select(PropertySettings)).business_date = BDATE
            night_audit.run(s, admin)
    with db.session() as s:
        night_audit.run(s, admin)  # second night
    with db.session() as s:
        summ = folio.summary(s, res.id)
        assert summ.balance == Decimal("312.00")
        assert BDATE + D(days=2) == s.scalar(select(PropertySettings.business_date))
    with pytest.raises(BusinessError, match="balance"):
        with db.session() as s:
            frontdesk.check_out(s, admin, res.id)
    with db.session() as s:
        folio.add_payment(s, admin, res.id, Decimal("312.00"), "Card (terminal)", "AUTH123")
    with db.session() as s:
        out = frontdesk.check_out(s, admin, res.id)
    assert out.status == "checked_out" and out.room.status == "dirty"


def test_audit_blocked_by_pending_departure(admin, refs):
    with db.session() as s:
        res = R.create(s, admin, booking(refs, nights=1))
        frontdesk.check_in(s, admin, res.id)
        night_audit.run(s, admin)
    with pytest.raises(BusinessError, match="Check out or extend"):
        with db.session() as s:
            night_audit.run(s, admin)


def test_early_departure_shortens_stay(admin, refs):
    with db.session() as s:
        res = R.create(s, admin, booking(refs, nights=4))
        frontdesk.check_in(s, admin, res.id)
        night_audit.run(s, admin)
    with pytest.raises(NeedsConfirmation):
        with db.session() as s:
            frontdesk.check_out(s, admin, res.id)
    with db.session() as s:
        folio.add_payment(s, admin, res.id, Decimal("156.00"), "Cash")
        out = frontdesk.check_out(s, admin, res.id, force=True)
    assert out.check_out == BDATE + D(days=1) and out.status == "checked_out"


def test_dirty_room_check_in_needs_confirmation(admin, refs):
    with db.session() as s:
        frontdesk.set_room_status(s, admin, refs["rooms"]["101"], "dirty")
        res = R.create(s, admin, booking(refs))
    with pytest.raises(NeedsConfirmation):
        with db.session() as s:
            frontdesk.check_in(s, admin, res.id)
    with db.session() as s:
        assert frontdesk.check_in(s, admin, res.id, force=True).status == "checked_in"


def test_foreign_currency_payment_and_reversal(admin, refs):
    with db.session() as s:
        res = R.create(s, admin, booking(refs))
        folio.add_charge(s, admin, res.id, "Airport transfer", Decimal("45"), Decimal("2"))
        line = folio.add_payment(s, admin, res.id, Decimal("15700"), "Cash", currency="JMD")
    assert line.amount == Decimal("-100.00") and line.exchange_rate == Decimal("157.0000")
    with db.session() as s:
        assert folio.balance(s, res.id) == Decimal("-10.00")
        folio.reverse(s, admin, line.id, "Entered on wrong bill")
        assert folio.balance(s, res.id) == Decimal("90.00")
    with pytest.raises(BusinessError, match="already been reversed"):
        with db.session() as s:
            folio.reverse(s, admin, line.id, "again")


def test_invoice_numbers_increment(admin, refs):
    with db.session() as s:
        res = R.create(s, admin, booking(refs))
        folio.add_charge(s, admin, res.id, "Minibar", Decimal("12.50"))
        a = folio.issue_invoice(s, admin, res.id)
        b = folio.issue_invoice(s, admin, res.id)
    assert (a.number, b.number) == ("INV-000001", "INV-000002")


# ------------------------------------------------------------------ reports
def test_reports(admin, refs):
    with db.session() as s:
        R.create(s, admin, booking(refs, nights=2))
        R.create(s, admin, booking(refs, room="201", nights=1, ))
    with db.session() as s:
        days = reports.daily(s, BDATE, BDATE + D(days=3))
        dash = reports.dashboard(s)
        months = reports.monthly(s, 2026)
    assert [d.sold for d in days] == [2, 1, 0]
    assert days[0].available == 17 and round(days[0].occupancy, 1) == 11.8
    assert days[0].room_revenue == Decimal("350.00") and days[1].room_revenue == Decimal("140.00")
    assert days[0].adr == Decimal("175.00")
    assert len(dash.arrivals) == 2 and dash.rooms_total == 17
    assert months[10].nights_sold == 3 and months[10].stays == 2


def test_guest_duplicates_and_history(admin, refs):
    with db.session() as s:
        dups = catalog.possible_duplicates(s, "alicia", "CAMPBELL", "", "")
        assert len(dups) == 1
        R.create(s, admin, booking(refs))
        assert len(catalog.guest_history(s, refs["guests"][0])) == 1


# ------------------------------------------------------------------ concurrency
def test_two_desks_book_same_room_at_once(admin, refs, database):
    if database == "sqlite":
        pytest.skip("SQLite serialises writes; this checks real row locking")
    results = []
    barrier = threading.Barrier(2)

    def desk():
        try:
            with db.session() as s:
                barrier.wait()
                R.create(s, admin, booking(refs))
            results.append("ok")
        except BusinessError as e:
            results.append(type(e).__name__)
    threads = [threading.Thread(target=desk) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == ["BusinessError", "ok"]
    with db.session() as s:
        assert len(R.room_conflicts(s, refs["rooms"]["101"], BDATE, BDATE + D(days=3))) == 1
