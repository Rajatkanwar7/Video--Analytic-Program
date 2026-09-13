"""Exercise the frozen Windows package on synthetic local media, never a real camera."""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from contextlib import ExitStack


def run(destination, screenshot=None):
    destination = Path(destination).resolve()
    report = {"passed":False,"scope":"Synthetic local media and packaged CPU inference; no physical-camera accuracy test"}
    app = None
    def close_app():
        nonlocal app
        if app is not None:
            try:
                app.manager.close()
                app.after_cancel(app.poll_id)
            finally:
                app.destroy()
                app = None
    try:
        import cv2
        import numpy as np
        import torch
        import requests
        from PIL import ImageGrab
        from jailwatch.config import Config
        from jailwatch.detector import YoloDetector
        from .devices import Camera,bundled_model
        from .onvif import envelope,DEVICE
        from .recording import ffmpeg_executable
        from .ui import VMSApp
        torch.set_num_threads(2)
        detector = YoloDetector(Config(model=bundled_model(),image_size=640,device="cpu"))
        detector.predict(np.zeros((360,640,3),np.uint8))
        report["cpu_yolo_inference"] = True
        report["torch_version"] = torch.__version__
        report["opencv_version"] = cv2.__version__
        report["ffmpeg_found"] = Path(ffmpeg_executable()).is_file()
        envelope(DEVICE,"GetServices","test","test")
        with requests.Session():
            pass
        with ExitStack() as stack:
            root = stack.enter_context(tempfile.TemporaryDirectory(prefix="jailwatch-selftest-"))
            source = Path(root)/"demonstration.avi"
            writer = cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*"MJPG"),15,(640,360))
            if not writer.isOpened():
                raise RuntimeError("Synthetic video encoding unavailable")
            for i in range(240):
                frame = np.full((360,640,3),(30,23,17),np.uint8)
                cv2.rectangle(frame,(0,235),(640,270),(65,76,85),-1)
                cv2.line(frame,(320,40),(320,320),(80,160,180),2)
                x=60+i*3%500
                cv2.circle(frame,(x,130+round(30*np.sin(i/20))),7,(90,220,230),-1)
                cv2.putText(frame,"SIMULATED VIDEO / NO LIVE DEVICE",(25,40),cv2.FONT_HERSHEY_SIMPLEX,.55,(160,185,200),1)
                cv2.putText(frame,"OUTSIDE",(55,320),cv2.FONT_HERSHEY_SIMPLEX,.6,(80,180,230),1)
                cv2.putText(frame,"INSIDE",(445,320),cv2.FONT_HERSHEY_SIMPLEX,.6,(110,215,130),1)
                writer.write(frame)
            writer.release()
            input_source = str(source)
            if os.environ.get("JAILWATCH_RTSP_TEST_SERVER"):
                from .rtsp_fixture import RtspFixture
                input_source = stack.enter_context(RtspFixture(source))
                report["loopback_rtsp"] = True
            app = VMSApp(Path(root)/"vms")
            stack.callback(close_app)
            app.geometry("1260x810+0+0")
            for i,name in enumerate(("Demo · North wall","Demo · Entry gate","Demo · Tower 01","Demo · Service lane")):
                camera = Camera(name=name,group="Demonstration")
                camera.config.source = input_source
                app.inventory.put(camera)
            app.refresh_devices(); app.start_all()
            deadline = time.monotonic()+15
            while time.monotonic()<deadline:
                app.update(); time.sleep(.03)
                if all(w.snapshot()[1] is not None for w in app.manager.workers.values()):
                    break
            if not all(w.snapshot()[1] is not None for w in app.manager.workers.values()):
                raise RuntimeError("Camera grid did not receive all synthetic streams")
            report["simultaneous_video_sources"] = len(app.manager.workers)
            first = app.inventory.cameras[0]
            app.select_camera(first.id)
            app.manager.set_recording(first.id,True)
            deadline = time.monotonic()+3
            while time.monotonic()<deadline:
                app.update(); time.sleep(.03)
            app.manager.set_recording(first.id,False)
            deadline = time.monotonic()+7
            while time.monotonic()<deadline and not app.recordings.list():
                app.update(); time.sleep(.03)
            rows = app.recordings.list()
            if not rows:
                raise RuntimeError("Packaged FFmpeg did not finalize a recording")
            cap = cv2.VideoCapture(str(app.recordings.safe_path(rows[0]["path"])))
            try:
                if not cap.read()[0]:
                    raise RuntimeError("Packaged decoder could not play the recording")
            finally:
                cap.release()
            report["recording_and_playback"] = True
            app.test_alarm(); app.refresh_alarms(); app.update()
            if screenshot:
                ImageGrab.grab(bbox=(app.winfo_rootx(),app.winfo_rooty(),
                    app.winfo_rootx()+app.winfo_width(),app.winfo_rooty()+app.winfo_height())).save(screenshot)
            report["desktop_and_test_alarm"] = bool(app.events.list())
            close_app()
            report["passed"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        close_app()
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
