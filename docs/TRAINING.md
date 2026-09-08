# Improving bird and small-object recognition

YOLO11 is a generic detector. Three videos described as containing throws do not provide enough labels or bird negatives to measure reliable discrimination. No jail-specific model has been trained for this repository.

1. Mark exact throw intervals, noting when the object is visible and when it is occluded or too small to see.
2. Collect birds and normal activity: people, vegetation, shadows, insects, rain, day/night changes and compression artifacts.
3. Label visible `person`, `bird` and `thrown_object` boxes; retain true-negative frames with empty labels.
4. Split by camera/day/incident into train, validation and test. Adjacent frames of one incident must not leak across splits.
5. Reserve full videos for event-level evaluation, which is different from bounding-box accuracy.

Use the [Ultralytics detection dataset format](https://docs.ultralytics.com/datasets/detect/): a label file per image, with `class x_center y_center width height` normalized to the image. Copy `examples/dataset.example.yaml` and set its local path.

```bash
python scripts/train_model.py --data local/dataset.yaml --weights models/yolo11n.pt --device 0 --epochs 100
```

This invokes local training; the script does not upload footage. Training has not been run here. Select the resulting trusted `best.pt` in Camera setup, preserving `person` and `bird` class names. A `thrown_object` class is supported, but class recognition alone does not bypass the directional crossing rule or operator review.

Tune on validation data, then evaluate on held-out videos. Measure missed throws, bird false alarms, false alarms/hour and alert delay by camera and lighting condition. Synthetic software-test results are not detection accuracy.
