from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: str) -> dict[str, Any]:
    if not path:
        return {}
    file_path = Path(path)
    if not file_path.exists():
        return {}
    return json.loads(file_path.read_text(encoding="utf-8-sig", errors="replace"))


def number(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def get_bool(data: dict[str, Any], name: str) -> bool:
    return data.get(name) is True


def status(ready: bool, pending: bool = False) -> str:
    if ready:
        return "ready"
    if pending:
        return "pending"
    return "blocked"


def add_blocker(blockers: list[dict[str, str]], code: str, message: str, owner: str = "rigging") -> None:
    blockers.append({"code": code, "owner": owner, "message": message})


MDC_SEMANTIC_RISK_OVERRIDES: dict[str, dict[str, str]] = {
    "multiview_wrap_signoff_required": {
        "owner": "mdc_agent",
        "message": "Generated guides and numeric Biped diagnostics do not prove front/side/top wrapping. The MDC local visual agent must inspect the wire-bone views before Skin setup.",
        "suggestedAction": "Review front, side and top wire-bone screenshots plus pelvis, hand and foot crops. Approve only when the Biped centerline, limb pivots and foot/toe direction sit inside the visible model volume in all relevant views.",
    },
    "leg_landmarks_may_be_clothing_occluded": {
        "owner": "mdc_agent",
        "message": "Wide lower-body clothing can hide the true hip/knee/ankle chain; a mechanically fitted Biped may still be following the robe or skirt silhouette instead of the leg anatomy.",
        "suggestedAction": "Use front, side and top wire-bone views plus foot crops and knee/ankle cross sections. Approve only if hips, knees and ankles follow the under-clothing leg chain and visible boot/foot pivots, not the garment edge.",
    },
}


def normalize_mdc_review_payload(risk: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(risk)
    if normalized.get("severity") == "skin_blocker":
        normalized["owner"] = "mdc_agent"
    override = MDC_SEMANTIC_RISK_OVERRIDES.get(str(normalized.get("code", "")))
    if override:
        normalized.update(override)
    return normalized


REQUIRED_SIGNOFF_TOP_LEVEL = [
    "assetName",
    "decisionPolicy",
    "reviewer",
    "reviewedAt",
    "checks",
    "stage01HandoffRecommendation",
    "notes",
]

REQUIRED_SIGNOFF_CHECKS = [
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
]

ALLOWED_SIGNOFF_STATUSES = {"pass", "blocker", "needs_detail", "uncertain", "not_visible"}
ALLOWED_SIGNOFF_RECOMMENDATIONS = {"approve_for_mdc_skin_setup", "block_until_fixed", "needs_more_views"}


def evaluate_multiview_signoff(visual_signoff: dict[str, Any]) -> dict[str, Any]:
    required_checks = REQUIRED_SIGNOFF_CHECKS
    if not visual_signoff:
        return {
            "available": False,
            "ready": False,
            "schemaValid": False,
            "schemaIssues": ["visual signoff JSON is missing"],
            "requiredChecks": required_checks,
            "missingChecks": required_checks,
            "failedChecks": [],
            "recommendation": "",
        }

    schema_issues: list[str] = []
    for name in REQUIRED_SIGNOFF_TOP_LEVEL:
        if name not in visual_signoff:
            schema_issues.append(f"missing top-level field: {name}")
    if visual_signoff.get("decisionPolicy") != "visual_semantic_gate_only":
        schema_issues.append("decisionPolicy must be visual_semantic_gate_only")

    checks = visual_signoff.get("checks", {})
    if not isinstance(checks, dict):
        schema_issues.append("checks must be an object")
        checks = {}
    missing = [name for name in required_checks if name not in checks]
    for name in missing:
        schema_issues.append(f"missing required check: {name}")

    failed: list[dict[str, str]] = []
    for name in required_checks:
        check = checks.get(name)
        status_value = check.get("status") if isinstance(check, dict) else None
        if not isinstance(check, dict):
            schema_issues.append(f"check {name} must be an object")
        elif status_value not in ALLOWED_SIGNOFF_STATUSES:
            schema_issues.append(f"check {name} has invalid status: {status_value}")
        elif not isinstance(check.get("evidence"), list):
            schema_issues.append(f"check {name} evidence must be an array")
        elif not isinstance(check.get("comment"), str):
            schema_issues.append(f"check {name} comment must be a string")
        if status_value != "pass":
            failed.append(
                {
                    "check": name,
                    "status": str(status_value or "missing"),
                    "comment": str(check.get("comment", "")) if isinstance(check, dict) else "",
                }
            )

    recommendation = str(visual_signoff.get("stage01HandoffRecommendation", ""))
    if recommendation not in ALLOWED_SIGNOFF_RECOMMENDATIONS:
        schema_issues.append(f"invalid stage01HandoffRecommendation: {recommendation}")
    if not isinstance(visual_signoff.get("notes"), list):
        schema_issues.append("notes must be an array")

    schema_valid = not schema_issues
    ready = schema_valid and recommendation == "approve_for_mdc_skin_setup" and not missing and not failed
    return {
        "available": True,
        "ready": ready,
        "schemaValid": schema_valid,
        "schemaIssues": schema_issues,
        "requiredChecks": required_checks,
        "missingChecks": missing,
        "failedChecks": failed,
        "recommendation": recommendation,
        "reviewer": visual_signoff.get("reviewer", ""),
        "reviewedAt": visual_signoff.get("reviewedAt", ""),
    }


def analyze(
    *,
    asset_name: str,
    body_profile: dict[str, Any],
    biped_fit_qc: dict[str, Any],
    visual_qc: dict[str, Any],
    rig_detail: dict[str, Any],
    rig_asset_qc: dict[str, Any],
    slice_analysis: dict[str, Any],
    visual_signoff: dict[str, Any],
    mdc_semantic_confirmed: bool,
    skin_weights_complete: bool,
) -> dict[str, Any]:
    skeleton = rig_asset_qc.get("skeleton", {})
    transform = rig_asset_qc.get("transform", {})
    materials = rig_asset_qc.get("materials", {})

    biped_output_available = bool(biped_fit_qc) and biped_fit_qc.get("bipedFound") is True
    biped_fit_ready = (
        biped_output_available
        and not biped_fit_qc.get("missingGuides")
        and not biped_fit_qc.get("missingFitSamples")
        and not biped_fit_qc.get("fitFailures")
        and not biped_fit_qc.get("outsideBoundsSamples")
    )
    ct_wrap_available = bool(slice_analysis) and isinstance(slice_analysis.get("segments"), dict)
    ct_wrap_failure_count = int(slice_analysis.get("strictWrapFailureCount", 0) or 0) if ct_wrap_available else 0
    ct_wrap_ready = ct_wrap_available and ct_wrap_failure_count == 0
    visual_available = bool(visual_qc) and bool(visual_qc.get("screenshots") or visual_qc.get("visualMode"))
    detail_available = bool(rig_detail) and bool(rig_detail.get("semanticSkinReview") or rig_detail.get("boneReviews"))
    semantic_skin_review = rig_detail.get("semanticSkinReview", {})
    semantic_risks = semantic_skin_review.get("risks", [])
    multiview_signoff = evaluate_multiview_signoff(visual_signoff)
    raw_semantic_skin_blockers = [
        normalize_mdc_review_payload(risk)
        for risk in semantic_risks
        if isinstance(risk, dict) and risk.get("severity") == "skin_blocker"
    ]
    semantic_skin_blockers = [
        risk
        for risk in raw_semantic_skin_blockers
        if not (
            risk.get("code") in {"multiview_wrap_signoff_required", "leg_landmarks_may_be_clothing_occluded"}
            and multiview_signoff["ready"]
        )
    ]
    semantic_policy_ready = not semantic_skin_blockers
    semantic_skin_ready = semantic_policy_ready and multiview_signoff["ready"] and biped_fit_ready and ct_wrap_ready
    semantic_confirmed = mdc_semantic_confirmed or multiview_signoff["ready"]
    has_skin = skeleton.get("hasSkin") is True
    skin_influence_ready = (
        has_skin
        and number(skeleton.get("maxInfluencePerVertex")) <= 4
        and number(skeleton.get("zeroWeightVertices")) == 0
        and number(skeleton.get("verticesChecked")) > 0
    )

    stage01_candidate_available = biped_output_available and visual_available and detail_available
    stage01_mechanical_handoff_ready = biped_fit_ready and ct_wrap_ready
    stage01_handoff_ready = (
        stage01_candidate_available
        and stage01_mechanical_handoff_ready
        and semantic_skin_ready
        and multiview_signoff["ready"]
        and semantic_confirmed
    )
    skin_setup_ready = stage01_handoff_ready and semantic_confirmed
    production_ready = skin_setup_ready and skin_weights_complete and skin_influence_ready

    blockers: list[dict[str, str]] = []
    if not stage01_candidate_available:
        add_blocker(blockers, "stage01_candidate_outputs_missing", "Required Biped candidate outputs are missing: Biped fit QC, screenshots/visual QC, or semantic review.")
    elif not biped_fit_ready:
        add_blocker(
            blockers,
            "biped_fit_requires_correction",
            "Biped exists, but fit diagnostics still report missing samples, guide distance failures, or nodes outside the model bounds.",
        )
    if not ct_wrap_available:
        add_blocker(
            blockers,
            "cross_section_wrap_missing",
            "Strict CT-style joint/segment slice analysis is missing; Stage01 cannot prove that the Biped chain is wrapped by the point cloud.",
        )
    elif not ct_wrap_ready:
        add_blocker(
            blockers,
            "cross_section_wrap_requires_correction",
            f"Strict CT-style slice analysis reports {ct_wrap_failure_count} unwrapped joint/segment samples. Refit guides/Biped until every sampled section is wrapped.",
        )
    for risk in semantic_skin_blockers:
        add_blocker(
            blockers,
            risk.get("code", "semantic_skin_risk"),
            risk.get("message", "Semantic Skin handoff risk requires resolution."),
            risk.get("owner", "rigging"),
        )
    if not multiview_signoff["ready"]:
        if multiview_signoff["available"]:
            failed_names = ", ".join(item["check"] for item in multiview_signoff["failedChecks"]) or "none"
            schema_issue_text = "; ".join(multiview_signoff.get("schemaIssues", [])) or "none"
            add_blocker(
                blockers,
                "multiview_wrap_signoff_failed",
                f"MDC local-agent multiview review did not approve front/side/top wrapping. Failed or non-pass checks: {failed_names}. Schema issues: {schema_issue_text}.",
                "mdc_agent",
            )
        else:
            add_blocker(
                blockers,
                "multiview_wrap_signoff_missing",
                "Front, side and top wire-bone screenshots must be reviewed for wrapping before the Stage01 candidate can enter Skin setup.",
                "mdc_agent",
            )
    if not semantic_confirmed:
        add_blocker(
            blockers,
            "semantic_confirmation_required",
            "The MDC local visual agent still needs to confirm the estimated guide landmarks against the mesh before Skin.",
            "mdc_agent",
        )
    if not has_skin:
        add_blocker(blockers, "skin_modifier_missing", "No Skin modifier exists yet; this is expected for Stage01 but blocks production delivery.")
    if not skin_weights_complete:
        add_blocker(blockers, "skin_weights_not_complete", "Skin weights and deformation checks have not been completed.")
    if materials.get("missingTextures"):
        add_blocker(blockers, "missing_textures", "Missing textures must be fixed before bound asset delivery.", "asset")
    if materials.get("absoluteTexturePaths"):
        add_blocker(blockers, "absolute_texture_paths", "Texture paths are absolute and should be localized before delivery.", "asset")

    prep_warnings: list[dict[str, str]] = []
    if multiview_signoff["ready"] and not mdc_semantic_confirmed:
        prep_warnings.append(
            {
                "code": "mdc_followup_recommended_after_agent_signoff",
                "message": "MDC signoff cleared Stage01 handoff; keep the same local-agent evidence pack attached for downstream production review.",
            }
        )
    if transform.get("centeredXY") is False:
        prep_warnings.append(
            {
                "code": "asset_not_centered_xy",
                "message": "Asset QC reports the mesh is not centered around origin in X/Y; confirm project pivot policy before skinning.",
            }
        )
    for issue in rig_asset_qc.get("issues", []):
        if isinstance(issue, str) and "height looks too large" in issue:
            prep_warnings.append(
                {
                    "code": "scale_policy_unconfirmed",
                    "message": "Asset QC reports a large model height; confirm scene unit and export scale before skinning.",
                }
            )
            break

    body_type = body_profile.get("bodyType", "unknown")
    hand_detail = (
        rig_detail.get("skeletonPlan", {})
        .get("bipedStructure", {})
        .get("handDetail", "unknown")
    )
    mdc_checklist = [
        {
            "id": "open_scene_and_screenshots",
            "status": "done" if multiview_signoff["ready"] else "required",
            "check": "Open the Stage01 rig scene plus front/side/top wire-bone screenshots and visual_review evidence pack.",
        },
        {
            "id": "confirm_multiview_wrapping",
            "status": "done" if multiview_signoff["ready"] else "required",
            "check": "Confirm in front, side and top views that the Biped centerline and limb pivots sit inside the character volume and follow the local limb direction.",
        },
        {
            "id": "confirm_body_center_chain",
            "status": "done" if semantic_confirmed else "required",
            "check": "Confirm Biped COM/Pelvis sit at the visual waist/center of mass; Biped Spine, Chest, Neck and Head follow the body/head volume.",
        },
        {
            "id": "confirm_root_deformer_policy",
            "status": "done" if semantic_confirmed else "required",
            "check": "Confirm Biped COM is control-only and body deformation starts from Biped Pelvis in Skin.",
        },
        {
            "id": "confirm_headtop_vs_crest",
            "status": "done" if semantic_confirmed else "required",
            "check": "Confirm the Biped Head is aligned to skull/helmet volume; HeadTop/CrestTop guides are visual references only unless the Biped structure is explicitly extended.",
        },
        {
            "id": "confirm_leg_and_foot_pivots",
            "status": "done" if semantic_confirmed else "required",
            "check": "Confirm hip, knee, ankle, rear-foot and toe/front-foot pivots match the model and bend direction in front/side/top views; for robe or skirt silhouettes, confirm the chain follows the hidden leg anatomy rather than the clothing edge.",
        },
        {
            "id": "confirm_arm_centerlines",
            "status": "done" if semantic_confirmed else "required",
            "check": "Confirm clavicle, shoulder, elbow, wrist and hand-mass guides use the local limb centerline, not the silhouette edge.",
        },
        {
            "id": "confirm_ct_slice_wrapping",
            "status": "done" if ct_wrap_ready else "required",
            "check": "Confirm every joint/segment CT-style slice is green/strictly wrapped; red slices must be corrected before handoff.",
        },
        {
            "id": "confirm_deferred_details",
            "status": "done" if semantic_confirmed else "required",
            "check": "Confirm whether beak, cloth, weapon, wing, claw or finger details require Biped structure/options before Skin; do not add ordinary Bones to the body flow.",
        },
    ]

    skin_tasks = [
        {
            "id": "use_biped_skeleton",
            "status": status(stage01_candidate_available),
            "note": "Use the fitted Biped as the only skeleton; visual guides are calibration targets, not a second bone system.",
        },
        {
            "id": "correct_biped_fit",
            "status": status(biped_fit_ready),
            "note": "Continue visual/Figure Mode calibration until Biped fit QC has no missing samples, distance failures, or outside-bounds nodes.",
        },
        {
            "id": "correct_ct_slice_wrap",
            "status": status(ct_wrap_ready),
            "note": "Continue guide/Biped correction until strict CT-style slice analysis has zero unwrapped samples.",
        },
        {
            "id": "mdc_landmark_signoff",
            "status": status(semantic_confirmed),
            "note": "Required because current guides are generated from mesh-profile and centerline estimates. Can be satisfied by a passing MDC local-agent visual signoff.",
        },
        {
            "id": "multiview_wrap_signoff",
            "status": status(multiview_signoff["ready"]),
            "note": "Required MDC local-agent review of front, side and top wrapping. A generated candidate is not accepted without this signoff.",
        },
        {
            "id": "resolve_semantic_skin_blockers",
            "status": status(semantic_skin_ready),
            "note": "Biped COM/Pelvis policy, robe/leg occlusion, head/crest visual split, hand detail and foot/toe pivots must be signed off before Skin.",
        },
        {
            "id": "add_skin_modifier",
            "status": status(has_skin, pending=skin_setup_ready and not has_skin),
            "note": "Add Skin to the character mesh only after MDC semantic signoff.",
        },
        {
            "id": "add_biped_bones_to_skin",
            "status": status(has_skin, pending=skin_setup_ready and not has_skin),
            "note": "Add the required Biped nodes to Skin; do not add AIRA_BONE_* or other generated template bones.",
        },
        {
            "id": "initial_weight_pass",
            "status": status(skin_weights_complete),
            "note": "Create first-pass rigid/soft weights for pelvis, torso, head, arms, hand masses, legs, feet and toe pivots.",
        },
        {
            "id": "weight_qc",
            "status": status(skin_influence_ready),
            "note": "Re-run Asset QC and require max influences <= 4 and zero unweighted vertices.",
        },
    ]

    return {
        "assetName": asset_name,
        "gateMode": "stage01_to_skin_prep_gate",
        "bodyType": body_type,
        "handDetail": hand_detail,
        "decisionPolicy": "visual_semantic_gate_only",
        "scorePolicy": "scores_disabled_for_decision_diagnostic_only",
        "stage01CandidateAvailable": stage01_candidate_available,
        "stage01MechanicalHandoffReady": stage01_mechanical_handoff_ready,
        "semanticPolicyReady": semantic_policy_ready,
        "multiviewWrapConfirmed": multiview_signoff["ready"],
        "semanticSkinReady": semantic_skin_ready,
        "stage01HandoffReady": stage01_handoff_ready,
        "skinSetupReady": skin_setup_ready,
        "productionReady": production_ready,
        "mdcSemanticConfirmed": mdc_semantic_confirmed,
        "semanticConfirmed": semantic_confirmed,
        "skinWeightsComplete": skin_weights_complete,
        "readiness": {
            "bipedFit": {
                "ready": biped_fit_ready,
                "available": biped_output_available,
                "score": "hidden_diagnostic_only",
                "sourceProductionReady": biped_fit_qc.get("productionReady"),
                "decisionUse": "diagnostic_only",
                "fitRefinement": biped_fit_qc.get("fitRefinement", {}),
            },
            "visual": {
                "ready": visual_available,
                "score": "hidden_diagnostic_only",
                "sourceProductionReady": visual_qc.get("productionReady"),
                "decisionUse": "diagnostic_only",
            },
            "ctSliceWrap": {
                "ready": ct_wrap_ready,
                "available": ct_wrap_available,
                "strictWrapFailureCount": ct_wrap_failure_count,
                "failureExamples": slice_analysis.get("strictWrapFailures", [])[:12] if ct_wrap_available else [],
                "decisionUse": "decision_gate",
            },
            "rigDetail": {
                "ready": detail_available,
                "score": "hidden_diagnostic_only",
                "sourceProductionReady": rig_detail.get("productionReady"),
                "decisionUse": "diagnostic_only",
            },
            "semanticSkinReview": {
                "ready": semantic_skin_ready,
                "semanticPolicyReady": semantic_policy_ready,
                "skinBlockerCount": len(semantic_skin_blockers),
                "riskCount": len(semantic_risks) if isinstance(semantic_risks, list) else 0,
            },
            "multiviewWrapSignoff": multiview_signoff,
            "skinInfluence": {
                "ready": skin_influence_ready,
                "hasSkin": has_skin,
                "maxInfluencePerVertex": skeleton.get("maxInfluencePerVertex"),
                "zeroWeightVertices": skeleton.get("zeroWeightVertices"),
                "verticesChecked": skeleton.get("verticesChecked"),
            },
        },
        "mdcSemanticChecklist": mdc_checklist,
        "skinPrepTasks": skin_tasks,
        "semanticSkinBlockers": semantic_skin_blockers,
        "productionBlockers": blockers,
        "prepWarnings": prep_warnings,
        "decision": (
            "Biped candidate exists, but Biped fit diagnostics must be corrected before Skin setup."
            if stage01_candidate_available and not biped_fit_ready
            else "Biped candidate exists, but CT-style slice wrapping reports unwrapped joints/segments that must be corrected."
            if stage01_candidate_available and biped_fit_ready and not ct_wrap_ready
            else "Visual candidate exists, but front/side/top wrapping has not been approved by MDC local-agent review."
            if stage01_candidate_available and not multiview_signoff["ready"]
            else "Visual candidate exists, but semantic Skin blockers must be resolved before Skin setup."
            if stage01_candidate_available and not semantic_policy_ready
            else "Visual candidate exists and has no semantic blockers; MDC local-agent visual signoff is still required before Skin setup."
            if stage01_candidate_available and semantic_policy_ready and not semantic_confirmed
            else "Required visual candidate outputs are missing."
            if not stage01_candidate_available
            else "Visual semantic signoff is complete; proceed with Skin setup."
        ),
    }


def write_markdown(qc: dict[str, Any], inputs: dict[str, str], md_path: Path) -> None:
    lines = [
        f"# Stage01 Skin Prep Gate: {qc['assetName']}",
        "",
        f"- Gate mode: `{qc['gateMode']}`",
        f"- Body type: `{qc['bodyType']}`",
        f"- Hand detail: `{qc['handDetail']}`",
        f"- Decision policy: `{qc['decisionPolicy']}`",
        f"- Score policy: `{qc['scorePolicy']}`",
        f"- Stage01 candidate available: `{qc['stage01CandidateAvailable']}`",
        f"- Multiview wrap confirmed: `{qc['multiviewWrapConfirmed']}`",
        f"- Semantic policy ready: `{qc['semanticPolicyReady']}`",
        f"- Semantic Skin ready: `{qc['semanticSkinReady']}`",
        f"- Semantic confirmed: `{qc['semanticConfirmed']}`",
        f"- Stage01 handoff ready: `{qc['stage01HandoffReady']}`",
        f"- Skin setup ready: `{qc['skinSetupReady']}`",
        f"- Production ready: `{qc['productionReady']}`",
        f"- Decision: {qc['decision']}",
        "",
        "## Inputs",
        "",
    ]
    for name, path in inputs.items():
        if path:
            lines.append(f"- {name}: `{path}`")

    lines += [
        "",
        "## Readiness Matrix",
        "",
        "| Gate | Available / Ready | State | Decision use |",
        "| --- | --- | --- | --- |",
    ]
    readiness = qc["readiness"]
    biped_fit = readiness.get("bipedFit") or readiness.get("templateMechanical") or {
        "ready": False,
        "decisionUse": "diagnostic_only",
    }
    lines.append(
        f"| Biped fit output | `{biped_fit['ready']}` | `score_hidden` | `{biped_fit['decisionUse']}` |"
    )
    lines.append(
        f"| Visual screenshots / QC output | `{readiness['visual']['ready']}` | `score_hidden` | `{readiness['visual']['decisionUse']}` |"
    )
    ct_wrap = readiness["ctSliceWrap"]
    ct_wrap_state = f"available={ct_wrap['available']}, strictWrapFailures={ct_wrap['strictWrapFailureCount']}"
    lines.append(f"| CT-style slice wrap | `{ct_wrap['ready']}` | `{ct_wrap_state}` | `{ct_wrap['decisionUse']}` |")
    lines.append(
        f"| Rig detail diagnostic output | `{readiness['rigDetail']['ready']}` | `score_hidden` | `{readiness['rigDetail']['decisionUse']}` |"
    )
    multiview = readiness["multiviewWrapSignoff"]
    multiview_state = (
        f"recommendation={multiview.get('recommendation') or 'missing'}, "
        f"schemaValid={multiview.get('schemaValid')}, "
        f"failedChecks={len(multiview.get('failedChecks', []))}, "
        f"missingChecks={len(multiview.get('missingChecks', []))}"
    )
    lines.append(
        f"| Front/side/top wrap signoff | `{multiview['ready']}` | `{multiview_state}` | `decision_gate` |"
    )
    semantic = readiness["semanticSkinReview"]
    semantic_state = f"semanticPolicyReady={semantic['semanticPolicyReady']}, skinBlockers={semantic['skinBlockerCount']}, risks={semantic['riskCount']}"
    lines.append(f"| Semantic Skin review | `{semantic['ready']}` | `{semantic_state}` | `decision_gate` |")
    skin = readiness["skinInfluence"]
    skin_state = (
        f"hasSkin={skin['hasSkin']}, maxInfluence={skin['maxInfluencePerVertex']}, "
        f"zeroWeightVertices={skin['zeroWeightVertices']}, verticesChecked={skin['verticesChecked']}"
    )
    lines.append(f"| Skin influence QC | `{skin['ready']}` | `{skin_state}` | `post_skin_delivery_gate` |")

    lines += ["", "## MDC Semantic Checklist", ""]
    for item in qc["mdcSemanticChecklist"]:
        mark = "x" if item["status"] == "done" else " "
        lines.append(f"- [{mark}] `{item['id']}`: {item['check']}")

    lines += [
        "",
        "## Skin Prep Tasks",
        "",
        "| Task | Status | Note |",
        "| --- | --- | --- |",
    ]
    for task in qc["skinPrepTasks"]:
        lines.append(f"| `{task['id']}` | `{task['status']}` | {task['note']} |")

    lines += ["", "## Semantic Skin Blockers", ""]
    if qc.get("semanticSkinBlockers"):
        for blocker in qc["semanticSkinBlockers"]:
            lines.append(
                f"- `{blocker.get('code')}` ({blocker.get('severity')}, {blocker.get('owner')}): {blocker.get('message')} Suggested action: {blocker.get('suggestedAction')}"
            )
    else:
        lines.append("- None")

    lines += ["", "## Production Blockers", ""]
    if qc["productionBlockers"]:
        for blocker in qc["productionBlockers"]:
            lines.append(f"- `{blocker['code']}` ({blocker['owner']}): {blocker['message']}")
    else:
        lines.append("- None")

    lines += ["", "## Prep Warnings", ""]
    if qc["prepWarnings"]:
        for warning in qc["prepWarnings"]:
            lines.append(f"- `{warning['code']}`: {warning['message']}")
    else:
        lines.append("- None")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize Stage01 QC into a Skin-prep gate report.")
    parser.add_argument("--asset-name", default="")
    parser.add_argument("--body-profile-json", default="")
    parser.add_argument("--biped-fit-qc-json", default="")
    parser.add_argument("--template-qc-json", default="", help="Deprecated compatibility alias for old reports.")
    parser.add_argument("--visual-qc-json", default="")
    parser.add_argument("--rig-detail-review-json", default="")
    parser.add_argument("--rig-asset-qc-json", default="")
    parser.add_argument("--slice-analysis-json", default="")
    parser.add_argument("--visual-signoff-json", default="")
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--md-out-dir", default="")
    parser.add_argument("--mdc-semantic-confirmed", action="store_true")
    parser.add_argument("--skin-weights-complete", action="store_true")
    args = parser.parse_args()

    body_profile = load_json(args.body_profile_json)
    biped_fit_qc_path = args.biped_fit_qc_json or args.template_qc_json
    biped_fit_qc = load_json(biped_fit_qc_path)
    visual_qc = load_json(args.visual_qc_json)
    rig_detail = load_json(args.rig_detail_review_json)
    rig_asset_qc = load_json(args.rig_asset_qc_json)
    slice_analysis = load_json(args.slice_analysis_json)
    visual_signoff = load_json(args.visual_signoff_json)

    asset_name = (
        args.asset_name
        or biped_fit_qc.get("assetName")
        or visual_qc.get("assetName")
        or rig_detail.get("assetName")
        or body_profile.get("assetName")
        or "stage01_asset"
    )
    out_dir = Path(args.out_dir) if args.out_dir else Path(biped_fit_qc_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    md_dir = Path(args.md_out_dir) if args.md_out_dir else out_dir
    md_dir.mkdir(parents=True, exist_ok=True)

    qc = analyze(
        asset_name=asset_name,
        body_profile=body_profile,
        biped_fit_qc=biped_fit_qc,
        visual_qc=visual_qc,
        rig_detail=rig_detail,
        rig_asset_qc=rig_asset_qc,
        slice_analysis=slice_analysis,
        visual_signoff=visual_signoff,
        mdc_semantic_confirmed=args.mdc_semantic_confirmed,
        skin_weights_complete=args.skin_weights_complete,
    )
    inputs = {
        "bodyProfileJson": args.body_profile_json,
        "bipedFitQcJson": biped_fit_qc_path,
        "visualQcJson": args.visual_qc_json,
        "rigDetailReviewJson": args.rig_detail_review_json,
        "rigAssetQcJson": args.rig_asset_qc_json,
        "sliceAnalysisJson": args.slice_analysis_json,
        "visualSignoffJson": args.visual_signoff_json,
    }
    qc["inputs"] = inputs

    json_path = out_dir / f"{asset_name}_stage01_skin_prep_gate.json"
    md_path = md_dir / f"{asset_name}_stage01_skin_prep_gate.md"
    json_path.write_text(json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(qc, inputs, md_path)

    print(
        json.dumps(
            {
                "ok": True,
                "assetName": asset_name,
                "json": str(json_path),
                "markdown": str(md_path),
                "stage01HandoffReady": qc["stage01HandoffReady"],
                "skinSetupReady": qc["skinSetupReady"],
                "productionReady": qc["productionReady"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
