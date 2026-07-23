"""Thin, provider-abstracted LLM client for the narrative-generating agents (A2's
optional description, A3, A4 -- docs/INTERPOSE_SCOPING.md Sections 7.7-7.10).

Section 6.4 names Anthropic Claude as the eventual default LLM provider, but also
explicitly calls out Groq as an anticipated swap-in alternative -- which is exactly
what's configured here for now, for a concrete, practical reason: Groq has a genuinely
free tier, and this project's owner doesn't want per-call billing during development.
Swapping to Claude later means implementing `generate_structured`'s same signature
against the `anthropic` SDK instead of `groq`'s -- agent code (interpose.control_plane
.agents.*) never imports `groq` directly and would need zero changes.

`generate_structured` uses Groq's structured-output mode (`response_format={"type":
"json_schema", ..., "strict": True}`) rather than looser prompt-and-hope JSON mode --
this is what Section 7's "Structured JSON output constrained by Pydantic; no
free-form response" actually requires: the model is constrained to the schema at
generation time, not just asked nicely to produce JSON and validated after the fact.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from groq import AsyncGroq
from pydantic import BaseModel, ValidationError

from interpose.config import get_settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Raised when the LLM call fails outright, or its output doesn't validate
    against the expected schema. Callers (the agents) decide what that means for
    their own operation -- e.g. Agent A2's narrative is optional and can be skipped
    on failure; A3's narrative is not optional."""


def _strict_schema(schema: dict) -> dict:
    """Groq (like OpenAI) requires `additionalProperties: false` on every object in
    a strict-mode JSON schema -- Pydantic's `model_json_schema()` doesn't set this by
    default. Discovered by actually calling the real API (a live smoke test caught
    this; the mocked unit tests couldn't have, since they never sent a schema
    anywhere real enough to reject it)."""
    if schema.get("type") == "object":
        schema = {**schema, "additionalProperties": False}
    for key in ("properties", "$defs"):
        if key in schema:
            schema = {**schema, key: {k: _strict_schema(v) for k, v in schema[key].items()}}
    return schema


async def generate_structured[T: BaseModel](
    *,
    system_prompt: str,
    user_prompt: str,
    output_model: type[T],
    max_tokens: int = 500,
    temperature: float = 0.2,
) -> T:
    settings = get_settings()
    if not settings.groq_api_key:
        raise LLMError("GROQ_API_KEY is not configured")

    client = AsyncGroq(api_key=settings.groq_api_key)
    schema = _strict_schema(output_model.model_json_schema())
    try:
        response = await client.chat.completions.create(
            model=settings.groq_model,
            temperature=temperature,
            max_completion_tokens=max_tokens,
            # gpt-oss models spend part of the token budget on hidden reasoning
            # before producing output -- at the default effort level, that reasoning
            # alone can exhaust max_completion_tokens before any JSON is emitted at
            # all (discovered via a live smoke test, not something a mocked test
            # could have caught). These are short, low-ambiguity structured-output
            # tasks; "low" is enough reasoning for them and leaves the token budget
            # for the actual output.
            reasoning_effort="low",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": output_model.__name__,
                    "schema": schema,
                    "strict": True,
                },
            },
        )
    except Exception as exc:
        raise LLMError(f"LLM request failed: {exc}") from exc

    raw = response.choices[0].message.content
    try:
        return output_model.model_validate_json(raw)
    except ValidationError as exc:
        raise LLMError(f"LLM output failed schema validation: {exc}\nraw={raw!r}") from exc


# The type every agent's LLM dependency actually needs -- lets tests inject a fake
# implementation (no network, deterministic) instead of patching module internals.
GenerateFn = Callable[..., Awaitable[BaseModel]]
