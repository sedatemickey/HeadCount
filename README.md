# HeadCount · 合照人数助手

一个前后端分离、带 SQLite 数据库的本地网页应用，用于合照人头定位、人工校正和历史记录管理。

**本项目包含默认 `yolo-head-medium` ONNX 权重**，克隆或下载完整项目、安装依赖后即可本地自动识别，无需自行寻找权重；也支持手动安装其他模型。应用不会自动下载模型或上传照片。真实教室合照的准确率仍需验收。

**分发注意：** 默认权重的上游模型卡标注 MIT，而 ONNX 内嵌声明为 AGPL-3.0，存在尚未澄清的许可不一致。来源、固定版本、哈希和声明见 [models/NOTICE.md](models/NOTICE.md)；公开分发前须确认相关授权，不能将其视为已核实的无条件 MIT 模型。

## 功能

- JPEG / PNG / WebP 上传；25 MB、4000 万像素限制，拒绝动画/多帧图片。
- 保留原始文件，生成 EXIF 方向校正后的展示图和缩略图。
- 本地单类 head ONNX 适配：标准整图识别、精细重叠切片、坐标回映与 NMS 去重。
- 圆点标注；加人头、减人头、拖动标记、撤销/重做；人数始终由有效标记数量计算。
- 滚轮缩放、图片平移、适应窗口、隐藏标记查看原图。
- 拍照时间默认使用后端上传时间，精确到分钟；保存尊重用户自定义时间。
- 保存照片、最终标记、人数、时间、原始识别结果及模型配置。
- 历史分页、重新编辑、删除；重复首次保存幂等、历史编辑版本冲突检测。
- 临时照片 24 小时后清理；服务重启将未完成任务标为中断并允许重试。
- 中文响应式界面，所有运行资源均来自本地，无字体/CDN/分析统计服务依赖。

## 技术栈

- 前端：Vue 3 / TypeScript / Vite / Pinia / Element Plus / Konva。
- 后端：Python / FastAPI / SQLAlchemy / Alembic / Pillow / ONNX Runtime。
- 数据库：SQLite（WAL）；照片保存在文件系统，数据库关联照片 ID、元数据与标记。

## 快速启动（Windows）

需要 **Python 3.11+（建议 3.12）**、**Node.js 22.12+（本机验证使用 24）**。首次安装需要联网下载依赖；日常使用可离线。

在项目根目录执行：

```powershell
# 首次安装/依赖变更时执行
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1

# 启动
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

打开 **http://127.0.0.1:8000**。之后可以直接双击 `start.cmd`；关闭终端或 Ctrl+C 停止服务。

如果当前代码刚由编码助手在本机安装完成，虚拟环境与前端构建已准备，可直接运行 `start.cmd`。

默认模型已经包含在 `models/head-detector.onnx`，安装脚本会检查当前模型是否能加载。权重约 98.8 MiB，使用普通 Git 存储，不是 LFS 指针，完整仓库的源码 ZIP 也包含真实权重。首次安装仍需联网获取 Python/npm 依赖，不是下载后无需安装即可运行。

### macOS / Linux

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -c backend/requirements-lock.txt -e ./backend
cd frontend
npm ci
npm run build
cd ..
bash start.sh
```

跨平台入口已提供；当前实际运行与浏览器测试在 Windows / Python 3.12 / Node 24 上完成。其他系统仍需各自验证 ONNX Runtime 安装和执行后端兼容性。

## 使用方式

1. 上传一张照片；模型就绪后自动发起识别，否则可直接点击「加人头」。
2. 加人头模式：点击漏检头部中心；减人头模式：点击错误圆点。
3. 查看/移动模式：拖动照片平移，拖动圆点微调。滚轮缩放；圆点颜色区分自动与手动。
4. 检查总数，修改拍照时间，然后「保存结果」。
5. 从「历史记录」重新打开、修改并再次保存。

快捷键：Ctrl+Z 撤销、Ctrl+Shift+Z 重做、Ctrl+S 保存；画布聚焦时 Home 适应窗口，+ / - 缩放，Delete 删除选中圆点。输入时间时不会拦截输入框的快捷键。

精细模式用于高分辨率小人头，会进行多次推理，CPU 耗时明显更长。识别过程中允许观察图片，但禁止修改/保存当前照片。查询中断时，点击「重新查询任务」，不要反复刷新丢失编辑状态。

## 手动更换模型与恢复默认

默认权重由 Git 管理，安装自定义模型不会覆盖它。先停止服务，在项目根目录运行（替换实际文件、来源和许可）：

```powershell
.\backend\.venv\Scripts\python.exe -m app.model_cli install `
  --path 'D:\Models\custom-head.onnx' `
  --name 'custom-head' `
  --source '<真实来源URL或版本>' `
  --license '<已确认的许可或授权说明>' `
  --input-size 640 `
  --accept-license

.\backend\.venv\Scripts\python.exe -m app.model_cli doctor
```

默认安装到 `models/local/head-detector.onnx` 与同名 `.json`，两者均被 Git 忽略。再次更换已有本地模型时，先备份，再添加 `--replace`。安装通过后重启服务生效，不需要重建前端。

模型选择优先级：**`HEADCOUNT_MODEL_PATH` 环境变量 > `models/local/` 本地覆盖 > 随仓库提供的默认模型**。损坏或不完整的本地覆盖会明确报错，不会悄悄换回默认模型。

要切回默认 medium，停止服务后执行：

```powershell
# 如果设置过此环境变量，先在启动服务的同一终端清除
Remove-Item Env:HEADCOUNT_MODEL_PATH -ErrorAction SilentlyContinue
.\backend\.venv\Scripts\python.exe -m app.model_cli use-bundled
```

该命令将本地覆盖备份到 `backups/models/` 后移除覆盖，再启动服务即使用默认模型。`doctor --bundled` 可以只检查默认权重。其他目录和模型格式要求见 [models/README.md](models/README.md)。

## 开发与验证

```powershell
# 安装测试工具（使用已验证版本约束）
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -TestTools

# 终端 1：后端（只启动一个进程）
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000

# 终端 2：前端（/api 代理到后端）
cd frontend
npm run dev
```

开发访问 http://127.0.0.1:5173。

```powershell
# 后端单元与接口测试
cd backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests migrations
cd ..\frontend
npm test
npm run build
npm audit

# 浏览器测试：自启独立前后端（默认 18000 / 15173），不复用或停止正在使用的应用
npx playwright install chromium
npm run test:e2e
```

浏览器测试使用系统临时目录的独立数据库，不修改你的正式记录；测试图片是合成图形，不是真实学生照片。若测试端口被占用，可设置 `HEADCOUNT_E2E_API_PORT` / `HEADCOUNT_E2E_WEB_PORT` 为其他不同的空闲端口后重试。

**验证边界：** 单元测试中的 ONNX 合成图用于验证 Runtime、坐标回映和 NMS；默认真实 medium 权重另做完整性、CPU 标准/切片推理和隔离保存流程检查。这些都不证明真实教室照片的准确率；实际漏检/误检/CPU 耗时评测仍待完成，见 [模型验收清单](docs/model-validation.md)。

## 配置

通过进程环境变量配置；默认不自动读取 `.env`。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `HEADCOUNT_DATA_DIR` | 项目下 `data/` | 数据库与照片目录 |
| `HEADCOUNT_MODEL_PATH` | 未设置时优先 `models/local/`，否则 `models/head-detector.onnx` | 显式指定模型文件；同目录须有同名 `.json` 清单 |
| `HEADCOUNT_TIMEZONE` | `Asia/Shanghai` | 新上传照片的时间显示时区 |
| `HEADCOUNT_PROVIDER` | `CPUExecutionProvider` | 可选 CUDA，需要额外匹配 GPU 环境 |

```powershell
$env:HEADCOUNT_DATA_DIR = 'D:\HeadCountData'
.\start.ps1
```

不要对同一个数据目录运行多个后端进程，不使用 `--workers`。当前任务队列和文件/数据库协调锁是单进程设计。

## 存储、备份与隐私

```text
data/
  app.db                 # SQLite；运行时可能还有 -wal / -shm
  photos/<记录ID>/
    original.jpg|png|webp # 原始字节，可能保留 EXIF/GPS
    display.jpg          # 校正方向，不包含 EXIF/GPS，标记不烧录进图片
    thumbnail.jpg
  temp/<上传ID>/         # 未保存照片，默认 24 小时过期
models/
  head-detector.onnx      # Git 内置的默认 medium
  head-detector.json      # 哈希与固定来源
  NOTICE.md              # 许可不一致与来源声明
  local/                 # 可选本地覆盖，不入 Git
```

- **备份前先停止后端**，复制整个 `data/` 目录，模型目录也建议备份。不能只复制数据库而漏掉照片；不要在运行中只拷贝 `app.db` 而忽略 WAL。
- 恢复：停止服务，替换完整数据目录，再启动；启动时自动执行数据库迁移。升级程序前务必备份。
- 本地数据未加密，任何具有该目录权限的本机用户都可能读取照片；建议配合系统磁盘加密和独立目录权限。
- 默认仅监听回环地址；没有账号系统，不应改成 `0.0.0.0` 后直接对外开放。
- 照片可能涉及未成年人隐私，应取得相应授权。本项目不识别身份，不推断姓名。
- `.gitignore` 排除数据、照片、自定义权重、备份、评测集和报告；仅默认模型及其清单/声明允许入 Git。不要强制提交私人照片或 `models/local/` 内容。

## 目录

```text
backend/app/            API、ORM、图片存储、任务、本地检测与模型工具
backend/migrations/     数据库版本迁移
backend/tests/          接口、Runtime 和故障场景测试
frontend/src/           工作台、标注画布、历史记录、Pinia 状态
frontend/tests/         Playwright 完整流程
models/                 默认权重、清单、来源声明与本地覆盖说明
docs/                   架构及真实模型验收
setup.ps1               安装依赖并构建
start.ps1 / start.cmd   Windows 本地启动
start.sh                Unix 本地启动
```

更多设计说明见 [docs/architecture.md](docs/architecture.md)。
