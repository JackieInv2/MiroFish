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
    Document-aware IC debate mock provider.

    Every agent has a fixed analytical lens and distinct voice.
    Named metrics (PE, margin, growth, cash, revenue) are extracted
    semantically so the right figure appears in the right context.
    No prompt text ever leaks into user-visible output.
    """

    _BULLISH_KEYWORDS = [
        "growth", "profit", "margin", "beat", "record", "expand", "moat",
        "upgrade", "opportunity", "upside", "strong", "accelerat", "dominant",
        "cash flow", "buyback", "dividend", "undervalued", "outperform",
        "revenue", "raised", "market share", "services",
    ]
    _BEARISH_KEYWORDS = [
        "loss", "decline", "debt", "lawsuit", "fraud", "bankruptcy", "miss",
        "downgrade", "headwind", "concern", "weak", "poor", "negative",
        "short", "overvalued", "bubble", "impairment", "write-off",
        "competition", "risk", "compress", "cut", "reduce", "slow", "erosion",
    ]

    # ── Named metric extraction ────────────────────────────────────────────
    @staticmethod
    def _extract_metrics(text):
        """
        Return a dict of semantically labelled metrics so templates always
        receive the right number in the right context.

        Keys: growth, margin, pe, revenue, cash, multiple, eps, share
              (all fall back to a generic label if not found)
        """
        import re
        t = text

        def find(patterns, fallback="the key figure"):
            for pat in patterns:
                m = re.search(pat, t, re.IGNORECASE)
                if m:
                    return m.group(0).strip().rstrip(".,;")
            return fallback

        growth  = find([r'(?:up|down|grew?|growth|YoY|QoQ|rose?)\s+[\d,]+(?:\.\d+)?%',
                        r'[\d,]+(?:\.\d+)?%\s+(?:YoY|QoQ|growth|increase)',
                        r'(?:revenue|sales)\s+(?:up|down)\s+[\d,]+(?:\.\d+)?%'])
        margin  = find([r'(?:gross|operating|net|EBIT[DA]*)\s+margin[s]?[:\s]+(?:of\s+)?[\d,]+(?:\.\d+)?%',
                        r'[\d,]+(?:\.\d+)?%\s+(?:gross|operating|net)\s+margin',
                        r'margin[s]?\s*[:\s]+(?:at |of |expanded? to |compressed? to )?[\d,]+(?:\.\d+)?%'])
        pe      = find([r'(?:forward\s+)?P[/\s]?E\s*[:\s]+(?:ratio\s+)?(?:of\s+)?[\d,]+(?:\.\d+)?[x]?',
                        r'[\d,]+(?:\.\d+)?x\s+(?:forward\s+)?(?:earnings|P[/\s]?E)',
                        r'(?:trades?|valued?|priced?)\s+at\s+[\d,]+(?:\.\d+)?x'])
        revenue = find([r'\$[\d,]+(?:\.\d+)?[BMK]?\s+(?:in\s+)?(?:revenue|sales|total revenue)',
                        r'revenue[:\s]+(?:of\s+)?\$[\d,]+(?:\.\d+)?[BMK]?',
                        r'\$[\d,]+(?:\.\d+)?[BMK]\s+(?:in\s+Q[1-4]|quarterly)'])
        cash    = find([r'(?:net\s+)?cash\s+(?:position\s*)?[:\s]+(?:of\s+)?\$[\d,]+(?:\.\d+)?[BMK]?',
                        r'\$[\d,]+(?:\.\d+)?[BMK]\s+(?:in\s+)?(?:net\s+)?cash',
                        r'(?:operating\s+)?cash\s+flow\s*[:\s]+(?:of\s+)?\$[\d,]+(?:\.\d+)?[BMK]?'])
        eps     = find([r'(?:EPS|earnings\s+per\s+share)\s*[:\s]+(?:of\s+)?\$[\d,]+(?:\.\d+)?',
                        r'\$[\d,]+(?:\.\d+)?\s+(?:EPS|consensus\s+EPS)'])
        share   = find([r'[\d,]+(?:\.\d+)?%\s+(?:market\s+)?share',
                        r'market\s+share\s+(?:of\s+)?[\d,]+(?:\.\d+)?%'])

        # Generic fallbacks: pull any dollar figure or percentage
        all_dollars = re.findall(r'\$[\d,]+(?:\.\d+)?[BMK]?', t)
        all_pcts    = re.findall(r'[\d,]+(?:\.\d+)?%', t)

        def best(val, pool, idx, fallback):
            if val != fallback:
                return val
            return pool[idx] if len(pool) > idx else fallback

        def clean_label(val):
            """Strip redundant prefix words from extracted metric strings."""
            val = re.sub(r'^(?:Gross |Operating |Net |Forward |consensus |up |down |revenue of )', '', val, flags=re.IGNORECASE)
            val = re.sub(r'\s+(?:YoY|QoQ|PE ratio|position|EPS|consensus EPS)\b.*', '', val, flags=re.IGNORECASE)
            # Strip isolated leading labels
            val = re.sub(r'^(?:forward\s+)?P[/\s]?E\s*[:\s]+(?:ratio\s+)?(?:of\s+)?', '', val, flags=re.IGNORECASE)
            val = re.sub(r'^margin[s]?\s*[:]\s*', '', val, flags=re.IGNORECASE)
            val = re.sub(r'^revenue\s*[:\s]+(?:of\s+)?', '', val, flags=re.IGNORECASE)
            val = re.sub(r'^EPS\s*[:\s]+(?:of\s+)?', '', val, flags=re.IGNORECASE)
            return val.strip().rstrip(".,;")

        def extract_dollar(val):
            """Extract the dollar amount from a cash/revenue string like 'cash position $48B'."""
            m = re.search(r'\$[\d,]+(?:\.\d+)?[BMKT]?', val)
            return m.group(0) if m else val

        raw_cash = best(cash, all_dollars, 1, "the net cash position")
        return {
            "growth":   clean_label(best(growth,  all_pcts,    0, "the YoY growth rate")),
            "margin":   clean_label(best(margin,  all_pcts,    1, "gross margin")),
            "pe":       clean_label(best(pe,      all_dollars, 0, "the current multiple")),
            "revenue":  clean_label(best(revenue, all_dollars, 0, "total revenue")),
            "cash":     extract_dollar(raw_cash) if raw_cash != "the net cash position" else "the net cash position",
            "eps":      clean_label(best(eps,     all_dollars, 2, "consensus EPS")),
            "share":    clean_label(best(share,   all_pcts,    2, "market share")),
        }

    # ── Sentence extraction ────────────────────────────────────────────────
    @staticmethod
    def _clean_sentences(text, n=6):
        """Return up to n clean, non-lede sentences from the document."""
        PROMPT_MARKERS = [
            "respond with", "you are ", "round name", "=== ", "--- ",
            "json object", "full debate", "transcript", "investment committee",
            "produce the final", "review the full",
        ]
        # Heuristic: the first sentence is usually a company/revenue lede — skip it
        sents = re.split(r'(?<=[.!?])\s+', text.replace('\n', ' '))
        out = []
        for i, s in enumerate(sents):
            sl = s.strip().lower()
            if len(sl) < 35:
                continue
            if any(p in sl for p in PROMPT_MARKERS):
                continue
            # Skip raw analytical labels
            if sl.startswith("key risk:") or sl.startswith("key risks:") or ": " in sl[:20]:
                continue
            # Skip the first sentence if it starts with a company name or "X reported/announced"
            if i == 0 and re.match(r'^[A-Z][a-zA-Z ]+(?:Inc|Corp|Ltd|LLC|Co\.)?\s+(?:Q[1-4]|FY|reported|announced|revenue)', s.strip()):
                continue
            out.append(s.strip())
            if len(out) >= n:
                break
        return out

    @staticmethod
    def _short_phrase(sents, idx, fallback, maxlen=70):
        """Return a clean short phrase from sents[idx], stripped of trailing punctuation."""
        if idx < len(sents):
            s = sents[idx].rstrip('.')
            # If still long, take up to the first comma or semicolon
            for sep in [', ', '; ', ' — ', ' - ']:
                if len(s) > maxlen and sep in s:
                    s = s[:s.index(sep)]
            if len(s) > maxlen:
                # Truncate at last word boundary before maxlen
                s = s[:maxlen].rsplit(' ', 1)[0]
            return s
        return fallback

    # ── Sentiment scoring ──────────────────────────────────────────────────
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

    # ── Agent / round detection ────────────────────────────────────────────
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

    # ── Context extraction ─────────────────────────────────────────────────
    @staticmethod
    def _extract_context(messages):
        user_text = ""
        for m in messages:
            if m.get("role") == "user":
                user_text = m.get("content", "")
                break

        question = "this investment"
        for pat in [r'\*\*Question:\*\*\s*(.+?)(?:\n|$)', r'Question:\s*(.+?)(?:\n|$)']:
            match = re.search(pat, user_text)
            if match:
                question = match.group(1).strip()
                break

        STOP = r'(?=\nRespond with|\n\{|\*\*Question|\nYou are now|\nRound \d|===|---|\Z)'
        doc = ""
        for pat in [r'\*\*Document:\*\*\s*([\s\S]+?)' + STOP,
                    r'Document:\s*([\s\S]+?)' + STOP]:
            dm = re.search(pat, user_text)
            if dm and len(dm.group(1).strip()) > 20:
                doc = dm.group(1).strip()[:3000]
                break

        if not doc:
            clean = re.split(r'\nRespond with|\nYou are now|\n===|\n---|\n\{', user_text)[0]
            doc = clean.strip()[:2000]

        return question, doc

    # ── Round 1 ───────────────────────────────────────────────────────────
    def _build_round1(self, messages):
        question, doc = self._extract_context(messages)
        direction, conviction = self._score_sentiment(doc)
        agent   = self._detect_agent(messages)
        sents   = self._clean_sentences(doc, n=6)
        metrics = self._extract_metrics(doc)

        g  = metrics["growth"]
        m  = metrics["margin"]
        pe = metrics["pe"]
        rv = metrics["revenue"]
        ca = metrics["cash"]
        ep = metrics["eps"]
        sh = metrics["share"]

        # Pick a meaningful short insight sentence (not sentence[0] which is usually the lede)
        # Use metric-derived topic labels — never raw doc sentences in template strings
        _gr  = metrics['growth']  if metrics['growth']  not in ('the YoY growth rate',) else ''
        _mg  = metrics['margin']  if metrics['margin']  not in ('gross margin',)        else ''
        _pe  = metrics['pe']      if metrics['pe']      not in ('the current multiple',) else ''
        _ca  = metrics['cash']    if metrics['cash']    != 'the net cash position' else ''
        _ep  = metrics['eps']     if metrics['eps']     not in ('consensus EPS',)        else ''
        _rv  = metrics['revenue'] if metrics['revenue'] not in ('total revenue',)        else ''
        insight1  = (f"{_gr} revenue growth" if _gr else "the growth trajectory")
        insight2  = (f"{_mg} margins" if _mg else "the margin profile")
        # Build risk phrase from document sentences — extract a clean topic, not a raw sentence
        _raw_risk = self._short_phrase(sents, len(sents) - 1, "", maxlen=60) if sents else ""
        # Strip leading "Key risk:" / "Risk:" if it slipped through
        _raw_risk = re.sub(r'^(?:Key\s+)?risks?:\s*', '', _raw_risk, flags=re.IGNORECASE).strip()
        # Truncate at verbs/connectors to keep only the topic noun phrase
        _raw_risk = re.split(r'\s+(?:represents?|remains?|is|are|could|would|will|may|should|has|have)\s+', _raw_risk)[0].strip()
        risk_sent = _raw_risk if _raw_risk else "the identified risk factor"

        if agent == "devil":
            eff_dir = "SELL" if direction == "BUY" else "BUY" if direction == "SELL" else "SELL"
            conviction = max(3.5, conviction - 1.5)
        else:
            eff_dir = direction
            if agent == "risk":
                conviction = max(2.0, conviction - 1.5)

        # ── Agent-specific argument generation ────────────────────────────
        if agent == "quant":
            if eff_dir == "BUY":
                args = [
                    f"Revenue growth of {g} is in the top quintile of large-cap peers — factor screens associate this momentum with 18–24% median forward returns over 12 months",
                    f"At {pe}, the stock trades at a 12–15% discount to growth-adjusted comps on a PEG basis; the multiple is not stretched relative to the {g} top-line trajectory",
                    f"Gross margin of {m} creates significant operating leverage — a 1% revenue beat should translate to 2.2–2.5x EPS upside versus consensus {ep}",
                ]
                risks = [
                    f"Mean-reversion risk: growth stocks at {pe} historically de-rate 35–50% on the first guidance cut; the quantitative edge disappears if {g} decelerates by even 5 percentage points",
                    f"Factor model crowding — the momentum signal is consensus; any macro regime shift will cause institutional liquidation before the fundamental thesis plays out",
                ]
            elif eff_dir == "SELL":
                args = [
                    f"Revenue growth decelerating to {g} at a {pe} multiple is historically associated with 25–40% drawdowns as the market reprices growth expectations",
                    f"Margin compression from {m} levels is a leading indicator of consensus earnings cuts — quant screens flag this setup in 70% of similar deceleration cycles across sectors",
                    f"At {pe} on {ep} EPS consensus, the stock prices in 4+ years of perfect execution; any miss triggers 2.5–3x downside leverage on a DCF basis",
                ]
                risks = [
                    f"Short squeeze risk if {g} growth stabilizes — high short interest means a single positive data point triggers violent covering",
                    "Timing risk: quantitative bear signals can persist for 2–4 quarters before the fundamental deterioration shows up in consensus estimates",
                ]
            else:  # HOLD
                args = [
                    f"At {pe}, the multiple fully reflects {g} growth — the stock is fairly priced, not cheap; quantitative screens show no statistical alpha at current entry",
                    f"Margin profile at {m} is healthy but priced in — upside requires either multiple expansion or a growth re-acceleration that is not visible in the data",
                    f"Risk/reward is symmetric at {ep} consensus EPS; I score this a 5.5/10 conviction HOLD pending a cleaner catalyst signal from the earnings cadence",
                ]
                risks = [
                    f"Opportunity cost risk: fair value is not the same as a good investment — holding at {pe} when alternatives offer better risk-adjusted return is a hidden loss",
                    f"Sentiment shift risk: a single catalyst could re-rate {g} growth expectations sharply, leaving a neutral positioning caught in either direction",
                ]

        elif agent == "fundamental":
            if eff_dir == "BUY":
                args = [
                    f"The installed base and services attach rate compound in a way the market systematically underestimates — {insight1} understates the platform stickiness that sustains pricing power across cycles",
                    f"Management capital allocation is disciplined: {ca} in net cash and active buybacks signal confidence in free cash flow durability, not financial engineering",
                    f"The TAM expansion runway is longer than consensus models assume — {insight2} is consistent with a business that has not yet been forced to compete on price in its core segments, implying multiple innings of unit economics upside",
                ]
                risks = [
                    "Key-man and product cycle risk: the business model depends on continued innovation cadence that is inherently difficult to forecast beyond 18 months",
                    f"Competitive encroachment is the tail risk the committee must model — the scenario where {risk_sent} materializes could structurally impair the moat and warrants quarterly reassessment",
                ]
            elif eff_dir == "SELL":
                args = [
                    f"The apparent moat is narrowing: {insight1} — pricing power is eroding as substitutes improve and the premium segment faces commoditization pressure",
                    f"Management credibility is at risk — {insight2} is inconsistent with prior guidance cadence, suggesting either deteriorating visibility or a structural demand shift the market has not priced",
                    f"TAM is being systematically over-estimated; penetration curves implied by current consensus require market conditions that break down under competitive pressure",
                ]
                risks = [
                    "The bear thesis could be invalidated by a strategic pivot or product launch that re-establishes pricing power — qualitative shorts require constant monitoring",
                    f"Valuation is a poor short catalyst on its own — fundamentals need to visibly deteriorate, and {risk_sent} may take 2–3 quarters to show up in reported numbers",
                ]
            else:
                args = [
                    f"The business model is fundamentally sound but the near-term growth catalyst is absent — {insight1} is a lagging indicator of moat strength, not a leading one",
                    f"Management execution has been consistent, but at current levels the valuation embeds execution assumptions that leave limited room for operational error",
                    f"I want to see one more quarter confirming {insight2} before recommending incremental exposure — the risk of being early is real given the macro backdrop",
                ]
                risks = [
                    "Catalyst optionality risk: if the growth re-acceleration comes faster than expected, the HOLD position will underperform meaningfully",
                    f"Anchoring risk: HOLD positions tend to drift; if {risk_sent} deteriorates further, the exit decision becomes psychologically harder to execute",
                ]

        elif agent == "risk":
            if eff_dir == "BUY":
                args = [
                    f"Stress-tested the bear case: a 25% revenue miss scenario still leaves the equity supported at current price by {ca} in net cash — the downside is bounded and quantifiable",
                    f"Liquidity profile is strong at {m} gross margins — operating cash generation covers our projected maximum drawdown even in a 1-in-10 year stress event",
                    f"Correlation to the broader market is manageable; beta is below 1 on a trailing 12-month basis, providing genuine portfolio diversification at 1.5–2% weight",
                ]
                risks = [
                    f"Concentration risk: the {rv} revenue base is dependent on a few product lines — a demand shift in the primary segment creates outsized downside beyond the stress test",
                    "Macro correlation spikes in risk-off environments — in a credit event, this name will be sold regardless of fundamentals as institutions de-risk indiscriminately",
                ]
            elif eff_dir == "SELL":
                args = [
                    f"Tail risk is severely underpriced: a 2-sigma adverse move on {insight1} would result in 40–55% drawdown, exceeding the reward case by a factor of 3",
                    f"Liquidity deterioration risk: if {g} growth guidance is cut, the stock could gap 20%+ lower in a single session with no institutional support at that level",
                    f"Risk-adjusted Sharpe on a long position here is below 0.4 — beneath our 0.8 minimum threshold; I cannot recommend adding exposure at these levels",
                ]
                risks = [
                    "Short position carries asymmetric theoretical loss; gamma risk if an unexpected positive catalyst triggers a short squeeze above key technical levels",
                    f"Timing the fundamental deterioration is imprecise — the {risk_sent} may take longer to materialize than the short thesis assumes, creating prolonged mark-to-market pain",
                ]
            else:
                args = [
                    f"Risk/reward is balanced but not compelling: {insight1} is a known, partially-priced risk that limits both the upside and the conviction to add",
                    f"I am comfortable with a 1% portfolio allocation at current levels — the {m} margin base provides some fundamental support — but not more than that",
                    "Recommend maintaining current position size with a hard stop at -15% from cost basis to contain tail risk if the thesis breaks",
                ]
                risks = [
                    "Complacency risk: HOLD positions drift larger as other positions rotate; size discipline is as important as the directional call",
                    f"Stop-loss discipline: if {insight2} deteriorates further, I will immediately recommend a full exit — the HOLD is conditional, not permanent",
                ]

        else:  # devil
            if eff_dir == "BUY":
                args = [
                    f"The committee is anchoring on near-term weakness. {insight1} is a contrarian BUY signal — the market is extrapolating a temporary headwind into a permanent structural impairment that the data does not support",
                    f"Consensus SELL is itself the biggest risk: short interest is crowded, and any positive inflection in {g} will trigger a violent squeeze that punishes the late bears",
                    "The bear case requires multiple adverse outcomes to occur simultaneously and in sequence — the correlation assumptions embedded in that scenario are heroically pessimistic",
                ]
                risks = [
                    "The contrarian BUY only works if the market re-rates the narrative — catalyst identification and timing discipline are the execution risks, not the thesis itself",
                    f"Hidden leverage risk: {insight2} understates operating leverage on the upside, which means the BUY thesis may be more sensitive to macro conditions than I am assuming",
                ]
            elif eff_dir == "SELL":
                args = [
                    f"The committee is committing the classic recency bias: {insight1} looks strong in isolation, but growth is decelerating and every cycle peak has had analysts defending this exact thesis at the top",
                    f"At {pe}, the margin of safety is zero — the BUY case requires best-case outcomes across every dimension simultaneously; that is a bet, not an investment",
                    f"I challenge the committee: model a scenario where margins compress 500bps from {m} — at what point does the investment thesis break? The resulting equity value is 40–60% below current price, and the probability of that path is materially higher than consensus assumes",
                ]
                risks = [
                    "The bearish narrative can remain wrong longer than expected — management has tools to sustain appearances for 2–3 quarters, making the short timing risk real",
                    "Regulatory or strategic intervention — a restructuring, buyout, or product pivot — could invalidate the bear thesis before the market prices the deterioration",
                ]
            else:
                args = [
                    f"HOLD is not a neutral position — it is a decision to accept the current risk/reward. I submit that {insight1} makes this risk/reward materially worse than the committee is acknowledging",
                    "A conviction score of 5.5 signals we have insufficient edge to invest; intellectual honesty demands we either build the conviction to act or admit we lack the information advantage to be here",
                    "HOLD positions create anchoring — the committee will be slow to exit when the thesis breaks because they never fully committed to a directional view",
                ]
                risks = [
                    f"The market will not stay at 'fair value' — if {insight2} inflects, we are either chasing performance on the upside or holding a deteriorating position on the downside",
                    "Opportunity cost is real: every quarter we hold a HOLD, we are allocating risk budget to a position with no alpha expectation",
                ]

        price_target = next(
            (n for n in re.findall(r'\$[\d,]+(?:\.\d+)?(?:[BMK]|\s*(?:billion|million))?', doc) if "$" in n),
            None
        )

        return {
            "direction": eff_dir,
            "conviction": round(conviction, 1),
            "key_arguments": args[:3],
            "key_risks": risks[:2],
            "price_target": price_target,
            "expected_return": (
                "15–25% upside over 12 months" if eff_dir == "BUY"
                else "–15% to –30% over 12 months" if eff_dir == "SELL"
                else "0–5% with high dispersion"
            ),
            "time_horizon": "12 months",
            "causal_factors": [{
                "event": f"Primary driver: {insight1} — {question[:60]}",
                "channel": (
                    "Earnings growth and multiple expansion" if eff_dir == "BUY"
                    else "Earnings compression and de-rating" if eff_dir == "SELL"
                    else "Range-bound pending catalyst confirmation"
                ),
                "direction": "bullish" if eff_dir == "BUY" else "bearish",
                "magnitude": "high" if conviction > 7 else "medium",
                "confidence": round(conviction / 10.0, 2),
                "time_horizon": "medium_term",
            }],
        }

    # ── Round 2 ───────────────────────────────────────────────────────────
    def _build_round2(self, messages):
        question, doc = self._extract_context(messages)
        direction, conviction = self._score_sentiment(doc)
        agent   = self._detect_agent(messages)
        sents   = self._clean_sentences(doc, n=4)
        metrics = self._extract_metrics(doc)

        g  = metrics["growth"]
        m  = metrics["margin"]
        pe = metrics["pe"]
        rv = metrics["revenue"]
        ca = metrics["cash"]
        sh = metrics["share"]
        opp = "SELL" if direction == "BUY" else "BUY"

        _ca  = metrics['cash']    if metrics['cash']    != 'the net cash position' else 'net cash'
        _gr  = metrics['growth']  if metrics['growth']  != 'the YoY growth rate' else ''
        _mg  = metrics['margin']  if metrics['margin']  not in ('gross margin','the key figure') else ''
        _pe  = metrics['pe']      if metrics['pe']      != 'the current multiple' else ''
        topic1 = f"{_gr} revenue growth" if _gr else "the growth trajectory"
        topic2 = f"{_mg} margins"  if _mg else "the margin profile"
        topic3 = f"{_pe} forward multiple" if _pe else "the current valuation"
        s1 = self._short_phrase(sents, 0, "the primary thesis assumption", maxlen=65)
        s2 = self._short_phrase(sents, 1, "the supporting data point", maxlen=65)

        if agent == "quant":
            return {"challenges": {
                "Fundamental Analyst": [
                    f"Your moat narrative is unfalsifiable without numbers behind it. At {pe}, where exactly does pricing power appear in the unit economics? Show me the ROIC spread over cost of capital — qualitative conviction is not a substitute for that calculation.",
                    f"I ran a peer screen of comparable businesses at the {topic3} stage of maturity. In 7 out of 10 analogous cases, the moat narrative held until the quarter it didn't. What's the falsification condition for yours?",
                ],
                "Risk Manager": [
                    f"Your bear scenario uses a 25% revenue miss as the tail. Mean-reversion analysis at {pe} multiples with {g} growth historically implies a 40%+ miss is the correct 2-sigma scenario — your stress test is miscalibrated.",
                    "You're anchoring on historical max-drawdown figures that don't account for a regime shift. In 2008 and 2020, inter-asset correlations converged to 1 and all hedges failed simultaneously — have you sized for that?",
                ],
                "Devil's Advocate": [
                    f"Your contrarian thesis is a narrative without a quantitative trigger. What is the specific factor signal — not the story — that tells us the market's {pe} pricing is wrong? I need a measurable edge, not a heuristic.",
                    f"Contrarian positions with negative factor loading have historically produced negative alpha in trending markets. Give me the regime indicator that tells us the trend is breaking before I can give your {opp} call any weight.",
                ],
            }}
        elif agent == "fundamental":
            return {"challenges": {
                "Quant Analyst": [
                    f"You are over-indexing on {g} as if revenue growth rate is the entire picture. The quant model is systematically blind to the qualitative shift in '{topic1}' — no regression captures a competitive moat transition in a single data point.",
                    f"Momentum signals at {pe} are a lagging indicator of business quality. By the time your screen confirms the thesis, institutional money has already moved — we are analyzing competitive position, not price action.",
                ],
                "Risk Manager": [
                    f"Your tail-risk framework is backward-looking by construction. '{topic1}' represents a structural change in the competitive position — you are building stress scenarios for the last crisis, not the one that's actually forming.",
                    f"The max-drawdown models you're citing assume mean reversion to historical fundamentals. But the {m} margin profile and '{topic2}' suggest the earnings power floor is materially higher than history implies — your downside is overstated.",
                ],
                "Devil's Advocate": [
                    f"The disruption comparison requires that '{topic1}' represents technology substitution. I have examined the analogues cited and they all involve demand destruction, not the demand migration we see here — the structural case is different.",
                    f"Your adversarial thesis requires either management incompetence or deliberate misrepresentation. The {ca} cash position and buyback program are inconsistent with a management team that doesn't believe in their own trajectory.",
                ],
            }}
        elif agent == "risk":
            return {"challenges": {
                "Quant Analyst": [
                    f"A model anchored to {g} momentum has not survived a structural break scenario. In the 2000 and 2008 cycles, every quant signal failed within the same 90-day window as credit conditions tightened — what's your signal in that regime?",
                    f"Your factor loading on {pe} is not orthogonal to macro risk. In a credit event, the momentum factor flips negative with a lag of 30–45 days. Is the position sized to absorb that correlation breakdown, or are we relying on historical independence that no longer holds?",
                ],
                "Fundamental Analyst": [
                    f"The moat described in '{topic1}' is also a source of concentration risk. A genuine competitive advantage in a narrow segment creates catastrophic downside precisely when that advantage is challenged — have you stress-tested the scenario where the moat is breached in a single product cycle?",
                    f"The {_ca} cash reserve and buyback program are not a risk management tool — they are a capital allocation decision that can be reversed in a quarter. I need to see what the equity value looks like if {g} growth halves before I can endorse the base case.",
                ],
                "Devil's Advocate": [
                    f"Your contrarian {opp} position requires you to be right on timing within a 12-month window. What is the maximum drawdown you will accept on this thesis before acknowledging the timing is wrong? I have not seen that number from you.",
                    "An adversarial position creates its own tail risk — if consensus is right for one more quarter, the loss profile exceeds the reward of being right by 18 months. That is not a trade I can endorse without explicit risk parameters.",
                ],
            }}
        else:  # devil
            return {"challenges": {
                "Quant Analyst": [
                    f"Your entire quantitative framework assumes {g} mean-reverts to trend. But '{topic1}' could represent a structural break — not a cyclical deviation — and your model has no mechanism to distinguish between the two. The backtest is looking at a sample that no longer describes the current regime.",
                    f"The momentum signal you're citing has worked in a low-rate, expanding-multiple environment. That regime ended. Show me the out-of-sample performance in a rising-rate, multiple-compression cycle — I suspect it does not survive the test.",
                ],
                "Fundamental Analyst": [
                    f"You cite the moat as durable, but '{topic2}' is structurally identical to what analysts said about Kodak before digital, Blockbuster before streaming, Nokia before the smartphone. At what point does the moat thesis become the trap? What is the specific trigger that would change your view?",
                    f"The TAM expansion story at {pe} forward earnings requires 5 consecutive years of above-consensus execution with no meaningful competitive response. What is your honest probability estimate for that scenario? I believe it is being systematically overstated.",
                ],
                "Risk Manager": [
                    f"Your bear scenario is simultaneously too conservative to be a useful hedge and too mild to capture the actual tail. You have correctly identified the known risks — but '{topic1}' implies an unknown risk category that does not appear anywhere in your stress framework.",
                    f"A 1–2% position cap is not risk management — it is hedging against being wrong without the intellectual commitment to act on a conviction. If the risk is real enough to limit size, it should be real enough to short. If it isn't, own it fully. This position is analytically incoherent.",
                ],
            }}

    # ── Round 3 ───────────────────────────────────────────────────────────
    def _build_round3(self, messages):
        question, doc = self._extract_context(messages)
        direction, conviction = self._score_sentiment(doc)
        agent   = self._detect_agent(messages)
        sents   = self._clean_sentences(doc, n=4)
        metrics = self._extract_metrics(doc)

        g  = metrics["growth"]
        m  = metrics["margin"]
        pe = metrics["pe"]
        ca = metrics["cash"]

        _ca  = metrics['cash'] if metrics['cash'] != 'the net cash position' else 'net cash'
        _pe  = metrics['pe']   if metrics['pe']   != 'the current multiple' else ''
        _gr  = metrics['growth'] if metrics['growth'] != 'the YoY growth rate' else ''
        topic1 = f"{_gr} revenue growth" if _gr else "the growth trajectory"
        topic2 = f"{_pe} forward multiple" if _pe else "the current valuation"
        s1 = self._short_phrase(sents, 0, "the primary thesis driver", maxlen=80)
        s2 = self._short_phrase(sents, 1, "the supporting evidence", maxlen=80)

        if agent == "devil":
            eff_dir = "SELL" if direction == "BUY" else "BUY" if direction == "SELL" else "SELL"
            conviction = max(3.5, conviction - 1.5)
        else:
            eff_dir = direction
            if agent == "risk":
                conviction = max(2.0, conviction - 1.5)

        updated_conv = round(max(2.5, conviction - 0.5), 1)

        if agent == "quant":
            defenses = [
                f"The stress-test calibration challenge is fair, but the conclusion is wrong. I have rerun the bear scenario at a 40% revenue miss — the equity still clears intrinsic value by 10–12% at that level. The quantitative edge holds even in the challenged scenario.",
                f"On the falsification point: '{topic1}' is not a narrative in my model — it maps to a measurable factor with a 0.68 information coefficient over 24-month horizons. That's not a story, it's a tested signal. I'm happy to share the full factor decay curve.",
            ]
            concessions = [
                f"I concede that the correlation breakdown scenario in a macro shock is underweighted in the base case. I will reduce the recommended position size by 20% to create headroom for that regime risk — the thesis remains intact, but the sizing needs to be more conservative.",
            ]
        elif agent == "fundamental":
            defenses = [
                f"The disruption analogues cited in Round 2 are not structurally applicable. Kodak and Blockbuster faced technology substitution of their core demand. '{topic1}' represents a demand migration within an expanding category — the qualitative dynamics are different in a way that matters for the thesis.",
                f"On management track record: the {_ca} cash position and consistent buyback execution is not survivorship bias — it has been sustained across two different macro regimes and reflects a repeatable capital allocation philosophy, not a lucky run.",
            ]
            concessions = [
                f"I concede that the TAM expansion timeline is more uncertain than my base case assumed. I will revise the 12-month price target to reflect a more conservative penetration curve and reduce my conviction by 0.5, but the direction remains unchanged.",
            ]
        elif agent == "risk":
            defenses = [
                f"My max-drawdown scenario is not backward-looking — it is specifically calibrated to the liquidity profile of this name, which has historically widened 4x in bid-ask spread during stress periods. The {m} gross margin floor provides a genuine cushion that the generic bear scenario ignores.",
                f"On the moat concentration critique: I agree the competitive advantage creates idiosyncratic risk. But concentration in a genuine moat is categorically different from single-factor exposure. My position sizing already reflects a stress-adjusted weight — this is not an oversight.",
            ]
            concessions = [
                f"I concede that my tail scenario probability was anchored on historical correlation structures that may understate the company's fundamental resilience. I will revise the extreme bear case probability from 20% to 15%, which modestly improves the risk-adjusted return.",
            ]
        else:  # devil
            defenses = [
                f"The committee has not substantively addressed the regime-change argument. '{topic1}' held as a thesis driver in the prior environment. The burden of proof is on the committee to demonstrate it still holds — not on me to prove the negative.",
                f"On timing: I don't need to be precise about timing — I need the committee to quantify the assumption fragility. The {pe} multiple embeds a specific set of outcomes; if any of those outcomes disappoint, the downside is non-linear. That acknowledgment needs to be in the position sizing.",
            ]
            concessions = [
                f"I concede that my adversarial position overstates the probability of a sharp near-term reversal. I'll moderate my conviction from maximum to 6.5/10, acknowledging that the consensus thesis has legitimate support on a 6-month horizon — my disagreement is primarily with the 18-month view.",
            ]

        return {
            "defenses": defenses,
            "concessions": concessions,
            "updated_conviction": updated_conv,
            "updated_direction": eff_dir,
        }

    # ── Round 4 ───────────────────────────────────────────────────────────
    def _build_round4(self, messages):
        question, transcript = self._extract_context(messages)
        direction, conviction = self._score_sentiment(transcript)

        label = "high" if conviction > 7.5 else "moderate" if conviction > 5 else "low"

        if direction == "BUY":
            thesis = (
                f"After four rounds of structured IC debate, the committee reaches a {label}-conviction BUY. "
                f"The quantitative, fundamental, and risk analyses converge: the submitted research supports initiating or adding to a long position with a 12-month investment horizon. "
                f"The Devil's Advocate raised legitimate regime-change concerns that the committee has incorporated into position sizing rather than thesis direction."
            )
            risks = [
                "Guidance miss risk: any deceleration in the primary revenue driver triggers multiple compression that is not reflected in the current BUY case — the thesis has zero tolerance for a growth cut",
                "Macro de-risking: in a broad risk-off event, this position will underperform regardless of idiosyncratic thesis quality as institutional selling overrides fundamentals",
                "Execution concentration: the BUY thesis is dependent on continued operational delivery across product, margin, and capital allocation simultaneously — a stumble in any dimension pressures the investment case",
            ]
            sizing = "2–3% portfolio weight. Scale in over 3–4 weeks in equal tranches to manage entry timing risk. Hard stop at –12% from average cost basis."
        elif direction == "SELL":
            thesis = (
                f"After four rounds of structured IC debate, the committee reaches a {label}-conviction SELL. "
                f"Quantitative, fundamental, and risk analyses converge on material deterioration signals in the submitted document. "
                f"The committee acknowledges the Devil's Advocate correctly identified timing as the primary execution risk on the short thesis."
            )
            risks = [
                "Short squeeze risk: elevated short interest makes any positive catalyst — even a minor one — capable of triggering a violent covering rally that punishes conviction before the thesis plays out",
                "Timing risk: fundamental deterioration theses routinely take 12–18 months to fully materialize; the committee must size for the interim mark-to-market pain, not just the terminal value",
                "Structural improvement risk: a management pivot, cost restructuring, or strategic transaction could partially or fully invalidate the bear thesis before it is priced in",
            ]
            sizing = "1–2% short position. Cap strictly — asymmetric loss profile demands size discipline. Cover 50% if the position moves against the thesis by 10%; full cover at 15%."
        else:
            thesis = (
                f"After four rounds of structured IC debate, the committee does not achieve directional conviction. "
                f"The submitted research contains genuinely mixed signals that the quantitative, fundamental, and risk frameworks interpret differently with legitimate analytical basis on both sides. "
                f"A HOLD recommendation reflects capital allocation discipline — we do not deploy risk budget without a clear edge."
            )
            risks = [
                "Opportunity cost risk: a flat position while the stock moves materially in either direction is a real economic loss — the HOLD is not free",
                "Narrative shift risk: a single catalyst could rapidly resolve the ambiguity and leave a neutral position badly positioned; establish the re-entry conditions now",
                "Anchoring risk: re-engaging after a sharp move will feel psychologically expensive — define the entry triggers in advance and commit to them in writing",
            ]
            sizing = "No new position. Maintain existing exposure at no more than 1% of portfolio. Mandatory reassessment at next earnings print with pre-specified decision criteria."

        if direction == "BUY":
            dist = {"BUY": round(min(0.70, 0.45 + (conviction - 5) * 0.05), 2), "HOLD": 0.25, "SELL": 0.10}
        elif direction == "SELL":
            dist = {"BUY": 0.10, "HOLD": 0.25, "SELL": round(min(0.70, 0.45 + (conviction - 5) * 0.05), 2)}
        else:
            dist = {"BUY": 0.30, "HOLD": 0.45, "SELL": 0.25}

        total = sum(dist.values())
        dist  = {k: round(v / total, 2) for k, v in dist.items()}

        opp_dir = "SELL" if direction == "BUY" else "BUY" if direction == "SELL" else "directional"
        return {
            "recommendation": direction,
            "confidence_distribution": dist,
            "consensus_conviction": round(conviction - 0.3, 1),
            "key_thesis": thesis,
            "primary_risks": risks,
            "position_sizing_guidance": sizing,
            "dissenting_views": [
                f"Devil's Advocate maintains the {opp_dir} case is underweighted. The committee should formally stress-test the {direction} recommendation against a scenario where the primary thesis driver reverses within two quarters — and document the position exit criteria before that scenario materialises."
            ],
            "debate_quality_score": round(7.5 + (conviction % 1.5) * 0.5, 1),
        }

    # ── Entry points ──────────────────────────────────────────────────────
    def _generate(self, messages):
        r = self._detect_round(messages)
        if r == 1:   return self._build_round1(messages)
        elif r == 2: return self._build_round2(messages)
        elif r == 3: return self._build_round3(messages)
        else:        return self._build_round4(messages)

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
