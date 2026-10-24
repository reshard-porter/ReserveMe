"""Guest profile editor and picker."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QLineEdit, QVBoxLayout

from ...services import catalog
from ..common import (F, FAILED, FormDialog, ask, button, call, fill_table, hbox, label, make_table,
                      selected_id, state)

ID_TYPES = [("", None), ("Passport", "Passport"), ("Driver's licence", "Driver's licence"),
            ("National ID", "National ID"), ("Other", "Other")]


def guest_fields() -> list[F]:
    fields = [
        F("first_name", "First name", required=True), F("last_name", "Last name", required=True),
        F("email", "Email"), F("phone", "Phone"), F("company", "Company"), F("nationality", "Nationality"),
        F("id_type", "ID type", "choice", choices=ID_TYPES), F("id_number", "ID / passport number"),
        F("date_of_birth", "Date of birth (optional)", "text", help="Format: YYYY-MM-DD"),
        F("address", "Address", "multiline"), F("vip", "VIP", "bool"),
    ]
    if state.can("settings"):
        fields.append(F("blacklisted", "Do not book", "bool"))
    fields.append(F("notes", "Notes / preferences", "multiline"))
    return fields


def edit_guest(parent, guest_id: int | None = None, prefill: dict | None = None) -> int | None:
    import datetime as dt
    values = dict(prefill or {})
    if guest_id:
        g = call(parent, lambda s: s.get(catalog.Guest, guest_id))
        if g is FAILED or g is None:
            return None
        values = {k: getattr(g, k) for k in catalog.GUEST_FIELDS}
        values["date_of_birth"] = g.date_of_birth.isoformat() if g.date_of_birth else ""

    def save(v: dict):
        dob = v.get("date_of_birth") or None
        if dob:
            try:
                v["date_of_birth"] = dt.date.fromisoformat(dob)
            except ValueError:
                from ..common import warn
                warn(parent, "Date of birth must look like 1985-04-30.")
                return FAILED
        else:
            v["date_of_birth"] = None
        if not guest_id:
            dups = call(parent, catalog.possible_duplicates, v["first_name"], v["last_name"], v["email"], v["phone"])
            if dups and dups is not FAILED:
                names = "\n".join(f"• {d.full_name} – {d.email or ''} {d.phone or ''}" for d in dups)
                if not ask(parent, "Possible duplicate",
                           f"These guests look similar:\n{names}\n\nCreate a new profile anyway?"):
                    return FAILED
        res = call(parent, catalog.save_guest, state.actor, guest_id, **v)
        return res.id if res is not FAILED else FAILED

    dlg = FormDialog(parent, "Edit guest" if guest_id else "New guest", guest_fields(), values, save)
    if dlg.exec():
        state.changed()
        return dlg.result_value
    return None


class GuestPicker(QDialog):
    def __init__(self, parent=None, initial: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Choose guest")
        self.resize(760, 480)
        self.guest_id = None
        lay = QVBoxLayout(self)
        self.search = QLineEdit(initial)
        self.search.setPlaceholderText("Search by name, email, phone, company or ID number…")
        self.table = make_table(["Name", "Email", "Phone", "Nationality", "Company", "VIP"], stretch=1)
        self.table.doubleClicked.connect(self._choose)
        lay.addWidget(self.search)
        lay.addWidget(self.table)
        lay.addWidget(label("Tip: double-click a guest to choose them.", "muted"))
        lay.addLayout(hbox(button("New guest…", self._new), "stretch", button("Cancel", self.reject),
                           button("Choose", self._choose, "primary")))
        self.timer = QTimer(self, singleShot=True, interval=300)
        self.timer.timeout.connect(self.load)
        self.search.textChanged.connect(lambda: self.timer.start())
        self.load()

    def load(self):
        guests = call(self, catalog.search_guests, self.search.text())
        if guests is FAILED:
            return
        fill_table(self.table, [[g.full_name + (" ⛔" if g.blacklisted else ""), g.email, g.phone, g.nationality,
                                 g.company, "★" if g.vip else ""] for g in guests], [g.id for g in guests])

    def _choose(self):
        gid = selected_id(self.table)
        if gid:
            self.guest_id = gid
            self.accept()

    def _new(self):
        parts = self.search.text().strip().split(" ", 1)
        prefill = {"first_name": parts[0], "last_name": parts[1] if len(parts) > 1 else ""} if parts[0] else {}
        gid = edit_guest(self, None, prefill)
        if gid:
            self.guest_id = gid
            self.accept()


def pick_guest(parent, initial: str = "") -> int | None:
    dlg = GuestPicker(parent, initial)
    return dlg.guest_id if dlg.exec() else None
