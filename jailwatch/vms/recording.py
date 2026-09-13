"""Independent stream-copy recording, indexed closed segments and bounded storage."""
from __future__ import annotations

import csv
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path


def ffmpeg_executable():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def recording_command(executable, source, folder, segment_seconds):
    command = [executable,"-hide_banner","-loglevel","error","-y"]
    if source.startswith(("rtsp://","rtsps://")):
        command += ["-rtsp_transport","tcp","-timeout","5000000"]
    else:
        command += ["-re"]
    return command+["-i",source,"-map","0:v:0","-map","0:a?","-c","copy",
                    "-f","segment","-segment_format","matroska","-segment_time",str(segment_seconds),
                    "-reset_timestamps","1","-segment_list",str(Path(folder)/"segments.csv"),
                    "-segment_list_type","csv",str(Path(folder)/"clip_%06d.mkv")]


class RecordingStore:
    def __init__(self, root):
        self.root = Path(root).resolve()/"recordings"
        self.root.mkdir(parents=True,exist_ok=True)
        self.database = self.root/"recordings.sqlite3"
        self.lock = threading.RLock()
        self.pinned = set()
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS recordings (
                path TEXT PRIMARY KEY, camera_id TEXT NOT NULL, camera TEXT NOT NULL,
                started_utc TEXT NOT NULL, duration REAL NOT NULL, bytes INTEGER NOT NULL)""")
        self.recover()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database,timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def safe_path(self, value):
        path = (self.root/value).resolve()
        if not path.is_relative_to(self.root) or path.suffix != ".mkv":
            raise ValueError("Recording path is outside the VMS recording folder.")
        return path

    def new_session(self, camera):
        folder = self.root/camera.id/uuid.uuid4().hex
        folder.mkdir(parents=True)
        metadata = {"camera_id":camera.id,"camera":camera.name,
                    "started_utc":datetime.now(timezone.utc).isoformat()}
        (folder/"session.json").write_text(json.dumps(metadata),encoding="utf-8")
        return folder

    def index_session(self, folder):
        folder = Path(folder).resolve()
        if not folder.is_relative_to(self.root):
            raise ValueError("Recording session is outside the VMS folder.")
        manifest = folder/"segments.csv"
        if not manifest.exists():
            return 0
        metadata = json.loads((folder/"session.json").read_text(encoding="utf-8"))
        start = datetime.fromisoformat(metadata["started_utc"])
        count = 0
        with manifest.open(newline="",encoding="utf-8") as stream, self.connect() as db:
            for row in csv.reader(stream):
                if len(row) != 3:
                    continue
                name = Path(row[0]).name
                if not re.fullmatch(r"clip_\d{6,}\.mkv",name):
                    continue
                try:
                    begin,end = float(row[1]),float(row[2])
                    if not all(math.isfinite(v) for v in (begin,end)) or begin < 0 or end <= begin:
                        continue
                    path = self.safe_path(str((folder/name).relative_to(self.root)))
                    if not path.is_file():
                        continue
                    inserted = db.execute("INSERT OR IGNORE INTO recordings VALUES (?,?,?,?,?,?)",
                        (str(path.relative_to(self.root)),metadata["camera_id"],metadata["camera"],
                         (start+timedelta(seconds=begin)).isoformat(),end-begin,path.stat().st_size))
                    count += inserted.rowcount
                except (ValueError,OSError):
                    continue
        return count

    def recover(self):
        # Re-index completed segments after a crash; never guess a duration for an unfinished file.
        for manifest in self.root.glob("*/*/session.json"):
            try:
                self.index_session(manifest.parent)
            except (OSError,ValueError):
                continue

    def list(self, camera_id=None, date="", limit=1000):
        conditions,values = [],[]
        if camera_id:
            conditions.append("camera_id=?"); values.append(camera_id)
        if date:
            datetime.strptime(date,"%Y-%m-%d")
            conditions.append("started_utc LIKE ?"); values.append(date+"%")
        where = " WHERE "+" AND ".join(conditions) if conditions else ""
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM recordings"+where+
                    " ORDER BY started_utc DESC LIMIT ?",values+[limit])]

    def totals(self):
        with self.connect() as db:
            row = db.execute("SELECT COUNT(*), COALESCE(SUM(bytes),0) FROM recordings").fetchone()
        return {"segments":row[0],"bytes":row[1],"free_bytes":shutil.disk_usage(self.root).free}

    def prune(self, days, quota_bytes):
        cutoff = (datetime.now(timezone.utc)-timedelta(days=days)).isoformat()
        deleted = 0
        with self.lock, self.connect() as db:
            rows = db.execute("SELECT * FROM recordings ORDER BY started_utc").fetchall()
            total = sum(row["bytes"] for row in rows)
            for row in rows:
                if row["path"] in self.pinned:
                    continue
                if row["started_utc"] >= cutoff and total <= quota_bytes:
                    continue
                try:
                    self.safe_path(row["path"]).unlink(missing_ok=True)
                except OSError:
                    continue
                db.execute("DELETE FROM recordings WHERE path=?",(row["path"],))
                total -= row["bytes"]; deleted += 1
        return deleted

    def export(self, relative, target):
        with self.lock:
            source = self.safe_path(relative)
            destination = Path(target).resolve()
            if destination == source or destination.is_relative_to(self.root):
                raise ValueError("Export to a folder outside the managed recording storage.")
            shutil.copy2(source,destination)


class Recorder:
    def __init__(self, camera, store, preferences, executable_factory=ffmpeg_executable):
        self.camera,self.store,self.preferences = camera,store,preferences
        self.executable_factory = executable_factory
        self.process = None
        self.folder = None
        self.status = "Recording off"
        self.desired = False
        self.last_start = -1e20
        self.last_tick = 0
        self.last_growth = time.monotonic()
        self.last_marker = None

    def tick(self):
        now = time.monotonic()
        if now-self.last_tick < 1:
            return
        self.last_tick = now
        if not self.desired:
            if self.process:
                self.stop()
            return
        if shutil.disk_usage(self.store.root).free < 1024**3:
            self.stop(); self.desired = True
            self.status = "RECORDING PAUSED: less than 1 GB free"
            return
        if self.process and self.process.poll() is not None:
            self._finish()
            self.status = "Recording interrupted; reconnecting"
        if self.process is None:
            if now-self.last_start < 5:
                return
            self.last_start = now
            try:
                self.folder = self.store.new_session(self.camera)
                command = recording_command(self.executable_factory(),self.camera.config.resolved_source(),
                                            self.folder,self.preferences.segment_seconds)
                self.process = subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
                self.last_growth = now; self.last_marker = None
                self.status = "Starting recording"
            except (OSError,RuntimeError,ValueError):
                self.status = "Recording failed: check FFmpeg, stream and storage"
                return
        if self.folder and self.process:
            self.store.index_session(self.folder)
            files = sorted(self.folder.glob("clip_*.mkv"))
            latest = files[-1] if files else None
            marker = (latest.name,latest.stat().st_size) if latest and latest.is_file() else None
            if marker and marker[1]>0 and marker!=self.last_marker:
                self.last_growth = now; self.last_marker = marker
                self.status = "REC"
            elif now-self.last_growth > 20:
                self.stop(); self.desired = True
                self.status = "Recording stalled; retrying"

    def _finish(self):
        if self.process:
            if self.process.stdin:
                self.process.stdin.close()
            self.process = None
        if self.folder:
            self.store.index_session(self.folder)

    def stop(self):
        self.desired = False
        if self.process and self.process.poll() is None:
            try:
                self.process.stdin.write(b"q\n"); self.process.stdin.flush()
                self.process.wait(timeout=5)
            except (OSError,subprocess.TimeoutExpired):
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill(); self.process.wait(timeout=2)
        self._finish()
        self.status = "Recording off"
