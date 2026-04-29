import os
import shutil
import subprocess
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "scenario(id): scenario ID this test covers")
    config.addinivalue_line("markers", "requirement(id): requirement ID this test covers")


@pytest.fixture(scope="session", autouse=True)
def kane_auth():
    username = os.environ.get("LT_USERNAME", "")
    access_key = os.environ.get("LT_ACCESS_KEY", "")
    if username and access_key:
        kane = shutil.which("kane-cli") or "kane-cli"
        subprocess.run(
            [kane, "login", "--username", username, "--access-key", access_key],
            check=False,
        )


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, "rep_" + rep.when, rep)
