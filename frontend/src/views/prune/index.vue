<template>
  <section class="page" data-module="prune">
    <header class="page-head">
      <div>
        <h2>修剪造型管理</h2>
        <p class="page-desc">维护修剪任务，围绕修剪编号、修剪对象、修剪类型、修剪量做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记修剪任务</button>
        <button class="btn" type="button" @click="exportRows">导出修剪造型清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="applyFilters">
      <label class="filter-item">
        <span>修剪编号</span>
        <input v-model="keyword" placeholder="按修剪编号检索" />
      </label>
      <label class="filter-item">
        <span>修剪状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="option in statusOptions" :key="option" :value="option">{{ option }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <p v-if="feedback.text" class="feedback" :class="feedback.kind">{{ feedback.text }}</p>

    <div v-if="loadError" class="error-panel">
      <span>修剪任务列表读取失败：{{ loadError }}。这不是空清单，请重试。</span>
      <button class="btn" type="button" @click="loadAll">重试</button>
    </div>
    <p v-else-if="loading" class="hint-text">修剪任务列表加载中…</p>

    <template v-else>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in columns" :key="column">{{ column }}</th>
            <th>修剪状态</th>
            <th>待补说明</th>
            <th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="String(row.id)">
            <td
              v-for="column in columns"
              :key="column"
              :class="{ 'todo-cell': isMissingCell(row, column) }"
            >
              {{ cellText(row, column) }}
            </td>
            <td>
              <span :class="statusClass(row)">{{ statusOf(row) || '—' }}</span>
              <span v-if="hasMissing(row)" class="badge warn">待补</span>
            </td>
            <td class="todo-cell">{{ hasMissing(row) ? `缺：${missingReason(row)}` : '—' }}</td>
            <td class="row-actions">
              <button
                v-if="!hasQuantity(row)"
                class="link"
                type="button"
                :disabled="actingId === String(row.id)"
                @click="fetchQuantity(row)"
              >
                取数
              </button>
              <button
                v-if="hasMissing(row)"
                class="link"
                type="button"
                :disabled="actingId === String(row.id)"
                @click="openSupplement(row)"
              >
                补录
              </button>
              <button
                v-if="statusOf(row) === '待修剪'"
                class="link"
                type="button"
                :disabled="actingId === String(row.id)"
                @click="runAction('安排修剪', row)"
              >
                安排修剪
              </button>
              <button
                v-if="statusOf(row) === '修剪中'"
                class="link"
                type="button"
                :disabled="actingId === String(row.id)"
                @click="runAction('开始修剪', row)"
              >
                开始修剪
              </button>
              <button
                v-if="statusOf(row) === '已完成'"
                class="link"
                type="button"
                :disabled="actingId === String(row.id)"
                @click="runAction('返工登记', row)"
              >
                返工登记
              </button>
              <button
                v-if="statusOf(row) === '需返工'"
                class="link"
                type="button"
                :disabled="actingId === String(row.id)"
                @click="runAction('接回原结果', row)"
              >
                接回原结果
              </button>
              <button class="link" type="button" @click="goDetail(row)">详情</button>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td :colspan="columns.length + 3" class="empty-state">
              暂无符合条件的修剪任务，可重置条件或先登记修剪任务
            </td>
          </tr>
        </tbody>
      </table>

      <footer class="page-foot">
        <span>共 {{ total }} 条修剪造型记录</span>
        <div class="pagination">
          <button class="btn" type="button" :disabled="page <= 1" @click="changePage(page - 1)">上一页</button>
          <span>第 {{ page }} / {{ pageCount }} 页</span>
          <button class="btn" type="button" :disabled="page >= pageCount" @click="changePage(page + 1)">下一页</button>
        </div>
      </footer>
    </template>

    <div v-if="createVisible" class="modal-mask" @click.self="closeCreate">
      <div class="modal">
        <h3>登记修剪任务</h3>
        <p class="hint-text">修剪编号必填且唯一，重复提交只认第一次；其余字段可登记后补录。</p>
        <label v-for="field in createFields" :key="field.key" class="form-row">
          <span>{{ field.label }}<em v-if="field.required" class="required-mark">*</em></span>
          <input v-model="createForm[field.key]" :placeholder="field.placeholder" />
        </label>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" :disabled="submitting" @click="closeCreate">取消</button>
          <button class="btn primary" type="button" :disabled="submitting" @click="submitCreate">
            {{ submitting ? '提交中…' : '提交登记' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="supplementVisible" class="modal-mask" @click.self="closeSupplement">
      <div class="modal">
        <h3>补录修剪任务 {{ supplementTarget }}</h3>
        <p class="hint-text">只补空缺字段，已有值不会被覆盖；修剪量补录后标记为人工补录。</p>
        <label v-for="field in supplementFields" :key="field" class="form-row">
          <span>
            {{ field }}
            <em v-if="isSupplementMissing(field)" class="required-mark">待补</em>
          </span>
          <input
            v-model="supplementForm[field]"
            :placeholder="supplementPlaceholder(field)"
            :disabled="!isSupplementMissing(field)"
          />
        </label>
        <p v-if="supplementError" class="error-text">{{ supplementError }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" :disabled="submitting" @click="closeSupplement">取消</button>
          <button class="btn primary" type="button" :disabled="submitting" @click="submitSupplement">
            {{ submitting ? '提交中…' : '提交补录' }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

interface Row {
  id: number | string
  [key: string]: unknown
}

interface ActionReply {
  ok: boolean
  message: string
  entry: Row | null
}

const ENDPOINT = '/api/prune'
const PAGE_SIZE = 20
const columns = ["修剪编号", "修剪对象", "修剪类型", "修剪量", "造型要求", "作业日期", "操作人员"]
const statusOptions = ["待修剪", "修剪中", "已完成", "需返工", "待补"]
const createFields = [
  { key: "修剪编号", label: "修剪编号", required: true, placeholder: "如 PRUN-0005，全平台唯一" },
  { key: "修剪对象", label: "修剪对象", required: false, placeholder: "可登记后补录" },
  { key: "修剪类型", label: "修剪类型", required: false, placeholder: "可登记后补录" },
  { key: "造型要求", label: "造型要求", required: false, placeholder: "可登记后补录" },
  { key: "作业日期", label: "作业日期", required: false, placeholder: "如 2026-10-01" },
  { key: "操作人员", label: "操作人员", required: false, placeholder: "可登记后补录" },
]
const supplementFields = ["修剪对象", "修剪类型", "造型要求", "修剪量", "作业日期", "操作人员"]

const route = useRoute()
const router = useRouter()

const rows = ref<Row[]>([])
const total = ref(0)
const loading = ref(false)
const loadError = ref('')
const actingId = ref('')
const feedback = ref<{ text: string; kind: 'ok' | 'err' }>({ text: '', kind: 'ok' })

const keyword = ref(typeof route.query.keyword === 'string' ? route.query.keyword : '')
const statusFilter = ref(typeof route.query.status === 'string' ? route.query.status : '')
const page = ref(Math.max(1, Number(route.query.page) || 1))

const stats = ref([
  { label: '待修剪任务', value: 0 },
  { label: '修剪中任务', value: 0 },
  { label: '已完成任务', value: 0 },
  { label: '待返工', value: 0 },
  { label: '待补订单', value: 0 },
])

const createVisible = ref(false)
const createForm = ref<Record<string, string>>({})
const createError = ref('')
const submitting = ref(false)

const supplementVisible = ref(false)
const supplementId = ref('')
const supplementTarget = ref('')
const supplementForm = ref<Record<string, string>>({})
const supplementCurrent = ref<Row | null>(null)
const supplementError = ref('')

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

function missingOf(row: Row): string[] {
  const value = row['待补字段']
  return Array.isArray(value) ? (value as string[]) : []
}

function hasMissing(row: Row): boolean {
  return missingOf(row).length > 0
}

function missingReason(row: Row): string {
  return String(row['待补原因'] ?? '')
}

function statusOf(row: Row): string {
  return String(row['status'] ?? '')
}

function hasQuantity(row: Row): boolean {
  return String(row['修剪量'] ?? '') !== ''
}

function cellText(row: Row, field: string): string {
  const value = row[field]
  if (value !== null && value !== undefined && String(value) !== '') {
    return String(value)
  }
  return missingOf(row).includes(field) ? '待补' : '—'
}

function isMissingCell(row: Row, field: string): boolean {
  const value = row[field]
  const empty = value === null || value === undefined || String(value) === ''
  return empty && missingOf(row).includes(field)
}

function statusClass(row: Row): string {
  switch (statusOf(row)) {
    case '修剪中':
      return 'badge doing'
    case '已完成':
      return 'badge done'
    case '需返工':
      return 'badge rework'
    default:
      return 'badge'
  }
}

function setFeedback(text: string, kind: 'ok' | 'err') {
  feedback.value = { text, kind }
}

function syncQuery() {
  const query: Record<string, string> = {}
  if (keyword.value) query.keyword = keyword.value
  if (statusFilter.value) query.status = statusFilter.value
  if (page.value > 1) query.page = String(page.value)
  void router.replace({ query })
}

async function postAction(path: string, values?: Record<string, unknown>): Promise<ActionReply> {
  const response = await request(path, {
    method: 'POST',
    body: JSON.stringify(values === undefined ? {} : { values }),
  })
  if (!response.ok) {
    throw new Error(`接口返回 ${response.status}，操作未生效`)
  }
  return (await response.json()) as ActionReply
}

async function loadList() {
  loading.value = true
  loadError.value = ''
  const query = new URLSearchParams()
  if (keyword.value) query.set('keyword', keyword.value)
  if (statusFilter.value) query.set('status', statusFilter.value)
  query.set('page', String(page.value))
  query.set('size', String(PAGE_SIZE))
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error(`接口返回 ${response.status}`)
    }
    const payload = (await response.json()) as { items?: Row[]; total?: number }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    rows.value = []
    total.value = 0
    loadError.value = error instanceof Error ? error.message : '未知错误'
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) {
      return
    }
    const payload = (await response.json()) as Record<string, number>
    stats.value = [
      { label: '待修剪任务', value: payload['待修剪'] ?? 0 },
      { label: '修剪中任务', value: payload['修剪中'] ?? 0 },
      { label: '已完成任务', value: payload['已完成'] ?? 0 },
      { label: '待返工', value: payload['需返工'] ?? 0 },
      { label: '待补订单', value: payload['待补'] ?? 0 },
    ]
  } catch {
    // 看板统计失败不阻塞列表，下次操作后会重新拉取
  }
}

async function loadAll() {
  await Promise.all([loadList(), loadStats()])
}

function applyFilters() {
  page.value = 1
  syncQuery()
  void loadAll()
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  page.value = 1
  syncQuery()
  void loadAll()
}

function changePage(next: number) {
  page.value = Math.min(Math.max(1, next), pageCount.value)
  syncQuery()
  void loadAll()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function goDetail(row: Row) {
  void router.push(`/prune/${String(row.id)}`)
}

async function runAction(action: string, row: Row) {
  const id = String(row.id)
  actingId.value = id
  feedback.value = { text: '', kind: 'ok' }
  try {
    const result = await postAction(`${ENDPOINT}/${id}/actions`, { action })
    setFeedback(result.message, result.ok ? 'ok' : 'err')
  } catch (error) {
    setFeedback(error instanceof Error ? error.message : '修剪造型操作失败', 'err')
  } finally {
    actingId.value = ''
  }
  await loadAll()
}

async function fetchQuantity(row: Row) {
  const id = String(row.id)
  actingId.value = id
  feedback.value = { text: '', kind: 'ok' }
  try {
    const result = await postAction(`${ENDPOINT}/${id}/fetch-quantity`)
    // 取不到数也要明确提示：可点“取数”重试，或点“补录”人工填写
    setFeedback(result.message, result.ok ? 'ok' : 'err')
  } catch (error) {
    setFeedback(error instanceof Error ? error.message : '修剪量取数失败，可重试或补录', 'err')
  } finally {
    actingId.value = ''
  }
  await loadAll()
}

function openCreate() {
  createForm.value = {}
  createError.value = ''
  createVisible.value = true
}

function closeCreate() {
  createVisible.value = false
}

async function submitCreate() {
  if (submitting.value) return
  createError.value = ''
  if (!(createForm.value['修剪编号'] ?? '').trim()) {
    createError.value = '缺少必填字段：修剪编号'
    return
  }
  submitting.value = true
  try {
    const result = await postAction(ENDPOINT, createForm.value)
    if (!result.ok) {
      createError.value = result.message
      return
    }
    createVisible.value = false
    setFeedback(result.message, 'ok')
    await loadAll()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '修剪任务登记失败'
  } finally {
    submitting.value = false
  }
}

function openSupplement(row: Row) {
  supplementId.value = String(row.id)
  supplementTarget.value = String(row['修剪编号'] ?? row.id)
  supplementCurrent.value = row
  supplementForm.value = {}
  supplementError.value = ''
  supplementVisible.value = true
}

function closeSupplement() {
  supplementVisible.value = false
}

function isSupplementMissing(field: string): boolean {
  const current = supplementCurrent.value
  if (!current) return true
  const value = current[field]
  return value === null || value === undefined || String(value) === ''
}

function supplementPlaceholder(field: string): string {
  return isSupplementMissing(field) ? '待补，请填写' : '已有值，不覆盖'
}

async function submitSupplement() {
  if (submitting.value) return
  supplementError.value = ''
  const values: Record<string, string> = {}
  for (const field of supplementFields) {
    const value = (supplementForm.value[field] ?? '').trim()
    if (value) values[field] = value
  }
  if (!Object.keys(values).length) {
    supplementError.value = '请至少填写一个待补字段'
    return
  }
  submitting.value = true
  try {
    const result = await postAction(`${ENDPOINT}/${supplementId.value}/supplement`, values)
    if (!result.ok) {
      supplementError.value = result.message
      return
    }
    supplementVisible.value = false
    setFeedback(result.message, 'ok')
    await loadAll()
  } catch (error) {
    supplementError.value = error instanceof Error ? error.message : '补录失败'
  } finally {
    submitting.value = false
  }
}

onMounted(loadAll)
</script>
