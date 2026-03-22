"""WebSocket handlers for real-time Hivemind streaming.

Provides real-time progress updates during analysis, including:
- Agent execution progress
- Debate round updates
- Simulation results
- Final recommendations
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any

import jwt
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.config import settings
from app.deps import _decode_token
from app.routers.settings import get_active_api_key
from hivemind_core import (
    ClaudeLLM,
    execute_agent,
)
from hivemind_core.adapters import QdrantVectorStore, SQLAlchemyStorage

router = APIRouter()


class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket

    def disconnect(self, client_id: str):
        self.active_connections.pop(client_id, None)

    async def send_json(self, client_id: str, data: dict):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_json(data)

    async def broadcast(self, data: dict):
        for connection in self.active_connections.values():
            await connection.send_json(data)


manager = ConnectionManager()


async def _authenticate_websocket(websocket: WebSocket) -> dict | None:
    """Validate JWT from query param ``token``.

    Returns the decoded payload on success, or *None* after closing
    the socket with code 4001 on failure.
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.accept()
        await websocket.close(code=4001, reason="Missing auth token")
        return None
    try:
        from fastapi.security import HTTPAuthorizationCredentials

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        return _decode_token(creds)
    except (jwt.InvalidTokenError, jwt.ExpiredSignatureError, HTTPException, ValueError):
        await websocket.accept()
        await websocket.close(code=4001, reason="Invalid or expired token")
        return None


async def _resolve_connection_id(
    websocket: WebSocket,
    user: dict,
    requested_client_id: str,
) -> str | None:
    """Resolve socket connection identity from auth payload."""
    subject = str(user.get("sub") or "").strip()
    role = str(user.get("role") or "").strip()

    if not subject:
        await websocket.accept()
        await websocket.close(code=4001, reason="Missing token subject")
        return None

    if role not in {"operator", "client"}:
        await websocket.accept()
        await websocket.close(code=4003, reason="Invalid token role")
        return None

    if role == "client" and requested_client_id != subject:
        await websocket.accept()
        await websocket.close(code=4003, reason="client_id does not match token subject")
        return None

    if role == "client":
        return subject
    return requested_client_id


def _serialize_datetime(obj: Any) -> Any:
    """Serialize datetime objects for JSON."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


@router.websocket("/ws/analysis/{client_id}")
async def websocket_analysis(
    websocket: WebSocket,
    client_id: str,
):
    """WebSocket endpoint for real-time analysis streaming.

    Messages from client:
        {
            "type": "start_analysis",
            "query": "...",
            "theory_agent_ids": ["..."],
            "practicality_agent_ids": ["..."],
            "sufficiency_value": 1,
            "feasibility_threshold": 80
        }

    Messages to client:
        {
            "type": "status",
            "status": "connected" | "analyzing" | "complete" | "error",
            "message": "..."
        }
        {
            "type": "agent_start",
            "agent_id": "...",
            "agent_name": "..."
        }
        {
            "type": "agent_complete",
            "agent_id": "...",
            "agent_name": "...",
            "response": "...",
            "tokens": {...}
        }
        {
            "type": "debate_round",
            "round": 1,
            "recommendations_count": 3
        }
        {
            "type": "recommendation",
            "recommendation": {...}
        }
        {
            "type": "complete",
            "result": {...}
        }
    """
    user = await _authenticate_websocket(websocket)
    if user is None:
        return

    connection_id = await _resolve_connection_id(websocket, user, client_id)
    if connection_id is None:
        return

    await manager.connect(websocket, connection_id)

    try:
        await manager.send_json(connection_id, {
            "type": "status",
            "status": "connected",
            "message": "Connected to Hivemind analysis stream",
        })

        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "start_analysis":
                await _run_streaming_analysis(connection_id, message)

            elif message.get("type") == "ping":
                await manager.send_json(connection_id, {"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(connection_id)
    except Exception as e:
        await manager.send_json(connection_id, {
            "type": "status",
            "status": "error",
            "message": str(e),
        })
        manager.disconnect(connection_id)


async def _run_streaming_analysis(connection_id: str, message: dict):
    """Run analysis with streaming updates.

    This runs the analysis synchronously but sends progress updates
    via WebSocket at each step.
    """
    from app.db.session import SessionLocal

    db = SessionLocal()

    try:
        await manager.send_json(connection_id, {
            "type": "status",
            "status": "analyzing",
            "message": "Starting analysis...",
        })

        # Create core interfaces
        api_key = get_active_api_key()
        if not api_key:
            await manager.send_json(connection_id, {
                "type": "status",
                "status": "error",
                "message": "No Anthropic API key configured",
            })
            return

        llm = ClaudeLLM(api_key=api_key)
        storage = SQLAlchemyStorage(db)
        vector_store = QdrantVectorStore(
            qdrant_url=settings.VECTOR_DB_URL,
            embedding_model=settings.EMBEDDING_MODEL,
            db=db,
        )

        query = message.get("query", "")
        theory_agent_ids = message.get("theory_agent_ids", [])
        practicality_agent_ids = message.get("practicality_agent_ids", [])

        # Load theory agents
        theory_agents = []
        for agent_id in theory_agent_ids:
            agent = storage.get_agent(agent_id)
            if agent:
                theory_agents.append(agent)

        if not theory_agents:
            await manager.send_json(connection_id, {
                "type": "status",
                "status": "error",
                "message": "No valid theory agents found",
            })
            return

        # Execute each theory agent with streaming updates
        results = []
        for agent in theory_agents:
            await manager.send_json(connection_id, {
                "type": "agent_start",
                "agent_id": agent.id,
                "agent_name": agent.name,
                "network_type": str(agent.network_type),
            })

            # Run synchronously (could be made async with threadpool)
            result, audit = execute_agent(
                agent=agent,
                query=query,
                llm=llm,
                vector_store=vector_store,
                storage=storage,
            )
            results.append(result)

            await manager.send_json(connection_id, {
                "type": "agent_complete",
                "agent_id": result.agent_id,
                "agent_name": result.agent_name,
                "network_type": result.network_type,
                "response_preview": result.response[:500] + "..." if len(result.response) > 500 else result.response,
                "tokens": {
                    "input": result.input_tokens,
                    "output": result.output_tokens,
                },
                "latency_ms": result.latency_ms,
            })

            # Small delay to allow UI to update
            await asyncio.sleep(0.1)

        # Build recommendations
        recommendations = []
        for result in results:
            rec = {
                "id": str(uuid.uuid4()),
                "title": f"Recommendation from {result.agent_name}",
                "content": result.response,
                "contributing_agents": [result.agent_id],
                "average_feasibility": 0.0,
            }
            recommendations.append(rec)

            await manager.send_json(connection_id, {
                "type": "recommendation",
                "recommendation": rec,
            })

        # Practicality evaluation if agents specified
        if practicality_agent_ids:
            practicality_agents = []
            for agent_id in practicality_agent_ids:
                agent = storage.get_agent(agent_id)
                if agent:
                    practicality_agents.append(agent)

            for rec in recommendations:
                for p_agent in practicality_agents:
                    await manager.send_json(connection_id, {
                        "type": "agent_start",
                        "agent_id": p_agent.id,
                        "agent_name": p_agent.name,
                        "network_type": "practicality",
                        "evaluating_recommendation": rec["id"],
                    })

                    eval_query = f"Evaluate this recommendation:\n\n{rec['content']}"
                    result, audit = execute_agent(
                        agent=p_agent,
                        query=eval_query,
                        llm=llm,
                        vector_store=vector_store,
                        storage=storage,
                    )

                    await manager.send_json(connection_id, {
                        "type": "agent_complete",
                        "agent_id": result.agent_id,
                        "agent_name": result.agent_name,
                        "network_type": "practicality",
                        "response_preview": result.response[:500] + "..." if len(result.response) > 500 else result.response,
                        "evaluating_recommendation": rec["id"],
                    })

        # Send complete result
        await manager.send_json(connection_id, {
            "type": "complete",
            "result": {
                "id": str(uuid.uuid4()),
                "recommendations": recommendations,
                "total_agents_executed": len(results),
            },
        })

        await manager.send_json(connection_id, {
            "type": "status",
            "status": "complete",
            "message": "Analysis complete",
        })

    except Exception as e:
        await manager.send_json(connection_id, {
            "type": "status",
            "status": "error",
            "message": str(e),
        })
    finally:
        db.close()


@router.websocket("/ws/simulation/{client_id}")
async def websocket_simulation(
    websocket: WebSocket,
    client_id: str,
):
    """WebSocket endpoint for real-time simulation execution.

    Messages from client:
        {
            "type": "run_simulation",
            "formula_id": "...",
            "inputs": {...}
        }

    Messages to client:
        {
            "type": "simulation_result",
            "formula_id": "...",
            "outputs": {...},
            "variables": {...}
        }
    """
    user = await _authenticate_websocket(websocket)
    if user is None:
        return

    connection_id = await _resolve_connection_id(websocket, user, client_id)
    if connection_id is None:
        return

    await manager.connect(websocket, connection_id)

    try:
        await manager.send_json(connection_id, {
            "type": "status",
            "status": "connected",
            "message": "Connected to Hivemind simulation stream",
        })

        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "run_simulation":
                from app.db.session import SessionLocal
                from hivemind_core import run_simulation

                db = SessionLocal()
                try:
                    storage = SQLAlchemyStorage(db)
                    formula = storage.get_simulation(message.get("formula_id", ""))

                    if not formula:
                        await manager.send_json(connection_id, {
                            "type": "error",
                            "message": "Simulation formula not found",
                        })
                        continue

                    result = run_simulation(formula, message.get("inputs", {}))

                    await manager.send_json(connection_id, {
                        "type": "simulation_result",
                        "formula_id": formula.id,
                        "formula_name": formula.name,
                        "outputs": result["outputs"],
                        "variables": result["variables"],
                    })
                finally:
                    db.close()

            elif message.get("type") == "ping":
                await manager.send_json(connection_id, {"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(connection_id)
    except Exception as e:
        await manager.send_json(connection_id, {
            "type": "error",
            "message": str(e),
        })
        manager.disconnect(connection_id)
