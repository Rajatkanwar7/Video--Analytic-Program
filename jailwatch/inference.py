"""Bounded AI service for live streams; every result retains its original image/time."""
from __future__ import annotations

import queue
import threading
from collections import deque

from .detector import verify_candidate


class LiveInference:
    def __init__(self, config, factory, max_candidates=4):
        self.config, self.factory = config, factory
        self.max_candidates = max_candidates
        self.condition = threading.Condition()
        self.candidates = deque()
        self.semantic = None
        self.results = queue.Queue(maxsize=16)
        self.ready = threading.Event()
        self.stopping = False
        self.active = False
        self.error = None
        self.dropped_candidates = 0
        self.dropped_semantics = 0
        self.thread = threading.Thread(target=self._work, daemon=True, name="live-ai")
        self.thread.start()

    @property
    def pending(self):
        with self.condition:
            return len(self.candidates) + int(self.semantic is not None) + int(self.active) + self.results.qsize()

    def submit_semantic(self, generation, timestamp, image):
        with self.condition:
            if self.stopping:
                return
            if self.semantic is not None:
                self.dropped_semantics += 1
            self.semantic = {"type": "semantic", "generation": generation, "time": timestamp, "image": image.copy()}
            self.condition.notify()

    def submit_candidate(self, generation, candidate, image, samples):
        with self.condition:
            if self.stopping or len(self.candidates) >= self.max_candidates:
                self.dropped_candidates += 1
                return False
            self.candidates.append({"type": "candidate", "generation": generation,
                "candidate": candidate, "image": image.copy(), "samples": samples})
            self.condition.notify()
            return True

    def reset_pending(self):
        # An in-flight result can still arrive; generation checking discards it.
        with self.condition:
            self.candidates.clear()
            self.semantic = None

    def poll(self):
        if self.error is not None:
            raise ValueError(self.error)
        messages = []
        while True:
            try:
                messages.append(self.results.get_nowait())
            except queue.Empty:
                return messages

    def _work(self):
        try:
            detector = self.factory(self.config)
            self.ready.set()
            while True:
                with self.condition:
                    self.condition.wait_for(lambda: self.stopping or self.candidates or self.semantic is not None)
                    if self.stopping:
                        return
                    if self.candidates:
                        job = self.candidates.popleft()
                    else:
                        job, self.semantic = self.semantic, None
                    self.active = True
                if job["type"] == "semantic":
                    job["detections"] = detector.predict(job["image"])
                else:
                    label = verify_candidate(detector, job["image"], job["candidate"].box)
                    if label is None:
                        for _, crop, box in job["samples"]:
                            label = verify_candidate(detector, crop, box)
                            if label:
                                break
                    job["label"] = label
                    job.pop("samples")
                if not self.stopping:
                    try:
                        self.results.put_nowait(job)
                    except queue.Full:
                        raise RuntimeError("AI results are not being consumed") from None
                with self.condition:
                    self.active = False
        except Exception as exc:
            self.error = (str(exc) if isinstance(exc, ValueError) else
                          "Live AI failed. Monitoring stopped; check model, device and dependencies.")
        finally:
            self.ready.set()
            with self.condition:
                self.active = False

    def close(self):
        with self.condition:
            self.stopping = True
            self.candidates.clear()
            self.semantic = None
            self.condition.notify_all()
        self.thread.join(timeout=2)
