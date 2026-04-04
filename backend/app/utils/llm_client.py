"""
LLM Client — Multi-model abstraction layer.

Supports OpenAI and Anthropic providers, with per-agent model routing
and graceful fallback. Backward compatible with existing BTRate code
that uses `LLMClient(...)`.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from ..config import Config

logger = logging.getLogger("btrate.llm")


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

class MockProvider:
    """
    Document-aware mock provider — extracts real signals from the submitted
    document/question and generates a contextually relevant debate.

    Used when DEMO_MODE=true or when no real API key is configured.
    Each call produces unique, document-grounded output instead of canned AAPL boilerplate.
    """

    # Per-agent persona for round 1 framing
    _AGENT_ANGLES = {
        "quant": {
            "focus": "valuation multiples, revenue CAGR, margin trajectory, momentum signals",
            "style": "data-driven and precise",
        },
        "fundamental": {
            "focus": "business model quality, competitive moat, management execution, TAM",
            "style": "qualitative and long-term oriented",
        },
        "risk": {
            "focus": "tail risks, liquidity, max drawdown, concentration",
            "style": "conservative and thorough",
        },
        "devil": {
            "focus": "strongest counterargument to emerging consensus, hidden assumptions",
            "style": "adversarial and rigorous",
        },
    }

    # Bearish signals in doc text → flip to SELL bias
    _BEARISH_KEYWORDS = [
        "loss", "decline", "debt", "lawsuit", "fraud", "bankruptcy", "miss",
        "downgrade", "headwind", "risk", "concern", "weak", "poor", "negative",
        "short", "overvalued", "bubble", "impairment", "write-off",
    ]
    _BULLISH_KEYWORDS = [
        "growth", "profit", "margin", "beat", "record", "expand", "moat",
        "upgrade", "opportunity", "upside", "strong", "accelerat", "dominant",
        "cash flow", "buyback", "dividend", "undervalued",
    ]

    @staticmethod
    def _extract_context(messages):
        """Pull question + document snippet from the message list."""
        full_text = " ".join(m.get("content", "") for m in messages)
        # Extract the Question line
        import re
        q_match = re.search(r'\*\*Question:\*\*\s*(.+?)\n', full_text)
        question = q_match.group(1).strip() if q_match else "this investment"
        # Grab first 3000 chars of Document section
        doc_match = re.search(r'\*\*Document:\*\*\s*([\s\S]{50,3000})', full_text)
        doc_snippet = doc_match.group(1)[:3000] if doc_match else full_text[:1000]
        return question, doc_snippet

    @staticmethod
    def _score_sentiment(text):
        """Return (direction, conviction) based on keyword frequency."""
        text_l = text.lower()
        bull = sum(text_l.count(k) for k in MockProvider._BULLISH_KEYWORDS)
        bear = sum(text_l.count(k) for k in MockProvider._BEARISH_KEYWORDS)
        total = bull + bear or 1
        bull_ratio = bull / total
        if bull_ratio > 0.60:
            return "BUY", round(min(8.5, 6.0 + bull_ratio * 2.5), 1)
        elif bull_ratio < 0.40:
            return "SELL", round(min(8.0, 4.5 + (1 - bull_ratio) * 2.5), 1)
        else:
            return "HOLD", 5.5

    @staticmethod
    def _extract_sentences(text, n=6):
        """Pull the first n non-trivial sentences from the document."""
        import re
        sents = re.split(r'(?<=[.!?])\s+', text.replace('\n', ' '))
        return [s.strip() for s in sents if len(s.strip()) > 40][:n]

    @staticmethod
    def _extract_numbers(text):
        """Find numeric metrics mentioned in the text."""
        import re
        # Match things like "$45B", "18%", "3.2x", "$12.50"
        return re.findall(r'\$?[\d,]+(?:\.\d+)?(?:[BMK%x]|\s*(?:billion|million|percent))?', text)[:8]

    @staticmethod
    def _detect_agent(messages):
        """Detect which agent role is speaking from the system prompt."""
        sys_text = next((m.get("content","") for m in messages if m.get("role")=="system"), "").lower()
        if "quant" in sys_text:
            return "quant"
        if "fundamental" in sys_text:
            return "fundamental"
        if "risk" in sys_text or "chief risk" in sys_text:
            return "risk"
        if "devil" in sys_text or "adversar" in sys_text:
            return "devil"
        return "quant"

    @staticmethod
    def _detect_round(messages):
        text = " ".join(m.get("content", "") for m in messages).lower()
        if "cio" in text and "synthesis" in text:
            return 4
        if "rebuttal" in text or "defense" in text:
            return 3
        if "cross-examination" in text or "challenge" in text:
            return 2
        return 1

    def _build_round1(self, messages):
        import random
        question, doc = self._extract_context(messages)
        direction, conviction = self._score_sentiment(doc)
        agent = self._detect_agent(messages)
        sentences = self._extract_sentences(doc)
        numbers = self._extract_numbers(doc)

        # Build arguments grounded in actual doc sentences
        key_args = []
        key_risks = []
        if sentences:
            key_args.append(sentences[0] if len(sentences) > 0 else "Strong fundamentals support the thesis")
            key_args.append(sentences[2] if len(sentences) > 2 else "Favorable market positioning")
            key_args.append(sentences[4] if len(sentences) > 4 else "Compelling risk/reward at current levels")
            key_risks.append(sentences[1] if len(sentences) > 1 else "Execution risk remains elevated")
            key_risks.append(sentences[3] if len(sentences) > 3 else "Macro headwinds could pressure near-term results")
        else:
            key_args = [
                f"The investment thesis for {question[:60]} is supported by the submitted research",
                "Operating leverage and margin expansion trajectory are favorable",
                "Valuation appears compelling on a risk-adjusted basis",
            ]
            key_risks = [
                "Macro and rate environment creates near-term uncertainty",
                "Execution risk on key strategic initiatives remains elevated",
            ]

        # Quant adds numbers if any found
        if agent == "quant" and numbers:
            clean_nums = [n for n in numbers[:4] if len(n) > 1]
            if clean_nums:
                key_args[0] = f"Key metrics cited in the document ({', '.join(clean_nums)}) support the {direction} thesis"

        # Devil's Advocate flips conviction
        if agent == "devil":
            direction = "SELL" if direction == "BUY" else "BUY" if direction == "SELL" else "HOLD"
            conviction = max(1.0, conviction - 2.0)
            key_args = [
                f"The emerging {('BUY' if direction=='SELL' else 'SELL')} consensus is not justified by the evidence",
                key_risks[0] if key_risks else "The core assumption is flawed and not stress-tested",
                "Risk/reward is asymmetrically unfavorable at current entry",
            ]

        # Risk manager lowers conviction
        if agent == "risk":
            conviction = max(1.0, conviction - 1.5)
            key_risks = [
                key_risks[0] if key_risks else "Tail risk is under-appreciated by the committee",
                "Liquidity and correlation assumptions may not hold in a stress scenario",
                "Position sizing must account for potential max drawdown of 30%+",
            ]

        nums_str = numbers[0] if numbers else "N/A"
        return {
            "direction": direction,
            "conviction": round(conviction, 1),
            "key_arguments": key_args[:3],
            "key_risks": key_risks[:2],
            "price_target": nums_str if '$' in nums_str else None,
            "expected_return": "10-20% over 12 months" if direction == "BUY" else "-10% to -20% over 12 months" if direction == "SELL" else "0-5% sideways",
            "time_horizon": "12 months",
            "causal_factors": [
                {
                    "event": sentences[0][:80] if sentences else "Primary catalyst from submitted document",
                    "channel": "Earnings and cash flow impact",
                    "direction": "bullish" if direction == "BUY" else "bearish",
                    "magnitude": "high" if conviction > 7 else "medium",
                    "confidence": round(conviction / 10.0, 2),
                    "time_horizon": "medium_term",
                }
            ],
        }

    def _build_round2(self, messages):
        question, doc = self._extract_context(messages)
        direction, conviction = self._score_sentiment(doc)
        sentences = self._extract_sentences(doc, n=4)
        s0 = sentences[0][:100] if sentences else "the bullish thesis"
        s1 = sentences[1][:100] if len(sentences) > 1 else "the margin expansion assumption"
        opp_dir = "SELL" if direction == "BUY" else "BUY"
        return {
            "challenges": {
                "Quant Analyst": [
                    f"The quantitative case relies on {s0} — but this hasn't been stress-tested at different rate regimes",
                    f"The momentum signal embedded in {direction} call has historically mean-reverted within 3 months at similar setups",
                ],
                "Fundamental Analyst": [
                    f"{s1} — management guidance suggests the opposite: near-term margin compression before any expansion",
                    f"The moat is narrower than assumed; competition is encroaching on the core value proposition",
                ],
                "Risk Manager": [
                    f"Your tail risk analysis doesn't account for correlation breakdown in a stress event",
                    f"The {opp_dir} scenario probability is significantly underweighted given current macro backdrop",
                ],
                "Devil's Advocate": [
                    f"The entire {direction} consensus is built on the assumption that current trends continue — they won't",
                    f"The document itself contains signals pointing to a {opp_dir} scenario that the committee is ignoring",
                ],
            }
        }

    def _build_round3(self, messages):
        question, doc = self._extract_context(messages)
        direction, conviction = self._score_sentiment(doc)
        sentences = self._extract_sentences(doc, n=3)
        updated_conviction = round(max(3.0, conviction - 0.8 + (hash(question) % 3) * 0.3), 1)
        return {
            "defenses": [
                f"The challenges raised don't negate the core thesis: {sentences[0][:120] if sentences else 'the fundamental driver remains intact'}",
                f"Even in a bear scenario for the {direction} case, the risk/reward still skews favorable over a 12-month horizon",
            ],
            "concessions": [
                "I concede the near-term macro headwinds are more significant than initially modeled — adjusting conviction downward by 0.5",
            ],
            "updated_conviction": updated_conviction,
            "updated_direction": direction,
        }

    def _build_round4(self, messages):
        question, doc = self._extract_context(messages)
        direction, conviction = self._score_sentiment(doc)
        sentences = self._extract_sentences(doc, n=4)

        # Weighted distribution based on document sentiment
        if direction == "BUY":
            dist = {"BUY": round(0.50 + (conviction-5)/20, 2), "HOLD": 0.28, "SELL": 0.12}
        elif direction == "SELL":
            dist = {"BUY": 0.12, "HOLD": 0.28, "SELL": round(0.50 + (conviction-5)/20, 2)}
        else:
            dist = {"BUY": 0.30, "HOLD": 0.45, "SELL": 0.25}

        # Normalize to sum to 1
        total = sum(dist.values())
        dist = {k: round(v/total, 2) for k, v in dist.items()}

        thesis_base = sentences[0][:200] if sentences else f"Based on the submitted research, the committee analyzed {question[:80]}."
        return {
            "recommendation": direction,
            "confidence_distribution": dist,
            "consensus_conviction": round(conviction - 0.3, 1),
            "key_thesis": (
                f"The investment committee recommends {direction} with {'moderate' if 5 < conviction <= 7.5 else 'high' if conviction > 7.5 else 'low'} conviction "
                f"based on analysis of the submitted document. {thesis_base} "
                f"The debate surfaced {'bullish' if direction=='BUY' else 'bearish' if direction=='SELL' else 'mixed'} signals "
                f"across quantitative, fundamental, and risk dimensions."
            ),
            "primary_risks": [
                sentences[1][:120] if len(sentences) > 1 else "Execution risk on the primary thesis driver",
                sentences[2][:120] if len(sentences) > 2 else "Macro and rate environment may compress multiples",
                "Tail risk scenarios are not fully priced in by the market",
            ],
            "position_sizing_guidance": (
                f"{'2-4%' if conviction > 7 else '1-2%'} portfolio weight; "
                f"{'scale in over 4-6 weeks' if direction in ('BUY','SELL') else 'wait for clearer signal before initiating'}"
            ),
            "dissenting_views": [
                f"Devil's Advocate maintains that the {('SELL' if direction=='BUY' else 'BUY')} case is underweighted — "
                f"the document contains signals that challenge the {direction} consensus",
            ],
            "debate_quality_score": round(7.0 + (conviction % 2) * 0.5, 1),
        }

    def _generate(self, messages):
        round_num = self._detect_round(messages)
        if round_num == 1:
            return self._build_round1(messages)
        elif round_num == 2:
            return self._build_round2(messages)
        elif round_num == 3:
            return self._build_round3(messages)
        else:
            return self._build_round4(messages)

    def chat(self, messages, model, temperature=0.7, max_tokens=4096, **kwargs):
        import json, time
        time.sleep(0.3)
        return json.dumps(self._generate(messages))

    async def achat(self, messages, model, temperature=0.7, max_tokens=4096, **kwargs):
        import json, asyncio
        await asyncio.sleep(0.3)
        return json.dumps(self._generate(messages))


class OpenAIProvider:
    """OpenAI / OpenAI-compatible API provider (also works with Gemini, Groq, etc.)."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        from openai import OpenAI, AsyncOpenAI

        # Try OPENAI_API_KEY first (debate feature), then LLM_API_KEY (legacy)
        self.api_key = api_key or Config.OPENAI_API_KEY or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        if not self.api_key:
            raise ValueError("No API key configured (OPENAI_API_KEY or LLM_API_KEY)")

        # Detect Gemini: if the base_url points to Google's API, use it
        # Also detect if the key looks like a Gemini key (starts with 'AI')
        if self.api_key and self.api_key.startswith('AI'):
            # Likely a Gemini API key — force the Gemini-compatible base URL
            self.base_url = 'https://generativelanguage.googleapis.com/v1beta/openai/'
            logger.info("Detected Gemini API key, using Google endpoint")

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
        # In demo mode, always return mock provider
        if Config.DEMO_MODE:
            if "mock" not in self._providers:
                self._providers["mock"] = MockProvider()
                logger.info("Using MockProvider (DEMO_MODE=true)")
            return self._providers["mock"]

        if model.startswith("claude"):
            key = "anthropic"
        else:
            key = "openai"  # Default to OpenAI-compatible (also handles Gemini, Groq, etc.)
        if key not in self._providers:
            try:
                if key == "anthropic":
                    self._providers[key] = AnthropicProvider()
                else:
                    self._providers[key] = OpenAIProvider()
                logger.info(f"Initialized {key} provider")
            except Exception as e:
                logger.warning(f"Failed to init {key} provider: {e} — falling back to MockProvider")
                self._providers[key] = MockProvider()
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
# Backward-compatible LLMClient (used by existing BTRate code)
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
