from datetime import date, timedelta

from bank_reader.subscriptions import find_recurring


def _txn(d, amount, merchant, txn_type="debit"):
    return {"date": d.isoformat(), "amount": amount, "type": txn_type,
            "merchant": merchant, "category": "x", "description": merchant}


def test_monthly_subscription_found():
    txns = [_txn(date(2026, m, 5), 649.0, "NETFLIX") for m in (7, 8, 9, 10)]
    [sub] = find_recurring(txns)
    assert sub["frequency"] == "monthly"
    assert sub["usual_amount"] == 649.0
    assert sub["yearly_cost"] == 649.0 * 12
    assert sub["next_expected"] == "2026-11-05"
    assert sub["confidence"] == "high"


def test_two_charges_give_low_confidence():
    txns = [_txn(date(2026, 9, 12), 119.0, "SPOTIFY"), _txn(date(2026, 10, 12), 119.0, "SPOTIFY")]
    [sub] = find_recurring(txns)
    assert sub["confidence"] == "low"
    assert find_recurring(txns, min_occurrences=3) == []


def test_random_shopping_is_not_a_subscription():
    txns = [
        _txn(date(2026, 8, 2), 4497.0, "AMAZON"),
        _txn(date(2026, 8, 20), 299.0, "AMAZON"),
        _txn(date(2026, 10, 1), 1499.0, "AMAZON"),
    ]
    assert find_recurring(txns) == []


def test_irregular_gaps_are_ignored():
    start = date(2026, 1, 1)
    txns = [_txn(start + timedelta(days=d), 100.0, "CHAI") for d in (0, 3, 40, 41, 90)]
    assert find_recurring(txns) == []


def test_weekly_needs_three_charges():
    start = date(2026, 10, 1)
    two = [_txn(start + timedelta(days=7 * i), 50.0, "PAPER") for i in range(2)]
    four = [_txn(start + timedelta(days=7 * i), 50.0, "PAPER") for i in range(4)]
    assert find_recurring(two) == []
    assert find_recurring(four)[0]["frequency"] == "weekly"


def test_credits_are_ignored():
    txns = [_txn(date(2026, m, 1), 85000.0, "ACME", "credit") for m in (8, 9, 10)]
    assert find_recurring(txns) == []
