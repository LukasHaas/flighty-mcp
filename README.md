# Flighty MCP

A local MCP (Model Context Protocol) server that gives AI assistants access to your [Flighty](https://www.flightyapp.com/) flight data. Reads directly from the Flighty macOS app's local SQLite database.

## Features

- **List your flights** - View your own upcoming, past, or all flights
- **List friends' flights** - View connected friends' flights, filterable by name
- **Get flight details** - Look up any flight by number or ID
- **Search flights** - Filter by airline, airport, date range
- **Flight status** - Check current status, delays, gates, weather
- **Delay forecast** - Historical on-time performance statistics
- **Add flights** - Add a flight by flight code and date, with optional auto-lookup of airports
- **Airport search** - Look up airports by IATA code, city, or name
- **Airline search** - Look up airlines by IATA code, name, or alliance
- **Flight stats** - Aggregate statistics (distance, top routes, airlines)
- **Connections** - View layovers and connection times

## Prerequisites

- macOS with the [Flighty app](https://www.flightyapp.com/) installed
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- (Optional) Free [AirLabs](https://airlabs.co/) API key for automatic airport lookup when adding flights

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

To enable automatic airport lookup when adding flights, add your AirLabs API key:

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
      ],
      "env": {
        "AIRLABS_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

You can get a free API key at [airlabs.co](https://airlabs.co/).

### Claude Code

```bash
claude mcp add flighty -- uv --directory /path/to/flighty-mcp run main.py
```

With AirLabs API key:

```bash
claude mcp add flighty -e AIRLABS_API_KEY=your-api-key-here -- uv --directory /path/to/flighty-mcp run main.py
```

## Configuration

By default, the server reads from:

```
~/Library/Containers/com.flightyapp.flighty/Data/Documents/MainFlightyDatabase.db
```

Override with the `FLIGHTY_DB_PATH` environment variable if needed.

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FLIGHTY_DB_PATH` | No | Override the default Flighty database path |
| `AIRLABS_API_KEY` | No | [AirLabs](https://airlabs.co/) API key for automatic airport lookup when adding flights. Without this, you must provide departure and arrival airports manually. |

## Tools

| Tool | Description |
|------|-------------|
| `list_flights` | List your own flights with filters (upcoming/past/archived) |
| `list_friend_flights` | List connected friends' flights, optionally filtered by name |
| `get_flight` | Get detailed flight info by ID or flight number |
| `search_flights` | Search by airline, airports, date range |
| `get_flight_status` | Current status, delays, gates, weather |
| `get_delay_forecast` | Historical delay statistics |
| `add_flight` | Add a flight by code and date (airports auto-resolved with AirLabs API key) |
| `search_airports` | Search airports by code, city, or name |
| `search_airlines` | Search airlines by code, name, or alliance |
| `get_flight_stats` | Aggregate stats (distance, top routes, etc.) |
| `get_connections` | Flight connections and layover info |

## Example Queries

- "What are my upcoming flights?"
- "What flights does Felix have coming up?"
- "How often is UA194 delayed?"
- "Add flight LH400 on 2026-04-15"
- "Show my flight stats for 2025"
- "What gate does my next flight depart from?"
- "Search for airports in Tokyo"

## License

MIT
