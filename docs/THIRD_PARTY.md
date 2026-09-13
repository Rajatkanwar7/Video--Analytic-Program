JailWatch VMS — application and dependency notices
================================================

The application source is published at:
https://github.com/Rajatkanwar7/Video--Analytic-Program

The application's existing MIT license remains in LICENSE. Included dependencies and model weights have their own licenses. The Windows distribution includes dependency license/notice files in dependency_licenses and exact package versions and the bundled model SHA-256 in BUILD_INFO.json.

Ultralytics and the included YOLO11n weights are supplied under their applicable Ultralytics terms, including the AGPL-3.0 route. Their terms are not replaced by the application's MIT license. The public application source and Windows build instructions are in this repository.
Source and terms: https://github.com/ultralytics/ultralytics/tree/v8.3.228
Model source: https://github.com/ultralytics/assets/releases/tag/v8.3.0
Licensing: https://www.ultralytics.com/license

PyTorch / torchvision source and notices:
https://github.com/pytorch/pytorch/tree/v2.6.0
https://github.com/pytorch/vision/tree/v0.21.0

OpenCV source:
https://github.com/opencv/opencv/tree/4.13.0
Wheel build sources and third-party notices:
https://github.com/opencv/opencv-python

imageio-ffmpeg 0.6.0 includes a platform-specific FFmpeg binary. The FFmpeg binary's own license/build banner is recorded in dependency_licenses/FFMPEG_LICENSE.txt; do not assume the wrapper's BSD license covers that binary. Preserve FFmpeg's applicable license and corresponding-source obligations when redistributing a build.
Wrapper and binary-build references: https://github.com/imageio/imageio-ffmpeg/tree/v0.6.0
FFmpeg source: https://ffmpeg.org/download.html#get-sources

Other runtime components include Python, NumPy, Pillow, PyYAML, requests, urllib3, certifi, charset-normalizer, idna, defusedxml, SciPy, Matplotlib and Ultralytics' declared dependencies. Their installed versions are recorded in BUILD_INFO.json, with available distribution license files copied into dependency_licenses.

PyInstaller packages the runtime. Inno Setup creates the Windows installer. Their terms and source are available at:
https://pyinstaller.org/en/stable/license.html
https://github.com/jrsoftware/issrc

This release is a local VMS pilot. It does not claim ONVIF certification, universal camera compatibility or a measured detection accuracy. Review and validate each camera on your actual server before operational use.
