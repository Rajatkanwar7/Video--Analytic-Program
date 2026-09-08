# Train and measure a camera-specific model

The supplied YOLO11 weights are generic. This release improves the application and its training tools; no new jail-specific weights or measured accuracy claim are included. Three unlabelled throw videos cannot establish bird rejection or general reliability. A world-leading claim would need an independently evaluated, representative benchmark.

The practical goal is to detect more of your real incidents while keeping false alarms and live processing delay within agreed limits. Keep the original model as a baseline and promote a new model only after measuring those outcomes on footage it has never seen.

## 1. Collect and label footage

Collect multiple independent throwing incidents and substantial routine footage from each camera view: birds at different distances, people, waving vegetation, shadows, insects, rain, day/night changes and compression artefacts. Include the kinds of small packets and objects actually visible at the site. Mark every visible target; do not draw imagined boxes when the object is occluded or unresolvable.

Use these exact classes throughout training and the application:

| ID | Class | Label |
| --- | --- | --- |
| 0 | person | Visible people, including people who are not throwing. |
| 1 | bird | Visible birds, including small/distant examples. |
| 2 | thrown_object | The visible airborne item in a known throw event. The trajectory rule still determines outside-to-inside crossing. |

Label boxes using an annotation tool that exports the [Ultralytics detection format](https://docs.ultralytics.com/datasets/detect/). Each image needs a corresponding `.txt` file containing `class x_center y_center width height`, normalized to 0–1. For a reviewed image with none of these objects, create an empty label file. Missing labels are treated as incomplete annotation by the checker, not as automatic negatives.

To extract frames, open the project folder in File Explorer, type `cmd` in its address bar and press Enter. Then use the installed project Python:

```bat
.venv\Scripts\python.exe scripts/extract_frames.py --video "C:\Clips\throw.mp4" --group tower1_day1 --fps 25 --start 10 --end 15
```

Replace the path and times with the verified throw interval. Use the source frame rate around the throw so short events are retained; a lower sampling rate can be useful for long routine footage. The extractor writes original-resolution JPEGs and a time/group manifest under `local/annotation_frames/tower1_day1`. It never creates labels or uploads footage. Its default limit is 3,000 frames; it reports when that limit is reached. Existing output groups are not overwritten.

## 2. Separate training, validation and test data

Assign each recording/day/incident group to a single split. Never randomly distribute adjacent frames of one throw among all three splits. For testing performance on unseen cameras, also hold out whole camera views. A starting allocation such as 70/15/15 is a planning choice; independent coverage of conditions and events matters more than the exact percentages.

Keep complete test videos aside for event-level evaluation. Use this directory structure:

| Split | Images | Matching labels |
| --- | --- | --- |
| Training | `datasets/perimeter/images/train/` | `datasets/perimeter/labels/train/` |
| Validation | `datasets/perimeter/images/val/` | `datasets/perimeter/labels/val/` |
| Test | `datasets/perimeter/images/test/` | `datasets/perimeter/labels/test/` |

Copy `examples/dataset.example.yaml` to `local/dataset.yaml`. Set `path` to `../datasets/perimeter`, or your absolute dataset folder using forward slashes. Keep the class IDs above. Subfolders are allowed when the image/label structures match.

Also prepare `local/groups.csv` with columns `image,group_id`. Image paths are relative to the dataset root, for example `images/train/tower1_day1_00000251.jpg`. Give every image a group and keep one group in one split. The extractor's manifest supplies group IDs; update image paths after placing files in the split directories.

## 3. Check the dataset before training

```bat
.venv\Scripts\python.exe scripts/train_model.py --data local/dataset.yaml --groups local/groups.csv --check-data
```

This checks image readability, missing labels, normalized box bounds, class names/counts, exact duplicate files across splits and recording-group leakage. It counts confirmed negatives and boxes with a side smaller than 8 pixels. That size count is a review aid, not an accuracy prediction. All three classes must be represented in train and validation.

Without a group manifest the checker can find exact duplicate files, but it cannot prove that related frames are separated. It reports that limitation. It cannot tell whether a human label is semantically correct; manually audit difficult samples and all rare classes.

## 4. Train a candidate

```bat
.venv\Scripts\python.exe scripts/train_model.py --data local/dataset.yaml --groups local/groups.csv --weights models/yolo11n.pt --device 0 --epochs 100 --batch 4 --image-size 1280 --name candidate1
```

`--device 0` requires a configured NVIDIA GPU. Use `--device cpu` if one is unavailable; CPU training can be slow. If GPU memory is insufficient, reduce `--batch` first and then evaluate an image-size tradeoff. This application supports AI sizes up to 1920. The larger YOLO11s model is an optional benchmark candidate, not a guaranteed improvement; download it with `python -m jailwatch download-model --name yolo11s.pt` using the same project Python.

The script uses a recorded seed, deterministic training settings, validation-based early stopping, bounded augmentation and a fresh run directory. It saves the resolved local dataset configuration and check report. See [Ultralytics training settings](https://docs.ultralytics.com/modes/train/) for the meaning of these arguments. These defaults are a starting recipe, not optimized settings for your cameras.

The best checkpoint is normally `training_runs/candidate1/fit/weights/best.pt`. Keep the entire run directory and its validation results. The script does not automatically replace your active model.

## 5. Evaluate images and complete videos

First inspect image results on the held-out test set:

```bat
.venv\Scripts\python.exe scripts/train_model.py --mode test --data local/dataset.yaml --groups local/groups.csv --weights training_runs/candidate1/fit/weights/best.pt --device 0 --name candidate1_test
```

This saves bounding-box metrics and plots. Good box-level mAP does not prove that full throwing events are detected or that bird false alarms are acceptable.

Next select `best.pt` in **Camera setup**, save, and replay the complete held-out videos using the same calibrated zones as the baseline. Export Alarm history. In `local/throw_intervals.csv`, list every target event's acceptable detection interval with columns `start_seconds,end_seconds`. Use video-relative times from the run, not the camera's clock overlay.

```bat
.venv\Scripts\python.exe scripts/evaluate_events.py --events local/alerts.csv --labels local/throw_intervals.csv --run-id YOUR_RUN_ID --duration-seconds 1800 --output local/candidate1_metrics.json
```

Replace the run ID and duration with the actual fully reviewed run. If a confirmed complete run contains zero alerts, explicitly add `--allow-empty-run`. A wrong run ID must not be mistaken for perfect bird rejection. For bird-only footage use a header-only interval CSV, and manually confirm that no throws occurred. Evaluate that footage separately to measure bird-related false alarms.

The evaluator reports true/false positives, missed events, precision, recall, F1 and false alarms per hour. Duplicate alerts are counted as false positives. It does not infer ground truth or measure camera-to-alarm latency. Review alert timing against the original recordings separately.

## 6. Use the measured result

Compare both models on the same unseen videos, zone settings and hardware. Record recall, false alarms/hour, small-object misses, bird errors and live frame/AI queue loss for each lighting condition. Keep difficult errors in a development set, add fresh labels and retrain; keep the final test set untouched until the candidate is ready.

With the custom model selected, **Require trained object class** can be enabled for an additional classification requirement. This may reduce unknown-motion alarms while increasing missed unfamiliar objects. Measure both settings before choosing. Generic COCO weights cannot enable this option. Bird/person evidence in a sampled frame still suppresses a crossing even when another frame matches the custom object class.

Use **Live test mode** for controlled field trials before relying on a candidate operationally. More training cannot recover an object that the camera never resolved or frames the computer dropped. See [live testing](LIVE_TESTING.md).
