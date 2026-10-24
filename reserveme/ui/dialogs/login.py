"""Sign-in, lock screen and password change."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QVBoxLayout

from ... import __version__
from ...services import auth
from ..common import FAILED, button, call, hbox, label, ok, state, warn


class LoginDialog(QDialog):
    def __init__(self, parent=None, connection_text: str = ""):
        super().__init__(parent)
        self.setWindowTitle("ReserveMe – Sign in")
        self.setMinimumWidth(400)
        self.actor = None
        self.must_change = False
        self.change_connection = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.addWidget(label(state.property_name or "ReserveMe", "h1"))
        lay.addWidget(label("Sign in to continue", "muted"))
        form = QFormLayout()
        self.username = QLineEdit()
        self.username.setPlaceholderText("Username")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("Password")
        form.addRow("Username", self.username)
        form.addRow("Password", self.password)
        lay.addLayout(form)
        self.error = label("", "error")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        self.sign_in = button("Sign in", self._login, "primary")
        self.sign_in.setDefault(True)
        lay.addLayout(hbox(button("Database…", self._db), "stretch", button("Exit", self.reject), self.sign_in))
        foot = label(f"Version {__version__} · {connection_text}", "muted")
        foot.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(foot)
        self.username.setFocus()

    def _db(self):
        self.change_connection = True
        self.reject()

    def _login(self):
        self.error.setText("")
        u, p = self.username.text().strip(), self.password.text()
        if not u or not p:
            self.error.setText("Enter your username and password.")
            return
        res = call(self, auth.login, u, p)
        if res is FAILED:
            self.password.clear()
            self.password.setFocus()
            return
        self.actor, self.must_change = res
        self.accept()


class ChangePasswordDialog(QDialog):
    def __init__(self, actor, forced: bool = False, parent=None):
        super().__init__(parent)
        self.actor = actor
        self.setWindowTitle("Change password")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        if forced:
            m = label("Please choose your own password before continuing.", "h2")
            m.setWordWrap(True)
            lay.addWidget(m)
        lay.addWidget(label("At least 10 characters, with upper- and lower-case letters and a number.", "muted"))
        form = QFormLayout()
        self.old, self.new, self.again = QLineEdit(), QLineEdit(), QLineEdit()
        for w in (self.old, self.new, self.again):
            w.setEchoMode(QLineEdit.Password)
        form.addRow("Current password", self.old)
        form.addRow("New password", self.new)
        form.addRow("New password again", self.again)
        lay.addLayout(form)
        save = button("Change password", self._save, "primary")
        save.setDefault(True)
        lay.addLayout(hbox("stretch", button("Cancel", self.reject), save))

    def _save(self):
        if self.new.text() != self.again.text():
            warn(self, "The two new passwords do not match.")
            return
        if ok(call(self, auth.change_password, self.actor, self.old.text(), self.new.text())):
            self.accept()


class LockDialog(QDialog):
    """Shown after a period of inactivity; only the signed-in user can unlock."""

    def __init__(self, actor, parent=None):
        super().__init__(parent)
        self.actor = actor
        self.sign_out = False
        self.setWindowTitle("Locked")
        self.setModal(True)
        self.setMinimumWidth(380)
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Screen locked", "h1"))
        lay.addWidget(label(f"Signed in as {actor.full_name}. Enter your password to continue.", "muted"))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        lay.addWidget(self.password)
        self.error = label("", "error")
        lay.addWidget(self.error)
        unlock = button("Unlock", self._unlock, "primary")
        unlock.setDefault(True)
        lay.addLayout(hbox(button("Sign out", self._signout), "stretch", unlock))

    def keyPressEvent(self, e):  # Escape must not dismiss the lock
        if e.key() != Qt.Key_Escape:
            super().keyPressEvent(e)

    def _signout(self):
        self.sign_out = True
        self.accept()

    def _unlock(self):
        res = call(self, auth.verify, self.actor, self.password.text())
        if res is True:
            self.accept()
        else:
            self.password.clear()
            self.error.setText("Wrong password.")
