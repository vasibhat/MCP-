"""Read transactions out of a bank statement PDF.

Every bank lays out its statement a little differently, so this parser does not
depend on one fixed layout. It reads the PDF line by line and treats a line as
a transaction when it:

  * starts with a date (01/10/2026, 01-10-26, 01 Oct 2026, 01-Oct-2026 ...), and
  * has at least one money amount with two decimals (450.00, 1,23,456.78).

Which side the money went (debit or credit) is decided in this order:
  1. separate Withdrawal / Deposit columns, where one of them is 0.00
  2. a "Dr" / "Cr" marker next to the amount
  3. how the running balance changed from the previous row
  4. words in the description (SALARY, REFUND, INTEREST ...)
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

DATE_RE = re.compile(
    r"^\s*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\d{1,2}[ \-][A-Za-z]{3,9}[ \-,]+\d{2,4})(?=\s|$)"
)
DATE_FORMATS = [
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
    "%d %b %Y", "%d-%b-%Y", "%d %b %y", "%d-%b-%y",
    "%d %B %Y", "%d-%B-%Y", "%d %B %y", "%d-%B-%y",
]
AMOUNT_RE = re.compile(
    r"(?<![\w.,/])(\d{1,3}(?:,\d{2,3})+\.\d{2}|\d+\.\d{2})(?:\s*(Dr|Cr|DR|CR)\b)?(?![\w.,/])"
)
SKIP_ROW_RE = re.compile(
    r"^(opening balance|closing balance|balance b/?f|balance c/?f|b/f|c/f|"
    r"balance forward|brought forward|carried forward|total)",
    re.IGNORECASE,
)
OPENING_BALANCE_RE = re.compile(r"opening balance", re.IGNORECASE)
NOISE_RE = re.compile(
    r"(page \d+|statement|account (no|number|name)|customer|branch|ifsc|micr|"
    r"generated|narration|withdrawal|deposit|balance|computer generated|"
    r"date\s+(description|particulars|narration))",
    re.IGNORECASE,
)
CREDIT_WORDS = re.compile(
    r"\b(salary|sal|refund|reversal|interest|int\.?pd|cashback|dividend|neft cr|imps cr|"
    r"upi cr|by transfer|credited|deposit)\b",
    re.IGNORECASE,
)
MAX_CONTINUATION_LINES = 2


@dataclass
class Transaction:
    date: date
    description: str
    amount: float
    type: str  # "debit" or "credit"
    balance: float | None = None
    id: str = ""


@dataclass
class ParseResult:
    transactions: list[Transaction] = field(default_factory=list)
    opening_balance: float | None = None
    warnings: list[str] = field(default_factory=list)


class StatementError(Exception):
    """Raised when a PDF cannot be opened or read."""


def parse_date(text: str) -> date | None:
    cleaned = re.sub(r"[ ,]+", " ", text.strip())
    for candidate in {cleaned, text.strip()}:
        for fmt in DATE_FORMATS:
            try:
                value = datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
            if 2000 <= value.year <= 2100:
                return value
    return None


def to_amount(text: str) -> float:
    return round(float(text.replace(",", "")), 2)


def _strip_leading_date(text: str) -> str:
    """Remove a second date (the 'value date' column) if the row has one."""
    match = DATE_RE.match(text)
    if match and parse_date(match.group(1)):
        return text[match.end():]
    return text


def _clean_description(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" -|")
    # A trailing value date sometimes sits between description and amounts.
    text = re.sub(r"\s\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}$", "", text)
    return text.strip()


def _guess_type(description: str) -> str:
    return "credit" if CREDIT_WORDS.search(description) else "debit"


def _type_from_balance(prev: float | None, amount: float, balance: float | None) -> str | None:
    if prev is None or balance is None:
        return None
    if abs(round(prev - amount, 2) - balance) < 0.011:
        return "debit"
    if abs(round(prev + amount, 2) - balance) < 0.011:
        return "credit"
    return None


def _make_id(txn: Transaction, occurrence: int) -> str:
    key = "|".join(
        [txn.date.isoformat(), txn.description.upper(), f"{txn.amount:.2f}", txn.type,
         "" if txn.balance is None else f"{txn.balance:.2f}", str(occurrence)]
    )
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def parse_lines(lines: list[str]) -> ParseResult:
    result = ParseResult()
    prev_balance: float | None = None
    current: Transaction | None = None
    extra_lines = 0
    dated_rows_without_amount = 0
    guessed = 0

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        date_match = DATE_RE.match(line)
        txn_date = parse_date(date_match.group(1)) if date_match else None

        if txn_date is None:
            # Opening balance printed on its own line (no date in front).
            if OPENING_BALANCE_RE.search(line) and result.opening_balance is None:
                amounts = AMOUNT_RE.findall(line)
                if amounts:
                    result.opening_balance = to_amount(amounts[-1][0])
                    prev_balance = result.opening_balance
                continue
            # Long descriptions often wrap onto the next line.
            if (
                current is not None
                and extra_lines < MAX_CONTINUATION_LINES
                and not AMOUNT_RE.search(line)
                and not NOISE_RE.search(line)
                and len(line) <= 80
            ):
                current.description = f"{current.description} {line}".strip()
                extra_lines += 1
            else:
                current = None
            continue

        rest = _strip_leading_date(line[date_match.end():])
        amounts = list(AMOUNT_RE.finditer(rest))
        if not amounts:
            dated_rows_without_amount += 1
            current = None
            continue

        description = _clean_description(rest[: amounts[0].start()])
        values = [to_amount(m.group(1)) for m in amounts]
        markers = [(m.group(2) or "").lower() for m in amounts]

        if SKIP_ROW_RE.match(description):
            if OPENING_BALANCE_RE.match(description) and result.opening_balance is None:
                result.opening_balance = values[-1]
            prev_balance = values[-1]
            current = None
            continue

        txn_type: str | None = None
        balance: float | None = None
        if len(values) == 1:
            amount = values[0]
            if markers[0] in ("dr", "cr"):
                txn_type = "debit" if markers[0] == "dr" else "credit"
        elif len(values) == 2:
            amount, balance = values
            if markers[0] in ("dr", "cr"):
                txn_type = "debit" if markers[0] == "dr" else "credit"
        else:
            withdrawal, deposit, balance = values[-3:]
            if withdrawal > 0 and deposit == 0:
                amount, txn_type = withdrawal, "debit"
            elif deposit > 0 and withdrawal == 0:
                amount, txn_type = deposit, "credit"
            else:
                amount = values[-2]

        if amount == 0:
            current = None
            continue

        if txn_type is None:
            txn_type = _type_from_balance(prev_balance, amount, balance)
        if txn_type is None:
            txn_type = _guess_type(description)
            guessed += 1

        current = Transaction(
            date=txn_date,
            description=description or "(no description)",
            amount=amount,
            type=txn_type,
            balance=balance,
        )
        result.transactions.append(current)
        extra_lines = 0
        if balance is not None:
            prev_balance = balance

    # Stable ids so loading the same statement twice does not add duplicates.
    seen: Counter[tuple] = Counter()
    for txn in result.transactions:
        key = (txn.date, txn.description.upper(), txn.amount, txn.type, txn.balance)
        seen[key] += 1
        txn.id = _make_id(txn, seen[key])

    if dated_rows_without_amount:
        result.warnings.append(
            f"{dated_rows_without_amount} line(s) started with a date but had no amount and were skipped."
        )
    if guessed:
        result.warnings.append(
            f"{guessed} transaction(s) had no balance or Dr/Cr marker; debit/credit was guessed from the description."
        )
    if not result.transactions:
        result.warnings.append(
            "No transactions found. The PDF may be a scanned image (needs OCR) or use a layout this parser does not know yet."
        )
    return result


def extract_lines(pdf_path: str | Path, password: str | None = None) -> list[str]:
    import pdfplumber
    from pdfminer.pdfdocument import PDFPasswordIncorrect

    path = Path(pdf_path).expanduser()
    if not path.exists():
        raise StatementError(f"File not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise StatementError(f"Not a PDF file: {path.name}")

    try:
        with pdfplumber.open(path, password=password or None) as pdf:
            lines: list[str] = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                lines.extend(text.splitlines())
            return lines
    except PDFPasswordIncorrect as exc:
        raise StatementError(
            "This PDF is password protected. Pass the password (many Indian banks use part of your "
            "name or date of birth, as written in the email that came with the statement)."
        ) from exc
    except Exception as exc:  # pdfplumber raises many different error types
        if "password" in str(exc).lower() or type(exc).__name__ == "PdfminerException":
            raise StatementError(
                "Could not open the PDF. If it is password protected, pass the correct password."
            ) from exc
        raise StatementError(f"Could not read the PDF: {exc}") from exc


def parse_pdf(pdf_path: str | Path, password: str | None = None) -> ParseResult:
    return parse_lines(extract_lines(pdf_path, password))
