# Bank Statement Reader (MCP server)

A small MCP server that reads your bank statement PDFs on your own laptop. It
sorts spends into categories and finds repeat charges (subscriptions, EMIs,
rent, SIPs) that you may have forgotten about.

Ask Claude things like:

- "Load ~/Downloads/oct_statement.pdf, the password is ..."
- "What subscriptions am I paying for, and what do they cost in a year?"
- "How much did I spend on food in October?"
- "Payments to HOUSE OWNER are my rent, remember that."

## Privacy, please read

- PDFs are read on your laptop. Transactions are saved in a local SQLite file at
  `~/.bank-reader/transactions.db` (change it with `BANK_READER_HOME`).
- **But** whatever a tool returns (amounts, descriptions, merchant names) is sent
  to the AI model so it can answer you. Do not use this with data you are not
  comfortable sharing with your AI provider.
- `.gitignore` blocks `*.pdf` and `*.db`, so real statements never get committed.

## Setup

Needs Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
cd ~/mcp-bank-statement-reader
uv sync
uv run pytest            # all tests should pass
```

### Add it to Claude Code

```bash
claude mcp add bank-reader -- uv --directory ~/mcp-bank-statement-reader run bank-reader-mcp
```

Then start `claude` and type `/mcp` to check that `bank-reader` is connected.

### Add it to Claude Desktop

In `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "bank-reader": {
      "command": "uv",
      "args": ["--directory", "/Users/<you>/mcp-bank-statement-reader", "run", "bank-reader-mcp"]
    }
  }
}
```

### Try it without real data

```bash
uv run python -m bank_reader.sample sample_statement.pdf
```

This makes a fake 3-month statement. Ask Claude to load it and find the
subscriptions.

### Test with the MCP Inspector

```bash
npx @modelcontextprotocol/inspector uv --directory ~/mcp-bank-statement-reader run bank-reader-mcp
```

This opens a web page where you can call each tool by hand. It is the best way
to learn what the AI actually sees.

## What the server offers

### Tools

| Tool | What it does |
|---|---|
| `load_statement(pdf_path, password, account_label)` | Reads a PDF and saves its transactions. Safe to run twice; no duplicates. |
| `categorise(redo_manual)` | Re-sorts all transactions into categories with the current rules. |
| `find_subscriptions(min_occurrences, month_from)` | Finds weekly, monthly, quarterly and yearly repeat charges, with yearly cost and next due date. |
| `spending_summary(month)` | Money in, money out, savings, and spend per category. |
| `list_transactions(month, category, search, type, limit)` | Look up transactions. |
| `set_category_rule(keyword, category)` | Teach a rule, e.g. "HOUSE OWNER" goes to "Rent". |
| `remove_category_rule(keyword)` | Delete one of your rules. |
| `set_transaction_category(transaction_id, category)` | Fix one transaction by hand. |
| `list_statements()` / `delete_statement(file_name)` | See or remove loaded files. |
| `clear_all_data(confirm)` | Wipe all saved transactions. |

### Resource

- `bank://categories`: the built-in categories plus your own rules.

### Prompt

- `monthly_review(month)`: a ready-made request for a full month review.

## How it works

```
PDF ──► parser.py ──► categoriser.py ──► store.py (SQLite) ──► subscriptions.py
         lines →         keyword rules       local file           repeat-charge
         transactions    + merchant name                          detection
                                  ▲
                         server.py exposes all of this as MCP tools
```

- **parser.py**: reads PDF text line by line. A line is a transaction when it
  starts with a date and has money amounts. Debit or credit is worked out from
  Withdrawal/Deposit columns, Dr/Cr markers, or the change in running balance.
  Long descriptions that wrap onto the next line are joined back.
- **categoriser.py**: keyword rules for common Indian merchants (Swiggy,
  Zomato, BESCOM, Airtel, Groww, IRCTC ...). Your own rules always win.
- **subscriptions.py**: groups debits by merchant. A group counts as a repeat
  charge when amounts are within 15% of each other and the gaps fit a
  weekly, monthly, quarterly or yearly pattern.

## Limits

- Scanned (image only) PDFs have no text, so they need OCR first.
- Every bank's layout is a bit different. If a statement does not load well,
  look at the `warnings` from `load_statement`, then add a test in
  `tests/test_parser.py` with a few sample lines (with your numbers changed)
  and adjust `parser.py`.
- Amounts are stored as they appear in the statement (usually INR).

## Ideas to extend

- CSV and Excel statement support
- Credit card statements
- A `budget` tool that warns when a category goes over a limit
- OCR for scanned PDFs (`pytesseract`)

## Project layout

```
src/bank_reader/
  server.py         MCP tools, resource, prompt
  parser.py         PDF → transactions
  categoriser.py    categories + merchant names
  subscriptions.py  repeat charge detection
  store.py          SQLite + rules.json
  sample.py         fake statement for trying things out
tests/              pytest tests (use a temporary data folder, never your real one)
```
