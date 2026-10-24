"""Create or edit a reservation, with a live price quote."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QGridLayout,
                               QGroupBox, QHBoxLayout, QInputDialog, QLineEdit, QPlainTextEdit, QSpinBox,
                               QVBoxLayout)

from ...models import SOURCES
from ...services import catalog, frontdesk
from ...services import folio as folio_svc
from ...services import reservations as R
from ...services.pricing import RateBook
from .. import printing
from ..common import (FAILED, ask, button, call, date_edit, fill_table, fmt_money, from_qdate, hbox, info,
                      label, make_table, state, to_qdate, warn)
from ..theme import STATUS_COLORS, STATUS_LABELS
from .folio import open_folio
from .guests import edit_guest, pick_guest


class ReservationDialog(QDialog):
    def __init__(self, parent, res_id: int | None = None, *, check_in: dt.date | None = None,
                 room_id: int | None = None, room_type_id: int | None = None, nights: int = 1):
        super().__init__(parent)
        self.res_id, self.res = res_id, None
        self.guest_id: int | None = None
        self.saved = False
        self.setWindowTitle("Reservation" if res_id else "New reservation")
        self.resize(1040, 660)
        loaded = call(self, self._load_lookups)
        if loaded is FAILED:
            QTimer.singleShot(0, self.reject)
            return
        self._build()
        self._loading = True
        if self.res:
            self._fill_from(self.res)
        else:
            ci = check_in or state.business_date
            self.ci.setDate(to_qdate(ci))
            self.co.setDate(to_qdate(ci + dt.timedelta(days=max(1, nights))))
            if room_id:
                rt = next((r.room_type_id for r in self.all_rooms if r.id == room_id), None)
                room_type_id = rt or room_type_id
            if room_type_id:
                self.rtype.setCurrentIndex(max(0, self.rtype.findData(room_type_id)))
            self._preselect_room = room_id
            self.status.setCurrentIndex(1)
        ci, co = from_qdate(self.ci.date()), from_qdate(self.co.date())
        self.nights.setValue(max(1, (co - ci).days))
        self.co.setMinimumDate(to_qdate(ci + dt.timedelta(days=1)))
        self._loading = False
        self._update_buttons()
        self._update_quote()
        self._refresh_rooms()

    # ------------------------------------------------------------ data
    def _load_lookups(self, s):
        self.types = catalog.room_types(s, active_only=True)
        self.plans = catalog.rate_plans(s, active_only=True)
        self.all_rooms = catalog.rooms(s, active_only=True)
        self.book = RateBook(s)
        if self.res_id:
            self.res = R.get(s, self.res_id)
        if not self.types or not self.plans:
            raise R.BusinessError("Set up room types and rate plans in Settings first.")

    # ------------------------------------------------------------ layout
    def _build(self):
        outer = QVBoxLayout(self)
        self.title = label("New reservation", "h1")
        outer.addWidget(self.title)
        body = QHBoxLayout()
        outer.addLayout(body, 1)

        left = QVBoxLayout()
        body.addLayout(left, 3)
        g1 = QGroupBox("Guest")
        gl = QHBoxLayout(g1)
        self.guest_label = label("No guest chosen", "h2")
        gl.addWidget(self.guest_label, 1)
        gl.addWidget(button("Find / new…", self._choose_guest))
        self.btn_edit_guest = button("Edit profile", self._edit_guest)
        gl.addWidget(self.btn_edit_guest)
        left.addWidget(g1)

        g2 = QGroupBox("Stay")
        grid = QGridLayout(g2)
        self.ci, self.co = date_edit(), date_edit()
        self.nights = QSpinBox()
        self.nights.setRange(1, 365)
        self.rtype, self.plan, self.room = QComboBox(), QComboBox(), QComboBox()
        for t in self.types:
            self.rtype.addItem(f"{t.name} ({t.code})", t.id)
        for p in self.plans:
            self.plan.addItem(p.name, p.id)
        self.adults, self.children = QSpinBox(), QSpinBox()
        self.adults.setRange(1, 20)
        self.adults.setValue(2)
        self.children.setRange(0, 20)
        self.avail = label("", "muted")
        rows = [("Arrival", self.ci), ("Departure", self.co), ("Nights", self.nights), ("Room type", self.rtype),
                ("Rate plan", self.plan), ("Room", self.room), ("Adults", self.adults), ("Children", self.children)]
        for i, (text, w) in enumerate(rows):
            grid.addWidget(label(text), i // 2, (i % 2) * 2)
            grid.addWidget(w, i // 2, (i % 2) * 2 + 1)
        grid.addWidget(self.avail, 4, 0, 1, 4)
        left.addWidget(g2)

        g3 = QGroupBox("Booking details")
        form = QFormLayout(g3)
        self.status = QComboBox()
        self.status.addItem("Tentative (not guaranteed)", "tentative")
        self.status.addItem("Confirmed", "confirmed")
        self.source = QComboBox()
        self.source.setEditable(True)
        self.source.addItems(list(SOURCES))
        self.ext_ref = QLineEdit()
        self.ext_ref.setPlaceholderText("Booking.com / agent reference")
        self.arrival_time = QLineEdit()
        self.arrival_time.setPlaceholderText("HH:MM")
        self.arrival_time.setInputMask("99:99;_")
        self.override_on = QCheckBox("Manual nightly rate")
        self.override = QDoubleSpinBox()
        self.override.setRange(0, 1_000_000)
        self.override.setDecimals(2)
        self.override.setEnabled(False)
        can_override = state.can("override_rate")
        self.override_on.setEnabled(can_override)
        if not can_override:
            self.override_on.setToolTip("Only managers can set a manual rate.")
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(70)
        form.addRow("Status", self.status)
        form.addRow("Source", self.source)
        form.addRow("External ref.", self.ext_ref)
        form.addRow("Arrival time", self.arrival_time)
        form.addRow(self.override_on, self.override)
        form.addRow("Notes", self.notes)
        left.addWidget(g3)

        right = QVBoxLayout()
        body.addLayout(right, 2)
        g4 = QGroupBox(f"Price ({state.base_currency})")
        ql = QVBoxLayout(g4)
        self.quote_table = make_table(["Night", "Season", "Rate"], stretch=1)
        self.quote_table.setSortingEnabled(False)
        ql.addWidget(self.quote_table)
        self.quote_taxes = label("")
        self.quote_total = label("", "h2")
        self.quote_warn = label("", "error")
        self.quote_warn.setWordWrap(True)
        ql.addWidget(self.quote_taxes)
        ql.addWidget(self.quote_total)
        ql.addWidget(self.quote_warn)
        right.addWidget(g4)

        self.btn_bill = button("Bill…", lambda: self._action("bill"))
        self.btn_checkin = button("Check in", lambda: self._action("check_in"))
        self.btn_checkout = button("Check out", lambda: self._action("check_out"))
        self.btn_cancel = button("Cancel booking…", lambda: self._action("cancel"), "danger")
        self.btn_reinstate = button("Reinstate", lambda: self._action("reinstate"))
        self.btn_confirm = button("Confirmation", lambda: self._action("confirmation"))
        self.btn_regcard = button("Registration card", lambda: self._action("regcard"))
        self.btn_save = button("Save", self.save, "primary")
        self.btn_save.setDefault(True)
        outer.addLayout(hbox(self.btn_bill, self.btn_checkin, self.btn_checkout, self.btn_cancel,
                             self.btn_reinstate, self.btn_confirm, self.btn_regcard, "stretch",
                             button("Close", self.reject), self.btn_save))

        self.refresh_timer = QTimer(self, singleShot=True, interval=350)
        self.refresh_timer.timeout.connect(self._refresh_rooms)
        self.ci.dateChanged.connect(self._dates_changed)
        self.co.dateChanged.connect(self._co_changed)
        self.nights.valueChanged.connect(self._nights_changed)
        self.rtype.currentIndexChanged.connect(self._type_changed)
        self.plan.currentIndexChanged.connect(self._update_quote)
        self.override_on.toggled.connect(lambda on: (self.override.setEnabled(on), self._update_quote()))
        self.override.valueChanged.connect(self._update_quote)
        self._update_buttons()

    # ------------------------------------------------------------ filling
    def _fill_from(self, r):
        self.title.setText(f"Reservation {r.code}")
        self._set_guest(r.guest)
        self.ci.setDate(to_qdate(r.check_in))
        self.co.setDate(to_qdate(r.check_out))
        self.rtype.setCurrentIndex(max(0, self.rtype.findData(r.room_type_id)))
        self.plan.setCurrentIndex(max(0, self.plan.findData(r.rate_plan_id)))
        self.adults.setValue(r.adults)
        self.children.setValue(r.children)
        idx = self.status.findData(r.status)
        if idx >= 0:
            self.status.setCurrentIndex(idx)
        else:
            self.status.addItem(STATUS_LABELS[r.status], r.status)
            self.status.setCurrentIndex(self.status.count() - 1)
            self.status.setEnabled(False)
        self.source.setCurrentText(r.source or "")
        self.ext_ref.setText(r.external_ref or "")
        self.arrival_time.setText(r.arrival_time or "")
        if r.nightly_rate_override is not None:
            self.override_on.setChecked(True)
            self.override.setValue(float(r.nightly_rate_override))
        self.notes.setPlainText(r.notes or "")
        self._preselect_room = r.room_id
        color = STATUS_COLORS.get(r.status, "#999")
        self.title.setText(f"Reservation {r.code}  <span style='font-size:14px; color:white; background:{color};'>"
                           f"&nbsp;{STATUS_LABELS.get(r.status)}&nbsp;</span>")
        self.title.setTextFormat(Qt.RichText)
        locked = r.status in ("checked_out", "cancelled", "no_show")
        for w in (self.ci, self.co, self.nights, self.rtype, self.plan, self.room, self.adults, self.children,
                  self.source, self.ext_ref, self.arrival_time, self.override_on, self.override, self.notes):
            w.setEnabled(not locked and w.isEnabled())
        if r.status == "checked_in":
            self.ci.setEnabled(False)
            self.room.setEnabled(False)
            self.rtype.setEnabled(False)
        self.btn_save.setEnabled(not locked)

    def _set_guest(self, g):
        self.guest_id = g.id
        flags = (" ★ VIP" if g.vip else "") + (" ⛔ DO NOT BOOK" if g.blacklisted else "")
        self.guest_label.setText(f"{g.full_name}{flags}")
        self.guest_label.setToolTip(f"{g.email or ''}  {g.phone or ''}")

    def _update_buttons(self):
        st = self.res.status if self.res else None
        self.btn_bill.setVisible(bool(self.res) and state.can("billing"))
        self.btn_checkin.setVisible(st in ("tentative", "confirmed") and state.can("front_desk"))
        self.btn_checkout.setVisible(st == "checked_in" and state.can("front_desk"))
        self.btn_cancel.setVisible(st in ("tentative", "confirmed"))
        self.btn_reinstate.setVisible(st in ("cancelled", "no_show"))
        self.btn_confirm.setVisible(bool(self.res))
        self.btn_regcard.setVisible(bool(self.res))
        self.btn_edit_guest.setEnabled(bool(self.guest_id))

    # ------------------------------------------------------------ events
    def _dates_changed(self):
        if self._loading:
            return
        ci = from_qdate(self.ci.date())
        self._loading = True
        self.co.setMinimumDate(to_qdate(ci + dt.timedelta(days=1)))
        self.co.setDate(to_qdate(ci + dt.timedelta(days=self.nights.value())))
        self._loading = False
        self._changed()

    def _co_changed(self):
        if self._loading:
            return
        n = (from_qdate(self.co.date()) - from_qdate(self.ci.date())).days
        self._loading = True
        self.nights.setValue(max(1, n))
        self._loading = False
        self._changed()

    def _nights_changed(self):
        if self._loading:
            return
        self._loading = True
        self.co.setDate(to_qdate(from_qdate(self.ci.date()) + dt.timedelta(days=self.nights.value())))
        self._loading = False
        self._changed()

    def _type_changed(self):
        if not self._loading:
            self._preselect_room = None
            self._changed()

    def _changed(self):
        self._update_quote()
        self.refresh_timer.start()

    def _refresh_rooms(self):
        ci, co = from_qdate(self.ci.date()), from_qdate(self.co.date())
        if co <= ci:
            return
        tid = self.rtype.currentData()
        exclude = self.res_id
        data = call(self, lambda s: (R.available_rooms(s, ci, co, tid, exclude), R.type_availability(s, ci, co, exclude)))
        if data is FAILED:
            return
        rooms, avail = data
        keep = self._preselect_room if getattr(self, "_preselect_room", None) else self.room.currentData()
        self.room.blockSignals(True)
        self.room.clear()
        self.room.addItem("— assign later —", None)
        for r in rooms:
            tag = {"dirty": " (dirty)", "inspected": " ✓", "clean": ""}.get(r.status, "")
            self.room.addItem(f"{r.number}{tag}" + (f" · {r.building}" if r.building else ""), r.id)
        if keep and self.room.findData(keep) < 0 and self.res and self.res.room_id == keep and self.res.room:
            self.room.addItem(f"{self.res.room.number} (current)", keep)
        self.room.setCurrentIndex(max(0, self.room.findData(keep)) if keep else 0)
        self.room.blockSignals(False)
        self._preselect_room = None
        n = avail.get(tid, 0)
        colour = "#c0392b" if n <= 0 else ("#d98e04" if n <= 2 else "#2f8f38")
        self.avail.setText(f"<span style='color:{colour}'>{max(n, 0)} room(s) of this type still free for every night"
                           f"{' — fully booked' if n <= 0 else ''}</span> · {len(rooms)} specific room(s) free")

    def _update_quote(self):
        ci, co = from_qdate(self.ci.date()), from_qdate(self.co.date())
        if co <= ci or self.rtype.currentData() is None or self.plan.currentData() is None:
            return
        ov = Decimal(str(round(self.override.value(), 2))) if self.override_on.isChecked() else None
        q = self.book.quote(self.rtype.currentData(), self.plan.currentData(), ci, co, ov)
        fill_table(self.quote_table, [[n.date.strftime("%a %d %b"), n.season or "Base rate", n.amount] for n in q.nights])
        self.quote_taxes.setText("<br/>".join(f"{t.name}: {fmt_money(t.amount)}" for t in q.taxes)
                                 + f"<br/>Rooms: {fmt_money(q.room_total)} · Average {fmt_money(q.average_rate)}/night")
        self.quote_total.setText(f"Total {state.base_currency} {fmt_money(q.total)}")
        rt = next((t for t in self.types if t.id == self.rtype.currentData()), None)
        warns = list(q.warnings)
        if rt and self.adults.value() + self.children.value() > rt.max_occupancy:
            warns.append(f"{rt.name} sleeps at most {rt.max_occupancy}.")
        self.quote_warn.setText(" ".join(warns))

    def _choose_guest(self):
        gid = pick_guest(self)
        if gid:
            g = call(self, lambda s: s.get(catalog.Guest, gid))
            if g is not FAILED and g:
                self._set_guest(g)
                self._update_buttons()

    def _edit_guest(self):
        if self.guest_id and edit_guest(self, self.guest_id):
            g = call(self, lambda s: s.get(catalog.Guest, self.guest_id))
            if g is not FAILED and g:
                self._set_guest(g)

    # ------------------------------------------------------------ save & actions
    def _input(self) -> R.ReservationInput | None:
        if not self.guest_id:
            warn(self, "Choose a guest first.")
            return None
        t = self.arrival_time.text()
        t = t if t and t.replace(":", "").strip("_").isdigit() and len(t.replace("_", "")) == 5 else None
        return R.ReservationInput(
            guest_id=self.guest_id, room_type_id=self.rtype.currentData(), rate_plan_id=self.plan.currentData(),
            check_in=from_qdate(self.ci.date()), check_out=from_qdate(self.co.date()),
            room_id=self.room.currentData(), adults=self.adults.value(), children=self.children.value(),
            status=self.status.currentData(), source=self.source.currentText().strip() or None,
            external_ref=self.ext_ref.text().strip() or None,
            nightly_rate_override=Decimal(str(round(self.override.value(), 2))) if self.override_on.isChecked() else None,
            arrival_time=t, notes=self.notes.toPlainText().strip() or None)

    def _do_save(self) -> bool:
        data = self._input()
        if data is None:
            return False
        if self.res_id:
            res = call(self, R.update, state.actor, self.res_id, data)
        else:
            res = call(self, R.create, state.actor, data)
        if res is FAILED:
            return False
        self.res, self.res_id, self.saved = res, res.id, True
        state.changed()
        return True

    def save(self):
        new = not self.res_id
        if self._do_save():
            if new:
                info(self, f"Reservation {self.res.code} saved for {self.res.guest.full_name}.", "Saved")
            self.accept()

    def _action(self, what: str):
        if self.btn_save.isEnabled() and what not in ("confirmation", "regcard", "bill", "reinstate"):
            if not self._do_save():
                return
        rid = self.res_id
        if what == "bill":
            open_folio(self, rid)
            return
        if what == "confirmation":
            def build(s):
                r = R.get(s, rid)
                q = RateBook(s).quote(r.room_type_id, r.rate_plan_id, r.check_in, r.check_out, r.nightly_rate_override)
                return printing.confirmation_html(s, r, q)
            doc = call(self, build)
            if doc is not FAILED:
                printing.show(self, "Booking confirmation", doc, f"Confirmation {self.res.code}.pdf")
            return
        if what == "regcard":
            doc = call(self, lambda s: printing.registration_card_html(s, R.get(s, rid)))
            if doc is not FAILED:
                printing.show(self, "Registration card", doc, f"Registration {self.res.code}.pdf")
            return
        if what == "check_in":
            res = call(self, frontdesk.check_in, state.actor, rid)
        elif what == "check_out":
            res = call(self, frontdesk.check_out, state.actor, rid)
            if res is FAILED:
                bal = call(self, folio_svc.balance, rid)
                if bal is not FAILED and bal != 0 and ask(self, "Open the bill?", "Open the bill to settle the balance?"):
                    open_folio(self, rid)
                return
        elif what == "cancel":
            reason, okd = QInputDialog.getText(self, "Cancel reservation", "Reason for cancelling:")
            if not okd:
                return
            res = call(self, R.cancel, state.actor, rid, reason)
        elif what == "reinstate":
            res = call(self, R.reinstate, state.actor, rid)
        else:
            return
        if res is not FAILED:
            state.changed()
            self.saved = True
            self.accept()


def open_reservation(parent, res_id: int | None = None, **kw) -> bool:
    dlg = ReservationDialog(parent, res_id, **kw)
    if not hasattr(dlg, "ci"):
        return False
    dlg.exec()
    return dlg.saved
