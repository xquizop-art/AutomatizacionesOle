"""
WebSocket server para updates en tiempo real.
Stream de trades y senales a los clientes conectados.

Uso:
    from backend.api.websocket import ws_manager, websocket_endpoint

    # Registrar como callback del engine:
    engine.on_event(ws_manager.engine_event_handler)

    # Agregar al router de FastAPI:
    app.add_api_websocket_route("/ws/live", websocket_endpoint)
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger


class ConnectionManager:
    """
    Gestor de conexiones WebSocket.

    Mantiene un registro de clientes conectados y permite broadcast
    de eventos del engine a todos ellos.

    Cada conexion puede suscribirse opcionalmente a canales especificos
    (por defecto recibe todos los eventos).
    """

    def __init__(self) -> None:
        # Conexiones activas: {websocket: set_de_canales}
        # Si canales esta vacio, recibe todo.
        self._active_connections: dict[WebSocket, set[str]] = {}
        self._lock = asyncio.Lock()

    # ── Gestion de conexiones ────────────────────────────────────

    async def connect(
        self,
        websocket: WebSocket,
        channels: set[str] | None = None,
    ) -> None:
        """
        Acepta una nueva conexion WebSocket.

        Args:
            websocket: Conexion entrante.
            channels: Canales a suscribir (None = todos).
        """
        await websocket.accept()
        async with self._lock:
            self._active_connections[websocket] = channels or set()

        client_info = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "unknown"
        logger.info(
            f"WebSocket conectado: {client_info} | "
            f"channels={channels or 'ALL'} | "
            f"total_connections={len(self._active_connections)}"
        )

        # Enviar mensaje de bienvenida
        await self._send_json(websocket, {
            "event": "connected",
            "message": "Conectado al stream en tiempo real",
            "timestamp": datetime.now().isoformat(),
        })

    async def disconnect(self, websocket: WebSocket) -> None:
        """Elimina una conexion WebSocket del registro."""
        async with self._lock:
            self._active_connections.pop(websocket, None)

        client_info = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "unknown"
        logger.info(
            f"WebSocket desconectado: {client_info} | "
            f"total_connections={len(self._active_connections)}"
        )

    # ── Broadcast ────────────────────────────────────────────────

    async def broadcast(
        self,
        data: dict[str, Any],
        channel: str | None = None,
    ) -> None:
        """
        Envia un mensaje a todos los clientes conectados.

        Si se especifica un canal, solo envia a clientes suscritos
        a ese canal (o a todos los que no especificaron canales).

        Args:
            data: Diccionario con los datos a enviar.
            channel: Canal del evento (opcional).
        """
        async with self._lock:
            connections = list(self._active_connections.items())

        disconnected: list[WebSocket] = []

        for ws, channels in connections:
            # Filtrar por canal si el cliente tiene suscripciones
            if channels and channel and channel not in channels:
                continue

            try:
                await self._send_json(ws, data)
            except Exception:
                disconnected.append(ws)

        # Limpiar conexiones muertas
        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    self._active_connections.pop(ws, None)
            logger.debug(
                f"Eliminadas {len(disconnected)} conexiones muertas"
            )

    async def send_to(
        self,
        websocket: WebSocket,
        data: dict[str, Any],
    ) -> None:
        """Envia un mensaje a un cliente especifico."""
        try:
            await self._send_json(websocket, data)
        except Exception as e:
            logger.error(f"Error enviando a cliente: {e}")
            await self.disconnect(websocket)

    # ── Engine event handler ─────────────────────────────────────

    async def engine_event_handler(
        self,
        event: Any,
        data: dict[str, Any],
    ) -> None:
        """
        Callback para registrar en el engine.
        Convierte eventos del engine en broadcasts WebSocket.

        Uso:
            engine.on_event(ws_manager.engine_event_handler)
        """
        # Extraer el nombre del canal del tipo de evento
        channel = event.value if hasattr(event, "value") else str(event)

        await self.broadcast(data, channel=channel)

    # ── Utilidades ───────────────────────────────────────────────

    @property
    def connection_count(self) -> int:
        """Numero de conexiones activas."""
        return len(self._active_connections)

    async def _send_json(
        self,
        websocket: WebSocket,
        data: dict[str, Any],
    ) -> None:
        """Serializa y envia datos JSON por WebSocket."""
        # Serializar valores no-JSON (datetime, Enum, etc.)
        text = json.dumps(data, default=str)
        await websocket.send_text(text)


# ── Instancia global del manager ─────────────────────────────────

ws_manager = ConnectionManager()


# ── Endpoint WebSocket ───────────────────────────────────────────


async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    Endpoint WebSocket principal.

    Los clientes se conectan a /ws/live y reciben eventos en tiempo real.

    Protocolo:
        - Al conectar, pueden enviar un JSON con canales a suscribir:
          {"subscribe": ["order_submitted", "signal_generated"]}
        - Si no envian nada, reciben todos los eventos.
        - El servidor envia eventos como JSON:
          {"event": "order_submitted", "strategy": "sma_crossover", ...}
        - El cliente puede enviar "ping" y recibira "pong".
    """
    # Parsear canales de la query string (opcional)
    channels_param = websocket.query_params.get("channels", "")
    channels = (
        set(channels_param.split(","))
        if channels_param
        else set()
    )

    await ws_manager.connect(websocket, channels=channels)

    try:
        while True:
            # Escuchar mensajes del cliente
            message = await websocket.receive_text()

            # Ping/pong keepalive
            if message.strip().lower() == "ping":
                await ws_manager.send_to(websocket, {
                    "event": "pong",
                    "timestamp": datetime.now().isoformat(),
                })
                continue

            # Actualizar suscripciones en runtime
            try:
                payload = json.loads(message)
                if "subscribe" in payload:
                    new_channels = set(payload["subscribe"])
                    async with ws_manager._lock:
                        ws_manager._active_connections[websocket] = new_channels
                    await ws_manager.send_to(websocket, {
                        "event": "subscribed",
                        "channels": list(new_channels),
                        "timestamp": datetime.now().isoformat(),
                    })
                elif "unsubscribe" in payload:
                    # Volver a recibir todos los eventos
                    async with ws_manager._lock:
                        ws_manager._active_connections[websocket] = set()
                    await ws_manager.send_to(websocket, {
                        "event": "unsubscribed",
                        "message": "Recibiendo todos los eventos",
                        "timestamp": datetime.now().isoformat(),
                    })
            except json.JSONDecodeError:
                await ws_manager.send_to(websocket, {
                    "event": "error",
                    "message": f"Mensaje no reconocido: {message}",
                    "timestamp": datetime.now().isoformat(),
                })

    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Error en WebSocket: {e}")
        await ws_manager.disconnect(websocket)
