"""Unit tests for interpose.control_plane.llm -- the Groq client wrapper's own
logic (schema request shape, response parsing, error handling), with the actual
`AsyncGroq` client mocked out. No real network calls, no API key needed -- this is
exactly why agents depend on `generate_structured` rather than calling Groq directly:
one place to mock, everywhere it's used.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from interpose.config import Settings
from interpose.control_plane.llm import LLMError, _strict_schema, generate_structured


class _Output(BaseModel):
    narrative: str
    confidence: float


class _Nested(BaseModel):
    inner: _Output
    label: str


def _mock_completion(content: str) -> MagicMock:
    message = MagicMock(content=content)
    choice = MagicMock(message=message)
    return MagicMock(choices=[choice])


def _fake_settings(api_key: str | None = "test-key") -> Settings:
    return Settings(groq_api_key=api_key, groq_model="openai/gpt-oss-20b")


async def test_returns_validated_model_on_valid_json_response() -> None:
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_completion('{"narrative": "all clear", "confidence": 0.9}')
    )
    with (
        patch("interpose.control_plane.llm.get_settings", return_value=_fake_settings()),
        patch("interpose.control_plane.llm.AsyncGroq", return_value=mock_client),
    ):
        result = await generate_structured(
            system_prompt="system", user_prompt="user", output_model=_Output
        )
    assert result == _Output(narrative="all clear", confidence=0.9)


async def test_requests_strict_json_schema_response_format() -> None:
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_completion('{"narrative": "x", "confidence": 0.1}')
    )
    with (
        patch("interpose.control_plane.llm.get_settings", return_value=_fake_settings()),
        patch("interpose.control_plane.llm.AsyncGroq", return_value=mock_client),
    ):
        await generate_structured(system_prompt="s", user_prompt="u", output_model=_Output)

    _, kwargs = mock_client.chat.completions.create.call_args
    response_format = kwargs["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["name"] == "_Output"
    # Regression test for a real API rejection a live smoke test caught: Groq's
    # strict mode requires additionalProperties: false on every object, which
    # Pydantic's model_json_schema() doesn't set on its own.
    assert response_format["json_schema"]["schema"]["additionalProperties"] is False


async def test_uses_low_reasoning_effort_to_leave_budget_for_actual_output() -> None:
    # Also a live-smoke-test-driven fix: gpt-oss models spend part of the token
    # budget on hidden reasoning before producing output; at default effort, that
    # alone exhausted max_completion_tokens before any JSON was emitted.
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_completion('{"narrative": "x", "confidence": 0.1}')
    )
    with (
        patch("interpose.control_plane.llm.get_settings", return_value=_fake_settings()),
        patch("interpose.control_plane.llm.AsyncGroq", return_value=mock_client),
    ):
        await generate_structured(system_prompt="s", user_prompt="u", output_model=_Output)

    _, kwargs = mock_client.chat.completions.create.call_args
    assert kwargs["reasoning_effort"] == "low"


class TestStrictSchema:
    def test_sets_additional_properties_false_on_top_level_object(self) -> None:
        schema = _strict_schema(_Output.model_json_schema())
        assert schema["additionalProperties"] is False

    def test_sets_additional_properties_false_on_nested_defs(self) -> None:
        schema = _strict_schema(_Nested.model_json_schema())
        assert schema["additionalProperties"] is False
        # Pydantic puts referenced sub-models under $defs; each one is an object
        # that Groq's strict mode also requires additionalProperties: false on.
        for sub_schema in schema.get("$defs", {}).values():
            if sub_schema.get("type") == "object":
                assert sub_schema["additionalProperties"] is False


async def test_raises_llm_error_when_api_key_missing() -> None:
    with patch(
        "interpose.control_plane.llm.get_settings", return_value=_fake_settings(api_key=None)
    ):
        with pytest.raises(LLMError, match="GROQ_API_KEY"):
            await generate_structured(system_prompt="s", user_prompt="u", output_model=_Output)


async def test_raises_llm_error_when_request_itself_fails() -> None:
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("network down"))
    with (
        patch("interpose.control_plane.llm.get_settings", return_value=_fake_settings()),
        patch("interpose.control_plane.llm.AsyncGroq", return_value=mock_client),
    ):
        with pytest.raises(LLMError, match="LLM request failed"):
            await generate_structured(system_prompt="s", user_prompt="u", output_model=_Output)


async def test_raises_llm_error_on_schema_validation_failure() -> None:
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_completion('{"narrative": "missing confidence field"}')
    )
    with (
        patch("interpose.control_plane.llm.get_settings", return_value=_fake_settings()),
        patch("interpose.control_plane.llm.AsyncGroq", return_value=mock_client),
    ):
        with pytest.raises(LLMError, match="schema validation"):
            await generate_structured(system_prompt="s", user_prompt="u", output_model=_Output)
