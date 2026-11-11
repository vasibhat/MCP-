"""End-to-end tests of the MCP tools against the fake sample statement."""

import asyncio

from bank_reader import server


def test_load_statement_and_reload_is_safe(sample_pdf):
    first = server.load_statement(str(sample_pdf), account_label="Sample savings")
    assert first["ok"] is True
    assert first["added"] == first["transactions_found"] == 34
    assert first["from_date"] == "2026-08-01" and first["to_date"] == "2026-10-28"
    assert first["total_credits"] == 85_000 * 3 + 1_499

    again = server.load_statement(str(sample_pdf))
    assert again["added"] == 0 and again["already_saved"] == 34


def test_load_statement_bad_path():
    result = server.load_statement("/no/such/file.pdf")
    assert result["ok"] is False and "not found" in result["error"]


def test_find_subscriptions_on_sample(sample_pdf):
    server.load_statement(str(sample_pdf))
    result = server.find_subscriptions()
    merchants = {s["merchant"] for s in result["subscriptions"]}
    assert {"NETFLIX", "SPOTIFY", "GROWW", "AIRTEL", "HOUSE"} <= merchants
    assert "AMAZON" not in merchants
    assert all(s["frequency"] == "monthly" for s in result["subscriptions"])
    # Rent is the biggest repeat charge.
    assert result["subscriptions"][0]["merchant"] == "HOUSE"


def test_rules_summary_and_manual_category(sample_pdf):
    server.load_statement(str(sample_pdf))
    oct_before = server.spending_summary("2026-10")
    cats = {c["category"] for c in oct_before["spend_by_category"]}
    assert "Transfers" in cats  # rent goes here until we teach a rule

    rule = server.set_category_rule("house owner", "Rent")
    assert rule["ok"] and rule["now_in_category"] == 3

    oct_after = server.spending_summary("2026-10")
    rent = next(c for c in oct_after["spend_by_category"] if c["category"] == "Rent")
    assert rent["amount"] == 25_000
    assert oct_after["money_in"] == 85_000 + 1_499

    netflix = server.list_transactions(search="netflix", limit=1)["transactions"][0]
    server.set_transaction_category(netflix["id"], "Fun")
    server.categorise()  # re-applying rules keeps the hand-set category
    assert server.list_transactions(category="Fun")["count"] == 1
    server.categorise(redo_manual=True)
    assert server.list_transactions(category="Fun")["count"] == 0

    assert server.remove_category_rule("HOUSE OWNER")["ok"] is True
    assert server.list_transactions(category="Rent")["count"] == 0


def test_delete_and_clear(sample_pdf):
    server.load_statement(str(sample_pdf))
    assert server.list_statements()["statements"][0]["source"] == "sample_statement.pdf"
    assert server.clear_all_data()["ok"] is False
    assert server.delete_statement("sample_statement.pdf")["transactions_removed"] == 34
    server.load_statement(str(sample_pdf))
    assert server.clear_all_data(confirm=True)["transactions_removed"] == 34


def test_server_exposes_tools_resource_and_prompt():
    tools = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert {"load_statement", "categorise", "find_subscriptions", "spending_summary"} <= tools
    resources = [str(r.uri) for r in asyncio.run(server.mcp.list_resources())]
    assert "bank://categories" in resources
    prompts = {p.name for p in asyncio.run(server.mcp.list_prompts())}
    assert "monthly_review" in prompts
