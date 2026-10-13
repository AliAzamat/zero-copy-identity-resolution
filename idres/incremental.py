"""Update only the entities new records touch.

A nightly full rebuild is simple and wrong at scale: it reprocesses millions of
unchanged records to absorb a few thousand new ones. The risk of incremental
processing is drift, where the incremental result slowly diverges from what a
full rebuild would produce, so this module ships with an equivalence check.
"""
from __future__ import annotations

from dataclasses import dataclass

from idres.deterministic import MatchPair
from idres import deterministic, probabilistic
from idres.entities import Entity, resolve
from idres.probabilistic import block_key


@dataclass
class IncrementalResult:
    touched_entities: list[str]
    new_pairs: list[MatchPair]
    rebuilt_profiles: int


def affected_blocks(new_records: list[dict]) -> set[str]:
    """Which blocks the new records land in.

    Only records sharing a block with a new record can possibly match it, so
    only those blocks need re-scoring. This is the same blocking key the full
    matcher uses — reusing it is what keeps the incremental path faithful to
    the full one. Two different blocking rules would guarantee drift.
    """
    return {block_key(r) for r in new_records}


def update(existing_records: list[dict], new_records: list[dict],
           existing_pairs: list[MatchPair]) -> IncrementalResult:
    """Fold new records in, touching only the affected blocks."""
    blocks = affected_blocks(new_records)
    candidates = [r for r in existing_records if block_key(r) in blocks] + new_records

    det = deterministic.match(
        [r for r in candidates if r["_source"] != "web"], "crm",
        [r for r in candidates if r["_source"] == "web"], "web",
    )
    already = {(p.left_id, p.right_id) for p in existing_pairs} | {(p.left_id, p.right_id) for p in det}
    prob = probabilistic.match(candidates, already)

    new_pairs = det + prob
    entities = resolve(existing_pairs + new_pairs)

    new_ids = {f"{r['_source']}:{r['_id']}" for r in new_records}
    touched = [e.entity_id for e in entities if set(e.members) & new_ids]

    return IncrementalResult(
        touched_entities=touched,
        new_pairs=new_pairs,
        rebuilt_profiles=len(touched),
    )


def equivalent_to_full(incremental: list[Entity], full: list[Entity]) -> tuple[bool, str]:
    """Does the incremental result match a full rebuild?

    Compares MEMBERSHIP, not entity ids, because ids derive from membership and
    would trivially agree or trivially differ. The real question is whether the
    same records ended up grouped together.
    """
    inc_sets = {frozenset(e.members) for e in incremental}
    full_sets = {frozenset(e.members) for e in full}

    if inc_sets == full_sets:
        return True, "identical groupings"

    only_inc = inc_sets - full_sets
    only_full = full_sets - inc_sets
    return False, (
        f"{len(only_inc)} grouping(s) only in incremental, "
        f"{len(only_full)} only in full rebuild"
    )
