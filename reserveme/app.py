"""Application start-up: connection → sign-in → main window."""
from __future__ import annotations

import logging
import logging.handlers
import sys

from PySide6.QtCore import QEventLoop, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from . import APP_NAME, APP_ORG, __version__, config, db
from .ui import theme
from .ui.common import state


def setup_logging() -> None:
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(config.LOG_DIR / "reserveme.log", maxBytes=2_000_000,
                                                   backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if not getattr(sys, "frozen", False):
        root.addHandler(logging.StreamHandler())

    def excepthook(t, v, tb):
        logging.getLogger("reserveme").critical("Unhandled error", exc_info=(t, v, tb))
        QMessageBox.critical(None, "Unexpected error", f"{v}\n\nDetails were written to the log in {config.LOG_DIR}.")
    sys.excepthook = excepthook


def connect(app) -> bool:
    """Make sure we have a working, set-up database. Returns False if the user gives up."""
    from .ui.dialogs.connection import ConnectionDialog
    cfg = config.load()
    message = None
    while True:
        if not cfg.is_complete() or message:
            dlg = ConnectionDialog(cfg, message)
            if not dlg.exec():
                return False
            cfg = dlg.cfg
        try:
            db.init(cfg)
            db.check_ready()
            state.reload()
            return True
        except db.DatabaseNotReady as e:
            message = str(e)
        except Exception as e:  # noqa: BLE001
            logging.exception("Connection failed")
            message = "Could not connect: " + str(getattr(e, "orig", e)).strip().splitlines()[0][:300]


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORG)
    app.setApplicationVersion(__version__)
    from pathlib import Path
    icon = Path(__file__).parent / "resources" / "icon.png"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    setup_logging()
    theme.apply(app)
    logging.info("ReserveMe %s starting", __version__)
    if "--self-test" in sys.argv:
        return self_test()

    from .ui.dialogs.login import ChangePasswordDialog, LoginDialog
    from .ui.main_window import MainWindow

    if not connect(app):
        return 0
    while True:
        login = LoginDialog(connection_text=config.load().describe())
        if not login.exec():
            if login.change_connection:
                config_cfg = config.load()
                from .ui.dialogs.connection import ConnectionDialog
                if ConnectionDialog(config_cfg).exec() and not connect(app):
                    return 0
                continue
            return 0
        state.actor = login.actor
        if login.must_change:
            if not ChangePasswordDialog(state.actor, forced=True).exec():
                state.actor = None
                continue
        win = MainWindow()
        loop = QEventLoop()
        win.closed.connect(loop.quit)
        win.show()
        loop.exec()
        signed_out = win.signed_out
        win.deleteLater()
        state.actor = None
        if not signed_out:
            return 0


def self_test() -> int:
    """Support check: loads every module and drivers; with --db URL also checks the database."""
    import importlib
    for mod in ("reserveme.ui.main_window", "psycopg", "pymysql", "argon2", "openpyxl", "keyring"):
        importlib.import_module(mod)
    from .security import hash_password, verify_password
    assert verify_password(hash_password("x" * 12), "x" * 12)
    if "--db" in sys.argv:
        db.init(sys.argv[sys.argv.index("--db") + 1])
        db.check_ready()
        state.reload()
        print(f"Database OK: {state.property_name}, business date {state.business_date}")
    print(f"ReserveMe {__version__} self-test OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
