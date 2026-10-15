"""Offline adapter for single-class YOLOv8/11 raw ONNX outputs (no embedded NMS)."""

import ast
import hashlib
import json
import threading
import time
from pathlib import Path
from uuid import uuid4

import numpy as np
from PIL import Image


class ModelUnavailable(RuntimeError):
    pass


def nms(boxes: np.ndarray, scores: np.ndarray, threshold: float = 0.45) -> list[int]:
    if len(boxes) == 0:
        return []
    order = np.argsort(-scores, kind="stable")[:10000]
    keep = []
    area = np.maximum(0, boxes[:, 2] - boxes[:, 0]) * np.maximum(0, boxes[:, 3] - boxes[:, 1])
    while len(order) and len(keep) < 2000:
        i = int(order[0])
        keep.append(i)
        rest = order[1:]
        intersection = np.prod(
            np.maximum(
                0,
                np.minimum(boxes[i, 2:], boxes[rest, 2:])
                - np.maximum(boxes[i, :2], boxes[rest, :2]),
            ),
            axis=1,
        )
        iou = intersection / np.maximum(area[i] + area[rest] - intersection, 1e-9)
        order = rest[iou <= threshold]
    return keep


def tile_origins(length: int, size: int = 1024, overlap: float = 0.25) -> list[int]:
    if length <= size:
        return [0]
    starts = list(range(0, length - size + 1, int(size * (1 - overlap))))
    if starts[-1] != length - size:
        starts.append(length - size)
    return starts


class HeadDetector:
    def __init__(self, model_path: Path, provider: str = "CPUExecutionProvider"):
        self.path = model_path
        self.provider = provider
        self._session = None
        self._manifest = None
        self._lock = threading.Lock()
        self.last_error = None

    def _load(self):
        with self._lock:
            if self._session is not None:
                return
            if not self.path.is_file():
                raise ModelUnavailable(
                    "未安装人头检测模型。请按 models/README.md 安装；仍可手动标注。"
                )
            manifest_path = self.path.with_suffix(".json")
            if not manifest_path.is_file():
                raise ModelUnavailable("缺少模型清单 JSON，请使用模型安装工具安装。")
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                for key in ("name", "sha256", "source_url", "license", "input_size"):
                    if not manifest.get(key):
                        raise ValueError(f"缺少字段 {key}")
                if (
                    manifest.get("task") != "head-detection"
                    or manifest.get("output_format") != "yolov8-raw-single-class"
                ):
                    raise ValueError("仅支持单类 head 的 YOLOv8 原始输出")
                digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
                if digest != manifest["sha256"]:
                    raise ValueError("模型 SHA256 与清单不一致")
                import onnxruntime as ort

                if self.provider not in ort.get_available_providers():
                    raise ValueError(f"执行后端不可用: {self.provider}")
                options = ort.SessionOptions()
                options.intra_op_num_threads = 2
                session = ort.InferenceSession(
                    str(self.path), sess_options=options, providers=[self.provider]
                )
                if len(session.get_inputs()) != 1 or len(session.get_outputs()) != 1:
                    raise ValueError("需要一个输入和一个原始输出，不能包含 NMS")
                inp = session.get_inputs()[0]
                size = int(manifest["input_size"])
                if size < 128 or size > 2048 or size % 32:
                    raise ValueError("输入尺寸须为 128～2048 范围内的 32 倍数")
                if inp.type != "tensor(float)" or len(inp.shape) != 4:
                    raise ValueError("输入必须为 float32 NCHW")
                for got, want in zip(inp.shape, [1, 3, size, size]):
                    if isinstance(got, int) and got != want:
                        raise ValueError("输入尺寸与清单不一致")
                # Refuse a known person/face model even if incorrectly described in its sidecar.
                names = session.get_modelmeta().custom_metadata_map.get("names")
                if not names:
                    raise ValueError("缺少 names 类别元数据，无法确认这是人头模型")
                parsed = ast.literal_eval(names)
                labels = list(parsed.values()) if isinstance(parsed, dict) else parsed
                if (
                    not isinstance(labels, (list, tuple))
                    or len(labels) != 1
                    or str(labels[0]).lower() not in ("head", "heads", "human_head", "human head")
                ):
                    raise ValueError(f"模型类别不是单类 head: {names}")
                self._decode(
                    session.run(None, {inp.name: np.zeros((1, 3, size, size), dtype=np.float32)})[0]
                )
                self._session = session
                self._manifest = manifest
                self.last_error = None
            except ModelUnavailable:
                raise
            except Exception as exc:
                raise ModelUnavailable(f"模型不可用：{exc}") from exc

    @staticmethod
    def _decode(output: np.ndarray) -> np.ndarray:
        if output.ndim != 3 or output.shape[0] != 1:
            raise ValueError("输出必须为 [1,5,N] 或 [1,N,5]")
        arr = output[0]
        if arr.shape[0] == 5:
            arr = arr.T
        elif arr.shape[1] != 5:
            raise ValueError("模型不是单类 head 原始输出，不接受 person/多类/NMS 模型")
        return arr

    def status(self) -> dict:
        try:
            self._load()
            return {
                "ready": True,
                "name": self._manifest["name"],
                "provider": self._session.get_providers()[0],
                "error": None,
            }
        except ModelUnavailable as exc:
            self.last_error = str(exc)
            return {"ready": False, "name": None, "provider": self.provider, "error": str(exc)}

    def _predict_crop(self, image: Image.Image, confidence: float):
        size = int(self._manifest["input_size"])
        ratio = min(size / image.width, size / image.height)
        resized = image.resize(
            (round(image.width * ratio), round(image.height * ratio)), Image.Resampling.BILINEAR
        )
        left = (size - resized.width) // 2
        top = (size - resized.height) // 2
        canvas = Image.new("RGB", (size, size), (114, 114, 114))
        canvas.paste(resized, (left, top))
        tensor = np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0
        raw = self._decode(self._session.run(None, {self._session.get_inputs()[0].name: tensor})[0])
        raw = raw[np.all(np.isfinite(raw), axis=1) & (raw[:, 4] >= confidence) & (raw[:, 4] <= 1)]
        boxes = np.empty((len(raw), 4), dtype=np.float32)
        boxes[:, :2] = raw[:, :2] - raw[:, 2:4] / 2
        boxes[:, 2:] = raw[:, :2] + raw[:, 2:4] / 2
        boxes -= np.array([left, top, left, top])
        boxes /= ratio
        boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, image.width)
        boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, image.height)
        valid = np.all(boxes[:, 2:] > boxes[:, :2], axis=1)
        return boxes[valid], raw[valid, 4]

    def detect(self, image_path: Path, mode: str = "standard") -> dict:
        self._load()
        started = time.perf_counter()
        with Image.open(image_path) as source:
            image = source.convert("RGB")
        crops = [(0, 0, image.width, image.height)]
        if mode == "fine" and max(image.size) > 1024:
            crops += [
                (x, y, min(x + 1024, image.width), min(y + 1024, image.height))
                for y in tile_origins(image.height)
                for x in tile_origins(image.width)
            ]
        all_boxes, all_scores = [], []
        for x1, y1, x2, y2 in crops:
            boxes, scores = self._predict_crop(image.crop((x1, y1, x2, y2)), 0.25)
            boxes += np.array([x1, y1, x1, y1])
            all_boxes.append(boxes)
            all_scores.append(scores)
        boxes = np.concatenate(all_boxes)
        scores = np.concatenate(all_scores)
        marks = []
        for i in nms(boxes, scores):
            box = (
                boxes[i] / np.array([image.width, image.height, image.width, image.height])
            ).tolist()
            marks.append(
                {
                    "id": str(uuid4()),
                    "x": (box[0] + box[2]) / 2,
                    "y": (box[1] + box[3]) / 2,
                    "bbox": box,
                    "source": "auto",
                    "confidence": float(scores[i]),
                    "is_modified": False,
                }
            )
        return {
            "marks": marks,
            "model_version": f"{self._manifest['name']}@{self._manifest['sha256'][:12]}",
            "config": {
                "mode": mode,
                "confidence": 0.25,
                "nms_iou": 0.45,
                "input_size": self._manifest["input_size"],
                "provider": self._session.get_providers()[0],
                "tiles": len(crops),
            },
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
