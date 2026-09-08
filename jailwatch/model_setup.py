from __future__ import annotations

import hashlib
import os
import urllib.request
from pathlib import Path


def download_model(name="yolo11n.pt", directory=Path("models")):
    if name not in {"yolo11n.pt", "yolo11s.pt"}:
        raise ValueError("Choose yolo11n.pt or yolo11s.pt.")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    if target.is_file():
        return target
    url = "https://github.com/ultralytics/assets/releases/download/v8.3.0/" + name
    temporary = target.with_suffix(".pt.part")
    try:
        with urllib.request.urlopen(url, timeout=30) as source, temporary.open("wb") as output:
            total = 0
            while chunk := source.read(1024 * 1024):
                total += len(chunk)
                if total > 100 * 1024 * 1024:
                    raise ValueError("Unexpected model download size.")
                output.write(chunk)
        if total < 1024 * 1024:
            raise ValueError("Incomplete model download.")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def checksum(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
