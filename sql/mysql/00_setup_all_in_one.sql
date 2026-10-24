-- ReserveMe 1.0.0 — 00 All-in-one: schema + required data + sample data
-- Target: MySQL 8.0.16+ / MariaDB 10.5+   Schema version: 1
-- Generated 2026-10-24 from reserveme/models.py — do not edit by hand.
-- Paste this whole file into your host's SQL console on an EMPTY database.
-- (Same content as 01 + 02 + 03 run in order.)

-- ReserveMe 1.0.0 — 01 Schema: creates all tables
-- Target: MySQL 8.0.16+ / MariaDB 10.5+   Schema version: 1
-- Generated 2026-10-24 from reserveme/models.py — do not edit by hand.
-- Run this once on an EMPTY database, then run 02_required_data.sql.

-- guests
CREATE TABLE guests (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	first_name VARCHAR(80) NOT NULL, 
	last_name VARCHAR(80) NOT NULL, 
	email VARCHAR(150), 
	phone VARCHAR(50), 
	nationality VARCHAR(60), 
	id_type VARCHAR(40), 
	id_number VARCHAR(60), 
	address VARCHAR(300), 
	date_of_birth DATE, 
	company VARCHAR(120), 
	vip BOOL NOT NULL DEFAULT false, 
	blacklisted BOOL NOT NULL DEFAULT false, 
	notes TEXT, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_guests_email ON guests (email);
CREATE INDEX ix_guests_name ON guests (last_name, first_name);

-- property_settings
CREATE TABLE property_settings (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	name VARCHAR(150) NOT NULL, 
	address VARCHAR(300), 
	phone VARCHAR(50), 
	email VARCHAR(150), 
	website VARCHAR(150), 
	tax_registration VARCHAR(80), 
	base_currency VARCHAR(3) NOT NULL DEFAULT 'USD', 
	alt_currency VARCHAR(3) DEFAULT 'JMD', 
	alt_rate NUMERIC(14, 4) NOT NULL DEFAULT '1', 
	check_in_time VARCHAR(5) NOT NULL DEFAULT '15:00', 
	check_out_time VARCHAR(5) NOT NULL DEFAULT '11:00', 
	business_date DATE NOT NULL, 
	invoice_footer TEXT, 
	next_reservation_no INTEGER NOT NULL DEFAULT '1001', 
	next_invoice_no INTEGER NOT NULL DEFAULT '1', 
	updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- rate_plans
CREATE TABLE rate_plans (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	code VARCHAR(12) NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	includes_breakfast BOOL NOT NULL DEFAULT false, 
	description TEXT, 
	is_active BOOL NOT NULL DEFAULT true, 
	PRIMARY KEY (id), 
	UNIQUE (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- room_types
CREATE TABLE room_types (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	code VARCHAR(12) NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	description TEXT, 
	base_occupancy INTEGER NOT NULL DEFAULT '2', 
	max_occupancy INTEGER NOT NULL DEFAULT '2', 
	base_rate NUMERIC(12, 2) NOT NULL DEFAULT '0', 
	sort_order INTEGER NOT NULL DEFAULT '0', 
	is_active BOOL NOT NULL DEFAULT true, 
	PRIMARY KEY (id), 
	UNIQUE (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- schema_info
CREATE TABLE schema_info (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	version INTEGER NOT NULL, 
	applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- taxes
CREATE TABLE taxes (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	name VARCHAR(80) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	value NUMERIC(12, 4) NOT NULL, 
	is_active BOOL NOT NULL DEFAULT true, 
	sort_order INTEGER NOT NULL DEFAULT '0', 
	PRIMARY KEY (id), 
	CONSTRAINT ck_taxes_kind CHECK (kind IN ('percent', 'fixed_per_night'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- users
CREATE TABLE users (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	username VARCHAR(60) NOT NULL, 
	full_name VARCHAR(120) NOT NULL, 
	email VARCHAR(150), 
	`role` VARCHAR(20) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	is_active BOOL NOT NULL DEFAULT true, 
	must_change_password BOOL NOT NULL DEFAULT false, 
	failed_attempts INTEGER NOT NULL DEFAULT '0', 
	locked_until DATETIME, 
	last_login_at DATETIME, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_users_role CHECK (role IN ('admin', 'manager', 'front_desk', 'reservations', 'housekeeping', 'accounting')), 
	UNIQUE (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- audit_log
CREATE TABLE audit_log (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	user_id INTEGER, 
	action VARCHAR(60) NOT NULL, 
	entity VARCHAR(40) NOT NULL, 
	entity_id INTEGER, 
	details TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_audit_log_at ON audit_log (at);
CREATE INDEX ix_audit_log_entity ON audit_log (entity, entity_id);

-- night_audit_runs
CREATE TABLE night_audit_runs (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	business_date DATE NOT NULL, 
	run_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	user_id INTEGER, 
	rooms_posted INTEGER NOT NULL DEFAULT '0', 
	room_revenue NUMERIC(12, 2) NOT NULL DEFAULT '0', 
	tax_revenue NUMERIC(12, 2) NOT NULL DEFAULT '0', 
	no_shows INTEGER NOT NULL DEFAULT '0', 
	notes TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_night_audit_date UNIQUE (business_date), 
	FOREIGN KEY(user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- rates
CREATE TABLE rates (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	rate_plan_id INTEGER NOT NULL, 
	room_type_id INTEGER NOT NULL, 
	season_name VARCHAR(60), 
	start_date DATE NOT NULL, 
	end_date DATE NOT NULL, 
	amount NUMERIC(12, 2) NOT NULL, 
	weekend_amount NUMERIC(12, 2), 
	min_stay INTEGER NOT NULL DEFAULT '1', 
	PRIMARY KEY (id), 
	CONSTRAINT ck_rates_dates CHECK (end_date >= start_date), 
	FOREIGN KEY(rate_plan_id) REFERENCES rate_plans (id), 
	FOREIGN KEY(room_type_id) REFERENCES room_types (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_rates_lookup ON rates (rate_plan_id, room_type_id, start_date);

-- rooms
CREATE TABLE rooms (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	number VARCHAR(12) NOT NULL, 
	room_type_id INTEGER NOT NULL, 
	building VARCHAR(60), 
	floor VARCHAR(20), 
	status VARCHAR(20) NOT NULL DEFAULT 'clean', 
	is_active BOOL NOT NULL DEFAULT true, 
	notes TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_rooms_status CHECK (status IN ('clean', 'dirty', 'inspected', 'out_of_order')), 
	UNIQUE (number), 
	FOREIGN KEY(room_type_id) REFERENCES room_types (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- reservations
CREATE TABLE reservations (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	code VARCHAR(20) NOT NULL, 
	guest_id INTEGER NOT NULL, 
	room_type_id INTEGER NOT NULL, 
	room_id INTEGER, 
	rate_plan_id INTEGER NOT NULL, 
	check_in DATE NOT NULL, 
	check_out DATE NOT NULL, 
	adults INTEGER NOT NULL DEFAULT '1', 
	children INTEGER NOT NULL DEFAULT '0', 
	status VARCHAR(20) NOT NULL DEFAULT 'confirmed', 
	source VARCHAR(40), 
	external_ref VARCHAR(60), 
	nightly_rate_override NUMERIC(12, 2), 
	estimated_total NUMERIC(12, 2) NOT NULL DEFAULT '0', 
	arrival_time VARCHAR(5), 
	notes TEXT, 
	cancel_reason VARCHAR(255), 
	checked_in_at DATETIME, 
	checked_out_at DATETIME, 
	created_by INTEGER, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_reservations_dates CHECK (check_out > check_in), 
	CONSTRAINT ck_reservations_status CHECK (status IN ('tentative', 'confirmed', 'checked_in', 'checked_out', 'cancelled', 'no_show')), 
	CONSTRAINT ck_reservations_adults CHECK (adults >= 1), 
	UNIQUE (code), 
	FOREIGN KEY(guest_id) REFERENCES guests (id), 
	FOREIGN KEY(room_type_id) REFERENCES room_types (id), 
	FOREIGN KEY(room_id) REFERENCES rooms (id), 
	FOREIGN KEY(rate_plan_id) REFERENCES rate_plans (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_reservations_dates ON reservations (check_in, check_out);
CREATE INDEX ix_reservations_guest_id ON reservations (guest_id);
CREATE INDEX ix_reservations_room ON reservations (room_id, check_in);
CREATE INDEX ix_reservations_status ON reservations (status);

-- room_status_log
CREATE TABLE room_status_log (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	room_id INTEGER NOT NULL, 
	old_status VARCHAR(20), 
	new_status VARCHAR(20) NOT NULL, 
	at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	user_id INTEGER, 
	note VARCHAR(255), 
	PRIMARY KEY (id), 
	FOREIGN KEY(room_id) REFERENCES rooms (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_room_status_log_room_id ON room_status_log (room_id);

-- folio_lines
CREATE TABLE folio_lines (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	reservation_id INTEGER NOT NULL, 
	business_date DATE NOT NULL, 
	stay_date DATE, 
	kind VARCHAR(20) NOT NULL, 
	description VARCHAR(200) NOT NULL, 
	quantity NUMERIC(10, 2) NOT NULL DEFAULT '1', 
	amount NUMERIC(12, 2) NOT NULL, 
	method VARCHAR(40), 
	reference VARCHAR(80), 
	original_currency VARCHAR(3), 
	original_amount NUMERIC(12, 2), 
	exchange_rate NUMERIC(14, 4), 
	reverses_id INTEGER, 
	user_id INTEGER, 
	posted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_folio_lines_kind CHECK (kind IN ('room', 'tax', 'charge', 'payment', 'adjustment')), 
	FOREIGN KEY(reservation_id) REFERENCES reservations (id), 
	FOREIGN KEY(reverses_id) REFERENCES folio_lines (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_folio_lines_bdate ON folio_lines (business_date, kind);
CREATE INDEX ix_folio_lines_reservation_id ON folio_lines (reservation_id);

-- invoices
CREATE TABLE invoices (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	number VARCHAR(20) NOT NULL, 
	reservation_id INTEGER NOT NULL, 
	issued_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	total_charges NUMERIC(12, 2) NOT NULL, 
	total_payments NUMERIC(12, 2) NOT NULL, 
	user_id INTEGER, 
	PRIMARY KEY (id), 
	UNIQUE (number), 
	FOREIGN KEY(reservation_id) REFERENCES reservations (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_invoices_reservation_id ON invoices (reservation_id);


-- ReserveMe 1.0.0 — 02 Required data: settings, first admin, rate plans
-- Target: MySQL 8.0.16+ / MariaDB 10.5+   Schema version: 1
-- Generated 2026-10-24 from reserveme/models.py — do not edit by hand.
-- First sign-in: username 'admin', password 'ChangeMe2026!'.
-- The app forces a new password on first sign-in.

INSERT INTO schema_info (version, applied_at) VALUES (1, CURRENT_TIMESTAMP);
INSERT INTO property_settings (name, address, phone, email, base_currency, alt_currency, alt_rate, check_in_time, check_out_time, business_date, invoice_footer, next_reservation_no, next_invoice_no, updated_at) VALUES ('My Resort', 'Edit me in Settings', '', '', 'USD', 'JMD', 157.0000, '15:00', '11:00', CURRENT_DATE, 'Thank you for staying with us!', 1001, 1, CURRENT_TIMESTAMP);
INSERT INTO users (username, full_name, `role`, password_hash, is_active, must_change_password, failed_attempts, created_at) VALUES ('admin', 'System Administrator', 'admin', '$argon2id$v=19$m=65536,t=3,p=4$NSYBoDsaoTKQguat0clzzQ$BV6UbqH+4rXsDIBLqLWgw0hhByzJ0Ex3+9/hdSlI8B0', true, true, 0, CURRENT_TIMESTAMP);
INSERT INTO rate_plans (code, name, includes_breakfast, description) VALUES ('RO', 'Room only', false, 'Accommodation only.');
INSERT INTO rate_plans (code, name, includes_breakfast, description) VALUES ('BB', 'Bed & breakfast', true, 'Accommodation with daily breakfast.');

-- ReserveMe 1.0.0 — 03 Sample data (optional): room types, rooms, rates, example taxes, guests
-- Target: MySQL 8.0.16+ / MariaDB 10.5+   Schema version: 1
-- Generated 2026-10-24 from reserveme/models.py — do not edit by hand.
-- Skip this file for a real property and enter your own rooms in Settings.
-- The tax rows are placeholders: set the real rates before taking bookings.

INSERT INTO room_types (code, name, base_occupancy, max_occupancy, base_rate, sort_order) VALUES ('STD', 'Standard Garden View', 2, 3, 140.00, 1);
INSERT INTO room_types (code, name, base_occupancy, max_occupancy, base_rate, sort_order) VALUES ('DLX', 'Deluxe Ocean View', 2, 3, 210.00, 2);
INSERT INTO room_types (code, name, base_occupancy, max_occupancy, base_rate, sort_order) VALUES ('STE', 'One-Bedroom Suite', 2, 4, 320.00, 3);
INSERT INTO room_types (code, name, base_occupancy, max_occupancy, base_rate, sort_order) VALUES ('VIL', 'Beach Villa', 4, 6, 550.00, 4);
INSERT INTO rooms (number, room_type_id, building, floor, status) VALUES ('101', (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'STD'), 'Main', '1', 'clean');
INSERT INTO rooms (number, room_type_id, building, floor, status) VALUES ('102', (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'STD'), 'Main', '1', 'clean');
INSERT INTO rooms (number, room_type_id, building, floor, status) VALUES ('103', (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'STD'), 'Main', '1', 'clean');
INSERT INTO rooms (number, room_type_id, building, floor, status) VALUES ('104', (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'STD'), 'Main', '1', 'clean');
INSERT INTO rooms (number, room_type_id, building, floor, status) VALUES ('105', (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'STD'), 'Main', '1', 'clean');
INSERT INTO rooms (number, room_type_id, building, floor, status) VALUES ('106', (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'STD'), 'Main', '1', 'clean');
INSERT INTO rooms (number, room_type_id, building, floor, status) VALUES ('201', (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'DLX'), 'Main', '2', 'clean');
INSERT INTO rooms (number, room_type_id, building, floor, status) VALUES ('202', (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'DLX'), 'Main', '2', 'clean');
INSERT INTO rooms (number, room_type_id, building, floor, status) VALUES ('203', (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'DLX'), 'Main', '2', 'clean');
INSERT INTO rooms (number, room_type_id, building, floor, status) VALUES ('204', (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'DLX'), 'Main', '2', 'clean');
INSERT INTO rooms (number, room_type_id, building, floor, status) VALUES ('205', (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'DLX'), 'Main', '2', 'clean');
INSERT INTO rooms (number, room_type_id, building, floor, status) VALUES ('206', (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'DLX'), 'Main', '2', 'clean');
INSERT INTO rooms (number, room_type_id, building, floor, status) VALUES ('301', (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'STE'), 'Main', '3', 'clean');
INSERT INTO rooms (number, room_type_id, building, floor, status) VALUES ('302', (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'STE'), 'Main', '3', 'clean');
INSERT INTO rooms (number, room_type_id, building, floor, status) VALUES ('303', (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'STE'), 'Main', '3', 'clean');
INSERT INTO rooms (number, room_type_id, building, floor, status) VALUES ('V1', (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'VIL'), 'Beachfront', 'G', 'clean');
INSERT INTO rooms (number, room_type_id, building, floor, status) VALUES ('V2', (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'VIL'), 'Beachfront', 'G', 'clean');
INSERT INTO rates (rate_plan_id, room_type_id, season_name, start_date, end_date, amount, min_stay) VALUES ((SELECT rate_plans.id 
FROM rate_plans 
WHERE rate_plans.code = 'RO'), (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'STD'), 'Low season 2026', '2026-04-16', '2026-12-14', 140.00, 1);
INSERT INTO rates (rate_plan_id, room_type_id, season_name, start_date, end_date, amount, min_stay) VALUES ((SELECT rate_plans.id 
FROM rate_plans 
WHERE rate_plans.code = 'BB'), (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'STD'), 'Low season 2026', '2026-04-16', '2026-12-14', 190.00, 1);
INSERT INTO rates (rate_plan_id, room_type_id, season_name, start_date, end_date, amount, min_stay) VALUES ((SELECT rate_plans.id 
FROM rate_plans 
WHERE rate_plans.code = 'RO'), (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'STD'), 'Peak season 2026/27', '2026-12-15', '2027-04-15', 189.00, 3);
INSERT INTO rates (rate_plan_id, room_type_id, season_name, start_date, end_date, amount, min_stay) VALUES ((SELECT rate_plans.id 
FROM rate_plans 
WHERE rate_plans.code = 'BB'), (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'STD'), 'Peak season 2026/27', '2026-12-15', '2027-04-15', 239.00, 3);
INSERT INTO rates (rate_plan_id, room_type_id, season_name, start_date, end_date, amount, min_stay) VALUES ((SELECT rate_plans.id 
FROM rate_plans 
WHERE rate_plans.code = 'RO'), (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'STD'), 'Low season 2027', '2027-04-16', '2027-12-14', 140.00, 1);
INSERT INTO rates (rate_plan_id, room_type_id, season_name, start_date, end_date, amount, min_stay) VALUES ((SELECT rate_plans.id 
FROM rate_plans 
WHERE rate_plans.code = 'BB'), (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'STD'), 'Low season 2027', '2027-04-16', '2027-12-14', 190.00, 1);
INSERT INTO rates (rate_plan_id, room_type_id, season_name, start_date, end_date, amount, min_stay) VALUES ((SELECT rate_plans.id 
FROM rate_plans 
WHERE rate_plans.code = 'RO'), (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'DLX'), 'Low season 2026', '2026-04-16', '2026-12-14', 210.00, 1);
INSERT INTO rates (rate_plan_id, room_type_id, season_name, start_date, end_date, amount, min_stay) VALUES ((SELECT rate_plans.id 
FROM rate_plans 
WHERE rate_plans.code = 'BB'), (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'DLX'), 'Low season 2026', '2026-04-16', '2026-12-14', 260.00, 1);
INSERT INTO rates (rate_plan_id, room_type_id, season_name, start_date, end_date, amount, min_stay) VALUES ((SELECT rate_plans.id 
FROM rate_plans 
WHERE rate_plans.code = 'RO'), (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'DLX'), 'Peak season 2026/27', '2026-12-15', '2027-04-15', 284.00, 3);
INSERT INTO rates (rate_plan_id, room_type_id, season_name, start_date, end_date, amount, min_stay) VALUES ((SELECT rate_plans.id 
FROM rate_plans 
WHERE rate_plans.code = 'BB'), (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'DLX'), 'Peak season 2026/27', '2026-12-15', '2027-04-15', 334.00, 3);
INSERT INTO rates (rate_plan_id, room_type_id, season_name, start_date, end_date, amount, min_stay) VALUES ((SELECT rate_plans.id 
FROM rate_plans 
WHERE rate_plans.code = 'RO'), (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'DLX'), 'Low season 2027', '2027-04-16', '2027-12-14', 210.00, 1);
INSERT INTO rates (rate_plan_id, room_type_id, season_name, start_date, end_date, amount, min_stay) VALUES ((SELECT rate_plans.id 
FROM rate_plans 
WHERE rate_plans.code = 'BB'), (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'DLX'), 'Low season 2027', '2027-04-16', '2027-12-14', 260.00, 1);
INSERT INTO rates (rate_plan_id, room_type_id, season_name, start_date, end_date, amount, min_stay) VALUES ((SELECT rate_plans.id 
FROM rate_plans 
WHERE rate_plans.code = 'RO'), (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'STE'), 'Low season 2026', '2026-04-16', '2026-12-14', 320.00, 1);
INSERT INTO rates (rate_plan_id, room_type_id, season_name, start_date, end_date, amount, min_stay) VALUES ((SELECT rate_plans.id 
FROM rate_plans 
WHERE rate_plans.code = 'BB'), (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'STE'), 'Low season 2026', '2026-04-16', '2026-12-14', 370.00, 1);
INSERT INTO rates (rate_plan_id, room_type_id, season_name, start_date, end_date, amount, min_stay) VALUES ((SELECT rate_plans.id 
FROM rate_plans 
WHERE rate_plans.code = 'RO'), (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'STE'), 'Peak season 2026/27', '2026-12-15', '2027-04-15', 432.00, 3);
INSERT INTO rates (rate_plan_id, room_type_id, season_name, start_date, end_date, amount, min_stay) VALUES ((SELECT rate_plans.id 
FROM rate_plans 
WHERE rate_plans.code = 'BB'), (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'STE'), 'Peak season 2026/27', '2026-12-15', '2027-04-15', 482.00, 3);
INSERT INTO rates (rate_plan_id, room_type_id, season_name, start_date, end_date, amount, min_stay) VALUES ((SELECT rate_plans.id 
FROM rate_plans 
WHERE rate_plans.code = 'RO'), (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'STE'), 'Low season 2027', '2027-04-16', '2027-12-14', 320.00, 1);
INSERT INTO rates (rate_plan_id, room_type_id, season_name, start_date, end_date, amount, min_stay) VALUES ((SELECT rate_plans.id 
FROM rate_plans 
WHERE rate_plans.code = 'BB'), (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'STE'), 'Low season 2027', '2027-04-16', '2027-12-14', 370.00, 1);
INSERT INTO rates (rate_plan_id, room_type_id, season_name, start_date, end_date, amount, min_stay) VALUES ((SELECT rate_plans.id 
FROM rate_plans 
WHERE rate_plans.code = 'RO'), (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'VIL'), 'Low season 2026', '2026-04-16', '2026-12-14', 550.00, 1);
INSERT INTO rates (rate_plan_id, room_type_id, season_name, start_date, end_date, amount, min_stay) VALUES ((SELECT rate_plans.id 
FROM rate_plans 
WHERE rate_plans.code = 'BB'), (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'VIL'), 'Low season 2026', '2026-04-16', '2026-12-14', 650.00, 1);
INSERT INTO rates (rate_plan_id, room_type_id, season_name, start_date, end_date, amount, min_stay) VALUES ((SELECT rate_plans.id 
FROM rate_plans 
WHERE rate_plans.code = 'RO'), (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'VIL'), 'Peak season 2026/27', '2026-12-15', '2027-04-15', 742.00, 3);
INSERT INTO rates (rate_plan_id, room_type_id, season_name, start_date, end_date, amount, min_stay) VALUES ((SELECT rate_plans.id 
FROM rate_plans 
WHERE rate_plans.code = 'BB'), (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'VIL'), 'Peak season 2026/27', '2026-12-15', '2027-04-15', 842.00, 3);
INSERT INTO rates (rate_plan_id, room_type_id, season_name, start_date, end_date, amount, min_stay) VALUES ((SELECT rate_plans.id 
FROM rate_plans 
WHERE rate_plans.code = 'RO'), (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'VIL'), 'Low season 2027', '2027-04-16', '2027-12-14', 550.00, 1);
INSERT INTO rates (rate_plan_id, room_type_id, season_name, start_date, end_date, amount, min_stay) VALUES ((SELECT rate_plans.id 
FROM rate_plans 
WHERE rate_plans.code = 'BB'), (SELECT room_types.id 
FROM room_types 
WHERE room_types.code = 'VIL'), 'Low season 2027', '2027-04-16', '2027-12-14', 650.00, 1);
INSERT INTO taxes (name, kind, value, sort_order) VALUES ('Example tax % (set the real rate)', 'percent', 10.0000, 1);
INSERT INTO taxes (name, kind, value, sort_order) VALUES ('Example per-night levy (set the real amount)', 'fixed_per_night', 2.0000, 2);
INSERT INTO guests (first_name, last_name, email, phone, nationality, created_at) VALUES ('Alicia', 'Campbell', 'alicia@example.com', '+1 876 555 0101', 'Jamaican', CURRENT_TIMESTAMP);
INSERT INTO guests (first_name, last_name, email, phone, nationality, vip, created_at) VALUES ('Mark', 'Thompson', 'mark.t@example.com', '+1 305 555 0144', 'American', true, CURRENT_TIMESTAMP);
INSERT INTO guests (first_name, last_name, email, phone, nationality, created_at) VALUES ('Sophie', 'Müller', 'sophie@example.de', '+49 30 555 0199', 'German', CURRENT_TIMESTAMP);
