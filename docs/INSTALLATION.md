# Installation and deployment

## What runs where

The IP camera provides an RTSP stream on the CCTV network. JailWatch runs on a Windows or Linux computer that can reach that stream. Inference and evidence storage happen on that computer; the desktop operator sees the alarm screen.

GitHub distributes the source. GitHub Pages cannot run this desktop application or access a private camera network. No camera or server has been remotely accessed as part of this repository publication.

## Windows

1. Install Python 3.11 **64-bit** from [python.org](https://www.python.org/downloads/), including the Python launcher and Tcl/Tk.
2. Extract the repository into a writable folder such as `C:\JailWatch`. Use a local drive for the SQLite database.
3. Run `INSTALL_WINDOWS.bat`. It creates a virtual environment, installs CPU dependencies, downloads YOLO11n and runs software tests. It stops on errors.
4. Open `START_WINDOWS.bat`. In **Camera setup**, enter a name and the full RTSP URL supplied by your camera/NVR administrator, or select a local video.
5. Save settings, click **Preview and draw zones**, draw outside and inside polygons, and save.
6. Start monitoring and check the image, zone direction, processing rate and alarm history.

Installation needs internet. Monitoring uses the camera network and local weights. For an offline computer, prepare compatible package wheels and official weights on another computer and transfer them through your normal approved process.

### RTSP source

The path depends on camera/NVR model and channel. A structural example is:

```text
rtsp://USERNAME:PASSWORD@CAMERA_IP:554/VENDOR_STREAM_PATH
```

Use the real vendor path, not the literal example. URL-encode reserved characters in credentials. Test the same URL in your existing video player if preview fails.

The UI masks the source field, but the local JSON can contain the camera login in plaintext. Protect it with the computer's account/folder permissions and do not commit or share it. Advanced setups can leave `source` empty and set `source_env` to a variable such as `JAILWATCH_RTSP_URL`; the application reads the actual URL from that environment variable.

### After reboot

To open the application at operator login, place a shortcut to `START_WINDOWS.bat` in the Windows Startup folder (`Win+R`, then `shell:startup`). The operator checks the view and starts monitoring. On-screen alarms require an active desktop session.

For unattended processing, run the headless command with your scheduler/service manager. It writes local evidence and JSON events but has no on-screen alarm:

```text
.venv\Scripts\python.exe -m jailwatch run --config local/camera.json
```

### GPU

The installer uses CPU packages. For a supported NVIDIA GPU, install a compatible PyTorch/torchvision/CUDA combination using the [official PyTorch selector](https://pytorch.org/get-started/locally/) and set **Device** to `0`. GPU installation/performance has not been tested here. Benchmark your actual stream before deciding how many cameras one computer can handle.

## Linux

Install Python 3.11 or 3.12 with venv and Tk support. OpenCV can also require system `libGL` and `libglib` libraries. Then:

```bash
bash install_linux.sh
.venv/bin/python -m jailwatch gui
```

Use a graphical desktop for the GUI. Without a display:

```bash
.venv/bin/python -m jailwatch run --config local/camera.json
```

## Multiple cameras

Use one process per source and a separate configuration per camera:

```bash
python -m jailwatch gui --config local/tower1.json
python -m jailwatch gui --config local/tower2.json
```

Give each a distinct camera name and its own zones. Processes can share a local event database or use separate `data_dir` values. Changing a source in the setup form clears old zones so the new view is checked.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Python missing | Install 64-bit Python 3.11 with its launcher; rerun installation. |
| Missing model | Click Download model, or select trusted local detection weights with `person` and `bird` classes. |
| No preview | Verify IP connectivity, credentials, RTSP path/channel, camera session limits and codec. |
| Disconnected | Check camera/network power and connectivity. The application retries and resets tracks after reconnection. |
| Low processed FPS/frame loss | Reduce competing workloads, benchmark a smaller AI size, or configure a GPU. Fast objects can be missed while overloaded. |
| Too many alarms | Review snapshots, check direction, exclude vegetation and tune thresholds using labeled clips. |
| Missed throw | Check object visibility, observed outside-to-inside path, size thresholds, frame loss and false suppression near people. |
| Aspect-ratio warning | Redraw zones. Also recalibrate after camera movement/zoom/crop even when aspect ratio is unchanged. |
| No Linux GUI | Install Tk and use a graphical desktop. Headless mode has no alarm window. |
| Evidence write failure | Check free disk space and folder access. Monitoring stops if evidence cannot be saved. |
| File ends early | Decoder failure can look like end-of-file. Re-export from the NVR or remux with FFmpeg if possible. |

## Updates

Stop the application before replacing source files. Keep local configuration, model and evidence folders. Rerun dependency installation if requirements changed, run tests and replay acceptance clips before restarting monitoring. Git can restore a previous source commit; separately back up local configuration/evidence when needed.
