import pytest

from bank_reader.categoriser import categorise, extract_merchant


@pytest.mark.parametrize(
    "description, expected",
    [
        ("UPI/DR/412300000002/SWIGGY/YESB/swiggy@ybl", "SWIGGY"),
        ("POS 4321XXXXXXXX1234 NETFLIX.COM MUMBAI", "NETFLIX"),
        ("ACH D-GROWW MUTUAL FUND SIP-MF00012345", "GROWW"),
        ("ATW-512345XXXXXX6789-S1AWBL01-BANGALORE", "ATM WITHDRAWAL"),
        ("UPI-ZOMATO-zomato@hdfcbank-HDFC0000001-123456", "ZOMATO"),
        ("UPI/DR/1234/TATA 1MG/YESB", "TATA"),
    ],
)
def test_extract_merchant(description, expected):
    assert extract_merchant(description) == expected


@pytest.mark.parametrize(
    "description, txn_type, expected",
    [
        ("UPI/DR/1/SWIGGY/YESB", "debit", "Food & Dining"),
        ("UPI/DR/1/SWIGGYINSTAMART/YESB", "debit", "Groceries"),
        ("POS NETFLIX.COM", "debit", "Subscriptions & Entertainment"),
        ("UPI/DR/1/AMAZON/YESB", "debit", "Shopping"),
        ("UPI/DR/1/OLACABS/YESB", "debit", "Transport & Fuel"),
        ("UPI/DR/1/COCA COLA/YESB", "debit", "Transfers"),
        ("UPI/DR/1/LICIOUS/YESB", "debit", "Transfers"),
        ("LIC PREMIUM", "debit", "Insurance"),
        ("ATW-5123XXXX-S1AWBL01", "debit", "Cash Withdrawal"),
        ("UPI/DR/1/BESCOM/BillDesk", "debit", "Bills & Utilities"),
        ("ACH D-GROWW MUTUAL FUND SIP", "debit", "Investments"),
        ("NEFT CR-ACME-ACME LTD-SALARY OCT", "credit", "Salary"),
        ("UPI/CR/1/AMAZON REFUND", "credit", "Refund"),
        ("UPI/CR/1/FRIEND", "credit", "Money In"),
        ("SOMETHING ODD", "debit", "Other"),
    ],
)
def test_categorise_defaults(description, txn_type, expected):
    assert categorise(description, txn_type) == expected


def test_user_rule_wins():
    rules = {"HOUSE OWNER": "Rent"}
    assert categorise("UPI/DR/1/HOUSE OWNER/SBIN", "debit", rules) == "Rent"
    assert categorise("UPI/DR/1/HOUSE OWNER/SBIN", "debit") == "Transfers"
