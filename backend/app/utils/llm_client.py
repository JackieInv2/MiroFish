"""
LLM Client — Multi-model abstraction layer.

Supports OpenAI and Anthropic providers, with per-agent model routing
and graceful fallback. Backward compatible with existing MiroFish code
that uses `LLMClient(...)`.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from ..config import Config

logger = logging.getLogger("mirofish.llm")


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

class OpenAIProvider:
    """OpenAI / OpenAI-compatible API provider."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        from openai import OpenAI, AsyncOpenAI

        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        if not self.api_key:
            raise ValueError("OpenAI API key not configured (LLM_API_KEY)")
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.async_client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None,
    ) -> str:
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format
        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        return _clean_content(content)

    async def achat(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None,
    ) -> str:
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format
        response = await self.async_client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        return _clean_content(content)


class AnthropicProvider:
    """Anthropic Claude API provider."""

    def __init__(self, api_key: Optional[str] = None):
        import anthropic

        self.api_key = api_key or Config.ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError("Anthropic API key not configured (ANTHROPIC_API_KEY)")
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.async_client = anthropic.AsyncAnthropic(api_key=self.api_key)

    def _prepare_messages(self, messages: List[Dict[str, str]]):
        """Separate system message from user/assistant messages for Anthropic API."""
        system = None
        conversation = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                conversation.append(m)
        return system, conversation

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> str:
        system, conversation = self._prepare_messages(messages)
        create_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": conversation,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system:
            create_kwargs["system"] = system
        response = self.client.messages.create(**create_kwargs)
        content = response.content[0].text
        return _clean_content(content)

    async def achat(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> str:
        system, conversation = self._prepare_messages(messages)
        create_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": conversation,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system:
            create_kwargs["system"] = system
        response = await self.async_client.messages.create(**create_kwargs)
        content = response.content[0].text
        return _clean_content(content)


# ---------------------------------------------------------------------------
# Multi-model router
# ---------------------------------------------------------------------------

class MultiModelClient:
    """Routes LLM calls to different providers based on model name."""

    def __init__(self):
        self._providers: Dict[str, Any] = {}

    def _get_provider(self, model: str):
        """Lazy-init the correct provider for the given model."""
        if model.startswith("claude"):
            key = "anthropic"
        else:
            key = "openai"  # Default to OpenAI-compatible
        if key not in self._providers:
            try:
                if key == "anthropic":
                    self._providers[key] = AnthropicProvider()
                else:
                    self._providers[key] = OpenAIProvider()
                logger.info(f"Initialized {key} provider")
            except Exception as e:
                logger.error(f"Failed to init {key} provider: {e}")
                raise
        return self._providers[key]

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> str:
        provider = self._get_provider(model)
        return provider.chat(messages, model, temperature, max_tokens, **kwargs)

    async def achat(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> str:
        provider = self._get_provider(model)
        return await provider.achat(messages, model, temperature, max_tokens, **kwargs)

    async def achat_json(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """Send a request expecting a JSON response, with fallback parsing."""
        if model.startswith("claude"):
            # Anthropic doesn't have a native JSON mode — instruct via prompt
            response = await self.achat(messages, model, temperature, max_tokens)
        else:
            provider = self._get_provider(model)
            response = await provider.achat(
                messages, model, temperature, max_tokens,
                response_format={"type": "json_object"},
            )
        return _parse_json(response)

    async def achat_with_fallback(
        self,
        messages: List[Dict[str, str]],
        primary_model: str,
        fallback_model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> tuple[str, str]:
        """Try primary_model, fall back to fallback_model on failure.
        Returns (response_text, model_used).
        """
        try:
            text = await self.achat(messages, primary_model, temperature, max_tokens)
            return text, primary_model
        except Exception as e:
            logger.warning(
                f"Primary model {primary_model} failed ({e}), falling back to {fallback_model}"
            )
            text = await self.achat(messages, fallback_model, temperature, max_tokens)
            return text, fallback_model


# ---------------------------------------------------------------------------
# Backward-compatible LLMClient (used by existing MiroFish code)
# ---------------------------------------------------------------------------

class LLMClient:
    """Original LLM client interface — preserved for backward compatibility."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME

        if not self.api_key:
            raise ValueError("LLM_API_KEY 未配置")

        from openai import OpenAI
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None,
    ) -> str:
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format
        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        return _clean_content(content)

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        response = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        return _parse_json(response)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_content(content: str) -> str:
    """Remove <think> tags and other artifacts from LLM output."""
    content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
    return content


def _parse_json(text: str) -> Dict[str, Any]:
    """Parse JSON from LLM output, stripping markdown fences if present."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON from LLM: {cleaned[:500]}")
