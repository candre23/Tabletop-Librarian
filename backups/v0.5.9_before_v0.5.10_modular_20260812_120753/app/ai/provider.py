from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from threading import Event
from typing import Any

from app.config import DATA_DIR

SETTINGS_FILE = DATA_DIR / "ai_provider.json"

class AIRequestCancelled(RuntimeError):
    pass


DEFAULT_SETTINGS = {
    "provider": "openai_compatible",
    "base_url": "",
    "model": "qwen3.5-9b-q5",
    "api_key": "",
    "timeout": 120,
    "temperature": 0.2,
    "max_tokens": 1200,
}


def load_provider_settings() -> dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    if SETTINGS_FILE.exists():
        try:
            stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                settings.update(stored)
        except Exception:
            pass

    settings["base_url"] = str(settings.get("base_url", "")).rstrip("/")
    settings["model"] = str(settings.get("model", DEFAULT_SETTINGS["model"])).strip()
    settings["api_key"] = str(settings.get("api_key", "")).strip()

    try:
        settings["timeout"] = max(5, min(600, int(settings.get("timeout", 120))))
    except Exception:
        settings["timeout"] = 120

    try:
        settings["temperature"] = max(0.0, min(2.0, float(settings.get("temperature", 0.2))))
    except Exception:
        settings["temperature"] = 0.2

    try:
        settings["max_tokens"] = max(64, min(8192, int(settings.get("max_tokens", 1200))))
    except Exception:
        settings["max_tokens"] = 1200

    return settings


def provider_settings_for_ui() -> dict[str, Any]:
    settings = load_provider_settings()
    return {
        "provider": settings["provider"],
        "base_url": settings["base_url"],
        "model": settings["model"],
        "timeout": settings["timeout"],
        "temperature": settings["temperature"],
        "max_tokens": settings["max_tokens"],
        "has_api_key": bool(settings["api_key"]),
        "configured": bool(settings["base_url"] and settings["model"]),
    }


def save_provider_settings(*, base_url: str, model: str, api_key: str = "", timeout: int | str = 120, temperature: float | str = 0.2, max_tokens: int | str = 1200) -> dict[str, Any]:
    current = load_provider_settings()
    base_url = str(base_url or "").strip().rstrip("/")
    model = str(model or "").strip()

    if not base_url:
        raise ValueError("Base URL is required.")
    if not (base_url.startswith("http://") or base_url.startswith("https://")):
        raise ValueError("Base URL must begin with http:// or https://.")
    if not model:
        raise ValueError("Model name is required.")

    try:
        timeout_value = max(5, min(600, int(timeout)))
    except Exception as exc:
        raise ValueError("Timeout must be a whole number of seconds.") from exc

    try:
        temperature_value = max(0.0, min(2.0, float(temperature)))
    except Exception as exc:
        raise ValueError("Temperature must be a number from 0 to 2.") from exc

    try:
        max_tokens_value = max(64, min(8192, int(max_tokens)))
    except Exception as exc:
        raise ValueError("Maximum output tokens must be a whole number.") from exc

    submitted_key = str(api_key or "").strip()
    settings = {
        "provider": "openai_compatible",
        "base_url": base_url,
        "model": model,
        "api_key": submitted_key or current.get("api_key", ""),
        "timeout": timeout_value,
        "temperature": temperature_value,
        "max_tokens": max_tokens_value,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = SETTINGS_FILE.with_suffix(".json.tmp")
    temp_file.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    os.chmod(temp_file, 0o600)
    temp_file.replace(SETTINGS_FILE)
    os.chmod(SETTINGS_FILE, 0o600)
    return settings


def _request_json(method: str, url: str, *, payload: dict[str, Any] | None = None, timeout: int | None = None) -> dict[str, Any]:
    settings = load_provider_settings()
    headers = {"Accept": "application/json"}
    if settings["api_key"]:
        headers["Authorization"] = f"Bearer {settings['api_key']}"

    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(request, timeout=timeout or settings["timeout"]) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Provider returned HTTP {exc.code}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach AI provider: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("AI provider request timed out.") from exc

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("AI provider returned invalid JSON.") from exc

    if not isinstance(result, dict):
        raise RuntimeError("AI provider returned an unexpected response.")
    return result


def test_provider_connection() -> dict[str, Any]:
    settings = load_provider_settings()
    if not settings["base_url"]:
        raise RuntimeError("AI provider is not configured.")

    result = _request_json("GET", f"{settings['base_url']}/models", timeout=min(settings["timeout"], 20))
    models = []
    for item in result.get("data", []):
        if isinstance(item, dict) and item.get("id"):
            models.append(str(item["id"]))

    return {"ok": True, "models": models, "configured_model": settings["model"]}


def provider_health_check(*, timeout: float = 2.0) -> dict[str, Any]:
    """Fast reachability check used before any user-facing generation request."""
    settings = load_provider_settings()
    if not settings["base_url"]:
        return {
            "ok": False,
            "configured": False,
            "message": "AI backend is not configured.",
        }

    try:
        result = _request_json(
            "GET",
            f"{settings['base_url']}/models",
            timeout=max(0.5, min(float(timeout), 5.0)),
        )
    except Exception as exc:
        return {
            "ok": False,
            "configured": True,
            "message": f"AI backend is unavailable: {exc}",
        }

    models = [
        str(item.get("id"))
        for item in result.get("data", [])
        if isinstance(item, dict) and item.get("id")
    ]
    return {
        "ok": True,
        "configured": True,
        "message": "AI backend is available.",
        "models": models,
        "configured_model": settings["model"],
    }


def _streaming_chat_completion(
    messages: list[dict[str, str]],
    *,
    cancel_event: Event,
) -> dict[str, Any]:
    """OpenAI-compatible streaming request that can be interrupted by TTL."""
    settings = load_provider_settings()
    if not settings["base_url"]:
        raise RuntimeError("AI provider is not configured.")

    payload = {
        "model": settings["model"],
        "messages": messages,
        "temperature": settings["temperature"],
        "max_tokens": settings["max_tokens"],
        "stream": True,
    }

    headers = {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
    }
    if settings["api_key"]:
        headers["Authorization"] = f"Bearer {settings['api_key']}"

    request = urllib.request.Request(
        f"{settings['base_url']}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    parts: list[str] = []
    response_model = settings["model"]
    usage: dict[str, Any] = {}

    try:
        with urllib.request.urlopen(request, timeout=settings["timeout"]) as response:
            while True:
                if cancel_event.is_set():
                    # Exiting the response context closes the client socket. Most
                    # OpenAI-compatible local servers, including llama.cpp, stop
                    # generation when the streaming client disconnects.
                    raise AIRequestCancelled("AI request cancelled.")

                raw_line = response.readline()
                if not raw_line:
                    break

                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue

                data = line[5:].strip()
                if data == "[DONE]":
                    break

                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue

                if isinstance(event.get("model"), str):
                    response_model = event["model"]

                if isinstance(event.get("usage"), dict):
                    usage = event["usage"]

                choices = event.get("choices")
                if not isinstance(choices, list) or not choices:
                    continue

                choice = choices[0] if isinstance(choices[0], dict) else {}
                delta = choice.get("delta")
                if isinstance(delta, dict):
                    content = delta.get("content")
                    if isinstance(content, str):
                        parts.append(content)
                else:
                    # Some compatible servers stream a message/text shape.
                    message = choice.get("message")
                    if isinstance(message, dict) and isinstance(message.get("content"), str):
                        parts.append(message["content"])
                    elif isinstance(choice.get("text"), str):
                        parts.append(choice["text"])

    except AIRequestCancelled:
        raise
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Provider returned HTTP {exc.code}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach AI provider: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("AI provider request timed out.") from exc

    if cancel_event.is_set():
        raise AIRequestCancelled("AI request cancelled.")

    content = "".join(parts).strip()
    if not content:
        raise RuntimeError("AI provider returned an empty response.")

    return {
        "content": content,
        "model": response_model,
        "usage": usage,
    }


def chat_completion(
    messages: list[dict[str, str]],
    *,
    cancel_event: Event | None = None,
) -> dict[str, Any]:
    if cancel_event is not None:
        return _streaming_chat_completion(
            messages,
            cancel_event=cancel_event,
        )

    settings = load_provider_settings()
    if not settings["base_url"]:
        raise RuntimeError("AI provider is not configured.")

    payload = {
        "model": settings["model"],
        "messages": messages,
        "temperature": settings["temperature"],
        "max_tokens": settings["max_tokens"],
        "stream": False,
    }

    result = _request_json("POST", f"{settings['base_url']}/chat/completions", payload=payload)
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("AI provider returned no completion choices.")

    message = choices[0].get("message", {})
    content = message.get("content", "")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("AI provider returned an empty response.")

    return {
        "content": content.strip(),
        "model": result.get("model", settings["model"]),
        "usage": result.get("usage") or {},
    }
