"""Tests for the summarization providers module."""

from __future__ import annotations

from summarization.providers import (
    LLMProvider,
    SummarizationRequest,
    SummarizationResult,
    SummarizationService,
)


class TestSummarizationService:
    """Tests for SummarizationService provider routing."""

    def test_summarize_claude_returns_result(self) -> None:
        """Verify that Claude provider returns a SummarizationResult."""
        service = SummarizationService()
        request = SummarizationRequest(
            transcript="Alice: Hello. Bob: Hi.",
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-4-5-20250929",
            api_key="sk-test",
        )
        result = service.summarize(request)
        assert isinstance(result, SummarizationResult)
        assert result.provider == LLMProvider.CLAUDE

    def test_summarize_openai_returns_result(self) -> None:
        """Verify that OpenAI provider returns a SummarizationResult."""
        service = SummarizationService()
        request = SummarizationRequest(
            transcript="Alice: Hello.",
            provider=LLMProvider.OPENAI,
            model="gpt-4o",
            api_key="sk-test",
        )
        result = service.summarize(request)
        assert result.provider == LLMProvider.OPENAI

    def test_summarize_ollama_returns_result(self) -> None:
        """Verify that Ollama provider returns a SummarizationResult (no API key needed)."""
        service = SummarizationService()
        request = SummarizationRequest(
            transcript="Alice: Hello.",
            provider=LLMProvider.OLLAMA,
            model="llama3",
        )
        result = service.summarize(request)
        assert result.provider == LLMProvider.OLLAMA


class TestLLMProvider:
    """Tests for the LLMProvider enum."""

    def test_provider_values(self) -> None:
        """Verify that provider enum values are the expected strings."""
        assert LLMProvider.CLAUDE == "claude"
        assert LLMProvider.OPENAI == "openai"
        assert LLMProvider.OLLAMA == "ollama"


class TestSummarizationRequest:
    """Tests for the SummarizationRequest data class."""

    def test_api_key_defaults_to_none(self) -> None:
        """Verify that api_key is optional and defaults to None."""
        req = SummarizationRequest(
            transcript="test",
            provider=LLMProvider.OLLAMA,
            model="llama3",
        )
        assert req.api_key is None
