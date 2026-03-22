"""Flighty MCP Server - Access your local Flighty flight data."""

from mcp.server.fastmcp import FastMCP

import flighty

mcp = FastMCP("flighty")


@mcp.tool()
def list_flights(
    upcoming_only: bool = False,
    past_only: bool = False,
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List your flights from Flighty.

    Args:
        upcoming_only: Only show flights that haven't departed yet.
        past_only: Only show flights that have already departed.
        include_archived: Include archived flights in results.
        limit: Maximum number of flights to return (default 50).
        offset: Number of flights to skip for pagination.
    """
    return flighty.list_flights(
        upcoming_only=upcoming_only,
        past_only=past_only,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )


@mcp.tool()
def get_flight(
    flight_id: str | None = None,
    flight_number: str | None = None,
) -> dict | None:
    """Get detailed information about a specific flight.

    Provide either flight_id (internal ID) or flight_number (e.g. "UA194", "BA930").
    If flight_number is given, returns the most recent instance.

    Args:
        flight_id: The internal Flighty flight ID.
        flight_number: The flight number (e.g. "UA194").
    """
    return flighty.get_flight(flight_id=flight_id, flight_number=flight_number)


@mcp.tool()
def search_flights(
    airline: str | None = None,
    departure_airport: str | None = None,
    arrival_airport: str | None = None,
    after: str | None = None,
    before: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Search flights by airline, airports, or date range.

    Args:
        airline: Filter by airline IATA code or name (e.g. "UA" or "United").
        departure_airport: Filter by departure airport IATA code or city (e.g. "SFO" or "San Francisco").
        arrival_airport: Filter by arrival airport IATA code or city (e.g. "LHR" or "London").
        after: Only flights departing after this ISO date (e.g. "2025-01-01").
        before: Only flights departing before this ISO date (e.g. "2025-12-31").
        limit: Maximum number of results (default 50).
    """
    return flighty.search_flights(
        airline=airline,
        departure_airport=departure_airport,
        arrival_airport=arrival_airport,
        after=after,
        before=before,
        limit=limit,
    )


@mcp.tool()
def get_flight_status(flight_number: str) -> dict | None:
    """Get the current status and delay information for a flight.

    Returns status (scheduled/delayed/in_air/landed/cancelled), gate info,
    departure and arrival delays, weather at arrival, and aircraft details.

    Args:
        flight_number: The flight number (e.g. "UA194", "BA930").
    """
    return flighty.get_flight_status(flight_number)


@mcp.tool()
def get_delay_forecast(flight_number: str) -> dict | None:
    """Get historical delay statistics for a flight number.

    Shows the percentage breakdown of early, on-time, late (15/30/45+ min),
    cancelled, and diverted flights based on historical data.

    Args:
        flight_number: The flight number (e.g. "UA194").
    """
    return flighty.get_delay_forecast(flight_number)


@mcp.tool()
def search_airports(query: str, limit: int = 10) -> list[dict]:
    """Search airports by IATA/ICAO code, city, or name.

    Args:
        query: Search term (e.g. "SFO", "San Francisco", "Heathrow").
        limit: Maximum number of results (default 10).
    """
    return flighty.search_airports(query, limit=limit)


@mcp.tool()
def search_airlines(query: str, limit: int = 10) -> list[dict]:
    """Search airlines by IATA/ICAO code, name, or alliance.

    Args:
        query: Search term (e.g. "UA", "United", "Star Alliance").
        limit: Maximum number of results (default 10).
    """
    return flighty.search_airlines(query, limit=limit)


@mcp.tool()
def get_flight_stats(year: int | None = None) -> dict:
    """Get aggregate statistics about your flights.

    Returns total flights, distance traveled, unique airports/airlines,
    top routes, and top airlines. Optionally filter by year.

    Args:
        year: Filter stats to a specific year (e.g. 2025). Omit for all-time stats.
    """
    return flighty.get_flight_stats(year=year)


@mcp.tool()
def get_connections() -> list[dict]:
    """Get flight connections (layovers) showing connecting flights and layover duration."""
    return flighty.get_connections()


if __name__ == "__main__":
    mcp.run()
