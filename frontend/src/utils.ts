import { formatInTimeZone, fromZonedTime } from 'date-fns-tz'

export const clamp = (n: number, min = 0, max = 1) => Math.min(max, Math.max(min, n))

export function pointerToNormalized(
  pointer: { x: number; y: number },
  position: { x: number; y: number },
  scale: number,
  width: number,
  height: number,
) {
  const x = (pointer.x - position.x) / scale / width
  const y = (pointer.y - position.y) / scale / height
  return x >= 0 && x <= 1 && y >= 0 && y <= 1 ? { x, y } : null
}

export function localMinute(iso: string, zone: string): string {
  return formatInTimeZone(iso, zone, "yyyy-MM-dd'T'HH:mm")
}

export function utcMinute(local: string, zone: string): string {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(local)) throw new Error('请选择完整的拍照时间')
  const value = fromZonedTime(local, zone)
  if (!Number.isFinite(value.getTime()) || localMinute(value.toISOString(), zone) !== local) {
    throw new Error('拍照时间无效，请重新选择')
  }
  return value.toISOString()
}

export function displayTime(iso: string, zone: string): string {
  return formatInTimeZone(iso, zone, 'yyyy-MM-dd HH:mm')
}

export function cloneMarks<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}
