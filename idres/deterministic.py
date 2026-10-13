"""Exact matching on normalized strong keys.

Run this first, always. Deterministic matches are effectively certain, they are
cheap, and every pair resolved here is a pair the probabilistic stage never has
to consider. Running the fuzzy matcher first would mean scoring millions of
pairs that a single email comparison settles.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from idres.normalize import norm_email, norm_phone


@dataclass(frozen=True)
class MatchPair:
    """One asserted match between two source records, with its evidence.

    `evidence` is not decoration. When someone challenges a merge months later,
    "matched on normalized email" is an answer; a similarity score alone is not.
    """

    left_source: str
    left_id: str
    right_source: str
    right_id: str
    method: str
    confidence: float
    evidence: str


# Strong keys, in descending order of trust. A match on ANY of these is treated
# as certain. Order matters only for which evidence string gets recorded.
STRONG_KEYS = ["email", "phone"]


def _index_by_key(records: Iterable[dict], source: str, key: str) -> dict[str, list[tuple[str, dict]]]:
    """Group a source's records by one normalized key."""
    out: dict[str, list[tuple[str, dict]]] = {}
    norm = norm_email if key == "email" else norm_phone
    for rec in records:
        value = norm(rec.get(key))
        if not value:
            continue
        out.setdefault(value, []).append((rec["_id"], rec))
    return out


def match(left: list[dict], left_source: str,
          right: list[dict], right_source: str) -> list[MatchPair]:
    """Produce deterministic pairs between two sources."""
    pairs: list[MatchPair] = []
    seen: set[tuple[str, str]] = set()

    for key in STRONG_KEYS:
        lidx = _index_by_key(left, left_source, key)
        ridx = _index_by_key(right, right_source, key)

        for value, lrecs in lidx.items():
            rrecs = ridx.get(value)
            if not rrecs:
                continue

            # A key shared by many records on one side is not identifying. A
            # shared support inbox, or a company switchboard number, would
            # otherwise merge every customer who ever used it into one entity.
            if len(lrecs) > 5 or len(rrecs) > 5:
                continue

            for lid, _ in lrecs:
                for rid, _ in rrecs:
                    if (lid, rid) in seen:
                        continue
                    seen.add((lid, rid))
                    pairs.append(MatchPair(
                        left_source=left_source, left_id=lid,
                        right_source=right_source, right_id=rid,
                        method=f"deterministic:{key}",
                        confidence=1.0,
                        evidence=f"normalized {key} == {value}",
                    ))

    return pairs
