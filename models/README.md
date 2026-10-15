# 默认人头模型与手动替换

## 随项目提供的默认模型

项目内置当前使用的 **yolo-head-medium**，安装 Python/npm 依赖后即可使用，不需要另外寻找或下载权重。

```text
models/
├── head-detector.onnx       # Git 管理的默认 medium，103625405 字节
├── head-detector.json       # SHA256、固定上游来源、输入尺寸
├── NOTICE.md               # 许可不一致和来源声明，分发前必读
├── UPSTREAM_MODEL_CARD.md  # 固定提交的上游模型卡原文
├── AGPL-3.0.txt             # ONNX 声明涉及的 AGPL 完整条款
└── local/                  # 用户自己的模型覆盖，整个目录不入 Git
```

来源：[trysem/YOLOv8_head_detector](https://huggingface.co/trysem/YOLOv8_head_detector/blob/5f9ba067b61589b3c8120059601a016c548006b5/yolo-head-medium.onnx)。

SHA256：`19ae628e67095520fabe7b21eb54d2fd1c1dae93099cae68213b58d52aaa3e63`。

已确认上游公布的 LFS 对象 SHA256 与本地字节一致；本项目使用**普通 Git**存储真实 ONNX，不使用 LFS 指针，完整源代码 ZIP 同样包含权重。文件约 98.825 MiB，低于 GitHub 普通 Git 单文件 100 MiB 限制，但已接近上限。未来更大的默认权重需要另行设计分发方式，不能简单继续添加；仅本地使用的自定义模型不受这个 Git 限制影响。

**许可注意：上游模型卡标注 MIT，ONNX 内嵌声明 AGPL-3.0，适用许可尚未统一核实。** 本地纳入 Git 不代表已经解决公开再分发的授权问题。完整声明、证据和源码入口见 [NOTICE.md](NOTICE.md)，公开发布前应向相关权利人澄清。

默认 medium 已通过 CPU 加载及标准/切片推理链路检查，但尚未完成真实教室照片的准确率验收。medium 通常比 nano 更慢，是否更准确须用同一批真实照片比较。

## 模型选择优先级

1. 显式 `HEADCOUNT_MODEL_PATH` 环境变量。
2. `models/local/head-detector.onnx` 本地覆盖。
3. 随项目提供的 `models/head-detector.onnx`。

每个模型都需要同名 `.json` 清单。路径在应用启动时选择，修改后需要重启后端，无需重建前端。

如果发现本地覆盖的模型或清单残留，但两者不完整、哈希不一致或模型不兼容，会明确提示错误，**不会悄悄退回默认模型**。这可避免你以为正在使用新模型，实际却仍是旧模型。

## 手动安装新模型

1. 停止 HeadCount 服务。
2. 取得可信且有相应授权的 `.onnx`。
3. 在项目根目录运行，替换实际参数：

```powershell
.\backend\.venv\Scripts\python.exe -m app.model_cli install `
  --path 'D:\Models\your-head-model.onnx' `
  --name '<模型名称与版本>' `
  --source '<真实来源URL或固定版本>' `
  --license '<已核实的许可或授权说明>' `
  --input-size 640 `
  --accept-license
```

未设置环境变量时，工具写入：

```text
models/local/head-detector.onnx
models/local/head-detector.json
```

验证通过后自动生成清单，**不会覆盖随 Git 提供的默认模型**。已经有本地覆盖时，先备份，再添加 `--replace`。如果有发布者提供的 SHA256，可添加 `--sha256 <值>`；`--accept-license` 只是你的确认，不会自动授予许可。

```powershell
# 检查当前实际选择的模型（输出包含绝对路径）
.\backend\.venv\Scripts\python.exe -m app.model_cli doctor

# 仅检查内置默认模型，不受本地覆盖影响
.\backend\.venv\Scripts\python.exe -m app.model_cli doctor --bundled
```

退出码 0 表示格式可运行，2 表示缺失或不兼容。doctor 不代表识别准确率或许可审查已经达标。安装、检查工具不发出网络请求。

### 使用项目外的路径（可选）

安装时可通过 `--destination 'D:\Models\active-head.onnx'` 指定输出位置；随后在启动服务的同一终端设置：

```powershell
$env:HEADCOUNT_MODEL_PATH = 'D:\Models\active-head.onnx'
.\start.ps1
```

若未提供 `--destination`，但设置了 `HEADCOUNT_MODEL_PATH`，安装工具会将其作为目标路径。禁止把安装目标指向 Git 管理的默认模型。显式自定义目标不在默认/本地覆盖位置时，记得设置环境变量，否则不会被自动选中。

## 恢复内置默认 medium

先停止服务，再执行：

```powershell
# 仅清除此终端的显式覆盖；若配置了系统/用户级变量，需要同时取消
Remove-Item Env:HEADCOUNT_MODEL_PATH -ErrorAction SilentlyContinue
.\backend\.venv\Scripts\python.exe -m app.model_cli use-bundled
```

命令先确认内置模型可加载，再把 `models/local/` 内的模型和清单备份到 `backups/models/local-<时间>/`，移除本地覆盖。重启应用后使用默认 medium。外部路径的模型不会被删除；环境变量仍存在时，命令会提示先清除而不是假装切换成功。

Git 不会跟踪 `models/local/`、`backups/` 或其他任意放进 `models/` 的权重。只有默认模型和明确列出的说明文件允许提交，避免误发布个人模型或大文件。

## 支持的模型契约

- 单类别 head，不是 COCO `person`、人脸模型或人数回归。
- YOLOv8 / 兼容 YOLO11 原始输出格式，不含模型内 NMS。
- 单输入 `float32 [1,3,S,S]`，RGB，0～1，方形 letterbox 填充值 114。
- S 范围 128～2048，为 32 的倍数，默认 640。
- 单输出 `[1,5,N]` 或 `[1,N,5]`，字段为 `center_x, center_y, width, height, head_probability`。
- 坐标基于模型输入像素，概率已激活；`names` 元数据唯一类别为 `head`、`heads`、`human_head` 或 `human head`。
- 不支持 YOLOv5 objectness 格式、YOLO26/end-to-end/NMS 后输出、FP16、量化输入或 head/person 多类别模型。
- 使用可信、自包含 ONNX；哈希检查不是恶意模型扫描，不会证明模型质量或来源合法性。

不要把 person 模型改名为 head 绕过检查。

### 从可信 PyTorch 权重导出（可选）

在独立的导出环境中安装 Ultralytics / PyTorch / ONNX；日常推理不需要 PyTorch。仅加载自己训练或可信且授权清晰的 checkpoint，未知 `.pt` 的反序列化可能执行代码。

```text
yolo export model=你的head权重.pt format=onnx imgsz=640 batch=1 opset=17 dynamic=False simplify=False nms=False half=False device=cpu
```

具体选项以对应 Ultralytics 版本为准，导出 ONNX 不会自动清除原权重及底层组件的许可义务。

## 推理与验收

- 标准：整图推理，优先速度。
- 精细：整图 + 1024 像素切片，25% 重叠，统一回映后 NMS；CPU 耗时更长。
- 当前置信度阈值 0.25，NMS IoU 0.45，最多保留 2000 个候选。
- CPU intra-op 线程数为 2，模型常驻复用，一次运行一个识别任务。
- 切片并不保证消除边缘重复、遮挡和漏检，仍需人工核对。
- GPU 仅预留执行后端选择，需另配匹配的驱动、CUDA/cuDNN 与 GPU 版 Runtime；当前安装脚本按 CPU 配置。

真实样本评测见 [docs/model-validation.md](../docs/model-validation.md)。
