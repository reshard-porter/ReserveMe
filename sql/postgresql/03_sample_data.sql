-- ReserveMe 1.0.0 — 03 Sample data (optional): room types, rooms, rates, example taxes, guests
-- Target: PostgreSQL 13+   Schema version: 1
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
