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
            "progress": 12,
            "stage": "Preparing request",
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


def update_ai_request_progress(
    request_id: str,
    progress: int,
    stage: str,
) -> None:
    request_id = str(request_id or "").strip()
    if not request_id:
        return

    try:
        progress = max(0, min(99, int(progress)))
    except (TypeError, ValueError):
        progress = 0

    with _lock:
        row = _requests.get(request_id)
        if row is None:
            return
        row["progress"] = progress
        row["stage"] = str(stage or "").strip() or "Working"


def ai_request_progress(request_id: str) -> dict:
    request_id = str(request_id or "").strip()
    if not request_id:
        return {"active": False}

    with _lock:
        row = _requests.get(request_id)
        if row is None:
            return {"active": False}
        return {
            "active": True,
            "cancelled": bool(row["cancel_event"].is_set()),
            "progress": int(row.get("progress", 0)),
            "stage": str(row.get("stage") or "Working"),
        }


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
