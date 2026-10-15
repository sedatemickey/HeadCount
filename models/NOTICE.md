# 默认模型来源与第三方声明

## 文件身份

- 本项目文件：`head-detector.onnx`，原文件名 `yolo-head-medium.onnx`。
- 模型：单类 head 的 YOLOv8 medium，FP32，640 × 640，原始检测输出。
- 大小：103,625,405 字节（约 98.825 MiB）。
- SHA256：`19ae628e67095520fabe7b21eb54d2fd1c1dae93099cae68213b58d52aaa3e63`。
- 用户提供的下载页面：https://huggingface.co/trysem/YOLOv8_head_detector/blob/main/yolo-head-medium.onnx
- 固定上游提交：`5f9ba067b61589b3c8120059601a016c548006b5`。
- 固定文件链接：https://huggingface.co/trysem/YOLOv8_head_detector/blob/5f9ba067b61589b3c8120059601a016c548006b5/yolo-head-medium.onnx
- 已核对上游 tree API 的 LFS SHA256 和文件大小，与本地字节一致；本项目仅重命名文件，未修改 ONNX 字节。

## 上游关系

上游模型卡称其为 [Abcfsa/YOLOv8_head_detector](https://github.com/Abcfsa/YOLOv8_head_detector) 的 ONNX 版本，原模型使用 [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics) 在 [SCUT-HEAD A/B](https://github.com/HCIILAB/SCUT-HEAD-Dataset-Release) 上训练。

本仓库保存固定提交的模型卡原文：[UPSTREAM_MODEL_CARD.md](UPSTREAM_MODEL_CARD.md)。这份来源说明不是对训练过程或数据授权的独立审计。

## 必须披露的许可不一致

**上游模型卡标注 MIT，但 ONNX 内嵌元数据声明 AGPL-3.0。当前无法据此确认一个统一、无争议的再分发许可。**

ONNX 中的相关原始元数据：

```text
author: Ultralytics
version: 8.4.23
license: AGPL-3.0 License (https://ultralytics.com/license)
description: Ultralytics medium model trained on mydata.yaml
```

这些可能是导出器写入的声明，不能单独证明原模型、训练数据及转换者各部分的授权。核查时，原始 Abcfsa 仓库未提供独立的 LICENSE 文件；不能替作者补写 MIT 版权归属，也不能以模型卡的一个标签消除底层组件的要求。

为保留已声明条款，本仓库附上 [AGPL-3.0 完整文本](AGPL-3.0.txt)，取自 Ultralytics `v8.4.23` 的 LICENSE：https://github.com/ultralytics/ultralytics/blob/v8.4.23/LICENSE 。保留该文本并不等于已满足所有源码提供、再分发或训练数据相关义务，也不等于将整个 HeadCount 项目擅自重新许可。

**公开发布、向第三方分发或商业使用前，应向相关权利人确认适用许可、对应源码及模型/数据条款，或更换为授权清晰的模型。不要将这个模型宣传为“无条件 MIT 可商用”。** 将文件纳入本地 Git 并不代表公开再分发条件已经满足。

上游代码与说明入口：

- ONNX 转换仓库：https://huggingface.co/trysem/YOLOv8_head_detector/tree/5f9ba067b61589b3c8120059601a016c548006b5
- 原模型仓库：https://github.com/Abcfsa/YOLOv8_head_detector
- 导出工具对应版本：https://github.com/ultralytics/ultralytics/tree/v8.4.23
- Ultralytics 许可说明：https://www.ultralytics.com/license

本项目没有去除或修改权重内部的署名/许可元数据。模型不附带识别准确率保证，实际教室照片仍需评测和人工核对。
