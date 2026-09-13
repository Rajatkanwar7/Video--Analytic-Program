from __future__ import annotations

import copy
import json
import math
import os
import queue
import sqlite3
import subprocess
import sys
import threading
import time
import tkinter as tk
import uuid
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

from jailwatch.config import load_config
from jailwatch.events import EventStore
from jailwatch.rules import Candidate
from .devices import Camera, DataLock, Inventory, Preferences, bundled_model, data_home, redacted_source, stream_url
from .engine import MonitorManager
from .recording import RecordingStore

BG = "#0c121c"
PANEL = "#141e2d"
TEXT = "#e8edf5"
MUTED = "#93a5bb"
ACCENT = "#32b7c9"
GREEN = "#53d4a0"
AMBER = "#ffcb70"
RED = "#ff7b86"


def open_folder(path):
    path = str(Path(path).resolve())
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open",path])
    else:
        subprocess.Popen(["xdg-open",path])


def field(parent, label, variable, row, secret=False):
    ttk.Label(parent,text=label).grid(row=row,column=0,sticky="w",padx=(0,14),pady=7)
    entry = ttk.Entry(parent,textvariable=variable,show="•" if secret else "")
    entry.grid(row=row,column=1,sticky="ew",pady=7)
    return entry


def scroll_form(parent):
    outer = ttk.Frame(parent)
    canvas = tk.Canvas(outer,bg=BG,highlightthickness=0)
    bar = ttk.Scrollbar(outer,orient="vertical",command=canvas.yview)
    canvas.configure(yscrollcommand=bar.set)
    bar.pack(side="right",fill="y"); canvas.pack(side="left",fill="both",expand=True)
    content = ttk.Frame(canvas,padding=16)
    item = canvas.create_window(0,0,window=content,anchor="nw")
    content.bind("<Configure>",lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>",lambda e: canvas.itemconfigure(item,width=e.width))
    return outer,content


class CameraDialog(tk.Toplevel):
    def __init__(self, app, camera=None, endpoint=""):
        super().__init__(app)
        self.app = app
        self.camera = copy.deepcopy(camera) if camera else Camera()
        self.title("Edit camera" if camera else "Add camera or recorder channel")
        self.geometry("750x660"); self.minsize(710,620)
        self.configure(bg=BG); self.transient(app)
        self.profiles = []; self.fingerprint = None
        outer = ttk.Frame(self,padding=22); outer.pack(fill="both",expand=True)
        top = ttk.Frame(outer); top.pack(fill="x"); top.columnconfigure(1,weight=1)
        self.name = tk.StringVar(value=camera.name if camera else "")
        self.group = tk.StringVar(value=self.camera.group)
        field(top,"Camera name",self.name,0); field(top,"Site / group",self.group,1)
        self.tabs = ttk.Notebook(outer); self.tabs.pack(fill="both",expand=True,pady=16)
        onvif_page,onvif = scroll_form(self.tabs); manual_page,manual = scroll_form(self.tabs)
        analytic_page,analytic = scroll_form(self.tabs)
        self.tabs.add(onvif_page,text="IP / ONVIF"); self.tabs.add(manual_page,text="RTSP / video file")
        self.tabs.add(analytic_page,text="AI settings")
        self.connection_mode = 1 if camera else 0
        def changed(event):
            index = self.tabs.index(self.tabs.select())
            if index in (0,1):
                self.connection_mode = index
        self.tabs.bind("<<NotebookTabChanged>>",changed)
        onvif.columnconfigure(1,weight=1); manual.columnconfigure(1,weight=1); analytic.columnconfigure(1,weight=1)
        self.endpoint = tk.StringVar(value=endpoint)
        self.username = tk.StringVar(); self.password = tk.StringVar()
        field(onvif,"Device IP / ONVIF address",self.endpoint,0)
        field(onvif,"ONVIF username",self.username,1); field(onvif,"Password",self.password,2,True)
        ttk.Label(onvif,text="Example: 192.168.1.10 or 192.168.1.10:8080\nUse the device's ONVIF port and an enabled ONVIF account.",
                  style="Muted.TLabel",wraplength=550).grid(row=3,column=0,columnspan=2,sticky="w",pady=10)
        self.fetch_button = ttk.Button(onvif,text="Get available streams",command=self.get_streams)
        self.fetch_button.grid(row=4,column=0,columnspan=2,sticky="w",pady=8)
        self.profile_var = tk.StringVar()
        self.profile_box = ttk.Combobox(onvif,textvariable=self.profile_var,state="readonly")
        self.profile_box.grid(row=5,column=0,columnspan=2,sticky="ew",pady=8)
        self.connection_status = tk.StringVar(value="Enter the device address and login, then get its streams.")
        ttk.Label(onvif,textvariable=self.connection_status,wraplength=570,style="Muted.TLabel").grid(
            row=6,column=0,columnspan=2,sticky="w",pady=8)
        self.source = tk.StringVar(value=self.camera.config.source)
        self.source_entry = field(manual,"Full RTSP URL or file",self.source,0,True)
        show = tk.BooleanVar()
        ttk.Checkbutton(manual,text="Show connection address and login",variable=show,
            command=lambda: self.source_entry.configure(show="" if show.get() else "•")).grid(row=1,column=1,sticky="w")
        ttk.Button(manual,text="Choose video file",command=self.choose_video).grid(row=2,column=1,sticky="w",pady=12)
        self.host = tk.StringVar(); self.port = tk.StringVar(value="554"); self.path = tk.StringVar()
        self.rtsp_user = tk.StringVar(); self.rtsp_password = tk.StringVar()
        for row,label,var in [(3,"Camera / NVR IP",self.host),(4,"RTSP port",self.port),(5,"Stream path",self.path),
                              (6,"Username",self.rtsp_user),(7,"Password",self.rtsp_password)]:
            field(manual,label,var,row,label=="Password")
        ttk.Button(manual,text="Build RTSP address",command=self.build_url).grid(row=8,column=1,sticky="w",pady=10)
        self.ai_enabled = tk.BooleanVar(value=self.camera.analytics)
        self.test_mode = tk.BooleanVar(value=self.camera.config.test_mode)
        self.trails = tk.BooleanVar(value=self.camera.config.show_trajectories)
        self.strict = tk.BooleanVar(value=self.camera.config.require_object_class)
        for row,text,var in [(0,"Enable AI (saved zones required)",self.ai_enabled),(1,"Mark detection events as a live test",self.test_mode),
                             (2,"Show measured trajectories",self.trails),(3,"Require custom thrown_object class",self.strict)]:
            ttk.Checkbutton(analytic,text=text,variable=var).grid(row=row,column=0,columnspan=2,sticky="w",pady=5)
        self.model = tk.StringVar(value=self.camera.config.model)
        self.device = tk.StringVar(value=self.camera.config.device)
        self.image_size = tk.StringVar(value=str(self.camera.config.image_size))
        self.motion_width = tk.StringVar(value=str(self.camera.config.processing_width))
        field(analytic,"Model file",self.model,4)
        ttk.Button(analytic,text="Choose model",command=self.choose_model).grid(row=5,column=1,sticky="w")
        field(analytic,"AI device (cpu / auto / 0)",self.device,6)
        field(analytic,"AI input size",self.image_size,7); field(analytic,"Motion processing width",self.motion_width,8)
        ttk.Label(analytic,text="Add the camera first, then use AI zones to draw its perimeter and enable alerts.\n"
                  "The default model filters recognized birds; it cannot guarantee zero false alarms.",
                  style="Muted.TLabel",wraplength=570).grid(row=9,column=0,columnspan=2,sticky="w",pady=12)
        bottom = ttk.Frame(outer); bottom.pack(fill="x")
        ttk.Button(bottom,text="Cancel",command=self.destroy).pack(side="right")
        self.save_button = ttk.Button(bottom,text="Save camera",style="Accent.TButton",command=self.save)
        self.save_button.pack(side="right",padx=10)
        ttk.Label(bottom,text="Windows protects saved logins with your Windows account.",style="Muted.TLabel",
                  wraplength=340).pack(side="left")
        if camera:
            self.tabs.select(manual_page)

    def choose_video(self):
        path = filedialog.askopenfilename(parent=self,filetypes=[("Videos","*.mp4 *.ts *.mkv *.avi *.mov"),("All files","*.*")])
        if path:
            self.source.set(path)

    def choose_model(self):
        path = filedialog.askopenfilename(parent=self,filetypes=[("YOLO weights","*.pt")])
        if path:
            self.model.set(path)

    def build_url(self):
        try:
            self.source.set(stream_url(self.host.get(),int(self.port.get()),self.path.get(),self.rtsp_user.get(),self.rtsp_password.get()))
        except ValueError as exc:
            messagebox.showerror("Camera address",str(exc),parent=self)

    def get_streams(self):
        from .onvif import OnvifClient
        values = (self.endpoint.get().strip(),self.username.get(),self.password.get())
        self.fetch_button.configure(state="disabled")
        self.connection_status.set("Contacting the device and reading stream profiles…")
        def work():
            client = OnvifClient(*values)
            try:
                return client.profiles(resolve=False)
            finally:
                client.close()
        def done(profiles):
            if not self.winfo_exists():
                return
            self.profiles,self.fingerprint = profiles,values
            self.profile_box.configure(values=[f"{p.name}  ·  {p.encoding}  {p.resolution}" for p in profiles])
            self.profile_box.current(0)
            self.fetch_button.configure(state="normal")
            self.connection_status.set(f"{len(profiles)} stream profiles found. Choose a camera/channel profile and save.")
        def failed(text):
            if self.winfo_exists():
                self.fetch_button.configure(state="normal"); self.connection_status.set(text)
        self.app.background(work,done,failed)

    def save(self):
        try:
            use_onvif = self.connection_mode==0
            source = self.source.get().strip()
            if use_onvif:
                if not self.profiles or self.profile_box.current() < 0:
                    raise ValueError("Get available streams and select one first, or use the RTSP tab.")
                if self.fingerprint != (self.endpoint.get().strip(),self.username.get(),self.password.get()):
                    raise ValueError("Connection details changed. Get the available streams again.")
                profile = self.profiles[self.profile_box.current()]
                if not profile.url:
                    from .onvif import OnvifClient
                    values = self.fingerprint
                    self.save_button.configure(state="disabled")
                    self.connection_status.set("Reading the selected stream address…")
                    def work():
                        client = OnvifClient(*values)
                        try:
                            return client.stream_uri(profile)
                        finally:
                            client.close()
                    def done(uri):
                        if self.winfo_exists():
                            profile.url = uri
                            self.save_button.configure(state="normal")
                            self.save()
                    def failed(text):
                        if self.winfo_exists():
                            self.save_button.configure(state="normal"); self.connection_status.set(text)
                    self.app.background(work,done,failed)
                    return
                source = profile.url
            camera = copy.deepcopy(self.camera)
            camera.name,camera.group = self.name.get().strip(),self.group.get().strip()
            camera.analytics = self.ai_enabled.get()
            if source != camera.config.source:
                camera.config.inside_zone = []; camera.config.outside_zone = []; camera.config.ignore_zones = []
                camera.config.calibration_size = []
                camera.analytics = False
            camera.config.source,camera.config.source_env = source,""
            camera.config.model,camera.config.device = self.model.get().strip(),self.device.get().strip()
            camera.config.image_size,camera.config.processing_width = int(self.image_size.get()),int(self.motion_width.get())
            camera.config.test_mode = self.test_mode.get()
            camera.config.show_trajectories = self.trails.get()
            camera.config.require_object_class = self.strict.get()
            self.app.inventory.put(camera)
            self.app.refresh_devices()
            self.app.select_camera(camera.id)
            self.destroy()
        except (ValueError,OSError,TypeError) as exc:
            messagebox.showerror("Camera settings",str(exc),parent=self)


class VMSApp(tk.Tk):
    def __init__(self, root=None, factory=None):
        super().__init__()
        self.title("JailWatch VMS 2.0 | Control room")
        self.geometry("1380x850"); self.minsize(1120,720)
        self.configure(bg=BG)
        try:
            self.data_lock = DataLock(root or data_home())
            self.inventory = Inventory(root or data_home())
            self.events = EventStore(self.inventory.root/"events")
            self.recordings = RecordingStore(self.inventory.root)
        except Exception:
            self.destroy()
            raise
        options = {"factory":factory} if factory else {}
        self.manager = MonitorManager(self.events,self.recordings,self.inventory.preferences,**options)
        self.jobs = queue.Queue()
        self.selected_id = None
        self.tiles = {}; self.photos = {}; self.tile_stamps = {}
        self.page_index = 0
        self.last_tables = 0; self.last_bell = 0
        self.closing = False
        self._style(); self._build(); self.refresh_devices(); self.refresh_alarms(); self.refresh_recordings()
        self.protocol("WM_DELETE_WINDOW",self.close_app)
        self.bind("<F11>",lambda e: self.attributes("-fullscreen",not self.attributes("-fullscreen")))
        self.bind("<Escape>",lambda e: self.attributes("-fullscreen",False))
        self.poll_id = self.after(100,self.poll)

    def _style(self):
        style = ttk.Style(self); style.theme_use("clam")
        style.configure(".",background=BG,foreground=TEXT,font=("Segoe UI",10),borderwidth=0)
        style.configure("TFrame",background=BG)
        style.configure("Card.TFrame",background=PANEL)
        style.configure("TLabel",background=BG,foreground=TEXT)
        style.configure("Muted.TLabel",foreground=MUTED)
        style.configure("Title.TLabel",font=("Segoe UI",22,"bold"))
        style.configure("TButton",padding=(13,9),background="#233149",foreground=TEXT)
        style.map("TButton",background=[("active","#344964"),("disabled","#192333")],foreground=[("disabled","#607188")])
        style.configure("Accent.TButton",background=ACCENT,foreground="#06161d",font=("Segoe UI",10,"bold"))
        style.map("Accent.TButton",background=[("active","#64d1de")])
        style.configure("TEntry",fieldbackground="#1b283b",foreground=TEXT,insertcolor=TEXT,padding=7)
        style.configure("TCombobox",fieldbackground="#1b283b",background="#1b283b",foreground=TEXT,padding=5)
        style.map("TCombobox",fieldbackground=[("readonly","#1b283b")],foreground=[("readonly",TEXT)])
        style.configure("TCheckbutton",background=BG,foreground=TEXT,padding=4)
        style.configure("Treeview",background=PANEL,fieldbackground=PANEL,foreground=TEXT,rowheight=35,borderwidth=0)
        style.configure("Treeview.Heading",background="#202c3e",foreground=MUTED,padding=(10,10),font=("Segoe UI",10,"bold"))
        style.map("Treeview",background=[("selected","#245265")])
        style.configure("TNotebook",background=BG)
        style.configure("TNotebook.Tab",padding=(17,10),background=PANEL,foreground=MUTED)
        style.map("TNotebook.Tab",background=[("selected","#254456")],foreground=[("selected",TEXT)])
        self.option_add("*TCombobox*Listbox.background",PANEL)
        self.option_add("*TCombobox*Listbox.foreground",TEXT)

    def _build(self):
        sidebar = tk.Frame(self,bg="#101a28",width=185); sidebar.pack(side="left",fill="y"); sidebar.pack_propagate(False)
        tk.Label(sidebar,text="JAILWATCH",bg="#101a28",fg=TEXT,font=("Segoe UI",18,"bold"),anchor="w").pack(fill="x",padx=20,pady=(28,0))
        tk.Label(sidebar,text="VIDEO MANAGEMENT",bg="#101a28",fg=ACCENT,font=("Segoe UI",8,"bold"),anchor="w").pack(fill="x",padx=22,pady=(2,30))
        self.nav = {}
        for name in ("Live view","Devices","Recordings","Alarms","Settings"):
            button = tk.Button(sidebar,text=name,command=lambda n=name: self.show_page(n),anchor="w",relief="flat",
                borderwidth=0,bg="#101a28",fg=MUTED,activebackground="#243448",activeforeground=TEXT,font=("Segoe UI",11),padx=22,pady=14)
            button.pack(fill="x",padx=8,pady=3); self.nav[name] = button
        self.side_status = tk.StringVar(value="LOCAL SYSTEM\n0 cameras connected")
        tk.Label(sidebar,textvariable=self.side_status,bg="#101a28",fg=MUTED,justify="left",anchor="w",
                 font=("Segoe UI",9)).pack(side="bottom",fill="x",padx=22,pady=24)
        main = ttk.Frame(self,padding=(24,20)); main.pack(side="left",fill="both",expand=True)
        head = ttk.Frame(main); head.pack(fill="x",pady=(0,16))
        self.page_title = tk.StringVar(value="Live view")
        ttk.Label(head,textvariable=self.page_title,style="Title.TLabel").pack(side="left")
        self.clock = ttk.Label(head,text="",style="Muted.TLabel"); self.clock.pack(side="right")
        self.notice = tk.StringVar(value="Add a device to begin. RTSP and supported ONVIF streams stay on your local network.")
        ttk.Label(main,textvariable=self.notice,style="Muted.TLabel",wraplength=1080).pack(fill="x",pady=(0,12))
        self.workspace = ttk.Frame(main); self.workspace.pack(fill="both",expand=True)
        self.workspace.rowconfigure(0,weight=1); self.workspace.columnconfigure(0,weight=1)
        self.pages = {}
        for name in self.nav:
            page = ttk.Frame(self.workspace); page.grid(row=0,column=0,sticky="nsew"); self.pages[name] = page
        self._live(); self._devices(); self._recordings(); self._alarms(); self._settings()
        self.show_page("Live view")

    def show_page(self, name):
        if not hasattr(self,"pages"):
            return
        self.pages[name].tkraise(); self.page_title.set(name)
        for key,button in self.nav.items():
            button.configure(bg="#244154" if key==name else "#101a28",fg=TEXT if key==name else MUTED)

    def _live(self):
        page = self.pages["Live view"]
        bar = ttk.Frame(page); bar.pack(fill="x",pady=(0,12))
        ttk.Button(bar,text="+ Add device",style="Accent.TButton",command=self.add_camera).pack(side="left")
        self.camera_choice = tk.StringVar()
        self.camera_combo = ttk.Combobox(bar,textvariable=self.camera_choice,state="readonly",width=28)
        self.camera_combo.pack(side="left",padx=12)
        self.camera_combo.bind("<<ComboboxSelected>>",lambda e: self.select_by_name())
        self.layout = tk.StringVar(value="4")
        layout = ttk.Combobox(bar,textvariable=self.layout,values=["1","4","9","16"],state="readonly",width=4)
        layout.pack(side="right"); layout.bind("<<ComboboxSelected>>",lambda e: self.rebuild_grid())
        ttk.Label(bar,text="Views",style="Muted.TLabel").pack(side="right",padx=8)
        controls = ttk.Frame(page); controls.pack(fill="x",pady=(0,12))
        for text,command in [("Connect",self.start_selected),("Disconnect",self.stop_selected),
                             ("Record",lambda: self.record_selected(True)),("Stop REC",lambda: self.record_selected(False)),
                             ("Snapshot",self.snapshot_selected),("AI zones",self.draw_zones),("Edit",self.edit_camera)]:
            ttk.Button(controls,text=text,command=command).pack(side="left",padx=(0,7))
        self.grid_frame = ttk.Frame(page); self.grid_frame.pack(fill="both",expand=True)
        pager = ttk.Frame(page); pager.pack(fill="x",pady=(10,0))
        ttk.Button(pager,text="Previous",command=lambda: self.change_page(-1)).pack(side="left")
        ttk.Button(pager,text="Next",command=lambda: self.change_page(1)).pack(side="left",padx=8)
        self.grid_status = ttk.Label(pager,text="",style="Muted.TLabel"); self.grid_status.pack(side="left",padx=12)
        ttk.Button(pager,text="Test alarm",command=self.test_alarm).pack(side="right")
        self.alarm_banner = tk.Label(page,text="No unacknowledged alerts",bg=PANEL,fg=MUTED,anchor="w",padx=14,pady=12,
                                     font=("Segoe UI",10,"bold"))
        self.alarm_banner.pack(fill="x",pady=(12,0)); self.alarm_banner.bind("<Button-1>",lambda e: self.show_page("Alarms"))

    def tree(self, page, columns):
        box = ttk.Frame(page); box.pack(fill="both",expand=True)
        tree = ttk.Treeview(box,columns=[c[0] for c in columns],show="headings",selectmode="extended")
        for key,label,width in columns:
            tree.heading(key,text=label); tree.column(key,width=width,minwidth=60)
        scroll = ttk.Scrollbar(box,orient="vertical",command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left",fill="both",expand=True); scroll.pack(side="right",fill="y")
        return tree

    def _devices(self):
        page = self.pages["Devices"]
        bar = ttk.Frame(page); bar.pack(fill="x",pady=(0,14))
        for text,command in [("+ Add device",self.add_camera),("Discover ONVIF",self.discover),
                             ("Edit selected",self.edit_device_row),("Health",self.health),("Remove",self.remove_device),
                             ("Connect all",self.start_all),("Disconnect all",self.manager.stop_all)]:
            ttk.Button(bar,text=text,command=command).pack(side="left",padx=(0,8))
        self.device_tree = self.tree(page,[("name","Camera",180),("group","Site / group",130),("status","Connection",180),
                                          ("ai","Analytics",190),("record","Recording",130),("source","Source",240)])
        self.device_tree.bind("<Double-1>",lambda e: self.edit_device_row())
        bottom = ttk.Frame(page); bottom.pack(fill="x",pady=(14,0))
        ttk.Button(bottom,text="Import earlier JailWatch camera",command=self.import_camera).pack(side="left")
        ttk.Button(bottom,text="Export device names",command=self.export_inventory).pack(side="left",padx=8)
        ttk.Label(bottom,text="Use one device entry per camera or recorder channel.",style="Muted.TLabel").pack(side="right")

    def _recordings(self):
        page = self.pages["Recordings"]
        bar = ttk.Frame(page); bar.pack(fill="x",pady=(0,14))
        self.record_camera = tk.StringVar(value="All cameras")
        self.record_combo = ttk.Combobox(bar,textvariable=self.record_camera,state="readonly",width=25)
        self.record_combo.pack(side="left")
        self.record_date = tk.StringVar()
        ttk.Label(bar,text="UTC date (YYYY-MM-DD)",style="Muted.TLabel").pack(side="left",padx=10)
        ttk.Entry(bar,textvariable=self.record_date,width=13).pack(side="left")
        ttk.Button(bar,text="Search",command=self.refresh_recordings).pack(side="left",padx=8)
        ttk.Button(bar,text="Play",command=self.play_recording).pack(side="right")
        self.record_tree = self.tree(page,[("camera","Camera",190),("start","Start (UTC, approximate)",220),
                                         ("duration","Seconds",120),("size","Size",120)])
        self.record_tree.bind("<Double-1>",lambda e: self.play_recording())
        bottom = ttk.Frame(page); bottom.pack(fill="x",pady=(14,0))
        ttk.Button(bottom,text="Export selected MKV",command=self.export_recording).pack(side="left")
        self.storage_status = ttk.Label(bottom,text="",style="Muted.TLabel"); self.storage_status.pack(side="right")
        ttk.Label(page,text="Completed segments appear here. Stop recording to close the current segment. Playback covers recordings made by this VMS.",
                  style="Muted.TLabel",wraplength=1050).pack(fill="x",pady=(12,0))

    def _alarms(self):
        page = self.pages["Alarms"]
        bar = ttk.Frame(page); bar.pack(fill="x",pady=(0,14))
        self.alarm_camera = tk.StringVar(value="All cameras")
        self.alarm_combo = ttk.Combobox(bar,textvariable=self.alarm_camera,state="readonly",width=25)
        self.alarm_combo.pack(side="left"); self.alarm_combo.bind("<<ComboboxSelected>>",lambda e: self.refresh_alarms())
        self.unreviewed = tk.BooleanVar()
        ttk.Checkbutton(bar,text="Unreviewed only",variable=self.unreviewed,command=self.refresh_alarms).pack(side="left",padx=12)
        ttk.Button(bar,text="View evidence",command=self.evidence).pack(side="right")
        self.alarm_tree = self.tree(page,[("time","Created (UTC)",180),("camera","Camera",170),("kind","Event",180),
                                        ("source","Source time",100),("review","Review",100)])
        self.alarm_tree.bind("<Double-1>",lambda e: self.evidence())
        bottom = ttk.Frame(page); bottom.pack(fill="x",pady=(14,0))
        for text,command in [("Acknowledge selected",self.acknowledge),("Export all events",self.export_events),
                             ("Export selected trajectories",self.export_trajectories)]:
            ttk.Button(bottom,text=text,command=command).pack(side="left",padx=(0,8))
        ttk.Label(page,text="Suspected throws require review. Test alarms check the display and sound only.",style="Muted.TLabel").pack(fill="x",pady=(12,0))

    def _settings(self):
        page = self.pages["Settings"]
        ttk.Label(page,text="Storage and processing",font=("Segoe UI",15,"bold")).pack(anchor="w",pady=(0,18))
        form = ttk.Frame(page); form.pack(fill="x"); form.columnconfigure(1,weight=1)
        self.preference_vars = {}
        for row,(key,label) in enumerate([("retention_days","Recording retention (days)"),("quota_gb","Closed recording limit (GB)"),
                  ("segment_seconds","Recording segment length (seconds)"),("max_live","Simultaneous live cameras (1–16)"),
                  ("max_analytics","Simultaneous AI cameras (1–8)")]):
            self.preference_vars[key] = tk.StringVar(value=str(getattr(self.inventory.preferences,key)))
            field(form,label,self.preference_vars[key],row)
        self.sound = tk.BooleanVar(value=self.inventory.preferences.beep)
        ttk.Checkbutton(page,text="Sound the system bell for alerts",variable=self.sound).pack(anchor="w",pady=12)
        ttk.Label(page,text="Oldest completed VMS recordings are deleted when the retention or size limit is exceeded. "
                  "Active segments temporarily add to the size limit. Recording pauses below 1 GB free. "
                  "Export evidence you need to retain. Stop cameras before changing these settings.",style="Muted.TLabel",wraplength=900).pack(anchor="w",pady=12)
        ttk.Button(page,text="Save settings",style="Accent.TButton",command=self.save_preferences).pack(anchor="w",pady=8)
        ttk.Separator(page).pack(fill="x",pady=22)
        ttk.Label(page,text="Application data",font=("Segoe UI",13,"bold")).pack(anchor="w")
        ttk.Label(page,text=str(self.inventory.root),style="Muted.TLabel",wraplength=950).pack(anchor="w",pady=8)
        buttons = ttk.Frame(page); buttons.pack(fill="x",pady=8)
        ttk.Button(buttons,text="Open data folder",command=lambda: open_folder(self.inventory.root)).pack(side="left")
        ttk.Button(buttons,text="Download default AI model",command=self.download_model).pack(side="left",padx=10)
        ttk.Label(page,text="The Windows EXE includes CPU AI and video dependencies. More cameras and higher resolutions require more processing capacity. "
                  "Check frame loss, AI delay and recording status on the actual CCTV computer. F11 toggles full screen.",
                  style="Muted.TLabel",wraplength=950).pack(anchor="w",pady=16)

    def background(self, work, done, failed=None):
        def task():
            try:
                self.jobs.put((done,work(),None))
            except Exception as exc:
                text = str(exc) if isinstance(exc,ValueError) else "The operation failed. Check connection details, permissions and available storage."
                self.jobs.put((failed,None,text))
        threading.Thread(target=task,daemon=True).start()

    def selected(self):
        camera = next((c for c in self.inventory.cameras if c.id==self.selected_id),None)
        if camera is None:
            raise ValueError("Select or add a camera first.")
        return camera

    def select_camera(self, camera_id):
        self.selected_id = camera_id
        camera = next((c for c in self.inventory.cameras if c.id==camera_id),None)
        if camera:
            self.camera_choice.set(camera.name)
            if self.layout.get()=="1":
                self.rebuild_grid()

    def select_by_name(self):
        for camera in self.inventory.cameras:
            if camera.name==self.camera_choice.get():
                self.select_camera(camera.id); break

    def add_camera(self):
        CameraDialog(self)

    def edit_camera(self):
        try:
            camera = self.selected()
            if self.manager.running(camera.id):
                raise ValueError("Disconnect this camera before editing its connection or AI settings.")
            CameraDialog(self,camera)
        except ValueError as exc:
            messagebox.showinfo("Camera",str(exc),parent=self)

    def edit_device_row(self):
        ids = self.device_tree.selection()
        if ids:
            self.select_camera(ids[0]); self.edit_camera()

    def health(self):
        ids = self.device_tree.selection()
        if not ids:
            return
        key = ids[0]
        camera = next(c for c in self.inventory.cameras if c.id==key)
        win = tk.Toplevel(self); win.title("Camera health | "+camera.name); win.configure(bg=BG)
        value = tk.StringVar()
        ttk.Label(win,textvariable=value,padding=22,justify="left",wraplength=600).pack(fill="both",expand=True)
        def update():
            if not win.winfo_exists():
                return
            worker = self.manager.workers.get(key)
            if worker:
                state,_,stamp = worker.snapshot()
                value.set(f"{camera.name}\n\nConnection: {state['status']}\nAI: {state['ai']}\nRecording: {state['recording']}\n\n"
                          f"Processed FPS: {state['fps']:.1f}\nDropped capture frames: {state['dropped']}\n"
                          f"Processing delay: {state['latency']:.2f} s\nPending AI work: {state['ai_pending']}\n"
                          f"AI queue overflows: {state['ai_overflows']}\nSeconds since displayed frame: {max(0,time.monotonic()-stamp):.1f}")
            else:
                value.set(camera.name+"\n\nNot connected.")
            win.after(1000,update)
        update()

    def remove_device(self):
        ids = self.device_tree.selection()
        if not ids:
            return
        if any(self.manager.running(key) for key in ids):
            messagebox.showinfo("Devices","Disconnect the selected cameras before removing them.",parent=self); return
        if not messagebox.askyesno("Remove devices","Remove the selected device entries? Saved recordings and alerts will remain.",parent=self):
            return
        for key in ids:
            self.inventory.remove(key)
        self.refresh_devices()

    def start_selected(self):
        try:
            self.manager.start(self.selected())
        except (ValueError,OSError) as exc:
            messagebox.showerror("Connect camera",str(exc),parent=self)

    def start_all(self):
        failures = []
        for camera in self.inventory.cameras:
            try:
                self.manager.start(camera)
            except (ValueError,OSError) as exc:
                failures.append(f"{camera.name}: {exc}")
        if failures:
            messagebox.showinfo("Camera connections","\n".join(failures[:10]),parent=self)

    def stop_selected(self):
        if self.selected_id:
            self.manager.stop(self.selected_id)

    def record_selected(self, enabled):
        try:
            self.manager.set_recording(self.selected().id,enabled)
            self.notice.set("Recording requested. Check the tile's REC status." if enabled else "Closing the recording segment…")
        except ValueError as exc:
            messagebox.showinfo("Recording",str(exc),parent=self)

    def draw_zones(self):
        try:
            camera = copy.deepcopy(self.selected())
            if self.manager.running(camera.id):
                raise ValueError("Disconnect this camera before changing its AI zones.")
        except ValueError as exc:
            messagebox.showinfo("AI zones",str(exc),parent=self); return
        self.notice.set("Opening the selected camera for zone calibration…")
        def work():
            from jailwatch.capture import first_frame
            return first_frame(camera.config.resolved_source(),camera.config)
        def done(image):
            from jailwatch.ui import ZoneEditor
            def saved(config):
                camera.config = config; camera.analytics = True
                self.inventory.put(camera); self.refresh_devices()
                self.notice.set(f"{camera.name}: zones saved and AI enabled. Connect the camera to begin alerts.")
            ZoneEditor(self,image,camera.config,saved)
        self.background(work,done)

    def discover(self):
        interface = simpledialog.askstring("ONVIF discovery","Optional local computer IPv4 address for the CCTV network adapter.\nLeave blank to use the default adapter.",parent=self)
        if interface is None:
            return
        self.notice.set("Searching the local network for ONVIF devices…")
        def work():
            from .onvif import discover
            return discover(interface.strip())
        def done(devices):
            self.notice.set(f"Found {len(devices)} ONVIF device addresses.")
            if not devices:
                messagebox.showinfo("Discovery","No devices responded. Check the CCTV network adapter and ONVIF setting, or add the IP manually.",parent=self); return
            win = tk.Toplevel(self); win.title("Discovered ONVIF devices"); win.geometry("800x400")
            tree = self.tree(win,[("name","Device",220),("address","ONVIF address",500)])
            for i,d in enumerate(devices):
                tree.insert("","end",iid=str(i),values=(d["name"],d["endpoint"]))
            def add():
                if tree.selection():
                    endpoint = devices[int(tree.selection()[0])]["endpoint"]
                    win.destroy(); CameraDialog(self,endpoint=endpoint)
            ttk.Button(win,text="Add selected device",command=add).pack(pady=12)
        self.background(work,done)

    def import_camera(self):
        path = filedialog.askopenfilename(parent=self,filetypes=[("JailWatch camera JSON","*.json")])
        if not path:
            return
        try:
            config = load_config(path)
            if not Path(config.model).is_absolute():
                candidate = Path(path).resolve().parent.parent/config.model
                config.model = str(candidate) if candidate.is_file() else bundled_model()
            camera = Camera(name=config.camera_name,config=config,analytics=bool(config.inside_zone and config.outside_zone))
            self.inventory.put(camera); self.refresh_devices(); self.select_camera(camera.id)
        except (ValueError,OSError,TypeError) as exc:
            messagebox.showerror("Import camera",str(exc),parent=self)

    def export_inventory(self):
        path = filedialog.asksaveasfilename(parent=self,defaultextension=".json",initialfile="camera_names.json")
        if path:
            self.inventory.export_redacted(path)

    def snapshot_selected(self):
        try:
            camera = self.selected()
            worker = self.manager.workers.get(camera.id)
            if not worker:
                raise ValueError("Connect this camera first.")
            _,image,stamp = worker.snapshot()
            if image is None or time.monotonic()-stamp > 2:
                raise ValueError("No current frame is available.")
            path = filedialog.asksaveasfilename(parent=self,defaultextension=".jpg",initialfile="camera_snapshot.jpg")
            if path:
                import cv2
                if not cv2.imwrite(path,image):
                    raise OSError("Cannot write snapshot.")
        except (ValueError,OSError) as exc:
            messagebox.showerror("Snapshot",str(exc),parent=self)

    def refresh_devices(self):
        selection = self.device_tree.selection()
        self.device_tree.delete(*self.device_tree.get_children())
        for camera in self.inventory.cameras:
            worker = self.manager.workers.get(camera.id)
            state = worker.snapshot()[0] if worker else {"status":"Not connected","ai":"Enabled" if camera.analytics else "Off","recording":"Off"}
            self.device_tree.insert("","end",iid=camera.id,values=(camera.name,camera.group,state["status"],state["ai"],state["recording"],redacted_source(camera.config.source)))
        for key in selection:
            if self.device_tree.exists(key):
                self.device_tree.selection_add(key)
        names = [c.name for c in self.inventory.cameras]
        self.camera_combo.configure(values=names)
        self.record_combo.configure(values=["All cameras"]+names)
        self.alarm_combo.configure(values=["All cameras"]+names)
        if not any(c.id==self.selected_id for c in self.inventory.cameras):
            self.selected_id = self.inventory.cameras[0].id if self.inventory.cameras else None
        if self.selected_id:
            self.camera_choice.set(self.selected().name)
        else:
            self.camera_choice.set("")
        self.rebuild_grid()

    def change_page(self, delta):
        if self.layout.get()=="1" and self.inventory.cameras:
            index = next((i for i,c in enumerate(self.inventory.cameras) if c.id==self.selected_id),0)
            self.select_camera(self.inventory.cameras[(index+delta)%len(self.inventory.cameras)].id)
            return
        pages = max(1,math.ceil(len(self.inventory.cameras)/int(self.layout.get())))
        self.page_index = (self.page_index+delta)%pages
        self.rebuild_grid()

    def rebuild_grid(self):
        count = int(self.layout.get()); side = math.isqrt(count)
        cameras = self.inventory.cameras
        if count==1 and self.selected_id:
            cameras = [self.selected()]
        else:
            pages = max(1,math.ceil(len(cameras)/count)); self.page_index = min(self.page_index,pages-1)
            cameras = cameras[self.page_index*count:(self.page_index+1)*count]
        for widget in self.grid_frame.winfo_children():
            widget.destroy()
        for n in range(4):
            self.grid_frame.columnconfigure(n,weight=1 if n<side else 0)
            self.grid_frame.rowconfigure(n,weight=1 if n<side else 0)
        self.tiles = {}; self.photos = {}; self.tile_stamps = {}
        if not cameras:
            welcome = ttk.Frame(self.grid_frame,padding=22,style="Card.TFrame")
            welcome.grid(row=0,column=0,columnspan=side,rowspan=side,sticky="nsew")
            tk.Label(welcome,text="Your control room starts here",bg=PANEL,fg=TEXT,
                     font=("Segoe UI",20,"bold"),anchor="w").pack(fill="x",pady=(0,10))
            for title,description in [
                ("1   Add your camera","Enter its IP address and login, then choose a stream."),
                ("2   Connect and watch","Select the camera and click Connect. Use Record to save video."),
                ("3   Turn on perimeter alerts","Open AI zones, mark outside and inside, then reconnect.")]:
                tk.Label(welcome,text=title,bg=PANEL,fg=TEXT,font=("Segoe UI",12,"bold"),anchor="w").pack(fill="x",pady=(10,3))
                tk.Label(welcome,text=description,bg=PANEL,fg=MUTED,font=("Segoe UI",10),anchor="w",justify="left",wraplength=650).pack(fill="x")
            ttk.Button(welcome,text="Add my first camera",style="Accent.TButton",command=self.add_camera).pack(anchor="w",pady=(18,0))
            self.grid_status.configure(text="Add a camera IP, an RTSP stream, or a recorded video.")
            return
        for i in range(count):
            canvas = tk.Canvas(self.grid_frame,bg="#080e17",highlightthickness=1,highlightbackground="#26364c")
            canvas.grid(row=i//side,column=i%side,sticky="nsew",padx=4,pady=4)
            if i < len(cameras):
                camera = cameras[i]
                self.tiles[camera.id] = canvas
                canvas.bind("<Button-1>",lambda e,key=camera.id: self.select_camera(key))
                canvas.bind("<Double-1>",lambda e,key=camera.id: self.focus_tile(key))
            else:
                canvas.create_text(20,28,text="ADD A CAMERA" if not cameras else "EMPTY VIEW",fill="#3a4d66",anchor="w",font=("Segoe UI",10,"bold"))
        self.grid_status.configure(text=f"{len(self.inventory.cameras)} devices  ·  Page {self.page_index+1}  ·  Double-click a camera to enlarge")

    def focus_tile(self, key):
        self.selected_id = key; self.camera_choice.set(self.selected().name)
        self.layout.set("1"); self.rebuild_grid()

    def refresh_recordings(self, auto=False):
        camera = next((c for c in self.inventory.cameras if c.name==self.record_camera.get()),None)
        try:
            rows = self.recordings.list(camera.id if camera else None,self.record_date.get().strip())
        except ValueError:
            if not auto:
                messagebox.showinfo("Recording search","Use a date such as 2026-09-12, or leave the date empty.",parent=self)
            return
        selected = self.record_tree.selection()
        self.record_tree.delete(*self.record_tree.get_children())
        self.record_rows = {r["path"]:r for r in rows}
        for r in rows:
            self.record_tree.insert("","end",iid=r["path"],values=(r["camera"],r["started_utc"][:19].replace("T"," "),f"{r['duration']:.1f}",f"{r['bytes']/1024**2:.1f} MB"))
        for key in selected:
            if self.record_tree.exists(key):
                self.record_tree.selection_add(key)
        total = self.recordings.totals()
        self.storage_status.configure(text=f"{total['segments']} segments  ·  {total['bytes']/1024**3:.2f} GB stored  ·  {total['free_bytes']/1024**3:.1f} GB free")

    def play_recording(self):
        selected = self.record_tree.selection()
        if selected:
            from .playback import Playback
            Playback(self,self.recordings,self.record_rows[selected[0]])

    def export_recording(self):
        selected = self.record_tree.selection()
        if not selected:
            return
        path = filedialog.asksaveasfilename(parent=self,defaultextension=".mkv",initialfile="camera_recording.mkv")
        if path:
            self.background(lambda: self.recordings.export(selected[0],path),lambda _: self.notice.set("Recording exported."))

    def refresh_alarms(self):
        rows = self.events.list(limit=1000,unacknowledged=self.unreviewed.get())
        if self.alarm_camera.get()!="All cameras":
            rows = [r for r in rows if r["camera"]==self.alarm_camera.get()]
        selected = self.alarm_tree.selection()
        self.alarm_rows = {r["id"]:r for r in rows}
        self.alarm_tree.delete(*self.alarm_tree.get_children())
        for r in rows:
            self.alarm_tree.insert("","end",iid=r["id"],values=(r["created_utc"][:19].replace("T"," "),r["camera"],
                r["kind"].replace("_"," "),f"{r['source_time']:.2f}s","Reviewed" if r["acknowledged_utc"] else "NEW"))
        for key in selected:
            if self.alarm_tree.exists(key):
                self.alarm_tree.selection_add(key)
        outstanding = self.events.list(limit=1,unacknowledged=True)
        if outstanding:
            last = outstanding[0]
            self.alarm_banner.configure(text=f"ALERT  /  {last['camera']}  /  {last['kind'].replace('_',' ').upper()}  —  Click to review",bg="#582934",fg=TEXT)
        else:
            self.alarm_banner.configure(text="No unacknowledged alerts",bg=PANEL,fg=MUTED)

    def acknowledge(self):
        ids = self.alarm_tree.selection()
        if not ids:
            return
        note = simpledialog.askstring("Review events","Review note (for example: confirmed test throw, bird or normal activity):",parent=self)
        if note is not None:
            self.events.acknowledge(ids,note); self.refresh_alarms()

    def evidence(self):
        ids = self.alarm_tree.selection()
        if not ids:
            return
        row = self.alarm_rows[ids[0]]
        details = json.loads(row["details"])
        win = tk.Toplevel(self); win.title("Evidence | "+row["camera"]); win.configure(bg=BG)
        try:
            with Image.open(self.events.snapshot_path(row["snapshot"])) as source:
                image = source.copy()
            image.thumbnail((1100,650))
            photo = ImageTk.PhotoImage(image)
            label = ttk.Label(win,image=photo); label.image = photo; label.pack(padx=16,pady=16)
        except (ValueError,OSError):
            ttk.Label(win,text="This event has no saved image.",padding=20).pack()
        stats = details.get("trajectory_statistics",{})
        ttk.Label(win,text=f"{row['message']}\nCamera: {row['camera']}  |  Source time: {row['source_time']:.2f}s  |  Test: {details.get('test_mode',False)}\n"
                  f"Path samples: {stats.get('sample_count',0)}  |  Classification: {details.get('classification','system event')}\n"
                  f"Review: {row['note'] or 'Not reviewed'}",wraplength=1080,padding=16).pack(anchor="w")

    def export_events(self):
        path = filedialog.asksaveasfilename(parent=self,defaultextension=".csv",initialfile="vms_alerts.csv")
        if path:
            self.events.export_csv(path)

    def export_trajectories(self):
        ids = self.alarm_tree.selection()
        if not ids:
            messagebox.showinfo("Trajectories","Select one or more detection events first.",parent=self); return
        path = filedialog.asksaveasfilename(parent=self,defaultextension=".csv",initialfile="vms_trajectories.csv")
        if path:
            try:
                self.events.export_trajectories(path,ids)
            except (ValueError,OSError) as exc:
                messagebox.showerror("Trajectories",str(exc),parent=self)

    def test_alarm(self):
        self.events.add(Candidate("system_test",0,0,(0,0,0,0),[],"Operator test: no object was detected."),
                        "Control room",uuid.uuid4().hex,details={"test_only":True,"test_mode":True})
        self.refresh_alarms()
        if self.inventory.preferences.beep:
            self.bell()
        self.notice.set("Test alarm created. Connect a camera with AI enabled to test real detection.")

    def save_preferences(self):
        if any(w.thread.is_alive() for w in self.manager.workers.values()):
            messagebox.showinfo("Settings","Disconnect all cameras before changing settings.",parent=self); return
        try:
            preferences = Preferences(**{k:int(v.get()) for k,v in self.preference_vars.items()},beep=self.sound.get())
            preferences.validate()
            previous = self.inventory.preferences
            self.inventory.preferences = preferences
            try:
                self.inventory.save()
            except Exception:
                self.inventory.preferences = previous
                raise
            self.manager.preferences = preferences
            self.notice.set("Storage and processing settings saved.")
        except (ValueError,OSError) as exc:
            messagebox.showerror("Settings",str(exc),parent=self)

    def download_model(self):
        self.notice.set("Downloading the default model from Ultralytics…")
        def work():
            from jailwatch.model_setup import download_model
            return str(download_model("yolo11n.pt",self.inventory.root/"models"))
        def done(path):
            self.notice.set("Model downloaded. Select it in a camera's AI settings: "+path)
        self.background(work,done)

    def poll(self):
        if self.closing:
            return
        try:
            while True:
                done,result,error = self.jobs.get_nowait()
                if error:
                    if done:
                        done(error)
                    else:
                        self.notice.set(error)
                elif done:
                    done(result)
        except queue.Empty:
            pass
        try:
            while True:
                event = self.manager.messages.get_nowait()
                if event["type"]=="event":
                    self.refresh_alarms()
                    if self.inventory.preferences.beep and time.monotonic()-self.last_bell > 1:
                        self.bell(); self.last_bell = time.monotonic()
                else:
                    self.notice.set(event["text"])
        except queue.Empty:
            pass
        now = time.monotonic()
        connected = 0
        for camera in self.inventory.cameras:
            worker = self.manager.workers.get(camera.id)
            state,image,stamp = worker.snapshot() if worker else ({"status":"Not connected","ai":"Off","recording":"Off","fps":0,"dropped":0,"ai_overflows":0},None,0)
            fresh = image is not None and now-stamp < 2 and self.manager.running(camera.id)
            connected += int(fresh)
            if self.device_tree.exists(camera.id):
                self.device_tree.set(camera.id,"status",state["status"])
                self.device_tree.set(camera.id,"ai",state["ai"])
                self.device_tree.set(camera.id,"record",state["recording"])
            canvas = self.tiles.get(camera.id)
            if canvas is None:
                continue
            width,height = max(2,canvas.winfo_width()),max(2,canvas.winfo_height())
            key = (stamp,width,height)
            if image is not None and self.tile_stamps.get(camera.id)!=key:
                photo = Image.fromarray(image[:,:,::-1]); photo.thumbnail((width,max(2,height-62)))
                self.photos[camera.id] = ImageTk.PhotoImage(photo)
                canvas.delete("frame")
                canvas.create_image(width/2,height/2,image=self.photos[camera.id],tags="frame")
                self.tile_stamps[camera.id] = key
            canvas.delete("overlay")
            canvas.create_rectangle(0,0,width,31,fill=PANEL,outline="",tags="overlay")
            canvas.create_oval(10,12,17,19,fill=GREEN if fresh else RED,outline="",tags="overlay")
            canvas.create_text(25,16,text=camera.name,fill=TEXT,anchor="w",font=("Segoe UI",10,"bold"),tags="overlay")
            if state["recording"]=="REC":
                canvas.create_text(width-12,16,text="● REC",fill=RED,anchor="e",font=("Segoe UI",9,"bold"),tags="overlay")
            elif "Off" not in state["recording"] and "off" not in state["recording"]:
                canvas.create_text(width-12,16,text="REC pending",fill=AMBER,anchor="e",tags="overlay")
            canvas.create_rectangle(0,height-31,width,height,fill=PANEL,outline="",tags="overlay")
            if camera.analytics:
                info = f"AI: {state['ai']}  |  lost {state['dropped']}  |  queue loss {state['ai_overflows']}"
            else:
                info = f"VIEW ONLY  |  {state['fps']:.1f} FPS  |  lost {state['dropped']}"
            canvas.create_text(10,height-16,text=info,fill=AMBER if state["dropped"] or "FAILED" in state["ai"] else MUTED,
                               anchor="w",font=("Segoe UI",8),width=max(40,width-20),tags="overlay")
            if not fresh:
                canvas.create_rectangle(0,height/2-24,width,height/2+24,fill="#151c29",outline="",tags="overlay")
                canvas.create_text(width/2,height/2,text=state["status"] if image is None else "NO CURRENT VIDEO  ·  "+state["status"],
                                   fill=AMBER,width=max(40,width-30),justify="center",font=("Segoe UI",10),tags="overlay")
            canvas.configure(highlightbackground=ACCENT if camera.id==self.selected_id else "#26364c")
        self.side_status.set(f"LOCAL SYSTEM\n{connected} / {len(self.inventory.cameras)} live\nCPU / device AI")
        self.clock.configure(text=time.strftime("%d %b %Y   %H:%M:%S UTC",time.gmtime()))
        if now-self.last_tables > 3:
            try:
                self.refresh_alarms()
                if self.page_title.get()=="Recordings":
                    self.refresh_recordings(auto=True)
            except (OSError,sqlite3.Error):
                self.notice.set("Storage is unavailable. Check the data folder and free space.")
            self.last_tables = now
        self.poll_id = self.after(100,self.poll)

    def close_app(self):
        if self.closing:
            return
        self.closing = True
        self.after_cancel(self.poll_id)
        for child in self.winfo_children():
            if hasattr(child,"close"):
                child.close()
        self.notice.set("Closing camera connections and recording segments…")
        def finished():
            self.manager.close()
            self.jobs.put((None,"closed",None))
        threading.Thread(target=finished,daemon=True).start()
        def await_close():
            try:
                while True:
                    _,value,_ = self.jobs.get_nowait()
                    if isinstance(value,str) and value=="closed":
                        self.destroy(); return
            except queue.Empty:
                pass
            self.after(100,await_close)
        await_close()

    def destroy(self):
        if hasattr(self,"data_lock"):
            self.data_lock.close()
        super().destroy()


def launch(root=None):
    app = VMSApp(root)
    app.mainloop()
