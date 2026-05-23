from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from typing import Any

from visual_review_pack import (
    SLICE_SAMPLE_STATIONS,
    RgbImage,
    radial_coverage,
    convex_hull,
    point_in_polygon,
    vec_add,
    vec_cross,
    vec_dot,
    vec_length,
    vec_norm,
    vec_scale,
    vec_sub,
    write_slice_analysis,
)


ORDERED_SEGMENTS: list[tuple[str, str]] = [
    ("Pelvis", "Spine"),
    ("Spine", "Chest"),
    ("Chest", "Neck"),
    ("Neck", "Head"),
    ("Pelvis", "L_Hip"),
    ("L_Hip", "L_Knee"),
    ("L_Knee", "L_Ankle"),
    ("L_Ankle", "L_Toe"),
    ("Pelvis", "R_Hip"),
    ("R_Hip", "R_Knee"),
    ("R_Knee", "R_Ankle"),
    ("R_Ankle", "R_Toe"),
    ("Chest", "L_Clavicle"),
    ("L_Clavicle", "L_Shoulder"),
    ("L_Shoulder", "L_Elbow"),
    ("L_Elbow", "L_Wrist"),
    ("Chest", "R_Clavicle"),
    ("R_Clavicle", "R_Shoulder"),
    ("R_Shoulder", "R_Elbow"),
    ("R_Elbow", "R_Wrist"),
]

LEG_CHAINS: list[dict[str, Any]] = [
    {
        "name": "left_leg",
        "nodes": ["L_Hip", "L_Knee", "L_Ankle", "L_Toe"],
        "segments": [
            ("Pelvis", "L_Hip"),
            ("L_Hip", "L_Knee"),
            ("L_Knee", "L_Ankle"),
            ("L_Ankle", "L_Toe"),
        ],
    },
    {
        "name": "right_leg",
        "nodes": ["R_Hip", "R_Knee", "R_Ankle", "R_Toe"],
        "segments": [
            ("Pelvis", "R_Hip"),
            ("R_Hip", "R_Knee"),
            ("R_Knee", "R_Ankle"),
            ("R_Ankle", "R_Toe"),
        ],
    },
]

PROBE_STATIONS = list(SLICE_SAMPLE_STATIONS)
FLOOR_CLAMP = True


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def robust_center(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    lo = ordered[max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.12))))]
    hi = ordered[max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.88))))]
    return (lo + hi) * 0.5


def classify_coords(coords: list[tuple[float, float]]) -> dict[str, Any]:
    hull = convex_hull(coords)
    hull_contains_center = point_in_polygon((0.0, 0.0), hull)
    radial = radial_coverage(coords)
    strict = (
        len(coords) >= 12
        and hull_contains_center
        and radial["sectorCoverage"] >= 0.62
        and radial["quadrantCount"] == 4
    )
    if len(coords) < 12:
        state = "insufficient_slice_points"
    elif not hull_contains_center:
        state = "center_outside_cross_section_hull"
    elif radial["quadrantCount"] < 4 or radial["sectorCoverage"] < 0.62:
        state = "insufficient_radial_wrap"
    else:
        state = "strictly_wrapped"
    return {
        "strict": strict,
        "wrapState": state,
        "pointCount": len(coords),
        "hullContainsCenter": hull_contains_center,
        "radialCoverage": radial,
    }


def bone_map(snapshot: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (str(bone.get("start", "")), str(bone.get("end", ""))): bone
        for bone in snapshot.get("bipedBones", [])
    }


def node_positions(snapshot: dict[str, Any]) -> dict[str, list[float]]:
    nodes = snapshot.get("bipedNodes", {})
    return {str(name): [float(v) for v in value] for name, value in nodes.items()}


def node_floor_z(snapshot: dict[str, Any], node_name: str) -> float | None:
    bounds = snapshot.get("bounds", {})
    min_z = float(bounds.get("min", [0.0, 0.0, 0.0])[2])
    height = snapshot_height(snapshot)
    if node_name.endswith("_Toe") or node_name.endswith("_Foot") or node_name.endswith("_Heel"):
        return min_z + height * 0.015
    if node_name.endswith("_Ankle"):
        return min_z + height * 0.025
    if node_name.endswith("_Knee"):
        return min_z + height * 0.075
    return None


def clamp_nodes_to_body_floor(snapshot: dict[str, Any], nodes: dict[str, list[float]]) -> dict[str, list[float]]:
    clamped = clone_nodes(nodes)
    for name, value in clamped.items():
        floor_z = node_floor_z(snapshot, name)
        if floor_z is not None and value[2] < floor_z:
            value[2] = floor_z
    return clamped


def update_snapshot_nodes(snapshot: dict[str, Any], nodes: dict[str, list[float]]) -> None:
    if FLOOR_CLAMP:
        nodes = clamp_nodes_to_body_floor(snapshot, nodes)
    snapshot["bipedNodes"] = {name: [round(v, 6) for v in value] for name, value in nodes.items()}
    for bone in snapshot.get("bipedBones", []):
        start = str(bone.get("start", ""))
        end = str(bone.get("end", ""))
        if start in nodes:
            bone["startPosition"] = [round(v, 6) for v in nodes[start]]
        if end in nodes:
            bone["endPosition"] = [round(v, 6) for v in nodes[end]]
        if start in nodes and end in nodes:
            bone["boneLength"] = round(vec_length(vec_sub(nodes[end], nodes[start])), 6)


def clone_nodes(nodes: dict[str, list[float]]) -> dict[str, list[float]]:
    return {name: list(value) for name, value in nodes.items()}


def snapshot_height(snapshot: dict[str, Any]) -> float:
    bounds = snapshot.get("bounds", {})
    return max(float(bounds.get("size", [0, 0, 1])[2]), 1.0)


def segment_axes(start: list[float], end: list[float]) -> tuple[list[float], list[float], list[float], float]:
    axis_vec = vec_sub(end, start)
    length = vec_length(axis_vec)
    axis = vec_norm(axis_vec)
    ref = [0.0, 0.0, 1.0]
    if abs(vec_dot(axis, ref)) > 0.86:
        ref = [1.0, 0.0, 0.0]
    u_axis = vec_norm(vec_cross(axis, ref))
    v_axis = vec_norm(vec_cross(axis, u_axis))
    return axis, u_axis, v_axis, length


def is_foot_segment(start_name: str, end_name: str) -> bool:
    return start_name.endswith("_Ankle") and end_name.endswith("_Toe")


def apply_foot_planar_rule(
    snapshot: dict[str, Any],
    sample: dict[str, Any],
    *,
    segment_length: float,
    height: float,
) -> None:
    if sample["strict"]:
        return
    radial = sample["radialCoverage"]
    point_count = int(sample["pointCount"])
    foot_offset_tolerance = max(height * 0.075, segment_length * 0.35)
    toe_endpoint_tolerance = max(height * 0.12, segment_length * 0.55)

    if point_count >= 12:
        planar_hull_wrap = (
            sample["hullContainsCenter"]
            and radial["quadrantCount"] >= 3
            and radial["sectorCoverage"] >= 0.38
        )
        near_foot_plane = (
            sample["offsetLength"] <= foot_offset_tolerance
            and radial["sectorCoverage"] >= 0.25
            and radial["quadrantCount"] >= 2
        )
        if planar_hull_wrap or near_foot_plane:
            sample["strict"] = True
            sample["wrapState"] = "foot_planar_wrapped"
        return

    nearest = nearest_mesh_distance(snapshot, sample["center"])
    sample["nearestDistance"] = nearest
    if float(sample["t"]) >= 0.75 and nearest <= toe_endpoint_tolerance:
        sample["strict"] = True
        sample["wrapState"] = "foot_endpoint_close"


def segment_samples(
    snapshot: dict[str, Any],
    start_name: str,
    end_name: str,
    *,
    foot_planar: bool = False,
) -> list[dict[str, Any]]:
    nodes = node_positions(snapshot)
    if start_name not in nodes or end_name not in nodes:
        return []
    start = nodes[start_name]
    end = nodes[end_name]
    axis_vec = vec_sub(end, start)
    axis, u_axis, v_axis, length = segment_axes(start, end)
    if length <= 1e-6:
        return []
    height = snapshot_height(snapshot)
    slab = max(height * 0.018, length * 0.10, 1.0)
    mesh_points = snapshot.get("meshPoints", [])
    samples: list[dict[str, Any]] = []
    for t in PROBE_STATIONS:
        center = vec_add(start, vec_scale(axis_vec, float(t)))
        coords: list[tuple[float, float]] = []
        for point in mesh_points:
            delta = vec_sub(point, center)
            if abs(vec_dot(delta, axis)) <= slab:
                coords.append((vec_dot(delta, u_axis), vec_dot(delta, v_axis)))
        info = classify_coords(coords)
        info["t"] = float(t)
        info["center"] = center
        info["offset3d"] = [0.0, 0.0, 0.0]
        if coords:
            u_center = robust_center([c[0] for c in coords])
            v_center = robust_center([c[1] for c in coords])
            info["offset3d"] = vec_add(vec_scale(u_axis, u_center), vec_scale(v_axis, v_center))
            info["offsetLength"] = vec_length(info["offset3d"])
        else:
            info["offsetLength"] = 0.0
        if foot_planar and is_foot_segment(start_name, end_name):
            apply_foot_planar_rule(snapshot, info, segment_length=length, height=height)
        samples.append(info)
    return samples


def nearest_mesh_distance(snapshot: dict[str, Any], center: list[float]) -> float:
    mesh_points = snapshot.get("meshPoints", [])
    if not mesh_points:
        return 0.0
    return min(vec_length(vec_sub(point, center)) for point in mesh_points)


def sample_failure_penalty(snapshot: dict[str, Any], sample: dict[str, Any]) -> float:
    if sample["strict"]:
        return 0.0
    height = snapshot_height(snapshot)
    point_count = int(sample["pointCount"])
    radial = sample["radialCoverage"]
    missing_points = max(0.0, (12.0 - float(point_count)) / 12.0)
    sector_gap = max(0.0, 0.62 - float(radial["sectorCoverage"])) / 0.62
    quadrant_gap = max(0.0, 4.0 - float(radial["quadrantCount"])) / 4.0
    if point_count < 12:
        offset = nearest_mesh_distance(snapshot, sample["center"])
    else:
        offset = float(sample.get("offsetLength", 0.0))
    offset_penalty = min(offset / max(height * 0.20, 1.0), 4.0)
    return 1.0 + missing_points * 2.0 + sector_gap + quadrant_gap + offset_penalty


def evaluate(
    snapshot: dict[str, Any],
    severity_segments: set[str] | None = None,
    *,
    foot_planar: bool = False,
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    by_segment: dict[str, int] = {}
    by_segment_severity: dict[str, float] = {}
    total_severity = 0.0
    for start, end in ORDERED_SEGMENTS:
        segment = f"{start}->{end}"
        count = 0
        severity = 0.0
        collect_severity = severity_segments is None or segment in severity_segments
        for sample in segment_samples(snapshot, start, end, foot_planar=foot_planar):
            if not sample["strict"]:
                penalty = sample_failure_penalty(snapshot, sample) if collect_severity else 0.0
                count += 1
                severity += penalty
                total_severity += penalty
                failure = {
                    "segment": segment,
                    "t": sample["t"],
                    "wrapState": sample["wrapState"],
                    "pointCount": sample["pointCount"],
                }
                if collect_severity:
                    failure["penalty"] = round(penalty, 6)
                failures.append(failure)
        by_segment[segment] = count
        by_segment_severity[segment] = round(severity, 6)
    return {
        "failureCount": len(failures),
        "severity": round(total_severity, 6),
        "failures": failures,
        "bySegment": by_segment,
        "bySegmentSeverity": by_segment_severity,
    }


def clamp(vec: list[float], max_len: float) -> list[float]:
    length = vec_length(vec)
    if length <= max_len or length <= 1e-8:
        return vec
    return vec_scale(vec, max_len / length)


def axis_fallback_moves(max_step: float) -> list[list[float]]:
    moves: list[list[float]] = []
    axes = [
        [1.0, 0.0, 0.0],
        [-1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, -1.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.0, 0.0, -1.0],
    ]
    for fraction in (0.25, 0.5, 1.0):
        for axis in axes:
            moves.append(vec_scale(axis, max_step * fraction))
    return moves


def candidate_moves(
    snapshot: dict[str, Any],
    start: str,
    end: str,
    node: str,
    max_step: float,
    *,
    include_axis_fallback: bool = True,
) -> list[list[float]]:
    moves: list[list[float]] = []
    samples = segment_samples(snapshot, start, end)
    for sample in samples:
        if sample["strict"] or sample["pointCount"] < 12:
            continue
        t = float(sample["t"])
        offset = sample["offset3d"]
        if vec_length(offset) <= 1e-6:
            continue
        if node == end:
            influence = max(t, 0.25)
        else:
            influence = max(1.0 - t, 0.25)
        scale = 1.0 / influence
        move = clamp(vec_scale(offset, scale), max_step)
        moves.append(move)
        moves.append(vec_scale(move, 0.5))
        moves.append(vec_scale(move, 0.25))

    if include_axis_fallback:
        moves.extend(axis_fallback_moves(max_step))

    # Keep candidate list deterministic and compact.
    unique: dict[tuple[int, int, int], list[float]] = {}
    for move in moves:
        if vec_length(move) <= 1e-6:
            continue
        key = tuple(int(round(v * 1000)) for v in move)
        unique[key] = move
    return list(unique.values())


def nearest_mesh_offset(snapshot: dict[str, Any], center: list[float], *, k: int = 48) -> list[float]:
    mesh_points = snapshot.get("meshPoints", [])
    if not mesh_points:
        return [0.0, 0.0, 0.0]
    nearest = sorted(
        ((vec_length(vec_sub(point, center)), point) for point in mesh_points),
        key=lambda row: row[0],
    )[: max(1, min(k, len(mesh_points)))]
    return [
        robust_center([float(point[axis]) - center[axis] for _, point in nearest])
        for axis in range(3)
    ]


def low_point_recovery_moves(
    snapshot: dict[str, Any],
    start: str,
    end: str,
    node: str,
    max_step: float,
) -> list[list[float]]:
    moves: list[list[float]] = []
    samples = segment_samples(snapshot, start, end)
    height = snapshot_height(snapshot)
    max_nearest_distance = max(height * 0.35, max_step * 6.0)
    for sample in samples:
        if sample["strict"] or sample["pointCount"] >= 12:
            continue
        t = float(sample["t"])
        influence = t if node == end else 1.0 - t
        if influence <= 0.05:
            continue
        offset = nearest_mesh_offset(snapshot, sample["center"])
        distance = vec_length(offset)
        if distance <= 1e-6 or distance > max_nearest_distance:
            continue
        move = clamp(vec_scale(offset, 1.0 / influence), max_step)
        moves.extend([move, vec_scale(move, 0.5), vec_scale(move, 0.25)])
    return unique_moves(moves)


def segment_translation_moves(snapshot: dict[str, Any], start: str, end: str, max_step: float) -> list[list[float]]:
    moves: list[list[float]] = []
    height = snapshot_height(snapshot)
    max_nearest_distance = max(height * 0.35, max_step * 6.0)
    for sample in segment_samples(snapshot, start, end):
        if sample["strict"]:
            continue
        if sample["pointCount"] >= 12:
            offset = sample.get("offset3d") or [0.0, 0.0, 0.0]
        else:
            offset = nearest_mesh_offset(snapshot, sample["center"])
            if vec_length(offset) > max_nearest_distance:
                continue
        if vec_length(offset) <= 1e-6:
            continue
        move = clamp(offset, max_step)
        moves.extend([move, vec_scale(move, 0.5), vec_scale(move, 0.25)])
    return unique_moves(moves)


def unique_moves(moves: list[list[float]]) -> list[list[float]]:
    unique: dict[tuple[int, int, int], list[float]] = {}
    for move in moves:
        if vec_length(move) <= 1e-6:
            continue
        key = tuple(int(round(v * 1000)) for v in move)
        unique[key] = move
    return list(unique.values())


def chain_translation_moves(
    snapshot: dict[str, Any],
    chain_segments: list[tuple[str, str]],
    max_step: float,
) -> list[list[float]]:
    moves: list[list[float]] = []
    for start, end in chain_segments:
        moves.extend(segment_translation_moves(snapshot, start, end, max_step))
    return unique_moves(moves)


def segments_share_node(a: tuple[str, str], b: tuple[str, str]) -> bool:
    return a[0] in b or a[1] in b


def segment_prefers_axis_with_data(segment: tuple[str, str]) -> bool:
    names = f"{segment[0]} {segment[1]}"
    return any(token in names for token in ("Shoulder", "Elbow", "Wrist", "Clavicle"))


def score_detail(
    snapshot: dict[str, Any],
    locked: list[tuple[str, str]],
    active: tuple[str, str],
) -> tuple[tuple[int, int, int, int], tuple[float, float, float, float]]:
    active_key = f"{active[0]}->{active[1]}"
    related_segments = [
        (s, e)
        for s, e in ORDERED_SEGMENTS
        if segments_share_node((s, e), active)
    ]
    severity_keys = {active_key}
    severity_keys.update(f"{s}->{e}" for s, e in locked)
    severity_keys.update(f"{s}->{e}" for s, e in related_segments)
    result = evaluate(snapshot, severity_keys)
    locked_failures = sum(result["bySegment"].get(f"{s}->{e}", 0) for s, e in locked)
    related_failures = sum(
        result["bySegment"].get(f"{s}->{e}", 0)
        for s, e in related_segments
    )
    active_failures = result["bySegment"].get(active_key, 0)
    locked_severity = sum(result["bySegmentSeverity"].get(f"{s}->{e}", 0.0) for s, e in locked)
    related_severity = sum(
        result["bySegmentSeverity"].get(f"{s}->{e}", 0.0)
        for s, e in related_segments
    )
    active_severity = result["bySegmentSeverity"].get(active_key, 0.0)
    return (
        (active_failures, locked_failures, related_failures, result["failureCount"]),
        (
            round(active_severity, 6),
            round(locked_severity, 6),
            round(related_severity, 6),
            round(float(result["severity"]), 6),
        ),
    )


def score(snapshot: dict[str, Any], locked: list[tuple[str, str]], active: tuple[str, str]) -> tuple[int, int, int, int]:
    counts, _ = score_detail(snapshot, locked, active)
    return counts


def chain_score(snapshot: dict[str, Any], chain_segments: list[tuple[str, str]]) -> tuple[int, int, int]:
    counts, _ = chain_score_detail(snapshot, chain_segments)
    return counts


def chain_score_detail(
    snapshot: dict[str, Any],
    chain_segments: list[tuple[str, str]],
) -> tuple[tuple[int, int, int], tuple[float, float, float]]:
    keys = {f"{start}->{end}" for start, end in chain_segments}
    result = evaluate(snapshot, keys)
    chain_failures = sum(result["bySegment"].get(key, 0) for key in keys)
    global_failures = result["failureCount"]
    outside_failures = global_failures - chain_failures
    chain_severity = sum(result["bySegmentSeverity"].get(key, 0.0) for key in keys)
    global_severity = float(result["severity"])
    outside_severity = global_severity - chain_severity
    return (
        (chain_failures, outside_failures, global_failures),
        (round(chain_severity, 6), round(outside_severity, 6), round(global_severity, 6)),
    )


def protected_score_regressed(
    trial_counts: tuple[int, ...],
    current_counts: tuple[int, ...],
    trial_severity: tuple[float, ...],
    current_severity: tuple[float, ...],
    protected_indices: tuple[int, ...],
) -> bool:
    for index in protected_indices:
        if trial_counts[index] > current_counts[index]:
            return True
        if trial_counts[index] == current_counts[index] and trial_severity[index] > current_severity[index] + 1e-4:
            return True
    return False


def segment_score_better(
    trial_counts: tuple[int, int, int, int],
    trial_severity: tuple[float, float, float, float],
    best_counts: tuple[int, int, int, int],
    best_severity: tuple[float, float, float, float],
) -> bool:
    if trial_counts[0] < best_counts[0]:
        return True
    if trial_counts[0] == best_counts[0] and trial_counts[2] < best_counts[2]:
        return True
    if trial_counts[0] == best_counts[0] and trial_counts[2] == best_counts[2] and trial_counts[3] < best_counts[3]:
        return True
    counts_tied = trial_counts[0] == best_counts[0] and trial_counts[2] == best_counts[2] and trial_counts[3] == best_counts[3]
    if counts_tied and trial_severity[0] < best_severity[0] - 1e-4:
        return True
    if counts_tied and abs(trial_severity[0] - best_severity[0]) <= 1e-4 and trial_severity[2] < best_severity[2] - 1e-4:
        return True
    if counts_tied and abs(trial_severity[0] - best_severity[0]) <= 1e-4 and abs(trial_severity[2] - best_severity[2]) <= 1e-4:
        return trial_severity[3] < best_severity[3] - 1e-4
    return False


def chain_score_better(
    trial_counts: tuple[int, int, int],
    trial_severity: tuple[float, float, float],
    best_counts: tuple[int, int, int],
    best_severity: tuple[float, float, float],
) -> bool:
    if trial_counts[0] < best_counts[0]:
        return True
    if trial_counts[0] == best_counts[0] and trial_counts[2] < best_counts[2]:
        return True
    counts_tied = trial_counts[0] == best_counts[0] and trial_counts[2] == best_counts[2]
    if counts_tied and trial_severity[0] < best_severity[0] - 1e-4:
        return True
    if counts_tied and abs(trial_severity[0] - best_severity[0]) <= 1e-4:
        return trial_severity[2] < best_severity[2] - 1e-4
    return False


def refine_leg_chain(
    snapshot: dict[str, Any],
    chain: dict[str, Any],
    *,
    max_chain_iters: int,
    max_step: float,
    allow_node_moves: bool,
) -> dict[str, Any]:
    chain_segments = [(str(start), str(end)) for start, end in chain["segments"]]
    chain_nodes = [str(node) for node in chain["nodes"]]
    current, current_severity = chain_score_detail(snapshot, chain_segments)
    before = current
    before_severity = current_severity
    trace: list[dict[str, Any]] = []
    accepted_moves = 0
    stop_reason = "already_green" if current[0] == 0 else "no_positive_candidate"
    if current[0] == 0:
        return {
            "chain": chain["name"],
            "before": current,
            "after": current,
            "beforeSeverity": current_severity,
            "afterSeverity": current_severity,
            "acceptedMoves": 0,
            "stopReason": stop_reason,
            "trace": trace,
        }

    for iteration in range(1, max_chain_iters + 1):
        nodes = node_positions(snapshot)
        best_nodes: dict[str, list[float]] | None = None
        best_score = current
        best_severity = current_severity
        best_move: list[float] | None = None
        best_move_node = "chain"

        original_nodes = node_positions(snapshot)
        for move in chain_translation_moves(snapshot, chain_segments, max_step):
            trial_nodes = clone_nodes(original_nodes)
            missing = False
            for node in chain_nodes:
                if node not in trial_nodes:
                    missing = True
                    break
                trial_nodes[node] = vec_add(trial_nodes[node], move)
            if missing:
                continue
            update_snapshot_nodes(snapshot, trial_nodes)
            trial_score, trial_severity = chain_score_detail(snapshot, chain_segments)
            update_snapshot_nodes(snapshot, original_nodes)
            if protected_score_regressed(trial_score, current, trial_severity, current_severity, (1, 2)):
                continue
            if chain_score_better(trial_score, trial_severity, best_score, best_severity):
                best_nodes = trial_nodes
                best_score = trial_score
                best_severity = trial_severity
                best_move = move
                best_move_node = "chain"

        if allow_node_moves:
            for move_node in chain_nodes:
                if move_node not in nodes:
                    continue
                adjacent_segments = [segment for segment in chain_segments if move_node in segment]
                moves: list[list[float]] = []
                for start, end in adjacent_segments:
                    moves.extend(candidate_moves(snapshot, start, end, move_node, max_step, include_axis_fallback=False))
                    moves.extend(low_point_recovery_moves(snapshot, start, end, move_node, max_step))
                if not moves:
                    for start, end in adjacent_segments:
                        moves.extend(candidate_moves(snapshot, start, end, move_node, max_step))
                for move in unique_moves(moves):
                    trial_nodes = clone_nodes(original_nodes)
                    trial_nodes[move_node] = vec_add(trial_nodes[move_node], move)
                    update_snapshot_nodes(snapshot, trial_nodes)
                    trial_score, trial_severity = chain_score_detail(snapshot, chain_segments)
                    update_snapshot_nodes(snapshot, original_nodes)
                    if protected_score_regressed(trial_score, current, trial_severity, current_severity, (1, 2)):
                        continue
                    if chain_score_better(trial_score, trial_severity, best_score, best_severity):
                        best_nodes = trial_nodes
                        best_score = trial_score
                        best_severity = trial_severity
                        best_move = move
                        best_move_node = move_node

            if best_nodes is None:
                for move_node in chain_nodes:
                    if move_node not in nodes:
                        continue
                    for move in axis_fallback_moves(max_step):
                        trial_nodes = clone_nodes(original_nodes)
                        trial_nodes[move_node] = vec_add(trial_nodes[move_node], move)
                        update_snapshot_nodes(snapshot, trial_nodes)
                        trial_score, trial_severity = chain_score_detail(snapshot, chain_segments)
                        update_snapshot_nodes(snapshot, original_nodes)
                        if protected_score_regressed(trial_score, current, trial_severity, current_severity, (1, 2)):
                            continue
                        if chain_score_better(trial_score, trial_severity, best_score, best_severity):
                            best_nodes = trial_nodes
                            best_score = trial_score
                            best_severity = trial_severity
                            best_move = move
                            best_move_node = move_node

        if best_nodes is None or (best_score == current and best_severity == current_severity):
            stop_reason = "no_positive_candidate"
            break

        update_snapshot_nodes(snapshot, best_nodes)
        accepted_moves += 1
        trace.append(
            {
                "iteration": iteration,
                "moveNode": best_move_node,
                "move": [round(v, 6) for v in (best_move or [0.0, 0.0, 0.0])],
                "score": {
                    "chain": best_score[0],
                    "outside": best_score[1],
                    "global": best_score[2],
                },
                "severity": {
                    "chain": best_severity[0],
                    "outside": best_severity[1],
                    "global": best_severity[2],
                },
            }
        )
        current = best_score
        current_severity = best_severity
        stop_reason = "chain_green" if current[0] == 0 else "improving"
        if current[0] == 0:
            break

    return {
        "chain": chain["name"],
        "before": before,
        "after": current,
        "beforeSeverity": before_severity,
        "afterSeverity": current_severity,
        "acceptedMoves": accepted_moves,
        "stopReason": stop_reason,
        "trace": trace,
    }


def refine_segment(
    snapshot: dict[str, Any],
    segment: tuple[str, str],
    locked: list[tuple[str, str]],
    *,
    max_segment_iters: int,
    max_step: float,
    allow_start_backtrack: bool,
) -> dict[str, Any]:
    start, end = segment
    trace: list[dict[str, Any]] = []
    before, before_severity = score_detail(snapshot, locked, segment)
    current = before
    current_severity = before_severity
    accepted_moves = 0
    stop_reason = "already_green" if current[0] == 0 else "no_positive_candidate"
    if current[0] == 0:
        return {
            "segment": f"{start}->{end}",
            "before": before,
            "after": current,
            "beforeSeverity": before_severity,
            "afterSeverity": current_severity,
            "acceptedMoves": 0,
            "stopReason": stop_reason,
            "trace": trace,
        }

    for iteration in range(1, max_segment_iters + 1):
        nodes = node_positions(snapshot)
        if end not in nodes:
            stop_reason = "missing_child_node"
            break
        best_nodes: dict[str, list[float]] | None = None
        best_score = current
        best_severity = current_severity
        best_move: list[float] | None = None
        move_nodes = (end, start) if allow_start_backtrack else (end,)
        include_axis_with_data = segment_prefers_axis_with_data(segment)
        original_nodes = node_positions(snapshot)
        for move_node in move_nodes:
            if move_node not in nodes:
                continue
            moves = candidate_moves(
                snapshot,
                start,
                end,
                move_node,
                max_step,
                include_axis_fallback=include_axis_with_data,
            )
            moves.extend(low_point_recovery_moves(snapshot, start, end, move_node, max_step))
            if not moves:
                moves = candidate_moves(snapshot, start, end, move_node, max_step)
            for move in unique_moves(moves):
                trial_nodes = clone_nodes(original_nodes)
                trial_nodes[move_node] = vec_add(trial_nodes[move_node], move)
                update_snapshot_nodes(snapshot, trial_nodes)
                trial_score, trial_severity = score_detail(snapshot, locked, segment)
                update_snapshot_nodes(snapshot, original_nodes)
                # Locked, adjacent, and global sections must not regress.
                if protected_score_regressed(trial_score, current, trial_severity, current_severity, (1, 2, 3)):
                    continue
                if segment_score_better(trial_score, trial_severity, best_score, best_severity):
                    best_nodes = trial_nodes
                    best_score = trial_score
                    best_severity = trial_severity
                    best_move = move
                    best_move_node = move_node

        if start in nodes and end in nodes:
            for move in segment_translation_moves(snapshot, start, end, max_step):
                trial_nodes = clone_nodes(original_nodes)
                trial_nodes[start] = vec_add(trial_nodes[start], move)
                trial_nodes[end] = vec_add(trial_nodes[end], move)
                update_snapshot_nodes(snapshot, trial_nodes)
                trial_score, trial_severity = score_detail(snapshot, locked, segment)
                update_snapshot_nodes(snapshot, original_nodes)
                if protected_score_regressed(trial_score, current, trial_severity, current_severity, (1, 2, 3)):
                    continue
                if segment_score_better(trial_score, trial_severity, best_score, best_severity):
                    best_nodes = trial_nodes
                    best_score = trial_score
                    best_severity = trial_severity
                    best_move = move
                    best_move_node = f"{start}+{end}"

        if best_nodes is None:
            for move_node in move_nodes:
                if move_node not in nodes:
                    continue
                for move in axis_fallback_moves(max_step):
                    trial_nodes = clone_nodes(original_nodes)
                    trial_nodes[move_node] = vec_add(trial_nodes[move_node], move)
                    update_snapshot_nodes(snapshot, trial_nodes)
                    trial_score, trial_severity = score_detail(snapshot, locked, segment)
                    update_snapshot_nodes(snapshot, original_nodes)
                    if protected_score_regressed(trial_score, current, trial_severity, current_severity, (1, 2, 3)):
                        continue
                    if segment_score_better(trial_score, trial_severity, best_score, best_severity):
                        best_nodes = trial_nodes
                        best_score = trial_score
                        best_severity = trial_severity
                        best_move = move
                        best_move_node = move_node
        if best_nodes is None or (best_score == current and best_severity == current_severity):
            stop_reason = "no_positive_candidate"
            break
        update_snapshot_nodes(snapshot, best_nodes)
        accepted_moves += 1
        trace.append(
            {
                "iteration": iteration,
                "moveNode": best_move_node,
                "move": [round(v, 6) for v in (best_move or [0.0, 0.0, 0.0])],
                "score": {
                    "active": best_score[0],
                    "locked": best_score[1],
                    "related": best_score[2],
                    "global": best_score[3],
                },
                "severity": {
                    "active": best_severity[0],
                    "locked": best_severity[1],
                    "related": best_severity[2],
                    "global": best_severity[3],
                },
            }
        )
        current = best_score
        current_severity = best_severity
        if current[0] == 0:
            stop_reason = "segment_green"
            break
    return {
        "segment": f"{start}->{end}",
        "before": before,
        "after": current,
        "beforeSeverity": before_severity,
        "afterSeverity": current_severity,
        "acceptedMoves": accepted_moves,
        "stopReason": stop_reason,
        "trace": trace,
    }


def run_probe(
    snapshot: dict[str, Any],
    max_segment_iters: int,
    allow_start_backtrack: bool,
    max_step_ratio: float,
    *,
    leg_chain_pass: bool,
    max_chain_iters: int,
    leg_chain_node_moves: bool,
) -> dict[str, Any]:
    height = snapshot_height(snapshot)
    max_step = max(height * max_step_ratio, 1.0)
    initial = evaluate(snapshot)
    locked: list[tuple[str, str]] = []
    segment_results: list[dict[str, Any]] = []
    for segment in ORDERED_SEGMENTS:
        result = refine_segment(
            snapshot,
            segment,
            locked,
            max_segment_iters=max_segment_iters,
            max_step=max_step,
            allow_start_backtrack=allow_start_backtrack,
        )
        segment_results.append(result)
        if result["after"][0] == 0:
            locked.append(segment)
    chain_results: list[dict[str, Any]] = []
    if leg_chain_pass:
        for chain in LEG_CHAINS:
            before = chain_score(snapshot, [(str(s), str(e)) for s, e in chain["segments"]])
            result = refine_leg_chain(
                snapshot,
                chain,
                max_chain_iters=max_chain_iters,
                max_step=max_step,
                allow_node_moves=leg_chain_node_moves,
            )
            result["before"] = before
            chain_results.append(result)
    final = evaluate(snapshot)
    final_role_aware = evaluate(snapshot, foot_planar=True)
    return {
        "mode": "ordered_agent_controlled_ct_probe",
        "maxSegmentIterations": max_segment_iters,
        "allowStartBacktrack": allow_start_backtrack,
        "legChainPass": leg_chain_pass,
        "maxChainIterations": max_chain_iters,
        "legChainNodeMoves": leg_chain_node_moves,
        "floorClamp": FLOOR_CLAMP,
        "maxStep": round(max_step, 6),
        "initial": initial,
        "final": final,
        "finalRoleAware": final_role_aware,
        "lockedSegments": [f"{s}->{e}" for s, e in locked],
        "segments": segment_results,
        "chains": chain_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe ordered local CT refinement on a Stage01 visual snapshot.")
    parser.add_argument("snapshot_json")
    parser.add_argument("--asset-name", default="")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--max-segment-iters", type=int, default=16)
    parser.add_argument("--allow-start-backtrack", action="store_true")
    parser.add_argument("--max-step-ratio", type=float, default=0.035)
    parser.add_argument("--leg-chain-pass", action="store_true")
    parser.add_argument("--max-chain-iters", type=int, default=6)
    parser.add_argument("--leg-chain-node-moves", action="store_true")
    parser.add_argument("--floor-clamp", dest="floor_clamp", action="store_true", default=True)
    parser.add_argument("--no-floor-clamp", dest="floor_clamp", action="store_false")
    parser.add_argument(
        "--station-mode",
        choices=["standard", "dense"],
        default="standard",
        help="standard uses 0/25/50/75/100; dense adds midpoints for evidence escalation.",
    )
    parser.add_argument(
        "--skip-slice-images",
        action="store_true",
        help="Only write JSON/Markdown probe outputs; useful for fast algorithm regression samples.",
    )
    args = parser.parse_args()

    snapshot_path = Path(args.snapshot_json)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot = load_json(snapshot_path)
    global PROBE_STATIONS
    global FLOOR_CLAMP
    FLOOR_CLAMP = bool(args.floor_clamp)
    if args.station_mode == "dense":
        PROBE_STATIONS = [0.0, 0.125, 0.25, 0.375, 0.50, 0.625, 0.75, 0.875, 1.0]
    else:
        PROBE_STATIONS = list(SLICE_SAMPLE_STATIONS)
    asset_name = args.asset_name or str(snapshot.get("assetName") or snapshot_path.stem)

    working = copy.deepcopy(snapshot)
    result = run_probe(
        working,
        args.max_segment_iters,
        args.allow_start_backtrack,
        args.max_step_ratio,
        leg_chain_pass=args.leg_chain_pass,
        max_chain_iters=args.max_chain_iters,
        leg_chain_node_moves=args.leg_chain_node_moves,
    )
    update_snapshot_nodes(working, node_positions(working))

    write_json(out_dir / f"{asset_name}_ordered_ct_probe.json", result)
    write_json(out_dir / f"{asset_name}_ordered_ct_snapshot.json", working)
    if not args.skip_slice_images:
        slice_dir = out_dir / "slices"
        slice_dir.mkdir(parents=True, exist_ok=True)
        _, slice_analysis = write_slice_analysis(out_dir, asset_name, working, slice_dir)
        write_json(out_dir / "slice_analysis.json", slice_analysis)

    md_lines = [
        f"# Ordered CT Probe: {asset_name}",
        "",
        f"- Initial strict CT failures: `{result['initial']['failureCount']}`",
        f"- Final strict CT failures: `{result['final']['failureCount']}`",
        f"- Final role-aware CT failures: `{result['finalRoleAware']['failureCount']}`",
        f"- Locked green segments: `{len(result['lockedSegments'])}` / `{len(ORDERED_SEGMENTS)}`",
        f"- Floor clamp: `{result['floorClamp']}`",
        f"- Max local step: `{result['maxStep']}`",
        "",
        "| Segment | Before active/locked/related/global | After active/locked/related/global | Moves | Stop |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for item in result["segments"]:
        md_lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                item["segment"],
                item["before"],
                item["after"],
                item["acceptedMoves"],
                item["stopReason"],
            )
        )
    if result["chains"]:
        md_lines += ["", "## Leg Chain Pass", ""]
        md_lines.append("| Chain | Before chain/outside/global | After chain/outside/global | Moves | Stop |")
        md_lines.append("| --- | --- | --- | ---: | --- |")
        for item in result["chains"]:
            md_lines.append(
                "| `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                    item["chain"],
                    item["before"],
                    item["after"],
                    item["acceptedMoves"],
                    item["stopReason"],
                )
            )
    if result["final"]["failures"]:
        md_lines += ["", "## Remaining Failures", ""]
        for failure in result["final"]["failures"]:
            md_lines.append(
                f"- `{failure['segment']}` t=`{failure['t']}` {failure['wrapState']} pointCount=`{failure['pointCount']}`"
            )
    (out_dir / "README.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "assetName": asset_name,
                "outDir": str(out_dir),
                "initialFailures": result["initial"]["failureCount"],
                "finalFailures": result["final"]["failureCount"],
                "finalRoleAwareFailures": result["finalRoleAware"]["failureCount"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
