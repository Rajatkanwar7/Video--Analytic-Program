"""Local operator authentication. Windows file permissions remain the security boundary.

No default accounts, plaintext passwords, network listeners, or persistent login tokens.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

ITERATIONS = 600_000


@dataclass(frozen=True)
class Session:
    token: str
    username: str
    role: str


class AuthStore:
    def __init__(self, root, clock=time.time):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "accounts.sqlite3"
        self.clock = clock
        self.sessions = {}
        with closing(self._db()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                  name TEXT PRIMARY KEY, salt BLOB NOT NULL, digest BLOB NOT NULL,
                  iterations INTEGER NOT NULL, role TEXT NOT NULL,
                  enabled INTEGER NOT NULL DEFAULT 1, revision INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS attempts (
                  name TEXT PRIMARY KEY, failures INTEGER NOT NULL, until REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS audit (
                  id INTEGER PRIMARY KEY, timestamp REAL NOT NULL, actor TEXT NOT NULL,
                  action TEXT NOT NULL, subject TEXT NOT NULL);
            """)
        if os.name != "nt":
            self.path.chmod(0o600)

    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _name(name):
        name = name.strip().casefold()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,39}", name):
            raise ValueError("Username: use 3–40 letters, numbers, dots, underscores or hyphens.")
        return name

    @staticmethod
    def _password(password):
        if not isinstance(password, str) or not 15 <= len(password) <= 128:
            raise ValueError("Use a password or passphrase of 15–128 characters.")

    @staticmethod
    def _digest(password, salt, iterations=ITERATIONS):
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)

    def _audit(self, db, actor, action, subject=""):
        db.execute("INSERT INTO audit(timestamp,actor,action,subject) VALUES(?,?,?,?)",
                   (self.clock(), actor, action, subject))
        db.execute("DELETE FROM audit WHERE id < (SELECT COALESCE(MAX(id),0)-4999 FROM audit)")

    def needs_setup(self):
        with closing(self._db()) as db:
            return db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0

    def _insert(self, db, name, password, role):
        self._password(password)
        if role not in ("admin", "operator"):
            raise ValueError("Choose admin or operator.")
        salt = secrets.token_bytes(24)
        try:
            db.execute("INSERT INTO users(name,salt,digest,iterations,role) VALUES(?,?,?,?,?)",
                       (name, salt, self._digest(password, salt), ITERATIONS, role))
        except sqlite3.IntegrityError:
            raise ValueError("That username already exists.") from None

    def bootstrap(self, name, password):
        name = self._name(name)
        with closing(self._db()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
                raise PermissionError("Administrator setup is already complete. Sign in.")
            self._insert(db, name, password, "admin")
            self._audit(db, name, "initial administrator created", name)
        return self.authenticate(name, password)

    def authenticate(self, name, password):
        # Limit input before hashing; return the same error for missing/disabled accounts.
        name = str(name).strip().casefold()[:128]
        password = password if isinstance(password, str) and len(password) <= 128 else ""
        with closing(self._db()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            attempt = db.execute("SELECT * FROM attempts WHERE name=?", (name,)).fetchone()
            if attempt and attempt["until"] > self.clock():
                raise PermissionError("Sign-in temporarily locked. Wait a few minutes and try again.")
            row = db.execute("SELECT * FROM users WHERE name=?", (name,)).fetchone()
            salt, iterations = (row["salt"], row["iterations"]) if row else (b"jailwatch-dummy-salt-24!!", ITERATIONS)
            digest = self._digest(password, salt, iterations)
            valid = row is not None and hmac.compare_digest(digest, row["digest"]) and row["enabled"]
            if not valid:
                failures = (attempt["failures"] if attempt else 0) + 1
                delay = min(300, 30 * 2 ** min(4, failures - 5)) if failures >= 5 else 0
                db.execute("INSERT OR REPLACE INTO attempts VALUES(?,?,?)", (name, failures, self.clock()+delay))
                db.execute("DELETE FROM attempts WHERE name IN (SELECT name FROM attempts ORDER BY until DESC LIMIT -1 OFFSET 1000)")
                self._audit(db, name, "sign-in failed")
            else:
                db.execute("DELETE FROM attempts WHERE name=?", (name,))
                self._audit(db, name, "signed in")
        if not valid:
            raise PermissionError("Incorrect username or password, or account disabled.")
        session = Session(secrets.token_urlsafe(32), row["name"], row["role"])
        self.sessions[session.token] = (session, row["revision"], float("inf"))
        return session

    def require(self, session, admin=False):
        record = self.sessions.get(getattr(session, "token", ""))
        if not record or record[0] != session or record[2] <= self.clock():
            raise PermissionError("Your session has ended. Sign in again.")
        with closing(self._db()) as db:
            row = db.execute("SELECT * FROM users WHERE name=?", (session.username,)).fetchone()
        if not row or not row["enabled"] or row["revision"] != record[1] or row["role"] != session.role:
            self.sessions.pop(session.token, None)
            raise PermissionError("Your account changed. Sign in again.")
        if admin and session.role != "admin":
            raise PermissionError("An administrator account is required for this action.")
        return session

    def logout(self, session):
        if self.sessions.pop(getattr(session, "token", ""), None):
            with closing(self._db()) as db, db:
                self._audit(db, session.username, "signed out")

    def accounts(self, session):
        self.require(session, admin=True)
        with closing(self._db()) as db:
            return [dict(r) for r in db.execute("SELECT name,role,enabled FROM users ORDER BY name")]

    def create_account(self, session, name, password, role="operator"):
        self.require(session, admin=True)
        name = self._name(name)
        with closing(self._db()) as db, db:
            self._insert(db, name, password, role)
            self._audit(db, session.username, "account created", name)

    def set_enabled(self, session, name, enabled):
        self.require(session, admin=True)
        name = self._name(name)
        if name == session.username and not enabled:
            raise ValueError("You cannot disable the account you are using.")
        with closing(self._db()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM users WHERE name=?", (name,)).fetchone()
            if not row:
                raise ValueError("Account not found.")
            admins = db.execute("SELECT COUNT(*) FROM users WHERE enabled=1 AND role='admin'").fetchone()[0]
            if not enabled and row["enabled"] and row["role"] == "admin" and admins <= 1:
                raise ValueError("Keep at least one enabled administrator.")
            db.execute("UPDATE users SET enabled=?,revision=revision+1 WHERE name=?", (int(bool(enabled)), name))
            self._audit(db, session.username, "account enabled" if enabled else "account disabled", name)

    def change_password(self, session, old, new):
        self.require(session)
        self._password(new)
        # Use the normal persistent lockout path for re-authentication.
        proof = self.authenticate(session.username, old)
        self.logout(proof)
        salt = secrets.token_bytes(24)
        with closing(self._db()) as db, db:
            db.execute("UPDATE users SET salt=?,digest=?,iterations=?,revision=revision+1 WHERE name=?",
                       (salt, self._digest(new, salt), ITERATIONS, session.username))
            self._audit(db, session.username, "password changed", session.username)
        self.logout(session)
        return self.authenticate(session.username, new)
