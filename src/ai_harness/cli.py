"""Harness CLI entry point.

Stable commands:
    ./harness doctor
    ./harness validate
    ./harness list
    ./harness run <stage-or-workflow> [--dry-run] [--json]
    ./harness eval <smoke|full> [--offline] [--json]
    ./harness baseline compare <report-a> <report-b>
    ./harness explain <topic>
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from . import __version__
from .config import ConfigError, load_config
from .evals import DatasetError, compare_reports, load_dataset, run_eval
from .policy import (
    EXIT_INTERNAL,
    EXIT_POLICY_BLOCKED,
    EXIT_STAGE_FAILED,
    EXIT_SUCCESS,
    EXIT_USAGE,
    EXIT_VALIDATION,
)
from .result import (
    STATUS_BLOCKED,
    STATUS_FAILED,
    STATUS_PASSED,
    STATUS_SKIPPED,
    RunResult,
)
from .runner import RunRequest, list_targets, run_target

DEFAULT_CONFIG_PATH = "harness.toml"

# Tools we probe for in `doctor`. None are required for the harness itself.
DOCTOR_PROBES = ["python3", "git"]
DOCTOR_OPTIONAL_PROBES = ["ruff", "pyright", "pytest", "uv", "node", "go", "cargo", "dotnet"]


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        rc = _dispatch(args)
    except KeyboardInterrupt:
        return EXIT_INTERNAL
    except ConfigError as e:
        sys.stderr.write(f"validation error: {e}\n")
        return EXIT_VALIDATION
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"internal error: {type(e).__name__}: {e}\n")
        return EXIT_INTERNAL
    return rc


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="harness",
        description=(
            "Vendor-neutral control plane for AI-assisted development and "
            "AI application lifecycle management."
        ),
    )
    p.add_argument("--version", action="version", version=f"harness {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("doctor", help="Check harness, config, and toolchain.")
    sp.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    sp.add_argument("--json", action="store_true", dest="json_output")

    sp = sub.add_parser("validate", help="Validate harness config and datasets.")
    sp.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    sp.add_argument("--json", action="store_true", dest="json_output")
    sp.add_argument("--strict", action="store_true",
                    help="Treat warnings as errors.")

    sp = sub.add_parser("list", help="List stages, workflows, and config sources.")
    sp.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    sp.add_argument("--json", action="store_true", dest="json_output")

    sp = sub.add_parser("run", help="Run a stage or workflow.")
    sp.add_argument("target")
    sp.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--json", action="store_true", dest="json_output")

    sp = sub.add_parser("eval", help="Run an offline or online eval.")
    sp.add_argument("kind", choices=["smoke", "full"])
    sp.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    sp.add_argument("--offline", action="store_true",
                    help="Only use fixture outputs; never call a model.")
    sp.add_argument("--json", action="store_true", dest="json_output")

    sp = sub.add_parser("baseline", help="Baseline report tooling.")
    sp_b = sp.add_subparsers(dest="baseline_cmd", required=True)
    sp_c = sp_b.add_parser("compare",
                           help="Compare two eval reports by pass rate.")
    sp_c.add_argument("a")
    sp_c.add_argument("b")
    sp_c.add_argument("--json", action="store_true", dest="json_output")

    sp = sub.add_parser("explain", help="Explain a stage or policy topic.")
    sp.add_argument("topic")

    sp = sub.add_parser(
        "init",
        help="Bootstrap a harness setup in the current directory.",
    )
    sp.add_argument("--language", default="python",
                    choices=["python", "typescript", "go", "rust", "jvm", "dotnet", "other"])
    sp.add_argument("--workload", default="other",
                    choices=["chat", "rag", "agent", "extraction", "code-agent", "other"])
    sp.add_argument("--risk", default="standard",
                    choices=["prototype", "standard", "high-risk"])
    sp.add_argument("--name", default="",
                    help="Project name (defaults to current directory name).")
    sp.add_argument("--force", action="store_true",
                    help="Overwrite an existing harness.toml.")
    sp.add_argument("--json", action="store_true", dest="json_output")

    return p


def _dispatch(args: argparse.Namespace) -> int:
    cmd = args.cmd
    if cmd == "doctor":
        return _cmd_doctor(args)
    if cmd == "validate":
        return _cmd_validate(args)
    if cmd == "list":
        return _cmd_list(args)
    if cmd == "run":
        return _cmd_run(args)
    if cmd == "eval":
        return _cmd_eval(args)
    if cmd == "baseline":
        return _cmd_baseline(args)
    if cmd == "explain":
        return _cmd_explain(args)
    if cmd == "init":
        return _cmd_init(args)
    sys.stderr.write(f"unknown command: {cmd}\n")
    return EXIT_USAGE


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _cmd_doctor(args: argparse.Namespace) -> int:
    result = RunResult(command="doctor")
    cfg = None
    cfg_status = STATUS_PASSED
    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        cfg_status = STATUS_FAILED
        result.add_error(f"config: {e}")
    result.summary["config_loadable"] = cfg_status == STATUS_PASSED
    result.summary["config_path"] = str(args.config)

    # Probe required tooling.
    tools: dict[str, bool] = {}
    for name in DOCTOR_PROBES:
        tools[name] = shutil.which(name) is not None
    optional: dict[str, bool] = {}
    for name in DOCTOR_OPTIONAL_PROBES:
        optional[name] = shutil.which(name) is not None
    result.summary["tools"] = tools
    result.summary["optional_tools"] = optional

    # Probe profile-supplied executables referenced by commands.
    if cfg is not None:
        declared: dict[str, dict[str, Any]] = {}
        for stage, arrays in cfg.commands.items():
            declared[stage] = {
                "executables": sorted({a[0] for a in arrays if a}),
                "available": all(
                    shutil.which(a[0]) is not None
                    for a in arrays
                    if a
                ),
            }
        result.summary["declared_commands"] = declared

    # Probe eval datasets.
    if cfg is not None:
        evals: dict[str, dict[str, Any]] = {}
        for ename, ec in cfg.evals.items():
            try:
                cases = load_dataset(ec.dataset)
                evals[ename] = {
                    "dataset": ec.dataset,
                    "loadable": True,
                    "case_count": len(cases),
                }
            except DatasetError as e:
                evals[ename] = {
                    "dataset": ec.dataset,
                    "loadable": False,
                    "error": str(e),
                }
        result.summary["evals"] = evals

    result.status = (
        STATUS_PASSED
        if cfg_status == STATUS_PASSED and all(tools.values())
        else STATUS_FAILED
    )
    return _emit(result, args.json_output)


def _cmd_validate(args: argparse.Namespace) -> int:
    result = RunResult(command="validate")
    cfg = None
    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        result.add_error(str(e))
        result.status = STATUS_FAILED
        _emit(result, args.json_output)
        return EXIT_VALIDATION
    # Validate declared commands: each argv must have a non-empty executable.
    for stage, arrays in cfg.commands.items():
        for argv in arrays:
            if not argv or not argv[0]:
                result.add_error(
                    f"[commands].{stage} contains an empty argv"
                )
    # Validate datasets.
    for ename, ec in cfg.evals.items():
        try:
            load_dataset(ec.dataset)
        except DatasetError as e:
            result.add_error(f"[evals.{ename}]: {e}")
    # Check workflows reference known stages, workflows, or built-ins.
    from .runner import BUILTIN_STAGES

    known = (
        set(cfg.commands.keys())
        | set(cfg.workflows.keys())
        | BUILTIN_STAGES
    )
    for wfname, seq in cfg.workflows.items():
        for ref in seq:
            if ref not in known:
                result.add_error(
                    f"workflow '{wfname}' references unknown '{ref}'"
                )
    if result.errors:
        result.status = STATUS_FAILED
        _emit(result, args.json_output)
        return EXIT_VALIDATION
    result.summary["validated"] = {
        "commands": sorted(cfg.commands.keys()),
        "workflows": sorted(cfg.workflows.keys()),
        "evals": sorted(cfg.evals.keys()),
    }
    _emit(result, args.json_output)
    return EXIT_SUCCESS


def _cmd_list(args: argparse.Namespace) -> int:
    result = RunResult(command="list")
    cfg = load_config(args.config)
    targets = list_targets(cfg)
    result.summary["project"] = asdict(cfg.project)
    result.summary["source_path"] = cfg.source_path
    result.summary.update(targets)
    result.summary["security"] = {
        "tool_allowlist": cfg.security.tool_allowlist,
        "require_approval_for": cfg.security.require_approval_for,
        "redact_inputs": cfg.security.redact_inputs,
        "redact_outputs": cfg.security.redact_outputs,
    }
    return _emit(result, args.json_output)


def _cmd_run(args: argparse.Namespace) -> int:
    result = RunResult(command="run")
    cfg = load_config(args.config)
    request = RunRequest(
        name=args.target,
        dry_run=bool(args.dry_run),
        json_output=bool(args.json_output),
    )
    run_target(cfg, request, result)
    rc = _status_to_rc(result.status)
    _emit(result, args.json_output)
    if rc != EXIT_SUCCESS:
        sys.stdout.write(f"  exit_code: {rc}\n")
    return rc


def _cmd_eval(args: argparse.Namespace) -> int:
    result = RunResult(command="eval")
    cfg = load_config(args.config)
    stage = run_eval(cfg, args.kind, result, offline=bool(args.offline))
    result.stages.append(stage)
    if stage.status == STATUS_FAILED:
        result.status = STATUS_FAILED
    elif stage.status == STATUS_BLOCKED and result.status == STATUS_PASSED:
        result.status = STATUS_BLOCKED
    rc = _status_to_rc(result.status)
    _emit(result, args.json_output)
    return rc


def _cmd_baseline(args: argparse.Namespace) -> int:
    result = RunResult(command="baseline compare")
    try:
        delta = compare_reports(args.a, args.b)
    except FileNotFoundError as e:
        result.add_error(str(e))
        result.status = STATUS_FAILED
        _emit(result, args.json_output)
        return EXIT_VALIDATION
    result.summary["comparison"] = delta
    if delta.get("regression", 0) > 0:
        result.status = STATUS_FAILED
    _emit(result, args.json_output)
    return _status_to_rc(result.status)


def _cmd_explain(args: argparse.Namespace) -> int:
    topic = args.topic
    explanations = _EXPLANATIONS
    text = explanations.get(topic)
    if text is None:
        # Try fuzzy match on stage names.
        sys.stderr.write(
            f"unknown topic '{topic}'. Known: {sorted(explanations)}\n"
        )
        return EXIT_USAGE
    sys.stdout.write(text + "\n")
    return EXIT_SUCCESS


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def _harness_home() -> Path:
    """Resolve the source repo root that ships this CLI.

    Used by `init` to find executable, schema, and example templates.
    """
    return Path(__file__).resolve().parents[2]


def _cmd_init(args: argparse.Namespace) -> int:
    result = RunResult(command="init")
    cwd = Path.cwd()
    name = (args.name or cwd.name).strip()
    if not name:
        result.add_error("--name is required when cwd has no usable name")
        result.status = STATUS_FAILED
        return _emit(result, args.json_output)

    cfg_path = cwd / "harness.toml"
    if cfg_path.exists() and not args.force:
        msg = (
            f"harness.toml already exists at {cfg_path}. "
            f"Use --force to overwrite, or remove it first."
        )
        result.add_error(msg)
        result.status = STATUS_FAILED
        return _emit(result, args.json_output)

    home = _harness_home()
    actions: list[str] = []

    # 1. Copy executable entry point and schema.
    src_exe = home / "harness"
    src_schema = home / "harness.schema.json"
    if not src_exe.exists():
        result.add_error(f"harness source missing: {src_exe}")
        result.status = STATUS_FAILED
        return _emit(result, args.json_output)
    dst_exe = cwd / "harness"
    dst_schema = cwd / "harness.schema.json"
    dst_exe.write_bytes(src_exe.read_bytes())
    dst_exe.chmod(0o755)
    actions.append(f"copied harness executable -> {dst_exe}")
    if src_schema.exists():
        dst_schema.write_bytes(src_schema.read_bytes())
        actions.append(f"copied harness.schema.json -> {dst_schema}")

    # 2. Generate harness.toml from the closest example, or fall back to a
    #    synthesized config from language + workload + risk.
    toml_text = _render_init_toml(
        name=name,
        language=args.language,
        workload=args.workload,
        risk=args.risk,
        home=home,
    )
    cfg_path.write_text(toml_text, encoding="utf-8")
    actions.append(f"wrote {cfg_path}")

    # 3. Create skeleton directories.
    for d in (
        "evals/datasets",
        "evals/baselines",
        "evals/reports",
        "evals/graders",
        "prompts/templates",
        "prompts/schemas",
        "tests/unit",
        "tests/integration",
        "tests/fixtures",
    ):
        (cwd / d).mkdir(parents=True, exist_ok=True)
    # .gitkeep on dirs that would otherwise be empty.
    for keeper in (
        "evals/reports/.gitkeep",
        "evals/baselines/.gitkeep",
        "tests/fixtures/.gitkeep",
    ):
        kp = cwd / keeper
        if not kp.exists():
            kp.parent.mkdir(parents=True, exist_ok=True)
            kp.write_text("", encoding="utf-8")
    actions.append("created skeleton directories under evals/, prompts/, tests/")

    # 4. Seed a tiny offline smoke dataset so `eval smoke --offline` works
    #    out of the box. The user is expected to replace it.
    smoke_path = cwd / "evals/datasets/smoke.example.jsonl"
    if not smoke_path.exists():
        smoke_path.write_text(
            _INIT_SMOKE_DATASET, encoding="utf-8"
        )
        actions.append(
            f"seeded {smoke_path} (replace with your real samples)"
        )

    # 4b. Copy any *other* example datasets referenced by the chosen
    #     template (e.g. regression.example.jsonl) so validate + eval full
    #     work without manual setup.
    src_datasets = home / "evals" / "datasets"
    if src_datasets.is_dir():
        for ds_path in _dataset_paths_in_toml(cfg_path):
            basename = ds_path.split("/")[-1]
            if not basename.endswith(".jsonl"):
                continue
            dst = cwd / "evals" / "datasets" / basename
            if dst.exists():
                continue
            src = src_datasets / basename
            if src.exists():
                dst.write_bytes(src.read_bytes())
                actions.append(f"seeded {dst} (replace with your real samples)")

    # 5. Seed a baseline-latest pointer file so `baseline compare` has a
    #    target after the user runs the first eval.
    baseline_readme = cwd / "evals/baselines/README.md"
    if not baseline_readme.exists():
        baseline_readme.write_text(_INIT_BASELINE_README, encoding="utf-8")

    # 6. .gitignore for reports/workspace so they don't get committed.
    gi = cwd / ".gitignore"
    snippet = _INIT_GITIGNORE
    if gi.exists():
        existing = gi.read_text(encoding="utf-8")
        if "evals/reports/*" not in existing:
            gi.write_text(existing.rstrip() + "\n" + snippet, encoding="utf-8")
            actions.append("appended harness entries to existing .gitignore")
    else:
        gi.write_text(snippet, encoding="utf-8")
        actions.append("wrote .gitignore")

    result.summary["actions"] = actions
    result.summary["next_steps"] = [
        "Edit harness.toml: name, dataset paths, [commands] for your tools.",
        "Replace evals/datasets/smoke.example.jsonl with your real samples.",
        "Run ./harness doctor to verify your toolchain.",
        "Run ./harness run check to run your project's checks.",
        "Run ./harness eval smoke --offline for offline AI eval.",
    ]
    result.summary["project"] = {
        "name": name,
        "language": args.language,
        "workload": args.workload,
        "risk": args.risk,
        "path": str(cwd),
    }
    return _emit(result, args.json_output)


_INIT_SMOKE_DATASET = """{"id":"smoke-001","input":{"query":"hello","output":{"answer":"hello world"}},"expected":{"contains":["hello"]},"tags":["smoke"],"metadata":{"source":"synthetic"}}
{"id":"smoke-002","input":{"query":"bye","output":{"answer":"goodbye world"}},"expected":{"contains":["bye"]},"tags":["smoke"],"metadata":{"source":"synthetic"}}
"""

_INIT_BASELINE_README = """# Baselines

A baseline is a frozen eval report used as a regression reference. Promote
a report deliberately:

```bash
./harness eval full --offline
./harness baseline compare evals/baselines/latest.json "$(ls -t evals/reports/full-*.json | head -1)"
cp "$(ls -t evals/reports/full-*.json | head -1)" evals/baselines/latest.json
git add evals/baselines/latest.json && git commit -m "baseline: bump"
```

Baseline updates are an explicit, reviewable operation — they never
happen automatically inside an eval run. See
`docs/adr/0006-reports-vs-baselines.md` in the source repo for rationale.
"""

_INIT_GITIGNORE = """# Harness generated artifacts. Baselines under evals/baselines/ ARE
# checked in; reports and runtime artifacts are NOT.
evals/reports/*
!evals/reports/.gitkeep

# skill-up workspaces (per-iteration eval artifacts).
*-workspace/

# Python
__pycache__/
*.py[cod]
.venv/
venv/
"""

# Stage-name -> example argv mapping per language. Used when synthesizing a
# harness.toml for a (language, workload, risk) combo that has no exact
# example/ match.
_LANG_COMMANDS: dict[str, dict[str, list[list[str]]]] = {
    "python": {
        "bootstrap": [["python3", "-m", "pip", "install", "-e", "."]],
        "format": [["python3", "-m", "black", "."]],
        "lint": [["python3", "-m", "ruff", "check", "."]],
        "typecheck": [["python3", "-m", "pyright"]],
        "test-unit": [["python3", "-m", "pytest", "tests/unit"]],
        "test-integration": [["python3", "-m", "pytest", "tests/integration"]],
    },
    "typescript": {
        "bootstrap": [["npm", "ci"]],
        "format": [["npx", "prettier", "--write", "."]],
        "lint": [["npx", "eslint", "."]],
        "typecheck": [["npx", "tsc", "--noEmit"]],
        "test-unit": [["npx", "vitest", "run", "tests/unit"]],
        "test-integration": [["npx", "vitest", "run", "tests/integration"]],
    },
    "go": {
        "bootstrap": [["go", "mod", "download"]],
        "format": [["gofmt", "-w", "."]],
        "lint": [["golangci-lint", "run", "./..."]],
        "typecheck": [["go", "vet", "./..."], ["go", "build", "./..."]],
        "test-unit": [["go", "test", "./..."]],
        "test-integration": [["go", "test", "-tags=integration", "./..."]],
    },
    "rust": {
        "bootstrap": [["cargo", "fetch"]],
        "format": [["cargo", "fmt"]],
        "lint": [["cargo", "clippy", "--", "-D", "warnings"]],
        "typecheck": [["cargo", "check", "--all-targets"]],
        "test-unit": [["cargo", "test", "--lib"]],
        "test-integration": [["cargo", "test"]],
    },
    "jvm": {
        "bootstrap": [["./gradlew", "--quiet", "dependencies"]],
        "format": [["./gradlew", "--quiet", "spotlessApply"]],
        "lint": [["./gradlew", "--quiet", "checkstyleMain"]],
        "typecheck": [["./gradlew", "--quiet", "compileJava"]],
        "test-unit": [["./gradlew", "--quiet", "test"]],
        "test-integration": [["./gradlew", "--quiet", "integrationTest"]],
    },
    "dotnet": {
        "bootstrap": [["dotnet", "restore"]],
        "format": [["dotnet", "format"]],
        "lint": [["dotnet", "format", "--verify-no-changes"]],
        "typecheck": [["dotnet", "build", "--no-restore"]],
        "test-unit": [["dotnet", "test", "--no-build"]],
        "test-integration": [["dotnet", "test", "--no-build", "--filter", "Integration"]],
    },
}


def _render_init_toml(
    *, name: str, language: str, workload: str, risk: str, home: Path
) -> str:
    """Prefer an exact example/<lang>-<workload>/ template; else synthesize."""
    example = _find_example_for(language=language, workload=workload, home=home)
    if example is not None:
        text = example.read_text(encoding="utf-8")
        # Override name + risk to honor the user's flags.
        text = _override_toml_field(text, "name", name, section="project")
        text = _override_toml_field(text, "risk", risk, section="project")
        # Rewrite dataset paths so they resolve from the new project root,
        # not from the example's relative location.
        text = _localize_dataset_paths(text)
        return text
    cmds = _LANG_COMMANDS.get(language, {})
    lines: list[str] = [
        "version = 1",
        "",
        "[project]",
        f'name = "{name}"',
        f'language = "{language}"',
        f'workload = "{workload}"',
        f'risk = "{risk}"',
        "",
    ]
    if cmds:
        lines.append("[commands]")
        for stage, argv_arrays in cmds.items():
            argv_reprs = [
                "[" + ", ".join(f'"{a}"' for a in argv) + "]"
                for argv in argv_arrays
            ]
            if len(argv_reprs) == 1:
                lines.append(f"{stage} = [{argv_reprs[0]}]")
            else:
                lines.append(f"{stage} = [{', '.join(argv_reprs)}]")
        lines.append("")
    lines.extend([
        "[workflows]",
        'check = ["format", "lint", "typecheck", "test-unit"]',
        'release-check = ["check", "test-integration", "eval-full", "security"]',
        "",
        "[evals.smoke]",
        'dataset = "evals/datasets/smoke.example.jsonl"',
        "sample_limit = 20",
        "min_pass_rate = 0.90",
        "",
        "[evals.full]",
        'dataset = "evals/datasets/smoke.example.jsonl"',
        "repetitions = 1",
        "min_pass_rate = 0.95",
        "max_regression = 0.02",
        "",
        "[security]",
        "redact_inputs = true",
        "redact_outputs = true",
        'tool_allowlist = ["retrieve"]',
        'require_approval_for = ["external_write", "delete", "payment", "deploy"]',
        "",
    ])
    return "\n".join(lines)


def _find_example_for(
    *, language: str, workload: str, home: Path
) -> Path | None:
    examples = home / "examples"
    if not examples.is_dir():
        return None
    # Try exact match first: examples/<lang>-<workload>/
    direct = examples / f"{language}-{workload}"
    if (direct / "harness.toml").exists():
        return direct / "harness.toml"
    # Fall back to any example for that language.
    for p in sorted(examples.glob(f"{language}-*/harness.toml")):
        return p
    return None


def _override_toml_field(
    text: str, field: str, value: str, *, section: str
) -> str:
    """Replace `<field> = "..."` under `[<section>]` in TOML text."""
    import re

    pattern = re.compile(
        rf"(^\[{re.escape(section)}\]\n(?:[^\[]*?))"
        rf"({re.escape(field)}\s*=\s*)\"[^\"]*\"",
        re.MULTILINE,
    )

    def _repl(m: re.Match) -> str:
        return f"{m.group(1)}{m.group(2)}\"{value}\""

    return pattern.sub(_repl, text)


def _localize_dataset_paths(text: str) -> str:
    """Rewrite `dataset = "..."` paths to point at the new project's local
    evals/datasets/ directory, preserving the basename."""
    import re

    pattern = re.compile(r'^(dataset\s*=\s*)"([^"]+)"', re.MULTILINE)

    def _repl(m: re.Match) -> str:
        orig = m.group(2)
        # Strip any leading ../ sequences and the source-tree prefix.
        basename = orig.split("/")[-1]
        # If it's already a clean local path, leave it alone.
        if orig == f"evals/datasets/{basename}":
            return m.group(0)
        return f'{m.group(1)}"evals/datasets/{basename}"'

    return pattern.sub(_repl, text)


def _dataset_paths_in_toml(path: Path) -> list[str]:
    """Return all `dataset = "..."` values from a TOML file (text scan)."""
    import re

    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r'^dataset\s*=\s*"([^"]+)"', re.MULTILINE)
    return pattern.findall(text)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _status_to_rc(status: str) -> int:
    return {
        STATUS_PASSED: EXIT_SUCCESS,
        STATUS_SKIPPED: EXIT_SUCCESS,  # not an error to skip
        STATUS_FAILED: EXIT_STAGE_FAILED,
        STATUS_BLOCKED: EXIT_POLICY_BLOCKED,
    }.get(status, EXIT_INTERNAL)


def _emit(result: RunResult, json_output: bool) -> int:
    if json_output:
        sys.stdout.write(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2,
                       sort_keys=True)
            + "\n"
        )
        return _status_to_rc(result.status)
    # Human-readable summary.
    sys.stdout.write(f"[{result.command}] {result.status}\n")
    for stage in result.stages:
        _print_stage(stage, indent=1)
    for err in result.errors:
        sys.stdout.write(f"  error: {err}\n")
    if result.summary:
        sys.stdout.write(
            "  summary: "
            + json.dumps(result.summary, ensure_ascii=False, sort_keys=True)
            + "\n"
        )
    return _status_to_rc(result.status)


def _print_stage(stage, indent: int) -> None:
    pad = "  " * indent
    line = f"{pad}- {stage.name} [{stage.kind}] {stage.status}"
    if stage.reason:
        line += f" :: {stage.reason}"
    sys.stdout.write(line + "\n")
    for child in getattr(stage, "children", []):
        _print_stage(child, indent + 1)


_EXPLANATIONS: dict[str, str] = {
    "doctor": (
        "`doctor` checks that the harness, the project config, and the "
        "declared toolchain are usable. It does not run project checks — "
        "use `./harness run check` for that."
    ),
    "validate": (
        "`validate` parses harness.toml against the schema, checks that "
        "every workflow reference resolves, and loads each declared eval "
        "dataset to catch malformed JSONL."
    ),
    "check": (
        "`check` is a workflow composed in harness.toml. By default it "
        "runs format, lint, typecheck, and test-unit. Stages that are "
        "not configured or whose executable is absent are reported as "
        "`skipped` with a reason — never as `passed`."
    ),
    "eval-smoke": (
        "`eval smoke` runs the [evals.smoke] dataset with strict sample, "
        "timeout, and cost limits. It is meant for PR feedback loops and "
        "should run offline by default."
    ),
    "eval-full": (
        "`eval full` runs the [evals.full] dataset with repetitions and "
        "regression thresholds. It is meant for scheduled runs or release "
        "gates, not for every PR."
    ),
    "security": (
        "`security` covers secret redaction, tool allowlist, and approval "
        "gates. Tool calls default to read-only; write actions like "
        "external_write, delete, payment, and deploy must be added to "
        "require_approval_for explicitly."
    ),
    "release-check": (
        "`release-check` is a workflow that runs check, integration tests, "
        "full eval, and the security gate. It is the pre-release gate."
    ),
}


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
