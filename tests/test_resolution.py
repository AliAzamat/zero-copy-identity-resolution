"""Resolution tests. Each encodes a decision about who is the same person.

Every test here states the human situation it represents, because a future
reader needs to know whether a failure means broken code or a changed policy.
"""
from __future__ import annotations

import pytest

from idres.deterministic import MatchPair, match as det_match
from idres.entities import resolve, BRIDGE_THRESHOLD
from idres.normalize import norm_email, norm_name
from idres.probabilistic import score_pair, MATCH_THRESHOLD
from idres.survivorship import survive, build_profile


def rec(_id, source, **kw):
    return {"_id": _id, "_source": source, **kw}


# ---------- normalization ----------

@pytest.mark.parametrize("raw,expected", [
    ("Bob.Chen+news@Northwind.Example", "bob.chen@northwind.example"),
    ("  ROBERT.CHEN@northwind.example ", "robert.chen@northwind.example"),
    ("not-an-email", None),
])
def test_email_normalization(raw, expected):
    assert norm_email(raw) == expected


def test_dots_are_not_stripped_from_email():
    """j.smith and jsmith are usually two different people.

    Gmail ignores dots; most corporate mail does not. Stripping them would
    merge colleagues, so this test guards against a tempting "improvement".
    """
    assert norm_email("j.smith@corp.example") != norm_email("jsmith@corp.example")


def test_nickname_maps_but_alex_does_not():
    """Bob -> Robert is safe. Alex -> Alexander is not, because Alex stands alone."""
    assert norm_name("Bob Chen") == norm_name("Robert Chen")
    assert norm_name("Alex Park") != norm_name("Alexander Park")


# ---------- deterministic ----------

def test_shared_mailbox_does_not_merge_everyone():
    """Six records sharing support@ must NOT become one person."""
    left = [rec(f"c{i}", "crm", email="support@acme.example") for i in range(6)]
    right = [rec(f"w{i}", "web", email="support@acme.example") for i in range(6)]
    pairs = det_match(left, "crm", right, "web")
    assert pairs == [], "a mailbox shared by many records must not produce matches"


# ---------- probabilistic ----------

def test_same_person_across_sources_scores_above_threshold():
    """The Robert/Bob Chen case from the README, spread across two systems."""
    a = rec("c1", "crm", name="Robert Chen", email="robert.chen@northwind.example",
            company="Northwind")
    b = rec("w1", "web", name="Bob Chen", email="bob.chen+news@northwind.example",
            company="Northwind")
    total, _ = score_pair(a, b)
    assert total >= MATCH_THRESHOLD


def test_colleagues_do_not_match_on_domain_alone():
    """Two different people at one company share a domain and nothing else.

    This is the test that fails if email_domain is ever given a high weight.
    """
    a = rec("c1", "crm", name="Priya Nair", email="priya.nair@northwind.example",
            company="Northwind")
    b = rec("w1", "web", name="Daniel Osei", email="daniel.osei@northwind.example",
            company="Northwind")
    total, _ = score_pair(a, b)
    assert total < MATCH_THRESHOLD


# ---------- entities ----------

def test_weak_pair_does_not_bridge_two_clusters():
    """A-B and C-D are certain; B-C is weak. Three entities, not one."""
    strong = [
        MatchPair("crm", "a", "web", "b", "deterministic:email", 1.0, "exact"),
        MatchPair("crm", "c", "web", "d", "deterministic:email", 1.0, "exact"),
    ]
    weak = [MatchPair("web", "b", "crm", "c", "probabilistic",
                      BRIDGE_THRESHOLD - 0.05, "fuzzy name")]

    entities = resolve(strong + weak)
    sizes = sorted(len(e.members) for e in entities)
    assert sizes == [2, 2], f"weak pair bridged two clusters: {sizes}"


# ---------- survivorship ----------

def test_email_survives_by_recency_not_precedence():
    """Email is a recency field: the newest wins even from a lower-ranked source."""
    candidates = [
        rec("c1", "crm", email="old@northwind.example", _updated_at="2026-01-01"),
        rec("s1", "support", email="new@northwind.example", _updated_at="2026-09-01"),
    ]
    sv = survive("email", candidates)
    assert sv.value == "new@northwind.example"
    assert "most recent" in sv.rule


def test_legal_name_survives_by_source_precedence():
    """Legal name comes from the CRM even when support has a newer record."""
    candidates = [
        rec("c1", "crm", legal_name="Robert Chen", _updated_at="2026-01-01"),
        rec("s1", "support", legal_name="rob chen", _updated_at="2026-09-01"),
    ]
    sv = survive("legal_name", candidates)
    assert sv.value == "Robert Chen"
    assert "source precedence" in sv.rule


def test_profile_records_competing_values():
    """The explain block must show what lost, not only what won."""
    records = [
        rec("c1", "crm", legal_name="Robert Chen", email="robert.chen@northwind.example",
            _updated_at="2026-01-01"),
        rec("w1", "web", legal_name="Bob Chen", email="bob.chen@northwind.example",
            _updated_at="2026-09-01"),
    ]
    p = build_profile("ent_test", records)
    assert p["legal_name"] == "Robert Chen"
    assert "Bob Chen" in p["_explain"]["legal_name"]["competing"]
    assert p["_explain"]["email"]["source"] == "web"
