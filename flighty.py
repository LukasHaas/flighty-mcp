"""Business logic for querying the Flighty local SQLite database."""

import json
import os
import re
import sqlite3
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any

DEFAULT_DB_PATH = os.path.expanduser(
    "~/Library/Containers/com.flightyapp.flighty/Data/Documents/MainFlightyDatabase.db"
)

DB_PATH = os.environ.get("FLIGHTY_DB_PATH", DEFAULT_DB_PATH)
AIRLABS_API_KEY = os.environ.get("AIRLABS_API_KEY", "")


def _get_db(readonly: bool = True) -> sqlite3.Connection:
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(
            f"Flighty database not found at {DB_PATH}. "
            "Make sure the Flighty app is installed."
        )
    mode = "ro" if readonly else "rw"
    conn = sqlite3.connect(f"file:{DB_PATH}?mode={mode}", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _ts_to_iso(ts: int | None) -> str | None:
    """Convert a Unix timestamp (seconds) to ISO 8601 string."""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _build_flight_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Build a clean flight dictionary from a joined query row."""
    d = dict(row)
    # Convert key timestamps to ISO
    for key in [
        "departureScheduleGateOriginal",
        "departureScheduleGateEstimated",
        "departureScheduleGateActual",
        "departureScheduleRunwayOriginal",
        "departureScheduleRunwayEstimated",
        "departureScheduleRunwayActual",
        "arrivalScheduleGateOriginal",
        "arrivalScheduleGateEstimated",
        "arrivalScheduleGateActual",
        "arrivalScheduleRunwayOriginal",
        "arrivalScheduleRunwayEstimated",
        "arrivalScheduleRunwayActual",
        "equipmentFirstFlightDate",
        "checkInScheduleOpen",
        "checkInScheduleClose",
        "departureScheduleGateInitial",
        "arrivalScheduleGateInitial",
    ]:
        if key in d and d[key] is not None:
            d[key] = _ts_to_iso(d[key])
    return d


# ---------------------------------------------------------------------------
# Flight queries
# ---------------------------------------------------------------------------

_FLIGHT_BASE_QUERY = """
SELECT
    f.id,
    f.number AS flight_number,
    al.name AS airline_name,
    al.iata AS airline_iata,
    dep.iata AS departure_airport_iata,
    dep.name AS departure_airport_name,
    dep.city AS departure_city,
    dep.country AS departure_country,
    dep.timeZoneIdentifier AS departure_timezone,
    f.departureTerminal AS departure_terminal,
    f.departureGate AS departure_gate,
    f.departureScheduleGateOriginal,
    f.departureScheduleGateEstimated,
    f.departureScheduleGateActual,
    f.departureScheduleRunwayOriginal,
    f.departureScheduleRunwayEstimated,
    f.departureScheduleRunwayActual,
    arr.iata AS arrival_airport_iata,
    arr.name AS arrival_airport_name,
    arr.city AS arrival_city,
    arr.country AS arrival_country,
    arr.timeZoneIdentifier AS arrival_timezone,
    f.arrivalTerminal AS arrival_terminal,
    f.arrivalGate AS arrival_gate,
    f.arrivalBaggageBelt AS arrival_baggage_belt,
    f.arrivalScheduleGateOriginal,
    f.arrivalScheduleGateEstimated,
    f.arrivalScheduleGateActual,
    f.arrivalScheduleRunwayOriginal,
    f.arrivalScheduleRunwayEstimated,
    f.arrivalScheduleRunwayActual,
    f.isCancelled AS is_cancelled,
    f.distance AS distance_km,
    f.equipmentTailNumber AS tail_number,
    f.equipmentModelName AS aircraft_model,
    f.equipmentManufacturer AS aircraft_manufacturer,
    f.equipmentPlaneName AS aircraft_name,
    f.equipmentCruisingSpeed AS cruising_speed_kmh,
    f.arrivalWeatherCondition AS arrival_weather,
    f.arrivalWeatherTemperature AS arrival_temp_c,
    f.delayForecastDelayMean AS delay_forecast_mean_min,
    f.delayForecastObservations AS delay_forecast_observations,
    f.delayForecastEarlyCount,
    f.delayForecastOntimeCount,
    f.delayForecastLate15Count,
    f.delayForecastLate30Count,
    f.delayForecastLate45Count,
    f.delayForecastCanceledCount,
    f.delayForecastDivertedCount,
    f.checkInScheduleOpen,
    f.checkInScheduleClose,
    t.seatNumber AS seat_number,
    t.seatPosition AS seat_position,
    t.cabinClass AS cabin_class,
    t.pnr AS booking_reference,
    t.flightReason AS flight_reason,
    uf.isArchived AS is_archived,
    uf.importSource AS import_source
FROM Flight f
JOIN Airport dep ON f.departureAirportId = dep.id
JOIN Airport arr ON f.scheduledArrivalAirportId = arr.id
JOIN Airline al ON f.airlineId = al.id
JOIN UserFlight uf ON f.id = uf.flightId
LEFT JOIN Ticket t ON f.id = t.flightId AND uf.userId = t.userId
WHERE uf.deleted IS NULL AND f.deleted IS NULL
"""


def list_flights(
    upcoming_only: bool = False,
    past_only: bool = False,
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List the owner's own flights (excludes friends' flights)."""
    conn = _get_db()
    owner_id = _get_owner_user_id(conn)
    query = _FLIGHT_BASE_QUERY + " AND uf.userId = ?"
    params: list[Any] = [owner_id]

    if not include_archived:
        query += " AND uf.isArchived = 0"

    now = int(datetime.now(timezone.utc).timestamp())
    if upcoming_only:
        query += " AND f.departureScheduleGateOriginal >= ?"
        params.append(now)
    elif past_only:
        query += " AND f.departureScheduleGateOriginal < ?"
        params.append(now)

    query += " ORDER BY f.departureScheduleGateOriginal DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [_build_flight_dict(r) for r in rows]


def list_friend_flights(
    friend_name: str | None = None,
    upcoming_only: bool = False,
    past_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List flights belonging to connected friends (excludes the owner's flights)."""
    conn = _get_db()
    owner_id = _get_owner_user_id(conn)

    query = _FLIGHT_BASE_QUERY.replace(
        "LEFT JOIN Ticket t ON f.id = t.flightId AND uf.userId = t.userId",
        "LEFT JOIN Ticket t ON f.id = t.flightId AND uf.userId = t.userId\n"
        "LEFT JOIN Profile p ON uf.userId = p.userId",
    )
    query += " AND uf.userId != ?"
    params: list[Any] = [owner_id]

    if friend_name:
        query += " AND (UPPER(p.fullName) LIKE UPPER(?) OR UPPER(p.firstName) LIKE UPPER(?))"
        params.extend([f"%{friend_name}%", f"%{friend_name}%"])

    now = int(datetime.now(timezone.utc).timestamp())
    if upcoming_only:
        query += " AND f.departureScheduleGateOriginal >= ?"
        params.append(now)
    elif past_only:
        query += " AND f.departureScheduleGateOriginal < ?"
        params.append(now)

    # Add friend name to output
    query = query.replace(
        "SELECT\n    f.id,",
        "SELECT\n    p.fullName AS friend_name,\n    f.id,",
    )

    query += " ORDER BY f.departureScheduleGateOriginal DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [_build_flight_dict(r) for r in rows]


def get_flight(flight_id: str | None = None, flight_number: str | None = None) -> dict[str, Any] | None:
    """Get a specific flight by ID or flight number (returns most recent match)."""
    conn = _get_db()
    query = _FLIGHT_BASE_QUERY

    if flight_id:
        query += " AND f.id = ?"
        params = [flight_id]
    elif flight_number:
        query += " AND UPPER(REPLACE(f.number, ' ', '')) = UPPER(REPLACE(?, ' ', ''))"
        query += " ORDER BY f.departureScheduleGateOriginal DESC LIMIT 1"
        params = [flight_number]
    else:
        return None

    row = conn.execute(query, params).fetchone()
    conn.close()
    return _build_flight_dict(row) if row else None


def search_flights(
    airline: str | None = None,
    departure_airport: str | None = None,
    arrival_airport: str | None = None,
    after: str | None = None,
    before: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search flights by airline, airports, or date range."""
    conn = _get_db()
    query = _FLIGHT_BASE_QUERY
    params: list[Any] = []

    if airline:
        query += " AND (UPPER(al.iata) = UPPER(?) OR UPPER(al.name) LIKE UPPER(?))"
        params.extend([airline, f"%{airline}%"])
    if departure_airport:
        query += " AND (UPPER(dep.iata) = UPPER(?) OR UPPER(dep.city) LIKE UPPER(?))"
        params.extend([departure_airport, f"%{departure_airport}%"])
    if arrival_airport:
        query += " AND (UPPER(arr.iata) = UPPER(?) OR UPPER(arr.city) LIKE UPPER(?))"
        params.extend([arrival_airport, f"%{arrival_airport}%"])
    if after:
        ts = int(datetime.fromisoformat(after).timestamp())
        query += " AND f.departureScheduleGateOriginal >= ?"
        params.append(ts)
    if before:
        ts = int(datetime.fromisoformat(before).timestamp())
        query += " AND f.departureScheduleGateOriginal <= ?"
        params.append(ts)

    query += " ORDER BY f.departureScheduleGateOriginal DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [_build_flight_dict(r) for r in rows]


def get_flight_status(flight_number: str) -> dict[str, Any] | None:
    """Get delay and status info for the most recent instance of a flight number."""
    flight = get_flight(flight_number=flight_number)
    if not flight:
        return None

    dep_orig = flight.get("departureScheduleGateOriginal")
    dep_est = flight.get("departureScheduleGateEstimated")
    arr_orig = flight.get("arrivalScheduleGateOriginal")
    arr_est = flight.get("arrivalScheduleGateEstimated")

    # Calculate delays
    dep_delay_min = None
    arr_delay_min = None
    if dep_orig and dep_est:
        try:
            d1 = datetime.fromisoformat(dep_orig)
            d2 = datetime.fromisoformat(dep_est)
            dep_delay_min = int((d2 - d1).total_seconds() / 60)
        except (ValueError, TypeError):
            pass
    if arr_orig and arr_est:
        try:
            d1 = datetime.fromisoformat(arr_orig)
            d2 = datetime.fromisoformat(arr_est)
            arr_delay_min = int((d2 - d1).total_seconds() / 60)
        except (ValueError, TypeError):
            pass

    # Determine status
    if flight.get("is_cancelled"):
        status = "cancelled"
    elif flight.get("departureScheduleGateActual") and flight.get("arrivalScheduleGateActual"):
        status = "landed"
    elif flight.get("departureScheduleGateActual"):
        status = "in_air"
    elif dep_delay_min and dep_delay_min > 15:
        status = "delayed"
    else:
        status = "scheduled"

    return {
        "flight_number": flight["flight_number"],
        "status": status,
        "is_cancelled": flight["is_cancelled"],
        "departure_airport": flight["departure_airport_iata"],
        "arrival_airport": flight["arrival_airport_iata"],
        "scheduled_departure": dep_orig,
        "estimated_departure": dep_est,
        "actual_departure": flight.get("departureScheduleGateActual"),
        "scheduled_arrival": arr_orig,
        "estimated_arrival": arr_est,
        "actual_arrival": flight.get("arrivalScheduleGateActual"),
        "departure_delay_minutes": dep_delay_min,
        "arrival_delay_minutes": arr_delay_min,
        "departure_gate": flight.get("departure_gate"),
        "arrival_gate": flight.get("arrival_gate"),
        "arrival_baggage_belt": flight.get("arrival_baggage_belt"),
        "arrival_weather": flight.get("arrival_weather"),
        "arrival_temp_c": flight.get("arrival_temp_c"),
        "delay_forecast_mean_min": flight.get("delay_forecast_mean_min"),
        "aircraft": flight.get("aircraft_model"),
        "tail_number": flight.get("tail_number"),
    }


def get_delay_forecast(flight_number: str) -> dict[str, Any] | None:
    """Get historical delay statistics for a flight number."""
    flight = get_flight(flight_number=flight_number)
    if not flight:
        return None

    obs = flight.get("delay_forecast_observations") or 0
    if obs == 0:
        return {
            "flight_number": flight["flight_number"],
            "message": "No delay forecast data available for this flight.",
        }

    return {
        "flight_number": flight["flight_number"],
        "route": f"{flight['departure_airport_iata']} -> {flight['arrival_airport_iata']}",
        "observations": obs,
        "mean_delay_minutes": flight.get("delay_forecast_mean_min"),
        "early_pct": round(100 * (flight.get("delayForecastEarlyCount") or 0) / obs, 1),
        "ontime_pct": round(100 * (flight.get("delayForecastOntimeCount") or 0) / obs, 1),
        "late_15_pct": round(100 * (flight.get("delayForecastLate15Count") or 0) / obs, 1),
        "late_30_pct": round(100 * (flight.get("delayForecastLate30Count") or 0) / obs, 1),
        "late_45_pct": round(100 * (flight.get("delayForecastLate45Count") or 0) / obs, 1),
        "cancelled_pct": round(100 * (flight.get("delayForecastCanceledCount") or 0) / obs, 1),
        "diverted_pct": round(100 * (flight.get("delayForecastDivertedCount") or 0) / obs, 1),
    }


# ---------------------------------------------------------------------------
# Airport & Airline queries
# ---------------------------------------------------------------------------


def search_airports(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search airports by IATA code, city, or name."""
    conn = _get_db()
    rows = conn.execute(
        """
        SELECT id, name, iata, icao, city, country, countryCode, timeZoneIdentifier,
               latitude, longitude, website
        FROM Airport
        WHERE deleted IS NULL
          AND (UPPER(iata) = UPPER(?)
               OR UPPER(icao) = UPPER(?)
               OR UPPER(name) LIKE UPPER(?)
               OR UPPER(city) LIKE UPPER(?))
        ORDER BY relevance DESC
        LIMIT ?
        """,
        [query, query, f"%{query}%", f"%{query}%", limit],
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_airlines(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search airlines by IATA code, name, or alliance."""
    conn = _get_db()
    rows = conn.execute(
        """
        SELECT id, name, iata, icao, alliance, website, callsign, formattedPhone
        FROM Airline
        WHERE deleted IS NULL
          AND (UPPER(iata) = UPPER(?)
               OR UPPER(icao) = UPPER(?)
               OR UPPER(name) LIKE UPPER(?)
               OR UPPER(alliance) LIKE UPPER(?))
        ORDER BY relevance DESC
        LIMIT ?
        """,
        [query, query, f"%{query}%", f"%{query}%", limit],
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


def get_flight_stats(year: int | None = None) -> dict[str, Any]:
    """Get aggregate statistics about the user's flights."""
    conn = _get_db()
    where = "WHERE uf.deleted IS NULL AND f.deleted IS NULL AND uf.isArchived = 0"
    params: list[Any] = []

    if year:
        start = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp())
        end = int(datetime(year + 1, 1, 1, tzinfo=timezone.utc).timestamp())
        where += " AND f.departureScheduleGateOriginal >= ? AND f.departureScheduleGateOriginal < ?"
        params.extend([start, end])

    row = conn.execute(
        f"""
        SELECT
            COUNT(*) as total_flights,
            SUM(f.distance) as total_distance_km,
            COUNT(DISTINCT dep.id) as unique_departure_airports,
            COUNT(DISTINCT arr.id) as unique_arrival_airports,
            COUNT(DISTINCT al.id) as unique_airlines,
            COUNT(DISTINCT dep.country) + COUNT(DISTINCT arr.country) as approximate_countries,
            SUM(CASE WHEN f.isCancelled THEN 1 ELSE 0 END) as cancelled_flights,
            AVG(f.distance) as avg_distance_km
        FROM Flight f
        JOIN Airport dep ON f.departureAirportId = dep.id
        JOIN Airport arr ON f.scheduledArrivalAirportId = arr.id
        JOIN Airline al ON f.airlineId = al.id
        JOIN UserFlight uf ON f.id = uf.flightId
        {where}
        """,
        params,
    ).fetchone()

    # Top airlines
    top_airlines = conn.execute(
        f"""
        SELECT al.name, al.iata, COUNT(*) as flight_count
        FROM Flight f
        JOIN Airline al ON f.airlineId = al.id
        JOIN UserFlight uf ON f.id = uf.flightId
        {where}
        GROUP BY al.id
        ORDER BY flight_count DESC
        LIMIT 5
        """,
        params,
    ).fetchall()

    # Top routes
    top_routes = conn.execute(
        f"""
        SELECT dep.iata || ' -> ' || arr.iata as route, COUNT(*) as flight_count
        FROM Flight f
        JOIN Airport dep ON f.departureAirportId = dep.id
        JOIN Airport arr ON f.scheduledArrivalAirportId = arr.id
        JOIN UserFlight uf ON f.id = uf.flightId
        {where}
        GROUP BY dep.id, arr.id
        ORDER BY flight_count DESC
        LIMIT 5
        """,
        params,
    ).fetchall()

    conn.close()

    stats = dict(row)
    if stats.get("total_distance_km"):
        stats["total_distance_miles"] = round(stats["total_distance_km"] * 0.621371)
        stats["avg_distance_miles"] = round((stats.get("avg_distance_km") or 0) * 0.621371)
        stats["earth_circumnavigations"] = round(stats["total_distance_km"] / 40075, 2)

    stats["top_airlines"] = [dict(r) for r in top_airlines]
    stats["top_routes"] = [dict(r) for r in top_routes]
    stats["year"] = year or "all_time"

    return stats


def _parse_flight_number(flight_code: str) -> tuple[str, str]:
    """Parse a flight code like 'UA194' into (airline_iata, number).

    Handles formats: 'UA194', 'UA 194', 'UA-194'.
    """
    code = flight_code.strip().upper().replace("-", "").replace(" ", "")
    m = re.match(r"^([A-Z]{2}|\d[A-Z]|[A-Z]\d)(\d+)$", code)
    if not m:
        raise ValueError(
            f"Invalid flight code '{flight_code}'. "
            "Expected format like 'UA194' or 'BA930'."
        )
    return m.group(1), code


def _lookup_airline(conn: sqlite3.Connection, iata: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id, name, iata FROM Airline WHERE UPPER(iata) = ? AND deleted IS NULL LIMIT 1",
        [iata.upper()],
    ).fetchone()
    if not row:
        raise ValueError(f"Airline with IATA code '{iata}' not found in Flighty database.")
    return dict(row)


def _lookup_airport(conn: sqlite3.Connection, code: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id, iata, name FROM Airport WHERE UPPER(iata) = ? AND deleted IS NULL LIMIT 1",
        [code.upper()],
    ).fetchone()
    if not row:
        raise ValueError(f"Airport with IATA code '{code}' not found in Flighty database.")
    return dict(row)


def _get_owner_user_id(conn: sqlite3.Connection) -> str:
    """Get the local Flighty owner's user ID.

    The owner appears in ConnectedFriendRelationship as both sender and receiver
    more than any other user, but may not have a Profile entry with a name.
    Fallback: the userId with the most UserFlight rows.
    """
    row = conn.execute(
        """
        SELECT userId, COUNT(*) as cnt FROM (
            SELECT senderUserId AS userId FROM ConnectedFriendRelationship WHERE deleted IS NULL
            UNION ALL
            SELECT receiverUserId AS userId FROM ConnectedFriendRelationship WHERE deleted IS NULL
        )
        GROUP BY userId ORDER BY cnt DESC LIMIT 1
        """
    ).fetchone()
    if row:
        return row[0]
    # Fallback: user with the most flights
    row = conn.execute(
        "SELECT userId, COUNT(*) as cnt FROM UserFlight WHERE deleted IS NULL GROUP BY userId ORDER BY cnt DESC LIMIT 1"
    ).fetchone()
    if not row:
        raise RuntimeError("Could not determine Flighty user ID.")
    return row[0]


def _lookup_flight_route(flight_iata: str) -> dict[str, str] | None:
    """Look up flight route info from AirLabs API.

    Returns dict with dep_iata, arr_iata, dep_time, arr_time or None on failure.
    """
    if not AIRLABS_API_KEY:
        return None
    try:
        url = f"https://airlabs.co/api/v9/flight?flight_iata={flight_iata}&api_key={AIRLABS_API_KEY}"
        req = urllib.request.Request(url, headers={"User-Agent": "flighty-mcp/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        r = data.get("response")
        if r and r.get("dep_iata") and r.get("arr_iata"):
            return {
                "dep_iata": r["dep_iata"],
                "arr_iata": r["arr_iata"],
                "dep_time": r.get("dep_time"),
                "arr_time": r.get("arr_time"),
            }
    except Exception:
        pass
    return None


def add_flight(
    flight_code: str,
    date: str,
    departure_airport: str | None = None,
    arrival_airport: str | None = None,
    departure_time: str | None = None,
    arrival_time: str | None = None,
    seat_number: str | None = None,
    cabin_class: str | None = None,
    booking_reference: str | None = None,
) -> dict[str, Any]:
    """Add a flight to the Flighty database.

    Args:
        flight_code: Flight code (e.g. 'UA194', 'BA930').
        date: Departure date in YYYY-MM-DD format.
        departure_airport: Departure airport IATA code (e.g. 'SFO'). If omitted, looked up via AirLabs API.
        arrival_airport: Arrival airport IATA code (e.g. 'LHR'). If omitted, looked up via AirLabs API.
        departure_time: Optional departure time in HH:MM format (24h, local time). Defaults to '00:00'.
        arrival_time: Optional arrival time in HH:MM format (24h, local time). Defaults to departure + 3h.
        seat_number: Optional seat number (e.g. '12A').
        cabin_class: Optional cabin class (e.g. 'economy', 'business', 'first').
        booking_reference: Optional PNR/booking reference.

    Returns:
        A dictionary with the created flight details.
    """
    airline_iata, flight_number = _parse_flight_number(flight_code)

    # If airports not provided, try AirLabs API lookup
    if not departure_airport or not arrival_airport:
        route = _lookup_flight_route(flight_number)
        if route:
            departure_airport = departure_airport or route["dep_iata"]
            arrival_airport = arrival_airport or route["arr_iata"]
            if not departure_time and route.get("dep_time"):
                # dep_time format: "2021-07-14 19:53"
                try:
                    departure_time = route["dep_time"].split(" ")[1][:5]
                except (IndexError, TypeError):
                    pass
            if not arrival_time and route.get("arr_time"):
                try:
                    arrival_time = route["arr_time"].split(" ")[1][:5]
                except (IndexError, TypeError):
                    pass
        if not departure_airport or not arrival_airport:
            raise ValueError(
                "Could not determine airports. Provide departure_airport and arrival_airport, "
                "or set the AIRLABS_API_KEY environment variable for automatic lookup."
            )

    conn = _get_db(readonly=False)
    try:
        airline = _lookup_airline(conn, airline_iata)
        dep_airport = _lookup_airport(conn, departure_airport)
        arr_airport = _lookup_airport(conn, arrival_airport)
        user_id = _get_owner_user_id(conn)

        # Parse departure datetime
        dep_time = departure_time or "00:00"
        dep_dt = datetime.fromisoformat(f"{date}T{dep_time}:00")
        dep_ts = int(dep_dt.timestamp())

        # Parse or estimate arrival datetime
        if arrival_time:
            arr_dt = datetime.fromisoformat(f"{date}T{arrival_time}:00")
            # If arrival is before departure, assume next day
            if arr_dt <= dep_dt:
                from datetime import timedelta
                arr_dt += timedelta(days=1)
            arr_ts = int(arr_dt.timestamp())
        else:
            arr_ts = dep_ts + 3 * 3600  # default: 3 hours later

        now_ts = int(datetime.now(timezone.utc).timestamp())
        flight_id = str(uuid.uuid4())

        # Insert Flight row
        conn.execute(
            """
            INSERT INTO Flight (
                id, number, departureAirportId, scheduledArrivalAirportId,
                actualArrivalAirportId, airlineId, isCancelled, hasOfficialData,
                distance, lastKnownDepartureDate, lastKnownArrivalDate,
                departureScheduleGateOriginal, arrivalScheduleGateOriginal,
                created, lastUpdated
            ) VALUES (?, ?, ?, ?, ?, ?, 0, '0', 0, ?, ?, ?, ?, ?, ?)
            """,
            [
                flight_id, flight_number, dep_airport["id"], arr_airport["id"],
                arr_airport["id"], airline["id"],
                dep_ts, arr_ts, dep_ts, arr_ts,
                now_ts, now_ts,
            ],
        )

        # Insert UserFlight row
        conn.execute(
            """
            INSERT INTO UserFlight (
                userId, flightId, isRandom, isProUpgrade, isMyFlight,
                isArchived, importSource, lastUpdated, created
            ) VALUES (?, ?, 0, 0, 1, 0, 'MCP', ?, ?)
            """,
            [user_id, flight_id, now_ts, now_ts],
        )

        # Optionally insert Ticket row
        if seat_number or cabin_class or booking_reference:
            conn.execute(
                """
                INSERT INTO Ticket (
                    userId, flightId, seatNumber, seatPosition, cabinClass,
                    pnr, lastUpdated
                ) VALUES (?, ?, ?, NULL, ?, ?, ?)
                """,
                [user_id, flight_id, seat_number, cabin_class, booking_reference, now_ts],
            )

        conn.commit()

        return {
            "flight_id": flight_id,
            "flight_number": flight_number,
            "airline": airline["name"],
            "departure_airport": dep_airport["iata"],
            "arrival_airport": arr_airport["iata"],
            "departure_time": _ts_to_iso(dep_ts),
            "arrival_time": _ts_to_iso(arr_ts),
            "seat_number": seat_number,
            "cabin_class": cabin_class,
            "booking_reference": booking_reference,
            "status": "created",
        }
    finally:
        conn.close()


def get_connections() -> list[dict[str, Any]]:
    """Get flight connections (layovers) for the user."""
    conn = _get_db()
    rows = conn.execute(
        """
        SELECT
            c.id,
            f1.number AS departing_flight,
            dep1.iata AS from_airport,
            arr1.iata AS connection_airport,
            f2.number AS arriving_flight,
            arr2.iata AS to_airport,
            f1.arrivalScheduleGateOriginal AS arrival_time,
            f2.departureScheduleGateOriginal AS departure_time,
            c.mctMinutes AS min_connection_time_min,
            wait.name AS connection_airport_name
        FROM Connection c
        JOIN Flight f1 ON c.departingFlightId = f1.id
        JOIN Flight f2 ON c.arrivingFlightId = f2.id
        JOIN Airport dep1 ON f1.departureAirportId = dep1.id
        JOIN Airport arr1 ON f1.scheduledArrivalAirportId = arr1.id
        JOIN Airport arr2 ON f2.scheduledArrivalAirportId = arr2.id
        JOIN Airport wait ON c.waitingAirportId = wait.id
        WHERE c.deleted IS NULL
        ORDER BY f1.departureScheduleGateOriginal DESC
        """,
    ).fetchall()
    conn.close()

    results = []
    for r in rows:
        d = dict(r)
        arr_ts = d.get("arrival_time")
        dep_ts = d.get("departure_time")
        if arr_ts and dep_ts:
            d["layover_minutes"] = (dep_ts - arr_ts) // 60
            d["arrival_time"] = _ts_to_iso(arr_ts)
            d["departure_time"] = _ts_to_iso(dep_ts)
        results.append(d)
    return results
