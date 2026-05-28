from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage01_anatomy_safe_nudge_probe as anatomy_probe


PASS_STATUSES = {"pass", "passed", "ok", "approved"}

LOWER_BODY_NODES = [
    "L_Hip",
    "R_Hip",
    "L_Knee",
    "R_Knee",
    "L_Ankle",
    "R_Ankle",
    "L_Toe",
    "R_Toe",
]

CHECK_TO_ANATOMY_NODES = {
    "rootPelvisPolicy": ["L_Hip", "R_Hip"],
    "sideWrap": LOWER_BODY_NODES,
    "topWrap": LOWER_BODY_NODES,
    "crossSectionInsideVolume": LOWER_BODY_NODES,
    "legClothingOcclusion": LOWER_BODY_NODES,
    "leftFootPivot": ["L_Ankle", "L_Toe"],
    "rightFootPivot": ["R_Ankle", "R_Toe"],
}

CHECK_TO_COVERAGE_GUIDES = {
    "frontWrap": [
        "L_Shoulder",
        "R_Shoulder",
        "L_Elbow",
        "R_Elbow",
        "L_Wrist",
        "R_Wrist",
        "L_Hand",
        "R_Hand",
    ],
    "topWrap": [
        "L_Shoulder",
        "R_Shoulder",
        "L_Elbow",
        "R_Elbow",
        "L_Wrist",
        "R_Wrist",
        "L_Hand",
        "R_Hand",
    ],
    "leftHandDetail": ["L_Wrist", "L_Hand"],
    "rightHandDetail": ["R_Wrist", "R_Hand"],
}


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
    return data if isinstance(data, dict) else {}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def point(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    try:
        return [float(value[0]), float(value[1]), float(value[2])]
    except (TypeError, ValueError):
        return None


def rounded_point(value: list[float]) -> list[float]:
    return [round(float(v), 6) for v in value[:3]]


def distance(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((float(b[i]) - float(a[i])) ** 2 for i in range(3)))


def bounds_height(snapshot: dict[str, Any]) -> float:
    bounds = snapshot.get("bounds") or {}
    size = bounds.get("size") or []
    try:
        return max(float(size[2]), 1.0)
    except (IndexError, TypeError, ValueError):
        return 1.0


def status_is_pass(status: str) -> bool:
    return status.strip().lower() in PASS_STATUSES


def failed_signoff_checks(signoff: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    checks = signoff.get("checks") or {}
    if not isinstance(checks, dict):
        return rows
    for name, raw_payload in checks.items():
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        status = str(payload.get("status") or "missing")
        if status_is_pass(status):
            continue
        rows.append(
            {
                "name": str(name),
                "status": status,
                "evidence": payload.get("evidence") if isinstance(payload.get("evidence"), list) else [],
                "comment": str(payload.get("comment") or ""),
            }
        )
    return rows


def source_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row["name"]): row for row in rows}


def merge_source(action: dict[str, Any], check: dict[str, Any]) -> None:
    name = str(check["name"])
    if name not in action["sourceChecks"]:
        action["sourceChecks"].append(name)
    status = str(check.get("status") or "")
    if status and status not in action["sourceStatuses"]:
        action["sourceStatuses"].append(status)
    for item in check.get("evidence") or []:
        if item not in action["sourceEvidence"]:
            action["sourceEvidence"].append(item)


def upsert_action(actions: dict[tuple[str, str, str], dict[str, Any]], action: dict[str, Any], check: dict[str, Any]) -> None:
    key = (str(action["kind"]), str(action["targetName"]), str(action["rule"]))
    if key in actions:
        merge_source(actions[key], check)
        return
    merge_source(action, check)
    actions[key] = action


def make_target_action(
    *,
    kind: str,
    target_name: str,
    target_kind: str,
    rule: str,
    current: list[float],
    target: list[float],
    height: float,
    max_step_height: float,
    confidence: str,
    source: str,
    note: str = "",
    apply_to: list[str] | None = None,
) -> dict[str, Any]:
    dist = distance(current, target)
    return {
        "kind": kind,
        "targetName": target_name,
        "targetKind": target_kind,
        "applyTo": apply_to or [target_kind],
        "rule": rule,
        "source": source,
        "confidence": confidence,
        "current": rounded_point(current),
        "target": rounded_point(target),
        "deltaToTarget": rounded_point([target[i] - current[i] for i in range(3)]),
        "distance": round(dist, 6),
        "distanceHeightRatio": round(dist / height, 6),
        "maxSingleStep": round(height * max_step_height, 6),
        "maxSingleStepHeightRatio": max_step_height,
        "applyPhase": "guide_generation_or_pre_skin_biped_fit",
        "guardedBy": [
            "ct_no_regression",
            "ordered_chain_hierarchy",
            "symmetry_sanity_check",
            "mdc_visual_reinspect",
        ],
        "autoApplyNow": False,
        "autoApplyEligibleAfterBridge": True,
        "sourceChecks": [],
        "sourceStatuses": [],
        "sourceEvidence": [],
        "note": note,
    }


def anatomy_actions(
    snapshot: dict[str, Any],
    failed_checks: list[dict[str, Any]],
    *,
    height: float,
    max_step_height: float,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    actions: dict[tuple[str, str, str], dict[str, Any]] = {}
    anatomy_targets = anatomy_probe.build_anatomy_targets(snapshot)
    biped_nodes = snapshot.get("bipedNodes") or {}
    guides = snapshot.get("guides") or {}

    for check in failed_checks:
        for node in CHECK_TO_ANATOMY_NODES.get(str(check["name"]), []):
            target_info = anatomy_targets.get(node)
            if not target_info:
                continue
            target = point(target_info.get("target"))
            current = point(biped_nodes.get(node)) or point(guides.get(node))
            if target is None or current is None:
                continue
            action = make_target_action(
                kind="biped_node_nudge",
                target_name=node,
                target_kind="bipedNode",
                rule=str(target_info.get("rule") or "anatomy_prior"),
                current=current,
                target=target,
                height=height,
                max_step_height=max_step_height,
                confidence="medium",
                source="stage01_anatomy_safe_nudge_probe",
                note="No-reference local anatomy target built from current mesh point cloud and Biped snapshot.",
                apply_to=["bipedNode", "guideIfPresent"],
            )
            upsert_action(actions, action, check)
    return actions


def coverage_actions(
    snapshot: dict[str, Any],
    visual_qc: dict[str, Any],
    failed_checks: list[dict[str, Any]],
    *,
    height: float,
    max_step_height: float,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    actions: dict[tuple[str, str, str], dict[str, Any]] = {}
    biped_nodes = snapshot.get("bipedNodes") or {}
    guides = snapshot.get("guides") or {}
    coverage_maps = [
        ("armCoverage", visual_qc.get("armCoverage") or {}),
        ("handCoverage", visual_qc.get("handCoverage") or {}),
    ]

    for check in failed_checks:
        allowed = set(CHECK_TO_COVERAGE_GUIDES.get(str(check["name"]), []))
        if not allowed:
            continue
        for coverage_name, coverage_map in coverage_maps:
            if not isinstance(coverage_map, dict):
                continue
            for guide_name in allowed:
                raw = coverage_map.get(guide_name)
                if not isinstance(raw, dict):
                    continue
                if raw.get("ready") is True:
                    continue
                target = point(raw.get("target"))
                current = point(raw.get("guide")) or point(guides.get(guide_name)) or point(biped_nodes.get(guide_name))
                if target is None or current is None:
                    continue
                apply_to = ["guide"]
                if guide_name in biped_nodes:
                    apply_to.append("bipedNode")
                action = make_target_action(
                    kind="visual_centerline_nudge",
                    target_name=guide_name,
                    target_kind="guide",
                    rule=str(raw.get("targetType") or coverage_name),
                    current=current,
                    target=target,
                    height=height,
                    max_step_height=max_step_height,
                    confidence=str(raw.get("confidence") or "medium"),
                    source=f"visual_qc.{coverage_name}",
                    note=str(raw.get("note") or "Target comes from local visual silhouette centerline coverage."),
                    apply_to=apply_to,
                )
                upsert_action(actions, action, check)
    return actions


def review_only_items(failed_checks: list[dict[str, Any]], actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    covered_checks = {check for action in actions for check in action.get("sourceChecks", [])}
    review_items = []
    for check in failed_checks:
        if check["name"] in covered_checks:
            continue
        review_items.append(
            {
                "check": check["name"],
                "status": check["status"],
                "evidence": check.get("evidence") or [],
                "comment": check.get("comment") or "",
                "reason": "No bounded geometry target is available from current snapshot/QC; keep this as MDC semantic review or request more evidence.",
            }
        )
    return review_items


def plan_markdown(plan: dict[str, Any]) -> str:
    lines = [
        f"# MDC Visual Correction Plan: {plan['assetName']}",
        "",
        f"- Plan status: `{plan['summary']['planStatus']}`",
        f"- Signoff recommendation: `{plan.get('signoffRecommendation')}`",
        f"- Candidate actions: `{plan['summary']['candidateActionCount']}`",
        f"- Review-only blockers: `{plan['summary']['reviewOnlyCount']}`",
        f"- Automatic scene apply now: `{plan['readyToApplyAutomatically']}`",
        "",
        "## Guardrails",
        "",
    ]
    for guardrail in plan["guardrails"]:
        lines.append(f"- {guardrail}")

    lines += ["", "## Candidate Actions", ""]
    if not plan["actions"]:
        lines.append("- None")
    for action in plan["actions"]:
        lines.append(
            "- "
            f"`{action['id']}` {action['kind']} `{action['targetName']}` "
            f"via `{action['rule']}` distanceHeightRatio `{action['distanceHeightRatio']}` "
            f"from checks `{', '.join(action['sourceChecks'])}`"
        )

    lines += ["", "## Review-Only Items", ""]
    if not plan["reviewOnly"]:
        lines.append("- None")
    for item in plan["reviewOnly"]:
        lines.append(f"- `{item['check']}` status `{item['status']}`: {item['reason']}")
    return "\n".join(lines) + "\n"


def build_plan(
    *,
    snapshot: dict[str, Any],
    visual_qc: dict[str, Any],
    signoff: dict[str, Any],
    asset_name: str,
    paths: dict[str, str],
    max_step_height: float,
) -> dict[str, Any]:
    failed_checks = failed_signoff_checks(signoff)
    height = bounds_height(snapshot)
    action_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    action_map.update(anatomy_actions(snapshot, failed_checks, height=height, max_step_height=max_step_height))
    for key, action in coverage_actions(snapshot, visual_qc, failed_checks, height=height, max_step_height=max_step_height).items():
        if key in action_map:
            for check_name in action.get("sourceChecks", []):
                check = source_index(failed_checks).get(check_name)
                if check:
                    merge_source(action_map[key], check)
        else:
            action_map[key] = action

    actions = sorted(
        action_map.values(),
        key=lambda item: (
            -float(item.get("distanceHeightRatio") or 0.0),
            str(item.get("targetName") or ""),
            str(item.get("rule") or ""),
        ),
    )
    for index, action in enumerate(actions, 1):
        action["id"] = f"mvc_{index:03d}_{action['targetName']}"

    review_only = review_only_items(failed_checks, actions)
    recommendation = str(signoff.get("stage01HandoffRecommendation") or "missing_signoff")
    needs_more_views = recommendation == "needs_more_views" or any(
        str(check.get("status") or "") == "needs_more_views" for check in failed_checks
    )
    if not signoff:
        plan_status = "awaiting_mdc_visual_signoff"
    elif needs_more_views:
        plan_status = "evidence_incomplete_more_views_required"
    elif actions:
        plan_status = "candidate_corrections_available"
    elif failed_checks:
        plan_status = "review_only_blockers"
    else:
        plan_status = "no_corrections_required"

    return {
        "assetName": asset_name,
        "mode": "mdc_visual_correction_plan",
        "generatedAt": now_iso(),
        "decisionPolicy": "MDC vision may propose bounded correction targets; scene application must be guarded and followed by fresh evidence review.",
        "canParticipateInCorrection": True,
        "readyToApplyAutomatically": False,
        "automaticApplyNote": "This file is a correction plan. A MaxScript apply bridge must still consume bounded deltas, then rerun CT/visual evidence before Skin handoff.",
        "inputs": paths,
        "signoffRecommendation": recommendation,
        "summary": {
            "planStatus": plan_status,
            "failedCheckCount": len(failed_checks),
            "candidateActionCount": len(actions),
            "reviewOnlyCount": len(review_only),
            "needsMoreViews": needs_more_views,
            "targetedNodes": sorted({str(action["targetName"]) for action in actions}),
        },
        "guardrails": [
            "Only Guide or Biped node targets may be nudged; mesh, materials and Skin weights are untouched.",
            "Each apply step must be capped by maxSingleStepHeightRatio and may require multiple guarded passes.",
            "Strict and role-aware CT checks must not regress after any proposed move.",
            "Symmetry and parent-child chain order must remain valid after paired limb corrections.",
            "A fresh MDC local-agent visual review must inspect regenerated front/side/top and region evidence before Skin.",
        ],
        "failedChecks": failed_checks,
        "actions": actions,
        "reviewOnly": review_only,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert MDC local visual signoff blockers into bounded Stage01 correction targets.")
    parser.add_argument("snapshot_json", type=Path)
    parser.add_argument("--asset-name", default="")
    parser.add_argument("--visual-qc-json", type=Path, default=None)
    parser.add_argument("--visual-signoff-json", type=Path, default=None)
    parser.add_argument("--slice-analysis-json", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--out-json", type=Path, default=None)
    parser.add_argument("--md-out-dir", type=Path, default=None)
    parser.add_argument("--max-step-height", type=float, default=0.025)
    args = parser.parse_args()

    snapshot = load_json(args.snapshot_json)
    visual_qc = load_json(args.visual_qc_json)
    signoff = load_json(args.visual_signoff_json)
    asset_name = args.asset_name or str(snapshot.get("assetName") or args.snapshot_json.stem.replace("_visual_snapshot", ""))
    out_dir = args.out_dir or args.snapshot_json.parent
    out_json = args.out_json or out_dir / f"{asset_name}_mdc_visual_correction_plan.json"
    md_out_dir = args.md_out_dir or out_json.parent
    out_md = md_out_dir / f"{asset_name}_mdc_visual_correction_plan.md"

    paths = {
        "snapshotJson": str(args.snapshot_json),
        "visualQcJson": str(args.visual_qc_json) if args.visual_qc_json else "",
        "visualSignoffJson": str(args.visual_signoff_json) if args.visual_signoff_json else "",
        "sliceAnalysisJson": str(args.slice_analysis_json) if args.slice_analysis_json else "",
    }
    plan = build_plan(
        snapshot=snapshot,
        visual_qc=visual_qc,
        signoff=signoff,
        asset_name=asset_name,
        paths=paths,
        max_step_height=args.max_step_height,
    )
    write_json(out_json, plan)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(plan_markdown(plan), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "assetName": asset_name,
                "planStatus": plan["summary"]["planStatus"],
                "candidateActionCount": plan["summary"]["candidateActionCount"],
                "reviewOnlyCount": plan["summary"]["reviewOnlyCount"],
                "correctionPlanJson": str(out_json),
                "correctionPlanMarkdown": str(out_md),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
