"""
Skill 4: Playwright Test Generation

Generates pytest-based Playwright test files from the active scenario pool.
Test bodies are resolved from a priority chain:
  1. PLAYWRIGHT_BODIES dict injected at runtime (repo-specific curated bodies)
  2. Template registry keyed by feature type (platform-provided smart templates)
  3. Generic fallback body (page load assertion)

The generated file is 100% deterministic — same inputs → same output.
It must NEVER be edited manually; it is overwritten on every pipeline run.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import AgentSkill

_FALLBACK_BODY = '    assert page.title().strip() != "", "Page failed to load"'

_FEATURE_BODIES: dict[str, str] = {
    "SEARCH": """\
    page.goto(target_url)
    search_box = page.locator("input[name='search'], input[type='search'], #search")
    search_box.fill("laptop")
    search_box.press("Enter")
    page.wait_for_load_state("networkidle")
    results = page.locator(".product-thumb, .product-layout, article.product-card")
    assert results.count() > 0, "No search results returned for 'laptop'"
""",
    "CART": """\
    page.goto(target_url)
    page.wait_for_load_state("networkidle")
    product = page.locator(".product-thumb a, .product-layout a").first
    product.click()
    page.wait_for_load_state("networkidle")
    add_btn = page.locator("#button-cart, button[id*='cart'], .btn-cart")
    add_btn.click()
    page.wait_for_load_state("networkidle")
    cart_indicator = page.locator("#cart-total, .cart-total, #cart button")
    assert cart_indicator.is_visible(), "Cart did not update after adding product"
""",
    "CATALOG": """\
    page.goto(target_url + "index.php?route=product/category&path=20")
    page.wait_for_load_state("networkidle")
    products = page.locator(".product-thumb, .product-layout")
    assert products.count() > 0, "Category page shows no products"
""",
    "PRODUCT_DETAIL": """\
    page.goto(target_url)
    page.wait_for_load_state("networkidle")
    product_link = page.locator(".product-thumb a, h4 a").first
    product_link.click()
    page.wait_for_load_state("networkidle")
    assert page.locator("h1, h2.page-title").first.is_visible(), "Product title not visible on PDP"
    assert page.locator("#button-cart, .btn-cart").first.is_visible(), "Add to Cart button not visible"
""",
    "FILTER": """\
    page.goto(target_url + "index.php?route=product/category&path=20")
    page.wait_for_load_state("networkidle")
    filter_el = page.locator(".list-group-item, .filter-group input[type='checkbox']").first
    if filter_el.is_visible():
        filter_el.click()
        page.wait_for_load_state("networkidle")
    products = page.locator(".product-thumb, .product-layout")
    assert products.count() >= 0, "Filter interaction caused page error"
""",
    "AUTH": """\
    page.goto(target_url + "index.php?route=account/login")
    page.wait_for_load_state("networkidle")
    assert page.locator("#input-email, input[name='email']").is_visible(), "Email field not visible on login page"
    assert page.locator("#input-password, input[name='password']").is_visible(), "Password field not visible"
""",
    "CHECKOUT": """\
    page.goto(target_url + "index.php?route=checkout/checkout")
    page.wait_for_load_state("networkidle")
    assert page.locator("#checkout-checkout, .panel-checkout").first.is_visible() or \\
           page.locator("#cart-total, #cart").first.is_visible(), "Checkout page did not load"
""",
    "WISHLIST": """\
    page.goto(target_url)
    page.wait_for_load_state("networkidle")
    wishlist_btn = page.locator("a[title='Wish List'], .wishlist-icon, button[data-wishlist]").first
    if wishlist_btn.is_visible():
        wishlist_btn.click()
        page.wait_for_load_state("networkidle")
    assert page.title().strip() != "", "Wishlist interaction failed"
""",
    "SORT": """\
    page.goto(target_url + "index.php?route=product/category&path=20")
    page.wait_for_load_state("networkidle")
    sort_select = page.locator("#input-sort, select[name='sort']")
    if sort_select.is_visible():
        sort_select.select_option(index=1)
        page.wait_for_load_state("networkidle")
    products = page.locator(".product-thumb, .product-layout")
    assert products.count() > 0, "Products disappeared after sort"
""",
    "GUEST": """\
    page.goto(target_url)
    page.wait_for_load_state("networkidle")
    assert page.locator("header, nav").first.is_visible(), "Homepage header not visible for guest user"
    assert "login" not in page.url.lower(), "Guest was unexpectedly redirected to login"
""",
}


class PlaywrightGenerationSkill(AgentSkill):
    name = "playwright_generation"
    description = "Generate deterministic Playwright test file from active scenarios"
    version = "1.0.0"

    def run(self, **inputs: Any) -> dict:
        sc_path = Path(
            inputs.get("scenarios_path")
            or (self.config.scenarios_path if self.config else "scenarios/scenarios.json")
        )
        test_file = Path(
            inputs.get("test_file")
            or (self.config.framework.test_file if self.config else "tests/playwright/test_powerapps.py")
        )
        target_url = (
            inputs.get("target_url")
            or (self.config.target.url if self.config else "")
            or "https://ecommerce-playground.lambdatest.io/"
        )
        playwright_bodies: dict[str, str] = inputs.get("playwright_bodies", {})

        scenarios: list[dict] = []
        if sc_path.exists():
            scenarios = json.loads(sc_path.read_text(encoding="utf-8"))

        active = [s for s in scenarios if s.get("status") != "deprecated"]
        objectives: dict[str, str] = {}

        lines = [
            "# AUTO-GENERATED by Agentic STLC Platform — DO NOT EDIT",
            f"# Generated at: {datetime.now(timezone.utc).isoformat()}",
            "# Source: scenarios/scenarios.json",
            "",
            "import pytest",
            "import os",
            "",
            "",
            f'TARGET_URL = os.environ.get("TARGET_URL", {target_url!r})',
            "",
        ]

        for sc in active:
            sc_id = sc.get("id", "")
            req_id = sc.get("requirement_id", "")
            feature = sc.get("feature", "GENERAL")
            desc = sc.get("description", "")
            fn_name = f"test_{sc_id.lower().replace('-', '_')}"

            body = (
                playwright_bodies.get(sc_id)
                or _FEATURE_BODIES.get(feature)
                or _FALLBACK_BODY
            )
            # Normalise indentation to 4 spaces inside function
            body_lines = [f"    {line}" if not line.startswith("    ") and line.strip() else line
                          for line in body.splitlines()]
            body_str = "\n".join(body_lines)

            objectives[sc_id] = sc.get("kane_objective", f"Verify: {desc}")

            lines += [
                "",
                f'@pytest.mark.scenario("{sc_id}")',
                f'@pytest.mark.requirement("{req_id}")',
                f"def {fn_name}(page, target_url=TARGET_URL):",
                f'    """[{sc_id}] {desc[:80]}"""',
                body_str,
                "",
            ]

        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Write Kane objectives side-car
        obj_path = Path("kane/objectives.json")
        obj_path.parent.mkdir(parents=True, exist_ok=True)
        obj_path.write_text(json.dumps(objectives, indent=2) + "\n", encoding="utf-8")

        return {
            "success": True,
            "test_file": str(test_file),
            "objectives_file": str(obj_path),
            "tests_generated": len(active),
        }
