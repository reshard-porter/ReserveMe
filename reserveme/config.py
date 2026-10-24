"""Connection settings, stored per computer.

Non-secret settings live in a JSON file in the user's config folder.
The database password is kept in the operating system's credential store
(Windows Credential Manager / macOS Keychain) when available.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import quote_plus

from platformdirs import user_config_dir, user_log_dir

from . import APP_NAME, APP_ORG

log = logging.getLogger(__name__)

CONFIG_DIR = Path(user_config_dir(APP_NAME, APP_ORG))
LOG_DIR = Path(user_log_dir(APP_NAME, APP_ORG))
CONFIG_FILE = CONFIG_DIR / "connection.json"
KEYRING_SERVICE = "ReserveMe database"

ENGINES = {
    "postgresql": ("PostgreSQL", 5432),
    "mysql": ("MySQL / MariaDB", 3306),
    "sqlite": ("Local file (single computer / demo)", 0),
}


@dataclass
class ConnectionConfig:
    engine: str = "postgresql"
    host: str = ""
    port: int = 5432
    database: str = ""
    username: str = ""
    ssl: str = "prefer"  # disable | prefer | require
    sqlite_path: str = ""
    password: str = field(default="", repr=False)  # never written to the JSON file

    def is_complete(self) -> bool:
        if self.engine == "sqlite":
            return bool(self.sqlite_path)
        return bool(self.host and self.database and self.username)

    def url(self) -> str:
        if self.engine == "sqlite":
            return f"sqlite:///{self.sqlite_path}"
        user = quote_plus(self.username)
        pw = quote_plus(self.password)
        if self.engine == "postgresql":
            return f"postgresql+psycopg://{user}:{pw}@{self.host}:{self.port}/{self.database}"
        if self.engine == "mysql":
            return f"mysql+pymysql://{user}:{pw}@{self.host}:{self.port}/{self.database}?charset=utf8mb4"
        raise ValueError(f"Unknown engine {self.engine}")

    def connect_args(self) -> dict:
        if self.engine == "postgresql":
            return {"sslmode": self.ssl, "connect_timeout": 10, "application_name": APP_NAME}
        if self.engine == "mysql":
            args: dict = {"connect_timeout": 10}
            if self.ssl in ("prefer", "require"):
                # Encrypted; the server certificate is not verified (hosted services rotate them).
                args["ssl"] = {"check_hostname": False}
            return args
        return {}

    def describe(self) -> str:
        if self.engine == "sqlite":
            return f"Local file: {self.sqlite_path}"
        return f"{self.username}@{self.host}:{self.port}/{self.database}"


def _keyring():
    try:
        import keyring  # noqa: WPS433
        keyring.get_keyring()
        return keyring
    except Exception:  # pragma: no cover - depends on OS
        return None


def load() -> ConnectionConfig:
    cfg = ConnectionConfig()
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text("utf-8"))
            for k, v in data.items():
                if hasattr(cfg, k) and k != "password":
                    setattr(cfg, k, v)
            kr = _keyring()
            if kr and cfg.username:
                cfg.password = kr.get_password(KEYRING_SERVICE, f"{cfg.username}@{cfg.host}") or ""
            if not cfg.password:
                cfg.password = data.get("password_fallback", "")
        except Exception:
            log.exception("Could not read connection settings")
    return cfg


def save(cfg: ConnectionConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = asdict(cfg)
    data.pop("password", None)
    kr = _keyring()
    stored = False
    if kr and cfg.engine != "sqlite":
        try:
            kr.set_password(KEYRING_SERVICE, f"{cfg.username}@{cfg.host}", cfg.password)
            stored = True
        except Exception:  # pragma: no cover
            log.warning("Credential store unavailable; falling back to config file")
    if not stored and cfg.engine != "sqlite":
        data["password_fallback"] = cfg.password
    CONFIG_FILE.write_text(json.dumps(data, indent=2), "utf-8")
    try:
        CONFIG_FILE.chmod(0o600)
    except OSError:
        pass
