<template>
  <div class="debate-view">
    <!-- Header -->
    <header class="app-header">
      <div class="header-left">
        <div class="brand" @click="$router.push('/')">MIROFISH</div>
      </div>
      <div class="header-center">
        <span class="view-title">Investment Debate</span>
      </div>
      <div class="header-right">
        <span class="status-indicator" :class="statusClass">
          <span class="dot"></span>
          {{ statusText }}
        </span>
      </div>
    </header>

    <main class="debate-content">
      <!-- Upload / Start Panel -->
      <section v-if="!debateId" class="start-panel">
        <div class="start-card">
          <h2>Start Investment Debate</h2>
          <p class="desc">Upload a research PDF (earnings report, analyst report, 10-K filing) and ask an investment question. Five AI agents will debate the thesis in a structured IC-style format.</p>

          <div class="form-group">
            <label>Investment Question</label>
            <input
              v-model="question"
              type="text"
              placeholder='e.g. "Should we buy AAPL at current levels?"'
              class="text-input"
            />
          </div>

          <div class="form-group">
            <label>Research Document</label>
            <div
              class="drop-zone"
              :class="{ active: dragOver }"
              @dragover.prevent="dragOver = true"
              @dragleave="dragOver = false"
              @drop.prevent="onDrop"
              @click="$refs.fileInput.click()"
            >
              <input ref="fileInput" type="file" accept=".pdf,.txt,.md" hidden @change="onFileSelect" />
              <div v-if="!file" class="drop-placeholder">
                <span class="upload-icon">&#8679;</span>
                <span>Drop a PDF, TXT, or MD file here, or click to browse</span>
              </div>
              <div v-else class="file-info">
                <span class="file-name">{{ file.name }}</span>
                <button class="remove-btn" @click.stop="file = null">&times;</button>
              </div>
            </div>
          </div>

          <div class="form-group" v-if="!file">
            <label>Or paste text directly</label>
            <textarea v-model="pastedText" rows="6" class="text-area" placeholder="Paste investment research text here..."></textarea>
          </div>

          <button class="start-btn" :disabled="!canStart || loading" @click="startNewDebate">
            {{ loading ? 'Starting...' : 'Start Debate' }}
          </button>
          <p v-if="error" class="error-msg">{{ error }}</p>
        </div>
      </section>

      <!-- Active Debate -->
      <section v-else class="debate-panel">
        <!-- Progress bar -->
        <div class="progress-bar-container">
          <div class="progress-bar" :style="{ width: progress + '%' }"></div>
          <span class="progress-label">{{ progressLabel }}</span>
        </div>

        <!-- Rounds -->
        <div class="rounds-container">
          <div v-for="round in rounds" :key="round.round_number" class="round-card">
            <div class="round-header">
              <span class="round-num">Round {{ round.round_number }}</span>
              <span class="round-name">{{ round.round_name }}</span>
            </div>
            <div class="agents-grid">
              <div
                v-for="resp in round.responses"
                :key="resp.agent_role"
                class="agent-card"
                :class="agentClass(resp.agent_role)"
              >
                <div class="agent-header">
                  <span class="agent-icon">{{ agentIcon(resp.agent_role) }}</span>
                  <span class="agent-name">{{ resp.agent_name }}</span>
                  <span class="agent-model">{{ resp.model_used }}</span>
                </div>
                <div class="agent-body">
                  <!-- Round 1: Thesis -->
                  <template v-if="resp.thesis">
                    <div class="direction-badge" :class="resp.thesis.direction.toLowerCase()">
                      {{ resp.thesis.direction }}
                    </div>
                    <div class="conviction">Conviction: {{ resp.thesis.conviction }}/10</div>
                    <div class="arguments">
                      <strong>Key Arguments:</strong>
                      <ul><li v-for="a in resp.thesis.key_arguments" :key="a">{{ a }}</li></ul>
                    </div>
                    <div class="risks">
                      <strong>Key Risks:</strong>
                      <ul><li v-for="r in resp.thesis.key_risks" :key="r">{{ r }}</li></ul>
                    </div>
                  </template>

                  <!-- Round 2: Cross-Examination -->
                  <template v-else-if="resp.cross_examination">
                    <div v-for="(challenges, target) in resp.cross_examination.challenges" :key="target" class="challenge-block">
                      <strong>To {{ target }}:</strong>
                      <ul><li v-for="c in challenges" :key="c">{{ c }}</li></ul>
                    </div>
                  </template>

                  <!-- Round 3: Rebuttal -->
                  <template v-else-if="resp.rebuttal">
                    <div class="conviction">Updated Conviction: {{ resp.rebuttal.updated_conviction }}/10</div>
                    <div v-if="resp.rebuttal.updated_direction" class="direction-badge" :class="resp.rebuttal.updated_direction.toLowerCase()">
                      {{ resp.rebuttal.updated_direction }}
                    </div>
                    <div class="defenses">
                      <strong>Defenses:</strong>
                      <ul><li v-for="d in resp.rebuttal.defenses" :key="d">{{ d }}</li></ul>
                    </div>
                    <div v-if="resp.rebuttal.concessions.length" class="concessions">
                      <strong>Concessions:</strong>
                      <ul><li v-for="c in resp.rebuttal.concessions" :key="c">{{ c }}</li></ul>
                    </div>
                  </template>

                  <!-- Round 4: CIO Synthesis -->
                  <template v-else-if="resp.cio_synthesis">
                    <div class="direction-badge large" :class="resp.cio_synthesis.recommendation.toLowerCase()">
                      {{ resp.cio_synthesis.recommendation }}
                    </div>
                    <div class="conviction">Consensus Conviction: {{ resp.cio_synthesis.consensus_conviction }}/10</div>
                    <div class="thesis-text">{{ resp.cio_synthesis.key_thesis }}</div>
                    <div class="confidence-dist">
                      <span v-for="(pct, dir) in resp.cio_synthesis.confidence_distribution" :key="dir" class="conf-chip" :class="dir.toLowerCase()">
                        {{ dir }}: {{ (pct * 100).toFixed(0) }}%
                      </span>
                    </div>
                    <div class="risks">
                      <strong>Primary Risks:</strong>
                      <ul><li v-for="r in resp.cio_synthesis.primary_risks" :key="r">{{ r }}</li></ul>
                    </div>
                    <div v-if="resp.cio_synthesis.dissenting_views.length" class="dissent">
                      <strong>Dissenting Views:</strong>
                      <ul><li v-for="d in resp.cio_synthesis.dissenting_views" :key="d">{{ d }}</li></ul>
                    </div>
                  </template>

                  <!-- Fallback: raw text -->
                  <template v-else>
                    <div class="raw-content">{{ resp.content }}</div>
                  </template>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Final Recommendation Banner -->
        <div v-if="finalRecommendation" class="final-banner" :class="finalRecommendation.recommendation.toLowerCase()">
          <h2>Final Recommendation: {{ finalRecommendation.recommendation }}</h2>
          <p class="final-thesis">{{ finalRecommendation.key_thesis }}</p>
          <div v-if="consensusScore" class="calibration-note">
            Raw Conviction: {{ consensusScore.raw_score }}/10 |
            Calibrated (Platt): {{ (consensusScore.calibrated_score * 100).toFixed(1) }}%
          </div>
        </div>

        <!-- Error banner -->
        <div v-if="debateError" class="error-banner">
          <strong>Debate Failed:</strong> {{ debateError }}
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onUnmounted } from 'vue'
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

const statusText = computed(() => {
  if (!debateId.value) return 'Ready'
  const map = {
    pending: 'Pending',
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

const progressLabel = computed(() => `${progress.value}% — ${statusText.value}`)

function agentIcon(role) {
  const icons = {
    quant_analyst: 'Q',
    fundamental_analyst: 'F',
    risk_manager: 'R',
    devil_advocate: 'D',
    cio: 'C',
  }
  return icons[role] || '?'
}

function agentClass(role) {
  return `agent-${role.replace(/_/g, '-')}`
}

function onFileSelect(e) {
  file.value = e.target.files[0] || null
}

function onDrop(e) {
  dragOver.value = false
  const f = e.dataTransfer.files[0]
  if (f) file.value = f
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

      // Fetch full result to get rounds
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
  }, 3000)
}

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.debate-view {
  min-height: 100vh;
  background: #0a0a0a;
  color: #e0e0e0;
  font-family: 'SF Mono', 'Fira Code', monospace;
}

.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 24px;
  border-bottom: 1px solid #222;
  background: #111;
}

.brand {
  font-weight: 700;
  font-size: 16px;
  letter-spacing: 2px;
  cursor: pointer;
  color: #ff9800;
}

.view-title {
  font-size: 14px;
  color: #888;
  letter-spacing: 1px;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.status-indicator .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #555;
}

.status-indicator.running .dot { background: #ff9800; animation: pulse 1s infinite; }
.status-indicator.success .dot { background: #4caf50; }
.status-indicator.error .dot { background: #f44336; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.debate-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

/* Start Panel */
.start-card {
  background: #161616;
  border: 1px solid #2a2a2a;
  border-radius: 8px;
  padding: 32px;
  max-width: 700px;
  margin: 40px auto;
}

.start-card h2 {
  margin: 0 0 8px;
  font-size: 20px;
  color: #ff9800;
}

.start-card .desc {
  color: #888;
  font-size: 13px;
  margin-bottom: 24px;
  line-height: 1.6;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  font-size: 12px;
  color: #999;
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.text-input, .text-area {
  width: 100%;
  background: #0e0e0e;
  border: 1px solid #333;
  border-radius: 4px;
  padding: 10px 12px;
  color: #e0e0e0;
  font-size: 14px;
  font-family: inherit;
  box-sizing: border-box;
}

.text-input:focus, .text-area:focus {
  outline: none;
  border-color: #ff9800;
}

.drop-zone {
  border: 2px dashed #333;
  border-radius: 6px;
  padding: 24px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.2s;
}

.drop-zone.active, .drop-zone:hover {
  border-color: #ff9800;
}

.drop-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: #666;
  font-size: 13px;
}

.upload-icon {
  font-size: 24px;
}

.file-info {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: center;
}

.file-name {
  color: #ff9800;
  font-weight: 600;
}

.remove-btn {
  background: none;
  border: none;
  color: #f44336;
  font-size: 18px;
  cursor: pointer;
}

.start-btn {
  width: 100%;
  padding: 12px;
  background: #ff9800;
  color: #000;
  border: none;
  border-radius: 4px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
}

.start-btn:disabled {
  background: #333;
  color: #666;
  cursor: not-allowed;
}

.error-msg {
  color: #f44336;
  font-size: 12px;
  margin-top: 8px;
}

/* Progress */
.progress-bar-container {
  position: relative;
  background: #1a1a1a;
  height: 28px;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 24px;
}

.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #ff9800, #ff5722);
  transition: width 0.5s ease;
}

.progress-label {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: 11px;
  color: #fff;
  white-space: nowrap;
}

/* Rounds */
.round-card {
  background: #161616;
  border: 1px solid #2a2a2a;
  border-radius: 8px;
  margin-bottom: 20px;
  overflow: hidden;
}

.round-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #1c1c1c;
  border-bottom: 1px solid #2a2a2a;
}

.round-num {
  font-weight: 700;
  color: #ff9800;
  font-size: 13px;
}

.round-name {
  color: #888;
  font-size: 12px;
}

.agents-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  padding: 16px;
}

.agent-card {
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  padding: 14px;
  border-left: 3px solid #444;
}

.agent-quant-analyst { border-left-color: #2196f3; }
.agent-fundamental-analyst { border-left-color: #9c27b0; }
.agent-risk-manager { border-left-color: #f44336; }
.agent-devil-advocate { border-left-color: #ff5722; }
.agent-cio { border-left-color: #ff9800; }

.agent-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.agent-icon {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #222;
  border-radius: 4px;
  font-weight: 700;
  font-size: 12px;
  color: #ff9800;
}

.agent-name {
  font-weight: 600;
  font-size: 13px;
}

.agent-model {
  font-size: 10px;
  color: #666;
  margin-left: auto;
}

.agent-body {
  font-size: 12px;
  line-height: 1.6;
}

.direction-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 3px;
  font-weight: 700;
  font-size: 11px;
  margin-bottom: 6px;
}

.direction-badge.buy { background: #1b5e20; color: #4caf50; }
.direction-badge.sell { background: #b71c1c; color: #ef5350; }
.direction-badge.hold { background: #e65100; color: #ff9800; }
.direction-badge.large { font-size: 14px; padding: 4px 14px; }

.conviction {
  font-size: 12px;
  color: #aaa;
  margin-bottom: 8px;
}

.agent-body ul {
  margin: 4px 0 8px 16px;
  padding: 0;
}

.agent-body li {
  margin-bottom: 3px;
}

.challenge-block {
  margin-bottom: 10px;
}

.confidence-dist {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin: 8px 0;
}

.conf-chip {
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
}

.conf-chip.buy { background: #1b5e20; color: #4caf50; }
.conf-chip.sell { background: #b71c1c; color: #ef5350; }
.conf-chip.hold { background: #e65100; color: #ff9800; }

.thesis-text {
  color: #ccc;
  font-size: 13px;
  margin: 8px 0;
  line-height: 1.5;
}

.raw-content {
  white-space: pre-wrap;
  font-size: 11px;
  color: #999;
  max-height: 200px;
  overflow-y: auto;
}

/* Final Banner */
.final-banner {
  text-align: center;
  padding: 24px;
  border-radius: 8px;
  margin-top: 24px;
}

.final-banner.buy { background: linear-gradient(135deg, #1b5e20, #0a0a0a); border: 1px solid #4caf50; }
.final-banner.sell { background: linear-gradient(135deg, #b71c1c, #0a0a0a); border: 1px solid #ef5350; }
.final-banner.hold { background: linear-gradient(135deg, #e65100, #0a0a0a); border: 1px solid #ff9800; }

.final-banner h2 {
  margin: 0 0 8px;
  font-size: 20px;
}

.final-thesis {
  color: #ccc;
  font-size: 14px;
  max-width: 600px;
  margin: 0 auto 12px;
  line-height: 1.5;
}

.calibration-note {
  font-size: 11px;
  color: #888;
}

.error-banner {
  background: #1a0000;
  border: 1px solid #f44336;
  border-radius: 8px;
  padding: 16px;
  color: #ef5350;
  margin-top: 16px;
}
</style>
