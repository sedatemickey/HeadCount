# HeadCount 实现说明

## 部署与依赖

- Vue 3 + TypeScript 静态前端与 FastAPI JSON API 分离。
- 开发由 Vite `/api` 代理访问，发布由 FastAPI 同源托管 `frontend/dist/`。
- SQLite + SQLAlchemy + Alembic 自动迁移，单机无需另装数据库服务。
- 单个后端进程、一个推理工作线程、一个 ONNX Session；暂无 Redis/Celery。
- 默认只监听 127.0.0.1，校验 Host 与写操作 Origin。没有认证和多租户隔离，不是公网部署方案。

## 默认模型与本地覆盖

仓库内置 `models/head-detector.onnx`（medium）及哈希清单，直接由普通 Git 保存，不依赖 LFS 或启动时联网下载。上游固定版本和许可不一致见 `models/NOTICE.md`，技术内置不代表许可争议已解决。

读取优先级为 `HEADCOUNT_MODEL_PATH` > `models/local/head-detector.onnx` > 内置模型。即使本地只剩清单文件也视为用户指定了覆盖，加载失败时明确报错，不静默回退。路径在启动时决定，替换后需重启。

`app.model_cli install` 默认写入忽略目录 `models/local/`；可通过 `--destination` 或环境变量指定外部目标，但拒绝覆盖 Git 管理的默认路径。先验证临时模型，再替换本地文件对；正常文件替换异常时恢复旧文件对。异常退出/断电仍可能使文件对不完整，重新安装即可修复。

`app.model_cli use-bundled` 验证默认模型可运行后，备份并移除本地覆盖。显式环境变量存在时拒绝隐式清除配置，要求用户先取消该变量。备份、其他自定义模型、真实照片都不进入 Git。

## 生命周期

```text
POST /uploads
  校验 → 原始文件 / 展示图 / 缩略图 → uploads 临时元数据
POST /detection-jobs
  queued → running → succeeded / failed
  重启时 queued/running → interrupted
GET /detection-jobs/{id}
  前端轮询，返回检测点、框、置信度、模型与配置
用户修改标记和拍照时间
POST /records
  检查任务不在运行 → 拷贝临时目录到正式目录
  → 事务保存记录和最终标记 → 上传条目记录幂等关联
  → 成功后清理临时文件
GET /records、GET /records/{id}
PUT /records/{id}
  version 乐观并发校验 → 替换最终标记 → 服务端计数
DELETE /records/{id}
  先事务删除 DB → 删除照片；失败后交给孤立文件清理
```

上传成功后，临时文件和临时元数据已落盘，但不出现在历史列表；只有用户显式保存才产生正式记录。没有识别结果或识别失败都允许保存人工标注。0 人保存需要前端确认。

首次保存以唯一 upload_id 幂等。如果保存响应丢失，再次提交同一上传返回已保存的服务器状态，不重新覆盖它；需要进一步改动时走 PUT。前端采用服务器返回值作为新的编辑基线。

任务并发默认最多 4 个待处理/运行任务，按串行执行。同一个上传的未完成任务会复用，不重复排队。当前不提供取消推理，重启中断后可重试。

## 文件与 DB 一致性

Python 进程内 RLock 协调识别入队/状态切换、保存、删除和清理。这个锁不跨进程，因此不允许对同一数据目录开多个后端 worker。

文件拷贝与 SQLite 事务不具备跨资源原子性：

- 复制或 DB 保存失败：回滚 DB，移除部分正式目录，保留临时照片以重试。
- DB 已提交：返回成功，即使临时文件清理失败也不回滚正式记录。
- 复制之后、提交之前进程崩溃：产生的孤立目录超过 24 小时后清理。
- 删除先提交数据库；文件删除失败时之后清理孤立目录。
- 启动及每小时扫描过期临时数据与孤立目录，不清理正在 queued/running 的上传。

文件系统永久损坏、磁盘被外部修改、人工删除照片等不在事务恢复保证内；媒体接口将返回 404。备份需要同时包含 DB 与照片。

## 数据

- `uploads`：上传时间、原文件名、格式、尺寸、过期时间、已保存记录关联。
- `jobs`：任务状态、上传关联、模式、错误、原始检测结果。
- `records`：图片身份/尺寸、最终人数、拍照时间/时区、创建/更新时间、原始模型结果、模型与配置、编辑版本。
- `head_marks`：最终有效点位、可空框、来源、置信度、人工移动标志。

原始字节保留在 `original.*`；展示图统一转为 RGB JPEG 并去除 EXIF。所有标记以方向校正后的展示图尺寸为准，不写进原始文件。原图中的 GPS 等元数据仍可能存在。

自动标记含框和中心点；手动新增只有中心点，置信度为空。拖动自动标记后保留来源但标为人工调整，清除已经不再对应位置的框；原始模型框仍保留在 initial_detections 中。

删除自动标记不会抹去原始识别结果。当前没有逐次编辑审计日志，仅保存初始模型输出与最新最终状态。

后端验证 UUID、坐标范围、正面积框、标记 ID 不重复以及总数上限 2000；人数由最终标记长度重新计算，不接受前端独立 head_count 字段。

## 坐标与画布

- 标注坐标 `x,y∈[0,1]`，与屏幕分辨率无关。
- Konva Stage 管理平移与缩放；点击先逆变换到图片，再归一化。
- 在显示留白处点击不会添加标记。
- 缩放围绕指针位置，点击区域比可见圆点大，圆点大小保持屏幕尺度。
- 模型先反向消除 letterbox，再叠加切片偏移，最后归一化到完整图片。
- 使用 IoU NMS 合并同一人头候选，附近真实人头仍可能被误抑制，需实际调参验证。
- 窗口尺寸改变时重新适应窗口，点位不会变化；视图缩放/平移不计入未保存的业务修改。

## 时间

- uploaded_at 为后端上传完成时间；默认 captured_at 为该时间截断到分钟。
- 编辑框在记录保存的 IANA 时区中显示；不是直接假定浏览器本地时区。
- 前端显式转为 UTC ISO 字符串；后端要求 aware datetime，再次去除秒/微秒并统一 UTC。
- 用户保存时间优先；PUT 更新只改变 captured_at、最终标记及 updated_at，不改 uploaded_at 或 created_at。
- 重新打开历史记录仍用该记录自身时区，修改全局默认时区不会追溯改变历史记录。
- 第一版不自动读 EXIF 拍摄时间作为业务时间。

## HTTP API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 服务与本地模型状态、时区、图片限制 |
| POST | `/api/uploads` | multipart `file` |
| POST | `/api/detection-jobs` | `{upload_id, mode: standard 或 fine}` |
| GET | `/api/detection-jobs/{id}` | 状态及结果 |
| POST | `/api/records` | `{upload_id, captured_at, timezone, marks}` |
| GET | `/api/records?page=1&page_size=12` | 总量与分页摘要，按拍照时间倒序 |
| GET | `/api/records/{id}` | 完整记录、原始模型输出、最终标记 |
| PUT | `/api/records/{id}` | `{version, captured_at, timezone, marks}` |
| DELETE | `/api/records/{id}` | 204，无响应体 |
| GET | `/api/media/{uploads或records}/{id}/{original或display或thumbnail}` | 受控文件读取 |
| GET | `/api/openapi.json` | OpenAPI 机器可读文档 |

为保证离线，不使用依赖 CDN 的 Swagger/Redoc 页面。常见错误：422 无效输入，404 记录/文件/临时上传不存在，409 版本冲突或识别尚未结束，413 图片过大，429 队列满，503 模型未就绪。

## 限制与后续

- 已内置默认 medium，CPU 加载与推理通过；真实效果验收、许可不一致及手动更换说明见 models/README.md、models/NOTICE.md 及 model-validation.md。
- 没有身份识别、批量上传、视频检测、云同步或账号系统。
- 任务记录已落 DB，但推理队列是内存中的；不在重启后自动续跑。
- 前端未保存编辑在内存中；刷新前有浏览器离开提示，但浏览器崩溃时不能恢复，未实现草稿自动保存。
- 已保存照片若要重新自动识别，当前需重新上传原图；历史编辑支持位置和时间修改。
- 原图不加密；不提供加密备份和删除后的取证级擦除。
- GPU 只预留运行时选择，当前仅 CPU 测试；其他硬件后端需独立适配验收。
