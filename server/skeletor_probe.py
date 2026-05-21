from __future__ import annotations

import argparse
import json
from pathlib import Path

import networkx as nx
import skeletor
import trimesh


METHODS = {
    "vertex_clusters": (skeletor.skeletonize.by_vertex_clusters, {"sampling_dist": 8, "progress": False}),
    "wavefront": (skeletor.skeletonize.by_wavefront, {"step_size": 8, "progress": False}),
    "edge_collapse": (skeletor.skeletonize.by_edge_collapse, {"progress": False}),
}


def graph_stats(edges: list[list[int]] | object) -> dict[str, int]:
    graph = nx.Graph()
    for a, b in edges:
        graph.add_edge(int(a), int(b))
    components = list(nx.connected_components(graph))
    leaves = [node for node, degree in graph.degree() if degree == 1]
    branch_nodes = [node for node, degree in graph.degree() if degree >= 3]
    return {
        "graphNodes": graph.number_of_nodes(),
        "graphEdges": graph.number_of_edges(),
        "connectedComponents": len(components),
        "leafCount": len(leaves),
        "branchNodeCount": len(branch_nodes),
    }


def suitability(mesh: trimesh.Trimesh, stats: dict[str, int]) -> tuple[int, list[str]]:
    score = 100
    notes: list[str] = []
    mesh_components = len(mesh.split(only_watertight=False))
    if not mesh.is_watertight:
        score -= 25
        notes.append("Input mesh is not watertight; curve skeletonization may follow open borders and accessories.")
    if mesh_components > 1:
        penalty = min(35, mesh_components // 10)
        score -= penalty
        notes.append(f"Input mesh has {mesh_components} connected components; this usually means decorations/accessories will fragment the skeleton.")
    if stats["connectedComponents"] > 1:
        score -= min(30, stats["connectedComponents"] * 3)
        notes.append(f"Skeleton graph has {stats['connectedComponents']} connected components; not usable as one animation hierarchy without post-processing.")
    if stats["leafCount"] > 16:
        score -= min(20, stats["leafCount"] - 16)
        notes.append(f"Skeleton has {stats['leafCount']} leaves; likely captures mesh detail/decorations instead of a clean animator skeleton.")
    if score < 0:
        score = 0
    if not notes:
        notes.append("Geometry skeleton is coherent enough for downstream landmark hints.")
    return score, notes


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe skeletor geometry skeletonization for one OBJ.")
    parser.add_argument("obj")
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--asset-name", default="")
    args = parser.parse_args()

    obj_path = Path(args.obj)
    out_dir = Path(args.out_dir) if args.out_dir else obj_path.parent
    asset_name = args.asset_name or obj_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    mesh = trimesh.load(obj_path, force="mesh")
    mesh_components = len(mesh.split(only_watertight=False))
    results = []

    for method_name, (fn, kwargs) in METHODS.items():
        try:
            skeleton = fn(mesh, **kwargs)
            vertices = getattr(skeleton, "vertices", [])
            edges = getattr(skeleton, "edges", [])
            stats = graph_stats(edges)
            score, notes = suitability(mesh, stats)
            results.append(
                {
                    "method": method_name,
                    "ok": True,
                    "suitabilityScore": score,
                    "vertexCount": int(len(vertices)),
                    **stats,
                    "notes": notes,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "method": method_name,
                    "ok": False,
                    "suitabilityScore": 0,
                    "error": f"{type(exc).__name__}: {exc}",
                    "notes": ["Method failed on this mesh."],
                }
            )

    payload = {
        "assetName": asset_name,
        "obj": str(obj_path),
        "mesh": {
            "vertexCount": int(len(mesh.vertices)),
            "faceCount": int(len(mesh.faces)),
            "isWatertight": bool(mesh.is_watertight),
            "connectedComponents": mesh_components,
        },
        "results": results,
    }

    json_path = out_dir / f"{asset_name}_skeletor_probe.json"
    md_path = out_dir / f"{asset_name}_skeletor_probe.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# Skeletor Probe: {asset_name}",
        "",
        f"- OBJ: `{obj_path}`",
        f"- Mesh vertices: `{len(mesh.vertices)}`",
        f"- Mesh faces: `{len(mesh.faces)}`",
        f"- Watertight: `{mesh.is_watertight}`",
        f"- Connected components: `{mesh_components}`",
        "",
        "| Method | OK | Score | Vertices | Edges | Components | Leaves | Branches |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in results:
        lines.append(
            f"| {item['method']} | {item['ok']} | {item['suitabilityScore']} | "
            f"{item.get('vertexCount', 0)} | {item.get('graphEdges', 0)} | "
            f"{item.get('connectedComponents', 0)} | {item.get('leafCount', 0)} | {item.get('branchNodeCount', 0)} |"
        )
    lines.extend(["", "## Notes", ""])
    for item in results:
        lines.append(f"### {item['method']}")
        lines.append("")
        for note in item.get("notes", []):
            lines.append(f"- {note}")
        if not item.get("ok", False):
            lines.append(f"- Error: `{item.get('error', '')}`")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({"ok": True, "json": str(json_path), "markdown": str(md_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
