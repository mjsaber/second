"""Multi-provider LLM integration for meeting summarization.

Supports multiple LLM providers (Claude, OpenAI, Gemini, Ollama) for generating
structured meeting summaries from diarized transcripts.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

try:
    from enum import StrEnum
except ImportError:
    from enum import Enum as _Enum

    StrEnum = _Enum("StrEnum", {}, type=str)


class LLMProvider(StrEnum):
    """Supported LLM providers."""

    CLAUDE = "claude"
    OPENAI = "openai"
    GEMINI = "gemini"
    OLLAMA = "ollama"


SUMMARY_SYSTEM_PROMPT = """\
You are a meeting summarization assistant. Given a diarized transcript, \
produce a structured meeting summary in Markdown using exactly this format:

# Meeting: [Participant1] & [Participant2] — YYYY-MM-DD

## Participants
- Name (Role if known)

## Summary
[2-3 sentence overview]

## Key Discussion Points
- [Topic]: [Details with speaker attribution]

## Action Items
- [ ] [Name]: [Action item]

## Notes
[Additional context]

Rules:
- Extract participant names from the transcript speaker labels.
- Attribute key points and action items to specific speakers.
- Keep the summary concise but comprehensive.
- Use the exact section headers shown above.\
"""


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
            ValueError: If the provider is not supported or API key is missing.
            ConnectionError: If the LLM API is unreachable.
            RuntimeError: If the required SDK is not installed.
        """
        if request.provider == LLMProvider.CLAUDE:
            return self._summarize_claude(request)
        elif request.provider == LLMProvider.OPENAI:
            return self._summarize_openai(request)
        elif request.provider == LLMProvider.GEMINI:
            return self._summarize_gemini(request)
        elif request.provider == LLMProvider.OLLAMA:
            return self._summarize_ollama(request)
        else:
            raise ValueError(f"Unsupported provider: {request.provider}")

    def _summarize_claude(self, request: SummarizationRequest) -> SummarizationResult:
        """Call Claude API for summarization."""
        if not request.api_key:
            raise ValueError("API key required for claude")

        try:
            import anthropic  # type: ignore[import-not-found]
        except ImportError:
            raise RuntimeError("anthropic is not installed. Run: pip install anthropic")

        try:
            client = anthropic.Anthropic(api_key=request.api_key)
            response = client.messages.create(
                model=request.model,
                max_tokens=4096,
                system=SUMMARY_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": f"Summarize this transcript:\n\n{request.transcript}",
                    }
                ],
            )
        except Exception as e:
            raise ConnectionError(f"Failed to connect to claude: {e}") from e

        return SummarizationResult(
            markdown=response.content[0].text,
            provider=request.provider,
            model=request.model,
            token_count=response.usage.input_tokens + response.usage.output_tokens,
        )

    def _summarize_openai(self, request: SummarizationRequest) -> SummarizationResult:
        """Call OpenAI API for summarization."""
        if not request.api_key:
            raise ValueError("API key required for openai")

        try:
            import openai  # type: ignore[import-not-found]
        except ImportError:
            raise RuntimeError("openai is not installed. Run: pip install openai")

        try:
            client = openai.OpenAI(api_key=request.api_key)
            response = client.chat.completions.create(
                model=request.model,
                messages=[
                    {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Summarize this transcript:\n\n{request.transcript}",
                    },
                ],
            )
        except Exception as e:
            raise ConnectionError(f"Failed to connect to openai: {e}") from e

        return SummarizationResult(
            markdown=response.choices[0].message.content,
            provider=request.provider,
            model=request.model,
            token_count=response.usage.prompt_tokens + response.usage.completion_tokens,
        )

    def _summarize_gemini(self, request: SummarizationRequest) -> SummarizationResult:
        """Call Google Gemini API for summarization."""
        if not request.api_key:
            raise ValueError("API key required for gemini")

        try:
            import google.generativeai as genai  # type: ignore[import-not-found]
        except ImportError:
            raise RuntimeError(
                "google-generativeai is not installed. Run: pip install google-generativeai"
            )

        try:
            genai.configure(api_key=request.api_key)
            model = genai.GenerativeModel(request.model)
            response = model.generate_content(
                f"{SUMMARY_SYSTEM_PROMPT}\n\nSummarize this transcript:\n\n{request.transcript}"
            )
        except Exception as e:
            raise ConnectionError(f"Failed to connect to gemini: {e}") from e

        return SummarizationResult(
            markdown=response.text,
            provider=request.provider,
            model=request.model,
            token_count=(
                response.usage_metadata.prompt_token_count
                + response.usage_metadata.candidates_token_count
            ),
        )

    def _summarize_ollama(self, request: SummarizationRequest) -> SummarizationResult:
        """Call local Ollama instance for summarization."""
        url = "http://localhost:11434/api/generate"
        prompt = f"{SUMMARY_SYSTEM_PROMPT}\n\nSummarize this transcript:\n\n{request.transcript}"
        payload = json.dumps(
            {
                "model": request.model,
                "prompt": prompt,
                "stream": False,
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise ConnectionError(f"Failed to connect to ollama: {e}") from e

        return SummarizationResult(
            markdown=data["response"],
            provider=request.provider,
            model=request.model,
            token_count=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
        )
