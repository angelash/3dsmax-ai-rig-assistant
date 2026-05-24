from __future__ import annotations

import argparse
import copy
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage01_ct_ordered_refine_probe as ct_refine


DEFAULT_FOCUS_NODES = [
    "L_Toe",
    "R_Toe",
    "L_Ankle",
    "R_Ankle",
    "L_Knee",
    "R_Knee",
    "L_Wrist",
    "R_Wrist",
    "L_Hip",
    "R_Hip",
]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def bounds_info(snapshot: dict[str, Any]) -> tuple[list[float], list[float], list[float], float]:
    bounds = snapshot["bounds"]
    mn = [float(v) for v in bounds["min"]]
    mx = [float(v) for v in bounds["max"]]
    center = [float(v) for v in bounds["center"]]
    height = max(float(bounds["size"][2]), 1.0)
    return mn, mx, center, height


def z_at(snapshot: dict[str, Any], ratio: float) -> float:
    mn, _, _, height = bounds_info(snapshot)
    return mn[2] + height * ratio


def z_ratio(snapshot: dict[str, Any], point: list[float]) -> float:
    mn, _, _, height = bounds_info(snapshot)
    return (float(point[2]) - mn[2]) / height


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * pct)))
    return ordered[index]


def side_points(
    snapshot: dict[str, Any],
    side: str,
    *,
    z_min_ratio: float,
    z_max_ratio: float,
) -> list[list[float]]:
    mn, _, center, height = bounds_info(snapshot)
    points = []
    for raw in snapshot.get("meshPoints", []):
        point = [float(v) for v in raw]
        ratio = (point[2] - mn[2]) / height
        if ratio < z_min_ratio or ratio > z_max_ratio:
            continue
        if side == "L" and point[0] < center[0]:
            continue
        if side == "R" and point[0] > center[0]:
            continue
        points.append(point)
    return points


def lateral_percentile(side: str) -> float:
    return 0.78 if side == "L" else 0.22


def foot_target(snapshot: dict[str, Any], side: str, node: str) -> list[float] | None:
    nodes = snapshot.get("bipedNodes", {})
    if node not in nodes:
        return None
    current = [float(v) for v in nodes[node]]
    foot_points = side_points(snapshot, side, z_min_ratio=0.0, z_max_ratio=0.18)
    if len(foot_points) < 12:
        return None

    target = list(current)
    lateral_x = percentile([p[0] for p in foot_points], lateral_percentile(side))
    if lateral_x is not None:
        target[0] = lateral_x

    if node.endswith("_Toe"):
        target[2] = z_at(snapshot, 0.025)
        ankle_name = f"{side}_Ankle"
        ankle = nodes.get(ankle_name)
        if ankle is not None:
            ankle_y = float(ankle[1])
            current_y = current[1]
            y_values = [p[1] for p in foot_points]
            # Keep the current foot direction: move toward the lower or higher local foot end
            # rather than imposing a global front axis.
            target[1] = percentile(y_values, 0.18 if current_y < ankle_y else 0.82) or current_y
    else:
        target[2] = z_at(snapshot, 0.045)
        y_center = percentile([p[1] for p in foot_points], 0.5)
        if y_center is not None:
            target[1] = (target[1] * 0.6) + (y_center * 0.4)
    return target


def knee_target(snapshot: dict[str, Any], side: str) -> list[float] | None:
    nodes = snapshot.get("bipedNodes", {})
    node = f"{side}_Knee"
    hip_name = f"{side}_Hip"
    ankle_name = f"{side}_Ankle"
    if node not in nodes or hip_name not in nodes or ankle_name not in nodes:
        return None
    current = [float(v) for v in nodes[node]]
    current_ratio = z_ratio(snapshot, current)
    if current_ratio <= 0.165:
        return None

    hip = [float(v) for v in nodes[hip_name]]
    ankle = [float(v) for v in nodes[ankle_name]]
    target_z = z_at(snapshot, 0.13)
    denom = ankle[2] - hip[2]
    if abs(denom) < 1e-6:
        t = 0.5
    else:
        t = max(0.0, min(1.0, (target_z - hip[2]) / denom))
    target = [hip[i] + (ankle[i] - hip[i]) * t for i in range(3)]
    target[2] = target_z
    # Preserve part of the existing bend so a straight hidden-axis prior does not flatten legs.
    target[0] = target[0] * 0.65 + current[0] * 0.35
    target[1] = target[1] * 0.65 + current[1] * 0.35
    return target


def wrist_target(snapshot: dict[str, Any], side: str) -> list[float] | None:
    nodes = snapshot.get("bipedNodes", {})
    node = f"{side}_Wrist"
    if node not in nodes:
        return None
    current = [float(v) for v in nodes[node]]
    if z_ratio(snapshot, current) >= 0.53:
        return None
    arm_points = side_points(snapshot, side, z_min_ratio=0.35, z_max_ratio=0.72)
    if len(arm_points) < 12:
        return None
    target = list(current)
    lateral_x = percentile([p[0] for p in arm_points], lateral_percentile(side))
    if lateral_x is not None:
        target[0] = lateral_x
    target[2] = z_at(snapshot, 0.55)
    return target


def hip_target(snapshot: dict[str, Any], side: str) -> list[float] | None:
    nodes = snapshot.get("bipedNodes", {})
    node = f"{side}_Hip"
    if node not in nodes:
        return None
    current = [float(v) for v in nodes[node]]
    if z_ratio(snapshot, current) >= 0.22:
        return None
    target = list(current)
    target[2] = z_at(snapshot, 0.265)
    return target


def build_anatomy_targets(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    targets: dict[str, dict[str, Any]] = {}
    for side in ("L", "R"):
        for node in (f"{side}_Toe", f"{side}_Ankle"):
            target = foot_target(snapshot, side, node)
            if target is not None:
                targets[node] = {"target": target, "rule": "foot_floor_and_local_foot_cloud"}
        target = knee_target(snapshot, side)
        if target is not None:
            targets[f"{side}_Knee"] = {"target": target, "rule": "high_knee_hidden_leg_axis"}
        target = wrist_target(snapshot, side)
        if target is not None:
            targets[f"{side}_Wrist"] = {"target": target, "rule": "low_wrist_arm_height_prior"}
        target = hip_target(snapshot, side)
        if target is not None:
            targets[f"{side}_Hip"] = {"target": target, "rule": "low_hip_height_prior"}
    return targets


def node_error(snapshot: dict[str, Any], node: str, target: list[float]) -> float:
    _, _, _, height = bounds_info(snapshot)
    current = snapshot["bipedNodes"][node]
    return math.sqrt(sum(((float(current[i]) - target[i]) / height) ** 2 for i in range(3))) * 100.0


def anatomy_metrics(snapshot: dict[str, Any], targets: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = [
        {
            "node": node,
            "rule": target["rule"],
            "distancePctHeight": round(node_error(snapshot, node, target["target"]), 6),
        }
        for node, target in targets.items()
    ]
    distances = [row["distancePctHeight"] for row in rows]
    return {
        "meanDistancePctHeight": round(statistics.mean(distances), 6) if distances else 0.0,
        "medianDistancePctHeight": round(statistics.median(distances), 6) if distances else 0.0,
        "maxDistancePctHeight": round(max(distances), 6) if distances else 0.0,
        "worstNodes": sorted(rows, key=lambda row: row["distancePctHeight"], reverse=True)[:8],
    }


def metric_score(metrics: dict[str, Any], max_weight: float) -> float:
    return float(metrics["meanDistancePctHeight"]) + max_weight * float(metrics["maxDistancePctHeight"])


def set_node(snapshot: dict[str, Any], node: str, position: list[float]) -> None:
    nodes = {name: [float(v) for v in value] for name, value in snapshot["bipedNodes"].items()}
    nodes[node] = position
    ct_refine.update_snapshot_nodes(snapshot, nodes)


def nudge_snapshot(
    snapshot: dict[str, Any],
    targets: dict[str, dict[str, Any]],
    *,
    focus_nodes: list[str],
    max_nodes_per_pass: int,
    passes: int,
    max_step_height: float,
    fractions: list[float],
    max_weight: float,
) -> dict[str, Any]:
    current = copy.deepcopy(snapshot)
    base_strict = ct_refine.evaluate(current)
    base_role = ct_refine.evaluate(current, foot_planar=True)
    before_metrics = anatomy_metrics(current, targets)
    accepted: list[dict[str, Any]] = []
    _, _, _, height = bounds_info(snapshot)
    max_step = height * max_step_height
    candidates = [node for node in focus_nodes if node in targets]

    for pass_index in range(passes):
        ordered = sorted(
            candidates,
            key=lambda node: node_error(current, node, targets[node]["target"]),
            reverse=True,
        )
        for node in ordered[:max_nodes_per_pass]:
            current_position = [float(v) for v in current["bipedNodes"][node]]
            target = targets[node]["target"]
            vector = [target[i] - current_position[i] for i in range(3)]
            length = math.sqrt(sum(v * v for v in vector))
            if length <= 1e-6:
                continue

            current_metrics = anatomy_metrics(current, targets)
            for fraction in fractions:
                step = min(length * fraction, max_step)
                trial_position = [
                    current_position[i] + vector[i] / length * step
                    for i in range(3)
                ]
                trial = copy.deepcopy(current)
                set_node(trial, node, trial_position)
                strict = ct_refine.evaluate(trial)
                role = ct_refine.evaluate(trial, foot_planar=True)
                if strict["failureCount"] > base_strict["failureCount"]:
                    continue
                if role["failureCount"] > base_role["failureCount"]:
                    continue
                trial_metrics = anatomy_metrics(trial, targets)
                if metric_score(trial_metrics, max_weight) >= metric_score(current_metrics, max_weight) - 1e-4:
                    continue
                current = trial
                accepted.append(
                    {
                        "pass": pass_index + 1,
                        "node": node,
                        "rule": targets[node]["rule"],
                        "fraction": fraction,
                        "step": round(step, 6),
                        "strictFailures": strict["failureCount"],
                        "roleAwareFailures": role["failureCount"],
                        "meanDistancePctHeight": trial_metrics["meanDistancePctHeight"],
                        "maxDistancePctHeight": trial_metrics["maxDistancePctHeight"],
                    }
                )
                break

    final_strict = ct_refine.evaluate(current)
    final_role = ct_refine.evaluate(current, foot_planar=True)
    after_metrics = anatomy_metrics(current, targets)
    return {
        "snapshot": current,
        "report": {
            "initial": {
                "strictCtFailures": base_strict["failureCount"],
                "roleAwareCtFailures": base_role["failureCount"],
                "anatomyMetrics": before_metrics,
            },
            "final": {
                "strictCtFailures": final_strict["failureCount"],
                "roleAwareCtFailures": final_role["failureCount"],
                "anatomyMetrics": after_metrics,
            },
            "acceptedMoveCount": len(accepted),
            "acceptedMoves": accepted,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Nudge Stage01 nodes toward no-reference anatomy priors without CT regression.")
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--asset-name", default="")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--passes", type=int, default=3)
    parser.add_argument("--max-nodes-per-pass", type=int, default=10)
    parser.add_argument("--max-step-height", type=float, default=0.025)
    parser.add_argument("--fractions", default="0.18,0.1,0.05,0.025")
    parser.add_argument("--max-weight", type=float, default=0.15)
    parser.add_argument("--focus-nodes", default=",".join(DEFAULT_FOCUS_NODES))
    args = parser.parse_args()

    snapshot = load_json(args.snapshot)
    asset_name = args.asset_name or str(snapshot.get("assetName") or args.snapshot.stem.replace("_ordered_ct_snapshot", ""))
    targets = build_anatomy_targets(snapshot)
    fractions = [float(value.strip()) for value in args.fractions.split(",") if value.strip()]
    focus_nodes = [value.strip() for value in args.focus_nodes.split(",") if value.strip()]
    result = nudge_snapshot(
        snapshot,
        targets,
        focus_nodes=focus_nodes,
        max_nodes_per_pass=args.max_nodes_per_pass,
        passes=args.passes,
        max_step_height=args.max_step_height,
        fractions=fractions,
        max_weight=args.max_weight,
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = args.out_dir / f"{asset_name}_ordered_ct_snapshot.json"
    report_path = args.out_dir / f"{asset_name}_anatomy_safe_nudge_probe.json"
    report = {
        "assetName": asset_name,
        "inputSnapshot": str(args.snapshot),
        "targetCount": len(targets),
        "targets": {
            node: {
                "rule": target["rule"],
                "target": [round(float(v), 6) for v in target["target"]],
            }
            for node, target in targets.items()
        },
        "focusNodes": focus_nodes,
        "settings": {
            "passes": args.passes,
            "maxNodesPerPass": args.max_nodes_per_pass,
            "maxStepHeight": args.max_step_height,
            "fractions": fractions,
            "maxWeight": args.max_weight,
        },
        **result["report"],
        "outputSnapshot": str(snapshot_path),
    }
    write_json(snapshot_path, result["snapshot"])
    write_json(report_path, report)
    print(json.dumps({"ok": True, "asset": asset_name, "report": str(report_path), "snapshot": str(snapshot_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
