"""Loopback-only RTSP integration fixture, enabled explicitly by the build/test environment."""
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from .recording import ffmpeg_executable


class RtspFixture:
    def __init__(self, video):
        self.video=video
        self.server=None; self.publisher=None; self.tmp=None

    def __enter__(self):
        executable=Path(os.environ["JAILWATCH_RTSP_TEST_SERVER"])
        if not executable.is_file():
            raise ValueError("The explicitly configured RTSP test server is missing.")
        self.tmp=tempfile.TemporaryDirectory(prefix="jailwatch-rtsp-test-")
        with socket.socket() as address:
            address.bind(("127.0.0.1",0)); port=address.getsockname()[1]
        self.url=f"rtsp://127.0.0.1:{port}/synthetic"
        config=Path(self.tmp.name)/"mediamtx.yml"
        config.write_text(f"logLevel: error\nrtsp: true\nrtspAddress: 127.0.0.1:{port}\nrtspTransports: [tcp]\nrtmp: false\nhls: false\nwebrtc: false\nsrt: false\napi: false\nmetrics: false\npprof: false\nplayback: false\npaths:\n  all_others:\n",encoding="utf-8")
        options={"stdout":subprocess.DEVNULL,"stderr":subprocess.DEVNULL,
                 "creationflags":subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0}
        try:
            self.server=subprocess.Popen([str(executable.resolve()),str(config)],cwd=self.tmp.name,**options)
            deadline=time.monotonic()+8
            while True:
                try:
                    with socket.create_connection(("127.0.0.1",port),timeout=.3):
                        break
                except OSError:
                    if self.server.poll() is not None or time.monotonic()>deadline:
                        raise RuntimeError("Loopback RTSP test server did not start")
                    time.sleep(.05)
            self.publisher=subprocess.Popen([ffmpeg_executable(),"-hide_banner","-loglevel","error","-re",
                "-stream_loop","-1","-i",str(self.video),"-an","-c:v","libx264","-preset","ultrafast",
                "-tune","zerolatency","-g","15","-pix_fmt","yuv420p","-f","rtsp","-rtsp_transport","tcp",self.url],**options)
            return self.url
        except Exception:
            self.__exit__(None,None,None)
            raise

    def __exit__(self,*args):
        for process in (self.publisher,self.server):
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=3)
        if self.tmp:
            self.tmp.cleanup()
