# server.py (Optimized for Public/Enterprise Use)
import os
import logging
from typing import Optional, Any, Dict
from datetime import datetime, timezone

# FastMCP Framework
from fastmcp import FastMCP, Context
from fastmcp.tools.tool import Tool, ToolResult
from fastmcp.server.dependencies import get_context
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.exceptions import ToolError

# Storage
from key_value.aio.stores.redis import RedisStore

# Google SDK
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Environment Loading
from dotenv import load_dotenv

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("mcp-server")

# Load environment variables
load_dotenv()

# --- Configuration & Validation ---
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:8000")

# Redis Config
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_DB = int(os.environ.get("REDIS_DB", "0"))

if not all([GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET]):
    raise ValueError(
        "Missing required env variables: GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET."
    )

# --- Persistent Storage Layer ---
# 1. Initialize Redis Connection (Shared Storage for Multi-Instance Support)
# Tokens will be stored here.
secure_store = RedisStore(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
)

# --- Authentication Provider Setup ---
# We define the list of allowed redirect URIs.
# This is CRITICAL for public servers to support various clients.
ALLOWED_REDIRECT_URIS = [
    "https://claude.ai/api/mcp/auth_callback"  # REQUIRED for Claude Web [22]
]

auth_provider = GoogleProvider(
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    base_url=SERVER_URL,
    client_storage=secure_store,
    required_scopes=["https://www.googleapis.com/auth/calendar.events"],
    # Enable wide compatibility for DCR clients by allow-listing specific URIs
    # allowed_client_redirect_uris=ALLOWED_REDIRECT_URIS,
    # Ensure we request offline access to get a refresh token for persistence
    extra_authorize_params={"access_type": "offline"}
)

# --- Server Instantiation ---
mcp = FastMCP(
    name="Google Calendar Professional",
    instructions="Enterprise-grade Google Calendar integration with persistent OAuth.",
    auth=auth_provider
)


async def get_calendar_service(ctx: Context) -> Any:
    """
    Reconstructs the Google Calendar Service object for the specific authenticated user.
    """
    try:
        req_ctx = ctx.request_context
        if not req_ctx:
            raise ToolError("No active request context found.")

        request_obj = req_ctx.request

        # Check authentication status
        if not hasattr(request_obj, "user") or not request_obj.user.is_authenticated:
            raise ToolError("No active authentication found. Please log in.")

        # Extract Token Info
        token_info = request_obj.user

        # Access token retrieval logic (handles different FastMCP user object structures)
        if hasattr(token_info, "access_token") and hasattr(token_info.access_token, "token"):
            access_token = token_info.access_token.token
        else:
            access_token = getattr(token_info, "token", None)

        if not access_token:
            logger.error(
                f"Token extraction failed. Object type: {type(token_info)}")
            raise ToolError(
                "Could not retrieve access token from user context.")

        # Reconstruct Credentials
        # Note: The GoogleProvider manages refreshing the token automatically
        # if the client_storage is configured correctly.
        creds = Credentials(
            token=access_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            scopes=auth_provider.scopes if hasattr(auth_provider, "scopes") else [
                "https://www.googleapis.com/auth/calendar.events"]
        )

        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    except Exception as e:
        logger.error(f"Authorization/Service construction failed: {e}")
        raise ToolError(f"System Authorization Failure: {str(e)}")


class ListUpcomingEvents(Tool):
    name: str = "list_upcoming_events"
    description: str = "List upcoming events from the primary calendar."
    parameters: Dict[str, Any] = {
        "type": "object",
        "description": "Get upcoming calendar events",
        "properties": {
            "max_results": {"type": "integer", "description": "Max events to return. Default 10."},
            "time_min": {"type": "string", "description": "Start time in ISO format (YYYY-MM-DDTHH:MM:SSZ). Defaults to now."}
        },
        "additionalProperties": True
    }

    async def run(self, arguments: Dict[str, Any]) -> ToolResult:
        max_results = arguments.get('max_results', 10)
        time_min = arguments.get('time_min')

        try:
            ctx = get_context()
            service = await get_calendar_service(ctx)

            # Use timezone-aware UTC now
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            t_min = time_min if time_min else now

            logger.info(f"Fetching events for session {ctx.session_id}")
            events_result = service.events().list(
                calendarId='primary',
                timeMin=t_min,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])

            if not events:
                return ToolResult(content=[{"type": "text", "text": "No upcoming events found."}])

            result_lines = ["Upcoming events:"]
            for event in events:
                start = event['start'].get(
                    'dateTime', event['start'].get('date'))
                result_lines.append(
                    f"- {start}: {event.get('summary', 'No Title')}")

            return ToolResult(content=[{"type": "text", "text": "\n".join(result_lines)}])

        except Exception as e:
            logger.error(f"API Error in list_events: {e}")
            return ToolResult(content=[{"type": "text", "text": f"Google Calendar API Error: {str(e)}"}])


class CreateEvent(Tool):
    name: str = "create_event"
    description: str = "Create a new event in the primary calendar."
    parameters: Dict[str, Any] = {
        "type": "object",
        "description": "Create a calendar event",
        "required": ["summary", "start_time", "end_time"],
        "properties": {
            "summary": {"type": "string", "description": "The title of the event."},
            "start_time": {"type": "string", "description": "Start time in ISO 8601 format (e.g., 2024-12-31T10:00:00Z)."},
            "end_time": {"type": "string", "description": "End time in ISO 8601 format."},
            "description": {"type": "string", "description": "Description/body of the event.", "default": ""}
        },
        "additionalProperties": True
    }

    async def run(self, arguments: Dict[str, Any]) -> ToolResult:
        summary = arguments.get('summary')
        start_time = arguments.get('start_time')
        end_time = arguments.get('end_time')
        description = arguments.get('description', "")

        try:
            ctx = get_context()
            service = await get_calendar_service(ctx)

            event_body = {
                'summary': summary,
                'description': description,
                'start': {'dateTime': start_time, 'timeZone': 'UTC'},
                'end': {'dateTime': end_time, 'timeZone': 'UTC'},
            }

            event = service.events().insert(calendarId='primary', body=event_body).execute()
            return ToolResult(content=[{"type": "text", "text": f"Event created successfully. Link: {event.get('htmlLink')}"}])
        except Exception as e:
            logger.error(
                f"Failed to create event for session {ctx.session_id}: {e}")
            return ToolResult(content=[{"type": "text", "text": f"Failed to create event: {str(e)}"}])


# Add tools to server
mcp.add_tool(ListUpcomingEvents())
mcp.add_tool(CreateEvent())

if __name__ == "__main__":
    logger.info(f"Starting Google Calendar MCP Server on {HOST}:{PORT}...")
    # Using '0.0.0.0' allows external access (Public Server)
    mcp.run(transport="sse", host=HOST, port=PORT)
