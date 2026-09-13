"""Windows executable entry point and packaged-runtime verification."""
import multiprocessing
import os
import sys


def main():
    multiprocessing.freeze_support()
    # Windowed executables have no console; libraries may still write diagnostics.
    if sys.stdout is None:
        sys.stdout = open(os.devnull,"w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull,"w")
    os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL","-8")
    if "--self-test" in sys.argv:
        from jailwatch.vms.selftest import run
        destination = sys.argv[sys.argv.index("--self-test")+1]
        screenshot = sys.argv[sys.argv.index("--screenshot")+1] if "--screenshot" in sys.argv else None
        run(destination,screenshot)
        return
    try:
        from jailwatch.vms.ui import launch
        launch()
    except Exception as exc:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk(); root.withdraw()
        text = str(exc) if isinstance(exc,ValueError) else "Check that the application data folder is writable and the entire application is installed."
        messagebox.showerror("JailWatch VMS could not start",text,parent=root)
        root.destroy()
        raise SystemExit(1)


if __name__ == "__main__":
    main()
