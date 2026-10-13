"""Group match pairs into entities.

Matching is pairwise; identity is not. If A matches B and B matches C, the
usual choice is to put all three in one entity — transitive closure. That is
correct when matches are certain and catastrophic when they are merely likely,
because one weak link chains two unrelated clusters together.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field

from idres.deterministic import MatchPair


@dataclass
class Entity:
    entity_id: str
    members: list[str] = field(default_factory=list)
    sources: set[str] = field(default_factory=set)
    weakest_link: float = 1.0
    merge_path: list[str] = field(default_factory=list)


# A pair below this is not allowed to JOIN two existing clusters, though it may
# still attach a loose record to one. The distinction matters: attaching one
# record risks one record, while joining two clusters risks everything in both.
BRIDGE_THRESHOLD = 0.90


class UnionFind:
    """Standard disjoint sets, with the weakest link tracked per root."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}
        self.size: dict[str, int] = defaultdict(lambda: 1)
        self.weakest: dict[str, float] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]   # path compression
            x = self.parent[x]
        return x

    def union(self, a: str, b: str, confidence: float) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self.size[ra] < self.size[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size[rb]
        self.weakest[ra] = min(
            self.weakest.get(ra, 1.0), self.weakest.get(rb, 1.0), confidence
        )
        return True


def entity_id_for(members: list[str]) -> str:
    """A stable id derived from the member set.

    Deriving the id from the members means re-running on unchanged data yields
    the same ids. An auto-increment id would renumber every entity on each
    rebuild, breaking every downstream reference to a profile.
    """
    digest = hashlib.sha256("|".join(sorted(members)).encode()).hexdigest()
    return f"ent_{digest[:16]}"


def resolve(pairs: list[MatchPair]) -> list[Entity]:
    """Build entities, applying the bridge rule to weak pairs."""
    uf = UnionFind()
    cluster_sizes: dict[str, int] = defaultdict(lambda: 1)
    applied: list[MatchPair] = []

    # Strong pairs first, so clusters form from certain evidence. Weak pairs
    # then attach to what already exists rather than defining the structure.
    for p in sorted(pairs, key=lambda x: -x.confidence):
        a = f"{p.left_source}:{p.left_id}"
        b = f"{p.right_source}:{p.right_id}"
        ra, rb = uf.find(a), uf.find(b)

        if ra != rb and p.confidence < BRIDGE_THRESHOLD:
            # Both already belong to multi-record clusters: this weak pair
            # would BRIDGE them. Refuse; the risk is every record in both.
            if uf.size[ra] > 1 and uf.size[rb] > 1:
                continue

        if uf.union(a, b, p.confidence):
            applied.append(p)

    groups: dict[str, list[str]] = defaultdict(list)
    for node in list(uf.parent):
        groups[uf.find(node)].append(node)

    out: list[Entity] = []
    for root, members in groups.items():
        out.append(Entity(
            entity_id=entity_id_for(members),
            members=sorted(members),
            sources={m.split(":", 1)[0] for m in members},
            weakest_link=round(uf.weakest.get(root, 1.0), 4),
            merge_path=[
                f"{p.left_source}:{p.left_id}~{p.right_source}:{p.right_id} "
                f"({p.method} {p.confidence})"
                for p in applied
                if uf.find(f"{p.left_source}:{p.left_id}") == root
            ],
        ))
    return out
