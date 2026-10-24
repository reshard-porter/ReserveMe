"""Reservations list, front desk, guests, housekeeping and billing pages."""
from __future__ import annotations

import datetime as dt

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QInputDialog, QLineEdit, QSplitter,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from ...services import catalog, folio, frontdesk
from ...services import reservations as R
from .. import printing
from ..common import (FAILED, Page, ask, button, call, date_edit, export_table, fill_table, from_qdate, hbox,
                      label, make_table, selected_id, state, warn)
from ..dialogs.folio import open_folio
from ..dialogs.guests import edit_guest
from ..dialogs.reservation import open_reservation
from ..theme import ROOM_STATUS_COLORS, ROOM_STATUS_LABELS, STATUS_COLORS, STATUS_LABELS


def status_item(status: str) -> QTableWidgetItem:
    it = QTableWidgetItem(STATUS_LABELS.get(status, status))
    it.setForeground(QColor(STATUS_COLORS.get(status, "#333")).darker(130))
    return it


def res_row(r) -> list:
    return [r.code, r.guest.full_name + (" ★" if r.guest.vip else ""), r.check_in, r.check_out, r.nights,
            r.room.number if r.room else "—", r.room_type.code, status_item(r.status), r.source or "",
            r.estimated_total, r.created_at]


RES_HEADERS = ["Code", "Guest", "Arrival", "Departure", "Nights", "Room", "Type", "Status", "Source", "Total", "Booked"]


# --------------------------------------------------------------------------- reservations
class ReservationsPage(Page):
    title = "Reservations"
    permission = "reservations"
    FILTERS = [("Upcoming and in house", ["tentative", "confirmed", "checked_in"]), ("All", None),
               ("Tentative", ["tentative"]), ("Checked out", ["checked_out"]), ("Cancelled", ["cancelled"]),
               ("No-shows", ["no_show"])]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.header.addWidget(button("New reservation", self.new, "primary"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search code, guest name, email, phone, room or external ref…  (Ctrl+F)")
        self.filter = QComboBox()
        for text, _ in self.FILTERS:
            self.filter.addItem(text)
        self.use_dates = QCheckBox("Staying between")
        self.d1, self.d2 = date_edit(), date_edit(state.business_date + dt.timedelta(days=30))
        self.outer.addLayout(hbox(self.search, self.filter, self.use_dates, self.d1, label("and"), self.d2))
        self.table = make_table(RES_HEADERS, stretch=1)
        self.table.doubleClicked.connect(self.open)
        self.outer.addWidget(self.table, 1)
        self.count = label("", "muted")
        self.outer.addLayout(hbox(self.count, "stretch", button("Export…", lambda: export_table(self, self.table, "Reservations.xlsx")),
                                  button("Bill…", self.bill), button("Open", self.open)))
        self.timer = QTimer(self, singleShot=True, interval=350)
        self.timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda: self.timer.start())
        for sig in (self.filter.currentIndexChanged, self.use_dates.toggled, self.d1.dateChanged, self.d2.dateChanged):
            sig.connect(lambda *_: self.timer.start())

    def focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def refresh(self):
        statuses = self.FILTERS[self.filter.currentIndex()][1]
        start = end = None
        if self.use_dates.isChecked():
            start, end = from_qdate(self.d1.date()), from_qdate(self.d2.date())
        res = call(self, R.search, self.search.text(), statuses, start, end)
        if res is FAILED:
            return
        fill_table(self.table, [res_row(r) for r in res], [r.id for r in res])
        self.count.setText(f"{len(res)} reservation(s)" + (" (first 500 shown)" if len(res) >= 500 else ""))

    def new(self):
        if open_reservation(self):
            self.refresh()

    def open(self, *_):
        rid = selected_id(self.table)
        if rid and open_reservation(self, rid):
            self.refresh()

    def bill(self):
        rid = selected_id(self.table)
        if rid:
            open_folio(self, rid)
            self.refresh()


# --------------------------------------------------------------------------- front desk
class FrontDeskPage(Page):
    title = "Front desk"
    permission = "front_desk"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.header.addWidget(button("Walk-in…", self.walk_in, "primary", "New booking arriving today"))
        self.header.addWidget(button("Refresh", self.refresh))
        self.tabs = QTabWidget()
        self.arr = make_table(["Code", "Guest", "Room", "Type", "Nights", "Status", "ETA", "Notes"], stretch=7)
        self.inh = make_table(["Code", "Guest", "Room", "Arrived", "Departs", "Nights", "Balance"], stretch=1)
        self.dep = make_table(["Code", "Guest", "Room", "Status", "Balance"], stretch=1)
        for t in (self.arr, self.inh, self.dep):
            t.doubleClicked.connect(lambda _=None, t=t: self.open(t))
        self.tabs.addTab(self._tab(self.arr, [("Check in", self.check_in, "primary"), ("Registration card", self.regcard),
                                              ("Assign room / open", lambda: self.open(self.arr))]), "Arrivals")
        self.tabs.addTab(self._tab(self.inh, [("Bill…", lambda: self.bill(self.inh)), ("Move room…", self.move_room),
                                              ("Check out", lambda: self.check_out(self.inh)),
                                              ("Open", lambda: self.open(self.inh))]), "In house")
        self.tabs.addTab(self._tab(self.dep, [("Bill…", lambda: self.bill(self.dep)),
                                              ("Check out", lambda: self.check_out(self.dep), "primary"),
                                              ("Open", lambda: self.open(self.dep))]), "Departures")
        self.outer.addWidget(self.tabs, 1)

    def _tab(self, table, actions):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(table)
        btns = ["stretch"] + [button(a[0], a[1], a[2] if len(a) > 2 else None) for a in actions]
        lay.addLayout(hbox(*btns))
        return w

    def refresh(self):
        def load(s):
            bdate = frontdesk.settings(s).business_date
            arr = [r for r in frontdesk.arrivals(s, bdate) if r.status != "checked_in"]
            inh = frontdesk.in_house(s)
            dep = frontdesk.departures(s, bdate)
            bal = {r.id: b for r, b in folio.open_balances(s)}
            return bdate, arr, inh, dep, bal
        data = call(self, load)
        if data is FAILED:
            return
        bdate, arr, inh, dep, bal = data
        fill_table(self.arr, [[r.code, r.guest.full_name + (" ★" if r.guest.vip else ""), r.room.number if r.room else "— assign —",
                               r.room_type.code, r.nights, status_item(r.status), r.arrival_time or "", r.notes or ""]
                              for r in arr], [r.id for r in arr])
        fill_table(self.inh, [[r.code, r.guest.full_name, r.room.number if r.room else "", r.check_in, r.check_out,
                               r.nights, bal.get(r.id, 0)] for r in inh], [r.id for r in inh])
        fill_table(self.dep, [[r.code, r.guest.full_name, r.room.number if r.room else "", status_item(r.status),
                               bal.get(r.id, 0)] for r in dep], [r.id for r in dep])
        self.tabs.setTabText(0, f"Arrivals ({len(arr)})")
        self.tabs.setTabText(1, f"In house ({len(inh)})")
        self.tabs.setTabText(2, f"Departures ({sum(1 for r in dep if r.status == 'checked_in')} left of {len(dep)})")

    def _sel(self, t):
        rid = selected_id(t)
        if not rid:
            warn(self, "Select a guest in the list first.")
        return rid

    def walk_in(self):
        if open_reservation(self, None, check_in=state.business_date):
            self.refresh()

    def open(self, t):
        rid = self._sel(t)
        if rid and open_reservation(self, rid):
            self.refresh()

    def check_in(self):
        rid = self._sel(self.arr)
        if not rid:
            return
        res = call(self, frontdesk.check_in, state.actor, rid)
        if res is not FAILED:
            state.changed()
            self.refresh()
            if ask(self, "Checked in", f"{res.guest.full_name} is checked in to room {res.room.number}.\n\n"
                                       "Print the registration card now?"):
                self._print_regcard(rid)

    def regcard(self):
        rid = self._sel(self.arr)
        if rid:
            self._print_regcard(rid)

    def _print_regcard(self, rid):
        doc = call(self, lambda s: printing.registration_card_html(s, R.get(s, rid)))
        if doc is not FAILED:
            printing.show(self, "Registration card", doc, "Registration card.pdf")

    def check_out(self, t):
        rid = self._sel(t)
        if not rid:
            return
        res = call(self, frontdesk.check_out, state.actor, rid)
        if res is FAILED:
            bal = call(self, folio.balance, rid)
            if bal is not FAILED and bal != 0 and ask(self, "Settle the bill?", "Open the bill to settle the balance now?"):
                open_folio(self, rid)
                self.refresh()
            return
        state.changed()
        self.refresh()

    def bill(self, t):
        rid = self._sel(t)
        if rid:
            open_folio(self, rid)
            self.refresh()

    def move_room(self):
        rid = self._sel(self.inh)
        if not rid:
            return
        def load(s):
            r = R.get(s, rid)
            return r, R.available_rooms(s, frontdesk.settings(s).business_date, r.check_out, None, rid)
        data = call(self, load)
        if data is FAILED:
            return
        res, rooms = data
        if not rooms:
            warn(self, "No other rooms are free for the rest of this stay.")
            return
        names = [f"{r.number} – {r.room_type.name} ({ROOM_STATUS_LABELS[r.status]})" for r in rooms]
        choice, okd = QInputDialog.getItem(self, "Move room", f"Move {res.guest.full_name} from room "
                                           f"{res.room.number} to:", names, 0, False)
        if okd:
            room = rooms[names.index(choice)]
            if call(self, R.move, state.actor, rid, room.id) is not FAILED:
                state.changed()
                self.refresh()


# --------------------------------------------------------------------------- guests
class GuestsPage(Page):
    title = "Guests"
    permission = "guests"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.header.addWidget(button("New guest", self.new, "primary"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search name, email, phone, company or ID number…")
        self.outer.addWidget(self.search)
        split = QSplitter(Qt.Vertical)
        self.table = make_table(["Name", "Email", "Phone", "Nationality", "Company", "VIP", "Notes"], stretch=6)
        self.table.doubleClicked.connect(self.edit)
        self.table.itemSelectionChanged.connect(self.load_history)
        split.addWidget(self.table)
        hist = QWidget()
        hl = QVBoxLayout(hist)
        hl.setContentsMargins(0, 8, 0, 0)
        hl.addWidget(label("Stay history", "h2"))
        self.history = make_table(RES_HEADERS, stretch=1)
        self.history.doubleClicked.connect(self.open_res)
        hl.addWidget(self.history)
        split.addWidget(hist)
        split.setSizes([400, 220])
        self.outer.addWidget(split, 1)
        self.outer.addLayout(hbox("stretch", button("Export…", lambda: export_table(self, self.table, "Guests.xlsx")),
                                  button("New booking for guest", self.book), button("Edit", self.edit)))
        self.timer = QTimer(self, singleShot=True, interval=350)
        self.timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda: self.timer.start())

    def refresh(self):
        gs = call(self, catalog.search_guests, self.search.text())
        if gs is FAILED:
            return
        fill_table(self.table, [[g.full_name + (" ⛔" if g.blacklisted else ""), g.email, g.phone, g.nationality,
                                 g.company, "★" if g.vip else "", (g.notes or "")[:80]] for g in gs], [g.id for g in gs])

    def load_history(self):
        gid = selected_id(self.table)
        if not gid:
            self.history.setRowCount(0)
            return
        hs = call(self, catalog.guest_history, gid)
        if hs is not FAILED:
            fill_table(self.history, [res_row(r) for r in hs], [r.id for r in hs])

    def new(self):
        if edit_guest(self):
            self.refresh()

    def edit(self, *_):
        gid = selected_id(self.table)
        if gid and edit_guest(self, gid):
            self.refresh()

    def open_res(self, *_):
        rid = selected_id(self.history)
        if rid and open_reservation(self, rid):
            self.load_history()

    def book(self):
        gid = selected_id(self.table)
        if not gid:
            return
        from ..dialogs.reservation import ReservationDialog
        dlg = ReservationDialog(self)
        if hasattr(dlg, "ci"):
            g = call(self, lambda s: s.get(catalog.Guest, gid))
            if g is not FAILED and g:
                dlg._set_guest(g)
                dlg._update_buttons()
            dlg.exec()
            self.load_history()


# --------------------------------------------------------------------------- housekeeping
class HousekeepingPage(Page):
    title = "Housekeeping"
    permission = "housekeeping"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.header.addWidget(button("Refresh", self.refresh))
        self.filter = QComboBox()
        self.filter.addItem("All rooms", None)
        for k, v in ROOM_STATUS_LABELS.items():
            self.filter.addItem(v, k)
        self.filter.currentIndexChanged.connect(lambda _: self.refresh())
        self.outer.addLayout(hbox(label("Show"), self.filter, "stretch"))
        self.table = make_table(["Room", "Type", "Building / floor", "Status", "Occupancy", "Notes"], stretch=4)
        self.table.setSelectionMode(self.table.SelectionMode.ExtendedSelection)
        self.outer.addWidget(self.table, 1)
        self.outer.addLayout(hbox(
            button("Print sheet", self.print_sheet), "stretch",
            button("Mark dirty", lambda: self.set_status("dirty")),
            button("Mark clean", lambda: self.set_status("clean"), "primary"),
            button("Mark inspected", lambda: self.set_status("inspected")),
            button("Out of order…", lambda: self.set_status("out_of_order"), "danger"),
            button("Back in service", lambda: self.set_status("clean"))))

    def refresh(self):
        board = call(self, frontdesk.room_board)
        if board is FAILED:
            return
        want = self.filter.currentData()
        rows, ids = [], []
        for room, occ, arr in board:
            if want and room.status != want:
                continue
            st = QTableWidgetItem(ROOM_STATUS_LABELS.get(room.status, room.status))
            st.setForeground(QColor(ROOM_STATUS_COLORS.get(room.status, "#333")).darker(110))
            if occ:
                o = f"Occupied – {occ.guest.full_name} until {occ.check_out:%d %b}" + (
                    " (departs today)" if occ.check_out == state.business_date else "")
            elif arr:
                o = f"Vacant – arriving today: {arr.guest.full_name}" + (f" at {arr.arrival_time}" if arr.arrival_time else "")
            else:
                o = "Vacant"
            rows.append([room.number, room.room_type.name, " / ".join(x for x in (room.building, room.floor) if x), st,
                         o, room.notes or ""])
            ids.append(room.id)
        fill_table(self.table, rows, ids)

    def _selected(self):
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        return [self.table.item(r, 0).data(Qt.UserRole) for r in rows]

    def set_status(self, status):
        ids = self._selected()
        if not ids:
            warn(self, "Select one or more rooms first.")
            return
        note = None
        if status == "out_of_order":
            note, okd = QInputDialog.getText(self, "Out of order", "Reason (e.g. AC repair until Friday):")
            if not okd:
                return
        def work(s):
            for rid in ids:
                frontdesk.set_room_status(s, state.actor, rid, status, note)
        if call(self, work) is not FAILED:
            state.changed()
            self.refresh()

    def print_sheet(self):
        printing.show(self, "Housekeeping sheet", printing.table_widget_html(
            self.table, "Housekeeping sheet", f"Business date {state.business_date:%d %b %Y}"), "Housekeeping.pdf")


# --------------------------------------------------------------------------- billing
class BillingPage(Page):
    title = "Billing"
    permission = "billing"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.header.addWidget(button("Refresh", self.refresh))
        self.only_house = QCheckBox("In-house guests only")
        self.only_house.toggled.connect(lambda _: self.refresh())
        self.outer.addLayout(hbox(label("Bills that are not settled (balance is not zero)."), "stretch", self.only_house))
        self.table = make_table(["Code", "Guest", "Room", "Arrival", "Departure", "Status", "Balance"], stretch=1)
        self.table.doubleClicked.connect(self.open)
        self.outer.addWidget(self.table, 1)
        self.total = label("", "h2")
        self.find = QLineEdit()
        self.find.setPlaceholderText("Find any reservation's bill by code or guest name, then press Enter")
        self.find.returnPressed.connect(self.find_bill)
        self.outer.addLayout(hbox(self.total, "stretch", self.find,
                                  button("Export…", lambda: export_table(self, self.table, "Open balances.xlsx")),
                                  button("Open bill", self.open, "primary")))

    def refresh(self):
        data = call(self, folio.open_balances, not self.only_house.isChecked())
        if data is FAILED:
            return
        fill_table(self.table, [[r.code, r.guest.full_name, r.room.number if r.room else "—", r.check_in, r.check_out,
                                 status_item(r.status), b] for r, b in data], [r.id for r, _ in data])
        total = sum((b for _, b in data), 0)
        self.total.setText(f"Outstanding: {state.base_currency} {total:,.2f}")

    def open(self, *_):
        rid = selected_id(self.table)
        if rid:
            open_folio(self, rid)
            self.refresh()

    def find_bill(self):
        found = call(self, R.search, self.find.text(), None, None, None, 20)
        if found is FAILED:
            return
        if not found:
            warn(self, "No reservation matches.")
            return
        if len(found) == 1:
            open_folio(self, found[0].id)
        else:
            names = [f"{r.code} – {r.guest.full_name} – {r.check_in:%d %b %Y}" for r in found]
            choice, okd = QInputDialog.getItem(self, "Choose reservation", "Several reservations match:", names, 0, False)
            if okd:
                open_folio(self, found[names.index(choice)].id)
        self.refresh()
