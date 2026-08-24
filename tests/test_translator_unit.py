"""Unit tests for the translator, using a mocked HTTP transport.

No API key and no tokens are needed for these tests.
"""

import json

import httpx
import pytest

from ir.models import TranslationResult
from translator import TranslationError, Translator

MOVE_COMMAND = {
    "operation": "move",
    "source": "people",
    "destination": "pension",
    "condition": {"field": "age", "operator": ">", "value": 60},
}


def make_translator(handler, **kwargs):
    return Translator(api_key="test-key", transport=httpx.MockTransport(handler), **kwargs)


def chat_response(body: dict | str) -> httpx.Response:
    content = body if isinstance(body, str) else json.dumps(body)
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_translate_complete_move():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        assert request.headers["Authorization"] == "Bearer test-key"
        sent = json.loads(request.content)
        assert sent["response_format"] == {"type": "json_object"}
        return chat_response({"status": "complete", "command": MOVE_COMMAND})

    with make_translator(handler) as translator:
        result = translator.translate("Move everyone aged above 60 to pension.")

    assert result.status == "complete"
    assert result.command.operation == "move"
    assert result.command.source == "people"
    assert result.command.destination == "pension"
    assert result.command.condition.field == "age"
    assert result.command.condition.operator == ">"
    assert result.command.condition.value == 60


def test_translate_clarification():
    def handler(request: httpx.Request) -> httpx.Response:
        return chat_response(
            {
                "status": "needs_clarification",
                "clarification": {
                    "message": 'What minimum age counts as "old"?',
                    "missing": ["condition.value"],
                },
            }
        )

    with make_translator(handler) as translator:
        result = translator.translate("Move all the old people to pension.")

    assert result.status == "needs_clarification"
    assert result.clarification.message
    assert "condition.value" in result.clarification.missing


def test_non_json_output_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return chat_response("Sorry, I can only help with database tasks.")

    with make_translator(handler) as translator:
        with pytest.raises(TranslationError):
            translator.translate("Move people to pension.")


def test_structurally_invalid_json_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return chat_response({"status": "complete", "command": {"operation": "move", "banana": "hello"}})

    with make_translator(handler) as translator:
        with pytest.raises(TranslationError):
            translator.translate("Move people to pension.")


def test_http_error_is_wrapped():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid api key"})

    with make_translator(handler) as translator:
        with pytest.raises(TranslationError):
            translator.translate("Move people to pension.")


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    translator = Translator(api_key=None, transport=httpx.MockTransport(lambda r: r))
    with pytest.raises(TranslationError):
        translator.translate("Move people to pension.")
    translator.close()


def test_retries_once_on_invalid_json():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return chat_response("not json at all")
        return chat_response({"status": "complete", "command": MOVE_COMMAND})

    with make_translator(handler) as translator:
        result = translator.translate("Move everyone aged above 60 to pension.")

    assert result.status == "complete"
    assert calls["n"] == 2


def test_retries_once_on_schema_mismatch():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return chat_response(
                {"status": "complete", "command": {"operation": "move", "banana": "x"}}
            )
        return chat_response({"status": "complete", "command": MOVE_COMMAND})

    with make_translator(handler) as translator:
        result = translator.translate("Move everyone aged above 60 to pension.")

    assert result.command.source == "people"
    assert calls["n"] == 2


def test_tolerates_stray_trailing_brace():
    """DeepSeek sometimes emits an extra '}' after valid JSON — accept the first value."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        content = json.dumps({"status": "complete", "command": MOVE_COMMAND}) + "}"
        return chat_response(content)

    with make_translator(handler) as translator:
        result = translator.translate("Move everyone aged above 60 to pension.")

    assert result.status == "complete"
    assert result.command.condition.value == 60
    assert calls["n"] == 1
