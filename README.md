# ReserveMe — Resort Property Management (desktop, Windows & macOS)

ReserveMe runs the front office of a resort: reservations, a drag-and-drop tape chart, check-in and
check-out, guest profiles, housekeeping, guest bills and invoices, night audit, and management reports.
Every computer at the resort runs the app and connects to one shared online database (for example on
Filess.io), so all desks see the same rooms and bookings.

Version 1.0.0 · Python 3.12 · PySide6 (Qt 6) · PostgreSQL or MySQL/MariaDB

---

## 1. Set up the database on Filess.io

1. Sign in at filess.io and create a database. **Choose PostgreSQL** (recommended) or MySQL.
2. Open the database's **Connect** panel. Note the **host, port, database name, username and password**.
3. Open the database's SQL console (or connect with any SQL tool such as DBeaver or pgAdmin) and run,
   in this order, the files in the folder that matches your engine:

   | Step | PostgreSQL: `sql/postgresql/` | MySQL: `sql/mysql/` | What it does |
   | --- | --- | --- | --- |
   | 1 | `01_schema.sql` | `01_schema.sql` | Creates the 15 tables |
   | 2 | `02_required_data.sql` | `02_required_data.sql` | Settings row, first admin login, two rate plans |
   | 3 (optional) | `03_sample_data.sql` | `03_sample_data.sql` | 17 sample rooms, seasons, example taxes, 3 guests — for training only |
   | 4 (optional) | `04_optional_double_booking_guard.sql` | — | Extra database-level double-booking guard (skip if the host refuses `CREATE EXTENSION`) |

   Prefer one paste? `00_setup_all_in_one.sql` = steps 1 + 2 + 3.

   **Alternative:** skip the SQL entirely. When the app connects to an empty database it offers a
   **Create tables** button that does steps 1–2 (and 3 if you tick the sample box).

4. First sign-in: username **admin**, password **ChangeMe2026!** — the app makes you choose a new one.

**Plan size.** The Filess.io free plan gives 10 MB per database, enough to try the app and train staff.
For live operation use a paid plan (more storage, daily backups, IP filtering — see section 7).

## 2. Install and connect the app

* **Windows 10/11:** run `ReserveMe-Setup-1.0.0.exe`.
* **macOS 12+:** open `ReserveMe-1.0.0-arm64.dmg` (Apple silicon) or `…-x86_64.dmg` (Intel) and drag
  ReserveMe to Applications.

On first start the **Connect to your database** window appears. Choose the database type, paste the
details from Filess.io, click **Test connection**, then **Save and continue**. The password is stored in
Windows Credential Manager or the macOS Keychain, never in a plain file (unless the computer has no
credential store). Change it later in **Settings ▸ This computer**.

## 3. First-day setup (as admin)

1. **Settings ▸ Property** — name, address, phone, tax registration, main currency (e.g. USD), second
   currency and rate (e.g. JMD 157 per USD), check-in/out times, footer for bills.
2. **Settings ▸ Taxes** — enter your real taxes (percent of room rate, or a fixed amount per room per
   night). The sample taxes are placeholders.
3. **Settings ▸ Room types**, then **Rooms** — your inventory.
4. **Settings ▸ Rates & seasons** — one row per room type × rate plan × season. Optional weekend price
   and minimum stay. Nights with no season use the room type's default rate.
5. **Settings ▸ Users** — one account per staff member with the right role (below). Never share logins.

| Role | Can use |
| --- | --- |
| Administrator | Everything, including users |
| General manager | Everything except users; manual rates, corrections, do-not-book list |
| Front desk | Tape chart, reservations, check-in/out, bills and payments, housekeeping, night audit |
| Reservations | Tape chart, reservations, guests |
| Housekeeping | Room status only (and tape chart to see arrivals) |
| Accounting / night audit | Bills, corrections, reports, night audit |

## 4. Daily routine

* **Overview** — today's arrivals, departures, in-house, occupancy, rooms to clean, next 14 nights.
* **Tape chart** — drag across empty nights to book; drag a bar to move room or dates; double-click to
  open. Unassigned bookings are listed on the right.
* **Front desk** — check in (prints the registration card), move rooms, check out (blocked until the bill
  is settled; early departures shorten the stay after confirmation).
* **Billing** — every unsettled bill. In a bill: add charges, take payments (main or second currency),
  refunds, corrections (a reversing line — nothing is ever deleted), print, issue numbered invoices.
  **Card numbers are never entered**: take the card on the bank terminal and type only its approval code.
* **Housekeeping** — select rooms, mark dirty / clean / inspected / out of order; print the sheet.
* **Night audit** (once each night) — posts room and tax charges, turns non-arrivals into no-shows,
  marks occupied rooms for cleaning and moves to the next business date. It refuses to run while a
  guest due out today is still checked in.
* **Reports** — monthly performance (occupancy, ADR, RevPAR, length of stay), daily occupancy and
  revenue, arrivals, departures, guest register (police report), cashier report, reservations made,
  cancellations. Print, save as PDF, or export to Excel.

Shortcuts (Cmd on Mac): **Ctrl+N** new reservation · **Ctrl+F** find reservation · **F5/Ctrl+R** refresh ·
**Ctrl+L** lock · **Ctrl+1…9** pages. Screens lock after 10 idle minutes.

## 5. How the app protects your data

* Passwords hashed with Argon2id; 5 wrong attempts lock an account for 15 minutes.
* Every booking, change, cancellation, payment, correction, room status change and sign-in is written
  to the audit log (**Settings ▸ Audit log**).
* Double bookings are blocked with row locks, tested with two desks booking the same room at the same
  instant on PostgreSQL and MySQL/MariaDB.
* Money is stored as exact decimals; bills are corrected only by reversing lines.
* Encrypted connections (SSL) are used when the server offers them; choose **Required** to insist.
* Logs (for support) are in the folder shown in **Settings ▸ This computer**.

## 6. Build from source

```bash
python3.12 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m reserveme                                          # run the app
python -m pytest -q tests                                    # 20 tests, run once per configured database
```

Run the tests against real servers too:
`RM_TEST_PG_URL=postgresql+psycopg://user:pw@host/db RM_TEST_MYSQL_URL=mysql+pymysql://user:pw@host/db pytest`
(use empty test databases — the tests drop and recreate tables).

**Installers.** Each must be built on its own operating system:

* Windows: `packaging\build_windows.bat` → `dist\installer\ReserveMe-Setup-1.0.0.exe`
  (needs Python 3.12 64-bit and Inno Setup 6).
* macOS: `bash packaging/build_macos.sh` → `dist/ReserveMe-1.0.0-<arch>.dmg` (run once on an Apple
  silicon Mac and once on an Intel Mac, or let GitHub build both).
* GitHub: push this folder to a repository and push a tag such as `v1.0.0`;
  `.github/workflows/build.yml` runs all tests on PostgreSQL 17 and MySQL 8, then builds the Windows
  installer and both macOS disk images as downloadable artifacts.

**Support check:** `ReserveMe --self-test --db <database-url>` verifies the installed app and database.

**Changing the schema:** edit `reserveme/models.py`, bump `SCHEMA_VERSION`, run
`python tools/generate_sql.py` to regenerate `sql/`, and ship an upgrade script for existing databases.

## 7. Before going live (checklist)

- [ ] Paid database plan with daily backups; download a backup weekly and keep a copy off-site.
- [ ] Turn on IP filtering at the database host so only the resort's internet address can connect.
- [ ] Use a dedicated database user for the app (not the owner account) once tables are created.
- [ ] Code-sign the installers (Windows certificate; Apple Developer ID + notarization — set
      `SIGN_CMD`, `MAC_SIGN_ID`, `MAC_NOTARY_PROFILE`) so Windows SmartScreen and macOS Gatekeeper
      don't warn staff.
- [ ] Enter real taxes and confirm the bill layout with your accountant.
- [ ] Train each role with the sample data, then clear it (fresh database) before go-live.
- [ ] Run the old and new process side by side for two weeks, comparing night-audit totals.
- [ ] Keep printed arrival / in-house lists each night for internet outages.

## 8. Known limits of version 1.0

* The app talks to the database directly. Anyone who obtains the database password could bypass the
  app's role rules, so protect it (section 7). A small server in between (planned for 2.0) removes this.
* Speed depends on the internet link to the database; each screen loads in a few queries.
* Not yet included: online booking engine, channel manager (Booking.com/Expedia sync), card payment
  gateway, email sending, group blocks, POS link, key-card encoders, dark theme.

## Project layout

```
reserveme/          app source
  models.py         tables (also generates the SQL)
  services/         business rules: reservations, pricing, front desk, billing, night audit, reports
  ui/               windows, pages and dialogs (PySide6)
sql/postgresql/     setup scripts for PostgreSQL
sql/mysql/          setup scripts for MySQL / MariaDB
tests/              automated tests
tools/              SQL generator, UI smoke and workflow tests
packaging/          PyInstaller spec, Windows installer, macOS build, icons
```
