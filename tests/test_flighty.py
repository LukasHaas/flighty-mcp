"""Tests against a throwaway database built from Flighty's real table schema
(tests/schema.sql: CREATE TABLE statements only, no data).

Run: uv run python -m unittest discover tests
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import flighty  # noqa: E402

SCHEMA = (Path(__file__).parent / "schema.sql").read_text()
OWNER = "owner-uuid"


class FixtureDB(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "flighty.db")
        conn = sqlite3.connect(self.db)
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO Account (id, rawKind, rawStatus, authToken, created, lastUpdated)"
            " VALUES (7, 'main', 'enabled', 'x', 0, 0)"
        )
        for code, tz in (("LHR", "Europe/London"), ("MEX", "America/Mexico_City")):
            conn.execute(
                "INSERT INTO Airport (id, iata, name, city, country, countryCode, latitude,"
                " longitude, timeZoneIdentifier, relevance, created, lastUpdated)"
                " VALUES (?, ?, ?, 'c', 'c', 'cc', 0, 0, ?, 0, 0, 0)",
                [code, code, code, tz],
            )
        conn.execute(
            "INSERT INTO Airline (id, iata, name, relevance, created, lastUpdated)"
            " VALUES ('BA', 'BA', 'British Airways', 0, 0, 0)"
        )
        conn.commit()
        conn.close()
        patcher = mock.patch.object(flighty, "DB_PATH", self.db)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def add_owner_flight(self, number: str, days_ahead: float) -> None:
        dep = int((datetime.now(timezone.utc) + timedelta(days=days_ahead)).timestamp())
        conn = sqlite3.connect(self.db)
        fid = f"f-{number}-{days_ahead}"
        conn.execute(
            "INSERT INTO Flight (id, number, departureAirportId, scheduledArrivalAirportId,"
            " actualArrivalAirportId, airlineId, isCancelled, hasOfficialData, distance,"
            " lastKnownDepartureDate, lastKnownArrivalDate, departureScheduleGateOriginal,"
            " arrivalScheduleGateOriginal, created, lastUpdated)"
            " VALUES (?, ?, 'LHR', 'MEX', 'MEX', 'BA', 0, '1', 0, ?, ?, ?, ?, 0, 0)",
            [fid, number, dep, dep + 40000, dep, dep + 40000],
        )
        conn.execute(
            "INSERT INTO UserFlight (accountId, userId, flightId, isRandom, isProUpgrade,"
            " isMyFlight, isArchived, importSource, created, lastUpdated)"
            " VALUES (7, ?, ?, 0, 0, 1, 0, 'EMAIL', 0, 0)",
            [OWNER, fid],
        )
        conn.commit()
        conn.close()


class ListFlightsTest(FixtureDB):
    def test_upcoming_is_soonest_first_and_says_when_capped(self):
        """1 Nov 2026: limit=10 newest-first cut off the 3 and 6 Nov Mexico legs, so
        they were reported missing. Upcoming must start with the next flight, and a
        capped list must say more exist."""
        for d in range(1, 13):
            self.add_owner_flight(f"{100 + d}", d)
        out = flighty.list_flights(upcoming_only=True, limit=10)
        flights = [f for f in out if "flight_number" in f]
        self.assertEqual(len(flights), 10)
        self.assertEqual(flights[0]["flight_number"], "101")
        self.assertIn("showing 10 of 12", out[-1]["note"])

    def test_no_note_when_everything_fits(self):
        self.add_owner_flight("201", 2)
        out = flighty.list_flights(upcoming_only=True, limit=10)
        self.assertEqual(len(out), 1)
        self.assertNotIn("note", out[0])


class AddFlightTest(FixtureDB):
    def test_inserts_with_the_owners_account_id(self):
        self.add_owner_flight("999", -30)
        date = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%d")
        out = flighty.add_flight("BA243", date, "LHR", "MEX", "10:00", "14:00")
        self.assertEqual(out["status"], "created")
        conn = sqlite3.connect(self.db)
        self.assertEqual(
            conn.execute("SELECT accountId FROM UserFlight WHERE flightId = ?", [out["flight_id"]]).fetchone()[0],
            7,
        )

    def test_existing_flight_same_number_and_day_is_not_duplicated(self):
        self.add_owner_flight("243", 5)
        dep = datetime.now(timezone.utc) + timedelta(days=5)
        out = flighty.add_flight("BA243", dep.strftime("%Y-%m-%d"), "LHR", "MEX")
        self.assertEqual(out["status"], "exists")
        conn = sqlite3.connect(self.db)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM Flight WHERE number = '243'").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
