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
        self.app = VMSApp(self.tmp.name)
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
