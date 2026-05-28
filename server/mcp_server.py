from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from max_bridge_client import send_bridge_command


mcp = FastMCP(name="3ds Max AI Rig Assistant")
TOOL_ROOT = Path(__file__).resolve().parents[1]
BATCH_QC_SCRIPT = TOOL_ROOT / "server" / "batch_qc_fbx.ps1"
BATCH_STAGE01_SCRIPT = TOOL_ROOT / "server" / "batch_stage01_fbx.ps1"
BATCH_STAGE02_SCRIPT = TOOL_ROOT / "server" / "batch_stage02_skin.ps1"


def _call(command: str) -> dict[str, Any]:
    """Call the 3ds Max bridge and return a structured MCP result."""

    result = send_bridge_command(command)
    if not result.get("ok", False):
        raise RuntimeError(result.get("message", "3ds Max command failed."))
    return result


def _parse_batch_json(stdout: str) -> dict[str, Any]:
    """Extract the final JSON object from noisy 3dsmaxbatch output."""

    text = (stdout or "").replace("\x00", "")
    decoder = json.JSONDecoder()
    for index in [i for i, char in enumerate(text) if char == "{"][::-1]:
        try:
            parsed, _ = decoder.raw_decode(text[index:].strip())
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


@mcp.tool()
def ping_3dsmax() -> dict[str, Any]:
    """Check whether the 3ds Max MCP bridge is running."""

    return _call("ping")


@mcp.tool()
def stage01_load_tool() -> dict[str, Any]:
    """Load the Stage01 Biped Guide tool inside 3ds Max."""

    return _call("stage01_load_tool")


@mcp.tool()
def stage01_create_guides() -> dict[str, Any]:
    """Create or update Stage01 guide points from the current 3ds Max selection."""

    return _call("stage01_create_guides")


@mcp.tool()
def stage01_mirror_guides() -> dict[str, Any]:
    """Mirror left Stage01 guide points to the right side across X=0."""

    return _call("stage01_mirror_guides")


@mcp.tool()
def stage01_create_biped() -> dict[str, Any]:
    """Create a Biped from current Stage01 guide points."""

    return _call("stage01_create_biped")


@mcp.tool()
def stage01_fit_biped() -> dict[str, Any]:
    """Fit an existing Biped to current Stage01 guide points."""

    return _call("stage01_fit_biped")


@mcp.tool()
def stage01_generate_report() -> dict[str, Any]:
    """Generate the Stage01 Markdown validation report."""

    return _call("stage01_generate_report")


@mcp.tool()
def stage01_generate_fit_qc() -> dict[str, Any]:
    """Generate Stage01 fit-quality JSON and Markdown reports for the current scene."""

    return _call("stage01_generate_fit_qc")


@mcp.tool()
def stage01_save_file() -> dict[str, Any]:
    """Save the current scene as a Stage01 rig work file."""

    return _call("stage01_save_file")


@mcp.tool()
def stage01_auto_pipeline() -> dict[str, Any]:
    """Run the full rough Stage01 pipeline: guides, mirror, Biped creation, report."""

    return _call("stage01_auto_pipeline")


@mcp.tool()
def asset_qc_current_scene() -> dict[str, Any]:
    """Generate an asset QC JSON and Markdown report for the current 3ds Max scene."""

    return _call("asset_qc_current_scene")


@mcp.tool()
def stage02_load_tool() -> dict[str, Any]:
    """Load the independent Stage02 Skin setup tool inside 3ds Max."""

    return _call("stage02_load_tool")


@mcp.tool()
def stage02_skin_current_scene() -> dict[str, Any]:
    """Run Stage02 initial Skin setup on the current 3ds Max scene."""

    return _call("stage02_skin_current_scene")


@mcp.tool()
def asset_qc_fbx_file(fbx_path: str, asset_name: str = "") -> dict[str, Any]:
    """Run offline asset QC for a local FBX file through 3dsmaxbatch.exe."""

    source = Path(fbx_path)
    if not source.exists():
        raise FileNotFoundError(f"FBX file not found: {fbx_path}")

    safe_asset_name = asset_name or source.stem
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(BATCH_QC_SCRIPT),
        "-SourceFbx",
        str(source),
        "-AssetName",
        safe_asset_name,
    ]
    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout).strip())

    output_name = "".join("_" if ch in '\\/:*?"<>|' else ch for ch in safe_asset_name)
    out_dir = Path(os.environ.get("AIRA_OUT_DIR", str(TOOL_ROOT / "out")))
    batch_result = _parse_batch_json(completed.stdout)
    if batch_result:
        batch_result["batchReturnCode"] = completed.returncode
        return batch_result

    return {
        "ok": True,
        "sourceFbx": str(source),
        "assetName": output_name,
        "json": str(out_dir / f"{output_name}_asset_qc.json"),
        "markdown": str(out_dir / f"{output_name}_asset_qc.md"),
        "scene": str(out_dir / f"{output_name}_raw_asset_qc_scene.max"),
        "batchReturnCode": completed.returncode,
    }


@mcp.tool()
def stage01_rig_fbx_file(
    fbx_path: str,
    asset_name: str = "",
    guide_algorithm: str = "tutorial_centerline_qbird",
    visual_signoff_json: str = "",
    max_fit_iterations: int = 12,
) -> dict[str, Any]:
    """Run offline Stage01 guide, Biped creation, local visual evidence, and Skin-prep gate for a local FBX file."""

    source = Path(fbx_path)
    if not source.exists():
        raise FileNotFoundError(f"FBX file not found: {fbx_path}")

    allowed_algorithms = {"tutorial_centerline_qbird"}
    if guide_algorithm not in allowed_algorithms:
        raise ValueError(
            "Legacy guide algorithms and score-ranked recommendations are disabled. "
            "Use tutorial_centerline_qbird only as a visual candidate generator, then rely on Semantic Skin Review and MDC visual signoff."
        )

    safe_asset_name = asset_name or source.stem
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(BATCH_STAGE01_SCRIPT),
        "-SourceFbx",
        str(source),
        "-AssetName",
        safe_asset_name,
        "-GuideAlgorithm",
        guide_algorithm,
        "-MaxFitIterations",
        str(max_fit_iterations),
    ]
    if visual_signoff_json:
        signoff = Path(visual_signoff_json)
        if not signoff.exists():
            raise FileNotFoundError(f"Visual signoff JSON not found: {visual_signoff_json}")
        cmd.extend(["-VisualSignoffJson", str(signoff)])

    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout).strip())

    output_name = "".join("_" if ch in '\\/:*?"<>|' else ch for ch in safe_asset_name)
    out_dir = Path(os.environ.get("AIRA_OUT_DIR", str(TOOL_ROOT / "out")))
    batch_result = _parse_batch_json(completed.stdout)
    if batch_result:
        batch_result["batchReturnCode"] = completed.returncode
        return batch_result

    return {
        "ok": True,
        "sourceFbx": str(source),
        "assetName": output_name,
        "guideAlgorithm": guide_algorithm,
        "maxFitIterations": max_fit_iterations,
        "scene": str(out_dir / f"{output_name}_stage01_rig_scene.max"),
        "summary": str(out_dir / f"{output_name}_stage01_batch_summary.md"),
        "bodyProfileJson": str(out_dir / f"{output_name}_body_profile.json"),
        "bodyProfileMarkdown": str(out_dir / f"{output_name}_body_profile.md"),
        "fitQcJson": str(out_dir / f"{output_name}_stage01_fit_qc.json"),
        "fitQcMarkdown": str(out_dir / f"{output_name}_stage01_fit_qc.md"),
        "rigDetailReviewJson": str(out_dir / f"{output_name}_rig_detail_review.json"),
        "rigDetailReviewMarkdown": str(out_dir / f"{output_name}_rig_detail_review.md"),
        "stage01SkinPrepGateJson": str(out_dir / f"{output_name}_stage01_skin_prep_gate.json"),
        "stage01SkinPrepGateMarkdown": str(out_dir / f"{output_name}_stage01_skin_prep_gate.md"),
        "visualReviewManifest": str(out_dir / "runs" / output_name / "visual_review" / f"{output_name}_visual_evidence_manifest.json"),
        "visualReviewInput": str(out_dir / "runs" / output_name / "visual_review" / "review_input.md"),
        "visualReviewSchema": str(out_dir / "runs" / output_name / "visual_review" / "review_schema.json"),
        "visualSignoffJson": visual_signoff_json,
        "visualReviewStatus": "awaiting_local_signoff" if not visual_signoff_json else "local_signoff_used",
        "visualReviewMessage": "Provide visual_signoff_json after MDC local-agent image review.",
        "mdcVisualCorrectionPlanJson": "",
        "mdcVisualCorrectionPlanMarkdown": "",
        "wireBoneScreenshotDir": str(out_dir / "runs" / output_name / "wire_bone_screenshots"),
        "rigAssetQcJson": str(out_dir / f"{output_name}_stage01_rig_asset_qc.json"),
        "rigAssetQcMarkdown": str(out_dir / f"{output_name}_stage01_rig_asset_qc.md"),
        "batchReturnCode": completed.returncode,
    }


@mcp.tool()
def stage02_skin_max_file(
    source_max: str,
    asset_name: str = "",
    stage01_skin_prep_gate_json: str = "",
    allow_blocked_stage01: bool = False,
    bone_affect_limit: int = 3,
    reference_fbx: str = "",
) -> dict[str, Any]:
    """Run independent Stage02 Skin setup on an existing Stage01 MAX scene."""

    source = Path(source_max)
    if not source.exists():
        raise FileNotFoundError(f"Source MAX scene not found: {source_max}")
    if not 1 <= bone_affect_limit <= 4:
        raise ValueError("bone_affect_limit must be between 1 and 4.")
    reference = Path(reference_fbx) if reference_fbx else None
    if reference is not None and not reference.exists():
        raise FileNotFoundError(f"Reference FBX not found: {reference_fbx}")

    safe_asset_name = asset_name or source.stem.replace("_stage01_rig_scene", "")
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(BATCH_STAGE02_SCRIPT),
        "-SourceMax",
        str(source),
        "-AssetName",
        safe_asset_name,
        "-BoneAffectLimit",
        str(bone_affect_limit),
    ]
    if stage01_skin_prep_gate_json:
        gate = Path(stage01_skin_prep_gate_json)
        if not gate.exists():
            raise FileNotFoundError(f"Stage01 Skin Prep Gate JSON not found: {stage01_skin_prep_gate_json}")
        cmd.extend(["-Stage01SkinPrepGateJson", str(gate)])
    if allow_blocked_stage01:
        cmd.append("-AllowBlockedStage01")
    if reference is not None:
        cmd.extend(["-ReferenceFbx", str(reference)])

    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout).strip())

    batch_result = _parse_batch_json(completed.stdout)
    if batch_result:
        batch_result["batchReturnCode"] = completed.returncode
        return batch_result

    output_name = "".join("_" if ch in '\\/:*?"<>|' else ch for ch in safe_asset_name)
    out_dir = Path(os.environ.get("AIRA_OUT_DIR", str(TOOL_ROOT / "out"))) / "stage02_runs" / output_name
    return {
        "ok": True,
        "sourceMax": str(source),
        "assetName": output_name,
        "runRoot": str(out_dir),
        "boneAffectLimit": bone_affect_limit,
        "referenceFbx": str(reference) if reference is not None else "",
        "batchReturnCode": completed.returncode,
    }


if __name__ == "__main__":
    mcp.run()
