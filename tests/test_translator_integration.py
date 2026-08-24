"""Integration tests against the live DeepSeek API.

These run only when DEEPSEEK_API_KEY is set (e.g. loaded from .env).
Run with:  .venv/bin/python -m pytest tests/test_translator_integration.py -v
"""

import os

import pytest

from translator import translate

pytestmark = pytest.mark.integration

requires_key = pytest.mark.skipif(
    not os.getenv("DEEPSEEK_API_KEY"),
    reason="DEEPSEEK_API_KEY not set (create .env from .env.example)",
)


@requires_key
def test_real_translate_move():
    result = translate("Move everyone aged above 60 to collection pension.")
    assert result.status == "complete"
    assert result.command.operation == "move"
    assert result.command.source == "people"
    assert result.command.destination == "pension"
    assert result.command.condition.field == "age"
    assert result.command.condition.operator == ">"
    assert result.command.condition.value == 60


@requires_key
def test_real_ambiguity_requests_clarification():
    result = translate("Move all the old people to pension.")
    # The system must not silently guess; asking (clarify) or proposing a
    # best guess for confirmation are both valid.
    assert result.status in ("needs_clarification", "needs_confirmation")
    assert result.clarification.message
