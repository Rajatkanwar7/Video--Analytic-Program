# Configuration

The desktop writes `local/camera.json`. `config.example.json` lists all supported keys with empty source and zones. The supplied vendor JSON files describe another runtime and encrypted model references; the native runtime/weights were not supplied. They cannot be used directly as JailWatch configuration.

## Zones

Points are normalized `[x / image_width, y / image_height]`. Draw on a preview. Inside/outside describe the physical sides of the perimeter; there is no assumed left/right direction. Interiors cannot overlap. A small gap over the visible wall is allowed; tracking can bridge a brief gap.

A candidate must be visible outside before entering inside. A person's bottom-center box point determines zone occupancy. Ignore zones exclude their region from person/motion alerts. The UI edits one ignore polygon; JSON supports additional polygons. Avoid excluding the real object path.

`calibration_size` stores source dimensions. A changed aspect ratio stops monitoring. This cannot detect panning, zoom, rotation or crop with unchanged aspect ratio: manually recalibrate after any camera view change.

## Thresholds

| Field | Default | Meaning |
| --- | ---: | --- |
| `person_confidence` | 0.45 | Minimum person confidence. |
| `bird_confidence` | 0.20 | Minimum bird confidence; reducing it can suppress real objects incorrectly. |
| `semantic_interval_seconds` | 0.5 | Full-frame person inference interval in source seconds. Crossing verification uses exact event images. |
| `image_size` | 960 | Requested YOLO input size; the model may align this to its stride. |
| `processing_width` | 1280 | Maximum motion-processing width. Larger frames are downscaled. |
| `person_confirm_seconds` | 0.8 | Observed time inside before a moving person alerts. |
| `person_movement` | 0.018 | Required normalized person-center displacement. |
| `min_blob_area_ratio` | 0.000015 | Minimum contour area divided by image area. |
| `max_blob_area_ratio` | 0.004 | Maximum contour area divided by image area. |
| `min_track_points` | 4 | Minimum observed positions before a crossing candidate. |
| `min_throw_speed` | 0.12 | Normalized net displacement per source second, not meters/second. |
| `min_throw_displacement` | 0.04 | Minimum net travel from observed outside position. |
| `max_throw_seconds` | 2.5 | Maximum outside-to-inside interval. |
| `association_distance` | 0.065 | Maximum normalized distance to a track's predicted position. |
| `max_track_gap_seconds` | 0.30 | Maximum lifetime of an unseen motion track. |
| `reset_gap_seconds` | 0.75 | Larger gaps reset background, tracking and warmup. |
| `warmup_seconds` | 3 | Background initialization interval in source time. |
| `max_foreground_ratio` | 0.20 | Larger scene changes pause crossing detection and restart warmup. |
| `cooldown_seconds` | 8 | Per-type cooldown after a saved event. Separate same-type incidents within this interval may be suppressed. |

Normalized distance is `sqrt((dx / width)^2 + (dy / height)^2)`. These are image-space rules. Perspective affects apparent object speed/size; no universal speed value distinguishes birds from packages.

## Timing and capacity

Replay uses presentation times where available, with a frame-rate fallback. Warmup, speed and cooldown do not depend on how quickly the computer processes the file. Each run starts at source time zero; UTC event creation and source time are stored separately.

Live capture has a two-frame queue. Older queued frames are dropped and counted when motion analysis falls behind. AI runs in a separate worker for live cameras, with one replaceable person-inference request and at most four queued crossing candidates. The UI shows AI work pending; candidate overflow produces a warning because some crossings could not be reviewed. Person checks can be delayed while crossings are being verified. Frame loss/latency warnings also signal possible misses. Tracking is approximate: crowded or occluded objects can swap track IDs.

Each AI result retains its original frame and source time. Results from an earlier connection/reset are discarded. Stopping monitoring cancels pending AI reviews; wait for pending work to clear when possible before stopping. File replay uses synchronous AI so every candidate can be checked without a live-stream queue limit; replay may run slower than the original video.

Bird boxes from old frames are not applied to new frames. Crossing verification checks the exact event image and up to three recent contextual crops. Very small birds can remain unrecognized; overlap with a detected person can also suppress a real package.

## Storage

`data_dir` defaults to `data`, holding SQLite records and annotated JPEG snapshots. Retention defaults to 14 days or 5,000 events; pruning during monitoring removes older records and their snapshots. Acknowledged events follow the same retention policy. Archive evidence separately when needed. Original video/event clips are not recorded by JailWatch; use the NVR/VMS for original footage.

Paths are relative to the working directory; the supplied launchers start in the project folder. `source_env`, when set, takes precedence over `source`.
