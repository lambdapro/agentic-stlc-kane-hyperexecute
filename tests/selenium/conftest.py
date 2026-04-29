import os
import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


LT_USERNAME = os.environ.get("LT_USERNAME", "")
LT_ACCESS_KEY = os.environ.get("LT_ACCESS_KEY", "")
LAMBDATEST_GRID = f"https://{LT_USERNAME}:{LT_ACCESS_KEY}@hub.lambdatest.com/wd/hub"
USE_REMOTE = os.environ.get("USE_REMOTE_GRID", "").lower() in {"1", "true", "yes"}
if not os.environ.get("USE_REMOTE_GRID"):
    USE_REMOTE = bool(LT_USERNAME and LT_ACCESS_KEY)
HEADLESS = os.environ.get("HEADLESS", "true").lower() in {"1", "true", "yes"}


def pytest_configure(config):
    config.addinivalue_line("markers", "scenario(id): scenario ID this test covers")
    config.addinivalue_line("markers", "requirement(id): requirement ID this test covers")


@pytest.fixture(scope="function")
def driver(request):
    if USE_REMOTE:
        lt_options = {
            "browserName": "Chrome",
            "browserVersion": "latest",
            "LT:Options": {
                "username": LT_USERNAME,
                "accessKey": LT_ACCESS_KEY,
                "platform": "Windows 11",
                "build": "Agentic STLC - eCommerce Playground",
                "project": "agentic-stlc",
                "name": request.node.name,
                "selenium_version": "4.0.0",
                "w3c": True,
                "headless": False,
            },
        }
        driver = webdriver.Remote(
            command_executor=LAMBDATEST_GRID,
            options=webdriver.ChromeOptions(),
        )
        driver.execute_script(
            "lambda-name=" + request.node.name
        )
    else:
        opts = Options()
        if HEADLESS:
            opts.add_argument("--headless")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1440,2200")
        driver = webdriver.Chrome(options=opts)

    driver.set_page_load_timeout(30)
    driver.implicitly_wait(10)
    driver.set_window_size(1440, 2200)

    yield driver

    # Report pass/fail to LambdaTest
    if USE_REMOTE:
        status = "passed" if request.node.rep_call.passed else "failed"
        driver.execute_script(f"lambda-status={status}")

    driver.quit()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, "rep_" + rep.when, rep)
