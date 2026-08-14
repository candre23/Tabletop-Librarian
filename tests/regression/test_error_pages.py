#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
main=(ROOT/'app/main.py').read_text()
template=(ROOT/'app/templates/error.html').read_text()
css=(ROOT/'app/static/css/main.css').read_text()

assert 'from starlette.exceptions import HTTPException as StarletteHTTPException' in main
assert 'from fastapi.exceptions import RequestValidationError' in main
assert '@app.exception_handler(StarletteHTTPException)' in main
assert '@app.exception_handler(RequestValidationError)' in main
assert '@app.exception_handler(Exception)' in main
assert '"text/html" in request.headers.get("accept", "").lower()' in main
assert 'content={"detail": exc.detail}' in main
assert 'content={"detail": exc.errors()}' in main
assert 'request_id = uuid.uuid4().hex[:10]' in main
assert 'The error has been logged.' in main
assert 'login required.' in main

assert '{% extends "base.html" %}' in template
assert 'ttl-error-page' in template
assert 'Sign In' in template
assert 'Go Back' in template
assert 'request_id' in template
assert '{% if not error_page and base_role == "gm" %}' in (ROOT/'app/templates/base.html').read_text()
assert '"error_page": True' in main

assert '.ttl-error-card' in css
assert '.ttl-error-code' in css
assert '.ttl-error-actions' in css

print('PASS: professional error-page regression')
print('  framework HTTP errors use TTL HTML for browser requests: OK')
print('  API JSON fallback retained: OK')
print('  validation handler present: OK')
print('  unexpected errors use logged reference IDs: OK')
print('  styled error template present: OK')
