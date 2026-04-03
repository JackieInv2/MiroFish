<template>
  <div class="debate-view">
    <!-- Navigation Bar -->
    <nav class="navbar">
      <div class="nav-brand" @click="$router.push('/')">BTRATE</div>
      <div class="nav-center">Investment Debate Engine</div>
      <div class="nav-right">
        <span class="status-pill" :class="statusClass">
          <span class="status-dot"></span>
          {{ statusText }}
        </span>
      </div>
    </nav>

    <div class="main-content">
      <!-- ===================== START PANEL ===================== -->
      <section v-if="!debateId" class="start-section">
        <div class="start-hero">
          <div class="tag-row">
            <span class="orange-tag">IC DEBATE</span>
            <span class="version-text">/ Multi-Agent Consensus</span>
          </div>
          <h1 class="start-title">
            Upload Research<br>
            <span class="gradient-text">Start the Debate</span>
          </h1>
          <p class="start-desc">
            Five AI agents — <span class="hl-bold">Quant Analyst</span>, <span class="hl-bold">Fundamental Analyst</span>,
            <span class="hl-bold">Risk Manager</span>, <span class="hl-bold">Devil's Advocate</span>, and
            <span class="hl-bold">CIO</span> — will conduct a structured IC-style debate on your investment thesis.
          </p>
        </div>

        <div class="start-form">
          <div class="console-box">
            <div class="console-section">
              <div class="console-header">
                <span class="console-label">01 / Investment Question</span>
              </div>
              <input
                v-model="question"
                type="text"
                class="code-input single-line"
                placeholder='e.g. "Should we buy AAPL at current levels given Q1 earnings?"'
              />
            </div>

            <div class="console-divider"><span>Research Input</span></div>

            <div class="console-section">
              <div class="console-header">
                <span class="console-label">02 / Research Document</span>
                <span class="console-meta">PDF, TXT, MD</span>
              </div>
              <div
                class="upload-zone"
                :class="{ 'drag-over': dragOver, 'has-file': !!file }"
                @dragover.prevent="dragOver = true"
                @dragleave.prevent="dragOver = false"
                @drop.prevent="onDrop"
                @click="$refs.fileInput.click()"
              >
                <input ref="fileInput" type="file" accept=".pdf,.txt,.md" hidden @change="onFileSelect" />
                <div v-if="!file" class="upload-placeholder">
                  <div class="upload-icon-box">&#8679;</div>
                  <div class="upload-title">Drop file here or click to browse</div>
                </div>
                <div v-else class="file-display">
                  <span class="file-icon">&#128196;</span>
                  <span class="file-name">{{ file.name }}</span>
                  <button class="remove-btn" @click.stop="file = null">&times;</button>
                </div>
              </div>
            </div>

            <div v-if="!file" class="console-section">
              <div class="console-header">
                <span class="console-label">&gt;_ Or paste text</span>
              </div>
              <textarea
                v-model="pastedText"
                class="code-input multi-line"
                rows="5"
                placeholder="Paste earnings data, research notes, or financial text here..."
              ></textarea>
            </div>

            <div class="console-section btn-section">
              <button
                class="start-engine-btn"
                :disabled="!canStart || loading"
                @click="startNewDebate"
              >
                <span v-if="!loading">Start Debate</span>
                <span v-else>Initializing...</span>
                <span class="btn-arrow">&rarr;</span>
              </button>
            </div>
          </div>
          <p v-if="error" class="error-msg">{{ error }}</p>
        </div>
      </section>

      <!-- ===================== ACTIVE DEBATE ===================== -->
      <section v-else class="debate-section">
        <!-- Progress Bar -->
        <div class="progress-container">
          <div class="progress-track">
            <div class="progress-fill" :style="{ width: progress + '%' }"></div>
          </div>
          <span class="progress-text">{{ progress }}% &mdash; {{ statusText }}</span>
        </div>

        <!-- ============ MIND MAP ============ -->
        <div class="mindmap-wrapper">
          <div class="mindmap">
            <!-- SVG Connection Lines -->
            <svg class="mindmap-svg" viewBox="0 0 900 380" preserveAspectRatio="xMidYMid meet">
              <!-- Document to Agents -->
              <path d="M450,60 L175,155" class="conn-line" :class="lineClass(1)" />
              <path d="M450,60 L350,155" class="conn-line" :class="lineClass(1)" />
              <path d="M450,60 L550,155" class="conn-line" :class="lineClass(1)" />
              <path d="M450,60 L725,155" class="conn-line" :class="lineClass(1)" />
              <!-- Cross-examination lines between agents -->
              <path d="M225,240 L310,240" class="conn-line cross" :class="lineClass(2)" />
              <path d="M395,240 L505,240" class="conn-line cross" :class="lineClass(2)" />
              <path d="M595,240 L680,240" class="conn-line cross" :class="lineClass(2)" />
              <!-- Agents to CIO -->
              <path d="M175,265 L450,325" class="conn-line" :class="lineClass(4)" />
              <path d="M350,265 L450,325" class="conn-line" :class="lineClass(4)" />
              <path d="M550,265 L450,325" class="conn-line" :class="lineClass(4)" />
              <path d="M725,265 L450,325" class="conn-line" :class="lineClass(4)" />
            </svg>

            <!-- Document Node -->
            <div class="mm-node document-node" :class="{ visible: true }">
              <div class="mm-icon">&#128196;</div>
              <div class="mm-label">Document Input</div>
            </div>

            <!-- Agent Nodes -->
            <div class="mm-node agent-node quant" :class="nodeState('quant_analyst')">
              <div class="mm-icon-letter">Q</div>
              <div class="mm-label">Quant Analyst</div>
              <div class="mm-state">{{ nodeStateText('quant_analyst') }}</div>
            </div>

            <div class="mm-node agent-node fundamental" :class="nodeState('fundamental_analyst')">
              <div class="mm-icon-letter">F</div>
              <div class="mm-label">Fundamental</div>
              <div class="mm-state">{{ nodeStateText('fundamental_analyst') }}</div>
            </div>

            <div class="mm-node agent-node risk" :class="nodeState('risk_manager')">
              <div class="mm-icon-letter">R</div>
              <div class="mm-label">Risk Manager</div>
              <div class="mm-state">{{ nodeStateText('risk_manager') }}</div>
            </div>

            <div class="mm-node agent-node devil" :class="nodeState('devil_advocate')">
              <div class="mm-icon-letter">D</div>
              <div class="mm-label">Devil's Advocate</div>
              <div class="mm-state">{{ nodeStateText('devil_advocate') }}</div>
            </div>

            <div class="mm-node cio-node" :class="{ visible: activeRound >= 4, thinking: activeRound === 4 && status !== 'completed' }">
              <div class="mm-icon-letter cio">C</div>
              <div class="mm-label">CIO / PM</div>
              <div class="mm-sublabel">Final Verdict</div>
            </div>
          </div>
        </div>

        <!-- ============ ROUND CARDS ============ -->
        <div class="rounds-section">
          <!-- Round 1: Initial Thesis -->
          <div v-if="rounds.length >= 1" class="round-card fade-in">
            <div class="round-header">
              <span class="round-badge">01</span>
              <span class="round-title">Initial Thesis</span>
            </div>
            <div class="agents-grid">
              <div
                v-for="resp in (rounds[0]?.responses || [])"
                :key="resp.agent_role"
                class="agent-card"
                :class="'border-' + agentColor(resp.agent_role)"
              >
                <div class="agent-top">
                  <span class="agent-letter" :class="'bg-' + agentColor(resp.agent_role)">{{ agentIcon(resp.agent_role) }}</span>
                  <span class="agent-name">{{ resp.agent_name }}</span>
                  <span class="agent-model">{{ resp.model_used }}</span>
                </div>
                <template v-if="resp.thesis">
                  <div class="direction-badge" :class="dirClass(resp.thesis.direction)">
                    {{ resp.thesis.direction }}
                  </div>
                  <div class="conviction-row">
                    <span class="conviction-label">Conviction</span>
                    <span class="conviction-val">{{ resp.thesis.conviction }}/10</span>
                    <div class="conviction-bar">
                      <div class="conviction-fill" :style="{ width: (resp.thesis.conviction * 10) + '%' }"></div>
                    </div>
                  </div>
                  <div v-if="resp.thesis.key_arguments?.length" class="detail-block">
                    <div class="detail-title">Key Arguments</div>
                    <ul><li v-for="(a, i) in resp.thesis.key_arguments" :key="i">{{ a }}</li></ul>
                  </div>
                  <div v-if="resp.thesis.key_risks?.length" class="detail-block risks">
                    <div class="detail-title">Key Risks</div>
                    <ul><li v-for="(r, i) in resp.thesis.key_risks" :key="i">{{ r }}</li></ul>
                  </div>
                  <div v-if="resp.thesis.causal_factors?.length" class="factors-row">
                    <span
                      v-for="(f, i) in resp.thesis.causal_factors.slice(0, 4)"
                      :key="i"
                      class="factor-chip"
                    >{{ f.event || f.channel }}</span>
                  </div>
                </template>
                <div v-else class="raw-content">{{ resp.content }}</div>
              </div>
            </div>
          </div>

          <!-- Round 2: Cross-Examination -->
          <div v-if="rounds.length >= 2" class="round-card fade-in">
            <div class="round-header">
              <span class="round-badge">02</span>
              <span class="round-title">Cross-Examination</span>
            </div>
            <div class="agents-grid">
              <div
                v-for="resp in (rounds[1]?.responses || [])"
                :key="resp.agent_role"
                class="agent-card"
                :class="'border-' + agentColor(resp.agent_role)"
              >
                <div class="agent-top">
                  <span class="agent-letter" :class="'bg-' + agentColor(resp.agent_role)">{{ agentIcon(resp.agent_role) }}</span>
                  <span class="agent-name">{{ resp.agent_name }}</span>
                </div>
                <template v-if="resp.cross_examination">
                  <div
                    v-for="(challenges, target) in resp.cross_examination.challenges"
                    :key="target"
                    class="challenge-block"
                  >
                    <div class="challenge-target">Challenging {{ target }}:</div>
                    <ul><li v-for="(c, i) in challenges" :key="i">{{ c }}</li></ul>
                  </div>
                </template>
                <div v-else class="raw-content">{{ resp.content }}</div>
              </div>
            </div>
          </div>

          <!-- Round 3: Rebuttal -->
          <div v-if="rounds.length >= 3" class="round-card fade-in">
            <div class="round-header">
              <span class="round-badge">03</span>
              <span class="round-title">Rebuttal &amp; Revised Conviction</span>
            </div>
            <div class="agents-grid">
              <div
                v-for="resp in (rounds[2]?.responses || [])"
                :key="resp.agent_role"
                class="agent-card"
                :class="'border-' + agentColor(resp.agent_role)"
              >
                <div class="agent-top">
                  <span class="agent-letter" :class="'bg-' + agentColor(resp.agent_role)">{{ agentIcon(resp.agent_role) }}</span>
                  <span class="agent-name">{{ resp.agent_name }}</span>
                </div>
                <template v-if="resp.rebuttal">
                  <div v-if="resp.rebuttal.updated_direction" class="direction-badge" :class="dirClass(resp.rebuttal.updated_direction)">
                    {{ resp.rebuttal.updated_direction }}
                  </div>
                  <div class="conviction-row">
                    <span class="conviction-label">Updated Conviction</span>
                    <span class="conviction-val">{{ resp.rebuttal.updated_conviction }}/10</span>
                    <div class="conviction-bar">
                      <div class="conviction-fill" :style="{ width: (resp.rebuttal.updated_conviction * 10) + '%' }"></div>
                    </div>
                  </div>
                  <div v-if="resp.rebuttal.defenses?.length" class="detail-block">
                    <div class="detail-title">Defenses</div>
                    <ul><li v-for="(d, i) in resp.rebuttal.defenses" :key="i">{{ d }}</li></ul>
                  </div>
                  <div v-if="resp.rebuttal.concessions?.length" class="detail-block concessions">
                    <div class="detail-title">Concessions</div>
                    <ul><li v-for="(c, i) in resp.rebuttal.concessions" :key="i">{{ c }}</li></ul>
                  </div>
                </template>
                <div v-else class="raw-content">{{ resp.content }}</div>
              </div>
            </div>
          </div>

          <!-- Round 4: CIO Synthesis -->
          <div v-if="rounds.length >= 4" class="round-card cio-round fade-in">
            <div class="round-header cio-header">
              <span class="round-badge cio-badge">04</span>
              <span class="round-title">CIO Synthesis &mdash; Final Verdict</span>
            </div>
            <template v-if="cioData">
              <div class="cio-body">
                <div class="cio-rec-badge" :class="dirClass(cioData.recommendation)">
                  {{ cioData.recommendation }}
                </div>
                <div class="cio-conviction">
                  Consensus Conviction: <strong>{{ cioData.consensus_conviction }}/10</strong>
                </div>
                <div class="cio-thesis">{{ cioData.key_thesis }}</div>

                <!-- Confidence Distribution Bar -->
                <div v-if="cioData.confidence_distribution" class="conf-bar-wrapper">
                  <div class="conf-bar-label">Confidence Distribution</div>
                  <div class="conf-bar">
                    <div
                      v-for="(pct, dir) in cioData.confidence_distribution"
                      :key="dir"
                      class="conf-segment"
                      :class="dir.toLowerCase()"
                      :style="{ width: (pct * 100) + '%' }"
                    >
                      <span v-if="pct > 0.08" class="conf-seg-text">{{ dir }} {{ (pct * 100).toFixed(0) }}%</span>
                    </div>
                  </div>
                </div>

                <div class="cio-columns">
                  <div v-if="cioData.primary_risks?.length" class="cio-col">
                    <div class="detail-title">Primary Risks</div>
                    <ul><li v-for="(r, i) in cioData.primary_risks" :key="i">{{ r }}</li></ul>
                  </div>
                  <div v-if="cioData.dissenting_views?.length" class="cio-col dissent">
                    <div class="detail-title">Dissenting Views</div>
                    <ul><li v-for="(d, i) in cioData.dissenting_views" :key="i">{{ d }}</li></ul>
                  </div>
                </div>

                <div v-if="cioData.position_sizing_guidance" class="cio-sizing">
                  <span class="sizing-label">Position Sizing:</span> {{ cioData.position_sizing_guidance }}
                </div>
              </div>
            </template>
          </div>
        </div>

        <!-- ============ FINAL BANNER ============ -->
        <div v-if="finalRecommendation && status === 'completed'" class="final-banner" :class="dirClass(finalRecommendation.recommendation)">
          <div class="final-rec">{{ finalRecommendation.recommendation }}</div>
          <div class="final-thesis">{{ finalRecommendation.key_thesis }}</div>
          <div v-if="consensusScore" class="final-calibration">
            Raw Conviction: {{ consensusScore.raw_score }}/10
            <span class="cal-sep">&bull;</span>
            Platt-Calibrated: {{ (consensusScore.calibrated_score * 100).toFixed(1) }}%
          </div>
          <div v-if="cioData?.debate_quality_score" class="final-quality">
            Debate Quality: {{ cioData.debate_quality_score.toFixed(1) }}/10
          </div>
          <button class="new-debate-btn" @click="resetDebate">New Debate</button>
        </div>

        <!-- Error Banner -->
        <div v-if="debateError" class="error-banner">
          <strong>Debate Failed:</strong> {{ debateError }}
          <button class="new-debate-btn small" @click="resetDebate">Try Again</button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onUnmounted, watch } from 'vue'
import { startDebate, getDebateStatus, getDebateResult } from '../api/debate'

const question = ref('')
const file = ref(null)
const pastedText = ref('')
const dragOver = ref(false)
const loading = ref(false)
const error = ref('')
const debateId = ref(null)
const progress = ref(0)
const status = ref('')
const rounds = ref([])
const finalRecommendation = ref(null)
const consensusScore = ref(null)
const debateError = ref(null)

let pollTimer = null

const canStart = computed(() => question.value.trim() && (file.value || pastedText.value.trim()))

const activeRound = computed(() => {
  const m = { round_1: 1, round_2: 2, round_3: 3, round_4: 4, completed: 4 }
  return m[status.value] || 0
})

const cioData = computed(() => {
  if (rounds.value.length < 4) return null
  const r4 = rounds.value[3]
  if (!r4?.responses?.length) return null
  return r4.responses[0]?.cio_synthesis || null
})

const statusText = computed(() => {
  if (!debateId.value) return 'Ready'
  const map = {
    pending: 'Pending',
    running: 'Running',
    round_1: 'Round 1: Initial Thesis',
    round_2: 'Round 2: Cross-Examination',
    round_3: 'Round 3: Rebuttal',
    round_4: 'Round 4: CIO Synthesis',
    completed: 'Completed',
    failed: 'Failed',
  }
  return map[status.value] || status.value
})

const statusClass = computed(() => {
  if (status.value === 'completed') return 'success'
  if (status.value === 'failed') return 'error'
  if (debateId.value) return 'running'
  return 'idle'
})

function agentIcon(role) {
  const icons = { quant_analyst: 'Q', fundamental_analyst: 'F', risk_manager: 'R', devil_advocate: 'D', cio: 'C' }
  return icons[role] || '?'
}

function agentColor(role) {
  const colors = { quant_analyst: 'blue', fundamental_analyst: 'purple', risk_manager: 'red', devil_advocate: 'deeporange', cio: 'gold' }
  return colors[role] || 'gray'
}

function dirClass(dir) {
  if (!dir) return ''
  const d = dir.toLowerCase()
  if (d === 'buy') return 'dir-buy'
  if (d === 'sell') return 'dir-sell'
  return 'dir-hold'
}

function lineClass(minRound) {
  const r = activeRound.value
  const isComplete = status.value === 'completed'
  if (r < minRound) return ''
  if (isComplete) return 'done'
  return 'active'
}

function nodeState(role) {
  const r = activeRound.value
  if (r === 0) return ''
  if (r >= 1) {
    const isThinking = (r <= 3 && status.value !== 'completed')
    return { visible: true, thinking: isThinking && r === 1 }
  }
  return ''
}

function nodeStateText(role) {
  const r = activeRound.value
  if (r === 0) return 'Waiting'
  if (status.value === 'completed') return 'Done'
  if (r === 1) return 'Analyzing...'
  if (r === 2) return 'Debating...'
  if (r === 3) return 'Rebutting...'
  if (r === 4) return 'Reviewing...'
  return ''
}

function onFileSelect(e) {
  file.value = e.target.files[0] || null
}

function onDrop(e) {
  dragOver.value = false
  const f = e.dataTransfer.files[0]
  if (f) file.value = f
}

function resetDebate() {
  debateId.value = null
  progress.value = 0
  status.value = ''
  rounds.value = []
  finalRecommendation.value = null
  consensusScore.value = null
  debateError.value = null
  question.value = ''
  file.value = null
  pastedText.value = ''
  error.value = ''
}

async function startNewDebate() {
  loading.value = true
  error.value = ''
  try {
    let payload
    if (file.value) {
      payload = new FormData()
      payload.append('file', file.value)
      payload.append('question', question.value)
    } else {
      payload = { question: question.value, text: pastedText.value }
    }
    const res = await startDebate(payload)
    debateId.value = res.debate_id
    status.value = 'running'
    startPolling()
  } catch (e) {
    error.value = e.message || 'Failed to start debate'
  } finally {
    loading.value = false
  }
}

function startPolling() {
  pollTimer = setInterval(async () => {
    try {
      const st = await getDebateStatus(debateId.value)
      status.value = st.status
      progress.value = st.progress

      const res = await getDebateResult(debateId.value)
      if (res.data) {
        rounds.value = res.data.rounds || []
        finalRecommendation.value = res.data.final_recommendation
        consensusScore.value = res.data.consensus_score
        debateError.value = res.data.error
      }

      if (st.status === 'completed' || st.status === 'failed') {
        clearInterval(pollTimer)
        pollTimer = null
      }
    } catch (e) {
      console.error('Polling error:', e)
    }
  }, 2000)
}

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
/* =================== DESIGN TOKENS =================== */
:root {
  --black: #000000;
  --white: #FFFFFF;
  --orange: #FF4500;
  --bg: #FFFFFF;
  --bg-alt: #FAFAFA;
  --gray-text: #666666;
  --gray-light: #F5F5F5;
  --border: #E5E5E5;
  --font-mono: 'JetBrains Mono', monospace;
  --font-sans: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

* { box-sizing: border-box; }

.debate-view {
  min-height: 100vh;
  background: var(--bg);
  font-family: var(--font-sans);
  color: var(--black);
}

/* =================== NAVBAR =================== */
.navbar {
  height: 60px;
  background: var(--black);
  color: var(--white);
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 40px;
}

.nav-brand {
  font-family: var(--font-mono);
  font-weight: 800;
  letter-spacing: 1px;
  font-size: 1.2rem;
  cursor: pointer;
  transition: color 0.2s;
}
.nav-brand:hover { color: var(--orange); }

.nav-center {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  color: #888;
  letter-spacing: 1px;
}

.nav-right {
  display: flex;
  align-items: center;
}

.status-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: #888;
  padding: 4px 12px;
  border: 1px solid #333;
  border-radius: 20px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #555;
}

.status-pill.running .status-dot { background: var(--orange); animation: pulse 1.2s infinite; }
.status-pill.success .status-dot { background: #4caf50; }
.status-pill.error .status-dot { background: #f44336; }
.status-pill.running { color: var(--orange); border-color: var(--orange); }
.status-pill.success { color: #4caf50; border-color: #4caf50; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* =================== MAIN CONTENT =================== */
.main-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: 40px 40px 80px;
}

/* =================== START SECTION =================== */
.start-section {
  display: flex;
  gap: 60px;
  align-items: flex-start;
}

.start-hero {
  flex: 0.9;
  padding-top: 20px;
}

.tag-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
  font-family: var(--font-mono);
  font-size: 0.8rem;
}

.orange-tag {
  background: var(--orange);
  color: var(--white);
  padding: 4px 10px;
  font-weight: 700;
  letter-spacing: 1px;
  font-size: 0.75rem;
}

.version-text {
  color: #999;
  font-weight: 500;
}

.start-title {
  font-size: 3.5rem;
  line-height: 1.15;
  font-weight: 500;
  margin: 0 0 30px 0;
  letter-spacing: -1.5px;
  color: var(--black);
}

.gradient-text {
  background: linear-gradient(90deg, #000 0%, #444 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  display: inline-block;
}

.start-desc {
  font-size: 1rem;
  line-height: 1.8;
  color: var(--gray-text);
  max-width: 500px;
}

.hl-bold {
  color: var(--black);
  font-weight: 600;
}

.start-form {
  flex: 1.1;
}

/* Console Form (matches Home.vue) */
.console-box {
  border: 1px solid #CCC;
  padding: 8px;
}

.console-section {
  padding: 20px;
}

.console-section.btn-section {
  padding-top: 0;
}

.console-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: #666;
}

.console-meta {
  color: #aaa;
}

.console-divider {
  display: flex;
  align-items: center;
  margin: 4px 0;
}

.console-divider::before,
.console-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: #EEE;
}

.console-divider span {
  padding: 0 15px;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: #BBB;
  letter-spacing: 1px;
}

.code-input {
  width: 100%;
  border: 1px solid #DDD;
  background: var(--bg-alt);
  padding: 14px 16px;
  font-family: var(--font-mono);
  font-size: 0.9rem;
  line-height: 1.6;
  outline: none;
  color: var(--black);
  transition: border-color 0.2s;
}

.code-input:focus {
  border-color: var(--orange);
}

.code-input.multi-line {
  resize: vertical;
  min-height: 120px;
}

/* Upload Zone */
.upload-zone {
  border: 1px dashed #CCC;
  min-height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  background: var(--bg-alt);
}

.upload-zone:hover,
.upload-zone.drag-over {
  border-color: var(--orange);
  background: #FFF5F0;
}

.upload-placeholder {
  text-align: center;
}

.upload-icon-box {
  width: 36px;
  height: 36px;
  border: 1px solid #DDD;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 10px;
  color: #999;
  font-size: 18px;
}

.upload-title {
  font-size: 0.85rem;
  color: var(--gray-text);
}

.file-display {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
}

.file-icon { font-size: 1.2rem; }
.file-name {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  color: var(--orange);
  font-weight: 600;
}

.remove-btn {
  background: none;
  border: none;
  font-size: 1.3rem;
  color: #999;
  cursor: pointer;
  line-height: 1;
}
.remove-btn:hover { color: #f44336; }

/* Start Button */
.start-engine-btn {
  width: 100%;
  background: var(--black);
  color: var(--white);
  border: none;
  padding: 18px 24px;
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 1rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  transition: all 0.3s ease;
  letter-spacing: 1px;
}

.start-engine-btn:not(:disabled):hover {
  background: var(--orange);
}

.start-engine-btn:disabled {
  background: #E5E5E5;
  color: #999;
  cursor: not-allowed;
}

.btn-arrow { font-size: 1.2rem; }

.error-msg {
  color: #f44336;
  font-family: var(--font-mono);
  font-size: 0.8rem;
  margin-top: 12px;
}

/* =================== DEBATE SECTION =================== */
.debate-section { }

/* Progress */
.progress-container {
  margin-bottom: 32px;
}

.progress-track {
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 8px;
}

.progress-fill {
  height: 100%;
  background: var(--orange);
  transition: width 0.5s ease;
}

.progress-text {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--gray-text);
}

/* =================== MIND MAP =================== */
.mindmap-wrapper {
  margin-bottom: 40px;
  background: var(--bg-alt);
  border: 1px solid var(--border);
  padding: 24px 16px;
  overflow: hidden;
}

.mindmap {
  position: relative;
  width: 100%;
  max-width: 860px;
  height: 360px;
  margin: 0 auto;
}

.mindmap-svg {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.conn-line {
  fill: none;
  stroke: #DDD;
  stroke-width: 1.5;
  transition: stroke 0.5s, stroke-dashoffset 0.5s;
}

.conn-line.active {
  stroke: var(--orange);
  stroke-width: 2;
  stroke-dasharray: 8 4;
  animation: dash-flow 1.5s linear infinite;
}

.conn-line.done {
  stroke: #CCCCCC;
  stroke-width: 2;
  opacity: 1;
}

.conn-line.cross {
  stroke-dasharray: 4 4;
}

@keyframes dash-flow {
  to { stroke-dashoffset: -24; }
}

/* Mind-map Nodes */
.mm-node {
  position: absolute;
  background: var(--white);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
  text-align: center;
  opacity: 0;
  transform: translateY(10px);
  transition: opacity 0.5s, transform 0.5s;
  min-width: 120px;
}

.mm-node.visible {
  opacity: 1;
  transform: translateY(0);
}

.mm-node.thinking {
  animation: node-pulse 1.5s ease-in-out infinite;
}

@keyframes node-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(255, 69, 0, 0.2); }
  50% { box-shadow: 0 0 0 8px rgba(255, 69, 0, 0); }
}

/* Document node - top center */
.document-node {
  top: 8px;
  left: 50%;
  transform: translateX(-50%);
  opacity: 1;
  border-color: var(--orange);
}

.mm-icon {
  font-size: 1.5rem;
  margin-bottom: 4px;
}

.mm-label {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--black);
  white-space: nowrap;
}

.mm-sublabel {
  font-family: var(--font-mono);
  font-size: 0.6rem;
  color: var(--gray-text);
}

.mm-state {
  font-family: var(--font-mono);
  font-size: 0.6rem;
  color: var(--orange);
  margin-top: 2px;
}

/* Agent nodes - row */
.agent-node {
  top: 130px;
}

.agent-node.quant { left: 5%; }
.agent-node.fundamental { left: 27%; }
.agent-node.risk { left: 52%; }
.agent-node.devil { left: 74%; }

.mm-icon-letter {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-mono);
  font-weight: 800;
  font-size: 0.9rem;
  color: var(--white);
  margin: 0 auto 6px;
}

.quant .mm-icon-letter { background: #2196f3; }
.fundamental .mm-icon-letter { background: #9c27b0; }
.risk .mm-icon-letter { background: #f44336; }
.devil .mm-icon-letter { background: #E64A19; }
.mm-icon-letter.cio { background: #F9A825; width: 36px; height: 36px; font-size: 1rem; }

/* CIO node - bottom center */
.cio-node {
  top: 275px;
  left: 50%;
  transform: translateX(-50%);
  border-color: #F9A825;
  border-width: 2px;
  min-width: 140px;
}

.cio-node.visible {
  opacity: 1;
  transform: translateX(-50%) translateY(0);
}

/* =================== ROUND CARDS =================== */
.rounds-section {
  margin-bottom: 32px;
}

.round-card {
  background: var(--white);
  border: 1px solid var(--border);
  margin-bottom: 24px;
  overflow: hidden;
}

.fade-in {
  animation: fadeSlideIn 0.5s ease-out;
}

@keyframes fadeSlideIn {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}

.round-header {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-alt);
}

.round-badge {
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 0.8rem;
  color: var(--black);
  opacity: 0.3;
}

.round-title {
  font-weight: 600;
  font-size: 0.95rem;
  color: var(--black);
}

.cio-header {
  background: #FFFDE7;
  border-bottom-color: #F9A825;
}

.cio-badge {
  color: #F9A825;
  opacity: 1;
}

/* Agent Cards in Rounds */
.agents-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
  padding: 20px 24px;
}

.agent-card {
  background: var(--bg-alt);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 16px;
  border-left: 3px solid #DDD;
}

.border-blue { border-left-color: #2196f3; }
.border-purple { border-left-color: #9c27b0; }
.border-red { border-left-color: #f44336; }
.border-deeporange { border-left-color: #E64A19; }
.border-gold { border-left-color: #F9A825; }

.agent-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.agent-letter {
  width: 26px;
  height: 26px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 0.75rem;
  color: var(--white);
}

.bg-blue { background: #2196f3; }
.bg-purple { background: #9c27b0; }
.bg-red { background: #f44336; }
.bg-deeporange { background: #E64A19; }
.bg-gold { background: #F9A825; }

.agent-name {
  font-weight: 600;
  font-size: 0.85rem;
}

.agent-model {
  font-family: var(--font-mono);
  font-size: 0.65rem;
  color: #aaa;
  margin-left: auto;
}

/* Direction Badges */
.direction-badge {
  display: inline-block;
  padding: 3px 12px;
  border-radius: 3px;
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 0.75rem;
  margin-bottom: 10px;
  letter-spacing: 0.5px;
}

.dir-buy { background: #E8F5E9; color: #2E7D32; border: 1px solid #A5D6A7; }
.dir-sell { background: #FFEBEE; color: #C62828; border: 1px solid #EF9A9A; }
.dir-hold { background: #FFF3E0; color: #E65100; border: 1px solid #FFCC02; }

/* Conviction Bar */
.conviction-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-size: 0.8rem;
}

.conviction-label {
  color: var(--gray-text);
  font-size: 0.75rem;
}

.conviction-val {
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 0.8rem;
  min-width: 40px;
}

.conviction-bar {
  flex: 1;
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
}

.conviction-fill {
  height: 100%;
  background: var(--orange);
  transition: width 0.5s ease;
  border-radius: 2px;
}

/* Detail Blocks */
.detail-block {
  margin-bottom: 10px;
}

.detail-title {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--gray-text);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
}

.detail-block ul,
.cio-col ul {
  margin: 0;
  padding-left: 16px;
}

.detail-block li,
.cio-col li {
  font-size: 0.8rem;
  line-height: 1.6;
  color: #444;
  margin-bottom: 2px;
}

.detail-block.risks li { color: #C62828; }
.detail-block.concessions li { color: #E65100; font-style: italic; }

/* Factor Chips */
.factors-row {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 8px;
}

.factor-chip {
  font-family: var(--font-mono);
  font-size: 0.65rem;
  padding: 2px 8px;
  background: #F5F5F5;
  border: 1px solid var(--border);
  border-radius: 3px;
  color: var(--gray-text);
}

/* Challenge Block */
.challenge-block {
  margin-bottom: 12px;
}

.challenge-target {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--orange);
  margin-bottom: 4px;
}

.challenge-block ul {
  margin: 0;
  padding-left: 16px;
}

.challenge-block li {
  font-size: 0.8rem;
  line-height: 1.5;
  color: #444;
}

/* =================== CIO ROUND =================== */
.cio-round {
  border-color: #F9A825;
  border-width: 2px;
}

.cio-body {
  padding: 24px 32px;
}

.cio-rec-badge {
  display: inline-block;
  padding: 6px 20px;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-weight: 800;
  font-size: 1.1rem;
  margin-bottom: 12px;
  letter-spacing: 1px;
}

.cio-conviction {
  font-size: 0.9rem;
  color: var(--gray-text);
  margin-bottom: 16px;
}

.cio-conviction strong {
  color: var(--black);
}

.cio-thesis {
  font-size: 1rem;
  line-height: 1.7;
  color: #333;
  margin-bottom: 20px;
  border-left: 3px solid var(--orange);
  padding-left: 16px;
}

/* Confidence Distribution Bar */
.conf-bar-wrapper {
  margin-bottom: 24px;
}

.conf-bar-label {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--gray-text);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

.conf-bar {
  display: flex;
  height: 28px;
  border-radius: 4px;
  overflow: hidden;
}

.conf-segment {
  display: flex;
  align-items: center;
  justify-content: center;
  transition: width 0.5s ease;
}

.conf-segment.buy { background: #A5D6A7; color: #1B5E20; }
.conf-segment.hold { background: #FFE082; color: #E65100; }
.conf-segment.sell { background: #EF9A9A; color: #B71C1C; }

.conf-seg-text {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  font-weight: 700;
  white-space: nowrap;
}

.cio-columns {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  margin-bottom: 16px;
}

.cio-col.dissent {
  border-left: 2px solid var(--border);
  padding-left: 16px;
}

.cio-col.dissent li {
  color: #777;
  font-style: italic;
}

.cio-sizing {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--gray-text);
  padding: 10px 14px;
  background: var(--bg-alt);
  border: 1px solid var(--border);
  border-radius: 4px;
}

.sizing-label {
  font-weight: 700;
  color: var(--black);
}

/* Raw / fallback content */
.raw-content {
  white-space: pre-wrap;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: #888;
  max-height: 200px;
  overflow-y: auto;
}

/* =================== FINAL BANNER =================== */
.final-banner {
  text-align: center;
  padding: 40px 32px;
  border-radius: 8px;
  margin-top: 32px;
  border: 2px solid;
}

.final-banner.dir-buy {
  background: linear-gradient(135deg, #E8F5E9 0%, #FFFFFF 100%);
  border-color: #4CAF50;
}

.final-banner.dir-sell {
  background: linear-gradient(135deg, #FFEBEE 0%, #FFFFFF 100%);
  border-color: #EF5350;
}

.final-banner.dir-hold {
  background: linear-gradient(135deg, #FFF3E0 0%, #FFFFFF 100%);
  border-color: #FF9800;
}

.final-rec {
  font-family: var(--font-mono);
  font-size: 2.5rem;
  font-weight: 800;
  letter-spacing: 3px;
  margin-bottom: 12px;
}

.dir-buy .final-rec { color: #2E7D32; }
.dir-sell .final-rec { color: #C62828; }
.dir-hold .final-rec { color: #E65100; }

.final-thesis {
  font-size: 1rem;
  line-height: 1.6;
  color: #555;
  max-width: 600px;
  margin: 0 auto 16px;
}

.final-calibration {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--gray-text);
  margin-bottom: 6px;
}

.cal-sep {
  margin: 0 8px;
  color: #CCC;
}

.final-quality {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: #999;
  margin-bottom: 20px;
}

.new-debate-btn {
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 0.85rem;
  background: var(--black);
  color: var(--white);
  border: none;
  padding: 12px 32px;
  cursor: pointer;
  letter-spacing: 1px;
  transition: background 0.2s;
}

.new-debate-btn:hover { background: var(--orange); }

.new-debate-btn.small {
  padding: 8px 20px;
  font-size: 0.75rem;
  margin-left: 16px;
}

/* Error Banner */
.error-banner {
  background: #FFF5F5;
  border: 1px solid #EF5350;
  border-radius: 6px;
  padding: 16px 24px;
  color: #C62828;
  font-size: 0.9rem;
  margin-top: 16px;
  display: flex;
  align-items: center;
}

/* =================== RESPONSIVE =================== */
@media (max-width: 1024px) {
  .start-section {
    flex-direction: column;
  }

  .start-hero {
    padding-right: 0;
  }

  .start-title {
    font-size: 2.5rem;
  }

  .agents-grid {
    grid-template-columns: 1fr 1fr;
  }

  .cio-columns {
    grid-template-columns: 1fr;
  }

  .mindmap-wrapper {
    display: none;
  }
}

@media (max-width: 640px) {
  .main-content {
    padding: 20px 16px 60px;
  }

  .navbar {
    padding: 0 16px;
  }

  .agents-grid {
    grid-template-columns: 1fr;
  }
}
</style>
