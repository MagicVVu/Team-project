"""Run from the existing agent directory: python -m jev --help."""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from .budget import Budget
from .config import Config, MODEL, CACHE
from .engine import Engine
from .evaluation import load_dataset, evaluate, write_reports
from .providers import MockProvider, ReplayProvider, LiveProvider
from .schemas import DecisionRequest, NodeState, Node, JevError


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def make_provider(name):
    if name == "live":
        config = Config.from_environment()
        config.require_live()
        return LiveProvider(config)
    return ReplayProvider() if name == "replay" else MockProvider()


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def execute_local(args):
    if args.command == "check":
        config = Config.from_environment()
        samples = load_dataset()
        emit({"model": MODEL, "live_key_present": bool(config.api_key), "network_requested": False,
              "samples": len(samples), "budget": Budget().summary(), "production_integration": False})
        return 0
    if args.command == "budget":
        emit(Budget().summary())
        return 0
    if args.command == "report":
        emit(write_reports(read_json(args.input), args.output))
        return 0


async def execute(args):
    engine = Engine(make_provider(args.provider))
    if args.command in {"decide", "node"}:
        raw = read_json(args.input)
        if args.command == "node":
            state = NodeState.model_validate(raw) if "request" in raw else NodeState(request=DecisionRequest.model_validate(raw))
            result = await engine.evaluate_node(Node(args.name), state)
        else:
            result = await engine.evaluate(DecisionRequest.model_validate(raw))
        emit(result.model_dump(mode="json"))
        return 1 if result.status == "unavailable" else 0
    run = await evaluate(engine, load_dataset(args.dataset), split=args.split)
    output = Path(args.output) if args.output else CACHE / "reports" / (args.provider + "-" + args.split + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    report = write_reports(run, output)
    emit({"output": str(output.resolve()), "summary": report})
    return 1 if not report["all_completed"] or report["unavailable"] else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Opt-in Jev household decision lab; defaults to offline mock.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="Inspect config/data/budget without a model request")
    commands.add_parser("budget", help="Read the persistent USD ledger without creating it")
    for name in ("decide", "node", "evaluate"):
        sub = commands.add_parser(name)
        sub.add_argument("--provider", choices=["mock", "replay", "live"], default="mock")
        if name == "evaluate":
            sub.add_argument("--split", choices=["dev", "calibration", "test", "all"], default="dev")
            sub.add_argument("--dataset")
            sub.add_argument("--output")
        else:
            sub.add_argument("--input", required=True, help="Synthetic request JSON, or NodeState JSON for downstream node debugging")
        if name == "node":
            sub.add_argument("name", choices=[n.value for n in Node])
    report = commands.add_parser("report")
    report.add_argument("--input", required=True, help="An existing evaluation run.json")
    report.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command in {"check", "budget", "report"}:
            return execute_local(args)
        return asyncio.run(execute(args))
    except JevError as error:
        emit({"error_code": error.code})
        return 1
    except (ValueError, ValidationError, OSError, KeyError, TypeError):
        # Do not echo a Pydantic error containing the original input or HTTP contents.
        emit({"error_code": "INVALID_INPUT_OR_LOCAL_FILE"})
        return 2


if __name__ == "__main__":
    sys.exit(main())
