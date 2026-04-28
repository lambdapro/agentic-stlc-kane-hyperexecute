import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", default="requirements/analyzed_requirements.json")
    parser.add_argument("--scenarios", default="scenarios/scenarios.json")
    return parser.parse_args()


def load_json(path, default):
    file_path = Path(path)
    if not file_path.exists():
        return default
    content = file_path.read_text(encoding="utf-8").strip()
    if not content:
        return default
    return json.loads(content)


def title_and_steps(requirement):
    requirement_id = requirement["id"]
    description = requirement["description"].lower()
    if requirement_id == "AC-001" or "available products" in description:
        return (
            "Navigate to product section and view available products",
            [
                "Navigate to https://ecommerce-playground.lambdatest.io/",
                "Locate and click the Shop navigation link",
                "Verify the products listing page loads",
                "Verify multiple product tiles are visible on the page",
            ],
            "A list of available products is displayed with product tiles and filter options visible",
        )
    if "use filters" in description:
        return (
            "Filter products by category",
            [
                "Navigate to https://ecommerce-playground.lambdatest.io/",
                "Go to a category page",
                "Locate filter options on the sidebar",
                "Select a filter",
                "Verify the product list updates to show filtered results",
            ],
            "Filtered results are displayed after applying a filter",
        )
    if "click on a product" in description:
        return (
            "Click a product to view details",
            [
                "Navigate to https://ecommerce-playground.lambdatest.io/",
                "Search for a product",
                "Click on any product image or title",
                "Verify the product detail page loads",
                "Verify price and description information is visible",
            ],
            "Product detail page is displayed showing specific item information",
        )
    if "without logging in" in description:
        return (
            "View product highlights without logging in",
            [
                "Navigate to https://ecommerce-playground.lambdatest.io/ without logging in",
                "Scroll through the homepage",
                "Verify featured products or carousel is visible",
                "Verify no login prompt blocks the content",
            ],
            "Product highlights are visible on the page without requiring login",
        )
    return (
        "Search results are relevant to selected filters or criteria",
        [
            "Navigate to https://ecommerce-playground.lambdatest.io/",
            "Search for an item",
            "Apply a filter",
            "Verify the displayed items are relevant to the selected filter",
            "Check that item descriptions match the search term",
        ],
        "Results shown are relevant to the selected category or search term",
    )


def main():
    args = parse_args()
    requirements = load_json(args.requirements, [])
    scenarios = load_json(args.scenarios, [])
    existing_by_requirement = {scenario["requirement_id"]: scenario for scenario in scenarios}
    today = datetime.now(timezone.utc).date().isoformat()

    updated = []
    counts = {"active": 0, "updated": 0, "new": 0, "deprecated": 0}
    active_requirement_ids = set()

    for index, requirement in enumerate(requirements, start=1):
        active_requirement_ids.add(requirement["id"])
        title, steps, expected = title_and_steps(requirement)
        scenario = existing_by_requirement.get(requirement["id"])
        status = "new"
        if scenario:
            status = "active" if scenario.get("source_description") == requirement["description"] else "updated"
        else:
            scenario = {}

        record = {
            "id": scenario.get("id", f"SC-{index:03d}"),
            "requirement_id": requirement["id"],
            "title": title,
            "steps": steps,
            "expected_result": expected,
            "status": status,
            "kane_objective": requirement["description"],
            "kane_url": requirement["url"],
            "kane_last_status": requirement.get("kane_status", "pending"),
            "test_case_id": scenario.get("test_case_id", f"TC-{index:03d}"),
            "last_verified": today,
            "source_description": requirement["description"],
        }

        if requirement.get("kane_status") == "failed":
            record["kane_failure_reason"] = requirement.get("kane_summary", "")

        updated.append(record)
        counts[status] += 1

    for scenario in scenarios:
        if scenario["requirement_id"] in active_requirement_ids:
            continue
        deprecated = dict(scenario)
        deprecated["status"] = "deprecated"
        updated.append(deprecated)
        counts["deprecated"] += 1

    output = Path(args.scenarios)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")

    print(
        f"active={counts['active']} updated={counts['updated']} new={counts['new']} deprecated={counts['deprecated']}"
    )


if __name__ == "__main__":
    main()
