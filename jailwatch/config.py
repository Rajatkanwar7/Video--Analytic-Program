from __future__ import annotations

import json
import math
import os
import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .geometry import polygons_overlap, validate_polygon


@dataclass
class Config:
    schema_version: int = 1
    camera_name: str = "Tower camera"
    source: str = ""
    source_env: str = ""
    model: str = "models/yolo11n.pt"
    device: str = "cpu"
    image_size: int = 960
    person_confidence: float = 0.45
    bird_confidence: float = 0.20
    semantic_interval_seconds: float = 0.5
    inside_zone: list = field(default_factory=list)
    outside_zone: list = field(default_factory=list)
    ignore_zones: list = field(default_factory=list)
    calibration_size: list = field(default_factory=list)
    processing_width: int = 1280
    warmup_seconds: float = 3.0
    background_threshold: float = 28.0
    min_blob_area_ratio: float = 0.000015
    max_blob_area_ratio: float = 0.004
    max_foreground_ratio: float = 0.20
    association_distance: float = 0.065
    max_track_gap_seconds: float = 0.30
    reset_gap_seconds: float = 0.75
    min_track_points: int = 4
    min_throw_speed: float = 0.12
    min_throw_displacement: float = 0.04
    max_throw_seconds: float = 2.5
    person_movement: float = 0.018
    person_confirm_seconds: float = 0.8
    cooldown_seconds: float = 8.0
    data_dir: str = "data"
    retention_days: int = 14
    max_events: int = 5000
    beep: bool = True
    open_timeout_ms: int = 5000
    read_timeout_ms: int = 3000
    reconnect_seconds: float = 2.0

    def validate(self, zones=True):
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("Unsupported configuration version. Use the setup screen.")
        for name in ("camera_name", "source", "source_env", "model", "device", "data_dir"):
            if not isinstance(getattr(self, name), str):
                raise ValueError(f"{name} must be text.")
        if not self.camera_name.strip() or len(self.camera_name) > 80:
            raise ValueError("Camera name must contain 1 to 80 characters.")
        if self.source_env and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.source_env):
            raise ValueError("Source environment variable name is invalid.")
        if not self.data_dir or not self.model:
            raise ValueError("Model and data directory are required.")
        bounds = {
            "image_size": (320, 1920), "person_confidence": (0.05, 1),
            "bird_confidence": (0.05, 1), "semantic_interval_seconds": (0.05, 5),
            "processing_width": (320, 3840), "warmup_seconds": (0.1, 60),
            "background_threshold": (4, 100), "min_blob_area_ratio": (0.000001, 0.1),
            "max_blob_area_ratio": (0.000002, 0.2), "max_foreground_ratio": (0.01, 0.9),
            "association_distance": (0.005, 0.3), "max_track_gap_seconds": (0.04, 2),
            "reset_gap_seconds": (0.1, 10), "min_track_points": (3, 30),
            "min_throw_speed": (0.001, 5), "min_throw_displacement": (0.005, 0.8),
            "max_throw_seconds": (0.1, 10), "person_movement": (0.001, 0.5),
            "person_confirm_seconds": (0.1, 30), "cooldown_seconds": (0, 600),
            "retention_days": (1, 365), "max_events": (50, 100000),
            "open_timeout_ms": (500, 30000), "read_timeout_ms": (500, 30000),
            "reconnect_seconds": (0.2, 60),
        }
        integer_fields = {"image_size", "processing_width", "min_track_points", "retention_days",
                          "max_events", "open_timeout_ms", "read_timeout_ms"}
        for name, (low, high) in bounds.items():
            v = getattr(self, name)
            if (isinstance(v, bool) or not isinstance(v, (int, float)) or
                    not math.isfinite(v) or not low <= v <= high):
                raise ValueError(f"{name} must be between {low} and {high}.")
            if name in integer_fields and not isinstance(v, int):
                raise ValueError(f"{name} must be a whole number.")
        if not isinstance(self.beep, bool):
            raise ValueError("beep must be true or false.")
        if self.min_blob_area_ratio >= self.max_blob_area_ratio:
            raise ValueError("Minimum object area must be smaller than maximum area.")
        if self.max_track_gap_seconds > self.reset_gap_seconds:
            raise ValueError("Track gap must be no larger than reset gap.")
        if not isinstance(self.calibration_size, list):
            raise ValueError("Calibration size must be a list.")
        if self.calibration_size:
            if (len(self.calibration_size) != 2 or
                    any(not isinstance(x, int) or x < 1 for x in self.calibration_size)):
                raise ValueError("Calibration size must be [width, height].")
        validate_polygon(self.inside_zone, "Inside zone", optional=not zones)
        validate_polygon(self.outside_zone, "Outside zone", optional=not zones)
        if self.inside_zone and self.outside_zone:
            if polygons_overlap(self.inside_zone, self.outside_zone):
                raise ValueError("Inside and outside zones must not overlap. A shared edge is allowed.")
        if not isinstance(self.ignore_zones, list):
            raise ValueError("Ignore zones must be a list.")
        for p in self.ignore_zones:
            validate_polygon(p, "Ignore zone")
        return self

    def resolved_source(self):
        source = os.environ.get(self.source_env, "") if self.source_env else self.source
        if not source.strip():
            raise ValueError("Set a video source in Setup (or set the configured environment variable).")
        if not (source.lower().startswith(("rtsp://", "rtsps://")) or Path(source).is_file()):
            raise ValueError("Source must be an existing video file or an RTSP URL.")
        return source


def load_config(path):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("Configuration must be a JSON object.")
    unknown = set(data) - {f.name for f in fields(Config)}
    if unknown:
        raise ValueError("Unknown configuration fields: " + ", ".join(sorted(unknown)))
    return Config(**data).validate(zones=False)


def save_config(config, path):
    config.validate(zones=False)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(asdict(config), handle, indent=2, allow_nan=False)
        handle.write("\n")
    os.replace(temporary, path)
    if os.name != "nt":
        path.chmod(0o600)
