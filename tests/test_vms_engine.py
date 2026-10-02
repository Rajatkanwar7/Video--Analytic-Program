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

    def test_two_ai_cameras_produce_separate_inward_and_outward_events(self):
        import cv2,numpy as np,json
        class Detector:
            def __init__(self,_): pass
            def predict(self,image): return []
        with tempfile.TemporaryDirectory() as root:
            events=EventStore(Path(root,"events"))
            manager=MonitorManager(events,RecordingStore(root),Preferences(max_live=2,max_analytics=2),factory=Detector)
            cameras=[]
            for reverse in (False,True):
                path=Path(root,f"direction-{reverse}.avi")
                writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*"MJPG"),25,(640,360))
                self.assertTrue(writer.isOpened())
                for i in range(80):
                    image=np.zeros((360,640,3),np.uint8)
                    if 20<=i<=60:
                        x=100+(i-20)*9
                        if reverse: x=640-x
                        image[170:180,x:x+10]=255
                    writer.write(image)
                writer.release()
                c=config(); c.source=str(path); c.crossing_direction="both"
                camera=Camera(name="Outward" if reverse else "Inward",config=c,analytics=True)
                cameras.append(camera)
            try:
                for camera in cameras: manager.start(camera)
                deadline=time.monotonic()+7
                while time.monotonic()<deadline and len(events.list())<2:
                    time.sleep(.05)
                rows=events.list()
                self.assertEqual(len(rows),2)
                actual={r["camera"]:json.loads(r["details"]) for r in rows}
                self.assertEqual(actual["Inward"]["direction"],"outside_to_inside")
                self.assertEqual(actual["Outward"]["direction"],"inside_to_outside")
                self.assertEqual({v["camera_id"] for v in actual.values()},{c.id for c in cameras})
                self.assertTrue(all(v["notify"] for v in actual.values()))
            finally:
                manager.close()
