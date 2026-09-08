from __future__ import annotations

import copy
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

from . import __version__
from .config import Config, load_config, save_config
from .events import EventStore

BG, PANEL, TEXT, MUTED, ACCENT, RED = "#101b2c", "#19283b", "#ecf3fa", "#a7b8cb", "#45d5b3", "#ef6572"


class ZoneEditor(tk.Toplevel):
    def __init__(self, parent, image, config, on_save):
        super().__init__(parent)
        self.title("Draw camera zones")
        self.config_copy = copy.deepcopy(config)
        self.on_save = on_save
        self.original_size = [image.shape[1], image.shape[0]]
        rgb = Image.fromarray(image[:, :, ::-1])
        rgb.thumbnail((min(1100, self.winfo_screenwidth()-80), min(700, self.winfo_screenheight()-240)))
        self.width, self.height = rgb.size
        self.photo = ImageTk.PhotoImage(rgb)
        self.zone = tk.StringVar(value="outside")
        self.polygons = {"outside": list(config.outside_zone), "inside": list(config.inside_zone),
                         "ignore": list(config.ignore_zones[0]) if config.ignore_zones else []}
        # Additional ignore polygons in manually edited configs are preserved.
        self.extra_ignore = config.ignore_zones[1:]
        self.colors = {"outside": "#ffc55b", "inside": "#56ddad", "ignore": "#b795ff"}
        ttk.Label(self, text="Select a zone, then click its corners. Draw OUTSIDE and INSIDE on the correct sides of the wall.",
                  padding=12).pack()
        bar = ttk.Frame(self, padding=(12, 0, 12, 8)); bar.pack(fill="x")
        for label in self.polygons:
            ttk.Radiobutton(bar, text=label.upper(), variable=self.zone, value=label).pack(side="left", padx=8)
        ttk.Button(bar, text="Clear selected", command=self.clear).pack(side="right", padx=4)
        ttk.Button(bar, text="Undo point", command=self.undo).pack(side="right", padx=4)
        self.canvas = tk.Canvas(self, width=self.width, height=self.height, highlightthickness=0)
        self.canvas.pack(padx=12)
        self.canvas.bind("<Button-1>", self.add)
        ttk.Label(self, text="Zones cannot overlap. Leave a narrow gap over the wall. Ignore zones exclude vegetation or overlays.",
                  padding=10).pack()
        ttk.Button(self, text="Save zones", command=self.save).pack(pady=(0, 12))
        self.redraw()

    def add(self, event):
        self.polygons[self.zone.get()].append([min(1, max(0, event.x / self.width)),
                                               min(1, max(0, event.y / self.height))])
        self.redraw()

    def undo(self):
        if self.polygons[self.zone.get()]:
            self.polygons[self.zone.get()].pop()
        self.redraw()

    def clear(self):
        self.polygons[self.zone.get()] = []
        self.redraw()

    def redraw(self):
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        for name, polygon in self.polygons.items():
            points = [(x*self.width, y*self.height) for x, y in polygon]
            if len(points) >= 3:
                self.canvas.create_polygon(points, outline=self.colors[name], fill="", width=3)
            elif len(points) == 2:
                self.canvas.create_line(*points[0], *points[1], fill=self.colors[name], width=3)
            for x, y in points:
                self.canvas.create_oval(x-4, y-4, x+4, y+4, fill=self.colors[name], outline="")
            if points:
                self.canvas.create_text(points[0][0]+8, points[0][1]+12, text=name.upper(),
                                        fill=self.colors[name], anchor="w", font=("Segoe UI", 11, "bold"))

    def save(self):
        c = self.config_copy
        c.outside_zone, c.inside_zone = self.polygons["outside"], self.polygons["inside"]
        c.ignore_zones = ([self.polygons["ignore"]] if self.polygons["ignore"] else []) + self.extra_ignore
        c.calibration_size = self.original_size
        try:
            c.validate()
            self.on_save(c)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Zones need attention", str(exc), parent=self)
            return
        self.destroy()


class App(tk.Tk):
    def __init__(self, config_path):
        super().__init__()
        self.title(f"JailWatch {__version__} | CCTV monitor")
        self.geometry("1240x900")
        self.minsize(980, 720)
        self.configure(bg=BG)
        self.config_path = Path(config_path)
        try:
            self.settings = load_config(self.config_path) if self.config_path.exists() else Config()
        except (ValueError, OSError) as exc:
            messagebox.showerror("Configuration", str(exc), parent=self)
            self.settings = Config()
        self.store = EventStore(self.settings.data_dir)
        self.messages = queue.Queue(maxsize=100)
        self.latest_frame = None
        self.frame_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.worker = None
        self.busy = False
        self.last_bell = 0
        self.last_history_refresh = 0
        self.history_rows = {}
        self._style()
        self._build()
        self.refresh_history()
        self.poll_after_id = self.after(80, self.poll)
        self.protocol("WM_DELETE_WINDOW", self.close_app)

    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        s.configure("TFrame", background=BG)
        s.configure("TLabel", background=BG)
        s.configure("Muted.TLabel", foreground=MUTED)
        s.configure("Title.TLabel", font=("Segoe UI", 23, "bold"))
        s.configure("TButton", background=PANEL, foreground=TEXT, padding=(14, 9), borderwidth=0)
        s.map("TButton", background=[("active", "#2b435e"), ("disabled", PANEL)],
              foreground=[("disabled", "#617286")])
        s.configure("Accent.TButton", background=ACCENT, foreground=BG)
        s.map("Accent.TButton", background=[("active", "#79e6cb")])
        s.configure("TEntry", fieldbackground=PANEL, foreground=TEXT, insertcolor=TEXT, padding=6)
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=PANEL, padding=(18, 10))
        s.map("TNotebook.Tab", background=[("selected", "#2b435e")])
        s.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                    rowheight=29, borderwidth=0)
        s.configure("Treeview.Heading", background=BG, foreground=MUTED, padding=8)
        s.map("Treeview", background=[("selected", "#315371")])
        s.configure("TCheckbutton", background=BG, foreground=TEXT)
        s.configure("TRadiobutton", background=BG, foreground=TEXT)

    def _build(self):
        top = ttk.Frame(self, padding=(24, 18)); top.pack(fill="x")
        ttk.Label(top, text="JailWatch", style="Title.TLabel").pack(side="left")
        ttk.Label(top, text="  PERIMETER MONITOR  /  LOCAL PROCESSING", style="Muted.TLabel").pack(side="left", padx=15)
        self.tabs = ttk.Notebook(self); self.tabs.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        self.monitor_tab = ttk.Frame(self.tabs, padding=14)
        self.setup_tab = ttk.Frame(self.tabs, padding=20)
        self.history_tab = ttk.Frame(self.tabs, padding=14)
        self.tabs.add(self.monitor_tab, text="Monitor")
        self.tabs.add(self.setup_tab, text="Camera setup")
        self.tabs.add(self.history_tab, text="Alarm history")
        bar = ttk.Frame(self.monitor_tab); bar.pack(fill="x", pady=(0, 12))
        self.start_button = ttk.Button(bar, text="Start monitoring", style="Accent.TButton", command=self.start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(bar, text="Stop", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=8)
        self.camera_label = ttk.Label(bar, text=self.settings.camera_name, font=("Segoe UI", 12, "bold"))
        self.camera_label.pack(side="right")
        self.status_var = tk.StringVar(value="Ready. Configure the camera and draw zones before starting.")
        ttk.Label(self.monitor_tab, textvariable=self.status_var, wraplength=1100).pack(fill="x", pady=(0, 10))
        self.video = tk.Canvas(self.monitor_tab, background="#080f1b", highlightthickness=0)
        self.video.pack(fill="both", expand=True)
        self.video.create_text(450, 210, text="Your camera view will appear here", fill=MUTED, font=("Segoe UI", 18))
        self.stats_var = tk.StringVar(value="Processed FPS —   |   Frame loss —   |   Birds filtered —")
        ttk.Label(self.monitor_tab, textvariable=self.stats_var, style="Muted.TLabel").pack(fill="x", pady=10)
        self.alarm_var = tk.StringVar(value="No unacknowledged alerts")
        self.alarm = tk.Label(self.monitor_tab, textvariable=self.alarm_var, bg=PANEL, fg=TEXT,
                              anchor="w", padx=15, pady=14, font=("Segoe UI", 12, "bold"))
        self.alarm.pack(fill="x")
        ttk.Label(self.monitor_tab, text="Suspected throws require review. Bird filtering cannot guarantee zero false alarms.",
                  style="Muted.TLabel").pack(anchor="w", pady=(10, 0))
        self._setup_form()
        self._history()

    def _setup_form(self):
        f = self.setup_tab
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text="1. Connect a camera or select a recorded video", font=("Segoe UI", 13, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))
        self.vars = {}
        rows = [("camera_name", "Camera name"), ("source", "RTSP URL or video file"),
                ("model", "YOLO model file"), ("device", "Device (cpu, auto or 0 for GPU)"),
                ("image_size", "AI input size (pixels)"), ("processing_width", "Motion processing width"),
                ("person_confidence", "Person confidence (0–1)"), ("bird_confidence", "Bird confidence (0–1)"),
                ("person_movement", "Person movement (image fraction)"),
                ("min_throw_speed", "Minimum crossing speed (image fraction/sec)"),
                ("min_throw_displacement", "Minimum travel (image fraction)"),
                ("cooldown_seconds", "Alarm cooldown (seconds)")]
        for row, (key, label) in enumerate(rows, 1):
            ttk.Label(f, text=label).grid(row=row, column=0, sticky="w", pady=5, padx=(0, 20))
            v = tk.StringVar(value=str(getattr(self.settings, key)))
            self.vars[key] = v
            entry = ttk.Entry(f, textvariable=v, show="•" if key == "source" else "")
            entry.grid(row=row, column=1, sticky="ew", pady=5)
            if key == "source":
                self.source_entry = entry
                ttk.Button(f, text="Choose video", command=self.choose_video).grid(row=row, column=2, padx=8)
            elif key == "model":
                ttk.Button(f, text="Choose model", command=self.choose_model).grid(row=row, column=2, padx=8)
        self.show_source = tk.BooleanVar()
        ttk.Checkbutton(f, text="Show source / camera login", variable=self.show_source,
            command=lambda: self.source_entry.configure(show="" if self.show_source.get() else "•")).grid(
                row=13, column=1, sticky="w", pady=6)
        ttk.Label(f, text="Settings are saved on this computer. Camera logins can be stored in the local config file.",
                  style="Muted.TLabel").grid(row=14, column=0, columnspan=3, sticky="w", pady=(4, 12))
        bar = ttk.Frame(f); bar.grid(row=15, column=0, columnspan=3, sticky="ew")
        self.save_button = ttk.Button(bar, text="Save settings", command=self.save)
        self.save_button.pack(side="left", padx=(0, 8))
        self.zone_button = ttk.Button(bar, text="2. Preview and draw zones", style="Accent.TButton", command=self.calibrate)
        self.zone_button.pack(side="left", padx=8)
        self.model_button = ttk.Button(bar, text="Download model", command=self.download_model)
        self.model_button.pack(side="left", padx=8)
        self.zone_var = tk.StringVar()
        ttk.Label(f, textvariable=self.zone_var, style="Muted.TLabel").grid(row=16, column=0, columnspan=3, sticky="w", pady=12)
        ttk.Label(f, text="Use a fixed camera view. Draw separate zones for each camera.\n"
                  "After setup, return to Monitor and press Start. Acknowledgments and snapshots are in Alarm history.",
                  wraplength=1050, style="Muted.TLabel").grid(row=17, column=0, columnspan=3, sticky="w")
        self.update_zone_label()

    def update_zone_label(self):
        self.zone_var.set(f"Outside: {len(self.settings.outside_zone)} points   |   "
                          f"Inside: {len(self.settings.inside_zone)} points   |   "
                          f"Ignore zones: {len(self.settings.ignore_zones)}")

    def _history(self):
        bar = ttk.Frame(self.history_tab); bar.pack(fill="x", pady=(0, 12))
        ttk.Button(bar, text="Acknowledge selected", command=self.acknowledge).pack(side="left", padx=(0, 8))
        ttk.Button(bar, text="View snapshot", command=self.open_snapshot).pack(side="left", padx=8)
        ttk.Button(bar, text="Export CSV", command=self.export).pack(side="left", padx=8)
        ttk.Button(bar, text="Refresh", command=self.refresh_history).pack(side="right")
        self.only_open = tk.BooleanVar()
        ttk.Checkbutton(bar, text="Unacknowledged only", variable=self.only_open,
                        command=self.refresh_history).pack(side="right", padx=15)
        columns = ("time", "camera", "kind", "video_time", "status")
        box = ttk.Frame(self.history_tab); box.pack(fill="both", expand=True)
        self.table = ttk.Treeview(box, columns=columns, show="headings", selectmode="extended")
        for name, title, width in zip(columns, ["Time (UTC)", "Camera", "Alert", "Video time (s)", "Status"], [180, 180, 200, 140, 140]):
            self.table.heading(name, text=title)
            self.table.column(name, width=width)
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side="left", fill="both", expand=True); scroll.pack(side="right", fill="y")
        self.table.bind("<Double-1>", lambda event: self.open_snapshot())
        ttk.Label(self.history_tab, text="Shows the latest 300 records. CSV includes all retained records. "
                  "Acknowledgment records operator review and does not delete evidence.", wraplength=1080,
                  style="Muted.TLabel").pack(anchor="w", pady=12)

    def read_form(self):
        c = copy.deepcopy(self.settings)
        for key, var in self.vars.items():
            old = getattr(c, key)
            try:
                value = type(old)(var.get().strip())
            except ValueError:
                raise ValueError(f"Enter a valid number for {key}.") from None
            setattr(c, key, value)
        # An explicitly entered source takes precedence over an optional env-only config.
        if c.source != self.settings.source:
            c.source_env = ""
            c.inside_zone, c.outside_zone, c.ignore_zones, c.calibration_size = [], [], [], []
        return c.validate(zones=False)

    def save(self):
        if self.busy or (self.worker and self.worker.is_alive()):
            messagebox.showinfo("Stop monitoring", "Stop monitoring before changing settings.", parent=self)
            return False
        try:
            self.settings = self.read_form()
            save_config(self.settings, self.config_path)
            self.store = EventStore(self.settings.data_dir)
            self.camera_label.configure(text=self.settings.camera_name)
            self.update_zone_label()
            self.status_var.set("Settings saved. Preview the source and check both zones.")
            self.refresh_history()
            return True
        except (ValueError, OSError) as exc:
            messagebox.showerror("Settings", str(exc), parent=self)
            return False

    def choose_video(self):
        path = filedialog.askopenfilename(filetypes=[("Video files", "*.mp4 *.ts *.mkv *.avi *.mov"), ("All files", "*.*")])
        if path:
            self.vars["source"].set(path)

    def choose_model(self):
        path = filedialog.askopenfilename(filetypes=[("YOLO weights", "*.pt"), ("All files", "*.*")])
        if path:
            self.vars["model"].set(path)

    def set_busy(self, busy):
        self.busy = busy
        for button in (self.start_button, self.zone_button, self.save_button, self.model_button):
            button.configure(state="disabled" if busy else "normal")

    def calibrate(self):
        if not self.save():
            return
        try:
            source = self.settings.resolved_source()
        except ValueError as exc:
            messagebox.showerror("Source", str(exc), parent=self); return
        self.set_busy(True)
        self.status_var.set("Reading a frame for zone setup…")
        self.tabs.select(self.monitor_tab)
        config = copy.deepcopy(self.settings)
        def task():
            try:
                from .capture import first_frame
                self.messages.put({"type": "calibration", "image": first_frame(source, config)})
            except Exception:
                self.messages.put({"type": "error", "text": "Cannot read the video. Check the source, camera login and network."})
        threading.Thread(target=task, daemon=True).start()

    def zones_saved(self, config):
        self.settings = config
        save_config(config, self.config_path)
        self.update_zone_label()
        self.status_var.set("Zones saved. Ready to start monitoring.")

    def download_model(self):
        if self.busy or (self.worker and self.worker.is_alive()):
            return
        self.set_busy(True)
        self.status_var.set("Downloading the default model from Ultralytics…")
        def task():
            try:
                from .model_setup import download_model
                path = download_model("yolo11n.pt", Path("models"))
                self.messages.put({"type": "model", "path": str(path)})
            except Exception:
                self.messages.put({"type": "error", "text": "Model download failed. Check internet access or select an existing trusted model file."})
        threading.Thread(target=task, daemon=True).start()

    def callback(self, message):
        if message["type"] == "frame":
            with self.frame_lock:
                self.latest_frame = message
        else:
            try:
                self.messages.put_nowait(message)
            except queue.Full:
                # Alert evidence is already durable in SQLite; UI reloads it periodically.
                pass

    def start(self):
        if not self.save():
            return
        try:
            self.settings.validate()
            self.settings.resolved_source()
        except ValueError as exc:
            messagebox.showerror("Setup required", str(exc), parent=self)
            self.tabs.select(self.setup_tab); return
        self.set_busy(True)
        self.stop_button.configure(state="normal")
        self.stop_event.clear()
        config = copy.deepcopy(self.settings)
        store = self.store
        def task():
            try:
                from .pipeline import run_monitor
                summary = run_monitor(config, store, self.stop_event, self.callback, realtime=True)
                self.callback({"type": "finished", "summary": summary})
            except (ValueError, OSError, ImportError) as exc:
                self.callback({"type": "error", "text": str(exc) if isinstance(exc, ValueError) else
                    "Monitoring stopped. Check installed dependencies, model, source and writable data folder."})
            except Exception:
                self.callback({"type": "error", "text": "AI/video processing failed. Monitoring has stopped. Check the model/device settings and installation."})
        self.worker = threading.Thread(target=task, daemon=True, name="monitor")
        self.worker.start()

    def stop(self):
        self.stop_event.set()
        self.stop_button.configure(state="disabled")
        self.status_var.set("Stopping after the current frame…")

    def poll(self):
        try:
            while True:
                m = self.messages.get_nowait()
                kind = m["type"]
                if kind == "event":
                    self.refresh_history()
                    if self.settings.beep and time.monotonic() - self.last_bell > 1:
                        self.bell(); self.last_bell = time.monotonic()
                elif kind == "status":
                    self.status_var.set(m["text"])
                elif kind == "calibration":
                    self.set_busy(False)
                    ZoneEditor(self, m["image"], self.settings, self.zones_saved)
                elif kind == "model":
                    self.set_busy(False)
                    self.vars["model"].set(m["path"])
                    self.status_var.set("Model downloaded. Save settings to use it.")
                elif kind == "finished":
                    self.set_busy(False); self.stop_button.configure(state="disabled")
                    self.status_var.set(f"Stopped. Processed {m['summary']['processed_frames']} frames.")
                    self.refresh_history()
                elif kind == "error":
                    self.set_busy(False); self.stop_button.configure(state="disabled")
                    self.status_var.set("MONITORING STOPPED — " + m["text"])
                    messagebox.showerror("JailWatch", m["text"], parent=self)
        except queue.Empty:
            pass
        with self.frame_lock:
            frame, self.latest_frame = self.latest_frame, None
        if frame is not None:
            rgb = Image.fromarray(frame["image"][:, :, ::-1])
            rgb.thumbnail((max(2, self.video.winfo_width()), max(2, self.video.winfo_height())))
            self.video_photo = ImageTk.PhotoImage(rgb)
            self.video.delete("all")
            self.video.create_image(self.video.winfo_width()/2, self.video.winfo_height()/2, image=self.video_photo)
            if self.worker and self.worker.is_alive() and not self.stop_event.is_set():
                self.status_var.set(frame["text"])
            self.stats_var.set(f"Processed FPS {frame['fps']:.1f}   |   Frame loss {frame['dropped']}   |   "
                f"Birds filtered {frame['suppressed_birds']}   |   Processing delay {frame['latency']:.2f}s   |   "
                f"AI pending {frame.get('ai_pending', 0)}   |   Video time {frame['source_time']:.1f}s")
        if time.monotonic() - self.last_history_refresh > 3:
            self.refresh_history()
        self.poll_after_id = self.after(80, self.poll)

    def refresh_history(self):
        if not hasattr(self, "table"):
            return
        selected = self.table.selection()
        rows = self.store.list(unacknowledged=self.only_open.get())
        self.history_rows = {r["id"]: r for r in rows}
        self.table.delete(*self.table.get_children())
        for r in rows:
            self.table.insert("", "end", iid=r["id"], values=(r["created_utc"], r["camera"],
                r["kind"].replace("_", " "), f"{r['source_time']:.2f}", "Reviewed" if r["acknowledged_utc"] else "NEW"))
        for sid in selected:
            if sid in self.history_rows:
                self.table.selection_add(sid)
        outstanding = self.store.list(limit=1, unacknowledged=True)
        if outstanding:
            r = outstanding[0]
            self.alarm_var.set(f"ALERT  ·  {r['camera']}  ·  {r['kind'].replace('_', ' ').upper()} — Open Alarm history to review")
            self.alarm.configure(bg="#712f3e", fg="white")
        else:
            self.alarm_var.set("No unacknowledged alerts")
            self.alarm.configure(bg=PANEL, fg=TEXT)
        self.last_history_refresh = time.monotonic()

    def acknowledge(self):
        ids = self.table.selection()
        if not ids:
            return
        note = simpledialog.askstring("Review note", "Optional review note (for example: confirmed throw or bird):", parent=self)
        if note is not None:
            self.store.acknowledge(ids, note)
            self.refresh_history()

    def open_snapshot(self):
        ids = self.table.selection()
        if not ids:
            return
        r = self.history_rows[ids[0]]
        try:
            path = self.store.snapshot_path(r["snapshot"])
            img = Image.open(path)
        except (ValueError, OSError):
            messagebox.showinfo("Snapshot", "No saved snapshot is available for this event.", parent=self); return
        img.thumbnail((1100, 680))
        win = tk.Toplevel(self); win.title("Alert evidence")
        photo = ImageTk.PhotoImage(img)
        label = ttk.Label(win, image=photo); label.image = photo; label.pack(padx=12, pady=12)
        ttk.Label(win, text=f"{r['message']}\nCamera: {r['camera']} | Video time: {r['source_time']:.2f}s\n"
                  f"Review note: {r['note'] or '—'}", padding=12, wraplength=1050).pack(anchor="w")

    def export(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="jailwatch_alerts.csv",
                                          filetypes=[("CSV", "*.csv")])
        if path:
            try:
                self.store.export_csv(path)
                messagebox.showinfo("Export complete", "Alarm history exported.", parent=self)
            except OSError:
                messagebox.showerror("Export", "Could not write the file. Check folder permissions.", parent=self)

    def close_app(self):
        self.stop_event.set()
        self.after_cancel(self.poll_after_id)
        self.destroy()
