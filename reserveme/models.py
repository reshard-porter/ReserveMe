"""Database tables.

The same models drive the application and the generated SQL scripts in /sql,
so the two can never drift apart. Types are kept portable between
PostgreSQL and MySQL/MariaDB (both offered by Filess.io).
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer,
    Numeric, String, Text, UniqueConstraint, false, text, true,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

Money = Numeric(12, 2)


def utcnow() -> dt.datetime:
    """Naive UTC timestamp (portable across PostgreSQL and MySQL)."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------- #
# Enumerations (stored as short strings; CHECK constraints keep them honest)
# --------------------------------------------------------------------------- #
ROLES = ("admin", "manager", "front_desk", "reservations", "housekeeping", "accounting")
ROOM_STATUSES = ("clean", "dirty", "inspected", "out_of_order")
RES_STATUSES = ("tentative", "confirmed", "checked_in", "checked_out", "cancelled", "no_show")
ACTIVE_RES_STATUSES = ("tentative", "confirmed", "checked_in")
LINE_KINDS = ("room", "tax", "charge", "payment", "adjustment")
TAX_KINDS = ("percent", "fixed_per_night")
SOURCES = ("Direct", "Phone", "Email", "Walk-in", "Website", "Booking.com", "Expedia",
           "Airbnb", "Travel agent", "Corporate", "Other")
PAYMENT_METHODS = ("Cash", "Card (terminal)", "Bank transfer", "Cheque", "Voucher", "Other")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


class SchemaInfo(Base):
    __tablename__ = "schema_info"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    applied_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, server_default=text("CURRENT_TIMESTAMP"), nullable=False)


class PropertySettings(Base):
    """Single row holding the property's configuration and business date."""
    __tablename__ = "property_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(300))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    email: Mapped[Optional[str]] = mapped_column(String(150))
    website: Mapped[Optional[str]] = mapped_column(String(150))
    tax_registration: Mapped[Optional[str]] = mapped_column(String(80))
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="USD")
    alt_currency: Mapped[Optional[str]] = mapped_column(String(3), server_default="JMD")
    alt_rate: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False, server_default="1")
    check_in_time: Mapped[str] = mapped_column(String(5), nullable=False, server_default="15:00")
    check_out_time: Mapped[str] = mapped_column(String(5), nullable=False, server_default="11:00")
    business_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    invoice_footer: Mapped[Optional[str]] = mapped_column(Text)
    next_reservation_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1001")
    next_invoice_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, server_default=text("CURRENT_TIMESTAMP"), nullable=False)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_in("role", ROLES), name="ck_users_role"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(150))
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    locked_until: Mapped[Optional[dt.datetime]] = mapped_column(DateTime)
    last_login_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, server_default=text("CURRENT_TIMESTAMP"), nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_at", "at"), Index("ix_audit_log_entity", "entity", "entity_id"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    entity: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer)
    details: Mapped[Optional[str]] = mapped_column(Text)
    user: Mapped[Optional[User]] = relationship()


class RoomType(Base):
    __tablename__ = "room_types"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    base_occupancy: Mapped[int] = mapped_column(Integer, nullable=False, server_default="2")
    max_occupancy: Mapped[int] = mapped_column(Integer, nullable=False, server_default="2")
    base_rate: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default="0")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    rooms: Mapped[list["Room"]] = relationship(back_populates="room_type")


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (CheckConstraint(_in("status", ROOM_STATUSES), name="ck_rooms_status"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id"), nullable=False)
    building: Mapped[Optional[str]] = mapped_column(String(60))
    floor: Mapped[Optional[str]] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="clean")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    notes: Mapped[Optional[str]] = mapped_column(Text)
    room_type: Mapped[RoomType] = relationship(back_populates="rooms")


class RoomStatusLog(Base):
    __tablename__ = "room_status_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), nullable=False, index=True)
    old_status: Mapped[Optional[str]] = mapped_column(String(20))
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    note: Mapped[Optional[str]] = mapped_column(String(255))


class RatePlan(Base):
    __tablename__ = "rate_plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    includes_breakfast: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())


class Rate(Base):
    """Nightly price for a room type on a rate plan between two dates (season)."""
    __tablename__ = "rates"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_rates_dates"),
        Index("ix_rates_lookup", "rate_plan_id", "room_type_id", "start_date"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rate_plan_id: Mapped[int] = mapped_column(ForeignKey("rate_plans.id"), nullable=False)
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id"), nullable=False)
    season_name: Mapped[Optional[str]] = mapped_column(String(60))
    start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    weekend_amount: Mapped[Optional[Decimal]] = mapped_column(Money)
    min_stay: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    rate_plan: Mapped[RatePlan] = relationship()
    room_type: Mapped[RoomType] = relationship()


class Tax(Base):
    __tablename__ = "taxes"
    __table_args__ = (CheckConstraint(_in("kind", TAX_KINDS), name="ck_taxes_kind"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class Guest(Base):
    __tablename__ = "guests"
    __table_args__ = (Index("ix_guests_name", "last_name", "first_name"), Index("ix_guests_email", "email"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    last_name: Mapped[str] = mapped_column(String(80), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(150))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    nationality: Mapped[Optional[str]] = mapped_column(String(60))
    id_type: Mapped[Optional[str]] = mapped_column(String(40))
    id_number: Mapped[Optional[str]] = mapped_column(String(60))
    address: Mapped[Optional[str]] = mapped_column(String(300))
    date_of_birth: Mapped[Optional[dt.date]] = mapped_column(Date)
    company: Mapped[Optional[str]] = mapped_column(String(120))
    vip: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    blacklisted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint("check_out > check_in", name="ck_reservations_dates"),
        CheckConstraint(_in("status", RES_STATUSES), name="ck_reservations_status"),
        CheckConstraint("adults >= 1", name="ck_reservations_adults"),
        Index("ix_reservations_dates", "check_in", "check_out"),
        Index("ix_reservations_room", "room_id", "check_in"),
        Index("ix_reservations_status", "status"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id"), nullable=False, index=True)
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id"), nullable=False)
    room_id: Mapped[Optional[int]] = mapped_column(ForeignKey("rooms.id"))
    rate_plan_id: Mapped[int] = mapped_column(ForeignKey("rate_plans.id"), nullable=False)
    check_in: Mapped[dt.date] = mapped_column(Date, nullable=False)
    check_out: Mapped[dt.date] = mapped_column(Date, nullable=False)
    adults: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    children: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="confirmed")
    source: Mapped[Optional[str]] = mapped_column(String(40))
    external_ref: Mapped[Optional[str]] = mapped_column(String(60))
    nightly_rate_override: Mapped[Optional[Decimal]] = mapped_column(Money)
    estimated_total: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default="0")
    arrival_time: Mapped[Optional[str]] = mapped_column(String(5))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    cancel_reason: Mapped[Optional[str]] = mapped_column(String(255))
    checked_in_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime)
    checked_out_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    guest: Mapped[Guest] = relationship()
    room_type: Mapped[RoomType] = relationship()
    room: Mapped[Optional[Room]] = relationship()
    rate_plan: Mapped[RatePlan] = relationship()
    lines: Mapped[list["FolioLine"]] = relationship(back_populates="reservation", order_by="FolioLine.id")

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days


class FolioLine(Base):
    """One line on a guest's bill. Charges are positive, payments negative.

    Lines are never deleted; mistakes are corrected with a reversing line.
    """
    __tablename__ = "folio_lines"
    __table_args__ = (
        CheckConstraint(_in("kind", LINE_KINDS), name="ck_folio_lines_kind"),
        Index("ix_folio_lines_bdate", "business_date", "kind"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("reservations.id"), nullable=False, index=True)
    business_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    stay_date: Mapped[Optional[dt.date]] = mapped_column(Date)  # the night a room/tax line is for
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, server_default="1")
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)  # base currency, signed
    method: Mapped[Optional[str]] = mapped_column(String(40))
    reference: Mapped[Optional[str]] = mapped_column(String(80))
    original_currency: Mapped[Optional[str]] = mapped_column(String(3))
    original_amount: Mapped[Optional[Decimal]] = mapped_column(Money)
    exchange_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    reverses_id: Mapped[Optional[int]] = mapped_column(ForeignKey("folio_lines.id"))
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    posted_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    reservation: Mapped[Reservation] = relationship(back_populates="lines")
    user: Mapped[Optional[User]] = relationship()


class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("reservations.id"), nullable=False, index=True)
    issued_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    total_charges: Mapped[Decimal] = mapped_column(Money, nullable=False)
    total_payments: Mapped[Decimal] = mapped_column(Money, nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))


class NightAuditRun(Base):
    __tablename__ = "night_audit_runs"
    __table_args__ = (UniqueConstraint("business_date", name="uq_night_audit_date"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    run_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    rooms_posted: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    room_revenue: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default="0")
    tax_revenue: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default="0")
    no_shows: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    notes: Mapped[Optional[str]] = mapped_column(Text)
