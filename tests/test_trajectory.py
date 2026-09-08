import csv
import json
import tempfile
import unittest
from pathlib import Path

from jailwatch.events import EventStore
from jailwatch.rules import Candidate
from jailwatch.tracking import Observation, Track
from jailwatch.trajectory import trajectory_stats,visible_trails


class TrajectoryTests(unittest.TestCase):
    def test_stats_use_measured_coordinates_and_pixel_scale(self):
        result = trajectory_stats([(0,.1,.2),(1,.4,.6)],[1000,500])
        self.assertAlmostEqual(result["path_length_image_fraction"],.5)
        self.assertAlmostEqual(result["mean_speed_pixels_per_second"],(300**2+200**2)**.5)
        self.assertEqual(result["horizontal_direction"],"right")
        self.assertEqual(result["vertical_direction"],"down")

    def test_missing_tracks_expire_without_an_invented_path(self):
        track = Track(3)
        track.history.extend([Observation(0,(.1,.1,.2,.2)),Observation(.1,(.2,.1,.3,.2))])
        self.assertEqual(len(visible_trails({3:track},.2,2,.3)),1)
        self.assertEqual(visible_trails({3:track},1,2,.3),[])
        self.assertEqual(visible_trails({3:track},.2,.05,.3),[])

    def test_invalid_or_reversed_time_is_rejected(self):
        for points in [[(1,.1,.2),(1,.2,.3)],[(0,-1,.2)],[(0,float('nan'),.2)]]:
            with self.assertRaises(ValueError): trajectory_stats(points)

    def test_path_export_matches_saved_event_and_test_alarm_has_no_path(self):
        with tempfile.TemporaryDirectory() as d:
            store = EventStore(d)
            event = Candidate("suspected_throw",1,42,(.5,.4,.6,.5),[(0,.2,.4),(1,.55,.45)],"review")
            event_id = store.add(event,"cam","run",details={"image_size":[640,360]})
            target = Path(d)/"path.csv"
            self.assertEqual(store.export_trajectories(target,[event_id]),2)
            with target.open(encoding="utf-8-sig",newline="") as f: rows=list(csv.DictReader(f))
            self.assertEqual(rows[0]["track_id"],"42")
            self.assertEqual(float(rows[0]["x_pixels"]),128)
            test_id=store.add(Candidate("system_test",0,0,(0,0,0,0),[],"test"),"cam","test")
            with self.assertRaisesRegex(ValueError,"no measured trajectory"):
                store.export_trajectories(Path(d)/"test.csv",[test_id])

    def test_session_reports_are_persisted_and_cannot_escape_folder(self):
        with tempfile.TemporaryDirectory() as d:
            store = EventStore(d)
            path=store.save_run({"run_id":"a"*32,"event_counts":{"suspected_throw":2}})
            self.assertEqual(json.loads(Path(path).read_text())["event_counts"]["suspected_throw"],2)
            with self.assertRaises(ValueError): store.save_run({"run_id":"../escape"})
