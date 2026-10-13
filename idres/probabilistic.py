"""Fuzzy matching for the records strong keys did not resolve.

Two problems to solve: comparing every pair is quadratic and infeasible, and a
similarity score is meaningless without a threshold chosen deliberately.
Blocking fixes the first. Measuring against labelled pairs fixes the second.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass

from idres.deterministic import MatchPair
from idres.normalize import norm_email, norm_name, name_tokens


@dataclass
class FieldScore:
    field: str
    score: float
    weight: float
    detail: str


# Weights reflect how much each field's agreement should move the decision.
# Email domain agreement is weighted LOW on purpose: everyone at one company
# shares it, so it distinguishes almost nothing between colleagues while
# looking like strong evidence.
WEIGHTS = {
    "name": 0.55,
    "email_local": 0.30,
    "email_domain": 0.05,
    "company": 0.10,
}

# Above this, merge. Below, leave separate. Chosen by measuring against the
# labelled pairs in tests/fixtures/labelled_pairs.json, NOT by intuition.
MATCH_THRESHOLD = 0.82


def _ratio(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _name_score(a: str | None, b: str | None) -> tuple[float, str]:
    """Token-aware name comparison.

    Compares token SETS first so "chen robert" and "robert chen" score as
    identical. Falls back to a character ratio for typos within tokens.
    """
    na, nb = norm_name(a), norm_name(b)
    if not na or not nb:
        return 0.0, "one name missing"

    ta, tb = name_tokens(na), name_tokens(nb)
    if ta and ta == tb:
        return 1.0, "identical token set"
    if ta and tb and (ta & tb):
        overlap = len(ta & tb) / max(len(ta), len(tb))
        char = _ratio(na, nb)
        return max(overlap, char), f"token overlap {overlap:.2f}"
    return _ratio(na, nb), "character similarity"


def score_pair(left: dict, right: dict) -> tuple[float, list[FieldScore]]:
    """Weighted score for one candidate pair, with the per-field breakdown."""
    scores: list[FieldScore] = []

    n, detail = _name_score(left.get("name"), right.get("name"))
    scores.append(FieldScore("name", n, WEIGHTS["name"], detail))

    le, re_ = norm_email(left.get("email")), norm_email(right.get("email"))
    if le and re_:
        ll, _, ld = le.partition("@")
        rl, _, rd = re_.partition("@")
        scores.append(FieldScore("email_local", _ratio(ll, rl), WEIGHTS["email_local"],
                                 f"{ll} vs {rl}"))
        scores.append(FieldScore("email_domain", 1.0 if ld == rd else 0.0,
                                 WEIGHTS["email_domain"], f"{ld} vs {rd}"))
    else:
        scores.append(FieldScore("email_local", 0.0, WEIGHTS["email_local"], "missing"))
        scores.append(FieldScore("email_domain", 0.0, WEIGHTS["email_domain"], "missing"))

    lc, rc = (left.get("company") or "").lower(), (right.get("company") or "").lower()
    scores.append(FieldScore("company", _ratio(lc, rc), WEIGHTS["company"],
                             f"{lc} vs {rc}"))

    total = sum(s.score * s.weight for s in scores)
    return total, scores


def block_key(rec: dict) -> str:
    """Records only get compared when their block key matches.

    The key here is the email domain plus the first letter of the normalized
    name. It is deliberately loose: a blocking key that is too tight silently
    prevents true matches from ever being compared, and that failure is
    invisible because the pair simply never appears in the output.
    """
    email = norm_email(rec.get("email")) or ""
    domain = email.partition("@")[2] if email else "nodomain"
    name = norm_name(rec.get("name")) or ""
    initial = name[0] if name else "_"
    return f"{domain}|{initial}"


def match(records: list[dict], already_matched: set[tuple[str, str]]) -> list[MatchPair]:
    """Score candidate pairs within blocks and keep those above threshold."""
    blocks: dict[str, list[dict]] = {}
    for r in records:
        blocks.setdefault(block_key(r), []).append(r)

    pairs: list[MatchPair] = []
    for _key, group in blocks.items():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if a["_source"] == b["_source"]:
                    continue                    # never match within one source
                ident = (a["_id"], b["_id"])
                if ident in already_matched or (ident[1], ident[0]) in already_matched:
                    continue

                total, breakdown = score_pair(a, b)
                if total < MATCH_THRESHOLD:
                    continue

                top = sorted(breakdown, key=lambda s: s.score * s.weight, reverse=True)[:2]
                pairs.append(MatchPair(
                    left_source=a["_source"], left_id=a["_id"],
                    right_source=b["_source"], right_id=b["_id"],
                    method="probabilistic",
                    confidence=round(total, 4),
                    evidence="; ".join(f"{s.field}={s.score:.2f} ({s.detail})" for s in top),
                ))
    return pairs
