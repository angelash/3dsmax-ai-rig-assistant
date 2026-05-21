from __future__ import annotations

import argparse
import json
import math
import struct
import zlib
from pathlib import Path
from typing import Any


Color = tuple[int, int, int]
Point3 = list[float]


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)


class Canvas:
    def __init__(self, width: int, height: int, bg: Color = (250, 250, 248)) -> None:
        self.width = width
        self.height = height
        self.pixels = bytearray(bg * width * height)

    def set(self, x: int, y: int, color: Color) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            idx = (y * self.width + x) * 3
            self.pixels[idx : idx + 3] = bytes(color)

    def point(self, x: int, y: int, color: Color, radius: int = 1) -> None:
        for yy in range(y - radius, y + radius + 1):
            for xx in range(x - radius, x + radius + 1):
                if (xx - x) * (xx - x) + (yy - y) * (yy - y) <= radius * radius:
                    self.set(xx, yy, color)

    def line(self, x0: int, y0: int, x1: int, y1: int, color: Color, width: int = 1) -> None:
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.point(x0, y0, color, width)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def save_png(self, path: Path) -> None:
        rows = []
        stride = self.width * 3
        for y in range(self.height):
            row = self.pixels[y * stride : (y + 1) * stride]
            rows.append(b"\x00" + bytes(row))
        raw = b"".join(rows)
        data = (
            b"\x89PNG\r\n\x1a\n"
            + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0))
            + _png_chunk(b"IDAT", zlib.compress(raw, 9))
            + _png_chunk(b"IEND", b"")
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def project(point: Point3, view: str) -> tuple[float, float]:
    if view == "front":
        return point[0], point[2]
    if view == "side":
        return point[1], point[2]
    if view == "top":
        return point[0], point[1]
    raise ValueError(f"unknown view: {view}")


def view_ranges(bounds: dict[str, Point3], view: str) -> tuple[float, float, float, float]:
    mn = bounds["min"]
    mx = bounds["max"]
    corners = [
        [mn[0], mn[1], mn[2]],
        [mn[0], mn[1], mx[2]],
        [mn[0], mx[1], mn[2]],
        [mn[0], mx[1], mx[2]],
        [mx[0], mn[1], mn[2]],
        [mx[0], mn[1], mx[2]],
        [mx[0], mx[1], mn[2]],
        [mx[0], mx[1], mx[2]],
    ]
    coords = [project(corner, view) for corner in corners]
    xs = [coord[0] for coord in coords]
    ys = [coord[1] for coord in coords]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    pad_x = max((max_x - min_x) * 0.10, 1.0)
    pad_y = max((max_y - min_y) * 0.10, 1.0)
    return min_x - pad_x, max_x + pad_x, min_y - pad_y, max_y + pad_y


def mapper(bounds: dict[str, Point3], view: str, width: int, height: int):
    min_x, max_x, min_y, max_y = view_ranges(bounds, view)
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)

    def map_point(point: Point3) -> tuple[int, int]:
        x, y = project(point, view)
        px = int((x - min_x) / span_x * (width - 1))
        py = int((1.0 - (y - min_y) / span_y) * (height - 1))
        return px, py

    return map_point


def guide_color(name: str) -> Color:
    if name == "Root":
        return (116, 132, 150)
    if name.startswith("L_"):
        return (35, 155, 65)
    if name.startswith("R_"):
        return (45, 95, 215)
    if name in {"Root", "Pelvis", "Spine", "Chest", "Neck", "Head", "HeadTop", "CrestTop"}:
        return (218, 154, 22)
    return (190, 60, 60)


def draw_cross(canvas: Canvas, x: int, y: int, color: Color, size: int = 10, width: int = 2) -> None:
    canvas.line(x - size, y, x + size, y, color, width)
    canvas.line(x, y - size, x, y + size, color, width)


def draw_view(
    snapshot: dict[str, Any],
    view: str,
    path: Path,
    analysis: dict[str, Any] | None = None,
    width: int = 1200,
    height: int = 900,
) -> None:
    canvas = Canvas(width, height)
    bounds = snapshot["bounds"]
    to_pixel = mapper(bounds, view, width, height)

    for point in snapshot.get("meshPoints", []):
        x, y = to_pixel(point)
        canvas.point(x, y, (184, 184, 184), 1)

    for bone in snapshot.get("templateBones", []):
        start = bone.get("startPosition")
        end = bone.get("endPosition")
        if start is not None and end is not None:
            x0, y0 = to_pixel(start)
            x1, y1 = to_pixel(end)
            canvas.line(x0, y0, x1, y1, (232, 132, 28), 2)

    for name, point in snapshot.get("guides", {}).items():
        if point is None:
            continue
        x, y = to_pixel(point)
        radius = 4 if name == "Root" else 6
        canvas.point(x, y, guide_color(name), radius)
        canvas.point(x, y, (20, 20, 20), 1 if name == "Root" else 2)

    if analysis is not None:
        for name, coverage in analysis.get("armCoverage", {}).items():
            guide_point = coverage.get("guide")
            target_point = coverage.get("target")
            if guide_point is None or target_point is None:
                continue
            gx, gy = to_pixel(guide_point)
            tx, ty = to_pixel(target_point)
            canvas.line(gx, gy, tx, ty, (150, 74, 196), 2)
            draw_cross(canvas, tx, ty, (150, 74, 196), 8, 2)
            canvas.point(tx, ty, (255, 236, 78), 3)

        for name, coverage in analysis.get("handCoverage", {}).items():
            guide_point = coverage.get("guide")
            target_point = coverage.get("target")
            if guide_point is None or target_point is None:
                continue
            gx, gy = to_pixel(guide_point)
            tx, ty = to_pixel(target_point)
            canvas.line(gx, gy, tx, ty, (214, 52, 52), 2)
            draw_cross(canvas, tx, ty, (214, 52, 52), 10, 2)
            canvas.point(tx, ty, (255, 236, 78), 4)

    canvas.save_png(path)


def nearest_projected_distance(point: Point3, mesh_points: list[Point3], view: str) -> float:
    px, py = project(point, view)
    best = float("inf")
    for mesh_point in mesh_points:
        mx, my = project(mesh_point, view)
        dist = math.hypot(px - mx, py - my)
        if dist < best:
            best = dist
    return best


def percentile(values: list[float], ratio: float, fallback: float) -> float:
    if not values:
        return fallback
    sorted_values = sorted(values)
    idx = int(math.floor((len(sorted_values) - 1) * ratio))
    idx = max(0, min(len(sorted_values) - 1, idx))
    return sorted_values[idx]


def median_point(points: list[Point3], fallback: Point3) -> Point3:
    if not points:
        return fallback
    return [
        percentile([point[0] for point in points], 0.50, fallback[0]),
        percentile([point[1] for point in points], 0.50, fallback[1]),
        percentile([point[2] for point in points], 0.50, fallback[2]),
    ]


def centerline_point(points: list[Point3], fallback: Point3) -> Point3:
    """Trimmed bounding-center for a mesh surface slice.

    Mesh samples describe the surface, while guide joints should sit on the
    centerline of the local limb volume. A trimmed bbox center is less biased
    by uneven vertex density than a raw mean and avoids snapping to silhouette
    extremes.
    """
    if not points:
        return fallback
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    zs = [point[2] for point in points]
    return [
        (percentile(xs, 0.12, fallback[0]) + percentile(xs, 0.88, fallback[0])) / 2.0,
        (percentile(ys, 0.12, fallback[1]) + percentile(ys, 0.88, fallback[1])) / 2.0,
        (percentile(zs, 0.12, fallback[2]) + percentile(zs, 0.88, fallback[2])) / 2.0,
    ]


def distance3d(a: Point3, b: Point3) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def outer_hand_target(
    side: int,
    bounds: dict[str, Point3],
    mesh_points: list[Point3],
    fallback: Point3,
) -> dict[str, Any]:
    center = bounds["center"]
    size = bounds["size"]
    height = max(size[2], 1.0)
    width = max(size[0], 1.0)
    depth = max(size[1], 1.0)
    z0 = bounds["min"][2]

    candidates: list[Point3] = []
    side_values: list[float] = []
    for point in mesh_points:
        side_x = (point[0] - center[0]) * side
        if (
            side_x > width * 0.25
            and center[1] - depth * 0.38 <= point[1] <= center[1] + depth * 0.32
            and z0 + height * 0.25 <= point[2] <= z0 + height * 0.58
        ):
            candidates.append(point)
            side_values.append(side_x)

    if len(candidates) < 8:
        return {
            "target": fallback,
            "candidateCount": len(candidates),
            "outerCount": 0,
            "confidence": "low",
            "note": "Not enough side hand points were found; target fell back to the guide position.",
        }

    cutoff = percentile(side_values, 0.88, width * 0.38)
    outer = [point for point in candidates if (point[0] - center[0]) * side >= cutoff]
    return {
        "target": median_point(outer, fallback),
        "candidateCount": len(candidates),
        "outerCount": len(outer),
        "cutoff": round(cutoff, 6),
        "confidence": "medium" if len(outer) >= 12 else "low",
        "note": "Target is the median of the outer 12% side-hand silhouette points.",
    }


def hand_center_target(
    side: int,
    bounds: dict[str, Point3],
    mesh_points: list[Point3],
    fallback: Point3,
) -> dict[str, Any]:
    center = bounds["center"]
    size = bounds["size"]
    height = max(size[2], 1.0)
    width = max(size[0], 1.0)
    depth = max(size[1], 1.0)
    z0 = bounds["min"][2]

    candidates: list[Point3] = []
    side_values: list[float] = []
    for point in mesh_points:
        side_x = (point[0] - center[0]) * side
        if (
            side_x > width * 0.25
            and center[1] - depth * 0.38 <= point[1] <= center[1] + depth * 0.32
            and z0 + height * 0.25 <= point[2] <= z0 + height * 0.58
        ):
            candidates.append(point)
            side_values.append(side_x)

    if len(candidates) < 8:
        return {
            "target": fallback,
            "candidateCount": len(candidates),
            "centerlineCount": 0,
            "confidence": "low",
            "targetType": "hand_centerline",
            "note": "Not enough side hand points were found; target fell back to the guide position.",
        }

    cutoff = percentile(side_values, 0.70, width * 0.34)
    hand_mass = [point for point in candidates if (point[0] - center[0]) * side >= cutoff]
    return {
        "target": centerline_point(hand_mass, fallback),
        "candidateCount": len(candidates),
        "centerlineCount": len(hand_mass),
        "cutoff": round(cutoff, 6),
        "confidence": "medium" if len(hand_mass) >= 16 else "low",
        "targetType": "hand_centerline",
        "note": "Target is the trimmed center of the outer hand volume, not the silhouette surface.",
    }


def arm_band_target(
    side: int,
    bounds: dict[str, Point3],
    mesh_points: list[Point3],
    side_ratio: float,
    seed_z_ratio: float,
    fallback: Point3,
) -> dict[str, Any]:
    center = bounds["center"]
    size = bounds["size"]
    height = max(size[2], 1.0)
    width = max(size[0], 1.0)
    depth = max(size[1], 1.0)
    z0 = bounds["min"][2]
    target_side_x = width * side_ratio
    tolerance = width * 0.05
    seed_z = z0 + height * seed_z_ratio
    seed_tolerance = height * 0.10

    broad: list[Point3] = []
    local_band: list[Point3] = []
    for point in mesh_points:
        side_x = (point[0] - center[0]) * side
        if (
            abs(side_x - target_side_x) <= tolerance
            and center[1] - depth * 0.45 <= point[1] <= center[1] + depth * 0.40
            and z0 + height * 0.25 <= point[2] <= z0 + height * 0.58
        ):
            broad.append(point)
            if abs(point[2] - seed_z) <= seed_tolerance:
                local_band.append(point)

    candidates = local_band if len(local_band) >= 8 else broad
    if len(candidates) < 8:
        return {
            "target": fallback,
            "candidateCount": len(broad),
            "centerlineCount": len(candidates),
            "confidence": "low",
            "targetType": "arm_centerline",
            "note": "Not enough arm cross-section points were found; target fell back to the guide position.",
        }

    target = centerline_point(candidates, fallback)
    return {
        "target": target,
        "candidateCount": len(broad),
        "centerlineCount": len(candidates),
        "sideRatio": side_ratio,
        "seedZRatio": seed_z_ratio,
        "confidence": "medium" if len(candidates) >= 24 else "low",
        "targetType": "arm_centerline",
        "note": "Target is the trimmed center of the local arm cross-section, not the surface point cloud.",
    }


def add_issue(issues: list[dict[str, Any]], severity: str, code: str, message: str, guide: str | None = None) -> None:
    issues.append({"severity": severity, "code": code, "message": message, "guide": guide or ""})


def analyze(snapshot: dict[str, Any]) -> dict[str, Any]:
    bounds = snapshot["bounds"]
    size = bounds["size"]
    center = bounds["center"]
    height = max(size[2], 1.0)
    width = max(size[0], 1.0)
    depth = max(size[1], 1.0)
    guides: dict[str, Point3 | None] = snapshot.get("guides", {})
    mesh_points: list[Point3] = snapshot.get("meshPoints", [])
    issues: list[dict[str, Any]] = []
    observations: list[str] = []
    guide_distances: dict[str, dict[str, float]] = {}
    hand_coverage: dict[str, dict[str, Any]] = {}
    arm_coverage: dict[str, dict[str, Any]] = {}

    observations.append(
        f"Silhouette ratios: width/height={width / height:.3f}, depth/height={depth / height:.3f}."
    )
    if width / height >= 0.75:
        observations.append("Visual silhouette is compact and wide; standard humanoid proportions are a weak fit.")
    if depth / height >= 0.45:
        observations.append("Side silhouette is deep; pelvis and chest need side-view checking.")

    required = [
        "Root",
        "Pelvis",
        "Spine",
        "Chest",
        "Neck",
        "Head",
        "HeadTop",
        "CrestTop",
        "L_Shoulder",
        "L_Elbow",
        "L_Wrist",
        "L_HandTip",
        "R_Shoulder",
        "R_Elbow",
        "R_Wrist",
        "R_HandTip",
        "L_Hip",
        "L_Knee",
        "L_Ankle",
        "L_Heel",
        "R_Hip",
        "R_Knee",
        "R_Ankle",
        "R_Heel",
    ]
    for name in required:
        point = guides.get(name)
        if point is None:
            add_issue(issues, "error", "missing_guide", f"Missing guide {name}.", name)

    if mesh_points:
        near_threshold = height * 0.08
        far_threshold = height * 0.14
        for name, point in guides.items():
            if point is None:
                continue
            front_distance = nearest_projected_distance(point, mesh_points, "front")
            side_distance = nearest_projected_distance(point, mesh_points, "side")
            guide_distances[name] = {
                "front": round(front_distance, 6),
                "side": round(side_distance, 6),
            }
            if front_distance > far_threshold and side_distance > far_threshold:
                add_issue(
                    issues,
                    "warning",
                    "guide_far_from_silhouette",
                    f"{name} is far from both front and side silhouettes.",
                    name,
                )
            elif front_distance > near_threshold and name in {"Pelvis", "Chest", "Neck", "Head", "L_Hip", "R_Hip"}:
                add_issue(
                    issues,
                    "info",
                    "core_guide_front_offset",
                    f"{name} is visibly offset from the front-view silhouette centerline.",
                    name,
                )

        hand_error_threshold = height * 0.10
        hand_warning_threshold = height * 0.06
        for hand_name, side in [("L_Hand", 1), ("R_Hand", -1)]:
            guide_point = guides.get(hand_name)
            if guide_point is None:
                continue
            target_result = hand_center_target(side, bounds, mesh_points, guide_point)
            target = target_result["target"]
            dist = distance3d(guide_point, target)
            delta = [guide_point[i] - target[i] for i in range(3)]
            coverage_score = max(0, min(100, round(100 - (dist / height) * 500, 3)))
            ready = dist <= hand_warning_threshold and target_result["confidence"] != "low"
            hand_coverage[hand_name] = {
                "guide": [round(v, 6) for v in guide_point],
                "target": [round(v, 6) for v in target],
                "delta": [round(v, 6) for v in delta],
                "distance": round(dist, 6),
                "distanceHeightRatio": round(dist / height, 6),
                "score": coverage_score,
                "ready": ready,
                **target_result,
            }

            if target_result["confidence"] == "low":
                add_issue(
                    issues,
                    "info",
                    "hand_visual_target_low_confidence",
                    f"{hand_name} visual target has low point-cloud confidence.",
                    hand_name,
                )
            elif dist > hand_error_threshold:
                add_issue(
                    issues,
                    "error",
                    "hand_visual_target_mismatch",
                    f"{hand_name} is {dist:.3f} units from the hand centerline target.",
                    hand_name,
                )
            elif dist > hand_warning_threshold:
                add_issue(
                    issues,
                    "warning",
                    "hand_visual_target_offset",
                    f"{hand_name} is {dist:.3f} units from the hand centerline target.",
                    hand_name,
                )

        arm_warning_threshold = height * 0.055
        arm_error_threshold = height * 0.085
        arm_specs = [
            ("L_Shoulder", 1, 0.24, 0.43),
            ("R_Shoulder", -1, 0.24, 0.43),
            ("L_Elbow", 1, 0.32, 0.39),
            ("R_Elbow", -1, 0.32, 0.39),
            ("L_Wrist", 1, 0.42, 0.36),
            ("R_Wrist", -1, 0.42, 0.36),
        ]
        for guide_name, side, side_ratio, seed_z_ratio in arm_specs:
            guide_point = guides.get(guide_name)
            if guide_point is None:
                continue
            target_result = arm_band_target(side, bounds, mesh_points, side_ratio, seed_z_ratio, guide_point)
            target = target_result["target"]
            dist = distance3d(guide_point, target)
            delta = [guide_point[i] - target[i] for i in range(3)]
            coverage_score = max(0, min(100, round(100 - (dist / height) * 350, 3)))
            ready = dist <= arm_warning_threshold and target_result["confidence"] != "low"
            arm_coverage[guide_name] = {
                "guide": [round(v, 6) for v in guide_point],
                "target": [round(v, 6) for v in target],
                "delta": [round(v, 6) for v in delta],
                "distance": round(dist, 6),
                "distanceHeightRatio": round(dist / height, 6),
                "score": coverage_score,
                "ready": ready,
                **target_result,
            }

            if target_result["confidence"] == "low":
                add_issue(
                    issues,
                    "info",
                    "arm_visual_target_low_confidence",
                    f"{guide_name} visual target has low point-cloud confidence.",
                    guide_name,
                )
            elif dist > arm_error_threshold:
                add_issue(
                    issues,
                    "error",
                    "arm_visual_target_mismatch",
                    f"{guide_name} is {dist:.3f} units from the tutorial arm centerline target.",
                    guide_name,
                )
            elif dist > arm_warning_threshold:
                add_issue(
                    issues,
                    "warning",
                    "arm_visual_target_offset",
                    f"{guide_name} is {dist:.3f} units from the tutorial arm centerline target.",
                    guide_name,
                )

    centerline_names = ["Pelvis", "Spine", "Chest", "Neck", "Head", "HeadTop"]
    for name in centerline_names:
        point = guides.get(name)
        if point is not None and abs(point[0] - center[0]) > width * 0.08:
            add_issue(issues, "warning", "centerline_x_offset", f"{name} is offset from the center line.", name)

    ascending_chains = [["Pelvis", "Spine", "Chest", "Neck", "Head", "HeadTop"]]
    for chain in ascending_chains:
        for lower, upper in zip(chain, chain[1:]):
            lower_point = guides.get(lower)
            upper_point = guides.get(upper)
            if lower_point is not None and upper_point is not None and upper_point[2] <= lower_point[2]:
                add_issue(
                    issues,
                    "error",
                    "bad_vertical_order",
                    f"{upper} should be above {lower} in visual projection.",
                    upper,
                )

    descending_chains = [
        ["L_Hip", "L_Knee", "L_Ankle", "L_Heel"],
        ["R_Hip", "R_Knee", "R_Ankle", "R_Heel"],
        ["L_Shoulder", "L_Elbow", "L_Wrist", "L_Hand"],
        ["R_Shoulder", "R_Elbow", "R_Wrist", "R_Hand"],
    ]
    for chain in descending_chains:
        for upper, lower in zip(chain, chain[1:]):
            upper_point = guides.get(upper)
            lower_point = guides.get(lower)
            if upper_point is not None and lower_point is not None and upper_point[2] <= lower_point[2]:
                add_issue(
                    issues,
                    "error",
                    "bad_vertical_order",
                    f"{upper} should be above {lower} in visual projection.",
                    upper,
                )

    for left, right in [
        ("L_Shoulder", "R_Shoulder"),
        ("L_Elbow", "R_Elbow"),
        ("L_Wrist", "R_Wrist"),
        ("L_HandTip", "R_HandTip"),
        ("L_Hip", "R_Hip"),
        ("L_Knee", "R_Knee"),
        ("L_Ankle", "R_Ankle"),
        ("L_Heel", "R_Heel"),
    ]:
        lp = guides.get(left)
        rp = guides.get(right)
        if lp is None or rp is None:
            continue
        x_error = abs((lp[0] - center[0]) + (rp[0] - center[0]))
        z_error = abs(lp[2] - rp[2])
        if x_error > width * 0.06 or z_error > height * 0.04:
            add_issue(
                issues,
                "warning",
                "visual_symmetry_offset",
                f"{left}/{right} are not visually symmetric enough.",
                left,
            )

    error_count = sum(1 for issue in issues if issue["severity"] == "error")
    warning_count = sum(1 for issue in issues if issue["severity"] == "warning")
    info_count = sum(1 for issue in issues if issue["severity"] == "info")
    visual_score = 100 - error_count * 8 - warning_count * 4 - info_count
    visual_score = max(0, min(100, visual_score))

    return {
        "visualMode": "local_silhouette_projection",
        "decisionPolicy": "visual_semantic_gate_only",
        "scorePolicy": "scores_disabled_for_decision_diagnostic_only",
        "visualScore": visual_score,
        "visualReady": False,
        "legacyVisualReady": visual_score >= 85 and error_count == 0,
        "productionReady": False,
        "errorCount": error_count,
        "warningCount": warning_count,
        "infoCount": info_count,
        "observations": observations,
        "issues": issues,
        "guideProjectedDistances": guide_distances,
        "handCoverage": hand_coverage,
        "armCoverage": arm_coverage,
        "semanticWarning": "This is local 2D silhouette QC, not a vision-language model verdict. Use exported screenshots for human or VLM review before skinning.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate local visual silhouette QC from an AIRA visual snapshot.")
    parser.add_argument("snapshot_json")
    parser.add_argument("--asset-name", default="")
    parser.add_argument("--out-dir", default="")
    args = parser.parse_args()

    snapshot_path = Path(args.snapshot_json)
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8-sig"))
    asset_name = args.asset_name or snapshot.get("assetName") or snapshot_path.stem.replace("_visual_snapshot", "")
    out_dir = Path(args.out_dir) if args.out_dir else snapshot_path.parent
    screenshot_dir = out_dir / "visual_screenshots" / asset_name
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    qc = analyze(snapshot)
    screenshots = {}
    for view in ["front", "side", "top"]:
        path = screenshot_dir / f"{asset_name}_{view}.png"
        draw_view(snapshot, view, path, qc)
        screenshots[view] = str(path)

    qc.update(
        {
            "assetName": asset_name,
            "snapshot": str(snapshot_path),
            "screenshots": screenshots,
        }
    )

    json_path = out_dir / f"{asset_name}_visual_qc.json"
    md_path = out_dir / f"{asset_name}_visual_qc.md"
    json_path.write_text(json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# Visual Silhouette QC: {asset_name}",
        "",
        f"- Snapshot: `{snapshot_path}`",
        f"- Visual mode: `{qc['visualMode']}`",
        f"- Decision policy: `{qc['decisionPolicy']}`",
        f"- Score policy: `{qc['scorePolicy']}`",
        "- Decision use: `diagnostic_only`; this report must not be used as a Skin-ready score.",
        f"- Production ready: `{qc['productionReady']}`",
        f"- Diagnostic issue counts: errors `{qc['errorCount']}`, warnings `{qc['warningCount']}`, info `{qc['infoCount']}`",
        "",
        "## Screenshots",
        "",
    ]
    for view, path in screenshots.items():
        lines.append(f"- {view}: `{path}`")
    lines += ["", "## Observations", ""]
    for observation in qc["observations"]:
        lines.append(f"- {observation}")
    lines += ["", "## Hand Centerline Coverage", ""]
    if qc["handCoverage"]:
        for name, coverage in qc["handCoverage"].items():
            lines.append(
                f"- {name}: diagnostic distance `{coverage['distance']}`, target `{coverage['target']}`"
            )
    else:
        lines.append("- None")
    lines += ["", "## Arm Centerline Coverage", ""]
    if qc["armCoverage"]:
        for name, coverage in qc["armCoverage"].items():
            lines.append(
                f"- {name}: diagnostic distance `{coverage['distance']}`, target `{coverage['target']}`"
            )
    else:
        lines.append("- None")
    lines += ["", "## Issues", ""]
    if qc["issues"]:
        for issue in qc["issues"]:
            guide = f" ({issue['guide']})" if issue.get("guide") else ""
            lines.append(f"- [{issue['severity']}] {issue['code']}{guide}: {issue['message']}")
    else:
        lines.append("- None")
    lines += ["", "## Semantic Gate", "", f"- {qc['semanticWarning']}"]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "assetName": asset_name,
                "json": str(json_path),
                "markdown": str(md_path),
                "screenshotDir": str(screenshot_dir),
                "screenshots": screenshots,
                "decisionPolicy": qc["decisionPolicy"],
                "scorePolicy": qc["scorePolicy"],
                "legacyRatingFields": "hidden_diagnostic_only",
                "productionReady": qc["productionReady"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
