<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type Konva from 'konva'
import { useEditor } from '../stores/editor'
import { clamp, pointerToNormalized } from '../utils'

const editor = useEditor()
const host = ref<HTMLElement>()
const stageRef = ref<{ getNode(): Konva.Stage }>()
const width = ref(900)
const height = ref(550)
const image = ref<HTMLImageElement | null>(null)
const imageError = ref(false)
const scale = ref(1)
const position = ref({ x: 0, y: 0 })
const selected = ref<string | null>(null)
let observer: ResizeObserver | undefined
let loadVersion = 0
const fitScale = computed(() =>
  !editor.photo
    ? 1
    : Math.min((width.value - 40) / editor.photo.width, (height.value - 40) / editor.photo.height),
)
const zoomLabel = computed(() => `${Math.round(scale.value * 100)}%`)
const stageConfig = computed(() => ({
  width: width.value,
  height: height.value,
  x: position.value.x,
  y: position.value.y,
  scaleX: scale.value,
  scaleY: scale.value,
  draggable: editor.mode === 'view' && !editor.busy,
}))

function fit() {
  if (!editor.photo) return
  scale.value = fitScale.value
  position.value = {
    x: (width.value - editor.photo.width * scale.value) / 2,
    y: (height.value - editor.photo.height * scale.value) / 2,
  }
}

function zoom(factor: number, pointer = { x: width.value / 2, y: height.value / 2 }) {
  const next = clamp(scale.value * factor, fitScale.value * 0.5, fitScale.value * 12)
  const target = {
    x: (pointer.x - position.value.x) / scale.value,
    y: (pointer.y - position.value.y) / scale.value,
  }
  scale.value = next
  position.value = { x: pointer.x - target.x * next, y: pointer.y - target.y * next }
}

function wheel(event: Konva.KonvaEventObject<WheelEvent>) {
  event.evt.preventDefault()
  const pointer = stageRef.value?.getNode().getPointerPosition()
  if (pointer) zoom(event.evt.deltaY < 0 ? 1.12 : 1 / 1.12, pointer)
}

function addAt(event: Konva.KonvaEventObject<MouseEvent | TouchEvent>) {
  if (editor.mode !== 'add' || editor.busy || !editor.photo || !image.value) return
  const pointer = event.target.getStage()?.getPointerPosition()
  if (!pointer) return
  const point = pointerToNormalized(
    pointer,
    position.value,
    scale.value,
    editor.photo.width,
    editor.photo.height,
  )
  if (point) editor.add(point.x, point.y)
}

function clickMark(id: string, event: Konva.KonvaEventObject<MouseEvent | TouchEvent>) {
  event.cancelBubble = true
  if (editor.busy) return
  selected.value = id
  if (editor.mode === 'remove') {
    editor.remove(id)
    selected.value = null
  }
}

function moveMark(id: string, event: Konva.KonvaEventObject<DragEvent>) {
  event.cancelBubble = true
  if (editor.photo) {
    const x = clamp(event.target.x() / editor.photo.width)
    const y = clamp(event.target.y() / editor.photo.height)
    event.target.position({ x: x * editor.photo.width, y: y * editor.photo.height })
    editor.move(id, x, y)
  }
}

function panEnd(event: Konva.KonvaEventObject<DragEvent>) {
  if (event.target === stageRef.value?.getNode())
    position.value = { x: event.target.x(), y: event.target.y() }
}

function keydown(event: KeyboardEvent) {
  if (event.key === 'Delete' && selected.value && !editor.busy) {
    editor.remove(selected.value)
    selected.value = null
  }
  if (event.key === 'Home') {
    event.preventDefault()
    fit()
  }
  if (event.key === '+' || event.key === '=') zoom(1.2)
  if (event.key === '-') zoom(1 / 1.2)
}

async function loadImage() {
  const version = ++loadVersion
  image.value = null
  imageError.value = false
  selected.value = null
  if (!editor.photo) return
  const next = new Image()
  next.onload = async () => {
    if (version !== loadVersion) return
    image.value = next
    await nextTick()
    fit()
  }
  next.onerror = () => {
    if (version === loadVersion) imageError.value = true
  }
  next.src = editor.photo.image_url
}

watch(() => editor.photo?.image_url, loadImage, { immediate: true })
onMounted(() => {
  observer = new ResizeObserver((entries) => {
    const box = entries[0]!.contentRect
    width.value = Math.max(240, box.width)
    height.value = Math.max(280, box.height)
    fit()
  })
  if (host.value) observer.observe(host.value)
})
onBeforeUnmount(() => {
  observer?.disconnect()
  loadVersion++
})
</script>

<template>
  <div class="canvas-shell">
    <div
      ref="host"
      class="canvas-host"
      :class="`mode-${editor.mode}`"
      tabindex="0"
      role="application"
      aria-label="照片标注画布，可缩放拖动，点击添加或删除人头"
      @keydown="keydown"
    >
      <v-stage
        ref="stageRef"
        :config="stageConfig"
        @wheel="wheel"
        @click="addAt"
        @tap="addAt"
        @dragend="panEnd"
      >
        <v-layer>
          <v-image
            v-if="image && editor.photo"
            :config="{ image, width: editor.photo.width, height: editor.photo.height }"
          />
          <template v-if="editor.showMarks && image && editor.photo">
            <v-circle
              v-for="(mark, index) in editor.marks"
              :key="mark.id"
              :config="{
                id: mark.id,
                x: mark.x * editor.photo.width,
                y: mark.y * editor.photo.height,
                radius: (selected === mark.id ? 6 : 4.5) / scale,
                fill: mark.source === 'manual' ? '#f8b95f' : '#9fe165',
                stroke: selected === mark.id ? '#ffffff' : '#163830',
                strokeWidth: 1.5 / scale,
                hitStrokeWidth: 14 / scale,
                draggable: editor.mode === 'view' && !editor.busy,
                name: `head-${index + 1}`,
              }"
              @click="clickMark(mark.id, $event)"
              @tap="clickMark(mark.id, $event)"
              @mousedown="
                ($event: Konva.KonvaEventObject<MouseEvent>) => {
                  $event.cancelBubble = true
                }
              "
              @touchstart="
                ($event: Konva.KonvaEventObject<TouchEvent>) => {
                  $event.cancelBubble = true
                }
              "
              @dragend="moveMark(mark.id, $event)"
            />
          </template>
        </v-layer>
      </v-stage>
      <div v-if="!image" class="canvas-loading">
        <template v-if="imageError"
          >图片加载失败 <el-button text @click="loadImage">重新加载</el-button></template
        >
        <template v-else>正在加载照片…</template>
      </div>
      <div v-if="editor.activeJob" class="detection-badge">
        <span class="pulse-dot"></span>本地模型处理中
      </div>
      <div v-if="!editor.showMarks" class="original-badge">原图视图 · 标记已隐藏</div>
    </div>
    <div class="canvas-footer">
      <div class="legend">
        <span class="legend-dot auto"></span>自动识别
        <span class="legend-dot manual"></span>手动添加
      </div>
      <div class="zoom-controls">
        <button aria-label="缩小照片" @click="zoom(1 / 1.2)">−</button>
        <span>{{ zoomLabel }}</span>
        <button aria-label="放大照片" @click="zoom(1.2)">+</button>
        <button class="fit-button" @click="fit">适应窗口</button>
      </div>
    </div>
  </div>
</template>
