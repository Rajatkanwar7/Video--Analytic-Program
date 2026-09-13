from __future__ import annotations

import base64
import copy
import ctypes
import json
import os
import re
import sys
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

from jailwatch.config import Config


def data_home():
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home()/"AppData/Local"))/"JailWatchVMS"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home()/".local/share"))/"JailWatchVMS"


def bundled_model():
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return str(root/"models/yolo11n.pt")


class DataLock:
    """One running VMS per data folder; avoid concurrent inventory and retention writers."""
    def __init__(self, root):
        root = Path(root).resolve(); root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.file = (root/"vms.lock").open("a+b")
        if self.file.tell()==0:
            self.file.write(b"0"); self.file.flush()
        self.file.seek(0)
        try:
            if os.name=="nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise ValueError("JailWatch VMS is already using this data folder. Open the existing window or close it first.") from None

    def close(self):
        if not self.file.closed:
            self.file.seek(0)
            if os.name=="nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_UN)
            self.file.close()


def protect(value, decrypt=False):
    """Windows current-user DPAPI. Other systems use explicitly marked private-file storage."""
    if not decrypt and sys.platform != "win32":
        return {"format": "private-file", "value": value}
    if decrypt:
        if value.get("format") == "private-file":
            return value["value"]
        if value.get("format") != "windows-dpapi" or sys.platform != "win32":
            raise ValueError("This camera login belongs to another Windows account. Re-enter it on this computer.")
        payload = base64.b64decode(value["value"], validate=True)
    else:
        payload = value.encode("utf-8")
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(payload)
    source = Blob(len(payload), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    operation = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    operation.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    operation.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ValueError("Windows could not protect or read this login. Re-enter it under this Windows account.")
    try:
        result = ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)
    return result.decode("utf-8") if decrypt else {"format": "windows-dpapi", "value": base64.b64encode(result).decode("ascii")}


def stream_url(host, port, path, username="", password=""):
    host = host.strip().strip("[]")
    if not host or any(c in host for c in "/\\@?# \t\r\n"):
        raise ValueError("Enter a camera IP or hostname without http:// or a stream path.")
    if not 1 <= int(port) <= 65535:
        raise ValueError("RTSP port must be between 1 and 65535.")
    address = f"[{host}]" if ":" in host else host
    login = f"{quote(username,safe='')}:{quote(password,safe='')}@" if username else ""
    result = f"rtsp://{login}{address}:{int(port)}/{path.lstrip('/')}"
    validate_source(result)
    return result


def validate_source(source):
    if Path(source).is_file():
        return
    p = urlsplit(source)
    if p.scheme not in ("rtsp", "rtsps") or not p.hostname or p.fragment:
        raise ValueError("Enter a complete RTSP video URL, or choose an existing video file.")
    if p.port is not None and not 1 <= p.port <= 65535:
        raise ValueError("Invalid RTSP port.")
    if any(c in source for c in ("\r", "\n", "\x00")):
        raise ValueError("The video URL contains invalid characters.")


def redacted_source(source):
    p = urlsplit(source)
    if p.scheme in ("rtsp", "rtsps"):
        host = p.hostname or "camera"
        host = f"[{host}]" if ":" in host else host
        # Query strings can also contain access tokens.
        return urlunsplit((p.scheme, host+(f":{p.port}" if p.port else ""), p.path, "", ""))
    return Path(source).name


@dataclass
class Camera:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    name: str = "New camera"
    group: str = "Default"
    analytics: bool = False
    config: Config = field(default_factory=lambda: Config(model=bundled_model()))

    def validate(self):
        if not re.fullmatch(r"[a-f0-9]{32}", self.id):
            raise ValueError("Invalid camera identifier.")
        if not self.name.strip() or len(self.name) > 80 or len(self.group) > 80:
            raise ValueError("Camera name is required and names/groups must fit in 80 characters.")
        if type(self.analytics) is not bool:
            raise ValueError("Analytics must be enabled or disabled.")
        self.config.camera_name = self.name
        validate_source(self.config.resolved_source())
        self.config.validate(zones=self.analytics)


@dataclass
class Preferences:
    retention_days: int = 7
    quota_gb: int = 100
    segment_seconds: int = 300
    max_live: int = 16
    max_analytics: int = 2
    beep: bool = True

    def validate(self):
        for key, low, high in [("retention_days",1,365),("quota_gb",1,100000),
                               ("segment_seconds",10,1800),("max_live",1,16),("max_analytics",1,8)]:
            v = getattr(self,key)
            if type(v) is not int or not low <= v <= high:
                raise ValueError(f"{key} must be a whole number between {low} and {high}.")
        if type(self.beep) is not bool:
            raise ValueError("Sound must be enabled or disabled.")


class Inventory:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        self.path = self.root/"devices.json"
        self.cameras = []
        self.preferences = Preferences()
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if raw.get("version") != 1:
                raise ValueError("Unsupported VMS inventory version.")
            self.preferences = Preferences(**raw["preferences"])
            self.preferences.validate()
            for record in raw["cameras"]:
                config = record["config"]
                config["source"] = protect(config.pop("source_protected"), decrypt=True)
                camera = Camera(**{**record,"config":Config(**config)})
                # Missing local videos do not prevent opening the inventory to repair their path.
                if not re.fullmatch(r"[a-f0-9]{32}",camera.id):
                    raise ValueError("Invalid camera identifier in inventory.")
                self.cameras.append(camera)
            if len(self.cameras) > 256 or len({c.id for c in self.cameras}) != len(self.cameras):
                raise ValueError("Invalid or duplicate camera records.")

    def save(self):
        self.preferences.validate()
        records = []
        for camera in self.cameras:
            record = asdict(camera)
            # Resolve an environment-based source before storing a protected private copy.
            record["config"]["source_protected"] = protect(camera.config.resolved_source())
            record["config"].pop("source")
            record["config"]["source_env"] = ""
            records.append(record)
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w",encoding="utf-8") as output:
            if os.name != "nt":
                os.chmod(temporary,0o600)
            json.dump({"version":1,"preferences":asdict(self.preferences),"cameras":records},output,indent=2)
            output.flush(); os.fsync(output.fileno())
        temporary.replace(self.path)

    def put(self, camera):
        camera.validate()
        if any(c.id != camera.id and c.name.casefold() == camera.name.casefold() for c in self.cameras):
            raise ValueError("Use a different camera name so alarm sources remain unambiguous.")
        before = self.cameras[:]
        self.cameras = [copy.deepcopy(camera) if c.id == camera.id else c for c in self.cameras]
        if not any(c.id == camera.id for c in before):
            if len(before) >= 256:
                raise ValueError("The device inventory limit is 256.")
            self.cameras.append(copy.deepcopy(camera))
        try:
            self.save()
        except Exception:
            self.cameras = before
            raise

    def remove(self, camera_id):
        before = self.cameras[:]
        self.cameras = [c for c in self.cameras if c.id != camera_id]
        try:
            self.save()
        except Exception:
            self.cameras = before
            raise

    def export_redacted(self, destination):
        # No configuration, source URL, username, password or query token is exported.
        Path(destination).write_text(json.dumps({"cameras":[{"name":c.name,"group":c.group,
            "analytics":c.analytics} for c in self.cameras]},indent=2),encoding="utf-8")
