"""
Agentic STLC CLI

Entry point for the `agentic-stlc` command.

Commands:
  run      — execute the full pipeline end-to-end
  analyze  — run requirement analysis (Stage 1) only
  generate — generate Playwright tests from scenarios
  report   — re-generate all reports from existing artifacts
  status   — show current pipeline status / latest run results
  init     — scaffold a new agentic-stlc.config.yaml in the current directory
  validate — validate config + check required tools are installed

Examples:
  agentic-stlc run
  agentic-stlc run --repo https://github.com/org/app --branch main --full
  agentic-stlc analyze --requirements requirements/search.txt
  agentic-stlc generate --scenarios scenarios/scenarios.json
  agentic-stlc report --output reports/
  agentic-stlc init
  agentic-stlc validate
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Allow running from repo root without installing
sys.path.insert(0, str(Path(__file__).parent.parent))


def _load_config(args: argparse.Namespace):
    from platform.config import PlatformConfig
    config_path = getattr(args, "config", None) or "agentic-stlc.config.yaml"
    cfg = PlatformConfig.load(config_path)
    errors = cfg.validate()
    if errors:
        for e in errors:
            print(f"  [config] WARNING: {e}")
    return cfg


# ── Command handlers ──────────────────────────────────────────────────────────

def cmd_run(args: argparse.Namespace) -> int:
    """Run the full pipeline."""
    cfg = _load_config(args)

    # Override config with CLI flags
    data = cfg.as_dict()
    if getattr(args, "repo", None):
        data.setdefault("project", {})["repository"] = args.repo
    if getattr(args, "branch", None):
        data.setdefault("project", {})["branch"] = args.branch
    if getattr(args, "full", False):
        data.setdefault("execution", {})["mode"] = "full"
    if getattr(args, "target_url", None):
        data.setdefault("target", {})["url"] = args.target_url
    if getattr(args, "requirements", None):
        data.setdefault("requirements", {})["paths"] = [args.requirements]

    from platform.config import PlatformConfig
    from platform.pipeline import Pipeline
    cfg2 = PlatformConfig.from_dict(data)
    result = Pipeline(cfg2).run()

    print(f"\n{'=' * 60}")
    if result["success"]:
        print(f"  Pipeline PASSED  ({result['passed_stages']}/{result['total_stages']} stages)")
    else:
        print(f"  Pipeline FAILED  ({result['failed_stages']} stages failed)")
    print(f"  Duration: {result['total_duration_s']:.1f}s")
    print(f"{'=' * 60}")
    return 0 if result["success"] else 1


def cmd_analyze(args: argparse.Namespace) -> int:
    """Run KaneAI requirement analysis only."""
    cfg = _load_config(args)

    req_paths = ([args.requirements] if getattr(args, "requirements", None)
                 else cfg.as_dict().get("requirements", {}).get("paths", []))

    if not req_paths:
        print("ERROR: No requirements files specified.")
        return 1

    # Delegate to existing analyze_requirements.py for now
    import subprocess
    env = dict(os.environ)
    env["REQUIREMENTS_PATHS"] = ",".join(req_paths)
    result = subprocess.run([sys.executable, "ci/analyze_requirements.py"], env=env)
    return result.returncode


def cmd_generate(args: argparse.Namespace) -> int:
    """Generate Playwright tests from scenarios."""
    cfg = _load_config(args)

    sc_path = getattr(args, "scenarios", None) or str(cfg.scenarios_path)
    target_url = getattr(args, "target_url", None) or cfg.target.url or ""

    from skills.playwright_generation import PlaywrightGenerationSkill
    skill = PlaywrightGenerationSkill(config=cfg)
    result = skill.run(scenarios_path=sc_path, target_url=target_url)
    if result["success"]:
        print(f"Generated {result['tests_generated']} tests → {result['test_file']}")
    else:
        print(f"Generation failed: {result.get('error', 'unknown')}")
    return 0 if result["success"] else 1


def cmd_report(args: argparse.Namespace) -> int:
    """Re-generate reports from existing artifacts."""
    import subprocess
    output = getattr(args, "output", "reports")
    print(f"Generating reports → {output}/")
    result = subprocess.run([sys.executable, "ci/write_github_summary.py"])
    return result.returncode


def cmd_status(args: argparse.Namespace) -> int:
    """Show current pipeline status."""
    reports = Path("reports")
    if not reports.exists():
        print("No reports found. Run `agentic-stlc run` first.")
        return 1

    # Release recommendation
    rec_path = reports / "release_recommendation.json"
    if rec_path.exists():
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
        verdict  = rec.get("verdict", "UNKNOWN")
        icon = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}.get(verdict, "⚪")
        print(f"\n{icon}  Verdict: {verdict}")
        print(f"   Pass rate: {rec.get('pass_rate', 0)}%")

    # Quality gates
    qg_path = reports / "quality_gates.json"
    if qg_path.exists():
        qg = json.loads(qg_path.read_text(encoding="utf-8"))
        total = len(qg.get("gates", []))
        crits = qg.get("critical_failures", 0)
        warns = qg.get("warnings", 0)
        gate_icon = "✅" if qg.get("gates_passed") else "❌"
        print(f"\n{gate_icon}  Quality gates: {total - crits - warns}/{total} passed")
        print(f"   Critical failures: {crits} | Warnings: {warns}")

    # Confidence
    conf_path = reports / "scenario-confidence-report.json"
    if conf_path.exists():
        conf = json.loads(conf_path.read_text(encoding="utf-8"))
        by_level = conf.get("summary", {}).get("by_confidence_level", {})
        print(f"\n   Confidence distribution:")
        for level, count in by_level.items():
            if count:
                print(f"   {level}: {count}")

    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Scaffold agentic-stlc.config.yaml."""
    dest = Path("agentic-stlc.config.yaml")
    template = Path(__file__).parent.parent / "templates/config/agentic-stlc.config.yaml.example"
    if dest.exists():
        print(f"Config already exists: {dest}")
        return 1
    if template.exists():
        import shutil
        shutil.copy(str(template), str(dest))
        print(f"Created {dest} from template. Edit it to match your project.")
    else:
        print(f"Template not found at {template}. Writing minimal config.")
        dest.write_text(
            "version: '1.0'\nproject:\n  name: my-app\n  repository: ''\n", encoding="utf-8"
        )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate config and check required tools."""
    cfg = _load_config(args)
    errors = cfg.validate()
    print(f"\nConfig validation: {'PASS' if not errors else 'FAIL'}")
    for e in errors:
        print(f"  ERROR: {e}")

    # Tool checks
    import shutil
    tools = {"python": sys.executable, "kane-cli": "kane-cli", "node": "node"}
    for name, binary in tools.items():
        found = bool(shutil.which(binary))
        icon = "✅" if found else "❌"
        print(f"  {icon} {name}: {'found' if found else 'NOT FOUND'}")

    # HyperExecute CLI
    he_candidates = ["./hyperexecute", "./hyperexecute.exe", "hyperexecute"]
    he_found = any(Path(c).exists() for c in he_candidates)
    print(f"  {'✅' if he_found else '❌'} hyperexecute: {'found' if he_found else 'NOT FOUND'}")

    return 0 if not errors else 1


# ── Argument parser ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentic-stlc",
        description="Agentic STLC Platform — autonomous QA orchestration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--config", "-c", metavar="PATH", help="Path to agentic-stlc.config.yaml")

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # run
    p_run = subparsers.add_parser("run", help="Execute full pipeline")
    p_run.add_argument("--repo",        metavar="URL",  help="Target repository URL")
    p_run.add_argument("--branch",      metavar="BRANCH", default="", help="Git branch")
    p_run.add_argument("--requirements", metavar="FILE", help="Requirements file path")
    p_run.add_argument("--target-url",  metavar="URL",  help="Application URL under test")
    p_run.add_argument("--full",        action="store_true", help="Run all scenarios (not incremental)")
    p_run.add_argument("--stages",      metavar="IDS",  help="Comma-separated stage IDs to run")

    # analyze
    p_ana = subparsers.add_parser("analyze", help="Run KaneAI requirement analysis")
    p_ana.add_argument("--requirements", metavar="FILE", help="Requirements file path")

    # generate
    p_gen = subparsers.add_parser("generate", help="Generate Playwright tests from scenarios")
    p_gen.add_argument("--scenarios",  metavar="FILE", help="scenarios.json path")
    p_gen.add_argument("--target-url", metavar="URL",  help="Application URL under test")

    # report
    p_rep = subparsers.add_parser("report", help="Regenerate reports from existing artifacts")
    p_rep.add_argument("--output", metavar="DIR", default="reports", help="Report output directory")

    # status
    subparsers.add_parser("status", help="Show latest pipeline status")

    # init
    subparsers.add_parser("init", help="Scaffold agentic-stlc.config.yaml")

    # validate
    subparsers.add_parser("validate", help="Validate config and check tool availability")

    return parser


def main() -> int:
    parser = build_parser()
    args   = parser.parse_args()

    handlers = {
        "run":      cmd_run,
        "analyze":  cmd_analyze,
        "generate": cmd_generate,
        "report":   cmd_report,
        "status":   cmd_status,
        "init":     cmd_init,
        "validate": cmd_validate,
    }

    if not args.command:
        parser.print_help()
        return 0

    handler = handlers.get(args.command)
    if not handler:
        parser.print_help()
        return 1

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
