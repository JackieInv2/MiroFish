<template>
  <div class="debate-page">
    <!-- Navbar -->
    <nav class="navbar">
      <div class="nav-brand">BTRATE</div>
      <div class="nav-links">
        <router-link to="/" class="back-link">← Home</router-link>
        <a href="https://github.com/JackieInv2/BTRate" target="_blank" class="github-link">GitHub ↗</a>
      </div>
    </nav>

    <!-- Main layout: graph left + panel right -->
    <div class="main-layout">
      <!-- LEFT: D3 Force Graph -->
      <div class="graph-panel" ref="graphPanel">
        <div class="graph-header">
          <span class="graph-label">AGENT NETWORK</span>
          <span class="graph-status" :class="statusClass">{{ graphStatusText }}</span>
        </div>
        <div id="graph-container" ref="graphContainer">
          <svg id="force-graph" ref="svgEl"></svg>
          <!-- Node tooltip -->
          <div class="node-tooltip" v-if="hoveredNode" :style="tooltipStyle">
            {{ AGENT_NAMES[hoveredNode] }}
          </div>
          <!-- Node detail panel -->
          <div class="node-detail-card" v-if="selectedAgent && debateResults">
            <div class="detail-header">
              <span class="detail-title">{{ AGENT_NAMES[selectedAgent] }}</span>
              <button class="detail-close" @click="selectedAgent = null">×</button>
            </div>
            <div v-if="selectedAgentData" class="detail-body">
              <div class="detail-direction" :class="selectedAgentData.direction?.toLowerCase()">
                {{ selectedAgentData.direction }}
              </div>
              <div class="detail-conviction">Conviction: {{ selectedAgentData.conviction }}/10</div>
              <div class="detail-section" v-if="selectedAgentData.key_arguments?.length">
                <div class="detail-section-title">KEY ARGUMENTS</div>
                <div v-for="(arg, i) in selectedAgentData.key_arguments.slice(0,2)" :key="i" class="detail-bullet">· {{ arg }}</div>
              </div>
              <div class="detail-section" v-if="selectedAgentData.key_risks?.length">
                <div class="detail-section-title">KEY RISKS</div>
                <div class="detail-bullet risk">· {{ selectedAgentData.key_risks[0] }}</div>
              </div>
            </div>
          </div>
        </div>
        <!-- Legend -->
        <div class="graph-legend">
          <span v-for="(color, role) in AGENT_COLORS" :key="role" class="legend-item">
            <span class="legend-dot" :style="{background: color}"></span>
            {{ AGENT_LABELS[role] }} {{ AGENT_SHORT_NAMES[role] }}
          </span>
        </div>
      </div>

      <!-- RIGHT: Control / Results Panel -->
      <div class="right-panel">
        <!-- STATE 1: Input Form -->
        <div v-if="state === 'idle'" class="input-panel">
          <div class="panel-title-row">
            <span class="panel-badge">IC DEBATE ENGINE</span>
          </div>
          <div class="input-group">
            <label class="input-label">01 / INVESTMENT QUESTION</label>
            <textarea
              v-model="question"
              class="input-textarea"
              rows="4"
              placeholder="e.g. Should we take a long position in AAPL given current macro conditions?"
            ></textarea>
          </div>
          <div class="input-group">
            <label class="input-label">02 / RESEARCH DOCUMENT <span class="label-meta">paste text or drop file</span></label>
            <textarea
              v-if="!uploadedFile"
              v-model="documentText"
              class="input-textarea doc-textarea"
              rows="5"
              placeholder="Paste your investment memo, earnings report, or research note here…"
            ></textarea>
            <div
              class="file-drop-zone"
              :class="{ 'has-file': uploadedFile, 'drag-over': isDragOver }"
              @click="triggerFileInput"
              @dragover.prevent="isDragOver = true"
              @dragleave="isDragOver = false"
              @drop.prevent="handleDrop"
            >
              <span v-if="!uploadedFile" class="drop-text">Or drop a file (PDF · TXT · MD)</span>
              <span v-else class="drop-text file-name">📄 {{ uploadedFile.name }} <button class="clear-file-btn" @click.stop="clearFile">✕</button></span>
            </div>
            <input ref="fileInput" type="file" accept=".pdf,.txt,.md" class="hidden-input" @change="handleFileChange" />
            <div class="or-divider"><span>OR PASTE TEXT</span></div>
            <textarea
              v-model="documentText"
              class="input-textarea doc-textarea"
              rows="5"
              placeholder="Paste research document, earnings report, or investment memo text here..."
              :disabled="!!uploadedFile"
            ></textarea>
          </div>
          <button class="start-btn" @click="startDebate" :disabled="!question.trim()">
            START IC DEBATE <span class="btn-arrow">→</span>
          </button>
        </div>

        <!-- STATE 2: Running -->
        <div v-if="state === 'running'" class="running-panel">
          <div class="running-header">
            <span class="running-title">DEBATE IN PROGRESS</span>
            <div class="spinner"></div>
          </div>
          <div class="progress-bar-track">
            <div class="progress-bar-fill" :style="{width: progress + '%'}"></div>
          </div>
          <div class="round-indicators">
            <div v-for="r in 4" :key="r" class="round-badge" :class="{ active: progress >= r * 25 }">
              0{{ r }}
            </div>
          </div>
          <div class="running-desc">
            Running 4 structured IC rounds · Agents converging on recommendation
          </div>
          <div class="agent-activity">
            <div v-for="(color, role) in AGENT_COLORS" :key="role" class="activity-row">
              <div class="activity-dot" :style="{background: color}" :class="{ pulse: isAgentActive(role) }"></div>
              <span class="activity-name">{{ AGENT_NAMES[role] }}</span>
              <span class="activity-status">{{ agentStatus[role] || 'standby' }}</span>
            </div>
          </div>
        </div>

        <!-- STATE 3: Results -->
        <div v-if="state === 'complete' && debateResults" class="results-panel">
          <div class="results-scroll">
            <!-- Final Recommendation -->
            <div class="recommendation-block">
              <div class="rec-badge" :class="debateResults.final_recommendation.recommendation.toLowerCase()">
                {{ debateResults.final_recommendation.recommendation }}
              </div>
              <div class="rec-scores">
                <div class="score-item">
                  <div class="score-value">{{ debateResults.final_recommendation.consensus_conviction }}</div>
                  <div class="score-label">CONVICTION / 10</div>
                </div>
                <div class="score-divider"></div>
                <div class="score-item">
                  <div class="score-value">{{ debateResults.consensus_score?.calibrated_score?.toFixed(3) }}</div>
                  <div class="score-label">CALIBRATED</div>
                </div>
                <div class="score-divider"></div>
                <div class="score-item">
                  <div class="score-value">{{ debateResults.final_recommendation.debate_quality_score }}</div>
                  <div class="score-label">DEBATE QUALITY</div>
                </div>
              </div>
            </div>

            <!-- Key Thesis -->
            <div class="results-section">
              <div class="section-header">KEY THESIS</div>
              <p class="thesis-text">{{ debateResults.final_recommendation.key_thesis }}</p>
            </div>

            <!-- Confidence Distribution -->
            <div class="results-section">
              <div class="section-header">CONFIDENCE DISTRIBUTION</div>
              <div class="confidence-bars">
                <div v-for="(val, dir) in debateResults.final_recommendation.confidence_distribution" :key="dir" class="conf-row">
                  <span class="conf-label" :class="dir.toLowerCase()">{{ dir }}</span>
                  <div class="conf-track">
                    <div class="conf-fill" :class="dir.toLowerCase()" :style="{width: (val*100) + '%'}"></div>
                  </div>
                  <span class="conf-pct">{{ Math.round(val * 100) }}%</span>
                </div>
              </div>
            </div>

            <!-- Round Breakdown -->
            <div class="results-section">
              <div class="section-header">ROUND BREAKDOWN</div>
              <div class="round-tabs">
                <button v-for="r in debateResults.rounds" :key="r.round_number"
                  class="round-tab" :class="{active: activeRound === r.round_number}"
                  @click="activeRound = r.round_number">
                  Round {{ r.round_number }}
                </button>
              </div>
              <div v-if="currentRound" class="agent-cards">
                <div v-for="resp in currentRound.responses" :key="resp.agent_role" class="agent-card"
                  :style="{borderLeftColor: AGENT_COLORS[resp.agent_role] || '#444'}">
                  <div class="card-header">
                    <div class="card-agent-info">
                      <span class="card-label" :style="{background: AGENT_COLORS[resp.agent_role] || '#444'}">
                        {{ AGENT_LABELS[resp.agent_role] }}
                      </span>
                      <span class="card-role">{{ AGENT_NAMES[resp.agent_role] }}</span>
                    </div>
                    <!-- Use structured thesis (R1), rebuttal (R3), or cio_synthesis (R4) for verdict -->
                    <div v-if="getThesis(resp)" class="card-verdict">
                      <span class="card-direction" :class="getThesis(resp).direction?.toLowerCase()">
                        {{ getThesis(resp).direction }}
                      </span>
                      <span class="card-conviction">{{ getThesis(resp).conviction }}/10</span>
                    </div>
                    <div v-else-if="getCIOSynthesis(resp)" class="card-verdict">
                      <span class="card-direction" :class="getCIOSynthesis(resp).recommendation?.toLowerCase()">
                        {{ getCIOSynthesis(resp).recommendation }}
                      </span>
                      <span class="card-conviction">{{ getCIOSynthesis(resp).consensus_conviction }}/10</span>
                    </div>
                  </div>
                  <div class="card-body">
                    <!-- Round 1: thesis arguments + risks -->
                    <template v-if="getThesis(resp)">
                      <div v-if="getThesis(resp).key_arguments?.length" class="card-section">
                        <div class="card-section-title">ARGUMENTS</div>
                        <div v-for="(a, i) in getThesis(resp).key_arguments.slice(0,3)" :key="i" class="card-bullet">· {{ a }}</div>
                      </div>
                      <div v-if="getThesis(resp).key_risks?.length" class="card-section">
                        <div class="card-section-title risk-title">RISKS</div>
                        <div v-for="(r, i) in getThesis(resp).key_risks.slice(0,2)" :key="i" class="card-bullet risk-bullet">· {{ r }}</div>
                      </div>
                    </template>
                    <!-- Round 2: cross-examination challenges -->
                    <template v-else-if="getCrossExam(resp)">
                      <div class="card-section">
                        <div class="card-section-title">CHALLENGES RAISED</div>
                        <template v-for="(items, target) in getCrossExam(resp).challenges" :key="target">
                          <div class="card-bullet challenge-target">› {{ target }}</div>
                          <div v-for="(c, ci) in items.slice(0,1)" :key="ci" class="card-bullet challenge-item">· {{ c }}</div>
                        </template>
                      </div>
                    </template>
                    <!-- Round 3: rebuttal defenses + concessions -->
                    <template v-else-if="getRebuttal(resp)">
                      <div v-if="getRebuttal(resp).defenses?.length" class="card-section">
                        <div class="card-section-title">DEFENSES</div>
                        <div v-for="(d, i) in getRebuttal(resp).defenses.slice(0,2)" :key="i" class="card-bullet">· {{ d }}</div>
                      </div>
                      <div v-if="getRebuttal(resp).concessions?.length" class="card-section">
                        <div class="card-section-title risk-title">CONCESSIONS</div>
                        <div v-for="(c, i) in getRebuttal(resp).concessions.slice(0,1)" :key="i" class="card-bullet risk-bullet">· {{ c }}</div>
                      </div>
                      <div v-if="getRebuttal(resp).updated_direction" class="card-section">
                        <div class="card-section-title">UPDATED VIEW</div>
                        <div class="card-bullet">· {{ getRebuttal(resp).updated_direction }} · conviction {{ getRebuttal(resp).updated_conviction }}/10</div>
                      </div>
                    </template>
                    <!-- Round 4: CIO synthesis -->
                    <template v-else-if="getCIOSynthesis(resp)">
                      <div v-if="getCIOSynthesis(resp).key_thesis" class="card-section">
                        <div class="card-section-title">SYNTHESIS</div>
                        <div class="card-bullet">· {{ getCIOSynthesis(resp).key_thesis }}</div>
                      </div>
                      <div v-if="getCIOSynthesis(resp).position_sizing_guidance" class="card-section">
                        <div class="card-section-title">SIZING</div>
                        <div class="card-bullet">· {{ getCIOSynthesis(resp).position_sizing_guidance }}</div>
                      </div>
                    </template>
                    <!-- Fallback: show nothing extra -->
                  </div>
                </div>
              </div>
            </div>

            <!-- Primary Risks -->
            <div v-if="debateResults.final_recommendation.primary_risks?.length" class="results-section">
              <div class="section-header">PRIMARY RISKS</div>
              <div v-for="(r, i) in debateResults.final_recommendation.primary_risks" :key="i" class="risk-item">
                <span class="risk-num">{{ String(i+1).padStart(2,'0') }}</span>
                <span class="risk-text">{{ r }}</span>
              </div>
            </div>

            <!-- Dissenting Views -->
            <div v-if="debateResults.final_recommendation.dissenting_views?.length" class="results-section">
              <div class="section-header">DISSENTING VIEWS</div>
              <div v-for="(v, i) in debateResults.final_recommendation.dissenting_views" :key="i" class="risk-item">
                <span class="risk-num">{{ String(i+1).padStart(2,'0') }}</span>
                <span class="risk-text">{{ v }}</span>
              </div>
            </div>

            <button class="new-debate-btn" @click="resetDebate">NEW DEBATE →</button>
          </div>
        </div>

        <!-- STATE: Error -->
        <div v-if="state === 'error'" class="error-panel">
          <div class="error-icon">⚠</div>
          <div class="error-title">DEBATE FAILED</div>
          <div class="error-msg">{{ errorMessage }}</div>
          <button class="new-debate-btn" @click="resetDebate">TRY AGAIN →</button>
        </div>
      </div>
    </div>

    <!-- BOTTOM: System Dashboard Log -->
    <div class="dashboard-strip">
      <div class="strip-left">
        <span class="strip-label">SYSTEM DASHBOARD</span>
      </div>
      <div class="strip-logs" ref="logsEl">
        <div v-for="(log, i) in logs" :key="i" class="log-line">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-sym" :class="log.type">{{ log.sym }}</span>
          <span class="log-msg" :class="log.type">{{ log.msg }}</span>
        </div>
      </div>
      <div class="strip-right">
        <span class="strip-session">{{ sessionId }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import * as d3 from 'd3'
import { startDebate as apiStartDebate, getDebateStatus, getDebateResult } from '../api/debate.js'

// ─── Constants ───────────────────────────────────────────────────────────────

const AGENT_COLORS = {
  quant_analyst: '#2563EB',
  fundamental_analyst: '#7C3AED',
  risk_manager: '#DC2626',
  devil_advocate: '#EA580C',
  cio: '#D97706',
}

const AGENT_LABELS = {
  quant_analyst: 'Q',
  fundamental_analyst: 'F',
  risk_manager: 'R',
  devil_advocate: 'D',
  cio: 'C',
}

const AGENT_NAMES = {
  quant_analyst: 'QUANT ANALYST',
  fundamental_analyst: 'FUNDAMENTAL ANALYST',
  risk_manager: 'RISK MANAGER',
  devil_advocate: "DEVIL'S ADVOCATE",
  cio: 'CIO',
}

const AGENT_SHORT_NAMES = {
  quant_analyst: 'Quant',
  fundamental_analyst: 'Fund.',
  risk_manager: 'Risk',
  devil_advocate: 'Devil',
  cio: 'CIO',
}

// ─── State ───────────────────────────────────────────────────────────────────

const state = ref('idle') // idle | running | complete | error
const question = ref('')
const documentText = ref('')
const uploadedFile = ref(null)
const isDragOver = ref(false)
const progress = ref(0)
const debateResults = ref(null)
const activeRound = ref(1)
const selectedAgent = ref(null)
const hoveredNode = ref(null)
const tooltipStyle = ref({})
const showRebuttal = ref({})
const errorMessage = ref('')
const agentStatus = ref({})
const logs = ref([])
const sessionId = ref(Math.random().toString(16).slice(2, 10).toUpperCase())

// DOM refs
const svgEl = ref(null)
const graphContainer = ref(null)
const graphPanel = ref(null)
const logsEl = ref(null)
const fileInput = ref(null)

let pollInterval = null
let pollTimeout = null
let edgeAnimInterval = null
let simulation = null
let svgSelection = null
let linkSelection = null
let nodeSelection = null
let debateId = null

// ─── Computed ─────────────────────────────────────────────────────────────────

const statusClass = computed(() => ({
  'status-idle': state.value === 'idle',
  'status-running': state.value === 'running',
  'status-complete': state.value === 'complete',
  'status-error': state.value === 'error',
}))

const graphStatusText = computed(() => {
  if (state.value === 'idle') return '● READY'
  if (state.value === 'running') return '◈ RUNNING'
  if (state.value === 'complete') return '✓ COMPLETE'
  if (state.value === 'error') return '⚠ ERROR'
  return ''
})

const currentRound = computed(() => {
  if (!debateResults.value?.rounds) return null
  return debateResults.value.rounds.find(r => r.round_number === activeRound.value) || debateResults.value.rounds[0]
})

const selectedAgentData = computed(() => {
  if (!selectedAgent.value || !debateResults.value?.rounds) return null
  const allResps = debateResults.value.rounds.flatMap(r => r.responses)
  const last = allResps.filter(r => r.agent_role === selectedAgent.value).pop()
  if (!last) return null
  return parseContent(last.content)
})

// ─── Utility ──────────────────────────────────────────────────────────────────

function parseContent(str) {
  if (!str) return null
  try {
    if (typeof str === 'object') return str
    return JSON.parse(str)
  } catch {
    return null
  }
}

// Structured accessors — use backend-parsed fields, never raw content string
function getThesis(resp) {
  // Backend populates resp.thesis for Round 1
  if (resp.thesis && typeof resp.thesis === 'object') return resp.thesis
  // Fallback: try parsing content if it has direction+conviction
  const p = parseContent(resp.content)
  if (p && p.direction && p.conviction != null) return p
  return null
}

function getCrossExam(resp) {
  if (resp.cross_examination && typeof resp.cross_examination === 'object') return resp.cross_examination
  const p = parseContent(resp.content)
  if (p && p.challenges) return p
  return null
}

function getRebuttal(resp) {
  if (resp.rebuttal && typeof resp.rebuttal === 'object') return resp.rebuttal
  const p = parseContent(resp.content)
  if (p && (p.defenses || p.concessions)) return p
  return null
}

function getCIOSynthesis(resp) {
  if (resp.cio_synthesis && typeof resp.cio_synthesis === 'object') return resp.cio_synthesis
  const p = parseContent(resp.content)
  if (p && p.recommendation) return p
  return null
}

function now() {
  const d = new Date()
  return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}.${String(d.getMilliseconds()).padStart(3,'0')}`
}

function addLog(msg, type = 'info') {
  const syms = { info: '├─', success: '✓', warn: '⚠', error: '✗' }
  logs.value.push({ time: now(), sym: syms[type] || '├─', msg, type })
  nextTick(() => {
    if (logsEl.value) logsEl.value.scrollLeft = logsEl.value.scrollWidth
  })
}

function isAgentActive(role) {
  return state.value === 'running' && agentStatus.value[role] === 'active'
}

function toggleRebuttal(role) {
  showRebuttal.value[role] = !showRebuttal.value[role]
}

// ─── File handling ────────────────────────────────────────────────────────────

function triggerFileInput() {
  fileInput.value?.click()
}

function handleFileChange(e) {
  uploadedFile.value = e.target.files[0] || null
  if (uploadedFile.value) addLog(`File loaded · ${uploadedFile.value.name}`)
}

function clearFile() {
  uploadedFile.value = null
  if (fileInput.value) fileInput.value.value = ''
}

function handleDrop(e) {
  isDragOver.value = false
  const file = e.dataTransfer.files[0]
  if (file) {
    uploadedFile.value = file
    addLog(`File dropped · ${file.name}`)
  }
}

// ─── Debate Flow ──────────────────────────────────────────────────────────────

async function startDebate() {
  if (!question.value.trim()) return
  state.value = 'running'
  progress.value = 0
  debateResults.value = null
  selectedAgent.value = null
  agentStatus.value = {}
  showRebuttal.value = {}

  const q = question.value.trim()
  addLog(`Starting IC debate · "${q.slice(0, 50)}${q.length > 50 ? '...' : ''}"`)
  startEdgeAnimation()

  try {
    let payload
    if (uploadedFile.value) {
      payload = new FormData()
      payload.append('file', uploadedFile.value)
      payload.append('question', q)
    } else {
      const docText = documentText.value.trim() || q
      payload = { question: q, text: docText }
    }

    const res = await apiStartDebate(payload)
    // axios interceptor already unwraps response.data, so res IS the payload
    debateId = res.debate_id || res.data?.debate_id
    if (!debateId) throw new Error('No debate_id returned from server')
    addLog(`Debate started · id: ${debateId}`)
    startPolling()
  } catch (err) {
    state.value = 'error'
    errorMessage.value = err?.response?.data?.error || err.message || 'Failed to start debate'
    addLog(`Error: ${errorMessage.value}`, 'error')
    stopEdgeAnimation()
  }
}

async function pollOnce(tick) {
  // Use getDebateStatus directly — the axios interceptor returns res directly
  const statusRes = await getDebateStatus(debateId)
  const s = statusRes.status
  const p = statusRes.progress ?? 0

  progress.value = p

  // Simulate agent activity based on progress
  const agentRoles = Object.keys(AGENT_COLORS)
  const activeIdx = Math.min(Math.floor((p / 100) * agentRoles.length), agentRoles.length - 1)
  agentRoles.forEach((role, i) => {
    agentStatus.value[role] = i === activeIdx ? 'active' : i < activeIdx ? 'done' : 'standby'
  })

  if (tick % 4 === 0) addLog(`Polling · status: ${s} · progress: ${p}%`)
  return s
}

function startPolling() {
  let tick = 0
  let done = false

  const doPoll = async () => {
    if (done) return
    try {
      tick++
      const s = await pollOnce(tick)
      if (s === 'completed') {
        done = true
        stopPolling()
        addLog('Debate complete · fetching results', 'success')
        await fetchResults()
      } else if (s === 'failed' || s === 'error') {
        done = true
        stopPolling()
        state.value = 'error'
        errorMessage.value = 'Debate engine reported an error'
        addLog('Debate engine error', 'error')
        stopEdgeAnimation()
      }
    } catch (err) {
      // Don't log every poll failure — backend may still be cold-starting
      if (tick > 5) addLog(`Poll error: ${err.message}`, 'warn')
    }
  }

  // Simple recursive setTimeout — no dual-fire from setInterval + setTimeout
  const scheduleNext = (delay) => {
    pollTimeout = setTimeout(async () => {
      await doPoll()
      if (!done) scheduleNext(2000)
    }, delay)
  }
  scheduleNext(2000) // first poll at 2s
}

function stopPolling() {
  clearTimeout(pollTimeout)
  clearInterval(pollInterval)
  pollTimeout = null
  pollInterval = null
}

async function fetchResults() {
  try {
    const res = await getDebateResult(debateId)
    // result endpoint returns { data: {...}, success: true } — so .data IS the nested payload
    const data = res.data || res
    debateResults.value = data
    state.value = 'complete'
    activeRound.value = 1
    stopEdgeAnimation()
    const rec = data.final_recommendation?.recommendation
    const conv = data.final_recommendation?.consensus_conviction
    addLog(`Recommendation: ${rec} · conviction: ${conv}/10`, 'success')
    await nextTick()
    updateGraphForResults()
  } catch (err) {
    state.value = 'error'
    errorMessage.value = err.message
    addLog(`Failed to fetch results: ${err.message}`, 'error')
    stopEdgeAnimation()
  }
}

function resetDebate() {
  state.value = 'idle'
  question.value = ''
  documentText.value = ''
  uploadedFile.value = null
  if (fileInput.value) fileInput.value.value = ''
  debateResults.value = null
  selectedAgent.value = null
  progress.value = 0
  debateId = null
  agentStatus.value = {}
  showRebuttal.value = {}
  stopPolling()
  stopEdgeAnimation()
  resetGraphToIdle()
  addLog('New debate session started')
}

// ─── D3 Graph ─────────────────────────────────────────────────────────────────

// Pre-positioned in a pentagon so nodes start spread out immediately
function makeNodes(W, H) {
  const cx = W / 2, cy = H / 2
  const r = Math.min(W, H) * 0.30
  return Object.keys(AGENT_COLORS).map((id, i) => {
    const angle = (i / 5) * 2 * Math.PI - Math.PI / 2
    return { id, x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) }
  })
}

// Full mesh: every pair of nodes has an edge (defined lazily inside initGraph)
const LINK_PAIRS = []
const roleKeys = Object.keys(AGENT_COLORS)
for (let i = 0; i < roleKeys.length; i++) {
  for (let j = i + 1; j < roleKeys.length; j++) {
    LINK_PAIRS.push({ sourceId: roleKeys[i], targetId: roleKeys[j], id: `${roleKeys[i]}--${roleKeys[j]}` })
  }
}

// Live mutable arrays for this simulation instance
let nodes = []
let links = []

function initGraph() {
  if (!svgEl.value) return

  const container = graphContainer.value
  const W = container.clientWidth || 700
  const H = container.clientHeight || 520

  svgSelection = d3.select(svgEl.value)
    .attr('width', '100%')
    .attr('height', '100%')
    .attr('viewBox', `0 0 ${W} ${H}`)
    .attr('preserveAspectRatio', 'xMidYMid meet')

  svgSelection.selectAll('*').remove()

  // Build fresh node/link arrays with pre-positioned coordinates
  nodes = makeNodes(W, H)
  links = LINK_PAIRS.map(p => ({
    source: p.sourceId,
    target: p.targetId,
    id: p.id
  }))

  // Dot grid background
  const defs = svgSelection.append('defs')
  const pattern = defs.append('pattern')
    .attr('id', 'dot-grid')
    .attr('width', 30)
    .attr('height', 30)
    .attr('patternUnits', 'userSpaceOnUse')
  pattern.append('circle')
    .attr('cx', 3).attr('cy', 3).attr('r', 1)
    .attr('fill', 'rgba(255,255,255,0.04)')

  svgSelection.append('rect')
    .attr('width', W).attr('height', H)
    .attr('fill', 'url(#dot-grid)')

  // Arrow marker for directed edges
  defs.append('marker')
    .attr('id', 'arrow')
    .attr('viewBox', '0 -4 8 8')
    .attr('refX', 36).attr('refY', 0)
    .attr('markerWidth', 6).attr('markerHeight', 6)
    .attr('orient', 'auto')
    .append('path')
    .attr('d', 'M0,-4L8,0L0,4')
    .attr('fill', '#3A3A3A')

  const g = svgSelection.append('g')

  // Links
  linkSelection = g.append('g').attr('class', 'links')
    .selectAll('line')
    .data(links)
    .join('line')
    .attr('class', d => `edge edge-${d.id}`)
    .attr('stroke', '#2A2A2A')
    .attr('stroke-width', 1.5)
    .attr('stroke-opacity', 0.7)
    .attr('marker-end', 'url(#arrow)')

  // Node groups
  nodeSelection = g.append('g').attr('class', 'nodes')
    .selectAll('g')
    .data(nodes)
    .join('g')
    .attr('class', d => `node-group node-${d.id}`)
    .style('cursor', 'pointer')
    .call(d3.drag()
      .on('start', dragStarted)
      .on('drag', dragged)
      .on('end', dragEnded)
    )
    .on('mouseenter', (event, d) => {
      hoveredNode.value = d.id
      const rect = graphContainer.value.getBoundingClientRect()
      const x = event.clientX - rect.left + 12
      const y = event.clientY - rect.top - 8
      tooltipStyle.value = { left: x + 'px', top: y + 'px' }
      d3.select(`.node-${d.id} circle.main-circle`)
        .attr('filter', `drop-shadow(0 0 8px ${AGENT_COLORS[d.id]})`)
    })
    .on('mouseleave', (event, d) => {
      hoveredNode.value = null
      d3.select(`.node-${d.id} circle.main-circle`)
        .attr('filter', null)
    })
    .on('click', (event, d) => {
      selectedAgent.value = selectedAgent.value === d.id ? null : d.id
    })

  // Outer glow ring
  nodeSelection.append('circle')
    .attr('class', 'glow-ring')
    .attr('r', 34)
    .attr('fill', 'none')
    .attr('stroke', d => AGENT_COLORS[d.id])
    .attr('stroke-width', 0.5)
    .attr('stroke-opacity', 0.3)

  // Main circle
  nodeSelection.append('circle')
    .attr('class', 'main-circle')
    .attr('r', 26)
    .attr('fill', d => AGENT_COLORS[d.id])
    .attr('fill-opacity', 0.9)
    .attr('stroke', d => AGENT_COLORS[d.id])
    .attr('stroke-width', 2)
    .attr('stroke-opacity', 0.5)

  // Label
  nodeSelection.append('text')
    .attr('text-anchor', 'middle')
    .attr('dominant-baseline', 'central')
    .attr('fill', '#FFF')
    .attr('font-family', "'JetBrains Mono', monospace")
    .attr('font-size', '14px')
    .attr('font-weight', '700')
    .attr('pointer-events', 'none')
    .text(d => AGENT_LABELS[d.id])

  // Small role label below node
  nodeSelection.append('text')
    .attr('class', 'node-sublabel')
    .attr('text-anchor', 'middle')
    .attr('dominant-baseline', 'central')
    .attr('dy', 42)
    .attr('fill', '#666')
    .attr('font-family', "'JetBrains Mono', monospace")
    .attr('font-size', '9px')
    .attr('pointer-events', 'none')
    .text(d => AGENT_SHORT_NAMES[d.id])

  // Force simulation — nodes already pre-positioned, low alpha to avoid flying around
  simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id(d => d.id).distance(160).strength(0.25))
    .force('charge', d3.forceManyBody().strength(-500))
    .force('center', d3.forceCenter(W / 2, H / 2).strength(0.06))
    .force('collide', d3.forceCollide(58))
    .alpha(0.4)
    .alphaDecay(0.04)
    .on('tick', ticked)

  // Zoom
  const zoom = d3.zoom()
    .scaleExtent([0.5, 3])
    .on('zoom', (event) => g.attr('transform', event.transform))
  svgSelection.call(zoom)

  startIdleAnimation()
}

function ticked() {
  if (!linkSelection || !nodeSelection) return
  linkSelection
    .attr('x1', d => d.source.x)
    .attr('y1', d => d.source.y)
    .attr('x2', d => d.target.x)
    .attr('y2', d => d.target.y)

  nodeSelection.attr('transform', d => `translate(${d.x},${d.y})`)
}

function dragStarted(event, d) {
  if (!event.active) simulation.alphaTarget(0.3).restart()
  d.fx = d.x; d.fy = d.y
}
function dragged(event, d) {
  d.fx = event.x; d.fy = event.y
}
function dragEnded(event, d) {
  if (!event.active) simulation.alphaTarget(0)
  d.fx = null; d.fy = null
}

// Idle pulse animation on nodes
let idleAnimTimer = null
function startIdleAnimation() {
  let tick = 0
  idleAnimTimer = setInterval(() => {
    tick++
    svgSelection?.selectAll('.main-circle')
      .transition().duration(800).ease(d3.easeSinInOut)
      .attr('fill-opacity', 0.6 + 0.3 * Math.sin(tick * 0.8))
  }, 900)
}

function stopIdleAnimation() {
  clearInterval(idleAnimTimer)
  idleAnimTimer = null
  svgSelection?.selectAll('.main-circle').attr('fill-opacity', 0.9)
}

// Edge animation while debate is running
let edgeAnimTick = 0
function startEdgeAnimation() {
  stopIdleAnimation()
  const roles = Object.keys(AGENT_COLORS)
  edgeAnimInterval = setInterval(() => {
    edgeAnimTick++
    // Reset all edges
    svgSelection?.selectAll('.edge')
      .attr('stroke', '#2A2A2A')
      .attr('stroke-width', 1.5)
      .attr('stroke-opacity', 0.7)

    // Highlight a random edge with agent color
    const srcRole = roles[edgeAnimTick % roles.length]
    const color = AGENT_COLORS[srcRole]
    const relatedLinks = links.filter(l => {
      const sid = typeof l.source === 'object' ? l.source.id : l.source
      return sid === srcRole
    })
    if (relatedLinks.length) {
      const link = relatedLinks[edgeAnimTick % relatedLinks.length]
      const sid = typeof link.source === 'object' ? link.source.id : link.source
      const tid = typeof link.target === 'object' ? link.target.id : link.target
      svgSelection?.select(`.edge-${sid}--${tid}`)
        .attr('stroke', color)
        .attr('stroke-width', 3)
        .attr('stroke-opacity', 1)
    }

    // Ripple on a node
    const rippleRole = roles[(edgeAnimTick + 2) % roles.length]
    const nodeG = svgSelection?.select(`.node-${rippleRole}`)
    if (nodeG) {
      nodeG.append('circle')
        .attr('r', 28)
        .attr('fill', 'none')
        .attr('stroke', AGENT_COLORS[rippleRole])
        .attr('stroke-width', 2)
        .attr('stroke-opacity', 0.8)
        .transition().duration(800).ease(d3.easeExpOut)
        .attr('r', 55)
        .attr('stroke-opacity', 0)
        .remove()
    }
  }, 600)
}

function stopEdgeAnimation() {
  clearInterval(edgeAnimInterval)
  edgeAnimInterval = null
}

function updateGraphForResults() {
  if (!debateResults.value || !svgSelection) return
  stopIdleAnimation()
  stopEdgeAnimation()

  const rec = debateResults.value.final_recommendation?.recommendation
  const edgeColor = rec === 'BUY' ? '#16A34A' : rec === 'SELL' ? '#DC2626' : '#D97706'
  const conv = debateResults.value.final_recommendation?.consensus_conviction || 5
  const widthScale = d3.scaleLinear().domain([1, 10]).range([1, 6])

  // Color all edges by recommendation
  svgSelection.selectAll('.edge')
    .transition().duration(600)
    .attr('stroke', edgeColor)
    .attr('stroke-width', widthScale(conv))
    .attr('stroke-opacity', 0.6)

  // Glow on all nodes
  svgSelection.selectAll('.main-circle')
    .transition().duration(400)
    .attr('fill-opacity', 1)
}

function resetGraphToIdle() {
  if (!svgSelection) return
  svgSelection.selectAll('.edge')
    .attr('stroke', '#2A2A2A')
    .attr('stroke-width', 1.5)
    .attr('stroke-opacity', 0.7)
  svgSelection.selectAll('.main-circle')
    .attr('fill-opacity', 0.9)
  startIdleAnimation()
}

// Handle window resize — reinit graph with new dimensions
function onResize() {
  if (!graphContainer.value || !svgEl.value) return
  simulation?.stop()
  stopIdleAnimation()
  initGraph()
  if (state.value === 'running') startEdgeAnimation()
  else if (state.value === 'complete') updateGraphForResults()
  else startIdleAnimation()
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(() => {
  addLog('System initialized · BTRate v0.1', 'success')
  nextTick(() => {
    initGraph()
    window.addEventListener('resize', onResize)
  })
})

onUnmounted(() => {
  clearInterval(pollInterval)
  clearTimeout(pollTimeout)
  stopEdgeAnimation()
  stopIdleAnimation()
  simulation?.stop()
  window.removeEventListener('resize', onResize)
})

watch(state, (newState) => {
  if (newState === 'idle') {
    resetGraphToIdle()
  }
})
</script>

<style scoped>
/* ── Variables ── */
.debate-page {
  --black: #000000;
  --dark: #0A0A0A;
  --surface: #111111;
  --surface2: #1A1A1A;
  --border: #2A2A2A;
  --white: #FAFAFA;
  --gray: #888888;
  --orange: #FF4500;
  --blue: #2563EB;
  --purple: #7C3AED;
  --red: #DC2626;
  --gold: #D97706;
  --devil: #EA580C;
  --green: #16A34A;
  --font-mono: 'JetBrains Mono', monospace;
  --font-sans: 'Space Grotesk', system-ui, sans-serif;

  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--dark);
  color: var(--white);
  font-family: var(--font-sans);
  overflow: hidden;
}

/* ── Navbar ── */
.navbar {
  height: 52px;
  background: var(--black);
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 32px;
  flex-shrink: 0;
  z-index: 10;
}
.nav-brand {
  font-family: var(--font-mono);
  font-weight: 800;
  font-size: 1rem;
  letter-spacing: 2px;
  color: var(--white);
}
.nav-links { display: flex; align-items: center; gap: 20px; }
.back-link, .github-link {
  color: var(--gray);
  text-decoration: none;
  font-family: var(--font-mono);
  font-size: 0.8rem;
  transition: color 0.2s;
}
.back-link:hover { color: var(--orange); }
.github-link:hover { color: var(--white); }

/* ── Main Layout ── */
.main-layout {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* ── Graph Panel ── */
.graph-panel {
  flex: 0 0 55%;
  display: flex;
  flex-direction: column;
  background: var(--dark);
  border-right: 1px solid var(--border);
  position: relative;
}
.graph-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.graph-label {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: var(--gray);
  letter-spacing: 1px;
}
.graph-status {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  letter-spacing: 1px;
}
.status-idle { color: var(--gray); }
.status-running { color: var(--orange); animation: blink-status 1.2s step-end infinite; }
.status-complete { color: var(--green); }
.status-error { color: var(--red); }
@keyframes blink-status {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

#graph-container {
  flex: 1;
  position: relative;
  overflow: hidden;
}
#force-graph {
  width: 100%;
  height: 100%;
  display: block;
  background: var(--dark);
}

/* Node tooltip */
.node-tooltip {
  position: absolute;
  background: rgba(10,10,10,0.9);
  border: 1px solid var(--border);
  padding: 4px 10px;
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: var(--white);
  pointer-events: none;
  white-space: nowrap;
  z-index: 20;
  letter-spacing: 1px;
}

/* Node detail card */
.node-detail-card {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 240px;
  background: rgba(10,10,10,0.95);
  border: 1px solid var(--border);
  padding: 16px;
  z-index: 20;
}
.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.detail-title {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--white);
  letter-spacing: 1px;
  font-weight: 700;
}
.detail-close {
  background: none;
  border: none;
  color: var(--gray);
  cursor: pointer;
  font-size: 1.2rem;
  padding: 0;
  line-height: 1;
}
.detail-close:hover { color: var(--white); }
.detail-direction {
  font-family: var(--font-mono);
  font-size: 1.1rem;
  font-weight: 700;
  margin-bottom: 4px;
}
.detail-direction.buy { color: var(--green); }
.detail-direction.sell { color: var(--red); }
.detail-direction.hold { color: var(--gold); }
.detail-conviction {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: var(--gray);
  margin-bottom: 12px;
}
.detail-section { margin-bottom: 10px; }
.detail-section-title {
  font-family: var(--font-mono);
  font-size: 0.65rem;
  color: #555;
  letter-spacing: 1px;
  margin-bottom: 6px;
}
.detail-bullet {
  font-size: 0.78rem;
  color: #aaa;
  line-height: 1.5;
  margin-bottom: 4px;
}
.detail-bullet.risk { color: var(--red); opacity: 0.85; }

/* Legend */
.graph-legend {
  display: flex;
  gap: 16px;
  padding: 8px 16px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
  flex-wrap: wrap;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 5px;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--gray);
}
.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

/* ── Right Panel ── */
.right-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--dark);
}

/* ── Input Panel ── */
.input-panel {
  padding: 32px 28px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  height: 100%;
  box-sizing: border-box;
  overflow-y: auto;
}
.panel-title-row { display: flex; align-items: center; gap: 12px; }
.panel-badge {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: var(--orange);
  border: 1px solid var(--orange);
  padding: 3px 10px;
  letter-spacing: 1px;
}
.input-group { display: flex; flex-direction: column; gap: 8px; }
.input-label {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: #555;
  letter-spacing: 1px;
}
.label-meta {
  margin-left: 8px;
  color: #444;
}
.input-textarea {
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--white);
  padding: 14px 16px;
  font-family: var(--font-mono);
  font-size: 0.88rem;
  line-height: 1.6;
  resize: vertical;
  outline: none;
  transition: border-color 0.2s;
  border-radius: 0;
}
.input-textarea::placeholder { color: #444; }
.input-textarea:focus { border-color: var(--orange); }
.doc-textarea { font-size: 0.82rem; }

.clear-file-btn {
  background: none;
  border: none;
  color: var(--red);
  cursor: pointer;
  font-size: 0.9rem;
  padding: 0 4px;
  margin-left: 6px;
  vertical-align: middle;
}
.clear-file-btn:hover { opacity: 0.7; }

.file-drop-zone {
  background: var(--surface);
  border: 1px dashed var(--border);
  padding: 24px 16px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}
.file-drop-zone:hover, .file-drop-zone.drag-over {
  background: var(--surface2);
  border-color: var(--orange);
}
.file-drop-zone.has-file { border-color: var(--green); border-style: solid; }
.drop-text {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: #555;
}
.file-name { color: var(--green); }
.hidden-input { display: none; }
.or-divider {
  text-align: center;
  margin: 8px 0;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: #444;
  letter-spacing: 0.1em;
}
.doc-textarea {
  min-height: 80px;
  font-size: 0.78rem;
}
.doc-textarea:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.start-btn {
  width: 100%;
  background: var(--orange);
  color: #fff;
  border: none;
  padding: 18px 24px;
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 1rem;
  letter-spacing: 2px;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  transition: background 0.2s, transform 0.1s;
  margin-top: 8px;
}
.start-btn:hover:not(:disabled) { background: #CC3700; }
.start-btn:active:not(:disabled) { transform: translateY(1px); }
.start-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-arrow { font-size: 1.2rem; }

/* ── Running Panel ── */
.running-panel {
  padding: 32px 28px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  height: 100%;
  box-sizing: border-box;
}
.running-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.running-title {
  font-family: var(--font-mono);
  font-size: 1rem;
  font-weight: 700;
  letter-spacing: 2px;
  color: var(--orange);
}
.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border);
  border-top-color: var(--orange);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.progress-bar-track {
  height: 3px;
  background: var(--surface2);
  position: relative;
  overflow: hidden;
}
.progress-bar-fill {
  height: 100%;
  background: var(--orange);
  transition: width 0.4s ease;
  box-shadow: 0 0 8px var(--orange);
}
.round-indicators {
  display: flex;
  gap: 10px;
}
.round-badge {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  padding: 5px 14px;
  border: 1px solid var(--border);
  color: #444;
  letter-spacing: 1px;
  transition: all 0.3s;
}
.round-badge.active {
  border-color: var(--orange);
  color: var(--orange);
  background: rgba(255,69,0,0.08);
}
.running-desc {
  font-family: var(--font-mono);
  font-size: 0.78rem;
  color: #555;
  line-height: 1.6;
}
.agent-activity {
  display: flex;
  flex-direction: column;
  gap: 12px;
  border: 1px solid var(--border);
  padding: 20px;
}
.activity-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.activity-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  opacity: 0.5;
  transition: opacity 0.3s;
}
.activity-dot.pulse {
  opacity: 1;
  animation: dot-pulse 0.8s ease-in-out infinite;
}
@keyframes dot-pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.5); box-shadow: 0 0 6px currentColor; }
}
.activity-name {
  font-family: var(--font-mono);
  font-size: 0.78rem;
  color: var(--white);
  flex: 1;
  letter-spacing: 0.5px;
}
.activity-status {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: #555;
}

/* ── Results Panel ── */
.results-panel {
  flex: 1;
  overflow: hidden;
}
.results-scroll {
  height: 100%;
  overflow-y: auto;
  padding: 24px 28px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  box-sizing: border-box;
}
.results-scroll::-webkit-scrollbar { width: 4px; }
.results-scroll::-webkit-scrollbar-track { background: transparent; }
.results-scroll::-webkit-scrollbar-thumb { background: var(--border); }

.recommendation-block {
  border: 1px solid var(--border);
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.rec-badge {
  font-family: var(--font-mono);
  font-size: 2rem;
  font-weight: 700;
  letter-spacing: 4px;
  padding: 10px 24px;
  display: inline-block;
  align-self: flex-start;
}
.rec-badge.buy { background: var(--green); color: #fff; }
.rec-badge.sell { background: var(--red); color: #fff; }
.rec-badge.hold { background: var(--gold); color: #fff; }

.rec-scores {
  display: flex;
  gap: 0;
  border: 1px solid var(--border);
}
.score-item {
  flex: 1;
  padding: 14px 16px;
  text-align: center;
}
.score-divider {
  width: 1px;
  background: var(--border);
}
.score-value {
  font-family: var(--font-mono);
  font-size: 1.4rem;
  font-weight: 700;
  color: var(--white);
  margin-bottom: 4px;
}
.score-label {
  font-family: var(--font-mono);
  font-size: 0.65rem;
  color: #555;
  letter-spacing: 1px;
}

.results-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.section-header {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: #555;
  letter-spacing: 2px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 8px;
}
.thesis-text {
  font-size: 0.9rem;
  color: #bbb;
  line-height: 1.7;
  margin: 0;
}

/* Confidence bars */
.confidence-bars { display: flex; flex-direction: column; gap: 10px; }
.conf-row { display: flex; align-items: center; gap: 10px; }
.conf-label {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  font-weight: 700;
  width: 38px;
  flex-shrink: 0;
}
.conf-label.buy { color: var(--green); }
.conf-label.sell { color: var(--red); }
.conf-label.hold { color: var(--gold); }
.conf-track {
  flex: 1;
  height: 6px;
  background: var(--surface2);
  overflow: hidden;
}
.conf-fill {
  height: 100%;
  transition: width 0.6s ease;
}
.conf-fill.buy { background: var(--green); }
.conf-fill.sell { background: var(--red); }
.conf-fill.hold { background: var(--gold); }
.conf-pct {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: var(--gray);
  width: 32px;
  text-align: right;
}

/* Round tabs */
.round-tabs { display: flex; gap: 6px; }
.round-tab {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  padding: 5px 14px;
  background: none;
  border: 1px solid var(--border);
  color: #555;
  cursor: pointer;
  transition: all 0.2s;
  letter-spacing: 1px;
}
.round-tab:hover { border-color: var(--gray); color: var(--gray); }
.round-tab.active { border-color: var(--orange); color: var(--orange); background: rgba(255,69,0,0.08); }

/* Agent cards */
.agent-cards { display: flex; flex-direction: column; gap: 10px; }
.agent-card {
  background: #0D0D0D;
  border: 1px solid var(--border);
  border-left-width: 3px;
  padding: 14px 16px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.card-agent-info { display: flex; align-items: center; gap: 10px; }
.card-label {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-mono);
  font-size: 0.72rem;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
}
.card-role {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--white);
  letter-spacing: 0.5px;
}
.card-verdict { display: flex; align-items: center; gap: 8px; }
.card-direction {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  font-weight: 700;
  padding: 2px 8px;
}
.card-direction.buy { color: var(--green); border: 1px solid var(--green); }
.card-direction.sell { color: var(--red); border: 1px solid var(--red); }
.card-direction.hold { color: var(--gold); border: 1px solid var(--gold); }
.card-conviction {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: var(--gray);
}
.card-body { display: flex; flex-direction: column; gap: 8px; }
.card-section { display: flex; flex-direction: column; gap: 4px; }
.card-section-title {
  font-family: var(--font-mono);
  font-size: 0.65rem;
  color: #444;
  letter-spacing: 1px;
}
.risk-title { color: rgba(220,38,38,0.6); }
.card-bullet {
  font-size: 0.8rem;
  color: #888;
  line-height: 1.5;
}
.risk-bullet { color: rgba(220,38,38,0.8); }
.challenge-target {
  color: #666;
  font-size: 0.72rem;
  margin-top: 4px;
  font-family: var(--font-mono);
}
.challenge-item { color: #777; padding-left: 8px; }
.card-rebuttal-toggle {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: #555;
  cursor: pointer;
  margin-top: 4px;
  transition: color 0.2s;
}
.card-rebuttal-toggle:hover { color: var(--gray); }
.card-rebuttal {
  font-size: 0.8rem;
  color: #666;
  line-height: 1.6;
  border-top: 1px solid var(--border);
  padding-top: 8px;
  margin-top: 4px;
}

/* Risk items */
.risk-item {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}
.risk-num {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: #444;
  flex-shrink: 0;
  margin-top: 2px;
}
.risk-text {
  font-size: 0.85rem;
  color: #888;
  line-height: 1.6;
}

.new-debate-btn {
  width: 100%;
  background: none;
  border: 1px solid var(--border);
  color: var(--gray);
  padding: 14px;
  font-family: var(--font-mono);
  font-size: 0.85rem;
  cursor: pointer;
  letter-spacing: 1px;
  transition: all 0.2s;
  margin-top: 8px;
}
.new-debate-btn:hover {
  border-color: var(--orange);
  color: var(--orange);
  background: rgba(255,69,0,0.05);
}

/* ── Error Panel ── */
.error-panel {
  padding: 48px 28px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  text-align: center;
}
.error-icon {
  font-size: 2rem;
  color: var(--red);
}
.error-title {
  font-family: var(--font-mono);
  font-size: 1rem;
  color: var(--red);
  letter-spacing: 2px;
}
.error-msg {
  font-family: var(--font-mono);
  font-size: 0.82rem;
  color: #555;
  line-height: 1.6;
  max-width: 340px;
}

/* ── System Dashboard Strip ── */
.dashboard-strip {
  height: 88px;
  background: #050505;
  border-top: 1px solid #1A1A1A;
  display: flex;
  align-items: center;
  padding: 0 16px;
  gap: 16px;
  flex-shrink: 0;
}
.strip-left, .strip-right {
  flex-shrink: 0;
}
.strip-label {
  font-family: var(--font-mono);
  font-size: 0.62rem;
  color: #333;
  letter-spacing: 2px;
  writing-mode: horizontal-tb;
}
.strip-session {
  font-family: var(--font-mono);
  font-size: 0.62rem;
  color: #333;
  letter-spacing: 1px;
}
.strip-logs {
  flex: 1;
  overflow-x: auto;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 80px;
  scrollbar-width: thin;
  scrollbar-color: #222 transparent;
}
.strip-logs::-webkit-scrollbar { height: 3px; width: 3px; }
.strip-logs::-webkit-scrollbar-thumb { background: #222; }

.log-line {
  display: flex;
  gap: 10px;
  align-items: baseline;
  white-space: nowrap;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  line-height: 1.5;
}
.log-time { color: #444; flex-shrink: 0; }
.log-sym { flex-shrink: 0; }
.log-msg { color: #666; }
.log-sym.success, .log-msg.success { color: #16A34A; }
.log-sym.warn, .log-msg.warn { color: #D97706; }
.log-sym.error, .log-msg.error { color: #DC2626; }

/* ── Responsive ── */
@media (max-width: 900px) {
  .main-layout { flex-direction: column; }
  .graph-panel {
    flex: 0 0 40vh;
    border-right: none;
    border-bottom: 1px solid var(--border);
  }
  .dashboard-strip { display: none; }
}
</style>
