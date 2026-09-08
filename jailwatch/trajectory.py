"""Measured image-plane paths, never a predicted landing point or physical speed."""
from __future__ import annotations

import math


def trajectory_stats(points, image_size=None):
    points = [tuple(float(v) for v in row) for row in points]
    if any(len(row) != 3 or not all(math.isfinite(v) for v in row) for row in points):
        raise ValueError("Trajectory samples must contain finite time, x and y values.")
    if any(t < 0 or not 0 <= x <= 1 or not 0 <= y <= 1 for t, x, y in points):
        raise ValueError("Trajectory coordinates must be normalized and times nonnegative.")
    if any(b[0] <= a[0] for a, b in zip(points, points[1:])):
        raise ValueError("Trajectory sample times must increase.")
    duration = points[-1][0] - points[0][0] if len(points) > 1 else 0.0
    length = sum(math.hypot(b[1]-a[1], b[2]-a[2]) for a,b in zip(points,points[1:]))
    dx = points[-1][1]-points[0][1] if points else 0.0
    dy = points[-1][2]-points[0][2] if points else 0.0
    displacement = math.hypot(dx, dy)
    result = {"sample_count": len(points), "duration_seconds": duration,
              "path_length_image_fraction": length,
              "displacement_image_fraction": displacement,
              "mean_speed_image_fraction_per_second": length/duration if duration else 0.0,
              "net_to_path_ratio": displacement/length if length else 0.0,
              "horizontal_direction": "right" if dx > 0 else "left" if dx < 0 else "stationary",
              "vertical_direction": "down" if dy > 0 else "up" if dy < 0 else "stationary"}
    if image_size:
        w,h = image_size
        pixels = sum(math.hypot((b[1]-a[1])*w, (b[2]-a[2])*h) for a,b in zip(points,points[1:]))
        result["mean_speed_pixels_per_second"] = pixels/duration if duration else 0.0
    return result


def visible_trails(tracks, timestamp, duration, max_gap, *, corridor_only=False):
    trails = []
    for track in tracks.values():
        if not track.history or not 0 <= timestamp-track.history[-1].time <= max_gap:
            continue
        if corridor_only and track.outside_start is None and not track.fired:
            continue
        points = [(o.time, *o.point) for o in track.history if timestamp-o.time <= duration]
        if len(points) >= 2:
            trails.append((track.id, points, track.history[-1].box))
    return trails


def draw_trail(image, points, color, label="", box=None):
    import cv2
    import numpy as np
    h,w = image.shape[:2]
    pixels = np.array([(min(w-1,max(0,round(x*w))), min(h-1,max(0,round(y*h))))
                       for _,x,y in points], np.int32)
    if len(pixels) < 2:
        return
    cv2.polylines(image, [pixels], False, color, 2, cv2.LINE_AA)
    cv2.circle(image, tuple(pixels[0]), 3, color, -1)
    # Use the last distinct observation for direction, avoiding zero-length arrows.
    end = tuple(pixels[-1])
    start = next((tuple(p) for p in reversed(pixels[:-1]) if tuple(p) != end), None)
    if start:
        cv2.arrowedLine(image, start, end, color, 2, cv2.LINE_AA, tipLength=.35)
    if box:
        x1,y1,x2,y2 = box
        cv2.rectangle(image,(round(x1*w),round(y1*h)),(round(x2*w),round(y2*h)),color,1)
    if label:
        cv2.putText(image,label,(max(2,min(end[0]+8,w-160)),max(20,end[1]-10)),
                    cv2.FONT_HERSHEY_SIMPLEX,.45,color,1,cv2.LINE_AA)
