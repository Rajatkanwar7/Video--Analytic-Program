from __future__ import annotations

import math
import os
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Frame:
    image: object
    time: float
    index: int
    epoch: int
    received: float


class VideoSource:
    """File replay keeps every frame. RTSP uses a bounded latest-frame queue."""
    def __init__(self, source, config):
        self.source = source
        self.config = config
        self.live = not Path(source).is_file()
        self.frames = queue.Queue(maxsize=2)
        self.stop_event = threading.Event()
        self.thread = None
        self.cap = None
        self.status = "Opening video"
        self.dropped = 0
        self.fps = 25.0
        self.index = 0
        self.epoch = 0
        self.ended = False
        self.first_pts = None
        self.last_pts = -1.0

    def _open(self):
        os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "-8")
        import cv2
        # FFmpeg's log can include RTSP credentials. Keep low-level source errors private.
        if hasattr(cv2, "setLogLevel"):
            cv2.setLogLevel(0)
        if self.live:
            cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG, [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.config.open_timeout_ms,
                cv2.CAP_PROP_READ_TIMEOUT_MSEC, self.config.read_timeout_ms])
        else:
            cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            cap.release()
            raise OSError("Video could not be opened. Check source, camera login, network and codec.")
        fps = cap.get(cv2.CAP_PROP_FPS)
        self.fps = fps if math.isfinite(fps) and 1 <= fps <= 240 else 25.0
        return cap

    def open(self):
        if self.live:
            self.thread = threading.Thread(target=self._receive, daemon=True, name="rtsp-capture")
            self.thread.start()
        else:
            self.cap = self._open()
            self.status = "Replaying file"
        return self

    def _receive(self):
        while not self.stop_event.is_set():
            cap = None
            try:
                self.status = "Connecting to camera"
                cap = self._open()
                self.epoch += 1
                while not self.frames.empty():
                    try:
                        self.frames.get_nowait()
                    except queue.Empty:
                        break
                self.status = "Connected"
                while not self.stop_event.is_set():
                    ok, image = cap.read()
                    if not ok:
                        break
                    self.index += 1
                    now = time.monotonic()
                    packet = Frame(image, now, self.index, self.epoch, now)
                    if self.frames.full():
                        try:
                            self.frames.get_nowait()
                            self.dropped += 1
                        except queue.Empty:
                            pass
                    self.frames.put_nowait(packet)
            except (OSError, RuntimeError):
                pass
            except Exception:
                self.status = "Capture error; reconnecting"
            finally:
                if cap is not None:
                    cap.release()
            if not self.stop_event.is_set():
                self.status = "Camera disconnected; retrying"
                self.stop_event.wait(self.config.reconnect_seconds)
        self.status = "Stopped"
        self.ended = True

    def read(self):
        if self.live:
            try:
                return self.frames.get(timeout=0.25)
            except queue.Empty:
                return None
        import cv2
        ok, image = self.cap.read()
        if not ok:
            self.ended = True
            self.status = "End of video (or decoder stopped)"
            return None
        pts = self.cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        if self.first_pts is None:
            self.first_pts = pts if math.isfinite(pts) else 0.0
        pts -= self.first_pts
        if not math.isfinite(pts) or pts <= self.last_pts:
            pts = max(self.index / self.fps, self.last_pts + 1 / self.fps)
        self.last_pts = pts
        self.index += 1
        return Frame(image, pts, self.index, 0, time.monotonic())

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=(self.config.read_timeout_ms + self.config.open_timeout_ms) / 1000 + 1)
        elif self.cap is not None:
            self.cap.release()
        self.ended = True


def first_frame(source, config):
    reader = VideoSource(source, config).open()
    try:
        deadline = time.monotonic() + config.open_timeout_ms / 1000 + config.read_timeout_ms / 1000 + 2
        while time.monotonic() < deadline:
            frame = reader.read()
            if frame is not None:
                return frame.image
            if reader.ended:
                break
        raise OSError("No video frame received. Check the camera source and network.")
    finally:
        reader.close()
