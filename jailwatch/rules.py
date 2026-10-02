from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

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
    direction: str = ""
    context: dict = field(default_factory=dict)

    @property
    def cooldown_key(self):
        return f"{self.kind}:{self.direction}" if self.direction else self.kind


class RuleEngine:
    def __init__(self, config):
        self.config = config
        self.motion = Tracker(config.association_distance, config.max_track_gap_seconds)
        self.people = Tracker(0.12, max(1.5, 3 * config.semantic_interval_seconds))
        self.last_alert = {}
        self.person_observations = deque(maxlen=512)

    def reset(self):
        self.motion.reset()
        self.people.reset()
        self.last_alert.clear()
        self.person_observations.clear()

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
                track.origin_side = ""
                continue
            if track.outside_start and timestamp - track.outside_start.time > c.max_throw_seconds:
                track.outside_start = None
                track.origin_side = ""
            side = ("outside" if contains(last.point, c.outside_zone, False) else
                    "inside" if contains(last.point, c.inside_zone, False) else "")
            if side and track.outside_start is None:
                # outside_start is retained as a compatibility name for the origin observation.
                track.outside_start = last
                track.origin_side = side
            if track.fired or track.outside_start is None or not side or side == track.origin_side:
                continue
            direction = f"{track.origin_side}_to_{side}"
            if c.crossing_direction not in ("both", direction):
                continue
            start = track.outside_start
            trail = [o for o in track.history if o.time >= start.time]
            elapsed = timestamp - start.time
            displacement = distance(start.point, last.point)
            if (len(trail) >= c.min_track_points and elapsed > 0 and
                    displacement >= c.min_throw_displacement and displacement / elapsed >= c.min_throw_speed):
                track.fired = True
                candidates.append(Candidate(
                    "suspected_throw", timestamp, track.id, last.box,
                    [(o.time, *o.point) for o in trail],
                    f"Small moving object crossed {direction.replace('_', ' ')}; review required.", direction))
        return candidates

    def person_context(self, candidate):
        """Nearby people before the observed launch are context, never proof of a throw."""
        if not self.config.fence_zone or not candidate.trajectory:
            return {"nearby_person": False, "context_available": bool(self.config.fence_zone)}
        started, x, y = candidate.trajectory[0]
        origin = self.config.outside_zone if candidate.direction.startswith("outside") else self.config.inside_zone
        matches = []
        for t, tid, box, foot, near in self.person_observations:
            if not near or not 0 <= started-t <= self.config.person_context_seconds or not contains(foot,origin):
                continue
            # Distance to a person's bounding box supports throws from a hand above the feet.
            dx = max(box[0]-x, 0, x-box[2]); dy = max(box[1]-y, 0, y-box[3])
            separation = (dx*dx+dy*dy)**0.5
            if separation <= self.config.launch_person_distance:
                matches.append((separation, -t, tid))
        if not matches:
            return {"nearby_person": False, "context_available": True}
        separation, negative_time, tid = min(matches)
        return {"nearby_person": True, "context_available": True, "person_track_id": tid,
                "person_source_time": -negative_time, "launch_distance_normalized": round(separation,4),
                "meaning": "Person near fence and observed launch area; involvement is unconfirmed."}

    def person_movement(self, boxes, timestamp):
        alerts = []
        c = self.config
        while self.person_observations and timestamp-self.person_observations[0][0] > c.person_context_seconds+c.max_throw_seconds+2:
            self.person_observations.popleft()
        for track in self.people.update(boxes, timestamp):
            current = track.history[-1]
            foot = ((current.box[0] + current.box[2]) / 2, current.box[3])
            ignored = any(contains(foot, z) for z in c.ignore_zones)
            near = bool(c.fence_zone) and contains(foot, c.fence_zone) and not ignored
            self.person_observations.append((timestamp,track.id,current.box,foot,near))
            if near:
                if track.fence_start is None:
                    track.fence_start = current
                if not track.fence_fired and timestamp-track.fence_start.time >= c.fence_dwell_seconds:
                    track.fence_fired = True
                    alerts.append(Candidate("person_near_fence",timestamp,track.id,current.box,
                        [(o.time,*o.point) for o in track.history],
                        "Person remains in the fence watch area; no throw has been established.",
                        context={"fence_dwell_seconds":round(timestamp-track.fence_start.time,2)}))
            else:
                track.fence_start = None
                track.fence_fired = False
            if not contains(foot, c.inside_zone) or ignored:
                track.person_start = None
                track.fired = False
                continue
            if track.person_start is None:
                track.person_start = current
            start = track.person_start
            if (not track.fired and timestamp - start.time >= c.person_confirm_seconds and
                    distance(start.point, current.point) >= c.person_movement):
                track.fired = True
                alerts.append(Candidate("person_movement", timestamp, track.id, current.box,
                    [(o.time, *o.point) for o in track.history], "Person moving in the inside zone."))
        return alerts
