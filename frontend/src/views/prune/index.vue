<template>
  <section class="page" data-module="prune">
    <header class="page-head">
      <div>
        <h2>修剪造型管理</h2>
        <p class="page-desc">围绕修剪对象、造型要求、修剪量做登记与状态流转；缺项按待补挂起，取数失败可重试、清单为空走补录，返工可接回原修剪结果。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记修剪任务</button>
        <button class="btn" type="button" @click="exportRows">导出修剪造型清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card" :class="item.danger ? 'stat-danger' : ''">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>修剪编号</span>
        <input v-model="filters.keyword" placeholder="按修剪编号检索" />
      </label>
      <label class="filter-item">
        <span>修剪状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="st in statuses" :key="st" :value="st">{{ st }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>缺项/取数</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :class="{ 'row-pending': row._待补, 'row-rework': row._status === '需返工' }">
          <td v-for="column in columns" :key="column">
            <template v-if="column === '修剪编号'">
              <button class="link" type="button" @click="openDetail(row)">{{ row[column] }}</button>
            </template>
            <template v-else-if="column === '修剪状态'">
              <span class="status-tag" :class="statusClass(row)">{{ row[column] }}</span>
            </template>
            <template v-else-if="column === '修剪量'">
              <span :class="qtyClass(row)">{{ row[column] }}</span>
            </template>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="cell-note">
            <ul v-if="row._缺项 && row._缺项.length" class="reason-list">
              <li v-for="reason in row._缺项" :key="reason">{{ reason }}</li>
            </ul>
            <div v-if="row._修剪量状态 === 'failed'" class="retry-box">
              <button class="link" type="button" :disabled="busyId === row.id" @click="retryQuantity(row)">
                {{ busyId === row.id ? '取数中…' : '重试取数' }}
              </button>
              <button class="link" type="button" @click="openSupplement(row)">人工补录</button>
            </div>
            <div v-else-if="row._修剪量状态 === 'empty'" class="retry-box">
              <button class="link" type="button" @click="openSupplement(row)">补录修剪量</button>
            </div>
            <div v-else-if="row._可返工接回" class="retry-box">
              <span class="muted">原结果已留存，可接回</span>
            </div>
            <span v-else class="muted">—</span>
          </td>
          <td class="row-actions">
            <template v-for="action in availableActions(row)" :key="action.name">
              <button
                class="link"
                :class="action.primary ? 'primary-link' : ''"
                type="button"
                :disabled="busyId === row.id"
                @click="runAction(action.name, row)"
              >
                {{ action.label }}
              </button>
            </template>
            <button class="link" type="button" @click="openDetail(row)">详情</button>
          </td>
        </tr>
        <tr v-if="!rows.length && !loadFailed">
          <td :colspan="columns.length + 2" class="empty-state">暂无修剪造型数据，可先登记修剪任务</td>
        </tr>
        <tr v-if="loadFailed">
          <td :colspan="columns.length + 2" class="empty-state">
            <span class="error-text">修剪清单加载失败，与「暂无数据」不是一回事。</span>
            <button class="btn" type="button" @click="reload">重新加载</button>
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条修剪造型记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="successMessage" class="success-text">{{ successMessage }}</span>
    </footer>

    <!-- 登记修剪任务 -->
    <div v-if="creating" class="modal-mask" @click.self="creating = false">
      <div class="modal">
        <h3>登记修剪任务</h3>
        <div v-for="field in createFields" :key="field.name" class="form-item">
          <label>{{ field.label }}{{ field.required ? ' *' : '' }}</label>
          <input v-model="createForm[field.name]" :placeholder="field.placeholder" />
        </div>
        <p class="form-tip">登记后会自动向计量服务取修剪量；取不到数会提示取数失败并可重试，清单为空则引导人工补录。</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="creating = false">取消</button>
          <button class="btn primary" type="button" :disabled="submitting" @click="submitCreate">
            {{ submitting ? '提交中…' : '登记' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 补录缺项 / 修剪量 -->
    <div v-if="supplementing" class="modal-mask" @click.self="supplementing = false">
      <div class="modal">
        <h3>补录缺项 · {{ supplementForm.修剪编号 }}</h3>
        <ul v-if="supplementReasons.length" class="reason-list">
          <li v-for="reason in supplementReasons" :key="reason">待补：{{ reason }}</li>
        </ul>
        <div class="form-item">
          <label>造型要求</label>
          <input v-model="supplementForm.造型要求" placeholder="补填造型要求，未填不能提交修剪" />
        </div>
        <div class="form-item">
          <label>作业日期</label>
          <input v-model="supplementForm.作业日期" placeholder="YYYY-MM-DD" />
        </div>
        <div class="form-item">
          <label>修剪量（人工补录）</label>
          <input v-model="supplementForm.修剪量" placeholder="取不到数时在此手工补录数值" />
        </div>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="supplementing = false">取消</button>
          <button class="btn primary" type="button" :disabled="submitting" @click="submitSupplement">保存补录</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, any>

const ENDPOINT = '/api/prune'
const router = useRouter()
const columns = ['修剪编号', '修剪对象', '修剪类型', '修剪量', '造型要求', '作业日期', '操作人员', '修剪状态']
const statuses = ['待修剪', '修剪中', '已完成', '需返工', '待补']

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const successMessage = ref('')
const loadFailed = ref(false)
const busyId = ref<number | null>(null)
const filters = ref<{ keyword: string; status: string }>({ keyword: '', status: '' })

const boardStats = ref<Record<string, number>>({ 待修剪: 0, 修剪中: 0, 已完成: 0, 待返工: 0, 待补: 0 })
const statCards = computed(() => [
  { label: '待修剪任务', value: boardStats.value['待修剪'] ?? 0 },
  { label: '修剪中任务', value: boardStats.value['修剪中'] ?? 0 },
  { label: '已完成任务', value: boardStats.value['已完成'] ?? 0 },
  { label: '待返工', value: boardStats.value['待返工'] ?? 0, danger: true },
  { label: '待补项', value: boardStats.value['待补'] ?? 0, danger: true },
])

// 登记弹窗
const creating = ref(false)
const submitting = ref(false)
const createFields = [
  { name: '修剪编号', label: '修剪编号', required: true, placeholder: '如 PRUN-0008' },
  { name: '修剪对象', label: '修剪对象', required: true, placeholder: '对象不能为空' },
  { name: '修剪类型', label: '修剪类型', required: true, placeholder: '如 疏枝修剪 / 绿篱平剪' },
  { name: '造型要求', label: '造型要求', required: false, placeholder: '可后补，但提交修剪前必须填写' },
  { name: '作业日期', label: '作业日期', required: false, placeholder: 'YYYY-MM-DD' },
  { name: '操作人员', label: '操作人员', required: false, placeholder: '' },
]
const createForm = reactive<Record<string, string>>({})

// 补录弹窗
const supplementing = ref(false)
const supplementId = ref<number | null>(null)
const supplementForm = reactive<Row>({})
const supplementReasons = ref<string[]>([])

// 返回列表时恢复原位置（筛选 + 滚动），键与详情页保持一致
const SCROLL_KEY = 'prune-list-scroll'
function savePosition() {
  sessionStorage.setItem('prune-list-filter', JSON.stringify(filters.value))
  sessionStorage.setItem(SCROLL_KEY, String(window.scrollY))
}

function resetFilters() {
  filters.value = { keyword: '', status: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function statusClass(row: Row) {
  if (row._待补) return 'tag-pending'
  if (row._status === '需返工') return 'tag-rework'
  if (row._status === '已完成') return 'tag-done'
  return 'tag-normal'
}

function qtyClass(row: Row) {
  if (row._修剪量状态 === 'failed') return 'qty-failed'
  if (row._修剪量状态 === 'empty') return 'qty-empty'
  if (row['修剪量'] === '待补') return 'qty-empty'
  return 'qty-ok'
}

// 动作按钮随状态给出，避免对不能执行的动作白点
function availableActions(row: Row): { name: string; label: string; primary?: boolean }[] {
  switch (row._status) {
    case '待修剪':
      return [{ name: '安排修剪', label: '安排修剪' }]
    case '修剪中':
      return [{ name: '开始修剪', label: '提交修剪结果', primary: true }]
    case '已完成':
      return [{ name: '返工登记', label: '返工登记' }]
    case '需返工':
      return [{ name: '返工完成', label: '返工接回', primary: true }]
    case '待补':
      return []
    default:
      return []
  }
}

function flashError(message: string) {
  errorMessage.value = message
  successMessage.value = ''
}
function flashSuccess(message: string) {
  successMessage.value = message
  errorMessage.value = ''
}

async function reload() {
  errorMessage.value = ''
  successMessage.value = ''
  loadFailed.value = false
  const params = new URLSearchParams()
  if (filters.value.keyword) params.set('keyword', filters.value.keyword.trim())
  if (filters.value.status) params.set('status', filters.value.status)
  try {
    const [listRes, statsRes] = await Promise.all([
      request(`${ENDPOINT}?${params.toString()}`),
      request(`${ENDPOINT}/stats`),
    ])
    if (!listRes.ok || !statsRes.ok) throw new Error('接口返回异常')
    const payload = await listRes.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    boardStats.value = await statsRes.json()
  } catch {
    // 取数失败与「空清单」必须区分：这里是加载失败，给重试入口而不是显示空白
    loadFailed.value = true
    rows.value = []
    flashError('修剪任务列表读取失败，可点「重新加载」重试')
  }
}

async function loadStats() {
  try {
    const res = await request(`${ENDPOINT}/stats`)
    if (res.ok) boardStats.value = await res.json()
  } catch {
    /* 看板数字失败不阻断列表，下次刷新会再取 */
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  successMessage.value = ''
  busyId.value = row.id
  try {
    const res = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await res.json()
    if (!payload.ok) {
      flashError(payload.message || '修剪动作未生效')
      // 缺项被拦成待补时，刷新出待补原因
      await reload()
      return
    }
    flashSuccess(payload.message || '操作已生效')
    await reload()
  } catch {
    flashError('修剪造型操作失败，请稍后重试')
  } finally {
    busyId.value = null
  }
}

async function retryQuantity(row: Row) {
  errorMessage.value = ''
  successMessage.value = ''
  busyId.value = row.id
  try {
    const res = await request(`${ENDPOINT}/${row.id}/quantity`, { method: 'POST' })
    const payload = await res.json()
    if (payload.ok) flashSuccess(payload.message)
    else flashError(payload.message)
    await reload()
  } catch {
    flashError('修剪量取数请求失败，可再次重试')
  } finally {
    busyId.value = null
  }
}

function openCreate() {
  Object.keys(createForm).forEach((key) => delete createForm[key])
  errorMessage.value = ''
  creating.value = true
}

async function submitCreate() {
  const missing = createFields.filter((f) => f.required && !String(createForm[f.name] || '').trim())
  if (missing.length) {
    flashError(`缺少必填字段：${missing.map((f) => f.label).join('、')}`)
    return
  }
  submitting.value = true
  try {
    const res = await request(ENDPOINT, { method: 'POST', body: JSON.stringify({ values: { ...createForm } }) })
    const payload = await res.json()
    if (!payload.ok) {
      flashError(payload.message)
      return
    }
    creating.value = false
    flashSuccess(payload.message)
    await reload()
  } catch {
    flashError('修剪任务登记失败，请稍后重试')
  } finally {
    submitting.value = false
  }
}

function openSupplement(row: Row) {
  supplementId.value = row.id
  supplementReasons.value = row._缺项 ?? []
  supplementForm.修剪编号 = row['修剪编号']
  supplementForm.造型要求 = row['造型要求'] === '待补' ? '' : row['造型要求']
  supplementForm.作业日期 = row['作业日期'] === '—' ? '' : row['作业日期']
  supplementForm.修剪量 = ''
  supplementing.value = true
  errorMessage.value = ''
}

async function submitSupplement() {
  if (supplementId.value === null) return
  const values: Record<string, string> = {}
  if (String(supplementForm.造型要求 || '').trim()) values['造型要求'] = supplementForm.造型要求
  if (String(supplementForm.作业日期 || '').trim()) values['作业日期'] = supplementForm.作业日期
  if (String(supplementForm.修剪量 || '').trim()) values['修剪量'] = supplementForm.修剪量
  if (!Object.keys(values).length) {
    flashError('请至少补录一项内容')
    return
  }
  submitting.value = true
  try {
    const res = await request(`${ENDPOINT}/${supplementId.value}`, {
      method: 'PATCH',
      body: JSON.stringify({ values }),
    })
    const payload = await res.json()
    if (!payload.ok) {
      flashError(payload.message)
      return
    }
    supplementing.value = false
    flashSuccess(payload.message)
    await reload()
  } catch {
    flashError('补录保存失败，请稍后重试')
  } finally {
    submitting.value = false
  }
}

function openDetail(row: Row) {
  savePosition()
  void router.push(`/prune/${row.id}`)
}

onMounted(async () => {
  // 从详情返回时恢复筛选条件，再回到原处
  const savedFilter = sessionStorage.getItem('prune-list-filter')
  if (savedFilter) {
    try {
      filters.value = JSON.parse(savedFilter)
    } catch {
      /* 忽略损坏的缓存 */
    }
  }
  await reload()
  const savedScroll = sessionStorage.getItem(SCROLL_KEY)
  if (savedScroll) {
    window.scrollTo(0, Number(savedScroll))
    sessionStorage.removeItem(SCROLL_KEY)
  }
})
</script>
