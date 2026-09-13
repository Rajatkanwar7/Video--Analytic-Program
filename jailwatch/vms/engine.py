from __future__ import annotations

import copy
import queue
import threading
import time
import uuid

from jailwatch.capture import VideoSource
from jailwatch.detector import YoloDetector
from jailwatch.events import utc_now
from jailwatch.inference import LiveInference
from .recording import Recorder

_torch_lock = threading.Lock()
_torch_configured = False


def vms_detector(config):
    global _torch_configured
    with _torch_lock:
        if not _torch_configured:
            import torch
            torch.set_num_threads(2)
            _torch_configured = True
    return YoloDetector(config)


class CameraEvents:
    def __init__(self, store, camera_id):
        self.store,self.camera_id = store,camera_id

    def add(self, candidate, camera, run_id, image=None, details=None):
        return self.store.add(candidate,camera,run_id,image,{**(details or {}),"camera_id":self.camera_id})

    def prune(self, *args):
        self.store.prune(*args)


class CameraWorker:
    def __init__(self, camera, events, recordings, preferences, notify, factory=YoloDetector):
        self.camera = copy.deepcopy(camera)
        self.events,self.recordings,self.preferences = events,recordings,preferences
        self.notify,self.factory = notify,factory
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.latest = None
        self.last_frame_at = 0
        self.state = {"status":"Starting", "fps":0.0,"dropped":0,"ai":"Loading" if camera.analytics else "Off",
                      "recording":"Recording off","ai_pending":0,"ai_overflows":0,"latency":0.0}
        self.recorder = Recorder(self.camera,recordings,preferences)
        self.thread = threading.Thread(target=self._work,daemon=True,name=f"camera-{camera.id[:8]}")

    def update(self, **values):
        with self.lock:
            self.state.update(values)

    def snapshot(self):
        with self.lock:
            return dict(self.state), self.latest, self.last_frame_at

    def _work(self):
        from jailwatch.pipeline import Pipeline
        reader, ai, pipeline = None,None,None
        config = self.camera.config
        started = time.monotonic()
        started_utc = utc_now()
        run_id = uuid.uuid4().hex
        frames = 0
        first_time = None
        ai_failed = False
        failed = False
        last_display = 0
        try:
            reader = VideoSource(config.resolved_source(),config).open()
            if self.camera.analytics:
                ai = LiveInference(config,self.factory)
            while not self.stop_event.is_set():
                self.recorder.tick()
                self.update(recording=self.recorder.status)
                if ai and ai.ready.is_set() and pipeline is None and not ai_failed:
                    if ai.error:
                        ai_failed = True
                        self.update(ai="FAILED: check model/device")
                        self.notify({"type":"health","camera_id":self.camera.id,"text":f"{self.camera.name}: AI unavailable; live viewing continues."})
                    else:
                        pipeline = Pipeline(config,None,CameraEvents(self.events,self.camera.id),live_ai=ai)
                        run_id = pipeline.run_id
                packet = reader.read()
                if packet is None:
                    self.update(status=reader.status)
                    if reader.ended:
                        break
                    continue
                if first_time is None:
                    first_time = packet.time
                packet.time -= first_time
                if not reader.live:
                    wait = packet.time-(time.monotonic()-started)
                    if wait > 0 and self.stop_event.wait(wait):
                        break
                frames += 1
                image = packet.image
                if pipeline and not ai_failed:
                    try:
                        image, alerts = pipeline.process(packet)
                        for alert in alerts:
                            self.notify({"type":"event","camera_id":self.camera.id,**alert})
                        self.update(ai=pipeline.status,ai_pending=ai.pending,ai_overflows=ai.dropped_candidates)
                    except Exception:
                        ai_failed = True
                        self.update(ai="FAILED: analytics stopped")
                        self.notify({"type":"health","camera_id":self.camera.id,"text":f"{self.camera.name}: analytics stopped; check zones, model and evidence storage."})
                        ai.close()
                now = time.monotonic()
                if now-last_display >= .10:
                    import cv2
                    h,w = image.shape[:2]
                    if w > 1280:
                        image = cv2.resize(image,(1280,round(h*1280/w)))
                    with self.lock:
                        self.latest = image.copy()
                        self.last_frame_at = now
                    self.update(status=reader.status,fps=frames/max(.01,now-started),dropped=reader.dropped,
                                latency=max(0,now-packet.received))
                    last_display = now
        except Exception:
            failed = True
            self.update(status="Connection failed; check source, codec and storage")
            self.notify({"type":"health","camera_id":self.camera.id,"text":f"{self.camera.name}: camera worker stopped. Check connection and storage."})
        finally:
            try:
                self.recorder.stop()
            except Exception:
                self.notify({"type":"health","camera_id":self.camera.id,"text":f"{self.camera.name}: recording could not close cleanly."})
            if reader:
                reader.close()
            if ai:
                ai.close()
            try:
                self.events.save_run({"run_id":run_id,"camera_id":self.camera.id,"camera_name":self.camera.name,
                    "started_utc":started_utc,"finished_utc":utc_now(),"processed_frames":frames,
                    "dropped_frames":reader.dropped if reader else 0,"test_mode":config.test_mode,
                    "ai_requested":self.camera.analytics,"ai_failed":ai_failed,
                    "event_counts":dict(pipeline.event_counts) if pipeline else {},
                    "ai_overflows":ai.dropped_candidates if ai else 0,
                    "elapsed_seconds":round(time.monotonic()-started,3)})
            except Exception:
                self.notify({"type":"health","camera_id":self.camera.id,"text":f"{self.camera.name}: session report could not be saved."})
            self.update(status="FAILED: check connection/storage" if failed else "Stopped",recording=self.recorder.status,
                        ai="Stopped" if self.camera.analytics else "Off")


class MonitorManager:
    def __init__(self, events, recordings, preferences, factory=vms_detector):
        self.events,self.recordings,self.preferences = events,recordings,preferences
        self.factory = factory
        self.workers = {}
        self.messages = queue.Queue(maxsize=256)
        self.dropped_messages = 0
        self.maintenance_stop = threading.Event()
        self.maintenance = threading.Thread(target=self._maintain,daemon=True,name="recording-retention")
        self.maintenance.start()

    def notify(self, message):
        try:
            self.messages.put_nowait(message)
        except queue.Full:
            self.dropped_messages += 1

    def _maintain(self):
        while not self.maintenance_stop.wait(15):
            try:
                self.recordings.prune(self.preferences.retention_days,self.preferences.quota_gb*1024**3)
            except Exception:
                self.notify({"type":"health","text":"Recording retention failed. Check the storage folder."})

    def running(self, camera_id):
        return camera_id in self.workers and self.workers[camera_id].thread.is_alive()

    def start(self, camera):
        camera.validate()
        if self.running(camera.id):
            return
        active = [w for w in self.workers.values() if w.thread.is_alive()]
        if len(active) >= self.preferences.max_live:
            raise ValueError(f"The live-camera limit is {self.preferences.max_live}. Stop another camera first.")
        if camera.analytics and sum(w.camera.analytics for w in active) >= self.preferences.max_analytics:
            raise ValueError(f"The AI-camera limit is {self.preferences.max_analytics}. Change Settings only after checking server capacity.")
        worker = CameraWorker(camera,self.events,self.recordings,self.preferences,self.notify,self.factory)
        self.workers[camera.id] = worker
        worker.thread.start()

    def stop(self, camera_id):
        if camera_id in self.workers:
            self.workers[camera_id].stop_event.set()
            self.workers[camera_id].update(status="Stopping")

    def stop_all(self):
        for key in self.workers:
            self.stop(key)

    def set_recording(self, camera_id, enabled):
        if not self.running(camera_id):
            raise ValueError("Start this camera before recording.")
        self.workers[camera_id].recorder.desired = bool(enabled)

    def close(self):
        self.stop_all()
        self.maintenance_stop.set()
        deadline = time.monotonic()+25
        for worker in self.workers.values():
            worker.thread.join(timeout=max(0,deadline-time.monotonic()))
        self.maintenance.join(timeout=1)
