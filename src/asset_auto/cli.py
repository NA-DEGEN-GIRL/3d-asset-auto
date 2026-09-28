import argparse
import json
import os
import shlex
import sys
from pathlib import Path

from . import jobs
from .models import AssessmentRequest, AssetSpec, EditRequest, KimodoMotionRequest
from .pipeline import (
    edit_asset,
    generate,
    postprocess,
    postprocess_plan,
    resume_postprocess,
    resume_tripo,
    review,
    validate_godot,
)
from .settings import capabilities, root_path
from .store import Store, read_json


def main():
    parser = argparse.ArgumentParser(prog="assetctl")
    parser.add_argument("--root", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    resource_command = commands.add_parser("resources", help="Inspect private host policy or run a guarded command")
    resource_command.add_argument("--runtime", choices=("trellis", "kimodo", "local_rig", "local_parts", "blender"))
    resource_mode = resource_command.add_mutually_exclusive_group()
    resource_mode.add_argument("--shell-prefix", action="store_true")
    resource_mode.add_argument("--exec", dest="execute", action="store_true")
    resource_command.add_argument("argv", nargs=argparse.REMAINDER)
    commands.add_parser("list")
    commands.add_parser("tripo-balance")
    command = commands.add_parser("tripo-plan")
    command.add_argument("spec", type=Path)
    command = commands.add_parser("text-motion-plan")
    command.add_argument("spec", type=Path)
    command = commands.add_parser("compare-animations")
    command.add_argument("spec", type=Path)
    for operation in ("process-plan", "tripo-process-plan"):
        command = commands.add_parser(operation)
        command.add_argument("spec", type=Path)
    command = commands.add_parser("resume-tripo")
    command.add_argument("asset_id")
    command.add_argument("revision")
    command.add_argument("--async", dest="background", action="store_true")
    for operation in ("resume-process", "resume-tripo-process", "prepare-segment", "resume-text-motion", *jobs.AUTHORING_RESUMES):
        command = commands.add_parser(operation)
        command.add_argument("asset_id")
        command.add_argument("revision")
        command.add_argument("--async", dest="background", action="store_true")
    for operation in ("generate", "edit", "process", "tripo-process", "assess", "text-motion", *jobs.AUTHORING_MODELS):
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
        from . import resources

        # Jobs apply inside their error-recording scope; read-only resource
        # inspection reports current process state without changing it.
        if args.command not in ("_worker", "resources"):
            resources.apply_process_resources(root)
        if args.command == "resources":
            if args.execute or args.shell_prefix:
                if not args.runtime:
                    raise ValueError("--runtime is required for guarded execution or a shell prefix")
                if args.shell_prefix:
                    prefix = [sys.executable, "-m", "asset_auto.cli", "--root", str(root),
                              "resources", "--runtime", args.runtime, "--exec", "--"]
                    print("& " + " ".join("'" + part.replace("'", "''") + "'" for part in prefix)
                          if os.name == "nt" else shlex.join(prefix))
                    return 0
                from .runtime_execution import run

                command = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
                if not command:
                    raise ValueError("Provide an executable command after --exec --")
                run(root, args.runtime, command)
                return 0
            if args.argv:
                raise ValueError("Extra command arguments require --exec")
            result = resources.runtime_check(root, args.runtime) if args.runtime else resources.describe(root)
        elif args.command == "doctor":
            result = capabilities(root)
        elif args.command == "list":
            result = Store(root).list()
        elif args.command == "compare-animations":
            from .animation_compare import compare_request
            from .models import AnimationComparisonRequest

            result = compare_request(root, AnimationComparisonRequest.model_validate(read_json(args.spec)))
        elif args.command in ("text-motion-plan", "text-motion"):
            from . import text_motion

            request = KimodoMotionRequest.model_validate(read_json(args.spec))
            if args.command == "text-motion-plan":
                result = text_motion.plan(root, request)
            elif args.background:
                result = jobs.submit(root, "text-motion", request.model_dump())
            else:
                result = text_motion.generate(root, request)
        elif args.command == "resume-text-motion":
            from . import text_motion

            payload = {"asset_id": args.asset_id, "revision": args.revision}
            result = jobs.submit(root, args.command, payload) if args.background else text_motion.resume(root, **payload)
        elif args.command == "assess":
            from .assessment import assess

            request = AssessmentRequest.model_validate(read_json(args.spec))
            result = jobs.submit(root, "assess", request.model_dump()) if args.background else assess(root, request)
        elif args.command == "tripo-balance":
            from .tripo import TripoClient

            result = TripoClient(root).balance()
        elif args.command == "tripo-plan":
            from .tripo import plan

            result = plan(root, AssetSpec.model_validate(read_json(args.spec)))
        elif args.command in ("process-plan", "tripo-process-plan"):
            request = jobs.processing_request(read_json(args.spec), tripo_only=args.command == "tripo-process-plan")
            result = postprocess_plan(root, request)
        elif args.command in ("process", "tripo-process"):
            request = jobs.processing_request(read_json(args.spec), tripo_only=args.command == "tripo-process")
            result = jobs.submit(root, args.command, request.model_dump()) if args.background else postprocess(root, request)
        elif args.command in jobs.AUTHORING_MODELS:
            request = jobs.AUTHORING_MODELS[args.command].model_validate(read_json(args.spec))
            if args.background:
                result = jobs.submit(root, args.command, request.model_dump())
            else:
                from .authoring import edit_in_blender, merge_animations

                author = edit_in_blender if args.command == "blender-edit" else merge_animations
                result = author(root, request)
        elif args.command in jobs.AUTHORING_RESUMES:
            payload = {"asset_id": args.asset_id, "revision": args.revision}
            if args.background:
                result = jobs.submit(root, args.command, payload)
            else:
                from .authoring import resume_authoring, validate_resume

                operation = jobs.AUTHORING_RESUMES[args.command]
                validate_resume(root, **payload, operation=operation)
                result = resume_authoring(root, **payload, operation=operation)
        elif args.command in ("resume-process", "resume-tripo-process"):
            payload = {"asset_id": args.asset_id, "revision": args.revision}
            if args.command == "resume-tripo-process":
                jobs.validate_processing_resume(root, payload, tripo_only=True)
            result = jobs.submit(root, args.command, payload) if args.background else resume_postprocess(root, **payload)
        elif args.command == "prepare-segment":
            from .pipeline import prepare_segmentation

            payload = {"asset_id": args.asset_id, "revision": args.revision}
            result = jobs.submit(root, args.command, payload) if args.background else prepare_segmentation(root, **payload)
        elif args.command == "resume-tripo":
            if args.background:
                result = jobs.submit(root, "resume-tripo", {"asset_id": args.asset_id, "revision": args.revision})
            else:
                result = resume_tripo(root, args.asset_id, args.revision)
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
