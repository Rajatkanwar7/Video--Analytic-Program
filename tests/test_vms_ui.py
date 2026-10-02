import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


@unittest.skipUnless(sys.platform=="win32" or os.environ.get("DISPLAY"),"Desktop display unavailable")
class VMSDesktopTests(unittest.TestCase):
    def setUp(self):
        from jailwatch.vms.ui import VMSApp
        self.tmp = tempfile.TemporaryDirectory()
        from jailwatch.vms.auth import AuthStore
        self.auth=AuthStore(self.tmp.name)
        self.session=self.auth.bootstrap("admin","A local test passphrase")
        self.app = VMSApp(self.tmp.name,auth=self.auth,session=self.session)
        self.app.update()

    def tearDown(self):
        self.app.manager.close()
        self.app.after_cancel(self.app.poll_id)
        self.app.destroy()
        self.tmp.cleanup()

    def test_vms_navigation_and_operator_alarm_are_persistent(self):
        self.assertEqual(set(self.app.pages),{"Live view","Devices","Recordings","Alarms","Settings"})
        for page in self.app.pages:
            self.app.show_page(page); self.app.update()
            self.assertEqual(self.app.page_title.get(),page)
        self.app.test_alarm()
        rows = self.app.events.list()
        self.assertEqual(rows[0]["kind"],"system_test")
        self.assertIn("SYSTEM TEST",self.app.alarm_banner.cget("text"))

    def test_small_screen_keeps_alarm_and_actions_inside_the_window(self):
        self.app.geometry("992x648+0+0")
        self.app.update()
        for page,toolbar in [("Live view",self.app.live_controls),("Devices",self.app.device_controls)]:
            self.app.show_page(page); self.app.update()
            for button in toolbar.buttons:
                self.assertTrue(button.winfo_viewable())
                self.assertLessEqual(button.winfo_x()+button.winfo_width(),toolbar.winfo_width())
                self.assertLessEqual(button.winfo_y()+button.winfo_height(),toolbar.winfo_height())
        self.app.show_page("Live view"); self.app.update()
        self.assertTrue(self.app.alarm_banner.winfo_viewable())
        self.assertLessEqual(self.app.alarm_banner.winfo_rooty()+self.app.alarm_banner.winfo_height(),self.app.winfo_rooty()+self.app.winfo_height())
        self.assertGreater(self.app.grid_frame.winfo_height(),100)

    def test_cancel_close_keeps_active_monitoring_open(self):
        with patch.dict(self.app.manager.workers,{"active":object()}), \
             patch.object(self.app.manager,"running",return_value=True), \
             patch("jailwatch.vms.ui.messagebox.askyesno",return_value=False) as confirm:
            self.app.close_app()
            confirm.assert_called_once()
        self.assertFalse(self.app.closing)
        self.assertTrue(self.app.winfo_exists())

    def test_camera_form_saves_rtsp_and_grid_selection_survives_layout_changes(self):
        from jailwatch.vms.ui import CameraDialog
        dialog = CameraDialog(self.app)
        dialog.tabs.select(1); self.app.update()
        dialog.name.set("North wall")
        dialog.source.set("rtsp://operator:password@192.0.2.1/stream")
        dialog.tabs.select(2); self.app.update()
        with patch("jailwatch.vms.ui.messagebox.showerror") as error:
            dialog.save()
            error.assert_not_called()
        self.assertEqual(len(self.app.inventory.cameras),1)
        selected = self.app.selected_id
        for count in ("1","9","16","4"):
            self.app.layout.set(count); self.app.rebuild_grid(); self.app.update()
            self.assertIn(selected,self.app.tiles)
        self.assertNotIn("password",str(self.app.device_tree.item(selected,"values")))

    def test_recording_playback_window_opens_and_releases_its_file(self):
        from jailwatch.vms.devices import Camera
        from jailwatch.vms.recording import Recorder
        from jailwatch.vms.playback import Playback
        from test_vms_recording import make_video
        source = Path(self.tmp.name)/"source.avi"; make_video(source)
        camera = Camera(name="Playback test"); camera.config.source = str(source)
        recorder = Recorder(camera,self.app.recordings,self.app.inventory.preferences)
        recorder.desired = True; recorder.tick()
        time.sleep(1.5); recorder.stop()
        row = self.app.recordings.list()[0]
        player = Playback(self.app,self.app.recordings,row)
        try:
            self.app.update(); time.sleep(.2); self.app.update()
            self.assertIn(row["path"],self.app.recordings.pinned)
        finally:
            player.close()
            player.worker.join(timeout=3)

    def test_operator_can_review_but_cannot_edit_devices(self):
        self.auth.create_account(self.session,'operator','Operator test passphrase')
        self.app.session=self.auth.authenticate('operator','Operator test passphrase')
        with patch('jailwatch.vms.ui.messagebox.showerror') as error, patch('jailwatch.vms.ui.CameraDialog') as dialog:
            self.app.add_camera()
            error.assert_called_once(); dialog.assert_not_called()
        self.app.test_alarm()
        self.assertEqual(len(self.app.events.list()),1)

    def test_silent_review_cannot_hide_an_older_real_alarm(self):
        from jailwatch.rules import Candidate
        self.app.test_alarm()
        self.app.events.add(Candidate('suspected_throw',1,1,(.4,.4,.5,.5),[],'Silent review'),
                            'Wall','run',details={'notify':False,'direction':'inside_to_outside'})
        self.app.refresh_alarms()
        self.assertIn('SYSTEM TEST',self.app.alarm_banner.cget('text'))
        rows=self.app.events.list()
        self.assertEqual(self.app.alarm_tree.set(rows[0]['id'],'priority'),'Silent review')

    def test_saved_cameras_reconnect_after_authenticated_open(self):
        from jailwatch.vms.devices import Camera
        from jailwatch.vms.ui import VMSApp
        for name in ('North','South'):
            c=Camera(name=name); c.config.source='rtsp://192.0.2.1/test'
            self.app.inventory.put(c)
        self.app.manager.close(); self.app.after_cancel(self.app.poll_id); self.app.destroy()
        session=self.auth.authenticate('admin','A local test passphrase')
        with patch('jailwatch.vms.engine.MonitorManager.start') as start:
            self.app=VMSApp(self.tmp.name,auth=self.auth,session=session)
            end=time.monotonic()+.55
            while time.monotonic()<end:
                self.app.update(); time.sleep(.02)
            self.assertEqual(start.call_count,2)
            self.assertEqual(len(self.app.tiles),2)


@unittest.skipUnless(sys.platform=='win32' or os.environ.get('DISPLAY'),'Desktop display unavailable')
class LoginDesktopTests(unittest.TestCase):
    def test_setup_then_login_opens_only_after_valid_credentials(self):
        from jailwatch.vms.auth import AuthStore
        from jailwatch.vms.login import LoginWindow
        from jailwatch.vms.ui import VMSApp
        with tempfile.TemporaryDirectory() as root:
            auth=AuthStore(root)
            with self.assertRaises(PermissionError): VMSApp(root)
            login=LoginWindow(auth)
            try:
                login.update()
                self.assertLessEqual(login.submit_button.winfo_y()+login.submit_button.winfo_height(),login.submit_button.master.winfo_height())
                login.username.set('admin'); login.password.set('Login test passphrase'); login.confirm.set('Login test passphrase')
                login.submit()
                self.assertIsNotNone(login.session)
            finally:
                try: login.destroy()
                except Exception: pass
            auth.logout(login.session)
            login=LoginWindow(auth)
            try:
                self.assertFalse(login.setup)
                login.username.set('admin'); login.password.set('wrong'); login.submit()
                self.assertIsNone(login.session)
                login.password.set('Login test passphrase'); login.submit()
                auth.require(login.session)
            finally:
                try: login.destroy()
                except Exception: pass
