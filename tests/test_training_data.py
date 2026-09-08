import csv
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image
import yaml
from jailwatch.training_data import check_dataset


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for i,split in enumerate(("train","val","test")):
            (self.root/"images"/split).mkdir(parents=True)
            (self.root/"labels"/split).mkdir(parents=True)
            Image.new("RGB",(100,100),(i*40+10,60,90)).save(self.root/"images"/split/"objects.png")
            (self.root/"labels"/split/"objects.txt").write_text(
                "0 0.2 0.5 0.1 0.2\n1 0.5 0.5 0.1 0.2\n2 0.8 0.5 0.1 0.2\n")
            Image.new("RGB",(100,100),(i*40+10,10,10)).save(self.root/"images"/split/"negative.png")
            (self.root/"labels"/split/"negative.txt").write_text("")
        self.data=self.root/"dataset.yaml"
        self.data.write_text(yaml.safe_dump({"path":str(self.root),"train":"images/train","val":"images/val",
                            "test":"images/test","names":{0:"person",1:"bird",2:"thrown_object"}}))

    def test_explicit_negatives_and_valid_boxes_are_accepted(self):
        report=check_dataset(self.data,require_test=True)
        self.assertTrue(report["valid"],report["errors"])
        self.assertEqual(report["splits"]["train"]["negative_images"],1)

    def test_missing_labels_are_not_silently_treated_as_negatives(self):
        (self.root/"labels/train/negative.txt").unlink()
        self.assertIn("Missing reviewed label"," ".join(check_dataset(self.data)["errors"]))

    def test_duplicate_images_across_splits_are_rejected(self):
        shutil.copy2(self.root/"images/train/objects.png",self.root/"images/val/objects.png")
        self.assertIn("Duplicate image"," ".join(check_dataset(self.data)["errors"]))

    def test_group_leakage_is_rejected_even_with_different_images(self):
        groups=self.root/"groups.csv"
        with groups.open("w",newline="") as f:
            writer=csv.writer(f); writer.writerow(["image","group_id"])
            for split in ("train","val","test"):
                for image in ("objects","negative"):
                    writer.writerow([f"images/{split}/{image}.png","same_recording"])
        self.assertIn("more than one split"," ".join(check_dataset(self.data,groups)["errors"]))

    def test_invalid_boxes_and_remote_download_commands_are_rejected(self):
        (self.root/"labels/train/objects.txt").write_text("2 0.99 0.5 0.5 0.2\n")
        self.assertIn("Invalid class or normalized box"," ".join(check_dataset(self.data)["errors"]))
        self.data.write_text("download: echo forbidden\n")
        with self.assertRaisesRegex(ValueError,"download scripts"):
            check_dataset(self.data)
