import { expect, test, type Page } from '@playwright/test'
import path from 'node:path'

const fixture = path.resolve('tests/fixtures/synthetic-group.png')

async function clickPhoto(page: Page, x: number, y: number) {
  const host = page.getByRole('application', { name: /照片标注画布/ })
  const box = (await host.boundingBox())!
  const scale = Math.min((box.width - 40) / 1200, (box.height - 40) / 700)
  await host.click({
    position: {
      x: (box.width - 1200 * scale) / 2 + x * 1200 * scale,
      y: (box.height - 700 * scale) / 2 + y * 700 * scale,
    },
  })
}

test('无模型时的上传、增删、撤销、时间编辑、保存、历史与删除', async ({ page }) => {
  const errors: string[] = []
  const external: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.route('**/*', (route) => {
    if (!new URL(route.request().url()).hostname.match(/^(127\.0\.0\.1|localhost)$/)) {
      external.push(route.request().url())
      return route.abort()
    }
    return route.continue()
  })
  await page.goto('/')
  await expect(page.getByText(/未安装人头检测模型/)).toBeVisible()
  await page.getByLabel('选择合照文件').setInputFiles(fixture)
  await expect(page.getByRole('application')).toBeVisible()
  await expect(page.getByText('正在加载照片…')).toHaveCount(0)
  await expect(page.getByTestId('head-count')).toHaveText('0')
  await page.getByRole('button', { name: '加人头', exact: true }).click()
  await clickPhoto(page, 0.25, 0.4)
  await clickPhoto(page, 0.6, 0.4)
  await expect(page.getByTestId('head-count')).toHaveText('2')
  await page.getByRole('button', { name: '撤销', exact: true }).click()
  await expect(page.getByTestId('head-count')).toHaveText('1')
  await page.getByRole('button', { name: '重做', exact: true }).click()
  await expect(page.getByTestId('head-count')).toHaveText('2')
  await page.getByRole('button', { name: '减人头', exact: true }).click()
  await clickPhoto(page, 0.6, 0.4)
  await expect(page.getByTestId('head-count')).toHaveText('1')
  await page.getByLabel('拍照时间', { exact: true }).fill('2024-03-12T09:35')
  const saving = page.waitForResponse(
    (response) => response.url().endsWith('/api/records') && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: '保存结果', exact: true }).click()
  const saved = await (await saving).json()
  expect(saved.head_count).toBe(1)
  expect(saved.captured_at).toBe('2024-03-12T01:35:00+00:00')
  expect(saved.marks[0].x).toBeCloseTo(0.25, 2)
  expect(saved.marks[0].y).toBeCloseTo(0.4, 2)
  await expect(page.getByRole('button', { name: '保存结果', exact: true })).toBeDisabled()
  await page.reload()
  await page.getByRole('button', { name: '历史记录', exact: true }).click()
  await page.getByRole('button', { name: /打开记录 synthetic-group.png/ }).click()
  await expect(page.getByTestId('head-count')).toHaveText('1')
  await expect(page.getByLabel('拍照时间', { exact: true })).toHaveValue('2024-03-12T09:35')
  await expect(page.getByText('正在加载照片…')).toHaveCount(0)
  // Resize changes the canvas fit transform; the saved normalized mark must still be clickable.
  await page.setViewportSize({ width: 1000, height: 850 })
  await page.waitForTimeout(250)
  await page.getByRole('button', { name: '减人头', exact: true }).click()
  await clickPhoto(page, 0.25, 0.4)
  await expect(page.getByTestId('head-count')).toHaveText('0')
  await page.getByRole('button', { name: '撤销', exact: true }).click()
  await page.getByRole('button', { name: '历史记录', exact: true }).click()
  await page.getByRole('button', { name: '删除此记录' }).click()
  await page.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(page.getByText('还没有保存的合照')).toBeVisible()
  expect(errors).toEqual([])
  expect(external).toEqual([])
})

test('未保存替换提示与网络保存失败不丢标注', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('选择合照文件').setInputFiles(fixture)
  await expect(page.getByText('正在加载照片…')).toHaveCount(0)
  await page.getByRole('button', { name: '加人头', exact: true }).click()
  await clickPhoto(page, 0.5, 0.5)
  await expect(page.getByTestId('head-count')).toHaveText('1')
  await page.getByRole('button', { name: '新建识别', exact: true }).click()
  await expect(page.getByText('离开当前照片？', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '继续编辑', exact: true }).click()
  await page.route('**/api/records', (route) =>
    route.request().method() === 'POST' ? route.abort() : route.continue(),
  )
  await page.getByRole('button', { name: '保存结果', exact: true }).click()
  await expect(page.getByText(/无法连接本地服务/)).toBeVisible()
  await expect(page.getByTestId('head-count')).toHaveText('1')
  await expect(page.getByRole('button', { name: '保存结果', exact: true })).toBeEnabled()
  await page.screenshot({ path: 'test-results/editor-desktop.png', fullPage: true })
})

test('拖动标记、缩放后添加与移动端布局', async ({ page, request }) => {
  await page.goto('/')
  await page.getByLabel('选择合照文件').setInputFiles(fixture)
  await expect(page.getByRole('application')).toBeVisible()
  await expect(page.getByText('正在加载照片…')).toHaveCount(0)
  await page.getByRole('button', { name: '加人头', exact: true }).click()
  await clickPhoto(page, 0.3, 0.4)
  await page.getByRole('button', { name: '查看 / 移动', exact: true }).click()
  const host = page.getByRole('application')
  const box = (await host.boundingBox())!
  const fit = Math.min((box.width - 40) / 1200, (box.height - 40) / 700)
  const point = (x: number, y: number) => ({
    x: box.x + (box.width - 1200 * fit) / 2 + x * 1200 * fit,
    y: box.y + (box.height - 700 * fit) / 2 + y * 700 * fit,
  })
  const from = point(0.3, 0.4)
  const to = point(0.45, 0.6)
  await page.mouse.move(from.x, from.y)
  await page.mouse.down()
  await page.mouse.move(to.x, to.y, { steps: 12 })
  await page.mouse.up()
  await page.getByRole('button', { name: '放大照片', exact: true }).click()
  await page.getByRole('button', { name: '加人头', exact: true }).click()
  await host.click({ position: { x: box.width / 2, y: box.height / 2 } })
  await expect(page.getByTestId('head-count')).toHaveText('2')
  const saving = page.waitForResponse(
    (response) => response.url().endsWith('/api/records') && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: '保存结果', exact: true }).click()
  const saved = await (await saving).json()
  expect(
    saved.marks.some(
      (m: { x: number; y: number }) => Math.abs(m.x - 0.45) < 0.01 && Math.abs(m.y - 0.6) < 0.01,
    ),
  ).toBe(true)
  expect(
    saved.marks.some(
      (m: { x: number; y: number }) => Math.abs(m.x - 0.5) < 0.01 && Math.abs(m.y - 0.5) < 0.01,
    ),
  ).toBe(true)
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('button', { name: '加人头', exact: true })).toBeVisible()
  await expect(page.getByLabel('拍照时间', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  )
  await page.screenshot({ path: 'test-results/editor-mobile.png', fullPage: true })
  await request.delete(`/api/records/${saved.id}`)
})
