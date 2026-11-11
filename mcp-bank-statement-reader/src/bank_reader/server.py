"""MCP server: Bank Statement Reader.

Run with:  uv run bank-reader-mcp
Claude Code: claude mcp add bank-reader -- uv --directory /path/to/mcp-bank-statement-reader run bank-reader-mcp
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import store
from .categoriser import ALL_CATEGORIES, categorise as categorise_one, extract_merchant
from .parser import StatementError, parse_pdf
from .subscriptions import find_recurring

mcp = MCPServer("bank-statement-reader")


def _apply_categories(only_unset_manual: bool = True) -> dict[str, int]:
    rules = store.load_rules()
    counts: dict[str, int] = defaultdict(int)
    for txn in store.query_transactions():
        if only_unset_manual and txn["manual_category"]:
            counts[txn["category"]] += 1
            continue
        new = categorise_one(txn["description"], txn["type"], rules)
        if new != txn["category"]:
            store.update_category(txn["id"], new, manual=False)
        counts[new] += 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


@mcp.tool()
def load_statement(pdf_path: str, password: str = "", account_label: str = "") -> dict:
    """Read a bank statement PDF and save its transactions locally.

    Args:
        pdf_path: Full path to the statement PDF on this computer.
        password: PDF password, if the bank protected the file.
        account_label: Optional short name for the account, e.g. "HDFC savings".

    Loading the same statement again is safe: transactions already saved are skipped.
    Every new transaction is put into a category straight away.
    """
    path = Path(pdf_path).expanduser().resolve()
    try:
        result = parse_pdf(path, password or None)
    except StatementError as exc:
        return {"ok": False, "error": str(exc)}

    rules = store.load_rules()
    rows = [
        {
            "id": t.id,
            "date": t.date.isoformat(),
            "description": t.description,
            "amount": t.amount,
            "type": t.type,
            "balance": t.balance,
            "merchant": extract_merchant(t.description),
            "category": categorise_one(t.description, t.type, rules),
        }
        for t in result.transactions
    ]
    added, skipped = store.insert_transactions(rows, source=path.name, account=account_label)

    return {
        "ok": bool(rows),
        "file": path.name,
        "transactions_found": len(rows),
        "added": added,
        "already_saved": skipped,
        "from_date": min((r["date"] for r in rows), default=None),
        "to_date": max((r["date"] for r in rows), default=None),
        "total_debits": round(sum(r["amount"] for r in rows if r["type"] == "debit"), 2),
        "total_credits": round(sum(r["amount"] for r in rows if r["type"] == "credit"), 2),
        "opening_balance": result.opening_balance,
        "warnings": result.warnings,
    }


@mcp.tool()
def categorise(redo_manual: bool = False) -> dict:
    """Put every saved transaction into a spending category using the current rules.

    Run this after adding a rule with set_category_rule. Categories you set by hand
    with set_transaction_category are kept unless redo_manual is true.
    Returns how many transactions fall in each category.
    """
    counts = _apply_categories(only_unset_manual=not redo_manual)
    return {"categories": counts, "total": sum(counts.values())}


@mcp.tool()
def find_subscriptions(min_occurrences: int = 2, month_from: str = "") -> dict:
    """Find repeat charges: subscriptions, EMIs, rent, SIPs, phone bills and similar.

    Args:
        min_occurrences: How many times a charge must appear to count (default 2).
        month_from: Only look at transactions from this month onwards, as YYYY-MM.

    Each result has the merchant, how often it is charged, the usual amount,
    when it is next expected and an estimated yearly cost. "low" confidence means
    only two charges were seen so far.
    """
    txns = store.query_transactions(txn_type="debit")
    if month_from:
        txns = [t for t in txns if t["date"][:7] >= month_from]
    found = find_recurring(txns, min_occurrences=min_occurrences)
    return {
        "subscriptions": found,
        "count": len(found),
        "total_yearly_cost": round(sum(s["yearly_cost"] for s in found), 2),
        "note": "Amounts are in the statement currency (usually INR).",
    }


@mcp.tool()
def spending_summary(month: str = "") -> dict:
    """Money in vs money out, and spend per category.

    Args:
        month: A month as YYYY-MM. Leave empty for all saved data.
    """
    txns = store.query_transactions(month=month)
    spend: dict[str, float] = defaultdict(float)
    income: dict[str, float] = defaultdict(float)
    for t in txns:
        (spend if t["type"] == "debit" else income)[t["category"]] += t["amount"]
    total_out = round(sum(spend.values()), 2)
    total_in = round(sum(income.values()), 2)
    by_category = [
        {"category": c, "amount": round(a, 2),
         "share_percent": round(a * 100 / total_out, 1) if total_out else 0.0}
        for c, a in sorted(spend.items(), key=lambda kv: -kv[1])
    ]
    months = sorted({t["date"][:7] for t in txns})
    return {
        "period": month or (f"{months[0]} to {months[-1]}" if months else "no data"),
        "money_in": total_in,
        "money_out": total_out,
        "net_saved": round(total_in - total_out, 2),
        "spend_by_category": by_category,
        "money_in_by_category": {c: round(a, 2) for c, a in income.items()},
        "transaction_count": len(txns),
    }


@mcp.tool()
def list_transactions(
    month: str = "",
    category: str = "",
    search: str = "",
    type: str = "",
    limit: int = 50,
) -> dict:
    """List saved transactions, newest first.

    Args:
        month: Filter by month, YYYY-MM.
        category: Filter by category name, e.g. "Food & Dining".
        search: Text to look for in the description or merchant, e.g. "swiggy".
        type: "debit" or "credit".
        limit: Most rows to return (default 50, max 500).
    """
    limit = max(1, min(limit, 500))
    rows = store.query_transactions(month=month, category=category, search=search,
                                    txn_type=type, limit=limit)
    keep = ("id", "date", "description", "amount", "type", "merchant", "category", "account")
    return {"transactions": [{k: r[k] for k in keep} for r in rows], "count": len(rows)}


@mcp.tool()
def set_category_rule(keyword: str, category: str) -> dict:
    """Teach a new rule: any transaction whose description has this keyword goes to this category.

    Example: keyword "RAMESH" category "Rent" for monthly UPI payments to your landlord.
    Your rules always win over the built-in ones. All saved transactions are re-sorted right away.
    """
    keyword = keyword.strip().upper()
    category = category.strip()
    if not keyword or not category:
        return {"ok": False, "error": "Both keyword and category are needed."}
    rules = store.load_rules()
    rules[keyword] = category
    store.save_rules(rules)
    counts = _apply_categories()
    return {"ok": True, "rule": {keyword: category}, "all_rules": rules,
            "now_in_category": counts.get(category, 0)}


@mcp.tool()
def remove_category_rule(keyword: str) -> dict:
    """Delete one of your own keyword rules and re-sort saved transactions."""
    rules = store.load_rules()
    removed = rules.pop(keyword.strip().upper(), None)
    store.save_rules(rules)
    _apply_categories()
    return {"ok": removed is not None, "all_rules": rules}


@mcp.tool()
def set_transaction_category(transaction_id: str, category: str) -> dict:
    """Change the category of one transaction by hand (use the id from list_transactions).

    A category set this way is kept even when rules are re-applied.
    """
    store.update_category(transaction_id, category.strip(), manual=True)
    return {"ok": True, "transaction_id": transaction_id, "category": category.strip()}


@mcp.tool()
def list_statements() -> dict:
    """Show which statement files have been loaded and the dates they cover."""
    return {"statements": store.list_statements()}


@mcp.tool()
def delete_statement(file_name: str) -> dict:
    """Remove all transactions that came from one statement file (use the name from list_statements)."""
    removed = store.delete_statement(file_name)
    return {"ok": removed > 0, "transactions_removed": removed}


@mcp.tool()
def clear_all_data(confirm: bool = False) -> dict:
    """Delete every saved transaction. Pass confirm=true to really do it. Your keyword rules are kept."""
    if not confirm:
        return {"ok": False, "error": "Nothing deleted. Call again with confirm=true to delete all saved transactions."}
    return {"ok": True, "transactions_removed": store.clear_all()}


@mcp.resource("bank://categories")
def categories_resource() -> str:
    """Built-in category names plus your own keyword rules."""
    rules = store.load_rules()
    lines = ["Built-in categories:", *[f"- {c}" for c in ALL_CATEGORIES], "", "Your rules:"]
    lines += [f"- {k} -> {v}" for k, v in sorted(rules.items())] or ["- (none yet)"]
    return "\n".join(lines)


@mcp.prompt()
def monthly_review(month: str) -> str:
    """A ready-made request for a full review of one month's spending."""
    return (
        f"Please review my spending for {month} (YYYY-MM). "
        f"1) Call spending_summary for {month}. "
        "2) Call find_subscriptions and point out any I may have forgotten about. "
        "3) List the 5 biggest debits that month with list_transactions. "
        "4) Give me 3 simple, practical ideas to save money next month. "
        "Show amounts in rupees with Indian digit grouping (e.g. 1,23,456)."
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
