"""Build a native Windows folder distribution. Run the executable self-test before release."""
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    if sys.platform!="win32":
        raise SystemExit("Build this executable on Windows or use the Windows build workflow.")
    os.chdir(ROOT)
    from scripts.make_icon import make_icon
    from jailwatch.model_setup import download_model,checksum
    make_icon("build_assets/jailwatch.ico")
    model=download_model("yolo11n.pt",ROOT/"models")
    args=[sys.executable,"-m","PyInstaller","--noconfirm","--clean","--onedir","--windowed",
          "--name","JailWatchVMS","--icon","build_assets/jailwatch.ico",
          "--collect-all","ultralytics","--collect-all","imageio_ffmpeg",
          "--collect-submodules","jailwatch","--copy-metadata","ultralytics",
          "--add-data",str(model)+os.pathsep+"models","--add-data","docs"+os.pathsep+"docs",
          "--add-data","LICENSE"+os.pathsep+".","vms_main.py"]
    subprocess.run(args,check=True)
    output=ROOT/"dist/JailWatchVMS"
    shutil.copy2(ROOT/"docs/VMS_QUICKSTART.md",output/"START_HERE.md")
    shutil.copy2(ROOT/"docs/THIRD_PARTY.md",output/"THIRD_PARTY.md")
    shutil.copytree(ROOT/"docs",output/"guides",dirs_exist_ok=True)
    packages={d.metadata["Name"]:d.version for d in importlib.metadata.distributions()}
    license_dir=output/"dependency_licenses"; license_dir.mkdir(exist_ok=True)
    for distribution in importlib.metadata.distributions():
        name=distribution.metadata["Name"].replace("/","_")
        for item in distribution.files or []:
            if ".dist-info/" in str(item) and any(word in str(item).lower() for word in ("license","copying","notice")):
                source=Path(distribution.locate_file(item))
                if source.is_file():
                    destination=license_dir/name/Path(item).name
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(source,destination)
    (output/"BUILD_INFO.json").write_text(json.dumps({"version":"2.0.0","commit":os.environ.get("GITHUB_SHA","local"),
        "python":sys.version,"model_sha256":checksum(model),"packages":packages},indent=2),encoding="utf-8")
    import imageio_ffmpeg
    license_text=subprocess.check_output([imageio_ffmpeg.get_ffmpeg_exe(),"-L"],stderr=subprocess.STDOUT).decode("utf-8",errors="replace")
    (license_dir/"FFMPEG_LICENSE.txt").write_text(license_text,encoding="utf-8")


if __name__=="__main__":
    main()
