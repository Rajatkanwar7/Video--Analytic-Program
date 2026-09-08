"""Export original-resolution frames for human annotation; never invent labels."""
import argparse
import csv
import math
import re
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def extract(video, output, group, fps=2, start=0, end=None, limit=3000):
    from jailwatch.capture import VideoSource
    from jailwatch.config import Config
    import cv2
    if not Path(video).is_file():
        raise ValueError("Choose a local video file.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}",group):
        raise ValueError("Group name must use letters, numbers, underscores and hyphens.")
    if not math.isfinite(fps) or not 0 < fps <= 120 or not math.isfinite(start) or start < 0:
        raise ValueError("FPS must be between 0 and 120; start time must be nonnegative.")
    if end is not None and (not math.isfinite(end) or end <= start):
        raise ValueError("End time must be after the start time.")
    if not 1 <= limit <= 100000:
        raise ValueError("Frame limit must be between 1 and 100000.")
    reader = VideoSource(str(Path(video).resolve()),Config()).open()
    count,next_time = 0,start
    directory = Path(output)/group
    try:
        directory.mkdir(parents=True,exist_ok=False)
        with (directory/"frames.csv").open("w",newline="",encoding="utf-8") as out:
            writer = csv.writer(out)
            writer.writerow(["image","group_id","source_time_seconds","source_frame","annotation_status"])
            while count < limit:
                frame = reader.read()
                if frame is None:
                    if reader.ended:
                        break
                    continue
                if end is not None and frame.time > end:
                    break
                if frame.time+1e-8 < next_time:
                    continue
                name = f"{group}_{frame.index:08d}.jpg"
                if not cv2.imwrite(str(directory/name),frame.image,[cv2.IMWRITE_JPEG_QUALITY,95]):
                    raise OSError("Cannot save extracted frame.")
                writer.writerow([name,group,round(frame.time,6),frame.index,"needs_human_annotation"])
                count += 1
                next_time = start+count/fps
    finally:
        reader.close()
    if count == 0:
        raise ValueError("No frames extracted. Check the video and selected times.")
    return {"frames":count,"directory":str(directory),"limit_reached":count==limit,"labels_created":False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--video",required=True)
    p.add_argument("--output",default="local/annotation_frames")
    p.add_argument("--group",required=True,help="Recording/day group; keep the entire group in one data split")
    p.add_argument("--fps",type=float,default=2)
    p.add_argument("--start",type=float,default=0)
    p.add_argument("--end",type=float)
    p.add_argument("--limit",type=int,default=3000)
    args = p.parse_args(argv)
    try:
        print(extract(args.video,args.output,args.group,args.fps,args.start,args.end,args.limit))
        print("Frames are unlabelled. Annotate them before training; do not mark unknown frames as negatives.")
    except (ValueError,OSError) as exc:
        p.error(str(exc))


if __name__ == "__main__":
    main()
