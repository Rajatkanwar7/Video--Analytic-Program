"""Check local YOLO labels and exact-image/group leakage before training."""
from __future__ import annotations

import csv
import hashlib
import math
from pathlib import Path


def check_dataset(data_file, groups_file=None, require_test=False):
    import yaml
    from PIL import Image
    data_file = Path(data_file).resolve()
    try:
        data = yaml.safe_load(data_file.read_text(encoding="utf-8-sig"))
    except yaml.YAMLError as exc:
        raise ValueError("Invalid dataset YAML. Check its indentation and values.") from exc
    if not isinstance(data,dict) or set(data)-{"path","train","val","test","names","nc"}:
        raise ValueError("Use a local YAML with path, train, val, test and names; download scripts are not allowed.")
    names = data.get("names")
    if isinstance(names,list):
        names = dict(enumerate(names))
    if names != {0:"person",1:"bird",2:"thrown_object"}:
        raise ValueError("Use classes 0: person, 1: bird, 2: thrown_object.")
    if "nc" in data and data["nc"] != 3:
        raise ValueError("The dataset must declare exactly 3 classes.")
    root_value = data.get("path",str(data_file.parent))
    if not isinstance(root_value,str) or not root_value.strip():
        raise ValueError("Dataset path must be a local folder path.")
    root = Path(root_value)
    if not root.is_absolute():
        root = data_file.parent/root
    root = root.resolve()
    errors,warnings,seen,images,counts = [],[],{},{},{}
    resolved = {"path":str(root),"names":names}
    suffixes = {".jpg",".jpeg",".png",".bmp",".webp",".tif",".tiff"}
    for split in ("train","val","test"):
        location = data.get(split)
        if not location:
            if split != "test" or require_test:
                errors.append(f"Missing {split} image directory.")
            continue
        if not isinstance(location,str):
            errors.append(f"{split}: supply one local images directory."); continue
        folder = (root/location).resolve()
        if not folder.is_dir() or not folder.is_relative_to(root/"images"):
            errors.append(f"{split}: use an existing directory beneath {root/'images'}."); continue
        resolved[split] = str(folder)
        paths = sorted(p for p in folder.rglob("*") if p.suffix.lower() in suffixes and p.is_file())
        stats = {"images":len(paths),"negative_images":0,"objects":{n:0 for n in names.values()},"tiny_objects_under_8px":0}
        counts[split] = stats
        if not paths:
            errors.append(f"{split}: no images found.")
        for path in paths:
            relative = path.relative_to(root).as_posix()
            images[relative] = split
            try:
                with Image.open(path) as image:
                    width,height = image.size
                    image.verify()
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if digest in seen:
                    other_split,other_path = seen[digest]
                    message = f"Duplicate image: {relative} and {other_path}."
                    (errors if other_split != split else warnings).append(message)
                else:
                    seen[digest] = (split,relative)
            except (OSError,ValueError):
                errors.append(f"Unreadable image: {relative}"); continue
            label = root/"labels"/path.relative_to(root/"images").with_suffix(".txt")
            if not label.is_file():
                errors.append(f"Missing reviewed label: {label.relative_to(root)}. An empty file is required for a confirmed negative.")
                continue
            lines = [line.split() for line in label.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
            if not lines:
                stats["negative_images"] += 1
            for number,values in enumerate(lines,1):
                try:
                    if len(values) != 5:
                        raise ValueError()
                    category = int(values[0]); x,y,bw,bh = map(float,values[1:])
                    if (category not in names or not all(math.isfinite(v) for v in (x,y,bw,bh)) or
                            min(bw,bh) <= 0 or x-bw/2 < -1e-6 or y-bh/2 < -1e-6 or
                            x+bw/2 > 1+1e-6 or y+bh/2 > 1+1e-6):
                        raise ValueError()
                    stats["objects"][names[category]] += 1
                    stats["tiny_objects_under_8px"] += int(min(bw*width,bh*height) < 8)
                except ValueError:
                    errors.append(f"Invalid class or normalized box: {label.relative_to(root)}, line {number}.")
        if split in ("train","val"):
            for name,total in stats["objects"].items():
                if not total:
                    errors.append(f"{split}: no labeled {name} objects. Collect and label this class before training.")
        if not stats["negative_images"]:
            warnings.append(f"{split}: no confirmed negative frames; include normal activity and difficult backgrounds.")
    if groups_file:
        group_splits,covered = {},set()
        with Path(groups_file).open(encoding="utf-8-sig",newline="") as f:
            for row in csv.DictReader(f):
                key = row.get("image","").replace("\\","/")
                group = row.get("group_id","").strip()
                if key not in images or not group:
                    errors.append(f"Invalid group manifest row: {key}"); continue
                if key in covered:
                    errors.append(f"Duplicate group manifest row: {key}")
                covered.add(key)
                split = images[key]
                if group in group_splits and group_splits[group] != split:
                    errors.append(f"Recording/day group {group} appears in more than one split.")
                group_splits[group] = split
        if set(images)-covered:
            errors.append(f"Group manifest is missing {len(set(images)-covered)} images.")
    else:
        warnings.append("No group manifest supplied. Exact duplicates were checked; related frames from one incident/day may still leak across splits.")
    return {"valid":not errors,"errors":errors,"warnings":warnings,"splits":counts,"resolved_data":resolved}
