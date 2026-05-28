from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


LAYOUT_VERSION = "stage01-numbered-v1"


STEPS: list[dict[str, Any]] = [
    {
        "legacy": "scene",
        "numbered": "01_scene_workspace",
        "title": "Scene workspace",
        "phase": "输入工作副本与候选骨架场景",
        "does": "保存 3ds Max batch 使用的 ASCII-safe FBX 工作副本、贴图 sidecar，以及已经生成 Guide 和候选 Biped 的 .max 场景。",
        "read": "打开 .max 看真实 3ds Max 场景；FBX/FBM 是批处理工作副本，不是原始资产目录。",
        "use": "后续 MDC 校正 Guide、重新拟合 Biped、进入 Stage02 Skin 时从这里拿场景。",
        "misread": "这里的 Biped 是 Stage01 自动候选，不是参考答案骨架，也不是已完成蒙皮的生产结果。",
    },
    {
        "legacy": "logs",
        "numbered": "02_generation_logs",
        "title": "Generation logs",
        "phase": "3ds Max 批处理执行记录",
        "does": "保存 3dsmaxbatch 和 listener 原始日志，用来回溯导入、贴图 relink、截图、保存场景等过程。",
        "read": "优先在失败时看；正常复查不用从日志开始。",
        "use": "排查 MaxScript 报错、导入失败、截图失败、路径异常。",
        "misread": "日志不是结论报告，只是过程记录。",
    },
    {
        "legacy": "data",
        "numbered": "03_stage01_data",
        "title": "Stage01 structured data",
        "phase": "机器可读诊断数据",
        "does": "保存 body profile、Guide/Biped snapshot、机械贴合 QC、视觉 QC、细节审查、Skin gate 等 JSON。",
        "read": "脚本或二次分析优先读这里；MDC 只需查关键字段：fitRefinement、missingGuides、fitFailures、stage01HandoffReady、skinSetupReady。",
        "use": "生成报告、做参考答案比对、驱动下一步 gate 或自动复查。",
        "misread": "JSON 里的旧路径可能记录生成瞬间的位置，实际文件位置以本 README 和 layout manifest 为准。",
    },
    {
        "legacy": "reports",
        "numbered": "04_stage01_reports",
        "title": "Stage01 reports",
        "phase": "MDC 可读报告",
        "does": "保存 batch summary、body profile、fit QC、rig detail review、skin prep gate 等 Markdown。",
        "read": "从 batch summary 看本轮做了什么；从 skin prep gate 看能不能进入 Skin；从 fit QC 看机械贴合是否收敛。",
        "use": "给人快速判断当前候选骨架的状态、风险和下一步。",
        "misread": "机械贴合通过只代表候选 Biped 贴到了当前 Guide，不代表美术语义或蒙皮变形已经合格。",
    },
    {
        "legacy": "screenshots",
        "numbered": "05_qc_silhouette_views",
        "title": "QC silhouette views",
        "phase": "本地视觉 QC 三视图",
        "does": "保存由 visual_qc 根据 snapshot 绘制的 front/side/top 图，展示模型点云、Guide、候选骨架和局部偏差。",
        "read": "用于快速看 Guide/Biped 是否落在轮廓内部；这是投影示意图，不是 Max 真实视口。",
        "use": "自动/MDC 初筛大偏移、左右不对称、外轮廓漂移。",
        "misread": "不要把它当作最终渲染图；真实骨骼视口证据看第 07 步。",
    },
    {
        "legacy": "textured_screenshots",
        "numbered": "06_textured_model_views",
        "title": "Textured model views",
        "phase": "贴图外观三视图",
        "does": "保存 3ds Max 带贴图视图，用于理解角色颜色、纹样、头饰、服装、脚尖等语义线索。",
        "read": "先看角色实际外观，再和线框骨骼图对照。",
        "use": "确认 Guide 不能追错装饰、披风、裙摆、头饰或武器轮廓。",
        "misread": "这组图主要提供语义上下文，本身不证明骨骼位置正确。",
    },
    {
        "legacy": "wire_bone_screenshots",
        "numbered": "07_wire_bone_technical_views",
        "title": "Wire bone technical views",
        "phase": "真实 Max 技术视图",
        "does": "保存 3ds Max 线框 + Guide + 候选 Biped 的 front/side/top 技术截图。",
        "read": "这是判断候选 Biped 是否贴合体积的核心图；侧视看前后重心，顶视看深度，前视看左右和高度。",
        "use": "MDC 本地代理 signoff，定位骨盆/头/手/脚等高风险点。",
        "misread": "图里是真实创建的候选 Biped，但不是参考答案骨架，也没有证明 Skin 权重合格。",
    },
    {
        "legacy": "visual_review",
        "numbered": "08_visual_review_evidence",
        "title": "Visual review evidence",
        "phase": "视觉语义审查证据包",
        "does": "整合全局图、头/手/脚/骨盆局部裁剪、贴图语义叠加、纹理/线框配对图、MR 式切片和审查 schema。",
        "read": "从 review_input.md 看审查问题；从 full/、regions/、semantic_analysis/、slices/ 看证据。",
        "use": "给 MDC 本地代理按固定 blocker 做多视角语义确认。",
        "misread": "这里不输出产品级评分；它只帮助判断是否清除或保留 blocker。",
    },
    {
        "legacy": "views",
        "numbered": "09_view_indexes",
        "title": "View indexes",
        "phase": "按视角导航",
        "does": "保存 front/side/top 的引用式索引，把同一视角下的场景、截图、报告、JSON 串起来。",
        "read": "如果你正在看某一张图，打开对应 view markdown，顺着它跳到相关产物。",
        "use": "减少在多个目录里来回找文件的时间。",
        "misread": "这里是导航索引，不保存重复产物。",
    },
]


TEXT_SUFFIXES = {".json", ".md", ".txt", ".csv", ".log"}
VIEWS = ["front", "side", "top"]

BROKEN_NUMBERED_PATHS = {
    "02_generation_02_generation_02_generation_logs": "02_generation_logs",
    "02_generation_02_generation_logs": "02_generation_logs",
    "03_stage01_03_stage01_03_stage01_data": "03_stage01_data",
    "03_stage01_03_stage01_data": "03_stage01_data",
    "04_stage01_04_stage01_04_stage01_reports": "04_stage01_reports",
    "04_stage01_04_stage01_reports": "04_stage01_reports",
    "05_qc_silhouette_09_view_indexes": "05_qc_silhouette_views",
    "06_textured_model_09_view_indexes": "06_textured_model_views",
    "07_wire_bone_technical_09_view_indexes": "07_wire_bone_technical_views",
}


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


def write_text(path: Path, text: str, dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


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


def merge_or_rename_dir(src: Path, dst: Path, dry_run: bool, moves: list[dict[str, str]]) -> None:
    if src.exists() and src.resolve() == dst.resolve():
        return
    if src.exists() and not dst.exists():
        moves.append({"source": str(src), "target": str(dst), "kind": "rename_dir"})
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
        return
    if src.exists() and dst.exists():
        for item in sorted(src.iterdir(), key=lambda p: p.name):
            target = unique_target(dst / item.name)
            moves.append({"source": str(item), "target": str(target), "kind": "move_into_numbered"})
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(item), str(target))
        if not dry_run:
            try:
                src.rmdir()
            except OSError:
                pass
        return
    if not dst.exists():
        moves.append({"source": "", "target": str(dst), "kind": "create_empty_step_dir"})
        if not dry_run:
            dst.mkdir(parents=True, exist_ok=True)


def escaped_json_path(path: Path) -> str:
    return json.dumps(str(path), ensure_ascii=False)[1:-1]


def build_absolute_replacements(run_dir: Path) -> dict[str, str]:
    replacements: dict[str, str] = {}
    for step in STEPS:
        legacy = step["legacy"]
        numbered = step["numbered"]
        legacy_abs = run_dir / legacy
        numbered_abs = run_dir / numbered
        for old, new in [
            (str(legacy_abs), str(numbered_abs)),
            (legacy_abs.as_posix(), numbered_abs.as_posix()),
            (escaped_json_path(legacy_abs), escaped_json_path(numbered_abs)),
        ]:
            replacements[old] = new
    return dict(sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True))


def normalize_previously_broken_paths(text: str) -> str:
    updated = text
    for _ in range(4):
        before = updated
        for old, new in BROKEN_NUMBERED_PATHS.items():
            updated = updated.replace(old, new)
        if updated == before:
            break
    return updated


def rewrite_text_references(run_dir: Path, absolute_replacements: dict[str, str], dry_run: bool) -> int:
    changed = 0
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        original = read_text(path)
        updated = normalize_previously_broken_paths(original)
        for old, new in absolute_replacements.items():
            updated = updated.replace(old, new)
        for step in STEPS:
            legacy = re.escape(step["legacy"])
            numbered = step["numbered"]
            updated = re.sub(rf"(?<![A-Za-z0-9_]){legacy}(?=[\\/])", numbered, updated)
        if updated != original:
            changed += 1
            if not dry_run:
                path.write_text(updated, encoding="utf-8")
    return changed


def first_file(root: Path, pattern: str) -> Path | None:
    if not root.exists():
        return None
    matches = sorted(root.glob(pattern), key=lambda p: p.name)
    return matches[0] if matches else None


def files_in(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted([p for p in root.iterdir() if p.is_file()], key=lambda p: p.name)


def dirs_in(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name)


def collect_signals(run_dir: Path, asset_name: str) -> dict[str, Any]:
    data_dir = run_dir / "03_stage01_data"
    report_dir = run_dir / "04_stage01_reports"
    fit_qc = load_json(data_dir / f"{asset_name}_stage01_fit_qc.json")
    gate = load_json(data_dir / f"{asset_name}_stage01_skin_prep_gate.json")
    body = load_json(data_dir / f"{asset_name}_body_profile.json")
    summary = read_text(report_dir / f"{asset_name}_stage01_batch_summary.md")

    algorithm = fit_qc.get("guideSource") or "unknown"
    if "tutorial_centerline_qbird" in str(algorithm):
        algorithm = "tutorial_centerline_qbird"
    if algorithm == "unknown" and "Guide algorithm:" in summary:
        for line in summary.splitlines():
            if "Guide algorithm:" in line:
                algorithm = line.split("`")[1] if "`" in line else line.split(":", 1)[-1].strip()
                break

    blockers = gate.get("semanticSkinBlockers", [])
    if not isinstance(blockers, list):
        blockers = []
    refinement = fit_qc.get("fitRefinement", {})
    readiness = gate.get("readiness", {})
    biped_fit = readiness.get("bipedFit", {}) if isinstance(readiness, dict) else {}

    return {
        "assetName": asset_name,
        "layoutVersion": LAYOUT_VERSION,
        "guideAlgorithm": algorithm,
        "bodyType": gate.get("bodyType") or body.get("bodyType") or "unknown",
        "bipedFound": fit_qc.get("bipedFound"),
        "mechanicalConverged": refinement.get("converged") if isinstance(refinement, dict) else None,
        "fitIterations": refinement.get("iterations") if isinstance(refinement, dict) else None,
        "fitFinalFailures": refinement.get("finalFailures") if isinstance(refinement, dict) else None,
        "fitMaxDistance": fit_qc.get("maxGuideNodeDistance"),
        "bipedFitReady": biped_fit.get("ready") if isinstance(biped_fit, dict) else None,
        "stage01CandidateAvailable": gate.get("stage01CandidateAvailable"),
        "stage01MechanicalHandoffReady": gate.get("stage01MechanicalHandoffReady"),
        "stage01HandoffReady": gate.get("stage01HandoffReady"),
        "skinSetupReady": gate.get("skinSetupReady"),
        "productionReady": gate.get("productionReady"),
        "semanticSkinBlockerCount": len(blockers),
        "semanticSkinReady": gate.get("semanticSkinReady"),
    }


def key_artifacts(run_dir: Path, asset_name: str) -> dict[str, str]:
    artifacts = {
        "sceneMax": first_file(run_dir / "01_scene_workspace", f"{asset_name}_stage01_rig_scene.max"),
        "workingFbx": first_file(run_dir / "01_scene_workspace", f"{asset_name}.fbx"),
        "stage01Report": first_file(run_dir / "04_stage01_reports", "AIRA_stage01_biped_report.md"),
        "batchSummary": first_file(run_dir / "04_stage01_reports", f"{asset_name}_stage01_batch_summary.md"),
        "bodyProfileMarkdown": first_file(run_dir / "04_stage01_reports", f"{asset_name}_body_profile.md"),
        "fitQcMarkdown": first_file(run_dir / "04_stage01_reports", f"{asset_name}_stage01_fit_qc.md"),
        "visualQcMarkdown": first_file(run_dir / "04_stage01_reports", f"{asset_name}_visual_qc.md"),
        "rigDetailReviewMarkdown": first_file(run_dir / "04_stage01_reports", f"{asset_name}_rig_detail_review.md"),
        "skinGateMarkdown": first_file(run_dir / "04_stage01_reports", f"{asset_name}_stage01_skin_prep_gate.md"),
        "rigAssetQcMarkdown": first_file(run_dir / "04_stage01_reports", f"{asset_name}_stage01_rig_asset_qc.md"),
        "bodyProfileJson": first_file(run_dir / "03_stage01_data", f"{asset_name}_body_profile.json"),
        "visualSnapshotJson": first_file(run_dir / "03_stage01_data", f"{asset_name}_visual_snapshot.json"),
        "visualQcJson": first_file(run_dir / "03_stage01_data", f"{asset_name}_visual_qc.json"),
        "fitQcJson": first_file(run_dir / "03_stage01_data", f"{asset_name}_stage01_fit_qc.json"),
        "rigDetailReviewJson": first_file(run_dir / "03_stage01_data", f"{asset_name}_rig_detail_review.json"),
        "skinGateJson": first_file(run_dir / "03_stage01_data", f"{asset_name}_stage01_skin_prep_gate.json"),
        "rigAssetQcJson": first_file(run_dir / "03_stage01_data", f"{asset_name}_stage01_rig_asset_qc.json"),
        "wireFront": first_file(run_dir / "07_wire_bone_technical_views", f"{asset_name}_wire_bone_front.png"),
        "wireSide": first_file(run_dir / "07_wire_bone_technical_views", f"{asset_name}_wire_bone_side.png"),
        "wireTop": first_file(run_dir / "07_wire_bone_technical_views", f"{asset_name}_wire_bone_top.png"),
        "reviewInput": first_file(run_dir / "08_visual_review_evidence", "review_input.md"),
        "reviewManifest": first_file(run_dir / "08_visual_review_evidence", f"{asset_name}_visual_evidence_manifest.json"),
    }
    return {key: rel(path, run_dir) for key, path in artifacts.items() if path is not None}


def existing_rel(run_dir: Path, relative_path: str) -> str:
    path = run_dir / relative_path
    return relative_path if path.exists() else ""


def write_numbered_view_indexes(
    run_dir: Path,
    asset_name: str,
    signals: dict[str, Any],
    artifacts: dict[str, str],
    dry_run: bool,
) -> None:
    index_dir = run_dir / "09_view_indexes"
    if not dry_run:
        index_dir.mkdir(parents=True, exist_ok=True)

    pairs: list[dict[str, Any]] = []
    for view in VIEWS:
        screenshot = existing_rel(run_dir, f"05_qc_silhouette_views/{asset_name}_{view}.png")
        textured = existing_rel(run_dir, f"06_textured_model_views/{asset_name}_textured_{view}.png")
        wire = existing_rel(run_dir, f"07_wire_bone_technical_views/{asset_name}_wire_bone_{view}.png")
        full = existing_rel(run_dir, f"08_visual_review_evidence/full/{asset_name}_full_{view}.png")
        pair = {
            "view": view,
            "screenshots": {
                "qcSilhouette": screenshot,
                "texturedModel": textured,
                "wireBoneTechnical": wire,
                "visualReviewFull": full,
            },
            "outputs": artifacts,
        }
        pairs.append(pair)

        lines = [
            f"# {asset_name} - {view} 视角",
            "",
            "这是一张截图的操作索引。它不复制产物，只把同一视角相关的最终编号目录路径串起来。",
            "",
            "## 截图",
            "",
        ]
        for label, value in pair["screenshots"].items():
            lines.append(f"- `{label}`: `{value or 'missing'}`")
        lines += [
            "",
            "## 关键产物",
            "",
            f"- 场景：`{artifacts.get('sceneMax', '')}`",
            f"- 工作 FBX：`{artifacts.get('workingFbx', '')}`",
            f"- Visual QC：`{artifacts.get('visualQcMarkdown', '')}`",
            f"- 视觉语义证据包：`{artifacts.get('reviewInput', '')}`",
            f"- 逐骨检查：`{artifacts.get('rigDetailReviewMarkdown', '')}`",
            f"- Skin 前置门：`{artifacts.get('skinGateMarkdown', '')}`",
            f"- 资产 QC：`{artifacts.get('rigAssetQcMarkdown', '')}`",
            "",
            "## 当前信号",
            "",
        ]
        for key in [
            "bodyType",
            "guideAlgorithm",
            "stage01CandidateAvailable",
            "stage01MechanicalHandoffReady",
            "stage01HandoffReady",
            "skinSetupReady",
            "productionReady",
            "semanticSkinBlockerCount",
        ]:
            lines.append(f"- `{key}`: `{signals.get(key)}`")
        write_text(index_dir / f"{view}.md", "\n".join(lines) + "\n", dry_run)

    index_json = {
        "assetName": asset_name,
        "layoutVersion": LAYOUT_VERSION,
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "pairs": pairs,
    }
    write_text(index_dir / "index.json", json.dumps(index_json, ensure_ascii=False, indent=2) + "\n", dry_run)

    lines = [
        f"# View Indexes - {asset_name}",
        "",
        "| View | QC silhouette | Textured | Wire/Bone | Visual review full | Scene | Gate |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for pair in pairs:
        screenshots = pair["screenshots"]
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                pair["view"],
                screenshots.get("qcSilhouette", ""),
                screenshots.get("texturedModel", ""),
                screenshots.get("wireBoneTechnical", ""),
                screenshots.get("visualReviewFull", ""),
                artifacts.get("sceneMax", ""),
                artifacts.get("skinGateMarkdown", ""),
            )
        )
    lines += [
        "",
        "## 入口",
        "",
        "- `front.md`",
        "- `side.md`",
        "- `top.md`",
    ]
    write_text(index_dir / "index.md", "\n".join(lines) + "\n", dry_run)


def write_step_readme(run_dir: Path, step: dict[str, Any], dry_run: bool) -> None:
    directory = run_dir / step["numbered"]
    files = files_in(directory)
    dirs = dirs_in(directory)
    lines = [
        f"# {step['numbered']} - {step['title']}",
        "",
        f"- 流程阶段：{step['phase']}",
        f"- 这一步做什么：{step['does']}",
        f"- 怎样解读：{step['read']}",
        f"- 作用/下游：{step['use']}",
        f"- 常见误读：{step['misread']}",
        "",
        "## 内容",
        "",
    ]
    if dirs:
        lines.append("### 子目录")
        lines.append("")
        for item in dirs:
            lines.append(f"- `{item.name}/`")
        lines.append("")
    if files:
        lines.append("### 文件")
        lines.append("")
        for item in files:
            if item.name == "README.md":
                continue
            lines.append(f"- `{item.name}`")
    if not dirs and not [p for p in files if p.name != "README.md"]:
        lines.append("- 当前没有产物。")
    write_text(directory / "README.md", "\n".join(lines) + "\n", dry_run)


def write_run_readme(run_dir: Path, asset_name: str, signals: dict[str, Any], artifacts: dict[str, str], dry_run: bool) -> None:
    lines = [
        f"# Stage01 Run - {asset_name}",
        "",
        "这是一次 Stage01 自动候选骨架产出。目录已经按执行/复查顺序编号，建议从上到下看。",
        "",
        "## 先看结论",
        "",
        f"- Guide 算法：`{signals.get('guideAlgorithm')}`",
        f"- Body type：`{signals.get('bodyType')}`",
        f"- Biped 已生成：`{signals.get('bipedFound')}`",
        f"- 机械贴合收敛：`{signals.get('mechanicalConverged')}`",
        f"- Fit iterations：`{signals.get('fitIterations')}`",
        f"- Final failures：`{signals.get('fitFinalFailures')}`",
        f"- Stage01 mechanical handoff：`{signals.get('stage01MechanicalHandoffReady')}`",
        f"- Stage01 handoff ready：`{signals.get('stage01HandoffReady')}`",
        f"- Skin setup ready：`{signals.get('skinSetupReady')}`",
        f"- Production ready：`{signals.get('productionReady')}`",
        f"- Semantic Skin blockers：`{signals.get('semanticSkinBlockerCount')}`",
        "",
        "## 核心术语",
        "",
        "- `Guide`：从模型点云估算的候选关节点，是校准目标，不是真正骨骼。",
        "- `Candidate Biped`：按 Guide 创建并拟合出来的 3ds Max Biped，是真实对象，但仍是候选结果。",
        "- `Reference answer`：资产里已经绑定/蒙皮的参考答案；本 run 不会把参考骨架直接复制进来。",
        "- `Stage01 ready`：只说明候选骨架可以进入下一步检查，不代表 Skin 权重或动画变形已合格。",
        "",
        "## 推荐阅读顺序",
        "",
        "| 步骤 | 目录 | 这一步做了什么 | 怎样解读 |",
        "| --- | --- | --- | --- |",
    ]
    for step in STEPS:
        lines.append(
            f"| {step['numbered'].split('_', 1)[0]} | `{step['numbered']}/` | {step['phase']} | {step['read']} |"
        )
    lines += [
        "",
        "## 关键入口",
        "",
    ]
    if artifacts:
        for key, value in artifacts.items():
            lines.append(f"- `{key}`: `{value}`")
    else:
        lines.append("- 当前没有识别到关键入口文件。")
    lines += [
        "",
        "## 怎么用这包产物",
        "",
        "1. 先读 `04_stage01_reports/*_stage01_skin_prep_gate.md`，确认 gate 阻断项。",
        "2. 打开 `07_wire_bone_technical_views/` 的 front/side/top，看候选 Biped 是否在体积内部。",
        "3. 对照 `06_textured_model_views/`，确认骨盆、头、手、脚没有被衣服、头饰、武器或装饰误导。",
        "4. 需要局部证据时看 `08_visual_review_evidence/regions/` 和 `slices/`。",
        "5. 需要继续调骨时打开 `01_scene_workspace/*.max`。",
        "",
        "## 额外补充",
        "",
        "- 本目录保留 `layout_manifest.json`，记录旧目录到新编号目录的映射，方便脚本或 MDC 追踪。",
        "- 每个编号目录都有自己的 README，说明它的产物、上下文和常见误读。",
        "- 目录编号表达推荐操作/复查顺序；单个文件内部的生成时间仍以报告和日志为准。",
    ]
    write_text(run_dir / "README.md", "\n".join(lines) + "\n", dry_run)


def write_manifest(
    run_dir: Path,
    asset_name: str,
    moves: list[dict[str, str]],
    rewritten_files: int,
    signals: dict[str, Any],
    artifacts: dict[str, str],
    dry_run: bool,
) -> dict[str, Any]:
    legacy_to_numbered = {
        step["legacy"]: str((run_dir / step["numbered"]).resolve())
        for step in STEPS
    }
    manifest = {
        "ok": True,
        "layoutVersion": LAYOUT_VERSION,
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "assetName": asset_name,
        "runDir": str(run_dir.resolve()),
        "legacyToNumbered": legacy_to_numbered,
        "steps": [
            {
                "number": step["numbered"].split("_", 1)[0],
                "legacy": step["legacy"],
                "directory": step["numbered"],
                "path": str((run_dir / step["numbered"]).resolve()),
                "phase": step["phase"],
                "does": step["does"],
                "read": step["read"],
                "use": step["use"],
            }
            for step in STEPS
        ],
        "signals": signals,
        "keyArtifacts": artifacts,
        "moves": moves,
        "rewrittenTextFileCount": rewritten_files,
        "dryRun": dry_run,
    }
    write_text(run_dir / "layout_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", dry_run)
    return manifest


def write_runs_index(run_dir: Path, manifest: dict[str, Any], dry_run: bool) -> None:
    out_root = run_dir.parent.parent if run_dir.parent.name == "runs" else run_dir.parent
    index_dir = out_root / "_indexes"
    index_path = index_dir / "stage01_numbered_layout_latest.md"
    lines = [
        "# Stage01 Numbered Layout",
        "",
        "最新一次应用编号目录布局的 run：",
        "",
        f"- Run: `{rel(run_dir, out_root)}`",
        f"- Asset: `{manifest.get('assetName')}`",
        f"- Layout version: `{manifest.get('layoutVersion')}`",
        "",
        "## 编号目录",
        "",
        "| Step | Directory | Phase |",
        "| --- | --- | --- |",
    ]
    for step in manifest.get("steps", []):
        lines.append(f"| `{step['number']}` | `{rel(Path(step['path']), run_dir)}/` | {step['phase']} |")
    lines += [
        "",
        "打开该 run 根目录的 `README.md` 查看完整说明。",
    ]
    write_text(index_path, "\n".join(lines) + "\n", dry_run)


def apply_layout(run_dir: Path, asset_name: str, dry_run: bool = False) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    if not run_dir.exists() or not run_dir.is_dir():
        raise FileNotFoundError(f"run dir not found: {run_dir}")

    moves: list[dict[str, str]] = []
    for step in STEPS:
        merge_or_rename_dir(run_dir / step["legacy"], run_dir / step["numbered"], dry_run, moves)

    absolute_replacements = build_absolute_replacements(run_dir)
    rewritten_files = rewrite_text_references(run_dir, absolute_replacements, dry_run)

    signals = collect_signals(run_dir, asset_name)
    artifacts = key_artifacts(run_dir, asset_name)
    write_numbered_view_indexes(run_dir, asset_name, signals, artifacts, dry_run)
    for step in STEPS:
        write_step_readme(run_dir, step, dry_run)

    write_run_readme(run_dir, asset_name, signals, artifacts, dry_run)
    manifest = write_manifest(run_dir, asset_name, moves, rewritten_files, signals, artifacts, dry_run)
    write_runs_index(run_dir, manifest, dry_run)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply numbered final layout to a completed Stage01 run directory.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--asset-name", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    asset_name = args.asset_name or run_dir.name.split("__", 1)[0]
    manifest = apply_layout(run_dir, asset_name, dry_run=args.dry_run)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
