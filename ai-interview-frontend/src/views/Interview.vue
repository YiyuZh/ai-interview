<template>
  <div class="interview-page">
    <div v-if="preparing" class="prepare-overlay">
      <div class="prepare-card">
        <div class="ai-face-large">
          <svg viewBox="0 0 80 80" width="80" height="80">
            <circle cx="40" cy="40" r="38" fill="white" stroke="#4f46e5" stroke-width="2" />
            <ellipse cx="28" cy="36" rx="5" ry="6" fill="#1e1e1e">
              <animate attributeName="ry" values="6;1;6" dur="2.5s" repeatCount="indefinite" />
            </ellipse>
            <ellipse cx="52" cy="36" rx="5" ry="6" fill="#1e1e1e">
              <animate attributeName="ry" values="6;1;6" dur="2.5s" repeatCount="indefinite" />
            </ellipse>
            <path d="M30 52 Q40 60 50 52" stroke="#1e1e1e" stroke-width="2" fill="none" stroke-linecap="round" />
          </svg>
        </div>
        <h2 class="prepare-title">面试即将开始</h2>
        <p class="prepare-tip">{{ prepareTip }}</p>
        <div class="prepare-progress">
          <div class="prepare-bar" :style="{ width: `${preparePercent}%` }"></div>
        </div>
        <p class="prepare-subtitle">AI 正在为你准备面试题目...</p>
      </div>
    </div>

    <div v-if="!preparing" class="interview-header">
      <div class="header-brand">
        <svg viewBox="0 0 32 32" width="24" height="24">
          <circle cx="16" cy="16" r="15" fill="white" stroke="#4f46e5" stroke-width="1.5" />
          <ellipse cx="11" cy="14" rx="2.5" ry="3" fill="#1e1e1e" />
          <ellipse cx="21" cy="14" rx="2.5" ry="3" fill="#1e1e1e" />
        </svg>
        <span>AI 面试官</span>
      </div>
      <span class="progress">第 {{ currentIndex + 1 }} / {{ totalQuestions }} 题</span>
      <router-link
        to="/dashboard"
        class="btn-secondary"
        style="padding:4px 12px;font-size:12px;border-radius:6px;display:inline-block"
      >
        退出
      </router-link>
    </div>

    <div v-if="!preparing && isPanelMode" class="panel-status-card">
      <div class="panel-status-top">
        <div>
          <strong>当前模式：多面试官协同</strong>
          <p class="panel-status-note">
            对外仍然是单主持人提问；内部会综合多个训练视角做选题、追问和评估。
          </p>
        </div>
        <span class="panel-status-chip">内部协同中</span>
      </div>
      <div class="panel-role-tags">
        <span v-for="item in panelRoleHints" :key="item" class="panel-role-tag">{{ item }}</span>
      </div>
      <details v-if="latestRoundSummary" class="round-summary">
        <summary>最近一轮内部评估</summary>
        <p v-if="latestRoundSummary.feedback" class="round-summary-feedback">
          {{ latestRoundSummary.feedback }}
        </p>
        <ul v-if="latestRoundSummary.points.length" class="round-summary-list">
          <li v-for="(item, index) in latestRoundSummary.points" :key="`${item}-${index}`">{{ item }}</li>
        </ul>
      </details>
    </div>

    <div v-if="!preparing" ref="chatArea" class="chat-area">
      <div v-for="(msg, i) in messages" :key="i" :class="['message', msg.role]">
        <div v-if="msg.role === 'interviewer'" class="avatar-col">
          <svg viewBox="0 0 40 40" width="36" height="36" class="ai-avatar">
            <circle cx="20" cy="20" r="19" fill="white" stroke="#e5e7eb" stroke-width="1" />
            <ellipse cx="14" cy="17" rx="2.5" ry="3" fill="#1e1e1e" />
            <ellipse cx="26" cy="17" rx="2.5" ry="3" fill="#1e1e1e" />
          </svg>
        </div>

        <div class="bubble">
          <div class="bubble-content" v-html="renderContent(msg.content)"></div>
          <div v-if="msg.score" class="bubble-score">评分 {{ msg.score }}/10</div>
        </div>

        <div v-if="msg.role === 'candidate'" class="avatar-col">
          <img
            v-if="userAvatar && !avatarError"
            :src="userAvatar"
            class="user-avatar"
            alt="me"
            @error="avatarError = true"
          />
          <div v-else class="user-avatar-placeholder">{{ userInitial }}</div>
        </div>
      </div>

      <div v-if="streamingText" class="message interviewer">
        <div class="avatar-col">
          <svg viewBox="0 0 40 40" width="36" height="36" class="ai-avatar thinking">
            <circle cx="20" cy="20" r="19" fill="white" stroke="#4f46e5" stroke-width="1.5" />
            <ellipse cx="14" cy="17" rx="2.5" ry="3" fill="#1e1e1e">
              <animate attributeName="ry" values="3;1;3" dur="1.5s" repeatCount="indefinite" />
            </ellipse>
            <ellipse cx="26" cy="17" rx="2.5" ry="3" fill="#1e1e1e">
              <animate attributeName="ry" values="3;1;3" dur="1.5s" repeatCount="indefinite" />
            </ellipse>
          </svg>
        </div>
        <div class="bubble">
          <div class="bubble-content streaming-content" v-html="renderContent(streamingText)"></div>
          <span class="cursor-blink">▌</span>
        </div>
      </div>

      <div v-if="thinking && !streamingText" class="message interviewer">
        <div class="avatar-col">
          <svg viewBox="0 0 40 40" width="36" height="36" class="ai-avatar thinking">
            <circle cx="20" cy="20" r="19" fill="white" stroke="#4f46e5" stroke-width="1.5" />
            <ellipse cx="14" cy="17" rx="2.5" ry="3" fill="#1e1e1e">
              <animate attributeName="ry" values="3;1;3" dur="1s" repeatCount="indefinite" />
            </ellipse>
            <ellipse cx="26" cy="17" rx="2.5" ry="3" fill="#1e1e1e">
              <animate attributeName="ry" values="3;1;3" dur="1s" repeatCount="indefinite" />
            </ellipse>
          </svg>
        </div>
        <div class="bubble thinking-bubble">
          <span class="dot-animation">AI 思考中<span class="dots"></span></span>
        </div>
      </div>
    </div>

    <div v-if="!preparing && !finished" class="input-area">
      <textarea
        v-model="answer"
        placeholder="输入你的回答..."
        rows="3"
        :disabled="thinking"
        @keydown.enter.exact.prevent="handleSubmit"
        @keydown.shift.enter.exact="null"
      ></textarea>
      <button class="btn-primary" :disabled="!answer.trim() || thinking" @click="handleSubmit">
        {{ thinking ? '评估中...' : '发送 (Enter)' }}
      </button>
    </div>

    <div v-if="!preparing && finished" class="input-area finished">
      <p>面试已结束</p>
      <router-link
        :to="`/interview/${interviewId}/report`"
        class="btn-primary"
        style="display:inline-block;padding:10px 24px;color:white;border-radius:8px"
      >
        查看评估报告
      </router-link>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { getMessages, submitAnswerStream } from '../api/interview'

const route = useRoute()
const authStore = useAuthStore()
const interviewId = route.params.id

const messages = ref([])
const answer = ref('')
const thinking = ref(false)
const finished = ref(false)
const currentIndex = ref(0)
const totalQuestions = ref(5)
const chatArea = ref(null)
const streamingText = ref('')
const latestRoundSummary = ref(null)
const interviewMeta = ref(null)
const panelRoleHints = ['技术深挖', '项目追问', '业务场景', '表达结构', '压力质询']

const preparing = ref(true)
const preparePercent = ref(0)
const prepareTips = [
  '请做好准备，保持冷静和自信',
  '回答时尽量结合你的项目经验',
  '注意条理清晰，分点作答',
  '面试官会根据你的简历继续追问'
]
const prepareTip = ref(prepareTips[0])

const userAvatar = computed(() => authStore.userAvatar || '')
const avatarError = ref(false)
const userInitial = computed(() => {
  const name = authStore.userName || ''
  return name.charAt(0).toUpperCase() || '我'
})
const interviewMode = computed(() => interviewMeta.value?.interviewMode || route.query.mode || 'single')
const isPanelMode = computed(() => interviewMode.value === 'panel')

function loadInterviewMeta() {
  const storageKey = `interview_meta_${interviewId}`
  let storedMeta = null
  try {
    storedMeta = JSON.parse(sessionStorage.getItem(storageKey) || 'null')
  } catch (e) {
    storedMeta = null
  }

  const queryMode = typeof route.query.mode === 'string' ? route.query.mode : ''
  const queryTotal = Number(route.query.total || 0)
  interviewMeta.value = {
    ...(storedMeta || {}),
    interviewMode: queryMode || storedMeta?.interviewMode || 'single',
    totalQuestions: queryTotal || storedMeta?.totalQuestions || totalQuestions.value
  }

  if (interviewMeta.value.totalQuestions) {
    totalQuestions.value = Number(interviewMeta.value.totalQuestions)
  }
}

function normalizeRoundSummary(data) {
  if (!data || !isPanelMode.value) return null

  const moderator = data.moderator || {}
  const metadata = data.metadata || {}
  const panelViews = Array.isArray(data.panel_views) ? data.panel_views : []
  const followups = moderator.selected_followups || data.selected_followups || []
  const sliceIds = metadata.retrieved_slice_ids || data.used_slice_ids || []
  const points = []

  panelViews.slice(0, 3).forEach(item => {
    if (!item || typeof item !== 'object' || !item.summary) return
    points.push(`${item.title || item.role || '协同视角'}：${item.summary}`)
  })

  if (followups.length) {
    points.push(`建议追问：${followups.slice(0, 2).join('；')}`)
  }
  if (sliceIds.length) {
    points.push(`参考切片：#${sliceIds.slice(0, 4).join(' / #')}`)
  }
  if (!points.length) {
    points.push('本轮回答已完成多视角内部评估，结果会汇总到最终报告。')
  }

  return {
    feedback: data.feedback || moderator.reasoning_summary || '',
    points
  }
}

function renderContent(text) {
  if (!text) return ''
  const cleaned = String(text)
    .replace(/```json\s*\{[\s\S]*?\}\s*```/g, '')
    .replace(/\{[^{}]*"score"\s*:\s*[\d.]+[^{}]*\}/g, '')
    .trim()
  return cleaned.replace(/\n/g, '<br>')
}

function scrollToBottom() {
  nextTick(() => {
    if (chatArea.value) {
      chatArea.value.scrollTop = chatArea.value.scrollHeight
    }
  })
}

onMounted(async () => {
  loadInterviewMeta()

  let tipIdx = 0
  const tipTimer = setInterval(() => {
    tipIdx = (tipIdx + 1) % prepareTips.length
    prepareTip.value = prepareTips[tipIdx]
  }, 1500)

  const barTimer = setInterval(() => {
    if (preparePercent.value < 90) preparePercent.value += 2
  }, 100)

  try {
    const data = await getMessages(interviewId)
    const msgList = Array.isArray(data) ? data : (data.items || data)
    messages.value = msgList.map(item => ({
      role: item.role,
      content: item.content,
      score: item.score,
      feedback: item.feedback
    }))
    const indices = msgList.map(item => item.question_index).filter(index => index != null)
    if (indices.length) {
      currentIndex.value = Math.max(...indices)
    }
  } catch (e) {
    console.error('加载消息失败:', e)
  }

  preparePercent.value = 100
  clearInterval(barTimer)
  clearInterval(tipTimer)
  setTimeout(() => {
    preparing.value = false
  }, 600)
  nextTick(scrollToBottom)
})

async function handleSubmit() {
  if (!answer.value.trim() || thinking.value) return

  const myAnswer = answer.value.trim()
  answer.value = ''
  messages.value.push({ role: 'candidate', content: myAnswer })
  scrollToBottom()
  thinking.value = true
  streamingText.value = ''
  let rawStreamText = ''

  try {
    await submitAnswerStream(
      interviewId,
      myAnswer,
      chunk => {
        rawStreamText += chunk
        let display = rawStreamText
          .replace(/```json\s*\{[\s\S]*?\}\s*```/g, '')
          .replace(/\{[^{}]*"score"\s*:\s*[\d.]+[^{}]*\}/g, '')
        display = display.replace(/```json[\s\S]*$/g, '')
        display = display.replace(/\{[^}]*$/g, match => {
          return /["']?score/.test(match) || /^\{\s*$/.test(match) ? '' : match
        })
        streamingText.value = display.trim()
        scrollToBottom()
      },
      data => {
        latestRoundSummary.value = normalizeRoundSummary(data)

        if (rawStreamText.trim()) {
          const displayText = rawStreamText
            .replace(/```json\s*\{[\s\S]*?\}\s*```/g, '')
            .replace(/\{[^{}]*"score"\s*:\s*[\d.]+[^{}]*\}/g, '')
            .trim()
          if (displayText) {
            messages.value.push({ role: 'interviewer', content: displayText, score: data.score })
          }
        }

        streamingText.value = ''
        rawStreamText = ''

        const lastCandidate = [...messages.value].reverse().find(item => item.role === 'candidate')
        if (lastCandidate) {
          lastCandidate.score = data.score
        }

        if (data.is_finished) {
          finished.value = true
        } else if (data.next_question) {
          currentIndex.value = data.question_index + 1
          messages.value.push({ role: 'interviewer', content: data.next_question })
        }
        scrollToBottom()
      }
    )
  } catch (e) {
    streamingText.value = ''
    messages.value.push({ role: 'interviewer', content: `出错了：${e.message}` })
    scrollToBottom()
  } finally {
    thinking.value = false
  }
}
</script>

<style scoped>
.interview-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  max-width: 800px;
  margin: 0 auto;
}

.prepare-overlay {
  position: fixed;
  inset: 0;
  background: #f5f7fa;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}

.prepare-card {
  text-align: center;
  padding: 40px;
}

.ai-face-large {
  animation: faceFloat 2s ease-in-out infinite;
}

@keyframes faceFloat {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-8px);
  }
}

.prepare-title {
  margin-top: 20px;
  font-size: 20px;
}

.prepare-tip {
  color: #6b7280;
  margin-top: 8px;
  font-size: 14px;
}

.prepare-subtitle {
  color: #9ca3af;
  font-size: 12px;
  margin-top: 8px;
}

.prepare-progress {
  width: 280px;
  height: 6px;
  background: #e5e7eb;
  border-radius: 3px;
  margin: 16px auto 0;
  overflow: hidden;
}

.prepare-bar {
  height: 100%;
  background: linear-gradient(90deg, #4f46e5, #7c3aed);
  border-radius: 3px;
  transition: width 0.3s ease;
}

.interview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  background: white;
  border-bottom: 1px solid #e5e7eb;
  font-size: 14px;
  font-weight: 600;
}

.header-brand {
  display: flex;
  align-items: center;
  gap: 8px;
}

.progress {
  color: #6b7280;
  font-weight: 400;
}

.panel-status-card {
  margin: 16px 20px 0;
  padding: 14px 16px;
  border-radius: 14px;
  background: linear-gradient(135deg, rgba(79, 70, 229, 0.08), rgba(16, 185, 129, 0.08));
  border: 1px solid rgba(79, 70, 229, 0.1);
}

.panel-status-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.panel-status-note {
  margin-top: 6px;
  font-size: 13px;
  line-height: 1.7;
  color: #4b5563;
}

.panel-status-chip {
  flex-shrink: 0;
  padding: 4px 10px;
  border-radius: 999px;
  background: #eef2ff;
  color: #4338ca;
  font-size: 12px;
  font-weight: 600;
}

.panel-role-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.panel-role-tag {
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(79, 70, 229, 0.08);
  color: #374151;
  font-size: 12px;
}

.round-summary {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(79, 70, 229, 0.08);
}

.round-summary summary {
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  color: #312e81;
}

.round-summary-feedback {
  margin-top: 10px;
  font-size: 13px;
  line-height: 1.7;
  color: #374151;
}

.round-summary-list {
  list-style: none;
  padding: 0;
  margin: 10px 0 0;
}

.round-summary-list li {
  position: relative;
  padding-left: 14px;
  margin-bottom: 6px;
  font-size: 13px;
  line-height: 1.7;
  color: #4b5563;
}

.round-summary-list li::before {
  content: '•';
  position: absolute;
  left: 0;
  color: #6d28d9;
}

.chat-area {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.message {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.message.interviewer {
  justify-content: flex-start;
}

.message.candidate {
  justify-content: flex-end;
}

.avatar-col {
  flex-shrink: 0;
  margin-top: 2px;
}

.ai-avatar {
  border-radius: 50%;
  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.1));
}

.ai-avatar.thinking {
  animation: avatarPulse 1.5s ease-in-out infinite;
}

@keyframes avatarPulse {
  0%,
  100% {
    filter: drop-shadow(0 0 0 rgba(79, 70, 229, 0));
  }
  50% {
    filter: drop-shadow(0 0 8px rgba(79, 70, 229, 0.4));
  }
}

.user-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  object-fit: cover;
}

.user-avatar-placeholder {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #4f46e5, #7c3aed);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
}

.bubble {
  max-width: 70%;
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
}

.interviewer .bubble {
  background: white;
  border: 1px solid #e5e7eb;
  border-bottom-left-radius: 4px;
}

.candidate .bubble {
  background: #4f46e5;
  color: white;
  border-bottom-right-radius: 4px;
}

.thinking-bubble {
  color: #6b7280;
  font-style: italic;
}

.dot-animation .dots::after {
  content: '';
  animation: dots 1.5s steps(4, end) infinite;
}

@keyframes dots {
  0% {
    content: '';
  }
  25% {
    content: '.';
  }
  50% {
    content: '..';
  }
  75% {
    content: '...';
  }
  100% {
    content: '';
  }
}

.streaming-content {
  display: inline;
}

.cursor-blink {
  display: inline;
  animation: blink 0.8s step-end infinite;
  color: #4f46e5;
  font-size: 14px;
}

@keyframes blink {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0;
  }
}

.bubble-score {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.2);
  font-size: 13px;
}

.interviewer .bubble-score {
  border-top-color: #e5e7eb;
}

.input-area {
  padding: 16px 20px;
  background: white;
  border-top: 1px solid #e5e7eb;
  display: flex;
  gap: 12px;
  align-items: flex-end;
}

.input-area textarea {
  flex: 1;
  resize: none;
  font-family: inherit;
}

.input-area.finished {
  justify-content: center;
  align-items: center;
  padding: 24px;
  gap: 16px;
}

.input-area.finished p {
  font-size: 18px;
  font-weight: 600;
}

@media (max-width: 768px) {
  .interview-header {
    gap: 10px;
    flex-wrap: wrap;
  }

  .panel-status-top {
    flex-direction: column;
  }

  .bubble {
    max-width: 82%;
  }

  .input-area {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
