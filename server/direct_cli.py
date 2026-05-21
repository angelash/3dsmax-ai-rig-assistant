from __future__ import annotations

import argparse
import json

from max_bridge_client import send_bridge_command


COMMANDS = [
    "ping",
    "stage01_load_tool",
    "stage01_create_guides",
    "stage01_mirror_guides",
    "stage01_create_biped",
    "stage01_fit_biped",
    "stage01_generate_report",
    "stage01_generate_fit_qc",
    "stage01_save_file",
    "stage01_auto_pipeline",
    "asset_qc_current_scene",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Call the local 3ds Max AIRA bridge directly.")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=37820)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    result = send_bridge_command(args.command, args.host, args.port, args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
