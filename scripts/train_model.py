"""Check labels, train locally, or evaluate a custom detector on held-out images."""
import argparse
import json
import re
import sys
from datetime import datetime,timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jailwatch.training_data import check_dataset


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, help="Local dataset YAML")
    parser.add_argument("--groups",help="Optional image,group_id CSV to enforce recording/day separation")
    parser.add_argument("--check-data",action="store_true",help="Check data without loading AI or training")
    parser.add_argument("--mode",choices=["train","validate","test"],default="train")
    parser.add_argument("--weights", default="models/yolo11n.pt")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--patience",type=int,default=20)
    parser.add_argument("--batch",type=int,default=4)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--image-size", type=int, default=1280)
    parser.add_argument("--seed",type=int,default=42)
    parser.add_argument("--project",default="training_runs")
    parser.add_argument("--name",default=datetime.now(timezone.utc).strftime("perimeter_%Y%m%d_%H%M%S"))
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.epochs <= 10000 or not 1 <= args.batch <= 256 or not 1 <= args.patience <= 1000:
            raise ValueError("Use positive epochs, patience and batch size within the documented limits.")
        if not 320 <= args.image_size <= 1920 or args.image_size % 32:
            raise ValueError("Image size must be a multiple of 32 between 320 and 1920.")
        if not 0 <= args.seed <= 2147483647:
            raise ValueError("Seed must be between 0 and 2147483647.")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}",args.name):
            raise ValueError("Run name must use letters, numbers, underscores and hyphens.")
        report = check_dataset(args.data,args.groups,require_test=args.mode=="test")
        print(json.dumps(report,indent=2))
        if not report["valid"]:
            raise ValueError("Dataset checks failed. Correct the listed errors before training.")
        if args.check_data:
            return 0
        if not Path(args.weights).is_file():
            raise ValueError("Local model weights are required. Use Download model or supply a trusted .pt file.")
        from ultralytics import YOLO
        import yaml
        model = YOLO(str(Path(args.weights).resolve()),task="detect")
        if args.mode != "train" and model.names != {0:"person",1:"bird",2:"thrown_object"}:
            raise ValueError("Image validation requires custom weights with person, bird and thrown_object in that order.")
        directory = Path(args.project).resolve()/args.name
        directory.mkdir(parents=True,exist_ok=False)
        data_file = directory/"dataset.resolved.yaml"
        data_file.write_text(yaml.safe_dump(report["resolved_data"],sort_keys=False),encoding="utf-8")
        (directory/"dataset_checks.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
        (directory/"settings.json").write_text(json.dumps(vars(args),indent=2)+"\n",encoding="utf-8")
        if args.mode == "train":
            model.train(data=str(data_file),epochs=args.epochs,imgsz=args.image_size,device=args.device,
                        batch=args.batch,patience=args.patience,seed=args.seed,deterministic=True,
                        workers=0,close_mosaic=min(10,args.epochs),mosaic=.5,scale=.3,
                        project=str(directory),name="fit",exist_ok=False)
            print(f"Training finished. Review validation results before selecting {model.trainer.best} in Camera setup.")
        else:
            result = model.val(data=str(data_file),split="test" if args.mode=="test" else "val",
                               imgsz=args.image_size,batch=args.batch,device=args.device,workers=0,
                               project=str(directory),name="evaluation",plots=True)
            metrics = {key:float(value) for key,value in result.results_dict.items()}
            metrics["meaning"] = "Bounding-box metrics only; separately evaluate complete throwing and bird videos."
            (directory/"metrics.json").write_text(json.dumps(metrics,indent=2)+"\n",encoding="utf-8")
            print(json.dumps(metrics,indent=2))
        return 0
    except (ValueError,OSError,KeyError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
