from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .geometry import overlap


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    box: tuple


class YoloDetector:
    """Construct and use on the same processing thread. No hidden model downloads."""
    def __init__(self, config):
        model_path = Path(config.model)
        if not model_path.is_file():
            raise ValueError("Model is missing. Run Download model, or select trusted local YOLO weights in Setup.")
        from ultralytics import YOLO
        self.model = YOLO(str(model_path), task="detect")
        self.config = config
        self.names = {int(i): str(n).strip().lower() for i, n in self.model.names.items()}
        if not {"person", "bird"}.issubset(set(self.names.values())):
            raise ValueError("The selected model must include classes named person and bird.")
        self.classes = [i for i, n in self.names.items() if n in ("person", "bird", "thrown_object")]

    def predict(self, image):
        c = self.config
        results = self.model.predict(image, conf=min(c.person_confidence, c.bird_confidence),
            imgsz=c.image_size, device=None if c.device == "auto" else c.device,
            classes=self.classes, verbose=False)[0]
        h, w = image.shape[:2]
        detections = []
        if results.boxes is not None:
            for row in results.boxes.data.cpu().tolist():
                x1, y1, x2, y2, confidence, class_id = row[:6]
                label = self.names[int(class_id)]
                threshold = c.bird_confidence if label == "bird" else c.person_confidence
                if confidence >= threshold:
                    detections.append(Detection(label, confidence, (x1 / w, y1 / h, x2 / w, y2 / h)))
        return detections


def suppressing_label(detections, blob, margin=0.012):
    for label in ("bird", "person"):
        if any(d.label == label and overlap(blob, d.box, margin) for d in detections):
            return label
    return None


def verify_candidate(detector, image, box):
    """Classify the actual event image and a contextual crop; never reuse stale boxes."""
    full = detector.predict(image)
    label = suppressing_label(full, box)
    if label:
        return label
    h, w = image.shape[:2]
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    half_w = max(64 / w, (box[2] - box[0]) * 3)
    half_h = max(64 / h, (box[3] - box[1]) * 3)
    x1, y1 = max(0, int((cx - half_w) * w)), max(0, int((cy - half_h) * h))
    x2, y2 = min(w, int((cx + half_w) * w)), min(h, int((cy + half_h) * h))
    if x2 <= x1 or y2 <= y1:
        return None
    crop_box = ((box[0] * w - x1) / (x2 - x1), (box[1] * h - y1) / (y2 - y1),
                (box[2] * w - x1) / (x2 - x1), (box[3] * h - y1) / (y2 - y1))
    return suppressing_label(detector.predict(image[y1:y2, x1:x2]), crop_box, margin=0.04)
