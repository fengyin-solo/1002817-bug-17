<template>
  <section class="page" data-module="prune-detail">
    <header class="page-head">
      <div>
        <h2>修剪任务详情</h2>
        <p class="page-desc">与列表同源读取，修剪量等字段两边保持一致。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="goBack">返回列表</button>
      </div>
    </header>

    <div v-if="loadError" class="error-panel">
      <span>修剪任务详情读取失败：{{ loadError }}。</span>
      <button class="btn" type="button" @click="loadEntry">重试</button>
    </div>
    <p v-else-if="loading" class="hint-text">修剪任务详情加载中…</p>

    <template v-else-if="entry">
      <div v-if="hasMissing" class="error-panel">
        <span>该单存在待补字段：{{ missingReason }}，请回列表取数或补录后再完工。</span>
      </div>

      <dl class="desc-list">
        <div v-for="field in fields" :key="field" class="desc-item">
          <dt>{{ field }}</dt>
          <dd :class="{ 'todo-cell': isMissing(field) }">{{ cellText(field) }}</dd>
        </div>
      </dl>

      <section v-if="reworkSnapshot" class="rework-panel">
        <h3>原修剪结果（返工可接回）</h3>
        <dl class="desc-list">
          <div class="desc-item">
            <dt>原状态</dt>
            <dd>{{ snapshotText('status') }}</dd>
          </div>
          <div class="desc-item">
            <dt>原修剪量</dt>
            <dd>{{ snapshotText('修剪量') }}</dd>
          </div>
          <div class="desc-item">
            <dt>原造型要求</dt>
            <dd>{{ snapshotText('造型要求') }}</dd>
          </div>
          <div class="desc-item">
            <dt>返工登记时间</dt>
            <dd>{{ snapshotText('登记时间') }}</dd>
          </div>
        </dl>
        <div v-if="statusOf === '需返工'" class="rework-actions">
          <button class="btn primary" type="button" :disabled="acting" @click="restore">
            {{ acting ? '接回中…' : '接回原修剪结果' }}
          </button>
          <span class="hint-text">接回后恢复原状态，已填的修剪量保持不变。</span>
        </div>
        <p v-if="actionMessage" class="feedback ok">{{ actionMessage }}</p>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

interface Entry {
  id: number | string
  [key: string]: unknown
}

const ENDPOINT = '/api/prune'
const fields = ["修剪编号", "修剪对象", "修剪类型", "修剪量", "修剪量来源", "造型要求", "作业日期", "操作人员", "修剪状态"]

const route = useRoute()
const router = useRouter()

const entry = ref<Entry | null>(null)
const loading = ref(false)
const loadError = ref('')
const acting = ref(false)
const actionMessage = ref('')

const entryId = String(route.params.id ?? '')

const missingFields = computed<string[]>(() => {
  const value = entry.value?.['待补字段']
  return Array.isArray(value) ? (value as string[]) : []
})
const hasMissing = computed(() => missingFields.value.length > 0)
const missingReason = computed(() => String(entry.value?.['待补原因'] ?? ''))
const statusOf = computed(() => String(entry.value?.['status'] ?? ''))
const reworkSnapshot = computed<Record<string, unknown> | null>(() => {
  const value = entry.value?.['原修剪结果']
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : null
})

function isMissing(field: string): boolean {
  const value = entry.value?.[field]
  const empty = value === null || value === undefined || String(value) === ''
  return empty && missingFields.value.includes(field)
}

function cellText(field: string): string {
  const value = entry.value?.[field]
  if (value !== null && value !== undefined && String(value) !== '') {
    return String(value)
  }
  return isMissing(field) ? '待补' : '—'
}

function snapshotText(field: string): string {
  const value = reworkSnapshot.value?.[field]
  return value !== null && value !== undefined && String(value) !== '' ? String(value) : '—'
}

async function loadEntry() {
  loading.value = true
  loadError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${entryId}`)
    if (!response.ok) {
      throw new Error(`接口返回 ${response.status}`)
    }
    entry.value = (await response.json()) as Entry
  } catch (error) {
    entry.value = null
    loadError.value = error instanceof Error ? error.message : '未知错误'
  } finally {
    loading.value = false
  }
}

async function restore() {
  if (acting.value) return
  acting.value = true
  actionMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${entryId}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action: '接回原结果' } }),
    })
    if (!response.ok) {
      throw new Error(`接口返回 ${response.status}，接回未生效`)
    }
    const result = (await response.json()) as { ok: boolean; message: string }
    actionMessage.value = result.message
    await loadEntry()
  } catch (error) {
    actionMessage.value = error instanceof Error ? error.message : '接回原修剪结果失败'
  } finally {
    acting.value = false
  }
}

function goBack() {
  // 返回列表要停在原处：有历史记录就回退（筛选、页码、滚动位置随之恢复），否则回列表首页
  if (window.history.state?.back) {
    router.back()
  } else {
    void router.push('/prune')
  }
}

onMounted(loadEntry)
</script>
