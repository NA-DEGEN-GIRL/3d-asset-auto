import argparse
import json
import sys
from pathlib import Path

from . import jobs
from .models import AssetSpec, EditRequest
from .pipeline import edit_asset, generate, review, validate_godot
from .settings import capabilities, root_path
from .store import Store, read_json


def main():
    parser = argparse.ArgumentParser(prog="assetctl")
    parser.add_argument("--root", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    commands.add_parser("list")
    for operation in ("generate", "edit"):
        command = commands.add_parser(operation)
        command.add_argument("spec", type=Path)
        command.add_argument("--async", dest="background", action="store_true")
    for operation in ("inspect", "godot", "review"):
        command = commands.add_parser(operation)
        command.add_argument("asset_id")
        command.add_argument("revision")
        if operation == "review":
            command.add_argument("--result", choices=["pass", "fail"], required=True)
            command.add_argument("--notes", required=True)
    for operation in ("job", "_worker"):
        command = commands.add_parser(operation)
        command.add_argument("job_id")
    command = commands.add_parser("serve")
    command.add_argument("--port", type=int, default=8765)
    commands.add_parser("mcp")
    args = parser.parse_args()
    root = args.root.resolve() if args.root else root_path()
    try:
        if args.command == "doctor":
            result = capabilities(root)
        elif args.command == "list":
            result = Store(root).list()
        elif args.command in ("generate", "edit"):
            payload = read_json(args.spec)
            if args.background:
                result = jobs.submit(root, args.command, payload)
            elif args.command == "generate":
                result = generate(root, AssetSpec.model_validate(payload))
            else:
                result = edit_asset(root, EditRequest.model_validate(payload))
        elif args.command == "inspect":
            result = read_json(Store(root).revision(args.asset_id, args.revision) / "inspection.json")
        elif args.command == "godot":
            result = validate_godot(root, args.asset_id, args.revision)
        elif args.command == "review":
            result = review(root, args.asset_id, args.revision, args.result == "pass", args.notes)
        elif args.command == "job":
            result = jobs.status(root, args.job_id)
        elif args.command == "_worker":
            result = jobs.run(root, args.job_id)
            if result["state"] == "failed":
                print(json.dumps(result, ensure_ascii=False))
                return 1
        elif args.command == "mcp":
            from .mcp_server import serve

            serve(root)
            return 0
        else:
            import uvicorn

            from .web import create_app

            uvicorn.run(create_app(root), host="127.0.0.1", port=args.port)
            return 0
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, OSError, RuntimeError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
