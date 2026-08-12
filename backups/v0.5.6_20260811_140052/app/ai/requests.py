from __future__ import annotations

from threading import Event, Lock
import time


_lock = Lock()
_requests: dict[str, dict] = {}


def register_ai_request(request_id: str) -> Event:
    request_id = str(request_id or "").strip()
    if not request_id:
        raise ValueError("AI request id is required.")

    event = Event()
    with _lock:
        _requests[request_id] = {
            "cancel_event": event,
            "created_at": time.monotonic(),
        }
        _prune_locked()
    return event


def cancel_ai_request(request_id: str) -> bool:
    request_id = str(request_id or "").strip()
    if not request_id:
        return False

    with _lock:
        row = _requests.get(request_id)
        if row is None:
            return False
        event = row["cancel_event"]
        event.set()
        return True


def finish_ai_request(request_id: str) -> None:
    with _lock:
        _requests.pop(str(request_id or "").strip(), None)


def _prune_locked(max_age_seconds: float = 1800.0) -> None:
    now = time.monotonic()
    stale = [
        request_id
        for request_id, row in _requests.items()
        if now - float(row.get("created_at", now)) > max_age_seconds
    ]
    for request_id in stale:
        _requests.pop(request_id, None)
