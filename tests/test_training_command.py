"""Check training/evaluation wiring without downloading weights or running AI."""
import contextlib
import io
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.train_model import main


class TrainingCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.weights = self.root / "trusted_local.pt"
        self.weights.write_bytes(b"test stub; never loaded as real weights")
        self.report = {"valid": True, "errors": [], "warnings": [], "splits": {},
                       "resolved_data": {"path": str(self.root), "train": "images/train",
                                         "val": "images/val", "test": "images/test",
                                         "names": {0: "person", 1: "bird", 2: "thrown_object"}}}
        self.model = Mock()
        self.model.names = self.report["resolved_data"]["names"]
        self.model.trainer.best = self.root / "best.pt"
        self.module = types.SimpleNamespace(YOLO=Mock(return_value=self.model))
        self.arguments = ["--data", str(self.root / "dataset.yaml"), "--weights", str(self.weights),
                          "--project", str(self.root / "runs"), "--name", "trial"]

    def invoke(self, extra):
        with patch("scripts.train_model.check_dataset", return_value=self.report) as checker, \
                patch.dict("sys.modules", {"ultralytics": self.module}), \
                contextlib.redirect_stdout(io.StringIO()):
            result = main(self.arguments + extra)
        return result, checker

    def test_training_uses_checked_absolute_yaml_and_preserves_run_settings(self):
        result, _ = self.invoke(["--epochs", "5", "--batch", "2", "--seed", "7"])
        self.assertEqual(result, 0)
        arguments = self.model.train.call_args.kwargs
        self.assertTrue(Path(arguments["data"]).is_absolute())
        self.assertTrue(Path(arguments["data"]).is_file())
        self.assertEqual(arguments["close_mosaic"], 5)
        self.assertEqual(arguments["batch"], 2)
        self.assertEqual(arguments["seed"], 7)
        settings = json.loads((self.root / "runs/trial/settings.json").read_text())
        self.assertEqual(settings["epochs"], 5)
        self.model.val.assert_not_called()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.invoke([])
        self.assertEqual(self.model.train.call_count, 1)  # Never overwrite an earlier run.

    def test_held_out_test_evaluates_without_training_and_saves_metrics(self):
        self.model.val.return_value.results_dict = {"metrics/mAP50(B)": .5}
        result, checker = self.invoke(["--mode", "test"])
        self.assertEqual(result, 0)
        self.assertTrue(checker.call_args.kwargs["require_test"])
        self.assertEqual(self.model.val.call_args.kwargs["split"], "test")
        self.model.train.assert_not_called()
        metrics = json.loads((self.root / "runs/trial/metrics.json").read_text())
        self.assertEqual(metrics["metrics/mAP50(B)"], .5)
        self.assertIn("Bounding-box metrics only", metrics["meaning"])
