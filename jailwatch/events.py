from __future__ import annotations

import csv
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .trajectory import trajectory_stats


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class EventStore:
    """One short-lived SQLite connection per operation, safe across UI/worker threads."""
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.snapshots = self.directory / "snapshots"
        self.snapshots.mkdir(exist_ok=True)
        self.path = self.directory / "events.sqlite3"
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY, camera TEXT NOT NULL, run_id TEXT NOT NULL,
                created_utc TEXT NOT NULL, source_time REAL NOT NULL, kind TEXT NOT NULL,
                message TEXT NOT NULL, snapshot TEXT NOT NULL, details TEXT NOT NULL,
                acknowledged_utc TEXT, note TEXT NOT NULL DEFAULT '')""")
            db.execute("CREATE INDEX IF NOT EXISTS events_created ON events(created_utc)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.row_factory = sqlite3.Row
            # SQLite's context manager commits/rolls back but does not close.
            with db:
                yield db
        finally:
            db.close()

    def add(self, candidate, camera, run_id, image=None, details=None):
        event_id = uuid.uuid4().hex
        snapshot = ""
        extra = dict(details or {})
        extra["trajectory"] = candidate.trajectory
        extra["box"] = list(candidate.box)
        extra["track_id"] = candidate.track_id
        if image is not None:
            import cv2
            destination = self.snapshots / f"{event_id}.jpg"
            if not cv2.imwrite(str(destination), image):
                raise OSError("Cannot save alert snapshot. Check free disk space and folder permissions.")
            snapshot = destination.name
        try:
            with self.connect() as db:
                db.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
                    event_id, camera, run_id, utc_now(), candidate.source_time, candidate.kind,
                    candidate.message, snapshot, json.dumps(extra, allow_nan=False), None, ""))
        except Exception:
            if snapshot:
                (self.snapshots / snapshot).unlink(missing_ok=True)
            raise
        return event_id

    def list(self, limit=300, unacknowledged=False):
        where = " WHERE acknowledged_utc IS NULL" if unacknowledged else ""
        with self.connect() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM events" + where + " ORDER BY created_utc DESC, rowid DESC LIMIT ?", (limit,))]

    def acknowledge(self, ids, note=""):
        with self.connect() as db:
            db.executemany("UPDATE events SET acknowledged_utc=?, note=? WHERE id=? AND acknowledged_utc IS NULL",
                           [(utc_now(), note[:1000], i) for i in ids])

    def snapshot_path(self, name):
        path = (self.snapshots / name).resolve()
        if not name or path.parent != self.snapshots.resolve() or path.suffix != ".jpg":
            raise ValueError("Invalid snapshot path.")
        return path

    def prune(self, days, max_events):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        with self.connect() as db:
            old = db.execute("""SELECT id,snapshot FROM events WHERE created_utc < ? OR id IN
                (SELECT id FROM events ORDER BY created_utc DESC,rowid DESC LIMIT -1 OFFSET ?)""",
                (cutoff, max_events)).fetchall()
            db.executemany("DELETE FROM events WHERE id=?", [(r["id"],) for r in old])
        for row in old:
            if row["snapshot"]:
                self.snapshot_path(row["snapshot"]).unlink(missing_ok=True)

    def export_csv(self, path):
        columns = ["id", "camera", "run_id", "created_utc", "source_time", "kind", "message",
                   "snapshot", "acknowledged_utc", "note"]
        def safe(value):
            if value is None:
                return ""
            text = str(value)
            return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text
        with self.connect() as db, Path(path).open("w", newline="", encoding="utf-8-sig") as out:
            writer = csv.writer(out)
            writer.writerow(columns)
            for row in db.execute("SELECT * FROM events ORDER BY created_utc,rowid"):
                writer.writerow([safe(row[c]) for c in columns])

    def export_trajectories(self, path, ids):
        """Export selected saved paths; old events without image size retain normalized coordinates."""
        if not ids:
            raise ValueError("Select at least one event with a trajectory.")
        selected = set(ids)
        output = []
        with self.connect() as db:
            for row in db.execute("SELECT * FROM events ORDER BY created_utc,rowid"):
                if row["id"] not in selected:
                    continue
                details = json.loads(row["details"])
                points = details.get("trajectory", [])
                trajectory_stats(points)
                size = details.get("image_size")
                for t,x,y in points:
                    output.append([row["id"],row["run_id"],row["kind"],details.get("track_id", ""),
                                   t,x,y,x*size[0] if size else "",y*size[1] if size else "",
                                   size[0] if size else "",size[1] if size else ""])
        if not output:
            raise ValueError("The selected events contain no measured trajectory. A test alarm has no object path.")
        with Path(path).open("w",newline="",encoding="utf-8-sig") as out:
            writer = csv.writer(out)
            writer.writerow(["event_id","run_id","kind","track_id","source_time_seconds",
                             "x_normalized","y_normalized","x_pixels","y_pixels","image_width","image_height"])
            writer.writerows(output)
        return len(output)

    def save_run(self, summary):
        run_id = summary.get("run_id", "")
        if not re.fullmatch(r"[a-f0-9]{32}",run_id):
            raise ValueError("Invalid run identifier.")
        directory = self.directory / "runs"
        directory.mkdir(exist_ok=True)
        path = directory / f"{run_id}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        temporary.replace(path)
        return str(path)
