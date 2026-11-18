"""Mini IT Helpdesk - a ticketing web app built with Flask and SQLite.

Users log IT problems as tickets; support staff triage them by priority,
move them through Open -> In progress -> Resolved, and add notes.

Run:
    pip install -r requirements.txt
    python app.py            # then open http://127.0.0.1:5000
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, flash, g, redirect, render_template, request, url_for

CATEGORIES = ["Hardware", "Software", "Network", "Account / Password", "Printer", "Other"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]
STATUSES = ["Open", "In progress", "Resolved"]

# Target response times (hours) per priority - a simple SLA.
SLA_HOURS = {"Critical": 4, "High": 8, "Medium": 24, "Low": 72}

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT NOT NULL,
    requester   TEXT NOT NULL,
    category    TEXT NOT NULL,
    priority    TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'Open',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id  INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    author     TEXT NOT NULL,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def create_app(db_path: str | Path = "helpdesk.db") -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "dev-only-change-me"  # used for flash messages
    app.config["DATABASE"] = str(db_path)

    # ---------- database helpers ----------
    def get_db() -> sqlite3.Connection:
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    with app.app_context():
        get_db().executescript(SCHEMA)

    def now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def is_overdue(ticket: sqlite3.Row) -> bool:
        if ticket["status"] == "Resolved":
            return False
        age = datetime.now() - datetime.fromisoformat(ticket["created_at"])
        return age.total_seconds() / 3600 > SLA_HOURS[ticket["priority"]]

    app.jinja_env.globals.update(is_overdue=is_overdue)

    # ---------- routes ----------
    @app.route("/")
    def index():
        status = request.args.get("status", "")
        priority = request.args.get("priority", "")
        search = request.args.get("q", "").strip()

        # Build the query safely with ? placeholders (prevents SQL injection).
        sql = "SELECT * FROM tickets WHERE 1=1"
        params: list[str] = []
        if status in STATUSES:
            sql += " AND status = ?"
            params.append(status)
        if priority in PRIORITIES:
            sql += " AND priority = ?"
            params.append(priority)
        if search:
            sql += " AND (title LIKE ? OR description LIKE ? OR requester LIKE ?)"
            params += [f"%{search}%"] * 3
        # Most urgent first, then oldest first.
        sql += """ ORDER BY CASE priority WHEN 'Critical' THEN 0 WHEN 'High' THEN 1
                   WHEN 'Medium' THEN 2 ELSE 3 END, created_at"""
        tickets = get_db().execute(sql, params).fetchall()

        counts = {s: 0 for s in STATUSES}
        for row in get_db().execute("SELECT status, COUNT(*) AS n FROM tickets GROUP BY status"):
            counts[row["status"]] = row["n"]
        all_open = get_db().execute("SELECT * FROM tickets WHERE status != 'Resolved'").fetchall()
        overdue = sum(1 for t in all_open if is_overdue(t))

        return render_template(
            "index.html", tickets=tickets, counts=counts, overdue=overdue,
            statuses=STATUSES, priorities=PRIORITIES,
            current={"status": status, "priority": priority, "q": search},
        )

    @app.route("/tickets/new", methods=["GET", "POST"])
    def new_ticket():
        if request.method == "POST":
            form = request.form
            errors = []
            for field in ("title", "description", "requester"):
                if not form.get(field, "").strip():
                    errors.append(f"{field.capitalize()} is required.")
            if form.get("category") not in CATEGORIES:
                errors.append("Choose a valid category.")
            if form.get("priority") not in PRIORITIES:
                errors.append("Choose a valid priority.")
            if errors:
                for e in errors:
                    flash(e, "error")
                return render_template("new.html", categories=CATEGORIES,
                                       priorities=PRIORITIES, form=form), 400

            db = get_db()
            cur = db.execute(
                """INSERT INTO tickets (title, description, requester, category, priority,
                                        status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'Open', ?, ?)""",
                (form["title"].strip(), form["description"].strip(), form["requester"].strip(),
                 form["category"], form["priority"], now(), now()),
            )
            db.commit()
            flash(f"Ticket #{cur.lastrowid} created.", "success")
            return redirect(url_for("ticket_detail", ticket_id=cur.lastrowid))

        return render_template("new.html", categories=CATEGORIES, priorities=PRIORITIES, form={})

    def load_ticket(ticket_id: int) -> sqlite3.Row:
        ticket = get_db().execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if ticket is None:
            abort(404)
        return ticket

    @app.route("/tickets/<int:ticket_id>")
    def ticket_detail(ticket_id: int):
        ticket = load_ticket(ticket_id)
        notes = get_db().execute(
            "SELECT * FROM notes WHERE ticket_id = ? ORDER BY created_at", (ticket_id,)
        ).fetchall()
        return render_template("detail.html", ticket=ticket, notes=notes,
                               statuses=STATUSES, sla=SLA_HOURS[ticket["priority"]])

    @app.route("/tickets/<int:ticket_id>/status", methods=["POST"])
    def update_status(ticket_id: int):
        load_ticket(ticket_id)
        status = request.form.get("status")
        if status not in STATUSES:
            abort(400)
        db = get_db()
        db.execute("UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?",
                   (status, now(), ticket_id))
        db.execute("INSERT INTO notes (ticket_id, author, body, created_at) VALUES (?, ?, ?, ?)",
                   (ticket_id, "System", f"Status changed to {status}.", now()))
        db.commit()
        flash(f"Ticket #{ticket_id} is now {status}.", "success")
        return redirect(url_for("ticket_detail", ticket_id=ticket_id))

    @app.route("/tickets/<int:ticket_id>/notes", methods=["POST"])
    def add_note(ticket_id: int):
        load_ticket(ticket_id)
        author = request.form.get("author", "").strip()
        body = request.form.get("body", "").strip()
        if not author or not body:
            flash("Name and note are both required.", "error")
        else:
            db = get_db()
            db.execute("INSERT INTO notes (ticket_id, author, body, created_at) VALUES (?, ?, ?, ?)",
                       (ticket_id, author, body, now()))
            db.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (now(), ticket_id))
            db.commit()
            flash("Note added.", "success")
        return redirect(url_for("ticket_detail", ticket_id=ticket_id))

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("404.html"), 404

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
