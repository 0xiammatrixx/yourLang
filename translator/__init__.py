"""The LLM translator layer — the only place the LLM appears in the system."""

from .llm import TranslationError, Translator, translate

__all__ = ["TranslationError", "Translator", "translate"]
