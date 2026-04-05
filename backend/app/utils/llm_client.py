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
    Document-aware mock provider — every agent produces a genuinely distinct
    perspective grounded in the submitted document text.

    Design principles:
    - Agent identity is resolved from the system prompt, not guessed
    - No prompt text ever leaks into user-visible output
    - Each agent has a fixed analytical lens and unique voice
    - Round 2 challenges are AGENT-SPECIFIC (each agent challenges others from its own lens)
    - Round 3 defenses reference the actual challenge raised, not a generic phrase
    - Round 4 CIO never touches Round-prompt sentences
    """

    _BULLISH_KEYWORDS = [
        "growth", "profit", "margin", "beat", "record", "expand", "moat",
        "upgrade", "opportunity", "upside", "strong", "accelerat", "dominant",
        "cash flow", "buyback", "dividend", "undervalued", "outperform",
        "revenue", "beat", "guidance", "raised", "market share",
    ]
    _BEARISH_KEYWORDS = [
        "loss", "decline", "debt", "lawsuit", "fraud", "bankruptcy", "miss",
        "downgrade", "headwind", "concern", "weak", "poor", "negative",
        "short", "overvalued", "bubble", "impairment", "write-off",
        "competition", "risk", "compress", "cut", "reduce", "slow",
    ]

    # Each agent's analytical DNA
    _AGENT_PERSONA = {
        "quant": {
            "name": "Quant Analyst",
            "focus": "valuation multiples, revenue CAGR, margin trajectory, momentum signals",
            "voice": "data-driven and precise",
            "buy_args": [
                "revenue growth rate of {num1} signals accelerating top-line momentum — statistically associated with multiple expansion at similar market cap inflection points",
                "gross margin trajectory of {num2} is tracking above the sector 75th percentile; operating leverage should amplify EPS by 1.8–2.2x revenue growth",
                "forward PE of {num3} is trading at a 15% discount to historical growth-adjusted comps, implying a margin of safety on a DCF basis",
            ],
            "sell_args": [
                "regression analysis of {num1} revenue growth at this market cap historically precedes a 20–35% drawdown within 6 quarters as growth inevitably decelerates",
                "margin compression of {num2} is a leading indicator of earnings revisions — quantitative screens flag this pattern in 73% of similar deceleration cycles",
                "at {num3} forward PE, the multiple embeds 3+ years of perfection; any guidance cut triggers a 2.5–3x earnings downside on discounted cash flow",
            ],
            "hold_args": [
                "momentum signals are neutral: RSI in mid-band, no significant volume divergence; the {num1} data point is priced in",
                "at {num2}, valuation sits at fair value on a 5-year DCF; no statistical edge to enter or exit at current levels",
                "risk-adjusted return is symmetric; I score this a 5.5/10 conviction HOLD pending a cleaner catalyst signal",
            ],
            "buy_risks": [
                "mean reversion risk: hyper-growth multiples historically compress 40–60% on first guidance miss",
                "concentration risk if {num1} revenue stream faces a structural headwind",
            ],
            "sell_risks": [
                "short squeeze risk if sentiment turns — high short interest at current levels",
                "timing risk: quantitative bear signals can persist for 2–4 quarters before resolving",
            ],
            "hold_risks": [
                "opportunity cost: holding cash-equivalent returns while waiting for a catalyst",
                "risk of narrative shift forcing a rapid re-rating in either direction",
            ],
        },
        "fundamental": {
            "name": "Fundamental Analyst",
            "focus": "business model quality, competitive moat, management execution, TAM expansion",
            "voice": "qualitative and long-term oriented",
            "buy_args": [
                "the business model demonstrates durable pricing power — {doc1} points to a widening moat that competitors cannot replicate in a 3–5 year horizon",
                "management has a track record of capital allocation discipline; the {num1} figure reflects earnings quality, not financial engineering",
                "TAM is expanding faster than consensus assumes: {doc2} signals an early-stage adoption curve with multiple innings of growth ahead",
            ],
            "sell_args": [
                "the apparent moat described in '{doc1}' is eroding — substitute products and margin pressure indicate the competitive advantage period is shortening",
                "management credibility is at risk: {num1} is inconsistent with prior guidance, suggesting either weak visibility or overpromising to buy time",
                "TAM is being over-estimated; penetration rates implied by current consensus require market conditions that don't survive contact with competitive reality",
            ],
            "hold_args": [
                "the business model is sound but the near-term catalyst path is unclear — '{doc1}' is a lagging indicator of moat strength",
                "management execution has been solid, but at {num1} the valuation leaves little room for error over a 12-month horizon",
                "fundamentals justify the current price; I need a clearer catalyst before recommending incremental exposure",
            ],
            "buy_risks": [
                "key-man and execution risk: growth depends on continued product innovation that is difficult to forecast",
                "competitive response from incumbents could pressure unit economics before moat is fully established",
            ],
            "sell_risks": [
                "the bear thesis could be invalidated by a strategic pivot or M&A that unlocks hidden value",
                "qualitative moat deterioration is slow to show up in financials — timing a fundamental short is difficult",
            ],
            "hold_risks": [
                "catalyst optionality may cause the stock to re-rate sharply while we wait for confirmation",
                "holding a HOLD when fundamentals are inflecting can result in chasing performance",
            ],
        },
        "risk": {
            "name": "Risk Manager",
            "focus": "tail risk, drawdown scenarios, liquidity, correlation breakdown, position sizing",
            "voice": "conservative, stress-focused, and granular",
            "buy_args": [
                "under my base-case stress test, even a 25% revenue miss (bear scenario) leaves the equity value supported above current price by {num1} in net cash",
                "liquidity profile is strong — {num2} cash generation covers 3x our projected max drawdown in a 1-in-10 year scenario",
                "correlation to the broader market is below 0.6 at current beta, offering portfolio diversification benefit that justifies a 1.5–2% allocation",
            ],
            "sell_args": [
                "tail risk is severely underpriced: a 2-sigma adverse move on {doc1} would result in a 40–55% drawdown, far exceeding the reward case",
                "liquidity deterioration risk: if {num1} guidance is cut, the stock could gap down 20%+ in a single session with no institutional support at that level",
                "risk-adjusted Sharpe on this position is 0.4 — below our 0.8 threshold; I cannot recommend adding exposure at these levels",
            ],
            "hold_args": [
                "the risk/reward is balanced but not compelling: {doc1} represents a known risk that is partially priced in, limiting upside",
                "I am comfortable with a 1% portfolio allocation at these levels, but not more — the max drawdown scenario of {num1} is material",
                "recommend maintaining current position size with a hard stop at -15% to manage tail risk",
            ],
            "buy_risks": [
                "concentration risk: {num1} revenue is highly dependent on a single segment — a demand shift creates outsized downside",
                "macro correlation spikes in risk-off environments could cause forced selling regardless of fundamentals",
            ],
            "sell_risks": [
                "short position carries unlimited theoretical loss; gamma risk if positive catalyst triggers a squeeze",
                "position sizing must be strictly capped at 1–2% of portfolio given asymmetric risk profile",
            ],
            "hold_risks": [
                "complacency risk: HOLD positions often drift to larger size as other positions rotate — discipline on sizing is critical",
                "stop-loss discipline: if the {num1} thesis driver deteriorates further, I will recommend a full exit immediately",
            ],
        },
        "devil": {
            "name": "Devil's Advocate",
            "focus": "hidden assumptions, consensus blind spots, contrarian scenarios the committee is ignoring",
            "voice": "adversarial, rigorous, and deliberately provocative",
            "buy_args": [  # Devil flips to BUY when consensus is SELL/HOLD
                "the committee is anchoring on near-term data; {doc1} is actually a contrarian BUY signal — the market is extrapolating a temporary headwind into a permanent structural impairment",
                "consensus SELL is itself the risk: short interest is at extreme levels, and any positive data point on {num1} will trigger a violent squeeze that punishes the late shorts",
                "the bear case requires multiple things to go wrong simultaneously; the committee is assigning too much probability to tail scenarios that require correlated adverse outcomes",
            ],
            "sell_args": [  # Devil flips to SELL when consensus is BUY/HOLD
                "the committee is engaging in recency bias — {doc1} looks strong in isolation, but the trend is decelerating and every bull market top has had analysts defending the same thesis",
                "at {num1}, the margin of safety is zero; the entire BUY case requires the best-case scenario to materialize and everything else to hold — that is not an investment, that is a bet",
                "I challenge the committee to model a world where {doc2} does not recover — the resulting equity value is 40–60% below current price, and the probability of that scenario is non-trivial",
            ],
            "hold_args": [  # Devil challenges HOLD consensus
                "HOLD is not a neutral position — it is a decision to accept the current risk/reward. I submit that {doc1} makes this risk/reward materially worse than acknowledged",
                "the committee's conviction of 5.5/10 signals insufficient edge; we should either have conviction to act or admit we don't know and stay away entirely",
                "HOLD positions create anchoring effects — the committee will be slow to exit when the thesis breaks because they never fully committed to a view",
            ],
            "buy_risks": [
                "hidden leverage in the business model: {doc1} understates the operating leverage that amplifies both upside and downside",
                "the contrarian BUY only works if the market re-rates the narrative — timing that re-rating is the key risk",
            ],
            "sell_risks": [
                "the bearish narrative can be sustained by management longer than the shorts can remain solvent",
                "regulatory or strategic intervention could change the thesis in ways that are difficult to model",
            ],
            "hold_risks": [
                "intellectual honesty demands we acknowledge: if we cannot form a view, perhaps we lack the information edge to be invested at all",
                "the market will not stay at 'fair value' — we either earn alpha by acting or we are indexing at stock-picking fees",
            ],
        },
    }

    @staticmethod
    def _detect_agent(messages):
        sys_text = next(
            (m.get("content", "") for m in messages if m.get("role") == "system"), ""
        ).lower()
        if "quant" in sys_text:
            return "quant"
        if "fundamental" in sys_text:
            return "fundamental"
        if "risk" in sys_text or "chief risk" in sys_text:
            return "risk"
        if "devil" in sys_text or "adversar" in sys_text or "advocate" in sys_text:
            return "devil"
        if "cio" in sys_text or "chief investment" in sys_text:
            return "cio"
        return "quant"

    @staticmethod
    def _detect_round(messages):
        text = " ".join(m.get("content", "") for m in messages).lower()
        if "cio" in text and ("synthesis" in text or "final recommendation" in text):
            return 4
        if "rebuttal" in text or "defense" in text:
            return 3
        if "cross-examination" in text or "cross examination" in text:
            return 2
        return 1

    @staticmethod
    def _extract_context(messages):
        """Extract question and CLEAN document text from messages.

        Critically: stops at any instruction boundary so prompt text never
        appears in user-visible content.
        """
        user_text = ""
        for m in messages:
            if m.get("role") == "user":
                user_text = m.get("content", "")
                break

        # Extract question
        question = "this investment"
        for pat in [
            r'\*\*Question:\*\*\s*(.+?)(?:\n|$)',
            r'Question:\s*(.+?)(?:\n|$)',
        ]:
            m = re.search(pat, user_text)
            if m:
                question = m.group(1).strip()
                break

        # Extract document — stop hard at instruction boundaries
        STOP = r'(?=\nRespond with|\n\{|\*\*Question|\nYou are now|\nRound \d|===|---|\Z)'
        doc = ""
        for pat in [
            r'\*\*Document:\*\*\s*([\s\S]+?)' + STOP,
            r'Document:\s*([\s\S]+?)' + STOP,
        ]:
            dm = re.search(pat, user_text)
            if dm and len(dm.group(1).strip()) > 20:
                doc = dm.group(1).strip()[:3000]
                break

        # Fallback: use user_text but strip anything after instruction markers
        if not doc:
            clean = re.split(
                r'\nRespond with|\nYou are now|\n===|\n---|\n\{', user_text
            )[0]
            doc = clean.strip()[:2000]

        return question, doc

    @staticmethod
    def _score_sentiment(text):
        text_l = text.lower()
        bull = sum(text_l.count(k) for k in MockProvider._BULLISH_KEYWORDS)
        bear = sum(text_l.count(k) for k in MockProvider._BEARISH_KEYWORDS)
        total = bull + bear or 1
        ratio = bull / total
        if ratio > 0.58:
            return "BUY", round(min(8.5, 5.5 + ratio * 3.0), 1)
        elif ratio < 0.42:
            return "SELL", round(min(8.0, 4.0 + (1 - ratio) * 3.0), 1)
        else:
            return "HOLD", 5.5

    @staticmethod
    def _clean_sentences(text, n=6):
        """Extract clean sentences from the document — never prompt text."""
        PROMPT_MARKERS = [
            "respond with", "you are ", "round name", "=== ", "--- ",
            "json object", "full debate", "transcript", "investment committee",
            "produce the final", "review the full",
        ]
        sents = re.split(r'(?<=[.!?])\s+', text.replace('\n', ' '))
        out = []
        for s in sents:
            sl = s.strip().lower()
            if len(sl) < 35:
                continue
            if any(p in sl for p in PROMPT_MARKERS):
                continue
            out.append(s.strip())
            if len(out) >= n:
                break
        return out

    @staticmethod
    def _numbers(text):
        return re.findall(
            r'\$[\d,]+(?:\.\d+)?(?:[BMK]|\s*(?:billion|million))?|[\d,]+(?:\.\d+)?%|[\d.]+x',
            text
        )[:6]

    def _fill_template(self, template, nums, sents, direction):
        """Fill {num1}/{num2}/{doc1}/{doc2} placeholders safely."""
        replacements = {
            "{num1}": nums[0] if nums else "the key metric",
            "{num2}": nums[1] if len(nums) > 1 else "the second data point",
            "{num3}": nums[2] if len(nums) > 2 else "the valuation multiple",
            "{doc1}": sents[0][:80] if sents else "the submitted document",
            "{doc2}": sents[1][:80] if len(sents) > 1 else "the supporting data",
        }
        for k, v in replacements.items():
            template = template.replace(k, v)
        return template

    def _build_round1(self, messages):
        question, doc = self._extract_context(messages)
        direction, conviction = self._score_sentiment(doc)
        agent = self._detect_agent(messages)
        persona = self._AGENT_PERSONA.get(agent, self._AGENT_PERSONA["quant"])
        sents = self._clean_sentences(doc, n=6)
        nums = self._numbers(doc)

        # Devil's Advocate always takes the contrarian position
        if agent == "devil":
            if direction == "BUY":
                eff_dir = "SELL"
            elif direction == "SELL":
                eff_dir = "BUY"
            else:
                eff_dir = "SELL"  # Challenge the HOLD consensus
            conviction = max(3.5, conviction - 1.5)
        else:
            eff_dir = direction
            if agent == "risk":
                conviction = max(2.0, conviction - 1.5)

        # Select template set based on effective direction
        dir_key = eff_dir.lower()
        arg_templates = persona.get(f"{dir_key}_args", persona["hold_args"])
        risk_templates = persona.get(f"{dir_key}_risks", persona["hold_risks"])

        args = [self._fill_template(t, nums, sents, eff_dir) for t in arg_templates[:3]]
        risks = [self._fill_template(t, nums, sents, eff_dir) for t in risk_templates[:2]]

        # Price target: first $ figure from doc
        price_target = next((n for n in nums if "$" in n), None)
        num1 = nums[0] if nums else "N/A"

        return {
            "direction": eff_dir,
            "conviction": round(conviction, 1),
            "key_arguments": args,
            "key_risks": risks,
            "price_target": price_target,
            "expected_return": (
                "15-25% upside over 12 months" if eff_dir == "BUY"
                else "-15% to -30% over 12 months" if eff_dir == "SELL"
                else "0-5% with high dispersion"
            ),
            "time_horizon": "12 months",
            "causal_factors": [
                {
                    "event": sents[0][:90] if sents else f"Primary driver from research on {question[:60]}",
                    "channel": (
                        "Valuation re-rating via multiple expansion" if eff_dir == "BUY"
                        else "Earnings compression and multiple de-rating" if eff_dir == "SELL"
                        else "Range-bound price action pending catalyst"
                    ),
                    "direction": "bullish" if eff_dir == "BUY" else "bearish",
                    "magnitude": "high" if conviction > 7 else "medium",
                    "confidence": round(conviction / 10.0, 2),
                    "time_horizon": "medium_term",
                }
            ],
        }

    def _build_round2(self, messages):
        """Each agent challenges the OTHER agents from its own analytical lens."""
        question, doc = self._extract_context(messages)
        direction, conviction = self._score_sentiment(doc)
        agent = self._detect_agent(messages)
        sents = self._clean_sentences(doc, n=4)
        nums = self._numbers(doc)
        s0 = sents[0][:90] if sents else "the primary thesis driver"
        s1 = sents[1][:90] if len(sents) > 1 else "the margin assumption"
        n0 = nums[0] if nums else "the key metric"
        n1 = nums[1] if len(nums) > 1 else "the valuation multiple"
        opp = "SELL" if direction == "BUY" else "BUY"

        if agent == "quant":
            return {
                "challenges": {
                    "Fundamental Analyst": [
                        f"Your moat narrative is unfalsifiable. Show me the data: at {n0}, where exactly does pricing power show up in the unit economics?",
                        f"You cite qualitative business quality, but '{s0}' — a quant screen of peers at similar inflection points shows this narrative has a 55% failure rate.",
                    ],
                    "Risk Manager": [
                        f"Your stress test uses a 25% revenue miss as the bear case, but mean-reversion analysis at {n1} multiples implies a 40% miss is the historically correct tail scenario.",
                        "You're anchoring on historical max-drawdown — in a liquidity crisis, correlations go to 1 and your hedges fail simultaneously.",
                    ],
                    "Devil's Advocate": [
                        f"Your contrarian call requires the market to be wrong about {s1} for 12+ months. What's the quantitative edge that tells us the market's consensus pricing is incorrect?",
                        f"Contrarian positions backed by narrative alone have negative alpha; give me a factor signal or a mean-reversion trigger, not a story.",
                    ],
                }
            }
        elif agent == "fundamental":
            return {
                "challenges": {
                    "Quant Analyst": [
                        f"You are over-indexing on {n0} as if it were a complete picture. The quant model misses the qualitative shift happening in '{s0}' — no regression captures that.",
                        f"Momentum signals at {n1} are a lagging indicator of business quality change. By the time your quant screen confirms the thesis, the alpha is already gone.",
                    ],
                    "Risk Manager": [
                        "Your tail-risk framework is backward-looking and misses the structural change in this business's competitive position — you are protecting against the last crisis, not the next one.",
                        f"The max drawdown scenarios you cite assume mean reversion of fundamentals, but '{s1}' suggests this company's normalized earnings power is materially higher than the model assumes.",
                    ],
                    "Devil's Advocate": [
                        f"Devil's Advocate is confusing cyclical headwinds with structural impairment. '{s0}' looks like disruption but has the characteristics of a temporary industry dislocation.",
                        "Your adversarial thesis requires the management team to be either incompetent or dishonest — a strong burden of proof that your analysis has not met.",
                    ],
                }
            }
        elif agent == "risk":
            return {
                "challenges": {
                    "Quant Analyst": [
                        f"A model that relies on {n0} as a mean-reversion anchor has not stress-tested a structural break scenario. In 2008 and 2020, every quant signal failed simultaneously.",
                        f"Your momentum factor at {n1} is not orthogonal to macro risk — in a credit event, the factor loading flips negative. Have you sized for that correlation breakdown?",
                    ],
                    "Fundamental Analyst": [
                        f"The moat you describe in '{s0}' is a source of idiosyncratic risk, not just protection. Concentration in a narrow competitive advantage creates catastrophic downside if that moat is breached.",
                        "Management track record is survivorship bias — the team has operated in a bull market; I need to see how they perform in a downturn before trusting their capital allocation.",
                    ],
                    "Devil's Advocate": [
                        f"Your contrarian {opp} thesis requires precise timing. What is the maximum drawdown the portfolio can absorb if the thesis takes 18–24 months to play out instead of 6?",
                        "Adversarial positions create their own tail risk — if the contrarian view is wrong and momentum continues, the loss profile is worse than a directional mistake in the consensus direction.",
                    ],
                }
            }
        else:  # devil
            return {
                "challenges": {
                    "Quant Analyst": [
                        f"Your entire quantitative case rests on {n0} mean-reverting to trend. But what if '{s0}' represents a structural break, not a cyclical deviation? Your model cannot distinguish the two.",
                        f"The momentum signal you cite has worked for 3 years in a low-rate environment. The regime has changed — I challenge you to show me the backtest in a rising-rate, slowing-growth regime.",
                    ],
                    "Fundamental Analyst": [
                        f"You say the moat is widening, but '{s1}' is the exact same thing analysts said about Kodak, Blockbuster, and Nokia before disruption arrived. How is this time different?",
                        f"The TAM expansion story at {n1} forward earnings requires 5 consecutive years of above-consensus execution. What is the probability of that, honestly?",
                    ],
                    "Risk Manager": [
                        "The risk manager's bear scenario is too conservative to be useful as a hedge and too mild to protect against the real tail. You have identified the wrong risks.",
                        f"Your 1–2% allocation recommendation is not a risk management decision — it is a hedge against being wrong without the courage to commit to a view. What does {n0} at stress conditions actually imply for the portfolio?",
                    ],
                }
            }

    def _build_round3(self, messages):
        """Each agent defends their Round 1 thesis with specific rebuttals to Round 2 challenges."""
        question, doc = self._extract_context(messages)
        direction, conviction = self._score_sentiment(doc)
        agent = self._detect_agent(messages)
        sents = self._clean_sentences(doc, n=4)
        nums = self._numbers(doc)
        s0 = sents[0][:100] if sents else "the core thesis driver"
        s1 = sents[1][:100] if len(sents) > 1 else "the supporting evidence"
        n0 = nums[0] if nums else "the key metric"
        n1 = nums[1] if len(nums) > 1 else "the secondary measure"

        if agent == "devil":
            eff_dir = "SELL" if direction == "BUY" else "BUY"
        else:
            eff_dir = direction
            if agent == "risk":
                conviction = max(2.0, conviction - 1.5)

        updated_conv = round(max(2.5, conviction - 0.5), 1)

        if agent == "quant":
            defenses = [
                f"The stress-test critique is valid but misdirected — I have run the bear scenario at 40% miss on {n0} and the equity still trades at a 10% discount to intrinsic value. The quantitative edge holds.",
                f"On mean-reversion timing: '{s0}' is not a narrative — it is a measurable factor with a 0.68 information coefficient over 24-month horizons. I am comfortable with the signal.",
            ]
            concessions = [
                f"I concede that {n1} correlation breakdown risk in a macro shock is underweighted in my base case — I will adjust the position size recommendation downward by 20% to account for that regime risk.",
            ]
        elif agent == "fundamental":
            defenses = [
                f"The disruption comparison is not analogous — the companies cited all faced technology substitution of their core product. Here, '{s0}' represents a demand expansion, not substitution.",
                f"Management's capital allocation history is not survivorship bias; the {n0} return on invested capital over the past 4 years has been achieved across two different macro regimes.",
            ]
            concessions = [
                f"I concede that the TAM expansion timeline at {n1} is uncertain — I will revise my 12-month price target to reflect a more conservative penetration curve, reducing my conviction by 0.5.",
            ]
        elif agent == "risk":
            defenses = [
                f"My max-drawdown scenario at {n0} is not backward-looking — it is calibrated to the specific liquidity profile of this name, which has traded with a bid-ask spread that widens 4x in stress periods.",
                f"On the moat concentration risk: I agree that '{s0}' creates concentration, but concentration in a genuine competitive advantage is different from single-factor risk. My position sizing already accounts for this.",
            ]
            concessions = [
                f"I concede that my {n1} stress scenario assumed a historical correlation structure that may understate the company's resilience in the current cycle — I will revise the tail scenario probability from 20% to 15%.",
            ]
        else:  # devil
            defenses = [
                f"The committee has not addressed the core challenge: the regime has changed. '{s0}' worked as a thesis driver in the prior environment; the burden of proof is on the bulls/bears to show it still holds.",
                f"On the timing critique: I do not need precise timing — I need the committee to acknowledge that the {n0} assumption embedded in the consensus target is fragile. That acknowledgment changes position sizing, which is my point.",
            ]
            concessions = [
                f"I concede that my contrarian position overstates the probability of a sharp near-term reversal. I will moderate my adversarial conviction from maximum to 6.5/10, acknowledging that the consensus thesis has merit on a 6-month horizon even if it is wrong at 18 months.",
            ]

        return {
            "defenses": defenses,
            "concessions": concessions,
            "updated_conviction": updated_conv,
            "updated_direction": eff_dir,
        }

    def _build_round4(self, messages):
        question, transcript = self._extract_context(messages)
        direction, conviction = self._score_sentiment(transcript)

        conviction_label = "high" if conviction > 7.5 else "moderate" if conviction > 5 else "low"

        # Direction-specific, clean primary risks — never from transcript text
        if direction == "BUY":
            thesis_stmt = f"The committee has reached a {conviction_label}-conviction BUY recommendation following four rounds of structured debate. The quantitative, fundamental, and risk analyses converge on the view that the submitted document supports a long position with a 12-month horizon."
            primary_risks = [
                "Guidance miss risk: any deceleration in the primary revenue driver will trigger multiple compression that is not priced into the BUY case",
                "Macro correlation risk: in a risk-off scenario, the position will underperform regardless of idiosyncratic thesis quality",
                "Execution risk: the BUY thesis depends on continued operational delivery at a pace that leaves zero room for strategic error",
            ]
            sizing = "2–3% portfolio weight; scale in over 3–4 weeks to manage entry risk. Hard stop at -12% from entry."
        elif direction == "SELL":
            thesis_stmt = f"The committee recommends a {conviction_label}-conviction SELL following debate that surfaced material fundamental and technical deterioration signals in the submitted document. The bear thesis is supported by quantitative, qualitative, and risk dimensions."
            primary_risks = [
                "Short squeeze risk: high short interest means a positive catalyst could trigger a violent covering rally that tests conviction",
                "Timing risk: the deterioration thesis may take 12–18 months to fully materialize, creating interim mark-to-market pain",
                "Structural improvement risk: management could execute a pivot that invalidates the core bear thesis before the market prices it in",
            ]
            sizing = "1–2% short position; strictly capped given asymmetric loss profile. Cover 50% if position moves against thesis by 10%."
        else:
            thesis_stmt = f"The committee has not reached directional conviction following four rounds of debate. The submitted document contains mixed signals that the quantitative, fundamental, and risk frameworks interpret differently. A HOLD recommendation reflects disciplined capital allocation — we do not act without edge."
            primary_risks = [
                "Opportunity cost risk: remaining on the sidelines while the stock moves materially in either direction",
                "Narrative shift risk: a single catalyst could rapidly resolve the ambiguity and disadvantage a flat position",
                "Anchoring risk: re-engaging after a sharp move will feel psychologically difficult — establish the re-entry conditions now",
            ]
            sizing = "No new position. Maintain existing exposure at no more than 1% of portfolio. Re-evaluate on next earnings print."

        if direction == "BUY":
            dist = {"BUY": round(min(0.70, 0.45 + (conviction - 5) * 0.05), 2), "HOLD": 0.25, "SELL": 0.10}
        elif direction == "SELL":
            dist = {"BUY": 0.10, "HOLD": 0.25, "SELL": round(min(0.70, 0.45 + (conviction - 5) * 0.05), 2)}
        else:
            dist = {"BUY": 0.30, "HOLD": 0.45, "SELL": 0.25}

        total = sum(dist.values())
        dist = {k: round(v / total, 2) for k, v in dist.items()}

        return {
            "recommendation": direction,
            "confidence_distribution": dist,
            "consensus_conviction": round(conviction - 0.3, 1),
            "key_thesis": thesis_stmt,
            "primary_risks": primary_risks,
            "position_sizing_guidance": sizing,
            "dissenting_views": [
                f"Devil's Advocate maintains that the {'SELL' if direction == 'BUY' else 'BUY' if direction == 'SELL' else 'directional'} case is underweighted. "
                f"The committee should stress-test the {direction} recommendation against a scenario where the primary thesis driver reverses within 6 months.",
            ],
            "debate_quality_score": round(7.5 + (conviction % 1.5) * 0.5, 1),
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
        import time
        time.sleep(0.3)
        return json.dumps(self._generate(messages))

    async def achat(self, messages, model, temperature=0.7, max_tokens=4096, **kwargs):
        import asyncio
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
