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

PROBE_STATIONS = list(SLICE_SAMPLE_STATIONS)


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


def update_snapshot_nodes(snapshot: dict[str, Any], nodes: dict[str, list[float]]) -> None:
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


def segment_samples(snapshot: dict[str, Any], start_name: str, end_name: str) -> list[dict[str, Any]]:
    nodes = node_positions(snapshot)
    if start_name not in nodes or end_name not in nodes:
        return []
    start = nodes[start_name]
    end = nodes[end_name]
    axis_vec = vec_sub(end, start)
    axis, u_axis, v_axis, length = segment_axes(start, end)
    if length <= 1e-6:
        return []
    bounds = snapshot.get("bounds", {})
    height = max(float(bounds.get("size", [0, 0, 1])[2]), 1.0)
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
        samples.append(info)
    return samples


def evaluate(snapshot: dict[str, Any]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    by_segment: dict[str, int] = {}
    for start, end in ORDERED_SEGMENTS:
        segment = f"{start}->{end}"
        count = 0
        for sample in segment_samples(snapshot, start, end):
            if not sample["strict"]:
                count += 1
                failures.append(
                    {
                        "segment": segment,
                        "t": sample["t"],
                        "wrapState": sample["wrapState"],
                        "pointCount": sample["pointCount"],
                    }
                )
        by_segment[segment] = count
    return {"failureCount": len(failures), "failures": failures, "bySegment": by_segment}


def clamp(vec: list[float], max_len: float) -> list[float]:
    length = vec_length(vec)
    if length <= max_len or length <= 1e-8:
        return vec
    return vec_scale(vec, max_len / length)


def candidate_moves(snapshot: dict[str, Any], start: str, end: str, node: str, max_step: float) -> list[list[float]]:
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

    axes = [[1.0, 0.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, 1.0], [0.0, 0.0, -1.0]]
    for fraction in (0.25, 0.5, 1.0):
        for axis in axes:
            moves.append(vec_scale(axis, max_step * fraction))

    # Keep candidate list deterministic and compact.
    unique: dict[tuple[int, int, int], list[float]] = {}
    for move in moves:
        if vec_length(move) <= 1e-6:
            continue
        key = tuple(int(round(v * 1000)) for v in move)
        unique[key] = move
    return list(unique.values())


def segments_share_node(a: tuple[str, str], b: tuple[str, str]) -> bool:
    return a[0] in b or a[1] in b


def score(snapshot: dict[str, Any], locked: list[tuple[str, str]], active: tuple[str, str]) -> tuple[int, int, int, int]:
    result = evaluate(snapshot)
    active_key = f"{active[0]}->{active[1]}"
    locked_failures = sum(result["bySegment"].get(f"{s}->{e}", 0) for s, e in locked)
    related_failures = sum(
        result["bySegment"].get(f"{s}->{e}", 0)
        for s, e in ORDERED_SEGMENTS
        if segments_share_node((s, e), active)
    )
    active_failures = result["bySegment"].get(active_key, 0)
    return active_failures, locked_failures, related_failures, result["failureCount"]


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
    before = score(snapshot, locked, segment)
    current = before
    accepted_moves = 0
    stop_reason = "already_green" if current[0] == 0 else "no_positive_candidate"
    if current[0] == 0:
        return {
            "segment": f"{start}->{end}",
            "before": before,
            "after": current,
            "acceptedMoves": 0,
            "stopReason": stop_reason,
            "trace": trace,
        }

    for iteration in range(1, max_segment_iters + 1):
        nodes = node_positions(snapshot)
        if end not in nodes:
            stop_reason = "missing_child_node"
            break
        best_snapshot: dict[str, Any] | None = None
        best_score = current
        best_move: list[float] | None = None
        move_nodes = (end, start) if allow_start_backtrack else (end,)
        for move_node in move_nodes:
            if move_node not in nodes:
                continue
            for move in candidate_moves(snapshot, start, end, move_node, max_step):
                trial = copy.deepcopy(snapshot)
                trial_nodes = node_positions(trial)
                trial_nodes[move_node] = vec_add(trial_nodes[move_node], move)
                update_snapshot_nodes(trial, trial_nodes)
                trial_score = score(trial, locked, segment)
                # Locked, adjacent, and global sections must not regress.
                if trial_score[1] > current[1] or trial_score[2] > current[2] or trial_score[3] > current[3]:
                    continue
                better = (
                    trial_score[0] < best_score[0]
                    or (trial_score[0] == best_score[0] and trial_score[2] < best_score[2])
                    or (
                        trial_score[0] == best_score[0]
                        and trial_score[2] == best_score[2]
                        and trial_score[3] < best_score[3]
                    )
                )
                if better:
                    best_snapshot = trial
                    best_score = trial_score
                    best_move = move
                    best_move_node = move_node
        if best_snapshot is None or best_score == current:
            stop_reason = "no_positive_candidate"
            break
        snapshot.clear()
        snapshot.update(best_snapshot)
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
            }
        )
        current = best_score
        if current[0] == 0:
            stop_reason = "segment_green"
            break
    return {
        "segment": f"{start}->{end}",
        "before": before,
        "after": current,
        "acceptedMoves": accepted_moves,
        "stopReason": stop_reason,
        "trace": trace,
    }


def run_probe(snapshot: dict[str, Any], max_segment_iters: int, allow_start_backtrack: bool, max_step_ratio: float) -> dict[str, Any]:
    bounds = snapshot.get("bounds", {})
    height = max(float(bounds.get("size", [0, 0, 1])[2]), 1.0)
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
    final = evaluate(snapshot)
    return {
        "mode": "ordered_agent_controlled_ct_probe",
        "maxSegmentIterations": max_segment_iters,
        "allowStartBacktrack": allow_start_backtrack,
        "maxStep": round(max_step, 6),
        "initial": initial,
        "final": final,
        "lockedSegments": [f"{s}->{e}" for s, e in locked],
        "segments": segment_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe ordered local CT refinement on a Stage01 visual snapshot.")
    parser.add_argument("snapshot_json")
    parser.add_argument("--asset-name", default="")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--max-segment-iters", type=int, default=16)
    parser.add_argument("--allow-start-backtrack", action="store_true")
    parser.add_argument("--max-step-ratio", type=float, default=0.035)
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
    if args.station_mode == "dense":
        PROBE_STATIONS = [0.0, 0.125, 0.25, 0.375, 0.50, 0.625, 0.75, 0.875, 1.0]
    else:
        PROBE_STATIONS = list(SLICE_SAMPLE_STATIONS)
    asset_name = args.asset_name or str(snapshot.get("assetName") or snapshot_path.stem)

    working = copy.deepcopy(snapshot)
    result = run_probe(working, args.max_segment_iters, args.allow_start_backtrack, args.max_step_ratio)
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
        f"- Locked green segments: `{len(result['lockedSegments'])}` / `{len(ORDERED_SEGMENTS)}`",
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
    if result["final"]["failures"]:
        md_lines += ["", "## Remaining Failures", ""]
        for failure in result["final"]["failures"]:
            md_lines.append(
                f"- `{failure['segment']}` t=`{failure['t']}` {failure['wrapState']} pointCount=`{failure['pointCount']}`"
            )
    (out_dir / "README.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(json.dumps({"ok": True, "assetName": asset_name, "outDir": str(out_dir), "initialFailures": result["initial"]["failureCount"], "finalFailures": result["final"]["failureCount"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
