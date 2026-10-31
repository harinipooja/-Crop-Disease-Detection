import os
import secrets
from datetime import date, datetime
from functools import wraps

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY") or secrets.token_urlsafe(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",
)


@app.errorhandler(mysql.connector.Error)
def handle_database_error(error):
    app.logger.exception("Database request failed: %s", error)
    if error.errno == 1045:
        detail = (
            "MySQL rejected the configured account. Check DB_USER and DB_PASSWORD "
            "in your local .env file, then restart CareQueue."
        )
    elif error.errno == 1049:
        detail = (
            "The configured MySQL database does not exist. Run schema.sql in "
            "MySQL Workbench using your local MySQL connection, then reload."
        )
    elif error.errno == 2003:
        detail = "MySQL is not accepting connections. Start the MySQL80 Windows service and reload."
    else:
        detail = (
            "Check that MySQL is running, the schema is installed, and your "
            "DB_HOST, DB_USER, DB_PASSWORD, and DB_NAME settings are correct."
        )
    return render_template("service_unavailable.html", detail=detail), 503


def get_db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "hospital_queue"),
    )


def login_required(role=None):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("user_id"):
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


@app.before_request
def protect_post_requests():
    if request.method == "POST":
        supplied = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not expected or not secrets.compare_digest(supplied, expected):
            abort(400, description="Invalid or missing form token. Reload the page and try again.")


@app.context_processor
def inject_template_values():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return {
        "current_user": session.get("name"),
        "current_role": session.get("role"),
        "now_date": date.today().isoformat(),
    }


@app.get("/")
def index():
    if session.get("role") == "staff":
        return redirect(url_for("staff_dashboard"))
    if session.get("role") == "patient":
        return redirect(url_for("patient_dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if len(name) < 2 or len(name) > 100 or "@" not in email:
            flash("Enter a valid name and email address.", "error")
        elif len(password) < 8:
            flash("Password must contain at least 8 characters.", "error")
        else:
            db = get_db()
            cursor = db.cursor()
            try:
                cursor.execute(
                    "INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, 'patient')",
                    (name, email, generate_password_hash(password)),
                )
                db.commit()
            except mysql.connector.IntegrityError:
                db.rollback()
                flash("An account with that email already exists.", "error")
            else:
                flash("Your patient account is ready. Please sign in.", "success")
                return redirect(url_for("login"))
            finally:
                cursor.close()
                db.close()
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        db = get_db()
        cursor = db.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT id, name, email, password_hash, role FROM users WHERE email = %s",
                (email,),
            )
            user = cursor.fetchone()
        finally:
            cursor.close()
            db.close()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]
            session["csrf_token"] = secrets.token_urlsafe(32)
            return redirect(url_for("index"))
        flash("Email or password is incorrect.", "error")
    return render_template("login.html")


@app.post("/logout")
@login_required()
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("login"))


@app.get("/patient")
@login_required("patient")
def patient_dashboard():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT s.id, s.title, s.doctor_name, s.schedule_date,
                      TIME_FORMAT(s.start_time, '%h:%i %p') AS start_label,
                      TIME_FORMAT(s.end_time, '%h:%i %p') AS end_label, s.capacity,
                      s.capacity - COUNT(a.id) AS spots_left
               FROM schedules s
               LEFT JOIN appointments a
                 ON a.schedule_id = s.id AND a.status IN ('waiting', 'serving', 'completed')
               WHERE s.schedule_date > %s
                  OR (s.schedule_date = %s AND s.start_time > %s)
               GROUP BY s.id
               HAVING spots_left > 0
               ORDER BY s.schedule_date, s.start_time""",
            (date.today(), date.today(), datetime.now().time()),
        )
        schedules = cursor.fetchall()
        cursor.execute(
            """SELECT a.id AS appointment_id, a.status, a.created_at,
                      s.title, s.doctor_name, s.schedule_date,
                      TIME_FORMAT(s.start_time, '%h:%i %p') AS start_label,
                      (SELECT COUNT(*) FROM appointments earlier
                       WHERE earlier.schedule_id = a.schedule_id
                         AND earlier.status IN ('waiting', 'serving')
                         AND (earlier.created_at < a.created_at OR
                             (earlier.created_at = a.created_at AND earlier.id <= a.id))) AS queue_position
               FROM appointments a
               JOIN schedules s ON s.id = a.schedule_id
               WHERE a.patient_id = %s
               ORDER BY s.schedule_date DESC, s.start_time DESC, a.id DESC""",
            (session["user_id"],),
        )
        appointments = cursor.fetchall()
    finally:
        cursor.close()
        db.close()
    return render_template("patient_dashboard.html", schedules=schedules, appointments=appointments)


@app.post("/patient/book/<int:schedule_id>")
@login_required("patient")
def book_appointment(schedule_id):
    db = get_db()
    cursor = db.cursor()
    try:
        db.start_transaction()
        cursor.execute(
            "SELECT capacity, schedule_date, start_time FROM schedules WHERE id = %s FOR UPDATE",
            (schedule_id,),
        )
        schedule = cursor.fetchone()
        if not schedule or schedule[1] < date.today() or (
            schedule[1] == date.today() and schedule[2] <= datetime.now().time()
        ):
            db.rollback()
            flash("That appointment schedule is no longer available.", "error")
            return redirect(url_for("patient_dashboard"))
        cursor.execute(
            """SELECT id FROM appointments
               WHERE schedule_id = %s AND patient_id = %s
                 AND status IN ('waiting', 'serving', 'completed')
               FOR UPDATE""",
            (schedule_id, session["user_id"]),
        )
        if cursor.fetchone():
            db.rollback()
            flash("You already have an active appointment in this schedule.", "error")
            return redirect(url_for("patient_dashboard"))
        cursor.execute(
            """SELECT COUNT(*) FROM appointments
               WHERE schedule_id = %s AND status IN ('waiting', 'serving', 'completed')""",
            (schedule_id,),
        )
        booked = cursor.fetchone()[0]
        if booked >= schedule[0]:
            db.rollback()
            flash("This schedule has reached capacity.", "error")
            return redirect(url_for("patient_dashboard"))
        cursor.execute(
            "INSERT INTO appointments (schedule_id, patient_id, status) VALUES (%s, %s, 'waiting')",
            (schedule_id, session["user_id"]),
        )
        db.commit()
        flash("Appointment booked. Your queue position is now available below.", "success")
    except mysql.connector.IntegrityError:
        db.rollback()
        flash("You already have an appointment in this schedule.", "error")
    finally:
        cursor.close()
        db.close()
    return redirect(url_for("patient_dashboard"))


@app.post("/patient/cancel/<int:appointment_id>")
@login_required("patient")
def cancel_appointment(appointment_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute(
            """UPDATE appointments SET status = 'cancelled'
               WHERE id = %s AND patient_id = %s AND status = 'waiting'""",
            (appointment_id, session["user_id"]),
        )
        db.commit()
        if cursor.rowcount:
            flash("Appointment cancelled.", "success")
        else:
            flash("That appointment cannot be cancelled.", "error")
    finally:
        cursor.close()
        db.close()
    return redirect(url_for("patient_dashboard"))


@app.get("/staff")
@login_required("staff")
def staff_dashboard():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT s.id, s.title, s.doctor_name, s.schedule_date,
                      TIME_FORMAT(s.start_time, '%h:%i %p') AS start_label,
                      TIME_FORMAT(s.end_time, '%h:%i %p') AS end_label,
                      s.capacity, COUNT(a.id) AS booked
               FROM schedules s
               LEFT JOIN appointments a
                 ON a.schedule_id = s.id AND a.status IN ('waiting', 'serving', 'completed')
               GROUP BY s.id
               ORDER BY s.schedule_date DESC, s.start_time DESC"""
        )
        schedules = cursor.fetchall()
        cursor.execute(
            """SELECT a.id AS appointment_id, a.status, a.created_at,
                      u.name AS patient_name, u.email AS patient_email,
                      s.title, s.doctor_name, s.schedule_date,
                      TIME_FORMAT(s.start_time, '%h:%i %p') AS start_label,
                      (SELECT COUNT(*) FROM appointments earlier
                       WHERE earlier.schedule_id = a.schedule_id
                         AND earlier.status IN ('waiting', 'serving')
                         AND (earlier.created_at < a.created_at OR
                             (earlier.created_at = a.created_at AND earlier.id <= a.id))) AS queue_position
               FROM appointments a
               JOIN users u ON u.id = a.patient_id
               JOIN schedules s ON s.id = a.schedule_id
               WHERE s.schedule_date >= %s AND a.status IN ('waiting', 'serving')
               ORDER BY s.schedule_date, s.start_time, a.created_at, a.id""",
            (date.today(),),
        )
        queue = cursor.fetchall()
    finally:
        cursor.close()
        db.close()
    return render_template("staff_dashboard.html", schedules=schedules, queue=queue)


@app.post("/staff/schedules")
@login_required("staff")
def create_schedule():
    title = request.form.get("title", "").strip()
    doctor_name = request.form.get("doctor_name", "").strip()
    schedule_date = request.form.get("schedule_date", "")
    start_time = request.form.get("start_time", "")
    end_time = request.form.get("end_time", "")
    try:
        parsed_date = date.fromisoformat(schedule_date)
        parsed_start = datetime.strptime(start_time, "%H:%M").time()
        parsed_end = datetime.strptime(end_time, "%H:%M").time()
        capacity = int(request.form.get("capacity", "0"))
        valid = (
            len(title) > 0
            and len(title) <= 120
            and len(doctor_name) > 0
            and len(doctor_name) <= 100
            and parsed_date >= date.today()
            and (parsed_date > date.today() or parsed_start > datetime.now().time())
            and parsed_start < parsed_end
            and 1 <= capacity <= 500
        )
    except (ValueError, TypeError):
        valid = False
    if not valid:
        flash("Enter a future schedule, valid time range, and capacity (1–500).", "error")
        return redirect(url_for("staff_dashboard"))
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute(
            """INSERT INTO schedules
               (title, doctor_name, schedule_date, start_time, end_time, capacity, created_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (title, doctor_name, schedule_date, start_time, end_time, capacity, session["user_id"]),
        )
        db.commit()
        flash("Schedule created.", "success")
    finally:
        cursor.close()
        db.close()
    return redirect(url_for("staff_dashboard"))


@app.post("/staff/appointments/<int:appointment_id>/status")
@login_required("staff")
def update_appointment_status(appointment_id):
    status = request.form.get("status", "")
    if status not in {"serving", "completed", "cancelled"}:
        abort(400, description="Unsupported appointment status.")
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute(
            "UPDATE appointments SET status = %s WHERE id = %s AND status IN ('waiting', 'serving')",
            (status, appointment_id),
        )
        db.commit()
        if cursor.rowcount:
            flash("Queue status updated.", "success")
        else:
            flash("This appointment is no longer active.", "error")
    finally:
        cursor.close()
        db.close()
    return redirect(url_for("staff_dashboard"))


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
