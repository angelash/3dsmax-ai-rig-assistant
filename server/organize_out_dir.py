from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


KNOWN_STAGE01_SUFFIXES = [
    "_stage01_skin_prep_gate.json",
    "_stage01_skin_prep_gate.md",
    "_template_skeleton_fit_qc.json",
    "_template_skeleton_fit_qc.md",
    "_stage01_rig_asset_qc.json",
    "_stage01_rig_asset_qc.md",
    "_rig_detail_review.json",
    "_rig_detail_review.md",
    "_stage01_3dsmaxbatch.log",
    "_stage01_batch_summary.md",
    "_stage01_listener.log",
    "_stage01_fit_qc.json",
    "_stage01_fit_qc.md",
    "_stage01_rig_scene.max",
    "_visual_snapshot.json",
    "_visual_qc.json",
    "_visual_qc.md",
    "_body_profile.json",
    "_body_profile.md",
]

ALGORITHM_IDS = [
    "tutorial_centerline_qbird",
    "tutorial_visual_qbird",
    "visual_semantic_qbird",
    "semantic_qbird",
    "qbird_profile",
    "mesh_profile",
    "bbox_humanoid",
]

RUN_LAYOUT = {
    "scene": "3ds Max 场景和工作 FBX。这里放真正要打开或继续绑定的文件。",
    "screenshots": "视觉 QC 生成的前视、侧视、顶视 PNG。",
    "textured_screenshots": "3ds Max 渲染/视口生成的带贴图前视、侧视、顶视 PNG，用于检查材质、纹样和轮廓语义。",
    "wire_bone_screenshots": "3ds Max 技术视图截图，使用线框材质叠加骨骼/guide，用于检查侧面重心、腰线、头部和骨骼粗细。",
    "reports": "给人阅读的 Markdown 报告。",
    "data": "给脚本复查或后续流程使用的 JSON 数据。",
    "logs": "3ds Max batch 和 listener 原始日志。",
    "visual_review": "视觉语义审查证据包，包含全局图、局部裁剪、贴图语义叠加、MR 式切片、审查 schema 和审查输入。",
    "views": "按视角组织的引用式索引，只指向文件，不复制文件。",
}

LEGACY_GENERATED_INDEX_FILES = {
    "screenshot_output_pairs.json",
    "screenshot_output_pairs.md",
}

STAGING_SCREENSHOT_DIRS = {
    "visual_screenshots",
    "textured_screenshots",
    "wire_bone_screenshots",
}

RUN_DIR_TIMESTAMP_RE = re.compile(r"^(?P<asset>.+)__(?P<timestamp>\d{8}_\d{6})(?:__r(?P<revision>\d+))?$")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
    except json.JSONDecodeError:
        return {}


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8-sig", errors="replace")


def safe_child(root: Path, *parts: str) -> Path:
    root_resolved = root.resolve()
    path = root_resolved.joinpath(*parts).resolve()
    if path != root_resolved and root_resolved not in path.parents:
        raise ValueError(f"Refusing to write outside output root: {path}")
    return path


def unique_target(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}__dup{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def payload_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [p for p in root.rglob("*") if p.is_file() and p.name != "README.md"]


def has_payload(root: Path) -> bool:
    return bool(payload_files(root))


def move_file(src: Path, dst: Path, dry_run: bool, moves: list[dict[str, str]]) -> Path:
    if src.resolve() == dst.resolve():
        return src
    target = unique_target(dst)
    moves.append({"source": str(src), "target": str(target), "kind": "file"})
    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(target))
    return target


def move_dir_contents(
    src: Path,
    dst: Path,
    dry_run: bool,
    moves: list[dict[str, str]],
    skip_names: set[str] | None = None,
) -> None:
    if not src.exists():
        return
    skip_names = skip_names or set()
    if not dry_run:
        dst.mkdir(parents=True, exist_ok=True)
    for item in sorted(src.iterdir(), key=lambda p: p.name):
        if item.name in skip_names:
            continue
        target = unique_target(dst / item.name)
        moves.append({"source": str(item), "target": str(target), "kind": "directory" if item.is_dir() else "file"})
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item), str(target))


def stage01_asset_name(filename: str) -> str | None:
    for suffix in KNOWN_STAGE01_SUFFIXES:
        if filename.endswith(suffix):
            return filename[: -len(suffix)]
    if filename.startswith("luxun_model") and filename.endswith(".fbx"):
        return filename[:-4]
    return None


def texture_sidecar_asset_name(dirname: str) -> str | None:
    if dirname.startswith("luxun_model") and dirname.endswith(".fbm"):
        return dirname[:-4]
    return None


def split_run_dir_name(run_name: str) -> tuple[str, str]:
    match = RUN_DIR_TIMESTAMP_RE.match(run_name)
    if match:
        return match.group("asset"), match.group("timestamp")
    return run_name, ""


def format_run_timestamp(dt: datetime) -> str:
    return dt.strftime("%Y%m%d_%H%M%S")


def parse_report_datetime(value: str) -> datetime | None:
    value = value.strip()
    for fmt in ["%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M"]:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def timestamp_from_text(text: str) -> str:
    for label in ["Started", "Generated", "Finished"]:
        match = re.search(rf"-\s*{label}:\s*`?([^`\r\n]+)`?", text)
        if not match:
            continue
        parsed = parse_report_datetime(match.group(1))
        if parsed:
            return format_run_timestamp(parsed)
    return ""


def timestamp_from_paths(paths: list[Path]) -> str:
    for path in sorted(paths, key=lambda p: p.name):
        if path.name.endswith("_stage01_batch_summary.md") and path.exists():
            timestamp = timestamp_from_text(read_text(path))
            if timestamp:
                return timestamp
    existing = [path for path in paths if path.exists()]
    if not existing:
        return format_run_timestamp(datetime.now())
    newest_mtime = max(path.stat().st_mtime for path in existing)
    return format_run_timestamp(datetime.fromtimestamp(newest_mtime))


def timestamp_from_run_dir(run_dir: Path) -> str:
    _, timestamp = split_run_dir_name(run_dir.name)
    if timestamp:
        return timestamp
    artifacts = [
        p
        for p in run_dir.rglob("*")
        if p.is_file()
        and p.name != "README.md"
        and p.name not in LEGACY_GENERATED_INDEX_FILES
        and "__dup" not in p.stem
    ]
    return timestamp_from_paths(artifacts)


def unique_run_dir_name(runs_root: Path, asset_name: str, timestamp: str) -> str:
    base = f"{asset_name}__{timestamp}"
    candidate = base
    counter = 2
    while (runs_root / candidate).exists():
        candidate = f"{base}__r{counter}"
        counter += 1
    return candidate


def preferred_run_dir_name(asset_name: str, timestamp: str) -> str:
    return f"{asset_name}__{timestamp}"


def build_pending_run_dirs(out_dir: Path, screenshot_root: Path) -> dict[str, str]:
    pending: dict[str, list[Path]] = {}
    for file_path in out_dir.iterdir():
        if not file_path.is_file():
            continue
        asset_name = stage01_asset_name(file_path.name)
        if asset_name:
            pending.setdefault(asset_name, []).append(file_path)

    for image_root in [screenshot_root, out_dir / "textured_screenshots", out_dir / "wire_bone_screenshots"]:
        if image_root.exists():
            for screenshot_dir in sorted([p for p in image_root.iterdir() if p.is_dir()], key=lambda p: p.name):
                files = payload_files(screenshot_dir)
                if files:
                    pending.setdefault(screenshot_dir.name, []).extend(files)

    for dir_path in out_dir.iterdir():
        if not dir_path.is_dir():
            continue
        asset_name = texture_sidecar_asset_name(dir_path.name)
        if asset_name:
            files = [p for p in dir_path.rglob("*") if p.is_file()]
            pending.setdefault(asset_name, []).extend(files)

    stage_report = out_dir / "AIRA_stage01_biped_report.md"
    if stage_report.exists():
        if "luxun_model_tutorial_centerline_qbird" in pending:
            pending["luxun_model_tutorial_centerline_qbird"].append(stage_report)
        elif len(pending) == 1:
            only_asset = next(iter(pending))
            pending[only_asset].append(stage_report)

    runs_root = out_dir / "runs"
    run_dirs: dict[str, str] = {}
    for asset_name, paths in pending.items():
        timestamp = timestamp_from_paths(paths)
        run_dirs[asset_name] = unique_run_dir_name(runs_root, asset_name, timestamp)
    return run_dirs


def classify_root_file(path: Path, run_names: set[str], current_run_dirs: dict[str, str] | None = None) -> tuple[str, str]:
    current_run_dirs = current_run_dirs or {}
    name = path.name

    if name.startswith("luxun_model_algorithm_benchmark_history."):
        return "benchmarks/history", ""
    if name.startswith("luxun_model_algorithm_") or name in {
        "luxun_model_algorithm_benchmark.json",
        "luxun_model_algorithm_benchmark.md",
    }:
        return "benchmarks/latest", ""
    if name.startswith("luxun_model_asset_qc") or name == "luxun_model_raw_asset_qc_scene.max":
        return "asset_qc/luxun_model", ""
    if name.startswith("luxun_asset_qc") or name == "luxun_asset_qc_scene.max":
        return "asset_qc/luxun_legacy", ""
    if name.startswith("luxun_model_external"):
        return "external/luxun_model_external", ""
    if name.startswith("luxun_model_tutorial_") and name.endswith("_iteration_report.md"):
        return "reports/iteration", ""
    if name == "AIRA_stage01_biped_report.md":
        preferred = "luxun_model_tutorial_centerline_qbird"
        if preferred in current_run_dirs:
            return f"runs/{current_run_dirs[preferred]}", ""
        if len(current_run_dirs) == 1:
            return f"runs/{next(iter(current_run_dirs.values()))}", ""
        preferred_runs = [name for name in run_names if split_run_dir_name(name)[0] == preferred]
        if preferred_runs:
            return f"runs/{sorted(preferred_runs)[-1]}", ""
        if run_names:
            return f"runs/{sorted(run_names)[-1]}", ""
        return "legacy", ""

    asset_name = stage01_asset_name(name)
    if asset_name:
        return f"runs/{current_run_dirs.get(asset_name, asset_name)}", ""
    if name.startswith("luxun_"):
        return "legacy/luxun_stage01", ""

    return "misc", ""


def infer_algorithm(asset_name: str, summary_text: str) -> str:
    match = re.search(r"Guide algorithm:\s*`?([A-Za-z0-9_]+)`?", summary_text)
    if match:
        return match.group(1)
    for algorithm in ALGORITHM_IDS:
        if asset_name.endswith(algorithm) or f"_{algorithm}_" in asset_name:
            return algorithm
    if asset_name in {"luxun_model", "luxun_model_default"}:
        return "default at generation time"
    return "unknown"


def run_search_dirs(run_dir: Path) -> list[Path]:
    dirs = [run_dir]
    for name in ["scene", "reports", "data", "logs", "screenshots", "textured_screenshots", "wire_bone_screenshots", "visual_review"]:
        candidate = run_dir / name
        if candidate.exists():
            dirs.append(candidate)
    return dirs


def find_texture_sidecar(run_dir: Path) -> Path | None:
    scene_dir = run_dir / "scene"
    if not scene_dir.exists():
        return None
    matches = sorted([p for p in scene_dir.iterdir() if p.is_dir() and p.name.endswith(".fbm")], key=lambda p: p.name)
    return matches[0] if matches else None


def find_first(run_dir: Path, suffix: str) -> Path | None:
    for directory in run_search_dirs(run_dir):
        matches = sorted(directory.glob(f"*{suffix}"))
        if matches:
            return matches[0]
    return None


def find_named(run_dir: Path, name: str) -> Path | None:
    for directory in run_search_dirs(run_dir):
        candidate = directory / name
        if candidate.exists():
            return candidate
    return None


def relative_path(path: Path | None, base: Path) -> str:
    if path is None or not path.exists():
        return ""
    return path.relative_to(base).as_posix()


def screenshot_view(path: Path) -> str:
    stem = path.stem.lower()
    for view in ["front", "side", "top"]:
        if stem.endswith(f"_{view}"):
            return view
    return "unknown"


def run_artifacts(run_dir: Path) -> dict[str, Path | None]:
    return {
        "workingFbx": find_first(run_dir, ".fbx"),
        "sceneMax": find_first(run_dir, "_stage01_rig_scene.max"),
        "textureSidecar": find_texture_sidecar(run_dir),
        "stage01Report": find_named(run_dir, "AIRA_stage01_biped_report.md"),
        "stage01BatchLog": find_first(run_dir, "_stage01_3dsmaxbatch.log"),
        "stage01ListenerLog": find_first(run_dir, "_stage01_listener.log"),
        "batchSummary": find_first(run_dir, "_stage01_batch_summary.md"),
        "bodyProfileJson": find_first(run_dir, "_body_profile.json"),
        "bodyProfileMarkdown": find_first(run_dir, "_body_profile.md"),
        "bipedFitQcJson": find_first(run_dir, "_stage01_fit_qc.json"),
        "bipedFitQcMarkdown": find_first(run_dir, "_stage01_fit_qc.md"),
        "templateFitQcJson": find_first(run_dir, "_template_skeleton_fit_qc.json"),
        "templateFitQcMarkdown": find_first(run_dir, "_template_skeleton_fit_qc.md"),
        "visualSnapshotJson": find_first(run_dir, "_visual_snapshot.json"),
        "visualQcJson": find_first(run_dir, "_visual_qc.json"),
        "visualQcMarkdown": find_first(run_dir, "_visual_qc.md"),
        "wireBoneScreenshotDir": run_dir / "wire_bone_screenshots" if (run_dir / "wire_bone_screenshots").exists() else None,
        "visualReviewManifest": find_first(run_dir, "_visual_evidence_manifest.json"),
        "visualReviewInput": find_named(run_dir, "review_input.md"),
        "visualReviewSchema": find_named(run_dir, "review_schema.json"),
        "visualReviewTemplate": find_named(run_dir, "semantic_visual_review_template.json"),
        "visualMethodAssessment": find_named(run_dir, "visual_method_assessment.md"),
        "rigDetailReviewJson": find_first(run_dir, "_rig_detail_review.json"),
        "rigDetailReviewMarkdown": find_first(run_dir, "_rig_detail_review.md"),
        "skinPrepGateJson": find_first(run_dir, "_stage01_skin_prep_gate.json"),
        "skinPrepGateMarkdown": find_first(run_dir, "_stage01_skin_prep_gate.md"),
        "rigAssetQcJson": find_first(run_dir, "_stage01_rig_asset_qc.json"),
        "rigAssetQcMarkdown": find_first(run_dir, "_stage01_rig_asset_qc.md"),
    }


def run_signals(artifacts: dict[str, Path | None]) -> dict[str, Any]:
    body_profile = load_json(artifacts["bodyProfileJson"]) if artifacts["bodyProfileJson"] else {}
    fit_qc = load_json(artifacts["bipedFitQcJson"]) if artifacts["bipedFitQcJson"] else {}
    visual_qc = load_json(artifacts["visualQcJson"]) if artifacts["visualQcJson"] else {}
    detail_qc = load_json(artifacts["rigDetailReviewJson"]) if artifacts["rigDetailReviewJson"] else {}
    skin_gate = load_json(artifacts["skinPrepGateJson"]) if artifacts["skinPrepGateJson"] else {}
    asset_qc = load_json(artifacts["rigAssetQcJson"]) if artifacts["rigAssetQcJson"] else {}
    return {
        "bodyType": body_profile.get("bodyType", "unknown"),
        "decisionPolicy": skin_gate.get("decisionPolicy", "visual_semantic_gate_only"),
        "scorePolicy": skin_gate.get("scorePolicy", "scores_disabled_for_decision_diagnostic_only"),
        "stage01CandidateAvailable": skin_gate.get("stage01CandidateAvailable", "n/a"),
        "semanticSkinReady": skin_gate.get("semanticSkinReady", detail_qc.get("semanticSkinReady", "n/a")),
        "semanticSkinBlockers": len(skin_gate.get("semanticSkinBlockers", []))
        if isinstance(skin_gate.get("semanticSkinBlockers"), list)
        else detail_qc.get("semanticSkinReview", {}).get("skinBlockerCount", "n/a"),
        "visualReviewPackAvailable": bool(artifacts.get("visualReviewManifest") or artifacts.get("visualReviewInput")),
        "textureSidecarAvailable": bool(artifacts.get("textureSidecar")),
        "stage01HandoffReady": skin_gate.get("stage01HandoffReady", "n/a"),
        "skinSetupReady": skin_gate.get("skinSetupReady", "n/a"),
        "productionReady": skin_gate.get("productionReady", fit_qc.get("productionReady", "n/a")),
        "assetQcIssueCount": len(asset_qc.get("issues", [])) if asset_qc else "n/a",
        "diagnosticScoreFieldsHidden": True,
    }


def write_screenshot_pairs(run_dir: Path, asset_name: str) -> list[dict[str, Any]]:
    screenshot_dir = run_dir / "screenshots"
    screenshots = sorted(screenshot_dir.glob("*.png")) if screenshot_dir.exists() else []
    textured_dir = run_dir / "textured_screenshots"
    wire_dir = run_dir / "wire_bone_screenshots"
    views_dir = run_dir / "views"
    clear_directory(views_dir, run_dir)
    views_dir.mkdir(parents=True, exist_ok=True)

    artifacts = run_artifacts(run_dir)
    signals = run_signals(artifacts)
    paired_outputs = {
        name: relative_path(path, run_dir)
        for name, path in artifacts.items()
        if path is not None and path.exists()
    }

    pairs: list[dict[str, Any]] = []
    for screenshot in screenshots:
        view = screenshot_view(screenshot)
        textured = textured_dir / f"{asset_name}_textured_{view}.png"
        wire_bone = wire_dir / f"{asset_name}_wire_bone_{view}.png"
        pairs.append(
            {
                "assetName": asset_name,
                "view": view,
                "screenshot": relative_path(screenshot, run_dir),
                "texturedScreenshot": relative_path(textured, run_dir),
                "wireBoneScreenshot": relative_path(wire_bone, run_dir),
                "pairedOutputs": paired_outputs,
                "signals": signals,
            }
        )

    (views_dir / "index.json").write_text(
        json.dumps({"assetName": asset_name, "pairs": pairs}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        f"# 视角索引：{asset_name}",
        "",
        "这里按截图视角列出对应产物。注意：这里不复制 `.max`、报告或 JSON，只指向本 run 目录里的单份文件。",
        "",
        "| 视角 | 点云截图 | 贴图截图 | 线框+骨骼 | 场景 | Visual QC | Skin Gate |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for pair in pairs:
        outputs = pair["pairedOutputs"]
        lines.append(
            "| `{0}` | `{1}` | `{2}` | `{3}` | `{4}` | `{5}` | `{6}` |".format(
                pair["view"],
                pair["screenshot"],
                pair["texturedScreenshot"],
                pair["wireBoneScreenshot"],
                outputs.get("sceneMax", ""),
                outputs.get("visualQcMarkdown") or outputs.get("visualQcJson", ""),
                outputs.get("skinPrepGateMarkdown") or outputs.get("skinPrepGateJson", ""),
            )
        )
    lines += [
        "",
        "## 共享产物",
        "",
    ]
    for key, value in paired_outputs.items():
        lines.append(f"- `{key}`: `{value}`")
    (views_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (views_dir / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    for pair in pairs:
        outputs = pair["pairedOutputs"]
        view_lines = [
            f"# {asset_name} - {pair['view']} 视角",
            "",
            "这是一张截图的操作索引。实际文件只存放在 `scene/`、`reports/`、`data/`、`logs/`、`screenshots/`、`textured_screenshots/`、`wire_bone_screenshots/` 和 `visual_review/` 中。",
            "",
            "## 截图",
            "",
            f"- `{pair['screenshot']}`",
            f"- `{pair['texturedScreenshot']}`",
            f"- `{pair['wireBoneScreenshot']}`",
            "",
            "## 关键产物",
            "",
            f"- 场景：`{outputs.get('sceneMax', '')}`",
            f"- 工作 FBX：`{outputs.get('workingFbx', '')}`",
            f"- Visual QC：`{outputs.get('visualQcMarkdown') or outputs.get('visualQcJson', '')}`",
            f"- 视觉语义证据包：`{outputs.get('visualReviewInput') or outputs.get('visualReviewManifest', '')}`",
            f"- 逐骨检查：`{outputs.get('rigDetailReviewMarkdown') or outputs.get('rigDetailReviewJson', '')}`",
            f"- Skin 前置门：`{outputs.get('skinPrepGateMarkdown') or outputs.get('skinPrepGateJson', '')}`",
            f"- 资产 QC：`{outputs.get('rigAssetQcMarkdown') or outputs.get('rigAssetQcJson', '')}`",
            "",
            "## 当前信号",
            "",
        ]
        for key, value in signals.items():
            view_lines.append(f"- `{key}`: `{value}`")
        (views_dir / f"{pair['view']}.md").write_text("\n".join(view_lines) + "\n", encoding="utf-8")

    return pairs


def clear_directory(target: Path, allowed_parent: Path) -> None:
    target_resolved = target.resolve()
    parent_resolved = allowed_parent.resolve()
    if target_resolved == parent_resolved or parent_resolved not in target_resolved.parents:
        raise ValueError(f"Refusing to clear directory outside run folder: {target_resolved}")
    if not target.exists():
        return
    for child in target.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def run_bucket_for_file(path: Path) -> str | None:
    name = path.name
    suffix = path.suffix.lower()
    if name == "README.md":
        return None
    if name in LEGACY_GENERATED_INDEX_FILES:
        return "generated_index"
    if suffix in {".max", ".fbx"}:
        return "scene"
    if suffix == ".md":
        return "reports"
    if suffix == ".json":
        return "data"
    if suffix == ".log":
        return "logs"
    return "misc"


def remove_generated_directory(path: Path, allowed_parent: Path, moves: list[dict[str, str]], dry_run: bool) -> None:
    path_resolved = path.resolve()
    parent_resolved = allowed_parent.resolve()
    if not path.exists():
        return
    if path_resolved == parent_resolved or parent_resolved not in path_resolved.parents:
        raise ValueError(f"Refusing to remove directory outside run folder: {path_resolved}")
    moves.append({"source": str(path), "target": "(removed generated duplicate directory)", "kind": "directory"})
    if not dry_run:
        shutil.rmtree(path)


def normalize_run_layout(run_dir: Path, dry_run: bool, moves: list[dict[str, str]]) -> None:
    for directory_name in RUN_LAYOUT:
        target_dir = run_dir / directory_name
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)

    remove_generated_directory(run_dir / "screenshot_bundles", run_dir, moves, dry_run)

    for dir_path in sorted([p for p in run_dir.iterdir() if p.is_dir() and p.name.endswith(".fbm")], key=lambda p: p.name):
        target_dir = run_dir / "scene" / dir_path.name
        move_dir_contents(dir_path, target_dir, dry_run, moves)
        if not dry_run:
            try:
                dir_path.rmdir()
            except OSError:
                pass

    for file_path in sorted([p for p in run_dir.iterdir() if p.is_file()], key=lambda p: p.name):
        bucket = run_bucket_for_file(file_path)
        if bucket is None:
            continue
        if bucket == "generated_index":
            moves.append({"source": str(file_path), "target": "(removed legacy generated index)", "kind": "file"})
            if not dry_run:
                file_path.unlink()
            continue
        target_dir = run_dir / bucket
        move_file(file_path, target_dir / file_path.name, dry_run, moves)


def migrate_legacy_run_dirs(runs_root: Path, dry_run: bool, moves: list[dict[str, str]]) -> None:
    if not runs_root.exists():
        return
    for run_dir in sorted([p for p in runs_root.iterdir() if p.is_dir()], key=lambda p: p.name):
        _, existing_timestamp = split_run_dir_name(run_dir.name)
        if existing_timestamp:
            continue
        asset_name = run_dir.name
        existing_timestamped_siblings = [
            p for p in runs_root.iterdir() if p.is_dir() and split_run_dir_name(p.name)[0] == asset_name and split_run_dir_name(p.name)[1]
        ]
        if existing_timestamped_siblings:
            moves.append({"source": str(run_dir), "target": "(removed duplicate legacy directory; timestamped run already exists)", "kind": "directory"})
            if not dry_run:
                try:
                    shutil.rmtree(str(run_dir))
                except OSError as exc:
                    moves.append(
                        {
                            "source": str(run_dir),
                            "target": "(left in place; duplicate legacy directory is locked)",
                            "kind": "directory",
                            "error": str(exc),
                        }
                    )
            continue
        timestamp = timestamp_from_run_dir(run_dir)
        preferred_name = preferred_run_dir_name(asset_name, timestamp)
        target_name = preferred_name if not (runs_root / preferred_name).exists() else preferred_name
        target_dir = runs_root / target_name
        moves.append({"source": str(run_dir), "target": str(target_dir), "kind": "directory"})
        if not dry_run:
            if target_dir.exists():
                try:
                    shutil.rmtree(str(run_dir))
                except OSError as exc:
                    moves.append(
                        {
                            "source": str(run_dir),
                            "target": "(left in place; duplicate legacy directory is locked)",
                            "kind": "directory",
                            "error": str(exc),
                        }
                    )
                continue
            try:
                run_dir.rename(target_dir)
            except OSError:
                target_dir.mkdir(parents=True, exist_ok=True)
                for child in sorted(run_dir.iterdir(), key=lambda p: p.name):
                    target_child = target_dir / child.name
                    if child.is_dir():
                        move_dir_contents(child, target_child, dry_run, moves)
                        try:
                            child.rmdir()
                        except OSError:
                            pass
                    else:
                        move_file(child, target_child, dry_run, moves)
                try:
                    run_dir.rmdir()
                except OSError as exc:
                    moves.append(
                        {
                            "source": str(run_dir),
                            "target": "(left in place; empty legacy directory is locked)",
                            "kind": "directory",
                            "error": str(exc),
                        }
                    )


def write_run_subdir_readmes(run_dir: Path, asset_name: str) -> None:
    for directory_name, description in RUN_LAYOUT.items():
        directory = run_dir / directory_name
        directory.mkdir(parents=True, exist_ok=True)
        files = sorted([p.name for p in directory.iterdir() if p.is_file() and p.name != "README.md"])
        dirs = sorted([p.name for p in directory.iterdir() if p.is_dir()])
        lines = [
            f"# {asset_name} / {directory_name}",
            "",
            description,
            "",
        ]
        if dirs:
            lines += ["## 目录", ""]
            for dir_name in dirs:
                lines.append(f"- `{dir_name}/`")
            lines.append("")
        lines += ["## 文件", ""]
        if files:
            for file_name in files:
                lines.append(f"- `{file_name}`")
        else:
            lines.append("- 当前没有文件。")
        (directory / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def refresh_visual_qc_paths(run_dir: Path, asset_name: str, artifacts: dict[str, Path | None]) -> None:
    visual_json = artifacts.get("visualQcJson")
    visual_md = artifacts.get("visualQcMarkdown")
    snapshot = artifacts.get("visualSnapshotJson")
    if visual_json is None or visual_md is None or snapshot is None:
        return
    qc = load_json(visual_json)
    if not qc:
        return
    screenshot_dir = run_dir / "screenshots"
    screenshots = {
        view: str(screenshot_dir / f"{asset_name}_{view}.png")
        for view in ["front", "side", "top"]
        if (screenshot_dir / f"{asset_name}_{view}.png").exists()
    }
    qc["snapshot"] = str(snapshot)
    qc["screenshots"] = screenshots
    visual_json.write_text(json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# Visual Silhouette QC: {asset_name}",
        "",
        f"- Snapshot: `{snapshot}`",
        f"- Visual mode: `{qc.get('visualMode')}`",
        f"- Decision policy: `{qc.get('decisionPolicy', 'visual_semantic_gate_only')}`",
        f"- Score policy: `{qc.get('scorePolicy', 'scores_disabled_for_decision_diagnostic_only')}`",
        "- Decision use: `diagnostic_only`; this report must not be used as a Skin-ready score.",
        f"- Production ready: `{qc.get('productionReady')}`",
        f"- Diagnostic issue counts: errors `{qc.get('errorCount')}`, warnings `{qc.get('warningCount')}`, info `{qc.get('infoCount')}`",
        "",
        "## Screenshots",
        "",
    ]
    for view, path in screenshots.items():
        lines.append(f"- {view}: `{path}`")
    lines += ["", "## Observations", ""]
    for observation in qc.get("observations", []):
        lines.append(f"- {observation}")
    lines += ["", "## Hand Centerline Coverage", ""]
    if qc.get("handCoverage"):
        for name, coverage in qc["handCoverage"].items():
            lines.append(
                f"- {name}: diagnostic distance `{coverage['distance']}`, target `{coverage['target']}`"
            )
    else:
        lines.append("- None")
    lines += ["", "## Arm Centerline Coverage", ""]
    if qc.get("armCoverage"):
        for name, coverage in qc["armCoverage"].items():
            lines.append(
                f"- {name}: diagnostic distance `{coverage['distance']}`, target `{coverage['target']}`"
            )
    else:
        lines.append("- None")
    lines += ["", "## Issues", ""]
    if qc.get("issues"):
        for issue in qc["issues"]:
            guide = f" ({issue['guide']})" if issue.get("guide") else ""
            lines.append(f"- [{issue['severity']}] {issue['code']}{guide}: {issue['message']}")
    else:
        lines.append("- None")
    lines += ["", "## Semantic Gate", "", f"- {qc.get('semanticWarning')}"]
    visual_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def refresh_run_report_paths(run_dir: Path, asset_name: str) -> None:
    artifacts = run_artifacts(run_dir)
    refresh_visual_qc_paths(run_dir, asset_name, artifacts)

    rig_detail_md = artifacts.get("rigDetailReviewMarkdown")
    snapshot = artifacts.get("visualSnapshotJson")
    if rig_detail_md and snapshot and rig_detail_md.exists():
        text = read_text(rig_detail_md)
        text = re.sub(r"- Snapshot: `[^`]*`", lambda _: f"- Snapshot: `{snapshot}`", text)
        rig_detail_md.write_text(text, encoding="utf-8")

    skin_json = artifacts.get("skinPrepGateJson")
    skin_md = artifacts.get("skinPrepGateMarkdown")
    if skin_json and skin_md and skin_json.exists():
        qc = load_json(skin_json)
        inputs = {
            "bodyProfileJson": str(artifacts["bodyProfileJson"]) if artifacts.get("bodyProfileJson") else "",
            "bipedFitQcJson": str(artifacts["bipedFitQcJson"]) if artifacts.get("bipedFitQcJson") else "",
            "visualQcJson": str(artifacts["visualQcJson"]) if artifacts.get("visualQcJson") else "",
            "rigDetailReviewJson": str(artifacts["rigDetailReviewJson"]) if artifacts.get("rigDetailReviewJson") else "",
            "rigAssetQcJson": str(artifacts["rigAssetQcJson"]) if artifacts.get("rigAssetQcJson") else "",
        }
        qc["inputs"] = inputs
        skin_json.write_text(json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            from stage01_skin_prep_gate import write_markdown as write_skin_gate_markdown

            write_skin_gate_markdown(qc, inputs, skin_md)
        except Exception:
            text = read_text(skin_md)
            for key, value in inputs.items():
                text = re.sub(rf"- {re.escape(key)}: `[^`]*`", lambda _, k=key, v=value: f"- {k}: `{v}`", text)
            skin_md.write_text(text, encoding="utf-8")


def run_sort_key(run_dir: Path) -> tuple[str, float, str]:
    _, timestamp = split_run_dir_name(run_dir.name)
    mtime = run_dir.stat().st_mtime if run_dir.exists() else 0.0
    return timestamp, mtime, run_dir.name


def organized_run_dirs(runs_root: Path) -> list[Path]:
    if not runs_root.exists():
        return []
    all_dirs = sorted([p for p in runs_root.iterdir() if p.is_dir()], key=lambda p: p.name)
    timestamped_assets = {split_run_dir_name(p.name)[0] for p in all_dirs if split_run_dir_name(p.name)[1]}
    return [p for p in all_dirs if split_run_dir_name(p.name)[1] or split_run_dir_name(p.name)[0] not in timestamped_assets]


def build_asset_run_index(root: Path) -> dict[str, dict[str, Any]]:
    runs_root = root / "runs"
    grouped: dict[str, list[Path]] = {}
    if not runs_root.exists():
        return {}
    for run_dir in organized_run_dirs(runs_root):
        asset_name, timestamp = split_run_dir_name(run_dir.name)
        grouped.setdefault(asset_name, []).append(run_dir)

    index: dict[str, dict[str, Any]] = {}
    for asset_name, run_dirs in grouped.items():
        sorted_runs = sorted(run_dirs, key=run_sort_key)
        latest = sorted_runs[-1]
        _, timestamp = split_run_dir_name(latest.name)
        index[asset_name] = {
            "assetName": asset_name,
            "latestRunName": latest.name,
            "timestamp": timestamp,
            "runDir": str(latest),
            "runDirRelative": latest.relative_to(root).as_posix(),
            "allRunDirs": [p.relative_to(root).as_posix() for p in sorted_runs],
        }
    return index


def write_global_screenshot_pairs(root: Path) -> None:
    runs_root = root / "runs"
    all_pairs: list[dict[str, Any]] = []
    if runs_root.exists():
        for run_dir in organized_run_dirs(runs_root):
            pairs_path = run_dir / "views" / "index.json"
            if pairs_path.exists():
                data = load_json(pairs_path)
                for pair in data.get("pairs", []):
                    global_pair = dict(pair)
                    global_pair["runDir"] = run_dir.relative_to(root).as_posix()
                    global_pair["screenshot"] = f"{global_pair['runDir']}/{pair['screenshot']}"
                    global_pair["pairedOutputs"] = {
                        key: f"{global_pair['runDir']}/{value}" for key, value in pair.get("pairedOutputs", {}).items()
                    }
                    all_pairs.append(global_pair)

    index_dir = root / "_indexes"
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "screenshot_output_pairs.json").write_text(
        json.dumps({"pairCount": len(all_pairs), "pairs": all_pairs}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Screenshot Output Pairs",
        "",
        "Global index pairing each visual QC screenshot with its generated run outputs.",
        "",
        "| Run | Screenshot | View | Scene | Visual QC | Snapshot | Skin Gate |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for pair in all_pairs:
        outputs = pair.get("pairedOutputs", {})
        lines.append(
            "| `{0}` | `{1}` | `{2}` | `{3}` | `{4}` | `{5}` | `{6}` |".format(
                pair.get("runDir", ""),
                pair.get("screenshot", ""),
                pair.get("view", ""),
                outputs.get("sceneMax", ""),
                outputs.get("visualQcMarkdown") or outputs.get("visualQcJson", ""),
                outputs.get("visualSnapshotJson", ""),
                outputs.get("skinPrepGateMarkdown") or outputs.get("skinPrepGateJson", ""),
            )
        )
    (index_dir / "screenshot_output_pairs.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for legacy in [root / "screenshot_output_pairs.json", root / "screenshot_output_pairs.md"]:
        if legacy.exists():
            legacy.unlink()


def write_run_readme(run_dir: Path, asset_name: str) -> None:
    folder_asset_name, folder_timestamp = split_run_dir_name(run_dir.name)
    asset_name = folder_asset_name or asset_name
    artifacts = run_artifacts(run_dir)
    summary_path = artifacts["batchSummary"]
    summary_text = read_text(summary_path) if summary_path else ""
    signals = run_signals(artifacts)

    algorithm = infer_algorithm(asset_name, summary_text)
    fbx_line = ""
    match = re.search(r"- FBX:\s*`([^`]+)`", summary_text)
    if match:
        fbx_line = match.group(1)
    source_for_command = fbx_line or "<source.fbx>"

    write_run_subdir_readmes(run_dir, asset_name)
    pairs = write_screenshot_pairs(run_dir, asset_name)

    screenshot_dir = run_dir / "screenshots"
    screenshots = sorted([p.name for p in screenshot_dir.glob("*.png")]) if screenshot_dir.exists() else []

    lines = [
        f"# {asset_name}",
        "",
        "这个目录是一批 Stage01 输出，按用途分区保存。根目录只保留这个说明文件，实际产物都在子目录里。",
        "",
        "## 生成方式",
        "",
        f"- Run folder: `{run_dir.name}`",
        f"- Asset name: `{asset_name}`",
        f"- Run timestamp: `{folder_timestamp or 'unknown'}`",
        f"- Visual candidate generator: `{algorithm}`",
        f"- Working FBX recorded by batch summary: `{fbx_line or 'unknown'}`",
        "- Equivalent command:",
        "",
        "```powershell",
        "$repo = (Resolve-Path .).Path",
        f'& "$repo\\server\\batch_stage01_fbx.ps1" -SourceFbx "{source_for_command}" -AssetName {asset_name} -GuideAlgorithm tutorial_centerline_qbird',
        "```",
        "",
        "说明：`.fbx` 是给 3ds Max batch 使用的 ASCII-safe 工作副本。部分 JSON 内部路径仍可能保留生成瞬间的旧 `out` 路径，实际整理后的文件以本目录结构为准。",
        "",
        "## 当前信号",
        "",
        f"- Body type: `{signals['bodyType']}`",
        f"- Decision policy: `{signals['decisionPolicy']}`",
        f"- Score policy: `{signals['scorePolicy']}`",
        f"- Stage01 candidate available: `{signals['stage01CandidateAvailable']}`",
        f"- Semantic Skin ready: `{signals['semanticSkinReady']}`",
        f"- Semantic Skin blockers: `{signals['semanticSkinBlockers']}`",
        f"- Visual review pack available: `{signals['visualReviewPackAvailable']}`",
        f"- Texture sidecar available: `{signals['textureSidecarAvailable']}`",
        f"- Stage01 handoff ready: `{signals['stage01HandoffReady']}`",
        f"- Skin setup ready: `{signals['skinSetupReady']}`",
        f"- Production ready: `{signals['productionReady']}`",
        f"- Asset QC issues: `{signals['assetQcIssueCount']}`",
        f"- Diagnostic score fields hidden: `{signals['diagnosticScoreFieldsHidden']}`",
        "",
        "## 目录结构",
        "",
        "- `scene/`：`.max` 场景和工作 `.fbx`。",
        "- `scene/*.fbm/`：跟随工作 FBX/Max 场景一起保存的贴图 sidecar，材质 bitmap 会尽量改成相对路径引用这里。",
        "- `screenshots/`：front / side / top 三张截图。",
        "- `textured_screenshots/`：带贴图渲染/视口截图，用于纹样、颜色和附件语义检查。",
        "- `wire_bone_screenshots/`：3ds Max 线框+骨骼技术视图，用于看侧面重心、腰部原点、头/帽边界和骨骼粗细。",
        "- `reports/`：Markdown 报告，人看这里。",
        "- `data/`：JSON 数据，脚本和复查用这里。",
        "- `logs/`：3ds Max batch/listener 日志。",
        "- `visual_review/`：视觉语义审查证据包、局部裁剪、贴图语义叠加、MR 式切片和结构化审查模板。",
        "- `views/`：按截图视角组织的索引，只引用文件，不复制文件。",
        "",
        "## 截图",
        "",
    ]
    if screenshots:
        for file_name in screenshots:
            lines.append(f"- `screenshots/{file_name}`")
    else:
        lines.append("- None")
    lines += ["", "## 视角索引", ""]
    if pairs:
        lines.append("想按某张截图检查时，打开下面这些索引；它们不会复制产物，只指向本目录里的单份文件：")
        lines.append("")
        for pair in pairs:
            lines.append(f"- `views/{pair['view']}.md`")
    else:
        lines.append("- None")
    (run_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_out_readme(root: Path) -> None:
    asset_run_index = build_asset_run_index(root)
    recommended_info = asset_run_index.get("luxun_model_tutorial_centerline_qbird")
    recommended = root / recommended_info["runDirRelative"] if recommended_info else root / "runs" / "luxun_model_tutorial_centerline_qbird"
    run_count = len(organized_run_dirs(root / "runs"))
    view_count = len([p for p in root.glob("runs/*/views/*.md") if p.name not in {"README.md", "index.md"}])
    lines = [
        "# 3ds Max AI Rig Assistant 输出目录说明",
        "",
        "这个 `out/` 目录已经按“单份产物 + 带时间戳 run 目录 + 引用索引”重新整理。根目录只做导航；真正要看的内容在 `runs/<assetName>__YYYYMMDD_HHMMSS/` 下面。",
        "",
        "## 先看哪里",
        "",
    ]
    if recommended_info and recommended.exists():
        latest_rel = recommended_info["runDirRelative"]
        lines += [
            f"- 当前视觉候选结果：`{latest_rel}/README.md`",
            "- 当前视觉候选三视图索引：",
            f"  - `{latest_rel}/views/front.md`",
            f"  - `{latest_rel}/views/side.md`",
            f"  - `{latest_rel}/views/top.md`",
        ]
    else:
        lines.append("- 当前没有找到 `luxun_model_tutorial_centerline_qbird` 视觉候选目录。")
    lines += [
        "",
        "## 目录组织原则",
        "",
        "### 1. `runs/<assetName>__YYYYMMDD_HHMMSS/` 是一次生成批次",
        "",
        "同一个 `assetName` 每次重新生成都会新建一个带时间戳的 run 目录，不覆盖旧批次。每个 run 根目录不再平铺文件，只保留 `README.md` 和下列子目录：",
        "",
        "- `scene/`：生成后的 3ds Max 场景和 batch 工作 FBX。",
        "- `screenshots/`：front / side / top 截图。",
        "- `textured_screenshots/`：front / side / top 带贴图截图。",
        "- `wire_bone_screenshots/`：front / side / top 线框+骨骼截图。",
        "- `reports/`：`*_visual_qc.md`、`*_rig_detail_review.md`、`*_stage01_skin_prep_gate.md` 等人读报告。",
        "- `data/`：对应 JSON、snapshot 和机器可读 QC 数据。",
        "- `logs/`：batch/listener 原始日志。",
        "- `visual_review/`：全局证据图、头/手/脚/骨盆局部裁剪、贴图语义叠加、MR 式切片、审查 schema 和审查输入。",
        "- `views/`：按截图视角组织的索引，只引用文件，不复制文件。",
        "",
        "### 2. `runs/<assetName>__YYYYMMDD_HHMMSS/views/<view>.md` 是按截图检查的入口",
        "",
        "如果你是要看某一张截图和它对应的产出，直接打开这里。每个 `<view>` 是 `front`、`side` 或 `top`。这些索引只指向 `scene/`、`reports/`、`data/`、`logs/`、`screenshots/`、`textured_screenshots/`、`wire_bone_screenshots/` 中的单份文件，不再复制一整套重复内容。",
        "",
        "也就是说：不要再从根目录翻文件；要操作某张图，就看 `views/<view>.md`，再按里面的路径打开对应文件。",
        "",
        "### 3. `visual_review/` 是视觉语义审查证据包",
        "",
        "这里会放 `full/` 全局证据图、`regions/` 局部裁剪、`semantic_analysis/` 贴图语义叠加、`slices/` MR 式切片、`review_input.md`、`review_schema.json` 和 `semantic_visual_review_template.json`。它用于 MDC 本地代理按固定 blocker 审查，不产生分数。",
        "",
        "### 4. `benchmarks/` 是旧算法评分归档，不是生产入口",
        "",
        "- `benchmarks/latest/`：旧 benchmark、旧推荐算法和旧默认算法检查，生产判断不再使用。",
        "- `algorithm_benchmarks/`：历史 benchmark 快照归档，只适合回溯实验过程。",
        "",
        "### 5. `asset_qc/` 是原始资产质检",
        "",
        "这里放的是还没有进入 Stage01 自动骨架之前，或独立运行 Asset QC 得到的结果。它不等同于一个 rig 产出包。",
        "",
        "### 6. `external/`、`reports/`、`legacy/` 是辅助/历史材料",
        "",
        "- `external/`：OBJ 导出、Skeletor/外部探测结果。",
        "- `reports/`：独立迭代说明。",
        "- `legacy/`：早期 smoke test 或整理前遗留产物，只做参考。",
        "",
        "### 7. `_indexes/` 是跨 run 索引",
        "",
        "`_indexes/screenshot_output_pairs.md/json` 汇总所有 run 的截图和对应产物。它只是导航，不是产物存放位置。",
        "",
        "### 8. `default_recommended/` 是旧式快捷副本",
        "",
        "这个目录保留了旧推荐算法产物的扁平副本。它已经不作为生产入口；后续优先看带时间戳的 `runs/<assetName>__YYYYMMDD_HHMMSS/`。",
        "",
        "## 当前规模",
        "",
        f"- 生成批次目录数量：`{run_count}`",
        f"- 视角索引数量：`{view_count}`",
        "",
        "## 重新整理命令",
        "",
        "如果以后 `out/` 又被新批处理写乱，重新运行：",
        "",
        "```powershell",
        "tools\\3dsmax-ai-rig-assistant\\.venv\\Scripts\\python.exe tools\\3dsmax-ai-rig-assistant\\server\\organize_out_dir.py --out-dir tools\\3dsmax-ai-rig-assistant\\out",
        "```",
        "",
        "整理脚本会刷新 `README.md`、`views/`、`_indexes/screenshot_output_pairs.*` 和 `_organized_index.json`。",
    ]
    (root / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_simple_readme(directory: Path, title: str, description: str) -> None:
    files = sorted([p.name for p in directory.iterdir() if p.is_file() and p.name != "README.md"])
    dirs = sorted([p.name for p in directory.iterdir() if p.is_dir()])
    lines = [f"# {title}", "", description, "", "## 内容", ""]
    if dirs:
        lines.append("### 目录")
        lines.append("")
        for item in dirs:
            lines.append(f"- `{item}/`")
        lines.append("")
    if files:
        lines.append("### 文件")
        lines.append("")
        for item in files:
            lines.append(f"- `{item}`")
    if not dirs and not files:
        lines.append("- 整理后当前为空。")
    (directory / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_runs_root_readme(root: Path) -> None:
    runs_root = root / "runs"
    active = organized_run_dirs(runs_root)
    active_names = {p.name for p in active}
    ignored = sorted([p.name for p in runs_root.iterdir() if p.is_dir() and p.name not in active_names]) if runs_root.exists() else []
    lines = [
        "# runs",
        "",
        "这里按 `assetName__YYYYMMDD_HHMMSS` 保存每一次 Stage01 生成批次。同一个模型重复生成会得到新的时间戳目录。",
        "",
        "## 有效批次",
        "",
    ]
    if active:
        for run_dir in active:
            lines.append(f"- `{run_dir.name}/`")
    else:
        lines.append("- 当前没有有效批次。")
    if ignored:
        lines += [
            "",
            "## 已忽略的旧目录",
            "",
            "下面这些是整理前遗留或被 Windows 锁住的无时间戳空壳，不作为有效批次计入索引：",
            "",
        ]
        for name in ignored:
            lines.append(f"- `{name}/`")
    (runs_root / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_generic_readmes(root: Path) -> None:
    descriptions = {
        "runs": "按 assetName + 时间戳分组的一次次 Stage01 输出。每个子目录都会说明该模型怎样生成、当前 QC 状态如何。",
        "benchmarks": "旧算法评分结果、推荐 JSON、默认算法检查和历史记录；生产判断不再使用。",
        "asset_qc": "独立资产质检输出，不等同于一次 Stage01 rig 生成批次。",
        "external": "外部 mesh 导出和探测结果。",
        "legacy": "早期 smoke test 或整理前遗留产物，仅供参考。",
        "reports": "独立迭代说明和 MDC 可读实验记录。",
        "misc": "未匹配到已知输出规则的文件。",
        "visual_screenshots": "旧版截图暂存目录。整理脚本会尽量把截图移动到 `runs/<assetName>/screenshots/`。",
        "textured_screenshots": "带贴图截图暂存目录。整理脚本会把新截图移动到 `runs/<assetName>/textured_screenshots/`。",
        "wire_bone_screenshots": "线框+骨骼截图暂存目录。整理脚本会把新截图移动到 `runs/<assetName>/wire_bone_screenshots/`。",
        "_indexes": "由 `server/organize_out_dir.py` 生成的跨 run 导航索引。",
    }
    for directory in sorted([p for p in root.rglob("*") if p.is_dir()], key=lambda p: len(p.parts)):
        rel = directory.relative_to(root).as_posix()
        parts = directory.relative_to(root).parts
        if parts and parts[0] in STAGING_SCREENSHOT_DIRS:
            continue
        if directory.resolve() == (root / "runs").resolve():
            write_runs_root_readme(root)
            continue
        if parts and parts[0] == "runs" and len(parts) >= 2:
            continue
        title = rel or "out"
        desc = descriptions.get(directory.name, "由 `server/organize_out_dir.py` 整理生成的输出目录。")
        write_simple_readme(directory, title, desc)


def cleanup_generated_readme_duplicates(root: Path) -> None:
    for duplicate in root.glob("runs/*/screenshots/README__dup*.md"):
        duplicate.unlink()

    for screenshot_root in [root / name for name in STAGING_SCREENSHOT_DIRS]:
        if not screenshot_root.exists():
            continue
        for directory in sorted([p for p in screenshot_root.iterdir() if p.is_dir()], key=lambda p: p.name):
            files = [p for p in directory.iterdir() if p.is_file()]
            dirs = [p for p in directory.iterdir() if p.is_dir()]
            if dirs:
                continue
            if (not files) or all(p.name == "README.md" for p in files):
                for file_path in files:
                    try:
                        file_path.unlink()
                    except OSError:
                        pass
                try:
                    directory.rmdir()
                except OSError:
                    pass
        root_files = [p for p in screenshot_root.iterdir() if p.is_file()]
        root_dirs = [p for p in screenshot_root.iterdir() if p.is_dir()]
        if (not root_dirs) and all(p.name == "README.md" for p in root_files):
            for file_path in root_files:
                try:
                    file_path.unlink()
                except OSError:
                    pass
            try:
                screenshot_root.rmdir()
            except OSError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Organize 3ds Max AI Rig Assistant out/ files into per-batch directories.")
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    tool_root = Path(__file__).resolve().parents[1]
    out_dir = Path(args.out_dir).resolve() if args.out_dir else tool_root / "out"
    if not out_dir.exists():
        raise FileNotFoundError(out_dir)

    moves: list[dict[str, str]] = []
    screenshot_root = out_dir / "visual_screenshots"
    current_run_dirs = build_pending_run_dirs(out_dir, screenshot_root)
    run_names = set(current_run_dirs.values())
    runs_root = out_dir / "runs"
    if runs_root.exists():
        run_names.update(p.name for p in runs_root.iterdir() if p.is_dir())
    if screenshot_root.exists():
        run_names.update(p.name for p in screenshot_root.iterdir() if p.is_dir() and has_payload(p))
    textured_root = out_dir / "textured_screenshots"
    if textured_root.exists():
        run_names.update(p.name for p in textured_root.iterdir() if p.is_dir() and has_payload(p))
    wire_bone_root = out_dir / "wire_bone_screenshots"
    if wire_bone_root.exists():
        run_names.update(p.name for p in wire_bone_root.iterdir() if p.is_dir() and has_payload(p))
    for file_path in out_dir.iterdir():
        if file_path.is_file():
            asset_name = stage01_asset_name(file_path.name)
            if asset_name:
                run_names.add(asset_name)
        elif file_path.is_dir():
            asset_name = texture_sidecar_asset_name(file_path.name)
            if asset_name:
                run_names.add(asset_name)

    candidate_dirs = [out_dir, out_dir / "legacy" / "luxun_stage01", out_dir / "misc"]
    root_keep_files = {"README.md", "_organized_index.json", "screenshot_output_pairs.json", "screenshot_output_pairs.md"}
    for candidate_dir in candidate_dirs:
        if not candidate_dir.exists():
            continue
        for file_path in sorted([p for p in candidate_dir.iterdir() if p.is_file() and p.name not in root_keep_files], key=lambda p: p.name):
            rel_dir, _ = classify_root_file(file_path, run_names, current_run_dirs)
            target_dir = safe_child(out_dir, rel_dir)
            move_file(file_path, target_dir / file_path.name, args.dry_run, moves)

    if screenshot_root.exists():
        for screenshot_dir in sorted([p for p in screenshot_root.iterdir() if p.is_dir()], key=lambda p: p.name):
            if not has_payload(screenshot_dir):
                continue
            run_dir_name = current_run_dirs.get(screenshot_dir.name, screenshot_dir.name)
            target_dir = safe_child(out_dir, "runs", run_dir_name, "screenshots")
            run_names.add(run_dir_name)
            move_dir_contents(screenshot_dir, target_dir, args.dry_run, moves, skip_names={"README.md"})

    if textured_root.exists():
        for screenshot_dir in sorted([p for p in textured_root.iterdir() if p.is_dir()], key=lambda p: p.name):
            if not has_payload(screenshot_dir):
                continue
            run_dir_name = current_run_dirs.get(screenshot_dir.name, screenshot_dir.name)
            target_dir = safe_child(out_dir, "runs", run_dir_name, "textured_screenshots")
            run_names.add(run_dir_name)
            move_dir_contents(screenshot_dir, target_dir, args.dry_run, moves, skip_names={"README.md"})

    if wire_bone_root.exists():
        for screenshot_dir in sorted([p for p in wire_bone_root.iterdir() if p.is_dir()], key=lambda p: p.name):
            if not has_payload(screenshot_dir):
                continue
            run_dir_name = current_run_dirs.get(screenshot_dir.name, screenshot_dir.name)
            target_dir = safe_child(out_dir, "runs", run_dir_name, "wire_bone_screenshots")
            run_names.add(run_dir_name)
            move_dir_contents(screenshot_dir, target_dir, args.dry_run, moves, skip_names={"README.md"})

    for dir_path in sorted([p for p in out_dir.iterdir() if p.is_dir()], key=lambda p: p.name):
        asset_name = texture_sidecar_asset_name(dir_path.name)
        if not asset_name:
            continue
        run_dir_name = current_run_dirs.get(asset_name, asset_name)
        target_dir = safe_child(out_dir, "runs", run_dir_name, "scene", dir_path.name)
        move_dir_contents(dir_path, target_dir, args.dry_run, moves, skip_names={"README.md"})
        if not args.dry_run:
            try:
                dir_path.rmdir()
            except OSError:
                pass

    if not args.dry_run:
        runs_root = safe_child(out_dir, "runs")
        migrate_legacy_run_dirs(runs_root, args.dry_run, moves)
        if runs_root.exists():
            for run_dir in organized_run_dirs(runs_root):
                normalize_run_layout(run_dir, args.dry_run, moves)
                refresh_run_report_paths(run_dir, split_run_dir_name(run_dir.name)[0])
                write_run_readme(run_dir, split_run_dir_name(run_dir.name)[0])

        write_global_screenshot_pairs(out_dir)
        write_out_readme(out_dir)
        write_generic_readmes(out_dir)
        cleanup_generated_readme_duplicates(out_dir)
        asset_run_index = build_asset_run_index(out_dir)
        index = {
            "organizedAt": datetime.now().isoformat(timespec="seconds"),
            "outDir": str(out_dir),
            "moveCount": len(moves),
            "pendingRunDirs": current_run_dirs,
            "assetRuns": asset_run_index,
            "runs": [p.name for p in organized_run_dirs(out_dir / "runs")],
            "moves": moves,
        }
        (out_dir / "_organized_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        asset_run_index = {}

    final_runs_root = out_dir / "runs"
    final_run_count = len(organized_run_dirs(final_runs_root)) if final_runs_root.exists() else len(run_names)
    print(
        json.dumps(
            {
                "ok": True,
                "dryRun": args.dry_run,
                "outDir": str(out_dir),
                "moveCount": len(moves),
                "runCount": final_run_count,
                "pendingRunDirs": current_run_dirs,
                "assetRuns": asset_run_index,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
