"""
Agentic STLC CLI

Entry point for the `agentic-stlc` command.

Commands:
  run      - execute the full pipeline end-to-end
  analyze  - run requirement analysis (Stage 1) only
  generate - generate Playwright tests from scenarios
  report   - re-generate all reports from existing artifacts
  status   - show current pipeline status / latest run results
  init     - scaffold a new agentic-stlc.config.yaml in the current directory
  validate - validate config + check required tools are installed

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

# FIX Bug 1: Force UTF-8 output on all platforms (Windows cp1252 crashes on emoji)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure project root is on sys.path for local source runs
_ROOT = str(Path(__file__).parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _load_config(args: argparse.Namespace):
    from astlc.config import PlatformConfig
    config_path = getattr(args, "config", None) or "agentic-stlc.config.yaml"
    cfg = PlatformConfig.load(config_path)
    errors = cfg.validate()
    if errors:
        for e in errors:
            print(f"  [config] WARNING: {e}")
    return cfg


# ── Command handlers ──────────────────────────────────────────────────────────

def cmd_run(args: argparse.Namespace) -> int:
    """Run the full pipeline via the existing ci/agent.py orchestrator."""
    cfg = _load_config(args)
    data = cfg.as_dict()

    if getattr(args, "repo", None):
        data.setdefault("project", {})["repository"] = args.repo
    if getattr(args, "branch", None):
        data.setdefault("project", {})["branch"] = args.branch
    if getattr(args, "full", False):
        data.setdefault("execution", {})["mode"] = "full"
        os.environ["FULL_RUN"] = "true"
    if getattr(args, "target_url", None):
        data.setdefault("target", {})["url"] = args.target_url
        os.environ["TARGET_URL"] = args.target_url
    if getattr(args, "requirements", None):
        data.setdefault("requirements", {})["paths"] = [args.requirements]

    # Delegate to the existing battle-tested orchestrator
    import subprocess
    result = subprocess.run([sys.executable, "ci/agent.py"])
    return result.returncode


def cmd_analyze(args: argparse.Namespace) -> int:
    """Run KaneAI requirement analysis only (Stage 1)."""
    cfg = _load_config(args)

    # FIX Bug 9: Pass requirements as CLI arg, not env var
    req_paths = ([args.requirements] if getattr(args, "requirements", None)
                 else cfg.as_dict().get("requirements", {}).get("paths", []))

    if not req_paths:
        print("ERROR: No requirements files specified. Use --requirements FILE")
        return 1

    import subprocess
    cmd = [sys.executable, "ci/analyze_requirements.py"]
    # Pass paths via env var that analyze_requirements.py actually reads
    env = dict(os.environ)
    if len(req_paths) == 1:
        env["REQUIREMENTS_FILE"] = req_paths[0]
    result = subprocess.run(cmd, env=env)
    return result.returncode


def cmd_generate(args: argparse.Namespace) -> int:
    """Generate Playwright tests from scenarios."""
    cfg = _load_config(args)

    sc_path = getattr(args, "scenarios", None) or str(cfg.scenarios_path)
    target_url = getattr(args, "target_url", None) or (cfg.target.url if cfg.target else "") or ""

    from skills.playwright_generation import PlaywrightGenerationSkill
    skill = PlaywrightGenerationSkill(config=cfg)
    result = skill.run(scenarios_path=sc_path, target_url=target_url)
    if result["success"]:
        print(f"Generated {result['tests_generated']} tests -> {result['test_file']}")
    else:
        print(f"ERROR: Generation failed: {result.get('error', 'unknown')}")
    return 0 if result["success"] else 1


def cmd_report(args: argparse.Namespace) -> int:
    """Re-generate reports from existing artifacts."""
    import subprocess
    output = getattr(args, "output", "reports")
    print(f"Generating reports -> {output}/")
    result = subprocess.run([sys.executable, "ci/write_github_summary.py"])
    return result.returncode


def cmd_status(args: argparse.Namespace) -> int:
    """Show current pipeline status."""
    reports = Path("reports")
    if not reports.exists():
        print("No reports found. Run `agentic-stlc run` first.")
        return 1

    found_anything = False

    # FIX Bug 8: Try JSON first, fall back to MD for release recommendation
    rec_path_json = reports / "release_recommendation.json"
    rec_path_md   = reports / "release_recommendation.md"

    if rec_path_json.exists():
        try:
            rec = json.loads(rec_path_json.read_text(encoding="utf-8"))
            verdict  = rec.get("verdict", "UNKNOWN")
            icon = {"GREEN": "[GREEN]", "YELLOW": "[YELLOW]", "RED": "[RED]"}.get(verdict, "[?]")
            print(f"\n{icon}  Verdict: {verdict}")
            print(f"   Pass rate: {rec.get('pass_rate', 0)}%")
            found_anything = True
        except Exception:
            pass
    elif rec_path_md.exists():
        # Parse verdict from markdown header line
        for line in rec_path_md.read_text(encoding="utf-8").splitlines():
            if "GREEN" in line or "YELLOW" in line or "RED" in line:
                verdict = "GREEN" if "GREEN" in line else ("YELLOW" if "YELLOW" in line else "RED")
                icon = {"GREEN": "[GREEN]", "YELLOW": "[YELLOW]", "RED": "[RED]"}.get(verdict, "[?]")
                print(f"\n{icon}  Verdict: {verdict}")
                found_anything = True
                break

    # Traceability matrix
    matrix_path = reports / "traceability_matrix.json"
    if matrix_path.exists():
        try:
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
            summary = matrix.get("summary", {})
            print(f"\n   Coverage: {summary.get('coverage_pct', 0)}%")
            print(f"   Requirements: {summary.get('total_requirements', 0)} total, "
                  f"{summary.get('fully_covered', summary.get('covered', 0))} covered")
            found_anything = True
        except Exception:
            pass

    # Quality gates
    qg_path = reports / "quality_gates.json"
    if qg_path.exists():
        try:
            qg = json.loads(qg_path.read_text(encoding="utf-8"))
            total = len(qg.get("gates", []))
            crits = qg.get("critical_failures", 0)
            warns = qg.get("warnings", 0)
            gate_icon = "[PASS]" if qg.get("gates_passed") else "[FAIL]"
            print(f"\n{gate_icon}  Quality gates: {total - crits - warns}/{total} passed")
            print(f"   Critical failures: {crits} | Warnings: {warns}")
            found_anything = True
        except Exception:
            pass

    # Confidence
    conf_path = reports / "scenario-confidence-report.json"
    if conf_path.exists():
        try:
            conf = json.loads(conf_path.read_text(encoding="utf-8"))
            by_level = conf.get("summary", {}).get("by_confidence_level", {})
            if by_level:
                print(f"\n   Confidence distribution:")
                for level, count in by_level.items():
                    if count:
                        print(f"     {level}: {count}")
                found_anything = True
        except Exception:
            pass

    if not found_anything:
        print("No pipeline results found. Run `agentic-stlc run` first.")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Scaffold agentic-stlc.config.yaml."""
    dest = Path("agentic-stlc.config.yaml")
    template = Path(__file__).parent.parent / "templates/config/agentic-stlc.config.yaml.example"
    if dest.exists():
        print(f"Config already exists: {dest}")
        print("Delete it first or edit it directly.")
        return 1
    if template.exists():
        import shutil
        shutil.copy(str(template), str(dest))
        print(f"Created {dest} from template.")
        print("Next steps:")
        print("  1. Edit agentic-stlc.config.yaml - set project.repository and target.url")
        print("  2. Run: agentic-stlc validate")
        print("  3. Run: agentic-stlc run")
    else:
        dest.write_text(
            "version: '1.0'\nproject:\n  name: my-app\n  repository: ''\ntarget:\n  url: ''\n",
            encoding="utf-8",
        )
        print(f"Created minimal {dest}. Edit it to match your project.")
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    """Interactive chat-first workflow: upload requirements -> get results in chat."""
    cfg = _load_config(args)

    req_file   = getattr(args, "requirements", None)
    repo_url   = getattr(args, "repo", None)      or (cfg.project.repository if cfg.project else "")
    branch     = getattr(args, "branch", None)
    target_url = getattr(args, "target_url", None) or (cfg.target.url if cfg.target else "")
    yes        = getattr(args, "yes", False)

    from astlc.conversation import ConversationalOrchestrator

    def _update(msg: str) -> None:
        print(msg)

    orch = ConversationalOrchestrator(config=cfg, on_update=_update)

    # ── File ingestion ──────────────────────────────────────────────────────
    if not req_file:
        print("\nNo requirements file specified.")
        print("Usage:  agentic-stlc chat --requirements <file> [--repo URL] [--branch BRANCH]")
        req_file = input("\nRequirements file path: ").strip()
        if not req_file:
            print("ERROR: requirements file is required.")
            return 1

    print(f"\nIngesting: {req_file}")
    state = orch.ingest(path=req_file)

    if state.get("status") == "error":
        print(f"\nERROR: {state['error']}")
        return 1

    # Print the preview markdown
    print()
    print(state["markdown"])
    print()

    # ── Confirmation ─────────────────────────────────────────────────────────
    if not yes:
        try:
            answer = input("Proceed with full pipeline execution? [proceed/cancel]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "cancel"
        if answer not in ("proceed", "yes", "y"):
            print("Aborted.")
            return 0

    # ── Execute ───────────────────────────────────────────────────────────────
    print()
    result = orch.execute(
        state,
        repo_url=repo_url,
        branch=branch or None,
        target_url=target_url,
        auto_push=bool(repo_url),
    )

    if result.get("status") == "error":
        print(f"\nERROR at stage '{result.get('stage', '?')}': {result['error']}")
        return 1

    print()
    print(result.get("markdown", "Pipeline completed."))
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    """Set/check pipeline credentials and configuration."""
    action = getattr(args, "action", "show")

    if action == "check":
        from astlc.credential_validator import CredentialValidator
        repo_url = getattr(args, "repo", "") or os.environ.get("GITHUB_REPOSITORY", "")
        validator = CredentialValidator()
        report = validator.validate(repo_url=repo_url)

        print("\nCredential Check")
        print("=" * 40)
        _icon = lambda ok: "[OK]    " if ok else "[MISSING]"
        print(f"{_icon(report.github_token)} GITHUB_TOKEN{' (scope: ' + report.github_token_scope + ')' if report.github_token_scope else ''}")
        print(f"{_icon(report.lt_username)}  LT_USERNAME")
        print(f"{_icon(report.lt_access_key)} LT_ACCESS_KEY")
        print(f"{_icon(report.repo_url)}  Repository URL{': ' + report.repo_slug if report.repo_slug else ''}")

        if report.lt_credentials_valid is True:
            print("            LambdaTest API: verified OK")
        elif report.lt_credentials_valid is False:
            print("            LambdaTest API: INVALID credentials")

        if report.warnings:
            print("\nWarnings:")
            for w in report.warnings:
                print(f"  ! {w}")

        if report.errors:
            print("\nErrors:")
            for e in report.errors:
                print(f"  X {e}")
            print()
            print(report.onboarding_message() if hasattr(report, "onboarding_message") else "")
            return 1

        print("\nAll credentials valid. Ready to run.")
        return 0

    elif action == "set":
        key   = getattr(args, "key", "")
        value = getattr(args, "value", "")
        if not key or not value:
            print("Usage: agentic-stlc config set KEY VALUE")
            print("  Keys: GITHUB_TOKEN, LT_USERNAME, LT_ACCESS_KEY")
            return 1

        allowed = {"GITHUB_TOKEN", "LT_USERNAME", "LT_ACCESS_KEY"}
        if key not in allowed:
            print(f"Unknown key '{key}'. Allowed: {', '.join(sorted(allowed))}")
            return 1

        # Write to .env file in project root
        env_path = Path(".env")
        lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
        updated = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}"
                updated = True
                break
        if not updated:
            lines.append(f"{key}={value}")
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Set {key} in {env_path}")
        print("Load it in your shell: source .env  (or restart terminal)")
        return 0

    else:  # show
        cfg = _load_config(args)
        print("\nAgentic STLC Configuration")
        print("=" * 40)
        print(f"  project.name:       {cfg.project.name if cfg.project else '(not set)'}")
        print(f"  project.repository: {cfg.project.repository if cfg.project else '(not set)'}")
        print(f"  target.url:         {cfg.target.url if cfg.target else '(not set)'}")
        print(f"  execution.mode:     {cfg.execution.mode if cfg.execution else 'incremental'}")
        print()
        print("Environment:")
        for var in ("GITHUB_TOKEN", "LT_USERNAME", "LT_ACCESS_KEY"):
            val = os.environ.get(var, "")
            masked = (val[:4] + "***" + val[-4:]) if len(val) > 8 else ("***" if val else "(not set)")
            print(f"  {var}: {masked}")
        print()
        print("Run 'agentic-stlc config check' to verify credentials.")
        return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate config and check required tools."""
    cfg = _load_config(args)
    errors = cfg.validate()

    print(f"\nConfig validation: {'PASS' if not errors else 'FAIL'}")
    for e in errors:
        print(f"  ERROR: {e}")

    # Tool availability checks (ASCII-safe output for cross-platform)
    import shutil
    checks = [
        ("python3 / py",  sys.executable),
        ("kane-cli",      shutil.which("kane-cli") or ""),
        ("node",          shutil.which("node") or ""),
        ("git",           shutil.which("git") or ""),
    ]
    print("\nTool availability:")
    for name, path_or_cmd in checks:
        if path_or_cmd and (Path(path_or_cmd).exists() or shutil.which(path_or_cmd.split()[0])):
            print(f"  [OK]      {name}: {path_or_cmd}")
        else:
            found = shutil.which(name.split("/")[0].strip()) or shutil.which(name.split()[0])
            if found:
                print(f"  [OK]      {name}: {found}")
            else:
                print(f"  [MISSING] {name}: not found on PATH")

    he_candidates = ["./hyperexecute", "./hyperexecute.exe", "hyperexecute"]
    he_found = any(Path(c).exists() or bool(__import__('shutil').which(c.lstrip('./')))
                   for c in he_candidates)
    print(f"  {'[OK]     ' if he_found else '[MISSING]'} hyperexecute: {'found' if he_found else 'not found'}")

    # Config file check
    config_path = getattr(args, "config", None) or "agentic-stlc.config.yaml"
    print(f"\nConfig file: {config_path} ({'EXISTS' if Path(config_path).exists() else 'NOT FOUND - using defaults'})")
    print(f"  project.name:   {cfg.project.name if cfg.project else '(not set)'}")
    print(f"  target.url:     {cfg.target.url if cfg.target else '(not set)'}")
    print(f"  execution.mode: {cfg.execution.mode if cfg.execution else 'incremental'}")

    return 0 if not errors else 1


# ── Argument parser ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentic-stlc",
        description="Agentic STLC Platform -- autonomous QA orchestration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--config", "-c", metavar="PATH", help="Path to agentic-stlc.config.yaml")

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # run
    p_run = subparsers.add_parser("run", help="Execute full pipeline end-to-end")
    p_run.add_argument("--repo",         metavar="URL",    help="Repository URL (overrides config)")
    p_run.add_argument("--branch",       metavar="BRANCH", default="", help="Git branch")
    p_run.add_argument("--requirements", metavar="FILE",   help="Requirements file path")
    p_run.add_argument("--target-url",   metavar="URL",    dest="target_url", help="Application URL")
    p_run.add_argument("--full",         action="store_true", help="Run all scenarios (not incremental)")
    p_run.add_argument("--stages",       metavar="IDS",    help="Comma-separated stage IDs e.g. 2b,7a")

    # analyze
    p_ana = subparsers.add_parser("analyze", help="Run KaneAI requirement analysis (Stage 1)")
    p_ana.add_argument("--requirements", metavar="FILE", help="Requirements file path")

    # generate
    p_gen = subparsers.add_parser("generate", help="Generate Playwright tests from scenarios")
    p_gen.add_argument("--scenarios",  metavar="FILE", help="scenarios.json path")
    p_gen.add_argument("--target-url", metavar="URL",  dest="target_url", help="Application URL")

    # report
    p_rep = subparsers.add_parser("report", help="Regenerate reports from existing artifacts")
    p_rep.add_argument("--output", metavar="DIR", default="reports", help="Report output directory")

    # status
    subparsers.add_parser("status", help="Show latest pipeline status and verdicts")

    # init
    subparsers.add_parser("init", help="Scaffold agentic-stlc.config.yaml in current directory")

    # validate
    subparsers.add_parser("validate", help="Validate config and check tool availability")

    # config
    p_cfg = subparsers.add_parser("config", help="Show, set, or check credentials and configuration")
    p_cfg_sub = p_cfg.add_subparsers(dest="action", metavar="ACTION")
    p_cfg_sub.add_parser("show",  help="Show current configuration and masked credentials")
    p_cfg_check = p_cfg_sub.add_parser("check", help="Verify all credentials are set and valid")
    p_cfg_check.add_argument("--repo", metavar="URL", help="Repository URL to verify access for")
    p_cfg_set = p_cfg_sub.add_parser("set", help="Set a credential in .env file")
    p_cfg_set.add_argument("key",   help="Credential key (GITHUB_TOKEN, LT_USERNAME, LT_ACCESS_KEY)")
    p_cfg_set.add_argument("value", help="Value to set")

    # chat  (chat-first autonomous mode)
    p_chat = subparsers.add_parser("chat", help="Chat-first autonomous QA workflow: upload requirements -> results in chat")
    p_chat.add_argument("--requirements", metavar="FILE",   help="Requirements file path (txt/md/yaml/json)")
    p_chat.add_argument("--repo",         metavar="URL",    help="Repository URL")
    p_chat.add_argument("--branch",       metavar="BRANCH", help="Target branch (auto-generated if omitted)")
    p_chat.add_argument("--target-url",   metavar="URL",    dest="target_url", help="Application URL under test")
    p_chat.add_argument("--yes", "-y",    action="store_true", help="Skip confirmation prompt")

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
        "chat":     cmd_chat,
        "config":   cmd_config,
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
