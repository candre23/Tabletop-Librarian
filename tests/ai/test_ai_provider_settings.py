from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import app.ai.provider as provider


class _Response:
    def __init__(self, body: dict):
        self._body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self._body


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ttl-provider-test-") as td:
        provider.SETTINGS_FILE = Path(td) / "ai_provider.json"

        google = provider.save_provider_settings(
            provider="google_gemini",
            base_url="",
            model="gemini-test",
            api_key="google-key",
        )
        assert google["base_url"] == "https://generativelanguage.googleapis.com/v1beta/openai"

        captured: dict[str, str] = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["authorization"] = request.headers.get("Authorization", "")
            return _Response({"data": [{"id": "gemini-test"}]})

        with patch("urllib.request.urlopen", fake_urlopen):
            result = provider.test_provider_connection()

        assert captured["url"] == "https://generativelanguage.googleapis.com/v1beta/openai/models"
        assert captured["authorization"] == "Bearer google-key"
        assert result["models"] == ["gemini-test"]

        try:
            provider.save_provider_settings(
                provider="openai",
                base_url="",
                model="gpt-test",
                api_key="",
            )
        except ValueError as exc:
            assert "API key" in str(exc)
        else:
            raise AssertionError("Switching hosted providers must require the new provider's API key")

        openai = provider.save_provider_settings(
            provider="openai",
            base_url="",
            model="gpt-test",
            api_key="openai-key",
        )
        assert openai["base_url"] == "https://api.openai.com/v1"

        local = provider.save_provider_settings(
            provider="openai_compatible",
            base_url="http://127.0.0.1:8080/v1",
            model="local-test",
            api_key="",
        )
        assert local["base_url"] == "http://127.0.0.1:8080/v1"
        assert local["provider"] == "openai_compatible"

    print("v1.0.0 AI provider regression tests passed.")


if __name__ == "__main__":
    main()
