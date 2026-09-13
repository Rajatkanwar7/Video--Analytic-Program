JailWatch VMS adds multi-camera viewing, ONVIF stream lookup, local recording/playback and central alarm review to the existing perimeter analytics.

Download **JailWatchVMS-Setup-2.0.0-x64.exe** for the normal Windows installation. Python, video/CPU-AI dependencies and the generic YOLO11n model are included. A portable ZIP is also available; extract its entire folder before opening JailWatchVMS.exe.

Features include 1/4/9/16 camera layouts, per-camera connection and recording status, ONVIF discovery and Media1/Media2 stream lookup, manual RTSP/video input, stream-copy MKV recordings, playback and export, recording retention, Windows account-protected saved logins, and person/suspected-throw alerts with trajectory evidence.

The build runs source tests and a self-test of the actual packaged EXE, including CPU YOLO inference on a synthetic frame, four local video sources, FFmpeg recording, playback decoding and the desktop alarm screen. It then tests the installed EXE. Validation JSON files and checksums are attached.

This is an unsigned pilot build for 64-bit Windows. Physical cameras, vendor interoperability, real-camera throughput and detection accuracy have not been certified. Supported RTSP/ONVIF modes are required; cloud-only/proprietary devices are not universally supported. PTZ, audio talkback, NVR-history search and multi-user server/failover features are not included.

Read the VMS quick-start guide in the application folder or repository before configuring cameras. The installer does not connect to, change or replace your existing NVR automatically.
