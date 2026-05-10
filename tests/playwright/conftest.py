import json
import os
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


def _build_name():
    run_number = os.environ.get("GITHUB_RUN_NUMBER", "")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"Agentic STLC #{run_number} | {today}" if run_number else f"Agentic STLC | {today}"


def _session_name(request) -> str:
    scenario_marker = request.node.get_closest_marker("scenario")
    scenario_id = scenario_marker.args[0] if scenario_marker else "unknown"
    tc_id = f"TC-{scenario_id.split('-')[1]}" if "-" in scenario_id else "TC-000"
    return f"{scenario_id} | {tc_id} | {request.node.name}"


def pytest_configure(config):
    config.addinivalue_line("markers", "scenario(id): scenario ID this test covers")
    config.addinivalue_line("markers", "requirement(id): requirement ID this test covers")


def _m365_login(page, url: str) -> None:
    """Handle Microsoft 365 login flow for Power Apps access."""
    username = os.environ.get("M365_USERNAME", "")
    password = os.environ.get("M365_PASSWORD", "")
    if not username or not password:
        return

    page.goto(url)
    # Microsoft login: fill email
    email_input = page.locator("input[type='email'], input[name='loginfmt']")
    if email_input.count() > 0:
        email_input.first.fill(username)
        page.get_by_role("button", name="Next").click()
        page.wait_for_timeout(1000)

    # Fill password
    pwd_input = page.locator("input[type='password'], input[name='passwd']")
    if pwd_input.count() > 0:
        pwd_input.first.fill(password)
        page.get_by_role("button", name="Sign in").click()
        page.wait_for_timeout(1500)

    # Handle "Stay signed in?" prompt
    stay_signed = page.get_by_role("button", name="Yes")
    if stay_signed.count() > 0:
        stay_signed.click()

    page.wait_for_load_state("networkidle", timeout=30000)


@pytest.fixture(scope="function")
def page(request):
    lt_username = os.environ.get("LT_USERNAME", "")
    lt_access_key = os.environ.get("LT_ACCESS_KEY", "")

    capabilities = {
        "browserName": "Chrome",
        "browserVersion": "latest",
        "LT:Options": {
            "platform": "Windows 10",
            "build": _build_name(),
            "name": _session_name(request),
            "project": "Agentic STLC — Power Apps",
            "user": lt_username,
            "accessKey": lt_access_key,
            "video": True,
            "visual": True,
            "network": True,
            "console": True,
        },
    }
    cdp_url = (
        f"wss://cdp.lambdatest.com/playwright"
        f"?capabilities={urllib.parse.quote(json.dumps(capabilities))}"
    )

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url)
        context = browser.new_context()
        pw_page = context.new_page()

        yield pw_page

        scenario_marker = request.node.get_closest_marker("scenario")
        requirement_marker = request.node.get_closest_marker("requirement")
        scenario_id = scenario_marker.args[0] if scenario_marker else "unknown"
        requirement_id = requirement_marker.args[0] if requirement_marker else "unknown"

        rep = getattr(request.node, "rep_call", None)
        status = "passed" if (rep and rep.passed) else "failed"

        try:
            pw_page.evaluate(f"() => {{ window['lambda-status'] = '{status}'; }}")
        except Exception:
            pass

        session_id = context.browser.version  # placeholder; real session ID from LT dashboard
        session_link = f"https://automation.lambdatest.com/test?build={_build_name()}"

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

        pw_page.close()
        context.close()
        browser.close()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, "rep_" + rep.when, rep)
