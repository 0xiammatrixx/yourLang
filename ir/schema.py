"""Export the IR as a JSON Schema.

The same schema is used for:
1. Prompting the LLM ("translate into exactly this representation"),
2. Documenting the IR in the paper.
"""

import json

from .models import TranslationResult


def json_schema() -> dict:
    """JSON Schema of the LLM-facing IR (`TranslationResult`)."""
    return TranslationResult.model_json_schema()


def json_schema_string(indent: int | None = None) -> str:
    """The schema serialized as a JSON string (for embedding in prompts)."""
    return json.dumps(json_schema(), indent=indent)
