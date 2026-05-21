from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from max_bridge_client import send_bridge_command


mcp = FastMCP(name="3ds Max AI Rig Assistant")
TOOL_ROOT = Path(__file__).resolve().parents[1]
BATCH_QC_SCRIPT = TOOL_ROOT / "server" / "batch_qc_fbx.ps1"
BATCH_STAGE01_SCRIPT = TOOL_ROOT / "server" / "batch_stage01_fbx.ps1"


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
    out_dir = TOOL_ROOT / "out"
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
) -> dict[str, Any]:
    """Run offline Stage01 guide, Biped creation, and fit QC for a local FBX file."""

    source = Path(fbx_path)
    if not source.exists():
        raise FileNotFoundError(f"FBX file not found: {fbx_path}")

    allowed_algorithms = {"tutorial_centerline_qbird"}
    if guide_algorithm not in allowed_algorithms:
        raise ValueError(
            "Legacy guide algorithms and score-ranked recommendations are disabled. "
            "Use tutorial_centerline_qbird only as a visual candidate generator, then rely on Semantic Skin Review and human visual signoff."
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
    out_dir = TOOL_ROOT / "out"
    batch_result = _parse_batch_json(completed.stdout)
    if batch_result:
        batch_result["batchReturnCode"] = completed.returncode
        return batch_result

    return {
        "ok": True,
        "sourceFbx": str(source),
        "assetName": output_name,
        "guideAlgorithm": guide_algorithm,
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
        "wireBoneScreenshotDir": str(out_dir / "runs" / output_name / "wire_bone_screenshots"),
        "rigAssetQcJson": str(out_dir / f"{output_name}_stage01_rig_asset_qc.json"),
        "rigAssetQcMarkdown": str(out_dir / f"{output_name}_stage01_rig_asset_qc.md"),
        "batchReturnCode": completed.returncode,
    }


if __name__ == "__main__":
    mcp.run()
