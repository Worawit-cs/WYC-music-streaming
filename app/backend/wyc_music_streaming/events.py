"""In-process pub/sub for Server-Sent Events, one channel per user."""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

log = logging.getLogger(__name__)


class EventBroker:
    def __init__(self, maxsize: int = 100):
        self._maxsize = maxsize
        self._subs: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)

    def subscribe(self, user: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._maxsize)
        self._subs[user].add(queue)
        return queue

    def unsubscribe(self, user: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        subs = self._subs.get(user)
        if subs is None:
            return
        subs.discard(queue)
        if not subs:
            del self._subs[user]

    def publish(self, user: str, type_: str, data: Any) -> None:
        event = {"type": type_, "data": data}
        for queue in list(self._subs.get(user, ())):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                log.debug("dropping %s event for slow client of %s", type_, user)


def format_sse(event: dict[str, Any]) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
