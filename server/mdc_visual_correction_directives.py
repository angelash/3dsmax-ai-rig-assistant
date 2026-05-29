from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
    return data if isinstance(data, dict) else {}


def clean(value: Any) -> str:
    return str(value if value is not None else "").replace("\t", " ").replace("\r", " ").replace("\n", " ")


def point(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    try:
        return [float(value[0]), float(value[1]), float(value[2])]
    except (TypeError, ValueError):
        return None


def eligible_actions(plan: dict[str, Any], *, include_needs_more_views: bool = False) -> list[dict[str, Any]]:
    summary = plan.get("summary") or {}
    if summary.get("needsMoreViews") is True and not include_needs_more_views:
        return []
    rows = []
    for action in plan.get("actions") or []:
        if not isinstance(action, dict):
            continue
        if action.get("autoApplyEligibleAfterBridge") is not True:
            continue
        target = point(action.get("target"))
        if target is None:
            continue
        apply_to = action.get("applyTo") or []
        if "guide" not in apply_to and "guideIfPresent" not in apply_to:
            continue
        rows.append(action)
    return rows


def write_tsv(path: Path, plan: dict[str, Any], actions: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "targetName",
                "targetKind",
                "targetX",
                "targetY",
                "targetZ",
                "maxSingleStep",
                "actionId",
                "kind",
                "rule",
                "sourceChecks",
            ]
        )
        for action in actions:
            target = point(action.get("target")) or [0.0, 0.0, 0.0]
            writer.writerow(
                [
                    clean(action.get("targetName")),
                    clean(action.get("targetKind")),
                    f"{target[0]:.6f}",
                    f"{target[1]:.6f}",
                    f"{target[2]:.6f}",
                    f"{float(action.get('maxSingleStep') or 0.0):.6f}",
                    clean(action.get("id")),
                    clean(action.get("kind")),
                    clean(action.get("rule")),
                    clean(",".join(str(item) for item in (action.get("sourceChecks") or []))),
                ]
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert an MDC visual correction plan into MaxScript-friendly guide directives.")
    parser.add_argument("plan_json", type=Path)
    parser.add_argument("--out-tsv", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, default=None)
    parser.add_argument("--include-needs-more-views", action="store_true")
    args = parser.parse_args()

    plan = load_json(args.plan_json)
    actions = eligible_actions(plan, include_needs_more_views=args.include_needs_more_views)
    write_tsv(args.out_tsv, plan, actions)
    summary = {
        "ok": True,
        "assetName": plan.get("assetName") or "",
        "planJson": str(args.plan_json),
        "directivesTsv": str(args.out_tsv),
        "eligibleActionCount": len(actions),
        "planStatus": (plan.get("summary") or {}).get("planStatus") or "",
        "needsMoreViews": (plan.get("summary") or {}).get("needsMoreViews") is True,
        "policy": "Guide-only bounded correction directives for the next Stage01 run.",
    }
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
