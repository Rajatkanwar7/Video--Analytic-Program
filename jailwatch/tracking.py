from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .geometry import Box, center, distance


@dataclass(frozen=True)
class Observation:
    time: float
    box: Box

    @property
    def point(self):
        return center(self.box)


@dataclass
class Track:
    id: int
    history: deque = field(default_factory=lambda: deque(maxlen=100))
    outside_start: Observation | None = None
    fired: bool = False
    person_start: Observation | None = None


class Tracker:
    """Bounded, predictive, one-to-one association. Returns only freshly observed tracks."""
    def __init__(self, gate, max_gap, max_tracks=128):
        self.gate = gate
        self.max_gap = max_gap
        self.max_tracks = max_tracks
        self.tracks = {}
        self.next_id = 1

    def reset(self):
        self.tracks.clear()

    def update(self, boxes, timestamp):
        self.tracks = {k: t for k, t in self.tracks.items()
                       if 0 < timestamp - t.history[-1].time <= self.max_gap}
        candidates = []
        for tid, t in self.tracks.items():
            last = t.history[-1]
            predicted = last.point
            if len(t.history) >= 2:
                prev = t.history[-2]
                dt = last.time - prev.time
                if dt > 0:
                    ratio = min(2, (timestamp - last.time) / dt)
                    predicted = tuple(last.point[i] + (last.point[i] - prev.point[i]) * ratio for i in (0, 1))
            for idx, box in enumerate(boxes):
                score = distance(predicted, center(box))
                old_area = (last.box[2] - last.box[0]) * (last.box[3] - last.box[1])
                area = (box[2] - box[0]) * (box[3] - box[1])
                if score <= self.gate and 0.15 <= area / max(old_area, 1e-9) <= 6.5:
                    candidates.append((score, tid, idx))
        used_tracks, used_boxes, updated = set(), set(), []
        for _, tid, idx in sorted(candidates):
            if tid in used_tracks or idx in used_boxes:
                continue
            t = self.tracks[tid]
            t.history.append(Observation(timestamp, boxes[idx]))
            updated.append(t)
            used_tracks.add(tid)
            used_boxes.add(idx)
        for idx, box in enumerate(boxes):
            if idx not in used_boxes and len(self.tracks) < self.max_tracks:
                t = Track(self.next_id)
                self.next_id += 1
                t.history.append(Observation(timestamp, box))
                self.tracks[t.id] = t
                updated.append(t)
        return updated
