from __future__ import annotations

import argparse
import json
import math
import struct
import zlib
from datetime import datetime
from pathlib import Path
from typing import Any

from visual_qc import Canvas, draw_cross, guide_color, project


Point3 = list[float]

VIEWS = ["front", "side", "top"]

REGION_GUIDES = {
    "head": ["Neck", "Head", "HeadTop", "CrestTop"],
    "pelvis": ["Root", "Pelvis", "Spine", "L_Hip", "R_Hip"],
    "left_hand": ["L_Shoulder", "L_Elbow", "L_Wrist", "L_Hand", "L_HandTip"],
    "right_hand": ["R_Shoulder", "R_Elbow", "R_Wrist", "R_Hand", "R_HandTip"],
    "left_foot": ["L_Hip", "L_Knee", "L_Ankle", "L_Heel", "L_Foot", "L_Toe"],
    "right_foot": ["R_Hip", "R_Knee", "R_Ankle", "R_Heel", "R_Foot", "R_Toe"],
}

REGION_VIEWS = {
    "head": ["front", "side", "top"],
    "pelvis": ["front", "side", "top"],
    "left_hand": ["front", "side", "top"],
    "right_hand": ["front", "side", "top"],
    "left_foot": ["front", "side", "top"],
    "right_foot": ["front", "side", "top"],
}

BLOCKER_REGIONS = {
    "root_to_pelvis_control_only": ["pelvis_front", "pelvis_side", "pelvis_top"],
    "headtop_may_be_crest_or_ornament": ["head_front", "head_side", "head_top"],
    "cresttop_must_not_be_skin_bone": ["head_front", "head_side", "head_top"],
    "single_hand_mass_requires_detail_signoff": [
        "left_hand_front",
        "left_hand_side",
        "left_hand_top",
        "right_hand_front",
        "right_hand_side",
        "right_hand_top",
    ],
    "foot_pivots_require_side_top_signoff": [
        "left_foot_side",
        "left_foot_top",
        "right_foot_side",
        "right_foot_top",
    ],
    "leg_landmarks_may_be_clothing_occluded": [
        "full_front",
        "full_side",
        "full_top",
        "left_foot_front",
        "left_foot_side",
        "left_foot_top",
        "right_foot_front",
        "right_foot_side",
        "right_foot_top",
        "slice_l_hip_l_knee",
        "slice_l_knee_l_ankle",
        "slice_r_hip_r_knee",
        "slice_r_knee_r_ankle",
    ],
}

SEMANTIC_GUIDES = [
    "Root",
    "Pelvis",
    "Spine",
    "Chest",
    "Neck",
    "Head",
    "HeadTop",
    "CrestTop",
    "L_Heel",
    "L_Foot",
    "L_Toe",
    "R_Heel",
    "R_Foot",
    "R_Toe",
]

SLICE_SEGMENTS = [
    ("Pelvis", "Spine"),
    ("Spine", "Chest"),
    ("Chest", "Neck"),
    ("Neck", "Head"),
    ("L_Hip", "L_Knee"),
    ("L_Knee", "L_Ankle"),
    ("L_Ankle", "L_Toe"),
    ("R_Hip", "R_Knee"),
    ("R_Knee", "R_Ankle"),
    ("R_Ankle", "R_Toe"),
]


class RgbImage:
    def __init__(self, width: int, height: int, pixels: bytearray | None = None, bg: tuple[int, int, int] = (250, 250, 248)) -> None:
        self.width = width
        self.height = height
        self.pixels = pixels if pixels is not None else bytearray(bg * width * height)

    @classmethod
    def new(cls, width: int, height: int, bg: tuple[int, int, int] = (250, 250, 248)) -> "RgbImage":
        return cls(width, height, None, bg)

    @classmethod
    def from_png(cls, path: Path) -> "RgbImage":
        data = path.read_bytes()
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError(f"not a PNG file: {path}")
        offset = 8
        width = height = bit_depth = color_type = None
        idat = bytearray()
        while offset < len(data):
            length = struct.unpack(">I", data[offset : offset + 4])[0]
            kind = data[offset + 4 : offset + 8]
            payload = data[offset + 8 : offset + 8 + length]
            offset += 12 + length
            if kind == b"IHDR":
                width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(">IIBBBBB", payload)
                if bit_depth not in {8, 16} or compression != 0 or filter_method != 0 or interlace != 0:
                    raise ValueError(f"unsupported PNG format: {path}")
            elif kind == b"IDAT":
                idat.extend(payload)
            elif kind == b"IEND":
                break
        if width is None or height is None or bit_depth is None or color_type is None:
            raise ValueError(f"invalid PNG missing IHDR: {path}")
        channels = {0: 1, 2: 3, 6: 4}.get(color_type)
        if channels is None:
            raise ValueError(f"unsupported PNG color type {color_type}: {path}")
        raw = zlib.decompress(bytes(idat))
        bytes_per_sample = bit_depth // 8
        filter_bpp = channels * bytes_per_sample
        stride = width * filter_bpp
        rows: list[bytearray] = []
        pos = 0
        prev = bytearray(stride)
        for _ in range(height):
            filter_type = raw[pos]
            pos += 1
            row = bytearray(raw[pos : pos + stride])
            pos += stride
            for i in range(stride):
                left = row[i - filter_bpp] if i >= filter_bpp else 0
                up = prev[i]
                upper_left = prev[i - filter_bpp] if i >= filter_bpp else 0
                if filter_type == 1:
                    row[i] = (row[i] + left) & 0xFF
                elif filter_type == 2:
                    row[i] = (row[i] + up) & 0xFF
                elif filter_type == 3:
                    row[i] = (row[i] + ((left + up) // 2)) & 0xFF
                elif filter_type == 4:
                    row[i] = (row[i] + paeth(left, up, upper_left)) & 0xFF
                elif filter_type != 0:
                    raise ValueError(f"unsupported PNG row filter {filter_type}: {path}")
            rows.append(row)
            prev = row
        pixels = bytearray(width * height * 3)
        out = 0
        for row in rows:
            for x in range(width):
                src = x * filter_bpp
                def sample(index: int) -> int:
                    return row[src + index * bytes_per_sample]
                if color_type == 0:
                    gray = sample(0)
                    pixels[out : out + 3] = bytes((gray, gray, gray))
                elif color_type == 2:
                    pixels[out : out + 3] = bytes(sample(c) for c in range(3))
                else:
                    alpha = sample(3) / 255.0
                    pixels[out : out + 3] = bytes(
                        int(sample(c) * alpha) for c in range(3)
                    )
                out += 3
        return cls(width, height, pixels)

    def copy(self) -> "RgbImage":
        return RgbImage(self.width, self.height, bytearray(self.pixels))

    def save_png(self, path: Path) -> None:
        rows = []
        stride = self.width * 3
        for y in range(self.height):
            row = self.pixels[y * stride : (y + 1) * stride]
            rows.append(b"\x00" + bytes(row))
        raw = b"".join(rows)
        data = (
            b"\x89PNG\r\n\x1a\n"
            + png_chunk(b"IHDR", struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0))
            + png_chunk(b"IDAT", zlib.compress(raw, 9))
            + png_chunk(b"IEND", b"")
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, x: int, y: int) -> tuple[int, int, int]:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return (0, 0, 0)
        idx = (y * self.width + x) * 3
        return self.pixels[idx], self.pixels[idx + 1], self.pixels[idx + 2]

    def set(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            idx = (y * self.width + x) * 3
            self.pixels[idx : idx + 3] = bytes(color)

    def blend(self, x: int, y: int, color: tuple[int, int, int], alpha: float = 0.55) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            idx = (y * self.width + x) * 3
            inv = 1.0 - alpha
            self.pixels[idx] = int(self.pixels[idx] * inv + color[0] * alpha)
            self.pixels[idx + 1] = int(self.pixels[idx + 1] * inv + color[1] * alpha)
            self.pixels[idx + 2] = int(self.pixels[idx + 2] * inv + color[2] * alpha)

    def point(self, x: int, y: int, color: tuple[int, int, int], radius: int = 1, alpha: float = 1.0) -> None:
        for yy in range(y - radius, y + radius + 1):
            for xx in range(x - radius, x + radius + 1):
                if (xx - x) * (xx - x) + (yy - y) * (yy - y) <= radius * radius:
                    if alpha >= 1.0:
                        self.set(xx, yy, color)
                    else:
                        self.blend(xx, yy, color, alpha)

    def line(self, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int], width: int = 1, alpha: float = 1.0) -> None:
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.point(x0, y0, color, width, alpha)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def rect(self, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int], width: int = 1, alpha: float = 1.0) -> None:
        self.line(x0, y0, x1, y0, color, width, alpha)
        self.line(x1, y0, x1, y1, color, width, alpha)
        self.line(x1, y1, x0, y1, color, width, alpha)
        self.line(x0, y1, x0, y0, color, width, alpha)

    def paste(self, other: "RgbImage", left: int, top: int) -> None:
        for y in range(other.height):
            target_y = top + y
            if not 0 <= target_y < self.height:
                continue
            for x in range(other.width):
                target_x = left + x
                if 0 <= target_x < self.width:
                    self.set(target_x, target_y, other.get(x, y))

    def resized_nearest(self, width: int, height: int) -> "RgbImage":
        width = max(1, width)
        height = max(1, height)
        out = RgbImage.new(width, height, (0, 0, 0))
        for y in range(height):
            src_y = min(self.height - 1, int(y * self.height / height))
            for x in range(width):
                src_x = min(self.width - 1, int(x * self.width / width))
                out.set(x, y, self.get(src_x, src_y))
        return out


def paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def png_chunk(kind: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)


def load_json(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    file_path = Path(path)
    if not file_path.exists():
        return {}
    return json.loads(file_path.read_text(encoding="utf-8-sig", errors="replace"))


def rel(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return str(path)


def bbox_from_points(points: list[Point3], fallback_bounds: dict[str, Point3]) -> tuple[float, float, float, float, float, float]:
    if not points:
        mn = fallback_bounds["min"]
        mx = fallback_bounds["max"]
        return mn[0], mx[0], mn[1], mx[1], mn[2], mx[2]
    return (
        min(point[0] for point in points),
        max(point[0] for point in points),
        min(point[1] for point in points),
        max(point[1] for point in points),
        min(point[2] for point in points),
        max(point[2] for point in points),
    )


def expand_bbox(
    bbox: tuple[float, float, float, float, float, float],
    bounds: dict[str, Point3],
    ratio: float,
) -> tuple[float, float, float, float, float, float]:
    size = bounds["size"]
    pad_x = max(size[0] * ratio, 1.0)
    pad_y = max(size[1] * ratio, 1.0)
    pad_z = max(size[2] * ratio, 1.0)
    min_x, max_x, min_y, max_y, min_z, max_z = bbox
    return min_x - pad_x, max_x + pad_x, min_y - pad_y, max_y + pad_y, min_z - pad_z, max_z + pad_z


def point_in_bbox(point: Point3, bbox: tuple[float, float, float, float, float, float]) -> bool:
    min_x, max_x, min_y, max_y, min_z, max_z = bbox
    return min_x <= point[0] <= max_x and min_y <= point[1] <= max_y and min_z <= point[2] <= max_z


def region_points(snapshot: dict[str, Any], region: str) -> list[Point3]:
    bounds = snapshot["bounds"]
    guides = snapshot.get("guides", {})
    guide_points = [guides[name] for name in REGION_GUIDES[region] if guides.get(name) is not None]
    ratio = 0.16 if region in {"head", "pelvis"} else 0.12
    crop_bbox = expand_bbox(bbox_from_points(guide_points, bounds), bounds, ratio)
    mesh_points = [point for point in snapshot.get("meshPoints", []) if point_in_bbox(point, crop_bbox)]
    return mesh_points + guide_points


def projected_range(
    points: list[Point3],
    bounds: dict[str, Point3],
    view: str,
    pad_ratio: float = 0.22,
) -> tuple[float, float, float, float]:
    if not points:
        mn = bounds["min"]
        mx = bounds["max"]
        points = [
            [mn[0], mn[1], mn[2]],
            [mn[0], mn[1], mx[2]],
            [mn[0], mx[1], mn[2]],
            [mn[0], mx[1], mx[2]],
            [mx[0], mn[1], mn[2]],
            [mx[0], mn[1], mx[2]],
            [mx[0], mx[1], mn[2]],
            [mx[0], mx[1], mx[2]],
        ]
    projected = [project(point, view) for point in points]
    xs = [point[0] for point in projected]
    ys = [point[1] for point in projected]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)
    pad_x = max(span_x * pad_ratio, 1.0)
    pad_y = max(span_y * pad_ratio, 1.0)
    return min_x - pad_x, max_x + pad_x, min_y - pad_y, max_y + pad_y


def full_range(bounds: dict[str, Point3], view: str) -> tuple[float, float, float, float]:
    return projected_range([], bounds, view, 0.10)


def make_mapper(view_range: tuple[float, float, float, float], width: int, height: int):
    min_x, max_x, min_y, max_y = view_range
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)

    def map_point(point: Point3, view: str) -> tuple[int, int]:
        x, y = project(point, view)
        px = int((x - min_x) / span_x * (width - 1))
        py = int((1.0 - (y - min_y) / span_y) * (height - 1))
        return px, py

    return map_point


def visible_pixel(x: int, y: int, width: int, height: int, margin: int = 32) -> bool:
    return -margin <= x < width + margin and -margin <= y < height + margin


def image_foreground_bbox(image: RgbImage) -> tuple[int, int, int, int]:
    xs: list[int] = []
    ys: list[int] = []
    for y in range(image.height):
        for x in range(image.width):
            r, g, b = image.get(x, y)
            if max(r, g, b) > 22:
                xs.append(x)
                ys.append(y)
    if not xs or not ys:
        return 0, 0, image.width - 1, image.height - 1
    pad_x = max(int((max(xs) - min(xs)) * 0.02), 2)
    pad_y = max(int((max(ys) - min(ys)) * 0.02), 2)
    return (
        max(0, min(xs) - pad_x),
        max(0, min(ys) - pad_y),
        min(image.width - 1, max(xs) + pad_x),
        min(image.height - 1, max(ys) + pad_y),
    )


def image_mapper_from_foreground(snapshot: dict[str, Any], view: str, image: RgbImage, fg: tuple[int, int, int, int]):
    bounds = snapshot["bounds"]
    world_range = projected_range([], bounds, view, 0.0)
    min_x, max_x, min_y, max_y = world_range
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)
    fg_x0, fg_y0, fg_x1, fg_y1 = fg
    fg_w = max(fg_x1 - fg_x0, 1)
    fg_h = max(fg_y1 - fg_y0, 1)

    def to_pixel(point: Point3) -> tuple[int, int]:
        x, y = project(point, view)
        px = int(fg_x0 + (x - min_x) / span_x * fg_w)
        py = int(fg_y1 - (y - min_y) / span_y * fg_h)
        return px, py

    return to_pixel


def detect_belt_texture_band(image: RgbImage, fg: tuple[int, int, int, int]) -> dict[str, Any]:
    fg_x0, fg_y0, fg_x1, fg_y1 = fg
    width = max(fg_x1 - fg_x0, 1)
    height = max(fg_y1 - fg_y0, 1)
    roi = (
        int(fg_x0 + width * 0.38),
        int(fg_y0 + height * 0.60),
        int(fg_x0 + width * 0.62),
        int(fg_y0 + height * 0.82),
    )
    candidates: list[tuple[int, int]] = []
    rows: dict[int, int] = {}
    for y in range(roi[1], roi[3] + 1):
        for x in range(roi[0], roi[2] + 1):
            r, g, b = image.get(x, y)
            gold = r > 118 and g > 72 and b < 98 and r >= g * 0.95
            purple_or_band = r > 75 and b > 75 and g < 100 and abs(r - b) < 72
            lower_dark_trim = r > 48 and b > 45 and g < 78 and max(r, b) - g > 24 and y > (roi[1] + roi[3]) / 2.0
            if gold or purple_or_band or lower_dark_trim:
                candidates.append((x, y))
                rows[y] = rows.get(y, 0) + 1
    center_y = None
    centroid_y = None
    if rows:
        total = sum(rows.values())
        weighted = sum(y * count for y, count in rows.items())
        centroid_y = int(round(weighted / max(total, 1)))
        cumulative = 0
        target = total * 0.75
        for y in sorted(rows):
            cumulative += rows[y]
            if cumulative >= target:
                center_y = y
                break
    return {
        "roi": roi,
        "candidateCount": len(candidates),
        "candidateSample": candidates[:: max(1, len(candidates) // 800)] if candidates else [],
        "centerY": center_y,
        "centroidY": centroid_y,
    }


def skeleton_bones(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    biped_bones = snapshot.get("bipedBones")
    if isinstance(biped_bones, list) and biped_bones:
        return biped_bones
    return snapshot.get("templateBones", [])


def draw_guides_on_rgb(
    image: RgbImage,
    snapshot: dict[str, Any],
    view: str,
    to_pixel,
    *,
    highlight_guides: list[str] | None = None,
    draw_all_bones: bool = True,
) -> None:
    highlight = set(highlight_guides or [])
    if draw_all_bones:
        for bone in skeleton_bones(snapshot):
            start = bone.get("startPosition")
            end = bone.get("endPosition")
            if start is None or end is None:
                continue
            x0, y0 = to_pixel(start)
            x1, y1 = to_pixel(end)
            image.line(x0, y0, x1, y1, (240, 162, 24), 2, 0.90)
    for name in SEMANTIC_GUIDES:
        point = snapshot.get("guides", {}).get(name)
        if point is None:
            continue
        x, y = to_pixel(point)
        radius = 7 if name in highlight else 5
        image.point(x, y, guide_color(name), radius)
        image.point(x, y, (255, 246, 72), 2 if name in highlight else 1)


def write_texture_wire_compare(
    run_dir: Path,
    asset_name: str,
    view: str,
    textured_overlay: RgbImage,
    output_dir: Path,
) -> str | None:
    wire_path = run_dir / "wire_bone_screenshots" / f"{asset_name}_wire_bone_{view}.png"
    if not wire_path.exists():
        return None
    try:
        wire = RgbImage.from_png(wire_path)
    except Exception:
        return None

    target_h = max(textured_overlay.height, wire.height)
    left_w = max(1, int(round(textured_overlay.width * target_h / textured_overlay.height)))
    right_w = max(1, int(round(wire.width * target_h / wire.height)))
    left = textured_overlay if textured_overlay.height == target_h and textured_overlay.width == left_w else textured_overlay.resized_nearest(left_w, target_h)
    right = wire if wire.height == target_h and wire.width == right_w else wire.resized_nearest(right_w, target_h)

    gap = 18
    canvas = RgbImage.new(left.width + gap + right.width, target_h, (10, 10, 10))
    canvas.paste(left, 0, 0)
    canvas.paste(right, left.width + gap, 0)
    canvas.rect(0, 0, left.width - 1, target_h - 1, (0, 220, 230), 2, 1.0)
    canvas.rect(left.width + gap, 0, left.width + gap + right.width - 1, target_h - 1, (245, 156, 28), 2, 1.0)

    output = output_dir / f"{asset_name}_texture_wire_compare_{view}.png"
    canvas.save_png(output)
    return rel(output, run_dir)


def draw_textured_semantic_overlays(
    run_dir: Path,
    asset_name: str,
    snapshot: dict[str, Any],
    output_dir: Path,
) -> tuple[dict[str, str], dict[str, Any]]:
    images: dict[str, str] = {}
    analysis: dict[str, Any] = {"textureDrivenEvidence": [], "views": {}}
    textured_dir = run_dir / "textured_screenshots"
    for view in VIEWS:
        source = textured_dir / f"{asset_name}_textured_{view}.png"
        if not source.exists():
            continue
        try:
            image = RgbImage.from_png(source)
        except Exception as exc:
            analysis["views"][view] = {"error": str(exc), "source": rel(source, run_dir)}
            continue
        fg = image_foreground_bbox(image)
        overlay = image.copy()
        overlay.rect(*fg, (255, 255, 255), 1, 0.55)

        view_result: dict[str, Any] = {
            "source": rel(source, run_dir),
            "foregroundBbox": list(fg),
            "projectionPolicy": "texture overlays are texture-only; skeleton alignment must be read from Max wire_bone screenshots or texture_wire_compare images.",
        }
        if view == "front":
            belt = detect_belt_texture_band(image, fg)
            roi = belt["roi"]
            overlay.rect(*roi, (0, 210, 230), 2, 0.9)
            for x, y in belt.get("candidateSample", []):
                overlay.point(x, y, (0, 215, 240), 1, 0.80)
            if belt.get("centerY") is not None:
                overlay.line(roi[0], belt["centerY"], roi[2], belt["centerY"], (0, 235, 255), 3, 0.95)

            view_result["beltTextureSearch"] = {
                "roi": list(roi),
                "candidateCount": belt["candidateCount"],
                "centerY": belt.get("centerY"),
                "centroidY": belt.get("centroidY"),
                "use": "Use this texture-only band as the waist semantic target, then compare it against the real Max-rendered skeleton in texture_wire_compare_front or wire_bone_front.",
            }
            analysis["textureDrivenEvidence"].append("front_belt_texture_band_for_root_pelvis")
        elif view == "side":
            view_result["use"] = "Texture-only side silhouette context for head/foot/depth semantics; use texture_wire_compare_side or wire_bone_side for authoritative skeleton alignment."
            analysis["textureDrivenEvidence"].append("side_textured_silhouette_for_foot_and_head_axis")
        else:
            view_result["use"] = "Texture-only top silhouette context; use texture_wire_compare_top or wire_bone_top for authoritative skeleton depth alignment."
            analysis["textureDrivenEvidence"].append("top_textured_silhouette_for_depth_balance")

        output = output_dir / f"{asset_name}_textured_semantic_{view}.png"
        overlay.save_png(output)
        images[f"semantic_textured_{view}"] = rel(output, run_dir)
        compare = write_texture_wire_compare(run_dir, asset_name, view, overlay, output_dir)
        if compare:
            images[f"texture_wire_compare_{view}"] = compare
            view_result["authoritativeSkeletonEvidence"] = compare
        analysis["views"][view] = view_result
    return images, analysis


def vec_sub(a: Point3, b: Point3) -> Point3:
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def vec_add(a: Point3, b: Point3) -> Point3:
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def vec_scale(v: Point3, scale: float) -> Point3:
    return [v[0] * scale, v[1] * scale, v[2] * scale]


def vec_dot(a: Point3, b: Point3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vec_cross(a: Point3, b: Point3) -> Point3:
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def vec_length(v: Point3) -> float:
    return math.sqrt(vec_dot(v, v))


def vec_norm(v: Point3) -> Point3:
    length = vec_length(v)
    if length <= 1e-8:
        return [0.0, 0.0, 1.0]
    return [v[0] / length, v[1] / length, v[2] / length]


def bone_lookup(snapshot: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (bone.get("start", ""), bone.get("end", "")): bone
        for bone in skeleton_bones(snapshot)
    }


def draw_slice_panel(
    image: RgbImage,
    left: int,
    top: int,
    width: int,
    height: int,
    coords: list[tuple[float, float]],
    *,
    bone_width: float,
    bone_height: float,
) -> dict[str, Any]:
    if coords:
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
    else:
        min_x = min_y = -1.0
        max_x = max_y = 1.0
    pad = max(max_x - min_x, max_y - min_y, bone_width, bone_height, 1.0) * 0.22
    min_x -= pad
    max_x += pad
    min_y -= pad
    max_y += pad
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)

    def to_panel(u: float, v: float) -> tuple[int, int]:
        px = int(left + (u - min_x) / span_x * (width - 1))
        py = int(top + (1.0 - (v - min_y) / span_y) * (height - 1))
        return px, py

    image.rect(left, top, left + width - 1, top + height - 1, (212, 212, 212), 1, 1.0)
    ox, oy = to_panel(0.0, 0.0)
    image.line(left, oy, left + width - 1, oy, (220, 220, 220), 1, 1.0)
    image.line(ox, top, ox, top + height - 1, (220, 220, 220), 1, 1.0)
    for u, v in coords:
        px, py = to_panel(u, v)
        image.point(px, py, (150, 150, 150), 1, 0.85)

    radius_u = max(bone_width * 0.5, 0.1)
    radius_v = max(bone_height * 0.5, 0.1)
    previous: tuple[int, int] | None = None
    for i in range(96):
        angle = math.tau * i / 96
        px, py = to_panel(math.cos(angle) * radius_u, math.sin(angle) * radius_v)
        if previous is not None:
            image.line(previous[0], previous[1], px, py, (245, 156, 28), 2, 0.95)
        previous = (px, py)
    image.point(ox, oy, (245, 156, 28), 5, 1.0)

    inside = bool(coords) and min_x < 0 < max_x and min_y < 0 < max_y
    local_span = max(max_x - min_x - 2 * pad, max_y - min_y - 2 * pad, 1.0)
    thickness_ratio = max(bone_width, bone_height) / local_span
    if thickness_ratio < 0.22:
        thickness_state = "thin_for_visual_body_volume"
    elif thickness_ratio > 1.05:
        thickness_state = "too_large_for_local_section"
    else:
        thickness_state = "reasonable_visual_display_volume"
    return {
        "pointCount": len(coords),
        "insideBodySection": inside,
        "localSpan": round(local_span, 6),
        "boneDisplayDiameter": round(max(bone_width, bone_height), 6),
        "thicknessRatio": round(thickness_ratio, 6),
        "thicknessState": thickness_state,
    }


def write_slice_analysis(run_dir: Path, asset_name: str, snapshot: dict[str, Any], output_dir: Path) -> tuple[dict[str, str], dict[str, Any]]:
    bones = bone_lookup(snapshot)
    mesh_points = snapshot.get("meshPoints", [])
    bounds = snapshot["bounds"]
    height = max(bounds["size"][2], 1.0)
    images: dict[str, str] = {}
    analysis: dict[str, Any] = {"mode": "mr_style_cross_section_review", "segments": {}}

    for start_name, end_name in SLICE_SEGMENTS:
        bone = bones.get((start_name, end_name))
        if not bone:
            continue
        start = bone.get("startPosition")
        end = bone.get("endPosition")
        if start is None or end is None:
            continue
        axis_vec = vec_sub(end, start)
        length = vec_length(axis_vec)
        if length <= 1e-6:
            continue
        axis = vec_norm(axis_vec)
        ref = [0.0, 0.0, 1.0]
        if abs(vec_dot(axis, ref)) > 0.86:
            ref = [1.0, 0.0, 0.0]
        u_axis = vec_norm(vec_cross(axis, ref))
        v_axis = vec_norm(vec_cross(axis, u_axis))
        slab = max(height * 0.012, length * 0.08, 0.8)
        image = RgbImage.new(1140, 390, (248, 248, 246))
        segment_result: dict[str, Any] = {
            "segment": f"{start_name}->{end_name}",
            "slabThickness": round(slab, 6),
            "samples": [],
        }
        for index, t in enumerate([0.25, 0.50, 0.75]):
            center = vec_add(start, vec_scale(axis_vec, t))
            coords: list[tuple[float, float]] = []
            for point in mesh_points:
                delta = vec_sub(point, center)
                if abs(vec_dot(delta, axis)) <= slab:
                    coords.append((vec_dot(delta, u_axis), vec_dot(delta, v_axis)))
            panel_result = draw_slice_panel(
                image,
                20 + index * 375,
                20,
                350,
                350,
                coords,
                bone_width=float(bone.get("boneWidth") or 0.0),
                bone_height=float(bone.get("boneHeight") or 0.0),
            )
            panel_result["t"] = t
            segment_result["samples"].append(panel_result)
        slug = f"{start_name}_{end_name}".lower()
        path = output_dir / f"{asset_name}_slice_{slug}.png"
        image.save_png(path)
        key = f"slice_{slug}"
        images[key] = rel(path, run_dir)
        analysis["segments"][key] = segment_result
    return images, analysis


def draw_evidence_view(
    snapshot: dict[str, Any],
    view: str,
    path: Path,
    *,
    visual_qc: dict[str, Any],
    crop_points: list[Point3] | None = None,
    highlight_guides: list[str] | None = None,
    width: int = 1200,
    height: int = 900,
) -> None:
    canvas = Canvas(width, height, (250, 250, 248))
    bounds = snapshot["bounds"]
    view_range = projected_range(crop_points, bounds, view, 0.24) if crop_points else full_range(bounds, view)
    to_pixel = make_mapper(view_range, width, height)
    highlight_guides = highlight_guides or []

    for point in snapshot.get("meshPoints", []):
        x, y = to_pixel(point, view)
        if visible_pixel(x, y, width, height):
            canvas.point(x, y, (184, 184, 184), 1)

    for bone in skeleton_bones(snapshot):
        start = bone.get("startPosition")
        end = bone.get("endPosition")
        if start is None or end is None:
            continue
        x0, y0 = to_pixel(start, view)
        x1, y1 = to_pixel(end, view)
        if visible_pixel(x0, y0, width, height) or visible_pixel(x1, y1, width, height):
            canvas.line(x0, y0, x1, y1, (232, 132, 28), 3 if crop_points else 2)

    for name, point in snapshot.get("guides", {}).items():
        if point is None:
            continue
        x, y = to_pixel(point, view)
        if visible_pixel(x, y, width, height):
            radius = 4 if name == "Root" else (8 if name in highlight_guides else 6)
            canvas.point(x, y, guide_color(name), radius)
            canvas.point(x, y, (20, 20, 20), 1 if name == "Root" else 2)
            if name in highlight_guides:
                draw_cross(canvas, x, y, (255, 236, 78), 12, 2)

    for coverage_name in ["armCoverage", "handCoverage"]:
        for _, coverage in visual_qc.get(coverage_name, {}).items():
            guide_point = coverage.get("guide")
            target_point = coverage.get("target")
            if guide_point is None or target_point is None:
                continue
            gx, gy = to_pixel(guide_point, view)
            tx, ty = to_pixel(target_point, view)
            if visible_pixel(gx, gy, width, height) or visible_pixel(tx, ty, width, height):
                color = (150, 74, 196) if coverage_name == "armCoverage" else (214, 52, 52)
                canvas.line(gx, gy, tx, ty, color, 2)
                draw_cross(canvas, tx, ty, color, 8 if coverage_name == "armCoverage" else 10, 2)
                canvas.point(tx, ty, (255, 236, 78), 4)

    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save_png(path)


def review_schema() -> dict[str, Any]:
    status_enum = ["pass", "blocker", "needs_detail", "uncertain", "not_visible"]
    check_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["status", "evidence", "comment"],
        "properties": {
            "status": {"type": "string", "enum": status_enum},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "comment": {"type": "string"},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "assetName",
            "decisionPolicy",
            "reviewer",
            "reviewedAt",
            "checks",
            "stage01HandoffRecommendation",
            "notes",
        ],
        "properties": {
            "assetName": {"type": "string"},
            "decisionPolicy": {"type": "string", "enum": ["visual_semantic_gate_only"]},
            "reviewer": {"type": "string"},
            "reviewedAt": {"type": "string"},
            "checks": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "rootPelvisPolicy",
                    "frontWrap",
                    "sideWrap",
                    "topWrap",
                    "textureLandmarkTrace",
                    "crossSectionInsideVolume",
                    "legClothingOcclusion",
                    "headTopSemantic",
                    "leftHandDetail",
                    "rightHandDetail",
                    "leftFootPivot",
                    "rightFootPivot",
                    "deferredDetails",
                ],
                "properties": {
                    "rootPelvisPolicy": check_schema,
                    "frontWrap": check_schema,
                    "sideWrap": check_schema,
                    "topWrap": check_schema,
                    "textureLandmarkTrace": check_schema,
                    "crossSectionInsideVolume": check_schema,
                    "legClothingOcclusion": check_schema,
                    "headTopSemantic": check_schema,
                    "leftHandDetail": check_schema,
                    "rightHandDetail": check_schema,
                    "leftFootPivot": check_schema,
                    "rightFootPivot": check_schema,
                    "deferredDetails": check_schema,
                },
            },
            "stage01HandoffRecommendation": {
                "type": "string",
                "enum": ["approve_for_manual_skin_setup", "block_until_fixed", "needs_more_views"],
            },
            "notes": {"type": "array", "items": {"type": "string"}},
        },
    }


def review_template(asset_name: str, images: dict[str, str]) -> dict[str, Any]:
    def check(*evidence: str) -> dict[str, Any]:
        return {"status": "uncertain", "evidence": list(evidence), "comment": ""}

    return {
        "assetName": asset_name,
        "decisionPolicy": "visual_semantic_gate_only",
        "reviewer": "human_or_vlm",
        "reviewedAt": "",
        "checks": {
            "rootPelvisPolicy": check(images.get("pelvis_front", ""), images.get("pelvis_side", ""), images.get("wire_bone_side", "")),
            "frontWrap": check(images.get("wire_bone_front", ""), images.get("full_front", ""), images.get("texture_wire_compare_front", "")),
            "sideWrap": check(images.get("wire_bone_side", ""), images.get("full_side", ""), images.get("texture_wire_compare_side", "")),
            "topWrap": check(images.get("wire_bone_top", ""), images.get("full_top", ""), images.get("texture_wire_compare_top", "")),
            "textureLandmarkTrace": check(
                images.get("semantic_textured_front", ""),
                images.get("texture_wire_compare_front", ""),
                images.get("texture_wire_compare_side", ""),
                images.get("textured_front", ""),
            ),
            "crossSectionInsideVolume": check(
                images.get("slice_pelvis_spine", ""),
                images.get("slice_neck_head", ""),
                images.get("slice_l_knee_l_ankle", ""),
                images.get("slice_r_knee_r_ankle", ""),
            ),
            "legClothingOcclusion": check(
                images.get("full_front", ""),
                images.get("full_side", ""),
                images.get("full_top", ""),
                images.get("left_foot_front", ""),
                images.get("left_foot_side", ""),
                images.get("right_foot_front", ""),
                images.get("right_foot_side", ""),
                images.get("slice_l_hip_l_knee", ""),
                images.get("slice_r_hip_r_knee", ""),
            ),
            "headTopSemantic": check(
                images.get("head_front", ""),
                images.get("head_side", ""),
                images.get("texture_wire_compare_side", ""),
                images.get("wire_bone_side", ""),
            ),
            "leftHandDetail": check(images.get("left_hand_front", ""), images.get("left_hand_top", "")),
            "rightHandDetail": check(images.get("right_hand_front", ""), images.get("right_hand_top", "")),
            "leftFootPivot": check(images.get("left_foot_side", ""), images.get("left_foot_top", ""), images.get("slice_l_ankle_l_toe", "")),
            "rightFootPivot": check(images.get("right_foot_side", ""), images.get("right_foot_top", ""), images.get("slice_r_ankle_r_toe", "")),
            "deferredDetails": check(
                images.get("full_front", ""),
                images.get("full_side", ""),
                images.get("full_top", ""),
                images.get("semantic_textured_front", ""),
                images.get("texture_wire_compare_front", ""),
            ),
        },
        "stage01HandoffRecommendation": "block_until_fixed",
        "notes": [],
    }


def textured_images(run_dir: Path, asset_name: str) -> dict[str, str]:
    image_dir = run_dir / "textured_screenshots"
    images: dict[str, str] = {}
    for view in VIEWS:
        path = image_dir / f"{asset_name}_textured_{view}.png"
        if path.exists():
            images[f"textured_{view}"] = rel(path, run_dir)
    return images


def wire_bone_images(run_dir: Path, asset_name: str) -> dict[str, str]:
    image_dir = run_dir / "wire_bone_screenshots"
    images: dict[str, str] = {}
    for view in VIEWS:
        path = image_dir / f"{asset_name}_wire_bone_{view}.png"
        if path.exists():
            images[f"wire_bone_{view}"] = rel(path, run_dir)
    return images


def texture_atlas_images(run_dir: Path) -> list[str]:
    scene_dir = run_dir / "scene"
    images: list[str] = []
    if not scene_dir.exists():
        return images
    for sidecar in sorted([p for p in scene_dir.iterdir() if p.is_dir() and p.name.endswith(".fbm")], key=lambda p: p.name):
        for path in sorted(sidecar.glob("*.png")):
            images.append(rel(path, run_dir))
    return images


def write_method_assessment(path: Path, *, asset_name: str, images: dict[str, str], atlas_images: list[str]) -> None:
    def status(keys: list[str]) -> str:
        return "available" if any(images.get(key) for key in keys) else "missing"

    lines = [
        f"# Visual Method Assessment: {asset_name}",
        "",
        "这份文件说明本 run 里有哪些视觉证据可以用来判断骨架。它不是评分报告，也不把旧算法分数作为决策依据。",
        "",
        "| 方法 | 状态 | 看什么 | 证据 | 局限 |",
        "| --- | --- | --- | --- | --- |",
        "| Textured 3ds Max views | `{}` | 颜色、纹样、服饰/头饰语义、脚尖朝向和手端形状 | `{}` | 依赖 Max 渲染/材质显示，不能直接证明权重变形 |".format(
            status(["textured_front", "textured_side", "textured_top"]),
            "`, `".join([images.get(f"textured_{view}", "") for view in VIEWS if images.get(f"textured_{view}", "")]),
        ),
        "| Wireframe + bone technical views | `{}` | 侧面重心、腰部原点、头/帽边界、骨骼粗细和骨架是否贴近体积 | `{}` | 是技术渲染，不显示真实 Skin 权重；需要和贴图截图一起看 |".format(
            status(["wire_bone_front", "wire_bone_side", "wire_bone_top"]),
            "`, `".join([images.get(f"wire_bone_{view}", "") for view in VIEWS if images.get(f"wire_bone_{view}", "")]),
        ),
        "| Textured semantic overlays | `{}` | 只显示带贴图模型上的前景、腰带/腰封候选区和纹理语义线索；不再叠加近似投影骨骼 | `{}` | 不能单独证明骨架位置，需要和真实 wire+bones 渲染配对查看 |".format(
            status(["semantic_textured_front", "semantic_textured_side", "semantic_textured_top"]),
            "`, `".join([images.get(f"semantic_textured_{view}", "") for view in VIEWS if images.get(f"semantic_textured_{view}", "")]),
        ),
        "| Texture + wire comparison | `{}` | 左侧看贴图语义依据，右侧看同 run 的 3ds Max wireframe + bone 真实技术视图，用来确认语义线索是否真正被骨架采用 | `{}` | 左右不是同一张相机投影叠加，判断时看语义对应关系，不把左侧当骨骼位置证据 |".format(
            status(["texture_wire_compare_front", "texture_wire_compare_side", "texture_wire_compare_top"]),
            "`, `".join([images.get(f"texture_wire_compare_{view}", "") for view in VIEWS if images.get(f"texture_wire_compare_{view}", "")]),
        ),
        "| MR-style cross sections | `{}` | 沿高风险骨段 25/50/75% 切片，看骨骼中心和显示粗细是否落在局部体积内 | `{}` | 基于采样点云和显示骨粗，不等同于 Skin 包络或实际权重 |".format(
            "available" if any(key.startswith("slice_") for key in images) else "missing",
            "`, `".join([value for key, value in sorted(images.items()) if key.startswith("slice_")][:8]),
        ),
        "| Silhouette + skeleton overlay | `{}` | 骨骼中心线、三视图轮廓、左右对称、手/脚局部位置 | `{}` | 点云投影没有贴图语义，不能判断纹样边界 |".format(
            status(["full_front", "full_side", "full_top"]),
            "`, `".join([images.get(f"full_{view}", "") for view in VIEWS if images.get(f"full_{view}", "")]),
        ),
        "| Region crops | `{}` | 头、骨盆、手、脚这些高风险局部 | `visual_review/regions/` | 裁剪依赖 guide 包围盒，仍需看全图确认上下文 |".format(
            status(["head_front", "left_hand_front", "left_foot_side"])
        ),
        "| Texture atlas | `{}` | 确认贴图资源是否存在、角色颜色/纹样是否可读 | `{}` | Atlas 不是模型空间截图，需要和 textured views 对照 |".format(
            "available" if atlas_images else "missing",
            "`, `".join(atlas_images[:6]),
        ),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_landmark_reasoning(
    path: Path,
    *,
    asset_name: str,
    run_dir: Path,
    images: dict[str, str],
    semantic_analysis: dict[str, Any],
    slice_analysis: dict[str, Any],
) -> None:
    front = semantic_analysis.get("views", {}).get("front", {})
    belt = front.get("beltTextureSearch", {}) if isinstance(front, dict) else {}
    lines = [
        f"# Textured Landmark Reasoning: {asset_name}",
        "",
        "这份说明把“贴图参与了什么判断”写清楚：贴图语义图只显示纹理/轮廓证据，真实骨骼位置以 3ds Max wireframe + bone 渲染为准。",
        "",
        "## 颜色约定",
        "",
        "- 青色矩形/点：在贴图前视图里搜索腰带、腰封、扣件或下躯干装饰的候选像素。",
        "- 青色水平线：从贴图候选像素得到的低腰语义目标行。",
        "- 白色框：贴图截图中的可见模型前景范围。",
        "- 橙色边框的配对图右侧：3ds Max 真实 wireframe + bone 技术视图，是骨架位置的权威证据。",
        "- 注意：`semantic_textured_*` 不再绘制骨骼或 guide，避免后处理近似投影误导判断。",
        "",
        "## 贴图证据",
        "",
    ]
    if images.get("semantic_textured_front"):
        lines.append(f"- 前视贴图语义叠加：`{images['semantic_textured_front']}`")
    if images.get("semantic_textured_side"):
        lines.append(f"- 侧视贴图语义叠加：`{images['semantic_textured_side']}`")
    if images.get("semantic_textured_top"):
        lines.append(f"- 顶视贴图语义叠加：`{images['semantic_textured_top']}`")
    for key in ["texture_wire_compare_front", "texture_wire_compare_side", "texture_wire_compare_top"]:
        if images.get(key):
            lines.append(f"- 贴图语义/真实骨骼配对：`{images[key]}`")
    if belt:
        lines += [
            "",
            "### 腰/Biped COM/Pelvis",
            "",
            f"- 腰带贴图搜索区：`{belt.get('roi')}`",
            f"- 候选像素数量：`{belt.get('candidateCount')}`",
            f"- 候选腰带加权中心行：`{belt.get('centroidY')}`",
            f"- 低腰目标行（候选下分位）：`{belt.get('centerY')}`",
            "- 解释：前视贴图语义图只负责说明低腰目标来自哪里；Biped COM/Pelvis 是否采用了这个位置，要看 `texture_wire_compare_front` 右侧或 `wire_bone_front`。",
        ]
    lines += [
        "",
        "### 头部与外部挂件",
        "",
        "- HeadTop 仍表示脱帽后的头壳/头盔体积上端，CrestTop 只作为非变形外部装饰参考。",
        "- 侧视配对图用右侧 wire+bones 检查 Biped Neck/Head 是否落在脱帽后的头壳/头盔体积内，再用 HeadTop guide 确认没有追到高位羽饰。",
        "",
        "### 脚部",
        "",
        "- 宽袍、裙摆、披风或靴筒会让腿部外轮廓比真实腿链更宽；腿部判定必须看隐藏腿的合理轴线和可见脚/靴 pivot，不能让 Hip/Knee/Ankle 追衣服边。",
        "- 侧视配对图用右侧 wire+bones 检查 Heel/Foot/Toe 是否贴近脚底支撑形状，是否仍有明显歪斜或偏离重心。",
        "",
        "## MR 式切片",
        "",
        "切片图在每根高风险骨段的 25%、50%、75% 位置截取局部点云。灰点是模型截面采样，橙色圆/点是骨骼显示粗细和中心。它回答两个问题：骨骼中心是否在肢体内部，骨骼显示粗细是否与局部体积相称。",
        "",
    ]
    slice_keys = sorted(key for key in images if key.startswith("slice_"))
    if slice_keys:
        for key in slice_keys:
            lines.append(f"- `{key}`: `{images[key]}`")
    else:
        lines.append("- 本 run 未生成切片图。")

    lines += ["", "## 切片诊断摘要", ""]
    segments = slice_analysis.get("segments", {}) if isinstance(slice_analysis, dict) else {}
    if segments:
        for key, item in sorted(segments.items()):
            samples = item.get("samples", [])
            inside_count = sum(1 for sample in samples if sample.get("insideBodySection"))
            states = sorted({sample.get("thicknessState", "unknown") for sample in samples})
            lines.append(f"- `{key}`: inside sections `{inside_count}/{len(samples)}`, thickness `{', '.join(states)}`")
    else:
        lines.append("- 无切片诊断数据。")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def semantic_blockers(skin_gate: dict[str, Any], rig_detail: dict[str, Any]) -> list[dict[str, Any]]:
    blockers = skin_gate.get("semanticSkinBlockers")
    if isinstance(blockers, list):
        return [item for item in blockers if isinstance(item, dict)]
    risks = rig_detail.get("semanticSkinReview", {}).get("risks", [])
    return [
        item
        for item in risks
        if isinstance(item, dict) and item.get("severity") == "skin_blocker"
    ]


def write_review_input(
    path: Path,
    *,
    asset_name: str,
    run_dir: Path,
    manifest: dict[str, Any],
    blockers: list[dict[str, Any]],
) -> None:
    lines = [
        f"# Semantic Visual Review Input: {asset_name}",
        "",
        "Decision policy: `visual_semantic_gate_only`.",
        "Do not produce numeric scores. Return only blocker/pass/uncertain decisions using `review_schema.json`.",
        "",
        "## Full context images",
        "",
    ]
    for key in ["full_front", "full_side", "full_top"]:
        value = manifest["images"].get(key, "")
        if value:
            lines.append(f"- `{key}`: `{value}`")
    lines += ["", "## Textured context images", ""]
    for key in ["textured_front", "textured_side", "textured_top"]:
        value = manifest["images"].get(key, "")
        if value:
            lines.append(f"- `{key}`: `{value}`")
    if not any(manifest["images"].get(key, "") for key in ["textured_front", "textured_side", "textured_top"]):
        lines.append("- None generated; check `reports/*_stage01_batch_summary.md` for render errors.")
    lines += ["", "## Wireframe + bone technical images", ""]
    for key in ["wire_bone_front", "wire_bone_side", "wire_bone_top"]:
        value = manifest["images"].get(key, "")
        if value:
            lines.append(f"- `{key}`: `{value}`")
    if not any(manifest["images"].get(key, "") for key in ["wire_bone_front", "wire_bone_side", "wire_bone_top"]):
        lines.append("- None generated; check `reports/*_stage01_batch_summary.md` for render errors.")
    lines += ["", "## Textured semantic overlays", ""]
    for key in ["semantic_textured_front", "semantic_textured_side", "semantic_textured_top"]:
        value = manifest["images"].get(key, "")
        if value:
            lines.append(f"- `{key}`: `{value}`")
    if not any(manifest["images"].get(key, "") for key in ["semantic_textured_front", "semantic_textured_side", "semantic_textured_top"]):
        lines.append("- None generated; textured screenshots may be missing or unreadable.")
    lines += ["", "## Texture semantic + real wire/bone comparisons", ""]
    for key in ["texture_wire_compare_front", "texture_wire_compare_side", "texture_wire_compare_top"]:
        value = manifest["images"].get(key, "")
        if value:
            lines.append(f"- `{key}`: `{value}`")
    if not any(manifest["images"].get(key, "") for key in ["texture_wire_compare_front", "texture_wire_compare_side", "texture_wire_compare_top"]):
        lines.append("- None generated; wire_bone screenshots may be missing or unreadable.")
    lines += ["", "## MR-style cross sections", ""]
    slice_keys = sorted(key for key in manifest["images"] if key.startswith("slice_"))
    if slice_keys:
        for key in slice_keys:
            lines.append(f"- `{key}`: `{manifest['images'][key]}`")
    else:
        lines.append("- None generated; check `visual_review/landmark_reasoning.md` for details.")
    lines += ["", "## Region crops", ""]
    for key, value in sorted(manifest["images"].items()):
        if key.startswith("full_") or key.startswith("textured_") or key.startswith("wire_bone_") or key.startswith("semantic_textured_") or key.startswith("texture_wire_compare_") or key.startswith("slice_"):
            continue
        lines.append(f"- `{key}`: `{value}`")
    lines += ["", "## Current semantic blockers", ""]
    if blockers:
        for blocker in blockers:
            code = blocker.get("code", "semantic_skin_blocker")
            evidence = ", ".join(manifest["blockerEvidence"].get(code, []))
            lines.append(f"- `{code}`: {blocker.get('message', '')} Evidence: `{evidence}`")
    else:
        lines.append("- None recorded.")
    lines += [
        "",
        "## Required review questions",
        "",
        "- Front wrap: confirm the centerline chain and both arms/legs sit inside the front silhouette and follow the visible limb centers.",
        "- Side wrap: confirm torso, pelvis, knees, ankles, feet and head are inside the side-view volume, not floating in front of or behind the mesh.",
        "- Top wrap: confirm shoulders, hands, pelvis, knees, feet and toe direction are inside the top-view footprint and follow the model depth.",
        "- Biped COM/Pelvis: confirm COM is at the visual waist and control-only, and Pelvis starts body deformation.",
        "- Texture trace: confirm the cyan belt/waist texture search evidence and the paired real wire/bone view support the Biped COM/Pelvis placement, or mark uncertain/blocker.",
        "- Cross sections: confirm high-risk slices show bone centers inside the local body volume and display thickness is reasonable.",
        "- Leg clothing occlusion: if robe, skirt, cape or boot volume hides the real leg, confirm hip/knee/ankle are judged from under-clothing anatomy plus visible foot/boot pivots, not the clothing outline.",
        "- HeadTop/CrestTop: confirm HeadTop is skull/helmet volume and CrestTop is non-deforming crest/headwear reference.",
        "- Hands: confirm whether each hand mass needs Biped fingers or explicit Biped detail structure.",
        "- Feet: confirm rear-foot, toe/front-foot and knee bend direction from side/top views.",
        "- Deferred details: list crest, beak, cloth, weapon, wing or accessory needs that must be represented in the Biped-only rig plan before Skin.",
        "",
        "## Output files",
        "",
        f"- Schema: `{rel(run_dir / 'visual_review' / 'review_schema.json', run_dir)}`",
        f"- Review template: `{rel(run_dir / 'visual_review' / 'semantic_visual_review_template.json', run_dir)}`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a visual evidence pack for semantic Stage01 review.")
    parser.add_argument("snapshot_json")
    parser.add_argument("--asset-name", default="")
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--visual-qc-json", default="")
    parser.add_argument("--rig-detail-review-json", default="")
    parser.add_argument("--skin-prep-gate-json", default="")
    parser.add_argument("--body-profile-json", default="")
    args = parser.parse_args()

    snapshot_path = Path(args.snapshot_json)
    snapshot = load_json(snapshot_path)
    if not snapshot:
        raise FileNotFoundError(f"visual snapshot not found or invalid: {snapshot_path}")

    asset_name = args.asset_name or snapshot.get("assetName") or snapshot_path.name.replace("_visual_snapshot.json", "")
    run_dir = Path(args.out_dir) if args.out_dir else snapshot_path.parent.parent
    review_dir = run_dir / "visual_review"
    full_dir = review_dir / "full"
    region_dir = review_dir / "regions"
    semantic_dir = review_dir / "semantic_analysis"
    slice_dir = review_dir / "slices"
    review_dir.mkdir(parents=True, exist_ok=True)
    full_dir.mkdir(parents=True, exist_ok=True)
    region_dir.mkdir(parents=True, exist_ok=True)
    semantic_dir.mkdir(parents=True, exist_ok=True)
    slice_dir.mkdir(parents=True, exist_ok=True)

    visual_qc = load_json(args.visual_qc_json)
    rig_detail = load_json(args.rig_detail_review_json)
    skin_gate = load_json(args.skin_prep_gate_json)
    body_profile = load_json(args.body_profile_json)

    images: dict[str, str] = {}
    images.update(textured_images(run_dir, asset_name))
    images.update(wire_bone_images(run_dir, asset_name))
    semantic_images, semantic_analysis = draw_textured_semantic_overlays(run_dir, asset_name, snapshot, semantic_dir)
    images.update(semantic_images)
    slice_images, slice_analysis = write_slice_analysis(run_dir, asset_name, snapshot, slice_dir)
    images.update(slice_images)
    for view in VIEWS:
        path = full_dir / f"{asset_name}_full_{view}.png"
        draw_evidence_view(snapshot, view, path, visual_qc=visual_qc)
        images[f"full_{view}"] = rel(path, run_dir)

    for region, guides in REGION_GUIDES.items():
        points = region_points(snapshot, region)
        for view in REGION_VIEWS[region]:
            path = region_dir / f"{asset_name}_{region}_{view}.png"
            draw_evidence_view(
                snapshot,
                view,
                path,
                visual_qc=visual_qc,
                crop_points=points,
                highlight_guides=guides,
            )
            images[f"{region}_{view}"] = rel(path, run_dir)

    blockers = semantic_blockers(skin_gate, rig_detail)
    policy_evidence = {
        code: [images[key] for key in keys if key in images]
        for code, keys in BLOCKER_REGIONS.items()
    }
    active_blocker_codes = {item.get("code") for item in blockers if isinstance(item, dict)}
    blocker_evidence = {code: evidence for code, evidence in policy_evidence.items() if code in active_blocker_codes}

    schema_path = review_dir / "review_schema.json"
    template_path = review_dir / "semantic_visual_review_template.json"
    manifest_path = review_dir / f"{asset_name}_visual_evidence_manifest.json"
    input_path = review_dir / "review_input.md"
    method_path = review_dir / "visual_method_assessment.md"
    reasoning_path = review_dir / "landmark_reasoning.md"
    semantic_analysis_path = semantic_dir / "texture_semantic_analysis.json"
    slice_analysis_path = slice_dir / "slice_analysis.json"
    atlas_images = texture_atlas_images(run_dir)

    schema_path.write_text(json.dumps(review_schema(), ensure_ascii=False, indent=2), encoding="utf-8")
    template_path.write_text(
        json.dumps(review_template(asset_name, images), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    manifest = {
        "assetName": asset_name,
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "decisionPolicy": "visual_semantic_gate_only",
        "scorePolicy": "scores_disabled_for_decision_diagnostic_only",
        "sourceSnapshot": rel(snapshot_path, run_dir),
        "bodyType": body_profile.get("bodyType", "unknown"),
        "images": images,
        "textureSemanticAnalysis": rel(semantic_analysis_path, run_dir),
        "sliceAnalysis": rel(slice_analysis_path, run_dir),
        "landmarkReasoning": rel(reasoning_path, run_dir),
        "blockerEvidence": blocker_evidence,
        "policyEvidence": policy_evidence,
        "textureAtlasImages": atlas_images,
        "semanticSkinBlockers": blockers,
        "reviewSchema": rel(schema_path, run_dir),
        "reviewTemplate": rel(template_path, run_dir),
        "reviewInput": rel(input_path, run_dir),
        "methodAssessment": rel(method_path, run_dir),
    }
    semantic_analysis_path.write_text(json.dumps(semantic_analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    slice_analysis_path.write_text(json.dumps(slice_analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_review_input(input_path, asset_name=asset_name, run_dir=run_dir, manifest=manifest, blockers=blockers)
    write_method_assessment(method_path, asset_name=asset_name, images=images, atlas_images=atlas_images)
    write_landmark_reasoning(
        reasoning_path,
        asset_name=asset_name,
        run_dir=run_dir,
        images=images,
        semantic_analysis=semantic_analysis,
        slice_analysis=slice_analysis,
    )

    readme_lines = [
        f"# Visual Review Pack: {asset_name}",
        "",
        "This folder contains visual evidence for semantic Stage01 review. It is not a score report.",
        "",
        "- `full/`: full front, side and top context images.",
        "- `regions/`: cropped high-risk regions for head, pelvis, hands and feet.",
        "- `semantic_analysis/`: texture-only semantic evidence images, paired texture-vs-wire comparison images and machine-readable texture trace data.",
        "- `slices/`: MR-style cross sections for high-risk bones.",
        "- `../wire_bone_screenshots/`: 3ds Max wireframe + bone technical views referenced by this pack when available.",
        "- `review_schema.json`: strict review output shape for human/VLM review.",
        "- `semantic_visual_review_template.json`: blank review result to fill.",
        "- `review_input.md`: concise review prompt and evidence list.",
        "- `landmark_reasoning.md`: explains how texture evidence, real Max wire+bones and slices should be read together.",
        "- `visual_method_assessment.md`: available visual methods and their limitations.",
        f"- `{manifest_path.name}`: machine-readable manifest.",
    ]
    (review_dir / "README.md").write_text("\n".join(readme_lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "assetName": asset_name,
                "visualReviewDir": str(review_dir),
                "manifest": str(manifest_path),
                "reviewInput": str(input_path),
                "imageCount": len(images),
                "semanticBlockerCount": len(blockers),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
