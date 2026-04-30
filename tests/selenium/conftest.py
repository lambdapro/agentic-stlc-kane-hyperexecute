import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


def _build_name():
    """Consistent build label shared by Kane AI and Selenium sessions in the same run."""
    run_number = os.environ.get("GITHUB_RUN_NUMBER", "")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"Agentic SDLC #{run_number} | {today}" if run_number else f"Agentic SDLC | {today}"


def pytest_configure(config):
    config.addinivalue_line("markers", "scenario(id): scenario ID this test covers")
    config.addinivalue_line("markers", "requirement(id): requirement ID this test covers")


@pytest.fixture(scope="function")
def driver(request):
    lt_username = os.environ.get("LT_USERNAME", "")
    lt_access_key = os.environ.get("LT_ACCESS_KEY", "")

    # Build a consistent session name that aligns with the traceability matrix:
    # SC-001 | TC-001 | test_sc_001_<slug>
    # Markers are available at setup time via request.node.
    scenario_marker = request.node.get_closest_marker("scenario")
    requirement_marker = request.node.get_closest_marker("requirement")
    _scenario_id = scenario_marker.args[0] if scenario_marker else "unknown"
    _tc_id = f"TC-{_scenario_id.split('-')[1]}" if "-" in _scenario_id else "TC-000"
    session_name = f"{_scenario_id} | {_tc_id} | {request.node.name}"

    lt_options = {
        "username": lt_username,
        "accessKey": lt_access_key,
        "platformName": "Windows 10",
        "browserName": "Chrome",
        "browserVersion": "latest",
        "build": _build_name(),
        "name": session_name,
        "project": "Agentic SDLC",
        "video": True,
        "visual": True,
        "network": True,
        "console": True,
    }

    options = Options()
    options.set_capability("LT:Options", lt_options)

    hub_url = f"https://{lt_username}:{lt_access_key}@hub.lambdatest.com/wd/hub"
    d = webdriver.Remote(command_executor=hub_url, options=options)

    yield d

    session_id = d.session_id
    session_link = f"https://automation.lambdatest.com/test?testID={session_id}"

    scenario_marker = request.node.get_closest_marker("scenario")
    requirement_marker = request.node.get_closest_marker("requirement")
    scenario_id = scenario_marker.args[0] if scenario_marker else "unknown"
    requirement_id = requirement_marker.args[0] if requirement_marker else "unknown"

    rep = getattr(request.node, "rep_call", None)
    status = "passed" if (rep and rep.passed) else "failed"

    # Mark the LambdaTest session as passed or failed so the Automate dashboard
    # and traceability report reflect the actual assertion outcome.
    try:
        d.execute_script(f"lambda-status={status}")
    except Exception:
        pass

    Path("reports").mkdir(exist_ok=True)
    Path(f"reports/kane_result_{scenario_id}.json").write_text(
        json.dumps(
            {
                "requirement_id": requirement_id,
                "scenario_id": scenario_id,
                "test_case_id": f"TC-{scenario_id.split('-')[1]}",
                "status": status,
                "link": session_link,
                "one_liner": "",
                "duration": None,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    d.quit()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, "rep_" + rep.when, rep)
