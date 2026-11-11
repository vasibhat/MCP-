from datetime import date

from bank_reader.parser import parse_date, parse_lines, parse_pdf
from bank_reader.sample import OPENING_BALANCE, SAMPLE_ROWS


def test_parse_date_formats():
    assert parse_date("05/10/2026") == date(2026, 10, 5)
    assert parse_date("05-10-26") == date(2026, 10, 5)
    assert parse_date("05 Oct 2026") == date(2026, 10, 5)
    assert parse_date("05-Oct-2026") == date(2026, 10, 5)
    assert parse_date("5 October 2026") == date(2026, 10, 5)
    assert parse_date("31/02/2026") is None


def test_direction_from_running_balance():
    lines = [
        "Opening Balance 10,000.00",
        "01/10/2026 UPI/DR/1234/SWIGGY/YESB 450.00 9,550.00",
        "02/10/2026 NEFT CR-ACME-ACME LTD-SALARY 50,000.00 59,550.00",
    ]
    result = parse_lines(lines)
    assert result.opening_balance == 10_000.00
    assert [(t.amount, t.type) for t in result.transactions] == [(450.00, "debit"), (50_000.00, "credit")]
    assert result.warnings == []


def test_withdrawal_and_deposit_columns_with_zero():
    lines = [
        "01/10/2026 01/10/2026 POS NETFLIX.COM 649.00 0.00 1,00,000.00",
        "02/10/2026 02/10/2026 REFUND AMAZON 0.00 1,499.00 1,01,499.00",
    ]
    txns = parse_lines(lines).transactions
    assert [(t.amount, t.type, t.balance) for t in txns] == [
        (649.00, "debit", 100_000.00),
        (1_499.00, "credit", 101_499.00),
    ]
    assert txns[0].description == "POS NETFLIX.COM"


def test_dr_cr_markers():
    lines = [
        "01-Oct-2026 UPI-ZOMATO-zomato@hdfc 320.00 Dr 5,000.00 Cr",
        "03-Oct-2026 INTEREST CREDIT 12.00 Cr 5,012.00 Cr",
    ]
    txns = parse_lines(lines).transactions
    assert [(t.amount, t.type) for t in txns] == [(320.00, "debit"), (12.00, "credit")]


def test_wrapped_description_joins_next_line():
    lines = [
        "Opening Balance 2,000.00",
        "01/10/2026 UPI/DR/1234/BESCOM 1,180.00 820.00",
        "Electricity bill payment",
        "Page 1 of 2",
        "02/10/2026 UPI/DR/1235/AIRTEL 599.00 221.00",
    ]
    txns = parse_lines(lines).transactions
    assert txns[0].description == "UPI/DR/1234/BESCOM Electricity bill payment"
    assert txns[1].description == "UPI/DR/1235/AIRTEL"


def test_guess_used_when_no_balance_and_warns():
    result = parse_lines(["01/10/2026 SALARY OCT 50,000.00", "02/10/2026 SWIGGY ORDER 300.00"])
    assert [t.type for t in result.transactions] == ["credit", "debit"]
    assert any("guessed" in w for w in result.warnings)


def test_same_looking_rows_get_different_ids():
    lines = ["01/10/2026 CHAI 20.00", "01/10/2026 CHAI 20.00"]
    ids = [t.id for t in parse_lines(lines).transactions]
    assert len(set(ids)) == 2
    assert ids == [t.id for t in parse_lines(lines).transactions]  # stable across runs


def test_header_and_footer_lines_are_ignored():
    lines = [
        "Statement of Account",
        "Date Narration Withdrawal Deposit Balance",
        "Closing Balance: 100.00",
    ]
    result = parse_lines(lines)
    assert result.transactions == []
    assert any("No transactions found" in w for w in result.warnings)


def test_full_sample_pdf(sample_pdf):
    result = parse_pdf(sample_pdf)
    assert result.opening_balance == OPENING_BALANCE
    assert len(result.transactions) == len(SAMPLE_ROWS)
    for txn, (when, desc, withdrawal, deposit) in zip(result.transactions, SAMPLE_ROWS):
        assert txn.date == when
        assert txn.amount == round(withdrawal or deposit, 2)
        assert txn.type == ("debit" if withdrawal else "credit")
        assert txn.description == desc.replace("\n", " ")
    assert result.warnings == []
