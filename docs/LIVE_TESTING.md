# Live camera testing and object trajectories

JailWatch 1.1 runs on the CCTV computer and analyses the camera's RTSP stream. It can raise on-screen alerts while the camera is live. GitHub holds the program; it does not connect to your camera or run your monitoring session.

## First live test

1. Extract the updated ZIP into a new folder. Run `INSTALL_WINDOWS.bat`, then `START_WINDOWS.bat`.
2. In **Camera setup**, choose your model and enter the camera's full RTSP URL. Use your real camera/NVR stream path. Keep the password private.
3. Click **Preview and draw zones**. Mark OUTSIDE and INSIDE on the correct sides of the wall. Keep vegetation outside the required corridor in ignore zones. Save the zones.
4. Return to **Monitor**. Enable **Show trajectories** and **Live test mode**. Leave **Require trained object class** off when using the supplied generic YOLO11 model.
5. Press **Test alarm** once. Check the on-screen banner, sound and Alarm history. Its event type is `system_test`: no object was detected, and this does not test model accuracy.
6. Press **Start monitoring**. Wait until background warmup finishes. Check that frames update, the view matches the drawn zones, and processing/AI warnings remain clear.
7. Carry out controlled trials with the responsible site team: a person moving in the inside zone; a visible test object crossing from outside to inside; reverse-direction movement; and routine activity/birds. Record the original camera video and each trial time, including missed events.
8. Review **Alarm history** and each snapshot. Add notes such as confirmed test throw, bird false alarm or other motion. Acknowledge the event after review.
9. Select a detection and click **Export selected trajectories** to save its measured path. Press **Stop**, then **Export session report** for counts, frame loss, processing delay and AI queue warnings.

The test-mode checkbox marks actual detection evidence as a test; it still runs the normal detection pipeline and sounds alerts. The separate Test alarm button creates only a clearly labeled operator test. Neither option trains the model.

## Reading the trajectory

| Display/data | Meaning |
| --- | --- |
| Orange motion path and ID | Successive measured locations of a motion candidate in the crossing corridor. It may be an unknown object, bird, foliage or noise until reviewed. |
| Green person path | Person detections associated over time. |
| Blue bird path, when classified | A tracked candidate identified as a bird during event verification; its throw alert is suppressed. |
| Arrow | Direction between the most recent distinct measured locations. |
| Snapshot path | The observations associated with that saved event, preserved even after the live trail expires. |
| Exported coordinates | Normalized x/y and source time; pixel coordinates refer to the processing/snapshot dimensions recorded with that event. |

Paths are two-dimensional image measurements. The program does not estimate a landing point, distance in metres, speed in km/h, or the unseen part of a throw. A curved trail by itself cannot distinguish a bird from a thrown object. Track IDs are local to a monitoring run, not persistent identities. Motion and person tracks have separate ID namespaces.

Live paths expire when the track is missing or its display history is too old. They reset after a reconnection or a large scene change. AI review can arrive after an object has left the view; use the saved event snapshot to review the original path.

Advanced local configuration: `trajectory_seconds` controls the visible history, default 2 seconds. `processing_width` sets the motion-analysis resolution. Increasing resolution may preserve small objects but also increases processing load. Check frame loss on the actual computer before accepting a setting.

## What the session report proves

Reports are also saved automatically in the `runs` subfolder of the configured data folder (`data/runs/` by default). They include the run ID, camera name, source type, test flag, alert counts, observed frames/time, dropped frames, frame/connection gaps, suppressed candidates, processing delay, queued AI at shutdown and queue overflows. They contain no RTSP URL or camera password.

These are software/throughput measurements. Camera-to-screen network delay is not fully measured. Zero alerts does not mean zero incidents. A pending AI count at shutdown means some results may not have been delivered. No alert is generated for a packet that was invisible, dropped between analysed frames, outside the calibrated corridor, or rejected incorrectly by the classifier.

## Five-minute command-line trial

Open Command Prompt in the extracted project folder:

```bat
.venv\Scripts\python.exe -m jailwatch run --config local/camera.json --test-mode --duration 300
```

This runs the same detection pipeline without the desktop alarm screen and stops after approximately five minutes of processing following model loading. The normal desktop mode is the right choice for on-screen alarms. Ctrl+C stops the command-line run. Use the resulting run ID when evaluating exported events.

## Acceptance record

For each fixed camera view, compare the original full recording against every alert. Keep all trials, including no-alert trials. Record total real test throws, detected throws, missed throws, bird false alarms, other false alarms, and fully reviewed video duration. Compare baseline and custom weights on the same held-out recordings and hardware. Check day/night conditions, occlusion, weather, frame loss and reconnect behaviour separately. Agree operational targets with the site team before relying on the alerts.

See [training and evaluation](TRAINING.md) for preparing labels and measuring recall, precision, F1 and false alarms per hour.
