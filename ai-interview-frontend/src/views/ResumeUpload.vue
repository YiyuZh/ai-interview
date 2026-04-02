<template>
  <div class="container">
    <div class="card" style="max-width:600px;margin:40px auto">
      <h2 style="margin-bottom:20px">📄 上传简历 & 开始面试</h2>

      <!-- Step 1: 上传简历 -->
      <div v-if="step === 1">
        <div class="form-group">
          <label>上传简历 (PDF)</label>
          <div class="upload-area" @click="$refs.fileInput.click()" @dragover.prevent @drop.prevent="onDrop">
            <input ref="fileInput" type="file" accept=".pdf" @change="onFileChange" hidden />
            <p v-if="!file" style="color:#6b7280">点击或拖拽上传 PDF 简历</p>
            <p v-else>📎 {{ file.name }}</p>
          </div>
        </div>
        <div class="form-group">
          <label>目标岗位</label>
          <input v-model="targetPosition" placeholder="例如：Python后端开发工程师" />
        </div>
        <div class="card api-test-card" style="margin-bottom:16px">
          <div class="api-test-head">
            <div>
              <h3 style="margin-bottom:8px">AI 连接测试</h3>
              <p class="api-test-desc">
                开始解析前，你可以先测试当前账号的 AI API 是否可用。这里支持切换服务商和模型做连通性验证，但不会修改个人中心里已保存的默认配置。
              </p>
            </div>
          </div>
          <div class="form-row compact-form-row">
            <div class="form-group">
              <label>服务商</label>
              <select v-model="aiTestProvider" @change="handleAiProviderChange">
                <option v-for="option in aiProviderOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
            </div>
            <div class="form-group">
              <label>测试模型</label>
              <input
                v-model="aiTestModel"
                :placeholder="aiTestModelPlaceholder"
                :list="aiModelDatalistId"
              />
              <datalist :id="aiModelDatalistId">
                <option
                  v-for="option in activeAiModelOptions"
                  :key="option.value"
                  :value="option.value"
                >
                  {{ option.label }}
                </option>
              </datalist>
            </div>
          </div>
          <div class="api-test-actions">
            <button
              class="btn-secondary"
              @click="handleTestAiConnection"
              :disabled="testingAiConnection || uploading || starting"
            >
              {{ testingAiConnection ? '测试中...' : `测试 ${activeAiProviderLabel} 连接` }}
            </button>
            <p v-if="aiTestMessage" :class="aiTestSuccess ? 'success-msg inline-msg' : 'error inline-msg'">
              {{ aiTestMessage }}
            </p>
          </div>
          <p class="api-test-usage-note">
            当前这里选中的服务商和模型，会用于这一次简历解析；只是不修改你个人中心里保存的默认配置。
          </p>
        </div>
        <p v-if="error" class="error">{{ error }}</p>
        <button class="btn-primary" style="width:100%" @click="handleUpload" :disabled="!file || uploading">
          {{ uploading ? '上传中...' : '上传并解析简历' }}
        </button>
      </div>

      <!-- Step 1.5: 解析动画 -->
      <div v-if="step === 'parsing'" class="parsing-stage">
        <div class="parsing-icon">🔍</div>
        <h3>{{ parsingTitle }}</h3>
        <div class="progress-bar-wrapper">
          <div class="progress-bar" :style="{ width: progress + '%' }"></div>
        </div>
        <p class="progress-text">{{ progress }}%</p>
        <div class="tips-area">
          <transition name="tip-fade" mode="out-in">
            <p class="tip-text" :key="currentTip">💡 {{ currentTip }}</p>
          </transition>
        </div>
      </div>

      <!-- Step 2: 解析结果 + 简历分析 + 面试配置 -->
      <div v-if="step === 2">
        <div class="parsed-info card" style="background:#f9fafb;margin-bottom:20px">
          <h3 style="margin-bottom:12px">✅ 简历解析完成</h3>
          <div v-if="parsedContent">
            <p v-if="parsedContent.name"><strong>姓名：</strong>{{ parsedContent.name }}</p>
            <p v-if="parsedContent.education"><strong>学历：</strong>{{ parsedContent.education }}</p>
            <p v-if="parsedContent.skills?.length"><strong>技能：</strong>{{ parsedContent.skills.join('、') }}</p>
            <p v-if="parsedContent.summary"><strong>概述：</strong>{{ parsedContent.summary }}</p>
          </div>
        </div>

        <!-- 简历分析报告 -->
        <div v-if="analysis" class="card analysis-card" style="margin-bottom:20px">
          <h3 style="margin-bottom:14px">📊 简历分析报告</h3>
          <div class="analysis-score" v-if="analysis.overall_score">
            <div class="score-badge" :style="{ background: scoreColor(analysis.overall_score) }">
              {{ analysis.overall_score }}
            </div>
            <span class="score-text">简历综合评分</span>
          </div>
          <p v-if="analysis.summary" class="analysis-summary">{{ analysis.summary }}</p>
          <div class="analysis-section" v-if="analysis.keyword_match?.length">
            <h4>🎯 匹配技能</h4>
            <div class="tag-list">
              <span v-for="k in analysis.keyword_match" :key="k" class="tag tag-green">{{ k }}</span>
            </div>
          </div>
          <div class="analysis-section" v-if="analysis.missing_keywords?.length">
            <h4>⚠️ 缺少技能</h4>
            <div class="tag-list">
              <span v-for="k in analysis.missing_keywords" :key="k" class="tag tag-red">{{ k }}</span>
            </div>
          </div>
          <div class="analysis-two-col">
            <div v-if="analysis.strengths?.length">
              <h4 style="color:#059669;margin-bottom:8px">✅ 优势</h4>
              <ul><li v-for="(s, i) in analysis.strengths" :key="i">{{ s }}</li></ul>
            </div>
            <div v-if="analysis.weaknesses?.length">
              <h4 style="color:#dc2626;margin-bottom:8px">❌ 不足</h4>
              <ul><li v-for="(w, i) in analysis.weaknesses" :key="i">{{ w }}</li></ul>
            </div>
          </div>
          <div class="analysis-section" v-if="analysis.suggestions?.length">
            <h4>💡 改进建议</h4>
            <ul><li v-for="(s, i) in analysis.suggestions" :key="i">{{ s }}</li></ul>
          </div>
        </div>

        <div class="card knowledge-card" style="margin-bottom:20px">
          <div class="knowledge-header">
            <div>
              <h3 style="margin-bottom:8px">🧠 岗位知识库增强</h3>
              <p class="knowledge-desc">
                可选：选择你为目标岗位整理的知识库，让 AI 面试官更贴近你真正想训练的考点和追问方向。
              </p>
            </div>
            <router-link to="/knowledge-base" class="btn-secondary" style="display:inline-block;padding:8px 14px;border-radius:8px">
              管理知识库
            </router-link>
          </div>

          <div v-if="knowledgeLoading" class="knowledge-loading">正在加载知识库...</div>

          <template v-else>
            <div class="form-group">
              <label>选择要注入的岗位知识库</label>
              <select v-model="selectedKnowledgeBaseId">
                <option value="">不使用知识库（默认按简历与岗位出题）</option>
                <option
                  v-for="item in knowledgeBaseOptions"
                  :key="item.knowledge_base_id"
                  :value="String(item.knowledge_base_id)"
                >
                  {{ item.title }} ｜ {{ item.target_position }} ｜ {{ item.source_label }}{{ matchScore(item) > 0 ? ' · 推荐' : '' }}
                </option>
              </select>
            </div>

            <p v-if="knowledgeBaseOptions.length === 0" class="knowledge-empty">
              你还没有创建岗位知识库。建议先整理一份目标岗位的核心知识点，训练效果会更稳定。
            </p>

            <div v-else-if="selectedKnowledgeBase" class="knowledge-preview">
              <div class="knowledge-tags">
                <span class="knowledge-tag">{{ selectedKnowledgeBase.title }}</span>
                <span class="knowledge-tag subtle">{{ selectedKnowledgeBase.target_position }}</span>
                <span :class="['knowledge-tag', selectedKnowledgeBase.scope === 'public' ? 'public-tag' : 'private-tag']">
                  {{ selectedKnowledgeBase.source_label }}
                </span>
              </div>
              <p class="knowledge-preview-text">{{ selectedKnowledgeBase.preview }}</p>
              <p v-if="selectedKnowledgeBase.focus_points" class="knowledge-detail">
                <strong>训练重点：</strong>{{ selectedKnowledgeBase.focus_points }}
              </p>
              <p v-if="selectedKnowledgeBase.interviewer_prompt" class="knowledge-detail">
                <strong>面试官要求：</strong>{{ selectedKnowledgeBase.interviewer_prompt }}
              </p>
            </div>
          </template>
        </div>

        <div class="form-group">
          <label>面试难度</label>
          <select v-model="difficulty">
            <option value="easy">简单 - 基础知识</option>
            <option value="medium">中等 - 技术深度</option>
            <option value="hard">困难 - 系统设计</option>
          </select>
        </div>
        <div class="form-group">
          <label>题目数量</label>
          <select v-model.number="totalQuestions">
            <option :value="3">3 题（快速模式）</option>
            <option :value="5">5 题（标准模式）</option>
            <option :value="8">8 题（深度模式）</option>
          </select>
        </div>
        <div class="card panel-mode-card" style="margin-bottom:16px">
          <label class="panel-mode-toggle">
            <input v-model="multiInterviewerEnabled" type="checkbox" />
            <span>
              <strong>多面试官协同模式（第一阶段）</strong>
              <small>内部由多个训练角色协同出题和评估，对外仍只显示一个主持人，不改变当前交互形态。</small>
            </span>
          </label>
          <div v-if="multiInterviewerEnabled" class="panel-mode-preview">
            <div class="panel-preview-row">
              <span class="panel-preview-label">协同视角</span>
              <div class="panel-preview-tags">
                <span v-for="item in panelRoleHints" :key="item" class="panel-preview-tag">{{ item }}</span>
              </div>
            </div>
            <p class="panel-preview-note">
              外部仍然是单主持人面试流程；内部会额外综合多个训练视角做选题、追问和评估。
            </p>
          </div>
        </div>
        <p v-if="error" class="error">{{ error }}</p>
        <button class="btn-primary" style="width:100%" @click="handleStart" :disabled="starting">
          {{ starting ? '生成面试题中...' : '🚀 开始面试' }}
        </button>
      </div>

      <!-- Step 3: 面试准备动画 -->
      <div v-if="step === 'starting'" class="parsing-stage">
        <div class="ai-face-anim">
          <svg viewBox="0 0 80 80" width="80" height="80">
            <circle cx="40" cy="40" r="38" fill="white" stroke="#4f46e5" stroke-width="2"/>
            <ellipse cx="28" cy="36" rx="5" ry="6" fill="#1e1e1e">
              <animate attributeName="ry" values="6;1;6" dur="2s" repeatCount="indefinite"/>
            </ellipse>
            <ellipse cx="52" cy="36" rx="5" ry="6" fill="#1e1e1e">
              <animate attributeName="ry" values="6;1;6" dur="2s" repeatCount="indefinite"/>
            </ellipse>
            <path d="M30 52 Q40 60 50 52" stroke="#1e1e1e" stroke-width="2" fill="none" stroke-linecap="round"/>
          </svg>
        </div>
        <h3>{{ startingTitle }}</h3>
        <div class="progress-bar-wrapper">
          <div class="progress-bar" :style="{ width: startProgress + '%' }"></div>
        </div>
        <p class="progress-text">{{ startProgress }}%</p>
        <div class="tips-area">
          <transition name="tip-fade" mode="out-in">
            <p class="tip-text" :key="startTip">💡 {{ startTip }}</p>
          </transition>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { uploadResume, getResume } from '../api/resume'
import { startInterview } from '../api/interview'
import { getKnowledgeBases } from '../api/knowledgeBase'
import { getProfile, testAiConnection } from '../api/user'

const router = useRouter()
const step = ref(1)
const file = ref(null)
const targetPosition = ref('Python后端开发工程师')
const difficulty = ref('medium')
const totalQuestions = ref(5)
const multiInterviewerEnabled = ref(false)
const uploading = ref(false)
const starting = ref(false)
const error = ref('')
const resumeId = ref(null)
const parsedContent = ref(null)
const analysis = ref(null)
const knowledgeLoading = ref(false)
const knowledgeBases = ref([])
const selectedKnowledgeBaseId = ref('')
const panelRoleHints = ['技术深挖', '项目追问', '业务场景', '表达结构', '压力质询']

const aiProviderOptions = [
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'openai', label: 'ChatGPT / OpenAI' }
]
const aiProviderLabels = {
  deepseek: 'DeepSeek',
  openai: 'ChatGPT / OpenAI'
}
const aiProviderDefaults = {
  deepseek: { model: 'deepseek-chat' },
  openai: { model: 'gpt-5.2-chat-latest' }
}
const aiProviderModelOptions = {
  deepseek: [
    { value: 'deepseek-chat', label: 'deepseek-chat' },
    { value: 'deepseek-reasoner', label: 'deepseek-reasoner' }
  ],
  openai: [
    { value: 'gpt-5.2-chat-latest', label: 'gpt-5.2-chat-latest' },
    { value: 'gpt-5.2', label: 'gpt-5.2' },
    { value: 'gpt-5-mini', label: 'gpt-5-mini' }
  ]
}
const aiModelDatalistId = 'resume-upload-ai-model-options'
const aiTestProvider = ref('deepseek')
const aiTestModel = ref('')
const aiSavedModels = ref({
  deepseek: '',
  openai: ''
})
const testingAiConnection = ref(false)
const aiTestMessage = ref('')
const aiTestSuccess = ref(false)

const activeAiProviderLabel = computed(() => aiProviderLabels[aiTestProvider.value] || 'AI')
const activeAiModelOptions = computed(() => aiProviderModelOptions[aiTestProvider.value] || [])
const aiTestModelPlaceholder = computed(() => aiProviderDefaults[aiTestProvider.value]?.model || '')

const selectedKnowledgeBase = computed(() => {
  const id = Number(selectedKnowledgeBaseId.value)
  if (!id) return null
  return knowledgeBases.value.find(item => item.knowledge_base_id === id) || null
})

const knowledgeBaseOptions = computed(() => {
  return [...knowledgeBases.value].sort((a, b) => {
    const scoreDiff = matchScore(b) - matchScore(a)
    if (scoreDiff !== 0) return scoreDiff
    const scopeDiff = ownershipScore(b) - ownershipScore(a)
    if (scopeDiff !== 0) return scopeDiff
    return new Date(b.updated_at || b.created_at || 0).getTime() - new Date(a.updated_at || a.created_at || 0).getTime()
  })
})

// 解析动画相关
const progress = ref(0)
const parsingTitle = ref('正在上传简历...')
const currentTip = ref('')
let tipTimer = null
let progressTimer = null

const tips = [
  '面试前深呼吸，保持自信和冷静',
  '回答问题时用 STAR 法则：情境、任务、行动、结果',
  '不会的问题坦诚说不会，展示学习意愿比硬编更好',
  '准备好自我介绍，控制在1-2分钟',
  '技术面试中，思路比答案更重要',
  '项目经验要突出你的贡献和技术选型理由',
  '遇到算法题先理清思路再写代码',
  '面试官问"还有什么问题"时，准备2-3个有深度的问题',
  '简历上写的每个技术点都要能展开讲',
  '注意沟通表达，逻辑清晰比语速快更重要',
  '了解目标公司的业务和技术栈，展示你的诚意',
  '手撕代码时先写伪代码，再逐步实现',
  '系统设计题从需求分析开始，逐步细化',
  '准备几个你在项目中解决的难题案例',
  '面试结束后及时复盘，记录不足之处'
]

const resumeStatusMeta = {
  queued: { progress: 12, title: '简历已上传，正在进入解析队列...' },
  extracting: { progress: 32, title: '正在提取 PDF 文本内容...' },
  parsing: { progress: 58, title: 'AI 正在结构化解析简历...' },
  analyzing: { progress: 82, title: 'AI 正在生成简历分析报告...' },
  completed: { progress: 100, title: '解析完成，正在准备结果...' }
}

function syncParsingStage(status) {
  const meta = resumeStatusMeta[status]
  if (!meta) return
  if (progress.value < meta.progress) {
    progress.value = meta.progress
  }
  parsingTitle.value = meta.title
}

function startTipRotation() {
  currentTip.value = tips[Math.floor(Math.random() * tips.length)]
  tipTimer = setInterval(() => {
    let next
    do { next = tips[Math.floor(Math.random() * tips.length)] } while (next === currentTip.value)
    currentTip.value = next
  }, 3000)
}

function startProgressAnimation() {
  progress.value = 0
  const stages = [
    { target: 15, speed: 200, title: '正在上传简历...' },
    { target: 35, speed: 300, title: '正在提取文本内容...' },
    { target: 60, speed: 400, title: 'AI 正在解析简历...' },
    { target: 80, speed: 500, title: 'AI 正在分析简历质量...' },
    { target: 92, speed: 800, title: '即将完成...' }
  ]
  let stageIdx = 0

  function tick() {
    if (stageIdx >= stages.length) return
    const stage = stages[stageIdx]
    if (progress.value < stage.target) {
      progress.value++
      parsingTitle.value = stage.title
      progressTimer = setTimeout(tick, stage.speed)
    } else {
      stageIdx++
      tick()
    }
  }
  tick()
}

function stopAnimations() {
  if (tipTimer) { clearInterval(tipTimer); tipTimer = null }
  if (progressTimer) { clearTimeout(progressTimer); progressTimer = null }
}

function applyAiProfile(data) {
  aiSavedModels.value = {
    deepseek: data?.deepseek_model || '',
    openai: data?.openai_model || ''
  }
  aiTestProvider.value = data?.ai_provider || 'deepseek'
  aiTestModel.value = aiSavedModels.value[aiTestProvider.value] || aiProviderDefaults[aiTestProvider.value]?.model || ''
}

function handleAiProviderChange() {
  aiTestMessage.value = ''
  aiTestSuccess.value = false
  aiTestModel.value = aiSavedModels.value[aiTestProvider.value] || aiProviderDefaults[aiTestProvider.value]?.model || ''
}

onMounted(async () => {
  try {
    const data = await getProfile()
    applyAiProfile(data)
  } catch (e) {
    console.error('鍔犺浇 AI 閰嶇疆澶辫触', e)
  }
})

onUnmounted(() => {
  stopAnimations()
  stopStartingAnimation()
})

function selectPdfFile(candidate) {
  if (!candidate) return
  if (!candidate.name?.toLowerCase().endsWith('.pdf')) {
    error.value = '仅支持上传 PDF 简历'
    file.value = null
    return
  }
  if (candidate.size > 10 * 1024 * 1024) {
    error.value = '文件大小不能超过 10MB'
    file.value = null
    return
  }
  error.value = ''
  file.value = candidate
}

function onFileChange(e) {
  selectPdfFile(e.target.files[0])
}
function onDrop(e) {
  selectPdfFile(e.dataTransfer.files[0])
}

function normalizePosition(value) {
  return (value || '').trim().toLowerCase()
}

function matchScore(item) {
  const target = normalizePosition(targetPosition.value)
  const current = normalizePosition(item?.target_position)
  if (!target || !current) return 0
  if (current === target) return 2
  if (current.includes(target) || target.includes(current)) return 1
  return 0
}

function ownershipScore(item) {
  return item?.scope === 'private' ? 1 : 0
}

async function loadKnowledgeBases() {
  knowledgeLoading.value = true
  try {
    const data = await getKnowledgeBases()
    knowledgeBases.value = data.items || []

    if (!selectedKnowledgeBaseId.value) {
      const bestMatch = [...knowledgeBases.value]
        .sort((a, b) => {
          const scoreDiff = matchScore(b) - matchScore(a)
          if (scoreDiff !== 0) return scoreDiff
          return ownershipScore(b) - ownershipScore(a)
        })[0]
      if (bestMatch && matchScore(bestMatch) > 0) {
        selectedKnowledgeBaseId.value = String(bestMatch.knowledge_base_id)
      }
    }
  } catch (e) {
    console.error('加载知识库失败:', e)
    knowledgeBases.value = []
  } finally {
    knowledgeLoading.value = false
  }
}

async function handleTestAiConnection() {
  aiTestMessage.value = ''
  aiTestSuccess.value = false
  testingAiConnection.value = true
  try {
    const result = await testAiConnection({
      provider: aiTestProvider.value,
      model: aiTestModel.value?.trim() || undefined
    })
    aiTestSuccess.value = true
    aiTestMessage.value = result?.message || `${activeAiProviderLabel.value} API 连接测试成功`
  } catch (e) {
    aiTestMessage.value = e.message
  } finally {
    testingAiConnection.value = false
  }
}

async function handleUpload() {
  error.value = ''
  uploading.value = true
  try {
    await getProfile()

    // 切换到解析动画
    step.value = 'parsing'
    startTipRotation()
    startProgressAnimation()

    const data = await uploadResume(file.value, targetPosition.value, {
      provider: aiTestProvider.value,
      model: aiTestModel.value?.trim() || ''
    })
    resumeId.value = data.resume_id

    // 轮询等待解析完成
    let retries = 0
    while (retries < 180) {
      await new Promise(r => setTimeout(r, 3000))
      const detail = await getResume(resumeId.value)
      syncParsingStage(detail.status)
      if (detail.status === 'completed') {
        parsedContent.value = detail.parsed_content
        analysis.value = detail.analysis
        await loadKnowledgeBases()
        // 完成动画
        progress.value = 100
        parsingTitle.value = '解析完成！'
        await new Promise(r => setTimeout(r, 600))
        stopAnimations()
        step.value = 2
        return
      }
      if (detail.status === 'failed') {
        throw new Error(detail.error_message || '简历解析失败，请重试')
      }
      retries++
    }
    throw new Error('简历仍在后台解析中，请稍后到上传记录查看结果，无需重新上传')
  } catch (e) {
    stopAnimations()
    error.value = e.message
    step.value = 1
  } finally {
    uploading.value = false
  }
}

function scoreColor(score) {
  if (score >= 7) return '#10b981'
  if (score >= 5) return '#f59e0b'
  return '#ef4444'
}

// 面试准备动画
const startProgress = ref(0)
const startingTitle = ref('AI 面试即将开始，请做好准备')
const startTip = ref('')
let startTipTimer = null
let startProgressTimer = null

const startTips = [
  '深呼吸，保持冷静自信 💪',
  '回答时尽量结合你的项目经验',
  '思路比答案更重要，先理清再作答',
  '不会的问题坦诚说不会，展示学习意愿',
  '自我介绍控制在1-2分钟',
  '注意条理清晰，分点作答效果更好'
]

function startStartingAnimation() {
  startProgress.value = 0
  startTip.value = startTips[0]
  let tipIdx = 0
  startTipTimer = setInterval(() => {
    tipIdx = (tipIdx + 1) % startTips.length
    startTip.value = startTips[tipIdx]
  }, 2000)

  const stages = [
    { target: 30, speed: 150, title: 'AI 面试即将开始，请做好准备' },
    { target: 60, speed: 200, title: 'AI 正在生成面试题目...' },
    { target: 85, speed: 350, title: '正在根据你的简历定制题目...' },
    { target: 95, speed: 600, title: '即将开始...' }
  ]
  let stageIdx = 0

  function tick() {
    if (stageIdx >= stages.length) return
    const stage = stages[stageIdx]
    if (startProgress.value < stage.target) {
      startProgress.value++
      startingTitle.value = stage.title
      startProgressTimer = setTimeout(tick, stage.speed)
    } else {
      stageIdx++
      tick()
    }
  }
  tick()
}

function stopStartingAnimation() {
  if (startTipTimer) { clearInterval(startTipTimer); startTipTimer = null }
  if (startProgressTimer) { clearTimeout(startProgressTimer); startProgressTimer = null }
}

function cacheInterviewMeta(interviewId, data) {
  const meta = {
    interviewId,
    interviewMode: data?.interview_mode || (multiInterviewerEnabled.value ? 'panel' : 'single'),
    totalQuestions: data?.total_questions || totalQuestions.value,
    knowledgeBaseTitle: data?.knowledge_base_title || selectedKnowledgeBase.value?.title || '',
    targetPosition: targetPosition.value,
    multiInterviewerEnabled: !!multiInterviewerEnabled.value
  }
  sessionStorage.setItem(`interview_meta_${interviewId}`, JSON.stringify(meta))
  return meta
}

async function handleStart() {
  error.value = ''
  starting.value = true
  step.value = 'starting'
  startStartingAnimation()

  try {
    const data = await startInterview({
      resume_id: resumeId.value,
      target_position: targetPosition.value,
      knowledge_base_id: selectedKnowledgeBaseId.value ? Number(selectedKnowledgeBaseId.value) : null,
      difficulty: difficulty.value,
      total_questions: totalQuestions.value,
      multi_interviewer_enabled: multiInterviewerEnabled.value
    })
    const interviewMeta = cacheInterviewMeta(data.interview_id, data)
    // 完成动画
    startProgress.value = 100
    startingTitle.value = '面试准备完成！'
    stopStartingAnimation()
    await new Promise(r => setTimeout(r, 800))
    router.push({
      path: `/interview/${data.interview_id}`,
      query: {
        mode: interviewMeta.interviewMode,
        total: String(interviewMeta.totalQuestions)
      }
    })
  } catch (e) {
    stopStartingAnimation()
    error.value = e.message
    step.value = 2
  } finally {
    starting.value = false
  }
}
</script>

<style scoped>
.form-group { margin-bottom: 16px; }
.form-group label { display: block; margin-bottom: 6px; font-size: 14px; font-weight: 500; color: #374151; }
.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.compact-form-row {
  margin-bottom: 4px;
}
.upload-area {
  border: 2px dashed #d1d5db; border-radius: 8px; padding: 40px;
  text-align: center; cursor: pointer; transition: border-color 0.2s;
}
.upload-area:hover { border-color: #4f46e5; }
.error { color: #ef4444; font-size: 13px; margin-bottom: 12px; }
.parsed-info p { font-size: 14px; margin-bottom: 6px; line-height: 1.6; }
.api-test-card {
  border: 1px solid #e5e7eb;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
}
.api-test-head {
  margin-bottom: 12px;
}
.api-test-desc {
  font-size: 13px;
  line-height: 1.7;
  color: #6b7280;
}
.api-test-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.inline-msg {
  margin: 0;
}
.api-test-usage-note {
  margin: 10px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: #6b7280;
}

/* 解析动画 */
.parsing-stage { text-align: center; padding: 30px 0; }
.parsing-icon { font-size: 48px; margin-bottom: 16px; animation: pulse 1.5s ease-in-out infinite; }
.ai-face-anim { margin-bottom: 16px; animation: faceFloat 2s ease-in-out infinite; }
@keyframes faceFloat {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}
@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.15); opacity: 0.7; }
}
.parsing-stage h3 { font-size: 16px; color: #374151; margin-bottom: 20px; }
.progress-bar-wrapper {
  width: 100%; height: 8px; background: #e5e7eb; border-radius: 4px; overflow: hidden; margin-bottom: 8px;
}
.progress-bar {
  height: 100%; border-radius: 4px; transition: width 0.3s ease;
  background: linear-gradient(90deg, #4f46e5, #7c3aed, #a78bfa);
  background-size: 200% 100%;
  animation: shimmer 2s linear infinite;
}
@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
.progress-text { font-size: 13px; color: #6b7280; margin-bottom: 24px; }
.tips-area {
  min-height: 50px; display: flex; align-items: center; justify-content: center;
  background: #f9fafb; border-radius: 10px; padding: 14px 20px;
}
.tip-text { font-size: 13px; color: #4b5563; line-height: 1.6; margin: 0; }
.tip-fade-enter-active, .tip-fade-leave-active { transition: all 0.4s ease; }
.tip-fade-enter-from { opacity: 0; transform: translateY(8px); }
.tip-fade-leave-to { opacity: 0; transform: translateY(-8px); }

/* 分析报告 */
.analysis-card { border: 1px solid #e5e7eb; }
.analysis-score { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.score-badge {
  width: 48px; height: 48px; border-radius: 50%; display: flex; align-items: center;
  justify-content: center; color: white; font-size: 18px; font-weight: 700;
}
.score-text { font-size: 14px; color: #6b7280; }
.analysis-summary {
  font-size: 14px; line-height: 1.8; color: #374151; margin-bottom: 16px;
  padding: 10px 14px; background: #f9fafb; border-radius: 8px;
}
.analysis-section { margin-bottom: 14px; }
.analysis-section h4 { font-size: 14px; margin-bottom: 8px; color: #374151; }
.tag-list { display: flex; flex-wrap: wrap; gap: 8px; }
.tag { padding: 3px 10px; border-radius: 12px; font-size: 12px; }
.tag-green { background: #d1fae5; color: #065f46; }
.tag-red { background: #fee2e2; color: #991b1b; }
.analysis-two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 14px; }
.analysis-two-col ul, .analysis-section ul { list-style: none; padding: 0; }
.analysis-two-col li, .analysis-section li {
  font-size: 13px; line-height: 1.8; padding-left: 14px; position: relative;
}
.analysis-two-col li::before, .analysis-section li::before {
  content: '•'; position: absolute; left: 0; color: #9ca3af;
}
.knowledge-card {
  border: 1px solid #e5e7eb;
}
.knowledge-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.knowledge-desc {
  color: #6b7280;
  font-size: 14px;
  line-height: 1.7;
}
.knowledge-loading,
.knowledge-empty {
  font-size: 14px;
  color: #6b7280;
}
.knowledge-preview {
  margin-top: 14px;
  padding: 14px;
  border-radius: 10px;
  background: #f9fafb;
}
.knowledge-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.knowledge-tag {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  background: #ede9fe;
  color: #5b21b6;
  font-size: 12px;
  font-weight: 600;
}
.knowledge-tag.subtle {
  background: #e5e7eb;
  color: #4b5563;
}
.knowledge-tag.public-tag {
  background: #dbeafe;
  color: #1d4ed8;
}
.knowledge-tag.private-tag {
  background: #ede9fe;
  color: #5b21b6;
}
.knowledge-preview-text,
.knowledge-detail {
  font-size: 14px;
  color: #374151;
  line-height: 1.8;
}
.knowledge-detail {
  margin-top: 10px;
}
.panel-mode-card {
  background: linear-gradient(135deg, rgba(79, 70, 229, 0.08), rgba(16, 185, 129, 0.08));
  border: 1px solid rgba(79, 70, 229, 0.12);
}
.panel-mode-toggle {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  cursor: pointer;
}
.panel-mode-toggle input {
  margin-top: 4px;
}
.panel-mode-toggle strong {
  display: block;
  font-size: 14px;
  color: #111827;
  margin-bottom: 4px;
}
.panel-mode-toggle small {
  display: block;
  font-size: 12px;
  line-height: 1.6;
  color: #4b5563;
}
.panel-mode-preview {
  margin-top: 12px;
  padding: 12px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(79, 70, 229, 0.08);
}
.panel-preview-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.panel-preview-label {
  font-size: 12px;
  font-weight: 600;
  color: #4338ca;
  padding-top: 2px;
  white-space: nowrap;
}
.panel-preview-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.panel-preview-tag {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  color: #374151;
  background: #eef2ff;
  border: 1px solid rgba(79, 70, 229, 0.1);
}
.panel-preview-note {
  margin-top: 10px;
  font-size: 13px;
  line-height: 1.7;
  color: #4b5563;
}
@media (max-width: 640px) {
  .form-row {
    grid-template-columns: 1fr;
  }
  .api-test-actions {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>

