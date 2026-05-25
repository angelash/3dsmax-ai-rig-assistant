from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from stage01_numbered_layout import apply_layout
from visual_review_pack import RgbImage

try:
    from PIL import Image as PILImage
    from PIL import ImageDraw as PILImageDraw
except Exception:  # pragma: no cover - pure Python fallback remains available.
    PILImage = None
    PILImageDraw = None


RUN_RE = re.compile(r"^(a1_\d{3}_[a-z0-9_]+)__\d{8}_\d{6}(?:__r\d+)?$")
LAYOUT_VERSION = "stage01-a1-audit-report-v1"
VIEWS = ["front", "side", "top"]


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


def rel(path: Path, root: Path) -> str:
    path_resolved = path.resolve()
    root_resolved = root.resolve()
    try:
        return path_resolved.relative_to(root_resolved).as_posix()
    except ValueError:
        try:
            return Path(os.path.relpath(path_resolved, root_resolved)).as_posix()
        except ValueError:
            return str(path_resolved)


def clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def discover_runs(out_dir: Path) -> list[dict[str, Any]]:
    runs_root = out_dir / "runs"
    runs: list[dict[str, Any]] = []
    if not runs_root.exists():
        return runs
    for run_dir in sorted([p for p in runs_root.iterdir() if p.is_dir()], key=lambda p: p.name):
        match = RUN_RE.match(run_dir.name)
        if not match:
            continue
        asset_name = match.group(1)
        runs.append({"assetName": asset_name, "runDir": run_dir})
    return runs


def apply_layouts(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    upgraded: list[dict[str, Any]] = []
    for run in runs:
        manifest = apply_layout(run["runDir"], run["assetName"], dry_run=False)
        run["layoutManifest"] = manifest
        upgraded.append(run)
    return upgraded


def status_for_run(run: dict[str, Any]) -> dict[str, Any]:
    run_dir = run["runDir"]
    asset_name = run["assetName"]
    fit = load_json(run_dir / "03_stage01_data" / f"{asset_name}_stage01_fit_qc.json")
    gate = load_json(run_dir / "03_stage01_data" / f"{asset_name}_stage01_skin_prep_gate.json")
    rig = load_json(run_dir / "03_stage01_data" / f"{asset_name}_rig_detail_review.json")
    visual = load_json(run_dir / "03_stage01_data" / f"{asset_name}_visual_qc.json")
    body = load_json(run_dir / "03_stage01_data" / f"{asset_name}_body_profile.json")
    slice_analysis = load_json(run_dir / "08_visual_review_evidence" / "slices" / "slice_analysis.json")

    refinement = fit.get("fitRefinement", {})
    if not isinstance(refinement, dict):
        refinement = {}
    blockers = gate.get("semanticSkinBlockers", [])
    if not isinstance(blockers, list):
        blockers = []
    visual_issues = visual.get("issues", [])
    if not isinstance(visual_issues, list):
        visual_issues = []
    ct_failures = int(slice_analysis.get("strictWrapFailureCount", 0) or 0)
    ct_failure_items = slice_analysis.get("strictWrapFailures", [])
    if not isinstance(ct_failure_items, list):
        ct_failure_items = []
    ct_segments = Counter(
        str(item.get("segment", "unknown"))
        for item in ct_failure_items
        if isinstance(item, dict)
    )
    ct_worst_segment = ""
    if ct_segments:
        segment, count = ct_segments.most_common(1)[0]
        ct_worst_segment = f"{segment} x{count}"

    return {
        "assetName": asset_name,
        "runDir": str(run_dir),
        "bodyType": gate.get("bodyType") or body.get("bodyType") or "unknown",
        "bipedFound": fit.get("bipedFound"),
        "mechanicalConverged": refinement.get("converged"),
        "fitIterations": refinement.get("iterations"),
        "initialFailures": refinement.get("initialFailures"),
        "finalFailures": refinement.get("finalFailures"),
        "ctSliceFailureCount": ct_failures,
        "ctWorstSegment": ct_worst_segment,
        "finalMaxDistance": refinement.get("finalMaxDistance") or fit.get("maxGuideNodeDistance"),
        "averageGuideNodeDistance": fit.get("averageGuideNodeDistance"),
        "stage01MechanicalHandoffReady": gate.get("stage01MechanicalHandoffReady"),
        "stage01HandoffReady": gate.get("stage01HandoffReady"),
        "skinSetupReady": gate.get("skinSetupReady"),
        "productionReady": gate.get("productionReady"),
        "semanticSkinReady": gate.get("semanticSkinReady"),
        "semanticSkinBlockerCount": len(blockers),
        "semanticSkinBlockerCodes": ", ".join(
            str(item.get("code", "unknown")) for item in blockers if isinstance(item, dict)
        ),
        "visualIssueCount": len(visual_issues),
        "rigDetailRiskCount": len(rig.get("semanticSkinReview", {}).get("risks", []))
        if isinstance(rig.get("semanticSkinReview"), dict)
        else "",
    }


def image_groups() -> list[dict[str, str]]:
    groups: list[dict[str, str]] = []

    for view in VIEWS:
        groups.append(
            {
                "phase": "01_qc_silhouette_views",
                "slug": f"qc_silhouette_{view}",
                "title": f"QC silhouette {view}",
                "source": f"05_qc_silhouette_views/{{asset}}_{view}.png",
                "why": "visual_qc 根据 snapshot 投影出来的估算/初筛图，用来看 Guide/Biped 是否明显偏离轮廓。",
            }
        )
    for view in VIEWS:
        groups.append(
            {
                "phase": "02_textured_model_views",
                "slug": f"textured_model_{view}",
                "title": f"Textured model {view}",
                "source": f"06_textured_model_views/{{asset}}_textured_{view}.png",
                "why": "带贴图三视图，用来理解服饰、头饰、脚尖、手端和装饰语义。",
            }
        )
    for view in VIEWS:
        groups.append(
            {
                "phase": "03_wire_bone_technical_views",
                "slug": f"wire_bone_{view}",
                "title": f"Wire/Bone technical {view}",
                "source": f"07_wire_bone_technical_views/{{asset}}_wire_bone_{view}.png",
                "why": "真实 3ds Max 线框 + Guide + 候选 Biped 技术视图，是检查候选骨架贴合的核心图。",
            }
        )
    for view in VIEWS:
        groups.append(
            {
                "phase": "04_visual_review_full",
                "slug": f"visual_review_full_{view}",
                "title": f"Visual review full {view}",
                "source": f"08_visual_review_evidence/full/{{asset}}_full_{view}.png",
                "why": "视觉语义证据包的全局图，适合和 wire/bone 图交叉确认估算是否追错轮廓。",
            }
        )

    regions = ["head", "pelvis", "left_hand", "right_hand", "left_foot", "right_foot"]
    for region in regions:
        for view in VIEWS:
            groups.append(
                {
                    "phase": "05_region_crops",
                    "slug": f"{region}_{view}",
                    "title": f"{region} {view}",
                    "source": f"08_visual_review_evidence/regions/{{asset}}_{region}_{view}.png",
                    "why": "高风险局部裁剪图，用来快速扫头、骨盆、手、脚这些估算最容易错的位置。",
                }
            )

    for view in VIEWS:
        groups.append(
            {
                "phase": "06_texture_semantic_evidence",
                "slug": f"semantic_textured_{view}",
                "title": f"Semantic textured {view}",
                "source": f"08_visual_review_evidence/semantic_analysis/{{asset}}_textured_semantic_{view}.png",
                "why": "贴图语义线索图，只说明纹理/轮廓依据，不证明骨架位置。",
            }
        )
        groups.append(
            {
                "phase": "06_texture_semantic_evidence",
                "slug": f"texture_wire_compare_{view}",
                "title": f"Texture/Wire compare {view}",
                "source": f"08_visual_review_evidence/semantic_analysis/{{asset}}_texture_wire_compare_{view}.png",
                "why": "贴图语义和真实 wire/bone 的配对图，用来判断语义线索是否真的被候选骨架采用。",
            }
        )

    slice_slugs = [
        "pelvis_spine",
        "spine_chest",
        "chest_neck",
        "neck_head",
        "chest_l_clavicle",
        "l_clavicle_l_shoulder",
        "l_shoulder_l_elbow",
        "l_elbow_l_wrist",
        "chest_r_clavicle",
        "r_clavicle_r_shoulder",
        "r_shoulder_r_elbow",
        "r_elbow_r_wrist",
        "pelvis_l_hip",
        "l_hip_l_knee",
        "l_knee_l_ankle",
        "l_ankle_l_toe",
        "pelvis_r_hip",
        "r_hip_r_knee",
        "r_knee_r_ankle",
        "r_ankle_r_toe",
    ]
    for slug in slice_slugs:
        groups.append(
            {
                "phase": "07_cross_section_slices",
                "slug": f"slice_{slug}",
                "title": f"Slice {slug}",
                "source": f"08_visual_review_evidence/slices/{{asset}}_slice_{slug}.png",
                "why": "CT 式逐关节截面，观察骨段中心是否被局部点云截面严格包裹。",
            }
        )
    return groups


def card_html(item: dict[str, Any], pack_dir: Path, image_rel: str) -> str:
    status = item.get("status", {})
    danger = ""
    if status.get("stage01MechanicalHandoffReady") is False or status.get("finalFailures") not in (0, None, ""):
        danger = " danger"
    elif status.get("semanticSkinBlockerCount", 0):
        danger = " warn"
    meta = (
        f"finalFailures={status.get('finalFailures')}, "
        f"maxDist={status.get('finalMaxDistance')}, "
        f"blockers={status.get('semanticSkinBlockerCount')}"
    )
    return (
        f'<article class="card{danger}">'
        f'<a href="{html.escape(image_rel)}"><img loading="lazy" src="{html.escape(image_rel)}" alt="{html.escape(item["assetName"])}"></a>'
        f'<h3>{html.escape(item["assetName"])}</h3>'
        f'<p>{html.escape(meta)}</p>'
        f'<p><a href="{html.escape(item["runReadme"])}">run README</a></p>'
        f"</article>"
    )


def status_border_color(status: dict[str, Any]) -> tuple[int, int, int]:
    if status.get("stage01MechanicalHandoffReady") is False or status.get("finalFailures") not in (0, None, ""):
        return (204, 64, 64)
    if status.get("semanticSkinBlockerCount", 0):
        return (220, 165, 40)
    return (42, 139, 78)


def fit_size(width: int, height: int, max_width: int, max_height: int) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        return (max_width, max_height)
    scale = min(max_width / width, max_height / height)
    return (max(1, int(width * scale)), max(1, int(height * scale)))


def draw_border(image: RgbImage, left: int, top: int, width: int, height: int, color: tuple[int, int, int]) -> None:
    image.rect(left, top, left + width - 1, top + height - 1, color, 3, 1.0)


def build_contact_sheet(group_dir: Path, group: dict[str, str], copied: list[dict[str, Any]]) -> dict[str, Any]:
    if not copied:
        return {"path": "", "positions": []}

    is_slice = group["phase"] == "07_cross_section_slices"
    tile_w = 680 if is_slice else 380
    tile_h = 170 if is_slice else 285
    cols = 2 if is_slice else 4
    gap = 16
    margin = 18
    rows = (len(copied) + cols - 1) // cols
    sheet_w = margin * 2 + cols * tile_w + (cols - 1) * gap
    sheet_h = margin * 2 + rows * tile_h + (rows - 1) * gap
    positions: list[dict[str, Any]] = []
    path = group_dir / "contact_sheet.png"

    if PILImage is not None and PILImageDraw is not None:
        sheet = PILImage.new("RGB", (sheet_w, sheet_h), (246, 246, 244))
        draw = PILImageDraw.Draw(sheet)
        resample = getattr(getattr(PILImage, "Resampling", PILImage), "LANCZOS", 1)
        for index, item in enumerate(copied, start=1):
            row = (index - 1) // cols
            col = (index - 1) % cols
            left = margin + col * (tile_w + gap)
            top = margin + row * (tile_h + gap)
            draw.rectangle(
                [left, top, left + tile_w - 1, top + tile_h - 1],
                outline=status_border_color(item["status"]),
                width=3,
            )
            ok = False
            try:
                with PILImage.open(item["sourcePath"]) as src:
                    thumb = src.convert("RGB")
                    thumb.thumbnail((tile_w - 8, tile_h - 8), resample=resample)
                    sheet.paste(thumb, (left + (tile_w - thumb.width) // 2, top + (tile_h - thumb.height) // 2))
                ok = True
            except Exception as exc:  # pragma: no cover - report generation should keep going.
                item["error"] = str(exc)
            positions.append(
                {
                    "index": index,
                    "row": row + 1,
                    "column": col + 1,
                    "assetName": item["assetName"],
                    "ok": ok,
                    "status": item["status"],
                    "source": item["source"],
                    "runReadme": item["runReadme"],
                }
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(path)
        return {"path": path, "positions": positions, "columns": cols, "tileWidth": tile_w, "tileHeight": tile_h}

    sheet = RgbImage.new(sheet_w, sheet_h, (246, 246, 244))

    for index, item in enumerate(copied, start=1):
        row = (index - 1) // cols
        col = (index - 1) % cols
        left = margin + col * (tile_w + gap)
        top = margin + row * (tile_h + gap)
        draw_border(sheet, left, top, tile_w, tile_h, status_border_color(item["status"]))
        try:
            src_image = RgbImage.from_png(Path(item["sourcePath"]))
            thumb_w, thumb_h = fit_size(src_image.width, src_image.height, tile_w - 8, tile_h - 8)
            thumb = src_image.resized_nearest(thumb_w, thumb_h)
            sheet.paste(thumb, left + (tile_w - thumb_w) // 2, top + (tile_h - thumb_h) // 2)
            ok = True
        except Exception as exc:  # pragma: no cover - report generation should keep going.
            ok = False
            item["error"] = str(exc)
        positions.append(
            {
                "index": index,
                "row": row + 1,
                "column": col + 1,
                "assetName": item["assetName"],
                "ok": ok,
                "status": item["status"],
                "source": item["source"],
                "runReadme": item["runReadme"],
            }
        )

    sheet.save_png(path)
    return {"path": path, "positions": positions, "columns": cols, "tileWidth": tile_w, "tileHeight": tile_h}


def html_page(title: str, body: str, depth: int = 0) -> str:
    prefix = "../" * depth
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: light dark; --bg:#f7f7f7; --fg:#202124; --muted:#626970; --card:#ffffff; --line:#d9dce0; --warn:#fff6d6; --danger:#ffe0e0; }}
    @media (prefers-color-scheme: dark) {{ :root {{ --bg:#141414; --fg:#eeeeee; --muted:#b6b6b6; --card:#1f1f1f; --line:#3a3a3a; --warn:#3a3218; --danger:#3b1e1e; }} }}
    body {{ margin:0; font:14px/1.5 system-ui, -apple-system, Segoe UI, sans-serif; background:var(--bg); color:var(--fg); }}
    header, main {{ max-width:1600px; margin:0 auto; padding:20px; }}
    header {{ border-bottom:1px solid var(--line); }}
    a {{ color:#2563eb; }}
    .muted {{ color:var(--muted); }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(260px, 1fr)); gap:14px; align-items:start; }}
    .card {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:10px; }}
    .card.warn {{ background:var(--warn); }}
    .card.danger {{ background:var(--danger); }}
    .card img {{ width:100%; max-height:360px; object-fit:contain; display:block; background:#111; border-radius:6px; }}
    .contact {{ width:100%; max-height:none; display:block; background:#111; border:1px solid var(--line); }}
    .card h3 {{ font-size:14px; margin:8px 0 4px; }}
    .card p {{ margin:4px 0; color:var(--muted); }}
    table {{ border-collapse:collapse; width:100%; background:var(--card); }}
    th, td {{ border:1px solid var(--line); padding:6px 8px; text-align:left; vertical-align:top; }}
    th {{ position:sticky; top:0; background:var(--card); }}
    code {{ font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }}
  </style>
</head>
<body>
<header>
  <p><a href="{prefix}index.html">返回总览</a></p>
  <h1>{html.escape(title)}</h1>
</header>
<main>
{body}
</main>
</body>
</html>
"""


def write_group(pack_dir: Path, group: dict[str, str], runs: list[dict[str, Any]], statuses: dict[str, dict[str, Any]]) -> dict[str, Any]:
    group_dir = pack_dir / group["phase"] / group["slug"]
    group_dir.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, Any]] = []
    missing: list[str] = []
    for index, run in enumerate(runs, start=1):
        asset = run["assetName"]
        src = run["runDir"] / group["source"].format(asset=asset)
        if src.exists():
            copied.append(
                {
                    "assetName": asset,
                    "source": rel(src, pack_dir),
                    "sourcePath": str(src),
                    "runReadme": rel(run["runDir"] / "README.md", group_dir),
                    "status": statuses.get(asset, {}),
                }
            )
        else:
            missing.append(asset)

    contact = build_contact_sheet(group_dir, group, copied)
    contact_rel = rel(contact["path"], group_dir) if contact.get("path") else ""
    rows = "\n".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td><code>{}</code></td><td><a href=\"{}\">run README</a></td></tr>".format(
            item["index"],
            item["row"],
            item["column"],
            html.escape(item["assetName"]),
            html.escape(item["runReadme"]),
        )
        for item in contact.get("positions", [])
    )
    body = "\n".join(
        [
            f"<p>{html.escape(group['why'])}</p>",
            f"<p class=\"muted\">模型数：{len(copied)}，缺失：{len(missing)}</p>",
            f'<p><a href="{html.escape(contact_rel)}"><img class="contact" src="{html.escape(contact_rel)}" alt="{html.escape(group["title"])} contact sheet"></a></p>' if contact_rel else "",
            "<table><thead><tr><th>#</th><th>Row</th><th>Col</th><th>Asset</th><th>Run</th></tr></thead><tbody>",
            rows,
            "</tbody></table>",
        ]
    )
    write_text(group_dir / "index.html", html_page(group["title"], body, depth=2))

    md_lines = [
        f"# {group['title']}",
        "",
        group["why"],
        "",
        f"- Collected: `{len(copied)}`",
        f"- Missing: `{len(missing)}`",
        f"- Contact sheet: `{contact_rel}`",
        f"- Sheet grid: `{contact.get('columns', '')}` columns, tile `{contact.get('tileWidth', '')}x{contact.get('tileHeight', '')}`",
        "",
        "| # | Row | Col | Asset | Run | Flags |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in contact.get("positions", []):
        status = item["status"]
        flags = []
        if status.get("stage01MechanicalHandoffReady") is False:
            flags.append("mechanical_blocked")
        if status.get("ctSliceFailureCount"):
            flags.append(f"ctFailures={status.get('ctSliceFailureCount')}")
        if status.get("finalFailures") not in (0, None, ""):
            flags.append(f"finalFailures={status.get('finalFailures')}")
        if status.get("semanticSkinBlockerCount"):
            flags.append(f"semanticBlockers={status.get('semanticSkinBlockerCount')}")
        md_lines.append(
            f"| {item['index']} | `{item['row']}` | `{item['column']}` | `{item['assetName']}` | `{item['runReadme']}` | `{', '.join(flags)}` |"
        )
    if missing:
        md_lines += ["", "## Missing", ""]
        for asset in missing:
            md_lines.append(f"- `{asset}`")
    write_text(group_dir / "index.md", "\n".join(md_lines) + "\n")

    return {
        "phase": group["phase"],
        "slug": group["slug"],
        "title": group["title"],
        "why": group["why"],
        "directory": rel(group_dir, pack_dir),
        "html": rel(group_dir / "index.html", pack_dir),
        "markdown": rel(group_dir / "index.md", pack_dir),
        "contactSheet": rel(contact["path"], pack_dir) if contact.get("path") else "",
        "collected": len(copied),
        "missing": missing,
    }


def write_status_tables(pack_dir: Path, statuses: list[dict[str, Any]]) -> None:
    table_dir = pack_dir / "00_status_tables"
    table_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "assetName",
        "bodyType",
        "mechanicalConverged",
        "fitIterations",
        "initialFailures",
        "finalFailures",
        "ctSliceFailureCount",
        "ctWorstSegment",
        "finalMaxDistance",
        "averageGuideNodeDistance",
        "stage01MechanicalHandoffReady",
        "stage01HandoffReady",
        "skinSetupReady",
        "productionReady",
        "semanticSkinBlockerCount",
        "semanticSkinBlockerCodes",
        "visualIssueCount",
        "rigDetailRiskCount",
        "runDir",
    ]
    csv_path = table_dir / "status.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in statuses:
            writer.writerow({key: row.get(key, "") for key in fieldnames})

    md_lines = [
        "# A1 Stage01 Status Table",
        "",
        "| Asset | Mechanical | CT failures | Worst CT segment | Internal failures | Max dist | Stage01 handoff | Skin setup | Semantic blockers |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in statuses:
        md_lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row.get("assetName"),
                row.get("stage01MechanicalHandoffReady"),
                row.get("ctSliceFailureCount"),
                row.get("ctWorstSegment"),
                row.get("finalFailures"),
                row.get("finalMaxDistance"),
                row.get("stage01HandoffReady"),
                row.get("skinSetupReady"),
                row.get("semanticSkinBlockerCount"),
            )
        )
    write_text(table_dir / "status.md", "\n".join(md_lines) + "\n")

    html_rows = "\n".join(
        "<tr>{}</tr>".format(
            "".join(
                f"<td>{html.escape(str(row.get(key, '')))}</td>"
                for key in [
                    "assetName",
                    "stage01MechanicalHandoffReady",
                    "ctSliceFailureCount",
                    "ctWorstSegment",
                    "finalFailures",
                    "finalMaxDistance",
                    "stage01HandoffReady",
                    "skinSetupReady",
                    "semanticSkinBlockerCount",
                    "semanticSkinBlockerCodes",
                ]
            )
        )
        for row in statuses
    )
    body = f"""
<p>这张表用于先定位机械失败和高风险 blocker。详细视觉检查请回到总览按图组打开。</p>
<p><a href="status.csv">下载 CSV</a></p>
<table>
<thead><tr><th>Asset</th><th>Mechanical</th><th>CT failures</th><th>Worst CT segment</th><th>Internal failures</th><th>Max dist</th><th>Stage01 handoff</th><th>Skin setup</th><th>Blockers</th><th>Blocker codes</th></tr></thead>
<tbody>
{html_rows}
</tbody>
</table>
"""
    write_text(table_dir / "index.html", html_page("A1 Stage01 Status Table", body, depth=1))


def write_root_docs(pack_dir: Path, runs: list[dict[str, Any]], statuses: list[dict[str, Any]], group_results: list[dict[str, Any]]) -> None:
    mechanical_blocked = [row for row in statuses if row.get("stage01MechanicalHandoffReady") is False]
    nonzero_failures = [row for row in statuses if row.get("finalFailures") not in (0, None, "")]
    ct_blocked = [row for row in statuses if int(row.get("ctSliceFailureCount") or 0) > 0]
    total_images = sum(group["collected"] for group in group_results)
    missing_count = sum(len(group["missing"]) for group in group_results)

    phase_map: dict[str, list[dict[str, Any]]] = {}
    for group in group_results:
        phase_map.setdefault(group["phase"], []).append(group)

    link_lines: list[str] = []
    for phase, groups in phase_map.items():
        link_lines.append(f"<h2>{html.escape(phase)}</h2>")
        link_lines.append("<ul>")
        for group in groups:
            link_lines.append(
                f'<li><a href="{html.escape(group["html"])}">{html.escape(group["title"])}</a> '
                f'<span class="muted">({group["collected"]} images)</span></li>'
            )
        link_lines.append("</ul>")

    body = "\n".join(
        [
            "<p>这个包把 A1 批量 Stage01 输出按“同一种图横向看所有模型”的方式重新收集，方便一次性扫估算和候选 Biped 的整体问题。</p>",
            "<h2>先看哪里</h2>",
            "<ol>",
            '<li><a href="03_wire_bone_technical_views/wire_bone_front/index.html">wire/bone front 全模型</a></li>',
            '<li><a href="03_wire_bone_technical_views/wire_bone_side/index.html">wire/bone side 全模型</a></li>',
            '<li><a href="04_visual_review_full/visual_review_full_front/index.html">visual review full front 全模型</a></li>',
            '<li><a href="05_region_crops/pelvis_front/index.html">pelvis front 全模型</a></li>',
            '<li><a href="05_region_crops/head_side/index.html">head side 全模型</a></li>',
            '<li><a href="00_status_tables/index.html">状态表</a></li>',
            "</ol>",
            "<h2>本包状态</h2>",
            f"<p>模型数：{len(runs)}；已复制图：{total_images}；缺失图引用：{missing_count}。</p>",
            f"<p>机械 handoff 未通过：{len(mechanical_blocked)}；CT strict failures 非 0：{len(ct_blocked)}；internal final failures 非 0：{len(nonzero_failures)}。</p>",
            "<h2>所有图组</h2>",
            "\n".join(link_lines),
        ]
    )
    write_text(pack_dir / "index.html", html_page("A1 Stage01 All Models Visual Audit", body, depth=0))

    readme_lines = [
        "# A1 Stage01 All Models Visual Audit",
        "",
        "这个目录是从 `out/runs/a1_*` 单独整理出来的横向复查包。它不替代原始 run，只复制关键图片和生成索引，方便一次性扫全量模型。",
        "",
        "## 先看哪里",
        "",
        "- `index.html`：浏览器总入口。",
        "- `00_status_tables/status.md` / `status.csv`：机械收敛、handoff、blocker 表。",
        "- `03_wire_bone_technical_views/wire_bone_front/index.html`：所有模型真实 Max 线框+候选 Biped 前视。",
        "- `03_wire_bone_technical_views/wire_bone_side/index.html`：所有模型真实 Max 线框+候选 Biped 侧视。",
        "- `04_visual_review_full/visual_review_full_front/index.html`：所有模型投影证据全局前视。",
        "- `05_region_crops/`：头、骨盆、手、脚局部横向对比。",
        "- 每个图组只保留 `contact_sheet.png` 一张大图；具体行列和资产名看同目录 `index.md`。",
        "",
        "## 怎样解读",
        "",
        "- `01_qc_silhouette_views`：估算阶段的投影初筛，能快速看 Guide/Biped 是否明显错位。",
        "- `03_wire_bone_technical_views`：真实 3ds Max 技术截图，是看候选 Biped 的主证据。",
        "- `02_textured_model_views`：贴图语义上下文，帮助判断骨骼是否追错头饰、披风、裙摆或武器。",
        "- `05_region_crops`：优先扫骨盆、头、手、脚，这些最容易在估算阶段错。",
        "- `07_cross_section_slices`：看骨段中心是否落在局部体积里。",
        "",
        "## 当前概况",
        "",
        f"- 模型数：`{len(runs)}`",
        f"- 已复制图片数：`{total_images}`",
        f"- 缺失图引用数：`{missing_count}`",
        f"- 机械 handoff 未通过：`{len(mechanical_blocked)}`",
        f"- CT strict failures 非 0：`{len(ct_blocked)}`",
        f"- internal final failures 非 0：`{len(nonzero_failures)}`",
        "",
    ]
    if mechanical_blocked:
        readme_lines += ["### 机械 handoff 未通过", ""]
        for row in mechanical_blocked:
            readme_lines.append(
                f"- `{row['assetName']}` ctFailures=`{row.get('ctSliceFailureCount')}`, worstCt=`{row.get('ctWorstSegment')}`, internalFinalFailures=`{row.get('finalFailures')}`, maxDist=`{row.get('finalMaxDistance')}`"
            )
        readme_lines.append("")
    readme_lines += ["## 图组索引", ""]
    for group in group_results:
        readme_lines.append(f"- `{group['title']}`: `{group['html']}`")
    write_text(pack_dir / "README.md", "\n".join(readme_lines) + "\n")


def build_report(out_dir: Path, report_root: Path, pack_name: str, apply_numbered_layout: bool) -> dict[str, Any]:
    runs = discover_runs(out_dir)
    if apply_numbered_layout:
        runs = apply_layouts(runs)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pack_dir = report_root / (pack_name or f"a1_stage01_visual_audit_{timestamp}")
    clean_dir(pack_dir)

    statuses = [status_for_run(run) for run in runs]
    status_map = {row["assetName"]: row for row in statuses}
    write_status_tables(pack_dir, statuses)

    group_results: list[dict[str, Any]] = []
    for group in image_groups():
        group_results.append(write_group(pack_dir, group, runs, status_map))

    write_root_docs(pack_dir, runs, statuses, group_results)
    manifest = {
        "ok": True,
        "layoutVersion": LAYOUT_VERSION,
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "outDir": str(out_dir),
        "reportRoot": str(report_root),
        "packDir": str(pack_dir),
        "runCount": len(runs),
        "imageCount": sum(group["collected"] for group in group_results),
        "missingImageCount": sum(len(group["missing"]) for group in group_results),
        "groups": group_results,
        "statuses": statuses,
    }
    write_text(pack_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    latest = report_root / "latest_a1_stage01_visual_audit.md"
    write_text(
        latest,
        "\n".join(
            [
                "# Latest A1 Stage01 Visual Audit",
                "",
                f"- Pack: `{pack_dir.name}`",
                f"- HTML index: `{pack_dir.name}/index.html`",
                f"- README: `{pack_dir.name}/README.md`",
                f"- Run count: `{len(runs)}`",
                f"- Image count: `{manifest['imageCount']}`",
            ]
        )
        + "\n",
    )
    return manifest


def main() -> int:
    tool_root = Path(__file__).resolve().parents[1]
    default_out_dir = os.environ.get("AIRA_OUT_DIR", str(tool_root / "out"))
    default_report_root = os.environ.get("AIRA_REPORT_ROOT", str(tool_root / "report"))
    parser = argparse.ArgumentParser(description="Build an all-model Stage01 visual audit report pack for A1 runs.")
    parser.add_argument("--out-dir", default=default_out_dir)
    parser.add_argument("--report-root", default=default_report_root)
    parser.add_argument("--pack-name", default="")
    parser.add_argument("--skip-layout", action="store_true", help="Do not apply numbered layout before collecting images.")
    args = parser.parse_args()

    manifest = build_report(
        Path(args.out_dir),
        Path(args.report_root),
        args.pack_name,
        apply_numbered_layout=not args.skip_layout,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
