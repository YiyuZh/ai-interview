<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:20px">
      <div>
        <h1 style="font-size:20px;margin-bottom:8px">🧠 公共知识库</h1>
        <p style="color:#6b7280;font-size:14px;line-height:1.7">
          这里维护的是后台公共知识库。普通用户可以直接使用这些知识库，但不能编辑它们。
        </p>
      </div>
      <button class="btn-primary" @click="startCreate">{{ editingId ? '新建一份' : '+ 新建公共知识库' }}</button>
    </div>

    <div class="kb-layout">
      <div class="card">
        <h3 style="margin-bottom:16px">{{ editingId ? '编辑公共知识库' : '新建公共知识库' }}</h3>

        <div class="form-group">
          <label>标题</label>
          <input v-model="form.title" placeholder="例如：Java 后端面试高频题库" />
        </div>

        <div class="form-group">
          <label>目标岗位</label>
          <input v-model="form.target_position" placeholder="例如：Java后端开发工程师" />
        </div>

        <div class="form-group">
          <label>知识内容</label>
          <textarea v-model="form.knowledge_content" rows="9" placeholder="写岗位核心知识点、常见场景、常问原理、典型技术栈" />
        </div>

        <div class="form-group">
          <label>重点训练方向</label>
          <textarea v-model="form.focus_points" rows="5" placeholder="例如：重点追问缓存一致性、事务、索引原理、系统设计" />
        </div>

        <div class="form-group">
          <label>额外面试官要求</label>
          <textarea v-model="form.interviewer_prompt" rows="4" placeholder="例如：多问项目落地，不要停留在纯八股" />
        </div>

        <label class="switch-row">
          <input v-model="form.is_active" type="checkbox" />
          <span>启用这份公共知识库</span>
        </label>

        <p v-if="msg" :class="msg.startsWith('✅') ? 'success-text' : 'error-text'">{{ msg }}</p>

        <div style="display:flex;gap:10px;margin-top:12px">
          <button class="btn-primary" @click="handleSubmit" :disabled="saving">
            {{ saving ? '保存中...' : (editingId ? '保存修改' : '创建公共知识库') }}
          </button>
          <button v-if="editingId" class="btn-sm" @click="resetForm">取消编辑</button>
        </div>
      </div>

      <div>
        <div class="card" style="margin-bottom:12px">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:12px">
            <h3>公共知识库列表</h3>
            <input v-model="keyword" placeholder="按标题 / 岗位筛选" style="width:260px" />
          </div>
        </div>

        <div v-if="loading" class="card empty-card">加载中...</div>

        <div v-else-if="filteredItems.length === 0" class="card empty-card">
          还没有公共知识库。
        </div>

        <div v-else class="kb-list">
          <div v-for="item in filteredItems" :key="item.knowledge_base_id" class="card kb-item">
            <div class="kb-head">
              <div>
                <h3>{{ item.title }}</h3>
                <p>{{ item.target_position }}</p>
              </div>
              <span :class="['badge', item.is_active ? 'badge-green' : 'badge-red']">
                {{ item.is_active ? '启用中' : '已停用' }}
              </span>
            </div>

            <p class="kb-preview">{{ item.preview }}</p>

            <p v-if="item.focus_points" class="kb-extra"><strong>训练重点：</strong>{{ item.focus_points }}</p>
            <p v-if="item.interviewer_prompt" class="kb-extra"><strong>面试官要求：</strong>{{ item.interviewer_prompt }}</p>

            <div class="kb-footer">
              <span>更新时间：{{ formatDate(item.updated_at || item.created_at) }}</span>
              <div style="display:flex;gap:8px">
                <button class="btn-primary btn-sm" @click="handleEdit(item)">编辑</button>
                <button class="btn-danger btn-sm" @click="handleDelete(item)">删除</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { knowledgeBaseApi } from '../api'

const loading = ref(true)
const saving = ref(false)
const keyword = ref('')
const editingId = ref(null)
const msg = ref('')
const items = ref([])

const defaultForm = () => ({
  title: '',
  target_position: '',
  knowledge_content: '',
  focus_points: '',
  interviewer_prompt: '',
  is_active: true
})

const form = ref(defaultForm())

const filteredItems = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return items.value
  return items.value.filter(item => {
    return [item.title, item.target_position, item.preview]
      .filter(Boolean)
      .some(text => text.toLowerCase().includes(kw))
  })
})

function formatDate(value) {
  if (!value) return ''
  return new Date(value).toLocaleString('zh-CN')
}

async function loadItems() {
  loading.value = true
  try {
    const data = await knowledgeBaseApi.list()
    items.value = data.items || []
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

function resetForm() {
  editingId.value = null
  form.value = defaultForm()
  msg.value = ''
}

function startCreate() {
  resetForm()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function handleEdit(item) {
  editingId.value = item.knowledge_base_id
  form.value = {
    title: item.title || '',
    target_position: item.target_position || '',
    knowledge_content: item.knowledge_content || '',
    focus_points: item.focus_points || '',
    interviewer_prompt: item.interviewer_prompt || '',
    is_active: !!item.is_active
  }
  msg.value = ''
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

async function handleSubmit() {
  msg.value = ''
  if (!form.value.title.trim() || !form.value.target_position.trim() || !form.value.knowledge_content.trim()) {
    msg.value = '标题、目标岗位和知识内容不能为空'
    return
  }

  saving.value = true
  try {
    const payload = {
      ...form.value,
      title: form.value.title.trim(),
      target_position: form.value.target_position.trim(),
      knowledge_content: form.value.knowledge_content.trim(),
      focus_points: form.value.focus_points.trim(),
      interviewer_prompt: form.value.interviewer_prompt.trim()
    }

    if (editingId.value) {
      await knowledgeBaseApi.update(editingId.value, payload)
      await loadItems()
      msg.value = '✅ 公共知识库已更新'
    } else {
      await knowledgeBaseApi.create(payload)
      await loadItems()
      resetForm()
      msg.value = '✅ 公共知识库已创建'
    }
  } catch (e) {
    msg.value = e.message
  } finally {
    saving.value = false
  }
}

async function handleDelete(item) {
  if (!confirm(`确定删除“${item.title}”吗？`)) return
  try {
    await knowledgeBaseApi.delete(item.knowledge_base_id)
    if (editingId.value === item.knowledge_base_id) resetForm()
    await loadItems()
  } catch (e) {
    alert('删除失败：' + e.message)
  }
}

onMounted(loadItems)
</script>

<style scoped>
.kb-layout {
  display: grid;
  grid-template-columns: minmax(0, 420px) minmax(0, 1fr);
  gap: 16px;
}
.form-group {
  margin-bottom: 14px;
}
.form-group label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 600;
}
.form-group input,
.form-group textarea {
  width: 100%;
}
.form-group textarea {
  resize: vertical;
}
.switch-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  margin-top: 6px;
}
.switch-row input {
  width: auto;
}
.success-text {
  color: #059669;
  font-size: 13px;
}
.error-text {
  color: #ef4444;
  font-size: 13px;
}
.kb-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.kb-item {
  padding: 18px;
}
.kb-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}
.kb-head h3 {
  font-size: 17px;
  margin-bottom: 6px;
}
.kb-head p {
  color: #6b7280;
  font-size: 14px;
}
.kb-preview {
  margin: 14px 0;
  line-height: 1.8;
}
.kb-extra {
  font-size: 14px;
  line-height: 1.7;
  color: #4b5563;
  margin-top: 10px;
}
.kb-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  color: #6b7280;
  font-size: 13px;
}
.empty-card {
  text-align: center;
  color: #6b7280;
  padding: 40px 20px;
}

@media (max-width: 960px) {
  .kb-layout {
    grid-template-columns: 1fr;
  }
}
</style>
