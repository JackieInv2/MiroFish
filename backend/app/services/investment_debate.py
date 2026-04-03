"""
Investment Debate Engine — IC-style structured debate among AI agents.

Implements a 4-round debate:
  Round 1: Initial Thesis (parallel)
  Round 2: Cross-Examination
  Round 3: Rebuttal & Defense
  Round 4: CIO Synthesis & Consensus

Each agent can use a different LLM model for diversity of thought.
Conviction scores are calibrated with Platt scaling.
"""

import asyncio
import logging
import math
from datetime import datetime
from typing import Dict, List, Optional

from ..config import Config
from ..models.debate import (
    AgentResponse,
    AgentRole,
    AgentThesis,
    CIOSynthesis,
    ConsensusScore,
    CrossExamination,
    DebateResult,
    DebateRound,
    DebateStatus,
    Direction,
    InvestmentFactor,
    Rebuttal,
)
from ..utils.llm_client import MultiModelClient

logger = logging.getLogger("btrate.debate")

# Platt scaling parameter: alpha = sqrt(3) ≈ 1.73
PLATT_ALPHA = math.sqrt(3)

# In-memory debate store (matches existing TaskManager pattern)
_debate_store: Dict[str, DebateResult] = {}


def get_debate(debate_id: str) -> Optional[DebateResult]:
    return _debate_store.get(debate_id)


def list_debates() -> List[DebateResult]:
    return list(_debate_store.values())


# ---------------------------------------------------------------------------
# Agent configuration
# ---------------------------------------------------------------------------

AGENT_CONFIG = {
    AgentRole.QUANT_ANALYST: {
        "name": "Quant Analyst",
        "model_config": "QUANT_AGENT_MODEL",
        "temperature": 0.4,
        "system_prompt": (
            "You are a quantitative analyst at a top-tier hedge fund. "
            "Focus on statistical/quantitative factors: valuation metrics (P/E, EV/EBITDA, P/B), "
            "technical indicators, factor exposures, momentum signals, and volatility regime. "
            "Be precise with numbers and data-driven in your arguments. "
            "Always provide specific quantitative evidence for your claims."
        ),
    },
    AgentRole.FUNDAMENTAL_ANALYST: {
        "name": "Fundamental Analyst",
        "model_config": "FUNDAMENTAL_AGENT_MODEL",
        "temperature": 0.6,
        "system_prompt": (
            "You are a fundamental analyst at a top-tier investment firm. "
            "Focus on business model quality, competitive moats, management quality, "
            "earnings quality, industry dynamics, TAM, and margin trajectory. "
            "Provide deep qualitative analysis grounded in business fundamentals. "
            "Think about long-term competitive positioning and structural advantages."
        ),
    },
    AgentRole.RISK_MANAGER: {
        "name": "Risk Manager",
        "model_config": "RISK_AGENT_MODEL",
        "temperature": 0.3,
        "system_prompt": (
            "You are the Chief Risk Officer at a multi-strategy fund. "
            "Identify tail risks, correlation risks, liquidity concerns, "
            "position sizing issues, and max drawdown scenarios. "
            "Think about what could go wrong that others aren't considering. "
            "Be conservative and thorough in risk identification."
        ),
    },
    AgentRole.DEVIL_ADVOCATE: {
        "name": "Devil's Advocate",
        "model_config": "DEVIL_ADVOCATE_MODEL",
        "temperature": 0.8,
        "system_prompt": (
            "You are the designated Devil's Advocate on the investment committee. "
            "Your job is to find the strongest counterargument to ANY emerging consensus. "
            "Challenge every assumption, find flaws in every thesis. "
            "Be intellectually rigorous and adversarial. "
            "If everyone is bullish, find the bear case. If bearish, find the bull case."
        ),
    },
    AgentRole.CIO: {
        "name": "CIO / Portfolio Manager",
        "model_config": "CIO_MODEL",
        "temperature": 0.5,
        "system_prompt": (
            "You are the Chief Investment Officer chairing this IC meeting. "
            "Synthesize all perspectives, manage disagreements, and produce a "
            "final recommendation. Weigh arguments by quality of evidence, not "
            "just conviction. Consider position sizing, risk/reward, and portfolio fit. "
            "Acknowledge dissenting views while making a clear decision."
        ),
    },
}

DEBATE_AGENTS = [
    AgentRole.QUANT_ANALYST,
    AgentRole.FUNDAMENTAL_ANALYST,
    AgentRole.RISK_MANAGER,
    AgentRole.DEVIL_ADVOCATE,
]


def _get_model_for_role(role: AgentRole) -> str:
    config_key = AGENT_CONFIG[role]["model_config"]
    return getattr(Config, config_key, "gpt-4o")


def _platt_calibrate(raw: float, alpha: float = PLATT_ALPHA) -> float:
    """Apply Platt scaling: p_cal = p^α / (p^α + (1-p)^α).

    Converts raw conviction (1-10 scale → 0-1) to a calibrated probability,
    correcting for LLM hedging bias (clustering around 5/10).
    """
    p = max(0.01, min(0.99, raw / 10.0))
    numerator = p ** alpha
    denominator = numerator + (1.0 - p) ** alpha
    return numerator / denominator


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _round1_prompt(question: str, doc_text: str) -> str:
    return f"""Analyze the following investment research document and provide your initial thesis.

**Question:** {question}

**Document:**
{doc_text[:12000]}

Respond with a JSON object (no markdown fences):
{{
  "direction": "BUY" or "SELL" or "HOLD",
  "conviction": <float 1-10>,
  "key_arguments": ["arg1", "arg2", "arg3"],
  "key_risks": ["risk1", "risk2"],
  "price_target": "<price or null>",
  "expected_return": "<return estimate or null>",
  "time_horizon": "<time horizon>",
  "causal_factors": [
    {{
      "event": "<event>",
      "channel": "<channel>",
      "direction": "bullish" or "bearish",
      "magnitude": "low" or "medium" or "high",
      "confidence": <float 0-1>,
      "time_horizon": "near_term" or "medium_term" or "long_term"
    }}
  ]
}}"""


def _round2_prompt(question: str, agent_role: str, all_theses: Dict[str, str]) -> str:
    thesis_text = ""
    for role_name, thesis in all_theses.items():
        if role_name != agent_role:
            thesis_text += f"\n--- {role_name} ---\n{thesis}\n"

    return f"""You are now in the Cross-Examination round. Review the other analysts' theses and produce pointed challenges.

**Question:** {question}

**Other Analysts' Theses:**
{thesis_text}

For each analyst, produce 2-3 specific, substantive challenges to their arguments.

Respond with a JSON object (no markdown fences):
{{
  "challenges": {{
    "<analyst_role>": ["challenge1", "challenge2"],
    "<analyst_role>": ["challenge1", "challenge2"]
  }}
}}"""


def _round3_prompt(
    question: str,
    my_thesis: str,
    challenges_to_me: Dict[str, List[str]],
) -> str:
    challenges_text = ""
    for challenger, items in challenges_to_me.items():
        for item in items:
            challenges_text += f"  - {challenger}: {item}\n"

    return f"""You are now in the Rebuttal & Defense round. Other analysts have challenged your thesis.

**Question:** {question}

**Your Original Thesis:**
{my_thesis}

**Challenges Directed at You:**
{challenges_text}

You must either defend your position with additional evidence or concede specific points and adjust your thesis.

Respond with a JSON object (no markdown fences):
{{
  "defenses": ["defense1", "defense2"],
  "concessions": ["concession1 (if any)"],
  "updated_conviction": <float 1-10>,
  "updated_direction": "BUY" or "SELL" or "HOLD" or null
}}"""


def _round4_prompt(question: str, full_transcript: str) -> str:
    return f"""You are the CIO chairing this IC meeting. Review the full debate transcript and produce the final investment recommendation.

**Question:** {question}

**Full Debate Transcript:**
{full_transcript}

Produce a final synthesis. Respond with a JSON object (no markdown fences):
{{
  "recommendation": "BUY" or "SELL" or "HOLD",
  "confidence_distribution": {{"BUY": <float>, "HOLD": <float>, "SELL": <float>}},
  "consensus_conviction": <float 1-10>,
  "key_thesis": "<2-3 sentence summary>",
  "primary_risks": ["risk1", "risk2", "risk3"],
  "position_sizing_guidance": "<guidance or null>",
  "dissenting_views": ["<summary of any persistent dissent>"],
  "debate_quality_score": <float 1-10>
}}"""


# ---------------------------------------------------------------------------
# Debate engine
# ---------------------------------------------------------------------------

class InvestmentDebateEngine:
    """Runs a structured 4-round IC-style investment debate."""

    def __init__(self):
        self.client = MultiModelClient()

    async def run_debate(
        self,
        question: str,
        document_text: str,
        file_name: Optional[str] = None,
        debate_id: Optional[str] = None,
    ) -> DebateResult:
        """Execute a full 4-round debate and return the result.

        If debate_id is provided and already exists in the store, the existing
        DebateResult is updated in-place (allowing the API to return the ID
        before the debate finishes).
        """
        if debate_id and debate_id in _debate_store:
            result = _debate_store[debate_id]
        else:
            result = DebateResult(
                question=question,
                file_name=file_name,
                status=DebateStatus.PENDING,
            )
            _debate_store[result.debate_id] = result

        try:
            # Round 1: Initial Thesis (parallel)
            result.status = DebateStatus.ROUND_1
            result.progress = 10
            round1 = await self._run_round1(question, document_text)
            result.rounds.append(round1)
            result.progress = 30

            # Round 2: Cross-Examination
            result.status = DebateStatus.ROUND_2
            round2 = await self._run_round2(question, round1)
            result.rounds.append(round2)
            result.progress = 50

            # Round 3: Rebuttal & Defense
            result.status = DebateStatus.ROUND_3
            round3 = await self._run_round3(question, round1, round2)
            result.rounds.append(round3)
            result.progress = 70

            # Round 4: CIO Synthesis
            result.status = DebateStatus.ROUND_4
            round4 = await self._run_round4(question, result.rounds)
            result.rounds.append(round4)
            result.progress = 90

            # Extract final recommendation and calibrate
            cio_response = round4.responses[0] if round4.responses else None
            if cio_response and cio_response.cio_synthesis:
                result.final_recommendation = cio_response.cio_synthesis
                raw_conviction = cio_response.cio_synthesis.consensus_conviction
                cal = _platt_calibrate(raw_conviction)
                result.consensus_score = ConsensusScore(
                    raw_score=raw_conviction,
                    calibrated_score=round(cal, 4),
                )

            result.status = DebateStatus.COMPLETED
            result.progress = 100
            result.completed_at = datetime.now()

        except Exception as e:
            logger.exception(f"Debate failed: {e}")
            result.status = DebateStatus.FAILED
            result.error = str(e)

        return result

    # ------------------------------------------------------------------
    # Round implementations
    # ------------------------------------------------------------------

    async def _run_round1(
        self, question: str, doc_text: str
    ) -> DebateRound:
        """Round 1: Each agent independently produces an initial thesis (parallel)."""
        round_obj = DebateRound(
            round_number=1,
            round_name="Initial Thesis Presentation",
            started_at=datetime.now(),
        )

        async def _agent_thesis(role: AgentRole) -> AgentResponse:
            cfg = AGENT_CONFIG[role]
            model = _get_model_for_role(role)
            fallback = Config.FALLBACK_MODEL
            messages = [
                {"role": "system", "content": cfg["system_prompt"]},
                {"role": "user", "content": _round1_prompt(question, doc_text)},
            ]
            text, model_used = await self.client.achat_with_fallback(
                messages, model, fallback, temperature=cfg["temperature"]
            )
            # Parse thesis
            thesis = None
            try:
                data = _safe_parse_json(text)
                thesis = AgentThesis(
                    direction=Direction(data.get("direction", "HOLD")),
                    conviction=float(data.get("conviction", 5)),
                    key_arguments=data.get("key_arguments", []),
                    key_risks=data.get("key_risks", []),
                    price_target=data.get("price_target"),
                    expected_return=data.get("expected_return"),
                    time_horizon=data.get("time_horizon"),
                    causal_factors=[
                        InvestmentFactor(**f)
                        for f in data.get("causal_factors", [])
                    ],
                )
            except Exception as e:
                logger.warning(f"Failed to parse thesis from {role}: {e}")

            return AgentResponse(
                agent_role=role,
                agent_name=cfg["name"],
                model_used=model_used,
                round_number=1,
                content=text,
                thesis=thesis,
            )

        tasks = [_agent_thesis(role) for role in DEBATE_AGENTS]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        for resp in responses:
            if isinstance(resp, Exception):
                logger.error(f"Agent error in round 1: {resp}")
            else:
                round_obj.responses.append(resp)

        round_obj.completed_at = datetime.now()
        return round_obj

    async def _run_round2(
        self, question: str, round1: DebateRound
    ) -> DebateRound:
        """Round 2: Cross-Examination — each agent challenges others."""
        round_obj = DebateRound(
            round_number=2,
            round_name="Cross-Examination",
            started_at=datetime.now(),
        )

        # Build thesis map
        all_theses: Dict[str, str] = {}
        for resp in round1.responses:
            all_theses[resp.agent_name] = resp.content

        async def _agent_cross(role: AgentRole) -> AgentResponse:
            cfg = AGENT_CONFIG[role]
            model = _get_model_for_role(role)
            fallback = Config.FALLBACK_MODEL
            messages = [
                {"role": "system", "content": cfg["system_prompt"]},
                {"role": "user", "content": _round2_prompt(question, cfg["name"], all_theses)},
            ]
            text, model_used = await self.client.achat_with_fallback(
                messages, model, fallback, temperature=cfg["temperature"]
            )
            cross = None
            try:
                data = _safe_parse_json(text)
                cross = CrossExamination(challenges=data.get("challenges", {}))
            except Exception as e:
                logger.warning(f"Failed to parse cross-exam from {role}: {e}")

            return AgentResponse(
                agent_role=role,
                agent_name=cfg["name"],
                model_used=model_used,
                round_number=2,
                content=text,
                cross_examination=cross,
            )

        tasks = [_agent_cross(role) for role in DEBATE_AGENTS]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        for resp in responses:
            if isinstance(resp, Exception):
                logger.error(f"Agent error in round 2: {resp}")
            else:
                round_obj.responses.append(resp)

        round_obj.completed_at = datetime.now()
        return round_obj

    async def _run_round3(
        self,
        question: str,
        round1: DebateRound,
        round2: DebateRound,
    ) -> DebateRound:
        """Round 3: Rebuttal & Defense."""
        round_obj = DebateRound(
            round_number=3,
            round_name="Rebuttal & Defense",
            started_at=datetime.now(),
        )

        # Build per-agent thesis text and challenges directed at each agent
        thesis_by_name: Dict[str, str] = {}
        for resp in round1.responses:
            thesis_by_name[resp.agent_name] = resp.content

        challenges_by_target: Dict[str, Dict[str, List[str]]] = {}
        for resp in round2.responses:
            if resp.cross_examination:
                for target, items in resp.cross_examination.challenges.items():
                    challenges_by_target.setdefault(target, {})[resp.agent_name] = items

        async def _agent_rebuttal(role: AgentRole) -> AgentResponse:
            cfg = AGENT_CONFIG[role]
            model = _get_model_for_role(role)
            fallback = Config.FALLBACK_MODEL
            my_thesis = thesis_by_name.get(cfg["name"], "")
            my_challenges = challenges_by_target.get(cfg["name"], {})
            messages = [
                {"role": "system", "content": cfg["system_prompt"]},
                {"role": "user", "content": _round3_prompt(question, my_thesis, my_challenges)},
            ]
            text, model_used = await self.client.achat_with_fallback(
                messages, model, fallback, temperature=cfg["temperature"]
            )
            rebuttal = None
            try:
                data = _safe_parse_json(text)
                rebuttal = Rebuttal(
                    defenses=data.get("defenses", []),
                    concessions=data.get("concessions", []),
                    updated_conviction=float(data.get("updated_conviction", 5)),
                    updated_direction=(
                        Direction(data["updated_direction"])
                        if data.get("updated_direction")
                        else None
                    ),
                )
            except Exception as e:
                logger.warning(f"Failed to parse rebuttal from {role}: {e}")

            return AgentResponse(
                agent_role=role,
                agent_name=cfg["name"],
                model_used=model_used,
                round_number=3,
                content=text,
                rebuttal=rebuttal,
            )

        tasks = [_agent_rebuttal(role) for role in DEBATE_AGENTS]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        for resp in responses:
            if isinstance(resp, Exception):
                logger.error(f"Agent error in round 3: {resp}")
            else:
                round_obj.responses.append(resp)

        round_obj.completed_at = datetime.now()
        return round_obj

    async def _run_round4(
        self, question: str, rounds: List[DebateRound]
    ) -> DebateRound:
        """Round 4: CIO Synthesis — single CIO agent synthesizes everything."""
        round_obj = DebateRound(
            round_number=4,
            round_name="CIO Synthesis & Consensus",
            started_at=datetime.now(),
        )

        # Build full transcript
        transcript_parts = []
        for rd in rounds:
            transcript_parts.append(f"\n=== {rd.round_name} (Round {rd.round_number}) ===\n")
            for resp in rd.responses:
                transcript_parts.append(f"--- {resp.agent_name} ---\n{resp.content}\n")
        full_transcript = "\n".join(transcript_parts)

        # Truncate if too long
        if len(full_transcript) > 20000:
            full_transcript = full_transcript[:20000] + "\n... [truncated]"

        cfg = AGENT_CONFIG[AgentRole.CIO]
        model = _get_model_for_role(AgentRole.CIO)
        fallback = Config.FALLBACK_MODEL
        messages = [
            {"role": "system", "content": cfg["system_prompt"]},
            {"role": "user", "content": _round4_prompt(question, full_transcript)},
        ]
        text, model_used = await self.client.achat_with_fallback(
            messages, model, fallback, temperature=cfg["temperature"]
        )

        synthesis = None
        try:
            data = _safe_parse_json(text)
            synthesis = CIOSynthesis(
                recommendation=Direction(data.get("recommendation", "HOLD")),
                confidence_distribution=data.get("confidence_distribution", {}),
                consensus_conviction=float(data.get("consensus_conviction", 5)),
                key_thesis=data.get("key_thesis", ""),
                primary_risks=data.get("primary_risks", []),
                position_sizing_guidance=data.get("position_sizing_guidance"),
                dissenting_views=data.get("dissenting_views", []),
                debate_quality_score=float(data.get("debate_quality_score", 5)),
            )
        except Exception as e:
            logger.warning(f"Failed to parse CIO synthesis: {e}")

        response = AgentResponse(
            agent_role=AgentRole.CIO,
            agent_name=cfg["name"],
            model_used=model_used,
            round_number=4,
            content=text,
            cio_synthesis=synthesis,
        )
        round_obj.responses.append(response)
        round_obj.completed_at = datetime.now()
        return round_obj


# ---------------------------------------------------------------------------
# JSON parsing helper
# ---------------------------------------------------------------------------

import json
import re


def _safe_parse_json(text: str) -> dict:
    """Best-effort JSON extraction from LLM output."""
    cleaned = text.strip()
    # Remove markdown fences
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try to find a JSON object in the text
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    logger.warning(f"Could not parse JSON from LLM output (first 200 chars): {cleaned[:200]}")
    return {}
