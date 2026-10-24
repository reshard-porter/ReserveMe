"""Shared UI helpers: database calls with friendly errors, tables, forms, formatting."""
from __future__ import annotations

import csv
import datetime as dt
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable

from PySide6.QtCore import QDate, Qt, QTime
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                               QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from sqlalchemy.exc import DBAPIError, OperationalError

from .. import db
from ..security import PermissionDenied, can
from ..services.common import Actor, BusinessError, NeedsConfirmation

log = logging.getLogger(__name__)
FAILED = object()


# ------------------------------------------------------------------ app state
@dataclass
class AppState:
    actor: Actor | None = None
    property_name: str = ""
    base_currency: str = "USD"
    alt_currency: str | None = None
    alt_rate: Decimal = Decimal("1")
    business_date: dt.date = field(default_factory=dt.date.today)
    listeners: list[Callable[[], None]] = field(default_factory=list)

    def can(self, perm: str) -> bool:
        return bool(self.actor) and can(self.actor.role, perm)

    def reload(self) -> None:
        from ..services.common import settings
        with db.session() as s:
            st = settings(s)
            self.property_name, self.base_currency = st.name, st.base_currency
            self.alt_currency, self.alt_rate, self.business_date = st.alt_currency, st.alt_rate, st.business_date

    def changed(self) -> None:
        """Tell every page that shared data changed (after a save)."""
        for fn in list(self.listeners):
            try:
                fn()
            except Exception:  # pragma: no cover
                log.exception("listener failed")


state = AppState()


# ------------------------------------------------------------------ db calls
def call(parent: QWidget | None, fn: Callable, *args, confirm_force: bool = True, **kwargs) -> Any:
    """Run ``fn(session, *args, **kwargs)`` in one transaction.

    Shows plain-language messages for rule violations and connection problems.
    If the rules ask for confirmation, asks the user and retries with force=True.
    Returns FAILED when the action did not happen.
    """
    QGuiApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        with db.session() as s:
            return fn(s, *args, **kwargs)
    except NeedsConfirmation as e:
        QGuiApplication.restoreOverrideCursor()
        if confirm_force and ask(parent, "Please confirm", str(e)):
            kwargs["force"] = True
            return call(parent, fn, *args, confirm_force=False, **kwargs)
        return FAILED
    except (BusinessError, PermissionDenied) as e:
        QGuiApplication.restoreOverrideCursor()
        warn(parent, str(e))
        return FAILED
    except (OperationalError, DBAPIError) as e:
        QGuiApplication.restoreOverrideCursor()
        log.exception("Database error")
        if getattr(e, "connection_invalidated", False) or isinstance(e, OperationalError):
            warn(parent, "The database cannot be reached right now. Check the internet connection "
                         "and try again.\n\nDetails: " + str(e.orig).splitlines()[0][:300], title="Connection problem")
        else:
            warn(parent, "The database refused the change:\n" + str(e.orig).splitlines()[0][:400])
        return FAILED
    except Exception as e:  # pragma: no cover - unexpected
        QGuiApplication.restoreOverrideCursor()
        log.exception("Unexpected error")
        QMessageBox.critical(parent, "Something went wrong",
                             f"An unexpected error occurred and was written to the log.\n\n{e}")
        return FAILED
    finally:
        while QGuiApplication.overrideCursor() is not None:
            QGuiApplication.restoreOverrideCursor()


def ok(result: Any) -> bool:
    return result is not FAILED


def warn(parent, text: str, title: str = "Can't do that") -> None:
    QMessageBox.warning(parent, title, text)


def info(parent, text: str, title: str = "Done") -> None:
    QMessageBox.information(parent, title, text)


def ask(parent, title: str, text: str) -> bool:
    return QMessageBox.question(parent, title, text, QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) == QMessageBox.Yes


# ------------------------------------------------------------------ formatting
def fmt_money(v: Any, cur: str | None = None) -> str:
    if v is None:
        return ""
    s = f"{Decimal(v):,.2f}"
    return f"{cur} {s}" if cur else s


def fmt_date(d: dt.date | None) -> str:
    return d.strftime("%d %b %Y") if d else ""


def fmt_dt(d: dt.datetime | None) -> str:
    """Stored timestamps are UTC; show them in the computer's local time."""
    if not d:
        return ""
    return d.replace(tzinfo=dt.timezone.utc).astimezone().strftime("%d %b %Y %H:%M")


def to_qdate(d: dt.date) -> QDate:
    return QDate(d.year, d.month, d.day)


def from_qdate(q: QDate) -> dt.date:
    return dt.date(q.year(), q.month(), q.day())


def date_edit(d: dt.date | None = None) -> QDateEdit:
    w = QDateEdit()
    w.setCalendarPopup(True)
    w.setDisplayFormat("dd MMM yyyy")
    w.setDate(to_qdate(d or state.business_date))
    return w


# ------------------------------------------------------------------ widgets
def label(text: str, name: str | None = None) -> QLabel:
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    return lb


def button(text: str, slot: Callable | None = None, kind: str | None = None, tip: str | None = None) -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setObjectName(kind)
    if slot:
        b.clicked.connect(slot)
    if tip:
        b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    return b


def hbox(*widgets, stretch_at: int | None = None, margins=(0, 0, 0, 0)) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setContentsMargins(*margins)
    for i, w in enumerate(widgets):
        if w == "stretch":
            lay.addStretch(1)
        elif isinstance(w, QWidget):
            lay.addWidget(w)
        else:
            lay.addLayout(w)
    return lay


class Page(QWidget):
    """Base for the main sidebar pages."""
    title = ""
    permission = "dashboard"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(24, 18, 24, 18)
        self.outer.setSpacing(12)
        self.header = QHBoxLayout()
        self.header.addWidget(label(self.title, "h1"))
        self.header.addStretch(1)
        self.outer.addLayout(self.header)

    def refresh(self) -> None:  # pragma: no cover - overridden
        pass


def card(title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(16, 12, 16, 12)
    if title:
        lay.addWidget(label(title, "h2"))
    return f, lay


def make_table(headers: list[str], stretch: int | None = None) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setAlternatingRowColors(True)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(30)
    h = t.horizontalHeader()
    h.setSectionResizeMode(QHeaderView.Interactive)
    h.setStretchLastSection(stretch is None)
    if stretch is not None:
        h.setSectionResizeMode(stretch, QHeaderView.Stretch)
    t.setSortingEnabled(True)
    h.setSortIndicator(-1, Qt.AscendingOrder)  # keep the order rows were loaded in until a header is clicked
    return t


class NumItem(QTableWidgetItem):
    """Sorts by number, displays formatted text."""
    def __init__(self, value, text: str | None = None):
        super().__init__(text if text is not None else fmt_money(value))
        self.value = float(value or 0)
        self.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def __lt__(self, other):
        return self.value < getattr(other, "value", 0)


class DateItem(QTableWidgetItem):
    def __init__(self, d):
        super().__init__(fmt_date(d) if isinstance(d, dt.date) and not isinstance(d, dt.datetime) else fmt_dt(d))
        self.key = d.isoformat() if d else ""

    def __lt__(self, other):
        return self.key < getattr(other, "key", "")


def fill_table(t: QTableWidget, rows: list[list[Any]], ids: list[Any] | None = None,
               colors: list[str | None] | None = None) -> None:
    sortable = t.isSortingEnabled()
    t.setSortingEnabled(False)
    t.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            if isinstance(v, QTableWidgetItem):
                item = v
            elif isinstance(v, (Decimal, float)) :
                item = NumItem(v)
            elif isinstance(v, int) and not isinstance(v, bool):
                item = NumItem(v, str(v))
            elif isinstance(v, (dt.date, dt.datetime)):
                item = DateItem(v)
            else:
                item = QTableWidgetItem("" if v is None else str(v))
            if c == 0 and ids is not None:
                item.setData(Qt.UserRole, ids[r])
            if colors and colors[r]:
                item.setBackground(QColor(colors[r]))
            t.setItem(r, c, item)
    t.setSortingEnabled(sortable)
    t.resizeColumnsToContents()
    for c in range(t.columnCount()):
        if t.columnWidth(c) > 320:
            t.setColumnWidth(c, 320)


def selected_id(t: QTableWidget) -> Any:
    rows = t.selectionModel().selectedRows()
    if not rows:
        return None
    item = t.item(rows[0].row(), 0)
    return item.data(Qt.UserRole) if item else None


def export_table(parent: QWidget, t: QTableWidget, default_name: str) -> None:
    path, _ = QFileDialog.getSaveFileName(parent, "Export", default_name,
                                          "Excel workbook (*.xlsx);;CSV file (*.csv)")
    if not path:
        return
    headers = [t.horizontalHeaderItem(c).text() for c in range(t.columnCount())]
    rows = []
    for r in range(t.rowCount()):
        row = []
        for c in range(t.columnCount()):
            it = t.item(r, c)
            if it is None:
                row.append("")
            elif isinstance(it, NumItem):
                row.append(it.value)
            else:
                row.append(it.text())
        rows.append(row)
    try:
        if path.lower().endswith(".csv"):
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(headers)
                w.writerows(rows)
        else:
            from openpyxl import Workbook
            from openpyxl.styles import Font
            wb = Workbook()
            ws = wb.active
            ws.title = default_name[:30].rsplit(".", 1)[0] or "Report"
            ws.append(headers)
            for cell in ws[1]:
                cell.font = Font(bold=True)
            for row in rows:
                ws.append(row)
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(
                    45, max(10, *(len(str(c.value or "")) + 2 for c in col)))
            if not path.lower().endswith(".xlsx"):
                path += ".xlsx"
            wb.save(path)
        info(parent, f"Saved to {path}")
    except OSError as e:
        warn(parent, f"Could not save the file: {e}")


# ------------------------------------------------------------------ generic form dialog
@dataclass
class F:
    key: str
    label: str
    kind: str = "text"  # text|password|int|money|decimal|bool|choice|date|multiline|time
    default: Any = None
    choices: list[tuple[str, Any]] | None = None
    required: bool = False
    minimum: float = 0
    maximum: float = 1_000_000_000
    help: str | None = None


class FormDialog(QDialog):
    def __init__(self, parent, title: str, fields: list[F], values: dict | None = None,
                 on_save: Callable[[dict], Any] | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        self.fields, self.widgets, self.on_save, self.result_value = fields, {}, on_save, None
        values = values or {}
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        for f in fields:
            v = values.get(f.key, f.default)
            w = self._widget(f, v)
            self.widgets[f.key] = w
            form.addRow(f.label + (" *" if f.required else ""), w)
            if f.help:
                form.addRow("", label(f.help, "muted"))
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setObjectName("primary")
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _widget(self, f: F, v):
        if f.kind in ("text", "password"):
            w = QLineEdit("" if v is None else str(v))
            if f.kind == "password":
                w.setEchoMode(QLineEdit.Password)
        elif f.kind == "multiline":
            w = QPlainTextEdit("" if v is None else str(v))
            w.setFixedHeight(80)
        elif f.kind == "int":
            w = QSpinBox()
            w.setRange(int(f.minimum), int(min(f.maximum, 2_000_000_000)))
            w.setValue(int(v or 0))
        elif f.kind in ("money", "decimal"):
            w = QDoubleSpinBox()
            w.setDecimals(2 if f.kind == "money" else 4)
            w.setRange(f.minimum, f.maximum)
            w.setGroupSeparatorShown(True)
            w.setValue(float(v or 0))
        elif f.kind == "bool":
            w = QCheckBox()
            w.setChecked(bool(v))
        elif f.kind == "choice":
            w = QComboBox()
            for text, data in f.choices or []:
                w.addItem(text, data)
            idx = w.findData(v)
            if idx >= 0:
                w.setCurrentIndex(idx)
        elif f.kind == "date":
            w = date_edit(v)
        elif f.kind == "time":
            from PySide6.QtWidgets import QTimeEdit
            w = QTimeEdit()
            w.setDisplayFormat("HH:mm")
            if v:
                h, m = str(v).split(":")[:2]
                w.setTime(QTime(int(h), int(m)))
        else:
            raise ValueError(f.kind)
        return w

    def values(self) -> dict:
        out = {}
        for f in self.fields:
            w = self.widgets[f.key]
            if f.kind in ("text", "password"):
                out[f.key] = w.text().strip() if f.kind == "text" else w.text()
            elif f.kind == "multiline":
                out[f.key] = w.toPlainText().strip()
            elif f.kind == "int":
                out[f.key] = w.value()
            elif f.kind in ("money", "decimal"):
                out[f.key] = Decimal(str(round(w.value(), 4)))
            elif f.kind == "bool":
                out[f.key] = w.isChecked()
            elif f.kind == "choice":
                out[f.key] = w.currentData()
            elif f.kind == "date":
                out[f.key] = from_qdate(w.date())
            elif f.kind == "time":
                out[f.key] = w.time().toString("HH:mm")
        return out

    def _accept(self):
        vals = self.values()
        for f in self.fields:
            if f.required and vals.get(f.key) in ("", None):
                warn(self, f"“{f.label}” is required.")
                self.widgets[f.key].setFocus()
                return
        if self.on_save:
            res = self.on_save(vals)
            if not ok(res):
                return
            self.result_value = res
        self.accept()
