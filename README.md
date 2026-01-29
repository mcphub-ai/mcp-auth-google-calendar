# MCP Google Calendar Server with Persistent Auth

This project implements a Model Context Protocol (MCP) server for Google Calendar, featuring persistent OAuth 2.0 authentication using Redis. It allows AI assistants (like Claude or Custom Clients) to interact with your Google Calendar.

## Features

- **Google Calendar Integration**: List upcoming events and create new events.
- **Persistent Authentication**: Uses Redis to store OAuth tokens securely, so you don't need to re-authenticate on every restart.
- **FastMCP Framework**: Built on top of the modern FastMCP framework.
- **Client Implementation**: Includes a sample client (`client.py`) using OpenAI's GPT-4o to demonstrate interaction.

## Supported Tools

1.  **`list_events`**: Lists upcoming events from the user's primary calendar. Supports filtering by result count and minimum time.
2.  **`create_event`**: Creates a new event with a summary, start time, end time, and description.

## Prerequisites

Before running this project, ensure you have the following:

1.  **Python 3.12+**: This project requires a recent version of Python.
2.  **Redis Server**: A running Redis instance is required for token storage.
3.  **Google Cloud Project**:
    *   Enable the **Google Calendar API**.
    *   Create **OAuth 2.0 Client IDs** (Desktop app).
    *   **Scopes**: Ensure the client has access to `https://www.googleapis.com/auth/calendar.events`.
    *   **Redirect URI**: If configured for web, ensure `http://localhost:8000/auth/callback` is allowed (FastMCP default). For Desktop/Installed App, this is handled automatically.
    *   Download the JSON credentials or copy the Client ID and Client Secret.
4.  **OpenAI API Key**: Required if you want to run the provided `client.py` test script.

## Installation

This project manages dependencies using `uv` (recommended) or you can use `pip`.

### Using `uv` (Recommended)

1.  Sync the project environment:
    ```bash
    uv sync
    ```

### Using `pip`

1.  Create a virtual environment:
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```
2.  Install dependencies:
    ```bash
    pip install -e .
    ```

## Configuration

1.  Copy the example environment file:
    ```bash
    cp .env.example .env
    # On Windows: copy .env.example .env
    ```

2.  Edit `.env` and fill in your credentials:

    ```ini
    # Google OAuth Credentials
    GOOGLE_CLIENT_ID=your_client_id_here
    GOOGLE_CLIENT_SECRET=your_client_secret_here
    
    # Server URLs
    SERVER_URL=http://localhost:8000
    MCP_SERVER_URL=http://localhost:8000/sse

    # Redis (Defaults provided, change if needed)
    REDIS_HOST=localhost
    REDIS_PORT=6379
    REDIS_DB=0

    # OpenAI API Key (For running client.py)
    OPENAI_API_KEY=sk-your-openai-key
    ```

## Docker Support

You can also run the server using Docker.

1.  **Build the image**:
    ```bash
    docker build -t mcp-google-calendar .
    ```

2.  **Run the container** (ensure you environment variables are passed):
    ```bash
    # Assuming you have a .env file
    docker run --env-file .env -p 8000:8000 mcp-google-calendar
    ```
    *Note: If your Redis is running on the host, use `host.docker.internal` (Windows/Mac) or `--network="host"` (Linux).*

## Running the Server

1.  **Start Redis**: Ensure your Redis server is running locally (default port 6379).

2.  **Run the MCP Server**:
    Using `uv`:
    ```bash
    uv run server.py
    ```
    
    Using standard python:
    ```bash
    python server.py
    ```

    The server will start at `http://localhost:8000`.

You can also use profiles to maintain separate authentication sessions:
```bash
uv run client.py --profile work
uv run client.py --profile personal
```

## Connecting a Client

### Option 1: Using the provided Test Client
This project includes a CLI client powered by OpenAI to test the integration.

1.  Ensure the server is running.
2.  In a new terminal, run:
    ```bash
    uv run client.py
    # or: python client.py
    ```
3.  On first run, it will open your request OAuth authentication. Follow the steps in your browser to log in with your Google account.
4.  Once authenticated, you can chat with the assistant:
    > "What is on my calendar for today?"
    > "Schedule a meeting with the team tomorrow at 2 PM."

### Option 2: Using Claude Desktop
You can configure Claude Desktop to use this MCP server.

1.  Locate your Claude Desktop config file (typically `%APPDATA%\Claude\claude_desktop_config.json` on Windows or `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS).
2.  Add the server configuration:
    ```json
    {
      "mcpServers": {
        "google-calendar": {
          "command": "uv",
          "args": ["run", "--directory", "C:/path/to/repo/mcp-auth-gg-calendar", "server.py"],
          "env": {
             "GOOGLE_CLIENT_ID": "your_client_id",
             "GOOGLE_CLIENT_SECRET": "your_client_secret"
          }
        }
      }
    }
    ```
    *Note: Replace paths and credentials with your actual values.*

## Testing

Currently, no automated unit tests are included. The best way to test is using the `client.py` script as described above.

To run future tests (if added), you would use `pytest`:
```bash
uv run pytest
```
