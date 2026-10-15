"""Offline localization evaluation against normalized head bounding boxes."""

import argparse
import json
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from .config import Settings
from .detection import HeadDetector


def matched_count(predictions, truth, threshold=0.5):
    """Maximum bipartite matching by IoU; don't cancel FP and FN through counts."""
    adjacency = []
    for predicted in predictions:
        box = np.asarray(predicted, dtype=float)
        candidates = []
        for i, target in enumerate(truth):
            gt = np.asarray(target, dtype=float)
            intersection = np.prod(
                np.maximum(0, np.minimum(box[2:], gt[2:]) - np.maximum(box[:2], gt[:2]))
            )
            union = np.prod(box[2:] - box[:2]) + np.prod(gt[2:] - gt[:2]) - intersection
            iou = intersection / max(float(union), 1e-9)
            if iou >= threshold:
                candidates.append((float(iou), i))
        adjacency.append([i for _, i in sorted(candidates, reverse=True)])
    assigned = {}

    def augment(pred, visited):
        for target in adjacency[pred]:
            if target in visited:
                continue
            visited.add(target)
            if target not in assigned or augment(assigned[target], visited):
                assigned[target] = pred
                return True
        return False

    for index in range(len(predictions)):
        augment(index, set())
    return len(assigned)


def evaluate(dataset_path: Path, detector, mode="standard", iou=0.5):
    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(data.get("images"), list) or not data["images"]:
        raise ValueError("评测集需要非空 images 数组")
    root = dataset_path.resolve().parent
    rows = []
    with tempfile.TemporaryDirectory(prefix="headcount-eval-") as temp:
        image_path = Path(temp) / "display.jpg"
        for entry in data["images"]:
            file = (root / entry["file"]).resolve()
            if not file.is_relative_to(root):
                raise ValueError("样本路径不能越过评测集目录")
            truth = entry["heads"]
            if not isinstance(truth, list) or any(
                len(box) != 4
                or not all(isinstance(n, (int, float)) and 0 <= n <= 1 for n in box)
                or box[0] >= box[2]
                or box[1] >= box[3]
                for box in truth
            ):
                raise ValueError(f"无效的归一化头部框: {entry['file']}")
            with Image.open(file) as image:
                ImageOps.exif_transpose(image).convert("RGB").save(image_path, quality=95)
            result = detector.detect(image_path, mode)
            boxes = [mark["bbox"] for mark in result["marks"]]
            matched = matched_count(boxes, truth, iou)
            rows.append(
                {
                    "file": entry["file"],
                    "expected": len(truth),
                    "predicted": len(boxes),
                    "true_positive": matched,
                    "false_negative": len(truth) - matched,
                    "false_positive": len(boxes) - matched,
                    "absolute_count_error": abs(len(boxes) - len(truth)),
                    "elapsed_seconds": result["elapsed_seconds"],
                }
            )
    tp = sum(row["true_positive"] for row in rows)
    fp = sum(row["false_positive"] for row in rows)
    fn = sum(row["false_negative"] for row in rows)
    return {
        "model": result["model_version"],
        "config": result["config"],
        "iou_threshold": iou,
        "images": len(rows),
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "mean_absolute_count_error": float(np.mean([row["absolute_count_error"] for row in rows])),
        "latency_mean_seconds": float(np.mean([row["elapsed_seconds"] for row in rows])),
        "latency_p95_seconds": float(np.percentile([row["elapsed_seconds"] for row in rows], 95)),
        "per_image": rows,
    }


def main():
    parser = argparse.ArgumentParser(description="本地合照模型评测；不上传任何数据")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--mode", choices=["standard", "fine"], default="standard")
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 0 < args.iou <= 1:
        parser.error("--iou 必须位于 (0,1]")
    settings = Settings()
    detector = HeadDetector(settings.model_path, settings.provider)
    if not detector.status()["ready"]:
        parser.error(detector.status()["error"])
    report = evaluate(args.dataset, detector, args.mode, args.iou)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "per_image"}, ensure_ascii=False, indent=2
        )
    )


if __name__ == "__main__":
    main()
