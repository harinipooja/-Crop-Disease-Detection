# CareQueue — Hospital Appointment and Queue System

A small Flask application for patient appointment booking and live queue tracking, with a staff workspace for publishing schedules and managing appointments. The database is MySQL.

## Features

- Patient account registration and sign-in with hashed passwords.
- Staff sign-in and role-restricted schedule / queue management.
- Capacity-checked appointment booking, with one booking per patient per schedule.
- Patient queue position and appointment status.
- Staff controls to mark appointments as serving, completed, or cancelled.
- CSRF checks on all form submissions and parameterized database queries.
- Responsive HTML/CSS interface.

## Requirements

- Python 3.10+
- MySQL 8.0+

## Run locally

1. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

2. Install Python dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

3. Create the database and tables:

   ```powershell
   Get-Content .\schema.sql | mysql -u root -p
   ```

   Alternatively, open `schema.sql` in MySQL Workbench and execute the script.

4. Copy `.env.example` to `.env` and set your MySQL credentials and a unique `SECRET_KEY`:

   ```powershell
   Copy-Item .env.example .env
   ```

   Set `SECRET_KEY` to a long random value and `DB_PASSWORD` to the password for your MySQL user. The app creates a temporary random session key if `SECRET_KEY` is not set; sessions will expire when the app restarts.

5. Start the server:

   ```powershell
   python app.py
   ```

6. Open <http://127.0.0.1:5000>, create a patient account, and sign in.

## Run tests

The route and template smoke tests run with Python's standard library:

```powershell
python -m unittest discover -s tests -v
```

## Create a staff account

Register a regular account, then promote it from the MySQL console:

```sql
USE hospital_queue;
UPDATE users SET role = 'staff' WHERE email = 'your-staff-email@example.com';
```

Sign out and sign in again for the staff role to take effect. Public registration intentionally creates patient accounts only.

## Upgrade an existing database

If you created the tables with an earlier version of this project, remove the old one-booking-ever constraint so a patient can book again after cancelling:

```sql
USE hospital_queue;
ALTER TABLE appointments DROP INDEX uq_schedule_patient;
CREATE INDEX idx_schedule_patient ON appointments (schedule_id, patient_id, status);
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | Random per process | Flask session signing key. Set a stable long random value so sessions survive restarts. |
| `DB_HOST` | `localhost` | MySQL hostname |
| `DB_PORT` | `3306` | MySQL port |
| `DB_NAME` | `hospital_queue` | Database name |
| `DB_USER` | `root` | MySQL user |
| `DB_PASSWORD` | empty | MySQL password |
| `COOKIE_SECURE` | `false` | Set to `true` when served over HTTPS |
| `FLASK_DEBUG` | `false` | Enables Flask debug mode; keep disabled outside local development |

This project is a learning/demo starter. For production use, add HTTPS, database backups, rate limiting, operational monitoring, and an appropriate privacy/security review before handling real patient data.
