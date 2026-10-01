<template>
  <section class="page" data-module="prune-detail">
    <header class="page-head">
      <div>
        <h2>修剪任务详情</h2>
        <p class="page-desc">明细与修剪列表同源读取，修剪量保持一致；缺项、取数状态与返工留存结果都在此可见。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="backToList">返回列表</button>
      </div>
    </header>

    <div v-if="loadFailed" class="detail-error">
      <span class="error-text">修剪明细读取失败，与「记录不存在」不是一回事。</span>
      <button class="btn" type="button" @click="loadDetail">重新加载</button>
    </div>

    <template v-else-if="entry">
      <div class="detail-status">
        <span class="status-tag" :class="statusClass">{{ entry['修剪状态'] }}</span>
        <span v-if="entry._待补" class="tag-pending-text">该单存在待补项，补齐后才能进入修剪</span>
        <span v-if="entry._可返工接回" class="tag-rework-text">返工进行中，原修剪结果已留存，可一键接回</span>
      </div>

      <table class="data-table detail-table">
        <tbody>
          <tr v-for="field in detailFields" :key="field">
            <th>{{ field }}</th>
            <td>
              <template v-if="field === '修剪量'">
                <span :class="qtyClass">{{ entry[field] }}</span>
                <span v-if="entry._修剪量错误" class="muted">（{{ entry._修剪量错误 }}）</span>
              </template>
              <template v-else>{{ entry[field] ?? '—' }}</template>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="entry._缺项 && entry._缺项.length" class="detail-block">
        <h3>待补项与原因</h3>
        <ul class="reason-list">
          <li v-for="reason in entry._缺项" :key="reason">{{ reason }}</li>
        </ul>
      </div>

      <div v-if="entry._返工快照" class="detail-block">
        <h3>返工留存的原修剪结果</h3>
        <p class="muted">返工中途断掉也能据此接回，已填修剪量不会丢失。</p>
        <table class="data-table detail-table">
          <tbody>
            <tr><th>原状态</th><td>{{ entry._返工快照['原状态'] }}</td></tr>
            <tr><th>原修剪量</th><td>{{ entry._返工快照['修剪量'] }}</td></tr>
            <tr><th>原造型要求</th><td>{{ entry._返工快照['造型要求'] }}</td></tr>
            <tr><th>原作业日期</th><td>{{ entry._返工快照['作业日期'] }}</td></tr>
            <tr><th>原操作人员</th><td>{{ entry._返工快照['操作人员'] }}</td></tr>
          </tbody>
        </table>
      </div>

      <div class="detail-actions">
        <button v-if="entry._修剪量状态 === 'failed'" class="btn" type="button" :disabled="busy" @click="retryQuantity">
          {{ busy ? '取数中…' : '重试取数' }}
        </button>
        <button
          v-if="entry._修剪量状态 === 'failed' || entry._修剪量状态 === 'empty' || entry['修剪量'] === '待补'"
          class="btn"
          type="button"
          @click="supplementing = true"
        >
          人工补录修剪量
        </button>
        <button v-for="action in actions" :key="action.name" class="btn" :class="action.primary ? 'primary' : ''" type="button" :disabled="busy" @click="runAction(action.name)">
          {{ action.label }}
        </button>
      </div>
    </template>

    <!-- 补录 -->
    <div v-if="supplementing" class="modal-mask" @click.self="supplementing = false">
      <div class="modal">
        <h3>人工补录 · {{ entry?.['修剪编号'] }}</h3>
        <div class="form-item">
          <label>造型要求</label>
          <input v-model="supplementForm.造型要求" placeholder="补填造型要求" />
        </div>
        <div class="form-item">
          <label>修剪量</label>
          <input v-model="supplementForm.修剪量" placeholder="手工补录数值，如 120" />
        </div>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="supplementing = false">取消</button>
          <button class="btn primary" type="button" :disabled="busy" @click="submitSupplement">保存补录</button>
        </div>
      </div>
    </div>

    <footer class="page-foot">
      <span v-if="message" :class="ok ? 'success-text' : 'error-text'">{{ message }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, any>

const ENDPOINT = '/api/prune'
const route = useRoute()
const router = useRouter()

const detailFields = ['修剪编号', '修剪对象', '修剪类型', '修剪量', '造型要求', '作业日期', '操作人员', '修剪状态']

const entry = ref<Row | null>(null)
const loadFailed = ref(false)
const busy = ref(false)
const supplementing = ref(false)
const message = ref('')
const ok = ref(false)
const supplementForm = reactive<Row>({ 造型要求: '', 修剪量: '' })

const statusClass = computed(() => {
  const row = entry.value
  if (!row) return ''
  if (row._待补) return 'tag-pending'
  if (row._status === '需返工') return 'tag-rework'
  if (row._status === '已完成') return 'tag-done'
  return 'tag-normal'
})

const qtyClass = computed(() => {
  const state = entry.value?._修剪量状态
  if (state === 'failed') return 'qty-failed'
  if (state === 'empty') return 'qty-empty'
  return 'qty-ok'
})

const actions = computed<{ name: string; label: string; primary?: boolean }[]>(() => {
  switch (entry.value?._status) {
    case '待修剪':
      return [{ name: '安排修剪', label: '安排修剪' }]
    case '修剪中':
      return [{ name: '开始修剪', label: '提交修剪结果', primary: true }]
    case '已完成':
      return [{ name: '返工登记', label: '返工登记' }]
    case '需返工':
      return [{ name: '返工完成', label: '返工接回（恢复原修剪结果）', primary: true }]
    default:
      return []
  }
})

function flash(text: string, success = false) {
  message.value = text
  ok.value = success
}

async function loadDetail() {
  loadFailed.value = false
  message.value = ''
  const id = route.params.id
  try {
    const res = await request(`${ENDPOINT}/${id}`)
    if (!res.ok) throw new Error()
    entry.value = await res.json()
  } catch {
    loadFailed.value = true
    flash('修剪明细读取失败，可重试；这不同于记录不存在', false)
  }
}

async function runAction(action: string) {
  if (!entry.value) return
  busy.value = true
  try {
    const res = await request(`${ENDPOINT}/${entry.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await res.json()
    flash(payload.message, !!payload.ok)
    await loadDetail()
  } catch {
    flash('操作请求失败，请稍后重试', false)
  } finally {
    busy.value = false
  }
}

async function retryQuantity() {
  if (!entry.value) return
  busy.value = true
  try {
    const res = await request(`${ENDPOINT}/${entry.value.id}/quantity`, { method: 'POST' })
    const payload = await res.json()
    flash(payload.message, !!payload.ok)
    await loadDetail()
  } catch {
    flash('修剪量取数请求失败，可再次重试', false)
  } finally {
    busy.value = false
  }
}

async function submitSupplement() {
  if (!entry.value) return
  const values: Record<string, string> = {}
  if (String(supplementForm.造型要求 || '').trim()) values['造型要求'] = supplementForm.造型要求
  if (String(supplementForm.修剪量 || '').trim()) values['修剪量'] = supplementForm.修剪量
  if (!Object.keys(values).length) {
    flash('请至少补录一项内容', false)
    return
  }
  busy.value = true
  try {
    const res = await request(`${ENDPOINT}/${entry.value.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ values }),
    })
    const payload = await res.json()
    flash(payload.message, !!payload.ok)
    if (payload.ok) {
      supplementing.value = false
      supplementForm.造型要求 = ''
      supplementForm.修剪量 = ''
    }
    await loadDetail()
  } catch {
    flash('补录保存失败，请稍后重试', false)
  } finally {
    busy.value = false
  }
}

// 返回修剪列表，停在原来的筛选与滚动位置
function backToList() {
  void router.push('/prune')
}

onMounted(loadDetail)
</script>
