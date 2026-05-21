from __future__ import annotations

import argparse
import base64
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REVIEW_IMAGE_KEYS = [
    "wire_bone_front",
    "wire_bone_side",
    "wire_bone_top",
    "texture_wire_compare_front",
    "texture_wire_compare_side",
    "texture_wire_compare_top",
    "pelvis_front",
    "pelvis_side",
    "pelvis_top",
    "left_foot_side",
    "left_foot_top",
    "right_foot_side",
    "right_foot_top",
    "left_hand_front",
    "left_hand_top",
    "right_hand_front",
    "right_hand_top",
    "head_front",
    "head_side",
    "slice_pelvis_spine",
    "slice_l_knee_l_ankle",
    "slice_r_knee_r_ankle",
    "slice_l_ankle_l_toe",
    "slice_r_ankle_r_toe",
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))


def data_url(path: Path) -> str:
    suffix = path.suffix.lower()
    mime = "image/png"
    if suffix in {".jpg", ".jpeg"}:
        mime = "image/jpeg"
    elif suffix == ".webp":
        mime = "image/webp"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def resolve_image(run_dir: Path, relative_path: str) -> Path | None:
    if not relative_path:
        return None
    path = (run_dir / relative_path).resolve()
    try:
        path.relative_to(run_dir.resolve())
    except ValueError:
        return None
    return path if path.exists() else None


def extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def response_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    chunks: list[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks)


def build_prompt(asset_name: str, review_input: str, schema: dict[str, Any]) -> str:
    return "\n".join(
        [
            "You are reviewing a 3ds Max Biped Stage01 rig against a tutorial-style manual matching process.",
            "Use the images as the source of truth. Numeric diagnostics are evidence only.",
            "Decide whether the Biped wraps the character in front, side, and top views.",
            "Return ONLY a JSON object matching this schema. Do not add markdown.",
            "",
            f"Asset: {asset_name}",
            "",
            "Required behavior:",
            "- Every check must be pass, blocker, needs_detail, uncertain, or not_visible.",
            "- Use pass only when the evidence clearly supports it.",
            "- Use block_until_fixed unless all hard wrapping and semantic checks pass.",
            "- Mention concrete view-based evidence in comments.",
            "",
            "Schema:",
            json.dumps(schema, ensure_ascii=False, indent=2),
            "",
            "Review input:",
            review_input,
        ]
    )


def call_openai_responses(*, api_key: str, model: str, prompt: str, image_paths: list[Path]) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
    for path in image_paths:
        content.append({"type": "input_image", "image_url": data_url(path), "detail": "high"})

    body = {
        "model": model,
        "input": [{"role": "user", "content": content}],
        "max_output_tokens": 4000,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI Responses API failed: {exc.code} {detail}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Run VLM front/side/top Stage01 Biped signoff.")
    parser.add_argument("--manifest-json", required=True)
    parser.add_argument("--review-input", default="")
    parser.add_argument("--schema-json", default="")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--model", default=os.environ.get("AIRA_VLM_MODEL", "gpt-4.1"))
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--allow-missing-api-key", action="store_true")
    args = parser.parse_args()

    manifest_path = Path(args.manifest_json).resolve()
    run_dir = manifest_path.parents[1]
    manifest = load_json(manifest_path)
    images = manifest.get("images", {})

    review_input_path = Path(args.review_input).resolve() if args.review_input else run_dir / "visual_review" / "review_input.md"
    schema_path = Path(args.schema_json).resolve() if args.schema_json else run_dir / "visual_review" / "review_schema.json"
    out_path = Path(args.out_json).resolve() if args.out_json else run_dir / "visual_review" / f"{manifest.get('assetName', 'stage01')}_semantic_visual_review_vlm.json"

    api_key = os.environ.get(args.api_key_env, "")
    if not api_key:
        if args.allow_missing_api_key:
            print(json.dumps({"ok": False, "skipped": True, "reason": f"{args.api_key_env} is not set"}, ensure_ascii=False))
            return 0
        raise RuntimeError(f"{args.api_key_env} is not set")

    image_paths: list[Path] = []
    for key in REVIEW_IMAGE_KEYS:
        path = resolve_image(run_dir, images.get(key, ""))
        if path is not None:
            image_paths.append(path)

    if not image_paths:
        raise RuntimeError("No review images were found in the visual review manifest.")

    schema = load_json(schema_path)
    review_input = review_input_path.read_text(encoding="utf-8-sig", errors="replace")
    prompt = build_prompt(str(manifest.get("assetName", "")), review_input, schema)
    raw_response = call_openai_responses(api_key=api_key, model=args.model, prompt=prompt, image_paths=image_paths)
    review = extract_json(response_text(raw_response))
    out_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "assetName": manifest.get("assetName", ""),
                "model": args.model,
                "imagesUsed": len(image_paths),
                "json": str(out_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
