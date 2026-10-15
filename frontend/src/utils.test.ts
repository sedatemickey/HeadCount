import { describe, expect, it } from 'vitest'
import { localMinute, pointerToNormalized, utcMinute } from './utils'

describe('图片坐标', () => {
  it('正确处理缩放、平移与容器留白', () => {
    expect(pointerToNormalized({ x: 520, y: 280 }, { x: 20, y: 30 }, 0.5, 2000, 1000)).toEqual({
      x: 0.5,
      y: 0.5,
    })
    expect(pointerToNormalized({ x: 10, y: 20 }, { x: 20, y: 30 }, 0.5, 2000, 1000)).toBeNull()
  })
})

describe('分钟与时区', () => {
  it('上传时间按指定时区显示到分钟', () => {
    expect(localMinute('2024-03-12T01:35:48Z', 'Asia/Shanghai')).toBe('2024-03-12T09:35')
  })
  it('自定义时间与浏览器所在时区无关', () => {
    expect(utcMinute('2024-03-12T09:35', 'Asia/Shanghai')).toBe('2024-03-12T01:35:00.000Z')
    expect(utcMinute('2024-03-12T09:35', 'America/New_York')).toBe('2024-03-12T13:35:00.000Z')
  })
  it('拒绝空时间与无效时间', () => {
    expect(() => utcMinute('', 'Asia/Shanghai')).toThrow()
    expect(() => utcMinute('2024-02-31T09:35', 'Asia/Shanghai')).toThrow()
  })
})
