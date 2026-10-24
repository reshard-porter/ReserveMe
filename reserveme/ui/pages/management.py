"""Reports and night audit pages."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QSpinBox

from ...models import NightAuditRun
from ...services import night_audit, reports
from .. import printing
from ..common import (FAILED, NumItem, Page, ask, button, call, card, date_edit, export_table, fill_table, fmt_money,
                      from_qdate, hbox, info, label, make_table, state)
from ..theme import STATUS_LABELS


class ReportsPage(Page):
    title = "Reports"
    permission = "reports"
    REPORTS = [
        ("monthly", "Monthly performance (year)", "year"),
        ("daily", "Daily occupancy and revenue", "range"),
        ("arrivals", "Arrivals list", "day"),
        ("departures", "Departures list", "day"),
        ("register", "Guest register (in house on a night)", "day"),
        ("cashier", "Cashier report (business date)", "day"),
        ("created", "Reservations made", "range"),
        ("cancelled", "Cancellations and no-shows (by arrival date)", "range"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.kind = QComboBox()
        for key, text, _ in self.REPORTS:
            self.kind.addItem(text, key)
        self.d1 = date_edit(state.business_date.replace(day=1))
        self.d2 = date_edit(state.business_date + dt.timedelta(days=30))
        self.day = date_edit(state.business_date)
        self.year = QSpinBox()
        self.year.setRange(2000, 2100)
        self.year.setValue(state.business_date.year)
        self.l_from, self.l_to, self.l_day, self.l_year = label("From"), label("to"), label("Date"), label("Year")
        self.outer.addLayout(hbox(self.kind, self.l_year, self.year, self.l_from, self.d1, self.l_to, self.d2,
                                  self.l_day, self.day, button("Run", self.refresh, "primary"), "stretch"))
        self.summary = label("", "h2")
        self.outer.addWidget(self.summary)
        self.table = make_table(["Report"], stretch=None)
        self.outer.addWidget(self.table, 1)
        self.outer.addLayout(hbox(label("Future nights use booked rates; past nights use posted charges.", "muted"),
                                  "stretch", button("Print / PDF…", self.print_), button("Export…", self.export)))
        self.kind.currentIndexChanged.connect(self._mode)
        self._mode()

    def _mode(self):
        mode = self.REPORTS[self.kind.currentIndex()][2]
        for w in (self.l_from, self.d1, self.l_to, self.d2):
            w.setVisible(mode == "range")
        for w in (self.l_day, self.day):
            w.setVisible(mode == "day")
        for w in (self.l_year, self.year):
            w.setVisible(mode == "year")

    def _set(self, headers, rows, summary=""):
        self.table.clear()
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        fill_table(self.table, rows)
        self.summary.setText(summary)

    def refresh(self):
        key = self.kind.currentData()
        d1, d2, day = from_qdate(self.d1.date()), from_qdate(self.d2.date()), from_qdate(self.day.date())
        cur = state.base_currency
        if key in ("daily", "created", "cancelled") and d2 <= d1:
            return
        if key == "monthly":
            ms = call(self, reports.monthly, self.year.value())
            if ms is FAILED:
                return
            metrics = [("Room nights sold", lambda m: m.nights_sold),
                       ("Occupancy %", lambda m: NumItem(m.occupancy, f"{m.occupancy:.1f}%")),
                       (f"Room revenue ({cur})", lambda m: m.room_revenue), (f"ADR ({cur})", lambda m: m.adr),
                       (f"RevPAR ({cur})", lambda m: m.revpar), ("Avg. length of stay", lambda m: NumItem(m.alos, f"{m.alos:.1f}")),
                       ("Arrivals", lambda m: m.stays), ("Room nights available", lambda m: m.nights_available)]
            rows = [[name] + [fn(m) for m in ms] for name, fn in metrics]
            sold, avail = sum(m.nights_sold for m in ms), sum(m.nights_available for m in ms)
            rev = sum((m.room_revenue for m in ms), Decimal(0))
            self._set(["Measure"] + [m.label for m in ms], rows,
                      f"{self.year.value()}: {sold} room nights · occupancy {sold / avail * 100 if avail else 0:.1f}% · "
                      f"revenue {cur} {fmt_money(rev)}")
            self.table.setSortingEnabled(False)
            self.table.horizontalHeader().setStretchLastSection(False)
        elif key == "daily":
            ds = call(self, reports.daily, d1, d2)
            if ds is FAILED:
                return
            rows = [[d.date, d.date.strftime("%a"), d.available, d.sold, NumItem(d.occupancy, f"{d.occupancy:.1f}%"), d.arrivals, d.departures,
                     d.room_revenue, d.adr, d.revpar, "posted" if d.actual else "forecast"] for d in ds]
            sold, avail = sum(d.sold for d in ds), sum(d.available for d in ds)
            rev = sum((d.room_revenue for d in ds), Decimal(0))
            self._set(["Night", "Day", "Rooms", "Sold", "Occ.", "Arr.", "Dep.", f"Revenue ({cur})", "ADR", "RevPAR",
                       "Basis"], rows, f"{sold} room nights of {avail} · occupancy {sold / avail * 100 if avail else 0:.1f}% · "
                                       f"revenue {cur} {fmt_money(rev)} · ADR {fmt_money(rev / sold if sold else 0)}")
        elif key in ("arrivals", "departures", "register"):
            fn = {"arrivals": lambda s: reports.arrivals(s, day), "departures": lambda s: reports.departures(s, day),
                  "register": lambda s: reports.guest_register(s, day)}[key]
            rs = call(self, fn)
            if rs is FAILED:
                return
            if key == "register":
                rows = [[r.room.number if r.room else "", r.guest.full_name, r.guest.nationality, r.guest.id_type,
                         r.guest.id_number, r.check_in, r.check_out, r.adults + r.children] for r in rs]
                self._set(["Room", "Guest", "Nationality", "ID type", "ID number", "Arrival", "Departure", "Persons"],
                          rows, f"{len(rs)} room(s) occupied on the night of {day:%d %b %Y}")
            else:
                rows = [[r.code, r.guest.full_name, r.room.number if r.room else "—", r.room_type.code, r.check_in,
                         r.check_out, r.adults, r.children, STATUS_LABELS[r.status], r.notes or ""] for r in rs]
                self._set(["Code", "Guest", "Room", "Type", "Arrival", "Departure", "Adults", "Children", "Status",
                           "Notes"], rows, f"{len(rs)} {key} on {day:%d %b %Y}")
        elif key == "cashier":
            ls = call(self, reports.cashier, day)
            if ls is FAILED:
                return
            rows, by_method, by_kind = [], defaultdict(Decimal), defaultdict(Decimal)
            for l in ls:
                rows.append([l.posted_at, l.kind.title(), l.reservation.code, l.reservation.guest.full_name, l.description,
                             l.method or "", l.reference or "", l.amount, l.user.username if l.user else ""])
                if l.kind == "payment":
                    by_method[l.method or "Other"] += -l.amount
                else:
                    by_kind[l.kind] += l.amount
            summ = " · ".join(f"{m}: {fmt_money(v)}" for m, v in by_method.items()) or "No payments"
            chg = " · ".join(f"{k.title()}: {fmt_money(v)}" for k, v in by_kind.items()) or "No charges"
            self._set(["Time", "Type", "Res.", "Guest", "Description", "Method", "Reference", f"Amount ({cur})", "By"],
                      rows, f"Received – {summ}<br/>Charged – {chg}")
        else:
            by = "created" if key == "created" else "arrival"
            rs = call(self, reports.reservation_list, d1, d2, by)
            if rs is FAILED:
                return
            if key == "cancelled":
                rs = [r for r in rs if r.status in ("cancelled", "no_show")]
            rows = [[r.code, r.created_at, r.guest.full_name, r.check_in, r.nights, r.room_type.code, r.source or "",
                     STATUS_LABELS[r.status], r.estimated_total, r.cancel_reason or ""] for r in rs]
            total = sum((r.estimated_total for r in rs), Decimal(0))
            self._set(["Code", "Booked", "Guest", "Arrival", "Nights", "Type", "Source", "Status", f"Value ({cur})",
                       "Cancel reason"], rows, f"{len(rs)} reservation(s) · {sum(r.nights for r in rs)} nights · "
                                               f"value {cur} {fmt_money(total)}")

    def _title(self):
        return self.kind.currentText()

    def print_(self):
        printing.show(self, self._title(), printing.table_widget_html(self.table, self._title(),
                      self.summary.text().replace("<br/>", " · ")), f"{self._title()}.pdf")

    def export(self):
        export_table(self, self.table, f"{self._title()}.xlsx")


class NightAuditPage(Page):
    title = "Night audit"
    permission = "night_audit"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.header.addWidget(button("Refresh", self.refresh))
        self.lead = label("", "h2")
        self.lead.setWordWrap(True)
        self.outer.addWidget(self.lead)
        f1, l1 = card("Still in house but due to leave (must be checked out or extended first)")
        self.pending = make_table(["Code", "Guest", "Room", "Due out"], stretch=1)
        l1.addWidget(self.pending)
        f2, l2 = card("Expected today but not arrived (will become no-shows)")
        self.noshow = make_table(["Code", "Guest", "Room", "Type", "Status"], stretch=1)
        l2.addWidget(self.noshow)
        f3, l3 = card("Recent audits")
        self.runs = make_table(["Business date", "Run at", "Rooms posted", "Room revenue", "Tax", "No-shows"], stretch=None)
        l3.addWidget(self.runs)
        self.outer.addLayout(hbox(f1, f2))
        self.outer.addWidget(f3, 1)
        self.run_btn = button("Run night audit", self.run, "primary")
        self.outer.addLayout(hbox(label("Posts tonight's room charges and taxes, marks no-shows, marks occupied rooms "
                                        "for cleaning, and moves to the next business date.", "muted"), "stretch",
                                  self.run_btn))

    def refresh(self):
        def load(s):
            from sqlalchemy import select
            return night_audit.preview(s), list(s.scalars(select(NightAuditRun).order_by(NightAuditRun.business_date.desc()).limit(30)))
        data = call(self, load)
        if data is FAILED:
            return
        pv, runs = data
        self.lead.setText(f"Closing business date {pv.business_date:%A %d %B %Y} · {len(pv.in_house)} room(s) will be "
                          f"charged · {len(pv.expected_no_shows)} no-show(s)")
        fill_table(self.pending, [[r.code, r.guest.full_name, r.room.number if r.room else "", r.check_out]
                                  for r in pv.pending_departures], [r.id for r in pv.pending_departures])
        fill_table(self.noshow, [[r.code, r.guest.full_name, r.room.number if r.room else "—", r.room_type.code,
                                  STATUS_LABELS[r.status]] for r in pv.expected_no_shows])
        fill_table(self.runs, [[r.business_date, r.run_at, r.rooms_posted, r.room_revenue, r.tax_revenue, r.no_shows]
                               for r in runs])
        self.run_btn.setEnabled(pv.can_run)
        self.run_btn.setToolTip("" if pv.can_run else "Check out or extend the guests listed first.")

    def run(self):
        if not ask(self, "Run night audit", f"Close business date {state.business_date:%d %b %Y}?\n\n"
                                            "This cannot be undone."):
            return
        res = call(self, night_audit.run, state.actor)
        if res is FAILED:
            return
        state.reload()
        state.changed()
        info(self, f"Night audit complete.\n\n{res.rooms_posted} room(s) charged, room revenue "
                   f"{fmt_money(res.room_revenue, state.base_currency)}, {res.no_shows} no-show(s).\n\n"
                   f"New business date: {state.business_date:%A %d %B %Y}.")
        self.refresh()
