"""Train only after assembling a labeled, camera-separated dataset; no footage is uploaded."""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="Local Ultralytics dataset YAML")
    parser.add_argument("--weights", default="models/yolo11n.pt")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--image-size", type=int, default=1280)
    args = parser.parse_args()
    if not Path(args.data).is_file() or not Path(args.weights).is_file():
        parser.error("Local dataset YAML and model weights must exist.")
    from ultralytics import YOLO
    model = YOLO(args.weights)
    model.train(data=args.data, epochs=args.epochs, imgsz=args.image_size, device=args.device,
                project="training_runs", name="perimeter", exist_ok=False)


if __name__ == "__main__":
    main()
