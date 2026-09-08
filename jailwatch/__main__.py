from __future__ import annotations

import argparse
import importlib.metadata
import json
import signal
import sys
import threading
import time
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description="JailWatch: local CCTV person and crossing alerts")
    commands = parser.add_subparsers(dest="command")
    gui = commands.add_parser("gui", help="Open the desktop monitor (default)")
    gui.add_argument("--config", default="local/camera.json")
    run = commands.add_parser("run", help="Run without a desktop; write alerts and JSON messages")
    run.add_argument("--config", default="local/camera.json")
    run.add_argument("--max-frames", type=int, default=0)
    run.add_argument("--realtime", action="store_true", help="Pace file replay to original timing")
    commands.add_parser("doctor", help="Check installed dependencies without opening a camera")
    download = commands.add_parser("download-model", help="Download official YOLO11 detection weights")
    download.add_argument("--name", choices=["yolo11n.pt", "yolo11s.pt"], default="yolo11n.pt")
    download.add_argument("--directory", default="models")
    probe = commands.add_parser("probe", help="Decode a source and report its timing; does not run AI")
    probe.add_argument("--config", default="local/camera.json")
    probe.add_argument("--frames", type=int, default=100)
    init = commands.add_parser("init-config", help="Write an empty example config (does not overwrite)")
    init.add_argument("--output", default="local/camera.json")
    args = parser.parse_args(argv)
    try:
        if args.command in (None, "gui"):
            from .ui import App
            App(getattr(args, "config", "local/camera.json")).mainloop()
        elif args.command == "doctor":
            result = {"python": sys.version.split()[0], "required_python": "3.11 or 3.12"}
            for name in ("numpy", "Pillow", "opencv-python", "opencv-python-headless", "torch", "torchvision", "ultralytics"):
                try:
                    result[name] = importlib.metadata.version(name)
                except importlib.metadata.PackageNotFoundError:
                    result[name] = "not installed"
            try:
                import tkinter
                result["tkinter"] = "available (desktop display not checked)"
            except ImportError:
                result["tkinter"] = "missing"
            print(json.dumps(result, indent=2))
        elif args.command == "init-config":
            from .config import Config, save_config
            if Path(args.output).exists():
                raise ValueError("Config already exists; use Camera setup to edit it.")
            save_config(Config(), args.output)
            print("Created empty configuration. Set source and draw zones in the desktop app.")
        elif args.command == "download-model":
            from .model_setup import checksum, download_model
            path = download_model(args.name, Path(args.directory))
            print(json.dumps({"model": str(path), "sha256": checksum(path)}))
        elif args.command == "probe":
            from .capture import VideoSource
            from .config import load_config
            if not 1 <= args.frames <= 100000:
                raise ValueError("Frames must be between 1 and 100000.")
            config = load_config(args.config)
            reader = VideoSource(config.resolved_source(), config).open()
            count, first, last = 0, None, None
            deadline = time.monotonic() + 20
            try:
                while count < args.frames:
                    frame = reader.read()
                    if frame is None:
                        if reader.ended or time.monotonic() > deadline:
                            break
                        continue
                    deadline = time.monotonic() + 20
                    first = frame.time if first is None else first
                    last = frame.time
                    shape = frame.image.shape
                    count += 1
                if not count:
                    raise ValueError("No frames decoded. Check source, login, network and codec.")
                print(json.dumps({"decoded_frames": count, "width": shape[1], "height": shape[0],
                    "reported_fps": reader.fps, "source_seconds": round(last - first, 4),
                    "ended": reader.ended, "ai_tested": False}, indent=2))
            finally:
                reader.close()
        elif args.command == "run":
            from .config import load_config
            from .events import EventStore
            from .pipeline import run_monitor
            if args.max_frames < 0:
                raise ValueError("max-frames must be zero (all frames) or positive.")
            config = load_config(args.config)
            stop = threading.Event()
            signal.signal(signal.SIGINT, lambda *_: stop.set())
            if hasattr(signal, "SIGTERM"):
                signal.signal(signal.SIGTERM, lambda *_: stop.set())
            last_status = [""]
            last_health = [0.0]
            def callback(message):
                if message["type"] == "frame":
                    now = time.monotonic()
                    if now - last_health[0] >= 5:
                        print(json.dumps({"type": "health", **{k: v for k, v in message.items()
                            if k not in {"type", "image"}}}), flush=True)
                        last_health[0] = now
                    return
                if message["type"] == "status":
                    if message["text"] == last_status[0]:
                        return
                    last_status[0] = message["text"]
                print(json.dumps(message), flush=True)
            summary = run_monitor(config, EventStore(config.data_dir), stop, callback,
                                  max_frames=args.max_frames, realtime=args.realtime)
            print(json.dumps({"type": "summary", **summary}), flush=True)
        return 0
    except KeyboardInterrupt:
        return 130
    except ValueError as exc:
        print(f"JailWatch: {exc}", file=sys.stderr)
    except ImportError:
        print("JailWatch: dependency missing. Run INSTALL_WINDOWS.bat or install requirements.txt.", file=sys.stderr)
    except Exception as exc:
        # Avoid dumping source URLs/credentials from third-party error text.
        print(f"JailWatch: {type(exc).__name__}. Check the model, source, display and writable data folder.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
