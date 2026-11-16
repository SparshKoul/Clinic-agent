"""
app.py - Real-Time FastAPI & WebSocket Chat Server for Sunrise Multispeciality Clinic

Architecture:
- Object-Oriented Service Design: ConnectionManager, SessionManager, and WebSocketController
- Asynchronous Non-Blocking Event Dispatch: Status indicators, Booking cards, and Assistant messages
- Multi-Client Session Isolation: Each WebSocket connection maintains independent context and memory
"""

import os
import json
import uuid
import logging
from typing import Dict, Any, Optional
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
import uvicorn

import agent
import db

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("clinic_server")

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)


# =============================================================================
# 1. Connection & Session Management (OOP Facade)
# =============================================================================
class SessionManager:
    """Manages active ClinicAgentSession instances with state persistence across reconnections."""

    def __init__(self):
        self._sessions: Dict[str, agent.ClinicAgentSession] = {}

    def get_or_create(self, session_id: str) -> agent.ClinicAgentSession:
        """Retrieves existing session or creates a new isolated clinical session."""
        if session_id not in self._sessions:
            logger.info("Initializing new ClinicAgentSession for id: %s", session_id)
            self._sessions[session_id] = agent.ClinicAgentSession(session_id=session_id)
        return self._sessions[session_id]

    def remove_session(self, session_id: str) -> None:
        """Removes session from memory."""
        self._sessions.pop(session_id, None)

    def count(self) -> int:
        return len(self._sessions)


class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self):
        self._active_connections: Dict[str, WebSocket] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        """Accepts and stores active WebSocket connection."""
        await websocket.accept()
        self._active_connections[session_id] = websocket
        logger.info("WebSocket connected for session: %s. Active connections: %d", session_id, len(self._active_connections))

    def disconnect(self, session_id: str) -> None:
        """Removes connection on disconnect."""
        self._active_connections.pop(session_id, None)
        logger.info("WebSocket disconnected for session: %s. Active connections: %d", session_id, len(self._active_connections))

    async def send_json(self, websocket: WebSocket, payload: Dict[str, Any]) -> None:
        """Safely sends JSON payload across WebSocket."""
        try:
            await websocket.send_text(json.dumps(payload))
        except Exception as e:
            logger.warning("Failed to send JSON to client: %s", str(e))


session_manager = SessionManager()
connection_manager = ConnectionManager()


# =============================================================================
# 2. WebSocket Protocol Controller
# =============================================================================
class ClinicWebSocketController:
    """Coordinates incoming WebSocket requests, agent triage turns, and event streaming."""

    WELCOME_MESSAGE = (
        "Hello! Welcome to Sunrise Multispeciality Clinic. I'm your AI care assistant. "
        "How can I help you today? Have you visited us before?"
    )

    def __init__(
        self,
        websocket: WebSocket,
        session_id: str,
        session_mgr: SessionManager = session_manager,
        conn_mgr: ConnectionManager = connection_manager
    ):
        self.websocket = websocket
        self.session_id = session_id
        self.session_mgr = session_mgr
        self.conn_mgr = conn_mgr
        self.session: agent.ClinicAgentSession = self.session_mgr.get_or_create(session_id)

    async def handle_lifecycle(self) -> None:
        """Runs the complete connection lifecycle for a WebSocket client."""
        await self.conn_mgr.connect(self.session_id, self.websocket)
        try:
            # Send initial greeting if this is a newly initialized session
            if len(self.session.messages) <= 1:
                await self.conn_mgr.send_json(self.websocket, {
                    "type": "assistant_message",
                    "text": self.WELCOME_MESSAGE
                })

            while True:
                # Receive next patient message
                raw_text = await self.websocket.receive_text()
                await self._process_incoming_message(raw_text)

        except WebSocketDisconnect:
            logger.info("Client disconnected gracefully: session %s", self.session_id)
        except Exception as e:
            logger.error("Unexpected WebSocket error on session %s: %s", self.session_id, str(e), exc_info=True)
            try:
                await self.conn_mgr.send_json(self.websocket, {
                    "type": "error",
                    "text": "An internal error occurred. Please try again."
                })
            except Exception:
                pass
        finally:
            self.conn_mgr.disconnect(self.session_id)

    async def _process_incoming_message(self, raw_text: str) -> None:
        """Validates JSON structure and runs the autonomous agent turn."""
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            await self.conn_mgr.send_json(self.websocket, {
                "type": "error",
                "text": "Invalid JSON payload. Messages must be valid JSON."
            })
            return

        msg_type = data.get("type")
        if msg_type != "user_message":
            await self.conn_mgr.send_json(self.websocket, {
                "type": "error",
                "text": f"Unsupported message type: '{msg_type}'. Expected 'user_message'."
            })
            return

        user_text = (data.get("text") or "").strip()
        if not user_text:
            await self.conn_mgr.send_json(self.websocket, {
                "type": "error",
                "text": "Message text cannot be empty."
            })
            return

        # Add message to session
        self.session.add_user_message(user_text)

        # Callbacks for streaming events back across the WebSocket
        import asyncio
        loop = asyncio.get_running_loop()

        def sync_status_callback(status_text: str):
            asyncio.run_coroutine_threadsafe(
                self.conn_mgr.send_json(self.websocket, {
                    "type": "status",
                    "text": status_text
                }),
                loop
            )

        def sync_booking_callback(appointment_data: Dict[str, Any]):
            asyncio.run_coroutine_threadsafe(
                self.conn_mgr.send_json(self.websocket, {
                    "type": "booking",
                    "appointment": appointment_data
                }),
                loop
            )

        # Run multi-turn agent step
        assistant_reply = await self.session.run_turn(
            on_status=sync_status_callback,
            on_booking=sync_booking_callback
        )

        # Emit complete assistant message
        await self.conn_mgr.send_json(self.websocket, {
            "type": "assistant_message",
            "text": assistant_reply
        })


# =============================================================================
# 3. FastAPI Application Initialization
# =============================================================================
app = FastAPI(
    title="Sunrise Multispeciality Clinic AI Assistant",
    description="Autonomous clinical triage, medical knowledge RAG, and appointment scheduling agent.",
    version="1.0.0"
)


@app.get("/health")
async def health_check():
    """System health check endpoint."""
    return {
        "status": "healthy",
        "service": "Sunrise Multispeciality Clinic AI Assistant",
        "active_sessions": session_manager.count()
    }


@app.websocket("/ws/chat")
async def websocket_chat_endpoint(
    websocket: WebSocket,
    session_id: Optional[str] = Query(None)
):
    """
    WebSocket endpoint for real-time patient conversation.
    Supports session reconnection via query parameter ?session_id=...
    """
    sid = session_id or str(uuid.uuid4())
    controller = ClinicWebSocketController(websocket=websocket, session_id=sid)
    await controller.handle_lifecycle()


# Serve static web frontend
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serves the single-page chat client."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse(
        content="<h2>Sunrise Multispeciality Clinic AI Assistant</h2><p>Static UI not yet built.</p>",
        status_code=200
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
