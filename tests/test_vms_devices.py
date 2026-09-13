import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit,unquote

from jailwatch.vms.devices import Camera,DataLock,Inventory,Preferences,protect,redacted_source,stream_url


class DeviceTests(unittest.TestCase):
    def test_two_running_apps_cannot_write_the_same_inventory(self):
        with tempfile.TemporaryDirectory() as root:
            first=DataLock(root)
            try:
                with self.assertRaisesRegex(ValueError,"already using"):
                    DataLock(root)
            finally:
                first.close()
            second=DataLock(root); second.close()

    def test_rtsp_builder_encodes_credentials_and_ipv6(self):
        uri=stream_url("2001:db8::1",554,"Streaming/Channels/101","operator","p@ss:/?#")
        parsed=urlsplit(uri)
        self.assertEqual(parsed.hostname,"2001:db8::1")
        self.assertEqual(unquote(parsed.password),"p@ss:/?#")
        self.assertEqual(parsed.path,"/Streaming/Channels/101")
        with self.assertRaises(ValueError):
            stream_url("http://camera",554,"stream")

    def test_inventory_persists_without_exposing_windows_password(self):
        with tempfile.TemporaryDirectory() as root:
            inventory=Inventory(root)
            camera=Camera(name="North gate")
            camera.config.source="rtsp://operator:private_password@192.0.2.1/stream"
            inventory.put(camera)
            payload=Path(root,"devices.json").read_text()
            if sys.platform=="win32":
                self.assertNotIn("private_password",payload)
                self.assertIn("windows-dpapi",payload)
            restored=Inventory(root)
            self.assertEqual(restored.cameras[0].config.source,camera.config.source)
            self.assertEqual(restored.cameras[0].id,camera.id)
            destination=Path(root,"export.json"); inventory.export_redacted(destination)
            self.assertNotIn("192.0.2.1",destination.read_text())
            self.assertNotIn("private_password",destination.read_text())

    def test_duplicate_names_and_analytics_without_zones_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            inventory=Inventory(root)
            camera=Camera(name="Gate"); camera.config.source="rtsp://192.0.2.1/stream"
            inventory.put(camera)
            second=Camera(name="GATE"); second.config.source="rtsp://192.0.2.2/stream"
            with self.assertRaisesRegex(ValueError,"different camera name"):
                inventory.put(second)
            camera.analytics=True
            with self.assertRaises(ValueError):
                inventory.put(camera)
            self.assertEqual(len(Inventory(root).cameras),1)

    def test_corrupt_inventory_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root,"devices.json"); path.write_text('{"version":99}')
            with self.assertRaises(ValueError):
                Inventory(root)
            self.assertEqual(json.loads(path.read_text())["version"],99)

    def test_windows_secrets_are_not_silently_read_as_plaintext_elsewhere(self):
        with self.assertRaises(ValueError):
            protect({"format":"unsupported","value":"abc"},decrypt=True)

    def test_display_source_removes_credentials_and_query_tokens(self):
        display=redacted_source("rtsp://user:password@192.0.2.1:554/stream?token=secret")
        self.assertEqual(display,"rtsp://192.0.2.1:554/stream")
        with self.assertRaises(ValueError):
            Preferences(max_live=17).validate()
