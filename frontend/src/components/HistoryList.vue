<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Calendar, Delete, Refresh, Right } from '@element-plus/icons-vue'
import { request } from '../api'
import type { PhotoRecord } from '../types'
import { displayTime } from '../utils'
import { useEditor } from '../stores/editor'

const emit = defineEmits<{ open: [record: PhotoRecord] }>()
const editor = useEditor()
const items = ref<PhotoRecord[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const error = ref('')
const actionId = ref('')
let requestVersion = 0

async function load() {
  const version = ++requestVersion
  loading.value = true
  error.value = ''
  try {
    const result = await request<{ items: PhotoRecord[]; total: number }>(
      `/records?page=${page.value}&page_size=12`,
    )
    if (version !== requestVersion) return
    if (!result.items.length && page.value > 1) {
      page.value--
      await load()
      return
    }
    items.value = result.items
    total.value = result.total
  } catch (err) {
    if (version === requestVersion) error.value = (err as Error).message
  } finally {
    if (version === requestVersion) loading.value = false
  }
}

async function open(id: string) {
  if (actionId.value) return
  actionId.value = id
  try {
    emit('open', await request<PhotoRecord>(`/records/${id}`))
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    actionId.value = ''
  }
}

async function remove(record: PhotoRecord) {
  try {
    await ElMessageBox.confirm(
      `将永久删除这张合照及其 ${record.head_count} 个人头标记，无法撤销。`,
      '删除历史记录',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  actionId.value = record.id
  try {
    await request(`/records/${record.id}`, { method: 'DELETE' })
    if (editor.record?.id === record.id) editor.clear()
    ElMessage.success('记录已删除')
    await load()
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    actionId.value = ''
  }
}

onMounted(load)
</script>

<template>
  <section class="history-section">
    <div class="section-heading">
      <div>
        <span class="eyebrow">YOUR COLLECTION</span>
        <h1>每一次合照，都有记录。</h1>
        <p>已保存 {{ total }} 条记录，照片和标注仅存储在本机。</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="load">刷新记录</el-button>
    </div>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <div v-if="!loading && !items.length && !error" class="history-empty">
      <el-icon :size="42"><Calendar /></el-icon>
      <h2>还没有保存的合照</h2>
      <p>上传照片、核对人头，然后点击「保存结果」。</p>
    </div>
    <div v-loading="loading" class="history-grid" aria-label="历史记录列表">
      <article v-for="item in items" :key="item.id" class="history-card">
        <button
          class="history-image"
          :disabled="!!actionId"
          :aria-label="`打开记录 ${item.original_name}`"
          @click="open(item.id)"
        >
          <img :src="item.thumbnail_url" alt="已保存的合照缩略图" loading="lazy" />
          <span class="count-chip">{{ item.head_count }} 人</span>
        </button>
        <div class="history-card-body">
          <h3 :title="item.original_name">{{ item.original_name }}</h3>
          <p>
            <el-icon><Calendar /></el-icon>{{ displayTime(item.captured_at, item.timezone) }}
          </p>
          <div class="history-actions">
            <el-button
              text
              type="primary"
              :loading="actionId === item.id"
              :disabled="!!actionId && actionId !== item.id"
              @click="open(item.id)"
              >查看与编辑 <el-icon><Right /></el-icon
            ></el-button>
            <el-button
              text
              :icon="Delete"
              :disabled="!!actionId"
              aria-label="删除此记录"
              @click="remove(item)"
            />
          </div>
        </div>
      </article>
    </div>
    <el-pagination
      v-if="total > 12"
      v-model:current-page="page"
      :page-size="12"
      :total="total"
      layout="prev, pager, next"
      background
      @current-change="load"
    />
  </section>
</template>
