# JailWatch 1.1 — CCTV perimeter monitor

A local desktop application for an RTSP IP camera or recorded video. It alerts on moving people in a configured inside zone and on small moving objects crossing from outside to inside. Recognized birds are filtered from crossing alerts.

**Status: runnable pilot application.** A crossing alert is a **suspected throw**, not proof of a thrown item. A bird that the model fails to recognize can still cause an alarm. Detection accuracy on the supplied throwing events has not been established. See [validation](docs/VALIDATION.md).

## Start on Windows

1. Install **Python 3.11, 64-bit**, with pip and Tcl/Tk enabled. Select **Add python.exe to PATH**. The Python launcher is optional; Python 3.12, 64-bit is also supported.
2. Download this repository using **Code → Download ZIP**, extract it, and run **INSTALL_WINDOWS.bat**. Internet is needed for packages and model weights.
3. Run **START_WINDOWS.bat**. Open **Camera setup**, enter the RTSP URL or choose a video, and save settings.
4. Click **Preview and draw zones**. Mark the outside and inside sides of the wall. Save zones, return to **Monitor**, and press **Start monitoring**.
5. Review red alerts in **Alarm history**. Open the snapshot, add a review note, and acknowledge the event.

The program runs on the **CCTV/server computer**. The camera supplies its RTSP stream. Publishing code on GitHub does not start monitoring on the server or install software in the camera.

## Features

- Desktop live view, persistent on-screen alarm banner, optional system bell.
- Live measured object/person trails with track IDs and direction arrows; saved path statistics and trajectory CSV export.
- Live-test evidence labels, a separate operator test-alarm button, and saved session/throughput reports.
- Optional custom `thrown_object` classification with an independent confidence threshold and a strict classification gate.
- RTSP timeouts, automatic reconnect, visible connection and performance status.
- Separate live AI worker, bounded review queue and visible overload warnings.
- MP4/TS/AVI/MKV replay using video timestamps; headless batch processing.
- Interactive normalized inside, outside and ignore zones; overlap and aspect-ratio checks.
- Person movement confirmation, directional crossing tracks, cooldowns, warmup and scene-change handling.
- Bird/person verification on the event image and recent contextual crops; missing AI stops monitoring visibly.
- Local SQLite history, annotated snapshots, review notes, acknowledgments and CSV export.
- Retention limits, local configuration, command-line diagnostics, automated logic/video tests and GitHub Actions configuration.
- Optional custom-model training and event-evaluation scripts.
- Frame extraction for human annotation, dataset/label checks, recording-group leakage checks, and held-out model evaluation.

One source is monitored per application process. Use separate configuration files and processes for multiple cameras. This is a standalone application; it is not an i2V/VMS plug-in.

## Commands

Run from the extracted project folder. On Windows, use `.venv\Scripts\python.exe` in place of `python` after installation.

```bash
python -m jailwatch gui
python -m jailwatch doctor
python -m jailwatch probe --config local/camera.json --frames 100
python -m jailwatch run --config local/camera.json
python -m unittest discover -s tests -v
```

Linux: install Python 3.11/3.12 with venv and Tk support, then run `bash install_linux.sh`. A graphical desktop is required for on-screen alarms. See [installation and deployment](docs/INSTALLATION.md).

## Detection approach and limits

YOLO detects people and birds. Background subtraction and short tracks find candidate small-object crossings. A candidate must start outside, end inside, move far and fast enough, and pass bird/person filtering. The system does not identify faces, determine intent, or infer an unseen throwing action.

Trees, insects, shadows, occlusion, compression and camera movement can cause errors. If the object is invisible, crosses between analyzed frames, or never appears in the outside zone, the event may be missed. Validate each fixed camera view with known throws and bird-only footage before relying on alerts. Live frame loss and processing delay are displayed; replay can run slower without dropping decoded frames.

The repository contains source and example settings. Camera credentials, recordings, original vendor configurations, model weights and event evidence are kept out of Git.

## Further setup

- [Installation, RTSP setup and troubleshooting](docs/INSTALLATION.md)
- [Live testing, trajectory display and session reports](docs/LIVE_TESTING.md)
- [GitHub download and update instructions](docs/GITHUB.md)
- [Configuration and threshold tuning](docs/CONFIGURATION.md)
- [What was tested and camera validation](docs/VALIDATION.md)
- [Custom model training](docs/TRAINING.md)

Version 1.1 adds software features and training tools. No new jail-specific model weights or measured improvement in field accuracy are included. The live paths show observations in the image, not predicted landing points or physical speed.

## Dependencies

This repository retains its existing MIT license for the application code. Third-party packages and model weights have their own terms. Ultralytics describes YOLO11 licensing on its [official model page](https://docs.ultralytics.com/models/yolo11/). Its [prediction API](https://docs.ultralytics.com/modes/predict/) and [threading guidance](https://docs.ultralytics.com/guides/yolo-thread-safe-inference/) inform the detector integration. Video capture uses [OpenCV](https://docs.opencv.org/4.13.0/d8/dfe/classcv_1_1VideoCapture.html).
