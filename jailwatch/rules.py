from __future__ import annotations

from dataclasses import dataclass

from .geometry import contains, distance
from .tracking import Tracker


@dataclass
class Candidate:
    kind: str
    source_time: float
    track_id: int
    box: tuple
    trajectory: list
    message: str


class RuleEngine:
    def __init__(self, config):
        self.config = config
        self.motion = Tracker(config.association_distance, config.max_track_gap_seconds)
        self.people = Tracker(0.12, max(1.5, 3 * config.semantic_interval_seconds))
        self.last_alert = {}

    def reset(self):
        self.motion.reset()
        self.people.reset()
        self.last_alert.clear()

    def permitted(self, kind, timestamp):
        return timestamp - self.last_alert.get(kind, -1e20) >= self.config.cooldown_seconds

    def emitted(self, kind, timestamp):
        self.last_alert[kind] = timestamp

    def crossing(self, boxes, timestamp):
        candidates = []
        c = self.config
        for track in self.motion.update(boxes, timestamp):
            last = track.history[-1]
            if any(contains(last.point, zone) for zone in c.ignore_zones):
                track.outside_start = None
                continue
            if track.outside_start and timestamp - track.outside_start.time > c.max_throw_seconds:
                track.outside_start = None
            if contains(last.point, c.outside_zone, False) and track.outside_start is None:
                track.outside_start = last
            if track.fired or track.outside_start is None:
                continue
            start = track.outside_start
            trail = [o for o in track.history if o.time >= start.time]
            elapsed = timestamp - start.time
            displacement = distance(start.point, last.point)
            if (contains(last.point, c.inside_zone, False) and len(trail) >= c.min_track_points and
                    elapsed > 0 and displacement >= c.min_throw_displacement and
                    displacement / elapsed >= c.min_throw_speed):
                track.fired = True
                candidates.append(Candidate(
                    "suspected_throw", timestamp, track.id, last.box,
                    [(o.time, *o.point) for o in trail],
                    "Small moving object crossed from outside to inside; review required."))
        return candidates

    def person_movement(self, boxes, timestamp):
        alerts = []
        for track in self.people.update(boxes, timestamp):
            current = track.history[-1]
            # A person's foot position determines zone occupancy.
            foot = ((current.box[0] + current.box[2]) / 2, current.box[3])
            if (not contains(foot, self.config.inside_zone) or
                    any(contains(foot, z) for z in self.config.ignore_zones)):
                track.person_start = None
                track.fired = False
                continue
            if track.person_start is None:
                track.person_start = current
            start = track.person_start
            if (not track.fired and timestamp - start.time >= self.config.person_confirm_seconds and
                    distance(start.point, current.point) >= self.config.person_movement):
                track.fired = True
                alerts.append(Candidate("person_movement", timestamp, track.id, current.box,
                    [(o.time, *o.point) for o in track.history], "Person moving in the inside zone."))
        return alerts
