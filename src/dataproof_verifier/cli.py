"""Small offline command-line interface for NoUndo."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from dataproof_verifier import doppel_cli, join_cli, preflight, proof2test
from dataproof_verifier import explain as explanation
from dataproof_verifier.artifacts import ArtifactConflict, finish, prepare
from dataproof_verifier.ir import Query
from dataproof_verifier.models import Spec, SpecError, UnsupportedError, load_spec, output_dir_hint
from dataproof_verifier.parser import parse_query
from dataproof_verifier.replay import validate, validate_serialized
from dataproof_verifier.report import result_data, sha256_file, write_result, write_witness
from dataproof_verifier.solver import search
from dataproof_verifier.status import EXIT_CODES


def _emit(result: dict[str, Any], machine: bool) -> None:
    if machine:
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
    else:
        print(result["status"])
        if result.get("reason"):
            print(result["reason"])
        if result.get("witness_path"):
            print(f"witness: {result['witness_path']}")
            print(f"replay SQL: {result['replay_sql_path']}")


def check(path: Path, output: Path | None, machine: bool) -> int:
    result: dict[str, Any]
    try:
        spec = load_spec(path)
        if output is not None:
            spec = replace(spec, output_dir=output)
    except UnsupportedError as exc:
        result = {"status": "UNSUPPORTED", "reason": str(exc)}
        target = output or output_dir_hint(path)
        if target is not None:
            _write_input_failure(target, result)
        _emit(result, machine)
        return EXIT_CODES["UNSUPPORTED"]
    except (SpecError, OSError, ValueError) as exc:
        result = {"status": "INVALID_INPUT", "reason": str(exc)}
        target = output or output_dir_hint(path)
        if target is not None:
            _write_input_failure(target, result)
        _emit(result, machine)
        return EXIT_CODES["INVALID_INPUT"]

    try:
        prepare(spec.output_dir)
    except (ArtifactConflict, OSError) as exc:
        result = {"status": "INVALID_INPUT", "reason": str(exc)}
        _emit(result, machine)
        return EXIT_CODES["INVALID_INPUT"]
    try:
        try:
            view = parse_query(spec.views[0], spec, metric=False)
            metric = parse_query(spec.metric, spec, metric=True)
        except (UnsupportedError, SpecError, ValueError) as exc:
            status = "UNSUPPORTED" if isinstance(exc, UnsupportedError) else "INVALID_INPUT"
            result = {"status": status, "reason": str(exc)}
            write_result(spec, result)
            _emit(result, machine)
            return EXIT_CODES[status]
        try:
            return _check_backend(spec, path, view, metric, machine)
        except Exception as exc:
            # Unexpected backend failures never retain or publish a witness.
            result = result_data(
                spec, "INCONCLUSIVE", f"backend error: {type(exc).__name__}", sha256_file(path)
            )
            result["reason_code"] = "BACKEND_ERROR"
            write_result(spec, result)
            _emit(result, machine)
            return EXIT_CODES["INCONCLUSIVE_UNKNOWN"]
    finally:
        finish(spec.output_dir)


def _write_input_failure(output: Path, result: dict[str, Any]) -> None:
    try:
        prepare(output)
        output.joinpath("result.json").write_text(
            json.dumps({"schema_version": 1, **result}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        finish(output)
    except (ArtifactConflict, OSError):
        # The requested directory is unsafe or unwritable; preserve its contents.
        pass


def _check_backend(spec: Spec, path: Path, view: Query, metric: Query, machine: bool) -> int:

    found = search(spec, view, metric)
    result = result_data(spec, found.status, found.reason, sha256_file(path))
    if found.worlds is None:
        if found.status not in {"BOUNDED_NO_COUNTEREXAMPLE", "INCONCLUSIVE"}:
            result["status"] = "INCONCLUSIVE"
            result["reason"] = "solver returned inconsistent status without worlds"
            result["reason_code"] = "SOLVER_ERROR"
            write_result(spec, result)
            _emit(result, machine)
            return EXIT_CODES["INCONCLUSIVE_UNKNOWN"]
        result["result_path"] = str(spec.output_dir / "result.json")
        if found.status == "INCONCLUSIVE":
            reason = (found.reason or "").lower()
            result["reason_code"] = found.reason_code or (
                "TIMEOUT" if "timeout" in reason or "canceled" in reason else "UNKNOWN"
            )
        write_result(spec, result)
        _emit(result, machine)
        if found.status == "INCONCLUSIVE" and result["reason_code"] not in {
            "TIMEOUT",
            "MEMORY_LIMIT",
        }:
            return EXIT_CODES["INCONCLUSIVE_UNKNOWN"]
        return EXIT_CODES[found.status]
    if found.status != "CANDIDATE":
        result["status"] = "INCONCLUSIVE"
        result["reason"] = "solver returned inconsistent status with worlds"
        result["reason_code"] = "SOLVER_ERROR"
        write_result(spec, result)
        _emit(result, machine)
        return EXIT_CODES["INCONCLUSIVE_UNKNOWN"]
    left, right = found.worlds
    checked = validate(spec, left, right)
    if not checked.valid:
        result["status"] = "INVALID_CANDIDATE"
        result["reason"] = checked.reason
        write_result(spec, result)
        _emit(result, machine)
        return EXIT_CODES["INVALID_CANDIDATE"]
    result["status"] = "COUNTEREXAMPLE_FOUND"
    result["witness_path"] = str(spec.output_dir / "witness.json")
    result["replay_sql_path"] = str(spec.output_dir / "replay.sql")
    result["view_rows"] = [list(map(list, view_rows)) for view_rows in checked.views]
    result["metric_values"] = list(checked.metrics)
    spec.output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="candidate-", dir=spec.output_dir) as staging:
        staged = write_witness(spec, result, left, right, Path(staging))
        serialized = validate_serialized(staged)
        if not serialized.valid:
            result["status"] = "INVALID_CANDIDATE"
            result["reason"] = serialized.reason
            result.pop("witness_path")
            result.pop("replay_sql_path")
            write_result(spec, result)
            _emit(result, machine)
            return EXIT_CODES["INVALID_CANDIDATE"]
        os.replace(staged, spec.output_dir / "witness.json")
        os.replace(Path(staging) / "replay.sql", spec.output_dir / "replay.sql")
    final_validation = validate_serialized(spec.output_dir / "witness.json")
    if not final_validation.valid:
        result["status"] = "INVALID_CANDIDATE"
        result["reason"] = final_validation.reason
        result.pop("witness_path")
        result.pop("replay_sql_path")
        os.replace(spec.output_dir / "witness.json", spec.output_dir / "invalid_candidate.json")
        os.replace(spec.output_dir / "replay.sql", spec.output_dir / "invalid_candidate.sql")
        write_result(spec, result)
        _emit(result, machine)
        return EXIT_CODES["INVALID_CANDIDATE"]
    write_result(spec, result)
    _emit(result, machine)
    return EXIT_CODES["COUNTEREXAMPLE_FOUND"]


def replay(path: Path, machine: bool) -> int:
    try:
        result = validate_serialized(path)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        _emit({"status": "INVALID_INPUT", "reason": str(exc)}, machine)
        return EXIT_CODES["INVALID_INPUT"]
    except Exception as exc:
        _emit(
            {
                "status": "INCONCLUSIVE",
                "reason": f"backend error: {type(exc).__name__}",
                "reason_code": "BACKEND_ERROR",
            },
            machine,
        )
        return EXIT_CODES["INCONCLUSIVE_UNKNOWN"]
    status = "COUNTEREXAMPLE_FOUND" if result.valid else "INVALID_CANDIDATE"
    _emit({"status": status, "reason": result.reason, "metric_values": result.metrics}, machine)
    return EXIT_CODES[status]


def explain(path: Path) -> int:
    try:
        print(explanation.explain(path))
    except explanation.ExplanationError as exc:
        print(f"EXPLANATION_UNAVAILABLE: {exc}")
        return exc.code
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        print(f"EXPLANATION_UNAVAILABLE: invalid evidence ({type(exc).__name__})")
        return EXIT_CODES["INVALID_INPUT"]
    except Exception as exc:
        print(f"EXPLANATION_UNAVAILABLE: replay error ({type(exc).__name__})")
        return EXIT_CODES["INCONCLUSIVE_UNKNOWN"]
    return 0


def export_test(witness: Path, target: Path, format_name: str, output: Path) -> int:
    try:
        names = (
            proof2test.export_pytest(witness, target, output)
            if format_name == "pytest"
            else proof2test.export_dbt(witness, target, output)
        )
    except UnsupportedError as exc:
        print(f"UNSUPPORTED: {exc}")
        return EXIT_CODES["UNSUPPORTED"]
    except proof2test.ExportConflict as exc:
        print(f"INVALID_INPUT: {exc}")
        return EXIT_CODES["INVALID_INPUT"]
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"INVALID_INPUT: {exc}")
        return EXIT_CODES["INVALID_INPUT"]
    except Exception as exc:
        print(f"INCONCLUSIVE: backend error: {type(exc).__name__}")
        return EXIT_CODES["INCONCLUSIVE_UNKNOWN"]
    print("EXPORTED")
    for name in names:
        print(output / name)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="dataproof-verifier")
    sub = parser.add_subparsers(dest="command", required=True)
    check_parser = sub.add_parser("check", help="search and independently replay NoUndo")
    check_parser.add_argument("spec", type=Path)
    check_parser.add_argument("--output", type=Path)
    check_parser.add_argument("--json", action="store_true")
    preflight_parser = sub.add_parser(
        "preflight", help="check a NoUndo or Doppelgänger spec without searching"
    )
    preflight_parser.add_argument("workflow", choices=("no-undo", "doppelganger"))
    preflight_parser.add_argument("spec", type=Path)
    preflight_parser.add_argument("--json", action="store_true")
    replay_parser = sub.add_parser("replay", help="validate serialized witness and replay.sql")
    replay_parser.add_argument("witness", type=Path)
    replay_parser.add_argument("--json", action="store_true")
    explain_parser = sub.add_parser(
        "explain", help="read-only DuckDB-validated explanation of a positive witness"
    )
    explain_parser.add_argument("witness", type=Path)
    doppel_parser = sub.add_parser("doppelganger", help="find a declared test blind spot")
    doppel_sub = doppel_parser.add_subparsers(dest="doppel_command", required=True)
    doppel_check = doppel_sub.add_parser("check", help="search one legal synthetic dataset")
    doppel_check.add_argument("spec", type=Path)
    doppel_check.add_argument("--output", type=Path)
    doppel_check.add_argument("--json", action="store_true")
    doppel_replay = doppel_sub.add_parser("replay", help="validate a serialized blind spot")
    doppel_replay.add_argument("witness", type=Path)
    doppel_replay.add_argument("--json", action="store_true")
    join_parser = sub.add_parser("join", help="complete tiny two-table NoUndo check")
    join_sub = join_parser.add_subparsers(dest="join_command", required=True)
    join_preflight = join_sub.add_parser("preflight", help="validate the bounded join contract")
    join_preflight.add_argument("spec", type=Path)
    join_preflight.add_argument("--json", action="store_true")
    join_check = join_sub.add_parser("check", help="search and independently verify a join witness")
    join_check.add_argument("spec", type=Path)
    join_check.add_argument("--output", type=Path)
    join_check.add_argument("--json", action="store_true")
    join_replay = join_sub.add_parser("replay", help="validate serialized join evidence")
    join_replay.add_argument("witness", type=Path)
    join_replay.add_argument("--json", action="store_true")
    join_explain = join_sub.add_parser("explain", help="explain a replayed join witness")
    join_explain.add_argument("witness", type=Path)
    proof_parser = sub.add_parser("proof2test", help="export a validated regression fixture")
    proof_sub = proof_parser.add_subparsers(dest="proof_command", required=True)
    proof_export = proof_sub.add_parser("export")
    proof_export.add_argument("witness", type=Path)
    proof_export.add_argument("--target", type=Path, required=True)
    proof_export.add_argument("--format", choices=("pytest", "dbt"), default="pytest")
    proof_export.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "check":
        code = check(args.spec, args.output, args.json)
    elif args.command == "preflight":
        code = preflight.check(args.workflow, args.spec, args.json)
    elif args.command == "explain":
        code = explain(args.witness)
    elif args.command == "doppelganger":
        if args.doppel_command == "check":
            code = doppel_cli.check(args.spec, args.output, args.json)
        else:
            code = doppel_cli.replay(args.witness, args.json)
    elif args.command == "join":
        if args.join_command == "preflight":
            code = join_cli.preflight(args.spec, args.json)
        elif args.join_command == "check":
            code = join_cli.check(args.spec, args.output, args.json)
        elif args.join_command == "explain":
            code = join_cli.explain_witness(args.witness)
        else:
            code = join_cli.replay_witness(args.witness, args.json)
    elif args.command == "proof2test":
        code = export_test(args.witness, args.target, args.format, args.output)
    else:
        code = replay(args.witness, args.json)
    sys.exit(code)
