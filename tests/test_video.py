"""Actual OpenCV synthetic-video integration; test detector is not an AI accuracy test."""
import importlib.util
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from test_core import config

HAS_CV = importlib.util.find_spec("cv2") is not None


@unittest.skipUnless(HAS_CV, "Install requirements-base.txt to run video tests")
class VideoTests(unittest.TestCase):
    def setUp(self):
        import cv2
        import numpy as np
        self.cv2, self.np = cv2, np
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def detector(self, label=None):
        from jailwatch.detector import Detection
        np = self.np
        class TestDetector:
            def predict(self, image):
                if label is None:
                    return []
                mask = image[:, :, 1] > 180
                ys, xs = np.where(mask)
                if len(xs) == 0:
                    return []
                h, w = image.shape[:2]
                return [Detection(label, .95, (min(xs)/w, min(ys)/h, (max(xs)+1)/w, (max(ys)+1)/h))]
        return TestDetector()

    def generate(self, reverse=False, color=(255, 255, 255)):
        for i in range(80):
            image = self.np.zeros((360, 640, 3), self.np.uint8)
            if 20 <= i <= 60:
                x = 100 + (i-20)*9
                if reverse:
                    x = 640-x
                self.cv2.rectangle(image, (x, 170), (x+9, 179), color, -1)
            yield image

    def pipeline(self, reverse=False, label=None, require_class=False):
        from jailwatch.capture import Frame
        from jailwatch.events import EventStore
        from jailwatch.pipeline import Pipeline
        c = config(); c.data_dir = self.tmp.name
        c.require_object_class = require_class
        p = Pipeline(c, self.detector(label), EventStore(c.data_dir))
        for i, image in enumerate(self.generate(reverse, (0, 255, 0) if label else (255, 255, 255))):
            p.process(Frame(image, i/25, i, 0, time.monotonic()))
        return p

    def test_unknown_object_crossing_saves_snapshot(self):
        p = self.pipeline()
        rows = p.store.list()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "suspected_throw")
        self.assertTrue(p.store.snapshot_path(rows[0]["snapshot"]).is_file())

    def test_bird_candidate_is_suppressed_on_exact_event_frame(self):
        p = self.pipeline(label="bird")
        self.assertEqual(p.store.list(), [])
        self.assertEqual(p.suppressed_birds, 1)

    def test_person_blob_is_not_a_thrown_object(self):
        p = self.pipeline(label="person")
        self.assertFalse(any(r["kind"] == "suspected_throw" for r in p.store.list()))
        self.assertEqual(p.suppressed_people, 1)

    def test_reverse_motion_does_not_alert(self):
        self.assertEqual(self.pipeline(reverse=True).store.list(), [])

    def test_custom_class_gate_and_saved_classification(self):
        p=self.pipeline(require_class=True)
        self.assertEqual(p.store.list(),[])
        self.assertEqual(p.suppressed_unknown,1)
        p=self.pipeline(label="thrown_object",require_class=True)
        details=json.loads(p.store.list()[0]["details"])
        self.assertTrue(details["custom_object_match"])
        self.assertGreater(details["trajectory_statistics"]["sample_count"],2)

    def test_live_trajectory_draws_observed_path_and_toggle_hides_it(self):
        from jailwatch.capture import Frame
        from jailwatch.events import EventStore
        from jailwatch.pipeline import Pipeline
        p=Pipeline(config(),self.detector(),EventStore(self.tmp.name))
        for i,image in enumerate(self.generate()):
            annotated,_=p.process(Frame(image,i/25,i,0,time.monotonic()))
            if i==39:
                # A historical object location, away from the zone borders and current object.
                self.assertTrue(self.np.any(annotated[173:178,190:200]))
                p.config.show_trajectories=False
                hidden=p.annotate(image.copy(),i/25,[])
                self.assertFalse(self.np.any(hidden[173:178,190:200]))
                break

    def test_scene_change_and_time_gap_reset_tracks(self):
        from jailwatch.capture import Frame
        p = self.pipeline()
        before = len(p.store.list())
        white = self.np.full((360, 640, 3), 255, self.np.uint8)
        p.process(Frame(white, 8.0, 100, 1, time.monotonic()))
        self.assertEqual(len(p.store.list()), before)
        self.assertEqual(p.frame_gaps, 1)
        self.assertEqual(p.status, "Warming up background")

    def test_recorded_video_runner_reads_every_frame_and_closes(self):
        from jailwatch.events import EventStore
        from jailwatch.pipeline import run_monitor
        path = Path(self.tmp.name) / "synthetic.avi"
        writer = self.cv2.VideoWriter(str(path), self.cv2.VideoWriter_fourcc(*"MJPG"), 25, (640, 360))
        self.assertTrue(writer.isOpened())
        for image in self.generate():
            writer.write(image)
        writer.release()
        c = config(); c.source = str(path); c.data_dir = str(Path(self.tmp.name)/"events")
        c.test_mode = True
        events = []
        summary = run_monitor(c, EventStore(c.data_dir), threading.Event(), events.append,
                              detector_factory=lambda _: self.detector())
        self.assertEqual(summary["processed_frames"], 80)
        self.assertEqual(summary["dropped_frames"], 0)
        self.assertTrue(any(m["type"] == "event" for m in events))
        self.assertEqual(len(EventStore(c.data_dir).list()), 1)
        self.assertEqual(summary["event_counts"]["suspected_throw"],1)
        report=json.loads(Path(summary["report_path"]).read_text())
        self.assertEqual(report["run_id"],summary["run_id"])
        self.assertEqual(report["source_type"],"file")
        self.assertTrue(report["test_mode"])
        self.assertTrue(json.loads(EventStore(c.data_dir).list()[0]["details"])["test_mode"])

    def test_changed_camera_aspect_ratio_stops_monitoring(self):
        from jailwatch.capture import Frame
        p = self.pipeline(); p.config.calibration_size = [640, 480]
        with self.assertRaisesRegex(ValueError, "aspect ratio"):
            p.process(Frame(self.np.zeros((360, 640, 3), self.np.uint8), 4, 100, 0, time.monotonic()))

    def test_frame_extraction_preserves_timing_and_leaves_images_unlabelled(self):
        from scripts.extract_frames import extract
        source=Path(self.tmp.name)/"sample.avi"
        writer=self.cv2.VideoWriter(str(source),self.cv2.VideoWriter_fourcc(*"MJPG"),25,(640,360))
        self.assertTrue(writer.isOpened())
        for image in self.generate(): writer.write(image)
        writer.release()
        result=extract(source,Path(self.tmp.name)/"annotation","camera_day",fps=15,end=.5)
        self.assertEqual(result["frames"],8)
        self.assertFalse(result["labels_created"])
        self.assertEqual(len(list(Path(result["directory"]).glob("*.txt"))),0)
        with self.assertRaises(FileExistsError):
            extract(source,Path(self.tmp.name)/"annotation","camera_day",fps=15,end=.5)


if __name__ == "__main__":
    unittest.main()
