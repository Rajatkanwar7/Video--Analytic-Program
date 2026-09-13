import csv
import json
import tempfile
import time
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path

import cv2
import numpy as np

from jailwatch.vms.devices import Camera,Preferences
from jailwatch.vms.recording import Recorder,RecordingStore,recording_command


def make_video(path, frames=50):
    writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*"MJPG"),10,(320,180))
    if not writer.isOpened():
        raise RuntimeError("Synthetic video writer unavailable")
    for i in range(frames):
        image=np.zeros((180,320,3),np.uint8)
        cv2.rectangle(image,(i*3%280,70),(i*3%280+20,90),(0,220,190),-1)
        writer.write(image)
    writer.release()


class RecordingTests(unittest.TestCase):
    def test_ffmpeg_stream_copy_segment_is_indexed_and_playable_after_stop(self):
        with tempfile.TemporaryDirectory() as root:
            source=Path(root,"source.avi"); make_video(source)
            camera=Camera(name="Test camera"); camera.config.source=str(source)
            store=RecordingStore(root); recorder=Recorder(camera,store,Preferences(segment_seconds=10))
            recorder.desired=True
            try:
                recorder.tick()
                deadline=time.monotonic()+4
                while time.monotonic()<deadline and recorder.status!="REC":
                    time.sleep(.1); recorder.tick()
            finally:
                recorder.stop()
            rows=store.list()
            self.assertGreater(len(rows),0)
            self.assertGreater(rows[0]["duration"],0)
            self.assertIsNone(recorder.process)
            decoder=cv2.VideoCapture(str(store.safe_path(rows[0]["path"])))
            try:
                self.assertTrue(decoder.read()[0])
            finally:
                decoder.release()
            exported=Path(root,"export.mkv"); store.export(rows[0]["path"],exported)
            self.assertEqual(exported.stat().st_size,rows[0]["bytes"])
            self.assertEqual(len(RecordingStore(root).list()),len(rows))

    def test_retention_only_deletes_indexed_closed_segments_and_respects_playback(self):
        with tempfile.TemporaryDirectory() as root:
            store=RecordingStore(root); camera=Camera(name="Gate")
            folder=store.new_session(camera)
            metadata=json.loads((folder/"session.json").read_text())
            metadata["started_utc"]=(datetime.now(timezone.utc)-timedelta(days=30)).isoformat()
            (folder/"session.json").write_text(json.dumps(metadata))
            closed=folder/"clip_000000.mkv"; closed.write_bytes(b"closed test segment")
            active=folder/"clip_000001.mkv"; active.write_bytes(b"active test segment")
            unrelated=store.root/"unrelated.txt"; unrelated.write_text("keep")
            with (folder/"segments.csv").open("w",newline="") as f:
                csv.writer(f).writerow([str(closed),0,10])
            store.index_session(folder); row=store.list()[0]
            store.pinned.add(row["path"])
            self.assertEqual(store.prune(7,10000),0)
            store.pinned.clear()
            self.assertEqual(store.prune(7,10000),1)
            self.assertTrue(active.exists()); self.assertTrue(unrelated.exists())
            with self.assertRaises(ValueError):
                store.safe_path("../outside.mkv")

    def test_command_preserves_original_codecs_and_never_uses_shell_interpolation(self):
        uri="rtsp://operator:p%40ss@192.0.2.1/stream?channel=1&subtype=0"
        args=recording_command("ffmpeg",uri,Path("recording folder"),300)
        self.assertEqual(args[args.index("-i")+1],uri)
        self.assertEqual(args[args.index("-c")+1],"copy")
        self.assertIn("matroska",args)
