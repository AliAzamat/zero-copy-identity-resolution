"""Normalization: make comparable things comparable, and nothing more.

The line this module walks carefully: normalization must remove meaningless
differences (casing, whitespace, plus-addressing) without removing meaningful
ones. Over-normalizing merges distinct people, which is a much worse error than
failing to merge the same person, because a failed merge is visible and a wrong
merge shows one customer another customer's data.
"""
from __future__ import annotations

import re
import unicodedata

# Nicknames map to a canonical form. Deliberately conservative: only pairs that
# are near-universally the same name. "Alex" is NOT mapped to "Alexander",
# because Alex is also a full name in its own right and mapping it would merge
# two different people who happen to share a company.
NICKNAMES = {
    "bob": "robert", "rob": "robert", "bobby": "robert",
    "bill": "william", "will": "william", "billy": "william",
    "dick": "richard", "rick": "richard",
    "jim": "james", "jimmy": "james",
    "mike": "michael", "tom": "thomas", "tony": "anthony",
    "kate": "katherine", "kathy": "katherine",
    "liz": "elizabeth", "beth": "elizabeth",
    "dave": "david", "steve": "stephen", "joe": "joseph",
}


def norm_email(raw: str | None) -> str | None:
    """Lowercase, trim, and strip plus-addressing.

    `bob.chen+news@x.com` and `Bob.Chen@X.com` are the same mailbox. The plus
    suffix is a tag the user chose, not part of the address.

    Note what we do NOT do: gmail treats dots as insignificant, but most other
    providers do not. Stripping dots universally would merge
    `j.smith@corp.com` and `jsmith@corp.com`, which at most companies are two
    different people.
    """
    if not raw:
        return None
    e = raw.strip().lower()
    if "@" not in e:
        return None
    local, _, domain = e.partition("@")
    local = local.split("+", 1)[0]
    if not local or not domain:
        return None
    return f"{local}@{domain}"


def norm_name(raw: str | None) -> str | None:
    """Strip accents and punctuation, collapse whitespace, map nicknames."""
    if not raw:
        return None
    s = unicodedata.normalize("NFKD", raw)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-zA-Z\s'-]", " ", s).lower()
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return None

    parts = s.split(" ")
    parts = [NICKNAMES.get(p, p) for p in parts]
    return " ".join(parts)


def norm_phone(raw: str | None) -> str | None:
    """Digits only, keeping the last 10 as the comparable core.

    Country codes and formatting vary per system for the same number. The last
    ten digits are stable across all three sources here.
    """
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 10:
        return None
    return digits[-10:]


def name_tokens(normalized: str | None) -> frozenset[str]:
    """Token set for comparison, so word order does not matter."""
    if not normalized:
        return frozenset()
    return frozenset(t for t in normalized.split(" ") if len(t) > 1)
