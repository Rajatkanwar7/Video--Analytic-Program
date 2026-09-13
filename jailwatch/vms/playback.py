from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk


class Playback(tk.Toplevel):
    def __init__(self, parent, store, row):
        super().__init__(parent)
        self.title("Playback | "+row["camera"])
        self.geometry("1060x710")
        self.configure(bg="#101722")
        self.store,self.row = store,row
        self.path = store.safe_path(row["path"])
        self.store.pinned.add(row["path"])
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.frame = None
        self.position,self.duration = 0.0,row["duration"]
        self.paused,self.speed,self.seek = False,1.0,None
        self.status = "Opening recording"
        self.dragging = False
        ttk.Label(self,text=row["camera"]+"  /  "+row["started_utc"][:19]+" UTC",padding=14).pack(fill="x")
        self.canvas = tk.Canvas(self,bg="#050b12",highlightthickness=0)
        self.canvas.pack(fill="both",expand=True,padx=14)
        self.slider = ttk.Scale(self,from_=0,to=max(.1,self.duration))
        self.slider.pack(fill="x",padx=14,pady=10)
        self.slider.bind("<ButtonPress-1>",lambda e: setattr(self,"dragging",True))
        self.slider.bind("<ButtonRelease-1>",self.seek_to)
        bar = ttk.Frame(self,padding=14); bar.pack(fill="x")
        self.button = ttk.Button(bar,text="Pause",command=self.toggle); self.button.pack(side="left")
        self.rate = tk.StringVar(value="1×")
        speeds = ttk.Combobox(bar,textvariable=self.rate,values=["0.5×","1×","2×","4×"],state="readonly",width=6)
        speeds.pack(side="left",padx=12)
        speeds.bind("<<ComboboxSelected>>",lambda e: setattr(self,"speed",float(self.rate.get().rstrip("×"))))
        self.label = ttk.Label(bar,text=""); self.label.pack(side="left")
        ttk.Label(self,text="Video playback. Export the MKV to play any recorded audio in your video player.",padding=(14,0,14,12)).pack(anchor="w")
        self.worker = threading.Thread(target=self._decode,daemon=True,name="recording-playback")
        self.worker.start()
        self.poll_id = self.after(60,self.poll)
        self.protocol("WM_DELETE_WINDOW",self.close)

    def toggle(self):
        self.paused = not self.paused
        self.button.configure(text="Play" if self.paused else "Pause")

    def seek_to(self, event=None):
        self.seek = self.slider.get()
        self.dragging = False

    def _decode(self):
        import cv2
        cap = cv2.VideoCapture(str(self.path),cv2.CAP_FFMPEG)
        try:
            if not cap.isOpened():
                self.status = "Cannot decode this recording; export it for another player."
                return
            fps = cap.get(cv2.CAP_PROP_FPS)
            fps = fps if 1 <= fps <= 240 else 25
            first = True
            while not self.stop_event.is_set():
                target = self.seek
                if target is not None:
                    self.seek = None
                    cap.set(cv2.CAP_PROP_POS_MSEC,target*1000)
                    first = True
                if self.paused and not first:
                    self.stop_event.wait(.05); continue
                started = time.monotonic()
                ok,image = cap.read()
                if not ok:
                    self.paused = True
                    self.status = "End of segment"
                    self.stop_event.wait(.05); continue
                first = False
                h,w = image.shape[:2]
                if w > 1280:
                    image = cv2.resize(image,(1280,round(h*1280/w)))
                with self.lock:
                    self.frame = image
                    self.position = max(0,cap.get(cv2.CAP_PROP_POS_MSEC)/1000)
                self.status = "Playing"
                self.stop_event.wait(max(0,1/fps/self.speed-(time.monotonic()-started)))
        finally:
            cap.release()

    def poll(self):
        with self.lock:
            frame,self.frame = self.frame,None
            position = self.position
        if frame is not None:
            image = Image.fromarray(frame[:,:,::-1])
            image.thumbnail((max(2,self.canvas.winfo_width()),max(2,self.canvas.winfo_height())))
            self.photo = ImageTk.PhotoImage(image)
            self.canvas.delete("all")
            self.canvas.create_image(self.canvas.winfo_width()/2,self.canvas.winfo_height()/2,image=self.photo)
        if not self.dragging:
            self.slider.set(position)
        self.label.configure(text=f"{position:.1f} / {self.duration:.1f} seconds  ·  {self.status}")
        self.button.configure(text="Play" if self.paused else "Pause")
        self.poll_id = self.after(60,self.poll)

    def close(self):
        self.stop_event.set()
        self.after_cancel(self.poll_id)
        # Keep the file pinned until the decoder has released it.
        def release():
            self.worker.join(timeout=10)
            if not self.worker.is_alive():
                self.store.pinned.discard(self.row["path"])
        threading.Thread(target=release,daemon=True).start()
        self.destroy()
