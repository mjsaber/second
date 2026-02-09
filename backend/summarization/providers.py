"""Multi-provider LLM integration for meeting summarization.

Supports multiple LLM providers (Claude, OpenAI, Ollama) for generating
structured meeting summaries from diarized transcripts.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LLMProvider(StrEnum):
    """Supported LLM providers."""

    CLAUDE = "claude"
    OPENAI = "openai"
    OLLAMA = "ollama"


@dataclass
class SummarizationRequest:
    """Request to generate a meeting summary.

    Attributes:
        transcript: Full diarized transcript text.
        provider: Which LLM provider to use.
        model: Specific model identifier.
        api_key: API key for the provider (not needed for Ollama).
    """

    transcript: str
    provider: LLMProvider
    model: str
    api_key: str | None = None


@dataclass
class SummarizationResult:
    """Generated meeting summary.

    Attributes:
        markdown: The summary in Markdown format.
        provider: Which provider generated it.
        model: Which model was used.
        token_count: Total tokens used (prompt + completion).
    """

    markdown: str
    provider: LLMProvider
    model: str
    token_count: int


class SummarizationService:
    """Generates meeting summaries using configurable LLM providers.

    Usage:
        service = SummarizationService()
        result = service.summarize(SummarizationRequest(
            transcript="Alice: Let's discuss the roadmap...",
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-4-5-20250929",
            api_key="sk-...",
        ))
    """

    def summarize(self, request: SummarizationRequest) -> SummarizationResult:
        """Generate a meeting summary from a transcript.

        Args:
            request: Summarization parameters including transcript and provider config.

        Returns:
            The generated summary with metadata.

        Raises:
            ValueError: If the provider is not supported.
            ConnectionError: If the LLM API is unreachable.
        """
        if request.provider == LLMProvider.CLAUDE:
            return self._summarize_claude(request)
        elif request.provider == LLMProvider.OPENAI:
            return self._summarize_openai(request)
        elif request.provider == LLMProvider.OLLAMA:
            return self._summarize_ollama(request)
        else:
            raise ValueError(f"Unsupported provider: {request.provider}")

    def _summarize_claude(self, request: SummarizationRequest) -> SummarizationResult:
        """Call Claude API for summarization."""
        # Stub — will use anthropic SDK
        return SummarizationResult(
            markdown="", provider=request.provider, model=request.model, token_count=0
        )

    def _summarize_openai(self, request: SummarizationRequest) -> SummarizationResult:
        """Call OpenAI API for summarization."""
        # Stub — will use openai SDK
        return SummarizationResult(
            markdown="", provider=request.provider, model=request.model, token_count=0
        )

    def _summarize_ollama(self, request: SummarizationRequest) -> SummarizationResult:
        """Call local Ollama instance for summarization."""
        # Stub — will use HTTP requests to localhost
        return SummarizationResult(
            markdown="", provider=request.provider, model=request.model, token_count=0
        )
