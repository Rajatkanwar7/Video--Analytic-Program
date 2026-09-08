from __future__ import annotations

import time
import uuid
from collections import Counter, deque

import cv2
import numpy as np

from .capture import VideoSource
from .detector import YoloDetector, verify_track
from .geometry import contains
from .rules import RuleEngine
from .trajectory import draw_trail, trajectory_stats, visible_trails
from .events import utc_now


class MotionExtractor:
    def __init__(self, config):
        self.config = config
        self.reset()

    def reset(self):
        self.background = cv2.createBackgroundSubtractorMOG2(
            history=350, varThreshold=self.config.background_threshold, detectShadows=True)

    def extract(self, image):
        mask = self.background.apply(image)
        mask = (mask == 255).astype(np.uint8) * 255
        # No erosion: a thrown package can be only a few pixels wide.
        ratio = float(np.count_nonzero(mask)) / mask.size
        if ratio > self.config.max_foreground_ratio:
            return [], ratio
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        h, w = image.shape[:2]
        boxes = []
        for contour in contours:
            x, y, bw, bh = cv2.boundingRect(contour)
            area = cv2.contourArea(contour) / (w * h)
            if self.config.min_blob_area_ratio <= area <= self.config.max_blob_area_ratio:
                if max(bw / max(bh, 1), bh / max(bw, 1)) <= 10:
                    box = (x / w, y / h, (x + bw) / w, (y + bh) / h)
                    p = ((x + bw / 2) / w, (y + bh / 2) / h)
                    if not any(contains(p, z) for z in self.config.ignore_zones):
                        boxes.append(box)
        # Storms/leaves should not create unbounded association work.
        return boxes[:200], ratio


class Pipeline:
    def __init__(self, config, detector, store, live_ai=None):
        self.config, self.detector, self.store = config, detector, store
        self.live_ai = live_ai
        self.generation = 0
        self.rules = RuleEngine(config)
        self.motion = MotionExtractor(config)
        self.run_id = uuid.uuid4().hex
        self.first_time = None
        self.last_time = None
        self.last_semantic = -1e20
        self.last_submit = -1e20
        self.detections = []
        self.last_epoch = None
        self.status = "Warming up"
        self.suppressed_birds = 0
        self.suppressed_people = 0
        self.suppressed_unknown = 0
        self.track_labels = {}
        self.event_counts = Counter()
        self.observed_seconds = 0.0
        self.frame_gaps = 0
        # Keep contextual crops, not full-resolution video, for exact-time verification.
        self.samples = {}
        self.processed = 0
        self.started = time.monotonic()
        self.last_prune = 0.0

    def reset(self, timestamp):
        self.generation += 1
        if self.live_ai:
            self.live_ai.reset_pending()
        self.rules.reset()
        self.motion.reset()
        self.first_time = timestamp
        self.samples.clear()
        self.last_semantic = -1e20
        self.last_submit = -1e20
        self.detections = []
        self.track_labels.clear()

    def process(self, packet):
        c = self.config
        raw = packet.image
        rh, rw = raw.shape[:2]
        if c.calibration_size:
            cw, ch = c.calibration_size
            if abs((rw / rh) / (cw / ch) - 1) > 0.03:
                raise ValueError("Camera aspect ratio changed. Redraw zones on the new view.")
        scale = min(1, c.processing_width / rw)
        image = cv2.resize(raw, (round(rw * scale), round(rh * scale))) if scale < 1 else raw
        t = packet.time
        if (self.last_time is not None and packet.epoch == self.last_epoch and
                0 < t-self.last_time <= c.reset_gap_seconds):
            self.observed_seconds += t-self.last_time
        if (self.first_time is None or packet.epoch != self.last_epoch or self.last_time is None or
                t <= self.last_time or t - self.last_time > c.reset_gap_seconds):
            if self.first_time is not None:
                self.frame_gaps += 1
            self.reset(t)
        self.last_time, self.last_epoch = t, packet.epoch
        self.processed += 1
        self.status = "Monitoring"
        events = self._drain_ai()
        boxes, ratio = self.motion.extract(image)
        candidates = []
        warm = t - self.first_time < c.warmup_seconds
        if warm:
            self.status = "Warming up background"
        elif ratio > c.max_foreground_ratio:
            self.status = "Large scene change: crossing detection paused"
            self.reset(t)
        else:
            candidates = self.rules.crossing(boxes, t)
            self._sample_tracks(image, t)
        if t - self.last_submit >= c.semantic_interval_seconds:
            # Inference and rules share the frame's source timestamp, including slow replay.
            self.last_submit = t
            if self.live_ai:
                self.live_ai.submit_semantic(self.generation, t, image)
            else:
                events += self._semantic_result(self.detector.predict(image), t, image)
        for candidate in candidates:
            if not self.rules.permitted(candidate.kind, t):
                continue
            samples = list(self.samples.get(candidate.track_id, []))
            samples = samples[::max(1, len(samples) // 3)][:3]
            if self.live_ai:
                self.live_ai.submit_candidate(self.generation, candidate, image, samples)
                continue
            label = verify_track(self.detector, image, candidate.box, samples)
            event = self._candidate_result(candidate, image, label)
            if event:
                events.append(event)
        if self.live_ai:
            if self.live_ai.dropped_candidates:
                self.status += " | AI queue overflow: crossings may be missed"
            if t - self.last_semantic > max(2, c.semantic_interval_seconds * 3):
                self.status += " | AI person checks delayed"
        self._prune(t)
        return self.annotate(image.copy(), t, events), events

    def _semantic_result(self, detections, timestamp, image):
        self.detections, self.last_semantic = detections, timestamp
        events = []
        if timestamp - self.first_time >= self.config.warmup_seconds:
            people = [d.box for d in detections if d.label == "person"]
            for candidate in self.rules.person_movement(people, timestamp):
                event = self._emit(candidate, image, {"classification": "person"})
                if event:
                    events.append(event)
        return events

    def _candidate_result(self, candidate, image, label):
        self.track_labels[candidate.track_id] = label or "motion"
        if label == "bird":
            self.suppressed_birds += 1
        elif label == "person":
            self.suppressed_people += 1
        elif self.config.require_object_class and label != "thrown_object":
            self.suppressed_unknown += 1
        else:
            return self._emit(candidate, image, {
                "classification": "thrown_object" if label == "thrown_object" else "unknown moving object",
                "custom_object_match": label == "thrown_object", "bird_filter": "no bird recognized",
                "review_required": True})
        return None

    def _drain_ai(self):
        events = []
        if self.live_ai:
            for result in self.live_ai.poll():
                if result["generation"] != self.generation:
                    continue
                if result["type"] == "semantic":
                    events += self._semantic_result(result["detections"], result["time"], result["image"])
                else:
                    event = self._candidate_result(result["candidate"], result["image"], result["label"])
                    if event:
                        events.append(event)
        return events

    def _sample_tracks(self, image, timestamp):
        h, w = image.shape[:2]
        active = self.rules.motion.tracks
        self.track_labels = {key: value for key,value in self.track_labels.items() if key in active}
        self.samples = {key: value for key, value in self.samples.items() if key in active}
        for key, track in active.items():
            if track.history[-1].time != timestamp or track.outside_start is None:
                continue
            last = track.history[-1]
            trail = self.samples.setdefault(key, deque(maxlen=6))
            if trail and timestamp - trail[-1][0] < 0.1:
                continue
            cx, cy = last.point
            # Bounded at 128 tracks x 6 crops x 256x256x3 bytes; typically much smaller.
            x1, y1 = max(0, int(cx * w) - 128), max(0, int(cy * h) - 128)
            x2, y2 = min(w, x1 + 256), min(h, y1 + 256)
            box = tuple((v * (w if i % 2 == 0 else h) - (x1 if i % 2 == 0 else y1)) /
                        ((x2 - x1) if i % 2 == 0 else (y2 - y1)) for i, v in enumerate(last.box))
            trail.append((timestamp, image[y1:y2, x1:x2].copy(), box))

    def _emit(self, candidate, image, details):
        if not self.rules.permitted(candidate.kind, candidate.source_time):
            return None
        evidence = image.copy()
        self._draw_candidate(evidence, candidate)
        details = {**details, "test_mode": self.config.test_mode,
                   "image_size": [image.shape[1],image.shape[0]],
                   "trajectory_statistics": trajectory_stats(candidate.trajectory,[image.shape[1],image.shape[0]])}
        if self.config.test_mode:
            cv2.putText(evidence,"LIVE TEST",(12,58),cv2.FONT_HERSHEY_SIMPLEX,.65,(255,180,80),2)
        event_id = self.store.add(candidate, self.config.camera_name, self.run_id, evidence, details)
        self.rules.emitted(candidate.kind, candidate.source_time)
        self.event_counts[candidate.kind] += 1
        return {"id": event_id, "kind": candidate.kind, "source_time": candidate.source_time,
                "message": candidate.message, "run_id": self.run_id, "test_mode": self.config.test_mode}

    def _prune(self, t):
        now = time.monotonic()
        if now - self.last_prune > 60:
            self.store.prune(self.config.retention_days, self.config.max_events)
            self.last_prune = now

    @staticmethod
    def _draw_candidate(image, candidate):
        h, w = image.shape[:2]
        x1, y1, x2, y2 = candidate.box
        cv2.rectangle(image, (int(x1*w), int(y1*h)), (int(x2*w), int(y2*h)), (20, 40, 255), 2)
        points = np.array([(int(x*w), int(y*h)) for _, x, y in candidate.trajectory], np.int32)
        if len(points) >= 2:
            draw_trail(image,candidate.trajectory,(20,190,255),f"Track #{candidate.track_id}",candidate.box)
        cv2.putText(image, candidate.kind.upper(), (12, 30), cv2.FONT_HERSHEY_SIMPLEX, .7, (20, 40, 255), 2)

    def annotate(self, image, timestamp, events):
        h, w = image.shape[:2]
        for name, zone, color in (("OUTSIDE", self.config.outside_zone, (0, 190, 255)),
                                  ("INSIDE", self.config.inside_zone, (90, 220, 80))):
            points = np.array([(int(x*w), int(y*h)) for x, y in zone], np.int32)
            cv2.polylines(image, [points], True, color, 2)
            cv2.putText(image, name, tuple(points[0]), cv2.FONT_HERSHEY_SIMPLEX, .6, color, 2)
        if self.config.show_trajectories:
            for tid,points,box in visible_trails(self.rules.motion.tracks,timestamp,
                    self.config.trajectory_seconds,self.config.max_track_gap_seconds,corridor_only=True):
                label = self.track_labels.get(tid,"motion")
                color = (220,180,60) if label == "bird" else (30,180,255)
                draw_trail(image,points,color,f"{label.replace('_',' ')} #{tid}",box)
            for tid,points,box in visible_trails(self.rules.people.tracks,timestamp,
                    self.config.trajectory_seconds,max(1.5,3*self.config.semantic_interval_seconds)):
                draw_trail(image,points,(80,220,80),f"person #{tid}",box)
        if self.config.test_mode:
            cv2.putText(image,"LIVE TEST MODE",(12,25),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,180,80),2)
        if timestamp - self.last_semantic < 0.15:
            for d in self.detections:
                x1, y1, x2, y2 = d.box
                color = (200, 190, 40) if d.label == "bird" else (80, 220, 80)
                cv2.rectangle(image, (int(x1*w), int(y1*h)), (int(x2*w), int(y2*h)), color, 2)
                cv2.putText(image, f"{d.label} {d.confidence:.2f}", (int(x1*w), max(15, int(y1*h)-5)),
                            cv2.FONT_HERSHEY_SIMPLEX, .5, color, 1)
        if events:
            cv2.rectangle(image, (0, h-45), (w, h), (25, 35, 200), -1)
            cv2.putText(image, events[-1]["kind"].upper(), (12, h-15),
                        cv2.FONT_HERSHEY_SIMPLEX, .7, (255, 255, 255), 2)
        return image


def run_monitor(config, store, stop_event, callback, max_frames=0, realtime=False, detector_factory=YoloDetector,
                max_seconds=0):
    """Shared desktop/headless runner. callback runs on processing thread; UI must queue it."""
    config.validate()
    source = config.resolved_source()
    callback({"type": "status", "text": "Loading AI model"})
    reader = VideoSource(source, config)
    live_ai = None
    if reader.live:
        from .inference import LiveInference
        live_ai = LiveInference(config, detector_factory)
        while not live_ai.ready.wait(.2):
            if stop_event.is_set():
                live_ai.close()
                return {"processed_frames": 0, "dropped_frames": 0, "status": "Stopped during model loading"}
        if live_ai.error:
            live_ai.close()
            raise ValueError(live_ai.error)
        detector = None
    else:
        detector = detector_factory(config)
    pipeline = Pipeline(config, detector, store, live_ai=live_ai)
    started = time.monotonic()
    started_utc = utc_now()
    run_status = "stopped"
    max_latency = 0.0
    last_report = 0.0
    first_source_time = None
    try:
        reader.open()
        callback({"type": "session", "run_id": pipeline.run_id, "live": reader.live,
                  "test_mode": config.test_mode})
        while not stop_event.is_set():
            if max_seconds and time.monotonic()-started >= max_seconds:
                run_status = "duration_limit"
                break
            packet = reader.read()
            if packet is None:
                for event in pipeline._drain_ai():
                    callback({"type": "event", **event})
                callback({"type": "status", "text": reader.status})
                if reader.ended:
                    run_status = "source_ended"
                    break
                continue
            if first_source_time is None:
                first_source_time = packet.time
            if not reader.live and realtime:
                wait = packet.time - first_source_time - (time.monotonic() - started)
                if max_seconds:
                    wait = min(wait,max(0,max_seconds-(time.monotonic()-started)))
                if wait > 0 and stop_event.wait(wait):
                    break
                if max_seconds and time.monotonic()-started >= max_seconds:
                    run_status = "duration_limit"
                    break
            packet.time -= first_source_time
            annotated, events = pipeline.process(packet)
            for event in events:
                callback({"type": "event", **event})
            now = time.monotonic()
            latency = now - packet.received
            max_latency = max(max_latency,latency)
            if now - last_report >= .08 or events:
                status = pipeline.status
                if reader.live and (latency > .5 or reader.dropped):
                    status += " | Frame loss/latency: small objects may be missed"
                callback({"type": "frame", "image": annotated, "text": status,
                    "source_time": packet.time,
                    "fps": pipeline.processed / max(now - started, .01), "dropped": reader.dropped,
                    "latency": latency, "suppressed_birds": pipeline.suppressed_birds,
                    "ai_pending": live_ai.pending if live_ai else 0,
                    "ai_overflows": live_ai.dropped_candidates if live_ai else 0,
                    "frame_gaps": pipeline.frame_gaps,
                    "run_id": pipeline.run_id, "source_fps": reader.fps,
                    "test_mode": config.test_mode, "event_counts": dict(pipeline.event_counts),
                    "suppressed_unknown": pipeline.suppressed_unknown})
                last_report = now
            if max_frames and pipeline.processed >= max_frames:
                run_status = "frame_limit"
                break
    except Exception:
        run_status = "failed"
        raise
    finally:
        pending = live_ai.pending if live_ai else 0
        reader.close()
        if live_ai:
            live_ai.close()
        summary = {"processed_frames": pipeline.processed, "dropped_frames": reader.dropped,
                   "suppressed_birds": pipeline.suppressed_birds,"suppressed_people": pipeline.suppressed_people,
                   "suppressed_unknown": pipeline.suppressed_unknown, "event_counts": dict(pipeline.event_counts),
                   "frame_gaps": pipeline.frame_gaps,"run_id": pipeline.run_id,"status": run_status,
                   "test_mode": config.test_mode,"source_type": "rtsp" if reader.live else "file",
                   "camera_name": config.camera_name, "started_utc": started_utc,"finished_utc": utc_now(),
                   "source_fps": reader.fps,"source_seconds": pipeline.last_time or 0.0,
                   "observed_seconds": round(pipeline.observed_seconds,3),
                   "max_processing_delay_seconds": round(max_latency,3),"pending_ai_at_stop": pending,
                   "ai_overflows": live_ai.dropped_candidates if live_ai else 0,
                   "elapsed_seconds": round(time.monotonic()-started,3)}
        summary["report_path"] = store.save_run(summary)
    return summary
