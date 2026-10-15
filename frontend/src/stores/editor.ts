import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { request } from '../api'
import type { DetectionJob, Health, Mark, Photo, PhotoRecord } from '../types'
import { clamp, cloneMarks, localMinute, utcMinute } from '../utils'

export const useEditor = defineStore('editor', () => {
  const health = ref<Health | null>(null)
  const healthError = ref('')
  const photo = ref<Photo | null>(null)
  const record = ref<PhotoRecord | null>(null)
  const marks = ref<Mark[]>([])
  const capturedLocal = ref('')
  const zone = ref('Asia/Shanghai')
  const mode = ref<'view' | 'add' | 'remove'>('view')
  const showMarks = ref(true)
  const uploading = ref(false)
  const saving = ref(false)
  const startingDetection = ref(false)
  const activeJob = ref<string | null>(null)
  const pollingError = ref('')
  const status = ref('')
  const baseline = ref('')
  const undoStack = ref<Mark[][]>([])
  const redoStack = ref<Mark[][]>([])
  const busy = computed(
    () => uploading.value || saving.value || startingDetection.value || Boolean(activeJob.value),
  )
  const snapshot = () =>
    JSON.stringify({ marks: marks.value, time: capturedLocal.value, zone: zone.value })
  const dirty = computed(() => !!photo.value && (!record.value || snapshot() !== baseline.value))
  const count = computed(() => marks.value.length)

  async function checkHealth() {
    try {
      health.value = await request<Health>('/health')
      healthError.value = ''
    } catch (error) {
      healthError.value = (error as Error).message
    }
  }

  function resetEditing() {
    undoStack.value = []
    redoStack.value = []
    mode.value = 'view'
    showMarks.value = true
    pollingError.value = ''
  }

  async function upload(file: File) {
    uploading.value = true
    try {
      const data = new FormData()
      data.append('file', file)
      const next = await request<Photo>('/uploads', { method: 'POST', body: data })
      photo.value = next
      record.value = null
      marks.value = []
      zone.value = next.timezone
      capturedLocal.value = localMinute(next.captured_at, next.timezone)
      baseline.value = ''
      resetEditing()
      status.value = '照片已上传，可自动识别或手动添加人头。'
    } finally {
      uploading.value = false
    }
  }

  function openRecord(next: PhotoRecord) {
    photo.value = next
    record.value = next
    marks.value = cloneMarks(next.marks)
    zone.value = next.timezone
    capturedLocal.value = localMinute(next.captured_at, next.timezone)
    resetEditing()
    baseline.value = snapshot()
    status.value = '已打开历史记录，修改后请重新保存。'
  }

  function commit(next: Mark[]) {
    undoStack.value.push(cloneMarks(marks.value))
    if (undoStack.value.length > 100) undoStack.value.shift()
    marks.value = next
    redoStack.value = []
  }

  function add(x: number, y: number) {
    if (busy.value || marks.value.length >= 2000) return
    commit([
      ...marks.value,
      {
        id: crypto.randomUUID(),
        x: clamp(x),
        y: clamp(y),
        bbox: null,
        source: 'manual',
        confidence: null,
        is_modified: false,
      },
    ])
  }

  function remove(id: string) {
    if (!busy.value) commit(marks.value.filter((mark) => mark.id !== id))
  }

  function move(id: string, x: number, y: number) {
    if (busy.value) return
    const old = marks.value.find((mark) => mark.id === id)
    if (!old || (Math.abs(old.x - x) < 0.00001 && Math.abs(old.y - y) < 0.00001)) return
    commit(
      marks.value.map((mark) =>
        mark.id === id
          ? { ...mark, x: clamp(x), y: clamp(y), bbox: null, is_modified: true }
          : mark,
      ),
    )
  }

  function undo() {
    if (busy.value || !undoStack.value.length) return
    redoStack.value.push(cloneMarks(marks.value))
    marks.value = undoStack.value.pop()!
  }

  function redo() {
    if (busy.value || !redoStack.value.length) return
    undoStack.value.push(cloneMarks(marks.value))
    marks.value = redoStack.value.pop()!
  }

  let polling = false
  async function pollJob() {
    if (!activeJob.value || polling) return
    polling = true
    pollingError.value = ''
    try {
      while (activeJob.value) {
        const job = await request<DetectionJob>(`/detection-jobs/${activeJob.value}`)
        if (job.status === 'succeeded' && job.result) {
          commit(cloneMarks(job.result.marks))
          status.value = `自动识别到 ${job.result.marks.length} 个人头，用时 ${job.result.elapsed_seconds} 秒。请核对并校正。`
          activeJob.value = null
        } else if (job.status === 'failed' || job.status === 'interrupted') {
          status.value = job.error || '识别未完成，可以重试或手动标注。'
          activeJob.value = null
        } else {
          status.value = job.status === 'queued' ? '等待本地识别…' : '正在本地识别，请稍候…'
          await new Promise((resolve) => setTimeout(resolve, 800))
        }
      }
    } catch (error) {
      pollingError.value = (error as Error).message
      // Do not unlock saving while the backend may still be processing the photograph.
    } finally {
      polling = false
    }
  }

  async function detect(quality: 'standard' | 'fine') {
    if (!photo.value || record.value || busy.value) return
    startingDetection.value = true
    try {
      const job = await request<{ id: string }>('/detection-jobs', {
        method: 'POST',
        body: JSON.stringify({ upload_id: photo.value.id, mode: quality }),
      })
      activeJob.value = job.id
      await pollJob()
    } finally {
      startingDetection.value = false
    }
  }

  async function save() {
    if (!photo.value || busy.value) return
    const capturedAt = utcMinute(capturedLocal.value, zone.value)
    saving.value = true
    try {
      const editing = record.value
      const body = {
        captured_at: capturedAt,
        timezone: zone.value,
        marks: marks.value,
        ...(editing ? { version: editing.version } : { upload_id: photo.value.id }),
      }
      const next = await request<PhotoRecord>(editing ? `/records/${editing.id}` : '/records', {
        method: editing ? 'PUT' : 'POST',
        body: JSON.stringify(body),
      })
      // Also use the server's canonical state on an idempotent retry.
      openRecord(next)
      status.value = '已保存到本机。'
    } finally {
      saving.value = false
    }
  }

  function clear() {
    photo.value = null
    record.value = null
    marks.value = []
    capturedLocal.value = ''
    resetEditing()
  }

  return {
    health,
    healthError,
    photo,
    record,
    marks,
    capturedLocal,
    zone,
    mode,
    showMarks,
    uploading,
    saving,
    activeJob,
    pollingError,
    status,
    busy,
    dirty,
    count,
    undoStack,
    redoStack,
    checkHealth,
    upload,
    openRecord,
    add,
    remove,
    move,
    undo,
    redo,
    detect,
    pollJob,
    save,
    clear,
  }
})
