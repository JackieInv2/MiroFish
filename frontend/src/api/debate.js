import service, { requestWithRetry } from './index'

/**
 * Start a new investment debate
 * @param {FormData|Object} data - FormData with file+question, or {text, question}
 * @returns {Promise}
 */
export function startDebate(data) {
  const isFormData = data instanceof FormData
  return requestWithRetry(() =>
    service({
      url: '/api/debate/start',
      method: 'post',
      data,
      headers: isFormData ? { 'Content-Type': 'multipart/form-data' } : {},
    })
  )
}

/**
 * Get debate status
 * @param {string} debateId
 * @returns {Promise}
 */
export function getDebateStatus(debateId) {
  return service({ url: `/api/debate/${debateId}/status`, method: 'get' })
}

/**
 * Get full debate result
 * @param {string} debateId
 * @returns {Promise}
 */
export function getDebateResult(debateId) {
  return service({ url: `/api/debate/${debateId}/result`, method: 'get' })
}

/**
 * Get a specific debate round
 * @param {string} debateId
 * @param {number} roundNumber
 * @returns {Promise}
 */
export function getDebateRound(debateId, roundNumber) {
  return service({ url: `/api/debate/${debateId}/rounds/${roundNumber}`, method: 'get' })
}

/**
 * List all debates
 * @returns {Promise}
 */
export function listDebates() {
  return service({ url: '/api/debate/list', method: 'get' })
}
