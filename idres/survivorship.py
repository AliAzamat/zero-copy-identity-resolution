"""Pick the surviving value for each field, and record the reason.

This is the module people ask about. Not "how does the matching work" but "why
does this customer's profile say Bob when the CRM says Robert". Every surviving
value therefore carries the rule that produced it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable


@dataclass
class SurvivingValue:
    value: Any
    source: str
    rule: str
    competing: list[str]


# Which source to trust per field, most trusted first. These are business
# decisions, not technical ones: the CRM is authoritative for legal name
# because a human verified it at contract time, while the web signup is
# authoritative for the email the customer actually reads.
SOURCE_PRECEDENCE = {
    "legal_name": ["crm", "support", "web"],
    "email":      ["web", "crm", "support"],
    "phone":      ["crm", "support"],
    "company":    ["crm", "support"],
}

RECENCY_FIELDS = {"email", "phone"}


def _parse_ts(v: Any) -> datetime:
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v))
    except (TypeError, ValueError):
        return datetime.min


def survive(field: str, candidates: list[dict]) -> SurvivingValue | None:
    """Choose one value for `field` from candidate records.

    Order of rules:
      1. Drop empties. A missing value never wins by default.
      2. If every non-empty value agrees, that is the answer with no contest.
      3. For recency fields, prefer the most recently updated record.
      4. Otherwise apply source precedence.
      5. Tie-break deterministically so the same inputs give the same output.
    """
    present = [c for c in candidates if c.get(field) not in (None, "", [])]
    if not present:
        return None

    values = {str(c[field]).strip() for c in present}
    competing = sorted(values)

    if len(values) == 1:
        winner = present[0]
        return SurvivingValue(winner[field], winner["_source"], "unanimous", competing)

    if field in RECENCY_FIELDS:
        winner = max(present, key=lambda c: _parse_ts(c.get("_updated_at")))
        return SurvivingValue(
            winner[field], winner["_source"],
            f"most recent update ({winner.get('_updated_at')})", competing,
        )

    order = SOURCE_PRECEDENCE.get(field, [])
    for src in order:
        matches = [c for c in present if c["_source"] == src]
        if matches:
            # Within one source, break ties by recency then by value, so the
            # result never depends on row ordering from the database.
            winner = sorted(
                matches,
                key=lambda c: (_parse_ts(c.get("_updated_at")), str(c[field])),
                reverse=True,
            )[0]
            return SurvivingValue(
                winner[field], src, f"source precedence ({' > '.join(order)})", competing,
            )

    winner = sorted(present, key=lambda c: str(c[field]))[0]
    return SurvivingValue(winner[field], winner["_source"], "deterministic tie-break", competing)


def build_profile(entity_id: str, records: list[dict],
                  fields: list[str] | None = None) -> dict[str, Any]:
    """Assemble one profile with a per-field explanation."""
    fields = fields or list(SOURCE_PRECEDENCE)
    profile: dict[str, Any] = {"entity_id": entity_id, "_explain": {}}

    for f in fields:
        sv = survive(f, records)
        if sv is None:
            profile[f] = None
            profile["_explain"][f] = {"rule": "no value in any source"}
            continue
        profile[f] = sv.value
        profile["_explain"][f] = {
            "source": sv.source,
            "rule": sv.rule,
            "competing": sv.competing,
        }

    profile["_sources"] = sorted({r["_source"] for r in records})
    profile["_record_count"] = len(records)
    return profile
