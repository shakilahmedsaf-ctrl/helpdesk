"""Tests for the helpdesk app. Run with: python -m unittest -v"""

import tempfile
import unittest
from pathlib import Path

from app import create_app


class HelpdeskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(Path(self.tmp.name) / "test.db")
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def create(self, **overrides):
        data = {"requester": "Sam", "title": "Printer jam", "description": "Paper stuck",
                "category": "Printer", "priority": "High"}
        data.update(overrides)
        return self.client.post("/tickets/new", data=data, follow_redirects=True)

    def test_home_page_loads(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"No tickets found", res.data)

    def test_create_ticket(self):
        res = self.create()
        self.assertIn(b"Ticket #1 created", res.data)
        self.assertIn(b"Printer jam", self.client.get("/").data)

    def test_missing_fields_are_rejected(self):
        res = self.client.post("/tickets/new", data={"title": "", "description": "", "requester": "",
                                                     "category": "Printer", "priority": "Low"})
        self.assertEqual(res.status_code, 400)
        self.assertIn(b"Title is required", res.data)

    def test_invalid_priority_is_rejected(self):
        res = self.create(priority="Urgent!!!")
        self.assertIn(b"Choose a valid priority", res.data)

    def test_status_change_adds_system_note(self):
        self.create()
        res = self.client.post("/tickets/1/status", data={"status": "Resolved"}, follow_redirects=True)
        self.assertIn(b"Status changed to Resolved", res.data)

    def test_add_note(self):
        self.create()
        res = self.client.post("/tickets/1/notes", data={"author": "Shakil", "body": "Cleared the jam"},
                               follow_redirects=True)
        self.assertIn(b"Cleared the jam", res.data)

    def test_filter_and_search(self):
        self.create(title="Wi-Fi down", category="Network", priority="Critical")
        self.create(title="Need Excel", category="Software", priority="Low")
        self.assertNotIn(b"Need Excel", self.client.get("/?priority=Critical").data)
        self.assertIn(b"Need Excel", self.client.get("/?q=excel").data)

    def test_search_is_safe_from_sql_injection(self):
        self.create()
        res = self.client.get("/?q=' OR 1=1 --")
        self.assertEqual(res.status_code, 200)
        self.assertNotIn(b"Printer jam", res.data)

    def test_missing_ticket_is_404(self):
        self.assertEqual(self.client.get("/tickets/999").status_code, 404)


if __name__ == "__main__":
    unittest.main()
