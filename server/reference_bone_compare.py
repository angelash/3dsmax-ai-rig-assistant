from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any


REFERENCE_PRIMARY_BONES: dict[str, str] = {
    "Pelvis": "CC_Base_Hip",
    "Spine": "CC_Base_Waist",
    "Chest": "CC_Base_Spine02",
    "Neck": "CC_Base_NeckTwist01",
    "Head": "CC_Base_Head",
    "L_Clavicle": "CC_Base_L_Clavicle",
    "L_Shoulder": "CC_Base_L_Upperarm",
    "L_Elbow": "CC_Base_L_Forearm",
    "L_Wrist": "CC_Base_L_Hand",
    "R_Clavicle": "CC_Base_R_Clavicle",
    "R_Shoulder": "CC_Base_R_Upperarm",
    "R_Elbow": "CC_Base_R_Forearm",
    "R_Wrist": "CC_Base_R_Hand",
    "L_Hip": "CC_Base_L_Thigh",
    "L_Knee": "CC_Base_L_Calf",
    "L_Ankle": "CC_Base_L_Foot",
    "L_Toe": "CC_Base_L_ToeBase",
    "R_Hip": "CC_Base_R_Thigh",
    "R_Knee": "CC_Base_R_Calf",
    "R_Ankle": "CC_Base_R_Foot",
    "R_Toe": "CC_Base_R_ToeBase",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def bounds_height(bounds: dict[str, Any]) -> float:
    size = bounds.get("size") or [0, 0, 1]
    return max(float(size[2]), 1.0)


def normalized(point: list[float], bounds: dict[str, Any]) -> list[float]:
    center = bounds.get("center") or [0, 0, 0]
    height = bounds_height(bounds)
    return [(float(point[i]) - float(center[i])) / height for i in range(3)]


def distance(values: list[float]) -> float:
    return math.sqrt(sum(v * v for v in values))


def delta(a: list[float], b: list[float]) -> list[float]:
    return [a[i] - b[i] for i in range(3)]


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * pct)))
    return ordered[index]


def snapshot_for_asset(snapshot_root: Path, asset: str) -> Path | None:
    candidates = [
        snapshot_root / asset / f"{asset}_ordered_ct_snapshot.json",
        snapshot_root / f"{asset}_ordered_ct_snapshot.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    matches = list(snapshot_root.glob(f"**/{asset}_ordered_ct_snapshot.json"))
    return matches[0] if matches else None


def probe_for_asset(snapshot_root: Path, asset: str) -> Path | None:
    candidates = [
        snapshot_root / asset / f"{asset}_ordered_ct_probe.json",
        snapshot_root / f"{asset}_ordered_ct_probe.json",
        snapshot_root / asset / f"{asset}_anatomy_safe_nudge_probe.json",
        snapshot_root / f"{asset}_anatomy_safe_nudge_probe.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    matches = list(snapshot_root.glob(f"**/{asset}_ordered_ct_probe.json"))
    if not matches:
        matches = list(snapshot_root.glob(f"**/{asset}_anatomy_safe_nudge_probe.json"))
    return matches[0] if matches else None


def reference_for_asset(reference_root: Path, asset: str) -> Path | None:
    candidates = [
        reference_root / asset / f"{asset}_reference_bones.json",
        reference_root / f"{asset}_reference_bones.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    matches = list(reference_root.glob(f"**/{asset}_reference_bones.json"))
    return matches[0] if matches else None


def compare_asset(asset: str, snapshot_path: Path, reference_path: Path, probe_path: Path | None) -> dict[str, Any]:
    snapshot = load_json(snapshot_path)
    reference = load_json(reference_path)
    nodes = snapshot.get("bipedNodes") or {}
    reference_bones = {str(bone.get("name")): bone for bone in reference.get("skinBones") or []}
    landmark_rows: list[dict[str, Any]] = []

    for candidate_node, reference_name in REFERENCE_PRIMARY_BONES.items():
        if candidate_node not in nodes or reference_name not in reference_bones:
            continue
        candidate_position = [float(v) for v in nodes[candidate_node]]
        reference_position = [float(v) for v in reference_bones[reference_name].get("position", [0, 0, 0])]
        candidate_normal = normalized(candidate_position, snapshot["bounds"])
        reference_normal = normalized(reference_position, reference["bounds"])
        normal_delta = delta(candidate_normal, reference_normal)
        landmark_rows.append(
            {
                "candidateNode": candidate_node,
                "referenceBone": reference_name,
                "distancePctHeight": round(distance(normal_delta) * 100.0, 3),
                "deltaPctHeight": [round(v * 100.0, 3) for v in normal_delta],
                "candidatePosition": [round(v, 6) for v in candidate_position],
                "referencePosition": [round(v, 6) for v in reference_position],
            }
        )

    distances = [float(row["distancePctHeight"]) for row in landmark_rows]
    probe = load_json(probe_path) if probe_path and probe_path.exists() else {}
    final_probe = probe.get("final") or {}
    strict_failures = int(final_probe.get("failureCount") or final_probe.get("strictCtFailures") or 0)
    role_failures = int(
        (probe.get("finalRoleAware") or {}).get("failureCount")
        or final_probe.get("roleAwareCtFailures")
        or 0
    )
    unmapped_reference_bones = [
        bone.get("name")
        for bone in reference.get("skinBones") or []
        if bone.get("semantic") in (None, "")
    ]

    return {
        "asset": asset,
        "snapshot": str(snapshot_path),
        "reference": str(reference_path),
        "probe": str(probe_path) if probe_path else "",
        "strictCtFailures": strict_failures,
        "roleAwareCtFailures": role_failures,
        "skinBoneReferenceCount": reference.get("skinBoneReferenceCount", 0),
        "unmappedReferenceBoneCount": len(unmapped_reference_bones),
        "unmappedReferenceBones": unmapped_reference_bones,
        "landmarkCount": len(landmark_rows),
        "meanDistancePctHeight": round(statistics.mean(distances), 3) if distances else 0.0,
        "medianDistancePctHeight": round(statistics.median(distances), 3) if distances else 0.0,
        "p90DistancePctHeight": round(percentile(distances, 0.90), 3) if distances else 0.0,
        "maxDistancePctHeight": round(max(distances), 3) if distances else 0.0,
        "worstLandmarks": sorted(landmark_rows, key=lambda row: row["distancePctHeight"], reverse=True)[:8],
        "landmarks": landmark_rows,
    }


def markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Reference Bone Compare",
        "",
        f"- Assets compared: `{summary['assetCount']}`",
        f"- Mean landmark error: `{summary['aggregate']['meanDistancePctHeight']}`% height",
        f"- Median landmark error: `{summary['aggregate']['medianDistancePctHeight']}`% height",
        f"- P90 landmark error: `{summary['aggregate']['p90DistancePctHeight']}`% height",
        f"- Max landmark error: `{summary['aggregate']['maxDistancePctHeight']}`% height",
        "",
        "## Assets",
        "",
        "| Asset | CT strict | CT role | Mean %H | P90 %H | Max %H | Worst landmark | Unmapped ref bones |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    for item in summary["assets"]:
        worst = item["worstLandmarks"][0] if item["worstLandmarks"] else {}
        worst_label = ""
        if worst:
            worst_label = f"{worst['candidateNode']} -> {worst['referenceBone']} ({worst['distancePctHeight']}%)"
        lines.append(
            f"| `{item['asset']}` | {item['strictCtFailures']} | {item['roleAwareCtFailures']} | "
            f"{item['meanDistancePctHeight']:.3f} | {item['p90DistancePctHeight']:.3f} | "
            f"{item['maxDistancePctHeight']:.3f} | `{worst_label}` | {item['unmappedReferenceBoneCount']} |"
        )

    lines += ["", "## Worst Landmarks", ""]
    all_worst: list[dict[str, Any]] = []
    for item in summary["assets"]:
        for row in item["worstLandmarks"][:3]:
            all_worst.append({"asset": item["asset"], **row})
    all_worst.sort(key=lambda row: row["distancePctHeight"], reverse=True)
    lines += ["| Asset | Candidate | Reference | Distance %H | Delta %H XYZ |", "| --- | --- | --- | ---: | --- |"]
    for row in all_worst[:30]:
        lines.append(
            f"| `{row['asset']}` | `{row['candidateNode']}` | `{row['referenceBone']}` | "
            f"{row['distancePctHeight']:.3f} | `{row['deltaPctHeight']}` |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Stage01 CT snapshots against exported reference FBX bones.")
    parser.add_argument("--snapshot-root", required=True, type=Path)
    parser.add_argument("--reference-root", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--asset", action="append", default=[])
    args = parser.parse_args()

    assets = args.asset
    if not assets:
        assets = sorted(
            {
                path.relative_to(args.reference_root).parts[0]
                for path in args.reference_root.glob("*/**/*_reference_bones.json")
            }
        )

    results: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    for asset in assets:
        snapshot_path = snapshot_for_asset(args.snapshot_root, asset)
        reference_path = reference_for_asset(args.reference_root, asset)
        probe_path = probe_for_asset(args.snapshot_root, asset)
        if not snapshot_path or not reference_path:
            missing.append(
                {
                    "asset": asset,
                    "snapshot": str(snapshot_path) if snapshot_path else "",
                    "reference": str(reference_path) if reference_path else "",
                }
            )
            continue
        results.append(compare_asset(asset, snapshot_path, reference_path, probe_path))

    all_distances = [
        float(row["distancePctHeight"])
        for item in results
        for row in item.get("landmarks", [])
    ]
    summary = {
        "assetCount": len(results),
        "missing": missing,
        "aggregate": {
            "meanDistancePctHeight": round(statistics.mean(all_distances), 3) if all_distances else 0.0,
            "medianDistancePctHeight": round(statistics.median(all_distances), 3) if all_distances else 0.0,
            "p90DistancePctHeight": round(percentile(all_distances, 0.90), 3) if all_distances else 0.0,
            "maxDistancePctHeight": round(max(all_distances), 3) if all_distances else 0.0,
        },
        "assets": sorted(results, key=lambda item: item["meanDistancePctHeight"], reverse=True),
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "reference_bone_compare_summary.json", summary)
    (args.out_dir / "reference_bone_compare_summary.md").write_text(markdown_report(summary), encoding="utf-8")
    print(json.dumps({"ok": True, "assetCount": len(results), "missing": missing}, ensure_ascii=False))


if __name__ == "__main__":
    main()
