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


def analyze(
    *,
    asset_name: str,
    body_profile: dict[str, Any],
    template_qc: dict[str, Any],
    visual_qc: dict[str, Any],
    rig_detail: dict[str, Any],
    rig_asset_qc: dict[str, Any],
    manual_semantic_confirmed: bool,
    skin_weights_complete: bool,
) -> dict[str, Any]:
    skeleton = rig_asset_qc.get("skeleton", {})
    transform = rig_asset_qc.get("transform", {})
    materials = rig_asset_qc.get("materials", {})

    template_available = bool(template_qc) and not template_qc.get("missingGuides") and not template_qc.get("missingBones")
    visual_available = bool(visual_qc) and bool(visual_qc.get("screenshots") or visual_qc.get("visualMode"))
    detail_available = bool(rig_detail) and bool(rig_detail.get("semanticSkinReview") or rig_detail.get("boneReviews"))
    semantic_skin_review = rig_detail.get("semanticSkinReview", {})
    semantic_risks = semantic_skin_review.get("risks", [])
    semantic_skin_blockers = [
        risk for risk in semantic_risks if isinstance(risk, dict) and risk.get("severity") == "skin_blocker"
    ]
    semantic_skin_ready = semantic_skin_review.get("readyForSkin") is True and not semantic_skin_blockers
    has_skin = skeleton.get("hasSkin") is True
    skin_influence_ready = (
        has_skin
        and number(skeleton.get("maxInfluencePerVertex")) <= 4
        and number(skeleton.get("zeroWeightVertices")) == 0
        and number(skeleton.get("verticesChecked")) > 0
    )

    stage01_candidate_available = template_available and visual_available and detail_available
    stage01_mechanical_handoff_ready = False
    stage01_handoff_ready = stage01_candidate_available and semantic_skin_ready and manual_semantic_confirmed
    skin_setup_ready = stage01_handoff_ready and manual_semantic_confirmed
    production_ready = skin_setup_ready and skin_weights_complete and skin_influence_ready

    blockers: list[dict[str, str]] = []
    if not stage01_candidate_available:
        add_blocker(blockers, "stage01_candidate_outputs_missing", "Required visual candidate outputs are missing: template skeleton data, screenshots/visual QC, or semantic review.")
    for risk in semantic_skin_blockers:
        add_blocker(
            blockers,
            risk.get("code", "semantic_skin_risk"),
            risk.get("message", "Semantic Skin handoff risk requires resolution."),
            risk.get("owner", "rigging"),
        )
    if not manual_semantic_confirmed:
        add_blocker(
            blockers,
            "manual_semantic_confirmation_required",
            "A human rigger still needs to confirm the estimated guide landmarks against the mesh before Skin.",
            "human",
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
    manual_checklist = [
        {
            "id": "open_scene_and_screenshots",
            "status": "done" if manual_semantic_confirmed else "required",
            "check": "Open the Stage01 rig scene plus front/side/top visual QC screenshots.",
        },
        {
            "id": "confirm_body_center_chain",
            "status": "done" if manual_semantic_confirmed else "required",
            "check": "Confirm Root/COM and Pelvis sit at the visual waist/center of mass; Spine, Chest, Neck, Head and HeadTop follow the body/head volume.",
        },
        {
            "id": "confirm_root_deformer_policy",
            "status": "done" if manual_semantic_confirmed else "required",
            "check": "Confirm Root/COM is a control-only waist origin and no Root->Pelvis or accessory reference bone is included as a Skin influence.",
        },
        {
            "id": "confirm_headtop_vs_crest",
            "status": "done" if manual_semantic_confirmed else "required",
            "check": "Confirm HeadTop is skull/helmet volume and CrestTop is only a non-deforming crest/headwear reference.",
        },
        {
            "id": "confirm_leg_and_foot_pivots",
            "status": "done" if manual_semantic_confirmed else "required",
            "check": "Confirm hip, knee, ankle, rear-foot and toe/front-foot pivots match the model and bend direction in side/top views.",
        },
        {
            "id": "confirm_arm_centerlines",
            "status": "done" if manual_semantic_confirmed else "required",
            "check": "Confirm clavicle, shoulder, elbow, wrist and hand-mass guides use the local limb centerline, not the silhouette edge.",
        },
        {
            "id": "confirm_deferred_details",
            "status": "done" if manual_semantic_confirmed else "required",
            "check": "Confirm whether beak, cloth, weapon, wing, claw or finger detail bones must be added before Skin; hat/crest stays non-deforming unless explicitly rigged.",
        },
    ]

    skin_tasks = [
        {
            "id": "use_template_skeleton",
            "status": status(stage01_candidate_available),
            "note": "Use AIRA_BONE_* only after visual semantic blockers are resolved; Biped remains tutorial/reference only.",
        },
        {
            "id": "manual_landmark_signoff",
            "status": status(manual_semantic_confirmed),
            "note": "Required because current guides are generated from mesh-profile and centerline estimates.",
        },
        {
            "id": "resolve_semantic_skin_blockers",
            "status": status(semantic_skin_ready),
            "note": "Waist Root/COM policy, HeadTop skull vs CrestTop accessory split, hand tip detail and Heel/Foot/Toe depth chain must be represented before Skin.",
        },
        {
            "id": "add_skin_modifier",
            "status": status(has_skin, pending=skin_setup_ready and not has_skin),
            "note": "Add Skin to the character mesh only after manual semantic signoff.",
        },
        {
            "id": "add_template_bones_to_skin",
            "status": status(has_skin, pending=skin_setup_ready and not has_skin),
            "note": "Add all required AIRA_BONE_* nodes; defer Biped nodes unless the project explicitly wants Biped Skin bones.",
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
        "semanticSkinReady": semantic_skin_ready,
        "stage01HandoffReady": stage01_handoff_ready,
        "skinSetupReady": skin_setup_ready,
        "productionReady": production_ready,
        "manualSemanticConfirmed": manual_semantic_confirmed,
        "skinWeightsComplete": skin_weights_complete,
        "readiness": {
            "templateMechanical": {
                "ready": template_available,
                "score": "hidden_diagnostic_only",
                "sourceProductionReady": template_qc.get("productionReady"),
                "decisionUse": "diagnostic_only",
            },
            "visual": {
                "ready": visual_available,
                "score": "hidden_diagnostic_only",
                "sourceProductionReady": visual_qc.get("productionReady"),
                "decisionUse": "diagnostic_only",
            },
            "rigDetail": {
                "ready": detail_available,
                "score": "hidden_diagnostic_only",
                "sourceProductionReady": rig_detail.get("productionReady"),
                "decisionUse": "diagnostic_only",
            },
            "semanticSkinReview": {
                "ready": semantic_skin_ready,
                "skinBlockerCount": len(semantic_skin_blockers),
                "riskCount": len(semantic_risks) if isinstance(semantic_risks, list) else 0,
            },
            "skinInfluence": {
                "ready": skin_influence_ready,
                "hasSkin": has_skin,
                "maxInfluencePerVertex": skeleton.get("maxInfluencePerVertex"),
                "zeroWeightVertices": skeleton.get("zeroWeightVertices"),
                "verticesChecked": skeleton.get("verticesChecked"),
            },
        },
        "manualSemanticChecklist": manual_checklist,
        "skinPrepTasks": skin_tasks,
        "semanticSkinBlockers": semantic_skin_blockers,
        "productionBlockers": blockers,
        "prepWarnings": prep_warnings,
        "decision": (
            "Visual candidate exists, but semantic Skin blockers must be resolved before Skin setup."
            if stage01_candidate_available and not semantic_skin_ready
            else "Visual candidate exists and has no semantic blockers; human visual signoff is still required before Skin setup."
            if stage01_candidate_available and semantic_skin_ready and not manual_semantic_confirmed
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
        f"- Semantic Skin ready: `{qc['semanticSkinReady']}`",
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
    lines.append(
        f"| Template skeleton output | `{readiness['templateMechanical']['ready']}` | `score_hidden` | `{readiness['templateMechanical']['decisionUse']}` |"
    )
    lines.append(
        f"| Visual screenshots / QC output | `{readiness['visual']['ready']}` | `score_hidden` | `{readiness['visual']['decisionUse']}` |"
    )
    lines.append(
        f"| Rig detail diagnostic output | `{readiness['rigDetail']['ready']}` | `score_hidden` | `{readiness['rigDetail']['decisionUse']}` |"
    )
    semantic = readiness["semanticSkinReview"]
    semantic_state = f"skinBlockers={semantic['skinBlockerCount']}, risks={semantic['riskCount']}"
    lines.append(f"| Semantic Skin review | `{semantic['ready']}` | `{semantic_state}` | `decision_gate` |")
    skin = readiness["skinInfluence"]
    skin_state = (
        f"hasSkin={skin['hasSkin']}, maxInfluence={skin['maxInfluencePerVertex']}, "
        f"zeroWeightVertices={skin['zeroWeightVertices']}, verticesChecked={skin['verticesChecked']}"
    )
    lines.append(f"| Skin influence QC | `{skin['ready']}` | `{skin_state}` | `post_skin_delivery_gate` |")

    lines += ["", "## Manual Semantic Checklist", ""]
    for item in qc["manualSemanticChecklist"]:
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
    parser.add_argument("--template-qc-json", default="")
    parser.add_argument("--visual-qc-json", default="")
    parser.add_argument("--rig-detail-review-json", default="")
    parser.add_argument("--rig-asset-qc-json", default="")
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--manual-semantic-confirmed", action="store_true")
    parser.add_argument("--skin-weights-complete", action="store_true")
    args = parser.parse_args()

    body_profile = load_json(args.body_profile_json)
    template_qc = load_json(args.template_qc_json)
    visual_qc = load_json(args.visual_qc_json)
    rig_detail = load_json(args.rig_detail_review_json)
    rig_asset_qc = load_json(args.rig_asset_qc_json)

    asset_name = (
        args.asset_name
        or template_qc.get("assetName")
        or visual_qc.get("assetName")
        or rig_detail.get("assetName")
        or body_profile.get("assetName")
        or "stage01_asset"
    )
    out_dir = Path(args.out_dir) if args.out_dir else Path(args.template_qc_json).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    qc = analyze(
        asset_name=asset_name,
        body_profile=body_profile,
        template_qc=template_qc,
        visual_qc=visual_qc,
        rig_detail=rig_detail,
        rig_asset_qc=rig_asset_qc,
        manual_semantic_confirmed=args.manual_semantic_confirmed,
        skin_weights_complete=args.skin_weights_complete,
    )
    inputs = {
        "bodyProfileJson": args.body_profile_json,
        "templateQcJson": args.template_qc_json,
        "visualQcJson": args.visual_qc_json,
        "rigDetailReviewJson": args.rig_detail_review_json,
        "rigAssetQcJson": args.rig_asset_qc_json,
    }
    qc["inputs"] = inputs

    json_path = out_dir / f"{asset_name}_stage01_skin_prep_gate.json"
    md_path = out_dir / f"{asset_name}_stage01_skin_prep_gate.md"
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
