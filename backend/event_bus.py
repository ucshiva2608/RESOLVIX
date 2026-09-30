"""
Asynchronous Event Bus for real-time Server-Sent Events (SSE) broadcasting.
Allows agents, workflows, and simulators to publish live progress events
to connected SRE Mission Control dashboards.
"""

import asyncio
import json
from typing import Dict, Any, AsyncGenerator
from datetime import datetime, timezone


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class EventBus:
    """Manages active SSE subscriber queues and event broadcasting."""

    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []
        self._history: list[dict] = []
        self._max_history = 100

    async def subscribe(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Create a new subscriber queue and yield SSE messages."""
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(queue)
        try:
            # Yield initial connection confirmation
            yield {
                "event": "connected",
                "data": json.dumps({"status": "CONNECTED", "timestamp": utcnow()})
            }
            while True:
                data = await queue.get()
                yield data
        except asyncio.CancelledError:
            pass
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    async def broadcast(self, event_type: str, payload: Dict[str, Any]):
        """Broadcast an event to all connected subscribers."""
        event_dict = {
            "event": event_type,
            "data": json.dumps({
                "type": event_type,
                "timestamp": utcnow(),
                **payload
            })
        }
        self._history.append(event_dict)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event_dict)
            except Exception:
                # Discard failed queue
                if queue in self._subscribers:
                    self._subscribers.remove(queue)

    def publish_sync(self, event_type: str, payload: Dict[str, Any]):
        """Publish an event synchronously by scheduling it on the running event loop."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.broadcast(event_type, payload))
        except RuntimeError:
            # No running loop, or called from worker thread
            pass


# Global singleton event bus
event_bus = EventBus()
