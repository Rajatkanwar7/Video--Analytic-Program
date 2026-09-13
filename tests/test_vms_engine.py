import tempfile
import time
import unittest
from pathlib import Path

from jailwatch.events import EventStore
from jailwatch.vms.devices import Camera,Preferences
from jailwatch.vms.engine import MonitorManager
from jailwatch.vms.recording import RecordingStore
from test_core import config
from test_vms_recording import make_video


class ManagerTests(unittest.TestCase):
    def test_multiple_sources_run_and_shutdown_without_shared_frame_state(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root,"source.avi"); make_video(path)
            manager=MonitorManager(EventStore(Path(root,"events")),RecordingStore(root),Preferences(max_live=2))
            first,second=Camera(name="First"),Camera(name="Second")
            first.config.source=second.config.source=str(path)
            try:
                manager.start(first); manager.start(second)
                deadline=time.monotonic()+3
                while time.monotonic()<deadline and any(w.snapshot()[1] is None for w in manager.workers.values()):
                    time.sleep(.05)
                self.assertIsNotNone(manager.workers[first.id].snapshot()[1])
                self.assertIsNotNone(manager.workers[second.id].snapshot()[1])
                self.assertIsNot(manager.workers[first.id].snapshot()[1],manager.workers[second.id].snapshot()[1])
                third=Camera(name="Third"); third.config.source=str(path)
                with self.assertRaisesRegex(ValueError,"live-camera limit"):
                    manager.start(third)
            finally:
                manager.close()
            self.assertTrue(all(not w.thread.is_alive() for w in manager.workers.values()))

    def test_failed_ai_keeps_video_available_with_visible_failure(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root,"source.avi"); make_video(path)
            def unavailable(_):
                raise ValueError("Test model unavailable")
            manager=MonitorManager(EventStore(Path(root,"events")),RecordingStore(root),Preferences(),factory=unavailable)
            camera=Camera(name="Gate",config=config(),analytics=True); camera.config.source=str(path)
            try:
                manager.start(camera)
                worker=manager.workers[camera.id]
                deadline=time.monotonic()+3
                while time.monotonic()<deadline:
                    state,image,_=worker.snapshot()
                    if image is not None and "FAILED" in state["ai"]:
                        break
                    time.sleep(.05)
                self.assertIsNotNone(image)
                self.assertIn("FAILED",state["ai"])
            finally:
                manager.close()
