"""Desktop lifecycle smoke tests run where a real display is available (including Windows CI)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

HAS_DISPLAY = sys.platform == "win32" or bool(os.environ.get("DISPLAY"))


@unittest.skipUnless(HAS_DISPLAY, "Desktop display unavailable")
class DesktopTests(unittest.TestCase):
    def test_setup_and_monitor_widgets_open_and_close(self):
        from jailwatch.config import Config, save_config
        from jailwatch.ui import App
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/"camera.json"
            save_config(Config(data_dir=str(Path(d)/"data")), path)
            app = App(path)
            try:
                app.update()
                self.assertEqual(app.title(), "JailWatch 2.0.1 | CCTV monitor")
                self.assertEqual(len(app.tabs.tabs()), 3)
                self.assertTrue(app.save())
                app.tabs.select(app.setup_tab)
                app.update()
                app.test_alarm()
                rows = app.store.list()
                self.assertEqual(rows[0]["kind"],"system_test")
                self.assertIn('"test_only": true',rows[0]["details"])
            finally:
                app.close_app()

    def test_zone_editor_saves_real_normalized_polygons(self):
        import tkinter as tk
        import numpy as np
        from jailwatch.config import Config
        from jailwatch.ui import ZoneEditor
        root = tk.Tk(); root.withdraw()
        saved = []
        try:
            editor = ZoneEditor(root, np.zeros((360,640,3),np.uint8), Config(), saved.append)
            editor.polygons["outside"] = [[0,0],[.48,0],[.48,1],[0,1]]
            editor.polygons["inside"] = [[.52,0],[1,0],[1,1],[.52,1]]
            editor.redraw(); root.update(); editor.save()
            self.assertEqual(saved[0].calibration_size,[640,360])
            saved[0].validate()
        finally:
            root.destroy()
