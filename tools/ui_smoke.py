"""Headless smoke test: opens every screen against a real database and saves screenshots.

Usage: QT_QPA_PLATFORM=offscreen python tools/ui_smoke.py <database-url> <output-folder>
"""
from __future__ import annotations

import datetime as dt
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402
from sqlalchemy import select  # noqa: E402

from reserveme import db  # noqa: E402
from reserveme.models import Guest, RatePlan, Room, RoomType, User  # noqa: E402
from reserveme.services import auth, folio, frontdesk  # noqa: E402
from reserveme.services import reservations as R  # noqa: E402
from reserveme.services.common import settings  # noqa: E402
from reserveme.ui import theme  # noqa: E402
from reserveme.ui.common import state  # noqa: E402

D = dt.timedelta


def demo_data(actor):
    names = [("Daniel", "Brown"), ("Keisha", "Williams"), ("Oliver", "Smith"), ("Grace", "Johnson"),
             ("Liam", "O'Connor"), ("Priya", "Patel"), ("Carlos", "Mendez"), ("Emma", "Wilson"), ("Noah", "Clarke"),
             ("Ava", "Reid"), ("Lucas", "Martin"), ("Chloe", "Davis")]
    with db.session() as s:
        for f, l in names:
            s.add(Guest(first_name=f, last_name=l, email=f"{f.lower()}@example.com", phone="+1 876 555 01" + str(len(l)),
                        nationality="Jamaican" if len(f) % 2 else "American", id_type="Passport", id_number=f"P{len(f)}{len(l)}9921"))
        s.flush()
        bdate = settings(s).business_date
        guests = list(s.scalars(select(Guest)))
        rooms = list(s.scalars(select(Room)))
        plans = {p.code: p.id for p in s.scalars(select(RatePlan))}
        plan_cycle = ["RO", "BB"]
        bookings = [(0, 0, 3), (1, 1, 2), (2, 2, 5), (3, 6, 4), (4, 7, 2), (5, 8, 6), (6, 12, 3), (7, 15, 7),
                    (8, 3, 1), (9, 9, 3), (10, 13, 2), (11, 16, 4), (12, 4, 2), (13, 10, 5), (14, 11, 2)]
        made = []
        for i, (gi, ri, n) in enumerate(bookings):
            room = rooms[ri % len(rooms)]
            start = bdate + D(days=(i * 2) % 9 - (1 if i < 4 else 0) * 0)
            data = R.ReservationInput(guest_id=guests[gi % len(guests)].id, room_type_id=room.room_type_id,
                                      rate_plan_id=plans[plan_cycle[i % 2]], room_id=room.id, check_in=start,
                                      check_out=start + D(days=n), adults=2, children=i % 2,
                                      status="tentative" if i % 5 == 4 else "confirmed",
                                      source=["Direct", "Booking.com", "Expedia", "Phone"][i % 4])
            try:
                made.append(R.create(s, actor, data, force=True))
            except Exception as e:  # noqa: BLE001
                print("skip", e)
        # two unassigned bookings
        stype = s.scalar(select(RoomType).where(RoomType.code == "STE"))
        for k in range(2):
            made.append(R.create(s, actor, R.ReservationInput(guest_id=guests[k + 3].id, room_type_id=stype.id,
                        rate_plan_id=plans["BB"], check_in=bdate + D(days=4 + k), check_out=bdate + D(days=7 + k),
                        adults=2), force=True))
    with db.session() as s:
        today = [r for r in made if r.check_in == bdate and r.room_id]
        for r in today[:3]:
            frontdesk.check_in(s, actor, r.id, force=True)
        if today:
            folio.add_charge(s, actor, today[0].id, "Dinner – Seaside Grill", Decimal("86.50"))
            folio.add_payment(s, actor, today[0].id, Decimal("200"), "Card (terminal)", "AUTH 448210")
        frontdesk.set_room_status(s, actor, rooms[5].id, "dirty")
        frontdesk.set_room_status(s, actor, rooms[14].id, "out_of_order", "AC repair")


def main(url: str, out: str):
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    theme.apply(app)
    db.init(url)
    db.check_ready()
    with db.session() as s:
        actor, _ = auth.login(s, "admin", "ChangeMe2026!")
    demo_data(actor)
    state.actor = actor
    state.reload()

    from reserveme.ui.dialogs.connection import ConnectionDialog
    from reserveme.ui.dialogs.login import LoginDialog
    from reserveme.ui.main_window import MainWindow
    from reserveme import config

    def shot(w, name):
        w.repaint()
        app.processEvents()
        w.grab().save(str(out_dir / f"{name}.png"))
        print("saved", name)

    c = ConnectionDialog(config.ConnectionConfig(engine="postgresql", host="abc123.h.filess.io", port=5432,
                                                 database="reserveme_db", username="reserveme_user"))
    c.show()
    shot(c, "00_connection")
    c.close()
    lg = LoginDialog(connection_text="reserveme_user@abc123.h.filess.io:5432/reserveme_db")
    lg.show()
    shot(lg, "01_login")
    lg.close()

    win = MainWindow()
    win.resize(1440, 880)
    win.show()
    app.processEvents()
    for i, page in enumerate(win.pages):
        win.sidebar.setCurrentRow(i)
        app.processEvents()
        shot(win, f"{i + 2:02d}_{page.title.lower().replace(' ', '_')}")
    # reports variations
    from reserveme.ui.pages.management import ReportsPage
    from reserveme.ui.pages.settings import SettingsPage
    for i, p in enumerate(win.pages):
        if isinstance(p, ReportsPage):
            win.sidebar.setCurrentRow(i)
            p.kind.setCurrentIndex(1)
            p.refresh()
            shot(win, "20_report_daily")
            p.kind.setCurrentIndex(0)
            p.refresh()
            shot(win, "21_report_monthly")
        if isinstance(p, SettingsPage):
            win.sidebar.setCurrentRow(i)
            p.tabs.setCurrentIndex(4)
            shot(win, "22_settings_rates")
    # dialogs
    from reserveme.ui.dialogs.reservation import ReservationDialog
    from reserveme.ui.dialogs.folio import FolioDialog
    with db.session() as s:
        inhouse = frontdesk.in_house(s)
        first = R.search(s, "", ["confirmed"])[0]
    dlg = ReservationDialog(win, first.id)
    dlg.show()
    shot(dlg, "30_reservation_dialog")
    dlg.close()
    nd = ReservationDialog(win, None, check_in=state.business_date + D(days=3), nights=4)
    nd.show()
    shot(nd, "31_new_reservation")
    nd.close()
    if inhouse:
        fd = FolioDialog(win, inhouse[0].id)
        fd.show()
        shot(fd, "32_folio")
        fd.close()
    from reserveme.ui import printing
    with db.session() as s:
        r = R.get(s, inhouse[0].id)
        html = printing.folio_html(s, r, folio.summary(s, r.id))
    pd = printing.DocumentDialog(win, "Bill", html, "x.pdf")
    pd.show()
    shot(pd, "33_bill_preview")
    pd.close()
    win.close()
    print("OK")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
