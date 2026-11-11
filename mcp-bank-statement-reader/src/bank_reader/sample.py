"""Make a fake bank statement PDF for trying the server without real data.

    uv run python -m bank_reader.sample sample_statement.pdf

All names, numbers and amounts here are made up.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

OPENING_BALANCE = 42_350.75


def _month_rows(y: int, m: int, mon: str) -> list[tuple[date, str, float, float]]:
    return [
        (date(y, m, 1), f"NEFT CR-ACME0001234-ACME TECH PVT LTD-SALARY {mon}", 0, 85_000.00),
        (date(y, m, 3), "UPI/DR/412300000001/HOUSE OWNER/SBIN/owner@oksbi", 25_000.00, 0),
        (date(y, m, 5), "POS 4321XXXXXXXX1234 NETFLIX.COM MUMBAI", 649.00, 0),
        (date(y, m, 7), "UPI/DR/412300000002/SWIGGY/YESB/swiggy@ybl", 312.50 + m, 0),
        (date(y, m, 10), "ACH D-GROWW MUTUAL FUND SIP-MF00012345", 5_000.00, 0),
        (date(y, m, 12), "UPI/DR/412300000003/SPOTIFY/YESB/spotify@ybl", 119.00, 0),
        (date(y, m, 14), "ATW-512345XXXXXX6789-S1AWBL01-BANGALORE", 2_000.00, 0),
        (date(y, m, 16), "UPI/DR/412300000004/BESCOM/BillDesk\nElectricity bill payment", 1_180.00 + 10 * m, 0),
        (date(y, m, 19), "UPI/DR/412300000005/AMAZON/YESB/amazon@apl", 1_499.00 * (m % 3 + 1), 0),
        (date(y, m, 21), "UPI/DR/412300000006/ZOMATO/HDFC/zomato@hdfcbank", 455.00 + m, 0),
        (date(y, m, 25), "UPI/DR/412300000007/AIRTEL/ICIC/airtel@icici", 599.00, 0),
    ]


# (date, description, withdrawal, deposit). A second description line is split with "\n".
SAMPLE_ROWS: list[tuple[date, str, float, float]] = (
    _month_rows(2026, 8, "AUG")
    + _month_rows(2026, 9, "SEP")
    + _month_rows(2026, 10, "OCT")
    + [(date(2026, 10, 28), "UPI/CR/412300000099/AMAZON REFUND/YESB", 0, 1_499.00)]
)


def _fmt(value: float) -> str:
    return f"{value:,.2f}" if value else ""


def make_sample_statement(out_path: str | Path, rows=None, opening_balance: float = OPENING_BALANCE) -> Path:
    from fpdf import FPDF  # dev dependency, only needed for the sample

    rows = rows if rows is not None else SAMPLE_ROWS
    pdf = FPDF(orientation="L", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "SAMPLE BANK LTD - Statement of Account", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9)
    pdf.cell(0, 6, "Account No: XXXXXXXX9999    Period: 01/08/2026 to 31/10/2026", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Opening Balance: {opening_balance:,.2f}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    widths = [24, 140, 34, 34, 40]
    pdf.set_font("Helvetica", "B", 9)
    for w, head in zip(widths, ["Date", "Narration", "Withdrawal", "Deposit", "Balance"]):
        pdf.cell(w, 7, head, border=1)
    pdf.ln()
    pdf.set_font("Helvetica", size=9)

    balance = opening_balance
    for when, description, withdrawal, deposit in rows:
        balance = round(balance - withdrawal + deposit, 2)
        first, _, second = description.partition("\n")
        cells = [when.strftime("%d/%m/%Y"), first, _fmt(withdrawal), _fmt(deposit), f"{balance:,.2f}"]
        for i, (w, text) in enumerate(zip(widths, cells)):
            pdf.cell(w, 6, text, align="R" if i >= 2 else "L")
        pdf.ln()
        if second:
            pdf.cell(widths[0], 6, "")
            pdf.cell(widths[1], 6, second)
            pdf.ln()

    pdf.ln(2)
    pdf.cell(0, 6, f"Closing Balance: {balance:,.2f}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "This is a computer generated statement.", new_x="LMARGIN", new_y="NEXT")

    out = Path(out_path).expanduser().resolve()
    pdf.output(str(out))
    return out


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "sample_statement.pdf"
    print(f"Sample statement written to {make_sample_statement(target)}")
