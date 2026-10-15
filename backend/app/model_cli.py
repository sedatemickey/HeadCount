"""Explicit offline model management; never downloads or unpickles unknown weights."""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .detection import HeadDetector


def install(args) -> int:
    if not args.accept_license:
        print("请先核对代码、权重和训练数据许可，再显式添加 --accept-license。", file=sys.stderr)
        return 2
    source = Path(args.path).expanduser().resolve()
    destination = (
        Path(
            getattr(args, "destination", None)
            or os.getenv("HEADCOUNT_MODEL_PATH")
            or config.local_model_path()
        )
        .expanduser()
        .resolve()
    )
    if destination == config.bundled_model_path().resolve():
        print(
            "内置模型由 Git 管理，不能通过安装命令覆盖。请使用 models/local/ 或 --destination 指定其他路径。",
            file=sys.stderr,
        )
        return 2
    if source.suffix.lower() != ".onnx" or not source.is_file():
        print("需要一个可信的本地 .onnx 文件，不接受 .pt/pickle。", file=sys.stderr)
        return 2
    if destination.suffix.lower() != ".onnx":
        print("目标路径必须以 .onnx 结尾。", file=sys.stderr)
        return 2
    sidecar = destination.with_suffix(".json")
    if (destination.exists() or sidecar.exists()) and not args.replace:
        print("本地模型已存在。停止服务并备份后，使用 --replace。", file=sys.stderr)
        return 2
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if args.sha256 and args.sha256.lower() != digest:
        print("SHA256 不一致，拒绝安装。", file=sys.stderr)
        return 2
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as staging:
        staged = Path(staging) / "head-detector.onnx"
        shutil.copy2(source, staged)
        manifest = {
            "name": args.name,
            "sha256": digest,
            "source_url": args.source,
            "license": args.license,
            "input_size": args.input_size,
            "task": "head-detection",
            "output_format": "yolov8-raw-single-class",
        }
        staged.with_suffix(".json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        status = HeadDetector(staged, config.Settings().provider).status()
        if not status["ready"]:
            print(json.dumps(status, ensure_ascii=False, indent=2), file=sys.stderr)
            return 2
        previous = Path(staging) / "previous"
        previous.mkdir()
        targets = (destination, sidecar)
        for target in targets:
            if target.exists():
                shutil.copy2(target, previous / target.name)
        # The service must be stopped: these are two individual atomic file replacements.
        try:
            os.replace(staged, destination)
            os.replace(staged.with_suffix(".json"), sidecar)
        except BaseException:
            for target in targets:
                backup = previous / target.name
                if backup.exists():
                    os.replace(backup, target)
                else:
                    target.unlink(missing_ok=True)
            raise
    print(
        f"已安装 {args.name}\n路径: {destination}\nSHA256: {digest}\n内置默认模型未修改。请重启服务，并使用真实照片验证效果。"
    )
    return 0


def use_bundled() -> int:
    if os.getenv("HEADCOUNT_MODEL_PATH"):
        print(
            "HEADCOUNT_MODEL_PATH 优先级最高，请先清除该环境变量再切回内置模型。", file=sys.stderr
        )
        return 2
    status = HeadDetector(config.bundled_model_path(), config.Settings().provider).status()
    if not status["ready"]:
        print(json.dumps(status, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    local = config.local_model_path()
    targets = [path for path in (local, local.with_suffix(".json")) if path.exists()]
    if not targets:
        print("当前已使用内置默认模型，无需切换。")
        return 0
    backup = (
        config.ROOT
        / "backups/models"
        / ("local-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    )
    backup.mkdir(parents=True, exist_ok=False)
    for target in targets:
        shutil.copy2(target, backup / target.name)
    try:
        for target in targets:
            target.unlink()
    except BaseException:
        for target in targets:
            shutil.copy2(backup / target.name, target)
        raise
    print(f"已切回内置默认模型。本地覆盖已备份到: {backup}\n请重启服务。")
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="HeadCount 离线模型安装、检查与切换")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="检查当前使用的模型")
    doctor.add_argument("--bundled", action="store_true", help="忽略本地覆盖，仅检查内置模型")
    sub.add_parser("use-bundled", help="停止服务后执行：备份本地覆盖并切回内置模型")
    installer = sub.add_parser("install", help="将可信 ONNX 安装为本地覆盖，不修改 Git 内置模型")
    installer.add_argument("--path", required=True)
    installer.add_argument("--name", required=True)
    installer.add_argument("--source", required=True, help="权重来源与版本 URL，仅记录，不发出请求")
    installer.add_argument("--license", required=True, help="核对后的许可标识/说明")
    installer.add_argument("--sha256", help="发布者提供的 SHA256，可用于校验下载完整性")
    installer.add_argument("--input-size", type=int, default=640)
    installer.add_argument("--accept-license", action="store_true")
    installer.add_argument("--replace", action="store_true")
    installer.add_argument(
        "--destination",
        type=Path,
        help="自定义输出 .onnx 路径；默认为环境变量路径或 models/local/head-detector.onnx",
    )
    args = parser.parse_args()
    if args.command == "install":
        return install(args)
    if args.command == "use-bundled":
        return use_bundled()
    settings = config.Settings()
    path = config.bundled_model_path() if args.bundled else settings.model_path
    status = HeadDetector(path, settings.provider).status()
    status["path"] = str(path.resolve())
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0 if status["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
