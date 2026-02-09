"""Tests for the summarization providers module."""

from __future__ import annotations

import types
from unittest.mock import MagicMock, patch

import pytest

from summarization.providers import (
    SUMMARY_SYSTEM_PROMPT,
    LLMProvider,
    SummarizationRequest,
    SummarizationResult,
    SummarizationService,
)


class TestSummarizationService:
    """Tests for SummarizationService provider routing."""

    @pytest.fixture(autouse=True)
    def _mock_providers(self) -> None:  # type: ignore[no-untyped-def]
        """Mock provider internals so tests work without SDKs installed."""
        mock_anthropic = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="")]
        mock_response.usage.input_tokens = 0
        mock_response.usage.output_tokens = 0
        mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_response

        mock_openai = MagicMock()
        mock_oai_response = MagicMock()
        mock_oai_response.choices = [MagicMock(message=MagicMock(content=""))]
        mock_oai_response.usage.prompt_tokens = 0
        mock_oai_response.usage.completion_tokens = 0
        mock_openai.OpenAI.return_value.chat.completions.create.return_value = mock_oai_response

        with (
            patch.dict("sys.modules", {"anthropic": mock_anthropic, "openai": mock_openai}),
            patch("summarization.providers.urllib.request.urlopen") as mock_urlopen,
        ):
            mock_http = MagicMock()
            mock_http.read.return_value = (
                b'{"response": "", "prompt_eval_count": 0, "eval_count": 0}'
            )
            mock_http.__enter__ = lambda s: s
            mock_http.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_http
            yield

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


class TestLLMProviderEnum:
    """Tests for the LLMProvider enum completeness."""

    def test_provider_has_all_expected_values(self) -> None:
        """Verify that LLMProvider has claude, openai, gemini, and ollama."""
        assert LLMProvider.CLAUDE == "claude"
        assert LLMProvider.OPENAI == "openai"
        assert LLMProvider.GEMINI == "gemini"
        assert LLMProvider.OLLAMA == "ollama"

    def test_provider_enum_has_exactly_four_members(self) -> None:
        """Verify that LLMProvider has exactly 4 members."""
        assert len(LLMProvider) == 4


class TestSummarizationResultFields:
    """Tests for SummarizationResult dataclass fields."""

    def test_result_contains_all_expected_fields(self) -> None:
        """Verify SummarizationResult has markdown, provider, model, and token_count."""
        result = SummarizationResult(
            markdown="# Meeting Summary",
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-4-5-20250929",
            token_count=150,
        )
        assert result.markdown == "# Meeting Summary"
        assert result.provider == LLMProvider.CLAUDE
        assert result.model == "claude-sonnet-4-5-20250929"
        assert result.token_count == 150


class TestSummarySystemPrompt:
    """Tests for the SUMMARY_SYSTEM_PROMPT constant."""

    def test_prompt_contains_meeting_header(self) -> None:
        """Verify SUMMARY_SYSTEM_PROMPT instructs to produce a Meeting header."""
        assert "# Meeting:" in SUMMARY_SYSTEM_PROMPT

    def test_prompt_contains_participants_section(self) -> None:
        """Verify SUMMARY_SYSTEM_PROMPT contains Participants section."""
        assert "## Participants" in SUMMARY_SYSTEM_PROMPT

    def test_prompt_contains_summary_section(self) -> None:
        """Verify SUMMARY_SYSTEM_PROMPT contains Summary section."""
        assert "## Summary" in SUMMARY_SYSTEM_PROMPT

    def test_prompt_contains_key_discussion_points_section(self) -> None:
        """Verify SUMMARY_SYSTEM_PROMPT contains Key Discussion Points section."""
        assert "## Key Discussion Points" in SUMMARY_SYSTEM_PROMPT

    def test_prompt_contains_action_items_section(self) -> None:
        """Verify SUMMARY_SYSTEM_PROMPT contains Action Items section."""
        assert "## Action Items" in SUMMARY_SYSTEM_PROMPT

    def test_prompt_contains_notes_section(self) -> None:
        """Verify SUMMARY_SYSTEM_PROMPT contains Notes section."""
        assert "## Notes" in SUMMARY_SYSTEM_PROMPT


class TestSummarizeRouting:
    """Tests for SummarizationService.summarize routing to correct provider method."""

    def test_summarize_routes_to_claude(self) -> None:
        """Verify summarize calls _summarize_claude for Claude provider."""
        service = SummarizationService()
        request = SummarizationRequest(
            transcript="Alice: Hello.",
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-4-5-20250929",
            api_key="sk-test",
        )
        with patch.object(service, "_summarize_claude") as mock_claude:
            mock_claude.return_value = SummarizationResult(
                markdown="test", provider=LLMProvider.CLAUDE, model="test", token_count=0
            )
            service.summarize(request)
            mock_claude.assert_called_once_with(request)

    def test_summarize_routes_to_openai(self) -> None:
        """Verify summarize calls _summarize_openai for OpenAI provider."""
        service = SummarizationService()
        request = SummarizationRequest(
            transcript="Alice: Hello.",
            provider=LLMProvider.OPENAI,
            model="gpt-4o",
            api_key="sk-test",
        )
        with patch.object(service, "_summarize_openai") as mock_openai:
            mock_openai.return_value = SummarizationResult(
                markdown="test", provider=LLMProvider.OPENAI, model="test", token_count=0
            )
            service.summarize(request)
            mock_openai.assert_called_once_with(request)

    def test_summarize_routes_to_gemini(self) -> None:
        """Verify summarize calls _summarize_gemini for Gemini provider."""
        service = SummarizationService()
        request = SummarizationRequest(
            transcript="Alice: Hello.",
            provider=LLMProvider.GEMINI,
            model="gemini-pro",
            api_key="test-key",
        )
        with patch.object(service, "_summarize_gemini") as mock_gemini:
            mock_gemini.return_value = SummarizationResult(
                markdown="test", provider=LLMProvider.GEMINI, model="test", token_count=0
            )
            service.summarize(request)
            mock_gemini.assert_called_once_with(request)

    def test_summarize_routes_to_ollama(self) -> None:
        """Verify summarize calls _summarize_ollama for Ollama provider."""
        service = SummarizationService()
        request = SummarizationRequest(
            transcript="Alice: Hello.",
            provider=LLMProvider.OLLAMA,
            model="llama3",
        )
        with patch.object(service, "_summarize_ollama") as mock_ollama:
            mock_ollama.return_value = SummarizationResult(
                markdown="test", provider=LLMProvider.OLLAMA, model="test", token_count=0
            )
            service.summarize(request)
            mock_ollama.assert_called_once_with(request)

    def test_summarize_raises_valueerror_for_unsupported_provider(self) -> None:
        """Verify summarize raises ValueError for an unrecognized provider."""
        service = SummarizationService()
        request = SummarizationRequest(
            transcript="Alice: Hello.",
            provider="unsupported",  # type: ignore[arg-type]
            model="some-model",
        )
        with pytest.raises(ValueError, match="Unsupported provider"):
            service.summarize(request)


class TestSummarizeClaudeProvider:
    """Tests for _summarize_claude method."""

    def test_claude_calls_anthropic_messages_create(self) -> None:
        """Verify _summarize_claude calls Anthropic messages.create with correct params."""
        mock_anthropic_module = MagicMock()
        mock_client = MagicMock()
        mock_anthropic_module.Anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="# Meeting Summary")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_client.messages.create.return_value = mock_response

        with patch.dict("sys.modules", {"anthropic": mock_anthropic_module}):
            service = SummarizationService()
            request = SummarizationRequest(
                transcript="Alice: Hello. Bob: Hi.",
                provider=LLMProvider.CLAUDE,
                model="claude-sonnet-4-5-20250929",
                api_key="sk-test-key",
            )
            result = service._summarize_claude(request)

        mock_anthropic_module.Anthropic.assert_called_once_with(api_key="sk-test-key")
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-sonnet-4-5-20250929"
        assert call_kwargs["system"] == SUMMARY_SYSTEM_PROMPT
        assert any("Alice: Hello. Bob: Hi." in msg["content"] for msg in call_kwargs["messages"])
        assert result.markdown == "# Meeting Summary"
        assert result.provider == LLMProvider.CLAUDE
        assert result.model == "claude-sonnet-4-5-20250929"
        assert result.token_count == 150

    def test_claude_raises_valueerror_when_api_key_missing(self) -> None:
        """Verify _summarize_claude raises ValueError when api_key is None."""
        service = SummarizationService()
        request = SummarizationRequest(
            transcript="Alice: Hello.",
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-4-5-20250929",
            api_key=None,
        )
        with pytest.raises(ValueError, match="API key required for claude"):
            service._summarize_claude(request)

    def test_claude_raises_runtimeerror_when_sdk_not_installed(self) -> None:
        """Verify _summarize_claude raises RuntimeError when anthropic is not installed."""
        with patch.dict("sys.modules", {"anthropic": None}):
            service = SummarizationService()
            request = SummarizationRequest(
                transcript="Alice: Hello.",
                provider=LLMProvider.CLAUDE,
                model="claude-sonnet-4-5-20250929",
                api_key="sk-test-key",
            )
            with pytest.raises(RuntimeError, match="anthropic is not installed"):
                service._summarize_claude(request)

    def test_claude_raises_connectionerror_on_api_failure(self) -> None:
        """Verify _summarize_claude raises ConnectionError when API call fails."""
        mock_anthropic_module = MagicMock()
        mock_client = MagicMock()
        mock_anthropic_module.Anthropic.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("network timeout")

        with patch.dict("sys.modules", {"anthropic": mock_anthropic_module}):
            service = SummarizationService()
            request = SummarizationRequest(
                transcript="Alice: Hello.",
                provider=LLMProvider.CLAUDE,
                model="claude-sonnet-4-5-20250929",
                api_key="sk-test-key",
            )
            with pytest.raises(ConnectionError, match="Failed to connect to claude"):
                service._summarize_claude(request)


class TestSummarizeOpenAIProvider:
    """Tests for _summarize_openai method."""

    def test_openai_calls_chat_completions_create(self) -> None:
        """Verify _summarize_openai calls OpenAI chat.completions.create correctly."""
        mock_openai_module = MagicMock()
        mock_client = MagicMock()
        mock_openai_module.OpenAI.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="# Meeting Summary"))]
        mock_response.usage.prompt_tokens = 80
        mock_response.usage.completion_tokens = 40
        mock_client.chat.completions.create.return_value = mock_response

        with patch.dict("sys.modules", {"openai": mock_openai_module}):
            service = SummarizationService()
            request = SummarizationRequest(
                transcript="Alice: Hello. Bob: Hi.",
                provider=LLMProvider.OPENAI,
                model="gpt-4o",
                api_key="sk-test-key",
            )
            result = service._summarize_openai(request)

        mock_openai_module.OpenAI.assert_called_once_with(api_key="sk-test-key")
        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-4o"
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == SUMMARY_SYSTEM_PROMPT
        assert messages[1]["role"] == "user"
        assert "Alice: Hello. Bob: Hi." in messages[1]["content"]
        assert result.markdown == "# Meeting Summary"
        assert result.provider == LLMProvider.OPENAI
        assert result.model == "gpt-4o"
        assert result.token_count == 120

    def test_openai_raises_valueerror_when_api_key_missing(self) -> None:
        """Verify _summarize_openai raises ValueError when api_key is None."""
        service = SummarizationService()
        request = SummarizationRequest(
            transcript="test",
            provider=LLMProvider.OPENAI,
            model="gpt-4o",
            api_key=None,
        )
        with pytest.raises(ValueError, match="API key required for openai"):
            service._summarize_openai(request)

    def test_openai_raises_runtimeerror_when_sdk_not_installed(self) -> None:
        """Verify _summarize_openai raises RuntimeError when openai is not installed."""
        with patch.dict("sys.modules", {"openai": None}):
            service = SummarizationService()
            request = SummarizationRequest(
                transcript="test",
                provider=LLMProvider.OPENAI,
                model="gpt-4o",
                api_key="sk-test",
            )
            with pytest.raises(RuntimeError, match="openai is not installed"):
                service._summarize_openai(request)


class TestSummarizeGeminiProvider:
    """Tests for _summarize_gemini method."""

    def test_gemini_calls_generativeai_with_correct_params(self) -> None:
        """Verify _summarize_gemini uses google.generativeai with correct params."""
        mock_genai_module = MagicMock()
        mock_model = MagicMock()
        mock_genai_module.GenerativeModel.return_value = mock_model
        mock_response = MagicMock()
        mock_response.text = "# Meeting Summary"
        mock_response.usage_metadata.prompt_token_count = 90
        mock_response.usage_metadata.candidates_token_count = 60
        mock_model.generate_content.return_value = mock_response

        mock_google = types.ModuleType("google")
        mock_google.generativeai = mock_genai_module  # type: ignore[attr-defined]

        with patch.dict(
            "sys.modules",
            {"google": mock_google, "google.generativeai": mock_genai_module},
        ):
            service = SummarizationService()
            request = SummarizationRequest(
                transcript="Alice: Hello. Bob: Hi.",
                provider=LLMProvider.GEMINI,
                model="gemini-pro",
                api_key="test-api-key",
            )
            result = service._summarize_gemini(request)

        mock_genai_module.configure.assert_called_once_with(api_key="test-api-key")
        mock_genai_module.GenerativeModel.assert_called_once_with("gemini-pro")
        mock_model.generate_content.assert_called_once()
        assert result.markdown == "# Meeting Summary"
        assert result.provider == LLMProvider.GEMINI
        assert result.model == "gemini-pro"
        assert result.token_count == 150

    def test_gemini_raises_valueerror_when_api_key_missing(self) -> None:
        """Verify _summarize_gemini raises ValueError when api_key is None."""
        service = SummarizationService()
        request = SummarizationRequest(
            transcript="test",
            provider=LLMProvider.GEMINI,
            model="gemini-pro",
            api_key=None,
        )
        with pytest.raises(ValueError, match="API key required for gemini"):
            service._summarize_gemini(request)

    def test_gemini_raises_runtimeerror_when_sdk_not_installed(self) -> None:
        """Verify _summarize_gemini raises RuntimeError when SDK is missing."""
        with patch.dict("sys.modules", {"google": None, "google.generativeai": None}):
            service = SummarizationService()
            request = SummarizationRequest(
                transcript="test",
                provider=LLMProvider.GEMINI,
                model="gemini-pro",
                api_key="test-key",
            )
            with pytest.raises(RuntimeError, match="google-generativeai is not installed"):
                service._summarize_gemini(request)


class TestSummarizeOllamaProvider:
    """Tests for _summarize_ollama method."""

    def test_ollama_makes_http_request_to_localhost(self) -> None:
        """Verify _summarize_ollama sends POST to localhost:11434/api/generate."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": "# Meeting Summary",
            "prompt_eval_count": 70,
            "eval_count": 30,
        }

        with patch("summarization.providers.urllib.request.urlopen") as mock_urlopen:
            mock_http_response = MagicMock()
            mock_http_response.read.return_value = (
                b'{"response": "# Meeting Summary", "prompt_eval_count": 70, "eval_count": 30}'
            )
            mock_http_response.__enter__ = lambda s: s
            mock_http_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_http_response

            service = SummarizationService()
            request = SummarizationRequest(
                transcript="Alice: Hello. Bob: Hi.",
                provider=LLMProvider.OLLAMA,
                model="llama3",
            )
            result = service._summarize_ollama(request)

        mock_urlopen.assert_called_once()
        call_args = mock_urlopen.call_args
        req_obj = call_args[0][0]
        assert "localhost:11434" in req_obj.full_url
        assert result.markdown == "# Meeting Summary"
        assert result.provider == LLMProvider.OLLAMA
        assert result.model == "llama3"
        assert result.token_count == 100

    def test_ollama_does_not_require_api_key(self) -> None:
        """Verify _summarize_ollama does not raise ValueError when api_key is None."""
        with patch("summarization.providers.urllib.request.urlopen") as mock_urlopen:
            mock_http_response = MagicMock()
            mock_http_response.read.return_value = (
                b'{"response": "summary", "prompt_eval_count": 10, "eval_count": 5}'
            )
            mock_http_response.__enter__ = lambda s: s
            mock_http_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_http_response

            service = SummarizationService()
            request = SummarizationRequest(
                transcript="test",
                provider=LLMProvider.OLLAMA,
                model="llama3",
                api_key=None,
            )
            result = service._summarize_ollama(request)
            assert result.provider == LLMProvider.OLLAMA

    def test_ollama_raises_connectionerror_on_failure(self) -> None:
        """Verify _summarize_ollama raises ConnectionError when HTTP request fails."""
        with patch(
            "summarization.providers.urllib.request.urlopen",
            side_effect=Exception("Connection refused"),
        ):
            service = SummarizationService()
            request = SummarizationRequest(
                transcript="test",
                provider=LLMProvider.OLLAMA,
                model="llama3",
            )
            with pytest.raises(ConnectionError, match="Failed to connect to ollama"):
                service._summarize_ollama(request)


class TestHandleSummarizeIntegration:
    """Tests for handle_summarize IPC handler returning proper response format."""

    def test_handle_summarize_returns_complete_response_format(self) -> None:
        """Verify handle_summarize returns response with markdown, provider, model, token_count."""
        from ipc.handlers import handle_summarize
        from ipc.protocol import IPCMessage, MessageType

        with patch("summarization.providers.SummarizationService.summarize") as mock_summarize:
            mock_summarize.return_value = SummarizationResult(
                markdown="# Meeting Summary",
                provider=LLMProvider.CLAUDE,
                model="claude-sonnet-4-5-20250929",
                token_count=150,
            )

            msg = IPCMessage(
                type=MessageType.SUMMARIZE,
                payload={
                    "transcript": "Alice: Hello.",
                    "provider": "claude",
                    "model": "claude-sonnet-4-5-20250929",
                    "api_key": "sk-test",
                },
            )
            resp = handle_summarize(msg)

        result = resp.to_dict()
        assert result["type"] == "summary_complete"
        assert result["markdown"] == "# Meeting Summary"
        assert result["provider"] == "claude"
        assert result["model"] == "claude-sonnet-4-5-20250929"
        assert result["token_count"] == 150
