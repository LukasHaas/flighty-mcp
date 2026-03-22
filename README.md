# Flighty MCP

A local MCP (Model Context Protocol) server that gives AI assistants access to your [Flighty](https://www.flightyapp.com/) flight data. Reads directly from the Flighty macOS app's local SQLite database.

## Features

- **List flights** - View upcoming, past, or all flights with pagination
- **Get flight details** - Look up any flight by number or ID
- **Search flights** - Filter by airline, airport, date range
- **Flight status** - Check current status, delays, gates, weather
- **Delay forecast** - Historical on-time performance statistics
- **Airport search** - Look up airports by IATA code, city, or name
- **Airline search** - Look up airlines by IATA code, name, or alliance
- **Flight stats** - Aggregate statistics (distance, top routes, airlines)
- **Connections** - View layovers and connection times

## Prerequisites

- macOS with the [Flighty app](https://www.flightyapp.com/) installed
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager

## Setup

### Claude Desktop

Add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "flighty": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/flighty-mcp",
        "run",
        "main.py"
      ]
    }
  }
}
```

### Claude Code

```bash
claude mcp add flighty -- uv --directory /path/to/flighty-mcp run main.py
```

## Configuration

By default, the server reads from:

```
~/Library/Containers/com.flightyapp.flighty/Data/Documents/MainFlightyDatabase.db
```

Override with the `FLIGHTY_DB_PATH` environment variable if needed.

## Tools

| Tool | Description |
|------|-------------|
| `list_flights` | List flights with filters (upcoming/past/archived) |
| `get_flight` | Get detailed flight info by ID or flight number |
| `search_flights` | Search by airline, airports, date range |
| `get_flight_status` | Current status, delays, gates, weather |
| `get_delay_forecast` | Historical delay statistics |
| `search_airports` | Search airports by code, city, or name |
| `search_airlines` | Search airlines by code, name, or alliance |
| `get_flight_stats` | Aggregate stats (distance, top routes, etc.) |
| `get_connections` | Flight connections and layover info |

## Example Queries

- "What are my upcoming flights?"
- "How often is UA194 delayed?"
- "Show my flight stats for 2025"
- "What gate does my next flight depart from?"
- "Search for airports in Tokyo"

## License

MIT
