"""Fill the database with realistic demo tickets so the app has something to show.

Run:  python seed.py     (wipes and recreates helpdesk.db)
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from app import create_app

DB = Path("helpdesk.db")

# (title, description, requester, category, priority, status, hours_ago, notes)
DEMO = [
    ("Wi-Fi drops every few minutes", "Laptop keeps disconnecting from the office Wi-Fi since this morning.",
     "Priya (Finance)", "Network", "High", "In progress", 3,
     [("Shakil", "Router logs show DHCP lease errors. Restarted the router and renewed the lease.")]),
    ("Locked out of email", "Typed the wrong password too many times, account is locked.",
     "James (Sales)", "Account / Password", "Critical", "Open", 6, []),
    ("Printer on 2nd floor jammed", "Paper stuck in tray 2, shows error E-04.",
     "Fatima (HR)", "Printer", "Medium", "Resolved", 30,
     [("Shakil", "Cleared jam in tray 2, ran a test page - working.")]),
    ("Need Excel installed", "New starter needs Microsoft 365 apps on their laptop.",
     "Tom (Marketing)", "Software", "Low", "Open", 20, []),
    ("Monitor flickering", "Second screen flickers when the laptop is docked.",
     "Aisha (Design)", "Hardware", "Medium", "Open", 50, []),
    ("Suspicious email with attachment", "Got an email saying my parcel is held, with a .zip file attached. Didn't open it.",
     "Ben (Operations)", "Other", "High", "Resolved", 26,
     [("Shakil", "Confirmed phishing. Blocked sender domain and reminded the team not to open unknown attachments.")]),
]


def main():
    if DB.exists():
        DB.unlink()
    create_app(DB)  # creates the tables
    db = sqlite3.connect(DB)
    now = datetime.now()
    for title, desc, who, cat, pri, status, hours, notes in DEMO:
        created = (now - timedelta(hours=hours)).isoformat(timespec="seconds")
        cur = db.execute(
            """INSERT INTO tickets (title, description, requester, category, priority, status,
                                    created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, desc, who, cat, pri, status, created, created),
        )
        for author, body in notes:
            db.execute("INSERT INTO notes (ticket_id, author, body, created_at) VALUES (?, ?, ?, ?)",
                       (cur.lastrowid, author, body, created))
    db.commit()
    db.close()
    print(f"Seeded {len(DEMO)} demo tickets into {DB}.")


if __name__ == "__main__":
    main()
