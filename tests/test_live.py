"""Deterministic tests for live inference backpressure and stale result rejection."""
import tempfile
import threading
import time
import unittest

import numpy as np

from jailwatch.capture import Frame
from jailwatch.events import EventStore
from jailwatch.inference import LiveInference
from jailwatch.pipeline import Pipeline
from jailwatch.rules import Candidate
from test_core import box, config


class LiveTests(unittest.TestCase):
    def test_slow_ai_does_not_block_motion_and_event_is_verified_later(self):
        c = config()
        entered, release = threading.Event(), threading.Event()
        owner = []
        class Detector:
            def __init__(self, _):
                owner.append(threading.get_ident())
            def predict(self, image):
                assert threading.get_ident() == owner[0]
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("Test release timeout")
                return []
        service = LiveInference(c, Detector)
        self.assertTrue(service.ready.wait(2))
        with tempfile.TemporaryDirectory() as d:
            pipeline = Pipeline(c, None, EventStore(d), live_ai=service)
            try:
                for i in range(80):
                    image = np.zeros((360,640,3), np.uint8)
                    if 20 <= i <= 60:
                        x = 100+(i-20)*9
                        image[170:180,x:x+10] = 255
                    pipeline.process(Frame(image,i/25,i,0,time.monotonic()))
                    if i == 0:
                        self.assertTrue(entered.wait(2))
                # All motion frames were analyzed while the detector was blocked.
                self.assertEqual(pipeline.processed,80)
                self.assertEqual(pipeline.store.list(),[])
                release.set()
                deadline = time.monotonic()+4
                while time.monotonic() < deadline and not pipeline.store.list():
                    pipeline._drain_ai()
                    threading.Event().wait(.01)
                rows = pipeline.store.list()
                self.assertEqual(len(rows),1)
                self.assertEqual(rows[0]["kind"],"suspected_throw")
                self.assertLess(rows[0]["source_time"],3)
            finally:
                release.set(); service.close()

    def test_bounded_candidate_queue_reports_overflow(self):
        entered, release = threading.Event(), threading.Event()
        class Detector:
            def __init__(self,_):
                pass
            def predict(self,image):
                entered.set(); release.wait(3)
                return []
        service=LiveInference(config(),Detector,max_candidates=1)
        self.assertTrue(service.ready.wait(2))
        image=np.zeros((100,100,3),np.uint8)
        try:
            service.submit_semantic(1,0,image)
            self.assertTrue(entered.wait(2))
            candidate=Candidate("suspected_throw",1,1,box(.6),[],"review")
            self.assertTrue(service.submit_candidate(1,candidate,image,[]))
            self.assertFalse(service.submit_candidate(1,candidate,image,[]))
            self.assertEqual(service.dropped_candidates,1)
        finally:
            release.set(); service.close()

    def test_old_generation_cannot_alarm_after_reconnect(self):
        class ResultSource:
            def reset_pending(self):
                pass
            def poll(self):
                return [{"type":"candidate", "generation":1, "candidate":
                    Candidate("suspected_throw",.5,1,box(.6),[],"old frame"),
                    "image":np.zeros((100,100,3),np.uint8),"label":None}]
        with tempfile.TemporaryDirectory() as d:
            pipeline=Pipeline(config(),None,EventStore(d),live_ai=ResultSource())
            pipeline.reset(0); pipeline.reset(2)
            self.assertEqual(pipeline._drain_ai(),[])
            self.assertEqual(pipeline.store.list(),[])

    def test_model_failure_is_visible(self):
        def broken(_):
            raise ValueError("Model missing")
        service=LiveInference(config(),broken)
        try:
            self.assertTrue(service.ready.wait(2))
            with self.assertRaisesRegex(ValueError,"Model missing"):
                service.poll()
        finally:
            service.close()
