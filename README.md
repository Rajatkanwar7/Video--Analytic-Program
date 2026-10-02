# JailWatch VMS 2.1 — camera wall and perimeter alerts

**[Download the Windows installer or portable ZIP](https://github.com/Rajatkanwar7/Video--Analytic-Program/releases/latest)** · **[Camera setup guide](docs/VMS_QUICKSTART.md)** · **[What the analytics decide](docs/PERIMETER_ANALYTICS.md)**

Install `JailWatchVMS-Setup-2.1.0-x64.exe`, open JailWatch, create your administrator account, then sign in to the camera wall. The EXE includes Python, the CPU AI runtime, FFmpeg and generic YOLO11n weights. A Python launcher or BAT file is not required. The portable ZIP must be extracted completely, including its `_internal` directory.

This is a local Windows desktop VMS for a CCTV computer. GitHub distributes the application; it does not host camera feeds or start monitoring on your server.

## Operator workflow

1. **Sign in.** First launch creates an administrator; there is no default password. Administrators can add operator accounts in Settings.
2. **Add cameras.** Enter an IP and ONVIF login, choose an available stream, or enter a complete RTSP URL. Add one entry per NVR/DVR channel.
3. **See the camera wall.** Choose 1, 4, 9 or 16 views. Saved cameras reconnect after sign-in when Auto connect is enabled. Each tile shows connection, AI, frame-loss and recording status.
4. **Calibrate each camera.** Disconnect it, open AI zones and draw OUTSIDE and INSIDE. Optionally draw FENCE where a person's feet would appear near the fence, and IGNORE over irrelevant motion. Saving zones enables AI.
5. **Select direction and alert policy.** Edit → AI settings supports both directions, inward only or outward only. New and upgraded VMS cameras default to both. Reconnect and run controlled tests.
6. **Review evidence.** Alarms shows direction, review priority, snapshots and measured trajectories. Acknowledge events with a note or export CSV evidence.

## Included features

- Named administrator/operator sign-in, salted password hashes, persistent sign-in throttling and account disabling. No stored login sessions.
- Up to 16 concurrent live views; inventory of 256 devices with grid pages. AI defaults to two simultaneous cameras and can be configured up to eight after a hardware benchmark.
- ONVIF discovery and Media1/Media2 stream lookup, manual RTSP and recorded-video input.
- Suspected small-object crossings **outside → inside and inside → outside**, with independent directional cooldowns.
- Temporal visual bird/person checks on the event image and contextual crops. Recognized birds suppress throw notifications.
- Separate sustained **person near fence** warning. A person near the observed launch area raises a crossing's review priority; it does not establish involvement or a probability of guilt.
- Optional silent review of unclassified crossings; these remain in history without sound or an alarm banner. This option can also silence real throws.
- Measured object/person paths and arrows; source-time coordinates and trajectory exports. No fabricated landing predictions or physical speed estimates.
- Local stream-copy recording, playback, segment export, storage limits and stale-video indicators.
- Asynchronous live AI, bounded queues, visible overload/model failures and reconnect handling.
- Training-data checks, frame extraction, custom-model training and event-evaluation scripts.

## What this release establishes

JailWatch remains a **pilot application**. Software tests verify rule behavior, authentication, concurrent workers, recording and packaged operation. They do not establish detection rates on your actual cameras, support for every CCTV device, ONVIF certification, or superiority over another VMS.

Birds can glide and briefly follow smooth trajectories. An object path alone cannot reliably distinguish them from a thrown item. The generic model can miss tiny birds or tiny packages. No newly trained jail-specific weights or measured field improvement are included. See [validation](docs/VALIDATION.md) and [training](docs/TRAINING.md).

Keep the application running for viewing, recording and alerts. Signing out or closing it stops this desktop session. Use Windows lock to secure the workstation while monitoring continues. There is no background recording service or server failover in this release.

## Install from source

Use Python 3.11 or 3.12, 64-bit, with pip and Tcl/Tk. On Windows run `INSTALL_WINDOWS.bat`, then `START_WINDOWS.bat`. The launcher handles Python on PATH or in common installation locations; the Python launcher is optional. Linux: `bash install_linux.sh` on a graphical desktop.

```bash
python -m jailwatch vms
python -m unittest discover -s tests -v
python -m jailwatch doctor
```

The advanced legacy monitor remains available as `python -m jailwatch gui --config local/camera.json`; headless replay uses `python -m jailwatch run --config local/camera.json`. Those developer interfaces rely on Windows/Linux account permissions rather than VMS operator login. Legacy JSON defaults retain inward-only crossing unless configured otherwise.

## Guides

- [IP/RTSP setup, recording and compatibility](docs/VMS_QUICKSTART.md)
- [Accounts and local security boundary](docs/ACCOUNTS.md)
- [Bidirectional crossings, birds and fence context](docs/PERIMETER_ANALYTICS.md)
- [Live trials](docs/LIVE_TESTING.md), [training](docs/TRAINING.md), [validation](docs/VALIDATION.md)
- [Windows build](docs/WINDOWS_BUILD.md), [source installation](docs/INSTALLATION.md), [configuration](docs/CONFIGURATION.md)
- [Release notes](docs/RELEASE_NOTES_2.1.md)

Camera logins, recordings, real incident evidence and private vendor configurations are excluded from Git. Windows protects saved camera URLs with current-user DPAPI. Application code retains its MIT license; packages and model weights have their own [third-party terms](docs/THIRD_PARTY.md).
