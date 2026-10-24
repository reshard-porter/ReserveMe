"""Drive the real windows through a day's work (message boxes auto-answered).

Usage: QT_QPA_PLATFORM=offscreen python tools/ui_workflow_test.py <database-url>
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QItemSelectionModel
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from sqlalchemy import select

from reserveme import db
from reserveme.models import Guest, Reservation, Room
from reserveme.services import folio
from reserveme.ui import theme
from reserveme.ui.common import state

messages = []
QMessageBox.question = staticmethod(lambda *a, **k: (messages.append(("Q", a[2])), QMessageBox.Yes)[1])
QMessageBox.information = staticmethod(lambda *a, **k: messages.append(("I", a[2] if len(a) > 2 else "")))
QMessageBox.warning = staticmethod(lambda *a, **k: messages.append(("W", a[2] if len(a) > 2 else "")))
QMessageBox.critical = staticmethod(lambda *a, **k: messages.append(("C", a[2] if len(a) > 2 else "")))
QDialog.exec = lambda self: 0  # nested dialogs (printing etc.) close immediately


def select_row(table, rid):
    for r in range(table.rowCount()):
        if table.item(r, 0).data(256) == rid:
            table.selectionModel().select(table.model().index(r, 0),
                                          QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
            return True
    raise AssertionError(f"row {rid} not found")


def main(url):
    app = QApplication(sys.argv)
    theme.apply(app)
    db.init(url)
    db.check_ready()
    state.reload()

    from reserveme.ui.dialogs.login import ChangePasswordDialog, LockDialog, LoginDialog
    lg = LoginDialog()
    lg.username.setText("admin")
    lg.password.setText("wrong")
    lg._login()
    assert lg.actor is None and messages[-1][0] == "W", messages[-1]
    lg.password.setText("ChangeMe2026!")
    lg._login()
    assert lg.actor and lg.must_change
    state.actor = lg.actor
    cp = ChangePasswordDialog(state.actor, forced=True)
    cp.old.setText("ChangeMe2026!")
    cp.new.setText("Resort2026Pass")
    cp.again.setText("Resort2026Pass")
    cp._save()
    print("login + password change ok")

    from reserveme.ui.main_window import MainWindow
    from reserveme.ui.dialogs.reservation import ReservationDialog
    from reserveme.ui.pages.operations import FrontDeskPage
    from reserveme.ui.pages.tapechart import TapeChartPage, BookingBar
    from reserveme.ui.pages.management import NightAuditPage
    win = MainWindow()
    win.show()

    with db.session() as s:
        g = s.scalar(select(Guest).where(Guest.last_name == "Thompson"))
    dlg = ReservationDialog(win, None, check_in=state.business_date, nights=2)
    dlg._set_guest(g)
    dlg.rtype.setCurrentIndex(1)  # Deluxe
    dlg._refresh_rooms()
    dlg.room.setCurrentIndex(1)
    dlg.save()
    assert dlg.res and dlg.res.room is not None, messages[-3:]
    rid = dlg.res.id
    print("created", dlg.res.code, "room", dlg.res.room.number, "total", dlg.res.estimated_total)

    # second booking that clashes with the first must be refused
    dlg2 = ReservationDialog(win, None, check_in=state.business_date, nights=1)
    dlg2._set_guest(g)
    dlg2.rtype.setCurrentIndex(1)
    dlg2._refresh_rooms()
    dlg2.room.addItem("clash", dlg.res.room_id)
    dlg2.room.setCurrentIndex(dlg2.room.count() - 1)
    n = len(messages)
    dlg2.save()
    assert dlg2.res is None and "already booked" in messages[-1][1], messages[n:]
    print("clash refused:", messages[-1][1][:70])

    fd = next(p for p in win.pages if isinstance(p, FrontDeskPage))
    fd.refresh()
    select_row(fd.arr, rid)
    fd.check_in()
    with db.session() as s:
        assert s.get(Reservation, rid).status == "checked_in"
    print("checked in via front desk")

    tc = next(p for p in win.pages if isinstance(p, TapeChartPage))
    tc.refresh()
    bars = [i for i in tc.grid_scene.items() if isinstance(i, BookingBar) and i.res.id == rid]
    assert bars, "booking bar missing"
    with db.session() as s:
        other = s.scalar(select(Room).where(Room.number == "206"))
    tc.move_booking(bars[0], other.id, bars[0].res.check_in)
    app.processEvents()
    with db.session() as s:
        assert s.get(Reservation, rid).room_id == other.id
    print("moved on tape chart to 206")

    na = next(p for p in win.pages if isinstance(p, NightAuditPage))
    na.refresh()
    na.run()
    app.processEvents()
    with db.session() as s:
        bal = folio.balance(s, rid)
    assert bal > 0, bal
    print("night audit ok; business date now", state.business_date, "balance", bal)

    lock = LockDialog(state.actor, win)
    lock.password.setText("nope")
    lock._unlock()
    assert lock.error.text()
    lock.password.setText("Resort2026Pass")
    lock._unlock()
    print("lock screen ok")
    errors = [m for m in messages if m[0] == "C"]
    assert not errors, errors
    win.close()
    print("WORKFLOW OK")


if __name__ == "__main__":
    main(sys.argv[1])
