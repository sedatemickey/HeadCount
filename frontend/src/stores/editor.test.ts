import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useEditor } from './editor'
import type { PhotoRecord } from '../types'

function record(): PhotoRecord {
  return {
    id: crypto.randomUUID(),
    original_name: 'test.jpg',
    width: 100,
    height: 100,
    uploaded_at: '2024-01-01T00:00:00Z',
    captured_at: '2024-01-01T00:00:00Z',
    timezone: 'Asia/Shanghai',
    image_url: '/x',
    original_url: '/original',
    thumbnail_url: '/thumb',
    head_count: 0,
    detection_status: 'not_run',
    model_version: null,
    detection_config: null,
    initial_detections: [],
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    version: 1,
    marks: [],
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.unstubAllGlobals()
})

describe('标注编辑', () => {
  it('人数来自标记，增删与撤销重做保持一致', () => {
    const editor = useEditor()
    editor.openRecord(record())
    expect(editor.dirty).toBe(false)
    editor.add(0.2, 0.3)
    const id = editor.marks[0]!.id
    editor.add(0.7, 0.8)
    expect(editor.count).toBe(2)
    editor.remove(id)
    expect(editor.count).toBe(1)
    editor.undo()
    expect(editor.count).toBe(2)
    editor.redo()
    expect(editor.count).toBe(1)
    editor.undo()
    editor.undo()
    editor.undo()
    expect(editor.count).toBe(0)
    expect(editor.dirty).toBe(false)
  })

  it('移动时限制坐标，清除过时检测框，保留原始结果', () => {
    const editor = useEditor()
    const original = record()
    const point = {
      id: crypto.randomUUID(),
      x: 0.5,
      y: 0.5,
      bbox: [0.4, 0.4, 0.6, 0.6] as [number, number, number, number],
      source: 'auto' as const,
      confidence: 0.9,
      is_modified: false,
    }
    original.marks = [point]
    editor.openRecord(original)
    editor.move(point.id, -1, 2)
    expect(editor.marks[0]).toMatchObject({ x: 0, y: 1, is_modified: true, bbox: null })
    expect(original.marks[0]!.x).toBe(0.5)
    editor.undo()
    expect(editor.marks[0]!.bbox).toEqual(point.bbox)
  })

  it('时间修改触发未保存状态', () => {
    const editor = useEditor()
    editor.openRecord(record())
    expect(editor.capturedLocal).toBe('2024-01-01T08:00')
    editor.capturedLocal = '2020-01-01T12:30'
    expect(editor.dirty).toBe(true)
  })

  it('保存发送自定义时间和最终标记，不发送独立人数', async () => {
    const editor = useEditor()
    const original = record()
    editor.openRecord(original)
    editor.add(0.2, 0.3)
    editor.capturedLocal = '2020-01-01T12:30'
    const fetchMock = vi.fn().mockImplementation(async (_url, init) => {
      const body = JSON.parse(init.body)
      expect(body.captured_at).toBe('2020-01-01T04:30:00.000Z')
      expect(body.head_count).toBeUndefined()
      expect(body.marks).toHaveLength(1)
      return new Response(
        JSON.stringify({
          ...original,
          marks: body.marks,
          captured_at: body.captured_at,
          version: 2,
        }),
      )
    })
    vi.stubGlobal('fetch', fetchMock)
    await editor.save()
    expect(editor.dirty).toBe(false)
    expect(editor.count).toBe(1)
  })

  it('保存失败保留用户编辑', async () => {
    const editor = useEditor()
    editor.openRecord(record())
    editor.add(0.2, 0.3)
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    await expect(editor.save()).rejects.toThrow('无法连接本地服务')
    expect(editor.count).toBe(1)
    expect(editor.dirty).toBe(true)
    expect(editor.saving).toBe(false)
  })
})
