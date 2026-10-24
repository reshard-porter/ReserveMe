"""Main window: top bar, sidebar of modules, pages."""
from __future__ import annotations

import time

from PySide6.QtCore import QEvent, QObject, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QListWidget, QListWidgetItem, QMainWindow,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import __version__, config
from ..security import IDLE_LOCK_MINUTES, ROLE_LABELS
from .common import button, label, state
from .dialogs.login import ChangePasswordDialog, LockDialog
from .pages.dashboard import DashboardPage
from .pages.management import NightAuditPage, ReportsPage
from .pages.operations import BillingPage, FrontDeskPage, GuestsPage, HousekeepingPage, ReservationsPage
from .pages.settings import SettingsPage
from .pages.tapechart import TapeChartPage

PAGES = [DashboardPage, TapeChartPage, ReservationsPage, FrontDeskPage, GuestsPage, HousekeepingPage,
         BillingPage, ReportsPage, NightAuditPage, SettingsPage]
ICONS = {"Overview": "◷", "Tape chart": "▦", "Reservations": "☰", "Front desk": "⌂", "Guests": "☺",
         "Housekeeping": "✦", "Billing": "＄", "Reports": "▤", "Night audit": "☾", "Settings": "⚙"}
AUTO_REFRESH_SECONDS = 90


class IdleWatcher(QObject):
    def __init__(self):
        super().__init__()
        self.last = time.monotonic()

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.MouseButtonPress, QEvent.KeyPress, QEvent.Wheel, QEvent.MouseMove):
            self.last = time.monotonic()
        return False


class MainWindow(QMainWindow):
    closed = Signal()

    def __init__(self):
        super().__init__()
        self.signed_out = False
        self.setWindowTitle(f"ReserveMe – {state.property_name}")
        self.setMinimumSize(1180, 700)
        self.resize(1440, 880)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        top = QWidget()
        top.setObjectName("topbar")
        top.setFixedHeight(54)
        tl = QHBoxLayout(top)
        tl.setContentsMargins(18, 0, 14, 0)
        self.brand = label(state.property_name or "ReserveMe", "brand")
        self.bdate = label("")
        self.user = label(f"{state.actor.full_name} · {ROLE_LABELS.get(state.actor.role, state.actor.role)}")
        tl.addWidget(self.brand)
        tl.addSpacing(20)
        tl.addWidget(self.bdate)
        tl.addStretch(1)
        tl.addWidget(self.user)
        tl.addSpacing(10)
        tl.addWidget(button("Password", self.change_password))
        tl.addWidget(button("Lock", self.lock))
        tl.addWidget(button("Sign out", self.sign_out))
        root.addWidget(top)

        body = QHBoxLayout()
        body.setSpacing(0)
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(200)
        self.stack = QStackedWidget()
        self.pages = []
        for cls in PAGES:
            if not state.can(cls.permission):
                continue
            page = cls()
            self.pages.append(page)
            self.stack.addWidget(page)
            it = QListWidgetItem(f"{ICONS.get(cls.title, '•')}   {cls.title}")
            self.sidebar.addItem(it)
        body.addWidget(self.sidebar)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)
        self.setCentralWidget(central)
        self.sidebar.currentRowChanged.connect(self._switch)
        self.statusBar().showMessage(f"Connected to {config.load().describe()} · version {__version__}")

        self.dirty = set()
        state.listeners.append(self._data_changed)
        self._shortcuts()
        self.refresh_timer = QTimer(self, interval=AUTO_REFRESH_SECONDS * 1000)
        self.refresh_timer.timeout.connect(self._auto_refresh)
        self.refresh_timer.start()
        self.idle = IdleWatcher()
        QApplication.instance().installEventFilter(self.idle)
        self.idle_timer = QTimer(self, interval=15_000)
        self.idle_timer.timeout.connect(self._check_idle)
        self.idle_timer.start()
        self._update_header()
        self.sidebar.setCurrentRow(0)

    # ------------------------------------------------------------ navigation
    def _shortcuts(self):
        def add(seq, fn, text):
            a = QAction(text, self)
            a.setShortcut(QKeySequence(seq))
            a.triggered.connect(fn)
            self.addAction(a)
        add(QKeySequence.Refresh, self.refresh_current, "Refresh")
        add("Ctrl+R", self.refresh_current, "Refresh")
        add(QKeySequence.New, self.new_reservation, "New reservation")
        add(QKeySequence.Find, self.find_reservation, "Find reservation")
        add("Ctrl+L", self.lock, "Lock")
        for i in range(min(9, len(self.pages))):
            add(f"Ctrl+{i + 1}", lambda i=i: self.sidebar.setCurrentRow(i), f"Page {i + 1}")

    def _page_index(self, cls):
        for i, p in enumerate(self.pages):
            if isinstance(p, cls):
                return i
        return None

    def new_reservation(self):
        if state.can("reservations"):
            from .dialogs.reservation import open_reservation
            open_reservation(self)

    def find_reservation(self):
        i = self._page_index(ReservationsPage)
        if i is not None:
            self.sidebar.setCurrentRow(i)
            self.pages[i].focus_search()

    def _switch(self, row):
        if row < 0:
            return
        self.stack.setCurrentIndex(row)
        page = self.pages[row]
        page.refresh()
        self.dirty.discard(page)

    def refresh_current(self):
        page = self.stack.currentWidget()
        if page:
            page.refresh()
            self.dirty.discard(page)
        self._update_header()

    def _data_changed(self):
        self.dirty = set(self.pages)
        QTimer.singleShot(0, self.refresh_current)

    def _auto_refresh(self):
        if QApplication.activeModalWidget() is None and self.isActiveWindow():
            try:
                state.reload()
            except Exception:  # connection hiccup: keep the window usable
                self.statusBar().showMessage("Connection lost – retrying…")
                return
            self.statusBar().showMessage(f"Connected to {config.load().describe()} · updated "
                                         f"{time.strftime('%H:%M')}")
            self.refresh_current()

    def _update_header(self):
        self.brand.setText(state.property_name or "ReserveMe")
        self.bdate.setText(f"Business date: {state.business_date:%a %d %b %Y}")

    # ------------------------------------------------------------ session
    def _check_idle(self):
        if time.monotonic() - self.idle.last > IDLE_LOCK_MINUTES * 60 and not getattr(self, "_locked", False):
            self.lock()

    def lock(self):
        self._locked = True
        dlg = LockDialog(state.actor, self)
        dlg.exec()
        self._locked = False
        self.idle.last = time.monotonic()
        if dlg.sign_out:
            self.sign_out()

    def change_password(self):
        ChangePasswordDialog(state.actor, parent=self).exec()

    def sign_out(self):
        self.signed_out = True
        self.close()

    def closeEvent(self, e):
        if self._data_changed in state.listeners:
            state.listeners.remove(self._data_changed)
        QApplication.instance().removeEventFilter(self.idle)
        self.refresh_timer.stop()
        self.idle_timer.stop()
        super().closeEvent(e)
        self.closed.emit()
