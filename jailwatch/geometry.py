"""Normalized image geometry, independent of camera resolution."""
from __future__ import annotations

import math

Point = tuple[float, float]
Box = tuple[float, float, float, float]


def cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def on_segment(p, a, b):
    return (abs(cross(a, b, p)) < 1e-9 and
            min(a[0], b[0]) - 1e-9 <= p[0] <= max(a[0], b[0]) + 1e-9 and
            min(a[1], b[1]) - 1e-9 <= p[1] <= max(a[1], b[1]) + 1e-9)


def contains(p, polygon, boundary=True):
    if not polygon:
        return False
    inside = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if on_segment(p, a, b):
            return boundary
        if (a[1] > p[1]) != (b[1] > p[1]):
            if p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]:
                inside = not inside
    return inside


def proper_intersection(a, b, c, d):
    return cross(a, b, c) * cross(a, b, d) < -1e-12 and cross(c, d, a) * cross(c, d, b) < -1e-12


def validate_polygon(polygon, name, optional=False):
    if optional and polygon == []:
        return
    if not isinstance(polygon, list) or len(polygon) < 3:
        raise ValueError(f"{name}: draw at least three points.")
    for p in polygon:
        if (not isinstance(p, (tuple, list)) or len(p) != 2 or
                any(isinstance(v, bool) or not isinstance(v, (int, float)) or
                    not math.isfinite(v) or not 0 <= v <= 1 for v in p)):
            raise ValueError(f"{name}: points must be normalized numbers between 0 and 1.")
    if len(set(map(tuple, polygon))) != len(polygon):
        raise ValueError(f"{name}: repeated points are not allowed.")
    edges = list(zip(polygon, polygon[1:] + polygon[:1]))
    area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in edges)) / 2
    if area < 1e-5:
        raise ValueError(f"{name}: area is too small.")
    for i, (a, b) in enumerate(edges):
        for j, (c, d) in enumerate(edges):
            if j <= i + 1 or (i == 0 and j == len(edges) - 1):
                continue
            if (proper_intersection(a, b, c, d) or on_segment(a, c, d) or
                    on_segment(b, c, d) or on_segment(c, a, b) or on_segment(d, a, b)):
                raise ValueError(f"{name}: polygon must not cross itself.")


def polygons_overlap(a, b):
    # Shared boundary is allowed; shared interior is not.
    if any(contains(p, b, False) for p in a) or any(contains(p, a, False) for p in b):
        return True
    ea = list(zip(a, a[1:] + a[:1]))
    eb = list(zip(b, b[1:] + b[:1]))
    if any(proper_intersection(p, q, r, s) for p, q in ea for r, s in eb):
        return True
    # Identical polygons or aligned, overlapping rectangles can have boundary-only vertices.
    for poly, other in ((a, b), (b, a)):
        for p, q in zip(poly, poly[1:] + poly[:1]):
            mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
            if contains(mid, other, False):
                return True
            for dx, dy in ((1e-7, 0), (-1e-7, 0), (0, 1e-7), (0, -1e-7)):
                probe = (mid[0] + dx, mid[1] + dy)
                if contains(probe, poly, False) and contains(probe, other, False):
                    return True
    return False


def center(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def overlap(a, b, margin=0.0):
    return (a[0] <= b[2] + margin and a[2] >= b[0] - margin and
            a[1] <= b[3] + margin and a[3] >= b[1] - margin)


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])
