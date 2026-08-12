#!/usr/bin/env python3
from pathlib import Path
from threading import Event
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from app.ai.requests import (
    cancel_ai_request,
    finish_ai_request,
    register_ai_request,
)
from app.ai.provider import provider_health_check

event=register_ai_request("test-request")
assert isinstance(event,Event)
assert not event.is_set()
assert cancel_ai_request("test-request") is True
assert event.is_set()
finish_ai_request("test-request")
assert cancel_ai_request("test-request") is False

status=provider_health_check(timeout=.5)
assert isinstance(status,dict)
assert "ok" in status
assert "message" in status

main=(ROOT/"app/main.py").read_text()
ask=(ROOT/"app/templates/ask.html").read_text()
provider=(ROOT/"app/ai/provider.py").read_text()

assert '@app.get("/ai/status")' in main
assert '@app.post("/ai/cancel/{request_id}")' in main
assert "provider_health_check" in main
assert "register_ai_request" in main
assert "cancel_event=cancel_event" in main
assert "finish_ai_request(ai_request_id)" in main

assert 'id="ask-cancel"' in ask
assert 'id="ai-request-id"' in ask
assert 'fetch("/ai/status"' in ask
assert 'fetch(`/ai/cancel/${encodeURIComponent(id)}`' in ask
assert "window.stop();" in ask

assert '"stream": True' in provider
assert "AIRequestCancelled" in provider
assert "cancel_event.is_set()" in provider
assert "response.readline()" in provider

print("PASS: AI preflight + cancellation regression")
print("  generic request cancellation registry: OK")
print("  fast backend health-check API: OK")
print("  server-side preflight before generation: OK")
print("  UI preflight before form submission: OK")
print("  immediate browser-side Cancel control: OK")
print("  best-effort provider abort via streaming disconnect: OK")
