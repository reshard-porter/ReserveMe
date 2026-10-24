-- ReserveMe 1.0.0 — 02 Required data: settings, first admin, rate plans
-- Target: PostgreSQL 13+   Schema version: 1
-- Generated 2026-10-24 from reserveme/models.py — do not edit by hand.
-- First sign-in: username 'admin', password 'ChangeMe2026!'.
-- The app forces a new password on first sign-in.

INSERT INTO schema_info (version, applied_at) VALUES (1, CURRENT_TIMESTAMP);
INSERT INTO property_settings (name, address, phone, email, base_currency, alt_currency, alt_rate, check_in_time, check_out_time, business_date, invoice_footer, next_reservation_no, next_invoice_no, updated_at) VALUES ('My Resort', 'Edit me in Settings', '', '', 'USD', 'JMD', 157.0000, '15:00', '11:00', CURRENT_DATE, 'Thank you for staying with us!', 1001, 1, CURRENT_TIMESTAMP);
INSERT INTO users (username, full_name, role, password_hash, is_active, must_change_password, failed_attempts, created_at) VALUES ('admin', 'System Administrator', 'admin', '$argon2id$v=19$m=65536,t=3,p=4$NSYBoDsaoTKQguat0clzzQ$BV6UbqH+4rXsDIBLqLWgw0hhByzJ0Ex3+9/hdSlI8B0', true, true, 0, CURRENT_TIMESTAMP);
INSERT INTO rate_plans (code, name, includes_breakfast, description) VALUES ('RO', 'Room only', false, 'Accommodation only.');
INSERT INTO rate_plans (code, name, includes_breakfast, description) VALUES ('BB', 'Bed & breakfast', true, 'Accommodation with daily breakfast.');
