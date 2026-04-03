<div align="center">

# BTRate
### Behind The Rate

**Multi-Agent Investment Committee Debate Engine**

*Upload a research document. Get a structured IC-quality debate with a calibrated buy / sell / hold verdict.*

---

[![Status](https://img.shields.io/badge/Status-Private%20Research%20Tool-black?style=flat-square)](https://github.com/JackieInv2/MiroFish)
[![Stack](https://img.shields.io/badge/Stack-Vue%203%20%2B%20Flask%20%2B%20Python-FF4500?style=flat-square)](https://github.com/JackieInv2/MiroFish)
[![Models](https://img.shields.io/badge/LLM-GPT--4o%20%7C%20Claude%20%7C%20Gemini-555?style=flat-square)](https://github.com/JackieInv2/MiroFish)

</div>

---

## What Is BTRate?

BTRate is a private investment research tool built for equity PMs and analysts. It runs an **IC-style structured debate** across five specialized AI agents — each with a distinct investment perspective — and synthesizes their arguments into a calibrated consensus recommendation.

The thesis: real investment committees are more rigorous than any single analyst. BTRate replicates that process at machine speed.

**Input:** A research PDF (earnings report, 10-K, analyst note, news article) + an investment question.

**Output:** A structured 4-round debate with a final `BUY / SELL / HOLD` recommendation, calibrated conviction score, confidence distribution, position sizing guidance, and identified dissenting views.

---

## The Five Agents

| Agent | Lens | Temperature |
|---|---|---|
| **Quant Analyst** | Factor exposure, valuation multiples, technical signals, causal factor chains | 0.4 |
| **Fundamental Analyst** | Business model quality, competitive moat, earnings power, management | 0.6 |
| **Risk Manager** | Tail risk, drawdown scenarios, correlation to macro, concentration limits | 0.3 |
| **Devil's Advocate** | Argues against consensus, surfaces the bear case, finds logical flaws | 0.8 |
| **CIO / PM** | Synthesizes all views, resolves disagreements, issues final verdict | 0.5 |

Each agent independently reads the uploaded document and produces structured reasoning — not free-form text.

---

## Debate Structure

### Round 1 — Initial Thesis
All four analyst agents read the document in parallel and independently produce:
- Direction (`BUY` / `SELL` / `HOLD`) with conviction score (0–10)
- Key arguments and key risks
- Causal factor chains (event → channel → market impact)
- Price target, expected return, time horizon

### Round 2 — Cross-Examination
Each agent challenges the specific arguments of the other three. Challenges are targeted and logged by agent name.

### Round 3 — Rebuttal & Defense
Agents defend or concede specific points. Updated conviction scores are recorded. Conviction drift between Round 1 and Round 3 is tracked.

### Round 4 — CIO Synthesis
The CIO agent reads all prior rounds and issues:
- Final `recommendation` with `consensus_conviction`
- `confidence_distribution` across BUY / HOLD / SELL (sums to 1.0)
- Platt-calibrated probability score
- `primary_risks`, `dissenting_views`, `position_sizing_guidance`
- `debate_quality_score` (0–10)

---

## Calibration

Raw conviction scores are passed through **Platt scaling** before the final output:

```
p_cal = p^α / (p^α + (1-p)^α)     where α = √3 ≈ 1.73
```

This compresses overconfident raw scores toward a calibrated probability that better reflects historical hit rates in multi-agent ensemble systems.

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | Vue 3 + Vite + CSS (no UI framework) |
| Backend | Python / Flask |
| Agent Orchestration | Custom `InvestmentDebateService` |
| LLM Support | OpenAI (GPT-4o), Anthropic (Claude), Google (Gemini), MockProvider |
| Data Models | Pydantic v2 |
| Fonts | JetBrains Mono, Space Grotesk |

---

## Setup

### Prerequisites

- Node.js 18+
- Python ≥ 3.11, ≤ 3.12

### 1. Clone & Install

```bash
git clone https://github.com/JackieInv2/MiroFish.git
cd MiroFish
npm run setup:all
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env`:

```env
# LLM Provider — pick one or configure per-agent
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Google Gemini free tier (OpenAI-compatible endpoint)
# OPENAI_API_KEY=your_gemini_key
# LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
# LLM_MODEL_NAME=gemini-2.5-flash

# Set to true to run without any API key (mock responses)
DEMO_MODE=false
```

### 3. Run

```bash
npm run dev
```

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:5001`

---

## API Reference

```
POST /api/debate/start              Upload PDF or paste text + investment question
GET  /api/debate/{id}/status        Polling endpoint — returns status + progress %
GET  /api/debate/{id}/result        Full structured result (all rounds + final rec)
GET  /api/debate/{id}/rounds/{n}    Individual round result (1–4)
GET  /api/debate/list               List all debates in session
```

---

## Running Without an API Key

Set `DEMO_MODE=true` in `.env`. The `MockProvider` returns realistic structured responses for all four rounds. Useful for testing the UI and API contract without incurring LLM costs.

---

## Project Structure

```
MiroFish/
├── backend/
│   └── app/
│       ├── api/debate.py              — 5 REST endpoints
│       ├── models/debate.py           — Pydantic models (InvestmentFactor, etc.)
│       ├── services/investment_debate.py  — 4-round debate orchestrator
│       └── utils/llm_client.py        — Multi-model LLM client
├── frontend/
│   └── src/
│       ├── views/DebateView.vue       — Main UI: mind-map + round cards
│       ├── views/Home.vue             — Landing page
│       └── api/debate.js             — API client
└── .env                              — API keys + model config
```

---

<div align="center">
<sub>BTRate — Behind The Rate — Private Research Tool</sub>
</div>
