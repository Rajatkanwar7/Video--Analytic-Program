import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch

import numpy as np
from jailwatch.config import Config
from jailwatch.detector import Detection,YoloDetector,verify_track


class DetectorTests(unittest.TestCase):
    def test_custom_object_threshold_is_independent_of_person_threshold(self):
        with tempfile.TemporaryDirectory() as d:
            weights=Path(d)/"weights.pt"; weights.write_bytes(b"test placeholder")
            model=Mock(); model.names={0:"person",1:"bird",2:"thrown_object"}
            model.predict.return_value=[SimpleNamespace(boxes=SimpleNamespace(data=Mock()))]
            model.predict.return_value[0].boxes.data.cpu.return_value.tolist.return_value=[
                [40,40,60,60,.36,2],[40,40,60,60,.40,0],[40,40,60,60,.19,1]]
            c=Config(model=str(weights),require_object_class=True)
            with patch.dict("sys.modules",{"ultralytics":SimpleNamespace(YOLO=lambda *a,**k:model)}):
                detector=YoloDetector(c)
                result=detector.predict(np.zeros((100,100,3),np.uint8))
            self.assertEqual([r.label for r in result],["thrown_object"])

    def test_generic_weights_cannot_silently_enable_custom_class_requirement(self):
        with tempfile.TemporaryDirectory() as d:
            weights=Path(d)/"weights.pt"; weights.write_bytes(b"test placeholder")
            model=SimpleNamespace(names={0:"person",1:"bird"})
            with patch.dict("sys.modules",{"ultralytics":SimpleNamespace(YOLO=lambda *a,**k:model)}):
                with self.assertRaisesRegex(ValueError,"custom model"):
                    YoloDetector(Config(model=str(weights),require_object_class=True))

    def test_bird_in_earlier_sample_overrides_custom_object_match(self):
        class Detector:
            def predict(self,image):
                label="bird" if image[0,0,0] else "thrown_object"
                return [Detection(label,.9,(.4,.4,.6,.6))]
        full=np.zeros((100,100,3),np.uint8)
        bird=np.ones((100,100,3),np.uint8)
        self.assertEqual(verify_track(Detector(),full,(.4,.4,.6,.6),[(0,bird,(.4,.4,.6,.6))]),"bird")
