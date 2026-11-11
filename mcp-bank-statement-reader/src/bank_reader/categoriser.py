"""Sort transactions into spending categories and pull out a short merchant name.

Matching is keyword based. A keyword must match at the start of a word, so
"SWIGGY" matches "SWIGGYINSTAMART" but never the middle of another word.
Short keywords (4 letters or less, like "OLA", "LIC", "EMI") must match a whole
word, so "LIC" does not match "LICIOUS". Your own rules (saved with the
set_category_rule tool) are always checked before the built-in ones.
"""

from __future__ import annotations

import re

# Order matters: the first category with a matching keyword wins.
DEFAULT_RULES: dict[str, list[str]] = {
    "Groceries": ["SWIGGYINSTAMART", "SWIGGY INSTAMART", "BIGBASKET", "BLINKIT", "ZEPTO", "INSTAMART", "DMART", "JIOMART", "GROFERS",
                  "MORE RETAIL", "RELIANCE FRESH", "RELIANCE SMART", "NATURES BASKET", "SPENCER"],
    "Food & Dining": ["SWIGGY", "ZOMATO", "DOMINOS", "PIZZA", "MCDONALD", "KFC", "STARBUCKS",
                      "CAFE", "RESTAURANT", "BURGER", "HALDIRAM", "EATSURE", "CHAAYOS"],
    "Subscriptions & Entertainment": ["NETFLIX", "SPOTIFY", "HOTSTAR", "DISNEY", "PRIME VIDEO",
                                      "AMAZON PRIME", "YOUTUBE", "GOOGLE ONE", "APPLE", "ICLOUD",
                                      "SONYLIV", "ZEE5", "JIOCINEMA", "BOOKMYSHOW", "PVR", "INOX",
                                      "CHATGPT", "OPENAI", "ANTHROPIC", "CLAUDE", "LINKEDIN", "AUDIBLE"],
    "Shopping": ["AMAZON", "FLIPKART", "MYNTRA", "AJIO", "MEESHO", "NYKAA", "TATACLIQ", "DECATHLON",
                 "IKEA", "CROMA", "RELIANCE DIGITAL", "LIFESTYLE", "WESTSIDE", "PANTALOONS"],
    "Transport & Fuel": ["UBER", "OLA", "OLACABS", "RAPIDO", "IRCTC", "REDBUS", "METRO", "FASTAG", "PETROL",
                         "FUEL", "HPCL", "BPCL", "IOCL", "INDIAN OIL", "SHELL", "INDIGO",
                         "AIR INDIA", "VISTARA", "AKASA", "SPICEJET", "MAKEMYTRIP", "GOIBIBO",
                         "CLEARTRIP", "YATRA"],
    "Bills & Utilities": ["ELECTRICITY", "BESCOM", "MSEDCL", "TATA POWER", "ADANI ELEC", "TNEB",
                          "BSES", "AIRTEL", "JIO", "JIOFIBER", "JIOPOSTPAID", "VODAFONE", "BSNL", "ACT FIBERNET", "BROADBAND",
                          "HATHWAY", "TATA PLAY", "DTH", "GAS", "INDANE", "BHARATGAS", "HP GAS",
                          "WATER", "BBPS", "RECHARGE"],
    "Health": ["PHARMACY", "PHARMEASY", "APOLLO", "MEDPLUS", "NETMEDS", "1MG", "TATA 1MG", "PRACTO",
               "HOSPITAL", "CLINIC", "DIAGNOSTIC", "CULT", "CUREFIT", "GYM"],
    "Insurance": ["INSURANCE", "LIC", "POLICYBAZAAR", "HDFC LIFE", "ICICI PRU", "STAR HEALTH",
                  "ACKO", "DIGIT"],
    "Investments": ["ZERODHA", "GROWW", "KUVERA", "UPSTOX", "COIN", "MUTUAL FUND", "SIP", "PPF",
                    "NPS", "INDMONEY", "SMALLCASE", "ET MONEY", "BSE", "NSE", "CAMS", "KFIN"],
    "Loans & EMI": ["EMI", "LOAN", "BAJAJ FIN", "HOME LOAN", "CAR LOAN", "CRED CLUB", "CREDIT CARD",
                    "CC PAYMENT"],
    "Rent": ["RENT", "NOBROKER", "NESTAWAY"],
    "Education": ["SCHOOL", "COLLEGE", "UNIVERSITY", "FEES", "UDEMY", "COURSERA", "BYJU", "UNACADEMY"],
    "Cash Withdrawal": ["ATM", "ATW", "NWD", "CASH WDL", "CASH WITHDRAWAL"],
    "Bank Charges": ["CHARGES", "CHRG", "GST ON", "SMS ALERT", "ANNUAL FEE", "PENALTY", "MIN BAL"],
}

CREDIT_RULES: dict[str, list[str]] = {
    "Salary": ["SALARY", "SAL", "PAYROLL"],
    "Refund": ["REFUND", "REVERSAL", "CASHBACK", "RETURN"],
    "Interest": ["INTEREST", "INT.PD", "INT PD", "INT CREDIT"],
    "Dividend": ["DIVIDEND"],
}

TRANSFER_WORDS = ["UPI", "NEFT", "IMPS", "RTGS", "TRANSFER", "TRF"]

UNCATEGORISED = "Other"
MONEY_IN = "Money In"
TRANSFERS = "Transfers"

ALL_CATEGORIES = sorted(
    set(DEFAULT_RULES) | set(CREDIT_RULES) | {UNCATEGORISED, MONEY_IN, TRANSFERS}
)

STOP_TOKENS = {
    "UPI", "DR", "CR", "NEFT", "IMPS", "RTGS", "POS", "ECOM", "ATM", "ATW", "NWD", "ACH", "NACH",
    "MB", "IB", "INB", "BIL", "TO", "FROM", "BY", "TRANSFER", "TRF", "PAYMENT", "PAY", "REF",
    "TXN", "DEBIT", "CREDIT", "CARD", "ONLINE", "SI", "MANDATE", "AUTOPAY", "P2M", "P2A", "OK",
    "COLLECT", "REQUEST", "SENT", "RECEIVED", "IN", "OUT", "INR", "RS", "VPS", "PCD", "MMT",
    "COM", "WWW", "IN", "PVT", "LTD", "LIMITED", "PRIVATE", "THE", "AND", "FOR", "VIA",
    "YBL", "IBL", "AXL", "PAYTM", "OKAXIS", "OKHDFCBANK", "OKICICI", "OKSBI", "APL", "YESB",
    "HDFC", "ICIC", "ICICI", "SBIN", "UTIB", "KKBK", "AXIS", "SBI", "KOTAK", "BANK", "BILLDESK",
    "RAZORPAY", "PAYU", "CCAVENUE", "CASHFREE", "JUSPAY", "MUMBAI", "BANGALORE", "BENGALURU",
    "DELHI", "PUNE", "CHENNAI", "HYDERABAD", "GURGAON", "NOIDA", "KOLKATA", "IND", "INDIA",
}
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


def _normalise(text: str) -> str:
    return " " + re.sub(r"[^A-Z0-9]+", " ", text.upper()).strip() + " "


def _matches(text_norm: str, keyword: str) -> bool:
    kw = re.sub(r"[^A-Z0-9]+", " ", keyword.upper()).strip()
    if not kw:
        return False
    if len(kw) <= 4:
        return f" {kw} " in text_norm
    return f" {kw}" in text_norm


def extract_merchant(description: str) -> str:
    """Best guess at a short merchant name, e.g. 'UPI/DR/1234/SWIGGY/YESB' -> 'SWIGGY'."""
    upper = description.upper().strip()
    if re.match(r"^(ATW|ATM|NWD|CASH WDL|CASH WITHDRAWAL)\b", upper):
        return "ATM WITHDRAWAL"
    tokens = re.split(r"[/\-_*@:|,.\s]+", upper)
    for token in tokens:
        token = token.strip()
        if len(token) < 3 or token in STOP_TOKENS or IFSC_RE.match(token):
            continue
        # Skip reference numbers, masked card numbers and terminal codes like S1AWBL01.
        # Short names with a digit (1MG, ZEE5) are kept.
        if token.isdigit() or (any(ch.isdigit() for ch in token) and len(token) > 4):
            continue
        if "XXXX" in token:
            continue
        return token
    return re.sub(r"\s+", " ", description.upper()).strip()[:20] or "UNKNOWN"


def categorise(description: str, txn_type: str, user_rules: dict[str, str] | None = None) -> str:
    """Return the category for one transaction.

    user_rules maps keyword -> category and always wins over the built-in rules.
    """
    text = _normalise(description)

    for keyword, category in (user_rules or {}).items():
        if _matches(text, keyword):
            return category

    if txn_type == "credit":
        for category, keywords in CREDIT_RULES.items():
            if any(_matches(text, kw) for kw in keywords):
                return category
        return MONEY_IN

    for category, keywords in DEFAULT_RULES.items():
        if any(_matches(text, kw) for kw in keywords):
            return category

    if any(_matches(text, kw) for kw in TRANSFER_WORDS):
        return TRANSFERS
    return UNCATEGORISED
