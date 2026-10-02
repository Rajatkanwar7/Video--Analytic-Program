import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from jailwatch.vms.auth import AuthStore, Session

PASSPHRASE = 'Local test passphrase 42!'


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.now = 1000
        self.auth = AuthStore(self.tmp.name,clock=lambda: self.now)
        self.admin = self.auth.bootstrap('admin',PASSPHRASE)

    def test_no_default_password_and_setup_cannot_be_repeated(self):
        self.assertFalse(self.auth.needs_setup())
        with self.assertRaises(PermissionError): self.auth.bootstrap('other',PASSPHRASE)
        with self.assertRaises(PermissionError): self.auth.authenticate('admin','admin')
        self.assertEqual(self.auth.authenticate('ADMIN',PASSPHRASE).role,'admin')

    def test_passwords_salted_and_not_stored_in_plaintext(self):
        self.auth.create_account(self.admin,'operator',PASSPHRASE)
        with sqlite3.connect(self.auth.path) as db:
            rows=db.execute('SELECT salt,digest,iterations FROM users ORDER BY name').fetchall()
        self.assertNotEqual(rows[0][0],rows[1][0]); self.assertNotEqual(rows[0][1],rows[1][1])
        self.assertGreaterEqual(rows[0][2],600000)
        self.assertNotIn(PASSPHRASE.encode(),self.auth.path.read_bytes())

    def test_lockout_persists_across_restart(self):
        for _ in range(5):
            with self.assertRaises(PermissionError): self.auth.authenticate('admin','wrong')
        restarted=AuthStore(self.tmp.name,clock=lambda:self.now)
        with self.assertRaisesRegex(PermissionError,'locked'): restarted.authenticate('admin',PASSPHRASE)
        self.now+=31
        self.assertEqual(restarted.authenticate('admin',PASSPHRASE).role,'admin')

    def test_operator_cannot_manage_accounts_or_forge_admin_session(self):
        self.auth.create_account(self.admin,'operator',PASSPHRASE)
        operator=self.auth.authenticate('operator',PASSPHRASE)
        with self.assertRaises(PermissionError): self.auth.create_account(operator,'attack',PASSPHRASE,'admin')
        with self.assertRaises(PermissionError): self.auth.require(replace(operator,role='admin'),admin=True)
        with self.assertRaises(PermissionError): self.auth.require(Session('invented','admin','admin'))
        self.auth.require(operator)

    def test_disabling_account_revokes_existing_session(self):
        self.auth.create_account(self.admin,'operator',PASSPHRASE)
        operator=self.auth.authenticate('operator',PASSPHRASE)
        self.auth.set_enabled(self.admin,'operator',False)
        with self.assertRaises(PermissionError): self.auth.require(operator)
        with self.assertRaises(PermissionError): self.auth.authenticate('operator',PASSPHRASE)
        self.auth.set_enabled(self.admin,'operator',True)
        self.auth.require(self.auth.authenticate('operator',PASSPHRASE))

    def test_current_administrator_cannot_be_disabled(self):
        with self.assertRaises(ValueError): self.auth.set_enabled(self.admin,'admin',False)
        self.auth.require(self.admin,admin=True)

    def test_password_change_revokes_other_sessions(self):
        other=self.auth.authenticate('admin',PASSPHRASE)
        new=self.auth.change_password(self.admin,PASSPHRASE,'A changed test passphrase')
        with self.assertRaises(PermissionError): self.auth.require(other)
        with self.assertRaises(PermissionError): self.auth.require(self.admin)
        self.auth.require(new)
        with self.assertRaises(PermissionError): self.auth.authenticate('admin',PASSPHRASE)

    def test_logout_and_restart_do_not_remember_a_login(self):
        self.auth.logout(self.admin)
        with self.assertRaises(PermissionError): self.auth.require(self.admin)
        with self.assertRaises(PermissionError): AuthStore(self.tmp.name).require(self.admin)

    def test_short_password_and_duplicate_username_rejected(self):
        with self.assertRaises(ValueError): self.auth.create_account(self.admin,'operator','short')
        with self.assertRaises(ValueError): self.auth.create_account(self.admin,'ADMIN',PASSPHRASE)

    def test_corrupt_account_database_fails_closed(self):
        path=Path(self.tmp.name)/'broken'; path.mkdir()
        (path/'accounts.sqlite3').write_bytes(b'not a sqlite database')
        with self.assertRaises(sqlite3.DatabaseError): AuthStore(path)
