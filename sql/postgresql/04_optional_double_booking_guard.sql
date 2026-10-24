-- ReserveMe 1.0.0 — 04 Optional: database-level double-booking guard
-- Target: PostgreSQL 13+   Schema version: 1
-- Generated 2026-10-24 from reserveme/models.py — do not edit by hand.
-- The app already prevents double bookings. This adds a second, database-level
-- safety net. It needs the btree_gist extension; if your host does not allow
-- CREATE EXTENSION, skip this file — the app works without it.

CREATE EXTENSION IF NOT EXISTS btree_gist;
ALTER TABLE reservations ADD CONSTRAINT ex_reservations_no_double_booking
  EXCLUDE USING gist (room_id WITH =, daterange(check_in, check_out) WITH &&)
  WHERE (room_id IS NOT NULL AND status IN ('tentative', 'confirmed', 'checked_in'));
