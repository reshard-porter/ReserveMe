"""Generate the database setup scripts in /sql from the application models.

Run:  python tools/generate_sql.py
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, insert, select  # noqa: E402
from sqlalchemy.dialects import mysql, postgresql  # noqa: E402
from sqlalchemy.schema import CreateIndex, CreateTable  # noqa: E402

from reserveme import SCHEMA_VERSION, __version__  # noqa: E402
from reserveme import seed  # noqa: E402
from reserveme.models import (ACTIVE_RES_STATUSES, Base, Guest, PropertySettings, Rate,  # noqa: E402
                              RatePlan, Room, RoomType, SchemaInfo, Tax, User)
from reserveme.security import hash_password  # noqa: E402

# "named" paramstyle stops literal % signs being doubled to %% in the output.
DIALECTS = {"postgresql": postgresql.dialect(paramstyle="named"), "mysql": mysql.dialect(paramstyle="named")}


def header(title: str, engine: str, extra: str = "") -> str:
    eng = "PostgreSQL 13+" if engine == "postgresql" else "MySQL 8.0.16+ / MariaDB 10.5+"
    return (f"-- ReserveMe {__version__} — {title}\n"
            f"-- Target: {eng}   Schema version: {SCHEMA_VERSION}\n"
            f"-- Generated {dt.date.today().isoformat()} from reserveme/models.py — do not edit by hand.\n"
            f"{extra}\n")


def stmt(s, dialect) -> str:
    # Fill timestamp columns that the app normally fills in Python.
    table = s.table
    given = {c.key for c in s._values} if s._values else set()
    extra = {c.name: func.current_timestamp() for c in table.columns
             if c.default is not None and callable(getattr(c.default, "arg", None)) and c.name not in given}
    if extra:
        s = s.values(**extra)
    s = s.inline()
    return str(s.compile(dialect=dialect, compile_kwargs={"literal_binds": True})).strip() + ";\n"


def schema_sql(engine: str) -> str:
    d = DIALECTS[engine]
    out = [header("01 Schema: creates all tables", engine,
                  "-- Run this once on an EMPTY database, then run 02_required_data.sql.\n")]
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=d)).strip()
        if engine == "mysql":
            ddl += " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
        out.append(f"-- {table.name}\n{ddl};\n")
        for idx in sorted(table.indexes, key=lambda i: i.name):
            out.append(str(CreateIndex(idx).compile(dialect=d)).strip() + ";\n")
        out.append("\n")
    return "".join(out)


def required_sql(engine: str, admin_hash: str) -> str:
    d = DIALECTS[engine]
    p = seed.PROPERTY
    out = [header("02 Required data: settings, first admin, rate plans", engine,
                  f"-- First sign-in: username '{seed.DEFAULT_ADMIN_USERNAME}', password "
                  f"'{seed.DEFAULT_ADMIN_PASSWORD}'.\n"
                  "-- The app forces a new password on first sign-in.\n")]
    out.append(stmt(insert(SchemaInfo).values(version=SCHEMA_VERSION), d))
    out.append(stmt(insert(PropertySettings).values(business_date=func.current_date(), **p), d))
    out.append(stmt(insert(User).values(
        username=seed.DEFAULT_ADMIN_USERNAME, full_name="System Administrator", role="admin",
        password_hash=admin_hash, must_change_password=True, is_active=True, failed_attempts=0), d))
    for rp in seed.RATE_PLANS:
        out.append(stmt(insert(RatePlan).values(**rp), d))
    return "".join(out)


def sample_sql(engine: str) -> str:
    d = DIALECTS[engine]
    out = [header("03 Sample data (optional): room types, rooms, rates, example taxes, guests", engine,
                  "-- Skip this file for a real property and enter your own rooms in Settings.\n"
                  "-- The tax rows are placeholders: set the real rates before taking bookings.\n")]

    def type_id(code):
        return select(RoomType.id).where(RoomType.code == code).scalar_subquery()

    def plan_id(code):
        return select(RatePlan.id).where(RatePlan.code == code).scalar_subquery()

    for rt in seed.SAMPLE_ROOM_TYPES:
        out.append(stmt(insert(RoomType).values(**rt), d))
    for r in seed.SAMPLE_ROOMS:
        out.append(stmt(insert(Room).values(number=r["number"], room_type_id=type_id(r["type"]),
                                            building=r["building"], floor=r["floor"], status="clean"), d))
    for r in seed.sample_rates():
        out.append(stmt(insert(Rate).values(
            rate_plan_id=plan_id(r["plan"]), room_type_id=type_id(r["type"]), season_name=r["season_name"],
            start_date=r["start_date"], end_date=r["end_date"], amount=r["amount"],
            min_stay=r["min_stay"]), d))
    for t in seed.SAMPLE_TAXES:
        out.append(stmt(insert(Tax).values(**t), d))
    for g in seed.SAMPLE_GUESTS:
        out.append(stmt(insert(Guest).values(**g), d))
    return "".join(out)


def guard_sql() -> str:
    statuses = ", ".join(f"'{s}'" for s in ACTIVE_RES_STATUSES)
    return (header("04 Optional: database-level double-booking guard", "postgresql",
                   "-- The app already prevents double bookings. This adds a second, database-level\n"
                   "-- safety net. It needs the btree_gist extension; if your host does not allow\n"
                   "-- CREATE EXTENSION, skip this file — the app works without it.\n")
            + "CREATE EXTENSION IF NOT EXISTS btree_gist;\n"
            + "ALTER TABLE reservations ADD CONSTRAINT ex_reservations_no_double_booking\n"
            + "  EXCLUDE USING gist (room_id WITH =, daterange(check_in, check_out) WITH &&)\n"
            + f"  WHERE (room_id IS NOT NULL AND status IN ({statuses}));\n")


def main() -> None:
    admin_hash = hash_password(seed.DEFAULT_ADMIN_PASSWORD)
    for engine in DIALECTS:
        folder = ROOT / "sql" / engine
        folder.mkdir(parents=True, exist_ok=True)
        files = {
            "01_schema.sql": schema_sql(engine),
            "02_required_data.sql": required_sql(engine, admin_hash),
            "03_sample_data.sql": sample_sql(engine),
        }
        if engine == "postgresql":
            files["04_optional_double_booking_guard.sql"] = guard_sql()
        files["00_setup_all_in_one.sql"] = (
            header("00 All-in-one: schema + required data + sample data", engine,
                   "-- Paste this whole file into your host's SQL console on an EMPTY database.\n"
                   "-- (Same content as 01 + 02 + 03 run in order.)\n")
            + files["01_schema.sql"] + "\n" + files["02_required_data.sql"] + "\n" + files["03_sample_data.sql"])
        for name, text in files.items():
            (folder / name).write_text(text, "utf-8")
            print(f"wrote sql/{engine}/{name} ({len(text.splitlines())} lines)")


if __name__ == "__main__":
    main()
