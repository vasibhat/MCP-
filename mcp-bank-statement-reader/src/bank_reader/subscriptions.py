"""Find repeat charges (subscriptions, EMIs, rent, SIPs ...) in a list of debits.

A group of payments to the same merchant counts as a repeat charge when:
  * the amounts are close to each other (within 15% of the usual amount), and
  * the gaps between payments fit a weekly, monthly, quarterly or yearly pattern.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import median

FREQUENCIES = [
    # name, min gap days, max gap days, payments per year
    ("weekly", 5, 9, 52),
    ("monthly", 25, 35, 12),
    ("quarterly", 80, 100, 4),
    ("yearly", 350, 380, 1),
]
AMOUNT_TOLERANCE = 0.15


def _frequency(gap_days: float) -> tuple[str, int] | None:
    for name, low, high, per_year in FREQUENCIES:
        if low <= gap_days <= high:
            return name, per_year
    return None


def find_recurring(transactions: list[dict], min_occurrences: int = 2) -> list[dict]:
    """transactions: dicts with date (ISO str or date), amount, type, merchant, category."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for txn in transactions:
        if txn["type"] != "debit":
            continue
        groups[txn["merchant"]].append(txn)

    found: list[dict] = []
    for merchant, items in groups.items():
        if len(items) < max(2, min_occurrences):
            continue

        usual = median(t["amount"] for t in items)
        similar = [t for t in items if abs(t["amount"] - usual) <= usual * AMOUNT_TOLERANCE]
        if len(similar) < max(2, min_occurrences):
            continue

        dates = sorted(
            t["date"] if isinstance(t["date"], date) else date.fromisoformat(t["date"])
            for t in similar
        )
        # Two charges on the same day are one billing cycle, not a pattern.
        unique_dates = sorted(set(dates))
        if len(unique_dates) < max(2, min_occurrences):
            continue
        gaps = [(b - a).days for a, b in zip(unique_dates, unique_dates[1:])]
        typical_gap = median(gaps)
        freq = _frequency(typical_gap)
        if freq is None:
            continue
        name, per_year = freq
        if name == "weekly" and len(unique_dates) < 3:
            continue

        fitting = sum(1 for g in gaps if _frequency(g) and _frequency(g)[0] == name)
        if fitting / len(gaps) < 0.6:
            continue

        avg_amount = round(sum(t["amount"] for t in similar) / len(similar), 2)
        last = unique_dates[-1]
        found.append({
            "merchant": merchant,
            "category": similar[-1].get("category", ""),
            "frequency": name,
            "usual_amount": avg_amount,
            "times_charged": len(similar),
            "first_seen": unique_dates[0].isoformat(),
            "last_charged": last.isoformat(),
            "next_expected": (last + timedelta(days=round(typical_gap))).isoformat(),
            "yearly_cost": round(avg_amount * per_year, 2),
            "confidence": "high" if len(unique_dates) >= 3 else "low",
            "sample_description": similar[-1].get("description", ""),
        })

    found.sort(key=lambda s: s["yearly_cost"], reverse=True)
    return found
