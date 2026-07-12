"""Render Flighty query results as human-readable plain text."""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


def _fmt_dt(iso: str | None, tz_name: str | None = None) -> str | None:
    """Format an ISO 8601 UTC timestamp as e.g. 'Wed Apr 15 2026, 14:30 PDT'.

    If an IANA timezone name is given, the time is shown in that zone
    (i.e. the airport's local time); otherwise it stays in UTC.
    """
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return str(iso)
    if tz_name:
        try:
            dt = dt.astimezone(ZoneInfo(tz_name))
        except Exception:
            pass
    return dt.strftime("%a %b %d %Y, %H:%M %Z")


def _minutes_between(iso_from: str, iso_to: str) -> int | None:
    try:
        d1 = datetime.fromisoformat(iso_from)
        d2 = datetime.fromisoformat(iso_to)
    except (ValueError, TypeError):
        return None
    return int((d2 - d1).total_seconds() / 60)


def _fmt_delay(minutes: int) -> str:
    if minutes > 0:
        return f"{minutes} min late"
    if minutes < 0:
        return f"{-minutes} min early"
    return "on time"


def _fmt_duration(minutes: int) -> str:
    hours, mins = divmod(abs(int(minutes)), 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


def _schedule_line(label: str, flight: dict[str, Any], side: str, tz_name: str | None) -> str | None:
    """Build a 'Departs: ...' / 'Arrives: ...' line with delay info and gate."""
    orig = flight.get(f"{side}ScheduleGateOriginal")
    est = flight.get(f"{side}ScheduleGateEstimated")
    actual = flight.get(f"{side}ScheduleGateActual")
    shown = orig or est or actual
    if not shown:
        return None
    line = f"{label} {_fmt_dt(shown, tz_name)}"
    best = actual or est
    if orig and best:
        diff = _minutes_between(orig, best)
        if diff is not None and diff != 0:
            kind = "actual" if actual else "estimated"
            line += f" ({kind}: {_fmt_dt(best, tz_name)}, {_fmt_delay(diff)})"
        elif actual:
            line += " (on time)"
    extras = []
    terminal = flight.get(f"{'departure' if side == 'departure' else 'arrival'}_terminal")
    gate = flight.get(f"{'departure' if side == 'departure' else 'arrival'}_gate")
    if terminal:
        extras.append(f"Terminal {terminal}")
    if gate:
        extras.append(f"Gate {gate}")
    if extras:
        line += " — " + ", ".join(extras)
    return line


def _flight_block(flight: dict[str, Any]) -> str:
    """Render one flight as a short multi-line text block."""
    dep_tz = flight.get("departure_timezone")
    arr_tz = flight.get("arrival_timezone")

    header = (
        f"{flight.get('flight_number')} — {flight.get('airline_name')} · "
        f"{flight.get('departure_airport_iata')} → {flight.get('arrival_airport_iata')}"
    )
    friend = flight.get("friend_name")
    if friend:
        header += f" (friend: {friend})"
    if flight.get("is_cancelled"):
        header += " [CANCELLED]"

    lines = [header]
    lines.append(
        f"  Route: {flight.get('departure_city')}, {flight.get('departure_country')}"
        f" → {flight.get('arrival_city')}, {flight.get('arrival_country')}"
    )
    dep_line = _schedule_line("  Departs:", flight, "departure", dep_tz)
    if dep_line:
        lines.append(dep_line)
    arr_line = _schedule_line("  Arrives:", flight, "arrival", arr_tz)
    if arr_line:
        lines.append(arr_line)

    ticket = []
    if flight.get("seat_number"):
        seat = f"Seat {flight['seat_number']}"
        if flight.get("seat_position"):
            seat += f" ({flight['seat_position']})"
        ticket.append(seat)
    if flight.get("cabin_class"):
        ticket.append(f"Cabin: {flight['cabin_class']}")
    if flight.get("booking_reference"):
        ticket.append(f"Booking ref: {flight['booking_reference']}")
    if ticket:
        lines.append("  " + " · ".join(ticket))

    return "\n".join(lines)


def format_flight_list(flights: list[dict[str, Any]], empty_message: str = "No flights found.") -> str:
    """Render a list of flights as numbered text blocks."""
    if not flights:
        return empty_message
    count = len(flights)
    header = f"Found {count} flight{'s' if count != 1 else ''}:"
    blocks = []
    for i, flight in enumerate(flights, 1):
        block = _flight_block(flight)
        first, _, rest = block.partition("\n")
        numbered = f"{i}. {first}"
        if rest:
            numbered += "\n" + rest
        blocks.append(numbered)
    return header + "\n\n" + "\n\n".join(blocks)


def format_flight_details(flight: dict[str, Any] | None) -> str:
    """Render full details for a single flight."""
    if not flight:
        return "No matching flight found."

    lines = [_flight_block(flight)]

    aircraft_bits = []
    if flight.get("aircraft_manufacturer") or flight.get("aircraft_model"):
        model = " ".join(
            p for p in [flight.get("aircraft_manufacturer"), flight.get("aircraft_model")] if p
        )
        aircraft_bits.append(model)
    if flight.get("tail_number"):
        aircraft_bits.append(f"tail number {flight['tail_number']}")
    if flight.get("aircraft_name"):
        aircraft_bits.append(f'named "{flight["aircraft_name"]}"')
    if aircraft_bits:
        lines.append(f"  Aircraft: {', '.join(aircraft_bits)}")
    if flight.get("cruising_speed_kmh"):
        lines.append(f"  Cruising speed: {flight['cruising_speed_kmh']:,} km/h")

    if flight.get("distance_km"):
        km = flight["distance_km"]
        lines.append(f"  Distance: {km:,.0f} km ({km * 0.621371:,.0f} mi)")

    if flight.get("arrival_weather") or flight.get("arrival_temp_c") is not None:
        weather = flight.get("arrival_weather") or "unknown conditions"
        temp = flight.get("arrival_temp_c")
        line = f"  Weather at arrival: {weather}"
        if temp is not None:
            line += f", {temp:.0f}°C"
        lines.append(line)

    dep_tz = flight.get("departure_timezone")
    if flight.get("checkInScheduleOpen"):
        lines.append(f"  Check-in opens: {_fmt_dt(flight['checkInScheduleOpen'], dep_tz)}")
    if flight.get("checkInScheduleClose"):
        lines.append(f"  Check-in closes: {_fmt_dt(flight['checkInScheduleClose'], dep_tz)}")

    if flight.get("arrival_baggage_belt"):
        lines.append(f"  Baggage belt: {flight['arrival_baggage_belt']}")

    obs = flight.get("delay_forecast_observations")
    if obs:
        mean = flight.get("delay_forecast_mean_min")
        line = f"  Delay history: based on {obs} past flights"
        if mean is not None:
            line += f", average delay {mean:.0f} min"
        lines.append(line)

    if flight.get("is_archived"):
        lines.append("  This flight is archived.")
    if flight.get("id"):
        lines.append(f"  Flight ID: {flight['id']}")

    return "\n".join(lines)


def format_flight_status(status: dict[str, Any] | None) -> str:
    """Render the get_flight_status result as text."""
    if not status:
        return "No matching flight found."

    status_names = {
        "scheduled": "Scheduled",
        "delayed": "Delayed",
        "in_air": "In the air",
        "landed": "Landed",
        "cancelled": "Cancelled",
    }
    dep_tz = status.get("departure_timezone")
    arr_tz = status.get("arrival_timezone")
    lines = [
        f"{status.get('flight_number')} "
        f"({status.get('departure_airport')} → {status.get('arrival_airport')}): "
        f"{status_names.get(status.get('status'), status.get('status'))}"
    ]

    def time_lines(label: str, scheduled_key: str, estimated_key: str, actual_key: str,
                   delay_key: str, tz_name: str | None) -> None:
        scheduled = status.get(scheduled_key)
        estimated = status.get(estimated_key)
        actual = status.get(actual_key)
        delay = status.get(delay_key)
        if scheduled:
            lines.append(f"  Scheduled {label}: {_fmt_dt(scheduled, tz_name)}")
        if actual:
            lines.append(f"  Actual {label}: {_fmt_dt(actual, tz_name)}")
        elif estimated and estimated != scheduled:
            lines.append(f"  Estimated {label}: {_fmt_dt(estimated, tz_name)}")
        if delay:
            lines.append(f"  {label.capitalize()} delay: {_fmt_delay(delay)}")

    time_lines("departure", "scheduled_departure", "estimated_departure",
               "actual_departure", "departure_delay_minutes", dep_tz)
    time_lines("arrival", "scheduled_arrival", "estimated_arrival",
               "actual_arrival", "arrival_delay_minutes", arr_tz)

    if status.get("departure_gate"):
        lines.append(f"  Departure gate: {status['departure_gate']}")
    if status.get("arrival_gate"):
        lines.append(f"  Arrival gate: {status['arrival_gate']}")
    if status.get("arrival_baggage_belt"):
        lines.append(f"  Baggage belt: {status['arrival_baggage_belt']}")

    if status.get("arrival_weather") or status.get("arrival_temp_c") is not None:
        weather = status.get("arrival_weather") or "unknown conditions"
        line = f"  Weather at arrival: {weather}"
        if status.get("arrival_temp_c") is not None:
            line += f", {status['arrival_temp_c']:.0f}°C"
        lines.append(line)

    aircraft = []
    if status.get("aircraft"):
        aircraft.append(status["aircraft"])
    if status.get("tail_number"):
        aircraft.append(f"tail number {status['tail_number']}")
    if aircraft:
        lines.append(f"  Aircraft: {', '.join(aircraft)}")

    return "\n".join(lines)


def format_delay_forecast(forecast: dict[str, Any] | None) -> str:
    """Render historical delay statistics as text."""
    if not forecast:
        return "No matching flight found."
    if "message" in forecast:
        return f"{forecast.get('flight_number')}: {forecast['message']}"

    route = (forecast.get("route") or "").replace("->", "→")
    lines = [
        f"Delay forecast for {forecast.get('flight_number')} ({route})",
        f"Based on {forecast.get('observations')} observed flights:",
        f"  Early:              {forecast.get('early_pct')}%",
        f"  On time:            {forecast.get('ontime_pct')}%",
        f"  15+ min late:       {forecast.get('late_15_pct')}%",
        f"  30+ min late:       {forecast.get('late_30_pct')}%",
        f"  45+ min late:       {forecast.get('late_45_pct')}%",
        f"  Cancelled:          {forecast.get('cancelled_pct')}%",
        f"  Diverted:           {forecast.get('diverted_pct')}%",
    ]
    mean = forecast.get("mean_delay_minutes")
    if mean is not None:
        lines.append(f"Average delay: {mean:.0f} min")
    return "\n".join(lines)


def format_airports(airports: list[dict[str, Any]]) -> str:
    """Render airport search results as text."""
    if not airports:
        return "No airports found."
    blocks = []
    for i, a in enumerate(airports, 1):
        codes = "/".join(c for c in [a.get("iata"), a.get("icao")] if c)
        lines = [f"{i}. {a.get('name')} ({codes})"]
        place = ", ".join(p for p in [a.get("city"), a.get("country")] if p)
        details = []
        if place:
            details.append(place)
        if a.get("timeZoneIdentifier"):
            details.append(f"timezone {a['timeZoneIdentifier']}")
        if details:
            lines.append("   " + " · ".join(details))
        if a.get("website"):
            lines.append(f"   Website: {a['website']}")
        blocks.append("\n".join(lines))
    count = len(airports)
    return f"Found {count} airport{'s' if count != 1 else ''}:\n\n" + "\n\n".join(blocks)


def format_airlines(airlines: list[dict[str, Any]]) -> str:
    """Render airline search results as text."""
    if not airlines:
        return "No airlines found."
    blocks = []
    for i, a in enumerate(airlines, 1):
        codes = "/".join(c for c in [a.get("iata"), a.get("icao")] if c)
        lines = [f"{i}. {a.get('name')} ({codes})"]
        details = []
        if a.get("alliance"):
            details.append(f"Alliance: {a['alliance']}")
        if a.get("callsign"):
            details.append(f"Callsign: {a['callsign']}")
        if a.get("formattedPhone"):
            details.append(f"Phone: {a['formattedPhone']}")
        if details:
            lines.append("   " + " · ".join(details))
        if a.get("website"):
            lines.append(f"   Website: {a['website']}")
        blocks.append("\n".join(lines))
    count = len(airlines)
    return f"Found {count} airline{'s' if count != 1 else ''}:\n\n" + "\n\n".join(blocks)


def format_flight_stats(stats: dict[str, Any]) -> str:
    """Render aggregate flight statistics as text."""
    year = stats.get("year")
    period = "all time" if year == "all_time" else str(year)
    if not stats.get("total_flights"):
        return f"No flights found for {period}."

    lines = [f"Flight statistics ({period}):"]
    total = stats["total_flights"]
    cancelled = stats.get("cancelled_flights") or 0
    flights_line = f"  Total flights: {total:,}"
    if cancelled:
        flights_line += f" ({cancelled} cancelled)"
    lines.append(flights_line)

    if stats.get("total_distance_km"):
        lines.append(
            f"  Total distance: {stats['total_distance_km']:,.0f} km"
            f" ({stats.get('total_distance_miles', 0):,} mi)"
        )
        if stats.get("earth_circumnavigations"):
            lines.append(f"  That's {stats['earth_circumnavigations']}x around the Earth.")
    if stats.get("avg_distance_km"):
        lines.append(
            f"  Average flight distance: {stats['avg_distance_km']:,.0f} km"
            f" ({stats.get('avg_distance_miles', 0):,} mi)"
        )

    lines.append(f"  Unique airlines: {stats.get('unique_airlines', 0)}")
    lines.append(
        f"  Unique airports: {stats.get('unique_departure_airports', 0)} departure, "
        f"{stats.get('unique_arrival_airports', 0)} arrival"
    )

    top_airlines = stats.get("top_airlines") or []
    if top_airlines:
        lines.append("")
        lines.append("Top airlines:")
        for i, a in enumerate(top_airlines, 1):
            name = a.get("name")
            if a.get("iata"):
                name += f" ({a['iata']})"
            count = a.get("flight_count", 0)
            lines.append(f"  {i}. {name} — {count} flight{'s' if count != 1 else ''}")

    top_routes = stats.get("top_routes") or []
    if top_routes:
        lines.append("")
        lines.append("Top routes:")
        for i, r in enumerate(top_routes, 1):
            count = r.get("flight_count", 0)
            route = (r.get("route") or "").replace("->", "→")
            lines.append(f"  {i}. {route} — {count} flight{'s' if count != 1 else ''}")

    return "\n".join(lines)


def format_added_flight(result: dict[str, Any]) -> str:
    """Render the add_flight confirmation as text."""
    code = result.get("flight_code") or result.get("flight_number")
    lines = [
        "Flight added to Flighty:",
        f"  {code} — {result.get('airline')}",
        f"  {result.get('departure_airport')} → {result.get('arrival_airport')}",
        f"  Departs: {_fmt_dt(result.get('departure_time'), result.get('departure_timezone'))}",
        f"  Arrives: {_fmt_dt(result.get('arrival_time'), result.get('arrival_timezone'))}",
    ]
    ticket = []
    if result.get("seat_number"):
        ticket.append(f"Seat {result['seat_number']}")
    if result.get("cabin_class"):
        ticket.append(f"Cabin: {result['cabin_class']}")
    if result.get("booking_reference"):
        ticket.append(f"Booking ref: {result['booking_reference']}")
    if ticket:
        lines.append("  " + " · ".join(ticket))
    lines.append(f"  Flight ID: {result.get('flight_id')}")
    return "\n".join(lines)


def format_connections(connections: list[dict[str, Any]]) -> str:
    """Render flight connections (layovers) as text."""
    if not connections:
        return "No flight connections found."
    blocks = []
    for i, c in enumerate(connections, 1):
        lines = [
            f"{i}. {c.get('departing_flight')} ({c.get('from_airport')} → "
            f"{c.get('connection_airport')}) connecting to {c.get('arriving_flight')} "
            f"({c.get('connection_airport')} → {c.get('to_airport')})"
        ]
        layover = c.get("layover_minutes")
        airport_name = c.get("connection_airport_name") or c.get("connection_airport")
        if layover is not None:
            lines.append(f"   Layover at {airport_name}: {_fmt_duration(layover)}")
        else:
            lines.append(f"   Layover at {airport_name}")
        if c.get("arrival_time"):
            lines.append(f"   Arrive: {_fmt_dt(c['arrival_time'])}")
        if c.get("departure_time"):
            lines.append(f"   Depart: {_fmt_dt(c['departure_time'])}")
        if c.get("min_connection_time_min"):
            lines.append(f"   Minimum connection time: {c['min_connection_time_min']} min")
        blocks.append("\n".join(lines))
    count = len(connections)
    return f"Found {count} connection{'s' if count != 1 else ''}:\n\n" + "\n\n".join(blocks)
