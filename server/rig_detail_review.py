from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

Point3 = list[float]


SEGMENT_SPECS: list[dict[str, Any]] = [
    {"phase": "01 pelvis and center", "start": "Pelvis", "end": "Spine", "role": "pelvis_to_spine", "min": 0.05, "max": 0.14, "rules": ["center", "up"]},
    {"phase": "02 torso", "start": "Spine", "end": "Chest", "role": "spine_to_chest", "min": 0.05, "max": 0.16, "rules": ["center", "up"]},
    {"phase": "02 torso", "start": "Chest", "end": "Neck", "role": "chest_to_neck", "min": 0.08, "max": 0.24, "rules": ["center", "up"]},
    {"phase": "06 neck and head", "start": "Neck", "end": "Head", "role": "short_neck_to_head", "min": 0.04, "max": 0.16, "rules": ["center", "up"]},
    {"phase": "06 neck and head", "start": "Head", "end": "HeadTop", "role": "head_volume_axis", "min": 0.04, "max": 0.14, "rules": ["center", "up"]},
    {"phase": "04 clavicle and arms", "start": "Chest", "end": "L_Clavicle", "role": "left_clavicle", "min": 0.10, "max": 0.28, "rules": ["left", "outward"]},
    {"phase": "04 clavicle and arms", "start": "L_Clavicle", "end": "L_Shoulder", "role": "left_shoulder_socket", "min": 0.06, "max": 0.20, "rules": ["left", "outward"]},
    {"phase": "04 clavicle and arms", "start": "L_Shoulder", "end": "L_Elbow", "role": "left_upper_arm", "min": 0.08, "max": 0.24, "rules": ["left", "outward", "down"]},
    {"phase": "04 clavicle and arms", "start": "L_Elbow", "end": "L_Wrist", "role": "left_forearm", "min": 0.05, "max": 0.18, "rules": ["left", "outward", "down"]},
    {"phase": "04 clavicle and arms", "start": "L_Wrist", "end": "L_Hand", "role": "left_hand_mass", "min": 0.01, "max": 0.09, "rules": ["left", "outward"]},
    {"phase": "04 clavicle and arms", "start": "L_Hand", "end": "L_HandTip", "role": "left_hand_tip_detail", "min": 0.015, "max": 0.08, "rules": ["left", "outward"]},
    {"phase": "04 clavicle and arms", "start": "Chest", "end": "R_Clavicle", "role": "right_clavicle", "min": 0.10, "max": 0.28, "rules": ["right", "outward"]},
    {"phase": "04 clavicle and arms", "start": "R_Clavicle", "end": "R_Shoulder", "role": "right_shoulder_socket", "min": 0.06, "max": 0.20, "rules": ["right", "outward"]},
    {"phase": "04 clavicle and arms", "start": "R_Shoulder", "end": "R_Elbow", "role": "right_upper_arm", "min": 0.08, "max": 0.24, "rules": ["right", "outward", "down"]},
    {"phase": "04 clavicle and arms", "start": "R_Elbow", "end": "R_Wrist", "role": "right_forearm", "min": 0.05, "max": 0.18, "rules": ["right", "outward", "down"]},
    {"phase": "04 clavicle and arms", "start": "R_Wrist", "end": "R_Hand", "role": "right_hand_mass", "min": 0.01, "max": 0.09, "rules": ["right", "outward"]},
    {"phase": "04 clavicle and arms", "start": "R_Hand", "end": "R_HandTip", "role": "right_hand_tip_detail", "min": 0.015, "max": 0.08, "rules": ["right", "outward"]},
    {"phase": "03 legs and feet", "start": "Pelvis", "end": "L_Hip", "role": "left_hip_socket", "min": 0.06, "max": 0.16, "rules": ["left", "outward", "down"]},
    {"phase": "03 legs and feet", "start": "L_Hip", "end": "L_Knee", "role": "left_thigh", "min": 0.10, "max": 0.24, "rules": ["left", "down"]},
    {"phase": "03 legs and feet", "start": "L_Knee", "end": "L_Ankle", "role": "left_calf", "min": 0.08, "max": 0.20, "rules": ["left", "down"]},
    {"phase": "03 legs and feet", "start": "L_Ankle", "end": "L_Heel", "role": "left_heel_depth_pivot", "min": 0.02, "max": 0.10, "rules": ["left", "down"]},
    {"phase": "03 legs and feet", "start": "L_Heel", "end": "L_Foot", "role": "left_midfoot_depth_axis", "min": 0.04, "max": 0.14, "rules": ["left", "toe_forward", "level"]},
    {"phase": "03 legs and feet", "start": "L_Foot", "end": "L_Toe", "role": "left_front_foot", "min": 0.06, "max": 0.20, "rules": ["left", "toe_forward", "level"]},
    {"phase": "03 legs and feet", "start": "Pelvis", "end": "R_Hip", "role": "right_hip_socket", "min": 0.06, "max": 0.16, "rules": ["right", "outward", "down"]},
    {"phase": "03 legs and feet", "start": "R_Hip", "end": "R_Knee", "role": "right_thigh", "min": 0.10, "max": 0.24, "rules": ["right", "down"]},
    {"phase": "03 legs and feet", "start": "R_Knee", "end": "R_Ankle", "role": "right_calf", "min": 0.08, "max": 0.20, "rules": ["right", "down"]},
    {"phase": "03 legs and feet", "start": "R_Ankle", "end": "R_Heel", "role": "right_heel_depth_pivot", "min": 0.02, "max": 0.10, "rules": ["right", "down"]},
    {"phase": "03 legs and feet", "start": "R_Heel", "end": "R_Foot", "role": "right_midfoot_depth_axis", "min": 0.04, "max": 0.14, "rules": ["right", "toe_forward", "level"]},
    {"phase": "03 legs and feet", "start": "R_Foot", "end": "R_Toe", "role": "right_front_foot", "min": 0.06, "max": 0.20, "rules": ["right", "toe_forward", "level"]},
]


ROLE_THICKNESS_RATIOS = {
    "root_to_pelvis": 0.052,
    "pelvis_to_spine": 0.052,
    "spine_to_chest": 0.052,
    "chest_to_neck": 0.052,
    "short_neck_to_head": 0.060,
    "head_volume_axis": 0.060,
    "left_clavicle": 0.026,
    "right_clavicle": 0.026,
    "left_shoulder_socket": 0.026,
    "right_shoulder_socket": 0.026,
    "left_upper_arm": 0.030,
    "right_upper_arm": 0.030,
    "left_forearm": 0.030,
    "right_forearm": 0.030,
    "left_hand_mass": 0.030,
    "right_hand_mass": 0.030,
    "left_hand_tip_detail": 0.020,
    "right_hand_tip_detail": 0.020,
    "left_hip_socket": 0.034,
    "right_hip_socket": 0.034,
    "left_thigh": 0.034,
    "right_thigh": 0.034,
    "left_calf": 0.034,
    "right_calf": 0.034,
    "left_rear_foot": 0.038,
    "right_rear_foot": 0.038,
    "left_heel_depth_pivot": 0.032,
    "right_heel_depth_pivot": 0.032,
    "left_midfoot_depth_axis": 0.034,
    "right_midfoot_depth_axis": 0.034,
    "left_front_foot": 0.038,
    "right_front_foot": 0.038,
}


def distance(a: Point3, b: Point3) -> float:
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def vector(a: Point3, b: Point3) -> Point3:
    return [b[i] - a[i] for i in range(3)]


def normalized(v: Point3) -> Point3:
    length = math.sqrt(sum(x * x for x in v))
    if length <= 1e-8:
        return [0.0, 0.0, 0.0]
    return [x / length for x in v]


def round_point(point: Point3 | None) -> Point3 | None:
    if point is None:
        return None
    return [round(v, 6) for v in point]


def bone_map(snapshot: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for bone in snapshot.get("templateBones", []):
        result[(bone.get("start", ""), bone.get("end", ""))] = bone
    return result


def skeleton_plan(body_type: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    guides = snapshot.get("guides", {})
    visible_hand_detail = "hand mass + tip detail"
    fingers = 0
    finger_links = 0
    if body_type != "compact_q_bird_wide_body_short_legs":
        visible_hand_detail = "four-finger tutorial default"
        fingers = 4
        finger_links = 3

    return {
        "bodyType": body_type,
        "characterClass": "A1 compact Q-bird hero" if body_type == "compact_q_bird_wide_body_short_legs" else "stylized humanoid",
        "guideCountExpected": len([v for v in guides.values() if v is not None]),
        "templateBoneCountExpected": len(SEGMENT_SPECS),
        "bipedStructure": {
            "spineLinks": 2,
            "neckLinks": 1,
            "legLinks": 3,
            "fingers": fingers,
            "fingerLinks": finger_links,
            "toes": 1,
            "toeLinks": 1,
            "trianglePelvis": True,
            "handDetail": visible_hand_detail,
            "rootDeformerPolicy": "root_guide_only_no_root_to_pelvis_template_bone",
            "headTopPolicy": "HeadTop is skull/helmet cap; CrestTop marks crest/headwear as a non-deforming accessory reference",
            "footPivotPolicy": "Heel/Foot/Toe depth guides generated from side/top mesh bounds",
        },
        "extraBonesDeferred": [
            "Fine finger/claw chains remain optional; add them only when separated texture or mesh landmarks are visible.",
            "CrestTop is available as a non-deforming accessory reference; do not add it to Skin unless a rigger explicitly creates a dedicated accessory rig.",
        ],
    }


def check_segment(
    spec: dict[str, Any],
    guides: dict[str, Point3 | None],
    bones: dict[tuple[str, str], dict[str, Any]],
    bounds: dict[str, Point3],
) -> dict[str, Any]:
    start_name = spec["start"]
    end_name = spec["end"]
    start = guides.get(start_name)
    end = guides.get(end_name)
    center = bounds["center"]
    size = bounds["size"]
    height = max(size[2], 1.0)
    width = max(size[0], 1.0)
    depth = max(size[1], 1.0)
    issues: list[str] = []
    warnings: list[str] = []
    bone = bones.get((start_name, end_name), {})

    if start is None:
        issues.append(f"missing start guide {start_name}")
    if end is None:
        issues.append(f"missing end guide {end_name}")
    if not bone or bone.get("exists") is not True:
        issues.append("missing template bone")

    if start is None or end is None:
        return {
            "phase": spec["phase"],
            "segment": f"{start_name}->{end_name}",
            "role": spec["role"],
            "status": "fail",
            "issues": issues,
            "warnings": warnings,
        }

    vec = vector(start, end)
    length_value = distance(start, end)
    ratio = length_value / height
    direction = normalized(vec)
    side = 1 if "left" in spec["role"] else -1 if "right" in spec["role"] else 0

    if ratio < spec["min"]:
        warnings.append(f"diagnostic length ratio {ratio:.3f} below reference {spec['min']:.3f}; verify visually")
    if ratio > spec["max"]:
        warnings.append(f"diagnostic length ratio {ratio:.3f} above reference {spec['max']:.3f}; verify visually")

    rules = spec["rules"]
    center_tol_x = width * 0.055
    center_tol_y = depth * 0.12
    if "center" in rules:
        for guide_name, point in [(start_name, start), (end_name, end)]:
            if abs(point[0] - center[0]) > center_tol_x:
                warnings.append(f"{guide_name} is off center X by {abs(point[0] - center[0]):.3f}; verify visually")
            if abs(point[1] - center[1]) > center_tol_y:
                warnings.append(f"{guide_name} is off center Y by {abs(point[1] - center[1]):.3f}")
    if "left" in rules and end[0] <= center[0] + width * 0.02:
        warnings.append(f"{end_name} should stay on the left side of the model; verify visually")
    if "right" in rules and end[0] >= center[0] - width * 0.02:
        warnings.append(f"{end_name} should stay on the right side of the model; verify visually")
    if "up" in rules and vec[2] <= 0:
        warnings.append("segment should move upward; verify visually")
    if "down" in rules and vec[2] >= height * 0.01:
        warnings.append("segment should move downward; verify visually")
    if "outward" in rules and side != 0 and vec[0] * side <= width * 0.005:
        warnings.append("segment should move outward from the body center; verify visually")
    if "toe_forward" in rules and vec[1] >= -depth * 0.04:
        warnings.append("toe segment should point toward character front (-Y); verify visually")
    if "level" in rules and abs(vec[2]) > height * 0.035:
        warnings.append("foot/toe segment has too much vertical tilt")

    bone_length = float(bone.get("boneLength") or 0)
    bone_width = float(bone.get("boneWidth") or 0)
    bone_height = float(bone.get("boneHeight") or 0)
    if bone_length and abs(bone_length - length_value) > height * 0.025:
        warnings.append(f"bone display length differs from guide length by {abs(bone_length - length_value):.3f}; verify visually")

    expected_thickness = height * ROLE_THICKNESS_RATIOS.get(spec["role"], 0.03)
    max_thickness = max(0.25, min(expected_thickness * 1.45, length_value * 0.55))
    min_thickness = max(0.20, min(expected_thickness * 0.45, length_value * 0.15))
    if bone_width:
        if bone_width < min_thickness:
            warnings.append(f"bone width {bone_width:.3f} is thinner than expected display range")
        if bone_width > max_thickness:
            warnings.append(f"bone width {bone_width:.3f} is thicker than expected display range")
    if bone_height:
        if bone_height < min_thickness:
            warnings.append(f"bone height {bone_height:.3f} is thinner than expected display range")
        if bone_height > max_thickness:
            warnings.append(f"bone height {bone_height:.3f} is thicker than expected display range")

    status = "fail" if issues else "warn" if warnings else "pass"
    return {
        "phase": spec["phase"],
        "segment": f"{start_name}->{end_name}",
        "role": spec["role"],
        "status": status,
        "start": round_point(start),
        "end": round_point(end),
        "length": round(length_value, 6),
        "lengthHeightRatio": round(ratio, 6),
        "direction": round_point(direction),
        "frontAngleDeg": round(math.degrees(math.atan2(vec[2], vec[0] if abs(vec[0]) > 1e-8 else 1e-8)), 3),
        "topAngleDeg": round(math.degrees(math.atan2(vec[1], vec[0] if abs(vec[0]) > 1e-8 else 1e-8)), 3),
        "boneLength": round(bone_length, 6),
        "boneWidth": round(bone_width, 6),
        "boneHeight": round(bone_height, 6),
        "issues": issues,
        "warnings": warnings,
    }


def mirror_review(reviews: list[dict[str, Any]], height: float) -> list[dict[str, Any]]:
    by_segment = {review["segment"]: review for review in reviews}
    pairs: list[dict[str, Any]] = []
    for review in reviews:
        segment = review["segment"]
        if "L_" not in segment:
            continue
        mate = segment.replace("L_", "R_")
        right = by_segment.get(mate)
        if not right:
            continue
        left_length = float(review.get("length") or 0)
        right_length = float(right.get("length") or 0)
        diff = abs(left_length - right_length)
        ready = diff <= height * 0.025
        pairs.append(
            {
                "left": segment,
                "right": mate,
                "leftLength": round(left_length, 6),
                "rightLength": round(right_length, 6),
                "lengthDiff": round(diff, 6),
                "ready": ready,
            }
        )
    return pairs


def semantic_skin_review(
    *,
    snapshot: dict[str, Any],
    body_profile: dict[str, Any] | None,
    plan: dict[str, Any],
) -> dict[str, Any]:
    guides = snapshot.get("guides", {})
    bounds = snapshot["bounds"]
    min_z = float(bounds["min"][2])
    size = bounds["size"]
    height = max(float(size[2]), 1.0)
    body_type = plan.get("bodyType", "unknown")
    description = ((body_profile or {}).get("description") or "").lower()
    risks: list[dict[str, Any]] = []
    policies: list[dict[str, str]] = []
    template_bones = bone_map(snapshot)

    def guide(name: str) -> Point3 | None:
        value = guides.get(name)
        return value if isinstance(value, list) and len(value) >= 3 else None

    def add_risk(code: str, severity: str, owner: str, message: str, suggested_action: str) -> None:
        risks.append(
            {
                "code": code,
                "severity": severity,
                "owner": owner,
                "status": "requires_signoff",
                "message": message,
                "suggestedAction": suggested_action,
            }
        )

    root = guide("Root")
    pelvis = guide("Pelvis")
    if root and pelvis:
        root_pelvis_ratio = abs(pelvis[2] - root[2]) / height
        root_near_floor = root[2] <= min_z + height * 0.03
        root_template_bone_exists = ("Root", "Pelvis") in template_bones
        if root_near_floor and root_pelvis_ratio >= 0.25 and root_template_bone_exists:
            add_risk(
                "root_to_pelvis_control_only",
                "skin_blocker",
                "rigging",
                "Root->Pelvis spans from the floor/root control area into the body. This is useful as a rig control/reference axis but unsafe as a deformation bone.",
                "Mark AIRA_BONE_Root_Pelvis / Biped COM as control-only and exclude it from Skin influences; start body deformation weights from Pelvis.",
            )
            policies.append(
                {
                    "code": "exclude_root_to_pelvis_from_skin",
                    "target": "AIRA_BONE_Root_Pelvis",
                    "policy": "control_only_non_deforming",
                }
            )
        elif root_near_floor:
            policies.append(
                {
                    "code": "root_guide_only_no_skin",
                    "target": "Root guide / Biped COM",
                    "policy": "control_only_reference_not_in_template_deformer_chain",
                }
            )
        else:
            policies.append(
                {
                    "code": "root_com_at_waist_control_only",
                    "target": "Root guide / Biped COM",
                    "policy": "control_only_origin_at_visual_waist_not_skin_influence",
                }
            )

    head = guide("Head")
    head_top = guide("HeadTop")
    crest_top = guide("CrestTop")
    if head and head_top:
        head_top_ratio = abs(head_top[2] - head[2]) / height
        head_top_near_bounds = head_top[2] >= min_z + height * 0.94
        crest_like_body = "crest" in description or body_type == "compact_q_bird_wide_body_short_legs"
        crest_template_bone_exists = ("HeadTop", "CrestTop") in template_bones
        if crest_template_bone_exists:
            add_risk(
                "cresttop_must_not_be_skin_bone",
                "skin_blocker",
                "rigging",
                "CrestTop/headwear is present as a template bone. On this model it is a hat/crest accessory reference, not the main head deformation chain.",
                "Remove HeadTop->CrestTop from Skin candidate bones. Keep HeadTop on the skull/helmet volume and use CrestTop only as a non-deforming accessory landmark.",
            )
        elif crest_like_body and head_top_ratio >= 0.10 and head_top_near_bounds and not crest_top:
            add_risk(
                "headtop_may_be_crest_or_ornament",
                "skin_blocker",
                "rigging",
                "HeadTop is driven by the highest sparse silhouette area on a character profile that explicitly includes a tall head/crest region.",
                "Confirm whether the upper silhouette is skull volume or crest/headwear. If it is crest/headwear, keep it as an accessory reference and keep the main Head bone on the skull mass.",
            )
        elif crest_like_body and crest_top:
            policies.append(
                {
                    "code": "headtop_skull_cresttop_accessory_reference",
                    "target": "HeadTop/CrestTop",
                    "policy": "main head deformation ends at HeadTop; CrestTop marks non-deforming crest/headwear extent",
                }
            )

    hand_detail = plan.get("bipedStructure", {}).get("handDetail", "")
    if hand_detail == "single hand mass":
        add_risk(
            "single_hand_mass_requires_detail_signoff",
            "skin_blocker",
            "rigging",
            "The current skeleton collapses each hand into one mass. This is acceptable only if the model has no visible fingers, claws, weapon grips, sleeve flaps or hand accessories that need independent deformation.",
            "Inspect both hand ends in front/side/top screenshots. Add finger/claw/detail/socket bones before Skin if any separated hand features are visible.",
        )
    elif guide("L_HandTip") and guide("R_HandTip"):
        policies.append(
            {
                "code": "hand_tip_detail_guides_available",
                "target": "L_HandTip/R_HandTip",
                "policy": "hand mass has distal detail candidate; fine fingers remain optional",
            }
        )

    left_foot = guide("L_Foot")
    left_toe = guide("L_Toe")
    right_foot = guide("R_Foot")
    right_toe = guide("R_Toe")
    left_heel = guide("L_Heel")
    right_heel = guide("R_Heel")
    if left_foot and left_toe and right_foot and right_toe and not (left_heel and right_heel):
        add_risk(
            "foot_pivots_require_side_top_signoff",
            "skin_blocker",
            "human",
            "Front view alone cannot prove foot pivot depth, toe/front-foot direction or knee bend direction for this deep Q-bird silhouette.",
            "Open side and top screenshots before Skin. Confirm rear-foot, front-foot/toe and knee bend direction match the model's actual pose.",
        )
    elif left_heel and right_heel:
        policies.append(
            {
                "code": "heel_midfoot_toe_depth_chain",
                "target": "L_Heel/L_Foot/L_Toe and R_Heel/R_Foot/R_Toe",
                "policy": "side/top depth represented explicitly in the template foot chain",
            }
        )

    skin_blocker_count = sum(1 for risk in risks if risk["severity"] == "skin_blocker")
    return {
        "mode": "semantic_skin_handoff_review",
        "readyForSkin": skin_blocker_count == 0,
        "riskCount": len(risks),
        "skinBlockerCount": skin_blocker_count,
        "risks": risks,
        "deformerPolicies": policies,
    }


def analyze(snapshot: dict[str, Any], body_profile: dict[str, Any] | None) -> dict[str, Any]:
    bounds = snapshot["bounds"]
    size = bounds["size"]
    height = max(size[2], 1.0)
    body_type = "unknown"
    if body_profile is not None:
        body_type = body_profile.get("bodyType", body_type)
    plan = skeleton_plan(body_type, snapshot)
    guides = snapshot.get("guides", {})
    bones = bone_map(snapshot)
    reviews = [check_segment(spec, guides, bones, bounds) for spec in SEGMENT_SPECS]
    mirror = mirror_review(reviews, height)
    semantic = semantic_skin_review(snapshot=snapshot, body_profile=body_profile, plan=plan)

    fail_count = sum(1 for review in reviews if review["status"] == "fail")
    warn_count = sum(1 for review in reviews if review["status"] == "warn")
    mirror_fail_count = sum(1 for item in mirror if not item["ready"])
    detail_score = max(0, min(100, 100 - fail_count * 6 - warn_count * 2 - mirror_fail_count * 3))

    return {
        "detailMode": "tutorial_order_per_bone_review",
        "decisionPolicy": "visual_semantic_gate_only",
        "scorePolicy": "scores_disabled_for_decision_diagnostic_only",
        "detailScore": detail_score,
        "detailReady": False,
        "legacyDetailReady": detail_score >= 90 and fail_count == 0 and mirror_fail_count == 0,
        "productionReady": False,
        "failCount": fail_count,
        "warningCount": warn_count,
        "mirrorFailCount": mirror_fail_count,
        "semanticSkinReview": semantic,
        "semanticSkinReady": semantic["readyForSkin"],
        "skeletonPlan": plan,
        "reviewOrder": [
            "01 pelvis and body center",
            "02 legs, knees, ankles, feet and toe pivots",
            "03 torso side profile",
            "04 clavicle, shoulders, elbows, wrists and hand masses",
            "05 finger chains only when visible finger landmarks exist",
            "06 short neck and large head",
        ],
        "boneReviews": reviews,
        "mirrorReviews": mirror,
        "semanticWarning": "Mechanical per-bone checks can pass while Skin handoff risks remain. Resolve semantic skin blockers before adding Skin or weights.",
    }


def write_markdown(qc: dict[str, Any], snapshot_path: Path, md_path: Path) -> None:
    plan = qc["skeletonPlan"]
    lines = [
        f"# Rig Detail Review: {snapshot_path.stem.replace('_visual_snapshot', '')}",
        "",
        f"- Snapshot: `{snapshot_path}`",
        f"- Detail mode: `{qc['detailMode']}`",
        f"- Decision policy: `{qc['decisionPolicy']}`",
        f"- Score policy: `{qc['scorePolicy']}`",
        "- Decision use: `diagnostic_only`; use Semantic Skin Review and human visual signoff for Skin handoff.",
        f"- Production ready: `{qc['productionReady']}`",
        f"- Diagnostic issue counts: fails `{qc['failCount']}`, warnings `{qc['warningCount']}`, mirror fails `{qc['mirrorFailCount']}`",
        "",
        "## Skeleton Plan",
        "",
        f"- Body type: `{plan['bodyType']}`",
        f"- Character class: `{plan['characterClass']}`",
        f"- Expected template bones: `{plan['templateBoneCountExpected']}`",
        f"- Biped structure: `{json.dumps(plan['bipedStructure'], ensure_ascii=False)}`",
        "",
        "## Review Order",
        "",
    ]
    for item in qc["reviewOrder"]:
        lines.append(f"- {item}")
    lines += ["", "## Per-Bone Review", ""]
    lines.append("| Phase | Segment | Role | Status | Len/H | Width | Height | Issues |")
    lines.append("| --- | --- | --- | --- | ---: | ---: | ---: | --- |")
    for review in qc["boneReviews"]:
        issues = "; ".join(review.get("issues", []) + review.get("warnings", [])) or "OK"
        lines.append(
            f"| {review['phase']} | `{review['segment']}` | `{review['role']}` | `{review['status']}` | "
            f"{review.get('lengthHeightRatio', '')} | {review.get('boneWidth', '')} | {review.get('boneHeight', '')} | {issues} |"
        )
    lines += ["", "## Mirror Review", ""]
    if qc["mirrorReviews"]:
        for item in qc["mirrorReviews"]:
            lines.append(
                f"- `{item['left']}` / `{item['right']}`: diff `{item['lengthDiff']}`, ready `{item['ready']}`"
            )
    else:
        lines.append("- None")
    lines += ["", "## Deferred Detail", ""]
    for item in plan["extraBonesDeferred"]:
        lines.append(f"- {item}")

    semantic = qc.get("semanticSkinReview", {})
    lines += [
        "",
        "## Semantic Skin Review",
        "",
        f"- Ready for Skin: `{semantic.get('readyForSkin')}`",
        f"- Skin blockers: `{semantic.get('skinBlockerCount', 0)}`",
        f"- Risk count: `{semantic.get('riskCount', 0)}`",
        "",
    ]
    risks = semantic.get("risks", [])
    if risks:
        for risk in risks:
            lines.append(
                f"- `{risk['code']}` ({risk['severity']}, {risk['owner']}): {risk['message']} Suggested action: {risk['suggestedAction']}"
            )
    else:
        lines.append("- None")
    policies = semantic.get("deformerPolicies", [])
    if policies:
        lines += ["", "## Deformer Policies", ""]
        for policy in policies:
            lines.append(f"- `{policy['target']}`: `{policy['policy']}` (`{policy['code']}`)")
    lines += ["", "## Semantic Gate", "", f"- {qc['semanticWarning']}"]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Review Stage01 skeleton in tutorial order, bone by bone.")
    parser.add_argument("snapshot_json")
    parser.add_argument("--body-profile-json", default="")
    parser.add_argument("--asset-name", default="")
    parser.add_argument("--out-dir", default="")
    args = parser.parse_args()

    snapshot_path = Path(args.snapshot_json)
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    body_profile = None
    if args.body_profile_json:
        body_path = Path(args.body_profile_json)
        if body_path.exists():
            body_profile = json.loads(body_path.read_text(encoding="utf-8"))

    asset_name = args.asset_name or snapshot.get("assetName") or snapshot_path.stem.replace("_visual_snapshot", "")
    out_dir = Path(args.out_dir) if args.out_dir else snapshot_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    qc = analyze(snapshot, body_profile)
    json_path = out_dir / f"{asset_name}_rig_detail_review.json"
    md_path = out_dir / f"{asset_name}_rig_detail_review.md"
    json_path.write_text(json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(qc, snapshot_path, md_path)
    print(
        json.dumps(
            {
                "ok": True,
                "assetName": asset_name,
                "json": str(json_path),
                "markdown": str(md_path),
                "decisionPolicy": qc["decisionPolicy"],
                "scorePolicy": qc["scorePolicy"],
                "legacyRatingFields": "hidden_diagnostic_only",
                "semanticSkinReady": qc["semanticSkinReady"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
