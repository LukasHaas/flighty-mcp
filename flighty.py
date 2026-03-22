"""Business logic for querying the Flighty local SQLite database."""

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

DEFAULT_DB_PATH = os.path.expanduser(
    "~/Library/Containers/com.flightyapp.flighty/Data/Documents/MainFlightyDatabase.db"
)

DB_PATH = os.environ.get("FLIGHTY_DB_PATH", DEFAULT_DB_PATH)


def _get_db() -> sqlite3.Connection:
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(
            f"Flighty database not found at {DB_PATH}. "
            "Make sure the Flighty app is installed."
        )
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
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
    """List the user's flights with optional filtering."""
    conn = _get_db()
    query = _FLIGHT_BASE_QUERY
    params: list[Any] = []

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
