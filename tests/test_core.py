import csv
import tempfile
import unittest
from pathlib import Path

from jailwatch.config import Config, load_config, save_config
from jailwatch.events import EventStore
from jailwatch.geometry import contains, polygons_overlap, validate_polygon
from jailwatch.rules import Candidate, RuleEngine
from jailwatch.tracking import Tracker


def config():
    return Config(outside_zone=[[0, 0], [.48, 0], [.48, 1], [0, 1]],
                  inside_zone=[[.52, 0], [1, 0], [1, 1], [.52, 1]], warmup_seconds=.2,
                  person_confirm_seconds=.4, semantic_interval_seconds=.2, cooldown_seconds=0)


def box(x, y=.5, size=.01):
    return (x-size, y-size, x+size, y+size)


class GeometryTests(unittest.TestCase):
    def test_shared_boundary_and_interior(self):
        a = [[0, 0], [.5, 0], [.5, 1], [0, 1]]
        b = [[.5, 0], [1, 0], [1, 1], [.5, 1]]
        self.assertFalse(polygons_overlap(a, b))
        self.assertTrue(contains((.5, .5), a))
        self.assertFalse(contains((.5, .5), a, False))

    def test_identical_and_crossed_zones_rejected(self):
        p = [[0, 0], [.7, 0], [.7, .7], [0, .7]]
        self.assertTrue(polygons_overlap(p, p))
        c = config(); c.inside_zone = c.outside_zone
        with self.assertRaises(ValueError):
            c.validate()
        with self.assertRaises(ValueError):
            validate_polygon([[0, 0], [1, 1], [0, 1], [1, 0]], "test")

    def test_nonfinite_or_pixel_zones_rejected(self):
        for value in (float("nan"), float("inf"), 720):
            with self.assertRaises(ValueError):
                validate_polygon([[0, 0], [1, 0], [value, 1]], "test")


class ConfigTests(unittest.TestCase):
    def test_atomic_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "camera.json"
            save_config(config(), path)
            self.assertEqual(load_config(path), config())
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_bad_threshold_and_vendor_schema_rejected(self):
        for key, value in (("bird_confidence", 2), ("retention_days", -1), ("image_size", 640.5),
                           ("cooldown_seconds", float("nan"))):
            c = config(); setattr(c, key, value)
            with self.assertRaises(ValueError):
                c.validate()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.json"; p.write_text('{"rtsp_url":"example"}')
            with self.assertRaisesRegex(ValueError, "Unknown configuration"):
                load_config(p)


class RuleTests(unittest.TestCase):
    def crossings(self, points, times=None):
        r = RuleEngine(config())
        events = []
        for i, x in enumerate(points):
            events += r.crossing([box(x)], times[i] if times else i * .04)
        return events

    def test_outside_inside_crossing(self):
        events = self.crossings([.38, .42, .46, .50, .54, .58])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].kind, "suspected_throw")

    def test_reverse_and_inside_only_do_not_alert(self):
        self.assertEqual(self.crossings([.60, .56, .52, .48, .44, .40]), [])
        self.assertEqual(self.crossings([.60, .64, .68, .72]), [])

    def test_slow_crossing_and_short_jitter_do_not_alert(self):
        c = config(); c.min_throw_speed = .5
        r = RuleEngine(c)
        alerts = []
        for i in range(30):
            alerts += r.crossing([box(.40 + i*.005)], i * .1)
        self.assertEqual(alerts, [])
        self.assertEqual(self.crossings([.470, .473, .476, .479, .482]), [])

    def test_missing_track_cannot_cross_later(self):
        self.assertEqual(self.crossings([.40, .44, .48, .54], [0, .04, .08, 2]), [])

    def test_stale_track_never_reemitted(self):
        r = RuleEngine(config())
        events = []
        for i, x in enumerate([.38, .42, .46, .50, .54]):
            events += r.crossing([box(x)], i*.04)
        self.assertEqual(len(events), 1)
        for i in range(20):
            self.assertEqual(r.crossing([], .20 + i*.04), [])

    def test_person_requires_movement_and_time(self):
        r = RuleEngine(config())
        for t in (0, .2, .4, .6, .8):
            self.assertEqual(r.person_movement([box(.65, .6, .03)], t), [])
        self.assertEqual(len(r.person_movement([box(.69, .6, .03)], 1.0)), 1)
        self.assertEqual(r.person_movement([box(.72, .6, .03)], 1.2), [])

    def test_person_disappears_and_new_person_must_reconfirm(self):
        r = RuleEngine(config())
        r.person_movement([box(.65)], 0)
        r.person_movement([], 2)
        self.assertEqual(r.person_movement([box(.70)], 3), [])

    def test_cooldown_uses_source_time_and_reset(self):
        c = config(); c.cooldown_seconds = 8
        r = RuleEngine(c)
        r.emitted("suspected_throw", 10)
        self.assertFalse(r.permitted("suspected_throw", 17.9))
        self.assertTrue(r.permitted("suspected_throw", 18))
        r.reset()
        self.assertTrue(r.permitted("suspected_throw", 0))

    def test_ignore_zone(self):
        c = config(); c.ignore_zones = [[[0, .4], [1, .4], [1, .6], [0, .6]]]
        r = RuleEngine(c)
        self.assertFalse(any(r.crossing([box(x)], i*.04) for i,x in enumerate([.38,.42,.46,.50,.54])))

    def test_one_to_one_association(self):
        tracker = Tracker(.08, .3)
        initial = tracker.update([box(.4), box(.5)], 0)
        updated = tracker.update([box(.44), box(.46)], .04)
        self.assertEqual(len({t.id for t in updated}), 2)
        self.assertEqual({t.id for t in initial}, {t.id for t in updated})


class StoreTests(unittest.TestCase):
    def test_persistence_acknowledgment_and_csv(self):
        with tempfile.TemporaryDirectory() as d:
            store = EventStore(d)
            c = Candidate("suspected_throw", 12.3, 1, box(.6), [], "review")
            event_id = store.add(c, "=danger", "run-a")
            self.assertEqual(EventStore(d).list()[0]["id"], event_id)
            store.acknowledge([event_id], "Bird after review")
            self.assertEqual(store.list(unacknowledged=True), [])
            self.assertEqual(store.list()[0]["note"], "Bird after review")
            path = Path(d) / "export.csv"
            store.export_csv(path)
            with path.open(encoding="utf-8-sig") as f:
                row = next(csv.DictReader(f))
            self.assertEqual(row["camera"], "'=danger")
            self.assertEqual(row["source_time"], "12.3")

    def test_retention_and_path_escape(self):
        with tempfile.TemporaryDirectory() as d:
            store = EventStore(d)
            for i in range(4):
                store.add(Candidate("person_movement", i, i, box(.6), [], "review"), "cam", "run")
            store.prune(14, 2)
            self.assertEqual(len(store.list()), 2)
            with self.assertRaises(ValueError):
                store.snapshot_path("../../unrelated.jpg")


if __name__ == "__main__":
    unittest.main()
