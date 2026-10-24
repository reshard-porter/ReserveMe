"""First-run screen: where is the database?"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QSpinBox, QVBoxLayout)

from ... import config, db
from ..common import ask, button, info, label, warn


class ConnectionDialog(QDialog):
    def __init__(self, cfg: config.ConnectionConfig, message: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ReserveMe – Database connection")
        self.setMinimumWidth(520)
        self.cfg = cfg
        lay = QVBoxLayout(self)
        lay.addWidget(label("Connect to your database", "h1"))
        tip = label("Using Filess.io? Open your database there, choose “Connect”, and copy the host, port, "
                    "database name, username and password into the boxes below.", "muted")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        if message:
            m = label(message, "error")
            m.setWordWrap(True)
            m.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lay.addWidget(m)

        form = QFormLayout()
        self.engine = QComboBox()
        for key, (name, _) in config.ENGINES.items():
            self.engine.addItem(name, key)
        self.host = QLineEdit(cfg.host)
        self.host.setPlaceholderText("e.g. abc123.h.filess.io")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(cfg.port or 5432)
        self.database = QLineEdit(cfg.database)
        self.username = QLineEdit(cfg.username)
        self.password = QLineEdit(cfg.password)
        self.password.setEchoMode(QLineEdit.Password)
        self.ssl = QComboBox()
        for text, val in (("Use if available (recommended)", "prefer"), ("Required", "require"), ("Off", "disable")):
            self.ssl.addItem(text, val)
        self.ssl.setCurrentIndex(max(0, self.ssl.findData(cfg.ssl)))
        self.sqlite_path = QLineEdit(cfg.sqlite_path)
        browse = button("Browse…", self._browse)
        self.sqlite_row = QHBoxLayout()
        self.sqlite_row.addWidget(self.sqlite_path)
        self.sqlite_row.addWidget(browse)

        form.addRow("Database type", self.engine)
        form.addRow("Host", self.host)
        form.addRow("Port", self.port)
        form.addRow("Database name", self.database)
        form.addRow("Username", self.username)
        form.addRow("Password", self.password)
        form.addRow("Encryption (SSL)", self.ssl)
        form.addRow("Database file", self.sqlite_row)
        self.form = form
        lay.addLayout(form)

        self.sample = QCheckBox("When creating tables, add sample rooms, rates and guests")
        lay.addWidget(self.sample)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        self.create_btn = button("Create tables", self._create)
        self.create_btn.setToolTip("Set up an empty database: tables, settings and the first admin login.")
        lay.addLayout(self._row(button("Test connection", self._test), self.create_btn, "stretch",
                                button("Cancel", self.reject), button("Save and continue", self._save, "primary")))
        self.engine.currentIndexChanged.connect(self._engine_changed)
        self.engine.setCurrentIndex(max(0, self.engine.findData(cfg.engine)))
        self._engine_changed()

    @staticmethod
    def _row(*items):
        h = QHBoxLayout()
        for w in items:
            h.addStretch(1) if w == "stretch" else h.addWidget(w)
        return h

    def _engine_changed(self):
        key = self.engine.currentData()
        remote = key != "sqlite"
        for w in (self.host, self.port, self.database, self.username, self.password, self.ssl):
            w.setEnabled(remote)
            self.form.labelForField(w).setEnabled(remote)
        self.sqlite_path.setEnabled(not remote)
        default_port = config.ENGINES[key][1]
        if remote and self.port.value() in (5432, 3306, 0, 1):
            self.port.setValue(default_port)

    def _browse(self):
        path, _ = QFileDialog.getSaveFileName(self, "Database file", self.sqlite_path.text() or "reserveme.db",
                                              "Database (*.db)", options=QFileDialog.DontConfirmOverwrite)
        if path:
            self.sqlite_path.setText(path)

    def _read(self) -> config.ConnectionConfig:
        return config.ConnectionConfig(
            engine=self.engine.currentData(), host=self.host.text().strip(), port=self.port.value(),
            database=self.database.text().strip(), username=self.username.text().strip(),
            password=self.password.text(), ssl=self.ssl.currentData(), sqlite_path=self.sqlite_path.text().strip())

    def _try(self, cfg) -> tuple[bool, list[str] | None, str]:
        if not cfg.is_complete():
            return False, None, "Fill in every box first."
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            eng = db.make_engine(cfg)
            with eng.connect():
                pass
            missing = db.missing_tables(eng)
            eng.dispose()
            return True, missing, ""
        except Exception as e:  # noqa: BLE001 - show any driver error to the user
            msg = str(getattr(e, "orig", e)).strip().splitlines()[0][:300]
            return False, None, msg
        finally:
            QGuiApplication.restoreOverrideCursor()

    def _test(self) -> bool:
        good, missing, msg = self._try(self._read())
        if not good:
            self.status.setText(f"<span style='color:#c0392b'>Could not connect: {msg}</span>")
            return False
        if missing:
            self.status.setText(f"<span style='color:#d98e04'>Connected, but {len(missing)} tables are missing. "
                                "Run the SQL scripts from the “sql” folder, or click “Create tables”.</span>")
        else:
            self.status.setText("<span style='color:#2f8f38'>Connected. All tables are present.</span>")
        return True

    def _create(self):
        cfg = self._read()
        good, missing, msg = self._try(cfg)
        if not good:
            warn(self, f"Could not connect: {msg}")
            return
        if not missing:
            info(self, "All tables already exist. Nothing to create.")
            return
        from ...models import Base
        if len(missing) != len(Base.metadata.tables) and not ask(
                self, "Partly set up", "Some tables exist already. Create only the missing ones?"):
            return
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            eng = db.make_engine(cfg)
            db.create_all_and_seed(eng, with_sample=self.sample.isChecked())
            eng.dispose()
        except Exception as e:  # noqa: BLE001
            QGuiApplication.restoreOverrideCursor()
            warn(self, f"Could not create the tables: {getattr(e, 'orig', e)}")
            return
        QGuiApplication.restoreOverrideCursor()
        from ...seed import DEFAULT_ADMIN_PASSWORD, DEFAULT_ADMIN_USERNAME
        info(self, "The database is ready.\n\nSign in with username “%s” and password “%s”. "
                   "You will be asked to choose a new password." % (DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD))
        self._test()

    def _save(self):
        if not self._test():
            if not ask(self, "Save anyway?", "The connection test failed. Save these settings anyway?"):
                return
        self.cfg = self._read()
        config.save(self.cfg)
        self.accept()
