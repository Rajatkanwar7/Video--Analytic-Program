# Reproduce the Windows EXE

The [Windows build workflow](../.github/workflows/windows-exe.yml) builds the real executable on Windows. PyInstaller is not a cross-compiler; the Linux development environment does not produce a Windows binary by renaming a script.

Use Windows with Python 3.11 64-bit and sufficient free disk space. The full AI runtime makes the installer substantially larger than the source ZIP.

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python.exe -m pip install -r requirements.txt PyInstaller==6.22.2
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe scripts/build_windows.py
dist\JailWatchVMS\JailWatchVMS.exe --self-test exe-validation.json
```

Inspect `exe-validation.json`; it must say `passed: true`. This check exercises packaged CPU inference, simultaneous synthetic video streams, actual FFmpeg recording/playback and the GUI. It is not a field detection benchmark.

Compile `packaging/JailWatchVMS.iss` using Inno Setup 6 to create the setup EXE. The workflow installs that setup into an isolated path and repeats the executable self-test before publishing a release. The portable distribution is the entire `dist/JailWatchVMS` folder, including `_internal`.

Every published build identifies its Git commit and package versions in `BUILD_INFO.json`. The workflow uses a commit-specific release tag and does not overwrite an earlier release. The normal source tests also run on Windows/Linux with Python 3.11 and 3.12.

Sources informing this build:

- [PyInstaller operating modes and OS-specific builds](https://pyinstaller.org/en/stable/operating-mode.html)
- [imageio-ffmpeg binary distribution](https://github.com/imageio/imageio-ffmpeg)
- [ONVIF Media service specification](https://www.onvif.org/specs/srv/media/ONVIF-Media-Service-Spec.pdf)
- [ONVIF Media2 service specification](https://www.onvif.org/specs/srv/media/ONVIF-Media2-Service-Spec.pdf)

Code-signing credentials were not supplied, so the installer is unsigned. Do not embed camera passwords or signing secrets in the repository or build scripts.
