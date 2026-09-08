import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("evaluate_events", Path(__file__).parents[1]/"scripts/evaluate_events.py")
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


class EvaluationTests(unittest.TestCase):
    def test_false_alarms_per_hour_use_reviewed_duration(self):
        result=evaluation.evaluate([1,5,8],[(0,2)],duration_seconds=600)
        self.assertEqual(result["false_alarms_per_hour"],12)
        self.assertEqual(result["f1"],.5)
        with self.assertRaises(ValueError): evaluation.evaluate([700],[],600)

    def test_long_runs_do_not_recurse_and_invalid_alerts_are_rejected(self):
        self.assertEqual(evaluation.evaluate([1]*2000,[(0,2)]*2000)["true_positives"],2000)
        with self.assertRaises(ValueError): evaluation.evaluate([float('nan')],[])

    def test_overlapping_intervals_match_once(self):
        result = evaluation.evaluate([1.5, 2.5], [(1, 3), (1, 2)])
        self.assertEqual(result["true_positives"], 2)
        self.assertEqual(result["false_positives"], 0)

    def test_duplicate_alert_is_false_positive(self):
        result = evaluation.evaluate([1.5, 1.6, 8], [(1, 2), (4, 5)])
        self.assertEqual(result["true_positives"], 1)
        self.assertEqual(result["false_positives"], 2)
        self.assertEqual(result["false_negatives"], 1)

    def test_no_alerts_has_zero_recall_and_undefined_precision(self):
        result = evaluation.evaluate([], [(1, 2)])
        self.assertEqual(result["recall"], 0)
        self.assertIsNone(result["precision"])
