"""Settings: property, rooms, rates, taxes, users, audit log, connection."""
from __future__ import annotations

import datetime as dt
import json
from typing import Callable

from PySide6.QtWidgets import QFormLayout, QLineEdit, QTabWidget, QVBoxLayout, QWidget

from ... import config
from ...models import ROLES
from ...security import ROLE_LABELS
from ...services import auth, catalog
from ...services.common import settings as get_settings
from ..common import (F, FAILED, FormDialog, Page, button, call, date_edit, export_table, fill_table, fmt_dt,
                      from_qdate, hbox, info, label, make_table, selected_id, state, warn)
from ..dialogs.connection import ConnectionDialog


class CrudTab(QWidget):
    def __init__(self, headers, load: Callable, row: Callable, fields: Callable, save: Callable, title: str,
                 delete: Callable | None = None, note: str = ""):
        super().__init__()
        self.load_fn, self.row_fn, self.fields_fn, self.save_fn, self.title, self.delete_fn = (
            load, row, fields, save, title, delete)
        self.items = {}
        lay = QVBoxLayout(self)
        if note:
            n = label(note, "muted")
            n.setWordWrap(True)
            lay.addWidget(n)
        self.table = make_table(headers, stretch=1)
        self.table.doubleClicked.connect(self.edit)
        lay.addWidget(self.table)
        btns = ["stretch"]
        if delete:
            btns.append(button("Delete", self.delete, "danger"))
        btns += [button("Edit", self.edit), button(f"Add {title.lower()}", self.add, "primary")]
        lay.addLayout(hbox(*btns))

    def refresh(self):
        items = call(self, self.load_fn)
        if items is FAILED:
            return
        self.items = {i.id: i for i in items}
        fill_table(self.table, [self.row_fn(i) for i in items], [i.id for i in items])

    def _open(self, obj):
        fields = call(self, lambda s: self.fields_fn(s))
        if fields is FAILED:
            return
        values = {f.key: getattr(obj, f.key, None) for f in fields} if obj else {}
        dlg = FormDialog(self, f"{'Edit' if obj else 'Add'} {self.title.lower()}", fields, values,
                         lambda v: call(self, self.save_fn, state.actor, obj.id if obj else None, v))
        if dlg.exec():
            self.refresh()
            state.changed()

    def add(self):
        self._open(None)

    def edit(self, *_):
        oid = selected_id(self.table)
        if oid:
            self._open(self.items[oid])

    def delete(self):
        oid = selected_id(self.table)
        if oid and call(self, self.delete_fn, state.actor, oid) is not FAILED:
            self.refresh()


class PropertyTab(QWidget):
    FIELDS = [("name", "Property name"), ("address", "Address"), ("phone", "Phone"), ("email", "Email"),
              ("website", "Website"), ("tax_registration", "Tax registration no."), ("base_currency", "Main currency"),
              ("alt_currency", "Second currency"), ("alt_rate", "Exchange rate (second per main)"),
              ("check_in_time", "Check-in time"), ("check_out_time", "Check-out time"),
              ("invoice_footer", "Footer on bills and confirmations")]

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.edits = {}
        for key, text in self.FIELDS:
            e = QLineEdit()
            self.edits[key] = e
            form.addRow(text, e)
        self.edits["base_currency"].setMaxLength(3)
        self.edits["alt_currency"].setMaxLength(3)
        lay.addLayout(form)
        self.bdate = label("", "muted")
        lay.addWidget(self.bdate)
        lay.addLayout(hbox("stretch", button("Save", self.save, "primary")))
        lay.addStretch(1)

    def refresh(self):
        st = call(self, get_settings)
        if st is FAILED:
            return
        for key, _ in self.FIELDS:
            v = getattr(st, key)
            self.edits[key].setText("" if v is None else str(v))
        self.bdate.setText(f"Business date: {st.business_date:%d %b %Y} (changed only by the night audit). "
                           f"Next reservation no. R{st.next_reservation_no:06d}, next invoice INV-{st.next_invoice_no:06d}.")

    def save(self):
        from decimal import Decimal, InvalidOperation
        v = {k: self.edits[k].text().strip() or None for k, _ in self.FIELDS}
        try:
            v["alt_rate"] = Decimal(v["alt_rate"] or "1")
            if v["alt_rate"] <= 0:
                raise InvalidOperation
        except InvalidOperation:
            warn(self, "The exchange rate must be a number greater than zero.")
            return
        for k in ("check_in_time", "check_out_time"):
            try:
                dt.datetime.strptime(v[k] or "", "%H:%M")
            except ValueError:
                warn(self, "Times must look like 15:00.")
                return
        v["base_currency"] = (v["base_currency"] or "USD").upper()
        v["alt_currency"] = v["alt_currency"].upper() if v["alt_currency"] else None
        v["name"] = v["name"] or ""
        if call(self, catalog.save_settings, state.actor, **v) is not FAILED:
            state.reload()
            state.changed()
            info(self, "Settings saved.")


class AuditTab(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        self.d1, self.d2 = date_edit(dt.date.today() - dt.timedelta(days=7)), date_edit(dt.date.today())
        self.text = QLineEdit()
        self.text.setPlaceholderText("Filter by action, record or detail")
        self.text.returnPressed.connect(self.refresh)
        lay.addLayout(hbox(label("From"), self.d1, label("to"), self.d2, self.text, button("Show", self.refresh)))
        self.table = make_table(["When", "User", "Action", "Record", "ID", "Details"], stretch=5)
        lay.addWidget(self.table)
        lay.addLayout(hbox("stretch", button("Export…", lambda: export_table(self, self.table, "Audit log.xlsx"))))

    def refresh(self):
        rows = call(self, catalog.audit_entries, from_qdate(self.d1.date()), from_qdate(self.d2.date()), self.text.text())
        if rows is FAILED:
            return

        def detail(d):
            try:
                return ", ".join(f"{k}={v}" for k, v in json.loads(d).items()) if d else ""
            except ValueError:
                return d
        fill_table(self.table, [[a.at, a.user.username if a.user else "system", a.action, a.entity, a.entity_id,
                                 detail(a.details)[:300]] for a in rows])


class SettingsPage(Page):
    title = "Settings"
    permission = "settings"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tabs = QTabWidget()
        self.outer.addWidget(self.tabs, 1)
        self.property = PropertyTab()
        self.tabs.addTab(self.property, "Property")

        def type_fields(s):
            return [F("code", "Code", required=True), F("name", "Name", required=True), F("description", "Description", "multiline"),
                    F("base_occupancy", "Base occupancy", "int", 2, minimum=1, maximum=20),
                    F("max_occupancy", "Maximum occupancy", "int", 2, minimum=1, maximum=30),
                    F("base_rate", "Default nightly rate", "money", help="Used when no season covers a date."),
                    F("sort_order", "Order on screen", "int"), F("is_active", "Active (bookable)", "bool", True)]
        self.types = CrudTab(["Code", "Name", "Sleeps", "Default rate", "Active"], catalog.room_types,
                             lambda t: [t.code, t.name, f"{t.base_occupancy}–{t.max_occupancy}", t.base_rate,
                                        "Yes" if t.is_active else "No"],
                             type_fields, lambda s, a, i, v: catalog.save_room_type(s, a, i, **v), "Room type")
        self.tabs.addTab(self.types, "Room types")

        def room_fields(s):
            return [F("number", "Room number", required=True),
                    F("room_type_id", "Room type", "choice", choices=[(t.name, t.id) for t in catalog.room_types(s)]),
                    F("building", "Building"), F("floor", "Floor"), F("is_active", "Active (in inventory)", "bool", True),
                    F("notes", "Notes", "multiline")]
        self.rooms = CrudTab(["Number", "Type", "Building", "Floor", "Status", "Active"], catalog.rooms,
                             lambda r: [r.number, r.room_type.name, r.building, r.floor, r.status.replace("_", " "),
                                        "Yes" if r.is_active else "No"],
                             room_fields, lambda s, a, i, v: catalog.save_room(s, a, i, **v), "Room")
        self.tabs.addTab(self.rooms, "Rooms")

        def plan_fields(s):
            return [F("code", "Code", required=True), F("name", "Name", required=True),
                    F("includes_breakfast", "Includes breakfast", "bool"), F("description", "Description", "multiline"),
                    F("is_active", "Active", "bool", True)]
        self.plans = CrudTab(["Code", "Name", "Breakfast", "Active"], catalog.rate_plans,
                             lambda p: [p.code, p.name, "Yes" if p.includes_breakfast else "No", "Yes" if p.is_active else "No"],
                             plan_fields, lambda s, a, i, v: catalog.save_rate_plan(s, a, i, **v), "Rate plan")
        self.tabs.addTab(self.plans, "Rate plans")

        def rate_fields(s):
            return [F("season_name", "Season name", help="e.g. Peak season 2026/27"),
                    F("rate_plan_id", "Rate plan", "choice", choices=[(p.name, p.id) for p in catalog.rate_plans(s)]),
                    F("room_type_id", "Room type", "choice", choices=[(t.name, t.id) for t in catalog.room_types(s)]),
                    F("start_date", "First night", "date"), F("end_date", "Last night", "date"),
                    F("amount", "Nightly rate", "money", required=True),
                    F("weekend_amount", "Friday & Saturday rate", "money", help="Leave at 0 to use the nightly rate."),
                    F("min_stay", "Minimum stay (nights)", "int", 1, minimum=1, maximum=60)]
        self.rates = CrudTab(["Season", "Plan", "Room type", "From", "To", "Rate", "Weekend", "Min. stay"], catalog.rates,
                             lambda r: [r.season_name or "", r.rate_plan.code, r.room_type.code, r.start_date, r.end_date,
                                        r.amount, r.weekend_amount, r.min_stay],
                             rate_fields, lambda s, a, i, v: catalog.save_rate(s, a, i, **v), "Rate",
                             delete=catalog.delete_rate,
                             note="Each row prices one room type on one rate plan for a range of nights. Where seasons "
                                  "overlap, the one that starts latest wins. Nights with no season use the room "
                                  "type's default rate.")
        self.tabs.addTab(self.rates, "Rates & seasons")

        def tax_fields(s):
            return [F("name", "Name", required=True),
                    F("kind", "Type", "choice", choices=[("Percent of room rate", "percent"),
                                                         ("Fixed amount per room per night", "fixed_per_night")]),
                    F("value", "Value", "decimal", help="Percent (e.g. 10) or amount in the main currency."),
                    F("sort_order", "Order", "int"), F("is_active", "Active", "bool", True)]
        self.taxes = CrudTab(["Name", "Type", "Value", "Active"], catalog.taxes,
                             lambda t: [t.name, "Percent" if t.kind == "percent" else "Per night", f"{t.value:g}",
                                        "Yes" if t.is_active else "No"],
                             tax_fields, lambda s, a, i, v: catalog.save_tax(s, a, i, **v), "Tax",
                             note="Taxes apply to room charges. Changes affect new quotes and future night audits, "
                                  "not charges already posted.")
        self.tabs.addTab(self.taxes, "Taxes")

        self.users = None
        if state.can("users"):
            def user_fields(s):
                return [F("username", "Username", required=True), F("full_name", "Full name", required=True),
                        F("email", "Email"),
                        F("role", "Role", "choice", choices=[(ROLE_LABELS[r], r) for r in ROLES]),
                        F("is_active", "Active", "bool", True),
                        F("new_password", "Set temporary password", "password",
                          help="Leave blank to keep the current password. The user must change it at next sign-in.")]
            self.users = CrudTab(["Username", "Name", "Role", "Active", "Last sign-in"], auth.list_users,
                                 lambda u: [u.username, u.full_name, ROLE_LABELS.get(u.role, u.role),
                                            "Yes" if u.is_active else "No", fmt_dt(u.last_login_at)],
                                 user_fields, lambda s, a, i, v: auth.save_user(
                                     s, a, i, v["username"], v["full_name"], v["email"], v["role"], v["is_active"],
                                     v["new_password"] or None), "User")
            self.tabs.addTab(self.users, "Users")
        self.audit = None
        if state.can("audit_log"):
            self.audit = AuditTab()
            self.tabs.addTab(self.audit, "Audit log")

        conn = QWidget()
        cl = QVBoxLayout(conn)
        self.conn_label = label("")
        self.conn_label.setWordWrap(True)
        cl.addWidget(self.conn_label)
        cl.addWidget(label(f"Settings file: {config.CONFIG_FILE}", "muted"))
        cl.addWidget(label(f"Log files: {config.LOG_DIR}", "muted"))
        cl.addLayout(hbox(button("Change database connection…", self.change_connection), "stretch"))
        cl.addStretch(1)
        self.tabs.addTab(conn, "This computer")
        self.tabs.currentChanged.connect(lambda _: self.refresh())

    def refresh(self):
        w = self.tabs.currentWidget()
        if hasattr(w, "refresh"):
            w.refresh()
        self.conn_label.setText(f"Connected to: {config.load().describe()}")

    def change_connection(self):
        dlg = ConnectionDialog(config.load(), parent=self)
        if dlg.exec():
            info(self, "Connection saved. Close and reopen ReserveMe to use it.")
