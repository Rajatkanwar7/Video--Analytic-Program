"""First-run enrollment and named-operator sign-in before camera access."""
from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import messagebox, ttk


class LoginWindow(tk.Tk):
    def __init__(self, auth):
        super().__init__()
        self.auth = auth
        self.session = None
        self.setup = auth.needs_setup()
        self.title("JailWatch VMS | Sign in")
        self.geometry("560x600+60+35")
        self.minsize(520, 560)
        self.configure(bg="#0c121c")
        style = ttk.Style(self); style.theme_use("clam")
        style.configure("Login.TFrame", background="#0c121c")
        style.configure("Login.TLabel", background="#0c121c", foreground="#e7eef8", font=("Segoe UI",11))
        style.configure("Login.TEntry", fieldbackground="#1b283b", foreground="#e7eef8", insertcolor="#e7eef8", padding=10)
        style.configure("Login.TButton", background="#48c8d9", foreground="#06161d", font=("Segoe UI",11,"bold"), padding=12)
        frame = ttk.Frame(self, style="Login.TFrame", padding=38); frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="JAILWATCH", style="Login.TLabel", font=("Segoe UI",24,"bold")).pack(anchor="w")
        ttk.Label(frame, text="LOCAL VIDEO MANAGEMENT", style="Login.TLabel", foreground="#48c8d9").pack(anchor="w",pady=(5,24))
        ttk.Label(frame, text="Create your administrator" if self.setup else "Sign in to your camera wall",
                  style="Login.TLabel", font=("Segoe UI",17,"bold")).pack(anchor="w",pady=(0,10))
        text = ("Choose the first administrator account. There is no default password." if self.setup
                else "Use the account created on this CCTV computer.")
        ttk.Label(frame, text=text, style="Login.TLabel", wraplength=470).pack(anchor="w",pady=(0,18))
        self.username = tk.StringVar(); self.password = tk.StringVar(); self.confirm = tk.StringVar()
        for label, var, secret in [("Username",self.username,False),("Password / passphrase",self.password,True)]:
            ttk.Label(frame,text=label,style="Login.TLabel").pack(anchor="w",pady=(6,4))
            entry = ttk.Entry(frame,textvariable=var,show="•" if secret else "",style="Login.TEntry")
            entry.pack(fill="x")
            if not secret: entry.focus_set()
        if self.setup:
            ttk.Label(frame,text="Confirm password (15–128 characters)",style="Login.TLabel").pack(anchor="w",pady=(10,4))
            ttk.Entry(frame,textvariable=self.confirm,show="•",style="Login.TEntry").pack(fill="x")
        self.error = tk.StringVar()
        ttk.Label(frame,textvariable=self.error,style="Login.TLabel",foreground="#ffad93",wraplength=470).pack(fill="x",pady=(12,8))
        self.submit_button = ttk.Button(frame,text="Create account & open cameras" if self.setup else "Sign in",style="Login.TButton",
                   command=self.submit)
        self.submit_button.pack(fill="x",pady=6)
        self.bind("<Return>",lambda _: self.submit())
        self.protocol("WM_DELETE_WINDOW",self.destroy)

    def submit(self):
        try:
            if self.setup:
                if self.password.get() != self.confirm.get():
                    raise ValueError("The two passwords do not match.")
                self.session = self.auth.bootstrap(self.username.get(),self.password.get())
            else:
                self.session = self.auth.authenticate(self.username.get(),self.password.get())
        except (ValueError,PermissionError,OSError,sqlite3.Error) as exc:
            self.error.set(str(exc) if isinstance(exc,(ValueError,PermissionError)) else "Account storage is unavailable. Check the data folder.")
            self.password.set(""); self.confirm.set("")
            return
        self.password.set(""); self.confirm.set("")
        self.destroy()


def manage_accounts(app):
    app.auth.require(app.session,admin=True)
    win = tk.Toplevel(app); win.title("Operator accounts"); win.geometry("620x565"); win.transient(app)
    frame = ttk.Frame(win,padding=20); frame.pack(fill="both",expand=True)
    ttk.Label(frame,text="Operator accounts",font=("Segoe UI",18,"bold")).pack(anchor="w",pady=(0,12))
    ttk.Label(frame,text="Administrators configure the system. Operators monitor and review alerts.",wraplength=570).pack(anchor="w",pady=(0,10))
    listing = ttk.Treeview(frame,columns=("name","role","enabled"),show="headings",height=5)
    for key,label,width in [("name","Username",220),("role","Role",130),("enabled","State",130)]:
        listing.heading(key,text=label); listing.column(key,width=width)
    listing.pack(fill="x")
    def refresh():
        listing.delete(*listing.get_children())
        for row in app.auth.accounts(app.session):
            listing.insert("","end",iid=row["name"],values=(row["name"],row["role"],"Enabled" if row["enabled"] else "Disabled"))
    def toggle():
        selected = listing.selection()
        if not selected: return
        try:
            name = selected[0]
            enabled = listing.item(name,"values")[2] != "Enabled"
            app.auth.set_enabled(app.session,name,enabled); refresh()
        except (ValueError,PermissionError) as exc:
            messagebox.showerror("Account",str(exc),parent=win)
    ttk.Button(frame,text="Enable / disable selected",command=toggle).pack(anchor="w",pady=8)
    form = ttk.Frame(frame); form.pack(fill="x",pady=10); form.columnconfigure(1,weight=1)
    name,password = tk.StringVar(),tk.StringVar(); role=tk.StringVar(value="operator")
    for row,label,var in [(0,"New username",name),(1,"New passphrase",password)]:
        ttk.Label(form,text=label).grid(row=row,column=0,sticky="w",padx=(0,12),pady=6)
        ttk.Entry(form,textvariable=var,show="•" if row else "").grid(row=row,column=1,sticky="ew")
    ttk.Label(form,text="Role").grid(row=2,column=0,sticky="w",pady=8)
    ttk.Combobox(form,textvariable=role,values=("operator","admin"),state="readonly").grid(row=2,column=1,sticky="ew")
    ttk.Label(frame,text="Use 15–128 characters. Keep a second administrator account for recovery.",wraplength=560).pack(anchor="w",pady=8)
    def create():
        try:
            app.auth.create_account(app.session,name.get(),password.get(),role.get())
            name.set(""); password.set(""); refresh()
        except (ValueError,PermissionError) as exc:
            messagebox.showerror("Account",str(exc),parent=win)
    ttk.Button(frame,text="Create account",command=create).pack(anchor="w")
    refresh()


def change_password(app):
    app.auth.require(app.session)
    win = tk.Toplevel(app); win.title("Change your password"); win.transient(app)
    form=ttk.Frame(win,padding=24); form.pack(fill="both",expand=True)
    values=[tk.StringVar() for _ in range(3)]
    for row,(label,var) in enumerate(zip(("Current password","New passphrase (15–128 characters)","Confirm new passphrase"),values)):
        ttk.Label(form,text=label).grid(row=row*2,column=0,sticky="w",pady=(8,4))
        ttk.Entry(form,textvariable=var,show="•",width=45).grid(row=row*2+1,column=0,sticky="ew")
    def save():
        try:
            old,new,confirm=[v.get() for v in values]
            if new != confirm: raise ValueError("The two new passwords do not match.")
            app.session=app.auth.change_password(app.session,old,new)
            for v in values: v.set("")
            win.destroy(); app.notice.set("Password changed. Other sessions for this account have ended.")
        except (ValueError,PermissionError) as exc:
            messagebox.showerror("Password",str(exc),parent=win)
    ttk.Button(form,text="Change password",command=save).grid(row=6,column=0,sticky="ew",pady=(16,0))
