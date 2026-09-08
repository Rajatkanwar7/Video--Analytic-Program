# Validation record and camera acceptance

This separates implemented behavior from measured detection accuracy. No camera-specific detection rate or newly trained model is claimed for version 1.1.

## Version 1.1 validation

The [GitHub Actions workflow](https://github.com/Rajatkanwar7/Video--Analytic-Program/actions/workflows/tests.yml) checks Python 3.11 and 3.12 on Windows and Linux. Inspect the result for the commit you download. It installs the base dependencies and runs synthetic video, tracking, evidence, data-checking, evaluation, Windows launcher and display-dependent desktop tests. Linux runners without a display skip the desktop tests; Windows runs them. These checks do not install GPU drivers, download model weights, or connect to a physical camera.

New coverage includes measured trajectory rendering and its toggle, expired paths, coordinate exports, the strict custom-object gate, bird evidence overriding a custom-object match, persisted session reports, an operator-only test alarm, frame extraction timing, reviewed negative labels, class/box validation, duplicate/group leakage and false alarms per hour. Training-command tests use a controlled model stub to verify arguments and output reports; they do not train a neural network.

The current development environment ran the dependency-light tests and syntax checks. Its OpenCV runtime was unavailable, so current video and Windows checks are delegated to the workflow above. No new RTSP field test, real-video AI benchmark, GPU training, desktop visual inspection or detector-accuracy measurement was completed for this update.

## Earlier prototype record

The following smoke checks were performed on the original prototype, before version 1.1. They used Linux with Python 3.12.13, NumPy 2.3.5, OpenCV headless 4.13.0.92 and Pillow 12.3.0. AI smoke processing used PyTorch 2.6.0 CPU, torchvision 0.21.0 CPU and Ultralytics 8.3.228 with official YOLO11n weights. Installation requirements include desktop OpenCV and Pillow 12.1.0; a fresh end-user Windows installation was not run locally.

### Original automated software tests

`python -m unittest discover -s tests -v` completed with **31 passing tests and 2 skipped desktop tests** in the local environment.

Covered behavior:

- Zone geometry, shared boundaries, overlapping/self-crossing zones, nonfinite coordinates and invalid settings.
- Outside-to-inside candidates, reverse motion, insufficient movement, missing tracks, cooldowns and one-to-one association.
- Person movement/time confirmation, reappearance and ignore regions.
- Persistent event records, acknowledgments, CSV export, retention and snapshot-path containment.
- Actual OpenCV synthetic video: candidate creation, annotated snapshot writing, recognized-bird suppression, person-blob suppression, scene-change/reset behavior and complete file replay.
- Event matching: duplicate alerts, missed events and overlapping annotation intervals.
- Live AI concurrency: motion continues while inference is blocked, delayed events use their original source time, candidate queues are bounded, old-connection results are discarded and model failures are visible.

The synthetic bird/person labels come from a controlled test detector. These tests verify filtering logic; they do **not** measure YOLO bird recognition. Desktop tests are skipped when no display is available. They are included in the Windows GitHub Actions matrix. Syntax compilation and whitespace checks also passed locally.

## Supplied recordings

The user stated that all three supplied recordings show throwing incidents. Exact event intervals, object bounding boxes, confirmed zone boundaries and bird-only negatives were not supplied. No verified precision, recall or bird false-alarm rate is claimed.

| Input | Check performed | Result |
| --- | --- | --- |
| H.265 TS, 1920×1080, approximately 15 fps | Sequential decoding plus a 150-frame AI/pipeline smoke run | 150 frames processed; no file-mode frame drops. |
| H.264 TS, 1280×720, approximately 25 fps | Sequential decoding plus a 150-frame AI/pipeline smoke run | 150 frames processed; no file-mode frame drops. |
| Supplied MP4 copy | OpenCV open and FFprobe check | Could not decode the current copy; FFprobe reported `moov atom not found`. A complete export is needed to test this file. |

Smoke runs used artificial left/right test zones to exercise the pipeline. Those polygons are not camera calibrations, and any resulting candidate was not verified as a real throwing incident. The files and extracted evidence were not included in the public repository.

The initial synchronous CPU smoke runs were slower than their source videos. Live mode consequently uses a separate AI worker so motion analysis does not wait for model inference; this separation was verified with controlled slow-detector tests. No real-camera throughput claim is made. Benchmark the actual computer and observe frame-loss, AI delay and queue-overflow warnings.

Not tested locally: a live RTSP camera, network reconnect against physical equipment, Windows installer execution, desktop visual appearance, GPU operation, long-duration service behavior, or trained-model accuracy on real throwing/bird events. The GUI includes display-dependent smoke tests; GitHub Actions results must be checked separately after publication.

## Validate a camera before operational use

1. Draw zones on that camera's fixed view and confirm the physical outside/inside direction. Include enough visible space to track a thrown item before it reaches the wall.
2. Review each positive clip and record all throw intervals in seconds from video start. A small object must be visible across multiple frames for this method to work.
3. Replay the complete video and compare every alert with the original footage. Record missed events and incorrect suppression near birds/people.
4. Replay bird-only and routine-activity video from the same camera across relevant light/weather conditions. Measure false alarms per hour.
5. Tune on a development set, then evaluate different held-out incidents. Do not reuse the same few positive clips as both training and final acceptance evidence.
6. Test sustained live processing, camera disconnection/reconnection, operator acknowledgments, disk-write failures and retention on the real server. Agree acceptable recall, false-alarm rate and delay with the responsible operator.

### Evaluate exported events

Export Alarm history to CSV and select one completed replay's `run_id`. Create a local annotation CSV with the header `start_seconds,end_seconds` and one row per target event. Windows must cover the desired alert time; annotate every target incident in the full run.

```bash
python scripts/evaluate_events.py --events local/alerts.csv --labels local/throw_intervals.csv --run-id RUN_ID
```

The script performs one-to-one matching and reports true positives, false positives, false negatives, precision, recall and F1. Add `--duration-seconds` with the fully reviewed video duration to calculate false alarms per hour, and `--output local/evaluation.json` to save the result. A repeated alert does not count as another successful detection. If a confirmed complete replay emitted no alerts, add `--allow-empty-run`; check the run ID carefully. This command does not establish bird-specific performance unless the evaluated videos are separately annotated as bird negatives.

## Reproduce the checks

```bash
python -m unittest discover -s tests -v
python -m compileall -q jailwatch scripts tests
python -m jailwatch doctor
python -m jailwatch probe --config local/camera.json --frames 100
python -m jailwatch run --config local/camera.json --max-frames 150
```

`probe` checks decoding only. `run` needs model weights and calibrated zones. A successful run without an alert is not evidence that the clip contains no incident.
