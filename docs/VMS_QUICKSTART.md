# JailWatch VMS 2.0 — start here

JailWatch VMS runs on your Windows CCTV computer. It combines a camera grid, device setup, local recording/playback and the project's person/trajectory/crossing analytics. It is a pilot VMS; camera interoperability and detection accuracy must be checked on your equipment.

## Install the EXE

1. Open this project's [latest Windows release](https://github.com/Rajatkanwar7/Video--Analytic-Program/releases/latest).
2. Download `JailWatchVMS-Setup-2.0.1-x64.exe` and run the installer. Python is included; no Python launcher or BAT file is needed.
3. Open **JailWatch VMS** from the desktop or Start menu. Installation is for your current Windows account and does not require administrator privileges.

Alternatively download `JailWatchVMS-2.0.1-Windows-x64.zip`, extract the entire folder, and open `JailWatchVMS.exe`. Keep its `_internal` folder beside it. Copying the EXE alone will not work. The setup EXE installs that complete application for you.

The current installer is unsigned. If Windows or your organisation blocks it, use your IT team's normal application review process. Release checksums are provided in `SHA256SUMS.txt`.

## Connect a camera by IP

1. Connect the computer to the CCTV network. It must be able to reach the camera or recorder.
2. Click **Add device**. Enter a unique camera name and a site/group.
3. In **IP / ONVIF**, enter the IP, for example `192.168.1.10`. If ONVIF uses a different HTTP port, enter `192.168.1.10:8080`. A full ONVIF device-service URL is also accepted.
4. Enter the device's ONVIF username and password. Some cameras require ONVIF to be enabled and a separate ONVIF account to be created in the camera settings.
5. Click **Get available streams**. Choose the required camera/channel profile, then **Save camera**.
6. On **Live view**, select the camera and click **Connect**.

**Devices → Discover ONVIF** can find responding devices on the local network. On a computer with several adapters, enter the computer's CCTV-network IPv4 address in the discovery dialog. Discovery generally does not cross routers/VLANs; enter the IP manually if it finds nothing.

For cameras without supported ONVIF services, use the **RTSP / video file** tab. Enter a complete RTSP URL, or use the IP, port, username, password and vendor stream-path fields to build one. The builder encodes special characters in credentials. The stream path is device-specific; do not guess it from the brand alone.

For an NVR/DVR, add one entry per channel/profile. A camera on an NVR's private PoE network may be reachable only through that recorder's RTSP channel. Analogue cameras need a DVR or encoder that exposes a compatible network stream.

## Use the camera grid

Keep the application open while recording or monitoring. You can minimize it. Closing it, signing out, shutting down or restarting the computer stops recording and detection alerts. After reopening it, reconnect the required cameras and restart recording. This release is a desktop VMS, not an unattended Windows recording service.

- Choose 1, 4, 9 or 16 views. Click a tile to select it; double-click to enlarge it. Use Previous/Next for additional saved devices and F11 for full screen.
- The window starts within your screen; controls wrap on smaller displays and longer settings forms scroll.
- **Connect** and **Disconnect** affect the selected camera. **Devices → Connect all** respects the configured live/AI limits and reports cameras that could not start.
- A green tile indicator means recent frames are arriving. Stale images display **NO CURRENT VIDEO**. Check Devices for connection, AI and recording status.
- The inventory can hold up to 256 entries. At most 16 streams can be open in this process. These are software limits, not a promise that a particular computer can process that many streams at full resolution.

## Enable this project's AI alerts

New devices begin in **VIEW ONLY** mode. This lets you verify the video connection before calibrating detection.

1. Disconnect the selected camera.
2. Click **AI zones**. Draw outside and inside polygons on the real camera view; optionally mask irrelevant vegetation. Saving zones enables AI for that camera.
3. In **Edit → AI settings**, choose your weights and thresholds available there. The Windows package includes the generic YOLO11n model and CPU inference. Keep **Require custom thrown_object class** off with this model. Enable test-mode labels for controlled trials.
4. Connect the camera again. Check the AI status on the tile and in Devices. Warmup, overload and model failures are visible. A failed AI worker leaves the video view available but cannot generate detection alerts.
5. Review alerts and snapshots in **Alarms**, add an acknowledgment note and export events/trajectories if needed.

AI concurrency defaults to two cameras to avoid starting many large inference workers accidentally. Increase it only after measuring frame loss, delay and CPU/RAM use on the server. The packaged build is CPU-based. GPU deployment requires a source installation with a suitable PyTorch/CUDA runtime; entering `0` in this CPU package does not install GPU support.

**Test alarm** creates a clearly labeled system test and sounds the system bell. It does not simulate an AI detection. Paths are measured image positions, not predicted landing points or physical speeds. The existing [live-test guide](LIVE_TESTING.md) and [training guide](TRAINING.md) explain field validation; their single-camera UI labels refer to the earlier monitor.

## Record and play video

1. Connect the camera, select it, and click **Record**. Wait for the tile to display **REC**. A pending/failed recording indicator means recording is not confirmed.
2. Recording uses another RTSP connection and copies encoded video, plus supported audio when present, into MKV segments. It does not burn AI overlays into the original stream. The camera/NVR must allow enough concurrent stream connections.
3. Open **Recordings**, choose a camera and optional UTC date, then Search. Only completed segments are listed. Click **Stop REC** to finalize the current segment immediately; normal segments default to roughly five minutes and may end at the next keyframe.
4. Select a segment and click **Play**, or double-click it. Playback has pause, seeking and speed controls. The built-in player shows video; exported MKV files retain recorded audio for an external player.
5. **Export selected MKV** copies the segment outside managed storage. Saved AI overlays remain in alert snapshots, and trajectory CSVs can be exported separately.

Recording continues separately from AI inference. Network loss, stream limits, unsupported codecs, a full disk or a stopped computer can still interrupt it. Reconnection creates a new recording session; missing periods cannot be recovered by the VMS. Recorder start times shown in the list are approximate computer-clock times, not synchronized forensic timestamps. Seeking may align to codec keyframes.

## Storage and updates

Data defaults to `%LOCALAPPDATA%\JailWatchVMS`. Settings provides **Open data folder**. The folder contains device settings, event evidence, recording segments and session reports. It is separate from the installed program, so application upgrades do not intentionally remove it. Uninstalling the program leaves this data for you to retain or delete.

Windows protects persisted camera source URLs using current-user DPAPI. Copying the inventory to another Windows account/computer does not transfer usable credentials; re-enter the camera logins there. Source-based Linux deployments use private file permissions, not DPAPI encryption. Device-name export omits source URLs and credentials.

Recording retention defaults to seven days or 100 GB of completed segments, deleting oldest completed recordings when either limit is exceeded. Active segments temporarily add to that limit. Open playback segments are held while the player is using them. Recording pauses with less than 1 GB free; other files on the disk can also use space. Export evidence that needs longer retention. Incomplete files after a crash are not automatically presented as verified recordings.

Stop all cameras before changing storage/processing limits or updating the program. Earlier single-camera configuration can be imported through **Devices → Import earlier JailWatch camera**. Original recordings, vendor configurations, credentials and real incident evidence are not shipped in the public download.

## Compatibility boundaries

| Device/function | This release |
| --- | --- |
| IP camera with a reachable RTSP stream | Manual stream connection; codec and authentication must work with the bundled decoder. |
| ONVIF Media1 / Media2 device | Discovery and authenticated profile/RTSP-URI lookup implemented; verify against the actual model/firmware. |
| NVR/DVR exposing RTSP channels | Add each required channel as a separate device entry. |
| Analogue-only camera | Requires a compatible DVR/encoder. |
| Cloud/P2P-only camera or proprietary encrypted stream | Requires a supported local RTSP/ONVIF mode or vendor integration; not automatically supported. |
| Recordings already stored inside an NVR | Not searched by this release; use the vendor VMS/NVR for historical playback. |
| PTZ, talkback, relay control, mobile/cloud access, operator roles/failover | Not implemented in this release. |

This client has not completed ONVIF conformance certification. Supporting selected ONVIF operations does not imply complete Profile S/T/G conformance or universal device compatibility.
