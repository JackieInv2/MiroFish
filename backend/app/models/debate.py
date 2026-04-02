"""
Investment Debate Models
Pydantic models for the structured IC-style debate system.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class Magnitude(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TimeHorizon(str, Enum):
    NEAR_TERM = "near_term"
    MEDIUM_TERM = "medium_term"
    LONG_TERM = "long_term"


class AgentRole(str, Enum):
    QUANT_ANALYST = "quant_analyst"
    FUNDAMENTAL_ANALYST = "fundamental_analyst"
    RISK_MANAGER = "risk_manager"
    DEVIL_ADVOCATE = "devil_advocate"
    CIO = "cio"


class DebateStatus(str, Enum):
    PENDING = "pending"
    ROUND_1 = "round_1"
    ROUND_2 = "round_2"
    ROUND_3 = "round_3"
    ROUND_4 = "round_4"
    COMPLETED = "completed"
    FAILED = "failed"


class InvestmentFactor(BaseModel):
    """Causal reasoning factor inspired by AIA Forecaster's CausalFactor."""
    event: str
    channel: str
    direction: str  # "bullish" or "bearish"
    magnitude: Magnitude = Magnitude.MEDIUM
    confidence: float = Field(ge=0.0, le=1.0)
    time_horizon: TimeHorizon = TimeHorizon.MEDIUM_TERM


class AgentThesis(BaseModel):
    """Round 1 output: an agent's initial investment thesis."""
    direction: Direction
    conviction: float = Field(ge=1.0, le=10.0)
    key_arguments: List[str]
    key_risks: List[str]
    price_target: Optional[str] = None
    expected_return: Optional[str] = None
    time_horizon: Optional[str] = None
    causal_factors: List[InvestmentFactor] = Field(default_factory=list)


class CrossExamination(BaseModel):
    """Round 2 output: an agent's challenges to other agents."""
    challenges: Dict[str, List[str]]  # agent_role -> list of challenges


class Rebuttal(BaseModel):
    """Round 3 output: an agent's rebuttal/defense."""
    defenses: List[str]
    concessions: List[str]
    updated_conviction: float = Field(ge=1.0, le=10.0)
    updated_direction: Optional[Direction] = None


class CIOSynthesis(BaseModel):
    """Round 4 output: CIO's final synthesis."""
    recommendation: Direction
    confidence_distribution: Dict[str, float]  # e.g. {"BUY": 0.75, "HOLD": 0.20, "SELL": 0.05}
    consensus_conviction: float = Field(ge=1.0, le=10.0)
    key_thesis: str
    primary_risks: List[str]
    position_sizing_guidance: Optional[str] = None
    dissenting_views: List[str] = Field(default_factory=list)
    debate_quality_score: float = Field(ge=1.0, le=10.0)


class AgentResponse(BaseModel):
    """A single agent's response in a debate round."""
    agent_role: AgentRole
    agent_name: str
    model_used: str
    round_number: int
    content: str  # Raw LLM output
    thesis: Optional[AgentThesis] = None
    cross_examination: Optional[CrossExamination] = None
    rebuttal: Optional[Rebuttal] = None
    cio_synthesis: Optional[CIOSynthesis] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class DebateRound(BaseModel):
    """A complete debate round containing all agent responses."""
    round_number: int
    round_name: str
    responses: List[AgentResponse] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ConsensusScore(BaseModel):
    """Calibrated consensus score using Platt scaling."""
    raw_score: float
    calibrated_score: float
    alpha: float = 1.7320508075688772  # sqrt(3)


class DebateResult(BaseModel):
    """Full debate result with all rounds and final recommendation."""
    debate_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    question: str
    file_name: Optional[str] = None
    status: DebateStatus = DebateStatus.PENDING
    rounds: List[DebateRound] = Field(default_factory=list)
    final_recommendation: Optional[CIOSynthesis] = None
    consensus_score: Optional[ConsensusScore] = None
    created_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    progress: int = 0  # 0-100
