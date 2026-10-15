<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Camera,
  Check,
  CirclePlus,
  Clock,
  Delete,
  Download,
  Files,
  FullScreen,
  Hide,
  Lock,
  MagicStick,
  Picture,
  Plus,
  RefreshLeft,
  RefreshRight,
  UploadFilled,
  View,
} from '@element-plus/icons-vue'
import PhotoCanvas from './components/PhotoCanvas.vue'
import HistoryList from './components/HistoryList.vue'
import { useEditor } from './stores/editor'
import type { PhotoRecord } from './types'
import { displayTime } from './utils'

const editor = useEditor()
const tab = ref<'editor' | 'history'>('editor')
const fileInput = ref<HTMLInputElement>()
const quality = ref<'standard' | 'fine'>('standard')
const dragOver = ref(false)
const autoCount = computed(() => editor.marks.filter((mark) => mark.source === 'auto').length)
const manualCount = computed(() => editor.count - autoCount.value)
const ready = computed(() => editor.health?.model.ready === true && !editor.healthError)
const modeHint = computed(() =>
  editor.mode === 'add'
    ? '点击照片中的漏检人头，添加一个标记。'
    : editor.mode === 'remove'
      ? '点击错误标记，将其移除。'
      : '滚轮缩放 · 拖动照片平移 · 拖动圆点调整位置',
)

async function canReplace() {
  if (editor.busy) {
    ElMessage.warning('请等待当前操作完成；连接中断时请先重新查询任务。')
    return false
  }
  if (!editor.dirty) return true
  try {
    await ElMessageBox.confirm('当前照片有未保存的内容，继续将放弃这些修改。', '离开当前照片？', {
      type: 'warning',
      confirmButtonText: '放弃并继续',
      cancelButtonText: '继续编辑',
    })
    return true
  } catch {
    return false
  }
}

async function chooseFile(file?: File) {
  if (!file || !(await canReplace())) return
  if (file.size > 25 * 1024 * 1024) {
    ElMessage.error('图片不能超过 25 MB')
    return
  }
  try {
    await editor.upload(file)
    tab.value = 'editor'
    await editor.checkHealth()
    if (ready.value) await editor.detect(quality.value)
    else ElMessage.info('本地模型尚未就绪，可以使用「加人头」手动标注。')
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function fileChanged(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  void chooseFile(file)
}

function drop(event: DragEvent) {
  event.preventDefault()
  dragOver.value = false
  void chooseFile(event.dataTransfer?.files[0])
}

async function detect() {
  if (editor.count) {
    try {
      await ElMessageBox.confirm(
        '识别成功后将替换当前标记（可以撤销）。拍照时间不会改变。',
        '重新识别',
        { confirmButtonText: '开始识别', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
  }
  try {
    await editor.detect(quality.value)
  } catch (error) {
    ElMessage.error((error as Error).message)
    await editor.checkHealth()
  }
}

async function save() {
  if (!editor.capturedLocal) {
    ElMessage.warning('请填写拍照时间')
    return
  }
  if (editor.count === 0) {
    try {
      await ElMessageBox.confirm('当前没有人头标记，确认保存为 0 人吗？', '确认人数', {
        confirmButtonText: '保存 0 人',
        cancelButtonText: '继续标注',
      })
    } catch {
      return
    }
  }
  try {
    await editor.save()
    ElMessage.success('照片与标注已保存到本机')
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function openRecord(record: PhotoRecord) {
  if (!(await canReplace())) return
  editor.openRecord(record)
  tab.value = 'editor'
}

async function newPhoto() {
  if (!(await canReplace())) return
  editor.clear()
  tab.value = 'editor'
}

function setMode(mode: 'view' | 'add' | 'remove') {
  editor.mode = mode
  editor.showMarks = true
}

function beforeUnload(event: BeforeUnloadEvent) {
  if (editor.dirty || editor.busy) {
    event.preventDefault()
    event.returnValue = ''
  }
}
function shortcuts(event: KeyboardEvent) {
  const target = event.target as HTMLElement
  if (target.closest('input, textarea, [contenteditable=true]') || tab.value !== 'editor') return
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
    event.preventDefault()
    event.shiftKey ? editor.redo() : editor.undo()
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    event.preventDefault()
    if (editor.photo && !editor.busy) void save()
  }
}
onMounted(() => {
  void editor.checkHealth()
  window.addEventListener('beforeunload', beforeUnload)
  window.addEventListener('keydown', shortcuts)
})
onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', beforeUnload)
  window.removeEventListener('keydown', shortcuts)
})
</script>

<template>
  <div class="app-layout">
    <header class="app-header">
      <a href="#" class="brand" @click.prevent="tab = 'editor'"
        ><span class="brand-symbol"
          ><el-icon><Camera /></el-icon></span
        ><span>HeadCount<span class="brand-caption">合照人数助手</span></span></a
      >
      <nav aria-label="主导航">
        <button :class="{ active: tab === 'editor' }" @click="tab = 'editor'">
          <el-icon><FullScreen /></el-icon>识别工作台
        </button>
        <button :class="{ active: tab === 'history' }" @click="tab = 'history'">
          <el-icon><Files /></el-icon>历史记录
        </button>
      </nav>
      <div class="privacy-pill">
        <el-icon><Lock /></el-icon>本地运行 · 照片不出设备
      </div>
    </header>

    <main>
      <input
        ref="fileInput"
        type="file"
        accept="image/jpeg,image/png,image/webp"
        class="sr-only"
        aria-label="选择合照文件"
        @change="fileChanged"
      />
      <HistoryList v-if="tab === 'history'" @open="openRecord" />
      <template v-else>
        <div class="section-heading">
          <div>
            <span class="eyebrow">A LITTLE HELP FOR EVERY GROUP PHOTO</span>
            <h1>{{ editor.photo ? '把每一个人，都数清楚。' : '一张合照，一个准确的数字。' }}</h1>
            <p>自动识别人头，轻松核对校正，为每次相聚留下一份完整记录。</p>
          </div>
          <el-button v-if="editor.photo" :icon="Plus" :disabled="editor.busy" @click="newPhoto"
            >新建识别</el-button
          >
        </div>
        <el-alert
          v-if="editor.healthError"
          :title="editor.healthError"
          type="error"
          show-icon
          :closable="false"
          class="service-alert"
        />
        <div v-if="!ready" class="model-notice">
          <el-icon><MagicStick /></el-icon
          ><span>{{ editor.health?.model.error || '正在连接本地识别服务…' }}</span
          ><el-button text size="small" @click="editor.checkHealth">重新检查</el-button>
        </div>

        <section v-if="!editor.photo" class="welcome-layout">
          <div
            class="upload-panel"
            :class="{ 'drag-over': dragOver }"
            @dragover.prevent="dragOver = true"
            @dragleave.prevent="dragOver = false"
            @drop="drop"
          >
            <span class="eyebrow">START WITH A PHOTO</span>
            <div class="upload-art" aria-hidden="true">
              <div class="art-photo">
                <span class="art-sun"></span>
                <div class="art-people"><i></i><i></i><i></i><i></i><i></i></div>
                <span class="art-corner tl"></span><span class="art-corner br"></span>
              </div>
              <span class="art-count"
                ><el-icon><Check /></el-icon>每个人，都看见</span
              >
            </div>
            <h2>上传一张班级合照</h2>
            <p>拖动照片到这里，或从电脑中选择文件</p>
            <el-button
              type="primary"
              size="large"
              :icon="UploadFilled"
              :loading="editor.uploading"
              @click="fileInput?.click()"
              >选择合照</el-button
            >
            <span class="upload-formats">JPG / PNG / WebP · 最大 25 MB · 最高 4000 万像素</span>
          </div>
          <aside class="welcome-guide">
            <div class="guide-title">
              <span class="eyebrow">HOW IT WORKS</span>
              <h2>从合照到记录，<br />只需三步。</h2>
            </div>
            <div class="guide-step">
              <span>01</span>
              <div>
                <h3>上传并自动识别</h3>
                <p>本地模型定位每个人头，不向第三方发送照片。</p>
              </div>
            </div>
            <div class="guide-step">
              <span>02</span>
              <div>
                <h3>核对，再轻松校正</h3>
                <p>放大检查后排人头，点击补充漏检或删除误检。</p>
              </div>
            </div>
            <div class="guide-step">
              <span>03</span>
              <div>
                <h3>确认时间，保存记录</h3>
                <p>设置真实拍照时间，随时回看照片和标注。</p>
              </div>
            </div>
            <div class="guide-note">
              <el-icon><Lock /></el-icon
              ><span>所有数据保存在你的电脑。首次安装完成后，无需联网使用。</span>
            </div>
          </aside>
        </section>

        <section v-else class="workspace-layout">
          <div class="workspace-main">
            <div class="editor-toolbar">
              <div class="tool-modes" role="group" aria-label="标注工具">
                <el-button
                  :class="{ selected: editor.mode === 'view' }"
                  :icon="View"
                  :disabled="editor.busy"
                  @click="setMode('view')"
                  >查看 / 移动</el-button
                >
                <el-button
                  :class="{ selected: editor.mode === 'add' }"
                  :icon="CirclePlus"
                  :disabled="editor.busy"
                  @click="setMode('add')"
                  >加人头</el-button
                >
                <el-button
                  :class="{ selected: editor.mode === 'remove' }"
                  :icon="Delete"
                  :disabled="editor.busy"
                  @click="setMode('remove')"
                  >减人头</el-button
                >
              </div>
              <div class="toolbar-secondary">
                <el-button
                  :icon="RefreshLeft"
                  :disabled="editor.busy || !editor.undoStack.length"
                  aria-label="撤销"
                  title="撤销 Ctrl+Z"
                  @click="editor.undo"
                />
                <el-button
                  :icon="RefreshRight"
                  :disabled="editor.busy || !editor.redoStack.length"
                  aria-label="重做"
                  title="重做 Ctrl+Shift+Z"
                  @click="editor.redo"
                />
                <el-button
                  :icon="editor.showMarks ? Hide : View"
                  @click="editor.showMarks = !editor.showMarks"
                  >{{ editor.showMarks ? '查看原图' : '显示标记' }}</el-button
                >
              </div>
            </div>
            <PhotoCanvas />
            <div class="editor-hint">
              <el-icon><Picture /></el-icon>{{ modeHint }}
            </div>
            <el-alert
              v-if="editor.pollingError"
              :title="editor.pollingError"
              type="error"
              :closable="false"
              show-icon
              ><el-button @click="editor.pollJob">重新查询任务</el-button></el-alert
            >
            <div class="status-line" role="status">
              <span :class="['status-dot', { saved: !editor.dirty }]"></span>{{ editor.status }}
            </div>
          </div>
          <aside class="result-panel">
            <div class="result-header">
              <span class="eyebrow">COUNTING RESULT</span
              ><span class="save-state" :class="{ unsaved: editor.dirty }">{{
                editor.dirty ? '未保存' : '已保存'
              }}</span>
            </div>
            <div class="head-count">
              <span data-testid="head-count">{{ editor.count }}</span
              ><span>人</span>
            </div>
            <p class="count-description">当前人头总数</p>
            <div class="count-breakdown">
              <div>
                <span class="legend-dot auto"></span>自动标记 <b>{{ autoCount }}</b>
              </div>
              <div>
                <span class="legend-dot manual"></span>手动添加 <b>{{ manualCount }}</b>
              </div>
            </div>
            <div class="panel-divider"></div>
            <label class="field-label" for="captured-time"
              ><el-icon><Clock /></el-icon>拍照时间</label
            >
            <input
              id="captured-time"
              v-model="editor.capturedLocal"
              type="datetime-local"
              step="60"
              :disabled="editor.busy"
              class="time-input"
              aria-label="拍照时间"
            />
            <p class="field-note">默认使用上传时间，可修改到分钟。<br />时区：{{ editor.zone }}</p>
            <div v-if="!editor.record" class="recognition-settings">
              <label class="field-label">识别模式</label>
              <el-radio-group v-model="quality" :disabled="editor.busy" size="small"
                ><el-radio-button value="standard">标准 · 更快</el-radio-button
                ><el-radio-button value="fine">精细 · 小人头</el-radio-button></el-radio-group
              >
              <el-button
                class="detect-button"
                :icon="MagicStick"
                :disabled="editor.busy || !ready"
                @click="detect"
                >{{ editor.activeJob ? '识别中…' : '重新识别' }}</el-button
              >
            </div>
            <div class="photo-meta">
              <el-icon><Picture /></el-icon>
              <div>
                <strong :title="editor.photo.original_name">{{ editor.photo.original_name }}</strong
                ><span>{{ editor.photo.width }} × {{ editor.photo.height }} px</span>
              </div>
            </div>
            <a
              class="original-link"
              :href="editor.photo.original_url"
              target="_blank"
              rel="noopener"
              ><el-icon><Download /></el-icon>打开原始照片</a
            >
            <el-button
              class="save-button"
              type="primary"
              size="large"
              :icon="Check"
              :loading="editor.saving"
              :disabled="editor.busy || !editor.capturedLocal || !editor.dirty"
              @click="save"
              >保存结果</el-button
            >
            <p class="save-note">照片、标记与拍照时间将一起保存。</p>
            <div v-if="editor.record" class="saved-meta">
              最近保存<br />{{ displayTime(editor.record.updated_at, editor.zone) }}
            </div>
          </aside>
        </section>
      </template>
    </main>
    <footer class="app-footer">
      <span>HEADCOUNT <span class="footer-separator">/</span> 数清人数，记住相聚。</span
      ><span
        ><el-icon><Lock /></el-icon>LOCAL FIRST · PRIVATE BY DESIGN</span
      >
    </footer>
  </div>
</template>
